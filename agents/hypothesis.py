"""Hypothesis agent (spec 6.2; walkthrough Sat night, exploratory).

Between rounds, for each site: summarize what the site's networked model gets
wrong, ask a language model (Nemotron) for candidate effects and the test pieces
that would check them, validate the answer, and record it on a per-site
hypothesis receipt chain. Nothing here enters the auction or changes the run.

The model sees aggregates only: standardized residuals binned by kind and size,
residual trends against plate position and size, and the unmet-needs log. That is
no more than what may already cross a site boundary (spec 6.3), so the endpoint
can be local (NIM on the DGX Spark, the default) or hosted.

    python -m agents.hypothesis --checkpoint receipts/real/state.pkl --dry-run   # print the prompts
    python -m agents.hypothesis --checkpoint receipts/real/state.pkl             # ask and record

Endpoint: PREBUILT_LLM_URL (OpenAI-compatible, default http://localhost:8000/v1),
PREBUILT_LLM_MODEL, and NVIDIA_API_KEY if the endpoint needs one.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pickle
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

from model.physics import PARAMS, PieceArrays
from plates import spec
from receipts.chain import ReceiptChain, canonical, sha256

DEFAULT_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
MAX_HYPOTHESES, MAX_PIECES, MAX_TEXT = 3, 6, 300

SYSTEM = (
    "You are the hypothesis agent in a collective of agents characterizing a 3D printer "
    "from printed test pins and holes. You see only summary statistics of where the "
    "current physics model's predictions miss. Propose at most 3 candidate effects the "
    "model does not capture, each with up to 6 test pieces (pin or hole, nominal diameter "
    "in mm) whose measurements would confirm or refute it. Prefer effects the statistics "
    "actually support; say so if nothing stands out. Reply with a JSON array only: "
    '[{"effect": str, "evidence": str, "test_pieces": [{"kind": "pin"|"hole", "d": number}], '
    '"prediction": str}]'
)


# ---- summary (site-local aggregates) ------------------------------------------

def _trend_z(x: np.ndarray, y: np.ndarray) -> float:
    from arms.experiment import _trend_z as tz
    return round(float(tz(x, y)), 2)


def residual_summary(st, pieces, cfg, rng) -> dict:
    """Aggregates of the site's networked-model residuals on its own training data."""
    from arms.experiment import _fit
    ok = [(p, m) for p, m in st.data["networked"] if m.status == "ok"]
    failed = [p for p, m in st.data["networked"] if m.status == "failed"]
    out = {"site_process": st.process, "n_measured": len(ok), "n_failed": len(failed),
           "model_parameters": [s.name for s in PARAMS[st.process]],
           "failed_pieces": sorted({f"{p.kind} {p.nominal_d:.1f}" for p in failed})[:20]}
    if len(ok) < 4:
        return out | {"note": "too few measurements to summarize"}
    post = _fit(st, pieces, st.data["networked"], cfg, rng, st.inbox)
    z = np.array([(m.measured_d - mu) / sd for (p, m) in ok for mu, sd in [post.predict(p)]])
    x = PieceArrays.from_pieces([p for p, _ in ok])
    bins: dict[tuple, list[float]] = defaultdict(list)
    for (p, _), zi in zip(ok, z):
        bins[(p.kind, int(p.nominal_d))].append(float(zi))
    out["residual_z_by_bin"] = [
        {"kind": k, "d_mm": f"{lo}-{lo + 1}", "n": len(v), "mean_z": round(float(np.mean(v)), 2)}
        for (k, lo), v in sorted(bins.items())]
    out["residual_z_overall"] = {"mean": round(float(z.mean()), 2), "sd": round(float(z.std()), 2)}
    out["residual_trend_z"] = {  # t statistic of each correlation; |z| > 2 is notable
        "radial_distance_sq": _trend_z((x.u**2 + x.v**2) / 2, z),
        "column_position": _trend_z(x.u, z),
        "row_position": _trend_z(x.v, z),
        "inverse_diameter": _trend_z(1 / x.d, z),
        "hole_vs_pin": _trend_z(x.is_hole.astype(float), z),
    }
    incoming = [u for msg in st.inbox.values() for u in getattr(msg, "unmet_needs", [])]
    out["unmet_needs"] = {"own": list(st.unmet_out), "from_other_sites": incoming}
    return out


def messages(summary: dict) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Residual summary for one site:\n" + json.dumps(summary, indent=1)}]


# ---- model call ----------------------------------------------------------------

def ask_llm(msgs: list[dict], url: str | None = None, model: str | None = None, timeout: float = 120) -> str:
    url = (url or os.environ.get("PREBUILT_LLM_URL") or DEFAULT_URL).rstrip("/")
    body = {"model": model or os.environ.get("PREBUILT_LLM_MODEL") or DEFAULT_MODEL,
            "messages": msgs, "temperature": 0.2, "max_tokens": 1024}
    headers = {"Content-Type": "application/json"}
    if os.environ.get("NVIDIA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['NVIDIA_API_KEY']}"
    req = urllib.request.Request(f"{url}/chat/completions", json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


# ---- validation ----------------------------------------------------------------

def parse(text: str) -> list[dict]:
    """Validated hypotheses from the model's reply; anything malformed is dropped."""
    m = re.search(r"\[.*\]", text, re.S)
    try:
        raw = json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []
    out = []
    for h in raw if isinstance(raw, list) else []:
        if not isinstance(h, dict) or not isinstance(h.get("effect"), str):
            continue
        pieces = []
        for tp in h.get("test_pieces") or []:
            try:
                kind, d = tp["kind"], float(tp["d"])
            except (KeyError, TypeError, ValueError):
                continue
            if kind not in ("pin", "hole") or not spec.D_MIN <= d <= spec.D_MAX:
                continue
            snapped = round(round(d / spec.D_STEP) * spec.D_STEP, 1)  # onto the piece library grid
            if {"kind": kind, "d": snapped} not in pieces:
                pieces.append({"kind": kind, "d": snapped})
        out.append({"effect": h["effect"][:MAX_TEXT], "evidence": str(h.get("evidence", ""))[:MAX_TEXT],
                    "prediction": str(h.get("prediction", ""))[:MAX_TEXT], "test_pieces": pieces[:MAX_PIECES]})
    return out[:MAX_HYPOTHESES]


# ---- driver --------------------------------------------------------------------

def run(state: dict, ask=ask_llm, out_dir: str | Path | None = None, dry_run: bool = False) -> dict[str, dict]:
    """Hypotheses per site for the latest completed round of a checkpointed run."""
    from arms.experiment import Config
    res, sites, pieces = state["res"], state["sites"], state["pieces"]
    names = {f.name for f in dataclasses.fields(Config)}
    cfg = Config(**{k: tuple(v) if isinstance(v, list) else v for k, v in res.config.items() if k in names})
    rnd = state["next_round"] - 1
    rng = np.random.default_rng(10_000 + rnd)
    out = {}
    for s, st in sites.items():
        summary = residual_summary(st, pieces, cfg, rng)
        msgs = messages(summary)
        if dry_run:
            out[s] = {"round": rnd, "summary": summary, "messages": msgs}
            continue
        reply = ask(msgs)
        hyps = parse(reply)
        entry = {"round": rnd, "model": os.environ.get("PREBUILT_LLM_MODEL") or DEFAULT_MODEL,
                 "summary": summary, "prompt_hash": sha256(canonical(msgs)), "reply_hash": sha256(reply),
                 "hypotheses": hyps}
        if out_dir:
            ReceiptChain(f"{s}-hypotheses", str(Path(out_dir) / f"{s}-hypotheses.jsonl")).append("hypothesis", entry)
        out[s] = entry
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default="receipts/real/state.pkl")
    ap.add_argument("--dry-run", action="store_true", help="print the prompts, call nothing")
    ap.add_argument("--out-dir", default=None, help="hypothesis chains (default: the checkpoint's directory)")
    a = ap.parse_args()
    with open(a.checkpoint, "rb") as f:
        state = pickle.load(f)
    result = run(state, out_dir=a.out_dir or str(Path(a.checkpoint).parent), dry_run=a.dry_run)
    for s, r in result.items():
        print(f"\n=== {s}, after round {r['round']} ===")
        if a.dry_run:
            print(r["messages"][1]["content"])
        else:
            for h in r["hypotheses"] or [{"effect": "(nothing valid proposed)", "test_pieces": []}]:
                pcs = ", ".join(f"{p['kind']} {p['d']}" for p in h["test_pieces"])
                print(f"- {h['effect']}\n    test: {pcs or 'none'}")


if __name__ == "__main__":
    main()
