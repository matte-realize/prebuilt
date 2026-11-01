import json
from dataclasses import asdict

import numpy as np
import pytest

from agents.auction import allocate, clear
from agents.credibility import Roster, update_senders
from arms.experiment import Config, _init, _print_all, oracle_mh_steps, run_experiment
from contracts import Message
from eval.audit import audit
from model.posterior import ParticlePosterior
from network.protocol import BoundaryViolation, deserialize, likelihood_factor, send, serialize
from plates import heldout, spec
from plates.layout import build_plate
from plates.library import Candidate
from plates.seed import SEED_PIECES, seed_plate
from plates.stl import to_trimesh, plate_manifold
from receipts.chain import ReceiptChain
from sim.reference import make_world


# ---- auction and credibility --------------------------------------------------

def test_allocate_largest_remainder():
    a = allocate(18, {"a": 0.5, "b": 0.3, "c": 0.2})
    assert a == {"a": 9, "b": 5, "c": 4}  # quotas 9, 5.4, 3.6; the one leftover slot goes to c
    assert sum(allocate(17, {"x": 1, "y": 1, "z": 1}).values()) == 17
    assert allocate(17, {"x": 1, "y": 1, "z": 1}) == allocate(17, {"z": 1, "y": 1, "x": 1})


def test_clear_uses_only_own_proposals():
    p = {"a": [Candidate("pin", 2.0)] * 5, "b": [Candidate("hole", 3.0)] * 5}
    chosen, alloc = clear(4, {"a": 0.75, "b": 0.25}, p)
    assert alloc == {"a": 3, "b": 1}
    assert [ag for _, ag in chosen].count("a") == 3
    assert all(c.kind == ("pin" if ag == "a" else "hole") for c, ag in chosen)


def test_roster_retires_after_two_rounds_below_floor():
    r = Roster.uniform(["good", "bad", "ok"], floor=0.1)
    assert r.step({"bad": -1.0}, eta=5.0) == []
    assert r.step({"bad": -1.0}, eta=5.0) == ["bad"]
    assert set(r.cred) == {"good", "ok"} and abs(sum(r.cred.values()) - 1) < 1e-12


def test_sender_trust_clipped():
    t = update_senders({"s": 1.0}, {"s": 0.5}, eta=10)
    assert t["s"] == 1.0
    assert update_senders({"s": 1.0}, {"s": -0.5}, eta=10)["s"] < 0.01
    assert update_senders({"s": 1.0}, {"s": -1e6}, eta=20)["s"] >= 0  # no overflow


def test_agent_update_survives_huge_dlpd():
    c = Roster.uniform(["a", "b"], 0.0).cred
    from agents.credibility import update_agents
    out = update_agents(c, {"a": 1e4, "b": -1e4}, eta=20)
    assert abs(sum(out.values()) - 1) < 1e-9 and out["a"] > 0.999


def test_lpd_clip_bounds_one_outlier():
    from agents.credibility import delta_lpd
    full, minus = [1.0] * 8, [1.0] * 7 + [41.0]  # one piece swings 40 nats
    assert delta_lpd(full, minus, None) == -5.0
    assert delta_lpd(full, minus, 2.0) == -0.25  # at most clip / n_pieces
    # The outlier alone can no longer zero an honest sender's trust at eta = 20.
    assert update_senders({"s": 1.0}, {"s": delta_lpd(full, minus, 2.0)}, eta=20)["s"] > 1e-3
    assert delta_lpd([], [], 2.0) == 0.0


def test_lpd_clip_none_is_unclipped_mean_difference():
    from agents.credibility import delta_lpd
    rng = np.random.default_rng(0)
    full, minus = list(rng.normal(0, 20, 9)), list(rng.normal(0, 20, 9))
    assert delta_lpd(full, minus, None) == float(np.mean(full)) - float(np.mean(minus))  # the old expression, bit for bit
    assert delta_lpd(full, minus, 1e9) == pytest.approx(delta_lpd(full, minus, None))


# ---- boundary -------------------------------------------------------------------

def _msg(**kw):
    d = asdict(Message("resin", 1, {"size_coef": (0.01, 1e-4)}, {"physics": 0.5}, []))
    d.update(kw)
    return d


def test_boundary_accepts_valid_message():
    m = deserialize(serialize(_msg()))
    assert m.shared_params["size_coef"] == (0.01, 1e-4)


@pytest.mark.parametrize("bad", [
    _msg(raw_measurements=[5.01, 4.98]),                    # extra field
    _msg(shared_params={"Dp": (0.15, 1e-4)}),                # site-specific parameter
    _msg(shared_params={"size_coef": (0.01, -1.0)}),         # invalid variance
    _msg(hypotheses=["x" * 5000]),                           # oversized free text
    {k: v for k, v in _msg().items() if k != "round"},       # missing field
])
def test_boundary_rejects_and_logs(bad):
    chain = ReceiptChain("resin")
    with pytest.raises(BoundaryViolation):
        serialize(bad, chain)
    assert chain.entries()[-1]["kind"] == "boundary_reject"


def test_likelihood_factor_divides_out_prior():
    # A posterior equal to the prior carries no information and is dropped.
    from model.physics import SHARED
    s = {p.name: p for p in SHARED}["size_coef"]
    means, _ = likelihood_factor(Message("pla", 1, {"size_coef": (s.prior_mean, s.prior_std**2)}, {}, []))
    assert means == {}


def test_audit_catches_tampered_crossing():
    a, b = ReceiptChain("resin"), ReceiptChain("pla")
    send(Message("resin", 1, {"size_coef": (0.01, 1e-4)}, {}, []), a, b)
    assert audit([a, b]).passed
    e = json.loads(b._mem[-1])
    e["payload"]["wire"] = e["payload"]["wire"].replace("0.01", "0.02")
    b._mem[-1] = json.dumps(e)
    assert not audit([a, b]).passed


# ---- plates ---------------------------------------------------------------------

def test_seed_plate_layout_and_mesh():
    assert len(seed_plate("resin", keep=None).pieces) == spec.GRID[0] * spec.GRID[1]
    p = seed_plate("resin")
    seed = [x for x in p.pieces if x.arm == "seed"]
    assert len(seed) == SEED_PIECES and {x.kind for x in seed} == {"pin", "hole"}
    held = {x.slot for x in p.pieces if x.arm == "heldout"}
    assert held == set(heldout.HELDOUT_SLOTS)
    assert to_trimesh(plate_manifold(p)).is_watertight


def test_heldout_manifest_is_stable():
    assert heldout.manifest()["sha256"] == heldout.manifest()["sha256"]
    ood = [c for g in heldout.heldout_geometry().values() for c in g
           if not spec.TRAIN_RANGE[0] <= c.nominal_d <= spec.TRAIN_RANGE[1]]
    assert len(ood) == 2 * len(heldout.PLATES)


# ---- end to end -----------------------------------------------------------------

SITES = {"resin": "resin", "pla": "pla"}


def test_experiment_runs_and_passes_audit():
    res = run_experiment(make_world(SITES, 3), SITES, Config(rounds=2, n_particles=400, seed=3))
    assert {(r["round"], r["arm"]) for r in res.scores} == {(r, a) for r in (1, 2) for a in ("isolated", "networked", "oracle")}
    rep = audit(list(res.chains.values()))
    assert rep.passed and rep.crossings == 4


def test_bad_site_loses_trust():
    res = run_experiment(make_world(SITES, 4), SITES, Config(rounds=2, n_particles=400, seed=4, bad_sites=("pla",)))
    final = [r for r in res.trust if r["round"] == 2 and r["sender"] == "pla"]
    assert final[0]["trust"] < 0.5


def test_cut_network_sends_nothing():
    res = run_experiment(make_world(SITES, 5), SITES, Config(rounds=1, n_particles=300, seed=5, share_messages=False))
    assert audit(list(res.chains.values())).crossings == 0


# ---- oracle as a fair upper bound (design notes, point 4) ----------------------------

def test_oracle_mh_steps_scale_with_dimension():
    assert oracle_mh_steps(SITES, Config()) == 7                          # 18 dims vs 8: ceil(3 * 18 / 8)
    assert oracle_mh_steps(SITES, Config(oracle_hierarchical=False)) == 5  # 12 dims
    assert oracle_mh_steps({"resin": "resin"}, Config()) == 3              # one site: same as every arm
    assert oracle_mh_steps(SITES, Config(oracle_mh_steps=3)) == 3


def test_oracle_monte_carlo_error_no_worse_than_one_site():
    """Same data, different particle seeds: the oracle's predictive means must be about as
    stable as a single-site fit's, or Monte Carlo noise alone makes it lose to networked.
    With the old fixed 3 MH steps the oracle's spread was about twice the single site's."""
    printers = make_world(SITES, 0)
    state = _init(printers, SITES, Config(seed=0), None)
    sites, pieces = state["sites"], state["pieces"]
    _print_all({s: seed_plate(s) for s in sites}, printers, sites, pieces)
    pooled = [m for st in sites.values() for _, m in st.data["oracle"]]

    def spread(make, site, data, multi):
        preds = []
        for k in range(6):
            post = make(k)
            post.update(data)
            preds.append([post.predict(p, site if multi else None)[0] for p, m in sites[site].escrow if m.status == "ok"])
        return float(np.mean(np.std(preds, axis=0, ddof=1)))

    steps = oracle_mh_steps(SITES, Config())
    for site in SITES:
        own = [m for _, m in sites[site].data["oracle"]]
        single = spread(lambda k: ParticlePosterior(site, pieces, n=1000, seed=k), site, own, False)
        oracle = spread(lambda k: ParticlePosterior(SITES, pieces, n=1000, seed=k, between_site_sd=0.25, mh_steps=steps),
                        site, pooled, True)
        assert oracle < 1.2 * single, (site, oracle, single)


def test_oracle_data_knob_pools_networked_measurements():
    """oracle_data="networked" fits the oracle to exactly the networked arm's data."""
    from arms.experiment import _fit_oracle
    printers = make_world(SITES, 6, crn=True)
    cfg = Config(rounds=1, n_particles=300, seed=6, oracle_data="networked")
    state = _init(printers, SITES, cfg, None)
    sites, pieces = state["sites"], state["pieces"]
    _print_all({s: seed_plate(s) for s in sites}, printers, sites, pieces)
    for st in sites.values():  # give the networked arm data no other arm has
        st.data["networked"].append(st.data["oracle"][0])
    post = _fit_oracle(sites, pieces, cfg, np.random.default_rng(0))
    want = sorted(m.piece_id for st in sites.values() for _, m in st.data["networked"] if m.status == "ok")
    assert sorted(m.piece_id for m in post._seen) == want


def test_crn_gives_same_noise_to_same_candidates():
    printer = make_world({"resin": "resin"}, 7, crn=True)["resin"]
    c = Candidate("pin", 4.0)
    plate = build_plate("resin-r1", "resin", [(c, "oracle"), (c, "networked")], 1)
    resid = [m.measured_d - t for m, t in zip(printer.print_and_measure(plate), printer.truth(plate))]
    assert resid[0] == pytest.approx(resid[1])
