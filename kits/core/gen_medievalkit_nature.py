"""MEDIEVALKIT nature (mnat.*) and terrain / backdrops (mter.*), theme-agnostic.

Trees are chunky N64 forms: a tapered faceted trunk with a couple of limbs and a crown of a few lumpy foliage
masses (foliage role: painted leaf clusters, dark underside from the vertex bake), never alpha cards. Ground pieces
are 4 m cell tiles (origin at the tile centre, top at y = 0) that interlock edge to edge: path tiles keep the path
on the cell-edge midpoints (2 m wide) so straights, corners, tees, crosses and ends join like the dungeon floor.
Backdrops are inward-facing view-plane bands (vista / vista_far roles) for the far distance: rolling hills and a
far ridge with original castle silhouettes.
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from . import gen_medievalkit_core as M
from .gen_medievalkit_village import V
from .rng import rng


def solids(m):
    return [M.solid(k, v) for k, v in m.items() if v.f]


def trunk(h, r0, r1, seed, sides=6, lean=0.0, role="bark"):
    t = K.lathe([(0.0, -0.05), (r0 * 1.35, -0.05), (r0, 0.35), (r1, h)], sides, role, smooth=True, roles=["bark", role, role],
                start=seed * 0.37, cap_roles=(role, role))
    if lean:
        t.apply(lambda a: np.stack([a[:, 0] + lean * a[:, 2] / max(h, 1e-6) * a[:, 2] / max(h, 1e-6), a[:, 1], a[:, 2]], 1))
    return t


def limb(p0, p1, r):
    return M.beam(p0, p1, r * 2, r * 2, "bark", out=(0.0, 0.0, 1.0), bevel=0.25, embed=0.0)


# ---------------------------------------------------------------- trees
@register("mnat.oak", V, "flora", {
    "kind": S.enum("broad", ["broad", "young", "old"]),
    "height": S.num(7.5, 4.0, 11.0),
}, "Oak: a stout tapered trunk with two limbs under a broad crown of four lumpy foliage masses (broad), a slim young "
   "oak, or an old pollarded oak with a thicker trunk and a lower, wider crown.", origin="floor_center")
def oak(P, seed):
    k, H = P["kind"], P["height"]
    r = rng(seed, "mnat.oak", k)
    m = {"trunk": K.Mesh(), "crown": K.Mesh()}
    r0 = {"broad": 0.38, "young": 0.2, "old": 0.55}[k] * H / 7.5
    th = H * (0.45 if k != "old" else 0.38)
    m["trunk"].merge(trunk(th + 0.6, r0, r0 * 0.6, seed))
    spread = {"broad": 1.0, "young": 0.6, "old": 1.25}[k] * H / 7.5
    masses = [(0.0, 0.0, th + 1.9 * spread, 2.3, 2.1, 1.6)]
    for i in range(3 if k != "young" else 2):
        a = 2 * math.pi * i / 3 + r.random() * 0.6
        masses.append((1.5 * spread * math.cos(a), 1.5 * spread * math.sin(a), th + (0.9 + 0.5 * r.random()) * spread, 1.7, 1.6, 1.25))
    for i, (x, y, z, rx, ry, rz) in enumerate(masses):
        s_ = spread
        m["crown"].merge(M.blob(x, y, z, rx * s_, ry * s_, rz * s_, "foliage", seed * 7 + i, segs=7, rings=4, lump=0.16))
        if i:
            m["trunk"].merge(limb((0.0, 0.0, th * 0.85), (x * 0.7, y * 0.7, z - rz * s_ * 0.6), r0 * 0.45))
    return M.centred(solids(m), {"kind": k})


@register("mnat.pine", V, "flora", {
    "kind": S.enum("tall", ["tall", "short", "snowy"]),
    "height": S.num(9.0, 4.0, 14.0),
}, "Pine / fir: a straight trunk under stacked drooping tiers of needles (foliage role), tall or short; the snowy "
   "kind caps every tier with snow.", origin="floor_center")
def pine(P, seed):
    k, H = P["kind"], P["height"] * (0.6 if P["kind"] == "short" else 1.0)
    m = {"trunk": K.Mesh(), "tiers": K.Mesh(), "snow": K.Mesh()}
    m["trunk"].merge(trunk(H * 0.5, 0.22 * H / 9, 0.12 * H / 9, seed, sides=5))
    n = 4 if k != "short" else 3
    for i in range(n):
        t = i / n
        z0 = H * (0.18 + 0.68 * t)
        R = (1.0 - 0.72 * t) * H * 0.26
        hh = H * 0.36 * (1.0 - 0.3 * t)
        prof = [(0.0, z0 - 0.08 * hh), (R, z0), (R * 0.9, z0 + 0.12 * hh), (R * 0.3, z0 + hh * 0.75), (0.0, z0 + hh)]
        tier = K.lathe(prof, 7, "foliage", smooth=True, start=i * 0.45 + seed * 0.1)
        M.jitter(tier, seed * 5 + i, 0.06 * H / 9, keep_z0=False)
        m["tiers"].merge(tier)
        if k == "snowy":
            cap = K.lathe([(0.0, z0 + hh * 0.5), (R * 0.62, z0 + hh * 0.3), (0.0, z0 + hh + 0.05)], 7, "snow",
                          smooth=True, start=i * 0.45 + seed * 0.1)
            m["snow"].merge(cap)
    return M.centred(solids(m), {"kind": k})


@register("mnat.orchard", V, "flora", {
    "kind": S.enum("apple", ["apple", "pear", "blossom", "bare"]),
}, "Orchard fruit tree: a short crooked trunk under a rounded crown dotted with fruit (apple / pear), in blossom, or "
   "bare winter branches.", origin="floor_center")
def orchard(P, seed):
    k = P["kind"]
    r = rng(seed, "mnat.orchard", k)
    m = {"trunk": K.Mesh(), "crown": K.Mesh(), "fruit": K.Mesh()}
    m["trunk"].merge(trunk(2.0, 0.17, 0.1, seed, sides=5))
    if k == "bare":
        for i in range(5):
            a = 2 * math.pi * i / 5 + r.random() * 0.5
            p1 = (1.3 * math.cos(a), 1.3 * math.sin(a), 3.0 + 0.6 * r.random())
            m["trunk"].merge(limb((0.0, 0.0, 1.7), p1, 0.06))
            m["trunk"].merge(limb(p1, (p1[0] * 1.3, p1[1] * 1.3, p1[2] + 0.7), 0.035))
        return M.centred(solids(m), {"kind": k})
    role = "flower" if k == "blossom" else "foliage"
    m["crown"].merge(M.blob(0.0, 0.0, 3.0, 1.7, 1.6, 1.25, role, seed, segs=8, rings=4, lump=0.14))
    m["crown"].merge(M.blob(0.7, -0.3, 2.5, 1.0, 1.0, 0.75, role, seed + 1, segs=6, rings=3, lump=0.14))
    if k in ("apple", "pear"):
        fr = "cushion" if k == "apple" else "fur"
        for i in range(8):
            a = 2 * math.pi * i / 8 + r.random() * 0.4
            z = 2.4 + 1.2 * r.random()
            rad = 1.62 * math.sqrt(max(0.0, 1.0 - ((z - 3.0) / 1.3) ** 2)) + 0.02
            m["fruit"].merge(K.lathe([(0.0, -0.1), (0.1, 0.0), (0.0, 0.1)], 4, fr, smooth=True).translate(rad * math.cos(a), rad * math.sin(a), z))
    return M.centred(solids(m), {"kind": k})


@register("mnat.bush", V, "flora", {
    "kind": S.enum("round", ["round", "flowering", "berry", "bramble"]),
}, "Shrub: a round bush, a flowering bush, a berry bush, or a low tangled bramble.", origin="floor_center")
def bush(P, seed):
    k = P["kind"]
    m = {"bush": K.Mesh(), "dots": K.Mesh()}
    if k == "bramble":
        for i, (x, y, s_) in enumerate(((-0.5, 0.0, 0.7), (0.4, 0.2, 0.6), (0.0, -0.3, 0.5))):
            m["bush"].merge(M.blob(x, y, 0.25, 0.8 * s_, 0.7 * s_, 0.45 * s_, "foliage", seed + i, segs=6, rings=3, lump=0.3))
    else:
        m["bush"].merge(M.blob(0.0, 0.0, 0.55, 0.85, 0.8, 0.62, "foliage", seed, segs=7, rings=4, lump=0.18))
        if k in ("flowering", "berry"):
            r = rng(seed, "mnat.bush")
            role = "flower" if k == "flowering" else "cushion"
            for i in range(7):
                a = 2 * math.pi * i / 7 + r.random()
                z = 0.4 + 0.5 * r.random()
                rad = 0.84 * math.sqrt(max(0.0, 1.0 - ((z - 0.55) / 0.65) ** 2))
                m["dots"].merge(K.lathe([(0.0, -0.07), (0.08, 0.0), (0.0, 0.07)], 4, role, smooth=True).translate(rad * math.cos(a), rad * math.sin(a), z))
    return M.centred(solids(m), {"kind": k})


@register("mnat.hedgerow", V, "flora", {
    "kind": S.enum("straight", ["straight", "corner", "gap"]),
    "height": S.num(1.4, 0.8, 2.2),
}, "Hedgerow on a cell edge (4 m along X): a clipped-but-lumpy hedge, a corner turning south, or a hedge with a "
   "field gap. wall_end sockets (hedge) at +-2 m so hedges, fences and walls interlock.", origin="cell_edge")
def hedgerow(P, seed):
    k, H = P["kind"], P["height"]
    m = {"hedge": K.Mesh()}

    def run(x0, x1, sd):
        L = x1 - x0
        n = max(2, int(round(L / 1.0)))
        rings = []
        for i in range(n + 1):
            x = x0 + L * i / n
            w = 0.45 if 0 < i < n else 0.38
            rings.append([(x, -w, 0.0), (x, w, 0.0), (x, w * 0.92, H * 0.8), (x, w * 0.55, H), (x, -w * 0.55, H), (x, -w * 0.92, H * 0.8)])
        h = K.loft(rings, "foliage", smooth=True)
        M.jitter(h, sd, 0.08, keep_z0=True)
        return h
    if k == "gap":
        m["hedge"].merge(run(-2.0, -0.9, seed))
        m["hedge"].merge(run(0.9, 2.0, seed + 1))
    else:
        m["hedge"].merge(run(-2.0, 2.0, seed))
    if k == "corner":
        c = run(0.5, 4.0, seed + 2)
        c.rotate_z(-math.pi / 2).translate(2.0, 0.0, 0.0)
        m["hedge"].merge(c)
    socks = [M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="hedge")]
    socks.append(M.sock("wall_end", (2.0, 0.0, 0.0) if k != "corner" else (2.0, -4.0, 0.0), "e" if k != "corner" else "s", wall="hedge"))
    return M.assemble(solids(m), {"kind": k}, "cell_edge", sockets=socks)


@register("mnat.rock", V, "flora", {
    "kind": S.enum("boulder", ["boulder", "cluster", "standing", "outcrop"]),
    "size": S.num(1.0, 0.4, 3.0),
}, "Rocks: a mossy boulder, a cluster of three, a tall weathered standing stone, or a low layered outcrop.",
   origin="floor_center")
def rock(P, seed):
    k, s_ = P["kind"], P["size"]
    m = {"rock": K.Mesh(), "moss": K.Mesh()}
    if k == "boulder":
        m["rock"].merge(M.blob(0.0, 0.0, 0.35 * s_, 0.8 * s_, 0.65 * s_, 0.55 * s_, "rock", seed, segs=6, rings=4, lump=0.25, smooth=False))
        m["moss"].merge(M.blob(0.05 * s_, 0.0, 0.72 * s_, 0.45 * s_, 0.38 * s_, 0.14 * s_, "cap", seed + 9, segs=6, rings=3, lump=0.15))
    elif k == "cluster":
        for i, (x, y, f) in enumerate(((-0.5, 0.0, 1.0), (0.45, 0.2, 0.7), (0.1, -0.5, 0.5))):
            m["rock"].merge(M.blob(x * s_, y * s_, 0.3 * f * s_, 0.6 * f * s_, 0.5 * f * s_, 0.45 * f * s_, "rock", seed + i, segs=6, rings=3, lump=0.25, smooth=False))
    elif k == "standing":
        st = K.loft([[(-0.45 * s_, -0.3 * s_, 0.0), (0.45 * s_, -0.3 * s_, 0.0), (0.42 * s_, 0.3 * s_, 0.0), (-0.42 * s_, 0.3 * s_, 0.0)],
                     [(-0.38 * s_, -0.26 * s_, 1.6 * s_), (0.4 * s_, -0.25 * s_, 1.6 * s_), (0.36 * s_, 0.26 * s_, 1.6 * s_), (-0.36 * s_, 0.25 * s_, 1.6 * s_)],
                     [(-0.2 * s_, -0.18 * s_, 2.3 * s_), (0.26 * s_, -0.16 * s_, 2.4 * s_), (0.2 * s_, 0.18 * s_, 2.35 * s_), (-0.22 * s_, 0.16 * s_, 2.25 * s_)]],
                    "rock", smooth=False)
        M.jitter(st, seed + 3, 0.06 * s_, keep_z0=True)
        m["rock"].merge(st)
        m["moss"].merge(M.blob(0.0, 0.0, 0.05, 0.62 * s_, 0.5 * s_, 0.12 * s_, "cap", seed + 5, segs=6, rings=3, lump=0.2))
    else:
        for i in range(3):
            w = (2.4 - 0.55 * i) * s_
            m["rock"].merge(M.blob(0.15 * i * s_, 0.1 * i * s_, (0.25 + 0.4 * i) * s_, w / 2, w * 0.35, 0.3 * s_, "cliff", seed + i, segs=6, rings=3, lump=0.18, smooth=False))
        m["moss"].merge(M.blob(0.35 * s_, 0.2 * s_, 1.1 * s_, 0.55 * s_, 0.35 * s_, 0.1 * s_, "cap", seed + 7, segs=6, rings=3, lump=0.15))
    return M.centred(solids(m), {"kind": k})


@register("mnat.stump", V, "flora", {
    "kind": S.enum("stump", ["stump", "log", "mossy_log"]),
}, "A sawn tree stump with root flares, a fallen log, or a mossy log with a fungus shelf.", origin="floor_center")
def stump(P, seed):
    k = P["kind"]
    m = {"wood": K.Mesh(), "moss": K.Mesh()}
    if k == "stump":
        m["wood"].merge(K.lathe([(0.0, -0.05), (0.55, -0.05), (0.42, 0.12), (0.36, 0.55), (0.0, 0.5)], 7, "bark", smooth=True,
                                roles=["bark", "bark", "bark", "body"]))
        M.jitter(m["wood"], seed, 0.04, keep_z0=True)
    else:
        lg = K.lathe([(0.0, 0.0), (0.3, 0.0), (0.27, 2.6), (0.0, 2.6)], 6, "bark", smooth=True, roles=["body", "bark", "body"])
        lg.apply(lambda a: np.stack([a[:, 2] - 1.3, a[:, 1], a[:, 0] + 0.28], 1))
        m["wood"].merge(lg.orient_outward())
        if k == "mossy_log":
            m["moss"].merge(M.blob(-0.2, 0.0, 0.52, 0.9, 0.24, 0.1, "cap", seed, segs=6, rings=3, lump=0.2))
            m["moss"].merge(K.lathe([(0.0, 0.0), (0.18, 0.02), (0.0, 0.05)], 5, "paper", smooth=False).translate(0.6, -0.3, 0.35))
    return M.centred(solids(m), {"kind": k})


@register("mnat.flowers", V, "flora", {
    "kind": S.enum("meadow", ["meadow", "tufts", "reeds", "mushrooms"]),
}, "Small ground dressing: a patch of meadow flowers, grass tufts, waterside reeds, or a ring of mushrooms.",
   origin="floor_center")
def flowers(P, seed):
    k = P["kind"]
    r = rng(seed, "mnat.flowers", k)
    m = {"plants": K.Mesh(), "heads": K.Mesh()}
    n = {"meadow": 7, "tufts": 6, "reeds": 7, "mushrooms": 6}[k]
    for i in range(n):
        a = 2 * math.pi * i / n + r.random() * 0.5
        rad = 0.25 + 0.45 * r.random()
        x, y = rad * math.cos(a), rad * math.sin(a)
        if k == "meadow":
            m["plants"].merge(K.lathe([(0.0, 0.0), (0.06, 0.0), (0.0, 0.32 + 0.1 * r.random())], 3, "foliage", smooth=False, start=a).translate(x, y, 0.0))
            m["heads"].merge(K.lathe([(0.0, -0.04), (0.07, 0.0), (0.0, 0.05)], 4, "flower", smooth=False, start=a).translate(x, y, 0.36))
        elif k == "tufts":
            m["plants"].merge(K.lathe([(0.0, 0.0), (0.16, 0.0), (0.0, 0.42 + 0.15 * r.random())], 4, "grass", smooth=False, start=a).translate(x, y, 0.0))
        elif k == "reeds":
            h = 0.9 + 0.5 * r.random()
            m["plants"].merge(K.lathe([(0.0, 0.0), (0.03, 0.0), (0.0, h)], 3, "foliage", smooth=False, start=a).translate(x, y, 0.0))
            m["heads"].merge(K.lathe([(0.0, 0.0), (0.035, 0.05), (0.03, 0.2), (0.0, 0.25)], 4, "bark", smooth=False).translate(x, y, h - 0.28))
        else:
            h = 0.08 + 0.08 * r.random()
            m["plants"].merge(K.lathe([(0.03, 0.0), (0.025, h)], 4, "paper", smooth=False, cap_roles=("paper", "paper")).translate(x, y, 0.0))
            m["heads"].merge(K.lathe([(0.0, 0.0), (0.1, 0.01), (0.07, 0.05), (0.0, 0.07)], 5, "cushion", smooth=True).translate(x, y, h))
    return M.centred(solids(m), {"kind": k})


@register("mnat.dead_tree", V, "flora", {
    "kind": S.enum("bare", ["bare", "snowy"]),
}, "Leafless tree: a gnarled trunk splitting into crooked bare branches (winter / spooky), optionally snow-laden.",
   origin="floor_center")
def dead_tree(P, seed):
    r = rng(seed, "mnat.dead_tree")
    m = {"trunk": K.Mesh(), "snow": K.Mesh()}
    m["trunk"].merge(trunk(3.2, 0.3, 0.16, seed, sides=5))
    for i in range(5):
        a = 2 * math.pi * i / 5 + r.random() * 0.6
        p0 = (0.0, 0.0, 2.6 + 0.3 * i / 5)
        p1 = (1.6 * math.cos(a), 1.6 * math.sin(a), 4.2 + 0.8 * r.random())
        p2 = (p1[0] * 1.5 + 0.3 * r.random(), p1[1] * 1.5, p1[2] + 0.9)
        m["trunk"].merge(limb(p0, p1, 0.09))
        m["trunk"].merge(limb(p1, p2, 0.05))
        if P["kind"] == "snowy":
            m["snow"].merge(M.beam((p0[0] + (p1[0] - p0[0]) * 0.2, p0[1] + (p1[1] - p0[1]) * 0.2, p0[2] + 0.12 + (p1[2] - p0[2]) * 0.2),
                                   (p1[0], p1[1], p1[2] + 0.1), 0.13, 0.06, "snow", out=(0.0, 0.0, 1.0), bevel=0.3, embed=0.0))
    return M.centred(solids(m), {"kind": P["kind"]})


# ---------------------------------------------------------------- ground tiles, paths, fields
def tile_grid(x0, y0, x1, y1, n, role_fn, z_fn=None, up=True):
    """n x n quad sheet; role_fn(cx, cy) per quad; z_fn(x, y) per vertex (default 0)."""
    v, f, r = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = y0 + (y1 - y0) * j / n
            v.append((x, y, z_fn(x, y) if z_fn else 0.0))
    W = n + 1
    for j in range(n):
        for i in range(n):
            a = j * W + i
            f.append((a, a + 1, a + W + 1, a + W) if up else (a, a + W, a + W + 1, a + 1))
            r.append(role_fn(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n))
    return K.Mesh().add(v, f, r, False)


PATH_LAYOUTS = {"straight": "ns", "corner": "ne", "tee": "new", "cross": "nesw", "end": "n", "none": ""}


@register("mter.ground", V, "terrain", {
    "kind": S.enum("grass", ["grass", "cobble", "dirt", "plaza", "snow", "field_edge"]),
    "path": S.enum("none", list(PATH_LAYOUTS), "path layout across the tile (path on cell-edge midpoints, 2 m wide)"),
    "kerbs": S.boolean(True, "dressed kerb stones along cobbled path edges"),
    "cells": S.integer(1, 1, 4, "square tile size in cells (path layouts need 1)"),
    "quads": S.integer(0, 0, 16, "grid quads per side (0 = 4 per tile on one cell, 2 per cell on blocks; far meadows: 1 per cell)"),
}, "Ground tile, one 4 m cell (or a plain cells x cells block) (origin at the centre, top at y = 0): grass meadow, cobbles, dirt, flagstone plaza, "
   "snow, or a field edge; optionally crossed by a cobbled path (straight / corner / tee / cross / end) that meets "
   "the next tile on the cell-edge midpoints. Path sockets on every path end.", origin="terrain_center")
def ground(P, seed):
    k = P["kind"]
    base = {"grass": "grass", "cobble": "path", "dirt": "dirt", "plaza": "step", "snow": "snow", "field_edge": "grass"}[k]
    arms = PATH_LAYOUTS[P["path"]]
    hw = 1.0

    def on_path(x, y):
        if not arms:
            return False
        c = abs(x) <= hw and abs(y) <= hw
        return c or ("n" in arms and abs(x) <= hw and y > 0) or ("s" in arms and abs(x) <= hw and y < 0) or \
            ("e" in arms and abs(y) <= hw and x > 0) or ("w" in arms and abs(y) <= hw and x < 0)

    def role(x, y):
        if k == "field_edge" and y > 0.6:
            return "field"
        return "path" if on_path(x, y) and base != "path" else base
    nc = int(P["cells"])
    if nc > 1:
        arms = ""
    hh = 2.0 * nc
    m = {"ground": tile_grid(-hh, -hh, hh, hh, int(P["quads"]) or (4 if nc == 1 else 2 * nc), role)}
    m["kerbs"] = K.Mesh()
    if arms and P["kerbs"] and base not in ("path", "step"):
        for d_ in arms:
            for s_ in (-1, 1):
                for t in (0.5, 1.5):
                    if d_ in "ns":
                        x, y = s_ * (hw + 0.08), (1 if d_ == "n" else -1) * t
                        kb = M.chamfer_box(x, y, -0.06, 0.18, 0.92, 0.14, "trim", bevel=0.04)
                    else:
                        x, y = (1 if d_ == "e" else -1) * t, s_ * (hw + 0.08)
                        kb = M.chamfer_box(x, y, -0.06, 0.92, 0.18, 0.14, "trim", bevel=0.04)
                    m["kerbs"].merge(kb)
    socks = [M.sock("path", {"n": (0.0, 2.0, 0.0), "s": (0.0, -2.0, 0.0), "e": (2.0, 0.0, 0.0), "w": (-2.0, 0.0, 0.0)}[d_], d_, width_m=2.0)
             for d_ in arms]
    nodes = [Node("ground", m["ground"], "shell")] + ([M.solid("kerbs", m["kerbs"])] if m["kerbs"].f else [])
    if nc > 1:
        return M.assemble(nodes, {"kind": k, "path": "none"}, "cell_block_centre", cells=(nc, nc), ground=False)
    return M.assemble(nodes, {"kind": k, "path": P["path"]}, "cell_centre", cells=(1, 1), sockets=socks, ground=False)


@register("mnat.field", V, "terrain", {
    "kind": S.enum("wheat", ["wheat", "cabbage", "ploughed", "vines"]),
    "cells": S.integer(2, 1, 3, "square size in cells (4 m)"),
}, "Farm field on the grid (cells x cells, origin at the centre, ground at y = 0): standing wheat as a golden "
   "bevelled mass with a ragged top, rows of cabbages, ploughed furrows, or a vineyard of staked rows.",
   origin="terrain_center")
def field(P, seed):
    k, n = P["kind"], P["cells"]
    L = n * M.CELL
    h = L / 2
    m = {"soil": tile_grid(-h, -h, h, h, 2 * n, lambda x, y: "field" if k != "ploughed" else "dirt"), "crop": K.Mesh()}
    r = rng(seed, "mnat.field", k)
    if k == "wheat":
        rows = 4 * n
        for j in range(rows):
            y = -h + (j + 0.5) * L / rows
            ridge = K.prism([(-0.5, 0.0), (0.5, 0.0), (0.42, 0.78), (0.12, 1.05), (-0.18, 1.0), (-0.44, 0.74)], -h + 0.25, h - 0.25, "fur")
            ridge.apply(lambda a: np.stack([a[:, 2], a[:, 0], a[:, 1]], 1))
            ridge = M.swap_uv(ridge.orient_outward()).translate(0.0, y, -0.02)
            M.jitter(ridge, seed + j, 0.06, axes=(0.2, 0.3, 1.0), keep_z0=True)
            m["crop"].merge(ridge)
    elif k == "cabbage":
        rows = 2 * n
        for j in range(rows):
            y = -h + (j + 0.5) * L / rows
            for i in range(2 * n):
                x = -h + (i + 0.5) * L / (2 * n) + 0.2 * (r.random() - 0.5)
                m["crop"].merge(M.blob(x, y, 0.16, 0.36, 0.34, 0.24, "cap", seed + j * 31 + i, segs=5, rings=3, lump=0.2))
    elif k == "ploughed":
        rows = 4 * n
        for j in range(rows):
            y = -h + (j + 0.5) * L / rows
            fr = K.prism([(-0.3, 0.0), (0.3, 0.0), (0.12, 0.22), (-0.12, 0.22)], -h + 0.2, h - 0.2, "dirt")
            fr.apply(lambda a: np.stack([a[:, 2], a[:, 0], a[:, 1]], 1))
            m["crop"].merge(M.swap_uv(fr.orient_outward()).translate(0.0, y, -0.02))
    else:
        rows = 2 * n
        for j in range(rows):
            y = -h + (j + 0.5) * L / rows
            for x in (-h + 0.4, h - 0.4):
                m["crop"].merge(M.post(x, y, 0.0, 1.5, 0.05, 0.04, "post", sides=4))
            vine = K.loft([[(-h + 0.4, y - 0.22, 0.4), (-h + 0.4, y + 0.22, 0.4), (-h + 0.4, y + 0.18, 1.45), (-h + 0.4, y - 0.18, 1.45)],
                           [(h - 0.4, y - 0.22, 0.4), (h - 0.4, y + 0.22, 0.4), (h - 0.4, y + 0.18, 1.45), (h - 0.4, y - 0.18, 1.45)]],
                          "foliage", smooth=False)
            M.jitter(vine, seed + j, 0.06, keep_z0=False)
            m["crop"].merge(vine)
    nodes = [Node("soil", m["soil"], "shell"), M.solid("crop", m["crop"])]
    return M.assemble(nodes, {"kind": k, "cells": n}, "cell_block_centre", cells=(n, n), ground=False)


# ---------------------------------------------------------------- terrain: hills, banks, water
def height_hill(x, y, R, H, seed):
    d = math.hypot(x, y) / R
    if d >= 1.0:
        return 0.0
    base = H * (0.5 + 0.5 * math.cos(math.pi * d))
    return base * (1.0 + 0.12 * math.sin(3.1 * x / R + seed) * math.cos(2.3 * y / R - seed))


@register("mter.hill", V, "terrain", {
    "size": S.num(16.0, 8.0, 32.0, "footprint width (m)"),
    "height": S.num(4.0, 1.0, 10.0),
    "rock": S.boolean(True, "steep faces turn to rock"),
}, "Rolling hill: a smooth cosine mound on a coarse grid (grass on gentle slopes, rock on the steep ones), skirt at "
   "y = 0 so it sits on any ground tile.", origin="terrain_center")
def hill(P, seed):
    R, H = P["size"] / 2, P["height"]
    n = 8
    sh = tile_grid(-R, -R, R, R, n, lambda x, y: "grass", z_fn=lambda x, y: height_hill(x, y, R * 1.02, H, seed))
    if P["rock"]:
        A = np.asarray(sh.v)
        fn = M.bake.face_normals(A, sh.f)
        sh.r = ["rock" if nz[2] < 0.72 else "grass" for nz in fn]
    return Asset([Node("hill", sh, "shell")], {"size_m": P["size"], "height_m": H, "bbox_size_m": [2 * R, 2 * R, H]})


@register("mter.bank", V, "terrain", {
    "kind": S.enum("grass", ["grass", "rock", "rubble_wall"]),
    "rise": S.num(2.0, 1.0, 4.0),
}, "Terrace edge on a cell edge (4 m along X; the high side toward +Y): a grassy bank, a rock face with a grass lip, "
   "or a rubble retaining wall with a coping. Pairs with vlg.stairs for level changes.", origin="cell_edge")
def bank(P, seed):
    k, Hh = P["kind"], P["rise"]
    m = {"bank": K.Mesh(), "top": K.Mesh()}
    if k == "grass":
        sec = [(-1.2, 0.0), (1.0, 0.0), (1.0, Hh), (0.4, Hh), (-0.5, Hh * 0.45)]
        b = K.prism(sec, -2.0, 2.0, "grass")
    elif k == "rock":
        sec = [(-0.4, 0.0), (1.0, 0.0), (1.0, Hh), (-0.15, Hh), (-0.3, Hh * 0.6)]
        b = K.prism(sec, -2.0, 2.0, "cliff")
    else:
        sec = [(-0.3, 0.0), (1.0, 0.0), (1.0, Hh), (-0.1, Hh)]
        b = K.prism(sec, -2.0, 2.0, "wall_alt")
    b.apply(lambda a: a[:, [2, 0, 1]])
    b.orient_outward()
    fn = M.bake.face_normals(np.asarray(b.v), b.f)
    top_role = {"grass": "grass", "rock": "grass", "rubble_wall": "grass"}[k]
    b.r = [top_role if nz[2] > 0.8 else r_ for nz, r_ in zip(fn, b.r)]
    m["bank"].merge(M.swap_uv(b))
    if k != "grass":
        M.jitter(m["bank"], seed, 0.05, keep_z0=True)
    if k == "rubble_wall":
        m["top"].merge(M.chamfer_box(0.0, 0.0, Hh - 0.02, 4.0, 0.42, 0.18, "trim", bevel=0.04))
    socks = [M.sock("wall_end", (-2.0, 0.0, 0.0), "w", wall="bank", height_m=Hh), M.sock("wall_end", (2.0, 0.0, 0.0), "e", wall="bank", height_m=Hh)]
    return M.assemble(solids(m), {"kind": k, "rise_m": Hh}, "cell_edge", sockets=socks)


@register("mter.water", V, "terrain", {
    "kind": S.enum("river", ["river", "moat", "pond"]),
}, "Water on the grid: a river reach across one cell (4 m along X) with grassy banks, a castle moat segment with "
   "rubble revetments, or a round pond with a reed-and-stone rim (water role scrolls).", origin="terrain_center")
def water(P, seed):
    k = P["kind"]
    m = {"water": K.Mesh(), "banks": K.Mesh()}
    if k == "pond":
        ring = [(2.4 * math.cos(a), 1.9 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
        w = K.prism(ring, -0.16, -0.11, "water")
        m["water"].merge(w)
        m["banks"].merge(M.ring_path_solid([(1.04 * x, 1.04 * y) for x, y in ring], -0.6, 0.05, 0.55, "dirt", chamfer=0.05))
        nodes = solids(m)
        return Asset(nodes, {"kind": k, "bbox_size_m": [5.0, 4.0, 0.7]})
    w = K.box(0.0, 0.0, -0.45 if k == "river" else -0.9, 4.0, 2.4 if k == "river" else 3.0, 0.06, "water")
    m["water"].merge(w)
    for s_ in (-1, 1):
        if k == "river":
            sec = [(0.0, -0.9), (0.9, -0.9), (0.9, 0.0), (0.0, 0.0), (-0.45, -0.55)]
            role = "dirt"
        else:
            sec = [(0.0, -1.6), (0.6, -1.6), (0.6, 0.0), (0.05, 0.0)]
            role = "wall_alt"
        b = K.prism([(s_ * y, z) for y, z in sec] if s_ > 0 else [(-y, z) for y, z in reversed(sec)], -2.0, 2.0, role)
        b.apply(lambda a: a[:, [2, 0, 1]])
        b.orient_outward()
        off = 1.2 if k == "river" else 1.5
        fn = M.bake.face_normals(np.asarray(b.v), b.f)
        b.r = ["grass" if nz[2] > 0.8 else role for nz in fn]
        m["banks"].merge(M.swap_uv(b).translate(0.0, s_ * off, 0.0))
    socks = [M.sock("water", (-2.0, 0.0, 0.0), "w"), M.sock("water", (2.0, 0.0, 0.0), "e")]
    return M.assemble(solids(m), {"kind": k}, "cell_centre", cells=(1, 1), sockets=socks, ground=False)


# ---------------------------------------------------------------- far backdrops (view-plane bands)
def band(radius, heights, z0, role, seg_uv=1.0):
    """Inward-facing vertical band: heights[i] = top height at angle i/len (closed loop)."""
    n = len(heights)
    v, f, uv = [], [], []
    for i in range(n + 1):
        a = 2 * math.pi * (i % n) / n
        x, y = radius * math.cos(a), radius * math.sin(a)
        v.append((x, y, z0))
        v.append((x, y, heights[i % n]))
    top = max(heights)
    for i in range(n):
        a, b = 2 * i, 2 * i + 2
        f.append((a, a + 1, b + 1, b))
        uv.append(("n", [(i / n * seg_uv, 0.0), (i / n * seg_uv, (heights[i] - z0) / (top - z0)),
                         ((i + 1) / n * seg_uv, (heights[(i + 1) % n] - z0) / (top - z0)), ((i + 1) / n * seg_uv, 0.0)]))
    m = K.Mesh().add(v, f, role, False, uv)
    A = np.asarray(m.v)
    for fi, fc in enumerate(m.f):
        p = A[list(fc)]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        if np.dot(nrm, -p.mean(0)) < 0:
            m.f[fi] = tuple(reversed(fc))
            m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
    return m


@register("mter.backdrop", V, "sky", {
    "kind": S.enum("hills_castle", ["hills_castle", "hills", "mountains"]),
    "radius": S.runtime(S.num(260.0, 60.0, 900.0, "placement radius (fit inside fog / far plane)")),
}, "Far backdrop (origin at the viewer): an inward-facing band of rolling hills (vista role) in front of a far "
   "ridge (vista_far) that carries two original castle silhouettes (square keep with corner turrets, a round tower "
   "pair with a curtain), or a jagged mountain range. View-plane roles, so they take the sky colours of every variant.",
   origin="viewer")
def backdrop(P, seed):
    R = P["radius"]
    r = rng(seed, "mter.backdrop", P["kind"])
    n = 24
    near = [R * (0.05 + 0.035 * math.sin(i * 0.9 + seed) + 0.025 * math.sin(i * 2.3 + 1.0)) for i in range(n)]
    nodes = [Node("vista", band(R, near, -R * 0.05, "vista"), "shell")]
    if P["kind"] == "mountains":
        far = [R * (0.13 + 0.07 * abs(math.sin(i * 1.7 + seed)) + 0.03 * r.random()) for i in range(n)]
        nodes.append(Node("vista_far", band(R * 1.25, far, -R * 0.05, "vista_far"), "shell"))
    elif P["kind"] == "hills_castle":
        m_ = 40
        base = [R * 1.25 * (0.08 + 0.02 * math.sin(i * 0.7 + seed)) for i in range(m_)]
        # castle silhouettes as raised notches on the far ridge (keep with turrets at ~30 deg, towers + curtain at ~200 deg)
        for c, prof in ((3, [0.05, 0.11, 0.09, 0.09, 0.11, 0.05]), (22, [0.07, 0.04, 0.04, 0.07])):
            for j, hgt in enumerate(prof):
                base[(c + j) % m_] += R * 1.25 * hgt
        nodes.append(Node("vista_far", band(R * 1.25, base, -R * 0.05, "vista_far"), "shell"))
    ext = [2.5 * R, 2.5 * R, R * 0.4]
    return Asset(nodes, {"kind": P["kind"], "radius_m": R, "origin": "viewer", "bbox_size_m": ext})
