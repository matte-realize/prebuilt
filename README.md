# Prebuilt

A decentralized collective of scientist agents that characterizes 3D printers (resin SLA and PLA FDM) across sites that never share raw data, only beliefs. Built for the ScienceClaw Hackathon, MIT Media Lab, Oct 30 – Nov 1, 2026.

Each site prints test plates of pins and holes, scans them, and fits a physics model of its printer. Agents at each site bid for plate slots in a credibility-weighted auction. Sites exchange only posterior summaries of process-agnostic parameters, through a typed, schema-checked boundary that is recorded on hash-chained receipts. Three arms run side by side on every plate: **isolated** (own data only), **networked** (own data plus other sites' messages) and **oracle** (all raw data pooled). The question is how much of the isolated-to-oracle gap the network closes without pooling data.

## Setup

```
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"        # add ",warp" for the GPU simulator and posterior
.venv/bin/python -m pytest -q
```

Run commands from the repo root.

## Quick start

```
python run.py --source sim --seeds 10 --out sim.json           # all three arms on simulated printers
python -m eval.figures.headline sim.json --truth                # headline chart
python -m viewer.export --source sim --rounds 3 --open          # demo page for one run
python -m measure.rehearsal --rounds 2 --out /tmp/reh           # the real-printer loop, simulated scans
python -m prereg.check                                          # what the pre-registration still needs
python run.py --source real                                     # real printers (see the run sheet)
```

## Where things are

| Directory | What |
|---|---|
| `contracts.py` | Shared types: `Piece`, `Plate`, `Measurement`, `Printer`, `Model`, `Message` |
| `plates/` | Test-plate spec, piece library, plate generator, STL export, held-out set |
| `measure/` | Flatbed scanner pipeline, paper target, caliper entry, real-printer loop, rehearsal |
| `model/` | Physics models and the particle posterior (NumPy reference; `posterior_warp.py` on GPU) |
| `agents/` | Agents, auction, credibility, challenge round, hypothesis agent |
| `network/` | Message schema and boundary enforcement |
| `arms/` | The three-arm experiment (`run_experiment`) |
| `sim/` | Hidden-truth simulators (NumPy reference, Warp) and Phase D calibration |
| `eval/` | Metrics, fit-class accuracy, privacy audit, figures |
| `receipts/` | Hash-chained receipt logs |
| `prereg/` | Pre-registration and the held-out manifest |
| `hpc/` | Benchmarks, Nebius jobs, Phase C sweeps, Phase D |
| `viewer/` | Self-contained HTML page for a run |
| `console/` | Local web UI that drives a practice run from the browser: approve plates, enter hand measurements, watch scores (`python -m console`, [12-console.md](docs/build/12-console.md)) |
| `docs/` | Spec, build walkthrough, task split, status, run sheet ([index](docs/README.md)) |

## Reusable tools

Three parts are meant for reuse outside this project (spec §17).

### 1. Process-agnostic test plate

A 100 × 100 × 3 mm plate with an 8 × 8 grid of 10 mm cells. Each cell holds a through-hole or a 3 mm-tall pin at a chosen nominal diameter (1.0–8.0 mm in 0.1 mm steps). Three square corner fiducials and a bottom-edge notch fix position and orientation, so piece identity comes from grid position and no printed labels are needed. Any printer that can make a flat plate can print it.

```python
from plates.layout import build_plate
from plates.library import Candidate
from plates.stl import write_stl

plate = build_plate("my-plate", "my-site", [(Candidate("hole", 3.0), "test"), (Candidate("pin", 4.5), "test")], seed=1)
write_stl(plate, "my-plate.stl")    # watertight, ready for the slicer
```

The spec constants are in `plates/spec.py`. `python -m plates.seed` regenerates this project's seed plates.

### 2. Flatbed scanner measurement

Measures every pin and hole diameter on a plate from two ordinary flatbed scans: backlit for holes, dark background for pins. It finds the fiducials, detects a mirrored (face-down) scan from the notch, fits pixels to millimeters, and measures each feature's area with sub-pixel coverage weighting (d = 2√(A/π)), which doesn't depend on focus. Missing features come back as `status="failed"`.

```python
import cv2
from measure.scanner import measure_scan
from plates.layout import load_plate

plate = load_plate("plates/out/resin/resin-seed.json")
ms, info = measure_scan(cv2.imread("scan-holes.png", cv2.IMREAD_GRAYSCALE), plate, "holes")
```

On synthetic scans at 400 dpi it's about 2–5 µm RMS (`docs/build/07-status.md` has the stress test). Check your scanner first with a printed paper target: `python -m measure.target <plate.json> target.pdf`, then `python -m measure.target <plate.json> --check <scan>.png`. With caliper spot checks (`measure/manual.py`), a per-plate offset removes the remaining bias.

### 3. Hidden-truth multi-site simulator benchmark

Simulated printers that implement the same `Printer` interface as the real ones. Each site draws its own machine parameters, shared parameters vary slightly across sites, and effects the models don't know about are added on top: a radial plate-position term and, in the Warp version, orientation error, plus small-feature print failures. Any characterization method can be scored against the noise-free truth.

```python
from sim.reference import make_world          # NumPy reference; sim.warp_sim.make_world is the GPU drop-in
world = make_world({"resin": "resin", "pla": "pla"}, seed=0)
measurements = world["resin"].print_and_measure(plate)
truth = world["resin"].truth(plate)            # noise-free diameters, for scoring only
```

`sim.warp_sim` draws thousands of sites and prints batches of plates in one kernel launch, for sweeps.

## Status

See [docs/build/07-status.md](docs/build/07-status.md) for findings and decisions, [06-task-split.md](docs/build/06-task-split.md) for who owns what, and [09-run-sheet.md](docs/build/09-run-sheet.md) for printer day.
