"""Terrain patches and water planes (theme-agnostic; surface = material role)."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .genutil import finalize
from .rng import sub_seed

V = "3.0.0"


def _noise2(seed, n, lat=4):
    rs = np.random.default_rng(sub_seed("terrain", seed, lat))
    L = rs.random((lat + 1, lat + 1))
    xs = np.linspace(0, lat, n)
    i0 = np.clip(np.floor(xs).astype(int), 0, lat - 1)
    f = xs - i0
    f = f * f * (3 - 2 * f)
    a = L[i0][:, i0]
    b = L[i0][:, i0 + 1]
    c = L[i0 + 1][:, i0]
    d = L[i0 + 1][:, i0 + 1]
    top = a + (b - a) * f[None, :]
    bot = c + (d - c) * f[None, :]
    return top + (bot - top) * f[:, None]


def heightfield(n, amp, rough, feature, falloff, seed):
    h = 0.65 * _noise2(seed, n, 3) + 0.35 * rough * _noise2(seed + 1, n, 7)
    h = (h - h.mean()) * 2.0
    u = np.linspace(-1, 1, n)
    X, Y = np.meshgrid(u, u)
    R = np.sqrt(X * X + Y * Y)
    if feature == "mounds":
        h += 0.9 * np.exp(-((X - 0.25) ** 2 + (Y + 0.1) ** 2) * 6) + 0.6 * np.exp(-((X + 0.4) ** 2 + (Y - 0.35) ** 2) * 9)
    elif feature == "drifts":
        h += 0.5 * np.sin(X * 3.0 + Y * 1.2 + 0.7) * (0.5 + 0.5 * np.cos(Y * 2.0))
    elif feature == "ridge":
        h += 1.2 * np.exp(-((Y - 0.2 * np.sin(X * 2)) ** 2) * 10)
    elif feature == "crater":
        h += 0.9 * np.exp(-((R - 0.5) ** 2) * 30) - 0.8 * np.exp(-(R ** 2) * 12)
    if falloff > 0:
        edge = np.clip((1 - np.maximum(np.abs(X), np.abs(Y))) / (falloff * 0.5 + 1e-3), 0, 1)
        edge = edge * edge * (3 - 2 * edge)
    else:
        edge = np.ones_like(X)
    return h * amp * edge


def _slab(verts, faces, n, zmin, top_role, side_role, smooth=True):
    m = K.Mesh().add(verts, faces, top_role, smooth)
    ring = [i for i in range(n)] + [i * n + (n - 1) for i in range(1, n)] + \
           [(n - 1) * n + i for i in range(n - 2, -1, -1)] + [i * n for i in range(n - 2, 0, -1)]
    base = len(m.v)
    m.v.extend([(verts[k][0], verts[k][1], zmin) for k in ring])
    L = len(ring)
    for t in range(L):
        a, b = ring[t], ring[(t + 1) % L]
        m.f.append((b, a, base + t, base + (t + 1) % L))
        m.r.append(side_role)
        m.s.append(False)
        m.uv.append(None)
    m.f.append(tuple(base + t for t in reversed(range(L))))
    m.r.append(side_role)
    m.s.append(False)
    m.uv.append(None)
    return m.orient_outward()


@register("terrain.patch", V, "terrain", {
    "size_x": S.num(12.0, 2.0, 60.0), "size_y": S.num(12.0, 2.0, 60.0),
    "resolution": S.lod(S.integer(10, 4, 13, "grid cells per side; closed slab = 2r^2 + 12r - 2 tris (13 -> 492 <= 512)")),
    "amplitude": S.num(0.6, 0.0, 4.0), "roughness": S.num(0.5, 0.0, 1.0),
    "feature": S.enum("none", ["none", "mounds", "drifts", "ridge", "crater"]),
    "edge_falloff": S.num(0.5, 0.0, 1.0, "blend heights to 0 at the edges (tiling)"),
    "depth": S.num(0.5, 0.1, 5.0, "slab depth below the lowest point"),
    "surface": S.enum("grass", ["grass", "snow", "sand", "rock", "dirt", "ice", "floor"]),
}, "Seeded heightfield terrain patch as a closed slab (top surface + skirt + bottom); rest height y=0 at the edges.",
    origin="terrain_center")
def patch(P, seed):
    n = P["resolution"] + 1
    sx, sy = P["size_x"], P["size_y"]
    H = heightfield(n, P["amplitude"], P["roughness"], P["feature"], P["edge_falloff"], seed)
    zmin = float(H.min()) - P["depth"]
    verts = [(-sx / 2 + sx * i / (n - 1), -sy / 2 + sy * j / (n - 1), float(H[j, i])) for j in range(n) for i in range(n)]
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            if (i + j) % 2 == 0:
                faces += [(a, a + 1, a + n + 1), (a, a + n + 1, a + n)]
            else:
                faces += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    side = "rock" if P["surface"] in ("rock", "snow", "ice") else "dirt"
    m = _slab(verts, faces, n, zmin, P["surface"], side)
    return finalize([Node("terrain", m)], {"heights_m": [round(float(H.min()), 3), round(float(H.max()), 3)],
                                           "grid": n, "surface": P["surface"]}, ground=False)


@register("terrain.water", V, "terrain", {
    "shape": S.enum("rect", ["rect", "round", "oval"]), "size_x": S.num(10.0, 1.0, 80.0), "size_y": S.num(10.0, 1.0, 80.0),
    "resolution": S.lod(S.integer(8, 2, 13, "rect: closed slab = 2r^2 + 12r - 2 tris (13 -> 492 <= 512)")),
    "waves": S.num(0.05, 0.0, 0.3), "depth": S.num(0.1, 0.02, 1.0),
    "surface": S.enum("water", ["water", "ice"]),
}, "Water (or ice) plane: thin closed slab with gentle seeded waves; material kind 'water' scrolls UVs in the runtime.",
    origin="terrain_center")
def water(P, seed):
    n = P["resolution"] + 1
    sx, sy = P["size_x"], P["size_y"]
    if P["shape"] == "round":
        sx = sy = min(sx, sy)
    if P["shape"] == "rect":
        H = heightfield(n, P["waves"], 1.0, "none", 0.0, seed)
        verts = [(-sx / 2 + sx * i / (n - 1), -sy / 2 + sy * j / (n - 1), float(H[j, i])) for j in range(n) for i in range(n)]
        faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(n - 1) for i in range(n - 1)]
        m = _slab(verts, faces, n, float(H.min()) - P["depth"], P["surface"], P["surface"])
    else:
        k = 8 + 2 * P["resolution"]
        rs = np.random.default_rng(sub_seed("water", seed))
        rings = []
        for rr, z in ((0.5, 0.0), (0.33, 0.0), (0.16, 0.0)):
            rings.append([(rr * sx * math.cos(math.tau * i / k), rr * sy * math.sin(math.tau * i / k),
                           (P["waves"] * (rs.random() - 0.5) if rr < 0.5 else 0.0)) for i in range(k)])
        top = K.loft(rings, P["surface"], smooth=True, cap0=False, cap1=False)
        c = len(top.v)
        top.v.append((0.0, 0.0, 0.0))
        off = 2 * k
        for i in range(k):
            top.f.append((off + i, off + (i + 1) % k, c))
            top.r.append(P["surface"])
            top.s.append(True)
            top.uv.append(None)
        base = len(top.v)
        zlow = min(p[2] for p in top.v) - P["depth"]
        top.v.extend([(x, y, zlow) for x, y, z in rings[0]])
        for i in range(k):
            a, b = i, (i + 1) % k
            top.f.append((b, a, base + a, base + b))
            top.r.append(P["surface"])
            top.s.append(False)
            top.uv.append(None)
        top.f.append(tuple(base + i for i in range(k)))
        top.r.append(P["surface"])
        top.s.append(False)
        top.uv.append(None)
        m = _orient_any(top)
    return finalize([Node("water", m)], {"surface": P["surface"]}, ground=False)


def _orient_any(m):
    """Make winding consistent (BFS over faces) then orient outward by signed volume."""
    from collections import deque
    key = {}
    vid = []
    for p in m.v:
        kk = (round(p[0] * 1e5), round(p[1] * 1e5), round(p[2] * 1e5))
        vid.append(key.setdefault(kk, len(key)))
    edges = {}
    for fi, f in enumerate(m.f):
        for j in range(len(f)):
            a, b = vid[f[j]], vid[f[(j + 1) % len(f)]]
            edges.setdefault((min(a, b), max(a, b)), []).append(fi)
    seen = [False] * len(m.f)
    for start in range(len(m.f)):
        if seen[start]:
            continue
        seen[start] = True
        q = deque([start])
        while q:
            fi = q.popleft()
            f = m.f[fi]
            dirs = {(vid[f[j]], vid[f[(j + 1) % len(f)]]) for j in range(len(f))}
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
                    q.append(g)
    return m.orient_outward()


# ------------------------------------------------------------------ exterior yard (ROOMLOOK, additive 3.2)
YARD_EXIT = {"wall": S.enum("s", ["n", "e", "s", "w"]), "offset": S.num(0.0, -0.45, 0.45, "fraction along the wall"),
             "width": S.num(2.0, 0.8, 6.0)}
YARD_POND = {"x": S.num(0.0, -0.45, 0.45, "fraction of width"), "y": S.num(0.0, -0.45, 0.45, "fraction of depth"),
             "rx": S.num(1.5, 0.4, 8.0), "ry": S.num(1.0, 0.4, 8.0), "thickness": S.num(0.12, 0.04, 0.6)}


def _yard_rules(P):
    if P["plan"] == "oval" and min(P["width"], P["depth"]) < 4.0:
        return "oval yards need width/depth >= 4 m"
    if P["terraces"] * P["terrace_run"] + P["ridge_run"] > 30.0:
        return "terraces + ridge reach beyond 30 m"
    return None


def _yard_outline(P):
    from .gen_arch import _outline
    return _outline({"plan": P["plan"], "width": P["width"], "depth": P["depth"], "wall_segments": P["segments"]})


def _exit_points(P, out):
    from . import wall2d as W
    from .gen_arch import _wall_span
    Q = {"plan": P["plan"], "width": P["width"], "depth": P["depth"], "wall_segments": P["segments"]}
    path = W.PlanPath(out, 0.0)
    res = []
    for i, e in enumerate(P["exits"]):
        sc, half, L = _wall_span(Q, e["wall"])
        s = (sc + e["offset"] * 2 * half) % L
        p = path.point(s)
        n = path.normal_in(s)
        res.append({"index": i, "s": s, "L": L, "p": p, "n": n, "width": e["width"], "wall": e["wall"]})
    return res, path


def _rows(out, offsets, heights, roles, k, bowl=0.0, radial=None, smooth=False):
    """Loft of outline rings (outward offsets, per-vertex heights) -> one-sided strip facing the yard centre.
    bowl > 0 blends each ring toward an ellipse through the same offset (rounder further out); radial = optional
    per-ring per-vertex extra outward offsets (organic jag) that never reorder rings; smooth = Gouraud (shared
    vertex normals: ledge lips and ridge folds read rounded, hand-sculpted rather than boxed)."""
    from . import wall2d as W
    rings = []
    ang = [math.atan2(y, x) for x, y in out]
    ax = max(abs(x) for x, _ in out)
    ay = max(abs(y) for _, y in out)
    total = max(offsets[-1], 1e-6)
    for j, (off, hz) in enumerate(zip(offsets, heights)):
        ring = W.offset_outline(out, -off) if abs(off) > 1e-6 else out
        t = bowl * min(1.0, off / total) ** 0.8
        pts = []
        for i, ((x, y), z) in enumerate(zip(ring, hz)):
            ex, ey = (ax + off) * math.cos(ang[i]), (ay + off) * math.sin(ang[i])
            px, py = x * (1 - t) + ex * t, y * (1 - t) + ey * t
            if radial is not None and j > 0:
                rr = math.hypot(px, py)
                g = 1.0 + radial[j][i] / max(rr, 1e-6)
                px, py = px * g, py * g
            pts.append((px, py, z))
        rings.append(pts)
    verts = [p for r in rings for p in r]
    faces, fr = [], []
    for j in range(len(rings) - 1):
        for i in range(k):
            i2 = (i + 1) % k
            # uniform winding (outer ring first): treads face up, risers/cliffs face the yard centre
            faces.append(((j + 1) * k + i, (j + 1) * k + i2, j * k + i2, j * k + i))
            fr.append(roles[j])
    return K.Mesh().add(verts, faces, fr, smooth)


@register("terrain.yard", V, "shell", {
    "plan": S.enum("rounded_rect", ["rect", "rounded_rect", "oval"]),
    "width": S.num(12.0, 4.0, 16.0), "depth": S.num(10.0, 4.0, 16.0),
    "segments": S.lod(S.integer(28, 12, 40)), "floor_rings": S.lod(S.integer(3, 1, 6)),
    "terraces": S.integer(2, 0, 3), "terrace_rise": S.num(0.8, 0.2, 3.0), "terrace_run": S.num(2.5, 0.8, 8.0),
    "ridge_height": S.num(7.0, 0.0, 30.0), "ridge_run": S.num(5.0, 1.0, 20.0), "jag": S.num(0.35, 0.0, 0.8),
    "exits": S.array(YARD_EXIT, [], 6), "path_width": S.num(1.4, 0.0, 4.0), "ponds": S.array(YARD_POND, [], 2),
    "view_gap_azimuth": S.num(-1.0, -1.0, 360.0, "azimuth of the fixed camera's view in the kit plane (deg; +x = 0, "
                              "north/+y = 90; -1 = none): the ridge is lowered there so distant layers show"),
    "view_gap_width": S.num(80.0, 20.0, 180.0, "full angular width of the lowered ridge (deg)"),
    "view_gap": S.num(0.0, 0.0, 0.9, "fraction of ridge height removed at the view gap"),
    "bowl": S.num(0.0, 0.0, 1.0, "outer rings round off toward an ellipse (organic valley instead of a walled box)"),
    "ground_role": S.enum("grass", ["grass", "snow", "dirt", "sand", "rock", "field"]),
    "tread_role": S.enum("grass", ["grass", "snow", "dirt", "sand", "rock", "cap", "field"]),
    "cliff_role": S.enum("cliff", ["cliff", "rock", "stone", "ice", "snow"]),
    "cap_role": S.enum("cap", ["cap", "snow", "grass", "rock", "cliff"]),
    "path_role": S.enum("path", ["path", "dirt", "sand", "snow", "stone"]),
    "pond_role": S.enum("ice", ["ice", "water"]),
}, "Exterior yard (one-sided landscape shell): flat playfield (the room grid) ringed by readable terraces/ledges and an "
   "enclosing jagged ridge wall, passes cut where exits are, lighter path strips from exits to the centre, optional ice "
   "slabs/ponds with visible thickness. Meta: exits (placement), paths, terrace/ridge levels, walkable outline.",
    rules=_yard_rules, origin="room_floor")
def yard(P, seed):
    rs = np.random.default_rng(sub_seed("yard", seed))
    out = _yard_outline(P)
    k = len(out)
    exits, path = _exit_points(P, out)
    # exit weight per outline vertex (1 inside the pass, smooth falloff over 2 m of arc)
    svals = []
    acc = 0.0
    for i in range(k):
        svals.append(acc)
        acc += float(np.linalg.norm(np.asarray(out[(i + 1) % k]) - np.asarray(out[i])))
    ew = np.zeros(k)
    for e in exits:
        for i in range(k):
            d = abs(svals[i] - e["s"])
            d = min(d, e["L"] - d)
            t = np.clip((d - e["width"] / 2.0) / 2.0, 0.0, 1.0)
            ew[i] = max(ew[i], 1.0 - t * t * (3 - 2 * t))
    keep = 1.0 - ew
    nodes = []
    ground = K.Mesh()
    rings = int(P["floor_rings"])
    scales = [1.0 - (1.0 - 1.0 / (rings + 1)) * j / rings for j in range(rings + 1)]
    gv = [(x * s, y * s, 0.0) for s in scales for x, y in out]
    gf = [(j * k + i, j * k + (i + 1) % k, (j + 1) * k + (i + 1) % k, (j + 1) * k + i) for j in range(rings) for i in range(k)]
    gf.append(tuple(rings * k + i for i in range(k)))
    ground.add(gv, gf, P["ground_role"])
    nodes.append(Node("ground", ground, "shell"))
    T, rise, run = P["terraces"], P["terrace_rise"], P["terrace_run"]
    offs, hts, roles = [0.0], [np.zeros(k)], []
    fresh = [False]   # rings added by the organic shaping draw from their own stream (rs2)
    z = np.zeros(k)
    jit = lambda a: (rs.random(k) - 0.5) * a
    # organic-detail draws use a separate seeded stream so every original draw (rises, tread jitter, ridge heights,
    # ring jag, path bends) is unchanged: same layout and silhouette, only the shapes of ledges and cliff feet differ
    rs2 = np.random.default_rng(sub_seed("yard-organic", seed))
    jit2 = lambda a: (rs2.random(k) - 0.5) * a
    meta_terr = []
    for j in range(T):
        zt = z + rise * (1.0 + jit(0.3)) * keep
        # organic ledge (N64 look convention: no boxed terraces): a steep sloped riser with a ragged top, then a
        # rounded lip where the tread surface wraps over the edge; the tread keeps its outer offset (layout kept)
        s = min(0.45 * rise, 0.3 * run)
        lip = min(0.2 * rise, 0.12 * run)
        o = offs[-1]
        riser_top = z + (zt - z) * (0.84 + jit2(0.08))
        tread = zt + jit(0.12) * keep
        offs += [o + s, o + s + lip, o + run]
        fresh += [True, True, False]
        hts += [riser_top, zt, tread]
        roles += [P["cliff_role"], P["tread_role"], P["tread_role"]]
        meta_terr.append({"inner_offset": round(offs[-2], 3), "outer_offset": round(offs[-1], 3), "height": round(rise * (j + 1), 3)})
        z = hts[-1]
    gap = np.zeros(k)
    if P["view_gap_azimuth"] >= 0 and P["view_gap"] > 0:
        half_w = math.radians(P["view_gap_width"]) / 2.0
        az = math.radians(P["view_gap_azimuth"])
        for i, (x, y) in enumerate(out):
            dd = abs((math.atan2(y, x) - az + math.pi) % math.tau - math.pi)
            t = min(1.0, dd / half_w)
            gap[i] = P["view_gap"] * (1.0 - t * t * (3 - 2 * t))
    ridge_base = offs[-1]
    if P["ridge_height"] > 0:
        H, rr, jag = P["ridge_height"], P["ridge_run"], P["jag"]
        n1, n2 = jit(2 * jag), jit(2 * jag)
        ew = np.maximum(ew, gap)
        o0 = offs[-1]
        # ragged talus band at the cliff foot (irregular rock-cluster heights) so the ridge rises out of the ground
        # instead of meeting it in one straight crease
        talus = z + H * (0.1 + 0.12 * rs2.random(k)) * (1 - 0.85 * ew)
        offs += [o0 + 0.1 * rr, o0 + 0.25 * rr, o0 + 0.45 * rr, o0 + 0.7 * rr, o0 + rr]
        fresh += [True, False, False, False, False]
        hts += [talus, z + H * 0.5 * (1 + 0.5 * n1) * (1 - 0.85 * ew), z + H * 0.9 * (1 + n1 * 0.6) * (1 - 0.8 * ew),
                z + H * (1 + n2) * (1 - 0.75 * ew), z + H * 0.7 * (1 + 0.5 * n2) * (1 - 0.75 * ew)]
        roles += [P["cliff_role"], P["cliff_role"], P["cliff_role"], P["cap_role"], P["cap_role"]]
    if len(offs) > 1:
        # organic outward jag on ledge/ridge rings (bounded so rings never cross)
        radial = []
        for j in range(len(offs)):
            if j == 0:
                radial.append(np.zeros(k))  # the playfield edge matches the ground exactly
                continue
            gap_prev = offs[j] - offs[j - 1]
            if gap_prev < 0.05:
                radial.append(radial[-1].copy())  # riser top follows its base ring
                continue
            nxt = [offs[q] - offs[j] for q in range(j + 1, len(offs)) if offs[q] - offs[j] >= 0.05]
            amp = 0.28 * min([gap_prev] + nxt[:1])
            a = (jit2 if fresh[j] else jit)(2 * amp)
            radial.append(np.convolve(np.r_[a[-1:], a, a[:1]], np.ones(3) / 3, "valid"))
        nodes.append(Node("terraces", _rows(out, offs, hts, roles, k, P["bowl"], radial, smooth=True), "shell"))
    # paths: lighter strips from each exit (beyond the pass) to near the centre, gently bent
    meta_paths = []
    if P["path_width"] > 0 and exits:
        pm = K.Mesh()
        hw = P["path_width"] / 2.0
        reach = T * run + 1.5
        for idx, e in enumerate(exits):
            p0 = np.asarray(e["p"]) - np.asarray(e["n"]) * reach
            p1 = np.asarray(e["p"])
            p3 = np.asarray(e["n"]) * min(P["width"], P["depth"]) * 0.08
            side = np.array([-e["n"][1], e["n"][0]])
            bend = (rs.random() - 0.5) * 0.35 * float(np.linalg.norm(p3 - p1))
            p2 = (p1 + p3) / 2 + side * bend
            pts = [p0 + (p1 - p0) * t for t in (0.0, 0.5)]
            for t in np.linspace(0.0, 1.0, 7):
                pts.append((1 - t) ** 2 * p1 + 2 * (1 - t) * t * p2 + t * t * p3)
            zz = 0.012 + 0.004 * idx
            L = []
            R = []
            for i, p in enumerate(pts):
                a = pts[max(0, i - 1)]
                b = pts[min(len(pts) - 1, i + 1)]
                dvec = (b - a) / max(1e-9, float(np.linalg.norm(b - a)))
                nn = np.array([-dvec[1], dvec[0]])
                w = hw * (0.75 + 0.25 * math.sin(i * 1.7 + idx))
                L.append((p[0] + nn[0] * w, p[1] + nn[1] * w, zz))
                R.append((p[0] - nn[0] * w, p[1] - nn[1] * w, zz))
            base = len(pm.v)
            pm.v.extend(L + R)
            n = len(pts)
            for i in range(n - 1):
                pm.f.append((base + i, base + n + i, base + n + i + 1, base + i + 1))
                pm.r.append(P["path_role"])
                pm.s.append(False)
                pm.uv.append(None)
            meta_paths.append([[round(float(p[0]), 3), round(float(-p[1]), 3)] for p in pts])
        A = np.asarray(pm.v)
        for fi, f in enumerate(pm.f):
            p = A[list(f)]
            if np.cross(p[1] - p[0], p[2] - p[0])[2] < 0:
                pm.f[fi] = tuple(reversed(f))
        nodes.append(Node("paths", pm, "shell"))
    for pi, pd in enumerate(P["ponds"]):
        cx, cy = pd["x"] * P["width"], pd["y"] * P["depth"]
        top = pd["thickness"]
        slab = K.prism(K.circle2d(0, 16, rx=pd["rx"], ry=pd["ry"]), -0.05, top, P["pond_role"]).translate(cx, cy, 0.0)
        nodes.append(Node("pond_%d" % pi, slab.orient_outward()))
    meta_exits = []
    for e in exits:
        yaw = math.degrees(math.atan2(e["n"][1], e["n"][0])) + 90.0
        meta_exits.append({"index": e["index"], "wall": e["wall"], "width": e["width"],
                           "pos_gltf": [round(float(e["p"][0]), 4), 0.0, round(float(-e["p"][1]), 4)], "yaw_deg": round(yaw % 360.0, 3)})
    meta = {"plan": P["plan"], "exits": meta_exits, "paths_gltf": meta_paths, "terraces": meta_terr,
            "ridge": {"base_offset": round(ridge_base, 3),
                      "height": P["ridge_height"], "run": P["ridge_run"]},
            "walkable_outline_gltf": [[round(x, 4), round(-y, 4)] for x, y in out]}
    return Asset([n for n in nodes if n.mesh.f], meta)


@register("terrain.vista", V, "terrain", {
    "radius": S.runtime(S.num(60.0, 20.0, 400.0, "placement scale; keep inside the fog/far plane")),
    "layers": S.integer(2, 1, 3), "segments": S.lod(S.integer(48, 16, 64)),
    "height": S.num(0.16, 0.02, 0.6, "silhouette height as a fraction of the radius"),
    "jag": S.num(0.5, 0.0, 1.0), "kind": S.enum("mountains", ["mountains", "hills", "forest", "mixed"]),
    "below": S.num(0.08, 0.0, 0.5, "fraction of the radius extending below the horizon"),
}, "Distant silhouette rings around the viewer (inward-facing, role 'vista' near / 'vista_far' beyond; v = 0 at the "
   "base .. 1 at the crest so packs paint haze gradients). Painted depth layers between the playfield and the sky.",
    origin="viewer")
def vista(P, seed):
    rs = np.random.default_rng(sub_seed("vista", seed))
    R, k = P["radius"], P["segments"]
    nodes = []
    for layer in range(P["layers"]):
        rad = R * (1.0 + 0.45 * layer)
        top_h = P["height"] * R * (1.0 + 0.35 * layer)
        xs = np.arange(k + 1) / k
        if P["kind"] == "hills":
            prof = 0.55 + 0.45 * np.interp(xs, np.linspace(0, 1, 7), np.r_[rs.random(6), 0][:7])
        else:
            cnt = 9 + 4 * layer
            pts = rs.random(cnt + 1)
            pts[-1] = pts[0]
            prof = 0.35 + 0.65 * np.interp(xs, np.linspace(0, 1, cnt + 1), pts) ** (1.0 + P["jag"])
            if P["kind"] in ("forest", "mixed"):
                teeth = (np.sin(xs * k * 1.7 + layer) > 0.2) * 0.12 * (1.0 if P["kind"] == "forest" else 0.5)
                prof = prof + teeth
        prof[-1] = prof[0]
        z0 = -P["below"] * R
        verts, faces, uvs = [], [], []
        for i in range(k + 1):
            a = math.tau * i / k
            c, s = math.cos(a), math.sin(a)
            verts.append((rad * c, rad * s, z0))
            verts.append((rad * c, rad * s, top_h * prof[i]))
        for i in range(k):
            b = 2 * i
            faces.append((b, b + 2, b + 3, b + 1))
            uvs.append(("n", [(i / k * 4, 0.0), ((i + 1) / k * 4, 0.0), ((i + 1) / k * 4, 1.0), (i / k * 4, 1.0)]))
        m = K.Mesh().add(verts, faces, "vista" if layer == 0 else "vista_far", False, uvs)
        A = np.asarray(m.v)
        for fi, f in enumerate(m.f):
            p = A[list(f)]
            nrm = np.cross(p[1] - p[0], p[2] - p[0])
            if np.dot(nrm, -p.mean(0)) < 0:
                m.f[fi] = tuple(reversed(f))
                m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
        nodes.append(Node("vista_%d" % layer, m, "shell"))
    return Asset(nodes, {"radius_m": R, "layers": P["layers"], "origin": "viewer"})
