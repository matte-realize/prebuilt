"""The real-printer loop end to end: rehearsal with simulated scans, crash and resume, failed
and vetoed plates, and fallback tier B (one site simulated)."""
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


def test_tier_b_one_real_site_one_simulated(tmp_path):
    from measure.real import RealPrinter
    from run import real_printers
    from sim.reference import SimPrinter

    cfg = Config(rounds=1, n_particles=300, sim_sites=("pla",), failed_plate_fraction=0.5)
    printers = real_printers(cfg, str(tmp_path / "scans"))
    assert isinstance(printers["resin"], RealPrinter) and isinstance(printers["pla"], SimPrinter)
    printers["resin"] = rehearsal_printers({"resin": "resin"}, tmp_path)["resin"]  # operator stand-in
    res = run_experiment(printers, SITES, cfg, chain_dir=str(tmp_path / "receipts"))
    assert {r["site"] for r in res.scores} == set(SITES) and audit(list(res.chains.values())).passed
    assert res.config["sim_sites"] == ("pla",) or res.config["sim_sites"] == ["pla"]


def test_crash_mid_round_resumes_with_valid_chains_and_same_results(tmp_path):

    class Crash(Exception):
        pass

    def printers(base, crash_on=None):
        ps = rehearsal_printers(SITES, base)
        if crash_on:
            orig = ps["pla"].print_and_measure

            def flaky(plate, orig=orig):
                if plate.plate_id == crash_on and not flaky.done:
                    flaky.done = True
                    raise Crash  # e.g. a scan the scanner can't read, or Ctrl-C
                return orig(plate)
            flaky.done = False
            ps["pla"].print_and_measure = flaky
        return ps

    def run(base, ps):
        return run_experiment(ps, SITES, Config(rounds=2, n_particles=300), chain_dir=str(base / "receipts"),
                              checkpoint=str(base / "receipts" / "state.pkl"))

    clean = run(tmp_path / "clean", printers(tmp_path / "clean"))
    crashed = tmp_path / "crashed"
    ps = printers(crashed, crash_on="pla-r2")
    try:
        run(crashed, ps)
        raise AssertionError("expected the crash")
    except Crash:
        pass
    resumed = run(crashed, printers(crashed))  # a fresh process: new printer objects
    assert audit(list(resumed.chains.values())).passed
    kinds = [e["kind"] for e in resumed.chains["resin"].entries()]
    assert "resume" in kinds
    key = lambda rows: sorted((r["round"], r["site"], r["arm"], round(r["mae"], 12)) for r in rows)
    assert key(resumed.scores) == key(clean.scores)


def test_veto_unreadable_scan_and_excluded_data(tmp_path):
    import cv2
    import numpy as np
    from arms.experiment import _ingest
    from measure.rehearsal import RehearsalPrinter
    from plates.seed import seed_plate
    from sim.reference import make_world

    plate = seed_plate("resin")
    # Veto: nothing printed, the event is reported, and none of it becomes data.
    p = RehearsalPrinter(make_world({"resin": "resin"}, 0)["resin"], tmp_path / "a", tmp_path / "plates")
    p.ask = lambda q: "veto supports won't fit" if "approve" in q else ""
    assert p.prepare(plate)["vetoed"]
    ms = p.print_and_measure(plate)
    assert {m.method for m in ms} == {"failed-plate"} and p.pop_events()[0]["event"].startswith("vetoed")
    st = _init_site(tmp_path)
    _ingest(plate, ms, st)
    assert not st.escrow and not any(st.data.values())
    # Unreadable scan: the operator is asked again instead of the run crashing.
    from measure.real import RealPrinter
    scans = tmp_path / "b"
    answers = iter(["", ""])
    r = RealPrinter("resin", str(scans), ask=lambda q: next(answers), plate_dir=tmp_path / "plates")
    scans.mkdir(exist_ok=True)
    blank = np.full((400, 400), 255, np.uint8)
    for s in ("holes", "pins"):
        cv2.imwrite(str(scans / f"{plate.plate_id}-{s}.png"), blank)
    calls = []
    real_read = r._read_scans
    def read(plate, base):
        calls.append(1)
        if len(calls) == 1:
            return real_read(plate, base)  # blank image: no fiducials, raises ValueError
        return []
    r._read_scans = read
    assert r._measure_once(plate) == [] and len(calls) == 2


def _init_site(tmp_path):
    from arms.experiment import ARMS, SiteState
    from receipts.chain import ReceiptChain
    return SiteState("resin", "resin", ReceiptChain("resin"), {a: [] for a in ARMS})


def test_no_scanner_every_piece_measured_by_hand(tmp_path):
    import csv
    from measure.real import RealPrinter
    from plates.seed import seed_plate

    plate = seed_plate("resin")
    sheet = tmp_path / f"{plate.plate_id}-manual.csv"
    answers = []

    def ask(q):  # operator fills half the sheet, presses Enter, then finishes it
        answers.append(q)
        rows = list(csv.DictReader(open(sheet)))
        n = len(rows) // 2 if len(answers) == 1 else len(rows)
        for i, r in enumerate(rows[:n]):
            r["measured_d"], r["status"] = ("", "failed") if i == 0 else ("3.05", "")
        with open(sheet, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return ""

    pr = RealPrinter("resin", str(tmp_path), ask=ask, plate_dir=tmp_path)
    ms = pr.print_and_measure(plate)
    assert len(answers) == 2 and len(ms) == len(plate.pieces)
    assert sum(m.status == "failed" for m in ms) == 1 and all(m.method == "caliper" for m in ms)
    assert (tmp_path / f"{plate.plate_id}-measurements.json").exists()
    assert pr.pop_events()[0]["event"] == "measured by hand, no scans"


def test_hand_sheet_skip_is_not_data_and_not_a_failure(tmp_path):
    import csv
    from arms.experiment import NOT_DATA
    from measure.real import NOT_MEASURED, RealPrinter, _failed_fraction, read_manual_sheet
    from plates.seed import seed_plate

    plate = seed_plate("resin")
    sheet = tmp_path / f"{plate.plate_id}-manual.csv"

    def ask(q):  # micrometer only: every pin measured, every hole skipped
        with open(sheet, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["row", "col", "kind", "measured_d", "status"])
            for p in plate.pieces:
                w.writerow([*p.slot, p.kind, "3.0" if p.kind == "pin" else "", "" if p.kind == "pin" else "skip"])
        return ""

    pr = RealPrinter("resin", str(tmp_path), ask=ask, plate_dir=tmp_path, failed_plate_fraction=0.5)
    ms = pr.print_and_measure(plate)  # holes are half the plate: must not trip the reprint rule
    holes = [m for p, m in zip(plate.pieces, ms) if p.kind == "hole"]
    assert holes and all(m.status == "skipped" and m.method == NOT_MEASURED and m.measured_d is None for m in holes)
    assert NOT_MEASURED in NOT_DATA and _failed_fraction(ms) == 0.0
    assert not any(e["event"] == "reprint" for e in pr.pop_events())
    ms, todo = read_manual_sheet(sheet, plate)
    assert todo == []


def test_console_practice_run_headless(tmp_path):
    """The console's runner end to end with a fake operator: approve, fill with simulated readings."""
    import time
    from console.runner import Run, Settings

    run = Run(Settings(resin="real", pla="sim", rounds=1, particles=300, consistency_check=True), tmp_path).start()
    seen = []
    t0 = time.time()
    while run.thread.is_alive() and time.time() - t0 < 120:
        p = run.prompt
        if p is None:
            time.sleep(0.02)
            continue
        seen.append((p.kind, p.plate_id))
        assert p.site == "resin" and p.plate["pieces"]
        if p.kind == "approve":
            run.answer(p.id, "y")
        else:
            rows = run.fill(p.id)
            if p.plate_id.endswith("r1"):  # one skipped piece, typed as a micrometer reading elsewhere
                rows[0]["status"], rows[0]["value"] = "skip", None
                ok = next(r for r in rows[1:] if r["status"] == "ok")
                ok["value"] = ok["value"] * 1000
            run.submit_measurements(p.id, rows, "sim-fill")
        while run.prompt is not None and run.prompt.id == p.id:
            time.sleep(0.01)
    run.thread.join(5)
    assert run.status == "done", run.error + "\n".join(run.log_lines[-30:])
    assert seen == [("approve", "resin-seed"), ("measure", "resin-seed"), ("approve", "resin-r1"), ("measure", "resin-r1")]
    v = run.view()
    assert {(r["site"], r["arm"]) for r in v["scores"]} == {(s, a) for s in ("resin", "pla") for a in ("isolated", "networked", "oracle")}
    assert all(r["mae"] > 0 for r in v["scores"])
    assert all(r["mae_truth"] is None for r in v["scores"] if r["site"] == "resin")  # real site: no hidden truth
    assert v["audit"]["passed"] and v["crossed"]["measurements"] == 0 and v["crossed"]["numbers"] > 0
    assert v["checks"] and v["filled"] == ["resin-seed", "resin-r1"]
    d = run.dir
    for f in ["state.pkl", "results.json", "run.json", "log.txt", "receipts/resin.jsonl", "receipts/pla.jsonl",
              "plates/resin/resin-r1.stl", "scans/resin/resin-r1-manual.csv", "scans/resin/resin-r1-measurements.json"]:
        assert (d / f).exists(), f
    sheet = (d / "scans/resin/resin-r1-manual.csv").read_text()
    assert "skip" in sheet and "sim-fill" in sheet
