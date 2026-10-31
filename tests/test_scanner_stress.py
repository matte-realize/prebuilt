"""The stress harness itself: degradations land where intended and the fix prototypes stay accurate."""
import numpy as np
import pytest

from hpc.scanner_stress.degrade import Defects, Geometry, make_scan
from hpc.scanner_stress.fixes import measure_variant
from measure.scanner import measure_scan
from plates import spec
from plates.layout import load_plate


@pytest.fixture(scope="module")
def plate():
    return load_plate("plates/out/resin/resin-seed.json")


def _truth(plate, seed=0):
    rng = np.random.default_rng(seed)
    return {p.piece_id: p.nominal_d + rng.normal(0, 0.1) for p in plate.pieces}


def test_clean_scan_matches_render_scan_accuracy(plate):
    true = _truth(plate)
    img = make_scan(plate, true, "holes", Defects(), seed=1)
    ms, _ = measure_scan(img, plate, "holes")
    err = np.array([m.measured_d - true[m.piece_id] for m in ms])
    assert np.abs(err).max() < 0.025


@pytest.mark.parametrize("angle", [7.0, 45.0])  # 45 deg needs a wider canvas than render_scan's default
def test_geometry_finds_pins(plate, angle):
    true = _truth(plate)
    df = Defects(angle_deg=angle, mirror=True, blur_px=0, noise=0)
    img = make_scan(plate, true, "pins", df, seed=0)
    geo = Geometry.of(df.dpi, angle, True)
    for p in plate.pieces:
        x, y = np.round(geo.to_px(spec.slot_center(*p.slot))).astype(int)
        assert img[y, x] > 200 if p.kind == "pin" else img[y, x] < 30  # pin tops bright, holes dark


def test_shadow_darkens_plate_beside_pins_only(plate):
    true = _truth(plate)
    clean = make_scan(plate, true, "pins", Defects(angle_deg=0.0, mirror=False, blur_px=0, noise=0), seed=0)
    shad = make_scan(plate, true, "pins", Defects(angle_deg=0.0, mirror=False, blur_px=0, noise=0, shadow_mm=0.5), seed=0)
    diff = clean.astype(int) - shad.astype(int)
    assert diff.min() >= 0 and diff.max() > 40
    geo = Geometry.of(400, 0.0, False)
    pin = next(p for p in plate.pieces if p.kind == "pin")
    x, y = np.round(geo.to_px(spec.slot_center(*pin.slot))).astype(int)
    assert diff[y, x] == 0  # pin top unchanged


@pytest.mark.parametrize("mode", ["holes", "pins"])
def test_edge_homography_fix_is_accurate_and_beats_shadow_and_keystone(plate, mode):
    true = _truth(plate)
    for df in (Defects(), Defects(keystone=0.01), Defects(shadow_mm=0.3)):
        img = make_scan(plate, true, mode, df, seed=2)
        ms = measure_variant(img, plate, mode, "edge", "homography")
        err = np.array([m.measured_d - true[m.piece_id] for m in ms])
        assert all(m.status == "ok" for m in ms) and np.abs(err).max() < 0.02, (df, np.abs(err).max())


def test_fiducial_retry_survives_noisy_blurry_pin_scan(plate):
    true = _truth(plate)
    df = Defects(blur_px=3.0, noise=0.04, grad=0.6)
    img = make_scan(plate, true, "pins", df, seed=3)
    with pytest.raises(ValueError, match="fiducials"):
        measure_scan(img, plate, "pins")
    ms = measure_variant(img, plate, "pins", "edge", "homography")
    assert sum(m.status == "ok" for m in ms) == len(ms)
