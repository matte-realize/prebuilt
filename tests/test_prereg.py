import yaml

from arms.experiment import oracle_mh_steps
from prereg.check import PREREG, check_heldout, config_from, load, missing, sim_config

SITES = {"resin": "resin", "pla": "pla"}


def _filled(tmp_path, with_range: bool):
    pr = yaml.safe_load(PREREG.read_text())
    pr["config"].update(oracle_particles=4000, eta=5.0, cred_floor=0.05, trust_init=0.5, discount=0.2,
                        challenge_eig=0.05, spawn_threshold=2)
    for site in ("resin", "pla"):
        pr["fit_classes_mm"][site] = {"press_below": 0.05, "slip": [0.05, 0.3], "loose_above": 0.3}
    pr["failed_plate_fraction"] = 0.3
    pr["predicted_range"]["metric"] = "iso_minus_net_mae_um"
    if with_range:
        pr["predicted_range"]["range"] = [-1.0, 4.0]
    path = tmp_path / "prereg.yaml"
    path.write_text(yaml.safe_dump(pr))
    return path


def test_committed_prereg_is_ready_for_seed():
    pr, sha = load()
    check_heldout(pr)
    assert missing(pr, "seed") == [] and len(sha) == 64
    assert config_from(pr, sha).same_agents  # unknown keys would raise


def test_registered_oracle_mh_steps():
    # The prereg's deviation oracle_mh_steps states 14; the Warp posterior needs < 16.
    pr, sha = load()
    assert oracle_mh_steps(SITES, config_from(pr, sha)) == 14


def test_sim_config_follows_prereg():
    pr, sha = load()
    registered = config_from(pr, sha)
    cfg = sim_config(pr, seed=3)
    assert (cfg.n_particles, cfg.mh_steps, cfg.oracle_particles, cfg.eta) == \
        (registered.n_particles, registered.mh_steps, registered.oracle_particles, registered.eta)
    assert cfg.seed == 3 and cfg.prereg_sha256 is None
    small = sim_config(pr, n_particles=300, lpd_clip=None)
    assert (small.n_particles, small.oracle_particles, small.lpd_clip) == (300, None, None)
    assert sim_config(pr, n_particles=300, oracle_particles=500).oracle_particles == 500


def test_filled_prereg_builds_config_and_gates_round1(tmp_path):
    pr, sha = load(_filled(tmp_path, with_range=False))
    assert missing(pr, "seed") == []
    assert missing(pr, "round1") == ["predicted_range.range"]
    cfg = config_from(pr, sha, rounds=0)
    assert (cfg.rounds, cfg.eta, cfg.seed_pieces, cfg.slots_per_arm, cfg.prereg_sha256) == (0, 5.0, 16, 6, sha)
    pr, _ = load(_filled(tmp_path, with_range=True))
    assert missing(pr, "round1") == []


def test_unknown_prediction_metric_is_flagged(tmp_path):
    pr, _ = load(_filled(tmp_path, with_range=True))
    pr["predicted_range"]["metric"] = "gap"
    assert [p for p in missing(pr) if p.startswith("predicted_range.metric")]
