"""ANCIENTKIT nature (wild.*), theme-agnostic (Blender space, +Z up, front faces -Y = glTF south).

Ten generators: date palms (leaning trunks of chevron scales and V-folded two-sided fronds), jungle trees (buttress
roots, a crown of rounded leaf clumps and a few hanging vines), ferns, wall vines (wall-mounted curtain), sand dunes, boulders
and desert pillar rocks, the oasis pool (the lane's own water piece: the dungeonkit lake kit is not in this lane's
base), reeds, shrubs and fallen logs. Leaves are two-sided open sheets (kit_shell_*, front + offset back sheet,
because the runtime culls back faces); trunks, rocks and dunes are closed solids.
"""
import math

import numpy as np

from . import gen_ancientkit_core as A
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .genutil import finalize
from .rng import rng

V = "1.0.0"
TAU = math.tau
WATER_Z = -0.25          # oasis water surface below the ground datum (glTF y = -0.25)


def taper_tube(path, radii, sides, role, smooth=True, start=0.0):
    """Closed tube along a 3D polyline with a radius per path point (parallel-transport frames, metric UVs)."""
    T_, N_, B_ = K.frames_along(path)
    rings = []
    for p, n, b, r in zip(path, N_, B_, radii):
        ring = []
        for i in range(sides):
            a = start + TAU * i / sides
            d = np.asarray(n) * math.cos(a) + np.asarray(b) * math.sin(a)
            ring.append(tuple(np.asarray(p) + d * r))
        rings.append(ring)
    return K.loft(rings, role, smooth=smooth)


def curve(p0, p1, bend, n):
    """Points on a quadratic curve from p0 to p1 whose midpoint is pushed by the vector `bend`."""
    p0, p1, bend = np.asarray(p0, float), np.asarray(p1, float), np.asarray(bend, float)
    mid = (p0 + p1) / 2 + bend
    return [tuple((1 - t) ** 2 * p0 + 2 * (1 - t) * t * mid + t * t * p1) for t in np.linspace(0, 1, n)]


def leaf_crown(top, count, length, width, droop, rs, role="foliage", segs=2, tilt=0.0, phase=0.0):
    m = K.Mesh()
    for k in range(count):
        a = phase + TAU * k / count + rs.uniform(-0.12, 0.12)
        ln = length * rs.uniform(0.85, 1.1)
        f = A.frond(top, a, ln, width, droop * rs.uniform(0.85, 1.15), role, segs=segs, fold=0.3)
        m.merge(A.two_sided(f, 0.012))
    return m


# ---------------------------------------------------------------- wild.palm
@register("wild.palm", V, "flora", {
    "style": S.enum("tall", ["tall", "leaning", "young", "twin"]), "height": S.num(6.5, 3.0, 9.0),
}, "Date palm: a gently curved trunk of chevron leaf-base scales tapering to a crown of V-folded two-sided fronds with "
   "a date cluster; leaning = strong lean (oasis edge); young = short with a low crown; twin = two trunks from one root. "
   "Origin at the trunk base.", origin="root")
def palm(P, seed):
    r = rng(seed, "wild.palm", P["style"])
    st = P["style"]
    h = P["height"] if st != "young" else min(P["height"], 3.4)
    specs = []
    if st == "twin":
        specs = [((0.0, 0.0), h, (0.9, 0.3), 5), ((0.35, 0.2), h * 0.78, (-0.6, 0.7), 4)]
    else:
        lean = {"tall": 0.6, "leaning": 2.0, "young": 0.25}[st]
        specs = [((0.0, 0.0), h, (lean, 0.25 * lean), 7 if st != "young" else 6)]
    nodes = []
    trunks = K.Mesh()
    crowns = K.Mesh()
    fruit = K.Mesh()
    for (bx, by), hh, (lx, ly), nf in specs:
        top = (bx + lx, by + ly, hh)
        path = curve((bx, by, 0.0), top, (lx * -0.25, ly * -0.25, 0.0), 5)
        radii = [0.24, 0.19, 0.17, 0.16, 0.18]
        trunks.merge(taper_tube(path, radii, 6, "bark", smooth=True))
        crowns.merge(leaf_crown((top[0], top[1], top[2] - 0.05), nf, 2.5 if st != "young" else 1.7, 0.42, 1.25, r, segs=2,
                                phase=r.uniform(0, TAU)))
        fruit.merge(K.blob(top[0] + 0.05, top[1] - 0.18, top[2] - 0.32, 0.17, 0.15, 0.22, "flower", segs=5, rings=3))
    trunks = A.weld(trunks)
    nodes += [Node("trunk", trunks), Node("crown", crowns, "shell"), Node("dates", fruit)]
    return finalize(nodes, A.grid_meta("free", None, [A.sock("plant", (0, 0, 0), "up")], style=st, height_m=h),
                    center_x=False, center_y=False)


# ---------------------------------------------------------------- wild.tree
@register("wild.tree", V, "flora", {
    "style": S.enum("canopy", ["canopy", "tall", "strangler"]), "height": S.num(9.0, 5.0, 14.0),
}, ("Jungle tree: a straight trunk on four buttress roots under a crown of rounded leaf clumps (a high dome over three "
    "lower clumps) with a few hanging vines; tall = slimmer, higher crown; strangler = roots and trunk wrapped around a "
    "broken stone column. Origin at the trunk base."), origin="root")
def tree(P, seed):
    r = rng(seed, "wild.tree", P["style"])
    st, h = P["style"], P["height"]
    if st == "tall":
        h *= 1.15
    nodes = []
    trunk = A.lathe([(0.0, 0.0), (0.75, 0.0), (0.48, 0.6), (0.36, h * 0.35), (0.3, h * 0.8), (0.0, h * 0.84)], 5, "bark", smooth=True)
    nodes.append(Node("trunk", trunk))
    roots = K.Mesh()
    for k in range(4):
        a = TAU * k / 4 + 0.4
        fin = K.prism([(0.0, 0.0), (1.5, 0.0), (0.25, 1.7), (0.0, 1.9)], -0.08, 0.08, "bark")
        fin.apply(lambda q: q[:, [0, 2, 1]])
        fin = fin.orient_outward()
        fin.rotate_z(a).translate(0.22 * math.cos(a), 0.22 * math.sin(a), 0.0)
        roots.merge(fin)
    nodes.append(Node("buttresses", roots))
    # crown: a high central dome over three lower clumps leaning out and down (a broadleaf fig / kapok crown that reads
    # at 320x240); one flat disc on evenly spaced hanging strands read as a parasol table (CRITIQUE-4, round 21)
    s = 1.0 if st != "tall" else 0.78
    zc = h * (0.84 if st != "tall" else 0.9)
    canopy = K.Mesh()
    canopy.merge(A.rock(0.0, 0.0, zc + 0.45 * s, 2.1 * s, 1.95 * s, 1.5 * s, r, "foliage", segs=7, rings=4, jitter=0.16,
                        flat_bottom=False))
    clumps = []
    for k in range(3):
        a = TAU * k / 3 + 0.5 + r.uniform(-0.25, 0.25)
        cxk, cyk, czk = 1.75 * s * math.cos(a), 1.75 * s * math.sin(a), zc - 0.3 * s + r.uniform(-0.2, 0.2)
        clumps.append((cxk, cyk, czk, a))
        canopy.merge(A.rock(cxk, cyk, czk, 1.45 * s, 1.35 * s, 1.0 * s, r, "foliage", segs=6, rings=3, jitter=0.16,
                            flat_bottom=False))
    nodes.append(Node("canopy", canopy))
    if st != "strangler":
        rim = K.Mesh()
        for cxk, cyk, czk, a in clumps[:2]:
            f = A.frond((cxk + 0.95 * s * math.cos(a), cyk + 0.95 * s * math.sin(a), czk - 0.45 * s), a, 1.4 * s, 0.4, 1.1,
                        "foliage", segs=2, fold=0.25)
            rim.merge(A.two_sided(f, 0.012))
        nodes.append(Node("rim_leaves", rim, "shell"))
    vines = K.Mesh()
    for cxk, cyk, czk, a in clumps[1:]:
        x, y = cxk * 0.85, cyk * 0.85
        ln = r.uniform(1.3, 2.2) * s
        z0 = czk - 0.6 * s
        card = K.Mesh().add([(x - 0.18, y, z0 - ln), (x + 0.18, y, z0 - ln), (x + 0.18, y, z0), (x - 0.18, y, z0)], [(0, 1, 2, 3)],
                            "rope", False, [("n", [(0, 0), (1, 0), (1, ln / 0.6), (0, ln / 0.6)])])
        vines.merge(A.two_sided(card, 0.01))
    nodes.append(Node("vines", vines, "shell"))
    if st == "strangler":
        col = A.lathe([(0.0, 0.0), (0.5, 0.0), (0.46, 2.6), (0.0, 2.7)], 7, "trim", smooth=True)
        col.translate(1.1, -0.9, 0.0)
        nodes.append(Node("column", col))
        wrap = K.Mesh()
        path = [(1.1 + 0.55 * math.cos(t), -0.9 + 0.55 * math.sin(t), 0.3 + 1.6 * t / TAU) for t in np.linspace(0, TAU * 1.1, 7)]
        wrap.merge(K.tube(path, 0.1, 3, "bark", smooth=True))
        nodes.append(Node("roots_wrap", wrap))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("plant", (0, 0, 0), "up")], style=st, height_m=round(h, 2)),
                    center_x=False, center_y=False)


# ---------------------------------------------------------------- wild.fern
@register("wild.fern", V, "flora", {
    "size": S.num(1.2, 0.5, 2.2), "style": S.enum("fan", ["fan", "spray"]),
}, "Fern: a rosette of arching two-sided fronds (fan) or a tall upright spray, rooted in a small leaf-litter mound.",
   origin="floor_center")
def fern(P, seed):
    r = rng(seed, "wild.fern", P["style"])
    s = P["size"]
    fronds = K.Mesh()
    n = 7 if P["style"] == "fan" else 5
    for k in range(n):
        a = TAU * k / n + r.uniform(-0.2, 0.2)
        if P["style"] == "fan":
            f = A.frond((0, 0, 0.08), a, s * r.uniform(0.85, 1.1), s * 0.17, s * 0.55, "foliage", segs=2, fold=0.3)
        else:
            f = A.frond((0, 0, 0.08), a, s * 1.2, s * 0.13, s * 0.15, "foliage", segs=2, fold=0.25)
            f.apply(lambda q: np.column_stack([q[:, 0] * 0.55, q[:, 1] * 0.55, 0.08 + (q[:, 2] - 0.08) + np.hypot(q[:, 0], q[:, 1]) * 1.1]))
        fronds.merge(A.two_sided(f, 0.01))
    mound = A.lathe([(0.0, -0.02), (0.32 * s, -0.02), (0.18 * s, 0.1), (0.0, 0.13)], 6, "dirt", smooth=True)
    return finalize([Node("fronds", fronds, "shell"), Node("mound", mound)], A.grid_meta("free", None, [], style=P["style"]))


# ---------------------------------------------------------------- wild.vines
@register("wild.vines", V, "flora", {
    "width": S.num(3.0, 1.0, 4.0), "drop": S.num(3.2, 1.0, 4.5), "density": S.integer(5, 3, 8),
}, "Hanging vine curtain for a wall top (wall-mounted, origin on the wall face at floor level): leafy strands of uneven "
   "length draped from the top edge and a mossy leaf roll along the coping.", wall_mounted=True, origin="wall_back")
def vines(P, seed):
    r = rng(seed, "wild.vines")
    w, drop, n = P["width"], P["drop"], P["density"]
    top = 4.5
    strands = K.Mesh()
    for k in range(n):
        x = -w / 2 + w * (k + 0.5) / n + r.uniform(-0.12, 0.12)
        ln = drop * r.uniform(0.5, 1.0)
        y = -0.04 - 0.03 * k % 2
        card = K.Mesh().add([(x - 0.17, y, top - ln), (x + 0.17, y, top - ln), (x + 0.17, y, top), (x - 0.17, y, top)], [(0, 1, 2, 3)],
                            "rope", False, [("n", [(0, 0), (1, 0), (1, ln / 0.6), (0, ln / 0.6)])])
        strands.merge(A.two_sided(card, 0.008))
    roll = K.tube([(-w / 2, -0.12, top + 0.02), (0.0, -0.18, top + 0.06), (w / 2, -0.12, top + 0.02)], 0.16, 5, "foliage", smooth=True)
    return Asset([Node("strands", strands, "shell"), Node("roll", roll)],
                 A.grid_meta("wall_face", None, [A.sock("wall", (0, 0, 0), "s")], width_m=w))


# ---------------------------------------------------------------- wild.dune
@register("wild.dune", V, "terrain", {
    "shape": S.enum("mound", ["mound", "crescent", "ridge"]), "size": S.num(9.0, 3.0, 16.0),
    "height": S.num(1.3, 0.4, 3.5),
}, "Sand dune: a soft mound, a crescent dune with a steep slip face on its lee (north) side, or a long wind ridge; "
   "closed solid sunk 0.2 m below the ground datum so its foot meets any ground tile.", origin="room_floor")
def dune(P, seed):
    r = rng(seed, "wild.dune", P["shape"])
    s, h = P["size"], P["height"]
    sh = P["shape"]
    segs, rings = 12, 4
    verts = []
    for j in range(rings + 1):
        t = j / rings
        for i in range(segs):
            a = TAU * i / segs
            jit = r.uniform(0.95, 1.05) if j < rings else 1.0
            rad = s / 2 * (1 - t ** 1.35) * jit
            x, y = rad * math.cos(a), rad * math.sin(a)
            if sh == "ridge":
                x *= 1.9
                y *= 0.45
            if sh == "crescent":
                lee = max(0.0, math.sin(a))          # lee side (north, +y) steep and hollowed
                y = y * (1 - 0.45 * lee * t)
            y += 0.16 * s * t * (0.45 if sh == "ridge" else 1.0)   # crest shifted to the lee
            z = h * (1 - (1 - t) ** 2.4) - 0.2 * (1 - t)
            if sh == "crescent":
                z *= 1 - 0.25 * max(0.0, math.sin(a)) * (1 - t)
            verts.append((x, y, z if j < rings else h))
    faces = []
    for j in range(rings):
        for i in range(segs):
            a, b = j * segs + i, j * segs + (i + 1) % segs
            faces.append((a, b, b + segs, a + segs))
    faces.append(tuple(reversed(range(segs))))
    top = rings * segs
    faces = faces[:-1] + [tuple(reversed(range(segs)))]
    faces.append(tuple(range(top, top + segs)))
    m = K.Mesh().add(verts, faces, "sand", True)
    m = A.weld(m).orient_outward()
    a = Asset([Node("dune", m)], A.grid_meta("free", None, [], shape=sh, height_m=h))
    a.meta["bbox_size_m"] = [round(float(x), 4) for x in np.ptp(np.asarray(m.v), axis=0)]
    return a


# ---------------------------------------------------------------- wild.rock
@register("wild.rock", V, "terrain", {
    "style": S.enum("boulder", ["boulder", "cluster", "pillar", "slab"]), "size": S.num(1.6, 0.5, 4.0),
}, "Rocks: a weathered boulder, a cluster of three, a wind-carved pillar rock (stacked strata lumps with a cap) or a "
   "tilted slab outcrop.", origin="floor_center")
def rock(P, seed):
    r = rng(seed, "wild.rock", P["style"])
    s, st = P["size"], P["style"]
    m = K.Mesh()
    nodes = []
    if st == "boulder":
        m.merge(A.rock(0, 0, s * 0.35, s * 0.6, s * 0.5, s * 0.45, r, "rock", segs=7, rings=4))
    elif st == "cluster":
        for (x, y, k) in ((0, 0, 1.0), (s * 0.75, s * 0.25, 0.6), (-s * 0.5, s * 0.45, 0.45)):
            m.merge(A.rock(x, y, s * 0.3 * k, s * 0.55 * k, s * 0.45 * k, s * 0.4 * k, r, "rock", segs=6, rings=3))
    elif st == "pillar":
        rings, k = [], 7
        prof = ((0.0, 0.62), (0.9, 0.5), (1.9, 0.36), (2.7, 0.42), (3.1, 0.5))
        for j, (zz, rr) in enumerate(prof):
            ring = []
            for i in range(k):
                a = TAU * i / k + 0.2 * j
                q = rr * s * r.uniform(0.85, 1.12)
                ring.append((q * math.cos(a), q * 0.9 * math.sin(a), zz * s * 0.55))
            rings.append(ring)
        m.merge(K.loft(rings, "cliff", smooth=False, cap_roles=("cliff", "rock")))
        m.merge(A.rock(0.1 * s, 0.0, 3.1 * s * 0.55 + 0.12 * s, 0.6 * s, 0.55 * s, 0.25 * s, r, "rock", segs=6, rings=3))
    else:
        sl = A.chamfer_box(0, 0, 0, s * 1.6, s * 0.9, s * 0.35, "rock", bevel=0.08)
        sl.rotate_x(0.32).rotate_z(0.4).translate(0, 0, 0.1)
        m.merge(sl)
        m.merge(A.rock(s * 0.7, -s * 0.3, s * 0.12, s * 0.3, s * 0.25, s * 0.2, r, "rock", segs=5, rings=3))
    nodes.append(Node("rock", m))
    return finalize(nodes, A.grid_meta("free", None, [], style=st))


# ---------------------------------------------------------------- wild.oasis
@register("wild.oasis", V, "terrain", {
    "radius": S.num(4.0, 2.0, 4.2), "style": S.enum("desert", ["desert", "jungle"]),
    "cells": S.integer(3, 2, 3, "square footprint in cells (the ground tile it replaces)"),
}, "Oasis pool (the lane's own water piece): a water disc at WATER_Z = -0.25 m (water role, slow UV scroll, no wobble) "
   "inside a closed bank ring that slopes from the ground datum into the water, with a reed bed and lily pads, on a "
   "square ground skirt that fills its cell block (cells x 4 m) at the datum, so it drops into a gap in the ground "
   "tiles and meets them edge to edge (ground_edge sockets). jungle = an earth-and-moss bank and darker water. Sockets "
   "'shore' on the bank, 'water' at the surface.", origin="terrain_center")
def oasis(P, seed):
    r = rng(seed, "wild.oasis", P["style"])
    R = P["radius"]
    segs = 16                                            # rays at 45 degrees hit the skirt's square corners
    jungle = P["style"] == "jungle"
    bank_role = "dirt" if jungle else "sand"             # the ground tile's role, so bank and skirt match the tiles
    n_c = P["cells"]
    R = min(R, n_c * A.CELL / 2 - 1.75)
    # bank: closed ring, outer rim flush with the ground, inner lip below the water surface
    loop = [(R - 0.6, WATER_Z - 0.09), (R + 1.6, -0.05), (R + 1.6, 0.02), (R + 0.6, 0.06), (R - 0.2, WATER_Z + 0.05)]
    bank = K.lathe_closed(loop, segs, bank_role, smooth=True, rx=1.0, ry=0.82)
    nodes = [Node("bank", bank)]
    # square skirt from the bank's outer rim (ellipse rx = R + 1.6, ry = 0.82 (R + 1.6), top at +0.02) out to the cell
    # block edge at the datum
    half = n_c * A.CELL / 2
    sv, sf = [], []
    for i in range(segs):
        a = TAU * i / segs
        ca, sa = math.cos(a), math.sin(a)
        sv.append(((R + 1.6) * ca, (R + 1.6) * 0.82 * sa, 0.02))
        k = half / max(abs(ca), abs(sa))
        sv.append((k * ca, k * sa, 0.0))
    for i in range(segs):
        j = (i + 1) % segs
        sf.append((2 * i, 2 * i + 1, 2 * j + 1, 2 * j))
    skirt = K.Mesh().add(sv, sf, bank_role, True)          # inner -> outer -> next outer -> next inner: normal +z
    nodes.append(Node("skirt", skirt, "shell"))
    water = K.Mesh()
    ring = [((R - 0.1) * math.cos(TAU * i / segs), (R - 0.1) * 0.82 * math.sin(TAU * i / segs), WATER_Z) for i in range(segs)]
    water.add([(0.0, 0.0, WATER_Z)] + ring, [(0, 1 + i, 1 + (i + 1) % segs) for i in range(segs)], "water", False)
    nodes.append(Node("water", water, "shell"))
    reeds = K.Mesh()
    for k in range(4 if not jungle else 3):
        a = r.uniform(0, TAU)
        x, y = (R - 0.2) * math.cos(a), (R - 0.2) * 0.82 * math.sin(a)
        for j in range(3):
            b = a + j * 2.1
            hh = r.uniform(0.9, 1.5)
            c = K.Mesh().add([(-0.16, 0, WATER_Z), (0.16, 0, WATER_Z), (0.05, 0, WATER_Z + hh)], [(0, 1, 2)], "grass", False,
                             [("n", [(0, 0), (1, 0), (0.5, 1)])])
            c.rotate_z(b).translate(x + 0.15 * math.cos(b), y + 0.15 * math.sin(b), 0.0)
            reeds.merge(A.two_sided(c, 0.008))
    nodes.append(Node("reeds", reeds, "shell"))
    pads = K.Mesh()
    for k in range(5):
        a = r.uniform(0, TAU)
        d = r.uniform(0.3, 0.75) * R
        pads.merge(A.lathe([(0.0, WATER_Z + 0.01), (0.32, WATER_Z + 0.01), (0.32, WATER_Z + 0.04), (0.0, WATER_Z + 0.04)], 6, "foliage",
                           smooth=False, cx=d * math.cos(a), cy=d * 0.82 * math.sin(a)))
    nodes.append(Node("pads", pads))
    a = Asset(nodes, A.grid_meta("cell_block_centre", (n_c, n_c), [
        A.sock("ground_edge", (-half, 0, 0), "w"), A.sock("ground_edge", (half, 0, 0), "e"),
        A.sock("ground_edge", (0, -half, 0), "s"), A.sock("ground_edge", (0, half, 0), "n"),
        A.sock("shore", (0, -(R + 0.6) * 0.82, 0), "s"), A.sock("water", (0, 0, WATER_Z), "up")],
        water_level_m=WATER_Z, radius_m=R, datum_m=0.0))
    allv = np.concatenate([np.asarray(n.mesh.v) for n in a.nodes])
    a.meta["bbox_size_m"] = [round(float(x), 4) for x in np.ptp(allv, axis=0)]
    return a


# ---------------------------------------------------------------- wild.reeds
@register("wild.reeds", V, "flora", {
    "style": S.enum("tuft", ["tuft", "papyrus", "grass"]), "size": S.num(1.0, 0.4, 2.0),
}, "Reeds and grasses: a tuft of blades, tall umbel-topped water reeds (papyrus-like heads, two-sided) or a low dry "
   "grass clump; two-sided blades. Origin at the root.", origin="root")
def reeds(P, seed):
    r = rng(seed, "wild.reeds", P["style"])
    s, st = P["size"], P["style"]
    m = K.Mesh()
    n = {"tuft": 7, "papyrus": 5, "grass": 9}[st]
    for k in range(n):
        a = TAU * k / n + r.uniform(-0.2, 0.2)
        hh = s * r.uniform(0.7, 1.1) * (1.8 if st == "papyrus" else (0.5 if st == "grass" else 1.0))
        lean = r.uniform(0.1, 0.35) * hh
        w = 0.07 if st != "grass" else 0.1
        blade = K.Mesh().add([(-w, 0, 0), (w, 0, 0), (lean + 0.01, 0, hh)], [(0, 1, 2)], "grass", False,
                             [("n", [(0, 0), (1, 0), (0.5, 1)])])
        blade.rotate_z(a).translate(0.12 * s * math.cos(a), 0.12 * s * math.sin(a), 0)
        m.merge(A.two_sided(blade, 0.006))
        if st == "papyrus":
            tip = (0.12 * s * math.cos(a) + lean * math.cos(a), 0.12 * s * math.sin(a) + lean * math.sin(a), hh)
            for j in range(3):
                b = a + TAU * j / 3
                head = A.frond(tip, b, 0.32 * s, 0.07, 0.15, "foliage", segs=1, fold=0.2)
                m.merge(A.two_sided(head, 0.006))
    return finalize([Node("blades", m, "shell")], A.grid_meta("free", None, [], style=st), center_x=False, center_y=False)


# ---------------------------------------------------------------- wild.shrub
@register("wild.shrub", V, "flora", {
    "style": S.enum("scrub", ["scrub", "broadleaf", "flowering"]), "size": S.num(1.2, 0.5, 2.5),
}, "Shrub: a desert scrub of low leaf masses on dry stems, a jungle broadleaf clump of big drooping two-sided leaves, "
   "or a flowering bush (foliage masses dotted with blossom clusters).", origin="floor_center")
def shrub(P, seed):
    r = rng(seed, "wild.shrub", P["style"])
    s, st = P["size"], P["style"]
    nodes = []
    if st == "broadleaf":
        leaves = K.Mesh()
        for k in range(7):
            a = TAU * k / 7 + r.uniform(-0.2, 0.2)
            f = A.frond((0, 0, 0.2 * s), a, s * 1.1, s * 0.32, s * 0.6, "foliage", segs=2, fold=0.2)
            leaves.merge(A.two_sided(f, 0.01))
        nodes.append(Node("leaves", leaves, "shell"))
        nodes.append(Node("stem", A.lathe([(0.0, 0.0), (0.1 * s, 0.0), (0.06 * s, 0.3 * s), (0.0, 0.32 * s)], 5, "bark", smooth=True)))
    else:
        m = K.Mesh()
        for k, (x, y, z, rad) in enumerate(((0, 0, 0.48, 0.58), (0.48, 0.18, 0.34, 0.42), (-0.42, 0.2, 0.32, 0.4))):
            b = A.rock(x * s, y * s, z * s, rad * s, rad * s * 0.9, rad * s * 0.72, r, "foliage", segs=8, rings=4, jitter=0.16,
                       flat_bottom=True)
            m.merge(b)
        nodes.append(Node("leaves", m))
        if st == "flowering":
            fl = K.Mesh()
            for k in range(5):
                a = r.uniform(0, TAU)
                fl.merge(K.blob(0.45 * s * math.cos(a), 0.4 * s * math.sin(a), 0.55 * s + r.uniform(0, 0.2) * s, 0.09 * s, 0.09 * s, 0.07 * s,
                                "flower", segs=5, rings=2))
            nodes.append(Node("blossoms", fl))
    return finalize(nodes, A.grid_meta("free", None, [], style=st))


# ---------------------------------------------------------------- wild.log
@register("wild.log", V, "flora", {
    "style": S.enum("log", ["log", "roots", "stump"]), "length": S.num(4.0, 2.0, 6.0),
}, "Jungle deadwood: a fallen mossy log with a broken end, a tangle of arching surface roots, or a hollow stump.",
   origin="floor_center")
def log(P, seed):
    r = rng(seed, "wild.log", P["style"])
    st, L = P["style"], P["length"]
    nodes = []
    if st == "log":
        path = [(-L / 2, 0.0, 0.32), (-L / 6, 0.15, 0.36), (L / 6, -0.1, 0.34), (L / 2, 0.05, 0.3)]
        nodes.append(Node("log", taper_tube(path, [0.36, 0.34, 0.32, 0.28], 7, "bark", smooth=True)))
        nodes.append(Node("branch", K.tube([(L / 6, -0.1, 0.5), (L / 6 + 0.4, -0.6, 0.95), (L / 6 + 0.5, -0.9, 1.1)], 0.08, 4, "bark")))
    elif st == "roots":
        m = K.Mesh()
        for k in range(4):
            a = TAU * k / 4 + r.uniform(-0.3, 0.3)
            p0 = (0.3 * math.cos(a), 0.3 * math.sin(a), 0.1)
            p1 = (L / 2 * math.cos(a), L / 2 * math.sin(a), -0.05)
            pts = curve(p0, p1, (0, 0, 0.7), 5)
            m.merge(taper_tube(pts, [0.2, 0.17, 0.14, 0.11, 0.08], 5, "bark", smooth=True))
        nodes.append(Node("roots", m))
    else:
        nodes.append(Node("stump", K.lathe_closed([(0.32, 0.0), (0.62, 0.0), (0.5, 0.25), (0.46, 0.9), (0.36, 0.95), (0.3, 0.3)], 7, "bark", smooth=True)))
        nodes.append(Node("rot", A.lathe([(0.0, 0.25), (0.34, 0.25), (0.33, 0.3), (0.0, 0.3)], 7, "dirt", smooth=False)))
    return finalize(nodes, A.grid_meta("free", None, [], style=st))
