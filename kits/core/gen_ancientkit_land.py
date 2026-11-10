"""ANCIENTKIT desert / jungle terrain and sky backdrop sets (land.*), theme-agnostic (Blender space, +Z up).

Eight generators (presets make the pieces): ground tiles on the RUIN GRID whose edges sit exactly on the ground datum
(so any two tiles meet without a seam) and whose interior undulates (dune ripples, leaf-litter hummocks), mesa cliff
segments with strata faces and a sand cap, sand slopes between tier levels, raised paved causeways with kerbs, and
the sky backdrop set: an inward dome painted by the pack's `sky` role (deep zenith, pale horizon haze = the exterior
fog colour, the sun) with an optional ring of distant silhouettes (mesas, dunes, jungle canopy) in the `vista_far`
role. The sky dome is bound to the runtime's `sky.backdrop` name by the ANCIENTKIT bindings. Terraces (raised
plateau blocks for tiered terrain), dry washes (stream-bed tiles that chain north-south) and distant skyline cards
(temple city, mesas, jungle canopy) complete the family.
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
CELL = A.CELL


def _vnoise(rs, x, y, scale):
    """Smooth deterministic value noise from a small seeded lattice (no hash())."""
    g = rs.random((9, 9))
    fx, fy = x / scale, y / scale
    ix, iy = int(math.floor(fx)) % 8, int(math.floor(fy)) % 8
    tx, ty = fx - math.floor(fx), fy - math.floor(fy)
    sx, sy = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a, b = g[iy, ix], g[iy, ix + 1]
    c, d = g[iy + 1, ix], g[iy + 1, ix + 1]
    return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy


# ---------------------------------------------------------------- land.ground
@register("land.ground", V, "terrain", {
    "style": S.enum("sand", ["sand", "jungle", "paved", "court"]), "cells": S.integer(2, 1, 4, "square tile side in cells"),
    "relief": S.num(0.35, 0.0, 0.8, "interior undulation amplitude (m); edges stay on the datum"),
}, "Ground tile on the RUIN GRID (cells x 4 m square, open sheet facing up): sand = soft dune ripples (sand role); "
   "jungle = earth and moss patches with hummocks (dirt role); paved = worn flagstones (path role); court = flat paving "
   "(path role). Edges lie exactly on the ground datum so tiles interlock edge to edge.", origin="terrain_center")
def ground(P, seed):
    r = rng(seed, "land.ground", P["style"])
    nrs = np.random.default_rng(int(r.random() * 2 ** 31))
    st, n_c = P["style"], P["cells"]
    size = n_c * CELL
    # 2 m vertex spacing on real relief, 4 m on paving and on low-relief (distant) tiles
    res = n_c * 2 if st in ("sand", "jungle") and P["relief"] >= 0.2 else n_c
    amp = 0.0 if st == "court" else P["relief"] * (0.35 if st == "paved" else 1.0)
    half = size / 2
    lattice = nrs.random((9, 9))
    crest = r.uniform(0, TAU)

    def edge(x, y):
        dx = min(x + half, half - x) / max(2.0, size * 0.25)
        dy = min(y + half, half - y) / max(2.0, size * 0.25)
        t = max(0.0, min(1.0, min(dx, dy)))
        return t * t * (3 - 2 * t)

    def zfn(x, y):
        if amp == 0.0:
            return 0.0
        fx, fy = (x + half) / size * 3.0, (y + half) / size * 3.0
        ix, iy = int(fx) % 8, int(fy) % 8
        tx, ty = fx - int(fx), fy - int(fy)
        sx, sy = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        n = (lattice[iy, ix] * (1 - sx) + lattice[iy, ix + 1] * sx) * (1 - sy) + (lattice[iy + 1, ix] * (1 - sx) + lattice[iy + 1, ix + 1] * sx) * sy
        if st == "sand":
            ripple = 0.25 * math.sin((x * math.cos(crest) + y * math.sin(crest)) * 1.1)
            return amp * (n - 0.35 + ripple) * edge(x, y)
        return amp * (n - 0.3) * edge(x, y)

    # one role per style: per-quad role switching on a 2-4 m grid paints rectangles (a checkerboard), so the large-scale
    # variation comes from the painted texture (dune ripples, earth/moss patches) and the baked vertex variation
    # ground roles are the runtime's GROUND_ROLES (assets.gd) so capture masks and the style gate see them as ground
    role = {"sand": "sand", "jungle": "dirt", "paved": "path", "court": "path"}[st]

    sheet = A.height_sheet(-half, -half, half, half, res, res, zfn, role, smooth=True)
    sheet = A.weld(sheet)
    a = Asset([Node("ground", sheet, "shell")], A.grid_meta("cell_block_centre", (n_c, n_c), [
        A.sock("ground_edge", (-half, 0, 0), "w"), A.sock("ground_edge", (half, 0, 0), "e"),
        A.sock("ground_edge", (0, -half, 0), "s"), A.sock("ground_edge", (0, half, 0), "n")], style=st, datum_m=0.0))
    a.meta["bbox_size_m"] = [round(float(x), 4) for x in np.ptp(np.asarray(sheet.v), axis=0)]
    return a


# ---------------------------------------------------------------- land.cliff
@register("land.cliff", V, "terrain", {
    "style": S.enum("straight", ["straight", "corner", "end", "pillar"]), "height": S.num(6.0, 2.0, 12.0),
    "length": S.num(8.0, 4.0, 12.0),
}, "Mesa cliff on cell edges: a strata-banded face (cliff role) with jittered ledges, eroded buttresses and a sand cap "
   "on top; straight = a run along one edge, corner = an outer corner, end = a tapering spur, pillar = a free mesa "
   "butte. Closed solid; the face stands on its cell edge facing south (origin on the edge line at the datum; the rock "
   "runs 3 m back to the north).", origin="cell_edge")
def cliff(P, seed):
    r = rng(seed, "land.cliff", P["style"])
    st, h, L = P["style"], P["height"], P["length"]
    nodes = []
    if st == "pillar":
        rings, k = [], 9
        for j, (z, rad) in enumerate(((0.0, 3.0), (h * 0.35, 2.6), (h * 0.7, 2.35), (h, 2.2))):
            ring = []
            for i in range(k):
                a = TAU * i / k
                rr = rad * r.uniform(0.82, 1.12)
                ring.append((rr * math.cos(a), rr * math.sin(a), z + (r.uniform(-0.15, 0.15) if 0 < j < 3 else 0.0)))
            rings.append(ring)
        body = K.loft(rings, "cliff", smooth=False, cap_roles=("cliff", "sand"))
        nodes.append(Node("butte", body))
    else:
        depth = 3.0
        if st == "straight":
            path = [(-L / 2, 0.0), (L / 2, 0.0)]
        elif st == "corner":
            path = [(-L / 2, 0.0), (0.0, 0.0), (0.0, L / 2)]
        else:
            path = [(-L / 2, 0.0), (L / 2 - 1.5, 0.0)]
        # face profile: d from the face (0) back into the rock (-depth -> left of the path = north), bumpy ledges
        prof = [(0.0, 0.0), (0.35, h * 0.3), (0.05, h * 0.55), (0.25, h * 0.8), (0.0, h), (-depth, h), (-depth, 0.0)]
        prof = [(-d if i < 5 else d, z) for i, (d, z) in enumerate(prof)]
        prof = [(d, z) for d, z in prof]
        body = A.sweep(path, [(-d, z) for d, z in prof], "cliff")
        # jitter face vertices (not the cap) for an eroded look
        Vv = np.asarray(body.v)
        jit = np.array([r.uniform(-0.18, 0.18) for _ in range(len(Vv))])
        on_face = (Vv[:, 2] > 0.2) & (Vv[:, 2] < h - 0.2)
        Vv[:, 1] = Vv[:, 1] + np.where(on_face, jit, 0.0)
        body.v = [tuple(p) for p in Vv.tolist()]
        # cap role on upward faces
        for fi, f in enumerate(body.f):
            p = Vv[list(f)]
            nrm = np.cross(p[1] - p[0], p[2] - p[0])
            if np.linalg.norm(nrm) > 0 and nrm[2] / np.linalg.norm(nrm) > 0.9 and p[:, 2].min() > h - 0.05:
                body.r[fi] = "sand"
        nodes.append(Node("cliff", body))
        if st == "end":
            spur = A.rock(L / 2 - 0.9, -0.8, h * 0.35, 1.4, 1.4, h * 0.4, r, "cliff", segs=6, rings=3)
            nodes.append(Node("spur", spur))
        tal = K.Mesh()
        for i in range(2):
            x = r.uniform(-L / 2 + 1, L / 2 - 2)
            tal.merge(A.rock(x, -1.0 - r.uniform(0, 0.5), 0.25, 0.7, 0.55, 0.45, r, "rock", segs=5, rings=3))
        nodes.append(Node("talus", tal))
    socks = A.edge_sockets(L) if st == "straight" else []
    anchor = {"pillar": "free", "corner": "corner"}.get(st, "cell_edge")
    a = finalize(nodes, A.grid_meta(anchor, None, socks, style=st, height_m=h),
                 center_x=st != "corner", center_y=False)
    return a


# ---------------------------------------------------------------- land.slope
@register("land.slope", V, "terrain", {
    "rise": S.num(2.0, 0.5, 4.0), "width_cells": S.integer(1, 1, 3), "style": S.enum("sand", ["sand", "earth"]),
}, "Slope between terrace levels inside one cell run (4 m long, width_cells x 4 m wide): a soft S-curved sand or earth "
   "ramp climbing north with cliff-role flanks. Sockets at the foot (ground datum) and the crest (at the rise).",
   origin="floor_center")
def slope(P, seed):
    rise, w = P["rise"], P["width_cells"] * CELL
    role = "sand" if P["style"] == "sand" else "dirt"
    n = 6
    side = [(-CELL / 2, 0.0)]
    for i in range(n + 1):
        t = i / n
        side.append((-CELL / 2 + CELL * t, rise * (t * t * (3 - 2 * t))))
    side.append((CELL / 2, 0.0))
    pts = side[1:]
    m = K.prism([(y, z) for y, z in pts], -w / 2, w / 2, "cliff")
    m.apply(lambda q: q[:, [2, 0, 1]])
    m = m.orient_outward()
    Vv = np.asarray(m.v)
    for fi, f in enumerate(m.f):
        p = Vv[list(f)]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        ln = np.linalg.norm(nrm)
        if ln > 0 and nrm[2] / ln > 0.2:
            m.r[fi] = role
    meta = A.grid_meta("cell_centre", (P["width_cells"], 1), [A.sock("slope_foot", (0, -CELL / 2, 0), "s", width_m=w),
                                                               A.sock("slope_crest", (0, CELL / 2, rise), "n", width_m=w)], rise_m=rise)
    return finalize([Node("slope", m)], meta)


# ---------------------------------------------------------------- land.causeway
@register("land.causeway", V, "structure", {
    "style": S.enum("straight", ["straight", "steps", "end", "broken"]), "height": S.num(0.6, 0.25, 1.5),
}, "Raised paved causeway for one cell (3 m wide deck running north-south): a battered stone body, worn path paving on "
   "top and kerb stones along both edges; steps = a short flight down to the ground at the south end; end = a "
   "rounded terminus; broken = a collapsed middle with fallen slabs. Edge sockets on the north and south cell edges "
   "(origin on the cell centre at the datum; the steps run out past the south edge).", origin="cell_centre")
def causeway(P, seed):
    r = rng(seed, "land.causeway", P["style"])
    st, hh = P["style"], P["height"]
    w = 3.0
    nodes = []
    if st == "broken":
        for sy in (-1, 1):
            nodes.append(Node("deck_%s" % ("s" if sy < 0 else "n"), A.taper_box(0, sy * 1.25, 0.0, hh, w + 0.4, 1.5, w, 1.4, "wall",
                                                                                     bevel=0.05, top_role="path")))
        fall = K.Mesh()
        for i in range(3):
            fall.merge(A.block_chunk(r.uniform(-1.0, 1.0), r.uniform(-0.4, 0.4), 0.0, 0.9, 0.7, 0.3, r, "stone", tilt=r.uniform(-0.4, 0.4)))
        nodes.append(Node("fallen", fall))
    else:
        L = CELL if st != "end" else CELL * 0.75
        y0 = 0.0 if st != "end" else -CELL * 0.125
        nodes.append(Node("deck", A.taper_box(0, y0, 0.0, hh, w + 0.4, L, w, L, "wall", bevel=0.05, top_role="path")))
        kerb = K.Mesh()
        for sx in (-1, 1):
            kerb.merge(A.frustum(sx * (w / 2 - 0.12), y0, hh, hh + 0.16, 0.26, L - 0.1, 0.18, L - 0.14, "trim"))
        nodes.append(Node("kerbs", kerb))
        if st == "steps":
            n = max(1, int(round(hh / A.STEP_RISE)))
            fl = K.Mesh()
            for i in range(n):
                z1 = hh - (i + 1) * (hh / n)
                fl.merge(A.chamfer_box(0, -CELL / 2 - 0.2 - i * 0.4, 0.0, w - 0.3, 0.42, max(0.06, z1 + hh / n), "step", bevel=0.03))
            nodes.append(Node("steps", fl))
        if st == "end":
            nodes.append(Node("terminus", A.lathe([(0.0, 0.0), (w / 2 + 0.2, 0.0), (w / 2, hh), (0.0, hh)], 8, "wall", smooth=False,
                                                  cy=CELL / 2 - 0.4)))
    meta = A.grid_meta("cell_centre", (1, 1), [A.sock("edge", (0, -CELL / 2, hh), "s", width_m=w), A.sock("edge", (0, CELL / 2, hh), "n", width_m=w)],
                       style=st, deck_m=hh)
    return finalize(nodes, meta, center_y=False)


# ---------------------------------------------------------------- land.sky
@register("land.sky", V, "sky", {
    "horizon": S.enum("none", ["none", "mesas", "dunes", "canopy"]),
    "radius": S.runtime(S.num(400.0, 20.0, 1800.0, "placement scale (fit inside the camera far plane)")),
    "sun_azimuth": S.num(0.0, -180.0, 180.0, "turns the painted sun around the viewer (degrees)"),
}, "Sky backdrop set: inward-facing dome (kit_shell_sky, role 'sky': the pack's painted deep zenith, pale horizon haze "
   "= fog colour, and the sun) plus an optional ring of distant silhouettes in the vista_far role (flat-topped mesas, "
   "rolling dunes or a jungle canopy line) just inside the dome. Origin at the viewer; bound as `sky.backdrop`.",
   origin="viewer")
def sky(P, seed):
    r = rng(seed, "land.sky", P["horizon"])
    R = P["radius"]
    seg, nr = 12, 4
    below = 0.15 * R
    e0 = -math.asin(min(0.99, below / R))
    elev = [e0 + (math.pi / 2 - e0) * j / nr for j in range(nr)]
    rows = [[(R * math.cos(e) * math.cos(TAU * i / seg), R * math.cos(e) * math.sin(TAU * i / seg), R * math.sin(e)) for i in range(seg + 1)]
            for e in elev]
    vrow = [j / nr for j in range(nr)]
    verts, faces, uvs = [], [], []
    for row in rows:
        verts.extend(row)
    W = seg + 1
    for j in range(len(rows) - 1):
        for i in range(seg):
            a = j * W + i
            faces.append((a, a + W, a + W + 1, a + 1))
            uvs.append(("n", [(i / seg, vrow[j]), (i / seg, vrow[j + 1]), ((i + 1) / seg, vrow[j + 1]), ((i + 1) / seg, vrow[j])]))
    apex = len(verts)
    verts.append((0.0, 0.0, R))
    off = (len(rows) - 1) * W
    for i in range(seg):
        faces.append((off + i, apex, off + i + 1))
        uvs.append(("n", [(i / seg, vrow[-1]), ((i + 0.5) / seg, 1.0), ((i + 1) / seg, vrow[-1])]))
    dome = K.Mesh().add(verts, faces, "sky", False, uvs)
    nodes = [Node("sky", _inward(dome), "shell")]
    if P["horizon"] != "none":
        k = 16
        rr = R * 0.9
        ring_b, ring_t = [], []
        for i in range(k + 1):
            a = TAU * i / k
            if P["horizon"] == "mesas":
                hgt = R * (0.075 if (i % 4) in (1, 2) else 0.03) * r.uniform(0.85, 1.15)
            elif P["horizon"] == "dunes":
                hgt = R * (0.035 + 0.02 * math.sin(a * 3 + 1.0)) * r.uniform(0.9, 1.1)
            else:
                hgt = R * (0.06 + 0.025 * math.sin(a * 5) + 0.015 * r.uniform(-1, 1))
            if i == k:
                hgt = ring_t[0][2]
            ring_b.append((rr * math.cos(a), rr * math.sin(a), -0.02 * R))
            ring_t.append((rr * math.cos(a), rr * math.sin(a), hgt))
        hv = ring_b + ring_t
        hf, hu = [], []
        for i in range(k):
            hf.append((i, i + 1, k + 2 + i, k + 1 + i))
            hu.append(("n", [(i / k, 0.0), ((i + 1) / k, 0.0), ((i + 1) / k, 1.0), (i / k, 1.0)]))
        band = K.Mesh().add(hv, hf, "vista_far", False, hu)
        nodes.append(Node("horizon", _inward(band), "shell"))
    if P["sun_azimuth"]:
        for n in nodes:
            n.mesh.rotate_z(math.radians(P["sun_azimuth"]))
    allv = np.concatenate([np.asarray(n.mesh.v) for n in nodes])
    return Asset(nodes, {"kind": "dome", "radius_m": R, "origin": "viewer", "horizon": P["horizon"],
                         "bbox_size_m": [round(float(x), 4) for x in np.ptp(allv, axis=0)]})


def _inward(m):
    Av = np.asarray(m.v)
    for fi, f in enumerate(m.f):
        p = Av[list(f)]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(nrm) < 1e-12 and len(f) > 3:
            nrm = np.cross(p[2] - p[0], p[3] - p[0])
        if np.dot(nrm, -p.mean(0)) < 0:
            m.f[fi] = tuple(reversed(f))
            if m.uv[fi] is not None:
                m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
    return m


# ---------------------------------------------------------------- land.terrace
@register("land.terrace", V, "terrain", {
    "cells": S.integer(2, 1, 3, "square plateau side in cells"), "height": S.num(2.0, 0.5, 4.0, "plateau top (m)"),
    "style": S.enum("sand", ["sand", "jungle"]), "batter": S.num(0.4, 0.0, 0.8, "how far the foot spreads past the cells (m)"),
}, "Raised terrace / plateau block for tiered terrain: a flat top (sand or earth-and-moss) on battered, eroded "
   "cliff-role sides, cells x 4 m at the top so a land.slope crest or a stair flight meets its edge on the grid. Closed "
   "solid; the foot spreads `batter` m past the cell block and sinks below the datum. Sockets 'terrace_edge' on the four "
   "top edges.", origin="terrain_center")
def terrace(P, seed):
    r = rng(seed, "land.terrace", P["style"])
    n_c, h, bat = P["cells"], P["height"], P["batter"]
    top_role = "sand" if P["style"] == "sand" else "dirt"
    half = n_c * CELL / 2
    k = 2 * n_c                                           # vertices per side (2 m spacing)

    def ring(hw, z, jit):
        pts = []
        for side in range(4):
            for i in range(k):
                t = -1.0 + 2.0 * i / k
                x, y = {0: (t * hw, -hw), 1: (hw, t * hw), 2: (-t * hw, hw), 3: (-hw, -t * hw)}[side]
                if jit and i:
                    d = r.uniform(-jit, jit)
                    x, y = (x, y + (-d if side == 0 else d)) if side in (0, 2) else (x + (d if side == 1 else -d), y)
                pts.append((x, y, z))
        return pts

    rings = [ring(half + bat, -0.15, 0.0), ring(half + bat * 0.55, h * 0.45, 0.22), ring(half, h, 0.0)]
    body = K.loft(rings, "cliff", smooth=False, cap_roles=("cliff", top_role))
    nodes = [Node("terrace", body)]
    socks = [A.sock("terrace_edge", (0, -half, h), "s", width_m=2 * half), A.sock("terrace_edge", (0, half, h), "n", width_m=2 * half),
             A.sock("terrace_edge", (-half, 0, h), "w", width_m=2 * half), A.sock("terrace_edge", (half, 0, h), "e", width_m=2 * half)]
    return finalize(nodes, A.grid_meta("cell_block_centre", (n_c, n_c), socks, top_m=h, datum_m=0.0), center_x=False,
                    center_y=False, ground=False)


# ---------------------------------------------------------------- land.wash
@register("land.wash", V, "terrain", {
    "cells": S.integer(2, 1, 3, "square tile side in cells"), "depth": S.num(0.45, 0.2, 0.9),
    "style": S.enum("sand", ["sand", "jungle"]),
}, "Dry wash / stream-bed ground tile: a cells x 4 m ground sheet with a meandering sunken channel running north-south "
   "(the channel re-centres on the tile's north and south edges so washes chain tile to tile) and a scatter of rounded "
   "pebbles in its bed. Outside the channel the edges lie on the ground datum like land.ground. Sockets 'wash' where "
   "the channel crosses the north and south edges, 'ground_edge' on east and west.", origin="terrain_center")
def wash(P, seed):
    r = rng(seed, "land.wash", P["style"])
    n_c, dep = P["cells"], P["depth"]
    role = "sand" if P["style"] == "sand" else "dirt"
    half = n_c * CELL / 2
    amp = 0.7 * min(1.0, n_c / 2.0)
    ph = r.uniform(0, TAU)

    def centre(y):
        t = (y + half) / (2 * half)
        return amp * math.sin(t * TAU + ph) * math.sin(t * math.pi)       # 0 at both edges: chains

    def zfn(x, y):
        d = abs(x - centre(y)) / 1.15
        return -dep * max(0.0, 1.0 - d * d) if d < 1.0 else 0.0

    sheet = A.height_sheet(-half, -half, half, half, n_c * 4, n_c * 2, zfn, role, smooth=True)
    nodes = [Node("ground", sheet, "shell")]
    peb = K.Mesh()
    for i in range(3 * n_c):
        y = -half + (i + 0.5) * (2 * half) / (3 * n_c) + r.uniform(-0.3, 0.3)
        x = centre(y) + r.uniform(-0.45, 0.45)
        rad = r.uniform(0.18, 0.32)
        peb.merge(A.rock(x, y, zfn(x, y) + rad * 0.35, rad, rad * 0.85, rad * 0.6, r, "rock", segs=5, rings=3))
    nodes.append(Node("pebbles", peb))
    socks = [A.sock("wash", (0, -half, -dep), "s", width_m=2.3), A.sock("wash", (0, half, -dep), "n", width_m=2.3),
             A.sock("ground_edge", (-half, 0, 0), "w"), A.sock("ground_edge", (half, 0, 0), "e")]
    return finalize(nodes, A.grid_meta("cell_block_centre", (n_c, n_c), socks, style=P["style"], datum_m=0.0),
                    center_x=False, center_y=False, ground=False)


# ---------------------------------------------------------------- land.skyline
SKYLINES = {
    # (x from -1..1 across the card, height as a fraction of the card height) outline vertices, left to right
    "city": [(-1.0, 0.0), (-1.0, 0.12), (-0.86, 0.12), (-0.86, 0.22), (-0.78, 0.22), (-0.78, 0.32), (-0.7, 0.32),
             (-0.7, 0.22), (-0.62, 0.22), (-0.62, 0.12), (-0.5, 0.12), (-0.47, 0.62), (-0.44, 0.12), (-0.3, 0.12),
             (-0.3, 0.2), (-0.2, 0.2), (-0.2, 0.36), (-0.1, 0.36), (-0.1, 0.52), (0.0, 0.52), (0.0, 0.68), (0.1, 0.68),
             (0.1, 0.52), (0.2, 0.52), (0.2, 0.36), (0.3, 0.36), (0.3, 0.2), (0.4, 0.2), (0.4, 0.12), (0.52, 0.12),
             (0.52, 0.3), (0.6, 0.27), (0.6, 0.12), (0.7, 0.12), (0.72, 0.46), (0.74, 0.12), (0.84, 0.12), (0.84, 0.18),
             (0.92, 0.18), (0.92, 0.1), (1.0, 0.1), (1.0, 0.0)],
    "mesas": [(-1.0, 0.0), (-1.0, 0.18), (-0.84, 0.2), (-0.74, 0.52), (-0.5, 0.54), (-0.42, 0.24), (-0.2, 0.2), (-0.12, 0.34),
              (0.1, 0.36), (0.16, 0.18), (0.38, 0.16), (0.46, 0.66), (0.72, 0.64), (0.8, 0.22), (1.0, 0.18), (1.0, 0.0)],
    "canopy": [(-1.0, 0.0), (-1.0, 0.3), (-0.9, 0.42), (-0.78, 0.36), (-0.66, 0.5), (-0.52, 0.4), (-0.4, 0.46), (-0.3, 0.4),
               (-0.16, 0.44), (-0.08, 0.4), (-0.06, 0.62), (0.0, 0.62), (0.0, 0.74), (0.06, 0.74), (0.06, 0.62),
               (0.12, 0.62), (0.14, 0.42), (0.26, 0.5), (0.4, 0.4), (0.54, 0.48), (0.68, 0.38), (0.8, 0.46), (0.92, 0.36),
               (1.0, 0.4), (1.0, 0.0)],
}


@register("land.skyline", V, "terrain", {
    "style": S.enum("city", ["city", "mesas", "canopy"]), "width": S.num(60.0, 20.0, 120.0), "height": S.num(18.0, 6.0, 40.0),
}, "Distant skyline card for the far band (vista_far role, so it takes the pack's horizon haze and most of the "
   "distance fog): one flat silhouette facing south. city = an original temple-city outline (stepped pyramids, a "
   "pylon pair, obelisk spikes, broken colonnade stumps); mesas = flat-topped buttes; canopy = rounded jungle crowns "
   "with a stepped pyramid top breaking through. Place 50-120 m out; its foot sinks 1 m below the datum.",
   origin="terrain_center")
def skyline(P, seed):
    w, h = P["width"], P["height"]
    outline = [(x * w / 2, z * h - (1.0 if z == 0.0 else 0.0)) for x, z in SKYLINES[P["style"]]]
    verts = [(x, 0.0, z) for x, z in outline]
    face = list(range(len(verts)))[::-1]                  # wound to face -y (south, toward the viewer)
    uvs = [("n", [((verts[i][0] + w / 2) / w, max(0.0, verts[i][2]) / h) for i in face])]
    m = K.Mesh().add(verts, [tuple(face)], "vista_far", False, uvs)
    return Asset([Node("skyline", m, "shell")], {"kind": "skyline", "style": P["style"], "origin": "terrain_center",
                                                   "bbox_size_m": [round(w, 4), 0.0, round(h + 1.0, 4)]})
