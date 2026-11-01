"""Summarize ceiling.py output: per cell and round, mean error per arm and paired gains.

    .venv/bin/python hpc/sweeps/coldstart/analyze.py OUT.jsonl [ROUNDS e.g. 1,3,5,8]

Errors are mae_truth in um, averaged over sites per world. 'gain' = isolated - arm, as a
percentage of isolated; 'of avail' = (isolated - networked) / (isolated - known_shared);
'wins' = worlds where networked < isolated.
"""
import json
import sys
from collections import defaultdict
from math import comb

import numpy as np


def sign_p(k, n):
    if n == 0:
        return 1.0
    t = min(k, n - k)
    return min(1.0, 2 * sum(comb(n, i) for i in range(t + 1)) / 2**n)


def main(path, rounds):
    by = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # cell -> round -> arm -> [world means]
    for line in open(path):
        d = json.loads(line)
        cell = json.dumps(d["cell"], sort_keys=True)
        acc = defaultdict(list)
        for s in d["scores"]:
            if s["mae_truth"] is not None:
                acc[(s["round"], s["arm"])].append(s["mae_truth"] * 1000)
        for (r, arm), v in acc.items():
            by[cell][r][arm].append((d["seed"], np.mean(v)))
    print("| cell | round | worlds | isolated | networked | oracle | known_shared | true θ | net gain | oracle gain | avail gain | of avail | wins |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cell in sorted(by, key=lambda c: (json.loads(c)["n"], json.loads(c)["seed_pieces"], json.loads(c)["slots"], c)):
        for r in rounds:
            if r not in by[cell]:
                continue
            arms = {a: dict(v) for a, v in by[cell][r].items()}
            seeds = sorted(set.intersection(*(set(v) for v in arms.values())))
            m = {a: np.array([arms[a][s] for s in seeds]) for a in arms}
            iso = m["isolated"]
            g = lambda a: 100 * np.mean(iso - m[a]) / np.mean(iso)
            wins = int(np.sum(m["networked"] < iso))
            avail = np.mean(iso - m["known_shared"])
            of = 100 * np.mean(iso - m["networked"]) / avail if avail > 0 else float("nan")
            c = json.loads(cell)
            label = f"{c.pop('n')} sites, seed {c.pop('seed_pieces')}, {c.pop('slots')}/rd" + (" " + str(c) if c else "")
            print(f"| {label} | {r} | {len(seeds)} | {iso.mean():.1f} | {m['networked'].mean():.1f} | {m['oracle'].mean():.1f} | "
                  f"{m['known_shared'].mean():.1f} | {m['true_theta'].mean():.1f} | {g('networked'):.1f}% | {g('oracle'):.1f}% | "
                  f"{g('known_shared'):.1f}% | {of:.0f}% | {wins}/{len(seeds)} (p={sign_p(wins, len(seeds)):.3f}) |")


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,3,5,8").split(",")])
