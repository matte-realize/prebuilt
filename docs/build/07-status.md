# Build: Status and Phase C Findings

As of Sat Oct 31. T's Phase C sweep results: `hpc/sweeps/phase_c/README.md` (recommends 16 seed pieces, 6 slots per arm). M's Phase A and B tasks are built and tested (`.venv/bin/python -m pytest -q`, 34 tests).

## What runs

- `python -m plates.seed` writes seed plates (JSON + watertight STL) for both sites and `prereg/heldout.json`.
- `python run.py --source sim --seeds 20` runs the full three-arm, two-site experiment on the NumPy reference simulator (`sim/reference.py`) and runs the privacy audit for every seed. About 3 s per seed at 1000 particles.
- `python run.py --source real` drives the real printers. It writes plate files, asks for human approval, waits for `scans/<site>/<plate>-holes.png` and `-pins.png`, measures them, and checkpoints after every round (`receipts/real/state.pkl`). Rerun the same command to resume.
- `python -m measure.target plates/out/resin/resin-seed.json target.pdf` writes a 1:1 paper target for checking the scanner before any plate prints.
- `python -m eval.audit receipts/real/resin.jsonl receipts/real/pla.jsonl` replays the receipt chains for the privacy check.

## Phase C findings (for T's sweeps; decide before freezing config)

Run sweeps with `run.py --source sim --seeds 20 --out results.json`. In simulation, rows include `mae_truth`: error against the noise-free diameters, recorded for evaluation only and never shown to agents.

1. **With the full seed plate, the arms can't separate.** Over 20 seeds × 2 sites, isolated, networked and oracle all sit at MAE ≈ 0.031 mm, within ±0.0005 mm of each other. Even against the noise-free truth they're within ±0.0006 mm (≈ 0.008 mm). The 56-piece seed plate already teaches each site everything the 3 shared parameters can offer.
2. **With less data per site, sharing helps.** With 8 seed pieces and 6 slots per arm (`--seed-pieces 8 --slots 6`), error against the noise-free truth at round 2 is isolated 0.0163, networked 0.0133, oracle 0.0140 mm. That's an 18% reduction for networked, about 3 standard errors. **Decided: shrink.** Following T's sweep, the seed plate now has 16 calibration pieces (`plates.seed.SEED_PIECES`; 8 pins + 8 holes spread over 1.5–7.0 mm, no duplicates) plus the 8 held-out, and `Config` defaults to 6 slots per arm. The STLs and paper target in `plates/out/` are regenerated. `seed_pieces=None` still gives the full 56 for sweeps.
3. **Real held-out data probably can't resolve the effect.** Measured MAE is dominated by measurement noise (σ ≈ 0.03–0.04 mm). A 0.003 mm difference in model error doesn't show up in measured MAE, even with 40 held-out pieces per site (measured differences are +0.0005 ± 0.0008 mm). So the real-printer claim should be sim-to-real (claim 2), not detecting H1 on real data alone. Say so in the prereg.
4. **Why the oracle lost to networked, and the fix.** The walkthrough gives isolated and oracle one max-information agent each, but networked gets the five-agent auction. So isolated minus networked measured the agents' piece choices as well as sharing. Evidence, 20 seeds, 16 seed pieces, 6 slots, 1000 particles, round 2 (µm):
   - Walkthrough arms: iso − net 1.75 ± 0.92, oracle − net +2.19 ± 0.59 (oracle worse).
   - Messages cut (`share_messages=False`): iso − net is still 1.33 ± 0.70. That part is the auction, not the network.
   - **`Config.same_agents=True` (now the default):** isolated and oracle also choose by the agent auction, at uniform credibility. iso − net 1.96 ± 0.74, oracle − net −0.26 ± 0.74. Networked now lands between isolated and oracle, and the difference measures sharing only.

   Not the cause: oracle particle count (`Config.oracle_particles`: +0.6, +1.1, +1.3 µm oracle − net at 1000, 4000, 8000 particles), four times the MH steps, or the flat oracle. The oracle stays hierarchical (`Config.oracle_hierarchical`). **This deviates from the walkthrough's arm definitions; say so in the prereg.** T: rerun the seed-plate and tuning sweeps with the new default before drafting the predicted range. 20 seeds are too noisy to commit numbers from.
5. **Between-site spread is a setting.** `Config.between_site_sd` (default 0.25 of prior std) widens every incoming message. Without it, near-noise-free sites with tight but different beliefs made the networked arm much worse (MAE 0.10 vs 0.001 mm) until trust collapsed. Pre-register it; don't tune it on real data.
6. **η = 20 is too high.** Honest senders lose trust from noise in the leave-one-out difference: in one bad-site run the honest sender dropped to 0.25. Sweep η, `trust_init` and `cred_floor` together, scoring both "bad site loses trust" and "honest site keeps it".
7. **Held-out LPD can swing by tens of nats** when the model is wrong. Credibility math is overflow-safe now, but one round can dominate credit. Consider clipping per-piece LPD.

## Replies to T (08-warp-posterior.md)

- **`model/posterior.py` refactor (d5df0dd):** reviewed and approved. It's behavior-preserving, and it's already on main.
- **NumPy `predict` at 17 ms per piece:** doesn't reproduce. On your benchmark's workload (60 training pieces, 200 held-out) on an idle M-series Mac it's 0.23 ms per piece at 20k particles and 0.04 ms at 2k. The 17 ms was most likely contention from the other job on the shared machine (BLAS threads). Rerun the NumPy column with `OMP_NUM_THREADS=1` on an idle node.

## Not built yet (M)

- Challenge round, spawn/retire of dormant agents (retire on the credibility floor is built), hypothesis agent.
- Fit-class accuracy: waits on the prereg thresholds.
- Scanner on real scans: synthetic error is under 25 µm at 400 dpi. Real lighting, shadows and pin-top edges will be worse; check with the paper target, then a test print.
- Slice-check the seed STLs in PreForm and the PLA slicer.
