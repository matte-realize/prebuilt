"""Synthetic flatbed scans of a plate with known diameters, for testing the scanner.

Coverage of each feature is computed by 8x supersampling in its bounding box,
so the true area of every blob in the image is exact up to sampling.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from contracts import Plate
from plates import spec

LEVELS = {  # (background, plate, feature) gray levels
    "holes": (1.0, 0.08, 1.0),
    "pins": (0.04, 0.45, 0.92),
}


def render_scan(
    plate: Plate,
    true_d: dict[str, float],
    mode: str,
    dpi: float = 600,
    angle_deg: float = 2.0,
    mirror: bool = True,
    blur_px: float = 1.2,
    noise: float = 0.01,
    margin_mm: float = 8.0,
    seed: int = 0,
    gradient: float = 0.0,      # illumination falls off linearly by this fraction across the bed
    vignette: float = 0.0,      # extra fractional fall-off at the corners
    shadow_mm: float = 0.0,     # pins only: shadow cast on the plate, offset this far from each pin
    dust: int = 0,              # number of dust specks / scratches
    jpeg: int = 0,              # JPEG quality (0 = lossless)
) -> np.ndarray:
    """Defaults give a clean scan. The other knobs add real-scanner defects for stress tests."""
    px_per_mm = dpi / 25.4
    size = int((spec.PLATE + 2 * margin_mm) * px_per_mm)
    c_px = np.array([size / 2, size / 2])
    c_mm = np.array([spec.PLATE / 2, spec.PLATE / 2])
    a = math.radians(angle_deg)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    flip = np.diag([-1.0 if mirror else 1.0, -1.0])  # plate y up -> image y down
    L = px_per_mm * rot @ flip                       # mm -> px, linear part
    Linv = np.linalg.inv(L)
    to_px = lambda mm: (L @ (np.asarray(mm, float) - c_mm).T).T + c_px
    to_mm = lambda px: (Linv @ (np.asarray(px, float) - c_px).T).T + c_mm

    bg, pl, ft = LEVELS[mode]
    img = np.full((size, size), bg)
    corners = to_px([(0, 0), (spec.PLATE, 0), (spec.PLATE, spec.PLATE), (0, spec.PLATE)])
    plate_mask = np.zeros((size, size), np.uint8)
    cv2.fillPoly(plate_mask, [np.round(corners * 16).astype(np.int32)], 255, cv2.LINE_AA, shift=4)
    pm = plate_mask / 255.0
    img = img * (1 - pm) + pl * pm

    def paint(inside_fn, bbox_mm, level):
        pts = to_px([(bbox_mm[0], bbox_mm[1]), (bbox_mm[2], bbox_mm[1]), (bbox_mm[0], bbox_mm[3]), (bbox_mm[2], bbox_mm[3])])
        x0, y0 = np.floor(pts.min(axis=0)).astype(int) - 2
        x1, y1 = np.ceil(pts.max(axis=0)).astype(int) + 2
        ss = 8
        xs = x0 + (np.arange((x1 - x0) * ss) + 0.5) / ss
        ys = y0 + (np.arange((y1 - y0) * ss) + 0.5) / ss
        X, Y = np.meshgrid(xs, ys)
        mm = to_mm(np.stack([X.ravel(), Y.ravel()], axis=1))
        inside = inside_fn(mm[:, 0], mm[:, 1]).reshape(len(ys), len(xs))
        cov = inside.reshape(y1 - y0, ss, x1 - x0, ss).mean(axis=(1, 3))
        sub = img[y0:y1, x0:x1]
        img[y0:y1, x0:x1] = sub * (1 - cov) + level * cov

    hole_level = {"holes": ft, "pins": bg}[mode]
    for fx, fy in spec.FIDUCIALS:
        s = spec.FIDUCIAL / 2
        paint(lambda x, y, fx=fx, fy=fy, s=s: (abs(x - fx) <= s) & (abs(y - fy) <= s), (fx - s, fy - s, fx + s, fy + s), hole_level)
    nx, nw, nd = spec.NOTCH
    paint(lambda x, y: (abs(x - nx) <= nw / 2) & (y <= nd), (nx - nw / 2, -1, nx + nw / 2, nd), hole_level)

    if shadow_mm > 0 and mode == "pins":
        for p in plate.pieces:
            if p.kind == "pin":
                cx, cy = spec.slot_center(*p.slot)
                r = true_d[p.piece_id] / 2
                sx, sy = cx + shadow_mm, cy - shadow_mm
                paint(lambda x, y, sx=sx, sy=sy, r=r: (x - sx) ** 2 + (y - sy) ** 2 <= r * r,
                      (sx - r, sy - r, sx + r, sy + r), 0.5 * pl)

    for p in plate.pieces:
        if p.kind == "hole" or mode == "pins":
            cx, cy = spec.slot_center(*p.slot)
            r = true_d[p.piece_id] / 2
            level = hole_level if p.kind == "hole" else ft
            if mode == "holes" and p.kind == "pin":
                continue
            paint(lambda x, y, cx=cx, cy=cy, r=r: (x - cx) ** 2 + (y - cy) ** 2 <= r * r, (cx - r, cy - r, cx + r, cy + r), level)

    rng = np.random.default_rng(seed)
    for _ in range(dust):
        x, y = rng.uniform(0, size, 2)
        if rng.random() < 0.7:  # speck
            cv2.circle(img, (int(x), int(y)), int(rng.integers(1, 4)), float(rng.choice([0.0, 1.0])), -1)
        else:                   # hair / scratch
            a, n = rng.uniform(0, math.pi), rng.uniform(20, 150)
            cv2.line(img, (int(x), int(y)), (int(x + n * math.cos(a)), int(y + n * math.sin(a))),
                     float(rng.choice([0.0, 1.0])), 1)
    if blur_px > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur_px)
    if gradient or vignette:
        yy, xx = np.mgrid[0:size, 0:size] / size
        img = img * (1 - gradient * xx) * (1 - vignette * ((xx - 0.5) ** 2 + (yy - 0.5) ** 2) * 2)
    img = img + noise * rng.standard_normal(img.shape)
    out = np.clip(img * 255, 0, 255).astype(np.uint8)
    if jpeg:
        out = cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])[1], cv2.IMREAD_GRAYSCALE)
    return out
