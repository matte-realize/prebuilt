"""Summarize results/scans.jsonl: error distribution per defect, the 25 um threshold, and the figure.

    .venv/bin/python hpc/scanner_stress/analyze.py      # writes results/summary.md and stress.png

Errors are |measured - true| in um over printed pieces the scanner measured.
"fail" is the share of printed pieces with no measurement (whole-scan errors
count every piece); "false ok" is the share of empty slots that got a diameter.
A level "breaks" when p95 passes 25 um or fail passes 5%.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sweep import DPIS, SINGLE  # noqa: E402

OUT = HERE / "results"
LIMIT_UM, FAIL_MAX = 25.0, 0.05
VARIANTS = ["base", "base_cal", "fid", "fid_cal", "edge", "area_h", "edge_h", "edge_h_cal"]
LABEL = {"base": "scanner.py", "base_cal": "+ caliper", "fid": "fiducial retry",
         "fid_cal": "fiducial retry + caliper", "edge": "edge fit", "area_h": "homography",
         "edge_h": "edge + homography", "edge_h_cal": "edge + homography + caliper"}


def load() -> list[dict]:
    return [json.loads(line) for line in (OUT / "scans.jsonl").open()]


def stats(rows: list[dict], v: str) -> dict:
    err, fail, present, false_ok, empty = [], 0, 0, 0, 0
    for r in rows:
        vals = r[v]
        for i, is_empty in enumerate(r["empty"]):
            e = None if isinstance(vals, str) else vals[i]
            if is_empty:
                empty += 1
                false_ok += e is not None
            else:
                present += 1
                if e is None:
                    fail += 1
                else:
                    err.append(e)
    a = np.abs(np.array(err)) if err else np.array([np.nan])
    return {"n_scans": len(rows), "median": float(np.median(a)), "p95": float(np.percentile(a, 95)),
            "bias": float(np.mean(err)) if err else np.nan, "fail": fail / max(present, 1),
            "false_ok": false_ok / max(empty, 1), "scan_err": sum(isinstance(r[v], str) for r in rows) / len(rows)}


def breaks(s: dict) -> bool:
    return not (s["p95"] <= LIMIT_UM) or s["fail"] > FAIL_MAX


def threshold(levels: list, ss: list[dict]) -> str:
    """First level where it breaks, interpolated on p95 between the last good and first bad level."""
    if not ss:
        return "-"
    for i, s in enumerate(ss):
        if breaks(s):
            if i == 0:
                return f"<= {levels[0]}"
            a, b, pa, pb = levels[i - 1], levels[i], ss[i - 1]["p95"], s["p95"]
            if s["fail"] > FAIL_MAX or not np.isfinite(pb) or pb <= pa or isinstance(a, str):
                return f"{a} - {b}"
            x = a + (b - a) * (LIMIT_UM - pa) / (pb - pa)
            return f"~{x:.3g}"
    return f"> {levels[-1]}"


def group(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["sweep"], r["level"], r["defects"]["dpi"])].append(r)
    return g


def fmt(s: dict) -> str:
    return f"{s['median']:.1f} / {s['p95']:.1f} / {100 * s['fail']:.1f}%"


def main() -> None:
    rows = load()
    g = group(rows)
    md = ["# Scanner stress sweep: full results", "",
          f"{len(rows)} scans. Cells: median / p95 |error| (um) / fail rate. Bias is the mean signed error (um).", ""]
    thr = {}
    for knob, levels in SINGLE.items():
        md += [f"## {knob}", ""]
        for dpi in DPIS:
            md += [f"**{dpi} dpi**", "", "| level | " + " | ".join(LABEL[v] for v in VARIANTS) + " | bias (base) | false ok (base) |",
                   "|---" * (len(VARIANTS) + 3) + "|"]
            per_v, done = {v: [] for v in VARIANTS}, []
            for lv in levels:
                rs = g[(knob, lv, dpi)]
                if not rs:
                    continue
                done.append(lv)
                ss = {v: stats(rs, v) for v in VARIANTS}
                for v in VARIANTS:
                    per_v[v].append(ss[v])
                md.append(f"| {lv} | " + " | ".join(fmt(ss[v]) for v in VARIANTS)
                          + f" | {ss['base']['bias']:+.1f} | {100 * ss['base']['false_ok']:.0f}% |")
            for v in VARIANTS:
                thr[(knob, dpi, v)] = threshold(done, per_v[v])
            md += ["", "Breaks at: " + "; ".join(f"{LABEL[v]} {thr[(knob, dpi, v)]}" for v in VARIANTS), ""]
    md += ["## Setups (all defects together)", "", "| setup | dpi | " + " | ".join(LABEL[v] for v in VARIANTS) + " |",
           "|---" * (len(VARIANTS) + 2) + "|"]
    for tier in ("good", "typical", "bad"):
        for dpi in DPIS:
            rs = g[(f"tier_{tier}", dpi, dpi)]
            if not rs:
                continue
            md.append(f"| {tier} | {dpi} | " + " | ".join(fmt(stats(rs, v)) for v in VARIANTS) + " |")
    mc = [r for r in rows if r["sweep"] == "mc"]
    md += ["", "## Random combinations (Monte Carlo)", "", "| dpi | scans | " + " | ".join(LABEL[v] for v in VARIANTS) + " |",
           "|---" * (len(VARIANTS) + 2) + "|"]
    for dpi in DPIS:
        rs = [r for r in mc if r["defects"]["dpi"] == dpi]
        if not rs:
            continue
        md.append(f"| {dpi} | {len(rs)} | " + " | ".join(fmt(stats(rs, v)) for v in VARIANTS) + " |")
    md += ["", "Which defect drives the combined error (400 dpi, scanner.py, p95 um by tercile of each defect):", "",
           "| defect | low | mid | high |", "|---|---|---|---|"]
    rs = [r for r in mc if r["defects"]["dpi"] == 400]
    for knob in [] if not rs else ("blur_px", "noise", "grad", "radial", "shadow_mm", "rim_mm", "keystone", "dust", "jpeg"):
        x = np.array([r["defects"][knob] for r in rs], float)
        if knob == "jpeg":
            x = np.where(x == 0, 101, x) * -1  # lower quality = worse
        cuts = np.quantile(x, [1 / 3, 2 / 3])
        bins = [[r for r, xi in zip(rs, x) if lo(xi)] for lo in
                (lambda v: v <= cuts[0], lambda v: cuts[0] < v <= cuts[1], lambda v: v > cuts[1])]
        md.append(f"| {knob} | " + " | ".join(f"{stats(b, 'base')['p95']:.0f}" if b else "-" for b in bins) + " |")
    (OUT / "summary.md").write_text("\n".join(md) + "\n")
    json.dump({"|".join(map(str, k)): v for k, v in thr.items()}, (OUT / "thresholds.json").open("w"), indent=1)
    figure(g)
    print((OUT / "summary.md").read_text()[:3000])


def figure(g) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    knobs = list(SINGLE)
    fig, axes = plt.subplots(3, 4, figsize=(13, 8.5), constrained_layout=True)
    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    series = [("base", "scanner.py", "#2a78d6"), ("edge_h", "edge fit + homography", "#eb6834")]
    for ax, knob in zip(axes.flat, knobs + ["dpi"]):
        if knob == "dpi":
            xs = list(DPIS)
            rows = {d: g[("blur_px", 1.2, d)] for d in DPIS}
            xlab = "dpi (defaults)"
        else:
            xs = SINGLE[knob]
            rows = {lv: g[(knob, lv, 400)] for lv in xs}
            xlab = knob
        pos = np.arange(len(xs))
        for v, name, col in series:
            p95 = [stats(rows[x], v)["p95"] if rows[x] else np.nan for x in xs]
            ax.plot(pos, p95, color=col, lw=2, marker="o", ms=4, label=name)
        ax.axhline(LIMIT_UM, color=muted, lw=1, ls="--")
        ax.set_yscale("log")
        ax.set_ylim(1, 1000)
        ax.set_xticks(pos, [str(x) for x in xs], fontsize=8, color=muted)
        ax.tick_params(axis="y", labelsize=8, colors=muted)
        ax.set_title(xlab, fontsize=10, color=ink, loc="left")
        ax.grid(axis="y", color=grid, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(grid)
    axes.flat[0].set_ylabel("p95 |error|, um (log)", fontsize=9, color=muted)
    axes.flat[0].text(0, LIMIT_UM * 1.1, "25 um", fontsize=8, color=muted)
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="upper right", ncols=2,
               frameon=False, fontsize=10)
    fig.suptitle("Scanner p95 error under one defect at a time (400 dpi unless noted; both sites, both modes)",
                 fontsize=11, color=ink, x=0.01, ha="left")
    fig.savefig(HERE / "stress.png", dpi=130)


if __name__ == "__main__":
    main()
