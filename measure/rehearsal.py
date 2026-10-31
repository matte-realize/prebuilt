"""Rehearse the real-printer loop without printers.

Runs `run_experiment` through `RealPrinter` exactly as on Saturday (plate files,
approval prompts, scan files on disk, scanner, measurements JSON, receipts,
checkpoints), but a simulated printer "prints" each plate and renders the two
scans the operator would have saved.

    python -m measure.rehearsal --rounds 1 --out /tmp/rehearsal
    python -m measure.rehearsal --rounds 2 --out /tmp/rehearsal   # resumes from the checkpoint
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from contracts import Plate
from measure.real import RealPrinter
from measure.synth import render_scan
from model import physics
from sim.reference import FAIL_D, FAIL_WIDTH, SimPrinter


class RehearsalPrinter(RealPrinter):
    """A RealPrinter whose operator always approves and whose scans come from a SimPrinter."""

    def __init__(self, sim: SimPrinter, scan_dir: str | Path, plate_dir: str | Path, dpi: float = 400, seed: int = 0):
        super().__init__(sim.site, str(scan_dir), ask=self._operator, plate_dir=plate_dir)
        self.sim, self.dpi = sim, dpi
        self.rng = np.random.default_rng(seed)

    def _operator(self, prompt: str) -> str:
        return "y" if "approve" in prompt else ""

    def print_and_measure(self, plate: Plate):
        d = self.sim.truth(plate)
        sigma = physics.sigma(self.sim.process, self.sim.theta[None, :])[0]
        true = {}
        for p, di in zip(plate.pieces, d):
            p_fail = 1 / (1 + np.exp((p.nominal_d - FAIL_D[self.sim.process][p.kind]) / FAIL_WIDTH))
            true[p.piece_id] = 0.0 if self.rng.random() < p_fail else float(di + sigma * self.rng.standard_normal())
        self.printed = true
        for mode in ("holes", "pins"):
            img = render_scan(plate, true, mode, dpi=self.dpi, angle_deg=float(self.rng.uniform(-3, 3)),
                              mirror=bool(self.rng.random() < 0.5), noise=0.02, seed=int(self.rng.integers(2**31)))
            cv2.imwrite(str(self.scan_dir / f"{plate.plate_id}-{mode}.png"), img)
        return super().print_and_measure(plate)


def rehearsal_printers(sites: dict[str, str], out: Path, seed: int = 0) -> dict[str, RehearsalPrinter]:
    from sim.reference import make_world
    world = make_world(sites, seed)
    return {s: RehearsalPrinter(world[s], out / "scans" / s, out / "plates", seed=seed + i)
            for i, s in enumerate(sites)}


def main() -> None:
    from arms.experiment import Config, run_experiment
    from eval.audit import audit
    from eval.metrics import summarize
    from run import SITES

    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--particles", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    res = run_experiment(rehearsal_printers(SITES, out, a.seed), SITES,
                         Config(rounds=a.rounds, n_particles=a.particles, seed=a.seed),
                         chain_dir=str(out / "receipts"), checkpoint=str(out / "receipts" / "state.pkl"))
    print(summarize(res.scores))
    rep = audit(list(res.chains.values()))
    print(f"privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")


if __name__ == "__main__":
    main()
