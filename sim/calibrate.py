"""Phase D: calibrate the simulator to real seed data, then predict oracle-gap-closed.

    python -m sim.calibrate --state receipts/real/state.pkl --seeds 200 --out hpc/phase_d/out
    python -m sim.calibrate --synthetic 7 --draft --out ...   # self-check: seed data from a known sim world

The collective config comes from the `config` section of prereg/prereg.yaml
(prereg.check.config_from), the same place real runs take it from.

Step 1 fits each site's hidden truth for `sim.reference.SimPrinter` to the
seed-plate pieces only (held-out pieces on the seed plate are left out): the
physics parameters including `sigma_meas`, the unmodeled radial term, and the
failure model (50% failure diameter per kind and the logistic width).
Diameters are fit jointly across sites, with the shared parameters tied by the
same small between-site spread `make_world` draws them with, so a prediction
world has one shared truth like the real one. Failures are fit per site.
Both use adaptive Metropolis over several chains.

Step 2 runs the full experiment with the pre-registered config many times.
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
from dataclasses import asdict, dataclass, replace
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from arms.experiment import NOT_DATA, Config, run_experiment
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
SHARED_JITTER = 0.2    # site-to-site spread of the shared parameters, fraction of prior std (make_world's shared_jitter)
FAIL_D_STD = 0.4       # mm, prior around FAIL_D
LOG_WIDTH_STD = 0.5    # prior on log(fail_width) around log(FAIL_WIDTH)
FAIL_NAMES = ["fail_d_pin", "fail_d_hole", "fail_width"]


# ---- seed data -----------------------------------------------------------------

def seed_data_from_state(path: str | Path) -> tuple[dict[str, Data], dict[str, list[str]]]:
    """Seed-plate pieces from a real-run checkpoint (`run.py --source real`), and per site the
    printed seed pieces the run kept out of its data (arms.experiment.NOT_DATA: a cell outside
    the scan, a dropped plate)."""
    with open(path, "rb") as f:
        state = pickle.load(f)
    data = {s: [(p, m) for p, m in st.data["isolated"] if p.arm == "seed"] for s, st in state["sites"].items()}
    printed = {s: [p.piece_id for p in state["pieces"].values() if p.arm == "seed" and p.piece_id.startswith(f"{s}-seed-")]
               for s in data}
    return data, {s: sorted(set(printed[s]) - {p.piece_id for p, _ in d}) for s, d in data.items()}


def seed_data_from_scans(scan_dir: str | Path) -> tuple[dict[str, Data], dict[str, list[str]]]:
    """Seed-plate pieces from `scans/<site>/<site>-seed-measurements.json` (measure/real.py),
    routed like the checkpoint: NOT_DATA rows are returned as not measured, not as failures."""
    data, dropped = {}, {}
    for site in SITES:
        plate = seed_plate(site, None)  # every id the seed plate can have; the scan file holds the printed ones
        rows = json.loads((Path(scan_dir) / site / f"{plate.plate_id}-measurements.json").read_text())
        by_id = {r["piece_id"]: Measurement(**r) for r in rows}
        seed = [(p, by_id[p.piece_id]) for p in plate.pieces if p.arm == "seed" and p.piece_id in by_id]
        data[site] = [(p, m) for p, m in seed if m.method not in NOT_DATA]
        dropped[site] = sorted(p.piece_id for p, m in seed if m.method in NOT_DATA)
    return data, dropped


def seed_data_synthetic(seed: int, keep: int | None = None) -> tuple[dict[str, Data], dict[str, SimPrinter]]:
    """Seed-plate pieces from a known sim world, to check that calibration recovers it.

    `keep` thins the seed plate the way the experiment does (Config.seed_pieces).
    """
    world = make_world(SITES, seed)
    out = {}
    for site, printer in world.items():
        plate = seed_plate(site, keep)
        ms = {m.piece_id: m for m in printer.print_and_measure(plate)}
        out[site] = [(p, ms[p.piece_id]) for p in plate.pieces if p.arm == "seed"]
    return out, world


def check_seed_size(data: dict[str, Data], keep: int | None, dropped: dict[str, list[str]] | None = None) -> None:
    """The seed data must be the seed plate the pre-registered config prints, or the calibration fits a different setup.

    `dropped` pieces were printed but aren't data (not measured); they count as on the plate.
    """
    for s, d in data.items():
        if not d:
            raise SystemExit(f"{s}: no seed piece measured (seed plate dropped?); reprint before calibrating")
    dropped = dropped or {}
    want = {s: sorted(p.piece_id for p in seed_plate(s, keep).pieces if p.arm == "seed") for s in data}
    got = {s: sorted([p.piece_id for p, _ in d] + dropped.get(s, [])) for s, d in data.items()}
    if got != want:
        got, want = ({s: len(x) for s, x in v.items()} for v in (got, want))
        raise SystemExit(f"seed pieces per site {got} don't match the frozen config's seed_pieces={keep} ({want})")


def screen_failures(data: dict[str, Data], exclude: list[str]) -> dict[str, Data]:
    """Keep only failures that are printability outcomes.

    "failed" also covers a whole plate the operator marked failed and pieces the
    scanner couldn't read. A plate with every piece failed can't be calibrated;
    `exclude` drops failed pieces judged (from the summary's list) to be scanner misses.
    """
    for site, d in data.items():
        if d and all(m.status == "failed" for _, m in d):
            raise SystemExit(f"{site}: every seed piece failed (whole plate failed?); reprint before calibrating")
    failed = {p.piece_id for d in data.values() for p, m in d if m.status == "failed"}
    if bad := sorted(set(exclude) - failed):
        raise SystemExit(f"--exclude-failed names pieces that aren't failed seed pieces: {bad}")
    return {s: [(p, m) for p, m in d if p.piece_id not in exclude] for s, d in data.items()}


def failed_pieces(d: Data) -> list[dict]:
    return [{"piece_id": p.piece_id, "kind": p.kind, "nominal_d": p.nominal_d, "slot": list(p.slot)}
            for p, m in d if m.status == "failed"]


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
        return _summary(self.names + FAIL_NAMES, np.hstack([self.draws, self.fail_draws]), self.rhat)

    def printer(self, k: int, seed: int) -> SimPrinter:
        theta, radial = self.draws[k, :-1], float(self.draws[k, -1])
        fp, fh, fw = self.fail_draws[k]
        return SimPrinter(self.site, self.process, theta.copy(), radial, np.random.default_rng(seed),
                          fail_d={"pin": float(fp), "hole": float(fh)}, fail_width=float(fw))


@dataclass
class Calibration:
    """Joint fit of every site. Row k of each site's draws comes from the same joint sample."""
    sites: dict[str, SiteFit]
    shared: np.ndarray        # [K, len(SHARED)] world-level shared parameters
    shared_rhat: dict[str, float]

    def __len__(self) -> int:
        return len(self.shared)

    def world(self, k: int, rng: np.random.Generator) -> dict[str, SimPrinter]:
        return {s: f.printer(k, int(rng.integers(2**32))) for s, f in self.sites.items()}

    def summary(self) -> dict:
        return {"shared_world": _summary([sp.name for sp in physics.SHARED], self.shared, self.shared_rhat),
                **{s: f.summary() for s, f in self.sites.items()}}


def _summary(names: list[str], draws: np.ndarray, rh: dict[str, float]) -> dict[str, dict[str, float]]:
    return {k: {"mean": float(v.mean()), "sd": float(v.std()), "q05": float(np.quantile(v, 0.05)),
                "q95": float(np.quantile(v, 0.95)), "rhat": rh[k]} for k, v in zip(names, draws.T)}


def _site_loglik(process: str, data: Data):
    """Gaussian log likelihood of a site's ok diameters given theta [N, P] and radial [N]."""
    ok = [(p, m) for p, m in data if m.status == "ok"]
    x = PieceArrays.from_pieces([p for p, _ in ok])
    y = np.array([m.measured_d for _, m in ok])
    r2 = (x.u**2 + x.v**2) / 2

    def loglik(theta: np.ndarray, radial: np.ndarray) -> np.ndarray:
        mu = physics.predict_d(process, x, theta) + radial[:, None] * r2
        sig = physics.sigma(process, theta)[:, None]
        return (-0.5 * ((y - mu) / sig) ** 2 - np.log(sig)).sum(axis=1)

    return loglik, len(ok)


def _joint_logp(blocks: list[tuple[str, slice, object]], jitter: float):
    """Hierarchical posterior over every site's theta + radial, plus world-level shared parameters g.

    Mirrors make_world: g ~ shared prior; each site's shared parameters ~ N(g, (jitter * prior_std)^2)
    within bounds; site-only parameters and radial get their own priors.
    """
    shared_std = np.array([sp.prior_std for sp in physics.SHARED])
    shared_lo = np.array([sp.lo for sp in physics.SHARED])
    shared_hi = np.array([sp.hi for sp in physics.SHARED])
    n_shared = len(physics.SHARED)

    def logp(z: np.ndarray) -> np.ndarray:
        g = z[:, -n_shared:]
        lp = physics.log_prior(physics.SHARED, g)
        for process, sl, loglik in blocks:
            theta, radial = z[:, sl][:, :-1], z[:, sl][:, -1]
            site_cols = [j for j, sp in enumerate(physics.PARAMS[process]) if sp.tag == "site"]
            shared_cols = [physics.index(process)[sp.name] for sp in physics.SHARED]
            sh = theta[:, shared_cols]
            lp = lp + physics.log_prior([physics.PARAMS[process][j] for j in site_cols], theta[:, site_cols])
            lp = lp - 0.5 * (((sh - g) / (jitter * shared_std)) ** 2).sum(axis=1) - 0.5 * (radial / RADIAL_STD) ** 2
            lp = np.where(((sh >= shared_lo) & (sh <= shared_hi)).all(axis=1), lp, -np.inf)
            good = np.isfinite(lp)
            if good.any():
                lp[good] += loglik(theta[good], radial[good])
        return lp

    return logp


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


def _fit_failures(process: str, data: Data, n_draws: int, steps: int, chains: int, rng):
    f0 = np.column_stack([rng.normal(FAIL_D[process]["pin"], 0.1, chains), rng.normal(FAIL_D[process]["hole"], 0.1, chains),
                          rng.normal(math.log(FAIL_WIDTH), 0.1, chains)])
    fdraws, frh = _run_chains(_failure_logp(process, data), f0, np.array([0.1, 0.1, 0.1]), steps, n_draws, rng)
    fdraws[:, 2] = np.exp(fdraws[:, 2])
    return fdraws, frh


def fit(data: dict[str, Data], n_draws: int = 2000, steps: int = 60000, chains: int = 8, seed: int = 0,
        jitter: float = SHARED_JITTER) -> Calibration:
    """Fit every site's hidden truth jointly; failures are fit per site (separate likelihood)."""
    rng = np.random.default_rng(seed)
    blocks, x0, scale, col, n_ok = [], [], [], 0, {}
    for site, d in data.items():
        process = SITES[site]
        specs = physics.PARAMS[process]
        loglik, n_ok[site] = _site_loglik(process, d)
        blocks.append((process, slice(col, col + len(specs) + 1), loglik))
        col += len(specs) + 1
        x0.append(np.hstack([physics.sample_prior(process, chains, rng), rng.normal(0, RADIAL_STD, (chains, 1))]))
        scale += [sp.prior_std * 0.1 for sp in specs] + [RADIAL_STD * 0.1]
    x0.append(physics.sample_prior(physics.SHARED, chains, rng))
    scale += [sp.prior_std * 0.1 for sp in physics.SHARED]

    draws, rh = _run_chains(_joint_logp(blocks, jitter), np.hstack(x0), np.array(scale), steps, n_draws, rng)
    sites = {}
    for (site, d), (process, sl, _) in zip(data.items(), blocks):
        names = physics.names(process) + ["radial"]
        fdraws, frh = _fit_failures(process, d, n_draws, steps // 4, chains, rng)
        sites[site] = SiteFit(site, process, names, draws[:, sl], fdraws,
                              dict(zip(names + FAIL_NAMES, map(float, np.r_[rh[sl], frh]))), n_ok[site], len(d) - n_ok[site])
    shared_names = [sp.name for sp in physics.SHARED]
    return Calibration(sites, draws[:, -len(shared_names):], dict(zip(shared_names, map(float, rh[-len(shared_names):]))))


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

_WORKER: tuple[Calibration, Config] | None = None  # set once per pool worker, so draws aren't re-sent per seed


def _init_worker(calib: Calibration, cfg: Config) -> None:
    global _WORKER
    _WORKER = calib, cfg


def _run_worker(seed: int) -> dict:
    return run_seed(seed, *_WORKER)


def run_seed(seed: int, calib: Calibration, cfg: Config) -> dict:
    rng = np.random.default_rng([seed, 0xD])
    world = calib.world(int(rng.integers(len(calib))), rng)
    res = run_experiment(world, SITES, replace(cfg, seed=seed))
    # a site with no ok held-out pieces scores mae_truth None; NaN drops it from this seed's numbers
    scores = [{**row, "mae_truth": math.nan if row["mae_truth"] is None else row["mae_truth"]} for row in res.scores]

    def iso_minus_net(metric: str) -> dict[int, float]:
        by = {}
        for row in scores:
            by.setdefault(row["round"], {}).setdefault(row["arm"], []).append(row[metric])
        return {r: 1000 * (np.nanmean(a["isolated"]) - np.nanmean(a["networked"])) for r, a in by.items()}

    # iso - net on measured MAE is the primary H1 metric (07-status); gap closed is reported as a reference
    return {"seed": seed,
            "iso_minus_net_um": iso_minus_net("mae"),
            "iso_minus_net_truth_um": iso_minus_net("mae_truth"),
            "gap": oracle_gap_closed(scores, "mae"),
            "gap_truth": oracle_gap_closed(scores, "mae_truth")}


def _interval(v: list[float]) -> dict[str, float | None]:
    a = np.array([x for x in v if not math.isnan(x)])
    if not len(a):
        return {"median": None, "q05": None, "q25": None, "q75": None, "q95": None, "n": 0}
    q = np.quantile(a, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {"median": q[2], "q05": q[0], "q25": q[1], "q75": q[3], "q95": q[4], "n": len(a)}


def predict(calib: Calibration, cfg: Config, seeds: range, workers: int) -> dict:
    # spawn: fork is unsafe once Warp has started threads
    with get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(calib, cfg)) as pool:
        rows = pool.map(_run_worker, seeds, chunksize=1)
    rounds = sorted(rows[0]["gap"])
    return {key: {r: _interval([row[key][r] for row in rows]) for r in rounds}
            for key in ("iso_minus_net_um", "iso_minus_net_truth_um", "gap", "gap_truth")}


def load_config(path: str | Path, draft: bool = False) -> tuple[Config, str, list[str]]:
    """Config from the prereg's `config` section, its sha256, and the fields still null.

    The prediction needs every field a seed-plate run needs. `draft` runs anyway, with
    Config defaults for the null fields, for checking the pipeline before tuning is frozen.
    """
    from prereg.check import config_from, load, missing
    prereg, sha = load(path)
    gaps = missing(prereg, "seed")
    if gaps and not draft:
        raise SystemExit(f"{path} incomplete, fill in before predicting (or pass --draft):\n  " + "\n  ".join(gaps))
    cfg = config_from(prereg, sha)
    if cfg.bad_sites or not cfg.share_messages:
        raise SystemExit(f"{path} config has an ablation on (bad_sites / share_messages)")
    return cfg, sha, gaps


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
    ap.add_argument("--prereg", default=str(ROOT / "prereg" / "prereg.yaml"), help="config comes from its `config` section")
    ap.add_argument("--draft", action="store_true", help="run with null prereg fields at Config defaults; output marked DRAFT")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=50000, help="first experiment seed (away from run.py and Phase C)")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--steps", type=int, default=60000)
    ap.add_argument("--shared-jitter", type=float, default=SHARED_JITTER,
                    help="assumed site-to-site spread of the shared parameters, fraction of prior std")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--exclude-failed", nargs="*", default=[], metavar="PIECE_ID",
                    help="failed seed pieces to leave out of the failure fit (scanner misses, not print failures)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    cfg, prereg_sha, gaps = load_config(a.prereg, a.draft)
    truth, dropped = None, {}
    if a.state:
        data, dropped = seed_data_from_state(a.state)
    elif a.scans:
        data, dropped = seed_data_from_scans(a.scans)
    else:
        data, truth = seed_data_synthetic(a.synthetic, cfg.seed_pieces)
    check_seed_size(data, cfg.seed_pieces, dropped)
    data = screen_failures(data, a.exclude_failed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    fitted = fit(dict(sorted(data.items())), a.draws, a.steps, jitter=a.shared_jitter)
    fits = fitted.sites
    calib = {"shared_world": {"params": fitted.summary()["shared_world"]}}
    for site, d in sorted(data.items()):
        calib[site] = {"n_ok": fits[site].n_ok, "n_failed": fits[site].n_failed, "failed": failed_pieces(d),
                       "not_measured": dropped.get(site, []),
                       "excluded": [x for x in a.exclude_failed if x.startswith(f"{site}-")], "params": fits[site].summary()}
        if truth:
            t = truth[site]
            calib[site]["truth"] = {**dict(zip(physics.names(t.process), map(float, t.theta))), "radial": t.radial,
                                    "fail_d_pin": FAIL_D[t.process]["pin"], "fail_d_hole": FAIL_D[t.process]["hole"],
                                    "fail_width": FAIL_WIDTH}
        plot_residuals(fits[site], d, out / f"residuals_{site}.png")
        print(f"{site}: {fits[site].n_ok} ok, {fits[site].n_failed} failed, {len(dropped.get(site, []))} not measured, "
              f"max R-hat {max(fits[site].rhat.values()):.3f}", flush=True)
    (out / "calibration.json").write_text(json.dumps(calib, indent=1))

    pred = predict(fitted, cfg, range(a.seed0, a.seed0 + a.seeds), a.workers)
    record = {**provenance(), "prereg_sha256": prereg_sha, "draft_null_fields": gaps, "config": asdict(cfg), "source": {"state": a.state, "scans": a.scans, "synthetic": a.synthetic},
              "seeds": [a.seed0, a.seed0 + a.seeds], **pred}
    (out / "prediction.json").write_text(json.dumps(record, indent=1))

    lines = [f"# Phase D prediction{' (DRAFT: null prereg fields at defaults: ' + ', '.join(gaps) + ')' if gaps else ''}\n",
             f"    {record['command']}\n", f"git {record['git_hash']}{' (dirty)' if record['git_dirty'] else ''}, prereg sha256 {prereg_sha}\n",
             "Median [5%, 95%] over seeds. Isolated − networked on measured MAE is the primary metric (what real rounds produce).\n",
             "| round | isolated − networked, measured MAE (µm) | same, noise-free MAE (µm) | oracle gap closed, measured MAE | same, noise-free MAE |",
             "|---|---|---|---|---|"]
    for r in sorted(pred["gap"]):
        lines.append(f"| {r} | " + " | ".join(_fmt(pred[k][r]) for k in ("iso_minus_net_um", "iso_minus_net_truth_um", "gap", "gap_truth")) + " |")
    lines += ["", "## Calibration (mean ± sd, R-hat)", ""]
    for site, c in calib.items():
        cells = ", ".join(f"{k} {v['mean']:.4g} ± {v['sd']:.2g} ({v['rhat']:.2f})" for k, v in c["params"].items())
        counts = f" ({c['n_ok']} ok, {c['n_failed']} failed)" if "n_ok" in c else ""
        lines.append(f"- **{site}**{counts}: {cells}")
    lines += ["", "## Failed seed pieces (fit as printability failures; check for scanner misses)", ""]
    for site, c in calib.items():
        if "failed" in c:
            items = ", ".join(f"{f['piece_id']} ({f['kind']} {f['nominal_d']} mm)" for f in c["failed"]) or "none"
            lines.append(f"- **{site}**: {items}" + (f"; excluded: {', '.join(c['excluded'])}" if c["excluded"] else "")
                         + (f"; not measured (left out): {', '.join(c['not_measured'])}" if c["not_measured"] else ""))
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
