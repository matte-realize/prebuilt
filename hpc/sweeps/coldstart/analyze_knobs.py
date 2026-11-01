"""Each knob cell vs the same-size baseline cell from the grid, paired by world.

    .venv/bin/python hpc/sweeps/coldstart/analyze_knobs.py GRID.jsonl KNOBS.jsonl

'net gain' = isolated - networked as % of isolated, inside the knob runs.
'vs base' = baseline networked - knob networked, um (positive = the knob helps), and the
number of worlds where the knob's networked error is lower.
"""
import json
import sys
from collections import defaultdict

import numpy as np

from analyze import sign_p

ROUNDS = (1, 3, 5)


def load(path):
    out = {}
    for line in open(path):
        d = json.loads(line)
        acc = defaultdict(list)
        for s in d["scores"]:
            if s["mae_truth"] is not None:
                acc[(s["round"], s["arm"])].append(s["mae_truth"] * 1000)
        out[(json.dumps(d["cell"], sort_keys=True), d["seed"])] = {k: np.mean(v) for k, v in acc.items()}
    return out


def main(grid, knobs):
    g, k = load(grid), load(knobs)
    cells = sorted({c for c, _ in k}, key=lambda c: (json.loads(c)["n"], c))
    print("| knob | round | worlds | net gain (knob) | net gain (base, same worlds) | vs base | knob better |")
    print("|---|---|---|---|---|---|---|")
    for c in cells:
        cell = json.loads(c)
        base = json.dumps({x: cell[x] for x in ("n", "seed_pieces", "slots")}, sort_keys=True)
        seeds = sorted(s for cc, s in k if cc == c and (base, s) in g)
        knob = {x: v for x, v in cell.items() if x not in ("n", "seed_pieces", "slots")}
        for r in ROUNDS:
            kn = np.array([k[(c, s)][(r, "networked")] for s in seeds])
            ki = np.array([k[(c, s)][(r, "isolated")] for s in seeds])
            bn = np.array([g[(base, s)][(r, "networked")] for s in seeds])
            bi = np.array([g[(base, s)][(r, "isolated")] for s in seeds])
            wins = int(np.sum(kn < bn))
            print(f"| {cell['n']} sites, {knob} | {r} | {len(seeds)} | {100 * np.mean(ki - kn) / ki.mean():.1f}% | "
                  f"{100 * np.mean(bi - bn) / bi.mean():.1f}% | {np.mean(bn - kn):+.2f} | {wins}/{len(seeds)} (p={sign_p(wins, len(seeds)):.2f}) |")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
