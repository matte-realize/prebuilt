"""Printable 1:1 paper target of a plate's hole layout, to check the scanner before printing.

    python -m measure.target plates/out/resin/resin-seed.json target.pdf            # write it
    python -m measure.target plates/out/resin/resin-seed.json --check target-scan.png  # measure a scan of it

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


def check_scan(plate_path: str, scan_path: str) -> dict:
    """Scanner error on a scan of the paper target: measured minus nominal, per slot."""
    import cv2
    import numpy as np
    from measure.scanner import measure_scan
    plate = target_plate(load_plate(plate_path))
    img = cv2.imread(scan_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"can't read {scan_path}")
    ms, info = measure_scan(img, plate, "holes")
    nominal = {p.piece_id: p.nominal_d for p in plate.pieces}
    err = np.array([m.measured_d - nominal[m.piece_id] for m in ms if m.status == "ok"])
    out = {"um_per_px": round(info.mm_per_px * 1000, 1), "mirrored": info.mirrored,
           "measured": len(err), "failed": sum(m.status == "failed" for m in ms), "notes": info.notes}
    if len(err):
        out |= {"bias_um": round(float(err.mean()) * 1000, 1), "sd_um": round(float(err.std()) * 1000, 1),
                "max_abs_um": round(float(np.abs(err).max()) * 1000, 1)}
    return out


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[2] == "--check":
        r = check_scan(sys.argv[1], sys.argv[3])
        for k, v in r.items():
            print(f"{k}: {v}")
        print("Bias near 0 and sd under ~20 um means the scanner is ready. A constant bias is usually the "
              "paper printer's scale: check the 50 mm bar with calipers.")
    else:
        write_target(sys.argv[1], sys.argv[2])
