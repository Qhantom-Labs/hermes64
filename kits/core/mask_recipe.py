"""Mask recipes (`hermes64-mask/1`): a texture slot's value as a small hand-written JSON drawing.

A texture SLOT is one named cell of a pack atlas (or one small standalone sheet) plus the pieces that show it; packs
declare their slots in `kits/packs/<pack>/slots.json` (`hermes64-texture-slots/1`, see `load_slots`). A slot VALUE is
a mask recipe: a grid (16, 32 or 64 columns; rows 8-64), up to three tones named from the slot's pack ramp, and an
ordered list of primitives drawn on top of a background tone:

    {"format": "hermes64-mask/1", "grid": 32, "rows": 16, "tones": ["dark", "white"], "background": 0,
     "prims": [{"op": "rect", "at": [2, 2], "size": [4, 4], "tone": 1},
               {"op": "disc", "at": [16, 8], "r": 5, "tone": 1},
               {"op": "poly", "points": [[0, 0], [8, 0], [4, 6]], "tone": 1},
               {"op": "stroke", "points": [[0, 15], [31, 15]], "width": 1, "tone": 1},
               {"op": "text5x7", "text": "OPEN 24", "at": [1, 4], "scale": 1, "tone": 1}]}

Rules (why: a slot value is untrusted data from a user, a premise or an overlay):
- closed fields, bounded sizes and counts (MAX_* below), numbers only where numbers belong;
- no image decoding and no file reference: a slot value is a recipe dict, never a path or a picture;
- rasterised with NO smoothing (pixel-centre tests: inside or not), drawn in order, later primitives on top;
- the raster becomes ramp steps of the slot's texture, inserted into the pack's own painted field before the pack's
  normal soften/quantize/colour steps (`bake_atlas`), so the cell is coloured and filtered like the rest of the kit;
- same recipe + same pack -> same bytes (no randomness, no clock, no environment).
"""
import hashlib
import json
import re

import numpy as np

FORMAT = "hermes64-mask/1"
SLOTS_FORMAT = "hermes64-texture-slots/1"
GRIDS = (16, 32, 64)
ROWS = (8, 16, 32, 64)
MAX_TONES = 3
MAX_PRIMS = 64
MAX_POINTS = 32
MAX_TEXT = 12
MAX_SCALE = 4
MAX_WIDTH = 8
MAX_BYTES = 8192
MAX_NAME = 64
TONE_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
SLOT_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TEXT_RE = re.compile(r"^[A-Z0-9 ]+$")
CLEAR = "clear"          # sheet slots may name a transparent tone

TOP_KEYS = {"format", "grid", "rows", "tones", "background", "prims", "name"}
OPS = {
    "rect": {"op", "at", "size", "tone"},
    "disc": {"op", "at", "r", "tone"},
    "poly": {"op", "points", "tone"},
    "stroke": {"op", "points", "width", "tone"},
    "text5x7": {"op", "text", "at", "scale", "tone"},
}
OPTIONAL = {"stroke": {"width"}, "text5x7": {"scale"}}

# 5 x 7 block capitals A-Z and 0-9 (rows top to bottom, '1' = dot). An ordinary dot-matrix alphabet.
FONT5X7 = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 10001 11001 10101 10011 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 10001 01010 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
}


class MaskError(ValueError):
    """Rejected recipe or slot declaration. `code` is a stable machine-readable reason."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _fail(code, message):
    raise MaskError(code, message)


def _num(v, where, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        _fail("mask_type", "%s must be a number" % where)
    if not lo <= v <= hi:
        _fail("mask_range", "%s=%r outside [%g, %g]" % (where, v, lo, hi))
    return float(v)


def _int(v, where, allowed=None, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, int):
        _fail("mask_type", "%s must be an integer" % where)
    if allowed is not None and v not in allowed:
        _fail("mask_range", "%s=%r not in %s" % (where, v, list(allowed)))
    if lo is not None and not lo <= v <= hi:
        _fail("mask_range", "%s=%r outside [%d, %d]" % (where, v, lo, hi))
    return v


def _point(v, where, g, r):
    if not isinstance(v, list) or len(v) != 2:
        _fail("mask_type", "%s must be [x, y]" % where)
    return (_num(v[0], where + "[0]", -g, 2 * g), _num(v[1], where + "[1]", -r, 2 * r))


def validate(recipe, tones_allowed=None):
    """Check a recipe against hermes64-mask/1 (and, when given, the slot's tone vocabulary). Returns a normalised
    copy (canonical key order); raises MaskError with a stable code."""
    if isinstance(recipe, str):
        _fail("slot_value_path", "a slot value is a mask recipe object, not a path or file name (%r)" % recipe[:40])
    if not isinstance(recipe, dict):
        _fail("mask_type", "a mask recipe is a JSON object")
    raw = json.dumps(recipe, sort_keys=True, separators=(",", ":"))
    if len(raw.encode()) > MAX_BYTES:
        _fail("mask_size", "recipe is %d bytes (limit %d)" % (len(raw.encode()), MAX_BYTES))
    extra = set(recipe) - TOP_KEYS
    if extra:
        _fail("mask_field", "unknown field(s) %s" % sorted(extra))
    if recipe.get("format") != FORMAT:
        _fail("mask_format", "format must be %r" % FORMAT)
    g = _int(recipe.get("grid"), "grid", GRIDS)
    r = _int(recipe.get("rows", g), "rows", ROWS)
    tones = recipe.get("tones")
    if not isinstance(tones, list) or not 1 <= len(tones) <= MAX_TONES:
        _fail("mask_tones", "tones must list 1-%d tone names" % MAX_TONES)
    for t in tones:
        if not isinstance(t, str) or not TONE_RE.match(t):
            _fail("mask_tones", "bad tone name %r" % (t,))
        if tones_allowed is not None and t not in tones_allowed:
            _fail("mask_off_ramp", "tone %r is not in this slot's ramp %s" % (t, sorted(tones_allowed)))
    if len(set(tones)) != len(tones):
        _fail("mask_tones", "duplicate tone names")
    nt = len(tones)
    bg = _int(recipe.get("background", 0), "background", lo=0, hi=nt - 1)
    prims = recipe.get("prims")
    if not isinstance(prims, list) or len(prims) > MAX_PRIMS:
        _fail("mask_prims", "prims must be a list of at most %d primitives" % MAX_PRIMS)
    name = recipe.get("name", "")
    if not isinstance(name, str) or len(name) > MAX_NAME or "/" in name or "\\" in name:
        _fail("mask_field", "name must be a short label (no path separators)")
    out = []
    for i, p in enumerate(prims):
        w = "prims[%d]" % i
        if not isinstance(p, dict):
            _fail("mask_type", w + " must be an object")
        op = p.get("op")
        if op not in OPS:
            _fail("mask_unknown_op", "%s: unknown primitive %r (known: %s)" % (w, op, sorted(OPS)))
        missing = OPS[op] - OPTIONAL.get(op, set()) - set(p)
        extra = set(p) - OPS[op]
        if missing or extra:
            _fail("mask_field", "%s %s: missing %s, unknown %s" % (w, op, sorted(missing), sorted(extra)))
        q = {"op": op, "tone": _int(p["tone"], w + ".tone", lo=0, hi=nt - 1)}
        if op == "rect":
            q["at"] = list(_point(p["at"], w + ".at", g, r))
            sz = p["size"]
            if not isinstance(sz, list) or len(sz) != 2:
                _fail("mask_type", w + ".size must be [w, h]")
            q["size"] = [_num(sz[0], w + ".size[0]", 0, 2 * g), _num(sz[1], w + ".size[1]", 0, 2 * r)]
        elif op == "disc":
            q["at"] = list(_point(p["at"], w + ".at", g, r))
            q["r"] = _num(p["r"], w + ".r", 0, 2 * max(g, r))
        elif op in ("poly", "stroke"):
            pts = p["points"]
            lo = 3 if op == "poly" else 2
            if not isinstance(pts, list) or not lo <= len(pts) <= MAX_POINTS:
                _fail("mask_points", "%s.points needs %d-%d points" % (w, lo, MAX_POINTS))
            q["points"] = [list(_point(v, "%s.points[%d]" % (w, k), g, r)) for k, v in enumerate(pts)]
            if op == "stroke":
                q["width"] = _num(p.get("width", 1), w + ".width", 0.5, MAX_WIDTH)
        else:
            text = p["text"]
            if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT or not TEXT_RE.match(text):
                _fail("mask_text", "%s.text must be 1-%d block capitals A-Z, 0-9 or spaces" % (w, MAX_TEXT))
            q["text"] = text
            q["at"] = list(_point(p["at"], w + ".at", g, r))
            q["scale"] = _int(p.get("scale", 1), w + ".scale", lo=1, hi=MAX_SCALE)
        out.append(q)
    norm = {"format": FORMAT, "grid": g, "rows": r, "tones": list(tones), "background": bg, "prims": out}
    if name:
        norm["name"] = name
    return norm


# ---------------------------------------------------------------- raster (no smoothing)
def _inside_poly(px, py, pts):
    inside = np.zeros(px.shape, dtype=bool)
    n = len(pts)
    for k in range(n):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % n]
        if y0 == y1:
            continue
        cross = ((y0 > py) != (y1 > py))
        xi = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
        inside ^= cross & (px < xi)
    return inside


def _near_segment(px, py, a, b, half):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll == 0:
        t = np.zeros(px.shape)
    else:
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / ll, 0.0, 1.0)
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2 <= half * half


def text_width(text, scale=1):
    return (len(text) * 6 - 1) * scale


def raster(recipe, tones_allowed=None):
    """Validated recipe -> (rows, grid) uint8 array of tone indices (0..len(tones)-1)."""
    rc = validate(recipe, tones_allowed)
    g, r = rc["grid"], rc["rows"]
    img = np.full((r, g), rc["background"], dtype=np.uint8)
    py, px = np.mgrid[0:r, 0:g].astype(np.float64)
    px += 0.5
    py += 0.5
    for p in rc["prims"]:
        op, tone = p["op"], p["tone"]
        if op == "rect":
            (x, y), (w, h) = p["at"], p["size"]
            m = (px >= x) & (px < x + w) & (py >= y) & (py < y + h)
        elif op == "disc":
            (cx, cy), rr = p["at"], p["r"]
            m = (px - cx) ** 2 + (py - cy) ** 2 <= rr * rr
        elif op == "poly":
            m = _inside_poly(px, py, p["points"])
        elif op == "stroke":
            m = np.zeros(px.shape, dtype=bool)
            pts = p["points"]
            for k in range(len(pts) - 1):
                m |= _near_segment(px, py, pts[k], pts[k + 1], p["width"] / 2.0)
        else:
            m = np.zeros(px.shape, dtype=bool)
            x0, y0 = p["at"]
            s = p["scale"]
            for ci, ch in enumerate(p["text"]):
                if ch == " ":
                    continue
                rows = FONT5X7[ch].split()
                for ry, row in enumerate(rows):
                    for rx, bit in enumerate(row):
                        if bit == "1":
                            cx = x0 + (ci * 6 + rx) * s
                            cy = y0 + ry * s
                            m |= (px >= cx) & (px < cx + s) & (py >= cy) & (py < cy + s)
        img[m] = tone
    return img


def fit(index_img, w, h):
    """Nearest-neighbour fit of a recipe raster to a w x h cell: integer up-scaling only, aspect must match."""
    r, g = index_img.shape
    if g > w or w % g or h % r or w // g != h // r:
        _fail("mask_cell_fit", "a %dx%d grid does not fit a %dx%d cell (integer scale, same aspect)" % (g, r, w, h))
    k = w // g
    return np.repeat(np.repeat(index_img, k, axis=0), k, axis=1)


def recipe_sha256(recipe):
    """Content hash of a recipe (canonical JSON of the validated form)."""
    return hashlib.sha256(json.dumps(validate(recipe), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- pack slot declarations
SLOT_KEYS = {"target", "role", "cell", "size", "ramp", "tones", "pieces", "consumer", "default", "note", "image"}
IMAGE_GRIDS = (32, 64, 128)


def validate_slots(doc, pack_id=None, pal_names=None, mat_ramp_len=None):
    """Check a pack's slots.json. Each slot is either
       atlas: {"target": "atlas", "role": <material role>, "cell": [x, y, w, h], "tones": {name: ramp step},
               "pieces": [piece ids], "default": "pack" | <recipe>}
       sheet: {"target": "sheet", "size": 16|32|64, "ramp": [palette names], "tones": {name: step | "clear"},
               "consumer": <runtime consumer id>, "default": "none" | <recipe>,
               "image": {"grids": [32, 64, 128]}}   # optional: an OVERLAY may fill it with a local picture
                                                    # (adventure_maker/overlay_image.py); atlas slots never take one"""
    if not isinstance(doc, dict) or doc.get("format") != SLOTS_FORMAT:
        _fail("slots_format", "slots file format must be %r" % SLOTS_FORMAT)
    if pack_id is not None and doc.get("pack") != pack_id:
        _fail("slots_format", "slots file names pack %r, expected %r" % (doc.get("pack"), pack_id))
    slots = doc.get("slots")
    if not isinstance(slots, dict) or not slots:
        _fail("slots_format", "slots must be a non-empty object")
    for sid, s in slots.items():
        if not SLOT_RE.match(sid) or not isinstance(s, dict):
            _fail("slots_format", "bad slot %r" % sid)
        extra = set(s) - SLOT_KEYS
        if extra:
            _fail("slots_format", "slot %s: unknown field(s) %s" % (sid, sorted(extra)))
        tones = s.get("tones")
        if not isinstance(tones, dict) or not tones or not all(TONE_RE.match(k) for k in tones):
            _fail("slots_format", "slot %s: tones must map tone names to ramp steps" % sid)
        if s.get("target") == "atlas":
            cell = s.get("cell")
            if not (isinstance(cell, list) and len(cell) == 4 and all(isinstance(v, int) and v >= 0 for v in cell)):
                _fail("slots_format", "slot %s: cell must be [x, y, w, h] texels" % sid)
            if not isinstance(s.get("role"), str):
                _fail("slots_format", "slot %s: role names the material whose atlas holds the cell" % sid)
            for k, v in tones.items():
                if not isinstance(v, int) or v < 0 or (mat_ramp_len and v >= mat_ramp_len(s["role"])):
                    _fail("slots_format", "slot %s: tone %s step %r is not on the %s ramp" % (sid, k, v, s["role"]))
            pieces = s.get("pieces", [])
            if not isinstance(pieces, list) or not all(isinstance(p, str) for p in pieces):
                _fail("slots_format", "slot %s: pieces must list piece ids" % sid)
            d = s.get("default", "pack")
            if "image" in s:
                _fail("slots_format", "slot %s: atlas slots take mask recipes only (image is for sheet slots)" % sid)
        elif s.get("target") == "sheet":
            _int(s.get("size"), "slot %s size" % sid, GRIDS)
            ramp = s.get("ramp")
            if not isinstance(ramp, list) or not ramp or (pal_names and any(n not in pal_names for n in ramp)):
                _fail("slots_format", "slot %s: ramp must list palette names of this pack" % sid)
            for k, v in tones.items():
                if v != CLEAR and (not isinstance(v, int) or not 0 <= v < len(ramp)):
                    _fail("slots_format", "slot %s: tone %s step %r is not on its ramp" % (sid, k, v))
            if not isinstance(s.get("consumer"), str):
                _fail("slots_format", "slot %s: consumer names the runtime feature that shows the sheet" % sid)
            d = s.get("default", "none")
            img = s.get("image")
            if img is not None and not (isinstance(img, dict) and set(img) == {"grids"} and isinstance(img["grids"], list)
                                        and img["grids"] and all(v in IMAGE_GRIDS for v in img["grids"])):
                _fail("slots_format", "slot %s: image must be {\"grids\": [subset of %s]}" % (sid, list(IMAGE_GRIDS)))
        else:
            _fail("slots_format", "slot %s: target must be 'atlas' or 'sheet'" % sid)
        if isinstance(d, dict):
            validate(d, set(tones))
        elif d not in ("pack", "none"):
            _fail("slots_format", "slot %s: default must be 'pack', 'none' or a recipe" % sid)
    return doc


# ---------------------------------------------------------------- bake
def _steps_field(index_img, tone_names, tonemap, ramp_len):
    lv = np.array([tonemap[t] for t in tone_names], dtype=np.float64) / max(1, ramp_len - 1)
    return lv[index_img]


def bake_atlas(spec_texture, pal, pack_id, role, fills):
    """The pack's own make_texture for `role`, with slot cells replaced by recipe rasters BEFORE the pack's soften /
    dither / quantize. fills: list of (cell [x, y, w, h], recipe, tonemap). With no fills the bytes equal the pack's
    normal texture (tested)."""
    from . import texgen as T
    from .palette import quantize_field
    from .pipeline import load_generators
    load_generators()           # every kit's painters registered, as in the kit build
    recipe = spec_texture
    gen = recipe["gen"]
    if gen in ("env", "scene"):
        _fail("slots_format", "role %s is painted by %r, which has no atlas cells" % (role, gen))
    n = int(recipe.get("size", 32))
    f = T.field(gen, n, recipe, pack_id, role)
    ramp_len = len(recipe["ramp"])
    for cell, rc, tonemap in fills:
        x, y, w, h = cell
        if x + w > f.shape[1] or y + h > f.shape[0]:
            _fail("mask_cell_fit", "cell %s outside the %dx%d %s atlas" % (cell, f.shape[1], f.shape[0], role))
        idx = fit(raster(rc, set(tonemap)), w, h)
        f[y:y + h, x:x + w] = _steps_field(idx, validate(rc)["tones"], tonemap, ramp_len)
    tx = T.convention_textures()
    passes = int(recipe.get("soften", tx.get("soften_gens", {}).get(gen, tx.get("soften", 0))))
    if passes:
        f = T.soften(f, passes)
    ramp = pal.ramp_rgb(recipe["ramp"])
    dither = T.recipe_dither(recipe)
    if gen in tx.get("crisp_gens", []) and "dither" not in recipe:
        dither = False
    thr = None
    pattern = recipe.get("dither_pattern", tx.get("dither_pattern", "bayer"))
    if dither and pattern == "mottle":
        thr = T.mottle_thresholds(T._rs("mottle", pack_id, role), f.shape[0], f.shape[1], int(tx.get("mottle_clump", 1)))
    return quantize_field(f, ramp, dither=dither, thresholds=thr)


def bake_sheet(slot, recipe, pal):
    """A standalone slot sheet (size x size RGBA): recipe tones -> the slot's palette ramp colours, 'clear' -> alpha 0.
    No smoothing, no dither (the consumer shows it as a crisp emblem)."""
    size = int(slot["size"])
    tonemap = slot["tones"]
    rc = validate(recipe, set(tonemap))
    idx = fit(raster(rc), size, size * rc["rows"] // rc["grid"])
    ramp = [tuple(int(c) for c in rgb) for rgb in pal.ramp_rgb(slot["ramp"])]
    lut = np.zeros((len(rc["tones"]), 4), dtype=np.uint8)
    for i, t in enumerate(rc["tones"]):
        v = tonemap[t]
        lut[i] = (0, 0, 0, 0) if v == CLEAR else ramp[v] + (255,)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    img = lut[idx]
    out[:img.shape[0], :img.shape[1]] = img
    return out


def same_bytes_twice(fn):
    """Determinism check used by the bake and its tests: run fn() twice, compare bytes. Returns (ok, sha_a, sha_b)."""
    a, b = fn(), fn()
    ha, hb = hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest()
    return ha == hb, ha, hb
