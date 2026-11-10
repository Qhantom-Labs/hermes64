"""DUNGEONKIT temple family (tmpl.*), theme-agnostic (Blender space, +Z up, front faces -Y).

Columns, altar, carved reliefs, the boss door, dais, obelisk, inlaid floor and a temple wall segment on the same
DUNGEON GRID as dgn.*. Carvings are painted (normalized-UV panels of the pack's wall_alt / hull / screen roles), never
modelled detail, so they stay inside N64 budgets. tmpl.boss_door shares the dgn.doorway door anchor and covers the
standard frame room.gd places on every door.
"""
import math

from . import dkit as D
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .gen_dungeon import CUT_H, CUT_W, FRAME_D, grid_meta, grid_floor, panel, sock, stations, light
from .gen_dprops import flame
from .genutil import finalize
from .rng import rng

V = "1.0.0"


def fluted_ring(z, r, flutes=12, depth=0.08):
    pts = []
    for i in range(2 * flutes):
        a = math.pi * i / flutes
        rr = r * (1.0 - depth if i % 2 else 1.0)
        pts.append((rr * math.cos(a), rr * math.sin(a), z))
    return pts


# ---------------------------------------------------------------- tmpl.column
@register("tmpl.column", V, "structure", {
    "height": S.num(5.5, 3.5, 7.5), "state": S.enum("whole", ["whole", "broken"]), "flutes": S.lod(S.integer(10, 6, 14)),
}, "Temple column: square plinth, moulded base, fluted shaft with entasis, echinus capital and abacus slab; broken "
   "= snapped shaft with a jagged top and a fallen drum.", origin="floor_center")
def column(P, seed):
    r = rng(seed, "tmpl.column")
    h = P["height"]
    nodes = []
    base = K.Mesh()
    base.merge(D.bevel_box(0, 0, 0, 1.25, 1.25, 0.35, "stone", bevel=0.05))
    base.merge(K.lathe([(0.0, 0.35), (0.56, 0.35), (0.58, 0.45), (0.5, 0.55), (0.0, 0.55)], 10, "trim", smooth=True))
    nodes.append(Node("base", base))
    top = h - 0.75 if P["state"] == "whole" else h * r.uniform(0.35, 0.5)
    rings = [fluted_ring(0.55, 0.44, P["flutes"]), fluted_ring(0.55 + (top - 0.55) * 0.35, 0.45, P["flutes"]),
             fluted_ring(top, 0.38, P["flutes"])]
    if P["state"] == "broken":
        jag = []
        for i, p in enumerate(rings[-1]):
            jag.append((p[0], p[1], p[2] + 0.22 * math.sin(i * 1.7) + 0.1 * r.uniform(-1, 1)))
        rings[-1] = jag
    shaft = K.loft(rings, "trim", smooth=False)
    nodes.append(Node("shaft", shaft))
    if P["state"] == "whole":
        cap = K.Mesh()
        cap.merge(K.lathe([(0.0, top), (0.4, top), (0.5, top + 0.18), (0.62, top + 0.36), (0.0, top + 0.36)], 10, "frame", smooth=True))
        cap.merge(D.bevel_box(0, 0, top + 0.36, 1.35, 1.35, 0.39, "frame", bevel=0.05))
        nodes.append(Node("capital", cap))
    else:
        drum = K.loft([fluted_ring(-0.35, 0.42, P["flutes"]), fluted_ring(0.35, 0.42, P["flutes"])], "trim", smooth=False)
        drum.rotate_x(math.pi / 2).rotate_z(r.uniform(0, math.pi)).translate(1.3, 0.4, 0.42)
        rub = D.rock_blob(-0.9, -0.6, 0.1, 0.3, 0.25, 0.18, r, "stone", segs=5, rings=3)
        nodes.append(Node("fallen", drum.merge(rub)))
    return finalize(nodes, grid_meta("free", None, [sock("pillar", (0, 0, 0), "up", footprint_m=1.35)], state=P["state"]))


# ---------------------------------------------------------------- tmpl.altar
@register("tmpl.altar", V, "furniture_large", {
    "fire": S.boolean(True, "offering fire in a bronze bowl"),
}, "Altar on a two-step dais: dressed block with painted relief panels on the front and sides, overhanging top slab, "
   "a bronze offering bowl (optionally burning) and candle stubs.", origin="floor_center")
def altar(P, seed):
    m = K.Mesh()
    m.merge(D.bevel_box(0, 0, 0, 3.2, 2.4, 0.22, "step", bevel=0.04))
    m.merge(D.bevel_box(0, 0.1, 0.22, 2.6, 1.7, 0.22, "step", bevel=0.04))
    m.merge(D.bevel_box(0, 0.2, 0.44, 1.8, 0.95, 0.85, "trim", bevel=0.05))
    m.merge(D.bevel_box(0, 0.2, 1.29, 2.05, 1.15, 0.16, "frame", bevel=0.04))
    rel = K.Mesh()
    rel.merge(panel(0, 0.2 - 0.95 / 2 - 0.02, 0.56, 1.5, 0.62, 0.05, "wall_alt", "trim"))
    for sx in (-1, 1):
        p = panel(0, 0, 0.56, 0.7, 0.62, 0.05, "wall_alt", "trim").rotate_z(-sx * math.pi / 2)
        rel.merge(p.translate(sx * (0.9 + 0.02), 0.2, 0))
    bowl = K.lathe([(0.0, 1.45), (0.12, 1.45), (0.3, 1.55), (0.36, 1.68), (0.31, 1.69), (0.0, 1.6)], 8, "metal", smooth=False).translate(0, 0.2, 0)
    nodes = [Node("altar", m), Node("reliefs", rel), Node("bowl", bowl)]
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up", interact="offer")])
    if P["fire"]:
        nodes.append(Node("flame", flame(0, 0.2, 1.6, 0.55, 0.22, "fire", segs=6)))
        # no self-bake: a pool from a bowl just above the slab lands almost only on the up-facing top, which then
        # renders as a flat saturated amber sheet (n64 neon measure, round 18-19); the runtime emitter lights it
        meta["emitter"] = {"offset_gltf": [0.0, 1.95, -0.2], "radius_m": 6.0, "warm": True}
    cs = K.Mesh()
    for sx in (-1, 1):
        cs.merge(K.cylinder(sx * 0.75, 0.0, 1.45, 0.05, 0.22, 5, "paper"))
    nodes.append(Node("candles", cs))
    return finalize(nodes, meta)


# ---------------------------------------------------------------- tmpl.relief
@register("tmpl.relief", V, "arch", {
    "width": S.num(2.8, 1.6, 3.6), "height": S.num(2.2, 1.2, 3.0),
}, "Carved relief wall panel: painted relief slab (original motif) in a dressed frame with a lintel and a small sill, "
   "mounted on a wall face. Origin on the wall face at floor level; panel centred at 2.3 m.", wall_mounted=True,
   origin="opening")
def relief(P, seed):
    w, h = P["width"], P["height"]
    zc = 2.3
    z0 = zc - h / 2
    pan = panel(0, -0.07, z0, w, h, 0.1, "wall_alt", "trim")
    fo = K.rounded_rect2d(w + 0.42, h + 0.42, 0.03, 1)
    fi = K.rounded_rect2d(w, h, 0.02, 1)
    fr = K.prism([(x, z + zc) for x, z in fo], 0.0, 0.18, "frame", holes=[[(x, z + zc) for x, z in fi]]).rotate_x(math.pi / 2)
    lint = D.bevel_box(0, -0.12, zc + h / 2 + 0.21, w + 0.8, 0.26, 0.24, "trim", bevel=0.04)
    sill = D.bevel_box(0, -0.1, z0 - 0.33, w + 0.5, 0.22, 0.12, "trim", bevel=0.03)
    return Asset([Node("relief", pan), Node("frame", fr.merge(lint, sill))],
                 grid_meta("wall_face", None, [sock("mount", (0, 0, 0), "s", fits="wall")]))


# ---------------------------------------------------------------- tmpl.boss_door
@register("tmpl.boss_door", V, "structure", {
    "state": S.enum("closed", ["closed", "open"]),
}, "Boss door: a towering stepped surround (jamb towers, sigil lintel, pediment, braziers' brackets) with sigil-painted "
   "arched leaves under a heavy iron lock. Shares the dgn.doorway door anchor and covers the standard frame; open = "
   "leaves and lock gone, dark passage beyond.", origin="opening")
def boss_door(P, seed):
    ow, oh = D.DOOR_W - 0.1, D.DOOR_H - 0.05
    r = ow / 2
    spring = oh - r
    front = FRAME_D + 0.38        # surround front face, 0.38 m proud of the standard frame
    nodes = []
    sur = K.Mesh()
    for sx in (-1, 1):
        sur.merge(D.bevel_box(sx * 1.85, -0.25 - front / 2 + 0.25, 0.0, 1.0, front + 0.0, 4.1, "trim", bevel=0.06))
        sur.merge(K.box(sx * 1.85, -front / 2, 4.1 + 0.175, 1.2, front + 0.1, 0.35, "frame"))
        sur.merge(K.box(sx * 1.85, -front / 2, 0.225, 1.2, front + 0.1, 0.45, "stone"))
    # arch head between the towers (closed U ring, covers the frame head)
    head_o = [(-1.35, 0.0), (-r, 0.0), (-r, spring)]
    for i in range(1, 8):
        a = math.pi - math.pi * i / 8
        head_o.append((r * math.cos(a), spring + r * math.sin(a)))
    head_o += [(r, spring), (r, 0.0), (1.35, 0.0), (1.35, 4.45), (-1.35, 4.45)]
    head = K.prism(head_o, FRAME_D - 0.02, front, "frame").rotate_x(math.pi / 2)
    sur.merge(head)
    nodes.append(Node("surround", sur))
    # sigil lintel and pediment
    lint = panel(0, -front - 0.06, 4.45, 3.2, 0.95, 0.16, "hull", "trim")
    ped_o = [(-2.45, 5.4), (2.45, 5.4), (0.0, 6.35)]
    ped = K.prism(ped_o, front - 0.05, front + 0.12, "trim").rotate_x(math.pi / 2)
    cor = D.bevel_box(0, -front / 2, 5.4 - 0.05, 4.9, front + 0.2, 0.18, "frame", bevel=0.04)
    nodes.append(Node("lintel", lint.merge(ped, cor)))
    if P["state"] == "closed":
        leaf_o = [(-r, 0.0), (r, 0.0), (r, spring)]
        for i in range(1, 8):
            a = math.pi * i / 8
            leaf_o.append((r * math.cos(a), spring + r * math.sin(a)))
        leaf_o.append((-r, spring))
        leaf = K.prism(leaf_o, 0.0, 0.16, "door").rotate_x(math.pi / 2).translate(0, -FRAME_D / 2 + 0.08, 0)
        # sigil face: a normalized-UV slab just in front of the leaf
        sig = panel(0, -FRAME_D / 2 - 0.1, 0.25, ow - 0.25, oh - 0.5, 0.04, "hull", "door")
        lock = K.Mesh()
        lock.merge(D.bevel_box(0, -FRAME_D / 2 - 0.22, 1.05, 0.6, 0.2, 0.55, "metal", bevel=0.06))
        lock.merge(K.torus(0.2, 0.05, 6, 3, "metal").rotate_x(math.pi / 2).translate(0, -FRAME_D / 2 - 0.22, 1.7))
        lock.merge(K.box(0, -FRAME_D / 2 - 0.33, 1.2, 0.1, 0.02, 0.18, "opening"))
        for sx in (-1, 1):
            lock.merge(K.tube([(sx * 0.95, -FRAME_D / 2 - 0.15, 0.4), (sx * 0.45, -FRAME_D / 2 - 0.25, 1.0), (sx * 0.2, -FRAME_D / 2 - 0.24, 1.2)],
                              0.05, 4, "metal", smooth=False))
        nodes += [Node("leaf", leaf), Node("sigil", sig), Node("lock", lock)]
    else:
        void = K.Mesh().add([(-r, 0.4, 0.0), (r, 0.4, 0.0), (r, 0.4, oh), (-r, 0.4, oh)], [(0, 1, 2, 3)], "opening", False)
        nodes.append(Node("dark", void, "card"))
    socks = [sock("door", (0, 0, 0), "s", fits="dgn.doorway", covers_m=[4.9, 6.35], state=P["state"], boss=True)]
    return Asset(nodes, grid_meta("door_anchor", None, socks, state=P["state"]))


# ---------------------------------------------------------------- tmpl.dais
@register("tmpl.dais", V, "structure", {
    "size_cells": S.integer(1, 1, 2), "steps": S.integer(3, 1, 4),
}, "Stepped temple dais on the grid (1 or 2 cells square): stacked dressed courses with a carved border on the top "
   "platform.", origin="floor_center")
def dais(P, seed):
    s = D.CELL * P["size_cells"] - 0.8
    m = K.Mesh()
    for k in range(P["steps"]):
        w = s - 0.9 * k
        m.merge(D.bevel_box(0, 0, 0.25 * k, w, w, 0.25 + (0.0 if k < P["steps"] - 1 else 0.0), "step", bevel=0.04))
    top = 0.25 * P["steps"]
    wt = s - 0.9 * (P["steps"] - 1)
    bd = K.Mesh()
    bd.merge(panel(0, 0, top, wt - 0.6, wt - 0.6, 0.012, "trim"))
    return finalize([Node("dais", m), Node("inlay", bd)], grid_meta("free", (P["size_cells"], P["size_cells"]),
                                                                    [sock("walk_top", (0, top, 0), "up", height_m=top)]))


# ---------------------------------------------------------------- tmpl.obelisk
@register("tmpl.obelisk", V, "structure", {
    "height": S.num(4.0, 2.5, 6.0),
}, "Carved obelisk: tapered square shaft with chamfered edges, a pyramidion cap, softly glowing glyph panels on its "
   "four faces, on a stepped plinth.", origin="floor_center")
def obelisk(P, seed):
    h = P["height"]
    m = K.Mesh()
    m.merge(D.bevel_box(0, 0, 0, 1.5, 1.5, 0.3, "stone", bevel=0.05))
    m.merge(D.bevel_box(0, 0, 0.3, 1.15, 1.15, 0.3, "trim", bevel=0.05))
    shaft = D.taper_loft(0, 0, [0.6, h], [(0.38, 0.38), (0.26, 0.26)], "trim", bevel=0.05)
    tip = K.loft([K.ring3d(0, 0, h, K.rounded_rect2d(0.5, 0.5, 0.0)), K.ring3d(0, 0, h + 0.45, K.rounded_rect2d(0.02, 0.02, 0.0))],
                 "frame", smooth=False)
    gl = K.Mesh()
    for k in range(4):
        p = panel(0, -0.34, 1.1, 0.42, h * 0.55, 0.03, "screen", "trim")
        gl.merge(p.rotate_z(k * math.pi / 2))
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up")])
    meta["emitter"] = {"offset_gltf": [0, round(h * 0.5, 3), 0], "radius_m": 2.5, "warm": False}
    return finalize([Node("obelisk", m.merge(shaft, tip)), Node("glyphs", gl)], meta)


# ---------------------------------------------------------------- tmpl.floor
@register("tmpl.floor", V, "shell", {
    "cells": S.integer(2, 1, 3), "medallion": S.num(3.0, 1.5, 5.0),
}, "Temple floor tile (1-3 cells square): flagstones framed by a dressed border with a painted relief medallion "
   "inlaid at the centre.", origin="terrain_center")
def temple_floor(P, seed):
    e = D.CELL * P["cells"] / 2
    md = P["medallion"] / 2
    f = grid_floor(stations(-e, e, 2.0, (-e + 0.6, e - 0.6, -md - 0.25, md + 0.25)), stations(-e, e, 2.0, (-e + 0.6, e - 0.6, -md - 0.25, md + 0.25)),
                   lambda x, y: True, 0.0, lambda x, y: "trim" if (abs(x) > e - 0.6 or abs(y) > e - 0.6 or (abs(x) < md + 0.25 and abs(y) < md + 0.25)) else "floor")
    med = K.Mesh()
    v = [(-md, -md, 0.012), (md, -md, 0.012), (md, md, 0.012), (-md, md, 0.012)]
    med.add(v, [(0, 1, 2, 3)], "wall_alt", False, [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    return Asset([Node("floor", f, "shell"), Node("medallion", med, "card")],
                 grid_meta("cell_block_centre", (P["cells"], P["cells"]), [sock("floor", (0, 0, 0), "up")]))


# ---------------------------------------------------------------- tmpl.wall
@register("tmpl.wall", V, "shell", {
    "columns": S.boolean(True, "engaged half-columns at both ends"), "frieze": S.boolean(True),
    "panel": S.boolean(True, "carved relief panel in the middle"),
}, "Temple wall segment for one cell edge: the dungeon relief wall sheet with engaged columns at its ends, a painted "
   "frieze band under the cornice and a carved relief panel. Origin on the cell boundary at floor level.",
   origin="opening_floor")
def temple_wall(P, seed):
    L = D.CELL
    sheet = D.wall_sheet(L).translate(-L / 2, -D.WALL_T, 0)
    nodes = [Node("wall", sheet, "shell")]
    det = K.Mesh()
    if P["frieze"]:
        det.merge(panel(0, -D.WALL_T - 0.03, D.H - 1.25, L - 0.2, 0.6, 0.06, "wall_alt", "trim"))
    if P["panel"]:
        det.merge(panel(0, -D.WALL_T - 0.04, 1.0, 1.7, 1.9, 0.08, "wall_alt", "trim"))
    if det.f:
        nodes.append(Node("carving", det))
    if P["columns"]:
        cols = K.Mesh()
        for sx in (-1, 1):
            c = K.Mesh()
            c.merge(D.bevel_box(0, 0, 0, 0.75, 0.75, 0.4, "stone", bevel=0.04))
            c.merge(K.loft([fluted_ring(0.4, 0.3, 8), fluted_ring(D.H - 0.75, 0.27, 8)], "trim", smooth=False))
            c.merge(D.bevel_box(0, 0, D.H - 0.75, 0.8, 0.8, 0.3, "frame", bevel=0.04))
            cols.merge(c.translate(sx * (L / 2 - 0.42), -D.WALL_T - 0.05, 0))
        nodes.append(Node("columns", cols))
    return Asset(nodes, grid_meta("cell_edge", (1, 0), [sock("wall", (0, -D.WALL_T, 0), "s")]))
