"""Analyze consistency.jsonl: does quarantining inconsistent notes stop the liar without costing honest sharing?

    .venv/bin/python hpc/sweeps/relevance/analyze_consistency.py hpc/sweeps/relevance/results/consistency.jsonl
"""
import gzip, json, math, sys
from collections import defaultdict
import numpy as np

def _open(path):
    """Results are committed gzipped (*.jsonl.gz); plain .jsonl works too."""
    path = str(path)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


runs = [json.loads(l) for l in _open(sys.argv[1])]
R = max(s["round"] for s in runs[0]["scores"])
by = defaultdict(dict)
for r in runs:
    by[(r["cond"], r["check"])][r["seed"]] = r
seeds = sorted(by[("normal", False)])


def sign_p(w, n):
    if n == 0: return 1.0
    k = min(w, n - w); return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def err(key, arm, r, site=None):
    return np.array([1000 * np.mean([s["mae_truth"] for s in by[key][sd]["scores"]
                                     if s["arm"] == arm and s["round"] == r and (site is None or s["site"] == site)]) for sd in seeds])


print(f"{len(seeds)} worlds, {R} rounds, true-size error (µm), networked arm, median over worlds\n")
print(f"{'condition':28s} " + " ".join(f"round {r:d}" for r in range(1, R + 1)))
for key, nm in ((("alone", False), "no notes"), (("normal", False), "honest notes"), (("normal", True), "honest notes + check"),
                (("liar", False), "liar, no check"), (("liar", True), "liar + check")):
    print(f"{nm:28s} " + " ".join(f"{np.median(err(key, 'networked', r)):7.1f}" for r in range(1, R + 1)))
print("\nResin (the site receiving the liar's notes), round 1:")
for key, nm in ((("alone", False), "no notes"), (("liar", False), "liar, no check"), (("liar", True), "liar + check")):
    print(f"  {nm:20s} {np.median(err(key, 'networked', 1, 'resin')):6.1f} µm")


def paired(a, b, label):
    d = b - a; w = int((d > 0).sum())
    print(f"  {label:46s} median {np.median(d):+6.2f} µm, better in {w}/{len(d)}, p={sign_p(w, int((d != 0).sum())):.3f}")


print("\nPaired per world (positive = first is better):")
for r in (1, R):
    print(f" round {r}:")
    paired(err(("liar", True), "networked", r), err(("liar", False), "networked", r), "liar: check vs no check")
    paired(err(("liar", True), "networked", r), err(("alone", False), "networked", r), "liar + check vs no notes")
    paired(err(("normal", True), "networked", r), err(("normal", False), "networked", r), "honest: check vs no check (cost of the check)")
    paired(err(("normal", True), "networked", r), err(("normal", True), "isolated", r), "honest + check: together vs alone")

chk = [c for sd in seeds for c in by[("normal", True)][sd]["checks"]]
liar = [c for sd in seeds for c in by[("liar", True)][sd]["checks"] if c["sender"] == "pla"]
hon_in_liar = [c for sd in seeds for c in by[("liar", True)][sd]["checks"] if c["sender"] != "pla"]
print(f"\nHonest notes wrongly dropped: {sum(c['dropped'] for c in chk)} of {len(chk)} (honest run), "
      f"{sum(c['dropped'] for c in hon_in_liar)} of {len(hon_in_liar)} (honest site's notes in the liar run)")
print(f"Liar's notes caught: {sum(c['dropped'] for c in liar)} of {len(liar)}; "
      f"honest chi2 median {np.median([c['chi2'] for c in chk]):.2f} (99th pct {np.percentile([c['chi2'] for c in chk], 99):.1f}), "
      f"liar chi2 min {min(c['chi2'] for c in liar):.0f}; threshold 16.3")
