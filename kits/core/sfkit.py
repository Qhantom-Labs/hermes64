"""SCIFIKIT shared geometry (theme-agnostic; Blender space: +Z up, model front faces -Y = glTF +Z = south).

STATION GRID (docs/SCIFIKIT.md section 4). Station architecture, tech props and the hangar pieces snap to ONE grid:

- 1 cell = 4 m x 4 m; a room plot is cells x 4 m plus a 0.5 m apron on every side (grid_size = 4 * cells + 1);
- wall inner faces stand WALL_T (0.5 m) inside the outer cell boundary, so a corridor is 3.0 m clear between its walls
  and two corridor cells meet only on their shared boundary line;
- corridor clear height H_CORR (3.2 m), room height H_ROOM (4.0 m); airlock / bulkhead doorway 2.0 m x 2.6 m;
- the room.gd door anchor (0.4 m in from the room edge, side midpoint: door.position for side cell i = 4 i + 2) sits
  ANCHOR_BACK (0.6 m) behind the inner wall face; doorway frames and airlock leaves have their origin on it;
- sockets sit on floor level at cell-edge midpoints (corridor ends, doors) or on wall faces (vents, panels), in glTF
  piece space (x east, y up, z south), see socket() and kits/library/scifikit-sockets.json.

Walls, floors and ceilings of rooms and corridors are ONE-SIDED shells facing into the space (kit_shell_*): a camera
outside sees in through the near wall (back faces culled), the N64 cutaway. Wall cross-sections are chamfered (kick
chamfer at the floor, light band, upper chamfer into the ceiling), corners are mitred, nothing is a plain box. Props
are closed solids (kit_*) built from tapered lofts, bevelled blocks and lathes.

Vertex AO: bake_ao() attaches the whole asset's triangles (plus an optional ground plane) to every node mesh; the
baked-light hook below adds hemisphere-ray occlusion per corner. Only meshes that carry it (SCIFIKIT builds) take the
SCIFIKIT path; every other mesh goes through kits/core/bake.py unchanged (byte-identical builds for existing kits).
"""
import math

import numpy as np

from . import bake as _bake
from . import meshkit as K
from . import texgen_scifi  # noqa: F401  (registers the painted SCIFIKIT field generators in texgen.FIELD_GENS)

CELL = 4.0
APRON = 0.5
WALL_T = 0.5
H_CORR = 3.2
H_ROOM = 4.0
DOOR_W, DOOR_H = 2.0, 2.6
ANCHOR_BACK = 0.6
CORR_W = CELL - 2 * WALL_T
TILE = 8.0             # exterior TERRAIN GRID tile (planet surface pieces)

# Wall cross-sections: (inset into the space d, height z, role of the segment from this point to the next).
CORR_PROFILE = ((0.34, 0.0, "wall_alt"), (0.0, 0.42, "wall"), (0.0, 1.35, "wall"), (0.0, 2.28, "light"),
                (0.0, 2.44, "wall_alt"), (0.52, H_CORR, None))
ROOM_PROFILE = ((0.3, 0.0, "wall_alt"), (0.0, 0.4, "wall"), (0.0, 1.5, "wall"), (0.0, 2.86, "light"),
                (0.0, 3.02, "wall_alt"), (0.46, H_ROOM, None))


# ---------------------------------------------------------------- mesh hygiene
def weld_mesh(m, tol=1e-5):
    """Merge coincident vertices, drop faces that collapse (repeated corners / zero area)."""
    key, remap, verts = {}, [], []
    for p in m.v:
        k = (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))
        if k not in key:
            key[k] = len(verts)
            verts.append(p)
        remap.append(key[k])
    out = K.Mesh()
    out.v = verts
    V = np.asarray(verts, dtype=np.float64)
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


def merged(*meshes):
    out = K.Mesh()
    for m in meshes:
        if m is not None and m.f:
            out.merge(m)
    return out


# ---------------------------------------------------------------- 2D outlines
def chamfer_rect(w, d, c):
    """CCW rectangle with chamfered corners (octagon); c = chamfer length (0 = plain rectangle)."""
    c = max(0.0, min(c, w / 2 - 1e-3, d / 2 - 1e-3))
    if c < 1e-4:
        return [(w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2), (-w / 2, -d / 2)]
    x, y = w / 2, d / 2
    return [(x - c, -y), (x, -y + c), (x, y - c), (x - c, y), (-x + c, y), (-x, y - c), (-x, -y + c), (-x + c, -y)]


def ngon(r, k, start=0.0, rx=None, ry=None):
    return K.circle2d(r, k, start=start, rx=rx, ry=ry)


def hexagon(r, flat_top=True):
    return K.circle2d(r, 6, start=0.0 if flat_top else math.pi / 6)


# ---------------------------------------------------------------- closed solids
def loft_levels(outline, levels, role, roles=None, smooth=False, cap_roles=None):
    """Closed solid through rings of one CCW outline: levels = [(z, sx, sy[, ox, oy])] bottom -> top.
    roles: optional per band (len(levels) - 1). Tapers, bevels, plinths and slanted console tops are levels."""
    rings = []
    for lv in levels:
        z, sx, sy = lv[0], lv[1], lv[2]
        ox, oy = (lv[3], lv[4]) if len(lv) > 3 else (0.0, 0.0)
        rings.append([(ox + x * sx, oy + y * sy, z) for x, y in outline])
    return K.loft(rings, role, smooth, True, True, roles=roles, cap_roles=cap_roles)


def loft_y(outline_xz, stations, role, roles=None, smooth=False):
    """Closed solid lofted along +Y through sections of one CCW (x, z) outline: stations = [(y, sx, sz[, ox, oz])]
    front (-Y) -> back. Hulls, fuselages, nacelles. roles: optional per band."""
    rings = []
    for st in stations:
        y, sx, sz = st[0], st[1], st[2]
        ox, oz = (st[3], st[4]) if len(st) > 3 else (0.0, 0.0)
        rings.append([(ox + x * sx, y, oz + z * sz) for x, z in outline_xz])
    return K.loft(rings, role, smooth, True, True, roles=roles)


def loft_x(outline_yz, stations, role, roles=None, smooth=False):
    """Closed solid lofted along +X through sections of one (y, z) outline: stations = [(x, sy, sz[, oy, oz])]: wings,
    fins and struts (root -> tip)."""
    rings = []
    for st in stations:
        x, sy, sz = st[0], st[1], st[2]
        oy, oz = (st[3], st[4]) if len(st) > 3 else (0.0, 0.0)
        rings.append([(x, oy + y * sy, oz + z * sz) for y, z in outline_yz])
    return K.loft(rings, role, smooth, True, True, roles=roles)


def bevel_block(cx, cy, z0, w, d, h, role, bevel=0.06, chamfer=0.0, top_role=None, bottom_bevel=False, roles=None):
    """Block with a bevelled top edge (and optionally bottom) and optional chamfered vertical edges: never a plain box."""
    out = chamfer_rect(w, d, chamfer)
    b = max(0.0, min(bevel, h * 0.45, w * 0.45, d * 0.45))
    fx, fy = (w - 2 * b) / w, (d - 2 * b) / d
    lv = []
    if bottom_bevel and b > 1e-4:
        lv += [(z0, fx, fy, cx, cy), (z0 + b, 1.0, 1.0, cx, cy)]
    else:
        lv += [(z0, 1.0, 1.0, cx, cy)]
    if b > 1e-4:
        lv += [(z0 + h - b, 1.0, 1.0, cx, cy), (z0 + h, fx, fy, cx, cy)]
    else:
        lv += [(z0 + h, 1.0, 1.0, cx, cy)]
    cr = (role, top_role or role)
    return loft_levels(out, lv, role, roles=roles, cap_roles=cr)


def extrude_xz(poly, y0, y1, role, role_cap=None, holes=()):
    """Closed prism of a polygon drawn in the x-z plane (any orientation, optional holes), extruded along y."""
    m = K.prism([(x, z) for x, z in poly], y0, y1, role, role_top=role_cap, role_bottom=role_cap,
                holes=[[(x, z) for x, z in h] for h in holes])
    # prism builds along its 3rd axis: (x, z_poly, y_extrude) -> (x, y_extrude, z_poly); swapping two axes mirrors
    m.v = [(p[0], p[2], p[1]) for p in m.v]
    m.flip()
    return m.orient_outward()


def frame_ring(outer, inner, y0, y1, role, role_cap=None):
    """Closed frame (outer outline minus inner hole, both in x-z) extruded along y: door / window / bulkhead frames."""
    return extrude_xz(outer, y0, y1, role, role_cap, holes=[inner])


def arch_frame(w_in, h_in, w_out, h_out, c_in, c_out):
    """Inverted-U frame outline in (x, z) standing on z = 0 around a floor-level opening w_in x h_in (chamfered head
    corners c_in), outer w_out x h_out (chamfered c_out). One simple polygon (no hole), CCW."""
    a, b = w_in / 2, w_out / 2
    return [(-b, 0.0), (-a, 0.0), (-a, h_in - c_in), (-a + c_in, h_in), (a - c_in, h_in), (a, h_in - c_in), (a, 0.0),
            (b, 0.0), (b, h_out - c_out), (b - c_out, h_out), (-b + c_out, h_out), (-b, h_out - c_out)]


def opening_outline(w, h, z0=0.0, c=0.0):
    """Chamfered rectangular opening outline in (x, z), bottom at z0 (CCW)."""
    return [(x, z + z0 + h / 2) for x, z in chamfer_rect(w, h, c)]


def taper_rib(path_xz, depth0, depth1, y0, y1, role, sink=0.02, depth_mid=None):
    """Closed rib following a polyline in the x-z plane (a wall profile), protruding toward the polyline's LEFT side
    by a depth tapering from depth0 at the start to depth1 at the end (or to depth_mid at the middle and back, when
    given); the back face sinks `sink` behind the path. Extruded along y from y0 to y1."""
    P = [np.asarray(p, dtype=np.float64) for p in path_xz]
    n = len(P)
    seg = [P[i + 1] - P[i] for i in range(n - 1)]
    nor = []
    for s in seg:
        L = np.linalg.norm(s)
        t = s / max(L, 1e-9)
        nor.append(np.array([-t[1], t[0]]))
    cum = [0.0]
    for s in seg:
        cum.append(cum[-1] + float(np.linalg.norm(s)))
    total = max(cum[-1], 1e-9)

    def offset(i, dist):
        if i in (0, n - 1):
            # end points slide along their segment so they keep the end's height (ribs stand on the floor exactly)
            j = 0 if i == 0 else n - 2
            t = seg[j] / max(np.linalg.norm(seg[j]), 1e-12)
            q = P[i] + nor[j] * dist
            if abs(t[1]) > 1e-6:
                q = q + t * (-(nor[j][1] * dist) / t[1])
            return q
        a, b = nor[i - 1], nor[i]
        m = (a + b) / max(1.0 + float(np.dot(a, b)), 1e-3)
        return P[i] + m * dist
    if depth_mid is None:
        inner = [offset(i, depth0 + (depth1 - depth0) * cum[i] / total) for i in range(n)]
    else:
        inner = [offset(i, depth0 + (depth_mid - depth0) * math.sin(math.pi * cum[i] / total)) for i in range(n)]
    outer = [offset(i, -sink) for i in range(n)]
    poly = [tuple(p) for p in outer] + [tuple(p) for p in reversed(inner)]
    return extrude_xz(poly, y0, y1, role)


def lathe(profile, segs, role, roles=None, smooth=True, start=0.0, cap_roles=None, rx=1.0, ry=1.0):
    return K.lathe(profile, segs, role, smooth, roles=roles, start=start, cap_roles=cap_roles, rx=rx, ry=ry)


def lathe_ring(r0, r1, z0, z1, segs, role, smooth=False, start=0.0, roles=None):
    """Closed flat annulus (washer) r0..r1, z0..z1: rims, rings, hazard bands on round platforms.
    roles: optional (bottom, outer, top, inner) face roles."""
    return K.lathe_closed([(r0, z0), (r1, z0), (r1, z1), (r0, z1)], segs, role, smooth, start=start, roles=roles)


def arc_wall(r0, r1, z0, z1, a0, a1, segs, role, roles=None):
    """Closed thick arc wall (partial revolve of the rectangle r0..r1 x z0..z1 from angle a0 to a1, flat end faces):
    alcoves, canopies, curved bulkheads. roles: optional (bottom, outer, top, inner)."""
    rings = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        c, s = math.cos(a), math.sin(a)
        rings.append([(r0 * c, r0 * s, z0), (r1 * c, r1 * s, z0), (r1 * c, r1 * s, z1), (r0 * c, r0 * s, z1)])
    m = K.loft(rings, role, False, True, True, roles=None)
    if roles:
        # loft faces are ordered band by band, 4 faces per band (bottom, outer, top, inner), then the 2 caps
        for fi in range(len(m.f) - 2):
            m.r[fi] = roles[fi % 4]
    return m.orient_outward()


def sweep(path, section, role, smooth=True, cap0=True, cap1=True, roles=None):
    """Loft a closed 2D section [(u, v)] along a 3D polyline (parallel-transport frames; u along N, v along B)."""
    T, N, B = K.frames_along(path)
    rings = []
    for i, p in enumerate(path):
        rings.append([tuple(np.asarray(p) + N[i] * u + B[i] * v) for u, v in section])
    return K.loft(rings, role, smooth, cap0, cap1, roles=roles)


def tube(path, radius, sides, role, smooth=True, cap0=True, cap1=True):
    return K.tube(path, radius, sides, role, smooth, cap0, cap1)


# ---------------------------------------------------------------- one-sided shells
def strip(rows, roles, smooth=False, uv_metric=True):
    """One-sided surface between consecutive open polylines rows[j] (equal length). roles: per column segment i or a
    single role. Face normal follows (rows[j][i+1] - rows[j][i]) x (rows[j+1][i] - rows[j][i])."""
    m = K.Mesh()
    nrow, ncol = len(rows), len(rows[0])
    base = 0
    verts = [p for r in rows for p in r]
    faces, rl, sm, uvs = [], [], [], []
    for j in range(nrow - 1):
        for i in range(ncol - 1):
            a = base + j * ncol + i
            faces.append((a, a + 1, a + ncol + 1, a + ncol))
            rl.append(roles[i] if isinstance(roles, (list, tuple)) else roles)
            sm.append(smooth)
            uvs.append(None)
    m.add(verts, faces, rl, sm, uvs)
    return m


def floor_grid(x0, x1, y0, y1, z, nx, ny, role, up=True, holes=()):
    """Subdivided one-sided plane (normals +Z when up). holes: [(x0, x1, y0, y1)] cells to skip (cell-aligned)."""
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    ys = [y0 + (y1 - y0) * j / ny for j in range(ny + 1)]
    verts = [(x, y, z) for y in ys for x in xs]
    faces = []
    for j in range(ny):
        for i in range(nx):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(h[0] <= cx <= h[1] and h[2] <= cy <= h[3] for h in holes):
                continue
            a = j * (nx + 1) + i
            q = (a, a + 1, a + nx + 2, a + nx + 1)
            faces.append(q if up else tuple(reversed(q)))
    return K.Mesh().add(verts, faces, role, False)


def chain_offset(points, closed, d):
    """Offset of a wall-plane polyline by d to its LEFT (the room side when the chain runs CCW around the room), mitred
    at interior vertices (concave corners shorten, convex corners extend), perpendicular at open ends."""
    P = [np.asarray(p, dtype=np.float64) for p in points]
    n = len(P)
    segs = n if closed else n - 1
    T = []
    for i in range(segs):
        s = P[(i + 1) % n] - P[i]
        T.append(s / max(np.linalg.norm(s), 1e-12))
    N = [np.array([-t[1], t[0]]) for t in T]
    out = []
    for i in range(n):
        if not closed and i == 0:
            out.append(P[0] + N[0] * d)
        elif not closed and i == n - 1:
            out.append(P[-1] + N[-1] * d)
        else:
            a, b = N[(i - 1) % segs], N[i % segs]
            out.append(P[i] + (a + b) / max(1.0 + float(np.dot(a, b)), 1e-3) * d)
    return out


def wall_chain(points, closed, profile, seg_len=2.0, openings=None, extra_z=(), cap=None, cap_role="wall_alt",
               min_station=0.62):
    """One-sided chamfered wall along a wall-plane polyline (CCW around the space, room on the left).

    profile: [(d, z, role)] bottom -> top (role = segment to the next point). openings: {segment index: [(s0, s1, z0,
    z1)]} rectangular cuts (s along the segment from its start vertex); frames cover the cut edges. cap: optional top
    ledge height (thickness seen from above, from the top inset back to the cell boundary WALL_T behind the face)."""
    openings = openings or {}
    prof = list(profile)
    zs_extra = set(round(z, 6) for z in extra_z)
    for ops in openings.values():
        for o in ops:
            zs_extra.update((round(o[2], 6), round(o[3], 6)))
    levels = []
    for i, (d, z, role) in enumerate(prof):
        levels.append((d, z, role))
        if i + 1 < len(prof):
            z2, d2 = prof[i + 1][1], prof[i + 1][0]
            for ze in sorted(zs_extra):
                if z + 1e-6 < ze < z2 - 1e-6:
                    t = (ze - z) / (z2 - z)
                    levels.append((d + t * (d2 - d), ze, role))
    offs = [chain_offset(points, closed, lv[0]) for lv in levels]
    P = [np.asarray(p, dtype=np.float64) for p in points]
    n = len(P)
    segs = n if closed else n - 1
    out = K.Mesh()
    for si in range(segs):
        a, b = P[si], P[(si + 1) % n]
        L = float(np.linalg.norm(b - a))
        t = (b - a) / max(L, 1e-12)
        nn = np.array([-t[1], t[0]])
        ops = openings.get(si, [])
        st = set()
        k = max(1, int(round(L / seg_len)))
        st.update(L * i / k for i in range(1, k))
        for o in ops:
            st.update((o[0], o[1]))
        lo_end = min_station if (closed or si > 0) else 0.0
        hi_end = L - (min_station if (closed or si < segs - 1) else 0.0)
        stations = sorted(s for s in st if lo_end - 1e-6 <= s <= hi_end + 1e-6 and 1e-6 < s < L - 1e-6)
        rows = []
        for li, (d, z, role) in enumerate(levels):
            A = offs[li][si]
            B = offs[li][(si + 1) % n]
            row = [(A[0], A[1], z)]
            for s in stations:
                q = a + t * s + nn * d
                row.append((q[0], q[1], z))
            row.append((B[0], B[1], z))
            rows.append(row)
        scol = [None] + stations + [None]
        verts = [p for r in rows for p in r]
        ncol = len(rows[0])
        faces, rl = [], []
        for j in range(len(levels) - 1):
            zlo, zhi = levels[j][1], levels[j + 1][1]
            for i in range(ncol - 1):
                s0 = scol[i] if scol[i] is not None else (0.0 if i == 0 else L)
                s1 = scol[i + 1] if scol[i + 1] is not None else (L if i + 1 == ncol - 1 else 0.0)
                sm, zm = (s0 + s1) / 2, (zlo + zhi) / 2
                if any(o[0] - 1e-6 <= sm <= o[1] + 1e-6 and o[2] - 1e-6 <= zm <= o[3] + 1e-6 for o in ops):
                    continue
                q = j * ncol + i
                # room on the left of t: (p00, p01, p11, p10) winds the normal toward +n
                faces.append((q, q + ncol, q + ncol + 1, q + 1))
                rl.append(levels[j][2] or "wall")
        out.merge(K.Mesh().add(verts, faces, rl, False))
        if cap is not None:
            top_d = levels[-1][0]
            A, B = chain_offset(points, closed, top_d), chain_offset(points, closed, -WALL_T)
            p0, p1 = A[si], A[(si + 1) % n]
            q0, q1 = B[si], B[(si + 1) % n]
            cz = cap
            out.merge(K.Mesh().add([(p0[0], p0[1], cz), (p1[0], p1[1], cz), (q1[0], q1[1], cz), (q0[0], q0[1], cz)],
                                   [(0, 1, 2, 3)], cap_role, False))
    return out


def face_up(m):
    """Orient every face of a one-sided horizontal sheet to +Z (helper for generated decks)."""
    A = np.asarray(m.v, dtype=np.float64)
    for fi, f in enumerate(m.f):
        p = A[list(f)]
        nz = 0.0
        for a in range(len(f)):
            b = (a + 1) % len(f)
            nz += p[a][0] * p[b][1] - p[b][0] * p[a][1]
        if nz < 0:
            m.f[fi] = tuple(reversed(f))
            if m.uv[fi] is not None:
                m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
    return m


# ---------------------------------------------------------------- sockets / grid meta (glTF piece space)
def gl(x, y, z):
    """Blender (x, y, z) -> glTF (x, y_up, z_south)."""
    return [round(float(x), 4), round(float(z), 4), round(float(-y), 4)]


FACING = {"n": "n", "s": "s", "e": "e", "w": "w"}


def socket(typ, bx, by, bz=0.0, facing="s", **kw):
    s = {"type": typ, "position": gl(bx, by, bz), "facing": facing}
    s.update(kw)
    return s


def grid_meta(anchor, cells=(1, 1), extra=None):
    g = {"anchor": anchor, "cells": list(cells), "cell_m": CELL, "wall_inset_m": WALL_T}
    if extra:
        g.update(extra)
    return {"station_grid": g}


# ---------------------------------------------------------------- vertex AO (hemisphere rays, per corner)
class AOMesh(K.Mesh):
    """A kit Mesh that carries the SCIFIKIT occlusion inputs (all asset triangles + amount/reach)."""
    __slots__ = ("ao",)


def _dirs(k=16):
    out = []
    for i in range(k):
        r = math.sqrt((i + 0.5) / k)
        a = i * 2.399963229728653
        out.append((r * math.cos(a), r * math.sin(a), math.sqrt(max(0.0, 1.0 - r * r))))
    return np.asarray(out)


_DIRS = _dirs()


def _occlusion(p, n, tris, lo, hi, reach):
    n = n / max(np.linalg.norm(n), 1e-12)
    a = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(n, a)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    dirs = _DIRS[:, 0:1] * t1 + _DIRS[:, 1:2] * t2 + _DIRS[:, 2:3] * n
    o = p + n * 0.025
    near = np.all((lo <= o + reach) & (hi >= o - reach), axis=1)
    T = tris[near]
    if not len(T):
        return 0.0
    v0, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    tv = o - v0
    hits = 0.0
    for d in dirs:
        pv = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, pv)
        ok = np.abs(det) > 1e-10
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, e1)
        v = (qv @ d) * inv
        tt = np.einsum("ij,ij->i", e2, qv) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (tt > 1e-4) & (tt < reach)
        if np.any(hit):
            # nearer hits darken more (soft falloff instead of a binary shadow edge)
            hits += 1.0 - 0.5 * float(tt[hit].min()) / reach
    return hits / float(len(dirs))


def bake_ao(nodes, amount=0.3, reach=1.1, ground=True, ground_z=0.0):
    """Attach occlusion inputs to every node mesh (all node triangles + an optional ground plane under the footprint).
    The kit pack may override the amount with light_rig.vertex_ao. Returns the nodes (meshes become AOMesh)."""
    tris = []
    for nd in nodes:
        V = np.asarray(nd.mesh.v, dtype=np.float64)
        for f in nd.mesh.f:
            for i in range(1, len(f) - 1):
                tris.append((V[f[0]], V[f[i]], V[f[i + 1]]))
    if ground and tris:
        A = np.asarray(tris).reshape(-1, 3)
        lo, hi = A.min(0) - reach, A.max(0) + reach
        g = [(lo[0], lo[1], ground_z), (hi[0], lo[1], ground_z), (hi[0], hi[1], ground_z), (lo[0], hi[1], ground_z)]
        tris.append((np.array(g[0]), np.array(g[1]), np.array(g[2])))
        tris.append((np.array(g[0]), np.array(g[2]), np.array(g[3])))
    T = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
    info = {"tris": T, "lo": T.min(1), "hi": T.max(1), "amount": float(amount), "reach": float(reach)}
    for nd in nodes:
        m = nd.mesh
        am = AOMesh()
        am.v, am.f, am.r, am.s, am.uv = m.v, m.f, m.r, m.s, m.uv
        am.ao = info
        nd.mesh = am
    return nodes


_ORIG_BAKE = getattr(_bake.bake_corner_light, "_scifikit_orig", _bake.bake_corner_light)


def bake_corner_light(mesh, rig, n_steps, role_kind, origin_z=0.0):
    """kits/core/bake.py model + per-corner ray occlusion for SCIFIKIT meshes; any other mesh: the original, unchanged."""
    info = getattr(mesh, "ao", None)
    if info is None:
        return _ORIG_BAKE(mesh, rig, n_steps, role_kind, origin_z)
    V = np.asarray(mesh.v, dtype=np.float64)
    fn = _bake.face_normals(V, mesh.f)
    cn = _bake.corner_normals(V, mesh.f, mesh.s, fn)
    k = np.asarray(rig["key_dir"], dtype=np.float64)
    k = k / np.linalg.norm(k)
    amb, key, sky, gnd = rig["ambient"], rig["key"], rig["sky"], rig["ground"]
    ao = rig.get("ao", 0.0)
    ao_h = rig.get("ao_height", 0.35)
    gamma = rig.get("gamma", 1.0)
    occ_amt = float(rig.get("vertex_ao", info["amount"]))
    var = _bake.vertex_variation()
    var_amt = float(var.get("amount", 0.0))
    var_roles = set(var.get("roles", []))
    var_scale = float(var.get("scale_m", 3.0))
    cache = {}
    out = []
    for fi, f in enumerate(mesh.f):
        kind = role_kind(mesh.r[fi])
        if kind in _bake.FULLBRIGHT_KINDS:
            out.append([n_steps - 1] * len(f))
            continue
        varied = var_amt > 0 and mesh.r[fi] in var_roles
        row = []
        for ci, vi in enumerate(f):
            n = np.asarray(cn[fi][ci], dtype=np.float64)
            z = V[vi][2] - origin_z
            t = amb + key * max(0.0, float(np.dot(n, k))) + sky * max(0.0, n[2]) + gnd * max(0.0, -n[2])
            if ao > 0:
                c = max(0.0, min(1.0, z / ao_h))
                t -= ao * (1.0 - c) * (1.0 - c)
            if varied:
                t += var_amt * (2.0 * _bake.value_noise(V[vi], var_scale) - 1.0)
            if occ_amt > 0:
                kk = (round(V[vi][0], 3), round(V[vi][1], 3), round(V[vi][2], 3), round(n[0], 2), round(n[1], 2), round(n[2], 2))
                if kk not in cache:
                    cache[kk] = _occlusion(V[vi], n, info["tris"], info["lo"], info["hi"], info["reach"])
                t -= occ_amt * cache[kk]
            t = max(0.0, min(1.0, t)) ** gamma
            row.append(int(round(t * (n_steps - 1))))
        out.append(row)
    return out


bake_corner_light._scifikit_orig = _ORIG_BAKE
if getattr(_bake.bake_corner_light, "_scifikit_orig", None) is None:
    _bake.bake_corner_light = bake_corner_light
