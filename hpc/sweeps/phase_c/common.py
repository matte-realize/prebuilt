"""Shared runner for the Phase C sweeps.

Each job is one (config, seed) pair, run through `arms.run_experiment` on the
NumPy reference simulator. Jobs fan out over a process pool; results append to
a JSONL file, one line per job, so an interrupted sweep resumes where it
stopped.
"""
from __future__ import annotations

import os

# One BLAS thread per worker; the pool provides the parallelism.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import gzip
import json
import sys
import time
from dataclasses import asdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arms.experiment import Config, run_experiment  # noqa: E402
from eval.audit import audit  # noqa: E402
from sim.reference import make_world  # noqa: E402

SITES = {"resin": "resin", "pla": "pla"}
OUT = Path(__file__).resolve().parent / "results"


def job_key(arm: str, cfg: dict) -> str:
    return f"{arm}|seed={cfg['seed']}"


def run_job(job: tuple[str, dict]) -> dict:
    arm, kw = job
    cfg = Config(**kw)
    t0 = time.time()
    res = run_experiment(make_world(SITES, cfg.seed), SITES, cfg)
    rep = audit(list(res.chains.values()))
    return {
        "key": job_key(arm, kw), "arm": arm, "config": asdict(cfg), "seconds": time.time() - t0,
        "audit_pass": rep.passed, "scores": res.scores, "trust": res.trust,
        "credibility": res.credibility, "retired": res.retired,
    }


def run_sweep(name: str, arms: dict[str, dict], seeds: range, workers: int) -> Path:
    """arms: label -> Config kwargs (without seed). Appends to results/<name>.jsonl, skipping finished jobs."""
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.jsonl"
    done = set()
    if path.exists():
        with open(path) as f:
            done = {json.loads(line)["key"] for line in f if line.strip()}
    jobs = [(arm, {**kw, "seed": s}) for s in seeds for arm, kw in arms.items()]
    jobs = [j for j in jobs if job_key(*j) not in done]
    print(f"{name}: {len(jobs)} jobs to run ({len(done)} already done), {workers} workers", flush=True)
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a") as f:
        for i, row in enumerate(pool.imap_unordered(run_job, jobs), 1):
            f.write(json.dumps(row) + "\n")
            f.flush()
            if i % max(1, len(jobs) // 20) == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    return path


def load(name: str) -> list[dict]:
    """Reads results/<name>.jsonl, or the committed results/<name>.jsonl.gz."""
    path = OUT / f"{name}.jsonl"
    with (open(path) if path.exists() else gzip.open(f"{path}.gz", "rt")) as f:
        return [json.loads(line) for line in f if line.strip()]


def cli(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--seed0", type=int, default=1000, help="first seed (kept away from run.py's 0..19)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--particles", type=int, default=2000)
    ap.add_argument("--rounds", type=int, default=3)
    return ap.parse_args()
