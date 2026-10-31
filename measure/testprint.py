"""Test print: scan one printed plate and compare it, piece by piece, with the model.

Off the books: nothing goes on a receipt chain or into the checkpoint, so a test print
of the seed plate doesn't count as the registered seed run. Use it to check the printer,
the slicer and the scanner before `run.py --source real`.

    python -m measure.testprint plates/out/resin/resin-seed.json scans/test
    python -m measure.testprint plates/out/resin/resin-seed.json /tmp/tp --synthetic 0   # self-check

Reads {plate_id}-holes.png and -pins.png (and -caliper.csv if present) from the scan
directory. Side by side per piece: nominal, measured, the prior's prediction, and the
prediction after fitting the plate's calibration pieces. Held-out pieces are never
fitted, so their "fit" column is an out-of-sample check.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from contracts import Measurement, Plate
from measure.manual import agreement, apply_offsets, load_caliper_csv, scanner_offsets
from measure.scanner import measure_scan
from model.posterior import ParticlePosterior
from plates.layout import load_plate

PROCESS = {"resin": "resin", "pla": "pla"}


def read_scans(plate: Plate, scan_dir: Path) -> list[Measurement]:
    base = scan_dir / plate.plate_id
    ms = []
    for mode in ("holes", "pins"):
        img = cv2.imread(f"{base}-{mode}.png", cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise SystemExit(f"missing or unreadable: {base}-{mode}.png")
        got, info = measure_scan(img, plate, mode)
        print(f"{mode}: {sum(m.status == 'ok' for m in got)}/{len(got)} measured, "
              f"{info.mm_per_px * 1000:.1f} um/px, mirrored={info.mirrored}")
        for n in info.notes:
            print(f"  {n}")
        ms += got
    cal = Path(f"{base}-caliper.csv")
    if cal.exists():
        checks = load_caliper_csv(str(cal), plate)
        print(f"scanner vs caliper: {agreement(ms, checks)}")
        offsets = scanner_offsets(ms, checks, plate)
        if offsets:
            ms = apply_offsets(ms, offsets, plate)
            print(f"corrected scanner bias per kind (mm): {offsets}")
    return ms


def synthesize(plate: Plate, scan_dir: Path, seed: int) -> None:
    """Print the plate on a simulated printer and render its two scans."""
    from measure.synth import render_scan
    from sim.reference import make_world

    sim = make_world({plate.site: PROCESS[plate.site]}, seed)[plate.site]
    rng = np.random.default_rng(seed)
    true = {p.piece_id: float(d + 0.03 * rng.standard_normal()) for p, d in zip(plate.pieces, sim.truth(plate))}
    scan_dir.mkdir(parents=True, exist_ok=True)
    for mode in ("holes", "pins"):
        img = render_scan(plate, true, mode, angle_deg=float(rng.uniform(-3, 3)), seed=int(rng.integers(2**31)))
        cv2.imwrite(str(scan_dir / f"{plate.plate_id}-{mode}.png"), img)


def compare(plate: Plate, ms: list[Measurement], particles: int, seed: int) -> None:
    pieces = {p.piece_id: p for p in plate.pieces}
    prior = ParticlePosterior(PROCESS[plate.site], pieces, n=particles, seed=seed)
    fit = ParticlePosterior(PROCESS[plate.site], pieces, n=particles, seed=seed)
    fit.update([m for m in ms if pieces[m.piece_id].arm != "heldout"])

    got = {m.piece_id: m for m in ms}
    print(f"\n{'slot':<8}{'kind':<5}{'arm':<8}{'nominal':>8}{'measured':>9}{'prior':>8}{'fit':>8}{'fit err':>9}  (mm)")
    err = {"prior": [], "fit": []}
    for p in sorted(plate.pieces, key=lambda p: (p.arm != "heldout", p.kind, p.nominal_d)):
        m = got.get(p.piece_id)
        mu0, mu1 = prior.predict(p)[0], fit.predict(p)[0]
        if m is None or m.status != "ok":
            meas, e = (m.status if m else "missing"), ""
        else:
            meas, e = f"{m.measured_d:.3f}", f"{m.measured_d - mu1:+.3f}"
            if p.arm == "heldout":
                err["prior"].append(abs(m.measured_d - mu0))
                err["fit"].append(abs(m.measured_d - mu1))
        print(f"{p.piece_id.rsplit('-', 1)[-1]:<8}{p.kind:<5}{p.arm:<8}{p.nominal_d:>8.2f}{meas:>9}{mu0:>8.3f}{mu1:>8.3f}{e:>9}")
    if err["fit"]:
        print(f"\nheld-out MAE ({len(err['fit'])} pieces): prior {np.mean(err['prior']) * 1000:.0f} um, "
              f"after fitting the calibration pieces {np.mean(err['fit']) * 1000:.0f} um")
    failed = [m.piece_id for m in ms if m.status != "ok"]
    if failed:
        print(f"not measured: {len(failed)} ({', '.join(f.rsplit('-', 1)[-1] for f in failed)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate", help="plate JSON next to the STL you printed")
    ap.add_argument("scans", help="directory with {plate_id}-holes.png and -pins.png")
    ap.add_argument("--synthetic", type=int, metavar="SEED", help="render scans from a simulated printer first")
    ap.add_argument("--particles", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    plate, scan_dir = load_plate(a.plate), Path(a.scans)
    if a.synthetic is not None:
        synthesize(plate, scan_dir, a.synthetic)
    compare(plate, read_scans(plate, scan_dir), a.particles, a.seed)


if __name__ == "__main__":
    main()
