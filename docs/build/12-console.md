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

**Stop run** is cooperative: it stops at the next plate or at an open prompt. Finished rounds stay in the checkpoint.

## Files

```
console/
  server.py     HTTP endpoints: /api/state, /api/run, /api/answer, /api/measure, /api/fill, /api/stop, /api/viewer, /runs/<file>
  runner.py     Run: builds the printers, runs run_experiment in a thread, turns RealPrinter's ask= prompts into browser prompts
  index.html    the page (vanilla JS, no CDN)
  runs/<time>/  run.json (settings, config), log.txt, state.pkl, results.json, receipts/, plates/<site>/, scans/<site>/, viewer.html
```

Headless test: `tests/test_real_loop.py::test_console_practice_run_headless`.
