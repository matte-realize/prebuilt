import copy
import json
import math
from dataclasses import replace

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
    for key in ("iso_minus_net_um", "iso_minus_net_truth_um", "gap", "gap_truth"):
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
    assert math.isfinite(row["iso_minus_net_truth_um"][1])  # resin alone


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


@pytest.fixture(scope="module")
def tier_b(tmp_path_factory):
    """A tier B seed-plate checkpoint (pla simulated) and a small prereg with the same seed."""
    import pickle
    from arms.experiment import Config, run_experiment
    from sim.reference import make_world
    tmp = tmp_path_factory.mktemp("tier_b")
    printers = {**make_world(calibrate.SITES, 0), "resin": make_world(calibrate.SITES, 11)["resin"]}  # resin stands in for a real printer
    run_experiment(printers, calibrate.SITES, Config(rounds=0, n_particles=300, seed_pieces=16, seed=0, sim_sites=("pla",)),
                   checkpoint=str(tmp / "state.pkl"))
    prereg = yaml.safe_load(PREREG.read_text())
    prereg["config"].update(rounds=1, n_particles=300, oracle_particles=300, mh_steps=2, slots_per_arm=4, seed=0)
    (tmp / "prereg.yaml").write_text(yaml.safe_dump(prereg))
    return tmp, pickle.loads((tmp / "state.pkl").read_bytes())


def _calibrate(monkeypatch, tmp, *args):
    monkeypatch.setattr("sys.argv", ["calibrate", "--state", str(tmp / "state.pkl"), "--prereg", str(tmp / "prereg.yaml"),
                                     "--steps", "2000", "--draws", "50", "--seeds", "1", "--workers", "1", "--out", str(tmp / "out"), *args])
    calibrate.main()


def test_tier_b_calibrates_only_the_real_site(tier_b, monkeypatch):
    from sim.reference import make_world
    tmp, state = tier_b
    assert state["sites"]["pla"].data["isolated"]  # the simulated site has seed data in the checkpoint
    _calibrate(monkeypatch, tmp)
    calib = json.loads((tmp / "out" / "calibration.json").read_text())
    assert "resin" in calib and "pla" not in calib
    world = make_world(calibrate.SITES, 0)["pla"]
    assert calib["simulated"]["pla"]["world_seed"] == 0
    assert calib["simulated"]["pla"]["truth"]["radial"] == world.radial
    pred = json.loads((tmp / "out" / "prediction.json").read_text())
    assert pred["config"]["sim_sites"] == ["pla"] and pred["iso_minus_net_um"]["1"]["n"] == 1
    assert "pla**: simulated" in (tmp / "out" / "summary.md").read_text()


def test_tier_b_prediction_uses_the_runs_world(synthetic):
    from sim.reference import make_world
    calib = replace(synthetic[2], sites={"resin": synthetic[2].sites["resin"]},
                    fixed=calibrate.simulated_sites(("pla",), 0))
    rng = np.random.default_rng(0)
    a, b = calib.world(0, rng), calib.world(1, rng)
    truth = make_world(calibrate.SITES, 0)["pla"]
    for w in (a, b):
        assert np.array_equal(w["pla"].theta, truth.theta) and w["pla"].radial == truth.radial
    assert a["pla"].rng is not b["pla"].rng and a["pla"].rng.random() != b["pla"].rng.random()  # fresh noise per seed
    with pytest.raises(SystemExit, match="some but not all"):
        calibrate.simulated_sites(("pla", "resin"), 0)


def test_tier_b_refuses_a_mismatched_checkpoint(tier_b, monkeypatch):
    tmp, _ = tier_b
    with pytest.raises(SystemExit, match="simulated"):
        _calibrate(monkeypatch, tmp, "--sim-site", "resin")
    prereg = yaml.safe_load((tmp / "prereg.yaml").read_text())
    prereg["config"]["seed"] = 1
    (tmp / "other.yaml").write_text(yaml.safe_dump(prereg))
    monkeypatch.setattr("sys.argv", ["calibrate", "--state", str(tmp / "state.pkl"), "--prereg", str(tmp / "other.yaml"), "--out", str(tmp / "x")])
    with pytest.raises(SystemExit, match="seed 0"):
        calibrate.main()
