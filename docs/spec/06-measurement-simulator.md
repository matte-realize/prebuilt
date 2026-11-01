# Spec: Measurement and Simulator

## 9. Measurement

- **Scanner pipeline** (`measure/scanner.py`): two flatbed scans per plate, backlit for holes and dark background for pins. Fiducials and a notch fix position and orientation; each diameter comes from sub-pixel area (d = 2√(A/π)). About 2–5 µm RMS on synthetic 400 dpi scans; untested on real scans.
- **Spot checks** (`measure/manual.py`): about 10 caliper readings per plate; with 3+ per kind, the scanner − caliper offset is subtracted, which removes pin-shadow bias.
- **Hand measurement:** a manual sheet (`{plate_id}-manual.csv`, entered in the console) replaces the scanner when only calipers or a micrometer are available; pieces printed but not measured are marked `skip` and never used as data.
- **Paper target** (`measure/target.py`) checks a scanner's scale before any plate prints.
- Process-agnostic: works at any site that can print the test-plate spec. Measurements never leave the site.

Real measurements so far: three micrometer readings on one Formlabs Form Studio 1.

## 10. Hidden-truth multi-site simulator

- Implements the same `Printer` interface as real sites, so the experiment code can't tell them apart.
- Each simulated site draws its own machine parameters; shared parameters vary slightly across sites (`shared_jitter`). Effects the model doesn't know about are added on top: a radial plate-position term and small-feature print failures, plus an orientation error in the Warp version.
- Options for controls: `independent_shared` (negative control), `independent_sites` (mixed fleets), `crn` (common random numbers across arms).
- NumPy reference (`sim/reference.py`) and a batched NVIDIA Warp version (`sim/warp_sim.py`) that draws thousands of sites in one kernel launch; `sim/batch.py` runs many seeds with batched GPU posteriors.
- `sim/calibrate.py` (Phase D) calibrates the simulator to real seed-plate data and computes the predicted range; it has run only on rehearsal data.
- Usable as a public benchmark: any characterization method can be scored against the noise-free truth.
