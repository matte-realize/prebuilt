"""Corrected designs: "I want a D mm hole (or pin); draw it at D' mm on this printer."

The product-facing payoff of learning a printer's error. Given a fitted posterior, invert
the forward model (`model.physics.predict_d`): find the nominal diameter D' whose
posterior-mean predicted diameter equals the target, then report what a piece drawn at D'
is predicted to come out at, with a 90% interval.

Two intervals are reported for the printed size when drawn at D':
  interval        predictive: parameter uncertainty plus the per-piece scatter the model
                  learned (sigma_meas, which lumps print-to-print scatter with measurement
                  noise), i.e. where one printed and measured piece should land;
  model_interval  parameter uncertainty only: how well the model knows this printer's mean.
With few measurements the model interval is wide; that is the honest answer.

Predicted diameter is monotone increasing in nominal over the plate's range (slope
1 - shrink + (poly_k - size_coef) / d^2 > 0 within the parameter bounds), so a 1-D
bisection on the posterior-mean prediction is enough. The search is limited to the plate
library's range (plates.spec D_MIN..D_MAX); a target outside what that range can print is
clipped and flagged. Positions are normalized plate coordinates (u = column axis,
v = row axis, both in [-1, 1]); the default is the plate center.

What the model does not cover: whether a small feature prints at all (failures are scored
separately), and effects it doesn't model (the simulator's radial term, real-printer
quirks). For a simulated site the simulator's truth is available to check against.

    python -m model.compensate --checkpoint console/runs/<time>/state.pkl --site resin --kind hole --target 5.0
    python -m model.compensate --checkpoint <state.pkl> --site pla --table
"""
from __future__ import annotations

import argparse
import dataclasses
import pickle
from pathlib import Path

import numpy as np

from model import physics
from model.physics import PieceArrays
from plates import spec

Q = 0.9
DEFAULT_TARGETS = (2.0, 3.0, 5.0, 7.0)  # mm, the console's default table


def _pieces(kind: str, d, at=(0.0, 0.0)) -> PieceArrays:
    d = np.atleast_1d(np.asarray(d, float))
    return PieceArrays(d=d, is_hole=np.full(d.shape, kind == "hole"),
                       u=np.full(d.shape, float(at[0])), v=np.full(d.shape, float(at[1])))


def _check(kind: str, at) -> None:
    if kind not in ("pin", "hole"):
        raise ValueError(f"kind must be 'pin' or 'hole', not {kind!r}")
    if not all(-1.0 <= float(c) <= 1.0 for c in at):
        raise ValueError("plate position (u, v) must be within [-1, 1]")


def predicted_mean(post, kind: str, d, at=(0.0, 0.0), site: str | None = None) -> np.ndarray:
    """Posterior-mean predicted diameter for nominal(s) d, [M]."""
    mu, _ = post.predictive_components(_pieces(kind, d, at), site)
    return np.exp(post.logw) @ mu


def _draws(post, kind: str, d: float, at, site, rng, k: int):
    """Weighted particle draws at nominal d: (model-only means [k], predictive draws [k])."""
    mu, s = post.predictive_components(_pieces(kind, d, at), site)
    idx = rng.choice(len(post.logw), size=k, p=np.exp(post.logw - np.logaddexp.reduce(post.logw)))
    m = mu[idx, 0]
    return m, m + s[idx] * rng.standard_normal(k)


def _ivl(x: np.ndarray, q: float) -> list[float]:
    lo, hi = np.quantile(x, [(1 - q) / 2, (1 + q) / 2])
    return [float(lo), float(hi)]


def compensate(post, kind: str, target_d: float, at=(0.0, 0.0), site: str | None = None,
               q: float = Q, k: int = 20000, seed: int = 0, tol: float = 1e-5) -> dict:
    """Nominal to draw so the printed `kind` comes out at `target_d` mm, on the printer `post` was fit to.

    post: a fitted ParticlePosterior (or anything with predictive_components and logw);
    site: needed only for a multi-site posterior. Returns
      draw_d          mm to draw (clipped to the plate range D_MIN..D_MAX)
      predicted_d     posterior-mean printed size when drawn at draw_d
      interval        q predictive interval of the printed size at draw_d (one piece, with scatter)
      model_interval  q interval of the printer's mean at draw_d (parameter uncertainty only)
      shift_um        draw_d - target_d, in µm
      as_drawn        the same three numbers if you just drew it at target_d
      clipped / notes when the target can't be reached in range, or is outside the fitted range.
    """
    _check(kind, at)
    target = float(target_d)
    lo, hi = spec.D_MIN, spec.D_MAX
    f = lambda d: float(predicted_mean(post, kind, d, at, site)[0]) - target
    f_lo, f_hi = f(lo), f(hi)
    notes, clipped = [], None
    if f_lo > 0:
        draw, clipped = lo, "low"
        notes.append(f"a {kind} drawn at the plate minimum {lo:g} mm already prints at {f_lo + target:.3f} mm; "
                     f"{target:g} mm is below what this range can make")
    elif f_hi < 0:
        draw, clipped = hi, "high"
        notes.append(f"a {kind} drawn at the plate maximum {hi:g} mm prints at {f_hi + target:.3f} mm; "
                     f"{target:g} mm is above what this range can make")
    else:
        a, b = lo, hi
        while b - a > tol:
            mid = 0.5 * (a + b)
            a, b = (mid, b) if f(mid) < 0 else (a, mid)
        draw = 0.5 * (a + b)
    t_lo, t_hi = spec.TRAIN_RANGE
    if not clipped and not t_lo <= draw <= t_hi:
        notes.append(f"draw size {draw:.2f} mm is outside the range the plates measure ({t_lo:g}-{t_hi:g} mm): extrapolating")
    if draw < 2.0:
        notes.append("small feature: the model predicts size, not whether it prints at all")
    rng = np.random.default_rng(seed)
    out = {"kind": kind, "target_d": target, "at": [float(at[0]), float(at[1])], "q": q,
           "draw_d": float(draw), "shift_um": float((draw - target) * 1000), "clipped": clipped, "notes": notes}
    for key, d in (("", draw), ("as_drawn", target)):
        m, y = _draws(post, kind, d, at, site, rng, k)
        res = {"predicted_d": float(predicted_mean(post, kind, d, at, site)[0]),
               "interval": _ivl(y, q), "model_interval": _ivl(m, q)}
        if key:
            out[key] = res
        else:
            out.update(res)
    return out


def table(post, targets=DEFAULT_TARGETS, at=(0.0, 0.0), site: str | None = None, **kw) -> list[dict]:
    """compensate() for pins and holes at each target."""
    return [compensate(post, kind, t, at, site, **kw) for t in targets for kind in ("pin", "hole")]


def true_d(printer, kind: str, d, at=(0.0, 0.0)) -> np.ndarray:
    """A SimPrinter's noise-free printed diameter (hidden truth, unmodeled radial term included).
    Same formula as SimPrinter.truth, for a free-standing piece at (u, v). Evaluation only."""
    x = _pieces(kind, d, at)
    return physics.predict_d(printer.process, x, printer.theta[None, :])[0] + printer.radial * (x.u**2 + x.v**2) / 2


# ---- from a run's checkpoint -------------------------------------------------

def load_state(checkpoint: str | Path) -> dict:
    with open(checkpoint, "rb") as f:
        return pickle.load(f)


def posterior_from_state(state: dict, site: str, arm: str = "networked", seed: int = 20261031):
    """Refit `arm`'s posterior for `site` from a checkpoint, as the arm's scoring fit does:
    the site's own data plus (networked) the notes in its inbox at the trust it holds."""
    from arms.experiment import Config, _fit
    sites = state["sites"]
    if site not in sites:
        raise ValueError(f"no site {site!r} in this run (sites: {', '.join(sites)})")
    if arm not in ("isolated", "networked"):
        raise ValueError("arm must be 'isolated' or 'networked'")
    names = {f.name for f in dataclasses.fields(Config)}
    cfg = Config(**{k: tuple(v) if isinstance(v, list) else v for k, v in state["res"].config.items() if k in names})
    st = sites[site]
    inbox = st.inbox if arm == "networked" else None
    return _fit(st, state["pieces"], st.data[arm], cfg, np.random.default_rng(seed), inbox)


def basis(state: dict, site: str, arm: str = "networked") -> dict:
    """What the fit for `site` rests on, for labeling: rounds done, measurements, notes used."""
    st = state["sites"][site]
    kinds = [p.kind for p, m in st.data[arm] if m.status == "ok" and m.measured_d is not None]
    inbox = st.inbox if arm == "networked" else {}
    return {"site": site, "process": st.process, "arm": arm, "rounds_done": state["next_round"] - 1,
            "n_measurements": len(kinds), "n_pins": kinds.count("pin"), "n_holes": kinds.count("hole"),
            "notes_from": {s: round(float(st.trust.get(s, 0.0)), 3) for s in inbox}}


# ---- CLI ---------------------------------------------------------------------

def _fmt(r: dict) -> str:
    lo, hi = r["interval"]
    mlo, mhi = r["model_interval"]
    a = r["as_drawn"]
    s = (f"{r['kind']} {r['target_d']:g} mm: draw it at {r['draw_d']:.3f} mm ({r['shift_um']:+.0f} µm) "
         f"-> prints {r['predicted_d']:.3f} mm (90%: {lo:.3f}-{hi:.3f}; printer mean {mlo:.3f}-{mhi:.3f})\n"
         f"    drawn as-is at {r['target_d']:g} mm it would print {a['predicted_d']:.3f} mm "
         f"({(a['predicted_d'] - r['target_d']) * 1000:+.0f} µm)")
    return s + "".join(f"\n    note: {n}" for n in r["notes"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", required=True, help="state.pkl of a run (console/runs/<time>/ or receipts/)")
    ap.add_argument("--site", required=True)
    ap.add_argument("--kind", choices=("pin", "hole"))
    ap.add_argument("--target", type=float, help="mm wanted")
    ap.add_argument("--table", action="store_true", help=f"pins and holes at {', '.join(f'{t:g}' for t in DEFAULT_TARGETS)} mm")
    ap.add_argument("--at", type=float, nargs=2, default=(0.0, 0.0), metavar=("U", "V"),
                    help="plate position, normalized [-1, 1] (default: center)")
    ap.add_argument("--arm", default="networked", choices=("networked", "isolated"))
    a = ap.parse_args()
    if not a.table and (a.kind is None or a.target is None):
        ap.error("give --kind and --target, or --table")
    state = load_state(a.checkpoint)
    post = posterior_from_state(state, a.site, a.arm)
    b = basis(state, a.site, a.arm)
    notes = ", ".join(f"{s} (trust {t})" for s, t in b["notes_from"].items()) or "none"
    after = "the seed plate" if b["rounds_done"] == 0 else f"round {b['rounds_done']}"
    print(f"{a.site} ({b['process']}), {a.arm} posterior after {after}: "
          f"{b['n_measurements']} measurements ({b['n_pins']} pins, {b['n_holes']} holes); notes from other sites: {notes}")
    sim = getattr(state["res"], "config", {}).get("sim_sites") or ()
    if a.site in sim:
        print("  (this site was printed by a simulator)")
    rows = table(post, at=tuple(a.at)) if a.table else [compensate(post, a.kind, a.target, tuple(a.at))]
    for r in rows:
        print(_fmt(r))


if __name__ == "__main__":
    main()
