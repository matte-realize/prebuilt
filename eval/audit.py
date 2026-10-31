"""Privacy audit: replay receipt chains and check every boundary crossing.

Needs only the chains, not any site's raw data. Checks:
  1. each site's chain is intact (hash links, payload hashes);
  2. every message_out passed the closed `Message` schema;
  3. every message_in matches a message_out in the sender's chain, byte for byte,
     and references that entry's hash.

    python -m eval.audit receipts/resin.jsonl receipts/pla.jsonl
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from network.protocol import BoundaryViolation, deserialize
from receipts.chain import ReceiptChain


@dataclass
class AuditReport:
    chains_ok: dict[str, bool] = field(default_factory=dict)
    crossings: int = 0
    rejected_at_boundary: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.chains_ok.values()) and not self.problems


def audit(chains: list[ReceiptChain]) -> AuditReport:
    rep = AuditReport()
    outs: dict[str, dict] = {}
    for c in chains:
        rep.chains_ok[c.site] = c.verify()
        for e in c.entries():
            if e["kind"] == "message_out":
                rep.crossings += 1
                try:
                    msg = deserialize(e["payload"]["wire"])
                    if msg.sender_site != c.site:
                        rep.problems.append(f"{c.site} seq {e['seq']}: sender_site {msg.sender_site!r} != chain site")
                except (BoundaryViolation, ValueError) as err:
                    rep.problems.append(f"{c.site} seq {e['seq']}: outside schema: {err}")
                outs[e["hash"]] = e
            elif e["kind"] == "boundary_reject":
                rep.rejected_at_boundary += 1
    for c in chains:
        for e in c.entries():
            if e["kind"] != "message_in":
                continue
            src = outs.get(e["payload"]["sender_entry"])
            if src is None:
                rep.problems.append(f"{c.site} seq {e['seq']}: message_in with no matching message_out")
            elif src["payload"]["wire"] != e["payload"]["wire"] or src["payload"]["to"] != c.site:
                rep.problems.append(f"{c.site} seq {e['seq']}: message_in differs from what was sent")
    return rep


def main(paths: list[str]) -> int:
    chains = []
    for p in paths:
        site = p.rsplit("/", 1)[-1].removesuffix(".jsonl")
        chains.append(ReceiptChain(site, p))
    rep = audit(chains)
    print(f"chains intact: {rep.chains_ok}")
    print(f"boundary crossings: {rep.crossings}, rejected at boundary: {rep.rejected_at_boundary}")
    for p in rep.problems:
        print("PROBLEM:", p)
    print("PASS" if rep.passed else "FAIL")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
