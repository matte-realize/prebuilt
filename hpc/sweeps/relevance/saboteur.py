"""Does the agent market protect a site from a bad agent? Exploratory, simulation only.

One agent ("geometry") is replaced by a saboteur that always proposes the least informative
pieces. It sits in every arm (same agents everywhere). Within a run, isolated clears at uniform
credibility and networked at learned credibility (frozen config), so with messages cut the two
arms differ only in credibility.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/relevance/saboteur.py 100 hpc/sweeps/relevance/results/saboteur.jsonl
"""
import json, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

SITES = {"resin": "resin", "pla": "pla"}
ROUNDS = 5
SAB = "geometry"


_HONEST = None


def _set_saboteur(on: bool) -> None:
    """Install or remove the saboteur. Workers are reused across jobs, so every job sets this explicitly."""
    global _HONEST
    import arms.experiment as X
    from agents.selection import candidate_eig
    from plates.library import candidates
    if _HONEST is None:
        _HONEST = X.propose
    if not on:
        X.propose = _HONEST
        return
    honest = _HONEST

    def propose(agent, k, posts, data, discount, site=None):
        if agent != SAB:
            return honest(agent, k, posts, data, discount, site)
        cands = list(candidates())
        eig = candidate_eig(posts["all"], cands, site)
        return [cands[i] for i in eig.argsort()[:k]]  # least informative first
    X.propose = propose


def one(job):
    seed, sab, share = job
    _set_saboteur(sab)
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arms.experiment import run_experiment
    from frozen import frozen_config
    from sim.reference import make_world
    res = run_experiment(make_world(SITES, seed), SITES, frozen_config(rounds=ROUNDS, seed=seed, share_messages=share))
    share_by_round = []
    for site, ch in res.chains.items():
        for i, e in enumerate(x for x in ch.entries() if x["kind"] == "clearing"):
            al = e["payload"]["allocation"]
            share_by_round.append({"site": site, "round": i + 1, "sab_slots": al.get(SAB, 0), "slots": sum(al.values())})
    cred = [{"round": r["round"], "site": r["site"], "sab": r.get(SAB)} for r in res.credibility]
    return {"seed": seed, "sab": sab, "share": share, "cred": cred, "alloc": share_by_round,
            "scores": [{k: r[k] for k in ("round", "site", "arm", "mae", "mae_truth")} for r in res.scores]}


if __name__ == "__main__":
    n, out = int(sys.argv[1]), sys.argv[2]
    jobs = [(s, sab, share) for s in range(n) for sab in (False, True) for share in (False, True)]
    t0 = time.time()
    with ProcessPoolExecutor() as ex, open(out, "w") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush()
    print("DONE", round(time.time() - t0), flush=True)
