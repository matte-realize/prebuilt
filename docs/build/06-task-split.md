# Build: Task Split

**M** = Matthew: agents, the physical loop (plates, printers, scanner), verification.
**T** = teammate: HPC. Everything that runs on GPUs or at scale (Warp, Nebius H100s, sweeps).

This replaces the per-phase M/T assignments in [02-friday-night.md](02-friday-night.md) and [03-saturday.md](03-saturday.md). Plates and the scanner move from T to M, so that T owns every GPU path end to end.

## Ownership

| Area | Owner | Code | Status |
|---|---|---|---|
| Contracts, receipts, physics models, NumPy posterior | M | `contracts.py`, `receipts/`, `model/` | Done (Phase A) |
| Pre-registration values | M + T | `prereg/` | Kickoff, together |
| Piece library, plate generator, seed STLs | M | `plates/` | Done; slice-check on both printers still to do |
| Agents, auction, credibility | M | `agents/` | Done (challenge round, spawn not built) |
| Message schema and boundary enforcement | M | `network/` | Done |
| Three arms (isolated, networked, oracle) | M | `arms/` | Done; oracle definition open (see 07-status.md) |
| Scanner pipeline, caliper entry | M | `measure/` | First pass done on synthetic scans; paper target next |
| Privacy audit replay | M | `eval/audit.py` | Done |
| Hypothesis agent (Nemotron, async) | M | `agents/hypothesis.py` | Sat night, exploratory |
| Warp multi-site simulator (`Printer`) | T | `sim/` | Phase B |
| Domain randomization, unmodeled effects | T | `sim/` | Phase B |
| Warp/GPU port of the posterior | T | `model/posterior_warp.py` | Phase B–C |
| Batched experiment runner (many sites × seeds per launch) | T | `sim/batch.py` | Phase C |
| Nebius setup, job scripts, result storage | T | `hpc/` | Fri night |
| Many-seed runs; tune and freeze η, floor, slot split | T (M signs off) | `hpc/` | Phase C |
| Sim calibration to seed data; predicted range (Phase D) | T | `sim/calibrate.py` | Sat ~11:30 |
| Robustness, scaling, ablation sweeps | T | `hpc/sweeps/` | Sat afternoon and night |
| Held-out scoring, metrics | M | `eval/metrics.py` | Done (fit-class accuracy waits on prereg thresholds) |
| Figures | T (sweeps), M (real rounds) | `eval/figures/` | Sat night |

## Handoff contracts

These are the only places the two tracks touch. Agree on them at kickoff and don't change them alone.

1. **Simulator → everything.** `sim.SimPrinter` implements `contracts.Printer`. Hidden truth uses the parameter names and tags in `model/physics.py`, plus the unmodeled effects, which agents never see.
2. **GPU posterior → agents.** `posterior_warp` exposes the same methods as `model/posterior.py` (`update`, `predict`, `predict_interval`, `log_predictive`, `summary`, `set_prior_from_summary`) and passes `tests/test_posterior.py` unchanged. The NumPy version stays as the reference.
3. **Arms → sweeps.** M provides `arms.run_experiment(printers, config, seed) -> results`, a pure function with no global state. T runs it at scale. Batching over sites and seeds is T's job, done inside the simulator and posterior, not by changing the arms.
4. **Frozen config.** T proposes η, credibility floor, slot split, and proposal discount from Phase C sweeps. M signs off, then the config is committed with its hash.

## Timeline

| When | M | T |
|---|---|---|
| Fri 9:00–9:30 PM | Kickoff together: prereg values, handoff contracts, printer logistics | Same |
| Fri 9:30 PM – 1 AM | Piece library, plate generator, seed STLs (slice-check on both printers) | Nebius environment; Warp simulator implementing `Printer` |
| Fri 1 – 4 AM | Agents, auction, credibility, message boundary, three arms | Domain randomization; batched sim; start the Warp posterior port |
| Fri 4 – 8 AM | Sleep ~4–7:30, then scanner first pass on a paper target | Many-seed runs; propose frozen config; draft predicted range. Sleep after handing off at 7:30 |
| Sat 8:30 – 11:00 | Test pieces, seed plates on both printers, scan | Sim sweeps running on Nebius (sleeping or monitoring) |
| Sat ~11:30 | Ingest seed data | Phase D: calibrate the sim to seed data, recompute and commit the predicted range |
| Sat 12 – 10 PM | Rounds 1–3: auctions, printing, scanning, updates | Robustness, scaling, ablation sweeps. Covers scanning during M's breaks |
| Sat night | Score real rounds, privacy audit, hypothesis agent | Recalibrate the sim with all real data; sweep figures |
| Sun to 2:30 PM | Real-round figures, slides | Sweep figures, receipt replay demo, backup video |

## Measurement duty

M runs printers and scanning by default. T takes over scanning for one round on Saturday afternoon (pick which at kickoff) so M can work on the auction and score the earlier round.

## If someone is behind

- **M behind on plates at midnight:** T pauses the sim and finishes the seed STLs. Seed plates printing at 9 AM beats everything else.
- **M behind on agents at 4 AM:** T runs Phase C with only the isolated and oracle arms, so the frozen config is ready when the networked arm lands.
- **Warp port not done by Sat noon:** run the sweeps with the NumPy posterior on Nebius CPUs with fewer seeds, and say so in the results.
- **Nebius unavailable:** run the sweeps locally on the DGX Spark at smaller scale (fewer sites and seeds).
