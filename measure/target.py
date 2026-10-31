"""Printable 1:1 paper target of a plate's hole layout, to check the scanner before printing.

    python -m measure.target plates/out/resin/resin-seed.json target.pdf

Print at 100% scale (no "fit to page") and check the 50 mm scale bar with
calipers. Scan it normally: white circles on the black plate read like a
backlit plate, so use "holes" mode with `target_plate(plate)`, which draws
every slot as a hole. Compare scanner output to the nominal diameters; the
difference is the scanner's error (plus the paper printer's).
"""
from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mp
import matplotlib.pyplot as plt

from measure.manual import MM_PER_IN
from plates import spec
from contracts import Plate
from plates.layout import load_plate


def target_plate(plate: Plate) -> Plate:
    """The plate as drawn on the target: every slot is a hole."""
    from dataclasses import replace
    return replace(plate, pieces=[replace(p, kind="hole") for p in plate.pieces])


def write_target(plate_path: str, out_path: str, dpi: int = 600) -> None:
    plate = load_plate(plate_path)
    margin = 15.0
    side = spec.PLATE + 2 * margin
    fig = plt.figure(figsize=(side / MM_PER_IN, side / MM_PER_IN))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-margin, spec.PLATE + margin)
    ax.set_ylim(-margin, spec.PLATE + margin)
    ax.set_aspect("equal")
    ax.axis("off")
    # Black plate, white through-features: matches a backlit scan of the real plate.
    ax.add_patch(mp.Rectangle((0, 0), spec.PLATE, spec.PLATE, color="black", lw=0))
    for fx, fy in spec.FIDUCIALS:
        s = spec.FIDUCIAL
        ax.add_patch(mp.Rectangle((fx - s / 2, fy - s / 2), s, s, color="white", lw=0))
    nx, nw, nd = spec.NOTCH
    ax.add_patch(mp.Rectangle((nx - nw / 2, -0.5), nw, nd + 0.5, color="white", lw=0))
    for p in plate.pieces:
        ax.add_patch(mp.Circle(spec.slot_center(*p.slot), p.nominal_d / 2, color="white", lw=0))
    ax.plot([0, 50], [-8, -8], color="black", lw=1)
    ax.text(25, -12, "50 mm (check with calipers)", ha="center", fontsize=7)
    ax.text(0, spec.PLATE + 4, f"{plate.plate_id} target: all slots drawn as holes", fontsize=7)
    fig.savefig(out_path, dpi=dpi)


if __name__ == "__main__":
    write_target(sys.argv[1], sys.argv[2])
