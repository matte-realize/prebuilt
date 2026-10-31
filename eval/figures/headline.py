"""Headline chart (slide 6): held-out error vs pieces printed, plus the prediction.

    python -m eval.figures.headline sim.json                         # run.py --source sim --seeds N --out sim.json
    python -m eval.figures.headline sim.json --real real.json --out headline.png
    python -m eval.figures.headline sim.json --truth                 # noise-free error (simulation only)

Left: held-out MAE per arm against pieces printed per site (seed plate + arm
slots), mean over seeds and sites with a +-1 SE band; real rounds, if given, as
markers. Right: isolated - networked per round in um, the simulated 5-95% spread,
the committed predicted range (prereg, if filled) on its round, and the real value.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ARMS = ("isolated", "networked", "oracle")
# Validated categorical slots 1-3 (dataviz palette, light surface). Aqua is under 3:1 on
# white, so every line is direct-labeled and the oracle line is also dashed.
COLOR = {"isolated": "#2a78d6", "networked": "#eb6834", "oracle": "#1baf7a"}
STYLE = {"isolated": "-", "networked": "-", "oracle": (0, (4, 2))}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def per_seed(rows: list[dict], metric: str) -> dict:
    """(seed, round) -> arm -> (metric averaged over sites, n_train averaged over sites)."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.get(metric) is not None:
            acc[(r.get("seed", 0), r["round"])][r["arm"]].append((r[metric], r["n_train"]))
    return {k: {a: tuple(np.mean(v, axis=0)) for a, v in arms.items()} for k, arms in acc.items()
            if all(a in arms for a in ARMS)}


def curves(rows: list[dict], metric: str):
    """round -> arm -> (x, mean, se), and round -> list of per-seed iso - net."""
    ps = per_seed(rows, metric)
    by_round = defaultdict(lambda: defaultdict(list))
    diff = defaultdict(list)
    for (_, r), arms in ps.items():
        for a, v in arms.items():
            by_round[r][a].append(v)
        diff[r].append(arms["isolated"][0] - arms["networked"][0])
    out = {}
    for r, arms in sorted(by_round.items()):
        out[r] = {}
        for a, v in arms.items():
            v = np.array(v)
            se = v[:, 0].std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0.0
            out[r][a] = (v[:, 1].mean(), v[:, 0].mean(), se)
    return out, {r: np.array(d) for r, d in sorted(diff.items())}


def predicted(prereg_path: str | None, metric_is_truth: bool):
    if not prereg_path or metric_is_truth or not Path(prereg_path).exists():
        return None
    import yaml
    pr = (yaml.safe_load(Path(prereg_path).read_text()) or {}).get("predicted_range") or {}
    rng = pr.get("range") or [None, None]
    if pr.get("metric") != "iso_minus_net_mae_um" or None in rng:
        return None
    return pr.get("round", 3), rng


def draw(sim_rows, real_rows, metric: str, out: str, prereg: str | None) -> None:
    um = 1000.0
    sim, sim_diff = curves(sim_rows, metric)
    real, real_diff = curves(real_rows, "mae") if real_rows else ({}, {})
    n_seeds = len({r.get("seed", 0) for r in sim_rows})

    plt.rcParams.update({"font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [3, 2]}, facecolor=SURFACE)
    for a_ in (ax, bx):
        a_.set_facecolor(SURFACE)
        a_.grid(axis="y", color=GRID, lw=0.8)
        a_.spines[["top", "right"]].set_visible(False)

    rounds = sorted(sim)
    ends = {}
    for arm in ARMS:
        x = np.array([sim[r][arm][0] for r in rounds])
        y = np.array([sim[r][arm][1] for r in rounds]) * um
        se = np.array([sim[r][arm][2] for r in rounds]) * um
        ax.fill_between(x, y - se, y + se, color=COLOR[arm], alpha=0.12, lw=0)
        ax.plot(x, y, color=COLOR[arm], ls=STYLE[arm], lw=2, marker="o", ms=8,
                mec=SURFACE, mew=2, label=f"{arm} (sim)")
        ends[arm] = (x[-1], y[-1])
        if real:
            rr = sorted(real)
            ax.plot([real[r][arm][0] for r in rr], [real[r][arm][1] * um for r in rr], ls="none",
                    marker="D", ms=9, mfc=SURFACE, mec=COLOR[arm], mew=2, label=f"{arm} (real)")
    # Direct labels at the line ends, pushed apart so they never overlap.
    span = np.ptp(ax.get_ylim())
    placed = []
    for arm, (x1, y1) in sorted(ends.items(), key=lambda kv: kv[1][1]):
        y_lab = max(y1, placed[-1] + 0.06 * span) if placed else y1
        placed.append(y_lab)
        ax.annotate(arm, (x1, y1), xytext=(x1, y_lab), textcoords="data", va="center", color=INK,
                    fontsize=11, ha="left", annotation_clip=False,
                    xycoords="data").set_position((x1 + 0.025 * np.ptp(ax.get_xlim()), y_lab))
    ax.set_xlabel("pieces printed per site (seed plate + this arm's slots)")
    ax.set_ylabel(("noise-free " if metric == "mae_truth" else "") + "held-out MAE (µm)")
    ax.set_title(f"Held-out error by arm · simulation, {n_seeds} seeds × 2 sites, mean ± 1 SE",
                 loc="left", fontsize=12, color=INK)
    ax.legend(frameon=False, fontsize=9, ncol=2 if real else 1, loc="upper right")
    ax.margins(x=0.12)

    xs = np.arange(len(sim_diff))
    for i, (r, d) in enumerate(sim_diff.items()):
        d = d * um
        lo, hi = np.percentile(d, [5, 95])
        bx.vlines(i, lo, hi, color=COLOR["networked"], lw=6, alpha=0.25)
        bx.plot(i, np.median(d), "o", color=COLOR["networked"], ms=9, mec=SURFACE, mew=2)
    bx.axhline(0, color=INK2, lw=1)
    pred = predicted(prereg, metric == "mae_truth")
    if pred and pred[0] in sim_diff:
        i = list(sim_diff).index(pred[0])
        bx.add_patch(plt.Rectangle((i - 0.3, pred[1][0]), 0.6, pred[1][1] - pred[1][0],
                                   fill=False, ec=INK, lw=1.5, ls=(0, (3, 2))))
        bx.annotate("committed\nprediction", (i + 0.32, pred[1][1]), fontsize=9, color=INK2, va="top")
    for r, d in real_diff.items():
        if r in sim_diff:
            bx.plot(list(sim_diff).index(r), d.mean() * um, "D", ms=10, mfc=SURFACE, mec=INK, mew=2)
    bx.set_xticks(xs, [f"round {r}" for r in sim_diff])
    bx.set_ylabel("isolated − networked (µm)")
    bx.set_title("Benefit of sharing · median, 5–95% over seeds" + (" · ◇ real" if real_diff else ""),
                 loc="left", fontsize=12, color=INK)
    bx.margins(x=0.25)

    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    fig.savefig(Path(out).with_suffix(".pdf"), facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sim", help="results JSON from run.py --source sim --seeds N --out")
    ap.add_argument("--real", help="results JSON from run.py --source real --out")
    ap.add_argument("--truth", action="store_true", help="noise-free error (simulation only)")
    ap.add_argument("--prereg", default="prereg/prereg.yaml")
    ap.add_argument("--out", default="eval/figures/out/headline.png")
    a = ap.parse_args()
    sim = json.loads(Path(a.sim).read_text())
    real = json.loads(Path(a.real).read_text()) if a.real else None
    draw(sim, real, "mae_truth" if a.truth else "mae", a.out, a.prereg)
    print(f"wrote {a.out} and {Path(a.out).with_suffix('.pdf')}")


if __name__ == "__main__":
    main()
