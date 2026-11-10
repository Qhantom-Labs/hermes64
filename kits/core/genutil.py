"""Shared helpers for generators (theme-agnostic)."""
import math

import numpy as np

from . import meshkit as K
from .asset import Asset, Node

ROLE_STRUCT = ["body", "body_alt", "wood", "stone", "metal", "chrome", "wall", "trim", "frame", "hull", "leather"]
ROLE_SOFT = ["cushion", "quilt", "fabric", "knit", "fur", "leather"]
ROLE_METAL = ["metal", "chrome", "wood", "body_alt", "post", "trim"]


def finalize(nodes, meta=None, center_x=True, center_y=True, ground=True):
    """Translate every node (meshes + pivots) so the bbox footprint is centred and min z = 0."""
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for n in nodes:
        a = np.asarray(n.mesh.v)
        lo = np.minimum(lo, a.min(0))
        hi = np.maximum(hi, a.max(0))
    d = np.zeros(3)
    if center_x:
        d[0] = -(lo[0] + hi[0]) / 2
    if center_y:
        d[1] = -(lo[1] + hi[1]) / 2
    if ground:
        d[2] = -lo[2]
    for n in nodes:
        n.mesh.translate(*d)
        n.origin = tuple(np.asarray(n.origin) + d)
    meta = dict(meta or {})
    meta["bbox_size_m"] = [round(float(x), 4) for x in (hi - lo)]
    return Asset(nodes, meta)


def post(x, y, z0, z1, r, role, sides=6, square=False, smooth=True):
    if square:
        return K.box(x, y, (z0 + z1) / 2, 2 * r, 2 * r, z1 - z0, role)
    return K.cylinder(x, y, z0, r, z1 - z0, sides, role, smooth)


def leg_points(shape, w, d, inset):
    if shape in ("round", "oval", "flower", "kidney"):
        return [((w / 2 - inset) * math.cos(a) * 0.72, (d / 2 - inset) * math.sin(a) * 0.72)
                for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)]
    return [(sx * (w / 2 - inset), sy * (d / 2 - inset)) for sx in (-1, 1) for sy in (-1, 1)]


def seg_count(shape, base=16):
    return 4 if shape == "rect" else base


def single(name, mesh, meta=None, **kw):
    return finalize([Node(name, mesh)], meta, **kw)
