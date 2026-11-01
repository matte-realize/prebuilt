import gzip, json, math, sys
from collections import defaultdict
import numpy as np

def _open(path):
    """Results are committed gzipped (*.jsonl.gz); plain .jsonl works too."""
    path = str(path)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


rows = [json.loads(l) for l in _open(sys.argv[1])]
R = max(s["round"] for s in rows[0]["scores"])


def sign_p(w, n):
    if n == 0: return 1.0
    k = min(w, n - w); return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def curves(run, metric):
    acc = defaultdict(lambda: defaultdict(list))
    for s in run["scores"]:
        acc[s["arm"]][s["round"]].append(s[metric])
    return {a: np.array([np.mean(b[r]) for r in range(1, R + 1)]) * 1000 for a, b in acc.items()}


C = defaultdict(dict)  # C[(cell, cond)][seed] = run
for r in rows:
    C[(r["cell"], r["cond"])][r["seed"]] = r
cells = list(dict.fromkeys(r["cell"] for r in rows))


def paired(a, b):
    d = b - a; pct = d / b * 100; w = int((d > 0).sum())
    return np.median(d), np.median(pct), w, len(d), sign_p(w, int((d != 0).sum()))


def fitacc(runs, cond_arm_rounds):
    ok = tot = 0
    for run in runs:
        for f in run["fit"]:
            if f["arm"] == cond_arm_rounds[0] and f["round"] in cond_arm_rounds[1] and f["fit_pairs"]:
                ok += f["fit_acc"] * f["fit_pairs"]; tot += f["fit_pairs"]
    return ok / tot if tot else float("nan"), tot


print(f"{R} rounds, error vs true size (µm), median over worlds. 'together' = team with notes; gains are paired per world.\n")
hdr = f"{'regime':32s} {'rnd':>3s} {'alone':>6s} {'togeth':>6s} {'gain µm':>7s} {'gain %':>6s} {'wins':>6s} {'p':>6s} | {'notes µm':>8s} {'notes %':>7s} {'wins':>6s} {'p':>6s} | {'meas %':>6s}"
print(hdr); print("-" * len(hdr))
for cell in cells:
    if (cell, "alone") not in C: continue
    seeds = sorted(set(C[(cell, "normal")]) & set(C[(cell, "alone")]))
    for rnd in (1, 3, R):
        i = rnd - 1
        get = lambda cond, arm, m="mae_truth": np.array([curves(C[(cell, cond)][s], m)[arm][i] for s in seeds])
        iso, net, na = get("normal", "isolated"), get("normal", "networked"), get("alone", "networked")
        g = paired(net, iso); n = paired(net, na)
        meas = paired(get("normal", "networked", "mae"), get("normal", "isolated", "mae"))
        print(f"{cell if rnd == 1 else '':32s} {rnd:3d} {np.median(iso):6.1f} {np.median(net):6.1f} {g[0]:7.2f} {g[1]:6.1f} {g[2]:3d}/{g[3]:<2d} {g[4]:6.3f} | {n[0]:8.2f} {n[1]:7.1f} {n[2]:3d}/{n[3]:<2d} {n[4]:6.3f} | {meas[1]:6.1f}")
    print()

print("Fit calls (pin-in-hole class vs true clearance), pooled over worlds, rounds 1-%d:" % R)
for cell in cells:
    if (cell, "alone") not in C: continue
    a, na_ = fitacc(C[(cell, "normal")].values(), ("isolated", range(1, R + 1)))
    t, nt = fitacc(C[(cell, "normal")].values(), ("networked", range(1, R + 1)))
    o, no = fitacc(C[(cell, "normal")].values(), ("oracle", range(1, R + 1)))
    print(f"  {cell:32s} wrong calls per 100: alone {100 * (1 - a):4.1f}  together {100 * (1 - t):4.1f}  pooled {100 * (1 - o):4.1f}   ({nt} pairs)")

print("\nTrust start (warm-up 16, 6/round, 2 sites):")
base = "2 sites, warm-up 16, 6/round"
def team(cell, cond, rnd):
    return np.array([curves(run, "mae_truth")["networked"][rnd - 1] for _, run in sorted(C[(cell, cond)].items())])
for rnd in (1, 2, R):
    l1, l3 = team("trust 1.0", "liar", rnd), team("trust 0.3", "liar", rnd)
    h1, h3 = team(base, "normal", rnd), team("trust 0.3", "normal", rnd)
    alone = team(base, "alone", rnd)
    print(f"  round {rnd}: with a liar, trust 1.0 -> {np.median(l1):5.1f} µm, trust 0.3 -> {np.median(l3):5.1f} µm | honest notes, trust 1.0 -> {np.median(h1):5.1f}, trust 0.3 -> {np.median(h3):5.1f} | no notes {np.median(alone):5.1f}")
