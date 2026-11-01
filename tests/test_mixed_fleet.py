"""make_world(independent_sites=...): named sites draw their shared parameters on their own; the rest are untouched."""
import numpy as np

from model import physics
from sim.reference import make_world

SITES = {"resin0": "resin", "pla0": "pla", "resin1": "resin", "pla1": "pla"}


def shared(printer):
    ix = physics.index(printer.process)
    return np.array([printer.theta[ix[s.name]] for s in physics.SHARED])


def test_default_unchanged_and_paired():
    base = make_world(SITES, 3)
    mixed = make_world(SITES, 3, independent_sites={"resin1", "pla1"})
    for s in ("resin0", "pla0"):  # matched sites: identical truth, so worlds stay paired
        np.testing.assert_array_equal(base[s].theta, mixed[s].theta)
        assert base[s].radial == mixed[s].radial
    for s in ("resin1", "pla1"):  # same non-shared draws, different shared ones
        assert not np.allclose(shared(base[s]), shared(mixed[s]))
        assert base[s].radial == mixed[s].radial
    assert np.array_equal(make_world(SITES, 3, independent_sites=()).get("pla1").theta, base["pla1"].theta)


def test_matches_negative_control_for_named_sites():
    ctrl = make_world(SITES, 5, independent_shared=True)
    mixed = make_world(SITES, 5, independent_sites={"pla1"})
    np.testing.assert_array_equal(ctrl["pla1"].theta, mixed["pla1"].theta)
