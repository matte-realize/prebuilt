"""Negative control: printers that share no physics. Exploratory, simulation only.

make_world(..., independent_shared=True) draws every site's "shared" parameters on its own from the
prior, with the same rng draws otherwise, so each control world is paired with the normal world of
the same seed. If the networked gain were built into the simulator or the scoring, it would show up
here too; it should be ~0. A third condition switches on the consistency check (Config.consistency_check),
to see whether receivers set aside notes about physics they don't actually share.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/negative_control.py 60 hpc/sweeps/relevance/results/negative_control.jsonl
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

SITES = {"resin": "resin", "pla": "pla"}
ROUNDS = 3  # headline round, matching the real experiment


def one(job):
    seed, world, cond = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import make_world
    cfg = frozen_config(rounds=ROUNDS, seed=seed, share_messages=cond != "alone", consistency_check=cond == "check")
    res = run_experiment(make_world(SITES, seed, independent_shared=world == "control"), SITES, cfg)
    return {"seed": seed, "world": world, "cond": cond, "checks": res.checks,
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth", "cov90")} for r in res.scores]}


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    jobs = [(s, w, c) for s in range(n) for w in ("normal", "control") for c in ("normal", "alone", "check")]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
    print("DONE", round(time.time() - t0), flush=True)
