import json
import pickle

from agents.hypothesis import messages, parse, run
from arms.experiment import Config, run_experiment
from receipts.chain import ReceiptChain
from run import SITES
from sim.reference import make_world

REPLY = """Here you go:
[{"effect": "radial over-cure", "evidence": "radial trend z 2.4",
  "test_pieces": [{"kind": "hole", "d": 3.04}, {"kind": "hole", "d": 3.0}, {"kind": "slot", "d": 2},
                  {"kind": "pin", "d": 42}, {"kind": "pin", "d": "x"}], "prediction": "corner holes smaller"},
 {"no_effect": true}]"""


def test_parse_validates_and_snaps():
    (h,) = parse(REPLY)
    assert h["effect"] == "radial over-cure" and h["test_pieces"] == [{"kind": "hole", "d": 3.0}]
    assert parse("no json here") == [] and parse("[not json]") == []


def test_run_records_hypotheses_without_raw_data(tmp_path):
    ckpt = tmp_path / "state.pkl"
    run_experiment(make_world(SITES, 2), SITES, Config(rounds=1, n_particles=300), checkpoint=str(ckpt))
    state = pickle.loads(ckpt.read_bytes())
    seen = []
    out = run(state, ask=lambda msgs: seen.append(msgs) or REPLY, out_dir=tmp_path)
    assert set(out) == set(SITES) and all(r["hypotheses"] for r in out.values())
    prompt = json.dumps(seen)
    raw = [m for st in state["sites"].values() for _, m in st.data["networked"] if m.status == "ok"]
    assert not any(m.piece_id in prompt or f"{m.measured_d:.4f}" in prompt for m in raw)
    for s in SITES:
        chain = ReceiptChain(f"{s}-hypotheses", str(tmp_path / f"{s}-hypotheses.jsonl"))
        assert chain.verify() and chain.entries()[-1]["kind"] == "hypothesis"
    assert messages({"x": 1})[0]["role"] == "system"


def test_ping_and_model_discovery_against_a_fake_endpoint(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from agents import hypothesis

    class Fake(BaseHTTPRequestHandler):
        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"data": [{"id": "nvidia/nemotron-test"}]})

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert req["model"] == "nvidia/nemotron-test"
            self._send({"choices": [{"message": {"content": REPLY}}]})

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("PREBUILT_LLM_URL", f"http://127.0.0.1:{srv.server_port}/v1")
    monkeypatch.delenv("PREBUILT_LLM_MODEL", raising=False)
    try:
        assert hypothesis.model_name() == "nvidia/nemotron-test"
        assert hypothesis.ping() == 0
    finally:
        srv.shutdown()
