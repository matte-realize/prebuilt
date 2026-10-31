"""Generate seed calibration plates (both sites) and the held-out manifest.

    python -m plates.seed            # writes plates/out/ and prereg/heldout.json

Seed plate: 8 held-out pieces at the fixed slots, plus SEED_PIECES calibration
pieces. The full calibration grid is 14 diameters x {pin, hole} x 2 duplicates
= 56 pieces, randomly placed; the printed plate keeps 16 of them, evenly spaced
in (kind, diameter). Phase C showed that with all 56 each site learns the shared
parameters alone and the arms can't separate (hpc/sweeps/phase_c/README.md).
"""
from __future__ import annotations

import json
import zlib
from dataclasses import replace
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
SEED_PIECES = 16


def seed_plate(site: str, keep: int | None = SEED_PIECES) -> Plate:
    """The seed plate with `keep` calibration pieces (None = the full 56). Held-out always kept."""
    ds = np.round(np.linspace(*spec.TRAIN_RANGE, 14), 1)
    items = [(Candidate(k, float(d)), "seed") for d in ds for k in ("pin", "hole") for _ in range(2)]
    placement = SEED_PLACEMENT.get(site, zlib.crc32(site.encode()))  # simulated sites: stable per name
    plate = build_plate(f"{site}-seed", site, items, placement, heldout.heldout_fixed("seed"))
    if keep is None:
        return plate
    seed = sorted((p for p in plate.pieces if p.arm == "seed"), key=lambda p: (p.kind, p.nominal_d, p.slot))
    idx = set(np.round(np.linspace(0, len(seed) - 1, keep)).astype(int)) if keep else set()
    kept = {seed[i].piece_id for i in idx}
    return replace(plate, pieces=[p for p in plate.pieces if p.arm != "seed" or p.piece_id in kept])


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
