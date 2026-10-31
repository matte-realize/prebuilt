"""Append-only, hash-chained receipt log. One chain per site.

Each entry commits to its payload and to the previous entry's hash, so any
edit, deletion, or reordering breaks `verify()`.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def _default(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "tolist"):  # numpy arrays and scalars
        return obj.tolist()
    raise TypeError(f"not serializable: {type(obj).__name__}")


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _entry_hash(e: dict) -> str:
    return sha256(canonical({k: v for k, v in e.items() if k != "hash"}))


class ReceiptChain:
    def __init__(self, site: str, path: str | Path | None = None):
        """`path=None` keeps the chain in memory (simulation sweeps)."""
        self.site = site
        self.path = Path(path) if path is not None else None
        self._mem: list[str] = []
        self._seq = 0
        self._head = GENESIS
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path is not None and self.path.exists():
            for e in self.entries():
                self._seq, self._head = e["seq"] + 1, e["hash"]

    def head(self) -> str:
        return self._head

    def append(self, kind: str, payload: Any) -> dict:
        payload = json.loads(canonical(payload))  # store exactly what was hashed
        e = {
            "seq": self._seq,
            "ts": time.time(),
            "site": self.site,
            "kind": kind,
            "payload": payload,
            "payload_hash": sha256(canonical(payload)),
            "prev_hash": self._head,
        }
        e["hash"] = _entry_hash(e)
        if self.path is None:
            self._mem.append(canonical(e))
        else:
            with self.path.open("a") as f:
                f.write(canonical(e) + "\n")
        self._seq, self._head = self._seq + 1, e["hash"]
        return e

    def entries(self) -> list[dict]:
        if self.path is None:
            return [json.loads(line) for line in self._mem]
        with self.path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

    def verify(self) -> bool:
        prev = GENESIS
        for i, e in enumerate(self.entries()):
            if (
                e["seq"] != i
                or e["site"] != self.site
                or e["prev_hash"] != prev
                or e["payload_hash"] != sha256(canonical(e["payload"]))
                or e["hash"] != _entry_hash(e)
            ):
                return False
            prev = e["hash"]
        return True
