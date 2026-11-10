"""CYBERKIT shared geometry and the CITY GRID (theme-agnostic, Blender space: +Z up, front faces -Y).

The neon-city kits (cytower. cystreet. cysign. cytech. cyroom. cydress. cysky.) interlock on ONE documented grid
(docs/CYBERKIT.md, kits/library/cyberkit-sockets.json):

- 1 cell = 4 m x 4 m; grid pieces snap with their origin on cell centres, cell-block centres or cell edges, yaw in
  90 degree steps; a street is 3 cells wide (2 m sidewalk + 8 m road + 2 m sidewalk), curbs 0.15 m;
- towers and storefronts use a 4 m storey (window rows painted into the facade at that pitch, lit floors as
  emissive window bands); a frontage piece (facade, shopfront) stands on a cell edge and faces the street (-Y);
- interior shells follow the room.gd door convention (0.5 m apron, walls inset 0.5 m, door anchor on cell-edge
  midpoints: door.position = 4 i + 2), like the dungeon grid, so the same room compiler rules apply;
- sockets are listed per piece in meta["sockets"] (glTF piece space: x right, y up, z toward the front).

Signs, neon tubes and screens map into small painted ATLAS textures with normalized UVs (one texture per role, as
every N64 cartridge did): the cell table lives here so the painters (kits/core/texgen_cyber.py) and the generators
agree. Atlas colours are accent SLOTS (a, b, c, d) that each kit pack fills from its own palette roles, so a sign
recolours with the pack, never by a colour baked into the generator.
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K

CELL = 4.0
APRON = 0.5
STOREY = 4.0
CURB = 0.15
ROAD_W = 8.0
WALK_W = 2.0
STREET_W = ROAD_W + 2 * WALK_W          # 12 m = 3 cells
WALL_T = 0.5
ROOM_H = 4.5
DOOR_W, DOOR_H = 2.0, 3.0
CUT_W, CUT_H = 2.8, 3.4
LIFT = 0.025                            # emissive cards stand this far proud of their host face

SIDES = ["n", "e", "s", "w"]
SLOTS = ("a", "b", "c", "d")

# ---------------------------------------------------------------- atlas tables (texels, row 0 = TOP of the image)
# screen (64 px, emissive, crisp): horizontal glyph signs 32x16 in slots a/b/c (two designs each), 4 pictograms 16x16
SCREEN_SIZE = 64
SCREEN = {}
for _i, _s in enumerate("abc"):
    for _k in range(2):
        SCREEN["sign_%s%d" % (_s, _k)] = (32 * _k, 16 * _i, 32, 16, _s)
for _k, (_name, _s) in enumerate((("bowl", "c"), ("cross", "a"), ("joystick", "b"), ("ring", "c"))):
    SCREEN["picto_" + _name] = (16 * _k, 48, 16, 16, _s)
# paper (64 px, emissive, crisp): vertical blade signs 16x64 in slots a/b/c/d
PAPER_SIZE = 64
PAPER = {"blade_%s" % s: (16 * k, 0, 16, 64, s) for k, s in enumerate(SLOTS)}
# book (64 px, emissive, crisp): displays - billboard 64x32 (slots b+a), monitor 32x32 (a), menu/product grid 32x32 (c)
BOOK_SIZE = 64
BOOK = {"billboard": (0, 0, 64, 32, "b"), "monitor": (0, 32, 32, 32, "a"), "menu": (32, 32, 32, 32, "c")}
# light (32 px, emissive): neon tube rows, 8 texels each: slot a, b, c, d (profile edge -> body -> white core)
LIGHT_SIZE = 32
LIGHT = {s: (0, 8 * k, 32, 8, s) for k, s in enumerate(SLOTS)}
# fire (64 px, emissive): window-light rows, 4 rows x 8 windows (8 x 16 texels per window), 16 m of facade per width
FIRE_SIZE = 64
FIRE_ROWS = 4
FIRE_SPAN_M = 16.0
# fabric (64 px, baked): four hanging banners 16x64 (slots a/b/c/d cloth)
FABRIC_SIZE = 64
FABRIC = {"banner_%s" % s: (16 * k, 0, 16, 64, s) for k, s in enumerate(SLOTS)}

ATLASES = {"screen": (SCREEN, SCREEN_SIZE), "paper": (PAPER, PAPER_SIZE), "book": (BOOK, BOOK_SIZE),
           "light": (LIGHT, LIGHT_SIZE), "fabric": (FABRIC, FABRIC_SIZE)}


def cell_uv(atlas, name, inset=0.6):
    """Atlas cell -> (u0, v0, u1, v1) in Blender UV convention (v up), inset by `inset` texels so the soft filter
    never reaches the neighbouring cell."""
    table, size = ATLASES[atlas]
    x, y, w, h = table[name][:4]
    u0, u1 = (x + inset) / size, (x + w - inset) / size
    v1, v0 = 1.0 - (y + inset) / size, 1.0 - (y + h - inset) / size
    return (u0, v0, u1, v1)


def quad_uv(rect):
    u0, v0, u1, v1 = rect
    return ("n", [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


# ---------------------------------------------------------------- sockets / meta (glTF piece space)
def gl(p):
    """Blender (x, y, z) -> glTF (x, z, -y), rounded (socket data)."""
    return [round(float(p[0]), 4), round(float(p[2]), 4), round(float(-p[1]), 4)]


def sock(kind, pos, facing, **kw):
    """facing: outward direction in piece space, one of n e s w up down (n = glTF -Z, s = glTF +Z / the front)."""
    d = {"type": kind, "position": gl(pos), "facing": facing}
    d.update(kw)
    return d


def grid_meta(anchor, cells=None, sockets=(), **kw):
    g: dict = {"cell_m": CELL, "storey_m": STOREY, "street_m": STREET_W, "anchor": anchor}
    if cells is not None:
        g["cells"] = list(cells)
    m: dict = {"city_grid": g}
    m["sockets"] = list(sockets)
    m.update(kw)
    return m


def light(pos, radius=4.0, strength=1.0):
    """Baked point-light pool (pack light_rig.point_bake): asset space, +Z up."""
    return {"pos": [round(float(c), 4) for c in pos], "radius": radius, "strength": strength}


# ---------------------------------------------------------------- 2D outlines
def cham_rect(w, d, c=0.0):
    """Rectangle w x d centred at the origin with 45 degree corner chamfers c (8 points, CCW); c = 0 -> 4 points."""
    c = max(0.0, min(c, 0.45 * min(w, d)))
    if c < 1e-4:
        return [(w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2), (-w / 2, -d / 2)]
    x, y = w / 2, d / 2
    return [(x - c, -y), (x, -y + c), (x, y - c), (x - c, y), (-x + c, y), (-x, y - c), (-x, -y + c), (-x + c, -y)]


def ngon(r, k, start=0.0, rx=None, ry=None):
    return K.circle2d(r, k, start, rx, ry)


def offset_outline(pts, d):
    """Offset a CCW outline outward by d (mitred)."""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = np.array(pts[i - 1]), np.array(pts[i]), np.array(pts[(i + 1) % n])
        e0, e1 = p1 - p0, p2 - p1
        n0 = np.array([e0[1], -e0[0]]) / max(np.linalg.norm(e0), 1e-9)
        n1 = np.array([e1[1], -e1[0]]) / max(np.linalg.norm(e1), 1e-9)
        m = n0 + n1
        lm = np.linalg.norm(m)
        if lm < 1e-9:
            out.append(tuple(p1 + n0 * d))
            continue
        m /= lm
        cosa = max(0.25, float(np.dot(m, n0)))
        out.append(tuple(p1 + m * d / cosa))
    return out


def outline_len(pts):
    return sum(math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0], pts[(i + 1) % len(pts)][1] - pts[i][1]) for i in range(len(pts)))


# ---------------------------------------------------------------- closed solids
def prism(outline, z0, z1, role, top=None, bottom=None, cx=0.0, cy=0.0, smooth=False):
    pts = [(x + cx, y + cy) for x, y in outline]
    return K.prism(pts, z0, z1, role, role_top=top, role_bottom=bottom, smooth_sides=smooth)


def cham_prism(cx, cy, z0, z1, w, d, c, role, top=None, bottom=None):
    return prism(cham_rect(w, d, c), z0, z1, role, top, bottom, cx, cy)


def rings_loft(rings2d, zs, role, cx=0.0, cy=0.0, roles=None, cap_roles=None, smooth=False):
    """Loft equal-length 2D rings at heights zs (closed with caps): tapers, setbacks, bulges, crowns."""
    rings = [[(x + cx, y + cy, z) for x, y in r] for r, z in zip(rings2d, zs)]
    return K.loft(rings, role, smooth=smooth, roles=roles, cap_roles=cap_roles)


def taper(cx, cy, z0, z1, w0, d0, w1, d1, c0, c1, role, top=None, bottom=None, roles=None):
    """Tapered chamfered block (always 8-sided rings so the loft stays consistent)."""
    a = cham_rect(w0, d0, max(c0, 0.02))
    b = cham_rect(w1, d1, max(c1, 0.02))
    return rings_loft([a, b], [z0, z1], role, cx, cy, roles=roles, cap_roles=(bottom or role, top or role))


def slab(cx, cy, z0, sx, sy, sz, role, c=0.05, top=None):
    """Cheap chamfered block (8-sided prism, 28 tris): slabs, ledges, boxes on a budget."""
    return cham_prism(cx, cy, z0, z0 + sz, sx, sy, c, role, top)


def bevel_box(cx, cy, z0, sx, sy, sz, role, bevel=0.05, top=None):
    """Never a raw cuboid: chamfered vertical edges and a bevelled top rim (shared dungeon helper)."""
    return D.bevel_box(cx, cy, z0, sx, sy, sz, role, bevel=bevel, top_role=top)


def cyl(cx, cy, z0, r, h, segs, role, cap=None, smooth=True):
    return K.cylinder(cx, cy, z0, r, h, segs, role, smooth, cap_roles=(cap or role, cap or role))


def frustum(cx, cy, z0, z1, r0, r1, segs, role, cap=None, smooth=True):
    return K.lathe([(r0, 0.0), (r1, z1 - z0)], segs, role, smooth, cap_roles=(cap or role, cap or role)).translate(cx, cy, z0)


def lathe_at(cx, cy, z0, profile, segs, role, smooth=True, roles=None, rx=1.0, ry=1.0):
    return K.lathe(profile, segs, role, smooth, roles=roles, rx=rx, ry=ry).translate(cx, cy, z0)


def tube(points, r, sides, role, smooth=True):
    return K.tube([tuple(float(c) for c in p) for p in points], r, sides, role, smooth)


def ring(cx, cy, z, R, r, segs, sides, role, smooth=True):
    return K.torus(R, r, segs, sides, role, smooth).translate(cx, cy, z)


def rod(p0, p1, r, sides, role, smooth=True):
    """Closed straight tube between two points (cables, poles, antenna members)."""
    return K.tube([tuple(float(c) for c in p0), tuple(float(c) for c in p1)], r, sides, role, smooth)


def catenary(p0, p1, sag, n=6):
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    out = []
    for i in range(n + 1):
        t = i / n
        p = p0 + (p1 - p0) * t
        p[2] -= sag * 4 * t * (1 - t)
        out.append(tuple(p))
    return out


def wedge(cx, cy, z0, w, d, h_front, h_back, role, c=0.04, top=None):
    """Block with a sloped top (front height -> back height): wedge tower tops, ramps, sloped awnings."""
    out = cham_rect(w, d, c)
    pts = [(x + cx, y + cy) for x, y in out]
    m = K.Mesh()
    n = len(pts)
    top_z = [z0 + h_front + (h_back - h_front) * ((y - cy) / d + 0.5) for _, y in pts]
    verts = [(x, y, z0) for x, y in pts] + [(x, y, tz) for (x, y), tz in zip(pts, top_z)]
    faces, roles = [], []
    faces.append(tuple(reversed(range(n))))
    roles.append(role)
    faces.append(tuple(range(n, 2 * n)))
    roles.append(top or role)
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
        roles.append(role)
    m.add(verts, faces, roles, False)
    return m.orient_outward()


# ---------------------------------------------------------------- open surfaces (shells / cards)
def quad(a, b, c, d, role, uv=None, smooth=False):
    """One quad a-b-c-d (CCW seen from its front)."""
    return K.Mesh().add([a, b, c, d], [(0, 1, 2, 3)], role, smooth, [uv] if uv else None)


def face_card(cx, cy, z0, w, h, role, uv_rect=None, facing="-y", lift=0.0):
    """Vertical card centred on (cx, cy) standing from z0, facing -Y (default) or +Y / -X / +X, with normalized
    atlas UVs (uv_rect) or metric UVs."""
    x0, x1, z1 = -w / 2, w / 2, z0 + h
    uv = quad_uv(uv_rect) if uv_rect else ("m", [(0, z0), (w, z0), (w, z1), (0, z1)])
    if facing == "-y":
        pts = [(cx + x0, cy - lift, z0), (cx + x1, cy - lift, z0), (cx + x1, cy - lift, z1), (cx + x0, cy - lift, z1)]
    elif facing == "+y":
        pts = [(cx + x1, cy + lift, z0), (cx + x0, cy + lift, z0), (cx + x0, cy + lift, z1), (cx + x1, cy + lift, z1)]
    elif facing == "+x":
        pts = [(cx + lift, cy + x0, z0), (cx + lift, cy + x1, z0), (cx + lift, cy + x1, z1), (cx + lift, cy + x0, z1)]
    else:
        pts = [(cx - lift, cy + x1, z0), (cx - lift, cy + x0, z0), (cx - lift, cy + x0, z1), (cx - lift, cy + x1, z1)]
    return quad(pts[0], pts[1], pts[2], pts[3], role, uv)


def flat_card(cx, cy, z, w, d, role, uv_rect=None, yaw_deg=0.0, down=False):
    """Horizontal card (decals, pools, puddles) facing up (or down)."""
    pts = [(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)
    P = [(cx + x * ca - y * sa, cy + x * sa + y * ca, z) for x, y in pts]
    uv = quad_uv(uv_rect) if uv_rect else ("m", [(x, y) for x, y in pts])
    m = quad(P[0], P[1], P[2], P[3], role, uv)
    return m.flip() if down else m


def strip(p0, p1, width, role, normal=(0.0, -1.0, 0.0), uv_rect=None):
    """Thin flat ribbon card from p0 to p1, `width` wide, facing `normal` (emissive neon strips, edge lights)."""
    p0, p1, nrm = np.asarray(p0, float), np.asarray(p1, float), np.asarray(normal, float)
    t = p1 - p0
    side = np.cross(nrm, t)
    side /= max(np.linalg.norm(side), 1e-9)
    h = side * width / 2
    a, b, c, d = p0 - h, p1 - h, p1 + h, p0 + h
    uv = quad_uv(uv_rect) if uv_rect else None
    m = quad(tuple(a), tuple(b), tuple(c), tuple(d), role, uv)
    n = np.cross(b - a, d - a)
    if np.dot(n, nrm) < 0:
        m.flip()
    return m


def neon_tube(points, r, role, slot_rect, sides=4, closed=False):
    """Closed thin neon tube along a polyline (or a closed loop) with the light-atlas row of its slot mapped across
    every side face (core in the middle of the row): reads as a painted N64 neon tube from any side."""
    pts = [np.asarray(p, dtype=np.float64) for p in points]
    n = len(pts)
    if closed:
        # Newell normal of the loop: a fixed binormal axis keeps every ring consistent (no twist, no seam)
        nrm = np.zeros(3)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            nrm += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
        nrm /= max(np.linalg.norm(nrm), 1e-12)
        T = [pts[(i + 1) % n] - pts[i - 1] for i in range(n)]
        T = [t / max(np.linalg.norm(t), 1e-12) for t in T]
        N = [np.cross(t, nrm) for t in T]
        N = [v / max(np.linalg.norm(v), 1e-12) for v in N]
        B = [np.cross(t, v) for t, v in zip(T, N)]
    else:
        T, N, B = K.frames_along([tuple(p) for p in pts])
    u0, v0, u1, v1 = slot_rect
    vc = 0.5 * (v0 + v1)
    rings = []
    for i, p in enumerate(pts):
        rings.append([tuple(p + N[i] * r * math.cos(K.TAU * (k + 0.5) / sides) + B[i] * r * math.sin(K.TAU * (k + 0.5) / sides))
                      for k in range(sides)])
    verts = [q for rr in rings for q in rr]
    faces, uvs = [], []
    nseg = n if closed else n - 1
    for j in range(nseg):
        j2 = (j + 1) % n
        for k in range(sides):
            a = j * sides + k
            b = j * sides + (k + 1) % sides
            faces.append((a, b, j2 * sides + (k + 1) % sides, j2 * sides + k))
            # each side face spans the full row height: edge -> core -> edge across the face
            uvs.append(("n", [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]))
    if not closed:
        last = (n - 1) * sides
        faces.append(tuple(reversed(range(sides))))
        uvs.append(("n", [(u0, vc)] * sides))
        faces.append(tuple(range(last, last + sides)))
        uvs.append(("n", [(u1, vc)] * sides))
    return K.Mesh().add(verts, faces, role, False, uvs).orient_outward()


def window_bands(outline, cx, cy, floors, rs, lit, role="fire", min_len=1.2, rows=FIRE_ROWS, span=FIRE_SPAN_M,
                 z_lo=0.85, z_hi=3.35, lift=LIFT):
    """Emissive window-light bands (cards) on the side faces of a closed outline for each lit floor base z in
    `floors`: one quad per face wide enough to carry windows, a random window-row variant and u offset per band
    (whole 2 m bays), so lit floors read as strips of warm/cool panes over the painted dark facade."""
    m = K.Mesh()
    n = len(outline)
    pts = [(x + cx, y + cy) for x, y in outline]
    for z in floors:
        if rs.random() > lit:
            continue
        row = rs.randrange(rows)
        off = 2.0 * rs.randrange(int(span / 2))
        acc = 0.0
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            L = math.hypot(x1 - x0, y1 - y0)
            if L >= min_len:
                nx, ny = (y1 - y0) / L, -(x1 - x0) / L      # outward for a CCW outline
                a = (x0 + nx * lift, y0 + ny * lift)
                b = (x1 + nx * lift, y1 + ny * lift)
                v_top = 1.0 - row / rows
                v_bot = 1.0 - (row + 1) / rows
                inset = 0.6 / FIRE_SIZE
                u0 = (acc + off) / span
                u1 = (acc + off + L) / span
                uv = ("n", [(u0, v_bot + inset), (u1, v_bot + inset), (u1, v_top - inset), (u0, v_top - inset)])
                m.merge(quad((a[0], a[1], z + z_lo), (b[0], b[1], z + z_lo), (b[0], b[1], z + z_hi),
                             (a[0], a[1], z + z_hi), role, uv))
            acc += L
    return m


# ---------------------------------------------------------------- relief wall sheets (interior shells, alleys)
# (z, inset, role) bottom -> top, the dkit.wall_sheet profile contract: a dark skirting plinth, the panel body, a
# cove for the light strip and a slim cornice. Lean on purpose (shell budget).
PROFILE = (
    (0.0, 0.08, "trim"), (0.35, 0.08, "trim"), (0.35, 0.0, "stone"),
    (ROOM_H - 0.5, 0.0, "stone"), (ROOM_H - 0.5, 0.12, "trim"), (ROOM_H - 0.2, 0.18, "trim"), (ROOM_H, 0.18, "trim"),
)


def profile(body="stone", plinth="trim", cornice="trim", height=ROOM_H):
    return ((0.0, 0.08, plinth), (0.35, 0.08, plinth), (0.35, 0.0, body), (height - 0.5, 0.0, body),
            (height - 0.5, 0.12, cornice), (height - 0.2, 0.18, cornice), (height, 0.18, cornice))


def wall_sheet(length, prof=PROFILE, **kw):
    return D.wall_sheet(length, profile=prof, **kw)


def weld(m, tol=1e-5):
    return D.weld_mesh(m, tol)


def grid_floor(xs, ys, inside, z=0.0, role="floor", flip=False):
    """One-sided floor (or ceiling if flip) on station lists xs, ys; quads whose centre passes inside(cx, cy).
    role may be a callable (cx, cy) -> role."""
    m = K.Mesh()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
            if not inside(cx, cy):
                continue
            q = [(xs[i], ys[j], z), (xs[i + 1], ys[j], z), (xs[i + 1], ys[j + 1], z), (xs[i], ys[j + 1], z)]
            m.add(q, [(0, 1, 2, 3)], role if isinstance(role, str) else role(cx, cy), False)
    m = weld(m)
    return m.flip() if flip else m


def stations(a, b, step, extra=()):
    k = max(1, int(round((b - a) / step)))
    s = {round(a + (b - a) * i / k, 6) for i in range(k + 1)}
    s.update(round(e, 6) for e in extra if a - 1e-9 <= e <= b + 1e-9)
    return sorted(s)


def place(m, x=0.0, y=0.0, z=0.0, yaw_deg=0.0):
    if yaw_deg:
        m.rotate_z(math.radians(yaw_deg))
    return m.translate(x, y, z)


def rot_xy(p, yaw_deg):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def merge(*meshes):
    out = K.Mesh()
    for m in meshes:
        if m is not None:
            out.merge(m)
    return out


def stair_flight(width, run, rise, n, role="step", side_role=None, cx=0.0, cy=0.0, z0=0.0, descend=False):
    """One closed sawtooth solid for a whole flight (a stepped profile in the y-z plane extruded across x): ~8 tris
    per step instead of a box per tread. Climbs `rise` along +y over `run` (descend=True: drops `rise` along +y,
    from z0 down to z0 - rise), centred on cx, cy."""
    th, tr = rise / n, run / n
    prof = [(-run / 2, 0.0)]
    for k in range(n):
        y = -run / 2 + k * tr
        prof += [(y, (k + 1) * th), (y + tr, (k + 1) * th)]
    prof.append((run / 2, 0.0))
    m = K.prism(prof, -width / 2, width / 2, role, role_top=side_role or role, role_bottom=side_role or role)
    m.apply(lambda a: a[:, [2, 0, 1]])
    if descend:
        m.rotate_z(math.pi)
        m.translate(0, 0, -rise)
    return m.translate(cx, cy, z0).orient_outward()


def open_box(x0, x1, y0, y1, z0, z1, roles, drop=("top",)):
    """Inward-facing room box as a shell (consistent winding across its corners): faces bottom, top, n (+y), s (-y),
    e (+x), w (-x); `drop` removes faces (open tops, entries). roles: role or {face: role}."""
    P = {"bottom": [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],
         "top": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
         "s": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
         "n": [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
         "e": [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
         "w": [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]}
    m = K.Mesh()
    for k, q in P.items():
        if k in drop:
            continue
        role = roles.get(k, "stone") if isinstance(roles, dict) else roles
        # outward-facing quads as written; the box is flipped below so every face looks inward
        m.add(q, [(0, 1, 2, 3)], role, False, [("m", _face_uv(q))])
    return weld(m).flip()


def _face_uv(q):
    a = np.asarray(q, dtype=np.float64)
    n = np.cross(a[1] - a[0], a[3] - a[0])
    ax = int(np.argmax(np.abs(n)))
    if ax == 2:
        return [(p[0], p[1]) for p in q]
    if ax == 1:
        return [(p[0], p[2]) for p in q]
    return [(p[1], p[2]) for p in q]


def finish(nodes, meta=None, cx=True, cy=True, ground=True):
    """genutil.finalize, but the sockets in meta (glTF piece space) move with the geometry: footprint centred on
    the axes asked for, min z = 0 if `ground`."""
    from .genutil import finalize
    live = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for n in live:
        a = np.asarray(n.mesh.v)
        lo = np.minimum(lo, a.min(0))
        hi = np.maximum(hi, a.max(0))
    d = np.zeros(3)
    if cx:
        d[0] = -(lo[0] + hi[0]) / 2
    if cy:
        d[1] = -(lo[1] + hi[1]) / 2
    if ground:
        d[2] = -lo[2]
    for n in live:
        n.mesh.translate(*d)
        n.origin = tuple(np.asarray(n.origin) + d)
    meta = dict(meta or {})
    g = gl(d)
    for s in meta.get("sockets", []):
        s["position"] = [round(s["position"][i] + g[i], 4) for i in range(3)]
    for L_ in meta.get("bake_lights", []):
        L_["pos"] = [round(L_["pos"][i] + float(d[i]), 4) for i in range(3)]
    return finalize(live, meta, center_x=False, center_y=False, ground=False)


def sockets_doc():
    return {"cell_m": CELL, "storey_m": STOREY, "street_m": STREET_W, "road_m": ROAD_W, "sidewalk_m": WALK_W,
            "curb_m": CURB, "wall_inset_m": WALL_T, "room_storey_m": ROOM_H, "doorway_m": [DOOR_W, DOOR_H]}
