"""Sharper trust in mixed fleets. Exploratory, simulation only, frozen config.

Section 10 found adaptive spread only partly separates matched from unmatched senders after
3 rounds. Two ways to sharpen it, same mixed fleet (make_world independent_sites, half the
sites share no physics), data-poor sites (warm-up 4 pieces, 2 per round), paired by world seed:

  A. Longer horizon: run ROUNDS rounds and read rounds 3, 6, 8 (the first rounds of a long
     run are the same as a short run's, so one run covers every horizon).
  B. Predictive trust (Config.predictive_trust): each receiver scores each sender's note on its
     own newly measured held-out pieces and scales that note's spread by the likelihood ratio
     against it.

Records, per receiver and sender and round, the adaptive-spread disagreement (mean z^2) and the
predictive score d (nats), so the analysis can rebuild the multiplier after any round.

Leakage check (--split): predictive trust scores notes on the same held-out pieces the evaluation
uses. With --split, predictive conditions set predictive_half, so notes are scored only on half the
held-out pieces (arms.experiment.trust_half == 0), and every run also records true-size error on
each half separately ("half_scores"); the untouched half 1 is the honest test.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/sharper_trust.py 20 hpc/sweeps/relevance/results/sharper_trust.jsonl [--sites 8] [--rounds 8]
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/sharper_trust.py 20 hpc/sweeps/relevance/results/sharper_trust_split.jsonl --rounds 6 --split --only alone,fixed,predictive,pred_check
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

CONDS = {
    "alone": dict(share_messages=False),
    "fixed": {},
    "adaptive": dict(adaptive_spread=True),
    "both": dict(consistency_check=True, adaptive_spread=True),
    "predictive": dict(predictive_trust=True),
    "pred_check": dict(predictive_trust=True, consistency_check=True),
}


def fleet(n):
    """n sites, half resin half PLA; the first half of each process is matched, the rest unmatched (as mixed_fleet.py)."""
    sites = {f"{p}{i}": p for i in range(n // 2) for p in ("resin", "pla")}
    unmatched = {f"{p}{i}" for i in range(n // 4, n // 2) for p in ("resin", "pla")}
    return sites, unmatched


def one(job):
    seed, n, cond, rounds, split = (*job, False)[:5]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms import experiment
    from frozen import frozen_config
    from sim.reference import make_world

    rec = {"disagree": {}, "predictive": {}}
    orig = experiment._score

    def spy(r, st, *a, **k):  # after broadcast and credit: snapshot this receiver's running records
        orig(r, st, *a, **k)
        for s, v in st.disagree.items():
            rec["disagree"][f"{st.site}<{s}"] = list(v)
        for s, v in st.predictive.items():
            rec["predictive"][f"{st.site}<{s}"] = list(v)

    experiment._score = spy
    sites, unmatched = fleet(n)
    kw = dict(CONDS[cond], **({"predictive_half": True} if split and CONDS[cond].get("predictive_trust") else {}))
    cfg = frozen_config(rounds=rounds, seed=seed, seed_pieces=4, slots_per_arm=2, **kw)
    res = experiment.run_experiment(make_world(sites, seed, independent_sites=unmatched), sites, cfg)
    experiment._score = orig
    halves = {}
    if split:  # true-size absolute error per (round, site, arm, half)
        for p in res.predictions:
            if p["truth"] is not None:
                halves.setdefault(f"{p['round']}|{p['site']}|{p['arm']}|{experiment.trust_half(p['piece_id'])}", []).append(abs(p["mean"] - p["truth"]))
        halves = {k: float(sum(v) / len(v)) for k, v in halves.items()}
    return {"seed": seed, "n": n, "cond": cond, "rounds": rounds, "unmatched": sorted(unmatched), "split": split,
            "half_scores": halves, "checks": res.checks, **rec,
            "scores": [{k: s[k] for k in ("round", "site", "arm", "mae_truth")} for s in res.scores]}


if __name__ == "__main__":
    nworlds, out = int(sys.argv[1]), sys.argv[2]
    n = int(sys.argv[sys.argv.index("--sites") + 1]) if "--sites" in sys.argv else 8
    rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 8
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else list(CONDS)
    split = "--split" in sys.argv
    done = set()
    if os.path.exists(out):
        for line in open(out):
            d = json.loads(line)
            done.add((d["seed"], d["n"], d["cond"]))
    todo = [(s, n, c, rounds, split) for s in range(nworlds) for c in only if (s, n, c) not in done]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "a") as f:
        for i, fut in enumerate(as_completed([ex.submit(one, j) for j in todo]), 1):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
            if i % 10 == 0:
                print(f"{i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print("DONE", len(todo), round(time.time() - t0), flush=True)
