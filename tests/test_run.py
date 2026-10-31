import pickle
from dataclasses import asdict
from types import SimpleNamespace

import pytest

import run
from arms.experiment import Config


def test_resume_refuses_a_different_config(tmp_path):
    ckpt = tmp_path / "state.pkl"
    run.check_resume(str(ckpt), Config(eta=5))  # nothing to resume yet
    ckpt.write_bytes(pickle.dumps({"res": SimpleNamespace(config=asdict(Config(eta=5)))}))
    run.check_resume(str(ckpt), Config(eta=5))
    with pytest.raises(SystemExit, match="eta"):
        run.check_resume(str(ckpt), Config(eta=2))
