"""Real-printer `Printer`: writes plate files, records human approval, waits for scans.

File conventions, per plate, in `scan_dir`:
    {plate_id}-holes.png     backlit scan
    {plate_id}-pins.png      front-lit scan, dark lid
    {plate_id}-caliper.csv   optional spot checks (see measure/manual.py)
Measurements are written to {plate_id}-measurements.json and never leave the site.
"""
from __future__ import annotations

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


class RealPrinter:
    def __init__(self, site: str, scan_dir: str, ask=input, plate_dir: str | Path = PLATE_DIR,
                 failed_plate_fraction: float | None = None):
        self.site = site
        self.failed_plate_fraction = failed_plate_fraction  # prereg: above this, reprint once
        self.plate_dir = Path(plate_dir)
        self.scan_dir = Path(scan_dir)
        self.scan_dir.mkdir(parents=True, exist_ok=True)
        self.ask = ask

    def prepare(self, plate: Plate) -> dict:
        """Write plate files and get printability/safety approval. Returned dict goes on the receipt chain."""
        save_plate(plate, self.plate_dir / self.site / f"{plate.plate_id}.json")
        stl = self.plate_dir / self.site / f"{plate.plate_id}.stl"
        write_stl(plate, stl)
        print(f"\n[{self.site}] {plate.plate_id}: {stl}")
        print(f"  caliper-check slots: {sample_for_caliper(plate, seed=plate.seed)}")
        answer = self.ask(f"[{self.site}] approve {plate.plate_id} for printing? [y / or describe edit/veto] ").strip()
        return {"plate_id": plate.plate_id, "approved": answer.lower() in ("y", "yes"), "note": "" if answer.lower() in ("y", "yes") else answer}

    def print_and_measure(self, plate: Plate) -> list[Measurement]:
        """Measure the plate. Past the prereg's failed-plate fraction it is reprinted once; if the
        reprint fails too, every piece is reported failed so the round is scored without it."""
        base = self.scan_dir / plate.plate_id
        ms = self._measure_once(plate)
        frac = sum(m.status == "failed" for m in ms) / max(len(ms), 1)
        if self.failed_plate_fraction is None or frac <= self.failed_plate_fraction:
            return ms
        print(f"  [{self.site}] {plate.plate_id}: {frac:.0%} of pieces failed, over the prereg's "
              f"{self.failed_plate_fraction:.0%}. Reprint the same plate file once.")
        stamp = 1
        while any(self.scan_dir.glob(f"{plate.plate_id}.failed{stamp}-*")):
            stamp += 1
        for f in self.scan_dir.glob(f"{plate.plate_id}-*"):  # keep the failed scans, out of the way
            f.rename(f.with_name(f.name.replace(plate.plate_id, f"{plate.plate_id}.failed{stamp}", 1)))
        ms = self._measure_once(plate)
        frac = sum(m.status == "failed" for m in ms) / max(len(ms), 1)
        if frac > self.failed_plate_fraction:
            print(f"  [{self.site}] reprint also failed ({frac:.0%}): scoring the round without this plate.")
            ms = [Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "failed-plate") for p in plate.pieces]
            Path(f"{base}-measurements.json").write_text(json.dumps([asdict(m) for m in ms], indent=1))
        return ms

    def _measure_once(self, plate: Plate) -> list[Measurement]:
        base = self.scan_dir / plate.plate_id
        while True:
            answer = self.ask(f"[{self.site}] scans for {plate.plate_id} in {self.scan_dir}? [Enter when ready / 'fail' if the plate failed] ").strip()
            if answer.lower() == "fail":
                return [Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", "scanner") for p in plate.pieces]
            missing = [s for s in ("holes", "pins") if not os.path.exists(f"{base}-{s}.png")]
            if not missing:
                break
            print(f"  missing: {', '.join(f'{base}-{m}.png' for m in missing)}")

        ms = []
        for mode in ("holes", "pins"):
            got, info = measure_scan(cv2.imread(f"{base}-{mode}.png", cv2.IMREAD_GRAYSCALE), plate, mode)
            print(f"  {mode}: {sum(m.status == 'ok' for m in got)}/{len(got)} measured, "
                  f"{info.mm_per_px * 1000:.1f} um/px, mirrored={info.mirrored}")
            for n in info.notes:
                print(f"    {n}")
            ms += got
        cal = f"{base}-caliper.csv"
        if os.path.exists(cal):
            checks = load_caliper_csv(cal, plate)
            print(f"  scanner vs caliper: {agreement(ms, checks)}")
            offsets = scanner_offsets(ms, checks, plate)
            if offsets:
                ms = apply_offsets(ms, offsets, plate)
                print(f"  corrected scanner bias per kind (mm): {offsets}; after: {agreement(ms, checks)}")
        Path(f"{base}-measurements.json").write_text(json.dumps([asdict(m) for m in ms], indent=1))
        return ms
