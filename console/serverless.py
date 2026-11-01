"""One complete simulated run per request, for hosts without a long-lived server (Vercel).

The local console (`python -m console`) runs in a background thread and keeps state between
requests, which also lets a real printer stop and wait for an operator. A serverless function
can't, so this runs the whole thing synchronously (~7 s at the registered settings) and returns
everything the page plays back: plates, notes, scores, trust, checks, the audit, the corrected-
design table for each site and a grid of corrected designs for the "your turn" step.
Simulated printers only.
"""
from __future__ import annotations

import json
import pickle
import sys
import tempfile
from pathlib import Path

import numpy as np

from console import runner

GRID = [round(x, 1) for x in np.arange(1.0, 8.01, 0.1)]  # "your turn": any size 1-8 mm, 0.1 mm steps
GRID_SITE = "resin"
# Runs computed ahead (`python -m console.serverless --bake`), same code and settings: on Vercel's 1 vCPU a run takes
# ~35 s, so the walkthrough's two runs (world 4, honest and with a lying printer) load from here. Any other setting runs fresh.
CACHE = Path(__file__).resolve().parent / "data" / "runs"
BAKE = [{"seed": "4", "rounds": "3"}, {"seed": "4", "rounds": "3", "liar": "pla", "consistency_check": True}]


def _key(st, cfg) -> str:
    return (f"w{st.seed}-r{cfg.rounds}-p{cfg.n_particles}-{'notes' if st.share_messages else 'nonotes'}"
            f"{'-control' if st.negative_control else ''}{'-liar-' + st.liar if st.liar else ''}{'-check' if st.consistency_check else ''}")


def simulate(body: dict) -> dict:
    from arms.experiment import run_experiment
    from eval.audit import audit
    from model import compensate as comp
    from sim.reference import make_world

    st = runner.Settings.from_dict({**body, "resin": body.get("resin", "sim"), "pla": body.get("pla", "sim")})
    if any(st.mode(s) == "real" for s in runner.SITES):
        raise ValueError("real printers need the local console (python -m console)")
    st.validate()
    cfg = runner.build_config(st)
    hit = CACHE / f"{_key(st, cfg)}.json"
    if hit.exists() and not body.get("fresh"):
        return {**json.loads(hit.read_text()), "cached": True}
    world = lambda: make_world(runner.SITES, st.seed, independent_shared=st.negative_control)
    with tempfile.TemporaryDirectory() as d:
        res = run_experiment(world(), runner.SITES, cfg, chain_dir=f"{d}/receipts", checkpoint=f"{d}/state.pkl")
        with open(f"{d}/state.pkl", "rb") as f:
            state = pickle.load(f)
        rep = audit(list(res.chains.values()))  # the receipt logs live in the temp dir: read them before it goes
        snap = runner.summarize_state(state)
    truth = world()  # a separate copy of the same world: the hidden true sizes, never seen by the run

    designs, corrected = {}, {}
    for s in runner.SITES:
        post = comp.posterior_from_state(state, s)
        rows = comp.table(post, comp.DEFAULT_TARGETS, k=4000)
        for r in rows:
            r["sim_truth"] = {"at_draw": float(comp.true_d(truth[s], r["kind"], r["draw_d"])[0]),
                              "as_drawn": float(comp.true_d(truth[s], r["kind"], r["target_d"])[0])}
        designs[s] = {"site": s, "mode": "sim", "basis": comp.basis(state, s), "rows": rows, "filled": []}
        if s == GRID_SITE:
            grid = {}
            for kind in ("hole", "pin"):
                for t in GRID:
                    r = comp.compensate(post, kind, t, k=4000)
                    grid[f"{kind}:{t:.1f}"] = {
                        "kind": kind, "target_d": t, "draw_d": r["draw_d"], "predicted_d": r["predicted_d"],
                        "interval": r["interval"], "shift_um": r["shift_um"], "notes": r["notes"], "clipped": r["clipped"],
                        "as_drawn": {"predicted_d": r["as_drawn"]["predicted_d"]},
                        "sim_truth": {"at_draw": float(comp.true_d(truth[s], kind, r["draw_d"])[0]),
                                      "as_drawn": float(comp.true_d(truth[s], kind, t)[0])}}
            corrected[s] = grid

    return runner._nan_to_none({
        "name": f"vercel-{st.seed}", "dir": "", "status": "done", "stage": {"step": "done"}, "error": "",
        "settings": runner.asdict(st), "modes": {s: "sim" for s in runner.SITES},
        "rounds": cfg.rounds, "particles": cfg.n_particles, "prompt": None, "filled": [], "viewer": None, "log": "",
        "audit": {"passed": rep.passed, "crossings": rep.crossings, "chains_ok": rep.chains_ok,
                  "rejected": rep.rejected_at_boundary, "problems": rep.problems},
        **snap,
        "designs": designs, "corrected": corrected, "oneshot": True,
    })


def bake() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for b in BAKE:
        st = runner.Settings.from_dict({**b, "resin": "sim", "pla": "sim"})
        out = CACHE / f"{_key(st, runner.build_config(st))}.json"
        out.write_text(json.dumps(simulate({**b, "fresh": True}), separators=(",", ":")))
        print(f"wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")


if __name__ == "__main__":
    if "--bake" in sys.argv:
        bake()
