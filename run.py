"""Single entry point. `--source sim` and `--source real` share every code path.

    python run.py --source sim --rounds 3 --seeds 10
"""
import argparse
import json
import math
import os
import pickle
from collections import defaultdict
from dataclasses import asdict

import numpy as np

from agents.agents import DORMANT_NAMES
from arms.experiment import Config, run_experiment
from eval.audit import audit
from eval.metrics import oracle_gap_closed, summarize, with_fit

SITES = {"resin": "resin", "pla": "pla"}
# CLI flag (argparse dest) -> Config field, for sim runs.
SIM_FLAGS = {"rounds": "rounds", "particles": "n_particles", "oracle_particles": "oracle_particles",
             "mh_steps": "mh_steps", "seed_pieces": "seed_pieces", "slots": "slots_per_arm", "lpd_clip": "lpd_clip"}


def check_resume(checkpoint: str, cfg: Config) -> None:
    """Refuse to resume a real run under different settings than it started with.

    Only `rounds` (the seed plate runs alone until the range is committed) and the
    prereg hash (committing the range changes it) may differ.
    """
    if not os.path.exists(checkpoint):
        return
    with open(checkpoint, "rb") as f:
        started = pickle.load(f)["res"].config
    now = json.loads(json.dumps(asdict(cfg)))  # tuples -> lists, as recorded
    diff = {k: (started.get(k), v) for k, v in now.items()
            if k not in ("rounds", "prereg_sha256") and json.loads(json.dumps(started.get(k))) != v}
    if diff:
        raise SystemExit(f"{checkpoint} was started with different settings (started, now): {diff}")


def real_printers(cfg: Config, scans: str) -> dict:
    """Printers for a real run: RealPrinter per site, except cfg.sim_sites, which print on a
    simulated world (sim.reference.make_world, fixed by cfg.seed) for fallback tier B."""
    from measure.real import RealPrinter
    from sim.reference import make_world
    world = make_world(SITES, cfg.seed) if cfg.sim_sites else {}
    return {s: world[s] if s in cfg.sim_sites else
            RealPrinter(s, f"{scans}/{s}", failed_plate_fraction=cfg.failed_plate_fraction,
                        caliper_checks=cfg.caliper_checks, caliper_min_pairs=cfg.caliper_min_pairs)
            for s in SITES}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim", "real"], required=True)
    # Sim settings default to the prereg's `config` section (SUPPRESS = not given, keep the prereg's).
    keep = argparse.SUPPRESS
    ap.add_argument("--rounds", type=int, default=keep)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=1, help="sim only: number of seeds")
    ap.add_argument("--particles", type=int, default=keep)
    ap.add_argument("--oracle-particles", type=int, default=keep, help="oracle arm particles (default: prereg, or --particles if given)")
    ap.add_argument("--mh-steps", type=int, default=keep, help="sim sweep: MH steps per resample (the oracle's scale from it)")
    ap.add_argument("--bad-site", action="append", default=[], help="sim only: site that broadcasts bad beliefs")
    ap.add_argument("--no-messages", action="store_true", help="ablation: cut the network")
    ap.add_argument("--challenge", action="store_true", help="secondary analysis: run the challenge round (networked arm)")
    ap.add_argument("--spawn", action="store_true", help="secondary analysis: dormant agents can wake (networked arm)")
    ap.add_argument("--seed-pieces", type=int, default=keep, help="sim sweep: calibration pieces on the seed plate (max 56)")
    ap.add_argument("--slots", type=int, default=keep, help="sim sweep: slots per arm per plate")
    ap.add_argument("--lpd-clip", type=lambda v: None if v.lower() == "none" else float(v), default=keep,
                    help="per-piece held-out dLPD bound in nats for credit ('none' = unclipped)")
    ap.add_argument("--chains", default=None, help="directory for receipt chains (default: in memory)")
    ap.add_argument("--out", default=None, help="write results JSON here")
    ap.add_argument("--prereg", default="prereg/prereg.yaml", help="pre-registration file (real: config; both: fit classes)")
    ap.add_argument("--scans", default="scans", help="real only: directory the scanner saves into")
    ap.add_argument("--sim-site", action="append", default=[],
                    help="real only, fallback tier B: this site is simulated (repeatable; at least one site stays real)")
    args = ap.parse_args()

    if args.source == "real":
        from prereg.check import check_heldout, config_from, fit_thresholds, load, missing
        prereg, sha = load(args.prereg)
        check_heldout(prereg)
        gaps = missing(prereg, "seed")
        if gaps:
            raise SystemExit("prereg incomplete, fill in before printing:\n  " + "\n  ".join(gaps))
        late = missing(prereg, "round1")
        # Real runs take every setting from the prereg; CLI tuning flags are for simulation.
        unknown = set(args.sim_site) - set(SITES)
        if unknown or len(set(args.sim_site)) == len(SITES):
            raise SystemExit(f"--sim-site must name some but not all of {sorted(SITES)}")
        meas = prereg.get("measurement") or {}
        cfg = config_from(prereg, sha, rounds=0 if late else None, sim_sites=tuple(sorted(set(args.sim_site))),
                          failed_plate_fraction=prereg["failed_plate_fraction"],
                          caliper_checks=meas.get("caliper_checks_per_plate"),
                          caliper_min_pairs=meas.get("caliper_offset_min_pairs"))
        if late:
            print("predicted range not committed yet: running the seed plate only. "
                  "Commit the range, then rerun to resume at round 1.")
        print(f"prereg sha256 {sha}")
        chains = args.chains or "receipts/real"
        check_resume(f"{chains}/state.pkl", cfg)
        printers = real_printers(cfg, args.scans)
        if cfg.sim_sites:
            print(f"fallback tier B: {', '.join(cfg.sim_sites)} simulated (world seed {cfg.seed}), the rest real")
        res = run_experiment(printers, SITES, cfg,
                             chain_dir=chains, checkpoint=f"{chains}/state.pkl")
        res.scores = with_fit(res.scores, res.predictions, fit_thresholds(prereg), SITES)
        print(summarize(res.scores))
        rep = audit(list(res.chains.values()))
        print(f"privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")
        if args.out:
            with open(args.out, "w") as f:
                json.dump(res.scores, f, indent=1)
        return

    from prereg.check import fit_thresholds, load, sim_config
    from sim.reference import make_world

    prereg = load(args.prereg)[0]
    thresholds = fit_thresholds(prereg)  # fit-class accuracy once the prereg has them
    given = {f: getattr(args, a) for a, f in SIM_FLAGS.items() if hasattr(args, a)}
    if args.challenge:
        given["challenge"] = True
    if args.spawn:
        given["dormant"] = tuple(DORMANT_NAMES)
    gaps = defaultdict(list)
    all_rows = []
    for k in range(args.seeds):
        seed = args.seed + k
        cfg = sim_config(prereg, **given, seed=seed, bad_sites=tuple(args.bad_site), share_messages=not args.no_messages)
        chain_dir = f"{args.chains}/seed{seed}" if args.chains else None
        res = run_experiment(make_world(SITES, seed), SITES, cfg, chain_dir)
        res.scores = with_fit(res.scores, res.predictions, thresholds, SITES)
        rep = audit(list(res.chains.values()))
        if args.seeds == 1:
            print(summarize(res.scores))
            for row in res.trust:
                print(f"trust round {row['round']}: {row['receiver']} <- {row['sender']}: {row['trust']:.3f}")
        spawned = ", ".join(f"{x['agent']}@{x['site']} r{x['round']}" for x in res.spawned) or "none"
        print(f"seed {seed}: privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings); "
              f"{len(res.challenges)} challenge flags; spawned: {spawned}")
        for r, g in oracle_gap_closed(res.scores).items():
            gaps[r].append(g)
        all_rows += [{**row, "seed": seed} for row in res.scores]

    if args.seeds > 1:
        for r, g in sorted(gaps.items()):
            g = np.array([x for x in g if not math.isnan(x)])
            print(f"round {r}: oracle gap closed (MAE) median {np.median(g):.2f}, IQR [{np.percentile(g, 25):.2f}, {np.percentile(g, 75):.2f}], n={len(g)}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(all_rows, f, indent=1)


if __name__ == "__main__":
    main()
