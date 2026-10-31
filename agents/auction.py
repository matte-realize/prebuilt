"""Fixed clearing rule. It allocates slots only and never chooses content."""
from __future__ import annotations

import math

from plates.library import Candidate


def allocate(pool: int, cred: dict[str, float]) -> dict[str, int]:
    """Split `pool` slots in proportion to credibility, largest-remainder rounding.

    Ties on the remainder break by agent name so the rule is deterministic.
    """
    total = sum(cred.values())
    if pool <= 0 or total <= 0:
        return {a: 0 for a in cred}
    quota = {a: pool * c / total for a, c in cred.items()}
    alloc = {a: math.floor(q) for a, q in quota.items()}
    left = pool - sum(alloc.values())
    for a in sorted(quota, key=lambda a: (-(quota[a] - alloc[a]), a))[:left]:
        alloc[a] += 1
    return alloc


def clear(
    pool: int, cred: dict[str, float], proposals: dict[str, list[Candidate]]
) -> tuple[list[tuple[Candidate, str]], dict[str, int]]:
    """Each agent fills its slots with its own top proposals. Returns (piece, agent) pairs."""
    alloc = allocate(pool, cred)
    chosen = []
    for agent in sorted(alloc):
        chosen += [(c, agent) for c in proposals.get(agent, [])[: alloc[agent]]]
    return chosen, alloc
