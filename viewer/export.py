"""Build the Prebuilt viewer: one self-contained HTML page for a run.

    python -m viewer.export --source sim --rounds 3 --seed 0 --open            # 3D demo
    python -m viewer.export --source sim --rounds 3 --report --open            # scrolling report
    python -m viewer.export --source sim --rounds 3 --bad-site pla --open
    python -m viewer.export --checkpoint receipts/real/state.pkl --open     # a real (or rehearsal) run

Reads only what a run already keeps (the checkpoint state: results, site data,
receipt chains). Writes viewer/out/index.html. No server needed; the 3D demo loads three.js from a CDN.
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

from arms.experiment import ARMS, Config, run_experiment
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
                     bad_sites=tuple(args.bad_site), share_messages=not args.no_messages,
                     consistency_check=getattr(args, "consistency_check", False))
    with tempfile.TemporaryDirectory() as d:
        ckpt = f"{d}/state.pkl"
        run_experiment(make_world(SITES, args.seed), SITES, cfg, checkpoint=ckpt)
        return load(ckpt)


def _condition_run(job) -> tuple:
    seed, cond, rounds, liar = job
    from sim.reference import make_world
    cfg = Config(rounds=rounds, seed=seed, share_messages=cond != "alone", bad_sites=(liar,) if cond == "liar" else ())
    res = run_experiment(make_world(SITES, seed), SITES, cfg)
    mae = lambda arm: sum(r["mae"] for r in res.scores if r["round"] == rounds and r["arm"] == arm) / len(SITES)
    return cond, seed, mae("isolated"), mae("networked")


def condition_summary(seeds: int, rounds: int, liar: str) -> dict:
    """Final-round error, together vs. alone, for each demo condition over many simulated worlds."""
    import statistics
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(s, c, rounds, liar) for s in range(seeds) for c in ("normal", "alone", "liar")]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_condition_run, jobs))
    out = {"seeds": seeds, "rounds": rounds}
    for c in ("normal", "alone", "liar"):
        pct = [(iso - net) / iso * 100 for cc, _, iso, net in rows if cc == c]
        out[c] = {"median_pct_closer": statistics.median(pct), "wins": sum(p > 0 for p in pct), "pct_by_seed": pct}
    team = {(c, s): net for c, s, _, net in rows}
    paired = [(team["alone", s] - team["normal", s]) / team["alone", s] * 100 for s in range(seeds)]
    out["notes_vs_none"] = {"median_pct_better": statistics.median(paired), "wins": sum(p > 0 for p in paired)}
    return out


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
        "checks": getattr(res, "checks", []),  # consistency check rows, when the run had it on
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


def render(data: dict, fragment: bool = False, page: str = "demo.html") -> str:
    html = (HERE / page).read_text()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", blob)
    if not fragment:  # inline three.js (viewer/vendor, MIT) so the page works offline; fragments keep the CDN
        for url, name in (("https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js", "three.min.js"),
                          ("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js", "OrbitControls.js")):
            tag = f'<script src="{url}"></script>'
            if tag in html:
                code = (HERE / "vendor" / name).read_text().replace("</script", "<\\/script")
                html = html.replace(tag, f"<script>/* {name}, three.js r128, MIT */\n{code}\n</script>", 1)
    if fragment:  # for hosts that supply their own document skeleton (claude.ai artifacts)
        for tag in ("<!doctype html>", '<html lang="en">', "<head>", "</head>", "<body>", "</body>", "</html>",
                    '<meta charset="utf-8">',
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'):
            html = html.replace(tag, "", 1)
    return html


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
    ap.add_argument("--consistency-check", action="store_true", help="receivers drop notes that contradict their own data")
    ap.add_argument("--seed-pieces", type=int, default=keep)
    ap.add_argument("--slots", type=int, default=keep)
    ap.add_argument("--out", default=str(HERE / "out" / "index.html"))
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    ap.add_argument("--report", action="store_true", help="the scrolling report instead of the 3D demo")
    ap.add_argument("--single", action="store_true", help="3D demo: skip the extra 'no sharing', 'one site lies' and 'lies, checked' runs")
    ap.add_argument("--summary-seeds", type=int, default=0, help="3D demo: worlds per condition in the summary (0 = none)")
    ap.add_argument("--liar", default="pla", choices=list(SITES), help="3D demo: the site that lies in the 'one site lies' run")
    ap.add_argument("--fragment", action="store_true", help="omit <html>/<head>/<body>, for hosts that add their own")
    args = ap.parse_args()

    if args.checkpoint:
        state, label = load(args.checkpoint), f"checkpoint {args.checkpoint}"
        data = bundle(state, label)
    else:
        label = f"simulation, seed {args.seed}" + (f", bad site {', '.join(args.bad_site)}" if args.bad_site else "") \
            + (", network cut" if args.no_messages else "") + (", consistency check" if args.consistency_check else "")
        data = bundle(run_sim(args), label)
    if not args.report and not args.checkpoint and not args.single:
        # The 3D demo lets viewers flip conditions, so it carries two more real runs on the same world:
        # the network cut, one site broadcasting bad beliefs, and the same with the consistency check on.
        print("running the 'no sharing', 'one site lies' and 'lies, checked' conditions for the demo switches...")
        alone = bundle(run_sim(argparse.Namespace(**{**vars(args), "no_messages": True, "bad_site": []})), label + ", network cut")
        liar = bundle(run_sim(argparse.Namespace(**{**vars(args), "no_messages": False, "bad_site": [args.liar]})), label + f", bad site {args.liar}")
        liar_check = bundle(run_sim(argparse.Namespace(**{**vars(args), "no_messages": False, "bad_site": [args.liar], "consistency_check": True})),
                            label + f", bad site {args.liar}, consistency check")
        data = {"scenarios": {"normal": data, "alone": alone, "liar": liar, "liar_check": liar_check}, "liar": args.liar, "seed": args.seed}
        if args.summary_seeds:
            print(f"running each condition on {args.summary_seeds} simulated worlds for the summary...")
            data["summary"] = condition_summary(args.summary_seeds, args.rounds, args.liar)
    ev = HERE / "evidence.json"  # hpc/sweeps/relevance/evidence.py: the many-world results the demo may cite
    if not args.report and ev.exists():
        data = data if "scenarios" in data else {"scenarios": {"normal": data}}
        data["evidence"] = json.loads(ev.read_text())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data, args.fragment, "template.html" if args.report else "demo.html"))
    print(f"wrote {out}")
    if args.open:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(out)], check=False)


if __name__ == "__main__":
    main()
