"""WESTERNKIT town architecture family (wtown.*), theme-agnostic, on the FRONTIER GRID (gen_westernkit_base).

Lot-line pieces (buildings, false fronts, boardwalks, porches, balconies, fences, the interior gallery) have their origin
on the lot line (a cell boundary) at the middle of their frontage, floor level. Buildings stand behind the line
(Blender +Y = glTF -Z); boardwalks, porches and balconies stand in front of it (toward the street). `entry: socket`
gives a building a door socket on the room.gd door anchor (0.1 m behind the lot line) where the runtime places the
timber doorway frame (wtown.doorway, bound as arch.door) around a dark doorway; `entry: dressed` draws its own door
casing and painted door and has no socket (dressing that is not enterable). Interior shells (wtown.room) are cell-block
pieces (origin on the block centre). Night packs bake warm window pools (meta bake_lights) in front of lit panes.

Painted panels (window panes, doors, blank signs) are single-sided cards (kit_card_*) just proud of a closed frame.
"""
import math

import numpy as np

from . import dkit as D
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from . import gen_westernkit_base as B
from .genutil import finalize
from .rng import rng

V = "1.0.0"
SIDES = ["n", "e", "s", "w"]
SHAPES = ["square", "stepped", "arched", "gabled", "pediment", "tall"]
WALL_ROLES = ["wall", "wall_alt", "hull", "body_alt", "trim", "stone"]
ENTRY = ["dressed", "socket"]


class Parts:
    """Named node accumulator: parts.add(name, mesh[, kind]); parts.win(...) adds a window frame + pane card."""

    def __init__(self):
        self.meshes = {}
        self.order = []

    def add(self, name, mesh, kind="solid"):
        key = (name, kind)
        if key not in self.meshes:
            self.meshes[key] = K.Mesh()
            self.order.append(key)
        self.meshes[key].merge(mesh)
        return self

    def win(self, *a, **kw):
        f, p = B.window(*a, **kw)
        self.add("windows", f)
        self.add("panes", p, "card")

    def nodes(self):
        return [Node(n, B.planar_uv(self.meshes[(n, k)]) if k != "card" else self.meshes[(n, k)], k) for n, k in self.order]


def frontage(span):
    return span * B.CELL - 0.2


def door_socket(x):
    """Door socket on the anchor 0.1 m behind the lot line; facing n = away from the street room."""
    return B.sock("door", (x, B.ANCHOR_BACK, 0.0), "n", width_m=B.DOOR_W, height_m=B.DOOR_H, needs="wtown.doorway")


def door_x(span, at):
    """Door x for frontage `span` cells: `at` = offset from the frontage centre in 2 m steps."""
    x = 2.0 * at
    hw = span * B.CELL / 2.0
    if abs(x) > hw - 1.6 + 1e-9:
        raise ValueError("door offset %s outside a %d-cell frontage" % (at, span))
    return x


def casing(parts, x, w, h, y_face, z0=0.0):
    """Self-drawn door casing for dressed buildings: two jamb boards and a head board with a drip cap."""
    t = 0.15
    parts.add("trim", B.board(x - w / 2 - t, x - w / 2, y_face - 0.08, y_face + 0.01, z0, z0 + h + 0.02, "trim"))
    parts.add("trim", B.board(x + w / 2, x + w / 2 + t, y_face - 0.08, y_face + 0.01, z0, z0 + h + 0.02, "trim"))
    parts.add("trim", B.slab([(x - w / 2 - t - 0.08, z0 + h), (x + w / 2 + t + 0.08, z0 + h), (x + w / 2 + t + 0.08, z0 + h + 0.2),
                              (x + w / 2 + t, z0 + h + 0.26), (x - w / 2 - t, z0 + h + 0.26), (x - w / 2 - t - 0.08, z0 + h + 0.2)],
                             y_face - 0.1, y_face + 0.01, "trim"))


def batwing_outline(cx, bw, sx):
    """Saloon batwing door leaf outline (x, z): straight bottom at 0.85 m, a scalloped top rising toward the hinge."""
    out = [(cx - bw / 2, 0.85), (cx + bw / 2, 0.85)]
    hinge_hi = 0.12
    for k in range(0, 7):
        a = k / 6.0
        x = cx + bw / 2 - bw * a
        lift = hinge_hi * (a if sx < 0 else 1.0 - a)
        out.append((x, 1.86 + lift + 0.07 * math.sin(math.pi * a)))
    return out


def entry(parts, x, y_face, kind, style="plank", w=1.25, h=2.4):
    """Street door on the facade (front face at y_face). socket: a dark 2.4 x 3.0 doorway for the runtime frame (plus
    batwing doors for a saloon); dressed: a painted plank door (or batwings) inside a drawn casing."""
    if kind == "socket":
        parts.add("panes", B.card(x, y_face - 0.006, B.DOOR_H / 2, B.DOOR_W - 0.02, B.DOOR_H - 0.01, "opening"), "card")
        dw = B.DOOR_W
    else:
        dw = w
        parts.add("panes", B.card(x, y_face - 0.012, h / 2, w, h, "door" if style != "batwing" else "opening"), "card")
        casing(parts, x, w, h, y_face)
    if style == "batwing":
        bw = min(dw * 0.46, 0.66)
        for sx in (-1, 1):
            cx = x + sx * (bw / 2 + 0.02)
            parts.add("door", B.slab(batwing_outline(cx, bw, sx), y_face - 0.1, y_face - 0.06, "door"))


def sign_board(parts, cx, cz, w, h, y_face, frame=True):
    """Blank painted sign board (role knit = blank sign texture) in a thin frame with clipped corners."""
    if frame:
        c = 0.12
        x0, x1, z0, z1 = cx - w / 2 - 0.08, cx + w / 2 + 0.08, cz - h / 2 - 0.08, cz + h / 2 + 0.08
        o = [(x0 + c, z0), (x1 - c, z0), (x1, z0 + c), (x1, z1 - c), (x1 - c, z1), (x0 + c, z1), (x0, z1 - c), (x0, z0 + c)]
        parts.add("trim", B.slab(o, y_face - 0.05, y_face - 0.004, "trim"))
    parts.add("panes", B.card(cx, y_face - 0.058, cz, w, h, "knit"), "card")


def window_lights(xs, z, y_face, strength=0.55):
    return [B.light((x, y_face - 1.1, z - 0.4), 2.6, strength) for x in xs]


def lot_meta(span, depth, sockets, entry_kind, **kw):
    m = B.grid_meta("lot_line", [span, 1], sockets, frontage_m=span * B.CELL, depth_m=depth, entry=entry_kind)
    m.update(kw)
    return m


def front_sockets(span):
    return [B.sock("frontage", (0.0, 0.0, 0.0), "s", span=span)]


def corner_boards(parts, w, y_face, h):
    for sx in (-1, 1):
        x = sx * (w / 2 - 0.09)
        parts.add("trim", B.board(x - 0.1, x + 0.1, y_face - 0.06, y_face + 0.02, 0.0, h, "trim"))


def porch_roof(parts, x0, x1, y_face, z_front=2.9, z_back=3.3, posts=None, role="roof"):
    parts.add("porch", B.shed_roof(x0, x1, -2.05, y_face - 0.02, z_front, z_back, role, t=0.1))
    xs = posts if posts is not None else (x0 + 0.25, x1 - 0.25)
    for x in xs:
        parts.add("porch", B.sq_post(x, -1.88, 0.0, z_front, 0.16, "post"))


def stovepipe(parts, x, y, z0, z1):
    p = B.post(x, y, z0, z1, 0.12, "metal", sides=6, taper=1.0)
    p.merge(K.lathe([(0.12, z1 + 0.002), (0.24, z1 + 0.12), (0.0, z1 + 0.3)], 6, "metal", smooth=False).translate(x, y, 0.0))
    parts.add("stovepipe", p)


# ---------------------------------------------------------------- wtown.saloon
@register("wtown.saloon", V, "building", {
    "span": S.integer(2, 2, 3, "frontage in 4 m cells"),
    "depth": S.num(11.0, 8.0, 14.0),
    "shape": S.enum("stepped", SHAPES),
    "balcony": S.boolean(True),
    "entry": S.enum("dressed", ENTRY),
    "door_at": S.integer(0, -2, 2, "door offset from the frontage centre in 2 m steps"),
}, "Two-storey frontier saloon: lap-sided body under a shingle gable, a tall shaped false front with a bracketed "
   "cornice and a blank sign board, an upper balcony on posts with a railing, batwing doors between two windows, upper "
   "windows and a stovepipe.", origin="lot_line")
def saloon(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    he, hr = 6.0, 7.5
    h_wall, h_top = 6.5, 8.6
    yf = -0.12
    pt = Parts()
    pt.add("body", B.gable_body(w - 0.3, d, he, hr, "wall", y_front=0.02))
    pt.add("roof", B.gable_roof(w - 0.3, d, he, hr, "roof", over_side=0.3, over_front=0.0, over_back=0.35, y_front=0.02, sag=0.06))
    pt.add("front", B.slab(B.false_front_outline(w, h_wall, h_top, P["shape"]), yf, 0.0, "trim", front="wall", back="wall"))
    pt.add("trim", B.cornice(-w / 2 - 0.05, w / 2 + 0.05, h_wall - 0.05, yf, depth=0.26, h=0.22, brackets=4))
    pt.add("trim", B.cornice(-w / 2 + 0.05, w / 2 - 0.05, 3.3, yf, depth=0.16, h=0.16))
    corner_boards(pt, w, yf, h_wall - 0.3)
    sign_board(pt, 0.0, 7.3 if P["shape"] not in ("square", "gabled") else 7.0, w * 0.6, 0.9, yf)
    dx = door_x(span, P["door_at"])
    for x in (-w * 0.3, 0.0, w * 0.3):
        pt.win(x, 4.7, 0.85, 1.35, yf, head=True)
    xs_dn = [x for x in (-w * 0.33, w * 0.33) if abs(x - dx) > 1.9]
    for x in xs_dn:
        pt.win(x, 1.75, 1.2, 1.55, yf)
    entry(pt, dx, yf, P["entry"], style="batwing", w=1.5, h=2.5)
    if P["balcony"]:
        yb = -1.75
        pt.add("balcony", B.plank_deck(-w / 2 + 0.1, w / 2 - 0.1, yb, yf - 0.01, 3.15, 0.16))
        for x in (-w / 2 + 0.35, 0.0, w / 2 - 0.35):
            if abs(x - dx) > 1.6:
                pt.add("balcony", B.sq_post(x, yb + 0.2, 0.0, 2.99, 0.18, "post"))
        pt.add("balcony", B.railing(-w / 2 + 0.2, w / 2 - 0.2, yb + 0.1, 3.15, 0.95, 3, balusters=2))
    stovepipe(pt, w * 0.25, d * 0.7, hr - 1.4, hr + 0.9)
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=2)
    meta["bake_lights"] = window_lights(xs_dn + [dx], 1.8, yf, 0.6) + window_lights([-w * 0.3, w * 0.3], 4.6, yf, 0.3)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.store
@register("wtown.store", V, "building", {
    "span": S.integer(2, 1, 3), "depth": S.num(9.0, 6.0, 12.0),
    "shape": S.enum("square", SHAPES), "wall_role": S.enum("wall", WALL_ROLES),
    "porch": S.boolean(True), "entry": S.enum("dressed", ENTRY), "door_at": S.integer(0, -2, 2),
}, "General store: one storey with a tall false front, cornice and blank sign, two big display windows, a plank door "
   "and a shingled porch roof on posts over the boardwalk.", origin="lot_line")
def store(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    he, hr = 3.5, 4.8
    yf = -0.12
    role = P["wall_role"]
    pt = Parts()
    pt.add("body", B.gable_body(w - 0.3, d, he, hr, role, y_front=0.02))
    pt.add("roof", B.gable_roof(w - 0.3, d, he, hr, "roof", over_side=0.25, over_front=0.0, y_front=0.02, sag=0.05))
    h_wall, h_top = (4.7, 5.9) if P["shape"] != "square" else (5.6, 5.6)
    pt.add("front", B.slab(B.false_front_outline(w, h_wall, h_top, P["shape"]), yf, 0.0, "trim", front=role, back=role))
    zc = min(h_wall, h_top)
    pt.add("trim", B.cornice(-w / 2 - 0.04, w / 2 + 0.04, zc - 0.05, yf, depth=0.24, h=0.2, brackets=2 + span))
    sign_board(pt, 0.0, zc - 0.85, w * 0.7, 0.8, yf)
    corner_boards(pt, w, yf, zc - 0.25)
    dx = door_x(span, P["door_at"])
    xs = [x for x in (-w * 0.3, w * 0.3) if abs(x - dx) > 1.9] if span > 1 else []
    for x in xs:
        pt.win(x, 1.7, 1.5, 1.7, yf)
    entry(pt, dx, yf, P["entry"])
    if P["porch"]:
        porch_roof(pt, -w / 2, w / 2, yf, posts=(-w / 2 + 0.25, w / 2 - 0.25) + ((0.0,) if span > 2 else ()))
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=1)
    meta["bake_lights"] = window_lights(xs + [dx], 1.7, yf, 0.6)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.bank
@register("wtown.bank", V, "building", {
    "span": S.integer(2, 2, 3), "depth": S.num(10.0, 8.0, 14.0),
    "entry": S.enum("dressed", ENTRY), "door_at": S.integer(0, -2, 2),
}, "Bank: a two-storey fieldstone block with a flat roof, a heavy bracketed cornice and stepped parapet, a string "
   "course, round-arched ground-floor windows and door, tall upper windows and a blank name plaque.", origin="lot_line")
def bank(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    h = 6.8
    yf = 0.0
    pt = Parts()
    pt.add("body", B.flat_body(w, d, h, "stone", y_front=yf, ch=0.18, top="roof"))
    pt.add("trim", B.cornice(-w / 2 - 0.12, w / 2 + 0.12, h + 0.1, yf, depth=0.4, h=0.3, brackets=6))
    pt.add("trim", B.slab([(-w / 2 + 0.05, h + 0.12), (w / 2 - 0.05, h + 0.12), (w / 2 - 0.05, h + 0.75), (w * 0.14, h + 0.75),
                           (w * 0.14, h + 1.05), (-w * 0.14, h + 1.05), (-w * 0.14, h + 0.75), (-w / 2 + 0.05, h + 0.75)],
                          yf + 0.02, yf + 0.26, "stone"))
    pt.add("trim", B.cornice(-w / 2 - 0.04, w / 2 + 0.04, 3.5, yf, depth=0.14, h=0.16))
    sign_board(pt, 0.0, 6.0, w * 0.34, 0.42, yf, frame=True)
    dx = door_x(span, P["door_at"])
    for x in (-w * 0.32, w * 0.32):
        pt.win(x, 4.95, 0.85, 1.6, yf, head=True)
    xs = [x for x in (-w * 0.3, w * 0.3) if abs(x - dx) > 1.9]
    for x in xs:
        pt.add("windows", B.slab([(x + px, 0.62 + pz) for px, pz in K.opening2d("arch", 1.6, 2.35, 10)], yf - 0.05, yf + 0.02, "trim"))
        pt.add("panes", B.card_poly([(x + px, 0.74 + pz) for px, pz in K.opening2d("arch", 1.3, 2.1, 10)], yf - 0.058, "screen"), "card")
    if P["entry"] == "socket":
        entry(pt, dx, yf, "socket")
    else:
        pt.add("trim", B.slab([(dx + px, pz) for px, pz in K.opening2d("arch", 1.9, 3.0, 10)], yf - 0.05, yf + 0.02, "trim"))
        pt.add("panes", B.card_poly([(dx + px, pz) for px, pz in K.opening2d("arch", 1.4, 2.65, 10)], yf - 0.058, "door"), "card")
    pt.add("chimney", B.chamfer(-w * 0.3, d * 0.75, h - 0.5, h + 1.4, 0.7, 0.7, 0.08, "stone", top="metal"))
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=2)
    meta["bake_lights"] = window_lights(xs, 1.8, yf, 0.5)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.sheriff
@register("wtown.sheriff", V, "building", {
    "span": S.integer(2, 1, 2), "depth": S.num(8.0, 6.0, 11.0),
    "entry": S.enum("dressed", ENTRY),
}, "Sheriff's office and jail: a lap-sided office with a pediment false front, blank plaque and porch roof beside a "
   "fieldstone cell block with small barred windows.", origin="lot_line")
def sheriff(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    he, hr = 3.4, 4.5
    yf = -0.12
    wo = w if span == 1 else 4.6
    xo = -w / 2 + wo / 2
    pt = Parts()
    pt.add("body", B.gable_body(wo - 0.3, d, he, hr, "wall", y_front=0.02).translate(xo, 0, 0))
    pt.add("roof", B.gable_roof(wo - 0.3, d, he, hr, "roof", over_side=0.25, over_front=0.0, y_front=0.02).translate(xo, 0, 0))
    pt.add("front", B.slab(B.false_front_outline(wo, 4.4, 5.4, "pediment"), yf, 0.0, "trim", front="wall", back="wall").translate(xo, 0, 0))
    pt.add("trim", B.cornice(xo - wo / 2 - 0.04, xo + wo / 2 + 0.04, 4.35, yf, depth=0.22, h=0.18, brackets=2))
    sign_board(pt, xo, 3.85, wo * 0.64, 0.58, yf)
    if span == 1:
        dx = 0.0 if P["entry"] == "socket" else -0.6
    else:
        dx = -2.0 if P["entry"] == "socket" else xo + 0.6
    entry(pt, dx, yf, P["entry"], w=1.2, h=2.4)
    if span > 1:
        wj = w - wo
        xj = w / 2 - wj / 2
        pt.add("jail", B.flat_body(wj - 0.1, d * 0.85, 3.3, "stone", y_front=0.05, ch=0.12, top="roof").translate(xj, 0, 0))
        pt.add("jail", B.cornice(xj - wj / 2 + 0.02, xj + wj / 2 - 0.08, 3.35, 0.05, depth=0.12, h=0.14))
        for x in (xj - wj * 0.22, xj + wj * 0.22):
            pt.win(x, 2.25, 0.6, 0.55, 0.05, frame_role="stone")
            for k in range(3):
                bx = x - 0.2 + 0.2 * k
                pt.add("bars", B.spindle((bx, 0.05 - 0.085, 1.94), (bx, 0.05 - 0.085, 2.56), 0.035, "metal"))
    if span > 1 or P["entry"] == "dressed":
        pt.win(xo + wo * 0.27 if span > 1 else w * 0.25, 1.7, 0.8 if span == 1 else 0.9, 1.2, yf)
    porch_roof(pt, xo - wo / 2, xo + wo / 2, yf, z_front=2.85, z_back=3.2)
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=1)
    meta["bake_lights"] = window_lights([dx], 1.7, yf, 0.55)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.stable
@register("wtown.stable", V, "building", {
    "span": S.integer(2, 2, 3), "depth": S.num(10.0, 8.0, 14.0),
    "lean_to": S.boolean(True),
}, "Livery stable: a steep-gabled barn of painted board-and-batten facing the street, big double doors, a hayloft "
   "door under a hoist beam with a pulley and rope, a vent cupola on the ridge and an open lean-to on one side.",
   origin="lot_line")
def stable(P, seed):
    span, d = P["span"], P["depth"]
    wt = frontage(span)
    w = wt * 0.66 if P["lean_to"] else wt
    xo = -wt / 2 + w / 2
    he, hr = 4.2, 7.4
    yf = 0.02
    pt = Parts()
    pt.add("body", B.gable_body(w, d, he, hr, "wall_alt", y_front=yf).translate(xo, 0, 0))
    pt.add("roof", B.gable_roof(w, d, he, hr, "roof", over_side=0.4, over_front=0.3, over_back=0.3, y_front=yf, sag=0.08).translate(xo, 0, 0))
    for sx in (-1, 1):
        pt.add("panes", B.card(xo + sx * 0.82, yf - 0.012, 1.55, 1.6, 3.1, "door"), "card")
    pt.add("panes", B.card(xo, yf - 0.012, 5.15, 1.15, 1.25, "door"), "card")
    pt.add("trim", B.board(xo - 1.85, xo + 1.85, yf - 0.08, yf - 0.002, 3.1, 3.3, "trim"))
    for sx in (-1, 1):
        pt.add("trim", B.board(xo + sx * 1.74 - 0.09, xo + sx * 1.74 + 0.09, yf - 0.078, yf - 0.004, 0.0, 3.096, "trim"))
        pt.add("trim", B.board(xo + sx * 0.7 - 0.08, xo + sx * 0.7 + 0.08, yf - 0.078, yf - 0.004, 4.45, 5.796, "trim"))
    pt.add("trim", B.board(xo - 0.78, xo + 0.78, yf - 0.08, yf - 0.002, 5.8, 5.96, "trim"))
    pt.add("hoist", B.timber((xo, yf + 0.6, hr - 0.45), (xo, yf - 1.15, hr - 0.45), 0.16, 0.2, "wood"))
    pt.add("hoist", K.lathe([(0.12, hr - 1.02), (0.15, hr - 0.8), (0.12, hr - 0.58)], 8, "metal", smooth=True).translate(xo, yf - 0.95, 0.0))
    pt.add("rope", B.post(xo, yf - 0.95, 5.95, hr - 1.03, 0.025, "rope", sides=4, taper=1.0))
    cup = B.chamfer(xo, yf + d * 0.5, hr - 0.4, hr + 0.75, 0.9, 0.9, 0.06, "wall_alt", top="roof")
    pt.add("cupola", cup)
    pt.add("cupola_cap", K.lathe([(0.78, hr + 0.752), (0.0, hr + 1.35)], 4, "roof", smooth=False, start=math.pi / 4).translate(xo, yf + d * 0.5, 0.0))
    if P["lean_to"]:
        lw = wt - w - 0.1
        x0 = xo + w / 2 + 0.02
        lean = B.shed_roof(x0, x0 + lw + 0.25, yf - 0.4, yf + d + 0.3, 3.0, 3.0, "roof", t=0.1)
        A = np.asarray(lean.v)
        A[:, 2] = A[:, 2] - 0.8 * np.clip((A[:, 0] - x0) / max(lw, 0.1), 0, 1.2)
        lean.v = [tuple(p) for p in A.tolist()]
        pt.add("lean_to", lean)
        for y in (yf - 0.2, yf + d * 0.5, yf + d + 0.1):
            pt.add("lean_to", B.sq_post(x0 + lw - 0.1, y, 0.0, 2.25, 0.15, "post"))
        pt.add("lean_rail", B.timber((x0 + lw - 0.1, yf - 0.2, 1.05), (x0 + lw - 0.1, yf + d * 0.5, 1.05), 0.1, 0.12, "rail"))
    return Asset(pt.nodes(), lot_meta(span, d, front_sockets(span), "dressed", storeys=1))


# ---------------------------------------------------------------- wtown.hotel
@register("wtown.hotel", V, "building", {
    "span": S.integer(2, 2, 3), "depth": S.num(10.0, 8.0, 13.0),
    "entry": S.enum("dressed", ENTRY), "door_at": S.integer(0, -2, 2),
}, "Two-storey hotel: side-gabled shingle roof with two dormers, a two-level veranda across the front (posts, upper "
   "gallery with railing, shed roof), a long blank sign board between the floors and rows of windows.",
   origin="lot_line")
def hotel(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    he, hr = 6.1, 8.2
    yf = 0.02
    pt = Parts()
    sec = [(0.0, 0.0), (d, 0.0), (d, he), (d / 2, hr), (0.0, he)]
    body = K.prism(sec, -w / 2 + 0.1, w / 2 - 0.1, "wall", role_top="wall", role_bottom="wall")
    A = np.asarray(body.v)
    body.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0] + yf, A[:, 1]], axis=1).tolist()]
    pt.add("body", body.orient_outward())
    slope = (hr - he) / (d / 2)
    ze = he - 0.35 * slope
    rsec = [(-0.35, ze - 0.14), (-0.35, ze), (d / 2, hr + 0.05), (d + 0.35, ze), (d + 0.35, ze - 0.14), (d / 2, hr - 0.18)]
    roof = K.prism(rsec, -w / 2 - 0.15, w / 2 + 0.15, "roof", role_top="trim", role_bottom="trim")
    A = np.asarray(roof.v)
    roof.v = [tuple(p) for p in np.stack([A[:, 2], A[:, 0] + yf, A[:, 1]], axis=1).tolist()]
    pt.add("roof", roof.orient_outward())
    for x in (-w * 0.25, w * 0.25):
        z0 = he + 0.05
        pt.add("dormers", B.gable_body(1.4, 1.6, 1.15, 1.75, "wall", y_front=yf + 0.55).translate(x, 0, z0))
        pt.add("dormer_roofs", B.gable_roof(1.4, 1.6, 1.15, 1.75, "roof", over_side=0.15, over_front=0.12, over_back=0.0, t=0.08,
                                            y_front=yf + 0.55).translate(x, 0, z0))
        pt.add("panes", B.card(x, yf + 0.538, z0 + 0.65, 0.62, 0.7, "screen"), "card")
    dx = door_x(span, P["door_at"])
    for x in (-w * 0.36, -w * 0.12, w * 0.12, w * 0.36):
        pt.win(x, 4.55, 0.75, 1.3, yf)
    xs_dn = [x for x in (-w * 0.33, 0.0, w * 0.33) if abs(x - dx) > 1.9]
    for x in xs_dn:
        pt.win(x, 1.7, 0.9, 1.4, yf)
    sign_board(pt, 0.0, 3.5, w * 0.62, 0.48, yf)
    entry(pt, dx, yf, P["entry"])
    yv = -1.85
    pt.add("veranda", B.plank_deck(-w / 2 + 0.05, w / 2 - 0.05, yv, yf - 0.02, 3.1, 0.15))
    for x in (-w / 2 + 0.3, -w / 6, w / 6, w / 2 - 0.3):
        if abs(x - dx) > 1.6:
            pt.add("veranda", B.sq_post(x, yv + 0.2, 0.0, 2.95, 0.17, "post"))
        pt.add("veranda", B.sq_post(x, yv + 0.2, 3.1, 5.85, 0.15, "post"))
    pt.add("veranda", B.railing(-w / 2 + 0.3, w / 2 - 0.3, yv + 0.2, 3.1, 0.9, 3, balusters=2, post_s=0.0))
    pt.add("veranda_roof", B.shed_roof(-w / 2, w / 2, yv - 0.15, yf - 0.02, 5.85, 6.15, "roof", t=0.1))
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=2)
    meta["bake_lights"] = window_lights(xs_dn + [dx], 1.7, yf, 0.55) + window_lights([-w * 0.12, w * 0.12], 4.45, yf, 0.3)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.church
@register("wtown.church", V, "building", {
    "span": S.integer(2, 2, 3), "depth": S.num(12.0, 9.0, 16.0),
}, "Frontier chapel: white-washed lap siding under a steep shingle roof, a square front tower with louvred belfry, a "
   "tapering spire crowned by a simple cross, pointed-arch windows and double doors at the top of three plank steps.",
   origin="lot_line")
def church(P, seed):
    span, d = P["span"], P["depth"]
    w = min(frontage(span), 7.6)
    he, hr = 4.6, 8.0
    tw = 2.4
    yt = 1.1 + tw / 2                      # tower centre: steps on the first 1.1 m behind the lot line
    yf = yt + tw / 2 - 0.3                 # nave front face (just behind the tower front)
    pt = Parts()
    pt.add("body", B.gable_body(w, d, he, hr, "trim", y_front=yf))
    pt.add("roof", B.gable_roof(w, d, he, hr, "roof", over_side=0.35, over_front=0.3, over_back=0.3, y_front=yf, end_role="trim"))
    pt.add("tower", B.chamfer(0.0, yt, 0.0, he + 3.3, tw, tw, 0.12, "trim", top="roof"))
    pt.add("belfry", B.chamfer(0.0, yt, he + 3.302, he + 5.0, tw * 0.82, tw * 0.82, 0.1, "trim", top="roof"))
    for k in range(4):
        c = B.card(0.0, -tw * 0.41 - 0.006, he + 4.15, 0.75, 1.15, "opening")
        pt.add("panes", c.rotate_z(k * math.pi / 2).translate(0.0, yt, 0.0), "card")
    pt.add("spire", K.lathe([(tw * 0.62, he + 5.002), (0.0, he + 8.4)], 4, "roof", smooth=False, start=math.pi / 4).translate(0.0, yt, 0.0))
    zc = he + 8.3
    pt.add("cross", B.timber((0.0, yt, zc), (0.0, yt, zc + 1.3), 0.12, 0.12, "metal", up=(0.0, 1.0, 0.0)))
    pt.add("cross_arm", B.timber((-0.4, yt, zc + 0.88), (0.4, yt, zc + 0.88), 0.11, 0.11, "metal"))
    for sx in (-1, 1):
        for k in range(3):
            yy = yf + d * (0.3 + 0.25 * k)
            fr = B.slab([(px, 1.2 + pz) for px, pz in K.opening2d("gothic", 1.0, 2.1, 8)], -0.04, 0.02, "trim")
            pn = B.card_poly([(px, 1.3 + pz) for px, pz in K.opening2d("gothic", 0.8, 1.9, 8)], -0.048, "screen")
            ang = -sx * math.pi / 2
            pt.add("windows", fr.rotate_z(ang).translate(sx * w / 2, yy, 0.0))
            pt.add("panes", pn.rotate_z(ang).translate(sx * w / 2, yy, 0.0), "card")
    yd = yt - tw / 2
    pt.add("trim", B.slab([(px, 0.6 + pz) for px, pz in K.opening2d("gothic", 1.7, 2.9, 8)], yd - 0.05, yd + 0.02, "wall"))
    for sx in (-1, 1):
        pt.add("panes", B.card(sx * 0.37, yd - 0.058, 1.65, 0.7, 2.0, "door"), "card")
    for i in range(3):
        dep = 0.36 * (3 - i)
        pt.add("steps", B.chamfer(0.0, yd - 0.06 - dep / 2 + 0.012 * i, 0.0, 0.2 * (i + 1), 2.2 - 0.06 * i, dep, 0.03, "wood", top="step"))
    return Asset(pt.nodes(), lot_meta(span, d, front_sockets(span), "dressed", storeys=1, landmark=True))


# ---------------------------------------------------------------- wtown.facade (false-front facades, 6 shapes)
@register("wtown.facade", V, "building", {
    "span": S.integer(1, 1, 2), "shape": S.enum("square", SHAPES), "wall_role": S.enum("wall", WALL_ROLES),
    "storeys": S.integer(1, 1, 2), "porch": S.boolean(False), "awning": S.boolean(False),
    "entry": S.enum("dressed", ENTRY), "door_at": S.integer(0, -1, 1),
}, "False-front shop facade on a shallow gabled body: shaped parapet (square / stepped / arched / gabled / pediment / "
   "tall), cornice, blank sign board, door and window(s), optional porch roof or striped awning; the cheap filler that "
   "makes a main street.", origin="lot_line")
def facade(P, seed):
    span = P["span"]
    w = frontage(span)
    two = P["storeys"] == 2
    d = 6.0
    he, hr = (6.0, 7.2) if two else (3.3, 4.4)
    h_wall = 6.4 if two else 4.3
    h_top = h_wall + (1.4 if P["shape"] != "square" else 0.0)
    yf = -0.12
    role = P["wall_role"]
    pt = Parts()
    pt.add("body", B.gable_body(w - 0.3, d, he, hr, role, y_front=0.02))
    pt.add("roof", B.gable_roof(w - 0.3, d, he, hr, "roof", over_side=0.22, over_front=0.0, y_front=0.02, sag=0.04))
    pt.add("front", B.slab(B.false_front_outline(w, h_wall, h_top, P["shape"]), yf, 0.0, "trim", front=role, back=role))
    pt.add("trim", B.cornice(-w / 2 - 0.04, w / 2 + 0.04, h_wall - 0.05, yf, depth=0.22, h=0.18, brackets=2 * span))
    sign_board(pt, 0.0, h_wall - 0.78, w * 0.7, 0.68, yf)
    corner_boards(pt, w, yf, h_wall - 0.25)
    if P["entry"] == "socket":
        dx = door_x(span, P["door_at"])
    else:
        dx = -0.8 if span == 1 else 2.0 * P["door_at"] - 0.4
    entry(pt, dx, yf, P["entry"], w=1.15, h=2.35)
    gap = 1.9 if P["entry"] == "socket" else 1.2
    xw = [x for x in ((-w * 0.28, w * 0.28) if span > 1 else (0.95,)) if abs(x - dx) > gap]
    for x in xw:
        pt.win(x, 1.75, 1.0 if span == 1 else 1.3, 1.5, yf)
    if two:
        for x in ((-w * 0.25, w * 0.25) if span > 1 else (0.0,)):
            pt.win(x, 4.45, 0.75, 1.25, yf, head=True)
    if P["porch"]:
        porch_roof(pt, -w / 2, w / 2, yf)
    elif P["awning"]:
        pt.add("awning", B.shed_roof(-w / 2 + 0.2, w / 2 - 0.2, -1.25, yf - 0.02, 2.6, 3.1, "band", t=0.05, end_role="band"))
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(dx))
    meta = lot_meta(span, d, socks, P["entry"], storeys=P["storeys"], shape=P["shape"])
    meta["bake_lights"] = window_lights(xw + [dx], 1.7, yf, 0.55)
    return Asset(pt.nodes(), meta)


# ---------------------------------------------------------------- wtown.shack
@register("wtown.shack", V, "building", {
    "size": S.num(4.0, 3.0, 5.0), "tin_roof": S.boolean(True), "porch": S.boolean(True),
}, "Homesteader's shack: a small board-and-batten cabin with a corrugated tin (or shingle) gable roof, a crooked "
   "stovepipe, one window, a plank door and a little porch on two posts.", origin="floor_center")
def shack(P, seed):
    s = P["size"]
    w, d = s, s * 0.9
    he, hr = 2.6, 3.6
    pt = Parts()
    pt.add("body", B.gable_body(w, d, he, hr, "body_alt", y_front=-d / 2))
    pt.add("roof", B.gable_roof(w, d, he, hr, "hull_alt" if P["tin_roof"] else "roof", over_side=0.3, over_front=0.9 if P["porch"] else 0.2,
                                over_back=0.2, y_front=-d / 2, t=0.08, sag=0.05))
    pt.add("panes", B.card(-w * 0.18, -d / 2 - 0.012, 1.0, 0.9, 2.0, "door"), "card")
    casing(pt, -w * 0.18, 0.9, 2.0, -d / 2)
    pt.win(w * 0.24, 1.55, 0.7, 0.75, -d / 2)
    pt.add("pipe", B.post(w * 0.28, d * 0.2, hr - 1.0, hr + 0.75, 0.09, "metal", sides=6, taper=1.0))
    pt.add("pipe_elbow", B.timber((w * 0.28, d * 0.2, hr + 0.78), (w * 0.28 + 0.3, d * 0.2, hr + 1.02), 0.13, 0.13, "metal"))
    if P["porch"]:
        for x in (-w / 2 + 0.2, w / 2 - 0.2):
            pt.add("porch", B.sq_post(x, -d / 2 - 0.75, 0.2, he - 0.3, 0.13, "post"))
        pt.add("porch_deck", B.plank_deck(-w / 2 + 0.1, w / 2 - 0.1, -d / 2 - 0.9, -d / 2 - 0.01, 0.2, 0.2))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], size=s))


# ---------------------------------------------------------------- wtown.water_tower
@register("wtown.water_tower", V, "structure", {
    "height": S.num(6.0, 4.5, 8.0, "deck height"), "spout": S.boolean(True),
}, "Water tower: a stave tank with a conical shingle cap on four splayed timber legs with X-bracing and girts, an "
   "octagonal deck, a side ladder and (optional) a hinged spout chute for the railroad.", origin="floor_center")
def water_tower(P, seed):
    h = P["height"]
    pt = Parts()
    b0, b1 = 1.9, 1.35

    def t(z):
        return b0 + (b1 - b0) * z / h
    hexa = [(0.13 * math.cos(a), 0.13 * math.sin(a)) for a in [math.pi / 6 + k * math.pi / 3 for k in range(6)]]
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("legs", B.section_beam((sx * b0, sy * b0, 0.0), (sx * b1, sy * b1, h - 0.01), hexa, "wood"))
    zl, zh = h * 0.1, h * 0.55
    for (ax, ay), (bx, by) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
        pt.add("bracing", B.beam((ax * t(zl), ay * t(zl), zl), (bx * t(zh), by * t(zh), zh), 0.09, 0.12, "wood", roll=45.0))
        pt.add("bracing_x", B.beam((bx * t(zl), by * t(zl), zl + 0.08), (ax * t(zh), ay * t(zh), zh + 0.08), 0.09, 0.12, "wood", roll=45.0))
        zg, k = h * 0.8, 0.07
        ga = (ax * t(zg) * (1 - k) + bx * t(zg) * k, ay * t(zg) * (1 - k) + by * t(zg) * k, zg)
        gb = (bx * t(zg) * (1 - k) + ax * t(zg) * k, by * t(zg) * (1 - k) + ay * t(zg) * k, zg)
        pt.add("girts", B.beam(ga, gb, 0.13, 0.13, "wood", roll=45.0))
    pt.add("deck", K.prism(K.circle2d(2.25, 8, start=math.pi / 8), h, h + 0.22, "wood", role_top="step"))
    pt.add("tank", K.lathe([(1.95, h + 0.222), (2.06, h + 1.6), (1.95, h + 3.0)], 10, "body_alt", smooth=True, cap_roles=("wood", "roof")))
    pt.add("cap", K.lathe([(2.28, h + 2.95), (0.0, h + 4.35)], 10, "roof", smooth=False))
    for zb, rb in ((h + 0.75, 2.065), (h + 2.35, 2.05)):
        pt.add("hoops", K.lathe([(rb, zb), (rb, zb + 0.1)], 8, "metal", smooth=False, start=math.pi / 8))
    for sx in (-1, 1):
        pt.add("ladder", B.beam((2.4, sx * 0.25, 0.0), (2.18, sx * 0.25, h + 0.25), 0.06, 0.06, "wood", roll=45.0))
    for k in range(5):
        z = 0.8 + k * (h - 0.8) / 5.0
        xr = 2.4 - 0.22 * z / (h + 0.25)
        pt.add("rungs", B.spindle((xr, -0.25, z), (xr, 0.25, z), 0.05, "wood"))
    if P["spout"]:
        pt.add("spout", B.section_beam((-1.9, 0.0, h + 0.75), (-3.2, 0.0, h - 0.3),
                                       [(-0.17, -0.06), (0.17, -0.06), (0.17, 0.08), (0.12, 0.0), (-0.12, 0.0), (-0.17, 0.08)], "hull_alt"))
        pt.add("rope", B.post(-3.15, 0.0, h - 1.5, h - 0.36, 0.025, "rope", sides=3, taper=1.0))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True))


# ---------------------------------------------------------------- wtown.boardwalk
@register("wtown.boardwalk", V, "structure", {
    "kind": S.enum("straight", ["straight", "end_w", "end_e", "steps", "ends"]),
}, "Raised plank boardwalk module along a lot line (4 m long, 2 m deep, 0.3 m high): painted planks over joist posts; "
   "end_w / end_e close one end with a plank step, steps adds a step down in front, ends closes both.",
   origin="lot_line")
def boardwalk(P, seed):
    L, D_, H = B.CELL, B.WALK_D, B.WALK_H
    kind = P["kind"]
    pt = Parts()
    pt.add("deck", B.chamfer(0.0, -D_ / 2, 0.0, H, L - 0.01, D_ - 0.02, 0.025, "wood", top="step"))
    for x in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):
        pt.add("joists", B.post(x, -D_ - 0.07, 0.0, H - 0.04, 0.07, "post", sides=6, taper=1.0))
    socks = []
    ends = {"straight": (), "end_w": ("w",), "end_e": ("e",), "steps": (), "ends": ("w", "e")}[kind]
    for side in ("w", "e"):
        sx = -1 if side == "w" else 1
        if side in ends:
            pt.add("steps", B.chamfer(sx * (L / 2 + 0.22), -D_ / 2, 0.0, H * 0.5, 0.42, D_ - 0.12, 0.03, "wood", top="step"))
        else:
            socks.append(B.sock("walk", (sx * L / 2, -D_ / 2, 0.0), side, depth_m=D_))
    if kind == "steps":
        pt.add("steps", B.chamfer(0.0, -D_ - 0.23, 0.0, H * 0.5, 1.6, 0.42, 0.03, "wood", top="step"))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [1, 1], socks, walk=True, deck_m=H))


# ---------------------------------------------------------------- wtown.porch
@register("wtown.porch", V, "arch", {
    "span": S.integer(1, 1, 2), "role": S.enum("roof", ["roof", "band", "hull_alt"]),
}, "Porch roof / awning over a boardwalk: a sloped plank (or striped canvas, or tin) roof from the facade to two or "
   "three posts at the boardwalk edge. Lot-line piece in front of a building frontage.", origin="lot_line")
def porch(P, seed):
    w = frontage(P["span"])
    pt = Parts()
    if P["role"] == "band":
        pt.add("roof", B.shed_roof(-w / 2, w / 2, -1.3, -0.14, 2.55, 3.05, "band", t=0.05, end_role="band"))
        for x in (-w / 2 + 0.1, w / 2 - 0.1):
            pt.add("rods", B.beam((x, -0.14, 2.62), (x, -1.25, 2.47), 0.03, 0.03, "metal", roll=45.0))
    else:
        porch_roof(pt, -w / 2, w / 2, -0.12, role=P["role"], posts=(-w / 2 + 0.25, w / 2 - 0.25) + ((0.0,) if P["span"] > 1 else ()))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [P["span"], 1], [B.sock("frontage_fit", (0, 0, 0), "n", span=P["span"])]))


# ---------------------------------------------------------------- wtown.balcony
@register("wtown.balcony", V, "arch", {
    "span": S.integer(1, 1, 2), "height": S.num(3.1, 2.8, 3.4),
}, "Upper balcony for a two-storey frontage: a plank deck on diagonal knee braces with a railing. Lot-line piece in "
   "front of the facade at the second-storey floor.", origin="lot_line")
def balcony(P, seed):
    w = frontage(P["span"]) - 0.3
    z = P["height"]
    pt = Parts()
    pt.add("deck", B.plank_deck(-w / 2, w / 2, -1.25, -0.14, z, 0.15))
    for x in (-w / 2 + 0.3, w / 2 - 0.3) + ((0.0,) if P["span"] > 1 else ()):
        pt.add("brackets", B.timber((x, -0.16, z - 1.05), (x, -1.1, z - 0.17), 0.11, 0.13, "wood", up=(1.0, 0.0, 0.0)))
    pt.add("railing", B.railing(-w / 2 + 0.1, w / 2 - 0.1, -1.15, z, 0.95, 2 * P["span"], balusters=2 if P["span"] == 1 else 1))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [P["span"], 1], [B.sock("balcony_fit", (0, 0, 0), "n", span=P["span"])]))


# ---------------------------------------------------------------- wtown.hitching_post
@register("wtown.hitching_post", V, "furniture", {
    "bays": S.integer(1, 1, 2),
}, "Hitching rail: rough hewn posts with a worn top rail and iron tie rings.", origin="floor_center")
def hitching_post(P, seed):
    n = P["bays"]
    L = 2.0 * n
    pt = Parts()
    for i in range(n + 1):
        x = -L / 2 + L * i / n
        pt.add("posts", B.post(x, 0.0, 0.0, 0.93, 0.085, "post", sides=5, taper=0.88, start=0.4 * i))
    pt.add("rail", B.timber((-L / 2 - 0.15, 0.0, 0.99), (L / 2 + 0.15, 0.0, 0.99), 0.12, 0.11, "rail"))
    for i in range(n):
        x = -L / 2 + L * (i + 0.5) / n
        pt.add("rings", K.torus(0.07, 0.016, 6, 4, "metal", smooth=False).rotate_x(math.pi / 2).translate(x, -0.08, 0.86))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up", interact="tie")]))


# ---------------------------------------------------------------- wtown.stairs
@register("wtown.stairs", V, "structure", {
    "rise": S.num(3.1, 1.5, 3.4, "landing height"), "width": S.num(1.1, 0.9, 1.6), "rail": S.boolean(True),
}, "Exterior or interior plank stair to a balcony or gallery: a solid sawtooth stair block (stringer profile on the "
   "sides) with an open handrail on posts.", origin="floor_center")
def stairs(P, seed):
    H, w = P["rise"], P["width"]
    n = max(4, int(round(H / 0.22)))
    run = 0.27
    pt = Parts()
    pt.add("treads", B.stair_block(w, n, H / n, run, "step", "wood", y_top=n * run / 2))
    if P["rail"]:
        y0, y1 = -n * run / 2 + 0.12, n * run / 2 - 0.12
        x = w / 2 + 0.07
        pt.add("rail_posts", B.sq_post(x, y0, 0.0, 1.1, 0.1, "post"))
        pt.add("rail_posts", B.sq_post(x, y1, 0.0, H + 1.0, 0.1, "post"))
        pt.add("rail", B.beam((x, y0, 0.98), (x, y1, H + 0.92), 0.07, 0.07, "rail", roll=45.0))
        for k in range(2, n - 1, 2):
            yk = y0 + (y1 - y0) * k / (n - 1)
            zr = 0.98 + (H - 0.06) * (yk - y0) / (y1 - y0)
            pt.add("spindles", B.spindle((x, yk, 0.02), (x, yk, zr - 0.05), 0.04, "rail"))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], rise_m=H))


# ---------------------------------------------------------------- wtown.doorway (arch.door)
@register("wtown.doorway", V, "arch", {
    "style": S.enum("frame", ["frame", "gate"]),
}, "Timber doorway frame on the door anchor (bound as arch.door): two chamfered posts, a heavy header beam with "
   "corbels and a threshold board, 2.4 x 3.0 m clear. Reads as a door casing on a facade, a ranch gate in a fence line "
   "and the timber set of a mine portal; 'gate' adds a blank hanging sign under the header.", origin="opening")
def doorway(P, seed):
    W, Hh = B.DOOR_W, B.DOOR_H
    yb, yf = B.FRAME_BACK, -B.FRAME_FRONT          # Blender: front (toward the room) is -Y
    yc = 0.5 * (yb + yf)
    dep = yb - yf
    pt = Parts()
    for sx in (-1, 1):
        pt.add("posts", B.chamfer(sx * (W / 2 + 0.13), yc, 0.0, Hh - 0.002, 0.26, dep, 0.04, "frame"))
    pt.add("header", B.chamfer(0.0, yc, Hh, Hh + 0.34, W + 0.9, dep + 0.04, 0.05, "frame"))
    for sx in (-1, 1):
        sec = [(sx * (W / 2 - 0.004), Hh - 0.32), (sx * (W / 2 - 0.004), Hh - 0.006), (sx * (W / 2 - 0.36), Hh - 0.006)]
        pt.add("corbels", B.slab(K.ccw(sec), yf + 0.04, yb - 0.04, "frame"))
    pt.add("sill", B.chamfer(0.0, yc - 0.02, 0.0, 0.05, W - 0.01, dep - 0.04, 0.02, "wood", top="step"))
    if P["style"] == "gate":
        c = 0.08
        o = [(-0.75 + c, Hh - 0.8), (0.75 - c, Hh - 0.8), (0.75, Hh - 0.8 + c), (0.75, Hh - 0.36 - c), (0.75 - c, Hh - 0.36),
             (-0.75 + c, Hh - 0.36), (-0.75, Hh - 0.36 - c), (-0.75, Hh - 0.8 + c)]
        pt.add("sign", B.slab(o, yf + 0.04, yf + 0.08, "trim"))
        pt.add("panes", B.card(0.0, yf + 0.034, Hh - 0.58, 1.36, 0.36, "knit"), "card")
        for sx in (-1, 1):
            pt.add("chains", B.post(sx * 0.6, yf + 0.06, Hh - 0.36, Hh - 0.33, 0.016, "metal", sides=4, taper=1.0))
    return Asset(pt.nodes(), B.grid_meta("door_anchor", None, [B.sock("door", (0, 0, 0), "n", fits="door", width_m=W, height_m=Hh)]))


# ---------------------------------------------------------------- wtown.fence
@register("wtown.fence", V, "structure", {
    "kind": S.enum("rails", ["rails", "picket", "gateway", "broken"]),
}, "Fence segment along one cell edge (4 m): ranch rails, a cemetery picket fence, a gateway (two tall posts and rail "
   "stubs around a 2.4 m gap that carries a door socket for road exits) or a broken run with a fallen rail.",
   origin="lot_line")
def fence(P, seed):
    k = P["kind"]
    L = B.CELL
    r = rng(seed, "wtown.fence", k)
    pt = Parts()
    socks = []
    y = -0.15
    if k in ("rails", "broken"):
        for i in range(3):
            x = -L / 2 + 0.1 + (L - 0.2) * i / 2
            pt.add("posts", B.post(x, y, 0.0, 1.35, 0.08, "post", sides=5, taper=0.85, start=0.3 * i))
        for j, z in enumerate((0.45, 0.85, 1.22)):
            if k == "broken" and j == 1:
                pt.add("rails", B.timber((-L / 2 + 0.25, y - 0.4, 0.06), (0.4, y - 0.72, 0.06), 0.1, 0.09, "rail"))
                continue
            pt.add("rails", B.timber((-L / 2 + 0.02, y - 0.12, z + 0.05 * r.random()), (L / 2 - 0.02, y - 0.12, z + 0.05 * r.random()),
                                     0.08, 0.11, "rail"))
    elif k == "picket":
        for x in (-L / 2 + 0.08, L / 2 - 0.08):
            pt.add("posts", B.post(x, y, 0.0, 1.2, 0.075, "post", sides=4, taper=0.9))
        for z in (0.3, 0.85):
            pt.add("rails", B.beam((-L / 2 + 0.05, y + 0.09, z), (L / 2 - 0.05, y + 0.09, z), 0.06, 0.06, "rail", roll=45.0))
        for i in range(9):
            x = -L / 2 + 0.4 + (L - 0.8) * i / 8
            o = [(x - 0.05, 0.05), (x + 0.05, 0.05), (x + 0.05, 1.0), (x, 1.1), (x - 0.05, 1.0)]
            pt.add("pickets", B.slab(o, y - 0.01, y + 0.02, "trim"))
    else:
        g = B.DOOR_W / 2 + 0.3
        for sx in (-1, 1):
            pt.add("posts", B.post(sx * (L / 2 - 0.1), y, 0.0, 1.35, 0.08, "post", sides=5, taper=0.85))
            for z in (0.5, 1.15):
                pt.add("rails", B.timber((sx * g, y - 0.12, z), (sx * (L / 2 - 0.02), y - 0.12, z), 0.08, 0.11, "rail"))
        socks.append(B.sock("door", (0.0, B.ANCHOR_BACK, 0.0), "n", width_m=B.DOOR_W, height_m=B.DOOR_H, needs="wtown.doorway",
                            exit=True))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [1, 1], socks, kind=k))


# ---------------------------------------------------------------- interiors: wtown.room / wtown.gallery
DOOR_ITEM = {"side": S.enum("s", SIDES), "cell": S.integer(0, 0, 5)}
WIN_ITEM = {"side": S.enum("n", SIDES), "cell": S.integer(0, 0, 5),
            "level": S.integer(0, 0, 1, "storey: 0 ground, 1 upper (rooms 5.8 m and taller)")}
LAMP_ITEM = {"side": S.enum("n", SIDES), "cell": S.integer(0, 0, 5)}
SHEET_YAW = {"n": 0.0, "e": -90.0, "s": 180.0, "w": 90.0}
CUT_W, CUT_H = 2.8, 3.2


def interior_profile(H):
    """Interior wall cross-section bottom -> top: baseboard, plank wainscot under a chair rail, papered wall, crown
    board. Extra rows on the paper give the baked light vertices to work with."""
    p = [(0.0, 0.04, "trim"), (0.22, 0.04, "trim"), (0.22, 0.0, "body_alt"), (1.05, 0.0, "body_alt"),
         (1.05, 0.05, "trim"), (1.15, 0.05, "trim"), (1.15, 0.0, "quilt")]
    z = 1.15 + 1.25
    while z < H - 0.7:
        p.append((round(z, 3), 0.0, "quilt"))
        z += 1.25
    p += [(H - 0.3, 0.0, "quilt"), (H - 0.3, 0.08, "trim"), (H, 0.08, "trim")]
    return tuple(p)


def side_sheet(side, hx, hy, s0, s1, **kw):
    L = s1 - s0
    shift = [(o[0] - s0, o[1] - s0) + tuple(o[2:]) for o in kw.pop("openings", ())]
    m = D.wall_sheet(L, openings=shift, extra_z=(), **kw)
    if side == "n":
        m.translate(s0 - hx, hy, 0)
    elif side == "s":
        m.rotate_z(math.pi).translate(hx - s0, -hy, 0)
    elif side == "e":
        m.rotate_z(-math.pi / 2).translate(hx, hy - s0, 0)
    else:
        m.rotate_z(math.pi / 2).translate(-hx, s0 - hy, 0)
    return m


def side_point(side, hx, hy, s, out=0.0, z=0.0):
    if side == "n":
        return (s - hx, hy - out, z)
    if side == "s":
        return (hx - s, -hy + out, z)
    if side == "e":
        return (hx - out, hy - s, z)
    return (-hx + out, s - hy, z)


@register("wtown.room", V, "shell", {
    "cells_x": S.integer(3, 1, 4), "cells_y": S.integer(3, 1, 4),
    "height": S.num(4.2, 3.2, 6.4),
    "doors": S.array(DOOR_ITEM, [{"side": "s", "cell": 1}], 6, "door cuts on cell-edge midpoints"),
    "windows": S.array(WIN_ITEM, [], 8, "window views on wall cells (painted desert view in a trim frame)"),
    "lamps": S.array(LAMP_ITEM, [], 8, "wall lamp sockets (wprop.lantern wall mount)"),
    "ceiling": S.enum("beams", ["none", "flat", "beams"]),
}, "Frontier interior shell on the 4 m grid: one-sided walls with a baseboard, plank wainscot under a chair rail, "
   "papered upper walls and a crown board, a plank floor, a plank ceiling with chamfered beams, door cuts on cell-edge "
   "midpoints for the timber doorway frame, painted window views and wall lamp sockets.", origin="room_floor")
def room(P, seed):
    cx_, cy_ = P["cells_x"], P["cells_y"]
    H = P["height"]
    W, Dd = cx_ * B.CELL, cy_ * B.CELL
    hx, hy = W / 2 - B.WALL_T, Dd / 2 - B.WALL_T
    span = {"n": 2 * hx, "s": 2 * hx, "e": 2 * hy, "w": 2 * hy}
    ncell = {"n": cx_, "s": cx_, "e": cy_, "w": cy_}
    doors = {(d["side"], d["cell"]) for d in P["doors"]}
    wins = {(d["side"], d["cell"]) for d in P["windows"] if d["level"] == 0}
    upper = {(d["side"], d["cell"]) for d in P["windows"] if d["level"] == 1}
    lamps = {(d["side"], d["cell"]) for d in P["lamps"]}
    for s_, c_ in doors | wins | upper | lamps:
        if c_ >= ncell[s_]:
            raise ValueError("socket %s%d outside a %dx%d room" % (s_, c_, cx_, cy_))
    if doors & wins:
        raise ValueError("a wall cell cannot carry both a door and a window")
    if upper and H < 5.8:
        raise ValueError("upper-storey windows need a room at least 5.8 m tall")
    if wins & lamps:
        raise ValueError("a wall cell cannot carry both a ground window and a wall lamp")
    prof = interior_profile(H)
    pt = Parts()
    walls = K.Mesh()
    socks, lights = [], []
    for side in SIDES:
        L = span[side]
        ext = B.WALL_T if side in ("n", "s") else 0.0
        nat = (lambda t: t) if side in ("n", "e") else (lambda t, L=L: L - t)
        cuts = []
        for i in range(ncell[side]):
            mid = nat(4.0 * i + 2.0 - B.WALL_T)
            if (side, i) in doors:
                cuts.append((mid - CUT_W / 2, mid + CUT_W / 2, CUT_H))
                p = side_point(side, hx, hy, mid, out=-(B.WALL_T + B.ANCHOR_BACK))
                socks.append(B.sock("door", p, side, cell=i, side=side, width_m=B.DOOR_W, height_m=B.DOOR_H, needs="wtown.doorway"))
                # Painted street depth beyond a traversable doorway; do not expose the runtime void.
                q = side_point(side, hx, hy, mid, out=-0.3)
                depth = B.card(0.0, 0.0, CUT_H / 2, CUT_W + 0.2, CUT_H + 0.1, "view")
                pt.add("door_views", depth.rotate_z(math.radians(SHEET_YAW[side])).translate(q[0], q[1], 0.0), "card")
            elif (side, i) in wins:
                q = side_point(side, hx, hy, mid)
                f, pn = B.window(0.0, 1.95, 1.1, 1.3, 0.0, pane_role="view", frame_role="trim")
                yaw = math.radians(SHEET_YAW[side])
                pt.add("windows", f.rotate_z(yaw).translate(q[0], q[1], 0.0))
                pt.add("views", pn.rotate_z(yaw).translate(q[0], q[1], 0.0), "card")
            if (side, i) in upper:
                q = side_point(side, hx, hy, mid)
                f, pn = B.window(0.0, 1.95 + B.STOREY, 1.1, 1.3, 0.0, pane_role="view", frame_role="trim")
                yaw = math.radians(SHEET_YAW[side])
                pt.add("windows", f.rotate_z(yaw).translate(q[0], q[1], 0.0))
                pt.add("views", pn.rotate_z(yaw).translate(q[0], q[1], 0.0), "card")
            if (side, i) in lamps:
                sl = mid if (side, i) not in doors else mid + 1.9
                q = side_point(side, hx, hy, sl)
                socks.append(B.sock("lamp", q, side, cell=i, side=side, mount_height_m=2.3))
                lights.append(B.light(side_point(side, hx, hy, sl, out=0.45, z=2.3), 3.4, 0.55))
        walls.merge(side_sheet(side, hx, hy, -ext, L + ext, profile=prof, openings=cuts, top_cap=B.WALL_T,
                               cap_trim=(0.0, 0.0) if ext else (B.WALL_T + 0.005, B.WALL_T + 0.005)))
    floor = D.floor_grid(-hx, -hy, hx, hy, 0.0, 2.0, "floor")
    nodes_shell = [Node("floor", floor, "shell"), Node("walls", walls, "shell")]
    if P["ceiling"] != "none":
        nodes_shell.append(Node("ceiling", D.flat_ceiling(-hx - 0.002, -hy - 0.002, hx + 0.002, hy + 0.002, H, 2.0, "ceiling"), "shell"))
        if P["ceiling"] == "beams":
            along_y = W <= Dd
            n = int(round((Dd if along_y else W) / 2.0))
            for k in range(1, n):
                t = -((Dd if along_y else W) / 2) + 2.0 * k
                if along_y:
                    pt.add("beams", B.chamfer(0.0, t, H - 0.3, H - 0.004, 2 * hx - 0.02, 0.26, 0.05, "wood"))
                else:
                    pt.add("beams", B.chamfer(t, 0.0, H - 0.3, H - 0.004, 0.26, 2 * hy - 0.02, 0.05, "wood"))
    meta = B.grid_meta("cell_block_centre", [cx_, cy_], socks, bake_lights=lights, height_m=H,
                       plot_m=[W + 1.0, Dd + 1.0], interior_m=[2 * hx, 2 * hy],
                       door_positions={"%s%d" % (s_, c_): 4 * c_ + 2 for s_, c_ in sorted(doors)},
                       note="room plot = cells x 4 m + 0.5 m apron each side; place the shell at the plot centre; a door on "
                            "side/cell i has door.position = 4*i + 2 (room.gd door anchor)")
    return Asset(nodes_shell + pt.nodes(), meta)


@register("wtown.gallery", V, "structure", {
    "span": S.integer(3, 2, 4), "depth": S.num(2.4, 1.8, 3.0), "height": S.num(3.0, 2.8, 3.4),
    "stair_gap": S.enum("e", ["none", "e", "w"]),
}, "Interior gallery (mezzanine) along a wall: a plank floor on posts at the upper storey with a railing along the "
   "front; a gap in the railing at one end meets a wtown.stairs flight. Origin on the room's inner wall line.",
   origin="lot_line")
def gallery(P, seed):
    w = P["span"] * B.CELL - 2 * B.WALL_T - 0.04
    dep, z = P["depth"], P["height"]
    y0 = -0.01
    yf = y0 - dep
    pt = Parts()
    pt.add("deck", B.plank_deck(-w / 2, w / 2, yf, y0, z, 0.22))
    nposts = P["span"] + 1
    for i in range(nposts):
        x = -w / 2 + 0.25 + (w - 0.5) * i / (nposts - 1)
        pt.add("posts", B.sq_post(x, yf + 0.18, 0.0, z - 0.222, 0.2, "post"))
        pt.add("braces", B.beam((x, yf + 0.3, z - 0.95), (x, y0 - 0.04, z - 0.25), 0.1, 0.1, "wood", up=(1.0, 0.0, 0.0), roll=45.0))
    x0, x1 = -w / 2 + 0.1, w / 2 - 0.1
    if P["stair_gap"] == "e":
        x1 -= 1.3
    elif P["stair_gap"] == "w":
        x0 += 1.3
    pt.add("railing", B.railing(x0, x1, yf + 0.08, z, 0.95, P["span"], balusters=2))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [P["span"], 1], [B.sock("gallery", (0.0, 0.0, 0.0), "n", span=P["span"])],
                                         height_m=z))
