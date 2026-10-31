"""Warp posterior against the NumPy reference: physics, layout, batching, Monte Carlo agreement."""
import numpy as np
import pytest

from tests.conftest import warp_gpu_available

if not warp_gpu_available():
    pytest.skip("no Warp or CUDA GPU", allow_module_level=True)

from model import physics
from model import posterior as reference
from model import posterior_warp as gpu
from tests.test_posterior import _measure, _pieces

ORACLE = {"resin": "resin", "pla": "pla"}


def _world(process, n_train=60, n_held=30, seed=1):
    rng = np.random.default_rng(seed)
    theta_true = physics.sample_prior(process, 1, rng)[0]
    train = _pieces(rng, n_train, f"{process}-t", "seed")
    held = _pieces(rng, n_held, f"{process}-h", "heldout")
    ms, _, _ = _measure(process, train, theta_true, rng)
    return train, held, ms


def _oracle_world():
    worlds = {p: _world(p, seed=i + 1) for i, p in enumerate(ORACLE)}
    pieces = {pc.piece_id: pc for tr, he, _ in worlds.values() for pc in tr + he}
    return worlds, pieces


def test_initial_particles_match_reference():
    for sites in ("resin", "pla", ORACLE):
        ref = reference.ParticlePosterior(sites, {}, n=3000, seed=7, between_site_sd=0.5)
        post = gpu.ParticlePosterior(sites, {}, n=3000, seed=7, between_site_sd=0.5)
        assert np.array_equal(ref.theta, post.theta)
        assert post.names == ref.names and post.tags == ref.tags


@pytest.mark.parametrize("sites", ["resin", "pla", "oracle"])
def test_kernel_physics_matches_numpy(sites):
    """Same particles in, same per-particle predictions out (kernels mirror model/physics.py)."""
    sites = ORACLE if sites == "oracle" else sites
    rng = np.random.default_rng(3)
    held = _pieces(rng, 40, "h", "heldout")
    ref = reference.ParticlePosterior(sites, {}, n=3000, seed=5, between_site_sd=0.5)
    post = gpu.ParticlePosterior(sites, {}, n=3000, seed=5, between_site_sd=0.5)
    for site in ref.sites if ref.single is False else [None]:
        mu_r, s_r = ref.predictive_components(held, site)
        mu_g, s_g = post.predictive_components(held, site)
        np.testing.assert_allclose(mu_g, mu_r, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(s_g, s_r)


def test_batched_member_equals_standalone():
    """A member's result depends only on its own seed and data, not on the rest of the batch."""
    worlds, pieces = _oracle_world()
    (_, _, ms_r), (_, _, ms_p) = worlds["resin"], worlds["pla"]
    batch = gpu.PosteriorBatch(["resin", "pla", ORACLE, "resin"], pieces, [11, 12, 13, 14], n=2000, between_site_sd=0.5)
    batch.update([ms_r[:30], ms_p[:30], ms_r[:30] + ms_p[:30], []])
    batch.update({0: ms_r[30:], 3: ms_r})
    batch[1].set_prior_from_summary({"size_coef": 0.05}, np.array([[0.02**2]]), 0.7, key="resin")

    alone = [gpu.ParticlePosterior(s, pieces, n=2000, seed=sd, between_site_sd=0.5)
             for s, sd in (("resin", 11), ("pla", 12), (ORACLE, 13), ("resin", 14))]
    alone[0].update(ms_r[:30]); alone[0].update(ms_r[30:])
    alone[1].update(ms_p[:30]); alone[1].set_prior_from_summary({"size_coef": 0.05}, np.array([[0.02**2]]), 0.7, key="resin")
    alone[2].update(ms_r[:30] + ms_p[:30])
    alone[3].update(ms_r)
    for i, a in enumerate(alone):
        np.testing.assert_array_equal(batch[i].theta, a.theta)
        np.testing.assert_array_equal(batch[i].logw, a.logw)

    held = worlds["resin"][1]
    means, stds = batch.predict([held, held[:3], [], held])
    assert [len(m) for m in means] == [len(held), 3, 0, len(held)]
    for j, p in enumerate(held[:5]):
        np.testing.assert_allclose((means[0][j], stds[0][j]), batch[0].predict(p), rtol=1e-12)
    np.testing.assert_allclose(batch.ess(), [m.ess() for m in alone], rtol=1e-12)


def _fit(cls, case, seed, n):
    if case == "oracle":
        worlds, pieces = _oracle_world()
        post = cls(ORACLE, pieces, n=n, seed=seed, between_site_sd=0.5)
        for chunk in range(3):
            post.update([m for _, _, ms in worlds.values() for m in ms[20 * chunk : 20 * chunk + 20]])
        return [post.predict(p, site) for site, (_, held, _) in worlds.items() for p in held]
    train, held, ms = _world(case)
    post = cls(case, {p.piece_id: p for p in train + held}, n=n, seed=seed)
    if case == "resin":  # also exercise a message prior on a shared parameter
        post.set_prior_from_summary({"size_coef": 0.02, "pos_gx": 0.0}, np.diag([0.03, 0.02]) ** 2, 0.5, key="pla")
    for chunk in (ms[:20], ms[20:40], ms[40:]):
        post.update(chunk)
    return [post.predict(p) for p in held]


@pytest.mark.parametrize("case", ["resin", "pla", "oracle"])
def test_predictive_agrees_within_monte_carlo_error(case):
    """Predictive means/stds on held-out pieces: Warp vs NumPy, judged against seed-to-seed spread."""
    seeds, n = range(5), 5000
    runs = {cls: np.array([_fit(cls, case, 100 + s, n) for s in seeds])  # [seeds, pieces, (mean, std)]
            for cls in (reference.ParticlePosterior, gpu.ParticlePosterior)}
    ref, gp = runs[reference.ParticlePosterior], runs[gpu.ParticlePosterior]
    diff = gp.mean(0) - ref.mean(0)                                     # [pieces, 2]
    se = np.sqrt(((ref.var(0, ddof=1) + gp.var(0, ddof=1)) / len(seeds)).mean(0))  # pooled over pieces, [2]
    z = diff / se
    assert np.abs(z).max() < 5, z
    assert np.sqrt((z**2).mean(0)).max() < 2.5, z
    # And the agreement is tight in absolute terms: well under the measurement noise.
    assert np.abs(diff[:, 0]).max() < 0.2 * ref[..., 1].mean()
