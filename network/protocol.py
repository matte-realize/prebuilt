"""The site boundary. `Message` is the only thing that crosses it.

The boundary is enforced here: `serialize` and `deserialize` both validate
against a closed schema and raise `BoundaryViolation` on anything else.
Unmet-needs entries (spec 6.3) carry a dormant-agent template, a short
question, and one anonymized residual summary (a z-score); nothing else.
Every crossing is written to both sites' receipt chains, and every
rejection to the sender's chain, so the privacy claim can be checked by
replaying receipts (`eval/audit.py`).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, fields

import numpy as np

from agents.agents import DORMANT_NAMES
from contracts import Message
from model import physics
from receipts.chain import ReceiptChain, canonical

FIELDS = {f.name for f in fields(Message)}
SHARED_PARAMS = {s.name for s in physics.SHARED}   # process-agnostic only
MAX_HYPOTHESES, MAX_HYPOTHESIS_LEN, MAX_CRED_KEYS = 20, 1000, 64
OPTIONAL = {"unmet_needs"}                          # absent in chains written before it existed
UNMET_KEYS, MAX_UNMET, MAX_QUESTION_LEN = {"template", "question", "z"}, 10, 200


class BoundaryViolation(Exception):
    pass


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(d: dict) -> Message:
    """Check a message dict against the closed schema. Returns the typed Message."""
    if not isinstance(d, dict) or not (FIELDS - OPTIONAL <= set(d) <= FIELDS):
        raise BoundaryViolation(f"fields must be exactly {sorted(FIELDS)}, got {sorted(d) if isinstance(d, dict) else type(d)}")
    if not isinstance(d["sender_site"], str) or not d["sender_site"]:
        raise BoundaryViolation("sender_site must be a non-empty string")
    if not isinstance(d["round"], int) or isinstance(d["round"], bool) or d["round"] < 0:
        raise BoundaryViolation("round must be a non-negative int")

    sp = d["shared_params"]
    if not isinstance(sp, dict):
        raise BoundaryViolation("shared_params must be a dict")
    for k, v in sp.items():
        if k not in SHARED_PARAMS:
            raise BoundaryViolation(f"shared_params[{k!r}] is not a process-agnostic parameter")
        if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(_finite(x) for x in v) and v[1] > 0):
            raise BoundaryViolation(f"shared_params[{k!r}] must be (mean, variance>0)")

    cred = d["credibility"]
    if not isinstance(cred, dict) or len(cred) > MAX_CRED_KEYS:
        raise BoundaryViolation("credibility must be a small dict")
    if not all(isinstance(k, str) and _finite(v) for k, v in cred.items()):
        raise BoundaryViolation("credibility must map str -> finite float")

    hyp = d["hypotheses"]
    if not isinstance(hyp, list) or len(hyp) > MAX_HYPOTHESES:
        raise BoundaryViolation("hypotheses must be a short list")
    if not all(isinstance(h, str) and len(h) <= MAX_HYPOTHESIS_LEN for h in hyp):
        raise BoundaryViolation("hypotheses must be short strings")

    unmet = d.get("unmet_needs", [])
    if not isinstance(unmet, list) or len(unmet) > MAX_UNMET:
        raise BoundaryViolation("unmet_needs must be a short list")
    for u in unmet:
        if not isinstance(u, dict) or set(u) != UNMET_KEYS:
            raise BoundaryViolation(f"unmet_needs entries must have exactly {sorted(UNMET_KEYS)}")
        if u["template"] not in DORMANT_NAMES:
            raise BoundaryViolation(f"unmet_needs template {u['template']!r} is not a dormant agent")
        if not isinstance(u["question"], str) or len(u["question"]) > MAX_QUESTION_LEN:
            raise BoundaryViolation("unmet_needs question must be a short string")
        if not _finite(u["z"]):
            raise BoundaryViolation("unmet_needs z must be a finite number")

    return Message(
        sender_site=d["sender_site"],
        round=d["round"],
        shared_params={k: (float(v[0]), float(v[1])) for k, v in sp.items()},
        credibility={k: float(v) for k, v in cred.items()},
        hypotheses=list(hyp),
        unmet_needs=[{"template": u["template"], "question": u["question"], "z": float(u["z"])} for u in unmet],
    )


def serialize(msg: Message | dict, chain: ReceiptChain | None = None) -> str:
    d = asdict(msg) if isinstance(msg, Message) else msg
    try:
        validate(d)
    except BoundaryViolation as e:
        if chain is not None:
            chain.append("boundary_reject", {"reason": str(e), "fields": sorted(d) if isinstance(d, dict) else None})
        raise
    return canonical(d)


def deserialize(s: str) -> Message:
    return validate(json.loads(s))


def send(msg: Message, sender: ReceiptChain, receiver: ReceiptChain) -> Message:
    """Cross the boundary once: validate, log on both chains, return what the receiver sees."""
    wire = serialize(msg, sender)
    out = sender.append("message_out", {"to": receiver.site, "wire": wire, "receiver_head": receiver.head()})
    received = deserialize(wire)
    receiver.append("message_in", {"from": sender.site, "wire": wire, "sender_entry": out["hash"]})
    return received


def likelihood_factor(msg: Message) -> tuple[dict[str, float], np.ndarray]:
    """Turn a sender's posterior summary into a factor on shared parameters.

    The sender's posterior already contains the shared prior; dividing it out
    (Gaussian approximation) keeps the receiver from counting the prior once
    per sender. Parameters the sender hasn't learned anything about are dropped.
    """
    prior = {s.name: s for s in physics.SHARED}
    means, precs = {}, []
    for k, (m, v) in msg.shared_params.items():
        pv = prior[k].prior_std ** 2
        prec = 1.0 / v - 1.0 / pv
        if prec <= 0.05 / pv:
            continue
        means[k] = (m / v - prior[k].prior_mean / pv) / prec
        precs.append(prec)
    return means, np.diag(1.0 / np.array(precs)) if precs else np.zeros((0, 0))
