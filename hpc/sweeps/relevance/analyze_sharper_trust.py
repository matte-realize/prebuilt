"""Analyze sharper_trust.jsonl: gains for matched and unmatched sites, and how well each trust rule
separates matched senders from mismatched ones, at rounds 3, 6, 8. True-size error, paired per world.

Separation: the spread multiplier a receiver would apply to a sender after round R.
  adaptive / both:          max(1, mean z^2 over rounds 1..R)
  predictive / pred_check:  predictive_multiplier(d) for the latest score at or before round R
AUC = chance a mismatched sender gets a bigger multiplier than a matched one (matched receivers;
0.5 = no separation, 1 = perfect).

    .venv/bin/python hpc/sweeps/relevance/analyze_sharper_trust.py hpc/sweeps/relevance/results/sharper_trust.jsonl.gz [--json out.json]
    .venv/bin/python hpc/sweeps/relevance/analyze_sharper_trust.py --split hpc/sweeps/relevance/results/sharper_trust_split.jsonl.gz [--json out.json]

--split (leakage check): predictive trust scored notes on half 0 of the held-out pieces only;
error is reported on half 0 (seen by trust) and half 1 (never seen by trust) separately.
"""
import json, os, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from evidence import _open, gain  # noqa: E402
from arms.experiment import predictive_multiplier  # noqa: E402

HORIZONS = (3, 6, 8)
CONDS = ("fixed", "adaptive", "both", "predictive", "pred_check")


def err(run, arm, sites, r):
    v = [x["mae_truth"] for x in run["scores"] if x["arm"] == arm and x["round"] == r and x["site"] in sites and x["mae_truth"] is not None]
    return 1000 * float(np.mean(v)) if v else np.nan


def paired(a_runs, a_arm, b_runs, b_arm, sites, r):
    seeds = sorted(set(a_runs) & set(b_runs))
    a = np.array([err(a_runs[s], a_arm, sites, r) for s in seeds])
    b = np.array([err(b_runs[s], b_arm, sites, r) for s in seeds])
    ok = ~(np.isnan(a) | np.isnan(b))
    return {**gain(a[ok], b[ok]), "a_um": float(a[ok].mean()), "b_um": float(b[ok].mean())}


def multiplier(run, cond, key, r):
    if cond in ("adaptive", "both"):
        v = run["disagree"].get(key, [])[:r]
        return max(1.0, float(np.mean(v))) if v else 1.0
    v = run["predictive"].get(key, [])[: r - 1]  # scored from round 2, one score per round the note arrived
    return predictive_multiplier(v[-1]) if v else 1.0


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


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
        gof = lambda s: "unmatched" if s in un else "matched"
        o = {"worlds": len(by["fixed"]), "groups": {g: sorted(s) for g, s in groups.items()}}
        for r in HORIZONS:
            if r > any_run["rounds"]:
                continue
            h = {}
            for g, sites in groups.items():
                h[g] = {"alone_um": float(np.nanmean([err(x, "isolated", sites, r) for x in by["alone"].values()]))}
                for c in CONDS:
                    if by[c]:
                        h[g][c] = {"vs_alone": paired(by[c], "networked", by[c], "isolated", sites, r),
                                   "vs_fixed": paired(by[c], "networked", by["fixed"], "networked", sites, r)}
            for c in ("adaptive", "both", "predictive", "pred_check"):
                if not by[c]:
                    continue
                mult = defaultdict(list)
                for run in by[c].values():
                    for o_ in allsites:
                        for s_ in allsites - {o_}:
                            mult[f"{gof(o_)}<{gof(s_)}"].append(multiplier(run, c, f"{o_}<{s_}", r))
                h[f"sep_{c}"] = {
                    "pairs": {k: {"mean": float(np.mean(v)), "median": float(np.median(v)),
                                  "frac_above_2": float(np.mean(np.array(v) > 2)), "n": len(v)} for k, v in sorted(mult.items())},
                    "auc_matched_receivers": auc(mult["matched<unmatched"], mult["matched<matched"])}
            o[f"round_{r}"] = h
        out[str(n)] = o
    return out


def analyze_split(path):
    D = defaultdict(dict)  # cond -> seed -> run
    for line in _open(path):
        x = json.loads(line)
        D[x["cond"]][x["seed"]] = x
    any_run = next(iter(D["fixed"].values()))
    un = set(any_run["unmatched"])
    allsites = {x["site"] for x in any_run["scores"]}
    groups = {"matched": allsites - un, "unmatched": un}

    def herr(run, arm, sites, r, half):
        v = [run["half_scores"].get(f"{r}|{s}|{arm}|{half}") for s in sites]
        v = [x for x in v if x is not None]
        return 1000 * float(np.mean(v)) if v else np.nan

    out = {"worlds": len(D["fixed"])}
    for r in (3, 6):
        for half in (0, 1):
            for g, sites in groups.items():
                for c in ("fixed", "predictive"):
                    seeds = sorted(D[c])
                    a = np.array([herr(D[c][s], "networked", sites, r, half) for s in seeds])
                    b = np.array([herr(D[c][s], "isolated", sites, r, half) for s in seeds])
                    ok = ~(np.isnan(a) | np.isnan(b))
                    out[f"r{r}|half{half}|{g}|{c}"] = {**gain(a[ok], b[ok]), "a_um": float(a[ok].mean()), "b_um": float(b[ok].mean())}
    return out


def fmt(g):
    return f"{g['pct']:+6.1f}% ({g['wins']}/{g['n']}, p={g['p']:.3f})"


if __name__ == "__main__" and "--split" in sys.argv:
    O = analyze_split(Path(sys.argv[sys.argv.index("--split") + 1]))
    print(f"Leakage check, {O['worlds']} worlds: together vs alone, paired median; half 0 = pieces trust saw, half 1 = never seen")
    for k, g in O.items():
        if k != "worlds":
            print(f"  {k:32s} {g['a_um']:5.1f} vs {g['b_um']:5.1f} µm  {fmt(g)}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(O, indent=1))
    sys.exit()

if __name__ == "__main__":
    O = analyze(Path(sys.argv[1]))
    for n, o in O.items():
        print(f"== {n} sites, {o['worlds']} worlds; together vs alone, paired median; positive = better")
        for r in HORIZONS:
            h = o.get(f"round_{r}")
            if not h:
                continue
            print(f"\n-- round {r}: alone matched {h['matched']['alone_um']:.1f} µm, unmatched {h['unmatched']['alone_um']:.1f} µm")
            for c in CONDS:
                if c in h["matched"]:
                    print(f"  {c:11s} matched {fmt(h['matched'][c]['vs_alone'])}   unmatched {fmt(h['unmatched'][c]['vs_alone'])}"
                          f"   | vs fixed: m {h['matched'][c]['vs_fixed']['wins']}/{h['matched'][c]['vs_fixed']['n']}, u {h['unmatched'][c]['vs_fixed']['wins']}/{h['unmatched'][c]['vs_fixed']['n']}")
            for c in ("adaptive", "both", "predictive", "pred_check"):
                sp = h.get(f"sep_{c}")
                if sp:
                    p = sp["pairs"]
                    print(f"  sep {c:11s} AUC {sp['auc_matched_receivers']:.2f}; m<m med {p['matched<matched']['median']:.2f} >2x {100*p['matched<matched']['frac_above_2']:.0f}%;"
                          f" m<u med {p['matched<unmatched']['median']:.2f} >2x {100*p['matched<unmatched']['frac_above_2']:.0f}%;"
                          f" u<u >2x {100*p['unmatched<unmatched']['frac_above_2']:.0f}%")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(O, indent=1))
