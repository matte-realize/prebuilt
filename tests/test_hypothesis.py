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
