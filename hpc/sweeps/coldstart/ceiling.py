"""Cold start: how much can sharing gain, and which levers raise it? Exploratory; sim only.

Runs the frozen config with two extra diagnostic predictors scored next to the three arms
(they choose no pieces and change nothing the arms do):

  true_theta    the site's true parameters: error from effects the model doesn't have (the
                radial plate term). Not a strict floor: fitted parameters can absorb part of it.
  known_shared  the isolated arm's data plus the site's true shared parameters, as a tight
                Gaussian (0.1 prior std, trust 1). The most any sharing of shared-parameter
                summaries could give that site.

So isolated - known_shared is the gain available to sharing and isolated - networked is
what the network gets of it.

    PYTHONPATH=. .venv/bin/python hpc/sweeps/coldstart/ceiling.py OUT.jsonl CELLSET [WORLD_SCALE]
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "relevance"))
from frozen import frozen_config  # noqa: E402

from arms import experiment  # noqa: E402
from model import physics  # noqa: E402
from model.physics import PieceArrays  # noqa: E402
from sim.reference import make_world  # noqa: E402

TIGHT = 0.1  # known_shared factor std, in prior stds
_PRINTERS: dict = {}
_orig_score = experiment._score


def _score_plus(r, st, pieces, oracle_post, cfg, rng, res):
    _orig_score(r, st, pieces, oracle_post, cfg, rng, res)
    pr = _PRINTERS[st.site]
    ok = [p for p, m in st.escrow if m.status == "ok" and p.piece_id in st.truth]
    truth = np.array([st.truth[p.piece_id] for p in ok])
    x = PieceArrays.from_pieces(ok)
    floor = physics.predict_d(st.process, x, pr.theta[None, :])[0]
    ix = physics.index(st.process)
    means = {s.name: float(pr.theta[ix[s.name]]) for s in physics.SHARED}
    cov = np.diag([(TIGHT * s.prior_std) ** 2 for s in physics.SHARED])
    post = st.posterior(st.process, pieces, n=cfg.n_particles, seed=int(rng.integers(2**31)), mh_steps=cfg.mh_steps)
    # Draw the shared columns from the factor itself (reweighting prior draws by a factor
    # this tight leaves a handful of particles), then register it for the MH moves.
    new = post.layout.shared_factor(means, cov, 1.0)
    cols, mu = new[0], new[1]
    for j, c in enumerate(cols):
        spec = post.specs[c]
        post.theta[:, c] = np.clip(mu[j] + np.sqrt(cov[j, j]) * post.rng.standard_normal(post.n), spec.lo, spec.hi)
    post._extra_priors["truth"] = new
    post.update([m for _, m in st.data["isolated"]])
    known = np.array([post.predict(p)[0] for p in ok])
    for arm, pred in (("true_theta", floor), ("known_shared", known)):
        res.scores.append({"round": r, "site": st.site, "arm": arm, "mae_truth": float(np.mean(np.abs(pred - truth)))})


experiment._score = _score_plus

# Knob msg_proposal: draw the shared columns from prior x (trust-weighted message factors)
# instead of reweighting prior draws by them. Exact for the Gaussian part of the prior;
# avoids collapsing to a few particles when many sites send tight summaries.
_MSG_PROPOSAL = False
_orig_fit = experiment._fit


def _fit_proposal(st, pieces, data, cfg, rng, messages=None):
    if not (_MSG_PROPOSAL and messages):
        return _orig_fit(st, pieces, data, cfg, rng, messages)
    post = _orig_fit(st, pieces, [], cfg, rng, messages)
    if post._extra_priors:
        names = [n for n, t in zip(post.names, post.tags) if t == "shared"]
        cols = np.array([post.names.index(n) for n in names])
        specs = [post.specs[c] for c in cols]
        P = np.diag([1 / sp.prior_std**2 for sp in specs])
        h = P @ np.array([sp.prior_mean for sp in specs])
        where = {c: i for i, c in enumerate(cols)}
        for fc, mu, prec, w in post._extra_priors.values():
            ix = [where[c] for c in fc]
            P[np.ix_(ix, ix)] += w * prec
            h[ix] += w * prec @ mu
        cov = np.linalg.inv(P)
        draw = post.rng.multivariate_normal(cov @ h, cov, post.n)
        lo, hi = np.array([sp.lo for sp in specs]), np.array([sp.hi for sp in specs])
        post.theta[:, cols] = np.clip(draw, lo, hi)
        post.logw = np.full(post.n, -np.log(post.n))
    post.update([m for _, m in data])
    return post


experiment._fit = _fit_proposal


def sites_n(n):
    return {f"{p}{i}": p for i in range(n // 2) for p in ("resin", "pla")}


CELLSETS = {
    # data poverty x network size
    "grid": [dict(n=n, seed_pieces=sp, slots=sl) for n in (2, 4) for sp in (0, 4, 16) for sl in (2, 6)]
            + [dict(n=8, seed_pieces=sp, slots=2) for sp in (0, 4)],
    # method knobs at a data-poor 2-site and 4-site setting
    "knobs": [dict(n=n, seed_pieces=4, slots=2, **kw) for n in (2, 4) for kw in (
        dict(between_site_sd=0.1), dict(between_site_sd=0.5), dict(between_site_sd=0.0),
        dict(discount=0.0), dict(discount=0.5), dict(msg_proposal=True))]
            + [dict(n=8, seed_pieces=4, slots=2, msg_proposal=True)],
}


def one(job):
    cell, seed, rounds = job
    global _MSG_PROPOSAL
    kw = {k: v for k, v in cell.items() if k not in ("n", "seed_pieces", "slots", "msg_proposal")}
    _MSG_PROPOSAL = cell.get("msg_proposal", False)
    sites = sites_n(cell["n"])
    world = make_world(sites, seed)
    _PRINTERS.clear()
    _PRINTERS.update(world)
    cfg = frozen_config(rounds=rounds, seed=seed, seed_pieces=cell["seed_pieces"], slots_per_arm=cell["slots"], **kw)
    res = experiment.run_experiment(world, sites, cfg)
    return {"cell": cell, "seed": seed,
            "scores": [{k: s[k] for k in ("round", "site", "arm", "mae_truth")} for s in res.scores]}


if __name__ == "__main__":
    out, cellset = sys.argv[1], sys.argv[2]
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    worlds = {2: 60, 4: 40, 8: 20}  # bigger networks cost ~n^2 per run
    rounds = int(os.environ.get("ROUNDS", 5))
    done_keys = set()
    if os.path.exists(out):
        for line in open(out):
            d = json.loads(line)
            done_keys.add((json.dumps(d["cell"], sort_keys=True), d["seed"]))
    jobs = [(c, s, rounds) for c in CELLSETS[cellset] for s in range(int(worlds[c["n"]] * scale))
            if (json.dumps(c, sort_keys=True), s) not in done_keys]
    jobs.sort(key=lambda j: -j[0]["n"])  # big networks first
    t0, done = time.time(), 0
    with ProcessPoolExecutor(int(os.environ.get("WORKERS", os.cpu_count()))) as ex, open(out, "a") as f:
        for fut in as_completed([ex.submit(one, j) for j in jobs]):
            f.write(json.dumps(fut.result()) + "\n"); f.flush(); done += 1
            if done % 20 == 0:
                print(f"{done}/{len(jobs)} runs, {time.time() - t0:.0f}s", flush=True)
    print("DONE", time.time() - t0, flush=True)
