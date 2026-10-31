import numpy as np
import pytest

from contracts import Measurement, Model, Piece
from model import physics
from model.physics import PieceArrays
from model.posterior import ParticlePosterior


def _pieces(rng, n, prefix, arm):
    return [
        Piece(
            f"{prefix}{i}",
            "hole" if i % 2 else "pin",
            float(rng.uniform(1.0, 8.0)),
            (int(rng.integers(0, 8)), int(rng.integers(0, 8))),
            arm,
        )
        for i in range(n)
    ]


def _measure(process, pieces, theta_true, rng):
    x = PieceArrays.from_pieces(pieces)
    mu = physics.predict_d(process, x, theta_true[None, :])[0]
    s = physics.sigma(process, theta_true[None, :])[0]
    y = mu + s * rng.standard_normal(len(pieces))
    return [Measurement(p.piece_id, "plate0", process, float(v), "ok", "sim") for p, v in zip(pieces, y)], y, mu


@pytest.mark.parametrize("process", ["resin", "pla"])
def test_posterior_learns_and_is_calibrated(process):
    rng = np.random.default_rng(1)
    theta_true = physics.sample_prior(process, 1, rng)[0]
    train = _pieces(rng, 60, "t", "seed")
    held = _pieces(rng, 200, "h", "heldout")
    post = ParticlePosterior(process, {p.piece_id: p for p in train + held}, n=4000, seed=2)
    ms, _, _ = _measure(process, train, theta_true, rng)
    _, y_held, mu_held = _measure(process, held, theta_true, rng)

    # Error against the noise-free truth, so the noise floor doesn't mask learning.
    prior_err = np.mean([abs(post.predict(p)[0] - m) for p, m in zip(held, mu_held)])
    prior_lpd = np.mean([post.log_predictive(p, y) for p, y in zip(held, y_held)])

    # Arrive in three chunks, as a plate's measurements stream in.
    for chunk in (ms[:20], ms[20:40], ms[40:]):
        post.update(chunk)

    post_err = np.mean([abs(post.predict(p)[0] - m) for p, m in zip(held, mu_held)])
    post_lpd = np.mean([post.log_predictive(p, y) for p, y in zip(held, y_held)])
    assert post_err < 0.5 * prior_err
    assert post_lpd > prior_lpd

    inside = [lo <= y <= hi for p, y in zip(held, y_held) for lo, hi in [post.predict_interval(p, 0.9)]]
    assert 0.80 <= np.mean(inside) <= 0.97

    # Measurement noise should be recovered to within a factor of ~1.6.
    s_true = theta_true[physics.index(process)["sigma_meas"]]
    s_post = np.exp(post.logw) @ physics.sigma(process, post.theta)
    assert s_true / 1.6 < s_post < s_true * 1.6
    assert post.ess() > 0.3 * post.n


def test_failed_measurements_ignored():
    rng = np.random.default_rng(0)
    pieces = _pieces(rng, 3, "f", "seed")
    post = ParticlePosterior("resin", {p.piece_id: p for p in pieces}, n=500)
    before = post.theta.copy()
    post.update([Measurement("f0", "plate0", "resin", None, "failed", "scanner")])
    assert np.array_equal(before, post.theta)


def test_summary_only_shared():
    rng = np.random.default_rng(0)
    pieces = _pieces(rng, 3, "s", "seed")
    post = ParticlePosterior("pla", {p.piece_id: p for p in pieces}, n=500)
    summ, cov, names = post.summary("shared")
    assert set(summ) == {"size_coef", "pos_gx", "pos_gy"} == set(names)
    assert cov.shape == (3, 3)
    with pytest.raises(ValueError):
        post.set_prior_from_summary({"w_off": 0.0}, np.eye(1), 0.5)


def test_tempered_prior_pulls_shared_params():
    rng = np.random.default_rng(0)
    pieces = _pieces(rng, 3, "s", "seed")
    post = ParticlePosterior("resin", {p.piece_id: p for p in pieces}, n=4000)
    post.set_prior_from_summary({"size_coef": 0.1}, np.array([[0.01**2]]), 1.0)
    mean = post.summary()[0]["size_coef"][0]
    assert abs(mean - 0.1) < 0.02


def test_satisfies_model_protocol():
    post: Model = ParticlePosterior("resin", {}, n=10)
    assert hasattr(post, "update") and hasattr(post, "predict")
