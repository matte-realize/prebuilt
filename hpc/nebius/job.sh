#!/usr/bin/env bash
# Runs inside a Nebius AI job (injected by submit.sh). Clones the repo at $GIT_REF,
# installs it with the CUDA 12 Warp wheel, checks the GPU, then runs $CMD from the
# repo root with $OUT pointing into the results bucket.
set -euo pipefail
mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
echo "job $JOB_NAME, ref $GIT_REF, started $(date -u +%FT%TZ)"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

git clone -q https://github.com/matte-realize/prebuilt.git /work/prebuilt
cd /work/prebuilt
git checkout -q "$GIT_REF"
echo "commit $(git rev-parse HEAD)"

pip install -q uv
uv venv -q .venv
# The default PyPI warp-lang needs a CUDA 13 driver and silently falls back to CPU otherwise;
# the cu12 build runs on any CUDA 12+ driver.
uv pip install -q --python .venv/bin/python -e ".[dev]" \
  "warp-lang @ https://github.com/NVIDIA/warp/releases/download/v1.18.0/warp_lang-1.18.0%2Bcu12-py3-none-manylinux_2_28_x86_64.whl"
.venv/bin/python -c "import warp as wp; wp.init(); assert wp.get_cuda_devices(), 'Warp sees no CUDA device'; print('warp devices', wp.get_cuda_devices())"

export PATH="/work/prebuilt/.venv/bin:$PATH"
echo "running: $CMD"
status=0
bash -c "$CMD" || status=$?
echo "finished $(date -u +%FT%TZ), exit $status"
exit "$status"
