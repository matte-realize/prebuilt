import numpy as np
import pytest

wp = pytest.importorskip("warp")
wp.config.quiet = True
if not wp.get_cuda_device_count():
    pytest.skip("no CUDA GPU for Warp", allow_module_level=True)

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
