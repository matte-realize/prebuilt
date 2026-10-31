"""Credibility from held-out improvement (docs/spec/03-architecture.md, 6.6–6.7).

Agents:  c_a <- c_a * exp(eta * dLPD_a), normalized over active agents.
Senders: same update, but clipped to [0, 1] rather than normalized. The value
is the tempering weight on that sender's messages, so a site with a single
peer can still lose trust in it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def update_agents(cred: dict[str, float], dlpd: dict[str, float], eta: float) -> dict[str, float]:
    # Log space: a large dLPD must not overflow exp().
    logc = {a: math.log(max(c, 1e-300)) + eta * dlpd.get(a, 0.0) for a, c in cred.items()}
    m = max(logc.values())
    raw = {a: math.exp(v - m) for a, v in logc.items()}
    total = sum(raw.values())
    return {a: max(v / total, 1e-300) for a, v in raw.items()}


def update_senders(trust: dict[str, float], dlpd: dict[str, float], eta: float) -> dict[str, float]:
    return {s: math.exp(min(0.0, math.log(max(t, 1e-300)) + eta * dlpd.get(s, 0.0))) for s, t in trust.items()}


@dataclass
class Roster:
    """Active agents and their credibility. An agent below `floor` for two rounds in a row retires;
    a dormant agent `wake`s with uniform credibility (docs/spec/03-architecture.md 6.7)."""
    cred: dict[str, float]
    floor: float
    strikes: dict[str, int] = field(default_factory=dict)
    retired: list[str] = field(default_factory=list)

    @classmethod
    def uniform(cls, agents: list[str], floor: float) -> Roster:
        return cls({a: 1.0 / len(agents) for a in agents}, floor)

    def step(self, dlpd: dict[str, float], eta: float) -> list[str]:
        """Apply one round of credit. Returns agents retired this round."""
        self.cred = update_agents(self.cred, dlpd, eta)
        newly = []
        for a, c in list(self.cred.items()):
            self.strikes[a] = self.strikes.get(a, 0) + 1 if c < self.floor else 0
            if self.strikes[a] >= 2 and len(self.cred) > 1:
                newly.append(a)
        for a in newly:
            del self.cred[a]
            self.retired.append(a)
        if newly:
            total = sum(self.cred.values())
            self.cred = {a: c / total for a, c in self.cred.items()}
        return newly

    def wake(self, agent: str) -> None:
        """A dormant agent joins with uniform credibility: 1/(n+1), the others scaled to share the rest."""
        n = len(self.cred)
        self.cred = {a: c * n / (n + 1) for a, c in self.cred.items()}
        self.cred[agent] = 1.0 / (n + 1)
        self.strikes[agent] = 0
