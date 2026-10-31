import json

from arms.experiment import Config, run_experiment
from run import SITES
from sim.reference import make_world
from viewer.export import bundle, load, render


def test_viewer_page_from_checkpoint(tmp_path):
    ckpt = tmp_path / "state.pkl"
    run_experiment(make_world(SITES, 0), SITES, Config(rounds=2, n_particles=300), checkpoint=str(ckpt))
    data = bundle(load(str(ckpt)), "test")
    json.dumps(data, allow_nan=False)  # the page's JSON must be strict
    assert data["rounds"] == 2 and data["audit"]["passed"]
    assert {p["arm"] for p in data["predictions"]} == {"isolated", "networked", "oracle"}
    html = render(data)
    assert "/*__DATA__*/null" not in html and '"label":"test"' in html
