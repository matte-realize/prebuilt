"""Held-out set: fixed before the first print, hashed, committed.

Eight fixed slots per plate (one per row and column, so they span the plate
and capture position effects), on every plate, so held-out pieces are spread
across plates and capture drift. A quarter of the geometries fall outside the
range agents may propose (`spec.TRAIN_RANGE`), for the new-geometries claim.
"""
from __future__ import annotations

import hashlib
import json
import zlib

import numpy as np

from plates import spec
from plates.library import Candidate

HELDOUT_SLOTS = [(0, 3), (1, 6), (2, 1), (3, 4), (4, 7), (5, 2), (6, 5), (7, 0)]
PLATES = ["seed", "r1", "r2", "r3", "r4"]   # real plates; r4 is the optional short round
HELDOUT_SEED = 20261030


def plate_geometry(name: str) -> list[Candidate]:
    """8 held-out candidates for plate `name`, in HELDOUT_SLOTS order. Same for every site.

    Deterministic per plate name, so simulated runs with more rounds get more plates
    without changing the real ones.
    """
    rng = np.random.default_rng([HELDOUT_SEED, zlib.crc32(name.encode())])
    lo, hi = spec.TRAIN_RANGE
    geoms = []
    for i in range(len(HELDOUT_SLOTS)):
        kind = "pin" if i % 2 == 0 else "hole"
        if i in (3, 6):  # out of distribution: below or above the training range
            d = rng.uniform(spec.D_MIN, lo - 0.1) if i == 3 else rng.uniform(hi + 0.1, spec.D_MAX)
        else:
            d = rng.uniform(lo, hi)
        geoms.append(Candidate(kind, round(float(d), 1)))
    return geoms


def heldout_geometry() -> dict[str, list[Candidate]]:
    return {name: plate_geometry(name) for name in PLATES}


def heldout_fixed(plate_name: str) -> dict[tuple[int, int], tuple[Candidate, str]]:
    return {s: (c, "heldout") for s, c in zip(HELDOUT_SLOTS, plate_geometry(plate_name))}


def manifest() -> dict:
    g = heldout_geometry()
    body = {
        "slots": [list(s) for s in HELDOUT_SLOTS],
        "plates": {k: [[c.kind, c.nominal_d] for c in v] for k, v in g.items()},
        "seed": HELDOUT_SEED,
    }
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body
