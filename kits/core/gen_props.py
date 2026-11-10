"""Small props (signage, books, keys, tools, vessels, devices), soft goods, sky backdrop, particle
cards. Theme-agnostic: shapes + material roles only."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .genutil import finalize, post
from .rng import rng

V = "3.0.0"
SOFT = ["cushion", "quilt", "fabric", "knit", "fur", "leather"]


def _xz(outline, y0, y1, role):
    m = K.prism(outline, y0, y1, role)
    m.apply(lambda v: np.stack([v[:, 0], v[:, 2], v[:, 1]], 1))
    return m.orient_outward()


# ------------------------------------------------------------------ signage
def _sign_top(P):
    """Overall height of the sign assembly for each kind (used by the fail-closed rule)."""
    k, h, ph = P["kind"], P["height"], P["post_height"]
    if k == "post":
        return ph + h
    if k == "arrow":
        return ph + 1.15 * h
    if k == "hanging":
        return 0.9 * ph + h + 0.4
    return h + 0.05  # standing A-board / wall plaque


@register("prop.sign", V, "prop", {
    "kind": S.enum("post", ["post", "hanging", "standing", "plaque", "arrow"]),
    "width": S.num(0.6, 0.15, 1.4), "height": S.num(0.35, 0.1, 1.0), "board_shape": S.enum("rect", ["rect", "rounded_rect", "oval", "arch"]),
    "text_lines": S.integer(2, 0, 4, "abstract glyph strips"), "post_height": S.num(1.2, 0.5, 1.5),
    "board_role": S.enum("wood", ["wood", "metal", "paper", "body", "stone", "screen"]),
    "text_role": S.enum("trim", ["trim", "paper", "light", "metal", "band"]),
}, "Sign: post sign, hanging (bracket + chains as rods), standing A-board, wall plaque (wall_mounted variant), arrow; text = abstract glyph strips.",
    rules=lambda P: ("sign assembly height %.2f m exceeds the 1.6 m prop-class extent (lower post_height or height)" % _sign_top(P))
    if _sign_top(P) > 1.58 else None)
def sign(P, seed):
    w, h = P["width"], P["height"]
    r = rng(seed, "sign")
    t = 0.04
    if P["kind"] == "arrow":
        outline = [(-w / 2, 0), (w / 2 - h / 2, 0), (w / 2 - h / 2, -h * 0.15), (w / 2, h / 2), (w / 2 - h / 2, h * 1.15), (w / 2 - h / 2, h), (-w / 2, h)]
    else:
        # the A-board carries two boards: coarser curved outlines keep it inside the 150-tri prop budget
        # (opening2d's rounded_rect has a fixed 16-point outline, so the A-board builds a 12-point one)
        if P["kind"] == "standing" and P["board_shape"] == "rounded_rect":
            outline = [(x, z + h / 2) for x, z in K.rounded_rect2d(w, h, min(w, h) * 0.3, 2)]
        else:
            outline = K.opening2d(P["board_shape"], w, h, 8 if P["kind"] == "standing" else 12)
    det = K.Mesh()
    if P["kind"] == "standing":
        ang = math.radians(12)
        for sgn in (-1, 1):
            b = _xz(outline, -t / 2, t / 2, P["board_role"])
            b.rotate_x(sgn * ang).translate(0, sgn * h * math.sin(ang) * 0.5, 0.02)
            det.merge(b)
        board_z = 0.0
        node = Node("sign", det)
        lines = K.Mesh()
        for i in range(P["text_lines"]):
            z = h * (0.75 - 0.5 * i / max(1, P["text_lines"]))
            lw = w * (0.5 + 0.3 * r.random())
            lines.merge(K.box(0, 0, 0, lw, 0.012, h * 0.08, P["text_role"]).rotate_x(-ang).translate(0, -h * math.sin(ang) * 0.5 - t / 2 - 0.004 - (z * math.sin(ang)), 0.02 + z * math.cos(ang)))
        return finalize([node, Node("sign_text", lines)], {"kind": "standing"})
    base = {"post": P["post_height"], "hanging": P["post_height"] * 0.9, "plaque": 0.0, "arrow": P["post_height"]}[P["kind"]]
    board = _xz([(x, z + base) for x, z in outline], -t / 2, t / 2, P["board_role"])
    if P["kind"] in ("post", "arrow"):
        det.merge(post(0 if P["kind"] == "post" else -w * 0.3, t / 2 + 0.04, 0, base + h * 0.9, 0.035, "post", 4, square=True))
    elif P["kind"] == "hanging":
        top = base + h + 0.35
        det.merge(post(-w / 2 - 0.12, 0, 0, top + 0.05, 0.04, "post", 4, square=True))
        det.merge(K.box(-0.06, 0, top, w + 0.2, 0.05, 0.05, "post"))
        for sx in (-1, 1):
            det.merge(K.box(sx * w * 0.35, 0, (base + h + top) / 2, 0.012, 0.012, top - base - h, "metal"))
    lines = K.Mesh()
    for i in range(P["text_lines"]):
        z = base + h * (0.7 - 0.45 * i / max(1, P["text_lines"] - 1 if P["text_lines"] > 1 else 1))
        lw = w * (0.45 + 0.3 * r.random()) * (0.8 if P["board_shape"] in ("oval", "arch") else 1.0)
        lines.merge(K.box(0, -t / 2 - 0.004, z, lw, 0.01, h * 0.09, P["text_role"]))
    meta = {"kind": P["kind"]}
    if P["kind"] == "plaque":
        meta["wall_mounted_back"] = "y=+t/2 (glTF -Z)"
    return finalize([Node("sign", board), Node("sign_frame", det), Node("sign_text", lines)], meta, ground=True)


# ------------------------------------------------------------------ books
@register("prop.book", V, "prop", {
    "kind": S.enum("closed", ["closed", "open", "stack", "row"]), "count": S.integer(3, 1, 6),
    "width": S.num(0.16, 0.08, 0.4), "height": S.num(0.23, 0.1, 0.5), "thickness": S.num(0.04, 0.01, 0.12),
    "cover_role": S.enum("book", ["book", "leather", "paper", "fabric", "body"]),
}, "Books: single closed, open (two page blocks), stack (lying) or row (standing, varied heights).")
def book(P, seed):
    r = rng(seed, "book")
    w, h, t = P["width"], P["height"], P["thickness"]
    m = K.Mesh()
    pages = K.Mesh()

    def one(cx, cy, cz, ww, hh, tt, yaw=0.0, standing=False):
        c = K.box(0, 0, 0, ww, hh, tt, P["cover_role"])
        p = K.box(0.006, 0, 0, ww - 0.012, hh - 0.01, tt * 0.8, "paper")
        p.translate(0, -0.004, 0)
        if standing:
            c.rotate_y(math.pi / 2).rotate_x(math.pi / 2)
            p.rotate_y(math.pi / 2).rotate_x(math.pi / 2)
        for part in (c, p):
            part.rotate_z(yaw).translate(cx, cy, cz)
        m.merge(c)
        pages.merge(p)
    k = P["kind"]
    if k == "closed":
        one(0, 0, t / 2, w, h, t)
    elif k == "open":
        for sx in (-1, 1):
            # 4 mm spine gap: the two cover slabs are separate islands (no shared/coincident faces)
            c = K.box(sx * (w / 2 + 0.002), 0, 0.006, w, h, 0.012, P["cover_role"])
            m.merge(c)
            pg = K.box(sx * (w / 2 - 0.005), 0, 0.012 + t * 0.2, w - 0.02, h - 0.02, t * 0.4, "paper")
            pg.rotate_y(sx * -0.08)
            pages.merge(pg)
    elif k == "stack":
        z = 0.0
        for i in range(P["count"]):
            tt = t * (0.7 + 0.6 * r.random())
            ww, hh = w * (0.85 + 0.3 * r.random()), h * (0.85 + 0.3 * r.random())
            one((r.random() - 0.5) * 0.03, (r.random() - 0.5) * 0.03, z + tt / 2, ww, hh, tt, (r.random() - 0.5) * 0.5)
            z += tt + 0.0005
    else:
        x = 0.0
        for i in range(P["count"]):
            tt = t * (0.7 + 0.6 * r.random())
            hh = h * (0.8 + 0.35 * r.random())
            ww = w * (0.85 + 0.2 * r.random())
            c = K.box(x + tt / 2, 0, hh / 2, tt, ww, hh, P["cover_role"])
            p = K.box(x + tt / 2, -0.004, hh / 2, tt * 0.8, ww - 0.01, hh - 0.012, "paper")
            m.merge(c)
            pages.merge(p)
            x += tt + 0.002
    return finalize([Node("book", m), Node("book_pages", pages)], {"kind": k})


# ------------------------------------------------------------------ keys
@register("prop.key", V, "prop", {
    "kind": S.enum("classic", ["classic", "skeleton", "card", "crystal"]), "length": S.num(0.08, 0.04, 0.3),
    "role": S.enum("metal", ["metal", "chrome", "body", "orb", "wood"]),
}, "Key: classic (ring bow, teeth), skeleton (ornate bow), keycard, crystal key. Lies flat (origin on the floor).")
def key(P, seed):
    L = P["length"]
    role = P["role"]
    m = K.Mesh()
    if P["kind"] == "card":
        m.merge(K.rounded_box(0, 0, L * 0.01, L * 0.62, L, L * 0.02, role, bevel=0.2, smooth=False, k_corner=1))
        m.merge(K.box(0, L * 0.25, L * 0.022, L * 0.4, L * 0.18, L * 0.006, "band"))
    elif P["kind"] == "crystal":
        m.merge(K.lathe([(0, 0), (L * 0.12, L * 0.1), (L * 0.12, L * 0.75), (0, L)], 6, role, smooth=False).rotate_x(-math.pi / 2).translate(0, -L / 2, L * 0.12))
        m.merge(K.torus(L * 0.16, L * 0.035, 8, 4, "metal", smooth=False).rotate_x(math.pi / 2 * 0).translate(0, -L * 0.62, L * 0.04))
    else:
        r_bow = L * (0.18 if P["kind"] == "classic" else 0.22)
        # bow ring 8x3 (48 tris); skeleton lobes 4x2 (8 tris each) -> skeleton key 136 tris <= 150
        m.merge(K.torus(r_bow, L * 0.045, 8, 3, role, smooth=False).translate(0, -L / 2 + r_bow, L * 0.05))
        m.merge(K.cylinder(0, 0, 0, L * 0.035, L * 0.68, 6, role, smooth=False).rotate_x(-math.pi / 2).translate(0, -L / 2 + 2 * r_bow - 0.002, L * 0.05))
        bits = 2 if P["kind"] == "classic" else 3
        for i in range(bits):
            m.merge(K.box(L * 0.06, L / 2 - L * 0.08 - i * L * 0.09, L * 0.05, L * 0.12, L * 0.05, L * 0.05, role))
        if P["kind"] == "skeleton":
            for a in (0, math.pi / 2, math.pi, 1.5 * math.pi):
                m.merge(K.blob(math.cos(a) * r_bow, -L / 2 + r_bow + math.sin(a) * r_bow, L * 0.05, L * 0.05, L * 0.05, L * 0.04, role, 4, 2))
    return finalize([Node("key", m)], {"kind": P["kind"], "grip": "bow"})


# ------------------------------------------------------------------ tools
@register("prop.tool", V, "prop", {
    "kind": S.enum("hammer", ["hammer", "wrench", "shovel", "axe", "pick", "broom", "flashlight", "fishing_rod"]),
    "length": S.num(0.4, 0.15, 1.6), "head_role": S.enum("metal", ["metal", "chrome", "body", "stone"]),
    "handle_role": S.enum("wood", ["wood", "body", "leather", "metal", "rope"]),
}, "Hand tool lying on the ground (origin at the grip centre projected to the floor): hammer, wrench, shovel, axe, pick, broom, flashlight, fishing rod.")
def tool(P, seed):
    L = P["length"]
    k = P["kind"]
    hr, gr = P["head_role"], P["handle_role"]
    m = K.Mesh()
    head = K.Mesh()
    rad = max(0.012, L * 0.025)
    if k in ("hammer", "axe", "pick", "shovel", "broom", "fishing_rod"):
        hl = L * (0.78 if k != "fishing_rod" else 1.0)
        m.merge(K.cylinder(0, 0, 0, rad if k != "fishing_rod" else rad * 0.5, hl, 6, gr, smooth=False).rotate_x(-math.pi / 2).translate(0, -L / 2, rad))
        y = -L / 2 + hl
        if k == "hammer":
            head.merge(K.box(0, y, rad, L * 0.32, L * 0.1, L * 0.1, hr))
        elif k == "axe":
            head.merge(K.prism([(0, -L * 0.05), (L * 0.22, -L * 0.1), (L * 0.22, L * 0.12), (0, L * 0.05)], -0.012, 0.012, hr).translate(0, y - 0.02, rad))
        elif k == "pick":
            head.merge(K.tube([(-L * 0.3, y - L * 0.06, rad), (0, y, rad), (L * 0.3, y - L * 0.06, rad)], [L * 0.01, L * 0.04, L * 0.01], 4, hr, smooth=False))
        elif k == "shovel":
            head.merge(K.prism(K.opening2d("arch", L * 0.25, L * 0.3, 8), -0.01, 0.01, hr).translate(0, 0, 0)
                       .rotate_z(math.pi).translate(0, y + L * 0.3, rad))
        elif k == "broom":
            head.merge(K.lathe([(L * 0.03, 0), (L * 0.1, L * 0.2), (L * 0.08, L * 0.24), (0, L * 0.24)], 6, "rope", smooth=False)
                       .rotate_x(-math.pi / 2).translate(0, y - 0.01, L * 0.1))
        else:
            head.merge(K.cylinder(0, 0, 0, L * 0.05, L * 0.03, 8, hr, smooth=False).rotate_y(math.pi / 2).translate(0, -L / 2 + L * 0.15, L * 0.05))
    elif k == "wrench":
        head.merge(K.box(0, 0, rad, rad * 2.2, L * 0.75, rad * 1.2, hr))
        for sy in (-1, 1):
            head.merge(K.torus(L * 0.07, rad * 0.8, 8, 4, hr, smooth=False).translate(0, sy * L * 0.4, rad))
    else:  # flashlight
        head.merge(K.lathe([(rad * 1.6, 0), (rad * 1.6, L * 0.7), (rad * 2.6, L * 0.85), (rad * 2.6, L)], 8, hr, smooth=False,
                           cap_roles=(hr, "light")).rotate_x(-math.pi / 2).translate(0, -L / 2, rad * 2.6))
    return finalize([Node("tool", m), Node("tool_head", head)], {"kind": k, "grip": "handle"})


# ------------------------------------------------------------------ vessels
@register("prop.vessel", V, "prop", {
    "kind": S.enum("mug", ["mug", "bowl", "bottle", "jar", "vase", "pot", "kettle", "cup"]),
    "height": S.num(0.12, 0.04, 1.0), "width": S.num(0.09, 0.03, 0.8), "handle": S.boolean(True),
    "lid": S.boolean(False), "contents": S.boolean(False, "visible liquid/food surface (role water)"),
    "role": S.enum("body", ["body", "body_alt", "metal", "chrome", "glass", "stone", "wood", "paper"]),
}, "Vessel by lathe profile: mug, bowl, bottle, jar, vase, pot, kettle, cup; optional handle, lid and contents.",
    rules=lambda P: ("vessel proportions out of range: width/height %.2f not in [0.25, %.1f]"
                     % (P["width"] / P["height"], 4.0 if P["kind"] == "bowl" else 2.5))
    if not (0.25 <= P["width"] / P["height"] <= (4.0 if P["kind"] == "bowl" else 2.5)) else None)
def vessel(P, seed):
    h, w = P["height"], P["width"]
    k = P["kind"]
    r = w / 2
    wall = max(0.002, min(r * 0.08, h * 0.08))
    prof = {
        "mug": [(r, 0), (r, h)], "cup": [(r * 0.6, 0), (r, h)], "bowl": [(r * 0.5, 0), (r * 0.95, h * 0.6), (r, h)],
        "bottle": [(r, 0), (r, h * 0.55), (r * 0.35, h * 0.75), (r * 0.3, h)], "jar": [(r * 0.9, 0), (r, h * 0.2), (r, h * 0.8), (r * 0.75, h)],
        "vase": [(r * 0.55, 0), (r, h * 0.35), (r * 0.4, h * 0.8), (r * 0.6, h)], "pot": [(r * 0.85, 0), (r, h * 0.7), (r * 0.9, h)],
        "kettle": [(r * 0.9, 0), (r, h * 0.45), (r * 0.6, h * 0.85), (r * 0.25, h)],
    }[k]
    open_top = k in ("mug", "cup", "bowl", "pot", "vase", "jar") and not P["lid"]
    segs = 8
    if open_top:
        # Inner wall = outer profile offset along its 2D normals (thickness `wall`), so necked shapes
        # (vase, jar) keep a uniform wall instead of a straight inner line cutting through the neck.
        inner = []
        for j in range(len(prof) - 1, -1, -1):
            a = prof[max(0, j - 1)]
            b = prof[min(len(prof) - 1, j + 1)]
            dr, dz = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dr, dz) or 1.0
            nr, nz = dz / ln, -dr / ln  # outward normal of an upward profile
            ri = max(0.001, prof[j][0] - wall * nr)
            zi = min(h, max(wall, prof[j][1] - wall * nz))
            inner.append((ri, zi))
        inner[0] = (max(0.001, prof[-1][0] - wall), h)  # flat rim
        body = K.lathe([(0, 0)] + prof + inner + [(0, max(wall, inner[-1][1]))], segs, P["role"], smooth=True)
    else:
        body = K.lathe([(0, 0)] + prof + [(0, h)], segs, P["role"], smooth=True)
    extra = K.Mesh()
    if P["handle"] and k in ("mug", "cup", "kettle", "pot"):
        hh = h * 0.55
        rr = max(0.004, r * 0.08)
        pts = [(r * 0.95, 0, h * 0.75), (r + hh * 0.45, 0, h * 0.68), (r + hh * 0.45, 0, h * 0.3), (r * 0.95, 0, h * 0.25)]
        extra.merge(K.tube(pts, rr, 3, P["role"], smooth=False))
    if k == "kettle":
        extra.merge(K.tube([(-r * 0.8, 0, h * 0.35), (-r * 1.3, 0, h * 0.7)], [r * 0.12, r * 0.06], 4, P["role"], smooth=False))
    if P["lid"]:
        top_r = prof[-1][0]
        extra.merge(K.lathe([(0, h + 0.001), (top_r * 1.05, h + 0.001), (top_r * 0.3, h + h * 0.12), (0, h + h * 0.16)], segs, P["role"], smooth=False))
    if P["contents"] and open_top:
        # liquid/food disc sits inside the cavity at 70% height, radius from the inner wall there
        zc = h * 0.7
        rin = min(ri for ri, zi in inner if zi >= zc - 1e-9) if any(zi >= zc - 1e-9 for ri, zi in inner) else inner[0][0]
        extra.merge(K.cylinder(0, 0, zc - h * 0.03, max(0.001, rin * 0.85), h * 0.03, 6, "water", smooth=False))
    return finalize([Node("vessel", body), Node("vessel_detail", extra)], {"kind": k})


# ------------------------------------------------------------------ devices
@register("prop.device", V, "prop", {
    "kind": S.enum("radio", ["radio", "lantern", "tablet", "clock", "beacon", "camera"]),
    "size": S.num(0.25, 0.08, 0.8), "body_role": S.enum("body", ["body", "body_alt", "metal", "chrome", "wood"]),
    "screen_on": S.boolean(True),
}, "Small device: radio, lantern (glowing core), tablet, clock, beacon, camera; emissive parts use roles light/screen.")
def device(P, seed):
    s = P["size"]
    k = P["kind"]
    br = P["body_role"]
    m = K.Mesh()
    glow = K.Mesh()
    if k == "radio":
        m.merge(K.rounded_box(0, 0, s * 0.3, s, s * 0.4, s * 0.6, br, bevel=0.35, smooth=False, k_corner=1))
        glow.merge(K.box(s * 0.18, -s * 0.2 - 0.003, s * 0.35, s * 0.42, 0.01, s * 0.18, "screen" if P["screen_on"] else "glass"))
        m.merge(K.cylinder(-s * 0.25, -s * 0.2, 0, s * 0.1, 0.01, 8, "metal", smooth=False).rotate_x(math.pi / 2).translate(0, 0, 0)
                .translate(0, 0, 0))
        m.merge(post(s * 0.4, 0, s * 0.55, s * 1.3, max(0.003, s * 0.01), "metal", 4))
    elif k == "lantern":
        # 6-sided lantern (prop budget 150): base 20 + roof 24 + 4 posts 48 + core 20 + ring 30 = 142 tris
        m.merge(K.cylinder(0, 0, 0, s * 0.3, s * 0.08, 6, br, smooth=False))
        m.merge(K.lathe([(0, s * 0.68), (s * 0.32, s * 0.68), (s * 0.18, s * 0.8), (0, s * 0.82)], 6, br, smooth=False))
        for a in range(4):
            ang = math.tau * a / 4 + math.pi / 4
            m.merge(post(math.cos(ang) * s * 0.26, math.sin(ang) * s * 0.26, s * 0.07, s * 0.69, max(0.004, s * 0.02), br, 4, square=True))
        glow.merge(K.cylinder(0, 0, s * 0.08, s * 0.2, s * 0.6, 6, "light" if P["screen_on"] else "glass"))
        m.merge(K.torus(s * 0.12, max(0.003, s * 0.015), 5, 3, "metal", smooth=False).rotate_x(math.pi / 2).translate(0, 0, s * 0.92))
    elif k == "tablet":
        m.merge(K.rounded_box(0, 0, s * 0.02, s * 0.75, s, s * 0.04, br, bevel=0.2, smooth=False, k_corner=1))
        glow.merge(K.box(0, 0, s * 0.041, s * 0.65, s * 0.85, 0.004, "screen" if P["screen_on"] else "glass"))
    elif k == "clock":
        m.merge(K.cylinder(0, 0, 0, s * 0.5, s * 0.12, 12, br, smooth=False).rotate_x(math.pi / 2).translate(0, s * 0.06, s * 0.5))
        glow.merge(K.cylinder(0, 0, 0, s * 0.42, 0.01, 12, "paper", smooth=False).rotate_x(math.pi / 2).translate(0, -s * 0.06, s * 0.5))
        m.merge(K.box(0, -s * 0.075, s * 0.6, s * 0.03, 0.01, s * 0.2, "trim"))
        m.merge(K.box(s * 0.08, -s * 0.08, s * 0.5, s * 0.16, 0.01, s * 0.03, "trim"))
        for sx in (-1, 1):
            m.merge(K.box(sx * s * 0.3, 0, s * 0.03, s * 0.12, s * 0.12, s * 0.06, br))
    elif k == "beacon":
        m.merge(K.lathe([(0, 0), (s * 0.3, 0), (s * 0.3, s * 0.1), (s * 0.15, s * 0.18), (0, s * 0.18)], 8, br, smooth=False))
        m.merge(post(0, 0, s * 0.17, s * 0.7, s * 0.04, br, 6))
        glow.merge(K.sphere(0, 0, s * 0.8, s * 0.14, s * 0.14, s * 0.14, 8, 4, "light" if P["screen_on"] else "orb"))
    else:  # camera
        m.merge(K.rounded_box(0, 0, s * 0.3, s, s * 0.45, s * 0.6, br, bevel=0.3, smooth=False, k_corner=1))
        m.merge(K.cylinder(0, 0, 0, s * 0.2, s * 0.3, 10, "metal", smooth=False).rotate_x(math.pi / 2).translate(0, -s * 0.22, s * 0.3))
        glow.merge(K.cylinder(0, 0, 0, s * 0.14, 0.01, 10, "glass", smooth=False).rotate_x(math.pi / 2).translate(0, -s * 0.52, s * 0.3))
    return finalize([Node("device", m), Node("device_glow", glow)], {"kind": k})


# ------------------------------------------------------------------ soft goods
def puff_solid(outline, t, role, prof, z_top, z_bot=0.0, band_roles=None):
    """Closed, smooth, inflated cushion form: rings of a star-shaped outline scaled toward its centre
    by `prof` [(z_frac, scale)], closed by centre fans at z_bot / z_top (z_top below the top ring =
    a tufted dimple, above = a domed puff). band_roles: optional role per band (piping ridge)."""
    k = len(outline)
    rings = [[(x * sc, y * sc, zf * t) for x, y in outline] for zf, sc in prof]
    verts = [p for r in rings for p in r] + [(0.0, 0.0, z_bot), (0.0, 0.0, z_top)]
    cb, ct = len(verts) - 2, len(verts) - 1
    faces, roles = [], []
    for j in range(len(rings) - 1):
        for i in range(k):
            a, b = j * k + i, j * k + (i + 1) % k
            faces.append((a, b, b + k, a + k))
            roles.append(band_roles[j] if band_roles else role)
    last = (len(rings) - 1) * k
    for i in range(k):
        faces.append((cb, (i + 1) % k, i))
        roles.append(role)
        faces.append((ct, last + i, last + (i + 1) % k))
        roles.append(role)
    return K.Mesh().add(verts, faces, roles, True).orient_outward()


def heart2d(s, k=8):
    pts = []
    for i in range(k):
        a = math.tau * i / k
        x = 16 * math.sin(a) ** 3
        y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
        pts.append((x / 34 * s, (y + 4) / 34 * s))
    return K.ccw(pts)


@register("soft.pillow", V, "soft", {
    "shape": S.enum("square", ["square", "round", "bolster", "floor_cushion", "heart"]),
    "size": S.num(0.45, 0.2, 1.2), "thickness": S.num(0.15, 0.05, 0.4), "tuft": S.boolean(False),
    "role": S.enum("cushion", SOFT), "piping": S.boolean(False),
}, "Pillow/cushion: puffy square, round, bolster, floor cushion, heart; optional centre tuft button and piping.")
def pillow(P, seed):
    s, t = P["size"], P["thickness"]
    role = P["role"]
    det = K.Mesh()
    sh = P["shape"]
    trim = "trim"
    if sh == "bolster":
        roles = [role, trim if P["piping"] else role, role, trim if P["piping"] else role, role]
        m = K.lathe([(0, 0), (t * 0.42, 0.0), (t * 0.5, t * 0.12), (t * 0.5, s - t * 0.12), (t * 0.42, s), (0, s)],
                    8, role, roles=roles).rotate_y(math.pi / 2).translate(-s / 2, 0, t * 0.5)
        if P["tuft"]:
            for sx in (-1, 1):
                det.merge(K.cylinder(0, 0, -0.012, t * 0.09, 0.03, 6, trim, smooth=False).rotate_y(math.pi / 2)
                          .translate(sx * (s / 2 + 0.002), 0, t * 0.5))
    else:
        # 8-point outlines + 7 rings + centre fans = 112 tris (+20 for a tuft button) <= 150
        if sh == "round":
            outline = K.circle2d(s / 2, 8, start=math.pi / 8)
        elif sh == "heart":
            outline = heart2d(s)
        else:
            outline = K.superellipse2d(s / 2, s / 2, 8, 3.0 if sh == "square" else 2.6)
        if sh == "floor_cushion":
            prof = [(0.0, 0.84), (0.08, 0.96), (0.3, 1.0), (0.5, 1.01), (0.7, 1.0), (0.92, 0.96), (1.0, 0.84)]
        elif P["piping"]:
            prof = [(0.0, 0.6), (0.1, 0.88), (0.42, 1.0), (0.5, 1.045), (0.58, 1.0), (0.9, 0.88), (1.0, 0.6)]
        else:
            prof = [(0.0, 0.6), (0.1, 0.88), (0.3, 0.98), (0.5, 1.0), (0.7, 0.98), (0.9, 0.88), (1.0, 0.6)]
        band_roles = [role, role, trim, trim, role, role] if P["piping"] and sh != "floor_cushion" else None
        if P["piping"] and sh == "floor_cushion":
            band_roles = [role, role, trim, trim, role, role]
        z_top = t * (0.86 if P["tuft"] else 1.07)
        m = puff_solid(outline, t, role, prof, z_top, 0.0, band_roles)
        if P["tuft"]:
            det.merge(K.cylinder(0, 0, z_top - 0.01, s * 0.035, 0.025, 6, trim, smooth=False))
    return finalize([Node("pillow", m), Node("pillow_detail", det)], {"shape": sh})


@register("soft.blanket", V, "soft", {
    "kind": S.enum("folded", ["folded", "rolled", "spread"]), "width": S.num(1.4, 0.5, 2.6), "depth": S.num(1.8, 0.5, 2.6),
    "thickness": S.num(0.03, 0.01, 0.08), "folds": S.integer(3, 1, 4), "waves": S.num(0.03, 0.0, 0.1),
    "role": S.enum("quilt", SOFT), "fringe": S.boolean(False),
}, "Blanket: folded stack, rolled log, or spread flat with soft seeded waves (thin closed slab).")
def blanket(P, seed):
    r = rng(seed, "blanket")
    w, d, t = P["width"], P["depth"], P["thickness"]
    role = P["role"]
    m = K.Mesh()
    k = P["kind"]
    if k == "folded":
        # One closed soft stack (soft budget 150): a 6-point outline lofted through layer boundaries
        # (slightly pinched) and layer middles (the fold edge bulges, alternating sides per layer).
        layers = P["folds"] + 1
        fw, fd = w / 2, d / layers
        lt = t * 1.8
        rings = []
        for j in range(2 * layers + 1):
            z = lt * j / 2.0
            mid = j % 2 == 1
            side = 1 if (j // 2) % 2 == 0 else -1
            # every ring keeps a small outward bulge on both sides (strictly convex caps, no collinear
            # vertices); the fold side of each layer middle bulges further
            base = min(fw, fd) * 0.03
            bul_r = min(fw, fd) * 0.12 if (mid and side > 0) else base
            bul_l = min(fw, fd) * 0.12 if (mid and side < 0) else base
            sc = 1.0 if mid else 0.96
            jx, jy = (r.random() - 0.5) * 0.015, (r.random() - 0.5) * 0.015
            pts = [(-fw / 2 * sc, -fd / 2 * sc), (fw / 2 * sc, -fd / 2 * sc), (fw / 2 * sc + bul_r, 0.0),
                   (fw / 2 * sc, fd / 2 * sc), (-fw / 2 * sc, fd / 2 * sc), (-fw / 2 * sc - bul_l, 0.0)]
            rings.append([(x + jx, y + jy, z) for x, y in pts])
        m = K.loft(rings, role, smooth=True)
    elif k == "rolled":
        rr = math.sqrt(w * d * t / math.pi) * 1.4 + 0.03
        m.merge(K.lathe([(0, 0), (rr * 0.9, 0), (rr, rr * 0.2), (rr, w - rr * 0.2), (rr * 0.9, w), (0, w)], 8, role)
                .rotate_y(math.pi / 2).translate(-w / 2, 0, rr))
        for x in (-w * 0.3, w * 0.3):
            m.merge(K.torus(rr * 1.02, 0.012, 6, 3, "rope", smooth=False).rotate_y(math.pi / 2).translate(x, 0, rr))
    else:
        # Wavy 4x4 top over a flat bottom polygon: closed slab of 78 tris (+48 for the tassels).
        n = 4
        amp = P["waves"]
        ph = r.random() * math.tau

        def fn(u, v):
            x = -w / 2 + w * u
            y = -d / 2 + d * v
            z = t + amp * math.sin(u * 5.0 + ph + v * 2.0) * math.sin(v * 4.0 + 0.5)
            return (x, y, max(t * 0.5, z))
        top = K.grid_surface(n, n, fn, role)
        nn = n + 1
        ring = [i for i in range(nn)] + [i * nn + n for i in range(1, nn)] + [n * nn + i for i in range(n - 1, -1, -1)] + [i * nn for i in range(n - 1, 0, -1)]
        verts = list(top.v)
        bot_off = len(verts)
        verts += [(top.v[i][0], top.v[i][1], 0.0) for i in ring]
        faces = list(top.f)
        L = len(ring)
        for j in range(L):
            a, b = ring[j], ring[(j + 1) % L]
            faces.append((b, a, bot_off + j, bot_off + (j + 1) % L))
        faces.append(tuple(bot_off + j for j in reversed(range(L))))
        m = K.Mesh().add(verts, faces, role, True)
        from .gen_vehicles import _consistent
        m = _consistent(m)
    det = K.Mesh()
    if P["fringe"] and k == "spread":
        # 6 tetrahedral tassels per short edge (4 tris each)
        for sy in (-1, 1):
            for i in range(6):
                x = -w / 2 + w * (i + 0.5) / 6
                y0 = sy * (d / 2 - 0.01)
                y1 = sy * (d / 2 + 0.07)
                tet = K.Mesh().add([(x - 0.015, y0, 0.002), (x + 0.015, y0, 0.002), (x, y0, 0.016), (x, y1, 0.002)],
                                   [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)], "rope")
                det.merge(tet.orient_outward())
    return finalize([Node("blanket", m), Node("blanket_fringe", det)], {"kind": k})


# ------------------------------------------------------------------ sky + particles
@register("sky.backdrop", V, "sky", {
    "kind": S.enum("dome", ["dome", "cylinder"]),
    "radius": S.runtime(S.num(400.0, 20.0, 1800.0, "placement scale (fit inside the camera far plane); invisible from the viewer")),
    "segments": S.lod(S.integer(12, 8, 16)), "rings": S.lod(S.integer(4, 2, 4)), "below_horizon": S.num(0.15, 0.0, 0.5, "fraction of radius extending below the horizon"),
}, "Sky backdrop: inward-facing dome or cylinder (kit_shell_sky, role 'sky', v = elevation 0..1). Origin at the viewer; extends below y=0 by below_horizon*radius.",
    origin="viewer")
def backdrop(P, seed):
    R = P["radius"]
    seg = P["segments"]
    nr = P["rings"]
    below = P["below_horizon"] * R
    verts, faces, uvs = [], [], []
    if P["kind"] == "dome":
        # `rings` rows from the lowest (below-horizon) row up to the apex fan:
        # tris = 2*seg*(rings-1) + seg  (16 x 4 -> 112 <= 128)
        e0 = -math.asin(min(0.99, below / R))
        elev = [e0 + (math.pi / 2 - e0) * j / nr for j in range(nr)]
        rows = [[(R * math.cos(e) * math.cos(math.tau * i / seg), R * math.cos(e) * math.sin(math.tau * i / seg), R * math.sin(e)) for i in range(seg + 1)] for e in elev]
        vrow = [j / nr for j in range(nr)]
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
    else:
        H = R * 0.8
        zs = [-below, H * 0.5, H]
        for z in zs:
            verts.extend([(R * math.cos(math.tau * i / seg), R * math.sin(math.tau * i / seg), z) for i in range(seg + 1)])
        W = seg + 1
        vv = [0.0, 0.5, 1.0]
        for j in range(2):
            for i in range(seg):
                a = j * W + i
                faces.append((a, a + W, a + W + 1, a + 1))
                uvs.append(("n", [(i / seg, vv[j]), (i / seg, vv[j + 1]), ((i + 1) / seg, vv[j + 1]), ((i + 1) / seg, vv[j])]))
    m = K.Mesh().add(verts, faces, "sky", False, uvs)
    # inward-facing: normals toward the origin
    A = np.asarray(m.v)
    for fi, f in enumerate(m.f):
        p = A[list(f)]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(n) < 1e-12 and len(f) > 3:
            n = np.cross(p[2] - p[0], p[3] - p[0])
        if np.dot(n, -p.mean(0)) < 0:
            m.f[fi] = tuple(reversed(f))
            m.uv[fi] = (m.uv[fi][0], list(reversed(m.uv[fi][1])))
    ext = np.ptp(np.asarray(m.v), axis=0)
    return Asset([Node("sky", m, "shell")], {"kind": P["kind"], "radius_m": R, "origin": "viewer",
                                              "bbox_size_m": [round(float(x), 4) for x in ext]})


@register("fx.particles", V, "fx", {
    "shape": S.enum("flake", ["flake", "spark", "puff", "leaf", "disc"]), "size": S.num(0.08, 0.01, 1.0),
    "rate": S.runtime(S.num(20.0, 1.0, 200.0)), "lifetime": S.runtime(S.num(4.0, 0.5, 20.0)),
    "velocity": S.runtime(S.num(0.6, 0.0, 5.0)), "spread_deg": S.runtime(S.num(25.0, 0.0, 180.0)),
    "gravity": S.runtime(S.num(-0.3, -9.8, 9.8)), "area": S.runtime(S.num(4.0, 0.1, 40.0)),
}, "Particle card (kit_card_particle, role 'particle', alpha-tested pack texture) whose planar outline follows `shape` "
   "(flake star, spark sliver, puff cloud, leaf almond, disc octagon) + emitter spec in meta (runtime instancing; rate, "
   "lifetime, velocity, spread, gravity and area only act at runtime).", origin="card_center")
def particles(P, seed):
    s = P["size"]
    sh = P["shape"]
    if sh == "flake":
        outline = [(0.5 * (1.0 if i % 2 == 0 else 0.45) * math.cos(math.tau * i / 12 + math.pi / 2),
                    0.5 * (1.0 if i % 2 == 0 else 0.45) * math.sin(math.tau * i / 12 + math.pi / 2)) for i in range(12)]
    elif sh == "spark":
        outline = [(0.0, 0.5), (0.12, 0.0), (0.0, -0.5), (-0.12, 0.0)]
    elif sh == "puff":
        outline = [(0.5 * (0.82 + 0.18 * math.cos(3 * math.tau * i / 10)) * math.cos(math.tau * i / 10),
                    0.5 * (0.82 + 0.18 * math.cos(3 * math.tau * i / 10)) * math.sin(math.tau * i / 10)) for i in range(10)]
    elif sh == "leaf":
        outline = [(0.0, 0.5), (0.22, 0.2), (0.25, -0.15), (0.0, -0.5), (-0.25, -0.15), (-0.22, 0.2)]
    else:
        outline = [(0.5 * math.cos(math.tau * i / 8 + math.pi / 8), 0.5 * math.sin(math.tau * i / 8 + math.pi / 8)) for i in range(8)]
    # planar fan card in the XZ plane facing -Y (centre vertex keeps star/almond outlines degenerate-free);
    # outline made CCW in (x, z) so (centre, p_i, p_i+1) winds toward -Y
    outline = K.ccw(outline)
    verts = [(0.0, 0.0, 0.0)] + [(x * s, 0.0, z * s) for x, z in outline]
    n = len(outline)
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    uvs = [("n", [(0.5, 0.5), (0.5 + outline[i][0], 0.5 + outline[i][1]), (0.5 + outline[(i + 1) % n][0], 0.5 + outline[(i + 1) % n][1])])
           for i in range(n)]
    m = K.Mesh().add(verts, faces, "particle", False, uvs)
    spec = {k: P[k] for k in ("shape", "size", "rate", "lifetime", "velocity", "spread_deg", "gravity", "area")}
    spec["billboard"] = True
    ext = np.ptp(np.asarray(m.v), axis=0)
    return Asset([Node("particle", m, "card")], {"emitter": spec, "facing": "glTF +Z (billboard in runtime)",
                                                 "bbox_size_m": [round(float(x), 4) for x in ext]})
