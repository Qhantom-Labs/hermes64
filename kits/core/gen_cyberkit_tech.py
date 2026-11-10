"""CYBERKIT tech props (cytech.*): vending machines, street terminals, server racks, drones, hover cars, motorbikes,
power conduits, rooftop vents and AC, overhead cables, barriers, street lights, rain puddles, antenna clusters,
utility cabinets, security cameras and charging posts.

Static dressing only (drones and hover cars are parked or hover in place; no animation, no logic). Lit parts sample
the pack's slot atlases (light rows, book displays), bodies use the painted panel roles (body, body_alt, hull,
hull_alt), so every prop recolours with the pack. Floor props stand on y = 0 (origin floor_center); wall props mount
on the wall face (origin opening_floor, wall at z = 0, the prop toward +z / the street).
"""
import math

from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .gen_cyberkit_tower import gem, slot_rect
from .rng import rng

V = "1.0.0"
SLOT = S.enum("a", list(C.SLOTS), "neon accent slot (pack palette roles: a/b/c/d)")


def free_meta(**kw):
    return C.grid_meta("free", None, [], **kw)


def wall_meta(**kw):
    return C.grid_meta("wall_face", None, [C.sock("wall_mount", (0, 0, 0), "n")], **kw)


# ---------------------------------------------------------------- cytech.vending
@register("cytech.vending", V, "furniture", {
    "kind": S.enum("drink", ["drink", "snack", "capsule"]), "accent": SLOT,
}, "Vending machine: a chamfered painted body with a lit product panel (book atlas menu cell), a dark dispensing "
   "slot, a neon header strip and side stripe; the capsule kind wears a glass dome of toy capsules.",
    origin="floor_center")
def vending(P, seed):
    k = P["kind"]
    W, D_, H = (1.0, 0.8, 1.9) if k != "capsule" else (0.8, 0.7, 1.3)
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    body.merge(C.slab(0, 0, 0.0, W, D_, H, "body", c=0.06))
    body.merge(C.slab(0, -D_ / 2 + 0.06, 0.12, W * 0.55, 0.14, 0.22, "opening", c=0.02))
    if k == "capsule":
        deco.merge(C.lathe_at(0, 0, H - 0.02, [(W * 0.42, 0.0), (W * 0.42, 0.35), (W * 0.3, 0.6), (0.0, 0.68)], 8, "orb", smooth=True))
        cards.merge(C.face_card(0, -D_ / 2, 0.45, W * 0.75, 0.62, "book", C.cell_uv("book", "menu"), lift=C.LIFT))
    else:
        cards.merge(C.face_card(-0.06, -D_ / 2, 0.55, W * 0.68, 1.1, "book", C.cell_uv("book", "menu" if k == "drink" else "monitor"),
                                lift=C.LIFT))
        body.merge(C.slab(W * 0.36, -D_ / 2 + 0.04, 0.9, 0.16, 0.1, 0.36, "trim", c=0.02))
    rect = slot_rect(P["accent"])
    cards.merge(C.strip((-W / 2 + 0.05, -D_ / 2 - C.LIFT, H - 0.12), (W / 2 - 0.05, -D_ / 2 - C.LIFT, H - 0.12), 0.1, "light", (0, -1, 0), rect))
    cards.merge(C.face_card(W / 2, 0.0, 0.2, D_ - 0.2, 0.14, "hull_alt", None, facing="+x", lift=C.LIFT))
    return C.finish([Node("body", body, "solid"), Node("dome", deco, "solid"), Node("front", cards, "card")],
                    free_meta(emitter={"slot": P["accent"]}, bake_lights=[C.light((0, -0.9, 1.0), 2.2, 0.5)]))


# ---------------------------------------------------------------- cytech.terminal
@register("cytech.terminal", V, "furniture", {
    "kind": S.enum("kiosk", ["kiosk", "wall", "atm"]), "accent": SLOT,
}, "Street terminal: a tapered pedestal kiosk with an angled lit screen (book monitor cell), a wall-hung info panel, "
   "or an ATM block with keypad and card slot.", origin="floor_center")
def terminal(P, seed):
    k = P["kind"]
    body, cards = K.Mesh(), K.Mesh()
    rect = slot_rect(P["accent"])
    if k == "kiosk":
        body.merge(C.taper(0, 0, 0.0, 1.05, 0.55, 0.45, 0.38, 0.32, 0.06, 0.05, "body_alt", top="trim"))
        head = C.slab(0, 0, 0.0, 0.8, 0.14, 0.62, "body", c=0.04)
        head.rotate_x(math.radians(-20)).translate(0, 0.05, 1.0)
        body.merge(head)
        scr = C.face_card(0, -0.075, 0.06, 0.66, 0.48, "book", C.cell_uv("book", "monitor"), lift=C.LIFT)
        scr.rotate_x(math.radians(-20)).translate(0, 0.05, 1.0)
        cards.merge(scr)
        cards.merge(C.strip((-0.27, -0.24, 0.3), (0.27, -0.24, 0.3), 0.05, "light", (0, -1, 0), rect))
    elif k == "wall":
        body.merge(C.slab(0, 0.1, 0.9, 0.9, 0.2, 1.2, "body", c=0.04))
        cards.merge(C.face_card(0, 0.0, 1.05, 0.7, 0.9, "book", C.cell_uv("book", "monitor"), lift=C.LIFT))
        body.merge(C.rod((0, 0.15, 0.0), (0, 0.15, 0.92), 0.06, 4, "post"))
    else:
        body.merge(C.slab(0, 0, 0.0, 0.9, 0.7, 1.8, "body_alt", c=0.06))
        body.merge(C.wedge(0, -0.35, 0.95, 0.75, 0.3, 0.12, 0.02, "trim", c=0.02))
        cards.merge(C.face_card(0, -0.35, 1.2, 0.56, 0.42, "book", C.cell_uv("book", "monitor"), lift=C.LIFT))
        cards.merge(C.face_card(0, -0.35, 0.6, 0.4, 0.28, "book", C.cell_uv("book", "menu"), lift=C.LIFT))
        cards.merge(C.strip((-0.4, -0.36, 1.72), (0.4, -0.36, 1.72), 0.06, "light", (0, -1, 0), rect))
    return C.finish([Node("body", body, "solid"), Node("screen", cards, "card")], free_meta(emitter={"slot": P["accent"]}))


# ---------------------------------------------------------------- cytech.rack
@register("cytech.rack", V, "furniture", {
    "units": S.integer(1, 1, 4, "cabinets side by side"), "accent": SLOT, "cables": S.boolean(True),
    "height": S.num(2.1, 1.8, 2.9, "cabinet height in metres (taller rows frame a hall)"),
}, "Server rack row: vented dark cabinets with rows of status lights (light atlas row strips) and a cable bundle "
   "looping out of the top into the ceiling tray.", origin="floor_center")
def rack(P, seed):
    n = P["units"]
    H = P.get("height", 2.1)
    # default literals kept so the shipped 2.1 m builds stay byte-identical
    rows, top, tend = (6, 2.08, 2.7) if H == 2.1 else (int((H - 0.45) / 0.27), H - 0.02, H + 0.6)
    body, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    rect = slot_rect(P["accent"])
    for i in range(n):
        x = (i - (n - 1) / 2) * 0.68
        body.merge(C.slab(x, 0, 0.0, 0.64, 0.9, H, "body_alt", c=0.03))
        for r in range(rows):
            z = 0.35 + r * 0.27
            cards.merge(C.strip((x - 0.2, -0.45 - C.LIFT, z), (x + 0.12 + 0.06 * (r % 2), -0.45 - C.LIFT, z), 0.035, "light", (0, -1, 0), rect))
        if P["cables"]:
            deco.merge(C.tube(C.catenary((x - 0.15, 0.1, top), (x - 0.15, 0.2, tend), -0.15, 4), 0.05, 4, "rope"))
    return C.finish([Node("cabinets", body, "solid"), Node("cables", deco, "solid"), Node("lights", cards, "card")],
                    free_meta(emitter={"slot": P["accent"]}))


# ---------------------------------------------------------------- cytech.drone
@register("cytech.drone", V, "furniture", {
    "kind": S.enum("courier", ["courier", "patrol", "camera"]), "accent": SLOT,
}, "Quad drone (static dressing, placed hovering): a lathed hull pod, four arms with rotor rings, a glowing belly "
   "lamp; a parcel box (courier), a light bar (patrol) or a camera ball (camera).", origin="floor_center")
def drone(P, seed):
    k = P["kind"]
    body, deco = K.Mesh(), K.Mesh()
    body.merge(C.lathe_at(0, 0, 0.18, [(0.0, 0.0), (0.16, 0.03), (0.22, 0.12), (0.18, 0.22), (0.0, 0.26)], 8, "hull", smooth=True))
    for i in range(4):
        a = K.TAU * (i + 0.5) / 4
        ex, ey = 0.42 * math.cos(a), 0.42 * math.sin(a)
        body.merge(C.rod((0.12 * math.cos(a), 0.12 * math.sin(a), 0.32), (ex, ey, 0.34), 0.025, 4, "metal"))
        body.merge(C.lathe_at(ex, ey, 0.32, [(0.0, 0.0), (0.17, 0.0), (0.17, 0.04), (0.0, 0.04)], 6, "trim", smooth=False))
    deco.merge(gem(0, 0, 0.16, 0.06, P["accent"], "core"))
    if k == "courier":
        body.merge(C.slab(0, 0, 0.0, 0.28, 0.24, 0.16, "wood", c=0.02))
    elif k == "patrol":
        deco.merge(C.neon_tube([(-0.16, 0.0, 0.46), (0.16, 0.0, 0.46)], 0.025, "light", slot_rect(P["accent"])))
    else:
        body.merge(K.sphere(0, -0.12, 0.12, 0.08, 0.08, 0.08, 6, 4, "chrome"))
    return C.finish([Node("drone", body, "solid"), Node("lamp", deco, "solid")], free_meta(hover=True))


# ---------------------------------------------------------------- cytech.hovercar
def car_hull(L, W, H, nose, roof=0.0):
    """Lofted wedge hull: sections from nose to tail (rounded-chamfered), a cabin bump."""
    secs = []
    stations = [(-L / 2, 0.55 * W, 0.18, 0.42 * H), (-L / 2 + nose, 0.98 * W, 0.1, 0.62 * H), (-L * 0.05, W, 0.08, 0.7 * H + roof),
                (L * 0.25, W, 0.08, 0.68 * H + roof), (L / 2 - 0.25, 0.92 * W, 0.12, 0.62 * H), (L / 2, 0.8 * W, 0.2, 0.5 * H)]
    for y, w, z0, z1 in stations:
        c = min(0.18, w * 0.2)
        sec = [(-w / 2 + c, z0), (w / 2 - c, z0), (w / 2, z0 + c), (w / 2, z1 - c), (w / 2 - c, z1), (-w / 2 + c, z1), (-w / 2, z1 - c), (-w / 2, z0 + c)]
        secs.append([(x, -y, z) for x, z in sec])
    return K.loft(secs, "hull", smooth=False, cap_roles=("hull", "hull"))


@register("cytech.hovercar", V, "vehicle", {
    "kind": S.enum("sedan", ["sedan", "taxi", "van", "patrol"]), "accent": SLOT, "hover": S.num(0.35, 0.0, 1.2, "pod clearance"),
}, "Hover car (static prop): a lofted wedge hull, a glass canopy, four glowing hover pods instead of wheels, an "
   "underglow strip and tail lights; taxi (roof glyph sign, hazard stripe), van (tall box) or patrol (light bar).",
    origin="floor_center")
def hovercar(P, seed):
    k = P["kind"]
    L, W, H = (4.4, 1.9, 1.3) if k != "van" else (4.8, 2.0, 1.9)
    hv = P["hover"]
    body, glass, deco, cards = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    hull = car_hull(L, W, H, 1.1, 0.0 if k != "van" else 0.5)
    hull.translate(0, 0, hv)
    body.merge(hull)
    cz = hv + 0.7 * H + (0.0 if k != "van" else 0.5)
    can = [(-0.7, 0.9), (0.7, 0.9), (0.62, 0.0), (-0.62, 0.0)]
    secs = []
    for y, sc, dz in ((-1.0, 0.7, 0.1), (-0.55, 1.0, 0.42), (0.6, 1.0, 0.45), (1.0, 0.8, 0.1)):
        secs.append([(x * sc * W / 1.6, y, cz - 0.05 + z * dz / 0.9 * 0.9) for x, z in can])
    if k != "van":
        glass.merge(K.loft(secs, "glass", smooth=False))
    rect = slot_rect(P["accent"])
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * W * 0.38, sy * L * 0.3
            deco.merge(C.lathe_at(x, y, max(0.0, hv - 0.18), [(0.0, 0.0), (0.24, 0.06), (0.28, 0.2), (0.22, 0.3), (0.0, 0.3)], 8, "metal",
                                  smooth=True))
            deco.merge(gem(x, y, max(0.0, hv - 0.18) + 0.03, 0.13, P["accent"], "bright"))
    for sx in (-1, 1):
        cards.merge(C.strip((sx * (W / 2 + 0.01), -L * 0.36, hv + 0.2), (sx * (W / 2 + 0.01), L * 0.36, hv + 0.2), 0.06, "light", (sx, 0, 0), rect))
    tail = slot_rect("b")
    cards.merge(C.strip((-W * 0.38, L / 2 + 0.01, hv + 0.42 * H), (W * 0.38, L / 2 + 0.01, hv + 0.42 * H), 0.08, "light", (0, 1, 0), tail))
    cards.merge(C.strip((-W * 0.3, -L / 2 - 0.01, hv + 0.3 * H), (W * 0.3, -L / 2 - 0.01, hv + 0.3 * H), 0.06, "light", (0, -1, 0),
                        slot_rect("c")))
    if k == "taxi":
        body.merge(C.slab(0, 0.2, cz + 0.42, 0.7, 0.28, 0.24, "frame", c=0.03))
        cards.merge(C.face_card(0, 0.06, cz + 0.45, 0.6, 0.18, "screen", C.cell_uv("screen", "sign_c0"), lift=C.LIFT))
        for sx in (-1, 1):
            cards.merge(C.face_card(sx * (W / 2 + 0.005), 0.0, hv + 0.5 * H, L * 0.6, 0.12, "hull_alt", None,
                                    facing="+x" if sx > 0 else "-x"))
    elif k == "patrol":
        deco.merge(C.neon_tube([(-0.5, 0.2, cz + 0.5), (0.0, 0.2, cz + 0.5)], 0.05, "light", slot_rect("b")))
        deco.merge(C.neon_tube([(0.02, 0.2, cz + 0.5), (0.5, 0.2, cz + 0.5)], 0.05, "light", slot_rect("a")))
    return C.finish([Node("hull", body, "solid"), Node("canopy", glass, "solid"), Node("pods", deco, "solid"),
                     Node("lights", cards, "card")], free_meta(hover=hv > 0, emitter={"slot": P["accent"]}))


# ---------------------------------------------------------------- cytech.bike
@register("cytech.bike", V, "vehicle", {"accent": SLOT, "kind": S.enum("street", ["street", "racer"])},
          "Neon motorbike (parked): two disc wheels with glowing rims, a lofted fairing, a leather seat, a headlight "
          "and tail strip; racer = low, long fairing.", origin="floor_center")
def bike(P, seed):
    racer = P["kind"] == "racer"
    body, deco, cards = K.Mesh(), K.Mesh(), K.Mesh()
    R = 0.34
    for y in (-0.72, 0.72):
        w = C.lathe_at(0, 0, 0, [(0.0, -0.08), (R * 0.6, -0.09), (R, -0.05), (R, 0.05), (R * 0.6, 0.09), (0.0, 0.08)], 10, "rope",
                       smooth=True)
        w.rotate_y(math.pi / 2).translate(0, y, R)
        body.merge(w)
        rim = [(0.0, y + R * 0.8 * math.cos(K.TAU * i / 10), R + R * 0.8 * math.sin(K.TAU * i / 10)) for i in range(10)]
        deco.merge(C.neon_tube([(0.1, p[1], p[2]) for p in rim], 0.02, "light", slot_rect(P["accent"]), closed=True))
    secs = []
    prof = [(-0.95, 0.15, 0.62, 0.9), (-0.5, 0.3, 0.55, 1.05 if not racer else 0.85), (0.2, 0.32, 0.55, 0.92 if not racer else 0.8),
            (0.8, 0.18, 0.62, 0.85 if not racer else 0.7)]
    for y, w, z0, z1 in prof:
        secs.append([(-w / 2, y, z0), (w / 2, y, z0), (w / 2 * 0.8, y, z1), (-w / 2 * 0.8, y, z1)])
    body.merge(K.loft(secs, "hull", smooth=False))
    body.merge(C.slab(0, 0.25, 0.86 if not racer else 0.76, 0.28, 0.6, 0.12, "leather", c=0.04))
    cards.merge(C.face_card(0, -0.96, 0.7, 0.14, 0.12, "light", slot_rect("c")))
    cards.merge(C.face_card(0, 0.81, 0.7, 0.14, 0.06, "light", slot_rect("b"), facing="+y"))
    return C.finish([Node("bike", body, "solid"), Node("rims", deco, "solid"), Node("lamps", cards, "card")], free_meta())


# ---------------------------------------------------------------- cytech.conduit
@register("cytech.conduit", V, "structure", {
    "length": S.num(6.0, 2.0, 12.0), "pipes": S.integer(3, 1, 4), "accent": SLOT,
}, "Power conduit run along a wall: parallel insulated pipes on stand-off clamps, junction boxes with a hazard band "
   "and a status light (wall-mounted, origin on the wall face).", origin="opening")
def conduit(P, seed):
    Lc, n = P["length"], P["pipes"]
    m, cards = K.Mesh(), K.Mesh()
    for i in range(n):
        z = 0.25 + i * 0.22
        m.merge(C.rod((-Lc / 2, -0.14, z), (Lc / 2, -0.14, z), 0.07 if i == 0 else 0.05, 6, "metal" if i else "rope"))
    k = max(2, int(Lc // 2.5) + 1)
    for j in range(k):
        x = -Lc / 2 + 0.3 + (Lc - 0.6) * j / (k - 1)
        m.merge(C.slab(x, -0.06, 0.12, 0.08, 0.12, 0.25 + n * 0.22, "trim", c=0.01))
    for x in (-Lc * 0.25, Lc * 0.3):
        m.merge(C.slab(x, -0.16, 0.05, 0.5, 0.3, 0.6, "body_alt", c=0.04))
        cards.merge(C.face_card(x, -0.31, 0.1, 0.46, 0.1, "band", None, lift=C.LIFT))
        m.merge(gem(x + 0.15, -0.32, 0.5, 0.04, P["accent"], "core"))
    return C.finish([Node("pipes", m, "solid"), Node("bands", cards, "card")], wall_meta(), cy=False, ground=False)


# ---------------------------------------------------------------- cytech.vent
@register("cytech.vent", V, "furniture", {
    "kind": S.enum("ac", ["ac", "exhaust", "fan", "duct"]), "accent": SLOT,
}, "Rooftop machinery: an AC condenser with a fan grille, a mushroom exhaust stack, a big turbine fan housing or an "
   "elbow duct with a hazard band. Roof clutter that makes a skyline read as lived-in.", origin="floor_center")
def vent(P, seed):
    k = P["kind"]
    m, cards = K.Mesh(), K.Mesh()
    if k == "ac":
        m.merge(C.slab(0, 0, 0.0, 1.4, 0.9, 1.0, "body", c=0.06))
        cards.merge(C.flat_card(0, 0, 1.005, 0.8, 0.7, "metal"))
        for sx in (-1, 1):
            m.merge(C.slab(sx * 0.6, 0, -0.0, 0.12, 0.8, 0.08, "trim", c=0.01))
    elif k == "exhaust":
        m.merge(C.lathe_at(0, 0, 0, [(0.35, 0.0), (0.35, 0.25), (0.22, 0.32), (0.22, 1.6), (0.5, 1.75), (0.45, 1.95), (0.0, 2.05)], 8, "metal",
                           smooth=False))
    elif k == "fan":
        m.merge(C.lathe_at(0, 0, 0, [(1.0, 0.0), (1.05, 0.5), (0.95, 0.9), (0.8, 0.95), (0.8, 0.85), (0.0, 0.85)], 12, "body_alt", smooth=False))
        cards.merge(K.Mesh().add([(0.78 * math.cos(K.TAU * i / 12), 0.78 * math.sin(K.TAU * i / 12), 0.86) for i in range(12)],
                                 [tuple(range(12))], "metal", False))
    else:
        path = [(0.0, 0.0, 0.0), (0.0, 0.0, 1.3), (0.0, -0.3, 1.75), (0.0, -0.9, 1.9)]
        m.merge(C.tube(path, 0.32, 6, "metal", smooth=False))
        m.merge(C.slab(0, 0, 0.0, 0.9, 0.9, 0.2, "trim", c=0.04))
        cards.merge(C.face_card(0, -0.33, 0.55, 0.5, 0.12, "band", None, lift=0.0))
    return C.finish([Node("unit", m, "solid"), Node("grille", cards, "card")], free_meta())


# ---------------------------------------------------------------- cytech.cables
@register("cytech.cables", V, "structure", {
    "span": S.num(12.0, 4.0, 16.0), "count": S.integer(4, 1, 6), "sag": S.num(0.9, 0.2, 2.0), "lanterns": S.boolean(False),
    "accent": SLOT,
}, "Overhead cable run spanning a street or alley: a bundle of sagging catenary cables between two wall brackets, "
   "optionally strung with small lit lanterns. Origin at mid-span, bracket height (placed at the anchor height).",
    origin="opening")
def cables(P, seed):
    r = rng(seed, "cytech.cables")
    Sp, n, sag = P["span"], P["count"], P["sag"]
    m, deco = K.Mesh(), K.Mesh()
    for i in range(n):
        dz = 0.12 * i
        dy = 0.18 * (i - (n - 1) / 2)
        s = sag * (0.8 + 0.4 * r.random())
        m.merge(C.tube(C.catenary((-Sp / 2, dy, -dz), (Sp / 2, dy * 0.6, -dz - 0.1 * i), s, 8), 0.025 + 0.01 * (i % 2), 4, "rope"))
        if P["lanterns"] and i == 0:
            for t in (0.2, 0.4, 0.6, 0.8):
                z = -sag * 4 * t * (1 - t) - 0.05
                deco.merge(C.lathe_at(-Sp / 2 + Sp * t, dy * (1 - 0.4 * t), z - 0.32, [(0.0, 0.0), (0.12, 0.05), (0.16, 0.15), (0.12, 0.28), (0.0, 0.3)],
                                      6, "light", smooth=False))
    for sx in (-1, 1):
        m.merge(C.slab(sx * (Sp / 2 + 0.05), 0, -0.25 - 0.12 * n, 0.2, 0.3, 0.4 + 0.12 * n, "metal", c=0.03))
    if P["lanterns"]:
        u, v = (C.LIGHT[P["accent"]][0] + 16) / C.LIGHT_SIZE, 1.0 - (C.LIGHT[P["accent"]][1] + 2.5) / C.LIGHT_SIZE
        deco.uv = [("n", [(u, v)] * len(f)) for f in deco.f]
    return C.finish([Node("cables", m, "solid"), Node("lanterns", deco, "solid")],
                    C.grid_meta("street_span", None, [C.sock("street_span", (0, 0, 0), "s", span_m=Sp)]), cx=True, cy=False, ground=False)


# ---------------------------------------------------------------- cytech.barrier
@register("cytech.barrier", V, "furniture", {
    "kind": S.enum("jersey", ["jersey", "rail", "bollards"]), "length": S.num(2.4, 1.2, 4.0), "accent": SLOT,
}, "Street barrier: a sloped jersey block with a hazard band and reflector, a light-strip rail barrier on feet, or "
   "a row of light-capped bollards.", origin="floor_center")
def barrier(P, seed):
    k, Lb = P["kind"], P["length"]
    m, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    rect = slot_rect(P["accent"])
    if k == "jersey":
        prof = [(-0.3, 0.0), (0.3, 0.0), (0.3, 0.08), (0.12, 0.3), (0.09, 0.8), (-0.09, 0.8), (-0.12, 0.3), (-0.3, 0.08)]
        m.merge(K.loft([[(xx, py, pz) for py, pz in prof] for xx in (-Lb / 2, Lb / 2)], "stone", smooth=False, cap_roles=("stone", "stone")))
        cards.merge(C.face_card(0, -0.105, 0.45, Lb * 0.8, 0.14, "band", None, lift=0.02))
    elif k == "rail":
        for sx in (-1, 1):
            m.merge(C.slab(sx * (Lb / 2 - 0.15), 0, 0.0, 0.3, 0.6, 0.08, "metal", c=0.02))
            m.merge(C.rod((sx * (Lb / 2 - 0.15), 0, 0.06), (sx * (Lb / 2 - 0.15), 0, 1.0), 0.04, 4, "post"))
        m.merge(C.slab(0, 0, 0.75, Lb, 0.06, 0.25, "band", c=0.01))
        cards.merge(C.strip((-Lb / 2 + 0.1, -0.04, 0.62), (Lb / 2 - 0.1, -0.04, 0.62), 0.05, "light", (0, -1, 0), rect))
    else:
        n = max(2, int(Lb / 0.9) + 1)
        for i in range(n):
            x = -Lb / 2 + Lb * i / (n - 1)
            m.merge(C.lathe_at(x, 0, 0, [(0.12, 0.0), (0.12, 0.85), (0.09, 0.95), (0.0, 0.97)], 6, "post", smooth=False))
            deco.merge(gem(x, 0, 0.8, 0.06, P["accent"], "bright"))
    return C.finish([Node("barrier", m, "solid"), Node("lamps", deco, "solid"), Node("bands", cards, "card")], free_meta())


# ---------------------------------------------------------------- cytech.street_light
@register("cytech.street_light", V, "structure", {
    "kind": S.enum("single", ["single", "double", "tall"]), "accent": S.enum("c", list(C.SLOTS), "lamp colour slot"),
}, "Street light: a tapered pole on a chamfered plinth, a curved arm (two for double) and a long lamp head with a lit "
   "underside (light atlas slot); the emitter sits under the head.", origin="floor_center")
def street_light(P, seed):
    k = P["kind"]
    H = 6.0 if k != "tall" else 8.0
    m, cards = K.Mesh(), K.Mesh()
    m.merge(C.slab(0, 0, 0.0, 0.5, 0.5, 0.5, "stone", c=0.08, top="trim"))
    m.merge(C.frustum(0, 0, 0.45, H, 0.12, 0.07, 6, "post"))
    arms = [1] if k != "double" else [-1, 1]
    rect = slot_rect(P["accent"])
    for s in arms:
        arc = [(s * 0.02, 0.0, H - 0.3), (s * 0.4, 0.0, H + 0.15), (s * 1.1, 0.0, H + 0.3), (s * 1.6, 0.0, H + 0.25)]
        m.merge(C.tube(arc, 0.055, 4, "post", smooth=False))
        hx = s * 1.9
        m.merge(C.wedge(hx, 0, H + 0.02, 0.9, 0.36, 0.22, 0.32, "frame", c=0.04))
        cards.merge(C.flat_card(hx, 0, H + 0.015, 0.78, 0.26, "light", rect, down=True))
    return C.finish([Node("pole", m, "solid"), Node("lamp", cards, "card")],
                    free_meta(emitter={"slot": P["accent"], "offset_m": [1.9, H - 0.3, 0.0]},
                              bake_lights=[C.light((1.9 * arms[-1], 0, 0.6), 4.0, 0.8)]))


# ---------------------------------------------------------------- cytech.puddle
@register("cytech.puddle", V, "furniture", {
    "size": S.num(1.8, 0.6, 3.6), "count": S.integer(2, 1, 4),
}, "Rain puddles: irregular flat water decals (water role: dark sheen with slow ripples) a few millimetres above "
   "the street, so wet asphalt catches the neon. Several blobs per piece.", origin="floor_center")
def puddle(P, seed):
    r = rng(seed, "cytech.puddle")
    m = K.Mesh()
    for i in range(P["count"]):
        cx, cy = (r.random() - 0.5) * P["size"] * 0.9, (r.random() - 0.5) * P["size"] * 0.9
        rad = P["size"] * (0.25 + 0.2 * r.random()) / max(1, P["count"] * 0.6)
        k = 9
        pts = []
        for j in range(k):
            a = K.TAU * j / k
            rr = rad * (0.7 + 0.5 * r.random())
            pts.append((cx + rr * math.cos(a) * 1.4, cy + rr * math.sin(a), 0.006 + 0.0005 * i))
        m.add(pts, [tuple(range(k))], "water", False, [("m", [(p[0], p[1]) for p in pts])])
    return C.finish([Node("water", m, "card")], free_meta(decal=True), ground=False)


# ---------------------------------------------------------------- cytech.antenna
@register("cytech.antenna", V, "furniture", {"accent": SLOT, "dishes": S.integer(2, 1, 3)},
          "Rooftop antenna cluster: a short mast with dish antennas on yokes, a whip array and a blinking beacon.",
          origin="floor_center")
def antenna(P, seed):
    m, deco = K.Mesh(), K.Mesh()
    m.merge(C.slab(0, 0, 0.0, 0.8, 0.8, 0.25, "trim", c=0.05))
    m.merge(C.frustum(0, 0, 0.2, 3.0, 0.08, 0.05, 6, "post"))
    for k in range(P["dishes"]):
        z = 0.9 + 0.7 * k
        a = K.TAU * (0.2 + 0.35 * k)
        d = C.lathe_at(0, 0, 0, [(0.0, 0.0), (0.3, 0.05), (0.5, 0.17), (0.47, 0.2), (0.0, 0.07)], 8, "chrome", smooth=True)
        d.rotate_y(math.pi / 2 - 0.3).translate(0.45, 0, 0).rotate_z(a).translate(0, 0, z)
        m.merge(d)
        m.merge(C.rod((0.06 * math.cos(a), 0.06 * math.sin(a), z), (0.4 * math.cos(a), 0.4 * math.sin(a), z), 0.025, 4, "metal"))
    for i in range(3):
        m.merge(C.rod((0.1 * (i - 1), 0.08, 2.9), (0.1 * (i - 1), 0.08, 3.8 - 0.2 * i), 0.012, 3, "metal"))
    deco.merge(gem(0, 0, 3.08, 0.08, P["accent"], "core"))
    return C.finish([Node("mast", m, "solid"), Node("beacon", deco, "solid")], free_meta())


# ---------------------------------------------------------------- cytech.utility
@register("cytech.utility", V, "furniture", {"accent": SLOT, "kind": S.enum("cabinet", ["cabinet", "transformer"])},
          "Utility cabinet or transformer box: a vented painted housing with hazard band, conduit stubs into the "
          "ground, a small status light and a glyph warning plate.", origin="floor_center")
def utility(P, seed):
    tr = P["kind"] == "transformer"
    W, D_, H = (1.6, 1.0, 1.5) if tr else (0.9, 0.5, 1.4)
    m, cards = K.Mesh(), K.Mesh()
    m.merge(C.slab(0, 0, 0.1, W, D_, H, "body_alt", c=0.05, top="trim"))
    m.merge(C.slab(0, 0, 0.0, W + 0.1, D_ + 0.1, 0.12, "stone", c=0.04))
    cards.merge(C.face_card(0, -D_ / 2, 0.25, W * 0.85, 0.12, "band", None, lift=C.LIFT))
    cards.merge(C.face_card(0, -D_ / 2, H - 0.45, 0.42, 0.21, "screen", C.cell_uv("screen", "sign_c1"), lift=C.LIFT))
    m.merge(gem(W / 2 - 0.15, -D_ / 2 - 0.02, H - 0.1, 0.035, P["accent"], "core"))
    if tr:
        for i in range(3):
            m.merge(C.lathe_at(-0.4 + 0.4 * i, 0.1, H + 0.1, [(0.07, 0.0), (0.1, 0.1), (0.07, 0.2), (0.1, 0.3), (0.0, 0.35)], 6, "chrome", smooth=False))
    return C.finish([Node("box", m, "solid"), Node("plates", cards, "card")], free_meta())


# ---------------------------------------------------------------- cytech.camera / charger
@register("cytech.camera", V, "prop", {"accent": SLOT},
          "Security camera on a wall bracket: a chamfered housing with a lens ring and a red-eye status lamp (wall "
          "mounted, origin on the wall face).", origin="opening_floor")
def camera(P, seed):
    m, deco = K.Mesh(), K.Mesh()
    m.merge(C.slab(0, -0.03, 0.0, 0.16, 0.06, 0.22, "metal", c=0.02))
    m.merge(C.rod((0, -0.05, 0.12), (0, -0.25, 0.2), 0.025, 4, "post"))
    head = C.slab(0, 0, 0, 0.18, 0.42, 0.16, "body", c=0.03)
    head.rotate_x(math.radians(-15)).translate(0, -0.42, 0.12)
    m.merge(head)
    deco.merge(gem(0, -0.65, 0.2, 0.035, P["accent"], "core"))
    return C.finish([Node("camera", m, "solid"), Node("lamp", deco, "solid")], wall_meta(), cy=False)


@register("cytech.charger", V, "furniture", {"accent": SLOT},
          "Charging post for hover cars and bikes: a slim chamfered pedestal with a lit display, a coiled cable "
          "holster and a neon ring at the base.", origin="floor_center")
def charger(P, seed):
    m, cards, deco = K.Mesh(), K.Mesh(), K.Mesh()
    m.merge(C.taper(0, 0, 0.0, 1.5, 0.42, 0.3, 0.32, 0.24, 0.06, 0.05, "body", top="trim"))
    cards.merge(C.face_card(0, -0.15, 0.95, 0.24, 0.32, "book", C.cell_uv("book", "monitor"), lift=0.04))
    m.merge(C.tube([(0.2, 0.0, 1.0), (0.32, -0.05, 0.8), (0.3, -0.1, 0.5), (0.18, -0.05, 0.35)], 0.025, 4, "rope", smooth=False))
    ring = [(0.36 * math.cos(K.TAU * i / 10), 0.28 * math.sin(K.TAU * i / 10), 0.03) for i in range(10)]
    deco.merge(C.neon_tube(ring, 0.025, "light", slot_rect(P["accent"]), closed=True))
    return C.finish([Node("post", m, "solid"), Node("ring", deco, "solid"), Node("screen", cards, "card")], free_meta())
