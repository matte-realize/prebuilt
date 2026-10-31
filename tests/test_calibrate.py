import copy
import json
import math

import numpy as np
import pytest
import yaml

from contracts import Measurement, Plate
from model import physics
from model.physics import PieceArrays
from plates.seed import seed_plate
from sim import calibrate
from prereg.check import PREREG
from sim.reference import SimPrinter


@pytest.fixture(scope="module")
def synthetic():
    data, world = calibrate.seed_data_synthetic(7)
    return data, world, calibrate.fit(data, n_draws=500, steps=20000)


def test_calibration_recovers_known_world(synthetic):
    data, world, calib = synthetic
    assert max(calib.shared_rhat.values()) < 1.05
    for site, fit in calib.sites.items():
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
    plate = seed_plate("pla", None)
    printer = SimPrinter("pla", "pla", physics.sample_prior("pla", 1, np.random.default_rng(0))[0], 0.0,
                         np.random.default_rng(1), fail_d={"pin": 2.5, "hole": 2.5})
    ms = {m.piece_id: m for m in printer.print_and_measure(plate)}
    data = [(p, ms[p.piece_id]) for p in plate.pieces if p.arm == "seed"]
    s = calibrate.fit({"pla": data}, n_draws=500, steps=8000).sites["pla"].summary()
    assert s["fail_d_pin"]["mean"] > 1.8 and s["fail_d_hole"]["mean"] > 2.0  # priors are 1.3 and 1.6


def test_draws_become_printers(synthetic):
    p = synthetic[2].sites["resin"].printer(0, seed=3)
    assert p.fail_d.keys() == {"pin", "hole"} and p.fail_width > 0
    assert len(p.print_and_measure(seed_plate("resin", None))) == 64


def test_config_comes_from_the_prereg(tmp_path):
    prereg = yaml.safe_load(PREREG.read_text())
    prereg["config"]["eta"] = None
    path = tmp_path / "prereg.yaml"
    path.write_text(yaml.safe_dump(prereg))
    with pytest.raises(SystemExit, match="config.eta"):
        calibrate.load_config(path)
    cfg, sha, gaps = calibrate.load_config(path, draft=True)
    assert "config.eta" in gaps and cfg.prereg_sha256 == sha
    prereg["config"]["bad_sites"] = ["pla"]
    path.write_text(yaml.safe_dump(prereg))
    with pytest.raises(SystemExit, match="ablation"):
        calibrate.load_config(path, draft=True)


def test_predict_returns_interval_per_round(synthetic):
    fits = synthetic[2]
    cfg = calibrate.Config(rounds=1, n_particles=300, slots_per_arm=4, seed_pieces=8)
    pred = calibrate.predict(fits, cfg, range(2), workers=2)
    for key in ("gap", "gap_truth", "iso_minus_net_um"):
        assert set(pred[key]) == {1}
        assert {"median", "q05", "q95"} <= set(pred[key][1])


def test_interval_with_no_defined_values():
    assert calibrate._interval([math.nan, math.nan])["n"] == 0
    assert "n=0" in calibrate._fmt(calibrate._interval([]))


@pytest.mark.filterwarnings("ignore:Mean of empty slice", "ignore:invalid value encountered")  # arms/ scores an empty held-out set
def test_prediction_survives_a_site_failing_every_heldout_piece(synthetic):
    fits = copy.deepcopy(synthetic[2])
    fits.sites["pla"].fail_draws[:, :2] = 50.0  # every piece fails at pla
    row = calibrate.run_seed(0, fits, calibrate.Config(rounds=1, n_particles=300, slots_per_arm=4, seed_pieces=8))
    assert math.isfinite(row["iso_minus_net_um"][1])  # resin alone


def test_more_draws_than_kept_samples():
    data, _ = calibrate.seed_data_synthetic(3)
    fit = calibrate.fit({"pla": data["pla"]}, n_draws=2000, steps=1000).sites["pla"]
    assert fit.draws.shape[0] == fit.fail_draws.shape[0] == 2000


def test_seed_data_must_match_the_frozen_seed_plate():
    data, _ = calibrate.seed_data_synthetic(3, keep=16)
    assert {len(d) for d in data.values()} == {16}
    calibrate.check_seed_size(data, 16)
    with pytest.raises(SystemExit):
        calibrate.check_seed_size(data, None)  # full plate is 56


def test_one_world_shares_one_draw(synthetic):
    # both sites' shared parameters come from the same joint sample, so they sit close together
    calib = synthetic[2]
    r, p = calib.sites["resin"].draws, calib.sites["pla"].draws
    ir, ip = [physics.index("resin")[sp.name] for sp in physics.SHARED], [physics.index("pla")[sp.name] for sp in physics.SHARED]
    paired = np.abs(r[:, ir] - p[:, ip]).mean()
    shuffled = np.abs(r[:, ir] - p[np.random.default_rng(0).permutation(len(p))][:, ip]).mean()
    assert paired < shuffled


def test_failure_screening():
    data, _ = calibrate.seed_data_synthetic(7)
    failed = [p.piece_id for p, m in data["pla"] if m.status == "failed"]
    assert failed  # pla's small holes fail in this world
    kept = calibrate.screen_failures(data, failed[:1])
    assert failed[0] not in {p.piece_id for p, _ in kept["pla"]}
    ok_id = next(p.piece_id for p, m in data["pla"] if m.status == "ok")
    with pytest.raises(SystemExit):
        calibrate.screen_failures(data, [ok_id])  # only failed pieces can be excluded
    whole = {**data, "resin": [(p, Measurement(p.piece_id, "x", "resin", None, "failed", "scanner")) for p, _ in data["resin"]]}
    with pytest.raises(SystemExit, match="every seed piece failed"):
        calibrate.screen_failures(whole, [])
