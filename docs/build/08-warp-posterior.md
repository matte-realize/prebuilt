# Build: Warp GPU Posterior

Status as of 2026-10-31. Branch `feat/warp-posterior`, not pushed. Owner: T. Handoff contract 2 in [06-task-split.md](06-task-split.md).

## Result

`model/posterior_warp.py` is a GPU port of `model.posterior.ParticlePosterior`. It has the same public API and runs the same algorithm: resample-move SMC with adaptive tempering, systematic resampling and random-walk Metropolis moves. All tests pass (48 in the full suite), including `tests/test_posterior.py` run unchanged against the Warp class.

`model/posterior.py` is still the reference. Its only change is a behavior-preserving refactor that moves the layout and API rules into a public `Layout` class shared with the GPU port; particles, weights, summaries and intervals are bit-identical to before. `arms/`, `agents/` and `contracts.py` are unchanged.

## Commits

| Commit | Files |
|---|---|
| `chore: add warp-lang as optional dependency` | `pyproject.toml`. Copied from `feat/warp-sim`; the change is identical, so the branches merge cleanly. |
| `feat: Warp GPU port of the particle posterior with a batched entry point` | `model/posterior_warp.py` |
| `test: run posterior tests against both implementations; Warp vs NumPy checks` | `tests/conftest.py`, `tests/test_posterior_warp.py` |
| `feat: benchmark NumPy vs Warp posterior update and predict` | `hpc/bench_posterior.py` |
| `refactor: share posterior layout and API helpers for the GPU port` | `model/posterior.py` (Matthew's file; see below) |
| `fix: address code review in the Warp posterior` | `model/posterior_warp.py`, `tests/test_posterior_warp.py` |
| `fix: time both predict styles on one fit; match feat/warp-sim pyproject` | `hpc/bench_posterior.py`, `pyproject.toml` |

Install: `uv pip install -e '.[dev,warp]'`. The extra adds `warp-lang>=1.18`.

## Design

- **`PosteriorBatch`** holds B independent posteriors (sites × seeds) as `[B, N, P]` float64 arrays, so each SMC step is one kernel launch for every member. Members can mix resin, pla and the multi-site oracle layout. P is padded to the widest member, and kernels stop at each member's own parameter count.
- **Batched entry points** for the batched runner (`sim/batch.py`):
  - `update(ms_per_member)` takes a list, or a dict `{member: measurements}`.
  - `predict(pieces_per_member, sites=None)` returns per-member arrays of means and stds.
  - `ess()` returns `[B]`.
- **`ParticlePosterior`** is a one-member view (`batch[i]`, or built standalone) with the reference API: `update`, `predict`, `predict_interval`, `log_predictive`, `predictive_components`, `summary`, `set_prior_from_summary`, `ess`, the same `site=` handling, and `theta` / `logw` as host copies.
- **Shared with the reference:** layout, prior draws, measurement grouping, message-prior validation and summary building all come from `model.posterior.Layout` and its module helpers. For the same seed, both versions start from identical particles and accept the same inputs.
- **`theta` and `logw`** live on the GPU. Reading returns a host copy of that member only; assigning a whole array writes it back. In-place edits of the returned array do nothing.
- **Random numbers are per member.** Each member's stream depends only on its own seed and its own call count. A member inside a batch gives bit-identical results to the same posterior run alone.
- **Most work stays on the GPU.** The tempering-step search, resampling, proposal covariance, Cholesky factorization and Metropolis moves all run in kernels. The host syncs once per tempering iteration to check whether every member is done.
- **Tempering search.** The reference bisects 30 times. The Warp version runs 8 rounds of a 16-point grid search instead. Precision is the same or better, and it takes far fewer kernel launches. Members whose full remaining step is accepted in round 1 (the common case) do no further work.

## Tests

- `tests/conftest.py` runs `tests/test_posterior.py` twice, once with `[numpy]` and once with `[warp]`, without editing the test bodies.
- `tests/test_posterior_warp.py` checks:
  - Starting particles, names and tags are identical to the reference.
  - Kernel physics matches `model/physics.py` to 1e-12 (resin, pla, oracle).
  - Batched members are bit-identical to standalone runs. The batch mixes processes, includes an oracle member, and adds a message prior.
  - `PosteriorBatch` rejects a bare site string or oracle dict, and `theta` / `logw` assignment writes back to one member only.
  - Predictive means and stds on held-out pieces agree with NumPy within Monte Carlo error. Each case uses 5 seeds × 5,000 particles; the cases are resin with a message prior, pla, and the hierarchical oracle. Worst |z| was 2.9, and the largest difference in predicted mean was 0.004 mm.
- GPU tests skip cleanly when Warp or a CUDA GPU is unavailable.

## Benchmark

Run: `PYTHONPATH=. .venv/bin/python hpc/bench_posterior.py --batch 64`

Hardware: RTX 5060 Laptop GPU, Warp 1.18. Workload: 60 measurements in 3 chunks, then 200 held-out predictions. Times are after warm-up.

| particles | NumPy update | Warp update | speedup | NumPy predict ×200 | Warp ×200, one call per piece | Warp ×200, batched |
|---|---|---|---|---|---|---|
| 2,000 | 0.040 s | 0.047 s | 0.9x | 0.010 s | 0.471 s | 0.003 s |
| 20,000 | 0.576 s | 0.105 s | 5.5x | 2.91 s | 0.536 s | 0.008 s |
| 200,000 | 5.76 s | 0.583 s | 9.9x | 5.79 s | 0.817 s | 0.055 s |

64 posteriors in one batch, update plus predict:

| particles | NumPy loop (est.) | Warp batch | speedup |
|---|---|---|---|
| 2,000 | 4.54 s | 0.529 s | 8.6x |
| 20,000 | 259 s | 4.16 s | 62x |

The NumPy loop times are estimated: 8 members were timed and the result scaled to 64. NumPy times moved by up to 30% between runs because the machine was shared (see below), so read the speedups as rough.

## Known gaps

- **The benchmark ran on a shared GPU.** Another job (`python -m mirage.dynamics --train`) was using the GPU the whole time. Each wait for the GPU cost about 1.6 ms, so the Warp numbers are pessimistic, especially one-piece-at-a-time predict. Rerun on an idle GPU or on Nebius for clean numbers.
- **Single small posteriors gain nothing.** At 2k particles, per-call overhead cancels out the speedup. Calling `predict`, `log_predictive` or `predict_interval` one piece at a time is limited by GPU round trips. Bulk work should go through `PosteriorBatch`.
- **Everything is in float64.** At 200k particles, the Metropolis and likelihood kernels dominate, and laptop GPUs are slow at float64. An H100 should do much better. There is no float32 mode.
- **Results match NumPy statistically, not exactly.** The random number streams differ, and the tempering search is a grid search instead of bisection. Both searches assume ESS falls as the step grows.
- **The physics is duplicated.** The kernels repeat `model/physics.py`. The tests catch drift, but a physics change means updating the kernels too.
- **`model/posterior.py` was changed on this branch.** The refactor is behavior-preserving and in its own commit, but the file is Matthew's and contract 2 says not to change it alone. He needs to OK it before merge, or that commit gets dropped.
- **`pyproject.toml` comment.** The `warp` extra's comment names only `sim/warp_sim.py`. It is kept identical to `feat/warp-sim` so the branches merge without a conflict.
- **Limits:**
  - All members of a batch share `n`, `ess_frac` and `mh_steps`.
  - `mh_steps` must be below 16.
  - There is no CUDA graph capture, so each tempering iteration costs about 50 kernel launches. Search rounds after round 1 are still launched even when every member is done: a host check costs a sync, which measured slower.
- **Possible slowdown in the NumPy version (not investigated).** Its `predict` takes about 17 ms per piece at 20k particles. Not investigated; `model/posterior.py` is M's.

## Next

- Wire `PosteriorBatch` into `sim/batch.py` for the Phase C many-seed runs.
- Rerun the benchmark on an H100 and update the tables above.
