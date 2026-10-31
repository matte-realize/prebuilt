"""NVIDIA Warp simulator: many sites, one kernel launch.

Same hidden truth as sim/reference.py, which stays the readable reference this
must match: the physics.PARAMS parameterization, make_world's world generation
(shared parameters drawn once per world, jittered per site) and the
FAIL_D / FAIL_WIDTH failure model. On top of the reference's radial
plate-position term it adds a second unmodeled effect, an orientation error:
each site has a hidden in-plane anisotropy axis, and each printed plate sits on
the bed at a hidden rotation relative to it, so a slot's error depends on its
direction from the plate center and on how that plate happened to be placed:

    orient_amp * cos(2 * (atan2(v, u) + plate_rot - orient_phase))

Agents never see either effect.

Two layers:
- `draw_sites` + `WarpSim.print_arrays`: domain randomization. Draw thousands
  of sites and print a batch of plates in one launch; arrays in, arrays out.
- `WarpPrinter`: one site of a `WarpSim`, implementing `contracts.Printer`, so
  arms/ and run.py can't tell it from `SimPrinter`. `make_world` is the
  drop-in for `sim.reference.make_world`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import warp as wp

from contracts import Measurement, Plate
from model import physics
from model.physics import PieceArrays
from sim import reference
from sim.reference import FAIL_D, FAIL_WIDTH

PROCESSES = ["resin", "pla"]  # process id = index here
KINDS = ["pin", "hole"]       # kind id = index here

# Kernel column layout: the union of both processes' parameters, by name, so the
# kernel never depends on the column order inside physics.PARAMS.
COLS = ["Dp", "Ec", "k_bleed", "shrink", "w_off", "poly_k", "flare", "sigma_meas", "size_coef", "pos_gx", "pos_gy"]
DP = wp.constant(0)
EC = wp.constant(1)
K_BLEED = wp.constant(2)
SHRINK = wp.constant(3)
W_OFF = wp.constant(4)
POLY_K = wp.constant(5)
FLARE = wp.constant(6)
SIGMA = wp.constant(7)
SIZE_COEF = wp.constant(8)
POS_GX = wp.constant(9)
POS_GY = wp.constant(10)

ORIENT_STD = 0.01  # mm, default orientation-error amplitude scale (small)

# splitmix64, the same constants as `_mix` on the host
GOLDEN = wp.constant(wp.uint64(0x9E3779B97F4A7C15))
MIX1 = wp.constant(wp.uint64(0xBF58476D1CE4E5B9))
MIX2 = wp.constant(wp.uint64(0x94D049BB133111EB))
TWO_M53 = wp.constant(wp.float64(2.0**-53))
TWO_PI = wp.constant(wp.float64(2.0 * np.pi))


def to_cols(process: str, theta: np.ndarray) -> np.ndarray:
    """[N, P] in PARAMS[process] order -> [N, len(COLS)], zeros for unused columns."""
    out = np.zeros((theta.shape[0], len(COLS)))
    for name, j in physics.index(process).items():
        out[:, COLS.index(name)] = theta[:, j]
    return out


def from_cols(process: str, cols: np.ndarray) -> np.ndarray:
    """Inverse of `to_cols`."""
    return cols[:, [COLS.index(n) for n in physics.names(process)]]


@dataclass
class SiteBatch:
    """Hidden truth for S sites, host-side."""
    process: np.ndarray       # [S] int, index into PROCESSES
    theta: np.ndarray         # [S, len(COLS)]
    radial: np.ndarray        # [S] mm at the plate corner
    orient_amp: np.ndarray    # [S] mm
    orient_phase: np.ndarray  # [S] rad, anisotropy axis
    salt: np.ndarray          # [S] uint64, mixes with plate.seed to place each plate on the bed
    fail_d: np.ndarray | None = None      # [S, len(KINDS)] mm, 50% failure diameter; None = FAIL_D by process
    fail_width: np.ndarray | None = None  # [S] mm, logistic width; None = FAIL_WIDTH

    def __len__(self) -> int:
        return len(self.process)

    def failure(self) -> tuple[np.ndarray, np.ndarray]:
        """Per-site (fail_d [S, len(KINDS)], fail_width [S]), filling in the defaults."""
        fail_d = self.fail_d if self.fail_d is not None else np.array(
            [[FAIL_D[PROCESSES[p]][k] for k in KINDS] for p in self.process], float).reshape(len(self), len(KINDS))
        fail_width = self.fail_width if self.fail_width is not None else np.full(len(self), FAIL_WIDTH)
        return fail_d, fail_width

    def theta_of(self, i: int) -> np.ndarray:
        """Site i's parameters in PARAMS[process] order."""
        return from_cols(PROCESSES[self.process[i]], self.theta[i : i + 1])[0]


def _draw_orientation(n: int, rng: np.random.Generator, orient_std: float):
    return rng.normal(0, orient_std, n), rng.uniform(0, np.pi, n), rng.integers(2**63, size=n, dtype=np.uint64)


def draw_sites(processes: list[str] | np.ndarray, seed: int, shared_jitter: float = 0.2,
               radial_std: float = 0.02, orient_std: float = ORIENT_STD) -> SiteBatch:
    """Domain randomization: one world with len(processes) sites.

    Same distribution as `sim.reference.make_world` (shared parameters drawn
    once for the world, jittered per site), vectorized, so it is not the same
    random stream: use `make_world` to reproduce a reference world exactly.
    """
    rng = np.random.default_rng(seed)
    proc = np.array([PROCESSES.index(p) for p in processes], dtype=np.int64)
    shared = {s.name: rng.normal(s.prior_mean, s.prior_std) for s in physics.SHARED}
    theta = np.zeros((len(proc), len(COLS)))
    for k, name in enumerate(PROCESSES):
        idx = np.flatnonzero(proc == k)
        if len(idx):
            theta[idx] = to_cols(name, physics.sample_prior(name, len(idx), rng))
    for s in physics.SHARED:
        j = COLS.index(s.name)
        theta[:, j] = np.clip(shared[s.name] + shared_jitter * s.prior_std * rng.standard_normal(len(proc)), s.lo, s.hi)
    radial = rng.normal(0, radial_std, len(proc))
    return SiteBatch(proc, theta, radial, *_draw_orientation(len(proc), rng, orient_std))


def _mix(x: np.ndarray) -> np.ndarray:
    """splitmix64 finalizer, vectorized; wraps mod 2**64."""
    with np.errstate(over="ignore"):
        x = np.asarray(x, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def _rank(x: np.ndarray) -> np.ndarray:
    """Each element's index among the earlier elements equal to it: [3, 1, 3, 3] -> [0, 0, 1, 2]."""
    order = np.argsort(x, kind="stable")
    ranked = x[order]
    rank = np.empty(len(x), dtype=np.int64)
    rank[order] = np.arange(len(x)) - np.searchsorted(ranked, ranked)
    return rank


def plate_rotation(salt: int, plate_seed: int) -> float:
    """Hidden angle a plate sits at on a site's bed, rad."""
    return float(np.random.default_rng([int(salt), plate_seed & (2**64 - 1)]).uniform(0, 2 * np.pi))


@wp.func
def _draw(key: wp.uint64, counter: int) -> wp.uint64:
    """Draw `counter` of a splitmix64 stream: 64-bit state, so pieces never share one in practice."""
    x = key + wp.uint64(counter + 1) * GOLDEN
    x = (x ^ (x >> wp.uint64(30))) * MIX1
    x = (x ^ (x >> wp.uint64(27))) * MIX2
    return x ^ (x >> wp.uint64(31))


@wp.func
def _unit(x: wp.uint64) -> wp.float64:
    """Uniform in (0, 1]."""
    return wp.float64((x >> wp.uint64(11)) + wp.uint64(1)) * TWO_M53


@wp.kernel
def _print_kernel(
    job: wp.array(dtype=wp.int32),           # [M] print job of each piece
    local: wp.array(dtype=wp.int32),         # [M] piece's index within its job
    d: wp.array(dtype=wp.float64),           # [M] nominal diameter
    kind: wp.array(dtype=wp.int32),          # [M] 0 pin, 1 hole
    u: wp.array(dtype=wp.float64),           # [M] column position in [-1, 1]
    v: wp.array(dtype=wp.float64),           # [M] row position in [-1, 1]
    job_site: wp.array(dtype=wp.int32),      # [B] site of each job
    rot: wp.array(dtype=wp.float64),         # [B] plate rotation of each job
    process: wp.array(dtype=wp.int32),       # [S]
    theta: wp.array2d(dtype=wp.float64),     # [S, len(COLS)]
    radial: wp.array(dtype=wp.float64),      # [S]
    orient_amp: wp.array(dtype=wp.float64),  # [S]
    orient_phase: wp.array(dtype=wp.float64),  # [S]
    fail_d: wp.array2d(dtype=wp.float64),    # [S, kind] 50% failure diameter
    fail_width: wp.array(dtype=wp.float64),  # [S]
    exposure: wp.float64,
    job_key: wp.array(dtype=wp.uint64),      # [B] noise key of each job, from its site's own stream
    sample: wp.int32,                        # 0: truth only, no failure or noise draws
    truth: wp.array(dtype=wp.float64),       # [M] out: noise-free, with unmodeled effects
    measured: wp.array(dtype=wp.float64),    # [M] out: NaN if failed; empty when sample == 0
):
    i = wp.tid()
    j = job[i]
    s = job_site[j]
    di = d[i]
    ui = u[i]
    vi = v[i]
    one = wp.float64(1.0)
    two = wp.float64(2.0)

    # physics.predict_d
    out = wp.float64(0.0)
    if process[s] == 0:
        cure_depth = theta[s, DP] * wp.log(exposure / theta[s, EC])
        bleed = theta[s, K_BLEED] * cure_depth
        scaled = di * (one - theta[s, SHRINK])
        if kind[i] == 1:
            out = scaled - two * bleed
        else:
            out = scaled + two * bleed
    else:
        if kind[i] == 1:
            out = di - two * theta[s, W_OFF] - theta[s, POLY_K] / di
        else:
            out = di + two * theta[s, W_OFF] + theta[s, FLARE]
    out = out + theta[s, SIZE_COEF] / di
    out = out + theta[s, POS_GX] * ui + theta[s, POS_GY] * vi

    # unmodeled effects
    out = out + radial[s] * (ui * ui + vi * vi) / two
    out = out + orient_amp[s] * wp.cos(two * (wp.atan2(vi, ui) + rot[j] - orient_phase[s]))
    truth[i] = out
    if sample == 0:
        return

    # failure, then measurement noise (SimPrinter.print_and_measure); z by Box-Muller
    key = job_key[j]
    n = 3 * local[i]
    r = _unit(_draw(key, n))
    z = wp.sqrt(-two * wp.log(_unit(_draw(key, n + 1)))) * wp.cos(TWO_PI * _unit(_draw(key, n + 2)))
    p_fail = one / (one + wp.exp((di - fail_d[s, kind[i]]) / fail_width[s]))
    if r < p_fail:
        measured[i] = wp.float64(wp.nan)
    else:
        measured[i] = out + theta[s, SIGMA] * z


@dataclass
class PrintBatch:
    """Result of one launch, one entry per piece (host arrays)."""
    job: np.ndarray       # [M] print job index
    truth: np.ndarray     # [M]
    measured: np.ndarray  # [M], NaN where failed

    @property
    def ok(self) -> np.ndarray:
        return ~np.isnan(self.measured)


class WarpSim:
    """S sites resident on one device; prints any batch of plates in one launch.

    Like SimPrinter, each site has its own noise stream: a site's draws depend
    only on its salt, `seed` and how many plates it has printed, never on
    other sites or on how prints are batched. Truth-only calls draw nothing.
    """

    def __init__(self, sites: SiteBatch, seed: int = 0, device: str | None = None):
        wp.init()
        self.sites = sites
        self.device = wp.get_device(device)
        self._key = _mix(np.uint64(int(seed) & (2**64 - 1)))
        self._prints = np.zeros(len(sites), dtype=np.uint64)  # plates printed per site
        put = self._put
        self._process = put(sites.process, wp.int32)
        self._theta = put(sites.theta, wp.float64)
        self._radial = put(sites.radial, wp.float64)
        self._amp = put(sites.orient_amp, wp.float64)
        self._phase = put(sites.orient_phase, wp.float64)
        fail_d, fail_width = sites.failure()
        self._fail_d = put(fail_d, wp.float64)
        self._fail_width = put(fail_width, wp.float64)

    def _put(self, a, dtype) -> wp.array:
        return wp.array(np.ascontiguousarray(a), dtype=dtype, device=self.device)

    def _job_keys(self, job_site: np.ndarray) -> np.ndarray:
        """Next noise key from each job's site stream; a site printing k plates here takes k in turn."""
        count = self._prints[job_site] + _rank(job_site).astype(np.uint64)
        self._prints += np.bincount(job_site, minlength=len(self._prints)).astype(np.uint64)
        return _mix(_mix(self.sites.salt[job_site] ^ self._key) + count)

    def _launch(self, job_site, job, d, is_hole, u, v, rot, sample: bool):
        """Returns (truth, measured); measured is None when sample is False."""
        put, n = self._put, len(d)
        job_site, job = np.asarray(job_site, dtype=np.int64), np.asarray(job, dtype=np.int64)
        if len(job_site) != len(rot):
            raise ValueError(f"job_site has {len(job_site)} jobs, rot has {len(rot)}")
        keys = self._job_keys(job_site) if sample else np.zeros(len(job_site), dtype=np.uint64)
        truth = wp.empty(n, dtype=wp.float64, device=self.device)
        measured = wp.empty(n if sample else 0, dtype=wp.float64, device=self.device)
        wp.launch(_print_kernel, dim=n, device=self.device, inputs=[
            put(job, wp.int32), put(_rank(job), wp.int32), put(d, wp.float64), put(is_hole, wp.int32),
            put(u, wp.float64), put(v, wp.float64), put(job_site, wp.int32), put(rot, wp.float64),
            self._process, self._theta, self._radial, self._amp, self._phase, self._fail_d, self._fail_width,
            wp.float64(physics.RESIN_EXPOSURE),
            put(keys, wp.uint64), int(sample),
        ], outputs=[truth, measured])
        return truth.numpy(), measured.numpy() if sample else None

    def print_arrays(self, job_site: np.ndarray, job: np.ndarray, d: np.ndarray, is_hole: np.ndarray,
                     u: np.ndarray, v: np.ndarray, rot: np.ndarray) -> PrintBatch:
        """job_site and rot are per job [B]; job and the geometry are per piece [M], in any order.

        A job's noise depends only on its site's stream and the order of its own pieces.
        """
        return PrintBatch(np.asarray(job), *self._launch(job_site, job, d, is_hole, u, v, rot, sample=True))

    def _plates_args(self, site: list[int], plates: list[Plate]) -> tuple:
        xs = [PieceArrays.from_pieces(p.pieces) for p in plates]
        lens = [len(x.d) for x in xs]
        cat = lambda f: np.concatenate([f(x) for x in xs]) if xs else np.empty(0)
        rot = [plate_rotation(self.sites.salt[s], p.seed) for s, p in zip(site, plates)]
        return (np.asarray(site, dtype=np.int64), np.repeat(np.arange(len(plates)), lens),
                cat(lambda x: x.d), cat(lambda x: x.is_hole), cat(lambda x: x.u), cat(lambda x: x.v), np.array(rot, float))

    def print_plates(self, site: list[int], plates: list[Plate]) -> PrintBatch:
        """Print plates[b] at site[b], all in one launch."""
        return self.print_arrays(*self._plates_args(site, plates))

    def truth_plates(self, site: list[int], plates: list[Plate]) -> np.ndarray:
        """Noise-free diameters of plates[b] at site[b], flat [M]; draws no noise."""
        return self._launch(*self._plates_args(site, plates), sample=False)[0]


@dataclass
class WarpPrinter:
    """Site `index` of a WarpSim, as a `contracts.Printer`."""
    site: str
    sim: WarpSim = field(repr=False)
    index: int

    @property
    def process(self) -> str:
        return PROCESSES[self.sim.sites.process[self.index]]

    @property
    def theta(self) -> np.ndarray:
        return self.sim.sites.theta_of(self.index)

    def truth(self, plate: Plate) -> np.ndarray:
        """Noise-free diameters including unmodeled effects (for evaluation only)."""
        return self.sim.truth_plates([self.index], [plate])

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        res = self.sim.print_plates([self.index], [plate])
        return [
            Measurement(p.piece_id, plate.plate_id, plate.site, float(y), "ok", "sim") if ok
            else Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "sim")
            for p, y, ok in zip(plate.pieces, res.measured, res.ok)
        ]


def from_reference(printers: dict[str, reference.SimPrinter], seed: int, orient_std: float = ORIENT_STD,
                   device: str | None = None) -> dict[str, WarpPrinter]:
    """Same hidden theta, radial and failure model as the given SimPrinters, plus the orientation effect."""
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])  # never a stream reference.make_world uses
    ps = list(printers.values())
    sites = SiteBatch(
        np.array([PROCESSES.index(p.process) for p in ps]),
        np.concatenate([to_cols(p.process, p.theta[None, :]) for p in ps]) if ps else np.zeros((0, len(COLS))),
        np.array([p.radial for p in ps], float),
        *_draw_orientation(len(ps), rng, orient_std),
        fail_d=np.array([[(p.fail_d or FAIL_D[p.process])[k] for k in KINDS] for p in ps], float).reshape(len(ps), len(KINDS)),
        fail_width=np.array([p.fail_width for p in ps], float),
    )
    sim = WarpSim(sites, seed=int(rng.integers(2**63)), device=device)
    return {name: WarpPrinter(name, sim, i) for i, name in enumerate(printers)}


def make_world(sites: dict[str, str], seed: int, shared_jitter: float = 0.2, radial_std: float = 0.02,
               orient_std: float = ORIENT_STD, device: str | None = None) -> dict[str, WarpPrinter]:
    """Drop-in for `sim.reference.make_world`: identical theta and radial for the same seed."""
    world = reference.make_world(sites, seed, shared_jitter, radial_std)
    return from_reference(world, seed=seed, orient_std=orient_std, device=device)


def bench(n_sites: int = 4096, n_ref: int = 64, seed: int = 0) -> None:
    """Sites printed per second, Warp batch vs. SimPrinter, one 64-piece plate each."""
    import time

    from plates.seed import seed_plate

    plate = seed_plate("resin")
    procs = [PROCESSES[i % 2] for i in range(n_sites)]

    ref = reference.make_world({f"s{i}": procs[i] for i in range(n_ref)}, seed)
    t = time.perf_counter()
    for p in ref.values():
        p.print_and_measure(plate)
    ref_rate = n_ref / (time.perf_counter() - t)

    sim = WarpSim(draw_sites(procs, seed), seed=seed)
    x = PieceArrays.from_pieces(plate.pieces)
    m = len(x.d)
    args = (np.arange(n_sites), np.repeat(np.arange(n_sites), m), np.tile(x.d, n_sites),
            np.tile(x.is_hole, n_sites), np.tile(x.u, n_sites), np.tile(x.v, n_sites),
            np.random.default_rng(seed).uniform(0, 2 * np.pi, n_sites))
    sim.print_arrays(*args)  # compile and warm up
    t = time.perf_counter()
    reps = 10
    for _ in range(reps):
        sim.print_arrays(*args)
    warp_rate = reps * n_sites / (time.perf_counter() - t)
    print(f"{m} pieces/plate on {sim.device}: reference {ref_rate:,.0f} sites/s, "
          f"warp {warp_rate:,.0f} sites/s ({n_sites} sites/launch), {warp_rate / ref_rate:,.0f}x")


if __name__ == "__main__":
    bench()
