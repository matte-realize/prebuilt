# Prebuilt — Build Walkthrough

**How we build it, who does what, and in what order.**
Companion to the technical spec. **M** = Matthew (agents, verification, sim-to-real). **T** = teammate (simulator, GPU, plates, measurement).

**Constraint that shapes everything:** printers are available Saturday from about 8–9 AM until 10 PM. Friday night is pure software. Sunday is analysis and slides; nothing in the plan depends on Sunday printer access.

---

## 0. What "done" means

Three claims, nothing more:

1. **Network vs. oracle.** At equal print budgets, the networked collective closes most of the gap between isolated sites and the pooled-data oracle, with no raw data crossing a site boundary.
2. **Sim-to-real.** The measured oracle-gap-closed on real printers falls inside the range we committed from simulation before round 1.
3. **Robustness (simulation only).** A site broadcasting bad beliefs loses influence and the network recovers.

Headline chart: held-out error vs. pieces printed for isolated, networked, and oracle, with the predicted range overlaid.

---

## 1. Kickoff (Fri 9:00–9:30 PM, together)

Do not split up until these are written down and committed.

1. Create the repo with the layout in Section 2.
2. Agree on the interfaces in Section 3 and commit them as code.
3. Fill in the pre-registration values in Section 9 (thresholds, η, metrics). Commit; record the commit hash.
4. Confirm Saturday printer logistics: opening time, printer models, resin type, whether a print started before 10 PM can be collected Sunday morning.
5. Assign measurement duty: who scans each round on Saturday.

---

## 2. Repo layout

```
prebuilt/
  contracts.py        # shared dataclasses (Section 3) — change only together
  prereg/             # pre-registration file + hashes
  receipts/           # hash-chained logs, one chain per site
  plates/             # generator, piece library, plate files
  sim/                # Warp simulator, domain randomization
  measure/            # scanner pipeline, caliper entry
  model/              # physics models + posterior
  agents/             # agents, auction, credibility
  network/            # message schema + boundary enforcement
  arms/               # isolated, networked, oracle
  eval/               # held-out scoring, metrics, figures
  run.py              # one entry point: --source sim|real
```

---

## 3. Interfaces (the contract)

Everything downstream sees only these. The simulator and the real scanner both implement `Printer`, so nothing can tell them apart.

```python
@dataclass
class Piece:
    piece_id: str
    kind: str              # "pin" | "hole"
    nominal_d: float       # mm
    slot: tuple[int, int]  # grid position on plate
    arm: str               # "isolated" | "networked" | "oracle" | "heldout" | "seed"

@dataclass
class Plate:
    plate_id: str
    site: str              # "resin" | "pla"
    pieces: list[Piece]
    seed: int              # placement shuffle seed

@dataclass
class Measurement:
    piece_id: str
    plate_id: str
    site: str
    measured_d: float | None   # None if failed
    status: str                # "ok" | "failed"
    method: str                # "scanner" | "caliper" | "sim"

class Printer(Protocol):
    def print_and_measure(self, plate: Plate) -> list[Measurement]: ...

class Model(Protocol):
    def update(self, ms: list[Measurement]) -> None: ...
    def predict(self, piece: Piece) -> tuple[float, float]: ...  # mean, std

@dataclass
class Message:                 # the ONLY thing that crosses a site boundary
    sender_site: str
    round: int
    shared_params: dict[str, tuple[float, float]]  # process-agnostic only
    credibility: dict[str, float]
    hypotheses: list[str]
```

The message serializer rejects any field not in `Message`. That rejection is the privacy guarantee, and it's logged.

---

## 4. Friday night build (software only)

### Phase A — Fri 9:30 PM to 1 AM

**M**
1. **Receipts.** Append-only log per site; each entry hashes the previous one. Log every plate, measurement, bid, clearing result, and message.
2. **Physics models.** Resin: Dp, Ec, lateral bleed, shrinkage. PLA: extrusion width, hole polygon shrinkage, first-layer flare. Plus process-agnostic terms: feature-size coefficient and plate-position gradient. Tag every parameter `shared` or `site`.
3. **Posterior.** Particle posterior (a few thousand particles), Gaussian measurement likelihood, importance reweighting with resampling. Implements `Model`. Vectorized in PyTorch or Warp so all agents update in one call.

**T**
1. **Piece library.** Pins and holes from about 1 to 8 mm nominal diameter, in steps fine enough to bracket expected fit transitions. Precompute every candidate once.
2. **Plate generator.** Roughly 100 × 100 mm plate, 3 mm thick, regular grid of slots. Holes go through the plate; pins are short standing cylinders. Three corner fiducials plus an orientation notch for the scanner. Piece identity comes from grid position, not printed text. Output STL for both printers.
3. **Seed plate files.** A fixed calibration grid plus held-out pieces, for both printers. These print first thing Saturday, so they must be finished tonight.

**Done when:** seed plate STLs exist and slice cleanly for both printers; the posterior updates on fake measurements and predicts with intervals.

### Phase B — Fri 1 AM to 4 AM

**M**
1. **Agents.** Each agent = an evidence filter + a prior + a proposal rule. Physics (datasheet priors), calibration (seed measurements only), printability (failure history), geometry and empirical (all site measurements, different features). Each proposes the library pieces with the highest predictive std under its own posterior, discounted by print height.
2. **Auction.** Arm slot pool split across agents in proportion to credibility, largest-remainder rounding. Agents fill slots with their top proposals. The rule never picks content.
3. **Credibility.** After each round: leave-one-agent-out change in held-out log predictive density; c ← c · exp(η · ΔLPD), normalize.
4. **Message boundary.** Typed `Message`, rejecting serializer, logged to both sites' receipt chains. Receiving site applies shared-parameter posteriors as a tempered prior, with the tempering weight set by sender credibility.
5. **Three arms.** Isolated (one agent, own site's data, max predictive std). Networked (auction + messages). Oracle (one agent, both sites' raw data, max predictive std). All three are scored by the same site model, so they differ only in which pieces they chose and, for networked, what they received.

**T**
1. **Simulator.** Implements `Printer`. Each simulated site draws true parameters from wide ranges around the datasheet values, adds measurement noise, and adds two effects the agents don't model: a plate-position gradient and an orientation-dependent error.
2. **Domain randomization + batching.** Thousands of simulated sites in one Warp launch.
3. **Scanner pipeline, first pass.** Detect fiducials, rectify, fit circles to holes (backlit) and pin tops (dark background). Test on a printed paper target with known circles to get a scale and error estimate.

**Done when:** `run.py --source sim` runs a full multi-round experiment for all three arms and prints held-out error per arm.

### Phase C — Fri 4 AM to 8 AM (stagger sleep)

One of you sleeps roughly 4–7:30 while the other runs Phase C; whoever slept takes the first printer shift.

1. **Run the sim experiment across many seeds.** Confirm networked lands between isolated and oracle. If it doesn't, debug before anything else; this is the whole project.
2. **Tune and freeze** η, credibility floor, slot split, and proposal discount in simulation only. Commit the frozen config with a hash.
3. **Draft the predicted range** for oracle-gap-closed on a two-site real setup. It gets recomputed after seed calibration (Phase D) and committed then.

**Done when:** frozen config committed; one figure showing the three arms across seeds.

---

## 5. Saturday printer day (about 8–9 AM to 10 PM)

Print and measurement times below are placeholders; adjust once you see real durations. Resin needs wash and cure time on top of printing.

| Approx. time | Printers | Software |
|---|---|---|
| 8:30 | Tiny test piece on each printer to confirm the pipeline end to end | Final checks on the scanner |
| 9:00 | **Seed plates** on both printers | Sim sweeps running on Nebius |
| ~11:00 | Collect, wash/cure resin, scan both | Ingest seed data |
| ~11:30 | — | **Phase D:** calibrate the simulator to seed data only; recompute the predicted range; commit it with a hash. Collective settings stay frozen. |
| ~12:00 | **Round 1** (all three arms + held-out) | Auction runs in seconds; messages exchanged after measurement |
| ~2:30 | Scan round 1 | Update posteriors, credibility, messages |
| ~3:00 | **Round 2** | — |
| ~5:30 | Scan round 2 | Update |
| ~6:00 | **Round 3** | Start figures with rounds 1–2 |
| ~8:30 | Scan round 3 | Update |
| 9:00–10:00 | Reprint any failed plate, or a short round 4 if time allows | — |

**Every real plate:** human approves for printability only; any change is logged. Duplicates on every plate. Held-out pieces at fixed, pre-registered slots spread across plates.

**Measurement routine (per plate):**
1. Scan with backlight for holes; scan on a dark background for pins.
2. Pipeline outputs a `Measurement` per piece; failed pieces get `status="failed"`.
3. Caliper-check a random sample of about 10 pieces; log agreement.
4. Physically test a few pin/hole pairs for fit; log against predicted fit class.

**Saturday checkpoints:**
- **Seed plates fail:** fix the obvious cause once (adhesion, supports, orientation) and reprint. A second failure on the same printer → drop to one real site plus simulated sites.
- **5 PM, behind schedule:** stop adding rounds; measure what exists.
- **10 PM:** printers done. Everything after is software.

---

## 6. Saturday night (software only)

**M**
1. Score real rounds: held-out error per arm, oracle-gap-closed, comparison to the committed predicted range.
2. Privacy audit: replay message receipts and show every crossing matched the schema.
3. Hypothesis agent (Nemotron), async: feed residual summaries and the unmet-needs log; record what it proposes. Exploratory only.

**T**
1. Recalibrate the simulator with all real data; report which parameters and unmodeled effects it got wrong.
2. Robustness sweep: inject a bad-faith site; plot its credibility and network recovery.
3. Scaling sweep: 2, 5, 10, 25 sites; plot oracle-gap-closed vs. number of sites.

**Done when:** all figures exist from real data plus sweeps.

---

## 7. Sunday

| Time | Task |
|---|---|
| until 9 AM | Finish anything outstanding; if a print ran overnight and is collectable, scan and include it |
| 9 AM | **Data freeze.** No new data after this. |
| 9 AM – 1 PM | Slides (Section 10), rehearse the one-line pitch, record a backup demo video |
| 1 – 2:30 PM | Final pass; submit slides by 2:30 |
| 4 PM | Present |

---

## 8. Fallback quick reference

| Situation | Do this |
|---|---|
| One printer unusable | One real site + simulated sites anchored to its data |
| Only seed plates succeed | Calibrate the simulator; run the network in simulation; real plates as validation |
| No usable prints | Pure simulation, reported honestly, with the committed prediction as the claim to test later |
| Scanner unreliable | Calipers on a smaller subset; reduce piece count per plate |
| Network doesn't beat isolated in sim (Phase C) | Stop and debug before printing; check message tempering and shared-parameter tags first |

---

## 9. Pre-registration file (fill in at kickoff)

```
claims: [network_vs_oracle, sim_to_real_range, robustness_sim]
arms: [isolated, networked, oracle]
fit_classes_mm:  resin: {press: <_, slip: _–_, loose: >_}
                 pla:   {press: <_, slip: _–_, loose: >_}
failed_plate_fraction: _
eta: _          (frozen after Phase C)
credibility_floor: _
heldout_slots: [list per plate]
metrics: [heldout_MAE, heldout_LPD, fit_class_acc, interval_coverage_90, oracle_gap_closed]
predicted_range_oracle_gap_closed: _–_   (committed after Phase D, before round 1)
failure_rules: failed pieces are printability outcomes; held-out failures reported, scored on survivors
```

---

## 10. Slide outline

1. One-line pitch.
2. The problem: every site re-learns its machines; raw data can't be shared.
3. The setup: two sites, one boundary, what crosses and what doesn't.
4. How the collective decides: auction, credibility, messages.
5. Sim-to-real: frozen in simulation, prediction committed, then real printers.
6. **Headline chart:** isolated vs. networked vs. oracle, with the predicted range.
7. Robustness and scaling (simulation).
8. Privacy audit replay.
9. What reality taught the simulator.
10. Closer: where this goes next. Print anywhere, trust the part.
