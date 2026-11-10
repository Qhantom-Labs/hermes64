"""CYBERKIT painted field generators (additive, theme-agnostic; registered into texgen.FIELD_GENS by
kits/core/gen_cyberkit.py on import, before any cyber pack texture is made).

Ocarina-era night-city surfaces painted by code: storey facades with dark window recesses, glass curtain walls,
wet asphalt with painted sheen, sidewalk slabs, crosswalk paint, roof membranes, ceramic tiles, shutters, grates, and
the SLOT ATLASES (glyph signs, blade signs, displays, neon tube rows, window-light rows, banners) whose cell table
lives in kits/core/cykit.py.

Painting rules (same as the dungeon painters, so n64_gate's library hf energy stays low):
- structured features (window frames, seams, glyph strokes, tube cores) sit EXACTLY on ramp steps, so the mottle
  threshold never flips them (palette.quantize_field: floor(k + 0.5 + t - 0.5) == k);
- only broad painted variation (tone, sheen, grime) lies between two steps of ONE family and mottles softly.

Slot ramps: the atlas painters read a 16-step ramp in a fixed layout
    [dark0 dark1 dark2 | a0 a1 a2 | b0 b1 b2 | c0 c1 c2 | d0 d1 d2 | white]
that the pack fills from its own palette roles (cyan / magenta / amber / violet in neon_city_night, cyan / electric
blue / amber / magenta in cyber_blue_grid). Values never fall between two families, so a sign never dithers cyan
into magenta. Glyphs come from an ORIGINAL stroke generator (a 3 x 4 node lattice, 2-4 strokes per glyph): an
invented script, no real alphabet, brand or logo.
"""
import math

import numpy as np

from . import texgen as T

SLOT_LAYOUT = ("dark", "a", "b", "c", "d", "white")
SLOT_LEN = 16


# ---------------------------------------------------------------- helpers
def _nr(p, default):
    return int(p.get("ramp_len", len(p.get("ramp") or []) or default))


def _lv(step, n):
    return float(step) / max(1, n - 1)


def _mix(step_a, step_b, t, n):
    """Field between two adjacent steps of one family (t in 0..1 mottles softly between them)."""
    return (step_a + (step_b - step_a) * np.clip(t, 0.0, 1.0)) / max(1, n - 1)


def _paint(f01, steps, n, soft=0.18):
    """Posterize a 0..1 painted field onto a list of ramp steps: texels sit EXACTLY on a step except in a narrow
    zone (+-soft of a band) around each boundary, where they ramp to the next step and the mottle threshold breaks
    the edge up. Broad painted blotches with mottled seams (N64 hand-painted), never salt-and-pepper speckle."""
    f = np.clip(np.asarray(f01, dtype=np.float64), 0.0, 1.0) * (len(steps) - 1)
    i = np.clip(np.floor(f).astype(int), 0, max(0, len(steps) - 2))
    fr = f - i
    lo, hi = 0.5 - soft, 0.5 + soft
    t = np.clip((fr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    t = t * t * (3 - 2 * t)
    st = np.asarray(steps, dtype=np.float64)
    if len(steps) == 1:
        return np.full(f.shape, st[0] / max(1, n - 1))
    a, b = st[i], st[np.minimum(i + 1, len(steps) - 1)]
    return (a + (b - a) * t) / max(1, n - 1)


def _slots(p):
    n = _nr(p, SLOT_LEN)
    if n != SLOT_LEN:
        raise ValueError("slot ramp must have %d steps (dark x3, a x3, b x3, c x3, d x3, white), got %d" % (SLOT_LEN, n))
    return {"dark": (0, 1, 2), "a": (3, 4, 5), "b": (6, 7, 8), "c": (9, 10, 11), "d": (12, 13, 14), "white": (15,)}


def _box(img, x0, y0, w, h, val):
    img[max(0, y0):max(0, y0 + h), max(0, x0):max(0, x0 + w)] = val


def _frame(img, x0, y0, w, h, val, t=1):
    _box(img, x0, y0, w, t, val)
    _box(img, x0, y0 + h - t, w, t, val)
    _box(img, x0, y0, t, h, val)
    _box(img, x0 + w - t, y0, t, h, val)


# ---------------------------------------------------------------- original glyph script
def glyph_mask(rs, w, h):
    """One invented glyph on a 3 x 4 node lattice inside a w x h box: a spine stroke plus 1-3 branch strokes and an
    optional dot. Angular, readable as 'signage script', belongs to no real writing system."""
    m = np.zeros((h, w), dtype=bool)
    xs = [0, (w - 1) // 2, w - 1]
    ys = [0, (h - 1) // 3, 2 * (h - 1) // 3, h - 1]

    def seg(a, b):
        (x0, y0), (x1, y1) = a, b
        k = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(k + 1):
            m[int(round(y0 + (y1 - y0) * i / k)), int(round(x0 + (x1 - x0) * i / k))] = True

    if rs.random() < 0.5:
        cx = xs[rs.integers(0, 3)]
        seg((cx, ys[0]), (cx, ys[3]))
    else:
        cy = ys[rs.integers(0, 4)]
        seg((xs[0], cy), (xs[2], cy))
    for _ in range(int(rs.integers(1, 4))):
        i, j = int(rs.integers(0, 3)), int(rs.integers(0, 4))
        kind = rs.integers(0, 3)
        if kind == 0:
            i2 = min(2, i + 1) if i < 2 else 0
            seg((xs[i], ys[j]), (xs[i2], ys[j]))
        elif kind == 1:
            j2 = min(3, j + 1 + int(rs.integers(0, 2)))
            seg((xs[i], ys[j]), (xs[i], ys[j2]))
        else:
            i2 = min(2, i + 1)
            j2 = min(3, j + 1)
            seg((xs[i], ys[j]), (xs[i2], ys[j2]))
    if rs.random() < 0.35:
        m[ys[1], xs[2] if rs.random() < 0.5 else xs[0]] = True
    return m


PICTOS = {
    # 14 x 14 pictograms drawn from primitives (bowl + steam, cross, joystick, ring/gem, bed, arrow, heart, bolt)
    "bowl": lambda yy, xx: ((yy >= 7) & (yy <= 10) & (np.abs(xx - 6.5) <= 6 - (yy - 7) * 1.1)) | ((yy == 6) & (xx >= 1) & (xx <= 12))
    | ((yy >= 1) & (yy <= 4) & ((xx == 4) | (xx == 7) | (xx == 10)) & ((yy + xx) % 2 == 0)),
    "cross": lambda yy, xx: ((np.abs(xx - 6.5) <= 1.6) & (yy >= 1) & (yy <= 12)) | ((np.abs(yy - 6.5) <= 1.6) & (xx >= 1) & (xx <= 12)),
    "joystick": lambda yy, xx: ((yy >= 9) & (yy <= 12) & (xx >= 1) & (xx <= 12)) | ((np.abs(xx - 6.5) <= 0.6) & (yy >= 4) & (yy <= 9))
    | (((xx - 6.5) ** 2 + (yy - 3.2) ** 2) <= 5.5),
    "ring": lambda yy, xx: ((((xx - 6.5) ** 2 + (yy - 8.0) ** 2) <= 20) & (((xx - 6.5) ** 2 + (yy - 8.0) ** 2) >= 8))
    | ((yy >= 1) & (yy <= 3) & (np.abs(xx - 6.5) <= 3 - (yy - 1))),
    "bed": lambda yy, xx: ((yy >= 7) & (yy <= 9) & (xx >= 1) & (xx <= 12)) | ((xx <= 2) & (yy >= 3) & (yy <= 12)) | ((xx >= 11) & (yy >= 9) & (yy <= 12))
    | (((xx - 4.5) ** 2 + (yy - 5.5) ** 2) <= 2.5),
    "arrow": lambda yy, xx: ((np.abs(yy - 6.5) <= 1.2) & (xx >= 1) & (xx <= 8)) | ((xx >= 8) & (np.abs(yy - 6.5) <= 12 - xx)),
}


def picto_mask(name, size=14):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    return PICTOS[name](yy, xx)


def _glyph_row(rs, img, x0, y0, w, h, count, val, gw=5, gh=7, gap=2):
    total = count * gw + (count - 1) * gap
    sx = x0 + max(0, (w - total) // 2)
    sy = y0 + max(0, (h - gh) // 2)
    for k in range(count):
        g = glyph_mask(rs, gw, gh)
        sub = img[sy:sy + gh, sx + k * (gw + gap):sx + k * (gw + gap) + gw]
        sub[g[:sub.shape[0], :sub.shape[1]]] = val


def _glyph_col(rs, img, x0, y0, w, h, count, val, gw=5, gh=7, gap=3):
    total = count * gh + (count - 1) * gap
    sx = x0 + max(0, (w - gw) // 2)
    sy = y0 + max(0, (h - total) // 2)
    for k in range(count):
        g = glyph_mask(rs, gw, gh)
        sub = img[sy + k * (gh + gap):sy + k * (gh + gap) + gh, sx:sx + gw]
        sub[g[:sub.shape[0], :sub.shape[1]]] = val


# ---------------------------------------------------------------- atlas painters (slot ramps, crisp)
def g_cy_signs(rs, n, p):
    """screen atlas: horizontal glyph signs (slots a/b/c, two designs each) and four pictogram cells."""
    from .cykit import SCREEN
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["dark"][0], N))
    for name, (x, y, w, h, s) in sorted(SCREEN.items()):
        e0, e1, e2 = S[s]
        sub_rs = rs
        _box(img, x, y, w, h, _lv(S["dark"][1], N))
        if name.startswith("sign_"):
            design = int(name[-1])
            _frame(img, x, y, w, h, _lv(e0, N))
            _frame(img, x + 1, y + 1, w - 2, h - 2, _lv(e2 if design == 0 else e1, N))
            _box(img, x + 2, y + 2, w - 4, h - 4, _lv(S["dark"][0], N))
            if design == 1:          # split sign: a lit tag block + glyphs
                _box(img, x + 3, y + 3, 7, h - 6, _lv(e1, N))
                _glyph_row(sub_rs, img, x + 11, y + 2, w - 13, h - 4, 3, _lv(S["white"][0], N), gw=4, gh=7, gap=1)
            else:
                _glyph_row(sub_rs, img, x + 2, y + 2, w - 4, h - 4, 4, _lv(e2, N), gw=5, gh=8, gap=1)
        else:
            pm = picto_mask(name[len("picto_"):])
            _frame(img, x, y, w, h, _lv(e0, N))
            sub = img[y + 1:y + 15, x + 1:x + 15]
            sub[pm] = _lv(e2, N)
    return img


def g_cy_blades(rs, n, p):
    """paper atlas: four vertical blade signs 16 x 64 (slots a/b/c/d): double neon rim, stacked glyph column, a lit
    cap block."""
    from .cykit import PAPER
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["dark"][0], N))
    for name, (x, y, w, h, s) in sorted(PAPER.items()):
        e0, e1, e2 = S[s]
        _frame(img, x, y, w, h, _lv(e0, N))
        _frame(img, x + 1, y + 1, w - 2, h - 2, _lv(e2, N))
        _box(img, x + 2, y + 2, w - 4, h - 4, _lv(S["dark"][1], N))
        _box(img, x + 3, y + 3, w - 6, 8, _lv(e1, N))
        _glyph_col(rs, img, x + 2, y + 12, w - 4, h - 15, 5, _lv(e2, N), gw=7, gh=7, gap=2)
    return img


def g_cy_displays(rs, n, p):
    """book atlas: billboard (a big pictogram ring, glyph line, colour bars), a monitor (code lines, a bar graph),
    a menu / product grid (lit cells)."""
    from .cykit import BOOK
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["dark"][0], N))
    x, y, w, h, s = BOOK["billboard"]
    e0, e1, e2 = S[s]
    a0, a1, a2 = S["a"]
    _box(img, x, y, w, h, _lv(S["dark"][1], N))
    _frame(img, x, y, w, h, _lv(e1, N))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    d = np.sqrt((xx - 15.5) ** 2 + (yy - 15.5) ** 2)
    sub = img[y:y + h, x:x + w]
    sub[(d < 11) & (d >= 7)] = _lv(e2, N)
    sub[(d < 7) & (d >= 5)] = _lv(e0, N)
    sub[(d < 4)] = _lv(S["white"][0], N)
    _glyph_row(rs, img, x + 30, y + 4, 32, 10, 4, _lv(S["white"][0], N), gw=5, gh=7, gap=2)
    for k in range(3):
        _box(img, x + 31, y + 16 + 4 * k, 8 + 7 * ((k + 1) % 3) + 6, 2, _lv((e1, a1, e2)[k], N))
    _box(img, x + 31, y + 27, 30, 2, _lv(a2, N))
    # monitor: code lines + bar graph
    x, y, w, h, s = BOOK["monitor"]
    e0, e1, e2 = S[s]
    _box(img, x, y, w, h, _lv(S["dark"][0], N))
    _frame(img, x, y, w, h, _lv(S["dark"][2], N))
    for r in range(6):
        ln = int(rs.integers(6, 22))
        ind = 2 * int(rs.integers(0, 3))
        _box(img, x + 3 + ind, y + 3 + 3 * r, ln, 1, _lv(e1 if r % 3 else e2, N))
    for k in range(6):
        hh = int(rs.integers(2, 9))
        _box(img, x + 4 + 4 * k, y + 29 - hh, 3, hh, _lv(e2 if k % 2 else e1, N))
    # menu / product grid
    x, y, w, h, s = BOOK["menu"]
    e0, e1, e2 = S[s]
    _box(img, x, y, w, h, _lv(S["dark"][1], N))
    _frame(img, x, y, w, h, _lv(e1, N))
    for r in range(3):
        for c in range(4):
            cx0, cy0 = x + 2 + 7 * c, y + 2 + 9 * r
            _box(img, cx0, cy0, 6, 7, _lv(e0, N))
            _box(img, cx0 + 1, cy0 + 1, 4, 4, _lv((e2, S["a"][2], S["b"][2], S["white"][0])[(r + c) % 4], N))
    return img


def g_cy_neon(rs, n, p):
    """light atlas: four 8-texel tube rows (slots a/b/c/d), each painted edge -> body -> white core -> body ->
    edge across the row, uniform along it."""
    from .cykit import LIGHT
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["white"][0], N))
    for name, (x, y, w, h, s) in sorted(LIGHT.items()):
        e0, e1, e2 = S[s]
        prof = [e0, e1, e2, S["white"][0], S["white"][0], e2, e1, e0]
        for k, st in enumerate(prof[:h]):
            img[y + k, x:x + w] = _lv(st, N)
    return img


def g_cy_windows(rs, n, p):
    """fire atlas: 4 window-row variants x 8 windows (8 x 16 texels each): warm lit panes (gradient to a bright
    top), cool lit panes, dim panes and dark panes, 1-texel mullions. The bands of cykit.window_bands sample one
    row and a 2 m-aligned offset, so lit floors never repeat in step."""
    from .cykit import FIRE_ROWS
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["dark"][0], N))
    rows = FIRE_ROWS
    rh = n // rows
    cw = n // 8
    weights = [float(x) for x in p.get("mix", [0.42, 0.18, 0.16, 0.24])]  # warm, cool, dim, dark
    cum = np.cumsum(weights) / sum(weights)
    for r in range(rows):
        for c in range(8):
            x0, y0 = c * cw, r * rh
            k = int(np.searchsorted(cum, rs.random()))
            _box(img, x0, y0, cw, rh, _lv(S["dark"][1], N))
            inner = (x0 + 1, y0 + 2, cw - 1, rh - 3)
            yy = np.arange(inner[3])[:, None] / max(1, inner[3] - 1)        # 0 top -> 1 bottom
            # gradients only between ADJACENT steps of one family; the bright pane top is an exact white stroke
            if k == 0:
                f = np.where(yy < 0.3, _lv(S["c"][2], N), _mix(S["c"][1], S["c"][2], 1.0 - (yy - 0.3) / 0.7, N))
                f = np.where(yy < 0.1, _lv(S["white"][0], N), f)
            elif k == 1:
                f = np.where(yy < 0.3, _lv(S["a"][2], N), _mix(S["a"][1], S["a"][2], 1.0 - (yy - 0.3) / 0.7, N))
                f = np.where(yy < 0.1, _lv(S["white"][0], N), f)
            elif k == 2:
                f = _mix(S["c"][0], S["c"][1], 1.0 - yy, N)
            else:
                f = _mix(S["dark"][0], S["dark"][2], 0.6 * (1.0 - yy), N)
            img[inner[1]:inner[1] + inner[3], inner[0]:inner[0] + inner[2]] = np.broadcast_to(f, (inner[3], inner[2]))
            if k in (0, 1) and rs.random() < 0.35:             # a blind or a figure: one darker block in the pane
                bx = inner[0] + int(rs.integers(0, max(1, inner[2] - 3)))
                _box(img, bx, inner[1] + 3, 3, inner[3] - 5, _lv(S["c"][0] if k == 0 else S["a"][0], N))
    return img


def g_cy_banners(rs, n, p):
    """fabric atlas: four hanging cloth banners 16 x 64 (slots a/b/c/d cloth mid tone, light glyph column, a dark
    hem band top and bottom). Baked (lit by the rig), so the glyph strokes stay 2 texels wide and soft-edged."""
    from .cykit import FABRIC
    S = _slots(p)
    N = SLOT_LEN
    img = np.full((n, n), _lv(S["dark"][1], N))
    for name, (x, y, w, h, s) in sorted(FABRIC.items()):
        e0, e1, e2 = S[s]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        fold = 0.5 + 0.5 * np.cos((xx / w) * 2 * math.pi * 2)
        img[y:y + h, x:x + w] = _mix(e0, e1, 0.55 + 0.45 * fold, N)
        _box(img, x, y, w, 4, _lv(S["dark"][2], N))
        _box(img, x, y + h - 4, w, 4, _lv(S["dark"][2], N))
        sub = np.zeros((h, w), dtype=bool)
        for k in range(4):
            g = glyph_mask(rs, 5, 6)
            g2 = np.repeat(np.repeat(g, 2, 0), 2, 1)[:12, :10]
            sub[7 + 14 * k:7 + 14 * k + g2.shape[0], 3:3 + g2.shape[1]] |= g2
        img[y:y + h, x:x + w][sub] = _lv(e2, N)
    return img


# ---------------------------------------------------------------- surfaces (ordinary dark->bright ramps)
def _tone_cells(ix, iy, salt=1.0):
    """Deterministic 0..1 tone per integer cell (per-tile / per-slab variation)."""
    return np.abs(np.sin((ix * 7.0 + iy * 13.0 + salt) * 12.9898) * 43758.5453) % 1.0


def g_cy_facade(rs, n, p):
    """One storey x `bays` bays (tiles both ways): a slab band with a shadow line, spandrel panels in two painted
    tones, dark window recesses with a cool diagonal sheen, a lit sill and a dark head. Ramp:
    [glass x3, panel x3, sill]."""
    nr = _nr(p, 7)
    u, v = T._grid(n)
    bays = int(p.get("bays", 2))
    ub = (u * bays) % 1.0
    wu0, wu1 = float(p.get("win_u0", 0.12)), float(p.get("win_u1", 0.88))
    wv0, wv1 = float(p.get("win_v0", 0.22)), float(p.get("win_v1", 0.85))
    slab = float(p.get("slab", 0.1))
    grime = T._norm(T.fbm(rs, n, 2, 2, sx=2, sy=1))
    streak = T._norm(T.fbm(rs, n, 3, 1, sx=3, sy=1))       # rain streaks under the sills
    f = _paint(0.35 * grime + 0.4 * (1.0 - v) * streak + 0.1, [3, 4, 5], nr)
    f = np.where(v < slab, _lv(5, nr), f)
    f = np.where((v >= slab) & (v < slab + 1.0 / n), _lv(3, nr), f)
    win = (ub > wu0) & (ub < wu1) & (v > wv0) & (v < wv1)
    sheen = np.clip(0.5 + 0.5 * np.sin((u * bays + v * 1.7) * 2 * math.pi), 0, 1) * (1.0 - (v - wv0) / (wv1 - wv0))
    f = np.where(win, _paint(0.1 + 0.8 * sheen, [0, 1, 2], nr, soft=0.25), f)
    mull = win & (np.abs(ub - 0.5) < 0.6 * bays / n)
    f = np.where(mull, _lv(3, nr), f)
    sill = (ub > wu0) & (ub < wu1) & (v >= wv0 - 1.5 / n) & (v <= wv0)
    f = np.where(sill, _lv(nr - 1, nr), f)
    head = (ub > wu0) & (ub < wu1) & (v >= wv1) & (v <= wv1 + 1.5 / n)
    return np.where(head, _lv(0, nr), f)


def g_cy_curtain(rs, n, p):
    """Glass curtain wall: dark glass with a broad diagonal reflection sweep painted in bands, a few lighter panes,
    thin mullions every 1/`cols`, a transom per storey. Ramp: [glass x4, mullion, transom]."""
    nr = _nr(p, 6)
    u, v = T._grid(n)
    cols = int(p.get("cols", 4))
    sweep = 0.5 + 0.5 * np.sin((u + v * 0.6) * 2 * math.pi)
    lift = _tone_cells(np.floor(u * cols), np.floor(v * 2), 3.0)
    f = _paint(0.12 + 0.62 * sweep + 0.22 * (lift > 0.8), [0, 1, 2, 3], nr, soft=0.22)
    mull = ((u * cols) % 1.0) < 1.0 * cols / n
    f = np.where(mull, _lv(nr - 2, nr), f)
    f = np.where(v < 2.0 / n, _lv(nr - 1, nr), f)
    return np.where((v > 0.74) & (v < 0.74 + 1.0 / n), _lv(nr - 2, nr), f)


def g_cy_tiles(rs, n, p):
    """Ceramic wall / floor tiles: `count` x `count` per tile, grout on an exact step, per-tile tone (two steps)
    and a broad polished sheen. Ramp: [grout, tile x(n-1)]."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    c = int(p.get("count", 4))
    tone = _tone_cells(np.floor(u * c), np.floor(v * c))
    sheen = T._norm(T.fbm(rs, n, 2, 2))
    f = _paint(0.25 * tone + 0.6 * sheen + 0.1, list(range(1, nr)), nr)
    gu = ((u * c) % 1.0 < 1.0 * c / n) | ((v * c) % 1.0 < 1.0 * c / n)
    return np.where(gu, _lv(0, nr), f)


def g_cy_asphalt(rs, n, p):
    """Wet asphalt: broad painted patches, long reflection smears along the road (v) a step or two lighter, an
    optional dashed centre line at u = 0.5. Ramp: [asphalt x(n-2), sheen, paint]."""
    nr = _nr(p, 7)
    u, v = T._grid(n)
    patch = T._norm(T.fbm(rs, n, 2, 2))
    smear = T._norm(T.fbm(rs, n, 2, 2, sx=4, sy=1))
    wet = np.clip((smear - 0.5) / 0.5, 0, 1)
    f = _paint(0.2 + 0.45 * patch, list(range(0, nr - 3)), nr)
    f = np.where(wet > 0.45, _paint(0.3 + 0.7 * wet, [nr - 4, nr - 3, nr - 2], nr), f)
    if p.get("lane", True):
        line = (np.abs(u - 0.5) < 1.6 / n) & ((v * float(p.get("dashes", 1))) % 1.0 < 0.5)
        f = np.where(line, _lv(nr - 1, nr), f)
    return f


def g_cy_paving(rs, n, p):
    """Sidewalk slabs (`cols` x `rows` per tile, running bond), dark seams on an exact step, per-slab tone, a broad
    wet sheen. Ramp: [seam, slab x(n-1)]."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    cols, rows = int(p.get("cols", 3)), int(p.get("rows", 4))
    ry = np.floor(v * rows)
    uu = (u * cols + 0.5 * (ry % 2)) % cols
    tone = _tone_cells(np.floor(uu), ry, 2.0)
    sheen = T._norm(T.fbm(rs, n, 2, 2))
    f = _paint(0.3 * tone + 0.55 * sheen + 0.08, list(range(1, nr)), nr)
    seam = ((uu % 1.0) < 1.0 * cols / n) | (((v * rows) % 1.0) < 1.0 * rows / n)
    return np.where(seam, _lv(0, nr), f)


def g_cy_zebra(rs, n, p):
    """Crosswalk paint: `stripes` bars across u over asphalt, worn edges. Ramp: [asphalt x2, paint x2]."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    k = int(p.get("stripes", 3))
    wear = T._norm(T.fbm(rs, n, 4, 2))
    bar = ((u * k) % 1.0) < 0.5
    paint = _paint(0.3 + 0.7 * wear, [nr - 2, nr - 1], nr)
    asph = _paint(0.2 + 0.6 * wear, [0, 1], nr)
    worn = bar & (wear < 0.16)
    return np.where(bar & ~worn, paint, asph)


def g_cy_membrane(rs, n, p):
    """Roof membrane: sheets `cols` per tile with lapped seams, darker painted patches, sparse gravel flecks."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    cols = int(p.get("cols", 4))
    patch = T._norm(T.fbm(rs, n, 3, 2))
    f = _paint(0.15 + 0.7 * patch, list(range(1, nr - 1)), nr)
    seam = ((u * cols) % 1.0) < 1.0 * cols / n
    f = np.where(seam, _lv(nr - 1, nr), f)
    lap = (((u * cols) % 1.0) >= 1.0 * cols / n) & (((u * cols) % 1.0) < 2.0 * cols / n)
    f = np.where(lap, _lv(0, nr), f)
    fleck = rs.random((n, n)) < float(p.get("flecks", 0.012))
    return np.where(fleck & ~seam, _lv(nr - 2, nr), f)


def g_cy_shutter(rs, n, p):
    """Roll shutter: horizontal slats (`slats` per tile) with a lit lip and a shadow groove, painted grime."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    s = int(p.get("slats", 8))
    t = (v * s) % 1.0
    grime = T._norm(T.fbm(rs, n, 2, 2, sx=1, sy=2))
    f = _paint(0.25 + 0.5 * grime, list(range(1, nr - 1)), nr)
    f = np.where(t < 1.0 * s / n, _lv(0, nr), f)
    return np.where((t >= 1.0 * s / n) & (t < 2.0 * s / n), _lv(nr - 1, nr), f)


def g_cy_grate(rs, n, p):
    """Metal grating: crossing bars on painted steps over a dark gap, lit crossings."""
    nr = _nr(p, 5)
    u, v = T._grid(n)
    k = int(p.get("count", 6))
    wear = T._norm(T.fbm(rs, n, 2, 2))
    bx = ((u * k) % 1.0) < 0.34
    by = ((v * k) % 1.0) < 0.34
    f = np.where(bx | by, _paint(0.2 + 0.6 * wear, list(range(2, nr - 1)), nr), _lv(0, nr))
    return np.where(bx & by, _lv(nr - 1, nr), f)


def g_cy_panels(rs, n, p):
    """Painted panel body (props, vehicles, racks, trims): `cols` x `rows` panels with a dark seam and a lit bevel
    edge, optional vent slots, two painted tones per panel. Ramp: [seam, body x(n-2), bevel]."""
    nr = _nr(p, 6)
    u, v = T._grid(n)
    cols, rows = int(p.get("cols", 2)), int(p.get("rows", 2))
    pu, pv = (u * cols) % 1.0, (v * rows) % 1.0
    grime = T._norm(T.fbm(rs, n, 2, 2))
    tone = _tone_cells(np.floor(u * cols), np.floor(v * rows), 5.0)
    f = _paint(0.2 + 0.4 * grime + 0.25 * tone + 0.15 * pv, list(range(1, nr - 1)), nr)
    e = 1.0 / n
    f = np.where((pu < cols * e) | (pv < rows * e), _lv(0, nr), f)
    f = np.where(((pu >= cols * e) & (pu < 2 * cols * e)) | ((pv >= 1 - 2 * rows * e) & (pv < 1 - rows * e)), _lv(nr - 1, nr), f)
    if p.get("vents"):
        vent = (pu > 0.2) & (pu < 0.8) & (pv > 0.15) & (pv < 0.45) & (((pv * 24) % 1.0) < 0.4)
        f = np.where(vent, _lv(0, nr), f)
    return f


def g_cy_hazard(rs, n, p):
    """Diagonal hazard / accent stripes on exact steps with a little painted wear. Ramp: [dark x2, accent x2]."""
    nr = _nr(p, 4)
    u, v = T._grid(n)
    k = int(p.get("count", 2))
    wear = T._norm(T.fbm(rs, n, 3, 2))
    s = ((u + v) * k) % 1.0 < 0.5
    return np.where(s, _paint(0.25 + 0.6 * wear, [nr - 2, nr - 1], nr), _paint(0.25 + 0.6 * wear, [0, 1], nr))


def g_cy_skyline(rs, n, p):
    """Skyline card body: dark tower masses (tone columns) with rows of tiny lit windows on exact steps and a
    painted city-glow band toward the bottom (two clean haze steps). Silhouettes come from the card GEOMETRY
    (cysky.skyline), so the texture tiles horizontally. Ramp: [mass x3, haze x2, warm window, cool window]."""
    nr = _nr(p, 7)
    u, v = T._grid(n)
    cols = int(p.get("towers", 6))
    tone = _tone_cells(np.floor(u * cols), 0.0, 4.0)
    grime = T._norm(T.fbm(rs, n, 3, 2))
    f = _paint(0.12 + 0.4 * tone + 0.32 * grime + 0.12 * v, [0, 1, 2, 3], nr, soft=0.28)
    # Painted recessed storey bands break up otherwise flat silhouette-card masses, not random pixel noise.
    f = np.where(((v * 12.0) % 1.0) < 0.075, _lv(0, nr), f)
    g = float(p.get("glow", 0.55))
    wob = 0.04 * np.sin(u * 2 * math.pi * 3.0)
    f = np.where(v < g * 0.62 + wob, _lv(3, nr), f)
    f = np.where(v < g * 0.28 + wob * 0.5, _lv(4, nr), f)
    rows = int(p.get("rows", 12))
    wcols = int(p.get("wcols", 24))
    ru, rv = (u * wcols) % 1.0, (v * rows) % 1.0
    rnd = _tone_cells(np.floor(u * wcols), np.floor(v * rows), 9.0 + float(p.get("seed", 0)))
    lit_p = float(p.get("lit", 0.22))
    lit = (ru < 0.45) & (rv < 0.4) & (rnd < lit_p) & (v > g * 0.3)
    f = np.where(lit & (rnd < lit_p * 0.7), _lv(nr - 2, nr), f)
    return np.where(lit & (rnd >= lit_p * 0.7), _lv(nr - 1, nr), f)


def g_cy_view(rs, n, p):
    """Window view (apartment / den / lobby): a night sky in painted bands, two depth layers of tower silhouettes
    with lit window flecks and a few neon dots. Ramp: [mass x2, sky x3 (dark -> horizon), warm, cool, accent]."""
    nr = _nr(p, 8)
    u, v = T._grid(n)
    hz = float(p.get("horizon", 0.3))
    f = _paint(np.clip(1.0 - (v - hz) / (1.0 - hz), 0, 1) ** 1.4, [2, 3, 4], nr, soft=0.12)
    xs = np.arange(n) / n
    for layer, (base, height, count, step) in enumerate(((hz + 0.05, 0.45, 9, 1), (hz - 0.08, 0.32, 7, 0))):
        h = np.full(n, base)
        for _ in range(count):
            c = rs.random()
            w = 0.04 + 0.07 * rs.random()
            hh = height * (0.35 + 0.65 * rs.random())
            d = np.abs(xs - c)
            d = np.minimum(d, 1 - d)
            h = np.where(d < w, np.maximum(h, base + hh), h)
            if rs.random() < 0.4:
                h = np.where(d < 0.006, np.maximum(h, base + hh + 0.12), h)
        mass = v < h[None, :]
        f = np.where(mass, _lv(step, nr), f)
        rnd = _tone_cells(np.floor(u * 64), np.floor(v * 40), 7.0 * (layer + 1))
        lit = mass & (((u * 64) % 1.0) < 0.5) & (((v * 40) % 1.0) < 0.5) & (rnd < (0.16 if layer else 0.26))
        f = np.where(lit, _lv(nr - 3 + layer, nr), f)
        f = np.where(mass & (rnd > 0.996), _lv(nr - 1, nr), f)
    return f


GENS = {
    "cy_signs": g_cy_signs, "cy_blades": g_cy_blades, "cy_displays": g_cy_displays, "cy_neon": g_cy_neon,
    "cy_windows": g_cy_windows, "cy_banners": g_cy_banners, "cy_facade": g_cy_facade, "cy_curtain": g_cy_curtain,
    "cy_tiles": g_cy_tiles, "cy_asphalt": g_cy_asphalt, "cy_paving": g_cy_paving, "cy_zebra": g_cy_zebra,
    "cy_membrane": g_cy_membrane, "cy_shutter": g_cy_shutter, "cy_grate": g_cy_grate, "cy_panels": g_cy_panels,
    "cy_hazard": g_cy_hazard, "cy_skyline": g_cy_skyline, "cy_view": g_cy_view,
}


def register():
    for k, fn in GENS.items():
        if T.FIELD_GENS.get(k, fn) is not fn:
            raise ValueError("texture generator %r already registered" % k)
        T.FIELD_GENS[k] = fn


register()
