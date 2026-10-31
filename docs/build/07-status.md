# Build: Status and Phase C Findings

As of Sat Oct 31. T's Phase C sweep results: `hpc/sweeps/phase_c/README.md` (recommends 16 seed pieces, 6 slots per arm). M's Phase A and B tasks are built and tested (`.venv/bin/python -m pytest -q`, 34 tests).

## What runs

- `python -m prereg.check` checks `prereg/prereg.yaml`: the held-out manifest hash, and that every key under `config` is a real `Config` field. It lists blank fields and prints the file's sha256. `run.py --source real` builds its config from the prereg (CLI tuning flags apply to simulation only) and refuses to start with blanks. Without a predicted range it runs the seed plate only. It writes the prereg sha256 onto both receipt chains before each run of rounds.
- `python -m plates.seed` writes seed plates (JSON + watertight STL) for both sites and `prereg/heldout.json`.
- `python run.py --source sim --seeds 20` runs the full three-arm, two-site experiment on the NumPy reference simulator (`sim/reference.py`) and runs the privacy audit for every seed. About 3 s per seed at 1000 particles.
- `python run.py --source real` drives the real printers. It writes plate files, asks for human approval, waits for `scans/<site>/<plate>-holes.png` and `-pins.png`, measures them, and checkpoints after every round (`receipts/real/state.pkl`). Rerun the same command to resume.
- `python -m measure.rehearsal --rounds 2 --out /tmp/reh` rehearses the real loop without printers: `RealPrinter`, plate files, approval prompts, scan files, scanner, receipts, checkpoint and resume, with a simulated printer rendering the scans. Scanner vs. printed truth on synthetic scans: about 5 µm RMS, under 30 µm max, no false or missed failures.
- `python -m measure.target plates/out/resin/resin-seed.json target.pdf` writes a 1:1 paper target for checking the scanner before any plate prints.
- `python -m eval.audit receipts/real/resin.jsonl receipts/real/pla.jsonl` replays the receipt chains for the privacy check.

## Phase C findings (for T's sweeps; decide before freezing config)

Run sweeps with `run.py --source sim --seeds 20 --out results.json`. In simulation, rows include `mae_truth`: error against the noise-free diameters, recorded for evaluation only and never shown to agents.

1. **With the full seed plate, the arms can't separate.** Over 20 seeds × 2 sites, isolated, networked and oracle all sit at MAE ≈ 0.031 mm, within ±0.0005 mm of each other. Even against the noise-free truth they're within ±0.0006 mm (≈ 0.008 mm). The 56-piece seed plate already teaches each site everything the 3 shared parameters can offer.
2. **With less data per site, sharing helps.** With 8 seed pieces and 6 slots per arm (`--seed-pieces 8 --slots 6`), error against the noise-free truth at round 2 is isolated 0.0163, networked 0.0133, oracle 0.0140 mm. That's an 18% reduction for networked, about 3 standard errors. **Decided: shrink.** Following T's sweep, the seed plate now has 16 calibration pieces (`plates.seed.SEED_PIECES`; 8 pins + 8 holes spread over 1.5–7.0 mm, no duplicates) plus the 8 held-out, and `Config` defaults to 6 slots per arm. The STLs and paper target in `plates/out/` are regenerated. `seed_pieces=None` still gives the full 56 for sweeps.
3. **Real held-out data probably can't resolve the effect.** Measured MAE is dominated by measurement noise (σ ≈ 0.03–0.04 mm). A 0.003 mm difference in model error doesn't show up in measured MAE, even with 40 held-out pieces per site (measured differences are +0.0005 ± 0.0008 mm). So the real-printer claim should be sim-to-real (claim 2), not detecting H1 on real data alone. Say so in the prereg.
4. **Why the oracle lost to networked, and the fix.** The walkthrough gives isolated and oracle one max-information agent each, but networked gets the five-agent auction. So isolated minus networked measured the agents' piece choices as well as sharing. Evidence, 20 seeds, 16 seed pieces, 6 slots, 1000 particles, round 2 (µm):
   - Walkthrough arms: iso − net 1.75 ± 0.92, oracle − net +2.19 ± 0.59 (oracle worse).
   - Messages cut (`share_messages=False`): iso − net is still 1.33 ± 0.70. That part is the auction, not the network. *(Superseded: 192 seeds give +0.15 ± 0.24 / +0.28 ± 0.25; see below.)*
   - **`Config.same_agents=True` (now the default):** isolated and oracle also choose by the agent auction, at uniform credibility. iso − net 1.96 ± 0.74, oracle − net −0.26 ± 0.74. Networked now lands between isolated and oracle, and the difference measures sharing only.

   **Same agents didn't fully fix it; Monte Carlo mixing was the main cause.** At 384 seeds (same settings, 3 rounds, all current defaults), the oracle still lost with `same_agents=True`: oracle − net +0.55 ± 0.19, +0.69 ± 0.17, +0.55 ± 0.18 µm in rounds 1-3. The −0.26 ± 0.74 above was 20-seed noise. To separate inference from piece choice, `Config.oracle_data="networked"` fits the oracle to exactly the networked arm's measurements, so only inference differs. The oracle still lost: +0.27 ± 0.13, +0.56 ± 0.09, +0.30 ± 0.13. The cause is MH steps: every posterior gets 3 random-walk MH steps per resample, and RW-MH mixes about 1/dim as fast per step. So the 18-dim hierarchical oracle's predictive means carried twice a 9-dim site's Monte Carlo error: across particle seeds on fixed seed-plate data, 3.9 vs 2.0 µm sd at 1000 particles. **Fix: `Config.oracle_mh_steps`** (default None = 3 × oracle dim / largest site dim, which is 7 for resin + pla; 3 restores the old behavior). The oracle's MC sd drops to 1.6 µm, and `tests/test_phase_b.py` checks it stays under 1.2× a single site's. Oracle − net, 384 seeds:

   | | round 1 | round 2 | round 3 |
   |---|---|---|---|
   | identical data, old (3 steps) | +0.27 ± 0.13 | +0.56 ± 0.09 | +0.30 ± 0.13 |
   | identical data, fixed | −0.06 ± 0.12 | −0.02 ± 0.05 | +0.01 ± 0.05 |
   | own data, old | +0.55 ± 0.19 | +0.69 ± 0.17 | +0.55 ± 0.18 |
   | own data, fixed (new default) | +0.07 ± 0.18 | +0.39 ± 0.16 | +0.31 ± 0.17 |
   | fixed, common print noise | +0.03 ± 0.14 | +0.41 ± 0.15 | +0.58 ± 0.14 |
   | fixed, common noise, oracle prints networked's pieces | −0.15 ± 0.13 | +0.22 ± 0.12 | +0.15 ± 0.10 |

   This is also why particle count didn't help: with 3 steps, 4× the particles only cut the oracle's MC sd from 3.9 to 2.8 µm. The earlier 12-seed particle and 4×-MH tests had SE ≈ 1 µm, too coarse to see a 0.5 µm effect.

   The remaining +0.3-0.4 µm in rounds 2-3 is piece choice. The oracle's auction runs at uniform credibility. Networked's runs at learned credibility, and that picks slightly better pieces. Printing networked's pieces in the oracle arm cuts the gap to +0.15 ± 0.10. Dropping challenge and spawn (`challenge=False, dormant=()`) leaves it at +0.44 ± 0.14, so learned credibility does this, not the challenge round. Per-arm print noise is not a cause. `make_world(..., crn=True)` gives every arm the same noise draws for the same candidates. That lowers the SE but doesn't shrink the gap, and arms with independent, identically distributed noise can't be biased by it anyway. So the oracle is now an upper bound on inference with the same data. With its own uniform-credibility choices, it ties networked in round 1 and is 0.3-0.4 µm worse in rounds 2-3. Iso − net is unchanged (1.6-1.9 ± 0.2 µm), so oracle-gap-closed is still above 1 and shouldn't be reported yet. Options: let the oracle print networked's pieces, which makes it a clean data-only upper bound, or report only iso − net.

   **Decided (M): the primary H1 metric is iso − net in µm (mae_truth in sim, measured MAE on real).** The oracle keeps its pre-registered definition (pooled raw data, its own uniform-credibility auction) and is reported next to it as a reference, not as oracle-gap-closed. Printing networked's pieces in the oracle arm would mean changing an arm to make the benchmark come out right, and on the real printers it means reprinting networked's plate. iso − net answers the question we're asking (does sharing help?) and is already 8+ SE from zero. Put this in the prereg.

   **Decided (M): MH steps go into T's sweep, not a new default yet.** Every arm is limited by mixing at 3 steps (single-site MC sd 2.0 µm at 3 steps, 0.75 at 12). `Config.mh_steps` (default 3) now sets the single-site steps, and the oracle's scales from it, capped at 15 for the Warp posterior. `tuning.py --stage particles` now crosses particles with mh_steps ∈ {3, 6}. T: freeze the pair with the rest of the config, costing compute against MC sd.

   **Resolved conflict** with the messages-cut line above (the 192-seed number stands). In 192 seeds on the pre-challenge code with walkthrough arms and the MH fix, cutting messages left iso − net at only +0.15 ± 0.24 and +0.28 ± 0.25 µm (rounds 2, 3), not 1.33. Most of the walkthrough iso − net was sharing, and the walkthrough oracle's loss was mostly MC error, not the max-information agent. `same_agents=True` is still the cleaner design.

   Also not the cause: oracle particle count alone (`Config.oracle_particles`), the flat oracle, and unmodeled sim effects (radial term off, shared jitter off: the identical-data gap persisted with 3 MH steps). The oracle stays hierarchical (`Config.oracle_hierarchical`). **This deviates from the walkthrough's arm definitions; say so in the prereg.** T: rerun the seed-plate and tuning sweeps with the new default before drafting the predicted range. 20 seeds are too noisy to commit numbers from.
5. **Between-site spread is a setting.** `Config.between_site_sd` (default 0.25 of prior std) widens every incoming message. Without it, near-noise-free sites with tight but different beliefs made the networked arm much worse (MAE 0.10 vs 0.001 mm) until trust collapsed. Pre-register it; don't tune it on real data.
6. **η = 20 is too high.** Honest senders lose trust from noise in the leave-one-out difference: in one bad-site run the honest sender dropped to 0.25. Sweep η, `trust_init` and `cred_floor` together, scoring both "bad site loses trust" and "honest site keeps it".
7. **Held-out LPD can swing by tens of nats** when the model is wrong. **Decided: clip per piece.** Credit now averages per-piece LPD differences, each clipped to ±`Config.lpd_clip` nats (default 2.0; `--lpd-clip`, `None` reproduces the old numbers bit for bit), for both agent dLPD and sender leave-one-out dLPD (`agents.credibility.delta_lpd`). Why 2 nats: with measurement noise σ (0.03–0.04 mm), moving one prediction from error e₀ to e₁ is worth (e₀² − e₁²)/2σ², so turning a 2σ miss (about the 95th percentile of honest residuals) into a hit is worth 2 nats. Swings bigger than that come from pieces both fits miss badly, where the difference is shift × residual and amplifies noise. One piece now moves a round's dLPD by at most 2/n_heldout nats. Sim check (10 seeds, 16 seed pieces, 6 slots, η = 20, round 3): all honest, the clip never binds (max per-round |dLPD| 0.30 sender, 0.51 agent) and every number is unchanged. With pla bad, max |dLPD| drops from 16 to 1.5 (sender) and 64 to 1.9 (agent). pla still loses trust in all 10 seeds (min trust about 1e-13 instead of 1e-141), MAE against truth is the same within noise (networked 13.01 → 12.84 µm, isolated 15.54 → 15.60), and retirements go 45 → 43. The clip does **not** fix finding 6: honest senders still drop below 0.5 in 3–4 of 10 seeds, and those dLPDs are small (≤ 0.3 nats) times η = 20. That is η's job. `tuning.py --stage clip` sweeps the clip if needed.

## Replies to T (08-warp-posterior.md)

- **`model/posterior.py` refactor (d5df0dd):** reviewed and approved. It's behavior-preserving, and it's already on main.
- **NumPy `predict` at 17 ms per piece:** doesn't reproduce. On your benchmark's workload (60 training pieces, 200 held-out) on an idle M-series Mac it's 0.23 ms per piece at 20k particles and 0.04 ms at 2k. The 17 ms was most likely contention from the other job on the shared machine (BLAS threads). Rerun the NumPy column with `OMP_NUM_THREADS=1` on an idle node.

## Challenge round and spawn (built Oct 31)

Both are on by default (`Config.challenge`, `Config.dormant`), since spec 8.1 defines the networked arm as the full Section 6 system. `run.py --no-challenge --no-spawn` turns them off; with both off, results match the earlier code. They change results, so T's Phase C numbers predate them.

**Decided (M):** keep both on. The config isn't frozen yet, and freezing it with the full system beats bolting features on after the prereg. T: run the tuning sweep with them on, and add `challenge_eig` (and `spawn_threshold`) to the `knobs` stage. `Message.unmet_needs` is a change to the shared contract (`contracts.py`): it's optional with an empty default, and older receipt chains still pass the audit. T, please confirm it works for the Warp side. No real-round checkpoints exist yet, so the new state fields don't break any resume.

- **Challenge** (`agents/challenge.py`, spec 6.5 step 3). After proposing, each agent may flag one proposal another agent would win a slot with. It flags "redundant with mine" if the same piece is among its own winning proposals, or "already predictable from my evidence" if its own posterior's expected information gain on the piece is below `Config.challenge_eig` (0.05 nats, a placeholder to freeze with η). Flaggers go in order of credibility. A flagged piece moves to the end of its owner's list, so it prints only if the owner has slots to spare. In credit, the flagger gets ± (leave-one-piece-out held-out dLPD of the test piece − the round's average dLPD per piece), added to its own dLPD. The test piece is the flagged piece if it printed (the flagger gains if it's below average) or else the piece that replaced it (the flagger gains if that one is above average). Every flag and its credit goes on the receipt chain (`challenge`, `challenge_credit`) and into `Results.challenges`.
- **Spawn** (`arms/experiment.py` `_unmet_needs`, `_spawn`, spec 6.7). One dormant template exists: `position`, which proposes by information gain on `pos_gx`/`pos_gy`, with candidates scored at a plate corner. After credit, each site correlates its networked posterior's standardized training residuals with squared distance from the plate center. The physics model has linear plate gradients only, so this checks for the sim's unmodeled radial term. If |z| ≥ `Config.unmet_z` (2.0), the site logs an unmet need and broadcasts it in the new `Message.unmet_needs` field: template, question, and z only, validated by `network/protocol.py`. A site wakes the template with uniform credibility (1/(n+1)) once its own plus incoming entries reach `Config.spawn_threshold` (2), so a question raised at one site can wake the agent at the other. Retired agents don't respawn. In 5 seeds at 16 seed pieces and 6 slots, position woke at both sites in round 2 in 4 of 5 seeds.
- **Open:** no orientation template (`Piece` has no orientation). Challenge outcomes aren't broadcast (the spec allows it but doesn't require it). The position agent targets the modeled linear gradient, not the radial term that wakes it.

## Fit-class accuracy (built Oct 31)

`eval/fit.py`; the definition is in `prereg.yaml` under `fit_classes_mm`. `run.py` adds `fit_acc`, `fit_pairs` (and `fit_acc_truth` in simulation) to every score row once the prereg thresholds are filled. In a sim check with placeholder thresholds (press < 0.05, slip 0.05–0.3, loose > 0.3 mm; 4 seeds), accuracy is 0.94–0.98 for every arm on 4–15 pairs per site per round. It can't separate the arms, so report it and don't headline it.

## Predicted range: metric must be chosen (reply to hpc/phase_d/README.md)

The prereg field is now `predicted_range: {metric, round, range}`. `metric` is `iso_minus_net_mae_um` (Phase D's primary) or `oracle_gap_closed_mae`, and it must be set before the seed plate. `range` is committed after Phase D. **M's recommendation: `iso_minus_net_mae_um`.** Gap-closed divides by isolated − oracle, which is near zero on measured MAE, so it swings wildly. The catch: on 8 held-out pieces per plate the measured difference is about ±1 µm of noise (finding 3), so expect a wide range that straddles zero. The claim is then mainly that reality doesn't contradict the simulator.

## Headline chart (built Oct 31)

`python -m eval.figures.headline sim.json [--real real.json] [--truth]` takes `run.py --out` results and writes `eval/figures/out/headline.{png,pdf}`. Left panel: held-out MAE per arm against pieces printed per site, mean ± 1 SE, with real rounds as markers. Right panel: isolated − networked per round in µm (median, 5–95% over seeds), the committed prediction box when `predicted_range.metric` is `iso_minus_net_mae_um`, and the real value.

**Open question it surfaced:** on current `main` (12 seeds, 1000 particles, noise-free MAE), the oracle trails networked again at round 3 (+1.4 ± 0.9 µm). With `--no-challenge --no-spawn` it's −0.9 ± 0.7 at round 2 and +0.6 ± 0.7 at round 3. Challenge and spawn run only in the networked arm, so they may bring back the selection advantage that `same_agents` removed. That's suggestive, not settled. T: include the challenge-and-spawn off variants in the sweep. If it holds, either run the challenge round in all three arms' auctions too, or turn both off for the claim.

## Not built yet (M)

- Hypothesis agent.
- Scanner on real scans: still to check with the paper target, then a test print. Synthetic stress test, 400 dpi, full plate, 3 scans each (RMS / max error, µm):

  | defect | holes | pins |
  |---|---|---|
  | clean | 1.9 / 8.7 | 4.7 / 15 |
  | lighting gradient 30% / 60% | 4.2 / 13, 5.6 / 21 | 13 / 39, 22 / 80 |
  | pin shadow 0.3 mm | n/a | **51 / 65** (bias −50, spread 8) |
  | 150 dust specks | 5.8 / 22 | 9.1 / 57 |
  | blur 3 px | **15 / 76** | 14 / 34 |
  | JPEG q80, 300 dpi, noise 0.05 | under 7 / 16 | under 15 / 36 |

  Fixes: a lighting gradient used to break fiducial detection on pin scans, so it now falls back to local thresholds. Shadows bias pins by a near-constant amount, so when `{plate}-caliper.csv` exists, `RealPrinter` subtracts the per-kind median scanner − caliper offset (`measure.manual.scanner_offsets`), and the caliper sample is now split evenly between pins and holes. **On the day:** always do the ~10 caliper checks per plate. Scan at 400 dpi or more, lossless (PNG), and in focus. Blur is the one defect the offset doesn't remove.
- Slice-check the seed STLs in PreForm and the PLA slicer.
