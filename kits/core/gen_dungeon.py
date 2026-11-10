"""DUNGEONKIT dungeon architecture family (dgn.*), theme-agnostic, on the DUNGEON GRID (kits/core/dkit.py).

Blender space (+Z up). Grid pieces are NOT re-centred by finalize(): their origins are exact grid anchors so they
interlock by data (docs/DUNGEONKIT.md, kits/library/dungeonkit-sockets.json):

- cell pieces (dgn.room, dgn.corridor, dgn.floor, dgn.pit, dgn.ceiling, dgn.stairs) have their origin on the centre
  of their cell block at floor level; room north = Blender +Y (glTF -Z);
- wall-line pieces (dgn.wall) have their origin on the cell boundary line at floor level and stand into the room
  (Blender -Y = glTF +Z, the front of every kit piece);
- door pieces (dgn.doorway, dgn.door_locked) have their origin on the room.gd door anchor: 0.4 m in from the room edge
  = 0.1 m behind the cell boundary (the room plot has a 0.5 m apron, so doors sit on cell-edge midpoints).
Every piece lists its sockets in meta["sockets"] (glTF piece space: x right, y up, z toward the front).
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node
from .asset import register
from .rng import rng

V = "1.0.0"
SIDES = ["n", "e", "s", "w"]
DOOR_ITEM = {"side": S.enum("s", SIDES), "cell": S.integer(0, 0, 7)}
TORCH_ITEM = {"side": S.enum("n", SIDES), "cell": S.integer(0, 0, 7)}
TORCH_Z = 2.35          # flame height of a dprop.sconce mounted on a torch socket
TORCH_OUT = 0.42        # flame distance in front of the wall face
CUT_W, CUT_H = 2.8, 3.6   # wall cut a doorway frame fills (0.1 m of wall left before an inner corner)
FRAME_D = 0.75            # frame depth (back face on the door anchor, 0.15 m proud of the wall face)


def gl(p):
    """Blender (x, y, z) -> glTF (x, z, -y) rounded, for socket data."""
    return [round(float(p[0]), 4), round(float(p[2]), 4), round(float(-p[1]), 4)]


def sock(kind, pos, facing, **kw):
    """facing: outward direction in piece space, one of n e s w up down (n = glTF -Z, s = glTF +Z / the front)."""
    d = {"type": kind, "position": gl(pos), "facing": facing}
    d.update(kw)
    return d


def grid_meta(anchor, cells=None, sockets=(), **kw):
    m = {"dungeon_grid": {"cell_m": D.CELL, "wall_inset_m": D.WALL_T, "storey_m": D.H, "anchor": anchor}}
    if cells is not None:
        m["dungeon_grid"]["cells"] = list(cells)
    m["sockets"] = list(sockets)
    m.update(kw)
    return m


def light(pos, radius=4.2, strength=1.0):
    return {"pos": [round(float(c), 4) for c in pos], "radius": radius, "strength": strength}


def rot_xy(p, yaw_deg):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


# side -> (yaw of a sheet built along +X facing -Y, so it faces into the cell from that side)
SHEET_YAW = {"n": 0.0, "e": -90.0, "s": 180.0, "w": 90.0}
FACING = {"n": "n", "e": "e", "s": "s", "w": "w"}
INWARD = {"n": (0.0, -1.0), "e": (-1.0, 0.0), "s": (0.0, 1.0), "w": (1.0, 0.0)}


def side_sheet(side, hx, hy, s0, s1, **kw):
    """Wall sheet on `side` of a box with inner half extents hx, hy (inner faces at +-hx / +-hy), covering the sheet
    span [s0, s1] measured along the side (n/s: from the west end; e/w: from the north end). Returns a Mesh."""
    L = s1 - s0
    shift = [(o[0] - s0, o[1] - s0) + tuple(o[2:]) for o in kw.pop("openings", ())]
    pil = [(a - s0, b - s0, d) for a, b, d in kw.pop("pilasters", ())]
    rel = [(a - s0, b - s0, z0, z1, r) for a, b, z0, z1, r in kw.pop("relief", ())]
    m = D.wall_sheet(L, openings=shift, pilasters=pil, relief=rel, **kw)
    if side == "n":
        m.translate(s0 - hx, hy, 0)
    elif side == "s":
        m.rotate_z(math.pi).translate(hx - s0, -hy, 0)
    elif side == "e":
        m.rotate_z(-math.pi / 2).translate(hx, hy - s0, 0)
    else:
        m.rotate_z(math.pi / 2).translate(-hx, s0 - hy, 0)
    return m


def side_point(side, hx, hy, s, out=0.0, z=0.0):
    """Point on the inner face of `side` at span coordinate s (same convention as side_sheet), `out` metres into the
    room."""
    if side == "n":
        return (s - hx, hy - out, z)
    if side == "s":
        return (hx - s, -hy + out, z)
    if side == "e":
        return (hx - out, hy - s, z)
    return (-hx + out, s - hy, z)


def pier(cx, cy, size, h, role="trim", cap_role="trim", base_role="stone", capital=True):
    """Square pier with a chamfered base course (and a capital block): closed bevelled solids."""
    out = K.Mesh()
    out.merge(D.bevel_box(cx, cy, 0.0, size + 0.12, size + 0.12, 0.5, base_role, bevel=0.05))
    top = h - 0.45 if capital else h
    out.merge(D.bevel_box(cx, cy, 0.5, size, size, top - 0.5, role, bevel=0.07))
    if capital:
        out.merge(D.bevel_box(cx, cy, h - 0.45, size + 0.16, size + 0.16, 0.45, cap_role, bevel=0.06))
    return out


def panel(cx, cy, z0, w, h, d, role, edge_role=None):
    """Closed thin slab whose FRONT face (-Y) carries normalized UVs (one painted motif per panel); the other faces
    use metric UVs of edge_role."""
    x0, x1, y0, y1, z1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2, z0 + h
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 5, 4), (0, 3, 2, 1), (4, 5, 6, 7), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    er = edge_role or role
    uvs = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5
    return K.Mesh().add(v, f, [role, er, er, er, er, er], False, uvs)


def grid_floor(xs, ys, inside, z=0.0, role="floor", flip=False):
    """One-sided floor (or ceiling if flip) on station lists xs, ys; quads whose centre passes inside(cx, cy)."""
    m = K.Mesh()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
            if not inside(cx, cy):
                continue
            q = [(xs[i], ys[j], z), (xs[i + 1], ys[j], z), (xs[i + 1], ys[j + 1], z), (xs[i], ys[j + 1], z)]
            m.add(q, [(0, 1, 2, 3)], role if isinstance(role, str) else role(cx, cy), False)
    m = D.weld_mesh(m)
    return m.flip() if flip else m


def stations(a, b, step, extra=()):
    k = max(1, int(round((b - a) / step)))
    s = {round(a + (b - a) * i / k, 6) for i in range(k + 1)}
    s.update(round(e, 6) for e in extra if a - 1e-9 <= e <= b + 1e-9)
    return sorted(s)


def beams(x0, x1, ys, z, role="wood", w=0.32, h=0.34):
    out = K.Mesh()
    for y in ys:
        out.merge(D.bevel_box(0.5 * (x0 + x1), y, z - h, x1 - x0, w, h, role, bevel=0.04))
    return out


# ---------------------------------------------------------------- dgn.room
@register("dgn.room", V, "shell", {
    "cells_x": S.integer(3, 1, 5, "cells west-east (4 m each)"),
    "cells_y": S.integer(3, 1, 5, "cells north-south (4 m each)"),
    "doors": S.array(DOOR_ITEM, [{"side": "s", "cell": 1}], 8, "door sockets: side + cell index (n/s from west, e/w from north)"),
    "torches": S.array(TORCH_ITEM, [], 10, "torch sockets that carry a sconce (baked as warm pools in point_bake packs)"),
    "pilasters": S.boolean(True), "relief": S.enum("none", ["none", "alternate", "all"]),
    "floor_border": S.boolean(True),
    "open_cells": S.array({"x": S.integer(0, 0, 4), "y": S.integer(0, 0, 4)}, [], 12,
                          "cells left without room floor (x from the west, y from the north) for pit / stair / inlaid floor cells"),
}, "Dungeon room shell on the 4 m grid: one-sided relief walls (mossy plinth, cut-stone body, stepped cornice), "
   "pilasters on cell boundaries, flagstone floor with a dressed border, door cuts on cell-edge midpoints for "
   "dgn.doorway frames, torch sockets, carved relief panels, open cells for pit pieces. Ceilings are separate "
   "dgn.ceiling pieces.", origin="room_floor")
def room(P, seed):
    cx_, cy_ = P["cells_x"], P["cells_y"]
    W, Dd = cx_ * D.CELL, cy_ * D.CELL
    hx, hy = W / 2 - D.WALL_T, Dd / 2 - D.WALL_T
    span = {"n": 2 * hx, "s": 2 * hx, "e": 2 * hy, "w": 2 * hy}
    ncell = {"n": cx_, "s": cx_, "e": cy_, "w": cy_}
    doors = {(d["side"], d["cell"]) for d in P["doors"]}
    for s_, c_ in doors:
        if c_ >= ncell[s_]:
            raise ValueError("door %s%d outside a %dx%d room" % (s_, c_, cx_, cy_))
    torches = {(t["side"], t["cell"]) for t in P["torches"]}
    for t in torches:
        if t in doors or t[1] >= ncell[t[0]]:
            raise ValueError("torch socket %s%d is a door or outside the room" % t)
    walls = K.Mesh()
    panels = K.Mesh()
    sockets, lights = [], []
    for side in SIDES:
        L = span[side]
        ext = D.WALL_T if side in ("n", "s") else 0.0      # n/s run through the corners to the boundary
        cut, pil, rel = [], [], []
        nat = (lambda t: t) if side in ("n", "e") else (lambda t, L=L: L - t)   # room-friendly -> sheet span
        for i in range(ncell[side]):
            mid = nat(4.0 * i + 2.0 - D.WALL_T)     # cell-edge midpoint (cell i from the west / from the north)
            if (side, i) in doors:
                cut.append((mid - CUT_W / 2, mid + CUT_W / 2, CUT_H))
                p = side_point(side, hx, hy, mid)
                sockets.append(sock("door", p, side, cell=i, side=side, width_m=D.DOOR_W, height_m=D.DOOR_H,
                                    needs="dgn.doorway"))
            else:
                if P["relief"] == "all" or (P["relief"] == "alternate" and i % 2 == 1):
                    pp = panel(0.0, -0.05, 1.25, 2.0, 1.9, 0.1, "wall_alt", "trim")
                    q = side_point(side, hx, hy, mid)
                    panels.merge(pp.rotate_z(math.radians(SHEET_YAW[side])).translate(q[0], q[1], 0.0))
                p = side_point(side, hx, hy, mid)
                sockets.append(sock("torch" if (side, i) in torches else "wall", p, side, cell=i, side=side,
                                    mount_height_m=TORCH_Z))
                if (side, i) in torches:
                    lights.append(light(side_point(side, hx, hy, mid, TORCH_OUT, TORCH_Z)))
            if P["pilasters"] and 0 < i:
                b = nat(4.0 * i - D.WALL_T)
                pil.append((b - 0.32, b + 0.32, 0.2))
        walls.merge(side_sheet(side, hx, hy, -ext, L + ext, openings=cut, pilasters=pil, relief=rel,
                               cap_trim=(0.0, 0.0) if ext else (0.205, 0.205)))
    # corner rule (no shared vertices, no coplanar caps): n/s sheets run through the corners to the cell boundary
    # behind the e/w faces; e/w sheets stop on the n/s faces and leave the corner caps to n/s.
    border = 0.6 if P["floor_border"] else 0.0
    opened = {(c["x"], c["y"]) for c in P["open_cells"]}
    for c in opened:
        if c[0] >= cx_ or c[1] >= cy_:
            raise ValueError("open cell %s outside a %dx%d room" % (c, cx_, cy_))
    bx = [-W / 2 + D.CELL * k for k in range(1, cx_)] if opened else []
    by = [-Dd / 2 + D.CELL * k for k in range(1, cy_)] if opened else []
    xs = stations(-hx, hx, 2.0, ((-hx + border, hx - border) if border else ()) + tuple(bx))
    ys = stations(-hy, hy, 2.0, ((-hy + border, hy - border) if border else ()) + tuple(by))

    def frole(cx, cy):
        if border and (abs(cx) > hx - border or abs(cy) > hy - border):
            return "step"
        return "floor"

    def solid(x, y):
        return (int((x + W / 2) // D.CELL), int((Dd / 2 - y) // D.CELL)) not in opened
    floor = grid_floor(xs, ys, solid, 0.0, frole)
    for c in sorted(opened):
        sockets.append(sock("pit", (-W / 2 + D.CELL * (c[0] + 0.5), Dd / 2 - D.CELL * (c[1] + 0.5), 0.0), "up", cell=list(c),
                            needs="dgn.pit|dgn.stairs|dgn.floor|tmpl.floor"))
    nodes = [Node("floor", floor, "shell"), Node("walls", walls, "shell")]
    if panels.f:
        nodes.append(Node("reliefs", panels, "solid"))
    meta = grid_meta("cell_block_centre", (cx_, cy_), sockets, bake_lights=lights,
                     plot_m=[W + 1.0, Dd + 1.0], interior_m=[2 * hx, 2 * hy],
                     door_positions={"%s%d" % (s_, c_): 4 * c_ + 2 for s_, c_ in sorted(doors)},
                     note="room plot = cells x 4 m + 0.5 m apron each side; place the shell at the plot centre; "
                          "a door on side/cell i has door.position = 4*i + 2 (room.gd door anchor)")
    return Asset(nodes, meta)


# ---------------------------------------------------------------- dgn.corridor
CORRIDOR_OPEN = {"straight": "ns", "end_wall": "s", "end_door": "s", "corner": "se", "tee": "sew", "cross": "nsew"}


@register("dgn.corridor", V, "shell", {
    "kind": S.enum("straight", list(CORRIDOR_OPEN)),
    "ceiling": S.enum("flat", ["none", "flat"]),
    "torch": S.boolean(False, "torch socket on the first closed side wall (baked pool in point_bake packs)"),
}, "Corridor cell (4 m): 3 m clear passage between one-sided relief walls, piers on convex corners, flagstone "
   "floor, beamed flat ceiling. Kinds: straight, end_wall, end_door (door cut for a dgn.doorway), corner, tee, cross. "
   "Open sides carry corridor sockets that must meet another corridor socket.", origin="room_floor")
def corridor(P, seed):
    kind = P["kind"]
    opn = set(CORRIDOR_OPEN[kind])
    h = D.CELL / 2 - D.WALL_T        # 1.5: inner faces
    e = D.CELL / 2                   # 2.0: cell boundary
    walls = K.Mesh()
    sockets, lights = [], []
    closed = [s for s in SIDES if s not in opn]
    torch_side = closed[0] if (P["torch"] and closed) else None
    for side in SIDES:
        if side in opn:
            p = {"n": (0, e, 0), "s": (0, -e, 0), "e": (e, 0, 0), "w": (-e, 0, 0)}[side]
            sockets.append(sock("corridor", p, side, width_m=2 * h))
            continue
        # natural sheet span (n: west->east, e: north->south, s: east->west, w: south->north); walls stop at inner
        # corners and run to the cell boundary at open ends
        west = -e if "w" in opn else -h
        east = e if "e" in opn else h
        north = e if "n" in opn else h
        south = -e if "s" in opn else -h
        s0, s1 = {"n": (west + h, east + h), "e": (h - north, h - south), "s": (h - east, h - west),
                  "w": (south + h, north + h)}[side]
        trim = [0.0, 0.0]
        if side in ("n", "s"):
            # through closed corners to the boundary (behind the e/w faces)
            lo_closed = ("w" not in opn) if side == "n" else ("e" not in opn)
            hi_closed = ("e" not in opn) if side == "n" else ("w" not in opn)
            s0 -= D.WALL_T if lo_closed else 0.0
            s1 += D.WALL_T if hi_closed else 0.0
        else:
            lo_closed = ("n" not in opn) if side == "e" else ("s" not in opn)
            hi_closed = ("s" not in opn) if side == "e" else ("n" not in opn)
            trim = [0.205 if lo_closed else 0.0, 0.205 if hi_closed else 0.0]
        openings = []
        if kind == "end_door" and side == "n":
            openings = [(h - CUT_W / 2, h + CUT_W / 2, CUT_H)]
            sockets.append(sock("door", side_point("n", h, h, h), "n", width_m=D.DOOR_W, height_m=D.DOOR_H,
                                needs="dgn.doorway"))
        mid = 0.5 * (s0 + s1)
        if side == torch_side and not openings:
            sockets.append(sock("torch", side_point(side, h, h, mid), side, mount_height_m=TORCH_Z))
            lights.append(light(side_point(side, h, h, mid, TORCH_OUT, TORCH_Z), 3.8))
        walls.merge(side_sheet(side, h, h, s0, s1, openings=openings, cap_trim=tuple(trim)))
    xs = stations(-e if "w" in opn else -h, e if "e" in opn else h, 1.5, (-h, h, 0.0))
    ys = stations(-e if "s" in opn else -h, e if "n" in opn else h, 1.5, (-h, h, 0.0))

    def inside(x, y):
        if abs(x) <= h and abs(y) <= h:
            return True
        if abs(x) <= h and ((y > h and "n" in opn) or (y < -h and "s" in opn)):
            return True
        if abs(y) <= h and ((x > h and "e" in opn) or (x < -h and "w" in opn)):
            return True
        return False
    nodes = [Node("floor", grid_floor(xs, ys, inside, 0.0, "floor"), "shell"), Node("walls", walls, "shell")]
    piers = K.Mesh()
    ps = 0.78
    for sx, sy, a_, b_ in ((1, 1, "n", "e"), (1, -1, "s", "e"), (-1, -1, "s", "w"), (-1, 1, "n", "w")):
        if a_ in opn and b_ in opn:
            piers.merge(pier(sx * (e - ps / 2), sy * (e - ps / 2), ps, D.H + 0.1))
    if piers.f:
        nodes.append(Node("piers", piers, "solid"))
    if P["ceiling"] == "flat":
        nodes.append(Node("ceiling", grid_floor(xs, ys, inside, D.H, "ceiling", flip=True), "shell"))
        if kind in ("straight", "end_wall", "end_door"):
            nodes.append(Node("beams", beams(-h, h, [0.0], D.H, "wood"), "solid"))
        else:
            boss = D.bevel_box(0, 0, D.H - 0.3, 1.0, 1.0, 0.3, "trim", bevel=0.08)
            nodes.append(Node("boss", boss, "solid"))
    meta = grid_meta("cell_centre", (1, 1), sockets, bake_lights=lights, kind=kind, open_sides="".join(s for s in SIDES if s in opn))
    return Asset(nodes, meta)


# ---------------------------------------------------------------- dgn.wall (modular wall segment)
@register("dgn.wall", V, "shell", {
    "kind": S.enum("solid", ["solid", "door", "slit", "alcove", "relief", "torch"]),
    "length_cells": S.integer(1, 1, 2),
    "end_piers": S.enum("none", ["none", "left", "right", "both"], "piers covering open wall ends (convex corners)"),
}, "Modular wall segment for one (or two) cell edges: origin on the cell boundary, inner face 0.5 m in front. "
   "Kinds: solid, door (cut for dgn.doorway), slit (window slit with splayed reveal and a cold glow plate), alcove "
   "(arched niche), relief (carved panel), torch (torch socket).", origin="opening_floor")
def wall(P, seed):
    L = D.CELL * P["length_cells"]
    kind = P["kind"]
    openings, rel = [], []
    nodes, sockets, lights = [], [], []
    mid = L / 2
    extra = K.Mesh()
    if kind == "door":
        openings.append((mid - CUT_W / 2, mid + CUT_W / 2, CUT_H))
        sockets.append(sock("door", (0, -D.WALL_T, 0), "s", width_m=D.DOOR_W, height_m=D.DOOR_H, needs="dgn.doorway",
                            anchor_offset_m=0.1))
    elif kind == "slit":
        sw, z0, z1 = 0.7, 1.35, 3.3
        openings.append((mid - sw / 2, mid + sw / 2, z1, z0))
        # splayed reveal: a closed frame ring around the hole, narrowing to a 0.22 m slit at the back
        out_ = [(-sw / 2 - 0.12, z0 - 0.12), (sw / 2 + 0.12, z0 - 0.12), (sw / 2 + 0.12, z1 + 0.12), (-sw / 2 - 0.12, z1 + 0.12)]
        hole = [(-sw / 2, z0), (sw / 2, z0), (sw / 2, z1), (-sw / 2, z1)]
        fr = K.prism(out_, 0.0, 0.18, "frame", holes=[hole]).rotate_x(math.pi / 2).translate(0, -D.WALL_T + 0.04, 0)
        extra.merge(fr)
        back = [(-0.11, z0 + 0.15), (0.11, z0 + 0.15), (0.11, z1 - 0.15), (-0.11, z1 - 0.15)]
        rv = K.Mesh()
        # reveal sides (one-sided, facing into the slit) from the wall face back to the glow plate
        F = [(-sw / 2, -D.WALL_T, z0), (sw / 2, -D.WALL_T, z0), (sw / 2, -D.WALL_T, z1), (-sw / 2, -D.WALL_T, z1)]
        B = [(x, -0.12, z) for x, z in back]
        for i in range(4):
            a, b = F[i], F[(i + 1) % 4]
            c, d = B[(i + 1) % 4], B[i]
            rv.add([a, b, c, d], [(0, 1, 2, 3)], "stone", False)
        rv = D.weld_mesh(rv)
        nodes.append(Node("reveal", rv, "shell"))
        glow = K.Mesh().add(B, [(0, 1, 2, 3)], "view", False,
                            [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
        nodes.append(Node("glow", glow, "card"))
        sockets.append(sock("window", (0, -D.WALL_T, 0.5 * (z0 + z1)), "s", width_m=0.22, height_m=z1 - z0))
    elif kind == "alcove":
        aw, ah, ad = 1.6, 2.6, 0.36
        openings.append((mid - aw / 2, mid + aw / 2, ah + 0.5, 0.5))
        niche = K.Mesh()
        x0, x1, z0, z1 = -aw / 2, aw / 2, 0.5, 0.5 + ah
        yf, yb = -D.WALL_T, -D.WALL_T + ad
        quads = [
            [(x0, yb, z0), (x1, yb, z0), (x1, yb, z1), (x0, yb, z1)],            # back (faces -Y)
            [(x0, yf, z0), (x0, yb, z0), (x0, yb, z1), (x0, yf, z1)],            # left side (faces +X)
            [(x1, yb, z0), (x1, yf, z0), (x1, yf, z1), (x1, yb, z1)],            # right side (faces -X)
            [(x0, yf, z0), (x1, yf, z0), (x1, yb, z0), (x0, yb, z0)],            # sill (faces +Z)
            [(x0, yb, z1), (x1, yb, z1), (x1, yf, z1), (x0, yf, z1)],            # head (faces -Z)
        ]
        for q, r in zip(quads, ["wall_alt", "stone", "stone", "trim", "stone"]):
            niche.add(q, [(0, 1, 2, 3)], r, False)
        nodes.append(Node("niche", D.weld_mesh(niche), "shell"))
        ring_o = [(-aw / 2 - 0.16, 0.5 - 0.1), (aw / 2 + 0.16, 0.5 - 0.1), (aw / 2 + 0.16, z1 + 0.16), (-aw / 2 - 0.16, z1 + 0.16)]
        ring_i = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        extra.merge(K.prism(ring_o, 0.0, 0.14, "frame", holes=[ring_i]).rotate_x(math.pi / 2).translate(0, -D.WALL_T + 0.02, 0))
        sockets.append(sock("alcove", (0, -D.WALL_T + 0.18, 0.5), "s", width_m=aw, depth_m=ad))
    elif kind == "relief":
        rel.append((mid - 1.2, mid + 1.2, 1.3, 3.1, "wall_alt"))
    elif kind == "torch":
        sockets.append(sock("torch", (0, -D.WALL_T, 0), "s", mount_height_m=TORCH_Z))
        lights.append(light((0, -D.WALL_T - TORCH_OUT, TORCH_Z), 4.0))
    sheet = D.wall_sheet(L, openings=openings, relief=rel).translate(-mid, -D.WALL_T, 0)
    nodes.insert(0, Node("wall", sheet, "shell"))
    ends = P["end_piers"]
    pm = K.Mesh()
    ps = 0.78
    if ends in ("left", "both"):
        pm.merge(pier(-mid + ps / 2 - 0.0, -D.WALL_T + 0.5 - ps / 2 - 0.0, ps, D.H + 0.1))
    if ends in ("right", "both"):
        pm.merge(pier(mid - ps / 2, -D.WALL_T + 0.5 - ps / 2, ps, D.H + 0.1))
    if pm.f:
        extra.merge(pm)
    if extra.f:
        nodes.append(Node("trim", extra, "solid"))
    for k in range(P["length_cells"]):
        pass
    meta = grid_meta("cell_edge", (P["length_cells"], 0), sockets, bake_lights=lights, kind=kind,
                     note="origin on the cell boundary line; inner face 0.5 m toward the front")
    return Asset(nodes, meta)


# ---------------------------------------------------------------- dgn.floor
@register("dgn.floor", V, "shell", {
    "kind": S.enum("plain", ["plain", "border", "grate", "cracked"]),
    "cells_x": S.integer(1, 1, 2), "cells_y": S.integer(1, 1, 2),
}, "Floor tile for 1-2 x 1-2 cells (covers the full cell block; walls stand on its rim). Kinds: plain flagstones, "
   "border (dressed rim), grate (iron drain grate over a dark sump), cracked (sunken broken slabs).",
   origin="terrain_center")
def floor(P, seed):
    hx, hy = P["cells_x"] * D.CELL / 2, P["cells_y"] * D.CELL / 2
    kind = P["kind"]
    nodes = []
    if kind == "grate":
        g = 0.7
        m = grid_floor(stations(-hx, hx, 2.0, (-g, g)), stations(-hy, hy, 2.0, (-g, g)),
                       lambda x, y: not (abs(x) < g and abs(y) < g), 0.0, "floor")
        sump = K.Mesh()
        for q in ([(-g, -g, 0), (-g, -g, -0.5), (-g, g, -0.5), (-g, g, 0)], [(g, -g, -0.5), (g, -g, 0), (g, g, 0), (g, g, -0.5)],
                  [(-g, -g, -0.5), (-g, -g, 0), (g, -g, 0), (g, -g, -0.5)], [(-g, g, 0), (-g, g, -0.5), (g, g, -0.5), (g, g, 0)],
                  [(-g, -g, -0.5), (g, -g, -0.5), (g, g, -0.5), (-g, g, -0.5)]):
            sump.add(q, [(0, 1, 2, 3)], "stone", False)
        sump = D.weld_mesh(sump)
        nodes.append(Node("sump", sump, "shell"))
        bars = K.Mesh()
        for i in range(5):
            x = -g + (i + 0.5) * (2 * g / 5)
            bars.merge(K.box(x, 0, -0.04, 0.07, 2 * g + 0.1, 0.08, "metal"))
        bars.merge(K.box(0, -g - 0.02, -0.03, 2 * g + 0.12, 0.08, 0.06, "metal"))
        bars.merge(K.box(0, g + 0.02, -0.03, 2 * g + 0.12, 0.08, 0.06, "metal"))
        nodes.append(Node("grate", bars, "solid"))
    elif kind == "cracked":
        m = grid_floor(stations(-hx, hx, 1.0), stations(-hy, hy, 1.0), lambda x, y: True, 0.0, "floor")
        r = rng(seed, "dgn.floor", "cracked")
        V_ = np.asarray(m.v)
        for i, p in enumerate(V_):
            if abs(p[0]) < hx - 0.05 and abs(p[1]) < hy - 0.05 and r.random() < 0.5:
                V_[i][2] = -0.05 * r.random()
        m.v = [tuple(p) for p in V_]
        chips = K.Mesh()
        for k in range(4):
            chips.merge(D.rock_blob(r.uniform(-hx + 0.6, hx - 0.6), r.uniform(-hy + 0.6, hy - 0.6), 0.06, 0.18, 0.14, 0.09, r, "stone", segs=5, rings=3))
        nodes.append(Node("chips", chips, "solid"))
    else:
        b = 0.5 if kind == "border" else 0.0
        m = grid_floor(stations(-hx, hx, 2.0, (-hx + b, hx - b) if b else ()), stations(-hy, hy, 2.0, (-hy + b, hy - b) if b else ()),
                       lambda x, y: True, 0.0, (lambda x, y: "step" if b and (abs(x) > hx - b or abs(y) > hy - b) else "floor"))
    nodes.insert(0, Node("floor", m, "shell"))
    socks = [sock("floor", (0, 0, 0), "up", cells=[P["cells_x"], P["cells_y"]])]
    return Asset(nodes, grid_meta("cell_block_centre", (P["cells_x"], P["cells_y"]), socks, kind=kind))


# ---------------------------------------------------------------- dgn.doorway
@register("dgn.doorway", V, "arch", {
    "style": S.enum("frame", ["frame", "arch"]),
    "passage": S.boolean(True, "short dark passage sleeve behind the frame (doorways lead into darkness)"),
    "keystone": S.boolean(True),
}, "Round-arched stone doorway. frame: fills a 3 x 3.6 m wall cut (2 x 3 m opening), back face on the room.gd door "
   "anchor, optional 1.5 m passage sleeve receding into the dark. arch: freestanding arch on two piers spanning a "
   "3 m corridor.", origin="opening_floor")
def doorway(P, seed):
    nodes = []
    if P["style"] == "frame":
        ow, oh = D.DOOR_W, D.DOOR_H
        r = ow / 2
        spring = oh - r
        out = [(-CUT_W / 2, 0.0), (-r, 0.0), (-r, spring)]
        for i in range(1, 8):
            a = math.pi - math.pi * i / 8
            out.append((r * math.cos(a), spring + r * math.sin(a)))
        out += [(r, spring), (r, 0.0), (CUT_W / 2, 0.0), (CUT_W / 2, CUT_H), (-CUT_W / 2, CUT_H)]
        fr = K.prism(out, 0.0, FRAME_D, "frame").rotate_x(math.pi / 2)
        nodes.append(Node("frame", fr, "solid"))
        det = K.Mesh()
        if P["keystone"]:
            ks = [(-0.22, oh - 0.12), (0.22, oh - 0.12), (0.3, oh + 0.42), (-0.3, oh + 0.42)]
            det.merge(K.prism(ks, FRAME_D - 0.02, FRAME_D + 0.08, "trim").rotate_x(math.pi / 2))
        # threshold slab
        det.merge(D.bevel_box(0, -FRAME_D / 2, 0.0, ow + 0.1, FRAME_D - 0.04, 0.05, "step", bevel=0.02))
        # impost blocks at the springing line (painted carving reads at N64 resolution)
        for sx in (-1, 1):
            det.merge(D.bevel_box(sx * (r + 0.2), -FRAME_D - 0.04, spring - 0.12, 0.5, 0.12, 0.24, "trim", bevel=0.03))
        nodes.append(Node("detail", det, "solid"))
        socks = [sock("door", (0, 0, 0), "s", width_m=ow, height_m=oh, fills_cut_m=[CUT_W, CUT_H], depth_m=FRAME_D)]
        if P["passage"]:
            L = 1.6
            pm = K.Mesh()
            hw = r
            # floor, side walls and barrel head of a short sleeve behind the frame, all facing inward
            pm.merge(grid_floor([-hw, 0.0, hw], [0.0, L / 2, L], lambda x, y: True, 0.0, "floor"))
            for sx in (-1, 1):
                q = K.Mesh().add([(sx * hw, 0, 0), (sx * hw, L, 0), (sx * hw, L, spring), (sx * hw, 0, spring)], [(0, 1, 2, 3)], "wall", False)
                if sx > 0:
                    q.flip()
                pm.merge(q)
            vault = K.Mesh()
            for i in range(8):
                a0, a1 = math.pi * i / 8, math.pi * (i + 1) / 8
                p0 = (hw * math.cos(a0), spring + hw * math.sin(a0))
                p1 = (hw * math.cos(a1), spring + hw * math.sin(a1))
                vault.add([(p0[0], 0, p0[1]), (p1[0], 0, p1[1]), (p1[0], L, p1[1]), (p0[0], L, p0[1])], [(0, 1, 2, 3)], "ceiling", False)
            pm.merge(vault)
            nodes.append(Node("passage", D.weld_mesh(pm), "shell"))
            # the sleeve ends in the void colour (N64 doorways lead into darkness, never into uncovered background)
            end = K.Mesh().add([(-hw, L, 0.0), (hw, L, 0.0), (hw, L, oh), (-hw, L, oh)], [(0, 1, 2, 3)], "opening", False)
            nodes.append(Node("dark", end, "card"))
        meta = grid_meta("door_anchor", None, socks, note="origin = room.gd door anchor (0.4 m in from the room edge, "
                         "0.1 m behind the cell boundary); frame back face at the anchor, front 0.15 m proud of the wall")
    else:
        span, h, pd = 3.0, 3.9, 0.64
        r = span / 2
        spring = h - r
        piers = K.Mesh()
        for sx in (-1, 1):
            piers.merge(pier(sx * (r + 0.36), 0.0, 0.7, spring + 0.1, "frame", "trim", "stone", capital=False))
        ro, ri = r + 0.62, r
        poly = [(ri, spring), (ro, spring)]
        for i in range(1, 8):
            a = math.pi * i / 8
            poly.append((ro * math.cos(a), spring + ro * math.sin(a)))
        poly += [(-ro, spring), (-ri, spring)]
        for i in range(7, 0, -1):
            a = math.pi * i / 8
            poly.append((ri * math.cos(a), spring + ri * math.sin(a)))
        head = K.prism(poly, -pd / 2, pd / 2, "frame").rotate_x(math.pi / 2)
        nodes.append(Node("piers", piers, "solid"))
        nodes.append(Node("head", head, "solid"))
        if P["keystone"]:
            ks = [(-0.24, h - 0.08), (0.24, h - 0.08), (0.32, h + 0.55), (-0.32, h + 0.55)]
            nodes.append(Node("keystone", K.prism(ks, -pd / 2 - 0.06, pd / 2 + 0.06, "trim").rotate_x(math.pi / 2), "solid"))
        socks = [sock("corridor", (0, 0, 0), "s", width_m=span), sock("corridor", (0, 0, 0), "n", width_m=span)]
        meta = grid_meta("cell_edge", None, socks, note="freestanding arch centred on a cell boundary across a 3 m passage")
    return Asset(nodes, meta)


# ---------------------------------------------------------------- dgn.door_locked
@register("dgn.door_locked", V, "arch", {
    "lock": S.enum("padlock", ["padlock", "bars"]),
    "state": S.enum("closed", ["closed", "open"]),
}, "Locked door insert for a dgn.doorway frame (same door anchor). padlock: iron-banded timber leaf with crossed "
   "chains and a heavy padlock; open = leaf swung back into the passage, chains gone. bars: iron gate bars; open = "
   "bars withdrawn (only the sockets remain). Swap closed/open by flag (presentation piece flag / asset_when_set). "
   "Origin = the door anchor of the frame it fills.", origin="opening")
def door_locked(P, seed):
    ow, oh = D.DOOR_W, D.DOOR_H
    r = ow / 2
    spring = oh - r
    ymid = -FRAME_D / 2
    nodes = []
    if P["lock"] == "padlock":
        leaf_o = [(-r + 0.03, 0.0), (r - 0.03, 0.0), (r - 0.03, spring)]
        for i in range(1, 8):
            a = math.pi * i / 8
            leaf_o.append(((r - 0.03) * math.cos(a), spring + (r - 0.03) * math.sin(a)))
        leaf_o.append((-r + 0.03, spring))
        leaf = K.prism(leaf_o, -0.07, 0.07, "door").rotate_x(math.pi / 2)
        bands = K.Mesh()
        for z in (0.55, 1.6, 2.45):
            bands.merge(K.box(0, -0.085, z, ow - 0.14, 0.035, 0.13, "metal"))
        ring = K.torus(0.11, 0.025, 6, 3, "metal").rotate_x(math.pi / 2).translate(0.55, -0.11, 1.25)
        if P["state"] == "closed":
            leaf.translate(0, ymid, 0)
            bands.translate(0, ymid, 0)
            ring.translate(0, ymid, 0)
            nodes += [Node("leaf", leaf, "solid"), Node("bands", bands, "solid"), Node("ring", ring, "solid")]
            ch = K.Mesh()
            for sgn in (-1, 1):
                p0 = np.array([-0.88 * sgn, ymid - 0.2, 0.5])
                p1 = np.array([0.88 * sgn, ymid - 0.2, 2.3])
                path = [tuple(p0 + (p1 - p0) * t + np.array([0, -0.04 * math.sin(math.pi * t), -0.12 * math.sin(math.pi * t)]))
                        for t in (0.0, 0.33, 0.66, 1.0)]
                ch.merge(K.tube(path, 0.045, 4, "metal", smooth=False, twist=math.pi / 4))
            nodes.append(Node("chains", ch, "solid"))
            lock = K.Mesh()
            lock.merge(D.bevel_box(0, ymid - 0.32, 1.12, 0.42, 0.16, 0.38, "metal", bevel=0.05))
            lock.merge(K.torus(0.14, 0.035, 8, 3, "metal").rotate_x(math.pi / 2).translate(0, ymid - 0.32, 1.56))
            lock.merge(K.box(0, ymid - 0.41, 1.25, 0.08, 0.02, 0.12, "opening"))
            nodes.append(Node("padlock", lock, "solid"))
        else:
            g = K.Mesh().merge(leaf, bands, ring)
            g.translate(r - 0.03, 0, 0)              # hinge on the left jamb at x = -r
            g.rotate_z(math.radians(95))
            g.translate(-r + 0.02, ymid + 0.06, 0)
            nodes.append(Node("leaf", g, "solid"))
    else:
        bars = K.Mesh()
        n = 7
        for i in range(n):
            x = -r + 0.18 + i * (ow - 0.36) / (n - 1)
            top = spring + math.sqrt(max(0.0, r * r - x * x)) - 0.05
            if P["state"] == "closed":
                bars.merge(K.box(x, ymid, top / 2, 0.08, 0.08, top, "metal"))
            bars.merge(K.box(x, ymid, 0.015, 0.15, 0.15, 0.03, "trim"))
        if P["state"] == "closed":
            for z in (0.9, 2.1):
                bars.merge(K.box(0, ymid, z, ow - 0.25, 0.1, 0.1, "metal"))
        nodes.append(Node("bars", bars, "solid"))
    socks = [sock("door_insert", (0, 0, 0), "s", fits="dgn.doorway", state=P["state"])]
    return Asset(nodes, grid_meta("door_anchor", None, socks, lock=P["lock"], state=P["state"]))


# ---------------------------------------------------------------- dgn.stairs
@register("dgn.stairs", V, "structure", {
    "direction": S.enum("up", ["up", "down"]),
    "steps": S.lod(S.integer(9, 6, 12)),
}, "Stair cell against a wall (4 x 4 m). up: a flight rising 2.25 m to a dark arched landing portal in the back "
   "wall (the piece replaces the wall segment on its north edge). down: a stairwell sinking into the dark with low "
   "parapets on both sides.", origin="terrain_center")
def stairs(P, seed):
    e, h = D.CELL / 2, D.CELL / 2 - D.WALL_T
    n = P["steps"]
    rise = 2.25
    nodes = []
    if P["direction"] == "up":
        run = 3.2
        front = -e + 0.3
        back = front + run                       # = e - WALL_T: the landing meets the back wall face
        st = K.Mesh()
        for i in range(n):
            y0 = front + run * i / n
            d_ = run / n + (0.03 if i < n - 1 else 0.0)        # overlap the next step: no coincident corners
            st.merge(K.box(0, y0 + d_ / 2, rise * (i + 1) / n / 2, 2.64, d_, rise * (i + 1) / n, "step"))
        nodes.append(Node("steps", st, "solid"))
        nodes.append(Node("floor", grid_floor([-e, -1.0, 1.0, e], [-e, front, 0.0, e - D.WALL_T], lambda x, y: True, 0.0,
                                              "floor"), "shell"))
        lw = K.Mesh()
        o = [(front, 0.0), (back, 0.0), (back, rise + 0.6), (front, 0.75)]
        for x0 in (1.3, -1.62):
            lw.merge(K.prism(o, 0.0, 0.32, "stone").rotate_x(math.pi / 2).rotate_z(math.pi / 2).translate(x0, 0, 0))
        nodes.append(Node("cheeks", lw, "solid"))
        # back wall above the landing with a dark portal
        sheet = D.wall_sheet(D.CELL, openings=[(2.0 - 0.9, 2.0 + 0.9, rise + 2.4, rise)]).translate(-2.0, e - D.WALL_T, 0)
        nodes.append(Node("wall", sheet, "shell"))
        port = K.Mesh().add([(-0.9, e - D.WALL_T + 0.3, rise), (0.9, e - D.WALL_T + 0.3, rise), (0.9, e - D.WALL_T + 0.3, rise + 2.4),
                             (-0.9, e - D.WALL_T + 0.3, rise + 2.4)], [(0, 1, 2, 3)], "opening", False)
        nodes.append(Node("portal", port, "card"))
        ring_o = [(-1.15, rise - 0.05), (1.15, rise - 0.05), (1.15, rise + 2.65), (-1.15, rise + 2.65)]
        ring_i = [(-0.9, rise), (0.9, rise), (0.9, rise + 2.4), (-0.9, rise + 2.4)]
        nodes.append(Node("portal_frame", K.prism(ring_o, 0.0, 0.42, "frame", holes=[ring_i]).rotate_x(math.pi / 2)
                          .translate(0, e - D.WALL_T + 0.3, 0), "solid"))
        socks = [sock("wall", (0, e, 0), "n", replaces="dgn.wall"), sock("stairs_up", (0, rise, e - D.WALL_T), "n")]
    else:
        well_w, run = 2.4, 3.0
        fm = grid_floor([-e, -well_w / 2, well_w / 2, e], [-e, -run / 2, run / 2, e],
                        lambda x, y: not (abs(x) < well_w / 2 and abs(y) < run / 2), 0.0, "floor")
        nodes.append(Node("floor", fm, "shell"))
        depth = 2.6
        wm = K.Mesh()
        x0, x1, y0, y1 = -well_w / 2, well_w / 2, -run / 2, run / 2
        for q in ([(x0, y0, 0), (x0, y0, -depth), (x0, y1, -depth), (x0, y1, 0)],
                  [(x1, y0, -depth), (x1, y0, 0), (x1, y1, 0), (x1, y1, -depth)],
                  [(x0, y1, 0), (x0, y1, -depth), (x1, y1, -depth), (x1, y1, 0)]):
            wm.add(q, [(0, 1, 2, 3)], "wall", False)
        wm = D.weld_mesh(wm)
        nodes.append(Node("well", wm, "shell"))
        st = K.Mesh()
        for i in range(n):
            y = y0 + run * i / n
            ztop = -depth * (i + 1) / n
            d_ = run / n + (0.03 if i < n - 1 else 0.0)
            st.merge(K.box(0, y + d_ / 2, ztop - 0.15, well_w + 0.04, d_, 0.3, "step"))
        nodes.append(Node("steps", st, "solid"))
        dark = K.Mesh().add([(x0, y0 - 0.0, -depth), (x1, y0, -depth), (x1, y1, -depth), (x0, y1, -depth)], [(0, 1, 2, 3)], "opening", False)
        nodes.append(Node("void", dark, "card"))
        par = K.Mesh()
        for sx in (-1, 1):
            par.merge(D.bevel_box(sx * (well_w / 2 + 0.2), 0, 0, 0.38, run + 0.4, 0.75, "trim", bevel=0.05))
        par.merge(D.bevel_box(0, y1 + 0.2, 0, well_w + 0.78, 0.38, 0.75, "trim", bevel=0.05))
        nodes.append(Node("parapet", par, "solid"))
        socks = [sock("floor", (0, 0, 0), "up"), sock("stairs_down", (0, -depth, -y0), "s")]
    return Asset(nodes, grid_meta("cell_centre", (1, 1), socks, direction=P["direction"]))


# ---------------------------------------------------------------- dgn.pillar
@register("dgn.pillar", V, "structure", {
    "style": S.enum("square", ["square", "round", "broken"]),
    "height": S.num(4.5, 2.0, 6.0),
}, "Free-standing dungeon pillar: square (chamfered shaft, base course, capital), round (tapered drum shaft on a "
   "square plinth) or broken (stump with fallen drums).", origin="floor_center")
def pillar(P, seed):
    h = P["height"]
    st = P["style"]
    nodes = []
    if st == "square":
        nodes.append(Node("pillar", pier(0, 0, 0.8, h, "trim", "frame", "stone"), "solid"))
    elif st == "round":
        m = K.Mesh()
        m.merge(D.bevel_box(0, 0, 0, 1.15, 1.15, 0.45, "stone", bevel=0.06))
        prof = [(0.0, 0.45), (0.46, 0.45), (0.46, 0.62), (0.4, 0.7), (0.36, h - 0.7), (0.42, h - 0.62), (0.5, h - 0.5), (0.0, h - 0.5)]
        m.merge(K.lathe(prof, 10, "trim", smooth=True))
        m.merge(D.bevel_box(0, 0, h - 0.5, 1.15, 1.15, 0.5, "frame", bevel=0.06))
        nodes.append(Node("pillar", m, "solid"))
    else:
        r = rng(seed, "dgn.pillar", "broken")
        m = K.Mesh()
        m.merge(D.bevel_box(0, 0, 0, 1.15, 1.15, 0.45, "stone", bevel=0.06))
        top = 1.2 + 0.5 * r.random()
        ring = []
        for i in range(10):
            a = 2 * math.pi * i / 10
            ring.append((0.36 * math.cos(a), 0.36 * math.sin(a), top + 0.25 * (r.random() - 0.5)))
        base = [(0.4 * math.cos(2 * math.pi * i / 10), 0.4 * math.sin(2 * math.pi * i / 10), 0.45) for i in range(10)]
        m.merge(K.loft([base, ring], "trim", smooth=True))
        nodes.append(Node("stump", m, "solid"))
        dr = K.Mesh()
        for k in range(2):
            d = K.cylinder(0, 0, -0.33, 0.36, 0.66, 10, "trim").rotate_x(math.pi / 2)
            d.rotate_z(r.uniform(0, math.pi)).translate(r.uniform(0.9, 1.3) * (1 if k else -1), r.uniform(-0.7, 0.7), 0.36)
            dr.merge(d)
        dr.merge(D.rock_blob(0.4, 0.75, 0.12, 0.25, 0.2, 0.16, r, "stone"))
        nodes.append(Node("drums", dr, "solid"))
    from .genutil import finalize
    a = finalize(nodes, grid_meta("free", None, [sock("pillar", (0, 0, 0), "up", footprint_m=1.15)], style=st))
    return a


# ---------------------------------------------------------------- dgn.pit
@register("dgn.pit", V, "shell", {
    "kind": S.enum("full", ["full", "edge", "corner"]),
    "depth": S.num(3.0, 1.5, 6.0),
}, "Pit cell: floor with a hole whose shaft walls fall into the dark (one-sided, void at the bottom), dressed rim "
   "stones. full: the whole cell is pit inside a rim; edge: the north half; corner: the north-east quarter.",
   origin="terrain_center")
def pit(P, seed):
    e = D.CELL / 2
    d = P["depth"]
    rim = 0.35
    if P["kind"] == "full":
        hx0, hx1, hy0, hy1 = -e + rim, e - rim, -e + rim, e - rim
    elif P["kind"] == "edge":
        hx0, hx1, hy0, hy1 = -e, e, 0.0 + rim, e
    else:
        hx0, hx1, hy0, hy1 = 0.0 + rim, e, 0.0 + rim, e
    xs = stations(-e, e, 2.0, (hx0, hx1))
    ys = stations(-e, e, 2.0, (hy0, hy1))
    inside_hole = lambda x, y: hx0 < x < hx1 and hy0 < y < hy1
    fm = grid_floor(xs, ys, lambda x, y: not inside_hole(x, y), 0.0, "floor")
    nodes = [Node("floor", fm, "shell")]
    sh = K.Mesh()
    edges = []
    if hy0 > -e + 1e-6:
        edges.append(((hx0, hy0), (hx1, hy0)))
    if hx1 < e - 1e-6:
        edges.append(((hx1, hy0), (hx1, hy1)))
    if hy1 < e - 1e-6:
        edges.append(((hx1, hy1), (hx0, hy1)))
    if hx0 > -e + 1e-6:
        edges.append(((hx0, hy1), (hx0, hy0)))
    for (ax, ay), (bx, by) in edges:
        # shaft wall facing into the hole: walking CCW around the hole, the inside is on the left
        sh.add([(ax, ay, 0.0), (bx, by, 0.0), (bx, by, -d), (ax, ay, -d)], [(0, 1, 2, 3)], "wall", False)
    sh = D.weld_mesh(sh)
    nodes.append(Node("shaft", sh, "shell"))
    void = K.Mesh().add([(hx0, hy0, -d), (hx1, hy0, -d), (hx1, hy1, -d), (hx0, hy1, -d)], [(0, 1, 2, 3)], "opening", False)
    nodes.append(Node("void", void, "card"))
    rm = K.Mesh()
    for (ax, ay), (bx, by) in edges:
        L = math.hypot(bx - ax, by - ay)
        k = max(1, int(round(L / 1.0)))
        for i in range(k):
            t0, t1 = (i + 0.06) / k, (i + 0.94) / k
            cx, cy = ax + (bx - ax) * 0.5 * (t0 + t1), ay + (by - ay) * 0.5 * (t0 + t1)
            nx, ny = -(by - ay) / L, (bx - ax) / L          # into the hole
            ox, oy = cx - nx * 0.18, cy - ny * 0.18
            sx = abs(bx - ax) * (t1 - t0) + abs(nx) * 0.36
            sy = abs(by - ay) * (t1 - t0) + abs(ny) * 0.36
            rm.merge(D.bevel_box(ox, oy, -0.02, sx, sy, 0.12, "trim", bevel=0.03))
    nodes.append(Node("rim", rm, "solid"))
    socks = [sock("floor", (0, 0, 0), "up"), sock("pit", ((hx0 + hx1) / 2, (hy0 + hy1) / 2, 0), "up",
                                                 hole_m=[round(hx1 - hx0, 3), round(hy1 - hy0, 3)], bridgeable=P["kind"] == "full")]
    return Asset(nodes, grid_meta("cell_centre", (1, 1), socks, kind=P["kind"], depth_m=d))


# ---------------------------------------------------------------- dgn.bridge
@register("dgn.bridge", V, "structure", {
    "span_cells": S.integer(1, 1, 2), "width": S.num(1.6, 1.0, 2.6), "parapet": S.boolean(True),
}, "Narrow stone slab bridge across pit cells (north-south), resting on the rims, with a deep keel and low "
   "parapets; spans 1-2 cells. Origin on the deck top at floor level (the keel hangs below the floor).",
   origin="opening")
def bridge(P, seed):
    L = D.CELL * P["span_cells"]
    w = P["width"]
    m = K.Mesh()
    m.merge(D.bevel_box(0, 0, -0.45, w, L, 0.47, "step", bevel=0.05, top_role="step"))
    m.merge(D.bevel_box(0, 0, -1.05, w * 0.55, L - 1.2, 0.62, "stone", bevel=0.08))
    nodes = [Node("deck", m, "solid")]
    if P["parapet"]:
        p = K.Mesh()
        for sx in (-1, 1):
            p.merge(D.bevel_box(sx * (w / 2 - 0.1), 0, 0.02, 0.2, L - 0.3, 0.42, "trim", bevel=0.04))
            for k in range(int(L // 2) + 1):
                p.merge(K.box(sx * (w / 2 - 0.1), -L / 2 + 0.3 + (L - 0.6) * k / max(1, int(L // 2)), 0.3, 0.28, 0.28, 0.6, "frame"))
        nodes.append(Node("parapet", p, "solid"))
    return Asset(nodes, grid_meta("deck_top_centre", (1, P["span_cells"]),
                                  [sock("walk", (0, -L / 2, 0), "s"), sock("walk", (0, L / 2, 0), "n")]))


# ---------------------------------------------------------------- dgn.ceiling
@register("dgn.ceiling", V, "shell", {
    "style": S.enum("vault", ["vault", "flat", "groin"]),
    "cells_x": S.integer(1, 1, 5), "cells_y": S.integer(1, 1, 5),
}, "Ceiling over a cell block, one-sided facing down (cameras above see into the room: N64 cutaway). vault: barrel "
   "vault along north-south springing at the cornice; flat: slab with timber beams; groin: cross vault per cell with "
   "ribs and a boss. Origin at floor level on the cell block centre (geometry at the storey height).", origin="opening")
def ceiling(P, seed):
    hx, hy = P["cells_x"] * D.CELL / 2 - D.WALL_T, P["cells_y"] * D.CELL / 2 - D.WALL_T
    nodes = []
    if P["style"] == "flat":
        nodes.append(Node("ceiling", grid_floor(stations(-hx, hx, 2.0), stations(-hy, hy, 2.0), lambda x, y: True, D.H, "ceiling", flip=True), "shell"))
        ys = [D.CELL * k - P["cells_y"] * D.CELL / 2 for k in range(1, P["cells_y"])] or [0.0]
        nodes.append(Node("beams", beams(-hx, hx, ys, D.H, "wood"), "solid"))
    elif P["style"] == "vault":
        v = D.barrel_vault(2 * hy, 2 * hx, D.H, min(1.8, hx), segs=8, role="ceiling", step=2.0)
        nodes.append(Node("vault", v, "shell"))
        ends = K.Mesh()
        for sy in (-1, 1):
            pts = [(0.0, D.H)] + [(-hx * math.cos(math.pi * i / 8), D.H + min(1.8, hx) * math.sin(math.pi * i / 8)) for i in range(9)]
            fan = K.Mesh()
            ring = [(x, sy * hy, z) for x, z in pts[1:]]
            c = (0.0, sy * hy, D.H)
            for i in range(8):
                fan.add([c, ring[i], ring[i + 1]], [(0, 1, 2)], "wall", False)
            if sy > 0:
                fan.flip()
            ends.merge(fan)
        nodes.append(Node("tympana", D.weld_mesh(ends), "shell"))
        ribs = K.Mesh()
        for k in range(P["cells_y"] + 1):
            y = -hy + (2 * hy) * k / P["cells_y"]
            y = max(-hy + 0.2, min(hy - 0.2, y))
            path = [(-hx * math.cos(math.pi * i / 8) * 0.97, y, D.H + min(1.8, hx) * math.sin(math.pi * i / 8) * 0.97 - 0.02) for i in range(9)]
            ribs.merge(K.tube(path, 0.12, 4, "trim", smooth=False))
        nodes.append(Node("ribs", ribs, "solid"))
    else:
        m = K.Mesh()
        rise = 1.4
        for i in range(P["cells_x"]):
            for j in range(P["cells_y"]):
                cx = -P["cells_x"] * D.CELL / 2 + D.CELL * (i + 0.5)
                cy = -P["cells_y"] * D.CELL / 2 + D.CELL * (j + 0.5)
                ex = min(D.CELL / 2, hx - abs(cx) + D.CELL / 2) if P["cells_x"] == 1 else D.CELL / 2
                ex = hx if P["cells_x"] == 1 else D.CELL / 2
                ey = hy if P["cells_y"] == 1 else D.CELL / 2
                apex = (cx, cy, D.H + rise)
                cs = [(cx - ex, cy - ey), (cx + ex, cy - ey), (cx + ex, cy + ey), (cx - ex, cy + ey)]
                for a in range(4):
                    (x0, y0), (x1, y1) = cs[a], cs[(a + 1) % 4]
                    xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
                    mid = (xm, ym, D.H + rise * 0.75)
                    m.add([(x0, y0, D.H), (x1, y1, D.H), apex], [(0, 1, 2)], "ceiling", True)
        m = D.weld_mesh(m).flip()
        nodes.append(Node("groin", m, "shell"))
        boss = K.Mesh()
        for i in range(P["cells_x"]):
            for j in range(P["cells_y"]):
                cx = -P["cells_x"] * D.CELL / 2 + D.CELL * (i + 0.5)
                cy = -P["cells_y"] * D.CELL / 2 + D.CELL * (j + 0.5)
                boss.merge(K.sphere(cx, cy, D.H + rise - 0.1, 0.22, 0.22, 0.18, 6, 4, "trim", smooth=True))
        nodes.append(Node("boss", boss, "solid"))
    return Asset(nodes, grid_meta("cell_block_centre", (P["cells_x"], P["cells_y"]), [sock("ceiling", (0, 0, D.H), "down")],
                                  style=P["style"]))


# ---------------------------------------------------------------- dgn.rubble
@register("dgn.rubble", V, "furniture_large", {
    "size": S.num(1.0, 0.5, 1.6), "blocks": S.integer(3, 0, 4), "stones": S.integer(5, 2, 8),
}, "Rubble heap: rounded faceted stones around a few broken cut blocks (fallen masonry).", origin="floor_center")
def rubble(P, seed):
    r = rng(seed, "dgn.rubble")
    s = P["size"]
    m = K.Mesh()
    m.merge(D.rock_blob(0, 0, 0.12 * s, 0.75 * s, 0.6 * s, 0.32 * s, r, "stone", segs=8, rings=4, jitter=0.2))
    for k in range(P["stones"]):
        a = 2 * math.pi * k / P["stones"] + r.uniform(-0.3, 0.3)
        d = r.uniform(0.55, 1.1) * s
        rr = r.uniform(0.12, 0.26) * s
        m.merge(D.rock_blob(d * math.cos(a), d * math.sin(a), rr * 0.5, rr, rr * 0.8, rr * 0.6, r, "stone", segs=5, rings=3))
    bl = K.Mesh()
    for k in range(P["blocks"]):
        a = r.uniform(0, 2 * math.pi)
        d = r.uniform(0.2, 0.7) * s
        b = D.bevel_box(0, 0, 0, 0.62 * s, 0.4 * s, 0.34 * s, "wall", bevel=0.05)
        b.rotate_y(r.uniform(-0.5, 0.5)).rotate_z(r.uniform(0, math.pi))
        bl.merge(b.translate(d * math.cos(a), d * math.sin(a), 0.1 * s + 0.15 * s * r.random()))
    from .genutil import finalize
    nodes = [Node("stones", m), Node("blocks", bl)]
    return finalize(nodes, grid_meta("free", None, [sock("prop", (0, 0, 0), "up")]))
