import numpy as np
import pytest

wp = pytest.importorskip("warp")  # runs on the CUDA GPU if there is one, else on Warp's CPU device
wp.config.quiet = True

from arms.experiment import Config, run_experiment
from contracts import Piece, Plate
from model import physics
from plates.seed import seed_plate
from sim import reference, warp_sim
from sim.reference import FAIL_D, FAIL_WIDTH

SITES = {"resin": "resin", "pla": "pla"}


def small_plate(site: str, seed: int = 0) -> Plate:
    """All 64 slots, pins and holes alternating, diameters spanning the failure transition."""
    d = np.linspace(0.6, 3.0, 64)
    pieces = [Piece(f"{site}-p{i}", ("pin", "hole")[i % 2], float(d[i]), (i // 8, i % 8), "seed") for i in range(64)]
    return Plate(f"{site}-small-{seed}", site, pieces, seed)


def test_kernel_columns_cover_physics_params():
    # the kernel mirrors physics.predict_d by hand; a new parameter must be added there too
    assert set(warp_sim.COLS) == {n for proc in warp_sim.PROCESSES for n in physics.names(proc)}


@pytest.mark.parametrize("seed", [0, 1, 7, 123])
def test_truth_matches_reference(seed):
    ref = reference.make_world(SITES, seed)
    w = warp_sim.make_world(SITES, seed, orient_std=0.0)
    for s in SITES:
        assert w[s].process == ref[s].process
        np.testing.assert_array_equal(w[s].theta, ref[s].theta)
        for plate in (seed_plate(s), small_plate(s)):
            np.testing.assert_allclose(w[s].truth(plate), ref[s].truth(plate), rtol=0, atol=1e-6)


def test_noise_and_failures_match_reference():
    k = 3000
    ref = reference.make_world(SITES, 11)
    w = warp_sim.make_world(SITES, 11, orient_std=0.0)
    for s in SITES:
        plate = small_plate(s)
        truth = ref[s].truth(plate)
        sigma = physics.sigma(s, ref[s].theta[None, :])[0]

        r = np.array([[np.nan if m.measured_d is None else m.measured_d for m in ref[s].print_and_measure(plate)]
                      for _ in range(k)])
        res = w[s].sim.print_plates([w[s].index] * k, [plate] * k)
        g = res.measured.reshape(k, -1)

        # failure rate per piece: both match the logistic model and each other
        nominal = np.array([p.nominal_d for p in plate.pieces])
        fail_d = np.array([FAIL_D[s][p.kind] for p in plate.pieces])
        p_fail = 1 / (1 + np.exp((nominal - fail_d) / FAIL_WIDTH))
        se = np.sqrt(p_fail * (1 - p_fail) / k) + 1e-3
        for x in (r, g):
            assert np.all(np.abs(np.isnan(x).mean(0) - p_fail) < 5 * se)

        # standardized residuals of printed pieces: N(0, 1) for both
        zr = ((r - truth) / sigma)[~np.isnan(r)]
        zg = ((g - truth) / sigma)[~np.isnan(g)]
        for z in (zr, zg):
            assert abs(z.mean()) < 5 / np.sqrt(len(z))
            assert abs(z.std() - 1) < 5 / np.sqrt(2 * len(z))
        qs = [0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]
        np.testing.assert_allclose(np.quantile(zg, qs), np.quantile(zr, qs), atol=0.05)


def test_per_printer_failure_model_carries_over():
    # calibrated printers (sim/calibrate.py) set their own failure diameters and width
    ref = reference.make_world(SITES, 5)
    ref["pla"].fail_d, ref["pla"].fail_width = {"pin": 2.5, "hole": 0.9}, 0.05
    w = warp_sim.from_reference(ref, seed=5, orient_std=0.0)
    k, plate = 2000, small_plate("pla")
    g = w["pla"].sim.print_plates([w["pla"].index] * k, [plate] * k).measured.reshape(k, -1)
    nominal = np.array([p.nominal_d for p in plate.pieces])
    fail_d = np.array([{"pin": 2.5, "hole": 0.9}[p.kind] for p in plate.pieces])
    p_fail = 1 / (1 + np.exp((nominal - fail_d) / 0.05))
    se = np.sqrt(p_fail * (1 - p_fail) / k) + 1e-3
    assert np.all(np.abs(np.isnan(g).mean(0) - p_fail) < 5 * se)


def test_one_launch_matches_per_site_printers():
    sites = {f"s{i}": ("resin", "pla")[i % 2] for i in range(6)}
    w = warp_sim.make_world(sites, 3)
    plates = [seed_plate(p.process) for p in w.values()]
    sim = next(iter(w.values())).sim
    res = sim.print_plates([p.index for p in w.values()], plates)
    for b, (p, plate) in enumerate(zip(w.values(), plates)):
        np.testing.assert_array_equal(res.truth[res.job == b], p.truth(plate))


def test_orientation_effect():
    amp = 0.05
    ref = reference.make_world(SITES, 2)
    w = warp_sim.make_world(SITES, 2, orient_std=amp)
    p = w["resin"]
    a, a_again, b = small_plate("resin", 1), small_plate("resin", 1), small_plate("resin", 2)
    extra = p.truth(a) - ref["resin"].truth(a)
    site_amp = p.sim.sites.orient_amp[p.index]
    assert site_amp != 0 and np.all(np.abs(extra) <= abs(site_amp) + 1e-12)
    assert np.abs(extra).max() > 0.1 * abs(site_amp)
    # placement comes from plate.seed, so truth() matches what every print of that plate used
    res = p.sim.print_plates([p.index] * 3, [a, a_again, b])
    np.testing.assert_array_equal(res.truth[res.job == 0], p.truth(a))
    np.testing.assert_array_equal(res.truth[res.job == 1], p.truth(a))
    assert not np.allclose(res.truth[res.job == 2], p.truth(a))  # placement differs plate to plate


def test_draw_sites_distribution():
    n = 20000
    procs = ["resin", "pla"] * (n // 2)
    sites = warp_sim.draw_sites(procs, seed=5, orient_std=0.01)
    for s in physics.SHARED:  # one world value, small per-site jitter
        col = sites.theta[:, warp_sim.COLS.index(s.name)]
        assert col.std() == pytest.approx(0.2 * s.prior_std, rel=0.05)
    for k, proc in enumerate(warp_sim.PROCESSES):
        theta = warp_sim.from_cols(proc, sites.theta[sites.process == k])
        prior = physics.sample_prior(proc, n, np.random.default_rng(0))
        for j, s in enumerate(physics.PARAMS[proc]):
            assert np.all((theta[:, j] >= s.lo) & (theta[:, j] <= s.hi))
            if s.tag == "site":
                assert theta[:, j].mean() == pytest.approx(prior[:, j].mean(), abs=4 * s.prior_std / np.sqrt(n // 2))
                assert theta[:, j].std() == pytest.approx(prior[:, j].std(), rel=0.05)
    assert sites.radial.std() == pytest.approx(0.02, rel=0.05)
    assert sites.orient_amp.std() == pytest.approx(0.01, rel=0.05)


def test_arms_run_on_warp_printers():
    res = run_experiment(warp_sim.make_world(SITES, 3), SITES, Config(rounds=1, n_particles=300, seed=3))
    assert {r["arm"] for r in res.scores} == {"isolated", "networked", "oracle"}
    assert all(r["mae_truth"] is not None for r in res.scores)


def test_site_noise_streams_are_independent():
    sites = {f"s{i}": ("resin", "pla")[i % 2] for i in range(4)}
    plates = {s: small_plate(s) for s in sites}

    def run(order, truth_calls, batched):
        w = warp_sim.make_world(sites, 9)
        if batched:
            sim = next(iter(w.values())).sim
            res = sim.print_plates([w[s].index for s in order], [plates[s] for s in order])
            return {s: res.measured[res.job == b] for b, s in enumerate(order)}
        out = {}
        for s in order:
            out[s] = np.array([np.nan if m.measured_d is None else m.measured_d for m in w[s].print_and_measure(plates[s])])
            if truth_calls:
                w[s].truth(plates[s])
        return out

    base = run(list(sites), truth_calls=False, batched=False)
    for other in (run(list(sites)[::-1], True, False), run(list(sites)[::-1], False, True)):
        for s in sites:
            np.testing.assert_array_equal(other[s], base[s])


def test_orientation_draws_do_not_repeat_next_world():
    # make_world(seed) must not reuse the stream reference.make_world(seed + 1) draws from
    for seed in range(10):
        amp = warp_sim.make_world(SITES, seed, orient_std=1.0)["resin"].sim.sites.orient_amp
        nxt = np.random.default_rng(seed + 1).standard_normal(8)
        assert not np.isclose(amp[:, None], nxt[None, :]).any()


def test_empty_plate_does_not_shift_other_sites():
    def site_a(empty_first):
        w = warp_sim.make_world({"a": "resin", "b": "pla"}, 4)
        if empty_first:
            w["b"].sim.print_plates([w["b"].index], [Plate("empty", "b", [], 1)])
        return w["a"].sim.print_plates([w["a"].index], [seed_plate("resin")]).measured

    np.testing.assert_array_equal(site_a(True), site_a(False))


def test_print_arrays_noise_does_not_depend_on_layout():
    x = physics.PieceArrays.from_pieces(seed_plate("resin").pieces)
    m = len(x.d)

    def run(order):
        sim = warp_sim.make_world({"a": "resin", "b": "pla"}, 4)["a"].sim
        job = np.repeat([0, 1], m)[order]
        geo = [np.tile(a, 2)[order] for a in (x.d, x.is_hole, x.u, x.v)]
        res = sim.print_arrays(np.array([0, 1]), job, *geo, np.zeros(2))
        out = np.empty(2 * m)
        out[order] = res.measured
        return out

    interleaved = np.arange(2 * m).reshape(2, m).T.ravel()
    np.testing.assert_array_equal(run(np.arange(2 * m)), run(interleaved))


def test_pieces_in_one_launch_never_share_noise():
    n = 4096  # the bench's batch size; 32-bit RNG states collided hundreds of times here
    sites = warp_sim.draw_sites(["resin"] * n, 0, orient_std=0.0)
    sim = warp_sim.WarpSim(sites, seed=0)
    x = physics.PieceArrays.from_pieces(seed_plate("resin").pieces)
    m = len(x.d)
    res = sim.print_arrays(np.arange(n), np.repeat(np.arange(n), m), np.full(n * m, 3.0),  # 3 mm: nothing fails
                           np.tile(x.is_hole, n), np.tile(x.u, n), np.tile(x.v, n), np.zeros(n))
    sigma = physics.sigma("resin", warp_sim.from_cols("resin", sites.theta))[res.job]
    z = np.sort((res.measured - res.truth) / sigma)
    assert np.all(np.diff(z) > 1e-12)  # chance of a false alarm ~0.02


def test_negative_seed():
    warp_sim.WarpSim(warp_sim.draw_sites(["resin"], 0), seed=-1).print_plates([0], [small_plate("resin")])
