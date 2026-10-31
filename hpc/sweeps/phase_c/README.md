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

## 2. Tuning sweep (16 seed pieces, 6 slots)

Run on the GCP VM from main at ce27b43 (challenge and spawn off, `same_agents`, scaled `oracle_mh_steps`), 40 seeds, 3 rounds, seeds 2000-2039. Raw rows are committed gzipped; `analyze.py` reads them directly.

    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage trust --seed-pieces 16 --slots 6 --seeds 40 --workers 31

### Trust: eta 5, trust_init 1.0, cred_floor 0.05

Full table: [`results/tuning_trust_seed16_slots6.md`](results/tuning_trust_seed16_slots6.md). Last round, 40 seeds per condition:

| eta, trust_init | bad sender's trust | honest trust | honest links < 0.5 | net/iso under attack (median) | iso − net honest, µm (SE) |
|---|---|---|---|---|---|
| 1, 1.0 | 0.25 | 0.97 | 0% | 1.94 | 1.81 (0.50) |
| 2, 1.0 | 0.12 | 0.95 | 1% | 1.15 | 1.92 (0.50) |
| **5, 1.0** | **0.03** | **0.89** | **6%** | **0.97** | **2.22 (0.47)** |
| 5, 0.75 | 0.04 | 0.77 | 10% | 0.92 | 2.03 (0.50) |
| 10, 1.0 | 0.02 | 0.83 | 11% | 0.94 | 1.81 (0.51) |
| 20, 1.0 | 0.005 | 0.76 | 26% | 0.94 | 1.91 (0.61) |

- **eta 5** is the smallest learning rate that stops a bad sender from hurting the honest site (networked/isolated under attack below 1). At eta 1-2 the bad site still makes the honest site's model 15-94% worse. Above 5, trust between honest sites starts collapsing: at eta 20 a quarter of honest links end below 0.5.
- **trust_init 1.0** over 0.75: the honest links stay higher (0.89 vs 0.77) with the same protection. 0.5 starts honest links at the threshold, so 40% of them end below it.
- **cred_floor 0.05**: makes no difference at eta 5 (0.02 and 0.05 give identical rows). 0.1 starts retiring agents (0.1 per run). 0.05 is the middle of the range that doesn't bind.
- iso − net differs across configs by less than 1 SE, so the networking benefit doesn't decide the choice; protection against a bad site does.

The same sweep with challenge and spawn on (main at 8777dae, [`results/tuning_trust_seed16_slots6_challenge_on.md`](results/tuning_trust_seed16_slots6_challenge_on.md)) picks the same values: bad trust 0.03, honest 0.92, net/iso under attack 0.97. So the choice holds for the secondary analysis as well.

Provisional config for downstream work: [`hpc/phase_d/provisional_config.json`](../../phase_d/provisional_config.json). Nothing reads it automatically: `sim.calibrate` and `run.py` take the config from `prereg/prereg.yaml`. To use it before the prereg is filled in, copy `prereg.yaml`, put these values in its `config` section and pass the copy with `--prereg`. `n_particles` and `oracle_particles` in it are still the defaults until their stages finish; the knobs stage kept `discount` 0.2 and `between_site_sd` 0.25.

### Knobs: discount 0.2, between_site_sd 0.25 (the defaults)

Full table: [`results/tuning_knobs_seed16_slots6.md`](results/tuning_knobs_seed16_slots6.md). Same 40 seeds, at eta 5, trust_init 1.0, cred_floor 0.05:

| discount | between_site_sd | bad sender's trust | honest trust | net/iso under attack (median) | iso − net honest, µm (SE) |
|---|---|---|---|---|---|
| 0.0 | 0.25 | 0.04 | 0.91 | 0.99 | 1.11 (0.47) |
| 0.1 | 0.25 | 0.03 | 0.90 | 0.98 | 1.83 (0.48) |
| **0.2** | **0.25** | **0.03** | **0.89** | **0.97** | **2.22 (0.47)** |
| 0.4 | 0.25 | 0.03 | 0.90 | 1.03 | 2.20 (0.53) |
| 0.2 | 0.1 | 0.007 | 0.87 | 0.94 | 1.97 (0.45) |
| 0.2 | 0.5 | 0.19 | 0.93 | 0.98 | 2.35 (0.51) |
| 0.2 | 1.0 | 0.73 | 0.93 | 1.02 | 1.16 (0.53) |

- **discount 0** costs about half the networking benefit (1.1 vs 2.2 µm); 0.1-0.4 are within 1 SE of each other. 0.2 is the middle of that plateau.
- **between_site_sd** trades detection against benefit. At 1.0 the bad site keeps trust 0.73: incoming beliefs are widened so much that disagreement no longer shows, and the benefit halves. 0.5 has the largest benefit (2.35 µm, within 1 SE of 0.25) but the bad sender keeps trust 0.19. 0.25 detects it (0.03) at no measurable cost in benefit. 0.1 detects best but trims the benefit and honest trust slightly.

### Particles: n_particles 4000, mh_steps 6 (changed from 2000, 3)

Full table: [`results/tuning_particles_seed16_slots6.md`](results/tuning_particles_seed16_slots6.md). Honest runs, same 40 seeds, round 3. Change in iso − net is paired by seed against 2000 particles, 3 MH steps:

| n_particles, mh_steps | iso − net, µm (SE) | change vs 2000, 3 (SE) | isolated change | networked change | s per run |
|---|---|---|---|---|---|
| 1000, 3 | 2.51 (0.59) | +0.29 (0.50) | +0.44 | +0.15 | 6 |
| **2000, 3 (old)** | **2.22 (0.47)** | - | - | - | 10 |
| 4000, 3 | 2.42 (0.46) | +0.20 (0.34) | +0.15 | −0.05 | 18 |
| 8000, 3 | 1.22 (0.41) | −1.00 (0.36) | −0.56 | +0.44 | 36 |
| 1000, 6 | 1.41 (0.51) | −0.81 (0.47) | −0.37 | +0.44 | 8 |
| 2000, 6 | 1.69 (0.43) | −0.54 (0.42) | −0.29 | +0.25 | 14 |
| **4000, 6** | **1.44 (0.43)** | **−0.78 (0.40)** | **−0.57** | **+0.22** | **26** |
| 8000, 6 | 1.65 (0.58) | −0.57 (0.55) | −0.26 | +0.30 | 50 |

Every setting with better mixing (6 MH steps, or 8000 particles) shrinks iso − net by 0.5-1.0 µm, and always the same way: isolated gets better, networked slightly worse. So about a third of the 2.2 µm benefit at the old setting is sampler error in the isolated fit that incoming messages happen to correct, not information from the other site. With better mixing the benefit settles at 1.2-1.7 µm, still about 3 SE above zero.

Recommendation: **n_particles 4000, mh_steps 6**. It sits on that plateau with margin (2000, 6 is there too, but only just). 26 s per simulated run is cheap, and on real rounds the fit time is negligible next to printing. `mh_steps` is not in the prereg's `config` section yet; `prereg.check.config_from` accepts any `Config` field, so adding `mh_steps: 6` there is enough. `oracle_mh_steps` scales with it (12 steps for the oracle).

The trust and knobs stages ran at 2000, 3. A check of those choices at 4000, 6 is listed below.

### Oracle: oracle_particles = n_particles; no count makes the oracle an upper bound

Full table: [`results/tuning_oracle_seed16_slots6.md`](results/tuning_oracle_seed16_slots6.md). 100 seeds (2000-2099), honest runs, at 4000 particles, 6 MH steps (oracle 12). The target was the smallest `oracle_particles` at which the oracle beats networked in at least 90% of seeds. None does:

| oracle_particles | oracle < networked, rounds 1 / 2 / 3 | oracle mae_truth round 3, µm |
|---|---|---|
| 2000 | 47% / 52% / 52% | 11.15 ± 0.37 |
| 4000 | 48% / 52% / 50% | 11.30 ± 0.37 |
| 8000 | 51% / 57% / 53% | 11.17 ± 0.39 |
| 16000 | 51% / 53% / 52% | 11.23 ± 0.38 |
| 32000 | 50% / 51% / 50% | 11.35 ± 0.38 |

Why: with two sites, networked already extracts what the oracle does. A diagnostic run with `Config.oracle_data="networked"` (the oracle pools exactly the networked arm's data, so only inference differs; [`results/diag_oracle_data_networked.jsonl.gz`](results/diag_oracle_data_networked.jsonl.gz), 40 seeds) gives oracle − networked of −0.04, −0.01, +0.05 µm (SE 0.06-0.07) in rounds 1-3, oracle winning in 60%, 48%, 40% of seeds. Two estimators that agree to within 0.05 µm split the seeds about evenly, so a 90% rule can't be met by any particle count. In the real design the arms also print different pieces, which adds noise to each seed's comparison.

Consequences: per-seed oracle gap closed sits near 1 with a wide spread (IQR roughly [0, 1.5]); it is not bounded in [0, 1] and shouldn't be committed. iso − net (now the registered metric) is unaffected. Recommend `oracle_particles: 4000` (= n_particles; extra particles change nothing).

### Trust check at 4000 particles, 6 MH steps

[`results/tuning_trustcheck_p4000_mh6.md`](results/tuning_trustcheck_p4000_mh6.md), 40 seeds, trust_init 1.0, cred_floor 0.05. eta 5 still the best trade:

| eta | bad sender's trust | honest trust | honest links < 0.5 | net/iso under attack (median) |
|---|---|---|---|---|
| 2 | 0.14 | 0.95 | 1% | 1.27 |
| **5** | **0.05** | **0.90** | **5%** | **1.03** |
| 10 | 0.03 | 0.84 | 11% | 1.00 |

### Trust and knobs rerun at 4000 particles, 6 MH steps: no change

Full grids at the prereg sampler, same seeds as the 2000/3 runs so differences are paired by seed: trust, 30 seeds (2000-2029), [`results/tuning_trust_seed16_slots6_p4000_mh6.md`](results/tuning_trust_seed16_slots6_p4000_mh6.md); knobs, 40 seeds, at eta 5, trust_init 1.0, cred_floor 0.05, [`results/tuning_knobs_seed16_slots6_p4000_mh6.md`](results/tuning_knobs_seed16_slots6_p4000_mh6.md). `tuning.py` now tags these sweep names with `_p<particles>_mh<steps>`.

    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage trust --seed-pieces 16 --slots 6 --particles 4000 --mh-steps 6 --seeds 30 --workers 31
    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage knobs --seed-pieces 16 --slots 6 --particles 4000 --mh-steps 6 --eta 5 --trust-init 1.0 --cred-floor 0.05 --seeds 40 --workers 31

Paired difference against the prereg config, last round (SE):

| config | bad sender's trust | honest trust | honest links < 0.5 | net/iso under attack (mean) | iso − net, µm |
|---|---|---|---|---|---|
| **eta 5, ti 1.0, floor 0.05** | **0.059** | **0.886** | **7%** | **1.19** | **1.19 (0.46)** |
| eta 10 | −0.021 (0.005) | −0.065 (0.011) | +7% | −0.06 (0.03) | −0.10 (0.14) |
| eta 2 | +0.086 (0.007) | +0.053 (0.011) | −5% | +0.43 (0.11) | −0.17 (0.12) |
| trust_init 0.75 | +0.010 (0.011) | −0.111 (0.013) | +1% | +0.02 (0.05) | +0.10 (0.14) |
| cred_floor 0.02 or 0.1 | 0 | 0 | 0 | 0 | 0 |
| **discount 0.2** (knobs, 40 seeds) | **0.052** | **0.903** | **5%** | **1.16** | **1.44 (0.43)** |
| discount 0.1 | 0 | −0.006 (0.002) | +1% | −0.04 (0.02) | +0.28 (0.16) |
| discount 0.4 | 0 | 0 | 0 | −0.01 (0.02) | −0.17 (0.26) |
| discount 0.0 | 0 | −0.016 (0.012) | +1% | −0.12 (0.07) | −0.14 (0.49) |

- **eta 5** stays. eta 10 detects the bad sender slightly better but costs honest trust (6 SE) and doubles the honest links under 0.5; the networking benefit doesn't move. eta 2 lets the bad site make the honest site's networked model 61% worse than its isolated one (mean net/iso 1.61, against 1.19 at eta 5).
- **trust_init 1.0** stays: 0.75 lowers honest trust by 0.11 with no gain in protection. **cred_floor** doesn't bind at eta 5 (identical rows), so 0.05 stays.
- **discount 0.2** stays. 0.1 is the closest rival, +0.28 µm (1.7 SE), inside the 2 SE bar. At 2000/3, discount 0 halved the benefit; at 4000/6 discount 0 and 0.4 are within 1 SE of 0.2 and 0.1 is at 1.7 SE, so discount barely matters now.
- Under attack the honest site's median networked/isolated is 1.03-1.05 at eta 5, against 0.97 at 2000/3. Every config with eta ≥ 5 sits at 1.0-1.08, so this is the sampler, not the eta choice: mild, not a failure.
- iso − net at the prereg config, paired against the same seeds at 2000/3: −1.00 µm (0.48) on the trust seeds, −0.78 (0.40) on the knobs seeds. The same shrinkage the particles stage found.

## 3. Proposed config (for review; prereg.yaml not edited)

Values for the `config` section of `prereg/prereg.yaml`. Main (1dbf284) already holds eta, cred_floor, trust_init and discount as below; the changes are `n_particles`, `oracle_particles` and a new `mh_steps` line.

    n_particles: 4000            # was 2000; 6 MH steps / 4000 particles removes sampler error that inflated iso - net
    mh_steps: 6                  # new line; Config default is 3. oracle_mh_steps scales with it (12)
    oracle_particles: 4000       # = n_particles; 2000-32000 all tie with networked (oracle stage)
    eta: 5
    cred_floor: 0.05
    trust_init: 1.0
    discount: 0.2
    between_site_sd: 0.25        # unchanged; knobs stage

## 4. Draft predicted range (simulation only, before calibration)

Per seed, isolated − networked, µm, both sites averaged, at the proposed config. 100 seeds from `tuning_oracle_seed16_slots6` (oracle_particles 4000 rows):

| round | measured MAE (registered): median [IQR] | share > 0 | noise-free MAE: median [IQR] | share > 0 | oracle gap closed, noise-free: median [IQR] |
|---|---|---|---|---|---|
| 1 | 0.61 [−1.26, 2.04] | 56% | 1.62 [−0.25, 3.40] | 72% | 0.83 [−0.01, 1.85] |
| 2 | 0.62 [−0.64, 2.31] | 63% | 1.62 [−0.30, 4.16] | 72% | 0.62 [−0.39, 1.55] |
| 3 | 0.60 [−0.39, 1.97] | 61% | 1.75 [−0.44, 3.26] | 69% | 0.68 [−0.03, 1.52] |

The mean effect on noise-free error is clear (1.5-2.0 µm, SE 0.3). But on measured error over 8 held-out pieces per site, measurement noise is about as large as the effect: in about 40% of simulated worlds a single real run would show networked no better than isolated. The real experiment is one seed. This range replaces nothing until `sim.calibrate` reruns it on the real seed plates.

## Compared with earlier numbers

- The laptop preview (trust stage before `oracle_particles` and `same_agents`) was lost with the `prebuilt-phase-d` worktree. The closest comparison is section 1 (`same_agents` off, old oracle sampler): there the oracle trailed networked by about 1 µm at round 3 (11.84 vs 10.87). Now it ties (11.30 vs 11.52). That change is mostly the oracle MH fix plus `same_agents` together; these runs can't separate the two, and the `oracle_data="networked"` check says the remaining tie is real.
- iso − net (noise-free, round 3) was 2.06 µm in section 1, 2.22 at 2000/3 with `same_agents`, and 1.52 at 4000/6. `same_agents` left it about the same; better sampling lowered it.
- The trust choice is the same with challenge and spawn on or off, and at 2000/3 or 4000/6.

## Confidence

- High: eta 5, trust_init 1.0, cred_floor 0.05, discount 0.2, between_site_sd 0.25. The choice is stable across three sweeps (challenge on/off, 2000/3 and 4000/6).
- High: oracle_particles doesn't matter, and the 90% rule can't be met.
- Moderate: 4000/6 over 2000/6. Both sit on the plateau; the paired SEs are about 0.4 µm.
- Moderate: the draft range. It is from the uncalibrated sim; real noise and failure rates will move it.
- Open: whether a 60% chance of a positive result on one real run is acceptable. That is a design question for M (more held-out pieces per plate, or scoring on more rounds, would cut measurement noise).
