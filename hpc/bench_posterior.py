"""Benchmark: NumPy reference vs Warp posterior, update + predict.

Workload per posterior: 60 measurements folded in as three chunks of 20 (one
plate streaming in), then predictive mean/std for 200 held-out pieces.

    .venv/bin/python hpc/bench_posterior.py                  # 2k, 20k, 200k particles
    .venv/bin/python hpc/bench_posterior.py --batch 64       # plus B posteriors in one batch

Timings are wall clock after a warm-up (kernel compile excluded), median of
--repeats runs. Warp predict is shown per piece (reference API, one sync per
call) and batched (PosteriorBatch.predict, one sync for all pieces).
"""
from __future__ import annotations

import argparse
import statistics
import time

import numpy as np
import warp as wp

from model import physics
from model import posterior as reference
from model import posterior_warp as gpu
from tests.test_posterior import _measure, _pieces


def workload(process: str, seed: int):
    rng = np.random.default_rng(seed)
    theta_true = physics.sample_prior(process, 1, rng)[0]
    train, held = _pieces(rng, 60, "t", "seed"), _pieces(rng, 200, "h", "heldout")
    ms, _, _ = _measure(process, train, theta_true, rng)
    return {p.piece_id: p for p in train + held}, [ms[:20], ms[20:40], ms[40:]], held


def timed(fn) -> float:
    wp.synchronize()
    t = time.perf_counter()
    fn()
    wp.synchronize()
    return time.perf_counter() - t


def bench_single(cls, n: int, repeats: int) -> tuple[float, float, float | None]:
    """Median seconds: update, per-piece predict, batched predict (Warp only) on the same fit."""
    pieces, chunks, held = workload("resin", 1)
    up, pr, bp = [], [], []
    for r in range(repeats):
        post = cls("resin", pieces, n=n, seed=r)
        up.append(timed(lambda: [post.update(c) for c in chunks]))
        pr.append(timed(lambda: [post.predict(p) for p in held]))
        if hasattr(post, "batch"):
            bp.append(timed(lambda: post.batch.predict([held])))
    return statistics.median(up), statistics.median(pr), statistics.median(bp) if bp else None


def bench_batch(b: int, n: int, repeats: int, numpy_members: int) -> tuple[float, float]:
    """Seconds for B posteriors (alternating resin/pla, distinct data): Warp batch vs NumPy loop."""
    procs = ["resin" if i % 2 == 0 else "pla" for i in range(b)]
    data = [workload(p, i) for i, p in enumerate(procs)]
    pieces = [d[0] for d in data]

    def run_gpu(seed):
        batch = gpu.PosteriorBatch(procs, pieces, [seed * b + i for i in range(b)], n=n)
        for k in range(3):
            batch.update([d[1][k] for d in data])
        batch.predict([d[2] for d in data])

    def run_numpy(i):
        post = reference.ParticlePosterior(procs[i], pieces[i], n=n, seed=i)
        for c in data[i][1]:
            post.update(c)
        [post.predict(p) for p in data[i][2]]

    gpu_t = statistics.median(timed(lambda: run_gpu(r)) for r in range(repeats))
    k = min(b, numpy_members)  # NumPy cost is linear in B; time a subset and scale
    np_t = timed(lambda: [run_numpy(i) for i in range(k)]) * b / k
    return gpu_t, np_t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--particles", type=int, nargs="+", default=[2000, 20000, 200000])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--batch", type=int, default=0, help="also time B posteriors per launch")
    ap.add_argument("--numpy-members", type=int, default=8, help="NumPy members actually run in the batch test")
    args = ap.parse_args()

    wp.init()
    print(f"device: {wp.get_device().name}")
    bench_single(gpu.ParticlePosterior, 500, 1)  # compile and warm up

    print("\n| particles | NumPy update | Warp update | speedup | NumPy predict x200 | Warp predict x200 (per piece) | Warp predict x200 (batched) |")
    print("|---|---|---|---|---|---|---|")
    for n in args.particles:
        reps = 1 if n >= 100000 else args.repeats
        nu, npr, _ = bench_single(reference.ParticlePosterior, n, reps)
        gu, gpr, gbp = bench_single(gpu.ParticlePosterior, n, reps)
        print(f"| {n:,} | {nu:.3f} s | {gu:.3f} s | {nu / gu:.1f}x | {npr:.3f} s | {gpr:.3f} s | {gbp:.4f} s |")

    if args.batch:
        print("\n| particles | B | NumPy loop (est.) | Warp batch | speedup |")
        print("|---|---|---|---|---|")
        for n in args.particles:
            if n * args.batch > 4_000_000:
                continue
            g, nump = bench_batch(args.batch, n, args.repeats, args.numpy_members)
            print(f"| {n:,} | {args.batch} | {nump:.2f} s | {g:.3f} s | {nump / g:.1f}x |")


if __name__ == "__main__":
    main()
