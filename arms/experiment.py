"""One experiment: seed plates, then R rounds of all three arms at every site.

    run_experiment(printers, processes, cfg) -> Results

A pure function with no global state. Sweeps call it directly (handoff
contract 3 in docs/build/06-task-split.md).

Arms, all sharing every plate with equal slot budgets and random placement:
  isolated   one agent, own site's data only, max information gain
  networked  agents + auction at each site, plus messages from other sites
  oracle     one agent, every site's raw data pooled (joint posterior); upper bound
All three are scored by the same physics posterior, so they differ only in
which pieces they chose and, for networked, what it received.

Per round, per site: propose, clear, print and measure, then credit, broadcast, and score.
Held-out measurements go into an escrow that only scoring and credibility read.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import asdict, dataclass, field

import numpy as np

from agents import auction
from agents.agents import AGENT_NAMES, propose
from agents.credibility import Roster, update_senders
from agents.selection import greedy_batch
from contracts import Measurement, Message, Piece, Printer
from model.physics import SHARED
from model.posterior import ParticlePosterior
from network import protocol
from plates import heldout
from plates.layout import build_plate_indexed, plate_to_dict
from plates.seed import SEED_PIECES, seed_plate
from receipts.chain import ReceiptChain, canonical, sha256

ARMS = ("isolated", "networked", "oracle")
SHARED_STD = {s.name: s.prior_std for s in SHARED}
Data = list[tuple[Piece, Measurement]]


@dataclass
class Config:
    rounds: int = 3
    n_particles: int = 2000
    slots_per_arm: int = 6           # Phase C: keeps the arms separable (max (64 - 8 held-out) // 3 = 18)
    # Tuned and frozen in Phase C; these defaults are placeholders until then.
    eta: float = 20.0
    cred_floor: float = 0.05
    discount: float = 0.2
    trust_init: float = 1.0
    # Allowed site-to-site spread of the "shared" parameters, as a fraction of each
    # one's prior std. Added to every incoming message's variance, so two sites'
    # confident but slightly different beliefs don't fight.
    between_site_sd: float = 0.25
    oracle_hierarchical: bool = True   # oracle pools raw data under the same between-site spread
    # The oracle's joint posterior has about twice the dimensions of one site's,
    # so it needs more particles to stay an upper bound. None = n_particles.
    oracle_particles: int | None = None
    # True: isolated and oracle also choose pieces by the agent auction (uniform
    # credibility), so the arms differ only in the data each model sees.
    # False: the walkthrough's single max-information agent for both.
    same_agents: bool = True
    # Ablations
    share_messages: bool = True      # False = cut the network
    bad_sites: tuple[str, ...] = ()  # sites that broadcast corrupted beliefs
    agents: tuple[str, ...] = tuple(AGENT_NAMES)
    seed_pieces: int | None = SEED_PIECES  # calibration pieces on the seed plate (None = all 56)
    seed: int = 0


@dataclass
class SiteState:
    site: str
    process: str
    chain: ReceiptChain
    data: dict[str, Data]                       # arm -> (piece, measurement); seed data in every arm
    escrow: Data = field(default_factory=list)  # held-out, scoring and credibility only
    truth: dict[str, float] = field(default_factory=dict)  # sim only: noise-free held-out diameters, eval only
    roster: Roster | None = None
    inbox: dict[str, Message] = field(default_factory=dict)
    trust: dict[str, float] = field(default_factory=dict)


@dataclass
class Results:
    scores: list[dict]          # one row per (round, site, arm)
    credibility: list[dict]     # one row per (round, site): agent credibility after credit
    trust: list[dict]           # one row per (round, receiver, sender)
    retired: list[dict]
    chains: dict[str, ReceiptChain]
    config: dict


def run_experiment(
    printers: dict[str, Printer],
    processes: dict[str, str],
    cfg: Config = Config(),
    chain_dir: str | None = None,
    checkpoint: str | None = None,
) -> Results:
    """Run (or, if `checkpoint` exists, resume) an experiment.

    With `checkpoint`, the full state is pickled after the seed plates and after
    every round, so a crash mid-Saturday loses at most the round in progress.
    """
    state = _load(checkpoint) if checkpoint and os.path.exists(checkpoint) else None
    if state is None:
        state = _init(printers, processes, cfg, chain_dir)
    sites, pieces, res, rng = state["sites"], state["pieces"], state["res"], state["rng"]

    if state["next_round"] == 0:
        _print_all({s: seed_plate(s, cfg.seed_pieces) for s in sites}, printers, sites, pieces)
        state["next_round"] = 1
        _save(checkpoint, state)

    for r in range(state["next_round"], cfg.rounds + 1):
        oracle_post = _fit_oracle(sites, pieces, cfg, rng)
        plates, contribs = {}, {}
        for s, st in sites.items():
            items, contrib = _choose(st, sites, pieces, oracle_post, cfg, rng)
            plate_seed = int(rng.integers(2**31))
            plates[s], index = build_plate_indexed(f"{s}-r{r}", s, items, plate_seed, heldout.heldout_fixed(f"r{r}"))
            contribs[s] = {pid: contrib[i] for pid, i in index.items() if contrib[i] is not None}
        _print_all(plates, printers, sites, pieces)

        for s, st in sites.items():
            _credit(r, st, pieces, contribs[s], cfg, rng, res)
        if cfg.share_messages:
            _broadcast(r, sites, pieces, cfg, rng)
        oracle_post = _fit_oracle(sites, pieces, cfg, rng)
        for s, st in sites.items():
            _score(r, st, pieces, oracle_post, cfg, rng, res)
        state["next_round"] = r + 1
        _save(checkpoint, state)
    return res


def _init(printers, processes, cfg: Config, chain_dir) -> dict:
    sites = {
        s: SiteState(
            s, processes[s],
            ReceiptChain(s, f"{chain_dir}/{s}.jsonl" if chain_dir else None),
            {arm: [] for arm in ARMS},
            roster=Roster.uniform(list(cfg.agents), cfg.cred_floor),
            trust={o: cfg.trust_init for o in printers if o != s},
        )
        for s in printers
    }
    for st in sites.values():
        st.chain.append("config", asdict(cfg))
    res = Results([], [], [], [], {s: st.chain for s, st in sites.items()}, asdict(cfg))
    return {"sites": sites, "pieces": {}, "res": res, "rng": np.random.default_rng(cfg.seed), "next_round": 0}


def _save(path: str | None, state: dict) -> None:
    if path:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(state, f)
        os.replace(tmp, path)


def _load(path: str) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def _print_all(plates: dict, printers: dict[str, Printer], sites: dict[str, SiteState], pieces) -> None:
    """Hand every site its plate first (real printers can then run in parallel), then measure."""
    for s, plate in plates.items():
        _log_plate(plate, sites[s], pieces)
        prepare = getattr(printers[s], "prepare", None)  # real printers: write files, get human approval
        if prepare:
            approval = prepare(plate)
            if approval:
                sites[s].chain.append("approval", approval)
    for s, plate in plates.items():
        _ingest(plate, printers[s].print_and_measure(plate), sites[s])
        truth = getattr(printers[s], "truth", None)  # simulators only; never shown to agents
        if truth:
            sites[s].truth.update({p.piece_id: float(d) for p, d in zip(plate.pieces, truth(plate)) if p.arm == "heldout"})


# ---- fitting ---------------------------------------------------------------

def _rng_seed(rng: np.random.Generator) -> int:
    return int(rng.integers(2**31))


def _fit(st: SiteState, pieces, data: Data, cfg: Config, rng, messages: dict[str, Message] | None = None) -> ParticlePosterior:
    post = ParticlePosterior(st.process, pieces, n=cfg.n_particles, seed=_rng_seed(rng))
    for sender, msg in (messages or {}).items():
        means, cov = protocol.likelihood_factor(msg)
        if means:
            cov = cov + np.diag([(cfg.between_site_sd * SHARED_STD[k]) ** 2 for k in means])
        if means:
            post.set_prior_from_summary(means, cov, st.trust.get(sender, 0.0), key=sender)
    post.update([m for _, m in data])
    return post


def _fit_oracle(sites: dict[str, SiteState], pieces, cfg: Config, rng, keep=lambda p: True) -> ParticlePosterior:
    post = ParticlePosterior({s: st.process for s, st in sites.items()}, pieces,
                             n=cfg.oracle_particles or cfg.n_particles, seed=_rng_seed(rng),
                             between_site_sd=cfg.between_site_sd if cfg.oracle_hierarchical else None)
    post.update([m for st in sites.values() for p, m in st.data["oracle"] if keep(p)])
    return post


# ---- choosing pieces ---------------------------------------------------------

def _uniform_auction(posts, data, k: int, cfg: Config, site: str | None = None) -> list:
    """The networked arm's agents and clearing rule, at fixed uniform credibility."""
    cred = {a: 1.0 / len(cfg.agents) for a in cfg.agents}
    proposals = {a: propose(a, k, posts, data, cfg.discount, site) for a in cred}
    chosen, _ = auction.clear(k, cred, proposals)
    return [c for c, _ in chosen]


def _choose(st: SiteState, sites: dict[str, SiteState], pieces, oracle_post, cfg: Config, rng):
    k = cfg.slots_per_arm
    items, contrib = [], []

    iso_data = st.data["isolated"]
    iso = _fit(st, pieces, iso_data, cfg, rng)
    if cfg.same_agents:
        seed_only = [(p, m) for p, m in iso_data if p.arm == "seed"]
        iso_posts = {"all": iso, "seed": _fit(st, pieces, seed_only, cfg, rng)}
        items += [(c, "isolated") for c in _uniform_auction(iso_posts, iso_data, k, cfg)]
        ora_data = [(p, m) for o in sites.values() for p, m in o.data["oracle"]]
        ora_posts = {"all": oracle_post,
                     "seed": _fit_oracle(sites, pieces, cfg, rng, lambda p: p.arm == "seed")}
        mine = [(p, m) for p, m in ora_data if m.site == st.site]
        items += [(c, "oracle") for c in _uniform_auction(ora_posts, mine, k, cfg, st.site)]
    else:
        items += [(c, "isolated") for c, _ in greedy_batch(iso, k, discount=cfg.discount)]
        items += [(c, "oracle") for c, _ in greedy_batch(oracle_post, k, discount=cfg.discount, site=st.site)]
    contrib += [None] * (2 * k)

    net_data = st.data["networked"]
    posts = {
        "all": _fit(st, pieces, net_data, cfg, rng, st.inbox),
        "seed": _fit(st, pieces, [(p, m) for p, m in net_data if p.arm == "seed"], cfg, rng),
    }
    proposals = {a: propose(a, k, posts, net_data, cfg.discount) for a in st.roster.cred}
    chosen, alloc = auction.clear(k, st.roster.cred, proposals)
    items += [(c, "networked") for c, _ in chosen]
    contrib += [a for _, a in chosen]

    st.chain.append("clearing", {
        "credibility": st.roster.cred,
        "allocation": alloc,
        "proposals": {a: [c.key for c in v[: alloc[a]]] for a, v in proposals.items()},
    })
    return items, contrib


def _log_plate(plate, st: SiteState, pieces) -> None:
    for p in plate.pieces:
        pieces[p.piece_id] = p
    st.chain.append("plate", {
        "plate_id": plate.plate_id,
        "plate_hash": sha256(canonical(plate_to_dict(plate))),
        "seed_hash": sha256(str(plate.seed)),
    })


def _ingest(plate, ms: list[Measurement], st: SiteState) -> None:
    """Route measurements: held-out to escrow, seed to every arm, the rest to their arm."""
    st.chain.append("measurements", {"plate_id": plate.plate_id, "hashes": [sha256(canonical(m)) for m in ms]})
    by_id = {m.piece_id: m for m in ms}
    for p in plate.pieces:
        m = by_id[p.piece_id]
        if p.arm == "heldout":
            st.escrow.append((p, m))
        elif p.arm == "seed":
            for arm in ARMS:
                st.data[arm].append((p, m))
        else:
            st.data[p.arm].append((p, m))


# ---- credit, messages, scoring -----------------------------------------------

def heldout_lpd(post: ParticlePosterior, escrow: Data, site: str | None = None) -> float:
    ok = [(p, m) for p, m in escrow if m.status == "ok"]
    if not ok:
        return 0.0
    return float(np.mean([post.log_predictive(p, m.measured_d, site) for p, m in ok]))


def _credit(r: int, st: SiteState, pieces, contrib: dict[str, str], cfg: Config, rng, res: Results) -> None:
    data = st.data["networked"]
    msgs = st.inbox
    full = heldout_lpd(_fit(st, pieces, data, cfg, rng, msgs), st.escrow)

    dlpd = {}
    for agent in st.roster.cred:
        mine = {pid for pid, a in contrib.items() if a == agent}
        if mine:
            minus = [(p, m) for p, m in data if p.piece_id not in mine]
            dlpd[agent] = full - heldout_lpd(_fit(st, pieces, minus, cfg, rng, msgs), st.escrow)
    retired = st.roster.step(dlpd, cfg.eta)
    res.credibility.append({"round": r, "site": st.site, **st.roster.cred, "dlpd": dlpd})
    for a in retired:
        res.retired.append({"round": r, "site": st.site, "agent": a})

    sender_dlpd = {}
    for sender in msgs:
        others = {k: v for k, v in msgs.items() if k != sender}
        sender_dlpd[sender] = full - heldout_lpd(_fit(st, pieces, data, cfg, rng, others), st.escrow)
    st.trust = update_senders(st.trust, sender_dlpd, cfg.eta)
    for sender, t in st.trust.items():
        res.trust.append({"round": r, "receiver": st.site, "sender": sender, "trust": t, "dlpd": sender_dlpd.get(sender)})
    st.chain.append("credit", {"round": r, "dlpd": dlpd, "credibility": st.roster.cred,
                               "retired": retired, "sender_dlpd": sender_dlpd, "trust": st.trust})


def _broadcast(r: int, sites: dict[str, SiteState], pieces, cfg: Config, rng) -> None:
    """Each site sends the shared-parameter summary of its own data only (no echo of others' messages)."""
    outgoing = {}
    for s, st in sites.items():
        local = _fit(st, pieces, st.data["networked"], cfg, rng)
        summ, _, _ = local.summary("shared")
        if s in cfg.bad_sites:
            summ = _corrupt(summ)
        outgoing[s] = Message(s, r, summ, dict(st.roster.cred), [])
    for s, msg in outgoing.items():
        for o, other in sites.items():
            if o != s:
                other.inbox[s] = protocol.send(msg, sites[s].chain, other.chain)


def _corrupt(summ: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """A bad-faith site: confident beliefs 3 prior std away from the prior mean."""
    prior = {s.name: s for s in SHARED}
    return {k: (prior[k].prior_mean + 3 * prior[k].prior_std, (0.1 * prior[k].prior_std) ** 2) for k in summ}


def _score(r: int, st: SiteState, pieces, oracle_post, cfg: Config, rng, res: Results) -> None:
    models = {
        "isolated": (_fit(st, pieces, st.data["isolated"], cfg, rng), None),
        "networked": (_fit(st, pieces, st.data["networked"], cfg, rng, st.inbox), None),
        "oracle": (oracle_post, st.site),
    }
    ok = [(p, m) for p, m in st.escrow if m.status == "ok"]
    for arm, (post, site) in models.items():
        errs, lpds, inside, terrs = [], [], [], []
        for p, m in ok:
            mean, _ = post.predict(p, site)
            if p.piece_id in st.truth:
                terrs.append(abs(mean - st.truth[p.piece_id]))
            lo, hi = post.predict_interval(p, 0.9, k=4000, site=site)
            errs.append(abs(mean - m.measured_d))
            lpds.append(post.log_predictive(p, m.measured_d, site))
            inside.append(lo <= m.measured_d <= hi)
        res.scores.append({
            "round": r, "site": st.site, "arm": arm,
            "mae": float(np.mean(errs)), "lpd": float(np.mean(lpds)), "cov90": float(np.mean(inside)),
            "mae_truth": float(np.mean(terrs)) if terrs else None,  # sim only: model error without noise
            "n_train": sum(1 for _ in st.data[arm]), "n_heldout": len(ok),
            "n_heldout_failed": sum(1 for _, m in st.escrow if m.status == "failed"),
        })
