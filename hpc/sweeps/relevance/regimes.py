"""Where does sharing matter? Sweep data-poverty, network size and trust_init. Exploratory; not the prereg config."""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import yaml
import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arms.experiment import run_experiment
from frozen import frozen_config
from sim.reference import make_world
from eval.fit import fit_accuracy
TWO = {"resin": "resin", "pla": "pla"}
FOUR = {"resin": "resin", "pla": "pla", "resin2": "resin", "pla2": "pla"}
TH = yaml.safe_load(open("prereg/prereg.yaml"))["fit_classes_mm"]
ROUNDS, W = 5, 60
CELLS = []
for sp in (4, 8, 16):
    for sl in (2, 6):
        CELLS.append((f"2 sites, warm-up {sp}, {sl}/round", TWO, sp, sl, 1.0, ("normal", "alone")))
CELLS.append(("4 sites, warm-up 8, 6/round", FOUR, 8, 6, 1.0, ("normal", "alone")))
CELLS.append(("4 sites, warm-up 4, 2/round", FOUR, 4, 2, 1.0, ("normal", "alone")))
CELLS.append(("trust 1.0", TWO, 16, 6, 1.0, ("liar",)))
CELLS.append(("trust 0.3", TWO, 16, 6, 0.3, ("normal", "liar")))
def one(job):
    cell, sites, sp, sl, ti, cond, seed = job
    cfg = frozen_config(rounds=ROUNDS, seed=seed, seed_pieces=sp, slots_per_arm=sl, trust_init=ti,
                 share_messages=cond != "alone", bad_sites=("pla",) if cond == "liar" else ())
    res = run_experiment(make_world(sites, seed), sites, cfg)
    fit = fit_accuracy(res.predictions, TH, sites, truth=True)
    return {"cell": cell, "cond": cond, "seed": seed, "sites": len(sites),
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth")} for r in res.scores],
            "fit": [{k: r[k] for k in ("round", "site", "arm", "fit_acc", "fit_pairs")} for r in fit]}
if __name__ == "__main__":
    jobs = [(c[0], c[1], c[2], c[3], c[4], cond, s) for c in CELLS for cond in c[5] for s in range(W)]
    jobs.sort(key=lambda j: -len(j[1]))  # slow 4-site runs first
    t0 = time.time(); done = 0
    with ProcessPoolExecutor() as ex, open(sys.argv[1], "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush(); done += 1
            if done % 100 == 0: print(f"{done}/{len(jobs)} runs, {time.time()-t0:.0f}s", flush=True)
    print("DONE", time.time() - t0, flush=True)
