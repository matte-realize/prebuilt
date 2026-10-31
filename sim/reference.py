"""NumPy reference simulator implementing `contracts.Printer`.

STAND-IN: the Warp multi-site simulator (teammate, docs/build/06-task-split.md)
replaces this for batched sweeps. Keep this one as the readable reference that
the Warp version must match on the same hidden truth.

Each simulated site draws its own machine parameters. The shared
(process-agnostic) parameters are drawn once per world and perturbed slightly
per site, so they really are mostly shared. Two effects the agents don't
model are added on top: a radial plate-position term and small features
failing to print.
"""
from __future__ import annotations

import zlib
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from contracts import Measurement, Plate
from model import physics
from model.physics import PieceArrays

FAIL_D = {"resin": {"pin": 1.2, "hole": 1.0}, "pla": {"pin": 1.3, "hole": 1.6}}  # mm, 50% failure diameter
FAIL_WIDTH = 0.12  # mm, logistic width of the failure transition


@dataclass
class SimPrinter:
    site: str
    process: str
    theta: np.ndarray                 # hidden truth, PARAMS[process] order
    radial: float                     # mm at the plate corner, unmodeled
    rng: np.random.Generator = field(repr=False)
    # Diagnostic: common random numbers across arms. When set, a piece's failure and
    # noise draws depend only on (plate, kind, diameter, how many times this arm has
    # already printed that geometry on the plate), so two arms printing the same
    # candidates get the same draws. None = one shared stream (the default).
    crn_seed: int | None = None

    def truth(self, plate: Plate) -> np.ndarray:
        """Noise-free diameters including unmodeled effects (for evaluation only)."""
        x = PieceArrays.from_pieces(plate.pieces)
        d = physics.predict_d(self.process, x, self.theta[None, :])[0]
        return d + self.radial * (x.u**2 + x.v**2) / 2

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        d = self.truth(plate)
        sigma = physics.sigma(self.process, self.theta[None, :])[0]
        out = []
        seen: Counter = Counter()
        for p, di in zip(plate.pieces, d):
            rng = self.rng
            if self.crn_seed is not None:
                geom = (p.arm, p.kind, round(p.nominal_d * 10))
                rng = np.random.default_rng([self.crn_seed, zlib.crc32(plate.plate_id.encode()),
                                             int(p.kind == "hole"), geom[2], seen[geom]])
                seen[geom] += 1
            p_fail = 1 / (1 + np.exp((p.nominal_d - FAIL_D[self.process][p.kind]) / FAIL_WIDTH))
            if rng.random() < p_fail:
                out.append(Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "sim"))
            else:
                y = float(di + sigma * rng.standard_normal())
                out.append(Measurement(p.piece_id, plate.plate_id, plate.site, y, "ok", "sim"))
        return out


def make_world(sites: dict[str, str], seed: int, shared_jitter: float = 0.2, radial_std: float = 0.02,
               crn: bool = False) -> dict[str, SimPrinter]:
    """sites: site name -> process. Returns one SimPrinter per site.

    crn=True gives every arm common random numbers for print noise (diagnostic);
    the hidden truth is the same either way.
    """
    rng = np.random.default_rng(seed)
    shared = {s.name: rng.normal(s.prior_mean, s.prior_std) for s in physics.SHARED}
    printers = {}
    for site, proc in sites.items():
        theta = physics.sample_prior(proc, 1, rng)[0]
        for j, s in enumerate(physics.PARAMS[proc]):
            if s.tag == "shared":
                theta[j] = np.clip(shared[s.name] + shared_jitter * s.prior_std * rng.standard_normal(), s.lo, s.hi)
        printers[site] = SimPrinter(site, proc, theta, float(rng.normal(0, radial_std)), np.random.default_rng(rng.integers(2**32)))
    if crn:
        for i, p in enumerate(printers.values()):
            p.crn_seed = int(np.random.default_rng([seed, 0xC4, i]).integers(2**31))
    return printers
