"""Does it matter? Analyze worlds.jsonl (100 worlds x {normal, alone, liar} x 8 rounds)."""
import gzip, json, math, sys
from collections import defaultdict
import numpy as np

def _open(path):
    """Results are committed gzipped (*.jsonl.gz); plain .jsonl works too."""
    path = str(path)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


rows = [json.loads(l) for l in _open(sys.argv[1])]
rng = np.random.default_rng(0)
R = max(s["round"] for s in rows[0]["scores"])
SEEDS = sorted({r["seed"] for r in rows})

# curve[cond][seed][arm][metric] -> array over rounds 1..R, averaged over the two sites
curve = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
trust = defaultdict(dict)
for run in rows:
    acc = defaultdict(lambda: defaultdict(list))
    for s in run["scores"]:
        for m in ("mae", "mae_truth", "lpd", "cov90"):
            acc[(s["arm"], m)][s["round"]].append(s[m])
    for (arm, m), byr in acc.items():
        curve[run["cond"]][run["seed"]][arm][m] = np.array([np.mean(byr[r]) for r in range(1, R + 1)]) * (1000 if m.startswith("mae") else 1)
    trust[run["cond"]][run["seed"]] = run["trust"]


def sign_p(wins, n):
    """Exact two-sided sign test."""
    if n == 0:
        return 1.0
    k = min(wins, n - wins)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot_ci(x, f=np.median, b=4000):
    x = np.asarray(x)
    s = [f(rng.choice(x, len(x))) for _ in range(b)]
    return np.percentile(s, [2.5, 97.5])


def compare(a, b, label):
    """Paired over worlds: % by which a's error is lower than b's (positive = a better)."""
    pct = (b - a) / b * 100
    wins, n = int((pct > 0).sum()), int((pct != 0).sum())
    lo, hi = boot_ci(pct)
    print(f"  {label:44s} median {np.median(pct):5.1f}%  95% CI [{lo:5.1f}, {hi:5.1f}]  better in {wins}/{len(pct)}  sign-test p={sign_p(wins, n):.3f}")
    return pct


def rounds_to(target, c):
    hit = np.nonzero(c <= target)[0]
    return hit[0] + 1 if len(hit) else R + 1  # R+1 = not reached within R rounds


M = "mae_truth"
print(f"{len(SEEDS)} worlds, {R} rounds, metric = held-out error vs true size (µm), averaged over both printers\n")

print("Median learning curves (µm), sharing notes condition:")
print("  round " + " ".join(f"{r:6d}" for r in range(1, R + 1)))
for arm in ("isolated", "networked", "oracle"):
    med = np.median([curve["normal"][s][arm][M] for s in SEEDS], axis=0)
    print(f"  {arm:9s}" + " ".join(f"{v:6.1f}" for v in med))
med = np.median([curve["alone"][s]["networked"][M] for s in SEEDS], axis=0)
print(f"  {'team, no notes':9s}" + " ".join(f"{v:6.1f}" for v in med))
med = np.median([curve["liar"][s]["networked"][M] for s in SEEDS], axis=0)
print(f"  {'team, liar':9s}" + " ".join(f"{v:6.1f}" for v in med))

for r in (3, R):
    i = r - 1
    print(f"\nAt round {r}:")
    g = lambda c, arm: np.array([curve[c][s][arm][M][i] for s in SEEDS])
    compare(g("normal", "oracle"), g("normal", "isolated"), "CEILING: pooled raw data vs alone")
    compare(g("normal", "networked"), g("normal", "isolated"), "A. together (with notes) vs alone")
    compare(g("normal", "networked"), g("alone", "networked"), "B. notes vs no notes (same team)")
    compare(g("alone", "networked"), g("alone", "isolated"), "C. team without notes vs alone")
    compare(g("liar", "networked"), g("alone", "networked"), "D. liar present vs no notes (harm?)")
    compare(g("liar", "networked"), g("normal", "networked"), "E. liar present vs honest notes")

print(f"\nMeasured error (includes scanner noise), round {R}:")
g = lambda c, arm: np.array([curve[c][s][arm]["mae"][R - 1] for s in SEEDS])
compare(g("normal", "networked"), g("normal", "isolated"), "together vs alone, measured")
compare(g("normal", "networked"), g("alone", "networked"), "notes vs no notes, measured")
print("  scanner-noise floor: median measured error alone at round %d = %.1f µm vs true-size error %.1f µm"
      % (R, np.median(g("normal", "isolated")), np.median([curve["normal"][s]["isolated"][M][R - 1] for s in SEEDS])))

print("\nTest prints to reach a target accuracy (6 test parts per approach per round):")
for k in (3, 5, R):
    for tag, base_c, base_arm, new_c, new_arm in [("together vs alone", "normal", "isolated", "normal", "networked"),
                                                  ("notes vs no notes", "alone", "networked", "normal", "networked")]:
        rb, rn = [], []
        for s in SEEDS:
            target = curve[base_c][s][base_arm][M][k - 1]
            rb.append(rounds_to(target, curve[base_c][s][base_arm][M]))
            rn.append(rounds_to(target, curve[new_c][s][new_arm][M]))
        rb, rn = np.array(rb), np.array(rn)
        saved = rb - rn
        print(f"  target = baseline's round-{k} accuracy, {tag:18s}: baseline needs {np.median(rb):.0f} rounds (median), "
              f"new {np.median(rn):.0f}; mean rounds saved {saved.mean():+.2f} ({saved.mean() * 6:+.1f} parts); "
              f"faster in {(saved > 0).sum()}, slower in {(saved < 0).sum()}, never reached in {(rn > R).sum()} worlds")

print("\nTrust in the liar (resin listening to pla), median over worlds:")
for c in ("normal", "liar"):
    by = defaultdict(list)
    for s in SEEDS:
        for t in trust[c][s]:
            if t["receiver"] == "resin" and t["sender"] == "pla":
                by[t["round"]].append(t["trust"])
    print(f"  {c:6s} " + " ".join(f"r{r}:{np.median(v):.2f}" for r, v in sorted(by.items())))

print(f"\nCalibration (share of test parts inside the 90% range), round {R}, median:")
for c, arm in (("normal", "isolated"), ("normal", "networked"), ("normal", "oracle")):
    print(f"  {arm:9s} {np.median([curve[c][s][arm]['cov90'][R - 1] for s in SEEDS]) * 100:.0f}%")

print("\nAbsolute gains (µm of true-size error), median over worlds:")
for r in (1, 3, R):
    i = r - 1
    iso = np.array([curve["normal"][s]["isolated"][M][i] for s in SEEDS]); net = np.array([curve["normal"][s]["networked"][M][i] for s in SEEDS])
    na = np.array([curve["alone"][s]["networked"][M][i] for s in SEEDS])
    print(f"  round {r}: alone {np.median(iso):.1f}  together {np.median(net):.1f}  -> together saves {np.median(iso - net):.1f} µm; notes save {np.median(na - net):.1f} µm vs the same team without notes")
lr = np.array([curve["liar"][s]["networked"][M][0] for s in SEEDS]); nr = np.array([curve["alone"][s]["networked"][M][0] for s in SEEDS])
print(f"  liar, round 1 (before trust drops): team error {np.median(lr):.1f} µm vs {np.median(nr):.1f} with no notes; worse in {(lr > nr).sum()}/100 worlds")
