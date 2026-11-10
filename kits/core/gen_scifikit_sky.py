"""SCIFIKIT star-field / planet sky backdrops (skyx.*): star-field dome or cylinder, a big planet (optional ring) and
a small moon, a nebula band behind windows, and distant horizon rings (mesas, spires, dunes).

All pieces are class `sky` (<= 128 tris, origin at the viewer) and use only the painted view-plane roles, so they
take the pack's sky treatment (unlit, fog-scaled): `sky` (dome), `view` (nebula band), `vista` and `vista_far`
(planets, moons, horizon rings). space_station binds sky/view to painted star fields and vista/vista_far to banded
planet textures; alien_world binds sky to its painted violet-to-peach sky, vista to the near mountain haze and
vista_far to a pale ringed planet. Recolour through those roles; original designs only."""
import math

from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register

V = "1.0.0"


def _sky_asset(nodes, meta):
    return Asset([n for n in nodes if n.mesh.f], dict(meta, station_grid={"anchor": "viewer"}))


@register("skyx.starfield", V, "sky", {
    "kind": S.enum("dome", ["dome", "cylinder"], "inward dome (12 x 4) or open cylinder band"),
    "radius": S.runtime(S.num(300.0, 30.0, 1500.0, "placement scale (inside the camera far plane)")),
    "below": S.num(0.12, 0.0, 0.4, "fraction of the radius below the horizon"),
}, "Star-field sky: inward-facing dome (or cylinder) carrying the pack's painted sky (role sky, v = elevation 0..1): "
   "deep space with nebula wisps and stars on space_station, the painted alien sky on alien_world.", origin="viewer")
def starfield(P, seed):
    R, seg = P["radius"], 12
    below = P["below"] * R
    verts, faces, uvs = [], [], []
    if P["kind"] == "dome":
        nr = 4
        e0 = -math.asin(min(0.99, below / R))
        elev = [e0 + (math.pi / 2 - e0) * j / nr for j in range(nr)]
        W = seg + 1
        for e in elev:
            verts.extend([(R * math.cos(e) * math.cos(math.tau * i / seg), R * math.cos(e) * math.sin(math.tau * i / seg),
                           R * math.sin(e)) for i in range(W)])
        vrow = [j / nr for j in range(nr)]
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
    else:
        Hc = R * 0.8
        W = seg + 1
        for z in (-below, Hc * 0.5, Hc):
            verts.extend([(R * math.cos(math.tau * i / seg), R * math.sin(math.tau * i / seg), z) for i in range(W)])
        vv = [0.0, 0.5, 1.0]
        for j in range(2):
            for i in range(seg):
                a = j * W + i
                faces.append((a, a + W, a + W + 1, a + 1))
                uvs.append(("n", [(i / seg, vv[j]), (i / seg, vv[j + 1]), ((i + 1) / seg, vv[j + 1]), ((i + 1) / seg, vv[j])]))
    return _sky_asset([Node("sky", K.Mesh().add(verts, faces, "sky", False, uvs), "shell")], {"kind": P["kind"]})


def _sphere_uv(R, seg, rings, role, cx, cy, cz, flat=1.0):
    verts, faces, uvs = [], [], []
    for j in range(rings + 1):
        lat = -math.pi / 2 + math.pi * j / rings
        for i in range(seg + 1):
            lon = math.tau * i / seg
            verts.append((cx + R * math.cos(lat) * math.cos(lon), cy + R * math.cos(lat) * math.sin(lon), cz + R * flat * math.sin(lat)))
    W = seg + 1
    for j in range(rings):
        for i in range(seg):
            a = j * W + i
            q = (a, a + 1, a + W + 1, a + W)
            uv = [(i / seg, j / rings), ((i + 1) / seg, j / rings), ((i + 1) / seg, (j + 1) / rings), (i / seg, (j + 1) / rings)]
            if j == 0:
                faces.append((a, a + W + 1, a + W))
                uvs.append(("n", [uv[0], uv[2], uv[3]]))
            elif j == rings - 1:
                faces.append((a, a + 1, a + W))
                uvs.append(("n", [uv[0], uv[1], uv[3]]))
            else:
                faces.append(q)
                uvs.append(("n", uv))
    m = K.Mesh().add(verts, faces, role, True, uvs)
    return m


@register("skyx.planet", V, "sky", {
    "role": S.enum("vista_far", ["vista_far", "vista"], "painted planet role (packs bind banded planet textures)"),
    "size": S.num(60.0, 5.0, 300.0, "planet radius (m) at its placement distance"),
    "distance": S.runtime(S.num(260.0, 60.0, 1200.0, "distance from the viewer along -Y (north) before rotation")),
    "elevation": S.num(0.22, 0.0, 0.8, "height above the horizon as a fraction of the distance"),
    "ring": S.boolean(False, "flat banded ring around the planet (same role)"),
    "oblate": S.num(0.94, 0.8, 1.0, "polar flattening"),
}, "Sky planet: a smooth banded sphere (10 x 6, painted terminator in the texture) hanging over the horizon, optionally "
   "ringed; moons are small presets. Place with the room backdrop or as a region piece far out.", origin="viewer")
def planet(P, seed):
    R, d = P["size"], P["distance"]
    cz = P["elevation"] * d
    nodes = [Node("planet", _sphere_uv(R, 8 if P["ring"] else 10, 6, P["role"], 0.0, d, cz, P["oblate"]), "shell")]
    if P["ring"]:
        seg = 10
        ri, ro = R * 1.35, R * 2.1
        verts, faces, uvs = [], [], []
        for i in range(seg + 1):
            a = math.tau * i / seg
            verts += [(ri * math.cos(a), d + ri * math.sin(a) * 0.32, cz + ri * math.sin(a) * 0.08),
                      (ro * math.cos(a), d + ro * math.sin(a) * 0.32, cz + ro * math.sin(a) * 0.08)]
        for i in range(seg):
            a = 2 * i
            faces.append((a, a + 1, a + 3, a + 2))
            uvs.append(("n", [(0.05, i / seg), (0.95, i / seg), (0.95, (i + 1) / seg), (0.05, (i + 1) / seg)]))
        ring = K.Mesh().add(verts, faces, P["role"], False, uvs)
        # visible from both sides: add the reversed copy (separate one-sided surface)
        back = K.Mesh().add(verts, [tuple(reversed(f)) for f in faces], P["role"], False,
                            [(u[0], list(reversed(u[1]))) for u in uvs])
        nodes += [Node("ring", ring, "shell"), Node("ring_back", back, "shell")]
    return _sky_asset(nodes, {"ring": P["ring"]})


@register("skyx.nebula", V, "sky", {
    "width": S.num(40.0, 10.0, 120.0, "band width"), "height": S.num(18.0, 6.0, 60.0, "band height"),
    "distance": S.runtime(S.num(30.0, 6.0, 200.0, "distance north of the origin")),
}, "Nebula band: a gently curved inward card (role view: painted star field, nebula and planet) placed beyond big "
   "windows and hangar mouths for parallax depth.", origin="viewer")
def nebula(P, seed):
    W, H, d = P["width"], P["height"], P["distance"]
    seg = 6
    verts, faces, uvs = [], [], []
    for i in range(seg + 1):
        t = i / seg
        a = (t - 0.5) * (W / d)
        x, y = d * math.sin(a), d * math.cos(a)
        verts += [(x, y, -H * 0.2), (x, y, H * 0.8)]
    for i in range(seg):
        a = 2 * i
        faces.append((a, a + 2, a + 3, a + 1))
        uvs.append(("n", [(i / seg, 0.0), ((i + 1) / seg, 0.0), ((i + 1) / seg, 1.0), (i / seg, 1.0)]))
    return _sky_asset([Node("nebula", K.Mesh().add(verts, faces, "view", False, uvs), "shell")], {})


HORIZON = ("mesas", "spires", "dunes")


@register("skyx.horizon", V, "sky", {
    "kind": S.enum("mesas", list(HORIZON), "flat-topped mesas, needle spires or rolling dunes"),
    "radius": S.runtime(S.num(90.0, 30.0, 400.0, "ring radius")),
    "height": S.num(0.12, 0.03, 0.3, "silhouette height as a fraction of the radius"),
    "role": S.enum("vista", ["vista", "vista_far"]),
}, "Horizon ring: an inward silhouette ring around the viewer (v = 0 at the base .. 1 at the crest so the pack's "
   "vista haze gradient paints it): flat-topped mesas, needle spires or dunes, original alien skylines.",
   origin="viewer")
def horizon(P, seed):
    R, kind = P["radius"], P["kind"]
    Hh = P["height"] * R
    seg = 30
    import numpy as np
    rs = np.random.default_rng(seed + 23)
    tops = []
    for i in range(seg):
        t = i / seg
        if kind == "mesas":
            blocks = math.sin(t * math.tau * 5 + 1.3) + 0.6 * math.sin(t * math.tau * 9)
            h = 0.25 + (0.75 if blocks > 0.4 else 0.15 * rs.random())
        elif kind == "spires":
            h = 0.3 + (0.7 if (i % 4 == 1 and rs.random() > 0.3) else 0.2 * rs.random())
        else:
            h = 0.35 + 0.25 * (math.sin(t * math.tau * 3) + 1) / 2 + 0.1 * rs.random()
        tops.append(h)
    verts, faces, uvs = [], [], []
    for i in range(seg + 1):
        a = math.tau * i / seg
        h = tops[i % seg]
        c, s = math.cos(a), math.sin(a)
        verts += [(R * c, R * s, -0.08 * R), (R * c, R * s, Hh * h)]
    for i in range(seg):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))      # inward facing (normal toward the viewer)
        uvs.append(("n", [(i / seg, 0.0), (i / seg, tops[i]), ((i + 1) / seg, tops[(i + 1) % seg]), ((i + 1) / seg, 0.0)]))
    return _sky_asset([Node("horizon", K.Mesh().add(verts, faces, P["role"], False, uvs), "shell")], {"kind": kind})
