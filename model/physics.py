"""Physics forward models for resin (SLA) and PLA (FDM) pin/hole diameters.

Every function is vectorized over particles: `theta` is [N, P] in the column
order of `PARAMS[process]`, and the result is [N, M] for M pieces. Each
parameter is tagged "shared" (process-agnostic, may cross a site boundary as a
posterior summary) or "site" (never leaves the site).

Priors are generic and deliberately wide: the models don't need a printer's exact
settings, because the seed plate learns them. They allow roughly -0.35..0 mm on resin
holes, -0.1..+0.27 mm on resin pins, -0.63..+0.09 mm on PLA holes and up to +0.5 mm on
PLA pins (1st-99th percentile), with hard bounds well beyond. RESIN_EXPOSURE only sets
the scale of the learned Ec, since bleed depends on ln(E / Ec). What the priors can't
guarantee is that a real printer lies inside them; `python -m eval.prior_check` checks
that on the real seed data (and `run.py --source real` runs it after the seed plate).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from contracts import ParamSpec, Piece

from plates.spec import GRID  # plate slot grid (rows, cols); positions are normalized to [-1, 1]

# Process-agnostic terms, identical across processes so summaries are comparable.
SHARED = [
    ParamSpec("size_coef", 0.0, 0.05, -0.3, 0.3, "shared"),  # mm^2; adds size_coef / d
    ParamSpec("pos_gx", 0.0, 0.03, -0.15, 0.15, "shared"),   # mm across the plate, column axis
    ParamSpec("pos_gy", 0.0, 0.03, -0.15, 0.15, "shared"),   # mm across the plate, row axis
]

# Resin: Jacobs working curve Cd = Dp * ln(E / Ec); lateral bleed scales with Cd.
RESIN_EXPOSURE = 25.0  # mJ/cm^2, nominal; only sets the scale of the learned Ec
RESIN = [
    ParamSpec("Dp", 0.15, 0.04, 0.03, 0.4, "site"),       # mm, penetration depth
    ParamSpec("Ec", 7.0, 2.0, 1.0, 20.0, "site"),         # mJ/cm^2, critical exposure (< E)
    ParamSpec("k_bleed", 0.25, 0.1, 0.0, 1.0, "site"),    # lateral bleed per unit cure depth
    ParamSpec("shrink", 0.01, 0.005, -0.01, 0.04, "site"),  # isotropic cure shrinkage
    ParamSpec("sigma_meas", 0.03, 0.015, 0.005, 0.15, "site"),  # mm, measurement noise
]

# PLA: extrusion width offset, small-hole polygon shrink, first-layer flare on pins.
PLA = [
    ParamSpec("w_off", 0.05, 0.05, -0.1, 0.25, "site"),   # mm per wall, extrusion width error
    ParamSpec("poly_k", 0.3, 0.15, 0.0, 1.0, "site"),     # mm^2; holes shrink by poly_k / d
    ParamSpec("flare", 0.1, 0.08, 0.0, 0.5, "site"),      # mm, first-layer flare on pins
    ParamSpec("sigma_meas", 0.04, 0.02, 0.005, 0.2, "site"),
]

PARAMS: dict[str, list[ParamSpec]] = {"resin": RESIN + SHARED, "pla": PLA + SHARED}


def names(process: str) -> list[str]:
    return [p.name for p in PARAMS[process]]


def index(process: str) -> dict[str, int]:
    return {n: i for i, n in enumerate(names(process))}


@dataclass
class PieceArrays:
    """Column view of a list of pieces, for vectorized prediction."""
    d: np.ndarray        # [M] nominal diameter, mm
    is_hole: np.ndarray  # [M] bool
    u: np.ndarray        # [M] column position in [-1, 1]
    v: np.ndarray        # [M] row position in [-1, 1]

    @classmethod
    def from_pieces(cls, pieces: list[Piece], grid: tuple[int, int] = GRID) -> PieceArrays:
        rows, cols = grid
        r = np.array([p.slot[0] for p in pieces], float)
        c = np.array([p.slot[1] for p in pieces], float)
        return cls(
            d=np.array([p.nominal_d for p in pieces], float),
            is_hole=np.array([p.kind == "hole" for p in pieces]),
            u=(c - (cols - 1) / 2) / max((cols - 1) / 2, 1),
            v=(r - (rows - 1) / 2) / max((rows - 1) / 2, 1),
        )


def predict_d(process: str, x: PieceArrays, theta: np.ndarray) -> np.ndarray:
    """Noise-free predicted measured diameter, [N, M].

    Every term is (a function of the particle) x (a function of the piece), so the
    prediction is one matrix product of per-particle coefficients [N, K] and per-piece
    features [K, M]. Same model as written out term by term:

      resin: d (1 - shrink) +- 2 k_bleed Dp ln(E / Ec)            (+ pin, - hole)
      pla:   hole d - 2 w_off - poly_k / d,  pin d + 2 w_off + flare
      both:  + size_coef / d + pos_gx u + pos_gy v
    """
    ix = index(process)
    col = lambda name: theta[:, ix[name]]  # [N]
    d = x.d
    sign = np.where(x.is_hole, -1.0, 1.0)  # [M]
    if process == "resin":
        bleed = col("k_bleed") * col("Dp") * np.log(RESIN_EXPOSURE / col("Ec"))
        coef = [1 - col("shrink"), 2 * bleed]
        feat = [d, sign]
    elif process == "pla":
        coef = [np.ones(theta.shape[0]), 2 * col("w_off"), col("poly_k"), col("flare")]
        feat = [d, sign, -x.is_hole.astype(float) / d, (~x.is_hole).astype(float)]
    else:
        raise ValueError(f"unknown process {process!r}")
    coef += [col("size_coef"), col("pos_gx"), col("pos_gy")]
    feat += [1 / d, x.u, x.v]
    return np.stack(coef, axis=1) @ np.stack(feat, axis=0)


def sigma(process: str, theta: np.ndarray) -> np.ndarray:
    """Measurement noise std per particle, [N]."""
    return theta[:, index(process)["sigma_meas"]]


def _specs(process_or_specs: str | list[ParamSpec]) -> list[ParamSpec]:
    return PARAMS[process_or_specs] if isinstance(process_or_specs, str) else process_or_specs


def sample_prior(process: str | list[ParamSpec], n: int, rng: np.random.Generator) -> np.ndarray:
    """Truncated-normal draws from the priors, [n, P]."""
    specs = _specs(process)
    out = np.empty((n, len(specs)))
    for j, s in enumerate(specs):
        if s.prior_std > 10 * (s.hi - s.lo):  # effectively flat: uniform within bounds
            out[:, j] = rng.uniform(s.lo, s.hi, n)
            continue
        col = rng.normal(s.prior_mean, s.prior_std, n)
        bad = (col < s.lo) | (col > s.hi)
        while bad.any():
            col[bad] = rng.normal(s.prior_mean, s.prior_std, bad.sum())
            bad = (col < s.lo) | (col > s.hi)
        out[:, j] = col
    return out


def log_prior(process: str | list[ParamSpec], theta: np.ndarray) -> np.ndarray:
    """Unnormalized truncated-normal log prior, [N]; -inf outside bounds."""
    specs = _specs(process)
    mean = np.array([s.prior_mean for s in specs])
    std = np.array([s.prior_std for s in specs])
    lo = np.array([s.lo for s in specs])
    hi = np.array([s.hi for s in specs])
    lp = -0.5 * (((theta - mean) / std) ** 2).sum(axis=1)
    inside = ((theta >= lo) & (theta <= hi)).all(axis=1)
    return np.where(inside, lp, -np.inf)
