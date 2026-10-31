"""Site agents. Each agent = an evidence filter + a prior + a proposal rule.

Agents that share an evidence filter share one posterior, so a site does at
most two posterior fits per round for proposals ("all" and "seed").

| Agent        | Evidence                         | Messages in | Proposal rule                          |
|--------------|----------------------------------|-------------|----------------------------------------|
| physics      | all site measurements            | yes         | information gain on site parameters    |
| calibration  | seed plate only                  | no          | total information gain                 |
| geometry     | all site measurements            | yes         | information gain on size_coef          |
| empirical    | all site measurements            | yes         | information gain x residual size by bin|
| printability | print outcomes (ok / failed)     | no          | uncertainty about failing to print     |
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from agents.selection import greedy_batch
from contracts import Measurement, Piece
from model.posterior import ParticlePosterior
from plates.library import Candidate, candidates, print_cost


@dataclass(frozen=True)
class AgentSpec:
    name: str
    evidence: str            # "all" | "seed" | "outcomes"
    receives_messages: bool


AGENTS = [
    AgentSpec("physics", "all", True),
    AgentSpec("calibration", "seed", False),
    AgentSpec("geometry", "all", True),
    AgentSpec("empirical", "all", True),
    AgentSpec("printability", "outcomes", False),
]
AGENT_NAMES = [a.name for a in AGENTS]


def propose(
    agent: str,
    k: int,
    posts: dict[str, ParticlePosterior],
    data: list[tuple[Piece, Measurement]],
    discount: float,
) -> list[Candidate]:
    """Ranked proposals for one agent. `posts` maps evidence filter -> fitted posterior."""
    if agent == "physics":
        post = posts["all"]
        focus = [n for n, t in zip(post.names, post.tags) if t == "site" and n != "sigma_meas"]
        picks = greedy_batch(post, k, score="focus", focus=focus, discount=discount)
    elif agent == "calibration":
        picks = greedy_batch(posts["seed"], k, discount=discount)
    elif agent == "geometry":
        picks = greedy_batch(posts["all"], k, score="focus", focus=["size_coef"], discount=discount)
    elif agent == "empirical":
        return _empirical(posts["all"], k, data, discount)
    elif agent == "printability":
        return _printability(k, data, discount)
    else:
        raise ValueError(f"unknown agent {agent!r}")
    return [c for c, _ in picks]


def _bin(kind: str, d: float) -> tuple[str, int]:
    return kind, int(d)  # 1 mm bins per kind


def _empirical(post: ParticlePosterior, k: int, data, discount: float) -> list[Candidate]:
    """Information gain, weighted up where this site's residuals are large."""
    ok = [(p, m) for p, m in data if m.status == "ok"]
    zbin: dict[tuple[str, int], list[float]] = defaultdict(list)
    if ok:
        mu, s = post.predictive_components([p for p, _ in ok])
        w = np.exp(post.logw)
        mean = w @ mu
        sd = np.sqrt(w @ (mu - mean) ** 2 + w @ s**2)
        for (p, m), mn, sdv in zip(ok, mean, sd):
            zbin[_bin(p.kind, p.nominal_d)].append(abs(m.measured_d - mn) / sdv)
    picks = greedy_batch(post, 4 * k, discount=discount)
    boost = {c.key: 1.0 + float(np.mean(zbin[_bin(c.kind, c.nominal_d)])) if zbin.get(_bin(c.kind, c.nominal_d)) else 1.0
             for c, _ in picks}
    ranked = sorted(picks, key=lambda cs: -cs[1] * boost[cs[0].key])
    return [c for c, _ in ranked[:k]]


def _printability(k: int, data, discount: float) -> list[Candidate]:
    """Pieces whose print success is most uncertain: Beta(1+fail, 1+ok) per 0.5 mm bin."""
    cands = candidates()
    key = lambda kind, d: (kind, round(d * 2) / 2)
    fails, oks = defaultdict(int), defaultdict(int)
    for p, m in data:
        (fails if m.status == "failed" else oks)[key(p.kind, p.nominal_d)] += 1
    cost = np.array([print_cost(c) for c in cands])
    mult = 1.0 - discount * cost / max(cost.max(), 1e-9)
    added: dict = defaultdict(int)
    out = []
    for _ in range(k):
        best, best_sc = None, -1.0
        for c, mlt in zip(cands, mult):
            b = key(c.kind, c.nominal_d)
            a, bb = 1 + fails[b], 1 + oks[b] + added[b]
            p = a / (a + bb)
            sc = mlt * p * (1 - p) / (a + bb + 1)  # expected shrink of the Beta variance
            if sc > best_sc:
                best, best_sc = c, sc
        out.append(best)
        added[key(best.kind, best.nominal_d)] += 1
    return out
