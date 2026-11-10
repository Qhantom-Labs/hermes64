"""MEDIEVALKIT village architecture family (vlg.*), theme-agnostic, on the MEDIEVAL GRID (gen_medievalkit_core).

Exterior buildings are LOT pieces: origin on the body centre at ground level, front door facing glTF +Z (south),
footprints on the 2 m half-cell lattice so neighbours line up on the 4 m grid; each lists a `door` socket on its
threshold (the room compiler checks it opens onto a path / plaza) and its lot size. Walls, fences and town walls are
CELL-EDGE pieces (origin on a cell boundary, 4 m long, `wall_end` sockets at +-2 m). Interiors (vlg.room) follow the
dungeon-compatible room grid: cells x 4 m, walls 0.5 m inside the cell boundary, door sockets on cell-edge midpoints.

Built in the canonical house frame (ridge along Blender Y, eave walls at +-X, gable walls at +-Y) and turned when the
door is on the eaves side. Every element is its own closed solid (beams, posts, panes, leaves, chimney courses), so
islands may interpenetrate (the topology gate checks self-intersection within an island only) but never share
vertices.
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from . import gen_medievalkit_core as M
from . import gen_medievalkit_tex  # noqa: F401  (registers the mk_ painted texture generators)
from .rng import rng

V = "1.0.0"


# ---------------------------------------------------------------- wall-local construction
def wall_map(body, side, mesh):
    """Map a mesh built in wall-local coordinates (a along the wall, o outward from the surface, z up) onto a Body
    wall; closed solids are re-oriented outward afterwards (the local frame may be mirrored)."""
    n = np.asarray(body.outward(side), dtype=np.float64)

    def f(arr):
        out = np.empty_like(arr)
        for i, (a, o, z) in enumerate(arr):
            out[i] = np.asarray(body.surf(side, a, z)) + n * o
        return out
    mesh.apply(f)
    return mesh.orient_outward()


def panel_local(a0, a1, z0, z1, o0, o1, role, edge_role=None, front_uv=True):
    """Closed thin slab in wall-local coordinates whose outer face (o = o1) carries normalized UVs (one painted leaf /
    pane / sign face per panel); the edges use metric UVs of edge_role."""
    v = [(a0, o0, z0), (a1, o0, z0), (a1, o0, z1), (a0, o0, z1), (a0, o1, z0), (a1, o1, z0), (a1, o1, z1), (a0, o1, z1)]
    f = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    er = edge_role or role
    uvs = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)]) if front_uv else None] + [None] * 5
    return K.Mesh().add(v, f, [role, er, er, er, er, er], False, uvs)


def wall_beam(body, side, a0, z0, a1, z1, role="frame", w=0.2, h=0.08):
    p0 = body.surf(side, a0, z0)
    p1 = body.surf(side, a1, z1)
    return M.beam(p0, p1, w, h, role, out=body.outward(side), bevel=0.3, embed=0.04)


def door_set(body, side, a, w=1.1, h=2.15, shape="lintel", frame_role="frame", leaf_role="door", step_role="step", step=True):
    out = K.Mesh()
    leaf = K.prism([(x, z) for x, z in M.opening_outline(shape, w, h)], -0.05, 0.035, leaf_role)
    # prism extrudes along Z: rebuild in wall-local (a, o, z) with o = extrusion
    leaf.apply(lambda arr: arr[:, [0, 2, 1]])
    leaf.uv = [("n", [((p[0] + w / 2) / w, p[2] / h) for p in (leaf.v[i] for i in fc)]) if abs(K_normal(leaf, fi)[1]) > 0.9 else u
               for fi, (fc, u) in enumerate(zip(leaf.f, leaf.uv))]
    leaf.translate(a, 0.0, 0.0)
    out.merge(wall_map(body, side, leaf))
    fr = M.arch_frame(shape, w, h, 0.2, 0.18, frame_role, segs=6, z0=0.0, y0=-0.07)
    fr.translate(a, 0.0, 0.0)
    out.merge(wall_map(body, side, fr))
    if step:
        st = M.chamfer_box(a, 0.28, 0.0, w + 0.5, 0.56, 0.16, step_role, bevel=0.04)
        out.merge(wall_map(body, side, st))
    return out


def K_normal(m, fi):
    P = np.asarray([m.v[i] for i in m.f[fi]])
    n = np.zeros(3)
    for i in range(len(P)):
        n += np.cross(P[i], P[(i + 1) % len(P)])
    ln = np.linalg.norm(n)
    return n / ln if ln > 1e-12 else n


def window_set(body, side, a, z0, w=0.8, h=0.9, frame_role="frame", glass_role="glass", shutters=False,
               shutter_role="body", sill_role=None, lintel=True):
    out = K.Mesh()
    out.merge(wall_map(body, side, panel_local(a - w / 2, a + w / 2, z0, z0 + h, -0.04, 0.02, glass_role, frame_role)))
    out.merge(wall_beam(body, side, a - w / 2 - 0.12, z0 - 0.02, a + w / 2 + 0.12, z0 - 0.02, sill_role or frame_role, w=0.16, h=0.1))
    if lintel:
        out.merge(wall_beam(body, side, a - w / 2 - 0.14, z0 + h + 0.08, a + w / 2 + 0.14, z0 + h + 0.08, frame_role, w=0.18, h=0.09))
    if shutters:
        sw = w / 2 + 0.04
        for s_ in (-1, 1):
            c = a + s_ * (w / 2 + 0.06 + sw / 2)
            out.merge(wall_map(body, side, panel_local(c - sw / 2, c + sw / 2, z0 - 0.02, z0 + h + 0.02, 0.01, 0.06, shutter_role)))
    return out


def corner_posts(body, z0, z1, role="frame", s=0.24):
    """Square corner posts centred on the four body corners (one closed bevelled post per corner)."""
    out = K.Mesh()
    zc = 0.5 * (z0 + z1)
    hw, hd = body.hwz(zc), body.hdz(zc)
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.merge(M.chamfer_box(sx * hw, sy * hd, z0, s, s, z1 - z0, role, bevel=0.04))
    return out


def chimney(x, y, z0, z1, role="wall_alt", cap_role="trim", w=0.9, d=0.8):
    out = K.Mesh()
    out.merge(M.chamfer_box(x, y, z0, w, d, z1 - z0, role, bevel=0.06))
    out.merge(M.chamfer_box(x, y, z1 - 0.06, w + 0.16, d + 0.16, 0.22, cap_role, bevel=0.05))
    return out


def plinth(body, h=0.45, role="wall_alt", grow=0.08):
    return M.chamfer_box(0.0, 0.0, 0.0, 2 * body.hw + 2 * grow, 2 * body.hd + 2 * grow, h, role, bevel=0.06)


def turn90(meshes, points):
    """Canonical (door on -x) -> lot space (door on -y): rotate +90 degrees about Z."""
    for m in meshes:
        if m is not None:
            m.rotate_z(math.pi / 2)
    return [(-p[1], p[0], p[2]) for p in points]


def bays(L, k):
    return [-L / 2 + L * i / k for i in range(k + 1)]


def roof_for(body, kind, overhang=0.45, gable_overhang=0.35, sag=0.05, hip=0.0, thick=None, rise_extra=0.0):
    """Roof solid over a Body (canonical frame). kind: thatch (roof role) | slate (hull) | tiles (hull_alt)."""
    E = body.eave
    hw = body.hwz(E)
    if kind == "thatch":
        th = thick or 0.38
        role, bulge, rr, droop, n = "roof", 0.07, 0.12, 0.16, 3
    elif kind == "slate":
        th = thick or 0.17
        role, bulge, rr, droop, n = "hull", 0.0, 0.0, 0.05, 2
    else:
        th = thick or 0.2
        role, bulge, rr, droop, n = "hull_alt", 0.02, 0.0, 0.06, 2
    rise = body.ridge + 0.6 * th - E + rise_extra
    m = M.roof_pitched(2 * hw, 2 * body.hdz(E), E, rise, th, role, overhang=overhang, gable_overhang=gable_overhang,
                       droop=droop, bulge=bulge, ridge_round=rr, hip=hip, n=n, sag=sag,
                       stations=None if hip else [-(body.hdz(E) + gable_overhang), 0.0, body.hdz(E) + gable_overhang])
    return m


# ---------------------------------------------------------------- vlg.cottage
COTTAGE_STYLES = ["timber", "stone", "longhouse", "townhouse"]


@register("vlg.cottage", V, "building", {
    "style": S.enum("timber", COTTAGE_STYLES, "timber: whitewash + oak frame + thatch; stone: rubble + slate + shutters; "
                    "longhouse: long, low, hipped thatch; townhouse: two storeys, jettied, clay tiles, gable to the street"),
    "width": S.num(7.0, 4.0, 10.0, "front width in metres (2 m lattice recommended)"),
    "depth": S.num(5.0, 4.0, 8.0, "depth in metres"),
    "door_offset": S.num(0.0, -2.5, 2.5, "door position along the front from the centre"),
    "windows": S.integer(2, 0, 4, "front windows"),
    "chimney": S.boolean(True),
    "roof": S.enum("auto", ["auto", "thatch", "slate", "tiles"], "auto = the style's roof"),
    "lean": S.num(0.03, 0.0, 0.08, "hand-built irregularity (deterministic jitter, metres)"),
    "door": S.enum("leaf", ["leaf", "doorway"], "leaf: own plank door; doorway: the room's arch.door (vlg.doorway) fills it"),
}, "Village cottage in four original styles on a 2 m lattice lot: tapered walls, adzed oak framing as separate bevelled "
   "beams, a lofted roof with rolled eaves and a sagging ridge (thick bulging thatch, slate or clay pantiles), plank "
   "door with a painted leaf, glass panes (glow at night), rubble plinth and chimney. Door socket on the threshold.",
   origin="lot_centre")
def cottage(P, seed):
    st = P["style"]
    W, Dp = P["width"], P["depth"]
    roof = P["roof"] if P["roof"] != "auto" else {"timber": "thatch", "stone": "slate", "longhouse": "thatch", "townhouse": "tiles"}[st]
    r = rng(seed, "vlg.cottage", st)
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stone": K.Mesh(), "fittings": K.Mesh()}
    if st == "townhouse":
        return townhouse(P, seed, roof)
    eaves_front = st != "townhouse"
    # canonical: front = -x wall, its length (front width) runs along Y
    eave = {"timber": 2.9, "stone": 2.8, "longhouse": 2.2}[st]
    rise = {"timber": 2.3, "stone": 2.0, "longhouse": 2.0}[st] * (Dp / 5.0) ** 0.5
    # hipped roofs sit on a flat-topped body (gable triangles would poke through the hip ends)
    body = M.Body(Dp, W, eave, eave + rise, taper=0.018 if st != "stone" else 0.01, gable=(st != "longhouse"))
    wall_role = "wall_alt" if st == "stone" else "wall"
    meshes["walls"].merge(body.mesh(wall_role, rows=(0.5, 1.4)))
    meshes["stone"].merge(plinth(body, 0.45 if st != "stone" else 0.3))
    a_door = max(-W / 2 + 1.0, min(W / 2 - 1.0, P["door_offset"]))
    door_w, door_h = (1.1, 2.1) if st != "longhouse" else (1.05, 1.85)
    if P["door"] == "leaf":
        meshes["fittings"].merge(door_set(body, "-x", a_door, door_w, door_h, "lintel" if st != "stone" else "arch",
                                          frame_role="frame" if st != "stone" else "trim"))
    # windows spread along the front, avoiding the door bay
    slots = [s for s in bays(W, P["windows"] + 2)[1:-1]] if P["windows"] else []
    free = [s for s in slots if abs(s - a_door) > door_w / 2 + 0.75]
    while len(free) < P["windows"] and P["windows"]:
        cand = [-W / 2 + 0.9, W / 2 - 0.9]
        free += [c for c in cand if abs(c - a_door) > door_w / 2 + 0.75 and all(abs(c - f) > 1.2 for f in free)]
        break
    wz = 1.05 if st != "longhouse" else 0.95
    wh = 0.85 if st != "longhouse" else 0.6
    for a in free[:P["windows"]]:
        meshes["fittings"].merge(window_set(body, "-x", a, wz, 0.7, wh, frame_role="frame" if st != "stone" else "trim",
                                            shutters=(st == "stone"), lintel=True))
    # back + gable windows (small)
    meshes["fittings"].merge(window_set(body, "+x", 0.0, wz, 0.6, wh * 0.9, frame_role="frame" if st != "stone" else "trim",
                                        shutters=(st == "stone")))
    if st != "longhouse":
        for side in ("-y", "+y"):
            meshes["fittings"].merge(window_set(body, side, 0.0, eave + 0.25, 0.45, 0.5, frame_role="frame" if st != "stone" else "trim",
                                                lintel=False))
    # timber framing
    if st in ("timber", "longhouse"):
        meshes["frame"].merge(corner_posts(body, 0.4, eave + 0.05, "frame"))
        rail = wz - 0.04
        for s_ in (-1, 1):
            edge = a_door + s_ * (door_w / 2 + 0.16)
            end = s_ * (W / 2 - 0.15)
            if abs(end - edge) > 0.5:
                meshes["frame"].merge(wall_beam(body, "-x", edge, 0.45, edge, eave - 0.05))
                meshes["frame"].merge(wall_beam(body, "-x", edge, rail, end, rail))
        meshes["frame"].merge(wall_beam(body, "+x", -W / 2 + 0.15, rail, W / 2 - 0.15, rail))
        meshes["frame"].merge(wall_beam(body, "+x", -W / 2 + 0.15, eave - 0.1, W / 2 - 0.15, eave - 0.1))
        meshes["frame"].merge(wall_beam(body, "-x", -W / 2 + 0.15, eave - 0.1, W / 2 - 0.15, eave - 0.1))
        for side in ("-y", "+y"):
            hwE = body.hwz(eave) - 0.12
            meshes["frame"].merge(wall_beam(body, side, -hwE, eave - 0.06, hwE, eave - 0.06, w=0.22))
            if st == "timber":
                meshes["frame"].merge(wall_beam(body, side, 0.0, eave, 0.0, body.ridge - 0.25))
                meshes["frame"].merge(wall_beam(body, side, -hwE + 0.3, eave + 0.05, -0.18, body.ridge - 0.55, w=0.16))
                meshes["frame"].merge(wall_beam(body, side, hwE - 0.3, eave + 0.05, 0.18, body.ridge - 0.55, w=0.16))
                meshes["frame"].merge(wall_beam(body, side, -hwE, rail, hwE, rail, w=0.18))
    else:
        # stone cottage: three big dressed quoins per corner, alternating long faces (chunky, readable at distance)
        for k in range(3):
            z = 0.3 + k * (eave - 0.75) / 2.0
            hgt = 0.44
            hwz, hdz = body.hwz(z + hgt / 2), body.hdz(z + hgt / 2)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    lx, ly = (0.66, 0.42) if k % 2 == 0 else (0.42, 0.66)
                    cx = sx * (hwz - lx / 2 + 0.1)
                    cy = sy * (hdz - ly / 2 + 0.1)
                    meshes["stone"].merge(M.chamfer_box(cx, cy, z, lx, ly, hgt, "trim", bevel=0.05))
    meshes["roof"].merge(roof_for(body, roof, overhang=0.5 if st == "longhouse" else 0.42,
                                  gable_overhang=0.32 if roof == "thatch" else 0.22,
                                  sag=0.06 if roof == "thatch" else 0.03, hip=1.6 if st == "longhouse" else 0.0))
    if P["chimney"]:
        cy = (W / 2 - 1.1) * (1 if r.random() < 0.5 else -1)
        if st == "stone":
            gy = body.hd + 0.3
            meshes["stone"].merge(chimney(0.0, gy * (1 if cy > 0 else -1), 0.0, body.ridge + 0.7, "wall_alt", "trim", w=1.1, d=0.7))
        else:
            meshes["stone"].merge(chimney(Dp * 0.18, cy, eave - 0.6, body.ridge + 0.75, "wall_alt", "trim"))
    for k_, m in meshes.items():
        if k_ in ("frame", "stone", "fittings") and m.f:
            M.jitter(m, seed * 7 + len(k_), P["lean"] * 0.5, keep_z0=True)
    M.jitter(meshes["roof"], seed * 11 + 3, P["lean"], axes=(0.6, 0.6, 1.0), keep_z0=False)
    door_pt = body.surf("-x", a_door, 0.0)
    pts = [door_pt]
    if eaves_front:
        pts = turn90(list(meshes.values()), pts)
    door_pt = pts[0]
    nodes = [M.solid("walls", meshes["walls"]), M.solid("frame", meshes["frame"]), M.solid("roof", meshes["roof"]),
             M.solid("stonework", meshes["stone"]), M.solid("fittings", meshes["fittings"])]
    lot = [2.0 * math.ceil((W + 1.0) / 2.0), 2.0 * math.ceil((Dp + 1.0) / 2.0)]
    socks = [M.sock("door", M.door_out(door_pt, P["door"]), "s", width_m=door_w if P["door"] == "leaf" else M.DOORWAY[0],
                    height_m=door_h if P["door"] == "leaf" else M.DOORWAY[1], needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes, {"style": st, "roof": roof, "lot_m": lot, "door_mode": P["door"]}, "lot_centre", sockets=socks, ground=False)


def townhouse(P, seed, roof):
    """Two storeys, gable to the street (canonical front = -y), jettied upper floor, dense framing upstairs."""
    W, Dp = P["width"], P["depth"]
    W = min(W, 7.0)
    meshes = {"walls": K.Mesh(), "frame": K.Mesh(), "roof": K.Mesh(), "stone": K.Mesh(), "fittings": K.Mesh()}
    h1 = 2.8
    lower = M.Body(W, Dp, h1, h1 + 0.01, taper=0.0, gable=False)
    meshes["walls"].merge(lower.mesh("wall_alt", rows=(0.5, 1.4)))
    jet = 0.45
    up_eave = h1 + 2.5
    upper = M.Body(W + 0.2, Dp + jet, up_eave, up_eave + 3.0 * (W / 6.0), taper=0.012, z0=h1 - 0.05)
    # shift the upper storey forward (toward -y) by the jetty
    up = upper.mesh("wall", rows=(h1 + 0.9, h1 + 1.7)).translate(0.0, -jet / 2, 0.0)
    meshes["walls"].merge(up)

    sb = M.Shifted(upper, 0.0, -jet / 2)
    meshes["stone"].merge(plinth(lower, 0.3))
    a_door = max(-W / 2 + 0.9, min(W / 2 - 0.9, P["door_offset"] - 0.8))
    if P["door"] == "leaf":
        meshes["fittings"].merge(door_set(lower, "-y", a_door, 1.1, 2.15, "arch", frame_role="trim"))
    # shop window beside the door (wide, low sill), upstairs windows in a row
    shop_a = a_door + (1.6 if a_door < 0 else -1.6)
    meshes["fittings"].merge(window_set(lower, "-y", shop_a, 0.9, 1.3, 1.0, frame_role="frame", lintel=True))
    n_up = max(2, min(3, P["windows"] + 1))
    for a in bays(W, n_up + 1)[1:-1]:
        meshes["fittings"].merge(window_set(sb, "-y", a, h1 + 0.75, 0.6, 0.95, frame_role="frame"))
    meshes["fittings"].merge(window_set(sb, "-y", 0.0, up_eave + 0.6, 0.5, 0.65, frame_role="frame", lintel=False))
    # jetty: bressumer beam + carved brackets (short bevelled braces) under the overhang
    yb = -Dp / 2 - jet + 0.06
    meshes["frame"].merge(M.beam((-W / 2 - 0.1, yb, h1 - 0.02), (W / 2 + 0.1, yb, h1 - 0.02), 0.24, 0.2, "frame", out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
    for x in bays(W, 3):
        x = max(-W / 2 + 0.2, min(W / 2 - 0.2, x))
        meshes["frame"].merge(M.beam((x, -Dp / 2 + 0.05, h1 - 0.85), (x, yb + 0.05, h1 - 0.2), 0.16, 0.16, "frame", out=(1.0, 0.0, 0.0), bevel=0.25, embed=0.0))
    # upper framing: posts + a diamond brace pattern between windows
    hz = h1 + 0.1
    xs = bays(W + 0.2 - 0.3, 4)
    for x in xs:
        meshes["frame"].merge(wall_beam(sb, "-y", x, hz, x, up_eave - 0.05, w=0.18))
    meshes["frame"].merge(wall_beam(sb, "-y", xs[0], h1 + 0.65, xs[-1], h1 + 0.65, w=0.18))
    meshes["frame"].merge(wall_beam(sb, "-y", xs[0], up_eave - 0.08, xs[-1], up_eave - 0.08, w=0.2))
    for x0, x1 in ((xs[0], xs[1]), (xs[-2], xs[-1])):
        meshes["frame"].merge(wall_beam(sb, "-y", x0, h1 + 0.7, x1, up_eave - 0.15, w=0.14))
        meshes["frame"].merge(wall_beam(sb, "-y", x1, h1 + 0.7, x0, up_eave - 0.15, w=0.14))
    for side in ("-x", "+x"):
        for u in bays(Dp + jet - 0.4, 3):
            meshes["frame"].merge(wall_beam(sb, side, u, hz, u, up_eave - 0.05, w=0.18))
    meshes["frame"].merge(corner_posts(lower, 0.3, h1 - 0.1, "trim", s=0.3))
    rb = M.Body(W + 0.2, Dp + jet, up_eave, upper.ridge, taper=0.0)
    rm = roof_for(rb, roof, overhang=0.38, gable_overhang=0.4, sag=0.04)
    meshes["roof"].merge(rm.translate(0.0, -jet / 2, 0.0))
    if P["chimney"]:
        meshes["stone"].merge(chimney(W / 2 - 0.2, Dp * 0.25, up_eave - 0.4, upper.ridge + 0.6, "wall_alt", "trim", w=0.85, d=0.85))
    for k_, m in meshes.items():
        if k_ in ("frame", "fittings", "stone") and m.f:
            M.jitter(m, seed * 7 + len(k_), P["lean"] * 0.5, keep_z0=True)
    M.jitter(meshes["roof"], seed * 11 + 3, P["lean"], axes=(0.6, 0.6, 1.0), keep_z0=False)
    door_pt = lower.surf("-y", a_door, 0.0)
    nodes = [M.solid("walls", meshes["walls"]), M.solid("frame", meshes["frame"]), M.solid("roof", meshes["roof"]),
             M.solid("stonework", meshes["stone"]), M.solid("fittings", meshes["fittings"])]
    lot = [2.0 * math.ceil((W + 1.0) / 2.0), 2.0 * math.ceil((Dp + jet + 1.0) / 2.0)]
    socks = [M.sock("door", M.door_out(door_pt, P["door"]), "s", width_m=1.1 if P["door"] == "leaf" else M.DOORWAY[0],
                    height_m=2.15 if P["door"] == "leaf" else M.DOORWAY[1], needs="path|plaza" if P["door"] == "leaf" else "arch.door")]
    return M.assemble(nodes, {"style": "townhouse", "roof": roof, "lot_m": lot, "door_mode": P["door"]}, "lot_centre", sockets=socks, ground=False)
