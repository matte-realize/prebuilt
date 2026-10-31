import json

from contracts import Measurement
from receipts.chain import GENESIS, ReceiptChain


def _fill(chain, n=100):
    for i in range(n):
        chain.append("measurement", Measurement(f"p{i}", "plate0", chain.site, 5.0 + i * 0.01, "ok", "sim"))


def test_chain_verifies(tmp_path):
    c = ReceiptChain("resin", tmp_path / "resin.jsonl")
    assert c.head() == GENESIS
    _fill(c)
    assert c.verify()
    assert c.entries()[0]["prev_hash"] == GENESIS


def test_tamper_detected(tmp_path):
    path = tmp_path / "resin.jsonl"
    c = ReceiptChain("resin", path)
    _fill(c)
    lines = path.read_text().splitlines()
    e = json.loads(lines[42])
    e["payload"]["measured_d"] = 9.99
    lines[42] = json.dumps(e)
    path.write_text("\n".join(lines) + "\n")
    assert not c.verify()


def test_deletion_detected(tmp_path):
    path = tmp_path / "resin.jsonl"
    c = ReceiptChain("resin", path)
    _fill(c, 10)
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:3] + lines[4:]) + "\n")
    assert not c.verify()


def test_reopen_continues_chain(tmp_path):
    path = tmp_path / "pla.jsonl"
    c = ReceiptChain("pla", path)
    _fill(c, 5)
    head = c.head()
    c2 = ReceiptChain("pla", path)
    assert c2.head() == head
    e = c2.append("plate", {"plate_id": "plate1"})
    assert e["prev_hash"] == head and e["seq"] == 5
    assert c2.verify()
