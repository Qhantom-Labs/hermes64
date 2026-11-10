"""Generic furniture + containers (theme-agnostic; materials are roles)."""
import math

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .genutil import finalize, leg_points, post, seg_count
from .rng import rng

V = "3.0.0"
STRUCT = ["body", "body_alt", "wood", "stone", "metal", "chrome", "leather", "trim"]
SOFT = ["cushion", "quilt", "fabric", "knit", "fur", "leather"]
STAND = ["metal", "chrome", "wood", "body", "body_alt", "trim"]


# ------------------------------------------------------------------ table
@register("furn.table", V, "furniture", {
    "top_shape": S.enum("rect", ["rect", "round", "oval", "flower", "kidney"]),
    "width": S.num(1.2, 0.4, 3.0), "depth": S.num(0.8, 0.4, 2.0), "height": S.num(0.75, 0.3, 1.2),
    "top_thickness": S.num(0.05, 0.02, 0.12),
    "legs": S.enum("four", ["four", "pedestal", "trestle", "tulip", "plinth"]),
    "leg_radius": S.num(0.035, 0.02, 0.08),
    "ornament": S.enum("none", ["none", "sphere", "vase"]),
    "top_role": S.enum("wood", STRUCT + ["glass"]), "base_role": S.enum("wood", STAND),
    "segments": S.integer(16, 6, 24, "top outline segments (low-poly support plinths)"),
}, "Table: rect/round/oval/flower/kidney top; four legs, pedestal, trestle, tulip or solid plinth base; optional ornament.")
def table(P, seed):
    w, d, h, t = P["width"], P["depth"], P["height"], P["top_thickness"]
    if P["top_shape"] == "round":
        d = w = min(w, d)
    seg = int(P["segments"])
    top = K.prism(K.plan2d(P["top_shape"], w, d, seg), h - t, h, P["top_role"])
    base = K.Mesh()
    lr = P["leg_radius"]
    br = P["base_role"]
    if P["legs"] == "four":
        for x, y in leg_points(P["top_shape"], w, d, lr * 2.5):
            base.merge(post(x, y, 0.0, h - t + 0.01, lr, br, 6, square=P["top_shape"] == "rect"))
    elif P["legs"] == "pedestal":
        rb = min(w, d) * 0.32
        base.merge(K.lathe([(0, 0), (rb, 0), (rb * 0.9, 0.04), (lr * 1.4, 0.08), (lr * 1.2, h - t - 0.04),
                            (lr * 2.2, h - t + 0.01), (0, h - t + 0.01)], 10, br))
    elif P["legs"] == "tulip":
        rb = min(w, d) * 0.3
        base.merge(K.lathe([(0, 0), (rb, 0), (rb * 0.7, 0.05), (lr * 1.5, h * 0.35), (lr * 1.3, h * 0.6),
                            (rb * 0.6, h - t + 0.01), (0, h - t + 0.01)], 12, br))
    elif P["legs"] == "plinth":  # solid molded column under the top (cheap support stand)
        base.merge(K.prism(K.plan2d(P["top_shape"], w * 0.62, d * 0.62, seg), 0.0, h - t + 0.01, br))
    else:  # trestle: two end frames + stretcher
        for sx in (-1, 1):
            x = sx * (w / 2 - 0.12)
            base.merge(K.box(x, 0, (h - t + 0.01) / 2, 0.06, d * 0.7, h - t + 0.01, br))
            base.merge(K.box(x, 0, 0.03, 0.08, d * 0.85, 0.06, br))
        base.merge(K.box(0, 0, h * 0.35, w - 0.3, 0.05, 0.06, br))
    orn = K.Mesh()
    if P["ornament"] == "sphere":
        r = min(w, d) * 0.12
        orn.merge(K.sphere(0, 0, h + r * 0.95, r, r, r, 8, 6, "orb"))
    elif P["ornament"] == "vase":
        r = min(w, d) * 0.08
        orn.merge(K.lathe([(0, h - 0.005), (r, h - 0.005), (r * 1.3, h + r), (r * 0.6, h + r * 2.4), (r * 0.8, h + r * 2.8),
                           (0, h + r * 2.8)], 8, "glass" if P["top_role"] != "glass" else "body"))
    return finalize([Node("table_top", top), Node("table_base", base), Node("ornament", orn)],
                    {"seat_height": None, "top_height": round(h, 3)})


# ------------------------------------------------------------------ chair / stool / bench
def _chair_rules(P):
    if P["kind"] == "stool" and P["back_height"] > 0:
        return "stool has no back (back_height must be 0)"
    return None


@register("furn.chair", V, "furniture", {
    "kind": S.enum("chair", ["stool", "chair", "armchair", "bench"]),
    "seat_shape": S.enum("rect", ["rect", "round"]),
    "seat_height": S.num(0.45, 0.3, 0.8), "width": S.num(0.46, 0.35, 1.8), "depth": S.num(0.46, 0.35, 0.75),
    "back_height": S.num(0.45, 0.0, 0.9),
    "legs": S.enum("four", ["four", "pedestal", "sled"]),
    "cushion": S.boolean(True),
    "seat_role": S.enum("wood", STRUCT), "frame_role": S.enum("wood", STAND), "cushion_role": S.enum("cushion", SOFT),
}, "Seat: stool, chair, armchair or bench; four legs, pedestal or sled base; optional cushion.", rules=_chair_rules)
def chair(P, seed):
    w, d, sh = P["width"], P["depth"], P["seat_height"]
    if P["seat_shape"] == "round":
        w = d = min(w, d)
    st = 0.05
    seat = K.prism(K.plan2d(P["seat_shape"], w, d, 12), sh - st, sh, P["seat_role"])
    frame = K.Mesh()
    fr = P["frame_role"]
    if P["legs"] == "four":
        for x, y in leg_points(P["seat_shape"], w, d, 0.05):
            frame.merge(post(x, y, 0, sh - st + 0.01, 0.022, fr, 6, square=P["seat_shape"] == "rect"))
    elif P["legs"] == "pedestal":
        rb = min(w, d) * 0.42
        frame.merge(K.lathe([(0, 0), (rb, 0), (rb * 0.85, 0.035), (0.03, 0.08), (0.028, sh - st - 0.03), (0.07, sh - st + 0.01),
                             (0, sh - st + 0.01)], 10, fr))
    else:  # sled: two U runners
        for sx in (-1, 1):
            x = sx * (w / 2 - 0.04)
            frame.merge(K.box(x, 0, 0.015, 0.03, d * 0.95, 0.03, fr))
            for sy in (-1, 1):
                frame.merge(K.box(x, sy * (d / 2 - 0.06), (sh - st) / 2 + 0.01, 0.03, 0.03, sh - st, fr))
    soft = K.Mesh()
    if P["cushion"]:
        soft.merge(K.rounded_box(0, 0, sh + 0.035, w * 0.92, d * 0.92, 0.08, P["cushion_role"], bevel=0.6, k_corner=1))
    back = K.Mesh()
    bh = P["back_height"]
    if bh > 0 and P["kind"] != "stool":
        back.merge(K.box(0, d / 2 - 0.03, sh + bh / 2 - 0.01, w * (0.95 if P["kind"] != "bench" else 0.98), 0.05, bh + 0.02, P["seat_role"]))
        if P["cushion"]:
            back.merge(K.rounded_box(0, d / 2 - 0.08, sh + 0.06 + bh * 0.45, w * 0.85, 0.07, bh * 0.75, P["cushion_role"], bevel=0.6, k_corner=1))
    if P["kind"] == "armchair":
        for sx in (-1, 1):
            back.merge(K.box(sx * (w / 2 + 0.04), 0, sh + 0.11, 0.08, d * 0.95, 0.22, P["seat_role"]))
    return finalize([Node("seat", seat), Node("frame", frame), Node("cushion", soft), Node("back", back)],
                    {"seat_height": round(sh + (0.07 if P["cushion"] else 0.0), 3)})


# ------------------------------------------------------------------ bed
@register("furn.bed", V, "furniture_large", {
    "kind": S.enum("box", ["box", "nook", "pod", "cot"]),
    "width": S.num(1.4, 0.8, 2.2), "length": S.num(2.0, 1.6, 2.4), "height": S.num(0.45, 0.2, 0.7),
    "pillows": S.integer(2, 0, 4), "blanket": S.boolean(True),
    "headboard": S.enum("low", ["none", "low", "high", "curved"]),
    "frame_role": S.enum("wood", STRUCT), "mattress_role": S.enum("fabric", SOFT),
    "pillow_role": S.enum("quilt", SOFT), "blanket_role": S.enum("knit", SOFT),
}, "Bed: box/nook/pod/cot frame, mattress, pillows, draped blanket, headboard.")
def bed(P, seed):
    w, L, h = P["width"], P["length"], P["height"]
    r = rng(seed, "bed")
    frame = K.Mesh()
    fr = P["frame_role"]
    mat_h = 0.18
    base_top = h - mat_h + 0.02
    if P["kind"] == "pod":
        frame.merge(K.lathe([(0, 0.02), (0.42, 0.02), (0.52, base_top + 0.05), (0.47, base_top + 0.08),
                             (0, base_top + 0.08)], 12, fr, rx=w * 1.05, ry=L * 0.55))
        base_top += 0.05
    elif P["kind"] == "cot":
        frame.merge(K.box(0, 0, base_top - 0.03, w, L, 0.05, fr))
        for sx in (-1, 1):
            for sy in (-1, 1):
                frame.merge(post(sx * (w / 2 - 0.04), sy * (L / 2 - 0.04), 0, base_top - 0.04, 0.025, fr, 6, square=True))
    else:
        frame.merge(K.rounded_box(0, 0, base_top / 2, w + 0.06, L + 0.06, base_top, fr, bevel=0.15 if P["kind"] == "box" else 0.4, k_corner=1))
    mattress = K.rounded_box(0, 0, base_top + mat_h / 2 - 0.02, w * 0.96, L * 0.97, mat_h, P["mattress_role"], bevel=0.5, k_corner=1)
    soft = K.Mesh()
    top_z = base_top + mat_h - 0.02
    n = P["pillows"]
    for i in range(n):
        pw = (w * 0.9) / max(1, n)
        x = -w * 0.45 + pw * (i + 0.5)
        soft.merge(K.blob(x, L / 2 - 0.22, top_z + 0.06, pw * 0.42, 0.16, 0.08, P["pillow_role"], 6, 3, 0.3))
    if P["blanket"]:
        # draped blanket: U-section slab over the lower 60% of the mattress, folded over the sides
        y0, y1 = -L / 2 + 0.02, L * 0.1
        bw, bt, drop = w * 0.99 + 0.04, 0.035, mat_h * 0.7
        sec = [(-bw / 2, top_z - drop), (-bw / 2 + bt, top_z - drop), (-bw / 2 + bt, top_z - 0.005),
               (bw / 2 - bt, top_z - 0.005), (bw / 2 - bt, top_z - drop), (bw / 2, top_z - drop), (bw / 2, top_z + bt),
               (-bw / 2, top_z + bt)]
        rings = []
        steps = 3
        for j in range(steps + 1):
            y = y0 + (y1 - y0) * j / steps
            wob = 0.012 * math.sin(j * 1.9 + r.random())
            rings.append([(x, y, z + wob) for x, z in sec])
        blanket = K.loft(rings, P["blanket_role"], smooth=True)
        soft.merge(blanket)
    head = K.Mesh()
    hb = P["headboard"]
    if hb != "none" and P["kind"] != "nook":
        hh = {"low": 0.35, "high": 0.75, "curved": 0.6}[hb]
        if hb == "curved":
            head = K.rounded_box(0, L / 2 + 0.04, (base_top + hh) / 2 + 0.05, w + 0.08, 0.1, base_top + hh, fr, bevel=0.9, k_corner=1)
        else:
            head.merge(K.box(0, L / 2 + 0.04, (base_top + hh) / 2, w + 0.08, 0.08, base_top + hh, fr))
    nook = K.Mesh()
    if P["kind"] == "nook":
        H = h + 1.25
        nook.merge(K.box(0, L / 2 + 0.1, H / 2, w + 0.5, 0.12, H, fr))            # back wall
        for sx in (-1, 1):
            nook.merge(K.box(sx * (w / 2 + 0.2), 0.05, H / 2, 0.12, L + 0.2, H, fr))  # side walls
        nook.merge(K.box(0, 0.05, H + 0.05, w + 0.5, L + 0.2, 0.12, fr))          # canopy
    return finalize([Node("bed_frame", frame), Node("mattress", mattress), Node("bedding", soft),
                     Node("headboard", head), Node("nook", nook)], {"sleep_height": round(top_z, 3)})


# ------------------------------------------------------------------ shelf / cabinet
@register("furn.shelf", V, "furniture", {
    "kind": S.enum("bookshelf", ["bookshelf", "cabinet", "open_rack"]),
    "width": S.num(1.0, 0.4, 2.4), "height": S.num(1.8, 0.4, 2.4), "depth": S.num(0.35, 0.2, 0.6),
    "shelves": S.integer(4, 1, 6), "books": S.num(0.6, 0.0, 1.0),
    "frame_role": S.enum("wood", STRUCT),
}, "Bookshelf, cabinet (doors) or open rack; seeded book groups.")
def shelf(P, seed):
    w, h, d = P["width"], P["height"], P["depth"]
    r = rng(seed, "shelf")
    fr = P["frame_role"]
    t = 0.03
    frame = K.Mesh()
    if P["kind"] == "open_rack":
        for sx in (-1, 1):
            for sy in (-1, 1):
                frame.merge(post(sx * (w / 2 - 0.02), sy * (d / 2 - 0.02), 0, h, 0.018, fr, 4, square=True))
    else:
        for sx in (-1, 1):
            frame.merge(K.box(sx * (w / 2 - t / 2), 0, h / 2, t, d, h, fr))
        frame.merge(K.box(0, d / 2 - 0.01, h / 2, w - 2 * t + 0.01, 0.02, h - 0.01, fr))  # back
        frame.merge(K.box(0, 0, h - t / 2, w + 0.02, d + 0.02, t, fr))  # top
    n = P["shelves"]
    levels = [0.06 + (h - 0.12) * i / n for i in range(n + 1)][:-1] if P["kind"] != "open_rack" else \
        [0.05 + (h - 0.1) * i / max(1, n) for i in range(n + 1)]
    boards = K.Mesh()
    books = K.Mesh()
    n_groups = 0
    inner_w = w - 2 * t - 0.02 if P["kind"] != "open_rack" else w - 0.06
    for li, z in enumerate(levels):
        boards.merge(K.box(0, -0.005, z, inner_w + (0.015 if P["kind"] != "open_rack" else 0.06), d - 0.03, t * 0.8, fr))
        if P["kind"] == "cabinet":
            continue
        gap = (h - 0.12) / n
        if z > h - 0.2:
            continue
        x = -inner_w / 2 + 0.01
        while x < inner_w / 2 - 0.06 and n_groups < 12:
            gw = 0.12 + r.random() * 0.28
            if x + gw > inner_w / 2 - 0.01:
                gw = inner_w / 2 - 0.01 - x
            if r.random() < P["books"] and gw > 0.05:
                bh = gap * (0.55 + 0.35 * r.random())
                books.merge(K.box(x + gw / 2, -0.02, z + t * 0.4 + bh / 2, gw - 0.004, d * 0.75, bh, "book"))
                n_groups += 1
            x += gw + 0.004
    doors = K.Mesh()
    if P["kind"] == "cabinet":
        for sx in (-1, 1):
            doors.merge(K.box(sx * w / 4, -d / 2 - 0.006, h / 2, w / 2 - 0.02, 0.02, h - 0.08, fr))
            doors.merge(K.box(sx * 0.04, -d / 2 - 0.025, h / 2, 0.015, 0.02, 0.12, "metal"))
    return finalize([Node("shelf_frame", frame), Node("shelf_boards", boards), Node("books", books), Node("doors", doors)])


# ------------------------------------------------------------------ containers
@register("furn.container", V, "furniture", {
    "kind": S.enum("crate", ["crate", "barrel", "chest", "basket", "locker", "capsule"]),
    "width": S.num(0.6, 0.3, 1.5), "depth": S.num(0.6, 0.3, 1.5), "height": S.num(0.6, 0.3, 1.8),
    "lid_open": S.num(0.0, 0.0, 100.0, "chest lid angle (deg)"), "bands": S.integer(2, 0, 3),
    "body_role": S.enum("wood", STRUCT + ["hull"]), "band_role": S.enum("metal", STAND + ["rope"]),
}, "Container: crate, barrel, chest (hinged kit_lid), basket, locker, capsule.")
def container(P, seed):
    w, d, h = P["width"], P["depth"], P["height"]
    br, bd = P["body_role"], P["band_role"]
    k = P["kind"]
    body = K.Mesh()
    bands = K.Mesh()
    nodes = []
    if k == "crate":
        body.merge(K.box(0, 0, h / 2, w, d, h, br))
        for i in range(P["bands"]):
            z = h * (i + 1) / (P["bands"] + 1)
            bands.merge(K.box(0, 0, z, w + 0.02, d + 0.02, 0.05, bd))
        for sx in (-1, 1):
            for sy in (-1, 1):
                bands.merge(K.box(sx * (w / 2 - 0.015), sy * (d / 2 - 0.015), h / 2, 0.05, 0.05, h + 0.005, bd))
    elif k in ("barrel", "capsule", "basket"):
        r = min(w, d) / 2
        if k == "barrel":
            body.merge(K.lathe([(0, 0), (r * 0.85, 0), (r, h * 0.5), (r * 0.85, h), (0, h)], 10, br))
            for i in range(P["bands"]):
                z = h * (0.15 + 0.7 * i / max(1, P["bands"] - 1)) if P["bands"] > 1 else h * 0.5
                rr = r * (0.85 + 0.15 * math.sin(math.pi * z / h)) + 0.012
                bands.merge(K.lathe_closed([(rr - 0.015, z - 0.025), (rr, z - 0.025), (rr, z + 0.025), (rr - 0.015, z + 0.025)], 10, bd))
        elif k == "capsule":
            body.merge(K.lathe([(0, 0), (r * 0.7, 0), (r, h * 0.15), (r, h * 0.85), (r * 0.7, h), (0, h)], 12, br))
            for i in range(P["bands"]):
                z = h * (0.3 + 0.4 * i / max(1, P["bands"] - 1)) if P["bands"] > 1 else h * 0.5
                bands.merge(K.lathe_closed([(r - 0.01, z - 0.03), (r + 0.015, z - 0.03), (r + 0.015, z + 0.03), (r - 0.01, z + 0.03)], 12, bd))
        else:
            body.merge(K.lathe([(0, 0), (r * 0.75, 0), (r, h), (r * 0.9, h), (r * 0.65, 0.04), (0, 0.04)], 10, "rope"))
            bands.merge(K.lathe_closed([(r * 0.95, h - 0.03), (r * 1.05, h - 0.03), (r * 1.05, h + 0.02), (r * 0.95, h + 0.02)], 10, bd))
    elif k == "locker":
        body.merge(K.box(0, 0, h / 2, w, d, h, br))
        bands.merge(K.box(0, -d / 2 - 0.004, h * 0.55, w * 0.88, 0.012, h * 0.82, bd))
        bands.merge(K.box(w * 0.3, -d / 2 - 0.016, h * 0.55, 0.03, 0.02, 0.12, "metal"))
    else:  # chest with hinged lid node
        bh = h * 0.6
        body.merge(K.box(0, 0, bh / 2, w, d, bh, br))
        for i in range(P["bands"]):
            x = (-w / 2 + w * (i + 1) / (P["bands"] + 1))
            bands.merge(K.box(x, 0, bh / 2, 0.05, d + 0.02, bh + 0.005, bd))
        lid_h = h - bh
        lid = _lid_shape(w, d, lid_h, br)  # hinge line at local y=0, z=0; lid extends to -y
        ang = math.radians(P["lid_open"])
        hinge = (0.0, d / 2, bh)
        lid.rotate_x(-ang).translate(*hinge)
        nodes.append(Node("lid", lid, origin=hinge))
    nodes = [Node("container", body), Node("bands", bands)] + nodes
    return finalize(nodes, {"interactive": k == "chest"})


def _lid_shape(w, d, lid_h, role):
    """Half-round lid along X, flat bottom at z=0 spanning y in [-d, 0] (hinge at y=0)."""
    pts = [(-d, 0.0), (0.0, 0.0)]
    for i in range(1, 6):
        a = math.pi * i / 6
        pts.append((-d / 2 + d / 2 * math.cos(a), lid_h * math.sin(a)))
    # extrude the (y, z) profile along x
    rings = [[(x, y, z) for y, z in pts] for x in (-w / 2, w / 2)]
    return K.loft(rings, role, smooth=False)


# ------------------------------------------------------------------ lamp
@register("furn.lamp", V, "furniture", {
    "kind": S.enum("floor", ["floor", "table", "hanging", "lantern", "sphere"]),
    "height": S.num(1.6, 0.2, 2.2), "shade": S.enum("cone", ["cone", "sphere", "drum", "dome"]),
    "shade_size": S.num(0.35, 0.1, 0.8), "base": S.enum("disc", ["disc", "tripod", "flower"]),
    "stand_role": S.enum("chrome", STAND),
}, "Lamp: floor/table/hanging/lantern/sphere; shade cone/sphere/drum/dome (emissive role 'light'). height = overall "
   "height (floor/table/sphere/lantern) or cord drop (hanging); base applies to floor/table/sphere, shade to "
   "floor/table/hanging.", rules=lambda P: (
    "table lamp height must be <= 0.9 m" if P["kind"] == "table" and P["height"] > 0.9 else
    "lantern height must be <= 0.6 m" if P["kind"] == "lantern" and P["height"] > 0.6 else
    "lamp shade %.2f m too big for height %.2f m" % (P["shade_size"], P["height"])
    if P["kind"] in ("floor", "table", "sphere") and P["shade_size"] > 0.8 * P["height"] else None))
def lamp(P, seed):
    h, s = P["height"], P["shade_size"]
    sr = P["stand_role"]
    k = P["kind"]
    stand = K.Mesh()
    shade = K.Mesh()
    top = h
    if k in ("floor", "table", "sphere"):
        rb = max(0.08, s * 0.55)
        if P["base"] == "disc":
            stand.merge(K.lathe([(0, 0), (rb, 0), (rb * 0.9, 0.035), (0, 0.035)], 12, sr))
        elif P["base"] == "flower":
            stand.merge(K.prism(K.plan2d("flower", rb * 2.2, rb * 2.2, 18), 0, 0.04, sr))
        else:
            for i in range(3):
                a = math.tau * i / 3
                stand.merge(K.tube([(math.cos(a) * rb, math.sin(a) * rb, 0.02), (0, 0, min(h * 0.25, 0.4))], 0.012, 4, sr))
        stand.merge(post(0, 0, 0.02, h - s * 0.5, 0.015, sr, 6))
    if k == "hanging":  # height = cord drop from the ceiling canopy to the shade
        zc0 = s * 0.5
        stand.merge(post(0, 0, zc0 + s * 0.2, zc0 + h, 0.01, sr, 4))
        stand.merge(K.lathe([(0, zc0 + h - 0.02), (0.08, zc0 + h - 0.02), (0.08, zc0 + h + 0.02), (0, zc0 + h + 0.02)], 8, sr))
    if k == "lantern":
        lh = h
        stand.merge(K.box(0, 0, 0.02, s * 0.8, s * 0.8, 0.04, sr))
        stand.merge(K.box(0, 0, lh - 0.02, s * 0.8, s * 0.8, 0.04, sr))
        for sx in (-1, 1):
            for sy in (-1, 1):
                stand.merge(post(sx * s * 0.36, sy * s * 0.36, 0.02, lh - 0.02, 0.012, sr, 4, square=True))
        stand.merge(K.lathe_closed([(0.035, lh + 0.02), (0.05, lh + 0.02), (0.05, lh + 0.09), (0.035, lh + 0.09)], 6, sr))
        shade.merge(K.box(0, 0, lh / 2, s * 0.62, s * 0.62, lh - 0.1, "light"))
        return finalize([Node("lamp_stand", stand), Node("lamp_shade", shade)], {"emits_light": True})
    zc = h - s * 0.5 if k != "hanging" else s * 0.5
    sh = P["shade"] if k != "sphere" else "sphere"
    if sh == "cone":
        shade.merge(K.lathe_closed([(s * 0.18, zc + s * 0.45), (s * 0.5, zc - s * 0.45), (s * 0.47, zc - s * 0.45),
                                    (s * 0.15, zc + s * 0.45)], 12, "light"))
    elif sh == "drum":
        shade.merge(K.lathe_closed([(s * 0.42, zc - s * 0.35), (s * 0.45, zc - s * 0.35), (s * 0.45, zc + s * 0.35),
                                    (s * 0.42, zc + s * 0.35)], 12, "light"))
    elif sh == "dome":
        shade.merge(K.lathe([(0, zc + s * 0.4), (s * 0.3, zc + s * 0.3), (s * 0.5, zc - s * 0.1), (s * 0.52, zc - s * 0.3),
                             (0, zc - s * 0.3)][::-1], 12, "light"))
    else:
        shade.merge(K.sphere(0, 0, zc, s / 2, s / 2, s / 2, 10, 7, "light"))
    return finalize([Node("lamp_stand", stand), Node("lamp_shade", shade)], {"emits_light": True})


# furn.pod and furn.console moved to core/gen_molded.py (sculpted rewrite, 2026-11-07 continuation 3).


# ------------------------------------------------------------------ rug
@register("furn.rug", V, "furniture", {
    "shape": S.enum("oval", ["rect", "round", "oval"]),
    "width": S.num(2.0, 0.6, 4.0), "depth": S.num(1.4, 0.6, 4.0), "thickness": S.num(0.02, 0.01, 0.06),
    "fringe": S.boolean(False), "rug_role": S.enum("fur", SOFT),
}, "Rug: thin slab, rect/round/oval, optional fringe.")
def rug(P, seed):
    w, d = P["width"], P["depth"]
    if P["shape"] == "round":
        w = d = min(w, d)
    slab = K.prism(K.plan2d(P["shape"], w, d, 18), 0, P["thickness"], P["rug_role"])
    fr = K.Mesh()
    if P["fringe"] and P["shape"] == "rect":
        for sx in (-1, 1):
            fr.merge(K.box(sx * (w / 2 + 0.03), 0, P["thickness"] * 0.4, 0.07, d * 0.9, P["thickness"] * 0.8, "rope"))
    return finalize([Node("rug", slab), Node("fringe", fr)])


# ------------------------------------------------------------------ hearth / stove / heater
@register("furn.hearth", V, "furniture", {
    "kind": S.enum("fireplace", ["fireplace", "stove", "brazier", "heater"]),
    "width": S.num(1.2, 0.5, 2.0), "height": S.num(1.1, 0.5, 2.0), "depth": S.num(0.6, 0.4, 1.0),
    "fire": S.boolean(True), "body_role": S.enum("stone", STRUCT),
}, "Heat source: stone fireplace, stove with pipe, brazier, molded heater (emissive 'fire').")
def hearth(P, seed):
    k, w, h, d = P["kind"], P["width"], P["height"], P["depth"]
    br = P["body_role"]
    body = K.Mesh()
    fire = K.Mesh()
    fz = 0.08
    if k == "fireplace":
        for sx in (-1, 1):
            body.merge(K.box(sx * (w / 2 - 0.12), 0, h * 0.4, 0.24, d, h * 0.8, br))
        body.merge(K.box(0, d / 2 - 0.08, h * 0.4, w - 0.46, 0.16, h * 0.8, br))
        body.merge(K.box(0, 0, h * 0.86, w + 0.1, d + 0.06, h * 0.14, br))
        body.merge(K.box(0, 0, 0.03, w - 0.44, d - 0.02, 0.06, br))
        fz = 0.06
        if P["fire"]:
            for i, x in enumerate((-0.12, 0.12)):
                body.merge(K.tube([(x - 0.18, -0.02 + 0.04 * i, fz + 0.05), (x + 0.18, 0.02 - 0.04 * i, fz + 0.05)], 0.045, 6, "wood"))
    elif k == "stove":
        body.merge(K.box(0, 0, h * 0.3, w * 0.6, d * 0.8, h * 0.6, br))
        body.merge(post(0, d * 0.2, h * 0.6 - 0.01, h * 1.6, 0.07, "metal", 8))
        fz = h * 0.12
    elif k == "brazier":
        R = min(w, d) / 2
        body.merge(K.lathe_closed([(R * 0.3, h * 0.55), (R, h * 0.75), (R, h * 0.82), (R * 0.9, h * 0.82), (R * 0.28, h * 0.62)], 10, "metal"))
        for i in range(3):
            a = math.tau * i / 3
            body.merge(K.tube([(math.cos(a) * R * 0.8, math.sin(a) * R * 0.8, 0.0), (math.cos(a) * R * 0.3, math.sin(a) * R * 0.3, h * 0.6)], 0.02, 4, "metal"))
        fz = h * 0.6
    else:  # heater
        R = min(w, d) / 2
        body.merge(K.lathe([(0, 0), (R, 0), (R * 1.05, h * 0.2), (R * 0.9, h * 0.9), (R * 0.5, h), (0, h)], 14, br))
        fire.merge(K.lathe_closed([(R * 0.98, h * 0.45), (R * 1.04, h * 0.45), (R * 1.0, h * 0.6), (R * 0.94, h * 0.6)], 14, "fire"))
    if P["fire"] and k == "stove":
        fire.merge(K.box(0, -d * 0.4 - 0.005, h * 0.25, w * 0.3, 0.012, h * 0.18, "fire"))
    elif P["fire"] and k != "heater":
        fh = 0.35 if k == "fireplace" else 0.25
        fw = 0.22 if k != "brazier" else min(w, d) * 0.3
        fire.merge(K.lathe([(0, fz), (fw, fz), (fw * 0.6, fz + fh * 0.5), (0, fz + fh)], 6, "fire"))
    return finalize([Node("hearth_body", body), Node("fire", fire)], {"emits_light": bool(P["fire"])})
