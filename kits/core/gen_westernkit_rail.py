"""WESTERNKIT rail and mine family (wrail.*, wmine.*), theme-agnostic, on the FRONTIER GRID.

Track pieces join on `track` sockets at cell-edge midpoints (origin on the start cell centre): straight 4 m, curve
R = 6 m (a 2 x 2 block, start (0, -2) heading north, end (6, 4) heading east, glTF x/z), buffer stop and road crossing;
mine track is 0.6 m gauge with a 2 m radius cell corner. Mine tunnels run on cell centres with a 3 m clear passage
(one-sided rough rock walls 0.5 m in from the cell edges, a rock ceiling at 3.2 m, timber sets every 2 m).
The mine portal is a one-sided cliff face with a cut opening on a door socket (the runtime frame = wtown.doorway).
Wheels are painted discs (role ice = painted spoked wheel) with a rim band.
"""
import math

from . import meshkit as K
from . import schema as S
from .asset import Asset, register
from . import gen_westernkit_base as B
from .gen_westernkit_town import Parts, frontage, door_socket, sign_board, porch_roof, entry, lot_meta, front_sockets
from .genutil import finalize
from .rng import rng

V = "1.0.0"
TIE_Z = 0.16        # tie top above the floor datum (ballast + tie)
RAIL_SEC = [(-0.045, 0.0), (0.045, 0.0), (0.028, 0.12), (-0.028, 0.12)]
BALLAST_SEC = [(-1.45, -0.002), (1.45, -0.002), (1.05, 0.06), (-1.05, 0.06)]
MINE_BALLAST = [(-0.75, -0.002), (0.75, -0.002), (0.55, 0.04), (-0.55, 0.04)]


def track_path(kind, n=8):
    """Plan centre line (Blender x, y) of a standard track piece."""
    if kind == "curve":
        return B.arc_path(6.0, -2.0, 6.0, math.pi, math.pi / 2, n)
    return [(0.0, -2.0, 0.0), (0.0, 2.0, 0.0)]


def lay_track(pt, path, gauge, tie_len, tie_step, ballast=True, sec_b=BALLAST_SEC, tie_w=0.22, tie_h=0.1, ballast_role="dirt"):
    """Ballast berm, sleepers and two rails along a plan path (list of (x, y, 0)). The main line rides a sunlit
    dirt berm (role path); mine track sits in the drift's trodden dirt (role dirt)."""
    import numpy as np
    Pp = [np.asarray(p, dtype=float) for p in path]
    zb = sec_b[2][1]
    if ballast:
        pt.add("ballast", B.sweep(path, sec_b, ballast_role))
    seg = [float(np.linalg.norm(Pp[i + 1] - Pp[i])) for i in range(len(Pp) - 1)]
    L = sum(seg)
    nt = max(2, int(round(L / tie_step)))
    for k in range(nt):
        d = (k + 0.5) * L / nt
        acc = 0.0
        p, tg = Pp[0], (Pp[1] - Pp[0]) / max(seg[0], 1e-9)
        for i, sl in enumerate(seg):
            if acc + sl >= d - 1e-9:
                t = (d - acc) / sl
                p = Pp[i] + (Pp[i + 1] - Pp[i]) * t
                tg = (Pp[i + 1] - Pp[i]) / sl
                break
            acc += sl
        sd = np.array([tg[1], -tg[0], 0.0])
        a = p + sd * tie_len / 2 + np.array([0, 0, zb + tie_h / 2])
        b = p - sd * tie_len / 2 + np.array([0, 0, zb + tie_h / 2])
        c = min(0.03, tie_h * 0.3)
        sec = [(-tie_w / 2, -tie_h / 2), (tie_w / 2, -tie_h / 2), (tie_w / 2, tie_h / 2 - c), (tie_w / 2 - c, tie_h / 2),
               (-tie_w / 2 + c, tie_h / 2), (-tie_w / 2, tie_h / 2 - c)]
        pt.add("ties", B.section_beam(tuple(a), tuple(b), sec, "wood"))
    zr = zb + tie_h
    for sx in (-1, 1):
        rp = []
        for i, p in enumerate(Pp):
            if i == 0:
                tg = Pp[1] - Pp[0]
            elif i == len(Pp) - 1:
                tg = Pp[-1] - Pp[-2]
            else:
                tg = Pp[i + 1] - Pp[i - 1]
            tg = tg / np.linalg.norm(tg)
            sd = np.array([tg[1], -tg[0], 0.0])
            rp.append(tuple(p + sd * sx * gauge / 2 + np.array([0, 0, zr])))
        pt.add("rails", B.sweep(rp, RAIL_SEC, "metal"))
    return zr + 0.12


def track_sockets(kind, mine=False):
    if kind == "curve":
        return [B.sock("track", (0.0, -2.0, 0.0), "s", gauge_m=B.MINE_GAUGE if mine else B.RAIL_GAUGE),
                B.sock("track", (6.0, 4.0, 0.0), "e", gauge_m=B.MINE_GAUGE if mine else B.RAIL_GAUGE)]
    if kind == "corner":
        return [B.sock("track", (0.0, -2.0, 0.0), "s", gauge_m=B.MINE_GAUGE), B.sock("track", (2.0, 0.0, 0.0), "e", gauge_m=B.MINE_GAUGE)]
    out = [B.sock("track", (0.0, -2.0, 0.0), "s", gauge_m=B.MINE_GAUGE if mine else B.RAIL_GAUGE)]
    if kind not in ("bumper", "end"):
        out.append(B.sock("track", (0.0, 2.0, 0.0), "n", gauge_m=B.MINE_GAUGE if mine else B.RAIL_GAUGE))
    return out


# ================================================================ RAIL
@register("wrail.track", V, "structure", {
    "kind": S.enum("straight", ["straight", "curve", "bumper", "crossing"]),
}, "Standard-gauge track on a ballast berm: straight 4 m cell, 90 degree curve of 6 m radius over a 2 x 2 block, a "
   "timber buffer stop, or a road crossing (plank fill between and beside the rails). Joins on track sockets at "
   "cell-edge midpoints.", origin="cell_centre")
def track(P, seed):
    kind = P["kind"]
    pt = Parts()
    path = track_path(kind)
    zr = lay_track(pt, path, B.RAIL_GAUGE, 2.3, 0.85 if kind == "curve" else 0.78, ballast_role="path")
    if kind == "bumper":
        y = 1.2
        for sx in (-1, 1):
            pt.add("bumper", B.timber((sx * 0.55, y - 0.9, TIE_Z), (sx * 0.55, y, 0.95), 0.2, 0.2, "wood", up=(1.0, 0.0, 0.0)))
            pt.add("bumper", B.sq_post(sx * 0.55, y, 0.0, 1.0, 0.24, "post"))
        pt.add("bumper", B.timber((-0.95, y - 0.12, 0.85), (0.95, y - 0.12, 0.85), 0.26, 0.3, "band"))
    if kind == "crossing":
        for x0, x1 in ((-1.25, -0.62), (-0.48, 0.48), (0.62, 1.25)):
            pt.add("planks", B.chamfer((x0 + x1) / 2, 0.0, TIE_Z, zr + 0.1, x1 - x0, 3.2, 0.03, "wood", top="step"))
    return Asset(pt.nodes(), B.grid_meta("cell_centre", [2, 2] if kind == "curve" else [1, 1], track_sockets(kind), kind=kind))


@register("wrail.platform", V, "structure", {
    "kind": S.enum("straight", ["straight", "end_w", "end_e"]),
}, "Station platform module (4 m): a raised plank deck with a timber edge beam on posts, end ramp on end pieces. "
   "Lot-line piece joining end to end on walk sockets, the track runs along its front.", origin="lot_line")
def platform(P, seed):
    L, Dp, H = B.CELL, 2.5, 0.75
    pt = Parts()
    pt.add("deck", B.chamfer(0.0, -Dp / 2, H - 0.12, H, L - 0.01, Dp - 0.02, 0.03, "wood", top="step"))
    for x in (-L / 2 + 0.25, 0.0, L / 2 - 0.25):
        for y in (-Dp + 0.2, -0.25):
            pt.add("posts", B.post(x, y, 0.0, H - 0.12, 0.09, "post", sides=6, taper=1.0))
    pt.add("edge", B.timber((-L / 2 + 0.01, -Dp + 0.05, H - 0.24), (L / 2 - 0.01, -Dp + 0.05, H - 0.24), 0.14, 0.22, "frame"))
    socks = []
    for side, sx in (("w", -1), ("e", 1)):
        if P["kind"] == "end_" + side:
            ramp = [(sx * L / 2, 0.0), (sx * (L / 2 + 1.6), 0.0), (sx * L / 2, H - 0.002)]
            pt.add("ramp", B.slab(K.ccw(ramp), -Dp + 0.02, -0.02, "wood", front="wood", back="wood"))
        else:
            socks.append(B.sock("walk", (sx * L / 2, -1.0, 0.0), side, depth_m=Dp))
    return Asset(pt.nodes(), B.grid_meta("lot_line", [1, 1], socks, deck_m=H))


@register("wrail.station", V, "building", {
    "span": S.integer(3, 2, 3), "depth": S.num(6.0, 5.0, 8.0), "entry": S.enum("dressed", ["dressed", "socket"]),
}, "Small frontier depot: a board-and-batten building under a low gable with deep overhanging eaves on knee braces "
   "over the platform, a projecting telegrapher's bay window, a ticket window, a plank door, a blank station-name "
   "board on the gable and a raised plank platform along the front.", origin="lot_line")
def station(P, seed):
    span, d = P["span"], P["depth"]
    w = frontage(span)
    he, hr = 3.6, 5.6
    yf = 0.02
    pt = Parts()
    pt.add("body", B.gable_body(d, w - 0.4, he, hr, "body_alt", y_front=-(w - 0.4) / 2).rotate_z(math.pi / 2).translate(0, yf + d / 2, 0))
    rf = B.gable_roof(d, w - 0.4, he, hr, "roof", over_side=1.9, over_front=0.6, over_back=0.6, y_front=-(w - 0.4) / 2, t=0.14)
    pt.add("roof", rf.rotate_z(math.pi / 2).translate(0, yf + d / 2, 0))
    for x in (-w * 0.36, -w * 0.12, w * 0.12, w * 0.36):
        pt.add("braces", B.timber((x, yf - 0.02, 2.3), (x, yf - 1.6, he - 0.08), 0.12, 0.14, "wood", up=(1.0, 0.0, 0.0)))
    bay = B.chamfer(-w * 0.12, yf - 0.4, 0.0, 3.2, 2.0, 0.8, 0.35, "body_alt", top="roof")
    pt.add("bay", bay)
    pt.win(-w * 0.12, 1.75, 0.8, 1.3, yf - 0.8, frame_role="trim")
    entry(pt, w * 0.2 if P["entry"] == "dressed" else 2.0 * round(w * 0.2 / 2.0), yf, P["entry"], w=1.15, h=2.4)
    pt.win(-w * 0.36, 1.7, 0.85, 1.3, yf)
    pt.win(w * 0.4, 1.7, 0.7, 1.1, yf)
    gsign = Parts()
    sign_board(gsign, 0.0, 4.6, 1.9, 0.48, 0.0)
    for name, kind in gsign.order:
        m = gsign.meshes[(name, kind)]
        m.rotate_z(math.pi / 2).translate(w / 2 - 0.2, yf + d / 2, 0)
        pt.add(name, m, kind)
    pt.add("deck", B.chamfer(0.0, -1.05, 0.0, 0.15, w + 0.4, 2.1, 0.04, "wood", top="step"))
    pt.add("chimney", B.chamfer(w * 0.18, yf + d * 0.55, hr - 1.0, hr + 0.9, 0.55, 0.55, 0.06, "stone", top="metal"))
    socks = front_sockets(span)
    if P["entry"] == "socket":
        socks.append(door_socket(2.0 * round(w * 0.2 / 2.0)))
    meta = lot_meta(span, d, socks, P["entry"], storeys=1)
    meta["bake_lights"] = [B.light((-w * 0.12, yf - 1.6, 1.6), 2.8, 0.55)]
    return Asset(pt.nodes(), meta)


@register("wrail.handcar", V, "vehicle", {
    "pumped": S.num(0.0, -1.0, 1.0, "lever tilt (-1..1)"),
}, "Pump handcar: a plank deck on four small painted wheels with a timber frame, a central A-frame and a see-saw "
   "pump lever with cross handles at both ends.", origin="floor_center")
def handcar(P, seed):
    pt = Parts()
    zr = TIE_Z + 0.12
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("wheels", B.wheel(sx * B.RAIL_GAUGE / 2, sy * 0.62, zr + 0.3, 0.3, 0.07, axis="x", sides=10))
    pt.add("frame", B.chamfer(0.0, 0.0, zr + 0.42, zr + 0.6, 1.5, 2.1, 0.06, "wood", top="step"))
    for sx in (-1, 1):
        pt.add("aframe", B.timber((sx * 0.32, -0.2, zr + 0.6), (0.0, 0.0, zr + 1.45), 0.09, 0.09, "wood", up=(0.0, 1.0, 0.0)))
        pt.add("aframe", B.timber((sx * 0.32, 0.2, zr + 0.6), (0.0, 0.0, zr + 1.45), 0.09, 0.09, "wood", up=(0.0, 1.0, 0.0)))
    tilt = P["pumped"] * 0.25
    a = (0.0, -1.0, zr + 1.5 + tilt)
    b = (0.0, 1.0, zr + 1.5 - tilt)
    pt.add("lever", B.timber(a, b, 0.08, 0.1, "metal"))
    for p in (a, b):
        pt.add("handles", B.timber((-0.38, p[1], p[2]), (0.38, p[1], p[2]), 0.06, 0.06, "wood"))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up", rides="track")]))


@register("wrail.trestle", V, "structure", {
    "height": S.num(4.0, 2.0, 8.0, "rail height above the ground datum"),
    "kind": S.enum("span", ["span", "end"]),
}, "Timber trestle bridge module (4 m): a bent of four battered posts with cap, sill and X-bracing under a deck of "
   "stringers, sleepers and rails with guard timbers; modules join on track sockets, 'end' adds a cribbed log abutment.",
   origin="cell_centre")
def trestle(P, seed):
    h = P["height"]
    pt = Parts()
    zd = h - 0.28

    def bent(y):
        xs = [(-1.6, -0.95), (-0.45, -0.45), (0.45, 0.45), (1.6, 0.95)]
        hexa = [(0.11 * math.cos(a), 0.11 * math.sin(a)) for a in [math.pi / 6 + k * math.pi / 3 for k in range(6)]]
        for xb, xt in xs:
            pt.add("bents", B.section_beam((xb, y, 0.0), (xt, y, zd - 0.3), hexa, "wood"))
        pt.add("caps", B.timber((-1.25, y, zd - 0.18), (1.25, y, zd - 0.18), 0.26, 0.24, "wood"))
        pt.add("sills", B.timber((-1.85, y, 0.12), (1.85, y, 0.12), 0.24, 0.24, "wood"))
        pt.add("braces", B.beam((-1.45, y + 0.14, 0.4), (1.0, y + 0.14, zd - 0.45), 0.08, 0.16, "wood", roll=45.0))
        pt.add("braces", B.beam((1.45, y - 0.14, 0.4), (-1.0, y - 0.14, zd - 0.45), 0.08, 0.16, "wood", roll=45.0))
    bent(-2.0 + 0.15)
    if P["kind"] == "end":
        # abutment: a cribbed log pier closing the far end
        pt.add("crib", B.chamfer(0.0, 2.0 - 0.7, 0.0, zd - 0.12, 3.2, 1.3, 0.25, "bark", top="wood"))
    for sx in (-1, 1):
        pt.add("stringers", B.timber((sx * 0.55, -2.0, zd - 0.06 - 0.06), (sx * 0.55, 2.0, zd - 0.06 - 0.06), 0.25, 0.12, "wood"))
    pt2 = Parts()
    lay_track(pt2, [(0.0, -2.0, 0.0), (0.0, 2.0, 0.0)], B.RAIL_GAUGE, 2.6, 0.6, ballast=False, sec_b=[(0, 0), (0, 0), (0, 0.0), (0, 0)])
    for name, kind in pt2.order:
        pt.add(name, pt2.meshes[(name, kind)].translate(0.0, 0.0, zd), kind)
    for sx in (-1, 1):
        pt.add("guards", B.beam((sx * 1.18, -2.0, zd + 0.15), (sx * 1.18, 2.0, zd + 0.15), 0.13, 0.13, "wood", roll=45.0))
    socks = [B.sock("track", (0.0, -2.0, 0.0), "s", deck_m=h - 0.0), B.sock("track", (0.0, 2.0, 0.0), "n", deck_m=h)]
    for s in socks:
        s["position"][1] = 0.0
    return Asset(pt.nodes(), B.grid_meta("cell_centre", [1, 1], socks, rail_height_m=round(zd + 0.22, 3)))


@register("wrail.signal", V, "structure", {
    "arm": S.enum("stop", ["stop", "clear"]),
}, "Semaphore signal: a tapered timber mast with a ladder, a painted arm on a pivot, a lamp box with a lit lens and "
   "a finial cap.", origin="floor_center")
def signal(P, seed):
    pt = Parts()
    H = 5.2
    pt.add("mast", B.post(0.0, 0.0, 0.0, H, 0.16, "post", sides=6, taper=0.7))
    pt.add("cap", K.lathe([(0.13, H - 0.002), (0.0, H + 0.35)], 6, "metal", smooth=False))
    pt.add("base", B.chamfer(0.0, 0.0, 0.0, 0.3, 0.7, 0.7, 0.12, "stone"))
    ang = 0.0 if P["arm"] == "stop" else math.radians(40)
    L = 1.5
    x1, z1 = 0.15 + L * math.cos(ang), H - 0.7 + L * math.sin(ang)
    pt.add("arm", B.section_beam((0.12, -0.14, H - 0.7), (x1, -0.14, z1), [(-0.03, -0.11), (0.03, -0.11), (0.03, 0.11), (-0.03, 0.11)],
                                 "band", up=(0.0, -1.0, 0.0)))
    pt.add("lamp", B.chamfer(0.0, -0.22, H - 1.25, H - 0.85, 0.32, 0.28, 0.05, "metal"))
    pt.add("lens", B.card(0.0, -0.37, H - 1.05, 0.16, 0.16, "light"), "card")
    for k in range(7):
        z = 0.5 + k * 0.62
        pt.add("ladder", B.spindle((-0.32, 0.16, z), (0.32, 0.16, z), 0.04, "metal"))
    for sx in (-1, 1):
        pt.add("ladder", B.beam((sx * 0.3, 0.16, 0.3), (sx * 0.3, 0.16, H - 1.3), 0.04, 0.04, "metal", roll=45.0))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wrail.car", V, "vehicle", {
    "kind": S.enum("boxcar", ["boxcar", "flatcar", "caboose"]),
}, "Freight car on two four-wheel trucks: a board-and-batten boxcar with a curved roof and sliding door, a flatcar "
   "with stake pockets and a lashed load, or a caboose with a rooftop cupola and end platforms.", origin="floor_center")
def car(P, seed):
    kind = P["kind"]
    pt = Parts()
    zr = TIE_Z + 0.12
    L, W = 7.2, 2.3
    zf = zr + 0.75
    for sy in (-1, 1):
        for ay in (-0.55, 0.55):
            for sx in (-1, 1):
                pt.add("wheels", B.wheel(sx * B.RAIL_GAUGE / 2, sy * (L / 2 - 1.2) + ay, zr + 0.34, 0.34, 0.08, sides=8))
        gy = sy * (L / 2 - 1.2)
        pt.add("trucks", B.board(-(B.RAIL_GAUGE + 0.25) / 2, (B.RAIL_GAUGE + 0.25) / 2, gy - 0.8, gy + 0.8, zr + 0.3, zr + 0.6, "metal", ch=0.1))
    pt.add("frame", B.board(-W / 2, W / 2, -L / 2, L / 2, zf - 0.15, zf, "wood", ch=0.06, top="step"))
    if kind == "boxcar":
        hb = 2.4
        pt.add("body", B.chamfer(0.0, 0.0, zf, zf + hb, W - 0.06, L - 0.06, 0.05, "wall_alt", top="roof"))
        sec = [(-W / 2 - 0.08, 0.0), (W / 2 + 0.08, 0.0), (W / 2 + 0.08, 0.06), (W * 0.3, 0.2), (0.0, 0.24), (-W * 0.3, 0.2), (-W / 2 - 0.08, 0.06)]
        pt.add("roof", B.slab([(x, z + zf + hb + 0.002) for x, z in sec], -L / 2 - 0.08, L / 2 + 0.08, "roof"))
        for sx in (-1, 1):
            c = B.card(0.0, -0.004, zf + 1.1, 1.8, 2.0, "door").rotate_z(sx * math.pi / 2 if sx < 0 else -math.pi / 2)
            pt.add("doors", c.translate(sx * (W / 2 - 0.03 + 0.0), 0.0, 0.0), "card")
            pt.add("door_track", B.timber((sx * (W / 2 - 0.01), -1.2, zf + 2.18), (sx * (W / 2 - 0.01), 1.2, zf + 2.18), 0.06, 0.08, "metal"))
    elif kind == "flatcar":
        for k in range(4):
            y = -L / 2 + 0.4 + k * (L - 0.8) / 3
            for sx in (-1, 1):
                pt.add("stakes", B.post(sx * (W / 2 - 0.08), y, zf, zf + 0.9, 0.05, "wood", sides=4, taper=0.9))
        for k in range(3):
            pt.add("load", B.post(0.0, 0.0, 0.0, L - 1.2, 0.26, "bark", sides=6, taper=0.94).rotate_x(math.pi / 2).translate(-0.5 + 0.5 * k, (L - 1.2) / 2, zf + 0.27))
        pt.add("load", B.post(0.0, 0.0, 0.0, L - 1.4, 0.24, "bark", sides=6, taper=0.94).rotate_x(math.pi / 2).translate(-0.25, (L - 1.4) / 2, zf + 0.7))
        pt.add("load", B.post(0.0, 0.0, 0.0, L - 1.4, 0.24, "bark", sides=6, taper=0.94).rotate_x(math.pi / 2).translate(0.25, (L - 1.4) / 2, zf + 0.7))
    else:
        Lb = L - 1.6
        hb = 2.3
        pt.add("body", B.chamfer(0.0, 0.0, zf, zf + hb, W - 0.1, Lb, 0.05, "wall_alt", top="roof"))
        pt.add("roof", B.chamfer(0.0, 0.0, zf + hb + 0.002, zf + hb + 0.14, W + 0.1, Lb + 0.5, 0.04, "roof"))
        pt.add("cupola", B.board(-0.75, 0.75, -0.5, 1.1, zf + hb + 0.142, zf + hb + 1.0, "wall_alt", ch=0.05, top="roof"))
        for sx in (-1, 1):
            for yy in (-1.2, 1.2):
                c = B.card(yy, -0.003, zf + 1.45, 0.55, 0.6, "screen").rotate_z(-math.pi / 2 if sx > 0 else math.pi / 2)
                pt.add("panes", c.translate(sx * (W / 2 - 0.05), 0.0, 0.0), "card")
        for sy in (-1, 1):
            pt.add("platforms", B.railing(-W / 2 + 0.1, W / 2 - 0.1, sy * (L / 2 - 0.1), zf, 0.9, 1, balusters=0, post_s=0.07))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up", rides="track")]))


@register("wrail.locomotive", V, "vehicle", {
    "stack": S.enum("balloon", ["balloon", "straight"]),
}, "Small frontier steam locomotive: a tapered boiler with a flared smokestack, steam and sand domes, a square "
   "headlamp, a pilot, two big painted driving wheels and one small leading wheel a side, and a cab with a "
   "curved roof and side windows.", origin="floor_center")
def locomotive(P, seed):
    pt = Parts()
    zr = TIE_Z + 0.12
    yb0, yb1 = -1.6, 2.2
    zc = zr + 1.65
    pt.add("frame", B.board(-0.68, 0.68, -3.1, 3.1, zr + 0.6, zr + 0.9, "metal", ch=0.08))
    boiler = K.lathe([(0.66, 0.0), (0.66, yb1 - yb0)], 10, "metal", smooth=True, cap_roles=("metal", "metal")).rotate_x(-math.pi / 2)
    pt.add("boiler", boiler.translate(0.0, yb0, zc))
    pt.add("smokebox", K.lathe([(0.7, 0.0), (0.7, 0.55)], 10, "metal", smooth=True).rotate_x(-math.pi / 2).translate(0.0, yb1 + 0.001, zc))
    ys = yb1 + 0.25
    if P["stack"] == "balloon":
        prof = [(0.17, zc + 0.5), (0.2, zc + 1.0), (0.45, zc + 1.55), (0.42, zc + 1.78)]
    else:
        prof = [(0.17, zc + 0.5), (0.19, zc + 1.5), (0.26, zc + 1.7)]
    pt.add("stack", K.lathe(prof, 6, "metal", smooth=True).translate(0.0, ys, 0.0))
    pt.add("domes", K.lathe([(0.3, zc + 0.5), (0.3, zc + 0.85), (0.0, zc + 1.05)], 6, "chrome", smooth=True).translate(0.0, 0.5, 0.0))
    pt.add("lamp", B.board(-0.2, 0.2, yb1 + 0.06, yb1 + 0.44, zc + 0.62, zc + 1.05, "metal", ch=0.05))
    pt.add("lens", B.card(0.0, yb1 + 0.25 - 0.2, zc + 0.83, 0.24, 0.24, "light").rotate_z(math.pi).translate(0.0, 2 * (yb1 + 0.25), 0.0), "card")
    pilot = [(-0.7, 0.0), (0.7, 0.0), (0.7, 0.62), (-0.7, 0.62)]
    wedge = [(0.0, zr + 0.06), (0.0, zr + 0.85), (0.75, zr + 0.85)]
    pw = B.slab(K.ccw([(yb1 + 0.55 + y, z) for y, z in wedge]), -0.7, 0.7, "band")
    import numpy as np
    A = np.asarray(pw.v)
    pw.v = [tuple(p) for p in np.stack([A[:, 1], A[:, 0], A[:, 2]], axis=1).tolist()]
    pt.add("pilot", pw.orient_outward())
    for sx in (-1, 1):
        for y in (0.15, -1.15):
            pt.add("drivers", B.wheel(sx * B.RAIL_GAUGE / 2 + sx * 0.02, y, zr + 0.6, 0.6, 0.1, sides=10))
        pt.add("leaders", B.wheel(sx * B.RAIL_GAUGE / 2, 1.85, zr + 0.32, 0.32, 0.08, sides=6))
        pt.add("rods", B.beam((sx * (B.RAIL_GAUGE / 2 + 0.1), -1.15, zr + 0.45), (sx * (B.RAIL_GAUGE / 2 + 0.1), 0.15, zr + 0.45), 0.06, 0.06, "metal", roll=45.0))
    cy0, cy1 = -3.0, yb0 + 0.02
    pt.add("cab", B.chamfer(0.0, (cy0 + cy1) / 2, zr + 0.9, zr + 3.0, 2.0, cy1 - cy0, 0.06, "wall_alt", top="roof"))
    sec = [(-1.2, 0.0), (1.2, 0.0), (1.2, 0.07), (0.6, 0.24), (0.0, 0.28), (-0.6, 0.24), (-1.2, 0.07)]
    rf = B.slab([(x, z + zr + 3.002) for x, z in sec], cy0 - 0.25, cy1 + 0.3, "roof")
    pt.add("cab_roof", rf)
    for sx in (-1, 1):
        c = B.card((cy0 + cy1) / 2, -0.003, zr + 2.2, 0.8, 0.7, "screen").rotate_z(-math.pi / 2 if sx > 0 else math.pi / 2)
        pt.add("panes", c.translate(sx * 1.0, 0.0, 0.0), "card")
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up", rides="track")], landmark=True))


# ================================================================ MINE
OPEN = {"straight": "ns", "corner": "se", "tee": "sew", "cross": "nsew", "end": "s", "end_door": "ns"}
HT = 3.2           # tunnel storey


def tunnel_segments(opens):
    """Wall segments (x0, y0, x1, y1) around the 3 m passage; the passage lies to the LEFT of travel."""
    c = 1.5
    e = 2.0
    segs = []
    # centre square, counter-clockwise; each side either a wall or an arm opening
    corners = [(-c, -c), (c, -c), (c, c), (-c, c)]
    sides = ["s", "e", "n", "w"]
    for k, sd in enumerate(sides):
        a, b = corners[k], corners[(k + 1) % 4]
        if sd in opens:
            # arm walls: from the square corner out to the cell edge and back
            out = {"s": (0, -1), "e": (1, 0), "n": (0, 1), "w": (-1, 0)}[sd]
            a2 = (a[0] + out[0] * (e - c), a[1] + out[1] * (e - c))
            b2 = (b[0] + out[0] * (e - c), b[1] + out[1] * (e - c))
            segs.append((a[0], a[1], a2[0], a2[1]))
            segs.append((b2[0], b2[1], b[0], b[1]))
        else:
            segs.append((a[0], a[1], b[0], b[1]))
    # merge collinear neighbours (ccw chain)
    merged = []
    for s in segs:
        if merged:
            p = merged[-1]
            d1 = (p[2] - p[0], p[3] - p[1])
            d2 = (s[2] - s[0], s[3] - s[1])
            if abs(p[2] - s[0]) < 1e-9 and abs(p[3] - s[1]) < 1e-9 and abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-9 and d1[0] * d2[0] + d1[1] * d2[1] > 0:
                merged[-1] = (p[0], p[1], s[2], s[3])
                continue
        merged.append(s)
    if len(merged) > 1:
        p, s = merged[-1], merged[0]
        d1 = (p[2] - p[0], p[3] - p[1])
        d2 = (s[2] - s[0], s[3] - s[1])
        if abs(p[2] - s[0]) < 1e-9 and abs(p[3] - s[1]) < 1e-9 and abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-9 and d1[0] * d2[0] + d1[1] * d2[1] > 0:
            merged[0] = (p[0], p[1], s[2], s[3])
            merged.pop()
    # segments of an open side end on the cell edge: drop zero-length
    return [s for s in merged if math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-6]


def rock_wall(seg, r, h=HT, role="rock"):
    """One-sided lumpy rock sheet along a segment, front side toward the passage (left of travel). Lumps fade to zero
    at both ends and along the floor so neighbouring sheets and cells meet."""
    x0, y0, x1, y1 = seg
    L = math.hypot(x1 - x0, y1 - y0)
    nu = max(2, int(round(L / 1.0)))
    bs = B.bumps(r, max(2, int(L * 1.3)), (0.1, 0.15), (0.9, 0.95), amp=0.22, size=(0.12, 0.3))

    def fn(u, v):
        env = math.sin(math.pi * u) ** 0.7
        d = env * (math.sin(math.pi * min(1.0, v * 1.15)) ** 0.5 * B.bump_field(bs, u, v) + 0.18 * v ** 2)
        return (u * L, -d, v * h)
    us = [i / nu for i in range(nu + 1)]
    vs = [0.0, 0.3, 0.62, 0.86, 1.0]
    m = B.grid_sheet(us, vs, fn, lambda i, j: role if j < 3 else "cliff")
    # grid_sheet fronts face local -Y (right of travel); the passage lies LEFT of travel (+Y): mirror in Y (meshkit
    # flips the winding with it) so the front and the lumps face the passage
    m.scale(1.0, -1.0, 1.0)
    ang = math.atan2(y1 - y0, x1 - x0)
    return m.rotate_z(ang).translate(x0, y0, 0.0)


def passage_rects(opens):
    c, e = 1.5, 2.0
    rects = [(-c, -c, c, c)]
    for sd in opens:
        rects.append({"s": (-c, -e, c, -c), "n": (-c, c, c, e), "e": (c, -c, e, c), "w": (-e, -c, -c, c)}[sd])
    return rects


def flat_rects(rects, z, role, down=False, step=1.5):
    m = K.Mesh()
    for x0, y0, x1, y1 in rects:
        nx = max(1, int(round((x1 - x0) / step)))
        ny = max(1, int(round((y1 - y0) / step)))
        for i in range(nx):
            for j in range(ny):
                a = (x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny)
                b = (x0 + (x1 - x0) * (i + 1) / nx, y0 + (y1 - y0) * (j + 1) / ny)
                q = [(a[0], a[1], z), (b[0], a[1], z), (b[0], b[1], z), (a[0], b[1], z)]
                m.add(list(reversed(q)) if down else q, [(0, 1, 2, 3)], role, False)
    return B.weld(m)


def timber_set(pt, x_axis, at, w=2.7, h=2.75, post="post", cap="wood"):
    """Mine timber set across the passage: two battered posts, a cap beam, blocking wedges (piece-space)."""

    def P_(s, z):
        return (s, at, z) if x_axis else (at, s, z)
    for sx in (-1, 1):
        pt.add("sets", B.timber(P_(sx * (w / 2 + 0.02), 0.0), P_(sx * (w / 2 - 0.1), h - 0.02), 0.2, 0.2, post, up=(0.0, 1.0, 0.0) if x_axis else (1.0, 0.0, 0.0)))
    pt.add("caps", B.timber(P_(-w / 2 - 0.25, h + 0.1), P_(w / 2 + 0.25, h + 0.1), 0.22, 0.24, cap))
    for s in (-0.6, 0.6):
        pt.add("wedges", B.timber(P_(s - 0.15, h + 0.25), P_(s + 0.15, h + 0.25), 0.18, 0.06, cap, ch=0.02))


@register("wmine.tunnel", V, "shell", {
    "kind": S.enum("straight", list(OPEN)),
    "track": S.boolean(False, "mine track along a straight tunnel"),
    "daylight": S.boolean(False, "end_door only: the mouth of the mine - painted daylight beyond the door frame"),
}, "Mine tunnel cell (4 m): one-sided rough rock walls around a 3 m passage, a dirt floor and a low rock ceiling, "
   "timber sets (battered posts, cap, wedges) every 2 m. Kinds: straight, corner, tee, cross, end, end_door (the north "
   "arm runs out through a door socket on the room edge: the runtime timber frame, dark drift depth beyond, or with "
   "daylight the bright desert seen through the mine mouth). Joins on tunnel sockets at cell-edge midpoints.",
   origin="cell_centre")
def tunnel(P, seed):
    kind = P["kind"]
    opens = OPEN[kind]
    r = rng(seed, "wmine.tunnel", kind)
    pt = Parts()
    walls = K.Mesh()
    for seg in tunnel_segments(opens):
        walls.merge(rock_wall(seg, r))
    pt.add("walls", walls, "shell")
    rects = passage_rects(opens)
    pt.add("floor", flat_rects(rects, 0.0, "dirt"), "shell")
    pt.add("ceiling", flat_rects(rects, HT, "rock", down=True), "shell")
    if kind in ("straight", "end_door"):
        for y in ((-1.0, 1.0) if kind == "straight" else (-1.0,)):
            timber_set(pt, True, y)
    else:
        for sd in opens:
            y = 1.75
            if sd in "ns":
                timber_set(pt, True, y if sd == "n" else -y)
            else:
                timber_set(pt, False, y if sd == "e" else -y)
    if P["track"] and kind == "straight":
        lay_track(pt, [(0.0, -2.0, 0.0), (0.0, 2.0, 0.0)], B.MINE_GAUGE, 1.1, 0.5, sec_b=MINE_BALLAST, tie_w=0.14, tie_h=0.07)
    socks = [B.sock("tunnel", {"s": (0.0, -2.0, 0.0), "n": (0.0, 2.0, 0.0), "e": (2.0, 0.0, 0.0), "w": (-2.0, 0.0, 0.0)}[sd], sd,
                    width_m=B.TUNNEL_W) for sd in opens if not (kind == "end_door" and sd == "n")]
    if kind == "end_door":
        # the drift runs on into the dark beyond the door frame (a dark depth card), or - daylight - the mouth of the
        # mine: the painted desert view (fullbright, role view) seen through the frame
        pt.add("depth", B.card(0.0, 2.0 + B.ANCHOR_BACK + 0.55, HT / 2, B.TUNNEL_W + 0.6, HT + 0.4,
                               "view" if P["daylight"] else "opening"), "card")
        socks.append(B.sock("door", (0.0, 2.0 + B.ANCHOR_BACK, 0.0), "n", width_m=B.DOOR_W, height_m=B.DOOR_H, needs="wtown.doorway"))
    nodes = pt.nodes()
    return Asset(nodes, B.grid_meta("cell_centre", [1, 1], socks, kind=kind, height_m=HT))


@register("wmine.track", V, "structure", {
    "kind": S.enum("straight", ["straight", "corner", "end"]),
}, "Narrow-gauge mine track (0.6 m): straight cell, a 2 m radius cell corner (south to east) or a buffer end with a "
   "timber chock; light sleepers on a thin ballast bed.", origin="cell_centre")
def mine_track(P, seed):
    kind = P["kind"]
    pt = Parts()
    path = B.arc_path(2.0, -2.0, 2.0, math.pi, math.pi / 2, 6) if kind == "corner" else [(0.0, -2.0, 0.0), (0.0, 2.0, 0.0)]
    lay_track(pt, path, B.MINE_GAUGE, 1.1, 0.5, sec_b=MINE_BALLAST, tie_w=0.14, tie_h=0.07)
    if kind == "end":
        pt.add("chock", B.timber((-0.6, 1.4, 0.3), (0.6, 1.4, 0.3), 0.3, 0.32, "wood"))
        for sx in (-1, 1):
            pt.add("chock", B.sq_post(sx * 0.5, 1.6, 0.0, 0.5, 0.18, "post"))
    return Asset(pt.nodes(), B.grid_meta("cell_centre", [1, 1], track_sockets(kind, mine=True), kind=kind))


@register("wmine.portal", V, "shell", {
    "width": S.num(10.0, 8.0, 14.0), "height": S.num(7.0, 5.0, 9.0), "sign": S.boolean(True),
}, "Mine entrance: a one-sided rock cliff face with a cut opening on a door socket (the runtime timber frame is "
   "wtown.doorway), dark tunnel depth behind it, horizontal lagging logs over the cap and a blank sign board above.",
   origin="lot_line")
def portal(P, seed):
    w, h = P["width"], P["height"]
    r = rng(seed, "wmine.portal")
    ow, oh = 2.8, 3.2
    bs = B.bumps(r, 9, (0.05, 0.1), (0.95, 0.95), amp=0.7, size=(0.08, 0.2))
    peaks = [(r.uniform(0.1, 0.9), r.uniform(0.1, 0.3), r.uniform(0.07, 0.16)) for _ in range(4)]
    xs = sorted({-w / 2, w / 2, -ow / 2, ow / 2} | {-w / 2 + w * i / 8 for i in range(9)})
    zs = [0.0, 1.6, oh, oh + 1.0, h * 0.75, h]

    def fn(x, z):
        u = (x + w / 2) / w
        v = z / h
        crest = 1.0 + sum(a * math.exp(-((u - cu) / cw) ** 2) for cu, a, cw in peaks) * math.sin(math.pi * u) ** 0.6
        near = max(0.0, 1.0 - max(abs(x) - ow / 2, z - oh, 0.0) / 1.2) if abs(x) < ow / 2 + 1.2 and z < oh + 1.2 else 0.0
        d = (0.25 + B.bump_field(bs, u, v) * (1 - near)) * (1 - near) + 1.5 * (1 - math.sin(math.pi * u)) ** 2 + 0.5 * v ** 2
        return (x, -d, z * (crest if z > oh + 0.5 else 1.0))

    m = B.grid_sheet(xs, zs, fn, lambda i, j: "cliff" if j % 2 else "rock",
                     skip=lambda i, j: (xs[i] >= -ow / 2 - 1e-9 and xs[i + 1] <= ow / 2 + 1e-9 and zs[j + 1] <= oh + 1e-9))
    pt = Parts()
    pt.add("face", m, "shell")
    pt.add("depth", B.card(0.0, 1.2, oh / 2, ow + 0.1, oh + 0.1, "opening"), "card")
    for k in range(3):
        z = B.DOOR_H + 0.45 + 0.24 * k
        pt.add("lagging", B.post(0.0, 0.0, 0.0, ow + 1.0 - 0.3 * k, 0.12, "bark", sides=6, taper=0.95).rotate_y(math.pi / 2)
               .translate(-(ow + 1.0 - 0.3 * k) / 2, -0.22, z))
    if P["sign"]:
        sign_board(pt, 0.0, B.DOOR_H + 1.55, 1.8, 0.5, -0.3)
        for sx in (-1, 1):
            pt.add("sign_posts", B.post(sx * 0.7, -0.27, B.DOOR_H + 0.4, B.DOOR_H + 1.3, 0.04, "post", sides=4, taper=1.0))
    socks = [door_socket(0.0)]
    return Asset(pt.nodes(), B.grid_meta("lot_line", [int(round(w / 4)), 1], socks, entry="socket"))


@register("wmine.cart", V, "vehicle", {
    "load": S.boolean(True), "tipped": S.boolean(False),
}, "Ore cart: a tapered riveted tub on a timber frame with four small painted wheels and couplers; loaded with a "
   "heap of ore or empty, optionally tipped on its side as wreckage dressing.", origin="floor_center")
def cart(P, seed):
    pt = Parts()
    r = rng(seed, "wmine.cart")
    zr = 0.11 + 0.07
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("wheels", B.wheel(sx * B.MINE_GAUGE / 2, sy * 0.42, zr + 0.18, 0.18, 0.06, sides=8))
    pt.add("frame", B.chamfer(0.0, 0.0, zr + 0.24, zr + 0.36, 0.9, 1.3, 0.05, "wood"))
    rings = []
    for z, sx, sy in ((zr + 0.36, 0.42, 0.62), (zr + 0.95, 0.56, 0.78)):
        rings.append([(x * sx, y * sy, z) for x, y in K.rounded_rect2d(2.0, 2.0, 0.3, 1)])
    tub = K.loft(rings, "hull_alt", smooth=False, cap0=True, cap1=True, cap_roles=("metal", "opening"))
    pt.add("tub", tub)
    for sy in (-1, 1):
        pt.add("couplers", B.timber((0.0, sy * 0.66, zr + 0.3), (0.0, sy * 0.85, zr + 0.3), 0.08, 0.08, "metal"))
    if P["load"]:
        pt.add("ore", B.rock_blob(0.0, 0.0, zr + 0.95, 0.46, 0.66, 0.24, r, role="rock", segs=7, rings=3, jitter=0.2))
    nodes = pt.nodes()
    if P["tipped"]:
        for n in nodes:
            n.mesh.rotate_y(math.pi / 2 * 0.95).translate(0.0, 0.0, 0.0)
    return finalize(nodes, B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up", rides="mine_track")]))


@register("wmine.headframe", V, "structure", {
    "height": S.num(8.0, 6.0, 11.0),
}, "Timber headframe over a mine shaft: four battered legs with girts and X-bracing, back braces, a sheave wheel "
   "(painted disc) on top, a hoist rope down to a cage and a timber shaft collar with a dark shaft card. Origin on "
   "the shaft centre (back braces reach 4 m behind).", origin="shaft_centre")
def headframe(P, seed):
    h = P["height"]
    pt = Parts()
    b0, b1 = 1.6, 0.75
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("legs", B.timber((sx * b0, sy * b0, 0.0), (sx * b1, sy * b1, h), 0.24, 0.24, "wood"))
    for z in (h * 0.35, h * 0.7):
        t = b0 + (b1 - b0) * z / h
        for (ax, ay), (bx, by) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            k = 0.08
            pt.add("girts", B.beam((ax * t * (1 - k) + bx * t * k, ay * t * (1 - k) + by * t * k, z),
                                   (bx * t * (1 - k) + ax * t * k, by * t * (1 - k) + ay * t * k, z), 0.12, 0.12, "wood", roll=45.0))
    for sx in (-1, 1):
        pt.add("backs", B.timber((sx * 1.0, 4.2, 0.0), (sx * 0.6, b1 * 0.9, h * 0.92), 0.22, 0.22, "wood"))
    pt.add("sheave_axle", B.timber((-0.9, 0.0, h + 0.2), (0.9, 0.0, h + 0.2), 0.18, 0.18, "wood"))
    pt.add("sheave", B.wheel(0.0, 0.0, h + 0.75, 0.75, 0.12, sides=12))
    pt.add("rope", B.post(0.0, -0.74, 1.6, h + 0.7, 0.025, "rope", sides=3, taper=1.0))
    pt.add("cage", B.chamfer(0.0, -0.74, 1.0 + 0.6, 1.0 + 1.5, 0.9, 0.9, 0.06, "metal", top="metal"))
    pt.add("collar", K.prism(K.rounded_rect2d(3.4, 3.4, 0.25, 1), 0.0, 0.25, "wood", role_top="step",
                             holes=[K.rounded_rect2d(2.2, 2.2, 0.1, 1)]))
    pt.add("shaft", B.card(0.0, 0.0, 0.0, 2.2, 2.2, "opening").rotate_x(-math.pi / 2).translate(0.0, 0.0, 0.03), "card")
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")], landmark=True), center_x=False, center_y=False)


@register("wmine.ore_pile", V, "furniture_large", {
    "size": S.num(1.6, 0.8, 3.0), "count": S.integer(6, 3, 9),
}, "Spoil / ore heap: a low rounded mound of faceted rock lumps with a few loose stones around its foot.",
   origin="floor_center")
def ore_pile(P, seed):
    r = rng(seed, "wmine.ore_pile")
    s = P["size"]
    pt = Parts()
    pt.add("mound", B.rock_blob(0.0, 0.0, s * 0.18, s, s * 0.8, s * 0.42, r, role="dirt", segs=8, rings=3, jitter=0.12))
    for i in range(P["count"]):
        a = 2 * math.pi * i / P["count"] + r.uniform(-0.3, 0.3)
        d = s * r.uniform(0.75, 1.1)
        rr = s * r.uniform(0.12, 0.2)
        pt.add("lumps", B.rock_blob(d * math.cos(a), d * 0.8 * math.sin(a), rr * 0.5, rr, rr * 0.9, rr * 0.7, r, role="rock",
                                    segs=5, rings=2, jitter=0.2))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wmine.ore_bin", V, "structure", {
    "height": S.num(3.2, 2.4, 4.2),
}, "Ore bin (tipple): a sloped-bottom plank bin on four timber stilts with cross bracing and a hinged chute over a "
   "track, a ramp-side catwalk rail on top.", origin="floor_center")
def ore_bin(P, seed):
    h = P["height"]
    pt = Parts()
    for sx in (-1, 1):
        for sy in (-1, 1):
            pt.add("stilts", B.sq_post(sx * 1.25, sy * 1.0, 0.0, h, 0.24, "post"))
    pt.add("braces", B.beam((-1.25, -1.0, 0.3), (1.25, -1.0, h - 0.4), 0.08, 0.14, "wood", roll=45.0))
    pt.add("braces", B.beam((-1.25, 1.0, 0.3), (1.25, 1.0, h - 0.4), 0.08, 0.14, "wood", roll=45.0))
    rings = [[(x * 1.3, y * 1.05, h) for x, y in K.rounded_rect2d(2.0, 2.0, 0.1, 1)],
             [(x * 1.5, y * 1.25, h + 1.8) for x, y in K.rounded_rect2d(2.0, 2.0, 0.1, 1)]]
    pt.add("bin", K.loft(rings, "hull", smooth=False, cap_roles=("wood", "dirt")))
    pt.add("chute", B.section_beam((0.0, -1.0, h + 0.2), (0.0, -2.3, h - 0.9), [(-0.35, 0.0), (0.35, 0.0), (0.35, 0.3), (0.28, 0.08), (-0.28, 0.08), (-0.35, 0.3)],
                                   "hull_alt"))
    pt.add("rail", B.railing(-1.4, 1.4, 1.2, h + 1.8, 0.9, 2, balusters=1, post_s=0.08))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wmine.windlass", V, "furniture", {
    "bucket": S.boolean(True),
}, "Hand windlass over a prospect hole: two A-frame uprights, a log drum with a crank handle, rope down to a "
   "wooden bucket, a plank collar around a dark hole.", origin="floor_center")
def windlass(P, seed):
    pt = Parts()
    for sx in (-1, 1):
        pt.add("uprights", B.timber((sx * 0.75, -0.45, 0.0), (sx * 0.75, 0.0, 1.05), 0.1, 0.1, "wood", up=(1.0, 0.0, 0.0)))
        pt.add("uprights", B.timber((sx * 0.75, 0.45, 0.0), (sx * 0.75, 0.0, 1.05), 0.1, 0.1, "wood", up=(1.0, 0.0, 0.0)))
    pt.add("drum", B.post(0.0, 0.0, 0.0, 1.62, 0.12, "bark", sides=7, taper=1.0).rotate_y(math.pi / 2).translate(-0.81, 0.0, 1.08))
    pt.add("crank", B.timber((0.85, 0.0, 1.08), (0.85, -0.05, 0.78), 0.05, 0.05, "metal", up=(1.0, 0.0, 0.0)))
    pt.add("crank", B.timber((0.85, -0.05, 0.78), (1.1, -0.05, 0.78), 0.05, 0.05, "metal"))
    pt.add("collar", K.prism(K.rounded_rect2d(1.5, 1.2, 0.08, 1), 0.0, 0.08, "wood", role_top="step", holes=[K.rounded_rect2d(1.0, 0.75, 0.05, 1)]))
    pt.add("hole", B.card(0.0, 0.0, 0.0, 1.0, 0.75, "opening").rotate_x(-math.pi / 2).translate(0.0, 0.0, 0.02), "card")
    if P["bucket"]:
        pt.add("rope", B.post(0.1, 0.0, 0.62, 1.0, 0.012, "rope", sides=3, taper=1.0))
        pt.add("bucket", K.lathe([(0.13, 0.38), (0.16, 0.62)], 7, "body", smooth=False, cap_roles=("wood", "opening")).translate(0.1, 0.0, 0.0))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wmine.shaft", V, "structure", {
    "size": S.num(2.4, 1.6, 3.2), "ladder": S.boolean(True),
}, "Shaft collar: a square timber frame around a dark shaft opening in the floor, guard rails on three sides and a "
   "ladder top; reads as a way down.", origin="room_floor")
def shaft(P, seed):
    s = P["size"]
    pt = Parts()
    pt.add("collar", K.prism(K.rounded_rect2d(s + 0.8, s + 0.8, 0.2, 1), 0.0, 0.22, "wood", role_top="step",
                             holes=[K.rounded_rect2d(s, s, 0.06, 1)]))
    pt.add("hole", B.card(0.0, 0.0, 0.0, s, s, "opening").rotate_x(-math.pi / 2).translate(0.0, 0.0, 0.03), "card")
    e = s / 2 + 0.25
    for (x, y) in ((-e, e), (e, e), (-e, -e), (e, -e)):
        pt.add("posts", B.sq_post(x, y, 0.22, 1.2, 0.12, "post"))
    pt.add("rails", B.beam((-e, e, 1.1), (e, e, 1.1), 0.07, 0.07, "rail", roll=45.0))
    pt.add("rails", B.beam((-s / 2 - 0.25, -s / 2 - 0.25, 1.06), (-s / 2 - 0.25, s / 2 + 0.25, 1.06), 0.07, 0.07, "rail", roll=45.0))
    pt.add("rails", B.beam((s / 2 + 0.25, -s / 2 - 0.25, 1.06), (s / 2 + 0.25, s / 2 + 0.25, 1.06), 0.07, 0.07, "rail", roll=45.0))
    if P["ladder"]:
        for sx in (-1, 1):
            pt.add("ladder", B.beam((sx * 0.25, -s / 2 + 0.1, -0.3), (sx * 0.25, -s / 2 + 0.1, 0.9), 0.06, 0.06, "wood", roll=45.0))
        for k in range(3):
            pt.add("ladder", B.spindle((-0.25, -s / 2 + 0.1, 0.0 + 0.3 * k), (0.25, -s / 2 + 0.1, 0.0 + 0.3 * k), 0.045, "wood"))
    return Asset(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wmine.ladder", V, "furniture", {
    "height": S.num(3.0, 1.5, 4.5),
}, "Wall ladder of split poles with lashed rungs, leaning slightly; wall-mounted dressing for shafts, lofts and "
   "galleries.", origin="floor_center")
def ladder(P, seed):
    h = P["height"]
    pt = Parts()
    lean = 0.35
    for sx in (-1, 1):
        pt.add("poles", B.timber((sx * 0.25, -lean, 0.0), (sx * 0.23, 0.0, h), 0.07, 0.07, "post", up=(1.0, 0.0, 0.0)))
    n = int(h / 0.32)
    for k in range(1, n):
        t = k / n
        pt.add("rungs", B.spindle((-0.26, -lean * (1 - t), h * t), (0.26, -lean * (1 - t), h * t), 0.04, "wood"))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("wall", (0, 0, 0), "s")]))


@register("wmine.rubble", V, "furniture_large", {
    "size": S.num(2.2, 1.2, 3.0),
}, "Cave-in rubble: a heap of broken rock with a snapped timber post and a fallen cap beam across it.",
   origin="floor_center")
def rubble(P, seed):
    r = rng(seed, "wmine.rubble")
    s = P["size"]
    pt = Parts()
    pt.add("heap", B.rock_blob(0.0, 0.0, s * 0.2, s, s * 0.7, s * 0.45, r, role="rock", segs=8, rings=3, jitter=0.18))
    for i in range(4):
        a = r.uniform(0, 2 * math.pi)
        d = s * r.uniform(0.6, 1.0)
        rr = s * r.uniform(0.15, 0.25)
        pt.add("rocks", B.rock_blob(d * math.cos(a), d * 0.7 * math.sin(a), rr * 0.45, rr, rr * 0.8, rr * 0.6, r, role="rock", segs=5,
                                    rings=2, jitter=0.2))
    pt.add("beam", B.timber((-s * 0.9, -0.3, 0.25), (s * 0.8, 0.35, s * 0.62), 0.22, 0.24, "wood"))
    pt.add("post", B.timber((s * 0.75, -0.55, 0.0), (s * 0.95, -0.6, 1.1), 0.2, 0.2, "post"))
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))


@register("wmine.timber_set", V, "structure", {
    "width": S.num(2.7, 2.2, 3.2), "height": S.num(2.75, 2.2, 3.2),
}, "Standalone mine timber set: two battered posts, a cap beam with blocking wedges; spans a 3 m passage, a cave "
   "mouth or a shoring line.", origin="floor_center")
def timber_set_piece(P, seed):
    pt = Parts()
    timber_set(pt, True, 0.0, w=P["width"], h=P["height"])
    return finalize(pt.nodes(), B.grid_meta("free", None, [B.sock("prop", (0, 0, 0), "up")]))
