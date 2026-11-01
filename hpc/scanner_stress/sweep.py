"""Scanner stress sweep: degraded synthetic scans of the real seed plates, measured by
`measure.scanner.measure_scan` (unchanged) and by the prototype fixes in `fixes.py`.

    .venv/bin/python hpc/scanner_stress/sweep.py --reps 12 --mc 2000 --workers 15
    .venv/bin/python hpc/scanner_stress/analyze.py

One job = one scan: site x mode x defects x seed. Each scan's plate keeps the
seed-plate layout; true diameters are nominal + N(0, 0.1 mm), and one slot of
each kind is left empty (did not print) to check failure flags. Results append
to results/scans.jsonl, one line per scan, so an interrupted sweep resumes.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import sys
import time
import zlib
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from contracts import Measurement  # noqa: E402
from hpc.scanner_stress.degrade import Defects, make_scan  # noqa: E402
from hpc.scanner_stress.fixes import measure_variant  # noqa: E402
from measure.manual import apply_offsets, sample_for_caliper, scanner_offsets  # noqa: E402
from measure.scanner import measure_scan  # noqa: E402
from plates.layout import load_plate  # noqa: E402

cv2.setNumThreads(1)

OUT = Path(__file__).resolve().parent / "results"
SITES = ("resin", "pla")
MODES = ("holes", "pins")
DPIS = (300, 400, 600)
PIN_ONLY = {"shadow_mm", "shadow_dark", "rim_mm"}

# One factor at a time, everything else at the clean defaults (blur 1.2 px, noise 0.01, +-3 deg).
SINGLE = {
    "blur_px": [0.6, 1.2, 1.8, 2.4, 3.0, 4.0, 5.0],
    "noise": [0.0, 0.01, 0.02, 0.04, 0.06, 0.1],
    "grad": [0.0, 0.1, 0.2, 0.4, 0.6, 0.8],
    "radial": [0.0, 0.1, 0.2, 0.4, 0.6, 0.8],
    "shadow_mm": [0.0, 0.1, 0.2, 0.3, 0.5, 0.8],
    "shadow_dark": [0.2, 0.4, 0.6, 0.8],      # at shadow_mm 0.3
    "rim_mm": [0.0, 0.05, 0.1, 0.2, 0.3],
    "angle_deg": [0.0, 3.0, 10.0, 30.0, 45.0, 90.0, 180.0],
    "keystone": [0.0, 0.001, 0.002, 0.005, 0.01, 0.02],
    "jpeg": [0, 95, 90, 80, 70, 50, 30],
    "dust": [0, 25, 50, 100, 200, 400],
}

# Whole setups, for the scanning checklist.
TIERS = {
    "good": Defects(blur_px=1.2, noise=0.01, grad=0.1, radial=0.1, shadow_mm=0.1, dust=10),
    "typical": Defects(blur_px=1.8, noise=0.02, grad=0.3, radial=0.2, shadow_mm=0.3, dust=50, jpeg=90),
    "bad": Defects(blur_px=3.0, noise=0.04, grad=0.6, radial=0.4, shadow_mm=0.5, dust=200, jpeg=70, keystone=0.005),
}


def sample_defects(rng: np.random.Generator, dpi: float) -> Defects:
    """Random combination of every defect over plausible ranges (Monte Carlo)."""
    lu = lambda lo, hi: float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    return Defects(
        dpi=dpi, blur_px=lu(0.6, 4.0), noise=lu(0.003, 0.06), grad=rng.uniform(0, 0.6), radial=rng.uniform(0, 0.5),
        shadow_mm=rng.choice([0.0, lu(0.05, 0.6)]), shadow_dark=rng.uniform(0.2, 0.7),
        rim_mm=rng.choice([0.0, lu(0.02, 0.2)]), keystone=rng.choice([0.0, lu(0.0005, 0.01)]),
        dust=int(rng.integers(0, 200)), jpeg=int(rng.choice([0, 0, 95, 90, 80, 70])),
    )


def jobs(reps: int, mc: int) -> list[dict]:
    out = []
    def add(sweep, level, df, n, modes=MODES):
        for i in range(n):
            for site in SITES:
                for mode in modes:
                    out.append({"sweep": sweep, "level": level, "site": site, "mode": mode, "rep": i, "defects": df.as_dict()})
    for dpi in DPIS:
        for knob, levels in SINGLE.items():
            for v in levels:
                base = Defects(dpi=dpi, shadow_mm=0.3) if knob == "shadow_dark" else Defects(dpi=dpi)
                add(knob, v, replace(base, **{knob: v}), reps, ("pins",) if knob in PIN_ONLY else MODES)
        for name, df in TIERS.items():
            add(f"tier_{name}", dpi, replace(df, dpi=dpi), reps * 2)
    rng = np.random.default_rng(12345)
    for i in range(mc):
        dpi = int(rng.choice(DPIS, p=[0.25, 0.5, 0.25]))
        site, mode = SITES[i % 2], MODES[(i // 2) % 2]
        out.append({"sweep": "mc", "level": dpi, "site": site, "mode": mode, "rep": i,
                    "defects": sample_defects(rng, dpi).as_dict()})
    for j in out:
        j["key"] = f"{j['sweep']}|{j['level']}|{j['defects']['dpi']}|{j['site']}|{j['mode']}|{j['rep']}"
    return out


# Every variant includes the fiducial retry; "fid" is that fix alone.
VARIANTS = {"fid": ("area", "affine"), "edge": ("edge", "affine"),
            "area_h": ("area", "homography"), "edge_h": ("edge", "homography")}
CALIPER = ("base", "fid", "edge_h")  # also scored after the caliper offset


def run_job(job: dict) -> dict:
    rng = np.random.default_rng(zlib.crc32(job["key"].encode()))
    site, mode = job["site"], job["mode"]
    plate = load_plate(str(ROOT / "plates" / "out" / site / f"{site}-seed.json"))
    kind = {"holes": "hole", "pins": "pin"}[mode]
    true = {p.piece_id: p.nominal_d + rng.normal(0, 0.1) for p in plate.pieces}
    for k in ("pin", "hole"):  # one empty slot per kind
        ps = [p for p in plate.pieces if p.kind == k]
        true[ps[int(rng.integers(len(ps)))].piece_id] = 0.0
    t0 = time.time()
    img = make_scan(plate, true, mode, Defects(**job["defects"]), seed=int(rng.integers(2**31)))
    res: dict[str, list | str] = {}

    def record(name, fn):
        try:
            ms = fn()
        except Exception as e:  # fiducials not found etc.: every piece in the scan failed
            res[name] = f"error: {type(e).__name__}: {e}"[:200]
            return None
        res[name] = [None if m.measured_d is None else round((m.measured_d - true[m.piece_id]) * 1000, 2) for m in ms]
        return ms

    base = record("base", lambda: measure_scan(img, plate, mode)[0])
    fixed = {v: record(v, lambda c=c, m=m: measure_variant(img, plate, mode, c, m)) for v, (c, m) in VARIANTS.items()}
    # Caliper spot checks as on the day (~10 per plate, about half of this kind), 10 um caliper noise.
    slots = set(sample_for_caliper(plate, k=10, seed=int(rng.integers(2**31))))
    checks = [Measurement(p.piece_id, plate.plate_id, site, true[p.piece_id] + rng.normal(0, 0.01), "ok", "caliper")
              for p in plate.pieces if p.slot in slots and true[p.piece_id] > 0]
    for name, ms in ((f"{v}_cal", base if v == "base" else fixed[v]) for v in CALIPER):
        if ms is None:
            res[name] = res[name.removesuffix("_cal")]
        else:
            record(name, lambda ms=ms: apply_offsets(ms, scanner_offsets(ms, checks, plate), plate))
    pieces = [p for p in plate.pieces if p.kind == kind]
    return {**job, "seconds": round(time.time() - t0, 2),
            "nominal": [p.nominal_d for p in pieces], "empty": [true[p.piece_id] == 0 for p in pieces], **res}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--mc", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--only", default=None, help="run only jobs whose sweep name starts with this")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    path = OUT / "scans.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["key"] for line in path.open()}
    todo = [j for j in jobs(a.reps, a.mc) if j["key"] not in done and (a.only is None or j["sweep"].startswith(a.only))]
    # big scans first so the pool drains evenly
    todo.sort(key=lambda j: -j["defects"]["dpi"])
    print(f"{len(todo)} scans to run ({len(done)} done), {a.workers} workers", flush=True)
    t0 = time.time()
    with Pool(a.workers) as pool, path.open("a") as f:
        for n, row in enumerate(pool.imap_unordered(run_job, todo, chunksize=2), 1):
            f.write(json.dumps(row) + "\n")
            if n % 200 == 0 or n == len(todo):
                f.flush()
                print(f"{n}/{len(todo)}  {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
