"""Turn a list of (candidate, arm) items into a `Plate` with seeded random placement."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from contracts import Piece, Plate
from plates import spec
from plates.library import Candidate

Item = tuple[Candidate, str]  # (geometry, arm)


def piece_id(plate_id: str, slot: tuple[int, int]) -> str:
    return f"{plate_id}-r{slot[0]}c{slot[1]}"


def build_plate(
    plate_id: str,
    site: str,
    items: list[Item],
    seed: int,
    fixed: dict[tuple[int, int], Item] | None = None,
) -> Plate:
    """Place `fixed` items at their slots, then shuffle `items` into the remaining slots."""
    return build_plate_indexed(plate_id, site, items, seed, fixed)[0]


def build_plate_indexed(
    plate_id: str,
    site: str,
    items: list[Item],
    seed: int,
    fixed: dict[tuple[int, int], Item] | None = None,
) -> tuple[Plate, dict[str, int]]:
    """Like `build_plate`, also returning piece_id -> index into `items` (fixed pieces omitted)."""
    fixed = fixed or {}
    free = [s for s in spec.all_slots() if s not in fixed]
    if len(items) > len(free):
        raise ValueError(f"{len(items)} items but only {len(free)} free slots on {plate_id}")
    order = np.random.default_rng(seed).permutation(len(free))
    placed = dict(fixed)
    index = {}
    for i, (item, k) in enumerate(zip(items, order)):
        placed[free[k]] = item
        index[piece_id(plate_id, free[k])] = i
    pieces = [
        Piece(piece_id(plate_id, slot), c.kind, c.nominal_d, slot, arm)
        for slot, (c, arm) in sorted(placed.items())
    ]
    return Plate(plate_id, site, pieces, seed), index


def plate_to_dict(p: Plate) -> dict:
    return {
        "plate_id": p.plate_id,
        "site": p.site,
        "seed": p.seed,
        "pieces": [
            {"piece_id": x.piece_id, "kind": x.kind, "nominal_d": x.nominal_d, "slot": list(x.slot), "arm": x.arm}
            for x in p.pieces
        ],
    }


def plate_from_dict(d: dict) -> Plate:
    pieces = [Piece(x["piece_id"], x["kind"], x["nominal_d"], tuple(x["slot"]), x["arm"]) for x in d["pieces"]]
    return Plate(d["plate_id"], d["site"], pieces, d["seed"])


def save_plate(p: Plate, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(plate_to_dict(p), indent=1))


def load_plate(path: str | Path) -> Plate:
    return plate_from_dict(json.loads(Path(path).read_text()))
