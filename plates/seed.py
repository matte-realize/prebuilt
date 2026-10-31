"""Generate seed calibration plates (both sites) and the held-out manifest.

    python -m plates.seed            # writes plates/out/ and prereg/heldout.json

Seed plate: 8 held-out pieces at the fixed slots, plus a calibration grid of
14 diameters x {pin, hole} x 2 duplicates = 56 pieces, randomly placed.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np

from contracts import Plate
from plates import heldout, spec
from plates.layout import build_plate, save_plate
from plates.library import Candidate
from plates.stl import write_stl

OUT = Path(__file__).parent / "out"
SITES = ["resin", "pla"]
SEED_PLACEMENT = {"resin": 101, "pla": 202}


def seed_plate(site: str) -> Plate:
    ds = np.round(np.linspace(*spec.TRAIN_RANGE, 14), 1)
    items = [(Candidate(k, float(d)), "seed") for d in ds for k in ("pin", "hole") for _ in range(2)]
    placement = SEED_PLACEMENT.get(site, zlib.crc32(site.encode()))  # simulated sites: stable per name
    return build_plate(f"{site}-seed", site, items, placement, heldout.heldout_fixed("seed"))


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    (root / "prereg").mkdir(exist_ok=True)
    (root / "prereg" / "heldout.json").write_text(json.dumps(heldout.manifest(), indent=1))
    for site in SITES:
        p = seed_plate(site)
        save_plate(p, OUT / site / f"{p.plate_id}.json")
        tm = write_stl(p, OUT / site / f"{p.plate_id}.stl")
        print(f"{p.plate_id}: {len(p.pieces)} pieces, watertight={tm.is_watertight}, "
              f"volume={tm.volume:.0f} mm^3, bounds={tm.bounds.round(2).tolist()}")


if __name__ == "__main__":
    main()
