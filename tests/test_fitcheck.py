import pickle

from eval.fitcheck import load_checks, score
from measure.rehearsal import rehearsal_printers
from arms.experiment import Config, run_experiment
from run import SITES

TH = {"press_below": 0.0, "slip": [0.05, 0.15], "loose_above": 0.2}


def test_fitcheck_reads_csv_and_scores_every_arm(tmp_path):
    ckpt = tmp_path / "receipts" / "state.pkl"
    run_experiment(rehearsal_printers(SITES, tmp_path), SITES, Config(rounds=1, n_particles=300),
                   chain_dir=str(tmp_path / "receipts"), checkpoint=str(ckpt))
    state = pickle.loads(ckpt.read_bytes())
    seed = [p for p in state["pieces"].values() if p.piece_id.startswith("resin-seed-")]
    pin = next(p for p in seed if p.kind == "pin")
    hole = next(p for p in seed if p.kind == "hole")
    (tmp_path / "scans" / "resin" / "resin-seed-fitcheck.csv").write_text(
        "pin_row,pin_col,hole_row,hole_col,fit\n"
        f"{pin.slot[0]},{pin.slot[1]},{hole.slot[0]},{hole.slot[1]},loose\n"
        f"{hole.slot[0]},{hole.slot[1]},{pin.slot[0]},{pin.slot[1]},loose\n"   # pin and hole swapped: skipped
        "9,9,0,0,slip\n")                                                    # no such piece: skipped
    checks = load_checks(tmp_path / "scans", state)
    assert len(checks) == 1 and checks[0]["site"] == "resin"
    r = score(state, checks, {"resin": TH, "pla": TH})
    row = r["rows"][0]
    assert {row["isolated"], row["networked"], row["oracle"], row["scanner"]} <= {"press", "slip", "loose"}
    assert set(r["agreement"]) == {"isolated", "networked", "oracle", "scanner"}
