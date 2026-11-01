import numpy as np
import pytest

from model.compensate import compensate, predicted_mean, table, true_d
from model.posterior import ParticlePosterior
from plates import spec
from plates.seed import seed_plate
from sim.reference import make_world

SITES = {"resin": "resin", "pla": "pla"}


def _fit(sim, site, keep=None, n=800, seed=0):
    plate = seed_plate(site, keep)
    pieces = {p.piece_id: p for p in plate.pieces}
    post = ParticlePosterior(site, pieces, n=n, seed=seed)
    post.update([m for m in sim.print_and_measure(plate) if pieces[m.piece_id].arm == "seed"])
    return post


@pytest.fixture(scope="module")
def fits():
    out = []
    for seed in range(4):
        world = make_world(SITES, seed)
        out += [(world[s], _fit(world[s], s, seed=seed)) for s in SITES]
    return out


def test_corrected_draw_prints_closer_to_target(fits):
    raw, cor = [], []
    for sim, post in fits:
        for kind in ("pin", "hole"):
            for t in (2.0, 3.0, 5.0, 7.0):
                r = compensate(post, kind, t, k=2000)
                raw.append(abs(true_d(sim, kind, t)[0] - t))
                cor.append(abs(true_d(sim, kind, r["draw_d"])[0] - t))
    raw, cor = np.array(raw), np.array(cor)
    assert np.mean(cor < raw) > 0.85
    assert np.median(cor) < 0.3 * np.median(raw)
    assert np.median(cor) < 0.03  # mm


def test_inversion_hits_the_posterior_mean(fits):
    _, post = fits[0]
    r = compensate(post, "hole", 4.0, at=(0.5, -0.5), k=2000)
    assert r["clipped"] is None and not r["notes"]
    assert abs(predicted_mean(post, "hole", r["draw_d"], (0.5, -0.5))[0] - 4.0) < 1e-4
    assert abs(r["predicted_d"] - 4.0) < 1e-4
    assert r["interval"][0] < 4.0 < r["interval"][1]
    lo, hi = r["model_interval"]
    assert r["interval"][0] <= lo < hi <= r["interval"][1]  # scatter widens it
    assert r["shift_um"] == pytest.approx((r["draw_d"] - 4.0) * 1000)


def test_out_of_range_targets_are_clipped_and_said(fits):
    _, post = fits[0]
    low = compensate(post, "pin", 0.3, k=500)
    high = compensate(post, "hole", 12.0, k=500)
    assert low["clipped"] == "low" and low["draw_d"] == spec.D_MIN and "below" in low["notes"][0]
    assert high["clipped"] == "high" and high["draw_d"] == spec.D_MAX and "above" in high["notes"][0]
    edge = compensate(post, "pin", 7.6, k=500)
    assert edge["clipped"] or any("extrapolating" in n for n in edge["notes"])
    with pytest.raises(ValueError):
        compensate(post, "slot", 3.0)
    with pytest.raises(ValueError):
        compensate(post, "pin", 3.0, at=(2.0, 0.0))


def test_few_measurements_give_wider_intervals():
    world = make_world(SITES, 11)
    few, many = _fit(world["resin"], "resin", keep=4, n=800), _fit(world["resin"], "resin", keep=None, n=800)
    w = lambda post: np.diff(compensate(post, "hole", 5.0, k=4000)["model_interval"])[0]
    assert w(few) > w(many)


def test_table_covers_pins_and_holes(fits):
    rows = table(fits[1][1], k=200)
    assert [(r["kind"], r["target_d"]) for r in rows] == [(k, t) for t in (2.0, 3.0, 5.0, 7.0) for k in ("pin", "hole")]


def test_from_a_run_checkpoint(tmp_path, capsys, monkeypatch):
    import sys

    from arms.experiment import Config, run_experiment
    from model import compensate as comp

    ck = tmp_path / "state.pkl"
    run_experiment(make_world(SITES, 3), SITES, Config(rounds=1, n_particles=300, seed=3), checkpoint=str(ck))
    state = comp.load_state(ck)
    b = comp.basis(state, "pla")
    assert b["rounds_done"] == 1 and b["n_measurements"] > 0 and "resin" in b["notes_from"]
    post = comp.posterior_from_state(state, "pla")
    assert compensate(post, "pin", 3.0, k=200)["clipped"] is None
    monkeypatch.setattr(sys, "argv", ["compensate", "--checkpoint", str(ck), "--site", "resin", "--kind", "hole", "--target", "5"])
    comp.main()
    out = capsys.readouterr().out
    assert "draw it at" in out and "round 1" in out


def test_console_corrected_designs(tmp_path):
    from console.runner import Run, Settings

    run = Run(Settings(resin="sim", pla="sim", rounds=1, particles=300), tmp_path).start()
    run.thread.join(120)
    assert run.status == "done", run.error
    d = run.designs("resin")
    assert d["mode"] == "sim" and d["basis"]["rounds_done"] == 1 and len(d["rows"]) == 8
    assert all("sim_truth" in r for r in d["rows"])
    one = run.corrected("pla", "hole", 5.0)["result"]
    assert abs(one["sim_truth"]["at_draw"] - 5.0) < abs(one["sim_truth"]["as_drawn"] - 5.0) + 0.02
    with pytest.raises(ValueError):
        run.corrected("pla", "hole", -1)


def test_discrepancy_widens_the_printer_mean_interval(fits):
    _, post = fits[0]
    on, off = compensate(post, "hole", 5.0, k=4000), compensate(post, "hole", 5.0, k=4000, discrepancy=False)
    assert on["draw_d"] == off["draw_d"] and on["model_sd"] == pytest.approx(off["model_sd"])
    w = lambda r: np.diff(r["model_interval"])[0]
    assert w(on) > w(off)
    expect = 2 * 1.6449 * np.hypot(off["model_sd"], on["discrepancy_mm"])  # roughly normal
    assert w(on) == pytest.approx(expect, rel=0.15)
    assert off["discrepancy_mm"] == 0.0
