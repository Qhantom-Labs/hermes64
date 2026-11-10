"""MEDIEVALKIT shared geometry (theme-agnostic; Blender space: +Z up, front faces -Y = glTF +Z = south).

All medieval kit families (village, castle, props, nature, terrain/sky) are built from these helpers on one
documented grid (MEDIEVAL GRID, docs/MEDIEVALKIT.md):

- 1 cell = 4 m (the same cell as the dungeon kits, so castle cells can meet dungeon corridors), half cell 2 m for
  free-standing exterior lots; grid pieces turn in 90-degree steps;
- interior walls stand 0.5 m inside the plot edge (plot = cells x 4 m + 0.5 m apron each side); the door anchor is
  room.gd's own convention (side cell i -> door.position 4 i + 2, anchor 0.4 m in from the edge);
- village storey 3.4 m to the wall plate, castle storey 4.5 m; village doorway 1.6 x 2.5 m, castle 2.0 x 3.0 m.

Forms are never raw cuboids: beams have a bevelled (trapezoid) section, posts taper, boxes are chamfered, roofs are
lofted with rolled eaves, and a deterministic position-hash jitter gives hand-made irregularity without breaking
welds. Interior walls/floors/ceilings are one-sided inward shells (kit_shell_: the runtime's N64 cutaway sees
through near walls); everything else is a closed solid (kit_).

Baking: pieces that carry light (torches, braziers, lanterns, hearths, glowing windows) list them in
meta["bake_lights"] (asset space, +Z up); the shared core bakes them into vertex colour only when the pack light rig opts
in (point_bake), and real ray AO only with ao_occlusion (kits/core/bake.asset_rig, pack data). No hook, no monkeypatch.
"""
import math

import numpy as np

from . import bake
from . import meshkit as K
from .asset import Asset, Node

CELL = 4.0
SUB = 2.0
APRON = 0.5
WALL_T = 0.5
V_H = 3.4
C_H = 4.5
V_DOOR = (1.6, 2.5)
C_DOOR = (2.0, 3.0)
TAU = 2.0 * math.pi


# ---------------------------------------------------------------- mesh hygiene
def weld(m, tol=1e-5):
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
    V = np.asarray(verts, dtype=np.float64) if verts else np.zeros((0, 3))
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
        uv = m.uv[fi]
        if uv is not None and len(uv[1]) != len(g):
            uv = None
        out.f.append(tuple(g))
        out.r.append(m.r[fi])
        out.s.append(m.s[fi])
        out.uv.append(uv)
    return out


def swap_uv(m):
    """Swap u and v of metric UVs (roof slopes: v runs down the slope so streak textures follow the fall line)."""
    m.uv = [u if (u is None or u[0] != "m") else ("m", [(b, a) for a, b in u[1]]) for u in m.uv]
    return m


def _h(ix, iy, iz, salt):
    n = (ix * 73856093 ^ iy * 19349663 ^ iz * 83492791 ^ salt * 2654435761) & 0xFFFFFFFF
    n = ((n << 13) ^ n) & 0xFFFFFFFF
    n = (n * ((n * n * 15731 + 789221) & 0xFFFFFFFF) + 1376312589) & 0x7FFFFFFF
    return n / 2147483647.0


def jitter(m, seed, amount, axes=(1.0, 1.0, 1.0), keep_z0=True):
    """Deterministic hand-made irregularity: every vertex moves by a hash of its own position, so coincident
    (welded) vertices move together and closed solids stay closed. keep_z0 keeps ground-contact vertices flat."""
    out = []
    for p in m.v:
        ix, iy, iz = int(round(p[0] * 1000)), int(round(p[1] * 1000)), int(round(p[2] * 1000))
        d = [(2.0 * _h(ix, iy, iz, seed * 3 + k + 1) - 1.0) * amount * axes[k] for k in range(3)]
        if keep_z0 and abs(p[2]) < 1e-6:
            d[2] = 0.0
        out.append((p[0] + d[0], p[1] + d[1], p[2] + d[2]))
    m.v = out
    return m


def merged(*meshes):
    out = K.Mesh()
    for x in meshes:
        if x is not None:
            out.merge(x)
    return out


# ---------------------------------------------------------------- closed solids
def loft_y(sections, ys, role, roles=None, cap_roles=None, smooth=False, scale_z=None, scale_x=None, z_off=None):
    """Loft one closed 2D section [(x, z)] (CCW seen from -Y) along +Y through stations ys (closed with caps).
    scale_x / scale_z / z_off: optional per-station factors (hip roofs, tapers)."""
    rings = []
    for j, y in enumerate(ys):
        sec = sections[j] if isinstance(sections[0][0], (list, tuple)) else sections
        sx = scale_x[j] if scale_x else 1.0
        sz = scale_z[j] if scale_z else 1.0
        zo = z_off[j] if z_off else 0.0
        rings.append([(x * sx, y, z * sz + zo) for x, z in sec])
    m = K.loft(rings, role, smooth=smooth, roles=roles, cap_roles=cap_roles)
    return m


def chamfer_box(cx, cy, z0, sx, sy, sz, role, bevel=0.05, top_role=None, base_bevel=0.0):
    """Closed box whose top rim (and optionally base rim) is bevelled inward: never a raw cuboid (sloped bevel
    normals), 20-28 triangles."""
    b = max(0.004, min(bevel, 0.45 * min(sx, sy), 0.45 * sz))
    out = [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]
    inn = [(-sx / 2 + b, -sy / 2 + b), (sx / 2 - b, -sy / 2 + b), (sx / 2 - b, sy / 2 - b), (-sx / 2 + b, sy / 2 - b)]
    rings = []
    if base_bevel > 0:
        bb = max(0.004, min(base_bevel, 0.45 * min(sx, sy), 0.3 * sz))
        rings.append([(cx + x * (1 - 2 * bb / sx), cy + y * (1 - 2 * bb / sy), z0) for x, y in out])
        rings.append([(cx + x, cy + y, z0 + bb) for x, y in out])
    else:
        rings.append([(cx + x, cy + y, z0) for x, y in out])
    rings.append([(cx + x, cy + y, z0 + sz - b) for x, y in out])
    rings.append([(cx + x, cy + y, z0 + sz) for x, y in inn])
    return K.loft(rings, role, smooth=False, cap_roles=(role, top_role or role))


def octa_box(cx, cy, z0, sx, sy, sz, role, chamfer=0.08, top_role=None, top_bevel=0.04):
    """Box with chamfered vertical edges (octagonal plan) and a bevelled top: chunky N64 crates, plinths, merlons."""
    c = max(0.004, min(chamfer, 0.45 * min(sx, sy)))
    hx, hy = sx / 2, sy / 2
    ring = [(hx - c, -hy), (hx, -hy + c), (hx, hy - c), (hx - c, hy), (-hx + c, hy), (-hx, hy - c), (-hx, -hy + c), (-hx + c, -hy)]
    tb = max(0.003, min(top_bevel, 0.4 * sz, 0.4 * min(sx, sy)))
    fx, fy = (hx - tb) / hx, (hy - tb) / hy
    rings = [[(cx + x, cy + y, z0) for x, y in ring], [(cx + x, cy + y, z0 + sz - tb) for x, y in ring],
             [(cx + x * fx, cy + y * fy, z0 + sz) for x, y in ring]]
    return K.loft(rings, role, smooth=False, cap_roles=(role, top_role or role))


def beam(p0, p1, w, h, role, out=(0.0, -1.0, 0.0), bevel=0.3, embed=0.03):
    """Timber beam from p0 to p1 with a trapezoid section: back face width w on the surface plane, front face
    (protruding h along `out`) narrower by `bevel` (hand-adzed bevelled edges). The back sits `embed` inside the
    surface so it never shares vertices with the wall it decorates. 12 triangles."""
    a, b = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    d = b - a
    L = float(np.linalg.norm(d))
    if L < 1e-6:
        return None
    d /= L
    o = np.asarray(out, dtype=np.float64)
    o = o - d * float(np.dot(o, d))
    o /= max(np.linalg.norm(o), 1e-12)
    s = np.cross(d, o)
    bw, fw = w / 2.0, w / 2.0 * (1.0 - bevel)
    back = -embed
    sec = [(-bw, back), (bw, back), (fw, h), (-fw, h)]
    rings = []
    for p in (a, b):
        rings.append([tuple(p + s * u + o * t) for u, t in sec])
    m = K.loft(rings, role, smooth=False)
    return m


def post(x, y, z0, z1, r0, r1, role, sides=6, start=None, smooth=False, cap_role=None):
    """Tapered polygonal post (closed): r0 at the foot, r1 at the head."""
    st = (math.pi / sides) if start is None else start
    m = K.lathe([(r0, 0.0), (r1, z1 - z0)], sides, role, smooth=smooth, start=st, cap_roles=(role, cap_role or role))
    return m.translate(x, y, z0)


def rounded_lathe(profile, segs, role, smooth=True, start=0.0, roles=None, cap_roles=None, rx=1.0, ry=1.0):
    return K.lathe(profile, segs, role, smooth=smooth, start=start, roles=roles, cap_roles=cap_roles, rx=rx, ry=ry)


def blob(cx, cy, cz, rx, ry, rz, role, seed, segs=8, rings=5, lump=0.14, flat=0.0, smooth=True):
    """Lumpy ellipsoid (tree canopies, hay, bushes, rocks): a low-poly sphere whose rings are pushed in/out by a
    seeded hash (poles stay on the axis, so the solid stays closed)."""
    prof = []
    for j in range(rings + 1):
        a = -math.pi / 2 + math.pi * j / rings
        prof.append((math.cos(a), math.sin(a)))
    verts = []
    ids = []
    for j, (c, s) in enumerate(prof):
        z = cz + rz * s
        if flat > 0 and s < 0:
            z = cz + rz * s * (1.0 - flat)
        if j == 0 or j == rings:
            ids.append([len(verts)])
            verts.append((cx, cy, z))
            continue
        row = []
        for i in range(segs):
            t = TAU * i / segs + 0.37 * j
            f = 1.0 + lump * (2.0 * _h(i, j, segs, seed + 17) - 1.0)
            row.append(len(verts))
            verts.append((cx + rx * c * math.cos(t) * f, cy + ry * c * math.sin(t) * f, z + rz * lump * 0.4 * (_h(j, i, 3, seed) - 0.5)))
        ids.append(row)
    faces = []
    for j in range(len(ids) - 1):
        A, B = ids[j], ids[j + 1]
        for i in range(segs):
            if len(A) == 1:
                faces.append((A[0], B[(i + 1) % segs], B[i]))
            elif len(B) == 1:
                faces.append((A[i], A[(i + 1) % segs], B[0]))
            else:
                faces.append((A[i], A[(i + 1) % segs], B[(i + 1) % segs], B[i]))
    return K.Mesh().add(verts, faces, role, smooth).orient_outward()


def arch_frame(shape, width, height, depth, thick, role, segs=8, z0=0.0, y0=0.0):
    """Closed frame (two jambs + head) around an opening width x height of `shape` (rect / lintel / arch /
    pointed), centred on x=0, from y0 to y0+depth: a thick x depth section swept along the frame's centre line,
    mitred at corners, flat on the ground at both feet."""
    line = opening_outline(shape, width + thick, height + thick / 2.0, segs)
    # drop the bottom edge: the outline starts (-w/2, 0), (w/2, 0); walk from the right foot over the head to the left
    path = line[1:] + line[:1]
    path = list(reversed(path))          # left foot -> head -> right foot
    if path[0][0] > path[-1][0]:
        path = list(reversed(path))
    P = [np.array([x, z + z0]) for x, z in path]
    n = len(P)
    rings = []
    h = thick / 2.0
    for i in range(n):
        if i == 0 or i == n - 1:
            t = (P[1] - P[0]) if i == 0 else (P[n - 1] - P[n - 2])
            t = t / max(np.linalg.norm(t), 1e-12)
            nn = np.array([t[1], -t[0]])          # same side convention as the interior mitres (no twisted end band)
            sc = 1.0
        else:
            ta = P[i] - P[i - 1]
            tb = P[i + 1] - P[i]
            ta /= max(np.linalg.norm(ta), 1e-12)
            tb /= max(np.linalg.norm(tb), 1e-12)
            na = np.array([ta[1], -ta[0]])
            nb = np.array([tb[1], -tb[0]])
            nn = na + nb
            ln = np.linalg.norm(nn)
            nn = na if ln < 1e-9 else nn / ln
            sc = 1.0 / max(0.35, float(np.dot(nn, na)))
        x, z = P[i]
        dx, dz = nn[0] * h * sc, nn[1] * h * sc
        rings.append([(x - dx, y0, z - dz), (x + dx, y0, z + dz), (x + dx, y0 + depth, z + dz), (x - dx, y0 + depth, z - dz)])
    return K.loft(rings, role, smooth=False)


def opening_outline(shape, w, h, segs=8):
    """Opening outline (x, z) bottom at z=0, CCW: rect, arch (round top), pointed (lancet), lintel (flat, chamfer)."""
    if shape == "arch":
        r = w / 2.0
        sp = max(0.0, h - r)
        pts = [(-r, 0.0), (r, 0.0), (r, sp)]
        for i in range(1, segs):
            a = math.pi * i / segs
            pts.append((r * math.cos(a), sp + r * math.sin(a)))
        pts.append((-r, sp))
        return pts
    if shape == "pointed":
        sp = max(0.0, h - 0.8 * w)
        rise = h - sp
        pts = [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, sp)]
        k = max(2, segs // 2)
        for i in range(1, k):
            t = i / k
            pts.append((w / 2 * (1 - t) ** 1.25 * (1 - 0.15 * t), sp + rise * math.sin(t * math.pi / 2) ** 0.9))
        pts.append((0.0, h))
        for i in range(k - 1, 0, -1):
            t = i / k
            pts.append((-w / 2 * (1 - t) ** 1.25 * (1 - 0.15 * t), sp + rise * math.sin(t * math.pi / 2) ** 0.9))
        pts.append((-w / 2, sp))
        return pts
    if shape == "lintel":
        c = min(0.12, w * 0.15)
        return [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h - c), (w / 2 - c, h), (-w / 2 + c, h), (-w / 2, h - c)]
    return [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h), (-w / 2, h)]


def slab_y(outline_xz, y0, y1, role, smooth=False):
    """Extrude an (x, z) outline along +Y from y0 to y1 (closed solid; door leaves, window panes, gable slabs)."""
    m = K.prism([(x, z) for x, z in outline_xz], y0, y1, role)
    m.apply(lambda a: a[:, [0, 2, 1]])
    return m.orient_outward()


def ring_path_solid(path_xy, z0, z1, width, role, closed=True, chamfer=0.0):
    """A wall-like solid following a 2D path (closed ring or open polyline) with given width; optional top chamfer.
    Used for well rims, round tower parapet walks, garden kerbs."""
    P = [np.asarray(p, dtype=np.float64) for p in path_xy]
    n = len(P)
    inner, outer = [], []
    for i in range(n):
        if closed:
            a, b = P[i - 1], P[(i + 1) % n]
        else:
            a, b = P[max(i - 1, 0)], P[min(i + 1, n - 1)]
        t = b - a
        t /= max(np.linalg.norm(t), 1e-12)
        nrm = np.array([t[1], -t[0]])
        outer.append(P[i] + nrm * width / 2)
        inner.append(P[i] - nrm * width / 2)
    m = K.Mesh()
    if closed:
        rings = []
        c = chamfer
        for z, shrink in ((z0, 0.0), (z1 - c, 0.0), (z1, c)):
            rings.append(([tuple(p) for p in outer], [tuple(p) for p in inner], z, shrink))
        # build as lathe-like ring band: outer wall, inner wall, top, bottom
        verts = []
        def idx(level, side, i):
            return (level * 2 + side) * n + i
        levels = [(z0, 0.0), (z1 - chamfer, 0.0), (z1, chamfer)] if chamfer > 0 else [(z0, 0.0), (z1, 0.0)]
        for z, c in levels:
            for side, pts in ((0, outer), (1, inner)):
                for i in range(n):
                    p = pts[i]
                    q = P[i]
                    d = q - p
                    dl = np.linalg.norm(d)
                    pp = p + (d / dl * c if dl > 1e-9 and c > 0 else 0.0)
                    verts.append((float(pp[0]), float(pp[1]), z))
        faces = []
        L = len(levels)
        for lv in range(L - 1):
            for i in range(n):
                j = (i + 1) % n
                faces.append((idx(lv, 0, i), idx(lv, 0, j), idx(lv + 1, 0, j), idx(lv + 1, 0, i)))
                faces.append((idx(lv, 1, j), idx(lv, 1, i), idx(lv + 1, 1, i), idx(lv + 1, 1, j)))
        top = L - 1
        for i in range(n):
            j = (i + 1) % n
            faces.append((idx(top, 0, i), idx(top, 0, j), idx(top, 1, j), idx(top, 1, i)))
            faces.append((idx(0, 0, j), idx(0, 0, i), idx(0, 1, i), idx(0, 1, j)))
        m.add(verts, faces, role, False)
        return m.orient_outward()
    poly = [tuple(p) for p in outer] + [tuple(p) for p in reversed(inner)]
    return K.prism(poly, z0, z1, role)


# ---------------------------------------------------------------- roofs
def roof_skins(half_w, rise, thick, droop=0.15, bulge=0.0, ridge_round=0.0, n=4, lip=0.0):
    """(upper, lower) skins of a pitched roof section: upper runs left eave -> ridge -> right eave, lower runs back
    right -> left under it (offset down by the thickness, pulled in at the eaves = rolled lip). Concatenated they form
    one closed loop."""
    top = []
    for i in range(n + 1):
        t = i / n
        x = -half_w + half_w * t
        z = rise * t + bulge * math.sin(math.pi * t) * rise
        if ridge_round > 0 and t > 0.75:
            z -= ridge_round * ((t - 0.75) / 0.25) ** 2
        top.append((x, z))
    right = [(-x, z) for x, z in reversed(top[:-1])]
    upper = top + right
    upper[0] = (upper[0][0], upper[0][1] - droop)
    upper[-1] = (upper[-1][0], upper[-1][1] - droop)
    lower = [(x * (1.0 - 0.02), z - thick) for x, z in reversed(upper)]
    lower[0] = (upper[-1][0] - (thick * 0.6 + lip), upper[-1][1] - thick * 0.55)
    lower[-1] = (upper[0][0] + (thick * 0.6 + lip), upper[0][1] - thick * 0.55)
    return upper, lower


def roof_section(half_w, rise, thick, droop=0.15, bulge=0.0, ridge_round=0.0, n=4, lip=0.0):
    """Closed (x, z) section of a pitched roof, eaves at x = +-half_w (z = -droop .. lip), ridge at z = rise.
    bulge > 0 swells the slopes (thatch), ridge_round rounds the ridge, lip rolls the eave edge down. CCW."""
    top = []
    for i in range(n + 1):
        t = i / n
        x = -half_w + half_w * t
        z = rise * t + bulge * math.sin(math.pi * t) * rise
        if ridge_round > 0 and t > 0.75:
            z -= ridge_round * ((t - 0.75) / 0.25) ** 2
        top.append((x, z))
    right = [(-x, z) for x, z in reversed(top[:-1])]
    upper = top + right
    upper[0] = (upper[0][0], upper[0][1] - droop)
    upper[-1] = (upper[-1][0], upper[-1][1] - droop)
    lower = []
    for x, z in reversed(upper):
        # soffit: offset straight down by the thatch thickness, pulled in at the eaves (rolled lip)
        lower.append((x * (1.0 - 0.02), z - thick))
    lower[0] = (upper[-1][0] - (thick * 0.6 + lip) * (1 if upper[-1][0] > 0 else -1), upper[-1][1] - thick * 0.55)
    lower[-1] = (upper[0][0] + (thick * 0.6 + lip), upper[0][1] - thick * 0.55)
    sec = upper + lower
    return K.ccw(sec)


def roof_pitched(w, d, z0, rise, thick, role, overhang=0.35, gable_overhang=0.3, droop=0.12, bulge=0.0,
                 ridge_round=0.0, hip=0.0, n=4, ridge_role=None, stations=None, sag=0.0):
    """Gable (hip=0) or hipped (hip = run of the hip end in metres) roof solid over a w x d footprint; ridge along
    Y. Lofted along Y; v of the slope UVs runs down the fall line (swap_uv). Ridge sag gives an old, hand-built
    line."""
    hw = w / 2.0 + overhang
    D = d / 2.0 + gable_overhang
    sec = roof_section(hw, rise, thick, droop, bulge, ridge_round, n)
    sec = [(x, z + z0) for x, z in sec]
    if hip > 0:
        # true hip: toward each end the slopes fall to the eave line while the eaves run on around the end, so every
        # station scales the upper skin about the upper eave height and the lower skin about the lower eave height
        # (thickness stays positive; the end station is a thin eave sliver, never degenerate)
        up, lo = roof_skins(hw, rise, thick, droop, bulge, ridge_round, n)
        ue, le = up[0][1], lo[0][1]
        hr = min(hip, D * 0.9)
        ys = [-D, -D + hr * 0.5, -D + hr, D - hr, D - hr * 0.5, D]

        def hipped(f):
            u2 = [(x, z0 + ue + (z - ue) * f) for x, z in up]
            l2 = [(x, z0 + le + (z - le) * f) for x, z in lo]
            return K.ccw(u2 + l2)
        fs = [0.08, 0.54, 1.0, 1.0, 0.54, 0.08]
        m = loft_y([hipped(f) for f in fs], ys, role)
    else:
        ys = stations or [-D, -D / 3.0, D / 3.0, D]
        zs = [(-sag * math.sin(math.pi * (y + D) / (2 * D))) for y in ys]
        m = loft_y(sec, ys, role, z_off=zs)
    return roof_uvs(m)


def roof_uvs(m):
    """Metric roof UVs so thatch courses / slate rows run level on every face: u along the eave direction, v = distance
    up the fall line (z / sin(slope)), increasing toward the ridge; soffits (facing down) take planar UVs."""
    V = np.asarray(m.v, dtype=np.float64)
    fn = bake.face_normals(V, m.f)
    out = []
    for f, n_ in zip(m.f, fn):
        if n_[2] < -0.3:
            out.append(None)
            continue
        side = abs(n_[0]) >= abs(n_[1])
        a = abs(n_[0]) if side else abs(n_[1])
        s = math.sqrt(a * a + n_[2] * n_[2]) / max(a, 0.05)
        out.append(("m", [((V[i][1] if side else V[i][0]), V[i][2] * s) for i in f]))
    m.uv = out
    return m


def cone_roof(r, z0, h, role, overhang=0.3, droop=0.15, thick=0.2, segs=10, flare=0.25, tip=0.0, start=0.0):
    """Conical (segs >= 8) or pyramid (segs = 4, start = 45 deg) roof with a flared, drooping eave. Closed."""
    R = r + overhang
    prof = [(max(0.05, r - thick), z0 - thick * 0.4), (R, z0 - droop), (R * 0.9, z0 + h * 0.06 * (1 + flare))]
    for t in (0.35, 0.65):
        prof.append((R * 0.9 * (1 - t) ** (1.0 + flare * 0.6), z0 + h * t))
    if tip > 0:
        prof.append((tip, z0 + h * 0.96))
    prof.append((0.0, z0 + h))
    m = K.lathe(prof, segs, role, smooth=segs >= 8, start=start)
    return m


# ---------------------------------------------------------------- building bodies and interior sheets
class Body:
    """Tapered building body in the canonical house frame: ridge along Y, eave walls at +-X, gable walls at +-Y.
    Footprint half extents hw, hd at z=0 shrink by `taper` metres per metre of height (walls lean in slightly, the
    hand-built storybook look). surf(side, u, z) returns a point on a wall surface (u runs along the wall: y for the
    +-x walls, x for the +-y walls); outward(side) its normal."""

    def __init__(self, w, d, eave, ridge, taper=0.015, z0=0.0, gable=True):
        self.hw, self.hd, self.eave, self.ridge, self.t, self.z0, self.gable = w / 2.0, d / 2.0, eave, ridge, taper, z0, gable

    def hwz(self, z):
        return self.hw - self.t * (z - self.z0)

    def hdz(self, z):
        return self.hd - self.t * (z - self.z0)

    def surf(self, side, u, z):
        if side == "-x":
            return (-self.hwz(z), u, z)
        if side == "+x":
            return (self.hwz(z), u, z)
        if side == "-y":
            return (u, -self.hdz(z), z)
        return (u, self.hdz(z), z)

    def outward(self, side):
        t = self.t
        n = {"-x": (-1.0, 0.0, t), "+x": (1.0, 0.0, t), "-y": (0.0, -1.0, t), "+y": (0.0, 1.0, t)}[side]
        ln = math.sqrt(sum(c * c for c in n))
        return tuple(c / ln for c in n)

    def top(self, side, u):
        """Wall top at u: the eave on +-x walls; the gable line on +-y walls."""
        if side in ("-x", "+x") or not self.gable:
            return self.eave
        hw = self.hwz(self.eave)
        return self.eave + (self.ridge - self.eave) * max(0.0, 1.0 - abs(u) / hw)

    def mesh(self, role, rows=(1.3,), base_role=None, base_h=0.0):
        zs = sorted(set([self.z0] + [z for z in rows if self.z0 < z < self.eave] + [self.eave]))
        sec = [(-self.hwz(z), z) for z in zs] + ([(0.0, self.ridge)] if self.gable else []) + [(self.hwz(z), z) for z in reversed(zs)]
        sec = K.ccw(sec)
        t = self.t
        front = [(x, -self.hd + t * (z - self.z0), z) for x, z in sec]
        back = [(x, self.hd - t * (z - self.z0), z) for x, z in sec]
        m = K.loft([front, back], role, smooth=False)
        if base_role and base_h > 0:
            for fi, f in enumerate(m.f):
                zc = sum(m.v[i][2] for i in f) / len(f)
                if zc < base_h:
                    m.r[fi] = base_role
        return m


class Shifted:
    """A Body seen through a translation (jettied upper storeys, porches)."""

    def __init__(self, body, dx=0.0, dy=0.0):
        self.b, self.d = body, (dx, dy, 0.0)
        self.eave, self.ridge, self.hw, self.hd = body.eave, body.ridge, body.hw, body.hd

    def surf(self, side, u, z):
        p = self.b.surf(side, u, z)
        return (p[0] + self.d[0], p[1] + self.d[1], p[2])

    def outward(self, side):
        return self.b.outward(side)

    def hwz(self, z):
        return self.b.hwz(z)

    def hdz(self, z):
        return self.b.hdz(z)

    def top(self, side, u):
        return self.b.top(side, u)


def house_body(w, d, eave, ridge, role, rows=(0.45, 1.3), base_role=None, base_h=0.0, gable=True, taper=0.0):
    """Closed body of a building (Body.mesh): pentagon section (rectangle + gable triangle) along Y with extra
    horizontal vertex rows (vertex light / contact AO need vertices on big walls). gable=False -> flat top."""
    return Body(w, d, eave, ridge, taper, gable=gable).mesh(role, rows, base_role, base_h)


def wall_sheet(length, height, role, openings=(), posts=(), post_depth=0.06, post_role="frame", plinth=(0.0, 0.0, None),
               rows=(), seg=2.0, cap=0.0, cap_role=None, rails=(), rail_role=None):
    """One-sided interior wall along +X (0..length) facing -Y (the room side), base plane y=0, as a height field:
    `posts` [(x0, x1)] raised by post_depth (timber framing / pilasters); `rails` [(z0, z1)] raised horizontal bands;
    plinth (h, depth, role) a raised base band; openings [(x0, x1, z0, z1)] rectangular holes (frames cover edges).
    `cap` > 0 adds the wall top ledge (thickness seen from above, toward +Y)."""
    ph, pd, prole = plinth
    xs = {0.0, float(length)}
    k = max(1, int(round(length / seg)))
    xs.update(length * i / k for i in range(k + 1))
    for x0, x1, _, _ in openings:
        xs.update((x0, x1))
    pe = set()
    for x0, x1 in posts:
        pe.update((round(x0, 6), round(x1, 6)))
        xs.update((x0, x1))
    xs = sorted(x for x in xs if -1e-9 <= x <= length + 1e-9)
    zs = {0.0, float(height)}
    zs.update(r for r in rows if 0 < r < height)
    if ph > 0:
        zs.add(ph)
    for z0, z1 in rails:
        zs.update((z0, z1))
    for _, _, z0, z1 in openings:
        zs.update((z0, z1))
    zs = sorted(z for z in zs if -1e-9 <= z <= height + 1e-9)
    cols = []
    for x in xs:
        if round(x, 6) in pe:
            cols += [(x, -1), (x, 1)]
        else:
            cols.append((x, 0))
    levs = []
    for z in zs:
        rail_edge = any(abs(z - a) < 1e-9 or abs(z - b) < 1e-9 for a, b in rails) or (ph > 0 and abs(z - ph) < 1e-9)
        if rail_edge:
            levs += [(z, -1), (z, 1)]
        else:
            levs.append((z, 0))

    def depth(x, z):
        d = 0.0
        if ph > 0 and z < ph:
            d = max(d, pd)
        for a, b in rails:
            if a < z < b:
                d = max(d, post_depth * 0.8)
        for a, b in posts:
            if a < x < b:
                d = max(d, post_depth)
        return d

    pts = {}
    for ci, (x, sx) in enumerate(cols):
        for li, (z, sz) in enumerate(levs):
            xe, ze = x + 1e-4 * sx, z + 1e-4 * sz
            pts[(ci, li)] = (x, -depth(xe, ze), z)
    m = K.Mesh()
    for ci in range(len(cols) - 1):
        xa, xb = cols[ci][0], cols[ci + 1][0]
        xm = 0.5 * (xa + xb)
        side = abs(xb - xa) < 1e-9
        for li in range(len(levs) - 1):
            za, zb = levs[li][0], levs[li + 1][0]
            zm = 0.5 * (za + zb)
            step = abs(zb - za) < 1e-9
            if any(x0 - 1e-9 <= xm <= x1 + 1e-9 and z0 - 1e-9 <= zm <= z1 + 1e-9 for x0, x1, z0, z1 in openings) and not (side or step):
                continue
            if (side or step) and any(x0 - 1e-9 <= xm <= x1 + 1e-9 and z0 - 1e-9 <= zm <= z1 + 1e-9 for x0, x1, z0, z1 in openings):
                continue
            a, b = pts[(ci, li)], pts[(ci + 1, li)]
            c, d = pts[(ci + 1, li + 1)], pts[(ci, li + 1)]
            if np.linalg.norm(np.cross(np.subtract(b, a), np.subtract(d, a)) + np.cross(np.subtract(d, c), np.subtract(b, c))) < 1e-9:
                continue
            r = role
            dz = depth(xm + 1e-4 * (1 if side else 0), zm)
            if ph > 0 and zm < ph:
                r = prole or role
            elif any(p0 < xm < p1 for p0, p1 in posts) or (side and any(abs(xm - p0) < 1e-6 or abs(xm - p1) < 1e-6 for p0, p1 in posts)):
                r = post_role
            elif any(a0 < zm < a1 for a0, a1 in rails) or (step and any(abs(zm - a0) < 1e-6 or abs(zm - a1) < 1e-6 for a0, a1 in rails)):
                r = rail_role or post_role
            _ = dz
            m.add([a, b, c, d], [(0, 1, 2, 3)], r, False)
    if cap > 0:
        last = len(levs) - 1
        for ci in range(len(cols) - 1):
            a, b = pts[(ci, last)], pts[(ci + 1, last)]
            if abs(a[0] - b[0]) < 1e-9:
                continue
            m.add([a, b, (b[0], cap, height), (a[0], cap, height)], [(0, 1, 2, 3)], cap_role or role, False)
    return weld(m)


def floor_sheet(x0, y0, x1, y1, z, role, step=2.0, holes=(), border=0.0, border_role=None, up=True):
    """One-sided horizontal sheet (+Z up when up=True, down when False) tessellated every ~step metres."""
    def st(a, b):
        k = max(1, int(round((b - a) / step)))
        s = {a + (b - a) * i / k for i in range(k + 1)}
        if border > 0:
            s.update((a + border, b - border))
        return s
    xs, ys = st(x0, x1), st(y0, y1)
    for hx0, hy0, hx1, hy1 in holes:
        xs.update((hx0, hx1))
        ys.update((hy0, hy1))
    xs, ys = sorted(xs), sorted(ys)
    m = K.Mesh()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
            if any(a <= cx <= c and b <= cy <= d for a, b, c, d in holes):
                continue
            r = role
            if border > 0 and (cx < x0 + border or cx > x1 - border or cy < y0 + border or cy > y1 - border):
                r = border_role or role
            q = [(xs[i], ys[j], z), (xs[i + 1], ys[j], z), (xs[i + 1], ys[j + 1], z), (xs[i], ys[j + 1], z)]
            m.add(q if up else list(reversed(q)), [(0, 1, 2, 3)], r, False)
    return weld(m)


def place(m, x=0.0, y=0.0, z=0.0, yaw_deg=0.0):
    if m is None:
        return None
    if yaw_deg:
        m.rotate_z(math.radians(yaw_deg))
    return m.translate(x, y, z)


# ---------------------------------------------------------------- battlements, stairs
def merlons(x0, x1, y, z, height, depth, role, merlon=0.9, gap=0.7, chamfer=0.06, end_full=True):
    """Crenellation along X at plane y (front at y - depth/2): merlons of `merlon` width separated by crenels."""
    L = x1 - x0
    n = max(1, int(round((L + gap) / (merlon + gap))))
    mw = (L - gap * (n - 1)) / n if end_full else merlon
    m = K.Mesh()
    for i in range(n):
        cx = x0 + mw / 2 + i * (mw + gap)
        m.merge(chamfer_box(cx, y, z, mw, depth, height, role, bevel=0.07))      # 20 tris: weathered bevelled cap
    return m


def stairs_solid(width, run, rise, steps, role, side_role=None, nosing=0.03):
    """Closed straight stair: one stepped-profile prism across X (front edge at y=0, rising toward +Y)."""
    pts = [(0.0, 0.0)]
    for i in range(steps):
        y0 = run * i / steps
        z1 = rise * (i + 1) / steps
        pts.append((y0 - (nosing if i else 0.0), z1 - rise / steps))
        pts.append((y0 - (nosing if i else 0.0), z1))
    pts.append((run, rise))
    pts.append((run, 0.0))
    cleaned = []
    for p in pts:
        if not cleaned or (abs(p[0] - cleaned[-1][0]) > 1e-9 or abs(p[1] - cleaned[-1][1]) > 1e-9):
            cleaned.append(p)
    sec = K.ccw([(y, z) for y, z in cleaned])
    m = K.prism(sec, -width / 2, width / 2, role)
    m.apply(lambda a: a[:, [2, 0, 1]])
    m.orient_outward()
    if side_role:
        for fi, f in enumerate(m.f):
            n = bake.face_normals(np.asarray(m.v), [f])[0]
            if abs(n[0]) > 0.9:
                m.r[fi] = side_role
    return m


# ---------------------------------------------------------------- assembly, sockets, meta
def glb(p):
    """Blender (x, y, z) -> glTF/Godot (x, y up, z south)."""
    return [round(float(p[0]), 4), round(float(p[2]), 4), round(float(-p[1]), 4)]


FACING = {"n": (0.0, 1.0), "s": (0.0, -1.0), "e": (1.0, 0.0), "w": (-1.0, 0.0)}


DOOR_PROUD = 0.06   # doorway-mode buildings: the door socket sits this far in front of the facade (vlg.doorway leaf plane)


def door_out(p, mode):
    """Door socket of a building facing -Y (Blender): in doorway mode it moves DOOR_PROUD in front of the facade so the
    room's vlg.doorway leaf (on the door face point) stands just proud of the uncut wall."""
    return (p[0], p[1] - DOOR_PROUD, p[2]) if mode == "doorway" else tuple(p)


def sock(kind, p_blender, facing, **kw):
    """Snap socket in glTF piece space. facing: n/s/e/w (toward where the mate lies) or up/down."""
    s = {"type": kind, "position": glb(p_blender), "facing": facing}
    s.update(kw)
    return s


def assemble(nodes, meta, anchor, cells=None, lights=None, sockets=(), ground=True, emitter=None, extra=None):
    """Grid pieces keep their anchor at the origin (no re-centring); ground=True drops min z to 0.
    Returns an Asset whose meshes carry the baked lights (opt-in hook) and whose meta records the MEDIEVAL GRID
    anchor, cells, sockets and bbox."""
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for n in nodes:
        a = np.asarray(n.mesh.v)
        lo = np.minimum(lo, a.min(0))
        hi = np.maximum(hi, a.max(0))
    dz = float(-lo[2]) if ground else 0.0
    if abs(dz) > 1e-12:
        for n in nodes:
            n.mesh.translate(0.0, 0.0, dz)
            n.origin = (n.origin[0], n.origin[1], n.origin[2] + dz)
    lights = [dict(L, pos=[L["pos"][0], L["pos"][1], L["pos"][2] + dz]) for L in (lights or [])]
    meta = dict(meta or {})
    meta["bbox_size_m"] = [round(float(x), 4) for x in (hi - lo)]
    meta["medieval_grid"] = {"anchor": anchor, "cells": list(cells) if cells else None, "cell_m": CELL}
    if sockets:
        meta["sockets"] = [dict(s, position=[round(float(s["position"][0]), 4), round(float(s["position"][1]) + dz, 4),
                                             round(float(s["position"][2]), 4)]) for s in sockets]
    if lights:
        meta["bake_lights"] = [{"pos": [round(float(c), 4) for c in L["pos"]], "radius": L.get("radius", 3.0),
                                "strength": L.get("strength", 1.0)} for L in lights]
    if emitter:
        meta["emitter"] = emitter
    if extra:
        meta.update(extra)
    return Asset(nodes, meta)


def centred(nodes, meta, **kw):
    """Free props: footprint-centred, grounded (genutil.finalize semantics) + opt-in bake meshes."""
    from .genutil import finalize
    a = finalize(nodes, meta)
    a.meta["medieval_grid"] = {"anchor": "free", "cells": None, "cell_m": CELL}
    a.meta.update(kw)
    return a


def centred_lit(nodes, meta, lights):
    """centred() for lit free props: the footprint shift finalize applies is applied to the bake lights too."""
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    before = np.min(np.concatenate([np.asarray(n.mesh.v) for n in nodes]), 0)
    a = centred(nodes, meta)
    after = np.min(np.concatenate([np.asarray(n.mesh.v) for n in a.nodes]), 0)
    d = after - before
    a.meta["bake_lights"] = [{"pos": [round(float(L["pos"][i] + d[i]), 4) for i in range(3)], "radius": L.get("radius", 3.0),
                              "strength": L.get("strength", 1.0)} for L in lights]
    return a


def solid(name, *meshes):
    m = merged(*meshes)
    return Node(name, m) if m.f else None


def shell(name, *meshes):
    m = merged(*meshes)
    return Node(name, m, "shell") if m.f else None


# ---------------------------------------------------------------- interior room shells (dungeon-compatible room grid)
SIDES = ("n", "e", "s", "w")
SHEET_YAW = {"n": 0.0, "e": -90.0, "s": 180.0, "w": 90.0}
DOOR_CUT = (1.5, 2.6)          # wall cut a vlg.doorway frame fills (frame outer 1.7 m wide)
DOORWAY = (1.3, 2.4)           # vlg.doorway clear opening (room.gd places it as arch.door)


def side_point(side, hx, hy, s, out=0.0, z=0.0):
    """Point on the inner face of `side` at span coordinate s (n/s from the west end, e/w from the north end)."""
    if side == "n":
        return (s - hx, hy - out, z)
    if side == "s":
        return (hx - s, -hy + out, z)
    if side == "e":
        return (hx - out, hy - s, z)
    return (-hx + out, s - hy, z)


def side_sheet(side, hx, hy, s0, s1, height, role, **kw):
    """wall_sheet on `side` of a room with inner half extents hx, hy covering span [s0, s1] (side_point convention)."""
    L = s1 - s0
    ops = [(a - s0, b - s0, z0, z1) for a, b, z0, z1 in kw.pop("openings", ())]
    posts = [(a - s0, b - s0) for a, b in kw.pop("posts", ())]
    m = wall_sheet(L, height, role, openings=ops, posts=posts, **kw)
    if side == "n":
        m.translate(s0 - hx, hy, 0)
    elif side == "s":
        m.rotate_z(math.pi).translate(hx - s0, -hy, 0)
    elif side == "e":
        m.rotate_z(-math.pi / 2).translate(hx, hy - s0, 0)
    else:
        m.rotate_z(math.pi / 2).translate(-hx, s0 - hy, 0)
    return m


def room_shell(cells_x, cells_y, height, doors=(), windows=(), lights=(), wall_role="wall", post_role="frame",
               post_depth=0.07, plinth=(0.0, 0.0, None), rails=(), rail_role=None, floor_role="floor", border=0.0,
               border_role="step", cap_role=None, window_z=(1.0, 2.1), arch=None, arch_role="trim"):
    """One-sided interior shell on the room grid: walls stand 0.5 m inside the cell block (inner half extents
    hx = 2 cells_x - 0.5), posts (studs / pilasters) on cell boundaries, door cuts DOOR_CUT on cell-edge midpoints
    (`doors` [(side, cell)]), painted window panels on `windows` [(side, cell)], wall sockets everywhere else.
    lights: [(side, cell, kind, z, out, radius, strength)] -> bake pools + typed sockets (hearth / torch).
    arch: optional (thickness, depth) stone surround around each door cut (castle halls).
    Returns (walls mesh, floor mesh, extras mesh (solid), sockets, bake_lights, info)."""
    W, Dd = cells_x * CELL, cells_y * CELL
    hx, hy = W / 2 - WALL_T, Dd / 2 - WALL_T
    span = {"n": 2 * hx, "s": 2 * hx, "e": 2 * hy, "w": 2 * hy}
    ncell = {"n": cells_x, "s": cells_x, "e": cells_y, "w": cells_y}
    doors = {(s_, int(c_)) for s_, c_ in doors}
    wins = {(s_, int(c_)) for s_, c_ in windows}
    lit = {(L[0], int(L[1])): L for L in lights}
    for s_, c_ in doors | wins | set(lit):
        if c_ >= ncell[s_]:
            raise ValueError("socket %s%d outside a %dx%d room" % (s_, c_, cells_x, cells_y))
    if doors & wins or doors & set(lit):
        raise ValueError("a door cell cannot also carry a window / light")
    walls, extras = K.Mesh(), K.Mesh()
    socks, bl = [], []
    for side in SIDES:
        L = span[side]
        ext = WALL_T if side in ("n", "s") else 0.0          # n/s run through the corners to the cell boundary
        nat = (lambda t: t) if side in ("n", "e") else (lambda t, L=L: L - t)
        cut, posts = [], []
        for i in range(ncell[side]):
            mid = nat(4.0 * i + 2.0 - WALL_T)
            p = side_point(side, hx, hy, mid)
            if (side, i) in doors:
                cut.append((mid - DOOR_CUT[0] / 2, mid + DOOR_CUT[0] / 2, 0.0, DOOR_CUT[1]))
                socks.append(sock("door", p, side, cell=i, side=side, width_m=DOORWAY[0], height_m=DOORWAY[1], needs="arch.door"))
                if arch:
                    th, dp = arch
                    fr = arch_frame("arch", DOOR_CUT[0], DOOR_CUT[1], dp, th, arch_role, segs=6, z0=0.0, y0=-dp + 0.12)
                    fr.rotate_z(math.radians(SHEET_YAW[side] + 180.0))
                    extras.merge(fr.translate(p[0], p[1], 0.0))
            else:
                kind = "wall"
                if (side, i) in wins:
                    z0, z1 = window_z
                    pane = K.Mesh()
                    v = [(-0.45, 0.02, z0), (0.45, 0.02, z0), (0.45, 0.02, z1), (-0.45, 0.02, z1),
                         (-0.45, -0.05, z0), (0.45, -0.05, z0), (0.45, -0.05, z1), (-0.45, -0.05, z1)]
                    f = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
                    pane.add(v, f, ["glass"] + [post_role] * 5, False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5)
                    pane.flip().orient_outward()
                    sill = chamfer_box(0.0, -0.06, z0 - 0.1, 1.2, 0.2, 0.1, post_role, bevel=0.03)
                    lin = chamfer_box(0.0, -0.05, z1, 1.2, 0.16, 0.14, post_role, bevel=0.03)
                    for part in (pane, sill, lin):
                        part.rotate_z(math.radians(SHEET_YAW[side]))
                        extras.merge(part.translate(p[0], p[1], 0.0))
                    kind = "window"
                if (side, i) in lit:
                    _, _, lk, lz, lo, lr, ls = lit[(side, i)]
                    bl.append({"pos": list(side_point(side, hx, hy, mid, lo, lz)), "radius": lr, "strength": ls})
                    kind = lk
                socks.append(sock(kind, p, side, cell=i, side=side))
            if 0 < i and post_role:
                b = nat(4.0 * i - WALL_T)
                posts.append((b - 0.18, b + 0.18))
        walls.merge(side_sheet(side, hx, hy, -ext, L + ext, height, wall_role, openings=cut, posts=posts,
                               post_depth=post_depth, post_role=post_role, plinth=plinth, rails=rails, rail_role=rail_role,
                               cap=WALL_T if ext else 0.0, cap_role=cap_role or wall_role))
    floor = floor_sheet(-hx, -hy, hx, hy, 0.0, floor_role, step=2.0, border=border, border_role=border_role)
    info = {"plot_m": [W + 1.0, Dd + 1.0], "interior_m": [2 * hx, 2 * hy],
            "door_positions": {"%s%d" % (s_, c_): 4 * c_ + 2 for s_, c_ in sorted(doors)}}
    return walls, floor, extras, socks, bl, info
