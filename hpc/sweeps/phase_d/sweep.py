"""Phase D evaluation sweeps on the GPU: robustness, ablation, scaling.

    .venv/bin/python hpc/sweeps/phase_d/sweep.py robustness --seeds 200   # honest, bad_pla, bad_resin
    .venv/bin/python hpc/sweeps/phase_d/sweep.py ablation --seeds 200     # honest, no_messages
    .venv/bin/python hpc/sweeps/phase_d/sweep.py scaling --seeds 100      # honest at 2, 5, 10, 25 sites
    .venv/bin/python hpc/sweeps/phase_d/sweep.py robustness --cpu         # no GPU: reference sim, process pool

Every run takes its config from prereg/prereg.yaml (`prereg.check.sim_config`);
only the seed, the sites and the condition change. GPU runs go through
`sim.batch.run_batch` with orient_std 0, the world `run.py --source sim` uses,
so a seed here is the same world as that seed in run.py and the Phase C sweeps.

Results go to results/<condition>_sites<k>.jsonl, one line per seed, and a
condition shared by two sweeps (honest) runs once. Finished seeds are skipped,
so an interrupted sweep resumes. `analyze.py` reads the .jsonl or the
committed .jsonl.gz.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import gzip
import json
import multiprocessing
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arms.experiment import Config, Results, run_experiment  # noqa: E402
from eval.audit import audit  # noqa: E402
from prereg.check import load as load_prereg, sim_config  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
SEED0 = 3000  # away from run.py's 0..19 and the Phase C tuning seeds 2000..2099

# condition -> Config overrides; bad_sites names are resolved per world
CONDITIONS = {
    "honest": {},
    "bad_pla": {"bad_sites": ("pla",)},
    "bad_resin": {"bad_sites": ("resin",)},
    "no_messages": {"share_messages": False},
}
SWEEPS = {
    "robustness": [("honest", 2), ("bad_pla", 2), ("bad_resin", 2)],
    "ablation": [("honest", 2), ("no_messages", 2)],
    "scaling": [("honest", k) for k in (2, 5, 10, 25)],
}


def site_names(k: int) -> dict[str, str]:
    from sim.batch import site_names as names
    return names(k)


def base_config(prereg_path: str) -> tuple[Config, str]:
    prereg, sha = load_prereg(prereg_path)
    return sim_config(prereg), sha


def record(seed: int, condition: str, sites: dict, res: Results, sha: str, seconds: float) -> dict:
    rep = audit(list(res.chains.values()))
    return {"seed": seed, "condition": condition, "n_sites": len(sites), "prereg_sha256": sha,
            "config": res.config, "seconds": seconds, "audit_pass": rep.passed, "scores": res.scores,
            "trust": res.trust, "credibility": res.credibility, "retired": res.retired}


def path_for(condition: str, k: int) -> Path:
    return OUT / f"{condition}_sites{k}.jsonl"


def done_seeds(path: Path) -> set[int]:
    seeds = set()
    for p in (path, Path(f"{path}.gz")):
        if p.exists():
            with (gzip.open(p, "rt") if p.suffix == ".gz" else open(p)) as f:
                seeds |= {json.loads(line)["seed"] for line in f if line.strip()}
    return seeds


def _gpu_chunk(seeds: list[int], condition: str, k: int, prereg_path: str) -> list[dict]:
    from sim.batch import run_batch
    cfg, sha = base_config(prereg_path)
    sites = site_names(k)
    t0 = time.time()
    results = run_batch(seeds, sites, replace(cfg, **CONDITIONS[condition]), orient_std=0.0)
    per = (time.time() - t0) / len(seeds)
    return [record(s, condition, sites, r, sha, per) for s, r in zip(seeds, results)]


def _cpu_job(seed: int, condition: str, k: int, prereg_path: str) -> list[dict]:
    from sim.reference import make_world
    cfg, sha = base_config(prereg_path)
    sites = site_names(k)
    t0 = time.time()
    res = run_experiment(make_world(sites, seed), sites, replace(cfg, seed=seed, **CONDITIONS[condition]))
    return [record(seed, condition, sites, res, sha, time.time() - t0)]


def _star(args):
    fn, *rest = args
    return fn(*rest)


def run_condition(condition: str, k: int, seeds: list[int], a: argparse.Namespace) -> Path:
    OUT.mkdir(exist_ok=True)
    path = path_for(condition, k)
    gz = Path(f"{path}.gz")
    if gz.exists() and not path.exists():  # resume from the committed copy
        with gzip.open(gz, "rt") as f, open(path, "w") as out:
            out.write(f.read())
    todo = [s for s in seeds if s not in done_seeds(path)]
    print(f"{condition}, {k} sites: {len(todo)} seeds to run ({len(seeds) - len(todo)} done)", flush=True)
    if not todo:
        return path
    if a.cpu:
        jobs = [(_cpu_job, s, condition, k, a.prereg) for s in todo]
    else:
        batch = a.batch or max(1, 32 // k)
        jobs = [(_gpu_chunk, todo[i:i + batch], condition, k, a.prereg) for i in range(0, len(todo), batch)]
    t0, n = time.time(), 0
    # spawn, not fork: each GPU worker needs its own CUDA context
    with multiprocessing.get_context("spawn").Pool(a.workers) as pool, open(path, "a") as f:
        for rows in pool.imap_unordered(_star, jobs):
            for row in rows:
                f.write(json.dumps(row) + "\n")
            f.flush()
            n += len(rows)
            print(f"  {n}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sweep", choices=list(SWEEPS))
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=SEED0)
    ap.add_argument("--sites", type=int, nargs="*", default=None, help="scaling: only these site counts")
    ap.add_argument("--workers", type=int, default=None,
                    help="processes (GPU default 6: each holds a CUDA context on the 8 GB laptop card; CPU default: cores - 1)")
    ap.add_argument("--batch", type=int, default=None, help="GPU: seeds per batch (default 32 // sites)")
    ap.add_argument("--cpu", action="store_true", help="reference sim on CPU workers instead of sim.batch")
    ap.add_argument("--prereg", default=str(ROOT / "prereg/prereg.yaml"))
    a = ap.parse_args()
    a.workers = a.workers or (max(1, (os.cpu_count() or 2) - 1) if a.cpu else 6)

    seeds = list(range(a.seed0, a.seed0 + a.seeds))
    for condition, k in SWEEPS[a.sweep]:
        if a.sites and k not in a.sites:
            continue
        run_condition(condition, k, seeds, a)


if __name__ == "__main__":
    main()
