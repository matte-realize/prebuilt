"""Fit the model-discrepancy term and check interval coverage on held-out worlds.

Per (site, kind) on worlds 0-29 vs 30-59 for the detail; then one pooled term: two-fold
cross-validation (fit on one half, cover the other, both ways) for the honest range, and the
value fitted on all worlds, which is what model/compensate.py uses.

    .venv/bin/python hpc/sweeps/relevance/analyze_compensate_calibration.py hpc/sweeps/relevance/results/compensate_calibration.jsonl.gz [--json out.json]
"""
import json, os, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import _open  # noqa: E402

Z = 1.6449  # two-sided 90%
SPLIT = 30


def covered(rows, delta):
    r = np.array([x["true"] - x["pred"] for x in rows])
    sd = np.sqrt(np.array([x["model_sd"] for x in rows]) ** 2 + delta ** 2)
    return float(np.mean(np.abs(r) <= Z * sd))


def fit_delta(rows, target=0.90):
    lo, hi = 0.0, 0.2
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if covered(rows, mid) < target else (lo, mid)
    return hi


if __name__ == "__main__":
    rows = [json.loads(l) for l in _open(Path(sys.argv[1]))]
    groups = sorted({(x["site"], x["kind"]) for x in rows})
    out = {"split": SPLIT, "groups": {}}
    cal_all = [x for x in rows if x["seed"] < SPLIT]; test_all = [x for x in rows if x["seed"] >= SPLIT]
    print(f"{len(rows)} rows; calibrate on worlds <{SPLIT} ({len(cal_all)}), test on the rest ({len(test_all)})")
    test_before, test_after = [], []
    for g in groups:
        cal = [x for x in cal_all if (x["site"], x["kind"]) == g]
        test = [x for x in test_all if (x["site"], x["kind"]) == g]
        d = fit_delta(cal)
        res = np.array([x["true"] - x["pred"] for x in test])
        o = {"delta_mm": d, "test_n": len(test), "test_cover_before": covered(test, 0), "test_cover_after": covered(test, d),
             "test_bias_um": float(res.mean() * 1e3), "test_resid_sd_um": float(res.std() * 1e3),
             "model_sd_um_median": float(np.median([x["model_sd"] for x in test]) * 1e3),
             "half_width_um_median_after": float(np.median([Z * np.hypot(x["model_sd"], d) for x in test]) * 1e3)}
        out["groups"]["/".join(g)] = o
        test_before += [(x, 0) for x in test]; test_after += [(x, d) for x in test]
        print(f"{g[0]:5s} {g[1]:4s} delta {d*1e3:5.1f} µm | test cover {o['test_cover_before']:.0%} -> {o['test_cover_after']:.0%} | "
              f"bias {o['test_bias_um']:+5.1f} µm, resid sd {o['test_resid_sd_um']:4.1f}, model sd {o['model_sd_um_median']:4.1f} | "
              f"90% half-width {o['half_width_um_median_after']:.0f} µm")
    cb = np.mean([covered([x], d) for x, d in test_before]); ca = np.mean([covered([x], d) for x, d in test_after])
    out["test_cover_before"], out["test_cover_after"] = float(cb), float(ca)
    halves = (cal_all, test_all)
    cv = [covered(halves[1 - i], fit_delta(halves[i])) for i in (0, 1)]
    d_all = fit_delta(rows)
    out["pooled"] = {"delta_mm": d_all, "cv_cover": cv, "cover_before_all": covered(rows, 0)}
    print(f"POOLED: two-fold cross-validated cover {cv[0]:.0%} and {cv[1]:.0%} (mean {np.mean(cv):.0%}); "
          f"fitted on all {len(rows) // 16} worlds: delta {d_all*1e3:.1f} µm (cover before {covered(rows, 0):.0%})")
    corr = np.array([abs(x["true"] - x["target"]) for x in test_all]); raw = np.array([abs(x["as_is"] - x["target"]) for x in test_all])
    out["test_median_err_um"] = {"as_is": float(np.median(raw) * 1e3), "corrected": float(np.median(corr) * 1e3)}
    print(f"ALL test cover {cb:.0%} -> {ca:.0%}; median |true - target| as-is {np.median(raw)*1e3:.0f} µm, corrected {np.median(corr)*1e3:.0f} µm")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(out, indent=1))
