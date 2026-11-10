"""SCIFIKIT station architecture (stn.*): corridors, bulkhead doorways, airlock leaves (closed / open), room shells,
ceilings, the bridge / cockpit shell, the hangar bay, deck floors (plain / hex / grate / pad), bulkhead frames,
viewport windows, a lift and stairs / ramps / dais. All snap to the STATION GRID (kits/core/sfkit.py, docs/SCIFIKIT.md).

Original designs: chamfered octagonal corridor sections, mitred one-sided wall shells with a recessed light band,
tapered ribs, zig-zag sealed airlock leaves. Nothing is a plain box (the cuboid gate checks it)."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from . import sfkit as F
from .asset import Asset, Node, register

V = "1.0.0"
SIDES = ("n", "s", "e", "w")
OPEN_SIDES = {"straight": "ns", "corner": "ne", "tee": "nes", "cross": "nesw", "end": "s", "end_door": "s"}


def _asset(nodes, meta, ao=0.3, reach=1.1, ground=False):
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    F.bake_ao(nodes, amount=ao, reach=reach, ground=ground)
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for n in nodes:
        a = np.asarray(n.mesh.v)
        lo, hi = np.minimum(lo, a.min(0)), np.maximum(hi, a.max(0))
    meta = dict(meta)
    meta["bbox_size_m"] = [round(float(x), 4) for x in (hi - lo)]
    return Asset(nodes, meta)


def _corr_rib(width=0.26, d_end=0.14, d_mid=0.07, role="trim", y=0.0, half=1.5, profile=F.CORR_PROFILE, h=F.H_CORR):
    """U-frame following a wall profile across the ceiling (right floor -> up -> across -> down -> left floor)."""
    right = [(half - d, z) for d, z, _ in profile]
    left = [(-half + d, z) for d, z, _ in reversed(profile)]
    path = right + left
    clean = [path[0]]
    for p in path[1:]:
        if abs(p[0] - clean[-1][0]) + abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    return F.taper_rib(clean, d_end, d_end, y - width / 2, y + width / 2, role, sink=0.02, depth_mid=d_mid)


# ------------------------------------------------------------------ corridor
def _corr_chains(shape):
    h, b = F.CORR_W / 2, F.CELL / 2
    if shape == "straight":
        return [[(-h, b), (-h, -b)], [(h, -b), (h, b)]]
    if shape == "corner":
        return [[(-h, b), (-h, -h), (b, -h)], [(b, h), (h, h), (h, b)]]
    if shape == "tee":
        return [[(-h, b), (-h, -b)], [(b, h), (h, h), (h, b)], [(h, -b), (h, -h), (b, -h)]]
    if shape == "cross":
        return [[(b, h), (h, h), (h, b)], [(-h, b), (-h, h), (-b, h)], [(-b, -h), (-h, -h), (-h, -b)],
                [(h, -b), (h, -h), (b, -h)]]
    # end / end_door: side walls stop on the flat end bulkhead wall at y = +h
    return [[(-h, h), (-h, -b)], [(h, -b), (h, h)]]


@register("stn.corridor", V, "structure", {
    "shape": S.enum("straight", list(OPEN_SIDES), "open sides: straight N+S, corner N+E, tee N+E+S, cross all, end S "
                    "(flat end bulkhead), end_door S (end bulkhead with a 2.0 x 2.6 door cut on the north socket)"),
    "rib": S.boolean(True, "tapered frame rib across the corridor at the cell centre (straight only)"),
    "light_band": S.boolean(True, "recessed light band in the wall profile (off: plain panel band)"),
    "wall_div": S.lod(S.integer(4, 2, 6)),
}, "Station corridor cell (4 m, 3 m clear, 3.2 m high): chamfered octagonal section, mitred one-sided walls with a "
   "recessed light band, floor and ceiling sheets, cap ledges for the cutaway; corridor sockets on open cell-edge "
   "midpoints.", origin="floor_center")
def corridor(P, seed):
    shape = P["shape"]
    prof = list(F.CORR_PROFILE)
    if not P["light_band"]:
        prof = [(d, z, ("wall" if r == "light" else r)) for d, z, r in prof]
    chains = _corr_chains(shape)
    seg = F.CELL / P["wall_div"]
    walls = F.merged(*[F.wall_chain(c, False, prof, seg_len=seg, cap=F.H_CORR + 0.01) for c in chains])
    nodes = [Node("walls", F.weld_mesh(walls), "shell")]
    h, b = F.CORR_W / 2, F.CELL / 2
    if shape in ("end", "end_door"):
        holes = [(-F.DOOR_W / 2, F.DOOR_W / 2, 0.0, F.DOOR_H)] if shape == "end_door" else []
        nodes.append(Node("end_wall", _flat_wall(-h, h, h, F.H_CORR, holes), "shell"))
        nodes.append(Node("end_frame", _end_frame(h), "solid"))
    nodes.append(Node("floor", F.floor_grid(-b, b, -b, b, 0.0, 4, 4, "floor", up=True), "shell"))
    nodes.append(Node("ceiling", F.floor_grid(-b, b, -b, b, F.H_CORR, 2, 2, "ceiling", up=False), "shell"))
    if shape == "straight" and P["rib"]:
        nodes.append(Node("rib", _corr_rib(), "solid"))
    sockets = []
    for side in OPEN_SIDES[shape]:
        x, y = {"n": (0.0, b), "s": (0.0, -b), "e": (b, 0.0), "w": (-b, 0.0)}[side]
        sockets.append(F.socket("corridor", x, y, 0.0, side, width_m=F.CORR_W, side=side))
    if shape == "end_door":
        sockets.append(F.socket("door", 0.0, h + F.ANCHOR_BACK, 0.0, "n", width_m=F.DOOR_W, side="n"))
    meta = {"shape": shape, "sockets": sockets, "open_sides": OPEN_SIDES[shape]}
    meta.update(F.grid_meta("cell_centre", (1, 1)))
    return _asset(nodes, meta)


def _flat_wall(x0, x1, y, h, holes=(), role="wall_alt", trim_z=(0.42, 2.28, 2.44)):
    """Flat one-sided end wall facing -Y at y, from x0 to x1, z 0..h, with rectangular holes (x0, x1, z0, z1)."""
    xs = sorted(set([x0, x1] + [v for hh in holes for v in hh[:2]] + [x0 + (x1 - x0) * i / 3 for i in range(1, 3)]))
    zs = sorted(set([0.0, h] + [v for hh in holes for v in hh[2:]] + list(trim_z)))
    verts = [(x, y, z) for z in zs for x in xs]
    faces, roles = [], []
    nx = len(xs)
    for j in range(len(zs) - 1):
        for i in range(nx - 1):
            cx, cz = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            if any(hh[0] <= cx <= hh[1] and hh[2] <= cz <= hh[3] for hh in holes):
                continue
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))   # normal -Y (toward the corridor)
            roles.append("light" if trim_z[1] <= cz <= trim_z[2] else ("wall" if trim_z[0] <= cz <= trim_z[1] else role))
    return K.Mesh().add(verts, faces, roles, False)


def _end_frame(h):
    """Bulkhead frame ring on the flat end wall (closed solid), following the corridor section."""
    prof = F.CORR_PROFILE
    pts_r = [(h - d, z) for d, z, _ in prof]
    outer = pts_r + [(-x, z) for x, z in reversed(pts_r)]
    inner = [(x * 0.86, 0.12 + z * 0.9) for x, z in outer]
    return F.frame_ring(outer, inner, h - 0.14, h - 0.01, "trim")


# ------------------------------------------------------------------ doorway + airlock
def _door_frame_parts(w=F.DOOR_W, hgt=F.DOOR_H, role="frame", lip="band"):
    """Chamfered inverted-U frame through the wall slab + a hazard lip proud of the inner face (no sill: the deck runs
    through)."""
    frame = F.extrude_xz(F.arch_frame(w, hgt, w + 0.9, hgt + 0.5, 0.22, 0.42), -F.ANCHOR_BACK - 0.14, 0.04, role)
    lipm = F.extrude_xz(F.arch_frame(w - 0.02, hgt - 0.01, w + 0.3, hgt + 0.18, 0.21, 0.3),
                        -F.ANCHOR_BACK - 0.2, -F.ANCHOR_BACK - 0.13, lip)
    return frame, lipm


@register("stn.doorway", V, "arch", {
    "lights": S.boolean(True, "two status lights over the opening"),
    "beyond": S.enum("dark", ["dark", "lit"], "card behind the opening: dark passage or a lit corridor glimpse"),
}, "Bulkhead doorway frame for a 2.0 x 2.6 door cut: chamfered steel frame with a hazard lip, raised sill and a card "
   "behind the opening. Origin on the room.gd door anchor (0.6 m behind the inner wall face); room.gd places it on every "
   "door through the arch.door binding.", origin="opening_floor")
def doorway(P, seed):
    frame, lip = _door_frame_parts()
    nodes = [Node("frame", frame), Node("lip", lip)]
    w, hgt = F.DOOR_W, F.DOOR_H
    card = K.Mesh().add([(-w / 2 - 0.05, 0.02, 0.0), (w / 2 + 0.05, 0.02, 0.0), (w / 2 + 0.05, 0.02, hgt + 0.05),
                         (-w / 2 - 0.05, 0.02, hgt + 0.05)], [(0, 1, 2, 3)],
                        "opening" if P["beyond"] == "dark" else "light", False,
                        [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    nodes.append(Node("beyond", card, "card"))
    if P["lights"]:
        lm = F.merged(*[F.bevel_block(sx * 0.62, -F.ANCHOR_BACK - 0.2, hgt + 0.1, 0.22, 0.08, 0.1, "light", bevel=0.02)
                        for sx in (-1, 1)])
        nodes.append(Node("lights", lm))
    meta = {"sockets": [F.socket("door", 0.0, 0.0, 0.0, "s", width_m=w, height_m=hgt)], "cut_m": [w, hgt],
            "emitter": "door_lights" if P["lights"] else None}
    meta.update(F.grid_meta("door_anchor"))
    return _asset(nodes, meta, ao=0.25, reach=0.8)


def _leaf(x0, x1, seam, z0, z1, y0, y1, role):
    """Leaf outline from jamb x0 to the zig-zag seam (list of (x, z) bottom -> top), extruded y0..y1."""
    poly = [(x0, z0)] + [(x, z) for x, z in seam] + [(x0, z1)]
    return F.extrude_xz(poly if x0 < seam[0][0] else list(reversed(poly)), y0, y1, role)


@register("stn.airlock", V, "arch", {
    "state": S.enum("closed", ["closed", "open"], "closed: leaves meet on a zig-zag seal; open: leaves parked in the jambs"),
    "teeth": S.integer(3, 2, 5, "zig-zag teeth on the seal"),
}, "Airlock leaves for the 2.0 x 2.6 doorway cut (insert piece, flag-swapped closed -> open): two white leaves with a "
   "hazard-striped zig-zag seal and a round lock hub. Origin on the door anchor like stn.doorway.", origin="opening_floor")
def airlock(P, seed):
    w, hgt = F.DOOR_W, F.DOOR_H
    z0, z1 = 0.0, hgt - 0.01
    n = P["teeth"]
    amp = 0.13
    seam = []
    for i in range(2 * n + 1):
        z = z0 + (z1 - z0) * i / (2 * n)
        seam.append((amp if i % 2 else -amp, z))
    gap = 0.012
    off = 0.0 if P["state"] == "closed" else w / 2 - 0.12
    y0, y1 = -F.ANCHOR_BACK + 0.18, -F.ANCHOR_BACK + 0.32
    left_seam = [(x - gap - off, z) for x, z in seam]
    right_seam = [(x + gap + off, z) for x, z in seam]
    lx0, rx0 = -w / 2 - 0.08 - off, w / 2 + 0.08 + off
    left = F.extrude_xz([(lx0, z0)] + left_seam + [(lx0, z1)], y0, y1, "door")
    right = F.extrude_xz([(rx0, z1)] + list(reversed(right_seam)) + [(rx0, z0)], y0, y1, "door")
    nodes = [Node("leaf_l", left), Node("leaf_r", right)]
    # hazard bands just inside the seal on both leaves (thin raised strips)
    # hazard bands on the room face of both leaves, following the seal (thin raised strips just proud of the leaves)
    bl = F.extrude_xz([(x - 0.18 - gap - off, z) for x, z in seam] + list(reversed(left_seam)), y0 - 0.03, y0 - 0.002, "band")
    br = F.extrude_xz(right_seam + [(x + 0.18 + gap + off, z) for x, z in reversed(seam)], y0 - 0.03, y0 - 0.002, "band")
    nodes += [Node("seal_l", bl), Node("seal_r", br)]
    if P["state"] == "closed":
        hub = F.lathe([(0.0, 0.0), (0.34, 0.0), (0.36, 0.05), (0.3, 0.1), (0.12, 0.13), (0.0, 0.14)], 12, "trim",
                      smooth=False)
        hub.rotate_x(math.pi / 2).translate(0.0, y0 + 0.01, hgt * 0.52)
        nodes.append(Node("hub", hub))
    meta = {"state": P["state"], "sockets": [F.socket("door", 0.0, 0.0, 0.0, "s", width_m=w, height_m=hgt)],
            "insert_for": "stn.doorway"}
    meta.update(F.grid_meta("door_anchor"))
    return _asset(nodes, meta, ao=0.2, reach=0.6)


# ------------------------------------------------------------------ room shell + ceiling
def side_cell_station(side, cell, cx, cy):
    """(segment index, s centre) of side cell `cell` on a room's CCW wall loop (SW -> SE -> NE -> NW)."""
    W, D = cx * F.CELL, cy * F.CELL
    inn = F.WALL_T
    x0, x1, y0, y1 = -W / 2 + inn, W / 2 - inn, -D / 2 + inn, D / 2 - inn
    if side in ("n", "s"):
        x = -W / 2 + F.CELL * cell + F.CELL / 2
        return (0, x - x0) if side == "s" else (2, x1 - x)
    # e/w: plugin door index runs north -> south (glTF +z); Blender y = north
    y = D / 2 - F.CELL * cell - F.CELL / 2
    return (1, y - y0) if side == "e" else (3, y1 - y)


def anchor_xy(side, cell, cx, cy, back=F.ANCHOR_BACK):
    W, D = cx * F.CELL, cy * F.CELL
    inn = F.WALL_T
    if side in ("n", "s"):
        x = -W / 2 + F.CELL * cell + F.CELL / 2
        return (x, D / 2 - inn + back) if side == "n" else (x, -D / 2 + inn - back)
    y = D / 2 - F.CELL * cell - F.CELL / 2
    return (W / 2 - inn + back, y) if side == "e" else (-W / 2 + inn - back, y)


def wall_sockets(cx, cy, used, skip=()):
    """Wall-face sockets (inner face, floor level, facing into the room) on every side-cell midpoint without a cut."""
    taken = {(o["side"], o["cell"]) for o in used} | set(skip)
    out = []
    for side in SIDES:
        for cell in range(cx if side in ("n", "s") else cy):
            if (side, cell) not in taken:
                out.append(F.socket("wall", *anchor_xy(side, cell, cx, cy, back=0.0), 0.0, side, side=side, cell=cell))
    return out


WINDOWS = {"band": (2.4, 1.4, 1.0), "port": (1.1, 1.1, 1.25), "tall": (1.2, 2.3, 0.45)}
OPENING_ITEM = {"side": S.enum("n", list(SIDES)), "cell": S.integer(0, 0, 5)}
WINDOW_ITEM = {"side": S.enum("n", list(SIDES)), "cell": S.integer(0, 0, 5), "kind": S.enum("band", list(WINDOWS))}


def room_walls(cx, cy, doors, windows, profile=F.ROOM_PROFILE, height=F.H_ROOM, ribs=True, hangar_mouth=None):
    W, D = cx * F.CELL, cy * F.CELL
    inn = F.WALL_T
    loop = [(-W / 2 + inn, -D / 2 + inn), (W / 2 - inn, -D / 2 + inn), (W / 2 - inn, D / 2 - inn), (-W / 2 + inn, D / 2 - inn)]
    ops = {}
    for d in doors:
        si, s = side_cell_station(d["side"], d["cell"], cx, cy)
        ops.setdefault(si, []).append((s - F.DOOR_W / 2, s + F.DOOR_W / 2, 0.0, F.DOOR_H))
    for wdw in windows:
        si, s = side_cell_station(wdw["side"], wdw["cell"], cx, cy)
        ww, wh, sill = WINDOWS[wdw["kind"]]
        ops.setdefault(si, []).append((s - ww / 2, s + ww / 2, sill, sill + wh))
    if hangar_mouth:
        si, s0, s1, ztop = hangar_mouth
        ops.setdefault(si, []).append((s0, s1, 0.0, ztop))
    walls = F.wall_chain(loop, True, profile, seg_len=2.0, openings=ops, cap=height + 0.01)
    ribm = []
    if ribs:
        for si in range(4):
            a, b = np.asarray(loop[si]), np.asarray(loop[(si + 1) % 4])
            L = float(np.linalg.norm(b - a))
            t = (b - a) / L
            n = np.array([-t[1], t[0]])
            k = int(round(L / F.CELL))
            for i in range(1, k + 1):
                s = i * F.CELL - F.CELL + (L - (k - 1) * F.CELL) / 2 if k > 1 else L / 2
                s = (L - (k - 1) * F.CELL) / 2 + (i - 1) * F.CELL - F.CELL / 2
                if s < 0.9 or s > L - 0.9:
                    continue
                if any(o[0] - 0.5 < s < o[1] + 0.5 for o in ops.get(si, [])):
                    continue
                ribm.append(_wall_rib(a + t * s, t, n, profile, height))
    return walls, F.merged(*ribm) if ribm else None


def _wall_rib(p, t, n, profile, height, w=0.3):
    """Vertical tapered pilaster rib on a wall (closed): follows the wall profile up to the upper chamfer top."""
    # local frame: x along n (into the room), z up, extruded along t. The path runs top -> bottom so the rib's LEFT
    # side (taper_rib protrudes to the left of travel) is +x = into the room; thicker at the floor than at the top.
    path = [(d, z) for d, z, _ in reversed(profile)]
    rib = F.taper_rib(path, 0.1, 0.16, -w / 2, w / 2, "trim", sink=0.02)
    M = np.array([[n[0], t[0], 0.0], [n[1], t[1], 0.0], [0.0, 0.0, 1.0]])
    rib.apply(lambda a: a @ M.T + np.array([p[0], p[1], 0.0]))
    return rib.orient_outward()


@register("stn.room", V, "shell", {
    "cells_x": S.integer(3, 1, 4, "plot width in 4 m cells"), "cells_y": S.integer(3, 1, 4, "plot depth in 4 m cells"),
    "doors": S.array(OPENING_ITEM, [{"side": "s", "cell": 1}], 8, "2.0 x 2.6 door cuts (side, side cell)"),
    "windows": S.array(WINDOW_ITEM, [], 6, "viewport cuts (side, side cell, kind) for stn.viewport"),
    "ribs": S.boolean(True, "tapered pilaster ribs on the cell boundaries along the walls"),
}, "Station room shell: deck floor + mitred one-sided chamfered walls (kick chamfer, panels, light band, upper chamfer "
   "to a 4 m ceiling line) with door / viewport cuts on side-cell midpoints and pilaster ribs. Ceiling: stn.ceiling. "
   "Origin on the cell-block centre.", origin="room_floor")
def room(P, seed):
    cx, cy = P["cells_x"], P["cells_y"]
    for d in P["doors"] + P["windows"]:
        if d["cell"] >= (cx if d["side"] in ("n", "s") else cy):
            raise S.ParamError("opening %s on a %dx%d room is off the plot" % (d, cx, cy))
    walls, ribs = room_walls(cx, cy, P["doors"], P["windows"], ribs=P["ribs"])
    W, D = cx * F.CELL, cy * F.CELL
    nodes = [Node("walls", F.weld_mesh(walls), "shell"),
             Node("floor", F.floor_grid(-W / 2, W / 2, -D / 2, D / 2, 0.0, 2 * cx, 2 * cy, "floor"), "shell")]
    if ribs is not None:
        nodes.append(Node("ribs", ribs))
    sockets = [F.socket("door", *anchor_xy(d["side"], d["cell"], cx, cy), 0.0, d["side"], width_m=F.DOOR_W,
                        side=d["side"], cell=d["cell"]) for d in P["doors"]]
    sockets += [F.socket("window", *anchor_xy(wd["side"], wd["cell"], cx, cy), 0.0, wd["side"], kind=wd["kind"],
                         side=wd["side"], cell=wd["cell"]) for wd in P["windows"]]
    sockets += wall_sockets(cx, cy, P["doors"] + P["windows"])
    meta = {"sockets": sockets, "height_m": F.H_ROOM}
    meta.update(F.grid_meta("cell_block_centre", (cx, cy)))
    return _asset(nodes, meta, ao=0.28, reach=1.2)


@register("stn.ceiling", V, "shell", {
    "cells_x": S.integer(3, 1, 4), "cells_y": S.integer(3, 1, 4),
    "lights": S.boolean(True, "recessed light panel per cell"),
    "beams": S.boolean(True, "tapered beams on the inner cell boundaries"),
    "height": S.num(4.0, 3.2, 8.0, "ceiling height (4.0 rooms; hangars higher)"),
}, "Room ceiling for stn.room / stn.hangar plots: one-sided panel sheet facing down (cameras above see in), "
   "recessed light panels and tapered beams. Origin on the cell-block centre at floor level (geometry at the ceiling "
   "height).", origin="opening")
def ceiling(P, seed):
    cx, cy, H = P["cells_x"], P["cells_y"], P["height"]
    W, D = cx * F.CELL, cy * F.CELL
    nodes = [Node("ceiling", F.floor_grid(-W / 2, W / 2, -D / 2, D / 2, H, 2 * cx, 2 * cy, "ceiling", up=False), "shell")]
    if P["lights"]:
        lm = K.Mesh()
        for i in range(cx):
            for j in range(cy):
                x, y = -W / 2 + F.CELL * (i + 0.5), -D / 2 + F.CELL * (j + 0.5)
                o = F.chamfer_rect(1.6, 1.6, 0.4)
                vs = [(x + a, y + b, H - 0.03) for a, b in o]
                lm.add(vs, [tuple(reversed(range(len(o))))], "light", False)
        nodes.append(Node("panels", lm, "shell"))
    if P["beams"]:
        bm = []
        sec = [(-0.22, 0.0), (0.22, 0.0), (0.13, -0.3), (-0.13, -0.3)]
        for i in range(1, cx):
            x = -W / 2 + F.CELL * i
            bm.append(F.loft_levels([(a, b) for a, b in sec], [], "trim") if False else
                      F.extrude_xz([(x + a, H + 0.02 + b) for a, b in sec], -D / 2 + 0.6, D / 2 - 0.6, "trim"))
        for j in range(1, cy):
            y = -D / 2 + F.CELL * j
            beam = F.extrude_xz([(a, H + 0.0 + b) for a, b in sec], -W / 2 + 0.6, W / 2 - 0.6, "trim")
            beam.v = [(-p[1], p[0], p[2]) for p in beam.v]
            beam.translate(0.0, y, 0.0)
            bm.append(beam.orient_outward())
        if bm:
            nodes.append(Node("beams", F.merged(*bm)))
    meta = {"height_m": H}
    meta.update(F.grid_meta("cell_block_centre", (cx, cy)))
    return _asset(nodes, meta, ao=0.22, reach=1.0)


# ------------------------------------------------------------------ bridge / cockpit shell
@register("stn.bridge", V, "shell", {
    "panes": S.integer(3, 2, 4, "front viewport panes"),
    "view_depth": S.num(0.44, 0.2, 0.46, "distance of the star-field card behind the front glass line (inside the plot)"),
}, "Bridge / cockpit shell on a 3x3-cell plot: the side walls angle in toward a faceted front viewport band (star-field "
   "card beyond, mullions, sill ledge), back door on the south side cell 1, panelled ceiling with a light ring. Origin "
   "on the cell-block centre.", origin="room_floor")
def bridge(P, seed):
    cx = cy = 3
    W, D = cx * F.CELL, cy * F.CELL
    inn = F.WALL_T
    xb, yb, yf = W / 2 - inn, -D / 2 + inn, D / 2 - inn
    xf = xb - 2.6
    # CCW: back SW -> SE -> front-right shoulder -> front right -> front left -> front-left shoulder
    ysh = yf - 3.2
    loop = [(-xb, yb), (xb, yb), (xb, ysh), (xf, yf), (-xf, yf), (-xb, ysh)]
    L_front = 2 * xf
    sill, top = 0.95, 3.15
    ops = {0: [(xb - F.DOOR_W / 2, xb + F.DOOR_W / 2, 0.0, F.DOOR_H)], 3: [(0.35, L_front - 0.35, sill, top)]}
    walls = F.wall_chain(loop, True, F.ROOM_PROFILE, seg_len=2.0, openings=ops, cap=F.H_ROOM + 0.01)
    nodes = [Node("walls", F.weld_mesh(walls), "shell")]
    floor = F.floor_grid(-W / 2, W / 2, -D / 2, D / 2, 0.0, 6, 6, "floor")
    nodes.append(Node("floor", floor, "shell"))
    # ceiling polygon (fan over the plan, one-sided facing down) with a light ring
    cpoly = F.chain_offset(loop, True, -inn)
    cm = K.Mesh()
    ctr = (0.0, 0.0, F.H_ROOM)
    vs = [ctr] + [(p[0], p[1], F.H_ROOM) for p in cpoly]
    fs = [(0, (i + 1) % len(cpoly) + 1, i + 1) for i in range(len(cpoly))]
    cm.add(vs, fs, "ceiling", False)
    # a slim light band set in a steel collar (round 4: the wide 0.6 m ring was the brightest, biggest shape in frame)
    ring = K.Mesh()
    k = 16
    for (ro, ri, z, role) in ((2.7, 2.3, F.H_ROOM - 0.03, "trim"), (2.3, 2.1, F.H_ROOM - 0.05, "light")):
        rv = [(ro * math.cos(math.tau * i / k), ro * math.sin(math.tau * i / k) - 0.6, z) for i in range(k)] + \
             [(ri * math.cos(math.tau * i / k), ri * math.sin(math.tau * i / k) - 0.6, z) for i in range(k)]
        ring.add(rv, [(i, k + i, k + (i + 1) % k, (i + 1) % k) for i in range(k)], role, False)
    nodes += [Node("ceiling", cm, "shell"), Node("light_ring", ring, "shell")]
    # front glazing: mullions + sill ledge + star-field card
    n = P["panes"]
    mull = []
    for i in range(1, n):
        x = -xf + 0.35 + (L_front - 0.7) * i / n
        mull.append(F.bevel_block(x, yf + 0.02, sill + 0.001, 0.16, 0.22, top - sill - 0.002, "frame", bevel=0.04, chamfer=0.04))
    ledge = F.bevel_block(0.0, yf - 0.18, sill - 0.12, L_front - 0.5, 0.5, 0.12, "frame", bevel=0.05, chamfer=0.12)
    head = F.bevel_block(0.0, yf - 0.04, top, L_front - 0.4, 0.26, 0.14, "frame", bevel=0.04)
    nodes += [Node("mullions", F.merged(*mull)), Node("ledge", ledge), Node("head", head)]
    vd = P["view_depth"]
    vx = xf + 0.9
    card = K.Mesh().add([(-vx, yf + vd, sill - 0.6), (vx, yf + vd, sill - 0.6), (vx, yf + vd, top + 0.8), (-vx, yf + vd, top + 0.8)],
                        [(0, 1, 2, 3)], "view", False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    nodes.append(Node("view", card, "card"))
    door = {"side": "s", "cell": 1}
    meta = {"sockets": [F.socket("door", *anchor_xy("s", 1, cx, cy), 0.0, "s", width_m=F.DOOR_W, side="s", cell=1)],
            "height_m": F.H_ROOM, "door": door, "front_glass_m": [round(L_front - 0.7, 3), round(top - sill, 3)]}
    meta.update(F.grid_meta("cell_block_centre", (cx, cy)))
    return _asset(nodes, meta, ao=0.28, reach=1.2)


# ------------------------------------------------------------------ hangar bay
HANGAR_H = 7.0
HANGAR_PROFILE = ((0.34, 0.0, "wall_alt"), (0.0, 0.5, "wall"), (0.0, 2.4, "wall"), (0.0, 4.6, "light"),
                  (0.0, 4.8, "wall_alt"), (0.8, HANGAR_H, None))


@register("stn.hangar", V, "shell", {
    "cells": S.integer(4, 3, 4, "square plot in 4 m cells"),
    "mouth_w": S.num(10.0, 6.0, 12.0, "hangar mouth width on the north wall"),
    "mouth_h": S.num(5.4, 4.0, 6.0, "hangar mouth height"),
    "door_cell": S.integer(1, 0, 3, "south-wall side cell of the crew door"),
}, "Hangar bay shell (7 m high): tall chamfered walls with a high light band, a wide north mouth open to space "
   "(star-field card, heavy chamfered frame with hazard lips), painted landing ring on the hex deck, crew door on the "
   "south wall. Ceiling: stn.ceiling height 7. Origin on the cell-block centre.", origin="room_floor")
def hangar(P, seed):
    c = P["cells"]
    W = D = c * F.CELL
    inn = F.WALL_T
    mw, mh = P["mouth_w"], P["mouth_h"]
    yf = D / 2 - inn
    xr = W / 2 - inn
    si_n, s_c = 2, xr
    mouth = (si_n, s_c - mw / 2, s_c + mw / 2, mh)
    walls, ribs = room_walls(c, c, [{"side": "s", "cell": P["door_cell"]}], [], profile=HANGAR_PROFILE, height=HANGAR_H,
                             ribs=True, hangar_mouth=mouth)
    nodes = [Node("walls", F.weld_mesh(walls), "shell"),
             Node("floor", F.floor_grid(-W / 2, W / 2, -D / 2, D / 2, 0.0, 2 * c, 2 * c, "floor"), "shell")]
    if ribs is not None:
        nodes.append(Node("ribs", ribs))
    nodes.append(Node("mouth_frame", F.extrude_xz(F.arch_frame(mw, mh, mw + 1.6, mh + 0.9, 0.55, 0.9), yf - 0.3, yf + 0.5,
                                                 "frame")))
    nodes.append(Node("mouth_lip", F.extrude_xz(F.arch_frame(mw - 0.02, mh - 0.01, mw + 0.36, mh + 0.2, 0.54, 0.62),
                                               yf - 0.38, yf - 0.31, "band")))
    vy = yf + 0.46
    card = K.Mesh().add([(-mw / 2 - 1.2, vy, 0.0), (mw / 2 + 1.2, vy, 0.0), (mw / 2 + 1.2, vy, mh + 1.2),
                         (-mw / 2 - 1.2, vy, mh + 1.2)], [(0, 1, 2, 3)], "view", False,
                        [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    nodes.append(Node("space", card, "card"))
    # painted landing ring (band role) just above the deck
    ring = K.Mesh()
    k = 24
    ro, ri = 4.2, 3.7
    rv = [(ro * math.cos(math.tau * i / k), ro * math.sin(math.tau * i / k) + 0.8, 0.012) for i in range(k)] + \
         [(ri * math.cos(math.tau * i / k), ri * math.sin(math.tau * i / k) + 0.8, 0.012) for i in range(k)]
    ring.add(rv, [(i, (i + 1) % k, k + (i + 1) % k, k + i) for i in range(k)], "band", False)
    nodes.append(Node("deck_ring", ring, "shell"))
    meta = {"sockets": [F.socket("door", *anchor_xy("s", P["door_cell"], c, c), 0.0, "s", width_m=F.DOOR_W, side="s",
                                 cell=P["door_cell"]),
                        F.socket("hangar_mouth", 0.0, yf, 0.0, "n", width_m=mw, height_m=mh)] +
                       wall_sockets(c, c, [{"side": "s", "cell": P["door_cell"]}], skip=[("n", i) for i in range(c)]),
            "height_m": HANGAR_H, "pad_centre": F.gl(0.0, 0.8, 0.0)}
    meta.update(F.grid_meta("cell_block_centre", (c, c)))
    return _asset(nodes, meta, ao=0.25, reach=1.4)


# ------------------------------------------------------------------ deck floor tiles
@register("stn.floor", V, "structure", {
    "kind": S.enum("hex", ["plain", "hex", "grate", "pad"], "plain panel deck, raised hex plates, recessed grate, landing pad"),
}, "Deck tile for one cell laid over a room floor: raised bevelled hex plates, a framed grate, a plain bevelled deck "
   "plate or a circular marked pad. Origin on the cell centre.", origin="floor_center")
def floor_tile(P, seed):
    kind = P["kind"]
    nodes = []
    if kind == "hex":
        # seven raised bevelled hex plates (~1.1 m) on a chamfered deck plate: 3 columns of a flat-top hex lattice
        r = 0.55
        dx, dy = 1.5 * r * 1.06, math.sqrt(3) * r * 1.06
        m = []
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                x = i * dx
                y = j * dy + (dy / 2 if i % 2 else 0.0)
                if abs(y) + 0.87 * r > 1.86:
                    continue
                m.append(F.loft_levels(F.hexagon(r), [(0.02, 1.0, 1.0, x, y), (0.07, 1.0, 1.0, x, y), (0.1, 0.84, 0.84, x, y)],
                                       "floor"))
        nodes.append(Node("plates", F.merged(*m)))
        nodes.append(Node("base", F.bevel_block(0.0, 0.0, 0.0, 3.8, 3.8, 0.02, "wall_alt", bevel=0.008, chamfer=0.3)))
    elif kind == "grate":
        outer = F.chamfer_rect(3.6, 3.6, 0.3)
        inner = F.chamfer_rect(2.8, 2.8, 0.2)
        nodes += [Node("frame", K.prism(outer, 0.0, 0.05, "trim", holes=[inner])),
                  Node("grate", K.prism(inner, 0.0, 0.02, "step"))]
    elif kind == "plain":
        nodes.append(Node("plate", F.bevel_block(0.0, 0.0, 0.0, 3.7, 3.7, 0.05, "floor", bevel=0.03, chamfer=0.35)))
    else:
        disc = F.lathe([(0.0, 0.0), (1.75, 0.0), (1.8, 0.04), (1.7, 0.07), (0.0, 0.07)], 20, "floor", smooth=False)
        ring = F.lathe([(1.2, 0.068), (1.45, 0.068), (1.45, 0.078), (1.2, 0.078)], 20, "band", smooth=False)
        nodes += [Node("pad", disc), Node("marks", ring)]
    meta = {"kind": kind}
    meta.update(F.grid_meta("cell_centre"))
    return _asset(nodes, meta, ao=0.2, reach=0.6, ground=True)


# ------------------------------------------------------------------ bulkhead frame
@register("stn.bulkhead", V, "arch", {
    "lights": S.boolean(True, "light nodes on the upper chamfers"),
    "depth": S.num(0.5, 0.3, 0.9, "frame depth along the corridor"),
}, "Heavy bulkhead frame ring across a corridor on a cell edge: follows the chamfered section, thicker at the base, "
   "hazard lip inside. Origin on the cell-edge midpoint (frame centred on the boundary).", origin="floor_center")
def bulkhead(P, seed):
    dep = P["depth"]
    h = F.CORR_W / 2
    prof = F.CORR_PROFILE
    pts_r = [(h - d + 0.0, z) for d, z, _ in prof]
    wall = pts_r + [(-x, z) for x, z in reversed(pts_r)]
    outer = [(x * 1.08 + math.copysign(0.02, x), z * 1.04) for x, z in wall]
    inner = [(x * 0.88, 0.1 + z * 0.88) for x, z in wall]
    ring = F.frame_ring(outer, inner, -dep / 2, dep / 2, "frame")
    lip_inner = [(x * 0.84, 0.12 + z * 0.85) for x, z in wall]
    lip = F.frame_ring([(x * 0.9, 0.08 + z * 0.9) for x, z in wall], lip_inner, -dep / 2 - 0.05, -dep / 2 + 0.06, "band")
    nodes = [Node("ring", ring), Node("lip", lip)]
    if P["lights"]:
        lm = []
        for sx in (-1, 1):
            b = F.bevel_block(sx * 1.05, -dep / 2 - 0.02, 2.62, 0.3, 0.06, 0.12, "light", bevel=0.02)
            lm.append(b)
        nodes.append(Node("lights", F.merged(*lm)))
    meta = {"sockets": [F.socket("corridor", 0.0, 0.0, 0.0, "n", width_m=F.CORR_W), F.socket("corridor", 0.0, 0.0, 0.0, "s", width_m=F.CORR_W)]}
    meta.update(F.grid_meta("cell_edge"))
    return _asset(nodes, meta, ao=0.2, reach=0.7)


# ------------------------------------------------------------------ viewport window
@register("stn.viewport", V, "arch", {
    "kind": S.enum("band", list(WINDOWS), "band 2.4 x 1.4 (sill 1.0), port 1.1 round-cornered (sill 1.25), tall 1.2 x 2.3"),
    "view_depth": S.num(0.9, 0.3, 2.0, "star-field card distance behind the frame"),
}, "Viewport window for a room-wall cut: chamfered frame (depth through the wall), sill ledge and a star-field card "
   "behind (dark space, nebula, a distant violet planet). Origin on the wall anchor (0.6 m behind the inner face, "
   "side-cell midpoint, floor level); the card reaches the floor behind the wall.", origin="opening_floor")
def viewport(P, seed):
    ww, wh, sill = WINDOWS[P["kind"]]
    c = 0.5 if P["kind"] == "port" else 0.24
    inner = F.opening_outline(ww, wh, sill, c)
    outer = F.opening_outline(ww + 0.56, wh + 0.56, sill - 0.28, c + 0.2)
    nodes = [Node("frame", F.frame_ring(outer, inner, -F.ANCHOR_BACK - 0.12, 0.05, "frame")),
             Node("ledge", F.bevel_block(0.0, -F.ANCHOR_BACK - 0.14, sill - 0.32, ww + 0.4, 0.3, 0.1, "trim", bevel=0.04,
                                         chamfer=0.08))]
    vd = P["view_depth"]
    pad = 0.6 + vd * 0.5
    card = K.Mesh().add([(-ww / 2 - pad, vd, 0.0), (ww / 2 + pad, vd, 0.0), (ww / 2 + pad, vd, sill + wh + pad),
                         (-ww / 2 - pad, vd, sill + wh + pad)], [(0, 1, 2, 3)], "view", False,
                        [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    nodes.append(Node("view", card, "card"))
    meta = {"kind": P["kind"], "cut_m": [ww, wh, sill], "sockets": [F.socket("window", 0.0, 0.0, 0.0, "s", kind=P["kind"])]}
    meta.update(F.grid_meta("door_anchor"))
    return _asset(nodes, meta, ao=0.2, reach=0.6)


# ------------------------------------------------------------------ lift
@register("stn.lift", V, "structure", {
    "radius": S.num(1.3, 0.9, 1.5, "platform radius"),
    "columns": S.integer(3, 3, 4, "guide columns"),
    "height": S.num(3.6, 3.0, 4.0, "guide height (top ring)"),
}, "Lift platform for one cell: bevelled round platform with a hazard rim, tapered guide columns, a top guide ring with "
   "a light band and a call post on the front. Origin on the cell centre.", origin="floor_center")
def lift(P, seed):
    r, n, H = P["radius"], P["columns"], P["height"]
    k = 12
    nodes = [Node("platform", F.lathe([(0.0, 0.0), (r + 0.2, 0.0), (r + 0.12, 0.18), (0.0, 0.18)], k, "floor",
                                      smooth=False)),
             Node("rim", F.lathe_ring(r - 0.16, r + 0.05, 0.181, 0.195, k, "band"))]
    cols = []
    for i in range(n):
        a = math.tau * (i + 0.5) / n + math.pi / 2
        x, y = (r + 0.32) * math.cos(a), (r + 0.32) * math.sin(a)
        cols.append(F.loft_levels(F.chamfer_rect(0.26, 0.26, 0.07), [(0.0, 1.3, 1.3, x, y), (0.25, 1.0, 1.0, x, y),
                                                                    (H, 0.66, 0.66, x, y)], "trim"))
    nodes.append(Node("columns", F.merged(*cols)))
    # top guide ring with a glowing underside (one solid: bottom face role light)
    nodes.append(Node("top_ring", F.lathe_ring(r + 0.16, r + 0.5, H - 0.1, H + 0.08, k, "frame",
                                               roles=["light", "frame", "frame", "frame"])))
    py = -(r + 0.36)
    nodes.append(Node("call_post", F.loft_levels(F.chamfer_rect(0.22, 0.16, 0.05), [(0.0, 1.2, 1.2, 0.9, py),
                                                                                  (1.05, 1.0, 1.0, 0.9, py),
                                                                                  (1.2, 0.9, 1.0, 0.9, py)], "body_alt")))
    nodes.append(Node("call_screen", F.bevel_block(0.9, py - 0.09, 0.98, 0.16, 0.02, 0.14, "screen", bevel=0.006)))
    meta = {"emitter": "lift_ring"}
    meta.update(F.grid_meta("cell_centre"))
    return _asset(nodes, meta, ao=0.25, reach=0.8, ground=True)


# ------------------------------------------------------------------ stairs / ramp / dais
@register("stn.stairs", V, "structure", {
    "kind": S.enum("steps", ["steps", "ramp", "dais"], "steps: 4-step flight; ramp: 0.8 m over 3.2 m; dais: round 2-step platform"),
    "width": S.num(2.4, 1.6, 3.2, "flight / ramp width"),
}, "Stairs, ramp or dais for raised decks (command platforms, catwalk ends): one solid zig-zag flight with grille "
   "treads, tapered side stringers, tube handrails on posts. Origin on the footprint centre.", origin="floor_center")
def stairs(P, seed):
    kind, w = P["kind"], P["width"]
    nodes = []
    if kind in ("steps", "ramp"):
        if kind == "steps":
            prof = [(-1.6, 0.0), (1.6, 0.0), (1.6, 0.8)]
            for i in range(3, -1, -1):
                y = -1.6 + 0.8 * i
                prof += [(y, 0.2 * (i + 1)), (y, 0.2 * i)] if i else [(y, 0.2)]
            prof = [p for j, p in enumerate(prof) if j == 0 or p != prof[j - 1]]
        else:
            prof = [(-1.6, 0.0), (1.6, 0.0), (1.6, 0.8)]
        body = F.extrude_xz(prof, -w / 2, w / 2, "step", role_cap="frame")
        body.v = [(p[1], p[0], p[2]) for p in body.v]
        nodes.append(Node("flight", body.orient_outward()))
        strs = []
        for sx in (-1, 1):
            poly = [(-1.6, 0.0), (1.6, 0.0), (1.6, 0.98), (1.3, 0.98), (-1.6, 0.26)]
            st = F.extrude_xz(poly, -0.07, 0.07, "frame")
            st.v = [(p[1] + sx * (w / 2 + 0.07), p[0], p[2]) for p in st.v]
            strs.append(st.orient_outward())
        nodes.append(Node("stringers", F.merged(*strs)))
        xr = w / 2 + 0.07
        nodes.append(Node("rails", F.merged(*[F.tube([(sx * xr, -1.7, 1.12), (sx * xr, 1.45, 1.92)], 0.035, 6, "rail")
                                               for sx in (-1, 1)])))
        nodes.append(Node("posts", F.merged(*[F.tube([(sx * xr, y, 0.27 + 0.226 * (y + 1.6)), (sx * xr, y, 1.08 + 0.254 * (y + 1.6))],
                                                     0.028, 5, "post") for sx in (-1, 1) for y in (-1.3, 0.0, 1.2)])))
    else:
        dais = F.lathe([(0.0, 0.0), (1.9, 0.0), (1.9, 0.18), (1.75, 0.2), (1.5, 0.2), (1.5, 0.38), (1.38, 0.4), (0.0, 0.4)],
                       16, "step", smooth=False)
        nodes += [Node("dais", dais), Node("rim", F.lathe_ring(1.36, 1.46, 0.401, 0.412, 16, "light"))]
    meta = {"kind": kind, "rise_m": {"steps": 0.8, "ramp": 0.8, "dais": 0.4}[kind]}
    meta.update(F.grid_meta("free"))
    return _asset(nodes, meta, ao=0.25, reach=0.8, ground=True)
