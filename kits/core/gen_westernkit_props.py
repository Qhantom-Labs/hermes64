"""WESTERNKIT props family (wprop.*), theme-agnostic: barrels, crates, cacti, wagons, saloon furniture and fittings,
wanted boards with blank posters, windmill, well, tombstones, lanterns and the small dressing that fills a frontier
street (sacks, hay, wheels, troughs, signposts, buckets, bottles, skulls).

Free props: origin on the floor centre, closed solids, tapered and bevelled forms (staves, bulges, chamfers), painted
roles; blank sign / poster faces are cards (kit_card_*). Lamps carry bake_lights (night packs bake warm pools).
"""
import math

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from . import gen_westernkit_base as B
from .gen_westernkit_town import Parts, batwing_outline
from .genutil import finalize
from .rng import rng

V = "1.0.0"


def free(pt, **kw):
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], **kw))


def barrel_mesh(h, r, bulge=0.12, sides=8, role="body_alt", hoop_role="metal", z0=0.0, lid="wood"):
    """Stave barrel: bulged lathe (staves painted by the role texture) with two iron hoop bands as profile steps."""
    rb = r * (1 + bulge)
    prof = [(r, z0), (r * 1.02, z0 + h * 0.12), (rb * 0.97, z0 + h * 0.3), (rb, z0 + h * 0.5), (rb * 0.97, z0 + h * 0.7),
            (r * 1.02, z0 + h * 0.88), (r, z0 + h)]
    roles = [hoop_role, role, role, role, role, hoop_role]
    return K.lathe(prof, sides, role, smooth=True, roles=roles, cap_roles=(lid, lid), start=math.pi / sides)


# ---------------------------------------------------------------- containers
@register("wprop.barrel", V, "prop", {
    "kind": S.enum("barrel", ["barrel", "keg", "water", "powder", "tipped"]),
}, "Barrel: a bulged stave barrel with iron hoops; keg (squat), water barrel (lid and dipper), powder keg (painted "
   "band) or tipped on its side.", origin="floor_center")
def barrel(P, seed):
    k = P["kind"]
    pt = Parts()
    if k == "keg":
        pt.add("barrel", barrel_mesh(0.62, 0.27, 0.14))
    elif k == "powder":
        pt.add("barrel", barrel_mesh(0.7, 0.24, 0.1, role="band"))
    else:
        pt.add("barrel", barrel_mesh(0.95, 0.3, 0.12))
    if k == "water":
        pt.add("lid", K.lathe([(0.31, 0.95), (0.31, 0.99)], 8, "wood", smooth=False, start=math.pi / 8))
        pt.add("dipper", B.beam((0.05, 0.0, 1.0), (0.32, 0.05, 1.18), 0.04, 0.04, "wood", roll=45.0))
    nodes = pt.nodes()
    if k == "tipped":
        for n in nodes:
            n.mesh.rotate_y(math.pi / 2)
    return free(pt) if k != "tipped" else finalize(nodes, B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wprop.crate", V, "prop", {
    "kind": S.enum("crate", ["crate", "slats", "long", "powder"]),
    "size": S.num(0.7, 0.4, 1.0),
}, "Crate: a chamfered box with board edges (crate), an open slatted crate, a long box (rifle / tool box) or a "
   "stencilled powder box with rope handles.", origin="floor_center")
def crate(P, seed):
    s = P["size"]
    k = P["kind"]
    pt = Parts()
    w, d, h = (s, s, s * 0.85) if k != "long" else (s * 1.9, s * 0.55, s * 0.45)
    if k == "slats":
        for z in (0.06, h * 0.5, h - 0.06):
            for sy in (-1, 1):
                pt.add("slats", B.beam((-w / 2 + 0.06, sy * (d / 2 - 0.03), z), (w / 2 - 0.06, sy * (d / 2 - 0.03), z), 0.05, 0.1, "body_alt"))
        for sx in (-1, 1):
            for sy in (-1, 1):
                pt.add("corners", B.beam((sx * (w / 2 - 0.04), sy * (d / 2 - 0.04), 0.0), (sx * (w / 2 - 0.04), sy * (d / 2 - 0.04), h),
                                         0.07, 0.07, "wood", up=(1.0, 0.0, 0.0), roll=45.0))
        pt.add("floor", B.board(-w / 2 + 0.08, w / 2 - 0.08, -d / 2 + 0.08, d / 2 - 0.08, 0.0, 0.04, "wood"))
    else:
        pt.add("box", B.chamfer(0.0, 0.0, 0.0, h, w, d, min(w, d) * 0.06, "body_alt" if k != "powder" else "band", top="wood"))
        for z in (0.04, h - 0.04):
            pt.add("edges", K.prism(K.rounded_rect2d(w + 0.03, d + 0.03, 0.03, 1), z - 0.04, z + 0.035, "wood"))
        if k == "powder":
            for sx in (-1, 1):
                pt.add("handles", K.torus(0.06, 0.012, 4, 3, "rope", smooth=False).rotate_y(math.pi / 2).translate(sx * (w / 2 + 0.03), 0.0, h * 0.7))
    return free(pt)


@register("wprop.sacks", V, "prop", {
    "count": S.integer(3, 1, 3),
}, "Grain / flour sacks: soft tied bags slumped against each other.", origin="floor_center")
def sacks(P, seed):
    r = rng(seed, "wprop.sacks")
    pt = Parts()
    for i in range(P["count"]):
        a = 2 * math.pi * i / max(1, P["count"]) + r.uniform(-0.3, 0.3)
        d = 0.0 if P["count"] == 1 else 0.24
        x, y = d * math.cos(a), d * math.sin(a)
        pt.add("sacks", K.lathe([(0.2, 0.0), (0.25, 0.16), (0.22, 0.4), (0.08, 0.58), (0.0, 0.68)], 6, "fabric",
                                smooth=True, cap_roles=("fabric", "fabric")).rotate_z(r.uniform(0, 3)).translate(x, y, 0.0))
    return free(pt)


@register("wprop.hay", V, "furniture", {
    "kind": S.enum("bale", ["bale", "stack"]),
}, "Hay: a bound rectangular bale (rounded, twine bands) or a small stack of three bales.", origin="floor_center")
def hay(P, seed):
    pt = Parts()
    bales = [(0.0, 0.0, 0.0, 0.0)] if P["kind"] == "bale" else [(-0.32, 0.0, 0.0, 0.05), (0.32, 0.0, 0.0, -0.04), (0.0, 0.0, 0.42, 0.3)]
    for x, y, z, rot in bales:
        b = K.rounded_box(0.0, 0.0, 0.21, 0.62, 0.42, 0.42, "grass", bevel=0.25, smooth=True, k_corner=1)
        pt.add("bales", b.rotate_z(rot).translate(x, y, z))
    return free(pt)


# ---------------------------------------------------------------- plants (cacti)
def arm(base, out, up, r, role="cap"):
    """Cactus arm: a swept tube out from the trunk and turning up (elbow), closed with a rounded tip."""
    bx, by, bz = base
    ox, oy = out
    path = [(bx, by, bz), (bx + ox * 0.45, by + oy * 0.45, bz + 0.05), (bx + ox * 0.62, by + oy * 0.62, bz + 0.3), (bx + ox * 0.66, by + oy * 0.66, bz + up)]
    sec = [(r * math.cos(2 * math.pi * k / 6), r * math.sin(2 * math.pi * k / 6)) for k in range(6)]
    m = B.sweep(path, sec, role, cap=True)
    tip = K.lathe([(r, 0.0), (r * 0.6, r * 0.6), (0.0, r * 0.9)], 6, role, smooth=True).translate(path[-1][0], path[-1][1], path[-1][2])
    return m, tip


@register("wprop.cactus", V, "flora", {
    "kind": S.enum("saguaro", ["saguaro", "organ", "prickly", "barrel"]),
    "height": S.num(3.2, 0.4, 5.0),
}, "Desert cactus: a ribbed columnar saguaro with upturned arms, an organ-pipe clump of stems, a prickly pear of "
   "flat pads with red fruit, or a squat barrel cactus with a flower crown.", origin="floor_center")
def cactus(P, seed):
    r = rng(seed, "wprop.cactus", P["kind"])
    k = P["kind"]
    h = P["height"]
    pt = Parts()
    if k == "saguaro":
        rt = 0.26 * h / 3.2
        pt.add("trunk", K.lathe([(rt * 0.9, 0.0), (rt, h * 0.3), (rt * 0.96, h * 0.85), (rt * 0.6, h * 0.97), (0.0, h)], 8, "cap", smooth=True,
                                start=math.pi / 8))
        for side, zf, up in ((1, 0.45, 0.32), (-1, 0.58, 0.24)):
            m, tip = arm((0.0, 0.0, h * zf), (side * 1.0 * h / 3.2, 0.12 * side), h * up, rt * 0.62)
            pt.add("arms", m)
            pt.add("tips", tip)
    elif k == "organ":
        for i in range(5):
            a = 2 * math.pi * i / 5 + r.uniform(-0.2, 0.2)
            d = 0.22 if i else 0.0
            hh = h * r.uniform(0.6, 1.0) * (1.0 if i else 1.05)
            rr = 0.11 * h / 2.4
            stem = K.lathe([(rr, 0.0), (rr * 1.05, hh * 0.5), (rr * 0.8, hh * 0.95), (0.0, hh)], 6, "cap", smooth=True)
            pt.add("stems", stem.rotate_y(0.12 * (1 if i % 2 else -1) if i else 0.0).translate(d * math.cos(a), d * math.sin(a), 0.0))
    elif k == "prickly":
        pads = [((0.0, 0.0, 0.0), 0.0, 0.32), ((0.12, 0.0, 0.5), 0.5, 0.26), ((-0.15, 0.03, 0.48), -0.6, 0.25), ((0.32, -0.02, 0.88), 0.8, 0.2),
                ((-0.05, 0.05, 0.9), -0.15, 0.22)]
        for (x, y, z), tilt, s in pads:
            pad = K.sphere(0.0, 0.0, s, s * 0.85, s * 0.18, s, 7, 4, "cap", smooth=True)
            pt.add("pads", pad.rotate_y(tilt).rotate_z(r.uniform(-0.6, 0.6)).translate(x * h / 1.2, y, z * h / 1.2))
        for i in range(4):
            pt.add("fruit", K.sphere(r.uniform(-0.3, 0.4) * h / 1.2, r.uniform(-0.1, 0.1), (0.9 + r.uniform(0, 0.4)) * h / 1.2, 0.05, 0.05, 0.07,
                                     5, 3, "flower", smooth=True))
    else:
        rb = 0.3 * h / 0.6
        pt.add("body", K.lathe([(rb * 0.8, 0.0), (rb, h * 0.35), (rb * 0.9, h * 0.8), (rb * 0.45, h), (0.0, h * 1.02)], 10, "cap", smooth=True))
        for i in range(5):
            a = 2 * math.pi * i / 5
            pt.add("flowers", K.sphere(rb * 0.35 * math.cos(a), rb * 0.35 * math.sin(a), h * 1.0, 0.05, 0.05, 0.04, 5, 2, "flower"))
    return free(pt)


# ---------------------------------------------------------------- vehicles
@register("wprop.wagon", V, "vehicle", {
    "kind": S.enum("covered", ["covered", "buckboard", "broken"]),
}, "Wagon: a covered prairie wagon (plank box, canvas hoops, spoked painted wheels, tongue), an open buckboard with a "
   "bench seat, or a broken wreck with a fallen wheel.", origin="floor_center")
def wagon(P, seed):
    k = P["kind"]
    pt = Parts()
    L, W = 3.6, 1.3
    zb = 0.75
    wr = {"front": 0.45, "back": 0.6}
    wheels = [(-1, -1.2, wr["back"]), (1, -1.2, wr["back"]), (-1, 1.15, wr["front"]), (1, 1.15, wr["front"])]
    if k == "broken":
        wheels = wheels[:3]
    for sx, y, rr in wheels:
        pt.add("wheels", B.wheel(sx * (W / 2 + 0.12), y, rr, rr, 0.08, sides=10))
    for y, rr in ((-1.2, wr["back"]), (1.15, wr["front"])):
        pt.add("axles", B.timber((-W / 2 - 0.08, y, rr), (W / 2 + 0.08, y, rr), 0.1, 0.1, "wood"))
    box = B.chamfer(0.0, 0.0, zb, zb + 0.55, W, L, 0.05, "hull", top="floor")
    pt.add("box", box)
    pt.add("tongue", B.timber((0.0, L / 2, zb - 0.1), (0.0, L / 2 + 1.6, 0.35), 0.1, 0.1, "wood"))
    if k == "covered":
        # canvas: a closed thin arched shell (outer and inner arcs) over the box, flared at the ends
        ro, ri, zc = W / 2 + 0.08, W / 2 + 0.02, zb + 0.55
        sec = [(ro * math.cos(math.pi * j / 6), zc + 1.0 * math.sin(math.pi * j / 6)) for j in range(7)]
        sec += [(ri * math.cos(math.pi * j / 6), zc + 0.94 * math.sin(math.pi * j / 6)) for j in reversed(range(7))]
        pt.add("canvas", B.slab(K.ccw(sec), -L / 2 + 0.12, L / 2 - 0.12, "fabric"))
        pt.add("bonnet", B.timber((-W / 2 - 0.05, -L / 2 + 0.15, zb + 0.55), (W / 2 + 0.05, -L / 2 + 0.15, zb + 0.55), 0.06, 0.06, "wood"))
    elif k == "buckboard":
        pt.add("seat", B.chamfer(0.0, 0.9, zb + 0.55, zb + 0.65, W - 0.1, 0.45, 0.04, "wood", top="leather"))
        for sx in (-1, 1):
            pt.add("seat", B.timber((sx * 0.5, 0.9, zb + 0.55), (sx * 0.5, 1.0, zb + 0.95), 0.06, 0.06, "wood", up=(1.0, 0.0, 0.0)))
        pt.add("seat", B.timber((-0.55, 1.05, zb + 0.95), (0.55, 1.05, zb + 0.95), 0.07, 0.08, "wood"))
    nodes = pt.nodes()
    if k == "broken":
        for n in nodes:
            n.mesh.rotate_y(-0.12)
        fallen = B.wheel(0.0, 0.0, 0.0, wr["front"], 0.08, sides=10, axis="y").rotate_x(math.pi / 2).translate(1.7, 1.6, 0.04)
        nodes.append(Node("fallen_wheel", fallen))
    return finalize(nodes, B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


# ---------------------------------------------------------------- saloon furniture
@register("wprop.saloon_doors", V, "arch", {
    "width": S.num(1.5, 1.2, 2.4),
}, "Freestanding batwing saloon doors for an interior doorway: two scalloped half-height leaves on hinge posts "
   "with a lintel board.", origin="floor_center")
def saloon_doors(P, seed):
    w = P["width"]
    pt = Parts()
    for sx in (-1, 1):
        pt.add("posts", B.sq_post(sx * (w / 2 + 0.06), 0.0, 0.0, 2.3, 0.12, "frame"))
        bw = w / 2 - 0.03
        cx = sx * (bw / 2 + 0.015)
        pt.add("leaves", B.slab(batwing_outline(cx, bw, sx), -0.02, 0.02, "door"))
    pt.add("lintel", B.timber((-w / 2 - 0.2, 0.0, 2.38), (w / 2 + 0.2, 0.0, 2.38), 0.14, 0.16, "frame"))
    return free(pt)


@register("wprop.table", V, "furniture", {
    "kind": S.enum("round", ["round", "square", "card", "long"]),
}, "Table: a round saloon table on a turned pedestal, a square four-legged table, a card table with a felt top, or "
   "a long trestle table with benches' height.", origin="floor_center")
def table(P, seed):
    k = P["kind"]
    pt = Parts()
    if k in ("round", "card"):
        top = "wood" if k == "round" else "cushion"
        pt.add("top", K.lathe([(0.55, 0.72), (0.58, 0.75), (0.58, 0.78)], 10, "wood", smooth=False, cap_roles=("wood", top)))
        pt.add("pedestal", K.lathe([(0.32, 0.0), (0.3, 0.05), (0.06, 0.12), (0.07, 0.4), (0.05, 0.55), (0.09, 0.72)], 6, "wood", smooth=True))
    elif k == "square":
        pt.add("top", B.chamfer(0.0, 0.0, 0.7, 0.77, 0.95, 0.95, 0.06, "wood", top="body"))
        for sx in (-1, 1):
            for sy in (-1, 1):
                pt.add("legs", B.post(sx * 0.38, sy * 0.38, 0.0, 0.7, 0.04, "wood", sides=4, taper=1.25))
    else:
        pt.add("top", B.chamfer(0.0, 0.0, 0.72, 0.8, 2.2, 0.8, 0.05, "wood", top="body"))
        for sx in (-1, 1):
            pt.add("legs", B.slab([(-0.3, 0.0), (0.3, 0.0), (0.08, 0.15), (0.08, 0.62), (0.3, 0.72), (-0.3, 0.72), (-0.08, 0.62), (-0.08, 0.15)],
                                  -0.04, 0.04, "wood").rotate_z(math.pi / 2).translate(sx * 0.85, 0.0, 0.0))
        pt.add("stretcher", B.timber((-0.85, 0.0, 0.3), (0.85, 0.0, 0.3), 0.07, 0.09, "wood"))
    return free(pt)


@register("wprop.chair", V, "furniture", {
    "kind": S.enum("chair", ["chair", "stool", "rocking", "bench"]),
}, "Seat: a spindle-back saloon chair, a bar stool, a rocking chair on curved runners, or a plank bench.",
   origin="floor_center")
def chair(P, seed):
    k = P["kind"]
    pt = Parts()
    if k == "stool":
        pt.add("seat", K.lathe([(0.19, 0.7), (0.2, 0.74), (0.19, 0.77)], 8, "wood", smooth=False, cap_roles=("wood", "leather")))
        for i in range(3):
            a = 2 * math.pi * i / 3
            pt.add("legs", B.timber((0.22 * math.cos(a), 0.22 * math.sin(a), 0.0), (0.1 * math.cos(a), 0.1 * math.sin(a), 0.7), 0.04, 0.04, "wood"))
        return free(pt)
    if k == "bench":
        pt.add("seat", B.chamfer(0.0, 0.0, 0.42, 0.48, 1.6, 0.36, 0.04, "wood", top="step"))
        for sx in (-1, 1):
            pt.add("legs", B.slab([(-0.16, 0.0), (0.16, 0.0), (0.05, 0.12), (0.05, 0.42), (-0.05, 0.42), (-0.05, 0.12)], -0.03, 0.03, "wood")
                   .rotate_z(math.pi / 2).translate(sx * 0.62, 0.0, 0.0))
        return free(pt)
    pt.add("seat", B.chamfer(0.0, 0.0, 0.43, 0.48, 0.44, 0.42, 0.06, "wood", top="body"))
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("legs", B.post(sx * 0.18, sy * 0.17, 0.0 if k == "chair" else 0.1, 0.43, 0.022, "wood", sides=4, taper=1.0))
        pt.add("back_posts", B.timber((sx * 0.18, 0.19, 0.48), (sx * 0.19, 0.25, 1.02), 0.04, 0.04, "wood", up=(1.0, 0.0, 0.0)))
    pt.add("back", B.timber((-0.2, 0.25, 0.98), (0.2, 0.25, 0.98), 0.05, 0.1, "wood"))
    for x in (-0.08, 0.0, 0.08):
        pt.add("spindles", B.spindle((x, 0.22, 0.5), (x, 0.25, 0.93), 0.025, "wood"))
    if k == "rocking":
        for sx in (-1, 1):
            path = [(sx * 0.18, -0.42 + 0.84 * i / 6, 0.05 + 0.25 * ((i / 6 - 0.5) * 2) ** 2) for i in range(7)]
            pt.add("runners", B.sweep(path, [(-0.02, -0.03), (0.02, -0.03), (0.02, 0.03), (-0.02, 0.03)], "wood"))
    return free(pt)


@register("wprop.bar", V, "furniture_large", {
    "length": S.num(4.0, 2.0, 6.0), "kind": S.enum("counter", ["counter", "back_bar"]),
}, "Saloon bar: a long panelled counter with a polished top, a brass foot rail and a raised lip; or the back bar - "
   "shelving of bottles (painted shelf texture) under a cornice with a mirror panel.", origin="floor_center")
def bar(P, seed):
    L = P["length"]
    pt = Parts()
    if P["kind"] == "counter":
        sec = [(-0.32, 0.0), (0.32, 0.0), (0.32, 0.12), (0.28, 0.14), (0.28, 0.98), (-0.3, 0.98), (-0.3, 0.14), (-0.32, 0.12)]
        pt.add("body", B.slab([(y, z) for y, z in sec], -L / 2, L / 2, "body").rotate_z(math.pi / 2))
        pt.add("top", B.chamfer(0.0, -0.02, 0.98, 1.08, L + 0.12, 0.74, 0.05, "wood", top="body"))
        pt.add("rail", B.post(0.0, 0.0, 0.0, L - 0.2, 0.025, "chrome", sides=6, taper=1.0).rotate_y(math.pi / 2).translate(-(L - 0.2) / 2, -0.45, 0.2))
        for x in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):
            pt.add("panels", B.card(x, -0.325, 0.55, min(1.2, L / 3 - 0.2), 0.62, "door"), "card")
        return free(pt)
    pt.add("cabinet", B.chamfer(0.0, 0.0, 0.0, 1.0, L, 0.55, 0.05, "body", top="wood"))
    pt.add("shelves", B.board(-L / 2 + 0.05, L / 2 - 0.05, -0.12, 0.25, 1.0, 2.4, "wood"))
    for x0, x1 in ((-L / 2 + 0.1, -L * 0.2), (L * 0.2, L / 2 - 0.1)):
        pt.add("bottles", B.card((x0 + x1) / 2, -0.126, 1.7, x1 - x0, 1.3, "book"), "card")
    pt.add("mirror", B.card(0.0, -0.126, 1.75, L * 0.38, 1.1, "glass"), "card")
    pt.add("cornice", B.chamfer(0.0, 0.05, 2.4, 2.62, L + 0.2, 0.5, 0.06, "trim"))
    return free(pt)


@register("wprop.piano", V, "furniture_large", {
    "stool": S.boolean(True),
}, "Upright saloon piano: a tall cabinet with a fallboard and keyboard shelf, turned front legs, a music rest and a "
   "round stool.", origin="floor_center")
def piano(P, seed):
    pt = Parts()
    pt.add("cabinet", B.chamfer(0.0, 0.2, 0.0, 1.3, 1.5, 0.55, 0.05, "body", top="wood"))
    pt.add("keyshelf", B.chamfer(0.0, -0.15, 0.68, 0.78, 1.4, 0.32, 0.03, "wood", top="paper"))
    pt.add("keys", B.card(0.0, -0.312, 0.73, 1.3, 0.08, "paper"), "card")
    for sx in (-1, 1):
        pt.add("legs", K.lathe([(0.05, 0.0), (0.06, 0.3), (0.035, 0.5), (0.05, 0.68)], 6, "wood", smooth=True).translate(sx * 0.62, -0.25, 0.0))
    pt.add("rest", B.chamfer(0.0, -0.08, 1.0, 1.25, 0.9, 0.06, 0.02, "wood"))
    pt.add("top_trim", B.chamfer(0.0, 0.2, 1.3, 1.36, 1.6, 0.62, 0.04, "trim"))
    if P["stool"]:
        pt.add("stool", K.lathe([(0.2, 0.46), (0.21, 0.5)], 8, "wood", smooth=False, cap_roles=("wood", "cushion")).translate(0.0, -0.75, 0.0))
        pt.add("stool", K.lathe([(0.12, 0.0), (0.05, 0.08), (0.05, 0.46)], 6, "wood", smooth=True).translate(0.0, -0.75, 0.0))
    return free(pt)


@register("wprop.stove", V, "furniture", {
    "pipe": S.num(1.6, 0.6, 2.4),
}, "Pot-belly stove: a bulging cast-iron lathe body on three short legs with a glowing grate window and a stovepipe "
   "rising to the ceiling.", origin="floor_center")
def stove(P, seed):
    pt = Parts()
    pt.add("body", K.lathe([(0.22, 0.15), (0.32, 0.35), (0.34, 0.6), (0.26, 0.88), (0.24, 0.95), (0.12, 1.02)], 8, "metal", smooth=True))
    for i in range(3):
        a = 2 * math.pi * i / 3
        pt.add("legs", B.post(0.2 * math.cos(a), 0.2 * math.sin(a), 0.0, 0.17, 0.035, "metal", sides=4, taper=1.0))
    pt.add("pipe", B.post(0.0, 0.0, 1.0, 1.02 + P["pipe"], 0.08, "metal", sides=6, taper=1.0))
    pt.add("grate", B.card(0.0, -0.335, 0.5, 0.2, 0.14, "fire"), "card")
    meta = {"bake_lights": [B.light((0.0, -0.7, 0.5), 2.2, 0.45)]}
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], **meta))


# ---------------------------------------------------------------- street fixtures
@register("wprop.wanted_board", V, "furniture", {
    "posters": S.integer(3, 1, 5), "kind": S.enum("posts", ["posts", "wall"]),
}, "Notice board: a plank board in a frame (on two posts with a little roof, or wall-mounted) pinned with blank "
   "wanted posters (empty heading and portrait frame, no text).", origin="floor_center")
def wanted_board(P, seed):
    r = rng(seed, "wprop.wanted_board")
    pt = Parts()
    z0 = 0.9 if P["kind"] == "posts" else 0.0
    w, h = 1.6, 1.1
    pt.add("board", B.chamfer(0.0, 0.0, z0, z0 + h, w, 0.06, 0.02, "wood", top="trim"))
    pt.add("frame", K.prism(K.rounded_rect2d(w + 0.12, 0.1, 0.02, 1), z0 + h - 0.002, z0 + h + 0.08, "trim"))
    if P["kind"] == "posts":
        for sx in (-1, 1):
            pt.add("posts", B.sq_post(sx * (w / 2 - 0.1), 0.06, 0.0, z0 + h + 0.35, 0.12, "post"))
        pt.add("roof", B.shed_roof(-w / 2 - 0.15, w / 2 + 0.15, -0.3, 0.25, z0 + h + 0.32, z0 + h + 0.45, "roof", t=0.05))
    n = P["posters"]
    for i in range(n):
        x = -w / 2 + 0.22 + (w - 0.44) * (i + 0.5) / n - 0.0
        pw, ph = 0.36, 0.48
        tilt = r.uniform(-0.06, 0.06)
        c = B.card(0.0, 0.0, 0.0, pw, ph, "paper").rotate_y(tilt).translate(x, -0.032 - 0.002 * i, z0 + h / 2 + r.uniform(-0.12, 0.12))
        pt.add("posters", c, "card")
    return free(pt)


@register("wprop.windmill", V, "structure", {
    "height": S.num(8.0, 6.0, 10.0),
}, "Water-pumping windmill: a tapering four-leg lattice tower with girts and cross braces, a multi-blade fan wheel, "
   "a tail vane, a pump rod down to a pump head over a round stock tank.", origin="floor_center")
def windmill(P, seed):
    h = P["height"]
    pt = Parts()
    b0, b1 = 1.3, 0.3
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("legs", B.beam((sx * b0, sy * b0, 0.0), (sx * b1, sy * b1, h), 0.09, 0.09, "metal", roll=45.0))
    for z in (h * 0.3, h * 0.6, h * 0.85):
        t = b0 + (b1 - b0) * z / h
        for (ax, ay), (bx, by) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            k = 0.06
            pt.add("girts", B.beam((ax * t * (1 - k) + bx * t * k, ay * t * (1 - k) + by * t * k, z),
                                   (bx * t * (1 - k) + ax * t * k, by * t * (1 - k) + ay * t * k, z), 0.05, 0.05, "metal", roll=45.0))
    pt.add("platform", K.prism(K.circle2d(0.75, 8, start=math.pi / 8), h - 0.1, h, "wood", role_top="step"))
    pt.add("head", B.chamfer(0.0, 0.0, h, h + 0.5, 0.4, 0.7, 0.08, "metal"))
    hub = (0.0, -0.55, h + 0.3)
    nbl = 12
    pitch = math.radians(28)
    for i in range(nbl):
        a = 2 * math.pi * i / nbl
        er = (math.cos(a), 0.0, math.sin(a))
        et = (-math.sin(a) * math.cos(pitch), math.sin(pitch), math.cos(a) * math.cos(pitch))

        def pnt(rr, ww):
            return (hub[0] + er[0] * rr + et[0] * ww, hub[1] + er[1] * rr + et[1] * ww, hub[2] + er[2] * rr + et[2] * ww)
        q = [pnt(0.25, -0.05), pnt(1.5, -0.17), pnt(1.5, 0.17), pnt(0.25, 0.05)]
        uv = [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])]
        pt.add("blades", K.Mesh().add(q, [(0, 1, 2, 3)], "hull_alt", False, uv), "card")   # hull_alt renders double-sided
    pt.add("rim", K.torus(1.5, 0.03, 12, 3, "metal", smooth=False).rotate_x(math.pi / 2).translate(hub[0], hub[1], hub[2]))
    pt.add("hubcap", K.lathe([(0.14, 0.0), (0.0, 0.18)], 6, "metal", smooth=False).rotate_x(math.pi / 2).translate(hub[0], hub[1] - 0.02, hub[2]))
    pt.add("tail_boom", B.beam((0.0, 0.2, h + 0.3), (0.0, 2.0, h + 0.45), 0.05, 0.05, "metal", roll=45.0))
    vane = [(0.0, 0.0), (1.2, -0.12), (1.2, 0.72), (0.0, 0.34)]
    pt.add("vane", B.slab(vane, -0.012, 0.012, "hull_alt").rotate_z(math.pi / 2).translate(0.0, 1.0, h + 0.12))
    pt.add("rod", B.post(0.0, 0.0, 0.6, h, 0.02, "metal", sides=3, taper=1.0))
    pt.add("pump", B.chamfer(0.0, 0.0, 0.0, 0.7, 0.2, 0.2, 0.04, "metal"))
    pt.add("tank", K.lathe([(1.1, 0.0), (1.1, 0.6)], 12, "hull_alt", smooth=True, cap_roles=("metal", "water")).translate(1.6, 1.6, 0.0))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True))


@register("wprop.well", V, "structure", {
    "roof": S.boolean(True),
}, "Fieldstone well: a round stone curb (lathe with a coping lip) around dark water, two posts carrying a log "
   "windlass with crank and rope bucket, and a little shingle roof.", origin="floor_center")
def well(P, seed):
    pt = Parts()
    pt.add("curb", K.prism(K.circle2d(0.92, 10, start=math.pi / 10), 0.0, 0.72, "stone", role_top="trim",
                           holes=[K.circle2d(0.66, 10, start=math.pi / 10)]))
    pt.add("water", K.prism(K.circle2d(0.66, 10, start=math.pi / 10), 0.25, 0.3, "water"))
    for sx in (-1, 1):
        pt.add("posts", B.sq_post(sx * 0.78, 0.0, 0.0, 1.95, 0.14, "post"))
    pt.add("drum", B.post(0.0, 0.0, 0.0, 1.4, 0.1, "bark", sides=7, taper=1.0).rotate_y(math.pi / 2).translate(-0.7, 0.0, 1.3))
    pt.add("crank", B.timber((0.85, 0.0, 1.3), (0.85, -0.06, 1.05), 0.04, 0.04, "metal", up=(1.0, 0.0, 0.0)))
    pt.add("crank", B.timber((0.85, -0.06, 1.05), (1.05, -0.06, 1.05), 0.04, 0.04, "metal"))
    pt.add("rope", B.post(0.0, 0.0, 0.85, 1.22, 0.012, "rope", sides=3, taper=1.0))
    pt.add("bucket", K.lathe([(0.11, 0.62), (0.14, 0.85)], 7, "body", smooth=False, cap_roles=("wood", "opening")))
    if P["roof"]:
        pt.add("roof", B.gable_roof(1.5, 1.3, 2.0, 2.6, "roof", over_side=0.2, over_front=0.2, over_back=0.2, t=0.06, y_front=-0.65))
    return free(pt)


@register("wprop.tombstone", V, "prop", {
    "kind": S.enum("round", ["round", "cross", "board", "cairn"]),
}, "Grave marker: a round-topped headstone on a plinth, a timber cross, a painted wooden board marker, or a cairn "
   "of stones over a low mound.", origin="floor_center")
def tombstone(P, seed):
    k = P["kind"]
    r = rng(seed, "wprop.tombstone", k)
    pt = Parts()
    if k == "round":
        o = [(-0.25, 0.0), (0.25, 0.0)] + [(0.25 * math.cos(a), 0.62 + 0.25 * math.sin(a)) for a in [math.pi * i / 6 for i in range(7)]]
        pt.add("stone", B.slab(o, -0.05, 0.05, "rock").translate(0.0, 0.0, 0.1))
        pt.add("plinth", B.chamfer(0.0, 0.0, 0.0, 0.12, 0.62, 0.26, 0.03, "rock"))
    elif k == "cross":
        pt.add("cross", B.timber((0.0, 0.0, 0.0), (0.0, 0.0, 1.05), 0.08, 0.08, "post", up=(0.0, 1.0, 0.0)))
        pt.add("arm", B.timber((-0.28, 0.0, 0.75), (0.28, 0.0, 0.75), 0.07, 0.07, "post"))
    elif k == "board":
        o = [(-0.18, 0.0), (0.18, 0.0), (0.18, 0.72), (0.12, 0.8), (-0.12, 0.8), (-0.18, 0.72)]
        pt.add("board", B.slab(o, -0.025, 0.025, "wood"))
        pt.add("face", B.card(0.0, -0.026, 0.5, 0.28, 0.3, "knit"), "card")
    else:
        pt.add("mound", B.rock_blob(0.0, 0.0, 0.0, 0.45, 0.72, 0.16, r, role="dirt", segs=7, rings=2, jitter=0.08))
        for i in range(6):
            pt.add("stones", B.rock_blob(r.uniform(-0.25, 0.25), r.uniform(-0.5, 0.5), 0.15, 0.13, 0.12, 0.09, r, role="rock", segs=5, rings=2))
    return free(pt)


@register("wprop.lantern", V, "furniture", {
    "kind": S.enum("hanging", ["hanging", "wall", "post", "table"]),
}, "Lamp: a hanging barn lantern with a wire bail, a wall bracket lantern, a street lamp on a post, or a table oil "
   "lamp with a glass chimney; the glowing glass is emissive and night packs bake a warm pool around it.",
   origin="floor_center")
def lantern(P, seed):
    k = P["kind"]
    pt = Parts()

    def lamp(z, s=1.0):
        pt.add("base", K.lathe([(0.09 * s, z), (0.1 * s, z + 0.04 * s)], 6, "metal", smooth=False))
        pt.add("glass", K.lathe([(0.075 * s, z + 0.042 * s), (0.09 * s, z + 0.14 * s), (0.065 * s, z + 0.24 * s)], 6, "orb", smooth=True))
        pt.add("cap", K.lathe([(0.1 * s, z + 0.242 * s), (0.03 * s, z + 0.33 * s), (0.0, z + 0.36 * s)], 6, "metal", smooth=False))
        pt.add("flame", K.lathe([(0.025 * s, z + 0.08 * s), (0.0, z + 0.17 * s)], 4, "light", smooth=False))
    if k == "hanging":
        lamp(0.0)
        pt.add("bail", K.torus(0.08, 0.008, 6, 3, "metal", smooth=False).rotate_x(math.pi / 2).translate(0.0, 0.0, 0.42))
        meta = {"bake_lights": [B.light((0.0, 0.0, 0.15), 3.0, 0.6)], "mount": "ceiling"}
    elif k == "wall":
        lamp(0.0)
        pt.add("bracket", B.timber((0.0, 0.25, 0.42), (0.0, 0.02, 0.42), 0.03, 0.03, "metal"))
        pt.add("plate", B.chamfer(0.0, 0.27, 0.2, 0.55, 0.12, 0.03, 0.02, "metal"))
        meta = {"bake_lights": [B.light((0.0, -0.3, 0.15), 3.2, 0.6)], "mount": "wall"}
    elif k == "post":
        pt.add("post", B.post(0.0, 0.0, 0.0, 2.6, 0.07, "metal", sides=6, taper=0.7))
        pt.add("arm", B.timber((0.0, 0.0, 2.55), (0.0, -0.45, 2.55), 0.04, 0.04, "metal"))
        lamp(2.12, 1.4)
        for key in list(pt.meshes):
            if key[0] in ("base", "glass", "cap", "flame"):
                pt.meshes[key].translate(0.0, -0.45, 0.0)
        meta = {"bake_lights": [B.light((0.0, -0.45, 2.3), 4.5, 0.7)], "mount": "floor"}
    else:
        pt.add("foot", K.lathe([(0.09, 0.0), (0.05, 0.03), (0.07, 0.12), (0.03, 0.16)], 6, "chrome", smooth=True))
        pt.add("glass", K.lathe([(0.04, 0.162), (0.05, 0.22), (0.025, 0.36)], 6, "orb", smooth=True))
        pt.add("flame", K.lathe([(0.012, 0.18), (0.0, 0.24)], 4, "light", smooth=False))
        meta = {"bake_lights": [B.light((0.0, 0.0, 0.25), 2.0, 0.45)], "mount": "table"}
    sock = B.sock("prop", (0, 0, 0), "up") if meta["mount"] in ("floor", "table") else B.sock(meta["mount"], (0, 0, 0), "s")
    m = B.grid_meta("free", None, [sock], **meta)
    return finalize(pt.nodes(), m)


@register("wprop.trough", V, "furniture", {
    "water": S.boolean(True),
}, "Water trough: a long plank trough on splayed legs with iron end bands and still water inside.",
   origin="floor_center")
def trough(P, seed):
    pt = Parts()
    rings = [[(x * 1.0, y * 0.3, 0.25) for x, y in K.rounded_rect2d(2.0, 2.0, 0.08, 1)],
             [(x * 1.1, y * 0.4, 0.75) for x, y in K.rounded_rect2d(2.0, 2.0, 0.08, 1)]]
    pt.add("trough", K.loft(rings, "body_alt", smooth=False, cap_roles=("wood", "water" if P["water"] else "opening")))
    for sx in (-1, 1):
        pt.add("legs", B.slab([(-0.42, 0.0), (0.42, 0.0), (0.3, 0.27), (-0.3, 0.27)], -0.04, 0.04, "wood").rotate_z(math.pi / 2).translate(sx * 0.75, 0.0, 0.0))
        pt.add("bands", K.prism(K.rounded_rect2d(0.08, 0.84, 0.02, 1), 0.3, 0.72, "metal").translate(sx * 1.0, 0.0, 0.0))
    return free(pt)


@register("wprop.signpost", V, "furniture", {
    "arrows": S.integer(3, 1, 4),
}, "Crossroads signpost: a tall post with blank pointed direction boards at different headings and heights.",
   origin="floor_center")
def signpost(P, seed):
    r = rng(seed, "wprop.signpost")
    pt = Parts()
    pt.add("post", B.post(0.0, 0.0, 0.0, 2.6, 0.08, "post", sides=6, taper=0.85))
    pt.add("cap", K.lathe([(0.1, 2.6), (0.0, 2.75)], 4, "trim", smooth=False, start=math.pi / 4))
    for i in range(P["arrows"]):
        z = 2.35 - 0.32 * i
        yaw = r.uniform(-1.4, 1.4) + (math.pi if i % 2 else 0.0)
        o = [(0.06, -0.11), (0.85, -0.11), (1.0, 0.0), (0.85, 0.11), (0.06, 0.11)]
        board = B.slab(o, -0.025, 0.025, "knit", front="knit", back="knit")
        pt.add("boards", board.rotate_z(yaw).translate(0.0, 0.0, z))
    return free(pt)


@register("wprop.wheel", V, "prop", {
    "lean": S.boolean(True),
}, "Spare wagon wheel: a painted spoked wheel leaning against a wall (or lying flat).", origin="floor_center")
def spare_wheel(P, seed):
    pt = Parts()
    w = B.wheel(0.0, 0.0, 0.0, 0.6, 0.08, sides=10, axis="y")
    if P["lean"]:
        w.rotate_x(-0.2).translate(0.0, 0.0, 0.6)
    else:
        w.rotate_x(math.pi / 2).translate(0.0, 0.0, 0.04)
    pt.add("wheel", w)
    return free(pt)


@register("wprop.bucket", V, "prop", {
    "kind": S.enum("bucket", ["bucket", "spittoon", "basin"]),
}, "Small vessel: a stave bucket with a rope bail, a brass spittoon, or a tin wash basin.", origin="floor_center")
def bucket(P, seed):
    k = P["kind"]
    pt = Parts()
    if k == "bucket":
        pt.add("bucket", K.lathe([(0.13, 0.0), (0.16, 0.3)], 8, "body", smooth=False, cap_roles=("wood", "water")))
        pt.add("bail", K.torus(0.15, 0.008, 8, 3, "rope", smooth=False).rotate_x(math.pi / 2).scale(1.0, 1.0, 0.7).translate(0.0, 0.0, 0.3))
    elif k == "spittoon":
        pt.add("pot", K.lathe([(0.1, 0.0), (0.14, 0.08), (0.12, 0.16), (0.07, 0.2), (0.12, 0.24)], 8, "chrome", smooth=True, cap_roles=("chrome", "opening")))
    else:
        pt.add("basin", K.lathe([(0.12, 0.0), (0.25, 0.11)], 8, "hull_alt", smooth=False, cap_roles=("metal", "water")))
    return free(pt)


@register("wprop.bottles", V, "prop", {
    "count": S.integer(3, 1, 5),
}, "Table dressing: whiskey bottles (lathe, glass role) and short glasses in a little cluster.", origin="floor_center")
def bottles(P, seed):
    r = rng(seed, "wprop.bottles")
    pt = Parts()
    for i in range(P["count"]):
        x, y = r.uniform(-0.12, 0.12), r.uniform(-0.1, 0.1)
        if i % 2 == 0:
            pt.add("bottles", K.lathe([(0.035, 0.0), (0.037, 0.17), (0.014, 0.23), (0.013, 0.29)], 6, "glass", smooth=True).translate(x, y, 0.0))
        else:
            pt.add("glasses", K.lathe([(0.025, 0.0), (0.03, 0.07)], 6, "glass", smooth=False, cap_roles=("glass", "fire")).translate(x, y, 0.0))
    return free(pt)


@register("wprop.skull", V, "prop", {
    "horns": S.boolean(True),
}, "Bleached steer skull: a tapered muzzle and brow with dark eye sockets and long curved horns; desert dressing.",
   origin="floor_center")
def skull(P, seed):
    pt = Parts()
    rings = []
    for y, w, h in ((-0.3, 0.07, 0.06), (-0.12, 0.1, 0.09), (0.05, 0.16, 0.13), (0.15, 0.17, 0.12)):
        rings.append([(w * math.cos(a), y, 0.13 + h * math.sin(a) * 0.8) for a in [2 * math.pi * k / 6 for k in range(6)]])
    pt.add("skull", K.loft(rings, "snow", smooth=True))
    for sx in (-1, 1):
        pt.add("eyes", B.card(0.0, 0.0, 0.0, 0.05, 0.05, "opening").rotate_z(sx * 0.9).translate(sx * 0.12, 0.02, 0.2), "card")
    if P["horns"]:
        for sx in (-1, 1):
            path = [(sx * 0.14, 0.12, 0.2), (sx * 0.35, 0.14, 0.24), (sx * 0.52, 0.1, 0.34), (sx * 0.58, 0.04, 0.46)]
            pt.add("horns", B.sweep(path, [(-0.035, -0.035), (0.035, -0.035), (0.0, 0.04)], "snow"))
    return free(pt)


@register("wprop.campfire", V, "prop", {
    "lit": S.boolean(True),
}, "Campfire: a ring of stones around crossed logs with emissive flame cards and a warm baked light.",
   origin="floor_center")
def campfire(P, seed):
    r = rng(seed, "wprop.campfire")
    pt = Parts()
    for i in range(7):
        a = 2 * math.pi * i / 7
        pt.add("stones", B.rock_blob(0.5 * math.cos(a), 0.5 * math.sin(a), 0.06, 0.12, 0.1, 0.08, r, role="rock", segs=5, rings=2))
    for a in (0.3, 1.9, 3.5):
        pt.add("logs", B.post(0.0, 0.0, 0.0, 0.7, 0.05, "bark", sides=5, taper=0.9).rotate_y(math.pi / 2 - 0.35).rotate_z(a).translate(0.0, 0.0, 0.05))
    meta = {}
    if P["lit"]:
        for k in range(3):
            c = B.card(0.0, 0.0, 0.25, 0.32, 0.5, "fire").rotate_z(k * math.pi / 3)
            pt.add("flames", c, "card")
        meta["bake_lights"] = [B.light((0.0, 0.0, 0.4), 3.5, 0.75)]
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], **meta))
