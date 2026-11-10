"""DUNGEONKIT shared geometry (theme-agnostic, Blender space: +Z up, front faces -Y).

The dungeon/cave/temple/lake kits are built on ONE documented grid (DUNGEON GRID, docs/DUNGEONKIT.md):

- 1 cell = 4 m x 4 m; pieces snap with their origin on cell centres or cell edges; yaw in 90 degree steps;
- walls stand INSIDE the cell boundary: inner face WALL_T (0.5 m) in from the edge, so two cells side by side share
  nothing but the boundary line and corridor clear width = 4 - 2 * 0.5 = 3 m;
- storey height H = 4.5 m to the cornice top; doorways 2 m x 3 m (round arch), corridor portals 3 m x 3.5 m;
- sockets sit on cell-edge midpoints at floor level (see sockets() and kits/library/dungeonkit-sockets.json).

Walls, floors and ceilings are ONE-SIDED shells facing into the room (kit_shell_*): a camera outside a room sees in
through the near wall (back faces culled), exactly the cutaway trick N64 rooms used, and from inside every surface
reads. Relief (plinth, string course, cornice, pilasters) is part of the sheet (a height field over the wall plane),
so nothing of the near wall floats in front of an outside camera. Props are closed solids (kit_*).
"""
import math

import numpy as np

from . import meshkit as K

CELL = 4.0
WALL_T = 0.5
H = 4.5
DOOR_W, DOOR_H = 2.0, 3.0
PORTAL_W, PORTAL_H = 3.0, 3.5

# Wall cross-section (z, inset into the room, role) bottom -> top: a damp mossy plinth, the cut-stone body and a
# stepped cornice. Equal z with different insets = a horizontal step face. Lean on purpose (shell budget).
PROFILE = (
    (0.0, 0.12, "stone"), (0.5, 0.12, "stone"), (0.5, 0.0, "wall"),
    (H - 0.55, 0.0, "wall"), (H - 0.55, 0.08, "trim"), (H - 0.2, 0.2, "trim"), (H, 0.2, "trim"),
)
PIL_Z = (0.5, H - 0.55)   # pilasters run between the plinth top and the cornice bottom


# ---------------------------------------------------------------- welding / mesh hygiene
def weld_mesh(m, tol=1e-5):
    """Merge coincident vertices and drop faces that collapse (repeated corners or zero area)."""
    key, remap, verts = {}, [], []
    for p in m.v:
        k = (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))
        if k not in key:
            key[k] = len(verts)
            verts.append(p)
        remap.append(key[k])
    out = K.Mesh()
    out.v = verts
    V = np.asarray(verts)
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


def quad_ok(a, b, c, d):
    n = np.cross(np.subtract(b, a), np.subtract(d, a)) + np.cross(np.subtract(d, c), np.subtract(b, c))
    return np.linalg.norm(n) > 1e-8


# ---------------------------------------------------------------- relief wall sheet
BODY_Z = (1.5, 2.6)        # extra vertex rows in the wall body (baked torch pools / AO need vertices)


def wall_sheet(length, profile=PROFILE, openings=(), pilasters=(), seg=2.0, top_cap=WALL_T, relief=(),
               pilaster_role="trim", cap_role="trim", height=None, extra_z=BODY_Z, cap_trim=(0.0, 0.0)):
    """One-sided relief wall along +X from x=0 to x=length. Base plane y=0; the room is toward -Y (front faces -Y,
    like every kit piece). A height field over the wall plane: inset(x, z) = profile inset + pilaster depth.

    profile: [(z, inset, role)] bottom -> top (equal z twice = a horizontal step face).
    openings: [(x0, x1, z_top)] or [(x0, x1, z_top, z_bottom)] rectangular holes (doorway / slit / alcove frames are
      separate solid pieces that cover the cut edges); z_bottom defaults to the floor.
    pilasters: [(x0, x1, depth)] raised vertical strips between PIL_Z (vertical side faces at x0 / x1).
    relief: [(x0, x1, z0, z1, role)] panels of the flat wall body painted with another role.
    height: optional override of the top z (the profile is scaled vertically above the plinth).
    top_cap: depth of the horizontal ledge on the wall top (the wall's cut thickness seen from above).
    cap_trim: (start, end) lengths without top cap (where a perpendicular wall's cap already covers the corner)."""
    prof = list(profile)
    if height is not None and abs(height - prof[-1][0]) > 1e-9:
        top0 = prof[-1][0]
        base = prof[2][0]
        k = (height - base) / (top0 - base)
        prof = [(z if z <= base else base + (z - base) * k, ins, role) for z, ins, role in prof]
    ztop = prof[-1][0]
    pz0, pz1 = PIL_Z[0], prof[3][0]
    # x stations: ends, regular segments, opening / pilaster / relief edges; pilaster edges are doubled (side faces)
    xs = {0.0, float(length)}
    k = max(1, int(round(length / seg)))
    xs.update(length * i / k for i in range(k + 1))
    openings = [tuple(o) + ((0.0,) if len(o) == 3 else ()) for o in openings]
    for x0, x1, _, _ in openings:
        xs.update((x0, x1))
    if cap_trim[0] > 0:
        xs.add(cap_trim[0])
    if cap_trim[1] > 0:
        xs.add(length - cap_trim[1])
    for x0, x1, _, _, _ in relief:
        xs.update((x0, x1))
    pil_edges = set()
    for x0, x1, _ in pilasters:
        pil_edges.update((round(x0, 6), round(x1, 6)))
        xs.update((x0, x1))
    xs = sorted(x for x in xs if -1e-9 <= x <= length + 1e-9)
    cols = []
    for x in xs:
        if round(x, 6) in pil_edges:
            cols += [(x, -1), (x, +1)]
        else:
            cols.append((x, 0))
    # z levels: profile levels + opening tops + relief bands (interpolated insets)
    levels = list(prof)
    extra = set(round(zt, 6) for _, _, zt, _ in openings) | set(round(zb, 6) for _, _, _, zb in openings if zb > 0)
    extra |= set(round(z, 6) for _, _, z0, z1, _ in relief for z in (z0, z1))
    extra |= set(round(z, 6) for z in extra_z if pz0 < z < pz1)
    for z in sorted(extra):
        if any(abs(z - lz) < 1e-6 for lz, _, _ in levels):
            continue
        for i in range(len(levels) - 1):
            za, zb = levels[i][0], levels[i + 1][0]
            if za < z < zb:
                t = (z - za) / (zb - za)
                levels.insert(i + 1, (z, levels[i][1] + t * (levels[i + 1][1] - levels[i][1]), levels[i][2]))
                break

    def pil(x, z, role="wall"):
        """Pilaster depth: the plinth rows follow it (pilaster base) and it rises to the cornice bottom row of the
        wall body (z == pz1 only on the body side of the cornice step), so every step face keeps its orientation."""
        if z > pz1 + 1e-9 or (abs(z - pz1) < 1e-9 and role != "wall"):
            return 0.0
        d = 0.0
        for x0, x1, dep in pilasters:
            if x0 < x < x1:
                d = max(d, dep)
        return d

    pts = {}
    for ci, (x, side) in enumerate(cols):
        xe = x + 1e-4 * side
        for li, (z, ins, role) in enumerate(levels):
            pts[(ci, li)] = (x, -(ins + pil(xe, z, role)), z)
    m = K.Mesh()
    for ci in range(len(cols) - 1):
        xa, xb = cols[ci][0], cols[ci + 1][0]
        xm = 0.5 * (xa + xb)
        side_face = abs(xb - xa) < 1e-9
        for li in range(len(levels) - 1):
            za, zb = levels[li][0], levels[li + 1][0]
            zm = 0.5 * (za + zb)
            if any(x0 - 1e-9 <= xm <= x1 + 1e-9 and zb < zm < zt for x0, x1, zt, zb in openings):
                continue
            a, b = pts[(ci, li)], pts[(ci + 1, li)]
            c, d = pts[(ci + 1, li + 1)], pts[(ci, li + 1)]
            if not quad_ok(a, b, c, d):
                continue
            role = levels[li + 1][2] if abs(za - zb) < 1e-9 else levels[li][2]
            if side_face or (pil(xm, zm, role) > 0 and role == "wall"):
                role = pilaster_role if role == "wall" else role
            for x0, x1, z0, z1, rr in relief:
                if x0 <= xm <= x1 and z0 <= zm <= z1 and pil(xm, zm, role) == 0 and role == "wall":
                    role = rr
            m.add([a, b, c, d], [(0, 1, 2, 3)], role, False)
    if top_cap > 0:
        last = len(levels) - 1
        for ci in range(len(cols) - 1):
            a, b = pts[(ci, last)], pts[(ci + 1, last)]
            if abs(a[0] - b[0]) < 1e-9:
                continue
            xm_ = 0.5 * (a[0] + b[0])
            if xm_ < cap_trim[0] or xm_ > length - cap_trim[1]:
                continue
            c, d = (b[0], top_cap, ztop), (a[0], top_cap, ztop)
            if quad_ok(a, b, c, d):
                m.add([a, b, c, d], [(0, 1, 2, 3)], cap_role, False)
    return weld_mesh(m)


def place(m, x=0.0, y=0.0, z=0.0, yaw_deg=0.0):
    """Rotate about +Z (Blender) by yaw_deg then translate."""
    if yaw_deg:
        m.rotate_z(math.radians(yaw_deg))
    return m.translate(x, y, z)


# ---------------------------------------------------------------- floors / ceilings
def floor_grid(x0, y0, x1, y1, z=0.0, step=2.0, role="floor", holes=(), border=0.0, border_role="trim"):
    """One-sided floor facing +Z over [x0,x1]x[y0,y1], tessellated every ~step metres (vertex light needs vertices).
    holes: [(hx0, hy0, hx1, hy1)] rectangles left open (pits). border: width of a ring of border_role along the edge."""
    def stations(a, b):
        k = max(1, int(round((b - a) / step)))
        s = {a + (b - a) * i / k for i in range(k + 1)}
        if border > 0 and b - a > 2 * border + 0.1:
            s.update((a + border, b - border))
        for hx0, hy0, hx1, hy1 in holes:
            pass
        return s
    xs = stations(x0, x1)
    ys = stations(y0, y1)
    for hx0, hy0, hx1, hy1 in holes:
        xs.update((hx0, hx1))
        ys.update((hy0, hy1))
    xs = sorted(xs)
    ys = sorted(ys)
    m = K.Mesh()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
            if any(hx0 <= cx <= hx1 and hy0 <= cy <= hy1 for hx0, hy0, hx1, hy1 in holes):
                continue
            role_ = role
            if border > 0 and (cx < x0 + border or cx > x1 - border or cy < y0 + border or cy > y1 - border):
                role_ = border_role
            m.add([(xs[i], ys[j], z), (xs[i + 1], ys[j], z), (xs[i + 1], ys[j + 1], z), (xs[i], ys[j + 1], z)],
                  [(0, 1, 2, 3)], role_, False)
    return weld_mesh(m)


def barrel_vault(length, span, z0, rise, segs=6, role="ceiling", step=2.0):
    """One-sided barrel vault facing DOWN (into the corridor) along +Y, spanning x in [-span/2, span/2]."""
    k = max(1, int(round(length / step)))
    ys = [length * i / k - length / 2 for i in range(k + 1)]
    ring = []
    for s in range(segs + 1):
        a = math.pi * s / segs
        ring.append((-span / 2 * math.cos(a), z0 + rise * math.sin(a)))
    m = K.Mesh()
    for j in range(len(ys) - 1):
        for s in range(segs):
            (xa, za), (xb, zb) = ring[s], ring[s + 1]
            a, b = (xa, ys[j], za), (xb, ys[j], zb)
            c, d = (xb, ys[j + 1], zb), (xa, ys[j + 1], za)
            m.add([a, d, c, b], [(0, 1, 2, 3)], role, True)
    return weld_mesh(m)


def flat_ceiling(x0, y0, x1, y1, z, step=2.0, role="ceiling"):
    """One-sided ceiling facing DOWN."""
    m = floor_grid(x0, y0, x1, y1, z, step, role)
    return m.flip()


# ---------------------------------------------------------------- closed solids
def bevel_box(cx, cy, z0, sx, sy, sz, role, bevel=0.06, top_role=None, k_corner=1):
    """Closed box with chamfered vertical edges and a bevelled top rim (never a raw cuboid)."""
    b = max(0.005, min(bevel, 0.45 * min(sx, sy), 0.45 * sz))
    outline = K.rounded_rect2d(sx, sy, b, k_corner)
    inner = K.rounded_rect2d(max(0.01, sx - 2 * b), max(0.01, sy - 2 * b), max(0.005, b * 0.5), k_corner)
    rings = [K.ring3d(cx, cy, z0, outline), K.ring3d(cx, cy, z0 + sz - b, outline), K.ring3d(cx, cy, z0 + sz, inner)]
    m = K.loft(rings, role, smooth=False, cap_roles=(role, top_role or role))
    return m


def taper_loft(cx, cy, z_levels, half_sizes, role, k_corner=1, bevel=0.04, roles=None, smooth=False):
    """Stacked chamfered rings (plinths, pedestals, tapering pillars). half_sizes: [(hx, hy)] per level."""
    rings = []
    for z, (hx, hy) in zip(z_levels, half_sizes):
        rings.append(K.ring3d(cx, cy, z, K.rounded_rect2d(2 * hx, 2 * hy, min(bevel, 0.45 * min(hx, hy) * 2), k_corner)))
    return K.loft(rings, role, smooth=smooth, roles=roles)


def lumpy_loft(path_rings, rs, jitter=0.12, role="rock", smooth=True, roles=None, cap0=True, cap1=True):
    """Organic loft: each ring (list of (x, y, z)) displaced radially by seeded noise (rounded rock forms)."""
    rings = []
    for ring in path_rings:
        P = np.asarray(ring, dtype=np.float64)
        c = P.mean(0)
        out = []
        for p in P:
            d = p - c
            d[2] = 0.0
            ln = np.linalg.norm(d)
            f = 1.0 + jitter * (rs.random() * 2.0 - 1.0)
            out.append(tuple(c + (p - c) * np.array([f, f, 1.0])))
        rings.append(out)
    return K.loft(rings, role, smooth=smooth, roles=roles, cap0=cap0, cap1=cap1)


def rock_blob(cx, cy, cz, rx, ry, rz, rs, role="rock", segs=7, rings=4, jitter=0.18, flat_bottom=True):
    """Rounded faceted rock: a low-poly ellipsoid with seeded radial jitter (shared vertices stay welded)."""
    prof = []
    for j in range(rings + 1):
        a = -math.pi / 2 + math.pi * j / rings
        prof.append((math.cos(a), math.sin(a)))
    rings_pts = []
    for j, (c, s) in enumerate(prof):
        z = cz + rz * s
        if flat_bottom and j == 0:
            z = cz - rz * 0.55
        if j in (0, rings):
            rings_pts.append(None)
            continue
        ring = []
        for i in range(segs):
            t = 2 * math.pi * i / segs + (0.3 * j)
            f = 1.0 + jitter * (rs.random() * 2 - 1)
            ring.append((cx + rx * c * math.cos(t) * f, cy + ry * c * math.sin(t) * f, z + rz * 0.12 * (rs.random() - 0.5)))
        rings_pts.append(ring)
    mids = [r for r in rings_pts if r is not None]
    bottom = (cx, cy, cz - rz * (0.55 if flat_bottom else 1.0))
    top = (cx, cy, cz + rz)
    verts = [bottom] + [p for r in mids for p in r] + [top]
    faces = []
    k = segs
    for i in range(k):
        faces.append((0, 1 + (i + 1) % k, 1 + i))
    for j in range(len(mids) - 1):
        a0 = 1 + j * k
        b0 = 1 + (j + 1) * k
        for i in range(k):
            faces.append((a0 + i, a0 + (i + 1) % k, b0 + (i + 1) % k, b0 + i))
    t = len(verts) - 1
    last = 1 + (len(mids) - 1) * k
    for i in range(k):
        faces.append((last + i, last + (i + 1) % k, t))
    return K.Mesh().add(verts, faces, role, True).orient_outward()


def arch_ring(width, height, depth, thickness, role="frame", segs=8, z0=0.0, keystone=True):
    """Closed round-arch frame (two jambs + semicircular head) as one solid ring, centred at x=0, front at y=0
    (extends to +y by depth). Inner opening width x height (springing at height - width/2)."""
    r_in = width / 2
    r_out = r_in + thickness
    spring = height - r_in
    inner, outer = [], []
    # outline of the arch ring in (x, z), CCW: outer boundary then inner reversed -> one polygon with a slot is not
    # possible for prism(); build as loft of the U-shaped section along the path instead.
    path = [(-r_in - thickness / 2, z0)]
    path.append((-r_in - thickness / 2, z0 + spring))
    for s in range(1, segs):
        a = math.pi - math.pi * s / segs
        path.append(((r_in + thickness / 2) * math.cos(a), z0 + spring + (r_in + thickness / 2) * math.sin(a)))
    path.append((r_in + thickness / 2, z0 + spring))
    path.append((r_in + thickness / 2, z0))
    # sweep a rectangle (thickness x depth) along the path in the XZ plane
    rings = []
    n = len(path)
    for i, (x, z) in enumerate(path):
        if i == 0:
            tx, tz = path[1][0] - x, path[1][1] - z
        elif i == n - 1:
            tx, tz = x - path[i - 1][0], z - path[i - 1][1]
        else:
            tx, tz = path[i + 1][0] - path[i - 1][0], path[i + 1][1] - path[i - 1][1]
        ln = math.hypot(tx, tz) or 1.0
        nx, nz = tz / ln, -tx / ln          # outward normal in XZ (path runs left -> over -> right)
        h = thickness / 2
        if i in (0, n - 1):
            nx, nz = (-1.0 if i == 0 else 1.0), 0.0
            sc = 1.0
        else:
            sc = 1.0
        ring = [(x - nx * h * sc, 0.0, z - nz * h * sc), (x + nx * h * sc, 0.0, z + nz * h * sc),
                (x + nx * h * sc, depth, z + nz * h * sc), (x - nx * h * sc, depth, z - nz * h * sc)]
        rings.append(ring)
    return K.loft(rings, role, smooth=False)


def sockets_doc():
    return {"cell_m": CELL, "wall_inset_m": WALL_T, "storey_m": H, "doorway_m": [DOOR_W, DOOR_H],
            "portal_m": [PORTAL_W, PORTAL_H]}
