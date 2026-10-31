"""Candidate piece library, precomputed once. Agents choose from this; nothing else."""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from plates import spec


@dataclass(frozen=True)
class Candidate:
    kind: str          # "pin" | "hole"
    nominal_d: float   # mm

    @property
    def key(self) -> str:
        return f"{self.kind}-{self.nominal_d:.1f}"


@lru_cache(maxsize=None)
def candidates(train_only: bool = True) -> tuple[Candidate, ...]:
    lo, hi = spec.TRAIN_RANGE if train_only else (spec.D_MIN, spec.D_MAX)
    n = round((hi - lo) / spec.D_STEP)
    ds = [round(lo + i * spec.D_STEP, 1) for i in range(n + 1)]
    return tuple(Candidate(k, d) for k in ("pin", "hole") for d in ds)


def print_cost(c: Candidate) -> float:
    """Relative print cost: material volume added above the plate (pins only), in mm^3.

    Holes remove material, so they cost nothing beyond the plate itself.
    """
    if c.kind == "hole":
        return 0.0
    return math.pi * (c.nominal_d / 2) ** 2 * spec.PIN_H
