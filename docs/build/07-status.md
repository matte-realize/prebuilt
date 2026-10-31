# Build: Status and Phase C Findings

As of Fri Oct 30, late evening. M's Phase A and B tasks are built and tested (`.venv/bin/python -m pytest -q`, 34 tests).

## What runs

- `python -m plates.seed` writes seed plates (JSON + watertight STL) for both sites and `prereg/heldout.json`.
- `python run.py --source sim --seeds 20` runs the full three-arm, two-site experiment on the NumPy reference simulator (`sim/reference.py`) and runs the privacy audit for every seed. About 3 s per seed at 1000 particles.
- `python run.py --source real` drives the real printers. It writes plate files, asks for human approval, waits for `scans/<site>/<plate>-holes.png` and `-pins.png`, measures them, and checkpoints after every round (`receipts/real/state.pkl`). Rerun the same command to resume.
- `python -m measure.target plates/out/resin/resin-seed.json target.pdf` writes a 1:1 paper target for checking the scanner before any plate prints.
- `python -m eval.audit receipts/real/resin.jsonl receipts/real/pla.jsonl` replays the receipt chains for the privacy check.

## Phase C findings (for T's sweeps; decide before freezing config)

1. **The arms barely separate under the placeholder priors.** In 20 seeds, oracle gap closed on MAE has median 0.32 at round 3, but the IQR is [-0.17, 0.97]. Isolated and oracle are close because the 56-piece seed plate plus 18 pieces per round already pins down the 3 shared parameters at each site alone. Levers to sweep: a smaller seed plate, fewer pieces per round, learning curves vs. pieces rather than per round, and more process-agnostic structure (e.g. size dependence per feature kind).
2. **The oracle is not an upper bound when sites differ.** The joint posterior assumes the shared parameters are identical at every site. The simulator perturbs them per site (`shared_jitter`), and real machines will differ too, so the oracle can do worse than isolated. Options: give the oracle the same between-site spread as the network (a hierarchical oracle), or set the simulator's jitter to 0 and state that assumption. **This decides what "upper bound" means in the headline claim.**
3. **Between-site spread is now a setting.** `Config.between_site_sd` (default 0.25 of prior std) widens every incoming message. Without it, near-noise-free sites with tight but different beliefs made the networked arm much worse (MAE 0.10 vs 0.001 mm) until trust collapsed. This should be pre-registered, not tuned on real data.
4. **η = 20 is too high.** Honest senders lose trust from noise in the leave-one-out difference: in one bad-site run the honest sender dropped to trust 0.25 while the bad one went to 0. Sweep η, `trust_init` and `cred_floor` together, scoring both "bad site loses trust" and "honest site keeps it".
5. **Held-out LPD can swing by tens of nats** when the model is wrong (seen with near-noise-free scans). Credibility math is now overflow-safe, but large swings mean one round can dominate credit. Consider clipping per-piece LPD, or using mean rank instead.

## Not built yet (M)

- Challenge round, spawn/retire of dormant agents (retire on the credibility floor is built), hypothesis agent.
- Fit-class accuracy: waits on the prereg thresholds.
- Scanner on real scans: synthetic error is under 25 µm at 400 dpi. Real lighting, shadows and pin-top edges will be worse; check with the paper target, then a test print.
- Slice-check the seed STLs in PreForm and the PLA slicer.
