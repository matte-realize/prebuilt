"""100 simulated worlds x {notes, no notes, liar}, 8 rounds. Saves per-round scores to JSONL."""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arms.experiment import run_experiment
from frozen import frozen_config
from sim.reference import make_world
SITES = {"resin": "resin", "pla": "pla"}
ROUNDS, N = 8, int(sys.argv[1]) if len(sys.argv) > 1 else 100
OUT = sys.argv[2]
def one(job):
    seed, cond = job
    cfg = frozen_config(rounds=ROUNDS, seed=seed, share_messages=cond != "alone", bad_sites=("pla",) if cond == "liar" else ())
    res = run_experiment(make_world(SITES, seed), SITES, cfg)
    trust = [{k: r[k] for k in ("round", "receiver", "sender", "trust")} for r in res.trust]
    return {"seed": seed, "cond": cond, "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth", "lpd", "cov90")} for r in res.scores], "trust": trust}
if __name__ == "__main__":
    jobs = [(s, c) for s in range(N) for c in ("normal", "alone", "liar")]
    t0 = time.time(); done = 0
    with ProcessPoolExecutor() as ex, open(OUT, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush(); done += 1
            if done % 30 == 0: print(f"{done}/{len(jobs)} runs, {time.time()-t0:.0f}s", flush=True)
    print("DONE", flush=True)
