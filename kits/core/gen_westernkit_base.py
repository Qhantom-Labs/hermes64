"""WESTERNKIT shared geometry: the FRONTIER GRID and frontier building parts (theme-agnostic; Blender space +Z up,
front faces -Y = glTF +Z).

FRONTIER GRID (docs/WESTERNKIT.md, kits/library/westernkit-sockets.json):

- 1 cell = 4 m x 4 m (the same module as the dungeon grid, so kits can share a room plot); a room plot is cells x 4 m
  plus a 0.5 m apron each side;
- LOT LINE pieces (buildings, false fronts, boardwalks, fences, porches) have their origin on a cell boundary line at
  floor level, in the middle of their frontage; buildings stand BEHIND the line (glTF -Z), boardwalks and porches in
  FRONT of it (glTF +Z, toward the street); a frontage is 1-3 cells;
- DOOR sockets sit on the room.gd door anchor: 0.4 m in from the plot edge = 0.1 m behind the cell boundary (lot line),
  at a cell-edge midpoint; the doorway frame (`wtown.doorway`, bound as `arch.door`) is placed there by the runtime;
- interior shells (`wtown.room`) are one-sided, facing in, walls WALL_T = 0.12 m inside the block boundary (flush with
  the doorway frame); ceilings, galleries and back bars are separate pieces;
- door sockets of lot-line buildings may sit every 2 m along the frontage (cell boundaries and cell-edge midpoints);
  interior shells cut doors on cell-edge midpoints;
- mine tunnels run on cell centres with 3 m clear width (walls 0.5 m in from the cell edges), track pieces join on
  cell-edge midpoints (`track` sockets), boardwalk modules join end to end (`walk` sockets);
- yaw in 90 degree steps for grid pieces; free props turn freely.

Closed solids are built from separate closed islands (body, roof, false front, trim, windows): islands never share a
vertex, so the kit validators see clean manifold parts. Big forms are chamfered or tapered (never plain cuboids).
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K

CELL = 4.0
APRON = 0.5
WALL_T = 0.12              # interior shell wall: inner face 0.12 m inside the block boundary (flush with the door frame)
STOREY = 3.0
DOOR_W, DOOR_H = 2.4, 3.0  # clear opening of the timber doorway frame (wtown.doorway = arch.door)
FRAME_BACK, FRAME_FRONT = 0.08, 0.27   # doorway frame depth behind / in front of the door anchor
ANCHOR_BACK = 0.1          # door anchor behind the lot line (room.gd: 0.4 m in from the plot edge)
WALK_D, WALK_H = 2.0, 0.3  # boardwalk depth and deck height
RAIL_GAUGE = 1.1
MINE_GAUGE = 0.6
TUNNEL_W, TUNNEL_H = 3.0, 3.0
EPS = 0.004                # gap that keeps touching islands from welding into one


def gl(p):
    """Blender (x, y, z) -> glTF (x, z, -y), rounded, for socket data."""
    return [round(float(p[0]), 4), round(float(p[2]), 4), round(float(-p[1]), 4)]


def sock(kind, pos, facing, **kw):
    """facing: outward direction in piece space: n e s w up down (s = glTF +Z = the piece front)."""
    d = {"type": kind, "position": gl(pos), "facing": facing}
    d.update(kw)
    return d


def grid_meta(anchor, cells=None, sockets=(), **kw):
    m: dict = {"frontier_grid": {"cell_m": CELL, "apron_m": APRON, "anchor": anchor}}
    if cells is not None:
        m["frontier_grid"]["cells"] = list(cells)
    m["sockets"] = list(sockets)
    m.update(kw)
    return m


def light(pos, radius=3.5, strength=1.0):
    return {"pos": [round(float(c), 4) for c in pos], "radius": radius, "strength": strength}


weld = D.weld_mesh
bevel_box = D.bevel_box
taper_loft = D.taper_loft
rock_blob = D.rock_blob


# ---------------------------------------------------------------- primitive solids
def slab(outline_xz, y0, y1, role, front=None, back=None):
    """Closed slab: a 2D outline in the XZ plane (x right, z up) extruded through y0..y1 (front face at y0 faces -Y).
    Sides take `role`, the front face `front`, the back face `back`."""
    m = K.prism(outline_xz, -y1, -y0, role, role_top=front or role, role_bottom=back or role)
    return m.rotate_x(math.pi / 2)


def xbox(x0, x1, y0, y1, z0, z1, role):
    return K.box((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), role)


def chamfer(cx, cy, z0, z1, w, d, ch, role, top=None, bottom=None):
    """Box with chamfered vertical edges (octagonal plan): 28 tris, never a cuboid."""
    o = K.rounded_rect2d(w, d, max(0.01, min(ch, 0.45 * min(w, d))), 1)
    return K.prism([(cx + x, cy + y) for x, y in o], z0, z1, role, role_top=top or role, role_bottom=bottom or role)


def post(x, y, z0, z1, r, role, sides=6, taper=0.85, start=None):
    """Tapered round/hex post (flat caps)."""
    st = math.pi / sides if start is None else start
    return K.lathe([(r, z0), (r * taper, z1)], sides, role, smooth=sides > 5, start=st).translate(x, y, 0)


def sq_post(x, y, z0, z1, s, role, taper=0.9):
    """Hewn timber post: six-sided, slightly tapered (20 tris; never an axis box)."""
    r = s * 0.62
    return K.lathe([(r, z0), (r * taper, z1)], 6, role, smooth=False, start=math.pi / 6).translate(x, y, 0)


def spindle(p0, p1, s, role):
    """Thin square spindle turned 45 degrees about its axis (diamond section, 12 tris): balusters, bars, rungs."""
    return beam(p0, p1, s, s, role, roll=45.0)


def beam(p0, p1, w, h, role, up=(0.0, 0.0, 1.0), roll=0.0):
    """Closed box beam between two points (width w across, height h along `up`); `roll` turns the section about the
    beam axis (45 = a ridged diamond rail)."""
    a = np.asarray(p0, dtype=np.float64)
    b = np.asarray(p1, dtype=np.float64)
    t = b - a
    L = float(np.linalg.norm(t))
    t = t / max(L, 1e-9)
    u = np.asarray(up, dtype=np.float64)
    s = np.cross(t, u)
    if np.linalg.norm(s) < 1e-6:
        s = np.cross(t, np.array([1.0, 0.0, 0.0]))
    s = s / np.linalg.norm(s)
    u2 = np.cross(s, t)
    if roll:
        c_, s_ = math.cos(math.radians(roll)), math.sin(math.radians(roll))
        s, u2 = s * c_ + u2 * s_, u2 * c_ - s * s_
    pts = []
    for e in (a, b):
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            pts.append(tuple(e + s * sx * w / 2 + u2 * sz * h / 2))
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return K.Mesh().add(pts, f, role, False).orient_outward()


def board(x0, x1, y0, y1, z0, z1, role, ch=0.025, top=None):
    """Timber board / casing: a box whose two front (-Y) vertical edges are chamfered (hexagonal plan, 20 tris)."""
    c = max(0.004, min(ch, 0.4 * (x1 - x0), 0.4 * (y1 - y0)))
    o = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1), (x0, y1), (x0, y0 + c)]
    return K.prism(o, z0, z1, role, role_top=top or role, role_bottom=role)


def section_beam(p0, p1, section, role, up=(0.0, 0.0, 1.0), cap_role=None):
    """Closed beam from p0 to p1 with a 2D section [(s, u)] (CCW) in the plane normal to the axis (s across, u along
    `up`). Used for chamfered timbers (octagonal section) and shaped rails."""
    a = np.asarray(p0, dtype=np.float64)
    b = np.asarray(p1, dtype=np.float64)
    t = b - a
    t = t / max(float(np.linalg.norm(t)), 1e-9)
    u = np.asarray(up, dtype=np.float64)
    s = np.cross(t, u)
    if np.linalg.norm(s) < 1e-6:
        s = np.cross(t, np.array([1.0, 0.0, 0.0]))
    s = s / np.linalg.norm(s)
    u2 = np.cross(s, t)
    sec = K.ccw(list(section))
    n = len(sec)
    pts = [tuple(e + s * px + u2 * pz) for e in (a, b) for px, pz in sec]
    m = K.Mesh()
    for i in range(n):
        j = (i + 1) % n
        m.add([pts[i], pts[j], pts[n + j], pts[n + i]], [(0, 1, 2, 3)], role, False)
    cr = cap_role or role
    m.add([pts[i] for i in reversed(range(n))], [tuple(range(n))], cr, False)
    m.add([pts[n + i] for i in range(n)], [tuple(range(n))], cr, False)
    return m.orient_outward()


def timber(p0, p1, w, h, role, ch=None, up=(0.0, 0.0, 1.0)):
    """Hewn timber: a beam with chamfered edges (octagonal section, 28 tris)."""
    c = min(w, h) * 0.22 if ch is None else ch
    hw, hh = w / 2, h / 2
    sec = [(-hw + c, -hh), (hw - c, -hh), (hw, -hh + c), (hw, hh - c), (hw - c, hh), (-hw + c, hh), (-hw, hh - c), (-hw, -hh + c)]
    return section_beam(p0, p1, sec, role, up)


def panel(cx, y, cz, w, h, d, role, edge_role=None):
    """Closed thin slab standing on a wall face (front face at y, facing -Y, normalized UVs for one painted motif)."""
    x0, x1, y0, y1, z0, z1 = cx - w / 2, cx + w / 2, y, y + d, cz - h / 2, cz + h / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 5, 4), (0, 3, 2, 1), (4, 5, 6, 7), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    er = edge_role or role
    uvs = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5
    return K.Mesh().add(v, f, [role, er, er, er, er, er], False, uvs)


# ---------------------------------------------------------------- building forms
def gable_body(w, d, h_eave, h_ridge, role="wall", gable_role=None, y_front=0.0, z0=0.0, ch=0.0):
    """House body: pentagon (gable end) extruded from y_front back by d; the gable faces the front. Front/back faces
    take gable_role (default role). ch > 0 chamfers the vertical corners (corner boards)."""
    if ch > 0:
        hw = w / 2
        sec = [(-hw + ch, z0), (hw - ch, z0), (hw, z0 + ch * 0.0), (hw, h_eave), (0.0, h_ridge), (-hw, h_eave), (-hw, z0)]
        sec = [(-hw, z0), (hw, z0), (hw, h_eave), (0.0, h_ridge), (-hw, h_eave)]
    else:
        sec = [(-w / 2, z0), (w / 2, z0), (w / 2, h_eave), (0.0, h_ridge), (-w / 2, h_eave)]
    return slab(sec, y_front, y_front + d, role, front=gable_role or role, back=gable_role or role)


def flat_body(w, d, h, role="wall", y_front=0.0, z0=0.0, ch=0.12, top="roof"):
    """Flat-roofed body with chamfered corner boards (octagonal plan), front face on y_front."""
    return chamfer(0.0, y_front + d / 2, z0, z0 + h, w, d, ch, role, top=top)


def gable_roof(w, d, h_eave, h_ridge, role="roof", over_side=0.35, over_front=0.25, over_back=0.25, t=0.14, y_front=0.0,
               end_role=None, sag=0.0):
    """Closed roof volume over a gable body: a chevron section (slopes + soffit) extruded along Y. `sag` lowers the
    ridge middle slightly (an old roof) by splitting the extrusion into two halves."""
    hw = w / 2 + over_side
    slope = (h_ridge - h_eave) / (w / 2)
    ze = h_eave - over_side * slope
    sec = [(-hw, ze - t), (-hw, ze), (0.0, h_ridge + t * 0.3), (hw, ze), (hw, ze - t), (0.0, h_ridge - t * 1.2)]
    m = slab(sec, y_front - over_front, y_front + d + over_back, role, front=end_role or "trim", back=end_role or "trim")
    if sag:
        y0, y1 = y_front - over_front, y_front + d + over_back
        ym = 0.5 * (y0 + y1)
        A = np.asarray(m.v)
        k = 1.0 - ((A[:, 1] - ym) / max(1e-6, (y1 - y0) / 2)) ** 2
        A[:, 2] -= sag * np.clip(k, 0, 1) * (A[:, 2] > h_eave)
        m.v = [tuple(p) for p in A.tolist()]
    return m


def shed_roof(x0, x1, y0, y1, z_front, z_back, role="roof", t=0.12, end_role="trim"):
    """Closed sloped slab (porch / awning / lean-to roof): front edge at y0 height z_front, back at y1 height z_back."""
    sec = [(y0, z_front - t), (y1, z_back - t), (y1, z_back), (y0, z_front)]
    m = K.prism(sec, x0, x1, role, role_top=end_role, role_bottom=end_role)
    # prism built in (y, z) with extrusion along x: rotate so outline-x -> world y, outline-y -> world z, extrude -> x
    A = np.asarray(m.v)
    B = np.stack([A[:, 2], A[:, 0], A[:, 1]], axis=1)
    m.v = [tuple(p) for p in B.tolist()]
    return m.orient_outward()


def false_front_outline(w, h_wall, h_top, shape):
    """Facade outline (x, z) for a false front: the wall rises to h_wall at the sides and to h_top at the centre with a
    shaped parapet. Shapes: square, stepped, arched, gabled, pediment, tall (square with a raised centre block)."""
    hw = w / 2
    if shape == "square":
        return [(-hw, 0.0), (hw, 0.0), (hw, h_top), (-hw, h_top)]
    if shape == "stepped":
        s1, s2 = h_wall + (h_top - h_wall) * 0.45, h_top
        return [(-hw, 0.0), (hw, 0.0), (hw, h_wall), (hw * 0.62, h_wall), (hw * 0.62, s1), (hw * 0.3, s1), (hw * 0.3, s2),
                (-hw * 0.3, s2), (-hw * 0.3, s1), (-hw * 0.62, s1), (-hw * 0.62, h_wall), (-hw, h_wall)]
    if shape == "arched":
        pts = [(-hw, 0.0), (hw, 0.0), (hw, h_wall)]
        k = 8
        for i in range(1, k):
            a = math.pi * i / k
            pts.append((hw * 0.92 * math.cos(a), h_wall + (h_top - h_wall) * math.sin(a)))
        pts.append((-hw, h_wall))
        return pts
    if shape == "gabled":
        return [(-hw, 0.0), (hw, 0.0), (hw, h_wall), (0.0, h_top), (-hw, h_wall)]
    if shape == "pediment":
        return [(-hw, 0.0), (hw, 0.0), (hw, h_wall), (hw * 0.55, h_wall), (0.0, h_top), (-hw * 0.55, h_wall), (-hw, h_wall)]
    if shape == "tall":
        return [(-hw, 0.0), (hw, 0.0), (hw, h_wall), (hw * 0.45, h_wall), (hw * 0.45, h_top), (-hw * 0.45, h_top),
                (-hw * 0.45, h_wall), (-hw, h_wall)]
    raise ValueError("unknown false-front shape %r" % shape)


def cornice(x0, x1, z, y_face, depth=0.28, h=0.22, role="trim", brackets=0, bracket_role="trim"):
    """Projecting cornice board along the top of a facade (front face at y_face - depth), optional brackets below."""
    m = K.Mesh()
    sec = [(y_face - depth, z - h * 0.35), (y_face + 0.02, z - h), (y_face + 0.02, z + 0.02), (y_face - depth, z + 0.02)]
    c = K.prism(sec, x0, x1, role)
    A = np.asarray(c.v)
    c.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0], A[:, 1]], axis=1).tolist()]
    m.merge(c.orient_outward())
    for i in range(brackets):
        bx = x0 + (x1 - x0) * (i + 0.5) / brackets
        sec = [(y_face + 0.01, z - h - 0.34), (y_face + 0.01, z - h + 0.01), (y_face - depth * 0.85, z - h + 0.01)]
        b = K.prism(sec, bx - 0.05, bx + 0.05, bracket_role)
        A = np.asarray(b.v)
        b.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0], A[:, 1]], axis=1).tolist()]
        m.merge(b.orient_outward())
    return m


def card(cx, y, cz, w, h, role):
    """Single-sided painted card (one quad, normalized UVs) in the XZ plane at depth y, facing -Y (kit_card_ nodes)."""
    v = [(cx - w / 2, y, cz - h / 2), (cx + w / 2, y, cz - h / 2), (cx + w / 2, y, cz + h / 2), (cx - w / 2, y, cz + h / 2)]
    return K.Mesh().add(v, [(0, 1, 2, 3)], role, False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])


def card_poly(outline_xz, y, role):
    """Single-sided planar polygon card facing -Y (arched panes, sign shapes); UVs normalized to the outline bbox."""
    P = np.asarray(outline_xz, dtype=np.float64)
    lo, hi = P.min(0), P.max(0)
    span = np.maximum(hi - lo, 1e-6)
    tris = K.tessellate(K.ccw([tuple(p) for p in outline_xz]))
    pts = K.ccw([tuple(p) for p in outline_xz])
    m = K.Mesh()
    for t in tris:
        q = [pts[i] for i in t]
        m.add([(x, y, z) for x, z in q], [(0, 1, 2)], role, False, [("n", [((x - lo[0]) / span[0], (z - lo[1]) / span[1]) for x, z in q])])
    m = weld(m)
    # face -Y: the triangles from a CCW (x, z) outline face +Y after the x-z embedding; flip them
    return m.flip()


def window(cx, cz, w, h, y_face, pane_role="screen", frame_role="trim", depth=0.06, sill=True, head=False):
    """Wall window -> (frame solid, pane card): a trim frame slab with a sill lip (and optional peaked head board),
    and a painted pane card just proud of it."""
    zb = cz - h / 2 - (0.16 if sill else 0.09)
    zs = zb + 0.07
    zt = cz + h / 2 + 0.11
    x0, x1 = cx - w / 2 - 0.1, cx + w / 2 + 0.1
    fr = [(x0 - 0.06, zb), (x1 + 0.06, zb), (x1 + 0.06, zs), (x1, zs), (x1, zt)]
    if head:
        fr += [(x1 + 0.06, zt), (x1 + 0.06, zt + 0.07), (cx, zt + 0.24), (x0 - 0.06, zt + 0.07), (x0 - 0.06, zt)]
    fr += [(x0, zt), (x0, zs), (x0 - 0.06, zs)]
    frame = slab(fr, y_face - depth, y_face + 0.02, frame_role)
    pane = card(cx, y_face - depth - 0.008, cz, w, h, pane_role)
    return frame, pane


def door_panel(cx, w, h, y_face, z0=0.0, role="door", recess=0.0, frame_role="trim"):
    """Painted door card (normalized UVs) just proud of a wall face; recess > 0 adds a dark reveal card behind."""
    m = K.Mesh()
    if recess > 0:
        m.merge(card(cx, y_face - 0.006, z0 + h / 2, w + 0.04, h + 0.02, "opening"))
        m.merge(card(cx, y_face - 0.02, z0 + h / 2, w * 0.96, h * 0.97, role))
    else:
        m.merge(card(cx, y_face - 0.01, z0 + h / 2, w, h, role))
    return m


def railing(x0, x1, y, z0, h, bays, role_rail="rail", role_post="post", balusters=2, post_s=0.12):
    """Porch / balcony railing along x at depth y: posts at the bay ends, a top and a mid rail, thin balusters."""
    m = K.Mesh()
    n = max(1, int(bays))
    for i in range(n + 1):
        if post_s <= 0:
            break
        x = x0 + (x1 - x0) * i / n
        m.merge(sq_post(x, y, z0, z0 + h + 0.06, post_s, role_post))
    m.merge(beam((x0, y, z0 + h), (x1, y, z0 + h), 0.09, 0.09, role_rail, roll=45.0))
    m.merge(beam((x0, y, z0 + h * 0.45), (x1, y, z0 + h * 0.45), 0.06, 0.06, role_rail, roll=45.0))
    for i in range(n):
        for k in range(balusters):
            x = x0 + (x1 - x0) * (i + (k + 1) / (balusters + 1)) / n
            m.merge(spindle((x, y, z0 + 0.02), (x, y, z0 + h - 0.05), 0.05, role_rail))
    return m


def stair_block(w, n, rise, run, role="step", side_role="wood", y_top=0.0, z0=0.0):
    """Solid plank stair as ONE closed sawtooth prism (n treads climbing toward +Y, top tread ending at y_top): the
    side faces show the stringer profile, the tread/riser faces carry the step planks."""
    pts = [(y_top - n * run, z0)]
    for i in range(n):
        y = y_top - (n - i) * run
        pts += [(y, z0 + (i + 1) * rise), (y + run, z0 + (i + 1) * rise)]
    pts += [(y_top, z0)]
    clean = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - clean[-1][0]) > 1e-9 or abs(p[1] - clean[-1][1]) > 1e-9:
            clean.append(p)
    m = K.prism(clean, -w / 2, w / 2, role, role_top=side_role, role_bottom=side_role)
    A = np.asarray(m.v)
    m.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0], A[:, 1]], axis=1).tolist()]
    return m.orient_outward()


def plank_deck(x0, x1, y0, y1, z, t, role="step", ch=0.03):
    """Deck slab (painted planks) with chamfered edges."""
    return chamfer((x0 + x1) / 2, (y0 + y1) / 2, z - t, z, x1 - x0, y1 - y0, ch, "wood", top=role, bottom="wood")


def mesh_tris(m):
    return m.tri_count()


UV_KEEP = ("post", "rope", "metal", "rail", "bark", "foliage", "flower", "cap", "chrome", "orb", "glass", "light", "fire")


def planar_uv(m, keep=UV_KEEP):
    """Per-face metric UVs aligned to the face: u along the face's horizontal tangent, v up its steepest slope (v = z
    on walls, so lap siding runs level; on roofs shingle courses run parallel to the eaves and tin corrugations run
    down the slope); horizontal faces map (x, y). Normalized ('n') UVs and the `keep` roles are left alone."""
    V = np.asarray(m.v, dtype=np.float64)
    up = np.array([0.0, 0.0, 1.0])
    for fi, f in enumerate(m.f):
        u = m.uv[fi]
        if (u is not None and u[0] == "n") or m.r[fi] in keep:
            continue
        P = V[list(f)]
        n = np.zeros(3)
        for i in range(len(f)):
            a_, b_ = P[i], P[(i + 1) % len(f)]
            n += np.array([(a_[1] - b_[1]) * (a_[2] + b_[2]), (a_[2] - b_[2]) * (a_[0] + b_[0]), (a_[0] - b_[0]) * (a_[1] + b_[1])])
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n /= ln
        if abs(n[2]) > 0.985:
            uv = [(float(p[0]), float(p[1] if n[2] >= 0 else -p[1])) for p in P]
        else:
            t = np.cross(up, n)
            t /= np.linalg.norm(t)
            bt = np.cross(n, t)
            uv = [(float(p @ t), float(p @ bt)) for p in P]
        m.uv[fi] = ("m", uv)
    return m


# ---------------------------------------------------------------- wheels, sweeps, rock sheets
def wheel(cx, cy, cz, r, w, role="ice", rim_role="metal", sides=10, axis="x"):
    """Painted disc wheel: a short closed cylinder whose two faces carry the painted spoke texture (normalized UVs)
    and whose tread band takes rim_role. axis 'x': turns about X (rolls along Y); 'y': turns about Y."""
    ring = [(r * math.cos(2 * math.pi * i / sides + math.pi / sides), r * math.sin(2 * math.pi * i / sides + math.pi / sides))
            for i in range(sides)]
    if axis == "x":
        A = [(cx - w / 2, cy + a, cz + b) for a, b in ring]
        Bv = [(cx + w / 2, cy + a, cz + b) for a, b in ring]
    else:
        A = [(cx + a, cy - w / 2, cz + b) for a, b in ring]
        Bv = [(cx + a, cy + w / 2, cz + b) for a, b in ring]
    uv = [(0.5 + 0.5 * a / r, 0.5 + 0.5 * b / r) for a, b in ring]
    m = K.Mesh()
    verts = A + Bv
    faces, roles, uvs = [], [], []
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, sides + j, sides + i))
        roles.append(rim_role)
        uvs.append(None)
    faces.append(tuple(reversed(range(sides))))
    roles.append(role)
    uvs.append(("n", list(reversed(uv))))
    faces.append(tuple(range(sides, 2 * sides)))
    roles.append(role)
    uvs.append(("n", uv))
    m.add(verts, faces, roles, False, uvs)
    return m.orient_outward()


def sweep(path, section, role, cap=True, up=(0.0, 0.0, 1.0), cap_role=None):
    """Loft a 2D section [(s, u)] (s across to the right of travel, u up) along a 3D polyline path."""
    P = [np.asarray(p, dtype=np.float64) for p in path]
    upv = np.asarray(up, dtype=np.float64)
    rings = []
    for i, p in enumerate(P):
        if i == 0:
            t = P[1] - P[0]
        elif i == len(P) - 1:
            t = P[-1] - P[-2]
        else:
            t = P[i + 1] - P[i - 1]
        t = t / max(np.linalg.norm(t), 1e-9)
        s = np.cross(t, upv)
        s = s / max(np.linalg.norm(s), 1e-9)
        u2 = np.cross(s, t)
        rings.append([tuple(p + s * a + u2 * b) for a, b in section])
    cr = cap_role or role
    m = K.loft(rings, role, smooth=False, cap0=cap, cap1=cap, cap_roles=(cr, cr))
    return m.orient_outward() if cap else m


def arc_path(cx, cy, r, a0, a1, n, z=0.0):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n), z) for i in range(n + 1)]


def bumps(r, n, lo=(0.0, 0.0), hi=(1.0, 1.0), amp=0.35, size=(0.18, 0.3)):
    out = []
    for _ in range(n):
        out.append((r.uniform(lo[0], hi[0]), r.uniform(lo[1], hi[1]), r.uniform(0.4, 1.0) * amp * (1 if r.random() < 0.8 else -0.6),
                    r.uniform(*size), r.uniform(*size)))
    return out


def bump_field(bs, s, t):
    v = 0.0
    for cs, ct, a, ws, wt in bs:
        v += a * math.exp(-(((s - cs) / ws) ** 2 + ((t - ct) / wt) ** 2))
    return v


def grid_sheet(us, vs, fn, role_fn, skip=None):
    """Open quad grid over parameter stations us x vs (lists in [0, 1] or metres); fn(u, v) -> (x, y, z) laid out so the
    front side faces -Y for u along +X and v along +Z; role_fn(i, j) -> role; skip(i, j) -> True leaves a hole."""
    Pg = [[fn(u, v) for u in us] for v in vs]
    m = K.Mesh()
    for j in range(len(vs) - 1):
        for i in range(len(us) - 1):
            if skip and skip(i, j):
                continue
            q = [Pg[j][i], Pg[j][i + 1], Pg[j + 1][i + 1], Pg[j + 1][i]]
            if not D.quad_ok(*q):
                continue
            m.add(q, [(0, 1, 2, 3)], role_fn(i, j), False)
    return weld(m)
