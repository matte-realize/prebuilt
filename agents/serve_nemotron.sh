#!/usr/bin/env bash
# Serve a Nemotron model with an OpenAI-compatible API on a GPU box (e.g. an NVIDIA Brev
# instance) for the hypothesis agent. Then, from the laptop:
#   brev port-forward <instance> --port 8000:8000     (or an ssh -L tunnel)
#   python -m agents.hypothesis --ping
#
# MODEL defaults to an 8B Nemotron that fits one 24 GB GPU (L4, A10). Check the current
# name on huggingface.co/nvidia; a NIM container (nvcr.io/nim/...) works too.
set -euo pipefail
MODEL="${MODEL:-nvidia/Llama-3.1-Nemotron-Nano-8B-v1}"
PORT="${PORT:-8000}"
python3 -m pip install --quiet vllm
exec python3 -m vllm.entrypoints.openai.api_server --model "$MODEL" --port "$PORT" --max-model-len 8192
