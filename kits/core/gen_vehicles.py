"""Vehicles and boats (theme-agnostic)."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .genutil import finalize, post

V = "3.0.0"
HULL = ["hull", "hull_alt", "wood", "metal", "body", "body_alt"]


def capped_loft(rings2d, ys, role, cap_role=None, smooth=False, mirror_from=None):
    """Loft closed (x, z) loops (possibly concave) placed at y positions; ends capped with our own
    tessellation so concave caps are explicit triangles. Returns a closed solid.
    mirror_from=m: loop positions >= m are a mirrored copy of the outer skin (thick-walled shell whose
    inner loop runs backwards). Their side quads are split along the mirrored diagonal so the inner
    skin's triangles are the image of the outer skin's (fixed-diagonal quad splits would cross
    between thin, strongly twisted sections)."""
    rings = [[(x, y, z) for x, z in r] for r, y in zip(rings2d, ys)]
    m = K.loft(rings, role, smooth=smooth, cap0=False, cap1=False)
    k = len(rings2d[0])
    if mirror_from is not None:
        nf, nr, ns, nu = [], [], [], []
        for fi, f in enumerate(m.f):
            uv = m.uv[fi]
            i = f[0] % k
            if len(f) == 4:
                a, b, c, d = f
                if i >= mirror_from:
                    tri, sel = [(a, b, d), (b, c, d)], [(0, 1, 3), (1, 2, 3)]
                else:
                    tri, sel = [(a, b, c), (a, c, d)], [(0, 1, 2), (0, 2, 3)]
                for t, s in zip(tri, sel):
                    nf.append(t)
                    nr.append(m.r[fi])
                    ns.append(m.s[fi])
                    nu.append((uv[0], [uv[1][j] for j in s]) if uv else None)
            else:
                nf.append(f)
                nr.append(m.r[fi])
                ns.append(m.s[fi])
                nu.append(uv)
        m.f, m.r, m.s, m.uv = nf, nr, ns, nu
    for idx, (r2, y) in ((0, (rings2d[0], ys[0])), (len(ys) - 1, (rings2d[-1], ys[-1]))):
        loop = list(r2)
        flip = K.polygon_area2d(loop) < 0
        tris = K.tessellate(K.ccw(loop))
        order = list(range(k)) if not flip else list(reversed(range(k)))
        base = idx * k
        for a, b, c in tris:
            m.f.append((base + order[a], base + order[b], base + order[c]))
            m.r.append(cap_role or role)
            m.s.append(False)
            m.uv.append(None)
    return _consistent(m)


def tray(w, l, h, wall, floor_t, z0, role):
    """Closed genus-0 open-top box: outer skin, rim, inner walls and floor as one 2-manifold (28 tris)."""
    def rect(x, y, z):
        return [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    ob = rect(w / 2, l / 2, z0)
    ot = rect(w / 2, l / 2, z0 + h)
    it = rect(w / 2 - wall, l / 2 - wall, z0 + h)
    ib = rect(w / 2 - wall, l / 2 - wall, z0 + floor_t)
    verts = ob + ot + it + ib
    faces = [(3, 2, 1, 0), (12, 13, 14, 15)]
    for i in range(4):
        j = (i + 1) % 4
        faces += [(i, j, 4 + j, 4 + i), (4 + i, 4 + j, 8 + j, 8 + i), (8 + i, 8 + j, 12 + j, 12 + i)]
    m = K.Mesh().add(verts, faces, role, False)
    return _consistent(m)


def _consistent(m):
    """Make face winding consistent per connected island, then orient each island outward."""
    from collections import deque
    key, vid = {}, []
    for p in m.v:
        kk = (round(p[0] * 1e5), round(p[1] * 1e5), round(p[2] * 1e5))
        vid.append(key.setdefault(kk, len(key)))
    edges = {}
    for fi, f in enumerate(m.f):
        for j in range(len(f)):
            a, b = vid[f[j]], vid[f[(j + 1) % len(f)]]
            edges.setdefault((min(a, b), max(a, b)), []).append(fi)
    seen = [False] * len(m.f)
    islands = []
    for start in range(len(m.f)):
        if seen[start]:
            continue
        seen[start] = True
        comp = [start]
        q = deque([start])
        while q:
            fi = q.popleft()
            f = m.f[fi]
            for j in range(len(f)):
                a, b = vid[f[j]], vid[f[(j + 1) % len(f)]]
                for g in edges[(min(a, b), max(a, b))]:
                    if seen[g]:
                        continue
                    gf = m.f[g]
                    gd = {(vid[gf[t]], vid[gf[(t + 1) % len(gf)]]) for t in range(len(gf))}
                    if (a, b) in gd:
                        m.f[g] = tuple(reversed(gf))
                        if m.uv[g] is not None:
                            m.uv[g] = (m.uv[g][0], list(reversed(m.uv[g][1])))
                    seen[g] = True
                    comp.append(g)
                    q.append(g)
        islands.append(comp)
    A = np.asarray(m.v)
    for comp in islands:
        vol = 0.0
        for fi in comp:
            f = m.f[fi]
            p0 = A[f[0]]
            for i in range(1, len(f) - 1):
                vol += np.dot(p0, np.cross(A[f[i]], A[f[i + 1]]))
        if vol < 0:
            for fi in comp:
                m.f[fi] = tuple(reversed(m.f[fi]))
                if m.uv[fi] is not None:
                    m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
    return m


def hull_section(beam, depth, flare=0.85, deadrise=0.3):
    """Thick U hull section (x, z), keel at z=0, gunwale at z=depth; loop of 14 points.
    The inner (cavity) curve is the outer curve scaled toward the gunwale centre (0, depth), so every
    inner point lies on the segment from that centre to its outer point: the wall can never cross
    itself, even at the narrow bow, and its thickness scales with the local section
    (min(5 cm, 15% of the half-beam))."""
    b = beam / 2
    outer = [(-b, depth), (-b * flare, depth * deadrise + depth * 0.08), (-b * 0.35, depth * 0.03), (0.0, 0.0),
             (b * 0.35, depth * 0.03), (b * flare, depth * deadrise + depth * 0.08), (b, depth)]
    th = min(0.05, 0.15 * b)
    s = 1.0 - th / b
    inner = [(x * s, depth + (z - depth) * s) for x, z in reversed(outer)]
    return outer + inner


@register("vehicle.boat", V, "vehicle", {
    "kind": S.enum("rowboat", ["rowboat", "canoe", "sailboat", "skiff", "raft"]),
    "length": S.num(3.6, 1.8, 8.0), "beam": S.num(1.3, 0.6, 2.6), "depth": S.num(0.55, 0.3, 1.2),
    "sheer": S.num(0.15, 0.0, 0.5, "bow/stern rise"), "seats": S.integer(2, 0, 3), "oars": S.boolean(True),
    "cabin": S.boolean(False), "hull_role": S.enum("hull", HULL), "trim_role": S.enum("trim", ["trim", "wood", "metal", "chrome", "band"]),
    "sail_role": S.enum("fabric", ["fabric", "quilt", "paper", "knit"]),
}, "Boat: rowboat/canoe/sailboat/skiff (thick U-section lofted hull with seats, oars, mast+sail, cabin) or log raft.",
    rules=lambda P: ("cabin needs kind skiff or sailboat" if P["cabin"] and P["kind"] not in ("skiff", "sailboat") else
                     "canoe beam must be <= 1.1" if P["kind"] == "canoe" and P["beam"] > 1.1 else None))
def boat(P, seed):
    L, B, D = P["length"], P["beam"], P["depth"]
    kind = P["kind"]
    nodes = []
    if kind == "raft":
        logs = K.Mesh()
        n = max(4, int(B / 0.2))
        r = B / n / 2
        for i in range(n):
            x = -B / 2 + r + 2 * r * i
            logs.merge(K.cylinder(0, 0, 0, r * 0.98, L * (0.92 + 0.08 * ((i * 37) % 5) / 4), 6, P["hull_role"]).rotate_x(math.pi / 2)
                       .translate(x, L / 2, r))
        for y in (-L * 0.35, L * 0.35):
            logs.merge(K.box(0, y, 2 * r + 0.03, B + 0.1, 0.12, 0.06, P["trim_role"]))
        nodes.append(Node("raft", logs))
        if P["oars"]:
            nodes.append(Node("oars", K.tube([(B / 2 - 0.1, -L * 0.3, 2 * r + 0.08), (B / 2 - 0.1, L * 0.35, 2 * r + 0.08)], 0.025, 4, "wood")
                              .merge(K.box(B / 2 - 0.1, L * 0.42, 2 * r + 0.08, 0.16, 0.3, 0.02, "wood"))))
        return finalize(nodes, {"kind": kind, "deck_height": round(2 * r + 0.06, 3)})
    nring = 9
    ys, rings = [], []
    pointed_stern = kind == "canoe"
    for i in range(nring):
        t = i / (nring - 1)
        y = -L / 2 + L * t
        if pointed_stern:
            w = math.sin(math.pi * t) ** 0.7
        else:
            w = (math.sin(math.pi * (0.18 + 0.82 * t)) ** 0.6) if t > 0.0 else 0.0
            w = max(w, 0.55 if t < 0.5 else 0.0) if t < 0.5 else w
        w = max(0.06, w)
        rise = P["sheer"] * ((2 * t - 1) ** 2) * (1.0 if not pointed_stern else 1.6)
        sec = hull_section(B * w, D)
        sec = [(x, z + (rise * z / D)) for x, z in sec]
        rings.append(sec)
        ys.append(y)
    hull = capped_loft(rings, ys, P["hull_role"], P["trim_role"], mirror_from=7)
    nodes.append(Node("hull", hull))
    det = K.Mesh()
    for s in range(P["seats"] if kind != "sailboat" or not P["cabin"] else 1):
        t = (s + 1) / (P["seats"] + 1)
        y = -L / 2 + L * (0.25 + 0.5 * t)
        ti = (y + L / 2) / L
        if pointed_stern:
            w = max(0.06, math.sin(math.pi * ti) ** 0.7)
        else:
            w = max(0.55, math.sin(math.pi * (0.18 + 0.82 * ti)) ** 0.6) if ti < 0.5 else max(0.06, math.sin(math.pi * (0.18 + 0.82 * ti)) ** 0.6)
        det.merge(K.box(0, y, D * 0.72, B * w * 0.92, 0.22, 0.05, P["trim_role"]))
    if P["oars"] and kind in ("rowboat", "canoe", "skiff"):
        for sx in (-1, 1):
            o0 = (sx * B * 0.3, -L * 0.18, D + 0.04)
            o1 = (sx * B * 0.45, L * 0.32, D + 0.08)
            det.merge(K.tube([o0, o1], 0.022, 4, "wood"))
            det.merge(K.box(o1[0], o1[1] + 0.12, o1[2], 0.14, 0.32, 0.02, "wood"))
    if kind == "sailboat":
        mh = L * 1.1
        det.merge(post(0, L * 0.12, D * 0.3, D + mh, 0.05, P["trim_role"], 6))
        sail = K.prism([(0.0, 0.0), (L * 0.42, 0.0), (0.0, mh * 0.85)], -0.012, 0.012, P["sail_role"])
        sail.apply(lambda v: np.stack([v[:, 2], v[:, 0], v[:, 1]], 1)).orient_outward()
        sail.translate(0.07, L * 0.12 - L * 0.42 + 0.06, D + 0.25)
        sail = K.prism([(0.0, 0.0), (-L * 0.42, 0.0), (0.0, mh * 0.85)], -0.012, 0.012, P["sail_role"])
        sail.apply(lambda v: np.stack([v[:, 2], v[:, 0], v[:, 1]], 1)).orient_outward()
        sail.translate(0.07, L * 0.12 - 0.08, D + 0.25)
        det.merge(sail)
        det.merge(K.tube([(0, L * 0.12, D + 0.22), (0, L * 0.12 - L * 0.45, D + 0.22)], 0.03, 4, P["trim_role"]))
    if P["cabin"]:
        cw, cl, ch = B * 0.62, L * 0.32, D * 0.9 + 0.45
        cab = K.rounded_box(0, L * 0.05, D * 0.5 + ch / 2, cw, cl, ch, "body", bevel=0.35, smooth=False, k_corner=1)
        det.merge(cab)
        for sx in (-1, 1):
            det.merge(K.box(sx * (cw / 2 + 0.005), L * 0.05, D * 0.5 + ch * 0.68, 0.03, cl * 0.6, ch * 0.25, "glass"))
        det.merge(K.box(0, L * 0.05 - cl / 2 - 0.005, D * 0.5 + ch * 0.68, cw * 0.62, 0.03, ch * 0.25, "glass"))
    if kind == "skiff":
        det.merge(K.rounded_box(0, -L / 2 - 0.12, D * 0.65, 0.3, 0.32, 0.45, "metal", bevel=0.4, smooth=False, k_corner=1))
        det.merge(post(0, -L / 2 - 0.15, D * 0.1, D * 0.45, 0.04, "metal", 4))
    nodes.append(Node("boat_detail", det))
    return finalize(nodes, {"kind": kind, "waterline_m": round(D * 0.35, 3), "length_m": L})


@register("vehicle.craft", V, "vehicle", {
    "kind": S.enum("cart", ["sled", "cart", "wagon", "rover", "hover", "saucer"]),
    "length": S.num(2.2, 1.0, 6.0), "width": S.num(1.2, 0.6, 2.6), "body_height": S.num(0.6, 0.3, 1.5),
    "wheel_radius": S.num(0.35, 0.15, 0.8), "canopy": S.enum("none", ["none", "dome", "roof", "hoop"]),
    "lights": S.boolean(True), "cargo": S.integer(0, 0, 4), "handle": S.boolean(True),
    "body_role": S.enum("body", HULL + ["wood"]), "trim_role": S.enum("trim", ["trim", "metal", "chrome", "wood", "band"]),
}, "Ground craft: sled (runners), cart (2 wheels + handle), wagon (4 wheels), rover (rounded cab, 4 wheels), hover pod (skirt), "
   "saucer (lens hull, black window bands, light ring, optional glass dome, landing legs; wheel_radius/handle/cargo unused, "
   "like wheel_radius for sled/hover).",
    rules=lambda P: ("canopy dome/roof needs body_height >= 0.5" if P["canopy"] in ("dome", "roof") and P["body_height"] < 0.5 else
                     "saucer takes canopy none/dome only, width >= 1.4 m and length within 0.8-1.3 x width"
                     if P["kind"] == "saucer" and (P["canopy"] in ("roof", "hoop") or P["width"] < 1.4
                                                   or not (0.8 * P["width"] <= P["length"] <= 1.3 * P["width"]))
                     else None))
def craft(P, seed):
    L, W, H = P["length"], P["width"], P["body_height"]
    kind = P["kind"]
    wr = P["wheel_radius"]
    body = K.Mesh()
    det = K.Mesh()
    glow = K.Mesh()
    if kind == "sled":
        z0 = 0.18
        body.merge(K.rounded_box(0, 0, z0 + H * 0.3, W, L, H * 0.6, P["body_role"], bevel=0.3, smooth=False, k_corner=1))
        for sx in (-1, 1):
            pts = [(sx * W * 0.42, -L / 2 + 0.05, 0.04), (sx * W * 0.42, L / 2 - 0.15, 0.04), (sx * W * 0.42, L / 2 + 0.05, 0.16),
                   (sx * W * 0.42, L / 2 + 0.02, 0.32)]
            det.merge(K.tube(pts, 0.03, 4, P["trim_role"], smooth=False))
            for y in (-L * 0.3, L * 0.2):
                det.merge(K.box(sx * W * 0.42, y, (0.04 + z0) / 2 + 0.02, 0.04, 0.05, z0 - 0.02, P["trim_role"]))
        top_z = z0 + H * 0.6
    else:
        if kind == "hover":
            z0 = 0.35
            body.merge(K.lathe([(0, z0), (0.5, z0), (0.5, z0 + H * 0.5), (0.36, z0 + H), (0, z0 + H)], 12, P["body_role"], smooth=False, rx=W, ry=L))
            det.merge(K.lathe_closed([(0.44, 0.05), (0.54, 0.05), (0.54, z0 + 0.05), (0.44, z0 + 0.05)], 12, P["trim_role"], smooth=False, rx=W, ry=L))
            top_z = z0 + H
        elif kind == "saucer":
            # smooth lens hull with two black window bands (rim + upper), underside light ring,
            # optional glass dome and three splayed landing legs with disc feet
            z0 = 0.3
            prof = [(0.0, z0), (0.2, z0 + 0.02 * H), (0.4, z0 + 0.12 * H), (0.5, z0 + 0.27 * H), (0.47, z0 + 0.36 * H),
                    (0.36, z0 + 0.47 * H), (0.3, z0 + 0.53 * H), (0.2, z0 + 0.6 * H), (0.0, z0 + 0.63 * H)]
            roles = [P["body_role"], "light" if P["lights"] else P["body_role"], P["body_role"], "band", P["body_role"], "band",
                     P["body_role"], P["body_role"]]
            body.merge(K.lathe(prof, 16, P["body_role"], smooth=True, roles=roles, rx=W, ry=L, start=math.pi / 16))
            top_z = z0 + 0.6 * H
            if P["canopy"] == "dome":
                det.merge(K.lathe([(0.0, top_z - 0.02), (0.21, top_z - 0.02), (0.17, top_z + 0.22 * H), (0.0, top_z + 0.3 * H)], 10,
                                  "glass", rx=W, ry=L))
            for i in range(3):
                a = math.tau * i / 3 + math.pi / 2
                ca, sa = math.cos(a), math.sin(a)
                det.merge(K.tube([(ca * W * 0.16, sa * L * 0.16, z0 + 0.04 * H), (ca * W * 0.27, sa * L * 0.27, 0.05)], 0.025, 4,
                                 P["trim_role"]))
                det.merge(K.cylinder(ca * W * 0.27, sa * L * 0.27, 0.0, 0.07, 0.04, 6, P["trim_role"], smooth=False))
        else:
            z0 = wr * 0.9
            if kind == "rover":
                body.merge(K.rounded_box(0, 0, z0 + H / 2, W, L, H, P["body_role"], bevel=0.5, smooth=True, k_corner=2))
            else:
                # one watertight open-top tray (floor + 4 walls share edges; overlapping boxes were
                # non-manifold and self-intersecting)
                body.merge(tray(W, L, H, 0.06, 0.08, z0, P["body_role"]))
            top_z = z0 + H
            wheels = [(-L * 0.0, 2)] if kind == "cart" else [(-L * 0.3, 2), (L * 0.3, 2)]
            for y, _ in wheels:
                for sx in (-1, 1):
                    wh = K.cylinder(0, 0, -0.06, wr, 0.12, 10, P["trim_role"] if kind != "rover" else "rubber" if False else "metal", smooth=False)
                    wh.rotate_y(math.pi / 2).translate(sx * (W / 2 + 0.07), y, wr)
                    det.merge(wh)
                    det.merge(K.cylinder(0, 0, -0.08, wr * 0.3, 0.16, 6, P["trim_role"], smooth=False).rotate_y(math.pi / 2)
                              .translate(sx * (W / 2 + 0.07), y, wr))
            det.merge(K.tube([(-W / 2 - 0.02, wheels[0][0], wr), (W / 2 + 0.02, wheels[0][0], wr)], 0.03, 4, P["trim_role"]))
            if P["handle"] and kind in ("cart", "wagon"):
                for sx in (-1, 1):
                    det.merge(K.tube([(sx * W * 0.35, -L / 2 + 0.05, z0 + 0.2), (sx * W * 0.25, -L / 2 - 0.9, z0 + 0.15)], 0.03, 4, P["trim_role"]))
                det.merge(K.tube([(-W * 0.25, -L / 2 - 0.9, z0 + 0.15), (W * 0.25, -L / 2 - 0.9, z0 + 0.15)], 0.03, 4, P["trim_role"]))
    if P["canopy"] == "dome" and kind != "saucer":  # saucer builds its own dome above
        det.merge(K.lathe([(0.0, 0.0), (0.5, 0.0), (0.44, 0.25), (0.28, 0.42), (0.0, 0.5)], 10, "glass", rx=W * 0.8, ry=L * 0.45)
                  .scale(1, 1, H * 1.2).translate(0, -L * 0.12, top_z - 0.02))
    elif P["canopy"] == "roof":
        for sx in (-1, 1):
            for sy in (-1, 1):
                det.merge(post(sx * (W / 2 - 0.05), sy * (L / 2 - 0.05), top_z - 0.05, top_z + 0.9, 0.03, P["trim_role"], 4))
        det.merge(K.box(0, 0, top_z + 0.93, W + 0.1, L + 0.1, 0.07, P["body_role"]))
    elif P["canopy"] == "hoop":
        for i in range(3):
            y = -L * 0.35 + L * 0.35 * i
            pts = [(W / 2 * math.cos(a), y, top_z + W * 0.55 * math.sin(a)) for a in np.linspace(0, math.pi, 6)]
            det.merge(K.tube(pts, 0.025, 4, P["trim_role"]))
        cover = K.lathe_closed([(W * 0.5, 0.0), (W * 0.53, 0.0), (W * 0.53, 0.01), (W * 0.5, 0.01)], 4, "fabric")
        det.merge(K.box(0, 0, top_z + W * 0.55 + 0.02, W * 0.4, L * 0.72, 0.04, "fabric"))
    if P["lights"] and kind != "saucer":  # saucer lights = its underside light-ring band
        for sx in (-1, 1):
            glow.merge(K.box(sx * W * 0.32, L / 2 + 0.01, top_z - H * 0.35 if kind != "sled" else top_z - 0.15, 0.14, 0.04, 0.1, "light"))
    for i in range(P["cargo"] if kind != "saucer" else 0):
        cs = min(W, L) * 0.28
        x = (-1 if i % 2 == 0 else 1) * W * 0.2
        y = (-1 if i < 2 else 1) * L * 0.18
        det.merge(K.box(x, y, top_z + cs / 2 + (0.0 if kind in ("cart", "wagon") else 0.0) - (H - 0.08 if kind in ("cart", "wagon") else 0.0),
                        cs, cs, cs, "wood" if kind != "rover" else "metal"))
    nodes = [Node("craft_body", body), Node("craft_detail", det), Node("craft_lights", glow)]
    return finalize(nodes, {"kind": kind})
