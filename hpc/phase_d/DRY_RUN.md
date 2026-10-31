# Phase D dry run

Rehearsal of the Saturday hand-off (seed plate -> Phase D -> commit range -> round 1) on a checkpoint from the real loop, run 2026-10-31 on the laptop (16 cores, RTX 5060 8 GB) at the prereg config (4000 particles, 6 MH steps). Everything works end to end after one fix in `sim/calibrate.py` (below). Round 1 waits about **3-5 minutes** on Phase D with the GPU path, whether or not other jobs are running; the CPU path takes 4.5 minutes idle but 20 under load.

## Commands for the real day

From the repo root, `py` = `.venv/bin/python`.

1. Seed plate (run sheet 3-5). With `predicted_range.range` null this runs the seed plate only and writes `receipts/real/state.pkl`:

       py run.py --source real

2. Commit or discard local changes first: `prediction.json` records the git hash and a dirty flag. Stopping other jobs helps but isn't required on the GPU path.

3. Phase D:

       py -m sim.calibrate --state receipts/real/state.pkl --seeds 200 --workers 6 --gpu-batch 17 --out hpc/phase_d/out

   No GPU (Warp or CUDA missing): drop `--gpu-batch 17` for the CPU path. Use one path only: every rerun (e.g. with `--exclude-failed`) keeps the same flags, so the committed range comes from one path.

   In `out/summary.md`, check the "Failed seed pieces" list. Any that are scanner misses rather than print failures: rerun with `--exclude-failed <piece_id> ...` (the fit is 20 s, the prediction the rest). Pieces listed as "not measured" (a cell outside the scan) are already left out.
   Check `out/residuals_<site>.png` and that every R-hat in the summary is under 1.05.

4. Copy the round-3 "isolated − networked, measured MAE" 5% and 95% values from `out/summary.md` into `prereg/prereg.yaml`, replacing `range: [null, null]`. Then:

       py -m prereg.check --stage round1      # must say "ready for round1"; prints the new sha256
       git add prereg/prereg.yaml && git commit -m "docs: commit Phase D predicted range"

   Record the commit hash with `prediction.json`'s command, git hash and prereg sha256.

5. Round 1 onward: `py run.py --source real` again. It resumes from the checkpoint and logs `resume` and then `prereg {sha256: <new>, from_round: 1}` on both chains. The seed-plate `config` entry keeps the old sha256 with `rounds: 0`.

## What the dry run did

    py -m hpc.phase_d.rehearse --out $DRY                                    # seed plate only
    py -m sim.calibrate --state $DRY/receipts/state.pkl --seeds 200 --workers 6 --out $DRY/phase_d
    cp prereg/prereg.yaml $DRY/prereg.yaml                                   # then fill range in the copy
    py -m prereg.check --path $DRY/prereg.yaml --stage round1
    py -m hpc.phase_d.rehearse --out $DRY --prereg $DRY/prereg.yaml --scores $DRY/real.json   # resumes, rounds 1-3

`hpc/phase_d/rehearse.py` is `run.py --source real` unchanged except that `run.real_printers` returns `measure.rehearsal` printers (simulated world `make_world(SITES, 0)`, scans rendered to disk and read by the real scanner). The real prereg is never touched.

Results:

- **Seed plate**: 16 calibration + 8 held-out pieces per site. One held-out 1.1 mm hole did not print at each site; no seed piece failed. The prior check said `ok` for both sites. Calibration read only the 16 seed pieces per site.
- **Calibration vs the known world**: all 24 fitted parameters (8 resin + 7 pla physics, radial, 3 failure each) have the true value inside their 5-95% interval; the largest miss is resin `sigma_meas` (true 0.044, fit 0.034 ± 0.006). Max R-hat 1.002. The failure parameters stay near their priors because nothing failed on the seed plate.
- **Predicted range** (round 3, isolated − networked, measured MAE): median 0.36 µm, 5-95% [-3.94, 4.59] µm. It is below the 1.2-1.7 µm median in the README because this world's pla printer is noisy (`sigma_meas` 0.06 mm against a 0.04 prior mean), and noise hides the sharing benefit. It spans zero, as the prereg claim expects.
- **prereg.check** on the filled copy: `ready for round1`. Resume ran rounds 1-3; both chains verify, carry the new sha256 from round 1, and the privacy audit passes. The rehearsal's round-3 isolated − networked came out -3.6 µm, inside the range.
- **Failed pieces**, on checkpoint copies: a failed 1.5 mm seed hole per site is listed in the summary and fit as a printability failure; `--exclude-failed` removes it; a wrong id is refused.

## Timings

Wall time, 200 seeds unless noted.

| step | quiet laptop (load ~15) | loaded (load 50-64: Phase C sweep + 2 other runs) |
|---|---|---|
| seed plate compute (rehearsal; real = print + scan time) | - | 3.8 s |
| calibration fit (inside `sim.calibrate`) | ~20 s | ~20 s |
| prediction, CPU, `--workers 6` | **4 min 22 s** | 20 min 9 s |
| prediction, GPU, `--workers 6 --gpu-batch 17` | 3 min 17 s | 4 min 26 s (`--workers 4 --gpu-batch 25`, GPU shared at 87%) |
| rounds 1-3 compute (rehearsal) | - | 96 s total |

The 7.5 min in the README was measured under some load; on an idle laptop it is closer to 4.5 min. Both paths give the same numbers on every rerun: CPU reproduced to the last digit at both loads, and GPU at two batch sizes.

**Use the GPU path on the real day.** It is never slower, and under load it was 4.5× faster even with another job using 87% of the GPU, so round 1 doesn't depend on what else is running. CPU and GPU give slightly different ranges from the same seeds and worlds (GPU [-3.24, 5.16] vs CPU [-3.94, 4.59]), because their Metropolis moves draw different random numbers. Both are valid; commit the range from one path, and `prediction.json` records which (the command includes `--gpu-batch`). The GPU path is newer: it reuses `sim.batch` and `model.posterior_warp`, which are tested against the NumPy reference, but its own test only checks that it runs and returns the same shape of results as CPU.

## Bugs found

1. **Fixed (`sim/calibrate.py`)**: `sim.calibrate --state` refused a real checkpoint whenever a seed piece was not measured. `arms.experiment._ingest` keeps `NOT_DATA` measurements out of the data: `scanner-miss` (the cell lies outside the scan image) and `failed-plate`. So one cropped scan the operator didn't redo gave `seed pieces per site {'resin': 16, 'pla': 15} don't match the frozen config's seed_pieces=16`, with no way around it on the day. Reproduced on a checkpoint copy with one pla seed pin dropped. Now the checkpoint's printed seed pieces (`state["pieces"]`) count as on the plate, the unmeasured ones are left out and listed as "not measured" in `calibration.json` and `summary.md`, and a wrong `seed_pieces` is still refused. `--scans` routes `NOT_DATA` rows the same way; before, it fit them as print failures. A site with no measured seed piece now gets a clear "seed plate dropped?" message.

2. **Proposed, `measure/rehearsal.py` (Matthew's)**: the run sheet's rehearsal (`py -m measure.rehearsal`, step 0.3) runs `Config(rounds, n_particles=1000)`, not the prereg config. It records no prereg sha256, skips the seed-only stop and the resume check, and `RehearsalPrinter` drops `failed_plate_fraction` and the caliper settings, so the reprint rule is never rehearsed. `hpc/phase_d/rehearse.py` covers the config side. Proposed so the printer side matches too:

   ```diff
   --- a/measure/rehearsal.py
   +++ b/measure/rehearsal.py
   @@ class RehearsalPrinter(RealPrinter):
   -    def __init__(self, sim: SimPrinter, scan_dir: str | Path, plate_dir: str | Path, dpi: float = 400, seed: int = 0):
   -        super().__init__(sim.site, str(scan_dir), ask=self._operator, plate_dir=plate_dir)
   +    def __init__(self, sim: SimPrinter, scan_dir: str | Path, plate_dir: str | Path, dpi: float = 400, seed: int = 0,
   +                 **real):
   +        """`real`: RealPrinter's failed_plate_fraction / caliper settings, as run.real_printers passes them."""
   +        super().__init__(sim.site, str(scan_dir), ask=self._operator, plate_dir=plate_dir, **real)
   @@
   -def rehearsal_printers(sites: dict[str, str], out: Path, seed: int = 0) -> dict[str, RehearsalPrinter]:
   +def rehearsal_printers(sites: dict[str, str], out: Path, seed: int = 0, **real) -> dict[str, RehearsalPrinter]:
        from sim.reference import make_world
        world = make_world(sites, seed)
   -    return {s: RehearsalPrinter(world[s], out / "scans" / s, out / "plates", seed=seed + i)
   +    return {s: RehearsalPrinter(world[s], out / "scans" / s, out / "plates", seed=seed + i, **real)
                for i, s in enumerate(sites)}
   ```

   Then `hpc/phase_d/rehearse.py` passes `failed_plate_fraction=cfg.failed_plate_fraction, caliper_checks=cfg.caliper_checks, caliper_min_pairs=cfg.caliper_min_pairs`, and run sheet step 0.3 can point at `py -m hpc.phase_d.rehearse --out /tmp/reh`.

3. **Not a bug, but watch it**: CPU Phase D wall time depends on machine load (4.4 vs 20 min above). The GPU path is the answer; on CPU, stop other jobs first.
