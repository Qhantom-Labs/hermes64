"""ANCIENTKIT carving props (relic.*), theme-agnostic (Blender space, +Z up, front faces -Y = glTF south).

Ten generators: statues of ORIGINAL invented figures (the Keeper: a robed figure holding a sun disc under a fan crown;
the Crested Guardian: a seated beast with plate crest and curled tail; the buried Keeper head; a small seated gold
idol), altars, braziers (runtime emitters), urns, glyph steles and tablets (original glyph grammar), sarcophagi,
pressure-plate tiles, banners, a reliquary coffer and a sun-dial puzzle dais. No real-culture iconography: the figures
are built from the kit's own motifs (disc, fan, stepped bars, plate crest) and the glyphs from its own grammar.
"""
import math

from . import gen_ancientkit_core as A
from . import meshkit as K
from . import schema as S
from .asset import Asset, Node, register
from .genutil import finalize
from .rng import rng

V = "1.0.0"
TAU = math.tau


def top_panel(cx, cy, z, w, d, t, face_role, edge_role, bevel=0.02):
    """Closed bevelled slab z-t..z whose TOP face shows the whole texture of face_role (normalized UVs)."""
    b = max(0.0, min(bevel, 0.3 * w, 0.3 * d))
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
    zb = z - t
    v = [(x0 + b, y0 + b, z), (x1 - b, y0 + b, z), (x1 - b, y1 - b, z), (x0 + b, y1 - b, z),
         (x0, y0, zb), (x1, y0, zb), (x1, y1, zb), (x0, y1, zb)]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)]
    return K.Mesh().add(v, faces, [face_role] + [edge_role] * 5, False,
                        [("n", [(0, 0), (1, 0), (1, 1), (0, 1)])] + [None] * 5).orient_outward()


def disc(cx, cy, cz, r, t, role, segs=10, facing="-y"):
    """Closed coin (sun disc) standing upright facing -Y (or lying flat with facing='up')."""
    m = K.lathe([(r, -t / 2), (r, t / 2)], segs, role, smooth=False)
    if facing == "-y":
        m.rotate_x(math.pi / 2)
    return m.translate(cx, cy, cz)


# ---------------------------------------------------------------- relic.statue
def _keeper(r, scale=1.0, with_plinth=True):
    s = scale
    nodes = []
    if with_plinth:
        nodes.append(Node("plinth", A.stack(0, 0, [(0.0, 1.5 * s, 1.3 * s, 0.05), (0.35 * s, 1.5 * s, 1.3 * s, 0.05),
                                                   (0.35 * s, 1.25 * s, 1.05 * s, 0.04), (0.55 * s, 1.25 * s, 1.05 * s, 0.04)], "step")))
    z0 = 0.55 * s if with_plinth else 0.0
    robe = A.lathe([(0.0, z0), (0.56 * s, z0), (0.5 * s, z0 + 0.5 * s), (0.4 * s, z0 + 1.35 * s), (0.36 * s, z0 + 1.85 * s),
                    (0.42 * s, z0 + 2.15 * s), (0.22 * s, z0 + 2.32 * s), (0.0, z0 + 2.34 * s)], 8, "post", smooth=True, ry=0.78)
    nodes.append(Node("robe", robe))
    back = A.taper_box(0, 0.3 * s, z0, z0 + 2.55 * s, 0.7 * s, 0.24 * s, 0.5 * s, 0.2 * s, "trim", bevel=0.04)
    nodes.append(Node("back_pillar", back))
    arms = K.Mesh()
    for sx in (-1, 1):
        arm = K.tube([(sx * 0.4 * s, -0.02 * s, z0 + 2.1 * s), (sx * 0.38 * s, -0.12 * s, z0 + 1.62 * s),
                      (sx * 0.16 * s, -0.36 * s, z0 + 1.6 * s)], 0.1 * s, 5, "post", smooth=True)
        arms.merge(arm)
    nodes.append(Node("arms", arms))
    nodes.append(Node("disc", disc(0, -0.44 * s, z0 + 1.66 * s, 0.26 * s, 0.07 * s, "chrome", 10)))
    head = K.sphere(0, -0.02 * s, z0 + 2.62 * s, 0.2 * s, 0.22 * s, 0.27 * s, 7, 4, "post", smooth=True)
    nodes.append(Node("head", head))
    crown = A.fan_crown(0.5 * s, 0.07 * s, "trim", rays=5)
    crown.translate(0, 0.1 * s, z0 + 2.56 * s)
    nodes.append(Node("crown", crown))
    nodes.append(Node("band", A.lathe([(0.0, z0 + 2.74 * s), (0.21 * s, z0 + 2.74 * s), (0.23 * s, z0 + 2.84 * s), (0.0, z0 + 2.86 * s)], 7, "chrome", smooth=False)))
    return nodes


def _guardian(r):
    nodes = [Node("plinth", A.stack(0, 0, [(0.0, 1.3, 2.6, 0.05), (0.32, 1.3, 2.6, 0.05), (0.32, 1.1, 2.4, 0.04), (0.5, 1.1, 2.4, 0.04)], "step"))]
    z0 = 0.5
    nodes.append(Node("body", K.blob(0, 0.35, z0 + 0.62, 0.48, 0.78, 0.6, "post", segs=7, rings=4)))
    nodes.append(Node("chest", K.blob(0, -0.38, z0 + 1.05, 0.42, 0.42, 0.55, "post", segs=7, rings=4)))
    legs = K.Mesh()
    for sx in (-1, 1):
        legs.merge(A.frustum(sx * 0.24, -0.62, z0, z0 + 0.95, 0.24, 0.28, 0.17, 0.2, "post"))
        legs.merge(A.frustum(sx * 0.25, -0.74, z0, z0 + 0.14, 0.26, 0.36, 0.2, 0.28, "post"))
        legs.merge(K.blob(sx * 0.36, 0.55, z0 + 0.32, 0.18, 0.42, 0.34, "post", segs=6, rings=3))
    nodes.append(Node("legs", legs))
    nodes.append(Node("head", K.blob(0, -0.6, z0 + 1.72, 0.3, 0.32, 0.3, "post", segs=7, rings=4)))
    nodes.append(Node("snout", A.frustum(0, -0.88, z0 + 1.56, z0 + 1.78, 0.26, 0.3, 0.2, 0.24, "post")))
    crest = K.Mesh()
    for k in range(3):
        fin = A.frustum(0, 0, 0.0, 0.42 - 0.08 * k, 0.07, 0.3, 0.04, 0.16, "trim")
        fin.rotate_x(0.35 + 0.3 * k).translate(0, -0.6 + 0.2 * k, z0 + 1.92 - 0.12 * k)
        crest.merge(fin)
    for sx in (-1, 1):
        ear = A.frustum(0, 0, 0.0, 0.24, 0.12, 0.06, 0.04, 0.03, "post")
        ear.rotate_y(sx * 0.6).translate(sx * 0.2, -0.56, z0 + 1.9)
        crest.merge(ear)
    nodes.append(Node("crest", crest))
    tail = K.tube([(0.0, 1.05, z0 + 0.4), (0.25, 1.22, z0 + 0.62), (0.32, 1.05, z0 + 0.95), (0.14, 0.92, z0 + 1.08)], 0.08, 5, "post", smooth=True)
    nodes.append(Node("tail", tail))
    nodes.append(Node("collar", disc(0, -0.78, z0 + 1.3, 0.13, 0.05, "chrome", 8)))
    return nodes


@register("relic.statue", V, "structure", {
    "figure": S.enum("keeper", ["keeper", "guardian", "buried", "idol"]),
}, "Statue of an ORIGINAL invented figure: keeper = robed standing figure holding a gold sun disc under a fan crown of "
   "three fins, with a back pillar, on a stepped plinth (3.4 m); guardian = seated crested beast (plate crest, curled "
   "tail, gold collar disc) on a long plinth; buried = the colossal keeper head sunk to the chin in a sand mound with "
   "one fallen crown fin; idol = a small seated gold figure with a rayed disc head on a carved pedestal.",
   origin="floor_center")
def statue(P, seed):
    r = rng(seed, "relic.statue", P["figure"])
    f = P["figure"]
    if f == "keeper":
        nodes = _keeper(r)
    elif f == "guardian":
        nodes = _guardian(r)
    elif f == "buried":
        nodes = [Node("mound", A.lathe([(0.0, 0.0), (2.6, 0.0), (1.9, 0.42), (1.0, 0.78), (0.0, 0.86)], 9, "sand", smooth=True, rx=1.0, ry=0.8))]
        head = K.sphere(0, 0, 0, 0.95, 1.05, 1.3, 8, 5, "post", smooth=True)
        head.rotate_x(-0.12).rotate_y(0.18).translate(0, 0.0, 1.45)
        nodes.append(Node("head", head))
        crown = A.fan_crown(1.9, 0.26, "trim", rays=5)
        crown.rotate_y(0.18).translate(0.1, 0.5, 1.75)
        nodes.append(Node("crown", crown))
        band = A.lathe([(0.0, 0.0), (0.98, 0.0), (1.02, 0.3), (0.0, 0.34)], 8, "chrome", smooth=False)
        band.rotate_x(-0.12).rotate_y(0.18).translate(0.0, 0.0, 2.15)
        nodes.append(Node("band", band))
        shard = A.frustum(0, 0, 0.0, 0.9, 0.6, 0.26, 0.2, 0.2, "trim")
        shard.rotate_y(math.pi / 2 - 0.15).rotate_z(0.6).translate(2.0, -1.2, 0.15)
        nodes.append(Node("fallen_ray", shard))
    else:
        nodes = [Node("pedestal", A.stack(0, 0, [(0.0, 0.8, 0.8, 0.04), (0.18, 0.8, 0.8, 0.04), (0.18, 0.6, 0.6, 0.03),
                                                 (0.82, 0.56, 0.56, 0.03), (0.82, 0.74, 0.74, 0.03), (0.96, 0.74, 0.74, 0.03)], "trim"))]
        nodes.append(Node("relief", A.panel(0, -0.31, 0.24, 0.42, 0.5, 0.03, "door", "trim")))
        body = K.blob(0, 0, 1.22, 0.2, 0.17, 0.26, "chrome", segs=7, rings=4)
        head = disc(0, -0.02, 1.62, 0.15, 0.08, "chrome", 8)
        rays = K.Mesh()
        for k in range(6):
            a = TAU * k / 6 + math.pi / 6
            ray = A.frustum(0, 0, 0.0, 0.12, 0.05, 0.04, 0.02, 0.03, "chrome")
            ray.rotate_y(a).translate(math.sin(a) * 0.16, -0.02, 1.62 + math.cos(a) * 0.16)
            rays.merge(ray)
        nodes += [Node("idol", body), Node("head", head), Node("rays", rays)]
    meta = A.grid_meta("free", None, [A.sock("landmark", (0, 0, 0), "s")], figure=f)
    return finalize(nodes, meta)


# ---------------------------------------------------------------- relic.altar
@register("relic.altar", V, "furniture_large", {
    "style": S.enum("basin", ["basin", "sun", "fire"]),
}, "Altar: stepped base, a dressed block with a carved procession relief on its front and a moulded top. basin = "
   "glazed offering bowl; sun = gold sun disc on a stand (the shrine focus); fire = a fire bowl (runtime emitter).",
   origin="floor_center")
def altar(P, seed):
    st = P["style"]
    nodes = [Node("base", A.stack(0, 0, [(0.0, 2.2, 1.4, 0.05), (0.2, 2.2, 1.4, 0.05), (0.2, 1.9, 1.15, 0.04), (0.32, 1.9, 1.15, 0.04)], "step"))]
    nodes.append(Node("block", A.chamfer_box(0, 0, 0.32, 1.6, 0.9, 0.72, "trim", bevel=0.05)))
    nodes.append(Node("relief", A.panel(0, -0.47, 0.4, 1.36, 0.56, 0.03, "wall_alt", "trim")))
    nodes.append(Node("top", A.chamfer_box(0, 0, 1.04, 1.9, 1.15, 0.16, "post", bevel=0.04)))
    meta = A.grid_meta("free", None, [A.sock("focus", (0, 0, 1.2), "up")], style=st)
    if st == "basin":
        nodes.append(Node("bowl", A.lathe([(0.0, 1.2), (0.3, 1.2), (0.46, 1.32), (0.5, 1.44), (0.42, 1.44), (0.0, 1.3)], 9, "body_alt", smooth=True)))
    elif st == "sun":
        stand = A.taper_box(0, 0.1, 1.2, 1.62, 0.3, 0.22, 0.18, 0.14, "post", bevel=0.02)
        nodes += [Node("stand", stand), Node("disc", disc(0, 0.04, 2.05, 0.46, 0.09, "chrome", 12))]
        rays = K.Mesh()
        for k in range(8):
            a = TAU * k / 8
            ray = A.frustum(0, 0, 0.0, 0.2, 0.09, 0.05, 0.03, 0.04, "chrome")
            ray.rotate_y(a).translate(math.sin(a) * 0.5, 0.04, 2.05 + math.cos(a) * 0.5)
            rays.merge(ray)
        nodes.append(Node("rays", rays))
    else:
        nodes.append(Node("bowl", A.lathe([(0.0, 1.2), (0.26, 1.2), (0.44, 1.36), (0.46, 1.46), (0.0, 1.38)], 8, "metal", smooth=True)))
        nodes.append(Node("flame", A.flame(0, 0, 1.36, 0.62, 0.24, "fire", 6)))
        meta["emitter"] = {"offset_gltf": [0.0, 1.8, 0.0], "radius_m": 5.0, "warm": True}
    return finalize(nodes, meta)


# ---------------------------------------------------------------- relic.brazier
@register("relic.brazier", V, "furniture", {
    "style": S.enum("tripod", ["tripod", "pedestal", "pit", "unlit"]),
}, "Brazier: gold-leaf bowl on a bronze tripod, on a carved stone pedestal, or a low stone fire pit; a lit flame "
   "(emissive) and a runtime warm emitter (meta.emitter, mirrored in view.json look.emitters). unlit = cold tripod.",
   origin="floor_center")
def brazier(P, seed):
    st = P["style"]
    nodes = []
    if st in ("tripod", "unlit"):
        legs = K.Mesh()
        for k in range(3):
            a = TAU * k / 3 + math.pi / 2
            legs.merge(K.tube([(0.42 * math.cos(a), 0.42 * math.sin(a), 0.0), (0.3 * math.cos(a), 0.3 * math.sin(a), 0.55),
                               (0.2 * math.cos(a), 0.2 * math.sin(a), 0.98)], 0.045, 4, "metal", smooth=True))
        nodes.append(Node("legs", legs))
        nodes.append(Node("ring", K.lathe([(0.0, 0.46), (0.33, 0.46), (0.33, 0.52), (0.0, 0.52)], 8, "metal", smooth=False)))
        top = 1.0
    elif st == "pedestal":
        nodes.append(Node("pedestal", A.lathe([(0.0, 0.0), (0.42, 0.0), (0.42, 0.14), (0.3, 0.22), (0.24, 0.62), (0.3, 0.86),
                                               (0.4, 0.94), (0.0, 0.96)], 8, "post", smooth=False)))
        top = 0.96
    else:
        ring = K.lathe_closed([(0.42, 0.0), (0.7, 0.0), (0.66, 0.32), (0.48, 0.34)], 9, "stone", smooth=False)
        nodes.append(Node("pit", ring))
        nodes.append(Node("embers", A.lathe([(0.0, 0.0), (0.5, 0.0), (0.46, 0.12), (0.0, 0.16)], 8, "light", smooth=True)))
        top = 0.05
    if st != "pit":
        nodes.append(Node("bowl", A.lathe([(0.0, top), (0.2, top), (0.42, top + 0.18), (0.48, top + 0.3), (0.42, top + 0.3),
                                           (0.0, top + 0.16)], 9, "metal", smooth=True)))
    meta = A.grid_meta("free", None, [A.sock("light", (0, 0, 0), "up")], style=st)
    if st != "unlit":
        fz = top + 0.16 if st != "pit" else 0.1
        nodes.append(Node("flame", A.flame(0, 0, fz, 0.7 if st != "pit" else 0.85, 0.26 if st != "pit" else 0.34, "fire", 6)))
        meta["emitter"] = {"offset_gltf": [0.0, round(fz + 0.4, 3), 0.0], "radius_m": 6.0, "warm": True}
    return finalize(nodes, meta)


# ---------------------------------------------------------------- relic.urn
@register("relic.urn", V, "prop", {
    "shape": S.enum("jar", ["jar", "amphora", "bowl", "broken"]), "height": S.num(0.9, 0.4, 1.4),
}, "Painted clay urn (terracotta with painted bands and a zigzag frieze; glazed bowl): jar, two-handled amphora, wide "
   "bowl, or a broken jar with a jagged rim and a shard.", origin="floor_center")
def urn(P, seed):
    r = rng(seed, "relic.urn", P["shape"])
    h, sh = P["height"], P["shape"]
    nodes = []
    if sh in ("jar", "broken"):
        prof = [(0.0, 0.0), (0.18 * h, 0.0), (0.36 * h, 0.28 * h), (0.38 * h, 0.55 * h), (0.24 * h, 0.82 * h), (0.15 * h, 0.9 * h),
                (0.2 * h, h), (0.0, h * 0.97)]
        if sh == "broken":
            prof = prof[:5] + [(0.0, 0.8 * h)]
        m = A.lathe(prof, 8, "body", smooth=True)
        if sh == "broken":
            m.apply(lambda a: a + ((a[:, 2:3] > 0.7 * h) * (a[:, 2:3] - 0.7 * h) * 0.0))
        nodes.append(Node("body", m))
        if sh == "broken":
            shard = A.chamfer_box(0.42 * h, -0.3 * h, 0.0, 0.22 * h, 0.16 * h, 0.04, "body", bevel=0.01)
            shard.rotate_z(0.7)
            nodes.append(Node("shard", shard))
    elif sh == "amphora":
        prof = [(0.0, 0.0), (0.06 * h, 0.0), (0.1 * h, 0.1 * h), (0.28 * h, 0.4 * h), (0.27 * h, 0.62 * h), (0.11 * h, 0.8 * h),
                (0.12 * h, 0.95 * h), (0.0, 0.95 * h)]
        nodes.append(Node("body", A.lathe(prof, 7, "body", smooth=True)))
        nodes.append(Node("foot", A.lathe([(0.0, 0.0), (0.13 * h, 0.0), (0.1 * h, 0.08 * h), (0.0, 0.08 * h)], 7, "body", smooth=False)))
        hd = K.Mesh()
        for sx in (-1, 1):
            hd.merge(K.tube([(sx * 0.11 * h, 0, 0.88 * h), (sx * 0.24 * h, 0, 0.86 * h), (sx * 0.24 * h, 0, 0.68 * h)], 0.025 * h + 0.008, 3, "body", smooth=True))
        nodes.append(Node("handles", hd))
    else:
        prof = [(0.0, 0.0), (0.16 * h, 0.0), (0.42 * h, 0.22 * h), (0.5 * h, 0.4 * h), (0.44 * h, 0.4 * h), (0.0, 0.18 * h)]
        nodes.append(Node("bowl", A.lathe(prof, 9, "body_alt", smooth=True)))
    return finalize(nodes, A.grid_meta("free", None, [], shape=sh))


# ---------------------------------------------------------------- relic.tablet
@register("relic.tablet", V, "arch", {
    "style": S.enum("stele", ["stele", "tablet", "fallen", "awakened"]),
}, "Glyph stone: stele = round-topped standing slab with an incised glyph face (original glyph grammar, hull role) on a "
   "base; tablet = a low inclined tablet on a stand (paper role glyphs); fallen = a stele broken in two in the sand; "
   "awakened = stele whose glyphs glow (emissive screen role + a cool runtime emitter).", origin="floor_center")
def tablet(P, seed):
    r = rng(seed, "relic.tablet", P["style"])
    st = P["style"]
    nodes = []
    meta = A.grid_meta("free", None, [A.sock("read", (0, -0.6, 0), "s")], style=st)
    if st in ("stele", "awakened"):
        nodes.append(Node("base", A.chamfer_box(0, 0, 0, 1.5, 0.8, 0.35, "step", bevel=0.05)))
        outline = K.opening2d("arch", 1.1, 2.3, 10)
        slab = A.front_prism([(x, z + 0.35) for x, z in outline], -0.18, 0.18, "trim")
        nodes.append(Node("slab", slab))
        face_role = "screen" if st == "awakened" else "hull"
        nodes.append(Node("glyphs", A.panel(0, -0.2, 0.55, 0.86, 1.5, 0.03, face_role, "trim")))
        if st == "awakened":
            meta["emitter"] = {"offset_gltf": [0.0, 1.4, 0.4], "radius_m": 3.0, "warm": False}
    elif st == "tablet":
        nodes.append(Node("stand", A.taper_box(0, 0.1, 0, 0.75, 0.9, 0.5, 0.75, 0.4, "post", bevel=0.04)))
        tab = A.panel(0, 0.0, 0.0, 1.1, 0.75, 0.12, "paper", "trim")
        tab.rotate_x(-0.55).translate(0, -0.05, 0.72)
        nodes.append(Node("tablet", tab))
    else:
        nodes.append(Node("base_part", A.chamfer_box(0, 0, 0, 1.5, 0.8, 0.35, "step", bevel=0.05)))
        jag = [(0.55, 0.35), (0.55, 0.95), (0.3, 0.78), (0.1, 1.02), (-0.18, 0.74), (-0.38, 0.9), (-0.55, 0.7), (-0.55, 0.35)]
        nodes.append(Node("stump", A.front_prism(K.ccw(jag), -0.18, 0.18, "trim")))
        top = A.front_prism([(x, z) for x, z in K.opening2d("arch", 1.1, 1.2, 10)], -0.18, 0.18, "trim")
        g = A.panel(0, -0.2, 0.1, 0.86, 0.9, 0.03, "hull", "trim")
        top.merge(g)
        top.rotate_x(-math.pi / 2 + 0.08).rotate_z(0.4).translate(0.7, -1.2, 0.2)
        nodes.append(Node("fallen_top", top))
    return finalize(nodes, meta)


# ---------------------------------------------------------------- relic.sarcophagus
@register("relic.sarcophagus", V, "furniture_large", {
    "state": S.enum("closed", ["closed", "open", "broken"]),
}, "Sarcophagus: a stone chest with incised glyph bands along both sides on a plinth, and a battered lid carved with "
   "the sun-wheel relief; open = lid slid aside showing the dark interior; broken = lid cracked in two on the floor.",
   origin="floor_center")
def sarcophagus(P, seed):
    st = P["state"]
    L, W, Hh = 2.5, 1.2, 0.95
    nodes = [Node("plinth", A.chamfer_box(0, 0, 0, L + 0.3, W + 0.3, 0.2, "step", bevel=0.04))]
    nodes.append(Node("chest", A.chamfer_box(0, 0, 0.2, L, W, Hh, "trim", bevel=0.05)))
    bands = K.Mesh()
    for sy in (-1, 1):
        p = A.panel(0, -(W / 2) - 0.02, 0.35, L - 0.4, 0.5, 0.03, "hull", "trim")
        if sy > 0:
            p.rotate_z(math.pi)
        bands.merge(p)
    nodes.append(Node("glyph_bands", bands))
    lid = A.taper_box(0, 0, 0.0, 0.32, L + 0.12, W + 0.12, L - 0.2, W - 0.3, "post", bevel=0.04)
    lid.merge(top_panel(0, 0, 0.335, L - 0.5, W - 0.5, 0.03, "door", "post"))
    if st == "closed":
        lid.translate(0, 0, 0.2 + Hh)
        nodes.append(Node("lid", lid))
    elif st == "open":
        nodes.append(Node("interior", top_panel(0, 0, 0.2 + Hh + 0.005, L - 0.3, W - 0.3, 0.02, "opening", "opening")))
        lid.rotate_z(0.35).translate(0.55, -0.45, 0.2 + Hh + 0.02)
        nodes.append(Node("lid", lid))
    else:
        nodes.append(Node("interior", top_panel(0, 0, 0.2 + Hh + 0.005, L - 0.3, W - 0.3, 0.02, "opening", "opening")))
        half_a = A.taper_box(0, 0, 0.0, 0.32, 1.25, W + 0.12, 1.15, W - 0.3, "post", bevel=0.04)
        half_b = half_a.copy()
        half_a.rotate_x(0.25).rotate_z(0.5).translate(-0.9, -1.35, 0.25)
        half_b.rotate_y(-0.2).rotate_z(-0.3).translate(1.0, -1.4, 0.18)
        nodes += [Node("lid_a", half_a), Node("lid_b", half_b)]
    return finalize(nodes, A.grid_meta("free", None, [A.sock("use", (0, -W / 2 - 0.5, 0), "s")], state=st))


# ---------------------------------------------------------------- relic.plate
@register("relic.plate", V, "prop", {
    "style": S.enum("sun", ["sun", "glyph"]), "state": S.enum("raised", ["raised", "pressed"]),
}, "Pressure-plate floor tile (1.2 m): a sunk stone frame and a plate carrying the sun inlay (frame role) or a glyph "
   "(hull role); raised = 8 cm proud, pressed = flush. Socket 'plate' at the centre (triggers stay in game data).",
   origin="floor_center")
def plate(P, seed):
    up = 0.08 if P["state"] == "raised" else 0.015
    face = "frame" if P["style"] == "sun" else "hull"
    w, b = 1.2, 0.14
    outer = [(-w / 2, -w / 2), (w / 2, -w / 2), (w / 2, w / 2), (-w / 2, w / 2)]
    inner = [(-w / 2 + b, -w / 2 + b), (w / 2 - b, -w / 2 + b), (w / 2 - b, w / 2 - b), (-w / 2 + b, w / 2 - b)]
    frame = K.prism(outer, 0.0, 0.05, "trim", holes=[inner])
    nodes = [Node("frame", frame), Node("plate", top_panel(0, 0, up, w - 2 * b - 0.04, w - 2 * b - 0.04, up - 0.002 if up > 0.03 else 0.012, face, "stone"))]
    return finalize(nodes, A.grid_meta("free", None, [A.sock("plate", (0, 0, 0), "up")], state=P["state"]))


# ---------------------------------------------------------------- relic.banner
@register("relic.banner", V, "soft", {
    "length": S.num(2.2, 1.2, 3.0),
}, "Woven banner on a wall bracket (wall-mounted, origin on the wall face): a crossbar with gold finials and a hanging "
   "cloth with a woven border and an original rayed-sun emblem (fabric role, two-sided).", wall_mounted=True,
   origin="wall_back")
def banner(P, seed):
    L = P["length"]
    top = 3.6
    bar = K.Mesh()
    bar.merge(K.tube([(-0.55, -0.18, top), (0.55, -0.18, top)], 0.04, 5, "wood", smooth=True))
    for sx in (-1, 1):
        bar.merge(K.sphere(sx * 0.6, -0.18, top, 0.06, 0.06, 0.06, 6, 3, "chrome", smooth=True))
    bar.merge(A.chamfer_box(0, -0.09, top - 0.06, 0.12, 0.18, 0.12, "metal", bevel=0.01))
    w = 0.9
    cloth = K.Mesh()
    segs = 3
    pts = []
    for s in range(segs + 1):
        t = s / segs
        z = top - 0.04 - L * t
        y = -0.2 - 0.06 * math.sin(math.pi * t)
        pts.append((z, y))
    for s in range(segs):
        (z0, y0), (z1, y1) = pts[s], pts[s + 1]
        v0, v1 = 1 - s / segs, 1 - (s + 1) / segs
        cloth.add([(-w / 2, y1, z1), (w / 2, y1, z1), (w / 2, y0, z0), (-w / 2, y0, z0)], [(0, 1, 2, 3)], "fabric", False,
                  [("n", [(0, v1), (1, v1), (1, v0), (0, v0)])])
    # point the tail: the last row narrows to a V
    cloth = A.weld(cloth)
    cloth = A.two_sided(cloth, 0.01)
    nodes = [Node("bar", bar), Node("cloth", cloth, "shell")]
    a = Asset(nodes, A.grid_meta("wall_face", None, [A.sock("wall", (0, 0, 0), "s")], length_m=L))
    return a


# ---------------------------------------------------------------- relic.coffer
@register("relic.coffer", V, "prop", {
    "state": S.enum("closed", ["closed", "open"]),
}, "Reliquary coffer (the goal object): a carved stone casket on four squat feet with gold corner caps and a lid "
   "carrying the sun inlay; open = lid tipped back on its hinge showing the dark inside.", origin="floor_center")
def coffer(P, seed):
    L, W, Hh = 0.9, 0.6, 0.42
    nodes = [Node("casket", A.chamfer_box(0, 0, 0.08, L, W, Hh, "trim", bevel=0.03))]
    feet = K.Mesh()
    for sx in (-1, 1):
        for sy in (-1, 1):
            feet.merge(A.frustum(sx * (L / 2 - 0.08), sy * (W / 2 - 0.08), 0.0, 0.11, 0.18, 0.18, 0.15, 0.15, "chrome"))
    nodes.append(Node("caps", feet))
    lid = A.frustum(0, 0, 0.0, 0.16, L + 0.06, W + 0.06, L - 0.12, W - 0.12, "trim")
    lid.merge(top_panel(0, 0, 0.17, L - 0.3, W - 0.24, 0.02, "frame", "chrome"))
    if P["state"] == "closed":
        lid.translate(0, 0, 0.08 + Hh)
    else:
        nodes.append(Node("inside", top_panel(0, 0, 0.08 + Hh + 0.004, L - 0.12, W - 0.12, 0.015, "opening", "opening")))
        lid.translate(0, -(W + 0.06) / 2, 0).rotate_x(1.9).translate(0, W / 2 + 0.05, 0.08 + Hh)
    nodes.append(Node("lid", lid))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("use", (0, -0.6, 0), "s")], state=P["state"]))


# ---------------------------------------------------------------- relic.dial
@register("relic.dial", V, "arch", {
    "rays": S.integer(8, 6, 12), "style": S.enum("whole", ["whole", "ruined"]),
}, "Sun-dial puzzle dais: a round stepped platform, a ring of tapered ray stones and a central gnomon with a gold tip; "
   "ruined = two rays toppled and a cracked step. Socket 'puzzle' at the gnomon.", origin="floor_center")
def dial(P, seed):
    r = rng(seed, "relic.dial", P["style"])
    nodes = [Node("dais", A.lathe([(0.0, 0.0), (2.4, 0.0), (2.4, 0.25), (1.85, 0.25), (1.85, 0.5), (0.0, 0.5)], 12, "step", smooth=False))]
    rays = K.Mesh()
    n = P["rays"]
    for k in range(n):
        a = TAU * k / n
        if P["style"] == "ruined" and k in (2, 5):
            st = A.frustum(0, 0, 0.0, 0.5, 0.3, 0.3, 0.22, 0.22, "trim")
            st.rotate_x(math.pi / 2 - 0.1).rotate_z(a + 0.4).translate(2.7 * math.cos(a), 2.7 * math.sin(a), 0.15)
            rays.merge(st)
            continue
        st = A.frustum(0, 0, 0.0, 0.62 if k % 2 == 0 else 0.4, 0.3, 0.3, 0.16, 0.16, "trim")
        st.rotate_z(a).translate(2.1 * math.cos(a), 2.1 * math.sin(a), 0.25)
        rays.merge(st)
    nodes.append(Node("rays", rays))
    nodes.append(Node("gnomon", A.frustum(0, 0, 0.5, 2.1, 0.36, 0.36, 0.14, 0.14, "trim")))
    nodes.append(Node("tip", A.lathe([(0.12, 2.08), (0.0, 2.4)], 4, "chrome", smooth=False, start=math.pi / 4)))
    nodes.append(Node("inlay", top_panel(0, 0, 0.505, 1.4, 1.4, 0.004, "frame", "trim")))
    return finalize(nodes, A.grid_meta("free", None, [A.sock("puzzle", (0, 0, 0.5), "up")], style=P["style"]))
