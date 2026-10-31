"""Phase D: calibrate the simulator to real seed data, then predict oracle-gap-closed.

    python -m sim.calibrate --state receipts/real/state.pkl --config hpc/phase_d/frozen_config.json \\
        --seeds 200 --out hpc/phase_d/out
    python -m sim.calibrate --synthetic 7 --config ...   # self-check: seed data from a known sim world

Step 1 fits each site's hidden truth for `sim.reference.SimPrinter` to that
site's seed-plate pieces only (held-out pieces on the seed plate are left out):
the physics parameters including `sigma_meas`, the unmodeled radial term, and
the failure model (50% failure diameter per kind and the logistic width).
Diameters and failures have separate likelihoods, so each gets its own
adaptive Metropolis run over several chains.

Step 2 runs the full experiment with the frozen collective config many times.
Every seed draws a fresh world from the calibration posterior, so the predicted
range carries the calibration uncertainty, not just the point estimate.

Outputs in --out: calibration.json, prediction.json, summary.md and one
residual plot per site. prediction.json records the exact command and git hash.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")  # one BLAS thread per worker; the pool provides the parallelism

import argparse
import json
import math
import pickle
import shlex
import subprocess
import sys
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from arms.experiment import Config, run_experiment
from contracts import Measurement, Piece
from eval.metrics import oracle_gap_closed
from model import physics
from model.physics import PieceArrays
from plates.seed import seed_plate
from sim.reference import FAIL_D, FAIL_WIDTH, SimPrinter, make_world

SITES = {"resin": "resin", "pla": "pla"}
ROOT = Path(__file__).resolve().parent.parent
Data = list[tuple[Piece, Measurement]]

RADIAL_STD = 0.02      # mm, prior on the radial term (make_world's radial_std)
FAIL_D_STD = 0.4       # mm, prior around FAIL_D
LOG_WIDTH_STD = 0.5    # prior on log(fail_width) around log(FAIL_WIDTH)
FAIL_NAMES = ["fail_d_pin", "fail_d_hole", "fail_width"]
# Config fields that must be frozen before a prediction; everything else keeps its default.
FROZEN = ("rounds", "n_particles", "slots_per_arm", "seed_pieces", "eta", "cred_floor", "discount",
          "trust_init", "between_site_sd")


# ---- seed data -----------------------------------------------------------------

def seed_data_from_state(path: str | Path) -> dict[str, Data]:
    """Seed-plate pieces from a real-run checkpoint (`run.py --source real`)."""
    with open(path, "rb") as f:
        state = pickle.load(f)
    return {s: [(p, m) for p, m in st.data["isolated"] if p.arm == "seed"] for s, st in state["sites"].items()}


def seed_data_from_scans(scan_dir: str | Path) -> dict[str, Data]:
    """Seed-plate pieces from `scans/<site>/<site>-seed-measurements.json` (measure/real.py)."""
    out = {}
    for site in SITES:
        plate = seed_plate(site)
        rows = json.loads((Path(scan_dir) / site / f"{plate.plate_id}-measurements.json").read_text())
        by_id = {r["piece_id"]: Measurement(**r) for r in rows}
        out[site] = [(p, by_id[p.piece_id]) for p in plate.pieces if p.arm == "seed" and p.piece_id in by_id]
    return out


def seed_data_synthetic(seed: int) -> tuple[dict[str, Data], dict[str, SimPrinter]]:
    """Seed-plate pieces from a known sim world, to check that calibration recovers it."""
    world = make_world(SITES, seed)
    out = {}
    for site, printer in world.items():
        plate = seed_plate(site)
        ms = {m.piece_id: m for m in printer.print_and_measure(plate)}
        out[site] = [(p, ms[p.piece_id]) for p in plate.pieces if p.arm == "seed"]
    return out, world


# ---- sampler -------------------------------------------------------------------

def metropolis(logp, x0: np.ndarray, scale: np.ndarray, steps: int, rng: np.random.Generator) -> np.ndarray:
    """Adaptive random-walk Metropolis over C chains at once. x0 [C, P] -> samples [steps, C, P].

    The proposal covariance is re-estimated from the chains' recent history
    during the first half (Haario-style); the second half is a plain Metropolis
    chain with a fixed proposal, so it is a valid sample.
    """
    C, P = x0.shape
    x, lp = x0.copy(), logp(x0)
    chol = np.diag(scale) * 2.38 / math.sqrt(P)
    out = np.empty((steps, C, P))
    for t in range(steps):
        if 1000 <= t <= steps // 2 and t % 500 == 0:
            hist = out[t // 2: t].reshape(-1, P)
            cov = np.cov(hist.T) + np.diag((1e-4 * scale) ** 2)
            chol = np.linalg.cholesky(cov * 2.38**2 / P)
        prop = x + rng.standard_normal((C, P)) @ chol.T
        lpp = logp(prop)
        acc = np.log(rng.random(C)) < lpp - lp
        x[acc], lp[acc] = prop[acc], lpp[acc]
        out[t] = x
    return out


def rhat(chains: np.ndarray) -> np.ndarray:
    """Gelman-Rubin R-hat per parameter for samples [steps, C, P]."""
    n = chains.shape[0]
    means = chains.mean(axis=0)
    w = chains.var(axis=0, ddof=1).mean(axis=0)
    b = n * means.var(axis=0, ddof=1)
    return np.sqrt(((n - 1) / n * w + b / n) / w)


# ---- calibration ---------------------------------------------------------------

@dataclass
class SiteFit:
    site: str
    process: str
    names: list[str]          # physics.PARAMS[process] names + "radial"
    draws: np.ndarray         # [K, P + 1]
    fail_draws: np.ndarray    # [K, 3]: fail_d_pin, fail_d_hole, fail_width
    rhat: dict[str, float]
    n_ok: int
    n_failed: int

    def summary(self) -> dict[str, dict[str, float]]:
        cols = dict(zip(self.names + FAIL_NAMES, np.hstack([self.draws, self.fail_draws]).T))
        return {k: {"mean": float(v.mean()), "sd": float(v.std()), "q05": float(np.quantile(v, 0.05)),
                    "q95": float(np.quantile(v, 0.95)), "rhat": self.rhat[k]} for k, v in cols.items()}

    def printer(self, k: int, seed: int) -> SimPrinter:
        theta, radial = self.draws[k, :-1], float(self.draws[k, -1])
        fp, fh, fw = self.fail_draws[k]
        return SimPrinter(self.site, self.process, theta.copy(), radial, np.random.default_rng(seed),
                          fail_d={"pin": float(fp), "hole": float(fh)}, fail_width=float(fw))


def _diameter_logp(process: str, data: Data):
    ok = [(p, m) for p, m in data if m.status == "ok"]
    x = PieceArrays.from_pieces([p for p, _ in ok])
    y = np.array([m.measured_d for _, m in ok])
    r2 = (x.u**2 + x.v**2) / 2

    def logp(z: np.ndarray) -> np.ndarray:
        theta, radial = z[:, :-1], z[:, -1]
        lp = physics.log_prior(process, theta) - 0.5 * (radial / RADIAL_STD) ** 2
        good = np.isfinite(lp)
        if good.any():
            mu = physics.predict_d(process, x, theta[good]) + radial[good, None] * r2
            sig = physics.sigma(process, theta[good])[:, None]
            lp[good] += (-0.5 * ((y - mu) / sig) ** 2 - np.log(sig)).sum(axis=1)
        return lp

    return logp, len(ok)


def _failure_logp(process: str, data: Data):
    d = np.array([p.nominal_d for p, _ in data])
    hole = np.array([p.kind == "hole" for p, _ in data])
    failed = np.array([m.status == "failed" for _, m in data])
    prior = np.array([FAIL_D[process]["pin"], FAIL_D[process]["hole"]])

    def logp(z: np.ndarray) -> np.ndarray:
        fd, log_w = z[:, :2], z[:, 2]
        lp = -0.5 * (((fd - prior) / FAIL_D_STD) ** 2).sum(axis=1) - 0.5 * ((log_w - math.log(FAIL_WIDTH)) / LOG_WIDTH_STD) ** 2
        lp = np.where((fd > 0).all(axis=1), lp, -np.inf)
        a = (d[None, :] - np.where(hole, fd[:, 1:2], fd[:, 0:1])) / np.exp(log_w)[:, None]
        # p_fail = sigmoid(-a): log p_fail = -logaddexp(0, a), log p_ok = -logaddexp(0, -a)
        ll = np.where(failed, -np.logaddexp(0, a), -np.logaddexp(0, -a)).sum(axis=1)
        return lp + ll

    return logp


def _run_chains(logp, x0, scale, steps, n_draws, rng):
    chains = metropolis(logp, x0, scale, steps, rng)[steps // 2:]
    flat = chains.reshape(-1, chains.shape[2])
    return flat[rng.choice(len(flat), n_draws, replace=len(flat) < n_draws)], rhat(chains)


def fit_site(site: str, process: str, data: Data, n_draws: int = 2000, steps: int = 40000, chains: int = 8,
             seed: int = 0) -> SiteFit:
    rng = np.random.default_rng(seed)
    specs = physics.PARAMS[process]
    names = [s.name for s in specs] + ["radial"]

    logp, n_ok = _diameter_logp(process, data)
    x0 = np.hstack([physics.sample_prior(process, chains, rng), rng.normal(0, RADIAL_STD, (chains, 1))])
    scale = np.array([s.prior_std for s in specs] + [RADIAL_STD]) * 0.1
    draws, rh = _run_chains(logp, x0, scale, steps, n_draws, rng)

    flogp = _failure_logp(process, data)
    f0 = np.column_stack([rng.normal(FAIL_D[process]["pin"], 0.1, chains), rng.normal(FAIL_D[process]["hole"], 0.1, chains),
                          rng.normal(math.log(FAIL_WIDTH), 0.1, chains)])
    fdraws, frh = _run_chains(flogp, f0, np.array([0.1, 0.1, 0.1]), steps // 4, n_draws, rng)
    fdraws[:, 2] = np.exp(fdraws[:, 2])

    return SiteFit(site, process, names, draws, fdraws, dict(zip(names + FAIL_NAMES, map(float, np.r_[rh, frh]))),
                   n_ok, len(data) - n_ok)


def residuals(fit: SiteFit, data: Data) -> dict[str, np.ndarray]:
    """Posterior-mean prediction (physics + radial) vs measured, for the ok pieces."""
    ok = [(p, m) for p, m in data if m.status == "ok"]
    x = PieceArrays.from_pieces([p for p, _ in ok])
    mu = physics.predict_d(fit.process, x, fit.draws[:, :-1]) + fit.draws[:, -1:] * (x.u**2 + x.v**2) / 2
    y = np.array([m.measured_d for _, m in ok])
    return {"d": x.d, "hole": x.is_hole, "radius": np.sqrt(x.u**2 + x.v**2), "resid": y - mu.mean(axis=0)}


def plot_residuals(fit: SiteFit, data: Data, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    r = residuals(fit, data)
    sigma = fit.draws[:, fit.names.index("sigma_meas")].mean()
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    for kind, mask, mk in (("pin", ~r["hole"], "o"), ("hole", r["hole"], "s")):
        ax[0].scatter(r["d"][mask], r["resid"][mask] * 1000, marker=mk, s=18, label=kind)
        ax[1].scatter(r["radius"][mask], r["resid"][mask] * 1000, marker=mk, s=18, label=kind)
    for a, xl in ((ax[0], "nominal diameter (mm)"), (ax[1], "distance from plate center (normalized)")):
        a.axhline(0, color="k", lw=0.8)
        a.axhspan(-sigma * 1000, sigma * 1000, color="0.85", zorder=0)
        a.set_xlabel(xl)
        a.set_ylabel("measured - fit (µm)")
    ax[0].legend()

    d = np.linspace(0.5, max(p.nominal_d for p, _ in data), 200)
    for kind, col in (("pin", 0), ("hole", 1)):
        fd, w = fit.fail_draws[:, col:col + 1], fit.fail_draws[:, 2:3]
        pf = 1 / (1 + np.exp((d[None, :] - fd) / w))
        line = ax[2].plot(d, pf.mean(axis=0), label=kind)[0]
        ax[2].fill_between(d, *np.quantile(pf, [0.05, 0.95], axis=0), color=line.get_color(), alpha=0.2)
        obs = [(p.nominal_d, m.status == "failed") for p, m in data if p.kind == kind]
        ax[2].scatter([o[0] for o in obs], [o[1] + (0.03 if col else -0.03) for o in obs], s=12, color=line.get_color())
    ax[2].set_xlabel("nominal diameter (mm)")
    ax[2].set_ylabel("P(failed)")
    ax[2].legend()
    fig.suptitle(f"{fit.site}: seed-plate residuals (grey band = fitted sigma_meas) and failure fit")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---- prediction ----------------------------------------------------------------

def _run_one(job: tuple[int, dict, dict[str, SiteFit]]) -> dict:
    seed, cfg_kw, fits = job
    rng = np.random.default_rng([seed, 0xD])
    world = {s: f.printer(int(rng.integers(len(f.draws))), int(rng.integers(2**32))) for s, f in fits.items()}
    res = run_experiment(world, SITES, Config(**cfg_kw, seed=seed))
    # a site with no ok held-out pieces scores mae_truth None; NaN drops it from this seed's numbers
    scores = [{**row, "mae_truth": math.nan if row["mae_truth"] is None else row["mae_truth"]} for row in res.scores]
    by = {}
    for row in scores:
        by.setdefault(row["round"], {}).setdefault(row["arm"], []).append(row["mae_truth"])
    return {"seed": seed,
            "gap": oracle_gap_closed(scores, "mae"),
            "gap_truth": oracle_gap_closed(scores, "mae_truth"),
            "iso_minus_net_um": {r: 1000 * (np.nanmean(a["isolated"]) - np.nanmean(a["networked"])) for r, a in by.items()}}


def _interval(v: list[float]) -> dict[str, float | None]:
    a = np.array([x for x in v if not math.isnan(x)])
    if not len(a):
        return {"median": None, "q05": None, "q25": None, "q75": None, "q95": None, "n": 0}
    q = np.quantile(a, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {"median": q[2], "q05": q[0], "q25": q[1], "q75": q[3], "q95": q[4], "n": len(a)}


def predict(fits: dict[str, SiteFit], cfg_kw: dict, seeds: range, workers: int) -> dict:
    jobs = [(s, cfg_kw, fits) for s in seeds]
    with get_context("spawn").Pool(workers) as pool:  # fork is unsafe once Warp has started threads
        rows = pool.map(_run_one, jobs, chunksize=1)
    rounds = sorted(rows[0]["gap"])
    return {key: {r: _interval([row[key][r] for row in rows]) for r in rounds}
            for key in ("gap", "gap_truth", "iso_minus_net_um")}


def load_config(path: str | Path) -> dict:
    """Exactly the FROZEN Config fields; anything else (seed, ablations) is set per run, never frozen."""
    kw = json.loads(Path(path).read_text())
    missing, extra = [k for k in FROZEN if k not in kw], sorted(set(kw) - set(FROZEN))
    if missing or extra:
        raise SystemExit(f"bad frozen config {path}: missing {missing}, not allowed {extra}")
    return kw


def provenance() -> dict:
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"command": " ".join(shlex.quote(a) for a in [sys.executable.rsplit("/", 1)[-1], "-m", "sim.calibrate", *sys.argv[1:]]),
            "git_hash": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}


# ---- CLI -----------------------------------------------------------------------

def _fmt(i: dict) -> str:
    if not i["n"]:
        return "undefined in every seed (n=0)"
    return f"{i['median']:.2f} [{i['q05']:.2f}, {i['q95']:.2f}] (IQR {i['q25']:.2f}-{i['q75']:.2f}, n={i['n']})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--state", help="real-run checkpoint, receipts/real/state.pkl")
    src.add_argument("--scans", help="scan directory holding <site>/<site>-seed-measurements.json")
    src.add_argument("--synthetic", type=int, metavar="SEED", help="self-check on a known sim world")
    ap.add_argument("--config", required=True, help="frozen collective config, JSON of Config fields")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=50000, help="first experiment seed (away from run.py and Phase C)")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--steps", type=int, default=40000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    cfg_kw = load_config(a.config)
    truth = None
    if a.state:
        data = seed_data_from_state(a.state)
    elif a.scans:
        data = seed_data_from_scans(a.scans)
    else:
        data, truth = seed_data_synthetic(a.synthetic)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    fits, calib = {}, {}
    for i, (site, d) in enumerate(sorted(data.items())):
        fits[site] = fit_site(site, SITES[site], d, a.draws, a.steps, seed=i)
        calib[site] = {"n_ok": fits[site].n_ok, "n_failed": fits[site].n_failed, "params": fits[site].summary()}
        if truth:
            t = truth[site]
            calib[site]["truth"] = {**dict(zip(physics.names(t.process), map(float, t.theta))), "radial": t.radial,
                                    "fail_d_pin": FAIL_D[t.process]["pin"], "fail_d_hole": FAIL_D[t.process]["hole"],
                                    "fail_width": FAIL_WIDTH}
        plot_residuals(fits[site], d, out / f"residuals_{site}.png")
        print(f"{site}: {fits[site].n_ok} ok, {fits[site].n_failed} failed, "
              f"max R-hat {max(fits[site].rhat.values()):.3f}", flush=True)
    (out / "calibration.json").write_text(json.dumps(calib, indent=1))

    pred = predict(fits, cfg_kw, range(a.seed0, a.seed0 + a.seeds), a.workers)
    record = {**provenance(), "config": cfg_kw, "source": {"state": a.state, "scans": a.scans, "synthetic": a.synthetic},
              "seeds": [a.seed0, a.seed0 + a.seeds], **pred}
    (out / "prediction.json").write_text(json.dumps(record, indent=1))

    lines = [f"# Phase D prediction\n", f"    {record['command']}\n", f"git {record['git_hash']}{' (dirty)' if record['git_dirty'] else ''}\n",
             "| round | oracle gap closed, measured MAE: median [5%, 95%] | same, noise-free MAE | isolated − networked, noise-free (µm) |",
             "|---|---|---|---|"]
    for r in sorted(pred["gap"]):
        lines.append(f"| {r} | {_fmt(pred['gap'][r])} | {_fmt(pred['gap_truth'][r])} | {_fmt(pred['iso_minus_net_um'][r])} |")
    lines += ["", "## Calibration (mean ± sd, R-hat)", ""]
    for site, c in calib.items():
        cells = ", ".join(f"{k} {v['mean']:.4g} ± {v['sd']:.2g} ({v['rhat']:.2f})" for k, v in c["params"].items())
        lines.append(f"- **{site}** ({c['n_ok']} ok, {c['n_failed']} failed): {cells}")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
