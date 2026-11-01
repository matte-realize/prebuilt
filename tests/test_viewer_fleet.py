"""The fleet page: site naming matches the coldstart sweep, and the template renders offline with its data."""
import json

from viewer.export import FLEET_SEED, FLEET_SETUP, fleet_sites, render


def test_fleet_sites_match_coldstart():
    assert fleet_sites(8) == {f"{p}{i}": p for i in range(4) for p in ("resin", "pla")}
    assert FLEET_SETUP == {"seed_pieces": 4, "slots": 2, "rounds": 3} and isinstance(FLEET_SEED, int)


def test_fleet_template_renders_offline():
    run = {"rounds": 1, "sites": {"resin0": "resin", "pla0": "pla"}, "plates": {}, "messages": [], "audit": {},
           "scores": [{"round": 1, "site": s, "arm": a, "mae_truth": 0.02} for s in ("resin0", "pla0") for a in ("isolated", "networked")]}
    html = render({"runs": {"share": run, "alone": run}, "seed": 1, "setup": FLEET_SETUP, "n": 2}, False, "fleet.html")
    assert "/*__DATA__*/null" not in html and '"seed_pieces":4' in html
    assert "cdnjs.cloudflare.com" not in html and "three.min.js, three.js r128, MIT" in html  # three.js inlined
    blob = html[html.index("const BLOB = ") + 13: html.index(";\nconst $ = ")]
    assert json.loads(blob.replace("<\\/", "</"))["runs"]["share"]["rounds"] == 1
