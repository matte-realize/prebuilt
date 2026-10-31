import json

import numpy as np
import pytest

from contracts import Plate
from model import physics
from model.physics import PieceArrays
from plates.seed import seed_plate
from sim import calibrate
from sim.reference import SimPrinter


@pytest.fixture(scope="module")
def synthetic():
    data, world = calibrate.seed_data_synthetic(7)
    fits = {s: calibrate.fit_site(s, calibrate.SITES[s], d, n_draws=500, steps=10000, seed=i)
            for i, (s, d) in enumerate(data.items())}
    return data, world, fits


def test_calibration_recovers_known_world(synthetic):
    data, world, fits = synthetic
    for site, fit in fits.items():
        assert max(fit.rhat.values()) < 1.05
        ok = [p for p, m in data[site] if m.status == "ok"]
        x = PieceArrays.from_pieces(ok)
        mu = physics.predict_d(fit.process, x, fit.draws[:, :-1]) + fit.draws[:, -1:] * (x.u**2 + x.v**2) / 2
        truth = world[site].truth(Plate("t", site, ok, 0))
        assert np.abs(mu.mean(axis=0) - truth).mean() < 0.01  # mm, noise-free diameters on the seed plate
        s = fit.summary()["sigma_meas"]
        true_sigma = world[site].theta[physics.index(fit.process)["sigma_meas"]]
        assert abs(s["mean"] - true_sigma) < 3 * s["sd"]


def test_failure_fit_moves_toward_observed_failures():
    plate = seed_plate("pla")
    printer = SimPrinter("pla", "pla", physics.sample_prior("pla", 1, np.random.default_rng(0))[0], 0.0,
                         np.random.default_rng(1), fail_d={"pin": 2.5, "hole": 2.5})
    ms = {m.piece_id: m for m in printer.print_and_measure(plate)}
    data = [(p, ms[p.piece_id]) for p in plate.pieces if p.arm == "seed"]
    fit = calibrate.fit_site("pla", "pla", data, n_draws=500, steps=8000)
    s = fit.summary()
    assert s["fail_d_pin"]["mean"] > 1.8 and s["fail_d_hole"]["mean"] > 2.0  # priors are 1.3 and 1.6


def test_draws_become_printers(synthetic):
    _, _, fits = synthetic
    p = fits["resin"].printer(0, seed=3)
    assert p.fail_d.keys() == {"pin", "hole"} and p.fail_width > 0
    assert len(p.print_and_measure(seed_plate("resin"))) == 64


def test_frozen_config_must_be_complete(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"eta": 5}))
    with pytest.raises(SystemExit):
        calibrate.load_config(path)
    full = {k: getattr(calibrate.Config(), k) for k in calibrate.FROZEN}
    for extra in ({"bad_sites": []}, {"share_messages": True}, {"seed": 1}):  # set per run, never frozen
        path.write_text(json.dumps({**full, **extra}))
        with pytest.raises(SystemExit):
            calibrate.load_config(path)
    path.write_text(json.dumps(full))
    assert calibrate.load_config(path) == full


def test_predict_returns_interval_per_round(synthetic):
    _, _, fits = synthetic
    cfg = dict(rounds=1, n_particles=300, slots_per_arm=4, seed_pieces=8)
    pred = calibrate.predict(fits, cfg, range(2), workers=2)
    for key in ("gap", "gap_truth", "iso_minus_net_um"):
        assert set(pred[key]) == {1}
        assert {"median", "q05", "q95"} <= set(pred[key][1])
