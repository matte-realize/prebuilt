"""GPU (NVIDIA Warp) port of `model.posterior.ParticlePosterior`.

Same algorithm as the NumPy reference: resample-move SMC with adaptive
tempering, systematic resampling and random-walk Metropolis moves. Every
particle-sized step runs in Warp kernels, in float64.

The core is `PosteriorBatch`: B independent posteriors (sites x seeds), each
with N particles, stored as [B, N, P] arrays, so one launch advances every
member. Members may differ in process and site layout; P is padded to the
widest member and kernels stop at each member's own parameter count.
`ParticlePosterior` is a view of one member with the reference API, so agents
and arms can take either implementation.

Layout, prior draws and measurement grouping come from the NumPy reference, so
for the same seed both start from identical particles. The kernel physics
mirrors `model/physics.py`; tests/test_posterior_warp.py checks the two
against each other, so change them together.

Raw measurements stay inside this object. Only `summary()` output, which
covers the shared-tagged parameters, may be put in a `Message`.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
import warp as wp

from contracts import Measurement, Piece
from model import physics
from model import posterior as reference
from model.physics import PieceArrays

wp.config.quiet = True

F = wp.float64
A1F, A2F, A3F, A4F = (wp.array(dtype=F, ndim=k) for k in (1, 2, 3, 4))
A1I, A2I = wp.array(dtype=wp.int32), wp.array2d(dtype=wp.int32)

NEG_INF = wp.constant(F(-math.inf))
HALF_LOG2PI = wp.constant(F(0.5 * math.log(2 * math.pi)))
RESIN_E = wp.constant(F(physics.RESIN_EXPOSURE))
GRID_N = 16  # candidate tempering steps per search round
GRID = wp.constant(GRID_N)
GRID_F = wp.constant(F(GRID_N))
SEARCH_ROUNDS = 8       # 16^8 > 2^30: at least as fine as the reference's 30 bisection halvings
NCOL = max(len(v) for v in physics.PARAMS.values())
PROC_ID = {"resin": 0, "pla": 1}

_r, _p = physics.index("resin"), physics.index("pla")
R_DP, R_EC, R_KB, R_SH, R_SIG = (wp.constant(_r[k]) for k in ("Dp", "Ec", "k_bleed", "shrink", "sigma_meas"))
R_SC, R_GX, R_GY = (wp.constant(_r[k]) for k in ("size_coef", "pos_gx", "pos_gy"))
P_W, P_PK, P_FL, P_SIG = (wp.constant(_p[k]) for k in ("w_off", "poly_k", "flare", "sigma_meas"))
P_SC, P_GX, P_GY = (wp.constant(_p[k]) for k in ("size_coef", "pos_gx", "pos_gy"))


@wp.struct
class Obs:
    """Flat observations (or prediction queries). cols maps PARAMS[proc] order to theta columns."""
    proc: A1I
    cols: A2I
    d: A1F
    hole: A1I
    u: A1F
    v: A1F
    y: A1F


@wp.struct
class Target:
    """Everything the tempered log target needs, per member."""
    npar: A1I
    mean: A2F
    std: A2F
    lo: A2F
    hi: A2F
    has_quad: A1I
    qa: A3F       # -0.5 x'Ax + b'x: hierarchical couplings + extra priors
    qb: A2F
    seen_lo: A1I
    seen_hi: A1I
    new_lo: A1I
    new_hi: A1I
    phi: A1F      # tempering progress through the new batch


# ---- physics (mirrors model/physics.py) ---------------------------------

@wp.func
def _th(x: A3F, b: int, n: int, cols: A2I, o: int, k: int) -> F:
    return x[b, n, cols[o, k]]


@wp.func
def _mu(x: A3F, b: int, n: int, ob: Obs, o: int) -> F:
    d = ob.d[o]
    out = F(0.0)
    sc = F(0.0)
    gx = F(0.0)
    gy = F(0.0)
    if ob.proc[o] == 0:
        cure = _th(x, b, n, ob.cols, o, R_DP) * wp.log(RESIN_E / _th(x, b, n, ob.cols, o, R_EC))
        bleed = _th(x, b, n, ob.cols, o, R_KB) * cure
        scaled = d * (F(1.0) - _th(x, b, n, ob.cols, o, R_SH))
        out = scaled + F(2.0) * bleed
        if ob.hole[o] != 0:
            out = scaled - F(2.0) * bleed
        sc = _th(x, b, n, ob.cols, o, R_SC)
        gx = _th(x, b, n, ob.cols, o, R_GX)
        gy = _th(x, b, n, ob.cols, o, R_GY)
    else:
        w = _th(x, b, n, ob.cols, o, P_W)
        out = d + F(2.0) * w + _th(x, b, n, ob.cols, o, P_FL)
        if ob.hole[o] != 0:
            out = d - F(2.0) * w - _th(x, b, n, ob.cols, o, P_PK) / d
        sc = _th(x, b, n, ob.cols, o, P_SC)
        gx = _th(x, b, n, ob.cols, o, P_GX)
        gy = _th(x, b, n, ob.cols, o, P_GY)
    return out + sc / d + gx * ob.u[o] + gy * ob.v[o]


@wp.func
def _sigma(x: A3F, b: int, n: int, ob: Obs, o: int) -> F:
    if ob.proc[o] == 0:
        return _th(x, b, n, ob.cols, o, R_SIG)
    return _th(x, b, n, ob.cols, o, P_SIG)


@wp.func
def _loglik(x: A3F, b: int, n: int, ob: Obs, lo: int, hi: int) -> F:
    s = F(0.0)
    for o in range(lo, hi):
        sd = _sigma(x, b, n, ob, o)
        z = (ob.y[o] - _mu(x, b, n, ob, o)) / sd
        s += F(-0.5) * z * z - wp.log(sd) - HALF_LOG2PI
    return s


@wp.func
def _log_target(x: A3F, b: int, n: int, t: Target, ob: Obs) -> F:
    """Prior x couplings x extra priors x past data x new batch^phi; -inf outside bounds."""
    p = t.npar[b]
    lp = F(0.0)
    inside = int(1)
    for j in range(p):
        v = x[b, n, j]
        if v < t.lo[b, j] or v > t.hi[b, j]:
            inside = 0
        z = (v - t.mean[b, j]) / t.std[b, j]
        lp += F(-0.5) * z * z
    if inside == 0:
        return NEG_INF
    if t.has_quad[b] != 0:
        for j in range(p):
            r = t.qb[b, j]
            for k in range(p):
                r -= F(0.5) * t.qa[b, j, k] * x[b, n, k]
            lp += r * x[b, n, j]
    lp += _loglik(x, b, n, ob, t.seen_lo[b], t.seen_hi[b])
    ph = t.phi[b]
    if ph > F(0.0):
        lp += ph * _loglik(x, b, n, ob, t.new_lo[b], t.new_hi[b])
    return lp


# ---- kernels: likelihood and tempering ------------------------------------

@wp.kernel
def k_loglik(theta: A3F, ob: Obs, t: Target, active: A1I, ll: A2F):
    b, n = wp.tid()
    if active[b] != 0:
        ll[b, n] = _loglik(theta, b, n, ob, t.new_lo[b], t.new_hi[b])


@wp.kernel
def k_lse_partial(base: A2F, extra: A2F, coef: A1F, rowb: A1I, mask: A1I, n: int, pm: A2F, p1: A2F, p2: A2F, chunk: int):
    """Per chunk of base[rowb[r]] + coef[r] * extra[r]: max, sum exp(a - max), sum exp(2(a - max))."""
    r, c = wp.tid()
    b = rowb[r]
    if mask[b] == 0:
        return
    i0 = c * chunk
    i1 = wp.min(i0 + chunk, n)
    cf = coef[r]
    m = NEG_INF
    for i in range(i0, i1):
        a = base[b, i]
        if cf != F(0.0):
            a += cf * extra[r, i]
        m = wp.max(m, a)
    s1 = F(0.0)
    s2 = F(0.0)
    if m > NEG_INF:
        for i in range(i0, i1):
            a = base[b, i]
            if cf != F(0.0):
                a += cf * extra[r, i]
            e = wp.exp(a - m)
            s1 += e
            s2 += e * e
    pm[r, c] = m
    p1[r, c] = s1
    p2[r, c] = s2


@wp.kernel
def k_lse_final(pm: A2F, p1: A2F, p2: A2F, nc: int, rowb: A1I, mask: A1I, lse: A1F, ess: A1F):
    """Combine chunks: log-sum-exp and ESS = (sum w)^2 / sum w^2."""
    r = wp.tid()
    if mask[rowb[r]] == 0:
        return
    m = NEG_INF
    for c in range(nc):
        m = wp.max(m, pm[r, c])
    if m == NEG_INF:
        lse[r] = NEG_INF
        ess[r] = F(0.0)
        return
    s1 = F(0.0)
    s2 = F(0.0)
    for c in range(nc):
        e = wp.exp(pm[r, c] - m)
        s1 += p1[r, c] * e
        s2 += p2[r, c] * e * e
    lse[r] = m + wp.log(s1)
    ess[r] = s1 * s1 / s2


@wp.kernel
def k_search_init(t: Target, active: A1I, lo: A1F, hi: A1F, full: A1I):
    b = wp.tid()
    if active[b] != 0:
        lo[b] = F(0.0)
        hi[b] = F(1.0) - t.phi[b]
        full[b] = 0


@wp.kernel
def k_grid_partial(logw: A2F, ll: A2F, lo: A1F, hi: A1F, active: A1I, n: int, pm: A3F, p1: A3F, p2: A3F, chunk: int):
    """Chunk sums for the ESS of logw + t_k * ll at GRID evenly spaced steps t_k in (lo, hi]."""
    b, k, c = wp.tid()
    if active[b] == 0:
        return
    tk = lo[b] + (hi[b] - lo[b]) * F(k + 1) / GRID_F
    i0 = c * chunk
    i1 = wp.min(i0 + chunk, n)
    m = NEG_INF
    for i in range(i0, i1):
        m = wp.max(m, logw[b, i] + tk * ll[b, i])
    s1 = F(0.0)
    s2 = F(0.0)
    for i in range(i0, i1):
        e = F(wp.exp(wp.float32(logw[b, i] + tk * ll[b, i] - m)))  # float32 is plenty for an ESS threshold
        s1 += e
        s2 += e * e
    pm[b, k, c] = m
    p1[b, k, c] = s1
    p2[b, k, c] = s2


@wp.kernel
def k_grid_ess(pm: A3F, p1: A3F, p2: A3F, nc: int, active: A1I, ess: A2F):
    b, k = wp.tid()
    if active[b] == 0:
        return
    m = NEG_INF
    for c in range(nc):
        m = wp.max(m, pm[b, k, c])
    s1 = F(0.0)
    s2 = F(0.0)
    for c in range(nc):
        e = wp.exp(pm[b, k, c] - m)
        s1 += p1[b, k, c] * e
        s2 += p2[b, k, c] * e * e
    ess[b, k] = s1 * s1 / s2


@wp.kernel
def k_grid_pick(ess: A2F, target: F, active: A1I, first: int, lo: A1F, hi: A1F, full: A1I):
    """Narrow (lo, hi] to the gap after the largest grid step that keeps ESS >= target."""
    b = wp.tid()
    if active[b] == 0:
        return
    best = int(-1)
    for k in range(GRID):
        if ess[b, k] >= target:
            best = k
    if first != 0 and best == GRID - 1:
        full[b] = 1  # the whole remaining step is fine
    width = (hi[b] - lo[b]) / GRID_F
    l = lo[b]
    if best < GRID - 1:
        hi[b] = l + width * F(best + 2)
    lo[b] = l + width * F(best + 1)


@wp.kernel
def k_take_step(t: Target, full: A1I, lo: A1F, active: A1I, step: A1F):
    b = wp.tid()
    if active[b] == 0:
        step[b] = F(0.0)
        return
    rem = F(1.0) - t.phi[b]
    s = wp.max(lo[b], F(1e-6))
    if full[b] != 0:
        s = rem
    step[b] = s
    t.phi[b] = wp.min(F(1.0), t.phi[b] + s)


@wp.kernel
def k_add_scaled(logw: A2F, ll: A2F, step: A1F, active: A1I):
    b, n = wp.tid()
    if active[b] != 0:
        logw[b, n] = logw[b, n] + step[b] * ll[b, n]


@wp.kernel
def k_subtract(logw: A2F, lse: A1F, mask: A1I):
    b, n = wp.tid()
    if mask[b] != 0:
        logw[b, n] = logw[b, n] - lse[b]


@wp.kernel
def k_flag_low_ess(ess: A1F, target: F, mask: A1I, out: A1I):
    b = wp.tid()
    out[b] = 0
    if mask[b] != 0 and ess[b] < target:
        out[b] = 1


# ---- kernels: resampling ----------------------------------------------------

@wp.kernel
def k_scan_chunk(logw: A2F, mask: A1I, n: int, cum: A2F, part: A2F, chunk: int):
    b, c = wp.tid()
    if mask[b] == 0:
        return
    acc = F(0.0)
    for i in range(c * chunk, wp.min(c * chunk + chunk, n)):
        acc += wp.exp(logw[b, i])
        cum[b, i] = acc
    part[b, c] = acc


@wp.kernel
def k_scan_parts(part: A2F, nc: int, mask: A1I):
    b = wp.tid()
    if mask[b] == 0:
        return
    acc = F(0.0)
    for c in range(nc):
        s = part[b, c]
        part[b, c] = acc
        acc += s


@wp.kernel
def k_scan_add(cum: A2F, part: A2F, mask: A1I, chunk: int):
    b, i = wp.tid()
    if mask[b] != 0:
        cum[b, i] = cum[b, i] + part[b, i // chunk]


@wp.func
def _search(cum: A2F, b: int, n: int, pos: F) -> int:
    """First i with cum[b, i] >= pos (np.searchsorted, side='left'), capped at n - 1."""
    lo = int(0)
    hi = n
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[b, mid] < pos:
            lo = mid + 1
        else:
            hi = mid
    return wp.min(lo, n - 1)


@wp.func
def _rng(seed: A1I, ncall: A1I, sub: int, b: int, offset: int) -> wp.uint32:
    """Per-member stream: depends only on the member's seed and its own call count (+ sub < 16)."""
    st = wp.rand_init(seed[b], ncall[b] * 16 + sub)
    return wp.rand_init(wp.randi(st), offset)


@wp.kernel
def k_bump(mask: A1I, ncall: A1I):
    b = wp.tid()
    if mask[b] != 0:
        ncall[b] = ncall[b] + 1  # after a resample-move: its draws used subs 0..mh_steps


@wp.kernel
def k_systematic(theta: A3F, cum: A2F, logw: A2F, mask: A1I, seed: A1I, ncall: A1I, n: int, p: int, out: A3F):
    """Systematic resampling of masked members; others are copied through."""
    b, i = wp.tid()
    src = i
    if mask[b] != 0:
        st = _rng(seed, ncall, 0, b, 0)  # one offset: the same draw for every thread of a member
        pos = (F(wp.randf(st)) + F(i)) / F(n)
        src = _search(cum, b, n, pos)
        logw[b, i] = -wp.log(F(n))
    for j in range(p):
        out[b, i, j] = theta[b, src, j]


# ---- kernels: moments and moves ---------------------------------------------

@wp.kernel
def k_mean_partial(theta: A3F, logw: A2F, npar: A1I, mask: A1I, n: int, part: A3F, chunk: int):
    b, c, j = wp.tid()
    if mask[b] == 0 or j >= npar[b]:
        return
    s = F(0.0)
    for i in range(c * chunk, wp.min(c * chunk + chunk, n)):
        s += wp.exp(logw[b, i]) * theta[b, i, j]
    part[b, c, j] = s


@wp.kernel
def k_mean_final(part: A3F, nc: int, npar: A1I, mask: A1I, mean: A2F):
    b, j = wp.tid()
    if mask[b] == 0 or j >= npar[b]:
        return
    s = F(0.0)
    for c in range(nc):
        s += part[b, c, j]
    mean[b, j] = s


@wp.kernel
def k_cov_partial(theta: A3F, logw: A2F, mean: A2F, npar: A1I, mask: A1I, n: int, part: A4F, chunk: int):
    b, c, jk = wp.tid()
    p = npar[b]
    j = jk // p
    k = jk - j * p
    if mask[b] == 0 or j >= p or k < j:
        return
    s = F(0.0)
    for i in range(c * chunk, wp.min(c * chunk + chunk, n)):
        s += wp.exp(logw[b, i]) * (theta[b, i, j] - mean[b, j]) * (theta[b, i, k] - mean[b, k])
    part[b, c, j, k] = s
    part[b, c, k, j] = s


@wp.kernel
def k_cov_final(part: A4F, nc: int, npar: A1I, mask: A1I, cov: A3F):
    """Weighted covariance (ddof 0)."""
    b, j, k = wp.tid()
    if mask[b] == 0 or j >= npar[b] or k >= npar[b]:
        return
    s = F(0.0)
    for c in range(nc):
        s += part[b, c, j, k]
    cov[b, j, k] = s


@wp.kernel
def k_proposal_chol(cov: A3F, npar: A1I, mask: A1I, n: int, chol: A3F):
    """chol = cholesky((2.38^2 / p) * (np.cov + 1e-12 I)); weights are uniform after a resample."""
    b = wp.tid()
    if mask[b] == 0:
        return
    p = npar[b]
    ddof = F(n) / F(n - 1)
    scale = F(2.38 * 2.38) / F(p)
    for j in range(p):
        s = scale * (cov[b, j, j] * ddof + F(1e-12))
        for k in range(j):
            s -= chol[b, j, k] * chol[b, j, k]
        ljj = wp.sqrt(wp.max(s, F(0.0)))
        chol[b, j, j] = ljj
        for i in range(j + 1, p):
            s2 = scale * cov[b, i, j] * ddof
            for k in range(j):
                s2 -= chol[b, i, k] * chol[b, j, k]
            chol[b, i, j] = F(0.0)
            if ljj > F(0.0):
                chol[b, i, j] = s2 / ljj


@wp.kernel
def k_log_target(theta: A3F, t: Target, ob: Obs, mask: A1I, lt: A2F):
    b, n = wp.tid()
    if mask[b] != 0:
        lt[b, n] = _log_target(theta, b, n, t, ob)


@wp.kernel
def k_mh(theta: A3F, prop: A3F, lt: A2F, chol: A3F, t: Target, ob: Obs, mask: A1I, seed: A1I, ncall: A1I, sub: int):
    """One random-walk Metropolis step: prop = theta + L z, accept with min(1, ratio)."""
    b, n = wp.tid()
    if mask[b] == 0:
        return
    st = _rng(seed, ncall, sub, b, n)
    p = t.npar[b]
    for j in range(p):
        prop[b, n, j] = theta[b, n, j]
    for k in range(p):
        z = F(wp.randn(st))
        for j in range(k, p):
            prop[b, n, j] = prop[b, n, j] + chol[b, j, k] * z
    lt_prop = _log_target(prop, b, n, t, ob)
    if wp.log(F(wp.randf(st))) < lt_prop - lt[b, n]:
        for j in range(p):
            theta[b, n, j] = prop[b, n, j]
        lt[b, n] = lt_prop


@wp.kernel
def k_add_gauss(theta: A3F, logw: A2F, b: int, cols: A1I, mu: A1F, prec: A2F, coef: F):
    """logw[b] += coef * (-0.5 d' prec d), d = theta[b, :, cols] - mu."""
    n = wp.tid()
    m = cols.shape[0]
    q = F(0.0)
    for i in range(m):
        di = theta[b, n, cols[i]] - mu[i]
        for j in range(m):
            q += di * prec[i, j] * (theta[b, n, cols[j]] - mu[j])
    logw[b, n] = logw[b, n] + coef * F(-0.5) * q


# ---- kernels: prediction ----------------------------------------------------

@wp.kernel
def k_predict(theta: A3F, q: Obs, qb: A1I, mu: A2F, s: A2F):
    r, n = wp.tid()
    b = qb[r]
    mu[r, n] = _mu(theta, b, n, q, r)
    s[r, n] = _sigma(theta, b, n, q, r)


@wp.kernel
def k_moments_partial(theta: A3F, q: Obs, qb: A1I, logw: A2F, n: int, part: A3F, chunk: int):
    """Per chunk: sum w d, sum w d^2, sum w s^2 with d = mu - mu(particle 0), a shift for stable variance."""
    r, c = wp.tid()
    b = qb[r]
    shift = _mu(theta, b, 0, q, r)
    s0 = F(0.0)
    s1 = F(0.0)
    s2 = F(0.0)
    for i in range(c * chunk, wp.min(c * chunk + chunk, n)):
        w = wp.exp(logw[b, i])
        d = _mu(theta, b, i, q, r) - shift
        sd = _sigma(theta, b, i, q, r)
        s0 += w * d
        s1 += w * d * d
        s2 += w * sd * sd
    part[r, c, 0] = s0
    part[r, c, 1] = s1
    part[r, c, 2] = s2


@wp.kernel
def k_moments_final(part: A3F, nc: int, theta: A3F, q: Obs, qb: A1I, out: A2F):
    """Predictive mean and variance (spread of particle means + mean noise variance); weights sum to 1."""
    r = wp.tid()
    s0 = F(0.0)
    s1 = F(0.0)
    s2 = F(0.0)
    for c in range(nc):
        s0 += part[r, c, 0]
        s1 += part[r, c, 1]
        s2 += part[r, c, 2]
    out[0, r] = _mu(theta, qb[r], 0, q, r) + s0
    out[1, r] = s1 - s0 * s0 + s2


@wp.kernel
def k_log_density(mu: A2F, s: A2F, y: A1F, out: A2F):
    r, n = wp.tid()
    z = (y[r] - mu[r, n]) / s[r, n]
    out[r, n] = F(-0.5) * z * z - wp.log(s[r, n]) - HALF_LOG2PI


@wp.kernel
def k_draw(cum: A2F, b: int, n: int, mu: A2F, s: A2F, seed: int, out: A1F):
    """Mixture draws: particle by weight (inverse CDF), then Gaussian noise."""
    i = wp.tid()
    st = wp.rand_init(seed, i)
    j = _search(cum, b, n, F(wp.randf(st)))
    out[i] = mu[0, j] + s[0, j] * F(wp.randn(st))


# ---- host side --------------------------------------------------------------

def _seed32(seed: int | tuple[int, ...]) -> int:
    return int(np.random.SeedSequence(seed).generate_state(1)[0] & 0x7FFFFFFF)


class _Member:
    """Host-side state of one posterior: layout (from the reference), data, extra priors."""

    def __init__(self, sites, pieces, n, seed, ess_frac, mh_steps, between_site_sd):
        ref = reference.ParticlePosterior(sites, pieces, n=n, seed=seed, ess_frac=ess_frac,
                                          mh_steps=mh_steps, between_site_sd=between_site_sd)
        self.theta0 = ref.theta              # initial draws, identical to the reference
        ref.theta = ref.logw = None          # only the layout and grouping helpers are kept
        self.ref = ref
        self.seed = seed
        self.seen = self._records({})
        self.extra: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}

    @property
    def p(self) -> int:
        return len(self.ref.specs)

    def records(self, ms: list[Measurement]) -> dict[str, np.ndarray]:
        return self._records(self.ref._batch(ms))

    def _records(self, batch) -> dict[str, np.ndarray]:
        parts = [_obs_records(self.ref.blocks[site], x, y) for site, (x, y) in batch.items()]
        return _concat(parts) if parts else _obs_records(("resin", np.zeros(0, int)), None, None)

    def quad(self) -> tuple[np.ndarray, np.ndarray]:
        """-0.5 x'Ax + b'x for the couplings plus every extra prior (constants dropped)."""
        a, bv = np.zeros((self.p, self.p)), np.zeros(self.p)
        for g, c, tau in self.ref._couplings:
            e = np.zeros(self.p)
            e[c], e[g] = 1.0, -1.0
            a += np.outer(e, e) / tau**2
        for cols, mu, prec, w in self.extra.values():
            a[np.ix_(cols, cols)] += w * prec
            bv[cols] += w * prec @ mu
        return a, bv


def _obs_records(block, x: PieceArrays | None, y: np.ndarray | None) -> dict[str, np.ndarray]:
    proc, cols = block
    m = 0 if x is None else len(x.d)
    padded = np.zeros(NCOL, np.int32)
    padded[: len(cols)] = cols
    return {
        "proc": np.full(m, PROC_ID[proc], np.int32),
        "cols": np.tile(padded, (m, 1)),
        "d": np.zeros(0) if x is None else x.d.astype(float),
        "hole": np.zeros(0, np.int32) if x is None else x.is_hole.astype(np.int32),
        "u": np.zeros(0) if x is None else x.u.astype(float),
        "v": np.zeros(0) if x is None else x.v.astype(float),
        "y": np.zeros(m) if y is None else np.asarray(y, float),
    }


def _concat(recs: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    return {k: np.concatenate([r[k] for r in recs]) for k in recs[0]}


_PAD = _obs_records(("resin", np.zeros(0, int)), PieceArrays(np.ones(1), np.zeros(1, bool), np.zeros(1), np.zeros(1)), None)


class PosteriorBatch:
    """B independent particle posteriors updated together on the GPU.

    `sites` gives each member's sites (as for the reference class); `pieces` is
    one piece library shared by all members or one per member. All members
    have the same particle count `n`. Index a batch (`batch[i]`) for a
    `ParticlePosterior` view with the reference API.

    Batched entry points: `update(ms_per_member)`, `predict(pieces_per_member)`,
    `ess()`.
    """

    def __init__(
        self,
        sites: Sequence[str | dict[str, str]],
        pieces: dict[str, Piece] | Sequence[dict[str, Piece]],
        seeds: Sequence[int],
        n: int = 4000,
        ess_frac: float = 0.5,
        mh_steps: int = 3,
        between_site_sd: float | None | Sequence[float | None] = None,
        device: str | None = None,
    ):
        b = len(sites)
        if len(seeds) != b:
            raise ValueError("one seed per member")
        if mh_steps >= 16:
            raise ValueError("mh_steps must be < 16 (random sub-streams per resample-move)")
        pieces = list(pieces) if not isinstance(pieces, Mapping) else [pieces] * b
        bsd = list(between_site_sd) if isinstance(between_site_sd, Sequence) else [between_site_sd] * b
        self.device = wp.get_device(device)
        self.n, self.b = n, b
        self.ess_frac, self.mh_steps = ess_frac, mh_steps
        self.members = [_Member(s, pc, n, sd, ess_frac, mh_steps, h) for s, pc, sd, h in zip(sites, pieces, seeds, bsd)]
        self.p = max(m.p for m in self.members)
        self.chunk = max(64, math.isqrt(n))  # particles per thread in reductions; ~sqrt(n) balances both levels
        self.nc = -(-n // self.chunk)          # chunks per member
        self._calls = 0

        theta = np.zeros((b, n, self.p))
        spec = {k: np.ones((b, self.p)) for k in ("mean", "std", "lo", "hi")}
        for i, m in enumerate(self.members):
            theta[i, :, : m.p] = m.theta0
            m.theta0 = None
            for k, attr in (("mean", "prior_mean"), ("std", "prior_std"), ("lo", "lo"), ("hi", "hi")):
                spec[k][i, : m.p] = [getattr(s, attr) for s in m.ref.specs]

        arr = lambda a, dt=F: wp.array(np.ascontiguousarray(a), dtype=dt, device=self.device)
        zeros = lambda shape, dt=F: wp.zeros(shape, dtype=dt, device=self.device)
        self._arr, self._zeros = arr, zeros
        self.theta_d = arr(theta)
        self.tmp_d = zeros((b, n, self.p))
        self.prop_d = zeros((b, n, self.p))
        self.logw_d = arr(np.full((b, n), -np.log(n)))
        self.ll_d = zeros((b, n))
        self.lt_d = zeros((b, n))
        self.cum_d = zeros((b, n))
        self.seed_d = arr([_seed32(m.seed) for m in self.members], wp.int32)
        self.ncall_d = zeros(b, wp.int32)
        self.rowb_d = arr(np.arange(b), wp.int32)
        self.zero_coef_d = zeros(b)
        self.gm_d, self.g1_d, self.g2_d = (zeros((b, GRID, self.nc)) for _ in range(3))
        self.gess_d = zeros((b, GRID))
        self.lse_d, self.ess_d = zeros(b), zeros(b)
        self.lo_d, self.hi_d, self.step_d = zeros(b), zeros(b), zeros(b)
        self.full_d, self.flag_d = zeros(b, wp.int32), zeros(b, wp.int32)
        self.pm_d, self.p1_d, self.p2_d = zeros((b, self.nc)), zeros((b, self.nc)), zeros((b, self.nc))
        self.part_d = zeros((b, self.nc))
        self.mpart_d = zeros((b, self.nc, self.p))
        self.cpart_d = zeros((b, self.nc, self.p, self.p))
        self.mean_d = zeros((b, self.p))
        self.cov_d = zeros((b, self.p, self.p))
        self.chol_d = zeros((b, self.p, self.p))

        t = Target()
        t.npar = arr([m.p for m in self.members], wp.int32)
        t.mean, t.std, t.lo, t.hi = (arr(spec[k]) for k in ("mean", "std", "lo", "hi"))
        t.phi = zeros(b)
        self.t = t
        self._upload_quad()
        self._upload_obs([None] * b)

    def __len__(self) -> int:
        return self.b

    def __getitem__(self, i: int) -> ParticlePosterior:
        return ParticlePosterior._view(self, i)

    # ---- batched entry points ----------------------------------------

    def update(self, ms_per_member: Sequence[list[Measurement]] | Mapping[int, list[Measurement]]) -> None:
        """Fold each member's new measurements in; all members advance in the same launches."""
        items = ms_per_member.items() if isinstance(ms_per_member, Mapping) else enumerate(ms_per_member)
        new: list[dict[str, np.ndarray] | None] = [None] * self.b
        for i, ms in items:
            ok = [m for m in ms if m.status == "ok" and m.measured_d is not None]
            if ok:  # failures are printability outcomes, scored elsewhere
                new[i] = self.members[i].records(ok)
        active = np.array([r is not None for r in new], np.int32)
        if not active.any():
            return
        self._upload_obs(new)
        self.t.phi.zero_()
        active_d = self._arr(active, wp.int32)
        target = self.ess_frac * self.n
        while True:
            self._launch(k_loglik, (self.b, self.n), [self.theta_d, self.ob, self.t, active_d, self.ll_d])
            self._next_step(active_d, target)
            self._launch(k_take_step, self.b, [self.t, self.full_d, self.lo_d, active_d, self.step_d])
            self._launch(k_add_scaled, (self.b, self.n), [self.logw_d, self.ll_d, self.step_d, active_d])
            self._normalize(active_d)
            self._launch(k_flag_low_ess, self.b, [self.ess_d, target, active_d, self.flag_d])
            self._resample_move(self.flag_d)
            active = active & (self.t.phi.numpy() < 1.0)
            if not active.any():
                break
            active_d = self._arr(active, wp.int32)
        for i, r in enumerate(new):
            if r is not None:
                self.members[i].seen = _concat([self.members[i].seen, r])
        self._upload_obs([None] * self.b)

    def predict(self, pieces_per_member: Sequence[list[Piece]], sites: Sequence[str | None] | None = None):
        """Predictive mean and std per piece, for every member at once: lists of [M_i] arrays."""
        sites = sites or [None] * self.b
        recs, rowb = [], []
        for i, (pcs, site) in enumerate(zip(pieces_per_member, sites)):
            if pcs:
                recs.append(self._query(i, pcs, site))
                rowb += [i] * len(pcs)
        if not recs:
            return [np.zeros(0)] * self.b, [np.zeros(0)] * self.b
        mean, var = self._moments(_concat(recs), np.array(rowb))
        mean_out, std_out, k = [], [], 0
        for pcs in pieces_per_member:
            m = len(pcs)
            mean_out.append(mean[k : k + m])
            std_out.append(np.sqrt(var[k : k + m]))
            k += m
        return mean_out, std_out

    def ess(self) -> np.ndarray:
        """Effective sample size per member, [B]."""
        mask = self._arr(np.ones(self.b), wp.int32)
        self._lse_rows(self.logw_d, self.ll_d, self.zero_coef_d, self.rowb_d, mask)
        return self.ess_d.numpy().copy()

    # ---- per-member operations used by the view ----------------------------

    def _mask(self, i: int):
        m = np.zeros(self.b, np.int32)
        m[i] = 1
        return self._arr(m, wp.int32)

    def _query(self, i: int, pieces, site: str | None) -> dict[str, np.ndarray]:
        ref = self.members[i].ref
        site = site or ref._only_site()
        x = pieces if isinstance(pieces, PieceArrays) else PieceArrays.from_pieces(pieces)
        return _obs_records(ref.blocks[site], x, None)

    def _components(self, rec: dict[str, np.ndarray], rowb: np.ndarray):
        q = len(rowb)
        mu, s = self._zeros((q, self.n)), self._zeros((q, self.n))
        self._launch(k_predict, (q, self.n), [self.theta_d, self._obs_struct(rec), self._arr(rowb, wp.int32), mu, s])
        return mu, s

    def _moments(self, rec, rowb: np.ndarray):
        """Predictive mean and variance per query row, without materializing [rows, N]."""
        out = np.empty((2, len(rowb)))
        block = max(1, (1 << 23) // (3 * self.nc))  # rows per pass: partial sums stay under 64 MB
        for k in range(0, len(rowb), block):
            sl = slice(k, k + block)
            q, qb = self._obs_struct({key: v[sl] for key, v in rec.items()}), self._arr(rowb[sl], wp.int32)
            rows = len(rowb[sl])
            part, res = self._zeros((rows, self.nc, 3)), self._zeros((2, rows))
            self._launch(k_moments_partial, (rows, self.nc), [self.theta_d, q, qb, self.logw_d, self.n, part, self.chunk])
            self._launch(k_moments_final, rows, [part, self.nc, self.theta_d, q, qb, res])
            out[:, sl] = res.numpy()
        return out[0], out[1]

    def _log_predictive(self, i: int, rec, y: np.ndarray) -> np.ndarray:
        rowb = np.full(len(y), i)
        mu, s = self._components(rec, rowb)
        lp = self._zeros(mu.shape)
        self._launch(k_log_density, mu.shape, [mu, s, self._arr(y), lp])
        q = len(y)
        pm, p1, p2 = self._zeros((q, self.nc)), self._zeros((q, self.nc)), self._zeros((q, self.nc))
        lse, ess = self._zeros(q), self._zeros(q)
        rowb_d, ones = self._arr(rowb, wp.int32), self._arr(np.ones(self.b), wp.int32)
        self._launch(k_lse_partial, (q, self.nc), [self.logw_d, lp, self._arr(np.ones(q)), rowb_d, ones, self.n, pm, p1, p2, self.chunk])
        self._launch(k_lse_final, q, [pm, p1, p2, self.nc, rowb_d, ones, lse, ess])
        return lse.numpy()

    def _interval_draws(self, i: int, rec, k: int) -> np.ndarray:
        mu, s = self._components(rec, np.array([i]))
        self._cumsum(self._mask(i))
        out = self._zeros(k)
        self._launch(k_draw, k, [self.cum_d, i, self.n, mu, s, _seed32((self.members[i].seed, self._salt())), out])
        return out.numpy()

    def _summary(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        mask = self._mask(i)
        self._weighted_cov(mask)
        p = self.members[i].p
        return self.mean_d.numpy()[i, :p], self.cov_d.numpy()[i, :p, :p]

    def _set_prior(self, i: int, key: str, new: tuple | None) -> None:
        mem = self.members[i]
        old = mem.extra.pop(key, None)
        if old is not None:
            self._gauss(i, old, -old[3])
        if new is not None:
            mem.extra[key] = new
            self._gauss(i, new, new[3])
        self._upload_quad()
        mask = self._mask(i)
        self._normalize(mask)
        if self.ess_d.numpy()[i] < self.ess_frac * self.n:
            self._resample_move(mask)

    def _gauss(self, i: int, prior, coef: float) -> None:
        cols, mu, prec, _ = prior
        self._launch(k_add_gauss, self.n, [self.theta_d, self.logw_d, i, self._arr(cols, wp.int32),
                                           self._arr(mu), self._arr(prec), float(coef)])

    # ---- SMC internals ------------------------------------------------

    def _launch(self, kernel, dim, inputs) -> None:
        wp.launch(kernel, dim=dim, inputs=inputs, device=self.device)

    def _salt(self) -> int:
        self._calls += 1  # host-side queries only; SMC draws use the per-member ncall_d
        return self._calls

    def _lse_rows(self, base, extra, coef, rowb, mask) -> None:
        """lse_d / ess_d of base + coef * extra, per member."""
        self._launch(k_lse_partial, (self.b, self.nc), [base, extra, coef, rowb, mask, self.n, self.pm_d, self.p1_d, self.p2_d, self.chunk])
        self._launch(k_lse_final, self.b, [self.pm_d, self.p1_d, self.p2_d, self.nc, rowb, mask, self.lse_d, self.ess_d])

    def _next_step(self, active, target) -> None:
        """Largest tempering step <= remaining that keeps ESS above target (grid search, GRID-ary)."""
        self._launch(k_search_init, self.b, [self.t, active, self.lo_d, self.hi_d, self.full_d])
        for r in range(SEARCH_ROUNDS):
            self._launch(k_grid_partial, (self.b, GRID, self.nc), [self.logw_d, self.ll_d, self.lo_d, self.hi_d, active,
                                                                   self.n, self.gm_d, self.g1_d, self.g2_d, self.chunk])
            self._launch(k_grid_ess, (self.b, GRID), [self.gm_d, self.g1_d, self.g2_d, self.nc, active, self.gess_d])
            self._launch(k_grid_pick, self.b, [self.gess_d, target, active, int(r == 0), self.lo_d, self.hi_d, self.full_d])

    def _normalize(self, mask) -> None:
        self._lse_rows(self.logw_d, self.ll_d, self.zero_coef_d, self.rowb_d, mask)
        self._launch(k_subtract, (self.b, self.n), [self.logw_d, self.lse_d, mask])

    def _cumsum(self, mask) -> None:
        self._launch(k_scan_chunk, (self.b, self.nc), [self.logw_d, mask, self.n, self.cum_d, self.part_d, self.chunk])
        self._launch(k_scan_parts, self.b, [self.part_d, self.nc, mask])
        self._launch(k_scan_add, (self.b, self.n), [self.cum_d, self.part_d, mask, self.chunk])

    def _weighted_cov(self, mask) -> None:
        npar = self.t.npar
        self._launch(k_mean_partial, (self.b, self.nc, self.p), [self.theta_d, self.logw_d, npar, mask, self.n, self.mpart_d, self.chunk])
        self._launch(k_mean_final, (self.b, self.p), [self.mpart_d, self.nc, npar, mask, self.mean_d])
        self._launch(k_cov_partial, (self.b, self.nc, self.p * self.p), [self.theta_d, self.logw_d, self.mean_d, npar, mask, self.n, self.cpart_d, self.chunk])
        self._launch(k_cov_final, (self.b, self.p, self.p), [self.cpart_d, self.nc, npar, mask, self.cov_d])

    def _resample_move(self, mask) -> None:
        """Systematic resample, then random-walk Metropolis moves, for masked members."""
        self._cumsum(mask)
        self._launch(k_systematic, (self.b, self.n), [self.theta_d, self.cum_d, self.logw_d, mask, self.seed_d,
                                                      self.ncall_d, self.n, self.p, self.tmp_d])
        self.theta_d, self.tmp_d = self.tmp_d, self.theta_d
        self._weighted_cov(mask)
        self._launch(k_proposal_chol, self.b, [self.cov_d, self.t.npar, mask, self.n, self.chol_d])
        self._launch(k_log_target, (self.b, self.n), [self.theta_d, self.t, self.ob, mask, self.lt_d])
        for step in range(self.mh_steps):
            self._launch(k_mh, (self.b, self.n), [self.theta_d, self.prop_d, self.lt_d, self.chol_d, self.t,
                                                  self.ob, mask, self.seed_d, self.ncall_d, step + 1])
        self._launch(k_bump, self.b, [mask, self.ncall_d])

    # ---- uploads --------------------------------------------------------

    def _upload_quad(self) -> None:
        qa, qb = np.zeros((self.b, self.p, self.p)), np.zeros((self.b, self.p))
        has = np.zeros(self.b, np.int32)
        for i, m in enumerate(self.members):
            if m.ref._couplings or m.extra:
                a, bv = m.quad()
                qa[i, : m.p, : m.p], qb[i, : m.p], has[i] = a, bv, 1
        self.t.qa, self.t.qb, self.t.has_quad = self._arr(qa), self._arr(qb), self._arr(has, wp.int32)

    def _upload_obs(self, new: list[dict[str, np.ndarray] | None]) -> None:
        """Flat layout: per member, its seen records then its new batch (if any)."""
        recs, bounds, k = [], np.zeros((4, self.b), np.int32), 0
        for i, m in enumerate(self.members):
            ns, nn = len(m.seen["y"]), 0 if new[i] is None else len(new[i]["y"])
            bounds[:, i] = (k, k + ns, k + ns, k + ns + nn)
            recs.append(m.seen)
            if nn:
                recs.append(new[i])
            k += ns + nn
        recs.append(_PAD)  # Warp arrays are never empty
        self.ob = self._obs_struct(_concat(recs))
        self.t.seen_lo, self.t.seen_hi, self.t.new_lo, self.t.new_hi = (self._arr(r, wp.int32) for r in bounds)

    def _obs_struct(self, rec: dict[str, np.ndarray]) -> Obs:
        ob = Obs()
        for k in ("proc", "cols", "hole"):
            setattr(ob, k, self._arr(rec[k], wp.int32))
        for k in ("d", "u", "v", "y"):
            setattr(ob, k, self._arr(rec[k]))
        return ob



class ParticlePosterior:
    """One posterior on the GPU, same API as `model.posterior.ParticlePosterior`.

    Built standalone it owns a batch of one; `PosteriorBatch[i]` gives a view
    of a member of a larger batch. `theta` and `logw` are host copies.
    """

    def __init__(
        self,
        sites: str | dict[str, str],
        pieces: dict[str, Piece],
        n: int = 4000,
        seed: int = 0,
        ess_frac: float = 0.5,
        mh_steps: int = 3,
        between_site_sd: float | None = None,
        device: str | None = None,
    ):
        batch = PosteriorBatch([sites], pieces, [seed], n=n, ess_frac=ess_frac, mh_steps=mh_steps,
                               between_site_sd=between_site_sd, device=device)
        self._bind(batch, 0)

    @classmethod
    def _view(cls, batch: PosteriorBatch, i: int) -> ParticlePosterior:
        self = cls.__new__(cls)
        self._bind(batch, i)
        return self

    def _bind(self, batch: PosteriorBatch, i: int) -> None:
        self.batch, self.i = batch, i
        ref = batch.members[i].ref
        self.sites, self.single, self.process = ref.sites, ref.single, ref.process
        self.pieces, self.hier = ref.pieces, ref.hier
        self.specs, self.blocks, self.names, self.tags = ref.specs, ref.blocks, ref.names, ref.tags
        self.n, self.ess_frac, self.mh_steps = batch.n, batch.ess_frac, batch.mh_steps

    @property
    def theta(self) -> np.ndarray:
        return self.batch.theta_d.numpy()[self.i, :, : len(self.specs)].copy()

    @property
    def logw(self) -> np.ndarray:
        return self.batch.logw_d.numpy()[self.i].copy()

    # ---- Model protocol -------------------------------------------------

    def update(self, ms: list[Measurement]) -> None:
        self.batch.update({self.i: ms})

    def predict(self, piece: Piece, site: str | None = None) -> tuple[float, float]:
        rec = self.batch._query(self.i, [piece], site)
        mean, var = self.batch._moments(rec, np.array([self.i]))
        return float(mean[0]), float(np.sqrt(var[0]))

    # ---- extra predictive outputs --------------------------------------

    def predict_interval(self, piece: Piece, q: float = 0.9, k: int = 20000, site: str | None = None) -> tuple[float, float]:
        draws = self.batch._interval_draws(self.i, self.batch._query(self.i, [piece], site), k)
        lo, hi = np.quantile(draws, [(1 - q) / 2, (1 + q) / 2])
        return float(lo), float(hi)

    def log_predictive(self, piece: Piece, y: float, site: str | None = None) -> float:
        """Log predictive density of an observed diameter (held-out LPD)."""
        rec = self.batch._query(self.i, [piece], site)
        return float(self.batch._log_predictive(self.i, rec, np.array([y], float))[0])

    def predictive_components(self, pieces: list[Piece] | PieceArrays, site: str | None = None):
        """Per-particle predicted mean [N, M] and noise std [N] for one site's pieces."""
        rec = self.batch._query(self.i, pieces, site)
        m = len(rec["y"])
        if m == 0:
            proc, cols = self.blocks[site or self.batch.members[self.i].ref._only_site()]
            return np.zeros((self.n, 0)), physics.sigma(proc, self.theta[:, cols])
        mu, s = self.batch._components(rec, np.full(m, self.i))
        return mu.numpy().T.copy(), s.numpy()[0].copy()

    # ---- cross-site summaries ------------------------------------------

    def summary(self, tag: str = "shared") -> tuple[dict[str, tuple[float, float]], np.ndarray, list[str]]:
        """Weighted mean/variance per parameter with `tag`, plus their covariance."""
        cols = [j for j, t in enumerate(self.tags) if t == tag]
        mean, cov = self.batch._summary(self.i)
        mean, cov = mean[cols], cov[np.ix_(cols, cols)]
        sel = [self.names[j] for j in cols]
        return {nm: (float(mean[i]), float(cov[i, i])) for i, nm in enumerate(sel)}, cov, sel

    def set_prior_from_summary(
        self, means: dict[str, float], cov: np.ndarray, weight: float, key: str = "default"
    ) -> None:
        """Add (or replace, by `key`) a tempered Gaussian factor on shared parameters.

        Same semantics as the reference: `weight` is the tempering exponent from
        sender credibility, `key` is the sender, only shared parameters accepted.
        """
        ix = {nm: j for j, nm in enumerate(self.names)}
        for nm in means:
            if nm not in ix or self.tags[ix[nm]] != "shared":
                raise ValueError(f"{nm} is not a shared parameter and cannot come from another site")
        new = None
        if weight > 0 and means:
            cols = np.array([ix[nm] for nm in means])
            prec = np.linalg.inv(cov + 1e-12 * np.eye(len(cols)))
            new = (cols, np.array(list(means.values()), float), prec, weight)
        self.batch._set_prior(self.i, key, new)

    def ess(self) -> float:
        return float(self.batch.ess()[self.i])

