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

Per round, per site: propose, challenge, clear, print and measure, then credit, log unmet
needs, broadcast, wake dormant agents, and score.
Held-out measurements go into an escrow that only scoring and credibility read.
"""
from __future__ import annotations

import math
import os
import pickle
from dataclasses import asdict, dataclass, field

import numpy as np

from agents import auction, challenge
from agents.agents import AGENT_NAMES, DORMANT_NAMES, SPECS, propose
from agents.credibility import Roster, delta_lpd, update_senders
from agents.selection import greedy_batch
from contracts import Measurement, Message, Piece, Printer
from model.physics import PARAMS, SHARED, PieceArrays
from model.posterior import Layout, ParticlePosterior
from network import protocol
from plates import heldout
from plates.layout import build_plate_indexed, plate_to_dict
from plates.seed import SEED_PIECES, seed_plate
from receipts.chain import ReceiptChain, canonical, sha256

ARMS = ("isolated", "networked", "oracle")
SHARED_STD = {s.name: s.prior_std for s in SHARED}
MH_STEPS = 3  # ParticlePosterior's default, used by every single-site fit
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
    # Per-piece bound (nats) on held-out dLPD in credit. With noise sigma, moving one
    # prediction from a 2-sigma miss to a hit is worth 2 nats; bigger swings come from
    # pieces both fits miss badly, where noise is amplified. None = unclipped.
    lpd_clip: float | None = 2.0
    # Allowed site-to-site spread of the "shared" parameters, as a fraction of each
    # one's prior std. Added to every incoming message's variance, so two sites'
    # confident but slightly different beliefs don't fight.
    between_site_sd: float = 0.25
    oracle_hierarchical: bool = True   # oracle pools raw data under the same between-site spread
    # Particles for the oracle's joint posterior (about twice one site's dimensions).
    # None = n_particles. Mixing (oracle_mh_steps) mattered more than count here.
    oracle_particles: int | None = None
    # True: isolated and oracle also choose pieces by the agent auction (uniform
    # credibility), so the arms differ only in the data each model sees.
    # False: the walkthrough's single max-information agent for both.
    same_agents: bool = True
    # Metropolis moves per resample for the oracle. Random-walk MH mixes about 1/dim as
    # fast per step, so with the same 3 steps a single site gets, the 18-dim hierarchical
    # oracle carries roughly twice the Monte Carlo error in its predictions and loses to
    # networked on identical data (07-status finding 4). None = MH_STEPS scaled by the
    # oracle's dimension over the largest single site's; 3 = the old behavior.
    oracle_mh_steps: int | None = None
    # Diagnostics (docs/build/07-status.md finding 4); defaults are the real design.
    # oracle_data: which arm's measurements the oracle posterior pools ("oracle", or
    #   "networked" = exactly the networked arm's data, so only inference differs).
    oracle_data: str = "oracle"
    # Ablations
    share_messages: bool = True      # False = cut the network
    bad_sites: tuple[str, ...] = ()  # sites that broadcast corrupted beliefs
    agents: tuple[str, ...] = tuple(AGENT_NAMES)
    seed_pieces: int | None = SEED_PIECES  # calibration pieces on the seed plate (None = all 56)
    # Challenge round (spec 6.5 step 3) and spawn of dormant agents (6.7). Both are part of
    # the networked arm's "full system (Section 6)" in the pre-registered design (8.1), so on.
    challenge: bool = True
    challenge_eig: float = 0.05      # nats; a proposal the flagger expects to learn less from is "predictable"
    dormant: tuple[str, ...] = tuple(DORMANT_NAMES)  # templates that can wake; () = no spawning
    spawn_threshold: int = 2         # unmet-needs entries (own + incoming, cumulative) that wake a template
    unmet_z: float = 2.0             # |z| of a residual trend that goes in the unmet-needs log
    seed: int = 0
    prereg_sha256: str | None = None  # real runs: hash of prereg/prereg.yaml, written to the chains


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
    flags: list = field(default_factory=list)            # this round: (Flag, judged_by result) pairs
    unmet: dict[str, int] = field(default_factory=dict)  # template -> unmet-needs entries seen, own + incoming
    unmet_out: list[dict] = field(default_factory=list)  # this round's own entries, to broadcast


@dataclass
class Results:
    scores: list[dict]          # one row per (round, site, arm)
    credibility: list[dict]     # one row per (round, site): agent credibility after credit
    trust: list[dict]           # one row per (round, receiver, sender)
    retired: list[dict]
    chains: dict[str, ReceiptChain]
    config: dict
    challenges: list[dict] = field(default_factory=list)  # one row per flag
    spawned: list[dict] = field(default_factory=list)
    predictions: list[dict] = field(default_factory=list)  # one row per (round, site, arm, held-out piece); viewer only


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

    if cfg.prereg_sha256 and state["next_round"] <= cfg.rounds:
        for st in sites.values():  # the prereg in force for the rounds this call runs
            st.chain.append("prereg", {"sha256": cfg.prereg_sha256, "from_round": state["next_round"]})
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
            _unmet_needs(r, st, pieces, cfg, rng)
        if cfg.share_messages:
            _broadcast(r, sites, pieces, cfg, rng)
        for st in sites.values():
            _spawn(r, st, cfg, res)
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


def oracle_mh_steps(processes: dict[str, str], cfg: Config) -> int:
    """MH steps that give the oracle the same mixing per resample as a single-site fit."""
    if cfg.oracle_mh_steps is not None:
        return cfg.oracle_mh_steps
    bsd = cfg.between_site_sd if cfg.oracle_hierarchical else None
    dim = len(Layout(processes, bsd).specs)
    return math.ceil(MH_STEPS * dim / max(len(PARAMS[p]) for p in processes.values()))


def _fit_oracle(sites: dict[str, SiteState], pieces, cfg: Config, rng, keep=lambda p: True) -> ParticlePosterior:
    processes = {s: st.process for s, st in sites.items()}
    post = ParticlePosterior(processes, pieces,
                             n=cfg.oracle_particles or cfg.n_particles, seed=_rng_seed(rng),
                             mh_steps=oracle_mh_steps(processes, cfg),
                             between_site_sd=cfg.between_site_sd if cfg.oracle_hierarchical else None)
    post.update([m for st in sites.values() for p, m in st.data[cfg.oracle_data] if keep(p)])
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
    bids = _challenge(st, k, proposals, posts, cfg)
    chosen, alloc = auction.clear(k, st.roster.cred, bids)
    items += [(c, "networked") for c, _ in chosen]
    contrib += [a for _, a in chosen]

    st.chain.append("clearing", {
        "credibility": st.roster.cred,
        "allocation": alloc,
        "proposals": {a: [c.key for c in v[: alloc[a]]] for a, v in bids.items()},
    })
    return items, contrib


def _challenge(st: SiteState, k: int, proposals, posts, cfg: Config):
    """Challenge round. Returns the proposals with flagged pieces demoted; keeps the flags for credit."""
    st.flags = []
    if not cfg.challenge:
        return proposals
    cred = st.roster.cred
    own = {a: posts.get(SPECS[a].evidence) for a in cred}
    flags = challenge.challenge(k, cred, proposals, own, cfg.challenge_eig)
    bids = challenge.demote(proposals, flags)
    st.flags = [(f, challenge.judged_by(k, cred, proposals, bids, f)) for f in flags]
    st.chain.append("challenge", {"flags": [
        {**asdict(f), "tested_by": t[0] if t else None} for f, t in st.flags]})
    return bids


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

def heldout_lpds(post: ParticlePosterior, escrow: Data, site: str | None = None) -> list[float]:
    """Per-piece held-out LPD over the measured escrow pieces."""
    return [post.log_predictive(p, m.measured_d, site) for p, m in escrow if m.status == "ok"]


def _credit(r: int, st: SiteState, pieces, contrib: dict[str, str], cfg: Config, rng, res: Results) -> None:
    data = st.data["networked"]
    msgs = st.inbox
    full = heldout_lpds(_fit(st, pieces, data, cfg, rng, msgs), st.escrow)

    dlpd = {}
    for agent in st.roster.cred:
        mine = {pid for pid, a in contrib.items() if a == agent}
        if mine:
            minus = [(p, m) for p, m in data if p.piece_id not in mine]
            dlpd[agent] = delta_lpd(full, heldout_lpds(_fit(st, pieces, minus, cfg, rng, msgs), st.escrow), cfg.lpd_clip)
    flag_credit = _challenge_credit(r, st, pieces, contrib, full, dlpd, cfg, rng, res)
    dlpd = {a: dlpd.get(a, 0.0) + flag_credit.get(a, 0.0) for a in dlpd.keys() | flag_credit.keys()}
    retired = st.roster.step(dlpd, cfg.eta)
    res.credibility.append({"round": r, "site": st.site, **st.roster.cred, "dlpd": dlpd})
    for a in retired:
        res.retired.append({"round": r, "site": st.site, "agent": a})

    sender_dlpd = {}
    for sender in msgs:
        others = {k: v for k, v in msgs.items() if k != sender}
        sender_dlpd[sender] = delta_lpd(full, heldout_lpds(_fit(st, pieces, data, cfg, rng, others), st.escrow), cfg.lpd_clip)
    st.trust = update_senders(st.trust, sender_dlpd, cfg.eta)
    for sender, t in st.trust.items():
        res.trust.append({"round": r, "receiver": st.site, "sender": sender, "trust": t, "dlpd": sender_dlpd.get(sender)})
    st.chain.append("credit", {"round": r, "dlpd": dlpd, "credibility": st.roster.cred,
                               "retired": retired, "sender_dlpd": sender_dlpd, "trust": st.trust})


def _challenge_credit(r: int, st: SiteState, pieces, contrib: dict[str, str], full: list[float],
                      dlpd: dict[str, float], cfg: Config, rng, res: Results) -> dict[str, float]:
    """Score this round's flags on held-out data; returns credit per flagger (added to its dLPD).

    The test piece's leave-one-piece-out dLPD is compared with the round's average per piece
    (sum of the agents' dLPD over pieces printed). A flagged piece that printed anyway holds
    the flag up by being below average; a replacement, by being above it.
    """
    if not st.flags:
        return {}
    data = st.data["networked"]
    baseline = sum(dlpd.values()) / max(len(contrib), 1)
    key = lambda pid: f"{pieces[pid].kind}-{pieces[pid].nominal_d:.1f}"
    credit: dict[str, float] = {}
    rows = []
    for f, test in st.flags:
        pid = value = None
        if test is not None:
            k, sign = test
            pid = next((p for p, a in sorted(contrib.items()) if a == f.target and key(p) == k), None)
        if pid is not None:
            minus = [(p, m) for p, m in data if p.piece_id != pid]
            piece_dlpd = delta_lpd(full, heldout_lpds(_fit(st, pieces, minus, cfg, rng, st.inbox), st.escrow), cfg.lpd_clip)
            value = sign * (piece_dlpd - baseline)
            credit[f.flagger] = credit.get(f.flagger, 0.0) + value
        rows.append({"round": r, "site": st.site, **asdict(f), "tested_by": pid, "credit": value})
    res.challenges += rows
    st.chain.append("challenge_credit", {"round": r, "baseline": baseline, "flags": rows})
    return credit


UNMET_QUESTIONS = {"position": "Is there a plate-position error the model does not explain?"}


def _trend_z(x: np.ndarray, y: np.ndarray) -> float:
    """t statistic of the correlation between x and y (0 if either is constant)."""
    n = len(x)
    if n < 4 or x.std() == 0 or y.std() == 0:
        return 0.0
    rho = float(np.clip(np.corrcoef(x, y)[0, 1], -0.999999, 0.999999))
    return rho * float(np.sqrt((n - 2) / (1 - rho**2)))


def _unmet_needs(r: int, st: SiteState, pieces, cfg: Config, rng) -> None:
    """Log what the site's model can't explain, for dormant templates (spec 6.7).

    position: standardized residuals of the networked posterior on the site's own
    training measurements, against squared distance from the plate center. The
    physics model has linear plate gradients only, so a trend here is unexplained.
    Only the trend's z-score leaves the site.
    """
    st.unmet_out = []
    if "position" not in cfg.dormant:
        return
    ok = [(p, m) for p, m in st.data["networked"] if m.status == "ok"]
    if len(ok) < 4:
        return
    post = _fit(st, pieces, st.data["networked"], cfg, rng, st.inbox)
    resid = []
    for p, m in ok:
        mean, sd = post.predict(p)
        resid.append((m.measured_d - mean) / sd)
    x = PieceArrays.from_pieces([p for p, _ in ok])
    z = _trend_z((x.u**2 + x.v**2) / 2, np.array(resid))
    if abs(z) >= cfg.unmet_z:
        entry = {"template": "position", "question": UNMET_QUESTIONS["position"], "z": z}
        st.unmet_out.append(entry)
        st.unmet["position"] = st.unmet.get("position", 0) + 1
        st.chain.append("unmet_need", {"round": r, **entry})


def _spawn(r: int, st: SiteState, cfg: Config, res: Results) -> None:
    """Count incoming unmet needs; wake any dormant template that reached the threshold."""
    for _, msg in sorted(st.inbox.items()):
        if msg.round == r:
            for u in msg.unmet_needs:
                st.unmet[u["template"]] = st.unmet.get(u["template"], 0) + 1
    roster = st.roster
    for t in cfg.dormant:
        if t in roster.cred or t in roster.retired or st.unmet.get(t, 0) < cfg.spawn_threshold:
            continue
        roster.wake(t)
        res.spawned.append({"round": r, "site": st.site, "agent": t, "unmet": st.unmet[t]})
        st.chain.append("spawn", {"round": r, "agent": t, "unmet": st.unmet[t], "credibility": roster.cred})


def _broadcast(r: int, sites: dict[str, SiteState], pieces, cfg: Config, rng) -> None:
    """Each site sends the shared-parameter summary of its own data only (no echo of others' messages)."""
    outgoing = {}
    for s, st in sites.items():
        local = _fit(st, pieces, st.data["networked"], cfg, rng)
        summ, _, _ = local.summary("shared")
        if s in cfg.bad_sites:
            summ = _corrupt(summ)
        outgoing[s] = Message(s, r, summ, dict(st.roster.cred), [], list(st.unmet_out))
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
            res.predictions.append({
                "round": r, "site": st.site, "arm": arm, "piece_id": p.piece_id, "kind": p.kind,
                "nominal_d": p.nominal_d, "measured_d": m.measured_d, "mean": float(mean),
                "lo": float(lo), "hi": float(hi), "truth": st.truth.get(p.piece_id),
            })
        res.scores.append({
            "round": r, "site": st.site, "arm": arm,
            "mae": float(np.mean(errs)), "lpd": float(np.mean(lpds)), "cov90": float(np.mean(inside)),
            "mae_truth": float(np.mean(terrs)) if terrs else None,  # sim only: model error without noise
            "n_train": sum(1 for _ in st.data[arm]), "n_heldout": len(ok),
            "n_heldout_failed": sum(1 for _, m in st.escrow if m.status == "failed"),
        })
