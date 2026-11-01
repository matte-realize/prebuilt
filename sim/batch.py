"""Batched experiment runner: many seeds of `arms.run_experiment` per GPU launch.

    python -m sim.batch --seeds 256 --sites 2 --out results.json

The arms are unchanged. Each seed runs `run_experiment`
in its own thread, with Warp printers and a batched posterior injected. When
every running seed is waiting on a posterior fit or a print, all those waits
are served together: one `PosteriorBatch` update and one `WarpSim` launch for
every seed at once.

Seeds never see each other. Each keeps its own world, noise streams and
posterior seeds, so a seed's results don't depend on which seeds share its
batch.

The posterior update (resample-move SMC, nearly all of the CPU path's time)
runs on the GPU. The per-piece queries the arms make afterwards (predict,
log_predictive, intervals, agent scoring) are small weighted sums over the
particles, so they run on a host copy with the NumPy reference. That is
faster than one GPU launch per piece.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from functools import partial

import numpy as np

from agents.agents import DORMANT_NAMES
from arms.experiment import Config, Results, run_experiment
from contracts import Measurement, Plate
from eval.audit import audit
from eval.metrics import oracle_gap_closed, summarize, with_fit
from model import posterior as reference
from model import posterior_warp
from plates.seed import SEED_PIECES
from prereg.check import fit_thresholds, load
from sim import warp_sim


def site_names(k: int) -> dict[str, str]:
    """k simulated sites, alternating processes: resin, pla, resin2, pla2, resin3, ...

    k = 2 gives run.py's two sites, so the two runners see the same worlds.
    """
    procs = [warp_sim.PROCESSES[i % 2] for i in range(k)]
    return {p if i < 2 else f"{p}{i // 2 + 1}": p for i, p in enumerate(procs)}


class Batcher:
    """Runs jobs in threads and serves their waits in batches."""

    def __init__(self, device: str | None = None):
        self.device = device
        self.launches = defaultdict(int)  # kind -> batches served
        self._cond = threading.Condition()
        self._waiting: dict[int, tuple[str, object]] = {}  # job -> (kind, arg); one wait per job at a time
        self._results: dict[int, tuple[object, BaseException | None]] = {}
        self._live = 0
        self._job = threading.local()

    def run(self, jobs: list[Callable[[], object]]) -> list:
        """Run every job to completion; returns their results in order, or raises the first error."""
        out: list = [None] * len(jobs)
        errors: list[BaseException | None] = [None] * len(jobs)

        def target(i: int) -> None:
            self._job.i = i
            try:
                out[i] = jobs[i]()
            except BaseException as e:  # noqa: BLE001 - re-raised after every job has stopped
                errors[i] = e
            finally:
                with self._cond:
                    self._live -= 1
                    self._serve_if_all_waiting()

        self._live = len(jobs)
        threads = [threading.Thread(target=target, args=(i,), daemon=True) for i in range(len(jobs))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for e in errors:
            if e is not None:
                raise e
        return out

    def posterior(self, *args, **kwargs) -> BatchedPosterior:
        """Posterior factory for `run_experiment(..., posterior=...)`."""
        return BatchedPosterior(self, *args, **kwargs)

    def wait(self, kind: str, arg) -> object:
        """Block until this wait is served with every other running job's."""
        i = self._job.i
        with self._cond:
            self._waiting[i] = (kind, arg)
            self._serve_if_all_waiting()
            while i not in self._results:
                self._cond.wait()
            result, error = self._results.pop(i)
        if error is not None:
            raise error
        return result

    def _serve_if_all_waiting(self) -> None:
        """Called with the lock held. Runs on whichever thread completes the barrier."""
        if not self._waiting or len(self._waiting) < self._live:
            return
        by_kind = defaultdict(list)
        for i in sorted(self._waiting):  # job order, so launches don't depend on thread timing
            kind, arg = self._waiting[i]
            by_kind[kind].append((i, arg))
        self._waiting = {}
        for kind, items in by_kind.items():
            jobs, args = zip(*items)
            try:
                results, error = SERVE[kind](list(args)), None
            except BaseException as e:  # noqa: BLE001 - handed to every waiting job
                results, error = [None] * len(jobs), e
            self.launches[kind] += 1
            for i, r in zip(jobs, results):
                self._results[i] = (r, error)
        self._cond.notify_all()


# ---- posterior -----------------------------------------------------------

class BatchedPosterior:
    """`model.posterior.ParticlePosterior` API for one fit in a batched run.

    `set_prior_from_summary` and `update` are queued. The first read after
    them waits for the batch, which applies them on the GPU and copies the
    particles back to the host copy that answers every read.
    """

    def __init__(self, batcher: Batcher, sites: str | dict[str, str], pieces, n: int = 4000, seed: int = 0,
                 ess_frac: float = 0.5, mh_steps: int = 3, between_site_sd: float | None = None):
        self._batcher = batcher
        self._kw = dict(sites=sites, pieces=pieces, n=n, seed=seed, ess_frac=ess_frac, mh_steps=mh_steps,
                        between_site_sd=between_site_sd)
        # same prior draws as the GPU member (both use Layout.sample_prior with this seed)
        self._host = reference.ParticlePosterior(**self._kw)
        self._gpu: posterior_warp.ParticlePosterior | None = None
        self._todo: list[tuple[str, tuple]] = []  # ("prior", args) or ("update", (ms,)), in call order

    def update(self, ms: list[Measurement]) -> None:
        ok = reference.usable(ms)
        if ok:
            self._todo.append(("update", (ok,)))

    def set_prior_from_summary(self, means: dict[str, float], cov: np.ndarray, weight: float, key: str = "default") -> None:
        self._todo.append(("prior", (means, cov, weight, key)))

    def __getattr__(self, name: str):
        # Only reached for names not set above: every read goes to the synced host copy.
        # (Agents read some private helpers too, e.g. _only_site.)
        if name in _OWN or name.startswith("__"):
            raise AttributeError(name)  # not set yet (e.g. mid-__init__ or unpickling): don't recurse
        if self._todo:
            self._batcher.wait("fit", self)
        return getattr(self._host, name)


_OWN = {"_batcher", "_kw", "_host", "_gpu", "_todo"}


def _serve_fits(posts: list[BatchedPosterior]) -> list[None]:
    groups = defaultdict(list)  # members of one PosteriorBatch must share n, ess_frac, mh_steps
    for p in posts:
        if p._gpu is None:
            groups[p._kw["n"], p._kw["ess_frac"], p._kw["mh_steps"]].append(p)
    device = posts[0]._batcher.device
    for (n, ess_frac, mh_steps), new in groups.items():
        member = lambda k: [p._kw[k] for p in new]  # noqa: E731
        batch = posterior_warp.PosteriorBatch(member("sites"), member("pieces"), member("seed"), n=n, ess_frac=ess_frac,
                                              mh_steps=mh_steps, between_site_sd=member("between_site_sd"), device=device)
        for i, p in enumerate(new):
            p._gpu = batch[i]

    # Apply each fit's queue in order: priors one member at a time, then the next
    # update of every fit that has one, batched per PosteriorBatch.
    while any(p._todo for p in posts):
        updates = {}  # id(batch) -> (batch, member -> measurements)
        for p in posts:
            while p._todo and p._todo[0][0] == "prior":
                p._gpu.set_prior_from_summary(*p._todo.pop(0)[1])
            if p._todo:
                b = p._gpu.batch
                updates.setdefault(id(b), (b, {}))[1][p._gpu.i] = p._todo.pop(0)[1][0]
        for b, ms in updates.values():
            b.update(ms)

    host = {}  # one device -> host copy per batch
    for p in posts:
        b = p._gpu.batch
        if id(b) not in host:
            host[id(b)] = (b.theta_d.numpy(), b.logw_d.numpy())
        theta, logw = host[id(b)]
        p._host.theta = theta[p._gpu.i, :, : len(p._host.specs)].copy()
        p._host.logw = logw[p._gpu.i].copy()
    return [None] * len(posts)


# ---- printers ------------------------------------------------------------

class BatchedPrinter:
    """A `contracts.Printer` whose prints wait to share one WarpSim launch."""

    def __init__(self, printer: warp_sim.WarpPrinter, batcher: Batcher):
        self.site, self.printer, self._batcher = printer.site, printer, batcher

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        return self._batcher.wait("print", (self.printer, plate))

    def truth(self, plate: Plate) -> np.ndarray:
        """Noise-free diameters including unmodeled effects (for evaluation only)."""
        return self._batcher.wait("truth", (self.printer, plate))


def _plates(items: list[tuple[warp_sim.WarpPrinter, Plate]]) -> tuple[warp_sim.WarpSim, list[int], list[Plate]]:
    sims = {id(p.sim) for p, _ in items}
    if len(sims) > 1:
        raise ValueError("batched printers must share one WarpSim (see warp_sim.merge)")
    return items[0][0].sim, [p.index for p, _ in items], [plate for _, plate in items]


def _split(flat: np.ndarray, plates: list[Plate]) -> list[np.ndarray]:
    return np.split(flat, np.cumsum([len(p.pieces) for p in plates])[:-1])


def _serve_prints(items) -> list[list[Measurement]]:
    sim, sites, plates = _plates(items)
    res = sim.print_plates(sites, plates)
    return [warp_sim.measurements(plate, y) for plate, y in zip(plates, _split(res.measured, plates))]


def _serve_truths(items) -> list[np.ndarray]:
    sim, sites, plates = _plates(items)
    return _split(sim.truth_plates(sites, plates), plates)


SERVE = {"fit": _serve_fits, "print": _serve_prints, "truth": _serve_truths}


# ---- entry points --------------------------------------------------------

def run_batch(seeds: list[int], sites: dict[str, str], cfg: Config = Config(),
              orient_std: float = warp_sim.ORIENT_STD, device: str | None = None) -> list[Results]:
    """`run_experiment` for every seed, batched; seed s runs `cfg` with `seed=s`.

    Seed s sees `warp_sim.make_world(sites, s, orient_std=orient_std)`, exactly
    as it would in a sequential run with Warp printers.
    """
    batcher = Batcher(device)
    worlds = warp_sim.merge([warp_sim.make_world(sites, s, orient_std=orient_std, device=device) for s in seeds],
                            device=device)
    jobs = [
        partial(run_experiment, {s: BatchedPrinter(p, batcher) for s, p in world.items()}, sites,
                replace(cfg, seed=seed), posterior=batcher.posterior)
        for seed, world in zip(seeds, worlds)
    ]
    return batcher.run(jobs)


def _run_chunk(seeds: list[int], sites: dict[str, str], cfg: Config, orient_std: float, device: str | None,
               thresholds: dict | None):
    """One worker's batch: per seed, score rows (with fit classes, as run.py writes them) and a status line."""
    out = []
    for seed, res in zip(seeds, run_batch(seeds, sites, cfg, orient_std, device)):
        rep = audit(list(res.chains.values()))
        spawned = ", ".join(f"{x['agent']}@{x['site']} r{x['round']}" for x in res.spawned) or "none"
        status = (f"seed {seed}: privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings); "
                  f"{len(res.challenges)} challenge flags; spawned: {spawned}")
        out.append((seed, with_fit(res.scores, res.predictions, thresholds, sites), status))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", type=int, default=1, help="number of seeds")
    ap.add_argument("--seed", type=int, default=0, help="first seed")
    ap.add_argument("--sites", type=int, default=2, help="sites per world (resin, pla, resin2, pla2, ...)")
    ap.add_argument("--batch", type=int, default=16, help="seeds per batch, all served in the same launches")
    ap.add_argument("--workers", type=int, default=8,
                    help="processes sharing the GPU; the host side of each batch is single-threaded Python, "
                         "so several workers keep the GPU busy. Each holds its own CUDA context and memory pool: "
                         "8 saturates an 8 GB RTX 5060, 16 runs out of GPU memory")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--particles", type=int, default=2000)
    ap.add_argument("--oracle-particles", type=int, default=None, help="oracle arm particles (default: --particles)")
    ap.add_argument("--bad-site", action="append", default=[], help="site that broadcasts bad beliefs")
    ap.add_argument("--no-messages", action="store_true", help="ablation: cut the network")
    ap.add_argument("--challenge", action="store_true", help="secondary analysis: run the challenge round (networked arm)")
    ap.add_argument("--spawn", action="store_true", help="secondary analysis: dormant agents can wake (networked arm)")
    ap.add_argument("--seed-pieces", type=int, default=SEED_PIECES, help="calibration pieces on the seed plate (max 56)")
    ap.add_argument("--slots", type=int, default=Config.slots_per_arm, help="slots per arm per plate")
    ap.add_argument("--lpd-clip", type=lambda v: None if v.lower() == "none" else float(v), default=Config.lpd_clip,
                    help="per-piece held-out dLPD bound in nats for credit ('none' = unclipped)")
    ap.add_argument("--prereg", default="prereg/prereg.yaml", help="pre-registration file (fit classes)")
    ap.add_argument("--orient-std", type=float, default=warp_sim.ORIENT_STD,
                    help="sim orientation-error scale, mm (0 = the world run.py --source sim uses)")
    ap.add_argument("--device", default=None, help="Warp device (default: CUDA if available)")
    ap.add_argument("--out", default=None, help="write results JSON here (run.py --out row format)")
    args = ap.parse_args()

    sites = site_names(args.sites)
    unknown = set(args.bad_site) - set(sites)
    if unknown:
        ap.error(f"--bad-site {sorted(unknown)} not among sites {list(sites)}")
    # the same Config run.py --source sim builds
    cfg = Config(rounds=args.rounds, n_particles=args.particles, oracle_particles=args.oracle_particles,
                 bad_sites=tuple(args.bad_site), share_messages=not args.no_messages,
                 seed_pieces=args.seed_pieces, slots_per_arm=args.slots, lpd_clip=args.lpd_clip,
                 challenge=args.challenge, dormant=tuple(DORMANT_NAMES) if args.spawn else ())
    thresholds = fit_thresholds(load(args.prereg)[0])

    seeds = list(range(args.seed, args.seed + args.seeds))
    chunks = [seeds[i : i + args.batch] for i in range(0, len(seeds), args.batch)]
    run = partial(_run_chunk, sites=sites, cfg=cfg, orient_std=args.orient_std, device=args.device,
                  thresholds=thresholds)
    t0 = time.perf_counter()
    if args.workers > 1 and len(chunks) > 1:
        # spawn, not fork: each worker needs its own CUDA context
        with ProcessPoolExecutor(min(args.workers, len(chunks)), mp_context=multiprocessing.get_context("spawn")) as ex:
            done = [r for chunk in ex.map(run, chunks) for r in chunk]
    else:
        done = [r for chunk in chunks for r in run(chunk)]
    elapsed = time.perf_counter() - t0

    gaps, all_rows = defaultdict(list), []
    for seed, scores, status in done:
        if args.seeds == 1:
            print(summarize(scores))
        print(status)
        for r, g in oracle_gap_closed(scores).items():
            gaps[r].append(g)
        all_rows += [{**row, "seed": seed} for row in scores]
    print(f"{len(seeds)} seeds x {len(sites)} sites in {elapsed:.1f} s ({3600 * len(seeds) / elapsed:,.0f} seeds/hour)")
    if args.seeds > 1:
        for r, g in sorted(gaps.items()):
            g = np.array([x for x in g if not math.isnan(x)])
            print(f"round {r}: oracle gap closed (MAE) median {np.median(g):.2f}, "
                  f"IQR [{np.percentile(g, 25):.2f}, {np.percentile(g, 75):.2f}], n={len(g)}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(all_rows, f, indent=1)


if __name__ == "__main__":
    main()
