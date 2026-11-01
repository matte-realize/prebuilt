"""Consistency check as a protocol option (Config.consistency_check), not a monkeypatch. Exploratory, simulation only.

Same design as consistency.py (the prototype), but uses the built-in check in arms/experiment.py:
after each broadcast, a receiver drops an incoming note whose shared-parameter summary contradicts its
own local fit (chi-square 0.999 over the shared parameters, with the between-site spread the model
allows). The receiver's own summary is the local fit it just made for its outgoing note, so no refit.
Off in the frozen/registered config; switched on here per job.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/consistency_protocol.py 60 hpc/sweeps/relevance/results/consistency_protocol.jsonl
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

SITES = {"resin": "resin", "pla": "pla"}
ROUNDS = 3


def one(job):
    seed, cond, check = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import make_world
    cfg = frozen_config(rounds=ROUNDS, seed=seed, share_messages=cond != "alone",
                        bad_sites=("pla",) if cond == "liar" else (), consistency_check=check)
    res = run_experiment(make_world(SITES, seed), SITES, cfg)
    return {"seed": seed, "cond": cond, "check": check, "checks": res.checks,
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth")} for r in res.scores]}


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    jobs = [(s, c, chk) for s in range(n) for c, chk in (("normal", False), ("normal", True), ("liar", False), ("liar", True), ("alone", False))]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
    print("DONE", round(time.time() - t0), flush=True)
