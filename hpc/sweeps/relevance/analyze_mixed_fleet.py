"""Analyze mixed_fleet.jsonl: matched vs unmatched sites, round 3, true-size error, paired per world.

Together vs alone is paired within each run (same world, same seed plate), as in section 8.
Trust: the adaptive-spread multiplier a receiver applies to a sender after round 3,
max(1, mean z^2 over rounds), grouped by (receiver group <- sender group).

    .venv/bin/python hpc/sweeps/relevance/analyze_mixed_fleet.py hpc/sweeps/relevance/results/mixed_fleet.jsonl.gz [--json out.json]
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import _open, gain  # noqa: E402

R = 3
CONDS = ("fixed", "check", "adaptive", "both")


def err(run, arm, sites, r=R):
    return 1000 * float(np.mean([x["mae_truth"] for x in run["scores"] if x["arm"] == arm and x["round"] == r
                                 and x["site"] in sites and x["mae_truth"] is not None]))


def paired(a_runs, a_arm, b_runs, b_arm, sites):
    seeds = sorted(set(a_runs) & set(b_runs))
    a = np.array([err(a_runs[s], a_arm, sites) for s in seeds])
    b = np.array([err(b_runs[s], b_arm, sites) for s in seeds])
    return {**gain(a, b), "a_um": float(a.mean()), "b_um": float(b.mean())}


def analyze(path):
    D = defaultdict(lambda: defaultdict(dict))  # n -> cond -> seed -> run
    for line in _open(path):
        x = json.loads(line)
        D[x["n"]][x["cond"]][x["seed"]] = x
    out = {}
    for n, by in sorted(D.items()):
        any_run = next(iter(by["fixed"].values()))
        un = set(any_run["unmatched"])
        allsites = {x["site"] for x in any_run["scores"]}
        groups = {"matched": allsites - un, "unmatched": un}
        o = {"worlds": len(by["fixed"]), "groups": {g: sorted(s) for g, s in groups.items()}}
        for g, sites in groups.items():
            o[g] = {"alone_um": float(np.mean([err(x, "isolated", sites) for x in by["alone"].values()]))}
            for c in CONDS:
                o[g][c] = {"vs_alone": paired(by[c], "networked", by[c], "isolated", sites),
                           "vs_fixed": paired(by[c], "networked", by["fixed"], "networked", sites)}
        gof = lambda s: "unmatched" if s in un else "matched"
        for c in ("adaptive", "both"):
            mult = defaultdict(list)
            for run in by[c].values():
                for key, v in run["disagree"].items():
                    o_, s_ = key.split("<")
                    mult[f"{gof(o_)}<{gof(s_)}"].append(max(1.0, float(np.mean(v))))
            o[f"spread_{c}"] = {k: {"mean": float(np.mean(v)), "median": float(np.median(v)),
                                    "frac_above_2": float(np.mean(np.array(v) > 2)), "n": len(v)}
                                for k, v in sorted(mult.items())}
        for c in ("check", "both"):
            drops = defaultdict(lambda: [0, 0])
            for run in by[c].values():
                for k in run["checks"]:
                    d = drops[f"{gof(k['receiver'])}<{gof(k['sender'])}"]
                    d[0] += k["dropped"]; d[1] += 1
            o[f"drops_{c}"] = {k: {"dropped": v[0], "notes": v[1]} for k, v in sorted(drops.items())}
        out[str(n)] = o
    return out


def fmt(g):
    return (f"{g['a_um']:5.1f} vs {g['b_um']:5.1f} µm: {g['pct']:+5.1f}% (CI {g['pct_ci'][0]:+.1f}..{g['pct_ci'][1]:+.1f}), "
            f"better in {g['wins']}/{g['n']}, p={g['p']:.4f}")


if __name__ == "__main__":
    O = analyze(Path(sys.argv[1]))
    for n, o in O.items():
        print(f"\n== {n} sites, {o['worlds']} worlds, round {R}; matched {o['groups']['matched']}, unmatched {o['groups']['unmatched']}")
        for g in ("matched", "unmatched"):
            print(f" {g.upper()} sites: alone {o[g]['alone_um']:.1f} µm")
            for c in CONDS:
                print(f"   {c:9s} together vs alone {fmt(o[g][c]['vs_alone'])}")
            for c in CONDS[1:]:
                print(f"   {c:9s} vs fixed          {fmt(o[g][c]['vs_fixed'])}")
        for c in ("adaptive", "both"):
            print(f" spread multiplier after round 3 ({c}), receiver<sender:")
            for k, v in o[f"spread_{c}"].items():
                print(f"   {k:20s} mean {v['mean']:5.2f}, median {v['median']:5.2f}, >2x in {100 * v['frac_above_2']:4.0f}% of {v['n']}")
        for c in ("check", "both"):
            print(f" consistency-check drops ({c}): " + ", ".join(f"{k} {v['dropped']}/{v['notes']}" for k, v in o[f"drops_{c}"].items()))
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(O, indent=1))
