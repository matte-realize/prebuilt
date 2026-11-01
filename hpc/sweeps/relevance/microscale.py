"""Micro-scale check: does the sharing gain grow on a plate of small features? Exploratory, simulation only.

The shared term size_coef / d grows as features shrink, so in the model the physics every printer
shares matters more at small d. This sweep asks whether that turns into a bigger networked gain.

Plates (set per worker by patching plates.spec; defaults untouched elsewhere):
  normal   the registered plate: agents propose 1.5-7.0 mm, library 1.0-8.0 mm
  small    agents propose 0.4-1.0 mm, library 0.3-1.2 mm (same 0.1 mm step)

Printers:
  default  the simulator's failure model as is (resin pins/holes fail 50% at 1.2/1.0 mm, PLA 1.3/1.6 mm)
  fine     a hypothetical finer process: 50% failure diameters scaled by 0.2 (resin 0.24/0.20, PLA 0.26/0.32)

Pairs: resin + PLA (the registered pair) and resin + resin (two SLA sites, the more plausible micro case:
the PLA model's poly_k / d hole shrink goes nonphysical below ~0.5 mm).

Frozen config, 3 rounds, paired by world seed.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/microscale.py 60 hpc/sweeps/relevance/results/microscale.jsonl
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROUNDS = 3
PLATES = {"normal": dict(TRAIN_RANGE=(1.5, 7.0), D_MIN=1.0, D_MAX=8.0),
          "small": dict(TRAIN_RANGE=(0.4, 1.0), D_MIN=0.3, D_MAX=1.2)}
PAIRS = {"resin_pla": {"resin": "resin", "pla": "pla"}, "resin_resin": {"resin": "resin", "resin2": "resin"}}
FINE = 0.2
CONDS = [("normal", "default"), ("small", "default"), ("small", "fine")]


def set_plate(name):
    from plates import library, spec
    for k, v in PLATES[name].items():
        setattr(spec, k, v)
    library.candidates.cache_clear()


def one(job):
    seed, pair, plate, printer = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    set_plate(plate)
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import FAIL_D, make_world
    sites = PAIRS[pair]
    world = make_world(sites, seed)
    if printer == "fine":
        for p in world.values():
            p.fail_d = {k: v * FINE for k, v in FAIL_D[p.process].items()}
    res = run_experiment(world, sites, frozen_config(rounds=ROUNDS, seed=seed))
    rel, ad = {}, {}  # (round, site, arm) -> true-size error / nominal size; and true-size error, held-out pieces that printed
    for x in res.predictions:
        if x["truth"] is not None:
            key = f"{x['round']}|{x['site']}|{x['arm']}"
            rel.setdefault(key, []).append(abs(x["mean"] - x["truth"]) / x["nominal_d"])
            ad.setdefault(key, []).append(x["nominal_d"])
    rows = []
    for r in res.scores:
        key = f"{r['round']}|{r['site']}|{r['arm']}"
        rows.append({**{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth", "cov90", "n_train", "n_heldout", "n_heldout_failed")},
                     "rel_truth": sum(rel[key]) / len(rel[key]) if rel.get(key) else None,
                     "mean_d": sum(ad[key]) / len(ad[key]) if ad.get(key) else None})
    return {"seed": seed, "pair": pair, "plate": plate, "printer": printer, "scores": rows}


def jobs(n):
    return [(s, pair, pl, pr) for s in range(n) for pair in PAIRS for pl, pr in CONDS]


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    todo = jobs(n)
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        futs = {ex.submit(one, j): j for j in todo}
        for fut in as_completed(futs):
            try:
                f.write(json.dumps(fut.result()) + "\n"); f.flush()
            except Exception as e:  # a condition that breaks the model is a finding, not a crash
                f.write(json.dumps({"job": futs[fut], "error": repr(e)}) + "\n"); f.flush()
    print("DONE", len(todo), round(time.time() - t0), flush=True)
