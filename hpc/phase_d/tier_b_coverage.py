"""Tier B coverage: does the measured round-3 iso - net land inside Phase D's 5-95% range?

Each world plays a tier B day end to end: the real site is a rehearsal printer (simulated
scans through RealPrinter) on its own world, the other site is simulated at the config
seed. Seed plate, Phase D exactly as `sim.calibrate` runs it, then rounds 1-3. Odd worlds
simulate pla, even worlds resin. One JSON line per world in <out>/coverage.jsonl.

    python hpc/phase_d/tier_b_coverage.py --out cov --worlds 11 15 --seeds 200 --workers 15
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from arms.experiment import run_experiment  # noqa: E402
from measure.rehearsal import RehearsalPrinter  # noqa: E402
from prereg.check import PREREG, config_from, load  # noqa: E402
from sim import calibrate  # noqa: E402
from sim.reference import make_world  # noqa: E402

SITES = calibrate.SITES


def world(w: int, out: Path, seeds: int, workers: int) -> dict:
    prereg, sha = load(PREREG)
    meas = prereg.get("measurement") or {}
    sim = "pla" if w % 2 else "resin"
    real = next(s for s in SITES if s != sim)
    d = out / f"world{w}"
    shutil.rmtree(d, ignore_errors=True)
    cfg = config_from(prereg, sha, sim_sites=(sim,), failed_plate_fraction=prereg["failed_plate_fraction"],
                      caliper_checks=meas.get("caliper_checks_per_plate"), caliper_min_pairs=meas.get("caliper_offset_min_pairs"))

    def printers():  # rebuilt on resume, as run.py does; the checkpoint restores their RNGs
        return {real: RehearsalPrinter(make_world(SITES, 100 + w)[real], d / "scans" / real, d / "plates", seed=100 + w),
                sim: make_world(SITES, cfg.seed)[sim]}

    ckpt = d / "receipts" / "state.pkl"
    run_experiment(printers(), SITES, replace(cfg, rounds=0), chain_dir=str(d / "receipts"), checkpoint=str(ckpt))
    data = {s: v for s, v in calibrate.seed_data_from_state(ckpt).items() if s != sim}
    calibrate.check_seed_size(data, cfg.seed_pieces)
    data = calibrate.screen_failures(data, [])
    fitted = replace(calibrate.fit(dict(sorted(data.items()))), fixed=calibrate.simulated_sites((sim,), cfg.seed))
    pred = calibrate.predict(fitted, cfg, range(50000, 50000 + seeds), workers)
    res = run_experiment(printers(), SITES, cfg, chain_dir=str(d / "receipts"), checkpoint=str(ckpt))
    row = {"world": w, "sim": sim, "seeds": seeds}
    for key, sites in (("iso_minus_net_um", None), ("iso_minus_net_real_um", [real])):
        m, i = calibrate.iso_minus_net(res.scores, "mae", sites)[cfg.rounds], pred[key][cfg.rounds]
        row[key] = {"measured": m, "q05": i["q05"], "q50": i["median"], "q95": i["q95"], "inside": bool(i["q05"] <= m <= i["q95"])}
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--worlds", type=int, nargs=2, metavar=("FIRST", "LAST"), required=True)
    ap.add_argument("--seeds", type=int, default=200, help="Phase D seeds per world")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for w in range(a.worlds[0], a.worlds[1] + 1):
        try:
            row = world(w, out, a.seeds, a.workers)
        except Exception:
            row = {"world": w, "error": traceback.format_exc()[-1500:]}
        with open(out / "coverage.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)


if __name__ == "__main__":  # spawn workers re-import this file
    main()
