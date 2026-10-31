"""Phase D dry run: `run.py --source real` with rehearsal printers instead of real ones.

    python -m hpc.phase_d.rehearse --out /tmp/dry --prereg prereg/prereg.yaml        # seed plate only (range null)
    python -m hpc.phase_d.rehearse --out /tmp/dry --prereg /tmp/dry/prereg.yaml       # range filled: resumes at round 1

Runs run.py's real path unchanged (prereg checks, config from the prereg, resume
check, receipts, checkpoint, seed-plate prior check); only `run.real_printers` is
swapped for `measure.rehearsal.rehearsal_printers`, whose simulated world is
`sim.reference.make_world(SITES, config.seed)`. Plates, scans and receipts all go
under --out. --scores writes run.py's scores JSON.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import run
from measure.rehearsal import rehearsal_printers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="scratch directory: plates/, scans/, receipts/")
    ap.add_argument("--prereg", default="prereg/prereg.yaml")
    ap.add_argument("--scores", default=None, help="write run.py's scores JSON here")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # Printers live in out/scans/<site>; the world is the one the config's seed picks.
    run.real_printers = lambda cfg, scans: rehearsal_printers(run.SITES, out, cfg.seed)
    sys.argv = ["run.py", "--source", "real", "--prereg", a.prereg, "--chains", str(out / "receipts"),
                "--scans", str(out / "scans"), *(["--out", a.scores] if a.scores else [])]
    run.main()


if __name__ == "__main__":
    main()
