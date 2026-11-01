"""Three technical checks. Exploratory, simulation only, frozen config, 3 rounds, paired by world seed.

  spread   Adaptive spread (Config.adaptive_spread) vs the fixed spread, the consistency check and no
           messages, in normal worlds and negative-control worlds (make_world independent_shared=True).
           Question: does learning how far to trust a sender remove the harm when printers share nothing,
           and keep the gain when they do?
  liar     How subtle a liar the defences catch: bad_offset 0.5 / 1 / 2 / 3 prior std, with no defence,
           the consistency check, and adaptive spread.
  random   Random piece selection (Config.selection="random") for every arm vs the agent auction.
           Question: do the agents' choices beat random, and does the network gain survive without them?

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/technical.py 60 hpc/sweeps/relevance/results/technical.jsonl
    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/technical.py 60 results/technical-both.jsonl --only both   # check + adaptive together
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

SITES = {"resin": "resin", "pla": "pla"}
ROUNDS = 3
CONDS = {  # name -> Config overrides
    "alone": dict(share_messages=False),
    "fixed": {},
    "check": dict(consistency_check=True),
    "adaptive": dict(adaptive_spread=True),
    "both": dict(consistency_check=True, adaptive_spread=True),
}


def jobs(n, only=None):
    for s in range(n):
        for world in ("normal", "control"):
            for cond in CONDS:
                yield (s, "spread", world, cond, None)
        for off in (0.5, 1.0, 2.0, 3.0):
            for cond in ("fixed", "check", "adaptive", "both"):
                yield (s, "liar", "normal", cond, off)
        yield (s, "random", "normal", "fixed", None)


def selected(n, only):
    """`--only both` runs just that condition (to append to an existing results file)."""
    return [j for j in jobs(n) if only is None or j[3] == only]


def one(job):
    seed, study, world, cond, off = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import make_world
    kw = dict(CONDS[cond])
    if study == "liar":
        kw.update(bad_sites=("pla",), bad_offset=off)
    if study == "random":
        kw.update(selection="random")
    cfg = frozen_config(rounds=ROUNDS, seed=seed, **kw)
    res = run_experiment(make_world(SITES, seed, independent_shared=world == "control"), SITES, cfg)
    return {"seed": seed, "study": study, "world": world, "cond": cond, "offset": off, "checks": res.checks,
            "trust": res.trust,
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth")} for r in res.scores]}


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    todo = selected(n, sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None)
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in todo]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
    print("DONE", len(todo), round(time.time() - t0), flush=True)
