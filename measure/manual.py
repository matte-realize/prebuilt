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
    """Caliper checks for one plate. Rows that can't be used are skipped with a printed warning
    instead of stopping the run mid-round (blank rows, unknown slots, unreadable numbers)."""
    by_slot = {p.slot: p for p in plate.pieces}
    out = []
    with open(path, newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            cells = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not any(cells.values()):
                continue
            try:
                p = by_slot[(int(cells.get("row", "")), int(cells.get("col", "")))]
            except (KeyError, ValueError):
                print(f"  {path} line {n}: no piece at row={cells.get('row')!r} col={cells.get('col')!r}, skipped")
                continue
            status = cells.get("status", "").lower() or "ok"
            d = None
            if status == "ok":
                try:
                    d = float(cells.get("measured_d", ""))
                except ValueError:
                    print(f"  {path} line {n}: measured_d {cells.get('measured_d')!r} isn't a number, skipped")
                    continue
            elif status != "failed":
                print(f"  {path} line {n}: status {status!r} should be ok or failed, skipped")
                continue
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
    kind = {p.piece_id: p.kind for p in plate.pieces if p.arm != "heldout"}  # held-out: scoring only
    s = {m.piece_id: m.measured_d for m in scanner if m.status == "ok"}
    diffs: dict[str, list[float]] = {}
    for m in caliper:
        if m.status == "ok" and m.piece_id in s and m.piece_id in kind:
            diffs.setdefault(kind[m.piece_id], []).append(s[m.piece_id] - m.measured_d)
    return {k: float(np.median(v)) for k, v in diffs.items() if len(v) >= min_pairs}


def apply_offsets(scanner: list[Measurement], offsets: dict[str, float], plate: Plate) -> list[Measurement]:
    kind = {p.piece_id: p.kind for p in plate.pieces}
    return [replace(m, measured_d=m.measured_d - offsets[kind[m.piece_id]], method=f"{m.method}+caliper-offset")
            if m.status == "ok" and kind[m.piece_id] in offsets else m
            for m in scanner]


def sample_for_caliper(plate: Plate, k: int = 10, seed: int = 0) -> list[tuple[int, int]]:
    """Random slots to caliper-check (about 10 per plate), split evenly
    between pins and holes so each kind gets enough checks for scanner_offsets. Held-out
    pieces are left out: their measurements must not shape the training data."""
    rng = np.random.default_rng(seed)
    out = []
    train = [p for p in plate.pieces if p.arm != "heldout"]
    kinds = sorted({p.kind for p in train})
    for i, kind in enumerate(kinds):
        pool = [p.slot for p in train if p.kind == kind]
        n = min(len(pool), k // len(kinds) + (i < k % len(kinds)))
        out += [pool[j] for j in rng.choice(len(pool), size=n, replace=False)]
    return sorted(out)
