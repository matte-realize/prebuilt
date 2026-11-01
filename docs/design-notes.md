# Design Notes

The decisions behind the registered design, what each one rests on, and the commands that run each part. Headline results are in the [README](../README.md) and the sweep READMEs under `hpc/sweeps/`; this page explains why the experiment is set up the way it is. Where the build departs from the original build plan ("the walkthrough" in the pre-registration), `prereg/prereg.yaml` lists each change under `deviations`, with the original choice stated next to it.

## The registered configuration

- **Config** (from `prereg/prereg.yaml`, checked by `python -m prereg.check`): η 5, trust_init 1.0, cred_floor 0.05, discount 0.2, 4000 particles, 6 MH steps; challenge round and spawn off. `run.py --source sim` and `viewer.export` build the same config from the prereg.
- **Design:** 16 seed pieces + 8 held-out per plate, 6 slots per arm, the same agents choose pieces in all three arms, hierarchical oracle with scaled MH steps. Primary metric: isolated − networked held-out MAE in µm.
- **Predicted range:** `predicted_range.range` is still blank. It is committed only after a real seed plate is measured and Phase D runs (`hpc/phase_d/README.md`), and no real seed run took place; `prereg.check` reports *ready for seed*.
- **Tests:** `.venv/bin/python -m pytest -q`. Warp tests skip without warp-lang and a CUDA GPU.

## What runs

- `python -m prereg.check` checks `prereg/prereg.yaml`: the held-out manifest hash, and that every key under `config` is a real `Config` field. It lists blank fields and prints the file's sha256. `run.py --source real` builds its config from the prereg (CLI tuning flags apply to simulation only) and refuses to start with blanks. Without a predicted range it runs the seed plate only. It writes the prereg sha256 onto both receipt chains before each run of rounds.
- `python -m plates.seed` writes seed plates (JSON + watertight STL) for both sites and `prereg/heldout.json`.
- `python run.py --source sim --seeds 20` runs the full three-arm, two-site experiment on the NumPy reference simulator (`sim/reference.py`) and runs the privacy audit for every seed. About 0.8 s per seed at 1000 particles.
- `python run.py --source real` drives real printers. It writes plate files, asks for human approval, waits for `scans/<site>/<plate>-holes.png` and `-pins.png`, measures them, and checkpoints after every round (`receipts/real/state.pkl`). Rerun the same command to resume. Step by step: [guides/real-site-run.md](guides/real-site-run.md).
- `python -m measure.rehearsal --rounds 2 --out /tmp/reh` rehearses the real loop without printers: `RealPrinter`, plate files, approval prompts, scan files, scanner, receipts, checkpoint and resume, with a simulated printer rendering the scans.
- `python -m measure.target plates/out/resin/resin-seed.json target.pdf` writes a 1:1 paper target for checking a scanner before any plate prints.
- `python -m eval.audit receipts/real/resin.jsonl receipts/real/pla.jsonl` replays the receipt chains for the privacy check.
- `python -m eval.figures.headline sim.json [--real real.json]` draws the headline chart; `python -m viewer.export ... --open` builds the demo page; `python docs/slides/make_pitch.py` rebuilds the pitch deck.
- `python -m agents.hypothesis --checkpoint receipts/real/state.pkl [--dry-run]` runs the hypothesis agent between rounds.

In simulation, score rows include `mae_truth`: error against the noise-free diameters, recorded for evaluation only and never shown to agents.

## Why the experiment looks like this

1. **A small seed plate, so the arms can separate.** With the full 56-piece seed plate, isolated, networked and oracle all sit at MAE ≈ 0.031 mm, within ±0.0005 mm of each other (20 seeds × 2 sites); even against noise-free truth they're within ±0.0006 mm. The full plate already teaches each site everything the 3 shared parameters can offer. With 8 seed pieces and 6 slots per arm, networked cuts error against truth by 18% at round 2 (about 3 SE). So the seed plate has 16 calibration pieces (`plates.seed.SEED_PIECES`; 8 pins + 8 holes over 1.5–7.0 mm, no duplicates) plus the 8 held-out, and `Config` defaults to 6 slots per arm. `seed_pieces=None` still gives the full 56 for sweeps.

2. **Real held-out data can't resolve the effect, so the real-printer claim is sim-to-real.** Measured MAE is dominated by measurement noise (σ ≈ 0.03–0.04 mm). A 0.003 mm difference in model error doesn't show up in measured MAE, even with 40 held-out pieces per site (measured differences +0.0005 ± 0.0008 mm). The registered real-printer claim is therefore that the measured value lands in a range predicted from simulation (claim 2), not that real data alone detects the sharing gain.

3. **The same agents choose pieces in every arm.** In the original plan, isolated and oracle each got one max-information agent while networked got the five-agent auction, so isolated − networked measured piece choice as well as sharing. With `Config.same_agents=True` (the default), isolated and oracle also choose by the auction, at uniform credibility, and the difference measures sharing only. A 192-seed check with the original arms and messages cut left iso − net at +0.15 ± 0.24 and +0.28 ± 0.25 µm (rounds 2, 3), so most of the original gap was sharing too; `same_agents` is still the cleaner design.

4. **The oracle needs more MH steps.** Even with identical data, the oracle lost to networked (+0.27 ± 0.13, +0.56 ± 0.09, +0.30 ± 0.13 µm in rounds 1–3, 384 seeds, `Config.oracle_data="networked"`). The cause is mixing: random-walk MH mixes about 1/dim as fast per step, so at 3 steps the 18-dim hierarchical oracle carried twice a 9-dim site's Monte Carlo error (3.9 vs 2.0 µm sd at 1000 particles). `Config.oracle_mh_steps` (default: `mh_steps` × oracle dim / largest site dim, capped at 15; 14 in the registered config) brings the oracle's MC sd to 1.6 µm; `tests/test_phase_b.py` checks it stays under 1.2× a single site's. Oracle − net, 384 seeds:

   | | round 1 | round 2 | round 3 |
   |---|---|---|---|
   | identical data, 3 steps | +0.27 ± 0.13 | +0.56 ± 0.09 | +0.30 ± 0.13 |
   | identical data, scaled steps | −0.06 ± 0.12 | −0.02 ± 0.05 | +0.01 ± 0.05 |
   | own data, 3 steps | +0.55 ± 0.19 | +0.69 ± 0.17 | +0.55 ± 0.18 |
   | own data, scaled steps (default) | +0.07 ± 0.18 | +0.39 ± 0.16 | +0.31 ± 0.17 |
   | scaled, common print noise | +0.03 ± 0.14 | +0.41 ± 0.15 | +0.58 ± 0.14 |
   | scaled, common noise, oracle prints networked's pieces | −0.15 ± 0.13 | +0.22 ± 0.12 | +0.15 ± 0.10 |

   This is also why more particles didn't help: at 3 steps, 4× the particles only cut the oracle's MC sd from 3.9 to 2.8 µm. The remaining +0.3–0.4 µm in rounds 2–3 is piece choice: networked's auction runs at learned credibility and picks slightly better pieces than the oracle's uniform-credibility auction (printing networked's pieces in the oracle arm cuts the gap to +0.15 ± 0.10). Not causes: oracle particle count alone, the flat oracle, unmodeled sim effects, per-arm print noise (`make_world(..., crn=True)` lowers the SE but not the gap). `Config.mh_steps` sets the single-site steps (default 3, 6 in the registered config).

5. **The primary metric is isolated − networked in µm, not oracle-gap-closed.** The oracle keeps its registered definition (pooled raw data, its own uniform-credibility auction) and is reported next to the result as a reference. Making it print networked's pieces would change an arm to make the benchmark come out right, and on real printers it would mean reprinting networked's plate. Gap-closed divides by isolated − oracle, which is near zero on measured MAE and swings wildly. iso − net answers the question asked (does sharing help?) and is 8+ SE from zero. The prereg field is `predicted_range: {metric, round, range}` with `metric: iso_minus_net_mae_um`.

6. **Between-site spread is a registered setting.** `Config.between_site_sd` (default 0.25 of prior std) widens every incoming message. Without it, near-noise-free sites with tight but different beliefs made the networked arm much worse (MAE 0.10 vs 0.001 mm) until trust collapsed. It's registered, not tuned on real data.

7. **η = 5.** At η = 20, honest senders lost trust from noise in the leave-one-out difference (one honest sender fell to 0.25 in a bad-site run). η, `trust_init` and `cred_floor` were swept together, scoring both "bad site loses trust" and "honest site keeps it" (`hpc/sweeps/phase_c/README.md`).

8. **Held-out LPD is clipped per piece.** When the model is wrong, held-out LPD can swing by tens of nats. Credit averages per-piece LPD differences, each clipped to ±`Config.lpd_clip` nats (default 2.0; `None` reproduces unclipped numbers bit for bit), for both agent dLPD and sender leave-one-out dLPD (`agents.credibility.delta_lpd`). Why 2: with measurement noise σ, moving one prediction from error e₀ to e₁ is worth (e₀² − e₁²)/2σ², so turning a 2σ miss (about the 95th percentile of honest residuals) into a hit is worth 2 nats; bigger swings come from pieces both fits miss badly. With all sites honest the clip never binds; with a bad PLA site max |dLPD| drops from 16 to 1.5 (sender) and 64 to 1.9 (agent), PLA still loses trust in all 10 seeds, and MAE is unchanged within noise. The clip doesn't stop honest senders losing trust at high η; that is η's job (point 7).

9. **Held-out count stays at 8.** A single real run comes out positive (networked beats isolated on measured error) only about 60–70% of the time. More held-out pieces per plate don't change that (100 paired worlds, share of runs with iso − net > 0):

   | held-out per plate | measured, round 3 | measured, rounds 1–3 pooled | noise-free, round 3 |
   |---|---|---|---|
   | 8 | 69% | 63% | 70% |
   | 16 | 66% | 72% | 68% |
   | 24 | 66% | 67% | 74% |

   Even with perfect measurement, networked wins in only ~70% of worlds: the benefit of sharing varies from one printer pair to the next, so measurement isn't the bottleneck. One real run is one draw from that spread, which is why the claim is that the measured value lands in the predicted range, not that networked must win.

## Prereg choices

- **Fit classes on measured clearance.** Resin: press < 0 mm, slip 0.05–0.15, loose > 0.2. PLA: press < 0, slip 0.10–0.25, loose > 0.35. Resin scores few pairs (0–5 per round in sim), so the metric is thin there; it's reported anyway rather than widening realistic thresholds. `eval/fit.py` scores them, and `eval/metrics.py` adds `fit_acc`, `fit_pairs` (and `fit_acc_truth` in simulation) to every score row. In simulation it's 0.94–0.98 for every arm, so it's reported, not headlined.
- **`failed_plate_fraction: 0.5`.** Agents deliberately probe small features near the failure limit, so many single failures are expected; a plate-level fault fails most pieces.
- **Challenge round and spawn off for the claim.** They act only in the networked arm, so they bring back the piece-selection confound that `same_agents` removes (with them on, the oracle trailed networked by +1.4 ± 0.9 µm at round 3; with them off, −0.9 ± 0.7 and +0.6 ± 0.7 at rounds 2–3). They remain available for a secondary analysis (`run.py --challenge --spawn`).
- **Fallback tiers** (`prereg.yaml` `fallback_tiers`) commit which claims hold if printing falls short. Tier B, `run.py --source real --sim-site pla` (or `resin`), runs one site on a simulated world fixed by the config seed; `Config.sim_sites` records it and locks it on resume, and calibration (`sim.calibrate --state`) skips the simulated site. Tier D, pure simulation, has a backup demo in `demo/tier-d/`.

## Challenge round and spawn

Both off by default (`Config.challenge=False`, `Config.dormant=()`); with both off, results match the code without them.

- **Challenge** (`agents/challenge.py`, spec 6.5 step 3). After proposing, each agent may flag one proposal another agent would win a slot with: "redundant with mine" if the piece is among its own winning proposals, or "already predictable from my evidence" if its own expected information gain on the piece is below `Config.challenge_eig` (0.05 nats). Flaggers go in order of credibility. A flagged piece moves to the end of its owner's list. In credit, the flagger gets ± (leave-one-piece-out held-out dLPD of the test piece − the round's average dLPD per piece). Every flag and its credit go on the receipt chain (`challenge`, `challenge_credit`) and into `Results.challenges`.
- **Spawn** (`arms/experiment.py` `_unmet_needs`, `_spawn`, spec 6.7). One dormant template exists: `position`, which proposes by information gain on `pos_gx`/`pos_gy`. After credit, each site correlates its standardized training residuals with squared distance from the plate center; the physics model has linear plate gradients only, so this checks for the simulator's unmodeled radial term. If |z| ≥ `Config.unmet_z` (2.0), the site logs an unmet need and broadcasts it in `Message.unmet_needs` (template, question and z only, validated by `network/protocol.py`). A site wakes the template once its own plus incoming entries reach `Config.spawn_threshold` (2), so a question raised at one site can wake the agent at the other. In 5 seeds, position woke at both sites in round 2 in 4 of 5.
- **Limits:** no orientation template (`Piece` has no orientation); challenge outcomes aren't broadcast; the position agent targets the modeled linear gradient, not the radial term that wakes it.

## Hypothesis agent (exploratory)

`python -m agents.hypothesis --checkpoint receipts/real/state.pkl [--dry-run]`, run between rounds. For each site it summarizes the networked model's residuals on the site's own data: standardized residuals binned by kind and 1 mm size, trend z against radial distance, row, column, 1/d and hole vs. pin, failed sizes, and the unmet-needs log. It asks a Nemotron endpoint for at most 3 candidate effects, each with up to 6 test pieces, validates the JSON reply, snaps the pieces onto the library grid, and appends the result to `{site}-hypotheses.jsonl` next to the checkpoint, a separate receipt chain from the run's. It doesn't enter the auction. The prompt holds aggregates only, no piece IDs or diameters (tested).

Endpoint: `PREBUILT_LLM_URL` (OpenAI-compatible; default `http://localhost:8000/v1`), `PREBUILT_LLM_MODEL` (default `nvidia/llama-3.1-nemotron-70b-instruct`), and `NVIDIA_API_KEY` if needed. `agents/serve_nemotron.sh` serves one with vLLM; `--ping` checks it end to end. It has not been run against a live model.

## Hardening of the real-printer path

An independent review of the real-printer path found these; all are fixed and tested:

- A crash mid-round broke both receipt chains on resume (stale pickled seq/head). Chains now continue from the file, and the run logs a `resume` entry. Test: crash in round 2, resume, chains verify and scores match an uninterrupted run exactly.
- Simulated printers replayed their noise after a resume. Printer RNGs are checkpointed.
- The caliper CSV crashed on blank rows, unknown slots or uppercase `OK`. Bad rows are skipped with a warning.
- Held-out caliper values shaped the training offset. Held-out pieces are no longer sampled or used for offsets.
- `veto <reason>` now skips the plate instead of still expecting it.
- A dropped plate and pieces the scan missed fed the printability agent's failure counts. They stay on the chain but are never used as data (`NOT_DATA`).
- Reprints, vetoes and dropped plates are on the chain (`printer_event`).
- An unreadable scan prompts a rescan instead of crashing.
- The prereg's failed-plate fraction and caliper settings reach the run, and resume locks them.

A crash during the seed plate (before the first checkpoint) re-logs the seed plate on a valid chain.

## Scanner stress test (synthetic)

400 dpi, full plate, 3 scans each (RMS / max error, µm). Source: `hpc/scanner_stress/`.

| defect | holes | pins |
|---|---|---|
| clean | 1.9 / 8.7 | 4.7 / 15 |
| lighting gradient 30% / 60% | 4.2 / 13, 5.6 / 21 | 13 / 39, 22 / 80 |
| pin shadow 0.3 mm | n/a | **51 / 65** (bias −50, spread 8) |
| 150 dust specks | 5.8 / 22 | 9.1 / 57 |
| blur 3 px | **15 / 76** | 14 / 34 |
| JPEG q80, 300 dpi, noise 0.05 | under 7 / 16 | under 15 / 36 |

A lighting gradient used to break fiducial detection on pin scans, so detection falls back to local thresholds. Shadows bias pins by a near-constant amount, so when `{plate}-caliper.csv` exists, `RealPrinter` subtracts the per-kind median scanner − caliper offset (`measure.manual.scanner_offsets`), with the caliper sample split evenly between pins and holes. Use about 10 caliper checks per plate, scan at 400 dpi or more, lossless (PNG) and in focus: blur is the one defect the offset doesn't remove. The scanner has been tested on synthetic scans only.

## Known limits

- **Priors vs. real printers.** The models don't need exact slicer or exposure settings; the seed plate learns them, and the priors are deliberately wide (`model/physics.py` docstring). Whether a real printer lies inside them can't be tested in simulation. `eval.prior_check` runs after the seed plate: in simulation it flags a printer outside the prior 8 of 8 times and never fires on a normal one (0 of 8). It catches a 1% PLA XY scale error (no such term in the model) only 1 of 8 times from 16 pieces, because the other terms absorb most of it.
- **`trust_init = 1.0` costs one round against a bad-faith site.** The honest site's networked error is 82 µm in round 1 (isolated 15) before trust drops, and only level with isolated by round 3. The consistency check and adaptive spread (opt-in, off in the registered config) remove most of that in simulation (`hpc/sweeps/relevance/README.md` sections 5 and 8).
- **No full real-printer run.** Everything in the sharing results is simulation; the real-printer evidence is a sanity check of error size on one Formlabs Form Studio 1.
