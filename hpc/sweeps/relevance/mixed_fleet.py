"""Mixed fleets: some sites share physics, some don't. Exploratory, simulation only, frozen config.

The negative control (section 6) is all-or-nothing. Real fleets are mixed: here half the sites
share the common draw of the shared parameters ("matched") and half draw them on their own
("unmatched", make_world independent_sites). Data-poor sites as in section 7 (warm-up 4 pieces,
2 per round), 3 rounds, paired by world seed.

Conditions: alone (no messages), fixed (frozen config), check, adaptive, both.
Also records each receiver's adaptive-spread multiplier per sender (mean z^2, floored at 1 when
used) so we can see whether trust separates matched from unmatched senders.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/mixed_fleet.py 40 hpc/sweeps/relevance/results/mixed_fleet.jsonl [--sites 4]
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROUNDS = 3
CONDS = {
    "alone": dict(share_messages=False),
    "fixed": {},
    "check": dict(consistency_check=True),
    "adaptive": dict(adaptive_spread=True),
    "both": dict(consistency_check=True, adaptive_spread=True),
}


def fleet(n):
    """n sites, half resin half PLA; the first half of each process is matched, the rest unmatched."""
    sites = {f"{p}{i}": p for i in range(n // 2) for p in ("resin", "pla")}
    unmatched = {f"{p}{i}" for i in range(n // 4, n // 2) for p in ("resin", "pla")}
    return sites, unmatched


def one(job):
    seed, n, cond = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms import experiment
    from frozen import frozen_config
    from sim.reference import make_world

    disagree = {}
    orig = experiment._broadcast

    def spy(r, sites, *a, **k):
        orig(r, sites, *a, **k)
        for o, st in sites.items():
            for s, v in st.disagree.items():
                disagree[f"{o}<{s}"] = v  # running list, one entry per round

    experiment._broadcast = spy
    sites, unmatched = fleet(n)
    cfg = frozen_config(rounds=ROUNDS, seed=seed, seed_pieces=4, slots_per_arm=2, **CONDS[cond])
    res = experiment.run_experiment(make_world(sites, seed, independent_sites=unmatched), sites, cfg)
    experiment._broadcast = orig
    return {"seed": seed, "n": n, "cond": cond, "unmatched": sorted(unmatched),
            "checks": res.checks, "disagree": disagree,
            "scores": [{k: s[k] for k in ("round", "site", "arm", "mae_truth")} for s in res.scores]}


if __name__ == "__main__":
    nworlds, out = int(sys.argv[1]), sys.argv[2]
    n = int(sys.argv[sys.argv.index("--sites") + 1]) if "--sites" in sys.argv else 4
    done = set()
    if os.path.exists(out):
        for line in open(out):
            d = json.loads(line)
            done.add((d["seed"], d["n"], d["cond"]))
    todo = [(s, n, c) for s in range(nworlds) for c in CONDS if (s, n, c) not in done]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "a") as f:
        for i, fut in enumerate(as_completed([ex.submit(one, j) for j in todo]), 1):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
            if i % 20 == 0:
                print(f"{i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print("DONE", len(todo), round(time.time() - t0), flush=True)
