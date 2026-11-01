# Build: The Console

A local web page that drives the whole pipeline (plates, approval, measurement, fitting, messages, scoring, privacy audit, 3D viewer) from a browser instead of terminal prompts. It's for practicing and testing the loop end to end, and for typing in real hand measurements when we have them. Every claim we make is still simulation.

## Run it

```
.venv/bin/python -m console                 # http://127.0.0.1:8765, opens the browser
.venv/bin/python -m console --port 9000 --no-browser
```

Stdlib only (`ThreadingHTTPServer`), bound to 127.0.0.1. One run at a time. To use it from a phone at the printer, run it on a laptop and tunnel or change the host in `console/server.py`; there is no login, so keep it local.

## What a practice run is

A practice run is off the books:

- the config comes from the prereg's `config` section, as `run.py --source sim` builds it (`prereg.check.sim_config`), with the prereg's measurement rules (failed-plate fraction, caliper checks) for the real sites;
- no prereg hash goes on the chains;
- plates, STLs, the hand sheets, measurements, receipts and the checkpoint go under `console/runs/<time>/` (git-ignored), never `receipts/real/` or `scans/`.

**A registered real run stays on the CLI:** `python run.py --source real` (see [09-run-sheet.md](09-run-sheet.md)).

### Setup options

| Option | Meaning |
|---|---|
| resin / pla: real or simulated | A real site asks you to approve and measure each plate (`measure.real.RealPrinter`). A simulated site prints on `sim.reference.make_world`. Both simulated = a full dry run. Defaults: resin real (the Form Studio 1), PLA simulated. |
| rounds | 1–5, default from the prereg. |
| world seed | Seeds the simulated world and the run. |
| particles | Default from the prereg (4000); **fast** = 800 for quick tests. |
| share messages | Off = network cut. |
| consistency check | `Config.consistency_check`: drop an incoming note that contradicts the receiver's own data. Rows appear in the live view. |
| lying site | A simulated site that broadcasts corrupted beliefs (`bad_sites`). |
| negative-control world | `make_world(..., independent_shared=True)`: the sites share no physics, so sharing should gain nothing. |

## At a real site

The top card always shows the one thing to do next.

1. **Approve plate.** A drawing of the plate (top view, notch at the bottom, three corner fiducials, row and column numbers, pins filled, holes outlined, held-out pieces ringed), and the STL to download. Approve, approve with an edit note (logged on the receipt chain), or veto (the plate isn't printed; the round is scored without it).
2. **Measure plate.** One row per piece by row, col and kind. Nominal sizes are hidden by default so they don't anchor the reading; a checkbox shows them. For each piece enter the diameter and a status:
   - **ok** with a value in mm. A value over 100 is read as µm (a micrometer reading like `1475.782` becomes 1.4758 mm) and the conversion is shown next to it.
   - **failed**: the piece didn't print.
   - **skip**: it printed but wasn't measured (e.g. every hole, when all we have is a micrometer). **Skip all holes** does that in one click.

   **Submit** writes `{plate_id}-manual.csv` in the run's `scans/<site>/`, the same sheet `RealPrinter` reads with no scanner, and the run continues. **Whole plate failed** answers `fail`; past the prereg's failed-plate fraction the plate is reprinted once and you'll be asked again (with a note saying so).

   **Fill with simulated readings** is for dry runs: a simulated printer of that process (a separate copy of the run's world) makes plausible numbers, which you can edit before submitting. Those plates are recorded as simulated (`source` column `sim-fill` on the sheet, `filled_with_sim` in `results.json`, and a warning on the finished run).

### How skip works

`measure.real.read_manual_sheet` turns `status=skip` into a `Measurement` with status `skipped` and method `not-measured` (`measure.real.NOT_MEASURED`). That method is in `arms.experiment.NOT_DATA`, so the piece is kept on the receipt chain but never used as data or scored, and it isn't a print failure: `_failed_fraction` ignores it, so a pins-only plate doesn't trip the 50% reprint rule. A skipped held-out piece just drops out of that round's scoring (`n_heldout` goes down).

## Live view

Polled every second from `/api/state`: rounds done and what's running now, which site is waiting on the operator, held-out MAE per round, site and arm (in µm; "measured" against the held-out measurements, "truth" against the simulator's hidden diameters, simulated sites only), trust, consistency-check rows, how many numbers crossed the boundary against 0 measurements, and the run's log. Scores come from the checkpoint, written after the seed plates and after each round. At the end the privacy audit (`eval.audit` over the chains) shows PASS or FAIL, and **Build and open the 3D viewer** runs `viewer.export --checkpoint <run>/state.pkl` into `<run>/viewer.html`.

## Corrected designs

The product-facing payoff of learning a printer's error: "I want a 5 mm hole; draw it at 5.23 mm on this printer." After the seed plates and every round, a **Corrected designs** card shows, per site:

- a default table: pins and holes wanted at 2, 3, 5, 7 mm → the size to draw → the predicted printed size and its 90% interval;
- a box to ask for any pin or hole size: "draw it at X mm (+shift µm) → prints Y mm (90%: a–b; printer mean c–d)", plus what drawing it as-is would give.

It uses the **networked arm's latest posterior** for the site, refit from the run's `state.pkl` the same way the arm is scored (`arms.experiment._fit` on the site's own data plus the notes in its inbox, at the trust it holds), cached per checkpoint. Everything is at the plate center. Labels:

- **simulated site**: says it's a simulated machine, and each cell also shows the simulator's hidden **truth** at the corrected draw and as drawn (a separate copy of the run's world, never seen by the agents);
- **real site**: how many measurements (pins, holes) the fit rests on; under 20, or under 5 of either kind, a warning that the model leans on its priors (and the other sites' notes) and the intervals are wide on purpose. Plates filled with simulated readings are named.

How it's computed (`model/compensate.py`): predicted diameter is monotone increasing in nominal over the plate range, so `compensate()` bisects on the posterior-mean prediction (`physics.predict_d`, vectorized over particles) for the nominal that prints at the target. Two 90% intervals at that draw size: **interval**, where one printed and measured piece should land (parameter uncertainty plus the learned scatter `sigma_meas`), and **printer mean** (`model_interval`), parameter uncertainty only. The search is limited to the plate library range (`plates.spec` D_MIN..D_MAX, 1–8 mm): a target that range can't make is clipped and said ("out of range"); a draw size outside the measured range (1.5–7 mm) is flagged as extrapolation, and under 2 mm there's a reminder that the model predicts size, not whether a feature prints. Plate position is an option in the library and CLI (`at=(u, v)`, normalized [-1, 1]).

CLI, on any run's checkpoint:

```
.venv/bin/python -m model.compensate --checkpoint console/runs/<time>/state.pkl --site resin --kind hole --target 5.0
.venv/bin/python -m model.compensate --checkpoint <state.pkl> --site pla --table        # 2, 3, 5, 7 mm
    [--at U V] [--arm isolated]
```

In simulation (10 worlds × 2 sites × pins/holes × 2, 3, 5, 7 mm, 1000 particles fit on the full seed plate), the median |true printed − target| at the plate center goes from 118 µm drawn as-is to 6 µm corrected (90th percentile 269 → 20 µm; corrected is closer in 98% of cases). With only 8 seed pieces: 118 → 17 µm. Simulation only; a real printer adds effects the model doesn't have. Tests: `tests/test_compensate.py`.

**Stop run** is cooperative: it stops at the next plate or at an open prompt. Finished rounds stay in the checkpoint.

## Files

```
console/
  server.py     HTTP endpoints: /api/state, /api/run, /api/answer, /api/measure, /api/fill, /api/designs, /api/corrected, /api/stop, /api/viewer, /runs/<file>
  runner.py     Run: builds the printers, runs run_experiment in a thread, turns RealPrinter's ask= prompts into browser prompts
  index.html    the page (vanilla JS, no CDN)
  runs/<time>/  run.json (settings, config), log.txt, state.pkl, results.json, receipts/, plates/<site>/, scans/<site>/, viewer.html
```

Headless test: `tests/test_real_loop.py::test_console_practice_run_headless`. Corrected designs: `model/compensate.py`, `tests/test_compensate.py`.
