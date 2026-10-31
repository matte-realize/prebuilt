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
4. **The oracle is now hierarchical** (`Config.oracle_hierarchical`, default on). It pools all raw data under the same between-site spread the network assumes, so it's meant to be an upper bound under matching assumptions. But it still scores slightly worse than networked (T's sweep: 11.84 vs 10.87 µm at 16 seed pieces, 6 slots, round 3). **Particle count isn't the cause:** `Config.oracle_particles` / `--oracle-particles` now exist, and at 16 pieces, 6 slots, 12 seeds, round 3, oracle minus networked was +0.6 ± 1.1 µm at 1000 particles, +1.1 ± 1.1 at 4000, +1.3 ± 0.9 at 8000. Four times the MH steps (+1.9 ± 1.0) and the flat, non-hierarchical oracle (+1.3 ± 1.0) don't fix it either. Still unchecked: piece selection in the oracle arm (its agents score pieces against the pooled posterior) and whether the networked arm gets an advantage from per-arm print noise. Until that's resolved, report isolated minus networked in µm, not oracle-gap-closed.
5. **Between-site spread is a setting.** `Config.between_site_sd` (default 0.25 of prior std) widens every incoming message. Without it, near-noise-free sites with tight but different beliefs made the networked arm much worse (MAE 0.10 vs 0.001 mm) until trust collapsed. Pre-register it; don't tune it on real data.
6. **η = 20 is too high.** Honest senders lose trust from noise in the leave-one-out difference: in one bad-site run the honest sender dropped to 0.25. Sweep η, `trust_init` and `cred_floor` together, scoring both "bad site loses trust" and "honest site keeps it".
7. **Held-out LPD can swing by tens of nats** when the model is wrong. Credibility math is overflow-safe now, but one round can dominate credit. Consider clipping per-piece LPD.

## Challenge round and spawn (built Oct 31)

Both are on by default (`Config.challenge`, `Config.dormant`), since spec 8.1 defines the networked arm as the full Section 6 system. `run.py --no-challenge --no-spawn` turns them off; with both off, results match the earlier code. They change results, so T's Phase C numbers predate them.

- **Challenge** (`agents/challenge.py`, spec 6.5 step 3). After proposing, each agent may flag one proposal another agent would win a slot with. It flags "redundant with mine" if the same piece is among its own winning proposals, or "already predictable from my evidence" if its own posterior's expected information gain on the piece is below `Config.challenge_eig` (0.05 nats, a placeholder to freeze with η). Flaggers go in order of credibility. A flagged piece moves to the end of its owner's list, so it prints only if the owner has slots to spare. In credit, the flagger gets ± (leave-one-piece-out held-out dLPD of the test piece − the round's average dLPD per piece), added to its own dLPD. The test piece is the flagged piece if it printed (the flagger gains if it's below average) or else the piece that replaced it (the flagger gains if that one is above average). Every flag and its credit goes on the receipt chain (`challenge`, `challenge_credit`) and into `Results.challenges`.
- **Spawn** (`arms/experiment.py` `_unmet_needs`, `_spawn`, spec 6.7). One dormant template exists: `position`, which proposes by information gain on `pos_gx`/`pos_gy`, with candidates scored at a plate corner. After credit, each site correlates its networked posterior's standardized training residuals with squared distance from the plate center. The physics model has linear plate gradients only, so this checks for the sim's unmodeled radial term. If |z| ≥ `Config.unmet_z` (2.0), the site logs an unmet need and broadcasts it in the new `Message.unmet_needs` field: template, question, and z only, validated by `network/protocol.py`. A site wakes the template with uniform credibility (1/(n+1)) once its own plus incoming entries reach `Config.spawn_threshold` (2), so a question raised at one site can wake the agent at the other. Retired agents don't respawn. In 5 seeds at 16 seed pieces and 6 slots, position woke at both sites in round 2 in 4 of 5 seeds.
- **Open:** no orientation template (`Piece` has no orientation). Challenge outcomes aren't broadcast (the spec allows it but doesn't require it). The position agent targets the modeled linear gradient, not the radial term that wakes it.

## Not built yet (M)

- Hypothesis agent.
- Fit-class accuracy: waits on the prereg thresholds.
- Scanner on real scans: synthetic error is under 25 µm at 400 dpi. Real lighting, shadows and pin-top edges will be worse; check with the paper target, then a test print.
- Slice-check the seed STLs in PreForm and the PLA slicer.
