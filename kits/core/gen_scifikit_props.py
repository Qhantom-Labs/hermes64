"""SCIFIKIT tech props (tech.*): consoles, holo-table stand, cryo pods, crates, tanks, cable runs, vents, reactor
column, robot charging pod, lockers, info terminal, command seat.

Original designs in the N64-era look: tapered pedestals, slanted desks, chamfered plates, lathed capsules with
painted bands; screens and light strips are emissive painted textures (no real holograms: the holo-table carries a
small lathed globe on its emitter, a static prop the style gate reads like any other accent). Blender space: +Z up,
front faces -Y (glTF +Z, the operator side). Free props stand on the floor (origin floor_center); wall props (wall
vent, wall terminal, lockers) have their back on y = 0 so the room compiler mounts them on stn.room wall sockets."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from . import sfkit as F
from .asset import Asset, Node, register

V = "1.0.0"


def _asset(nodes, meta, ao=0.3, reach=0.7, ground=True):
    """Centre the footprint on the origin (floor_center rule), bake AO. Wall props record where their back face ends
    up (station_grid.back_m, Blender +Y metres from the origin) so the room compiler sets the back on the wall face."""
    nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
    lo = np.min([np.asarray(n.mesh.v).min(0) for n in nodes], axis=0)
    hi = np.max([np.asarray(n.mesh.v).max(0) for n in nodes], axis=0)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for n in nodes:
        n.mesh.translate(-cx, -cy, 0.0)
    F.bake_ao(nodes, amount=ao, reach=reach, ground=ground)
    meta = dict(meta)
    grid = dict(meta.get("station_grid") or {"anchor": "free"})
    if grid.get("anchor") == "wall_face":
        grid["back_m"] = round(float(hi[1] - cy), 4)  # type: ignore[assignment]
    meta["station_grid"] = grid
    meta["bbox_size_m"] = [round(float(x), 4) for x in (hi - lo)]
    return Asset(nodes, meta)


def slant_slab(x0, x1, y0, z0, y1, z1, t, role):
    """Thin slab lying on the plane through (y0, z0)-(y1, z1), thickness t along that plane's up normal, x0..x1."""
    d = np.array([y1 - y0, z1 - z0], dtype=float)
    d /= np.linalg.norm(d)
    n = np.array([-d[1], d[0]])
    poly = [(y0, z0), (y1, z1), (y1 + n[0] * t, z1 + n[1] * t), (y0 + n[0] * t, z0 + n[1] * t)]
    return yz_prism(poly, x0, x1, role)


def yz_prism(poly, x0, x1, role, role_cap=None):
    """Closed prism of a (y, z) profile extruded along x."""
    m = F.extrude_xz(poly, x0, x1, role, role_cap=role_cap)
    m.v = [(p[1], p[0], p[2]) for p in m.v]
    return m.orient_outward()


# ------------------------------------------------------------------ console
@register("tech.console", V, "furniture", {
    "width": S.num(1.6, 0.9, 2.4, "desk width"),
    "screens": S.integer(2, 1, 3, "screens on the slanted desk"),
    "style": S.enum("desk", ["desk", "tall", "pillar"], "desk: slanted operator desk; tall: desk + leaning back "
                    "display; pillar: narrow standing column with one tilted screen"),
}, "Operator console: chamfered plinth, tapered body set back from the toes, slanted desk with painted emissive "
   "screens and a light strip, side fins; tall adds a leaning back display. Operator side -Y.", origin="floor_center")
def console(P, seed):
    w, ns, style = P["width"], P["screens"], P["style"]
    if style == "pillar":
        w, ns = min(w, 0.9), 1
    nodes = [Node("plinth", F.bevel_block(0.0, 0.0, 0.0, w + 0.06, 0.72, 0.1, "wall_alt", bevel=0.03, chamfer=0.08)),
             Node("body", F.loft_levels(F.chamfer_rect(w - 0.08, 0.56, 0.1), [(0.1, 1.0, 1.0, 0.0, 0.02),
                                                                             (0.78, 0.94, 0.88, 0.0, 0.06)], "body"))]
    front_y, back_y, z_front, z_back = -0.42, 0.34, 0.84, 1.04
    nodes.append(Node("desk", yz_prism([(front_y, 0.76), (back_y, 0.76), (back_y, z_back), (front_y, z_front)],
                                       -w / 2, w / 2, "body_alt", role_cap="trim")))
    sw = (w - 0.16 - 0.06 * (ns - 1)) / ns
    scr = []
    for i in range(ns):
        x0 = -w / 2 + 0.08 + i * (sw + 0.06)
        scr.append(slant_slab(x0, x0 + sw, front_y + 0.12, z_front + 0.032, back_y - 0.08, z_back - 0.017, 0.012, "screen"))
    nodes.append(Node("screens", F.merged(*scr)))
    nodes.append(Node("strip", slant_slab(-w / 2 + 0.06, w / 2 - 0.06, front_y + 0.015, z_front + 0.004, front_y + 0.07,
                                          z_front + 0.018, 0.01, "light")))
    fins = [yz_prism([(-0.36, 0.1), (0.3, 0.1), (0.38, 1.06), (0.2, 1.1), (-0.44, 0.86)], sx * (w / 2 + 0.01) - 0.03,
                     sx * (w / 2 + 0.01) + 0.03, "trim") for sx in (-1, 1)]
    nodes.append(Node("fins", F.merged(*fins)))
    if style == "tall":
        nodes.append(Node("back", yz_prism([(0.3, 1.04), (0.46, 1.04), (0.56, 1.72), (0.42, 1.74)], -w / 2 + 0.04,
                                           w / 2 - 0.04, "body", role_cap="trim")))
        nodes.append(Node("back_screen", slant_slab(-w / 2 + 0.12, w / 2 - 0.12, 0.293, 1.12, 0.4, 1.66, 0.012, "screen")))
    return _asset(nodes, {"style": style, "screens": ns, "emitter": "console_glow"})


# ------------------------------------------------------------------ holo table
@register("tech.holo_table", V, "furniture", {
    "radius": S.num(1.0, 0.7, 1.3, "table radius"),
    "globe": S.boolean(True, "small lathed planet globe hovering over the emitter (static prop)"),
}, "Holo-table stand: hexagonal lathe with a wide foot, tapered neck and flared top, a light rim and an emitter disc; "
   "an optional small globe hovers over the emitter (a static prop, no hologram shader).", origin="floor_center")
def holo_table(P, seed):
    r = P["radius"]
    st = math.pi / 6
    prof = [(0.0, 0.0), (r * 0.9, 0.0), (r * 0.94, 0.07), (r * 0.6, 0.16), (r * 0.36, 0.62), (r * 0.9, 0.8),
            (r, 0.88), (r * 0.96, 0.94), (0.0, 0.94)]
    nodes = [Node("stand", F.lathe(prof, 6, "body_alt", smooth=False, start=st,
                                   roles=["wall_alt", "wall_alt", "body_alt", "body_alt", "body", "trim", "trim", "body"])),
             Node("rim", F.lathe_ring(r * 0.78, r * 0.9, 0.941, 0.955, 6, "light", start=st)),
             Node("emitter", F.lathe([(0.0, 0.94), (0.26, 0.94), (0.2, 0.99), (0.0, 1.0)], 6, "light", smooth=False, start=st))]
    if P["globe"]:
        nodes += [Node("globe", K.sphere(0.0, 0.0, 1.42, 0.26, 0.26, 0.26, 7, 4, "orb", True)),
                  Node("globe_ring", F.lathe_ring(0.36, 0.42, 1.415, 1.425, 8, "light"))]
    return _asset(nodes, {"emitter": "holo_glow"})


# ------------------------------------------------------------------ cryo pod
@register("tech.cryo_pod", V, "furniture_large", {
    "state": S.enum("closed", ["closed", "open"], "closed: glass window shut; open: window door swung aside"),
    "lean": S.num(0.0, 0.0, 0.25, "backward lean of the capsule (radians)"),
}, "Standing cryo pod: hexagonal plinth with a light band, elliptic lathed capsule, oval glass window on the front, "
   "two hoses from the domed cap into the back. open swings the window door aside.", origin="floor_center")
def cryo_pod(P, seed):
    st = math.pi / 6
    nodes = [Node("plinth", F.lathe([(0.0, 0.0), (0.66, 0.0), (0.66, 0.16), (0.56, 0.24), (0.0, 0.24)], 6, "wall_alt",
                                    smooth=False, start=st)),
             Node("band", F.lathe_ring(0.6, 0.665, 0.07, 0.12, 6, "light", start=st))]
    prof = [(0.0, 0.24), (0.4, 0.24), (0.46, 0.4), (0.47, 1.6), (0.42, 1.86), (0.28, 2.04), (0.0, 2.1)]
    shell = F.lathe(prof, 10, "body", smooth=True, ry=0.82, roles=["trim", "body", "body", "body", "body", "trim"])
    ang = [math.tau * i / 10 for i in range(10)]
    win_poly = [(0.26 * math.cos(a), 1.12 + 0.6 * math.sin(a)) for a in ang]
    if P["state"] == "closed":
        win = F.extrude_xz(win_poly, -0.44, -0.35, "glass")
    else:
        win = F.extrude_xz(win_poly, -0.06, -0.01, "glass")
        win.rotate_z(-1.9).translate(-0.27, -0.42, 0.0)
    frame_out = [(0.31 * math.cos(a), 1.12 + 0.66 * math.sin(a)) for a in ang]
    frame = F.frame_ring(frame_out, [(0.265 * math.cos(a), 1.12 + 0.606 * math.sin(a)) for a in ang], -0.43, -0.34, "frame")
    hoses = [F.tube([(sx * 0.16, 0.1, 2.02), (sx * 0.2, 0.36, 2.0), (sx * 0.22, 0.52, 1.7), (sx * 0.22, 0.56, 0.3)], 0.045, 6,
                    "rope", smooth=True) for sx in (-1, 1)]
    parts = [Node("shell", shell), Node("window", win), Node("frame", frame), Node("hoses", F.merged(*hoses))]
    if P["lean"] > 0:
        for nd in parts:
            nd.mesh.translate(0.0, 0.0, -0.24).rotate_x(-P["lean"]).translate(0.0, 0.0, 0.24)
    return _asset(nodes + parts, {"state": P["state"], "emitter": "pod_band"})


# ------------------------------------------------------------------ crate
CRATES = {"small": (0.8, 0.8, 0.8), "large": (1.4, 1.0, 1.0), "long": (2.0, 0.8, 0.7)}


@register("tech.crate", V, "furniture_large", {
    "size": S.enum("small", list(CRATES) + ["stack"], "small 0.8 m cube, large, long, or stack (large + small on top)"),
    "band": S.boolean(True, "hazard band around the middle"),
}, "Cargo crate: chamfered bevelled box with corner bumpers and an optional hazard band; stack piles a small crate on "
   "a large one (2 mm gap, no interpenetration).", origin="floor_center")
def crate(P, seed):
    def one(w, d, h, z0, tag, yaw=0.0, band=True):
        out = [Node("box" + tag, F.bevel_block(0.0, 0.0, z0, w, d, h, "body_alt", bevel=0.05, chamfer=0.07))]
        caps = [F.loft_levels(F.chamfer_rect(0.16, 0.16, 0.035), [(z0 + 0.002, 1.0, 1.0, sx * (w / 2 - 0.05), sy * (d / 2 - 0.05)),
                                                                 (z0 + h - 0.002, 1.0, 1.0, sx * (w / 2 - 0.05), sy * (d / 2 - 0.05))],
                              "frame") for sx in (-1, 1) for sy in (-1, 1)]
        out.append(Node("corners" + tag, F.merged(*caps)))
        if P["band"] and band:
            bo, bi = F.chamfer_rect(w + 0.02, d + 0.02, 0.07), F.chamfer_rect(w - 0.04, d - 0.04, 0.06)
            out.append(Node("band" + tag, K.prism(bo, z0 + h * 0.42, z0 + h * 0.58, "band", holes=[bi])))
        if yaw:
            for nd in out:
                nd.mesh.rotate_z(yaw)
        return out
    if P["size"] == "stack":
        nodes = one(1.4, 1.0, 1.0, 0.0, "") + one(0.8, 0.8, 0.8, 1.002, "_top", yaw=0.35, band=False)
    else:
        nodes = one(*CRATES[P["size"]], 0.0, "")
    return _asset(nodes, {"size": P["size"]})


# ------------------------------------------------------------------ tank
@register("tech.tank", V, "furniture_large", {
    "orient": S.enum("upright", ["upright", "horizontal"], "standing column tank or a horizontal tank on saddles"),
    "radius": S.num(0.6, 0.35, 0.9), "length": S.num(2.2, 1.2, 3.2),
}, "Pressure tank: lathed capsule with domed ends and two painted bands, a valve wheel, standing on a hex foot ring "
   "(upright) or two tapered saddles (horizontal).", origin="floor_center")
def tank(P, seed):
    r, L = P["radius"], P["length"]
    k = 8
    prof = [(0.0, 0.0), (r * 0.55, 0.0), (r * 0.9, r * 0.18), (r, r * 0.5), (r, L - r * 0.5), (r * 0.9, L - r * 0.18),
            (r * 0.55, L), (0.0, L)]
    parts = [Node("body", F.lathe(prof, k, "metal", smooth=True)),
             Node("bands", F.merged(*[F.lathe_ring(r - 0.01, r + 0.03, z, z + 0.1, k, "band") for z in (L * 0.28, L * 0.66)])),
             Node("wheel", K.torus(0.16, 0.025, 8, 4, "trim", smooth=True).translate(0.0, 0.0, L + 0.12)),
             Node("stem", F.lathe([(0.0, L - 0.02), (0.05, L - 0.02), (0.05, L + 0.12), (0.0, L + 0.12)], 6, "trim", smooth=False))]
    if P["orient"] == "upright":
        for nd in parts:
            nd.mesh.translate(0.0, 0.0, 0.18)
        parts.append(Node("foot", F.lathe_ring(r * 0.45, r * 0.95, 0.0, 0.2, 6, "wall_alt")))
    else:
        for nd in parts:
            nd.mesh.translate(0.0, 0.0, -L / 2).rotate_y(math.pi / 2).translate(0.0, 0.0, r + 0.28)
        sad = [yz_prism([(-r * 0.8, 0.0), (r * 0.8, 0.0), (r * 0.62, 0.42), (-r * 0.62, 0.42)], x - 0.1, x + 0.1, "wall_alt")
               for x in (-L * 0.3, L * 0.3)]
        parts.append(Node("saddles", F.merged(*sad)))
    return _asset(parts, {"orient": P["orient"]})


# ------------------------------------------------------------------ cables
@register("tech.cables", V, "structure", {
    "length": S.num(4.0, 2.0, 8.0, "run length along x"),
    "count": S.integer(3, 2, 4, "cables in the bundle"),
    "mode": S.enum("floor", ["floor", "hang"], "floor: lying run between two junction boxes; hang: sagging run "
                   "between two bracket posts at 3 m"),
}, "Cable run: a bundle of tube cables (wavy on the floor or sagging between bracket posts) ending in chamfered "
   "junction boxes; cables never interpenetrate (laterally offset).", origin="floor_center")
def cables(P, seed):
    L, n, mode = P["length"], P["count"], P["mode"]
    rs = np.random.default_rng(seed + 7)
    hz = 3.0 if mode == "hang" else 0.0
    nodes = []
    for i in range(n):
        off = (i - (n - 1) / 2) * 0.11
        ph = rs.random() * math.tau
        pts = []
        k = 9
        for j in range(k + 1):
            t = j / k
            x = -L / 2 + 0.3 + (L - 0.6) * t
            if mode == "floor":
                pts.append((x, off + 0.05 * math.sin(t * math.tau * 1.5 + ph), 0.05 + 0.012 * i))
            else:
                pts.append((x, off, hz - 0.08 - (0.45 + 0.08 * i) * math.sin(math.pi * t)))
        if mode == "floor":
            pts = [(-L / 2 + 0.22, off, 0.25)] + pts + [(L / 2 - 0.22, off, 0.25)]
        nodes.append(Node("cable_%d" % i, F.tube(pts, 0.035 + 0.006 * (i % 2), 5, "rope", smooth=True)))
    if mode == "floor":
        boxes = [F.bevel_block(sx * (L / 2 - 0.15), 0.0, 0.0, 0.3, 0.5, 0.45, "body_alt", bevel=0.04, chamfer=0.05) for sx in (-1, 1)]
    else:
        boxes = [F.bevel_block(sx * (L / 2 - 0.15), 0.0, hz - 0.3, 0.3, 0.42, 0.42, "body_alt", bevel=0.04, chamfer=0.05)
                 for sx in (-1, 1)]
        nodes.append(Node("posts", F.merged(*[F.loft_levels(F.chamfer_rect(0.16, 0.16, 0.04),
                                                            [(0.0, 1.2, 1.2, sx * (L / 2 - 0.15), 0.0),
                                                             (hz - 0.302, 1.0, 1.0, sx * (L / 2 - 0.15), 0.0)], "post")
                                              for sx in (-1, 1)])))
    nodes.append(Node("boxes", F.merged(*boxes)))
    return _asset(nodes, {"mode": mode, "length_m": L}, ao=0.25, reach=0.5)


# ------------------------------------------------------------------ vent
@register("tech.vent", V, "prop", {
    "kind": S.enum("wall", ["wall", "floor"], "wall: kick-level wall vent (back on y = 0); floor: deck grate"),
    "fan": S.boolean(True, "fan hub and blades behind the grille"),
}, "Vent: chamfered frame, recessed grille plate and a three-blade fan hub behind it. wall stands on the floor "
   "against a wall (back on y = 0); floor lies in the deck.", origin="floor_center")
def vent(P, seed):
    w, h = 0.9, 0.56
    outer, inner = F.chamfer_rect(w, h, 0.1), F.chamfer_rect(w - 0.16, h - 0.16, 0.0)
    parts = [Node("frame", K.prism(outer, 0.0, 0.08, "frame", holes=[inner])),
             Node("grille", K.prism(inner, 0.02, 0.045, "step"))]
    if P["fan"]:
        hub = F.lathe([(0.0, 0.004), (0.08, 0.012), (0.0, 0.02)], 6, "metal", smooth=False)
        blades = [K.prism([(0.06, -0.03), (0.2, -0.05), (0.2, 0.05), (0.06, 0.03)], 0.003, 0.011, "metal").rotate_z(math.tau * i / 3)
                  for i in range(3)]
        parts += [Node("hub", hub), Node("blades", F.merged(*blades))]
    if P["kind"] == "wall":
        for nd in parts:
            # stand the vent in the x-z plane: plate normal -> -Y, back on y = 0, bottom 6 cm above the floor
            nd.mesh.rotate_x(math.pi / 2).translate(0.0, 0.0, h / 2)
    meta = {"kind": P["kind"]}
    if P["kind"] == "wall":
        meta["station_grid"] = {"anchor": "wall_face"}
    return _asset(parts, meta, ao=0.25, reach=0.3)


# ------------------------------------------------------------------ reactor
@register("tech.reactor", V, "structure", {
    "height": S.num(3.6, 2.6, 3.9, "column height (fits under a 4 m ceiling)"),
    "ribs": S.integer(4, 3, 6, "cage ribs"),
}, "Reactor column: stepped round plinth with a hazard ring, a glowing core cylinder inside tapered cage ribs, coil "
   "rings and a domed top cap.", origin="floor_center")
def reactor(P, seed):
    H, nr = P["height"], P["ribs"]
    k = 10
    nodes = [Node("plinth", F.lathe([(0.0, 0.0), (1.5, 0.0), (1.5, 0.16), (1.3, 0.2), (1.1, 0.2), (1.05, 0.4), (0.0, 0.4)], k,
                                    "wall_alt", smooth=False)),
             Node("hazard", F.lathe_ring(1.12, 1.42, 0.201, 0.215, k, "band")),
             Node("core", F.lathe([(0.0, 0.4), (0.42, 0.4), (0.42, H - 0.5), (0.0, H - 0.5)], 10, "light", smooth=True))]
    ribs = []
    for i in range(nr):
        a = math.tau * i / nr
        c, s = math.cos(a), math.sin(a)
        path = [(0.95 * c, 0.95 * s, 0.4), (0.72 * c, 0.72 * s, H * 0.5), (0.8 * c, 0.8 * s, H - 0.55)]
        ribs.append(F.sweep(path, [(-0.06, -0.07), (0.06, -0.07), (0.04, 0.07), (-0.04, 0.07)], "trim", smooth=False))
    nodes.append(Node("cage", F.merged(*ribs)))
    nodes.append(Node("coils", F.lathe_ring(0.5, 0.62, H * 0.5, H * 0.5 + 0.16, k, "metal")))
    nodes.append(Node("cap", F.lathe([(0.0, H - 0.55), (1.0, H - 0.55), (1.0, H - 0.4), (0.7, H - 0.12), (0.3, H), (0.0, H)],
                                     k, "body_alt", smooth=False, roles=["trim", "body_alt", "body_alt", "body_alt", "body_alt"])))
    return _asset(nodes, {"emitter": "reactor_core"}, ao=0.3, reach=0.8)


# ------------------------------------------------------------------ robot charging pod
@register("tech.charge_pod", V, "furniture_large", {
    "robot": S.boolean(True, "a dormant service robot docked on the pad"),
}, "Robot charging pod: curved alcove wall with a canopy and light strips, a round contact pad with a glowing ring, "
   "and (optional) a dormant service robot of original design (dome head, visor, stubby arm pods) docked on it. "
   "Alcove opens to -Y.", origin="floor_center")
def charge_pod(P, seed):
    a0, a1 = math.radians(20), math.radians(160)
    nodes = [Node("alcove", F.arc_wall(0.82, 0.94, 0.0, 2.1, a0, a1, 4, "body", roles=["body", "body_alt", "trim", "body"])),
             Node("canopy", F.arc_wall(0.14, 1.06, 2.1, 2.24, a0 - 0.05, a1 + 0.05, 4, "body_alt")),
             Node("strips", F.arc_wall(0.8, 0.818, 1.5, 1.56, a0 + 0.12, a1 - 0.12, 4, "light")),
             Node("pad", F.lathe([(0.0, 0.0), (0.66, 0.0), (0.62, 0.08), (0.0, 0.08)], 8, "wall_alt", smooth=False)),
             Node("pad_ring", F.lathe_ring(0.42, 0.54, 0.081, 0.092, 8, "light"))]
    if P["robot"]:
        nodes += [Node("bot_body", F.lathe([(0.0, 0.093), (0.2, 0.093), (0.28, 0.3), (0.3, 0.62), (0.24, 0.8), (0.0, 0.82)], 8,
                                           "hull", smooth=True, roles=["trim", "hull", "hull", "hull", "hull"])),
                  Node("bot_head", K.sphere(0.0, 0.0, 0.99, 0.2, 0.2, 0.16, 7, 4, "hull_alt", True)),
                  Node("bot_visor", F.extrude_xz([(-0.12, 0.95), (0.12, 0.95), (0.1, 1.02), (-0.1, 1.02)], -0.215, -0.15, "screen")),
                  Node("bot_arms", F.merged(*[K.sphere(sx * 0.36, 0.0, 0.55, 0.08, 0.1, 0.16, 5, 3, "body_alt", True)
                                              for sx in (-1, 1)]))]
    for nd in nodes:
        nd.mesh.translate(0.0, -0.3, 0.0)   # the alcove arc bulges to +Y; shift so the footprint centres on the origin
    return _asset(nodes, {"robot": P["robot"], "emitter": "pod_ring"})


# ------------------------------------------------------------------ lockers
@register("tech.locker", V, "furniture", {
    "doors": S.integer(3, 1, 4, "lockers in the bank"),
}, "Locker bank against a wall (back on y = 0 before centring): chamfered carcass with a sloped top, raised doors with "
   "vent slots and grip bars, a label strip per door.", origin="floor_center")
def locker(P, seed):
    n = P["doors"]
    dw = 0.52
    w, d, h = n * dw + 0.08, 0.5, 1.95
    nodes = [Node("carcass", yz_prism([(-d, 0.0), (0.0, 0.0), (0.0, h), (-d + 0.12, h), (-d, h - 0.12)], -w / 2, w / 2,
                                      "body_alt", role_cap="body_alt"))]
    doors, grips, slots, labels = [], [], [], []
    for i in range(n):
        x = -w / 2 + 0.04 + dw * (i + 0.5)
        doors.append(F.bevel_block(x, -d - 0.012, 0.08, dw - 0.05, 0.026, h - 0.3, "door", bevel=0.01))
        slots.append(F.bevel_block(x, -d - 0.03, h - 0.52, dw - 0.18, 0.01, 0.16, "step", bevel=0.003))
        gx = x + dw / 2 - 0.1
        grips.append(F.tube([(gx, -d - 0.024, 0.85), (gx, -d - 0.07, 0.9), (gx, -d - 0.07, 1.2), (gx, -d - 0.024, 1.25)],
                            0.015, 4, "trim", smooth=False))
        labels.append(F.bevel_block(x, -d - 0.03, h - 0.27, 0.2, 0.008, 0.05, "screen", bevel=0.002))
    nodes += [Node("doors", F.merged(*doors)), Node("slots", F.merged(*slots)), Node("grips", F.merged(*grips)),
              Node("labels", F.merged(*labels))]
    return _asset(nodes, {"doors": n, "station_grid": {"anchor": "wall_face", "back_y_m": 0.0}}, ao=0.3, reach=0.6)


# ------------------------------------------------------------------ info terminal
@register("tech.terminal", V, "furniture", {
    "kind": S.enum("stand", ["stand", "wall"], "stand: free-standing info pillar; wall: wall-hung panel on a wall "
                   "socket (back on y = 0)"),
}, "Info terminal: a tapered pillar (stand) or a wall panel with a tilted emissive screen, a keypad ledge and a status "
   "light.", origin="floor_center")
def terminal(P, seed):
    if P["kind"] == "stand":
        nodes = [Node("pillar", F.loft_levels(F.chamfer_rect(0.34, 0.26, 0.07), [(0.0, 1.3, 1.4), (0.08, 1.15, 1.2),
                                                                                (1.05, 0.8, 0.85), (1.1, 1.1, 1.2)],
                                              "body", roles=["wall_alt", "body", "trim"])),
                 Node("head", yz_prism([(-0.2, 1.1), (0.16, 1.1), (0.16, 1.44), (-0.14, 1.52)], -0.25, 0.25, "body_alt",
                                       role_cap="trim")),
                 Node("screen", slant_slab(-0.2, 0.2, -0.205, 1.18, -0.153, 1.48, 0.01, "screen")),
                 Node("lamp", F.bevel_block(0.0, 0.0, 1.49, 0.12, 0.1, 0.03, "light", bevel=0.008))]
    else:
        nodes = [Node("panel", yz_prism([(-0.16, 0.0), (0.0, 0.0), (0.0, 1.7), (-0.08, 1.72), (-0.16, 1.64)], -0.3, 0.3,
                                        "body_alt", role_cap="trim")),
                 Node("screen", slant_slab(-0.24, 0.24, -0.172, 1.08, -0.092, 1.6, 0.01, "screen")),
                 Node("ledge", yz_prism([(-0.3, 0.92), (-0.155, 0.92), (-0.155, 1.0), (-0.26, 1.0)], -0.26, 0.26, "trim"))]
    meta = {"kind": P["kind"]}
    if P["kind"] == "wall":
        meta["station_grid"] = {"anchor": "wall_face"}
    return _asset(nodes, meta, ao=0.25, reach=0.4)


# ------------------------------------------------------------------ command seat
@register("tech.seat", V, "furniture", {
    "arms": S.boolean(True, "armrests with small panels"),
    "tilt": S.num(0.18, 0.0, 0.35, "backrest tilt (radians)"),
}, "Command seat: tapered hex swivel base, upholstered seat and tilted backrest with a headrest wing, armrests with "
   "small emissive panels. Faces -Y.", origin="floor_center")
def seat(P, seed):
    nodes = [Node("base", F.lathe([(0.0, 0.0), (0.4, 0.0), (0.36, 0.06), (0.1, 0.12), (0.08, 0.42), (0.0, 0.42)], 6,
                                  "metal", smooth=False, start=math.pi / 6)),
             Node("seat", F.bevel_block(0.0, 0.0, 0.42, 0.62, 0.6, 0.14, "cushion", bevel=0.05, chamfer=0.08))]
    back = F.bevel_block(0.0, 0.0, 0.0, 0.58, 0.14, 0.78, "cushion", bevel=0.05, chamfer=0.06)
    head = F.loft_levels(F.chamfer_rect(0.5, 0.12, 0.04), [(0.8, 1.0, 1.0), (1.0, 0.8, 1.0)], "body_alt")
    for m in (back, head):
        m.rotate_x(-P["tilt"]).translate(0.0, 0.3, 0.56)
    nodes += [Node("back", back), Node("headrest", head)]
    if P["arms"]:
        nodes += [Node("arms", F.merged(*[F.bevel_block(sx * 0.37, -0.02, 0.62, 0.1, 0.5, 0.08, "body_alt", bevel=0.03)
                                          for sx in (-1, 1)])),
                  Node("arm_posts", F.merged(*[F.loft_levels(F.chamfer_rect(0.06, 0.08, 0.0),
                                                             [(0.5, 1.0, 1.0, sx * 0.37, 0.12), (0.62, 1.0, 1.0, sx * 0.37, 0.12)],
                                                             "trim") for sx in (-1, 1)])),
                  Node("arm_pads", F.merged(*[F.bevel_block(sx * 0.37, -0.16, 0.7, 0.07, 0.16, 0.012, "screen", bevel=0.003)
                                              for sx in (-1, 1)]))]
    return _asset(nodes, {}, ao=0.3, reach=0.5)
