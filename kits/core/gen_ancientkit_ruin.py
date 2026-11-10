"""ANCIENTKIT ruin architecture (ruin.*), theme-agnostic (Blender space, +Z up, front faces -Y = glTF south).

Twelve generators on the RUIN GRID (kits/core/gen_ancientkit_core.py): carved wall segments, corner piers, columns
(standing / broken / stump / fallen), stepped pyramid tiers, monumental stairs, the temple gate (the standard doorway
frame room.gd places on every door, a monumental pylon gate and a sealed state), obelisks, arches, ramparts, collapsed
rubble, a sunken court and floor / ceiling slabs. Everything is bevelled or tapered (no raw cuboids: the ANCIENTKIT
cuboid gate measures it), carvings are painted panels (normalized UVs of the pack's wall_alt / door / hull / frame
roles), and gold appears only as small painted or sphere-mapped accents.
"""
import math

from . import gen_ancientkit_core as A
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .genutil import finalize
from .rng import rng

V = "1.0.0"
CELL, H, WD = A.CELL, A.H, A.WALL_D


def _jag_top(w, base_h, rs, steps=7, amp=0.9):
    """Ragged top outline points from right to left (for broken walls)."""
    pts = []
    for i in range(steps + 1):
        x = w / 2 - w * i / steps
        z = base_h - amp * (0.25 + 0.75 * rs.random()) * (0.4 + 0.6 * math.sin(math.pi * i / steps))
        pts.append((x, max(0.6, z)))
    return pts


# ---------------------------------------------------------------- ruin.wall
@register("ruin.wall", V, "arch", {
    "style": S.enum("solid", ["solid", "door", "window", "relief", "broken", "low"]),
    "length": S.num(4.0, 2.0, 4.0, "cell edge length (4 m = one RUIN GRID cell)"),
    "height": S.num(4.5, 1.2, 4.5),
}, "Carved sandstone wall segment on a cell edge: a closed 1 m solid centred on the boundary (inner faces 0.5 m in), "
   "plinth, dressed cornice; door = 2.8 x 3.6 m cut with a lintel (the standard frame covers it), window = slit, relief "
   "= carved panel on both faces, broken = ragged collapsed top with fallen blocks, low = parapet.", origin="floor_center")
def wall(P, seed):
    r = rng(seed, "ruin.wall", P["style"])
    st, L = P["style"], P["length"]
    h = P["height"] if st != "low" else min(P["height"], 1.3)
    t = WD / 2
    nodes = []
    if st == "door":
        outline = A.notched_rect(L, h - 0.35, A.CUT_W, A.CUT_H)
        body = A.front_prism(outline, -t, t, "wall")
    elif st == "broken":
        top = _jag_top(L, h - 0.3, r, steps=7, amp=1.8)
        body = A.front_prism([(-L / 2, 0.0), (L / 2, 0.0)] + top, -t, t, "wall")
    else:
        outline = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, h - 0.35), (-L / 2, h - 0.35)]
        holes = []
        if st == "window":
            holes = [[(-0.28, 1.7), (0.28, 1.7), (0.28, 3.0), (-0.28, 3.0)]]
        body = K.prism(outline, -t, t, "wall", holes=holes)
        body.apply(lambda a: a[:, [0, 2, 1]])
        body = body.orient_outward()
    nodes.append(Node("body", body))
    plinth = K.Mesh()
    if st == "door":
        side = (L - A.CUT_W) / 2
        for sx in (-1, 1):
            plinth.merge(A.chamfer_box(sx * (A.CUT_W / 2 + side / 2), 0, 0, side - 0.02, WD + 0.16, 0.45, "step", bevel=0.05))
    else:
        plinth.merge(A.chamfer_box(0, 0, 0, L - 0.02, WD + 0.16, 0.45, "step", bevel=0.05))
    nodes.append(Node("plinth", plinth))
    trim = K.Mesh()
    if st in ("solid", "door", "window", "relief"):
        trim.merge(A.chamfer_box(0, 0, h - 0.5, L - 0.01, WD + 0.24, 0.5, "trim", bevel=0.08))
    if st == "low":
        trim.merge(A.chamfer_box(0, 0, h - 0.18, L - 0.01, WD + 0.2, 0.2, "trim", bevel=0.06))
    if st == "door":
        trim.merge(A.chamfer_box(0, 0, A.CUT_H + 0.02, A.CUT_W + 0.9, WD + 0.12, 0.42, "trim", bevel=0.06))
    if trim.f:
        nodes.append(Node("trim", trim))
    if st == "relief":
        rel = K.Mesh()
        rel.merge(A.panel(0, -t - 0.03, 1.05, 2.5, 2.1, 0.05, "wall_alt", "trim"))
        back = A.panel(0, -t - 0.03, 1.05, 2.5, 2.1, 0.05, "wall_alt", "trim")
        back.rotate_z(math.pi)
        rel.merge(back)
        nodes.append(Node("relief", rel))
    if st == "broken":
        fall = K.Mesh()
        for i in range(3):
            fall.merge(A.block_chunk(r.uniform(-1.4, 1.4), -t - 0.55 - r.uniform(0, 0.5), 0.0, r.uniform(0.6, 0.9),
                                     r.uniform(0.45, 0.6), r.uniform(0.4, 0.5), r, "stone", tilt=r.uniform(-0.25, 0.25)))
        nodes.append(Node("fallen", fall))
    sockets = A.edge_sockets(L) + [A.sock("wall", (0, -t, 0), "s", cell=0), A.sock("wall", (0, t, 0), "n", cell=0)]
    if st == "door":
        sockets += [A.sock("door", (0, -t, 0), "s", width_m=A.DOOR_W), A.sock("door", (0, t, 0), "n", width_m=A.DOOR_W)]
    return finalize(nodes, A.grid_meta("cell_edge", None, sockets, style=st, height_m=h))


# ---------------------------------------------------------------- ruin.pier
@register("ruin.pier", V, "arch", {
    "style": S.enum("full", ["full", "broken", "low"]),
}, "Corner pier on a cell corner: chamfered square shaft on a moulded base with a stepped capital; hides the joint "
   "where two walls meet. broken = ragged snapped top; low = parapet post.", origin="floor_center")
def pier(P, seed):
    r = rng(seed, "ruin.pier", P["style"])
    st = P["style"]
    h = {"full": H + 0.5, "broken": H * 0.55, "low": 1.6}[st]
    nodes = [Node("base", A.stack(0, 0, [(0.0, 1.6, 1.6, 0.06), (0.4, 1.6, 1.6, 0.06), (0.62, 1.4, 1.4, 0.05)], "step"))]
    if st == "broken":
        rings = [K.ring3d(0, 0, 0.55, K.rounded_rect2d(1.25, 1.25, 0.08, 1))]
        top = []
        for i, (x, y, z) in enumerate(K.ring3d(0, 0, h, K.rounded_rect2d(1.18, 1.18, 0.08, 1))):
            top.append((x, y, z - r.uniform(0.0, 0.9)))
        rings.append(top)
        nodes.append(Node("shaft", K.loft(rings, "wall", smooth=False)))
        nodes.append(Node("fallen", A.block_chunk(1.1, -0.9, 0, 0.7, 0.6, 0.5, r, "stone", tilt=0.3)))
    else:
        nodes.append(Node("shaft", A.taper_box(0, 0, 0.55, h - 0.5, 1.25, 1.25, 1.12, 1.12, "wall", bevel=0.07)))
        nodes.append(Node("capital", A.taper_box(0, 0, h - 0.6, h, 1.3, 1.3, 1.6, 1.6, "trim", bevel=0.07)))
    return finalize(nodes, A.grid_meta("corner", None, [A.sock("corner", (0, 0, 0), "up")], style=st))


# ---------------------------------------------------------------- ruin.column
def _shaft_rings(z0, z1, r0, r1, sides, bands=(), jag=None, rs=None):
    rings, roles = [], []
    zs = [z0, z0 + (z1 - z0) * 0.35, z1]
    pts = []
    for z in zs:
        t = (z - z0) / max(z1 - z0, 1e-6)
        rr = r0 + (r1 - r0) * t + 0.03 * math.sin(math.pi * t)       # entasis
        pts.append((rr, z))
    for rr, z in pts:
        ring = [(rr * math.cos(TAU * i / sides + math.pi / sides), rr * math.sin(TAU * i / sides + math.pi / sides), z) for i in range(sides)]
        rings.append(ring)
    if jag is not None:
        rings[-1] = [(x, y, z - jag * (0.2 + 0.8 * rs.random())) for x, y, z in rings[-1]]
    return rings


TAU = math.tau


@register("ruin.column", V, "arch", {
    "state": S.enum("whole", ["whole", "broken", "stump", "fallen"]),
    "height": S.num(5.0, 3.5, 6.5), "sides": S.lod(S.integer(8, 6, 10)),
}, "Temple column (original order): stepped square plinth, rounded base ring, faceted shaft with entasis and two carved "
   "limestone rings, a flared 'sun cup' capital under a square abacus. broken = snapped shaft with a fallen drum; stump = "
   "plinth and a jagged metre of shaft; fallen = drums and capital lying in the sand.", origin="floor_center")
def column(P, seed):
    r = rng(seed, "ruin.column", P["state"])
    st, h, sides = P["state"], P["height"], P["sides"]
    nodes = []
    plinth = A.stack(0, 0, [(0.0, 1.5, 1.5, 0.05), (0.3, 1.5, 1.5, 0.05), (0.3, 1.24, 1.24, 0.04), (0.52, 1.24, 1.24, 0.04)], "step")
    base = A.lathe([(0.0, 0.52), (0.6, 0.52), (0.5, 0.74), (0.0, 0.74)], sides, "post", smooth=False)
    if st != "fallen":
        nodes.append(Node("plinth", plinth))
        nodes.append(Node("base", base))
    if st == "whole":
        top = h - 0.85
        nodes.append(Node("shaft", K.loft(_shaft_rings(0.74, top, 0.44, 0.38, sides), "trim", smooth=True)))
        z = top - 0.6
        nodes.append(Node("ring", A.lathe([(0.0, z), (0.5, z), (0.47, z + 0.16), (0.0, z + 0.16)], sides, "post", smooth=False)))
        cap = K.Mesh()
        cap.merge(A.lathe([(0.0, top - 0.02), (0.36, top - 0.02), (0.66, top + 0.42), (0.0, top + 0.42)], sides, "post", smooth=True))
        cap.merge(A.chamfer_box(0, 0, top + 0.42, 1.42, 1.42, 0.43, "trim", bevel=0.06))
        nodes.append(Node("capital", cap))
    elif st in ("broken", "stump"):
        top = (h * r.uniform(0.42, 0.58)) if st == "broken" else 1.35
        nodes.append(Node("shaft", K.loft(_shaft_rings(0.74, top, 0.44, 0.41, sides, jag=0.35, rs=r), "trim", smooth=True)))
        fall = K.Mesh()
        if st == "broken":
            drum = K.loft([[(x, y, z - 0.45) for x, y, z in ring] for ring in
                           [[(0.42 * math.cos(TAU * i / sides), 0.42 * math.sin(TAU * i / sides), 0.0) for i in range(sides)],
                            [(0.42 * math.cos(TAU * i / sides), 0.42 * math.sin(TAU * i / sides), 0.9) for i in range(sides)]]],
                          "trim", smooth=True)
            drum.rotate_x(math.pi / 2).rotate_z(r.uniform(0.3, 1.2)).translate(1.55, -0.6, 0.42)
            fall.merge(drum)
        fall.merge(A.rock(-0.95, -0.85, 0.12, 0.32, 0.26, 0.2, r, "stone", segs=5, rings=3))
        nodes.append(Node("fallen", fall))
    else:
        lie = K.Mesh()
        n_dr = 3
        for i in range(n_dr):
            ln = 1.05
            drum = K.loft([[(0.42 * math.cos(TAU * k / sides), 0.42 * math.sin(TAU * k / sides), 0.0) for k in range(sides)],
                           [(0.41 * math.cos(TAU * k / sides), 0.41 * math.sin(TAU * k / sides), ln) for k in range(sides)]],
                          "trim", smooth=True)
            drum.rotate_y(math.pi / 2).rotate_z(r.uniform(-0.15, 0.15))
            drum.translate(-2.0 + i * 1.3, r.uniform(-0.2, 0.2), 0.41)
            lie.merge(drum)
        cap = A.chamfer_box(0, 0, -0.21, 1.42, 1.42, 0.43, "trim", bevel=0.06)
        cap.rotate_x(0.12).rotate_z(r.uniform(0, 1)).translate(2.2, 0.6, 0.25)
        lie.merge(cap)
        lie.merge(plinth.copy().translate(-3.4, -0.3, 0.0))
        nodes.append(Node("drums", lie))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("pillar", (0, 0, 0), "up", footprint_m=1.5)], state=st))


# ---------------------------------------------------------------- ruin.pyramid (stepped tiers)
def _sawtooth_stairs(width, steps, rise, run, z_base=0.0, y_front=0.0, role="step"):
    """Closed stair flight: side outline (sawtooth) extruded across `width` (x), climbing toward +Y (north)."""
    pts = [(y_front, z_base)]
    for i in range(steps):
        pts.append((y_front + i * run, z_base + (i + 1) * rise))
        pts.append((y_front + (i + 1) * run, z_base + (i + 1) * rise))
    pts.append((y_front + steps * run, z_base))
    # outline in (y, z) -> prism along x
    m = K.prism(pts, -width / 2, width / 2, role)
    m.apply(lambda a: a[:, [2, 0, 1]])
    return m.orient_outward()


@register("ruin.pyramid", V, "building", {
    "base_cells": S.integer(3, 1, 5, "square footprint in RUIN GRID cells"),
    "tiers": S.integer(3, 1, 5), "tier_h": S.num(2.0, 1.0, 3.0), "setback": S.num(1.5, 0.75, 2.5),
    "stair": S.enum("front", ["none", "front"]), "top": S.enum("shrine", ["none", "shrine", "altar"]),
    "ruin": S.num(0.3, 0.0, 1.0, "erosion: missing corner blocks and rubble at the foot"),
}, "Stepped pyramid: battered tiers with a dressed lip, an optional stair flight up the south face with sloped "
   "balustrades, and an optional summit shrine (doorway house under a stepped roof) or altar. tiers = 1 is a single "
   "walkable tier block.", origin="floor_center")
def pyramid(P, seed):
    r = rng(seed, "ruin.pyramid")
    n, th, sb = P["tiers"], P["tier_h"], P["setback"]
    base = P["base_cells"] * CELL - 0.5
    nodes = []
    tiers = K.Mesh()
    lips = K.Mesh()
    s = base
    z = 0.0
    sizes = []
    for i in range(n):
        if s < 2.5:
            break
        tiers.merge(A.taper_box(0, 0, z, z + th - 0.22, s, s, s - 0.5, s - 0.5, "roof", bevel=0.12, top_role="floor"))
        lips.merge(A.chamfer_box(0, 0, z + th - 0.24, s - 0.3, s - 0.3, 0.24, "trim", bevel=0.06, top_role="floor"))
        sizes.append((z, s))
        z += th
        s -= 2 * sb
    nodes.append(Node("tiers", tiers))
    nodes.append(Node("lips", lips))
    top_z = z
    top_s = sizes[-1][1] - 0.3 if sizes else 2.0
    if P["stair"] == "front" and sizes:
        steps = int(round(top_z / A.STEP_RISE))
        run = min(A.STEP_RUN, (base / 2 - top_s / 2 + 0.3) / max(steps, 1))
        y0 = -base / 2 - 0.25
        sw = min(3.2, top_s - 0.4)
        nodes.append(Node("stairs", _sawtooth_stairs(sw, steps, top_z / steps, run, 0.0, y0, "step")))
        bal = K.Mesh()
        for sx in (-1, 1):
            yb = y0 + steps * run
            pts = [(y0 - 0.1, 0.0), (yb, top_z + 0.2), (yb + 0.8, top_z + 0.2), (yb + 0.8, 0.0)]
            b = K.prism(pts, sx * (sw / 2) + (0.0 if sx > 0 else -0.5), sx * (sw / 2) + (0.5 if sx > 0 else 0.0), "trim")
            b.apply(lambda a: a[:, [2, 0, 1]])
            bal.merge(b.orient_outward())
        nodes.append(Node("balustrades", bal))
    if P["top"] == "shrine" and sizes:
        hs = min(3.6, top_s - 0.6)
        house = A.front_prism(A.notched_rect(hs, 2.6, 1.1, 1.8), -hs / 2 + 0.3, hs / 2 - 0.3, "wall")
        house.translate(0, 0, top_z)
        roof = K.Mesh()
        roof.merge(A.taper_box(0, 0, top_z + 2.6, top_z + 3.2, hs + 0.4, hs - 0.2, hs - 0.2, hs - 0.8, "trim", bevel=0.06))
        roof.merge(A.taper_box(0, 0, top_z + 3.2, top_z + 3.8, hs - 0.6, hs - 1.2, hs - 1.4, hs - 1.9, "roof", bevel=0.06))
        roof.merge(A.lathe([(0.0, top_z + 3.8), (0.32, top_z + 3.8), (0.2, top_z + 4.25), (0.0, top_z + 4.4)], 6, "chrome", smooth=True))
        dark = A.panel(0, -hs / 2 + 0.29, top_z, 1.1, 1.8, 0.02, "opening", "opening")
        nodes += [Node("shrine", house), Node("roof", roof), Node("shrine_door", dark)]
    elif P["top"] == "altar" and sizes:
        alt = K.Mesh()
        alt.merge(A.chamfer_box(0, 0.4, top_z, 1.6, 1.0, 0.9, "trim", bevel=0.06))
        alt.merge(A.chamfer_box(0, 0.4, top_z + 0.9, 1.9, 1.2, 0.18, "post", bevel=0.04))
        nodes.append(Node("altar", alt))
    if P["ruin"] > 0.05:
        rub = K.Mesh()
        k = int(2 + 5 * P["ruin"])
        for i in range(k):
            ang = r.uniform(0, TAU)
            rad = base / 2 + r.uniform(0.3, 1.4)
            x, y = rad * math.cos(ang), rad * math.sin(ang)
            if y < -base / 2 and abs(x) < 2.2:
                continue
            rub.merge(A.block_chunk(x, y, 0.0, r.uniform(0.6, 1.0), r.uniform(0.5, 0.8), r.uniform(0.4, 0.6), r, "stone",
                                    tilt=r.uniform(-0.3, 0.3)))
        if rub.f:
            nodes.append(Node("rubble", rub))
    meta = A.grid_meta("cell_block_centre", (P["base_cells"], P["base_cells"]),
                       [A.sock("stair_foot", (0, -base / 2 - 0.25, 0), "s", width_m=3.2), A.sock("summit", (0, 0, top_z), "up")],
                       summit_m=round(top_z, 3), tiers=len(sizes))
    return finalize(nodes, meta, center_y=False)


# ---------------------------------------------------------------- ruin.stairs
@register("ruin.stairs", V, "structure", {
    "rise": S.num(2.0, 0.5, 2.5), "width": S.num(3.0, 1.5, 7.0), "style": S.enum("whole", ["whole", "ruined"]),
}, "Monumental stair flight inside one cell: 0.25 m risers climbing north (glTF -Z) with sloped balustrades ending in "
   "disc terminals; ruined = missing treads and a cracked balustrade. Sockets: stair_bottom (south edge) and stair_top "
   "(north edge, at the rise).", origin="floor_center")
def stairs(P, seed):
    r = rng(seed, "ruin.stairs")
    steps = max(2, int(round(P["rise"] / A.STEP_RISE)))
    rise = P["rise"] / steps
    run = min(A.STEP_RUN, (CELL - 0.4) / steps)
    w = P["width"]
    y0 = -steps * run / 2
    nodes = [Node("flight", _sawtooth_stairs(w, steps, rise, run, 0.0, y0, "step"))]
    bal = K.Mesh()
    term = K.Mesh()
    for sx in (-1, 1):
        x0, x1 = (w / 2, w / 2 + 0.45) if sx > 0 else (-w / 2 - 0.45, -w / 2)
        yb = y0 + steps * run
        pts = [(y0 - 0.25, 0.0), (y0 - 0.25, 0.5), (yb, P["rise"] + 0.35), (yb + 0.2, P["rise"] + 0.35), (yb + 0.2, 0.0)]
        if P["style"] == "ruined" and sx > 0:
            pts = [(y0 - 0.25, 0.0), (y0 - 0.25, 0.5), (y0 + steps * run * 0.45, 0.5 + P["rise"] * 0.2),
                   (y0 + steps * run * 0.55, P["rise"] * 0.62), (yb, P["rise"] + 0.35), (yb + 0.2, P["rise"] + 0.35), (yb + 0.2, 0.0)]
        b = K.prism(pts, x0, x1, "trim")
        b.apply(lambda a: a[:, [2, 0, 1]])
        bal.merge(b.orient_outward())
        term.merge(A.lathe([(0.0, 0.48), (0.26, 0.5), (0.3, 0.66), (0.22, 0.82), (0.0, 0.86)], 7, "post", smooth=True,
                           cx=(x0 + x1) / 2, cy=y0 - 0.32))
    nodes += [Node("balustrades", bal), Node("terminals", term)]
    if P["style"] == "ruined":
        nodes.append(Node("fallen", A.block_chunk(-w / 2 - 1.0, y0 + 0.6, 0.0, 0.7, 0.5, 0.45, r, "stone", tilt=0.2)))
    meta = A.grid_meta("cell_centre", (1, 1), [A.sock("stair_bottom", (0, y0, 0), "s", width_m=w),
                                               A.sock("stair_top", (0, y0 + steps * run, P["rise"]), "n", width_m=w)],
                       rise_m=P["rise"])
    return finalize(nodes, meta)


# ---------------------------------------------------------------- ruin.gate
@register("ruin.gate", V, "structure", {
    "style": S.enum("doorway", ["doorway", "sealed", "pylon"]),
}, "Temple gate on the door anchor (room.gd places 'arch.door' 0.4 m in from the room edge; this frame covers the "
   "2.8 x 3.6 m wall cut): doorway = carved jambs and lintel with a sun-inlay keystone (the frame bound to arch.door); "
   "sealed = the same frame closed by a carved stone slab (state swap); pylon = a monumental gate of two battered "
   "towers and a carved beam around the standard frame (spans 3 cells).", origin="opening_floor")
def gate(P, seed):
    st = P["style"]
    yc = -0.1                     # wall centre line relative to the door anchor (anchor is 0.1 m outside it)
    nodes = []
    fw, fh = A.DOOR_W, A.DOOR_H
    outer_w, outer_h = A.CUT_W + 0.5, A.CUT_H + 0.45
    frame = A.front_prism(A.notched_rect(outer_w, outer_h, fw, fh), yc - 0.62, yc + 0.62, "trim")
    nodes.append(Node("frame", frame))
    lint = K.Mesh()
    lint.merge(A.chamfer_box(0, yc, outer_h - 0.05, outer_w + 0.5, 1.4, 0.4, "trim", bevel=0.07))
    lint.merge(A.panel(0, yc - 0.72, outer_h - 0.98, 0.9, 0.8, 0.08, "frame", "trim"))
    nodes.append(Node("lintel", lint))
    # threshold stone through the full frame depth: room floors stop at the wall centre line, so without it the outer
    # half of the cut showed the background as a bright sliver under the dark passage (round-19 shrine close-ups)
    nodes.append(Node("threshold", A.taper_box(0, yc, 0.0, 0.04, fw + 0.3, 1.24, fw + 0.24, 1.18, "step", bevel=0.0)))
    if st != "sealed":
        # the passage reads dark (opening role, a deep coloured void set back at the far face of the frame, facing the
        # plot): the N64 doorway, a strong value accent where the eye goes
        y0 = yc + 0.55
        dark = K.Mesh().add([(-fw / 2, y0, 0.0), (fw / 2, y0, 0.0), (fw / 2, y0, fh), (-fw / 2, y0, fh)], [(0, 1, 2, 3)],
                            "opening", False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
        nodes.append(Node("passage", dark, "shell"))
    if st == "sealed":
        slab = A.panel(0, yc - 0.15, 0.0, fw - 0.06, fh - 0.04, 0.3, "door", "stone")
        nodes.append(Node("slab", slab))
    if st == "pylon":
        tw = K.Mesh()
        for sx in (-1, 1):
            cx = sx * (outer_w / 2 + 1.9)
            tw.merge(A.taper_box(cx, yc, 0.0, 7.0, 3.6, 2.4, 2.9, 1.8, "wall", bevel=0.1))
            tw.merge(A.chamfer_box(cx, yc, 7.0, 3.3, 2.2, 0.5, "trim", bevel=0.08))
            tw.merge(A.panel(cx, yc - 1.12, 2.4, 2.0, 2.6, 0.06, "wall_alt", "trim"))
        nodes.append(Node("towers", tw))
        beam = K.Mesh()
        beam.merge(A.chamfer_box(0, yc, 5.2, outer_w + 3.6, 1.6, 0.9, "trim", bevel=0.08))
        beam.merge(A.panel(0, yc - 0.84, 5.25, 2.2, 0.8, 0.06, "door", "trim"))
        beam.merge(A.chamfer_box(0, yc, 4.4, outer_w + 0.2, 1.3, 0.8, "wall", bevel=0.06))
        nodes.append(Node("beam", beam))
    meta = A.grid_meta("door_anchor", None, [A.sock("door", (0, yc, 0), "s", width_m=A.DOOR_W, fits="cut")],
                       style=st, clear_m=[fw, fh])
    return Asset(nodes, meta)


# ---------------------------------------------------------------- ruin.obelisk
@register("ruin.obelisk", V, "arch", {
    "state": S.enum("whole", ["whole", "broken", "short"]), "height": S.num(7.0, 3.0, 9.0),
}, "Obelisk: tapered square shaft on a two-step base, glyph panels (original glyph grammar, hull role) on all four "
   "faces and a sphere-mapped gold cap. broken = snapped shaft with the top lying beside it; short = waist-high "
   "waystone.", origin="floor_center")
def obelisk(P, seed):
    r = rng(seed, "ruin.obelisk")
    st = P["state"]
    h = 2.4 if st == "short" else P["height"]
    nodes = [Node("base", A.stack(0, 0, [(0.0, 1.9, 1.9, 0.06), (0.35, 1.9, 1.9, 0.06), (0.35, 1.45, 1.45, 0.05),
                                         (0.7, 1.45, 1.45, 0.05)], "step"))]
    w0, w1 = 0.95, 0.6
    top = h if st != "broken" else h * 0.48
    wt = w0 + (w1 - w0) * (top - 0.7) / (h - 0.7)
    nodes.append(Node("shaft", A.taper_box(0, 0, 0.7, top, w0, w0, wt, wt, "trim", bevel=0.05)))
    gl = K.Mesh()
    ph = min(2.6, (top - 1.2) * 0.8)
    for k in range(4):
        p = A.panel(0, -(w0 / 2 + 0.01) + 0.02, 1.0, w0 * 0.68, ph, 0.03, "hull", "trim")
        p.rotate_z(k * math.pi / 2)
        gl.merge(p)
    nodes.append(Node("glyphs", gl))
    if st != "broken":
        nodes.append(Node("cap", A.lathe([(w1 * 0.72, top - 0.02), (0.0, top + 0.6)], 4, "chrome", smooth=False, start=math.pi / 4)))
    else:
        lying = A.taper_box(0, 0, 0.0, h - top, wt, wt, w1, w1, "trim", bevel=0.05)
        lying.merge(A.lathe([(w1 * 0.72, h - top - 0.02), (0.0, h - top + 0.6)], 4, "chrome", smooth=False, start=math.pi / 4))
        lying.rotate_y(math.pi / 2 - 0.05).rotate_z(0.5).translate(0.9, -1.4, wt / 2)
        nodes.append(Node("fallen", lying))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("landmark", (0, 0, 0), "up")], state=st, height_m=h))


# ---------------------------------------------------------------- ruin.arch
def _arc_ring(span, thick, depth, rise_k=1.0, segs=8, role="trim", z_spring=3.0):
    """Closed round arch ring standing in the XZ plane, front face at y=-depth/2."""
    rr = span / 2 + thick / 2
    path = [(rr * math.cos(math.pi - math.pi * i / segs), rr * math.sin(math.pi - math.pi * i / segs) * rise_k) for i in range(segs + 1)]
    prof = [(-thick / 2, -depth / 2), (thick / 2, -depth / 2), (thick / 2, depth / 2), (-thick / 2, depth / 2)]
    # sweep in plan (x, y) with the profile's z as depth, then stand it up
    m = A.sweep(path, [(d, z) for d, z in prof], role)
    m.apply(lambda a: a[:, [0, 2, 1]] * [1, -1, 1])
    m = m.orient_outward()
    return m.translate(0, 0, z_spring)


@register("ruin.arch", V, "structure", {
    "style": S.enum("round", ["round", "corbel", "broken"]), "span": S.num(3.0, 2.0, 4.5),
}, "Freestanding arch: two chamfered piers with moulded bases; round = voussoir ring with a carved keystone; corbel = "
   "stepped corbel vault outline; broken = one pier and a fallen half-ring among blocks.", origin="floor_center")
def arch(P, seed):
    r = rng(seed, "ruin.arch")
    sp, st = P["span"], P["style"]
    pw, depth, spring = 1.0, 1.1, 3.0
    nodes = []
    piers = K.Mesh()
    sides = (-1, 1) if st != "broken" else (-1,)
    for sx in sides:
        cx = sx * (sp / 2 + pw / 2)
        piers.merge(A.stack(cx, 0, [(0.0, pw + 0.3, depth + 0.3, 0.05), (0.4, pw + 0.3, depth + 0.3, 0.05), (0.55, pw, depth, 0.05)], "step"))
        piers.merge(A.taper_box(cx, 0, 0.5, spring + 0.05, pw, depth, pw - 0.06, depth - 0.06, "wall", bevel=0.06))
        piers.merge(A.chamfer_box(cx, 0, spring - 0.2, pw + 0.24, depth + 0.2, 0.25, "trim", bevel=0.05))
    nodes.append(Node("piers", piers))
    if st == "round":
        nodes.append(Node("ring", _arc_ring(sp, pw * 0.9, depth - 0.04, 1.0, 8, "trim", spring)))
        key = K.Mesh()
        key.merge(A.taper_box(0, 0, spring + sp / 2 + 0.05, spring + sp / 2 + 1.05, 0.62, depth + 0.1, 0.8, depth + 0.1, "trim", bevel=0.05))
        key.merge(A.panel(0, -(depth + 0.1) / 2 - 0.03, spring + sp / 2 + 0.2, 0.55, 0.55, 0.04, "frame", "trim"))
        nodes.append(Node("keystone", key))
    elif st == "corbel":
        w = sp + 2 * pw
        pts = [(-w / 2, spring)]
        steps = 4
        for i in range(steps):
            x = -sp / 2 + (sp / 2 - 0.25) * i / steps
            pts += [(x, spring + 0.45 * i), (x, spring + 0.45 * (i + 1))] if i else [(x, spring + 0.45)]
        # build the stepped soffit symmetric
        left = [(-sp / 2, spring)]
        for i in range(steps):
            x0 = -sp / 2 + (sp / 2 - 0.3) * i / steps
            x1 = -sp / 2 + (sp / 2 - 0.3) * (i + 1) / steps
            left += [(x0, spring + 0.5 * (i + 1)), (x1, spring + 0.5 * (i + 1))]
        right = [(-x, z) for x, z in reversed(left)]
        top = spring + 0.5 * steps + 0.7
        outline = [(-w / 2, spring), (-sp / 2 - 0.001, spring)] + left[1:] + right[:-1] + [(sp / 2 + 0.001, spring), (w / 2, spring), (w / 2, top), (-w / 2, top)]
        nodes.append(Node("vault", A.front_prism(outline, -depth / 2, depth / 2, "trim")))
    else:
        half = _arc_ring(sp, pw * 0.9, depth - 0.04, 1.0, 4, "trim", 0.0)
        half.rotate_y(1.2).translate(sp * 0.4, -0.8, 0.5)
        fall = K.Mesh()
        fall.merge(half)
        for i in range(3):
            fall.merge(A.block_chunk(r.uniform(0.0, sp), r.uniform(0.5, 1.6), 0.0, 0.7, 0.55, 0.5, r, "stone", tilt=r.uniform(-0.3, 0.3)))
        nodes.append(Node("fallen", fall))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("passage", (0, 0, 0), "s", width_m=sp)], style=st))


# ---------------------------------------------------------------- ruin.rampart
def _merlons(length, z, y, count, role="trim", w=0.8, d=0.5, hh=0.75):
    """Stepped merlons (a wide lower block under a narrow tapered cap): the desert-city crenellation of the kit."""
    m = K.Mesh()
    for i in range(count):
        x = -length / 2 + length * (i + 0.5) / count
        m.merge(A.frustum(x, y, z, z + hh * 0.5, w, d, w - 0.06, d - 0.04, role))
        m.merge(A.frustum(x, y, z + hh * 0.5 - 0.01, z + hh, w * 0.55, d * 0.8, w * 0.42, d * 0.7, role))
    return m


@register("ruin.rampart", V, "structure", {
    "style": S.enum("straight", ["straight", "corner", "tower", "broken"]), "height": S.num(3.6, 2.0, 5.0),
}, "Rampart on a cell edge: battered outer face, a 2 m walk on top and a crenellated parapet (tapered merlons); "
   "corner = L-shaped quarter; tower = round bastion; broken = a breach with spilled blocks.", origin="floor_center")
def rampart(P, seed):
    r = rng(seed, "ruin.rampart")
    st, h = P["style"], P["height"]
    nodes = []
    prof = [(-1.0, 0.0), (1.25, 0.0), (1.05, h - 0.2), (1.12, h - 0.2), (1.12, h + 0.05), (-1.0, h + 0.05)]
    if st in ("straight", "broken"):
        if st == "straight":
            body = A.sweep([(-CELL / 2, 0.0), (CELL / 2, 0.0)], [(d, z) for d, z in prof], "wall")
            nodes.append(Node("body", body))
            nodes.append(Node("merlons", _merlons(CELL - 0.2, h + 0.05, -0.8, 4)))
        else:
            for sx in (-1, 1):
                pts = [(-1.0, 0.0), (1.25, 0.0), (1.05, h - 0.2), (1.12, h - 0.2), (1.12, h + 0.05), (-1.0, h + 0.05)]
                seg = A.sweep([(sx * 0.45, 0.0), (sx * CELL / 2, 0.0)] if sx > 0 else [(-CELL / 2, 0.0), (-0.45, 0.0)], pts, "wall")
                nodes.append(Node("body_%s" % ("e" if sx > 0 else "w"), seg))
            breach = K.Mesh()
            for i in range(5):
                breach.merge(A.block_chunk(r.uniform(-1.0, 1.0), r.uniform(-1.6, 0.4), r.uniform(0, 0.4), r.uniform(0.6, 0.9),
                                           0.55, 0.45, r, "stone", tilt=r.uniform(-0.4, 0.4)))
            nodes.append(Node("breach", breach))
            nodes.append(Node("merlons", _merlons(CELL - 0.2, h + 0.05, -0.8, 4)))
    elif st == "corner":
        path = [(-CELL / 2, 0.0), (0.0, 0.0), (0.0, CELL / 2)]
        nodes.append(Node("body", A.sweep(path, prof, "wall")))
        m = _merlons(CELL / 2 - 0.2, h + 0.05, -0.8, 2).translate(-CELL / 4, 0, 0)
        m2 = _merlons(CELL / 2 - 0.2, h + 0.05, -0.8, 2)
        m2.rotate_z(math.pi / 2).translate(0, CELL / 4, 0)
        nodes.append(Node("merlons", m.merge(m2)))
    else:
        tower = A.lathe([(0.0, 0.0), (2.3, 0.0), (2.0, h + 1.0), (2.15, h + 1.0), (2.15, h + 1.3), (0.0, h + 1.3)], 10, "wall", smooth=False)
        nodes.append(Node("tower", tower))
        mer = K.Mesh()
        for i in range(8):
            a = TAU * i / 8
            st = _merlons(0.0, h + 1.3, 0.0, 1, w=0.7, d=0.5)
            st.rotate_z(a + math.pi / 2).translate(1.85 * math.cos(a), 1.85 * math.sin(a), 0.0)
            mer.merge(st)
        nodes.append(Node("merlons", mer))
    return finalize(nodes, A.grid_meta("cell_edge", None, A.edge_sockets(), style=st, walk_m=round(h, 3)))


# ---------------------------------------------------------------- ruin.rubble
@register("ruin.rubble", V, "structure", {
    "size": S.enum("small", ["small", "large", "drift", "drums"]),
}, "Collapsed rubble: tumbled dressed blocks and broken stone (small, large pile), blocks half-buried in a drifted sand "
   "mound (drift), or a heap of column drums.", origin="floor_center")
def rubble(P, seed):
    r = rng(seed, "ruin.rubble", P["size"])
    sz = P["size"]
    m = K.Mesh()
    nodes = []
    if sz in ("small", "large"):
        k = 3 if sz == "small" else 7
        spread = 1.0 if sz == "small" else 2.0
        for i in range(k):
            m.merge(A.block_chunk(r.uniform(-spread, spread), r.uniform(-spread * 0.7, spread * 0.7), 0.0 if i < k - 2 else 0.3,
                                  r.uniform(0.6, 1.0), r.uniform(0.45, 0.7), r.uniform(0.4, 0.55), r, "stone",
                                  tilt=r.uniform(-0.35, 0.35)))
        for i in range(2 if sz == "small" else 4):
            m.merge(A.rock(r.uniform(-spread, spread), r.uniform(-spread, spread), 0.12, 0.3, 0.25, 0.2, r, "stone", segs=5, rings=3))
        nodes.append(Node("blocks", m))
    elif sz == "drift":
        mound = A.lathe([(0.0, 0.0), (2.4, 0.0), (1.8, 0.35), (0.9, 0.62), (0.0, 0.7)], 9, "sand", smooth=True, rx=1.0, ry=0.75)
        nodes.append(Node("mound", mound))
        for i in range(2):
            m.merge(A.block_chunk(r.uniform(-1.2, 1.2), r.uniform(-0.6, 0.6), 0.15, 1.0, 0.65, 0.55, r, "stone", tilt=r.uniform(0.2, 0.5)))
        nodes.append(Node("blocks", m))
    else:
        for i in range(4):
            drum = K.lathe([(0.42, 0.0), (0.42, 0.9)], 8, "trim", smooth=True, cap_roles=("trim", "trim"))
            drum.translate(0, 0, -0.45).rotate_x(math.pi / 2).rotate_z(r.uniform(0, TAU))
            drum.translate(r.uniform(-1.2, 1.2), r.uniform(-0.8, 0.8), 0.42 + (0.75 if i == 3 else 0.0))
            m.merge(drum)
        nodes.append(Node("drums", m))
    return finalize(nodes, A.grid_meta("free", None, [], size=sz))


# ---------------------------------------------------------------- ruin.court
@register("ruin.court", V, "shell", {
    "cells_x": S.integer(3, 2, 5), "cells_y": S.integer(3, 2, 5),
    "steps": S.integer(3, 1, 4), "step_h": S.num(0.5, 0.25, 0.6), "step_run": S.num(0.9, 0.6, 1.2),
    "open_s": S.boolean(True), "open_n": S.boolean(False), "open_e": S.boolean(False), "open_w": S.boolean(False),
}, "Sunken court: stepped stone terraces rising outward around a court floor at y = 0 (the player's floor), swept as "
   "one closed stepped profile with mitred corners; open sides leave a 4 m entrance gap centred on that side (door "
   "sockets there).", origin="floor_center")
def court(P, seed):
    cx, cy = P["cells_x"], P["cells_y"]
    W, D = cx * CELL - 2 * P["steps"] * P["step_run"], cy * CELL - 2 * P["steps"] * P["step_run"]
    hw, hd = W / 2, D / 2
    prof = [(0.0, 0.0)]
    for i in range(P["steps"]):
        prof += [(-i * P["step_run"], (i + 1) * P["step_h"]), (-(i + 1) * P["step_run"], (i + 1) * P["step_h"])]
    top = P["steps"] * P["step_h"]
    prof += [(-(P["steps"]) * P["step_run"] - 0.6, top), (-(P["steps"]) * P["step_run"] - 0.6, 0.0)]
    prof[1] = (0.0, P["step_h"])
    prof = [prof[0]] + prof[1:]
    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]          # CCW: S edge, E edge, N edge, W edge
    gaps = {"s": P["open_s"], "e": P["open_e"], "n": P["open_n"], "w": P["open_w"]}
    gw = 2.0
    nodes = []
    if not any(gaps.values()):
        nodes.append(Node("terraces", A.sweep(corners, prof, "step", closed=True)))
    else:
        # walk the ring starting just after the first gap, splitting at every gap
        sides = [("s", corners[0], corners[1]), ("e", corners[1], corners[2]), ("n", corners[2], corners[3]), ("w", corners[3], corners[0])]
        start = next(i for i, (k, _, _) in enumerate(sides) if gaps[k])
        order = sides[start:] + sides[:start]
        runs, cur = [], []
        for idx, (k, a, b) in enumerate(order):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            dx, dy = (b[0] - a[0]), (b[1] - a[1])
            ln = math.hypot(dx, dy)
            ux, uy = dx / ln, dy / ln
            if gaps[k]:
                g1 = (mid[0] + ux * gw, mid[1] + uy * gw)
                g0 = (mid[0] - ux * gw, mid[1] - uy * gw)
                if cur:
                    cur.append(g0)
                    runs.append(cur)
                cur = [g1, b]
            else:
                cur.append(b)
        if cur:
            first_gap_side = order[0]
            a, b = first_gap_side[1], first_gap_side[2]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            cur.append((mid[0] - (b[0] - a[0]) / ln * gw, mid[1] - (b[1] - a[1]) / ln * gw))
            runs.append(cur)
        for i, run in enumerate(runs):
            nodes.append(Node("terraces_%d" % i, A.sweep(run, prof, "step")))
    socks = []
    for k, (x, y, f) in {"s": (0, -hd, "s"), "n": (0, hd, "n"), "e": (hw, 0, "e"), "w": (-hw, 0, "w")}.items():
        if gaps[k]:
            socks.append(A.sock("entrance", (x, y, 0), f, width_m=2 * gw))
    return finalize(nodes, A.grid_meta("cell_block_centre", (cx, cy), socks, floor_m=[round(W, 3), round(D, 3)], rim_m=round(top, 3)))


# ---------------------------------------------------------------- ruin.floor
def bed(cells=1):
    """Joint bed under the slabs: a closed battered block whose top (1 cm above the datum, below the slab top) spans
    the whole cell(s), so the 4 cm joints between neighbouring slabs show sand/moss instead of the sky behind a
    roofless room (round 21: void pixels along every shrine joint). Its top sits above the ground datum, so a floor
    laid on a ground tile does not z-fight; the battered sides keep it off the cuboid gate."""
    s = cells * CELL
    return A.frustum(0, 0, -0.03, 0.01, s - 0.04, s - 0.04, s, s, "dirt")


@register("ruin.floor", V, "arch", {
    "style": S.enum("plain", ["plain", "cracked", "inlay", "ceiling", "block"]),
}, "Paving slab for one RUIN GRID cell (4 x 4 m, 5 cm proud of the ground, chamfered) on a joint bed that fills the "
   "joints with sand/moss: plain; cracked = broken slabs with sand between; inlay = central sun inlay (frame role); "
   "block = 2 x 2 cells; ceiling = coffered slab hung at the storey height facing down (origin stays on the floor "
   "datum).", origin="opening")
def floor(P, seed):
    r = rng(seed, "ruin.floor", P["style"])
    st = P["style"]
    nodes = []
    if st in ("plain", "inlay", "cracked"):
        nodes.append(Node("bed", bed(1)))
    elif st == "block":
        nodes.append(Node("bed", bed(2)))
    if st in ("plain", "inlay"):
        nodes.append(Node("slab", A.chamfer_box(0, 0, 0, CELL - 0.04, CELL - 0.04, 0.05, "floor", bevel=0.03)))
        if st == "inlay":
            inl = K.Mesh().add([(-1.1, -1.1, 0.055), (1.1, -1.1, 0.055), (1.1, 1.1, 0.055), (-1.1, 1.1, 0.055),
                                (-1.1, -1.1, 0.0501), (1.1, -1.1, 0.0501), (1.1, 1.1, 0.0501), (-1.1, 1.1, 0.0501)],
                               [(0, 1, 2, 3), (5, 4, 7, 6), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)],
                               ["frame"] + ["trim"] * 5, False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5)
            nodes.append(Node("inlay", inl.orient_outward()))
    elif st == "block":
        nodes.append(Node("slab", A.chamfer_box(0, 0, 0, 2 * CELL - 0.04, 2 * CELL - 0.04, 0.05, "floor", bevel=0.03)))
    elif st == "cracked":
        m = K.Mesh()
        for i, (x, y) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
            if i == 3:
                continue
            m.merge(A.chamfer_box(x * 1.0 + r.uniform(-0.05, 0.05), y * 1.0 + r.uniform(-0.05, 0.05), 0.0, 1.9, 1.9, 0.05, "floor", bevel=0.03))
        m.merge(A.chamfer_box(1.15, 1.05, 0.0, 1.2, 0.9, 0.04, "floor", bevel=0.02))
        nodes.append(Node("slabs", m))
        nodes.append(Node("sand", A.chamfer_box(0, 0, 0, CELL - 0.1, CELL - 0.1, 0.03, "sand", bevel=0.01)))
    else:
        z = H
        ceil = K.Mesh().add([(-CELL / 2, -CELL / 2, z), (CELL / 2, -CELL / 2, z), (CELL / 2, CELL / 2, z), (-CELL / 2, CELL / 2, z),
                             (-CELL / 2, -CELL / 2, z + 0.25), (CELL / 2, -CELL / 2, z + 0.25), (CELL / 2, CELL / 2, z + 0.25),
                             (-CELL / 2, CELL / 2, z + 0.25)],
                            [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
                            ["ceiling"] + ["trim"] * 5, False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5)
        nodes.append(Node("ceiling", ceil.orient_outward()))
        beams = K.Mesh()
        for sx in (-1, 1):
            beams.merge(A.chamfer_box(sx * (CELL / 2 - 0.25), 0, z - 0.35, 0.5, CELL - 0.02, 0.36, "trim", bevel=0.04))
        nodes.append(Node("beams", beams))
    cells = (2, 2) if st == "block" else (1, 1)
    return Asset(nodes, A.grid_meta("cell_block_centre" if st == "block" else "cell_centre", cells, [], style=st,
                                    datum="ceiling" if st == "ceiling" else "floor"))
