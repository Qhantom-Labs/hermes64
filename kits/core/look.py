"""Look continuity: does a SET of textures built in one pack (base or mood-derived) keep the house look?

Measured per texture and over the set, against the pack and (optionally) the same roles painted in the base pack:

  palette adherence   share of texels whose colour is (within 2/255 per channel) a colour of the pack palette;
                      textures are palette-exact by convention (texgen.make_texture), so anything else is foreign
  value range         luma p5..p95 span; against the base texture of the same role the span keeps 60-160%
                      (same value structure), and the set's median span stays within 70-140% of the base set
  crispness           per-texel high-frequency energy (the n64_gate library measure: mean |L - wrapped 3x3 blur|)
                      <= n64_look gate.library.hf_energy_max, and <= 1.6x base + .01 for the same role; one-pixel
                      hard edge share (strong luma step done in one texel) <= ONE_PX_EDGE_MAX (screens/paper/book
                      exempt, as in the n64 gate)
  texel density       texels per metre = texture width / material tile_m, grouped by n64_look texel_density class:
                      every class inside the set within gate.library.density_spread_max, and within the bible
                      tolerance of the class target

All thresholds are read from kits/core/n64_look.json / style_bible.json except the three ratios marked here, which
are first numbers set so the shipped packs pass and the known-bad controls fail (tests/test_mood.py).
"""
import json
import os

import numpy as np

from . import png
from .palette import Palette

HERE = os.path.dirname(os.path.abspath(__file__))
SPAN_KEEP = (0.6, 1.6)        # per-texture value span vs the base texture of the same role
SET_SPAN_KEEP = (0.7, 1.4)    # set median span vs base set median span
HF_VS_BASE = 1.6              # per-texture hf energy may grow at most this factor (+ .01) over the base texture
ONE_PX_EDGE_MAX = 0.85        # share of strong edges that step in one texel (non-exempt roles; shipped max .76)
BASE_STRONG_MIN = 24          # strong edges the base texture needs before its one-texel share is compared
ONE_PX_VS_BASE = 0.12         # ... and at most this much above the base texture of the same role
ADHERENCE_MIN = 0.98          # per-texture share of palette-exact texels
SKIP_GENS = ("env", "scene")  # painted env spheres and sky cards are not tiling textures


def _conv():
    with open(os.path.join(HERE, "n64_look.json"), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def luma(img):
    a = img[..., :3].astype(np.float64) / 255.0
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def hf_energy(img):
    """Same measure as adventure_maker.n64_gate.texture_hf_energy (wrapped 3x3 box blur), vectorised."""
    L = luma(img)
    s = sum(np.roll(np.roll(L, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
    return float(np.mean(np.abs(L - s)))


def one_px_edges(img, strong=0.2):
    """Share of strong luma changes over 3 texels (wrapped) that happen in one texel step."""
    L = luma(img)
    tot = one = 0
    for ax in (0, 1):
        d1 = np.abs(np.roll(L, -1, ax) - L)
        d3 = np.abs(np.roll(L, -2, ax) - np.roll(L, 1, ax))
        m = d3 >= strong
        tot += int(m.sum())
        one += int((m & (d1 >= 0.85 * d3)).sum())
    return (one / tot) if tot else 0.0, tot


def adherence(img, pal_hex):
    px = img[..., :3].reshape(-1, 3).astype(np.int64)
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in pal_hex], dtype=np.int64)
    d = np.abs(px[:, None, :] - pal[None, :, :]).max(-1).min(-1)
    return float(np.mean(d <= 2))


def span(img):
    L = luma(img).ravel()
    return float(np.percentile(L, 95) - np.percentile(L, 5)), float(np.mean(L))


def role_class(conv, role):
    for cls, spec in conv.get("texel_density", {}).get("classes", {}).items():
        if role in spec.get("roles", []):
            return cls, float(spec.get("texels_per_m", 0))
    return None, None


def paint_pack_textures(pack_dict, roles=None):
    """Paint every textured role of a pack in memory with the real generators: {role: image}."""
    from .texgen import make_texture
    from .pipeline import load_generators
    load_generators()            # kit modules register their texture generators (mk_*, hazard, ...) on import
    pal = Palette(pack_dict["palette"], pack_dict["palette_names"])
    out = {}
    for role, m in sorted(pack_dict["materials"].items()):
        t = m.get("texture")
        if not isinstance(t, dict) or t.get("gen") in SKIP_GENS or "ramp" not in t:
            continue
        if roles and role not in roles:
            continue
        out[role] = make_texture(t, pal, pack_dict.get("texture_seed", pack_dict["id"]), role)
    return out


def measure(img, role, pack_dict, conv=None):
    conv = conv or _conv()
    m = pack_dict["materials"].get(role, {})
    sp, mean = span(img)
    e1, strong = one_px_edges(img)
    cls, want = role_class(conv, role)
    tile = float(m.get("tile_m", 1.0))
    return {"role": role, "size": [int(img.shape[1]), int(img.shape[0])], "adherence": round(adherence(img, pack_dict["palette"]), 4),
            "span": round(sp, 4), "mean_luma": round(mean, 4), "hf_energy": round(hf_energy(img), 5),
            "one_px_edges": round(e1, 4), "strong_edges": strong, "class": cls,
            "texels_per_m": round(img.shape[1] / tile, 3) if tile > 0 else None, "class_target": want}


def continuity(textures, pack_dict, base_textures=None, base_pack=None, conv=None):
    """textures: {role: image} built in pack_dict; base_textures: {role: image} of the same roles in the base pack.
    Returns {ok, errors, per_texture, set}."""
    conv = conv or _conv()
    lib = conv.get("gate", {}).get("library", {})
    exempt = set(lib.get("hf_exempt_roles", []))
    tol = float(conv.get("texel_density", {}).get("tolerance", 0.25))
    err, rows = [], {}
    base_rows = {}
    for role, img in sorted(textures.items()):
        r = measure(img, role, pack_dict, conv)
        rows[role] = r
        if r["adherence"] < ADHERENCE_MIN:
            err.append("%s: off-palette texture (%.0f%% palette texels, min %.0f%%)" % (role, 100 * r["adherence"], 100 * ADHERENCE_MIN))
        if role not in exempt:
            if r["hf_energy"] > lib.get("hf_energy_max", 1e9):
                err.append("%s: over-crisp / noisy texture (hf energy %.3f > %.3f)" % (role, r["hf_energy"], lib["hf_energy_max"]))
            if r["one_px_edges"] > ONE_PX_EDGE_MAX and r["strong_edges"] >= 8:
                err.append("%s: over-crisp texture (%.0f%% of strong edges step in one texel, max %.0f%%)" % (
                    role, 100 * r["one_px_edges"], 100 * ONE_PX_EDGE_MAX))
        if base_textures and role in base_textures:
            b = measure(base_textures[role], role, base_pack or pack_dict, conv)
            base_rows[role] = b
            if b["span"] > 0.02:
                k = r["span"] / b["span"]
                r["span_vs_base"] = round(k, 3)
                if not SPAN_KEEP[0] <= k <= SPAN_KEEP[1]:
                    err.append("%s: value structure changed (span %.0f%% of base, keep %d-%d%%)" % (
                        role, 100 * k, 100 * SPAN_KEEP[0], 100 * SPAN_KEEP[1]))
            # relative crispness only where the base texture has enough strong edges to measure a share
            if role not in exempt and b["strong_edges"] >= BASE_STRONG_MIN and \
                    r["one_px_edges"] > b["one_px_edges"] + ONE_PX_VS_BASE and r["strong_edges"] >= 8:
                err.append("%s: crisper edges than the base texture (%.0f%% vs %.0f%% one-texel steps)" % (
                    role, 100 * r["one_px_edges"], 100 * b["one_px_edges"]))
            if role not in exempt and r["hf_energy"] > HF_VS_BASE * b["hf_energy"] + 0.01:
                err.append("%s: crisper than the base texture (hf %.3f vs %.3f)" % (role, r["hf_energy"], b["hf_energy"]))
    # density per class
    by_cls = {}
    for role, r in rows.items():
        if r["class"] and r["texels_per_m"]:
            by_cls.setdefault(r["class"], {})[role] = r["texels_per_m"]
            if r["class_target"] and abs(r["texels_per_m"] - r["class_target"]) / r["class_target"] > tol + 1e-9:
                err.append("%s: texel density %.1f/m, %s class wants %.2f +-%d%%" % (
                    role, r["texels_per_m"], r["class"], r["class_target"], round(100 * tol)))
    spread = {}
    for cls, vals in sorted(by_cls.items()):
        spread[cls] = round(max(vals.values()) / min(vals.values()), 3)
        if spread[cls] > lib.get("density_spread_max", 1e9) + 1e-9:
            err.append("mixed texel density in class %s: %.2fx (max %.2fx): %s" % (
                cls, spread[cls], lib["density_spread_max"], ", ".join("%s %.0f" % kv for kv in sorted(vals.items()))))
    spans = sorted(r["span"] for r in rows.values())
    st = {"textures": len(rows), "median_span": spans[len(spans) // 2] if spans else 0.0,
          "median_hf": sorted(r["hf_energy"] for r in rows.values())[len(rows) // 2] if rows else 0.0,
          "min_adherence": min((r["adherence"] for r in rows.values()), default=1.0), "density_spread": spread}
    if base_rows:
        bs = sorted(r["span"] for r in base_rows.values())
        st["base_median_span"] = bs[len(bs) // 2]
        if st["base_median_span"] > 0:
            k = st["median_span"] / st["base_median_span"]
            st["median_span_vs_base"] = round(k, 3)
            if not SET_SPAN_KEEP[0] <= k <= SET_SPAN_KEEP[1]:
                err.append("set value range changed: median span %.0f%% of the base set" % (100 * k))
    if st["median_hf"] > lib.get("hf_energy_median_max", 1e9):
        err.append("set median texture energy %.3f > %.3f" % (st["median_hf"], lib["hf_energy_median_max"]))
    return {"ok": not err, "errors": err, "per_texture": rows, "set": st}


def read_textures(folder, pack_id, roles=None):
    """Textures a build wrote (tex_<pack>_<role>.png) -> {role: image}."""
    out = {}
    pre = "tex_%s_" % pack_id
    for name in sorted(os.listdir(folder)):
        if name.startswith(pre) and name.endswith(".png"):
            role = name[len(pre):-4]
            if roles is None or role in roles:
                out[role] = png.read(os.path.join(folder, name))
    return out
