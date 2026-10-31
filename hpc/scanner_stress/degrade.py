"""Degraded synthetic scans: `measure.synth.render_scan` (unchanged) plus real-scanner defects.

render_scan draws the plate with exact sub-pixel coverage. Every defect here is
applied to that clean image, in roughly the order light meets them:

    cast shadows, pin edge rounding -> dust on the glass -> perspective skew
    -> uneven lighting -> optical blur -> sensor noise -> JPEG

Rotation and dpi go through render_scan itself, so the geometry stays exact.
Sizes are in physical units (mm) where the defect is physical, and in pixels
where it belongs to the scanner (blur).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields

import cv2
import numpy as np

from contracts import Plate
from measure.synth import LEVELS, render_scan
from plates import spec

MARGIN_MM = 8.0  # render_scan's default


def margin_mm(angle_deg: float) -> float:
    """render_scan's margin, widened when a rotated plate's corners would leave the image
    (a real bed is big enough). Unchanged up to about 10 degrees."""
    a = math.radians(angle_deg)
    return max(MARGIN_MM, spec.PLATE / 2 * (abs(math.cos(a)) + abs(math.sin(a)) - 1) + 2.0)


@dataclass
class Defects:
    dpi: float = 400
    angle_deg: float | None = None  # None: uniform in +-3 deg per scan (hand placement)
    mirror: bool | None = None      # None: random per scan
    blur_px: float = 1.2            # Gaussian sigma, px (render_scan's default)
    noise: float = 0.01             # Gaussian sensor noise, fraction of full scale
    grad: float = 0.0               # linear light fall-off across the bed, fraction
    radial: float = 0.0             # fall-off from a hot spot to the bed corners, fraction
    shadow_mm: float = 0.0          # pins: cast shadow length beside each pin
    shadow_dark: float = 0.5        # pins: shadow darkens the plate by this fraction
    rim_mm: float = 0.0             # pins: rounded top edge band that reads as plate, mm
    keystone: float = 0.0           # perspective: one bed edge shorter by this fraction
    dust: int = 0                   # specks and hairs per scan
    jpeg: int = 0                   # JPEG quality, 0 = lossless

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class Geometry:
    """render_scan's mm -> px map, so defects can find pins in the image."""
    px_per_mm: float
    size: int
    L: np.ndarray

    @classmethod
    def of(cls, dpi: float, angle_deg: float, mirror: bool) -> "Geometry":
        px_per_mm = dpi / 25.4
        size = int((spec.PLATE + 2 * margin_mm(angle_deg)) * px_per_mm)
        a = math.radians(angle_deg)
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        flip = np.diag([-1.0 if mirror else 1.0, -1.0])
        return cls(px_per_mm, size, px_per_mm * rot @ flip)

    def to_px(self, xy_mm) -> np.ndarray:
        c = np.array([spec.PLATE / 2, spec.PLATE / 2])
        return (self.L @ (np.asarray(xy_mm, float) - c).T).T + self.size / 2


def _disks(shape, centers_px, radii_px) -> np.ndarray:
    """Anti-aliased coverage of filled disks, 0..1."""
    m = np.zeros(shape, np.uint8)
    for (x, y), r in zip(centers_px, radii_px):
        if r > 0:
            cv2.circle(m, (int(round(x * 16)), int(round(y * 16))), int(round(r * 16)), 255, -1, cv2.LINE_AA, shift=4)
    return m / 255.0


def make_scan(plate: Plate, true_d: dict[str, float], mode: str, df: Defects, seed: int) -> np.ndarray:
    """One degraded 8-bit grayscale scan."""
    rng = np.random.default_rng(seed)
    angle = df.angle_deg if df.angle_deg is not None else float(rng.uniform(-3, 3))
    mirror = df.mirror if df.mirror is not None else bool(rng.random() < 0.5)
    img = render_scan(plate, true_d, mode, dpi=df.dpi, angle_deg=angle, mirror=mirror,
                      blur_px=0, noise=0, margin_mm=margin_mm(angle), seed=seed).astype(np.float64) / 255
    geo = Geometry.of(df.dpi, angle, mirror)
    bg, pl, ft = LEVELS[mode]

    pins = [p for p in plate.pieces if p.kind == "pin" and true_d[p.piece_id] > 0]
    if mode == "pins" and pins and (df.shadow_mm > 0 or df.rim_mm > 0):
        c = geo.to_px([spec.slot_center(*p.slot) for p in pins])
        r = np.array([true_d[p.piece_id] / 2 for p in pins]) * geo.px_per_mm
        top = _disks(img.shape, c, r)
        if df.rim_mm > 0:  # a rounded top edge sends light away: that band reads near plate level
            inner = _disks(img.shape, c, np.maximum(r - df.rim_mm * geo.px_per_mm, 0))
            img -= 0.8 * (ft - pl) * (top - inner)
        if df.shadow_mm > 0:  # the lamp sits to one side of the scan line: shadows fall along image +y
            off = np.array([0.0, df.shadow_mm * geo.px_per_mm])
            sh = _disks(img.shape, c + off, r)
            pen = 0.25 * df.shadow_mm * geo.px_per_mm
            if pen > 0.3:
                sh = cv2.GaussianBlur(sh, (0, 0), pen)
            img -= df.shadow_dark * pl * sh * (1 - top)

    for _ in range(df.dust):
        x, y = rng.uniform(0, geo.size, 2)
        val = float(rng.choice([0.0, 1.0]))
        if rng.random() < 0.7:  # speck, 15-100 um radius
            rad = max(1, int(round(rng.uniform(0.015, 0.1) * geo.px_per_mm)))
            cv2.circle(img, (int(x), int(y)), rad, val, -1)
        else:                   # hair or fibre, 1-6 mm long
            a, n = rng.uniform(0, math.pi), rng.uniform(1, 6) * geo.px_per_mm
            w = max(1, int(round(0.03 * geo.px_per_mm)))
            cv2.line(img, (int(x), int(y)), (int(x + n * math.cos(a)), int(y + n * math.sin(a))), val, w)

    if df.keystone > 0:  # one edge of the bed foreshortened, as from a tilted plate or camera
        s = geo.size
        src = np.float32([[0, 0], [s, 0], [s, s], [0, s]])
        dst = src.copy()
        k = df.keystone * s / 2
        edge = int(rng.integers(4))  # which edge shrinks
        i, j = edge, (edge + 1) % 4
        mid = (src[i] + src[j]) / 2
        dst[i] += (mid - src[i]) / np.linalg.norm(mid - src[i]) * k
        dst[j] += (mid - src[j]) / np.linalg.norm(mid - src[j]) * k
        H = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(img, H, (s, s), flags=cv2.INTER_LINEAR, borderValue=bg)

    if df.grad > 0 or df.radial > 0:
        yy, xx = (np.mgrid[0:geo.size, 0:geo.size] + 0.5) / geo.size
        gain = np.ones_like(img)
        if df.grad > 0:
            a = rng.uniform(0, 2 * math.pi)
            t = (xx - 0.5) * math.cos(a) + (yy - 0.5) * math.sin(a)
            gain *= 1 - df.grad * (t - t.min()) / (t.max() - t.min())
        if df.radial > 0:
            cx, cy = rng.uniform(0.25, 0.75, 2)  # hot spot somewhere near the middle
            r2 = (xx - cx) ** 2 + (yy - cy) ** 2
            gain *= 1 - df.radial * r2 / r2.max()
        img = img * gain

    if df.blur_px > 0:
        img = cv2.GaussianBlur(img, (0, 0), df.blur_px)
    if df.noise > 0:
        img = img + df.noise * rng.standard_normal(img.shape)
    out = np.clip(img * 255, 0, 255).round().astype(np.uint8)
    if df.jpeg:
        out = cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, df.jpeg])[1], cv2.IMREAD_GRAYSCALE)
    return out
