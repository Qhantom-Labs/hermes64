"""MEDIEVALKIT dressing props (mprop.*), theme-agnostic: barrels, crates, carts, anvils, hay, tables and benches,
chests (state pair), weapon racks, signposts with BLANK sign frames (paper role, never text), lanterns, sacks,
buckets, cauldrons, woodpiles, grindstones, baskets, shields, beds, shelves, tableware, candles, troughs.

Free props are footprint-centred and grounded (front toward -Y = glTF +Z); wall props use the wall-face anchor.
Lit props carry meta bake_lights (point_bake pools on their own vertices) like the halls.
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import register
from . import gen_medievalkit_core as M
from .gen_medievalkit_village import V
from .rng import rng


def solids(m):
    return [M.solid(k, v) for k, v in m.items() if v.f]


def disc_x(x, y, z, r, w, role, segs=8, hub=None):
    """Wheel / disc with its axis along X (closed lathe turned on its side)."""
    prof = [(0.0, -w / 2), (r, -w / 2), (r, w / 2), (0.0, w / 2)]
    d = K.lathe(prof, segs, role, smooth=False, start=math.pi / segs)
    d.apply(lambda a: a[:, [2, 1, 0]])
    d.orient_outward()
    return d.translate(x, y, z)


def log_x(x0, x1, y, z, r, role="bark", segs=5, end_role="body"):
    """Log lying along X: bark sides, sawn end caps (cap_roles)."""
    L = x1 - x0
    lg = K.lathe([(0.0, 0.0), (r, 0.0), (r * 0.94, L), (0.0, L)], segs, role, smooth=True, roles=[end_role, role, end_role])
    lg.apply(lambda a: np.stack([a[:, 2], a[:, 1], a[:, 0]], 1))
    lg.orient_outward()
    return lg.translate(x0, y, z)


# ---------------------------------------------------------------- barrels, crates, sacks, buckets, baskets
@register("mprop.barrel", V, "prop", {
    "kind": S.enum("upright", ["upright", "lying", "keg", "water"]),
}, "Oak barrel with two iron hoops: upright, lying on its side, a small keg, or an open water butt.", origin="floor_center")
def barrel(P, seed):
    k = P["kind"]
    h, r0, r1 = {"keg": (0.62, 0.24, 0.29), "water": (0.95, 0.36, 0.41)}.get(k, (1.0, 0.33, 0.39))
    m = {"staves": K.Mesh(), "hoops": K.Mesh(), "water": K.Mesh()}
    top_z = h - (0.06 if k == "water" else 0.0)
    m["staves"].merge(K.lathe([(0.0, 0.0), (r0, 0.0), (r1, h / 2), (r0, h), (0.0, top_z)], 8, "body", smooth=True,
                              roles=["body_alt", "body", "body", "body_alt"]))
    for z in (0.16 * h, 0.84 * h):
        rr = r0 + (r1 - r0) * (1.0 - abs(z - h / 2) / (h / 2)) + 0.014
        m["hoops"].merge(K.lathe([(rr, z - 0.035), (rr, z + 0.035)], 8, "metal", smooth=True, cap_roles=("metal", "metal")))
    if k == "water":
        m["water"].merge(K.lathe([(0.0, 0.0), (r0 - 0.03, 0.0), (r0 - 0.03, 0.02), (0.0, 0.02)], 8, "water", smooth=False).translate(0.0, 0.0, h - 0.1))
    if k == "lying":
        for mm in m.values():
            mm.rotate_x(math.pi / 2)
    return M.centred(solids(m), {"kind": k})


@register("mprop.crate", V, "prop", {
    "kind": S.enum("braced", ["braced", "slatted", "small"]),
}, "Plank crate with corner battens and a diagonal brace (braced), an open-slatted produce crate, or a small box.",
   origin="floor_center")
def crate(P, seed):
    k = P["kind"]
    s = {"small": 0.5, "slatted": 0.75}.get(k, 0.9)
    hz = s * (0.6 if k == "slatted" else 1.0)
    m = {"box": K.Mesh(), "battens": K.Mesh()}
    m["box"].merge(M.chamfer_box(0.0, 0.0, 0.0, s, s * (0.7 if k == "slatted" else 1.0), hz, "body", bevel=0.03))
    sy = s * (0.7 if k == "slatted" else 1.0)
    for sx in (-1, 1):
        for syy in (-1, 1):
            m["battens"].merge(K.box(sx * (s / 2 - 0.035), syy * (sy / 2 - 0.035), hz / 2, 0.09, 0.09, hz + 0.012, "frame"))
    if k == "braced":
        for syy in (-1, 1):
            m["battens"].merge(M.beam((-s / 2 + 0.08, syy * (sy / 2 + 0.005), 0.08), (s / 2 - 0.08, syy * (sy / 2 + 0.005), hz - 0.08), 0.08, 0.025,
                                      "frame", out=(0.0, syy, 0.0), bevel=0.0, embed=0.0))
    elif k == "slatted":
        for z in (hz * 0.33, hz * 0.66):
            for syy in (-1, 1):
                m["battens"].merge(K.box(0.0, syy * (sy / 2 + 0.008), z, s - 0.2, 0.02, 0.06, "opening"))
    return M.centred(solids(m), {"kind": k})


@register("mprop.sack", V, "prop", {
    "kind": S.enum("single", ["single", "pile", "open"]),
}, "Tied burlap sack (pale cloth), a pile of three, or an open sack of grain.", origin="floor_center")
def sack(P, seed):
    k = P["kind"]
    m = {"sacks": K.Mesh(), "ties": K.Mesh()}
    spots = {"single": [(0.0, 0.0, 0.0, 0.0)], "pile": [(-0.3, 0.0, 0.0, 0.3), (0.3, 0.05, 0.0, -0.2), (0.0, 0.0, 0.42, 1.2)],
             "open": [(0.0, 0.0, 0.0, 0.0)]}[k]
    for i, (x, y, z, yaw) in enumerate(spots):
        body = K.lathe([(0.0, 0.0), (0.27, 0.03), (0.3, 0.25), (0.2, 0.5), (0.09, 0.6), (0.0, 0.62)], 5 if k == "pile" else 6, "paper", smooth=True)
        if k == "pile" and i < 2:
            body.rotate_x(math.pi / 2 - 0.15).translate(0.0, 0.25, 0.28)
        if k == "open":
            body = K.lathe([(0.0, 0.0), (0.27, 0.03), (0.32, 0.3), (0.3, 0.52), (0.0, 0.46)], 6, "paper", smooth=True,
                           roles=["paper", "paper", "paper", "fur"])
        m["sacks"].merge(body.rotate_z(yaw).translate(x, y, z))
        if k != "open" and not (k == "pile" and i < 2):
            m["ties"].merge(K.lathe([(0.095, 0.0), (0.095, 0.05)], 6, "rope", smooth=True, cap_roles=("rope", "rope")).translate(x, y, z + 0.5))
    return M.centred(solids(m), {"kind": k})


@register("mprop.bucket", V, "prop", {
    "water": S.boolean(True),
}, "Wooden pail with two iron bands and a rope handle, optionally full of water.", origin="floor_center")
def bucket(P, seed):
    m = {"pail": K.Mesh(), "iron": K.Mesh(), "water": K.Mesh()}
    m["pail"].merge(K.lathe([(0.0, 0.0), (0.16, 0.0), (0.2, 0.36), (0.0, 0.31)], 7, "body", smooth=True, roles=["body_alt", "body", "body_alt"]))
    for z in (0.06, 0.3):
        r = 0.16 + 0.04 * z / 0.36 + 0.01
        m["iron"].merge(K.lathe([(r, z - 0.02), (r, z + 0.02)], 7, "metal", smooth=True, cap_roles=("metal", "metal")))
    m["iron"].merge(M.beam((-0.19, 0.0, 0.34), (0.0, 0.0, 0.52), 0.02, 0.02, "rope", out=(0.0, 1.0, 0.0), bevel=0.0, embed=0.0))
    m["iron"].merge(M.beam((0.0, 0.0, 0.52), (0.19, 0.0, 0.34), 0.021, 0.021, "rope", out=(0.0, 1.0, 0.0), bevel=0.0, embed=0.0))
    if P["water"]:
        m["water"].merge(K.lathe([(0.0, 0.0), (0.17, 0.0), (0.17, 0.015), (0.0, 0.015)], 7, "water", smooth=False).translate(0.0, 0.0, 0.29))
    return M.centred(solids(m), {})


@register("mprop.basket", V, "prop", {
    "goods": S.enum("apples", ["apples", "bread", "wool", "empty"]),
}, "Woven wicker basket (wattle role) with apples, loaves or wool, or empty.", origin="floor_center")
def basket(P, seed):
    g = P["goods"]
    m = {"basket": K.Mesh(), "goods": K.Mesh()}
    m["basket"].merge(K.lathe([(0.0, 0.0), (0.2, 0.0), (0.28, 0.28), (0.25, 0.3), (0.0, 0.22)], 7, "rail", smooth=True,
                              roles=["rail", "rail", "rail", "body_alt"]))
    if g != "empty":
        role, rz = {"apples": ("flower", 0.1), "bread": ("fur", 0.08), "wool": ("paper", 0.12)}[g]
        m["goods"].merge(M.blob(0.0, 0.0, 0.25, 0.22, 0.22, rz, role, seed, segs=6, rings=3, lump=0.25))
    return M.centred(solids(m), {"goods": g})


# ---------------------------------------------------------------- hay, woodpile
@register("mprop.hay", V, "furniture", {
    "kind": S.enum("bale", ["bale", "stack", "rick"]),
}, "Straw: a tied bale, a stack of three bales, or a domed hay rick on a timber base.", origin="floor_center")
def hay(P, seed):
    k = P["kind"]
    m = {"hay": K.Mesh(), "ties": K.Mesh()}
    if k == "rick":
        m["hay"].merge(K.lathe([(0.0, 0.0), (1.1, 0.0), (1.25, 0.9), (1.0, 1.7), (0.45, 2.3), (0.0, 2.45)], 8, "fur", smooth=True))
        m["ties"].merge(M.post(0.0, 0.0, 2.3, 2.8, 0.05, 0.03, "wood", sides=5))
        M.jitter(m["hay"], seed + 2, 0.06, keep_z0=True)
    else:
        spots = [(0.0, 0.0, 0.0, 0.0)] if k == "bale" else [(-0.42, 0.0, 0.0, 0.05), (0.42, 0.02, 0.0, -0.04), (0.0, 0.0, 0.5, 0.5)]
        for x, y, z, yaw in spots:
            b = M.chamfer_box(0.0, 0.0, 0.0, 0.8, 0.5, 0.48, "fur", bevel=0.07, base_bevel=0.04)
            M.jitter(b, seed + int(10 * (x + 1)), 0.02, keep_z0=True)
            m["hay"].merge(b.rotate_z(yaw).translate(x, y, z))
            for t in (-0.2, 0.2):
                tie = K.box(t, 0.0, 0.24, 0.035, 0.53, 0.5, "rope")
                m["ties"].merge(tie.rotate_z(yaw).translate(x, y, z))
    return M.centred(solids(m), {"kind": k})


@register("mprop.woodpile", V, "furniture", {
    "kind": S.enum("stack", ["stack", "block"]),
}, "Firewood: a stacked log pile against two stakes, or a chopping block with split logs and an axe.", origin="floor_center")
def woodpile(P, seed):
    m = {"logs": K.Mesh(), "stakes": K.Mesh(), "axe": K.Mesh()}
    r = rng(seed, "mprop.woodpile")
    if P["kind"] == "stack":
        rows = [(0.0, 4), (0.21, 3), (0.42, 3), (0.62, 2)]
        for j, (z, n) in enumerate(rows):
            for i in range(n):
                y = -0.45 + (i + 0.5) * 0.9 / n + (0.1 if j % 2 else 0.0) - 0.05
                m["logs"].merge(log_x(-0.6 + 0.04 * r.random(), 0.6 - 0.04 * r.random(), y, z + 0.11, 0.1 + 0.01 * (i % 2)))
        for sx in (-1, 1):
            m["stakes"].merge(M.post(sx * 0.72, 0.0, 0.0, 1.0, 0.05, 0.035, "post", sides=5))
    else:
        m["logs"].merge(K.lathe([(0.0, 0.0), (0.3, 0.0), (0.28, 0.5), (0.0, 0.5)], 7, "bark", smooth=True, roles=["body", "bark", "body"]))
        for i in range(3):
            a = 0.6 + i * 2.0
            lg = log_x(0.0, 0.42, 0.0, 0.0, 0.08, segs=4)
            m["logs"].merge(lg.rotate_z(a).translate(0.5 * math.cos(a + 0.4), 0.5 * math.sin(a + 0.4), 0.08))
        m["axe"].merge(M.beam((0.05, 0.0, 0.48), (0.25, 0.25, 0.95), 0.04, 0.04, "wood", out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
        m["axe"].merge(M.chamfer_box(0.0, 0.0, 0.44, 0.22, 0.04, 0.14, "metal", bevel=0.01).rotate_z(math.pi / 4).translate(0.04, -0.02, 0.0))
    return M.centred(solids(m), {"kind": P["kind"]})


# ---------------------------------------------------------------- cart, anvil, grindstone, cauldron, trough
@register("mprop.cart", V, "vehicle", {
    "load": S.enum("hay", ["hay", "barrels", "sacks", "empty"]),
}, "Two-wheeled farm cart: plank bed with side boards, spoked-look wheels, shafts resting on the ground, loaded with "
   "hay, barrels or sacks, or empty.", origin="floor_center")
def cart(P, seed):
    m = {"bed": K.Mesh(), "wheels": K.Mesh(), "load": K.Mesh()}
    zb = 0.75
    m["bed"].merge(M.chamfer_box(0.0, 0.0, zb, 1.5, 2.2, 0.1, "body", bevel=0.02))
    for sx in (-1, 1):
        m["bed"].merge(M.chamfer_box(sx * 0.72, 0.0, zb + 0.08, 0.08, 2.2, 0.38, "body", bevel=0.02))
        m["wheels"].merge(disc_x(sx * 0.9, 0.1, 0.62, 0.62, 0.09, "body_alt", segs=10))
        m["wheels"].merge(disc_x(sx * 0.96, 0.1, 0.62, 0.14, 0.12, "metal", segs=6))
        m["bed"].merge(M.beam((sx * 0.5, -1.0, zb + 0.02), (sx * 0.38, -2.6, 0.06), 0.09, 0.09, "frame", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    m["bed"].merge(M.beam((-0.95, 0.1, 0.62), (0.95, 0.1, 0.62), 0.1, 0.1, "frame", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    m["bed"].merge(M.chamfer_box(0.0, 1.05, zb + 0.08, 1.36, 0.08, 0.32, "body", bevel=0.02))
    ld = P["load"]
    if ld == "hay":
        m["load"].merge(M.blob(0.0, 0.05, zb + 0.35, 0.68, 1.0, 0.45, "fur", seed, segs=7, rings=4, lump=0.18))
    elif ld == "barrels":
        for y in (-0.5, 0.45):
            m["load"].merge(K.lathe([(0.0, 0.0), (0.28, 0.0), (0.33, 0.4), (0.28, 0.8), (0.0, 0.8)], 7, "body", smooth=True,
                                    roles=["body_alt", "body", "body", "body_alt"]).translate(0.0, y, zb + 0.1))
    elif ld == "sacks":
        for i, (x, y) in enumerate(((-0.3, -0.5), (0.3, -0.4), (-0.25, 0.45), (0.3, 0.5))):
            m["load"].merge(M.blob(x, y, zb + 0.28, 0.3, 0.38, 0.2, "paper", seed + i, segs=6, rings=3, lump=0.15))
    return M.centred(solids(m), {"load": ld})


@register("mprop.anvil", V, "prop", {
    "tools": S.boolean(True, "tongs and a hammer resting on the anvil"),
}, "Blacksmith's anvil with a horn and heel on an oak stump, optionally with tongs and hammer.", origin="floor_center")
def anvil(P, seed):
    m = {"anvil": K.Mesh(), "stump": K.Mesh(), "tools": K.Mesh()}
    m["stump"].merge(K.lathe([(0.0, 0.0), (0.3, 0.0), (0.26, 0.5), (0.0, 0.5)], 7, "bark", smooth=True, roles=["body", "bark", "body"]))
    side = [(-0.32, 0.0), (0.32, 0.0), (0.2, 0.06), (0.12, 0.16), (0.24, 0.22), (0.62, 0.28), (0.3, 0.36), (-0.32, 0.36), (-0.38, 0.3),
            (-0.2, 0.22), (-0.12, 0.16), (-0.2, 0.06)]
    body = M.slab_y([(x, z) for x, z in side], -0.12, 0.12, "metal")
    m["anvil"].merge(body.translate(0.0, 0.0, 0.5))
    if P["tools"]:
        m["tools"].merge(M.beam((-0.2, -0.04, 0.88), (0.25, 0.04, 0.88), 0.03, 0.03, "metal", out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
        m["tools"].merge(M.beam((-0.25, 0.25, 0.53), (0.15, 0.32, 0.53), 0.035, 0.035, "wood", out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
        m["tools"].merge(M.chamfer_box(0.18, 0.32, 0.5, 0.1, 0.16, 0.08, "metal", bevel=0.01))
    return M.centred(solids(m), {})


@register("mprop.grindstone", V, "furniture", {}, "Treadle grindstone: a sandstone wheel on an oak frame with a crank and "
                                                 "a water trough.", origin="floor_center")
def grindstone(P, seed):
    m = {"frame": K.Mesh(), "wheel": K.Mesh(), "trough": K.Mesh()}
    for sy in (-1, 1):
        for sx in (-1, 1):
            m["frame"].merge(M.beam((sx * 0.45, sy * 0.25, 0.0), (sx * 0.18, sy * 0.15, 0.82), 0.08, 0.08, "frame", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    m["frame"].merge(M.beam((-0.42, 0.0, 0.82), (0.42, 0.0, 0.82), 0.1, 0.4, "frame", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    m["wheel"].merge(disc_x(0.0, 0.0, 1.05, 0.42, 0.14, "trim", segs=10))
    m["wheel"].merge(M.beam((0.0, 0.0, 1.05), (0.42, 0.0, 1.05), 0.04, 0.04, "metal", out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
    m["wheel"].merge(M.beam((0.42, 0.0, 1.05), (0.44, 0.0, 0.8), 0.035, 0.035, "metal", out=(0.0, 1.0, 0.0), bevel=0.0, embed=0.0))
    m["trough"].merge(M.chamfer_box(0.0, 0.0, 0.58, 0.5, 0.3, 0.2, "body", bevel=0.02))
    return M.centred(solids(m), {})


@register("mprop.cauldron", V, "furniture", {
    "fire": S.boolean(True),
}, "Iron cauldron hung from a tripod over a ring of stones, with a glowing fire (baked warm pool).", origin="floor_center")
def cauldron(P, seed):
    m = {"pot": K.Mesh(), "tripod": K.Mesh(), "stones": K.Mesh(), "fire": K.Mesh()}
    m["pot"].merge(K.lathe([(0.0, 0.0), (0.24, 0.04), (0.34, 0.24), (0.3, 0.46), (0.33, 0.5), (0.0, 0.44)], 8, "metal", smooth=True).translate(0.0, 0.0, 0.42))
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.3
        m["tripod"].merge(M.beam((0.85 * math.cos(a), 0.85 * math.sin(a), 0.0), (0.0, 0.0, 1.75), 0.06, 0.06, "wood",
                                 out=(-math.sin(a), math.cos(a), 0.0), bevel=0.1, embed=0.0))
    m["tripod"].merge(M.beam((0.0, 0.0, 1.7), (0.0, 0.0, 0.95), 0.025, 0.025, "metal", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    for k in range(7):
        a = 2 * math.pi * k / 7
        m["stones"].merge(M.blob(0.55 * math.cos(a), 0.55 * math.sin(a), 0.0, 0.14, 0.12, 0.1, "rock", seed + k, segs=5, rings=3, lump=0.2))
    lights = []
    if P["fire"]:
        m["fire"].merge(K.lathe([(0.0, 0.0), (0.26, 0.0), (0.12, 0.3), (0.0, 0.42)], 5, "fire", smooth=False).translate(0.0, 0.0, 0.02))
        lights = [{"pos": [0.0, 0.0, 0.3], "radius": 2.4, "strength": 1.0}]
    return M.centred_lit(solids(m), {"fire": P["fire"]}, lights)


@register("mprop.trough", V, "furniture", {
    "kind": S.enum("water", ["water", "feed"]),
}, "Hollowed log / plank trough on two blocks, filled with water or hay.", origin="floor_center")
def trough(P, seed):
    m = {"trough": K.Mesh(), "fill": K.Mesh()}
    sec = [(-0.32, 0.25), (-0.26, 0.0), (0.26, 0.0), (0.32, 0.25), (0.25, 0.25), (0.2, 0.08), (-0.2, 0.08), (-0.25, 0.25)]
    t = K.prism(sec, -0.9, 0.9, "body")
    t.apply(lambda a: a[:, [2, 0, 1]])
    m["trough"].merge(M.swap_uv(t.orient_outward()).translate(0.0, 0.0, 0.22))
    for x in (-0.65, 0.65):
        m["trough"].merge(M.chamfer_box(x, 0.0, 0.0, 0.3, 0.6, 0.24, "wall_alt", bevel=0.03))
    role = "water" if P["kind"] == "water" else "fur"
    m["fill"].merge(K.box(0.0, 0.0, 0.42, 1.76, 0.42, 0.04, role))
    return M.centred(solids(m), {"kind": P["kind"]})


# ---------------------------------------------------------------- furniture: tables, benches, beds, shelves, chests
@register("mprop.table", V, "furniture", {
    "kind": S.enum("trestle", ["trestle", "round", "feast"]),
}, "Tavern / hall table: a trestle table, a round table on a post and feet, or a long feast table.", origin="floor_center")
def table(P, seed):
    k = P["kind"]
    m = {"top": K.Mesh(), "legs": K.Mesh()}
    if k == "round":
        m["top"].merge(K.lathe([(0.0, 0.74), (0.62, 0.74), (0.62, 0.8), (0.0, 0.8)], 10, "body", smooth=False, start=math.pi / 10))
        m["legs"].merge(K.lathe([(0.1, 0.0), (0.08, 0.72)], 6, "body_alt", smooth=True, cap_roles=("body_alt", "body_alt")))
        for a in (0.0, 2.1, 4.2):
            m["legs"].merge(M.beam((0.0, 0.0, 0.05), (0.4 * math.cos(a), 0.4 * math.sin(a), 0.03), 0.08, 0.08, "body_alt", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    else:
        L = 1.8 if k == "trestle" else 3.6
        m["top"].merge(M.chamfer_box(0.0, 0.0, 0.72, L, 0.85, 0.08, "body", bevel=0.02))
        xs = (-L / 2 + 0.3, L / 2 - 0.3) if k == "trestle" else (-L / 2 + 0.3, 0.0, L / 2 - 0.3)
        for x in xs:
            tr = K.prism([(-0.36, 0.0), (0.36, 0.0), (0.08, 0.72), (-0.08, 0.72)], x - 0.05, x + 0.05, "body_alt")
            tr.apply(lambda a: a[:, [2, 0, 1]])
            m["legs"].merge(tr.orient_outward())
        m["legs"].merge(M.beam((xs[0], 0.0, 0.3), (xs[-1], 0.0, 0.3), 0.08, 0.08, "body_alt", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    return M.centred(solids(m), {"kind": k})


@register("mprop.bench", V, "furniture", {
    "kind": S.enum("bench", ["bench", "stool", "settle"]),
}, "Seating: a plank bench, a three-legged stool, or a high-backed settle.", origin="floor_center")
def bench(P, seed):
    k = P["kind"]
    m = {"seat": K.Mesh(), "legs": K.Mesh()}
    if k == "stool":
        m["seat"].merge(K.lathe([(0.0, 0.42), (0.18, 0.42), (0.18, 0.48), (0.0, 0.48)], 7, "body", smooth=False))
        for a in (0.3, 2.4, 4.5):
            m["legs"].merge(M.beam((0.2 * math.cos(a), 0.2 * math.sin(a), 0.0), (0.09 * math.cos(a), 0.09 * math.sin(a), 0.43), 0.045, 0.045, "body_alt",
                                   out=(0.0, 0.0, 1.0), bevel=0.0, embed=0.0))
    else:
        L = 1.6
        m["seat"].merge(M.chamfer_box(0.0, 0.0, 0.42, L, 0.34, 0.06, "body", bevel=0.015))
        for x in (-L / 2 + 0.2, L / 2 - 0.2):
            leg = K.prism([(-0.15, 0.0), (0.15, 0.0), (0.1, 0.42), (-0.1, 0.42)], x - 0.03, x + 0.03, "body_alt")
            leg.apply(lambda a: a[:, [2, 0, 1]])
            m["legs"].merge(leg.orient_outward())
        if k == "settle":
            m["seat"].merge(M.chamfer_box(0.0, 0.2, 0.0, L + 0.08, 0.07, 1.35, "body_alt", bevel=0.02))
            for sx in (-1, 1):
                arm = K.prism([(-0.18, 0.0), (0.22, 0.0), (0.22, 0.72), (-0.18, 0.78)], -0.03, 0.03, "body_alt")
                arm.apply(lambda a: np.stack([a[:, 2], a[:, 0], a[:, 1]], 1))
                m["legs"].merge(arm.orient_outward().translate(sx * (L / 2 + 0.06), 0.0, 0.0))
    return M.centred(solids(m), {"kind": k})


@register("mprop.chest", V, "prop", {
    "state": S.enum("closed", ["closed", "open"], "state pair: closed <-> open"),
    "kind": S.enum("iron", ["iron", "plain"]),
}, "Treasure / travel chest: oak body with a rounded lid, iron straps and a lock plate (iron) or plain boards; the "
   "lid shut or thrown open (a state pair for module flags).", origin="floor_center")
def chest(P, seed):
    m = {"body": K.Mesh(), "lid": K.Mesh(), "iron": K.Mesh(), "inside": K.Mesh()}
    w, d, h = 0.9, 0.55, 0.45
    m["body"].merge(M.chamfer_box(0.0, 0.0, 0.0, w, d, h, "body", bevel=0.02, base_bevel=0.02))
    arc = [(-d / 2 + d * i / 6, h + 0.2 * math.sin(math.pi * i / 6)) for i in range(7)]
    sec = [(-d / 2, h)] + [(y, z) for y, z in arc[1:-1]] + [(d / 2, h)]
    lid = K.prism([(y, z) for y, z in sec], -w / 2, w / 2, "body")
    lid.apply(lambda a: a[:, [2, 0, 1]])
    lid = M.swap_uv(lid.orient_outward())
    straps = K.Mesh()
    if P["kind"] == "iron":
        for x in (-0.28, 0.28):
            straps.merge(K.box(x, -d / 2 - 0.006, h / 2, 0.06, 0.02, h - 0.04, "metal"))
            s2 = K.prism([(y, z + 0.012) for y, z in sec], x - 0.03, x + 0.03, "metal")
            s2.apply(lambda a: a[:, [2, 0, 1]])
            straps.merge(s2.orient_outward().translate(0.0, 0.0, 0.0))
        m["iron"].merge(K.box(0.0, -d / 2 - 0.012, h - 0.06, 0.12, 0.03, 0.14, "metal"))
    if P["state"] == "open":
        hinge = (0.0, d / 2, h)
        for mm in (lid, straps):
            if mm.f:
                mm.translate(0.0, -hinge[1], -hinge[2]).rotate_x(math.radians(-105.0)).translate(0.0, hinge[1], hinge[2])
        m["inside"].merge(K.box(0.0, 0.0, h - 0.06, w - 0.1, d - 0.1, 0.05, "chrome"))
    m["lid"].merge(lid)
    m["iron"].merge(straps)
    meta = {"state": P["state"], "pair": "mprop.chest__open" if P["state"] == "closed" else "mprop.chest"}
    return M.centred(solids(m), meta)


@register("mprop.bed", V, "furniture_large", {
    "kind": S.enum("cot", ["cot", "fourposter"]),
}, "Bed: a plank cot with a straw mattress, blanket and pillow, or a four-poster with a cloth tester.", origin="floor_center")
def bed(P, seed):
    m = {"frame": K.Mesh(), "bedding": K.Mesh()}
    L, w = 2.1, 1.1 if P["kind"] == "cot" else 1.5
    m["frame"].merge(M.chamfer_box(0.0, 0.0, 0.18, w, L, 0.22, "body", bevel=0.02))
    m["frame"].merge(M.chamfer_box(0.0, L / 2 - 0.04, 0.0, w + 0.06, 0.08, 0.95, "body_alt", bevel=0.02))
    for sx in (-1, 1):
        for sy in (-1, 1):
            m["frame"].merge(K.box(sx * (w / 2 - 0.04), sy * (L / 2 - 0.1), 0.1, 0.08, 0.08, 0.2, "body_alt"))
    m["bedding"].merge(M.chamfer_box(0.0, 0.0, 0.4, w - 0.1, L - 0.2, 0.14, "fur" if P["kind"] == "cot" else "paper", bevel=0.05))
    m["bedding"].merge(M.chamfer_box(0.0, -0.25, 0.52, w - 0.04, L - 0.7, 0.06, "quilt" if P["kind"] == "fourposter" else "knit", bevel=0.03))
    m["bedding"].merge(M.blob(0.0, L / 2 - 0.35, 0.6, w * 0.32, 0.18, 0.08, "paper", seed, segs=6, rings=3, lump=0.05))
    if P["kind"] == "fourposter":
        for sx in (-1, 1):
            for sy in (-1, 1):
                m["frame"].merge(M.post(sx * (w / 2 + 0.02), sy * (L / 2 + 0.0) - sy * 0.03, 0.0, 2.2, 0.05, 0.045, "body_alt", sides=6))
        m["bedding"].merge(M.chamfer_box(0.0, 0.0, 2.18, w + 0.2, L + 0.15, 0.16, "band", bevel=0.04))
    return M.centred(solids(m), {"kind": P["kind"]})


@register("mprop.shelf", V, "furniture", {
    "goods": S.enum("jugs", ["jugs", "books", "empty"]),
}, "Wall shelf (wall-face anchor, front +Z): two oak boards on brackets carrying jugs and bowls, or books.",
   origin="wall_face")
def shelf(P, seed):
    m = {"boards": K.Mesh(), "goods": K.Mesh()}
    r = rng(seed, "mprop.shelf")
    for z in (1.0, 1.6):
        m["boards"].merge(M.chamfer_box(0.0, -0.17, z, 1.4, 0.3, 0.05, "body", bevel=0.01))
        for x in (-0.55, 0.55):
            br = K.Mesh().add([(x - 0.025, -0.01, z - 0.25), (x + 0.025, -0.01, z - 0.25), (x + 0.025, -0.01, z - 0.004),
                               (x - 0.025, -0.01, z - 0.004), (x - 0.025, -0.28, z - 0.004), (x + 0.025, -0.28, z - 0.004)],
                              [(0, 1, 2, 3), (1, 5, 2), (0, 3, 4), (3, 2, 5, 4), (0, 4, 5, 1)], "body_alt", False)
            m["boards"].merge(br.orient_outward())
        if P["goods"] == "jugs":
            for i, x in enumerate((-0.35, 0.3) if z < 1.3 else (-0.15, 0.4)):
                hgt = 0.18 + 0.12 * r.random()
                m["goods"].merge(K.lathe([(0.0, 0.0), (0.07, 0.0), (0.09, hgt * 0.45), (0.045, hgt), (0.0, hgt)], 5,
                                         "hull_alt", smooth=True).translate(x, -0.17, z + 0.05))
        elif P["goods"] == "books":
            for i in range(6):
                x = -0.5 + i * 0.13
                m["goods"].merge(K.box(x, -0.17, z + 0.05 + 0.12, 0.1, 0.2, 0.24, "book"))
    return M.assemble(solids(m), {"goods": P["goods"]}, "wall_face", ground=False)


@register("mprop.weapon_rack", V, "furniture", {
    "kind": S.enum("spears", ["spears", "swords", "shields"]),
}, "Armoury rack: an oak frame holding spears, swords, or round shields with original heraldic charges.",
   origin="floor_center")
def weapon_rack(P, seed):
    k = P["kind"]
    m = {"frame": K.Mesh(), "arms": K.Mesh()}
    for x in (-0.7, 0.7):
        m["frame"].merge(M.post(x, 0.0, 0.0, 1.5, 0.05, 0.045, "frame", sides=4, start=math.pi / 4))
        m["frame"].merge(M.chamfer_box(x, 0.0, 0.0, 0.12, 0.5, 0.06, "frame", bevel=0.01))
    for z in (0.35, 1.25):
        m["frame"].merge(M.beam((-0.75, 0.0, z), (0.75, 0.0, z), 0.07, 0.07, "frame", out=(0.0, 0.0, 1.0), bevel=0.2, embed=0.0))
    if k == "spears":
        for i in range(4):
            x = -0.45 + i * 0.3
            m["arms"].merge(M.post(x, -0.06, 0.05, 1.85, 0.022, 0.02, "wood", sides=4))
            m["arms"].merge(K.lathe([(0.0, 0.0), (0.04, 0.05), (0.0, 0.26)], 4, "metal", smooth=False).translate(x, -0.06, 1.85))
    elif k == "swords":
        for i in range(4):
            x = -0.45 + i * 0.3
            m["arms"].merge(K.box(x, -0.06, 0.75, 0.05, 0.015, 0.9, "metal"))
            m["arms"].merge(K.box(x, -0.06, 1.23, 0.2, 0.04, 0.04, "metal"))
            m["arms"].merge(K.box(x, -0.06, 1.33, 0.035, 0.035, 0.16, "leather"))
    else:
        for i, x in enumerate((-0.35, 0.35)):
            sh = K.lathe([(0.0, 0.0), (0.3, 0.02), (0.3, 0.05), (0.0, 0.07)], 8, "band", smooth=False)
            u0, v0 = 0.5 * (i % 2), 0.5
            sh.uv = [("n", [(u0 + 0.25 + 0.25 * (p[0] / 0.31), v0 + 0.25 + 0.25 * (p[1] / 0.31)) for p in (sh.v[j] for j in f)]) for f in sh.f]
            sh.rotate_x(math.pi / 2)
            m["arms"].merge(sh.translate(x, -0.08, 0.85))
    return M.centred(solids(m), {"kind": k})


@register("mprop.shield", V, "prop", {
    "design": S.integer(1, 0, 3, "heraldry atlas quadrant: 0 chevron, 1 cross, 2 pale, 3 roundel"),
    "shape": S.enum("heater", ["heater", "round"]),
}, "Wall shield (wall-face anchor, front +Z): a heater or round shield carrying an original heraldic charge (band "
   "atlas), with a dark rim.", origin="wall_face")
def shield(P, seed):
    k = P["design"]
    u0, v0 = 0.5 * (k % 2), (0.5 if k < 2 else 0.0)
    if P["shape"] == "round":
        out = [(0.32 * math.cos(a), 1.6 + 0.32 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
    else:
        out = [(-0.3, 1.92), (0.3, 1.92), (0.29, 1.6), (0.2, 1.38), (0.0, 1.22), (-0.2, 1.38), (-0.29, 1.6)]
    s = M.slab_y(out, -0.08, -0.03, "band")
    zs = [z for _, z in out]
    z0, z1 = min(zs), max(zs)
    fn = M.bake.face_normals(np.asarray(s.v), s.f)
    s.uv = [("n", [(u0 + 0.5 * (p[0] + 0.32) / 0.64, v0 + 0.5 * (p[2] - z0) / (z1 - z0)) for p in (s.v[j] for j in f)]) if abs(n_[1]) > 0.9 else None
            for f, n_ in zip(s.f, fn)]
    s.r = ["band" if abs(n_[1]) > 0.9 else "metal" for n_ in fn]
    return M.assemble([M.solid("shield", s)], {"design": k}, "wall_face", ground=False)


@register("mprop.tableware", V, "prop", {
    "kind": S.enum("meal", ["meal", "drinks", "candles"]),
}, "Table dressing: a trencher with bread and a jug (meal), tankards round a pitcher (drinks), or a pair of lit "
   "candlesticks (baked warm pool).", origin="floor_center")
def tableware(P, seed):
    k = P["kind"]
    m = {"ware": K.Mesh(), "food": K.Mesh(), "flame": K.Mesh()}
    lights = []
    if k == "meal":
        m["ware"].merge(K.lathe([(0.0, 0.0), (0.18, 0.0), (0.2, 0.03), (0.0, 0.02)], 8, "body", smooth=False))
        m["food"].merge(M.blob(0.0, 0.0, 0.03, 0.12, 0.08, 0.06, "fur", seed, segs=6, rings=3, lump=0.1))
        m["ware"].merge(K.lathe([(0.0, 0.0), (0.06, 0.0), (0.08, 0.1), (0.05, 0.2), (0.06, 0.24), (0.0, 0.24)], 6, "hull_alt", smooth=True).translate(0.3, 0.05, 0.0))
    elif k == "drinks":
        m["ware"].merge(K.lathe([(0.0, 0.0), (0.07, 0.0), (0.09, 0.12), (0.06, 0.26), (0.07, 0.3), (0.0, 0.3)], 6, "hull_alt", smooth=True))
        for i in range(3):
            a = 2 * math.pi * i / 3
            m["ware"].merge(K.lathe([(0.0, 0.0), (0.05, 0.0), (0.05, 0.13), (0.0, 0.12)], 6, "body_alt", smooth=False).translate(0.22 * math.cos(a), 0.22 * math.sin(a), 0.0))
    else:
        for x in (-0.15, 0.15):
            m["ware"].merge(K.lathe([(0.0, 0.0), (0.07, 0.0), (0.03, 0.04), (0.02, 0.2), (0.05, 0.22), (0.0, 0.22)], 6, "chrome", smooth=True).translate(x, 0.0, 0.0))
            m["food"].merge(K.lathe([(0.018, 0.0), (0.018, 0.16)], 5, "paper", smooth=False, cap_roles=("paper", "paper")).translate(x, 0.0, 0.22))
            m["flame"].merge(K.lathe([(0.0, 0.0), (0.02, 0.03), (0.0, 0.08)], 4, "light", smooth=False).translate(x, 0.0, 0.39))
        lights = [{"pos": [0.0, 0.0, 0.42], "radius": 1.6, "strength": 0.8}]
    if lights:
        return M.centred_lit(solids(m), {"kind": k}, lights)
    return M.centred(solids(m), {"kind": k})


# ---------------------------------------------------------------- signposts (blank sign frames) and lanterns
@register("mprop.signpost", V, "furniture", {
    "kind": S.enum("finger", ["finger", "hanging", "notice"]),
    "arms": S.integer(3, 1, 4, "finger arms (finger kind)"),
}, "Signposts with BLANK faces (paper role, never text: games paint their own): a fingerpost with pointed arms, a "
   "post with a hanging board on a bracket, or a little roofed notice board.", origin="floor_center")
def signpost(P, seed):
    k = P["kind"]
    m = {"post": K.Mesh(), "boards": K.Mesh()}
    if k == "finger":
        m["post"].merge(M.post(0.0, 0.0, 0.0, 2.5, 0.08, 0.065, "frame", sides=6))
        m["post"].merge(K.lathe([(0.0, 0.0), (0.1, 0.02), (0.0, 0.18)], 6, "frame", smooth=False).translate(0.0, 0.0, 2.48))
        for i in range(P["arms"]):
            yaw = [0.4, 2.6, 4.4, 1.5][i]
            z = 2.15 - i * 0.28
            arm = [(0.06, -0.09), (0.82, -0.09), (0.98, 0.0), (0.82, 0.09), (0.06, 0.09)]
            b = K.prism([(x, zz) for x, zz in arm], -0.025, 0.025, "frame")
            b.apply(lambda a: a[:, [0, 2, 1]])
            b.orient_outward()
            fn = M.bake.face_normals(np.asarray(b.v), b.f)
            b.r = ["paper" if abs(n_[1]) > 0.9 else "frame" for n_ in fn]
            m["boards"].merge(b.translate(0.0, 0.0, z).rotate_z(yaw))
    elif k == "hanging":
        from .gen_medievalkit_village2 import blank_sign
        m["post"].merge(M.post(0.0, 0.0, 0.0, 2.7, 0.09, 0.075, "frame", sides=6))
        m["boards"].merge(blank_sign(0.08, 0.0, 2.55, out=(1.0, 0.0, 0.0), arm=1.0))
    else:
        for x in (-0.6, 0.6):
            m["post"].merge(M.post(x, 0.0, 0.0, 2.1, 0.06, 0.055, "frame", sides=6))
        m["boards"].merge(M.chamfer_box(0.0, 0.0, 0.95, 1.3, 0.06, 0.9, "frame", bevel=0.015))
        for i, (x, z, w, h) in enumerate(((-0.33, 1.15, 0.42, 0.55), (0.18, 1.1, 0.36, 0.42), (0.38, 1.55, 0.28, 0.2))):
            m["boards"].merge(K.box(x, -0.04, z + h / 2 - 0.12, w, 0.02, h, "paper"))
        rf = M.roof_pitched(1.6, 0.5, 2.05, 0.28, 0.06, "hull", overhang=0.06, gable_overhang=0.08, droop=0.0, n=1)
        m["boards"].merge(rf.rotate_z(math.pi / 2).rotate_z(math.pi / 2))
    return M.centred(solids(m), {"kind": k})


@register("mprop.lantern", V, "furniture", {
    "base": S.enum("stone", ["stone", "plain"]),
}, "Lamp post: an oak post (on a stone footing) with an iron bracket and a glowing lantern cage; its warm pool is "
   "baked into its own vertices.", origin="floor_center")
def lantern(P, seed):
    from .gen_medievalkit_village2 import lantern as cage
    m = {"iron": K.Mesh(), "post": K.Mesh()}
    m["post"].merge(M.post(0.0, 0.0, 0.0, 2.6, 0.08, 0.06, "frame", sides=6))
    if P["base"] == "stone":
        m["post"].merge(M.chamfer_box(0.0, 0.0, 0.0, 0.32, 0.32, 0.25, "wall_alt", bevel=0.03))
    lm, lp = cage(0.0, -0.05, 2.45, out=(0.0, -1.0, 0.0), arm=0.5)
    m["iron"].merge(lm)
    return M.centred_lit(solids(m), {"base": P["base"]}, [{"pos": lp, "radius": 3.4, "strength": 0.9}])


@register("mprop.lantern_hung", V, "furniture", {
    "kind": S.enum("wall", ["wall", "hanging"]),
}, "Hung lanterns: a wall lantern on an iron bracket (wall-face anchor, front +Z, for lantern sockets) or a lantern "
   "hanging on a chain (origin at the ceiling hook). The cage glows; its warm pool is baked into its own vertices.",
   origin="wall_face")
def lantern_hung(P, seed):
    from .gen_medievalkit_village2 import lantern as cage
    k = P["kind"]
    m = {"iron": K.Mesh()}
    if k == "wall":
        lm, lp = cage(0.0, 0.0, 2.3, out=(0.0, -1.0, 0.0), arm=0.4)
        m["iron"].merge(lm)
        m["iron"].merge(M.chamfer_box(0.0, -0.025, 2.15, 0.12, 0.05, 0.3, "metal", bevel=0.01))
        return M.assemble(solids(m), {"kind": k}, "wall_face", lights=[{"pos": lp, "radius": 3.0, "strength": 0.85}], ground=False)
    m["iron"].merge(M.beam((0.0, 0.0, -0.02), (0.0, 0.0, -0.75), 0.025, 0.025, "metal", out=(1.0, 0.0, 0.0), bevel=0.0, embed=0.0))
    m["iron"].merge(M.octa_box(0.0, 0.0, -1.15, 0.24, 0.24, 0.36, "light", chamfer=0.05, top_role="metal", top_bevel=0.03))
    m["iron"].merge(M.chamfer_box(0.0, 0.0, -0.82, 0.3, 0.3, 0.07, "metal", bevel=0.02))
    return M.assemble(solids(m), {"kind": k}, "ceiling_hook", lights=[{"pos": [0.0, 0.0, -0.95], "radius": 3.0, "strength": 0.85}], ground=False)
