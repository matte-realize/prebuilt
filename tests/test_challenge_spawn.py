"""Challenge round (spec 6.5 step 3) and spawn of dormant agents (spec 6.7)."""
from dataclasses import asdict

import numpy as np
import pytest

from agents.agents import DORMANT_NAMES, propose
from agents.challenge import PREDICTABLE, REDUNDANT, Flag, challenge, demote, judged_by
from agents.credibility import Roster
from arms.experiment import Config, _trend_z, run_experiment
from contracts import Message
from eval.audit import audit
from model.posterior import ParticlePosterior
from network.protocol import BoundaryViolation, deserialize, serialize
from plates.library import Candidate
from sim.reference import make_world

SITES = {"resin": "resin", "pla": "pla"}
C = lambda kind, d: Candidate(kind, d)


# ---- challenge ------------------------------------------------------------------

def test_redundant_flag_goes_to_the_less_credible_copy():
    props = {"a": [C("pin", 2.0), C("pin", 3.0)], "b": [C("pin", 2.0), C("hole", 4.0)]}
    flags = challenge(2, {"a": 0.6, "b": 0.4}, props, {}, eig_floor=0.0)
    assert flags == [Flag("a", "b", "pin-2.0", REDUNDANT)]  # b can't flag a's copy back


def test_only_winning_proposals_can_be_flagged():
    # b wins no slot, so a's duplicate of b's top pick is not a winning proposal of b's.
    props = {"a": [C("pin", 2.0)], "b": [C("pin", 2.0)]}
    assert challenge(1, {"a": 0.9, "b": 0.1}, props, {}, eig_floor=0.0) == []


def test_predictable_flag_uses_flaggers_posterior_and_threshold():
    post = ParticlePosterior("resin", {}, n=300, seed=0)
    props = {"a": [C("pin", 2.0)], "b": [C("hole", 3.0)]}
    assert challenge(2, {"a": 0.5, "b": 0.5}, props, {"a": post, "b": None}, eig_floor=0.0) == []
    flags = challenge(2, {"a": 0.5, "b": 0.5}, props, {"a": post, "b": None}, eig_floor=1e9)
    assert len(flags) == 1  # b has no posterior, so only a flags
    f = flags[0]
    assert (f.flagger, f.target, f.piece, f.reason) == ("a", "b", "hole-3.0", PREDICTABLE) and f.eig > 0


def test_flagged_piece_loses_bid_weight_and_its_replacement_tests_the_flag():
    props = {"a": [C("pin", 2.0)], "b": [C("pin", 2.0), C("hole", 4.0), C("hole", 5.0)]}
    cred = {"a": 0.5, "b": 0.5}
    flags = challenge(2, cred, props, {}, eig_floor=0.0)
    bids = demote(props, flags)
    assert [c.key for c in bids["b"]] == ["hole-4.0", "hole-5.0", "pin-2.0"]
    assert judged_by(2, cred, props, bids, flags[0]) == ("hole-4.0", +1)


def test_flagged_piece_that_prints_anyway_tests_the_flag_itself():
    props = {"b": [C("pin", 2.0), C("hole", 4.0)]}
    f = Flag("a", "b", "pin-2.0", REDUNDANT)
    bids = demote(props, [f])
    assert judged_by(2, {"a": 0.0, "b": 1.0}, props, bids, f) == ("pin-2.0", -1)  # b has every slot


def test_at_most_one_flag_per_agent():
    props = {"a": [C("pin", 2.0), C("pin", 3.0)], "b": [C("pin", 2.0), C("pin", 3.0)]}
    flags = challenge(4, {"a": 0.5, "b": 0.5}, props, {}, eig_floor=0.0)
    assert len({f.flagger for f in flags}) == len(flags)


# ---- spawn ----------------------------------------------------------------------

def test_wake_gives_uniform_credibility():
    r = Roster({"a": 0.7, "b": 0.3}, floor=0.05)
    r.wake("position")
    assert r.cred["position"] == pytest.approx(1 / 3)
    assert r.cred["a"] / r.cred["b"] == pytest.approx(0.7 / 0.3)
    assert sum(r.cred.values()) == pytest.approx(1.0)


def test_position_agent_proposes_from_the_library():
    post = ParticlePosterior("resin", {}, n=300, seed=0)
    out = propose("position", 3, {"all": post}, [], 0.2)
    assert len(out) == 3 and all(isinstance(c, Candidate) for c in out)


def test_trend_z():
    x = np.linspace(0, 1, 40)
    assert _trend_z(x, 3 * x + 0.01 * np.sin(np.arange(40))) > 10
    assert _trend_z(x, np.ones(40)) == 0.0


# ---- boundary -------------------------------------------------------------------

def _wire(**kw):
    d = asdict(Message("resin", 1, {}, {}, [], [{"template": "position", "question": "q?", "z": 2.5}]))
    d.update(kw)
    return d


def test_boundary_carries_unmet_needs():
    m = deserialize(serialize(_wire()))
    assert m.unmet_needs == [{"template": "position", "question": "q?", "z": 2.5}]
    old = {k: v for k, v in _wire().items() if k != "unmet_needs"}  # chains from before the field existed
    assert deserialize(serialize(old)).unmet_needs == []


@pytest.mark.parametrize("bad", [
    [{"template": "Dp", "question": "q", "z": 1.0}],                          # not a dormant template
    [{"template": "position", "question": "q", "z": 1.0, "raw": [5.01]}],     # extra key (raw data)
    [{"template": "position", "question": "q" * 500, "z": 1.0}],              # oversized text
    [{"template": "position", "question": "q", "z": float("nan")}],           # not finite
])
def test_boundary_rejects_bad_unmet_needs(bad):
    with pytest.raises(BoundaryViolation):
        serialize(_wire(unmet_needs=bad))


# ---- end to end -----------------------------------------------------------------

def _kinds(res):
    return [e["kind"] for c in res.chains.values() for e in c.entries()]


def test_challenge_round_runs_logs_and_credits():
    res = run_experiment(make_world(SITES, 7), SITES,
                         Config(rounds=2, n_particles=300, seed=7, challenge=True, challenge_eig=1e9, dormant=()))
    assert res.challenges and audit(list(res.chains.values())).passed
    assert "challenge" in _kinds(res) and "challenge_credit" in _kinds(res)
    scored = [c for c in res.challenges if c["credit"] is not None]
    assert scored and all(c["tested_by"] for c in scored)
    for row in res.credibility:  # credit reaches the flagger's dLPD
        flaggers = {c["flagger"] for c in scored if c["round"] == row["round"] and c["site"] == row["site"]}
        assert flaggers <= set(row["dlpd"])


def test_unmet_needs_cross_sites_and_wake_dormant_agents():
    cfg = dict(rounds=2, n_particles=300, seed=8, unmet_z=0.0, spawn_threshold=2, challenge=False,
               dormant=tuple(DORMANT_NAMES))
    # With messages, one site's question plus the other's reaches the threshold in round 1.
    res = run_experiment(make_world(SITES, 8), SITES, Config(**cfg))
    assert {(s["round"], s["site"], s["agent"]) for s in res.spawned} == {(1, "resin", "position"), (1, "pla", "position")}
    assert all("position" in row for row in res.credibility if row["round"] == 2)
    assert audit(list(res.chains.values())).passed
    # Without messages, each site needs two rounds of its own.
    res = run_experiment(make_world(SITES, 8), SITES, Config(**cfg, share_messages=False))
    assert {(s["round"], s["agent"]) for s in res.spawned} == {(2, "position")}


def test_both_features_off():
    res = run_experiment(make_world(SITES, 9), SITES,
                         Config(rounds=1, n_particles=300, seed=9, challenge=False, dormant=()))
    assert not res.challenges and not res.spawned
    assert not {"challenge", "challenge_credit", "unmet_need", "spawn"} & set(_kinds(res))
    assert DORMANT_NAMES == ["position"]
