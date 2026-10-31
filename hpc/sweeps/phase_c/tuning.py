"""Sweep 2: trust and credibility tuning, then the remaining knobs, then particles.

Every config runs under three conditions: all sites honest, pla broadcasting
bad beliefs, resin broadcasting bad beliefs. One run therefore scores both
"bad site loses trust" and "honest site keeps trust".

    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage trust --seed-pieces 8 --slots 6
    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage knobs --seed-pieces 8 --slots 6 --eta 5 ...
    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage particles --seed-pieces 8 --slots 6 --eta 5 ...
    .venv/bin/python hpc/sweeps/phase_c/tuning.py --stage clip --seed-pieces 16 --slots 6 --eta 5 ...
"""
import argparse
import itertools
import sys

from common import run_sweep

CONDITIONS = {"honest": (), "bad_pla": ("pla",), "bad_resin": ("resin",)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["trust", "knobs", "particles", "clip"], required=True)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--seed0", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=15)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--particles", type=int, default=2000)
    ap.add_argument("--seed-pieces", type=int, default=None)
    ap.add_argument("--slots", type=int, default=18)
    # Base values for the later stages (frozen from the earlier ones).
    ap.add_argument("--eta", type=float, default=20.0)
    ap.add_argument("--trust-init", type=float, default=1.0)
    ap.add_argument("--cred-floor", type=float, default=0.05)
    ap.add_argument("--discount", type=float, default=0.2)
    ap.add_argument("--between-site-sd", type=float, default=0.25)
    ap.add_argument("--lpd-clip", type=lambda v: None if v.lower() == "none" else float(v), default=2.0)
    a = ap.parse_args()

    base = dict(rounds=a.rounds, n_particles=a.particles, seed_pieces=a.seed_pieces, slots_per_arm=a.slots,
                eta=a.eta, trust_init=a.trust_init, cred_floor=a.cred_floor, discount=a.discount,
                between_site_sd=a.between_site_sd, lpd_clip=a.lpd_clip)
    if a.stage == "trust":
        grid = {f"eta={e}_ti={t}_floor={c}": dict(eta=e, trust_init=t, cred_floor=c)
                for e, t, c in itertools.product((1, 2, 5, 10, 20), (0.5, 0.75, 1.0), (0.02, 0.05, 0.1))}
    elif a.stage == "knobs":
        grid = {f"disc={d}_bssd={b}": dict(discount=d, between_site_sd=b)
                for d, b in itertools.product((0.0, 0.1, 0.2, 0.4), (0.1, 0.25, 0.5, 1.0))}
    elif a.stage == "clip":
        grid = {f"clip={c}": dict(lpd_clip=c) for c in (None, 1.0, 2.0, 4.0, 8.0)}
    else:
        grid = {f"particles={n}_mh={m}": dict(n_particles=n, mh_steps=m)
                for n, m in itertools.product((1000, 2000, 4000, 8000), (3, 6))}

    arms = {f"{label}|{cond}": {**base, **kw, "bad_sites": bad}
            for label, kw in grid.items() for cond, bad in CONDITIONS.items()}
    if a.stage == "particles":  # bad-site runs don't tell us anything about particle count
        arms = {k: v for k, v in arms.items() if k.endswith("|honest")}
    plate = f"seed{a.seed_pieces or 56}_slots{a.slots}"
    run_sweep(f"tuning_{a.stage}_{plate}", arms, range(a.seed0, a.seed0 + a.seeds), a.workers)


if __name__ == "__main__":
    sys.exit(main())
