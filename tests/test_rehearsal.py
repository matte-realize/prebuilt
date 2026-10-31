"""The real-printer loop end to end, with a simulated printer rendering the scans."""
from arms.experiment import Config, run_experiment
from eval.audit import audit
from measure.rehearsal import rehearsal_printers
from run import SITES


def test_real_loop_runs_and_resumes(tmp_path):
    def run(rounds):
        return run_experiment(rehearsal_printers(SITES, tmp_path), SITES, Config(rounds=rounds, n_particles=300),
                              chain_dir=str(tmp_path / "receipts"), checkpoint=str(tmp_path / "receipts" / "state.pkl"))

    first = run(1)
    assert {r["round"] for r in first.scores} == {1}
    resumed = run(2)  # picks up from the round-1 checkpoint, prints only round 2
    assert {r["round"] for r in resumed.scores} == {1, 2}
    for s in SITES:
        assert sorted(p.name for p in (tmp_path / "scans" / s).glob("*-measurements.json")) == \
            [f"{s}-r1-measurements.json", f"{s}-r2-measurements.json", f"{s}-seed-measurements.json"]
    assert audit(list(resumed.chains.values())).passed
