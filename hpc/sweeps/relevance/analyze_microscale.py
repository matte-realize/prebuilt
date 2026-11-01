"""Analyze microscale.jsonl: networked vs isolated, round 3, true-size error, paired per world.

    .venv/bin/python hpc/sweeps/relevance/analyze_microscale.py hpc/sweeps/relevance/results/microscale.jsonl.gz [--json out.json]
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import _open, gain  # noqa: E402

R = 3


def _mean(scores, arm, key, scale=1.0):
    v = [x[key] for x in scores if x["arm"] == arm and x["round"] == R and x.get(key) is not None]
    return scale * float(np.mean(v)) if v else None


def analyze(path):
    runs, errors = defaultdict(dict), []
    for line in _open(path):
        x = json.loads(line)
        if "error" in x:
            errors.append(x)
            continue
        runs[(x["pair"], x["plate"], x["printer"])][x["seed"]] = x
    out = {"rounds": R, "errors": len(errors), "conditions": {}}
    for (pair, plate, printer), by in sorted(runs.items()):
        # A world counts only if both arms scored at least one printed held-out piece at every site.
        seeds = [s for s, x in sorted(by.items())
                 if _mean(x["scores"], "isolated", "mae_truth") is not None
                 and all(r.get("mae_truth") is not None for r in x["scores"] if r["round"] == R)]
        iso = np.array([_mean(by[s]["scores"], "isolated", "mae_truth", 1000) for s in seeds])
        net = np.array([_mean(by[s]["scores"], "networked", "mae_truth", 1000) for s in seeds])
        ora = np.array([_mean(by[s]["scores"], "oracle", "mae_truth", 1000) for s in seeds])
        allrows = [r for x in by.values() for r in x["scores"] if r["round"] == R and r["arm"] == "isolated"]
        failed = sum(r["n_heldout_failed"] for r in allrows) / max(1, sum(r["n_heldout_failed"] + r["n_heldout"] for r in allrows))
        c = {"worlds_run": len(by), "worlds_scored": len(seeds), "heldout_failed_frac": failed}
        if len(seeds) >= 5:
            c.update({
                "isolated_um": float(iso.mean()), "networked_um": float(net.mean()), "oracle_um": float(ora.mean()),
                "isolated_rel_pct": 100 * float(np.mean([_mean(by[s]["scores"], "isolated", "rel_truth") for s in seeds])),
                "networked_rel_pct": 100 * float(np.mean([_mean(by[s]["scores"], "networked", "rel_truth") for s in seeds])),
                "mean_heldout_d_mm": float(np.mean([_mean(by[s]["scores"], "isolated", "mean_d") for s in seeds])),
                "net_vs_iso": gain(net, iso), "oracle_vs_iso": gain(ora, iso)})
        out["conditions"][f"{pair}/{plate}/{printer}"] = c
    return out


if __name__ == "__main__":
    o = analyze(Path(sys.argv[1]))
    print(f"round {R}, true-size error on held-out pieces that printed; gain = networked better than isolated (median, paired)\n")
    for k, c in o["conditions"].items():
        print(f"{k:28s} worlds {c['worlds_scored']}/{c['worlds_run']}, held-out failed {100 * c['heldout_failed_frac']:.0f}%")
        if "net_vs_iso" in c:
            g = c["net_vs_iso"]
            print(f"   iso {c['isolated_um']:5.1f}  net {c['networked_um']:5.1f}  oracle {c['oracle_um']:5.1f} µm   "
                  f"rel iso {c['isolated_rel_pct']:.2f}% net {c['networked_rel_pct']:.2f}% of size (mean held-out d {c['mean_heldout_d_mm']:.2f} mm)")
            print(f"   net vs iso {g['um']:+.2f} µm ({g['pct']:+.1f}%, CI {g['pct_ci'][0]:+.1f}..{g['pct_ci'][1]:+.1f}), "
                  f"better in {g['wins']}/{g['n']}, p={g['p']:.4f}; oracle vs iso {c['oracle_vs_iso']['pct']:+.1f}%")
    if o["errors"]:
        print(f"\n{o['errors']} runs errored")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(o, indent=1))
