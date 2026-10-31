#!/usr/bin/env bash
# Run the Phase C sweeps on a Nebius CPU VM (or any Linux box with many cores).
#
#   scp -r <repo> nebius:prebuilt     # or git clone on the VM
#   ssh nebius 'cd prebuilt && SEED_PIECES=8 SLOTS=6 bash hpc/nebius/run_phase_c.sh'
#   scp -r nebius:prebuilt/hpc/sweeps/phase_c/results ./hpc/sweeps/phase_c/
#
# The sweeps are NumPy and CPU-bound; a GPU VM adds nothing until the Warp
# posterior lands. Results append to JSONL, so rerunning resumes a killed job.
# Override any knob through the environment, e.g. SEEDS=100 ETA=2.
set -euo pipefail
cd "$(dirname "$0")/../.."

SEEDS=${SEEDS:-100}
WORKERS=${WORKERS:-$(( $(nproc) - 1 ))}
SEED_PIECES=${SEED_PIECES:-16}
SLOTS=${SLOTS:-6}
ETA=${ETA:-20}
TRUST_INIT=${TRUST_INIT:-1.0}
CRED_FLOOR=${CRED_FLOOR:-0.05}

if [ ! -x .venv/bin/python ]; then
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  uv venv -q .venv
  # pyproject.toml lists only numpy and pyyaml; the rest are imported by plates/ and measure/.
  uv pip install -q --python .venv/bin/python numpy pyyaml pytest manifold3d opencv-python-headless trimesh matplotlib
fi
.venv/bin/python -m pytest -q

PY=".venv/bin/python hpc/sweeps/phase_c"
PLATE=(--seed-pieces "$SEED_PIECES" --slots "$SLOTS")
BASE=(--eta "$ETA" --trust-init "$TRUST_INIT" --cred-floor "$CRED_FLOOR")

$PY/seed_plate.py --seeds "$SEEDS" --rounds 4 --workers "$WORKERS"
$PY/tuning.py --stage trust "${PLATE[@]}" --seeds "$SEEDS" --workers "$WORKERS"
$PY/tuning.py --stage knobs "${PLATE[@]}" "${BASE[@]}" --seeds "$SEEDS" --workers "$WORKERS"
$PY/tuning.py --stage particles "${PLATE[@]}" "${BASE[@]}" --seeds "$SEEDS" --workers "$WORKERS"

cd hpc/sweeps/phase_c
../../../.venv/bin/python analyze.py seed_plate \
  "tuning_trust_seed${SEED_PIECES}_slots${SLOTS}" \
  "tuning_knobs_seed${SEED_PIECES}_slots${SLOTS}" \
  "tuning_particles_seed${SEED_PIECES}_slots${SLOTS}"
