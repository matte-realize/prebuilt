import inspect

import numpy as np
import pytest

wp = pytest.importorskip("warp")
wp.config.quiet = True

from arms.experiment import Config, run_experiment
from model import posterior_warp
from plates.seed import seed_plate
from sim import batch, reference, warp_sim
from tests.test_warp_sim import small_plate

SITES = {"resin": "resin", "pla": "pla"}
SMALL = Config(rounds=1, n_particles=300)
needs_hook = pytest.mark.skipif(
    "posterior" not in inspect.signature(run_experiment).parameters,
    reason="needs the posterior factory hook in arms.run_experiment",
)


def test_site_names():
    assert batch.site_names(2) == SITES  # run.py's sites, so both runners see the same worlds
    assert batch.site_names(5) == {"resin": "resin", "pla": "pla", "resin2": "resin", "pla2": "pla", "resin3": "resin"}


def test_merge_prints_what_each_world_prints_alone():
    seeds = [0, 1, 2]
    alone = [warp_sim.make_world(SITES, s) for s in seeds]
    merged = warp_sim.merge([warp_sim.make_world(SITES, s) for s in seeds])
    for a, m in zip(alone, merged):
        for s in SITES:
            for plate in (seed_plate(s), small_plate(s, 1), small_plate(s, 2)):
                np.testing.assert_array_equal(m[s].truth(plate), a[s].truth(plate))
                np.testing.assert_array_equal(
                    [x.measured_d for x in m[s].print_and_measure(plate)],
                    [x.measured_d for x in a[s].print_and_measure(plate)])


def _seed_data(site: str, seed: int):
    printer = reference.make_world(SITES, seed)[site]
    plate = seed_plate(site)
    return {p.piece_id: p for p in plate.pieces}, printer.print_and_measure(plate)


def test_batched_posterior_matches_warp_posterior():
    # Two fits served in one batch end with the same particles as each fit run alone on the GPU.
    fits = [_seed_data("resin", 0), _seed_data("pla", 1)]
    summary = ({"size_coef": 0.04}, np.array([[0.01**2]]), 0.7, "pla")  # a confident message, forces a resample-move
    b = batch.Batcher()

    def job(i):
        pieces, ms = fits[i]
        post = b.posterior(SITES["resin" if i == 0 else "pla"], pieces, n=500, seed=10 + i)
        if i == 0:
            post.set_prior_from_summary(*summary)
        post.update(ms)
        return post.theta, post.logw

    got = b.run([lambda i=i: job(i) for i in range(2)])
    assert b.launches["fit"] == 1
    for i, (theta, logw) in enumerate(got):
        pieces, ms = fits[i]
        ref = posterior_warp.ParticlePosterior("resin" if i == 0 else "pla", pieces, n=500, seed=10 + i)
        if i == 0:
            ref.set_prior_from_summary(*summary)
        ref.update(ms)
        np.testing.assert_allclose(theta, ref.theta, rtol=0, atol=1e-12)
        np.testing.assert_allclose(logw, ref.logw, rtol=0, atol=1e-12)


def test_batcher_raises_a_job_error_after_the_others_finish():
    b = batch.Batcher()

    def bad():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        b.run([bad, lambda: b.wait("truth", (warp_sim.make_world(SITES, 0)["resin"], seed_plate("resin")))])


@needs_hook
def test_seed_results_do_not_depend_on_batch_mates():
    alone = batch.run_batch([3], SITES, SMALL)[0]
    together = batch.run_batch([1, 3, 2], SITES, SMALL)[1]
    assert together.scores == alone.scores
    assert together.trust == alone.trust


@needs_hook
def test_more_than_two_sites():
    sites = batch.site_names(3)
    res = batch.run_batch([0, 1], sites, SMALL)
    for r in res:
        assert {row["site"] for row in r.scores} == set(sites)
        assert {row["arm"] for row in r.scores} == {"isolated", "networked", "oracle"}
