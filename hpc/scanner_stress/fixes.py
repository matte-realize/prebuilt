"""Prototype fixes for measure/scanner.py, run side by side with the original.

`measure_variant` reuses the scanner's own steps (`_to_float`, `_find_fiducials`,
`_affine`, `_measure_cell`) unchanged, so detection and failure flags match the
original exactly. Only the step being tested is swapped:

  fiducials             always: if the fiducial search fails, retry on the image
                        smoothed by 1-3 px (noise breaks the square test on pin scans).
                        Scans where the original succeeds are unchanged.
  cell="edge"           diameter from a robust circle fit to edge points (the
                        steepest point of the falling edge along 72 rays),
                        instead of coverage-weighted area. The edge position
                        doesn't depend on the brightness on either side, so
                        lighting, shadows and the ring's dark level drop out;
                        dust and hairs become outlier rays.
  mapping="homography"  after the affine pass, refit pixels -> mm as a
                        homography through the fiducials and every measured
                        feature center, then measure each cell in local mm.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from contracts import Measurement, Plate
from measure import scanner as S
from plates import spec

N_RAYS = 72


def _peak_shift_table() -> tuple[np.ndarray, np.ndarray]:
    """Where a blurred disk's edge is steepest, in sigma units: rho = R/sigma -> r_peak/sigma.

    The radial gradient of a disk of radius R blurred by a Gaussian is
    proportional to exp(-(r - R)^2 / 2 sigma^2) * e^-z I1(z), z = rR/sigma^2, so its
    peak sits inside R (by about sigma^2 / 2R once R > 3 sigma).
    """
    th = np.linspace(0, math.pi, 721)
    rho = np.linspace(1.2, 60, 600)
    peak = np.empty_like(rho)
    for k, R in enumerate(rho):
        x = np.linspace(max(R - 4, 0.05), R + 0.5, 2000)
        i1 = np.trapezoid(np.exp(np.multiply.outer(x * R, np.cos(th) - 1)) * np.cos(th), th, axis=1)
        peak[k] = x[np.argmax(-(x - R) ** 2 / 2 + np.log(np.maximum(i1, 1e-300)))]
    return peak, rho


_PEAK, _RHO = _peak_shift_table()


def _true_radius(r_peak: float, sigma: float) -> float:
    x = r_peak / sigma
    if x >= _PEAK[-1]:
        return r_peak + sigma ** 2 / (2 * r_peak)
    return float(np.interp(x, _PEAK, _RHO)) * sigma


def _blob_center(cell: np.ndarray) -> np.ndarray | None:
    """Centroid (px, cell coords) of the Otsu blob nearest the cell center, as _measure_cell picks it."""
    h, w = cell.shape
    _, bw = cv2.threshold((cell * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, _, _, cents = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n < 2:
        return None
    c0 = np.array([w / 2, h / 2])
    return cents[min(range(1, n), key=lambda j: np.linalg.norm(cents[j] - c0))]


def _edge_points(cell: np.ndarray, c: np.ndarray, r0: float, sig0: float = 1.0) -> tuple[np.ndarray, float]:
    """Edge point per ray where the profile falls fastest (features are brighter than their surroundings),
    plus the edge width: the Gaussian sigma of the gradient peak, median over rays (px)."""
    h, w = cell.shape
    step = 0.25
    r_in = 0.35 * r0
    r_out = min(r0 + max(6.0, 0.5 * r0, 3 * sig0), 0.5 * min(h, w) - 1)
    rs = np.arange(r_in, r_out, step)
    th = np.linspace(0, 2 * math.pi, N_RAYS, endpoint=False)
    X = (c[0] + np.outer(np.cos(th), rs)).astype(np.float32)
    Y = (c[1] + np.outer(np.sin(th), rs)).astype(np.float32)
    prof = cv2.remap(cell.astype(np.float32), X, Y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    sm = max(0.6, 0.5 * sig0)  # px; against noise and JPEG blocks, wider on blurry edges
    m = int(math.ceil(3 * sm / step))
    k = np.exp(-0.5 * (np.arange(-m, m + 1) * step / sm) ** 2)
    prof = np.apply_along_axis(lambda p: np.convolve(np.pad(p, m, mode="edge"), k / k.sum(), "valid"), 1, prof)
    g = -np.diff(prof, axis=1) / step  # falling edge -> positive peak
    n = np.arange(N_RAYS)
    hw = int(np.clip(round(sig0 / step), 4, 16))
    i = np.clip(np.argmax(g, axis=1), hw, g.shape[1] - hw - 1)
    # Gaussian peak: log g is a parabola. Three-point fit at +-1 sample for position, +-sigma for width.
    lg = np.log(np.maximum(g, 1e-9))
    a, b, cc = lg[n, i - 1], lg[n, i], lg[n, i + 1]
    den = a - 2 * b + cc
    frac = np.where(den < -1e-12, 0.5 * (a - cc) / den, 0.0)
    r = r_in + (i + 0.5 + np.clip(frac, -1, 1)) * step
    curv = (2 * lg[n, i] - lg[n, i - hw] - lg[n, i + hw]) / (hw * step) ** 2
    sig = np.sqrt(1.0 / curv[curv > 1e-6]) if (curv > 1e-6).any() else np.array([sig0])
    return np.stack([c[0] + r * np.cos(th), c[1] + r * np.sin(th)], axis=1), float(np.median(sig))


def _fit_circle(pts: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Algebraic circle fit with iterative MAD outlier rejection. Returns center, radius, inlier fraction."""
    keep = np.ones(len(pts), bool)
    for _ in range(4):
        p = pts[keep]
        A = np.column_stack([2 * p, np.ones(len(p))])
        sol, *_ = np.linalg.lstsq(A, (p ** 2).sum(1), rcond=None)
        c = sol[:2]
        r = math.sqrt(max(sol[2] + c @ c, 0))
        res = np.linalg.norm(pts - c, axis=1) - r
        mad = 1.4826 * np.median(np.abs(res[keep] - np.median(res[keep])))
        new = np.abs(res) < max(3 * mad, 0.004 * r, 1e-6)
        if new.sum() < 12 or (new == keep).all():
            break
        keep = new
    return c, r, float(keep.mean())


def _edge_diameter(cell: np.ndarray, to_mm, d_area_mm: float, mm_per_px: float) -> float | None:
    """Circle fit in mm to edge points found in pixels. The second pass recenters the rays.

    On a blurred circle the steepest point sits inside the true edge (`_true_radius`),
    so each point moves out by that much before the mm fit.
    """
    c = _blob_center(cell)
    if c is None:
        return None
    r0, sig = d_area_mm / 2 / mm_per_px, 1.0
    for _ in range(2):
        pts_px, sig = _edge_points(cell, c, r0, sig)
        c, r0, inl = _fit_circle(pts_px)
    if inl < 0.5:
        return None
    pts_px, sig = _edge_points(cell, c, r0, sig)
    c, r_pk, _ = _fit_circle(pts_px)
    u = (pts_px - c) / np.linalg.norm(pts_px - c, axis=1, keepdims=True)
    pts_px = pts_px + u * (_true_radius(r_pk, sig) - r_pk)
    _, r_mm, _ = _fit_circle(to_mm(pts_px))
    return 2 * r_mm


def _refine_homography(g, plate, kind, A, fid_px) -> np.ndarray | None:
    """Homography px -> mm through the fiducials and the centroids of every feature found with the affine map."""
    inv = cv2.invertAffineTransform(A)
    mm_per_px = math.sqrt(abs(np.linalg.det(A[:, :2])))
    half = spec.PITCH / 2 / mm_per_px * 0.95
    # fid_px is TL then TR/BL in either order; pair each with the fiducial A maps it nearest to.
    src = [np.asarray(f, float) for f in fid_px]
    dst = [A @ [*f, 1] for f in fid_px]
    dst = [np.asarray(min(spec.FIDUCIALS, key=lambda q: np.hypot(*(np.subtract(q, d)))), float) for d in dst]
    for p in plate.pieces:
        if p.kind != kind:
            continue
        cx, cy = inv @ [*spec.slot_center(*p.slot), 1]
        x0, y0 = int(cx - half), int(cy - half)
        x1, y1 = int(cx + half) + 1, int(cy + half) + 1
        if x0 < 0 or y0 < 0 or x1 > g.shape[1] or y1 > g.shape[0]:
            continue
        cell = g[y0:y1, x0:x1]
        if np.subtract(*np.percentile(cell, [99.5, 0.5])) < 0.15:
            continue
        c = _blob_center(cell)
        if c is None or np.linalg.norm(c - [(x1 - x0) / 2, (y1 - y0) / 2]) > 0.3 * (x1 - x0):
            continue
        src.append(c + [x0, y0])
        dst.append(np.asarray(spec.slot_center(*p.slot), float))
    if len(src) < 8:
        return None
    H, _ = cv2.findHomography(np.float64(src), np.float64(dst), cv2.RANSAC, 0.3)  # mm
    return H


def _find_fiducials(fid_img: np.ndarray) -> list[np.ndarray]:
    """The original search, retried on smoothed copies (the scale isn't known yet, so a few sigmas in px)."""
    try:
        return S._find_fiducials(fid_img)
    except ValueError as e:
        err = e
    for sig in (1.0, 2.0, 3.0):
        try:
            return S._find_fiducials(cv2.GaussianBlur(fid_img, (0, 0), sig))
        except ValueError as e:
            err = e
    raise err


def measure_variant(img: np.ndarray, plate: Plate, mode: str, cell: str = "area", mapping: str = "affine",
                    method: str = "scanner") -> list[Measurement]:
    g = S._to_float(img)
    kind = {"holes": "hole", "pins": "pin"}[mode]
    fid = _find_fiducials(g if mode == "holes" else 1 - g)
    A, _ = S._affine(fid, g, notch_bright=(mode == "holes"))
    H = _refine_homography(g, plate, kind, A, fid) if mapping == "homography" else None
    if H is not None:
        Hinv = np.linalg.inv(H)
        px_of = lambda xy: (Hinv @ [*xy, 1])[:2] / (Hinv @ [*xy, 1])[2]
        def to_mm_global(p):
            q = np.column_stack([p, np.ones(len(p))]) @ H.T
            return q[:, :2] / q[:, 2:]
    else:
        inv = cv2.invertAffineTransform(A)
        px_of = lambda xy: inv @ [*xy, 1]
        to_mm_global = lambda p: p @ A[:, :2].T + A[:, 2]

    out = []
    for p in plate.pieces:
        if p.kind != kind:
            continue
        xy = spec.slot_center(*p.slot)
        cx, cy = px_of(xy)
        # local scale at this cell (exact for the affine map)
        e = 0.5
        J = np.column_stack([px_of((xy[0] + e, xy[1])) - px_of((xy[0] - e, xy[1])),
                             px_of((xy[0], xy[1] + e)) - px_of((xy[0], xy[1] - e))]) / (2 * e)
        mm2_per_px = 1 / abs(np.linalg.det(J))
        mm_per_px = math.sqrt(mm2_per_px)
        half = spec.PITCH / 2 / mm_per_px * 0.95
        x0, x1 = int(cx - half), int(cx + half) + 1
        y0, y1 = int(cy - half), int(cy + half) + 1
        fail = Measurement(p.piece_id, plate.plate_id, plate.site, None, "failed", method)
        if x0 < 0 or y0 < 0 or x1 > g.shape[1] or y1 > g.shape[0]:
            out.append(fail)
            continue
        c = g[y0:y1, x0:x1]
        d, _, _ = S._measure_cell(c, mm2_per_px, p.nominal_d)
        if d is not None and cell == "edge":
            d = _edge_diameter(c, lambda q: to_mm_global(q + [x0, y0]), d, mm_per_px)
        out.append(fail if d is None else Measurement(p.piece_id, plate.plate_id, plate.site, d, "ok", method))
    return out
