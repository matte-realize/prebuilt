# Formlabs Test Print

One fast resin print to see how the plate prints, scans and compares with the model, before the registered seed run. Nothing from this print goes into receipts or the checkpoint.

Done once so far, on a Formlabs Form Studio 1 with Alpha Fast resin, with no scanner: three pins were measured by micrometer (a 1.5 mm pin read 1.41 and 1.48 mm). That is a sanity check of error size, too few pieces to fit the model, which needs the 16 calibration pieces. With only calipers or a micrometer, enter readings in the [console](console.md) instead of scanning.

## The file

`plates/out/test/resin-test.stl` (regenerate with `python -m plates.fasttest`).

- 100 × 100 mm, 3.5 mm tall: a 2 mm plate with 1.5 mm pins. The seed plate is 6 mm (3 + 3).
- Same layout as the seed plate: 24 pieces (12 pins, 12 through-holes, 1.1–7.3 mm), three square corner fiducials and a notch on one edge. The scanner reads it unchanged.
- About 20 mL of resin.

## Asking the operators

Things to agree on before they slice it:

1. **Which printer and resin?** Any Form 3/3+/3L/4 fits the plate. Standard Grey or Clear V4/V5 is ideal. Write down the resin and layer height used, because the model learns the printer as it's set up.
2. **Can it print flat, directly on the build platform with no supports?** That's the fast option: about 35 layers at 0.1 mm. With PreForm's default supports, a 100 mm plate gets tilted, ends up 30+ mm tall, and takes several times longer. Trade-off: the first layers on the platform can squish and slightly narrow the bottom of the holes, and the part needs careful removal. That's fine for this test. Decide the same way for the real seed plate and don't change it afterwards.
3. **Layer height:** 0.1 mm is the quickest that still resolves a 1.1 mm hole. Use the same setting later.
4. **Can we wash and cure?** Form Wash (IPA, ~10 min), air dry, then Form Cure at the resin's default settings. For a quick look, wash and dry are enough. Full cure changes dimensions by a few µm, so the registered plates must be fully cured every time.
5. **How long is the queue?** Ask for PreForm's time estimate after slicing.

In PreForm: import the STL as is. **Don't scale, rotate or move pieces.** Each piece is identified by its grid position, and the fiducials must stay put. Check that the 1.1 and 1.5 mm holes are open in the slice preview, and that the 1.5 mm pins are present.

## After printing

1. Wash, dry, and cure if you have time. Don't sand or file.
2. **Scan at 400 dpi or more, grayscale, PNG**, with the plate flat on the glass:
   - `scans/test/resin-test-holes.png`: backlit (light through the holes), lid open, or plate on a lightbox.
   - `scans/test/resin-test-pins.png`: front-lit with the lid closed over a dark sheet, pins down on the glass.
3. Optional but useful: measure about 10 pieces with calipers into `scans/test/resin-test-caliper.csv` (format: [real-site-run.md](real-site-run.md), step 4). The tool then corrects scanner bias.
4. Compare:

   ```
   .venv/bin/python -m measure.testprint plates/out/test/resin-test.json scans/test
   ```

   For every piece, side by side: nominal, measured, the prior's prediction, and the prediction after fitting the 16 calibration pieces. Then the held-out error before and after the fit. To see the output without a print, add `--synthetic 0`.

## What to look at

- **Pieces measured: 24 of 24.** Missing small holes or pins tell you the printable limit. That's a real result, not a failure.
- **Measured vs. nominal:** resin holes usually come out a little small and pins a little large. That offset is what the model learns.
- **Held-out error after the fit should drop well below the prior's.** If it doesn't, check scanner scale first (paper target, `measure.target`), then the slice settings.
- If the scanner can't find the fiducials, rescan with more contrast or a cleaner backlight.

The registered run then uses `plates/out/resin/resin-seed.stl` through `python run.py --source real`, with the same printer, resin, layer height and orientation as here.
