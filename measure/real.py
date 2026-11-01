"""Real-printer `Printer`: writes plate files, records human approval, waits for scans.

File conventions, per plate, in `scan_dir`:
    {plate_id}-holes.png     backlit scan
    {plate_id}-pins.png      front-lit scan, dark lid
    {plate_id}-caliper.csv   optional spot checks (see measure/manual.py)
    {plate_id}-manual.csv    no scanner: every piece measured by hand (blank sheet written for you)
Measurements are written to {plate_id}-measurements.json and never leave the site.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from pathlib import Path

import cv2

from contracts import Measurement, Plate
from measure.manual import agreement, apply_offsets, load_caliper_csv, sample_for_caliper, scanner_offsets
from measure.scanner import measure_scan
from plates.layout import save_plate
from plates.stl import write_stl

PLATE_DIR = Path(__file__).resolve().parent.parent / "plates" / "out"
# Method of a piece left unmeasured on the hand sheet (status "skipped"); arms.experiment.NOT_DATA.
NOT_MEASURED = "not-measured"


class RealPrinter:
    def __init__(self, site: str, scan_dir: str, ask=input, plate_dir: str | Path = PLATE_DIR,
                 failed_plate_fraction: float | None = None, caliper_checks: int = 10, caliper_min_pairs: int = 3):
        self.site = site
        self.failed_plate_fraction = failed_plate_fraction  # prereg: above this, reprint once
        self.caliper_checks, self.caliper_min_pairs = caliper_checks, caliper_min_pairs
        self.plate_dir = Path(plate_dir)
        self.scan_dir = Path(scan_dir)
        self.scan_dir.mkdir(parents=True, exist_ok=True)
        self.ask = ask
        self.vetoed: set[str] = set()
        self._events: list[dict] = []

    def pop_events(self) -> list[dict]:
        """Reprints, vetoes and dropped plates since the last call, for the receipt chain."""
        ev, self._events = self._events, []
        return ev

    def prepare(self, plate: Plate) -> dict:
        """Write plate files and get printability/safety approval. Returned dict goes on the receipt chain.

        `y` approves. An answer starting with `veto` skips the plate: it isn't printed and the
        round is scored without it. Anything else approves with that edit note logged.
        """
        save_plate(plate, self.plate_dir / self.site / f"{plate.plate_id}.json")
        stl = self.plate_dir / self.site / f"{plate.plate_id}.stl"
        write_stl(plate, stl)
        print(f"\n[{self.site}] {plate.plate_id}: {stl}")
        print(f"  caliper-check slots (row, col): {sample_for_caliper(plate, k=self.caliper_checks, seed=plate.seed)}")
        answer = self.ask(f"[{self.site}] approve {plate.plate_id}? [y / describe an edit / 'veto <reason>'] ").strip()
        vetoed = answer.lower().startswith("veto")
        if vetoed:
            self.vetoed.add(plate.plate_id)
        ok = answer.lower() in ("y", "yes")
        return {"plate_id": plate.plate_id, "approved": not vetoed, "vetoed": vetoed, "note": "" if ok else answer}

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        """Measure the plate. Past the prereg's failed-plate fraction it is reprinted once; if the
        reprint fails too, or the plate was vetoed, every piece is reported with method
        "failed-plate" and the round is scored without it."""
        if plate.plate_id in self.vetoed:
            self._events.append({"plate_id": plate.plate_id, "event": "vetoed, not printed"})
            return self._drop(plate)
        ms = self._measure_once(plate)
        frac = _failed_fraction(ms)
        if self.failed_plate_fraction is None or frac <= self.failed_plate_fraction:
            return ms
        print(f"  [{self.site}] {plate.plate_id}: {frac:.0%} of pieces failed, over the prereg's "
              f"{self.failed_plate_fraction:.0%}. Reprint the same plate file once.")
        stamp = 1
        while any(self.scan_dir.glob(f"{plate.plate_id}.failed{stamp}-*")):
            stamp += 1
        for f in self.scan_dir.glob(f"{plate.plate_id}-*"):  # keep the failed scans, out of the way
            f.rename(f.with_name(f.name.replace(plate.plate_id, f"{plate.plate_id}.failed{stamp}", 1)))
        self._events.append({"plate_id": plate.plate_id, "event": "reprint", "failed_fraction": round(frac, 3),
                             "first_attempt_files": f"{plate.plate_id}.failed{stamp}-*"})
        ms = self._measure_once(plate)
        frac = _failed_fraction(ms)
        if frac > self.failed_plate_fraction:
            print(f"  [{self.site}] reprint also failed ({frac:.0%}): scoring the round without this plate.")
            self._events.append({"plate_id": plate.plate_id, "event": "dropped after reprint", "failed_fraction": round(frac, 3)})
            return self._drop(plate)
        return ms

    def _drop(self, plate: Plate) -> list[Measurement]:
        ms = [Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "failed-plate") for p in plate.pieces]
        Path(f"{self.scan_dir / plate.plate_id}-measurements.json").write_text(json.dumps([asdict(m) for m in ms], indent=1))
        return ms

    def _measure_once(self, plate: Plate) -> list[Measurement]:
        base = self.scan_dir / plate.plate_id
        sheet = Path(f"{base}-manual.csv")
        if not sheet.exists():
            write_manual_sheet(plate, sheet)
        while True:
            answer = self.ask(f"[{self.site}] scans for {plate.plate_id} in {self.scan_dir}, or every piece in {sheet.name}? "
                              f"[Enter when ready / 'fail' if the plate failed] ").strip()
            if answer.lower() == "fail":
                return [Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "scanner") for p in plate.pieces]
            missing = [s for s in ("holes", "pins") if not os.path.exists(f"{base}-{s}.png")]
            if missing:
                ms, todo = read_manual_sheet(sheet, plate)
                if not todo:  # no scanner: every piece measured by hand
                    self._events.append({"plate_id": plate.plate_id, "event": "measured by hand, no scans",
                                         "file": sheet.name})
                    print(f"  measured by hand: {sum(m.status == 'ok' for m in ms)}/{len(ms)} ok")
                    Path(f"{base}-measurements.json").write_text(json.dumps([asdict(m) for m in ms], indent=1))
                    return ms
                print(f"  missing: {', '.join(f'{base}-{m}.png' for m in missing)}")
                print(f"  or, by hand: {len(todo)} pieces still blank in {sheet} (row, col): {todo}")
                continue
            try:
                ms = self._read_scans(plate, base)
                break
            except ValueError as e:  # fiducials not found, unreadable file: rescan, don't crash the run
                print(f"  {e}. Rescan, save over the same file, then press Enter.")

        cal = f"{base}-caliper.csv"
        if os.path.exists(cal):
            checks = load_caliper_csv(cal, plate)
            print(f"  scanner vs caliper: {agreement(ms, checks)}")
            offsets = scanner_offsets(ms, checks, plate, min_pairs=self.caliper_min_pairs)
            if offsets:
                ms = apply_offsets(ms, offsets, plate)
                print(f"  corrected scanner bias per kind (mm): {offsets}; after: {agreement(ms, checks)}")
        Path(f"{base}-measurements.json").write_text(json.dumps([asdict(m) for m in ms], indent=1))
        return ms

    def _read_scans(self, plate: Plate, base: Path) -> list[Measurement]:
        ms = []
        for mode in ("holes", "pins"):
            img = cv2.imread(f"{base}-{mode}.png", cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"{base}-{mode}.png is not a readable image")
            try:
                got, info = measure_scan(img, plate, mode)
            except ValueError as e:
                raise ValueError(f"{mode} scan: {e}") from e
            print(f"  {mode}: {sum(m.status == 'ok' for m in got)}/{len(got)} measured, "
                  f"{info.mm_per_px * 1000:.1f} um/px, mirrored={info.mirrored}")
            for n in info.notes:
                print(f"    {n}")
            ms += got
        return ms


def write_manual_sheet(plate: Plate, path: str | Path) -> None:
    """A blank hand-measurement sheet, one row per piece, for sites without a scanner.
    Fill measured_d in mm (micrometer for pins, pin gauges or calipers for holes),
    status=failed for a piece that didn't print, or status=skip for a piece that printed
    but wasn't measured (e.g. holes, with only a micrometer). Nominal sizes are left off
    so they don't anchor the reading."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row", "col", "kind", "measured_d", "status"])
        for p in sorted(plate.pieces, key=lambda p: p.slot):
            w.writerow([p.slot[0], p.slot[1], p.kind, "", ""])


def read_manual_sheet(path: str | Path, plate: Plate) -> tuple[list[Measurement], list[tuple[int, int]]]:
    """Hand measurements from the sheet, and the slots still blank. A piece counts as done
    when it has a number, status=failed, or status=skip. A skipped piece comes back with
    method NOT_MEASURED: not data, and not a print failure. Pieces still blank come back
    as failed."""
    by_slot = {p.slot: p for p in plate.pieces}
    done: dict[tuple[int, int], Measurement] = {}
    if Path(path).exists():
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                cells = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                try:
                    p = by_slot[(int(cells.get("row", "")), int(cells.get("col", "")))]
                except (KeyError, ValueError):
                    continue
                status = cells.get("status", "").lower()
                if status == "failed":
                    done[p.slot] = Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "caliper")
                    continue
                if status in ("skip", "skipped", "not measured", "not-measured"):
                    done[p.slot] = Measurement(p.piece_id, plate.plate_id, plate.site, None, "skipped", NOT_MEASURED)
                    continue
                try:
                    d = float(cells.get("measured_d", ""))
                except ValueError:
                    continue  # blank or unreadable: still to do
                if not 0.0 < d < 20.0:
                    print(f"  {Path(path).name} row {p.slot}: {d} mm isn't a plausible diameter, still to do")
                    continue
                done[p.slot] = Measurement(p.piece_id, plate.plate_id, plate.site, d, "ok", "caliper")
    todo = sorted(s for s in by_slot if s not in done)
    ms = [done.get(p.slot) or Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "caliper")
          for p in plate.pieces]
    return ms, todo


def _failed_fraction(ms: list[Measurement]) -> float:
    """Failed share of the pieces someone looked at: skipped (not measured) pieces don't
    count either way, so a pins-only plate doesn't trip the reprint rule."""
    seen = [m for m in ms if m.method != NOT_MEASURED]
    return sum(m.status == "failed" for m in seen) / max(len(seen), 1)
