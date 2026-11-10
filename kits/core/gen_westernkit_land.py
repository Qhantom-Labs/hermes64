"""WESTERNKIT nature / terrain (wland.*) and sky backdrop (wsky.*) families, theme-agnostic.

Canyon walls are one-sided layered rock faces on the lot line (front toward the canyon floor, a receding top cap so a
high camera sees a mesa top, ends that fade to a shared profile so walls tile); mesas, buttes, arches and hoodoos are
closed lofts of seeded lumpy rings with a hard cap-rock ledge; boulders are faceted blobs; plants are tapered closed
spines and blobs (no camera-facing billboards except palm fronds, which are double-sided cards); the dry riverbed and
ground patches are one-sided terrain shells that settle to the floor datum at the cell edges.

wsky.dome is the inward sky dome (v = elevation, the horizon at v = 0.0875 matches the wk_sky texture), wsky.mesas a
distant ring of butte silhouettes (vista role), wsky.sun a sun / moon disc card.
"""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from . import gen_westernkit_base as B
from .gen_westernkit_town import Parts
from .genutil import finalize
from .rng import rng

V = "1.0.0"


def free(pt, cls_meta=None, **kw):
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], **kw))


def strata_rings(r, levels, k, rx, ry, jitter=0.12, twist=0.0):
    """Rings for a layered rock form: levels = [(z, scale)] bottom -> top; each ring an ellipse of k points with seeded
    radial jitter that is SHARED across a bed (so the beds read as continuous layers)."""
    base = [1.0 + jitter * (r.random() * 2 - 1) for _ in range(k)]
    rings = []
    for li, (z, sc) in enumerate(levels):
        j = [b * (1.0 + 0.01 * (r.random() * 2 - 1)) for b in base]     # tiny per-bed wobble: ledge bands never fold
        ring = []
        for i in range(k):
            a = 2 * math.pi * i / k + twist * li
            ring.append((rx * sc * j[i] * math.cos(a), ry * sc * j[i] * math.sin(a), z))
        rings.append(ring)
    return rings


def bed_roles(levels, cap_from):
    """Roles per loft band: alternating rock / cliff beds, the cap-rock band from index cap_from."""
    out = []
    for i in range(len(levels) - 1):
        out.append("cliff" if i >= cap_from else ("rock" if i % 2 == 0 else "cliff"))
    return out


# ================================================================ canyon walls
@register("wland.canyon_wall", V, "shell", {
    "kind": S.enum("straight", ["straight", "corner", "end", "end_w"]),
    "width": S.num(8.0, 4.0, 16.0), "height": S.num(10.0, 5.0, 16.0),
    "ledges": S.integer(3, 1, 5),
}, "Canyon wall: a one-sided layered red-rock face on the lot line with stepped strata ledges, desert-varnish beds, "
   "a buttressed crest and a receding mesa-top cap; straight runs tile end to end, corner turns 90 degrees inward, "
   "end / end_w slope down to the canyon floor toward the piece's east / west end.", origin="lot_line")
def canyon_wall(P, seed):
    r = rng(seed, "wland.canyon_wall", P["kind"])
    w, h, nl = P["width"], P["height"], P["ledges"]
    kind = P["kind"]
    R = w / 2
    bs = B.bumps(r, 10, (0.05, 0.08), (0.95, 0.9), amp=0.55, size=(0.06, 0.16))
    peaks = [(r.uniform(0.15, 0.85), r.uniform(0.06, 0.16), r.uniform(0.06, 0.14)) for _ in range(3)]
    tiers = sorted(r.uniform(0.2, 0.85) for _ in range(nl))

    def crest(u):
        c = sum(a * math.exp(-((u - cu) / cw) ** 2) for cu, a, cw in peaks) * math.sin(math.pi * u) ** 0.8
        if kind == "end":
            c -= 0.7 * u ** 1.5
        elif kind == "end_w":
            c -= 0.7 * (1.0 - u) ** 1.5
        return 1.0 + c

    def depth(u, v):
        env = math.sin(math.pi * u) ** 0.5
        step = sum(0.45 / (1 + math.exp(-(v - t) * 45)) for t in tiers)
        return 0.15 + env * B.bump_field(bs, u, v) + step + 0.4 * v ** 3

    us = [i / max(4, int(w / 1.0)) for i in range(max(4, int(w / 1.0)) + 1)]
    vs = sorted({0.0, 1.0} | {t + d for t in tiers for d in (-0.02, 0.02)} | {0.5})
    vs = [v for v in vs if 0.0 <= v <= 1.0]

    roles = lambda i, j: "cliff" if (j % 2) else "rock"
    if kind == "corner":
        def fnc(u, v):
            th = math.pi / 2 * u
            d = depth(u, v)
            rad = R + d
            return (-rad * math.cos(th), rad * math.sin(th) - R * 0.0, v * h * crest(u))
        face = B.grid_sheet(us, vs, fnc, roles)
        face.flip()
    else:
        def fns(u, v):
            return (u * w - w / 2, -depth(u, v), v * h * crest(u))
        face = B.grid_sheet(us, vs, fns, roles)
    pt = Parts()
    pt.add("face", face, "shell")
    # mesa-top cap: a lip strip from the crest back 2.5 m (one-sided, facing up)
    cap = K.Mesh()
    for i in range(len(us) - 1):
        for (ua, ub) in ((us[i], us[i + 1]),):
            if kind == "corner":
                th0, th1 = math.pi / 2 * ua, math.pi / 2 * ub
                d0, d1 = depth(ua, 1.0), depth(ub, 1.0)
                z0, z1 = h * crest(ua), h * crest(ub)
                a0 = (-(R + d0) * math.cos(th0), (R + d0) * math.sin(th0), z0)
                a1 = (-(R + d1) * math.cos(th1), (R + d1) * math.sin(th1), z1)
                b0 = (-(R + d0 + 2.5) * math.cos(th0), (R + d0 + 2.5) * math.sin(th0), z0 - 0.05)
                b1 = (-(R + d1 + 2.5) * math.cos(th1), (R + d1 + 2.5) * math.sin(th1), z1 - 0.05)
                q = [a0, b0, b1, a1]
            else:
                x0, x1 = ua * w - w / 2, ub * w - w / 2
                z0, z1 = h * crest(ua), h * crest(ub)
                q = [(x0, -depth(ua, 1.0), z0), (x1, -depth(ub, 1.0), z1), (x1, 2.5, z1 - 0.05), (x0, 2.5, z0 - 0.05)]
            cap.add(q, [(0, 1, 2, 3)], "field", False)
    cap = B.weld(cap)
    # make the cap face up
    Vv = np.asarray(cap.v)
    f0 = cap.f[0]
    n = np.cross(Vv[f0[1]] - Vv[f0[0]], Vv[f0[2]] - Vv[f0[0]])
    if n[2] < 0:
        cap.flip()
    pt.add("cap", cap, "shell")
    socks = [B.sock("cliff_edge", (0.0, 0.0, 0.0), "s", width_m=w)]
    return Asset(pt.nodes(), B.grid_meta("lot_line", [max(1, int(round(w / 4))), 1], socks, kind=kind, height_m=h))


# ================================================================ mesa / butte / arch / hoodoo
@register("wland.mesa", V, "terrain", {
    "width": S.num(24.0, 10.0, 40.0), "height": S.num(10.0, 5.0, 18.0), "depth_ratio": S.num(0.7, 0.4, 1.0),
}, "Free-standing mesa: a broad talus skirt, layered steep flanks with a hard cap-rock ledge and a flat scrubby top; "
   "a closed loft of seeded lumpy rings (beds share their jitter so the strata read as continuous layers).",
   origin="floor_center")
def mesa(P, seed):
    r = rng(seed, "wland.mesa")
    w, h = P["width"], P["height"]
    rx, ry = w / 2, w / 2 * P["depth_ratio"]
    levels = [(0.0, 1.0), (h * 0.18, 0.86), (h * 0.42, 0.78), (h * 0.66, 0.74), (h * 0.84, 0.72), (h * 0.86, 0.75), (h * 0.98, 0.73), (h, 0.7)]
    rings = strata_rings(r, levels, 14, rx, ry, jitter=0.1)
    roles = ["sand", "rock", "cliff", "rock", "cliff", "cliff", "rock"]
    m = K.loft(rings, "rock", smooth=False, roles=roles, cap_roles=("sand", "field"))
    pt = Parts()
    pt.add("mesa", m)
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True))


@register("wland.butte", V, "terrain", {
    "width": S.num(7.0, 3.0, 12.0), "height": S.num(14.0, 6.0, 24.0),
}, "Butte / chimney rock: a narrow tower of layered rock on a talus cone, a slightly overhanging cap rock and a "
   "flat top; the far-silhouette landmark of a canyon.", origin="floor_center")
def butte(P, seed):
    r = rng(seed, "wland.butte")
    w, h = P["width"], P["height"]
    levels = [(0.0, 1.6), (h * 0.14, 1.0), (h * 0.35, 0.82), (h * 0.6, 0.76), (h * 0.82, 0.7), (h * 0.84, 0.82), (h * 0.97, 0.8), (h, 0.74)]
    rings = strata_rings(r, levels, 10, w / 2, w / 2 * 0.85, jitter=0.14, twist=0.08)
    m = K.loft(rings, "rock", smooth=False, roles=["sand", "rock", "cliff", "rock", "cliff", "cliff", "rock"], cap_roles=("sand", "field"))
    pt = Parts()
    pt.add("butte", m)
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True))


@register("wland.arch", V, "terrain", {
    "span": S.num(10.0, 5.0, 16.0), "height": S.num(8.0, 4.0, 12.0), "thickness": S.num(2.2, 1.2, 3.5),
}, "Natural rock arch: two lumpy layered legs joined by a sagging lofted span (a seeded lumpy section swept along "
   "an arch curve); walkable underneath, a postcard landmark.", origin="floor_center")
def arch(P, seed):
    r = rng(seed, "wland.arch")
    sp, h, t = P["span"], P["height"], P["thickness"]
    pt = Parts()
    for sx in (-1, 1):
        lv = [(0.0, 1.35), (h * 0.3, 1.0), (h * 0.62, 0.92), (h * 0.8, 0.95)]
        rings = strata_rings(r, lv, 8, t * 0.95, t * 0.75, jitter=0.15)
        leg = K.loft(rings, "rock", smooth=False, roles=["rock", "cliff", "rock"], cap_roles=("sand", "rock"))
        pt.add("legs", leg.translate(sx * sp / 2, 0.0, 0.0))
    n = 8
    path = []
    for i in range(n + 1):
        a = math.pi * i / n
        path.append((-math.cos(a) * sp / 2, 0.0, h * 0.62 + math.sin(a) * h * 0.34))
    k = 7
    sec_r = [1.0 + 0.18 * (r.random() * 2 - 1) for _ in range(k)]
    sec = [(t * 0.62 * sec_r[i] * math.cos(2 * math.pi * i / k), t * 0.45 * sec_r[i] * math.sin(2 * math.pi * i / k)) for i in range(k)]
    span_m = B.sweep(path, sec, "cliff", cap=True, up=(0.0, 1.0, 0.0))
    pt.add("span", span_m)
    return Asset(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True))


@register("wland.hoodoo", V, "terrain", {
    "count": S.integer(3, 1, 4), "height": S.num(5.0, 2.0, 9.0),
}, "Hoodoos: eroded rock spires with pinched waists (lathe of an irregular profile) wearing hard flat cap stones; "
   "a cluster of one to four.", origin="floor_center")
def hoodoo(P, seed):
    r = rng(seed, "wland.hoodoo")
    pt = Parts()
    for i in range(P["count"]):
        h = P["height"] * (1.0 if i == 0 else r.uniform(0.5, 0.85))
        rb = 0.45 + 0.12 * h / 5
        prof = [(rb * 1.5, 0.0), (rb * 1.1, h * 0.12)]
        z = h * 0.12
        while z < h * 0.85:
            z += h * r.uniform(0.12, 0.2)
            prof.append((rb * r.uniform(0.55, 1.0), min(z, h * 0.86)))
        prof.append((rb * 0.5, h * 0.88))
        a = 2 * math.pi * i / max(1, P["count"]) + r.uniform(-0.4, 0.4)
        d = 0.0 if i == 0 else r.uniform(1.4, 2.6)
        x, y = d * math.cos(a), d * math.sin(a)
        roles = ["sand"] + ["rock" if j % 2 else "cliff" for j in range(len(prof) - 2)]
        pt.add("spires", K.lathe(prof, 7, "rock", smooth=True, roles=roles, start=r.uniform(0, 1)).translate(x, y, 0.0))
        cap = K.prism(K.circle2d(rb * 1.25, 7, start=r.uniform(0, 1)), h * 0.88, h * 0.88 + rb * 0.55, "cliff", role_top="rock")
        pt.add("caps", cap.translate(x, y, 0.0))
    return free(pt)


@register("wland.boulder", V, "furniture_large", {
    "size": S.num(1.4, 0.4, 3.0), "count": S.integer(3, 1, 4),
}, "Desert boulders: faceted rounded rocks (one big, smaller companions) bedded into the sand.", origin="floor_center")
def boulder(P, seed):
    r = rng(seed, "wland.boulder")
    s = P["size"]
    pt = Parts()
    for i in range(P["count"]):
        sc = s * (1.0 if i == 0 else r.uniform(0.35, 0.6))
        a = 2 * math.pi * i / max(1, P["count"]) + r.uniform(-0.5, 0.5)
        d = 0.0 if i == 0 else s * r.uniform(0.9, 1.3)
        pt.add("rocks", B.rock_blob(d * math.cos(a), d * math.sin(a), sc * 0.42, sc, sc * r.uniform(0.7, 0.95), sc * 0.7, r, role="rock",
                                    segs=7, rings=4, jitter=0.16))
    return free(pt)


@register("wland.ledge", V, "terrain", {
    "width": S.num(8.0, 4.0, 16.0), "depth": S.num(4.0, 2.0, 8.0), "height": S.num(2.0, 0.8, 4.0),
}, "Rock shelf: a raised layered rock step (closed loft) with a flat sandy top to climb onto; stacks into terraces.",
   origin="floor_center")
def ledge(P, seed):
    r = rng(seed, "wland.ledge")
    w, d, h = P["width"], P["depth"], P["height"]
    levels = [(0.0, 1.06), (h * 0.5, 1.0), (h * 0.92, 0.98), (h, 0.96)]
    rings = []
    k = 12
    jit = [1.0 + 0.06 * (r.random() * 2 - 1) for _ in range(k)]
    for z, sc in levels:
        ring = []
        for i, (x, y) in enumerate(K.superellipse2d(w / 2, d / 2, k, e=5.0)):
            ring.append((x * sc * jit[i], y * sc * jit[i], z))
        rings.append(ring)
    m = K.loft(rings, "rock", smooth=False, roles=["rock", "cliff", "rock"], cap_roles=("sand", "field"))
    pt = Parts()
    pt.add("ledge", m)
    return free(pt)


@register("wland.riverbed", V, "terrain", {
    "size": S.num(8.0, 4.0, 32.0), "kind": S.enum("straight", ["straight", "bend"]), "stones": S.integer(6, 0, 10),
}, "Dry riverbed (wash): a one-sided terrain block with a sunken sandy channel between sloped cracked-earth banks "
   "that rise back to the floor datum toward the block edges, scattered river stones along the bed; a large block is "
   "a whole canyon floor.", origin="terrain_center")
def riverbed(P, seed):
    r = rng(seed, "wland.riverbed", P["kind"])
    s = P["size"]
    n = max(10, min(14, int(round(s / 2.3))))
    depth = 0.7
    bend = P["kind"] == "bend"

    def centre(t):
        return 0.0 if not bend else (s * 0.32) * math.sin(math.pi * t) * 0.9 - s * 0.0

    def zf(x, y):
        t = (y + s / 2) / s
        dx = x - centre(t)
        w_ = min(s * 0.18, 2.6)
        bed = depth * (1.0 - min(1.0, (abs(dx) / (w_ * 1.9)) ** 2.5))
        edge = min(1.0, min(x + s / 2, s / 2 - x) / (s * 0.12))
        return -max(0.0, bed) * edge

    xs = [-s / 2 + s * i / n for i in range(n + 1)]
    ys = [-s / 2 + s * j / n for j in range(n + 1)]
    m = K.Mesh()
    for j in range(n):
        for i in range(n):
            q = [(xs[i], ys[j], zf(xs[i], ys[j])), (xs[i + 1], ys[j], zf(xs[i + 1], ys[j])), (xs[i + 1], ys[j + 1], zf(xs[i + 1], ys[j + 1])),
                 (xs[i], ys[j + 1], zf(xs[i], ys[j + 1]))]
            zc = sum(p[2] for p in q) / 4
            m.add(q, [(0, 1, 2, 3)], "sand" if zc < -depth * 0.55 else ("dirt" if zc < -0.06 else "field"), False)
    pt = Parts()
    pt.add("ground", B.weld(m), "shell")
    for i in range(P["stones"]):
        t = r.uniform(0.08, 0.92)
        y = -s / 2 + s * t
        x = centre(t) + r.uniform(-0.7, 0.7)
        rr = r.uniform(0.12, 0.3)
        pt.add("stones", B.rock_blob(x, y, zf(x, y) + rr * 0.3, rr, rr * 0.8, rr * 0.5, r, role="rock", segs=5, rings=2, jitter=0.18))
    return Asset(pt.nodes(), B.grid_meta("cell_block_centre", [int(round(s / 4)), int(round(s / 4))], [], kind=P["kind"]))


@register("wland.ground", V, "terrain", {
    "size": S.num(12.0, 4.0, 48.0), "kind": S.enum("flat", ["flat", "dunes", "ruts"]), "relief": S.num(0.35, 0.0, 1.2),
    "road_w": S.num(0.0, 0.0, 16.0, "ruts: road width in metres (0 = 40% of the patch)"),
}, "Desert ground patch: a one-sided terrain sheet of painted sand that settles to the floor datum at its edges; "
   "dunes add soft wind-blown swells, ruts paint a wagon road (path role) across the middle.", origin="terrain_center")
def ground(P, seed):
    r = rng(seed, "wland.ground", P["kind"])
    s = P["size"]
    n = max(4, min(12, int(s / 1.5)))
    amp = P["relief"] * (1.6 if P["kind"] == "dunes" else 0.6)
    bs = B.bumps(r, 6 if P["kind"] == "dunes" else 4, (0.15, 0.15), (0.85, 0.85), amp=1.0, size=(0.15, 0.3))

    def zf(u, v):
        env = math.sin(math.pi * u) ** 0.8 * math.sin(math.pi * v) ** 0.8
        return amp * env * max(-0.3, B.bump_field(bs, u, v))
    m = K.Mesh()
    for j in range(n):
        for i in range(n):
            us_, vs_ = [i / n, (i + 1) / n], [j / n, (j + 1) / n]
            q = [(us_[0] * s - s / 2, vs_[0] * s - s / 2, zf(us_[0], vs_[0])), (us_[1] * s - s / 2, vs_[0] * s - s / 2, zf(us_[1], vs_[0])),
                 (us_[1] * s - s / 2, vs_[1] * s - s / 2, zf(us_[1], vs_[1])), (us_[0] * s - s / 2, vs_[1] * s - s / 2, zf(us_[0], vs_[1]))]
            uc = (i + 0.5) / n
            half = (P["road_w"] / s / 2.0) if P["road_w"] > 0 else 0.2
            role = "path" if (P["kind"] == "ruts" and abs(uc - 0.5) < half) else "sand"
            m.add(q, [(0, 1, 2, 3)], role, False)
    pt = Parts()
    pt.add("ground", B.weld(m), "shell")
    return Asset(pt.nodes(), B.grid_meta("cell_block_centre", [max(1, int(round(s / 4)))] * 2, [], kind=P["kind"]))


@register("wland.slope", V, "terrain", {
    "width": S.num(4.0, 2.0, 8.0), "rise": S.num(2.0, 0.5, 4.0), "run": S.num(4.0, 2.0, 8.0),
}, "Talus ramp: a closed wedge of packed scree rising from the floor to a ledge top (walkable slope), lumpy flanks "
   "and a few loose stones at its foot.", origin="floor_center")
def slope(P, seed):
    r = rng(seed, "wland.slope")
    w, h, L = P["width"], P["rise"], P["run"]
    sec = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, h), (L / 2 - 0.3, h), (-L / 2 + L * 0.15, h * 0.08)]
    m = K.prism(sec, -w / 2, w / 2, "rock", role_top="cliff", role_bottom="cliff")
    A = np.asarray(m.v)
    m.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0], A[:, 1]], axis=1).tolist()]
    m.orient_outward()
    for fi, f in enumerate(m.f):
        Pp = np.asarray([m.v[i] for i in f])
        n = np.cross(Pp[1] - Pp[0], Pp[2] - Pp[0])
        if n[2] > 0.3 * np.linalg.norm(n):
            m.r[fi] = "dirt"
    pt = Parts()
    pt.add("ramp", m)
    for i in range(3):
        x = r.uniform(-w / 2, w / 2)
        rr = r.uniform(0.15, 0.3)
        pt.add("stones", B.rock_blob(x, -L / 2 - 0.3, rr * 0.35, rr, rr * 0.8, rr * 0.55, r, role="rock", segs=5, rings=2))
    return free(pt)


# ================================================================ plants
def spine(base, tip, r0, role, sides=3):
    """Closed tapered spine (pyramid) from base to tip: leaves, blades, spikes."""
    a = np.asarray(base, dtype=float)
    b = np.asarray(tip, dtype=float)
    t = b - a
    t /= np.linalg.norm(t)
    s = np.cross(t, np.array([0.0, 0.0, 1.0]))
    if np.linalg.norm(s) < 1e-6:
        s = np.array([1.0, 0.0, 0.0])
    s /= np.linalg.norm(s)
    u = np.cross(s, t)
    ring = [tuple(a + (s * math.cos(2 * math.pi * k / sides) + u * math.sin(2 * math.pi * k / sides)) * r0) for k in range(sides)]
    verts = ring + [tuple(b)]
    faces = [tuple(reversed(range(sides)))] + [(k, (k + 1) % sides, sides) for k in range(sides)]
    return K.Mesh().add(verts, faces, role, False).orient_outward()


@register("wland.scrub", V, "flora", {
    "size": S.num(0.9, 0.4, 1.6), "clumps": S.integer(4, 2, 6),
}, "Sagebrush / desert scrub: a low mound of lumpy grey-green foliage blobs on twiggy stems, wider than tall.",
   origin="floor_center")
def scrub(P, seed):
    r = rng(seed, "wland.scrub")
    s = P["size"]
    pt = Parts()
    for i in range(P["clumps"]):
        a = 2 * math.pi * i / P["clumps"] + r.uniform(-0.3, 0.3)
        d = s * 0.35 if i else 0.0
        rr = s * r.uniform(0.32, 0.45) * (1.2 if i == 0 else 1.0)
        x, y = d * math.cos(a), d * math.sin(a)
        pt.add("foliage", B.rock_blob(x, y, rr * 0.75, rr, rr * 0.9, rr * 0.62, r, role="foliage", segs=6, rings=3, jitter=0.22))
    for i in range(3):
        a = 2 * math.pi * i / 3
        pt.add("stems", spine((0.0, 0.0, 0.0), (s * 0.4 * math.cos(a), s * 0.4 * math.sin(a), s * 0.35), 0.03, "bark"))
    return free(pt)


@register("wland.yucca", V, "flora", {
    "leaves": S.integer(14, 8, 20), "stalk": S.boolean(True),
}, "Yucca: a rosette of stiff sword leaves (closed tapered spines) radiating from a short trunk, with an optional "
   "tall flower stalk.", origin="floor_center")
def yucca(P, seed):
    r = rng(seed, "wland.yucca")
    pt = Parts()
    pt.add("trunk", K.lathe([(0.12, 0.0), (0.1, 0.35)], 6, "bark", smooth=True))
    for i in range(P["leaves"]):
        a = 2 * math.pi * i / P["leaves"] + r.uniform(-0.15, 0.15)
        el = r.uniform(0.35, 1.25)
        L = r.uniform(0.55, 0.8)
        tip = (L * math.cos(el) * math.cos(a), L * math.cos(el) * math.sin(a), 0.35 + L * math.sin(el))
        pt.add("leaves", spine((0.0, 0.0, 0.32), tip, 0.035, "foliage"))
    if P["stalk"]:
        pt.add("stalk", spine((0.0, 0.0, 0.4), (0.05, 0.0, 1.9), 0.03, "bark"))
        for k in range(4):
            z = 1.35 + 0.13 * k
            pt.add("blooms", K.sphere(0.06 * (1 if k % 2 else -1), 0.0, z, 0.06, 0.06, 0.07, 5, 2, "fabric"))
    return free(pt)


@register("wland.dead_tree", V, "flora", {
    "height": S.num(4.0, 2.0, 7.0), "branches": S.integer(4, 2, 6),
}, "Dead desert tree: a gnarled, leaning bleached trunk (swept tube) with crooked bare branches forking up.",
   origin="floor_center")
def dead_tree(P, seed):
    r = rng(seed, "wland.dead_tree")
    h = P["height"]
    pt = Parts()
    lean = r.uniform(-0.4, 0.4)
    path = [(0.0, 0.0, 0.0), (lean * 0.2, 0.05, h * 0.3), (lean * 0.5, -0.05, h * 0.6), (lean * 0.7, 0.0, h * 0.85)]
    rad = 0.16 * h / 4

    def sec(rr):
        return [(rr * math.cos(2 * math.pi * k / 5), rr * math.sin(2 * math.pi * k / 5)) for k in range(5)]
    rings = []
    for i, p in enumerate(path):
        rr = rad * (1.0 - 0.6 * i / (len(path) - 1)) * (1.4 if i == 0 else 1.0)
        rings.append([(p[0] + x, p[1] + y, p[2]) for x, y in sec(rr)])
    rings.append([(path[-1][0] + lean * 0.1 + x * 0.25, path[-1][1] + y * 0.25, path[-1][2] + h * 0.12) for x, y in sec(rad)])
    trunk = K.loft(rings, "bark", smooth=True)
    pt.add("trunk", trunk)
    for i in range(P["branches"]):
        t = r.uniform(0.4, 0.85)
        k = min(len(path) - 2, int(t * (len(path) - 1)))
        f = t * (len(path) - 1) - k
        base = tuple(path[k][j] + (path[k + 1][j] - path[k][j]) * f for j in range(3))
        a = 2 * math.pi * i / P["branches"] + r.uniform(-0.4, 0.4)
        L = h * r.uniform(0.25, 0.4)
        mid = (base[0] + L * 0.5 * math.cos(a), base[1] + L * 0.5 * math.sin(a), base[2] + L * 0.35)
        tip = (base[0] + L * math.cos(a) * 0.8, base[1] + L * math.sin(a) * 0.8, base[2] + L * 0.85)
        pt.add("branches", B.sweep([base, mid, tip], [(-rad * 0.35, -rad * 0.35), (rad * 0.35, -rad * 0.35), (0.0, rad * 0.4)], "bark"))
    return free(pt)


@register("wland.grass", V, "flora", {
    "blades": S.integer(12, 6, 18), "height": S.num(0.5, 0.25, 0.9),
}, "Dry bunch grass: a tuft of tapered straw blades (closed thin spines) splaying from a small base.",
   origin="floor_center")
def grass(P, seed):
    r = rng(seed, "wland.grass")
    h = P["height"]
    pt = Parts()
    for i in range(P["blades"]):
        a = 2 * math.pi * i / P["blades"] + r.uniform(-0.2, 0.2)
        spread = r.uniform(0.1, 0.45) * h
        pt.add("blades", spine((0.02 * math.cos(a), 0.02 * math.sin(a), 0.0), (spread * math.cos(a), spread * math.sin(a), h * r.uniform(0.7, 1.0)),
                               0.025, "grass"))
    return free(pt)


def palm(pt, x, y, h, r, lean=0.0):
    """Desert fan palm: a ringed, slightly curving trunk with a skirt of dead fronds and a crown of fan fronds (cards)."""
    path = [(x, y, 0.0), (x + lean * 0.3, y, h * 0.4), (x + lean * 0.7, y, h * 0.75), (x + lean, y, h)]
    rr = 0.22
    sec = [(rr * math.cos(2 * math.pi * k / 6), rr * math.sin(2 * math.pi * k / 6)) for k in range(6)]
    pt.add("trunks", B.sweep(path, sec, "bark"))
    top = path[-1]
    pt.add("skirts", K.lathe([(0.32, top[2] - 1.0), (0.42, top[2] - 0.3), (0.2, top[2] + 0.05)], 6, "grass", smooth=True).translate(top[0], top[1], 0.0))
    nf = 9
    for i in range(nf):
        a = 2 * math.pi * i / nf + r.uniform(-0.2, 0.2)
        el = r.uniform(-0.2, 0.55)
        L = r.uniform(1.4, 1.9)
        d = (math.cos(el) * math.cos(a), math.cos(el) * math.sin(a), math.sin(el))
        side = (-math.sin(a), math.cos(a), 0.0)
        base = (top[0] + d[0] * 0.12, top[1] + d[1] * 0.12, top[2] + 0.05 + d[2] * 0.12)
        tip = (base[0] + d[0] * L, base[1] + d[1] * L, base[2] + d[2] * L)
        wf = 0.55
        q = [base, (tip[0] + side[0] * wf, tip[1] + side[1] * wf, tip[2]), (tip[0] - side[0] * wf, tip[1] - side[1] * wf, tip[2])]
        uv = [("n", [(0.5, 0.0), (1.0, 1.0), (0.0, 1.0)])]
        pt.add("fronds", K.Mesh().add(q, [(0, 1, 2)], "foliage", False, uv), "card")
        pt.add("fronds_back", K.Mesh().add(list(reversed(q)), [(0, 1, 2)], "foliage", False, [("n", [(0.0, 1.0), (1.0, 1.0), (0.5, 0.0)])]), "card")


@register("wland.palm", V, "flora", {
    "height": S.num(6.0, 3.0, 9.0),
}, "Desert fan palm: a ringed curving trunk, a shaggy skirt of dead fronds and a crown of fan fronds (two-sided "
   "cards).", origin="floor_center")
def palm_piece(P, seed):
    r = rng(seed, "wland.palm")
    pt = Parts()
    palm(pt, 0.0, 0.0, P["height"], r, lean=r.uniform(-0.5, 0.5))
    return free(pt)


@register("wland.oasis", V, "terrain", {
    "size": S.num(8.0, 5.0, 12.0), "palms": S.integer(2, 0, 3),
}, "Oasis: a sunken pool of still water ringed by rocks and grass tufts, shaded by fan palms; the green surprise "
   "of a canyon floor.", origin="terrain_center")
def oasis(P, seed):
    r = rng(seed, "wland.oasis")
    s = P["size"]
    pt = Parts()
    outline = [(s * 0.32 * (1 + 0.12 * math.sin(3 * a + 1.0)) * math.cos(a), s * 0.25 * (1 + 0.12 * math.sin(2 * a)) * math.sin(a))
               for a in [2 * math.pi * k / 12 for k in range(12)]]
    pt.add("water", K.prism(outline, -0.25, -0.05, "water", role_bottom="sand"))
    bank = [(x * 1.25, y * 1.3) for x, y in outline]
    pt.add("bank", K.prism(bank, -0.3, 0.0, "grass", role_bottom="sand", holes=[outline]))
    for i in range(7):
        a = 2 * math.pi * i / 7 + r.uniform(-0.2, 0.2)
        x, y = s * 0.42 * math.cos(a), s * 0.33 * math.sin(a)
        rr = r.uniform(0.25, 0.55)
        pt.add("rocks", B.rock_blob(x, y, rr * 0.35, rr, rr * 0.8, rr * 0.6, r, role="rock", segs=5, rings=2, jitter=0.18))
    for i in range(P["palms"]):
        a = r.uniform(0, 2 * math.pi)
        palm(pt, s * 0.42 * math.cos(a), s * 0.36 * math.sin(a), r.uniform(4.5, 6.5), r, lean=r.uniform(-0.6, 0.6))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]), ground=False)


# ================================================================ sky
@register("wsky.dome", V, "sky", {
    "radius": S.runtime(S.num(400.0, 20.0, 1800.0, "placement scale (inside the camera far plane)")),
    "segments": S.integer(16, 8, 16), "below_horizon": S.num(0.15, 0.0, 0.3),
}, "Frontier sky dome: inward-facing hemisphere (kit_shell_sky, role sky, u = azimuth, v = elevation; the horizon "
   "sits at v = 0.0875, matching the wk_sky texture's distant mesas and horizon haze). The pack variant paints noon, "
   "golden hour, night or canyon skies onto the same dome.", origin="viewer")
def dome(P, seed):
    R = P["radius"]
    seg = P["segments"]
    below = P["below_horizon"] * R
    e0 = -math.asin(min(0.99, below / R))
    nr = 4
    elev = [e0 + (math.pi / 2 - e0) * j / nr for j in range(nr)]
    vrow = [j / nr for j in range(nr)]
    verts, faces, uvs = [], [], []
    for e in elev:
        verts.extend([(R * math.cos(e) * math.cos(math.tau * i / seg), R * math.cos(e) * math.sin(math.tau * i / seg), R * math.sin(e)) for i in range(seg + 1)])
    W = seg + 1
    for j in range(nr - 1):
        for i in range(seg):
            a = j * W + i
            faces.append((a, a + W, a + W + 1, a + 1))
            uvs.append(("n", [(i / seg, vrow[j]), (i / seg, vrow[j + 1]), ((i + 1) / seg, vrow[j + 1]), ((i + 1) / seg, vrow[j])]))
    apex = len(verts)
    verts.append((0.0, 0.0, R))
    off = (nr - 1) * W
    for i in range(seg):
        faces.append((off + i, apex, off + i + 1))
        uvs.append(("n", [(i / seg, vrow[-1]), ((i + 0.5) / seg, 1.0), ((i + 1) / seg, vrow[-1])]))
    m = K.Mesh().add(verts, faces, "sky", False, uvs)
    return Asset([Node("sky", m, "shell")], {"viewer_origin": True, "horizon_v": round((0 - e0) / (math.pi / 2 - e0), 4)})


@register("wsky.mesas", V, "sky", {
    "radius": S.num(160.0, 40.0, 400.0), "segments": S.integer(40, 24, 48), "height": S.num(0.09, 0.03, 0.3, "silhouette height / radius"),
}, "Distant mesa ring: an inward-facing band whose top edge follows seeded butte and mesa silhouettes (flat tops, "
   "steep shoulders), painted with the vista haze gradient; sits inside the sky dome between the playfield and the "
   "painted horizon so the far skyline has real parallax.", origin="terrain_center")
def mesas(P, seed):
    r = rng(seed, "wsky.mesas")
    R, seg = P["radius"], P["segments"]
    hmax = P["height"] * R
    tops = [0.25] * seg
    for _ in range(9):
        c = r.randrange(seg)
        w = r.randint(2, 6)
        hh = r.uniform(0.4, 1.0)
        for k in range(-w, w + 1):
            i = (c + k) % seg
            f = 1.0 if abs(k) < w - 1 else 0.55
            tops[i] = max(tops[i], hh * f)
    m = K.Mesh()
    for i in range(seg):
        a0, a1 = math.tau * i / seg, math.tau * (i + 1) / seg
        j = (i + 1) % seg
        h0, h1 = tops[i] * hmax, tops[j] * hmax
        q = [(R * math.cos(a1), R * math.sin(a1), -2.0), (R * math.cos(a0), R * math.sin(a0), -2.0), (R * math.cos(a0), R * math.sin(a0), h0),
             (R * math.cos(a1), R * math.sin(a1), h1)]
        m.add(q, [(0, 1, 2, 3)], "vista", False, [("n", [(i / seg, 0.0), ((i + 1) / seg, 0.0), ((i + 1) / seg, tops[i]), (i / seg, tops[j])])])
    # faces must point inward (toward the viewer at the centre)
    Vv = np.asarray(m.v)
    f0 = m.f[0]
    n = np.cross(Vv[f0[1]] - Vv[f0[0]], Vv[f0[2]] - Vv[f0[0]])
    cen = Vv[list(f0)].mean(0)
    if np.dot(n, -cen) < 0:
        m.flip()
    return Asset([Node("mesas", B.weld(m), "shell")], {"viewer_origin": True})


@register("wsky.sun", V, "fx", {
    "size": S.num(3.0, 1.0, 8.0),
}, "Sun / moon disc: a single emissive octagonal card (role light) to hang high in the backdrop, facing the viewer.",
   origin="floor_center")
def sun(P, seed):
    s = P["size"]
    o = [(s / 2 * math.cos(2 * math.pi * k / 8 + math.pi / 8), s / 2 * math.sin(2 * math.pi * k / 8 + math.pi / 8)) for k in range(8)]
    zmin = min(z for _, z in o)
    o = [(x, z - zmin) for x, z in o]
    return Asset([Node("disc", B.card_poly(o, 0.0, "light"), "card")], B.grid_meta("free", None, []))
