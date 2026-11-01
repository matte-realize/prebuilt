"""Shared interfaces. Every module depends on these; change them together.

The simulator and the real scanner both implement `Printer`, so nothing
downstream can tell them apart. `Message` is the only thing that crosses a
site boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Piece:
    piece_id: str
    kind: str              # "pin" | "hole"
    nominal_d: float       # mm
    slot: tuple[int, int]  # grid position on plate
    arm: str               # "isolated" | "networked" | "oracle" | "heldout" | "seed"


@dataclass
class Plate:
    plate_id: str
    site: str              # "resin" | "pla"
    pieces: list[Piece]
    seed: int              # placement shuffle seed


@dataclass
class Measurement:
    piece_id: str
    plate_id: str
    site: str
    measured_d: float | None   # None if failed
    status: str                # "ok" | "failed" | "skipped" (hand sheet: printed, not measured)
    method: str                # "scanner" | "caliper" | "sim" | "not-measured" | ...


class Printer(Protocol):
    def print_and_measure(self, plate: Plate) -> list[Measurement]: ...


class Model(Protocol):
    def update(self, ms: list[Measurement]) -> None: ...
    def predict(self, piece: Piece) -> tuple[float, float]: ...  # mean, std


@dataclass
class Message:                 # the ONLY thing that crosses a site boundary
    sender_site: str
    round: int
    shared_params: dict[str, tuple[float, float]]  # process-agnostic only
    credibility: dict[str, float]
    hypotheses: list[str]
    # Unmet-needs entries: {"template", "question", "z"}; z is the only residual summary.
    unmet_needs: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ParamSpec:
    """A model parameter. `tag` decides whether it may ever be shared."""
    name: str
    prior_mean: float
    prior_std: float
    lo: float
    hi: float
    tag: str               # "shared" (process-agnostic) | "site" (never leaves the site)
