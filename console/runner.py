"""One practice run of the full pipeline, driven from the console instead of terminal prompts.

`Run` builds the printers (RealPrinter for "real" sites, SimPrinter for simulated ones),
runs `arms.experiment.run_experiment` in a background thread, and turns every RealPrinter
prompt into a structured `Prompt` the browser answers. The real code paths are unchanged:
the console only supplies RealPrinter's `ask=` hook and writes the hand-measurement sheet
`{plate_id}-manual.csv` that measure/real.py already reads.

Practice runs are off the books: no prereg hash, everything under console/runs/<stamp>/.
Registered real runs stay on the CLI (`run.py --source real`).
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import pickle
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from contracts import Plate
from measure.real import RealPrinter, read_manual_sheet

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path(__file__).resolve().parent / "runs"
SITES = {"resin": "resin", "pla": "pla"}
FAST_PARTICLES = 800


class Stopped(Exception):
    """Raised inside the run thread when the operator stops the run."""


# ---- stdout per run thread ---------------------------------------------------

class _Router(io.TextIOBase):
    """sys.stdout stand-in: writes from a registered run thread go to that run's log too."""

    def __init__(self, real):
        self.real, self.sinks = real, {}

    def write(self, s):
        sink = self.sinks.get(threading.get_ident())
        if sink is not None:
            sink(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


def _router() -> _Router:
    if not isinstance(sys.stdout, _Router):
        sys.stdout = _Router(sys.stdout)
    return sys.stdout


# ---- settings ----------------------------------------------------------------

@dataclass
class Settings:
    resin: str = "real"              # "real" | "sim"
    pla: str = "sim"
    rounds: int | None = None        # None = prereg
    seed: int = 0
    particles: int | None = None     # None = prereg
    share_messages: bool = True
    consistency_check: bool = False
    liar: str = ""                   # "" | a simulated site
    negative_control: bool = False   # make_world(independent_shared=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        for k in ("resin", "pla", "liar"):
            if k in d and d[k] is not None:
                setattr(s, k, str(d[k]))
        for k in ("rounds", "particles"):
            if d.get(k) not in (None, ""):
                setattr(s, k, int(d[k]))
        if d.get("seed") not in (None, ""):
            s.seed = int(d["seed"])
        for k in ("share_messages", "consistency_check", "negative_control"):
            if k in d:
                setattr(s, k, bool(d[k]))
        return s

    def mode(self, site: str) -> str:
        return getattr(self, site)

    def validate(self) -> None:
        for s in SITES:
            if self.mode(s) not in ("real", "sim"):
                raise ValueError(f"{s} must be 'real' or 'sim'")
        if self.rounds is not None and not 1 <= self.rounds <= 5:
            raise ValueError("rounds must be 1 to 5")
        if self.particles is not None and not 100 <= self.particles <= 20000:
            raise ValueError("particles must be 100 to 20000")
        if self.liar and (self.liar not in SITES or self.mode(self.liar) != "sim"):
            raise ValueError("the lying site must be a simulated site")


def build_config(settings: Settings, prereg_path: str | Path = ROOT / "prereg" / "prereg.yaml"):
    """Config as run.py's sim path builds it (prereg `config` section, no prereg hash), plus
    the prereg's real-run measurement rules for the real sites."""
    from prereg.check import load, sim_config
    prereg = load(prereg_path)[0]
    meas = prereg.get("measurement") or {}
    over = {"seed": settings.seed, "share_messages": settings.share_messages,
            "consistency_check": settings.consistency_check,
            "bad_sites": (settings.liar,) if settings.liar else (),
            "failed_plate_fraction": prereg.get("failed_plate_fraction"),
            "caliper_checks": meas.get("caliper_checks_per_plate") or 10,
            "caliper_min_pairs": meas.get("caliper_offset_min_pairs") or 3}
    if settings.rounds is not None:
        over["rounds"] = settings.rounds
    if settings.particles is not None:
        over["n_particles"] = settings.particles
    return sim_config(prereg, **over)


def prereg_defaults() -> dict:
    from prereg.check import load
    c = load(ROOT / "prereg" / "prereg.yaml")[0].get("config") or {}
    return {"rounds": c.get("rounds", 3), "particles": c.get("n_particles", 2000), "fast_particles": FAST_PARTICLES}


# ---- prompts and printers ----------------------------------------------------

@dataclass
class Prompt:
    id: int
    site: str
    kind: str                 # "approve" | "measure"
    plate_id: str
    text: str                 # RealPrinter's own prompt
    plate: dict               # pieces with slot, kind, arm, nominal_d
    stl: str                  # URL path
    caliper_slots: list = field(default_factory=list)
    note: str = ""            # e.g. "reprint" or pieces still blank
    since: float = field(default_factory=time.time)


def plate_json(plate: Plate) -> dict:
    return {"plate_id": plate.plate_id, "site": plate.site,
            "pieces": [{"piece_id": p.piece_id, "kind": p.kind, "nominal_d": p.nominal_d,
                        "row": p.slot[0], "col": p.slot[1], "arm": p.arm}
                       for p in sorted(plate.pieces, key=lambda p: p.slot)]}


class ConsolePrinter(RealPrinter):
    """A RealPrinter whose operator is the browser. It remembers the plate in hand so the
    prompt it posts can carry the drawing and the piece table."""

    def __init__(self, run: "Run", site: str, **kw):
        super().__init__(site, str(run.dir / "scans" / site), ask=self._ask, plate_dir=run.dir / "plates", **kw)
        self.run, self.plate = run, None

    def prepare(self, plate):
        self.run.check_stop()
        self.plate = plate
        self.run.progress(site=self.site, plate=plate.plate_id, step="approve")
        return super().prepare(plate)

    def print_and_measure(self, plate):
        self.run.check_stop()
        self.plate = plate
        self.run.progress(site=self.site, plate=plate.plate_id, step="measure")
        ms = super().print_and_measure(plate)
        self.run.progress(step="fitting")
        return ms

    def _ask(self, text: str) -> str:
        kind = "approve" if "approve" in text else "measure"
        return self.run.ask(self.site, kind, self.plate, text, self.scan_dir)


class SimSite:
    """Wraps a SimPrinter so a stop request lands between plates and progress shows."""

    def __init__(self, run: "Run", sim):
        self._run, self._sim = run, sim

    def __getattr__(self, name):  # rng, truth, process, ...
        return getattr(self._sim, name)

    def print_and_measure(self, plate):
        self._run.check_stop()
        self._run.progress(site=self._sim.site, plate=plate.plate_id, step="simulating")
        ms = self._sim.print_and_measure(plate)
        self._run.progress(step="fitting")
        return ms


def simulated_fill(settings: Settings, site: str, plate: Plate) -> list[dict]:
    """Plausible hand readings for a dry run: a SimPrinter of the site's process, from a
    separate copy of the run's world (so the simulated sites' noise is untouched)."""
    from sim.reference import make_world
    world = make_world(SITES, settings.seed, independent_shared=settings.negative_control)
    sim = world[site]
    import zlib

    import numpy as np
    sim.rng = np.random.default_rng([settings.seed, zlib.crc32(plate.plate_id.encode())])
    by_id = {m.piece_id: m for m in sim.print_and_measure(plate)}
    return [{"row": p.slot[0], "col": p.slot[1],
             "value": round(by_id[p.piece_id].measured_d, 4) if by_id[p.piece_id].status == "ok" else None,
             "status": by_id[p.piece_id].status}
            for p in sorted(plate.pieces, key=lambda p: p.slot)]


def to_mm(v) -> float | None:
    """mm, accepting micrometer readings in µm (anything over 100)."""
    if v in (None, ""):
        return None
    x = float(v)
    return x / 1000 if x > 100 else x


def write_sheet(path: Path, plate: Plate, rows: list[dict], source: str) -> list[tuple[int, int]]:
    """Write the hand sheet measure/real.py reads. rows: {row, col, value (mm or µm), status}
    with status ok | failed | skip. Returns the slots left blank (should be none)."""
    by_slot = {(int(r["row"]), int(r["col"])): r for r in rows}
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row", "col", "kind", "measured_d", "status", "source"])
        for p in sorted(plate.pieces, key=lambda p: p.slot):
            r = by_slot.get(p.slot, {})
            st = (r.get("status") or "ok").lower()
            d = to_mm(r.get("value")) if st == "ok" else None
            w.writerow([p.slot[0], p.slot[1], p.kind, "" if d is None else f"{d:.4f}",
                        "" if st == "ok" else st, source])
    return read_manual_sheet(path, plate)[1]


# ---- the run -----------------------------------------------------------------

def _nan_to_none(x):
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: _nan_to_none(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_nan_to_none(v) for v in x]
    return x


class Run:
    def __init__(self, settings: Settings, runs_dir: Path = RUNS):
        settings.validate()
        self.settings = settings
        self.cfg = build_config(settings)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(runs_dir) / stamp
        n = 1
        while self.dir.exists():
            n += 1
            self.dir = Path(runs_dir) / f"{stamp}-{n}"
        self.dir.mkdir(parents=True)
        self.name = self.dir.name
        self.status = "starting"          # starting | running | waiting | done | stopped | error
        self.stage = {"site": None, "plate": None, "step": "starting"}
        self.prompt: Prompt | None = None
        self._plate: Plate | None = None  # the plate the open prompt is about
        self.filled: list[str] = []       # plates whose readings came from simulated fill
        self.error = ""
        self.audit = None
        self.viewer = None
        self.log_lines: list[str] = [""]
        self._lock = threading.Lock()
        self._answer: str | None = None
        self._answered = threading.Event()
        self._stop = threading.Event()
        self._ckpt_mtime = 0.0
        self._snapshot: dict = {}
        self._designs: dict = {}          # site -> (checkpoint mtime, posterior, basis); corrected designs
        self._design_lock = threading.Lock()
        self._prompt_seq = 0
        self.started = time.time()
        self.finished = None
        (self.dir / "run.json").write_text(json.dumps(
            {"practice": True, "settings": asdict(settings), "config": json.loads(json.dumps(asdict(self.cfg)))}, indent=1))
        self.thread = threading.Thread(target=self._main, name=f"run-{self.name}", daemon=True)

    # -- thread side --

    def start(self) -> "Run":
        self.thread.start()
        return self

    def log(self, s: str) -> None:
        with self._lock:
            parts = s.split("\n")
            self.log_lines[-1] += parts[0]
            self.log_lines.extend(parts[1:])
            if len(self.log_lines) > 2000:
                del self.log_lines[:-2000]
        with open(self.dir / "log.txt", "a") as f:
            f.write(s)

    def progress(self, **kw) -> None:
        self.stage = {**self.stage, **kw}

    def check_stop(self) -> None:
        if self._stop.is_set():
            raise Stopped()

    def ask(self, site: str, kind: str, plate: Plate, text: str, scan_dir: Path) -> str:
        """Called from RealPrinter (via ConsolePrinter): post the prompt, block for the answer."""
        self.check_stop()
        note = ""
        if kind == "measure":
            todo = read_manual_sheet(Path(f"{scan_dir / plate.plate_id}-manual.csv"), plate)[1]
            if any(scan_dir.glob(f"{plate.plate_id}.failed*")):
                note = "Reprint: the first attempt failed over the prereg's limit. Reprint the same file and measure again."
            elif 0 < len(todo) < len(plate.pieces):
                note = f"{len(todo)} pieces are still blank on the sheet."
        stl = f"/runs/{self.name}/plates/{site}/{plate.plate_id}.stl"
        from measure.manual import sample_for_caliper
        cal = sample_for_caliper(plate, k=self.cfg.caliper_checks, seed=plate.seed) if kind == "approve" else []
        with self._lock:
            self._prompt_seq += 1
            self._plate = plate
            self.prompt = Prompt(self._prompt_seq, site, kind, plate.plate_id, text.strip(), plate_json(plate),
                                 stl, [list(s) for s in cal], note)
            self._answer = None
            self._answered.clear()
            self.status = "waiting"
        self.log(f"\n>> waiting on the operator at {site}: {kind} {plate.plate_id}\n")
        while not self._answered.wait(0.25):
            if self._stop.is_set():
                break
        with self._lock:
            self.prompt = None
            self.status = "running"
        self.check_stop()
        return self._answer or ""

    def _printers(self) -> dict:
        from sim.reference import make_world
        world = make_world(SITES, self.settings.seed, independent_shared=self.settings.negative_control)
        return {s: ConsolePrinter(self, s, failed_plate_fraction=self.cfg.failed_plate_fraction,
                                  caliper_checks=self.cfg.caliper_checks, caliper_min_pairs=self.cfg.caliper_min_pairs)
                if self.settings.mode(s) == "real" else SimSite(self, world[s])
                for s in SITES}

    def _main(self) -> None:
        from arms.experiment import run_experiment
        from eval.audit import audit
        router = _router()
        router.sinks[threading.get_ident()] = self.log
        try:
            self.status = "running"
            modes = ", ".join(f"{s} {self.settings.mode(s)}" for s in SITES)
            print(f"practice run {self.name}: {modes}; {self.cfg.rounds} rounds, {self.cfg.n_particles} particles, "
                  f"world seed {self.cfg.seed}" + (", NEGATIVE-CONTROL world" if self.settings.negative_control else ""))
            res = run_experiment(self._printers(), SITES, self.cfg, chain_dir=str(self.dir / "receipts"),
                                 checkpoint=str(self.dir / "state.pkl"))
            rep = audit(list(res.chains.values()))
            self.audit = {"passed": rep.passed, "crossings": rep.crossings, "chains_ok": rep.chains_ok,
                          "rejected": rep.rejected_at_boundary, "problems": rep.problems}
            print(f"privacy audit {'PASS' if rep.passed else 'FAIL'} ({rep.crossings} crossings)")
            (self.dir / "results.json").write_text(json.dumps(_nan_to_none(
                {"scores": res.scores, "trust": res.trust, "checks": res.checks, "audit": self.audit,
                 "filled_with_sim": self.filled}), indent=1))
            self.status = "done"
            self.progress(step="done", site=None, plate=None)
        except Stopped:
            print("\nstopped by the operator.")
            self.status = "stopped"
            self.progress(step="stopped", site=None)
        except Exception as e:  # show it in the console rather than killing the server
            self.error = f"{type(e).__name__}: {e}"
            print("\n" + traceback.format_exc())
            self.status = "error"
            self.progress(step="error", site=None)
        finally:
            self.finished = time.time()
            router.sinks.pop(threading.get_ident(), None)

    # -- server side --

    def answer(self, prompt_id: int, text: str) -> None:
        with self._lock:
            if self.prompt is None or self.prompt.id != prompt_id:
                raise ValueError("that prompt is no longer open")
            self._answer = text
            self._answered.set()

    def submit_measurements(self, prompt_id: int, rows: list[dict], source: str = "hand") -> None:
        p = self.prompt
        if p is None or p.id != prompt_id or p.kind != "measure":
            raise ValueError("no open measurement prompt with that id")
        plate = self._plate
        bad = [(int(r["row"]), int(r["col"])) for r in rows
               if (r.get("status") or "ok") == "ok" and not _plausible(r.get("value"))]
        if bad or len(rows) != len(plate.pieces):
            raise ValueError(f"every piece needs a diameter (0-20 mm, or µm over 100), 'failed' or 'skip'; "
                             f"check (row, col) {bad or 'missing rows'}")
        printer_dir = self.dir / "scans" / p.site
        todo = write_sheet(printer_dir / f"{p.plate_id}-manual.csv", plate, rows, source)
        if todo:
            raise ValueError(f"sheet still has blanks at {todo}")
        if source == "sim-fill":
            self.filled.append(p.plate_id)
            print(f"  {p.plate_id}: readings are SIMULATED (dry-run fill), not measurements")
        self.answer(prompt_id, "")

    def fill(self, prompt_id: int) -> list[dict]:
        p = self.prompt
        if p is None or p.id != prompt_id or p.kind != "measure":
            raise ValueError("no open measurement prompt with that id")
        return simulated_fill(self.settings, p.site, self._plate)

    def stop(self) -> None:
        self._stop.set()

    # -- corrected designs --

    def _design_post(self, site: str):
        """The networked arm's latest posterior for `site`, refit from the checkpoint (cached per checkpoint)."""
        from model import compensate as comp
        if site not in SITES:
            raise ValueError(f"unknown site {site!r}")
        ck = self.dir / "state.pkl"
        if not ck.exists():
            raise ValueError("nothing fitted yet: the seed plates aren't done")
        with self._design_lock:
            m = ck.stat().st_mtime
            hit = self._designs.get(site)
            if hit is None or hit[0] != m:
                state = comp.load_state(ck)
                hit = (m, comp.posterior_from_state(state, site), comp.basis(state, site))
                self._designs[site] = hit
            return hit[1], hit[2]

    def _sim_printer(self, site: str):
        """The simulated site's printer (same world as the run), for the hidden-truth check; None at a real site."""
        if self.settings.mode(site) != "sim":
            return None
        from sim.reference import make_world
        return make_world(SITES, self.settings.seed, independent_shared=self.settings.negative_control)[site]

    def corrected(self, site: str, kind: str, target: float) -> dict:
        """One corrected design at the plate center: draw size, predicted printed size and interval."""
        from model.compensate import compensate, true_d
        if not 0.0 < float(target) < 20.0:
            raise ValueError("target must be a diameter in mm (0-20)")
        post, b = self._design_post(site)
        r = compensate(post, kind, float(target), k=8000)
        sim = self._sim_printer(site)
        if sim is not None:
            r["sim_truth"] = {"at_draw": float(true_d(sim, kind, r["draw_d"])[0]),
                              "as_drawn": float(true_d(sim, kind, r["target_d"])[0])}
        return {"site": site, "mode": self.settings.mode(site), "basis": b, "result": r}

    def designs(self, site: str) -> dict:
        """The default table (DEFAULT_TARGETS, pins and holes) for one site."""
        from model.compensate import DEFAULT_TARGETS, table, true_d
        post, b = self._design_post(site)
        rows = table(post, DEFAULT_TARGETS, k=4000)
        sim = self._sim_printer(site)
        if sim is not None:
            for r in rows:
                r["sim_truth"] = {"at_draw": float(true_d(sim, r["kind"], r["draw_d"])[0]),
                                  "as_drawn": float(true_d(sim, r["kind"], r["target_d"])[0])}
        return {"site": site, "mode": self.settings.mode(site), "basis": b, "rows": rows,
                "filled": [p for p in self.filled if p.startswith(f"{site}-")]}

    def view(self, log_tail: int = 400) -> dict:
        self._refresh()
        with self._lock:
            prompt = asdict(self.prompt) if self.prompt else None
            log = "\n".join(self.log_lines[-log_tail:])
        return _nan_to_none({
            "name": self.name, "dir": str(self.dir.relative_to(ROOT)) if self.dir.is_relative_to(ROOT) else str(self.dir),
            "status": self.status, "stage": self.stage, "error": self.error,
            "settings": asdict(self.settings), "modes": {s: self.settings.mode(s) for s in SITES},
            "rounds": self.cfg.rounds, "particles": self.cfg.n_particles,
            "prompt": prompt, "filled": self.filled, "audit": self.audit, "viewer": self.viewer,
            "started": self.started, "finished": self.finished, "log": log, **self._snapshot,
        })

    def _refresh(self) -> None:
        """Re-read the checkpoint (written after the seed plates and every round) when it changes."""
        ck = self.dir / "state.pkl"
        try:
            m = ck.stat().st_mtime
        except FileNotFoundError:
            return
        if m == self._ckpt_mtime:
            return
        try:
            with open(ck, "rb") as f:
                state = pickle.load(f)
        except Exception:
            return  # mid-write; next poll
        self._ckpt_mtime = m
        self._snapshot = summarize_state(state)


def summarize_state(state: dict) -> dict:
    from network.protocol import deserialize
    res, sites = state["res"], state["sites"]
    numbers, msgs = 0, 0
    for c in res.chains.values():
        for e in c.entries():
            if e["kind"] == "message_out":
                msg = deserialize(e["payload"]["wire"])
                msgs += 1
                numbers += 2 * len(msg.shared_params) + len(msg.credibility) + len(msg.unmet_needs)
    return {
        "rounds_done": state["next_round"] - 1,
        "scores": res.scores, "trust": res.trust, "checks": res.checks,
        "crossed": {"messages": msgs, "numbers": numbers, "measurements": 0},
        "kept": {s: len({p.piece_id for v in [*st.data.values(), st.escrow] for p, _ in v}) for s, st in sites.items()},
    }


def _plausible(v) -> bool:
    try:
        d = to_mm(v)
    except (TypeError, ValueError):
        return False
    return d is not None and 0.0 < d < 20.0


def build_viewer(run: Run) -> str:
    """viewer.export --checkpoint for this run; returns the page's URL path."""
    import subprocess
    out = run.dir / "viewer.html"
    r = subprocess.run([sys.executable, "-m", "viewer.export", "--checkpoint", str(run.dir / "state.pkl"),
                        "--out", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "viewer failed")
    run.viewer = f"/runs/{run.name}/viewer.html"
    return run.viewer
