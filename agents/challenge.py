"""Challenge round (docs/spec/03-architecture.md, 6.5 step 3).

One round, between propose and clear. Each agent may flag one other agent's
proposal with a reason:

  "redundant with mine"                  the same piece is in the flagger's own winning proposals
  "already predictable from my evidence" the flagger's posterior expects to learn almost nothing
                                         from it (expected information gain below `eig_floor`)

Only proposals that would win a slot are worth flagging, so each agent looks at
the others' top `allocate(pool, cred)[b]` proposals. Flaggers go in order of
credibility (ties by name); a piece is flagged at most once, and an agent can't
call a piece redundant with its own copy if that copy is already flagged.

Flagged pieces lose bid weight: they move to the end of their owner's ranked
list, so the owner fills its slots with its top surviving proposals and the
flagged piece only prints if the owner has slots to spare.

Whether a flag holds up is scored on held-out data after printing (see
`arms/experiment.py`, `_challenge_credit`). `judged_by` says which printed
piece tests each flag:
  - the flagged piece itself if it printed anyway (the flag says it adds little,
    so the flagger gains if its held-out contribution is below the round's average);
  - otherwise the piece that took its slot (the flagger gains if that one is above average).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from agents.auction import allocate
from agents.selection import candidate_eig
from model.posterior import ParticlePosterior
from plates.library import Candidate

REDUNDANT = "redundant with mine"
PREDICTABLE = "already predictable from my evidence"


@dataclass(frozen=True)
class Flag:
    flagger: str
    target: str     # agent whose proposal is flagged
    piece: str      # candidate key
    reason: str
    eig: float | None = None  # flagger's expected information gain, for PREDICTABLE


def challenge(
    pool: int,
    cred: dict[str, float],
    proposals: dict[str, list[Candidate]],
    posts: dict[str, ParticlePosterior | None],
    eig_floor: float,
) -> list[Flag]:
    """At most one flag per agent. `posts[agent]` is that agent's own posterior (None: it has none)."""
    alloc = allocate(pool, cred)
    winning = {a: [c.key for c in proposals.get(a, [])[: alloc[a]]] for a in cred}
    flagged: set[tuple[str, str]] = set()   # (target agent, piece key)
    flags = []
    for a in sorted(cred, key=lambda a: (-cred[a], a)):
        mine = [k for k in winning[a] if (a, k) not in flagged]
        others = [(b, k) for b in sorted(cred) if b != a for k in winning[b] if (b, k) not in flagged]
        if not others:
            continue
        dup = [(b, k) for b, k in others if k in mine]
        if dup:
            b, k = dup[0]
            flags.append(Flag(a, b, k, REDUNDANT))
            flagged.add((b, k))
            continue
        post = posts.get(a)
        if post is None:
            continue
        by_key = {c.key: c for b, _ in others for c in proposals[b]}
        g = candidate_eig(post, [by_key[k] for _, k in others])
        j = int(g.argmin())
        if g[j] < eig_floor:
            b, k = others[j]
            flags.append(Flag(a, b, k, PREDICTABLE, float(g[j])))
            flagged.add((b, k))
    return flags


def demote(proposals: dict[str, list[Candidate]], flags: list[Flag]) -> dict[str, list[Candidate]]:
    """Move each flagged piece to the end of its owner's list (first copy only)."""
    out = {}
    for b, props in proposals.items():
        hit = {f.piece for f in flags if f.target == b}
        keep, moved = [], []
        for c in props:
            if c.key in hit:
                moved.append(c)
                hit.discard(c.key)
            else:
                keep.append(c)
        out[b] = keep + moved
    return out


def _minus(a: list[str], b: list[str]) -> list[str]:
    """Multiset difference a - b, in the order of a."""
    left, out = Counter(b), []
    for x in a:
        if left[x]:
            left[x] -= 1
        else:
            out.append(x)
    return out


def judged_by(
    pool: int,
    cred: dict[str, float],
    before: dict[str, list[Candidate]],
    after: dict[str, list[Candidate]],
    flag: Flag,
) -> tuple[str, int] | None:
    """(piece key printed for `flag.target`, sign) that tests the flag, or None if nothing does.

    sign -1: the flagged piece printed anyway; sign +1: the piece that replaced it.
    """
    n = allocate(pool, cred)[flag.target]
    old = [c.key for c in before.get(flag.target, [])[:n]]
    new = [c.key for c in after.get(flag.target, [])[:n]]
    if flag.piece in new:
        return flag.piece, -1
    displaced, added = _minus(old, new), _minus(new, old)
    if flag.piece in displaced and displaced.index(flag.piece) < len(added):
        return added[displaced.index(flag.piece)], +1
    return None
