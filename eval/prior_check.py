"""After the seed plate: did each site's printer land inside what the model can represent?

The models don't need a printer's exact settings: the seed plate is there to learn them.
They do need the truth to sit inside the priors' bounds and the physics to have the right
terms. Neither is testable in simulation, where printers are drawn from the same priors,
so check the real seed data:

- a parameter whose posterior piles up at a bound means the printer is outside the prior;
- a posterior far out in the prior's tail is a surprise worth a look;
- residuals that trend with diameter, position or kind point at a missing term (PLA has
  no scale-with-size term, so an XY scale error shows up as a trend with d).

    python -m eval.prior_check --checkpoint receipts/real/state.pkl
"""
from __future__ import annotations

import argparse
import pickle

import numpy as np

from model import physics
from model.physics import PieceArrays
from model.posterior import ParticlePosterior

AT_BOUND = 0.03   # posterior mean within this fraction of the bound range from a bound
TAIL_Z = 3.0      # posterior mean this many prior std from the prior mean
TREND_Z = 3.0     # |t| of a residual trend


def _trend_z(x: np.ndarray, y: np.ndarray) -> float:
    n = len(x)
    if n < 4 or x.std() == 0 or y.std() == 0:
        return 0.0
    rho = float(np.clip(np.corrcoef(x, y)[0, 1], -0.999999, 0.999999))
    return rho * float(np.sqrt((n - 2) / (1 - rho**2)))


def check_site(process: str, data, pieces, n: int = 4000, seed: int = 0) -> dict:
    """Fit the seed data alone and list anything that says the model can't represent this printer."""
    post = ParticlePosterior(process, pieces, n=n, seed=seed)
    ok = [(p, m) for p, m in data if m.status == "ok"]
    post.update([m for _, m in ok])
    w = np.exp(post.logw)
    params, flags = [], []
    for j, s in enumerate(physics.PARAMS[process]):
        mean = float(w @ post.theta[:, j])
        sd = float(np.sqrt(w @ (post.theta[:, j] - mean) ** 2))
        edge = min(mean - s.lo, s.hi - mean) / (s.hi - s.lo)
        z = (mean - s.prior_mean) / s.prior_std if s.prior_std < 1e3 else 0.0
        params.append({"name": s.name, "mean": mean, "sd": sd, "prior": (s.prior_mean, s.prior_std), "bounds": (s.lo, s.hi)})
        if edge < AT_BOUND:
            flags.append(f"{s.name} = {mean:.4g} is at its bound [{s.lo}, {s.hi}]: the printer is outside the prior; widen it")
        elif abs(z) > TAIL_Z:
            flags.append(f"{s.name} = {mean:.4g} is {z:+.1f} prior sd from the prior mean {s.prior_mean}: check it's physical")
    if len(ok) >= 4:
        z = np.array([(m.measured_d - mu) / sd for p, m in ok for mu, sd in [post.predict(p)]])
        x = PieceArrays.from_pieces([p for p, _ in ok])
        trends = {"diameter": _trend_z(x.d, z), "1/diameter": _trend_z(1 / x.d, z),
                  "radial position": _trend_z(x.u**2 + x.v**2, z), "hole vs pin": _trend_z(x.is_hole.astype(float), z)}
        for k, t in trends.items():
            if abs(t) > TREND_Z:
                flags.append(f"residuals trend with {k} (t = {t:+.1f}): the model may be missing a term")
    else:
        trends = {}
    return {"n_ok": len(ok), "params": params, "trends": trends, "flags": flags}


def check_state(state: dict, n: int = 4000) -> dict[str, dict]:
    pieces = state["pieces"]
    sim = set((state["res"].config or {}).get("sim_sites") or ())
    return {s: check_site(st.process, [(p, m) for p, m in st.data["isolated"] if p.arm == "seed"], pieces, n)
            for s, st in state["sites"].items() if s not in sim}


def report(results: dict[str, dict]) -> str:
    lines = []
    for site, r in results.items():
        lines.append(f"[{site}] {r['n_ok']} seed pieces measured")
        for p in r["params"]:
            lines.append(f"  {p['name']:<11} {p['mean']:+.4f} ± {p['sd']:.4f}   prior {p['prior'][0]} ± {p['prior'][1]}, bounds {list(p['bounds'])}")
        lines += [f"  ! {f}" for f in r["flags"]] or ["  ok: inside the priors, no residual trends"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="receipts/real/state.pkl")
    ap.add_argument("--particles", type=int, default=4000)
    a = ap.parse_args()
    with open(a.checkpoint, "rb") as f:
        print(report(check_state(pickle.load(f), a.particles)))


if __name__ == "__main__":
    main()
