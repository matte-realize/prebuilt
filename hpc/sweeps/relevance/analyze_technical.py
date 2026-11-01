"""Analyze technical.jsonl: adaptive spread, subtle liars, random selection. Round 3, true-size error, paired per world.

    .venv/bin/python hpc/sweeps/relevance/analyze_technical.py hpc/sweeps/relevance/results/technical.jsonl.gz [--json out.json]
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import _open, _site_mean, gain  # noqa: E402

R = 3


def load(path):
    runs = defaultdict(dict)  # (study, world, cond, offset) -> seed -> run
    for line in _open(path):
        x = json.loads(line)
        runs[(x["study"], x["world"], x["cond"], x["offset"])][x["seed"]] = x
    return runs


def err(run, arm, r=R, site=None):
    return _site_mean(run["scores"], arm, r, site)


def paired(a_runs, a_arm, b_runs, b_arm, r=R, site=None):
    seeds = sorted(set(a_runs) & set(b_runs))
    a = np.array([err(a_runs[s], a_arm, r, site) for s in seeds])
    b = np.array([err(b_runs[s], b_arm, r, site) for s in seeds])
    return {**gain(a, b), "a_um": float(a.mean()), "b_um": float(b.mean())}


def analyze(path):
    D = load(path)
    out = {"rounds": R}
    sp = {}
    for w in ("normal", "control"):
        alone = D[("spread", w, "alone", None)]
        sp[w] = {"alone_um": float(np.mean([err(x, "isolated") for x in alone.values()]))}
        for c in ("fixed", "check", "adaptive", "both"):
            runs = D[("spread", w, c, None)]
            sp[w][c] = {"vs_alone": paired(runs, "networked", runs, "isolated"),  # same run: same worlds, same seed plate
                        "vs_fixed": paired(runs, "networked", D[("spread", w, "fixed", None)], "networked")}
    out["spread"] = sp

    li = {}
    alone = D[("spread", "normal", "alone", None)]
    for off in (0.5, 1.0, 2.0, 3.0):
        li[str(off)] = {}
        for c in ("fixed", "check", "adaptive", "both"):
            runs = D[("liar", "normal", c, off)]
            checks = [k for x in runs.values() for k in x["checks"] if k["sender"] == "pla"]
            li[str(off)][c] = {
                "resin_r1_um": float(np.mean([err(x, "networked", 1, "resin") for x in runs.values()])),
                "resin_r1_vs_alone": paired(runs, "networked", runs, "isolated", 1, "resin"),
                "resin_r3_vs_alone": paired(runs, "networked", runs, "isolated", 3, "resin"),
                "caught": sum(k["dropped"] for k in checks), "notes": len(checks)}
        li[str(off)]["resin_alone_r1_um"] = float(np.mean([err(x, "isolated", 1, "resin") for x in D[("liar", "normal", "fixed", off)].values()]))
    out["liar"] = li

    rnd, agt = D[("random", "normal", "fixed", None)], D[("spread", "normal", "fixed", None)]
    out["random"] = {
        "agents_vs_random_isolated": paired(agt, "isolated", rnd, "isolated"),
        "agents_vs_random_networked": paired(agt, "networked", rnd, "networked"),
        "random_together_vs_alone": paired(rnd, "networked", rnd, "isolated"),
        "agents_together_vs_alone": paired(agt, "networked", agt, "isolated"),
    }
    out["worlds"] = len(agt)
    return out


def fmt(g):
    return (f"{g['a_um']:5.1f} vs {g['b_um']:5.1f} µm: {g['um']:+5.2f} µm ({g['pct']:+5.1f}%, CI {g['pct_ci'][0]:+.1f}..{g['pct_ci'][1]:+.1f}), "
            f"better in {g['wins']}/{g['n']}, p={g['p']:.4f}")


if __name__ == "__main__":
    o = analyze(Path(sys.argv[1]))
    print(f"{o['worlds']} worlds, round {R}, true-size error; positive = first is better\n")
    for w, nm in (("normal", "SHARED PHYSICS"), ("control", "NOTHING SHARED (negative control)")):
        print(f"{nm}: alone {o['spread'][w]['alone_um']:.1f} µm")
        for c in ("fixed", "check", "adaptive", "both"):
            print(f"  {c:9s} together vs alone  {fmt(o['spread'][w][c]['vs_alone'])}")
        for c in ("check", "adaptive", "both"):
            print(f"  {c:9s} vs fixed           {fmt(o['spread'][w][c]['vs_fixed'])}")
    print("\nLIAR (pla, normal worlds), resin site")
    for off, d in o["liar"].items():
        print(f" offset {off} prior std (resin alone r1 {d['resin_alone_r1_um']:.1f} µm)")
        for c in ("fixed", "check", "adaptive", "both"):
            x = d[c]
            caught = f", caught {x['caught']}/{x['notes']}" if x["notes"] and c == "check" else ""
            print(f"   {c:9s} r1 {x['resin_r1_um']:6.1f} µm; r1 vs alone {x['resin_r1_vs_alone']['pct']:+6.1f}% "
                  f"({x['resin_r1_vs_alone']['wins']}/{x['resin_r1_vs_alone']['n']}); r3 vs alone {x['resin_r3_vs_alone']['pct']:+6.1f}% "
                  f"({x['resin_r3_vs_alone']['wins']}/{x['resin_r3_vs_alone']['n']}){caught}")
    print("\nRANDOM SELECTION")
    for k, g in o["random"].items():
        print(f"  {k:28s} {fmt(g)}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(o, indent=1))
