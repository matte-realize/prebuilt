"""Calibrate the corrected-design interval. Simulation only.

For each world and site: fit on the full seed plate (1000 particles), ask compensate() for pins and
holes at 2, 3, 5, 7 mm, and record the true printed size at the draw size, the posterior-mean
prediction and the model interval. Worlds 0-29 calibrate the model-discrepancy term; 30-59 test it.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/compensate_calibration.py 60 hpc/sweeps/relevance/results/compensate_calibration.jsonl
"""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

TARGETS = (2.0, 3.0, 5.0, 7.0)


def one(seed):
    import numpy as np
    from model.compensate import compensate, true_d
    from model.posterior import ParticlePosterior
    from plates.seed import seed_plate
    from sim.reference import make_world
    out = []
    for site, sim in make_world({"resin": "resin", "pla": "pla"}, seed).items():
        plate = seed_plate(site, None)
        ms = sim.print_and_measure(plate)
        pieces = {p.piece_id: p for p in plate.pieces}
        post = ParticlePosterior(site, pieces, n=1000, seed=seed)
        post.update([m for m in ms if pieces[m.piece_id].arm == "seed"])
        for kind in ("pin", "hole"):
            for t in TARGETS:
                r = compensate(post, kind, t, k=4000, discrepancy=False)
                out.append({"seed": seed, "site": site, "kind": kind, "target": t, "draw": r["draw_d"],
                            "pred": r["predicted_d"], "model_sd": r["model_sd"],
                            "true": float(true_d(sim, kind, r["draw_d"])[0]),
                            "as_is": float(true_d(sim, kind, t)[0])})
    return out


if __name__ == "__main__":
    n, path = int(sys.argv[1]), sys.argv[2]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(path, "w") as f:
        for fut in as_completed([ex.submit(one, s) for s in range(n)]):
            for row in fut.result():
                f.write(json.dumps(row) + "\n")
    print("DONE", n, round(time.time() - t0), flush=True)
