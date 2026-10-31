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

from arms.experiment import Config, run_experiment
from plates.seed import SEED_PIECES
from eval.audit import audit
from eval.metrics import oracle_gap_closed, summarize, with_fit

SITES = {"resin": "resin", "pla": "pla"}


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim", "real"], required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=1, help="sim only: number of seeds")
    ap.add_argument("--particles", type=int, default=2000)
    ap.add_argument("--oracle-particles", type=int, default=None, help="oracle arm particles (default: --particles)")
    ap.add_argument("--bad-site", action="append", default=[], help="sim only: site that broadcasts bad beliefs")
    ap.add_argument("--no-messages", action="store_true", help="ablation: cut the network")
    ap.add_argument("--no-challenge", action="store_true", help="ablation: skip the challenge round")
    ap.add_argument("--no-spawn", action="store_true", help="ablation: dormant agents never wake")
    ap.add_argument("--seed-pieces", type=int, default=SEED_PIECES, help="sim sweep: calibration pieces on the seed plate (max 56)")
    ap.add_argument("--slots", type=int, default=Config.slots_per_arm, help="sim sweep: slots per arm per plate")
    ap.add_argument("--lpd-clip", type=lambda v: None if v.lower() == "none" else float(v), default=Config.lpd_clip,
                    help="per-piece held-out dLPD bound in nats for credit ('none' = unclipped)")
    ap.add_argument("--chains", default=None, help="directory for receipt chains (default: in memory)")
    ap.add_argument("--out", default=None, help="write results JSON here")
    ap.add_argument("--prereg", default="prereg/prereg.yaml", help="pre-registration file (real: config; both: fit classes)")
    ap.add_argument("--scans", default="scans", help="real only: directory the scanner saves into")
    args = ap.parse_args()

    if args.source == "real":
        from measure.real import RealPrinter
        from prereg.check import check_heldout, config_from, fit_thresholds, load, missing
        prereg, sha = load(args.prereg)
        check_heldout(prereg)
        gaps = missing(prereg, "seed")
        if gaps:
            raise SystemExit("prereg incomplete, fill in before printing:\n  " + "\n  ".join(gaps))
        late = missing(prereg, "round1")
        # Real runs take every setting from the prereg; CLI tuning flags are for simulation.
        cfg = config_from(prereg, sha, rounds=0 if late else None)
        if late:
            print("predicted range not committed yet: running the seed plate only. "
                  "Commit the range, then rerun to resume at round 1.")
        print(f"prereg sha256 {sha}")
        chains = args.chains or "receipts/real"
        check_resume(f"{chains}/state.pkl", cfg)
        res = run_experiment({s: RealPrinter(s, f"{args.scans}/{s}") for s in SITES}, SITES, cfg,
                             chain_dir=chains, checkpoint=f"{chains}/state.pkl")
        res.scores = with_fit(res.scores, res.predictions, fit_thresholds(prereg), SITES)
        print(summarize(res.scores))
        rep = audit(list(res.chains.values()))
        print(f"privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")
        if args.out:
            with open(args.out, "w") as f:
                json.dump(res.scores, f, indent=1)
        return

    from prereg.check import fit_thresholds, load
    from sim.reference import make_world

    thresholds = fit_thresholds(load(args.prereg)[0])  # fit-class accuracy once the prereg has them
    gaps = defaultdict(list)
    all_rows = []
    for k in range(args.seeds):
        seed = args.seed + k
        cfg = Config(rounds=args.rounds, n_particles=args.particles, seed=seed, oracle_particles=args.oracle_particles,
                     bad_sites=tuple(args.bad_site), share_messages=not args.no_messages,
                     seed_pieces=args.seed_pieces, slots_per_arm=args.slots, lpd_clip=args.lpd_clip,
                     challenge=not args.no_challenge, **({"dormant": ()} if args.no_spawn else {}))
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
