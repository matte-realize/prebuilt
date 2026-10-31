import pickle
from dataclasses import asdict
from types import SimpleNamespace

import pytest

import run
from arms.experiment import Config


def test_resume_refuses_different_settings(tmp_path):
    ckpt = tmp_path / "state.pkl"
    run.check_resume(str(ckpt), Config(eta=5))  # nothing to resume yet
    ckpt.write_bytes(pickle.dumps({"res": SimpleNamespace(config=asdict(Config(eta=5, rounds=0, prereg_sha256="a")))}))
    run.check_resume(str(ckpt), Config(eta=5, rounds=3, prereg_sha256="b"))  # range committed: allowed
    with pytest.raises(SystemExit, match="eta"):
        run.check_resume(str(ckpt), Config(eta=2))


def test_resume_locks_the_simulated_sites(tmp_path):
    ckpt = tmp_path / "state.pkl"
    ckpt.write_bytes(pickle.dumps({"res": SimpleNamespace(config=asdict(Config(rounds=0, sim_sites=("pla",))))}))
    run.check_resume(str(ckpt), Config(rounds=3, sim_sites=("pla",)))
    for other in ((), ("resin",)):
        with pytest.raises(SystemExit, match="sim_sites"):
            run.check_resume(str(ckpt), Config(rounds=3, sim_sites=other))
