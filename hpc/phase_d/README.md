# Phase D: calibrated prediction

Calibrate the simulator to the real seed plates only, then rerun the experiment with the frozen collective config to get the predicted oracle-gap-closed range for `prereg.yaml`.

    .venv/bin/python -m sim.calibrate --state receipts/real/state.pkl \
        --config hpc/phase_d/frozen_config.json --seeds 200 --out hpc/phase_d/out

`--scans scans` reads `scans/<site>/<site>-seed-measurements.json` instead of the checkpoint. `--synthetic SEED` runs the same pipeline on a known sim world as a self-check.

## What it does

1. **Calibration**, per site, seed-arm pieces only (the 8 held-out pieces on the seed plate are left out). Adaptive Metropolis over 8 chains fits the `sim.reference.SimPrinter` hidden truth: the physics parameters including `sigma_meas`, the unmodeled radial term, and the failure model (50% failure diameter per kind, logistic width). Priors are the physics priors, radial ~ N(0, 0.02 mm), failure diameters ~ N(`FAIL_D`, 0.4 mm). Writes `out/calibration.json` (mean, sd, 5-95%, R-hat) and `out/residuals_<site>.png`.
2. **Prediction**: `--seeds` full experiments with the frozen config. Each seed draws a fresh world from the calibration posterior, so the range includes calibration uncertainty. Writes `out/prediction.json` and `out/summary.md`, with the exact command and git hash.

Reported per round: oracle gap closed on measured MAE (what round 1-3 on real printers will produce), the same on noise-free MAE, and isolated − networked in µm. Interval is the 5-95% range over seeds.

Not fitted: the Warp sim's orientation term. One seed plate per site can't separate it from noise, and the Phase C sweeps ran on the reference sim.

## Frozen config

`frozen_config.json` holds the `arms.experiment.Config` fields frozen after the Phase C tuning sweep: `rounds`, `n_particles`, `slots_per_arm`, `seed_pieces`, `eta`, `cred_floor`, `discount`, `trust_init`, `between_site_sd`. `sim.calibrate` and `run.py --source real` refuse to run without all of them, so the real run and the prediction use the same settings. With `--config`, `run.py` ignores `--rounds`, `--particles`, `--slots` and `--seed-pieces`.

TODO: fill in from the tuning sweep (`hpc/sweeps/phase_c/results/tuning_*`).

## Proposed `predicted_range_oracle_gap_closed`

TODO: after the real seed plates are measured. Fill in the value, `prediction.json`'s command and git hash, and the calibration summary. Then commit `prereg.yaml` and record that commit hash.
