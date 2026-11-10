"""ANCIENTKIT shared geometry (theme-agnostic, Blender space: +Z up, front faces -Y = glTF +Z = south).

All four ANCIENTKIT families (ruin./relic./wild./land.) snap to ONE documented grid, the RUIN GRID
(docs/ANCIENTKIT.md section 3). It deliberately shares the numbers of the DUNGEON GRID so the two kit sets can share
plots:

- 1 cell = 4 m x 4 m; grid pieces turn in 90 degree steps; free props turn freely;
- walls are CLOSED solids 1.0 m thick centred on the cell boundary, so each inner face stands WALL_T = 0.5 m in from
  the boundary (the dungeon grid's inner-face inset) and the same wall reads from both sides in ruins;
- storey H = 4.5 m; doorway cut 2.8 m x 3.6 m (the standard frame, ruin.gate__doorway, covers its edges);
- a room plot = cells x 4 m + a 0.5 m apron each side, so room.gd's door anchor (0.4 m in from the room edge at the
  side-cell midpoint 4 i + 2.5) lies inside the wall thickness;
- terrain tiers: stair rise 0.25 m, tread 0.4 m, pyramid tier 2.0 m.

Sockets live in each build's meta["sockets"] in glTF piece space (x east, y up, z south) and in the manifest
kits/library/ancientkit-sockets.json that the room compiler (tools/ancientkit_rooms.py) checks.

Mesh hygiene for the kit validators: closed parts (kit_*) are built from closed primitives that may overlap but never
share a vertex position (welding would merge them into non-manifold islands); open parts (terrain sheets, leaves)
are kit_shell_* nodes. The runtime culls back faces, so two-sided leaves are a front sheet plus an offset back sheet.
"""
import math

import numpy as np

from . import gen_ancientkit_tex  # noqa: F401  registers the anc_* texture fields
from . import meshkit as K

CELL = 4.0
WALL_T = 0.5            # inner face inset from the cell boundary
WALL_D = 1.0            # wall thickness (centred on the boundary)
H = 4.5                 # storey
CUT_W, CUT_H = 2.8, 3.6  # doorway cut in a wall
DOOR_W, DOOR_H = 2.0, 3.0  # clear opening of the standard frame
STEP_RISE, STEP_RUN = 0.25, 0.4
TIER_H = 2.0
DOOR_ANCHOR = 0.4       # room.gd door anchor, in from the room edge
TAU = math.tau


# ---------------------------------------------------------------- hygiene
def weld(m, tol=1e-5):
    """Merge coincident vertices; drop faces that collapse (repeated corners, zero area)."""
    key, remap, verts = {}, [], []
    for p in m.v:
        k = (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))
        if k not in key:
            key[k] = len(verts)
            verts.append(p)
        remap.append(key[k])
    out = K.Mesh()
    out.v = verts
    V = np.asarray(verts) if verts else np.zeros((0, 3))
    for fi, f in enumerate(m.f):
        g = []
        for i in f:
            j = remap[i]
            if not g or g[-1] != j:
                g.append(j)
        if len(g) > 1 and g[0] == g[-1]:
            g.pop()
        if len(g) < 3 or len(set(g)) < len(g):
            continue
        pts = V[g]
        n = np.zeros(3)
        for a in range(len(g)):
            n += np.cross(pts[a], pts[(a + 1) % len(g)])
        if np.linalg.norm(n) < 1e-9:
            continue
        out.f.append(tuple(g))
        out.r.append(m.r[fi])
        out.s.append(m.s[fi])
        out.uv.append(m.uv[fi])
    return out


def merge(*meshes):
    out = K.Mesh()
    for m in meshes:
        if m is not None:
            out.merge(m)
    return out


def place(m, x=0.0, y=0.0, z=0.0, yaw_deg=0.0):
    if yaw_deg:
        m.rotate_z(math.radians(yaw_deg))
    return m.translate(x, y, z)


# ---------------------------------------------------------------- closed primitives
def chamfer_box(cx, cy, z0, sx, sy, sz, role, bevel=0.06, top_role=None, bottom_role=None, k_corner=1):
    """Closed block with chamfered vertical edges and a bevelled top rim (never a raw cuboid)."""
    b = max(0.004, min(bevel, 0.45 * min(sx, sy), 0.45 * sz))
    outline = K.rounded_rect2d(sx, sy, b, k_corner)
    inner = K.rounded_rect2d(max(0.01, sx - 2 * b), max(0.01, sy - 2 * b), max(0.003, b * 0.5), k_corner)
    rings = [K.ring3d(cx, cy, z0, outline), K.ring3d(cx, cy, z0 + sz - b, outline), K.ring3d(cx, cy, z0 + sz, inner)]
    return K.loft(rings, role, smooth=False, cap_roles=(bottom_role or role, top_role or role))


def frustum(cx, cy, z0, z1, sx0, sy0, sx1, sy1, role, top_role=None):
    """Cheap closed battered block (12 tris): small parts (feet, rays, gnomons) where a chamfer costs too much; the
    lean keeps its sides off the axis-aligned cuboid look."""
    rings = [K.ring3d(cx, cy, z0, [(sx0 / 2, -sy0 / 2), (sx0 / 2, sy0 / 2), (-sx0 / 2, sy0 / 2), (-sx0 / 2, -sy0 / 2)]),
             K.ring3d(cx, cy, z1, [(sx1 / 2, -sy1 / 2), (sx1 / 2, sy1 / 2), (-sx1 / 2, sy1 / 2), (-sx1 / 2, -sy1 / 2)])]
    return K.loft(rings, role, smooth=False, cap_roles=(role, top_role or role))


def taper_box(cx, cy, z0, z1, sx0, sy0, sx1, sy1, role, bevel=0.06, top_role=None, k_corner=1):
    """Battered block (sides lean in): pyramid tiers, steles, pylons, plinths."""
    b = max(0.004, min(bevel, 0.4 * min(sx1, sy1), 0.4 * (z1 - z0)))
    o0 = K.rounded_rect2d(sx0, sy0, b, k_corner)
    t = (z1 - b - z0) / max(z1 - z0, 1e-6)
    sxm, sym = sx0 + (sx1 - sx0) * t, sy0 + (sy1 - sy0) * t
    o1 = K.rounded_rect2d(sxm, sym, b, k_corner)
    o2 = K.rounded_rect2d(max(0.01, sx1 - 2 * b), max(0.01, sy1 - 2 * b), max(0.003, b * 0.5), k_corner)
    rings = [K.ring3d(cx, cy, z0, o0), K.ring3d(cx, cy, z1 - b, o1), K.ring3d(cx, cy, z1, o2)]
    return K.loft(rings, role, smooth=False, cap_roles=(role, top_role or role))


def stack(cx, cy, levels, role, roles=None, k_corner=1, smooth=False):
    """Stacked chamfered rings: levels [(z, sx, sy, chamfer)] bottom -> top (mouldings, pedestals, tiers)."""
    rings = [K.ring3d(cx, cy, z, K.rounded_rect2d(sx, sy, min(c, 0.45 * min(sx, sy)), k_corner)) for z, sx, sy, c in levels]
    return K.loft(rings, role, smooth=smooth, roles=roles)


def lathe(profile, segs, role, smooth=True, roles=None, cx=0.0, cy=0.0, start=0.0, rx=1.0, ry=1.0):
    m = K.lathe(profile, segs, role, smooth=smooth, roles=roles, start=start, rx=rx, ry=ry)
    return m.translate(cx, cy, 0.0)


def front_prism(outline_xz, y0, y1, role, cap_role=None):
    """Extrude a front-view outline [(x, z)] (any simple polygon, e.g. a wall with a doorway notch) through the
    thickness y0..y1. Returns a closed solid; front and back faces take cap_role (box UVs)."""
    m = K.prism(outline_xz, y0, y1, role, role_top=cap_role or role, role_bottom=cap_role or role)
    m.apply(lambda a: a[:, [0, 2, 1]])
    m.uv = [None if u is None else u for u in m.uv]
    return m.orient_outward()


def notched_rect(w, h, notch_w, notch_h, shape="rect", k=10):
    """Front outline of a w x h wall with a doorway notch from the floor (rect or round-arch top), CCW."""
    if shape == "rect":
        opening = [(-notch_w / 2, 0.0), (notch_w / 2, 0.0), (notch_w / 2, notch_h), (-notch_w / 2, notch_h)]
    else:
        opening = K.opening2d("arch", notch_w, notch_h, k)
    a = opening[0]
    b = opening[1]
    rest = opening[2:]
    notch = [a] + list(reversed(rest)) + [b]
    return [(-w / 2, 0.0)] + notch + [(w / 2, 0.0), (w / 2, h), (-w / 2, h)]


def fan_crown(r, t, role, rays=5, spread=150.0, inner=0.62):
    """The Keeper's fan crown: a flat closed fan of `rays` tapered rays with notches between them, standing in the XZ
    plane (front -Y), base point at the origin. An original emblem of the kit (not a historical headdress)."""
    a0 = math.radians(90 - spread / 2)
    a1 = math.radians(90 + spread / 2)
    pts = [(0.0, 0.0)]
    half = (a1 - a0) / rays * 0.32
    for i in range(rays):
        a = a0 + (a1 - a0) * (i + 0.5) / rays
        if i == 0:
            pts.append((inner * r * math.cos(a0), inner * r * math.sin(a0)))
        pts.append((r * math.cos(a - half), r * math.sin(a - half)))
        pts.append((r * 1.04 * math.cos(a), r * 1.04 * math.sin(a)))
        pts.append((r * math.cos(a + half), r * math.sin(a + half)))
        an = a0 + (a1 - a0) * (i + 1) / rays
        pts.append((inner * r * math.cos(an), inner * r * math.sin(an)))
    pts = K.ccw(pts)
    return front_prism(pts, -t / 2, t / 2, role)


def rock(cx, cy, cz, rx, ry, rz, rs, role="rock", segs=7, rings=4, jitter=0.18, flat_bottom=True, smooth=True):
    """Rounded faceted rock: low-poly ellipsoid with seeded radial jitter (closed, welded)."""
    prof = []
    for j in range(rings + 1):
        a = -math.pi / 2 + math.pi * j / rings
        prof.append((math.cos(a), math.sin(a)))
    mids = []
    for j, (c, s) in enumerate(prof):
        if j in (0, rings):
            continue
        z = cz + rz * s
        ring = []
        for i in range(segs):
            t = TAU * i / segs + 0.3 * j
            f = 1.0 + jitter * (rs.random() * 2 - 1)
            ring.append((cx + rx * c * math.cos(t) * f, cy + ry * c * math.sin(t) * f, z + rz * 0.12 * (rs.random() - 0.5)))
        mids.append(ring)
    bottom = (cx, cy, cz - rz * (0.55 if flat_bottom else 1.0))
    top = (cx, cy, cz + rz * (0.9 + 0.2 * rs.random()))
    verts = [bottom] + [p for r in mids for p in r] + [top]
    faces = []
    k = segs
    for i in range(k):
        faces.append((0, 1 + (i + 1) % k, 1 + i))
    for j in range(len(mids) - 1):
        a0, b0 = 1 + j * k, 1 + (j + 1) * k
        for i in range(k):
            faces.append((a0 + i, a0 + (i + 1) % k, b0 + (i + 1) % k, b0 + i))
    t = len(verts) - 1
    last = 1 + (len(mids) - 1) * k
    for i in range(k):
        faces.append((last + i, last + (i + 1) % k, t))
    return K.Mesh().add(verts, faces, role, smooth).orient_outward()


def block_chunk(cx, cy, z0, sx, sy, sz, rs, role, yaw=None, tilt=0.0, bevel=0.07):
    """A fallen dressed block: chamfered, turned and slightly tilted (rubble, scattered masonry)."""
    m = chamfer_box(0, 0, -sz / 2, sx, sy, sz, role, bevel=bevel)
    if tilt:
        m.rotate_x(tilt)
    m.rotate_z(rs.uniform(0, TAU) if yaw is None else yaw)
    return m.translate(cx, cy, z0 + sz / 2)


def panel(cx, y, z0, w, h, depth, face_role, edge_role, bevel=0.025):
    """Closed bevelled plaque standing on z0 whose FRONT face (-Y) shows the whole texture of face_role (normalized
    UVs): carved reliefs, glyph faces, inlays. Front at y, back at y + depth; the front face is inset by `bevel` so the
    edges slope (catching light) and the plaque never reads as a raw box."""
    b = max(0.0, min(bevel, 0.3 * w, 0.3 * h))
    x0, x1, z1 = cx - w / 2, cx + w / 2, z0 + h
    yb = y + depth
    v = [(x0 + b, y, z0 + b), (x1 - b, y, z0 + b), (x1 - b, y, z1 - b), (x0 + b, y, z1 - b),
         (x0, yb, z0), (x1, yb, z0), (x1, yb, z1), (x0, yb, z1)]
    faces = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7), (1, 5, 6, 2), (3, 2, 6, 7), (4, 5, 1, 0)]
    roles = [face_role] + [edge_role] * 5
    uvs = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5
    return K.Mesh().add(v, faces, roles, False, uvs).orient_outward()


def flat_panel_uv(m, face_role):
    """Give every face of role face_role normalized UVs from its own bounding box in the face plane (one texture copy
    per face): used on lathe/loft faces that should show a whole emblem."""
    V = np.asarray(m.v)
    for fi, f in enumerate(m.f):
        if m.r[fi] != face_role or len(f) != 4:
            continue
        m.uv[fi] = ("n", [(0, 0), (1, 0), (1, 1), (0, 1)])
    return m


# ---------------------------------------------------------------- sweeps
def _offset_dirs(path, closed):
    """Unit left-normals (mitred) and mitre scale at each plan path vertex."""
    P = np.asarray(path, dtype=np.float64)
    n = len(P)
    out = []
    for i in range(n):
        if closed:
            a, b, c = P[(i - 1) % n], P[i], P[(i + 1) % n]
        else:
            a = P[i - 1] if i > 0 else P[i] - (P[1] - P[0])
            b = P[i]
            c = P[i + 1] if i < n - 1 else P[i] + (P[i] - P[i - 1])
        d0 = (b - a) / max(np.linalg.norm(b - a), 1e-12)
        d1 = (c - b) / max(np.linalg.norm(c - b), 1e-12)
        n0 = np.array([-d0[1], d0[0]])
        n1 = np.array([-d1[1], d1[0]])
        m = n0 + n1
        ln = np.linalg.norm(m)
        m = m / ln if ln > 1e-9 else n0
        s = 1.0 / max(0.3, float(np.dot(m, n0)))
        out.append((m, s))
    return out


def sweep(path, profile, role, closed=False, roles=None, smooth=False):
    """Sweep a CLOSED cross-section profile [(d, z)] (d = offset to the LEFT of the path direction, CCW in d-z) along a
    plan polyline path [(x, y)] with mitred joints. Open paths get end caps. Returns a closed solid (walls with plinths
    and cornices, ramparts, court terraces, causeway kerbs)."""
    dirs = _offset_dirs(path, closed)
    rings = []
    for (x, y), (m, s) in zip(path, dirs):
        rings.append([(x + m[0] * d * s, y + m[1] * d * s, z) for d, z in profile])
    if closed:
        rings.append(rings[0])
    k = len(profile)
    verts = [p for r in rings for p in r]
    faces, rl, sm = [], [], []
    for j in range(len(rings) - 1):
        for i in range(k):
            a = j * k + i
            b = j * k + (i + 1) % k
            faces.append((a, b, b + k, a + k))
            rl.append(roles[i] if roles else role)
            sm.append(smooth)
    if not closed:
        faces.append(tuple(reversed(range(k))))
        rl.append(role)
        sm.append(False)
        last = (len(rings) - 1) * k
        faces.append(tuple(range(last, last + k)))
        rl.append(role)
        sm.append(False)
    m = K.Mesh().add(verts, faces, rl, sm)
    m = weld(m)
    return m.orient_outward()


# ---------------------------------------------------------------- open sheets (terrain, leaves)
def height_sheet(x0, y0, x1, y1, nx, ny, zfn, role, smooth=True, roles_fn=None):
    """Open terrain sheet facing +Z over [x0,x1]x[y0,y1] on an nx x ny grid, z = zfn(x, y)."""
    verts = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            y = y0 + (y1 - y0) * j / ny
            verts.append((x, y, float(zfn(x, y))))
    faces, rl = [], []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
            if roles_fn is not None:
                cx = x0 + (x1 - x0) * (i + 0.5) / nx
                cy = y0 + (y1 - y0) * (j + 0.5) / ny
                rl.append(roles_fn(cx, cy))
            else:
                rl.append(role)
    return K.Mesh().add(verts, faces, rl, smooth)


def two_sided(front, offset=0.012):
    """Front sheet plus a back sheet offset along the face normals (the runtime culls back faces)."""
    V = np.asarray(front.v, dtype=np.float64)
    vn = np.zeros_like(V)
    for f in front.f:
        p = V[list(f)]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if len(f) > 3:
            n = n + np.cross(p[2] - p[0], p[3] - p[0])
        ln = np.linalg.norm(n)
        if ln > 1e-12:
            for vi in f:
                vn[vi] += n / ln
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    back = front.copy()
    back.v = [tuple(p) for p in (V - vn * offset).tolist()]
    back.flip()
    return merge(front, back)


def frond(base, direction, length, width, droop, role, segs=3, fold=0.35, twist=0.0, base_offset=0.04):
    """V-folded leaf strip (palm frond / fern leaf / jungle leaf), open front sheet (pair it with two_sided).
    base: (x, y, z); direction: plan angle (radians); droop: how far the tip sinks (m). UV v runs along the leaf.
    The strip starts base_offset out along its direction so leaves of one rosette never share a vertex (a shared
    root vertex would weld them into one island and count their crossings as self-intersections)."""
    dx, dy = math.cos(direction), math.sin(direction)
    bx, by, bz = base[0] + dx * base_offset, base[1] + dy * base_offset, base[2]
    px, py = -dy, dx
    verts, uvs = [], []
    pts = []
    for s in range(segs + 1):
        t = s / segs
        along = length * t
        z = bz + length * 0.35 * t * (1 - t) * 1.6 - droop * t * t
        w = width * (math.sin(math.pi * min(1.0, 0.15 + t)) if t < 1 else 0.08)
        w = max(w, 0.02)
        c = (bx + dx * along, by + dy * along, z)
        sag = fold * w
        pts.append((c, w, sag))
    m = K.Mesh()
    for s in range(segs):
        (c0, w0, f0), (c1, w1, f1) = pts[s], pts[s + 1]
        l0 = (c0[0] + px * w0, c0[1] + py * w0, c0[2] - f0)
        r0 = (c0[0] - px * w0, c0[1] - py * w0, c0[2] - f0)
        l1 = (c1[0] + px * w1, c1[1] + py * w1, c1[2] - f1)
        r1 = (c1[0] - px * w1, c1[1] - py * w1, c1[2] - f1)
        v0, v1 = s / segs, (s + 1) / segs
        # left half (rib -> left edge) and right half, each facing up
        m.add([c0, l0, l1, c1], [(0, 1, 2, 3)], role, True, [("n", [(0.5, v0), (0.0, v0), (0.0, v1), (0.5, v1)])])
        m.add([r0, c0, c1, r1], [(0, 1, 2, 3)], role, True, [("n", [(1.0, v0), (0.5, v0), (0.5, v1), (1.0, v1)])])
    m = weld(m)
    # make the front face up (+Z): check the first face normal
    V = np.asarray(m.v)
    f = m.f[0]
    n = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
    if n[2] < 0:
        m.flip()
    return m


def flame(cx, cy, z0, h, r, role="fire", segs=6):
    """Closed teardrop flame (emissive role), a low-poly lathe with a leaning tip."""
    prof = [(0.0, 0.0), (r * 0.7, h * 0.12), (r, h * 0.32), (r * 0.62, h * 0.62), (r * 0.22, h * 0.86), (0.0, h)]
    return K.lathe(prof, segs, role, smooth=True).translate(cx, cy, z0)


# ---------------------------------------------------------------- grid meta / sockets
def sock(kind, pos_blender, facing, **kw):
    """Socket in glTF piece space from a Blender-space position (x, y, z) -> (x, z, -y). facing in n/s/e/w/up/down
    (glTF: north = -Z)."""
    x, y, z = pos_blender
    d = {"type": kind, "position": [round(x, 4), round(z, 4), round(-y, 4)], "facing": facing}
    d.update(kw)
    return d


def grid_meta(anchor, cells, sockets, **extra):
    meta = {"ruin_grid": {"anchor": anchor, "cells": list(cells) if cells else None, "cell_m": CELL, "wall_thickness_m": WALL_D,
                          "storey_m": H}, "sockets": list(sockets)}
    meta.update(extra)
    return meta


def edge_sockets(length=CELL):
    """Wall/rampart/bank ends: edge sockets at both ends of a cell-edge piece (x = +-length/2)."""
    return [sock("edge", (-length / 2, 0, 0), "w"), sock("edge", (length / 2, 0, 0), "e")]
