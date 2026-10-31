"""Caliper and pin-gauge entry, plus scanner agreement checks.

CSV columns: row, col, measured_d, status   (status: ok | failed; measured_d blank if failed)
Pieces are identified by grid position, matching the plate files.
"""
from __future__ import annotations

import csv

import numpy as np

from contracts import Measurement, Plate

MM_PER_IN = 25.4


def load_caliper_csv(path: str, plate: Plate) -> list[Measurement]:
    by_slot = {p.slot: p for p in plate.pieces}
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            p = by_slot[(int(row["row"]), int(row["col"]))]
            status = row.get("status", "ok").strip() or "ok"
            d = float(row["measured_d"]) if status == "ok" and row["measured_d"].strip() else None
            out.append(Measurement(p.piece_id, plate.plate_id, plate.site, d, "ok" if d is not None else "failed", "caliper"))
    return out


def agreement(scanner: list[Measurement], caliper: list[Measurement]) -> dict:
    """Scanner vs caliper on the pieces both measured: bias, MAE, n."""
    s = {m.piece_id: m.measured_d for m in scanner if m.status == "ok"}
    pairs = [(s[m.piece_id], m.measured_d) for m in caliper if m.status == "ok" and m.piece_id in s]
    if not pairs:
        return {"n": 0}
    diff = np.array([a - b for a, b in pairs])
    return {"n": len(pairs), "bias": float(diff.mean()), "mae": float(np.abs(diff).mean()), "max": float(np.abs(diff).max())}


def sample_for_caliper(plate: Plate, k: int = 10, seed: int = 0) -> list[tuple[int, int]]:
    """Random slots to caliper-check (walkthrough: about 10 per plate)."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(plate.pieces), size=min(k, len(plate.pieces)), replace=False)
    return sorted(plate.pieces[i].slot for i in idx)
