"""Deterministic drafter (stdlib): measurements + controlled notes + kit library -> KITS 3.1.0 pack data.

No pixels enter here: only rounded cluster centroids / statistics from measurements.json. Every choice is
recorded in `decisions` so NOTES.md and validation can explain it. Theme-free: the only theme knowledge is
in library/*.json (tagged shipped presets, material vocabulary, audio tag map)."""
import math

from . import colour as C

CORE_ROLES = (
    "wall wall_alt floor ceiling trim frame door glass view roof step rail post stone metal chrome "
    "body body_alt cushion fabric knit fur quilt screen light orb wood paper book leather rope fire "
    "grass snow sand rock dirt water ice bark foliage cap flower hull hull_alt band sky particle "
    "skin face headwear opening costume coat").split()

FOG_DENSITY = {"none": 0.0, "light": 0.25, "medium": 0.5, "heavy": 0.75, "very_heavy": 0.92}
CONTRAST_IX = {"low": 0, "medium": 1, "high": 2}
LIGHT_STEPS = {"low": 7, "medium": 9, "high": 11}
KEY_DIR = {"day": [0.3, -0.45, 0.85], "artificial": [0.3, -0.45, 0.85], "unknown": [0.4, -0.45, 0.8],
           "golden_hour": [0.7, -0.5, 0.5], "dawn": [0.7, -0.45, 0.5], "dusk": [0.65, -0.5, 0.55],
           "night": [0.25, -0.35, 0.9]}

# surface class of a role when no preset parameter names it (theme-free semantics of the core roles)
ROLE_CLASS = {
    "wall": "walls", "wall_alt": "walls", "floor": "floor", "step": "floor", "ceiling": "ceiling",
    "trim": "trim", "frame": "trim", "door": "trim", "rail": "trim", "post": "trim", "stone": "stone",
    "roof": "roof", "metal": "metal", "chrome": "metal", "band": "glass", "glass": "glass", "orb": "glass",
    "body": "furniture", "body_alt": "furniture", "wood": "wood", "hull": "furniture", "hull_alt": "furniture",
    "cushion": "soft", "fabric": "soft", "knit": "soft", "fur": "soft", "quilt": "soft", "leather": "soft",
    "screen": "emissive", "light": "emissive", "fire": "emissive", "paper": "paper", "book": "paper",
    "rope": "rope", "grass": "ground", "snow": "ground", "sand": "ground", "rock": "ground", "dirt": "ground",
    "ice": "ground", "water": "ground", "bark": "nature", "foliage": "nature", "cap": "nature", "flower": "nature",
    "view": "sky", "sky": "sky", "particle": "weather", "skin": "fixed", "face": "fixed", "headwear": "fixed",
    "opening": "fixed", "costume": "fixed", "coat": "fixed",
}
# preset parameter name -> surface class it paints
PARAM_CLASS = {
    "floor_role": "floor", "wall_role": "walls", "ceiling_role": "ceiling", "leaf_role": "trim",
    "shell_role": "furniture", "body_role": "furniture", "top_role": "furniture", "seat_role": "furniture",
    "hull_role": "furniture", "cover_role": "furniture", "board_role": "furniture",
    "cushion_role": "soft", "throw_role": "soft", "mattress_role": "soft", "blanket_role": "soft",
    "pillow_role": "soft", "rug_role": "soft", "sail_role": "soft",
    "foot_role": "metal", "leg_role": "metal", "base_role": "metal", "band_role": "metal", "stand_role": "metal",
    "trim_role": "metal", "rail_role": "metal", "head_role": "metal", "handle_role": "metal",
    "port_role": "glass", "text_role": "emissive", "deck_role": "floor", "pile_role": "trim",
}
CLASS_WEIGHT = {"floor": 1.2, "walls": 1.0, "ceiling": 0.3, "trim": 1.6, "furniture": 1.6, "soft": 1.6,
                "metal": 1.8, "glass": 1.0, "emissive": 1.0, "stone": 1.0, "roof": 1.0, "wood": 1.0}
# (visibility prior: the elevated 3/4 cameras games use see floors most and ceilings least; a role shared by
#  floor and ceiling, e.g. the lounge shell's 'wood', must take the floor's colour -- round-trip r4 finding)

STRUCTURAL = ["glossy_plastic", "plaster", "adobe", "stone", "brick", "concrete", "marble", "timber", "polished_wood",
              "ice", "cobble", "tile", "rock", "brushed_metal", "iron", "rusted_iron", "chrome", "coral", "crystal"]
FLOORING = ["timber", "polished_wood", "stone", "cobble", "tile", "marble", "concrete", "glossy_plastic", "sand",
            "snow", "ice", "dirt", "grass", "rock", "brushed_metal", "iron", "rusted_iron", "brick", "adobe", "mud", "moss"]
METALS = ["chrome", "brushed_metal", "iron", "brass", "rusted_iron"]
FURNITURE = ["glossy_plastic", "timber", "polished_wood", "chrome", "brushed_metal", "iron", "stone", "leather",
             "marble", "rusted_iron", "concrete", "coral", "crystal", "brass", "adobe"]
SOFT = ["knit", "fur", "quilted_vinyl", "leather", "cloth", "canvas"]
GROUND = ["snow", "sand", "grass", "dirt", "rock", "mud", "ice", "moss", "cobble", "stone"]
ROOF = ["thatch", "tile", "snow", "stone", "timber", "brushed_metal", "iron", "concrete", "adobe"]
NATURE = ["foliage", "moss", "grass", "coral", "crystal"]
OUTDOOR_GROUND = ["snow", "ice", "sand", "grass", "dirt", "mud", "moss", "rock"]
ROLE_IDENTITY = {"stone": "stone", "leather": "leather", "knit": "knit", "fur": "fur", "rope": "rope", "paper": "paper",
                 "snow": "snow", "sand": "sand", "rock": "rock", "dirt": "dirt", "ice": "ice", "water": "water"}
# (grass is not an identity role: a snow world paints its 'grass' role as snow, like polar_pod does)
SLOT_AFFINITY = 5
THEME_GROUND = {"polar": "snow", "desert": "sand", "forest": "grass", "jungle": "grass", "plains": "grass",
                "village": "grass", "swamp": "mud", "cave": "rock", "mine": "rock", "mountain": "rock",
                "ocean": "sand", "underwater": "sand", "coast": "sand", "harbor": "cobble", "city": "stone",
                "ruins": "stone", "temple": "stone", "castle": "stone", "habitat": "snow", "space": "rock",
                "lab": "concrete", "industrial": "concrete"}
# generic colour semantics for nature-ish materials: preferred OKLCh hue window (degrees)
MATERIAL_HUE = {"grass": (100, 170), "foliage": (100, 170), "moss": (90, 165), "sand": (55, 110),
                "dirt": (35, 90), "mud": (35, 90), "water": (180, 285), "timber": (35, 95), "polished_wood": (25, 85),
                "thatch": (60, 110), "brick": (15, 55), "rusted_iron": (25, 75), "coral": (0, 45), "adobe": (35, 85),
                "leather": (25, 80), "brass": (60, 105), "rope": (55, 105), "bark": (35, 90)}
SCENE_LAYERS = {
    "polar": [("domes", 0.34, 0.16, 9), ("trees", 0.30, 0.20, 5)], "habitat": [("domes", 0.34, 0.16, 9)],
    "forest": [("mountains", 0.38, 0.16, 6), ("forest", 0.32, 0.2, 14)], "village": [("roofs", 0.3, 0.14, 8)],
    "jungle": [("forest", 0.34, 0.26, 18)], "desert": [("hills", 0.3, 0.14, 5), ("mountains", 0.34, 0.18, 5)],
    "ocean": [("hills", 0.3, 0.05, 3)], "coast": [("hills", 0.32, 0.1, 4)], "harbor": [("roofs", 0.3, 0.12, 9)],
    "underwater": [("hills", 0.26, 0.07, 4), ("mountains", 0.3, 0.2, 5)],
    "cave": [("mountains", 0.3, 0.4, 9)], "mine": [("mountains", 0.3, 0.35, 8)],
    "mountain": [("mountains", 0.3, 0.3, 6)], "city": [("roofs", 0.3, 0.25, 12)], "ruins": [("huts", 0.3, 0.12, 6)],
    "temple": [("domes", 0.3, 0.2, 3)], "castle": [("roofs", 0.3, 0.2, 5)], "plains": [("hills", 0.3, 0.08, 4)],
    "swamp": [("trees", 0.3, 0.18, 10)], "underwater": [("hills", 0.3, 0.2, 5)], "space": [("mountains", 0.25, 0.1, 5)],
    "lab": [("roofs", 0.3, 0.1, 6)], "industrial": [("roofs", 0.3, 0.22, 8)],
}


def r4(x):
    v = round(float(x), 4)
    return 0.0 if v == 0 else v


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def lab_t(lab):
    return tuple(float(v) for v in lab)


def lerp(a, b, t):
    return a + (b - a) * t


# ================================================================== light rig / light ramp

def light_rig(notes, stats):
    tod = notes["time_of_day"]
    key_dir = list(KEY_DIR.get(tod, KEY_DIR["unknown"]))
    ci = CONTRAST_IX[notes["lighting"]["contrast"]]
    rms = stats["rms_contrast"]
    # measured contrast nudges the notes' contrast class by at most one step
    if rms > 0.17 and ci < 2:
        ci += 1
    elif rms < 0.07 and ci > 0:
        ci -= 1
    ambient = (0.56, 0.48, 0.40)[ci]
    key = (0.34, 0.44, 0.52)[ci]
    ground_L = stats["ground_L"]
    sky = 0.16 if notes["setting"] != "interior" or stats["sky_L"] > 0.6 else 0.10
    ground = round(clamp(0.02 + 0.14 * max(0.0, (ground_L - 0.35) / 0.6), 0.02, 0.16), 3)
    ao = (0.24, 0.28, 0.32)[ci]
    return {"key_dir": key_dir, "ambient": ambient, "key": key, "sky": sky, "ground": ground,
            "ao": ao, "ao_height": 0.45, "gamma": 1.0}, ci


def bake_t(rig, n, ao_share=0.0):
    """Light level the core bake gives a normal n (Blender z-up): lane-kits core/bake.py
    t = ambient + key*max(0,n.k) + sky*max(0,nz) + ground*max(0,-nz) - ao*(1-c)^2, c = clamp(z/ao_height),
    clamped to [0, 1] AFTER the contact term. ao_share = mean (1-c)^2 over the surface (1 at floor level)."""
    k = rig["key_dir"]
    kl = math.sqrt(sum(c * c for c in k))
    k = [c / kl for c in k]
    t = rig["ambient"] + rig["key"] * max(0.0, sum(a * b for a, b in zip(n, k))) + rig["sky"] * max(0.0, n[2]) \
        + rig["ground"] * max(0.0, -n[2])
    t -= rig.get("ao", 0.0) * ao_share
    return clamp(t, 0.0, 1.0) ** rig.get("gamma", 1.0)


def surface_t(rig):
    # contact AO: floors/ground sit at z=0 (full ao); a wall's measurable middle and the ceiling get none;
    # furniture (~0.8 m tall) averages (1-c)^2 over its height: ao_height / (3 * 0.8)
    ah = rig.get("ao_height", 0.35)
    obj_share = min(1.0, ah / (3.0 * 0.8))
    walls = [bake_t(rig, (math.cos(a), math.sin(a), 0.0)) for a in [i * math.pi / 4 for i in range(8)]]
    walls_obj = [bake_t(rig, (math.cos(a), math.sin(a), 0.0), obj_share) for a in [i * math.pi / 4 for i in range(8)]]
    floor = bake_t(rig, (0, 0, 1), 1.0)
    # terrain is displaced (core terrain.patch default amplitude 0.6 m): with z ~ U[0, 0.6] the mean contact
    # share is (ao_height / 3) / 0.6 -- not the full share of a flat floor (round-trip r11 yard finding)
    ground_share = min(1.0, (ah / 3.0) / 0.6)
    return {"floor": floor, "ceiling": bake_t(rig, (0, 0, -1)), "walls": sum(walls) / 8.0,
            "object": 0.5 * (sum(walls_obj) / 8.0) + 0.5 * bake_t(rig, (0, 0, 1), obj_share),
            "ground": bake_t(rig, (0, 0, 1), ground_share)}


def light_curve(shadow, highlight, n):
    """OKLab colours dark->bright: shadow-tinted dark end, highlight-tinted middle, neutral top."""
    S, H = lab_t(shadow), lab_t(highlight)
    L0 = clamp(S[0] * 0.5, 0.14, 0.30)
    out = []
    for i in range(n):
        t = i / (n - 1)
        L = L0 + (0.992 - L0) * t
        if t < 0.7:
            u = t / 0.7
            a = lerp(S[1] * 0.95, H[1] * 0.8, u)
            b = lerp(S[2] * 0.95, H[2] * 0.8, u)
        else:
            u = (t - 0.7) / 0.3
            a = lerp(H[1] * 0.8, 0.0, u)
            b = lerp(H[2] * 0.8, 0.0, u)
        out.append((L, a, b))
    return out


def light_at(curve_lab, t):
    """Continuous light colour (linear RGB) at bake level t from the light curve."""
    x = clamp(t, 0.0, 1.0) * (len(curve_lab) - 1)
    i = min(int(round(x)), len(curve_lab) - 1)  # the bake quantises to the nearest step
    return C.oklab_to_lin(curve_lab[i])


def albedo_of(lab, light_lin):
    lin = C.oklab_to_lin(lab)
    out = [clamp(c, 0.0, 1.5) / max(l, 0.02) for c, l in zip(lin, light_lin)]
    m = max(out)
    if m > 1.0:
        out = [c / m for c in out]
    return C.lin_to_oklab(tuple(clamp(c, 0.0, 1.0) for c in out))


# ================================================================== palette

def oklch_of(lab):
    return C.oklch(lab)


def hue_families(cols, neutral_c=0.035, gap=25.0, max_span=40.0):
    # tight spans: wood browns (~60-70 deg), creams (~90) and foliage greens (~120-135) form one continuous
    # hue chain; a 75-degree span let one 'family' ramp run brown -> olive -> green (round-trip r3 finding)
    neutral = [c for c in cols if c["C"] < neutral_c]
    chrom = sorted([c for c in cols if c["C"] >= neutral_c], key=lambda c: (c["h"], c["L"]))
    groups = []
    if chrom:
        n = len(chrom)
        gaps = [((chrom[(i + 1) % n]["h"] - chrom[i]["h"]) % 360.0) if n > 1 else 360.0 for i in range(n)]
        cuts = [i for i, g in enumerate(gaps) if g > gap]
        if not cuts:
            groups = [chrom]
        else:
            start = (cuts[0] + 1) % n
            order = chrom[start:] + chrom[:start]
            cur = []
            cutset = {(c - start) % n for c in cuts}
            for i, c in enumerate(order):
                cur.append(c)
                if i in cutset:
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
    # split families whose hue span is too wide at their widest internal gap
    out = []
    stack = list(groups)
    while stack:
        g = stack.pop(0)
        hs = [c["h"] for c in g]
        span = sum(((hs[i + 1] - hs[i]) % 360.0) for i in range(len(hs) - 1))
        if span > max_span and len(g) >= 2:
            gi = max(range(len(g) - 1), key=lambda i: ((hs[i + 1] - hs[i]) % 360.0))
            stack[0:0] = [g[:gi + 1], g[gi + 1:]]
        else:
            out.append(g)
    if neutral:
        out.append(neutral)
    fams = []
    for g in out:
        cov = sum(c["cov"] for c in g)
        if cov <= 0:
            continue
        x = sum(c["cov"] * math.cos(math.radians(c["h"])) for c in g)
        y = sum(c["cov"] * math.sin(math.radians(c["h"])) for c in g)
        hue = math.degrees(math.atan2(y, x)) % 360.0
        meanC = sum(c["C"] * c["cov"] for c in g) / cov
        fams.append({"members": sorted(g, key=lambda c: c["L"]), "cov": cov, "hue": hue, "C": meanC,
                     "neutral": meanC < neutral_c, "Lmin": min(c["L"] for c in g), "Lmax": max(c["L"] for c in g)})
    fams.sort(key=lambda f: (-f["cov"], f["hue"]))
    return fams


def family_ramp(fam, steps):
    knots = []
    for m in fam["members"]:
        if knots and abs(m["L"] - knots[-1]["L"]) < 0.035:
            k = knots[-1]
            t = k["cov"] + m["cov"]
            k["lab"] = tuple((k["lab"][i] * k["cov"] + m["lab"][i] * m["cov"]) / t for i in range(3))
            k["L"] = k["lab"][0]
            k["cov"] = t
        else:
            knots.append({"lab": lab_t(m["lab"]), "L": m["L"], "cov": m["cov"]})
    if steps <= 1:
        t = sum(k["cov"] for k in knots)
        return [tuple(sum(k["lab"][i] * k["cov"] for k in knots) / t for i in range(3))]
    pad = 0.05 if steps > len(knots) else 0.0
    Lmin = clamp(knots[0]["L"] - pad, 0.10, 0.95)
    Lmax = clamp(knots[-1]["L"] + pad, Lmin + 0.04, 0.975)

    def ab_at(L):
        if L <= knots[0]["L"]:
            return knots[0]["lab"][1], knots[0]["lab"][2]
        if L >= knots[-1]["L"]:
            return knots[-1]["lab"][1], knots[-1]["lab"][2]
        for a, b in zip(knots, knots[1:]):
            if a["L"] <= L <= b["L"]:
                u = (L - a["L"]) / max(b["L"] - a["L"], 1e-9)
                return lerp(a["lab"][1], b["lab"][1], u), lerp(a["lab"][2], b["lab"][2], u)
        return knots[-1]["lab"][1], knots[-1]["lab"][2]

    out = []
    for i in range(steps):
        L = Lmin + (Lmax - Lmin) * i / (steps - 1)
        a, b = ab_at(L)
        fade = 1.0 if L <= 0.9 else max(0.4, 1.0 - (L - 0.9) * 6.0)
        out.append((L, a * fade, b * fade))
    # snap: the most important knots replace their nearest steps exactly (measured colours appear verbatim)
    used = set()
    for k in sorted(knots, key=lambda k: -k["cov"]):
        cand = [i for i in range(steps) if i not in used]
        if not cand:
            break
        i = min(cand, key=lambda i: abs(out[i][0] - k["L"]))
        out[i] = k["lab"]
        used.add(i)
    out.sort(key=lambda c: c[0])
    return out


class PaletteBuilder:
    def __init__(self):
        self.names, self.labs, self.hexes, self.src = [], [], [], []
        self.ramps = {}

    def add(self, name, lab, src):
        hx = C.oklab_to_hex(lab)
        for i, h in enumerate(self.hexes):
            if h == hx or C.ok_dist(C.hex_to_oklab(h), C.hex_to_oklab(hx)) < 0.012:
                return self.names[i]
        self.names.append(name)
        self.labs.append(C.hex_to_oklab(hx))
        self.hexes.append(hx)
        self.src.append(src)
        return name

    def nearest(self, lab, pool=None, Lrange=None):
        best, bd = None, 1e9
        for i, n in enumerate(self.names):
            if pool is not None and n not in pool:
                continue
            if Lrange and not (Lrange[0] <= self.labs[i][0] <= Lrange[1]):
                continue
            d = C.ok_dist(self.labs[i], lab)
            if d < bd:
                best, bd = n, d
        return best

    def lab(self, name):
        return self.labs[self.names.index(name)]

    def hex(self, name):
        return self.hexes[self.names.index(name)]


def unique_name(base, taken):
    if base not in taken:
        return base
    k = 2
    while "%s%d" % (base, k) in taken:
        k += 1
    return "%s%d" % (base, k)


# ================================================================== notes helpers

def first_in(seq, allowed, default=None):
    for m in seq:
        if m in allowed:
            return m
    return default


def surface_materials(notes):
    mats = notes["materials"]
    s = dict(notes.get("surfaces", {}))
    themes = notes.get("themes", [])
    s.setdefault("walls", first_in(mats, STRUCTURAL, "plaster"))
    flooring = FLOORING if notes["setting"] == "exterior" else [m for m in FLOORING if m not in OUTDOOR_GROUND]
    s.setdefault("floor", first_in([m for m in mats if m != s["walls"]] + [s["walls"]], flooring, s["walls"] if s["walls"] in FLOORING else "stone"))
    s.setdefault("ceiling", s["walls"])
    metal = first_in(mats, METALS, "chrome" if notes.get("finish") == "chrome" else None)
    if metal is None:
        metal = {"chrome": "chrome", "brushed": "brushed_metal", "iron": "iron", "rust": "rusted_iron",
                 "brass": "brass", "none": "brushed_metal"}.get(notes.get("metal_finish", "brushed"), "brushed_metal")
    s.setdefault("metal", metal)
    s.setdefault("trim", first_in(mats, METALS + ["timber", "polished_wood", "stone", "marble"], s["walls"]))
    s.setdefault("furniture", first_in(mats, FURNITURE, s["walls"] if s["walls"] in FURNITURE else "polished_wood"))
    s.setdefault("soft", first_in(mats, SOFT, "cloth"))
    g = first_in(mats, GROUND)
    if g is None:
        g = next((THEME_GROUND[t] for t in themes if t in THEME_GROUND), "dirt")
    s.setdefault("ground", g)
    s.setdefault("roof", first_in(mats, ROOF, s["walls"]))
    s.setdefault("nature", first_in(mats, NATURE, "foliage"))
    return s


# ================================================================== presets

def select_presets(lib, notes):
    sl = notes["shape_language"]
    themes = notes.get("themes", [])
    mats = notes["materials"]
    avoid = set(notes.get("avoid", []))
    avoid_tags = set()
    if "chrome" in avoid:
        avoid_tags.add("chrome")
    if "wood" in avoid:
        avoid_tags.update(["timber", "polished_wood"])
    if "foliage" in avoid:
        avoid_tags.add("foliage")
    surfaces = surface_materials(notes)
    cls_words = {"architecture": sl["architecture"], "openings": sl["openings"], "seating": sl["seating"],
                 "furniture": sl["furniture"], "props": sl["props"], "vehicles": sl["vehicles"], "nature": sl["nature"]}

    def score(e, words, bonus_tags=(), slot=None):
        tags = e["tags"]
        s = 0
        for i, w in enumerate(words[:3]):
            if w in tags:
                s += (3, 2, 1)[i]
        # nature pieces follow the world (themes, ground) more than shape words; themes are listed strongest
        # first, so the primary theme outweighs the rest (desert+village must pick the palm, not the oak)
        for ti, t in enumerate(themes):
            if t in tags:
                s += (4 if e["class"] == "nature" else 3) if ti == 0 else (2 if e["class"] == "nature" else 1)
        s += sum(1 for m in mats[:4] if m in tags)
        s += 3 * sum(1 for t in bonus_tags if t in tags)
        s -= 5 * sum(1 for t in avoid_tags if t in tags)
        if slot is not None and slot in e.get("slots", ()):
            s += SLOT_AFFINITY  # this preset is what a shipped pack (or a variant) binds to this slot's function
        return s

    chosen, scores = {}, {}
    for slot in sorted(lib["slots"]):
        cands = lib["slots"][slot]["candidates"]
        bonus = (surfaces["ground"],) if slot in ("ground", "weather", "tree", "rock", "water") else ()

        def key(eid):
            e = lib["entries"][eid]
            return (-score(e, cls_words[e["class"]], bonus, slot), 0 if slot in e.get("slots", ()) else 1, eid)

        best = sorted(cands, key=key)[0]
        chosen[slot] = best
        scores[slot] = -key(best)[0]
    defaults = {}
    for gid in sorted(lib["defaults"]):
        cands = lib["defaults"][gid]
        words = cls_words[lib["generator_class"][gid]]
        bonus = (surfaces["ground"],) if gid in ("terrain.patch", "fx.particles", "nature.tree", "nature.rock") else ()
        defaults[gid] = sorted(cands, key=lambda eid: (-score(lib["entries"][eid], words, bonus), eid))[0]
    return chosen, defaults, scores


def preset_slug(eid):
    src, gid, name = eid.split(":")
    pre = {"polar_pod": "pp", "forest_village": "fv", "variant": "v"}.get(src, src[:2])
    return "%s_%s" % (pre, name)


def role_usage(lib, chosen, defaults, layout_slots):
    usage = {}
    items = [(defaults["arch.room_shell"], 1.0)] if "arch.room_shell" in defaults else []
    for slot, eid in chosen.items():
        items.append((eid, 1.0 if slot in layout_slots else 0.25))
    for eid, w in items:
        e = lib["entries"][eid]
        p = e["params"]
        for role, area in e["role_area"].items():
            cls = None
            for k, v in sorted(p.items()):
                if v == role and (k.endswith("_role") or k == "role"):
                    if k == "role" or k == "frame_role":
                        cls = {"arch": "trim" if k == "frame_role" else ROLE_CLASS.get(role, "furniture"),
                               "furn": "furniture", "soft": "soft", "prop": "furniture",
                               "vehicle": "furniture", "nature": "ground", "terrain": "ground"}.get(e["generator"].split(".")[0])
                        if e["generator"] in ("arch.door", "arch.window") and k == "frame_role":
                            cls = "trim"
                        if e["generator"].startswith("arch.") and k == "role":
                            cls = ROLE_CLASS.get(role, "walls")
                    else:
                        cls = PARAM_CLASS.get(k)
                    if cls:
                        break
            if cls is None:
                cls = ROLE_CLASS.get(role, "furniture")
            usage.setdefault(role, {})
            usage[role][cls] = usage[role].get(cls, 0.0) + area * w * CLASS_WEIGHT.get(cls, 1.0)
    return usage


# ================================================================== main drafting

def pooled_stats(meas, notes):
    refs = meas["references"]
    nrefs = notes["references"]
    wsum = 0.0
    acc = {"L50": 0.0, "rms": 0.0, "chroma": 0.0, "smooth": 0.0, "flat": 0.0, "checker": 0.0, "edges": 0.0}
    sh, hi = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    shw = hiw = 0.0
    for r in refs:
        nr = nrefs[r["index"]]
        w = nr["weight"]
        if w <= 0:
            continue
        st = r["stats"]
        wsum += w
        acc["L50"] += w * st["L"][2]
        acc["rms"] += w * st["rms_contrast"]
        acc["chroma"] += w * st["chroma_mean"]
        for k in ("smooth", "flat", "checker", "edges"):
            acc[k] += w * st["texture"][k]
        if "lighting" in nr["use"] or "palette" in nr["use"]:
            for i in range(3):
                sh[i] += w * st["shadow"][i]
                hi[i] += w * st["highlight"][i]
            shw += w
            hiw += w
    wsum = wsum or 1.0
    out = {k: v / wsum for k, v in acc.items()}
    out["shadow"] = tuple(v / (shw or 1.0) for v in sh)
    out["highlight"] = tuple(v / (hiw or 1.0) for v in hi)
    out["rms_contrast"] = out["rms"]
    return out


def band_votes(meas, notes, setting_filter):
    """Per band (top/mid/bottom): summed share x weight per pooled cluster index, over refs of a setting."""
    votes = {"top": {}, "mid": {}, "bottom": {}}
    for r in meas["references"]:
        nr = notes["references"][r["index"]]
        if nr["setting"] not in setting_filter or nr["weight"] <= 0:
            continue
        for band in votes:
            for idx, share in r["band_clusters"][band]:
                votes[band][idx] = votes[band].get(idx, 0.0) + share * nr["weight"]
    return {b: (max(sorted(v), key=lambda i: v[i]) if v else None) for b, v in votes.items()}, votes


def draft(meas, notes, lib, pack_id, mode="albedo", accent_from_notes=True):
    """Returns dict(pack=..., decisions=..., warnings=[...], surfaces=...)."""
    warnings = []
    dec = {"mode": mode}
    clusters = meas["pooled"]["clusters"]
    st = pooled_stats(meas, notes)
    has_int = any(r["setting"] in ("interior", "mixed") and r["weight"] > 0 for r in notes["references"])
    has_ext = any(r["setting"] in ("exterior", "mixed") and r["weight"] > 0 for r in notes["references"])
    int_bands, _ = band_votes(meas, notes, ("interior", "mixed"))
    ext_bands, _ = band_votes(meas, notes, ("exterior", "mixed"))
    cl_lab = [lab_t(c["lab"]) for c in clusters]

    def cl(idx):
        return cl_lab[idx] if idx is not None else None

    # ---- light rig (needs ground/sky luminance)
    ground_idx = ext_bands["bottom"] if has_ext else int_bands["bottom"]
    sky_idx = ext_bands["top"] if has_ext else None
    st["ground_L"] = cl(ground_idx)[0] if ground_idx is not None else 0.4
    st["sky_L"] = cl(sky_idx)[0] if sky_idx is not None else 0.3
    rig, ci = light_rig(notes, st)
    n_light = LIGHT_STEPS[["low", "medium", "high"][ci]]
    if notes["detail"]["texture_detail"] == "flat":
        n_light = max(5, n_light - 2)
    curve = light_curve(st["shadow"], st["highlight"], n_light)
    T = surface_t(rig)
    dec["light"] = {"steps": n_light, "contrast_index": ci, "t": {k: r4(v) for k, v in T.items()},
                    "shadow": [r4(x) for x in st["shadow"]], "highlight": [r4(x) for x in st["highlight"]]}

    # ---- per-cluster albedo estimate (inverse lighting) or measured colour
    band_t_int = (T["ceiling"], T["walls"], T["floor"])
    band_t_ext = (1.0, T["walls"], T["ground"])
    ext_share = {}
    for r in meas["references"]:
        nr = notes["references"][r["index"]]
        for idx, share in r["cluster_share"]:
            e = ext_share.setdefault(idx, [0.0, 0.0])
            e[0 if nr["setting"] == "exterior" else 1] += share * max(nr["weight"], 1e-6)
    cols = []
    for i, c in enumerate(clusters):
        lab = cl_lab[i]
        if mode == "albedo":
            es = ext_share.get(i, [0.0, 1.0])
            fe = es[0] / max(es[0] + es[1], 1e-9)
            bt = [lerp(band_t_int[k], band_t_ext[k], fe) for k in range(3)]
            t = sum(bt[k] * c["bands"][k] for k in range(3))
            emissive_like = c["chroma"] > 0.12 and lab[0] > 0.75 and c["coverage"] < 0.02
            if not emissive_like:
                lab = albedo_of(lab, light_at(curve, t))
        L, Cc, h = oklch_of(lab)
        cols.append({"lab": lab, "L": L, "C": Cc, "h": h, "cov": c["coverage"], "idx": i, "bands": c["bands"],
                     "images": c.get("images", [])})

    # ---- agent-marked regions (notes.references[].regions): measured robust colours per surface, inverse-lit
    # with that surface's own bake level; injected as pseudo-clusters so the hue families contain them
    region_light = {"walls": T["walls"], "floor": T["floor"], "ceiling": T["ceiling"], "ground": T["ground"],
                    "furniture": T["object"], "soft": T["object"], "metal": T["object"], "accent": T["object"],
                    "foliage": T["object"], "water": T["ground"], "sky": None, "view": None}
    region_t = {}
    for key in sorted(region_light):
        acc, wsum = [0.0, 0.0, 0.0], 0.0
        for r in meas["references"]:
            nr = notes["references"][r["index"]]
            reg = (r["stats"].get("regions") or {}).get(key)
            if reg is None or nr["weight"] <= 0:
                continue
            lab = lab_t(reg["lab_chroma"] if key in ("soft", "accent", "foliage") and "lab_chroma" in reg else reg["lab"])
            if mode == "albedo" and region_light[key] is not None:
                lab = albedo_of(lab, light_at(curve, region_light[key]))
            w = nr["weight"] * min(1.0, reg["px"] / 40.0)
            acc = [a + w * x for a, x in zip(acc, lab)]
            wsum += w
        if wsum > 0:
            region_t[key] = tuple(a / wsum for a in acc)
    dec["regions"] = {k: C.oklab_to_hex(v) for k, v in sorted(region_t.items())}
    for k, (key, lab) in enumerate(sorted(region_t.items())):
        L, Cc, h = oklch_of(lab)
        cols.append({"lab": lab, "L": L, "C": Cc, "h": h, "cov": 0.03, "idx": 1000 + k, "bands": [0.0, 1.0, 0.0],
                     "images": [], "region": key})

    # ---- palette
    pb = PaletteBuilder()
    taken = set()
    fams = hue_families(cols)
    fams = [f for f in fams if f["cov"] >= 0.004 or f["C"] >= 0.10][:8]
    budget_total = 32
    # void + n_light light steps + 1 spare: when the top light step merges into a measured near-white, a separate
    # 'white' is appended (r14: that extra entry filled the palette and the interior fog lost its colour)
    reserved = 1 + n_light + 1
    # keep 2 slots for the fog colours plus one per requested accent (r12: an accent took the last slot and the
    # interior fog fell back to an unrelated nearest colour, 3.0 -> 12.7 dE00)
    budget = budget_total - reserved - 2 - len(notes["palette"].get("accent_hues", [])) if accent_from_notes else \
        budget_total - reserved - 2
    weights = [math.sqrt(f["cov"]) * (0.5 + (f["Lmax"] - f["Lmin"]) * 2.0) for f in fams]
    ws = sum(weights) or 1.0
    steps = []
    for f, w in zip(fams, weights):
        mn = 3 if f["cov"] >= 0.05 else 2
        steps.append(int(clamp(round(budget * w / ws), mn, 10)))
    while sum(steps) > budget and any(s > 2 for s in steps):
        j = max(range(len(steps)), key=lambda i: (steps[i] / max(weights[i], 1e-9), i))
        steps[j] -= 1
    while sum(steps) > budget and fams:
        fams.pop()
        steps.pop()
    void_lab = (clamp(min(c["L"] for c in cols) - 0.05, 0.06, 0.14), st["shadow"][1] * 0.35, st["shadow"][2] * 0.35)
    pb.add("void", void_lab, "derived:shadow")
    taken.add("void")
    fam_ramps = []
    for f, n in zip(fams, steps):
        base = "grey" if f["neutral"] else C.hue_word(f["hue"])
        nm = unique_name(base, taken)
        taken.add(nm)
        names = []
        for j, lab in enumerate(family_ramp(f, n)):
            got = pb.add("%s_%d" % (nm, j), lab, "measured" if any(C.ok_dist(lab, m["lab"]) < 1e-6 for m in f["members"]) else "interpolated")
            if got not in names:
                names.append(got)
        fam_ramps.append({"name": nm, "names": names, "cov": f["cov"], "hue": f["hue"], "neutral": f["neutral"], "C": f["C"]})
    # light ramp (shade_*) ending in white
    light_names = []
    for j, lab in enumerate(curve):
        nm = "white" if j == len(curve) - 1 else "shade_%d" % j
        got = pb.add(nm, lab, "derived:light_curve")
        if got not in light_names and (not light_names or pb.lab(got)[0] > pb.lab(light_names[-1])[0] + 0.005):
            light_names.append(got)
    if light_names[-1] != "white" and "white" not in pb.names:
        got = pb.add("white", (0.995, 0.0, 0.0), "derived:white")  # may merge into a measured near-white
        if got not in light_names:
            light_names.append(got)
    # strictly increasing on the FINAL hex values (palette merging/quantisation can collapse steps)
    mono = []
    for n in light_names:
        Ln = C.hex_to_oklab(pb.hex(n))[0]
        if not mono or Ln > C.hex_to_oklab(pb.hex(mono[-1]))[0] + 0.01:
            mono.append(n)
        elif n == light_names[-1]:
            mono[-1] = n  # keep the brightest step as the ramp's top
    light_names = mono
    if len(light_names) < 3:
        warnings.append("light ramp collapsed to %d steps; padded" % len(light_names))
        for L in (0.35, 0.65):
            light_names.append(pb.add("shade_pad_%d" % int(L * 100), (L, 0.0, 0.0), "derived:pad"))
        light_names = sorted(dict.fromkeys(light_names), key=lambda n: pb.lab(n)[0])
    # accents requested in notes but absent from the measured palette (agent decision, not pixels)
    accents = []
    if accent_from_notes:
        for hw in notes["palette"]["accent_hues"]:
            hc = C.NOTE_HUES[hw]
            have = [n for n in pb.names if pb.lab(n)[0] > 0.45 and C.oklch(pb.lab(n))[1] > 0.08
                    and C.hue_diff(C.oklch(pb.lab(n))[2], hc) < 30]
            if have:
                accents.append(max(have, key=lambda n: C.oklch(pb.lab(n))[1]))
            elif len(pb.names) < budget_total:
                Lc = 0.62 if hw == "brown" else 0.78
                cc = 0.08 if hw == "brown" else 0.15
                nm = unique_name("accent_%s" % hw, set(pb.names))
                accents.append(pb.add(nm, C.from_oklch(Lc, cc, hc), "notes:accent_hue"))
                warnings.append("accent hue %r not measured in the references; added from the notes" % hw)
    dec["families"] = [{"name": f["name"], "steps": len(f["names"]), "coverage": r4(f["cov"]), "hue": r4(f["hue"]),
                        "neutral": f["neutral"]} for f in fam_ramps]

    # ---- surface targets (OKLab, albedo space)
    def cl_alb(idx):
        if idx is None:
            return None
        for c in cols:
            if c["idx"] == idx:
                return c["lab"]
        return None

    targets = {}
    if has_int:
        targets["ceiling"] = cl_alb(int_bands["top"])
        targets["walls"] = cl_alb(int_bands["mid"])
        targets["floor"] = cl_alb(int_bands["bottom"])
    if has_ext:
        targets["sky_measured"] = cl(ext_bands["top"])  # sky is full-bright: measured colour IS the texture colour
        targets["ground"] = cl_alb(ext_bands["bottom"])
        targets.setdefault("walls", cl_alb(ext_bands["mid"]))
    if targets.get("floor") is None:
        targets["floor"] = targets.get("ground") or cols[0]["lab"]
    if targets.get("walls") is None:
        targets["walls"] = cols[0]["lab"]
    if targets.get("ceiling") is None:
        w = targets["walls"]
        targets["ceiling"] = (min(0.95, w[0] + 0.06), w[1], w[2])
    if targets.get("ground") is None:
        targets["ground"] = targets["floor"]
    for key in ("walls", "floor", "ceiling", "ground"):
        if key in region_t:
            targets[key] = region_t[key]
    if "sky" in region_t:
        targets["sky_measured"] = region_t["sky"]
    structural = [targets["walls"], targets["floor"], targets["ceiling"]]
    # object colours: not a structural surface, not mostly in the top band of interior views (ceiling, windows,
    # sky cards), not near-black (shadows, voids, glass) -- unless nothing else is left
    rest_all = sorted([c for c in cols if all(C.ok_dist(c["lab"], s) > 0.05 for s in structural)],
                      key=lambda c: (-c["cov"], c["idx"]))
    rest = [c for c in rest_all if c["L"] >= 0.3 and not (has_int and c["bands"][0] > 0.6)] or rest_all
    if has_int:
        # furniture, soft goods and metal live indoors: prefer colours seen in interior references
        int_idx = {r["index"] for r in notes["references"] if r["setting"] in ("interior", "mixed") and r["weight"] > 0}
        rest_in = [c for c in rest if set(c["images"]) & int_idx]
        rest = rest_in + [c for c in rest if c not in rest_in]
    surf = surface_materials(notes)
    # A ceiling is rarely in view; the top band is usually upper wall. When the notes give the ceiling the
    # same material as the floor or walls, it takes that surface's colour instead of the top-band guess.
    if "ceiling" in region_t:
        pass
    elif surf["ceiling"] == surf["floor"] and surf["ceiling"] != surf["walls"]:
        targets["ceiling"] = targets["floor"]
    elif surf["ceiling"] == surf["walls"]:
        w = targets["walls"]
        targets["ceiling"] = (min(0.95, w[0] + 0.04), w[1], w[2])

    def pick(pred, fallback):
        for c in rest:
            if pred(c):
                return c["lab"]
        return fallback

    fm = surf["furniture"]
    if fm == surf["floor"] or fm == surf["walls"]:
        # same material as a structural surface -> same colour family (the notes say so)
        base = targets["floor"] if fm == surf["floor"] else targets["walls"]
        targets["furniture"] = (clamp(base[0] + 0.04, 0.0, 0.95), base[1], base[2])
    elif fm in ("glossy_plastic", "marble", "crystal"):
        targets["furniture"] = pick(lambda c: c["L"] > 0.65, targets["walls"])
    elif fm in MATERIAL_HUE:
        lo, hi = MATERIAL_HUE[fm]
        targets["furniture"] = pick(lambda c: lo <= c["h"] <= hi and c["C"] > 0.03, pick(lambda c: True, targets["walls"]))
    elif fm in METALS:
        targets["furniture"] = pick(lambda c: c["C"] < 0.05 and c["L"] > 0.5, targets["walls"])
    else:
        targets["furniture"] = pick(lambda c: True, targets["walls"])
    targets["soft"] = pick(lambda c: c["C"] >= 0.05 and C.ok_dist(c["lab"], targets["furniture"]) > 0.05,
                           pick(lambda c: C.ok_dist(c["lab"], targets["furniture"]) > 0.05, targets["furniture"]))
    if surf["metal"] in ("iron", "rusted_iron"):
        targets["metal"] = pick(lambda c: c["C"] < 0.06 and 0.3 < c["L"] < 0.6, (0.45, 0.0, 0.0))
    else:
        targets["metal"] = pick(lambda c: c["C"] < 0.06 and c["L"] > 0.6, (0.78, st["highlight"][1] * 0.5, st["highlight"][2] * 0.5))
    accent_c = sorted(cols, key=lambda c: (-(c["C"] * (1.0 - min(c["cov"] * 5, 0.9))), c["idx"]))
    targets["accent"] = accent_c[0]["lab"] if accent_c else targets["soft"]
    for key in ("furniture", "soft", "metal", "accent"):
        if key in region_t:
            targets[key] = region_t[key]
    warm = [c for c in cols if 20 <= c["h"] <= 95 and c["C"] > 0.06 and c["L"] > 0.55]
    targets["warm_light"] = max(warm, key=lambda c: (c["L"] * c["C"], -c["idx"]))["lab"] if warm else None
    if targets["warm_light"] is None:
        warm_acc = [n for n in accents if 20 <= C.oklch(pb.lab(n))[2] <= 95]
        targets["warm_light"] = pb.lab(warm_acc[0]) if warm_acc else C.hex_to_oklab(pb.hex(light_names[-2]))
    targets["glass"] = (clamp(void_lab[0] + 0.18, 0.15, 0.4), targets["walls"][1] * 0.6, targets["walls"][2] * 0.6)
    if "view" in region_t:  # windows read as the view behind them; tint x env must land on the measured colour
        v = region_t["view"]
        targets["glass"] = (clamp(v[0] + 0.3, 0.45, 0.85), v[1] * 1.2, v[2] * 1.2)
    targets["roof"] = targets["walls"] if surf["roof"] == surf["walls"] else pick(
        lambda c: c["L"] < targets["walls"][0], targets["walls"])
    targets["stone"] = targets["walls"]
    targets["wood"] = targets["floor"] if surf["floor"] in ("timber", "polished_wood") else targets["furniture"]
    targets["paper"] = (0.86, st["highlight"][1] * 0.6, st["highlight"][2] * 0.6)
    targets["rope"] = targets["furniture"]
    targets["trim"] = targets["metal"] if surf["trim"] in METALS else (
        targets["wood"] if surf["trim"] in ("timber", "polished_wood") else targets["walls"])
    targets["nature"] = targets.get("ground")
    targets["emissive"] = targets["warm_light"]
    dec["targets"] = {k: C.oklab_to_hex(v) for k, v in sorted(targets.items()) if v is not None}
    dec["surfaces"] = surf

    # ---- presets
    chosen, defaults, pscores = select_presets(lib, notes)
    layout_slots = {"door_main", "window_main", "window_side", "seat_lounge", "seat_chair", "table_low", "rug",
                    "lamp_floor", "console", "shelf", "cat_bed", "plant", "container"}
    usage = role_usage(lib, chosen, defaults, layout_slots)
    dec["presets"] = {s: {"entry": e, "score": pscores[s]} for s, e in sorted(chosen.items())}
    dec["defaults"] = defaults

    # ---- helpers to make ramps from the palette
    fam_of = {}
    for f in fam_ramps:
        for n in f["names"]:
            fam_of.setdefault(n, f)

    def family_by_hue(lo, hi, minC=0.03):
        best = None
        for f in fam_ramps:
            if f["neutral"] or f["C"] < minC:
                continue
            if lo <= f["hue"] <= hi and (best is None or f["cov"] > best["cov"]):
                best = f
        return best

    def ramp_around(lab, n, below, fam=None):
        if fam is None:
            nm = pb.nearest(lab, pool=[x for f in fam_ramps for x in f["names"]] or None)
            fam = fam_of.get(nm)
        if fam is None:
            seq = sorted(pb.names, key=lambda x: pb.lab(x)[0])
        else:
            seq = fam["names"]
        seq = sorted(seq, key=lambda x: pb.lab(x)[0])
        nm = min(seq, key=lambda x: C.ok_dist(pb.lab(x), lab))
        i = seq.index(nm)
        n = max(1, min(n, len(seq)))
        s = clamp(int(math.floor(i - below + 0.5)), 0, len(seq) - n)  # below may be fractional (calibrated)
        out = seq[int(s):int(s) + n]
        # a sparse family can span dark leather to pale accent; keep the ramp near the target's lightness
        out = [x for x in out if abs(pb.lab(x)[0] - lab[0]) <= 0.3] or [nm]
        if len(out) < 2 and n >= 2:
            # pad with the nearest-lightness neighbours from the whole palette
            extra = sorted((x for x in pb.names if x not in out), key=lambda x: abs(pb.lab(x)[0] - pb.lab(out[0])[0]) + C.ok_dist(pb.lab(x), lab))
            out = sorted(out + extra[:n - len(out)], key=lambda x: pb.lab(x)[0])
        return out

    mats_lib = lib["materials"]["materials"]
    overrides = lib["materials"]["role_gen_overrides"]
    driving = {}
    for role in CORE_ROLES:
        u = usage.get(role)
        driving[role] = max(sorted(u), key=lambda k: u[k]) if u else ROLE_CLASS[role]
    foliage_fam = family_by_hue(100, 170, 0.04)
    dec["role_driving_class"] = driving

    def material_word(role, cls):
        # named roles keep their material identity (both shipped packs do: stone=blocks, leather=leather,
        # knit=knit, ...); the class that uses the role most only steers its colour target
        if role in ROLE_IDENTITY:
            return ROLE_IDENTITY[role]
        if role == "quilt" and "quilted_vinyl" in notes["materials"]:
            return "quilted_vinyl"
        if cls in ("walls", "floor", "ceiling", "trim", "furniture", "soft", "metal", "roof"):
            w = surf[cls]
        elif cls == "stone":
            w = "stone"
        elif cls == "wood":
            w = surf["floor"] if surf["floor"] in ("timber", "polished_wood") else (
                surf["furniture"] if surf["furniture"] in ("timber", "polished_wood") else "polished_wood")
        elif cls == "glass":
            w = "glass"
        elif cls == "paper":
            w = "paper"
        elif cls == "rope":
            w = "rope"
        elif cls == "ground":
            w = role if role in ("grass", "snow", "sand", "rock", "dirt", "ice", "water") else surf["ground"]
            if role == "grass" and foliage_fam is None and surf["ground"] in ("snow", "sand", "dirt", "rock", "ice", "mud"):
                w = surf["ground"]
        elif cls == "nature":
            w = {"bark": "polished_wood", "foliage": surf["nature"], "cap": surf["ground"] if surf["ground"] in ("snow", "ice") else surf["nature"],
                 "flower": surf["nature"]}.get(role, surf["nature"])
            if role == "foliage" and foliage_fam is None and surf["ground"] in ("snow", "ice"):
                w = "snow"
        else:
            w = surf.get(cls, "plaster")
        if role in ("wood", "body", "body_alt") and w in ("plaster", "adobe", "concrete", "snow", "ice", "sand"):
            w = surf["furniture"]
        return w

    def target_for(role, cls, word):
        if role in ("foliage", "flower") and "foliage" in region_t and word not in ("snow", "ice"):
            return region_t["foliage"], None
        if role == "water" and "water" in region_t:
            return region_t["water"], None
        if word in ("snow", "ice"):
            lab = pb.lab(light_names[-2]) if word == "snow" else (0.86, st["shadow"][1] * 0.4, st["shadow"][2] * 0.4)
            return lab, None
        if cls in ("ground", "nature") and word in MATERIAL_HUE:
            lo, hi = MATERIAL_HUE[word]
            f = family_by_hue(lo, hi)
            if f is not None:
                mid = f["names"][len(f["names"]) // 2]
                return pb.lab(mid), f
        if role == "bark":
            f = family_by_hue(*MATERIAL_HUE["bark"])
            if f is not None:
                return pb.lab(f["names"][max(0, len(f["names"]) // 3)]), f
        if word in MATERIAL_HUE and cls in ("walls", "floor", "furniture", "trim", "wood", "roof", "soft") \
                and cls not in region_t:  # an agent-marked region is measured truth: no hue prior over it
            lo, hi = MATERIAL_HUE[word]
            t = targets.get(cls) or targets.get("walls")
            Lt, Ct, ht = C.oklch(t)
            if not (lo <= ht <= hi) or Ct < 0.03:
                f = family_by_hue(lo, hi)
                if f is not None:
                    best = min((pb.lab(n) for n in f["names"]), key=lambda x: abs(x[0] - Lt))
                    if abs(best[0] - Lt) <= 0.2:  # the prior may move hue, never lightness (ocean floor finding)
                        return best, f
        key = {"wood": "wood", "stone": "stone", "roof": "roof", "glass": "glass", "paper": "paper",
               "rope": "rope", "emissive": "emissive", "ground": "ground", "nature": "nature"}.get(cls, cls)
        return targets.get(key) or targets["walls"], None

    materials = {}
    env_needed = {}
    for role in CORE_ROLES:
        cls = driving[role]
        if role in ("face",):
            materials[role] = {"kind": "face_atlas"}
            continue
        if role in ("headwear", "costume", "coat"):
            materials[role] = {"kind": "baked_unlit"}
            continue
        if role == "opening":
            materials[role] = {"kind": "baked_unlit", "tile_m": 1.0, "texture": {"gen": "flat", "size": 8, "ramp": ["void"]}}
            continue
        if role == "skin":
            materials[role] = {"kind": "baked_unlit", "tile_m": 1.0,
                               "texture": {"gen": "flat", "size": 8, "ramp": [pb.nearest(targets["warm_light"])]}}
            continue
        if role in ("view", "sky"):
            continue  # scene cards below
        if role == "particle":
            continue
        if role in ("glass", "orb", "band"):
            tl = targets["glass"] if role != "orb" else (targets["glass"][0] + 0.08, targets["glass"][1] * 1.5, targets["glass"][2] * 1.5)
            materials[role] = {"kind": "glass_env", "tint": pb.nearest(tl), "env": "env_glass"}
            env_needed["env_glass"] = True
            continue
        if role in ("screen", "light", "fire"):
            if role == "screen":
                acc = targets["accent"]
                cool = [n for n in pb.names if C.oklch(pb.lab(n))[1] > 0.06 and 180 <= C.oklch(pb.lab(n))[2] <= 300]
                hi_n = max(cool, key=lambda n: pb.lab(n)[0]) if cool else pb.nearest(acc)
                ramp = [light_names[1], pb.nearest((0.4, acc[1] * 0.5, acc[2] * 0.5)), pb.nearest(acc), hi_n]
                tex = {"gen": "screen", "size": 32, "ramp": list(dict.fromkeys(ramp)), "dither": False}
            elif role == "light":
                wl = targets["warm_light"] if "lamps" in notes["lighting"]["light_sources"] or "lanterns" in notes["lighting"]["light_sources"] else pb.lab(light_names[-3])
                ramp = [pb.nearest((wl[0] - 0.12, wl[1], wl[2])), pb.nearest(wl), light_names[-2], light_names[-1]]
                tex = {"gen": "glow", "size": 16, "ramp": list(dict.fromkeys(ramp))}
            else:
                wl = targets["warm_light"]
                emb = pb.nearest((max(0.45, wl[0] - 0.25), wl[1] * 1.3, wl[2] * 1.3))
                ramp = [emb, pb.nearest((wl[0] - 0.1, wl[1], wl[2])), pb.nearest(wl), light_names[-1]]
                tex = {"gen": "fire", "size": 16, "ramp": list(dict.fromkeys(ramp))}
            if len(tex["ramp"]) < 2:
                tex["ramp"] = [light_names[-3], light_names[-1]]
            materials[role] = {"kind": "emissive", "texture": tex}
            continue
        word = material_word(role, cls)
        tpl = mats_lib.get(word) or mats_lib["plaster"]
        if tpl["kind"] in ("chrome_env",):
            env = tpl["env"]
            t = targets["metal"]
            if word == "brass":
                wf = family_by_hue(*MATERIAL_HUE["brass"])
                t = pb.lab(wf["names"][-1]) if wf else t
            materials[role] = {"kind": "chrome_env", "tint": pb.nearest(t), "env": env}
            env_needed[env] = True
            continue
        if tpl["kind"] == "glass_env":
            materials[role] = {"kind": "glass_env", "tint": pb.nearest(targets["glass"]), "env": "env_glass"}
            env_needed["env_glass"] = True
            continue
        gen, extra = tpl["gen"], dict(tpl.get("extra", {}))
        ov = overrides.get(role, {})
        if word in ov or "*" in ov:
            g2, ex2 = ov.get(word) or ov["*"]
            gen, extra = g2, dict(ex2)
        lab, fam = target_for(role, cls, word)
        if role == "wall_alt":
            lab = (lab[0] - 0.08, lab[1], lab[2])
        if role in ("trim", "frame", "rail", "post") and tpl["kind"] == "baked_unlit" and cls == "trim" and word == surf["walls"]:
            lab = (lab[0] - 0.05, lab[1], lab[2])
        n, below = tpl["ramp"]["steps"], tpl["ramp"]["below"]
        cal = lib.get("gen_calibration", {}).get("%s/%d" % (gen, n)) if lib.get("use_gen_calibration", True) else None
        if cal and "mean_pos" in cal:
            # place the target where this generator's texture actually averages (refpack/calibrate_gens.py)
            below = cal["mean_pos"]
        if role == "book":
            spines = [light_names[1]] + [f["names"][len(f["names"]) // 2] for f in fam_ramps[:4]]
            ramp = list(dict.fromkeys(spines))
        else:
            ramp = ramp_around(lab, n, below, fam)
        tex = {"gen": gen, "size": tpl.get("size", 32), "ramp": ramp}
        tex.update(extra)
        m = {"kind": tpl["kind"], "tile_m": tpl.get("tile_m", 1.0), "texture": tex}
        if tpl["kind"] == "water":
            m["scroll"] = list(tpl.get("scroll", [0.03, 0.01]))
        materials[role] = m
    dith = notes["detail"]["dither"]
    if dith == "no" or (dith == "auto" and st["flat"] > 0.6 and st["smooth"] < 0.15):
        for role, m in materials.items():
            if "texture" in m and m["texture"].get("gen") not in ("screen",):
                m["texture"]["dither"] = False
        dec["dither"] = False
    else:
        dec["dither"] = True

    # ---- scene cards (window view + sky backdrop)
    tod = notes["time_of_day"]
    night = tod in ("night",) or (tod in ("dusk",) and st["L50"] < 0.4)
    underground = any(t in ("cave", "mine") for t in notes.get("themes", [])) and not has_ext
    if targets.get("sky_measured") is not None:
        sky_lab = targets["sky_measured"]
    elif underground:  # no sky underground: the 'sky' card is a dark rock vault, not a light accent
        w = targets["walls"]
        sky_lab = (clamp(void_lab[0] + 0.06, 0.1, 0.25), w[1] * 0.6, w[2] * 0.6)
    elif night:
        sky_lab = (clamp(void_lab[0] + 0.1, 0.12, 0.3), st["shadow"][1] * 0.8, st["shadow"][2] * 0.8)
    else:
        cool = family_by_hue(200, 290, 0.03)
        sky_lab = pb.lab(cool["names"][-2]) if cool and len(cool["names"]) > 1 else (0.8, st["highlight"][1], st["highlight"][2] - 0.04)
    def sky_ramp_for(lab):
        n0 = pb.nearest(lab)
        f0 = fam_of.get(n0)
        seq = sorted(f0["names"] if f0 else pb.names, key=lambda x: pb.lab(x)[0])
        i = seq.index(n0) if n0 in seq else 0
        if night:
            ramp = [seq[min(len(seq) - 1, i + 1)], n0] + [x for x in [pb.nearest((max(0.08, lab[0] - 0.06), lab[1], lab[2])), "void"] if x]
        else:
            ramp = [seq[min(len(seq) - 1, i + 2)], seq[min(len(seq) - 1, i + 1)], n0, seq[max(0, i - 1)]]
        ramp = list(dict.fromkeys(ramp))
        return ramp if len(ramp) >= 2 else [light_names[-2], light_names[-4]]

    sky_ramp = sky_ramp_for(sky_lab)
    view_sky_ramp = sky_ramp_for(region_t["view"]) if "view" in region_t else sky_ramp
    themes = notes.get("themes", [])
    layers_spec = next((SCENE_LAYERS[t] for t in themes if t in SCENE_LAYERS), [("hills", 0.3, 0.12, 5)])
    wall_seq = ramp_around(targets["walls"], 3, 1)
    lights_on = night or "windows" in notes["lighting"]["light_sources"]
    layers = []
    for k, (kind, base, height, count) in enumerate(layers_spec):
        lay = {"kind": kind, "base": base, "height": height, "count": count}
        if k == 0:
            lay["ramp"] = wall_seq
            if lights_on and kind in ("domes", "roofs", "huts"):
                lay["lights"] = {"color": pb.nearest(targets["warm_light"]), "count": count}
        else:
            lay["color"] = pb.nearest((max(0.12, targets["walls"][0] - 0.35), targets["walls"][1], targets["walls"][2]))
        layers.append(lay)
    ground_ramp = ramp_around(targets["ground"], 4, 2)
    view = {"gen": "scene", "width": 128, "height": 64, "sky": view_sky_ramp, "layers": layers,
            "ground": {"ramp": ground_ramp, "height": 0.3}}
    if night:
        view["stars"] = {"count": 70, "color": light_names[-1], "min_v": 0.5}
    materials["view"] = {"kind": "view_plane", "texture": view}
    sky_tex = {"gen": "scene", "width": 128, "height": 64, "sky": sky_ramp,
               "layers": [{"kind": "mountains", "base": 0.18, "height": 0.12, "count": 7,
                           "color": pb.nearest((max(0.15, sky_lab[0] - 0.1), sky_lab[1], sky_lab[2]))}],
               "ground": {"ramp": ground_ramp[:3], "height": 0.18}}
    if night:
        sky_tex["stars"] = {"count": 90, "color": light_names[-1], "min_v": 0.35}
    materials["sky"] = {"kind": "view_plane", "texture": sky_tex}
    weather_eid = chosen.get("weather")
    shape = lib["entries"][weather_eid]["params"].get("shape", "disc") if weather_eid else "disc"
    alpha = {"flake": "flake", "leaf": "leaf", "puff": "puff", "spark": "spark", "disc": "disc"}.get(shape, "disc")
    pcol = light_names[-1] if shape in ("flake", "disc", "puff") else pb.nearest(targets["accent"] if shape == "spark" else targets.get("nature") or targets["soft"])
    materials["particle"] = {"kind": "card_alpha", "texture": {"gen": "flat", "size": 8, "ramp": [pcol], "alpha": alpha}}

    # ---- fog
    dn = FOG_DENSITY[notes["fog"]["density"]]
    ext_haze = [r["stats"]["haze"]["density"] for r in meas["references"]
                if notes["references"][r["index"]]["setting"] == "exterior" and "fog" in notes["references"][r["index"]]["use"]]
    if ext_haze:
        dm = sum(ext_haze) / len(ext_haze)
        d_ext = clamp(0.75 * dn + 0.25 * dm, 0.0, 0.95)
    else:
        d_ext = dn
    ref_d = [FOG_DENSITY[r["fog_density"]] for r in notes["references"] if r["setting"] != "exterior" and r["weight"] > 0]
    d_int = sum(ref_d) / len(ref_d) if ref_d else dn
    end_ext = round(120.0 - 95.0 * d_ext, 1)
    start_ext = round(end_ext * (0.25 - 0.1 * d_ext), 1)
    end_int = round(30.0 - 12.0 * d_int, 1)
    start_int = 6.0
    # Fog colour rules (lane-kits fog is a linear blend toward one colour by distance and the background is
    # that colour, so the tint is mostly hidden inside blends; a dark-channel 'airlight' picks the brightest
    # pixels and fails at night). Day/dusk/dawn: the sky band just above the horizon (what distant geometry
    # fades into). Night: a dark tone of the upper sky (little scattered light). Interior: a dark tone of the
    # most saturated structural surface.
    ext_refs = [r for r in meas["references"] if notes["references"][r["index"]]["setting"] == "exterior"]
    tod = notes["time_of_day"]
    if ext_refs:
        def avg(key):
            return tuple(sum(r["stats"]["vertical"][key][i] for r in ext_refs) / len(ext_refs) for i in range(3))
        if tod == "night":
            t10, top = avg("top10"), avg("top")
            Lt, Ct, ht = C.oklch(top)
            fe = C.from_oklch(clamp(min(t10[0], top[0]) * 0.75, 0.18, 0.40), clamp(Ct, 0.0, 0.16), ht)
        else:
            # haze lightness between the brightest scene light (dark-channel airlight) and the horizon sky;
            # hue and chroma from the horizon sky (the airlight often lands on a sunlit wall, not the sky)
            hz = avg("horizon")
            air = tuple(sum(r["stats"]["haze"]["airlight"][i] for r in ext_refs) / len(ext_refs) for i in range(3))
            Lh, Ch, hh = C.oklch(hz)
            fe = C.from_oklch(0.5 * (air[0] + Lh), Ch, hh)
    else:
        fe = (clamp(st["shadow"][0] * 0.75, 0.2, 0.5), st["shadow"][1], st["shadow"][2])
    sat = max((targets["walls"], targets["floor"]), key=lambda t: C.oklch(t)[1])
    Ls, Cs, hs = C.oklch(sat)
    fi = C.from_oklch(0.33, clamp(Cs * 0.9, 0.0, 0.14), hs) if Cs >= 0.02 else (0.3, st["shadow"][1], st["shadow"][2])
    dec["fog_rule"] = {"exterior": ("night:top_sky_dark" if tod == "night" else "day:airlight_L+horizon_hue") if ext_refs else "shadow",
                       "interior": "dark_saturated_structure"}
    tint = notes["fog"]["tint"]
    if tint not in ("none", "grey", "white", "black") and tint in C.NOTE_HUES:
        for lab_ in (fe, fi):
            pass
        hc = C.NOTE_HUES[tint]
        Lfe, Cfe, hfe = C.oklch(fe)
        if C.hue_diff(hfe, hc) > 45:
            fe = C.from_oklch(Lfe, max(Cfe, 0.05), hc)
    fog_ext = pb.nearest(fe)
    if C.ok_dist(pb.lab(fog_ext), fe) > 0.04 and len(pb.names) < budget_total:
        fog_ext = pb.add("fog_ext", fe, "measured:haze")
    fog_int = pb.nearest(fi)
    if C.ok_dist(pb.lab(fog_int), fi) > 0.04 and len(pb.names) < budget_total:
        fog_int = pb.add("fog_int", fi, "measured:shadow")
    fog = {"color": fog_ext, "start": start_ext, "end": end_ext,
           "interior": {"color": fog_int, "start": start_int, "end": end_int}}
    dec["fog"] = {"density_notes": dn, "density_ext": r4(d_ext), "density_int": r4(d_int),
                  "measured_haze": [r4(x) for x in ext_haze], "ext_target": C.oklab_to_hex(fe), "int_target": C.oklab_to_hex(fi)}

    # ---- env maps
    def stops_from(labs):
        out = []
        for lab in labs:
            n = pb.nearest(lab)
            if not out or out[-1] != n:
                out.append(n)
        return out

    env_maps = {}
    fl, wl_, ce = targets["floor"], targets["walls"], targets["ceiling"]
    chrome_stops = stops_from([(fl[0] * 0.6, fl[1], fl[2]), fl, wl_, ce, pb.lab(light_names[-2]), pb.lab(light_names[-1])])
    if len(chrome_stops) < 3:
        chrome_stops = [light_names[1], light_names[len(light_names) // 2], light_names[-1]]
    env_maps["env_chrome"] = {"gen": "env", "size": 128, "stops": chrome_stops, "edge": chrome_stops[0],
                              "glint": light_names[-1], "glints": [[0.34, 0.24, 0.06], [0.64, 0.3, 0.035], [0.5, 0.14, 0.025]]}
    base_dark = sorted(fam_ramps[0]["names"], key=lambda x: pb.lab(x)[0])[:4] if fam_ramps else light_names[:4]
    if "view" in region_t:
        # glass renders as env x tint: build the env from the marked window view's own family (dark -> light),
        # as the shipped packs do (forest_village: leaf -> teal -> sky ramp), so windows read as the view
        v = region_t["view"]
        vf = fam_of.get(pb.nearest(v))
        vseq = sorted(vf["names"] if vf else [pb.nearest(v)], key=lambda x: pb.lab(x)[0])
        base_dark = vseq[-4:] if len(vseq) > 4 else vseq
    glass_stops = list(dict.fromkeys(["void"] + base_dark))
    if len(glass_stops) < 2:
        glass_stops = ["void", light_names[1]]
    env_maps["env_glass"] = {"gen": "env", "size": 64, "stops": glass_stops, "edge": "void", "glint": light_names[-1],
                             "glints": [[0.33, 0.27, 0.07]]}
    if env_needed.get("env_metal"):
        neutral = [n for n in pb.names if C.oklch(pb.lab(n))[1] < 0.06]
        ms = sorted(dict.fromkeys(["void"] + neutral + [light_names[len(light_names) // 2], light_names[-2]]), key=lambda x: pb.lab(x)[0])
        if len(ms) > 6:
            idx = [round(k * (len(ms) - 1) / 5) for k in range(6)]
            ms = [ms[k] for k in sorted(set(idx))]
        env_maps["env_metal"] = {"gen": "env", "size": 64, "stops": ms, "edge": ms[0], "glint": light_names[-1],
                                 "glints": [[0.36, 0.26, 0.06]]}

    # ---- colours / ui blocks for the runtime
    def hx(n):
        return pb.hex(n)

    lamp = pb.nearest(targets["warm_light"])
    lamp_dim = pb.nearest((targets["warm_light"][0] - 0.15, targets["warm_light"][1], targets["warm_light"][2]))
    colors = {"fog_ext": hx(fog_ext), "fog_int": hx(fog_int), "amb_ext": hx(light_names[min(2, len(light_names) - 1)]),
              "sun_ext": hx(light_names[int(len(light_names) * 0.6)]), "amb_int": hx(fog_int),
              "sun_int": hx(light_names[int(len(light_names) * 0.7)]), "lamp": hx(lamp), "lamp_dim": hx(lamp_dim),
              "window_light": hx(light_names[-3])}
    dark = sorted(pb.names, key=lambda x: pb.lab(x)[0])
    fill = dark[1] if len(dark) > 1 else dark[0]
    text = light_names[-1] if C.contrast_ratio(hx(light_names[-1]), hx(fill)) >= 4.5 else "white"
    ui = {"ink": hx("void"), "fill": hx(fill) + "d6", "frame": hx(pb.nearest(targets["metal"])), "text": hx(text),
          "dim": hx(light_names[int(len(light_names) * 0.65)]), "accent": hx(lamp)}
    dec["ui_contrast"] = r4(C.contrast_ratio(hx(text), hx(fill)))

    # ---- kit presets + fixtures (verbatim library params; named presets carry FULL params)
    kit_presets = {}
    for gid, eid in sorted(defaults.items()):
        kit_presets.setdefault(gid, {})["default"] = lib["entries"][eid]["params"]
    fixtures = {}
    for slot, eid in sorted(chosen.items()):
        e = lib["entries"][eid]
        slug = preset_slug(eid)
        kit_presets.setdefault(e["generator"], {})[slug] = e["params"]
        fixtures[slot] = {"generator": e["generator"], "preset": slug}

    # ---- palette lists
    if len(pb.names) > 32:
        raise ValueError("internal: palette grew to %d colours" % len(pb.names))
    ramps = {f["name"]: f["names"] for f in fam_ramps}
    ramps["light"] = list(light_names)
    if accents:
        ramps["accent"] = list(dict.fromkeys(accents))
    surf_sorted = {k: surf[k] for k in sorted(surf)}
    note = ("Draft theme pack from %d reference image(s): %s, %s; mood %s; materials %s; shapes architecture %s, "
            "furniture %s. Data only, built from the Hermes64 core. Drafted by hermes64_pack_from_refs; NOT approved."
            % (len(notes["references"]), notes["setting"], notes["time_of_day"], "/".join(notes["mood"]),
               ", ".join(notes["materials"][:4]), "/".join(notes["shape_language"]["architecture"]),
               "/".join(notes["shape_language"]["furniture"])))
    pack = {
        "id": pack_id, "version": "3.1.0", "note": note,
        "palette": list(pb.hexes), "palette_names": list(pb.names), "ramps": ramps, "light_ramp": list(light_names),
        "light_rig": rig, "fog": fog, "env_maps": env_maps, "materials": {r: materials[r] for r in CORE_ROLES},
        "kit_presets": kit_presets, "fixtures": fixtures,
        "cast": {"_note": "References only (KITS 3.1.0): people and animals are built by lane-characters. "
                          "This draft lists no cast; see refpack.cast_style for the agent's controlled style words."},
        "validator_thresholds": {"tri_limits": {}, "stretch": [0.45, 1.8], "visdiff_min": 0.015, "people_pairwise_min": 0.02},
        "colors": colors, "ui": ui,
        "refpack": {"status": "draft_unapproved", "surfaces": surf_sorted,
                    "cast_style": {k: v for k, v in sorted(notes.get("character_style", {}).items()) if k != "notes"},
                    "palette_sources": {n: s for n, s in zip(pb.names, pb.src)}},
    }
    return {"pack": pack, "decisions": dec, "warnings": warnings, "surfaces": surf, "usage": usage}
