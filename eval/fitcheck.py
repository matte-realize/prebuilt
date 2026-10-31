"""Hand fit checks against predicted fit classes (spec 7.4, walkthrough measurement step 4).

At the printer, push a few printed pins into printed holes and write what you feel to
`scans/<site>/<plate_id>-fitcheck.csv`:

    pin_row,pin_col,hole_row,hole_col,fit
    2,1,5,2,slip
    0,3,1,6,press

Rows and columns as on the run sheet (pins up, notch toward you, row 0 far). `fit` is
press, slip or loose. The pin and hole can be any two pieces on that plate.

    python -m eval.fitcheck --checkpoint receipts/real/state.pkl --scans scans

For each check it prints the class each arm's model predicts from its posterior means,
the class the scanner measurements imply, and the hand result, then the agreement rate
per arm. Fit classes come from the prereg thresholds.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from eval.fit import classify

CLASSES = ("press", "slip", "loose")


def load_checks(scans: str | Path, state: dict) -> list[dict]:
    """Every usable row of every fitcheck CSV for plates in the run. Bad rows are skipped with a warning."""
    pieces = state["pieces"]
    out = []
    for path in sorted(Path(scans).glob("*/*-fitcheck.csv")):
        plate_id = path.name[: -len("-fitcheck.csv")]
        with open(path, newline="") as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                cells = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                if not any(cells.values()):
                    continue
                try:
                    pin = pieces[f"{plate_id}-r{int(cells['pin_row'])}c{int(cells['pin_col'])}"]
                    hole = pieces[f"{plate_id}-r{int(cells['hole_row'])}c{int(cells['hole_col'])}"]
                except (KeyError, ValueError):
                    print(f"  {path} line {n}: no such piece on {plate_id}, skipped")
                    continue
                fit = cells.get("fit", "").lower()
                if pin.kind != "pin" or hole.kind != "hole" or fit not in CLASSES:
                    print(f"  {path} line {n}: needs a pin, a hole and fit = press|slip|loose, skipped")
                    continue
                out.append({"site": _site(state, plate_id), "plate": plate_id,
                            "pin": pin, "hole": hole, "hand": fit})
    return out


def _site(state: dict, plate_id: str) -> str:
    for s in state["sites"]:
        if plate_id.startswith(f"{s}-"):
            return s
    raise KeyError(plate_id)


def score(state: dict, checks: list[dict], thresholds: dict[str, dict]) -> dict:
    """Predicted (per arm) and scanner-measured class for each check, and agreement with the hand class."""
    from arms.experiment import ARMS, Config, _fit, _fit_oracle
    sites, pieces = state["sites"], state["pieces"]
    names = {f.name for f in dataclasses.fields(Config)}
    cfg = Config(**{k: tuple(v) if isinstance(v, list) else v for k, v in state["res"].config.items() if k in names})
    rng = np.random.default_rng(20261101)
    models = {}
    for s, st in sites.items():
        models[(s, "isolated")] = (_fit(st, pieces, st.data["isolated"], cfg, rng), None)
        models[(s, "networked")] = (_fit(st, pieces, st.data["networked"], cfg, rng, st.inbox), None)
    oracle = _fit_oracle(sites, pieces, cfg, rng)
    measured = {m.piece_id: m.measured_d for st in sites.values() for arm in ARMS
                for _, m in st.data[arm] if m.status == "ok"}
    measured |= {m.piece_id: m.measured_d for st in sites.values() for _, m in st.escrow if m.status == "ok"}
    rows, hits = [], defaultdict(list)
    for c in checks:
        th = thresholds[sites[c["site"]].process]
        row = {"plate": c["plate"], "pin": c["pin"].piece_id, "hole": c["hole"].piece_id, "hand": c["hand"]}
        for arm in ARMS:
            post, site_arg = (oracle, c["site"]) if arm == "oracle" else models[(c["site"], arm)]
            clearance = post.predict(c["hole"], site_arg)[0] - post.predict(c["pin"], site_arg)[0]
            row[arm] = classify(clearance, th)
            hits[arm].append(row[arm] == c["hand"])
        if c["pin"].piece_id in measured and c["hole"].piece_id in measured:
            row["scanner"] = classify(measured[c["hole"].piece_id] - measured[c["pin"].piece_id], th)
            hits["scanner"].append(row["scanner"] == c["hand"])
        rows.append(row)
    return {"rows": rows, "agreement": {k: (float(np.mean(v)), len(v)) for k, v in hits.items()}}


def main() -> None:
    from prereg.check import fit_thresholds, load
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="receipts/real/state.pkl")
    ap.add_argument("--scans", default="scans")
    ap.add_argument("--prereg", default="prereg/prereg.yaml")
    a = ap.parse_args()
    thresholds = fit_thresholds(load(a.prereg)[0])
    if not thresholds:
        raise SystemExit("fit-class thresholds aren't filled in the prereg")
    with open(a.checkpoint, "rb") as f:
        state = pickle.load(f)
    checks = load_checks(a.scans, state)
    if not checks:
        raise SystemExit(f"no fit checks found under {a.scans}/<site>/<plate>-fitcheck.csv")
    r = score(state, checks, thresholds)
    for row in r["rows"]:
        print(f"{row['pin']} in {row['hole']}: hand {row['hand']:<5}  isolated {row['isolated']:<5}  "
              f"networked {row['networked']:<5}  oracle {row['oracle']:<5}  scanner {row.get('scanner', '-')}")
    for k, (acc, n) in r["agreement"].items():
        print(f"{k:<9} agrees with the hand check {acc:.0%} ({n} pairs)")


if __name__ == "__main__":
    main()
