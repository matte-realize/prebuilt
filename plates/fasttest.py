"""Fast test plate: the seed plate's layout, half the height.

Same 100 x 100 mm footprint, fiducials and piece positions as the seed plate, so
the scanner and `measure.testprint` read it unchanged. The plate is 2 mm thick with
1.5 mm pins (seed plate: 3 + 3 mm), so a resin printer laid flat on the build
platform prints about 35 layers at 0.1 mm instead of 60. Off the books: for
checking the printer, slicer and scanner, never for the registered run.

    python -m plates.fasttest            # writes plates/out/test/{site}-test.{json,stl}
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from plates.layout import save_plate
from plates.seed import OUT, SITES, seed_plate
from plates.stl import write_stl

THICK, PIN_H = 2.0, 1.5


def main() -> None:
    for site in SITES:
        p = seed_plate(site)
        p = replace(p, plate_id=f"{site}-test")
        save_plate(p, OUT / "test" / f"{p.plate_id}.json")
        tm = write_stl(p, Path(OUT / "test" / f"{p.plate_id}.stl"), THICK, PIN_H)
        print(f"{p.plate_id}: {len(p.pieces)} pieces, watertight={tm.is_watertight}, "
              f"height={tm.extents[2]:.1f} mm, volume={tm.volume / 1000:.1f} mL")


if __name__ == "__main__":
    main()
