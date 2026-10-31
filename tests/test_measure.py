import cv2
import numpy as np
import pytest

from arms.experiment import Config, run_experiment
from eval.audit import audit
from measure.real import RealPrinter
from measure.scanner import measure_scan
from measure.synth import render_scan
from plates.seed import seed_plate
from sim.reference import make_world


@pytest.mark.parametrize("mode", ["holes", "pins"])
@pytest.mark.parametrize("mirror,angle", [(True, 2.0), (False, -4.0)])
def test_scanner_recovers_known_diameters(mode, mirror, angle):
    plate = seed_plate("pla", keep=None)  # full plate: every slot exercised
    rng = np.random.default_rng(0)
    true = {p.piece_id: p.nominal_d + rng.normal(0, 0.1) for p in plate.pieces}
    img = render_scan(plate, true, mode, dpi=400, mirror=mirror, angle_deg=angle, blur_px=1.5, noise=0.02)
    ms, info = measure_scan(img, plate, mode)
    assert info.mirrored == mirror
    assert all(m.status == "ok" for m in ms) and len(ms) == 32
    err = np.array([m.measured_d - true[m.piece_id] for m in ms])
    assert np.abs(err).max() < 0.025  # mm; 400 dpi is ~63 um/px. Real scans will be worse


def test_scanner_flags_missing_piece():
    plate = seed_plate("resin")
    true = {p.piece_id: p.nominal_d for p in plate.pieces}
    gone = next(p for p in plate.pieces if p.kind == "hole")
    true[gone.piece_id] = 0.0  # did not print through
    ms, _ = measure_scan(render_scan(plate, true, "holes", dpi=300), plate, "holes")
    assert {m.piece_id for m in ms if m.status == "failed"} == {gone.piece_id}


class ScanningPrinter(RealPrinter):
    """RealPrinter whose 'scanner' renders synthetic scans from a hidden-truth sim."""
    def __init__(self, sim, *a, **kw):
        super().__init__(*a, **kw)
        self.sim = sim

    def print_and_measure(self, plate):
        truth = dict(zip([p.piece_id for p in plate.pieces], self.sim.truth(plate)))
        for mode in ("holes", "pins"):
            cv2.imwrite(str(self.scan_dir / f"{plate.plate_id}-{mode}.png"), render_scan(plate, truth, mode, dpi=300))
        return super().print_and_measure(plate)


def test_real_path_end_to_end_with_resume(tmp_path):
    sites = {"resin": "resin", "pla": "pla"}
    world = make_world(sites, 7)
    printers = {s: ScanningPrinter(world[s], s, tmp_path / "scans" / s, ask=lambda _: "y" if "approve" in _ else "",
                                   plate_dir=tmp_path / "plates") for s in sites}
    ck, chains = str(tmp_path / "state.pkl"), str(tmp_path / "chains")
    run_experiment(printers, sites, Config(rounds=1, n_particles=300), chain_dir=chains, checkpoint=ck)
    res = run_experiment(printers, sites, Config(rounds=2, n_particles=300), chain_dir=chains, checkpoint=ck)
    assert sorted({r["round"] for r in res.scores}) == [1, 2]
    rep = audit(list(res.chains.values()))
    assert rep.passed and rep.crossings == 4
    kinds = [e["kind"] for e in res.chains["resin"].entries()]
    assert kinds.count("approval") == 3 and kinds.count("plate") == 3
