"""Fit-class accuracy (docs/spec/04-physics-models.md 7.4).

Clearance = hole diameter - pin diameter. Classes come from the prereg thresholds
per process:  press: c < press_below,  slip: lo <= c <= hi,  loose: c > loose_above.
(Clearances in a gap between press_below and slip lo, or slip hi and loose_above, are
assigned to the nearer class.)

Pairs: every held-out pin with every held-out hole at the same site scored in the
same round. Held-out sizes are spread out, so most pairs are trivially loose or
press. Only pairs whose *nominal* clearance lies within one slip-band width of the
class boundaries are scored; that rule depends only on the prereg thresholds and the
plate design, never on measurements.

A pair is correct when the class of the predicted clearance (posterior means)
matches the class of the measured clearance. In simulation, `truth` scores against
the noise-free clearance instead.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import product


def classify(c: float, th: dict) -> str:
    lo, hi = th["slip"]
    if c < th["press_below"]:
        return "press"
    if c > th["loose_above"]:
        return "loose"
    if lo <= c <= hi:
        return "slip"
    if c < lo:  # between press_below and the slip band
        return "press" if c - th["press_below"] < lo - c else "slip"
    return "loose" if th["loose_above"] - c < c - hi else "slip"


def scored_window(th: dict) -> tuple[float, float]:
    lo, hi = th["slip"]
    w = hi - lo
    return th["press_below"] - w, th["loose_above"] + w


def fit_accuracy(predictions: list[dict], thresholds: dict[str, dict], processes: dict[str, str],
                 truth: bool = False) -> list[dict]:
    """One row per (round, site, arm): accuracy and pair count. `thresholds` maps process -> classes."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in predictions:
        groups[(p["round"], p["site"], p["arm"])].append(p)
    rows = []
    for (r, site, arm), ps in sorted(groups.items()):
        th = thresholds[processes[site]]
        w0, w1 = scored_window(th)
        obs_key = "truth" if truth else "measured_d"
        pins = [p for p in ps if p["kind"] == "pin" and p.get(obs_key) is not None]
        holes = [p for p in ps if p["kind"] == "hole" and p.get(obs_key) is not None]
        hits = n = 0
        for pin, hole in product(pins, holes):
            if not w0 <= hole["nominal_d"] - pin["nominal_d"] <= w1:
                continue
            n += 1
            hits += classify(hole["mean"] - pin["mean"], th) == classify(hole[obs_key] - pin[obs_key], th)
        rows.append({"round": r, "site": site, "arm": arm, "fit_acc": hits / n if n else None, "fit_pairs": n})
    return rows
