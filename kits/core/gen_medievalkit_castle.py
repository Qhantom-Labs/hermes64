"""MEDIEVALKIT castle family (cst.*), theme-agnostic, on the MEDIEVAL GRID.

Castle masonry uses roles that mean castle in every pack: stone (dressed ashlar), wall_alt (rubble footings), trim
(pale dressed courses), step (flagstone floors and wall walks), hull (slate roofs), band (heraldic atlas), metal
(iron), body (timber gates and decks). So the castle builds the same under medieval_village and castle_keep packs.

Grid: curtain walls and battlements are CELL-EDGE pieces (4 m along X, wall_end sockets `curtain` at +-2 m); towers
stand on cell corners with wall_end sockets at 2 m on all four axes (a curtain segment overlaps the tower drum by a
metre, so joins never gap); the gatehouse is a three-cell edge piece (wall_end at +-6 m) whose passage carries a
`portcullis` socket, a `drawbridge` socket over the moat and an inner `door` socket (a declared region door takes
the room's vlg.doorway there). Portcullis (closed/raised) and drawbridge (raised/lowered) are STATE PAIRS: a room
places the closed form with {flag, asset_when_set: open form} and room.gd swaps them when a module gate sets the flag.
Halls are room-grid shells (cells x 4 m, walls 0.5 m in, door cuts with stone arch surrounds, torch sockets baked).
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from . import gen_medievalkit_core as M
from .gen_medievalkit_village import V, panel_local
from .rng import rng

CW_T, CW_H = 2.0, 7.0          # curtain wall thickness / wall-walk height


def jitter_all(meshes, seed, amt, skip=()):
    for k, m in meshes.items():
        if m.f and k not in skip:
            M.jitter(m, seed * 13 + len(k), amt, keep_z0=True)


def solids(meshes):
    return [M.solid(k, v) for k, v in meshes.items() if v.f]


def prism_x(section_yz, x0, x1, role):
    """Extrude a (y, z) section along X (closed); side UVs swapped so u runs along X and courses stay level."""
    m = K.prism([(y, z) for y, z in section_yz], x0, x1, role)
    m.apply(lambda a: a[:, [2, 0, 1]])
    m.orient_outward()
    return M.swap_uv(m)


def slit(x, y, z, out, h=1.1, w=0.16):
    """Arrow slit: a dark recess panel with a dressed surround (closed solids)."""
    m = K.Mesh()
    o = np.asarray(out, dtype=np.float64)
    side = np.cross(o, (0.0, 0.0, 1.0))
    c = np.array([x, y, z])
    for t, role, ww, hh in ((0.02, "opening", w, h), (0.0, "trim", w + 0.28, h + 0.3)):
        a = c + o * t
        pts = []
        for dz in (-hh / 2, hh / 2):
            for s_ in (-1, 1):
                pts.append(a + side * s_ * ww / 2 + np.array([0, 0, dz]))
        p = [pts[0], pts[1], pts[3], pts[2]]
        v = [tuple(q - o * 0.06) for q in p] + [tuple(q + o * (0.03 if role == "opening" else 0.02)) for q in p]
        f = [(4, 5, 6, 7), (3, 2, 1, 0), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        m.merge(K.Mesh().add(v, f, role, False).orient_outward())
    return m


def ring_merlons(R, z, n, h, depth, role="stone", phase=0.0, width_frac=0.55):
    out = K.Mesh()
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        w = 2 * math.pi * R / n * width_frac
        mm = M.chamfer_box(0.0, 0.0, 0.0, w, depth, h, role, bevel=0.07)
        mm.rotate_z(a + math.pi / 2)
        out.merge(mm.translate(R * math.cos(a), R * math.sin(a), z))
    return out


def pennant(x, y, z, h=2.2, design=0):
    """Pole with a swallow-tailed heraldic pennant (band atlas quadrant `design`)."""
    m = K.Mesh()
    m.merge(M.post(x, y, z, z + h, 0.05, 0.035, "wood", sides=5))
    u0, v0 = 0.5 * (design % 2), (0.5 if design < 2 else 0.0)
    L, H = 1.3, 0.55
    zt = z + h - 0.12
    prof = [(0.0, zt), (L, zt - 0.08), (L * 0.78, zt - H / 2), (L, zt - H + 0.08), (0.0, zt - H)]
    v, f = [], []
    for t in (-0.02, 0.02):
        for a, zz in prof:
            v.append((x + 0.04 + a, y + t, zz))
    uv = [(u0 + 0.5 * a / L, v0 + 0.5 * (zz - (zt - H)) / H) for a, zz in prof]
    f = [(5, 6, 7, 8, 9), (4, 3, 2, 1, 0)] + [(i, (i + 1) % 5, (i + 1) % 5 + 5, i + 5) for i in range(5)]
    uvs = [("n", uv), ("n", list(reversed(uv)))] + [None] * 5
    flag = K.Mesh().add(v, f, ["band", "band"] + ["band"] * 5, False, uvs)
    m.merge(flag.orient_outward())
    return m


# ---------------------------------------------------------------- curtain wall + battlement
CURTAIN_KINDS = ["straight", "slits", "broken", "stair"]


@register("cst.curtain", V, "structure", {
    "kind": S.enum("straight", CURTAIN_KINDS),
    "height": S.num(CW_H, 5.0, 9.0, "wall-walk height"),
}, "Castle curtain wall on a cell edge (4 m along X, outer face toward -Y): battered rubble footing, dressed ashlar "
   "face, a wall walk with a crenellated outer parapet and a string course; kinds with arrow slits, a ruined broken "
   "top, or an inner stair up to the walk. wall_end sockets (curtain) at +-2 m.", origin="cell_edge")
def curtain(P, seed):
    H = P["height"]
    k = P["kind"]
    m = {"wall": K.Mesh(), "top": K.Mesh(), "detail": K.Mesh()}
    t = CW_T / 2
    if k == "broken":
        sec = [(-t - 0.35, 0.0), (t, 0.0), (t, H - 1.6), (-t, H - 1.1), (-t, 1.6)]
    else:
        sec = [(-t - 0.35, 0.0), (t, 0.0), (t, H), (-t + 0.45, H), (-t + 0.45, H + 1.0), (-t, H + 1.0), (-t, 1.6)]
    body = prism_x(sec, -2.0, 2.0, "stone")
    fn = M.bake.face_normals(np.asarray(body.v), body.f)
    zc = [sum(body.v[i][2] for i in f_) / len(f_) for f_ in body.f]
    body.r = ["step" if n_[2] > 0.7 else ("wall_alt" if z_ < 1.4 else "stone") for n_, z_ in zip(fn, zc)]
    m["wall"].merge(body)
    if k != "broken":
        m["top"].merge(M.merlons(-2.0, 2.0, -t + 0.22, H + 0.98, 0.85, 0.44, "stone", merlon=1.0, gap=0.7))
        m["detail"].merge(M.beam((-2.02, -t, H - 0.35), (2.02, -t, H - 0.35), 0.24, 0.1, "trim", out=(0.0, -1.0, 0.0), bevel=0.3, embed=0.03))
    else:
        r = rng(seed, "cst.curtain.broken")
        for i in range(4):
            x = -1.6 + i * 1.05 + 0.2 * r.random()
            m["top"].merge(M.blob(x, (r.random() - 0.5) * 1.2, H - 1.4 + 0.3 * r.random(), 0.45, 0.4, 0.3, "wall_alt", seed + i, segs=6, rings=3, lump=0.25))
    if k == "slits":
        for x in (-1.0, 1.0):
            m["detail"].merge(slit(x, -t - 0.02, 3.4, (0.0, -1.0, 0.0), h=1.3))
    if k == "stair":
        st = M.stairs_solid(1.2, 3.6, H - 0.1, 12, "step", side_role="stone")
        st.rotate_z(-math.pi / 2)
        m["detail"].merge(st.translate(-1.8, t + 0.62, 0.0))
    socks = [M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="curtain", height_m=H), M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="curtain", height_m=H)]
    if k == "stair":
        socks.append(M.sock("path", (2.0, t + 0.62, 0.0), "e", width_m=1.2, note="stair foot on the inner side"))
    jitter_all(m, seed, 0.02, skip=("wall",))
    return M.assemble(solids(m), {"kind": k, "walk_m": H}, "cell_edge", sockets=socks)


@register("cst.battlement", V, "structure", {
    "kind": S.enum("crenel", ["crenel", "machicolated"]),
}, "Crenellated parapet strip on a cell edge (4 m along X) for keep roofs, towers and wall tops: merlons on a "
   "parapet with a dressed coping; machicolated kind corbels the parapet out over a row of brackets.", origin="cell_edge")
def battlement(P, seed):
    m = {"parapet": K.Mesh(), "merlons": K.Mesh()}
    out = 0.0 if P["kind"] == "crenel" else 0.45
    m["parapet"].merge(M.chamfer_box(0.0, -out, 0.0, 4.0, 0.5, 1.0, "stone", bevel=0.04, top_role="trim"))
    m["merlons"].merge(M.merlons(-2.0, 2.0, -out, 0.98, 0.85, 0.5, "stone", merlon=1.0, gap=0.7))
    if out:
        for x in (-1.5, -0.5, 0.5, 1.5):
            pts = [(x - 0.16, 0.25, -0.75), (x + 0.16, 0.25, -0.75), (x + 0.16, -0.7, 0.02), (x - 0.16, -0.7, 0.02)]
            back = [(p[0], 0.25, p[2]) for p in pts]
            br = K.Mesh().add([(x - 0.16, 0.25, -0.75), (x + 0.16, 0.25, -0.75), (x + 0.16, 0.25, 0.02), (x - 0.16, 0.25, 0.02),
                               (x - 0.16, -0.7, 0.02), (x + 0.16, -0.7, 0.02)],
                              [(0, 1, 2, 3), (1, 5, 2), (0, 3, 4), (3, 2, 5, 4), (0, 4, 5, 1)], "trim", False)
            m["parapet"].merge(br.orient_outward())
            _ = (pts, back)
    socks = [M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="battlement"), M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="battlement")]
    return M.assemble(solids(m), {"kind": P["kind"]}, "cell_edge", sockets=socks, ground=False)


# ---------------------------------------------------------------- towers
def tower_sockets(H, door_r=None):
    s = [M.sock("wall_end", (d * 2.0, 0.0, 0.0), f, wall="curtain", height_m=CW_H) for d, f in ((-1, "w"), (1, "e"))]
    s += [M.sock("wall_end", (0.0, d * 2.0, 0.0), f, wall="curtain", height_m=CW_H) for d, f in ((1, "n"), (-1, "s"))]
    if door_r is not None:
        s.append(M.sock("door", (0.0, -door_r, 0.0), "s", width_m=M.DOORWAY[0], height_m=M.DOORWAY[1], needs="arch.door?"))
    return s


@register("cst.tower_round", V, "building", {
    "top": S.enum("crenellated", ["crenellated", "roofed"]),
    "radius": S.num(3.0, 2.4, 3.6), "height": S.num(10.0, 8.0, 14.0),
    "door": S.boolean(False, "a ground door socket on the south face (room arch.door)"),
}, "Round castle tower on a cell corner: battered rubble base, ashlar drum with string courses and arrow slits, "
   "either a corbelled crenellated parapet or a flared conical slate roof with a heraldic pennant. Curtain wall_end "
   "sockets at 2 m on all four axes.", origin="floor_center")
def tower_round(P, seed):
    R, H = P["radius"], P["height"]
    seg = 10
    m = {"drum": K.Mesh(), "top": K.Mesh(), "detail": K.Mesh()}
    m["drum"].merge(K.lathe([(R + 0.45, 0.0), (R, 1.8), (R - 0.08, H)], seg, "stone", smooth=True, roles=["wall_alt", "stone"]))
    if P["top"] == "crenellated":
        m["top"].merge(K.lathe([(R - 0.1, H - 0.6), (R + 0.32, H - 0.25), (R + 0.32, H + 1.0), (0.0, H + 1.0)],
                               seg, "stone", smooth=False, roles=["trim", "stone", "step"], cap_roles=("stone", "step")))
        m["top"].merge(ring_merlons(R + 0.1, H + 0.98, 10, 0.85, 0.45, "stone", phase=math.pi / 10))
    else:
        m["top"].merge(M.cone_roof(R - 0.08, H, R * 1.6, "hull", overhang=0.5, droop=0.25, thick=0.25, segs=seg, flare=0.35))
        m["detail"].merge(pennant(0.0, 0.0, H + R * 1.6 - 0.15, design=seed % 4))
    for a, z in ((math.pi * 1.5, 3.6), (math.pi * 0.25, 5.6), (math.pi * 0.75, 3.4), (math.pi * 1.1, 6.4)):
        r_ = R - 0.08 * (z / H) + 0.0
        m["detail"].merge(slit(r_ * math.cos(a), r_ * math.sin(a), z, (math.cos(a), math.sin(a), 0.0)))
    m["detail"].merge(K.lathe([(R + 0.05, H * 0.45), (R + 0.17, H * 0.45 + 0.08), (R + 0.17, H * 0.45 + 0.24), (R + 0.03, H * 0.45 + 0.3)],
                              seg, "trim", smooth=True, cap_roles=("trim", "trim")).translate(0.0, 0.0, 0.0))
    if P["door"]:
        fr = M.arch_frame("pointed", M.DOOR_CUT[0], M.DOOR_CUT[1], 0.5, 0.35, "trim", segs=6, y0=-0.25)
        m["detail"].merge(fr.translate(0.0, -(R + 0.3), 0.0))
    jitter_all(m, seed, 0.02, skip=("drum",))
    return M.assemble(solids(m), {"top": P["top"]}, "cell_corner", sockets=tower_sockets(H, (R + 0.2) if P["door"] else None))


@register("cst.tower_square", V, "building", {
    "top": S.enum("crenellated", ["crenellated", "roofed"]),
    "size": S.num(5.0, 4.0, 6.0), "height": S.num(11.0, 8.0, 15.0),
}, "Square castle tower on a cell corner: battered rubble footing, ashlar shaft with quoins and slits, a "
   "crenellated parapet on corbel courses or a pyramid slate roof with a pennant. Curtain sockets at 2 m on four "
   "axes.", origin="floor_center")
def tower_square(P, seed):
    s, H = P["size"], P["height"]
    m = {"shaft": K.Mesh(), "top": K.Mesh(), "detail": K.Mesh()}
    h = s / 2

    def ring(hh, z):
        return [(-hh, -hh, z), (hh, -hh, z), (hh, hh, z), (-hh, hh, z)]
    m["shaft"].merge(K.loft([ring(h + 0.4, 0.0), ring(h, 1.8), ring(h - 0.06, H)], "stone", smooth=False, roles=["wall_alt", "stone"]))
    if P["top"] == "crenellated":
        m["top"].merge(K.loft([ring(h - 0.1, H - 0.5), ring(h + 0.3, H - 0.15), ring(h + 0.3, H + 1.0), ring(h - 0.35, H + 1.0)],
                              "stone", smooth=False, roles=["trim", "stone", "step"]))
        for k in range(4):
            mm = M.merlons(-h - 0.1, h + 0.1, 0.0, 0.0, 0.85, 0.45, "stone", merlon=0.9, gap=0.7)
            mm.translate(0.0, -(h + 0.1), H + 0.98).rotate_z(k * math.pi / 2)
            m["top"].merge(mm)
    else:
        m["top"].merge(M.cone_roof(h * 1.414 - 0.06, H, s * 1.1, "hull", overhang=0.4, droop=0.2, thick=0.22, segs=4, flare=0.2, start=math.pi / 4))
        m["detail"].merge(pennant(0.0, 0.0, H + s * 1.1 - 0.12, design=(seed + 1) % 4))
    for k in range(4):
        a = k * math.pi / 2
        for z in (3.8, 6.6):
            p = (math.cos(a - math.pi / 2) * 0.0, -(h - 0.06 * z / H) - 0.02, z)
            ss = slit(0.0, p[1], z, (0.0, -1.0, 0.0))
            m["detail"].merge(ss.rotate_z(a))
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (2.4, 5.4):
                if z < H - 1.0:
                    m["detail"].merge(M.chamfer_box(sx * (h - 0.2), sy * (h - 0.2), z, 0.62 if int(z) % 2 else 0.5, 0.62 if int(z) % 2 == 0 else 0.5, 0.46, "trim", bevel=0.04))
    jitter_all(m, seed, 0.02, skip=("shaft",))
    return M.assemble(solids(m), {"top": P["top"]}, "cell_corner", sockets=tower_sockets(H))


# ---------------------------------------------------------------- gatehouse, portcullis, drawbridge
GATE_W, GATE_H = 3.6, 4.6        # passage clear width / arch height


@register("cst.gatehouse", V, "building", {
    "depth": S.num(6.0, 5.0, 8.0),
    "top": S.enum("machicolated", ["machicolated", "crenellated"]),
}, "Castle gate block spanning two cell edges (8 m along X, centred on a cell corner, outer face toward -Y): ashlar "
   "masses on a battered footing around a pointed-arch passage with a dressed voussoir surround, a portcullis slot, a "
   "corbelled machicolation (or plain crenellation) over the arch, and an inner wall at the end of the passage with "
   "a door cut and stone arch. Flanking towers are cst.tower_round / cst.tower_square on the end corners. Sockets: "
   "wall_end (curtain / tower) at +-4 m, portcullis in the passage mouth, drawbridge in front over the moat, the "
   "inner door (a region door takes vlg.doorway).", origin="cell_corner")
def gatehouse(P, seed):
    dp = P["depth"]
    m = {"block": K.Mesh(), "top": K.Mesh(), "detail": K.Mesh()}
    Hb = 8.4
    sw = 4.0 - GATE_W / 2           # side mass width
    for sx in (-1, 1):
        cx = sx * (GATE_W / 2 + sw / 2)
        sec = [(-dp / 2 - 0.35, 0.0), (dp / 2, 0.0), (dp / 2, Hb), (-dp / 2, Hb), (-dp / 2, 1.6)]
        blk = K.prism([(y, z) for y, z in sec], cx - sw / 2, cx + sw / 2, "stone")
        blk.apply(lambda a_: a_[:, [2, 0, 1]])
        blk.orient_outward()
        fn = M.bake.face_normals(np.asarray(blk.v), blk.f)
        zc = [sum(blk.v[i][2] for i in f_) / len(f_) for f_ in blk.f]
        blk.r = ["step" if n_[2] > 0.7 else ("wall_alt" if z_ < 1.4 else "stone") for n_, z_ in zip(fn, zc)]
        m["block"].merge(M.swap_uv(blk))
    m["block"].merge(M.chamfer_box(0.0, 0.0, GATE_H + 0.25, GATE_W + 0.1, dp, Hb - GATE_H - 0.25, "stone", bevel=0.04, top_role="step"))
    m["detail"].merge(M.arch_frame("pointed", GATE_W, GATE_H, 0.62, 0.55, "trim", segs=4, y0=-dp / 2 - 0.12))
    if P["top"] == "machicolated":
        m["top"].merge(M.chamfer_box(0.0, -dp / 2 - 0.25, Hb - 0.05, 8.0, 0.55, 1.1, "stone", bevel=0.04, top_role="trim"))
        for x in (-3.0, -1.0, 1.0, 3.0):
            br = K.Mesh().add([(x - 0.18, -dp / 2 + 0.02, Hb - 0.9), (x + 0.18, -dp / 2 + 0.02, Hb - 0.9), (x + 0.18, -dp / 2 + 0.02, Hb - 0.02),
                               (x - 0.18, -dp / 2 + 0.02, Hb - 0.02), (x - 0.18, -dp / 2 - 0.5, Hb - 0.02), (x + 0.18, -dp / 2 - 0.5, Hb - 0.02)],
                              [(0, 1, 2, 3), (1, 5, 2), (0, 3, 4), (3, 2, 5, 4), (0, 4, 5, 1)], "trim", False)
            m["detail"].merge(br.orient_outward())
        m["top"].merge(M.merlons(-4.0, 4.0, -dp / 2 - 0.3, Hb + 1.03, 0.85, 0.45, "stone", merlon=1.2, gap=0.8))
    else:
        m["top"].merge(M.merlons(-4.0, 4.0, -dp / 2 + 0.25, Hb - 0.02, 0.85, 0.5, "stone", merlon=1.2, gap=0.8))
    m["top"].merge(M.merlons(-4.0, 4.0, dp / 2 - 0.25, Hb - 0.02, 0.85, 0.5, "stone", merlon=1.2, gap=0.8))
    # portcullis slot just inside the mouth (unjittered); inner wall + door arch at the end of the passage
    m["block"].merge(M.chamfer_box(0.0, -dp / 2 + 0.75, GATE_H - 0.05, GATE_W + 0.2, 0.22, 0.12, "opening", bevel=0.01))
    yw = dp / 2 - 0.8
    cut = M.opening_outline("arch", M.DOOR_CUT[0], M.DOOR_CUT[1], 6)
    r_, sp_ = M.DOOR_CUT[0] / 2, cut[2][1]
    outline = [(-GATE_W / 2 - 0.05, 0.0), (-r_, 0.0), (-r_, sp_)] + list(reversed(cut[3:-1])) + [(r_, sp_), (r_, 0.0), (GATE_W / 2 + 0.05, 0.0),
                                                                                               (GATE_W / 2 + 0.05, GATE_H + 0.3), (-GATE_W / 2 - 0.05, GATE_H + 0.3)]
    iw = K.prism(outline, yw, yw + 0.5, "stone")
    iw.apply(lambda a_: a_[:, [0, 2, 1]])
    m["block"].merge(iw.orient_outward())
    m["detail"].merge(M.arch_frame("arch", M.DOOR_CUT[0], M.DOOR_CUT[1], 0.56, 0.3, "trim", segs=4, y0=yw - 0.06))
    floor = M.floor_sheet(-GATE_W / 2, -dp / 2, GATE_W / 2, yw, 0.01, "step", step=2.0)
    jitter_all(m, seed, 0.02, skip=("block", "detail"))
    nodes = solids(m) + [Node("passage_floor", floor, "shell")]
    socks = [M.sock("wall_end", (-4.0, 0.0, 0.0), "w", wall="curtain", height_m=CW_H), M.sock("wall_end", (4.0, 0.0, 0.0), "e", wall="curtain", height_m=CW_H),
             M.sock("portcullis", (0.0, -dp / 2 + 0.75, 0.0), "s", width_m=GATE_W, height_m=GATE_H, needs="cst.portcullis"),
             M.sock("drawbridge", (0.0, -dp / 2 - 0.15, 0.0), "s", width_m=GATE_W, needs="cst.drawbridge"),
             M.sock("door", (0.0, yw, 0.0), "s", width_m=M.DOORWAY[0], height_m=M.DOORWAY[1], needs="arch.door",
                    note="inner door at the end of the passage: a region door here takes the room's vlg.doorway")]
    return M.assemble(nodes, {"passage_m": [GATE_W, GATE_H, dp]}, "cell_corner", sockets=socks)


@register("cst.portcullis", V, "arch", {
    "state": S.enum("closed", ["closed", "raised"], "state pair: closed <-> raised (room.gd swaps on a module flag)"),
}, "Portcullis for the gatehouse passage (portcullis socket anchor): an iron-shod oak grid with spiked feet, "
   "lowered or hauled up into the slot (only the spikes show). A state pair for module gates.", origin="gate_anchor")
def portcullis(P, seed):
    w, h = GATE_W - 0.1, GATE_H - 0.1
    lift = 0.0 if P["state"] == "closed" else h - 0.45
    m = {"grid": K.Mesh(), "iron": K.Mesh()}
    nv, nh = 6, 5
    for i in range(nv):
        x = -w / 2 + (i + 0.5) * w / nv
        m["grid"].merge(M.chamfer_box(x, 0.0, 0.25 + lift, 0.13, 0.13, h - 0.25, "body_alt", bevel=0.025))
        m["iron"].merge(K.lathe([(0.075, 0.0), (0.0, -0.25)], 4, "metal", smooth=False, start=math.pi / 4).translate(x, 0.0, 0.26 + lift))
    for j in range(nh):
        z = 0.6 + j * (h - 0.9) / (nh - 1) + lift
        m["iron"].merge(M.chamfer_box(0.0, -0.1, z, w, 0.09, 0.12, "metal", bevel=0.02))
    a = M.assemble(solids(m), {"state": P["state"], "pair": "cst.portcullis__raised" if P["state"] == "closed" else "cst.portcullis"},
                   "gate_anchor", sockets=[M.sock("portcullis", (0.0, 0.0, 0.0), "s", width_m=GATE_W)], ground=False)
    return a


@register("cst.drawbridge", V, "structure", {
    "state": S.enum("lowered", ["lowered", "raised"], "state pair: raised <-> lowered"),
    "length": S.num(5.0, 4.0, 8.0),
}, "Drawbridge for the gatehouse (drawbridge socket anchor, extending toward -Y over the moat): heavy plank deck on "
   "iron-strapped beams with hauling chains; lowered flat across the moat or raised upright against the gate. A "
   "state pair for module gates.", origin="gate_anchor")
def drawbridge(P, seed):
    L, w = P["length"], GATE_W - 0.05
    m = {"deck": K.Mesh(), "iron": K.Mesh()}
    m["deck"].merge(M.chamfer_box(0.0, -L / 2, -0.22, w, L, 0.22, "body", bevel=0.03))
    for x in (-w / 2 + 0.25, 0.0, w / 2 - 0.25):
        m["deck"].merge(M.chamfer_box(x, -L / 2, -0.42, 0.24, L - 0.1, 0.2, "body_alt", bevel=0.03))
    for y in (-0.6, -L / 2, -L + 0.6):
        m["iron"].merge(M.chamfer_box(0.0, y, -0.01, w + 0.04, 0.12, 0.03, "metal", bevel=0.01))
    for sx in (-1, 1):
        m["iron"].merge(M.beam((sx * (w / 2 - 0.1), -L + 0.25, 0.05), (sx * (w / 2 - 0.1), 0.25, 4.3), 0.07, 0.07, "metal",
                               out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    if P["state"] == "raised":
        for mm in m.values():
            mm.rotate_x(-math.pi / 2 + 0.06)
    return M.assemble(solids(m), {"state": P["state"], "pair": "cst.drawbridge" if P["state"] == "raised" else "cst.drawbridge__raised"},
                      "gate_anchor", sockets=[M.sock("drawbridge", (0.0, 0.0, 0.0), "s", width_m=GATE_W),
                                              M.sock("path", (0.0, -L if P["state"] == "lowered" else 0.0, 0.0), "s", width_m=w)], ground=False)


# ---------------------------------------------------------------- keep
@register("cst.keep", V, "building", {
    "size": S.num(10.0, 8.0, 12.0), "height": S.num(14.0, 11.0, 18.0),
    "turrets": S.enum("roofed", ["roofed", "crenellated"]),
}, "Castle keep: a great square tower with a battered rubble base, ashlar walls, a string course, lancet windows, "
   "a pointed main door with a stone surround, a crenellated parapet and four corbelled corner turrets with conical "
   "slate roofs. Door socket on the south face (a region door takes vlg.doorway).", origin="lot_centre")
def keep(P, seed):
    s, H = P["size"], P["height"]
    h = s / 2
    m = {"walls": K.Mesh(), "top": K.Mesh(), "detail": K.Mesh()}

    def ring(hh, z):
        return [(-hh, -hh, z), (hh, -hh, z), (hh, hh, z), (-hh, hh, z)]
    m["walls"].merge(K.loft([ring(h + 0.15, 0.0), ring(h + 0.15, 0.85), ring(h, 1.0), ring(h - 0.05, H)], "stone", smooth=False,
                            roles=["wall_alt", "trim", "stone"]))
    m["top"].merge(K.loft([ring(h - 0.1, H - 0.5), ring(h + 0.3, H - 0.15), ring(h + 0.3, H + 1.0), ring(h - 0.4, H + 1.0)],
                          "stone", smooth=False, roles=["trim", "stone", "step"]))
    tr = 1.35
    for k in range(4):
        mm = M.merlons(-h + tr + 0.2, h - tr - 0.2, 0.0, 0.0, 0.85, 0.45, "stone", merlon=1.5, gap=0.9)
        m["top"].merge(mm.translate(0.0, -(h + 0.1), H + 0.98).rotate_z(k * math.pi / 2))
        sx, sy = (1, 1) if k == 0 else ((-1, 1) if k == 1 else ((-1, -1) if k == 2 else (1, -1)))
        cx, cy = sx * (h + 0.05), sy * (h + 0.05)
        m["top"].merge(K.lathe([(0.0, H - 1.6), (tr - 0.3, H - 1.5), (tr, H - 0.6), (tr - 0.05, H + 2.2)], 6, "stone", smooth=True,
                               roles=["trim", "trim", "stone"]).translate(cx, cy, 0.0))
        if P["turrets"] == "roofed":
            m["top"].merge(M.cone_roof(tr - 0.05, H + 2.2, 2.6, "hull", overhang=0.3, droop=0.15, thick=0.18, segs=6, flare=0.3).translate(cx, cy, 0.0))
        else:
            m["top"].merge(ring_merlons(tr - 0.12, H + 2.18, 3, 0.6, 0.35, "stone", phase=math.pi / 6, width_frac=0.45).translate(cx, cy, 0.0))
    m["detail"].merge(M.beam((-h - 0.03, -h - 0.02, H * 0.55), (h + 0.03, -h - 0.02, H * 0.55), 0.3, 0.12, "trim", out=(0.0, -1.0, 0.0), bevel=0.3, embed=0.04))
    m["detail"].merge(M.beam((-h - 0.02, h + 0.03, H * 0.55), (-h - 0.02, -h - 0.03, H * 0.55), 0.3, 0.12, "trim", out=(-1.0, 0.0, 0.0), bevel=0.3, embed=0.04))
    m["detail"].merge(M.beam((h + 0.02, -h - 0.03, H * 0.55), (h + 0.02, h + 0.03, H * 0.55), 0.3, 0.12, "trim", out=(1.0, 0.0, 0.0), bevel=0.3, embed=0.04))
    # main door: stone pointed surround on the south face; windows: tall lancets (leaded glass) above
    fr = M.arch_frame("pointed", M.DOOR_CUT[0], M.DOOR_CUT[1], 0.7, 0.45, "trim", segs=4, y0=-0.62)
    m["detail"].merge(fr.translate(0.0, -h - 0.1 + 0.0, 0.0))
    for x, z in ((-2.3, H * 0.62), (2.3, H * 0.62)):
        lan = K.prism(M.opening_outline("pointed", 0.7, 2.0, 6), -0.06, 0.05, "glass")
        lan.apply(lambda a: a[:, [0, 2, 1]])
        lan.uv = [("n", [((p[0] + 0.35) / 0.7, p[2] / 2.0) for p in (lan.v[i] for i in fc)]) for fc in lan.f]
        m["detail"].merge(lan.orient_outward().translate(x, -h, z))
    jitter_all(m, seed, 0.02, skip=("walls",))
    socks = [M.sock("door", M.door_out((0.0, -h - 0.15, 0.0), "doorway"), "s", width_m=M.DOORWAY[0], height_m=M.DOORWAY[1],
                    needs="arch.door?", note="optional: a declared region door here takes the room's vlg.doorway")]
    return M.assemble(solids(m), {"size_m": s}, "lot_centre", sockets=socks, ground=False)


# ---------------------------------------------------------------- halls (interior shells) + ceilings
DOOR_ITEM = {"side": S.enum("s", ["n", "e", "s", "w"]), "cell": S.integer(0, 0, 4)}
MOUNT_ITEM = {"side": S.enum("n", ["n", "e", "s", "w"]), "cell": S.integer(0, 0, 4)}


@register("cst.hall", V, "shell", {
    "cells_x": S.integer(3, 1, 4), "cells_y": S.integer(4, 1, 5),
    "height": S.num(6.0, 3.5, 7.5),
    "doors": S.array(DOOR_ITEM, [{"side": "s", "cell": 1}], 6),
    "windows": S.array(MOUNT_ITEM, [{"side": "n", "cell": 0}, {"side": "n", "cell": 2}], 8, "tall painted lancets"),
    "torches": S.array(MOUNT_ITEM, [{"side": "e", "cell": 1}, {"side": "w", "cell": 1}, {"side": "e", "cell": 3}, {"side": "w", "cell": 3}], 10,
                       "torch sockets (warm baked pools; place cst.sconce)"),
    "mood": S.enum("hall", ["hall", "dungeon"], "hall: ashlar + pilasters + flagstones; dungeon: low rubble cells"),
}, "Castle hall shell on the room grid (keep hall, throne room, dungeon passage): ashlar walls on a rubble plinth "
   "with pilasters on cell boundaries and a dressed string course, flagstone floor with a pale border, door cuts with "
   "stone arch surrounds for vlg.doorway, tall painted lancets, torch sockets with warm baked pools.", origin="room_floor")
def hall(P, seed):
    dungeon = P["mood"] == "dungeon"
    H = P["height"]
    lights = [(t["side"], t["cell"], "torch", 2.4, 0.42, 5.0 if not dungeon else 4.2, 1.0) for t in P["torches"]]
    walls, floor, extras, socks, bl, info = M.room_shell(
        P["cells_x"], P["cells_y"], H, doors=[(d["side"], d["cell"]) for d in P["doors"]],
        windows=[] if dungeon else [(w["side"], w["cell"]) for w in P["windows"]], lights=lights,
        wall_role="wall_alt" if dungeon else "stone", post_role=None if dungeon else "trim", post_depth=0.16,
        plinth=(0.6, 0.06, "wall_alt"), rails=[] if dungeon else [(3.2, 3.42)], rail_role="trim", floor_role="step",
        border=0.0 if dungeon else 0.7, border_role="trim", cap_role="stone", window_z=(2.4, 4.6),
        arch=(0.32, 0.5), arch_role="trim")
    nodes = [Node("floor", floor, "shell"), Node("walls", walls, "shell")]
    if extras.f:
        nodes.append(Node("fittings", extras, "solid"))
    return M.assemble(nodes, dict(info, mood=P["mood"], height_m=H), "cell_block_centre", cells=(P["cells_x"], P["cells_y"]),
                      sockets=socks, lights=bl, ground=False)


@register("cst.ceiling", V, "shell", {
    "cells_x": S.integer(3, 1, 4), "cells_y": S.integer(4, 1, 5),
    "height": S.num(6.0, 4.5, 7.5),
    "kind": S.enum("trusses", ["trusses", "vault"]),
}, "Hall ceiling (one-sided, facing down, N64 cutaway-friendly): dark boards on arched oak trusses across the span, "
   "or a stone barrel vault with transverse ribs.", origin="cell_block_ceiling")
def hall_ceiling(P, seed):
    W, Dd = P["cells_x"] * M.CELL, P["cells_y"] * M.CELL
    hx, hy = W / 2 - M.WALL_T, Dd / 2 - M.WALL_T
    H = P["height"]
    m = {"ceiling": K.Mesh(), "ribs": K.Mesh()}
    if P["kind"] == "vault":
        segs = 6
        rings = []
        for y in M.np.linspace(-hy, hy, max(2, P["cells_y"] + 1)):
            rings.append([(-hx * math.cos(math.pi * i / segs), y, H - 1.2 + 1.2 * math.sin(math.pi * i / segs)) for i in range(segs + 1)])
        sheet = K.Mesh()
        for j in range(len(rings) - 1):
            for i in range(segs):
                a, b, c, d = rings[j][i], rings[j][i + 1], rings[j + 1][i + 1], rings[j + 1][i]
                sheet.add([a, d, c, b], [(0, 1, 2, 3)], "stone", False)
        m["ceiling"].merge(M.weld(sheet))
        for y in M.np.linspace(-hy, hy, P["cells_y"] + 1)[1:-1]:
            for i in range(segs):
                p0 = (-hx * math.cos(math.pi * i / segs), y, H - 1.2 + 1.2 * math.sin(math.pi * i / segs) - 0.02)
                p1 = (-hx * math.cos(math.pi * (i + 1) / segs), y, H - 1.2 + 1.2 * math.sin(math.pi * (i + 1) / segs) - 0.02)
                dx, dz = p1[0] - p0[0], p1[2] - p0[2]
                ln = math.hypot(dx, dz)
                e = 0.05 / ln
                m["ribs"].merge(M.beam((p0[0] - dx * e, y, p0[2] - dz * e), (p1[0] + dx * e, y, p1[2] + dz * e), 0.32 + 0.01 * i, 0.18, "trim",
                                       out=(0.0, 0.0, -1.0), bevel=0.3, embed=0.02))
    else:
        m["ceiling"].merge(M.floor_sheet(-hx, -hy, hx, hy, H, "ceiling", step=2.0, up=False))
        for y in M.np.linspace(-hy, hy, P["cells_y"] + 1)[1:-1]:
            m["ribs"].merge(M.beam((-hx - 0.02, y, H + 0.02), (hx + 0.02, y, H + 0.02), 0.32, 0.36, "frame", out=(0.0, 0.0, -1.0), bevel=0.2, embed=0.0))
            for sx in (-1, 1):
                m["ribs"].merge(M.beam((sx * hx, y, H - 1.6), (sx * (hx - 1.4), y, H - 0.3), 0.24, 0.24, "frame", out=(0.0, 1.0, 0.0), bevel=0.2, embed=0.0))
    nodes = [Node("ceiling", m["ceiling"], "shell")]
    if m["ribs"].f:
        nodes.append(M.solid("ribs", m["ribs"]))
    return M.assemble(nodes, {"height_m": H, "kind": P["kind"]}, "cell_block_centre", cells=(P["cells_x"], P["cells_y"]), ground=False)


# ---------------------------------------------------------------- throne room set
@register("cst.throne", V, "furniture_large", {
    "back": S.enum("crest", ["crest", "canopy"]),
}, "Throne: a tall gilded-oak chair with a pointed crest back, carved arm posts with gilt finials, a red cushion "
   "and seat back panel; canopy kind adds a cloth tester on two posts.", origin="floor_center")
def throne(P, seed):
    m = {"frame": K.Mesh(), "gilt": K.Mesh(), "cloth": K.Mesh()}
    m["frame"].merge(M.chamfer_box(0.0, 0.0, 0.0, 1.3, 1.05, 0.5, "body_alt", bevel=0.06, base_bevel=0.04))
    m["cloth"].merge(M.chamfer_box(0.0, -0.05, 0.5, 1.0, 0.82, 0.14, "cushion", bevel=0.05))
    back = [(-0.62, 0.0), (0.62, 0.0), (0.62, 1.55), (0.3, 1.75), (0.0, 2.15), (-0.3, 1.75), (-0.62, 1.55)]
    bk = M.slab_y([(x, z + 0.5) for x, z in back], 0.32, 0.52, "body_alt")
    m["frame"].merge(bk)
    pan = [(-0.44, 0.15), (0.44, 0.15), (0.44, 1.35), (0.0, 1.6), (-0.44, 1.35)]
    pn = M.slab_y([(x, z + 0.5) for x, z in pan], 0.27, 0.34, "cushion")
    pn.uv = [None] * len(pn.f)
    m["cloth"].merge(pn)
    for sx in (-1, 1):
        m["frame"].merge(M.chamfer_box(sx * 0.62, -0.1, 0.5, 0.14, 0.8, 0.12, "body_alt", bevel=0.03).translate(0.0, 0.0, 0.38))
        m["frame"].merge(M.post(sx * 0.62, -0.42, 0.0, 1.0, 0.07, 0.06, "body_alt", sides=6))
        m["gilt"].merge(K.lathe([(0.0, 0.0), (0.09, 0.03), (0.1, 0.1), (0.0, 0.2)], 6, "chrome", smooth=True).translate(sx * 0.62, -0.42, 1.0))
    m["gilt"].merge(K.lathe([(0.0, 0.0), (0.1, 0.04), (0.12, 0.14), (0.0, 0.3)], 6, "chrome", smooth=True).translate(0.0, 0.42, 2.62))
    m["gilt"].merge(M.beam((-0.64, 0.3, 2.05), (0.64, 0.3, 2.05), 0.1, 0.06, "chrome", out=(0.0, -1.0, 0.0), bevel=0.2, embed=0.02))
    if P["back"] == "canopy":
        for sx in (-1, 1):
            m["frame"].merge(M.post(sx * 0.85, 0.48, 0.0, 3.1, 0.06, 0.05, "body_alt", sides=6))
        m["cloth"].merge(M.chamfer_box(0.0, 0.1, 3.0, 1.9, 1.2, 0.16, "band", bevel=0.04))
    return M.centred(solids(m), {"back": P["back"]})


@register("cst.dais", V, "structure", {
    "cells_x": S.integer(2, 1, 3), "steps": S.integer(3, 1, 4),
}, "Stepped stone dais for a throne (one cell deep, cells_x wide): dressed flagstone treads with pale nosings and a "
   "carpet strip down the middle steps.", origin="floor_center")
def dais(P, seed):
    W = P["cells_x"] * M.CELL - 1.0
    n = P["steps"]
    m = {"steps": K.Mesh(), "carpet": K.Mesh()}
    D = 3.2
    for i in range(n):
        inset = i * 0.45
        m["steps"].merge(M.chamfer_box(0.0, inset / 2, i * 0.22, W - inset * 1.2, D - inset, 0.24, "step", bevel=0.04, top_role="step"))
    zt = n * 0.22
    cw = 1.4
    for i in range(n):
        y = -D / 2 + i * 0.45
        z = i * 0.22 + 0.24
        m["carpet"].merge(K.box(0.0, y - 0.035, z - 0.12, cw, 0.02, 0.22, "quilt"))
        y1 = (-D / 2 + (i + 1) * 0.45 - 0.05) if i < n - 1 else (y + 1.2)
        m["carpet"].merge(K.box(0.0, (y - 0.04 + y1) / 2, z + 0.008, cw, y1 - y + 0.04, 0.016, "quilt"))
    a = M.centred(solids(m), {"top_m": zt})
    a.meta["sockets"] = [M.sock("throne", (0.0, 0.3, zt), "up", needs="cst.throne")]
    return a


@register("cst.carpet", V, "structure", {
    "length": S.num(8.0, 3.0, 12.0), "width": S.num(1.6, 1.0, 2.4),
}, "Woven runner carpet (quilt role: dark border, pale stripe, diamond medallions) with a bevelled edge.", origin="floor_center")
def carpet(P, seed):
    L, w = P["length"], P["width"]
    m = M.chamfer_box(0.0, 0.0, 0.0, w, L, 0.03, "quilt", bevel=0.012)
    top = [i for i, f in enumerate(m.f)]
    m.uv = [("n", [((p[0] + w / 2) / w, (p[1] + L / 2) / L * max(1.0, L / 2.0)) for p in (m.v[j] for j in m.f[i])])
            if abs(M.bake.face_normals(np.asarray(m.v), [m.f[i]])[0][2]) > 0.9 else None for i in top]
    return M.centred([M.solid("carpet", m)], {})


@register("cst.pillar", V, "structure", {
    "style": S.enum("round", ["round", "square", "clustered"]),
    "height": S.num(6.0, 3.0, 7.5),
}, "Hall pillar: moulded base and capital with a round, square or clustered shaft (ashlar), pale dressed stone.",
   origin="floor_center")
def pillar(P, seed):
    H, st = P["height"], P["style"]
    m = {"shaft": K.Mesh(), "mould": K.Mesh()}
    if st == "square":
        m["mould"].merge(M.chamfer_box(0.0, 0.0, 0.0, 1.0, 1.0, 0.4, "trim", bevel=0.06))
        m["shaft"].merge(M.octa_box(0.0, 0.0, 0.38, 0.72, 0.72, H - 0.8, "stone", chamfer=0.1, top_bevel=0.02))
        m["mould"].merge(M.chamfer_box(0.0, 0.0, H - 0.44, 1.0, 1.0, 0.44, "trim", bevel=0.08, base_bevel=0.1))
    else:
        m["mould"].merge(K.lathe([(0.55, 0.0), (0.55, 0.18), (0.45, 0.32), (0.4, 0.42)], 8, "trim", smooth=False, start=math.pi / 8))
        if st == "round":
            m["shaft"].merge(K.lathe([(0.36, 0.4), (0.33, H - 0.5)], 8, "stone", smooth=True).translate(0.0, 0.0, 0.0))
        else:
            for k in range(4):
                a = k * math.pi / 2 + math.pi / 4
                m["shaft"].merge(K.lathe([(0.2, 0.4), (0.19, H - 0.5)], 6, "stone", smooth=True).translate(0.2 * math.cos(a), 0.2 * math.sin(a), 0.0))
        m["mould"].merge(K.lathe([(0.34, H - 0.52), (0.42, H - 0.36), (0.58, H - 0.2), (0.58, H)], 8, "trim", smooth=False, start=math.pi / 8))
    return M.centred(solids(m), {"style": st})


@register("cst.banner", V, "soft", {
    "design": S.integer(0, 0, 3, "heraldry atlas quadrant: 0 chevron, 1 cross, 2 pale, 3 roundel"),
    "length": S.num(2.6, 1.6, 4.0),
}, "Wall banner for a wall socket (wall-face anchor, front +Z): an original heraldic hanging (band atlas) with a "
   "pointed tail, on a turned pole with gilt finials and an iron bracket.", origin="wall_face")
def banner(P, seed):
    L, w = P["length"], 1.1
    k = P["design"]
    u0, v0 = 0.5 * (k % 2), (0.5 if k < 2 else 0.0)
    zt = 4.6
    prof = [(-w / 2, zt), (w / 2, zt), (w / 2, zt - L + 0.45), (0.0, zt - L), (-w / 2, zt - L + 0.45)]
    v = []
    for t in (-0.16, -0.12):
        for x, z in prof:
            v.append((x, t, z))
    uv = [(u0 + 0.5 * (x + w / 2) / w, v0 + 0.5 * (z - (zt - L)) / L) for x, z in prof]
    f = [(5, 6, 7, 8, 9), (4, 3, 2, 1, 0)] + [(i, (i + 1) % 5, (i + 1) % 5 + 5, i + 5) for i in range(5)]
    cloth = K.Mesh().add(v, f, "band", False, [("n", uv), ("n", list(reversed(uv)))] + [None] * 5).orient_outward()
    m = {"cloth": cloth, "pole": K.Mesh()}
    m["pole"].merge(M.beam((-w / 2 - 0.15, -0.14, zt + 0.06), (w / 2 + 0.15, -0.14, zt + 0.06), 0.07, 0.07, "wood", out=(0.0, 0.0, 1.0), bevel=0.3, embed=0.0))
    for sx in (-1, 1):
        m["pole"].merge(K.lathe([(0.0, 0.0), (0.06, 0.02), (0.05, 0.08), (0.0, 0.12)], 5, "chrome", smooth=True).rotate_y(sx * math.pi / 2).translate(sx * (w / 2 + 0.15), -0.14, zt + 0.06))
        m["pole"].merge(M.beam((sx * 0.4, 0.0, zt + 0.3), (sx * 0.4, -0.16, zt + 0.08), 0.04, 0.04, "metal", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    return M.assemble(solids(m), {"design": k}, "wall_face", ground=False)


@register("cst.chandelier", V, "furniture", {
    "candles": S.integer(6, 4, 10),
}, "Iron ring chandelier hung on chains from the ceiling (origin at the hook, hangs down -Z): candles glow, baked "
   "warm pool on its own iron.", origin="ceiling_hook")
def chandelier(P, seed):
    n = P["candles"]
    m = {"iron": K.Mesh(), "candles": K.Mesh()}
    R, zr = 0.9, -1.6
    ring = [(R * math.cos(a), R * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
    rr = M.ring_path_solid(ring, zr, zr + 0.08, 0.08, "metal")
    m["iron"].merge(rr)
    for k in range(3):
        a = 2 * math.pi * k / 3
        m["iron"].merge(M.beam((0.0, 0.0, -0.02), (R * math.cos(a) * 0.98, R * math.sin(a) * 0.98, zr + 0.06), 0.025, 0.025, "metal",
                               out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        x, y = R * math.cos(a), R * math.sin(a)
        m["candles"].merge(K.lathe([(0.04, 0.0), (0.035, 0.22)], 5, "paper", smooth=False).translate(x, y, zr + 0.08))
        m["candles"].merge(K.lathe([(0.0, 0.0), (0.03, 0.04), (0.0, 0.12)], 4, "light", smooth=False).translate(x, y, zr + 0.3))
    a = M.assemble(solids(m), {"hangs_m": 1.75}, "ceiling_hook", lights=[{"pos": [0.0, 0.0, zr + 0.3], "radius": 2.4, "strength": 0.9}], ground=False)
    return a


@register("cst.brazier", V, "furniture", {
    "height": S.num(1.1, 0.8, 1.5),
}, "Standing iron brazier: a hammered bowl of burning coals on three splayed legs (fire glows, baked warm pool).",
   origin="floor_center")
def brazier(P, seed):
    h = P["height"]
    m = {"iron": K.Mesh(), "fire": K.Mesh()}
    m["iron"].merge(K.lathe([(0.12, h - 0.35), (0.45, h - 0.12), (0.5, h), (0.42, h + 0.02), (0.0, h - 0.18)], 8, "metal", smooth=False))
    for k in range(3):
        a = 2 * math.pi * k / 3
        m["iron"].merge(M.beam((0.55 * math.cos(a), 0.55 * math.sin(a), 0.0), (0.18 * math.cos(a), 0.18 * math.sin(a), h - 0.3), 0.06, 0.06, "metal",
                               out=(-math.sin(a), math.cos(a), 0.0), bevel=0.0, embed=0.0))
    m["fire"].merge(M.blob(0.0, 0.0, h - 0.02, 0.36, 0.36, 0.1, "fire", seed, segs=7, rings=3, lump=0.2))
    m["fire"].merge(K.lathe([(0.0, 0.0), (0.26, 0.05), (0.12, 0.42), (0.0, 0.62)], 5, "fire", smooth=False).translate(0.0, 0.0, h))
    return M.assemble(solids(m), {}, "free", lights=[{"pos": [0.0, 0.0, h + 0.2], "radius": 2.5, "strength": 1.0}])


@register("cst.sconce", V, "prop", {
    "lit": S.boolean(True),
}, "Wall torch for a torch socket (wall-face anchor, front +Z): an iron bracket and a pitch torch with a flame "
   "(the shell bakes the pool; the runtime emitter flickers).", origin="wall_face")
def sconce(P, seed):
    m = {"iron": K.Mesh(), "torch": K.Mesh()}
    m["iron"].merge(M.chamfer_box(0.0, -0.03, 2.0, 0.16, 0.06, 0.36, "metal", bevel=0.015))
    m["iron"].merge(M.beam((0.0, -0.05, 2.12), (0.0, -0.36, 2.2), 0.05, 0.05, "metal", out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
    m["torch"].merge(K.lathe([(0.035, 0.0), (0.05, 0.4), (0.075, 0.48), (0.04, 0.52)], 5, "wood", smooth=False).translate(0.0, -0.4, 1.95))
    if P["lit"]:
        m["torch"].merge(K.lathe([(0.0, 0.0), (0.08, 0.06), (0.05, 0.22), (0.0, 0.34)], 5, "fire", smooth=False).translate(0.0, -0.4, 2.47))
    return M.assemble(solids(m), {"lit": P["lit"]}, "wall_face", ground=False)


# ---------------------------------------------------------------- dungeon cells + spiral stair
@register("cst.cell", V, "structure", {
    "door": S.enum("closed", ["closed", "open"], "barred door state pair"),
}, "Dungeon cell on one grid cell (4 x 4 m, open side toward -Y): rubble back and side walls, an iron-barred front "
   "with a barred door (closed / swung open), straw on the floor and wall shackles.", origin="cell_centre")
def cell(P, seed):
    m = {"walls": K.Mesh(), "bars": K.Mesh(), "straw": K.Mesh()}
    H = 3.0
    m["walls"].merge(M.chamfer_box(0.0, 1.7, 0.0, 3.8, 0.6, H, "wall_alt", bevel=0.04, top_role="wall_alt"))
    for sx in (-1, 1):
        m["walls"].merge(M.chamfer_box(sx * 1.75, -0.1, 0.0, 0.5, 3.0, H, "wall_alt", bevel=0.04))
    m["bars"].merge(M.chamfer_box(0.0, -1.55, H - 0.25, 3.0, 0.16, 0.18, "metal", bevel=0.02))
    m["bars"].merge(M.chamfer_box(0.0, -1.55, 0.0, 3.0, 0.16, 0.1, "metal", bevel=0.02))
    xs = np.linspace(-1.35, 1.35, 9)
    for i, x in enumerate(xs):
        if -0.5 < x < 0.6:
            continue
        m["bars"].merge(M.chamfer_box(x, -1.55, 0.08, 0.06, 0.06, H - 0.3, "metal", bevel=0.012))
    door = K.Mesh()
    for x in np.linspace(-0.4, 0.45, 4):
        door.merge(M.chamfer_box(x, 0.0, 0.12, 0.05, 0.05, 2.3, "metal", bevel=0.01))
    for z in (0.3, 1.25, 2.3):
        door.merge(M.chamfer_box(0.02, -0.04, z, 0.98, 0.05, 0.07, "metal", bevel=0.01))
    if P["door"] == "open":
        door.translate(0.48, 0.0, 0.0).rotate_z(math.radians(-100.0)).translate(-0.48, 0.0, 0.0)
    m["bars"].merge(door.translate(0.0, -1.55, 0.0))
    for k in range(2):
        m["straw"].merge(M.blob(-0.9 + 1.5 * k, 0.8, 0.0, 0.7, 0.5, 0.14, "fur", seed + k, segs=7, rings=3, lump=0.12))
    m["bars"].merge(M.chamfer_box(1.1, 1.38, 1.5, 0.3, 0.05, 0.06, "metal", bevel=0.01))
    m["bars"].merge(M.chamfer_box(-1.1, 1.38, 1.5, 0.3, 0.05, 0.06, "metal", bevel=0.01))
    socks = [M.sock("cell_door", (0.0, -1.55, 0.0), "s", state=P["door"], pair="cst.cell__open" if P["door"] == "closed" else "cst.cell")]
    return M.assemble(solids(m), {"door": P["door"]}, "cell_centre", cells=(1, 1), sockets=socks, ground=False)


@register("cst.spiral_stair", V, "structure", {
    "turns": S.num(1.0, 0.5, 1.5), "height": S.num(4.5, 3.0, 6.0),
}, "Newel (spiral) stair for a tower or keep corner: wedge stone steps winding up around a central newel inside a "
   "low drum wall, rising counter-clockwise (one cell).", origin="floor_center")
def spiral_stair(P, seed):
    H, turns = P["height"], P["turns"]
    n = max(6, int(round(turns * 14)))
    R, r = 1.75, 0.22
    m = {"steps": K.Mesh(), "newel": K.Mesh(), "drum": K.Mesh()}
    for i in range(n):
        a0 = 2 * math.pi * turns * i / n
        a1 = 2 * math.pi * turns * (i + 1) / n + 0.03
        z = H * i / n
        pts = [(r * math.cos(a0), r * math.sin(a0)), (R * math.cos(a0), R * math.sin(a0)), (R * math.cos(a1), R * math.sin(a1)), (r * math.cos(a1), r * math.sin(a1))]
        st = K.prism(pts, z, z + H / n + 0.02, "step")
        m["steps"].merge(st)
    m["newel"].merge(K.lathe([(r + 0.04, 0.0), (r, H + 0.6)], 8, "trim", smooth=True))
    ring = [(R + 0.05) * math.cos(a) for a in np.linspace(0, 2 * math.pi, 11, endpoint=False)]
    pts = [((R + 0.12) * math.cos(a), (R + 0.12) * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    m["drum"].merge(M.ring_path_solid(pts, 0.0, 1.0, 0.24, "wall_alt", chamfer=0.03))
    _ = ring
    socks = [M.sock("path", (R * 0.6, -0.4, 0.0), "s", width_m=1.4), M.sock("landing", (R * 0.6 * math.cos(2 * math.pi * turns), R * 0.6 * math.sin(2 * math.pi * turns), H), "up")]
    return M.centred(solids(m), {"rise_m": H})
