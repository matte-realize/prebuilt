"""The frozen experiment config from prereg/prereg.yaml, as an arms.experiment.Config.

Sweeps build their Config here so they track the prereg (e.g. 4000 particles, 6 MH steps)
instead of the code defaults, which can lag behind it.
"""
from dataclasses import fields, replace
from pathlib import Path

import yaml

from arms.experiment import Config

PREREG = Path(__file__).resolve().parents[3] / "prereg" / "prereg.yaml"


def frozen_config(**overrides) -> Config:
    raw = yaml.safe_load(PREREG.read_text())["config"]
    known = {f.name for f in fields(Config)}
    cfg = {k: tuple(v) if isinstance(v, list) else v for k, v in raw.items() if k in known}
    return replace(Config(**cfg), **overrides)
