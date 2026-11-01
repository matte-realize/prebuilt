"""Predictive trust (Config.predictive_trust): score notes on the receiver's held-out pieces, scale their spread."""
import math

from arms import experiment
from arms.experiment import Config, predictive_multiplier, run_experiment
from sim.reference import make_world

SITES = {"resin": "resin", "pla": "pla"}


def test_multiplier():
    assert predictive_multiplier(2.0) == 1.0          # a note that helps keeps full weight
    assert predictive_multiplier(0.0) == 1.0
    assert math.isclose(predictive_multiplier(-1.0), math.e)  # likelihood ratio against the note
    assert predictive_multiplier(-1e6, cap=100.0) == 100.0


def test_off_by_default_and_scored_when_on(monkeypatch):
    seen = {}
    orig = experiment._credit

    def spy(r, st, *a, **k):
        orig(r, st, *a, **k)
        seen[(r, st.site)] = {s: list(v) for s, v in st.predictive.items()}

    monkeypatch.setattr(experiment, "_credit", spy)
    cfg = dict(rounds=2, n_particles=300, seed=1, seed_pieces=8, slots_per_arm=4)
    run_experiment(make_world(SITES, 1), SITES, Config(**cfg))
    assert all(not v for v in seen.values())          # off: nothing scored
    seen.clear()
    run_experiment(make_world(SITES, 1), SITES, Config(**cfg, predictive_trust=True))
    assert seen[(1, "resin")] == {}                    # round 1: no note has arrived yet
    assert len(seen[(2, "resin")]["pla"]) == 1 and len(seen[(2, "pla")]["resin"]) == 1
