"""Prototype: quarantine incoming notes that contradict the receiver's own data. Exploratory, simulation only.

After each broadcast, every receiver compares each incoming shared-parameter summary with its own
local posterior (own data, no messages). Per parameter, z = (m_in - m_own) / sqrt(v_in + v_own + s_b^2),
with s_b = between_site_sd * prior std (the spread between sites the model already allows).
If sum z^2 exceeds the chi-square 0.999 quantile, the note is dropped for that round. Trust is left
alone, so a sender is re-checked every round. Monkeypatched onto arms.experiment; no repo code changes.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/consistency.py 100 hpc/sweeps/relevance/results/consistency.jsonl
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

SITES = {"resin": "resin", "pla": "pla"}
ROUNDS = 3
CHI2_999 = {1: 10.83, 2: 13.82, 3: 16.27}
_ORIG = None
LOG = []


def _set_check(on: bool) -> None:
    global _ORIG
    import arms.experiment as X
    from model.physics import SHARED
    if _ORIG is None:
        _ORIG = X._broadcast
    if not on:
        X._broadcast = _ORIG
        return
    std = {p.name: p.prior_std for p in SHARED}

    def broadcast(r, sites, pieces, cfg, rng):
        _ORIG(r, sites, pieces, cfg, rng)
        for name, st in sites.items():
            own, _, _ = X._fit(st, pieces, st.data["networked"], cfg, np.random.default_rng([cfg.seed, r, 7])).summary("shared")
            for snd in list(st.inbox):
                msg = st.inbox[snd]
                if msg.round != r:
                    continue
                z2 = [(m - own[k][0]) ** 2 / (v + own[k][1] + (cfg.between_site_sd * std[k]) ** 2)
                      for k, (m, v) in msg.shared_params.items() if k in own]
                stat = float(np.sum(z2))
                bad = bool(z2) and stat > CHI2_999[min(len(z2), 3)]
                LOG.append({"round": r, "receiver": name, "sender": snd, "chi2": stat, "dropped": bad})
                if bad:
                    del st.inbox[snd]
    X._broadcast = broadcast


def one(job):
    seed, cond, check = job
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import make_world
    _set_check(check)
    LOG.clear()
    cfg = frozen_config(rounds=ROUNDS, seed=seed, share_messages=cond != "alone", bad_sites=("pla",) if cond == "liar" else ())
    res = run_experiment(make_world(SITES, seed), SITES, cfg)
    return {"seed": seed, "cond": cond, "check": check, "checks": list(LOG),
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth")} for r in res.scores]}


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    jobs = [(s, c, chk) for s in range(n) for c, chk in (("normal", False), ("normal", True), ("liar", False), ("liar", True), ("alone", False))]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
    print("DONE", round(time.time() - t0), flush=True)
