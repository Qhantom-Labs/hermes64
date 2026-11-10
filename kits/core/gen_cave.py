"""DUNGEONKIT cave (cave.*) and lake/water (lake.*) families, theme-agnostic (Blender space, +Z up, front -Y).

Cave rock is built from rounded lofts and smooth height-field sheets (never boxes): walls lean into the ceiling,
lumps vanish at the cell ends so neighbouring pieces meet without seams (same DUNGEON GRID as dgn.*).
The lake kit only uses roles every pack defines (water, sand, path, grass, rock, cliff, wood, post, rope, foliage,
flower, snow for foam), so it rebuilds in any style profile; the water surface carries an N64 vertex wobble + scroll
hint (material extras, bounded by the lake gate in tools/dungeonkit_library.py).
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .gen_dungeon import grid_meta, sock, stations, grid_floor
from .genutil import finalize
from .rng import rng

V = "1.0.0"
HC = 5.0                 # cave storey (wall top / ceiling height)
WATER_Z = -0.35          # lake water level below the land datum
WOBBLE_MAX = {"amplitude_m": 0.08, "wavelength_m_min": 2.0, "speed_max": 2.5}
SCROLL_MAX = 0.06


def bumps(r, n, lo=(0.0, 0.0), hi=(1.0, 1.0), amp=0.35, size=(0.18, 0.3)):
    out = []
    for _ in range(n):
        out.append((r.uniform(lo[0], hi[0]), r.uniform(lo[1], hi[1]), r.uniform(0.4, 1.0) * amp * (1 if r.random() < 0.8 else -0.6),
                    r.uniform(*size), r.uniform(*size)))
    return out


def bump_field(bs, s, t):
    v = 0.0
    for cs, ct, a, ws, wt in bs:
        v += a * math.exp(-(((s - cs) / ws) ** 2 + ((t - ct) / wt) ** 2))
    return v


def sheet(nu, nv, fn, role, smooth=True, role_fn=None):
    """Open quad grid surface; fn(i/nu, j/nv) -> (x, y, z); faces wound CCW as seen from -Y for a wall laid out with
    u along +X and v along +Z (callers flip as needed)."""
    P = [[fn(i / nu, j / nv) for i in range(nu + 1)] for j in range(nv + 1)]
    m = K.Mesh()
    for j in range(nv):
        for i in range(nu):
            q = [P[j][i], P[j][i + 1], P[j + 1][i + 1], P[j + 1][i]]
            r = role_fn(i, j, q) if role_fn else role
            m.add(q, [(0, 1, 2, 3)], r, smooth)
    return D.weld_mesh(m)


# ================================================================ CAVE
@register("cave.wall", V, "shell", {
    "kind": S.enum("straight", ["straight", "corner"]),
    "lumps": S.integer(6, 2, 10), "lean": S.num(0.9, 0.3, 1.4, "how far the wall bows into the room at the top (m)"),
}, "Organic cave wall for one cell edge (4 m): a smooth lumpy rock sheet that leans into the ceiling, lumps fading to "
   "the shared profile at both ends so cells join seamlessly. corner: an inner 90-degree bend (two edges). Origin on "
   "the cell boundary at floor level (corner: the cell centre).", origin="opening")
def cave_wall(P, seed):
    r = rng(seed, "cave.wall", P["kind"])
    L = D.CELL
    lean = P["lean"]

    def base(t):
        return 0.3 + lean * t ** 2.2 + 0.07 * math.sin(t * 13.0)

    if P["kind"] == "straight":
        bs = bumps(r, P["lumps"], (0.1, 0.05), (0.9, 0.9))

        def fn(u, v):
            env = math.sin(math.pi * u) ** 0.7
            d = base(v) + env * bump_field(bs, u, v)
            return (u * L - L / 2, -d, v * HC)
        m = sheet(8, 7, fn, "rock")
        socks = [sock("cave_edge", (0, 0, 0), "s", profile="cave.wall")]
    else:
        # inner corner of the cell's north and east edges: straight -> quarter arc (radius RC) -> straight, the rock
        # surface offset inward (toward the cell centre) by the lumpy depth
        bs = bumps(r, P["lumps"], (0.1, 0.05), (0.9, 0.9))
        e, RC = D.CELL / 2, 1.4
        L1, LA = 2 * e - RC, math.pi / 2 * RC
        Lt = 2 * L1 + LA

        def path(u):
            s_ = u * Lt
            if s_ <= L1:
                return (-e + s_, e, 0.0, -1.0)
            if s_ <= L1 + LA:
                a = (s_ - L1) / RC                       # 0 -> pi/2 around the centre (e - RC, e - RC)
                cx = cy = e - RC
                return (cx + RC * math.sin(a), cy + RC * math.cos(a), -math.sin(a), -math.cos(a))
            t = s_ - L1 - LA
            return (e, e - RC - t, -1.0, 0.0)

        def fn(u, v):
            x, y, nx, ny = path(u)
            d = base(v) + math.sin(math.pi * u) ** 0.7 * bump_field(bs, u, v)
            return (x + nx * d, y + ny * d, v * HC)
        m = sheet(10, 7, fn, "rock")
        socks = [sock("cave_edge", (0, D.CELL / 2, 0), "n"), sock("cave_edge", (D.CELL / 2, 0, 0), "e")]
    base_rocks = K.Mesh()
    for k in range(3):
        x = r.uniform(-1.6, 1.6)
        base_rocks.merge(D.rock_blob(x, -0.5 - r.uniform(0, 0.25), 0.15, r.uniform(0.25, 0.45), r.uniform(0.2, 0.35), r.uniform(0.18, 0.3), r, "rock",
                                     segs=6, rings=3))
    nodes = [Node("rock", m, "shell")]
    if P["kind"] == "straight":
        nodes.append(Node("scree", base_rocks))
    return Asset(nodes, grid_meta("cell_edge" if P["kind"] == "straight" else "cell_centre", None, socks, kind=P["kind"]))


@register("cave.floor", V, "shell", {
    "roughness": S.num(0.12, 0.0, 0.3), "puddle": S.boolean(False),
}, "Uneven cave floor cell (4 x 4 m): gentle rounded humps that settle to the shared datum at the cell edges, earth "
   "in the hollows and bare rock on the rises; optional still puddle.", origin="terrain_center")
def cave_floor(P, seed):
    r = rng(seed, "cave.floor")
    bs = bumps(r, 7, (0.1, 0.1), (0.9, 0.9), amp=P["roughness"], size=(0.12, 0.25))
    e = D.CELL / 2
    hz = {}

    def fn(u, v):
        env = (math.sin(math.pi * u) * math.sin(math.pi * v)) ** 0.6
        z = env * bump_field(bs, u, v)
        if P["puddle"]:
            z -= 0.12 * math.exp(-(((u - 0.62) / 0.16) ** 2 + ((v - 0.4) / 0.13) ** 2))
        return (u * 2 * e - e, v * 2 * e - e, z)

    def role_fn(i, j, q):
        z = sum(p[2] for p in q) / 4
        return "rock" if z > P["roughness"] * 0.35 else "dirt"
    m = sheet(8, 8, fn, "dirt", role_fn=role_fn)          # u -> +X, v -> +Y: faces +Z
    nodes = [Node("floor", m, "shell")]
    if P["puddle"]:
        cx, cy = 0.62 * 2 * e - e, 0.4 * 2 * e - e
        pts = [(cx + 0.55 * math.cos(2 * math.pi * k / 8), cy + 0.42 * math.sin(2 * math.pi * k / 8), -0.03) for k in range(8)]
        pud = K.Mesh().add(pts, [tuple(range(8))], "water", False)
        nodes.append(Node("puddle", pud, "card"))
    return Asset(nodes, grid_meta("cell_centre", (1, 1), [sock("floor", (0, 0, 0), "up")]))


@register("cave.ceiling", V, "shell", {
    "stalactites": S.integer(4, 0, 8), "drop": S.num(0.6, 0.0, 1.2),
}, "Cave ceiling cell, one-sided facing down at the cave storey with lumpy sags (flat near the cell edges so walls and "
   "neighbours meet it) and hanging stalactites. Origin at floor level.", origin="opening")
def cave_ceiling(P, seed):
    r = rng(seed, "cave.ceiling")
    e = D.CELL / 2
    bs = bumps(r, 5, (0.25, 0.25), (0.75, 0.75), amp=P["drop"], size=(0.12, 0.22))

    def fn(u, v):
        env = (math.sin(math.pi * u) * math.sin(math.pi * v)) ** 1.5
        return (u * 2 * e - e, v * 2 * e - e, HC - env * bump_field(bs, u, v))
    m = sheet(6, 6, fn, "rock").flip()   # an XY sheet faces +Z; the ceiling faces down
    nodes = [Node("ceiling", m, "shell")]
    st = K.Mesh()
    for k in range(P["stalactites"]):
        x, y = r.uniform(-1.3, 1.3), r.uniform(-1.3, 1.3)
        u, v = (x + e) / (2 * e), (y + e) / (2 * e)
        top = HC - (math.sin(math.pi * u) * math.sin(math.pi * v)) ** 1.5 * bump_field(bs, u, v) + 0.08
        L = r.uniform(0.5, 1.5)
        rad = r.uniform(0.12, 0.24)
        prof = [(0.0, top - L), (rad * 0.25, top - L * 0.75), (rad * 0.6, top - L * 0.4), (rad, top - 0.05), (0.0, top)]
        st.merge(K.lathe(prof, 6, "cliff", smooth=True).translate(x, y, 0))
    if st.f:
        nodes.append(Node("stalactites", st))
    return Asset(nodes, grid_meta("cell_centre", (1, 1), [sock("ceiling", (0, 0, HC), "down")]))


@register("cave.spike", V, "structure", {
    "kind": S.enum("stalagmite", ["stalagmite", "stalactite", "column"]),
    "height": S.num(2.2, 0.6, 5.0), "count": S.integer(3, 1, 5),
}, "Dripstone cluster: lumpy tapering lathe spires. stalagmite rises from the floor, stalactite hangs from the cave "
   "storey, column joins floor and ceiling with a waisted middle.", origin="opening")
def cave_spike(P, seed):
    r = rng(seed, "cave.spike", P["kind"])
    m = K.Mesh()
    for k in range(P["count"]):
        h = P["height"] * (1.0 if k == 0 else r.uniform(0.35, 0.7))
        rad = (0.32 if k == 0 else r.uniform(0.12, 0.22)) * (1.4 if P["kind"] == "column" else 1.0)
        x, y = (0.0, 0.0) if k == 0 else (r.uniform(-0.55, 0.55), r.uniform(-0.55, 0.55))
        if P["kind"] == "column" and k == 0:
            prof = [(0.0, 0.0), (rad * 1.5, 0.0), (rad * 1.1, 0.5), (rad * 0.6, HC * 0.5), (rad * 1.1, HC - 0.5), (rad * 1.6, HC), (0.0, HC)]
        else:
            prof = [(0.0, 0.0), (rad, 0.0), (rad * 0.8, h * 0.25), (rad * 0.5, h * 0.6), (rad * 0.18, h * 0.88), (0.0, h)]
        sp = K.lathe(prof, 7, "cliff", smooth=True)
        V_ = np.asarray(sp.v)
        for i, p in enumerate(V_):
            rr = math.hypot(p[0], p[1])
            if rr > 1e-6:
                f = 1.0 + 0.16 * math.sin(p[2] * 3.1 + k) * math.sin(math.atan2(p[1], p[0]) * 3 + k)
                V_[i][0] *= f
                V_[i][1] *= f
        sp.v = [tuple(p) for p in V_]
        if P["kind"] == "stalactite" or (P["kind"] == "column" and k > 0 and k % 2 == 0):
            sp.scale(1, 1, -1).translate(0, 0, HC)
        m.merge(sp.translate(x, y, 0))
    return finalize([Node("dripstone", m)], grid_meta("free", None, [sock("prop", (0, 0, 0), "up")], kind=P["kind"]),
                    ground=False)


@register("cave.mouth", V, "structure", {
    "width": S.num(4.0, 2.5, 6.0), "height": S.num(4.2, 2.5, 6.0), "depth": S.num(2.4, 1.2, 4.0),
}, "Cave mouth: a thick rounded rock arch around a dark opening (closed lofted solid with lumpy rings) and a void card "
   "inside, to set into a cliff face or a cave wall line. Origin on the threshold centre, front face toward -Y.",
   origin="opening_floor")
def cave_mouth(P, seed):
    r = rng(seed, "cave.mouth")
    w, h, d = P["width"], P["height"], P["depth"]

    n = 9

    def outline(scale, jit):
        """U-shaped ring in (x, z): outer contour left foot -> over the top -> right foot, then the opening back."""
        ow, oh = w / 2 + 1.6 * scale, h + 1.3 * scale
        pts = []
        for i in range(n + 1):
            a = math.pi - math.pi * i / n
            if i in (0, n):
                pts.append((ow * math.cos(a), 0.0))
            else:
                pts.append((ow * math.cos(a) * (1 + jit[i] * 0.1), oh * math.sin(a) * (1 + jit[i] * 0.08)))
        for i in range(n + 1):
            a = math.pi * i / n
            if i in (0, n):
                pts.append((w / 2 * math.cos(a), 0.0))
            else:
                pts.append((w / 2 * math.cos(a) * (1 + jit[n + 1 + i] * 0.05), h * math.sin(a) * (1 + jit[n + 1 + i] * 0.04)))
        return pts
    jit = [r.uniform(-1, 1) for _ in range(2 * n + 4)]
    rings = []
    for y, sc in [(0.0, 0.8), (d * 0.3, 1.0), (d * 0.7, 0.95), (d, 0.8)]:
        j2 = [x + 0.25 * r.uniform(-1, 1) for x in jit]
        rings.append([(x, y, z) for x, z in outline(sc, j2)])
    m = K.loft(rings, "cliff", smooth=True)
    void = K.Mesh().add([(-w / 2 + 0.1, d * 0.6, 0.0), (w / 2 - 0.1, d * 0.6, 0.0), (w / 2 - 0.1, d * 0.6, h * 0.92),
                         (-w / 2 + 0.1, d * 0.6, h * 0.92)], [(0, 1, 2, 3)], "opening", False)
    floor = grid_floor([-w / 2, 0.0, w / 2], [-0.2, d * 0.3, d * 0.62], lambda x, y: True, 0.02, "dirt")
    return Asset([Node("arch", m), Node("void", void, "card"), Node("threshold", floor, "shell")],
                 grid_meta("threshold", None, [sock("cave_mouth", (0, 0, 0), "s", width_m=w, height_m=h)]))


@register("cave.ledge", V, "structure", {
    "height": S.num(1.8, 0.6, 3.0), "width": S.num(4.0, 2.0, 8.0), "depth": S.num(2.2, 1.2, 4.0),
}, "Underground ledge: a raised rock shelf with a rounded overhanging lip and lumpy flanks (closed loft of organic "
   "rings), walkable flat-ish top; back face flush with a wall line.", origin="floor_center")
def cave_ledge(P, seed):
    r = rng(seed, "cave.ledge")
    w, dp, h = P["width"], P["depth"], P["height"]
    k = 14

    def ring(z, grow, j):
        pts = []
        for i in range(k):
            a = 2 * math.pi * i / k
            x = math.cos(a) * w / 2 * (1 + grow)
            y = math.sin(a) * dp / 2 * (1 + grow)
            sx = 1.0 + 0.12 * j[i]
            pts.append((x * (abs(math.cos(a)) ** 0.25) * sx, y * (abs(math.sin(a)) ** 0.25) * sx + 0.0, z))
        return pts
    js = [[r.uniform(-1, 1) for _ in range(k)] for _ in range(4)]
    rings = [ring(0.0, 0.08, js[0]), ring(h * 0.45, 0.0, js[1]), ring(h * 0.88, 0.1, js[2]), ring(h, 0.02, [0.3 * x for x in js[3]])]
    m = K.loft(rings, "rock", smooth=True, cap_roles=("rock", "dirt"))
    return finalize([Node("ledge", m)], grid_meta("free", None, [sock("walk_top", (0, h, 0), "up", height_m=h)]))


@register("cave.boulder", V, "furniture_large", {
    "count": S.integer(2, 1, 4), "size": S.num(1.2, 0.5, 2.2),
}, "Rounded boulders: faceted lumpy blobs (one big, smaller companions) with moss-friendly tops.", origin="floor_center")
def cave_boulder(P, seed):
    r = rng(seed, "cave.boulder")
    m = K.Mesh()
    s = P["size"]
    for k in range(P["count"]):
        sc = s * (1.0 if k == 0 else r.uniform(0.35, 0.6))
        x = 0.0 if k == 0 else r.uniform(-1, 1) * s
        y = 0.0 if k == 0 else r.uniform(-1, 1) * s * 0.8
        m.merge(D.rock_blob(x, y, sc * 0.42, sc * 0.6, sc * 0.5, sc * 0.45, r, "rock", segs=8, rings=4, jitter=0.16))
    return finalize([Node("boulders", m)], grid_meta("free", None, [sock("prop", (0, 0, 0), "up")]))


@register("cave.cliff", V, "shell", {
    "width": S.num(8.0, 4.0, 16.0), "height": S.num(6.0, 3.0, 10.0), "strata": S.integer(3, 0, 5),
}, "Rock cliff face (exterior backdrop or chasm side): one-sided smooth rock sheet facing -Y with stepped strata "
   "ledges and a rounded crest; ends fade to a straight profile so cliffs tile along a line.", origin="opening_floor")
def cave_cliff(P, seed):
    r = rng(seed, "cave.cliff")
    w, h = P["width"], P["height"]
    bs = bumps(r, 8, (0.05, 0.05), (0.95, 0.95), amp=0.6, size=(0.08, 0.2))
    nst = P["strata"]
    # crest: rounded buttress peaks along the top (never a ruler-straight skyline); both ends return to the shared
    # height so cliffs tile, and recede ~1.6 m so a cliff seen from the side shows rock, not a sheet edge
    peaks = [(r.uniform(0.12, 0.88), r.uniform(0.12, 0.34), r.uniform(0.07, 0.18)) for _ in range(4)]

    def crest(u):
        c = sum(a * math.exp(-((u - cu) / cw) ** 2) for cu, a, cw in peaks)
        return 1.0 + c * math.sin(math.pi * u) ** 0.6 - 0.06 * (1 - math.sin(math.pi * u))

    def fn(u, v):
        env = math.sin(math.pi * u) ** 0.5
        step = 0.0
        for s_ in range(nst):
            t0 = (s_ + 1) / (nst + 1)
            step += 0.35 / (1 + math.exp(-(v - t0) * 40))
        d = 0.4 + env * bump_field(bs, u, v) - step + 0.6 * v ** 3 + 1.6 * (1 - math.sin(math.pi * u)) ** 2
        if v > 0.85:
            d += (v - 0.85) * 5.0
        return (u * w - w / 2, -d, v * h * crest(u))
    m = sheet(max(6, int(w / 1.2)), 8, fn, "cliff",
              role_fn=lambda i, j, q: "grass" if j == 7 else ("cliff" if j % 3 else "rock"))
    return Asset([Node("cliff", m, "shell")], grid_meta("cell_edge", None, [sock("cliff_edge", (0, 0, 0), "s", width_m=w)]))


# ================================================================ LAKE / WATER
def wobble_extras(amp=0.05, wavelength=3.2, speed=1.1, scroll=(0.025, 0.012)):
    return {"wobble": [round(amp, 4), round(wavelength, 4), round(speed, 4), 0.0], "scroll": [round(scroll[0], 4), round(scroll[1], 4)]}


@register("lake.water", V, "terrain", {
    "size_x": S.num(8.0, 4.0, 48.0), "size_y": S.num(8.0, 4.0, 48.0),
    "wobble": S.runtime(S.num(0.05, 0.0, 0.08, "vertex wobble amplitude (m); the lake gate caps it")),
    "wavelength": S.runtime(S.num(3.2, 2.0, 8.0)), "speed": S.runtime(S.num(1.1, 0.2, 2.5)),
    "resolution": S.lod(S.num(1.0, 0.75, 6.0, "vertex spacing (m) for the wobble (coarser for far water)")),
}, "Lake water surface tile: tessellated one-sided plane at the water level (origin = water surface centre) with the "
   "pack's painted water role; N64 vertex wobble + slow UV scroll declared as material extras (bounded by the lake "
   "gate). Tiles edge to edge; shore pieces overlap its rim.", origin="terrain_center")
def lake_water(P, seed):
    sx, sy = P["size_x"] / 2, P["size_y"] / 2
    res = P["resolution"]
    m = grid_floor(stations(-sx, sx, res), stations(-sy, sy, res), lambda x, y: True, 0.0, "water")
    meta = grid_meta("water_centre", (round(P["size_x"] / D.CELL, 3), round(P["size_y"] / D.CELL, 3)),
                     [sock("water", (0, 0, 0), "up", level_m=WATER_Z)],
                     material_extras={"water": wobble_extras(P["wobble"], P["wavelength"], P["speed"])},
                     water_level_m=WATER_Z, note="place with y = water level (WATER_Z below the land datum)")
    return Asset([Node("water", m, "shell")], meta)


SHORE_KINDS = ["straight", "corner_out", "corner_in", "land"]


@register("lake.shore", V, "terrain", {
    "kind": S.enum("straight", SHORE_KINDS), "stones": S.integer(4, 0, 8),
}, "Shoreline cell (4 x 4 m): land at the datum on the north side sloping under the water to the south (straight), "
   "around a convex corner (corner_out: water south and east) or a concave cove (corner_in); grass on top, a pebble "
   "beach band through the waterline, sand under water, scattered rounded stones.", origin="terrain_center")
def lake_shore(P, seed):
    r = rng(seed, "lake.shore", P["kind"])
    e = D.CELL / 2
    kind = P["kind"]

    def dist(x, y):
        """signed distance into the water (negative on land). Land edge lines: y = +0.5 (straight shores) and
        x = -0.5 (the rotated neighbour), so corners interlock with straight pieces on both sides."""
        dx, dy = x + 0.5, 0.5 - y
        if kind == "straight":
            return dy
        if kind == "land":                       # bank cell behind the shore: all land
            return -4.0
        if kind == "corner_out":                 # land only in the north-west quadrant, water wraps south and east
            if dx <= 0 and dy <= 0:
                return max(dx, dy)
            return math.hypot(max(dx, 0.0), max(dy, 0.0))
        if dx < 0 and dy < 0:                    # corner_in: water only in the south-east quadrant (a cove)
            return -math.hypot(dx, dy)
        return min(dx, dy)

    def z_of(t):
        if t <= 0:
            return 0.0
        return -min(1.2, 0.9 * (1 - math.exp(-t * 0.9)) + 0.1 * t)

    lumps = bumps(r, 5, (0.15, 0.15), (0.85, 0.85), amp=0.16, size=(0.12, 0.24)) if kind == "land" else []

    def fn(u, v):
        x, y = u * 2 * e - e, v * 2 * e - e
        t = dist(x, y)
        z = z_of(t)
        if lumps:
            z += (math.sin(math.pi * u) * math.sin(math.pi * v)) ** 0.8 * bump_field(lumps, u, v)
        return (x, y, z)

    def role_fn(i, j, q):
        zs = [p[2] for p in q]
        zm = sum(zs) / 4
        if kind == "land":
            return "path" if (i * 5 + j * 3) % 11 == 0 else "grass"
        if zm > -0.06:
            return "grass"
        if zm > WATER_Z - 0.18:
            return "path"
        return "sand"
    m = sheet(8, 8, fn, "grass", role_fn=role_fn)
    st = K.Mesh()
    for k in range(P["stones"]):
        for _ in range(12):
            x, y = r.uniform(-1.7, 1.7), r.uniform(-1.7, 1.7)
            t = dist(x, y)
            if -0.4 < t < 1.6:
                break
        z = z_of(t)
        st.merge(D.rock_blob(x, y, z + 0.05, r.uniform(0.15, 0.32), r.uniform(0.12, 0.26), r.uniform(0.1, 0.2), r, "rock", segs=6, rings=3))
    nodes = [Node("bank", m, "shell")]
    if st.f:
        nodes.append(Node("stones", st))
    socks = {"land": [sock("land", (0, e, 0), "n"), sock("land", (0, -e, 0), "s")],
             "straight": [sock("shore", (0, -e, 0), "s"), sock("land", (0, e, 0), "n")],
             "corner_out": [sock("shore", (0, -e, 0), "s"), sock("shore", (e, 0, 0), "e")],
             "corner_in": [sock("shore", (e, -e, 0), "s")]}[kind]
    return Asset(nodes, grid_meta("cell_centre", (1, 1), socks, kind=kind, water_level_m=WATER_Z))


@register("lake.dock", V, "structure", {
    "length": S.num(6.0, 3.0, 10.0), "width": S.num(2.0, 1.2, 3.0), "ladder": S.boolean(True),
}, "Timber dock: plank deck on round piles running out over the water from the shore, edge stringers, mooring posts "
   "with rope and an optional ladder.", origin="opening")
def lake_dock(P, seed):
    L, w = P["length"], P["width"]
    dz = 0.28
    deck = K.Mesh()
    deck.merge(D.bevel_box(0, -L / 2, dz - 0.1, w, L, 0.1, "wood", bevel=0.02))
    for sx in (-1, 1):
        deck.merge(K.box(sx * (w / 2 - 0.06), -L / 2, dz - 0.2, 0.12, L, 0.12, "post"))
    piles = K.Mesh()
    n = max(2, int(L / 2) + 1)
    for i in range(n):
        y = -0.3 - (L - 0.6) * i / (n - 1)
        for sx in (-1, 1):
            piles.merge(K.cylinder(sx * (w / 2 - 0.08), y, -1.4, 0.1, 1.4 + dz - 0.1, 6, "post"))
    posts = K.Mesh()
    for sx in (-1, 1):
        posts.merge(K.cylinder(sx * (w / 2 - 0.08), -L + 0.15, dz - 0.1, 0.11, 0.85, 6, "post"))
        posts.merge(K.torus(0.13, 0.03, 6, 3, "rope").translate(sx * (w / 2 - 0.08), -L + 0.15, dz + 0.55))
    nodes = [Node("deck", deck), Node("piles", piles), Node("posts", posts)]
    if P["ladder"]:
        lad = K.Mesh()
        for sx in (-1, 1):
            lad.merge(K.box(sx * 0.25, -L - 0.05, dz - 0.75, 0.06, 0.06, 1.3, "post"))
        for k in range(3):
            lad.merge(K.box(0, -L - 0.05, dz - 1.1 + 0.32 * k, 0.5, 0.05, 0.05, "post"))
        nodes.append(Node("ladder", lad))
    return Asset(nodes, grid_meta("shore_edge", None, [sock("land", (0, 0, 0), "n"), sock("walk", (0, dz, -L), "s")], deck_m=dz))


@register("lake.bridge", V, "structure", {
    "kind": S.enum("stones", ["stones", "planks"]), "length": S.num(8.0, 4.0, 12.0),
}, "Boat-less crossing over water, north-south: stepping stones (flat rounded rock tops in a meandering line) or a "
   "low plank walkway on piles with rope rails. Origin at the crossing centre on the land datum.", origin="opening")
def lake_bridge(P, seed):
    r = rng(seed, "lake.bridge", P["kind"])
    L = P["length"]
    nodes = []
    if P["kind"] == "stones":
        m = K.Mesh()
        n = int(L / 1.1)
        for i in range(n):
            y = -L / 2 + (i + 0.5) * L / n
            x = 0.35 * math.sin(i * 1.3) + r.uniform(-0.1, 0.1)
            rad = r.uniform(0.42, 0.55)
            prof = [(0.0, -0.9), (rad * 1.05, -0.9), (rad * 1.1, -0.35), (rad, 0.02), (rad * 0.8, 0.1), (0.0, 0.12)]
            st = K.lathe(prof, 7, "rock", smooth=True, rx=1.0, ry=0.85)
            m.merge(st.rotate_z(r.uniform(0, math.pi)).translate(x, y, 0))
        nodes.append(Node("stones", m))
    else:
        deck = K.Mesh()
        dz = 0.15
        n = int(L / 0.5)
        for i in range(n):
            y = -L / 2 + (i + 0.5) * L / n
            deck.merge(K.box(r.uniform(-0.03, 0.03), y, dz, 1.5, L / n - 0.05, 0.08, "wood"))
        piles = K.Mesh()
        rails = K.Mesh()
        k = int(L / 2) + 1
        for i in range(k):
            y = -L / 2 + 0.2 + (L - 0.4) * i / (k - 1)
            for sx in (-1, 1):
                piles.merge(K.cylinder(sx * 0.7, y, -1.2, 0.08, 2.3, 5, "post"))
        for sx in (-1, 1):
            rails.merge(K.tube([(sx * 0.7, -L / 2 + 0.2, 1.0), (sx * 0.7, 0.0, 0.85), (sx * 0.7, L / 2 - 0.2, 1.0)], 0.03, 3, "rope", smooth=False))
        nodes += [Node("deck", deck), Node("piles", piles), Node("rails", rails)]
    return Asset(nodes, grid_meta("crossing_centre", None, [sock("walk", (0, 0, -L / 2), "s"), sock("walk", (0, 0, L / 2), "n")],
                                  kind=P["kind"]))


@register("lake.reeds", V, "flora", {
    "blades": S.integer(14, 6, 22), "height": S.num(1.6, 0.8, 2.4), "cattails": S.integer(3, 0, 6),
}, "Reed clump: thin tapering blades (closed three-sided spines) arching outward from a tuft, with cattail heads; "
   "solid geometry so it reads in every pack (no alpha).", origin="floor_center")
def lake_reeds(P, seed):
    r = rng(seed, "lake.reeds")
    m = K.Mesh()
    for k in range(P["blades"]):
        a = r.uniform(0, 2 * math.pi)
        h = P["height"] * r.uniform(0.6, 1.0)
        lean = r.uniform(0.15, 0.5)
        x0, y0 = 0.18 * math.cos(a) * r.random(), 0.18 * math.sin(a) * r.random()
        path = [(x0, y0, 0.0), (x0 + lean * 0.3 * math.cos(a), y0 + lean * 0.3 * math.sin(a), h * 0.5),
                (x0 + lean * math.cos(a), y0 + lean * math.sin(a), h)]
        m.merge(K.tube(path, [0.03, 0.02, 0.004], 3, "foliage", smooth=False))
    heads = K.Mesh()
    for k in range(P["cattails"]):
        a = r.uniform(0, 2 * math.pi)
        h = P["height"] * r.uniform(0.8, 1.05)
        x, y = 0.15 * math.cos(a), 0.15 * math.sin(a)
        heads.merge(K.tube([(x, y, 0.0), (x * 1.5, y * 1.5, h * 0.75)], 0.012, 3, "foliage", smooth=False))
        heads.merge(K.cylinder(x * 1.5, y * 1.5, h * 0.75, 0.035, 0.2, 5, "bark"))
    nodes = [Node("reeds", m)]
    if heads.f:
        nodes.append(Node("cattails", heads))
    return finalize(nodes, grid_meta("free", None, [sock("water_plant", (0, 0, 0), "up")]))


@register("lake.lilies", V, "flora", {
    "pads": S.integer(6, 2, 10), "flowers": S.integer(2, 0, 4), "spread": S.num(1.4, 0.6, 2.5),
}, "Floating lily pads (thin notched discs) with closed water-lily blooms; origin on the water surface.",
   origin="opening")
def lake_lilies(P, seed):
    r = rng(seed, "lake.lilies")
    pads = K.Mesh()
    for k in range(P["pads"]):
        rad = r.uniform(0.18, 0.32)
        x, y = r.uniform(-1, 1) * P["spread"], r.uniform(-1, 1) * P["spread"]
        notch = r.uniform(0, 2 * math.pi)
        pts = []
        for i in range(7):
            a = notch + 0.35 + (2 * math.pi - 0.7) * i / 6
            pts.append((rad * math.cos(a), rad * math.sin(a)))
        pts.append((rad * 0.15 * math.cos(notch), rad * 0.15 * math.sin(notch)))
        pads.merge(K.prism(pts, 0.005, 0.03, "grass").translate(x, y, 0))
    fl = K.Mesh()
    for k in range(P["flowers"]):
        x, y = r.uniform(-0.7, 0.7) * P["spread"], r.uniform(-0.7, 0.7) * P["spread"]
        prof = [(0.0, 0.02), (0.06, 0.02), (0.12, 0.07), (0.09, 0.16), (0.04, 0.12), (0.0, 0.1)]
        fl.merge(K.lathe(prof, 6, "flower", smooth=False).translate(x, y, 0))
    nodes = [Node("pads", pads)]
    if fl.f:
        nodes.append(Node("blooms", fl))
    return Asset(nodes, grid_meta("water_surface", None, [sock("water_plant", (0, 0, 0), "up")]))


@register("lake.waterfall", V, "structure", {
    "height": S.num(6.0, 3.0, 10.0), "width": S.num(3.0, 1.5, 5.0),
}, "Waterfall: a bowed falling-water sheet (pack water role, fast downward scroll stretched into streaks) pouring "
   "from a rounded rock lip, white foam puffs and a churned pool rim at the foot. Front faces -Y; origin at the pool "
   "centre on the water surface.", origin="opening")
def lake_waterfall(P, seed):
    r = rng(seed, "lake.waterfall")
    h, w = P["height"], P["width"]
    nu, nv = 4, 8
    verts, faces, uvs = [], [], []
    P_ = []
    for j in range(nv + 1):
        t = j / nv
        z = h * (1 - t)
        y = 0.35 * math.sin(math.pi * t * 0.5) - 0.9 * t ** 2 + 1.2
        row = []
        for i in range(nu + 1):
            u = i / nu
            x = (u - 0.5) * w * (1 + 0.15 * t)
            row.append((x, y - 0.12 * math.sin(math.pi * u), z))
        P_.append(row)
    m = K.Mesh()
    for j in range(nv):
        for i in range(nu):
            q = [P_[j + 1][i], P_[j + 1][i + 1], P_[j][i + 1], P_[j][i]]
            uv = [(4.0 * i / nu, (j + 1) / nv * 1.5), (4.0 * (i + 1) / nu, (j + 1) / nv * 1.5), (4.0 * (i + 1) / nu, j / nv * 1.5),
                  (4.0 * i / nu, j / nv * 1.5)]
            m.add(q, [(0, 1, 2, 3)], "water", True, [("n", uv)])
    m = D.weld_mesh(m)
    lip = K.Mesh()
    lip.merge(D.rock_blob(0, 1.5, h - 0.1, w * 0.75, 0.9, 0.55, r, "cliff", segs=8, rings=4, jitter=0.12))
    for sx in (-1, 1):
        lip.merge(D.rock_blob(sx * (w / 2 + 0.6), 1.2, h * 0.5, 0.9, 0.8, h * 0.55, r, "cliff", segs=7, rings=4, jitter=0.15))
    foam = K.Mesh()
    for k in range(6):
        a = math.pi * (k + 0.5) / 6
        foam.merge(D.rock_blob(math.cos(a) * w * 0.6, 0.4 - math.sin(a) * 0.9, 0.0, r.uniform(0.25, 0.45), r.uniform(0.2, 0.35), r.uniform(0.12, 0.22), r,
                               "snow", segs=6, rings=3))
    meta = grid_meta("pool_centre", None, [sock("water", (0, 0, 0), "up"), sock("cliff_edge", (0, 0, -1.5), "n")],
                     material_extras={"water": {"scroll": [0.0, 0.55]}},
                     note="the water role scrolls along v (down the fall) at 0.55 UV/s on this piece only")
    return Asset([Node("falls", m, "shell"), Node("lip", lip), Node("foam", foam)], meta)


@register("lake.bed", V, "terrain", {
    "size": S.num(8.0, 4.0, 16.0), "depth": S.num(1.4, 0.6, 3.0), "weeds": S.integer(5, 0, 10),
}, "Underwater lake floor tile: soft sandy bed with pebble patches at the given depth below the water surface "
   "(origin = water surface centre), rounded stones and swaying weed tufts; seen from underwater views (fog tint).",
   origin="opening")
def lake_bed(P, seed):
    r = rng(seed, "lake.bed")
    s = P["size"] / 2
    dz = -P["depth"]
    bs = bumps(r, 6, (0.1, 0.1), (0.9, 0.9), amp=0.18, size=(0.1, 0.22))

    def fn(u, v):
        env = (math.sin(math.pi * u) * math.sin(math.pi * v)) ** 0.5
        return (u * 2 * s - s, v * 2 * s - s, dz + env * bump_field(bs, u, v))
    m = sheet(8, 8, fn, "sand", role_fn=lambda i, j, q: "path" if (i * 7 + j * 3) % 5 == 0 else "sand")
    rocks = K.Mesh()
    for k in range(4):
        rocks.merge(D.rock_blob(r.uniform(-s + 1, s - 1), r.uniform(-s + 1, s - 1), dz + 0.1, r.uniform(0.3, 0.6), r.uniform(0.25, 0.5), r.uniform(0.2, 0.35), r,
                                "rock", segs=6, rings=3))
    weeds = K.Mesh()
    for k in range(P["weeds"]):
        x, y = r.uniform(-s + 0.8, s - 0.8), r.uniform(-s + 0.8, s - 0.8)
        for b in range(3):
            a = r.uniform(0, 2 * math.pi)
            hh = r.uniform(0.4, 0.9)
            weeds.merge(K.tube([(x, y, dz), (x + 0.1 * math.cos(a), y + 0.1 * math.sin(a), dz + hh * 0.5),
                                (x + 0.25 * math.cos(a), y + 0.25 * math.sin(a), dz + hh)], [0.04, 0.03, 0.005], 3, "foliage", smooth=False))
    nodes = [Node("bed", m, "shell"), Node("rocks", rocks)]
    if weeds.f:
        nodes.append(Node("weeds", weeds))
    return Asset(nodes, grid_meta("water_centre", None, [sock("lake_bed", (0, 0, 0), "up", depth_m=P["depth"])]))
