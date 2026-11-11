"""CYBERKIT towers and frontages (cytower.*): six tower silhouettes, street facades, megastructure arch, antenna
spire, crown halo, rooftop garden, balcony units, skybridge and a low corner annex.

N64-era rules: every mass is chamfered or tapered (no raw cuboids), storeys are 4 m and their windows are PAINTED
into the facade texture (wall / wall_alt); lit floors are emissive window bands (kit_card nodes, role fire) a few
centimetres proud of the face, so a tower reads as strips of warm and cool panes at night at a few triangles per
floor. Neon accents (ledge strips, crown halos, edge tubes) sample the pack's light atlas through an accent SLOT
(a/b/c/d) so the same tower recolours with the pack. Towers are free-standing landmark pieces (origin floor_center);
facades, balconies and the annex snap to the CITY GRID (kits/core/cykit.py).
"""
import math

from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .rng import rng

V = "1.0.0"
SLOT = S.enum("a", list(C.SLOTS), "neon accent slot (pack palette roles: a/b/c/d)")


def slot_rect(slot):
    return C.cell_uv("light", slot, inset=0.0)


def slot_uv(slot, tone="bright"):
    """A single (u, v) inside the light-atlas row of `slot`: edge / body / bright / core texel."""
    x, y, w, h, _ = C.LIGHT[slot]
    k = {"edge": 0, "body": 1, "bright": 2, "core": 3}[tone]
    return ((x + w / 2) / C.LIGHT_SIZE, 1.0 - (y + k + 0.5) / C.LIGHT_SIZE)


def gem(cx, cy, cz, r, slot, tone="core", k=6, role="light"):
    """Closed bipyramid lamp / beacon in one atlas colour."""
    uv = slot_uv(slot, tone)
    ring = [(cx + r * math.cos(K.TAU * i / k), cy + r * math.sin(K.TAU * i / k), cz) for i in range(k)]
    verts = ring + [(cx, cy, cz - r * 1.2), (cx, cy, cz + r * 1.2)]
    faces = []
    for i in range(k):
        j = (i + 1) % k
        faces.append((j, i, k))
        faces.append((i, j, k + 1))
    return K.Mesh().add(verts, faces, role, False, [("n", [uv] * 3)] * len(faces)).orient_outward()


def ledge_strips(outline, cx, cy, z, slot, width=0.22, min_len=1.0, lift=C.LIFT):
    """Neon strips (cards) along the outward faces of an outline at height z."""
    m = K.Mesh()
    pts = [(x + cx, y + cy) for x, y in outline]
    rect = slot_rect(slot)
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < min_len:
            continue
        nx, ny = (y1 - y0) / L, -(x1 - x0) / L
        p0 = (x0 + nx * lift, y0 + ny * lift, z)
        p1 = (x1 + nx * lift, y1 + ny * lift, z)
        m.merge(C.strip(p0, p1, width, "light", (nx, ny, 0.0), rect))
    return m


def storeys(z0, z1, start=1):
    out = []
    k = start
    while z0 + (k + 1) * C.STOREY <= z1 + 1e-6:
        out.append(z0 + k * C.STOREY)
        k += 1
    return out


def antenna(cx, cy, z0, h, slot, role="post"):
    m = K.Mesh()
    m.merge(C.frustum(cx, cy, z0, z0 + h, 0.16, 0.05, 6, role))
    for k, f in enumerate((0.35, 0.62)):
        zz = z0 + h * f
        m.merge(C.rod((cx - 0.7 + 0.2 * k, cy, zz), (cx + 0.7 - 0.2 * k, cy, zz), 0.035, 4, "metal"))
    m.merge(gem(cx, cy, z0 + h + 0.18, 0.16, slot, "core"))
    return m


def machine_room(cx, cy, z0, w, d, h):
    return C.taper(cx, cy, z0, z0 + h, w, d, w * 0.86, d * 0.86, 0.3, 0.25, "trim", top="roof")


# ---------------------------------------------------------------- cytower.setback
@register("cytower.setback", V, "structure", {
    "height": S.num(32.0, 16.0, 40.0, "total height (m)"),
    "width": S.num(12.0, 8.0, 16.0), "depth": S.num(10.0, 6.0, 14.0),
    "tiers": S.integer(3, 2, 4, "stacked tiers stepping back"),
    "lit": S.num(0.55, 0.0, 1.0, "share of storeys with lit window bands"),
    "accent": SLOT, "crown": S.enum("mast", ["mast", "halo", "plain"]),
    "skin": S.enum("panel", ["panel", "glass"], "panel facade (wall) or glass curtain (wall_alt)"),
}, "Stepped setback slab tower: chamfered tiers stepping back toward the top, neon ledge strips on every setback, "
   "painted storeys with lit window bands, a machine room and an antenna mast or crown halo.", origin="floor_center")
def setback(P, seed):
    r = rng(seed, "cytower.setback")
    H, W, Dp, n = P["height"], P["width"], P["depth"], P["tiers"]
    skin = "wall" if P["skin"] == "panel" else "wall_alt"
    body, cards = K.Mesh(), K.Mesh()
    zs = [0.0]
    for i in range(n):
        zs.append(round((H - 2.5) * (i + 1) / n / C.STOREY) * C.STOREY if i < n - 1 else H - 2.5)
    for i in range(n):
        f = 1.0 - 0.17 * i
        w, d = W * f, Dp * (1.0 - 0.12 * i)
        cy = 0.06 * Dp * i
        ol = C.cham_rect(w, d, 0.9 - 0.12 * i)
        z0, z1 = zs[i] + (0.32 if i else 0.0), zs[i + 1]
        body.merge(C.prism(ol, z0, z1, skin, "roof", "roof", 0.0, cy))
        cards.merge(C.window_bands(ol, 0.0, cy, storeys(z0, z1, 1 if i == 0 else 0), r, P["lit"]))
        if i < n - 1:
            lo = C.offset_outline(ol, 0.35)
            body.merge(C.prism(lo, z1 - 0.06, z1 + 0.42, "trim", "roof", "trim", 0.0, cy))
            cards.merge(ledge_strips(lo, 0.0, cy, z1 + 0.18, P["accent"]))
    top = zs[-1]
    tw = W * (1.0 - 0.17 * (n - 1))
    tcy = 0.06 * Dp * (n - 1)
    body.merge(machine_room(0.0, tcy + 0.6, top - 0.05, tw * 0.45, Dp * 0.3, 2.4))
    deco = K.Mesh()
    if P["crown"] == "mast":
        deco.merge(antenna(0.0, tcy + 0.6, top + 2.3, 7.0, P["accent"]))
    elif P["crown"] == "halo":
        R = tw * 0.42
        ring = [(R * math.cos(K.TAU * i / 12), tcy + R * 0.55 * math.sin(K.TAU * i / 12), top + 3.2) for i in range(12)]
        deco.merge(C.neon_tube(ring, 0.16, "light", slot_rect(P["accent"]), closed=True))
        for sx in (-1, 1):
            deco.merge(C.rod((sx * R * 0.9, tcy, top - 0.1), (sx * R, tcy, top + 3.2), 0.07, 4, "post"))
    nodes = [Node("tower", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [C.sock("roof", (0, tcy, top), "up", footprint_m=round(tw, 2))],
                                       height_m=H, storeys=int(H // C.STOREY), landmark=True))


# ---------------------------------------------------------------- cytower.needle
@register("cytower.needle", V, "structure", {
    "height": S.num(38.0, 20.0, 40.0), "base": S.num(9.0, 6.0, 12.0, "shaft width at the podium"),
    "taper": S.num(0.55, 0.3, 0.9, "top width / base width"),
    "lit": S.num(0.5, 0.0, 1.0), "accent": SLOT, "rings": S.integer(3, 0, 4, "trim band rings up the shaft"),
}, "Tapered octagonal needle tower on a stepped podium: trim band rings, lit window bands that follow the taper, a "
   "glowing crown halo and a needle spire.", origin="floor_center")
def needle(P, seed):
    r = rng(seed, "cytower.needle")
    H, B, tp = P["height"], P["base"], P["taper"]
    spire = min(8.0, H * 0.2)
    Hs = H - spire
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    pod = C.cham_rect(B * 1.5, B * 1.3, 1.2)
    body.merge(C.prism(pod, 0.0, 4.0, "wall", "roof", "roof"))
    body.merge(C.prism(C.offset_outline(pod, 0.3), 3.9, 4.45, "trim", "roof", "trim"))
    cards.merge(C.window_bands(pod, 0, 0, [0.0], r, 1.0, z_lo=0.6, z_hi=3.2))
    oct0 = C.ngon(B / 2 / math.cos(math.pi / 8), 8, math.pi / 8)
    z0, z1 = 4.3, Hs - 1.0
    for k in range(4):
        za, zb = z0 + (z1 - z0) * k / 4, z0 + (z1 - z0) * (k + 1) / 4
        fa, fb = 1.0 - (1.0 - tp) * k / 4, 1.0 - (1.0 - tp) * (k + 1) / 4
        body.merge(C.rings_loft([[(x * fa, y * fa) for x, y in oct0], [(x * fb, y * fb) for x, y in oct0]], [za, zb + 0.02],
                                "wall_alt", cap_roles=("roof", "roof")))
        for zz in storeys(za, zb, 0):
            fz = 1.0 - (1.0 - tp) * (zz - z0) / (z1 - z0)
            fz2 = 1.0 - (1.0 - tp) * (zz + C.STOREY - z0) / (z1 - z0)
            if r.random() > P["lit"]:
                continue
            row, off = r.randrange(C.FIRE_ROWS), 2.0 * r.randrange(8)
            acc = 0.0
            for i in range(8):
                a0, a1 = oct0[i], oct0[(i + 1) % 8]
                L = math.hypot(a1[0] - a0[0], a1[1] - a0[1])
                nx, ny = (a1[1] - a0[1]) / L, -(a1[0] - a0[0]) / L
                lo_f = fz + (fz2 - fz) * 0.21
                hi_f = fz + (fz2 - fz) * 0.84
                pa = (a0[0] * lo_f + nx * C.LIFT, a0[1] * lo_f + ny * C.LIFT, zz + 0.85)
                pb = (a1[0] * lo_f + nx * C.LIFT, a1[1] * lo_f + ny * C.LIFT, zz + 0.85)
                pc = (a1[0] * hi_f + nx * C.LIFT, a1[1] * hi_f + ny * C.LIFT, zz + 3.35)
                pd = (a0[0] * hi_f + nx * C.LIFT, a0[1] * hi_f + ny * C.LIFT, zz + 3.35)
                vt, vb = 1.0 - row / C.FIRE_ROWS, 1.0 - (row + 1) / C.FIRE_ROWS
                u0, u1 = (acc + off) / C.FIRE_SPAN_M, (acc + off + L * lo_f) / C.FIRE_SPAN_M
                cards.merge(C.quad(pa, pb, pc, pd, "fire", ("n", [(u0, vb + 0.01), (u1, vb + 0.01), (u1, vt - 0.01), (u0, vt - 0.01)])))
                acc += L
        if 0 < k <= P["rings"]:
            ro = [(x * fa * 1.06, y * fa * 1.06) for x, y in oct0]
            body.merge(C.prism(ro, za - 0.25, za + 0.3, "trim", "trim", "trim"))
    ft = tp
    top = [(x * ft, y * ft) for x, y in oct0]
    body.merge(C.rings_loft([top, [(x * 0.7, y * 0.7) for x, y in top]], [z1, Hs], "trim", cap_roles=("roof", "roof")))
    R = B * tp * 0.62
    ring = [(R * math.cos(K.TAU * i / 12), R * math.sin(K.TAU * i / 12), Hs - 0.4) for i in range(12)]
    deco.merge(C.neon_tube(ring, 0.18, "light", slot_rect(P["accent"]), closed=True))
    deco.merge(C.frustum(0, 0, Hs - 0.05, H - 0.3, B * tp * 0.12, 0.04, 6, "chrome"))
    deco.merge(gem(0, 0, H - 0.2, 0.16, P["accent"], "core"))
    nodes = [Node("tower", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [], height_m=H, landmark=True))


# ---------------------------------------------------------------- cytower.drum
@register("cytower.drum", V, "structure", {
    "height": S.num(30.0, 16.0, 40.0), "radius": S.num(6.0, 4.0, 8.0),
    "lit": S.num(0.45, 0.0, 1.0), "accent": SLOT, "fins": S.integer(4, 0, 6, "vertical fins"),
    "cap": S.enum("disc", ["disc", "dome", "pad"], "saucer disc, low dome or helipad crown"),
}, "Round drum tower with a gentle bulge, vertical fins, lit window bands around the drum and a saucer disc, dome or "
   "helipad crown edged with a neon ring.", origin="floor_center")
def drum(P, seed):
    r = rng(seed, "cytower.drum")
    H, Rr = P["height"], P["radius"]
    segs = 12
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    Hc = H - 3.0
    prof = [(Rr * 1.05, 0.0), (Rr * 1.0, 0.75), (Rr * 1.02, Hc * 0.45), (Rr * 0.94, Hc)]
    body.merge(C.lathe_at(0, 0, 0, prof, segs, "wall_alt", smooth=False))
    ring_pts = C.ngon(1.0, segs, 0.0)
    for zz in storeys(0.0, Hc, 1):
        if r.random() > P["lit"]:
            continue
        t = zz / Hc
        rad = Rr * (1.02 if t < 0.45 else 1.02 + (0.94 - 1.02) * (t - 0.45) / 0.55) + C.LIFT * 2
        ol = [(x * rad, y * rad) for x, y in ring_pts]
        cards.merge(C.window_bands(ol, 0, 0, [zz], r, 1.0, min_len=0.5))
    for k in range(P["fins"]):
        a = K.TAU * (k + 0.5) / max(1, P["fins"])
        fin = C.wedge(0, 0, 0.0, 0.45, 1.6, Hc * 0.92, Hc * 0.6, "trim", c=0.04)
        fin.translate(0, Rr * 1.0 + 0.55, 0).rotate_z(a)
        body.merge(fin)
    if P["cap"] == "disc":
        body.merge(C.lathe_at(0, 0, Hc - 0.1, [(Rr * 0.9, 0.0), (Rr * 1.45, 0.9), (Rr * 1.45, 1.3), (Rr * 0.6, 2.2), (0.0, 2.3)], segs, "trim", smooth=False))
        rim = [(Rr * 1.47 * math.cos(K.TAU * i / 16), Rr * 1.47 * math.sin(K.TAU * i / 16), Hc + 1.1) for i in range(16)]
        deco.merge(C.neon_tube(rim, 0.14, "light", slot_rect(P["accent"]), closed=True))
    elif P["cap"] == "dome":
        body.merge(C.lathe_at(0, 0, Hc - 0.1, [(Rr * 0.96, 0.0), (Rr * 0.9, 1.2), (Rr * 0.6, 2.4), (0.0, 3.0)], segs, "wall_alt", smooth=True))
        rim = [(Rr * 0.99 * math.cos(K.TAU * i / 16), Rr * 0.99 * math.sin(K.TAU * i / 16), Hc + 0.3) for i in range(16)]
        deco.merge(C.neon_tube(rim, 0.14, "light", slot_rect(P["accent"]), closed=True))
    else:
        body.merge(C.lathe_at(0, 0, Hc - 0.1, [(Rr * 0.9, 0.0), (Rr * 1.3, 0.7), (Rr * 1.3, 1.0), (0.0, 1.0)], segs, "roof", smooth=False))
        for i in range(8):
            a = K.TAU * i / 8
            deco.merge(gem(Rr * 1.22 * math.cos(a), Rr * 1.22 * math.sin(a), Hc + 1.12, 0.12, P["accent"], "bright"))
        pad = [(Rr * 0.55 * math.cos(K.TAU * i / 16), Rr * 0.55 * math.sin(K.TAU * i / 16), Hc + 0.93) for i in range(16)]
        deco.merge(C.neon_tube(pad, 0.06, "light", slot_rect(P["accent"]), closed=True))
    nodes = [Node("tower", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [], height_m=H, landmark=True))


# ---------------------------------------------------------------- cytower.twin
@register("cytower.twin", V, "structure", {
    "height": S.num(34.0, 18.0, 40.0), "gap": S.num(6.0, 4.0, 10.0, "street gap between the two shafts"),
    "lit": S.num(0.5, 0.0, 1.0), "accent": SLOT, "bridge": S.num(0.66, 0.4, 0.85, "skybridge height fraction"),
}, "Twin slender chamfered towers on a shared podium, joined by a glazed skybridge with a neon underside, stepped "
   "caps and lit window bands.", origin="floor_center")
def twin(P, seed):
    r = rng(seed, "cytower.twin")
    H, gap = P["height"], P["gap"]
    sw = 6.0
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    span = gap + 2 * sw
    pod = C.cham_rect(span + 2.0, sw + 3.0, 1.0)
    body.merge(C.prism(pod, 0.0, 5.0, "wall", "roof", "roof"))
    body.merge(C.prism(C.offset_outline(pod, 0.3), 4.9, 5.45, "trim", "roof", "trim"))
    cards.merge(ledge_strips(C.offset_outline(pod, 0.3), 0, 0, 5.17, P["accent"]))
    for sx in (-1, 1):
        cx = sx * (gap / 2 + sw / 2)
        ol = C.cham_rect(sw, sw, 0.8)
        h = H - 3.0 - (2.0 if sx > 0 else 0.0)
        body.merge(C.prism(ol, 5.3, h, "wall_alt", "roof", "roof", cx, 0.0))
        cards.merge(C.window_bands(ol, cx, 0.0, storeys(5.3, h, 0), r, P["lit"]))
        body.merge(C.taper(cx, 0, h - 0.05, h + 1.6, sw * 0.86, sw * 0.86, sw * 0.5, sw * 0.5, 0.6, 0.3, "trim", top="roof"))
        deco.merge(antenna(cx, 0, h + 1.55, 3.0 + 1.5 * (sx < 0), P["accent"]))
    zb = 5.3 + (H - 8.3) * P["bridge"]
    bw = gap + 0.6
    br = C.cham_rect(bw, 2.6, 0.5)
    body.merge(C.prism(br, zb, zb + 3.2, "wall_alt", "roof", "trim"))
    deco.merge(C.neon_tube([(-bw / 2 + 0.3, -1.05, zb - 0.12), (bw / 2 - 0.3, -1.05, zb - 0.12)], 0.08, "light", slot_rect(P["accent"])))
    deco.merge(C.neon_tube([(-bw / 2 + 0.3, 1.05, zb - 0.12), (bw / 2 - 0.3, 1.05, zb - 0.12)], 0.08, "light", slot_rect(P["accent"])))
    cards.merge(C.window_bands(br, 0, 0, [zb - 0.6], r, 1.0, min_len=2.0))
    nodes = [Node("towers", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [], height_m=H, landmark=True))


# ---------------------------------------------------------------- cytower.wedge
@register("cytower.wedge", V, "structure", {
    "height": S.num(30.0, 16.0, 40.0), "width": S.num(10.0, 7.0, 14.0), "depth": S.num(8.0, 6.0, 12.0),
    "slope": S.num(8.0, 3.0, 12.0, "roof drop from back to front (m)"), "lit": S.num(0.5, 0.0, 1.0), "accent": SLOT,
}, "Wedge tower: a chamfered slab cut by a steep sloped roof, a full-height neon edge tube on the front corner, a "
   "rooftop billboard frame on the slope and lit window bands.", origin="floor_center")
def wedge(P, seed):
    r = rng(seed, "cytower.wedge")
    H, W, Dp, sl = P["height"], P["width"], P["depth"], P["slope"]
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    hf = H - sl
    body.merge(C.wedge(0, 0, 0.0, W, Dp, hf, H, "wall", c=0.7, top="roof"))
    ol = C.cham_rect(W, Dp, 0.7)
    cards.merge(C.window_bands(ol, 0, 0, storeys(0.0, hf - 0.5, 1), r, P["lit"]))
    body.merge(C.prism(C.offset_outline(ol, 0.3), 3.6, 4.1, "trim", "trim", "trim"))
    cards.merge(ledge_strips(C.offset_outline(ol, 0.3), 0, 0, 3.85, P["accent"], min_len=4.0))
    x0, y0 = W / 2 - 0.25, -Dp / 2 + 0.25
    deco.merge(C.neon_tube([(x0 + 0.12, y0 - 0.12, 4.4), (x0 + 0.12, y0 - 0.12, hf - 0.2)], 0.12, "light", slot_rect(P["accent"])))
    bz = hf + sl * 0.35
    deco.merge(C.rod((-W * 0.3, 0.2, hf + sl * 0.5 - 0.3), (-W * 0.3, 0.2, bz + 3.0), 0.09, 4, "post"))
    deco.merge(C.rod((W * 0.3, 0.2, hf + sl * 0.5 - 0.3), (W * 0.3, 0.2, bz + 3.0), 0.09, 4, "post"))
    panel = C.bevel_box(0, 0.0, bz, W * 0.75, 0.3, 2.8, "frame", bevel=0.06)
    body.merge(panel)
    cards.merge(C.face_card(0, -0.15, bz + 0.2, W * 0.7, 2.4, "book", C.cell_uv("book", "billboard"), lift=C.LIFT))
    nodes = [Node("tower", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [], height_m=H, landmark=True))


# ---------------------------------------------------------------- cytower.stack
@register("cytower.stack", V, "structure", {
    "height": S.num(28.0, 14.0, 40.0), "width": S.num(10.0, 7.0, 14.0), "depth": S.num(9.0, 6.0, 12.0),
    "blocks": S.integer(4, 3, 6, "stacked offset blocks"), "lit": S.num(0.5, 0.0, 1.0), "accent": SLOT,
    "clutter": S.num(0.6, 0.0, 1.0, "AC boxes and balconies on the faces"),
}, "Dense residential stack: offset chamfered blocks cantilevered over each other, AC boxes and balcony slabs on the "
   "faces, a rooftop water tank and antenna clutter, warm lit windows.", origin="floor_center")
def stack(P, seed):
    r = rng(seed, "cytower.stack")
    H, W, Dp, n = P["height"], P["width"], P["depth"], P["blocks"]
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    hs = [max(2, round(H / n / C.STOREY)) * C.STOREY for _ in range(n)]
    scale = (H - 3.0) / sum(hs)
    z = 0.0
    top = (0.0, 0.0, 0.0, W, Dp)
    for i in range(n):
        h = hs[i] * scale
        h = max(C.STOREY, round(h / C.STOREY) * C.STOREY) if i < n - 1 else max(C.STOREY, H - 3.0 - z)
        w = W * (0.82 + 0.22 * r.random())
        d = Dp * (0.82 + 0.22 * r.random())
        ox = (r.random() - 0.5) * W * 0.18
        oy = (r.random() - 0.5) * Dp * 0.18
        ol = C.cham_rect(w, d, 0.5)
        z0 = z + (0.02 if i else 0.0)
        body.merge(C.prism(ol, z0, z + h, "wall", "roof", "roof", ox, oy))
        cards.merge(C.window_bands(ol, ox, oy, storeys(z0, z + h, 1 if i == 0 else 0), r, P["lit"]))
        for _ in range(1 + int(r.random() < P["clutter"])):
            side = r.randrange(4)
            zz = z + C.STOREY * (0.25 + r.random() * max(0.2, h / C.STOREY - 1.0))
            t = (r.random() - 0.5) * 0.7
            if side == 0:
                px, py, yaw = ox + t * w, oy - d / 2, 0
            elif side == 1:
                px, py, yaw = ox + w / 2, oy + t * d, 90
            elif side == 2:
                px, py, yaw = ox + t * w, oy + d / 2, 180
            else:
                px, py, yaw = ox - w / 2, oy + t * d, 270
            box = C.slab(0, -0.3, 0, 0.9, 0.62, 0.62, "body_alt")
            box.rotate_z(math.radians(yaw)).translate(px, py, zz)
            body.merge(box)
            if r.random() < 0.4:
                sl = C.slab(0, -0.55, 0, 2.2, 1.1, 0.16, "trim")
                sl.merge(C.rod((-1.08, -1.06, 0.9), (1.08, -1.06, 0.9), 0.035, 4, "rail"))
                sl.rotate_z(math.radians(yaw)).translate(px + 1.2 * (side % 2 == 0), py + 1.2 * (side % 2 == 1), zz - 0.9)
                body.merge(sl)
        z += h
        top = (ox, oy, z, w, d)
    ox, oy, zt, w, d = top
    body.merge(C.lathe_at(ox - w * 0.2, oy + d * 0.15, zt - 0.05, [(1.1, 0.0), (1.1, 2.4), (0.2, 3.0), (0.0, 3.05)], 6, "metal",
                          smooth=False))
    deco.merge(gem(ox + w * 0.25, oy - d * 0.1, zt + 0.3, 0.14, P["accent"], "core"))
    deco.merge(C.neon_tube([(ox - w / 2 + 0.4, oy - d / 2 - 0.12, zt - 0.6), (ox + w / 2 - 0.4, oy - d / 2 - 0.12, zt - 0.6)], 0.09,
                           "light", slot_rect(P["accent"])))
    nodes = [Node("tower", body, "solid"), Node("crown", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("free", None, [], height_m=H, landmark=True))


# ---------------------------------------------------------------- cytower.arch
@register("cytower.arch", V, "structure", {
    "span": S.num(16.0, 12.0, 24.0, "clear span over the street"), "height": S.num(22.0, 14.0, 30.0),
    "lit": S.num(0.7, 0.0, 1.0), "accent": SLOT, "sign": S.boolean(True, "hanging glyph sign under the span"),
}, "Megastructure arch over a street: two tapered chamfered legs, a deep span block with lit window bands, a neon "
   "underside and an optional hanging blade sign. A landmark gateway between canyon blocks.", origin="floor_center")
def arch(P, seed):
    r = rng(seed, "cytower.arch")
    S_, H = P["span"], P["height"]
    leg = 4.0
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    zs = H - 7.0
    for sx in (-1, 1):
        cx = sx * (S_ / 2 + leg / 2)
        body.merge(C.taper(cx, 0, 0.0, zs + 0.3, leg + 1.2, 6.0, leg, 4.6, 0.6, 0.5, "wall", top="roof"))
        cards.merge(C.window_bands(C.cham_rect(leg, 4.6, 0.5), cx, 0, storeys(4.0, zs - 2.0, 0), r, P["lit"] * 0.6, min_len=2.0,
                                   lift=0.65))
    sp = C.cham_rect(S_ + 2 * leg + 1.0, 5.2, 0.8)
    body.merge(C.prism(sp, zs, H - 1.0, "wall_alt", "roof", "trim"))
    body.merge(C.taper(0, 0, H - 1.05, H, S_ + 2 * leg + 1.0, 5.2, S_ + 2 * leg - 1.0, 4.0, 0.8, 0.6, "trim", top="roof"))
    cards.merge(C.window_bands(sp, 0, 0, [zs + 0.2], r, 1.0, min_len=3.0, z_lo=0.6, z_hi=3.2))
    for y in (-1.9, 1.9):
        deco.merge(C.neon_tube([(-S_ / 2 + 0.4, y, zs - 0.14), (S_ / 2 - 0.4, y, zs - 0.14)], 0.11, "light", slot_rect(P["accent"])))
    if P["sign"]:
        for sx in (-1, 1):
            deco.merge(C.rod((sx * 0.8, 0, zs + 0.05), (sx * 0.8, 0, zs - 1.2), 0.05, 4, "post"))
        body.merge(C.bevel_box(0, 0, zs - 4.6, 2.2, 0.36, 3.5, "frame", bevel=0.05))
        cards.merge(C.face_card(0, -0.18, zs - 4.45, 1.9, 3.2, "paper", C.cell_uv("paper", "blade_" + P["accent"]), lift=C.LIFT))
        cards.merge(C.face_card(0, 0.18, zs - 4.45, 1.9, 3.2, "paper", C.cell_uv("paper", "blade_" + P["accent"]), facing="+y", lift=C.LIFT))
    nodes = [Node("arch", body, "solid"), Node("neon", deco, "solid"), Node("windows", cards, "card")]
    return C.finish(nodes, C.grid_meta("street_span", None, [C.sock("street_span", (0, 0, 0), "s", span_m=S_)], height_m=H,
                                       landmark=True))


# ---------------------------------------------------------------- cytower.spire
@register("cytower.spire", V, "structure", {
    "height": S.num(10.0, 5.0, 16.0), "accent": SLOT, "dishes": S.integer(2, 0, 3),
}, "Rooftop antenna spire: a tapered four-leg lattice mast with cross braces, dish antennas and a beacon tip.",
    origin="floor_center")
def spire(P, seed):
    H = P["height"]
    m, deco = K.Mesh(), K.Mesh()
    b0, b1 = 1.0, 0.18
    corners = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    for sx, sy in corners:
        m.merge(C.rod((sx * b0, sy * b0, 0.0), (sx * b1, sy * b1, H), 0.06, 4, "post"))
    for k in range(1, 5):
        t = k / 5.0
        b = b0 + (b1 - b0) * t
        z = H * t
        for i in range(4):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
            pa, pb = (ax * b, ay * b, z), (bx * b, by * b, z)
            qa = tuple(pa[j] + (pb[j] - pa[j]) * 0.06 for j in range(3))
            qb = tuple(pa[j] + (pb[j] - pa[j]) * 0.94 for j in range(3))
            m.merge(C.rod(qa, qb, 0.03, 4, "metal"))
    m.merge(C.bevel_box(0, 0, 0.0, 2.6, 2.6, 0.3, "trim", bevel=0.06))
    for k in range(P["dishes"]):
        z = H * (0.3 + 0.25 * k)
        a = K.TAU * (0.15 + 0.37 * k)
        d = C.lathe_at(0, 0, 0, [(0.0, 0.0), (0.45, 0.06), (0.75, 0.24), (0.7, 0.28), (0.0, 0.1)], 8, "chrome", smooth=True)
        d.rotate_y(math.pi / 2).translate(1.0, 0, 0).rotate_z(a).translate(0, 0, z)
        m.merge(d)
    deco.merge(gem(0, 0, H + 0.25, 0.2, P["accent"], "core"))
    deco.merge(gem(0, 0, H * 0.6, 0.12, P["accent"], "bright"))
    return C.finish([Node("mast", m, "solid"), Node("beacon", deco, "solid")],
                    C.grid_meta("roof", None, [C.sock("roof", (0, 0, 0), "down", footprint_m=2.6)], height_m=H))


# ---------------------------------------------------------------- cytower.crown
@register("cytower.crown", V, "structure", {
    "diameter": S.num(9.0, 5.0, 14.0), "accent": SLOT, "style": S.enum("halo", ["halo", "double", "fan"]),
}, "Rooftop crown: a neon halo ring on raked struts (single, double ring, or a fan of radiating light spokes) over "
   "a chamfered plinth. Tops any tower roof socket.", origin="floor_center")
def crown(P, seed):
    D_ = P["diameter"]
    R = D_ / 2
    base, deco = K.Mesh(), K.Mesh()
    base.merge(C.taper(0, 0, 0.0, 1.0, D_ * 0.6, D_ * 0.6, D_ * 0.5, D_ * 0.5, 0.8, 0.6, "trim", top="roof"))
    rect = slot_rect(P["accent"])
    if P["style"] in ("halo", "double"):
        for k, (rr, zz) in enumerate(((R, 3.6), (R * 0.72, 2.6))):
            if k and P["style"] == "halo":
                break
            ring = [(rr * math.cos(K.TAU * i / 16), rr * math.sin(K.TAU * i / 16), zz) for i in range(16)]
            deco.merge(C.neon_tube(ring, 0.15, "light", rect, closed=True))
        for i in range(4):
            a = K.TAU * (i + 0.5) / 4
            base.merge(C.rod((D_ * 0.22 * math.cos(a), D_ * 0.22 * math.sin(a), 0.95), (R * 0.98 * math.cos(a), R * 0.98 * math.sin(a), 3.6),
                             0.08, 4, "post"))
    else:
        for i in range(7):
            a = math.radians(-60 + 20 * i)
            p0 = (0.0, 0.0, 1.0)
            p1 = (R * math.sin(a), 0.0, 1.0 + R * math.cos(a))
            deco.merge(C.neon_tube([p0, p1], 0.12, "light", rect))
        base.merge(C.bevel_box(0, 0, 0.9, 1.2, 0.8, 0.6, "frame", bevel=0.06))
    return C.finish([Node("plinth", base, "solid"), Node("halo", deco, "solid")],
                    C.grid_meta("roof", None, [C.sock("roof", (0, 0, 0), "down", footprint_m=round(D_ * 0.6, 2))]))


# ---------------------------------------------------------------- cytower.garden
@register("cytower.garden", V, "furniture_large", {
    "size": S.num(6.0, 4.0, 6.0, "square module (m)"), "trees": S.integer(3, 0, 5), "pergola": S.boolean(True),
    "accent": SLOT,
}, "Rooftop garden module: chamfered planter beds with lawn and soil, small trees and clipped hedges, a pergola "
   "frame, a bench and low garden lamps. The only living green of the city, kept tidy (no clutter).",
    origin="floor_center")
def garden(P, seed):
    r = rng(seed, "cytower.garden")
    s = P["size"]
    beds, plants, deco = K.Mesh(), K.Mesh(), K.Mesh()
    beds.merge(C.cham_prism(0, 0, 0.0, 0.12, s, s, 0.4, "trim", top="roof"))
    for sx, sy, w, d in ((-1, 0, s * 0.3, s * 0.9), (1, 1, s * 0.5, s * 0.3)):
        cx, cy = sx * (s / 2 - w / 2 - 0.15), sy * (s / 2 - d / 2 - 0.15)
        beds.merge(C.cham_prism(cx, cy, 0.1, 0.65, w, d, 0.12, "stone", top="grass"))
    for k in range(P["trees"]):
        tx = -(s / 2 - s * 0.15 - 0.15)
        ty = -s * 0.35 + k * (s * 0.7 / max(1, P["trees"] - 1)) if P["trees"] > 1 else 0.0
        h = 1.6 + 0.7 * r.random()
        plants.merge(C.frustum(tx, ty, 0.6, 0.6 + h, 0.09, 0.06, 4, "bark"))
        plants.merge(K.blob(tx, ty, 0.6 + h + 0.35, 0.65, 0.65, 0.55, "foliage", segs=6, rings=3))
    plants.merge(C.taper(s / 2 - s * 0.25 - 0.15, s / 2 - s * 0.15 - 0.15, 0.6, 1.2, s * 0.46, s * 0.24, s * 0.4, s * 0.18, 0.12, 0.1, "foliage"))
    if P["pergola"]:
        x0, y0 = s * 0.05, -s * 0.3
        for px in (x0 - 1.2, x0 + 1.4):
            for py in (y0 - 1.0, y0 + 1.0):
                deco.merge(C.rod((px, py, 0.1), (px, py, 2.5), 0.07, 4, "post"))
        for k in range(4):
            yy = y0 - 0.95 + k * 0.63
            deco.merge(C.rod((x0 - 1.45, yy, 2.55), (x0 + 1.65, yy, 2.55), 0.05, 4, "wood"))
        deco.merge(C.slab(x0 + 0.1, y0, 0.1, 1.6, 0.5, 0.42, "wood"))
    for k in range(2):
        a = K.TAU * (k + 0.2) / 3
        lx, ly = s * 0.38 * math.cos(a), s * 0.38 * math.sin(a)
        deco.merge(C.frustum(lx, ly, 0.1, 0.55, 0.06, 0.05, 4, "post"))
        deco.merge(gem(lx, ly, 0.66, 0.09, P["accent"], "bright"))
    return C.finish([Node("beds", beds, "solid"), Node("plants", plants, "solid"), Node("pergola", deco, "solid")],
                    C.grid_meta("cell_block_centre", [1, 1], [C.sock("roof", (0, 0, 0), "down", footprint_m=s)],
                                bake_lights=[C.light((0, 0, 1.2), 3.5, 0.6)]))


# ---------------------------------------------------------------- cytower.facade
@register("cytower.facade", V, "shell", {
    "cells": S.integer(3, 1, 4, "frontage length in 4 m cells"),
    "storeys": S.integer(5, 2, 7, "storeys above the shop floor"),
    "shop": S.enum("open", ["open", "closed", "none"], "ground-floor shop slot: open recess, shuttered, or plain wall"),
    "skin": S.enum("panel", ["panel", "glass"]),
    "lit": S.num(0.55, 0.0, 1.0), "balconies": S.num(0.35, 0.0, 1.0), "accent": SLOT,
    "roofline": S.enum("cornice", ["cornice", "neon", "stepped"]),
}, "Street facade (canyon wall): a one-sided storey frontage on a cell edge facing the street, ground-floor shop slots "
   "(open recess or roll shutter) that take the shopfront kits, painted windows with lit bands, balcony slabs, end "
   "pilasters and a cornice, neon or stepped roofline.", origin="opening_floor")
def facade(P, seed):
    r = rng(seed, "cytower.facade")
    L = C.CELL * P["cells"]
    H = 4.6 + C.STOREY * P["storeys"]
    skin = "wall" if P["skin"] == "panel" else "wall_alt"
    sh, cards, solid = K.Mesh(), K.Mesh(), K.Mesh()
    slots = []
    if P["shop"] != "none":
        for k in range(P["cells"]):
            if P["cells"] >= 3 and k % 2 == 1:
                continue
            cx = -L / 2 + C.CELL * (k + 0.5) if P["cells"] < 3 else -L / 2 + C.CELL * (k + 1.0)
            if cx + 3.6 / 2 > L / 2 - 0.4:
                cx = L / 2 - 0.4 - 1.8
            slots.append(cx)
    sw, shh = 3.6, 3.7
    # front wall: z-strips between openings (one-sided quads facing -Y, metric UVs so storeys align at z = 4.6 + 4k)
    xs = sorted({-L / 2, L / 2} | {x for c in slots for x in (c - sw / 2, c + sw / 2)})
    zbreak = [0.0, shh, 4.6] + [4.6 + C.STOREY * k for k in range(1, P["storeys"] + 1)]
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        in_slot = any(abs((x0 + x1) / 2 - c) < sw / 2 - 1e-6 for c in slots)
        for j in range(len(zbreak) - 1):
            z0, z1 = zbreak[j], zbreak[j + 1]
            if in_slot and z1 <= shh + 1e-6:
                continue
            role = "stone" if z1 <= 4.6 + 1e-6 else skin
            sh.merge(C.quad((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1), role,
                            ("m", [(x0, z0 - 4.6), (x1, z0 - 4.6), (x1, z1 - 4.6), (x0, z1 - 4.6)])))
    for c in slots:
        x0, x1, d = c - sw / 2, c + sw / 2, 2.4
        # recess: back wall, sides and ceiling face the street (one-sided), so the slot never shows through
        if P["shop"] == "closed":
            sh.merge(C.quad((x0, 0.25, 0), (x1, 0.25, 0), (x1, 0.25, shh), (x0, 0.25, shh), "door",
                            ("m", [(x0, 0), (x1, 0), (x1, shh), (x0, shh)])))
            d = 0.25
        else:
            sh.merge(C.quad((x0, d, 0), (x1, d, 0), (x1, d, shh), (x0, d, shh), "stone"))
        sh.merge(C.quad((x0, 0, 0), (x0, d, 0), (x0, d, shh), (x0, 0, shh), "stone"))
        sh.merge(C.quad((x1, d, 0), (x1, 0, 0), (x1, 0, shh), (x1, d, shh), "stone"))
        sh.merge(C.quad((x0, 0, shh), (x0, d, shh), (x1, d, shh), (x1, 0, shh), "ceiling"))
        sh.merge(C.quad((x0, d, 0), (x1, d, 0), (x1, 0, 0), (x0, 0, 0), "floor").flip())
        solid.merge(C.bevel_box(c, -0.14, shh, sw + 0.5, 0.3, 0.36, "frame", bevel=0.05))
    # shop-floor fascia band + pilasters + roofline
    solid.merge(C.bevel_box(0, -0.12, 4.15, L - 0.1, 0.26, 0.45, "trim", bevel=0.05))
    cards.merge(C.strip((-L / 2 + 0.3, -0.27, 4.38), (L / 2 - 0.3, -0.27, 4.38), 0.12, "light", (0, -1, 0), slot_rect(P["accent"])))
    for sx in (-1, 1):
        solid.merge(C.taper(sx * (L / 2 - 0.25), -0.1, 0.0, H + 0.3, 0.62, 0.5, 0.5, 0.42, 0.08, 0.06, "trim", top="roof"))
    if P["roofline"] == "cornice":
        solid.merge(C.bevel_box(0, -0.2, H - 0.05, L - 0.2, 0.55, 0.5, "trim", bevel=0.08))
    elif P["roofline"] == "neon":
        solid.merge(C.bevel_box(0, -0.12, H - 0.05, L - 0.2, 0.36, 0.3, "trim", bevel=0.05))
        cards.merge(C.strip((-L / 2 + 0.4, -0.31, H + 0.1), (L / 2 - 0.4, -0.31, H + 0.1), 0.16, "light", (0, -1, 0), slot_rect(P["accent"])))
    else:
        for k in range(P["cells"]):
            hh = 0.6 + 0.9 * ((k + seed) % 2)
            solid.merge(C.bevel_box(-L / 2 + C.CELL * (k + 0.5), 0.15, H - 0.05, C.CELL - 0.3, 0.7, hh, "trim", bevel=0.08))
    # lit window bands on the storeys (front face only)
    for k in range(P["storeys"]):
        if r.random() > P["lit"]:
            continue
        z = 4.6 + C.STOREY * k
        row, off = r.randrange(C.FIRE_ROWS), 2.0 * r.randrange(8)
        v_t, v_b = 1.0 - row / C.FIRE_ROWS, 1.0 - (row + 1) / C.FIRE_ROWS
        u0, u1 = (off + 0.4) / C.FIRE_SPAN_M, (off + L - 0.4) / C.FIRE_SPAN_M
        cards.merge(C.quad((-L / 2 + 0.55, -C.LIFT, z + 0.85), (L / 2 - 0.55, -C.LIFT, z + 0.85), (L / 2 - 0.55, -C.LIFT, z + 3.35),
                           (-L / 2 + 0.55, -C.LIFT, z + 3.35), "fire",
                           ("n", [(u0, v_b + 0.01), (u1, v_b + 0.01), (u1, v_t - 0.01), (u0, v_t - 0.01)])))
    # balcony slabs with rails on some storeys
    socks = []
    for k in range(P["storeys"]):
        for b in range(P["cells"]):
            if r.random() >= P["balconies"] or k == P["storeys"] - 1:
                continue
            bx = -L / 2 + C.CELL * (b + 0.5)
            z = 4.6 + C.STOREY * k
            solid.merge(C.slab(bx, -0.6, z - 0.05, 2.8, 1.2, 0.2, "trim"))
            solid.merge(C.rod((bx - 1.35, -1.15, z + 1.05), (bx + 1.35, -1.15, z + 1.05), 0.04, 4, "rail"))
            for sx in (-1, 1):
                solid.merge(C.rod((bx + sx * 1.35, -1.15, z + 0.1), (bx + sx * 1.35, -1.15, z + 1.08), 0.035, 4, "rail"))
    for c in slots:
        socks.append(C.sock("shopfront", (c, 0, 0), "s", width_m=sw, height_m=shh))
    for k in range(P["cells"] + 1):
        x = -L / 2 + C.CELL * k
        if abs(x) < L / 2 - 0.5:
            socks.append(C.sock("sign_wall", (x, 0, 4.6 + 0.4), "s"))
    socks.append(C.sock("roof_edge", (0, 0, H), "up", length_m=L))
    meta = C.grid_meta("cell_edge", [P["cells"], 0], socks, height_m=round(H, 2), storey_m=C.STOREY, shop_slots=len(slots))
    return C.finish([Node("front", C.weld(sh), "shell"), Node("trim", solid, "solid"), Node("windows", cards, "card")], meta,
                    cy=False)


# ---------------------------------------------------------------- cytower.balcony
@register("cytower.balcony", V, "furniture", {
    "width": S.num(2.8, 1.6, 4.0), "kit": S.enum("ac", ["plain", "ac", "laundry", "planter"]), "accent": SLOT,
}, "Wall-mounted balcony unit: a bevelled slab on brackets, rail panel, and an AC box, laundry line or planter; a "
   "small neon edge on the slab lip. Mounts on any facade storey (origin on the wall face).", origin="opening_floor")
def balcony(P, seed):
    W = P["width"]
    m, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    m.merge(C.slab(0, -0.6, 0.6, W, 1.2, 0.2, "trim"))
    for sx in (-1, 1):
        m.merge(C.wedge(sx * (W / 2 - 0.2), -0.35, 0.0, 0.12, 0.7, 0.05, 0.62, "metal", c=0.01))
    m.merge(C.slab(0, -1.16, 0.79, W - 0.1, 0.05, 0.6, "rail", c=0.01))
    m.merge(C.rod((-W / 2 + 0.04, -1.16, 1.5), (W / 2 - 0.04, -1.16, 1.5), 0.04, 4, "rail"))
    for sx in (-1, 1):
        m.merge(C.rod((sx * (W / 2 - 0.05), -1.16, 0.78), (sx * (W / 2 - 0.05), -1.16, 1.52), 0.035, 4, "rail"))
        m.merge(C.rod((sx * (W / 2 - 0.05), -0.05, 1.5), (sx * (W / 2 - 0.05), -1.12, 1.5), 0.03, 4, "rail"))
    cards.merge(C.strip((-W / 2 + 0.1, -1.22, 0.7), (W / 2 - 0.1, -1.22, 0.7), 0.06, "light", (0, -1, 0), slot_rect(P["accent"])))
    k = P["kit"]
    if k == "ac":
        deco.merge(C.slab(W * 0.25, -0.45, 0.79, 0.9, 0.6, 0.62, "body_alt"))
        cards.merge(C.face_card(W * 0.25, -0.76, 0.86, 0.48, 0.48, "metal", lift=0.0))
    elif k == "laundry":
        for sx in (-1, 1):
            deco.merge(C.rod((sx * (W / 2 - 0.1), -1.1, 1.7), (sx * (W / 2 - 0.1), -1.1, 2.1), 0.025, 4, "post"))
        deco.merge(C.rod((-W / 2 + 0.1, -1.1, 2.08), (W / 2 - 0.1, -1.1, 2.08), 0.012, 3, "rope"))
        for i, role in enumerate(("quilt", "cushion", "knit")):
            x = -W / 3 + i * W / 3
            cards.merge(C.face_card(x, -1.1, 1.45, 0.55, 0.6, role, None, facing="-y"))
            cards.merge(C.face_card(x, -1.1, 1.45, 0.55, 0.6, role, None, facing="+y"))
    elif k == "planter":
        deco.merge(C.slab(-W * 0.2, -0.5, 0.79, 1.0, 0.4, 0.35, "stone", top="cap"))
        deco.merge(K.blob(-W * 0.2, -0.5, 1.35, 0.5, 0.25, 0.32, "foliage", segs=6, rings=3))
    return C.finish([Node("slab", m, "solid"), Node("kit", deco, "solid"), Node("cards", cards, "card")],
                    C.grid_meta("wall_face", None, [C.sock("wall_mount", (0, 0, 0), "n")]), cy=False)


# ---------------------------------------------------------------- cytower.skybridge
@register("cytower.skybridge", V, "structure", {
    "span": S.num(12.0, 8.0, 16.0), "accent": SLOT, "lit": S.num(0.8, 0.0, 1.0),
}, "Enclosed skybridge spanning a street between two towers: a chamfered glazed tube with end flanges, lit window "
   "band and a neon underside strip. Origin at the deck centre; placed at height between facades.",
    origin="floor_center")
def skybridge(P, seed):
    r = rng(seed, "cytower.skybridge")
    Sp = P["span"]
    m, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    sec = [(-1.6, 0.0), (1.6, 0.0), (1.6, 2.9), (1.15, 3.4), (-1.15, 3.4), (-1.6, 2.9)]
    rings = [[(x, y, z) for y, z in sec] for x in (-Sp / 2, Sp / 2)]
    m.merge(K.loft(rings, "wall_alt", smooth=False, cap_roles=("trim", "trim")))
    for sx in (-1, 1):
        m.merge(C.bevel_box(sx * (Sp / 2 - 0.3), 0, -0.3, 0.7, 4.0, 4.0, "trim", bevel=0.08))
    cards.merge(C.window_bands([(-Sp / 2 + 0.7, -1.6), (Sp / 2 - 0.7, -1.6), (Sp / 2 - 0.7, 1.6), (-Sp / 2 + 0.7, 1.6)], 0, 0, [0.0],
                               r, 1.0 if r.random() < P["lit"] else 0.0, min_len=4.0, z_lo=0.7, z_hi=2.6))
    deco.merge(C.neon_tube([(-Sp / 2 + 0.7, 0, -0.06), (Sp / 2 - 0.7, 0, -0.06)], 0.08, "light", slot_rect(P["accent"])))
    return C.finish([Node("tube", m, "solid"), Node("neon", deco, "solid"), Node("windows", cards, "card")],
                    C.grid_meta("street_span", None, [C.sock("street_span", (0, 0, 0), "s", span_m=Sp)]))


# ---------------------------------------------------------------- cytower.annex
@register("cytower.annex", V, "building", {
    "cells": S.integer(2, 1, 3, "footprint in cells (square)"), "storeys": S.integer(2, 1, 4),
    "corner": S.boolean(True, "chamfered street corner with a corner sign"), "lit": S.num(0.6, 0.0, 1.0), "accent": SLOT,
}, "Low corner building: a 1-4 storey chamfered block with a corner sign mast, rooftop AC boxes and water tank, lit "
   "window bands; fills street corners and rooftop views between towers.", origin="floor_center")
def annex(P, seed):
    r = rng(seed, "cytower.annex")
    w = C.CELL * P["cells"] - 0.4
    H = 4.6 + C.STOREY * (P["storeys"] - 1) + 0.4
    m, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    ol = C.cham_rect(w, w, 1.6 if P["corner"] else 0.4)
    m.merge(C.prism(ol, 0.0, H, "wall", "roof", "roof"))
    m.merge(C.prism(C.offset_outline(ol, 0.25), 4.1, 4.6, "trim", "trim", "trim"))
    cards.merge(ledge_strips(C.offset_outline(ol, 0.25), 0, 0, 4.35, P["accent"], min_len=1.5))
    cards.merge(C.window_bands(ol, 0, 0, [0.0] + storeys(0.6, H, 1), r, P["lit"], z_lo=0.8, z_hi=3.4))
    m.merge(C.prism(C.offset_outline(ol, 0.15), H - 0.05, H + 0.6, "trim", "roof", "trim"))
    for k in range(2):
        m.merge(C.bevel_box(-w * 0.2 + k * 1.3, w * 0.15, H + 0.55, 1.0, 0.7, 0.7, "body_alt", bevel=0.05))
    if P["corner"]:
        cx, cy = w / 2 - 0.5, -w / 2 + 0.5
        deco.merge(C.rod((cx + 0.25, cy - 0.25, 4.6), (cx + 0.25, cy - 0.25, H + 3.0), 0.08, 4, "post"))
        m.merge(C.bevel_box(cx + 0.9, cy - 0.9, H - 1.0, 0.9, 0.9, 3.6, "frame", bevel=0.05))
        rect = C.cell_uv("paper", "blade_" + P["accent"])
        for fac, dx, dy in (("-y", 0.0, -0.46), ("+x", 0.46, 0.0)):
            cards.merge(C.face_card(cx + 0.9 + dx, cy - 0.9 + dy, H - 0.85, 0.8, 3.3, "paper", rect, facing=fac, lift=C.LIFT))
    return C.finish([Node("block", m, "solid"), Node("mast", deco, "solid"), Node("cards", cards, "card")],
                    C.grid_meta("cell_block_centre", [P["cells"], P["cells"]], [C.sock("roof", (0, 0, H + 0.6), "up")],
                                height_m=round(H, 2)))
