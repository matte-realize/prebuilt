# Phase C sweeps

NumPy reference simulator (`sim/reference.py`) through `arms.run_experiment`, two sites (resin, pla), 2000 particles, current default config (eta 20, trust_init 1.0, cred_floor 0.05, discount 0.2, between_site_sd 0.25) unless stated.

    .venv/bin/python hpc/sweeps/phase_c/seed_plate.py --seeds 40 --rounds 4   # ~10 min on 15 workers
    .venv/bin/python hpc/sweeps/phase_c/analyze.py seed_plate                  # writes results/seed_plate.md

Errors are `mae_truth` in µm: model error against the noise-free held-out diameters, averaged over both sites within a seed. ± is the standard error over seeds. Full table, all rounds: [`results/seed_plate.md`](results/seed_plate.md).

## 1. Seed-plate decision

**Recommendation: shrink the seed plate to 16 pieces.** Keeping 56 and relying on learning curves doesn't work: with 56 seed pieces and 18 slots, isolated and networked never separate (difference 0.1-0.25 µm, inside 1 SE in every round). Each site's seed plate has already taught it the shared parameters before round 1, so there is no curve to show.

Isolated minus networked, µm (SE), 40 seeds:

| seed pieces | slots | round 1 | round 2 | round 3 | round 4 | round 3, % of isolated |
|---|---|---|---|---|---|---|
| 4 | 6 | 3.32 (1.30) | 3.59 (1.40) | 3.95 (1.06) | 3.85 (0.85) | 22% |
| 4 | 18 | 1.38 (1.03) | 1.99 (0.61) | 1.35 (0.41) | 0.54 (0.35) | 14% |
| 8 | 6 | 3.07 (0.86) | 2.42 (0.71) | 1.78 (0.69) | 2.13 (0.62) | 13% |
| 8 | 18 | 1.29 (0.85) | 0.88 (0.67) | 0.49 (0.46) | 1.00 (0.39) | 5% |
| **16** | **6** | **2.83 (0.44)** | **2.30 (0.54)** | **2.06 (0.51)** | **1.74 (0.64)** | **16%** |
| 16 | 18 | 2.36 (0.41) | 1.68 (0.41) | 1.17 (0.45) | 1.06 (0.47) | 13% |
| 32 | 6 | 1.26 (0.32) | 0.98 (0.40) | 0.80 (0.33) | 1.04 (0.33) | 8% |
| 32 | 18 | 1.12 (0.53) | 1.36 (0.58) | 0.81 (0.57) | 0.58 (0.52) | 10% |
| 56 | 6 | 0.65 (0.27) | 0.96 (0.26) | 0.82 (0.23) | 0.52 (0.22) | 10% |
| 56 | 18 | 0.13 (0.38) | 0.23 (0.32) | 0.11 (0.29) | 0.25 (0.30) | 2% |

16 pieces gives the most consistent effect: 4-6 SE in rounds 1-3 with 6 slots, and 2.6-5.8 SE with 18 slots. 4 pieces gives a bigger effect but noisier, and absolute error is worst there (18 µm at round 3). 8 pieces with 18 slots is weak by round 3.

**Slots: 6 (recommended) or 18, close call.**
- 6 slots per arm keeps the effect larger for longer: still 4 SE at round 3, 16% of isolated error. The plate prints 3 × 6 + 8 held-out = 26 pieces, so most of each plate is unused.
- 18 slots per arm is the current plate layout, fills the plate, and gives better absolute models (9 µm vs 13 µm at round 3). The effect shrinks to 2.6 SE by round 3.

The real-printer claim is sim-to-real (07-status finding 3), so what matters is a clean effect in simulation and a gap-closed that doesn't swing. 6 slots is better on both.

## Oracle-gap-closed is not usable yet

The oracle is meant to be the upper bound. Here it is usually *worse* than networked: at 16 pieces and 6 slots it scores 11.84 vs 10.87 µm at round 3. So isolated − oracle is smaller than isolated − networked, and the pooled gap-closed comes out above 1 (1.29-2.19). When the denominator gets near zero it blows up; at 32 pieces and 18 slots, round 3 it is −7.9.

Per-seed median gap-closed for 16 pieces, 6 slots is 0.79-0.88 in rounds 1-3. But the IQR is about [−0.2, 1.8], too wide to commit as a predicted range.

The main cause was Monte Carlo mixing, not particle count: the 18-dim oracle got the same 3 MH steps per resample as a 9-dim site. `Config.oracle_mh_steps` now scales them with dimension (07-status finding 4). A 0.3-0.4 µm residual from piece choice remains, so report iso − net in µm alongside gap-closed. Don't draft the range from these numbers; they predate the fix and `same_agents`.

## Confidence

- High: 56 seed pieces with 18 slots shows no effect, and a smaller seed plate does. Every thinned plate separates; the full plate never does.
- Moderate: 16 over 8. The SEs overlap at round 3, but 16 is steadier across rounds.
- Low: every gap-closed number above, until the oracle is fixed.

Privacy audit passed in 400/400 runs. Wall time per run: 7 s (4 pieces, 6 slots) to 52 s (56 pieces, 18 slots).

## Not run yet

`tuning.py` (stages `trust`, `knobs`, `particles`) and `hpc/nebius/run_phase_c.sh` are smoke-tested only (2 seeds, 1 round). The tuning sweep, frozen config and predicted range (deliverables 2-3) are still to do; the range waits on the oracle fix above.
