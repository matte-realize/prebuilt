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


def test_failed_plate_is_reprinted_once_then_dropped(tmp_path):
    from contracts import Measurement
    from measure.real import RealPrinter
    from plates.seed import seed_plate

    plate = seed_plate("resin")
    calls = []

    class Flaky(RealPrinter):
        def _measure_once(self, plate):  # stands in for scanning; writes the scan files the operator would
            calls.append(1)
            for s in ("holes", "pins"):
                (self.scan_dir / f"{plate.plate_id}-{s}.png").write_bytes(b"x")
            return [Measurement(p.piece_id, plate.plate_id, plate.site, None if i % 4 else 1.0,
                                "failed" if i % 4 else "ok", "scanner") for i, p in enumerate(plate.pieces)]

    ms = Flaky("resin", str(tmp_path), ask=lambda q: "", plate_dir=tmp_path, failed_plate_fraction=0.5).print_and_measure(plate)
    assert len(calls) == 2 and all(m.status == "failed" for m in ms)
    assert (tmp_path / f"{plate.plate_id}.failed1-holes.png").exists()
    ok = RealPrinter("resin", str(tmp_path), plate_dir=tmp_path, failed_plate_fraction=0.8)
    ok._measure_once = lambda plate: [Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "scanner")
                                      if i % 4 else Measurement(p.piece_id, plate.plate_id, plate.site, 1.0, "ok", "scanner")
                                      for i, p in enumerate(plate.pieces)]
    assert sum(m.status == "ok" for m in ok.print_and_measure(plate)) == 6   # 75% failed is under 80%: kept
