"""Build the Prebuilt viewer: one self-contained HTML page for a run.

    python -m viewer.export --source sim --rounds 3 --seed 0 --open
    python -m viewer.export --source sim --rounds 3 --bad-site pla --open
    python -m viewer.export --checkpoint receipts/real/state.pkl --open     # a real (or rehearsal) run

Reads only what a run already keeps (the checkpoint state: results, site data,
receipt chains). Writes viewer/out/index.html, which needs no server or network.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

from arms.experiment import ARMS, run_experiment
from eval.audit import audit
from eval.metrics import oracle_gap_closed
from model import physics
from network.protocol import deserialize

HERE = Path(__file__).parent
SITES = {"resin": "resin", "pla": "pla"}


def run_sim(args) -> dict:
    from prereg.check import load as load_prereg
    from prereg.check import sim_config
    from sim.reference import make_world

    flags = {"rounds": "rounds", "particles": "n_particles", "mh_steps": "mh_steps",
             "seed_pieces": "seed_pieces", "slots": "slots_per_arm"}
    given = {f: getattr(args, a) for a, f in flags.items() if hasattr(args, a)}
    cfg = sim_config(load_prereg(args.prereg)[0], **given, seed=args.seed,
                     bad_sites=tuple(args.bad_site), share_messages=not args.no_messages)
    with tempfile.TemporaryDirectory() as d:
        ckpt = f"{d}/state.pkl"
        run_experiment(make_world(SITES, args.seed), SITES, cfg, checkpoint=ckpt)
        return load(ckpt)


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


def _clean(x):
    """JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def plates_of(st) -> list[dict]:
    """Rebuild each printed plate from the site's (piece, measurement) pairs."""
    seen, plates = set(), {}
    for pairs in [*st.data.values(), st.escrow]:
        for p, m in pairs:
            if p.piece_id in seen:
                continue  # seed pieces sit in every arm's data
            seen.add(p.piece_id)
            plates.setdefault(m.plate_id, []).append({
                "id": p.piece_id, "kind": p.kind, "d": p.nominal_d, "slot": list(p.slot), "arm": p.arm,
                "measured": m.measured_d, "status": m.status,
            })
    order = lambda pid: -1 if pid.endswith("-seed") else int(pid.rsplit("-r", 1)[1])
    return [{"plate_id": pid, "round": max(order(pid), 0), "pieces": sorted(pcs, key=lambda q: q["slot"])}
            for pid, pcs in sorted(plates.items(), key=lambda kv: order(kv[0]))]


def messages_of(chain) -> list[dict]:
    out = []
    for e in chain.entries():
        if e["kind"] == "message_out":
            msg = deserialize(e["payload"]["wire"])
            out.append({"from": msg.sender_site, "to": e["payload"]["to"], "round": msg.round,
                        "shared_params": {k: [m, math.sqrt(v)] for k, (m, v) in msg.shared_params.items()},
                        "credibility": msg.credibility, "unmet_needs": msg.unmet_needs,
                        "bytes": len(e["payload"]["wire"]), "hash": e["hash"]})
    return out


def bundle(state: dict, label: str) -> dict:
    res, sites = state["res"], state["sites"]
    rep = audit(list(res.chains.values()))
    return _clean({
        "label": label,
        "config": res.config,
        "rounds": state["next_round"] - 1,
        "sites": {s: st.process for s, st in sites.items()},
        "arms": list(ARMS),
        "scores": res.scores,
        # Averaged over sites, as run.py reports it; the page computes per-site gaps itself.
        "gap_closed": {m: oracle_gap_closed(res.scores, m) for m in ("mae", "lpd")},
        "predictions": getattr(res, "predictions", []),
        "credibility": res.credibility,
        "trust": res.trust,
        "challenges": res.challenges,
        "spawned": res.spawned,
        "retired": res.retired,
        "plates": {s: plates_of(st) for s, st in sites.items()},
        "messages": [m for c in res.chains.values() for m in messages_of(c)],
        "private": {s: {"params": [p.name for p in physics.PARAMS[st.process] if p.tag == "site"],
                        "measurements": sum(len(v) for v in st.data.values()) + len(st.escrow)}
                    for s, st in sites.items()},
        "shared_names": [p.name for p in physics.SHARED],
        "audit": {"passed": rep.passed, "chains_ok": rep.chains_ok, "crossings": rep.crossings,
                  "rejected": rep.rejected_at_boundary, "problems": rep.problems},
        "chains": {s: [{k: e[k] for k in ("seq", "kind", "hash", "prev_hash", "payload")}
                       for e in c.entries()] for s, c in res.chains.items()},
    })


def render(data: dict) -> str:
    html = (HERE / "template.html").read_text()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return html.replace("/*__DATA__*/null", blob)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["sim"], default="sim")
    ap.add_argument("--checkpoint", help="state.pkl of a real or rehearsal run (skips the sim)")
    # Sim settings default to the prereg's `config` section (SUPPRESS = not given, keep the prereg's).
    keep = argparse.SUPPRESS
    ap.add_argument("--prereg", default="prereg/prereg.yaml", help="sim: pre-registration the config comes from")
    ap.add_argument("--rounds", type=int, default=keep)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--particles", type=int, default=keep)
    ap.add_argument("--mh-steps", type=int, default=keep)
    ap.add_argument("--bad-site", action="append", default=[])
    ap.add_argument("--no-messages", action="store_true")
    ap.add_argument("--seed-pieces", type=int, default=keep)
    ap.add_argument("--slots", type=int, default=keep)
    ap.add_argument("--out", default=str(HERE / "out" / "index.html"))
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    args = ap.parse_args()

    if args.checkpoint:
        state, label = load(args.checkpoint), f"checkpoint {args.checkpoint}"
    else:
        state = run_sim(args)
        label = f"simulation, seed {args.seed}" + (f", bad site {', '.join(args.bad_site)}" if args.bad_site else "") \
            + (", network cut" if args.no_messages else "")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(bundle(state, label)))
    print(f"wrote {out}")
    if args.open:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(out)], check=False)


if __name__ == "__main__":
    main()
