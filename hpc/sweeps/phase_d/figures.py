"""Phase D figures (PNG + PDF) into eval/figures/, from the sweep results.

    .venv/bin/python hpc/sweeps/phase_d/figures.py              # every figure whose results exist
    .venv/bin/python hpc/sweeps/phase_d/figures.py robustness

Arm colors are the headline chart's (eval/figures/headline.py): isolated blue,
networked orange, oracle aqua dashed. The validated palette has three hues that
separate pairwise, so the no-messages ablation is gray and the attacked
networked arm is orange dotted; every line is direct-labeled.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from analyze import err, load, robustness_seed  # noqa: E402
from eval.figures.headline import COLOR, GRID, INK, INK2, STYLE, SURFACE  # noqa: E402

FIGS = ROOT / "eval" / "figures"
GRAY = "#8a8984"  # no-messages ablation: neutral, labeled
SITES = (2, 5, 10, 25)


def ci(x) -> tuple[float, float]:
    x = np.asarray(x, float)
    return x.mean(), (1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0)


def style() -> None:
    plt.rcParams.update({"font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "text.color": INK, "axes.spines.top": False, "axes.spines.right": False})


def axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def line(ax, x, rows, color, ls="-", label=None, marker="o", mfc=None, band=True):
    m = np.array([ci(r)[0] for r in rows])
    h = np.array([ci(r)[1] for r in rows])
    if band:
        ax.fill_between(x, m - h, m + h, color=color, alpha=0.14, lw=0)
    # filled markers get a surface ring; hollow ones (mfc=SURFACE) keep a colored edge
    ax.plot(x, m, color=color, ls=ls, lw=2, marker=marker, ms=8, mfc=mfc or color, mew=2,
            mec=SURFACE if mfc is None else color)
    if label:
        ax._end_labels = getattr(ax, "_end_labels", []) + [(x[-1], m[-1], label)]
    return m


def place_labels(fig, gap: float = 0.075) -> None:
    """Direct labels at each line's end, nudged apart so none overlap (gap in axes height)."""
    fig.canvas.draw()  # final limits and scales
    for ax in fig.axes:
        items = getattr(ax, "_end_labels", [])
        to_ax = ax.transData + ax.transAxes.inverted()
        pts = sorted((to_ax.transform((x, y))[1], x, y, t) for x, y, t in items)
        ys = []
        for fy, *_ in pts:
            ys.append(max(fy, ys[-1] + gap) if ys else fy)
        shift = max(0.0, ys[-1] - 0.98) if ys else 0.0
        for y_lab, (_, x, y, t) in zip(ys, pts):
            ax.annotate(t, (x, y), xytext=(to_ax.transform((x, y))[0] + 0.02, y_lab - shift),
                        textcoords="axes fraction", va="center", color=INK, fontsize=10)


def save(fig, name: str) -> list[Path]:
    place_labels(fig)
    out = [FIGS / f"{name}.png", FIGS / f"{name}.pdf"]
    fig.savefig(out[0], dpi=200, facecolor=SURFACE, bbox_inches="tight")
    fig.savefig(out[1], facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def robustness() -> list[Path]:
    honest = load("honest")
    fig, grid = plt.subplots(2, 2, figsize=(12, 8.2), facecolor=SURFACE, gridspec_kw={"width_ratios": [2, 3]})
    for row, (bad, good) in zip(grid, (("pla", "resin"), ("resin", "pla"))):
        att = load(f"bad_{bad}")
        per = [robustness_seed(honest[s], att[s], bad, good) for s in sorted(set(att) & set(honest))]
        rounds = per[0]["rounds"]
        tx, ex = row
        for a_ in row:
            axes(a_)
            a_.set_xticks(rounds)
            a_.set_xlim(rounds[0] - 0.2, rounds[-1] + 0.9)
            a_.set_xlabel("round")
        col = lambda k: [[x[k][r] for x in per] for r in rounds]  # noqa: E731
        line(tx, rounds, col("good_trust"), INK, label=f"{bad} → trust in {good}\n(honest sender)")
        line(tx, rounds, col("bad_trust"), INK2, ls=(0, (1.5, 1.5)), label=f"{good} → trust in {bad}\n(lying sender)",
             mfc=SURFACE)
        tx.set_ylim(-0.03, 1.08)
        tx.set_ylabel("trust (mean ± 95% CI)")
        tx.set_title(f"{bad} lies ({len(per)} seeds): trust", loc="left", fontsize=11, color=INK)
        line(ex, rounds, col("iso_att"), COLOR["isolated"], STYLE["isolated"], label="isolated")
        line(ex, rounds, col("net_hon"), COLOR["networked"], STYLE["networked"], label="networked, no attack")
        line(ex, rounds, col("net_att"), COLOR["networked"], (0, (1.5, 1.5)), label="networked, under attack", mfc=SURFACE)
        ex.set_yscale("log")
        ex.set_yticks([10, 20, 50, 100])
        ex.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ex.set_ylabel(f"{good} held-out error, µm (log)")
        ex.set_title(f"honest site ({good}): noise-free held-out MAE", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    return save(fig, "robustness")


def ablation() -> list[Path]:
    honest, nomsg = load("honest"), load("no_messages")
    seeds = sorted(set(honest) & set(nomsg))
    rounds = sorted(err(honest[seeds[0]]))
    e = {s: err(honest[s]) for s in seeds}
    m = {s: err(nomsg[s]) for s in seeds}
    arms = {"isolated": ([[e[s][r]["isolated"] for s in seeds] for r in rounds], COLOR["isolated"], STYLE["isolated"]),
            "no messages": ([[m[s][r]["networked"] for s in seeds] for r in rounds], GRAY, (0, (6, 2))),
            "networked": ([[e[s][r]["networked"] for s in seeds] for r in rounds], COLOR["networked"], STYLE["networked"]),
            "oracle (reference)": ([[e[s][r]["oracle"] for s in seeds] for r in rounds], COLOR["oracle"], STYLE["oracle"])}
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.6), facecolor=SURFACE)
    for a_ in (ax, bx):
        axes(a_)
        a_.set_xticks(rounds)
        a_.set_xlim(rounds[0] - 0.2, rounds[-1] + 1.0)
        a_.set_xlabel("round")
    for name, (rows, c, ls) in arms.items():
        line(ax, rounds, rows, c, ls, label=name, band=False)  # unpaired bands overlap; paired CIs are on the right
    ax.set_ylabel("held-out MAE, µm (mean over seeds)")
    ax.set_title(f"noise-free held-out error, both sites, {len(seeds)} seeds", loc="left", fontsize=11, color=INK)
    iso = arms["isolated"][0]
    for name in ("no messages", "networked", "oracle (reference)"):
        rows, c, ls = arms[name]
        line(bx, rounds, [np.array(i) - np.array(x) for i, x in zip(iso, rows)], c, ls, label=name)
    bx.axhline(0, color=INK2, lw=1)
    bx.set_ylabel("isolated − arm, µm (paired, 95% CI)")
    bx.set_title("gain over isolated (above 0 = better)", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    return save(fig, "ablation")


def scaling() -> list[Path]:
    data = {}
    for k in SITES:
        try:
            data[k] = load("honest", k)
        except FileNotFoundError:
            pass
    ks = sorted(data)
    last = max(err(next(iter(data[ks[0]].values()))))
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.6), facecolor=SURFACE)
    for a_ in (ax, bx):
        axes(a_)
        a_.set_xscale("log")
        a_.set_xticks(ks)
        a_.set_xticklabels([f"{k}\n(n={len(data[k])})" for k in ks])
        a_.minorticks_off()
        a_.set_xlim(ks[0] / 1.25, ks[-1] * 2.2)
        a_.set_xlabel("sites (seeds)")
    e = {k: [err(r)[last] for r in data[k].values()] for k in ks}
    for arm in ("isolated", "networked", "oracle"):
        label = "oracle (reference)" if arm == "oracle" else arm
        line(ax, ks, [[x[arm] for x in e[k]] for k in ks], COLOR[arm], STYLE[arm], label=label)
    ax.set_ylabel(f"round {last} held-out MAE, µm (95% CI)")
    ax.set_title(f"noise-free held-out error at round {last}, averaged over sites", loc="left", fontsize=11, color=INK)
    line(bx, ks, [[x["isolated"] - x["networked"] for x in e[k]] for k in ks], COLOR["networked"], label="iso − net")
    line(bx, ks, [[x["isolated"] - x["oracle"] for x in e[k]] for k in ks], COLOR["oracle"], STYLE["oracle"],
         label="iso − oracle\n(reference)")
    bx.axhline(0, color=INK2, lw=1)
    bx.set_ylabel(f"round {last} gain over isolated, µm (95% CI)")
    bx.set_title("networking gain vs number of sites", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    return save(fig, "scaling")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("figures", nargs="*", default=["robustness", "ablation", "scaling"])
    a = ap.parse_args()
    style()
    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    for name in a.figures:
        try:
            paths = {"robustness": robustness, "ablation": ablation, "scaling": scaling}[name]()
        except FileNotFoundError as e:
            print(f"{name}: skipped, missing results ({e.filename})")
            continue
        print(f"{name}: {', '.join(str(p.relative_to(ROOT)) for p in paths)} (generated at {git})")


if __name__ == "__main__":
    main()
