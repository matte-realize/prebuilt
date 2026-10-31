#!/usr/bin/env bash
# Submit a one-GPU job (H100) to Nebius that runs a command on a fresh clone of the repo.
#
#   hpc/nebius/submit.sh <name> <git-ref> '<command>' [timeout]
#   hpc/nebius/submit.sh scaling feat/phase-d-eval \
#     'python hpc/sweeps/phase_d/sweep.py scaling --workers 14 && cp hpc/sweeps/phase_d/results/*.jsonl $OUT/' 4h
#
# The job clones GitHub at <git-ref>, so push first. The command runs from the repo
# root with the venv on PATH; write outputs to $OUT, which is
# <name>-<UTC time>/ in bucket prebuilt-results-20261031 (Nebius console: Storage >
# Buckets). $OUT/job.log holds the full log; `nebius ai logs <job id>` streams it.
#
# Event rules: one GPU per job; a job waits up to 30 min for a free GPU, then fails;
# timeout at least 1h. The project is shared with every team: job names get a
# "prebuilt-" prefix, and nothing secret goes in the command or the environment.
set -euo pipefail

if [ $# -lt 3 ]; then
  sed -n 2,16p "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
name=$1 ref=$2 cmd=$3 timeout=${4:-2h}
NEBIUS=${NEBIUS:-$(command -v nebius || echo "$HOME/.nebius/bin/nebius")}
BUCKET=storagebucket-e001675725228279791494  # prebuilt-results-20261031
SUBNET=vpcsubnet-e00tc2metkvjckkqqp          # default-subnet-fp1cxpow

# a branch or tag on origin, or a commit some pushed branch contains
if ! git ls-remote --exit-code origin "$ref" >/dev/null 2>&1 && [ -z "$(git branch -r --contains "$ref" 2>/dev/null)" ]; then
  echo "ref $ref is not on origin; push it first" >&2
  exit 1
fi

job="prebuilt-$name-$(date -u +%m%d-%H%M%S)"
"$NEBIUS" ai job create \
  --name "$job" \
  --image nvcr.io/nvidia/pytorch:25.12-py3 \
  --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb \
  --disk-size 100Gi --shm-size 16Gi \
  --subnet-id "$SUBNET" \
  --timeout "$timeout" \
  --volume "$BUCKET:/out:rw" \
  --inject-file "$(dirname "$0")/job.sh:/work/job.sh" \
  --env "JOB_NAME=$job" --env "GIT_REF=$ref" --env "OUT=/out/$job" --env "CMD=$cmd" \
  --container-command bash --args /work/job.sh \
  --async ${DRY_RUN:+--dry-run}
[ -n "${DRY_RUN:-}" ] || echo "submitted $job; outputs in bucket prebuilt-results-20261031 under $job/"
