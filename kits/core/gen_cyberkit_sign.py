"""CYBERKIT signage (cysign.*): neon sign frames, projecting blade signs, billboards, holographic cards, cloth banners,
free-form neon tubes, rooftop glyph signs, LED tickers, ad panels and five shopfronts with invented names (noodle
bar, arcade, clinic, pawn shop, hotel).

Every lettering surface samples the pack's slot atlases (kits/core/cykit.py: screen = horizontal glyph signs and
pictograms, paper = vertical blades, book = billboard / monitor / menu, fabric = cloth banners, light = neon tube
rows). The glyphs come from an ORIGINAL stroke generator (kits/core/texgen_cyber.py), an invented script: no real
alphabet, brand, logo or trademark appears anywhere. Shop names are invented and live in the metadata only
(meta["shop"]), rendered as glyphs.
"""
import math

from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .gen_cyberkit_tower import gem, slot_rect

V = "1.0.0"
SLOT = S.enum("a", list(C.SLOTS), "neon accent slot (pack palette roles: a/b/c/d)")
SIGN_SLOT = S.enum("a", ["a", "b", "c"], "glyph-sign colour slot (screen atlas rows a/b/c)")
SIZES = {"small": (1.6, 0.8), "medium": (2.4, 1.2), "large": (3.4, 1.7)}
OPEN_W, OPEN_H, RECESS = 3.6, 3.7, 2.4          # cytower.facade shop slot


def sign_box(cx, cy, z0, w, h, depth, cell, atlas="screen", facing="-y", both=False):
    """Frame box with a lit atlas face (card) on the front (and the back if `both`)."""
    solid = C.slab(cx, cy, z0, w + 0.16 if facing in ("-y", "+y") else depth, depth if facing in ("-y", "+y") else w + 0.16, h + 0.16,
                   "frame", c=0.04)
    cards = K.Mesh()
    rect = C.cell_uv(atlas, cell)
    if facing in ("-y", "+y"):
        cards.merge(C.face_card(cx, cy - depth / 2, z0 + 0.08, w, h, atlas, rect, facing="-y", lift=C.LIFT))
        if both:
            cards.merge(C.face_card(cx, cy + depth / 2, z0 + 0.08, w, h, atlas, rect, facing="+y", lift=C.LIFT))
    else:
        cards.merge(C.face_card(cx - depth / 2, cy, z0 + 0.08, w, h, atlas, rect, facing="-x", lift=C.LIFT))
        cards.merge(C.face_card(cx + depth / 2, cy, z0 + 0.08, w, h, atlas, rect, facing="+x", lift=C.LIFT))
    return solid, cards


def wall_meta(sockets=(), **kw):
    return C.grid_meta("wall_face", None, [C.sock("wall_mount", (0, 0, 0), "n")] + list(sockets), **kw)


# ---------------------------------------------------------------- cysign.frame
@register("cysign.frame", V, "furniture", {
    "size": S.enum("medium", list(SIZES)), "slot": SIGN_SLOT, "design": S.integer(0, 0, 1, "glyph sign design"),
    "mount": S.enum("wall", ["wall", "hang", "legs"], "flat on a wall, hung off a bracket, or on rooftop legs"),
}, "Neon sign frame: a chamfered box carrying a lit glyph panel (screen atlas, slot colour) with a neon top tube; "
   "flat on a wall, hung perpendicular off a bracket (two faces) or standing on rooftop legs.", origin="opening_floor")
def frame(P, seed):
    w, h = SIZES[P["size"]]
    cell = "sign_%s%d" % (P["slot"], P["design"])
    solid, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    rect = slot_rect(P["slot"])
    if P["mount"] == "wall":
        s, c = sign_box(0, -0.13, 0.0, w, h, 0.26, cell)
        solid.merge(s)
        cards.merge(c)
        deco.merge(C.neon_tube([(-w / 2, -0.3, h + 0.26), (w / 2, -0.3, h + 0.26)], 0.04, "light", rect))
    elif P["mount"] == "hang":
        off = 0.5
        s, c = sign_box(0, -(off + w / 2), 0.0, w, h, 0.22, cell, facing="x")
        solid.merge(s)
        cards.merge(c)
        deco.merge(C.rod((0, -0.05, h + 0.45), (0, -(off + w), h + 0.45), 0.04, 4, "post"))
        deco.merge(C.slab(0, -0.06, h - 0.1, 0.3, 0.12, 0.7, "metal", c=0.02))
        for t in (0.15, 0.85):
            deco.merge(C.rod((0, -(off + w * t), h + 0.43), (0, -(off + w * t), h + 0.14), 0.015, 3, "metal"))
    else:
        s, c = sign_box(0, 0.0, 1.4, w, h, 0.26, cell, both=False)
        solid.merge(s)
        cards.merge(c)
        for sx in (-1, 1):
            deco.merge(C.rod((sx * w * 0.35, 0.05, 0.0), (sx * w * 0.35, 0.05, 1.5), 0.05, 4, "post"))
            deco.merge(C.rod((sx * w * 0.35, 0.05, 0.0), (sx * w * 0.35, 0.7, 0.02), 0.04, 4, "post"))
        deco.merge(C.neon_tube([(-w / 2, -0.17, 1.4 + h + 0.26), (w / 2, -0.17, 1.4 + h + 0.26)], 0.04, "light", rect))
    return C.finish([Node("box", solid, "solid"), Node("neon", deco, "solid"), Node("face", cards, "card")],
                    wall_meta(emitter={"slot": P["slot"]}), cy=False)


# ---------------------------------------------------------------- cysign.blade
@register("cysign.blade", V, "furniture_large", {
    "height": S.num(4.0, 2.0, 5.6), "slot": SLOT, "edge": S.boolean(True, "neon tube on the outer edge"),
}, "Projecting blade sign: a tall chamfered box perpendicular to the wall on two brackets, both faces showing a lit "
   "glyph column (paper atlas), a cap and an outer neon edge tube. The classic canyon-street sign.",
    origin="opening_floor")
def blade(P, seed):
    H = P["height"]
    w, off = 0.95, 0.35
    solid, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    solid.merge(C.slab(0, -(off + w / 2), 0.0, 0.3, w + 0.16, H + 0.16, "frame", c=0.04))
    rect = C.cell_uv("paper", "blade_" + P["slot"])
    cards.merge(C.face_card(-0.15, -(off + w / 2), 0.08, w, H, "paper", rect, facing="-x", lift=C.LIFT))
    cards.merge(C.face_card(0.15, -(off + w / 2), 0.08, w, H, "paper", rect, facing="+x", lift=C.LIFT))
    solid.merge(C.wedge(0, -(off + w / 2), H + 0.14, 0.36, w + 0.3, 0.1, 0.25, "trim", c=0.02))
    for z in (0.4, H - 0.4):
        deco.merge(C.rod((0, -0.02, z), (0, -off - 0.05, z), 0.05, 4, "metal"))
    if P["edge"]:
        deco.merge(C.neon_tube([(0, -(off + w + 0.14), 0.15), (0, -(off + w + 0.14), H)], 0.05, "light", slot_rect(P["slot"])))
    return C.finish([Node("blade", solid, "solid"), Node("brackets", deco, "solid"), Node("faces", cards, "card")],
                    wall_meta(emitter={"slot": P["slot"]}), cy=False)


# ---------------------------------------------------------------- cysign.billboard
@register("cysign.billboard", V, "arch", {
    "width": S.num(8.0, 4.0, 12.0), "height": S.num(4.0, 2.0, 6.0), "lift": S.num(3.0, 0.5, 6.0, "leg height"),
    "accent": SLOT, "lamps": S.integer(3, 0, 4),
}, "Rooftop billboard: a framed display (book atlas ad: ring emblem, glyph line, colour bars) on a braced truss with a "
   "catwalk and lamp arms. Reads as a landmark against the skyline.", origin="floor_center")
def billboard(P, seed):
    W, H, Lf = P["width"], P["height"], P["lift"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    solid.merge(C.slab(0, 0.0, Lf, W + 0.3, 0.4, H + 0.3, "frame", c=0.06))
    cards.merge(C.face_card(0, -0.2, Lf + 0.15, W, H, "book", C.cell_uv("book", "billboard"), lift=C.LIFT))
    legs = [-W * 0.38, W * 0.38] if W < 7 else [-W * 0.4, 0.0, W * 0.4]
    for x in legs:
        deco.merge(C.rod((x, 0.5, 0.0), (x, 0.5, Lf + H * 0.8), 0.09, 4, "post"))
        deco.merge(C.rod((x, 1.4, 0.0), (x, 0.5, Lf * 0.9), 0.06, 4, "post"))
    for a, b in zip(legs, legs[1:]):
        deco.merge(C.rod((a + 0.06, 0.5, Lf * 0.5), (b - 0.06, 0.5, Lf * 0.5), 0.05, 4, "metal"))
    solid.merge(C.slab(0, -0.65, Lf - 0.12, W, 0.9, 0.1, "metal", c=0.02))
    for k in range(P["lamps"]):
        x = -W / 2 + W * (k + 0.5) / max(1, P["lamps"])
        deco.merge(C.rod((x, -0.9, Lf - 0.05), (x, -1.4, Lf + 0.5), 0.03, 4, "post"))
        deco.merge(gem(x, -1.45, Lf + 0.56, 0.11, P["accent"], "core"))
    cards.merge(C.strip((-W / 2, -0.24, Lf + H + 0.32), (W / 2, -0.24, Lf + H + 0.32), 0.12, "light", (0, -1, 0), slot_rect(P["accent"])))
    return C.finish([Node("panel", solid, "solid"), Node("truss", deco, "solid"), Node("face", cards, "card")],
                    C.grid_meta("roof", None, [C.sock("roof", (0, 0, 0), "down", footprint_m=round(W, 2))], landmark=True))


# ---------------------------------------------------------------- cysign.holo
@register("cysign.holo", V, "furniture", {
    "cell": S.enum("sign_b0", ["sign_a0", "sign_b0", "sign_c1", "picto_joystick", "picto_cross", "billboard", "monitor"],
                   "atlas cell shown by the hologram"),
    "accent": SLOT, "size": S.num(1.6, 0.8, 3.0), "tilt": S.num(12.0, 0.0, 25.0, "forward tilt (deg)"),
}, "Holographic card prop: a squat projector with a glowing emitter ring, a thin light shaft and a floating "
   "double-sided card (screen or book atlas cell) tilted toward the street.", origin="floor_center")
def holo(P, seed):
    s = P["size"]
    cell = P["cell"]
    atlas = "book" if cell in ("billboard", "monitor") else "screen"
    aspect = 2.0 if cell.startswith("sign") or cell == "billboard" else 1.0
    w, h = s, s / aspect
    base, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    base.merge(C.lathe_at(0, 0, 0, [(0.42, 0.0), (0.42, 0.18), (0.32, 0.36), (0.18, 0.42), (0.0, 0.43)], 8, "body_alt", smooth=False))
    rect = slot_rect(P["accent"])
    ring = [(0.3 * math.cos(K.TAU * i / 10), 0.3 * math.sin(K.TAU * i / 10), 0.4) for i in range(10)]
    deco.merge(C.neon_tube(ring, 0.03, "light", rect, closed=True))
    deco.merge(C.neon_tube([(0, 0, 0.45), (0, 0, 1.0)], 0.025, "light", rect))
    t = math.radians(P["tilt"])
    z0 = 1.05
    for facing in ("-y", "+y"):
        q = C.face_card(0, 0, 0.0, w, h, atlas, C.cell_uv(atlas, cell), facing=facing, lift=0.004)
        q.rotate_x(-t if facing == "-y" else -t)
        q.translate(0, 0, z0)
        cards.merge(q)
    return C.finish([Node("projector", base, "solid"), Node("shaft", deco, "solid"), Node("card", cards, "card")],
                    C.grid_meta("free", None, [], emitter={"slot": P["accent"]}))


# ---------------------------------------------------------------- cysign.banner
@register("cysign.banner", V, "furniture", {
    "slot": SLOT, "length": S.num(2.6, 1.6, 3.6, "cloth drop (m)"),
}, "Cloth banner hung perpendicular to a wall from a bracket pole: a long glyph banner (fabric atlas, slot cloth) "
   "with a weighted hem rod, both faces painted.", origin="opening_floor")
def banner(P, seed):
    Lb = P["length"]
    w = Lb / 4.0
    deco, cards = K.Mesh(), K.Mesh()
    top = Lb + 0.3
    deco.merge(C.rod((0, -0.02, top), (0, -(w + 0.5), top), 0.035, 4, "post"))
    deco.merge(C.slab(0, -0.05, top - 0.3, 0.2, 0.1, 0.45, "metal", c=0.02))
    deco.merge(C.rod((0, -0.3, 0.25), (0, -(w + 0.42), 0.25), 0.03, 4, "metal"))
    rect = C.cell_uv("fabric", "banner_" + P["slot"])
    for fac in ("-x", "+x"):
        cards.merge(C.face_card(0, -(0.36 + w / 2), 0.26, w, Lb, "fabric", rect, facing=fac, lift=0.006))
    return C.finish([Node("pole", deco, "solid"), Node("cloth", cards, "card")], wall_meta(), cy=False)


# ---------------------------------------------------------------- cysign.tube
SHAPES = {
    "arrow": [(-1.0, 0.0), (0.6, 0.0), (0.2, 0.4), (0.6, 0.0), (0.2, -0.4)],
    "chevron": [(-0.8, 0.5), (0.0, -0.3), (0.8, 0.5)],
    "wave": [(-1.0, 0.0), (-0.6, 0.35), (-0.2, 0.0), (0.2, -0.35), (0.6, 0.0), (1.0, 0.35)],
    "bolt": [(-0.3, 0.8), (0.15, 0.1), (-0.15, 0.1), (0.3, -0.8)],
}


@register("cysign.tube", V, "furniture", {
    "shape": S.enum("ring", ["ring", "arrow", "chevron", "wave", "bolt", "heart"]), "slot": SLOT,
    "size": S.num(1.4, 0.6, 2.4),
}, "Free-form neon tube sign on a dark mounting plate: a ring, arrow, chevron, wave, bolt or heart bent from one "
   "glowing tube (light atlas slot row), wall-mounted on stand-offs.", origin="opening_floor")
def tube(P, seed):
    s = P["size"]
    plate, deco = K.Mesh(), K.Mesh()
    plate.merge(C.slab(0, -0.04, 0.0, s * 1.2, 0.08, s * 1.0, "frame", c=0.03))
    rect = slot_rect(P["slot"])
    zc = s * 0.5
    sh = P["shape"]
    if sh == "ring":
        pts = [(0.42 * s * math.cos(K.TAU * i / 14), -0.16, zc + 0.42 * s * math.sin(K.TAU * i / 14)) for i in range(14)]
        deco.merge(C.neon_tube(pts, 0.035, "light", rect, closed=True))
    elif sh == "heart":
        pts = []
        for i in range(16):
            t = K.TAU * i / 16
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((x / 17.0 * 0.45 * s, -0.16, zc + y / 17.0 * 0.45 * s))
        deco.merge(C.neon_tube(pts, 0.035, "light", rect, closed=True))
    else:
        poly = SHAPES[sh]
        pts = [(x * 0.48 * s, -0.16, zc + y * 0.48 * s) for x, y in poly]
        if sh == "arrow":
            deco.merge(C.neon_tube(pts[:2], 0.035, "light", rect))
            deco.merge(C.neon_tube([pts[2], (pts[1][0] + 0.02, pts[1][1], pts[1][2]), pts[4]], 0.035, "light", rect))
        else:
            deco.merge(C.neon_tube(pts, 0.035, "light", rect))
    for sx in (-1, 1):
        deco.merge(C.rod((sx * s * 0.45, -0.07, zc - s * 0.35), (sx * s * 0.45, -0.15, zc - s * 0.35), 0.015, 3, "metal"))
    return C.finish([Node("plate", plate, "solid"), Node("tube", deco, "solid")], wall_meta(emitter={"slot": P["slot"]}), cy=False)


# ---------------------------------------------------------------- cysign.roof
@register("cysign.roof", V, "arch", {
    "glyphs": S.integer(4, 2, 5), "slot": SLOT, "size": S.num(2.2, 1.4, 3.0, "glyph panel size"),
}, "Rooftop glyph sign: a row of big single-glyph panels (one glyph each, cut from the paper atlas blade column) on "
   "a braced lattice frame with a catwalk: the skyline's readable landmark.", origin="floor_center")
def roof(P, seed):
    n, s = P["glyphs"], P["size"]
    W = n * (s + 0.25)
    frame_, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    x0, y0, w, h, _ = C.PAPER["blade_" + P["slot"]]
    for k in range(n):
        x = -W / 2 + (s + 0.25) * (k + 0.5)
        frame_.merge(C.slab(x, 0.0, 1.6, s + 0.1, 0.22, s + 0.1, "frame", c=0.04))
        gy = y0 + 12 + 9 * (k % 5)
        rect = ((x0 + 1.5) / C.PAPER_SIZE, 1.0 - (gy + 8.0) / C.PAPER_SIZE, (x0 + w - 1.5) / C.PAPER_SIZE, 1.0 - (gy - 1.0) / C.PAPER_SIZE)
        cards.merge(C.face_card(x, -0.11, 1.65, s, s, "paper", rect, lift=C.LIFT))
    for x in (-W / 2 + 0.3, W / 2 - 0.3):
        deco.merge(C.rod((x, 0.3, 0.0), (x, 0.3, 1.7 + s), 0.08, 4, "post"))
        deco.merge(C.rod((x, 1.2, 0.0), (x, 0.3, 1.5), 0.06, 4, "post"))
    deco.merge(C.rod((-W / 2 + 0.3, 0.3, 0.9), (W / 2 - 0.3, 0.3, 0.9), 0.05, 4, "metal"))
    deco.merge(C.rod((-W / 2 + 0.3, 0.3, 1.55), (W / 2 - 0.3, 0.3, 1.55), 0.05, 4, "metal"))
    cards.merge(C.strip((-W / 2, -0.13, 1.57), (W / 2, -0.13, 1.57), 0.08, "light", (0, -1, 0), slot_rect(P["slot"])))
    return C.finish([Node("panels", frame_, "solid"), Node("lattice", deco, "solid"), Node("glyphs", cards, "card")],
                    C.grid_meta("roof", None, [C.sock("roof", (0, 0, 0), "down", footprint_m=round(W, 2))], landmark=True))


# ---------------------------------------------------------------- cysign.ticker / adpanel
@register("cysign.ticker", V, "arch", {
    "length": S.num(6.0, 2.0, 12.0), "slot": SIGN_SLOT,
}, "LED ticker strip: a long slim housing with a lit glyph band (screen sign cells repeated) and a neon lip, mounted "
   "along a facade fascia or a bridge deck.", origin="opening_floor")
def ticker(P, seed):
    Lt = P["length"]
    solid, cards = K.Mesh(), K.Mesh()
    solid.merge(C.slab(0, -0.12, 0.0, Lt, 0.24, 0.62, "frame", c=0.04))
    k = max(1, int(round(Lt / 1.1)))
    seg = (Lt - 0.2) / k
    for i in range(k):
        cell = "sign_%s%d" % (P["slot"], i % 2)
        x = -Lt / 2 + 0.1 + seg * (i + 0.5)
        cards.merge(C.face_card(x, -0.24, 0.06, seg - 0.04, 0.5, "screen", C.cell_uv("screen", cell), lift=C.LIFT))
    cards.merge(C.strip((-Lt / 2 + 0.05, -0.25, 0.6), (Lt / 2 - 0.05, -0.25, 0.6), 0.04, "light", (0, -1, 0), slot_rect(P["slot"])))
    return C.finish([Node("housing", solid, "solid"), Node("band", cards, "card")], wall_meta(), cy=False)


@register("cysign.adpanel", V, "furniture", {
    "cell": S.enum("billboard", ["billboard", "menu", "monitor"]), "accent": SLOT,
}, "Free-standing backlit ad panel (street furniture): a slim chamfered frame on two feet with the same lit display "
   "on both faces and a neon crown line.", origin="floor_center")
def adpanel(P, seed):
    cell = P["cell"]
    w, h = (1.9, 0.95) if cell == "billboard" else (1.2, 1.2)
    solid, cards = K.Mesh(), K.Mesh()
    solid.merge(C.slab(0, 0, 0.35, w + 0.2, 0.22, h + 0.2, "frame", c=0.04))
    for sx in (-1, 1):
        solid.merge(C.wedge(sx * (w / 2 - 0.1), 0, 0.0, 0.2, 0.5, 0.4, 0.38, "trim", c=0.02))
    rect = C.cell_uv("book", cell)
    cards.merge(C.face_card(0, -0.11, 0.45, w, h, "book", rect, lift=C.LIFT))
    cards.merge(C.face_card(0, 0.11, 0.45, w, h, "book", rect, facing="+y", lift=C.LIFT))
    cards.merge(C.strip((-w / 2, -0.12, h + 0.6), (w / 2, -0.12, h + 0.6), 0.04, "light", (0, -1, 0), slot_rect(P["accent"])))
    return C.finish([Node("frame", solid, "solid"), Node("faces", cards, "card")], C.grid_meta("free", None, []))


# ---------------------------------------------------------------- shopfronts
def shop_meta(name, kind, slot):
    return C.grid_meta("shop_slot", [1, 0], [C.sock("shopfront", (0, 0, 0), "s", width_m=OPEN_W, height_m=OPEN_H)],
                       shop={"kind": kind, "name": name, "lettering": "invented glyph script (texgen_cyber.glyph_mask)"},
                       emitter={"slot": slot}, bake_lights=[C.light((0, -0.8, 2.6), 4.0, 0.7)])


def fascia(slot, cell, picto=None, width=OPEN_W + 0.3):
    """Sign box on the fascia band above the shop opening (z 3.75 - 4.55), optional pictogram box at its side."""
    solid, cards = sign_box(-0.35 if picto else 0.0, -0.45, 3.78, width - (1.0 if picto else 0.0), 0.7, 0.3, cell)
    if picto:
        s2, c2 = sign_box(width / 2 - 0.42, -0.47, 3.76, 0.7, 0.7, 0.34, "picto_" + picto)
        solid.merge(s2)
        cards.merge(c2)
    return solid, cards


def lantern(cx, cy, z, slot, r=0.18):
    m = C.lathe_at(cx, cy, z, [(0.0, 0.0), (r * 0.7, 0.04), (r, r * 0.9), (r * 0.7, r * 1.9), (0.0, r * 2.0)], 6, "light",
                   smooth=False)
    u, v = (C.LIGHT[slot][0] + 16) / C.LIGHT_SIZE, 1.0 - (C.LIGHT[slot][1] + 2.5) / C.LIGHT_SIZE
    m.uv = [("n", [(u, v)] * len(f)) for f in m.f]
    return m


@register("cysign.noodle", V, "building", {"slot": SIGN_SLOT, "stools": S.integer(3, 0, 4)},
          "Noodle bar front 'Lanternfold Noodles' (invented): a timber counter across the shop slot with stools, "
          "noren cloth strips, paper lanterns, a lit menu board on the back wall and a bowl-pictogram glyph sign.",
          origin="opening_floor")
def noodle(P, seed):
    slot = P["slot"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    s, c = fascia(slot, "sign_%s0" % slot, "bowl")
    solid.merge(s)
    cards.merge(c)
    solid.merge(C.slab(0, 0.35, 0.0, OPEN_W - 0.2, 0.6, 1.0, "wood", c=0.04))
    solid.merge(C.slab(0, 0.3, 1.0, OPEN_W - 0.1, 0.85, 0.08, "trim", c=0.03))
    solid.merge(C.slab(0, 2.0, 0.0, OPEN_W - 0.3, 0.6, 0.95, "body_alt", c=0.03))
    for k in range(P["stools"]):
        x = -OPEN_W / 2 + 0.6 + (OPEN_W - 1.2) * k / max(1, P["stools"] - 1)
        deco.merge(C.lathe_at(x, -0.45, 0.0, [(0.18, 0.0), (0.06, 0.08), (0.05, 0.62), (0.2, 0.66), (0.2, 0.74), (0.0, 0.75)], 6, "metal",
                              smooth=False, roles=["metal", "metal", "metal", "leather", "leather"]))
    rect_n = C.cell_uv("fabric", "banner_%s" % ("c" if slot != "c" else "a"))
    for k in range(3):
        x = -OPEN_W / 2 + OPEN_W * (k + 0.5) / 3
        cards.merge(C.face_card(x, -0.02, OPEN_H - 0.85, OPEN_W / 3 - 0.08, 0.8, "fabric", rect_n, lift=0.0))
    for x in (-OPEN_W / 2 - 0.25, OPEN_W / 2 + 0.25):
        deco.merge(C.rod((x, -0.1, 3.7), (x, -0.55, 3.7), 0.025, 3, "post"))
        deco.merge(lantern(x, -0.55, 2.95, "c"))
    cards.merge(C.face_card(0, RECESS - 0.03, 1.4, 1.6, 1.6, "book", C.cell_uv("book", "menu"), lift=0.0))
    return C.finish([Node("counter", solid, "solid"), Node("stools", deco, "solid"), Node("cards", cards, "card")],
                    shop_meta("Lanternfold Noodles", "noodle_bar", slot), cy=False)


@register("cysign.arcade", V, "building", {"slot": SIGN_SLOT, "cabinets": S.integer(2, 1, 3)},
          "Arcade front 'Hexcade Hall' (invented): a glazed shopfront with a door gap, glowing game cabinets inside, a "
          "chase-light frame around the opening and a joystick-pictogram glyph sign.", origin="opening_floor")
def arcade(P, seed):
    slot = P["slot"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    s, c = fascia(slot, "sign_%s1" % slot, "joystick")
    solid.merge(s)
    cards.merge(c)
    gw = (OPEN_W - 1.4) / 2
    for sx in (-1, 1):
        cards.merge(C.face_card(sx * (0.7 + gw / 2), 0.05, 0.25, gw, 3.0, "glass", None))
        solid.merge(C.slab(sx * (0.7 + gw / 2), 0.08, 0.0, gw, 0.12, 0.25, "frame", c=0.02))
    solid.merge(C.slab(0, 0.08, 3.25, OPEN_W, 0.12, 0.12, "frame", c=0.02))
    for k in range(P["cabinets"]):
        x = -1.1 + 2.2 * k / max(1, P["cabinets"] - 1) if P["cabinets"] > 1 else 0.0
        solid.merge(C.wedge(x, 1.6, 0.0, 0.8, 0.8, 1.85, 1.6, "body_alt", c=0.04))
        cards.merge(C.face_card(x, 1.2, 1.0, 0.62, 0.5, "book", C.cell_uv("book", "monitor"), lift=C.LIFT))
    rect = slot_rect(slot)
    for a, b in (((-OPEN_W / 2 - 0.1, -0.06, 0.1), (-OPEN_W / 2 - 0.1, -0.06, OPEN_H)), ((OPEN_W / 2 + 0.1, -0.06, 0.1), (OPEN_W / 2 + 0.1, -0.06, OPEN_H)),
                 ((-OPEN_W / 2 - 0.1, -0.06, OPEN_H), (OPEN_W / 2 + 0.1, -0.06, OPEN_H))):
        deco.merge(C.neon_tube([a, b], 0.045, "light", rect))
    return C.finish([Node("front", solid, "solid"), Node("chase", deco, "solid"), Node("cards", cards, "card")],
                    shop_meta("Hexcade Hall", "arcade", slot), cy=False)


@register("cysign.clinic", V, "building", {"slot": SIGN_SLOT},
          "Clinic front 'Patchwell Clinic' (invented): pale tiled half-walls, sliding glass doors, a reception counter "
          "inside, a lit canopy strip and a cross-pictogram glyph sign.", origin="opening_floor")
def clinic(P, seed):
    slot = P["slot"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    s, c = fascia(slot, "sign_%s0" % slot, "cross")
    solid.merge(s)
    cards.merge(c)
    for sx in (-1, 1):
        solid.merge(C.slab(sx * (OPEN_W / 2 - 0.45), 0.1, 0.0, 0.9, 0.2, 3.7, "stone", c=0.03))
    cards.merge(C.face_card(-0.45, 0.05, 0.05, 0.9, 2.9, "glass", None))
    cards.merge(C.face_card(0.45, 0.02, 0.05, 0.9, 2.9, "glass", None))
    solid.merge(C.slab(0, 0.06, 2.95, 1.8, 0.14, 0.12, "frame", c=0.02))
    solid.merge(C.slab(0, -0.55, 3.2, OPEN_W + 0.3, 1.1, 0.16, "trim", c=0.04))
    cards.merge(C.strip((-OPEN_W / 2, -1.11, 3.24), (OPEN_W / 2, -1.11, 3.24), 0.08, "light", (0, -1, 0), slot_rect("a" if slot != "a" else "a")))
    solid.merge(C.slab(0.6, 1.6, 0.0, 1.6, 0.6, 1.05, "body", c=0.04))
    cards.merge(C.face_card(0.6, 1.29, 0.6, 0.5, 0.35, "book", C.cell_uv("book", "monitor"), lift=0.0))
    return C.finish([Node("front", solid, "solid"), Node("trim", deco, "solid"), Node("cards", cards, "card")],
                    shop_meta("Patchwell Clinic", "clinic", slot), cy=False)


@register("cysign.pawn", V, "building", {"slot": SIGN_SLOT, "shutter": S.num(0.45, 0.0, 0.9, "shutter drop fraction")},
          "Pawn shop front 'Twice-Owned' (invented): a half-dropped roll shutter, a barred display window full of "
          "pawned goods, a ring-pictogram glyph sign and a small blade.", origin="opening_floor")
def pawn(P, seed):
    slot = P["slot"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    s, c = fascia(slot, "sign_%s1" % slot, "ring")
    solid.merge(s)
    cards.merge(c)
    drop = OPEN_H * P["shutter"]
    if drop > 0.05:
        cards.merge(C.face_card(0, 0.04, OPEN_H - drop, OPEN_W - 0.05, drop - 0.02, "door", None))
        solid.merge(C.slab(0, 0.06, OPEN_H - drop - 0.12, OPEN_W, 0.12, 0.14, "trim", c=0.02))
    solid.merge(C.slab(-OPEN_W / 4, 0.4, 0.0, OPEN_W / 2 - 0.1, 0.6, 0.9, "wood", c=0.03))
    for k in range(5):
        x = -OPEN_W / 2 + 0.1 + k * (OPEN_W / 2 - 0.2) / 4
        deco.merge(C.rod((x, 0.12, 0.9), (x, 0.12, OPEN_H - drop - 0.12 if drop > 0.05 else OPEN_H), 0.02, 3, "metal"))
    for k, role in enumerate(("chrome", "body", "hull", "orb", "leather")):
        solid.merge(C.slab(-OPEN_W / 2 + 0.4 + k * 0.32, 0.4, 0.9, 0.22, 0.22, 0.18 + 0.08 * (k % 3), role, c=0.02))
    solid.merge(C.slab(OPEN_W / 4, 1.6, 0.0, 1.2, 0.5, 2.0, "body_alt", c=0.03))
    return C.finish([Node("front", solid, "solid"), Node("bars", deco, "solid"), Node("cards", cards, "card")],
                    shop_meta("Twice-Owned Pawn", "pawn_shop", slot), cy=False)


@register("cysign.hotel", V, "building", {"slot": SLOT},
          "Hotel entrance 'Hotel Halflight' (invented): a deep marquee canopy with a lit underside, glass double doors "
          "to a warm lobby glow, two potted shrubs and a tall vertical glyph blade above.", origin="opening_floor")
def hotel(P, seed):
    slot = P["slot"]
    solid, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    solid.merge(C.taper(0, -1.0, 3.3, 3.62, OPEN_W + 1.6, 2.2, OPEN_W + 1.2, 2.0, 0.2, 0.2, "frame", top="roof"))
    rect = slot_rect(slot)
    cards.merge(C.strip((-OPEN_W / 2 - 0.6, -2.12, 3.42), (OPEN_W / 2 + 0.6, -2.12, 3.42), 0.12, "light", (0, -1, 0), rect))
    for sx in (-1, 1):
        deco.merge(C.rod((sx * (OPEN_W / 2 + 0.55), -1.9, 0.0), (sx * (OPEN_W / 2 + 0.55), -1.9, 3.32), 0.06, 4, "chrome"))
    for sx in (-1, 1):
        cards.merge(C.face_card(sx * 0.55, 0.06, 0.05, 1.05, 2.8, "glass", None))
    solid.merge(C.slab(0, 0.08, 2.85, 2.3, 0.14, 0.14, "frame", c=0.02))
    v_t, v_b = 1.0, 1.0 - 1.0 / C.FIRE_ROWS
    cards.merge(C.quad((-OPEN_W / 2 + 0.2, RECESS - 0.03, 0.4), (OPEN_W / 2 - 0.2, RECESS - 0.03, 0.4), (OPEN_W / 2 - 0.2, RECESS - 0.03, 3.3),
                       (-OPEN_W / 2 + 0.2, RECESS - 0.03, 3.3), "fire", ("n", [(0.0, v_b + 0.01), (0.2, v_b + 0.01), (0.2, v_t - 0.01), (0.0, v_t - 0.01)])))
    for sx in (-1, 1):
        x = sx * (OPEN_W / 2 + 0.05)
        solid.merge(C.lathe_at(x, -0.5, 0.0, [(0.32, 0.0), (0.38, 0.55), (0.34, 0.6), (0.0, 0.58)], 8, "stone", smooth=False,
                               roles=["stone", "trim", "cap"]))
        deco.merge(K.blob(x, -0.5, 0.95, 0.38, 0.38, 0.45, "foliage", segs=6, rings=3))
    solid.merge(C.slab(OPEN_W / 2 - 0.2, -0.75, 3.7, 0.3, 1.1, 3.0, "frame", c=0.04))
    br = C.cell_uv("paper", "blade_" + slot)
    cards.merge(C.face_card(OPEN_W / 2 - 0.35, -0.75, 3.78, 0.95, 2.84, "paper", br, facing="-x", lift=C.LIFT))
    cards.merge(C.face_card(OPEN_W / 2 - 0.05, -0.75, 3.78, 0.95, 2.84, "paper", br, facing="+x", lift=C.LIFT))
    return C.finish([Node("canopy", solid, "solid"), Node("posts", deco, "solid"), Node("cards", cards, "card")],
                    shop_meta("Hotel Halflight", "hotel", slot), cy=False)
