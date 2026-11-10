"""SCIFIKIT planet-surface terrain (planet.*): 8 m TERRAIN GRID tiles (ground, rise, plateau, crater, dune, trail,
ridge cliff, landing pad) plus a mesa landmark.

Interlocking: every tile is a closed heightfield slab (top + skirt + bottom) whose four edge profiles are fixed by
its type, so neighbours meet without gaps or steps: a `ground` edge is flat at its level (0, 2 or 6 m), a `ramp` edge
runs from level a to level b with the shared smoothstep profile, and trail edges carry the 2.4 m path band centred on
the edge. tile_edges() (meta.edges) states each edge so tools/scifikit_rooms.py can check neighbours. Undulation,
dunes, craters and rocks stay inside the tile (they fade to the edge profile over the outer 1.6 m). Blender space:
+Z up, tile centred on the origin (terrain_center), edges at +-4 m."""
import math

import numpy as np

from . import schema as S
from . import sfkit as F
from .asset import Asset, Node, register

V = "1.0.0"
T = F.TILE
H2, H6 = 2.0, 6.0
TRAIL_W = 2.4


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def vnoise2(x, y, seed, scale):
    """Deterministic smooth value noise (tileable inside one tile only; edges are faded anyway)."""
    xs, ys = x / scale, y / scale
    x0, y0 = np.floor(xs), np.floor(ys)
    fx, fy = smooth(xs - x0), smooth(ys - y0)

    def h(ix, iy):
        v = (int(ix) * 374761393 + int(iy) * 668265263 + int(seed) * 2147483647) % 4294967296
        v = ((v ^ (v >> 13)) * 1274126177) % 4294967296
        return (v % 10007) / 10007.0
    a, b = h(x0, y0), h(x0 + 1, y0)
    c, d = h(x0, y0 + 1), h(x0 + 1, y0 + 1)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def slab(xs, ys, Z, roles, depth=0.6, side_role=None):
    """Closed heightfield slab: top grid (xs x ys, heights Z[j][i], per-cell roles), vertical skirt, flat bottom."""
    from . import meshkit as K
    nx, ny = len(xs), len(ys)
    zmin = float(np.min(Z)) - depth
    verts = [(xs[i], ys[j], float(Z[j][i])) for j in range(ny) for i in range(nx)]
    faces, rl = [], []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            # split each cell along the diagonal that follows the terrain (shorter in height) to avoid creases
            faces.append((a, a + 1, a + nx + 1, a + nx))
            rl.append(roles[j][i])
    top = K.Mesh().add(verts, faces, rl, False)
    ring = [(i, 0) for i in range(nx)] + [(nx - 1, j) for j in range(1, ny)] + \
           [(i, ny - 1) for i in range(nx - 2, -1, -1)] + [(0, j) for j in range(ny - 2, 0, -1)]
    k = len(ring)
    base = len(top.v)
    sverts = [(xs[i], ys[j], zmin) for i, j in ring]
    top.v.extend(sverts)
    sf, sr = [], []
    for q in range(k):
        i0, j0 = ring[q]
        i1, j1 = ring[(q + 1) % k]
        a, b = j0 * nx + i0, j1 * nx + i1
        sf.append((b, a, base + q, base + (q + 1) % k))
        sr.append(side_role or roles[0][0])
    for f, r in zip(sf, sr):
        top.f.append(f)
        top.r.append(r)
        top.s.append(False)
        top.uv.append(None)
    top.f.append(tuple(base + q for q in reversed(range(k))))
    top.r.append(side_role or roles[0][0])
    top.s.append(False)
    top.uv.append(None)
    return top.orient_outward()


def grid(n=9, dense_y=None):
    xs = [-T / 2 + T * i / (n - 1) for i in range(n)]
    ys = list(xs) if dense_y is None else dense_y
    return xs, ys


def fade(x, y, width=1.6):
    """0 at the tile edge -> 1 inside (smooth), for interior detail that must not touch the edge profiles."""
    d = min(T / 2 - abs(x), T / 2 - abs(y))
    return float(smooth(d / width))


def ramp_h(y, lo, hi):
    """Shared ramp profile across a tile from the south edge (y = -4, level lo) to the north edge (level hi)."""
    return lo + (hi - lo) * float(smooth((y + T / 2) / T))


def tile_edges(kind, level=0.0, hi=None, trail=()):
    e = {}
    for side in "nesw":
        if kind == "ramp":
            e[side] = {"type": "ground", "level": hi} if side == "n" else (
                {"type": "ground", "level": level} if side == "s" else {"type": "ramp", "from": level, "to": hi})
        elif kind == "ridge":
            e[side] = {"type": "ground", "level": H6} if side == "n" else (
                {"type": "ground", "level": level} if side == "s" else {"type": "cliff", "from": level, "to": H6})
        else:
            e[side] = {"type": "ground", "level": level}
        if side in trail:
            e[side]["trail"] = TRAIL_W
    return e


def _sockets(edges):
    out = []
    for side, e in sorted(edges.items()):
        x, y = {"n": (0.0, T / 2), "s": (0.0, -T / 2), "e": (T / 2, 0.0), "w": (-T / 2, 0.0)}[side]
        lvl = e.get("level", e.get("from", 0.0))
        out.append(F.socket("terrain_edge", x, y, lvl, side, edge=e))
    return out


def _asset(nodes, meta, ao=0.22, reach=1.2):
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    F.bake_ao(nodes, amount=ao, reach=reach, ground=False)
    meta = dict(meta)
    meta.setdefault("station_grid", {"anchor": "terrain_tile", "tile_m": T})
    if "edges" in meta:
        meta["sockets"] = _sockets(meta["edges"])
    return Asset(nodes, meta)


SURF = ["sand", "dirt", "field", "path", "rock", "snow"]


# ------------------------------------------------------------------ ground / plateau
@register("planet.ground", V, "terrain", {
    "surface": S.enum("sand", SURF, "ground role (regolith sand, dark dirt, ochre field...)"),
    "level": S.enum("0", ["0", "2", "6"], "tile level in metres (plateaus at 2 or 6 m)"),
    "rough": S.num(0.3, 0.0, 0.8, "interior undulation (m)"),
    "rocks": S.integer(0, 0, 3, "low rock bumps inside the tile"),
}, "Planet ground tile (8 m): closed regolith slab, gently undulating inside and flat at its level on all four "
   "edges, optional low rock bumps (rock role). Interlocks with any tile whose edge is ground at the same level.",
   origin="terrain_center")
def ground(P, seed):
    lvl = float(P["level"])
    xs, ys = grid()
    rs = np.random.default_rng(seed * 31 + 7)
    bumps = [(rs.uniform(-2.2, 2.2), rs.uniform(-2.2, 2.2), rs.uniform(0.6, 1.1), rs.uniform(0.25, 0.5)) for _ in range(P["rocks"])]
    Z, R = [], []
    for y in ys:
        zr, rr = [], []
        for x in xs:
            f = fade(x, y)
            z = lvl + P["rough"] * f * (vnoise2(x + 11, y + 5, seed, 3.2) - 0.45)
            role = P["surface"]
            for bx, by, br, bh in bumps:
                d = math.hypot(x - bx, y - by)
                if d < br * 1.2:
                    z += bh * f * float(smooth(1.0 - d / (br * 1.2)))
                    role = "rock" if d < br else role
            zr.append(z)
            rr.append(role)
        Z.append(zr)
        R.append(rr[:-1])
    R = R[:-1]
    meta = {"edges": tile_edges("ground", lvl), "level": lvl}
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))], meta)


# ------------------------------------------------------------------ rise (ramp tile)
@register("planet.rise", V, "terrain", {
    "surface": S.enum("sand", SURF), "to": S.enum("2", ["2", "6"], "level reached at the north edge"),
}, "Rise tile (8 m): a smooth ramp from level 0 on the south edge to level 2 (or 6) on the north edge; east/west "
   "edges follow the shared ramp profile, steep cells take the cliff role.", origin="terrain_center")
def rise(P, seed):
    hi = float(P["to"])
    xs, ys = grid()
    Z, R = [], []
    for j, y in enumerate(ys):
        Z.append([ramp_h(y, 0.0, hi) + 0.18 * fade(x, y) * (vnoise2(x, y, seed, 2.8) - 0.5) for x in xs])
    for j in range(len(ys) - 1):
        slope = abs(ramp_h(ys[j + 1], 0, hi) - ramp_h(ys[j], 0, hi)) / (ys[j + 1] - ys[j])
        R.append([("cliff" if slope > 0.9 else P["surface"])] * (len(xs) - 1))
    meta = {"edges": tile_edges("ramp", 0.0, hi), "level": 0.0, "to": hi}
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))], meta)


# ------------------------------------------------------------------ crater
@register("planet.crater", V, "terrain", {
    "surface": S.enum("sand", SURF), "depth": S.num(1.1, 0.4, 1.8), "radius": S.num(2.6, 1.6, 3.0),
}, "Crater tile (8 m): a bowl with a raised rim (rim faces rock role) inside a flat-edged regolith tile.",
   origin="terrain_center")
def crater(P, seed):
    xs = [-4.0, -3.0, -2.2, -1.5, -0.8, 0.0, 0.8, 1.5, 2.2, 3.0, 4.0]
    ys = list(xs)
    rad, dep = P["radius"], P["depth"]
    Z, R = [], []
    for y in ys:
        zr = []
        for x in xs:
            d = math.hypot(x, y) / rad
            rim = 0.45 * math.exp(-((d - 1.0) / 0.28) ** 2)
            bowl = -dep * float(smooth(1.0 - d)) if d < 1.0 else 0.0
            zr.append((rim + bowl) * fade(x, y, 1.0) + 0.1 * fade(x, y) * (vnoise2(x, y, seed, 2.5) - 0.5))
        Z.append(zr)
    for j in range(len(ys) - 1):
        rr = []
        for i in range(len(xs) - 1):
            d = math.hypot((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2) / rad
            rr.append("rock" if 0.75 < d < 1.25 else ("dirt" if d <= 0.75 else P["surface"]))
        R.append(rr)
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))], {"edges": tile_edges("ground", 0.0), "level": 0.0})


# ------------------------------------------------------------------ dune
@register("planet.dune", V, "terrain", {
    "height": S.num(0.9, 0.3, 1.5, "dune crest height"), "waves": S.integer(2, 1, 3),
}, "Dune tile (8 m): wind ridges with a sharp crest and soft lee slope running east-west, fading to flat ground on "
   "every edge (sand role, crests path role for a lighter tone).", origin="terrain_center")
def dune(P, seed):
    xs, ys = grid(9, [-4.0 + 0.5 * j for j in range(17)])
    Z, R = [], []
    for y in ys:
        zr = []
        for x in xs:
            ph = ((y + 4.0) / T * P["waves"] + 0.15 * math.sin(x * 0.6)) % 1.0
            prof = (ph / 0.7) ** 1.6 if ph < 0.7 else (1.0 - (ph - 0.7) / 0.3) ** 2
            zr.append(P["height"] * prof * fade(x, y, 1.4))
        Z.append(zr)
    for j in range(len(ys) - 1):
        R.append(["path" if Z[j][i] > P["height"] * 0.7 else "sand" for i in range(len(xs) - 1)])
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))], {"edges": tile_edges("ground", 0.0), "level": 0.0})


# ------------------------------------------------------------------ trail
@register("planet.trail", V, "terrain", {
    "shape": S.enum("straight", ["straight", "bend", "end"], "straight N-S, bend S-E, end (S only, ends in a turning patch)"),
    "surface": S.enum("sand", SURF),
}, "Trail tile (8 m): a 2.4 m packed trail (path role) worn slightly into flat-edged ground, crossing the tile on the "
   "trail edges; neighbours must carry the trail on the shared edge.", origin="terrain_center")
def trail(P, seed):
    shape = P["shape"]
    xs, ys = grid(13, None)
    ys = list(xs)

    def dist(x, y):
        if shape == "straight":
            return abs(x)
        if shape == "end":
            return abs(x) if y < 0 else math.hypot(x, y) - 0.0
        # bend: quarter arc from the south edge midpoint to the east edge midpoint, centred on the SE corner
        return abs(math.hypot(x - 4.0, y + 4.0) - 4.0)
    Z, R = [], []
    for y in ys:
        Z.append([0.12 * fade(x, y) * (vnoise2(x, y, seed, 3.0) - 0.5) - 0.06 * float(smooth(1.0 - dist(x, y) / (TRAIL_W * 0.7)))
                  for x in xs])
    for j in range(len(ys) - 1):
        R.append(["path" if dist((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2) < TRAIL_W / 2 else P["surface"]
                  for i in range(len(xs) - 1)])
    # trail edges: keep the shared edge exactly flat (0) so neighbours meet; the wear dips only inside
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if abs(abs(x) - 4.0) < 1e-6 or abs(abs(y) - 4.0) < 1e-6:
                Z[j][i] = 0.0
    sides = {"straight": "ns", "bend": "se", "end": "s"}[shape]
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))],
                  {"edges": tile_edges("ground", 0.0, trail=sides), "level": 0.0, "shape": shape})


# ------------------------------------------------------------------ ridge (cliff tile)
@register("planet.ridge", V, "terrain", {
    "jag": S.num(0.8, 0.0, 1.0, "buttresses, gullies and rim bumps along the cliff (0 = smooth)"),
}, "Ridge tile (8 m): flat ground on the south half rising in a steep strata cliff (cliff role) to the 6 m plateau "
   "level on the north edge, the face broken into buttresses and gullies with rim bumps behind the crest; a backdrop "
   "wall for alien regions that interlocks with plateau tiles at level 6 and with other ridges cliff to cliff.",
   origin="terrain_center")
def ridge(P, seed):
    ys = [-4.0, -2.5, -1.0, -0.2, 0.4, 0.9, 1.4, 2.0, 2.8, 4.0]
    xs = [-4.0 + i for i in range(9)]
    rs = np.random.default_rng(seed * 7 + 77)
    # per-column offsets of the cliff line (buttresses / gullies) and rim bumps; zero on the tile edges so the E/W
    # "cliff" edge profile and the N/S levels stay exactly as declared (neighbours meet without steps)
    offs = [0.0] + [float(rs.uniform(-1.0, 1.0)) * P["jag"] for _ in range(7)] + [0.0]
    rim = [0.0] + [float(rs.uniform(0.0, 1.0)) * P["jag"] for _ in range(7)] + [0.0]
    Z, R = [], []
    for y in ys:
        zr = []
        for i, x in enumerate(xs):
            t = float(smooth((y + 0.4 + offs[i]) / 2.6))
            z = H6 * t
            if abs(abs(y) - 4.0) > 1e-6 and 0 < i < len(xs) - 1:
                z += rim[i] * math.exp(-((y - 2.3) / 0.6) ** 2)
                z += P["jag"] * 0.5 * (vnoise2(x * 1.7, y, seed, 1.6) - 0.5) * math.sin(math.pi * t)
            zr.append(z)
        Z.append(zr)
    for j in range(len(ys) - 1):
        row = []
        for i in range(len(xs) - 1):
            slope = abs(Z[j + 1][i] + Z[j + 1][i + 1] - Z[j][i] - Z[j][i + 1]) / (2.0 * (ys[j + 1] - ys[j]))
            row.append("cliff" if slope > 0.8 else ("sand" if ys[j] < 0 else "rock"))
        R.append(row)
    return _asset([Node("ground", slab(xs, ys, Z, R, side_role="cliff"))], {"edges": tile_edges("ridge", 0.0), "level": 0.0})


# ------------------------------------------------------------------ landing pad
@register("planet.pad", V, "terrain", {
    "beacons": S.integer(4, 0, 4, "beacon posts around the pad"),
}, "Landing pad tile (8 m): flat ground tile carrying a round bevelled hex-plated pad (floor role) with a hazard ring "
   "and up to four beacon posts with glowing heads. Interlocks as level-0 ground.", origin="terrain_center")
def pad(P, seed):
    xs, ys = grid(7)
    Z = [[0.06 * fade(x, y) * (vnoise2(x, y, seed, 3.0) - 0.5) - 0.04 for x in xs] for y in ys]
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if abs(abs(x) - 4.0) < 1e-6 or abs(abs(y) - 4.0) < 1e-6:
                Z[j][i] = 0.0
    R = [["sand"] * (len(xs) - 1) for _ in range(len(ys) - 1)]
    nodes = [Node("ground", slab(xs, ys, Z, R, side_role="cliff")),
             Node("pad", F.lathe([(0.0, -0.1), (3.3, -0.1), (3.3, 0.06), (3.1, 0.16), (0.0, 0.16)], 12, "floor", smooth=False,
                                 roles=["wall_alt", "wall_alt", "trim", "floor"])),
             Node("ring", F.lathe_ring(2.3, 2.75, 0.161, 0.175, 12, "band"))]
    posts, heads = [], []
    for i in range(P["beacons"]):
        a = math.tau * i / 4 + math.pi / 4
        x, y = 3.6 * math.cos(a), 3.6 * math.sin(a)
        posts.append(F.loft_levels(F.chamfer_rect(0.16, 0.16, 0.0), [(0.0, 1.4, 1.4, x, y), (0.9, 1.0, 1.0, x, y)], "post"))
        heads.append(F.bevel_block(x, y, 0.9, 0.2, 0.2, 0.16, "light", bevel=0.0))
    if posts:
        nodes += [Node("posts", F.merged(*posts)), Node("beacons", F.merged(*heads))]
    meta = {"edges": tile_edges("ground", 0.0), "level": 0.0, "emitter": "pad_beacons", "pad_centre": F.gl(0, 0, 0.16)}
    return _asset(nodes, meta)


# ------------------------------------------------------------------ mesa landmark
@register("planet.mesa", V, "structure", {
    "width": S.num(9.0, 6.0, 14.0), "height": S.num(5.0, 3.0, 8.0),
}, "Mesa: a flat-topped strata plateau with tapering eroded sides and a ledge band (cliff sides, sand top), a "
   "landmark for alien regions; stands on the ground anywhere off the tile grid.", origin="floor_center")
def mesa(P, seed):
    rs = np.random.default_rng(seed + 101)
    W, H = P["width"], P["height"]
    k = 9
    out = [(0.5 * W * (0.82 + 0.18 * rs.random()) * math.cos(math.tau * i / k),
            0.42 * W * (0.82 + 0.18 * rs.random()) * math.sin(math.tau * i / k)) for i in range(k)]
    body = F.loft_levels(out, [(0.0, 1.12, 1.12), (H * 0.45, 0.96, 0.96), (H * 0.55, 0.9, 0.9), (H, 0.84, 0.84)], "cliff",
                         roles=["cliff", "rock", "cliff"], cap_roles=("cliff", "sand"))
    return Asset([n for n in F.bake_ao([Node("mesa", body)], amount=0.25, reach=2.0, ground=True)],
                 {"station_grid": {"anchor": "free"}})
