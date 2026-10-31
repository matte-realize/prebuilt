"""Particle posterior over physics parameters. Implements `Model`.

Resample-move SMC: new measurements are folded in with adaptive tempering so
the effective sample size never collapses. After each resample, particles are
moved with a random-walk Metropolis step that targets the current tempered
posterior. Everything is vectorized over particles ([N, P]), so an agents
axis ([A, N, P]) can be added later without restructuring.

One site (the normal case): `ParticlePosterior("resin", pieces)`. Parameter
names match `physics.PARAMS`.
Several sites (the pooled-data oracle only): `ParticlePosterior({"resin": "resin",
"pla": "pla"}, pieces)`. Each site gets its own copy of the site-tagged
parameters (named "site.param"), and every site shares one set of
shared-tagged parameters.

Raw measurements stay inside this object. Only `summary()` output, which
covers the shared-tagged parameters, may be put in a `Message`.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from contracts import Measurement, Piece
from model import physics
from model.physics import PieceArrays

LOG2PI = np.log(2 * np.pi)


def _logsumexp(a: np.ndarray, axis: int | None = None) -> np.ndarray:
    m = np.max(a, axis=axis, keepdims=True)
    m = np.where(np.isfinite(m), m, 0.0)
    out = np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True)) + m
    return out.squeeze(axis) if axis is not None else out.item()


Batch = dict[str, tuple[PieceArrays, np.ndarray]]  # site -> (pieces, measured diameters)


class ParticlePosterior:
    def __init__(
        self,
        sites: str | dict[str, str],
        pieces: dict[str, Piece],
        n: int = 4000,
        seed: int = 0,
        ess_frac: float = 0.5,
        mh_steps: int = 3,
        between_site_sd: float | None = None,
    ):
        if isinstance(sites, str):
            sites = {sites: sites}
        self.sites = sites                     # site name -> process
        self.single = len(sites) == 1
        self.process = next(iter(sites.values())) if self.single else None
        self.pieces = pieces                   # piece_id -> Piece; Measurement carries only the id
        # Hierarchical (multi-site only): each site gets its own copy of the shared
        # parameters, drawn around one global value with sd = between_site_sd * prior std.
        self.hier = between_site_sd if (between_site_sd and not self.single) else None
        self.specs, self.blocks = self._layout(sites)
        self.names = [s.name for s in self.specs]
        self.tags = [s.tag for s in self.specs]
        self.rng = np.random.default_rng(seed)
        self.n = n
        self.ess_frac = ess_frac
        self.mh_steps = mh_steps
        self.theta = physics.sample_prior(self.specs, n, self.rng)  # [N, P]
        if self.hier:
            for g, c, tau in self._couplings:
                lo, hi = self.specs[g].lo, self.specs[g].hi
                self.theta[:, c] = np.clip(self.theta[:, g] + tau * self.rng.standard_normal(n), lo, hi)
        self.logw = np.full(n, -np.log(n))
        self._seen: list[Measurement] = []
        self._seen_batch: Batch | None = None
        self._extra_priors: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}

    def _layout(self, sites: dict[str, str]):
        """Column layout. blocks[site] = (process, theta columns in PARAMS[process] order)."""
        specs, site_cols = [], {}
        for site, proc in sites.items():
            site_cols[site] = []
            for s in physics.PARAMS[proc]:
                if s.tag == "site":
                    site_cols[site].append(len(specs))
                    specs.append(s if self.single else replace(s, name=f"{site}.{s.name}"))
        shared_ix = {}
        for s in physics.SHARED:
            shared_ix[s.name] = len(specs)
            specs.append(s)
        # Per-site copies of the shared parameters (hierarchical only). Their own prior is
        # flat within bounds; the coupling to the global value lives in _couplings.
        local_ix: dict[str, dict[str, int]] = {site: {} for site in sites}
        self._couplings: list[tuple[int, int, float]] = []   # (global col, site copy col, sd)
        if self.hier:
            for site in sites:
                for s in physics.SHARED:
                    local_ix[site][s.name] = len(specs)
                    self._couplings.append((shared_ix[s.name], len(specs), self.hier * s.prior_std))
                    specs.append(replace(s, name=f"{site}.{s.name}", prior_std=1e6, tag="site"))
        blocks = {}
        for site, proc in sites.items():
            it = iter(site_cols[site])
            cols = [next(it) if s.tag == "site" else local_ix[site].get(s.name, shared_ix[s.name])
                    for s in physics.PARAMS[proc]]
            blocks[site] = (proc, np.array(cols))
        return specs, blocks

    # ---- Model protocol -------------------------------------------------

    def update(self, ms: list[Measurement]) -> None:
        ok = [m for m in ms if m.status == "ok" and m.measured_d is not None]
        if not ok:
            return  # failures are printability outcomes, scored elsewhere
        batch = self._batch(ok)

        phi = 0.0  # fraction of the new batch's likelihood already absorbed
        while phi < 1.0:
            ll = self._loglik(batch, self.theta)
            step = self._next_step(ll, 1.0 - phi)
            self.logw = self._normalize(self.logw + step * ll)
            phi = min(1.0, phi + step)
            if self.ess() < self.ess_frac * self.n:
                self._resample()
                self._move(batch, phi)
        self._seen.extend(ok)
        self._seen_batch = self._batch(self._seen)

    def predict(self, piece: Piece, site: str | None = None) -> tuple[float, float]:
        mu, s = self.predictive_components([piece], site)
        w = np.exp(self.logw)
        mean = float(w @ mu[:, 0])
        var = float(w @ (mu[:, 0] - mean) ** 2 + w @ s**2)
        return mean, float(np.sqrt(var))

    # ---- extra predictive outputs --------------------------------------

    def predict_interval(self, piece: Piece, q: float = 0.9, k: int = 20000, site: str | None = None) -> tuple[float, float]:
        mu, s = self.predictive_components([piece], site)
        idx = self.rng.choice(self.n, size=k, p=np.exp(self.logw))
        draws = mu[idx, 0] + s[idx] * self.rng.standard_normal(k)
        lo, hi = np.quantile(draws, [(1 - q) / 2, (1 + q) / 2])
        return float(lo), float(hi)

    def log_predictive(self, piece: Piece, y: float, site: str | None = None) -> float:
        """Log predictive density of an observed diameter (held-out LPD)."""
        mu, s = self.predictive_components([piece], site)
        lp = -0.5 * ((y - mu[:, 0]) / s) ** 2 - np.log(s) - 0.5 * LOG2PI
        return float(_logsumexp(self.logw + lp))

    def predictive_components(self, pieces: list[Piece] | PieceArrays, site: str | None = None):
        """Per-particle predicted mean [N, M] and noise std [N] for one site's pieces."""
        site = site or self._only_site()
        proc, cols = self.blocks[site]
        x = pieces if isinstance(pieces, PieceArrays) else PieceArrays.from_pieces(pieces)
        th = self.theta[:, cols]
        return physics.predict_d(proc, x, th), physics.sigma(proc, th)

    # ---- cross-site summaries ------------------------------------------

    def summary(self, tag: str = "shared") -> tuple[dict[str, tuple[float, float]], np.ndarray, list[str]]:
        """Weighted mean/variance per parameter with `tag`, plus their covariance."""
        cols = [j for j, t in enumerate(self.tags) if t == tag]
        sub = self.theta[:, cols]
        w = np.exp(self.logw)
        mean = w @ sub
        dev = sub - mean
        cov = (dev * w[:, None]).T @ dev
        sel = [self.names[j] for j in cols]
        return {nm: (float(mean[i]), float(cov[i, i])) for i, nm in enumerate(sel)}, cov, sel

    def set_prior_from_summary(
        self, means: dict[str, float], cov: np.ndarray, weight: float, key: str = "default"
    ) -> None:
        """Add (or replace, by `key`) a tempered Gaussian factor on shared parameters.

        Used for another site's message: `weight` in [0, 1] is the tempering
        exponent, set from sender credibility; `key` is the sender, so a newer
        message from the same sender replaces the older one instead of
        double counting. Only shared-tagged parameters are accepted.
        """
        ix = {nm: j for j, nm in enumerate(self.names)}
        for nm in means:
            if nm not in ix or self.tags[ix[nm]] != "shared":
                raise ValueError(f"{nm} is not a shared parameter and cannot come from another site")
        old = self._extra_priors.pop(key, None)
        if old is not None:
            self.logw = self.logw - old[3] * self._gauss(self.theta, *old[:3])
        if weight > 0 and means:
            cols = np.array([ix[nm] for nm in means])
            mu = np.array(list(means.values()))
            prec = np.linalg.inv(cov + 1e-12 * np.eye(len(cols)))
            self._extra_priors[key] = (cols, mu, prec, weight)
            self.logw = self.logw + weight * self._gauss(self.theta, cols, mu, prec)
        self.logw = self._normalize(self.logw)
        if self.ess() < self.ess_frac * self.n:
            self._resample()
            self._move(None, 0.0)

    # ---- internals ------------------------------------------------------

    def ess(self) -> float:
        return float(1.0 / np.sum(np.exp(2 * self.logw)))

    def _only_site(self) -> str:
        if not self.single:
            raise ValueError("multi-site posterior: pass site=")
        return next(iter(self.sites))

    def _batch(self, ms: list[Measurement]) -> Batch:
        groups: dict[str, list[Measurement]] = {}
        for m in ms:
            site = self._only_site() if self.single else m.site
            groups.setdefault(site, []).append(m)
        return {
            site: (PieceArrays.from_pieces([self.pieces[m.piece_id] for m in g]), np.array([m.measured_d for m in g]))
            for site, g in groups.items()
        }

    def _loglik(self, batch: Batch, theta: np.ndarray) -> np.ndarray:
        ll = np.zeros(theta.shape[0])
        for site, (x, y) in batch.items():
            proc, cols = self.blocks[site]
            th = theta[:, cols]
            mu = physics.predict_d(proc, x, th)            # [N, M]
            s = physics.sigma(proc, th)[:, None]           # [N, 1]
            ll += (-0.5 * ((y[None, :] - mu) / s) ** 2 - np.log(s) - 0.5 * LOG2PI).sum(axis=1)
        return ll

    @staticmethod
    def _gauss(theta: np.ndarray, cols: np.ndarray, mu: np.ndarray, prec: np.ndarray) -> np.ndarray:
        d = theta[:, cols] - mu
        return -0.5 * np.einsum("ni,ij,nj->n", d, prec, d)

    def _log_target(self, theta: np.ndarray, batch: Batch | None, phi: float) -> np.ndarray:
        """Current tempered posterior: prior x extra priors x past data x new batch^phi."""
        with np.errstate(invalid="ignore", divide="ignore"):  # out-of-bounds proposals -> NaN, rejected
            lt = physics.log_prior(self.specs, theta)
            for g, c, tau in self._couplings:
                lt = lt - 0.5 * ((theta[:, c] - theta[:, g]) / tau) ** 2
            for cols, mu, prec, w in self._extra_priors.values():
                lt = lt + w * self._gauss(theta, cols, mu, prec)
            if self._seen_batch:
                lt = lt + self._loglik(self._seen_batch, theta)
            if batch is not None and phi > 0:
                lt = lt + phi * self._loglik(batch, theta)
            return lt

    def _next_step(self, ll: np.ndarray, remaining: float) -> float:
        """Largest tempering step <= remaining that keeps ESS above target."""
        target = self.ess_frac * self.n
        ess_at = lambda t: 1.0 / np.sum(np.exp(2 * self._normalize(self.logw + t * ll)))
        if ess_at(remaining) >= target:
            return remaining
        lo, hi = 0.0, remaining
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ess_at(mid) >= target else (lo, mid)
        return max(lo, 1e-6)

    def _resample(self) -> None:
        """Systematic resampling."""
        w = np.exp(self.logw)
        positions = (self.rng.random() + np.arange(self.n)) / self.n
        idx = np.minimum(np.searchsorted(np.cumsum(w), positions), self.n - 1)
        self.theta = self.theta[idx]
        self.logw = np.full(self.n, -np.log(self.n))

    def _move(self, batch: Batch | None, phi: float) -> None:
        """Random-walk Metropolis moves that leave the tempered posterior invariant."""
        p = self.theta.shape[1]
        cov = np.cov(self.theta, rowvar=False) + 1e-12 * np.eye(p)
        chol = np.linalg.cholesky((2.38**2 / p) * cov)
        lt = self._log_target(self.theta, batch, phi)
        for _ in range(self.mh_steps):
            prop = self.theta + self.rng.standard_normal(self.theta.shape) @ chol.T
            lt_prop = self._log_target(prop, batch, phi)
            accept = np.log(self.rng.random(self.n)) < lt_prop - lt
            self.theta[accept] = prop[accept]
            lt[accept] = lt_prop[accept]

    @staticmethod
    def _normalize(logw: np.ndarray) -> np.ndarray:
        return logw - _logsumexp(logw)
