"""MEDIEVALKIT village architecture, part 2 (vlg.*): tavern, smithy, mill, chapel, market stall, well, bridge,
gatehouse, town wall, fences, stairs, and the interior set (room shell, beamed ceiling, hearth, the shared doorway).

Conventions as in gen_medievalkit_village (lot pieces, cell-edge pieces with wall_end sockets at +-2 m, room grid).
`door: doorway` on a building omits its own door leaf/frame: the door socket then takes the room's arch.door piece
(vlg.doorway, placed by room.gd on the declared door) so enterable facades and interiors share one door.
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from . import gen_medievalkit_core as M
from .gen_medievalkit_village import (V, bays, chimney, corner_posts, door_set, panel_local, plinth, roof_for, turn90,
                                      wall_beam, wall_map, window_set)
from .rng import rng

DOOR_MODE = S.enum("leaf", ["leaf", "doorway"], "leaf: own plank door; doorway: the room's arch.door (vlg.doorway) fills it")


def jit(meshes, seed, lean, roof_keys=("roof",)):
    for k, m in meshes.items():
        if not m.f:
            continue
        if k in roof_keys:
            M.jitter(m, seed * 11 + 3, lean, axes=(0.6, 0.6, 1.0), keep_z0=False)
        elif k != "walls":
            M.jitter(m, seed * 7 + len(k), lean * 0.5, keep_z0=True)


def nodes_of(meshes):
    return [M.solid(k, m) for k, m in meshes.items() if m.f]


def lantern(x, y, z, out=(0.0, -1.0, 0.0), arm=0.45):
    """Wall lantern: iron bracket arm + a small glowing cage. Returns (mesh, bake light pos)."""
    o = np.asarray(out, dtype=np.float64)
    p0 = np.array([x, y, z])
    p1 = p0 + o * arm
    m = K.Mesh()
    m.merge(M.beam(tuple(p0 - o * 0.05), tuple(p1), 0.05, 0.05, "metal", out=(0.0, 0.0, 1.0), bevel=0.1, embed=0.0))
    m.merge(M.octa_box(p1[0], p1[1], z - 0.42, 0.22, 0.22, 0.34, "light", chamfer=0.05, top_role="metal", top_bevel=0.03))
    m.merge(M.chamfer_box(p1[0], p1[1], z - 0.1, 0.28, 0.28, 0.07, "metal", bevel=0.02))
    return m, [float(p1[0]), float(p1[1]), float(z - 0.25)]


def blank_sign(x, y, z, out=(0.0, -1.0, 0.0), w=0.8, h=0.6, arm=1.1):
    """Projecting sign bracket with a BLANK hanging board (paper face, never text): the user paints their own."""
    o = np.asarray(out, dtype=np.float64)
    p0 = np.array([x, y, z])
    p1 = p0 + o * arm
    m = K.Mesh()
    m.merge(M.beam(tuple(p0 - o * 0.05), tuple(p1), 0.09, 0.09, "frame", out=(0.0, 0.0, 1.0), bevel=0.25, embed=0.0))
    m.merge(M.beam(tuple(p0 - o * 0.05 - np.array([0, 0, 0.55])), tuple(p0 + o * arm * 0.6 - np.array([0, 0, 0.02])), 0.07, 0.07,
                   "frame", out=(0.0, 0.0, 1.0), bevel=0.25, embed=0.0))
    c = p0 + o * (arm * 0.62)
    side = np.cross(o, (0.0, 0.0, 1.0))
    for s_ in (-1, 1):
        a = c + side * 0.0 + o * (s_ * w * 0.38)
        m.merge(M.beam(tuple(a - np.array([0, 0, 0.02])), tuple(a - np.array([0, 0, 0.22])), 0.03, 0.03, "metal", out=tuple(side), bevel=0.0, embed=0.0))
    board = K.Mesh()
    v, f = [], []
    hw = w / 2
    zt = z - 0.22
    zb = zt - h
    corners = [(-hw, zb), (hw, zb), (hw, zt), (-hw, zt)]
    for t in (-0.03, 0.03):
        for a, zz in corners:
            p = c + o * a + side * t
            v.append((p[0], p[1], zz))
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    uv = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)]), ("n", [(0, 1), (1, 1), (1, 0), (0, 0)])] + [None] * 4
    board.add(v, f, ["paper", "paper", "frame", "frame", "frame", "frame"], False, uv)
    m.merge(board.orient_outward())
    return m


# ---------------------------------------------------------------- vlg.tavern
@register("vlg.tavern", V, "building", {
    "width": S.num(9.0, 7.0, 11.0, "front width (eaves to the street)"),
    "depth": S.num(6.0, 5.0, 7.5),
    "roof": S.enum("tiles", ["tiles", "thatch", "slate"]),
    "sign": S.boolean(True, "projecting bracket with a blank hanging sign board"),
    "door": DOOR_MODE,
    "lean": S.num(0.03, 0.0, 0.08),
}, "Two-storey village inn: rubble ground floor, jettied whitewashed upper storey with oak framing and braces, deep "
   "clay-tile (or thatch / slate) roof, external stone chimney, a projecting bracket with a BLANK sign board, a door "
   "lantern baked warm, wide tap-room windows. Door socket on the threshold.", origin="lot_centre")
def tavern(P, seed):
    W, D = P["width"], P["depth"]
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stonework": K.Mesh(), "fittings": K.Mesh()}
    h1, jet = 2.9, 0.5
    lower = M.Body(D, W, h1, h1 + 0.01, taper=0.0, gable=False)
    meshes["walls"].merge(lower.mesh("wall_alt", rows=(0.5, 1.5)))
    up_eave = h1 + 2.4
    upper = M.Body(D + jet, W + 0.3, up_eave, up_eave + 2.6 * (D / 6.0) ** 0.5, taper=0.01, z0=h1 - 0.05)
    meshes["walls"].merge(upper.mesh("wall", rows=(h1 + 1.0,)).translate(-jet / 2, 0.0, 0.0))
    sb = M.Shifted(upper, -jet / 2, 0.0)
    meshes["stonework"].merge(plinth(lower, 0.3))
    a_door = -W / 2 + 2.2
    if P["door"] == "leaf":
        meshes["fittings"].merge(door_set(lower, "-x", a_door, 1.2, 2.25, "arch", frame_role="trim"))
    for a in (a_door + 2.1, a_door + 4.4):
        if a < W / 2 - 0.8:
            meshes["fittings"].merge(window_set(lower, "-x", a, 0.95, 1.2, 1.05, frame_role="frame"))
    for a in bays(W, 4)[1:-1]:
        meshes["fittings"].merge(window_set(sb, "-x", a, h1 + 0.8, 0.7, 0.95, frame_role="frame"))
    # jetty: bressumer + brackets, upper framing (posts, rail, plate, two braced bays)
    xb = -D / 2 - jet + 0.06
    meshes["frame"].merge(M.beam((xb, -W / 2 - 0.12, h1 - 0.02), (xb, W / 2 + 0.12, h1 - 0.02), 0.26, 0.22, "frame",
                                 out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
    for y in bays(W - 0.4, 3):
        meshes["frame"].merge(M.beam((-D / 2 + 0.05, y, h1 - 0.9), (xb + 0.05, y, h1 - 0.2), 0.16, 0.16, "frame",
                                     out=(0.0, 1.0, 0.0), bevel=0.25, embed=0.0))
    ys = bays(W + 0.3 - 0.3, 5)
    for y in ys:
        meshes["frame"].merge(wall_beam(sb, "-x", y, h1 + 0.1, y, up_eave - 0.05, w=0.18))
    meshes["frame"].merge(wall_beam(sb, "-x", ys[0], h1 + 0.68, ys[-1], h1 + 0.68, w=0.18))
    meshes["frame"].merge(wall_beam(sb, "-x", ys[0], up_eave - 0.1, ys[-1], up_eave - 0.1, w=0.2))
    for y0, y1 in ((ys[0], ys[1]), (ys[-2], ys[-1])):
        meshes["frame"].merge(wall_beam(sb, "-x", y0, h1 + 0.75, y1, up_eave - 0.18, w=0.14))
    for side in ("-y", "+y"):
        hw_ = upper.hwz(up_eave) - 0.15
        meshes["frame"].merge(wall_beam(sb, side, -hw_, up_eave - 0.08, hw_, up_eave - 0.08, w=0.2))
        meshes["frame"].merge(wall_beam(sb, side, 0.0, up_eave, 0.0, upper.ridge - 0.3, w=0.18))
    rb = M.Body(D + jet, W + 0.3, up_eave, upper.ridge, taper=0.0)
    meshes["roof"].merge(roof_for(rb, P["roof"], overhang=0.42, gable_overhang=0.35, sag=0.05).translate(-jet / 2, 0.0, 0.0))
    meshes["stonework"].merge(chimney(0.4, W / 2 + 0.35, 0.0, upper.ridge + 0.8, "wall_alt", "trim", w=1.2, d=0.8))
    lights = []
    lm, lp = lantern(-D / 2 - 0.02, a_door + 0.95, 2.45, out=(-1.0, 0.0, 0.0), arm=0.4)
    meshes["fittings"].merge(lm)
    lights.append({"pos": lp, "radius": 3.2, "strength": 0.9})
    if P["sign"]:
        meshes["fittings"].merge(blank_sign(-D / 2 - jet - 0.02, a_door - 1.05, h1 + 0.55, out=(-1.0, 0.0, 0.0)))
    jit(meshes, seed, P["lean"])
    door_pt = lower.surf("-x", a_door, 0.0)
    pts = turn90(list(meshes.values()), [door_pt] + [tuple(L["pos"]) for L in lights])
    for L, p in zip(lights, pts[1:]):
        L["pos"] = list(p)
    lot = [2.0 * math.ceil((W + 1.5) / 2.0), 2.0 * math.ceil((D + jet + 1.5) / 2.0)]
    dw, dh = (1.2, 2.25) if P["door"] == "leaf" else M.DOORWAY
    socks = [M.sock("door", M.door_out(pts[0], P["door"]), "s", width_m=dw, height_m=dh, needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes_of(meshes), {"roof": P["roof"], "lot_m": lot, "door_mode": P["door"]}, "lot_centre",
                      sockets=socks, lights=lights, ground=False)


# ---------------------------------------------------------------- vlg.smithy
@register("vlg.smithy", V, "building", {
    "width": S.num(7.0, 6.0, 9.0), "depth": S.num(5.0, 4.5, 6.0),
    "roof": S.enum("slate", ["slate", "tiles", "thatch"]),
    "door": DOOR_MODE, "lean": S.num(0.025, 0.0, 0.08),
}, "Village smithy: rubble forge-house with a slate roof and an open-fronted lean-to workshop on timber posts, a "
   "stone forge with a glowing fire bed (baked warm pool), hood and tall chimney.", origin="lot_centre")
def smithy(P, seed):
    W, D = P["width"], P["depth"]
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stonework": K.Mesh(), "fittings": K.Mesh()}
    body = M.Body(D, W, 2.7, 2.7 + 1.9, taper=0.01)
    meshes["walls"].merge(body.mesh("wall_alt", rows=(0.5, 1.5)))
    meshes["stonework"].merge(plinth(body, 0.25))
    meshes["roof"].merge(roof_for(body, P["roof"], overhang=0.35, gable_overhang=0.25, sag=0.03))
    a_door = -W / 4
    if P["door"] == "leaf":
        meshes["fittings"].merge(door_set(body, "-x", a_door, 1.1, 2.1, "lintel", frame_role="frame", step=False))
    meshes["fittings"].merge(window_set(body, "+x", 0.0, 1.1, 0.7, 0.7, frame_role="frame", shutters=True))
    # lean-to workshop on the front: sloping slab on three posts
    x0, x1 = -D / 2, -D / 2 - 2.3
    roof_role = {"slate": "hull", "tiles": "hull_alt", "thatch": "roof"}[P["roof"]]
    z_hi, z_lo = 2.55, 2.05
    pts = [(x0 + 0.1, -W / 2 - 0.3, z_hi), (x1 - 0.3, -W / 2 - 0.3, z_lo), (x1 - 0.3, W / 2 + 0.3, z_lo), (x0 + 0.1, W / 2 + 0.3, z_hi)]
    top = [(p[0], p[1], p[2] + 0.12) for p in pts]
    lean = K.Mesh().add(pts + top, [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], roof_role, False)
    meshes["roof"].merge(M.roof_uvs(lean.orient_outward()))
    for y in (-W / 2 + 0.25, 0.4, W / 2 - 0.25):
        meshes["frame"].merge(M.post(x1 + 0.05, y, 0.0, z_lo + 0.05, 0.12, 0.1, "frame", sides=6))
    meshes["frame"].merge(M.beam((x1 + 0.05, -W / 2, z_lo - 0.02), (x1 + 0.05, W / 2, z_lo - 0.02), 0.16, 0.16, "frame",
                                 out=(0.0, 0.0, -1.0), bevel=0.25, embed=0.0))
    # forge: stone hearth with a fire bed, hood, chimney through the lean-to and past the eave
    fy = W / 4
    fx = x0 - 0.7
    meshes["stonework"].merge(M.chamfer_box(fx, fy, 0.0, 1.3, 1.4, 0.85, "wall_alt", bevel=0.06, top_role="step"))
    meshes["fittings"].merge(M.chamfer_box(fx, fy, 0.84, 0.8, 0.9, 0.06, "fire", bevel=0.02))
    meshes["stonework"].merge(M.octa_box(fx + 0.25, fy, 1.55, 0.9, 1.0, 0.7, "wall_alt", chamfer=0.15, top_bevel=0.2))
    meshes["stonework"].merge(chimney(fx + 0.3, fy, 2.2, body.ridge + 0.5, "wall_alt", "trim", w=0.7, d=0.7))
    lights = [{"pos": [fx, fy, 1.1], "radius": 3.0, "strength": 1.0}]
    jit(meshes, seed, P["lean"])
    door_pt = body.surf("-x", a_door, 0.0)
    pts2 = turn90(list(meshes.values()), [door_pt, tuple(lights[0]["pos"])])
    lights[0]["pos"] = list(pts2[1])
    lot = [2.0 * math.ceil((W + 1.0) / 2.0), 2.0 * math.ceil((D + 2.6 + 1.0) / 2.0)]
    dw, dh = (1.1, 2.1) if P["door"] == "leaf" else M.DOORWAY
    socks = [M.sock("door", M.door_out(pts2[0], P["door"]), "s", width_m=dw, height_m=dh, needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes_of(meshes), {"lot_m": lot, "door_mode": P["door"]}, "lot_centre", sockets=socks, lights=lights, ground=False)


# ---------------------------------------------------------------- vlg.mill
@register("vlg.mill", V, "building", {
    "kind": S.enum("windmill", ["windmill", "watermill"]),
    "sail_angle": S.num(20.0, 0.0, 90.0, "windmill sail rotation (degrees)"),
    "door": DOOR_MODE, "lean": S.num(0.025, 0.0, 0.08),
}, "Village mill: a tapered whitewashed tower mill with a stone footing, thatched cap and four lattice sails, or a "
   "rubble watermill with a paddle wheel on its gable.", origin="lot_centre")
def mill(P, seed):
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stonework": K.Mesh(), "fittings": K.Mesh()}
    lights = []
    if P["kind"] == "windmill":
        R0, R1, H = 2.6, 1.95, 7.2
        zb = 0.8
        meshes["walls"].merge(K.lathe([(R0, 0.0), (R0 - (R0 - R1) * zb / H, zb), (R1, H)], 8, "wall", smooth=False,
                                      roles=["wall_alt", "wall"], start=math.pi / 8))
        meshes["roof"].merge(M.cone_roof(R1, H, 2.6, "roof", overhang=0.35, droop=0.2, thick=0.3, segs=8, flare=0.3, start=math.pi / 8))
        axle = M.beam((0.0, -R1 + 0.4, H - 0.4), (0.0, -R1 - 0.55, H - 0.4), 0.32, 0.32, "frame", out=(0.0, 0.0, 1.0), bevel=0.3, embed=0.0)
        meshes["frame"].merge(axle)
        for k in range(4):
            a = math.radians(P["sail_angle"] + 90.0 * k)
            d = np.array([math.cos(a), 0.0, math.sin(a)])
            side = np.array([-math.sin(a), 0.0, math.cos(a)])
            c = np.array([0.0, -R1 - 0.45, H - 0.4])
            tip = c + d * 4.4
            meshes["frame"].merge(M.beam(tuple(c + d * 0.1), tuple(tip), 0.16, 0.14, "frame", out=(0.0, -1.0, 0.0), bevel=0.25, embed=0.0))
            q = [c + d * 1.0 + side * 0.08, c + d * 4.3 + side * 0.08, c + d * 4.3 + side * 1.0, c + d * 1.0 + side * 0.85]
            v = [tuple(p + np.array([0, 0.03, 0])) for p in q] + [tuple(p + np.array([0, -0.03, 0])) for p in q]
            sail = K.Mesh().add(v, [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)],
                                ["fabric", "fabric", "frame", "frame", "frame", "frame"], False,
                                [("n", [(0, 0), (1, 0), (1, 1), (0, 1)]), ("n", [(0, 1), (1, 1), (1, 0), (0, 0)])] + [None] * 4)
            meshes["fittings"].merge(sail.orient_outward())
        c8 = math.cos(math.pi / 8)          # octagon face distance = R cos(22.5 deg)
        body = M.Body(2 * R0 * c8, 2 * R0 * c8, 2.6, 2.61, taper=(R0 - R1) * c8 / H, gable=False)
        if P["door"] == "leaf":
            meshes["fittings"].merge(door_set(body, "-y", 0.0, 1.0, 2.0, "arch", frame_role="trim"))
        meshes["fittings"].merge(window_set(body, "-y", 0.0, 3.6, 0.5, 0.6, frame_role="frame", lintel=False))
        meshes["fittings"].merge(window_set(body, "+x", 0.0, 2.2, 0.5, 0.6, frame_role="frame", lintel=False))
        door_pt = (0.0, -R0 * c8, 0.0)
        lot = [8.0, 8.0]
        jit(meshes, seed, P["lean"])
    else:
        W, D = 7.0, 5.0
        body = M.Body(W, D, 3.2, 5.2, taper=0.01)        # gable front -y; wheel on the +x side wall
        meshes["walls"].merge(body.mesh("wall_alt", rows=(0.5, 1.6)))
        meshes["stonework"].merge(plinth(body, 0.35))
        meshes["roof"].merge(roof_for(body, "slate", overhang=0.3, gable_overhang=0.3, sag=0.03))
        if P["door"] == "leaf":
            meshes["fittings"].merge(door_set(body, "-y", -1.2, 1.1, 2.15, "arch", frame_role="trim"))
        meshes["fittings"].merge(window_set(body, "-y", 1.4, 1.2, 0.7, 0.8, frame_role="trim", shutters=True))
        meshes["fittings"].merge(window_set(body, "-y", 0.0, 3.6, 0.5, 0.6, frame_role="trim", lintel=False))
        # wheel: rim ring + 8 paddles + axle, on the +x wall
        cx, cz, R = body.hw + 0.55, 2.0, 1.9
        rim = M.ring_path_solid([(R * math.cos(a), R * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)],
                                -0.12, 0.12, 0.16, "frame")
        rim.apply(lambda a: a[:, [2, 0, 1]])          # ring in the y-z plane (axis along x)
        meshes["frame"].merge(rim.orient_outward().translate(cx, 0.0, cz))
        for k in range(8):
            a = 2 * math.pi * k / 8 + 0.2
            p_in = (cx, (R - 0.75) * math.cos(a), cz + (R - 0.75) * math.sin(a))
            p_out = (cx, (R + 0.25) * math.cos(a), cz + (R + 0.25) * math.sin(a))
            meshes["fittings"].merge(M.beam(p_in, p_out, 0.6, 0.06, "body", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.03))
        meshes["frame"].merge(M.beam((body.hw - 0.1, 0.0, cz), (cx + 0.35, 0.0, cz), 0.26, 0.26, "frame", out=(0.0, 0.0, 1.0), bevel=0.3, embed=0.0))
        door_pt = body.surf("-y", -1.2, 0.0)
        lot = [10.0, 6.0]
        jit(meshes, seed, P["lean"])
    dw, dh = (1.0, 2.0) if P["door"] == "leaf" else M.DOORWAY
    socks = [M.sock("door", M.door_out(door_pt, P["door"]), "s", width_m=dw, height_m=dh, needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes_of(meshes), {"kind": P["kind"], "lot_m": lot, "door_mode": P["door"]}, "lot_centre", sockets=socks, lights=lights,
                      ground=False)


# ---------------------------------------------------------------- vlg.chapel
@register("vlg.chapel", V, "building", {
    "length": S.num(9.0, 7.0, 12.0), "width": S.num(5.5, 4.5, 7.0),
    "bellcote": S.boolean(True), "apse": S.boolean(True),
    "door": DOOR_MODE, "lean": S.num(0.015, 0.0, 0.05),
}, "Village chapel: rubble nave with dressed quoins and buttresses, steep slate roof, pointed-arch door, lancet "
   "windows of leaded glass, a rounded apse and a gable bell-cote with a bell under a simple cross.", origin="lot_centre")
def chapel(P, seed):
    L, W = P["length"], P["width"]
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stonework": K.Mesh(), "fittings": K.Mesh()}
    eave = 3.7
    body = M.Body(W, L, eave, eave + 0.75 * W, taper=0.006)          # gable front = -y
    meshes["walls"].merge(body.mesh("wall_alt", rows=(0.5, 1.8)))
    meshes["stonework"].merge(plinth(body, 0.45, role="trim", grow=0.1))
    meshes["roof"].merge(roof_for(body, "slate", overhang=0.3, gable_overhang=0.2, sag=0.02))
    if P["door"] == "leaf":
        meshes["fittings"].merge(door_set(body, "-y", 0.0, 1.3, 2.7, "pointed", frame_role="trim"))
    # round window over the door, lancets on the long walls
    ow = K.prism([(0.42 * math.cos(a), 0.42 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)], -0.05, 0.05, "glass")
    ow.apply(lambda a: a[:, [0, 2, 1]])
    ow.uv = [("n", [((p[0] + 0.42) / 0.84, (p[2] + 0.42) / 0.84) for p in (ow.v[i] for i in fc)]) for fc in ow.f]
    ow.translate(0.0, 0.0, eave + 0.55)
    meshes["fittings"].merge(wall_map(body, "-y", ow))
    for side in ("-x", "+x"):
        for u in (-L / 4, L / 4):
            lan = K.prism(M.opening_outline("pointed", 0.6, 1.8, 6), -0.05, 0.04, "glass")
            lan.apply(lambda a: a[:, [0, 2, 1]])
            lan.uv = [("n", [((p[0] + 0.3) / 0.6, p[2] / 1.8) for p in (lan.v[i] for i in fc)]) for fc in lan.f]
            lan.translate(u, 0.0, 1.3)
            meshes["fittings"].merge(wall_map(body, side, lan))
            meshes["fittings"].merge(wall_beam(body, side, u - 0.42, 1.24, u + 0.42, 1.24, "trim", w=0.18, h=0.1))
    # buttresses (tapered, two per long wall) and dressed quoins at the front corners
    for side in ("-x", "+x"):
        sx = -1 if side == "-x" else 1
        for u in (0.0, L / 2 - 0.45):
            pts = [(sx * (body.hw - 0.05), u - 0.3, 0.0), (sx * (body.hw + 0.7), u - 0.3, 0.0), (sx * (body.hw + 0.7), u + 0.3, 0.0), (sx * (body.hw - 0.05), u + 0.3, 0.0)]
            top = [(sx * (body.hw - 0.05), u - 0.25, eave - 0.3), (sx * (body.hw + 0.18), u - 0.25, eave - 0.6), (sx * (body.hw + 0.18), u + 0.25, eave - 0.6), (sx * (body.hw - 0.05), u + 0.25, eave - 0.3)]
            meshes["stonework"].merge(K.loft([pts, top], "wall_alt", smooth=False, cap_roles=("wall_alt", "trim")))
    for k in range(2):
        z = 0.45 + k * 1.6
        for sx in (-1, 1):
            meshes["stonework"].merge(M.chamfer_box(sx * (body.hwz(z) - 0.22), -body.hdz(z) + 0.18, z, 0.62 if k % 2 == 0 else 0.42, 0.46, 0.44, "trim", bevel=0.05))
    if P["apse"]:
        r = W / 2 - 0.25
        meshes["walls"].merge(K.lathe([(r, 0.0), (r - 0.03, eave - 0.5)], 8, "wall_alt", smooth=False, start=math.pi / 8).translate(0.0, L / 2, 0.0))
        meshes["roof"].merge(M.cone_roof(r - 0.03, eave - 0.5, 1.9, "hull", overhang=0.25, droop=0.08, thick=0.15, segs=8, flare=0.1, start=math.pi / 8).translate(0.0, L / 2, 0.0))
    if P["bellcote"]:
        zt = body.ridge - 0.25
        hd = body.hdz(zt)
        for sx in (-1, 1):
            meshes["stonework"].merge(M.chamfer_box(sx * 0.42, -hd + 0.1, zt - 0.1, 0.26, 0.5, 1.15, "trim", bevel=0.04))
        cap = M.roof_pitched(1.1, 0.6, zt + 1.05, 0.45, 0.1, "hull", overhang=0.08, gable_overhang=0.08, droop=0.0, n=1)
        cap.rotate_z(math.pi / 2)
        meshes["roof"].merge(cap.translate(0.0, -hd + 0.1, 0.0))
        bell = K.lathe([(0.0, 0.0), (0.24, 0.02), (0.2, 0.12), (0.13, 0.36), (0.05, 0.44), (0.0, 0.46)], 8, "chrome", smooth=True)
        meshes["fittings"].merge(bell.translate(0.0, -hd + 0.1, zt + 0.35))
        cz = zt + 1.6
        meshes["fittings"].merge(M.chamfer_box(0.0, -hd + 0.1, cz - 0.05, 0.1, 0.1, 0.85, "trim", bevel=0.02))
        meshes["fittings"].merge(M.chamfer_box(0.0, -hd + 0.1, cz + 0.42, 0.48, 0.1, 0.1, "trim", bevel=0.02))
    jit(meshes, seed, P["lean"])
    door_pt = body.surf("-y", 0.0, 0.0)
    lot = [2.0 * math.ceil((W + 2.4) / 2.0), 2.0 * math.ceil((L + W / 2 + 1.0) / 2.0)]
    dw, dh = (1.3, 2.7) if P["door"] == "leaf" else M.DOORWAY
    socks = [M.sock("door", M.door_out(door_pt, P["door"]), "s", width_m=dw, height_m=dh, needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes_of(meshes), {"lot_m": lot, "door_mode": P["door"]}, "lot_centre", sockets=socks, ground=False)


# ---------------------------------------------------------------- vlg.stall
@register("vlg.stall", V, "structure", {
    "goods": S.enum("produce", ["produce", "cloth", "pottery", "bread", "empty"]),
    "awning": S.enum("fabric", ["fabric", "knit", "body"], "striped cloth, blue cloth or a plank roof"),
    "width": S.num(2.6, 2.0, 3.6),
}, "Market stall: plank counter on four posts under a sloping striped awning with a hanging valance, dressed with "
   "goods (produce crates, folded cloth, pots or loaves).", origin="floor_center")
def stall(P, seed):
    w, d = P["width"], 1.3
    r = rng(seed, "vlg.stall", P["goods"])
    m = {"frame": K.Mesh(), "counter": K.Mesh(), "awning": K.Mesh(), "goods": K.Mesh()}
    m["counter"].merge(M.chamfer_box(0.0, 0.1, 0.0, w, 0.9, 0.95, "body", bevel=0.04, top_role="body_alt"))
    for sx in (-1, 1):
        for y, h in ((-d / 2, 2.05), (d / 2, 2.35)):
            m["frame"].merge(M.post(sx * (w / 2 - 0.06), y, 0.0, h, 0.065, 0.055, "wood", sides=6))
    pts = [(-w / 2 - 0.2, -d / 2 - 0.45, 2.0), (w / 2 + 0.2, -d / 2 - 0.45, 2.0), (w / 2 + 0.2, d / 2 + 0.15, 2.4), (-w / 2 - 0.2, d / 2 + 0.15, 2.4)]
    top = [(p[0], p[1], p[2] + 0.05) for p in pts]
    aw = K.Mesh().add(pts + top, [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], P["awning"], False)
    m["awning"].merge(aw.orient_outward())
    val = [(-w / 2 - 0.2, -d / 2 - 0.47, 1.72), (w / 2 + 0.2, -d / 2 - 0.47, 1.72), (w / 2 + 0.2, -d / 2 - 0.47, 2.02), (-w / 2 - 0.2, -d / 2 - 0.47, 2.02)]
    vb = [(p[0], p[1] + 0.04, p[2]) for p in val]
    m["awning"].merge(K.Mesh().add(val + vb, [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)],
                                   P["awning"], False).orient_outward())
    g = P["goods"]
    if g == "produce":
        for i, x in enumerate((-w / 3, 0.0, w / 3)):
            m["goods"].merge(M.chamfer_box(x, 0.05, 0.95, 0.62, 0.5, 0.22, "body", bevel=0.03))
            m["goods"].merge(M.blob(x, 0.05, 1.2, 0.27, 0.2, 0.09, ["flower", "cap", "fur"][i], seed + i, segs=6, rings=3, lump=0.2))
    elif g == "cloth":
        for i, x in enumerate((-w / 3, 0.0, w / 3)):
            for k in range(2):
                m["goods"].merge(M.chamfer_box(x + 0.03 * k, 0.05, 0.95 + 0.12 * k, 0.55, 0.42, 0.11, ["cushion", "knit", "fabric"][(i + k) % 3], bevel=0.03))
    elif g == "pottery":
        for i, x in enumerate((-w / 3, -w / 9, w / 9, w / 3)):
            hgt = 0.3 + 0.12 * r.random()
            m["goods"].merge(K.lathe([(0.0, 0.0), (0.1, 0.0), (0.15, hgt * 0.45), (0.08, hgt * 0.9), (0.1, hgt), (0.0, hgt)], 7,
                                     "hull_alt", smooth=True).translate(x, 0.05, 0.95))
    elif g == "bread":
        for i, x in enumerate((-w / 3, 0.0, w / 3)):
            m["goods"].merge(M.chamfer_box(x, 0.05, 0.95, 0.6, 0.45, 0.12, "rail", bevel=0.04))
            m["goods"].merge(M.blob(x, 0.05, 1.12, 0.22, 0.16, 0.07, "fur", seed + i, segs=6, rings=3, lump=0.1))
    nodes = [M.solid(k, v) for k, v in m.items() if v.f]
    return M.centred(nodes, {"goods": g})


# ---------------------------------------------------------------- vlg.well
@register("vlg.well", V, "structure", {
    "roof": S.enum("thatch", ["thatch", "slate", "none"]),
}, "Village well: round rubble well-head with a dressed coping, still water inside, two oak posts carrying a "
   "windlass with rope and bucket under a little pitched roof.", origin="floor_center")
def well(P, seed):
    m = {"stone": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "water": K.Mesh()}
    ring = [(1.0 * math.cos(a), 1.0 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 9, endpoint=False)]
    m["stone"].merge(M.ring_path_solid(ring, 0.0, 0.78, 0.38, "wall_alt", chamfer=0.0))
    m["stone"].merge(M.ring_path_solid([(1.02 * x, 1.02 * y) for x, y in ring], 0.74, 0.9, 0.46, "trim", chamfer=0.04))
    wat = K.prism([(0.8 * x, 0.8 * y) for x, y in ring], 0.35, 0.42, "water")
    m["water"].merge(wat)
    for sx in (-1, 1):
        m["frame"].merge(M.post(sx * 1.05, 0.0, 0.0, 2.3, 0.1, 0.085, "frame", sides=6))
    m["frame"].merge(M.beam((-1.15, 0.0, 1.75), (1.15, 0.0, 1.75), 0.14, 0.14, "frame", out=(0.0, 0.0, 1.0), bevel=0.25, embed=0.0))
    m["frame"].merge(M.beam((1.12, 0.0, 1.75), (1.12, -0.35, 1.45), 0.06, 0.06, "metal", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    m["frame"].merge(M.beam((0.0, 0.0, 1.7), (0.0, 0.0, 1.05), 0.03, 0.03, "rope", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    m["frame"].merge(K.lathe([(0.0, 0.0), (0.13, 0.0), (0.16, 0.26), (0.0, 0.26)], 6, "body", smooth=False).translate(0.0, 0.0, 0.8))
    if P["roof"] != "none":
        rr = M.roof_pitched(2.0, 1.3, 2.3, 0.75, 0.14 if P["roof"] == "slate" else 0.24, "roof" if P["roof"] == "thatch" else "hull",
                            overhang=0.25, gable_overhang=0.2, droop=0.05, bulge=0.04 if P["roof"] == "thatch" else 0.0, n=2)
        rr.rotate_z(math.pi / 2)
        m["roof"].merge(rr)
    M.jitter(m["stone"], seed + 3, 0.02, keep_z0=True)
    return M.centred([M.solid(k, v) for k, v in m.items() if v.f], {"roof": P["roof"]})


# ---------------------------------------------------------------- vlg.bridge
@register("vlg.bridge", V, "structure", {
    "kind": S.enum("stone", ["stone", "timber"]),
    "width": S.num(3.2, 2.4, 4.0),
}, "Bridge spanning two cells (8 m, along X): a humpbacked rubble arch bridge with cobbled deck and parapets, or a "
   "timber footbridge on trestles with hand rails. Path sockets at both ends.", origin="cell_centre")
def bridge(P, seed):
    w = P["width"]
    m = {"body": K.Mesh(), "deck": K.Mesh(), "rail": K.Mesh()}
    if P["kind"] == "stone":
        xs = np.linspace(-4.0, 4.0, 9)
        top = [(x, 0.06 + 0.85 * (1.0 - (x / 4.0) ** 2)) for x in xs]
        arch = [(2.4 * math.cos(a), -0.9 + 1.35 * math.sin(a)) for a in np.linspace(0.0, math.pi, 7)]
        outline = top + [(4.0, -0.9)] + arch + [(-4.0, -0.9)]
        outline = list(reversed(outline))
        body = M.slab_y(outline, -w / 2, w / 2, "stone")
        fn = M.bake.face_normals(np.asarray(body.v), body.f)
        body.r = ["path" if n_[2] > 0.6 else "stone" for n_ in fn]
        m["body"].merge(body)
        for sy in (-1, 1):
            pt = [(x, z + 0.75) for x, z in top]
            pb = [(x, z - 0.05) for x, z in top]
            par = M.slab_y(pb + list(reversed(pt)), sy * (w / 2) - 0.16, sy * (w / 2) + 0.16, "wall_alt")
            fn = M.bake.face_normals(np.asarray(par.v), par.f)
            par.r = ["trim" if n_[2] > 0.6 else "wall_alt" for n_ in fn]
            m["rail"].merge(par)
        M.jitter(m["rail"], seed + 1, 0.02, keep_z0=False)
    else:
        xs = np.linspace(-4.0, 4.0, 5)
        prof = [(x, 0.08 + 0.35 * (1.0 - (x / 4.0) ** 2)) for x in xs]
        rings = []
        for x, z in prof:
            rings.append([(x, -w / 2, z - 0.12), (x, w / 2, z - 0.12), (x, w / 2, z), (x, -w / 2, z)])
        dk = K.loft(rings, "body", smooth=False)
        m["deck"].merge(dk)
        for x in (-2.0, 0.0, 2.0):
            for sy in (-1, 1):
                z = 0.08 + 0.35 * (1.0 - (x / 4.0) ** 2)
                m["rail"].merge(M.post(x, sy * (w / 2 - 0.05), -1.2, z + 1.0, 0.09, 0.08, "post", sides=6))
        for sy in (-1, 1):
            for k in range(len(prof) - 1):
                (x0, z0), (x1, z1) = prof[k], prof[k + 1]
                dx, dz = x1 - x0, z1 - z0
                ln = math.hypot(dx, dz)
                e = 0.04 / ln            # overlap neighbours slightly: no shared end-cap vertices
                m["rail"].merge(M.beam((x0 - dx * e, sy * (w / 2 - 0.05), z0 - dz * e + 0.95), (x1 + dx * e, sy * (w / 2 - 0.05), z1 + dz * e + 0.95),
                                       0.08 + 0.004 * k, 0.08, "wood", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    socks = [M.sock("path", (-4.0, 0.0, 0.0), "w", width_m=w - 0.6), M.sock("path", (4.0, 0.0, 0.0), "e", width_m=w - 0.6)]
    return M.assemble([M.solid(k, v) for k, v in m.items() if v.f], {"kind": P["kind"]}, "cell_centre", cells=(2, 1),
                      sockets=socks, ground=False)


# ---------------------------------------------------------------- town wall, fences, gatehouse
WALL_KINDS = ["stone", "stone_postern", "stone_corner", "stone_end", "palisade", "palisade_corner"]


def palisade_stake(x, y, h, r, seed):
    m = K.lathe([(r, 0.0), (r * 0.95, h - 0.35), (0.0, h)], 6, "post", smooth=False, start=seed * 0.37)
    return m.translate(x, y, 0.0)


@register("vlg.wall", V, "structure", {
    "kind": S.enum("stone", WALL_KINDS),
    "height": S.num(3.4, 2.4, 4.4),
}, "Town wall segment on a cell edge (4 m along X, origin on the boundary): rubble wall with a coping and wall-walk "
   "merlons, a postern with a door socket, corner and end pieces, or a sharpened log palisade. wall_end sockets at "
   "+-2 m interlock segments, towers and the gatehouse.", origin="cell_edge")
def town_wall(P, seed):
    k, H = P["kind"], P["height"]
    m = {"wall": K.Mesh(), "top": K.Mesh(), "fittings": K.Mesh()}
    socks = []
    if k.startswith("palisade"):
        n = 9
        for i in range(n):
            x = -2.0 + (i + 0.5) * 4.0 / n
            m["wall"].merge(palisade_stake(x, 0.0, H + 0.2 * ((i * 7) % 3), 0.22, i))
        m["top"].merge(M.beam((-2.0, -0.25, H * 0.55), (2.0, -0.25, H * 0.55), 0.18, 0.12, "frame", out=(0.0, -1.0, 0.0), bevel=0.25, embed=0.02))
        if k == "palisade_corner":
            for i in range(8):
                y = -0.45 - (i + 0.5) * 3.55 / 8
                m["wall"].merge(palisade_stake(2.0, y, H + 0.2 * ((i * 5) % 3), 0.22, i + 20))
            socks.append(M.sock("wall_end", (2.0, -4.0, 0.0), "s", wall="palisade", height_m=H))
        socks.append(M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="palisade", height_m=H))
        if k != "palisade_corner":
            socks.append(M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="palisade", height_m=H))
    else:
        t = 1.0
        if k == "stone_postern":
            body = K.Mesh()
            cut = M.opening_outline("arch", M.DOOR_CUT[0], M.DOOR_CUT[1], 6)
            r_, sp_ = M.DOOR_CUT[0] / 2, cut[2][1]
            arc = cut[3:-1]
            outline = [(-2.0, 0.0), (-r_, 0.0), (-r_, sp_)] + list(reversed(arc)) + [(r_, sp_), (r_, 0.0), (2.0, 0.0), (2.0, H), (-2.0, H)]
            sl = K.prism(outline, -t / 2, t / 2, "wall_alt")
            sl.apply(lambda a: a[:, [0, 2, 1]])
            body.merge(sl.orient_outward())
            fr = M.arch_frame("arch", M.DOOR_CUT[0], M.DOOR_CUT[1], t + 0.16, 0.34, "trim", segs=6, y0=-(t + 0.16) / 2)
            m["fittings"].merge(fr)
            m["wall"].merge(body)
            socks.append(M.sock("door", (0.0, -t / 2, 0.0), "s", width_m=M.DOORWAY[0], height_m=M.DOORWAY[1], needs="arch.door",
                                note="postern: a declared door here takes the room's vlg.doorway"))
        else:
            m["wall"].merge(M.chamfer_box(0.0, 0.0, 0.0, 4.0, t, H, "wall_alt", bevel=0.05, top_role="step"))
        m["top"].merge(M.merlons(-2.0, 2.0, -t / 2 + 0.17, H - 0.02, 0.85, 0.34, "wall_alt", merlon=0.9, gap=0.65))
        m["top"].merge(M.chamfer_box(0.0, -t / 2 - 0.02, H - 0.25, 4.02, 0.12, 0.2, "trim", bevel=0.03))
        if k == "stone_corner":
            m["wall"].merge(M.chamfer_box(2.0, -2.0 - t / 4 - 0.01, 0.0, t, 4.0 - t / 2 - 0.02, H, "wall_alt", bevel=0.05, top_role="step"))
            leg = M.merlons(-1.6, 2.0, 0.0, H - 0.02, 0.85, 0.34, "wall_alt")
            m["top"].merge(leg.rotate_z(-math.pi / 2).translate(2.0 + t / 2 - 0.17, 0.0, 0.0))
            socks.append(M.sock("wall_end", (2.0, -4.0, 0.0), "s", wall="town", height_m=H))
        if k == "stone_end":
            m["wall"].merge(M.octa_box(2.0, 0.0, 0.0, 1.5, 1.5, H + 0.6, "wall_alt", chamfer=0.35, top_role="step"))
        socks.append(M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="town", height_m=H))
        if k not in ("stone_corner", "stone_end"):
            socks.append(M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="town", height_m=H))
        M.jitter(m["top"], seed + 5, 0.025, keep_z0=False)
    return M.assemble([M.solid(kk, v) for kk, v in m.items() if v.f], {"kind": k}, "cell_edge", sockets=socks)


FENCE_KINDS = ["hurdle", "rail", "drystone", "rail_gate"]


@register("vlg.fence", V, "structure", {
    "kind": S.enum("hurdle", FENCE_KINDS),
}, "Fence on a cell edge (4 m along X): woven wattle hurdles between stakes, post-and-rail, a dry-stone wall with "
   "capstones, or a rail fence with a field gate. wall_end sockets at +-2 m.", origin="cell_edge")
def fence(P, seed):
    k = P["kind"]
    m = {"posts": K.Mesh(), "rails": K.Mesh()}
    if k == "drystone":
        m["rails"].merge(M.chamfer_box(0.0, 0.0, 0.0, 4.0, 0.6, 0.95, "wall_alt", bevel=0.1, base_bevel=0.0))
        for i in range(6):
            x = -2.0 + (i + 0.5) * 4.0 / 6
            m["posts"].merge(M.chamfer_box(x, 0.0, 0.88, 4.0 / 6 - 0.04, 0.5, 0.18, "trim", bevel=0.05))
        M.jitter(m["posts"], seed + 2, 0.03, keep_z0=False)
        M.jitter(m["rails"], seed + 3, 0.04, keep_z0=True)
    else:
        xs = [-1.95, -0.65, 0.65, 1.95] if k != "rail_gate" else [-1.95, -0.55, 1.95]
        for x in xs:
            m["posts"].merge(M.post(x, 0.0, 0.0, 1.15, 0.075, 0.065, "post", sides=6, start=x))
        if k == "hurdle":
            for a, b in zip(xs[:-1], xs[1:]):
                pan = panel_local(a + 0.05, b - 0.05, 0.15, 1.0, -0.04, 0.04, "rail", front_uv=False)
                pan.apply(lambda arr: arr[:, [0, 1, 2]])
                m["rails"].merge(pan.orient_outward())
        else:
            for z in (0.45, 0.9):
                m["rails"].merge(M.beam((-2.0, -0.08, z), (2.0, -0.08, z), 0.09, 0.07, "wood", out=(0.0, -1.0, 0.0), bevel=0.2, embed=0.02))
            if k == "rail_gate":
                for z in (0.3, 0.65, 1.0):
                    m["rails"].merge(M.beam((-0.5, -0.2, z), (1.9, -0.2, z), 0.08, 0.06, "body", out=(0.0, -1.0, 0.0), bevel=0.1, embed=0.0))
                m["rails"].merge(M.beam((-0.45, -0.2, 0.3), (1.85, -0.2, 1.0), 0.08, 0.06, "body", out=(0.0, -1.0, 0.0), bevel=0.1, embed=0.0))
    socks = [M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="fence"), M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="fence")]
    return M.assemble([M.solid(kk, v) for kk, v in m.items() if v.f], {"kind": k}, "cell_edge", sockets=socks)


@register("vlg.gatehouse", V, "building", {
    "gate": S.enum("closed", ["closed", "open"], "gate leaves (state pair for module gates: closed <-> open)"),
    "roof": S.enum("thatch", ["thatch", "tiles", "slate"]),
    "lean": S.num(0.02, 0.0, 0.06),
}, "Village gatehouse spanning a 3.2 m arched passage: rubble piers, deep voussoir arch, jettied timber room "
   "above with a roof; plank gate leaves closed or swung open (a state pair). wall_end sockets at +-3.5 m meet "
   "vlg.wall segments.", origin="cell_edge")
def gatehouse(P, seed):
    m = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stonework": K.Mesh(), "fittings": K.Mesh()}
    pw, dp, H = 3.2, 4.0, 4.2
    for sx in (-1, 1):
        m["stonework"].merge(M.chamfer_box(sx * (pw / 2 + 1.2), 0.0, 0.0, 2.4, dp, H, "wall_alt", bevel=0.06, top_role="step"))
    m["stonework"].merge(M.arch_frame("arch", pw, 3.0, dp + 0.1, 0.8, "trim", segs=6, y0=-(dp + 0.1) / 2))
    m["stonework"].merge(M.chamfer_box(0.0, 0.0, 3.1, pw + 0.4, dp, H - 3.1, "wall_alt", bevel=0.04))
    up = M.Body(dp + 0.6, 8.4, H + 2.5, H + 2.5 + 2.0, taper=0.01, z0=H - 0.05)
    room = up.mesh("wall", rows=(H + 1.2,))
    room.rotate_z(math.pi / 2)
    m["walls"].merge(room)
    rb = M.Body(dp + 0.6, 8.4, H + 2.5, up.ridge, taper=0.0)
    rf = roof_for(rb, P["roof"], overhang=0.4, gable_overhang=0.35, sag=0.04)
    rf.rotate_z(math.pi / 2)
    m["roof"].merge(rf)
    for sy in (-1, 1):
        y = sy * ((dp + 0.6) / 2 + 0.03)
        for x in (-4.0, -1.3, 1.3, 4.0):
            m["frame"].merge(M.beam((x, y, H), (x, y, H + 2.45), 0.18, 0.08, "frame", out=(0.0, sy, 0.0), bevel=0.3, embed=0.04))
        m["frame"].merge(M.beam((-4.2, y, H + 1.2), (4.2, y, H + 1.2), 0.18, 0.08, "frame", out=(0.0, sy, 0.0), bevel=0.3, embed=0.04))
        m["frame"].merge(M.beam((-4.3, sy * (dp / 2 + 0.24), H), (4.3, sy * (dp / 2 + 0.24), H), 0.24, 0.2, "frame",
                                out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
        win = panel_local(-0.45, 0.45, H + 1.35, H + 2.15, -0.04, 0.03, "glass", "frame")
        win.apply(lambda a, sy=sy: np.stack([a[:, 0], sy * ((dp + 0.6) / 2 + a[:, 1]), a[:, 2]], 1))
        m["fittings"].merge(win.orient_outward())
    # gate leaves: closed in the passage mouth, or swung back against the passage walls
    for sx in (-1, 1):
        if P["gate"] == "closed":
            leaf = panel_local(0.012, pw / 2 - 0.02, 0.02, 2.9, -0.06, 0.06, "door", "frame")
            leaf.apply(lambda a, sx=sx: np.stack([sx * a[:, 0], a[:, 1] - dp / 2 + 0.6, a[:, 2]], 1))
        else:
            leaf = panel_local(0.0, pw / 2 - 0.02, 0.02, 2.6, -0.06, 0.06, "door", "frame")
            leaf.apply(lambda a, sx=sx: np.stack([sx * (pw / 2 - 0.1 - a[:, 1]), -dp / 2 + 0.6 + a[:, 0], a[:, 2]], 1))
        m["fittings"].merge(leaf.orient_outward())
    jit(m, seed, P["lean"])
    socks = [M.sock("wall_end", (-4.0, 0.0, 0.0), "w", wall="town", height_m=3.4),
             M.sock("wall_end", (4.0, 0.0, 0.0), "e", wall="town", height_m=3.4),
             M.sock("gate", (0.0, -dp / 2, 0.0), "s", width_m=pw, state=P["gate"], pair="vlg.gatehouse__open" if P["gate"] == "closed" else "vlg.gatehouse")]
    return M.assemble(nodes_of(m), {"gate": P["gate"]}, "cell_edge", sockets=socks)


# ---------------------------------------------------------------- vlg.stairs
@register("vlg.stairs", V, "structure", {
    "kind": S.enum("stone", ["stone", "timber"]),
    "rise": S.num(1.5, 0.5, 3.0), "width": S.num(2.0, 1.2, 3.0),
}, "Exterior steps up a terrace (rising toward +Y / north): rubble flight with dressed treads and side cheeks, or an "
   "open timber stair with stringers. Path sockets at the foot and the head.", origin="cell_centre")
def stairs(P, seed):
    rise, w = P["rise"], P["width"]
    steps = max(3, int(round(rise / 0.25)))
    run = steps * 0.32
    m = {"stair": K.Mesh(), "sides": K.Mesh()}
    if P["kind"] == "stone":
        st = M.stairs_solid(w, run, rise, steps, "step", side_role="wall_alt")
        m["stair"].merge(st.translate(0.0, -run / 2, 0.0))
        for sx in (-1, 1):
            ch = K.prism([(-run / 2 - 0.1, 0.0), (run / 2 + 0.1, 0.0), (run / 2 + 0.1, rise + 0.35), (-run / 2 + 0.25, 0.35)], -0.2, 0.2, "wall_alt")
            ch.apply(lambda a: a[:, [2, 0, 1]])
            m["sides"].merge(ch.orient_outward().translate(sx * (w / 2 + 0.2), 0.0, 0.0))
        M.jitter(m["sides"], seed + 1, 0.02, keep_z0=True)
    else:
        for i in range(steps):
            y = -run / 2 + (i + 0.5) * run / steps
            z = (i + 1) * rise / steps
            m["stair"].merge(M.chamfer_box(0.0, y, z - 0.06, w, run / steps + 0.04, 0.06, "body", bevel=0.015))
        for sx in (-1, 1):
            m["sides"].merge(M.beam((sx * (w / 2 + 0.04), -run / 2 - 0.1, 0.0), (sx * (w / 2 + 0.04), run / 2, rise), 0.08, 0.26, "frame",
                                    out=(sx, 0.0, 0.0), bevel=0.15, embed=0.0))
    socks = [M.sock("path", (0.0, -run / 2 - 0.1, 0.0), "s", width_m=w), M.sock("path", (0.0, run / 2, rise), "n", width_m=w)]
    return M.assemble([M.solid(k, v) for k, v in m.items() if v.f], {"kind": P["kind"], "rise_m": rise}, "cell_centre", sockets=socks)


# ---------------------------------------------------------------- interior set
DOOR_ITEM = {"side": S.enum("s", ["n", "e", "s", "w"]), "cell": S.integer(0, 0, 4)}
MOUNT_ITEM = {"side": S.enum("n", ["n", "e", "s", "w"]), "cell": S.integer(0, 0, 4)}


@register("vlg.room", V, "shell", {
    "cells_x": S.integer(3, 1, 4, "cells west-east (4 m each)"),
    "cells_y": S.integer(2, 1, 4, "cells north-south"),
    "doors": S.array(DOOR_ITEM, [{"side": "s", "cell": 1}], 6, "door sockets (cut, vlg.doorway placed by room.gd)"),
    "windows": S.array(MOUNT_ITEM, [{"side": "n", "cell": 0}], 8, "painted window panels"),
    "hearth": S.array(MOUNT_ITEM, [{"side": "n", "cell": 2}], 2, "hearth sockets (warm baked pool; place vlg.hearth)"),
    "lanterns": S.array(MOUNT_ITEM, [], 6, "lantern wall sockets (warm baked pool; place mprop.lantern mounted)"),
}, "Timber-framed interior shell on the room grid (3.4 m storey): whitewashed panels between oak studs on cell "
   "boundaries, a mid rail and a plank skirting, plank floor with a flagstone border, door cuts for vlg.doorway, "
   "painted windows, hearth and lantern sockets with warm baked pools. Ceilings are separate (vlg.ceiling).",
   origin="room_floor")
def room(P, seed):
    lights = [(h["side"], h["cell"], "hearth", 1.0, 0.6, 5.5, 1.1) for h in P["hearth"]]
    lights += [(h["side"], h["cell"], "lantern", 2.2, 0.35, 3.5, 0.8) for h in P["lanterns"]]
    walls, floor, extras, socks, bl, info = M.room_shell(
        P["cells_x"], P["cells_y"], M.V_H, doors=[(d["side"], d["cell"]) for d in P["doors"]],
        windows=[(w["side"], w["cell"]) for w in P["windows"]], lights=lights, wall_role="wall", post_role="frame",
        post_depth=0.09, plinth=(0.45, 0.04, "body"), rails=[(1.35, 1.52)], rail_role="frame", floor_role="floor",
        border=0.6, border_role="step", cap_role="frame")
    nodes = [Node("floor", floor, "shell"), Node("walls", walls, "shell")]
    if extras.f:
        nodes.append(Node("fittings", extras, "solid"))
    meta = dict(info, note="room plot = cells x 4 m + 0.5 m apron each side; a door on side/cell i has door.position = 4*i + 2")
    return M.assemble(nodes, meta, "cell_block_centre", cells=(P["cells_x"], P["cells_y"]), sockets=socks, lights=bl, ground=False)


@register("vlg.ceiling", V, "shell", {
    "cells_x": S.integer(3, 1, 4), "cells_y": S.integer(2, 1, 4),
    "height": S.num(3.4, 2.8, 4.6),
}, "Beamed ceiling for vlg.room (one-sided, facing down so N64 cutaway cameras see in): dark boards on heavy oak "
   "joists across the short span (origin on the cell block centre at FLOOR level, like vlg.room).", origin="cell_block_ceiling")
def ceiling(P, seed):
    W, Dd = P["cells_x"] * M.CELL, P["cells_y"] * M.CELL
    hx, hy = W / 2 - M.WALL_T, Dd / 2 - M.WALL_T
    H = P["height"]
    m = M.floor_sheet(-hx, -hy, hx, hy, H, "ceiling", step=2.0, up=False)
    beams = K.Mesh()
    along_x = W >= Dd
    n = int(round((2 * hy if along_x else 2 * hx) / 1.6))
    for i in range(1, n):
        if along_x:
            y = -hy + 2 * hy * i / n
            beams.merge(M.beam((-hx - 0.02, y, H + 0.03), (hx + 0.02, y, H + 0.03), 0.26, 0.28, "frame", out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
        else:
            x = -hx + 2 * hx * i / n
            beams.merge(M.beam((x, -hy - 0.02, H + 0.03), (x, hy + 0.02, H + 0.03), 0.26, 0.28, "frame", out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
    return M.assemble([Node("ceiling", m, "shell"), M.solid("joists", beams)], {"height_m": H}, "cell_block_centre",
                      cells=(P["cells_x"], P["cells_y"]), ground=False)


@register("vlg.hearth", V, "furniture_large", {
    "fire": S.boolean(True), "width": S.num(2.2, 1.6, 3.0),
}, "Inglenook hearth for a hearth socket (wall-face anchor, front +Z): rubble cheeks, an oak bressumer under a "
   "plastered chimney breast rising to the ceiling, flagstone hearth slab, burning logs (fire glows, baked warm).",
   origin="wall_face")
def hearth(P, seed):
    w = P["width"]
    m = {"stone": K.Mesh(), "frame": K.Mesh(), "fire": K.Mesh()}
    for sx in (-1, 1):
        m["stone"].merge(M.chamfer_box(sx * (w / 2 - 0.2), -0.35, 0.0, 0.4, 0.7, 1.5, "wall_alt", bevel=0.05))
    m["stone"].merge(M.chamfer_box(0.0, -0.05, 0.0, w, 0.12, 1.5, "opening", bevel=0.01))
    m["frame"].merge(M.beam((-w / 2 - 0.05, -0.72, 1.6), (w / 2 + 0.05, -0.72, 1.6), 0.24, 0.24, "frame", out=(0.0, -1.0, 0.0), bevel=0.2, embed=0.0))
    m["stone"].merge(M.chamfer_box(0.0, -0.35, 1.48, w + 0.2, 0.72, 1.92, "wall", bevel=0.04))
    m["stone"].merge(M.chamfer_box(0.0, -0.75, 0.0, w + 0.4, 0.8, 0.08, "step", bevel=0.02))
    if P["fire"]:
        for k, (a, b) in enumerate(((-0.35, 0.3), (0.3, -0.25), (0.0, 0.05))):
            m["frame"].merge(M.beam((a, -0.55, 0.12 + 0.08 * k), (b, -0.25, 0.14 + 0.08 * k), 0.12, 0.12, "bark", out=(0.0, 0.0, 1.0), bevel=0.3, embed=0.0))
        m["fire"].merge(K.lathe([(0.0, 0.0), (0.32, 0.0), (0.18, 0.4), (0.0, 0.7)], 5, "fire", smooth=False).translate(0.0, -0.4, 0.12))
    lights = [{"pos": [0.0, -0.6, 0.5], "radius": 3.5, "strength": 1.0}] if P["fire"] else []
    a = M.assemble([M.solid(k, v) for k, v in m.items() if v.f], {"fire": P["fire"]}, "wall_face", lights=lights,
                   emitter={"kind": "hearth", "offset": [0.0, 0.5, 0.45]} if P["fire"] else None)
    return a


@register("vlg.doorway", V, "arch", {
    "leaf": S.enum("closed", ["closed", "ajar"]),
}, "THE medieval door (styles bind room.gd's arch.door to it): adzed oak frame with a lintel, a plank leaf with iron "
   "straps (painted leaf), a stone threshold; origin on the room.gd door anchor (0.4 m in from the room edge), front "
   "+Z toward the room, sized for the DOOR_CUT of every MEDIEVALKIT wall and the doorway mode of every building.",
   origin="door_anchor")
def doorway(P, seed):
    w, h = M.DOORWAY
    m = {"frame": K.Mesh(), "leaf": K.Mesh(), "sill": K.Mesh()}
    fr = M.arch_frame("lintel", w, h, 0.75, 0.2, "frame", segs=4, y0=-0.75)
    m["frame"].merge(fr)
    leaf = panel_local(-w / 2 + 0.01, w / 2 - 0.01, 0.02, h - 0.02, -0.08, 0.0, "door", "frame")
    leaf.apply(lambda a: np.stack([a[:, 0], -0.6 + a[:, 1], a[:, 2]], 1))
    if P["leaf"] == "ajar":
        leaf.translate(w / 2, 0.6, 0.0).rotate_z(math.radians(-55.0)).translate(-w / 2, -0.6, 0.0)
    m["leaf"].merge(leaf.orient_outward())
    m["sill"].merge(M.chamfer_box(0.0, -0.45, 0.0, w + 0.5, 0.95, 0.07, "step", bevel=0.02))
    return M.assemble([M.solid(k, v) for k, v in m.items() if v.f], {"leaf": P["leaf"], "opening_m": [w, h]}, "door_anchor",
                      sockets=[M.sock("door", (0.0, -0.6, 0.0), "s", width_m=w, height_m=h)], ground=False)
