from dataclasses import replace

from eval.prior_check import check_site, check_state, report
from model import physics
from plates.seed import seed_plate
from sim.reference import make_world


def _seed_check(printer, seed=0):
    plate = seed_plate(printer.site)
    ms = printer.print_and_measure(plate)
    data = [(p, m) for p, m in zip(plate.pieces, ms) if p.arm == "seed"]
    return check_site(printer.process, data, {p.piece_id: p for p in plate.pieces}, n=2000, seed=seed)


def test_printer_inside_the_prior_passes():
    assert _seed_check(make_world({"pla": "pla"}, 1)["pla"])["flags"] == []


def test_printer_outside_the_prior_is_flagged():
    p = make_world({"pla": "pla"}, 1)["pla"]
    th = p.theta.copy()
    th[physics.index("pla")["w_off"]] = 0.45  # bound is 0.25
    flags = _seed_check(replace(p, theta=th))["flags"]
    assert any("w_off" in f and "bound" in f for f in flags)


def test_check_state_skips_simulated_sites(tmp_path):
    import pickle
    from arms.experiment import Config, run_experiment
    from run import SITES
    ckpt = tmp_path / "state.pkl"
    run_experiment(make_world(SITES, 0), SITES, Config(rounds=0, n_particles=300, sim_sites=("pla",)), checkpoint=str(ckpt))
    out = check_state(pickle.loads(ckpt.read_bytes()), n=1000)
    assert set(out) == {"resin"} and "[resin]" in report(out)
