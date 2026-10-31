"""Sweep 1: seed-plate size x slots per arm, current default config otherwise.

    .venv/bin/python hpc/sweeps/phase_c/seed_plate.py --seeds 40 --rounds 4
"""
from common import cli, run_sweep

if __name__ == "__main__":
    a = cli(__doc__)
    arms = {
        f"seed{sp or 56}_slots{slots}": dict(seed_pieces=sp, slots_per_arm=slots, n_particles=a.particles, rounds=a.rounds)
        for sp in (4, 8, 16, 32, None)
        for slots in (6, 18)
    }
    run_sweep("seed_plate", arms, range(a.seed0, a.seed0 + a.seeds), a.workers)
