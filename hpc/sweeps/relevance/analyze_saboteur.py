"""Analyze saboteur.jsonl: does learned credibility cut off a bad agent?

    .venv/bin/python hpc/sweeps/relevance/analyze_saboteur.py hpc/sweeps/relevance/results/saboteur.jsonl
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


def sign_p(w, n):
    if n == 0: return 1.0
    k = min(w, n - w); return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def err(run, arm, r):
    return 1000 * np.mean([s["mae_truth"] for s in run["scores"] if s["arm"] == arm and s["round"] == r])


by = defaultdict(dict)
for run in runs:
    by[(run["sab"], run["share"])][run["seed"]] = run
seeds = sorted(by[(False, False)])

print(f"{len(seeds)} worlds, {R} rounds, true-size error (µm). Isolated = equal votes; networked = learned credibility.\n")
for share in (False, True):
    print(f"messages {'ON' if share else 'cut'}:")
    for r in (1, 3, R):
        line = f"  round {r}:"
        for sab in (False, True):
            iso = np.array([err(by[(sab, share)][s], "isolated", r) for s in seeds])
            net = np.array([err(by[(sab, share)][s], "networked", r) for s in seeds])
            d = iso - net; w = int((d > 0).sum())
            line += f"   {'saboteur' if sab else 'honest  '}: equal votes {np.median(iso):5.1f}, learned {np.median(net):5.1f}, learned better by {np.median(d):5.2f} µm ({np.median(d / iso * 100):4.1f}%) in {w}/{len(d)}, p={sign_p(w, int((d != 0).sum())):.3f}"
        print(line)
    # damage done by the saboteur under each voting rule
    for arm, nm in (("isolated", "equal votes"), ("networked", "learned credibility")):
        hon = np.array([err(by[(False, share)][s], arm, R) for s in seeds]); sab = np.array([err(by[(True, share)][s], arm, R) for s in seeds])
        print(f"  saboteur damage at round {R}, {nm:20s}: {np.median(sab - hon):+5.2f} µm ({np.median((sab - hon) / hon * 100):+4.1f}%), worse in {int((sab > hon).sum())}/{len(seeds)}")
    print()

print("Saboteur's share of networked slots and credibility, median over worlds and sites (messages cut):")
for r in range(1, R + 1):
    sl = [a["sab_slots"] / a["slots"] for s in seeds for a in by[(True, False)][s]["alloc"] if a["round"] == r]
    cr = [c["sab"] for s in seeds for c in by[(True, False)][s]["cred"] if c["round"] == r and c["sab"] is not None]
    hc = [c["sab"] for s in seeds for c in by[(False, False)][s]["cred"] if c["round"] == r and c["sab"] is not None]
    print(f"  round {r}: slot share {np.mean(sl) * 100:4.1f}% (mean), credibility after round {np.median(cr):.3f} vs honest geometry agent {np.median(hc):.3f}")
