# Phase D: calibrated prediction

Calibrate the simulator to the real seed plates only, then rerun the experiment with the frozen collective config to get the predicted oracle-gap-closed range for `prereg.yaml`.

    .venv/bin/python -m sim.calibrate --state receipts/real/state.pkl --seeds 200 --out hpc/phase_d/out

Check the failed seed pieces listed in `out/summary.md`. Any that are scanner misses rather than print failures go back in with `--exclude-failed <piece_id> ...`; a seed plate where every piece failed stops the run. `--scans scans` reads `scans/<site>/<site>-seed-measurements.json` instead of the checkpoint. `--synthetic SEED` runs the same pipeline on a known sim world as a self-check.

## What it does

1. **Calibration**, seed-arm pieces only (the 8 held-out pieces on the seed plate are left out). Adaptive Metropolis over 8 chains fits the `sim.reference.SimPrinter` hidden truth: the physics parameters including `sigma_meas`, the unmodeled radial term, and the failure model (50% failure diameter per kind, logistic width). Diameters are fit jointly across both sites: world-level shared parameters get the physics prior, and each site's shared parameters sit within `--shared-jitter` (default 0.2 prior std, as in `make_world`) of them. One posterior draw is one world, so the two sites share one truth like the real printers do. Failures are fit per site. Priors: physics priors, radial ~ N(0, 0.02 mm), failure diameters ~ N(`FAIL_D`, 0.4 mm). Writes `out/calibration.json` (mean, sd, 5-95%, R-hat) and `out/residuals_<site>.png`.
2. **Prediction**: `--seeds` full experiments with the frozen config. Each seed draws a fresh world from the calibration posterior, so the range includes calibration uncertainty. Writes `out/prediction.json` and `out/summary.md`, with the exact command and git hash.

Reported per round, median and 5-95% range over seeds: isolated − networked in µm on measured MAE (the primary metric, per 07-status, and what real rounds produce) and on noise-free MAE, plus oracle gap closed on both as a reference.

Not fitted: the Warp sim's orientation term. One seed plate per site can't separate it from noise, and the Phase C sweeps ran on the reference sim.

## Config

The prediction takes its config from the `config` section of `prereg/prereg.yaml`, the same place `run.py --source real` does, and records the prereg's sha256. It refuses to run while any field a seed-plate run needs is null (the tuning values from Phase C). `--draft` runs anyway with those fields at `Config` defaults and marks the output DRAFT, for checking the pipeline only.

`run.py --source real` refuses to resume a checkpoint started with different settings; only `rounds` and the prereg hash may change, since committing the range changes both.

## Proposed predicted range

The prereg field is still named `predicted_range_oracle_gap_closed`. With iso − net now primary, M should decide which number it holds (or rename it) before it is filled in.

TODO: after the real seed plates are measured. Fill in the value, `prediction.json`'s command and git hash, and the calibration summary. Then commit `prereg.yaml` and record that commit hash.
