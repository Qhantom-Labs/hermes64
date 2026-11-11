"""DUNGEONKIT painted field generators (additive, theme-agnostic; registered into texgen.FIELD_GENS).

N64-era stone, cave, relief and water surfaces painted by code. Every generator returns a tileable float field in
[0, 1] (row 0 = TOP of the image) that texgen.make_texture maps onto the recipe ramp with the shared N64 convention
(mottle quantization). Two painting rules keep the textures painted rather than noisy (n64_gate library hf energy):

- structured features (mortar, bevel highlights, glyph strokes, sigil rings) sit EXACTLY on ramp steps, so the mottle
  threshold never flips them (quantize_field: floor(k + t) == k);
- only broad painted variation (block tone, low-frequency blotches) lies between steps and mottles softly.

Segmented ramps: a recipe may concatenate two hue families in one ramp (e.g. 5 stone steps + 3 moss steps) and declare
`segments: [5, 3]`. A generator then paints each texel inside ONE segment only (values strictly within a segment's step
range), so dithering never mixes the hue families: moss stays moss, stone stays stone.
No colour, theme or palette word lives here: generators see step levels only.
"""
import math

import numpy as np

from . import texgen as T


# ---------------------------------------------------------------- helpers
def _nr(p, default):
    return int(p.get("ramp_len", len(p.get("ramp") or []) or default))


def _segs(p):
    """[(first_step, count), ...] for the recipe's ramp segments (default: one segment = whole ramp)."""
    n = _nr(p, 5)
    segs = p.get("segments") or [n]
    out, k = [], 0
    for c in segs:
        out.append((k, int(c)))
        k += int(c)
    if k != n:
        raise ValueError("ramp segments %r do not cover the %d-colour ramp" % (segs, n))
    return out, n


def _lv(step, n):
    """Field value of ramp step `step` (exact)."""
    return float(step) / max(1, n - 1)


def _in_seg(f01, seg, n, lo=0.0, hi=1.0):
    """Map a 0..1 field into segment `seg` = (first, count), limited to the sub-range [lo, hi] of its steps."""
    first, count = seg
    a = first + lo * (count - 1)
    b = first + hi * (count - 1)
    return (a + (b - a) * np.clip(f01, 0.0, 1.0)) / max(1, n - 1)


def _snap(f, n):
    """Round a field to exact ramp steps (crisp painted strokes)."""
    return np.round(np.clip(f, 0, 1) * (n - 1)) / max(1, n - 1)


def _hash01(*ints):
    h = 2166136261
    for v in ints:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h / 4294967295.0


# ---------------------------------------------------------------- cut stone courses
def g_ashlar(rs, n, p):
    """Cut-stone wall courses: `rows` courses per tile of varying height, irregular block lengths (`cols` blocks per
    course on average), dark mortar, a one-texel lit edge on the top/left of each block and a shaded lip on its
    bottom/right, a distinct painted tone per block plus soft blotches. Optional `moss` (needs a second ramp segment)
    creeps out of the lower mortar; `chips` paints knocked corners. Mortar = step 0; bodies within the stone segment."""
    segs, nr = _segs(p)
    stone = segs[0]
    rows = int(p.get("rows", 4))
    cols = float(p.get("cols", 2.0))
    u, v = T._grid(n)
    yy, xx = np.mgrid[0:n, 0:n]
    # course boundaries in texel rows (varying heights, tileable)
    hts = 0.75 + 0.5 * rs.random(rows)
    edges = np.concatenate([[0.0], np.cumsum(hts / hts.sum())]) * n
    edges = np.round(edges).astype(int)
    course = np.searchsorted(edges, yy, side="right") - 1
    course = np.clip(course, 0, rows - 1)
    top_px = yy - edges[course]
    bot_px = edges[course + 1] - 1 - yy
    joints = []
    for k in range(rows):
        m = max(1, int(round(cols + (rs.random() - 0.5) * 1.2)))
        w = 0.55 + rs.random(m)
        c = np.concatenate([[0.0], np.cumsum(w / w.sum())])[:-1]
        joints.append(np.sort(np.round(((c + rs.random()) % 1.0) * n).astype(int) % n))
    levels = rs.random((rows, 12))
    blot = T._norm(T.fbm(rs, n, 3, 2))
    body_lo, body_hi = float(p.get("body_lo", 0.3)), float(p.get("body_hi", 0.85))
    mort = int(p.get("mortar", 1))
    f = np.zeros((n, n))
    for k in range(rows):
        sel = course == k
        jj = joints[k]
        x = xx[sel]
        idx = np.searchsorted(jj, x, side="right") - 1          # block index (-1 = wraps to the last block)
        left = np.where(idx < 0, jj[-1] - n, jj[np.maximum(idx, 0)])
        nxt = np.where(idx + 1 < len(jj), jj[np.minimum(idx + 1, len(jj) - 1)], jj[0] + n)
        nxt = np.where(idx < 0, jj[0], nxt)
        along = x - left
        to_right = nxt - 1 - x
        bid = (idx % len(jj)) % 12
        t = levels[k, bid]
        val = body_lo + (body_hi - body_lo) * (0.62 * t + 0.38 * blot[sel])
        tp, bp = top_px[sel], bot_px[sel]
        lit = (tp == mort) | (along == mort)
        shade = (bp == 0) | (to_right == 0)
        val = np.where(lit, np.minimum(1.0, val + 0.25), val)
        val = np.where(shade, np.maximum(0.1, val - 0.28), val)
        fv = _in_seg(val, stone, nr)
        mortar = (tp < mort) | (along < mort)
        fv = np.where(mortar, _lv(stone[0], nr), fv)
        f[sel] = fv
    if p.get("chips"):
        f1, f2, ids = T._cells(rs, n, int(p.get("chip_cells", 9)))
        chip = (f1 < 0.03 * float(p["chips"]))
        f = np.where(chip, _lv(stone[0] + 1, nr), f)
    if p.get("moss") and len(segs) > 1:
        moss = segs[1]
        m = T._norm(T.fbm(rs, n, 4, 3)) + 0.55 * (1.0 - v) - 0.35           # lower courses (v small = bottom)
        mortar_near = f <= _lv(stone[0], nr) + 1e-9
        grow = (m > 1.0 - float(p["moss"])) & (mortar_near | (m > 1.12 - 0.6 * float(p["moss"])))
        mv = _in_seg(T._norm(T.fbm(rs, n, 6, 2)), moss, nr, 0.0, 1.0)
        f = np.where(grow, mv, f)
    return np.clip(f, 0, 1)


def g_flagstone(rs, n, p):
    """Irregular flagstone floor: jittered-grid Worley stones, dark joints, a painted lit rim on the upper-left of each
    stone, broad per-stone tone and worn soft centres. Optional `moss` creeps in the joints (second segment)."""
    segs, nr = _segs(p)
    stone = segs[0]
    k = int(p.get("cells", 5))
    u, v = T._grid(n)
    pts = []
    for j in range(k):
        for i in range(k):
            pts.append(((i + 0.2 + 0.6 * rs.random()) / k, (j + 0.2 + 0.6 * rs.random()) / k))
    pts = np.array(pts)
    best1 = np.full((n, n), 9.0)
    best2 = np.full((n, n), 9.0)
    ids = np.zeros((n, n), dtype=int)
    gx = np.zeros((n, n))
    gy = np.zeros((n, n))
    for i, (px, py) in enumerate(pts):
        dx = u - px
        dx = dx - np.round(dx)
        dy = v - py
        dy = dy - np.round(dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < best1
        best2 = np.where(closer, best1, np.minimum(best2, d))
        ids = np.where(closer, i, ids)
        gx = np.where(closer, dx, gx)
        gy = np.where(closer, dy, gy)
        best1 = np.where(closer, d, best1)
    tone = rs.random(len(pts))
    edge = best2 - best1
    gap = float(p.get("gap", 0.028))
    blot = T._norm(T.fbm(rs, n, 3, 2))
    body = float(p.get("body_lo", 0.3)) + (float(p.get("body_hi", 0.8)) - float(p.get("body_lo", 0.3))) * (0.6 * tone[ids] + 0.4 * blot)
    # rim light toward the upper-left of each stone, shade toward the lower-right (painted relief)
    rim = (edge < gap * 2.6) & (edge >= gap)
    lit = (gx < 0) & (gy > 0)
    body = np.where(rim & lit, np.minimum(1.0, body + 0.22), body)
    body = np.where(rim & ~lit, np.maximum(0.1, body - 0.25), body)
    f = _in_seg(body, stone, nr)
    f = np.where(edge < gap, _lv(stone[0], nr), f)
    if p.get("moss") and len(segs) > 1:
        moss = segs[1]
        m = T._norm(T.fbm(rs, n, 3, 3))
        grow = (edge < gap * 1.8) & (m > 1.0 - float(p["moss"]))
        f = np.where(grow, _in_seg(m, moss, nr, 0.0, 0.8), f)
    return np.clip(f, 0, 1)


def _warped_cells(rs, n, count, warp):
    """Tileable Worley on domain-warped coordinates: organic cells with wandering (not straight) borders."""
    u, v = T._grid(n)
    wu = (T._norm(T.fbm(rs, n, 2, 2)) - 0.5) * warp
    wv = (T._norm(T.fbm(rs, n, 2, 2)) - 0.5) * warp
    uu, vv = (u + wu) % 1.0, (v + wv) % 1.0
    pts = rs.random((count, 2))
    b1 = np.full((n, n), 9.0)
    b2 = np.full((n, n), 9.0)
    ids = np.zeros((n, n), dtype=int)
    for i, (px, py) in enumerate(pts):
        dx = uu - px
        dx = dx - np.round(dx)
        dy = vv - py
        dy = dy - np.round(dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < b1
        b2 = np.where(closer, b1, np.minimum(b2, d))
        ids = np.where(closer, i, ids)
        b1 = np.where(closer, d, b1)
    return b1, b2, ids


def g_cavestone(rs, n, p):
    """Organic cave rock: soft rounded lumps (domain-warped Worley, bright centres falling off to their rims), slanted
    strata, dark meandering crevices and broad painted blotches. Optional `wet` darkens streaks running down,
    `moss` fills the lowest hollows (second ramp segment)."""
    segs, nr = _segs(p)
    stone = segs[0]
    f1, f2, ids = _warped_cells(rs, n, int(p.get("cells", 6)), float(p.get("warp", 0.18)))
    span = np.maximum(f2, 1e-6)
    lump = np.clip(1.0 - f1 / span, 0, 1) ** 0.8
    u, v = T._grid(n)
    strata = 0.5 + 0.5 * np.sin((v * float(p.get("strata", 3)) + 0.25 * u + 0.3 * T._norm(T.fbm(rs, n, 2, 2))) * 2 * math.pi)
    blot = T._norm(T.fbm(rs, n, 3, 3))
    tone = rs.random(ids.max() + 1)[ids]
    body = T._norm(0.5 * lump + 0.12 * strata + 0.2 * blot + 0.18 * tone)
    crev = (f2 - f1) < float(p.get("crevice", 0.022)) * (0.6 + 0.8 * blot)
    f = _in_seg(body, stone, nr, 0.2, 1.0)
    f = np.where(crev, _lv(stone[0], nr), f)
    if p.get("wet"):
        streak = T._norm(T.fbm(rs, n, 6, 2, sx=4.0, sy=0.4))
        wetm = streak > 1.0 - float(p["wet"])
        f = np.where(wetm & ~crev, np.maximum(_lv(stone[0], nr), f - 1.0 / max(1, nr - 1)), f)
    if p.get("moss") and len(segs) > 1:
        moss = segs[1]
        grow = (lump < float(p["moss"])) & ~crev & (blot > 0.4)
        f = np.where(grow, _in_seg(blot, moss, nr, 0.0, 1.0), f)
    return np.clip(f, 0, 1)


def g_vault(rs, n, p):
    """Rough vault / ceiling stone: large soft blocks barely jointed, mostly dark, broad blotches (reads as stone that
    sinks into the dark above the torches)."""
    segs, nr = _segs(p)
    stone = segs[0]
    rows = int(p.get("rows", 2))
    u, v = T._grid(n)
    yy = (1 - v) * rows
    r = np.floor(yy).astype(int)
    shift = np.where(r % 2 == 1, 0.5, 0.0)
    uu = (u + shift) % 1.0
    c = np.floor(uu * int(p.get("cols", 2))).astype(int)
    tone = rs.random((rows + 1, 8))[r % rows, c % 8]
    blot = T._norm(T.fbm(rs, n, 3, 3))
    body = 0.25 + 0.4 * tone + 0.35 * blot
    fy = yy - np.floor(yy)
    fu = (uu * int(p.get("cols", 2))) % 1.0
    joint = (fy < 1.0 * rows / n) | (fu < 1.0 * int(p.get("cols", 2)) / n)
    f = _in_seg(body, stone, nr, 0.1, 0.85)
    return np.clip(np.where(joint, _lv(stone[0], nr), f), 0, 1)


# ---------------------------------------------------------------- carved and painted motifs
def _motif(kind, x, y):
    """Signed carving height (-1 groove .. +1 raised) of an original motif in a unit cell (x, y in -1..1)."""
    r = np.sqrt(x * x + y * y)
    a = np.arctan2(y, x)
    if kind == "spiral":
        s = np.sin(3.0 * a + r * 9.0)
        band = np.abs(s) < 0.45
        return np.where(r < 0.92, np.where(band, 1.0, -0.2), 0.0)
    if kind == "door":
        # an arched threshold with a keyhole (doors / keys / thresholds), on a carved step
        def arch(hw, top):
            spring = top - hw
            return (((np.abs(x) < hw) & (y < spring) & (y > -0.62)) |
                    ((y >= spring) & (x * x + (y - spring) ** 2 < hw * hw)))
        outer, inner = arch(0.62, 0.88), arch(0.44, 0.7)
        hole = ((x * x + (y - 0.06) ** 2) < 0.11 ** 2) | ((np.abs(x) < 0.045) & (y > -0.3) & (y < 0.06))
        step = (y < -0.62) & (y > -0.8) & (np.abs(x) < 0.82)
        out = np.where((outer & ~inner) | step, 1.0, np.where(inner, 0.35, 0.0))
        return np.where(hole, -1.0, out)
    if kind == "sun":
        disc = r < 0.38
        ring = (r > 0.5) & (r < 0.6)
        rays = (np.abs(np.sin(a * 8.0)) > 0.82) & (r > 0.62) & (r < 0.95)
        return np.where(disc | ring | rays, 1.0, np.where(r < 0.97, -0.15, 0.0))
    if kind == "serpent":
        wave = np.abs(y - 0.45 * np.sin(x * math.pi * 1.5)) < 0.16
        head = ((x - 0.78) ** 2 + (y - 0.45 * math.sin(0.78 * math.pi * 1.5)) ** 2) < 0.04
        return np.where(wave | head, 1.0, -0.1)
    if kind == "knot":
        a1 = np.abs(np.sin(x * math.pi) * np.cos(y * math.pi)) < 0.25
        a2 = (np.abs(np.abs(x) - 0.7) < 0.12) | (np.abs(np.abs(y) - 0.7) < 0.12)
        return np.where(a1 | a2, 1.0, -0.1)
    if kind == "key":
        bow = (np.abs(r - 0.36) < 0.12) & (x < 0.15)
        shaft = (np.abs(y) < 0.09) & (x > 0.0) & (x < 0.9)
        bit = (x > 0.55) & (x < 0.9) & (y < 0.0) & (y > -0.36) & ((np.floor((x - 0.55) / 0.12) % 2) == 0)
        return np.where(bow | shaft | bit, 1.0, 0.0)
    if kind == "wings":
        body = (np.abs(x) < 0.12) & (np.abs(y) < 0.6)
        feather = (np.abs(np.sin(np.abs(x) * 10.0 - y * 3.0)) < 0.5) & (np.abs(x) < 0.95) & (y > -0.2 - 0.6 * (1 - np.abs(x))) & (y < 0.45)
        return np.where(body | feather, 1.0, 0.0)
    raise ValueError("unknown motif %r" % kind)


MOTIFS = ("spiral", "door", "sun", "serpent", "knot", "key", "wings")


def g_relief(rs, n, p):
    """Carved relief frieze: `cols` x `rows` cells of an original motif (or `motifs` cycling) cut into dressed stone,
    with a raised border. Embossed painting: raised parts take a lit upper-left edge and a shaded lower-right edge,
    grooves are dark. Levels are exact steps except the stone body (soft blotches)."""
    segs, nr = _segs(p)
    stone = segs[0]
    lo = stone[0]
    top = stone[0] + stone[1] - 1
    cols, rows = int(p.get("cols", 1)), int(p.get("rows", 1))
    motifs = p.get("motifs") or [p.get("motif", "spiral")]
    u, v = T._grid(n)
    cu, cv = (u * cols) % 1.0, ((1 - v) * rows) % 1.0
    ci = np.floor(u * cols).astype(int)
    cj = np.floor((1 - v) * rows).astype(int)
    x, y = cu * 2 - 1, -(cv * 2 - 1)
    h = np.zeros((n, n))
    for k, kind in enumerate(motifs):
        sel = ((ci + cj) % len(motifs)) == k
        h = np.where(sel, _motif(kind, x / 0.82, y / 0.82), h)
    border = (np.abs(x) > 0.9) | (np.abs(y) > 0.9)
    h = np.where(border, 1.0, h)
    # emboss: compare with the height one texel up-left
    sh = np.roll(np.roll(h, 1, 0), 1, 1)
    edge_lit = (h > sh + 0.3)
    edge_dark = (h < sh - 0.3)
    blot = T._norm(T.fbm(rs, n, 3, 2))
    body = _in_seg(blot, stone, nr, 0.35, 0.65)
    f = np.where(h > 0.5, _lv(lo + max(1, (stone[1] - 1) * 2 // 3), nr), body)
    f = np.where(h < -0.5, _lv(lo, nr), f)
    f = np.where(edge_lit, _lv(top, nr), f)
    f = np.where(edge_dark, _lv(lo + 1 if stone[1] > 2 else lo, nr), f)
    return np.clip(f, 0, 1)


def g_runes(rs, n, p):
    """Glyph rows for rune tablets: original angular glyphs built from strokes on a cell grid (rows x glyphs), glowing
    strokes at the top step, a soft halo step around them, dark carved ground. Deterministic per seed tags."""
    nr = _nr(p, 4)
    rows, per = int(p.get("rows", 3)), int(p.get("glyphs", 4))
    f = np.full((n, n), _lv(0, nr))
    ch = n // rows
    cw = n // per
    halo = np.zeros((n, n), dtype=bool)
    stroke = np.zeros((n, n), dtype=bool)
    for j in range(rows):
        for i in range(per):
            x0, y0 = i * cw, j * ch
            gw, gh = max(3, cw - 3), max(3, ch - 3)
            segs = rs.integers(2, 5)
            for _ in range(segs):
                kind = rs.integers(0, 3)
                if kind == 0:      # vertical stroke
                    xx = x0 + 1 + rs.integers(0, gw)
                    a, b = sorted(rs.integers(0, gh, 2))
                    stroke[y0 + 1 + a:y0 + 2 + b, xx:xx + 1] = True
                elif kind == 1:    # horizontal stroke
                    yy = y0 + 1 + rs.integers(0, gh)
                    a, b = sorted(rs.integers(0, gw, 2))
                    stroke[yy:yy + 1, x0 + 1 + a:x0 + 2 + b] = True
                else:              # diagonal stroke
                    L = rs.integers(2, max(3, min(gw, gh)))
                    sx, sy = x0 + 1 + rs.integers(0, max(1, gw - L)), y0 + 1 + rs.integers(0, max(1, gh - L))
                    d = 1 if rs.random() < 0.5 else -1
                    for t in range(L):
                        xx = sx + (t if d > 0 else L - 1 - t)
                        stroke[min(n - 1, sy + t), min(n - 1, xx)] = True
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            halo |= np.roll(np.roll(stroke, dy, 0), dx, 1)
    f = np.where(halo, _lv(max(1, nr - 3), nr), f)
    f = np.where(stroke, _lv(nr - 1, nr), f)
    return f


def g_sigil(rs, n, p):
    """Boss-door sigil (one emblem per texture, normalised UVs): concentric carved rings, radiating rays, an original
    central arched threshold with a keyhole, iron studs on a ring, panel seams. Exact steps only (crisp painted carving)."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    x, y = u * 2 - 1, v * 2 - 1
    r = np.sqrt(x * x + y * y)
    a = np.arctan2(y, x)
    blot = T._norm(T.fbm(rs, n, 3, 2))
    f = _lv(1, nr) + (blot > 0.6) * (_lv(2, nr) - _lv(1, nr))
    ring = (np.abs(r - 0.78) < 0.05) | (np.abs(r - 0.56) < 0.035)
    rays = (np.abs(np.sin(a * float(p.get("rays", 12)) / 2.0)) > 0.93) & (r > 0.6) & (r < 0.76)
    studs = (np.abs(r - 0.88) < 0.04) & (np.abs(np.sin(a * 8.0)) > 0.94)
    spring, hw = 0.08, 0.26
    door_in = (((np.abs(x) < hw) & (y < spring) & (y > -0.42)) | ((y >= spring) & (x * x + (y - spring) ** 2 < hw * hw)))
    hw2 = hw + 0.07
    door_out = (((np.abs(x) < hw2) & (y < spring) & (y > -0.48)) | ((y >= spring) & (x * x + (y - spring) ** 2 < hw2 * hw2)))
    key = ((np.abs(x) < 0.04) & (y < -0.02) & (y > -0.2)) | ((x * x + (y + 0.0) ** 2) < 0.07 ** 2)
    seam = (np.abs(x) < 0.012) & ~door_out
    f = np.where(ring | rays, _lv(nr - 2, nr), f)
    f = np.where(door_out & ~door_in, _lv(nr - 1, nr), f)
    f = np.where(door_in, _lv(nr - 2, nr), f)
    f = np.where(key, _lv(0, nr), f)
    f = np.where(studs, _lv(nr - 1, nr), f)
    f = np.where(seam, _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_heraldry(rs, n, p):
    """Banner cloth (normalised UVs, v up): field colour with a woven ground, a contrasting border, and an original
    emblem (motif) in the upper half; a darker hem at the bottom. Exact steps for emblem/border."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    yy, xx = np.mgrid[0:n, 0:n]
    weave = ((xx // 1 + yy // 2) % 2) * 0.5
    f = _lv(1, nr) + weave * (_lv(2, nr) - _lv(1, nr))
    border = (u < 0.1) | (u > 0.9) | (v > 0.94)
    hem = v < 0.12
    x, y = (u - 0.5) * 2.4, (v - 0.62) * 2.4
    em = _motif(p.get("motif", "sun"), x, y) > 0.5
    f = np.where(border, _lv(nr - 2, nr), f)
    f = np.where(hem, _lv(0, nr), f)
    f = np.where(em, _lv(nr - 1, nr), f)
    return np.clip(f, 0, 1)


# ---------------------------------------------------------------- water and wet surfaces
def g_ripple(rs, n, p):
    """Painted N64 water: a deep body in broad flat pools (step 0 / step 1), wave crests painted as broken horizontal
    dashes on a gently warped stripe field (step 2, the classic scrolling-water squiggle, never a cell/tile grid),
    rare glints on crest tops (top step). Tileable; exact steps only."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    warp = T._norm(T.fbm(rs, n, 2, 2)) - 0.5
    bands = float(p.get("bands", 4))
    phase = (v * bands + warp * float(p.get("warp", 0.9)) + 0.12 * np.sin(u * 2 * np.pi * 2)) % 1.0
    crest = phase < float(p.get("crest", 0.16))
    dash = T._norm(T.fbm(rs, n, 3, 2, sx=2, sy=1)) > float(p.get("dash", 0.45))
    pool = T._norm(T.fbm(rs, n, 2, 2)) > float(p.get("pool", 0.55))
    f = np.where(pool, _lv(1, nr), _lv(0, nr))
    f = np.where(crest & dash, _lv(min(2, nr - 2), nr), f)
    glint = crest & dash & (T._norm(T.fbm(rs, n, 4, 2)) > float(p.get("glint", 0.82)))
    return np.clip(np.where(glint, _lv(nr - 1, nr), f), 0, 1)


def g_falls(rs, n, p):
    """Falling water sheet: vertical streaks (stretched noise along v) with bright foam threads; scrolls along u in the
    lake kit (the waterfall card maps u downward)."""
    nr = _nr(p, 4)
    s = T._norm(T.fbm(rs, n, 6, 3, sx=0.35, sy=6.0))
    thread = s > float(p.get("foam", 0.78))
    f = _in_seg(s, (0, nr), nr, 0.0, 0.75)
    return np.where(thread, _lv(nr - 1, nr), f)


def g_reedbed(rs, n, p):
    """Reed / grass blade colouring for alpha cards: vertical blades darker at the root (v low), light tips."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    blades = T._norm(T.fbm(rs, n, 8, 2, sx=4.0, sy=0.3))
    f = np.clip(0.2 + 0.6 * v + 0.25 * (blades - 0.5), 0, 1)
    return _in_seg(f, (0, nr), nr)


def g_pebbles(rs, n, p):
    """Shore pebbles / lake bed gravel: small rounded stones with painted rims on a soft sandy ground."""
    segs, nr = _segs(p)
    ground = segs[0]
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 22)))
    tone = rs.random(ids.max() + 1)[ids]
    stone = f1 < float(p.get("stone_r", 0.07)) * (0.7 + 0.6 * tone)
    blot = T._norm(T.fbm(rs, n, 3, 2))
    f = _in_seg(blot, ground, nr, 0.2, 0.7)
    rim = stone & (f1 > float(p.get("stone_r", 0.07)) * 0.55 * (0.7 + 0.6 * tone))
    seg2 = segs[1] if len(segs) > 1 else ground
    f = np.where(stone, _in_seg(tone, seg2, nr, 0.3, 1.0), f)
    f = np.where(rim, _lv(seg2[0], nr), f)
    return np.clip(f, 0, 1)


def g_ironwork(rs, n, p):
    """Painted wrought iron: dark plate with soft hammer blotches, a lit upper edge band and rivet dots (exact steps)."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    blot = T._norm(T.fbm(rs, n, 4, 2))
    f = _in_seg(blot, (0, nr), nr, 0.15, 0.6)
    k = int(p.get("rivets", 4))
    fu, fv = (u * k) % 1.0, (v * 2) % 1.0
    rivet = ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) < 0.012
    edge = v > 0.92
    f = np.where(edge, _lv(nr - 2, nr), f)
    return np.where(rivet, _lv(nr - 1, nr), f)


def g_ember(rs, n, p):
    """Torch flame / brazier coals (emissive): a teardrop of heat rising from the bottom, licking edges, a hot core
    that follows the same teardrop (no blocky rectangle)."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    lick = T._norm(T.fbm(rs, n, 3, 3, sx=1, sy=2))
    width = 0.48 * (1.0 - v) ** 0.7 + 0.04
    shape = 1.0 - np.abs(u - 0.5) / np.maximum(width, 1e-3) + 0.3 * (lick - 0.5) - 0.25 * v
    f = _in_seg(np.clip(shape, 0, 1), (0, nr), nr)
    core = shape > float(p.get("core", 0.78))
    return np.where(core, _lv(nr - 1, nr), f)


def g_crystal(rs, n, p):
    """Crystal facets for opaque painted gems (when no env map is used): angular bands with a bright edge step."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    a = (u * 3 + v * 2) % 1.0
    b = (u * 2 - v * 3) % 1.0
    f = _snap(0.35 + 0.4 * np.minimum(a, b) + 0.2 * T._norm(T.fbm(rs, n, 2, 1)), nr)
    edge = (np.minimum(a, 1 - a) < 1.2 / n * 3) | (np.minimum(b, 1 - b) < 1.2 / n * 3)
    return np.where(edge, _lv(nr - 1, nr), f)


GENS = {
    "ashlar": g_ashlar, "flagstone": g_flagstone, "cavestone": g_cavestone, "vault": g_vault, "relief": g_relief,
    "runes": g_runes, "sigil": g_sigil, "heraldry": g_heraldry, "ripple": g_ripple, "falls": g_falls,
    "reedbed": g_reedbed, "pebbles": g_pebbles, "ironwork": g_ironwork, "ember": g_ember, "crystal": g_crystal,
}

for _name, _fn in GENS.items():
    if _name in T.FIELD_GENS and T.FIELD_GENS[_name] is not _fn:
        raise RuntimeError("texture generator %r already registered" % _name)
    T.FIELD_GENS[_name] = _fn
