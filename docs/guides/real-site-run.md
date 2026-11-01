# Running at Real Sites

The registered real-printer run, step by step, for whoever is at the printers. All commands run from the repo root with `.venv/bin/python` (shown as `py`). To practice the loop or enter hand measurements in a browser instead, use the [console](console.md).

## 0. Before printing

1. `py -m prereg.check` must say **ready for seed**. If it lists `config.*` fields, the config isn't complete. Don't print the seed plates without it: the checkpoint locks the config.
2. `py -m pytest -q`: everything passes.
3. Rehearse once: `py -m measure.rehearsal --rounds 1 --out /tmp/reh`. Same prompts and files as the real run, with simulated scans.

## 1. Scanner check (~15 min)

1. Print `plates/out/resin/resin-seed-target.pdf` at **100% scale** (no "fit to page"). Check the 50 mm bar with calipers.
2. Scan it at **600 dpi, grayscale, PNG**, then run `py -m measure.target plates/out/resin/resin-seed.json --check <scan>.png`.
3. Ready when `failed: 0`, `|bias_um|` is under ~20, and `sd_um` is under ~20. A constant bias with a good 50 mm bar points at the scanner's scale; note it, and the caliper offset will correct it per plate.

## 2. Slice check

Load `plates/out/resin/resin-seed.stl` in PreForm and `plates/out/pla/pla-seed.stl` in the PLA slicer. Each plate is 100 × 100 mm, 3 mm thick, with 3 mm pins, 16 calibration pieces and 8 held-out. Check:
- The smallest holes (1.1 mm held-out, 1.5 mm calibration) aren't closed by the slicer, and the 1.5 mm pins aren't dropped.
- Print flat, plate on the bed, pins up. No supports under the plate for PLA; resin per PreForm's default for a flat part.
- Don't scale, rotate or move anything in the slicer. Piece identity comes from grid position and the fiducials.

Optional test print (off the books: no receipts, no checkpoint; see [test-print.md](test-print.md)): print the same STL, scan it into `scans/test/` with the usual names, then

```
py -m measure.testprint plates/out/resin/resin-seed.json scans/test
```

It lists every piece side by side (nominal, measured, prior prediction, prediction after fitting the 16 calibration pieces) and the held-out MAE before and after the fit. Add `--synthetic 0` to try it without a print.

## 3. Start the real run (seed plate)

```
py run.py --source real
```

- It checks the prereg and prints its sha256. With no predicted range yet, it runs **the seed plate only**.
- For each site it writes the plate files, prints the caliper-check slots, and asks for approval. Answer `y`; or describe an edit (printed, with the note logged); or `veto <reason>` to skip the plate, which isn't printed and leaves the round without it.
- Then it waits for scans: `scans/<site>/<plate_id>-holes.png` and `-pins.png`. Press Enter once both are saved. Type `fail` if the whole plate failed to print.
- Leave it running between prints. If it crashes or you stop it, run the same command again. It resumes from `receipts/real/state.pkl` and refuses if the settings changed.

## 4. Each plate: print, clean, scan, check

1. **Print** the plate file named in the prompt (`plates/out/<site>/<plate_id>.stl`). Resin: wash and cure fully before scanning.
2. **Holes scan** (backlit): plate flat on the glass, with a light source above it (lightpad, or a white phone screen at full brightness) and the lid open. Holes and the 3 square fiducials should show bright.
3. **Pins scan** (dark background): plate **pins down** on the glass, covered with black cloth or the closed lid. Pin tops should show bright on mid-gray.
4. Both at **≥ 400 dpi (600 preferred), grayscale, PNG**, whole plate in frame with a margin. Face up or face down are both fine: the notch tells the scanner which. Save as `scans/<site>/<plate_id>-holes.png` and `-pins.png`.
5. **Calipers** on the ~10 slots the prompt listed (half pins, half holes), written to `scans/<site>/<plate_id>-caliper.csv`:
   ```
   row,col,measured_d,status
   0,3,4.08,ok
   2,1,,failed
   ```
   Held-out pieces are never in the caliper list. Bad rows are skipped with a warning.
   Hold the plate pins up with the notch toward you: row 0 is the far row and column 0 the left column, counting from 0 (matches the plate file). With 3+ checks per kind, the run subtracts the scanner-vs-caliper offset. That fixes pin shadows, which read ~50 µm small.
6. Press Enter. Read the output:
   - `holes: n/n measured` and `pins: n/n measured`. Check that `um/px` matches your dpi (25400 / dpi).
   - `no feature (did not print?)`: the piece really is missing. That's fine, it's a printability outcome.
   - `blob touches cell edge (fused?)`: look at the piece. If it's a scanner problem (dust, hair), rescan and rerun.
   - Scanner vs caliper `mae` above ~0.05 mm: rescan (focus, flatness) before going on.
7. **Fit checks:** push 2–3 printed pins into printed holes from the same plate and write what you feel to `scans/<site>/<plate_id>-fitcheck.csv`:
   ```
   pin_row,pin_col,hole_row,hole_col,fit
   2,1,5,2,slip
   ```
   `fit` is press, slip or loose. After any round, `py -m eval.fitcheck` compares them with each arm's predicted class and the scanner-implied class.

**Failed plate:** if more than 50% of a plate's pieces fail (`failed_plate_fraction`), the run says so. It moves the scans to `<plate_id>.failed1-*` and waits for scans of a reprint of the same plate file. If the reprint also fails, that plate is dropped from the round (prereg failure rule). A seed plate that fails twice on one printer means one real site plus simulated sites (fallback tier B: `run.py --source real --sim-site <site>`).

## 5. After the seed plates: commit the predicted range

0. Read the **seed plate check** the run prints at the end (`eval.prior_check`). `ok` per site means the printer sits inside what the model can represent. A parameter "at its bound" means the real printer is outside the prior: widen that prior in `model/physics.py` **before** Phase D (the frozen config doesn't include priors, but the prediction depends on them). A residual trend points at a missing term; note it for the slides.
1. Commit nothing from `scans/` or `receipts/real/` (git-ignored, site data). Phase D needs the checkpoint `receipts/real/state.pkl` (or the `scans/<site>/<site>-seed-measurements.json` files).
2. Run Phase D: `py -m sim.calibrate --state receipts/real/state.pkl --seeds 200 --out hpc/phase_d/out` (see `hpc/phase_d/README.md`). Fill `predicted_range.range` in `prereg/prereg.yaml` and commits it. Record the commit hash.
3. `py -m prereg.check --stage round1` must say ready.

## 6. Rounds 1–3

1. `py run.py --source real` again. It resumes after the seed plate and logs the new prereg hash on both chains.
2. Each round: approve, print, scan, calipers, Enter (step 4). The auction, credit and messages run on their own after measurement.
3. Between rounds (optional, exploratory): `py -m agents.hypothesis --checkpoint receipts/real/state.pkl`. It needs a Nemotron endpoint: on Brev run `agents/serve_nemotron.sh`, forward port 8000, check with `py -m agents.hypothesis --ping`. Use `--dry-run` without one.
4. At the end: `py run.py --source real --out real.json` once more, which prints the summary and writes the scores. Then:
   - `py -m eval.audit receipts/real/resin.jsonl receipts/real/pla.jsonl` (privacy audit, must PASS)
   - `py -m eval.figures.headline sim.json --real real.json` (`sim.json` is a `run.py --source sim --seeds N --out` run)
   - `py -m viewer.export --checkpoint receipts/real/state.pkl --open` (demo page)

## If something goes wrong

| Problem | Do |
|---|---|
| `could not find the three fiducials` | The run asks you to rescan; it doesn't stop. Is the whole plate in frame? Are the fiducials clean and visible? For pins scans, use more contrast (a darker cover). Save over the same file and press Enter. |
| Many `failed` on a plate that printed fine | Wrong scan mode or lighting: holes need backlight, pins need a dark cover. Rescan. |
| `um/px` doesn't match the dpi | The scanner resampled. Set the dpi explicitly, turn off auto-crop and descreen, and rescan. |
| The run crashed | Rerun the same command. It resumes from the last checkpoint and logs a `resume` entry; the interrupted round reruns with the same plates. Scans already saved are reused. |
| `was started with different settings` | Someone changed the prereg config after the seed plate. Revert it. Only the range may change. |
| Out of time | Stop adding rounds. Measure and score what exists. |
