"""PLACEMAKER measurement: frames against the style bible's reference statistics, layout statistics, and the
approval store (place_approvals/<archetype>/<style>/<approval id>/).

Numbers only. Nothing here judges how a place looks; a score is "how many measured statistics sit inside the
reference p10..p90 band", and a distance is "how far these numbers are from the numbers of a recorded approval".

  frame_stats(png)                    -> dict of statistics (refpack measure, same as tools.style_ref_measure)
  band_score(stats)                   -> {"score", "in_band", "out_of_band"} vs kits/core/style_ref_numbers.json env
  palette_vector(png) / palette_distance(a, b)
  approve(store, run_room_dir, ...)   -> writes an approval record (frames, plan hash, params, pack + mood)
  compare(store, archetype, style, frames, layout) -> nearest approvals with palette + layout distances
"""
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
if str(R) not in sys.path:
    sys.path.insert(0, str(R))

REF = R / "kits" / "core" / "style_ref_numbers.json"
STORE = R / "place_approvals"
APPROVAL_FORMAT = "hermes64-place-approval/1"
BAND_KEYS = ("L_mean", "contrast_p95_p5", "rms_contrast", "edges", "flat", "chroma_mean", "accent_cluster_share")
BAND_MIN = 0.5            # first number: at least half the statistics inside the reference band
LAYOUT_KEYS = ("density_per_10m2", "coverage")
PALETTE_MAX = 0.35        # first number: palette distance to an approval above this is reported as "far"


def ref_env():
    return json.loads(REF.read_text(encoding='utf-8'))["groups"]["env"]


def frame_stats(png):
    from tools.style_ref_measure import measure_one
    try:
        st = measure_one(png)
    except Exception as e:       # refpack refuses frames it cannot measure (e.g. 2 colours): that is a failure
        return {"measure_error": str(e)[:200]}
    st["hue_hist"] = st.pop("_hue_hist")
    return st


def band_score(stats, ref=None):
    ref = ref or ref_env()
    inside, outside = [], []
    for k in BAND_KEYS:
        b = ref["stats"][k]
        v = stats.get(k)
        if v is None:
            continue
        (inside if b["p10"] <= v <= b["p90"] else outside).append(k)
    n = len(inside) + len(outside)
    return {"score": round(len(inside) / float(n or 1), 3), "in_band": inside, "out_of_band": outside,
            "ok": n > 0 and len(inside) / float(n) >= BAND_MIN}


def _rgb(png):
    from PIL import Image
    import numpy as np
    im = Image.open(png).convert("RGB")
    im.thumbnail((160, 160))
    return np.asarray(im, dtype="float64") / 255.0


def palette_vector(png):
    """Colour distribution: 12 OKLab hue bins (chroma-weighted) + 8 lightness bins + a neutral share, each block
    normalised. Comparable across frames of any size."""
    import numpy as np
    a = _rgb(png)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * lin[..., 0] + 0.5363325363 * lin[..., 1] + 0.0514459929 * lin[..., 2]
    m = 0.2119034982 * lin[..., 0] + 0.6806995451 * lin[..., 1] + 0.1073969566 * lin[..., 2]
    s = 0.0883024619 * lin[..., 0] + 0.2817188376 * lin[..., 1] + 0.6299787005 * lin[..., 2]
    l, m, s = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    C = np.hypot(A, B)
    hue = (np.degrees(np.arctan2(B, A)) + 360.0) % 360.0
    chroma_w = np.clip(C - 0.02, 0, None)
    hh = np.histogram(hue, bins=12, range=(0, 360), weights=chroma_w)[0]
    lh = np.histogram(np.clip(L, 0, 1), bins=8, range=(0, 1))[0].astype("float64")
    neutral = float((C < 0.02).mean())
    hh = hh / (hh.sum() or 1.0)
    lh = lh / (lh.sum() or 1.0)
    return [round(float(x), 5) for x in hh] + [round(float(x), 5) for x in lh] + [round(neutral, 5)]


def palette_distance(u, v):
    """Total-variation style distance in 0..1: half the L1 of the hue block, half of the lightness block, and the
    neutral-share difference, averaged."""
    hu = 0.5 * sum(abs(a - b) for a, b in zip(u[:12], v[:12]))
    lu = 0.5 * sum(abs(a - b) for a, b in zip(u[12:20], v[12:20]))
    nu = abs(u[20] - v[20])
    return round((hu + lu + nu) / 3.0, 4)


def layout_distance(a, b):
    """Relative difference of density / coverage plus the zone-share L1 (0 = same layout statistics)."""
    parts = []
    for k in LAYOUT_KEYS:
        x, y = float(a.get(k, 0)), float(b.get(k, 0))
        parts.append(abs(x - y) / max(abs(x), abs(y), 1e-6))
    za, zb = a.get("zone_share", {}), b.get("zone_share", {})
    keys = sorted(set(za) | set(zb))
    parts.append(0.5 * sum(abs(za.get(k, 0) - zb.get(k, 0)) for k in keys))
    return round(sum(parts) / len(parts), 4)


def offpalette_share(png, palette_hex, tol=40.0):
    """Share of pixels farther than tol (sRGB 0..255 euclid) from every pack palette colour (an off-palette probe)."""
    import numpy as np
    a = _rgb(png) * 255.0
    pal = np.array([[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)] for h in palette_hex], dtype="float64")
    d = np.sqrt(((a[..., None, :] - pal[None, None, :, :]) ** 2).sum(-1)).min(-1)
    return round(float((d > tol).mean()), 4)


# ----------------------------------------------------------------------------------------------- approvals
def style_key(pack, mood):
    return "%s__%s" % (pack, mood)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def approve(store, archetype, params, plan_sha256, pack, mood, frames, layout, approved_by, note="",
            synthetic=False, extra=None):
    """Record an approval. approved_by is what the caller declares; the store does not verify who it was.
    synthetic=True marks test/demo records (never a human approval)."""
    if not approved_by or not str(approved_by).strip():
        raise ValueError("approve: --by is required (who approved it)")
    store = Path(store)
    frames = [Path(f) for f in frames]
    for f in frames:
        if not f.is_file():
            raise ValueError("approve: frame not found: %s" % f)
    aid = "%s-%s" % (plan_sha256[:12], hashlib.sha256(("".join(_sha(f) for f in frames)).encode()).hexdigest()[:8])
    d = store / archetype / style_key(pack, mood) / aid
    (d / "frames").mkdir(parents=True, exist_ok=True)
    rows = []
    for f in frames:
        dst = d / "frames" / f.name
        shutil.copyfile(f, dst)
        rows.append({"file": "frames/" + f.name, "sha256": _sha(dst), "palette": palette_vector(dst),
                     "stats": {k: v for k, v in frame_stats(dst).items() if k != "hue_hist"}})
    rec = {"format": APPROVAL_FORMAT, "id": aid, "archetype": archetype, "params": params,
           "plan_sha256": plan_sha256, "pack": pack, "mood": mood, "layout": layout, "frames": rows,
           "approved_by": str(approved_by), "synthetic": bool(synthetic), "note": note,
           "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "caveat": "recorded as declared by the caller; the store does not verify the approver"}
    if extra:
        rec.update(extra)
    (d / "approval.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding='utf-8')
    return rec, d


def approvals(store, archetype, style=None, include_synthetic=True):
    store = Path(store)
    root = store / archetype
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*/*/approval.json")):
        rec = json.loads(f.read_text(encoding='utf-8'))
        if style and style_key(rec["pack"], rec["mood"]) != style:
            continue
        if rec.get("synthetic") and not include_synthetic:
            continue
        rec["_dir"] = str(f.parent)
        out.append(rec)
    return out


def compare(store, archetype, frames, layout, pack=None, mood=None, include_synthetic=True):
    """Distances from this run (frames + layout stats) to every approval of the archetype (same style first)."""
    pv = [palette_vector(f) for f in frames]
    style = style_key(pack, mood) if pack and mood else None
    rows = []
    for rec in approvals(store, archetype, include_synthetic=include_synthetic):
        ap = [fr["palette"] for fr in rec["frames"]]
        if not ap or not pv:
            continue
        pd = min(palette_distance(a, b) for a in pv for b in ap)
        ld = layout_distance(layout, rec.get("layout") or {})
        rows.append({"approval": rec["id"], "style": style_key(rec["pack"], rec["mood"]),
                     "same_style": style == style_key(rec["pack"], rec["mood"]), "synthetic": rec.get("synthetic"),
                     "approved_by": rec.get("approved_by"), "palette_distance": pd, "layout_distance": ld,
                     "palette_far": pd > PALETTE_MAX, "params": rec.get("params")})
    rows.sort(key=lambda r: (not r["same_style"], r["palette_distance"] + r["layout_distance"]))
    return {"archetype": archetype, "approvals": len(rows), "nearest": rows[:5],
            "note": "distances are numbers, not a look verdict; an empty store means nothing is approved yet"}


def examples(store, archetype, include_synthetic=False):
    """Approved params/seeds for the skill's few-shot list (human records only by default)."""
    return [{"id": r["id"], "params": r["params"], "pack": r["pack"], "mood": r["mood"], "plan_sha256": r["plan_sha256"],
             "approved_by": r["approved_by"], "synthetic": r.get("synthetic", False)}
            for r in approvals(store, archetype, include_synthetic=include_synthetic)]
