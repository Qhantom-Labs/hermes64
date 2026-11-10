"""CYBERKIT streets (cystreet.*): road segments, crossings, tee and corner junctions, road ends, sidewalks, plazas,
alleys, street stairs, ramps, elevated roads, monorail beams, footbridges, facade walkways and metro entrances.

All on the CITY GRID (kits/core/cykit.py): a street is 3 cells wide (2 m sidewalk + 8 m road + 2 m sidewalk), pieces
snap on cell-block centres with yaw in 90 degree steps, the road surface is at y = 0 and sidewalks stand 0.15 m
proud behind a chamfered curb. Ground surfaces are one-sided (kit_shell) and tessellated at 2 m so baked vertex
light and the runtime point-light lattice paint soft pools on them. Road paint (dashes, crosswalk bars, stop lines)
is decal geometry with the worn-paint ground role (snow), so a crossing has bars and no stray centre line.
"""
import math

from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .gen_cyberkit_tower import gem, slot_rect

V = "1.0.0"
SLOT = S.enum("a", list(C.SLOTS), "neon accent slot (pack palette roles: a/b/c/d)")
HALF = C.STREET_W / 2          # 6 m
ROAD = C.ROAD_W / 2            # 4 m
PAINT_Z = 0.012


def ground(x0, y0, x1, y1, z, role, step=2.0, uv_shift=(0.0, 0.0)):
    """One-sided upward ground quads on a 2 m lattice (metric UVs, optional u shift)."""
    xs = C.stations(x0, x1, step)
    ys = C.stations(y0, y1, step)
    m = K.Mesh()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            a, b = xs[i], xs[i + 1]
            c, d = ys[j], ys[j + 1]
            uv = ("m", [(a + uv_shift[0], c + uv_shift[1]), (b + uv_shift[0], c + uv_shift[1]),
                        (b + uv_shift[0], d + uv_shift[1]), (a + uv_shift[0], d + uv_shift[1])])
            m.add([(a, c, z), (b, c, z), (b, d, z), (a, d, z)], [(0, 1, 2, 3)], role, False, [uv])
    return C.weld(m)


def walk(x0, y0, x1, y1, curb_sides="", h=C.CURB, role="sand", curb="step"):
    """Raised sidewalk slab (closed solid): paving top, curb faces with a chamfered lip on `curb_sides` (n e s w)."""
    c = 0.06
    xa, xb = x0 + (c if "w" in curb_sides else 0.0), x1 - (c if "e" in curb_sides else 0.0)
    ya, yb = y0 + (c if "s" in curb_sides else 0.0), y1 - (c if "n" in curb_sides else 0.0)
    lo = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    hi = [(xa, ya), (xb, ya), (xb, yb), (xa, yb)]
    rings = [[(x, y, -0.02) for x, y in lo], [(x, y, h - 0.04) for x, y in lo], [(x, y, h) for x, y in hi]]
    return K.loft(rings, curb, smooth=False, cap_roles=(curb, role))


def dash_line(x, y0, y1, w=0.16, dash=3.0, gap=3.0):
    m = K.Mesh()
    y = y0 + gap / 2
    while y + dash <= y1 + 1e-6:
        m.merge(C.flat_card(x, y + dash / 2, PAINT_Z, w, dash, "snow"))
        y += dash + gap
    return m


def bars(cx, cy, length, depth, n=6, along="x"):
    """Crosswalk bars: n paint quads across a `length` m road, each `depth` m deep."""
    m = K.Mesh()
    pitch = length / n
    for k in range(n):
        t = -length / 2 + pitch * (k + 0.5)
        if along == "x":
            m.merge(C.flat_card(cx + t, cy, PAINT_Z, pitch * 0.55, depth, "snow"))
        else:
            m.merge(C.flat_card(cx, cy + t, PAINT_Z, depth, pitch * 0.55, "snow"))
    return m


def drains(xs, y0, y1, step=4.0):
    m = K.Mesh()
    for x in xs:
        y = y0 + step / 2
        while y < y1:
            m.merge(C.flat_card(x, y, PAINT_Z * 0.8, 0.35, 0.8, "metal"))
            y += step * 2
    return m


def street_sockets(L, ends=("n", "s")):
    out = []
    for e in ends:
        y = L / 2 if e == "n" else -L / 2
        out.append(C.sock("street_end", (0, y, 0), e, width_m=C.STREET_W))
    return out


def street_asset(nodes, meta):
    return C.finish(nodes, meta, cx=False, cy=False, ground=False)


# ---------------------------------------------------------------- cystreet.road
@register("cystreet.road", V, "shell", {
    "cells": S.integer(2, 1, 3, "length in 4 m cells"),
    "walks": S.enum("both", ["both", "left", "right", "none"], "raised sidewalks"),
    "markings": S.enum("dashed", ["dashed", "double", "none"], "centre paint"),
    "drains": S.boolean(True),
}, "Straight street segment, 3 cells wide: wet asphalt road (8 m), raised paving sidewalks with chamfered curbs, "
   "painted centre dashes or a double line, curb drains. Chains end to end on the street sockets.", origin="room_floor")
def road(P, seed):
    L = C.CELL * P["cells"]
    surf, solid, paint = K.Mesh(), K.Mesh(), K.Mesh()
    xl = -ROAD if P["walks"] in ("both", "left") else -HALF
    xr = ROAD if P["walks"] in ("both", "right") else HALF
    surf.merge(ground(xl, -L / 2, xr, L / 2, 0.0, "path", uv_shift=(3.0, 0.0)))
    if P["walks"] in ("both", "left"):
        solid.merge(walk(-HALF, -L / 2, -ROAD, L / 2, "e"))
    if P["walks"] in ("both", "right"):
        solid.merge(walk(ROAD, -L / 2, HALF, L / 2, "w"))
    if P["markings"] == "dashed":
        paint.merge(dash_line(0.0, -L / 2, L / 2))
    elif P["markings"] == "double":
        for x in (-0.14, 0.14):
            paint.merge(C.flat_card(x, 0, PAINT_Z, 0.1, L - 0.1, "snow"))
    if P["drains"]:
        paint.merge(drains([xl + 0.3, xr - 0.3], -L / 2, L / 2))
    meta = C.grid_meta("cell_block_centre", [3, P["cells"]], street_sockets(L), walks=P["walks"])
    return street_asset([Node("road", surf, "shell"), Node("walks", solid, "solid"), Node("paint", paint, "card")], meta)


# ---------------------------------------------------------------- junctions
ARMS = {"n": (-ROAD, ROAD, ROAD, HALF), "s": (-ROAD, -HALF, ROAD, -ROAD), "e": (ROAD, -ROAD, HALF, ROAD), "w": (-HALF, -ROAD, -ROAD, ROAD)}
ARM_SOCK = {"n": ((0, HALF, 0), "n"), "e": ((HALF, 0, 0), "e"), "s": ((0, -HALF, 0), "s"), "w": ((-HALF, 0, 0), "w")}


def junction(arms, crosswalks=True):
    """3 x 3 cell junction: asphalt box, arms open toward `arms` (n e s w) with crosswalk bars, closed sides as one
    continuous sidewalk band (n/s bands run the full 12 m, e/w bands stop 1 cm inside them so no two slabs share a
    vertex), free corners as corner slabs with curbs on both road sides."""
    surf, solid, paint = K.Mesh(), K.Mesh(), K.Mesh()
    surf.merge(ground(-ROAD, -ROAD, ROAD, ROAD, 0.0, "path", uv_shift=(1.5, 0.0)))
    closed = [a for a in "nesw" if a not in arms]
    for name, (x0, y0, x1, y1) in ARMS.items():
        if name in arms:
            surf.merge(ground(x0, y0, x1, y1, 0.0, "path", uv_shift=(1.5, 0.0)))
            if crosswalks:
                if name in "ns":
                    paint.merge(bars(0.0, (y0 + y1) / 2, C.ROAD_W - 0.6, 1.4, 6, "x"))
                else:
                    paint.merge(bars((x0 + x1) / 2, 0.0, C.ROAD_W - 0.6, 1.4, 6, "y"))
    for name in closed:
        if name == "n":
            solid.merge(walk(-HALF, ROAD, HALF, HALF, "s"))
        elif name == "s":
            solid.merge(walk(-HALF, -HALF, HALF, -ROAD, "n"))
        else:
            ya = -ROAD - 0.01 if "s" in closed else -HALF
            yb = ROAD + 0.01 if "n" in closed else HALF
            x0, x1 = (ROAD, HALF) if name == "e" else (-HALF, -ROAD)
            solid.merge(walk(x0, ya, x1, yb, "w" if name == "e" else "e"))
    for sx in (-1, 1):
        for sy in (-1, 1):
            arm_x = "e" if sx > 0 else "w"
            arm_y = "n" if sy > 0 else "s"
            if arm_x in closed or arm_y in closed:
                continue
            x0, x1 = sorted((sx * ROAD, sx * HALF))
            y0, y1 = sorted((sy * ROAD, sy * HALF))
            solid.merge(walk(x0, y0, x1, y1, ("w" if sx > 0 else "e") + ("s" if sy > 0 else "n")))
    return surf, solid, paint


def junction_asset(arms, P, extra=None):
    surf, solid, paint = junction(arms, P.get("crosswalks", True))
    if extra is not None:
        paint.merge(extra)
    meta = C.grid_meta("cell_block_centre", [3, 3], [C.sock("street_end", ARM_SOCK[a][0], ARM_SOCK[a][1], width_m=C.STREET_W) for a in arms])
    return street_asset([Node("road", surf, "shell"), Node("walks", solid, "solid"), Node("paint", paint, "card")], meta)


@register("cystreet.crossing", V, "shell", {"crosswalks": S.boolean(True), "manhole": S.boolean(True)},
          "Four-way crossing, 3 x 3 cells: asphalt box with crosswalk bars on every arm, four corner sidewalks with "
          "curbs and a manhole decal. The street sockets of every arm meet a cystreet.road end.", origin="room_floor")
def crossing(P, seed):
    hole = None
    if P["manhole"]:
        hole = K.Mesh().add([(0.55 * math.cos(K.TAU * i / 8) + 1.2, 0.55 * math.sin(K.TAU * i / 8) - 1.0, PAINT_Z) for i in range(8)],
                            [tuple(range(8))], "metal", False)
    return junction_asset("nesw", P, hole)


@register("cystreet.tee", V, "shell", {"crosswalks": S.boolean(True)},
          "T junction, 3 x 3 cells: arms north, south and east, a continuous sidewalk on the west side; crosswalk bars.",
          origin="room_floor")
def tee(P, seed):
    return junction_asset("nes", P)


@register("cystreet.corner", V, "shell", {"crosswalks": S.boolean(False)},
          "L corner, 3 x 3 cells: the street turns from south to east; outer sidewalks on the north and west sides.",
          origin="room_floor")
def corner(P, seed):
    return junction_asset("es", P)


@register("cystreet.end", V, "shell", {"bollards": S.integer(4, 0, 6), "accent": SLOT},
          "Street end, 3 x 1 cells: the road stops at a raised paving apron with light-capped bollards and a stop "
          "line: where a street meets a plaza or a pedestrian lane.", origin="room_floor")
def end(P, seed):
    L = C.CELL
    surf, solid, paint, deco = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    surf.merge(ground(-ROAD, -L / 2, ROAD, L / 2 - 1.5, 0.0, "path", uv_shift=(3.0, 0.0)))
    solid.merge(walk(-HALF, -L / 2, -ROAD, L / 2 - 1.49, "e"))
    solid.merge(walk(ROAD, -L / 2, HALF, L / 2 - 1.49, "w"))
    solid.merge(walk(-HALF, L / 2 - 1.5, HALF, L / 2, "s"))
    paint.merge(C.flat_card(0, L / 2 - 2.1, PAINT_Z, C.ROAD_W - 0.5, 0.35, "snow"))
    n = P["bollards"]
    for k in range(n):
        x = -ROAD + 0.6 + (C.ROAD_W - 1.2) * k / max(1, n - 1)
        deco.merge(C.lathe_at(x, L / 2 - 0.9, C.CURB - 0.02, [(0.13, 0.0), (0.13, 0.8), (0.1, 0.92), (0.0, 0.95)], 6, "post", smooth=False))
        deco.merge(gem(x, L / 2 - 0.9, C.CURB + 0.78, 0.07, P["accent"], "bright"))
    meta = C.grid_meta("cell_block_centre", [3, 1], street_sockets(L, ("s",)))
    return street_asset([Node("road", surf, "shell"), Node("walks", solid, "solid"), Node("paint", paint, "card"),
                         Node("bollards", deco, "solid")], meta)


# ---------------------------------------------------------------- cystreet.sidewalk / plaza
@register("cystreet.sidewalk", V, "shell", {
    "cells": S.integer(1, 1, 3), "curb": S.enum("s", ["none", "s", "e", "se"], "curb sides facing a road"),
    "role": S.enum("sand", ["sand", "ice"], "paving slabs or wet tiles"),
}, "Raised sidewalk tile(s) 0.15 m proud of the road: paving or wet tiles, chamfered curbs on the road sides. Fills "
   "building fronts, alley mouths and plaza edges.", origin="room_floor")
def sidewalk(P, seed):
    L = C.CELL * P["cells"]
    curbs = "" if P["curb"] == "none" else P["curb"]
    solid = walk(-L / 2, -C.CELL / 2, L / 2, C.CELL / 2, curbs, role=P["role"])
    return street_asset([Node("walk", solid, "solid")], C.grid_meta("cell_block_centre", [P["cells"], 1], []))


@register("cystreet.plaza", V, "shell", {
    "cells": S.integer(2, 1, 3, "square plaza tile in cells"), "accent": SLOT,
    "inlay": S.enum("ring", ["ring", "cross", "none"], "inlaid neon pattern"), "planter": S.boolean(False),
}, "Plaza tile: wet stone tiles with a paving border, inlaid neon light lines (ring or cross) and an optional "
   "central planter seat. Tiles together into squares in front of towers and stations.", origin="room_floor")
def plaza(P, seed):
    L = C.CELL * P["cells"]
    surf, solid, cards, deco = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    surf.merge(ground(-L / 2 + 0.5, -L / 2 + 0.5, L / 2 - 0.5, L / 2 - 0.5, C.CURB, "ice"))
    solid.merge(walk(-L / 2, -L / 2, L / 2, -L / 2 + 0.5, ""))
    solid.merge(walk(-L / 2, L / 2 - 0.5, L / 2, L / 2, ""))
    solid.merge(walk(-L / 2, -L / 2 + 0.49, -L / 2 + 0.5, L / 2 - 0.49, ""))
    solid.merge(walk(L / 2 - 0.5, -L / 2 + 0.49, L / 2, L / 2 - 0.49, ""))
    rect = slot_rect(P["accent"])
    z = C.CURB + 0.01
    if P["inlay"] == "ring":
        R = L * 0.34
        ring = [(R * math.cos(K.TAU * i / 16), R * math.sin(K.TAU * i / 16)) for i in range(16)]
        for i in range(16):
            a, b = ring[i], ring[(i + 1) % 16]
            cards.merge(C.strip((a[0], a[1], z), (b[0], b[1], z), 0.14, "light", (0, 0, 1), rect))
    elif P["inlay"] == "cross":
        for p0, p1 in (((-L / 2 + 0.8, 0, z), (L / 2 - 0.8, 0, z)), ((0, -L / 2 + 0.8, z), (0, L / 2 - 0.8, z))):
            cards.merge(C.strip(p0, p1, 0.14, "light", (0, 0, 1), rect))
    if P["planter"]:
        deco.merge(C.lathe_at(0, 0, C.CURB - 0.02, [(1.3, 0.0), (1.3, 0.45), (1.15, 0.5), (1.15, 0.42), (0.0, 0.42)], 10, "stone",
                              smooth=False, roles=["stone", "trim", "trim", "cap"]))
    meta = C.grid_meta("cell_block_centre", [P["cells"], P["cells"]], [])
    return street_asset([Node("tiles", surf, "shell"), Node("border", solid, "solid"), Node("inlay", cards, "card"),
                         Node("planter", deco, "solid")], meta)


# ---------------------------------------------------------------- cystreet.alley
@register("cystreet.alley", V, "shell", {
    "shape": S.enum("straight", ["straight", "end", "corner", "tee"]),
    "cells": S.integer(2, 1, 3, "length in cells (straight / end)"),
    "height": S.num(10.0, 6.0, 16.0, "side wall height"), "pipes": S.boolean(True), "accent": SLOT,
}, "Back alley, 1 cell wide: grime ground, one-sided building-back walls (facade texture, painted windows), "
   "drain channel, wall pipes and a caged wall lamp; straight, dead end, corner or tee. Open to the sky.",
    origin="room_floor")
def alley(P, seed):
    W = C.CELL
    L = C.CELL * (P["cells"] if P["shape"] in ("straight", "end") else 1)
    H = P["height"]
    surf, walls, deco, cards = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    surf.merge(ground(-W / 2, -L / 2, W / 2, L / 2, 0.0, "dirt", step=1.0))
    paint = C.flat_card(0, 0, PAINT_Z, 0.5, L - 0.2, "metal")
    sides = {"straight": "ew", "end": "ewn", "corner": "wn", "tee": "w"}[P["shape"]]

    def wall(x0, y0, x1, y1):
        # one-sided quad strip facing the alley centre, storeys aligned with the facade texture (4 m)
        zs = sorted(set([0.0, H] + [round(min(H, 4.0 * k + 0.6), 4) for k in range(1, int(H // 4) + 1)]))
        m = K.Mesh()
        L2 = math.hypot(x1 - x0, y1 - y0)
        for a, b in zip(zs, zs[1:]):
            m.add([(x0, y0, a), (x1, y1, a), (x1, y1, b), (x0, y0, b)], [(0, 1, 2, 3)], "wall", False,
                  [("m", [(0, a - 0.6), (L2, a - 0.6), (L2, b - 0.6), (0, b - 0.6)])])
        return C.weld(m)
    if "e" in sides:
        walls.merge(wall(W / 2, -L / 2, W / 2, L / 2))
    if "w" in sides:
        walls.merge(wall(-W / 2, L / 2, -W / 2, -L / 2))
    if "n" in sides:
        walls.merge(wall(W / 2, L / 2, -W / 2, L / 2))
    rect = slot_rect(P["accent"])
    if P["pipes"]:
        x = -W / 2 + 0.22
        deco.merge(C.rod((x, -L / 2 + 0.1, 3.2), (x, L / 2 - 0.1, 3.2), 0.1, 6, "metal"))
        deco.merge(C.rod((x + 0.05, -L / 2 + 0.1, 2.75), (x + 0.05, L / 2 - 0.1, 2.75), 0.06, 4, "metal"))
        deco.merge(C.rod((x, -L / 2 + 1.0, 0.0), (x, -L / 2 + 1.0, 3.05), 0.1, 6, "metal"))
    if "e" in sides:
        deco.merge(C.slab(W / 2 - 0.15, 0.0, 2.9, 0.3, 0.5, 0.4, "frame"))
        deco.merge(gem(W / 2 - 0.36, 0.0, 2.8, 0.12, P["accent"], "core"))
    cards.merge(C.strip((-W / 2 + 0.03, -L / 2 + 0.2, H - 0.5), (-W / 2 + 0.03, L / 2 - 0.2, H - 0.5), 0.1, "light", (1, 0, 0), rect))
    socks = [C.sock("alley_end", (0, -L / 2, 0), "s", width_m=W)]
    if P["shape"] in ("straight", "tee"):
        socks.append(C.sock("alley_end", (0, L / 2, 0), "n", width_m=W))
    if P["shape"] in ("corner", "tee"):
        socks.append(C.sock("alley_end", (W / 2, 0, 0), "e", width_m=W))
    meta = C.grid_meta("cell_block_centre", [1, int(L // C.CELL)], socks, wall_height_m=H)
    surf.merge(paint)
    return street_asset([Node("ground", surf, "shell"), Node("walls", walls, "shell"), Node("pipes", deco, "solid"),
                         Node("neon", cards, "card")], meta)


# ---------------------------------------------------------------- cystreet.stairs / ramp
@register("cystreet.stairs", V, "structure", {
    "rise": S.num(3.0, 1.5, 4.5, "height climbed (m)"), "width": S.num(4.0, 2.0, 4.0), "accent": SLOT,
    "lit_nosings": S.boolean(True, "neon strip on every third nosing"),
}, "Street stairs climbing `rise` over two cells: chamfered treads in a stone-faced flight between side walls, "
   "railings and neon nosing strips; lands on a raised plaza, walkway or station deck.", origin="floor_center")
def stairs(P, seed):
    rise, W = P["rise"], P["width"]
    n = max(4, int(round(rise / 0.25)))
    run = min(7.6, n * 0.32)
    th = rise / n
    tr = run / n
    steps, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    steps.merge(C.stair_flight(W, run, rise, n, "step"))
    for k in range(n):
        y0 = -run / 2 + k * tr
        if P["lit_nosings"] and k % 3 == 2:
            cards.merge(C.strip((-W / 2 + 0.2, y0 - 0.012, (k + 1) * th - 0.04), (W / 2 - 0.2, y0 - 0.012, (k + 1) * th - 0.04), 0.05,
                                "light", (0, -1, 0), slot_rect(P["accent"])))
    for sx in (-1, 1):
        x = sx * (W / 2 + 0.2)
        steps.merge(C.wedge(x, 0, 0.0, 0.4, run + 0.1, 0.5, rise + 0.5, "stone", c=0.03, top="trim"))
        deco.merge(C.rod((x - sx * 0.05, -run / 2, 1.4), (x - sx * 0.05, run / 2, rise + 1.4), 0.05, 4, "rail"))
        for t in (0.1, 0.5, 0.9):
            yy = -run / 2 + run * t
            deco.merge(C.rod((x - sx * 0.05, yy, 0.5 + rise * t - 0.05), (x - sx * 0.05, yy, 1.4 + rise * t), 0.035, 4, "rail"))
    meta = C.grid_meta("cell_block_centre", [1, 2], [C.sock("stair_foot", (0, -run / 2, 0), "s", width_m=W),
                                                     C.sock("stair_head", (0, run / 2, rise), "n", width_m=W)], rise_m=rise)
    return C.finish([Node("flight", steps, "solid"), Node("rails", deco, "solid"), Node("nosing", cards, "card")], meta)


@register("cystreet.ramp", V, "structure", {
    "rise": S.num(1.5, 0.5, 2.0), "width": S.num(4.0, 2.0, 4.0), "accent": SLOT,
}, "Street ramp: a two-cell incline with hazard-striped edges, kerb walls and a lit handrail; for vehicles, "
   "carts and level changes between street and plaza.", origin="floor_center")
def ramp(P, seed):
    rise, W = P["rise"], P["width"]
    L = 2 * C.CELL - 0.2
    m, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    m.merge(C.wedge(0, 0, 0.0, W, L, 0.06, rise, "sand", c=0.02, top="sand"))
    for sx in (-1, 1):
        x = sx * (W / 2 + 0.13)
        m.merge(C.wedge(x, 0, 0.0, 0.3, L + 0.06, 0.35, rise + 0.35, "band", c=0.02, top="trim"))
        deco.merge(C.rod((x, -L / 2 + 0.2, 1.2), (x, L / 2 - 0.2, rise + 1.0), 0.05, 4, "rail"))
        cards.merge(C.strip((x - sx * 0.16, -L / 2 + 0.3, 0.45), (x - sx * 0.16, L / 2 - 0.3, rise * 0.95 + 0.25), 0.06, "light",
                            (-sx, 0, 0), slot_rect(P["accent"])))
    meta = C.grid_meta("cell_block_centre", [1, 2], [C.sock("ramp_foot", (0, -L / 2, 0), "s", width_m=W),
                                                     C.sock("ramp_head", (0, L / 2, rise), "n", width_m=W)], rise_m=rise)
    return C.finish([Node("ramp", m, "solid"), Node("rails", deco, "solid"), Node("neon", cards, "card")], meta)


# ---------------------------------------------------------------- elevated deck / rail / bridge
@register("cystreet.elevated", V, "structure", {
    "height": S.num(7.0, 5.0, 12.0, "deck height (m)"), "cells": S.integer(2, 1, 3, "deck length in cells"),
    "pylon": S.boolean(True, "central pylon under this segment"), "accent": SLOT,
}, "Elevated road deck, 3 cells wide: an asphalt deck on a thick chamfered girder with lit parapet strips, a "
   "tapered central pylon with a hammerhead capital. Chains end to end at deck height.", origin="terrain_center")
def elevated(P, seed):
    H, L = P["height"], C.CELL * P["cells"]
    deck, surf, cards = K.Mesh(), K.Mesh(), K.Mesh()
    deck.merge(C.taper(0, 0, H - 1.6, H, C.STREET_W - 2.0, L, C.STREET_W, L, 0.3, 0.3, "stone", top="roof"))
    surf.merge(ground(-HALF + 0.5, -L / 2, HALF - 0.5, L / 2, H + 0.01, "path", uv_shift=(3.0, 0.0)))
    surf.merge(dash_line(0.0, -L / 2, L / 2).translate(0, 0, H + 0.01))
    for sx in (-1, 1):
        deck.merge(C.slab(sx * (HALF - 0.25), 0, H - 0.05, 0.5, L, 1.0, "stone", c=0.06, top="trim"))
        cards.merge(C.strip((sx * (HALF + C.LIFT), -L / 2 + 0.1, H - 0.4), (sx * (HALF + C.LIFT), L / 2 - 0.1, H - 0.4), 0.14, "light",
                            (sx, 0, 0), slot_rect(P["accent"])))
    if P["pylon"]:
        deck.merge(C.taper(0, 0, 0.0, H - 2.4, 2.4, 2.2, 1.6, 1.5, 0.3, 0.25, "stone", top="trim"))
        deck.merge(C.taper(0, 0, H - 2.45, H - 1.55, 2.0, 1.8, C.STREET_W - 3.0, 1.8, 0.2, 0.2, "trim"))
    meta = C.grid_meta("cell_block_centre", [3, P["cells"]], [C.sock("deck_end", (0, L / 2, H), "n", width_m=C.STREET_W),
                                                               C.sock("deck_end", (0, -L / 2, H), "s", width_m=C.STREET_W)], deck_m=H)
    return C.finish([Node("deck", deck, "solid"), Node("surface", surf, "shell"), Node("neon", cards, "card")], meta, ground=False)


@register("cystreet.rail", V, "structure", {
    "height": S.num(9.0, 6.0, 14.0), "cells": S.integer(2, 1, 3), "pylon": S.boolean(True), "accent": SLOT,
}, "Elevated monorail: a chamfered box-section beam with a lit underside strip on a Y pylon; chains end to end "
   "(cyroom.train cars ride on top).", origin="terrain_center")
def rail(P, seed):
    H, L = P["height"], C.CELL * P["cells"]
    m, cards = K.Mesh(), K.Mesh()
    sec = [(-0.45, 0.0), (0.45, 0.0), (0.6, 0.3), (0.6, 1.2), (0.45, 1.4), (-0.45, 1.4), (-0.6, 1.2), (-0.6, 0.3)]
    m.merge(K.loft([[(x, y, H - 1.4 + z) for x, z in sec] for y in (-L / 2, L / 2)], "trim", smooth=False, cap_roles=("stone", "stone")))
    cards.merge(C.strip((0, -L / 2 + 0.1, H - 1.42), (0, L / 2 - 0.1, H - 1.42), 0.4, "light", (0, 0, -1), slot_rect(P["accent"])))
    if P["pylon"]:
        m.merge(C.taper(0, 0, 0.0, H - 3.2, 1.3, 1.3, 0.9, 0.9, 0.2, 0.15, "stone", top="trim"))
        for sx in (-1, 1):
            m.merge(C.rod((sx * 0.08, 0, H - 3.4), (sx * 0.45, 0, H - 1.3), 0.22, 6, "stone"))
    meta = C.grid_meta("cell_block_centre", [1, P["cells"]], [C.sock("rail_end", (0, L / 2, H), "n"), C.sock("rail_end", (0, -L / 2, H), "s")],
                       deck_m=H)
    return C.finish([Node("beam", m, "solid"), Node("neon", cards, "card")], meta, ground=False)


@register("cystreet.bridge", V, "structure", {
    "span": S.num(14.0, 10.0, 18.0, "clear span (street width plus margins)"), "height": S.num(6.0, 4.5, 9.0),
    "accent": SLOT,
}, "Pedestrian footbridge across a street: a slim chamfered deck with glass-panel railings, a neon underside and "
   "two stair piers at the ends.", origin="floor_center")
def bridge(P, seed):
    Sp, H = P["span"], P["height"]
    m, glass, cards = K.Mesh(), K.Mesh(), K.Mesh()
    m.merge(C.taper(0, 0, H - 0.7, H, Sp, 2.0, Sp + 0.4, 3.0, 0.2, 0.3, "trim", top="sand"))
    for sy in (-1, 1):
        y = sy * 1.42
        m.merge(C.rod((-Sp / 2 - 0.1, y, H + 1.1), (Sp / 2 + 0.1, y, H + 1.1), 0.05, 4, "rail"))
        glass.merge(C.face_card(0, y, H + 0.05, Sp, 1.0, "glass", None, facing="-y" if sy < 0 else "+y"))
    cards.merge(C.strip((-Sp / 2 + 0.3, 0, H - 0.72), (Sp / 2 - 0.3, 0, H - 0.72), 0.5, "light", (0, 0, -1), slot_rect(P["accent"])))
    for sx in (-1, 1):
        m.merge(C.taper(sx * (Sp / 2 + 1.4), 0, 0.0, H + 1.2, 2.8, 3.4, 2.6, 3.2, 0.3, 0.3, "wall", top="roof"))
    meta = C.grid_meta("street_span", None, [C.sock("street_span", (0, 0, 0), "s", span_m=Sp)], deck_m=H)
    return C.finish([Node("deck", m, "solid"), Node("glass", glass, "card"), Node("neon", cards, "card")], meta)


@register("cystreet.walkway", V, "structure", {
    "cells": S.integer(2, 1, 3), "height": S.num(4.6, 3.0, 8.0, "deck height"), "accent": SLOT,
}, "Elevated walkway along a facade: a 2 m deck on wall brackets with railing and a lit lip, mounted at a storey "
   "line (origin on the wall face). Links fire escapes, stairs and upper shop doors.", origin="opening")
def walkway(P, seed):
    L, H = C.CELL * P["cells"], P["height"]
    m, cards = K.Mesh(), K.Mesh()
    m.merge(C.slab(0, -1.0, H - 0.25, L, 2.0, 0.25, "metal", c=0.04))
    k = P["cells"] + 1
    for i in range(k):
        x = -L / 2 + 0.3 + (L - 0.6) * i / max(1, k - 1)
        m.merge(C.wedge(x, -0.6, H - 1.3, 0.14, 1.2, 0.05, 1.05, "trim", c=0.01))
        m.merge(C.rod((x, -1.95, H), (x, -1.95, H + 1.05), 0.035, 4, "rail"))
    m.merge(C.rod((-L / 2, -1.95, H + 1.05), (L / 2, -1.95, H + 1.05), 0.045, 4, "rail"))
    m.merge(C.rod((-L / 2, -1.95, H + 0.5), (L / 2, -1.95, H + 0.5), 0.03, 4, "rail"))
    cards.merge(C.strip((-L / 2 + 0.1, -2.0 - C.LIFT, H - 0.12), (L / 2 - 0.1, -2.0 - C.LIFT, H - 0.12), 0.08, "light", (0, -1, 0),
                        slot_rect(P["accent"])))
    meta = C.grid_meta("wall_face", [P["cells"], 0], [C.sock("wall_mount", (0, 0, H), "n"), C.sock("walkway_end", (-L / 2, -1.0, H), "w"),
                                                      C.sock("walkway_end", (L / 2, -1.0, H), "e")])
    return C.finish([Node("deck", m, "solid"), Node("neon", cards, "card")], meta, cy=False, ground=False)


@register("cystreet.metro", V, "structure", {"accent": SLOT, "depth": S.num(4.0, 3.0, 5.0)},
          "Metro entrance: a stairwell cut into the sidewalk descending `depth` metres between tiled walls, a "
          "canopy frame with a glyph sign and railings; the lower landing ends in a dark tunnel opening.",
          origin="terrain_center")
def metro(P, seed):
    D_ = P["depth"]
    W, run = 3.0, 7.0
    walls, steps, deco, cards = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    n = int(round(D_ / 0.3))
    steps.merge(C.stair_flight(W - 0.04, run, D_, n, "step", descend=True, cy=-0.0))
    steps.merge(C.slab(0, -run / 2 - 1.0, -D_ - 0.25, W - 0.04, 2.02, 0.25, "floor", c=0.02))
    walls.merge(C.open_box(-W / 2, W / 2, -run / 2 - 2.0, run / 2, -D_ - 0.3, 0.0, {"bottom": "floor", "s": "opening", "e": "stone",
                                                                                 "w": "stone", "n": "stone"}, drop=("top", "n")))
    for sx in (-1, 1):
        deco.merge(C.slab(sx * (W / 2 + 0.2), -1.0, 0.0, 0.4, run + 2.0, 0.9, "stone", c=0.05, top="trim"))
        deco.merge(C.rod((sx * (W / 2 + 0.2), run / 2 - 0.2, 1.0), (sx * (W / 2 + 0.2), -run / 2 - 1.8, 1.0), 0.045, 4, "rail"))
        deco.merge(C.rod((sx * (W / 2 + 0.45), run / 2 + 0.1, 0.0), (sx * (W / 2 + 0.45), run / 2 + 0.1, 3.0), 0.08, 4, "post"))
    deco.merge(C.slab(0, run / 2 - 0.6, 2.95, W + 1.2, 1.6, 0.18, "frame", c=0.04))
    deco.merge(C.slab(0, run / 2 + 0.25, 2.2, W + 0.2, 0.18, 0.75, "frame", c=0.03))
    sign = "sign_%s0" % ("a" if P["accent"] == "d" else P["accent"])
    cards.merge(C.face_card(0, run / 2 + 0.34, 2.27, W * 0.94, 0.6, "screen", C.cell_uv("screen", sign), facing="+y", lift=C.LIFT))
    cards.merge(C.face_card(0, run / 2 + 0.16, 2.27, W * 0.94, 0.6, "screen", C.cell_uv("screen", sign), facing="-y", lift=C.LIFT))
    cards.merge(C.strip((-W / 2 - 0.5, run / 2 - 1.41, 2.94), (W / 2 + 0.5, run / 2 - 1.41, 2.94), 0.1, "light", (0, -1, 0), slot_rect(P["accent"])))
    meta = C.grid_meta("cell_block_centre", [1, 3], [C.sock("metro_top", (0, run / 2, 0), "n", width_m=W),
                                                     C.sock("metro_bottom", (0, -run / 2 - 2.0, -D_), "s", width_m=W)], depth_m=D_)
    return C.finish([Node("stairs", steps, "solid"), Node("well", walls, "shell"), Node("canopy", deco, "solid"),
                     Node("sign", cards, "card")], meta, cx=False, cy=True, ground=False)
