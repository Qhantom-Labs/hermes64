"""Mood packs: derive a new kit pack (and its style-pack view) from an existing base pack plus a mood.

Pure functions, stdlib only, deterministic. A mood pack may change HUE IDENTITY, never QUALITY:

  kept exactly    palette_names, every material binding (roles, kinds, texture generators, ramps, sizes, tile_m),
                  kit presets, fixtures, cast, validator thresholds, env-map structure, light rig numbers,
                  every style-gate threshold except `accent_hues`
  moved           palette colours, by role family and as whole ramps (OKLCh: hue rotated toward the mood's arc by
                  the bible's per-family weight, chroma scaled, lightness mapped by one monotone curve per family),
                  the fog colour name (re-picked from the derived palette), view.json hex colours (same transform),
                  style_gate.accent_hues (the mood's accent arc)

Every texture is painted by its generator from a ramp of palette NAMES (kits/core/texgen.py: field -> soften ->
mottle quantize onto the ramp), so recolouring the palette recolours every texture with the same painting grammar,
the same mottle and the same crispness. What can still break consistency is the ramp itself (steps collapsing,
value order flipping, steps of one ramp drifting to different hues). `check_derived` measures exactly that, plus the
bible's hard limits (32 colours, light ramp >= 3, neon cut) and character readability against the ground.

Vocabulary (hue words, neutral words, time words, value keys, tone words) and role families + hue-shift weights come
from kits/core/style_bible.json (`mood_vocabulary`, `role_families`). Unknown words are refused, never guessed.
"""
import copy
import hashlib
import json
import math
import os
import re

MOOD_VERSION = "1.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))
BIBLE_PATH = os.path.join(HERE, "style_bible.json")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class MoodError(ValueError):
    pass


# --------------------------------------------------------------------------------------------- mood list (data)
# Every word here must exist in the bible's closed vocabulary (checked by mood_spec()). `dominant` drives the shade
# families (stone, roof, metal, ground, sky, wood), `support` the living/cloth families (foliage, cloth), `accent` the
# emissive family and the style gate's accent arc. `neutral` (optional, a bible neutral word) pulls chroma/value.
MOODS = {
    "purple_dusk": {"words": ["purple dusk", "wizard purple", "violet dusk", "purple twilight", "arcane dusk"],
                    "dominant": "purple", "support": "indigo", "accent": "gold", "time": "dusk",
                    "value_key": "low", "tone": "mysterious"},
    "ember_night": {"words": ["ember night", "ember", "volcanic night", "embers", "ashen night"],
                    "dominant": "crimson", "support": "orange", "accent": "amber", "time": "night",
                    "value_key": "low", "tone": "grim"},
    "candy_pastel": {"words": ["candy pastel", "candy", "pastel", "sugar", "candyland"],
                     "dominant": "pink", "support": "azure", "accent": "yellow", "time": "afternoon",
                     "value_key": "high", "neutral": "pastel", "tone": "whimsical"},
    "bone_white": {"words": ["bone white", "bone", "ivory", "bleached", "ossuary"],
                   "dominant": "yellow", "support": "amber", "accent": "crimson", "time": "noon",
                   "value_key": "high", "neutral": "white", "tone": "eerie"},
    "toxic_green": {"words": ["toxic green", "toxic", "acid", "radioactive", "swamp gas"],
                    "dominant": "lime", "support": "emerald", "accent": "magenta", "time": "night",
                    "value_key": "low", "tone": "eerie"},
    "frost_dawn": {"words": ["frost dawn", "frost", "icy dawn", "winter morning", "frozen"],
                   "dominant": "azure", "support": "teal", "accent": "rose", "time": "dawn",
                   "value_key": "mid", "tone": "serene"},
    "golden_hour": {"words": ["golden hour", "golden", "sunset gold", "warm evening"],
                    "dominant": "amber", "support": "orange", "accent": "crimson", "time": "golden_hour",
                    "value_key": "mid", "tone": "hopeful"},
    "deep_sea": {"words": ["deep sea", "underwater", "abyssal", "sunken", "ocean deep"],
                 "dominant": "teal", "support": "blue", "accent": "cyan", "time": "night",
                 "value_key": "low", "tone": "lonely"},
}

# Which mood hue each bible role family moves toward.
FAMILY_TARGET = {"stone": "dominant", "roof": "dominant", "metal": "dominant", "ground": "dominant",
                 "sky": "dominant", "wood": "dominant", "foliage": "support", "cloth": "support",
                 "emissive": "accent", "skin": None}
EMISSIVE_ACCENT_WEIGHT = 0.35     # the bible's emissive weight is 0 (keep glow identity); the accent moves it this far
RAMP_SMOOTH = 3
SKIN_WEIGHT_CAP = 0.12            # names that also paint skin barely move (characters stay readable)
NEUTRAL_C = 0.03                  # OKLCh chroma below this is achromatic: hue is meaningless, a tint is added instead
TINT_C = 0.08                     # tint chroma given to greys at full family weight
TIME_SKY = {  # (unused, sky chroma scale, lightness-curve exponent factor) per time word
    "dawn": (1.0, 1.0, 1.0), "morning": (1.0, 1.0, 1.0), "noon": (1.0, 0.9, 1.0), "afternoon": (1.0, 1.0, 1.0),
    "golden_hour": (1.0, 1.1, 1.01), "dusk": (1.0, 1.15, 1.02), "twilight": (1.0, 1.1, 1.03),
    "night": (1.0, 0.9, 1.04), "midnight": (1.0, 0.85, 1.05), "indoor_warm": (1.0, 1.0, 1.0),
    "indoor_cool": (1.0, 1.0, 1.0)}
VALUE_KEY = {"low": 1.04, "mid": 1.0, "high": 1.12}   # curve exponent: low darkens mids (pow), high lifts mids (lift)
NEUTRAL_WORD = {"pastel": (0.55, 0.06), "white": (0.35, 0.08), "grey": (0.3, 0.0), "beige": (0.6, 0.03),
                "earthy": (0.8, -0.02), "brown": (0.9, -0.03), "black": (0.7, -0.06)}  # chroma scale, extra L lift
STRENGTH = 0.85                   # global hue-rotation strength (1 = families reach the arc at weight 1)
NEON_MARGIN = (0.55, 0.88)        # derived colours stay below sat .55 OR value .88 unless the base colour was neon

# check thresholds (first numbers, set so all 17 shipped packs and the 8 moods pass on the 3 proof bases; see tests)
RAMP_CONTRAST_KEEP = 0.55         # every ramp step keeps >= 55% of its base OKLab lightness step
RAMP_ORDER_EPS = 0.02             # base steps smaller than this may reorder
RAMP_HUE_SPREAD_MAX = 40.0        # degrees: spread of the hue shift across the chromatic steps of one ramp
READ_MIN_DE = 0.07                # character (skin) vs ground OKLab distance floor ...
READ_KEEP = 0.5                   # ... and at least half of the base pack's distance


# --------------------------------------------------------------------------------------------- colour maths
def _hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _rgb_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x * 255.0)))) for x in c)


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_oklab(rgb):
    r, g, b = (_lin(x) for x in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_rgb(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(_gam(x) if x > 0 else 0.0 for x in (r, g, bb)), all(-1e-4 <= x <= 1.0001 for x in (r, g, bb))


def hex_lch(h):
    L, a, b = rgb_oklab(_hex_rgb(h))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def lch_hex(L, C, H):
    """OKLCh -> hex, reducing chroma until the colour is inside sRGB (never shifts lightness or hue)."""
    L = max(0.0, min(1.0, L))
    for _ in range(40):
        rgb, ok = oklab_rgb((L, C * math.cos(math.radians(H)), C * math.sin(math.radians(H))))
        if ok or C < 1e-4:
            return _rgb_hex(rgb)
        C *= 0.92
    return _rgb_hex(oklab_rgb((L, 0.0, 0.0))[0])


def hsv(h):
    r, g, b = _hex_rgb(h)
    mx, mn = max(r, g, b), min(r, g, b)
    s = 0.0 if mx <= 0 else (mx - mn) / mx
    if mx == mn:
        hue = 0.0
    elif mx == r:
        hue = (60 * ((g - b) / (mx - mn))) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    return hue, s, mx


def is_neon(h, sat_min=0.6, val_min=0.92):
    _, s, v = hsv(h)
    return s >= sat_min and v >= val_min


def oklab_de(h1, h2):
    a, b = rgb_oklab(_hex_rgb(h1)), rgb_oklab(_hex_rgb(h2))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _hue_diff(a, b):
    """Signed shortest rotation from hue a to hue b, degrees."""
    return (b - a + 180.0) % 360.0 - 180.0


# oklch hue of a bible HSV arc centre (arcs are written in HSV degrees; rotation happens in OKLCh)
def _arc_centre_hsv(arcs):
    lo, hi = arcs[0]
    if len(arcs) > 1:                       # wrap-around arc like crimson [[340,360],[0,8]]
        span = (hi - lo) + (arcs[1][1] - arcs[1][0])
        return (lo + span / 2.0) % 360.0
    return (lo + hi) / 2.0


def _hsv_hue_to_oklch_hue(h):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, 0.6, 0.75)
    return hex_lch(_rgb_hex((r, g, b)))[2]


# --------------------------------------------------------------------------------------------- bible + mood spec
def load_bible(path=None):
    with open(path or BIBLE_PATH, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def mood_names():
    return sorted(MOODS)


def resolve_mood(text):
    """Free text ('Purple Dusk', 'wizard-purple', 'purple_dusk') -> mood id, or None (never a guess)."""
    t = re.sub(r"[^a-z ]+", " ", str(text).lower().replace("_", " ").replace("-", " ")).strip()
    t = re.sub(r"\s+", " ", t)
    if t.replace(" ", "_") in MOODS:
        return t.replace(" ", "_")
    hits = sorted(((len(w), mid) for mid, m in MOODS.items() for w in m["words"]
                   if re.search(r"\b%s\b" % re.escape(w), t)), reverse=True)
    return hits[0][1] if hits else None


def mood_from_brief(palette_mood, mood=None, mood_id="brief"):
    """Build a mood spec from a plan-07 brief (`palette_mood` {dominant, support, accent, value_key}, `mood` {time})."""
    pm = palette_mood or {}
    sup = pm.get("support") or []
    spec = {"words": [], "dominant": pm.get("dominant"), "support": sup[0] if isinstance(sup, list) and sup else
            (sup or pm.get("dominant")), "accent": (pm.get("accent") or "gold").split()[-1],
            "time": (mood or {}).get("time", "dusk"), "value_key": pm.get("value_key", "mid"),
            "tone": (mood or {}).get("tone")}
    return mood_spec(spec, mood_id=mood_id)


def mood_spec(mood, bible=None, mood_id=None):
    """Validate a mood (id or dict) against the bible's closed vocabulary; returns a normalised dict."""
    bible = bible or load_bible()
    if isinstance(mood, str):
        mid = mood if mood in MOODS else resolve_mood(mood)
        if not mid:
            raise MoodError("unknown mood %r (known: %s)" % (mood, ", ".join(mood_names())))
        mood, mood_id = MOODS[mid], mid
    voc = bible["mood_vocabulary"]
    hues, neutrals = voc["hue_words_hsv_deg"], voc["neutral_words"]
    out = {"id": mood_id or mood.get("id") or "custom"}
    for key in ("dominant", "support", "accent"):
        w = mood.get(key)
        if w not in hues:
            raise MoodError("mood %s: %r is not a bible hue word (%s)" % (key, w, ", ".join(sorted(hues))))
        out[key] = w
        out[key + "_hue"] = round(_hsv_hue_to_oklch_hue(_arc_centre_hsv(hues[w])), 3)
    out["accent_arc_hsv"] = [list(a) for a in hues[mood["accent"]]]
    if mood.get("time") not in voc["time_words"] or mood["time"] not in TIME_SKY:
        raise MoodError("mood time %r is not a bible time word (%s)" % (mood.get("time"), ", ".join(sorted(voc["time_words"]))))
    out["time"] = mood["time"]
    out["environment"] = voc["time_words"][mood["time"]]
    if mood.get("value_key") not in voc["value_keys_mean_luma"]:
        raise MoodError("mood value_key %r not in %s" % (mood.get("value_key"), sorted(voc["value_keys_mean_luma"])))
    out["value_key"] = mood["value_key"]
    if mood.get("neutral") is not None:
        if mood["neutral"] not in neutrals or mood["neutral"] not in NEUTRAL_WORD:
            raise MoodError("mood neutral %r is not a bible neutral word" % mood["neutral"])
        out["neutral"] = mood["neutral"]
    if mood.get("tone") is not None and mood["tone"] not in voc["tone_words"]:
        raise MoodError("mood tone %r is not a bible tone word" % mood["tone"])
    out["tone"] = mood.get("tone")
    # optional expert overrides (used by the known-bad controls; a mood may never touch quality thresholds)
    for k in ("family_weights", "strength", "chroma_scale", "light_curve"):
        if k in mood:
            out[k] = copy.deepcopy(mood[k])
    return out


def mood_sha(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------------------------- name -> family weight
def _names_in(obj, names):
    out = []
    if isinstance(obj, str):
        if obj in names:
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _names_in(v, names)
    elif isinstance(obj, list):
        for v in obj:
            out += _names_in(v, names)
    return out


def role_family_map(bible):
    return {r: fam for fam, roles in bible["role_families"]["families"].items() for r in roles}


def name_usage(pack, bible):
    """palette name -> list of role families that paint with it (one entry per reference)."""
    names = set(pack["palette_names"])
    fam_of = role_family_map(bible)
    use = {n: [] for n in pack["palette_names"]}
    env_users = {}
    for role, m in pack["materials"].items():
        fam = fam_of.get(role, "stone")
        for n in _names_in({k: v for k, v in m.items() if k != "kind"}, names):
            use[n].append(fam)
        if m.get("env"):
            env_users.setdefault(m["env"], []).append(fam)
    for env, em in pack.get("env_maps", {}).items():
        for n in _names_in(em, names):
            use[n] += env_users.get(env, ["metal"])
    for n in pack.get("light_ramp", []):
        use[n].append("stone")
    fog = pack.get("fog", {})
    for n in _names_in(fog, names):
        use[n].append("sky")
    return use


def _family_weight(spec, bible, fam):
    w = dict(bible["role_families"]["hue_shift_weight"])
    w.update(spec.get("family_weights") or {})
    if fam == "emissive" and "emissive" not in (spec.get("family_weights") or {}):
        return EMISSIVE_ACCENT_WEIGHT
    return float(w.get(fam, 0.5))


def name_plan(pack, spec, bible):
    """palette name -> (weight, target hue, family, protected). Weight = mean over the name's references, so every
    step of a ramp moves together; names that paint skin are protected (tiny hue move, no chroma change) so
    characters stay readable."""
    use = name_usage(pack, bible)
    plan = {}
    skin_override = "skin" in (spec.get("family_weights") or {})
    for n, fams in use.items():
        fams = fams or ["stone"]
        counts = {}
        for f in fams:
            counts[f] = counts.get(f, 0) + 1
        main = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        w = sum(_family_weight(spec, bible, f) for f in fams) / len(fams)
        # names that paint skin (characters readable) or mostly glow (fire, lamps: the warm practicals that carry the
        # accent; half or more of the name's references are emissive roles) are protected: small hue move, no chroma
        # change
        protected = ("skin" in counts and not skin_override) or counts.get("emissive", 0) * 2 >= len(fams)
        if protected:
            w = min(w, SKIN_WEIGHT_CAP)
        elif skin_override and "skin" in counts:
            w = _family_weight(spec, bible, "skin")
        # move vector: the mean of each reference's (weight x direction), so a name shared by stone and fire moves
        # between the two instead of following whichever family happens to be the majority
        vx = vy = 0.0
        for f in fams:
            wf = min(_family_weight(spec, bible, f), w) if protected else _family_weight(spec, bible, f)
            if skin_override and f == "skin":
                wf = _family_weight(spec, bible, "skin")
            h = math.radians(spec[(FAMILY_TARGET.get(f) or "dominant") + "_hue"])
            vx += wf * math.cos(h) / len(fams)
            vy += wf * math.sin(h) / len(fams)
        plan[n] = [vx, vy, main, protected]
    # ramp smoothing: steps that share a texture ramp pull their move vectors together (RAMP_SMOOTH passes), so a
    # ramp recolours as one painted ramp instead of drifting apart step by step
    ramps = [list(dict.fromkeys(r)) for _, r in _ramps(pack)] + [list(dict.fromkeys(pack.get("light_ramp", [])))]
    for _ in range(RAMP_SMOOTH):
        acc = {n: [0.0, 0.0, 0] for n in plan}
        for r in ramps:
            r = [n for n in r if n in plan]
            if len(r) < 2:
                continue
            mx = sum(plan[n][0] for n in r) / len(r)
            my = sum(plan[n][1] for n in r) / len(r)
            for n in r:
                acc[n][0] += mx
                acc[n][1] += my
                acc[n][2] += 1
        for n, (ax, ay, k) in acc.items():
            if k and not plan[n][3]:
                plan[n][0] = 0.5 * plan[n][0] + 0.5 * ax / k
                plan[n][1] = 0.5 * plan[n][1] + 0.5 * ay / k
    out = {}
    for n, (vx, vy, main, protected) in plan.items():
        out[n] = (round(math.hypot(vx, vy), 5), round(math.degrees(math.atan2(vy, vx)) % 360.0, 3), main, protected)
    return out


# --------------------------------------------------------------------------------------------- the move
def light_curve(spec):
    """ONE monotone lightness curve for every colour of the pack, so no ramp can flip its value order. Built-in moods
    use a power curve that keeps black and white fixed (a low key darkens the mid-tones and keeps the highlights the
    render gates look for; a high key lifts the mid-tones and keeps the darks): returns ("pow", g) or ("lift", g).
    An explicit `light_curve` [a, b] is an affine L' = a*L + b (expert override, used by the known-bad controls)."""
    f = spec.get("light_soften", 1.0)            # derive_checked's clamp eases the curve toward identity
    if spec.get("light_curve"):
        a, b = spec["light_curve"]
        return ("affine", 1.0 - (1.0 - a) * f, b * f)
    g = VALUE_KEY[spec["value_key"]] * TIME_SKY[spec["time"]][2]
    lift = spec["value_key"] == "high"
    if spec.get("neutral"):
        k = NEUTRAL_WORD[spec["neutral"]][1]
        if k > 0:
            lift, g = True, (g if lift else 1.0) * (1.0 + 2.0 * k)
        elif k < 0 and not lift:
            g *= 1.0 - 2.0 * k
    g = 1.0 + (g - 1.0) * f
    return ("lift" if lift else "pow", g)


def apply_curve(curve, L):
    L = max(0.0, min(1.0, L))
    if curve[0] == "affine":
        return curve[1] * L + curve[2]
    if curve[0] == "lift":
        return 1.0 - (1.0 - L) ** curve[1]
    return L ** curve[1]


def move_colour(hexc, weight, target_hue, fam, spec, protected=False, keep_l=False):
    """Move one colour: OKLab (a, b) blended toward the mood direction by the family weight (a continuous move: no
    wrap-around jumps, greys get a tint of TINT_C), chroma scaled by the mood (never on protected skin names), then
    the shared lightness curve, then the neon cut with margin."""
    L, A, B = rgb_oklab(_hex_rgb(hexc))
    C = math.hypot(A, B)
    w = max(0.0, min(1.0, weight * spec.get("strength", STRENGTH)))
    t = math.radians(target_hue)
    mag = max(C, TINT_C)
    A2, B2 = (1 - w) * A + w * mag * math.cos(t), (1 - w) * B + w * mag * math.sin(t)
    cs = 1.0
    if not protected and fam != "emissive":
        cs = spec.get("chroma_scale", 1.0)
        if spec.get("neutral"):
            cs *= NEUTRAL_WORD[spec["neutral"]][0]
        if fam == "sky":
            cs *= TIME_SKY[spec["time"]][1]
    C2 = math.hypot(A2, B2) * cs
    H2 = math.degrees(math.atan2(B2, A2)) % 360.0
    L2 = L if keep_l else apply_curve(light_curve(spec), L)
    out = lch_hex(L2, C2, H2)
    if not is_neon(hexc):
        for _ in range(60):
            _, s, v = hsv(out)
            if s < NEON_MARGIN[0] or v < NEON_MARGIN[1]:
                break
            C2 *= 0.93
            out = lch_hex(L2, C2, H2)
    return out


def _unique(hexes, order):
    """Nudge lightness of later duplicates by one 8-bit step so every palette colour stays distinct."""
    seen = set()
    out = list(hexes)
    for i in order:
        h = out[i]
        k = 0
        while h.lower() in seen:
            k += 1
            r, g, b = _hex_rgb(out[i])
            d = (k + 1) // 2 * (1 if k % 2 else -1) / 255.0
            h = _rgb_hex((r + d, g + d, b + d))
        seen.add(h.lower())
        out[i] = h
    return out


def derive_palette(pack, spec, bible):
    plan = name_plan(pack, spec, bible)
    hexes = [move_colour(h.lower(), plan[n][0], plan[n][1], plan[n][2], spec, plan[n][3]) for n, h in zip(pack["palette_names"], pack["palette"])]
    hexes = _unique(hexes, range(len(hexes)))
    return hexes, plan


def _nearest_name(hexc, names, hexes):
    return min(zip(names, hexes), key=lambda nh: (oklab_de(hexc, nh[1]), nh[0]))[0]


def _fog_target(base_hex, spec, bible, base=None):
    """The fog is the horizon: it takes exactly the move of the nearest sky-family palette colour of the base (the
    painted sky's horizon is drawn from those names), so fog and horizon stay together (n64 gate fog_horizon_delta)."""
    if base is not None:
        plan = name_plan(base, spec, bible)
        sky = [(n, h.lower()) for n, h in zip(base["palette_names"], base["palette"]) if plan[n][2] == "sky"]
        if sky:
            n = min(sky, key=lambda nh: (oklab_de(base_hex, nh[1]), nh[0]))[0]
            w, hue, _, _ = plan[n]
            return move_colour(base_hex.lower(), w, hue, "sky", spec)
    w = float(bible["role_families"]["hue_shift_weight"].get("sky", 1.0))
    return move_colour(base_hex.lower(), w, spec["dominant_hue"], "sky", spec)


def derive_pack(base, mood, bible=None, new_id=None):
    """base kit pack dict + mood (id, free text, or dict) -> derived kit pack dict (deterministic)."""
    bible = bible or load_bible()
    spec = mood_spec(mood, bible) if not (isinstance(mood, dict) and "dominant_hue" in mood) else mood
    d = copy.deepcopy(base)
    hexes, plan = derive_palette(base, spec, bible)
    d["palette"] = hexes
    names = d["palette_names"]
    pal_b = dict(zip(names, base["palette"]))
    # fog: re-pick the palette name nearest to the sky-moved fog colour (exterior and interior)
    fog = d.get("fog", {})
    if isinstance(fog.get("color"), str) and fog["color"] in pal_b:
        fog["color"] = _nearest_name(_fog_target(pal_b[fog["color"]], spec, bible, base), names, hexes)
    inner = fog.get("interior")
    if isinstance(inner, dict) and inner.get("color") in pal_b:
        inner["color"] = _nearest_name(_fog_target(pal_b[inner["color"]], spec, bible, base), names, hexes)
    d["id"] = new_id or "%s_%s" % (base["id"], spec["id"])
    d["texture_seed"] = base.get("texture_seed", base["id"])     # same strokes and mottle as the base textures
    if "style" in d:
        d["style"] = d["id"]
    d["note"] = ("Mood pack derived by kits/core/mood.py %s from %r + mood %r (%s %s, accent %s, %s, value %s). "
                 "Same roles, materials, ramps, presets and thresholds as the base; only colours moved."
                 % (MOOD_VERSION, base["id"], spec["id"], spec["dominant"], spec["time"], spec["accent"],
                    spec["support"], spec["value_key"]))
    d["mood"] = {"id": spec["id"], "version": MOOD_VERSION, "base": base["id"], "base_sha256": pack_sha(base),
                 "mood_sha256": mood_sha(spec), "spec": spec,
                 "families": {n: plan[n][2] for n in names}}
    return d


def pack_sha(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------------------------- views (style packs)
def _collect_hex(obj, out):
    if isinstance(obj, str) and HEX.match(obj):
        out.add(obj.lower())
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_hex(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_hex(v, out)


def _subst_hex(obj, cmap):
    if isinstance(obj, str) and HEX.match(obj):
        new = cmap[obj.lower()]
        return new.upper() if obj[1:] == obj[1:].upper() else new      # keep the source's case convention
    if isinstance(obj, dict):
        return {k: _subst_hex(v, cmap) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_hex(v, cmap) for v in obj]
    return obj


def colour_map(base, derived, extra_hexes, bible=None, fog_hexes=()):
    """base hex -> derived hex for every hex in a style pack / view: exact palette colours map to their derived
    colour; any other colour (UI, emitters, profile tints) takes the move of its nearest base palette colour."""
    bible = bible or load_bible()
    spec = derived["mood"]["spec"]
    plan = name_plan(base, spec, bible)
    by_hex = {h.lower(): (n, d) for n, h, d in zip(base["palette_names"], base["palette"], derived["palette"])}
    cmap = {}
    fog_hexes = {h.lower() for h in fog_hexes}
    for h in sorted(extra_hexes):
        if h in fog_hexes:
            cmap[h] = _fog_target(h, spec, bible, base)      # the fog is the horizon: it follows the sky's move
        elif h in by_hex:
            cmap[h] = by_hex[h][1].lower()
        else:
            n = _nearest_name(h, base["palette_names"], [x.lower() for x in base["palette"]])
            cmap[h] = move_colour(h, plan[n][0], plan[n][1], plan[n][2], spec, plan[n][3])
    # keep distinct inputs distinct
    keys = sorted(cmap)
    vals = _unique([cmap[k] for k in keys], range(len(keys)))
    return dict(zip(keys, vals))


# view.json colour classes by key path. Lights keep their lightness (a mood re-tints light, it never dims it: the
# render gates' contrast, exposure and highlight checks stay the base's problem, not the mood's); grade and UI colours
# are not scene colours and never move.
VIEW_EXACT_KEYS = ("gain", "lift", "ui", "ui_bg", "ui_text")
VIEW_LIGHT_KEYS = ("key", "fill", "ambient", "ground", "sky", "kicker", "color", "halo_color", "pool_color")


def _view_class(path):
    if any(k in VIEW_EXACT_KEYS for k in path):
        return "exact"
    if "fog" in path or "fog_colour" in path or "fog_color" in path:
        return "fog"
    if "emitters" in path or ("profiles" in path and path[-1] in VIEW_LIGHT_KEYS):
        return "light"
    return "surface"


def _subst_view(obj, fn, path=()):
    if isinstance(obj, str) and HEX.match(obj):
        new = fn(path, obj.lower())
        return new.upper() if obj[1:] == obj[1:].upper() else new
    if isinstance(obj, dict):
        return {k: _subst_view(v, fn, path + (k,)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_view(v, fn, path) for v in obj]
    return obj


def derive_view(base_kit, derived_kit, view, bible=None):
    """Style-pack view.json -> derived view. Surface colours (palette, palette_colors, backgrounds, shadow, material
    tints) take the palette move (exact palette colours map to their derived colour, others take the move of their
    nearest base palette colour); lights (profile key/fill/ambient/ground/sky/kicker, emitter colours) take the hue
    move with their lightness kept; fog follows the sky; grade gain/lift and UI colours stay. accent_hues = the mood
    accent arc. Returns (view, surface colour map)."""
    bible = bible or load_bible()
    spec = derived_kit["mood"]["spec"]
    hexes = set()
    _collect_hex(view, hexes)
    cmap = colour_map(base_kit, derived_kit, hexes, bible)
    plan = name_plan(base_kit, spec, bible)
    base_hex = [x.lower() for x in base_kit["palette"]]

    def fn(path, h):
        cls = _view_class(path)
        if cls == "exact":
            return h
        if cls == "fog":
            return _fog_target(h, spec, bible, base_kit)
        if cls == "light" and "emitters" in path:     # practical lights: toward the accent, lightness kept
            return move_colour(h, EMISSIVE_ACCENT_WEIGHT, spec["accent_hue"], "emissive", spec, True, keep_l=True)
        if cls == "light":
            n = _nearest_name(h, base_kit["palette_names"], base_hex)
            w, hue, fam, prot = plan[n]
            return move_colour(h, w, hue, fam, spec, prot, keep_l=True)
        return cmap[h]
    v = _subst_view(view, fn)
    did = derived_kit["id"]
    for k in ("kit_pack_id", "pack_id"):
        if k in v:
            v[k] = did
    sg = v.get("style_gate")
    if isinstance(sg, dict):
        sg["accent_hues"] = accent_hues(spec, sg.get("accent_hues"))
    return v, cmap


def accent_hues(spec, base_arcs=None):
    """The mood's accent arc (padded 8 deg) plus the base pack's arcs: glow names are protected, so the base warm
    practicals stay accents alongside the mood accent."""
    arcs = [[float(max(0, a - 8)), float(min(360, b + 8))] for a, b in spec["accent_arc_hsv"]]
    for a in base_arcs or []:
        if list(map(float, a)) not in arcs:
            arcs.append([float(a[0]), float(a[1])])
    return sorted(arcs)


def _fog_hexes(obj):
    """Hex colours stored under a key named fog / fog_colour / fog_color anywhere in a view or style pack."""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("fog", "fog_colour", "fog_color"):
                if isinstance(v, str) and HEX.match(v):
                    out.add(v.lower())
                elif isinstance(v, dict) and isinstance(v.get("color"), str) and HEX.match(v["color"]):
                    out.add(v["color"].lower())
            out |= _fog_hexes(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _fog_hexes(v)
    return out


def derive_style_pack(style_pack, cmap, new_id):
    sp = _subst_hex(style_pack, cmap)
    sp["id"] = new_id
    if "kit_pack_id" in sp:
        sp["kit_pack_id"] = new_id
    return sp


# --------------------------------------------------------------------------------------------- checks
HUE_C_MIN = 0.04                  # steps below this chroma have no meaningful hue for the drift check


def _spread(hues):
    """Smallest arc (degrees) that contains every hue."""
    hs = sorted(h % 360.0 for h in hues)
    gaps = [(hs[(i + 1) % len(hs)] - hs[i]) % 360.0 for i in range(len(hs))]
    return 360.0 - max(gaps) if len(hs) > 1 else 0.0


def _ramps(pack):
    out = []
    for role, m in sorted(pack["materials"].items()):
        t = m.get("texture") or {}
        r = t.get("ramp")
        if isinstance(r, list) and len(r) >= 2:
            out.append((role, r))
    return out


GROUND_ROLES = ("floor", "path", "grass", "field", "dirt", "step")


def readability(pack):
    """OKLab distance between the skin colour and the middle colour of each ground ramp (min over ground roles)."""
    pal = dict(zip(pack["palette_names"], pack["palette"]))
    skin = (pack["materials"].get("skin", {}).get("texture") or {}).get("ramp") or []
    if not skin:
        return None, {}
    s = pal[skin[len(skin) // 2]]
    per = {}
    for role in GROUND_ROLES:
        mat = pack["materials"].get(role)
        r = (mat.get("texture") or {}).get("ramp") if mat else None
        if r:
            per[role] = round(oklab_de(s, pal[r[len(r) // 2]]), 4)
    return (min(per.values()) if per else None), per


def check_derived(base, derived, bible=None, base_view=None, derived_view=None):
    """Hard rules on a derived pack against its base. Returns {ok, errors, warnings, numbers}."""
    from .packs import validate_pack_dict, CORE_ROLES
    bible = bible or load_bible()
    err, warn, num = [], [], {}
    err += ["pack: " + e for e in validate_pack_dict(derived)]
    pal = bible["palette"]
    if len(derived["palette"]) > pal["max_colours"]:
        err.append("palette has %d colours > %d" % (len(derived["palette"]), pal["max_colours"]))
    if len(derived["light_ramp"]) < pal["light_ramp_min"]:
        err.append("light ramp has %d steps < %d" % (len(derived["light_ramp"]), pal["light_ramp_min"]))
    missing = [r for r in CORE_ROLES if r not in derived["materials"]]
    if missing:
        err.append("core roles not bound: %s" % ", ".join(missing))
    # quality never moves: everything except colours, fog colour names, id/note/style/mood is byte-identical
    for k in sorted(set(base) | set(derived)):
        if k in ("palette", "id", "note", "style", "mood", "fog", "texture_seed"):
            continue
        if base.get(k) != derived.get(k):
            err.append("quality field %r changed (a mood may change hue identity, never quality)" % k)
    bf, df = dict(base.get("fog", {})), dict(derived.get("fog", {}))
    for f in (bf, df):
        f.pop("color", None)
        if isinstance(f.get("interior"), dict):
            f["interior"] = {k: v for k, v in f["interior"].items() if k != "color"}
    if bf != df:
        err.append("fog distances changed (only the fog colour may move)")
    # neon cut
    neon = pal.get("neon_hsv", {"sat_min": 0.6, "val_min": 0.92})
    sm, vm = neon.get("sat_min", 0.6), neon.get("val_min", 0.92)
    new_neon = [n for n, b, d in zip(derived["palette_names"], base["palette"], derived["palette"])
                if is_neon(d, sm, vm) and not is_neon(b, sm, vm)]
    if new_neon:
        err.append("neon cut: %s became neon-capable (sat >= %.2f and value >= %.2f)" % (", ".join(new_neon), sm, vm))
    share = sum(is_neon(c, sm, vm) for c in derived["palette"]) / float(len(derived["palette"]))
    num["neon_share"] = round(share, 4)
    if share > pal.get("neon_palette_share_max", 0.0625) + 1e-9:
        err.append("neon: %.1f%% of the palette is neon-capable (max %.1f%%)" % (100 * share, 100 * pal["neon_palette_share_max"]))
    # ramps: value order, step contrast, hue coherence
    pb, pd = dict(zip(base["palette_names"], base["palette"])), dict(zip(derived["palette_names"], derived["palette"]))
    worst_keep, worst_spread, flips = 9.0, 0.0, []
    for label, ramp in _ramps(base) + [("light_ramp", base["light_ramp"])]:
        Lb = [hex_lch(pb[n])[0] for n in ramp]
        Ld = [hex_lch(pd[n])[0] for n in ramp]
        for i in range(len(ramp) - 1):
            db, dd = Lb[i + 1] - Lb[i], Ld[i + 1] - Ld[i]
            if abs(db) < RAMP_ORDER_EPS:
                continue
            if db * dd <= 0:
                flips.append("%s %s->%s" % (label, ramp[i], ramp[i + 1]))
                continue
            worst_keep = min(worst_keep, dd / db)
        hb = [hex_lch(pb[n]) for n in dict.fromkeys(ramp)]
        hd = [hex_lch(pd[n]) for n in dict.fromkeys(ramp)]
        both = [(x[2], y[2]) for x, y in zip(hb, hd) if x[1] >= HUE_C_MIN and y[1] >= HUE_C_MIN]
        if len(both) >= 2:
            worst_spread = max(worst_spread, _spread([y for _, y in both]) - _spread([x for x, _ in both]))
    num["ramp_contrast_keep_min"] = round(worst_keep, 4) if worst_keep < 9 else 1.0
    num["ramp_hue_shift_spread_max"] = round(worst_spread, 2)
    if flips:
        err.append("ramp value order flipped: %s" % ", ".join(flips[:6]))
    if worst_keep < RAMP_CONTRAST_KEEP:
        err.append("ramp step contrast fell to %.0f%% of the base (min %.0f%%)" % (100 * worst_keep, 100 * RAMP_CONTRAST_KEEP))
    if worst_spread > RAMP_HUE_SPREAD_MAX:
        err.append("ramp hue drift: steps of one ramp moved %.0f deg apart (max %.0f)" % (worst_spread, RAMP_HUE_SPREAD_MAX))
    # characters readable against the ground
    rb, _ = readability(base)
    rd, per = readability(derived)
    num["readability_base"], num["readability"], num["readability_per_ground"] = rb, rd, per
    if rd is not None and rb is not None:
        need = max(READ_MIN_DE, READ_KEEP * rb) if rb >= READ_MIN_DE else READ_KEEP * rb
        num["readability_need"] = round(need, 4)
        if rd < need:
            err.append("characters unreadable: skin vs ground OKLab distance %.3f < %.3f (base %.3f)" % (rd, need, rb))
    # view: only accent_hues may differ among style-gate thresholds
    if base_view is not None and derived_view is not None:
        a, b = dict(base_view.get("style_gate") or {}), dict(derived_view.get("style_gate") or {})
        a.pop("accent_hues", None)
        b.pop("accent_hues", None)
        if a != b:
            err.append("view style_gate thresholds changed beyond accent_hues")
        if (base_view.get("n64") or {}) != (derived_view.get("n64") or {}):
            err.append("view n64 thresholds changed")
    return {"ok": not err, "errors": err, "warnings": warn, "numbers": num}


SOFTEN_LADDER = (1.0, 0.8, 0.6, 0.4)


def derive_checked(base, mood, bible=None, new_id=None, textures=True):
    """derive_pack, then check_derived and (textures=True) the look-continuity check of every texture painted by
    the real generators against the same texture in the base pack. If a check fails, retry with the mood strength
    stepped down (SOFTEN_LADDER) and report the clamp. Returns (derived or None, report). Never loosens a check."""
    bible = bible or load_bible()
    spec0 = mood_spec(mood, bible) if not (isinstance(mood, dict) and "dominant_hue" in mood) else mood
    tried = []
    base_tex = None
    for f in SOFTEN_LADDER:
        spec = dict(spec0)
        if f != 1.0:
            spec["strength"] = round(spec0.get("strength", STRENGTH) * f, 4)
            spec["light_soften"] = f
        d = derive_pack(base, spec, bible, new_id)
        rep = check_derived(base, d, bible)
        if rep["ok"] and textures:
            from . import look
            if base_tex is None:
                base_tex = look.paint_pack_textures(base)
            lc = look.continuity(look.paint_pack_textures(d), d, base_tex, base)
            rep["look"] = {"ok": lc["ok"], "errors": lc["errors"], "set": lc["set"]}
            if not lc["ok"]:
                rep["ok"] = False
                rep["errors"] = ["look: " + e for e in lc["errors"]]
        tried.append({"strength": spec.get("strength", STRENGTH), "ok": rep["ok"], "errors": rep["errors"][:4]})
        if rep["ok"]:
            rep["strength"] = spec.get("strength", STRENGTH)
            rep["clamped"] = f != 1.0
            rep["tried"] = tried
            return d, rep
    return None, {"ok": False, "errors": tried[-1]["errors"], "tried": tried, "clamped": True,
                  "warnings": ["mood %r refused on base %r at every strength" % (spec0["id"], base["id"])]}
