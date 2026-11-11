"""Style bible as data (plan 07 section 2.3): one derived export of the numbers every asset path reads.

    python3 -B -m tools.style_bible build     # write kits/core/style_bible.json
    python3 -B -m tools.style_bible check     # regenerate in memory; exit 1 if the committed file drifted

kits/core/style_bible.json is NEVER hand-edited. Every section names the source file and symbol it was read
from, so the bible cannot drift from the real gates: the gate code and data stay the single source of truth
and this file is an export of them (docs/STYLE-ARCHITECTURE.md section 4: no third source of truth).

Sections and where they come from:
  palette        kits/core/packs.py CORE_ROLES/OPTIONAL_ROLES/KINDS; colour and light-ramp limits are PROBED
                 against kits/core/palette.py Palette and packs.validate_pack_dict (not copied from text)
  budgets        kits/core/packs.py CORE_CLASSES; adventure_maker/packs.py LIMITS; kits/validate/checks.py
                 TEX_LIMIT; kits/core/n64_look.json texel_density; texture sizes seen in shipped packs
  extents        kits/validate/checks.py EXTENTS, NAME_RE, NODE_RE
  light, fog     kits/core/n64_look.json lighting, fog, environments
  material       kits/core/n64_look.json bake, textures; shipped pack material kinds
  render_gates   adventure_maker/style_gate.py CORE_DEFAULTS; adventure_maker/n64_gate.py thresholds() and the
                 neon HSV cut PROBED through n64_gate.colour_stats
  silhouette     MEASURED: every registered generator built once at defaults (python, no Blender, no files);
                 per class p5/p50/p95. ADVISORY ranges (warnings, never hard gates) until the 20-prompt test
  reference      kits/core/style_ref_numbers.json (numbers-only export of the private study references made by
                 tools/style_ref_measure.py); ADVISORY
  characters     POINTER to profiles/character-styles/n64_base.json (CHARS3 owns face/proportion rules); hash only
  mood_vocabulary  hand-written closed word lists (hue arcs, time, weather, value keys, tone) for the brief and
                 mood packs; REVIEW-NEEDED by Fable
  role_families  hand-written grouping of every palette role for whole-ramp mood remaps (plan 2.5); REVIEW-NEEDED

check_asset(bible, summary) and check_pack(bible, pack_dict) apply the HARD rules; silhouette and reference
ranges only ever produce warnings.
"""
import colorsys
import hashlib
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
if str(R) not in sys.path:
    sys.path.insert(0, str(R))
if str(R / "kits") not in sys.path:
    sys.path.append(str(R / "kits"))  # after the repo root: kits/tools must not shadow tools/

OUT = R / "kits" / "core" / "style_bible.json"
REF_NUMBERS = R / "kits" / "core" / "style_ref_numbers.json"
LOOK = R / "kits" / "core" / "n64_look.json"
CHAR_STYLE = R / "profiles" / "character-styles" / "n64_base.json"
PACKS_DIR = R / "kits" / "packs"
FORMAT = "hermes64-style-bible/1"


# --------------------------------------------------------------------------------------------- vocab (hand)
# HSV hue arcs in degrees (the unit style_gate accent_hues uses). Arcs overlap on purpose: a word names a region.
HUE_WORDS = {
    "red": [[345, 360], [0, 15]], "crimson": [[340, 360], [0, 8]], "orange": [[15, 40]], "amber": [[30, 48]],
    "gold": [[38, 55]], "yellow": [[48, 65]], "lime": [[65, 95]], "green": [[90, 150]], "emerald": [[130, 160]],
    "teal": [[160, 190]], "cyan": [[180, 200]], "azure": [[195, 220]], "blue": [[210, 245]],
    "indigo": [[235, 262]], "violet": [[258, 285]], "purple": [[265, 300]], "magenta": [[295, 325]],
    "pink": [[320, 350]], "rose": [[330, 355]],
}
NEUTRAL_WORDS = {  # no hue arc: saturation/value words
    "white": {"sat_max": 0.12, "val_min": 0.85}, "black": {"val_max": 0.15}, "grey": {"sat_max": 0.12},
    "brown": {"hue": [[15, 45]], "sat_min": 0.3, "val_max": 0.55}, "beige": {"hue": [[25, 50]], "sat_max": 0.35},
    "pastel": {"sat_max": 0.35, "val_min": 0.75}, "earthy": {"hue": [[15, 60]], "sat_max": 0.5, "val_max": 0.6},
}
TIME_WORDS = {  # -> kits/core/n64_look.json environments key used for light/fog ranges
    "dawn": "exterior_day", "morning": "exterior_day", "noon": "exterior_day", "afternoon": "exterior_day",
    "golden_hour": "exterior_day", "dusk": "exterior_night", "twilight": "exterior_night",
    "night": "exterior_night", "midnight": "exterior_night", "indoor_warm": "interior_warm",
    "indoor_cool": "interior_cool",
}
WEATHER_WORDS = ["clear", "cloudy", "overcast", "rain", "storm", "snow", "fog", "mist", "sandstorm", "ash"]
VALUE_KEYS = {"low": [0.12, 0.35], "mid": [0.3, 0.55], "high": [0.5, 0.7]}  # mean luma, inside style_gate bounds
TONE_WORDS = ["cozy", "mysterious", "eerie", "heroic", "melancholic", "whimsical", "tense", "serene", "grim",
              "festive", "sacred", "lonely", "bustling", "ancient", "hopeful", "dreamlike"]

# Every palette role (core + optional) in exactly one family; mood remaps move whole families (plan 2.5).
ROLE_FAMILIES = {
    "stone": ["wall", "wall_alt", "floor", "ceiling", "step", "stone", "rock", "cliff", "path"],
    "wood": ["wood", "bark", "door", "frame", "post", "rail", "trim", "paper", "book"],
    "foliage": ["grass", "foliage", "flower", "cap", "field"],
    "ground": ["dirt", "sand", "snow", "ice", "water"],
    "metal": ["metal", "chrome", "hull", "hull_alt", "band"],
    "cloth": ["body", "body_alt", "cushion", "fabric", "knit", "fur", "quilt", "leather", "rope", "costume",
              "coat", "headwear"],
    "roof": ["roof"],
    "sky": ["sky", "view", "vista", "vista_far", "glass", "opening"],
    "emissive": ["light", "fire", "screen", "orb", "particle"],
    "skin": ["skin", "face"],
}
ROLE_FAMILY_SHIFT = {  # relative hue-rotation weight toward a mood (plan 2.5: shade/sky most, skin/wood least)
    "sky": 1.0, "stone": 0.7, "roof": 0.6, "ground": 0.5, "metal": 0.5, "foliage": 0.4, "cloth": 0.4,
    "wood": 0.25, "emissive": 0.0, "skin": 0.0,
}


# --------------------------------------------------------------------------------------------- helpers
def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rel(path):
    return Path(path).resolve().relative_to(R).as_posix()


def _pct(values, q):
    v = sorted(values)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 4)


def _probe_max_colours():
    from core.palette import Palette
    n = 1
    while n < 256:
        try:
            Palette(["#%06x" % (i * 4099) for i in range(n + 1)], ["c%d" % i for i in range(n + 1)])
        except ValueError:
            return n
        n += 1
    raise RuntimeError("palette limit probe found no limit")


def _probe_light_ramp_min():
    from core.packs import validate_pack_dict
    base = json.loads((PACKS_DIR / "medieval_village" / "pack.json").read_text(encoding='utf-8'))
    for n in range(1, 9):
        d = dict(base, light_ramp=base["palette_names"][:n])
        if not any("light_ramp" in e for e in validate_pack_dict(d)):
            return n
    raise RuntimeError("light ramp probe found no minimum")


def _probe_neon_cut():
    """Binary-search the HSV saturation and value cuts n64_gate.colour_stats counts as neon."""
    from adventure_maker import n64_gate as NG

    def neon(s, v):
        r, g, b = colorsys.hsv_to_rgb(0.0, s, v)
        px = bytes(int(round(c * 255)) for c in (r, g, b))
        return NG.colour_stats((1, 1, px))[1] > 0

    def first_true(fn):
        lo, hi = 0, 255
        while lo < hi:
            mid = (lo + hi) // 2
            if fn(mid / 255.0):
                hi = mid
            else:
                lo = mid + 1
        return lo / 255.0

    # value probed at full saturation; saturation probed at full value (8-bit grid, so +-1/255)
    return {"sat_min": round(first_true(lambda s: neon(s, 1.0)), 2), "val_min": round(first_true(lambda v: neon(1.0, v)), 2)}


def _is_neon(hexc, cut):
    r, g, b = (int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    _, s, v = colorsys.rgb_to_hsv(r, g, b)
    return s >= cut["sat_min"] - 1e-9 and v >= cut["val_min"] - 1e-9


def _shipped_packs():
    out = {}
    for d in sorted(PACKS_DIR.iterdir()):
        f = d / "pack.json"
        if f.is_file():
            out[d.name] = json.loads(f.read_text(encoding='utf-8'))
    return out


def _mesh_stats(asset):
    import numpy as np
    vs, tris, vol = [], 0, 0.0
    for n in asset.nodes:
        m = n.mesh
        v = np.asarray(m.v, dtype=float)
        if not len(v):
            continue
        vs.append(v)
        tris += m.tri_count()
        for f in m.f:  # signed volume by fan triangulation (closed parts count; open cards add ~0)
            a = v[f[0]]
            for i in range(1, len(f) - 1):
                vol += float(np.dot(a, np.cross(v[f[i]], v[f[i + 1]]))) / 6.0
    allv = np.concatenate(vs)
    ext = allv.max(0) - allv.min(0)
    box = float(max(ext[0], 1e-6) * max(ext[1], 1e-6) * max(ext[2], 1e-6))
    foot = float(max(ext[0], ext[1], 1e-6))
    return {"tris": int(tris), "largest_extent_m": float(ext.max()), "height_over_footprint": float(ext[2] / foot),
            "bbox_fill": float(min(abs(vol) / box, 1.0)), "nodes": len(asset.nodes)}


def measure_library():
    """Build every registered generator once at defaults in a pack that resolves it; return per-id stats."""
    from core import pipeline as PL
    reg = PL.load_generators()
    packs = _shipped_packs()
    rows = {}
    for gid, spec in sorted(reg.items()):
        order = sorted(packs, key=lambda pid: (gid not in packs[pid].get("kit_presets", {}), pid))
        for pid in order:
            try:
                P = PL.resolve(spec, PL.get_pack(pid))
                asset = spec.build(P, 0)
            except Exception:
                continue
            rows[gid] = dict(_mesh_stats(asset), cls=spec.cls, pack=pid)
            break
        else:
            rows[gid] = {"cls": spec.cls, "error": "no shipped pack resolves it"}
    return rows


# --------------------------------------------------------------------------------------------- export
def export(library=None):
    from core import packs as KP
    from validate import checks as C
    from adventure_maker import packs as AP
    from adventure_maker import style_gate as SG
    from adventure_maker import n64_gate as NG

    look = json.loads(LOOK.read_text(encoding='utf-8'))
    shipped = _shipped_packs()
    neon_cut = _probe_neon_cut()
    library = library if library is not None else measure_library()

    tex_sizes = sorted({m["texture"]["size"] for p in shipped.values() for m in p["materials"].values()
                        if isinstance(m.get("texture"), dict) and m["texture"].get("size")}
                       | set(look["texel_density"]["sizes"]))
    neon_share = max(sum(_is_neon(c, neon_cut) for c in p["palette"]) / len(p["palette"]) for p in shipped.values())
    kinds_used = sorted({m["kind"] for p in shipped.values() for m in p["materials"].values()})

    by_cls = {}
    for gid, row in library.items():
        if "error" not in row:
            by_cls.setdefault(row["cls"], []).append(row)
    silhouette = {}
    for cls, rows in sorted(by_cls.items()):
        silhouette[cls] = {"n": len(rows)}
        for k in ("tris", "largest_extent_m", "height_over_footprint", "bbox_fill", "nodes"):
            vals = [r[k] for r in rows]
            silhouette[cls][k] = [_pct(vals, 0.05), _pct(vals, 0.5), _pct(vals, 0.95)]
        budget = KP.CORE_CLASSES[cls]
        silhouette[cls]["budget_use_p50"] = round(silhouette[cls]["tris"][1] / budget, 3)

    refs = json.loads(REF_NUMBERS.read_text(encoding='utf-8'))
    g = refs["groups"]

    def med(group, key):
        return g[group]["stats"][key]["median"]

    sg = SG.CORE_DEFAULTS
    reference = {
        "source": [_rel(REF_NUMBERS), "tools/style_ref_measure.py"], "advisory": True,
        "groups_measured": {k: v["images_measured"] for k, v in g.items()},
        "fingerprints": {k: v["fingerprint"] for k, v in g.items()},
        "env": {k: g["env"]["stats"][k] for k in ("L_mean", "contrast_p95_p5", "chroma_mean", "flat", "edges",
                                                  "accent_cluster_share", "gradient_L_top_minus_bottom",
                                                  "ground_darkening_mid_minus_bottom")},
        "character": {k: g["character"]["stats"][k] for k in ("L_mean", "chroma_mean", "accent_cluster_share")},
        "brand": {k: g["brand"]["stats"][k] for k in ("L_mean", "chroma_mean", "accent_cluster_share")},
        "brand_hue_hist_30deg_oklab": g["brand"]["hue_hist_30deg_oklab"],
        "ratios": {
            "env_over_character_L_mean": round(med("env", "L_mean") / med("character", "L_mean"), 3),
            "env_over_character_chroma": round(med("env", "chroma_mean") / med("character", "chroma_mean"), 3),
            "env_accent_share_over_gate_max": round(med("env", "accent_cluster_share") / sg["accent_fraction_max"], 3),
            "brand_accent_share_over_gate_max": round(med("brand", "accent_cluster_share") / sg["accent_fraction_max"], 3),
        },
        "caveats": [
            "character group = character sheets and close-ups; light sheet backgrounds survive the uniform-edge "
            "trim, so env_over_character_L_mean > 1 here does not contradict 'environment darker than characters' "
            "in-game; read it as unmeasured until a cropped character set exists",
            "OKLab L and chroma, not the Rec.601 luma of style_gate: compare trends, never thresholds",
            "triangle use far below budget is a visual observation from the references and is NOT measurable from "
            "images; the measured library budget_use_p50 in silhouette is the comparable number",
        ],
    }

    return {
        "format": FORMAT,
        "generated_by": "tools/style_bible.py (never hand-edit; run `python3 -B -m tools.style_bible build`)",
        # ROOF's approved profiles are authored data, separate from this derived export.
        "budget_profiles": {
            "source": ["kits/core/room_budget_profiles.json"],
            "profiles": json.loads((R / "kits/core/room_budget_profiles.json").read_text(encoding='utf-8'))["budget_profiles"],
        },
        "palette": {
            "source": ["kits/core/packs.py:CORE_ROLES", "kits/core/packs.py:OPTIONAL_ROLES", "kits/core/packs.py:KINDS",
                       "kits/core/packs.py:TEXTURED_KINDS", "kits/core/palette.py:Palette (probed)",
                       "kits/core/packs.py:validate_pack_dict (probed)", "kits/packs/*/pack.json (neon share)",
                       "adventure_maker/n64_gate.py:colour_stats (probed neon cut)"],
            "core_roles": list(KP.CORE_ROLES), "optional_roles": dict(KP.OPTIONAL_ROLES),
            "material_kinds": list(KP.KINDS), "textured_kinds": list(KP.TEXTURED_KINDS),
            "material_kinds_in_shipped_packs": kinds_used,
            "max_colours": _probe_max_colours(), "light_ramp_min": _probe_light_ramp_min(),
            "neon_hsv": neon_cut,
            "neon_palette_share_max": round(neon_share, 4),
            "neon_palette_share_note": "highest share of neon-capable colours in any shipped pack (all pass the "
                                       "frame neon gate); a pack above it is refused",
        },
        "role_families": {"source": ["hand-written in tools/style_bible.py:ROLE_FAMILIES (REVIEW-NEEDED)"],
                          "families": ROLE_FAMILIES, "hue_shift_weight": ROLE_FAMILY_SHIFT},
        "budgets": {
            "source": ["kits/core/packs.py:CORE_CLASSES", "adventure_maker/packs.py:LIMITS",
                       "kits/validate/checks.py:TEX_LIMIT", "kits/core/n64_look.json:texel_density",
                       "kits/packs/*/pack.json (texture sizes in use)"],
            "triangles": dict(KP.CORE_CLASSES), "project_pack_limits": dict(AP.LIMITS),
            "texture_px_max": dict(C.TEX_LIMIT), "texture_sizes": tex_sizes,
            "texel_density": {k: v for k, v in look["texel_density"].items() if k != "note"},
        },
        "extents": {"source": ["kits/validate/checks.py:EXTENTS", "kits/validate/checks.py:NAME_RE",
                               "kits/validate/checks.py:NODE_RE"],
                    "largest_extent_m": {k: list(v) for k, v in C.EXTENTS.items()},
                    "name_re": C.NAME_RE.pattern, "node_re": C.NODE_RE.pattern},
        "light": {"source": ["kits/core/n64_look.json:lighting", "kits/core/n64_look.json:fog",
                             "kits/core/n64_look.json:environments"],
                  "lighting": _strip_notes(look["lighting"]), "fog": _strip_notes(look["fog"]),
                  "environments": {k: v["ranges"] for k, v in look["environments"].items()}},
        "material": {"source": ["kits/core/n64_look.json:bake", "kits/core/n64_look.json:textures",
                                "kits/core/n64_look.json:output"],
                     "bake": _strip_notes(look["bake"]), "textures": _strip_notes(look["textures"]),
                     "output": _strip_notes(look["output"])},
        "render_gates": {"source": ["adventure_maker/style_gate.py:CORE_DEFAULTS",
                                    "adventure_maker/n64_gate.py:thresholds()"],
                         "style_gate": dict(sg), "n64_gate": NG.thresholds(),
                         "mood_may_change": ["accent_hues"],
                         "mood_may_change_note": "plan 07 2.5: a mood pack may change hue identity (accent_hues, "
                                                 "palette families), never a quality threshold"},
        "silhouette": {"source": ["measured: every kits/core registered generator at defaults, seed 0, "
                                  "python mesh stats (tools/style_bible.py:measure_library)"],
                       "advisory": True, "percentiles": ["p5", "p50", "p95"],
                       "measured_generators": sum(1 for r in library.values() if "error" not in r),
                       "unmeasured": sorted(k for k, r in library.items() if "error" in r),
                       "bbox_fill_note": "mesh volume over bounding-box volume (plan proposed convex hull; bbox is "
                                         "the cheap proxy used here)",
                       "classes": silhouette},
        "reference": reference,
        "characters": {"source": [_rel(CHAR_STYLE)], "sha256": _sha(CHAR_STYLE),
                       "owner": "CHARS3 (character lanes)",
                       "rule": "face and proportion ratios are read from the character style file; never restated "
                               "here",
                       "keys": sorted(json.loads(CHAR_STYLE.read_text(encoding='utf-8')).keys())},
        "mood_vocabulary": {"source": ["hand-written in tools/style_bible.py (REVIEW-NEEDED)"],
                            "hue_words_hsv_deg": HUE_WORDS, "neutral_words": NEUTRAL_WORDS,
                            "time_words": TIME_WORDS, "weather_words": WEATHER_WORDS,
                            "value_keys_mean_luma": VALUE_KEYS, "tone_words": TONE_WORDS},
    }


def _strip_notes(d):
    if isinstance(d, dict):
        return {k: _strip_notes(v) for k, v in d.items() if k != "note"}
    return d


def dumps(doc):
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def load(path=OUT):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# --------------------------------------------------------------------------------------------- checks
def check_asset(bible, s):
    """s: {"cls", "tris", "largest_extent_m", optional "texture_sizes": {kind: [px]}, "emission",
    "point_lights", "material_kinds", "roles", "height_over_footprint", "bbox_fill"}.
    Returns {"ok", "errors": [...], "warnings": [...]}; errors are hard bible rules, warnings advisory."""
    err, warn = [], []
    cls = s.get("cls")
    tri = bible["budgets"]["triangles"]
    if cls not in tri:
        return {"ok": False, "errors": ["unknown class %r (have %s)" % (cls, sorted(tri))], "warnings": []}
    if s.get("tris", 0) > tri[cls]:
        err.append("budget: %d triangles > %d for %s" % (s["tris"], tri[cls], cls))
    lo, hi = bible["extents"]["largest_extent_m"][cls]
    ext = s.get("largest_extent_m")
    if ext is not None and not lo <= ext <= hi:
        err.append("extent: largest side %.2f m outside [%g, %g] for %s" % (ext, lo, hi, cls))
    limits, sizes = bible["budgets"]["texture_px_max"], bible["budgets"]["texture_sizes"]
    for kind, pxs in (s.get("texture_sizes") or {}).items():
        lim = limits.get(kind, limits["default"])
        for px in pxs:
            if px > lim or px not in sizes:
                err.append("texture: %d px for %s (allowed %s, max %d)" % (px, kind, sizes, lim))
    light = bible["light"]["lighting"]
    if s.get("emission", 0) > light["emission_max"]:
        err.append("emission %.2f > %.2f" % (s["emission"], light["emission_max"]))
    if s.get("point_lights", 0) > light["point_lights_max"]:
        err.append("point lights %d > %d" % (s["point_lights"], light["point_lights_max"]))
    for k in s.get("material_kinds", []):
        if k not in bible["palette"]["material_kinds"]:
            err.append("material kind %r not in the N64 kinds" % k)
    roles = set(bible["palette"]["core_roles"]) | set(bible["palette"]["optional_roles"])
    for r in s.get("roles", []):
        if r not in roles:
            err.append("role %r is not a palette role" % r)
    sil = bible["silhouette"]["classes"].get(cls)
    if sil:
        for k in ("height_over_footprint", "bbox_fill", "tris"):
            if k in s and s[k] is not None and not sil[k][0] <= s[k] <= sil[k][2]:
                warn.append("silhouette (advisory): %s %.3g outside library p5-p95 [%g, %g] for %s"
                            % (k, s[k], sil[k][0], sil[k][2], cls))
    return {"ok": not err, "errors": err, "warnings": warn}


def check_pack(bible, d):
    """Hard bible rules on a kit pack dict (kits/packs/<id>/pack.json shape)."""
    err, warn = [], []
    pal = bible["palette"]
    colours = d.get("palette", [])
    if len(colours) > pal["max_colours"]:
        err.append("palette: %d colours > %d" % (len(colours), pal["max_colours"]))
    if len(d.get("light_ramp", [])) < pal["light_ramp_min"]:
        err.append("light_ramp: fewer than %d steps" % pal["light_ramp_min"])
    if colours:
        share = sum(_is_neon(c, pal["neon_hsv"]) for c in colours) / len(colours)
        if share > pal["neon_palette_share_max"] + 1e-9:
            err.append("neon: %.0f%% of the palette is neon-capable (max %.1f%%)"
                       % (100 * share, 100 * pal["neon_palette_share_max"]))
    tex = bible["budgets"]
    dens = tex["texel_density"]
    role_cls = {r: (c, v["texels_per_m"]) for c, v in dens["classes"].items() for r in v["roles"]}
    for role, m in (d.get("materials") or {}).items():
        if m.get("kind") not in pal["material_kinds"]:
            err.append("material %s: kind %r not in the N64 kinds" % (role, m.get("kind")))
        t = m.get("texture")
        if not isinstance(t, dict) or not t.get("size"):
            continue
        kind = "view_plane" if m.get("kind") == "view_plane" else ("sky" if role == "sky" else "default")
        lim = tex["texture_px_max"].get(kind, tex["texture_px_max"]["default"])
        if t["size"] > lim or t["size"] not in tex["texture_sizes"]:
            err.append("material %s: texture %d px (allowed %s, max %d)" % (role, t["size"], tex["texture_sizes"], lim))
        if role in role_cls and m.get("tile_m"):
            got, want = t["size"] / m["tile_m"], role_cls[role][1]
            if abs(got - want) / want > dens["tolerance"]:
                err.append("material %s: %.1f texels/m, %s class wants %.2f +-%d%%"
                           % (role, got, role_cls[role][0], want, round(100 * dens["tolerance"])))
    return {"ok": not err, "errors": err, "warnings": warn}


def summarize_asset(asset, cls):
    """Mesh numbers of a built (in-memory) generator Asset in the check_asset summary shape."""
    s = _mesh_stats(asset)
    s["cls"] = cls
    s["roles"] = sorted({r for n in asset.nodes for r in (n.mesh.r or []) if isinstance(r, str)})
    return s


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "check"
    text = dumps(export())
    if cmd == "build":
        OUT.write_text(text, encoding='utf-8')
        print("wrote %s (%d bytes)" % (_rel(OUT), len(text)))
        return 0
    if cmd == "check":
        same = OUT.exists() and OUT.read_text(encoding='utf-8') == text
        print("style bible: %s" % ("up to date" if same else "DRIFTED (run build)"))
        return 0 if same else 1
    print("usage: python3 -B -m tools.style_bible build|check")
    return 2


if __name__ == "__main__":
    sys.exit(main())
