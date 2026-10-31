"""Flatbed-scan measurement of pin and hole diameters.

Two scans per plate:
  holes  backlit: holes and fiducials bright, plate dark
  pins   front-lit, dark lid: pin tops bright, plate mid-gray, holes and fiducials dark

Pipeline: find the three square fiducials, decide the mirror state from the
notch (a face-down scan is mirrored), fit an affine map from pixels to mm, then
for each expected slot measure the blob's area with sub-pixel coverage
weighting:
    d = 2 * sqrt(area / pi)
Blur conserves the coverage sum, so this estimate doesn't depend on focus. A
slot with no blob, or a blob far too small or touching its cell edge (fused),
is reported as status="failed".
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from contracts import Measurement, Plate
from plates import spec


@dataclass
class ScanInfo:
    mm_per_px: float
    mirrored: bool
    fiducials_px: list[tuple[float, float]]
    roundness: dict[str, float] = field(default_factory=dict)   # piece_id -> minor/major axis
    notes: list[str] = field(default_factory=list)


def _to_float(img: np.ndarray) -> np.ndarray:
    g = img.astype(np.float64)
    if g.ndim == 3:
        g = g.mean(axis=2)
    lo, hi = np.percentile(g, 0.5), np.percentile(g, 99.5)
    return np.clip((g - lo) / max(hi - lo, 1e-9), 0, 1)


def _find_fiducials(bright: np.ndarray) -> list[np.ndarray]:
    """Centroids (px) of square, equal-size, bright blobs forming a right isosceles triangle."""
    u8 = (bright * 255).astype(np.uint8)
    _, bw = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(bw, connectivity=8)
    h, w = bw.shape
    squares = []
    for i in range(1, n):
        x, y, bw_, bh, area = stats[i]
        if area < 30 or x == 0 or y == 0 or x + bw_ >= w or y + bh >= h:
            continue
        cnt, _ = cv2.findContours((lab[y:y + bh, x:x + bw_] == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        (_, _), (rw, rh), _ = cv2.minAreaRect(cnt[0])
        if rw * rh == 0:
            continue
        if area / (rw * rh) > 0.88 and 0.8 < rw / rh < 1.25:
            squares.append((cents[i], area))
    best, best_err = None, math.inf
    leg_expected = math.dist(spec.FIDUCIALS[0], spec.FIDUCIALS[1]) / spec.FIDUCIAL  # legs in fiducial sides
    for tri in itertools.combinations(squares, 3):
        areas = [a for _, a in tri]
        if max(areas) / min(areas) > 1.3:
            continue
        side = math.sqrt(np.mean(areas))
        pts = [c for c, _ in tri]
        for k in range(3):  # k = the right-angle corner
            a, b, c = pts[k], pts[(k + 1) % 3], pts[(k + 2) % 3]
            l1, l2 = np.linalg.norm(b - a), np.linalg.norm(c - a)
            cosang = abs(np.dot(b - a, c - a)) / (l1 * l2)
            err = cosang + abs(l1 / l2 - 1) + abs((l1 + l2) / 2 / side / leg_expected - 1)
            if err < best_err:
                best, best_err = [a, b, c], err
    if best is None or best_err > 0.25:
        raise ValueError(f"could not find the three fiducials (best error {best_err:.2f})")
    return best


def _affine(fid_px: list[np.ndarray], g: np.ndarray, notch_bright: bool) -> tuple[np.ndarray, bool]:
    """px -> mm affine (2x3). Tries both corner assignments; the notch decides."""
    tl, p, q = fid_px
    dst = np.float32(spec.FIDUCIALS)  # TL, TR, BL
    nx, nw, nd = spec.NOTCH
    best = None
    for tr, bl in ((p, q), (q, p)):
        A = cv2.getAffineTransform(np.float32([tl, tr, bl]), dst)
        inv = cv2.invertAffineTransform(A)
        def sample(xm: float, ym: float) -> float:
            x, y = np.round(inv @ [xm, ym, 1]).astype(int)
            if not (0 <= y < g.shape[0] and 0 <= x < g.shape[1]):
                raise IndexError
            return g[y, x]
        try:
            inside, outside = sample(nx, nd / 2), sample(nx - nw * 2, nd / 2)
        except IndexError:
            continue
        contrast = (inside - outside) if notch_bright else (outside - inside)
        mirrored = np.linalg.det(A[:, :2]) > 0  # image y points down, plate y up: unmirrored det < 0
        if best is None or contrast > best[0]:
            best = (contrast, A, mirrored)
    return best[1], bool(best[2])


def measure_scan(img: np.ndarray, plate: Plate, mode: str, method: str = "scanner") -> tuple[list[Measurement], ScanInfo]:
    """Measure the pieces of one kind ("holes" -> holes, "pins" -> pins) from one scan."""
    g = _to_float(img)
    kind = {"holes": "hole", "pins": "pin"}[mode]
    fid_img = g if mode == "holes" else 1 - g
    fid = _find_fiducials(fid_img)
    A, mirrored = _affine(fid, g, notch_bright=(mode == "holes"))
    inv = cv2.invertAffineTransform(A)
    mm2_per_px = abs(np.linalg.det(A[:, :2]))
    mm_per_px = math.sqrt(mm2_per_px)
    info = ScanInfo(mm_per_px, mirrored, [tuple(map(float, f)) for f in fid])

    half = spec.PITCH / 2 / mm_per_px * 0.95   # cell half-width in px
    out = []
    for p in plate.pieces:
        if p.kind != kind:
            continue
        cx, cy = inv @ [*spec.slot_center(*p.slot), 1]
        x0, x1 = int(cx - half), int(cx + half) + 1
        y0, y1 = int(cy - half), int(cy + half) + 1
        if x0 < 0 or y0 < 0 or x1 > g.shape[1] or y1 > g.shape[0]:
            out.append(Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", method))
            info.notes.append(f"{p.piece_id}: cell outside image")
            continue
        d, why, rnd = _measure_cell(g[y0:y1, x0:x1], mm2_per_px, p.nominal_d)
        if d is None:
            out.append(Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", method))
            info.notes.append(f"{p.piece_id}: {why}")
        else:
            out.append(Measurement(p.piece_id, plate.plate_id, plate.site, d, "ok", method))
            info.roundness[p.piece_id] = rnd
    return out, info


def _measure_cell(cell: np.ndarray, mm2_per_px: float, nominal_d: float):
    """Coverage-weighted area of the bright blob nearest the cell center."""
    h, w = cell.shape
    u8 = (cell * 255).astype(np.uint8)
    _, bw = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n < 2:
        return None, "no blob", None
    c0 = np.array([w / 2, h / 2])
    i = min(range(1, n), key=lambda j: np.linalg.norm(cents[j] - c0))
    if np.linalg.norm(cents[i] - c0) > 0.3 * w:
        return None, "no blob near slot center", None
    x, y, bw_, bh, _ = stats[i]
    if x == 0 or y == 0 or x + bw_ >= w or y + bh >= h:
        return None, "blob touches cell edge (fused?)", None

    blob = (lab == i).astype(np.uint8)
    core = cv2.erode(blob, np.ones((3, 3), np.uint8), iterations=2)
    grow = max(3, int(0.15 * max(bw_, bh)))
    region = cv2.dilate(blob, np.ones((3, 3), np.uint8), iterations=grow)
    ring = cv2.dilate(region, np.ones((3, 3), np.uint8), iterations=3) - region
    if core.sum() == 0 or ring.sum() == 0:
        return None, "blob too small to measure", None
    bright = np.median(cell[core > 0])
    dark = np.median(cell[ring > 0])
    if bright - dark < 0.1:
        return None, "low contrast", None
    cov = np.clip((cell - dark) / (bright - dark), 0, 1)
    area_mm2 = cov[region > 0].sum() * mm2_per_px
    d = 2 * math.sqrt(area_mm2 / math.pi)
    if d < 0.5 * nominal_d:
        return None, f"blob far too small ({d:.2f} mm vs nominal {nominal_d})", None

    cnt, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rnd = 1.0
    if len(cnt[0]) >= 5:
        (_, _), (ma, mb), _ = cv2.fitEllipse(cnt[0])
        rnd = float(min(ma, mb) / max(ma, mb))
    return float(d), "", rnd
