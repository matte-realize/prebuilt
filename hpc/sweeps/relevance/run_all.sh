#!/usr/bin/env bash
# All relevance sweeps on the frozen prereg config, then the demo evidence. ~45 min on 18 cores.
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONPATH=.
R=hpc/sweeps/relevance
.venv/bin/python $R/worlds.py 100 $R/results/worlds.jsonl
echo "worlds done"
.venv/bin/python $R/saboteur.py 100 $R/results/saboteur.jsonl
echo "saboteur done"
.venv/bin/python $R/regimes.py $R/results/regimes.jsonl
echo "regimes done"
.venv/bin/python $R/evidence.py
