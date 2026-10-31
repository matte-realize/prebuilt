"""Caliper and pin-gauge entry, plus scanner agreement checks.

CSV columns: row, col, measured_d, status   (status: ok | failed; measured_d blank if failed)
Pieces are identified by grid position, matching the plate files.
"""
from __future__ import annotations

import csv
from dataclasses import replace

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


def scanner_offsets(scanner: list[Measurement], caliper: list[Measurement], plate: Plate, min_pairs: int = 3) -> dict[str, float]:
    """Per-kind scanner bias (median scanner - caliper) from the spot checks on one plate.

    Synthetic stress tests show front-lit pin scans lose ~40-50 um to cast
    shadows, nearly constant across pieces (spread 8-15 um). Kinds with fewer
    than `min_pairs` checks are left uncorrected.
    """
    kind = {p.piece_id: p.kind for p in plate.pieces}
    s = {m.piece_id: m.measured_d for m in scanner if m.status == "ok"}
    diffs: dict[str, list[float]] = {}
    for m in caliper:
        if m.status == "ok" and m.piece_id in s:
            diffs.setdefault(kind[m.piece_id], []).append(s[m.piece_id] - m.measured_d)
    return {k: float(np.median(v)) for k, v in diffs.items() if len(v) >= min_pairs}


def apply_offsets(scanner: list[Measurement], offsets: dict[str, float], plate: Plate) -> list[Measurement]:
    kind = {p.piece_id: p.kind for p in plate.pieces}
    return [replace(m, measured_d=m.measured_d - offsets[kind[m.piece_id]], method=f"{m.method}+caliper-offset")
            if m.status == "ok" and kind[m.piece_id] in offsets else m
            for m in scanner]


def sample_for_caliper(plate: Plate, k: int = 10, seed: int = 0) -> list[tuple[int, int]]:
    """Random slots to caliper-check (walkthrough: about 10 per plate), split evenly
    between pins and holes so each kind gets enough checks for scanner_offsets."""
    rng = np.random.default_rng(seed)
    out = []
    kinds = sorted({p.kind for p in plate.pieces})
    for i, kind in enumerate(kinds):
        pool = [p.slot for p in plate.pieces if p.kind == kind]
        n = min(len(pool), k // len(kinds) + (i < k % len(kinds)))
        out += [pool[j] for j in rng.choice(len(pool), size=n, replace=False)]
    return sorted(out)
