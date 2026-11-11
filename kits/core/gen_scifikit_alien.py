"""SCIFIKIT alien flora / rock / crystal (alien.*): crystal clusters, a crystal spire, cap trees, glow-bulb plants,
fan fronds, tendril corals, alien grass, faceted boulders, a natural rock arch, rock spires (hoodoos) and a geode.

Original strange-world shapes in the N64-era look: low-sided lathes and lofts with tapered, leaning forms; crystal
tips and spore lights use emissive roles (light / flower), stalks and rocks use painted organic / strata textures.
Every piece is deterministic from (params, seed); parts that could touch are separate nodes (no self-intersection).
Blender space: +Z up. Origin floor_center: footprint centred, lowest point on the ground."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from . import sfkit as F
from .asset import Asset, Node, register

V = "1.0.0"


def _asset(nodes, meta, ao=0.3, reach=0.8, ground=True):
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    lo = np.min([np.asarray(n.mesh.v).min(0) for n in nodes], axis=0)
    hi = np.max([np.asarray(n.mesh.v).max(0) for n in nodes], axis=0)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for n in nodes:
        n.mesh.translate(-cx, -cy, -lo[2])
    F.bake_ao(nodes, amount=ao, reach=reach, ground=ground)
    meta = dict(meta)
    meta["station_grid"] = {"anchor": "free"}
    meta["bbox_size_m"] = [round(float(x), 4) for x in (hi - lo)]
    return Asset(nodes, meta)


def _rng(seed, tag):
    return np.random.default_rng((abs(hash_tag(tag)) + 7919 * int(seed)) % (2 ** 32))


def hash_tag(tag):
    h = 2166136261
    for ch in tag:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def crystal(r, h, role="ice", tip="light", segs=6, tip_frac=0.72):
    """One faceted crystal: hexagonal prism with a pointed glowing tip (closed lathe, poles at both ends)."""
    return F.lathe([(0.0, 0.0), (r, 0.0), (r * 0.92, h * tip_frac), (0.0, h)], segs, role, smooth=False,
                   roles=[role, role, tip], start=math.pi / 6)


def rock_blob(rx, ry, rz, rs, segs=7, rings=4, jitter=0.18, role="rock", flat_bottom=True):
    """Faceted boulder: a low sphere with deterministic radial jitter (closed, convex-ish), flat-ish underside."""
    m = K.sphere(0.0, 0.0, 0.0, rx, ry, rz, segs, rings, role, False)
    A = np.asarray(m.v, dtype=float)
    k = 1.0 + jitter * (rs.random(len(A)) - 0.5) * 2.0
    # keep the two poles on the axis so the fans stay valid
    k[np.abs(A[:, 0]) + np.abs(A[:, 1]) < 1e-9] = 1.0
    A = A * k[:, None]
    if flat_bottom:
        A[:, 2] = np.maximum(A[:, 2], -rz * 0.55)
    m.v = [tuple(p) for p in A.tolist()]
    return m.orient_outward()


# ------------------------------------------------------------------ crystal cluster
@register("alien.crystal", V, "flora", {
    "count": S.integer(6, 3, 8, "crystals in the cluster"),
    "height": S.num(1.6, 0.6, 3.0, "tallest crystal"),
    "spread": S.num(0.55, 0.2, 1.2, "lean / spread of the outer crystals"),
}, "Crystal cluster: faceted hexagonal crystals with glowing tips leaning out of a low basalt foot; every crystal is "
   "its own node.", origin="floor_center")
def crystal_cluster(P, seed):
    rs = _rng(seed, "crystal")
    n, H, sp = P["count"], P["height"], P["spread"]
    nodes = [Node("foot", rock_blob(0.75 + 0.25 * sp, 0.65 + 0.2 * sp, 0.3, rs, segs=6, rings=3, jitter=0.15))]
    nodes[0].mesh.translate(0.0, 0.0, 0.08)
    for i in range(n):
        if i == 0:
            r, h, tilt, az, off = 0.24, H, 0.06, 0.0, 0.0
        else:
            az = math.tau * (i - 1) / (n - 1) + rs.random() * 0.5
            r = 0.1 + 0.1 * rs.random()
            h = H * (0.35 + 0.45 * rs.random())
            tilt = sp * (0.6 + 0.5 * rs.random())
            off = 0.18 + 0.2 * rs.random()
        c = crystal(r, h)
        c.rotate_y(tilt).rotate_z(az).translate(off * math.cos(az), off * math.sin(az), 0.14)
        nodes.append(Node("crystal_%d" % i, c))
    return _asset(nodes, {"count": n, "emitter": "crystal_glow"}, ao=0.25, reach=0.5)


# ------------------------------------------------------------------ spire
@register("alien.spire", V, "structure", {
    "height": S.num(5.5, 3.0, 8.0, "spire height"),
    "satellites": S.integer(3, 0, 4, "small crystals at the foot"),
}, "Crystal spire: a tall leaning six-sided monolith crystal with a glowing crown band and tip, small satellite "
   "crystals and a split basalt foot. A landmark for alien regions.", origin="floor_center")
def spire(P, seed):
    rs = _rng(seed, "spire")
    H = P["height"]
    body = F.lathe([(0.0, 0.0), (0.62, 0.0), (0.56, H * 0.55), (0.42, H * 0.78), (0.36, H * 0.84), (0.0, H)], 6, "ice",
                   smooth=False, start=math.pi / 6, roles=["ice", "ice", "ice", "light", "light"])
    body.rotate_y(0.08).translate(0.0, 0.0, 0.18)
    nodes = [Node("spire", body), Node("foot", rock_blob(1.3, 1.1, 0.5, rs, segs=7, rings=4, jitter=0.2))]
    nodes[1].mesh.translate(0.0, 0.0, 0.16)
    for i in range(P["satellites"]):
        az = math.tau * i / max(1, P["satellites"]) + 0.6
        c = crystal(0.14 + 0.06 * rs.random(), 0.8 + 0.8 * rs.random())
        c.rotate_y(0.5 + 0.3 * rs.random()).rotate_z(az).translate(0.85 * math.cos(az), 0.85 * math.sin(az), 0.2)
        nodes.append(Node("satellite_%d" % i, c))
    return _asset(nodes, {"emitter": "spire_crown"}, ao=0.25, reach=1.0)


# ------------------------------------------------------------------ cap tree
@register("alien.cap_tree", V, "flora", {
    "caps": S.integer(1, 1, 3, "umbrella caps (each on its own stalk)"),
    "height": S.num(3.6, 1.8, 6.0, "tallest stalk"),
}, "Cap tree: curving tapered stalks carrying wide umbrella caps with gilled undersides and glowing spots (cap role), "
   "a ring of root knuckles at the base.", origin="floor_center")
def cap_tree(P, seed):
    rs = _rng(seed, "cap_tree")
    H = P["height"]
    nodes = []
    for i in range(P["caps"]):
        h = H * (1.0 if i == 0 else 0.55 + 0.25 * rs.random())
        az = rs.random() * math.tau if i else 0.0
        lean = 0.0 if i == 0 else 0.7
        bx, by = (0.0, 0.0) if i == 0 else (0.35 * math.cos(az), 0.35 * math.sin(az))
        path = []
        for j in range(4):
            t = j / 3
            bend = math.sin(t * math.pi * 0.8) * (0.35 + lean * 0.5)
            path.append((bx + bend * math.cos(az + 0.8), by + bend * math.sin(az + 0.8), t * h))
        radii = [0.16 - 0.02 * i - 0.08 * (j / 3) for j in range(4)]
        nodes.append(Node("stalk_%d" % i, F.tube(path, radii, 5, "bark", smooth=True)))
        R = h * 0.36 + 0.3
        tx, ty, tz = path[-1]
        cap = F.lathe([(0.0, 0.3), (R * 0.6, 0.2), (R, -0.06), (R * 0.4, -0.08), (0.0, -0.02)], 6 if P["caps"] > 2 else 7,
                      "cap", smooth=True, roles=["cap", "cap", "foliage", "foliage"], start=0.3 * i)
        cap.rotate_x(0.12 * (i % 2)).translate(tx, ty, tz + 0.02)
        nodes.append(Node("cap_%d" % i, cap))
    roots = []
    nr = 3 if P["caps"] > 2 else 4
    for k in range(nr):
        a = math.tau * k / nr + 0.3
        roots.append(F.tube([(0.08 * math.cos(a), 0.08 * math.sin(a), 0.35), (0.34 * math.cos(a), 0.34 * math.sin(a), 0.08),
                             (0.46 * math.cos(a), 0.46 * math.sin(a), 0.0)], [0.07, 0.05, 0.03], 3, "bark", smooth=True))
    nodes.append(Node("roots", F.merged(*roots)))
    return _asset(nodes, {"caps": P["caps"], "emitter": "cap_spots"}, ao=0.28, reach=0.9)


# ------------------------------------------------------------------ glow bulbs
@register("alien.bulb", V, "flora", {
    "bulbs": S.integer(3, 2, 5, "glowing bulbs"),
    "height": S.num(1.3, 0.6, 2.2, "tallest bulb stem"),
}, "Glow-bulb plant: curved stems ending in round glowing bulbs (light role) over a rosette of broad lens leaves.",
   origin="floor_center")
def bulb(P, seed):
    rs = _rng(seed, "bulb")
    H = P["height"]
    nodes = []
    for i in range(P["bulbs"]):
        az = math.tau * i / P["bulbs"] + rs.random() * 0.4
        h = H * (0.55 + 0.45 * rs.random()) if i else H
        lean = 0.15 + 0.35 * rs.random()
        top = (lean * math.cos(az), lean * math.sin(az), h)
        nodes.append(Node("stem_%d" % i, F.tube([(0.05 * math.cos(az), 0.05 * math.sin(az), 0.0),
                                                 (top[0] * 0.3, top[1] * 0.3, h * 0.5), top], [0.04, 0.03, 0.025], 3, "bark")))
        r = 0.13 + 0.07 * rs.random()
        nodes.append(Node("bulb_%d" % i, K.sphere(top[0], top[1], top[2] + r * 0.8, r, r, r * 1.15, 7, 4, "light", True)))
    leaves = []
    for k in range(4):
        a = math.tau * k / 4 + 0.4
        c, s = math.cos(a), math.sin(a)
        path = [(0.05 * c, 0.05 * s, 0.02), (0.35 * c, 0.35 * s, 0.14), (0.62 * c, 0.62 * s, 0.06)]
        leaves.append(F.sweep(path, [(-0.012, 0.0), (0.0, -0.11), (0.012, 0.0), (0.0, 0.11)], "foliage", smooth=False))
    nodes.append(Node("leaves", F.merged(*leaves)))
    return _asset(nodes, {"emitter": "bulb_glow"}, ao=0.22, reach=0.5)


# ------------------------------------------------------------------ fan fronds
@register("alien.frond", V, "flora", {
    "blades": S.integer(6, 4, 8, "blade leaves"),
    "height": S.num(1.8, 0.8, 3.0, "blade reach"),
}, "Fan frond: long curved blade leaves (diamond-section sweeps) fanning out of a bulbous core, teal with spore-lit "
   "veins (foliage role).", origin="floor_center")
def frond(P, seed):
    rs = _rng(seed, "frond")
    H = P["height"]
    blades = []
    for i in range(P["blades"]):
        a = math.tau * i / P["blades"] + rs.random() * 0.3
        c, s = math.cos(a), math.sin(a)
        reach = H * (0.6 + 0.4 * rs.random())
        path = [(0.06 * c, 0.06 * s, 0.25), (0.25 * reach * c, 0.25 * reach * s, 0.75 * reach),
                (0.55 * reach * c, 0.55 * reach * s, 0.95 * reach), (0.8 * reach * c, 0.8 * reach * s, 0.7 * reach)]
        blades.append(Node("blade_%d" % i, F.sweep(path, [(-0.02, 0.0), (0.0, -0.13), (0.02, 0.0), (0.0, 0.13)], "foliage",
                                                   smooth=False)))
    core = F.lathe([(0.0, 0.0), (0.22, 0.0), (0.26, 0.16), (0.12, 0.36), (0.0, 0.4)], 6, "bark", smooth=True)
    return _asset(blades + [Node("core", core)], {}, ao=0.22, reach=0.6)


# ------------------------------------------------------------------ tendril coral
@register("alien.tendril", V, "flora", {
    "tubes": S.integer(6, 3, 8, "tubes in the colony"),
    "height": S.num(1.4, 0.6, 2.6, "tallest tube"),
}, "Tendril coral: a colony of leaning lathed tubes with flared glowing mouths (light role rims), magenta-coral skin "
   "(cap role).", origin="floor_center")
def tendril(P, seed):
    rs = _rng(seed, "tendril")
    H = P["height"]
    nodes = []
    for i in range(P["tubes"]):
        a = math.tau * i / P["tubes"] + rs.random() * 0.5
        d = 0.0 if i == 0 else 0.22 + 0.2 * rs.random()
        h = H if i == 0 else H * (0.4 + 0.5 * rs.random())
        r = 0.09 + 0.05 * rs.random()
        t = F.lathe([(0.0, 0.0), (r, 0.0), (r * 0.8, h * 0.7), (r * 1.6, h), (0.0, h - 0.03)], 5, "cap", smooth=True,
                    roles=["cap", "cap", "cap", "light"])
        t.rotate_y(0.0 if i == 0 else 0.25 + 0.3 * rs.random()).rotate_z(a).translate(d * math.cos(a), d * math.sin(a), 0.04)
        nodes.append(Node("tube_%d" % i, t))
    return _asset(nodes, {"emitter": "tendril_mouths"}, ao=0.25, reach=0.5)


# ------------------------------------------------------------------ alien grass
@register("alien.grass", V, "flora", {
    "blades": S.integer(12, 6, 16, "blades in the clump"),
    "height": S.num(0.9, 0.4, 1.6, "blade height"),
}, "Alien grass clump: thin twisting three-sided blades leaning out of a tuft, tips spore-lit (flower role).",
   origin="floor_center")
def grass(P, seed):
    rs = _rng(seed, "grass")
    H = P["height"]
    nodes = []
    for i in range(P["blades"]):
        a = rs.random() * math.tau
        d = 0.05 + 0.25 * rs.random()
        h = H * (0.5 + 0.5 * rs.random())
        lean = 0.2 + 0.4 * rs.random()
        x0, y0 = d * math.cos(a), d * math.sin(a)
        path = [(x0, y0, 0.0), (x0 + lean * 0.3 * math.cos(a), y0 + lean * 0.3 * math.sin(a), h * 0.55),
                (x0 + lean * math.cos(a), y0 + lean * math.sin(a), h)]
        b = F.tube(path, [0.03, 0.02, 0.004], 3, "grass", smooth=False)
        nb = len(b.f)
        b.r = ["grass"] * (nb - 4) + ["flower"] * 3 + ["grass"] if nb > 4 else b.r
        nodes.append(Node("blade_%d" % i, b))
    return _asset(nodes, {}, ao=0.15, reach=0.3)


# ------------------------------------------------------------------ boulder
BOULDERS = {"medium": (1.1, 0.9, 0.7), "big": (2.2, 1.7, 1.3), "slab": (1.8, 1.2, 0.35)}


@register("alien.boulder", V, "structure", {
    "size": S.enum("medium", list(BOULDERS), "medium (2 m), big (4 m) or a flat slab"),
}, "Faceted alien boulder: a jittered low sphere in violet basalt strata (rock role), flattened underside.",
   origin="floor_center")
def boulder(P, seed):
    rs = _rng(seed, "boulder_" + P["size"])
    rx, ry, rz = BOULDERS[P["size"]]
    return _asset([Node("rock", rock_blob(rx, ry, rz, rs, segs=8, rings=5, jitter=0.16))], {"size": P["size"]}, ao=0.3,
                  reach=1.0)


# ------------------------------------------------------------------ rock arch
@register("alien.arch", V, "structure", {
    "span": S.num(6.0, 4.0, 9.0, "inner span between the legs"),
    "height": S.num(4.5, 3.0, 6.5, "arch crown height"),
}, "Natural rock arch: two leaning eroded legs and a sagging octagonal span swept along an arc, in strata rock "
   "(cliff role). A landmark gateway for alien regions.", origin="floor_center")
def arch(P, seed):
    rs = _rng(seed, "arch")
    sp, H = P["span"], P["height"]
    sec = [(0.75 * math.cos(a), 0.55 * math.sin(a)) for a in [math.tau * i / 7 for i in range(7)]]
    path = []
    k = 9
    for i in range(k + 1):
        t = i / k
        ang = math.pi * t
        x = -(sp / 2 + 0.7) * math.cos(ang)
        z = 0.2 + (H - 0.2) * math.sin(ang) ** 0.75
        path.append((x, 0.12 * math.sin(ang * 2.0), z))
    span = F.sweep(path, sec, "cliff", smooth=False)
    A = np.asarray(span.v)
    A = A + (rs.random(A.shape) - 0.5) * 0.12
    span.v = [tuple(p) for p in A.tolist()]
    legs = []
    for sx in (-1, 1):
        lg = F.loft_levels(F.ngon(1.0, 7), [(0.0, 1.25, 1.0, sx * (sp / 2 + 0.75), 0.0), (1.2, 1.0, 0.85, sx * (sp / 2 + 0.7), 0.05),
                                            (2.2, 0.8, 0.7, sx * (sp / 2 + 0.72), 0.0)], "cliff")
        legs.append(Node("leg_%s" % ("w" if sx < 0 else "e"), lg))
    return _asset([Node("span", span.orient_outward())] + legs, {}, ao=0.3, reach=1.6)


# ------------------------------------------------------------------ rock spire (hoodoo)
@register("alien.rock_spire", V, "structure", {
    "height": S.num(4.0, 2.0, 7.0, "spire height"),
    "tiers": S.integer(3, 2, 4, "eroded tiers"),
}, "Rock spire (hoodoo): stacked eroded tiers narrowing upward with pinched waists and a wide balanced cap rock "
   "(rock role).", origin="floor_center")
def rock_spire(P, seed):
    rs = _rng(seed, "rock_spire")
    H, n = P["height"], P["tiers"]
    lv = []
    z = 0.0
    for i in range(n):
        th = (H - 0.6) / n
        w0 = 1.0 - 0.18 * i
        lv += [(z, w0, w0 * 0.9, 0.04 * rs.random(), 0.04 * rs.random()), (z + th * 0.6, w0 * 0.72, w0 * 0.66),
               (z + th, w0 * 0.82, w0 * 0.74)]
        z += th
    lv = [l for j, l in enumerate(lv) if j == 0 or l[0] > lv[j - 1][0] + 1e-6]
    body = F.loft_levels(F.ngon(0.8, 7), lv, "rock")
    cap = rock_blob(0.95, 0.85, 0.36, rs, segs=7, rings=3, jitter=0.14)
    cap.translate(0.06, 0.0, z + 0.25)
    return _asset([Node("tiers", body), Node("cap_rock", cap)], {}, ao=0.3, reach=1.0)


# ------------------------------------------------------------------ geode
@register("alien.geode", V, "furniture_large", {
    "radius": S.num(1.0, 0.6, 1.6, "geode radius"),
}, "Split geode: a half-buried faceted rock bowl (closed thick shell, rock outside, crystal-lined inside) with glowing "
   "crystal points standing in its hollow.", origin="floor_center")
def geode(P, seed):
    rs = _rng(seed, "geode")
    R = P["radius"]
    loop = [(R * 0.4, 0.0), (R, 0.15), (R * 1.02, R * 0.55), (R * 0.82, R * 0.75), (R * 0.7, R * 0.58), (R * 0.62, R * 0.25),
            (R * 0.3, R * 0.12)]
    shell = K.lathe_closed(loop, 8, "rock", False, roles=["rock", "rock", "rock", "ice", "ice", "ice", "ice"])
    floor = F.lathe([(0.0, 0.0), (R * 0.42, 0.0), (R * 0.32, R * 0.13), (0.0, R * 0.14)], 8, "ice", smooth=False)
    nodes = [Node("shell", shell), Node("floor", floor)]
    for i in range(4):
        a = math.tau * i / 4 + 0.4
        c = crystal(0.07 + 0.04 * rs.random(), R * (0.35 + 0.25 * rs.random()))
        c.rotate_y(0.35).rotate_z(a + math.pi).translate(R * 0.42 * math.cos(a), R * 0.42 * math.sin(a), R * 0.16)
        nodes.append(Node("point_%d" % i, c))
    return _asset(nodes, {"emitter": "geode_glow"}, ao=0.3, reach=0.7)
