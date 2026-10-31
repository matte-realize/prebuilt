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
from eval.audit import audit
from eval.metrics import oracle_gap_closed, summarize

SITES = {"resin": "resin", "pla": "pla"}


def check_resume(checkpoint: str, cfg: Config) -> None:
    """Refuse to resume a real run under a different config than the one it started with."""
    if not os.path.exists(checkpoint):
        return
    with open(checkpoint, "rb") as f:
        started = pickle.load(f)["res"].config
    now = json.loads(json.dumps(asdict(cfg)))  # tuples -> lists, as on the receipt chain
    diff = {k: (started.get(k), v) for k, v in now.items() if json.loads(json.dumps(started.get(k))) != v}
    if diff:
        raise SystemExit(f"{checkpoint} was started with a different config (started, now): {diff}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim", "real"], required=True)
    ap.add_argument("--config", default=None, help="frozen collective config JSON (hpc/phase_d/frozen_config.json); required for --source real, overrides --rounds/--particles/--slots/--seed-pieces")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=1, help="sim only: number of seeds")
    ap.add_argument("--particles", type=int, default=2000)
    ap.add_argument("--bad-site", action="append", default=[], help="sim only: site that broadcasts bad beliefs")
    ap.add_argument("--no-messages", action="store_true", help="ablation: cut the network")
    ap.add_argument("--seed-pieces", type=int, default=None, help="sim sweep: thin the seed plate to this many pieces")
    ap.add_argument("--slots", type=int, default=18, help="slots per arm per plate")
    ap.add_argument("--chains", default=None, help="directory for receipt chains (default: in memory)")
    ap.add_argument("--out", default=None, help="write results JSON here")
    ap.add_argument("--scans", default="scans", help="real only: directory the scanner saves into")
    args = ap.parse_args()
    frozen = {}
    if args.config:
        from sim.calibrate import load_config
        frozen = load_config(args.config)
    elif args.source == "real":
        ap.error("--source real needs --config, so the real run uses the frozen config the predicted range was computed with")

    if args.source == "real":
        from measure.real import RealPrinter
        cfg = Config(**frozen, seed=args.seed)
        chains = args.chains or "receipts/real"
        check_resume(f"{chains}/state.pkl", cfg)
        res = run_experiment({s: RealPrinter(s, f"{args.scans}/{s}") for s in SITES}, SITES, cfg,
                             chain_dir=chains, checkpoint=f"{chains}/state.pkl")
        print(summarize(res.scores))
        rep = audit(list(res.chains.values()))
        print(f"privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")
        if args.out:
            with open(args.out, "w") as f:
                json.dump(res.scores, f, indent=1)
        return

    from sim.reference import make_world

    gaps = defaultdict(list)
    all_rows = []
    for k in range(args.seeds):
        seed = args.seed + k
        knobs = frozen or dict(rounds=args.rounds, n_particles=args.particles, seed_pieces=args.seed_pieces, slots_per_arm=args.slots)
        cfg = Config(**knobs, seed=seed, bad_sites=tuple(args.bad_site), share_messages=not args.no_messages)
        chain_dir = f"{args.chains}/seed{seed}" if args.chains else None
        res = run_experiment(make_world(SITES, seed), SITES, cfg, chain_dir)
        rep = audit(list(res.chains.values()))
        if args.seeds == 1:
            print(summarize(res.scores))
            for row in res.trust:
                print(f"trust round {row['round']}: {row['receiver']} <- {row['sender']}: {row['trust']:.3f}")
        print(f"seed {seed}: privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")
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
