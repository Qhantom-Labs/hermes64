"""SCIFIKIT ships and vehicles (ship.*): small shuttle, cargo hauler, six-wheel rover, escape pod, service drone.

Original silhouettes (no franchise ship is copied): the shuttle is a blunt-nosed octagonal wedge with a dorsal spine,
downswept stub wings ending in round tip pods and twin rear thrusters on landing skids; the hauler is a long spine
with a bubble cab, clamped cargo pods and four rear nacelles on tapered legs; the rover is a raised chamfered chassis
with a slant-glass cab, a mast dish and six lathed wheels; the escape pod is a faceted cone capsule with a heat shield
and a round side hatch. Blender space: +Z up, nose to -Y (glTF +Z). Landed vehicles stand on the floor (origin
floor_center). Recolour through the hull / hull_alt / glass / light / fire roles."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from . import sfkit as F
from .asset import Asset, Node, register

V = "1.0.0"


def _asset(nodes, meta, ao=0.3, reach=1.0, ground=True):
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


def _nozzle(x, y, z, r, length, role="metal", glow="fire", segs=6):
    """Thruster bell pointing +Y: one closed flared cone whose back cap glows (fire role)."""
    bell = F.lathe([(0.0, 0.0), (r * 0.62, 0.0), (r, length), (0.0, length)], segs, role, smooth=False,
                   cap_roles=(role, glow), roles=[role, role, glow])
    return bell.rotate_x(-math.pi / 2).translate(x, y, z)


# ------------------------------------------------------------------ shuttle
HULL_OCT = F.chamfer_rect(2.4, 1.6, 0.46)       # (x, z) section of the shuttle body
WING_SEC = [(-0.7, 0.0), (0.5, -0.08), (0.8, 0.0), (0.5, 0.1), (-0.5, 0.12)]   # (y, z) wing section, CCW


@register("ship.shuttle", V, "vehicle", {
    "gear": S.enum("skids", ["skids", "pod"], "skids: landing skids on struts; pod: skids plus a belly cargo pod"),
    "wings": S.enum("down", ["down", "level"], "downswept or level stub wings"),
}, "Small shuttle (6.6 m): blunt-nosed octagonal wedge with a dorsal spine, slanted canopy, downswept stub wings "
   "ending in round tip pods, twin rear thrusters with glowing bells and landing skids (optional belly cargo pod). "
   "Original silhouette.", origin="floor_center")
def shuttle(P, seed):
    zc = 1.45
    body = F.loft_y(HULL_OCT, [(-3.3, 0.28, 0.3, 0.0, zc - 0.12), (-2.75, 0.72, 0.62, 0.0, zc - 0.05),
                               (-1.7, 0.98, 0.86, 0.0, zc), (0.6, 1.0, 1.0, 0.0, zc + 0.06), (2.1, 0.9, 0.94, 0.0, zc + 0.08),
                               (2.7, 0.7, 0.74, 0.0, zc + 0.08)], "hull",
                    roles=["hull", "hull", "hull", "hull", "hull_alt"])
    canopy = F.loft_y(F.chamfer_rect(1.3, 0.5, 0.0), [(-2.55, 0.5, 0.5, 0.0, zc + 0.36), (-2.05, 0.9, 0.95, 0.0, zc + 0.6),
                                                      (-1.2, 0.85, 0.9, 0.0, zc + 0.72), (-0.7, 0.55, 0.6, 0.0, zc + 0.7)], "glass")
    spine = F.loft_y(F.chamfer_rect(0.36, 0.6, 0.0), [(-0.9, 0.6, 0.4, 0.0, zc + 0.78), (0.4, 1.0, 1.0, 0.0, zc + 0.98),
                                                       (2.3, 0.9, 1.25, 0.0, zc + 1.02), (2.75, 0.5, 0.6, 0.0, zc + 0.92)], "hull_alt")
    nodes = [Node("body", body), Node("canopy", canopy), Node("spine", spine)]
    drop = 0.55 if P["wings"] == "down" else 0.0
    wings, pods = [], []
    for sx in (-1, 1):
        wings.append(F.loft_x(WING_SEC, [(sx * 0.95, 1.6, 1.4, 0.4, zc - 0.1), (sx * 2.9, 0.75, 0.9, 0.95, zc - 0.1 - drop)],
                              "hull").orient_outward())
        pod = F.lathe([(0.0, -0.9), (0.22, -0.4), (0.22, 0.5), (0.0, 0.78)], 6, "hull_alt", smooth=True)
        pods.append(pod.rotate_x(-math.pi / 2).translate(sx * 3.0, 0.95, zc - 0.1 - drop))
    nodes += [Node("wings", F.merged(*wings)), Node("tip_pods", F.merged(*pods))]
    nodes.append(Node("thrusters", F.merged(*[_nozzle(sx * 0.62, 2.55, zc + 0.02, 0.36, 0.7) for sx in (-1, 1)])))
    skids, struts = [], []
    for sx in (-1, 1):
        skids.append(F.tube([(sx * 1.05, -2.2, 0.3), (sx * 1.05, -1.9, 0.07), (sx * 1.05, 1.9, 0.07), (sx * 1.05, 2.15, 0.28)],
                            0.07, 4, "trim", smooth=False))
        for y in (-1.4, 1.3):
            struts.append(F.loft_levels(F.chamfer_rect(0.14, 0.2, 0.0), [(0.16, 1.0, 1.0, sx * 1.0, y),
                                                                          (zc - 0.62, 0.8, 0.8, sx * 0.84, y)], "metal"))
    nodes += [Node("skids", F.merged(*skids)), Node("struts", F.merged(*struts))]
    nodes.append(Node("nav_lights", F.merged(*[F.bevel_block(sx * 3.0, 0.1, zc - 0.1 - drop + 0.2, 0.08, 0.3, 0.06, "light",
                                                             bevel=0.0) for sx in (-1, 1)])))
    if P["gear"] == "pod":
        nodes.append(Node("cargo_pod", F.loft_y(F.chamfer_rect(1.2, 0.6, 0.2), [(-1.2, 0.8, 0.8, 0.0, zc - 0.74),
                                                                             (-0.8, 1.0, 1.0, 0.0, zc - 0.8),
                                                                             (1.0, 1.0, 1.0, 0.0, zc - 0.8),
                                                                             (1.3, 0.8, 0.8, 0.0, zc - 0.74)], "body_alt")))
    return _asset(nodes, {"gear": P["gear"], "emitter": "shuttle_engines"}, ao=0.28, reach=1.2)


# ------------------------------------------------------------------ hauler
@register("ship.hauler", V, "vehicle", {
    "pods": S.integer(4, 0, 4, "clamped cargo pods along the spine (0 = empty frame)"),
}, "Cargo hauler (12 m): long chamfered spine with a bubble cab at the nose, clamp frames carrying up to four cargo "
   "pods with hazard bands, four rear nacelles and tapered landing legs. Original silhouette.", origin="floor_center")
def hauler(P, seed):
    zc = 2.3
    spine = F.loft_y(F.chamfer_rect(1.0, 0.8, 0.0), [(-4.4, 0.8, 0.8, 0.0, zc + 0.3), (-3.6, 1.0, 1.0, 0.0, zc + 0.3),
                                                      (4.6, 1.0, 1.0, 0.0, zc + 0.3), (5.2, 0.8, 0.9, 0.0, zc + 0.3)], "hull")
    cab = F.loft_y(F.chamfer_rect(2.2, 1.8, 0.6), [(-6.4, 0.4, 0.42, 0.0, zc + 0.5), (-5.6, 1.0, 1.0, 0.0, zc + 0.46),
                                                   (-4.0, 0.88, 0.86, 0.0, zc + 0.42), (-3.4, 0.5, 0.55, 0.0, zc + 0.38)], "hull",
                   roles=["hull", "hull", "hull_alt"])
    glass = F.loft_y(F.chamfer_rect(1.7, 0.5, 0.0), [(-6.1, 0.5, 0.6, 0.0, zc + 0.9), (-5.6, 0.9, 1.0, 0.0, zc + 1.1),
                                                     (-4.7, 0.6, 0.6, 0.0, zc + 1.12)], "glass")
    nodes = [Node("spine", spine), Node("cab", cab), Node("cab_glass", glass)]
    frame = [(-0.8, 0.0), (-0.51, 0.0), (-0.51, 0.82), (0.51, 0.82), (0.51, 0.0), (0.8, 0.0), (0.8, 1.1), (0.55, 1.3),
             (-0.55, 1.3), (-0.8, 1.1)]
    clamps = [F.extrude_xz([(x, z + zc - 0.4) for x, z in frame], y - 0.15, y + 0.15, "frame") for y in (-2.6, 2.2)]
    nodes.append(Node("clamps", F.merged(*clamps)))
    pods = []
    z0 = zc - 0.9
    for i in range(P["pods"]):
        sx = -1 if i % 2 == 0 else 1
        y = -1.4 + 2.4 * (i // 2)
        pods.append(F.loft_levels(F.chamfer_rect(1.3, 2.0, 0.0), [(z0, 1.0, 1.0, sx * 1.45, y), (z0 + 0.62, 1.0, 1.0, sx * 1.45, y),
                                                                  (z0 + 0.84, 1.0, 1.0, sx * 1.45, y), (z0 + 1.42, 1.0, 1.0, sx * 1.45, y),
                                                                  (z0 + 1.5, 0.92, 0.95, sx * 1.45, y)], "hull_alt",
                                  roles=["hull_alt", "band", "hull_alt", "trim"]))
    if pods:
        nodes.append(Node("pods", F.merged(*pods)))
    nac = []
    for sx in (-1, 1):
        x, z = sx * 0.95, zc + 0.3
        nac.append(F.lathe([(0.0, -0.4), (0.42, 0.0), (0.42, 0.8), (0.0, 0.95)], 6, "hull", smooth=True)
                   .rotate_x(-math.pi / 2).translate(x, 4.4, z))
    nodes += [Node("nacelles", F.merged(*nac)),
              Node("bells", F.merged(*[_nozzle(sx * 0.95, 5.3, zc + 0.3, 0.36, 0.55) for sx in (-1, 1)]))]
    legs = [F.loft_levels(F.chamfer_rect(0.3, 0.3, 0.0), [(0.0, 2.0, 2.0, sx * 1.9, y), (0.12, 1.4, 1.4, sx * 1.9, y),
                                                           (zc - 0.1, 0.8, 0.8, sx * 0.62, y)], "metal")
            for sx in (-1, 1) for y in (-3.4, 3.6)]
    nodes.append(Node("legs", F.merged(*legs)))
    return _asset(nodes, {"pods": P["pods"], "emitter": "hauler_engines"}, ao=0.25, reach=1.4)


# ------------------------------------------------------------------ rover
@register("ship.rover", V, "vehicle", {
    "wheels": S.enum("six", ["six", "four"], "six or four lathed wheels"),
    "mast": S.boolean(True, "sensor mast with a dish"),
}, "Planet rover (4.6 m): raised chamfered chassis with a slant-glass cab, cargo deck with a light bar, sensor mast "
   "and dish, six (or four) lathed wheels with hub caps.", origin="floor_center")
def rover(P, seed):
    wz = 0.46
    nodes = [Node("chassis", F.bevel_block(0.0, 0.2, 0.62, 2.0, 4.2, 0.5, "hull", bevel=0.1, chamfer=0.3,
                                           roles=["hull_alt", "hull", "hull"])),
             Node("cab", F.loft_y(F.chamfer_rect(1.8, 1.0, 0.3), [(-1.85, 0.7, 0.5, 0.0, 1.2), (-1.4, 1.0, 1.0, 0.0, 1.5),
                                                                 (0.2, 1.0, 1.0, 0.0, 1.55), (0.5, 0.9, 0.85, 0.0, 1.5)], "hull")),
             Node("glass", F.loft_y(F.chamfer_rect(1.5, 0.4, 0.0), [(-1.62, 0.6, 0.6, 0.0, 1.62), (-1.25, 1.0, 1.0, 0.0, 1.88),
                                                                   (-0.7, 0.7, 0.6, 0.0, 1.95)], "glass"))]
    ys = (-1.45, 0.25, 1.75) if P["wheels"] == "six" else (-1.3, 1.6)
    tyres, hubs = [], []
    for sx in (-1, 1):
        for y in ys:
            t = F.lathe([(0.0, -0.16), (wz, -0.16), (wz, 0.16), (0.0, 0.16)], 8, "rope", smooth=False, cap_roles=("trim", "trim"))
            tyres.append(t.rotate_y(math.pi / 2).translate(sx * 1.12, y, wz))
    nodes += [Node("wheels", F.merged(*tyres)),
              Node("lightbar", F.bevel_block(0.0, -1.95, 1.06, 1.4, 0.08, 0.1, "light", bevel=0.0)),
              Node("deck_rail", F.merged(*[F.tube([(sx * 0.85, 0.6, 1.12), (sx * 0.85, 0.7, 1.42), (sx * 0.85, 2.0, 1.42),
                                                   (sx * 0.85, 2.15, 1.12)], 0.04, 4, "rail", smooth=False) for sx in (-1, 1)]))]
    if P["mast"]:
        nodes.append(Node("mast", F.loft_levels(F.chamfer_rect(0.12, 0.12, 0.0), [(1.55, 1.0, 1.0, -0.55, 0.1),
                                                                                (2.6, 0.7, 0.7, -0.55, 0.1)], "metal")))
        dish = F.lathe([(0.0, 0.0), (0.4, 0.14), (0.34, 0.15), (0.0, 0.04)], 6, "body_alt", smooth=False)
        nodes.append(Node("dish", dish.rotate_x(0.9).translate(-0.55, 0.1, 2.62)))
    return _asset(nodes, {"wheels": P["wheels"]}, ao=0.28, reach=0.9)


# ------------------------------------------------------------------ escape pod
@register("ship.escape_pod", V, "vehicle", {
    "state": S.enum("closed", ["closed", "open"], "hatch shut or swung open"),
    "landed": S.boolean(True, "upright on its heat shield (off: tipped over on its side skirt)"),
}, "Escape pod (2.7 m): faceted octagonal cone capsule with a scorched heat-shield skirt, three fin legs, a round side "
   "hatch (open variant swings it aside over a dark opening) and a beacon light on top.", origin="floor_center")
def escape_pod(P, seed):
    prof = [(0.0, 0.0), (0.9, 0.0), (1.05, 0.22), (1.0, 0.5), (0.86, 1.5), (0.5, 2.3), (0.28, 2.5), (0.0, 2.55)]
    nodes = [Node("body", F.lathe(prof, 8, "hull", smooth=False, start=math.pi / 8,
                                  roles=["rock", "rock", "hull_alt", "hull", "hull", "hull", "trim"]))]
    fins = []
    for i in range(3):
        fin = F.loft_x([(-0.3, 0.0), (0.3, 0.0), (0.12, 0.9), (-0.12, 0.9)], [(0.7, 1.0, 1.0), (1.32, 0.6, 0.5)], "trim")
        fins.append(fin.rotate_z(math.tau * i / 3 + math.pi / 2))
    nodes.append(Node("fins", F.merged(*fins)))
    hatch = F.lathe([(0.0, 0.0), (0.42, 0.0), (0.38, 0.08), (0.0, 0.1)], 8, "door", smooth=False).rotate_x(math.pi / 2)
    ring = F.lathe_ring(0.42, 0.52, 0.0, 0.06, 8, "frame").rotate_x(math.pi / 2).translate(0.0, -0.9, 1.15)
    if P["state"] == "closed":
        hatch.translate(0.0, -0.91, 1.15)
    else:
        hatch.rotate_z(1.6).translate(-0.62, -1.08, 1.15)
        nodes.append(Node("hatch_dark", F.extrude_xz([(0.36 * math.cos(a), 1.15 + 0.36 * math.sin(a))
                                                     for a in [math.tau * i / 8 for i in range(8)]], -0.915, -0.905, "opening")))
    nodes += [Node("hatch", hatch), Node("hatch_ring", ring),
              Node("beacon", F.lathe([(0.0, 2.55), (0.12, 2.55), (0.1, 2.72), (0.0, 2.76)], 6, "light", smooth=False))]
    if not P["landed"]:
        for nd in nodes:
            nd.mesh.rotate_y(1.2)
    return _asset(nodes, {"state": P["state"], "emitter": "pod_beacon"}, ao=0.28, reach=0.8)


# ------------------------------------------------------------------ service drone
@register("ship.drone", V, "prop", {
    "cargo": S.boolean(False, "carries a small crate (resting on the floor) in two grip arms"),
}, "Service drone (0.9 m): lathed saucer body with a sensor eye, three thruster rings on short arms, resting on three "
   "small feet; cargo variant clutches a crate.", origin="floor_center")
def drone(P, seed):
    z0 = 0.5 if P["cargo"] else 0.16
    nodes = [Node("body", F.lathe([(0.0, 0.0), (0.34, 0.08), (0.2, 0.24), (0.0, 0.27)], 6, "hull", smooth=True)),
             Node("eye", F.bevel_block(0.0, -0.25, 0.07, 0.12, 0.06, 0.06, "light", bevel=0.0))]
    rings, arms = [], []
    for i in range(3):
        a = math.tau * i / 3 + math.pi / 2
        c, s = math.cos(a), math.sin(a)
        rings.append(F.lathe([(0.0, 0.04), (0.13, 0.06), (0.1, 0.13), (0.0, 0.12)], 4, "trim", smooth=False)
                     .translate(0.5 * c, 0.5 * s, 0.0))
        arms.append(F.tube([(0.28 * c, 0.28 * s, 0.1), (0.42 * c, 0.42 * s, 0.09)], 0.025, 3, "metal", smooth=False))
    nodes += [Node("rings", F.merged(*rings)), Node("arms", F.merged(*arms))]
    for nd in nodes:
        nd.mesh.translate(0.0, 0.0, z0)
    if P["cargo"]:
        nodes.append(Node("crate", F.bevel_block(0.0, 0.0, 0.0, 0.4, 0.4, 0.4, "body_alt", bevel=0.0)))
        nodes.append(Node("grips", F.merged(*[F.tube([(sx * 0.12, 0.0, z0 + 0.01), (sx * 0.23, 0.0, 0.36), (sx * 0.22, 0.0, 0.2)],
                                                    0.018, 3, "trim", smooth=False) for sx in (-1, 1)])))
    else:
        nodes.append(Node("feet", F.merged(*[F.tube([(0.16 * math.cos(a), 0.16 * math.sin(a), z0 + 0.02),
                                                     (0.22 * math.cos(a), 0.22 * math.sin(a), 0.0)], 0.02, 3, "trim", smooth=False)
                                             for a in [math.tau * i / 3 for i in range(3)]])))
    return _asset(nodes, {"cargo": P["cargo"]}, ao=0.25, reach=0.3)
