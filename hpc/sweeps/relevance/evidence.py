"""Condense the relevance sweeps into viewer/evidence.json, the numbers the 3D demo is allowed to show.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/evidence.py

Reads results/worlds.jsonl (worlds.py: 100 worlds x {notes, no notes, liar}, 8 rounds) and, if present,
results/regimes.jsonl (regimes.py), consistency(_protocol).jsonl, negative_control.jsonl, and
../coldstart/results/grid.jsonl (sites needed). `consistency_check` comes from the protocol sweep when
present (source: protocol), else from the prototype. Errors are against the simulator's true sizes (mae_truth) unless
named "measured". Every gain is paired per world: same world, same printers, one thing changed.
"""
from __future__ import annotations

import gzip, json
import math
from collections import defaultdict
from pathlib import Path

def _open(path):
    """Results are committed gzipped (*.jsonl.gz); plain .jsonl works too."""
    path = str(path)
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


import numpy as np
import yaml

HERE = Path(__file__).parent
HORIZON = 3  # headline round: the real experiment prints 3 rounds
ROOT = HERE.parents[2]


def sign_p(w: int, n: int) -> float:
    if n == 0:
        return 1.0
    k = min(w, n - w)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def ci(x, b=4000, seed=0):
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    return [float(v) for v in np.percentile([np.median(rng.choice(x, len(x))) for _ in range(b)], [2.5, 97.5])]


def load(path: Path):
    runs = [json.loads(line) for line in _open(path)]
    R = max(s["round"] for s in runs[0]["scores"])
    C = defaultdict(dict)
    for run in runs:
        acc = defaultdict(lambda: defaultdict(list))
        for s in run["scores"]:
            for m in ("mae", "mae_truth", "cov90"):
                if m in s:
                    acc[(s["arm"], m)][s["round"]].append(s[m])
        run["curve"] = {k: np.array([np.mean(v[r]) for r in range(1, R + 1)]) * (100 if k[1] == "cov90" else 1000) for k, v in acc.items()}
        C[(run.get("cell", "main"), run["cond"])][run["seed"]] = run
    return C, R


def gain(better, base):
    """Paired: how much lower `better` is than `base` (µm and %), per world."""
    d = base - better
    w = int((d > 0).sum())
    return {"um": float(np.median(d)), "pct": float(np.median(d / base * 100)), "pct_ci": ci(d / base * 100),
            "wins": w, "n": len(d), "p": sign_p(w, int((d != 0).sum()))}


def _site_mean(scores, arm, r, site=None, key="mae_truth"):
    return 1000 * float(np.mean([x[key] for x in scores if x["arm"] == arm and x["round"] == r and x.get(key) is not None
                                 and (site is None or x["site"] == site)]))


def consistency_protocol(path: Path) -> dict:
    """consistency_protocol.py: Config.consistency_check on/off, honest and lying pla, plus no notes."""
    runs = [json.loads(line) for line in _open(path)]
    by = defaultdict(dict)
    for r in runs:
        by[(r["cond"], r["check"])][r["seed"]] = r
    seeds = sorted(set.intersection(*(set(v) for v in by.values())))
    e = lambda cond, chk, arm="networked", r=HORIZON, site=None: np.array([_site_mean(by[(cond, chk)][s]["scores"], arm, r, site) for s in seeds])
    caught = [c for s in seeds for c in by[("liar", True)][s]["checks"] if c["sender"] == "pla"]
    honest = [c for s in seeds for (cond, chk) in (("normal", True), ("liar", True)) for c in by[(cond, chk)][s]["checks"]
              if not (cond == "liar" and c["sender"] == "pla")]
    return {
        "source": "protocol",  # Config.consistency_check in arms/experiment.py; off in the frozen config
        "worlds": len(seeds), "rounds": HORIZON,
        "liar_caught": int(sum(c["dropped"] for c in caught)), "liar_notes": len(caught),
        "honest_dropped": int(sum(c["dropped"] for c in honest)), "honest_notes": len(honest),
        "liar_chi2_min": float(min(c["chi2"] for c in caught)) if caught else None,
        "honest_chi2_p99": float(np.percentile([c["chi2"] for c in honest], 99)) if honest else None,
        "threshold": 16.27,
        "resin_round1_um": {"liar_no_check": float(np.median(e("liar", False, r=1, site="resin"))),
                            "liar_check": float(np.median(e("liar", True, r=1, site="resin"))),
                            "no_notes": float(np.median(e("alone", False, r=1, site="resin"))),
                            "honest": float(np.median(e("normal", False, r=1, site="resin")))},
        "round1_check_vs_no_check": gain(e("liar", True, r=1), e("liar", False, r=1)),
        "error_um_by_round": {f"{c}{' + check' if k else ''}": [float(np.median(e(c, k, r=r))) for r in range(1, HORIZON + 1)]
                              for c, k in (("alone", False), ("normal", False), ("normal", True), ("liar", False), ("liar", True))},
        "honest_together_vs_alone": {"check_off": gain(e("normal", False), e("normal", False, "isolated")),
                                     "check_on": gain(e("normal", True), e("normal", True, "isolated"))},
        "honest_check_vs_no_check": gain(e("normal", True), e("normal", False)),
        "liar_check_vs_no_notes": gain(e("liar", True), e("alone", False)),
        "liar_no_check_vs_no_notes": gain(e("liar", False), e("alone", False)),
        "liar_check_together_vs_alone": gain(e("liar", True), e("liar", True, "isolated")),
    }


def negative_control(path: Path) -> dict:
    """negative_control.py: the normal world vs one where every site's 'shared' parameters are drawn independently."""
    runs = [json.loads(line) for line in _open(path)]
    by = defaultdict(dict)
    for r in runs:
        by[(r["world"], r["cond"])][r["seed"]] = r
    seeds = sorted(set.intersection(*(set(v) for v in by.values())))
    e = lambda world, cond, arm, r=HORIZON: np.array([_site_mean(by[(world, cond)][s]["scores"], arm, r) for s in seeds])
    out = {"worlds": len(seeds), "rounds": HORIZON}
    for w in ("normal", "control"):
        out[w] = {"alone_um": float(np.median(e(w, "normal", "isolated"))), "together_um": float(np.median(e(w, "normal", "networked"))),
                  "together_vs_alone": gain(e(w, "normal", "networked"), e(w, "normal", "isolated")),
                  "notes_vs_no_notes": gain(e(w, "normal", "networked"), e(w, "alone", "networked")),
                  "pooled_vs_alone": gain(e(w, "normal", "oracle"), e(w, "normal", "isolated"))}
        if (w, "check") in by:  # same, with the consistency check on
            chk = [c for s in seeds for c in by[(w, "check")][s]["checks"]]
            out[w]["check"] = {"together_vs_alone": gain(e(w, "check", "networked"), e(w, "check", "isolated")),
                               "vs_no_check": gain(e(w, "check", "networked"), e(w, "normal", "networked")),
                               "dropped": int(sum(c["dropped"] for c in chk)), "notes": len(chk)}
    return out


def sites_needed(path: Path, cell=(4, 2), r=HORIZON) -> dict:
    """coldstart/results/grid.jsonl at warm-up 4, 2 pieces/round: networked vs isolated by number of sites.
    pct is the coldstart README's metric (mean gain / mean isolated error); the paired gain() is alongside."""
    acc = defaultdict(dict)
    curves = defaultdict(lambda: {a: [[] for _ in range(r)] for a in ("isolated", "networked", "oracle")})
    for line in _open(path):
        d = json.loads(line)
        c = d["cell"]
        if (c.get("seed_pieces"), c.get("slots")) != cell or set(c) != {"n", "seed_pieces", "slots"}:
            continue
        acc[c["n"]][d["seed"]] = (_site_mean(d["scores"], "isolated", r), _site_mean(d["scores"], "networked", r))
        for arm in ("isolated", "networked", "oracle"):  # by-round curves for the demo's "many printers" chart
            for k in range(1, r + 1):
                curves[c["n"]][arm][k - 1].append(_site_mean(d["scores"], arm, k))
    rows = []
    for n in sorted(acc):
        iso, net = (np.array(v) for v in zip(*acc[n].values()))
        g = gain(net, iso)
        rows.append({"sites": n, "worlds": len(iso), "alone_um": float(iso.mean()), "together_um": float(net.mean()),
                     "pct": float(100 * (iso - net).mean() / iso.mean()), "wins": g["wins"], "n": g["n"], "p": g["p"], "paired": g,
                     "curve_um": {a: [float(np.mean(v)) for v in curves[n][a]] for a in curves[n]}})
    return {"source": "hpc/sweeps/coldstart/results/" + Path(path).name, "seed_pieces": cell[0], "per_round": cell[1], "round": r, "rows": rows}


def main() -> None:
    res = lambda name: next((p for p in (HERE / "results" / f"{name}.jsonl", HERE / "results" / f"{name}.jsonl.gz") if p.exists()), HERE / "results" / f"{name}.jsonl")
    C, R = load(res("worlds"))
    seeds = sorted(C[("main", "normal")])
    arr = lambda cond, arm, m="mae_truth", r=HORIZON: np.array([C[("main", cond)][s]["curve"][(arm, m)][r - 1] for s in seeds])
    trust = defaultdict(list)
    for s in seeds:
        for t in C[("main", "liar")][s]["trust"]:
            if t["receiver"] == "resin" and t["sender"] == "pla":
                trust[t["round"]].append(t["trust"])
    th = yaml.safe_load((ROOT / "prereg" / "prereg.yaml").open())["fit_classes_mm"]
    ev = {
        "worlds": len(seeds), "rounds": HORIZON, "rounds_run": R,
        "at_last_round": {"together_vs_alone": gain(arr("normal", "networked", r=R), arr("normal", "isolated", r=R)),
                          "notes_vs_no_notes": gain(arr("normal", "networked", r=R), arr("alone", "networked", r=R)),
                          "liar_vs_no_notes": gain(arr("liar", "networked", r=R), arr("alone", "networked", r=R))},
        "error_um": {arm: float(np.median(arr("normal", arm))) for arm in ("isolated", "networked", "oracle")},
        "error_um_round1": {arm: float(np.median(arr("normal", arm, r=1))) for arm in ("isolated", "networked")},
        "together_vs_alone": gain(arr("normal", "networked"), arr("normal", "isolated")),
        "pooled_vs_alone": gain(arr("normal", "oracle"), arr("normal", "isolated")),
        "notes_vs_no_notes": gain(arr("normal", "networked"), arr("alone", "networked")),
        "team_without_notes_vs_alone": gain(arr("alone", "networked"), arr("alone", "isolated")),
        "liar_together_vs_alone": gain(arr("liar", "networked"), arr("liar", "isolated")),
        "measured": {
            "together_vs_alone": gain(arr("normal", "networked", "mae"), arr("normal", "isolated", "mae")),
            "alone_error_um": float(np.median(arr("normal", "isolated", "mae"))),
        },
        "liar": {
            "trust_by_round": {r: float(np.median(v)) for r, v in sorted(trust.items())},
            "round1_error_um": float(np.median(arr("liar", "networked", r=1))),
            "round1_error_um_no_notes": float(np.median(arr("alone", "networked", r=1))),
            "round1_worse_in": int((arr("liar", "networked", r=1) > arr("alone", "networked", r=1)).sum()),
            "final_vs_no_notes": gain(arr("liar", "networked"), arr("alone", "networked")),
        },
        "coverage": {arm: round(float(np.median(arr("normal", arm, "cov90")))) for arm in ("isolated", "networked", "oracle")},
        # Slip-fit band widths from the prereg, the tolerance scale a part's fit actually depends on.
        "slip_band_um": {proc: round((v["slip"][1] - v["slip"][0]) * 1000) for proc, v in th.items()},
    }
    reg = res("regimes")
    if reg.exists() and reg.stat().st_size:
        RC, RR = load(reg)
        ev["regimes"] = []
        cells = list(dict.fromkeys(k[0] for k in RC))
        for cell in cells:
            if (cell, "alone") not in RC:
                continue
            ss = sorted(set(RC[(cell, "normal")]) & set(RC[(cell, "alone")]))
            g = lambda cond, arm, m="mae_truth", r=min(HORIZON, RR): np.array([RC[(cell, cond)][s]["curve"][(arm, m)][r - 1] for s in ss])
            fit = {}
            for arm in ("isolated", "networked", "oracle"):
                ok = tot = 0
                for s in ss:
                    for f in RC[(cell, "normal")][s]["fit"]:
                        if f["arm"] == arm and f["fit_pairs"]:
                            ok += f["fit_acc"] * f["fit_pairs"]; tot += f["fit_pairs"]
                fit[arm] = {"wrong_per_100": 100 * (1 - ok / tot) if tot else None, "pairs": tot}
            ev["regimes"].append({
                "name": cell, "worlds": len(ss), "rounds": min(HORIZON, RR),
                "alone_um": float(np.median(g("normal", "isolated"))), "together_um": float(np.median(g("normal", "networked"))),
                "together_vs_alone": gain(g("normal", "networked"), g("normal", "isolated")),
                "notes_vs_no_notes": gain(g("normal", "networked"), g("alone", "networked")),
                "round1": gain(g("normal", "networked", r=1), g("normal", "isolated", r=1)),
                "fit": fit,
            })
        tr = {}
        for cell, cond in (("trust 1.0", "liar"), ("trust 0.3", "liar"), ("trust 0.3", "normal"), ("2 sites, warm-up 16, 6/round", "normal"), ("2 sites, warm-up 16, 6/round", "alone")):
            if (cell, cond) in RC:
                tr[f"{cell} | {cond}"] = [float(np.median([run["curve"][("networked", "mae_truth")][r] for run in RC[(cell, cond)].values()])) for r in range(RR)]
        ev["trust_start"] = tr
    cons = res("consistency")
    if cons.exists() and cons.stat().st_size:
        runs = [json.loads(line) for line in _open(cons)]
        cell = lambda cond, chk, site="resin": [1000 * np.mean([x["mae_truth"] for x in r["scores"] if x["arm"] == "networked" and x["round"] == 1 and x["site"] == site])
                                                for r in runs if r["cond"] == cond and r["check"] == chk]
        caught = [c for r in runs if r["cond"] == "liar" and r["check"] for c in r["checks"] if c["sender"] == "pla"]
        honest = [c for r in runs if r["check"] for c in r["checks"] if not (r["cond"] == "liar" and c["sender"] == "pla")]
        ev["consistency_check"] = {
            "worlds": len({r["seed"] for r in runs}),
            "liar_caught": sum(c["dropped"] for c in caught), "liar_notes": len(caught),
            "honest_dropped": sum(c["dropped"] for c in honest), "honest_notes": len(honest),
            "resin_round1_um": {"liar_no_check": float(np.median(cell("liar", False))), "liar_check": float(np.median(cell("liar", True))),
                                "no_notes": float(np.median(cell("alone", False)))},
        }
    proto = res("consistency_protocol")
    if proto.exists() and proto.stat().st_size:
        ev["consistency_check"] = consistency_protocol(proto)  # replaces the prototype's numbers
    neg = res("negative_control")
    if neg.exists() and neg.stat().st_size:
        ev["negative_control"] = negative_control(neg)
    cold = next((p for p in (ROOT / "hpc/sweeps/coldstart/results/grid.jsonl", ROOT / "hpc/sweeps/coldstart/results/grid.jsonl.gz") if p.exists()), None)
    if cold:
        ev["sites_needed"] = sites_needed(cold)
    out = ROOT / "viewer" / "evidence.json"
    out.write_text(json.dumps(ev, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
