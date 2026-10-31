"""Turn sweep JSONL into markdown tables.

    .venv/bin/python hpc/sweeps/phase_c/analyze.py seed_plate
    .venv/bin/python hpc/sweeps/phase_c/analyze.py tuning_trust_seed8_slots6

All errors are `mae_truth` (model error against the noise-free diameters, sim
only), in micrometres, averaged over the two sites within a seed. Standard
errors are across seeds. Two oracle-gap-closed numbers are given:
  pooled   (mean iso - mean net) / (mean iso - mean ora), 90% bootstrap CI over seeds
  per-seed median and IQR of the per-seed ratio; this is the prereg's form,
           and it is noisy whenever a seed's iso - ora is near zero.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict

import numpy as np

from common import OUT, load

ARMS3 = ("isolated", "networked", "oracle")
RNG = np.random.default_rng(0)


def per_seed(rows: list[dict], metric: str = "mae_truth", sites: tuple[str, ...] | None = None) -> dict:
    """label -> round -> arm -> array over seeds (site-averaged)."""
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for row in rows:
        by = defaultdict(list)
        for s in row["scores"]:
            if sites is None or s["site"] in sites:
                by[(s["round"], s["arm"])].append(s[metric])
        for (r, arm), v in by.items():
            acc[row["arm"]][r][arm][row["config"]["seed"]] = float(np.mean(v))
    out = {}
    for label, rounds in acc.items():
        out[label] = {}
        for r, arms in rounds.items():
            seeds = sorted(set.intersection(*(set(arms[a]) for a in ARMS3)))
            out[label][r] = {a: np.array([arms[a][s] for s in seeds]) for a in ARMS3}
    return out


def se(x: np.ndarray) -> float:
    return float(np.std(x, ddof=1) / math.sqrt(len(x))) if len(x) > 1 else math.nan


def pooled_gap(iso, net, ora) -> float:
    d = iso.mean() - ora.mean()
    return (iso.mean() - net.mean()) / d if abs(d) > 1e-12 else math.nan


def gap_ci(iso, net, ora, n: int = 2000) -> tuple[float, float]:
    idx = RNG.integers(len(iso), size=(n, len(iso)))
    g = np.array([pooled_gap(iso[i], net[i], ora[i]) for i in idx])
    g = g[np.isfinite(g)]
    return float(np.percentile(g, 5)), float(np.percentile(g, 95))


def seed_gaps(iso, net, ora) -> np.ndarray:
    d = iso - ora
    ok = np.abs(d) > 1e-12
    return (iso[ok] - net[ok]) / d[ok]


def mean_se(x: np.ndarray, fmt: str = ".3f") -> str:
    return f"{x.mean():{fmt}} ({se(x):{fmt}})" if len(x) else "-"


def um(x: float) -> str:
    return f"{1000 * x:.2f}"


def table_arms(data: dict, labels: list[str]) -> str:
    lines = ["| config | round | n | isolated | networked | oracle | iso - net (SE) | gap closed, pooled [90% CI] | gap closed, per-seed median [IQR] |",
             "|---|---|---|---|---|---|---|---|---|"]
    for label in labels:
        for r, a in sorted(data[label].items()):
            iso, net, ora = (a[k] for k in ARMS3)
            lo, hi = gap_ci(iso, net, ora)
            g = seed_gaps(iso, net, ora)
            diff = iso - net
            lines.append(
                f"| {label} | {r} | {len(iso)} | {um(iso.mean())} ± {um(se(iso))} | {um(net.mean())} ± {um(se(net))} "
                f"| {um(ora.mean())} ± {um(se(ora))} | {um(diff.mean())} ({um(se(diff))}) "
                f"| {pooled_gap(iso, net, ora):.2f} [{lo:.2f}, {hi:.2f}] "
                f"| {np.median(g):.2f} [{np.percentile(g, 25):.2f}, {np.percentile(g, 75):.2f}] |")
    return "\n".join(lines)


def seed_plate(name: str) -> str:
    rows = load(name)
    data = per_seed(rows)
    order = sorted(data, key=lambda l: (int(l.split("_")[0][4:]), int(l.split("slots")[1])))
    secs = defaultdict(list)
    for row in rows:
        secs[row["arm"]].append(row["seconds"])
    audits = sum(r["audit_pass"] for r in rows)
    out = [f"## {name}", "",
           f"mae_truth in µm (mean ± SE over seeds). Privacy audit passed {audits}/{len(rows)} runs.", "",
           table_arms(data, order), "",
           "Mean wall time per run (s): " + ", ".join(f"{l} {np.mean(secs[l]):.1f}" for l in order)]
    return "\n".join(out)


def tuning(name: str) -> str:
    rows = load(name)
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        label, cond = row["arm"].split("|")
        groups[label][cond].append(row)
    last = max(s["round"] for s in rows[0]["scores"])

    out = [f"## {name}", "",
           "bad trust: honest site's final trust in the bad sender (lower is better). "
           "honest trust: final trust between honest sites, in honest runs and from the bad site toward the honest one "
           "(higher is better); `<0.5` is the share of those links that ended below 0.5. "
           "net/iso under attack: honest site's networked over isolated mae_truth at the last round (1.0 = no harm). "
           "Gap closed: honest runs, pooled, last round. Retired: agents retired per run, honest runs.", "",
           "| config | bad trust (SE) | honest trust (SE) | honest <0.5 | net/iso under attack | iso - net honest, µm (SE) | gap closed [90% CI] | retired |",
           "|---|---|---|---|---|---|---|---|"]
    for label, conds in groups.items():
        bad_t, hon_t, harm, retired = [], [], [], []
        for cond, rs in conds.items():
            bad = cond[4:] if cond.startswith("bad_") else None
            for row in rs:
                for t in row["trust"]:
                    if t["round"] != last:
                        continue
                    (bad_t if t["sender"] == bad else hon_t).append(t["trust"])
                if bad:
                    honest_site = next(s for s in ("resin", "pla") if s != bad)
                    sc = {x["arm"]: x["mae_truth"] for x in row["scores"] if x["round"] == last and x["site"] == honest_site}
                    harm.append(sc["networked"] / sc["isolated"])
                else:
                    retired.append(len(row["retired"]))
        bad_t, hon_t, harm = map(np.array, (bad_t, hon_t, harm))
        hon = per_seed([{**r, "arm": label} for r in conds["honest"]])[label][last]
        iso, net, ora = (hon[k] for k in ARMS3)
        lo, hi = gap_ci(iso, net, ora)
        diff = iso - net
        out.append(
            f"| {label} | {mean_se(bad_t)} | {mean_se(hon_t)} "
            f"| {np.mean(hon_t < 0.5):.2f} | {f'{np.median(harm):.2f} (mean {harm.mean():.2f})' if len(harm) else '-'} "
            f"| {um(diff.mean())} ({um(se(diff))}) | {pooled_gap(iso, net, ora):.2f} [{lo:.2f}, {hi:.2f}] "
            f"| {np.mean(retired):.2f} |")
    return "\n".join(out)


if __name__ == "__main__":
    for name in sys.argv[1:]:
        text = seed_plate(name) if name.startswith("seed_plate") else tuning(name)
        (OUT / f"{name}.md").write_text(text + "\n")
        print(text, "\n")
