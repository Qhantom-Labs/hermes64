"""DUNGEONKIT dungeon props family (dprop.*), theme-agnostic (Blender space, +Z up, front faces -Y).

Floor props are footprint-centred (finalize). Wall-mounted props (sconce, banner) and the corner cobweb have their
origin on the wall face (cobweb: on the corner line) at floor level, so they snap to the torch / wall sockets of the
dgn.* pieces (see kits/core/gen_dungeon.py TORCH_Z / sockets). Emitters (sconce, brazier, crystal) declare
meta["bake_lights"] (baked warm pools in point_bake packs) and meta["emitter"] (runtime light hint mirrored in the
pack view.json look.emitters).
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .gen_dungeon import TORCH_Z, grid_meta, panel, sock, light
from .genutil import finalize
from .rng import rng

V = "1.0.0"
MOTIFS = ["spiral", "eye", "sun", "serpent", "knot", "key", "wings"]


def flame(cx, cy, z0, h, r, role="fire", segs=6):
    """Closed teardrop flame (lathe): wide low belly, pointed tip."""
    prof = [(0.0, z0), (r * 0.75, z0 + h * 0.12), (r, z0 + h * 0.32), (r * 0.7, z0 + h * 0.62), (r * 0.28, z0 + h * 0.86), (0.0, z0 + h)]
    return K.lathe(prof, segs, role, smooth=True).translate(cx, cy, 0)


# ---------------------------------------------------------------- dprop.sconce
@register("dprop.sconce", V, "prop", {
    "style": S.enum("bracket", ["bracket", "cage"]),
    "lit": S.boolean(True),
}, "Wall torch sconce: iron back plate and bracket holding a tilted timber torch with a painted flame (emissive). "
   "Origin on the wall face at floor level; the flame sits at the torch-socket height.", wall_mounted=True, origin="opening")
def sconce(P, seed):
    zf = TORCH_Z
    m = K.Mesh()
    m.merge(K.box(0, -0.02, zf - 0.55, 0.16, 0.04, 0.34, "metal"))
    m.merge(K.tube([(0, -0.03, zf - 0.6), (0, -0.2, zf - 0.55), (0, -0.33, zf - 0.38)], 0.025, 4, "metal", smooth=False))
    cup = K.lathe([(0.0, zf - 0.47), (0.06, zf - 0.47), (0.085, zf - 0.33), (0.07, zf - 0.31), (0.0, zf - 0.31)], 5, "metal", smooth=False)
    m.merge(cup.translate(0, -0.33, 0))
    if P["style"] == "cage":
        for k in range(3):
            a = math.pi / 2 + k * 2 * math.pi / 3
            m.merge(K.tube([(0.07 * math.cos(a), -0.33 + 0.07 * math.sin(a), zf - 0.32),
                            (0.1 * math.cos(a), -0.33 + 0.1 * math.sin(a), zf + 0.02)], 0.014, 3, "metal", smooth=False))
    torch = K.cylinder(0, 0, -0.3, 0.045, 0.42, 5, "post", smooth=True)
    torch.rotate_x(-0.18).translate(0, -0.33, zf - 0.28)
    m.merge(torch)
    nodes = [Node("sconce", m)]
    meta = grid_meta("wall_face", None, [sock("mount", (0, 0, 0), "s", fits="torch")], lit=P["lit"])
    if P["lit"]:
        nodes.append(Node("flame", flame(0, -0.36, zf - 0.14, 0.56, 0.15, "fire")))
        meta["bake_lights"] = [light((0, -0.36, zf + 0.05), 1.2, 0.8)]
        meta["emitter"] = {"offset_gltf": [0.0, round(zf + 0.05, 3), 0.36], "radius_m": 5.5, "warm": True}
    return Asset(nodes, meta)


# ---------------------------------------------------------------- dprop.brazier
@register("dprop.brazier", V, "furniture", {
    "height": S.num(1.0, 0.6, 1.4), "lit": S.boolean(True),
}, "Standing iron brazier: wide bowl on three splayed legs with a ring brace, heaped glowing coals and a flame.",
   origin="floor_center")
def brazier(P, seed):
    h = P["height"]
    r = rng(seed, "dprop.brazier")
    bowl = K.lathe([(0.0, h - 0.22), (0.2, h - 0.22), (0.38, h - 0.08), (0.46, h + 0.06), (0.42, h + 0.08), (0.34, h - 0.02),
                    (0.0, h - 0.02)], 7, "metal", smooth=False)
    legs = K.Mesh()
    for k in range(3):
        a = 2 * math.pi * k / 3
        legs.merge(K.tube([(0.16 * math.cos(a), 0.16 * math.sin(a), h - 0.18), (0.3 * math.cos(a), 0.3 * math.sin(a), h * 0.45),
                           (0.42 * math.cos(a), 0.42 * math.sin(a), 0.0)], 0.035, 4, "metal", smooth=False))
    brace = K.torus(0.27, 0.02, 8, 3, "metal").translate(0, 0, h * 0.42)
    nodes = [Node("bowl", bowl), Node("legs", legs.merge(brace))]
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up")], lit=P["lit"])
    if P["lit"]:
        coals = D.rock_blob(0, 0, h - 0.04, 0.32, 0.32, 0.09, r, "fire", segs=7, rings=3, jitter=0.15)
        nodes.append(Node("coals", coals))
        fl = flame(0, 0, h + 0.02, 0.62, 0.22, "fire", segs=6)
        fl.merge(flame(0.13, 0.06, h + 0.0, 0.4, 0.12, "fire", segs=4))
        nodes.append(Node("flame", fl))
        meta["bake_lights"] = [light((0, 0, h + 0.3), 1.6, 0.9)]
        meta["emitter"] = {"offset_gltf": [0.0, round(h + 0.35, 3), 0.0], "radius_m": 6.5, "warm": True}
    return finalize(nodes, meta)


# ---------------------------------------------------------------- dprop.chest
@register("dprop.chest", V, "furniture", {
    "size": S.enum("small", ["small", "large"]), "state": S.enum("closed", ["closed", "open"]),
}, "Iron-banded timber treasure chest with a barrel lid, corner caps and a lock plate; large = the big ornate key "
   "chest. open: lid swung back.", origin="floor_center")
def chest(P, seed):
    big = P["size"] == "large"
    w, d, h = (1.3, 0.85, 0.62) if big else (0.85, 0.55, 0.42)
    body = D.bevel_box(0, 0, 0, w, d, h, "door", bevel=0.03)
    rr = d / 2
    k = 5
    lid_o = [(-rr * math.cos(math.pi * i / k), rr * 0.75 * math.sin(math.pi * i / k)) for i in range(k + 1)]
    lid = K.prism(lid_o, -w / 2 + 0.02, w / 2 - 0.02, "door").rotate_x(math.pi / 2).rotate_z(math.pi / 2)
    xs = (-w / 2 + 0.14, w / 2 - 0.14) if not big else (-w / 2 + 0.16, 0.0, w / 2 - 0.16)
    lidg = K.Mesh().merge(lid)
    for x in xs:
        lidg.merge(K.tube([(x, -rr * math.cos(math.pi * i / k) * 1.04, rr * 0.75 * math.sin(math.pi * i / k) * 1.04 + 0.01)
                           for i in range(k + 1)], 0.035, 3, "metal", smooth=False))
    bands = K.Mesh()
    for x in xs:
        bands.merge(K.box(x, 0, h / 2, 0.07, d + 0.03, h + 0.01, "metal"))
    lock = K.Mesh()
    lock.merge(K.box(0, -d / 2 - 0.02, h - 0.1, 0.16 if not big else 0.24, 0.05, 0.2 if not big else 0.28, "metal"))
    lock.merge(K.box(0, -d / 2 - 0.05, h - 0.12, 0.04, 0.02, 0.07, "opening"))
    if big:
        for sx in (-1, 1):
            for sy in (-1, 1):
                lock.merge(K.box(sx * (w / 2 - 0.03), sy * (d / 2 - 0.03), h / 2, 0.1, 0.1, h + 0.02, "metal"))
    nodes = [Node("body", body), Node("bands", bands), Node("lock", lock)]
    if P["state"] == "open":
        lidg.translate(0, -rr, 0).rotate_x(-1.95).translate(0, rr + 0.02, h)
        inner = K.Mesh().add([(-w / 2 + 0.05, -d / 2 + 0.05, h - 0.02), (w / 2 - 0.05, -d / 2 + 0.05, h - 0.02),
                              (w / 2 - 0.05, d / 2 - 0.05, h - 0.02), (-w / 2 + 0.05, d / 2 - 0.05, h - 0.02)], [(0, 1, 2, 3)], "opening", False)
        glint = D.rock_blob(0, 0, h - 0.08, w * 0.22, d * 0.2, 0.08, rng(seed, "glint"), "light", segs=5, rings=3)
        nodes += [Node("lid", lidg), Node("gold", glint), Node("inside", inner, "card")]
    else:
        lidg.translate(0, 0, h)
        nodes.append(Node("lid", lidg))
    return finalize(nodes, grid_meta("free", None, [sock("prop", (0, 0, 0), "up", interact="open")], size=P["size"], state=P["state"]))


# ---------------------------------------------------------------- dprop.breakable
@register("dprop.breakable", V, "furniture", {
    "kind": S.enum("pot", ["pot", "urn", "crates"]),
}, "Breakable dungeon containers: round clay pot with a rolled lip, tall two-handled urn, or a stack of iron-cornered "
   "timber crates.", origin="floor_center")
def breakable(P, seed):
    kind = P["kind"]
    r = rng(seed, "dprop.breakable", kind)
    nodes = []
    if kind == "pot":
        prof = [(0.0, 0.0), (0.16, 0.0), (0.27, 0.12), (0.3, 0.26), (0.24, 0.42), (0.15, 0.5), (0.17, 0.55), (0.12, 0.57), (0.0, 0.52)]
        nodes.append(Node("pot", K.lathe(prof, 8, "body_alt", smooth=True)))
    elif kind == "urn":
        prof = [(0.0, 0.0), (0.18, 0.0), (0.2, 0.06), (0.15, 0.12), (0.3, 0.4), (0.32, 0.6), (0.2, 0.85), (0.14, 0.92), (0.19, 1.0),
                (0.15, 1.03), (0.0, 0.98)]
        nodes.append(Node("urn", K.lathe(prof, 8, "body_alt", smooth=True)))
        hd = K.Mesh()
        for sx in (-1, 1):
            hd.merge(K.tube([(sx * 0.16, 0, 0.88), (sx * 0.3, 0, 0.88), (sx * 0.33, 0, 0.74), (sx * 0.28, 0, 0.64)], 0.025, 4, "body_alt", smooth=False))
        nodes.append(Node("handles", hd))
    else:
        cr = K.Mesh()
        boxes = [(0, 0, 0, 0.9, 0.0), (0.92, 0.05, 0, 0.7, 0.3), (0.42, 0.0, 0.9, 0.7, -0.2)]
        for x, y, z, s, a in boxes:
            b = D.bevel_box(0, 0, 0, s, s, s, "wood", bevel=0.03)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    b.merge(K.box(sx * (s / 2 - 0.02), sy * (s / 2 - 0.02), s / 2, 0.07, 0.07, s + 0.01, "metal"))
            b.rotate_z(a).translate(x, y, z)
            cr.merge(b)
        nodes.append(Node("crates", cr))
    return finalize(nodes, grid_meta("free", None, [sock("prop", (0, 0, 0), "up", interact="break")], kind=kind))


# ---------------------------------------------------------------- dprop.switch
@register("dprop.switch", V, "furniture", {
    "kind": S.enum("orb", ["orb", "lever"]),
}, "Switch plinth: carved tapering stone pedestal with a crystal orb in a claw cup (strike to toggle) or an iron "
   "floor lever in a slotted block.", origin="floor_center")
def switch(P, seed):
    nodes = []
    if P["kind"] == "orb":
        ped = D.taper_loft(0, 0, [0.0, 0.18, 0.22, 0.95, 1.0, 1.12], [(0.36, 0.36), (0.36, 0.36), (0.26, 0.26), (0.2, 0.2), (0.28, 0.28),
                                                                       (0.28, 0.28)], "trim", bevel=0.05)
        nodes.append(Node("pedestal", ped))
        claws = K.Mesh()
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2
            claws.merge(K.tube([(0.14 * math.cos(a), 0.14 * math.sin(a), 1.1), (0.21 * math.cos(a), 0.21 * math.sin(a), 1.25),
                                (0.13 * math.cos(a), 0.13 * math.sin(a), 1.4)], 0.03, 3, "metal", smooth=False))
        nodes.append(Node("claws", claws))
        nodes.append(Node("orb", K.sphere(0, 0, 1.33, 0.19, 0.19, 0.19, 8, 5, "orb", smooth=True)))
        meta_e = {"offset_gltf": [0, 1.33, 0], "radius_m": 2.5, "warm": False}
    else:
        blk = D.bevel_box(0, 0, 0, 0.7, 0.5, 0.45, "trim", bevel=0.05)
        nodes.append(Node("block", blk))
        lev = K.Mesh()
        lev.merge(K.box(0, 0, 0.47, 0.12, 0.34, 0.04, "opening"))
        arm = K.cylinder(0, 0, 0.0, 0.035, 0.75, 5, "metal").rotate_x(-0.45).translate(0, 0, 0.42)
        lev.merge(arm)
        lev.merge(K.sphere(0, -0.32, 1.1, 0.07, 0.07, 0.07, 6, 4, "metal"))
        nodes.append(Node("lever", lev))
        meta_e = None
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up", interact="toggle")], kind=P["kind"])
    if meta_e:
        meta["emitter"] = meta_e
    return finalize(nodes, meta)


# ---------------------------------------------------------------- dprop.plate
@register("dprop.plate", V, "prop", {
    "size": S.num(1.0, 0.6, 1.6), "state": S.enum("up", ["up", "down"]),
}, "Floor pressure plate: carved square stone slab with a painted motif in a dressed sunken frame; down = pressed "
   "flush.", origin="floor_center")
def plate(P, seed):
    s = P["size"]
    fr_o = K.rounded_rect2d(s + 0.3, s + 0.3, 0.04, 1)
    fr_i = K.rounded_rect2d(s + 0.04, s + 0.04, 0.02, 1)
    frame = K.prism(fr_o, 0.0, 0.05, "trim", holes=[fr_i])
    top = 0.11 if P["state"] == "up" else 0.035
    # painted motif on the top face (+Z)
    x0, x1, y0, y1 = -s / 2, s / 2, -s / 2, s / 2
    v = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0), (x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top)]
    f = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    uvs = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5
    slab = K.Mesh().add(v, f, ["wall_alt", "trim", "trim", "trim", "trim", "trim"], False, uvs)
    return finalize([Node("frame", frame), Node("slab", slab)],
                    grid_meta("free", None, [sock("floor_prop", (0, 0, 0), "up", interact="step")], state=P["state"]))


# ---------------------------------------------------------------- dprop.block
@register("dprop.block", V, "furniture", {
    "size": S.num(1.2, 0.8, 1.6), "motif": S.enum("spiral", MOTIFS),
}, "Pushable block: a chamfered carved stone (every edge bevelled, never a plain cube) with a carved relief motif "
   "inset on all four sides and a worn top.", origin="floor_center")
def block(P, seed):
    s = P["size"]
    b = 0.09 * s
    out = K.rounded_rect2d(s, s, b, 1)
    inn = K.rounded_rect2d(s - 2 * b, s - 2 * b, b * 0.5, 1)
    rings = [K.ring3d(0, 0, 0.0, inn), K.ring3d(0, 0, b, out), K.ring3d(0, 0, s - b, out), K.ring3d(0, 0, s, inn)]
    body = K.loft(rings, "trim", smooth=False)
    pan = K.Mesh()
    for k in range(4):
        p = panel(0, -s / 2 - 0.02, s * 0.18, s * 0.64, s * 0.64, 0.06, "wall_alt", "trim")
        pan.merge(p.rotate_z(k * math.pi / 2))
    return finalize([Node("block", body), Node("relief", pan)],
                    grid_meta("free", None, [sock("pushable", (0, 0, 0), "up", cell_m=s)], motif=P["motif"]))


# ---------------------------------------------------------------- dprop.statue
@register("dprop.statue", V, "furniture_large", {
    "pose": S.enum("sword", ["sword", "shield"]), "plinth": S.num(0.6, 0.3, 1.0),
}, "Hooded guardian statue (original design): robed stone figure on a dressed plinth, hands resting on a sword set "
   "point-down (or holding a round shield), faceless dark hood.", origin="floor_center")
def statue(P, seed):
    ph = P["plinth"]
    m = K.Mesh()
    m.merge(D.taper_loft(0, 0, [0.0, ph - 0.12, ph], [(0.55, 0.45), (0.5, 0.4), (0.55, 0.45)], "trim", bevel=0.05))
    robe = K.lathe([(0.0, ph), (0.42, ph), (0.38, ph + 0.5), (0.3, ph + 1.1), (0.27, ph + 1.45), (0.33, ph + 1.62), (0.24, ph + 1.78),
                    (0.0, ph + 1.8)], 8, "stone", smooth=True, ry=0.78)
    m.merge(robe)
    hood = K.lathe([(0.0, ph + 1.6), (0.2, ph + 1.62), (0.24, ph + 1.85), (0.17, ph + 2.08), (0.0, ph + 2.18)], 7, "stone", smooth=True)
    m.merge(hood)
    face = K.sphere(0, -0.13, ph + 1.88, 0.13, 0.07, 0.14, 6, 4, "opening", smooth=True)
    nodes = [Node("figure", m), Node("face", face)]
    arms = K.Mesh()
    if P["pose"] == "sword":
        for sx in (-1, 1):
            arms.merge(K.tube([(sx * 0.3, -0.02, ph + 1.55), (sx * 0.24, -0.22, ph + 1.2), (sx * 0.07, -0.34, ph + 1.08)], 0.075, 5, "stone"))
        sw = K.Mesh()
        sw.merge(K.box(0, -0.38, ph + 0.55, 0.1, 0.035, 1.0, "metal"))
        sw.merge(K.box(0, -0.38, ph + 1.07, 0.42, 0.07, 0.07, "metal"))
        sw.merge(K.box(0, -0.38, ph + 1.2, 0.06, 0.06, 0.22, "metal"))
        sw.merge(K.sphere(0, -0.38, ph + 1.34, 0.06, 0.06, 0.06, 5, 3, "metal"))
        nodes.append(Node("sword", sw))
    else:
        for sx in (-1, 1):
            arms.merge(K.tube([(sx * 0.3, -0.02, ph + 1.55), (sx * 0.3, -0.18, ph + 1.25), (sx * 0.12, -0.3, ph + 1.15)], 0.075, 5, "stone"))
        sh = K.cylinder(0, 0, -0.04, 0.42, 0.08, 10, "metal", smooth=False).rotate_x(math.pi / 2).translate(0, -0.42, ph + 1.05)
        boss = K.sphere(0, -0.47, ph + 1.05, 0.1, 0.06, 0.1, 6, 3, "trim")
        nodes.append(Node("shield", sh.merge(boss)))
    nodes.append(Node("arms", arms))
    return finalize(nodes, grid_meta("free", None, [sock("prop", (0, 0, 0), "up", front="s")], pose=P["pose"]))


# ---------------------------------------------------------------- dprop.banner
@register("dprop.banner", V, "soft", {
    "length": S.num(2.2, 1.2, 2.8), "tail": S.enum("swallow", ["swallow", "point", "straight"]),
}, "Hanging cloth banner on an iron rod with finials: painted heraldic cloth (original emblem), swallow-tail, point "
   "or straight hem. Origin on the wall face at floor level, top at 4.0 m.", wall_mounted=True, origin="opening")
def banner(P, seed):
    top, L, w = 4.0, P["length"], 1.0
    y = -0.06
    rod = K.cylinder(0, 0, -w / 2 - 0.12, 0.03, w + 0.24, 6, "metal").rotate_y(math.pi / 2).translate(0, y - 0.02, top + 0.04)
    fin = K.Mesh()
    for sx in (-1, 1):
        fin.merge(K.sphere(sx * (w / 2 + 0.14), y - 0.02, top + 0.04, 0.055, 0.055, 0.055, 6, 3, "metal"))
        fin.merge(K.box(sx * (w / 2 + 0.02), -0.03, top + 0.04, 0.04, 0.06, 0.04, "metal"))
    b = top - L
    if P["tail"] == "swallow":
        pts = [(-w / 2, b), (0.0, b + 0.35), (w / 2, b), (w / 2, top), (-w / 2, top)]
    elif P["tail"] == "point":
        pts = [(-w / 2, b + 0.3), (0.0, b), (w / 2, b + 0.3), (w / 2, top), (-w / 2, top)]
    else:
        pts = [(-w / 2, b), (w / 2, b), (w / 2, top), (-w / 2, top)]
    cloth = K.Mesh()
    halves = [pts] if P["tail"] == "straight" else [[pts[0], pts[1], (0.0, top), pts[4]], [pts[1], pts[2], pts[3], (0.0, top)]]
    for poly in halves:                    # convex pieces (the swallow / point hem is concave as one polygon)
        cloth.add([(x, y, z) for x, z in poly], [tuple(range(len(poly)))], "fabric", False,
                  [("n", [((x + w / 2) / w, (z - b) / L) for x, z in poly])])
    cloth = D.weld_mesh(cloth)
    return Asset([Node("rod", rod.merge(fin)), Node("cloth", cloth, "card")],
                 grid_meta("wall_face", None, [sock("mount", (0, 0, 0), "s", fits="wall")], tail=P["tail"]))


# ---------------------------------------------------------------- dprop.cobweb
@register("dprop.cobweb", V, "prop", {
    "size": S.num(1.1, 0.5, 1.5),
}, "Corner cobweb: one alpha card spanning the inner corner of two walls under the cornice (painted radial web). "
   "Origin on the corner line at floor level; the card faces the room diagonal.", origin="opening")
def cobweb(P, seed):
    s = P["size"]
    zc = D.H - 0.55
    # one planar triangle in the inner corner (+X/+Y walls meet at the origin line; the room is toward -X/-Y)
    t = (-0.04, -0.04, zc)
    a = (-s * 0.8, -0.0, zc - s * 0.45)
    b = (-0.0, -s * 0.8, zc - s * 0.45)
    card = K.Mesh().add([t, a, b], [(0, 1, 2)], "particle", False, [("n", [(0.0, 1.0), (1.0, 1.0), (0.0, 0.0)])])
    n = np.cross(np.subtract(a, t), np.subtract(b, t))
    if n[0] + n[1] > 0:
        card.flip()
    return Asset([Node("web", card, "card")], grid_meta("corner", None, [sock("corner", (0, 0, 0), "up")]))


# ---------------------------------------------------------------- dprop.tablet
@register("dprop.tablet", V, "furniture", {
    "height": S.num(1.6, 1.0, 2.2),
}, "Rune tablet: rounded-top standing stone on a stepped base with a recessed panel of softly glowing original glyphs "
   "(emissive, period-correct, no text).", origin="floor_center")
def tablet(P, seed):
    h = P["height"]
    w, t = 0.9, 0.24
    o = [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h - w / 2)]
    for i in range(1, 6):
        a = math.pi * i / 6
        o.append((w / 2 * math.cos(a), h - w / 2 + w / 2 * math.sin(a) * 0.8))
    o.append((-w / 2, h - w / 2))
    slab = K.prism(o, -t / 2, t / 2, "trim").rotate_x(math.pi / 2).translate(0, 0, 0.25)
    base = D.bevel_box(0, 0, 0, w + 0.3, t + 0.3, 0.25, "stone", bevel=0.04)
    glyph = panel(0, -t / 2 - 0.005, 0.25 + h * 0.18, w * 0.7, h * 0.58, 0.02, "screen", "trim")
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up", interact="read")])
    meta["emitter"] = {"offset_gltf": [0, round(0.25 + h * 0.45, 3), 0.3], "radius_m": 2.0, "warm": False}
    return finalize([Node("slab", slab.merge(base)), Node("glyphs", glyph)], meta)


# ---------------------------------------------------------------- dprop.crystal
@register("dprop.crystal", V, "furniture", {
    "count": S.integer(5, 3, 7), "height": S.num(1.1, 0.5, 1.8),
}, "Crystal cluster: hexagonal pointed prisms of painted glass leaning out of a rock seat; glows faintly.",
   origin="floor_center")
def crystal(P, seed):
    r = rng(seed, "dprop.crystal")
    seat = D.rock_blob(0, 0, 0.1, 0.45, 0.4, 0.18, r, "rock", segs=7, rings=3)
    cr = K.Mesh()
    for k in range(P["count"]):
        hh = P["height"] * (1.0 if k == 0 else r.uniform(0.4, 0.75))
        rad = 0.11 if k == 0 else r.uniform(0.05, 0.09)
        prof = [(0.0, 0.0), (rad, 0.0), (rad, hh * 0.78), (0.0, hh)]
        c = K.lathe(prof, 6, "glass", smooth=False)
        if k:
            a = 2 * math.pi * k / (P["count"] - 1) + r.uniform(-0.3, 0.3)
            c.rotate_y(r.uniform(0.35, 0.7)).rotate_z(a).translate(0.12 * math.cos(a), 0.12 * math.sin(a), 0.12)
        else:
            c.translate(0, 0, 0.1)
        cr.merge(c)
    meta = grid_meta("free", None, [sock("prop", (0, 0, 0), "up")])
    meta["emitter"] = {"offset_gltf": [0, round(P["height"] * 0.6, 3), 0], "radius_m": 3.0, "warm": False}
    return finalize([Node("seat", seat), Node("crystals", cr)], meta)
