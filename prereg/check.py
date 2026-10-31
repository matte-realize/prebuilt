"""Load and check the pre-registration; build the experiment Config from it.

    python -m prereg.check             # list missing fields, print the sha256
    python -m prereg.check --stage round1
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import yaml

PREREG = Path(__file__).resolve().parent / "prereg.yaml"
# The predicted range is committed after seed calibration (Phase D), so the seed plate may run without it.
LATE = ("predicted_range.range",)
METRICS = ("iso_minus_net_mae_um", "oracle_gap_closed_mae")


def load(path: str | Path = PREREG) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def missing(prereg: dict, stage: str = "seed") -> list[str]:
    """Dotted paths of null fields that must be filled before `stage` ("seed" or "round1")."""
    out = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}" if path else k)
        elif isinstance(v, list):
            if any(x is None for x in v):
                out.append(path)
            for i, x in enumerate(v):
                if isinstance(x, (dict, list)):
                    walk(x, f"{path}[{i}]")
        elif v is None:
            out.append(path)

    walk(prereg, "")
    if stage == "seed":
        out = [p for p in out if not p.startswith(LATE)]
    metric = (prereg.get("predicted_range") or {}).get("metric")
    if metric is not None and metric not in METRICS:
        out.append(f"predicted_range.metric (unknown {metric!r}; one of {', '.join(METRICS)})")
    return out


def check_heldout(prereg: dict, root: Path = PREREG.parent.parent) -> None:
    h = prereg["heldout"]
    manifest = json.loads((root / h["manifest"]).read_text())
    if manifest["sha256"] != h["manifest_sha256"]:
        raise ValueError("held-out manifest changed since pre-registration")
    if [list(s) for s in manifest["slots"]] != h["slots"]:
        raise ValueError("held-out slots differ from the manifest")


def config_from(prereg: dict, sha256: str, **overrides):
    """arms.experiment.Config from the prereg's `config` section; `overrides` win (e.g. particles)."""
    from arms.experiment import Config
    fields = {f.name for f in dataclasses.fields(Config)}
    cfg = dict(prereg["config"])
    unknown = set(cfg) - fields
    if unknown:
        raise ValueError(f"prereg config has unknown fields: {sorted(unknown)}")
    cfg = {k: v for k, v in cfg.items() if v is not None}
    if "dormant" in cfg:
        cfg["dormant"] = tuple(cfg["dormant"])
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return Config(**cfg, prereg_sha256=sha256)


def sim_config(prereg: dict, **overrides):
    """Config for a simulated run: the prereg's `config` section, so sim numbers match what is
    registered. `overrides` win, even None (lpd_clip=None = unclipped). Overriding n_particles
    alone also moves the oracle's, as in Config. No prereg hash: that marks a real run."""
    if "n_particles" in overrides:
        overrides.setdefault("oracle_particles", None)
    return dataclasses.replace(config_from(prereg, None), **overrides)


def fit_thresholds(prereg: dict) -> dict | None:
    """process -> fit-class thresholds, or None until every threshold is filled in."""
    fc = prereg.get("fit_classes_mm") or {}
    return None if any(p.startswith("fit_classes_mm") for p in missing(prereg)) or not fc else fc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["seed", "round1"], default="seed")
    ap.add_argument("--path", default=str(PREREG))
    a = ap.parse_args()
    prereg, sha = load(a.path)
    check_heldout(prereg)
    config_from(prereg, sha)  # fails loudly on unknown keys
    gaps = missing(prereg, a.stage)
    print(f"sha256 {sha}")
    print(f"ready for {a.stage}" if not gaps else f"missing before {a.stage}:\n  " + "\n  ".join(gaps))
    raise SystemExit(1 if gaps else 0)


if __name__ == "__main__":
    main()
