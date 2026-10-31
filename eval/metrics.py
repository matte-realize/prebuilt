"""Held-out metrics across arms, including oracle gap closed.

oracle_gap_closed = (isolated - networked) / (isolated - oracle), for error
metrics (lower is better). For LPD (higher is better) the signs flip, which
gives the same formula. Undefined (NaN) when isolated and oracle are tied.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np


def gap_closed(iso: float, net: float, ora: float) -> float:
    denom = iso - ora
    return (iso - net) / denom if abs(denom) > 1e-12 else math.nan


def by_round(scores: list[dict], metric: str = "mae") -> dict[int, dict[str, float]]:
    """round -> arm -> metric averaged over sites."""
    acc: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in scores:
        if row.get(metric) is not None:
            acc[row["round"]][row["arm"]].append(row[metric])
    return {r: {arm: float(np.mean(v)) for arm, v in arms.items()} for r, arms in sorted(acc.items())}


def oracle_gap_closed(scores: list[dict], metric: str = "mae") -> dict[int, float]:
    return {r: gap_closed(a["isolated"], a["networked"], a["oracle"]) for r, a in by_round(scores, metric).items()}


def summarize(scores: list[dict]) -> str:
    lines = []
    metrics = ["mae", "lpd", "cov90"] + (["fit_acc"] if any(r.get("fit_acc") is not None for r in scores) else [])
    for metric in metrics:
        rounds = by_round(scores, metric)
        for r, arms in rounds.items():
            if len(arms) < 3:
                continue
            gap = gap_closed(arms["isolated"], arms["networked"], arms["oracle"]) if metric in ("mae", "lpd") else math.nan
            cells = "  ".join(f"{a}={arms[a]:.4f}" for a in ("isolated", "networked", "oracle"))
            lines.append(f"{metric:7s} round {r}: {cells}" + (f"  gap_closed={gap:.2f}" if not math.isnan(gap) else ""))
    return "\n".join(lines)


def with_fit(scores: list[dict], predictions: list[dict], thresholds: dict | None, processes: dict[str, str]) -> list[dict]:
    """Score rows with fit_acc / fit_pairs (and fit_acc_truth in simulation) merged in."""
    if not thresholds:
        return scores
    from eval.fit import fit_accuracy
    key = lambda r: (r["round"], r["site"], r["arm"])
    meas = {key(r): r for r in fit_accuracy(predictions, thresholds, processes)}
    true = {key(r): r for r in fit_accuracy(predictions, thresholds, processes, truth=True)}
    out = []
    for row in scores:
        m, t = meas.get(key(row), {}), true.get(key(row), {})
        out.append({**row, "fit_acc": m.get("fit_acc"), "fit_pairs": m.get("fit_pairs"),
                    **({"fit_acc_truth": t["fit_acc"]} if t.get("fit_pairs") else {})})
    return out
