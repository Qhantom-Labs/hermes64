"""Flora and rocks (theme-agnostic)."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .genutil import finalize
from .rng import rng, sub_seed

V = "3.0.0"


@register("nature.tree", V, "flora", {
    "kind": S.enum("broadleaf", ["broadleaf", "conifer", "bare", "birch", "palm", "crystal"]),
    "height": S.num(5.0, 1.0, 12.0), "trunk_radius": S.num(0.18, 0.05, 0.6), "canopy": S.num(1.0, 0.5, 1.6),
    "lobes": S.integer(3, 1, 5), "branches": S.integer(4, 2, 6), "cap": S.boolean(False, "snow/moss cap (role 'cap')"),
    "lean": S.num(4.0, 0.0, 15.0),
}, "Tree: broadleaf blobs, stacked conifer tiers, bare branching (cap = snow-laden), birch, palm, crystal (faceted ice trunk, angular branches, glass shards; additive 3.2).")
def tree(P, seed):
    r = rng(seed, "tree")
    h, tr = P["height"], P["trunk_radius"]
    kind = P["kind"]
    lean = math.radians(P["lean"]) * (1 if r.random() > 0.5 else -1)
    trunk_h = h * {"broadleaf": 0.55, "conifer": 0.3, "bare": 0.7, "birch": 0.65, "palm": 0.92, "crystal": 0.62}[kind]
    path = [(0.0, 0.0, -0.05)]
    for i in range(1, 4):
        t = i / 3
        path.append((math.sin(lean) * trunk_h * t * t + (r.random() - 0.5) * 0.05 * t, (r.random() - 0.5) * 0.05 * t, trunk_h * t))
    radii = [tr * (1.0 - 0.45 * i / 3) for i in range(4)]
    trunk = K.tube(path, radii, 6 if kind != "birch" else 5, "bark" if kind != "crystal" else "ice")
    can = K.Mesh()
    cap = K.Mesh()
    top = np.array(path[-1])
    cs = P["canopy"]
    if kind in ("broadleaf", "birch"):
        n = P["lobes"]
        bs = 7 if n <= 3 else 6
        R = h * 0.28 * cs * (0.75 if kind == "birch" else 1.0)
        for i in range(n):
            a = math.tau * i / max(1, n) + r.random()
            off = np.array([math.cos(a), math.sin(a), 0]) * R * (0.45 if n > 1 else 0)
            c = top + off + np.array([0, 0, R * (0.55 + 0.25 * r.random())])
            rr = R * (0.75 + 0.3 * r.random())
            can.merge(K.blob(c[0], c[1], c[2], rr, rr * 0.95, rr * 0.8, "foliage", bs, 4, 0.25))
            if P["cap"]:
                cap.merge(K.blob(c[0], c[1], c[2] + rr * 0.5, rr * 0.72, rr * 0.7, rr * 0.36, "cap", 6, 2, 0.6))
    elif kind == "conifer":
        tiers = 3 + (1 if h > 6 else 0)
        base = trunk_h * 0.6
        R0 = h * 0.24 * cs
        for i in range(tiers):
            t = i / tiers
            z0 = base + (h - base) * t * 0.85
            hh = (h - base) / tiers * 1.6
            rr = R0 * (1 - 0.7 * t)
            can.merge(K.lathe([(0, z0), (rr, z0), (0, z0 + hh)], 8, "foliage", smooth=False, start=r.random()))
            if P["cap"]:
                cap.merge(K.lathe([(0, z0 + hh * 0.38), (rr * 0.66, z0 + hh * 0.38), (0, z0 + hh * 1.02)], 8, "cap", smooth=False))
    elif kind == "bare":
        nb = P["branches"]
        for i in range(nb):
            a = math.tau * i / nb + r.random() * 0.6
            z = trunk_h * (0.45 + 0.5 * i / nb)
            L = h * (0.32 - 0.12 * i / nb) * cs
            p0 = np.array([math.sin(lean) * z * z / trunk_h, 0, z])
            p1 = p0 + np.array([math.cos(a) * L * 0.55, math.sin(a) * L * 0.55, L * 0.45])
            p2 = p1 + np.array([math.cos(a + 0.4) * L * 0.5, math.sin(a + 0.4) * L * 0.5, L * 0.5])
            br = tr * 0.35
            can.merge(K.tube([tuple(p0), tuple(p1), tuple(p2)], [br, br * 0.7, br * 0.35], 4, "bark"))
            if P["cap"]:
                up = np.array([0, 0, br * 0.9])
                # 3-sided ridge of snow/moss along each branch top (14 tris) keeps 6 capped branches < 300
                cap.merge(K.tube([tuple(p0 + up * 1.2), tuple(p1 + up), tuple(p2 + up * 0.7)], [br * 0.7, br * 0.55, br * 0.3], 3, "cap"))
        if P["cap"]:
            cap.merge(K.blob(top[0], top[1], top[2] + tr * 0.4, tr * 0.8, tr * 0.8, tr * 0.5, "cap", 6, 3))
    elif kind == "crystal":
        # faceted landmark tree: ice trunk, branches on a golden-angle spiral (never a planar fan), and a crown
        # of clustered glass shards so the silhouette reads as a crystalline canopy, not bare twigs
        def shard(c, sz, ang, tilt):
            prof = [(0, -sz * 1.1), (sz * 0.62, 0), (0, sz * 1.9)]
            m = K.lathe(prof, 4, "glass", smooth=False, start=ang)
            return m.rotate_x(tilt).rotate_z(ang).translate(c[0], c[1], c[2])
        nb = P["branches"] + 2
        for i in range(nb):
            a = i * 2.39996 + r.random() * 0.25
            t = (i + 0.5) / nb
            z = trunk_h * (0.4 + 0.55 * t)
            L = h * (0.3 - 0.1 * t) * cs
            p0 = np.array([math.sin(lean) * z * z / trunk_h, 0, z])
            p1 = p0 + np.array([math.cos(a) * L * 0.55, math.sin(a) * L * 0.55, L * 0.32])
            p2 = p1 + np.array([math.cos(a + 0.35) * L * 0.35, math.sin(a + 0.35) * L * 0.35, L * 0.48])
            br = tr * 0.42
            can.merge(K.tube([tuple(p0), tuple(p1), tuple(p2)], [br, br * 0.6, br * 0.22], 3, "ice", smooth=False))
            can.merge(shard(p2, L * 0.17, a, 0.35))
            if P["cap"] and i % 2 == 0:
                cap.merge(K.tube([tuple(p0 + np.array([0, 0, br])), tuple(p1 + np.array([0, 0, br * 0.8]))], [br * 0.55, br * 0.35], 3, "cap"))
        # crown: shards on a squashed sphere around the top
        R = h * 0.16 * cs
        for j in range(6):
            a = j * 2.39996
            el = 0.25 + 0.5 * ((j * 0.618) % 1.0)
            c = top + np.array([math.cos(a) * R * math.cos(el), math.sin(a) * R * math.cos(el), R * 0.55 * math.sin(el) + R * 0.35])
            can.merge(shard(c, h * (0.05 + 0.02 * (j % 3)), a, 0.45 * math.cos(el)))
        can.merge(shard(top + np.array([0, 0, R * 1.1]), h * 0.08, 0.0, 0.0))
    else:  # palm
        n = max(4, P["lobes"] + 3)
        for i in range(n):
            a = math.tau * i / n + r.random() * 0.3
            L = h * 0.35 * cs
            pts = [tuple(top + np.array([0, 0, 0.05])),
                   tuple(top + np.array([math.cos(a) * L * 0.5, math.sin(a) * L * 0.5, L * 0.2])),
                   tuple(top + np.array([math.cos(a) * L, math.sin(a) * L, -L * 0.15]))]
            can.merge(K.tube(pts, [0.06 * L, 0.12 * L, 0.02 * L], 4, "foliage", ry=[0.02 * L, 0.03 * L, 0.01 * L]))
    return finalize([Node("trunk", trunk), Node("canopy", can), Node("cap", cap)], {"kind": kind, "height_m": round(h, 3)})


@register("nature.bush", V, "flora", {
    "lobes": S.integer(3, 1, 5), "size": S.num(0.8, 0.2, 2.5), "flowers": S.integer(0, 0, 6), "cap": S.boolean(False),
    "flatness": S.num(0.3, 0.0, 0.7),
}, "Bush/shrub of overlapping blobs; optional flower heads (role 'flower') and cap (snow/moss).")
def bush(P, seed):
    r = rng(seed, "bush")
    s = P["size"]
    can, cap, fl = K.Mesh(), K.Mesh(), K.Mesh()
    n = P["lobes"]
    blobs = []
    for i in range(n):
        a = math.tau * i / n + r.random()
        d = s * 0.28 * (1 if n > 1 else 0)
        rr = s * (0.32 + 0.12 * r.random())
        c = (math.cos(a) * d, math.sin(a) * d, rr * (1 - P["flatness"]) * 0.9)
        blobs.append((c, rr))
        can.merge(K.blob(c[0], c[1], c[2], rr, rr, rr * (1 - P["flatness"]), "foliage", 6, 4, 0.4))
        if P["cap"]:
            cap.merge(K.blob(c[0], c[1], c[2] + rr * (1 - P["flatness"]) * 0.6, rr * 0.7, rr * 0.7, rr * 0.3, "cap", 5, 2, 0.6))
    for i in range(P["flowers"]):
        c, rr = blobs[i % n]
        a = r.random() * math.tau
        el = 0.3 + r.random() * 0.9
        p = (c[0] + math.cos(a) * math.cos(el) * rr * 0.98, c[1] + math.sin(a) * math.cos(el) * rr * 0.98,
             c[2] + math.sin(el) * rr * (1 - P["flatness"]) * 0.98)
        fl.merge(K.blob(p[0], p[1], p[2], s * 0.05, s * 0.05, s * 0.04, "flower", 4, 2))
    return finalize([Node("bush", can), Node("cap", cap), Node("flowers", fl)])


@register("nature.rock", V, "flora", {
    "size": S.num(1.0, 0.2, 4.0), "roughness": S.num(0.4, 0.0, 1.0), "flatness": S.num(0.3, 0.0, 0.8),
    "count": S.integer(1, 1, 4), "role": S.enum("rock", ["rock", "ice", "stone", "snow"]), "cap": S.boolean(False),
}, "Rock or cluster: star-shaped noise-displaced spheres (never self-intersecting), sunk into the ground; optional cap.")
def rock(P, seed):
    r = rng(seed, "rock")
    m, cap = K.Mesh(), K.Mesh()
    n = P["count"]
    for i in range(n):
        s = P["size"] * (1.0 if i == 0 else 0.35 + 0.35 * r.random())
        a = r.random() * math.tau
        d = 0.0 if i == 0 else P["size"] * (0.55 + 0.2 * r.random())
        cx, cy = math.cos(a) * d, math.sin(a) * d
        sph = K.sphere(0, 0, 0, 1, 1, 1, 8 if i == 0 else 6, 5 if i == 0 else 4, P["role"], smooth=False, start=r.random())
        rs = np.random.default_rng(sub_seed("rock", seed, i))
        rough = P["roughness"]
        k = 1.0 - P["flatness"]
        sc = 1.0 + rough * 0.35 * (rs.random(len(sph.v)) - 0.5)
        sph.apply(lambda v: (v * sc[:, None]) * np.array([s * 0.55 * (1 + 0.3 * rough), s * 0.5, s * 0.45 * k]))
        lo = min(p[2] for p in sph.v)
        sph.translate(cx, cy, -lo - s * 0.12 * k)
        m.merge(sph)
        if P["cap"]:
            hi = max(p[2] for p in sph.v)
            cap.merge(K.blob(cx, cy, hi - s * 0.08, s * 0.33, s * 0.3, s * 0.12, "cap", 5, 2, 0.7))
    return finalize([Node("rock", m), Node("cap", cap)])


@register("nature.grass_tuft", V, "flora", {
    "blades": S.integer(7, 3, 12), "height": S.num(0.35, 0.08, 1.2), "spread": S.num(0.25, 0.05, 0.8),
    "flowers": S.integer(0, 0, 4), "role": S.enum("grass", ["grass", "foliage", "snow", "sand", "ice"]),
}, "Grass tuft: solid 3-sided blades (closed pyramids) with optional flower heads.")
def grass_tuft(P, seed):
    r = rng(seed, "grass")
    out, fl = K.Mesh(), K.Mesh()
    for i in range(P["blades"]):
        a = r.random() * math.tau
        d = r.random() * P["spread"] * 0.5
        bx, by = math.cos(a) * d, math.sin(a) * d
        hh = P["height"] * (0.6 + 0.4 * r.random())
        lean = r.random() * 0.4
        tx, ty = bx + math.cos(a) * hh * lean, by + math.sin(a) * hh * lean
        w = 0.025 + 0.02 * r.random()
        base = [(bx + w * math.cos(a + k * math.tau / 3), by + w * math.sin(a + k * math.tau / 3), -0.01) for k in range(3)]
        blade = K.Mesh().add(base + [(tx, ty, hh)], [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)], P["role"])
        out.merge(blade.orient_outward())
        if i < P["flowers"]:
            fl.merge(K.blob(tx, ty, hh + 0.02, 0.035, 0.035, 0.03, "flower", 5, 3))
    return finalize([Node("grass", out), Node("flowers", fl)])
