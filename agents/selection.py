"""Which pieces to print next: expected information gain over the candidate library.

Placement is random, so candidates are scored at the plate center (no
position term). Batches are built greedily with a "believer" step: after
choosing a candidate, the particles are reweighted as if its predicted mean had
been observed, which stops a batch from repeating the same piece.
"""
from __future__ import annotations

import numpy as np

from model.physics import PieceArrays
from model.posterior import ParticlePosterior
from plates.library import Candidate, candidates, print_cost


def candidate_arrays(cands: tuple[Candidate, ...]) -> PieceArrays:
    n = len(cands)
    return PieceArrays(
        d=np.array([c.nominal_d for c in cands]),
        is_hole=np.array([c.kind == "hole" for c in cands]),
        u=np.zeros(n),
        v=np.zeros(n),
    )


def cost_discount(cands: tuple[Candidate, ...], discount: float) -> np.ndarray:
    """Multiplier in [1 - discount, 1]; the costliest piece gets the full discount."""
    cost = np.array([print_cost(c) for c in cands])
    return 1.0 - discount * cost / max(cost.max(), 1e-9)


def eig(mu: np.ndarray, s: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Expected information gain per candidate (Gaussian approximation), [C]."""
    mean = w @ mu
    var_model = w @ (mu - mean) ** 2
    noise = w @ s**2
    return 0.5 * np.log1p(var_model / noise)


def focused_gain(mu: np.ndarray, s: np.ndarray, w: np.ndarray, theta_focus: np.ndarray) -> np.ndarray:
    """Expected fraction of each focus parameter's variance removed by measuring a candidate, summed, [C]."""
    mean = w @ mu
    dmu = mu - mean                                      # [N, C]
    var_y = w @ dmu**2 + w @ s**2                        # [C]
    dth = theta_focus - w @ theta_focus                  # [N, F]
    var_th = w @ dth**2                                  # [F]
    cov = (dth * w[:, None]).T @ dmu                     # [F, C]
    return ((cov**2) / (var_th[:, None] * var_y[None, :] + 1e-30)).sum(axis=0)


def greedy_batch(
    post: ParticlePosterior,
    k: int,
    score: str = "eig",
    focus: list[str | int] | None = None,   # parameter names or theta columns
    discount: float = 0.0,
    site: str | None = None,
    exclude: set[str] | None = None,
) -> list[tuple[Candidate, float]]:
    """Top-k candidates with believer updates between picks. Returns (candidate, score) pairs."""
    cands = candidates()
    x = candidate_arrays(cands)
    mu, s = post.predictive_components(x, site)
    mult = cost_discount(cands, discount)
    logw = post.logw.copy()
    focus_cols = [f if isinstance(f, int) else post.names.index(f) for f in (focus or [])]
    blocked = np.array([c.key in (exclude or set()) for c in cands])
    out = []
    for _ in range(k):
        w = np.exp(logw - logw.max())
        w /= w.sum()
        if score == "focus" and focus_cols:
            sc = focused_gain(mu, s, w, post.theta[:, focus_cols])
        else:
            sc = eig(mu, s, w)
        sc = sc * mult
        sc[blocked] = -np.inf
        j = int(np.argmax(sc))
        out.append((cands[j], float(sc[j])))
        y = w @ mu[:, j]
        logw = logw - 0.5 * ((y - mu[:, j]) / s) ** 2 - np.log(s)
    return out
