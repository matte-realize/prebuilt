"""Plate -> watertight STL. Holes go through the plate; pins stand on the top face."""
from __future__ import annotations

from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh

from contracts import Plate
from plates import spec


def _cyl(d: float, h: float, x: float, y: float, z0: float) -> mf.Manifold:
    return mf.Manifold.cylinder(h, d / 2, d / 2, spec.SEGMENTS).translate((x, y, z0))


def plate_manifold(plate: Plate, thick: float = spec.THICK, pin_h: float = spec.PIN_H) -> mf.Manifold:
    body = mf.Manifold.cube((spec.PLATE, spec.PLATE, thick))
    cuts, adds = [], []

    for fx, fy in spec.FIDUCIALS:
        s = spec.FIDUCIAL
        cuts.append(mf.Manifold.cube((s, s, thick + 2)).translate((fx - s / 2, fy - s / 2, -1)))
    nx, nw, nd = spec.NOTCH
    cuts.append(mf.Manifold.cube((nw, nd + 1, thick + 2)).translate((nx - nw / 2, -1, -1)))

    for p in plate.pieces:
        x, y = spec.slot_center(*p.slot)
        if p.kind == "hole":
            cuts.append(_cyl(p.nominal_d, thick + 2, x, y, -1))
        else:
            # Overlap 0.01 mm into the plate so the union is one solid.
            adds.append(_cyl(p.nominal_d, pin_h + 0.01, x, y, thick - 0.01))

    if cuts:
        body = body - mf.Manifold.batch_boolean(cuts, mf.OpType.Add)
    if adds:
        body = body + mf.Manifold.batch_boolean(adds, mf.OpType.Add)
    return body


def to_trimesh(m: mf.Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))


def write_stl(plate: Plate, path: str | Path, thick: float = spec.THICK, pin_h: float = spec.PIN_H) -> trimesh.Trimesh:
    tm = to_trimesh(plate_manifold(plate, thick, pin_h))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tm.export(str(path))
    return tm
