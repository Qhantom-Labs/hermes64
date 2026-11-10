"""Architecture generators (theme-agnostic): room shells with shaped openings, wall/floor/ceiling
modules, doors, windows, stairs, roofs, corridors, railings, piers, bridges, columns, houses."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from . import wall2d as W
from .asset import Asset, Node, register
from .genutil import finalize, post
from .rng import rng

V = "3.0.0"
SHAPES = ["rect", "rounded_rect", "oval", "round", "arch", "gothic"]
WALLS = {"e": 0.0, "n": 90.0, "w": 180.0, "s": 270.0}
STRUCT = ["wall", "wall_alt", "wood", "stone", "metal", "body", "trim", "frame"]
DOOR_SHAPE = {"rounded_rect": "rounded_top"}  # floor-level openings need a flat bottom
OPENING_ITEM = {
    "wall": S.enum("s", ["n", "e", "s", "w"]), "offset": S.num(0.0, -0.45, 0.45, "fraction along the wall"),
    "width": S.num(1.0, 0.4, 4.0), "height": S.num(1.2, 0.4, 3.5), "sill": S.num(0.9, 0.0, 2.5),
    "kind": S.enum("window", ["window", "door"]), "shape": S.enum("rect", SHAPES),
}


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def _corner(P):
    return 0.3 * min(P["width"], P["depth"]) * 0.5 if P["plan"] == "rounded_rect" else 0.0


def _outline(P):
    plan, w, d = P["plan"], P["width"], P["depth"]
    if plan == "round":
        w = d = min(w, d)
    k = int(P.get("wall_segments", 24))
    if plan == "rect":
        return K.rounded_rect2d(w, d, 0.0)
    if plan == "rounded_rect":
        return K.rounded_rect2d(w, d, _corner(P), max(2, k // 8))
    if plan == "round":
        return K.circle2d(w / 2, k)
    return K.circle2d(0, k, rx=w / 2, ry=d / 2)


def _wall_span(P, wall):
    """(s_center, half_usable_length, perimeter) of a wall direction along the plan outline."""
    out = _outline(P)
    path = W.PlanPath(out, 0.0)
    ang = math.radians(WALLS[wall])
    ray = np.array([math.cos(ang), math.sin(ang)])
    best, best_s = -1e9, 0.0
    for i in range(len(out)):
        a = np.array(out[i])
        b = np.array(out[(i + 1) % len(out)])
        for t in np.linspace(0, 1, 9):
            p = a + (b - a) * t
            dirn = p / max(1e-9, np.linalg.norm(p))
            sc = float(np.dot(dirn, ray))
            if sc > best + 1e-9:
                best, best_s = sc, path.s[i] + t * (path.s[i + 1] - path.s[i])
    plan, w, d = P["plan"], P["width"], P["depth"]
    if plan in ("rect", "rounded_rect"):
        side = w if wall in ("n", "s") else d
        usable = side - 2 * _corner(P)
    else:
        usable = path.length / 4.0
    return best_s, usable / 2.0, path.length


def _layout_openings(P):
    cove = P["cove"]
    zb = cove
    zt = P["height"] - (cove if P["ceiling"] != "gable" else 0.0)
    res = []
    for i, o in enumerate(P["openings"]):
        sc, half, L = _wall_span(P, o["wall"])
        ow = o["width"] if o["shape"] != "round" else min(o["width"], o["height"])
        s = sc + o["offset"] * 2 * half
        if abs(o["offset"] * 2 * half) + ow / 2 > half - 0.05:
            raise S.ParamError("opening %d (%s wall) does not fit: needs %.2f m, usable half-wall %.2f m"
                               % (i, o["wall"], abs(o["offset"] * 2 * half) + ow / 2, half - 0.05))
        hatch = o["kind"] == "door" and o["shape"] in ("oval", "round")
        sill = (zb + 0.08 if hatch else zb) if o["kind"] == "door" else max(o["sill"], zb + 0.05)
        oh = o["height"] if o["shape"] != "round" else ow
        if sill + oh > zt - 0.05:
            raise S.ParamError("opening %d top %.2f m exceeds wall top %.2f m" % (i, sill + oh, zt - 0.05))
        res.append({"s": s % L, "w": ow, "h": oh, "sill": sill, "kind": o["kind"], "shape": o["shape"],
                    "wall": o["wall"], "L": L, "index": i})
    res.sort(key=lambda r: r["s"])
    if len(res) > 1:
        for a, b in zip(res, res[1:] + res[:1]):
            gap = (b["s"] - a["s"]) % a["L"]
            if gap < (a["w"] + b["w"]) / 2 + 0.1:
                raise S.ParamError("openings %d and %d overlap along the wall" % (a["index"], b["index"]))
    return res


def _shell_rules(P):
    if P["ceiling"] == "gable" and P["plan"] != "rect":
        return "gable ceiling needs plan 'rect'"
    if P["cove"] > min(P["width"], P["depth"]) / 4 or P["cove"] > (P["height"] - 2.0) / 2:
        return "cove too large for the room"
    plan, w, d = P["plan"], P["width"], P["depth"]
    curv = {"rect": 1e9, "rounded_rect": _corner(P), "round": min(w, d) / 2,
            "oval": (min(w, d) / 2) ** 2 / (max(w, d) / 2)}[plan]
    if P["cove"] > 0.8 * curv:
        return "cove %.2f m exceeds 0.8x the plan's tightest curvature radius (%.2f m)" % (P["cove"], curv)
    if any(o["kind"] == "door" for o in P["openings"]) and P["cove"] > 0.35:
        return "rooms with doors allow cove <= 0.35 (door threshold = cove)"
    try:
        _layout_openings(P)
    except S.ParamError as e:
        return str(e)
    return None


def _loop_loft(rings, role, smooth=True):
    """Closed (torus-topology) loft: connects ring i to i+1 and the last to the first; no caps."""
    k = len(rings[0])
    n = len(rings)
    verts = [p for r in rings for p in r]
    faces = []
    for j in range(n):
        j2 = (j + 1) % n
        for i in range(k):
            i2 = (i + 1) % k
            faces.append((j * k + i, j * k + i2, j2 * k + i2, j2 * k + i))
    return K.Mesh().add(verts, faces, role, smooth).orient_outward()


def _orient_toward(m, centre_fn):
    """Flip individual faces so each normal points toward centre_fn(face_centroid)."""
    V3 = np.asarray(m.v)
    for i, f in enumerate(m.f):
        p = V3[list(f)]
        nrm = np.zeros(3)
        for j in range(len(f)):
            nrm += np.cross(p[j], p[(j + 1) % len(f)])
        c = p.mean(0)
        if np.dot(nrm, np.asarray(centre_fn(c)) - c) < 0:
            m.f[i] = tuple(reversed(f))
            if m.uv[i] is not None:
                m.uv[i] = (m.uv[i][0], list(reversed(m.uv[i][1])))
    return m


@register("arch.room_shell", V, "shell", {
    "plan": S.enum("rect", ["rect", "rounded_rect", "round", "oval"]),
    "width": S.num(6.0, 2.5, 16.0), "depth": S.num(5.0, 2.5, 16.0), "height": S.num(2.8, 2.2, 6.0),
    "cove": S.num(0.0, 0.0, 1.0, "radius of rounded floor/ceiling junctions"),
    "ceiling": S.enum("flat", ["flat", "dome", "gable"]), "ceiling_rise": S.num(0.8, 0.2, 3.0),
    "wall_segments": S.lod(S.integer(24, 12, 40)),
    "openings": S.array(OPENING_ITEM, [{"wall": "s", "offset": 0.0, "width": 1.0, "height": 2.1, "sill": 0.0, "kind": "door", "shape": "rect"},
                                        {"wall": "n", "offset": 0.0, "width": 1.6, "height": 1.2, "sill": 0.9, "kind": "window", "shape": "rect"}], 8),
    "trim": S.boolean(True), "floor_role": S.enum("floor", ["floor", "stone", "wood", "snow", "dirt"]),
    "wall_role": S.enum("wall", STRUCT), "ceiling_role": S.enum("ceiling", ["ceiling", "wall", "wood", "stone", "roof"]),
    "floor_rings": S.lod(S.integer(0, 0, 6, "concentric floor/ceiling rings (vertex density for per-vertex light); 0 = single polygon")),
    "ring_bias": S.num(1.0, 1.0, 3.0, "ring spacing exponent: >1 packs rings toward the outline (narrow baked-AO band at the wall base instead of a wide Gouraud zigzag)"),
    "cap_center": S.boolean(False, "close ringed floor/ceiling caps with a centre vertex (radial light falloff) instead of one n-gon fan, whose long thin triangles show as stair-stepped wedges"),
    "ceiling_panel": S.num(0.0, 0.0, 0.7, "luminous ceiling panel (role 'light', chrome 'trim' bezel) at this fraction of the ceiling outline; dome: lit oculus"),
}, "Interior room shell (one-sided): rect/rounded/round/oval plan, coves, flat/dome/gable ceiling, shaped door/window openings, optional ring-tessellated floor/ceiling and luminous ceiling panel; meta lists openings (with module placement) + walkable outline.",
    rules=_shell_rules, origin="room_floor")
def room_shell(P, seed):
    out = _outline(P)
    h, c = P["height"], P["cove"]
    zb = c
    zt = h - (c if P["ceiling"] != "gable" else 0.0)
    ops = _layout_openings(P)
    L = W.PlanPath(out, 0.0).length
    seam = 0.0
    if ops:
        best = -1.0
        for a, b in zip(ops, ops[1:] + ops[:1]):
            gap = ((b["s"] - b["w"] / 2) - (a["s"] + a["w"] / 2)) % L if len(ops) > 1 else L - a["w"]
            if gap > best:
                best = gap
                seam = (a["s"] + a["w"] / 2 + gap / 2) % L
    path = W.PlanPath(out, seam)
    holes, notches, meta_ops = [], [], []
    for o in sorted(ops, key=lambda r: r["index"]):
        sl = (o["s"] - seam) % L
        notch = o["kind"] == "door" and o["shape"] not in ("oval", "round")
        pts = K.opening2d(DOOR_SHAPE.get(o["shape"], o["shape"]) if notch else o["shape"], o["w"], o["h"], 16)
        if notch:
            npath = [pts[0]] + list(reversed(pts[1:]))
            notches.append((sl - o["w"] / 2, sl + o["w"] / 2, [(sl + x, zb + z) for x, z in npath]))
        else:
            holes.append([(sl + x, o["sill"] + z) for x, z in pts])
        p = path.point(sl)
        n = path.normal_in(sl)
        yaw = math.degrees(math.atan2(n[1], n[0])) + 90.0
        meta_ops.append({"index": o["index"], "kind": o["kind"], "shape": o["shape"], "wall": o["wall"],
                         "width": round(o["w"], 4), "height": round(o["h"], 4), "sill": round(o["sill"], 4),
                         "pos_gltf": [round(float(p[0]), 4), 0.0, round(float(-p[1]), 4)],
                         "yaw_deg": round(yaw % 360.0, 3)})
    cuts = path.local_cuts()
    tris = W.strip_polys(L, zb, zt, holes, notches, snap=cuts)
    polys = W.weld_polys(W.split_all(tris, cuts), 3e-4)
    walls = K.Mesh()
    for poly in polys:
        q = W.map_polys([poly], path)[0]
        for a, b, cc in W.tri_convex(poly):  # explicit, degenerate-free triangulation of each piece
            walls.add([q[a], q[b], q[cc]], [(0, 1, 2)], P["wall_role"], False, [("m", [poly[a], poly[b], poly[cc]])])
    walls = _orient_toward(walls, lambda cpt: (0.0, 0.0, cpt[2]))
    if c > 1e-3:
        steps = [0.0, math.pi / 4, math.pi / 2]
        rings_b = [[(x, y, c * (1 - math.cos(t))) for x, y in W.offset_outline(out, c * (1 - math.sin(t)))] for t in steps]
        cm = K.loft(rings_b, P["wall_role"], smooth=True, cap0=False, cap1=False)
        walls.merge(_orient_toward(cm, lambda cpt: (0.0, 0.0, h * 0.5)))
        if P["ceiling"] != "gable":
            rings_t = [[(x, y, h - c + c * math.sin(t)) for x, y in W.offset_outline(out, c * (1 - math.cos(t)))] for t in steps]
            ct = K.loft(rings_t, P["wall_role"], smooth=True, cap0=False, cap1=False)
            walls.merge(_orient_toward(ct, lambda cpt: (0.0, 0.0, h * 0.5)))
    floor_outline = W.offset_outline(out, c) if c > 1e-3 else out
    nring = int(P.get("floor_rings", 0))
    panel = float(P.get("ceiling_panel", 0.0))
    floor = _ring_disc(floor_outline, 0.0, nring, P["floor_role"], True, bias=float(P.get("ring_bias", 1.0)), center=bool(P.get("cap_center", False)))
    ceil = K.Mesh()
    cr = P["ceiling_role"]
    if P["ceiling"] == "gable":
        w, d = P["width"], P["depth"]
        rise = P["ceiling_rise"]
        if w >= d:
            slopes = [[(-w / 2, -d / 2, h), (w / 2, -d / 2, h), (w / 2, 0, h + rise), (-w / 2, 0, h + rise)],
                      [(w / 2, d / 2, h), (-w / 2, d / 2, h), (-w / 2, 0, h + rise), (w / 2, 0, h + rise)]]
            ends = [[(-w / 2, -d / 2, h), (-w / 2, 0, h + rise), (-w / 2, d / 2, h)],
                    [(w / 2, d / 2, h), (w / 2, 0, h + rise), (w / 2, -d / 2, h)]]
        else:
            slopes = [[(w / 2, -d / 2, h), (w / 2, d / 2, h), (0, d / 2, h + rise), (0, -d / 2, h + rise)],
                      [(-w / 2, d / 2, h), (-w / 2, -d / 2, h), (0, -d / 2, h + rise), (0, d / 2, h + rise)]]
            ends = [[(-w / 2, -d / 2, h), (w / 2, -d / 2, h), (0, -d / 2, h + rise)],
                    [(w / 2, d / 2, h), (-w / 2, d / 2, h), (0, d / 2, h + rise)]]
        for q in slopes:
            ceil.add(q, [(0, 1, 2, 3)], cr)
        gab = K.Mesh()
        for tri in ends:
            gab.add(tri, [(0, 1, 2)], P["wall_role"])
        ceil = _orient_toward(ceil, lambda cpt: (0.0, 0.0, h * 0.5))
        walls.merge(_orient_toward(gab, lambda cpt: (0.0, 0.0, h * 0.5)))
    elif P["ceiling"] == "dome":
        rise = P["ceiling_rise"]
        base = W.offset_outline(out, c) if c > 1e-3 else out
        rings = []
        ts = [0.0, math.pi / 6, math.pi / 3]
        if panel > 0:  # oculus: an extra ring at the panel radius; only the cap inside it is lit
            ts.append(math.acos(min(panel, 0.45)))
        for t in ts:
            sc = math.cos(t)
            rings.append([(x * sc, y * sc, h + rise * math.sin(t)) for x, y in base])
        dm = K.loft(rings, cr, smooth=True, cap0=False, cap1=False)
        apex = len(dm.v)
        dm.v.append((0.0, 0.0, h + rise))
        k = len(base)
        off = (len(rings) - 1) * k
        for i in range(k):
            dm.f.append((off + i, off + (i + 1) % k, apex))
            dm.r.append("light" if panel > 0 else cr)  # lit oculus at the apex
            dm.s.append(True)
            dm.uv.append(None)
        ceil = _orient_toward(dm, lambda cpt: (0.0, 0.0, h * 0.5))
    else:
        co = W.offset_outline(out, c) if c > 1e-3 else out
        ceil = _ring_disc(co, h, nring, cr, False, panel, bias=float(P.get("ring_bias", 1.0)), center=bool(P.get("cap_center", False)))
    trim = _baseboard(out, ops, L) if (P["trim"] and c <= 1e-3) else K.Mesh()
    meta = {"plan": P["plan"], "openings": meta_ops, "height": h, "cove": c,
            "walkable_outline_gltf": [[round(x, 4), round(-y, 4)] for x, y in floor_outline],
            "door_threshold_m": round(c, 4)}
    nodes = [Node("floor", floor, "shell"), Node("walls", walls, "shell"), Node("ceiling", ceil, "shell"), Node("trim", trim)]
    return Asset([n for n in nodes if n.mesh.f], meta)


def _ring_disc(outline, z, rings, role, up, panel=0.0, bias=1.0, center=False):
    """Floor/ceiling cap of a convex CCW outline at height z. rings=0 and panel=0 -> the legacy single
    polygon. Otherwise concentric rings (outline scaled about the origin) give per-vertex lighting
    something to work with; panel>0 ends in a luminous disc (role 'light') inside a chrome bezel band."""
    k = len(outline)
    if rings <= 0 and panel <= 0:
        f = tuple(range(k)) if up else tuple(reversed(range(k)))
        return K.Mesh().add([(x, y, z) for x, y in outline], [f], role)
    inner = panel if panel > 0 else 1.0 / (rings + 1)
    n = max(rings, 1)
    t = [(j / n) ** bias for j in range(n + 1)] if bias != 1.0 else [j / n for j in range(n + 1)]
    scales = [1.0 - (1.0 - inner * 1.08) * tj for tj in t] if panel > 0 else \
        [1.0 - (1.0 - inner) * tj for tj in t]
    roles = [role] * n
    if panel > 0:
        scales.append(inner)
        roles.append("trim")
    verts, faces, fr = [], [], []
    for s in scales:
        verts.extend((x * s, y * s, z) for x, y in outline)
    for j, r in enumerate(roles):
        for i in range(k):
            i2 = (i + 1) % k
            q = (j * k + i, j * k + i2, (j + 1) * k + i2, (j + 1) * k + i)
            faces.append(q if up else tuple(reversed(q)))
            fr.append(r)
    last = len(scales) - 1
    if center:
        ci = len(verts)
        verts.append((0.0, 0.0, z))
        for i in range(k):
            t = (last * k + i, last * k + (i + 1) % k, ci)
            faces.append(t if up else tuple(reversed(t)))
            fr.append("light" if panel > 0 else role)
        return K.Mesh().add(verts, faces, fr)
    cap = tuple(last * k + i for i in range(k))
    faces.append(cap if up else tuple(reversed(cap)))
    fr.append("light" if panel > 0 else role)
    return K.Mesh().add(verts, faces, fr)


def _baseboard(out, ops, L, hgt=0.09, dep=0.025):
    """Baseboard trim along the plan (role 'trim'), interrupted at doors (closed solid pieces)."""
    path = W.PlanPath(out, 0.0)
    doors = sorted((o["s"] - o["w"] / 2, o["s"] + o["w"] / 2) for o in ops if o["kind"] == "door")
    if not doors:
        inner = W.offset_outline(out, dep)
        rings = [[(x, y, 0.0), (xi, yi, 0.0), (xi, yi, hgt), (x, y, hgt)] for (x, y), (xi, yi) in zip(out, inner)]
        return _loop_loft(rings, "trim", smooth=False)
    mesh = K.Mesh()
    for i, (a, b) in enumerate(doors):
        na = doors[(i + 1) % len(doors)][0]
        start, end = b + 0.02, na - 0.02
        if end <= start:
            end += L
        if end - start < 0.1:
            continue
        verts_s = [sk for sk in path.s[:-1] + [sk + L for sk in path.s[:-1]] if start + 0.01 < sk < end - 0.01]
        ss = [start] + verts_s + [end]
        rings = []
        for s in ss:
            sm = s % L
            p = path.point(sm)
            n = path.normal_in(sm)
            if s in verts_s:  # mitre at plan vertices
                n2 = path.normal_in((sm - 1e-4) % L)
                n = (n + n2)
                n /= max(1e-9, np.linalg.norm(n))
            q = p + n * dep
            rings.append([(p[0], p[1], 0.0), (q[0], q[1], 0.0), (q[0], q[1], hgt), (p[0], p[1], hgt)])
        mesh.merge(K.loft(rings, "trim", smooth=False))
    return mesh


# ------------------------------------------------------------------ wall / floor / ceiling modules
def _extrude_xz(outline, holes, y0, y1, role):
    """Extrude an (x, z) outline (+holes) along +y from y0 to y1 (closed solid)."""
    m = K.prism(outline, y0, y1, role, holes=holes)
    m.apply(lambda v: np.stack([v[:, 0], v[:, 2], v[:, 1]], 1))
    return m.orient_outward()


def _wall_rules(P):
    if P["opening"] != "none":
        if P["opening_width"] > P["length"] - 0.2:
            return "opening wider than wall"
        top = (0.08 if P["opening"] == "door" else P["opening_sill"]) + P["opening_height"]
        if top > P["height"] - 0.1:
            return "opening taller than wall"
        if P["opening"] == "window" and P["opening_sill"] < 0.1:
            return "window sill must be >= 0.1 (use opening=door for floor-level openings)"
    return None


@register("arch.wall_module", V, "arch", {
    "length": S.num(2.0, 0.5, 8.0), "height": S.num(2.8, 1.0, 6.0), "thickness": S.num(0.2, 0.05, 0.6),
    "top": S.enum("flat", ["flat", "rounded", "crenel"]),
    "opening": S.enum("none", ["none", "door", "window"]), "opening_shape": S.enum("rect", SHAPES),
    "opening_width": S.num(1.0, 0.3, 4.0), "opening_height": S.num(1.2, 0.3, 3.5), "opening_sill": S.num(0.9, 0.0, 2.5),
    "role": S.enum("wall", STRUCT),
}, "Straight wall segment (closed solid) with optional shaped door notch or window hole; interior face at y=0.",
    rules=_wall_rules, origin="opening_floor")
def wall_module(P, seed):
    L, H, T = P["length"], P["height"], P["thickness"]
    top = []
    if P["top"] == "rounded":
        rr = min(0.4, L * 0.15)
        top = [(L / 2 * math.cos(math.pi * i / 6), H + rr * math.sin(math.pi * i / 6)) for i in range(1, 6)]
    elif P["top"] == "crenel":
        n = max(2, int(L / 0.5))
        for i in range(n, 0, -1):
            x0 = -L / 2 + L * i / n
            x1 = -L / 2 + L * (i - 1) / n
            hh = H + (0.25 if i % 2 == 0 else 0.0)
            top += [(x0, hh), (x1, hh)]
    outline = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, H)] + top + [(-L / 2, H)]
    holes = []
    if P["opening"] == "window":
        holes.append([(x, P["opening_sill"] + z) for x, z in K.opening2d(P["opening_shape"], P["opening_width"], P["opening_height"], 14)])
    elif P["opening"] == "door" and P["opening_shape"] in ("oval", "round"):
        holes.append([(x, 0.08 + z) for x, z in K.opening2d(P["opening_shape"], P["opening_width"], P["opening_height"], 14)])
    elif P["opening"] == "door":
        pts = K.opening2d(DOOR_SHAPE.get(P["opening_shape"], P["opening_shape"]), P["opening_width"], P["opening_height"], 14)
        outline = [(-L / 2, 0.0)] + [pts[0]] + list(reversed(pts[1:])) + outline[1:]
    m = _extrude_xz(_dedupe(outline), holes, 0.0, T, P["role"])
    return finalize([Node("wall", m)], {"interior_face": "y=0 (glTF +Z side)", "opening": P["opening"]}, center_y=False)


@register("arch.floor_module", V, "arch", {
    "shape": S.enum("rect", ["rect", "rounded_rect", "round", "oval"]),
    "width": S.num(2.0, 0.5, 10.0), "depth": S.num(2.0, 0.5, 10.0), "thickness": S.num(0.1, 0.02, 0.5),
    "bevel": S.boolean(False), "role": S.enum("floor", ["floor", "stone", "wood", "snow", "dirt", "grass", "body"]),
}, "Floor slab (closed solid), bottom at y=0, walkable top at y=thickness.")
def floor_module(P, seed):
    w, d, t = P["width"], P["depth"], P["thickness"]
    if P["shape"] == "round":
        w = d = min(w, d)
    if P["bevel"]:
        if P["shape"] in ("rect", "rounded_rect"):
            m = K.rounded_box(0, 0, t / 2, w, d, t, P["role"], bevel=0.25, smooth=False, k_corner=1)
        else:
            m = K.lathe([(0, 0), (0.5 - min(0.2, t * 0.6 / max(w, d)), 0), (0.5, t * 0.5), (0.5, t), (0, t)], 16, P["role"], smooth=False, rx=w, ry=d)
    else:
        m = K.prism(K.plan2d(P["shape"], w, d, 16, 0.3), 0, t, P["role"])
    return finalize([Node("floor", m)], {"walk_height": round(t, 4)})


@register("arch.ceiling_module", V, "arch", {
    "shape": S.enum("rect", ["rect", "rounded_rect", "round", "oval"]),
    "width": S.num(2.0, 0.5, 10.0), "depth": S.num(2.0, 0.5, 10.0), "thickness": S.num(0.1, 0.03, 0.4),
    "style": S.enum("flat", ["flat", "coffered", "dome", "beams"]), "rise": S.num(0.4, 0.1, 2.0),
    "role": S.enum("ceiling", ["ceiling", "wood", "stone", "wall", "body"]),
}, "Ceiling piece (closed solid): flat slab, coffered, dome or beamed; bottom at y=0.")
def ceiling_module(P, seed):
    w, d, t = P["width"], P["depth"], P["thickness"]
    if P["shape"] == "round":
        w = d = min(w, d)
    role = P["role"]
    m = K.prism(K.plan2d(P["shape"], w, d, 16, 0.3), 0, t, role)
    extra = K.Mesh()
    if P["style"] == "dome":
        extra = K.lathe([(0, t - 0.01), (0.45, t - 0.01), (0.32, t + P["rise"] * 0.7), (0, t + P["rise"])], 12, role, rx=w, ry=d)
    elif P["style"] == "coffered":
        n = max(2, int(min(w, d) / 0.8))
        for i in range(1, n):
            extra.merge(K.box(-w / 2 + w * i / n, 0, -0.06, 0.08, d * 0.9, 0.14, "trim"))
            extra.merge(K.box(0, -d / 2 + d * i / n, -0.07, w * 0.9, 0.08, 0.12, "trim"))
    elif P["style"] == "beams":
        n = max(2, int(w / 0.9))
        for i in range(n):
            extra.merge(K.box(-w / 2 + w * (i + 0.5) / n, 0, -0.07, 0.12, d * 0.98, 0.16, "trim"))
    return finalize([Node("ceiling", m), Node("ceiling_detail", extra)])


# ------------------------------------------------------------------ doors and windows
def _frame_polygon(shape, w, h, fw, ring, k=14):
    """Frame around an opening (x, z), opening bottom at z=0. ring=True -> closed ring (outline,
    [hole]); ring=False -> U-shaped frame open at the bottom (single polygon, no holes)."""
    inner = K.opening2d(shape, w, h, k)
    if shape in ("oval", "round", "rounded_rect"):
        outer = [(x, z - fw) for x, z in K.opening2d(shape, w + 2 * fw, h + 2 * fw, k)]
        return outer, [inner]
    outer = [(x * (w + 2 * fw) / w, z * (h + fw) / h) for x, z in inner]
    if ring:
        outer = [(x, z - fw if z < 1e-6 else z) for x, z in outer]
        return outer, [inner]
    poly = [outer[0], inner[0]] + list(reversed(inner[1:])) + [outer[1]] + outer[2:]
    return _dedupe(poly), []


@register("arch.door", V, "arch", {
    "shape": S.enum("rect", ["rect", "arch", "round_top", "oval", "hatch", "gothic"]),
    "width": S.num(1.0, 0.6, 3.0), "height": S.num(2.1, 1.2, 3.5),
    "frame_width": S.num(0.1, 0.03, 0.3), "frame_depth": S.num(0.2, 0.05, 0.6),
    "leaf": S.enum("panel", ["planks", "panel", "slab", "porthole", "none"]),
    "open_angle": S.num(0.0, 0.0, 110.0), "frame_role": S.enum("frame", STRUCT + ["chrome"]),
    "leaf_role": S.enum("door", ["door", "wood", "metal", "body", "stone"]),
    "segments": S.integer(14, 6, 24, "curve segments of round/oval openings (low-poly variants for room budgets)"),
}, "Door: frame + hinged leaf node (kit_door_leaf, pivot at the hinge); rect/arch/oval/hatch/gothic.",
    origin="opening_floor")
def door(P, seed):
    shape = P["shape"]
    w, h = P["width"], P["height"]
    if shape == "hatch":
        h = max(h, w)
    fw, fd = P["frame_width"], P["frame_depth"]
    ring = shape in ("oval", "hatch")
    oshape = "oval" if shape == "hatch" else shape
    sill = fw if ring else 0.0
    seg = int(P["segments"])
    outline, holes = _frame_polygon(oshape, w, h, fw, ring, seg)
    frame = _extrude_xz([(x, z + sill) for x, z in outline], [[(x, z + sill) for x, z in hh] for hh in holes], 0.0, fd, P["frame_role"])
    nodes = [Node("door_frame", frame)]
    if P["leaf"] != "none":
        lw, lh = w - 0.03, h - 0.03
        lp = [(x, z + 0.015 + sill) for x, z in K.opening2d(oshape, lw, lh, seg)]
        lt = 0.05
        y0 = fd * 0.5 - lt / 2
        leaf = _extrude_xz(lp, [], y0, y0 + lt, P["leaf_role"])
        if P["leaf"] == "planks":
            for i in range(3):
                leaf.merge(K.box(0, y0 - 0.011, sill + lh * (0.2 + 0.3 * i), lw * 0.7, 0.024, 0.08, P["leaf_role"]))
        elif P["leaf"] == "panel":
            for zf in (0.3, 0.68):
                leaf.merge(K.box(0, y0 - 0.009, sill + lh * zf, lw * 0.55, 0.02, lh * 0.26, P["leaf_role"]))
        elif P["leaf"] == "porthole":
            r = min(lw, lh) * 0.18
            leaf.merge(_extrude_xz(K.circle2d(r, min(10, seg)), [], y0 - 0.012, y0 + lt + 0.012, "glass").translate(0, 0, sill + lh * 0.62))
        hinge = (-lw / 2, fd * 0.5, 0.0)
        leaf.translate(-hinge[0], -hinge[1], 0).rotate_z(-math.radians(P["open_angle"])).translate(*hinge)
        nodes.append(Node("door_leaf", leaf, origin=hinge))
    return finalize(nodes, {"opening_width": round(w, 4), "opening_height": round(h, 4), "threshold": round(sill, 4),
                            "interior_face": "y=0"}, center_y=False)


def _molded_bezel(opening, fw, fd, role, z0):
    """Soft molded window surround: a rounded lip profile swept around the opening (miter offsets
    along the outline normals) -> closed genus-1 solid with the deep reveal as its inner wall."""
    pts = [np.array(p, dtype=np.float64) for p in K.ccw(opening)]
    n = len(pts)
    nrm = []
    for i in range(n):
        e = pts[(i + 1) % n] - pts[i]
        e /= max(np.linalg.norm(e), 1e-12)
        nrm.append(np.array([e[1], -e[0]]))  # outward normal of a CCW edge
    miter = []
    for i in range(n):
        n1, n2 = nrm[i - 1], nrm[i]
        miter.append((n1 + n2) / max(1.0 + float(np.dot(n1, n2)), 0.2))
    prof = [(0.0, fd), (0.0, 0.0), (0.3 * fw, -0.04), (0.7 * fw, -0.05), (fw, -0.02), (fw, fd)]
    verts = []
    for o, y in prof:
        for p, m in zip(pts, miter):
            q = p + o * m
            verts.append((q[0], y, q[1] + z0))
    J = len(prof)
    faces = []
    for j in range(J):
        j2 = (j + 1) % J
        for i in range(n):
            i2 = (i + 1) % n
            faces.append((j * n + i, j * n + i2, j2 * n + i2, j2 * n + i))
    return K.Mesh().add(verts, faces, role, True).orient_outward()


def _window_rules(P):
    if P["frame_style"] == "molded":
        npts = {"rect": 4, "rounded_rect": 16, "oval": 14, "round": 14}.get(P["shape"], 14)
        est = npts * 12 + (4 * npts - 4 if P["glass"] else 0) + 2 + (12 if P["ledge"] else 0) + 24 * P["shutters"] \
            + 12 * (P["mullions_x"] + P["mullions_z"])
        if est > 300:
            return "molded %s frame with %d mullions (%d tris est.) exceeds the 300 arch budget" % (
                P["shape"], P["mullions_x"] + P["mullions_z"], est)
    return None


@register("arch.window", V, "arch", {
    "shape": S.enum("rect", SHAPES), "width": S.num(1.2, 0.3, 4.0), "height": S.num(1.0, 0.3, 3.0),
    "sill": S.num(0.9, 0.0, 2.5), "frame_width": S.num(0.08, 0.02, 0.4), "frame_depth": S.num(0.18, 0.04, 0.6),
    "mullions_x": S.integer(0, 0, 4), "mullions_z": S.integer(0, 0, 3), "ledge": S.boolean(True),
    "shutters": S.boolean(False), "glass": S.boolean(True), "view_card": S.boolean(True),
    "frame_role": S.enum("frame", STRUCT + ["chrome"]),
    "frame_style": S.enum("flat", ["flat", "molded"], "molded = soft rounded lip swept around the opening (additive 3.1)"),
}, "Window: shaped frame ring (flat or molded lip), glass, mullions, ledge, shutters, view card (kit_card_view behind the glass, facing the room). Geometry starts at the sill; origin at floor level below.",
    wall_mounted=True, origin="opening", rules=_window_rules)
def window(P, seed):
    shape, w, h, s = P["shape"], P["width"], P["height"], P["sill"]
    if shape == "round":
        w = h = min(w, h)
    fw, fd = P["frame_width"], P["frame_depth"]
    if P["frame_style"] == "molded":
        frame = _molded_bezel(K.opening2d(shape, w, h, 14), fw, fd, P["frame_role"], s)
    else:
        outline, holes = _frame_polygon(shape, w, h, fw, True)
        frame = _extrude_xz([(x, z + s) for x, z in outline], [[(x, z + s) for x, z in hh] for hh in holes], 0.0, fd, P["frame_role"])
    nodes = [Node("window_frame", frame)]
    det = K.Mesh()
    inner = K.opening2d(shape, w, h, 14)
    if P["glass"]:
        det.merge(_extrude_xz([(x * 0.99, z * 0.99 + s + h * 0.005) for x, z in inner], [], fd * 0.55, fd * 0.55 + 0.012, "glass"))
    clip = (shape in ("rect", "rounded_rect"))
    for i in range(P["mullions_x"]):
        x = -w / 2 + w * (i + 1) / (P["mullions_x"] + 1)
        mh = h * 0.98 if clip else h * 0.98 * math.sqrt(max(0.05, 1 - (2 * x / w) ** 2))
        det.merge(K.box(x, fd * 0.5, s + h / 2, 0.04, fd * 0.3, mh, P["frame_role"]))
    for i in range(P["mullions_z"]):
        z = h * (i + 1) / (P["mullions_z"] + 1)
        mw = w * 0.98 if clip else w * 0.98 * math.sqrt(max(0.05, 1 - (2 * z / h - 1) ** 2))
        det.merge(K.box(0, fd * 0.5, s + z, mw, fd * 0.3, 0.04, P["frame_role"]))
    if P["ledge"]:
        det.merge(K.box(0, -0.04, s - fw - 0.03, w + 2 * fw + 0.08, 0.14, 0.05, P["frame_role"]))
    if P["shutters"]:
        for sx in (-1, 1):
            det.merge(K.box(sx * (w / 2 + fw + w * 0.26), -0.03, s + h / 2, w * 0.5, 0.03, h + fw, "wood"))
    nodes.append(Node("window_detail", det))
    if P["view_card"]:
        cw, ch = w + 2 * fw + 1.2, h + 2 * fw + 0.9
        card = K.card(cw, ch, "view", facing="-y").translate(0, fd + 0.6, s - fw - 0.45)
        nodes.append(Node("view", card, "card"))
    return finalize(nodes, {"sill": round(s, 4), "opening_width": round(w, 4), "opening_height": round(h, 4)},
                    center_y=False, ground=False)


# ------------------------------------------------------------------ stairs
@register("arch.stairs", V, "structure", {
    "kind": S.enum("straight", ["straight", "spiral"]), "steps": S.integer(10, 2, 20),
    "rise": S.num(0.18, 0.1, 0.25), "run": S.num(0.28, 0.2, 0.4), "width": S.num(1.0, 0.6, 3.0),
    "stringer": S.enum("solid", ["solid", "open"]), "railing": S.enum("right", ["none", "left", "right", "both"]),
    "role": S.enum("step", ["step", "wood", "stone", "metal", "body"]), "rail_role": S.enum("rail", ["rail", "metal", "wood", "chrome"]),
}, "Stairs: straight (solid blocks or open treads + stringers) or spiral around a column; railings.")
def stairs(P, seed):
    n, rise, run, w = P["steps"], P["rise"], P["run"], P["width"]
    role = P["role"]
    m = K.Mesh()
    rail = K.Mesh()
    if P["kind"] == "straight":
        for i in range(n):
            z1 = rise * (i + 1)
            y = -n * run / 2 + run * (i + 0.5)
            if P["stringer"] == "solid":
                m.merge(K.box(0, y, z1 / 2, w, run + 0.004, z1, role))
            else:
                m.merge(K.box(0, y, z1 - 0.025, w - 0.14, run * 0.95, 0.05, role))
        if P["stringer"] == "open":
            Ls = math.hypot(n * run, n * rise)
            ang = math.atan2(n * rise, n * run)
            for sx in (-1, 1):
                m.merge(K.box(0, 0, 0, 0.06, Ls, 0.2, role).rotate_x(ang).translate(sx * (w / 2 - 0.03), 0, n * rise / 2 - 0.02))
        sides = {"none": [], "left": [-1], "right": [1], "both": [-1, 1]}[P["railing"]]
        for sx in sides:
            x = sx * (w / 2 + 0.05)
            idx = sorted(set(list(range(0, n, max(1, n // 4))) + [n - 1]))
            pts = []
            for i in idx:
                y = -n * run / 2 + run * (i + 0.5)
                z = rise * (i + 1)
                rail.merge(post(x, y, z - 0.05, z + 0.9, 0.02, P["rail_role"], 4))
                pts.append((x, y, z + 0.9))
            rail.merge(K.tube([pts[0], pts[-1]], 0.028, 4, P["rail_role"]))
    else:
        R = w
        col_r = 0.12
        m.merge(K.cylinder(0, 0, 0, col_r, rise * n + 0.3, 8, "metal" if role != "stone" else "stone"))
        dth = math.radians(30)
        for i in range(n):
            a0 = i * dth
            z1 = rise * (i + 1)
            pts = [(col_r * 0.5 * math.cos(a0 + dth / 2), col_r * 0.5 * math.sin(a0 + dth / 2))]
            for kk in range(3):
                a = a0 + dth * kk / 2 * 1.02
                pts.append((R * math.cos(a), R * math.sin(a)))
            m.merge(K.prism(pts, z1 - 0.06, z1, role))
        if P["railing"] != "none":
            pts = [(R * 1.03 * math.cos(i * dth), R * 1.03 * math.sin(i * dth), rise * i + 0.95) for i in range(0, n + 1, 2)]
            rail.merge(K.tube(pts, 0.025, 4, P["rail_role"]))
            for i in range(0, n, 3):
                a = i * dth + dth / 2
                rail.merge(post(R * 1.03 * math.cos(a), R * 1.03 * math.sin(a), rise * (i + 1) - 0.03, rise * (i + 1) + 0.95, 0.018, P["rail_role"], 4))
    return finalize([Node("stairs", m), Node("stair_rail", rail)], {"total_rise": round(rise * n, 4), "steps": n})


# ------------------------------------------------------------------ roof
def _roof_mesh(kind, w, d, pitch_deg, over, t, role, z0=0.0):
    W2, D2 = w / 2 + over, d / 2 + over
    rise = math.tan(math.radians(pitch_deg)) * min(W2, D2)
    if kind == "gable":
        along_x = w >= d
        half = D2 if along_x else W2
        rr = math.tan(math.radians(pitch_deg)) * half
        tt = min(t, half * 0.3)
        inner_apex = max(rr * 0.35, rr - tt * 1.4)
        prof = [(-half, 0.0), (-half + tt * 1.2, 0.0), (0.0, inner_apex), (half - tt * 1.2, 0.0), (half, 0.0), (0.0, rr)]
        Lh = W2 if along_x else D2
        if along_x:
            m = _yz_prism([(a, b + z0) for a, b in prof], -Lh, Lh, role)
        else:
            m = _extrude_xz([(a, b + z0) for a, b in prof], [], -Lh, Lh, role)
        return m, rr
    if kind == "hip":
        pts = [(-W2, -D2, z0), (W2, -D2, z0), (W2, D2, z0), (-W2, D2, z0)]
        if abs(W2 - D2) < 1e-6:
            vs = pts + [(0, 0, z0 + rise)]
            faces = [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
        elif w >= d:
            vs = pts + [(-(W2 - D2), 0, z0 + rise), ((W2 - D2), 0, z0 + rise)]
            faces = [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)]
        else:
            vs = pts + [(0, -(D2 - W2), z0 + rise), (0, (D2 - W2), z0 + rise)]
            faces = [(0, 3, 2, 1), (0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5)]
        return K.Mesh().add(vs, faces, role).orient_outward(), rise
    if kind == "shed":
        r2 = math.tan(math.radians(pitch_deg)) * 2 * D2 * 0.5
        prof = [(-D2, 0.0), (D2, 0.0), (D2, t), (-D2, r2 + t)]
        return _yz_prism([(a, b + z0) for a, b in prof], -W2, W2, role), r2 + t
    if kind == "flat":
        return K.box(0, 0, z0 + t / 2, 2 * W2, 2 * D2, t, role), t
    if kind == "dome":
        m = K.lathe([(0, z0), (0.5, z0), (0.47, z0 + rise * 0.35), (0.35, z0 + rise * 0.75), (0.18, z0 + rise * 0.95), (0, z0 + rise)],
                    12, role, rx=2 * W2, ry=2 * D2)
        return m, rise
    m = K.lathe([(0, z0), (0.5, z0), (0, z0 + rise * 1.4)], 10, role, smooth=False, rx=2 * W2, ry=2 * D2)
    return m, rise * 1.4


def _yz_prism(pts_yz, x0, x1, role):
    """Extrude a (y, z) outline along x (closed solid)."""
    m = K.prism(pts_yz, x0, x1, role)
    m.apply(lambda v: np.stack([v[:, 2], v[:, 0], v[:, 1]], 1))
    return m.orient_outward()


@register("arch.roof", V, "arch", {
    "kind": S.enum("gable", ["gable", "hip", "shed", "flat", "dome", "cone"]),
    "width": S.num(4.0, 1.0, 12.0), "depth": S.num(3.0, 1.0, 12.0), "pitch": S.num(35.0, 10.0, 60.0),
    "overhang": S.num(0.3, 0.0, 1.0), "thickness": S.num(0.15, 0.05, 0.4),
    "role": S.enum("roof", ["roof", "wood", "stone", "metal", "snow", "body"]),
}, "Standalone roof (closed solid): gable, hip, shed, flat, dome, cone.")
def roof(P, seed):
    m, _ = _roof_mesh(P["kind"], P["width"], P["depth"], P["pitch"], P["overhang"], P["thickness"], P["role"])
    return finalize([Node("roof", m)])


# ------------------------------------------------------------------ corridor
@register("arch.corridor", V, "structure", {
    "section": S.enum("rect", ["rect", "rounded", "round", "arch"]),
    "length": S.num(4.0, 1.0, 12.0), "width": S.num(1.6, 1.0, 4.0), "height": S.num(2.5, 2.0, 4.0),
    "curve_deg": S.num(0.0, -90.0, 90.0), "segments": S.integer(6, 2, 12),
    "floor_role": S.enum("floor", ["floor", "stone", "wood", "dirt"]), "wall_role": S.enum("wall", STRUCT),
}, "Corridor interior shell (one-sided, open ends): rect/rounded/round/arch section, straight or curved.",
    origin="room_floor",
    rules=lambda P: ("curved corridor too tight: inner wall radius %.2f m < 0.30 m (bend radius = length / curve)"
                     % (P["length"] / abs(math.radians(P["curve_deg"])) - P["width"] / 2))
    if abs(P["curve_deg"]) > 1e-6 and P["length"] / abs(math.radians(P["curve_deg"])) - P["width"] / 2 < 0.30 else None)
def corridor(P, seed):
    w, h, L = P["width"], P["height"], P["length"]
    sec = P["section"]
    if sec == "rect":
        wall_pts = [(w / 2, 0), (w / 2, h), (-w / 2, h), (-w / 2, 0)]
    elif sec == "rounded":
        r = min(w / 2 * 0.85, h / 3)
        k45 = 1 - math.cos(math.pi / 4)
        wall_pts = [(w / 2, 0), (w / 2, h - r), (w / 2 - r * k45, h - r * k45), (w / 2 - r, h), (-w / 2 + r, h),
                    (-w / 2 + r * k45, h - r * k45), (-w / 2, h - r), (-w / 2, 0)]
    else:
        R = w / 2
        hs = max(0.3, h - R) if sec == "arch" else max(0.0, h - R)
        arc = [(R * math.cos(a), hs + R * math.sin(a)) for a in np.linspace(0, math.pi, 7)]
        wall_pts = _dedupe([(w / 2, 0)] + arc + [(-w / 2, 0)])
    nseg = P["segments"]
    ang = math.radians(P["curve_deg"])
    frames = []
    for i in range(nseg + 1):
        t = i / nseg
        if abs(ang) < 1e-6:
            frames.append((np.array([0.0, -L / 2 + L * t]), np.array([1.0, 0.0])))
        else:
            Rc = L / ang
            th = ang * t
            p = np.array([Rc - Rc * math.cos(th), Rc * math.sin(th) - L / 2 * 0])
            tang = np.array([math.sin(th), math.cos(th)])
            right = np.array([tang[1], -tang[0]])
            frames.append((p, right))

    def ring(pts, fr):
        p, right = fr
        return [(p[0] + right[0] * x, p[1] + right[1] * x, z) for x, z in pts]
    walls = K.Mesh()
    floor = K.Mesh()
    for i in range(nseg):
        a, b = ring(wall_pts, frames[i]), ring(wall_pts, frames[i + 1])
        for j in range(len(wall_pts) - 1):
            walls.add([a[j], a[j + 1], b[j + 1], b[j]], [(0, 1, 2, 3)], P["wall_role"])
        fa = ring([(w / 2, 0), (-w / 2, 0)], frames[i])
        fb = ring([(w / 2, 0), (-w / 2, 0)], frames[i + 1])
        floor.add([fa[0], fb[0], fb[1], fa[1]], [(0, 1, 2, 3)], P["floor_role"])
    centres = []
    for i in range(nseg):
        p0, _ = frames[i]
        p1, _ = frames[i + 1]
        centres.append(((p0 + p1) / 2))
    nw = len(wall_pts) - 1
    for i in range(len(walls.f)):
        cc = centres[i // nw]
        f = walls.f[i]
        V3 = np.asarray([walls.v[j] for j in f])
        nrm = np.cross(V3[1] - V3[0], V3[2] - V3[0])
        target = np.array([cc[0], cc[1], h * 0.45])
        if np.dot(nrm, target - V3.mean(0)) < 0:
            walls.f[i] = tuple(reversed(f))
    for i, f in enumerate(floor.f):
        V3 = np.asarray([floor.v[j] for j in f])
        if np.cross(V3[1] - V3[0], V3[2] - V3[0])[2] < 0:
            floor.f[i] = tuple(reversed(f))
    return finalize([Node("corridor_floor", floor, "shell"), Node("corridor_walls", walls, "shell")],
                    {"section": sec, "ends": "open"}, ground=False)


# ------------------------------------------------------------------ railing / fence
@register("arch.railing", V, "arch", {
    "path": S.enum("straight", ["straight", "arc"]), "length": S.num(3.0, 0.5, 10.0),
    "radius": S.num(3.0, 0.5, 10.0), "arc_deg": S.num(90.0, 15.0, 180.0), "height": S.num(1.0, 0.4, 1.4),
    "post_spacing": S.num(1.2, 0.4, 2.5), "post_shape": S.enum("round", ["round", "square"]),
    "rails": S.integer(2, 1, 3), "infill": S.enum("none", ["none", "bars", "panels", "picket"]),
    "role": S.enum("rail", ["rail", "metal", "wood", "chrome", "stone"]),
}, "Railing/fence along a straight or arc path: posts, rails, infill (bars, glass panels, pickets).",
    rules=lambda P: ("arc railing span %.2f m exceeds the 16 m arch-class extent"
                     % (2 * P["radius"] * math.sin(math.radians(min(P["arc_deg"], 180.0)) / 2) + 0.06))
    if P["path"] == "arc" and 2 * P["radius"] * math.sin(math.radians(min(P["arc_deg"], 180.0)) / 2) + 0.06 > 15.9 else None)
def railing(P, seed):
    h = P["height"]
    role = P["role"]
    if P["path"] == "straight":
        L = P["length"]
        pts = lambda t: np.array([-L / 2 + L * t, 0.0])
        total = L
    else:
        R, A = P["radius"], math.radians(P["arc_deg"])
        pts = lambda t: np.array([R * math.cos(-A / 2 + A * t), R * math.sin(-A / 2 + A * t)])
        total = R * A
    n = min(8, max(1, int(round(total / P["post_spacing"]))))
    m = K.Mesh()
    sq = P["post_shape"] == "square"
    for i in range(n + 1):
        p = pts(i / n)
        m.merge(post(p[0], p[1], 0, h + 0.03, 0.03, role, 4, square=sq))
    # Budget-aware level of detail (class limit 300): posts 12 tris each, rail = 8*segs+4 tris,
    # bar 8 / picket 12 / panel 12 tris. Curve smoothness first, then as many infill pieces as fit.
    cap = 298
    post_tris = (n + 1) * 12
    panel_tris = n * 12 if P["infill"] == "panels" else 0
    per = {"bars": 8, "picket": 12}.get(P["infill"], 0)
    if P["path"] == "straight":
        segs = 1
    else:
        avail = cap - post_tris - panel_tris - 2 * per
        segs = max(2, min(2 * n, (avail // max(1, P["rails"]) - 4) // 8))
    rail_tris = P["rails"] * (8 * segs + 4)
    nb = 0
    if per:
        want = min(10, max(2, int(total / (0.14 if P["infill"] == "bars" else 0.18))))
        nb = max(0, min(want, (cap - post_tris - rail_tris) // per))
    samples = [pts(i / segs) for i in range(segs + 1)]
    for r in range(P["rails"]):
        z = h - r * (h * 0.7 / max(1, P["rails"]))
        m.merge(K.tube([(p[0], p[1], z) for p in samples], 0.022, 4, role))
    inf = K.Mesh()
    if P["infill"] in ("bars", "picket"):
        for i in range(nb):
            p = pts((i + 0.5) / nb)
            if P["infill"] == "picket":
                inf.merge(K.box(p[0], p[1], h * 0.42 + 0.02, 0.07, 0.025, h * 0.84, role))
            else:
                inf.merge(post(p[0], p[1], 0.04, h - 0.05, 0.01, role, 3))
    elif P["infill"] == "panels":
        for i in range(n):
            a, b = pts(i / n), pts((i + 1) / n)
            mid = (a + b) / 2
            seg = b - a
            ln = float(np.linalg.norm(seg))
            yaw = math.atan2(seg[1], seg[0])
            inf.merge(K.box(0, 0, 0, max(0.05, ln - 0.08), 0.015, h * 0.7, "glass").rotate_z(yaw).translate(mid[0], mid[1], h * 0.45))
    return finalize([Node("railing", m), Node("railing_infill", inf)])


# ------------------------------------------------------------------ pier / bridge
@register("arch.pier", V, "structure", {
    "length": S.num(6.0, 2.0, 20.0), "width": S.num(2.0, 1.0, 4.0), "deck_height": S.num(1.0, 0.3, 3.0),
    "pile_spacing": S.num(2.0, 1.0, 4.0), "planks": S.boolean(True), "ladder": S.boolean(True), "end_posts": S.boolean(True),
    "deck_role": S.enum("wood", ["wood", "stone", "metal", "floor"]), "pile_role": S.enum("post", ["post", "wood", "stone", "metal"]),
}, "Pier/jetty: piles, deck (planks or slab), ladder, end posts.")
def pier(P, seed):
    L, w, dh = P["length"], P["width"], P["deck_height"]
    r = rng(seed, "pier")
    deck = K.Mesh()
    if P["planks"]:
        n = min(16, max(4, int(L / 0.8)))
        for i in range(n):
            y = -L / 2 + L * (i + 0.5) / n
            dz = (r.random() - 0.5) * 0.02
            deck.merge(K.box(0, y, dh - 0.04 + dz, w + (r.random() - 0.5) * 0.1, L / n - 0.03, 0.06, P["deck_role"]))
    else:
        deck.merge(K.box(0, 0, dh - 0.06, w, L, 0.12, P["deck_role"]))
    piles = K.Mesh()
    n = min(6, max(1, int(L / P["pile_spacing"])))
    for i in range(n + 1):
        y = -L / 2 + 0.15 + (L - 0.3) * i / n
        for sx in (-1, 1):
            top = dh - 0.08 + (0.5 if (P["end_posts"] and i == n) else 0.0)
            piles.merge(post(sx * (w / 2 - 0.1), y, 0.0, top, 0.09, P["pile_role"], 5))
    if P["ladder"]:
        x = w / 2 + 0.06
        for sy in (-0.2, 0.2):
            piles.merge(K.box(x, -L / 2 + 1.0 + sy, dh / 2, 0.05, 0.05, dh + 0.02, P["pile_role"]))
        for kk in range(max(1, int(dh / 0.3))):
            piles.merge(K.box(x, -L / 2 + 1.0, 0.25 + kk * 0.3, 0.04, 0.44, 0.04, P["pile_role"]))
    return finalize([Node("pier_deck", deck), Node("pier_piles", piles)], {"deck_height": dh})


@register("arch.bridge", V, "structure", {
    "kind": S.enum("arched", ["flat", "arched", "rope"]), "span": S.num(6.0, 2.0, 20.0), "width": S.num(1.6, 0.8, 4.0),
    "rise": S.num(1.0, 0.0, 3.0), "railing": S.boolean(True), "segments": S.integer(8, 4, 12),
    "deck_role": S.enum("wood", ["wood", "stone", "metal", "floor"]), "rail_role": S.enum("rail", ["rail", "rope", "wood", "metal", "stone"]),
}, "Bridge: flat beam, arched (ribs) or rope-sag span with railings and end posts.")
def bridge(P, seed):
    L, w = P["span"], P["width"]
    n = P["segments"]
    k = P["kind"]

    def zf(t):
        if k == "flat":
            return 0.6
        if k == "arched":
            return 0.6 + P["rise"] * math.sin(math.pi * t)
        return 0.6 + P["rise"] * 0.6 * (1 - math.sin(math.pi * t))
    deck = K.Mesh()
    for i in range(n):
        t0, t1 = i / n, (i + 1) / n
        y0, y1 = -L / 2 + L * t0, -L / 2 + L * t1
        z0, z1 = zf(t0), zf(t1)
        seg = K.box(0, 0, 0, w, math.hypot(y1 - y0, z1 - z0) + 0.02, 0.12, P["deck_role"])
        seg.rotate_x(math.atan2(z1 - z0, y1 - y0)).translate(0, (y0 + y1) / 2, (z0 + z1) / 2)
        deck.merge(seg)
    sup = K.Mesh()
    for sy in (-1, 1):
        for sx in (-1, 1):
            top = zf(0 if sy < 0 else 1) + (1.2 if k == "rope" else 0.0)
            sup.merge(post(sx * (w / 2 - 0.1), sy * (L / 2 - 0.1), 0.0, top, 0.1,
                           P["rail_role"] if k == "rope" else P["deck_role"], 6, square=k != "rope"))
    if k == "arched" and P["rise"] > 0.15:
        under = [(-L / 2 + 0.25, 0.0), (L / 2 - 0.25, 0.0)] + \
                [(-L / 2 + 0.25 + (L - 0.5) * i / 10, zf(0.04 + 0.92 * i / 10) - 0.12) for i in range(10, -1, -1)]
        rib = _yz_prism(_dedupe(under), -0.06, 0.06, P["deck_role"])
        for sx in (-1, 1):
            sup.merge(rib.copy().translate(sx * (w / 2 - 0.08), 0, 0))
    rail = K.Mesh()
    if P["railing"]:
        for sx in (-1, 1):
            x = sx * (w / 2 - 0.03)
            idx = sorted(set(list(range(0, n + 1, 2)) + [n]))
            pts = [(x, -L / 2 + L * i / n, zf(i / n) + 0.9) for i in idx]
            rail.merge(K.tube(pts, 0.025 if k != "rope" else 0.022, 4, P["rail_role"]))
            for i in sorted(set(list(range(0, n + 1, 4)) + [n])):
                y = -L / 2 + L * i / n
                rail.merge(post(x, y, zf(i / n) - 0.02, zf(i / n) + 0.88, 0.016, P["rail_role"], 4))
    return finalize([Node("bridge_deck", deck), Node("bridge_supports", sup), Node("bridge_rail", rail)])


# ------------------------------------------------------------------ column
@register("arch.column", V, "arch", {
    "shape": S.enum("round", ["round", "square", "organic"]), "height": S.num(3.0, 1.0, 6.0), "radius": S.num(0.2, 0.08, 0.8),
    "base": S.boolean(True), "capital": S.boolean(True), "flare": S.num(0.5, 0.0, 1.0, "organic flare at top/bottom"),
    "role": S.enum("stone", ["stone", "wood", "metal", "body", "wall", "chrome"]),
}, "Column: round/square shaft, base, capital; 'organic' = smooth flared trunk (molded interiors).")
def column(P, seed):
    h, r = P["height"], P["radius"]
    role = P["role"]
    m = K.Mesh()
    if P["shape"] == "organic":
        f = P["flare"]
        prof = [(0, 0), (r * (1 + 2.2 * f), 0), (r * (1 + 0.6 * f), h * 0.12), (r, h * 0.3), (r * 0.95, h * 0.6),
                (r * (1 + 0.8 * f), h * 0.88), (r * (1 + 2.6 * f), h), (0, h)]
        m.merge(K.lathe(prof, 10, role))
    elif P["shape"] == "square":
        m.merge(K.box(0, 0, h / 2, 2 * r, 2 * r, h - 0.02, role))
        if P["base"]:
            m.merge(K.box(0, 0, 0.08, 2.6 * r, 2.6 * r, 0.16, role))
        if P["capital"]:
            m.merge(K.box(0, 0, h - 0.08, 2.8 * r, 2.8 * r, 0.16, role))
    else:
        m.merge(K.cylinder(0, 0, 0.02, r, h - 0.04, 10, role))
        if P["base"]:
            m.merge(K.lathe([(0, 0), (r * 1.4, 0), (r * 1.4, 0.1), (r * 1.1, 0.18), (0, 0.18)], 10, role, smooth=False))
        if P["capital"]:
            m.merge(K.lathe([(0, h - 0.2), (r * 1.1, h - 0.2), (r * 1.5, h - 0.08), (r * 1.5, h), (0, h)], 10, role, smooth=False))
    return finalize([Node("column", m)])


# ------------------------------------------------------------------ house (exterior building)
@register("arch.house", V, "building", {
    "plan": S.enum("rect", ["rect", "round", "oval"]), "width": S.num(5.0, 2.0, 12.0), "depth": S.num(4.0, 2.0, 12.0),
    "wall_height": S.num(2.8, 1.5, 6.0), "roof": S.enum("gable", ["gable", "hip", "dome", "cone", "flat"]),
    "roof_pitch": S.num(35.0, 15.0, 55.0), "overhang": S.num(0.35, 0.0, 1.0),
    "door_side": S.enum("s", ["n", "e", "s", "w"]), "windows": S.integer(2, 0, 4),
    "window_shape": S.enum("rect", ["rect", "rounded_rect", "oval", "round", "arch"]),
    "lit_windows": S.boolean(True), "chimney": S.boolean(False), "foundation": S.boolean(True), "beams": S.boolean(False),
    "wall_role": S.enum("wall", STRUCT + ["snow"]), "roof_role": S.enum("roof", ["roof", "wood", "stone", "metal", "snow", "body"]),
}, "Exterior building (closed solids): rect cottage / round dome shelter / oval hut; roof types; door, lit windows, chimney, beams.")
def house(P, seed):
    plan, w, d, wh = P["plan"], P["width"], P["depth"], P["wall_height"]
    if plan == "round":
        w = d = min(w, d)
    wr = P["wall_role"]
    k = 4 if plan == "rect" else 16
    outline = K.plan2d(plan, w, d, k)
    base_z = 0.25 if P["foundation"] else 0.0
    walls = K.Mesh()
    walls.merge(K.prism(outline, base_z, wh, wr))
    if P["foundation"]:
        walls.merge(K.prism(K.plan2d(plan, w + 0.2, d + 0.2, k), 0.0, base_z + 0.03, "stone"))
    roof_kind = P["roof"]
    if plan != "rect" and roof_kind in ("gable", "hip"):
        roof_kind = "cone"
    rm, rise = _roof_mesh(roof_kind, w, d, P["roof_pitch"], P["overhang"] if roof_kind != "dome" else 0.03, 0.15,
                          P["roof_role"], z0=wh - 0.03)
    det = K.Mesh()
    glow = K.Mesh()
    side_ang = {"e": 0.0, "n": 90.0, "w": 180.0, "s": 270.0}

    def facade(ang_deg):
        a = math.radians(ang_deg)
        if plan == "rect":
            dx, dy = math.cos(a), math.sin(a)
            tx = (w / 2) / abs(dx) if abs(dx) > 1e-9 else 1e9
            ty = (d / 2) / abs(dy) if abs(dy) > 1e-9 else 1e9
            t = min(tx, ty)
            n = np.array([1.0 if dx > 0 else -1.0, 0.0]) if tx < ty else np.array([0.0, 1.0 if dy > 0 else -1.0])
            return np.array([dx * t, dy * t]), n
        rx, ry = w / 2, d / 2
        p = np.array([rx * math.cos(a), ry * math.sin(a)])
        n = np.array([math.cos(a) / rx, math.sin(a) / ry])
        return p, n / np.linalg.norm(n)

    def place(part, p, n, out=0.03):
        yaw = math.atan2(n[1], n[0]) + math.pi / 2
        part.rotate_z(yaw).translate(p[0] + n[0] * out, p[1] + n[1] * out, 0)
        return part
    p, n = facade(side_ang[P["door_side"]])
    dw, dh = min(1.0, w * 0.3), min(2.0, (wh - base_z) * 0.8)
    det.merge(place(K.box(0, 0, base_z + dh / 2, dw, 0.12, dh, "door"), p, n, 0.02))
    det.merge(place(K.box(0, 0.02, base_z + dh / 2 + 0.04, dw + 0.18, 0.1, dh + 0.12, "frame"), p, n, 0.0))
    sides = [s for s in ("s", "e", "n", "w") if s != P["door_side"]]
    nw = P["windows"]
    for i in range(nw):
        sd = sides[i % 3]
        a = side_ang[sd] + (((i // 3) * 2 - 1) * 18.0 if nw > 3 and sd == sides[0] else 0.0)
        p2, n2 = facade(a)
        ww, whh = min(0.9, w * 0.2), min(0.8, (wh - base_z) * 0.3)
        zc = base_z + (wh - base_z) * 0.42
        pane = _extrude_xz([(x, z + zc) for x, z in K.opening2d(P["window_shape"], ww, whh, 10)], [], -0.03, 0.03,
                           "light" if P["lit_windows"] else "glass")
        fr = _extrude_xz([(x, z + zc - 0.06) for x, z in K.opening2d(P["window_shape"], ww + 0.14, whh + 0.12, 10)], [], 0.0, 0.05, "frame")
        glow.merge(place(pane, p2, n2, 0.03))
        det.merge(place(fr, p2, n2, 0.0))
    if P["chimney"]:
        cx, cy = (w * 0.25, d * 0.12) if plan == "rect" else (w * 0.18, 0.0)
        ch_top = wh + rise * 0.85 + 0.35
        det.merge(K.box(cx, cy, (wh * 0.6 + ch_top) / 2, 0.45, 0.45, ch_top - wh * 0.6, "stone"))
    if P["beams"] and plan == "rect":
        for sx in (-1, 1):
            for sy in (-1, 1):
                det.merge(K.box(sx * (w / 2 + 0.02), sy * (d / 2 + 0.02), (wh + base_z) / 2, 0.16, 0.16, wh - base_z - 0.02, "trim"))
        for sy in (-1, 1):
            det.merge(K.box(0, sy * (d / 2 + 0.035), wh - 0.12, w - 0.2, 0.1, 0.14, "trim"))
    nodes = [Node("house_walls", walls), Node("house_roof", rm), Node("house_detail", det), Node("house_windows", glow)]
    return finalize(nodes, {"door_side": P["door_side"], "eave_height": wh, "ridge_height": round(wh + rise, 3)})


# ------------------------------------------------------------------ tower (exterior landmark, additive 3.2)
@register("arch.tower", V, "building", {
    "height": S.num(14.0, 4.0, 30.0), "radius": S.num(1.6, 0.6, 4.0), "taper": S.num(0.7, 0.4, 1.0),
    "segments": S.lod(S.integer(12, 8, 16)), "bands": S.integer(3, 0, 6),
    "gallery": S.boolean(True, "railed walkway ring below the top"), "lantern": S.boolean(True, "glazed lit lantern room"),
    "cap": S.enum("cone", ["cone", "dome", "flat"]), "windows": S.integer(3, 0, 6), "door": S.boolean(True),
    "body_role": S.enum("wall", STRUCT + ["snow"]), "band_role": S.enum("trim", STRUCT + ["chrome", "band"]),
    "cap_role": S.enum("roof", ["roof", "metal", "chrome", "body", "stone", "snow"]),
    "rail_role": S.enum("rail", ["rail", "metal", "chrome", "wood"]),
}, "Tall landmark tower (closed solids): tapered round body with bold bands, gallery ring + rail posts, glazed lit "
   "lantern room, cone/dome cap, lit slit windows, door. Reads from 60 m: lighthouse, observatory, beacon.")
def tower(P, seed):
    H, R, tp, k = P["height"], P["radius"], P["taper"], P["segments"]
    lant = P["lantern"]
    body_h = H * (0.78 if lant else 0.9)
    body = K.lathe([(0, 0), (R * 1.18, 0), (R * 1.18, 0.35), (R, 0.4), (R * tp, body_h), (0, body_h)], k, P["body_role"], smooth=True)
    det = K.Mesh()
    glow = K.Mesh()
    nb = P["bands"]
    for i in range(nb):
        z0 = body_h * (0.18 + 0.7 * i / max(1, nb))
        z1 = z0 + body_h * 0.07
        r0 = R + (R * tp - R) * z0 / body_h
        r1 = R + (R * tp - R) * z1 / body_h
        det.merge(K.lathe([(0, z0), (r0 + 0.04, z0), (r1 + 0.04, z1), (0, z1)], k, P["band_role"], smooth=True))
    top_r = R * tp
    z = body_h
    if P["gallery"]:
        det.merge(K.lathe([(0, z), (top_r * 1.45, z), (top_r * 1.45, z + 0.18), (0, z + 0.18)], k, P["band_role"], smooth=False))
        for i in range(8):
            a = math.tau * i / 8
            det.merge(K.box(math.cos(a) * top_r * 1.38, math.sin(a) * top_r * 1.38, z + 0.59, 0.07, 0.07, 0.8, P["rail_role"]))
        det.merge(K.lathe([(top_r * 1.33, z + 1.0), (top_r * 1.43, z + 1.0), (top_r * 1.43, z + 1.08), (top_r * 1.33, z + 1.08)], k,
                          P["rail_role"], smooth=False))
        z += 0.18
    if lant:
        lh = H * 0.12
        glow.merge(K.lathe([(0, z), (top_r * 0.85, z), (top_r * 0.85, z + lh), (0, z + lh)], max(8, k - 4), "light", smooth=False))
        for i in range(6):
            a = math.tau * i / 6
            det.merge(K.box(math.cos(a) * top_r * 0.86, math.sin(a) * top_r * 0.86, z + lh / 2, 0.08, 0.08, lh, P["band_role"]))
        z += lh
    if P["cap"] == "cone":
        det.merge(K.lathe([(0, z), (top_r * 1.05, z), (0, z + H * 0.1)], k, P["cap_role"], smooth=False))
    elif P["cap"] == "dome":
        det.merge(K.lathe([(0, z), (top_r * 1.0, z), (top_r * 0.8, z + top_r * 0.6), (top_r * 0.4, z + top_r * 0.92), (0, z + top_r)], k,
                          P["cap_role"], smooth=True))
    else:
        det.merge(K.lathe([(0, z), (top_r * 1.05, z), (top_r * 1.05, z + 0.15), (0, z + 0.15)], k, P["cap_role"], smooth=False))
    for i in range(P["windows"]):
        zc = body_h * (0.3 + 0.55 * (i + 0.5) / max(1, P["windows"]))
        rr = R + (R * tp - R) * zc / body_h
        a = math.pi * 0.5 + (i % 2) * 0.9 - 0.45
        pane = _extrude_xz(K.opening2d("arch", 0.32, 0.6, 8), [], -0.02, 0.04, "light")
        glow.merge(pane.rotate_z(a + math.pi / 2).translate(math.cos(a) * (rr + 0.01), math.sin(a) * (rr + 0.01), zc - 0.3))
    if P["door"]:
        a = -math.pi / 2
        det.merge(K.box(math.cos(a) * (R + 0.05), math.sin(a) * (R + 0.05), 0.4 + 0.9, 0.9, 0.1, 1.8, "door"))
    nodes = [Node("tower_body", body), Node("tower_detail", det), Node("tower_glow", glow)]
    return finalize(nodes, {"height_m": round(H, 3), "lantern": lant}, center_x=True, center_y=True)
