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

    def __len__(self) -> int:
        return len(self.process)

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


def plate_rotation(salt: int, plate_seed: int) -> float:
    """Hidden angle a plate sits at on a site's bed, rad."""
    return float(np.random.default_rng([int(salt), plate_seed & (2**64 - 1)]).uniform(0, 2 * np.pi))


@wp.kernel
def _print_kernel(
    site: wp.array(dtype=wp.int32),          # [M] site of each piece
    job: wp.array(dtype=wp.int32),           # [M] print job of each piece
    d: wp.array(dtype=wp.float64),           # [M] nominal diameter
    kind: wp.array(dtype=wp.int32),          # [M] 0 pin, 1 hole
    u: wp.array(dtype=wp.float64),           # [M] column position in [-1, 1]
    v: wp.array(dtype=wp.float64),           # [M] row position in [-1, 1]
    rot: wp.array(dtype=wp.float64),         # [B] plate rotation of each job
    process: wp.array(dtype=wp.int32),       # [S]
    theta: wp.array2d(dtype=wp.float64),     # [S, len(COLS)]
    radial: wp.array(dtype=wp.float64),      # [S]
    orient_amp: wp.array(dtype=wp.float64),  # [S]
    orient_phase: wp.array(dtype=wp.float64),  # [S]
    fail_d: wp.array2d(dtype=wp.float64),    # [process, kind] 50% failure diameter
    exposure: wp.float64,
    fail_width: wp.float64,
    seed: wp.int32,
    truth: wp.array(dtype=wp.float64),       # [M] out: noise-free, with unmodeled effects
    measured: wp.array(dtype=wp.float64),    # [M] out: NaN if failed
):
    i = wp.tid()
    s = site[i]
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
    out = out + orient_amp[s] * wp.cos(two * (wp.atan2(vi, ui) + rot[job[i]] - orient_phase[s]))
    truth[i] = out

    # failure, then measurement noise (SimPrinter.print_and_measure)
    state = wp.rand_init(seed, i)
    r = wp.float64(wp.randf(state))
    z = wp.float64(wp.randn(state))
    p_fail = one / (one + wp.exp((di - fail_d[process[s], kind[i]]) / fail_width))
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
    """S sites resident on one device; prints any batch of plates in one launch."""

    def __init__(self, sites: SiteBatch, seed: int = 0, device: str | None = None):
        wp.init()
        self.sites = sites
        self.device = wp.get_device(device)
        self.rng = np.random.default_rng(seed)  # launch seeds only
        put = self._put
        self._process = put(sites.process, wp.int32)
        self._theta = put(sites.theta, wp.float64)
        self._radial = put(sites.radial, wp.float64)
        self._amp = put(sites.orient_amp, wp.float64)
        self._phase = put(sites.orient_phase, wp.float64)
        self._fail_d = put([[FAIL_D[p][k] for k in KINDS] for p in PROCESSES], wp.float64)

    def _put(self, a, dtype) -> wp.array:
        return wp.array(np.ascontiguousarray(a), dtype=dtype, device=self.device)

    def print_arrays(self, site: np.ndarray, job: np.ndarray, d: np.ndarray, is_hole: np.ndarray,
                     u: np.ndarray, v: np.ndarray, rot: np.ndarray) -> PrintBatch:
        """Flat per-piece arrays [M] (site index, job index, geometry); rot is [B] per job."""
        put, n = self._put, len(d)
        truth = wp.empty(n, dtype=wp.float64, device=self.device)
        measured = wp.empty(n, dtype=wp.float64, device=self.device)
        wp.launch(_print_kernel, dim=n, device=self.device, inputs=[
            put(site, wp.int32), put(job, wp.int32), put(d, wp.float64), put(is_hole, wp.int32),
            put(u, wp.float64), put(v, wp.float64), put(rot, wp.float64),
            self._process, self._theta, self._radial, self._amp, self._phase, self._fail_d,
            wp.float64(physics.RESIN_EXPOSURE), wp.float64(FAIL_WIDTH), int(self.rng.integers(2**31)),
        ], outputs=[truth, measured])
        return PrintBatch(np.asarray(job), truth.numpy(), measured.numpy())

    def print_plates(self, site: list[int], plates: list[Plate]) -> PrintBatch:
        """Print plates[b] at site[b], all in one launch."""
        xs = [PieceArrays.from_pieces(p.pieces) for p in plates]
        lens = [len(x.d) for x in xs]
        cat = lambda f: np.concatenate([f(x) for x in xs]) if xs else np.empty(0)
        rot = [plate_rotation(self.sites.salt[s], p.seed) for s, p in zip(site, plates)]
        return self.print_arrays(np.repeat(site, lens), np.repeat(np.arange(len(plates)), lens),
                                 cat(lambda x: x.d), cat(lambda x: x.is_hole), cat(lambda x: x.u), cat(lambda x: x.v),
                                 np.array(rot, float))


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
        return self.sim.print_plates([self.index], [plate]).truth

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        res = self.sim.print_plates([self.index], [plate])
        return [
            Measurement(p.piece_id, plate.plate_id, plate.site, float(y), "ok", "sim") if ok
            else Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "sim")
            for p, y, ok in zip(plate.pieces, res.measured, res.ok)
        ]


def from_reference(printers: dict[str, reference.SimPrinter], seed: int, orient_std: float = ORIENT_STD,
                   device: str | None = None) -> dict[str, WarpPrinter]:
    """Same hidden theta and radial as the given SimPrinters, plus the orientation effect."""
    rng = np.random.default_rng(seed)
    ps = list(printers.values())
    sites = SiteBatch(
        np.array([PROCESSES.index(p.process) for p in ps]),
        np.concatenate([to_cols(p.process, p.theta[None, :]) for p in ps]) if ps else np.zeros((0, len(COLS))),
        np.array([p.radial for p in ps], float),
        *_draw_orientation(len(ps), rng, orient_std),
    )
    sim = WarpSim(sites, seed=int(rng.integers(2**63)), device=device)
    return {name: WarpPrinter(name, sim, i) for i, name in enumerate(printers)}


def make_world(sites: dict[str, str], seed: int, shared_jitter: float = 0.2, radial_std: float = 0.02,
               orient_std: float = ORIENT_STD, device: str | None = None) -> dict[str, WarpPrinter]:
    """Drop-in for `sim.reference.make_world`: identical theta and radial for the same seed."""
    world = reference.make_world(sites, seed, shared_jitter, radial_std)
    return from_reference(world, seed=seed + 1, orient_std=orient_std, device=device)


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
    args = (np.repeat(np.arange(n_sites), m), np.repeat(np.arange(n_sites), m), np.tile(x.d, n_sites),
            np.tile(x.is_hole, n_sites), np.tile(x.u, n_sites), np.tile(x.v, n_sites),
            sim.rng.uniform(0, 2 * np.pi, n_sites))
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
