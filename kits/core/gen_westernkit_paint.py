"""WESTERNKIT painted field generators (additive, theme-agnostic; registered into texgen.FIELD_GENS on import).

Frontier surfaces painted by code for the Ocarina-era look: lap-sided and board-and-batten timber, plank decks, wood
shingles, corrugated tin, adobe plaster, brick, fieldstone, layered canyon sandstone, desert ground with wheel ruts,
sage scrub, cactus ribs, saloon wallpaper, a back-bar bottle shelf, blank posters and sign boards, painted window panes,
plank doors and the frontier sky dome (gradient + mesa silhouettes + streak clouds or stars).

Every generator returns a tileable float field in [0, 1] (row 0 = TOP of the image) that texgen.make_texture maps onto
the recipe ramp with the shared N64 convention (mottle quantization). Painting rules (same method as the other kits):

- structured features (lap shadows, plank gaps, mortar, ridge crests, silhouettes, sign borders) sit EXACTLY on ramp
  steps, so the mottle threshold never flips them;
- only broad painted variation (board tone, weathering, sky gradient) lies between steps and mottles softly;
- `segments: [a, b]` splits a ramp into hue families (e.g. tin + rust); a texel is painted inside one segment only.

No colour, theme or palette word lives here: generators see step levels only. Registered names are prefixed `wk_` so
they never collide with core or other kit generators.
"""
import math

import numpy as np

from . import texgen as T


# ---------------------------------------------------------------- helpers
def _nr(p, default=5):
    return int(len(p.get("ramp") or []) or default)


def _segs(p):
    n = _nr(p)
    segs = p.get("segments") or [n]
    out, k = [], 0
    for c in segs:
        out.append((k, int(c)))
        k += int(c)
    if k != n:
        raise ValueError("ramp segments %r do not cover the %d-colour ramp" % (segs, n))
    return out, n


def _lv(step, n):
    return float(step) / max(1, n - 1)


def _in_seg(f01, seg, n, lo=0.0, hi=1.0):
    first, count = seg
    a = first + lo * (count - 1)
    b = first + hi * (count - 1)
    return (a + (b - a) * np.clip(f01, 0.0, 1.0)) / max(1, n - 1)


def _rows_cols(n):
    yy, xx = np.mgrid[0:n, 0:n]
    return yy, xx


def _blot(rs, n, lat=3, oct=2):
    return T._norm(T.fbm(rs, n, lat, oct))


# ---------------------------------------------------------------- timber
def g_clapboard(rs, n, p):
    """Lap siding: `boards` horizontal boards per tile; each board's top texel row is the lap shadow cast by the board
    above (exact step 0), the face brightens toward its thick lower edge, per-board tone, horizontal grain, staggered
    butt joints (exact dark step) and broad sun-weathering (`weather`: lighter, greyer patches)."""
    nr = _nr(p)
    boards = int(p.get("boards", 12))
    yy, xx = _rows_cols(n)
    bh = n / float(boards)
    b = np.floor(yy / bh).astype(int) % boards
    t = (yy - b * bh) / bh                                   # 0 at the board's top, 1 at its bottom edge
    tone = rs.random(boards)
    grain = T._norm(T.fbm(rs, n, 2, 3, sx=6, sy=1))
    blot = _blot(rs, n, 2, 2)
    lo, hi = float(p.get("body_lo", 0.25)), float(p.get("body_hi", 0.92))
    face = 0.42 * tone[b] + 0.26 * t + 0.14 * grain + float(p.get("weather", 0.25)) * (blot - 0.5) + 0.12
    f = _in_seg(np.clip(face, 0, 1), (1, nr - 1), nr, lo, hi)
    shadow = (yy - b * bh) < float(p.get("lap", 1.0))
    f = np.where(shadow, _lv(0, nr), f)
    joints = np.floor(rs.random(boards) * n).astype(int)
    joint2 = np.floor(rs.random(boards) * n).astype(int)
    jx = joints[b]
    jx2 = joint2[b]
    jm = ((xx == jx) | ((xx == jx2) & (rs.random(boards)[b] < float(p.get("joints", 0.5))))) & ~shadow
    f = np.where(jm, _lv(min(1, nr - 1), nr), f)
    return np.clip(f, 0, 1)


def g_battens(rs, n, p):
    """Board-and-batten: `boards` vertical boards per tile with a narrow batten over every seam (lit left edge, shaded
    right edge, exact steps), vertical grain, per-board tone and optional paint `wear` (weathered patches dropping two
    steps, as old paint over bare wood)."""
    nr = _nr(p)
    boards = int(p.get("boards", 4))
    yy, xx = _rows_cols(n)
    bw = n / float(boards)
    b = np.floor(xx / bw).astype(int) % boards
    s = xx - b * bw
    tone = rs.random(boards)
    grain = T._norm(T.fbm(rs, n, 2, 3, sx=1, sy=6))
    blot = _blot(rs, n, 3, 2)
    face = 0.45 * tone[b] + 0.2 * grain + 0.25 * blot + 0.08
    f = _in_seg(np.clip(face, 0, 1), (1, nr - 1), nr, 0.1, 0.8)
    bat_w = max(2.0, bw * float(p.get("batten", 0.22)))
    on_bat = s < bat_w
    f = np.where(on_bat, _in_seg(0.75 + 0.2 * tone[(b + 1) % boards], (1, nr - 1), nr, 0.3, 1.0), f)
    f = np.where(on_bat & (s < 1.0), _lv(nr - 1, nr), f)
    f = np.where((s >= bat_w) & (s < bat_w + 1.0), _lv(0, nr), f)
    wear = float(p.get("wear", 0.0))
    if wear > 0:
        w = T._norm(T.fbm(rs, n, 4, 3)) > 1.0 - wear
        f = np.where(w & ~on_bat, np.maximum(_lv(1, nr), f - 2.0 / max(1, nr - 1)), f)
    return np.clip(f, 0, 1)


def g_deck(rs, n, p):
    """Plank deck / floor: `planks` boards per tile running along u, dark gaps (exact step 0), staggered butt joints,
    per-board tone, grain along the boards and a worn lighter path down the middle (`wear`)."""
    nr = _nr(p)
    planks = int(p.get("planks", 8))
    yy, xx = _rows_cols(n)
    ph = n / float(planks)
    b = np.floor(yy / ph).astype(int) % planks
    tone = rs.random(planks)
    grain = T._norm(T.fbm(rs, n, 2, 3, sx=6, sy=1))
    blot = _blot(rs, n, 2, 2)
    face = 0.45 * tone[b] + 0.2 * grain + 0.22 * blot + 0.05
    wear = float(p.get("wear", 0.0))
    if wear:
        u, v = T._grid(n)
        face = face + wear * (0.5 - np.abs(v - 0.5)) * 0.6
    f = _in_seg(np.clip(face, 0, 1), (1, nr - 1), nr, float(p.get("body_lo", 0.15)), float(p.get("body_hi", 0.85)))
    gap = (yy - b * ph) < float(p.get("gap", 1.0))
    seam = _lv(int(p.get("seam_step", 0)), nr)
    f = np.where(gap, seam, f)
    joints = np.floor(rs.random(planks) * n).astype(int)
    f = np.where((xx == joints[b]) & ~gap, seam, f)
    return np.clip(f, 0, 1)


def g_shingle(rs, n, p):
    """Wood shingles: `rows` courses per tile, staggered vertical gaps, a dark shadow under each course's butt edge
    (exact step 0), per-shingle tone and a few lifted (lighter) shingles."""
    nr = _nr(p)
    rows = int(p.get("rows", 8))
    cols = float(p.get("cols", 5))
    yy, xx = _rows_cols(n)
    rh = n / float(rows)
    r = np.floor(yy / rh).astype(int) % rows
    t = (yy - r * rh) / rh
    offs = rs.random(rows)
    widths = [0.6 + 0.8 * rs.random(32) for _ in range(rows)]
    f = np.zeros((n, n))
    for k in range(rows):
        sel = r == k
        w = widths[k]
        edges = np.concatenate([[0.0], np.cumsum(w)])
        edges = edges / edges[int(round(cols))] if int(round(cols)) < len(edges) else edges / edges[-1]
        uu = ((xx[sel] / n) + offs[k]) % 1.0
        idx = np.searchsorted(edges, uu, side="right") - 1
        tone = rs.random(64)[idx % 64]
        lift = rs.random(64)[(idx + 7) % 64] > 0.85
        face = 0.35 + 0.4 * tone + 0.25 * t[sel] + np.where(lift, 0.25, 0.0)
        val = _in_seg(np.clip(face, 0, 1), (1, nr - 1), nr, 0.1, 0.95)
        left = np.abs(uu - edges[np.clip(idx, 0, len(edges) - 1)]) * n < 0.9
        val = np.where(left, _lv(0, nr), val)
        f[sel] = val
    f = np.where((yy - r * rh) >= rh - float(p.get("shadow", 1.4)), _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_tin(rs, n, p):
    """Corrugated tin: vertical ridges every `period` texels (crest = exact top step of the metal segment, trough =
    exact low step), one lapped sheet seam per tile with nail dots, and rust (second segment) bleeding down from the
    seam and up from the bottom edge (`rust`)."""
    segs, nr = _segs(p)
    metal = segs[0]
    period = float(p.get("period", 4))
    yy, xx = _rows_cols(n)
    ph = (xx % period) / period
    prof = 0.5 + 0.5 * np.cos(ph * 2 * math.pi)
    blot = _blot(rs, n, 3, 2)
    val = 0.15 + 0.6 * prof + 0.25 * blot
    f = _in_seg(np.clip(val, 0, 1), metal, nr, 0.0, 1.0)
    crest = ph < 0.5 / period
    f = np.where(crest, _lv(metal[0] + metal[1] - 1, nr), f)
    seam_y = int(n * float(p.get("seam", 0.42)))
    seam = (yy == seam_y)
    f = np.where(seam, _lv(metal[0], nr), f)
    nails = (yy == seam_y + 1) & (xx % int(period * 3) == 0)
    f = np.where(nails, _lv(metal[0], nr), f)
    rust = float(p.get("rust", 0.0))
    if rust > 0 and len(segs) > 1:
        r = segs[1]
        u, v = T._grid(n)
        d_seam = np.clip(1.0 - np.abs(yy - seam_y) / (n * 0.35), 0, 1) * (yy > seam_y)
        grow = T._norm(T.fbm(rs, n, 5, 3, sx=1, sy=3)) * 0.7 + 0.45 * d_seam + 0.5 * np.clip(0.3 - v, 0, 1)
        m = grow > 1.0 - rust
        f = np.where(m & ~seam, _in_seg(T._norm(T.fbm(rs, n, 6, 2)), r, nr), f)
    return np.clip(f, 0, 1)


# ---------------------------------------------------------------- masonry / plaster
def g_adobe(rs, n, p):
    """Adobe plaster: broad soft blotches, a darker grime band along the bottom (`grime`), a few hairline cracks (exact
    dark step) and optional patches where the plaster has fallen to show mud bricks (`bricks`, exact mortar)."""
    nr = _nr(p)
    u, v = T._grid(n)
    yy, xx = _rows_cols(n)
    big = _blot(rs, n, 2, 2)
    mid = _blot(rs, n, 5, 2)
    val = 0.55 + 0.3 * (big - 0.5) + 0.12 * (mid - 0.5) - float(p.get("grime", 0.25)) * np.clip(0.25 - v, 0, 1) * 3.0
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.2, 1.0)
    bricks = float(p.get("bricks", 0.0))
    if bricks:
        patch = T._norm(T.fbm(rs, n, 3, 2)) > 1.0 - bricks
        rows = 8
        r = np.floor(yy / (n / rows)).astype(int)
        cu = ((xx / (n / 4.0)) + 0.5 * (r % 2)) % 1.0
        mortar = ((yy % (n // rows)) == 0) | (cu * (n / 4.0) < 1.0)
        bv = _in_seg(0.3 + 0.4 * rs.random((rows + 1, 8))[r % rows, (np.floor(xx / (n / 4.0)).astype(int)) % 8], (1, nr - 1), nr, 0.0, 0.6)
        f = np.where(patch, np.where(mortar, _lv(1, nr), bv), f)
    cracks = int(p.get("cracks", 3))
    for _ in range(cracks):
        x = rs.random() * n
        y = rs.random() * n * 0.5
        ang = math.pi / 2 + (rs.random() - 0.5) * 1.2
        L = n * (0.15 + 0.2 * rs.random())
        for s in range(int(L)):
            ang += (rs.random() - 0.5) * 0.6
            x += math.cos(ang)
            y += math.sin(ang)
            f[int(y) % n, int(x) % n] = _lv(0, nr)
    return np.clip(f, 0, 1)


def g_brick(rs, n, p):
    """Running-bond brick: `rows` courses, `cols` bricks per course, mortar on exact step 0, a lit top row per brick
    (exact top step of the brick range) and per-brick tone with soft soot blotches."""
    nr = _nr(p)
    rows, cols = int(p.get("rows", 8)), int(p.get("cols", 4))
    yy, xx = _rows_cols(n)
    rh, cw = n / float(rows), n / float(cols)
    r = np.floor(yy / rh).astype(int) % rows
    sx = xx + (r % 2) * cw * 0.5
    c = np.floor(sx / cw).astype(int) % cols
    tone = rs.random((rows, cols))
    blot = _blot(rs, n, 3, 2)
    val = 0.25 + 0.45 * tone[r, c] + 0.3 * blot
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 0.8)
    top = (yy - r * rh) < 2.0
    f = np.where(top, _lv(nr - 1, nr), f)
    mortar = ((yy - r * rh) < 1.0) | ((sx - np.floor(sx / cw) * cw) < 1.0)
    f = np.where(mortar, _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_fieldstone(rs, n, p):
    """Rubble fieldstone masonry: rounded jittered-Worley stones, mortar (exact step 1 of the ramp, step 0 is the deep
    joint), a lit upper-left crescent per stone and per-stone tone."""
    nr = _nr(p)
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 14)))
    tone = rs.random(int(ids.max()) + 1)
    yy, xx = _rows_cols(n)
    edge = f2 - f1
    val = 0.3 + 0.5 * tone[ids] + 0.2 * (1 - T._norm(f1))
    f = _in_seg(np.clip(val, 0, 1), (2, nr - 2), nr, 0.0, 1.0) if nr > 3 else _in_seg(val, (1, nr - 1), nr)
    gap = float(p.get("gap", 0.035))
    f = np.where(edge < gap * 1.6, _lv(1, nr), f)
    f = np.where(edge < gap * 0.7, _lv(0, nr), f)
    return np.clip(f, 0, 1)


# ---------------------------------------------------------------- rock / ground / plants
def g_strata(rs, n, p):
    """Layered canyon sandstone: horizontal beds of varying thickness and tone (`beds` per tile), gently warped; hard
    beds end in a lit ledge row (exact top step) over a shadowed undercut (exact low step); dark desert-varnish streaks
    run down the face (`varnish`); a few vertical joints (exact step 0)."""
    nr = _nr(p)
    beds = int(p.get("beds", 6))
    yy, xx = _rows_cols(n)
    warp = (T._norm(T.fbm(rs, n, 2, 2, sx=1, sy=1)) - 0.5) * n * float(p.get("warp", 0.08))
    y = (yy + warp) % n
    hts = 0.6 + 0.8 * rs.random(beds)
    edges = np.concatenate([[0.0], np.cumsum(hts / hts.sum())]) * n
    bed = np.clip(np.searchsorted(edges, y, side="right") - 1, 0, beds - 1)
    tone = rs.random(beds)
    hard = rs.random(beds) > 0.45
    t = (y - edges[bed]) / np.maximum(1.0, edges[bed + 1] - edges[bed])
    blot = _blot(rs, n, 4, 2)
    val = 0.18 + 0.5 * tone[bed] + 0.22 * blot + 0.1 * (1 - t)
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 0.85)
    ledge = hard[bed] & ((y - edges[bed]) < 1.0)
    under = hard[(bed + 1) % beds] & ((edges[bed + 1] - y) < 1.2)
    f = np.where(ledge, _lv(nr - 1, nr), f)
    f = np.where(under & ~ledge, _lv(1, nr), f)
    var = float(p.get("varnish", 0.3))
    if var > 0:
        cols = T._norm(T.fbm(rs, n, 6, 2, sx=4, sy=0.4))
        streak = cols > 1.0 - var * 0.5
        f = np.where(streak & ~ledge, np.maximum(_lv(1, nr), f - 1.0 / max(1, nr - 1)), f)
    for _ in range(int(p.get("joints", 2))):
        jx = int(rs.random() * n)
        y0 = int(rs.random() * n)
        L = int(n * (0.2 + 0.3 * rs.random()))
        for s in range(L):
            f[(y0 + s) % n, (jx + int(1.5 * math.sin(s * 0.3))) % n] = _lv(0, nr)
    return np.clip(f, 0, 1)


def g_desert(rs, n, p):
    """Desert ground: big painted blotches (1-3 m), sparse pebbles (a dark texel under a lit texel, exact steps) and
    optional wheel `ruts` running along v (two darker wobbling bands with a lighter crown between them)."""
    nr = _nr(p)
    u, v = T._grid(n)
    yy, xx = _rows_cols(n)
    big = _blot(rs, n, int(p.get("lattice", 2)), 2)
    mid = _blot(rs, n, 4, 2)
    val = 0.5 + float(p.get("contrast", 0.8)) * (0.6 * (big - 0.5) + 0.3 * (mid - 0.5))
    ruts = float(p.get("ruts", 0.0))
    if ruts:
        wob = 0.025 * np.sin(v * 2 * math.pi + 1.3)
        for c in (0.3, 0.7):
            d = np.abs(u - c - wob)
            val = val - ruts * np.clip(1.0 - d / 0.06, 0, 1)
            val = val + 0.5 * ruts * np.clip(1.0 - np.abs(d - 0.075) / 0.025, 0, 1)
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 1.0)
    peb = float(p.get("pebbles", 0.0))
    if peb:
        cnt = int(peb * n * n / 64)
        px = rs.integers(0, n, cnt)
        py = rs.integers(0, n, cnt)
        f[py, px] = _lv(0, nr)
        f[(py - 1) % n, px] = _lv(nr - 1, nr)
    return np.clip(f, 0, 1)


def g_sage(rs, n, p):
    """Sage / scrub foliage: clumps of small leaf clusters (Worley blobs) lit from the upper left, dark gaps between
    clusters (exact step 0) and a few twig strokes."""
    nr = _nr(p)
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 22)))
    yy, xx = _rows_cols(n)
    tone = rs.random(int(ids.max()) + 1)
    u, v = T._grid(n)
    lit = np.clip(1.0 - T._norm(f1) * 1.4, 0, 1)
    val = 0.2 + 0.45 * tone[ids] + 0.35 * lit
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 1.0)
    f = np.where((f2 - f1) < float(p.get("gap", 0.03)), _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_ribs(rs, n, p):
    """Cactus skin: `ribs` vertical ribs per tile, each a lit crest line (exact top step) between shaded grooves
    (exact step 0), soft vertical tone and sparse spine areoles along the crests (exact step 1)."""
    nr = _nr(p)
    ribs = int(p.get("ribs", 8))
    yy, xx = _rows_cols(n)
    rw = n / float(ribs)
    s = (xx % rw) / rw
    prof = np.sin(s * math.pi)
    blot = _blot(rs, n, 2, 2)
    val = 0.15 + 0.6 * prof + 0.25 * blot
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 0.85)
    crest = np.abs(s - 0.5) * rw < 0.5
    f = np.where(crest, _lv(nr - 1, nr), f)
    groove = (s * rw) < 0.8
    f = np.where(groove, _lv(0, nr), f)
    areole = crest & ((yy % int(p.get("areole", 5))) == 0)
    f = np.where(areole, _lv(1, nr), f)
    return np.clip(f, 0, 1)


# ---------------------------------------------------------------- interiors / signs
def g_wallpaper(rs, n, p):
    """Saloon wallpaper: alternating wide and narrow vertical stripes (two steps), a small diamond lattice motif in
    the wide stripes (exact step), broad ageing blotches and a darker band near the top (`soot`)."""
    nr = _nr(p)
    stripes = int(p.get("stripes", 4))
    yy, xx = _rows_cols(n)
    u, v = T._grid(n)
    sw = n / float(stripes)
    s = (xx % sw) / sw
    wide = s < 0.72
    blot = _blot(rs, n, 2, 2)
    base = np.where(wide, 0.55, 0.32) + 0.18 * (blot - 0.5) - float(p.get("soot", 0.15)) * np.clip(v - 0.8, 0, 1) * 4.0
    f = _in_seg(np.clip(base, 0, 1), (1, nr - 1), nr, 0.0, 0.9)
    cell = max(4, int(sw * 0.72 / 2))
    cx = (xx % sw) - sw * 0.36
    cy = (yy % cell) - cell / 2.0
    diamond = wide & (np.abs(cx) + np.abs(cy) <= 1.0)
    f = np.where(diamond, _lv(nr - 1, nr), f)
    edge = np.abs(s - 0.72) * sw < 0.6
    f = np.where(edge, _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_shelves(rs, n, p):
    """Back-bar shelving: `shelves` boards per tile (lit top edge, shaded underside on exact steps) with rows of bottle
    and jar silhouettes in the bottle segment (tall-necked, short, square), dark wall between them."""
    segs, nr = _segs(p)
    wood = segs[0]
    glass = segs[1] if len(segs) > 1 else segs[0]
    shelves = int(p.get("shelves", 2))
    yy, xx = _rows_cols(n)
    sh = n / float(shelves)
    f = np.full((n, n), _lv(0, nr))
    board = max(2, int(sh * 0.14))
    k = np.floor(yy / sh).astype(int)
    t = yy - k * sh
    f = np.where(t >= sh - board, _in_seg(0.5, wood, nr), f)
    f = np.where(t >= sh - board, np.where(t < sh - board + 1, _lv(wood[0] + wood[1] - 1, nr), f), f)
    for row in range(shelves):
        x = 1.0 + rs.random() * 2
        y_base = row * sh + sh - board
        while x < n - 2:
            kind = rs.random()
            w = 3 if kind < 0.55 else (5 if kind < 0.85 else 4)
            h = sh * (0.62 if kind < 0.55 else (0.4 if kind < 0.85 else 0.5)) * (0.85 + 0.25 * rs.random())
            tone = 0.2 + 0.7 * rs.random()
            for xi in range(int(x), int(x + w)):
                for yi in range(int(y_base - h), int(y_base)):
                    neck = kind < 0.55 and yi < y_base - h * 0.62 and (xi == int(x) or xi == int(x + w - 1))
                    if neck:
                        continue
                    hi = (xi == int(x) + (1 if kind < 0.55 else 0)) and yi > y_base - h * 0.7
                    f[yi % n, xi % n] = _lv(glass[0] + glass[1] - 1, nr) if hi else _in_seg(tone, glass, nr, 0.0, 0.8)
            x += w + 1 + int(rs.random() * 2.5)
    return np.clip(f, 0, 1)


def g_poster(rs, n, p):
    """Blank notice / wanted poster: aged paper (soft blotches, a darker edge vignette), a printed double border
    (exact dark steps), an empty heading block and an empty portrait frame; pin dots in the corners. No text."""
    nr = _nr(p)
    u, v = T._grid(n)
    yy, xx = _rows_cols(n)
    blot = _blot(rs, n, 3, 2)
    edge = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    val = 0.75 + 0.2 * (blot - 0.5) - 0.5 * np.clip(0.08 - edge, 0, 1) * 6
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.4, 1.0)
    b1 = max(2, n // 16)
    ring = lambda d: ((xx == d) | (xx == n - 1 - d) | (yy == d) | (yy == n - 1 - d)) & (xx >= d) & (xx <= n - 1 - d) & (yy >= d) & (yy <= n - 1 - d)
    f = np.where(ring(b1) | ring(b1 + 2), _lv(0, nr), f)
    head = (yy >= b1 + 4) & (yy < b1 + 4 + n // 8) & (xx >= b1 + 5) & (xx <= n - b1 - 6)
    f = np.where(head, _lv(1, nr), f)
    fr = (yy >= n * 0.36) & (yy <= n * 0.78) & (xx >= n * 0.28) & (xx <= n * 0.72)
    frin = (yy >= n * 0.36 + 2) & (yy <= n * 0.78 - 2) & (xx >= n * 0.28 + 2) & (xx <= n * 0.72 - 2)
    f = np.where(fr & ~frin, _lv(0, nr), f)
    f = np.where(frin, _in_seg(0.55 + 0.2 * (blot - 0.5), (1, nr - 1), nr, 0.4, 1.0), f)
    for (cx, cy) in ((b1 + 1, b1 + 1), (n - b1 - 2, b1 + 1)):
        f[cy, cx] = _lv(0, nr)
    return np.clip(f, 0, 1)


def g_signboard(rs, n, p):
    """Blank painted sign board: `boards` horizontal planks (exact dark seams), a painted border band inset from the
    edge (exact top step) around an empty field, paint flaking to bare wood in places (`flake`). No lettering."""
    nr = _nr(p)
    boards = int(p.get("boards", 3))
    yy, xx = _rows_cols(n)
    u, v = T._grid(n)
    bh = n / float(boards)
    b = np.floor(yy / bh).astype(int)
    blot = _blot(rs, n, 3, 2)
    val = 0.45 + 0.25 * (blot - 0.5) + 0.1 * rs.random(boards + 1)[b]
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.2, 0.7)
    seam = (yy - b * bh) < 1.0
    f = np.where(seam & (yy > 0), _lv(0, nr), f)
    m = max(2, n // 12)
    band = ((np.abs(xx - m) < 1) | (np.abs(xx - (n - 1 - m)) < 1) | (np.abs(yy - m) < 1) | (np.abs(yy - (n - 1 - m)) < 1)) & \
        (xx >= m - 1) & (xx <= n - m) & (yy >= m - 1) & (yy <= n - m)
    f = np.where(band, _lv(nr - 1, nr), f)
    flake = float(p.get("flake", 0.15))
    if flake:
        fl = T._norm(T.fbm(rs, n, 6, 3)) > 1.0 - flake
        f = np.where(fl & ~band, _lv(1, nr), f)
    return np.clip(f, 0, 1)


def g_window(rs, n, p):
    """Painted window: `cols` x `rows` panes in a frame (bars and frame on exact step 0), each pane a diagonal
    reflection gradient (darker lower right) and optional side `curtain` bands. The pack ramp decides day panes (dark,
    sky glint) or lit night panes (warm)."""
    nr = _nr(p)
    cols, rows = int(p.get("cols", 2)), int(p.get("rows", 3))
    yy, xx = _rows_cols(n)
    u, v = T._grid(n)
    fw = max(2, n // 12)
    inner = (xx >= fw) & (xx < n - fw) & (yy >= fw) & (yy < n - fw)
    pu = (xx - fw) / max(1.0, n - 2 * fw)
    pv = (yy - fw) / max(1.0, n - 2 * fw)
    cu = (pu * cols) % 1.0
    cv = (pv * rows) % 1.0
    bar_u = (cu * (n - 2 * fw) / cols) < 1.0
    bar_v = (cv * (n - 2 * fw) / rows) < 1.0
    refl = 0.75 - 0.5 * (0.6 * cu + 0.4 * cv) + 0.25 * np.clip(0.35 - np.abs(cu - cv * 0.8 - 0.1), 0, 1) * 2.0
    f = _in_seg(np.clip(refl, 0, 1), (1, nr - 1), nr, 0.0, 1.0)
    cur = float(p.get("curtain", 0.0))
    if cur:
        side = (pu < cur) | (pu > 1 - cur)
        f = np.where(side & inner, _in_seg(0.45 + 0.15 * np.sin(pu * 60), (1, nr - 1), nr, 0.2, 0.7), f)
    f = np.where(~inner | bar_u | bar_v, _lv(0, nr), f)
    return np.clip(f, 0, 1)


def g_door(rs, n, p):
    """Plank door: `boards` vertical boards (exact dark seams), two horizontal ledges and a diagonal brace (lit top
    edges on exact steps, the classic Z), per-board tone and a dark handle dot."""
    nr = _nr(p)
    boards = int(p.get("boards", 4))
    yy, xx = _rows_cols(n)
    u, v = T._grid(n)
    bw = n / float(boards)
    b = np.floor(xx / bw).astype(int) % boards
    grain = T._norm(T.fbm(rs, n, 2, 3, sx=1, sy=6))
    val = 0.3 + 0.35 * rs.random(boards)[b] + 0.2 * grain
    f = _in_seg(np.clip(val, 0, 1), (1, nr - 1), nr, 0.0, 0.75)
    f = np.where((xx - b * bw) < 1.0, _lv(0, nr), f)
    lh = max(2, n // 10)
    for yc in (0.2, 0.8):
        y0 = int(n * yc)
        led = (yy >= y0) & (yy < y0 + lh)
        f = np.where(led, _in_seg(0.6, (1, nr - 1), nr, 0.3, 0.9), f)
        f = np.where(yy == y0, _lv(nr - 1, nr), f)
        f = np.where(yy == y0 + lh, _lv(0, nr), f)
    y_a, y_b = int(n * 0.8) - 1, int(n * 0.2) + lh
    for xi in range(n):
        yc = y_a + (y_b - y_a) * (xi / max(1, n - 1))
        for d in range(lh - 1):
            yi = int(yc) + d - lh // 2
            if 0 <= yi < n:
                f[yi, xi] = _in_seg(0.65, (1, nr - 1), nr, 0.3, 0.9) if d else _lv(nr - 1, nr)
    hx, hy = int(n * 0.82), int(n * 0.52)
    f[hy:hy + 2, hx:hx + 2] = _lv(0, nr)
    return np.clip(f, 0, 1)


def g_wheel(rs, n, p):
    """Painted spoked wheel for a disc face (normalized UVs, centre at the texture centre): an iron tyre ring (exact
    top step on its outer edge), a wooden felloe band, `spokes` tapered spokes from a hub, dark gaps between spokes
    (exact step 0: reads as shadow through the wheel)."""
    nr = _nr(p)
    yy, xx = _rows_cols(n)
    cx = cy = (n - 1) / 2.0
    dx, dy = (xx - cx) / (n / 2.0), (yy - cy) / (n / 2.0)
    r = np.sqrt(dx * dx + dy * dy)
    a = np.arctan2(dy, dx)
    k = int(p.get("spokes", 10))
    f = np.full((n, n), _lv(0, nr))
    tone = _blot(rs, n, 3, 2)
    spoke = np.abs(((a / (2 * math.pi) * k) % 1.0) - 0.5) * 2.0          # 1 at spoke centre lines
    width = 0.5 + 0.2 * (1 - r)
    on_spoke = (spoke > width) & (r < 0.8) & (r > 0.18)
    f = np.where(on_spoke, _in_seg(0.55 + 0.3 * tone, (1, nr - 1), nr, 0.2, 0.8), f)
    f = np.where((r >= 0.68) & (r < 0.86), _in_seg(0.45 + 0.3 * tone, (1, nr - 1), nr, 0.1, 0.7), f)
    f = np.where((r >= 0.86) & (r < 1.01), _lv(1, nr), f)
    f = np.where((r >= 0.94) & (r < 1.01), _lv(nr - 1, nr), f)
    f = np.where(r < 0.2, _in_seg(0.6, (1, nr - 1), nr, 0.3, 0.9), f)
    f = np.where(r < 0.08, _lv(nr - 1, nr), f)
    return np.clip(f, 0, 1)


# ---------------------------------------------------------------- sky
def g_wk_sky(rs, n, p):
    """Frontier sky dome (u = azimuth, v = elevation over the wsky dome: v = 0 at `v_horizon` below... see the wsky
    generator; rows top->bottom = zenith->below horizon). Ramp layout: `mesa` steps first (distant butte silhouettes),
    then the sky gradient from ZENITH to HORIZON. `glow` (step offset from the horizon, optional) paints a warm band
    just above the horizon (golden hour); `clouds` paints flat streaks of a light step; `stars` single texels."""
    nr = _nr(p)
    m = int(p.get("mesa", 2))
    sky0 = m
    sky1 = nr - 1
    u, v = T._grid(n)
    yy, xx = _rows_cols(n)
    vh = float(p.get("v_horizon", 0.1))
    top = float(p.get("v_top", 1.0))
    e = np.clip((v - vh) / max(1e-6, top - vh), 0, 1)                 # 0 at the horizon, 1 at the zenith
    grad = 1.0 - e ** float(p.get("gamma", 0.55))
    f = (sky0 + (sky1 - sky0) * grad) / max(1, nr - 1)
    hz = float(p.get("haze", 0.06))                                    # exact horizon (fog colour) band height
    f = np.where(e < hz, _lv(sky1, nr), f)
    glow = p.get("glow")
    if glow:
        g = np.clip(1.0 - np.abs(e - float(glow.get("at", 0.12))) / float(glow.get("height", 0.08)), 0, 1)
        gl = _lv(int(glow["step"]), nr)
        f = np.where(g > 0.5, gl, np.where(g > 0.0, f + (gl - f) * (g / 0.5), f))
    cl = p.get("clouds")
    if cl:
        streak = T._norm(T.fbm(rs, n, 2, 3, sx=1, sy=float(cl.get("stretch", 6))))
        band = np.clip(1.0 - np.abs(e - float(cl.get("at", 0.45))) / float(cl.get("height", 0.25)), 0, 1)
        c = streak * band
        thr = float(cl.get("cover", 0.55))
        f = np.where(c > thr, _lv(int(cl["step"]), nr), f)
        f = np.where((c > thr - 0.06) & (c <= thr), (_lv(int(cl["step"]), nr) + f) * 0.5, f)
    st = p.get("stars")
    if st:
        cnt = int(st.get("count", 60))
        sx = rs.integers(0, n, cnt)
        sy = rs.integers(0, n, cnt)
        keep = e[sy, sx] > float(st.get("min_e", 0.2))
        f[sy[keep], sx[keep]] = _lv(int(st["step"]), nr)
    if m > 0 and p.get("mesas", True):
        k = int(p.get("buttes", 7))
        hgt = np.zeros(n)
        cs = np.sort(rs.random(k))
        for i, c in enumerate(cs):
            w = 0.04 + 0.08 * rs.random()
            h = float(p.get("mesa_h", 0.05)) * (0.45 + 0.75 * rs.random())
            d = np.abs((np.arange(n) + 0.5) / n - c)
            d = np.minimum(d, 1 - d)
            shoulder = w * 0.22
            prof = np.where(d < w - shoulder, h, np.where(d < w, h * (w - d) / shoulder * 0.85, 0.0))
            hgt = np.maximum(hgt, prof)
        lowband = float(p.get("mesa_base", 0.012))
        f = np.where(v < vh, _lv(sky1, nr), f)
        sil = (e <= (hgt[None, :] + lowband)) & (v >= vh - 0.03) & (hgt[None, :] > 0)
        lit = sil & (e > hgt[None, :] + lowband - 0.014)
        f = np.where(sil, _lv(0, nr), f)
        if m > 1:
            f = np.where(lit, _lv(1, nr), f)
    else:
        f = np.where(v < vh, _lv(sky1, nr), f)
    return np.clip(f, 0, 1)


GENS = {
    "wk_clapboard": g_clapboard, "wk_battens": g_battens, "wk_deck": g_deck, "wk_shingle": g_shingle, "wk_tin": g_tin,
    "wk_adobe": g_adobe, "wk_brick": g_brick, "wk_fieldstone": g_fieldstone, "wk_strata": g_strata,
    "wk_desert": g_desert, "wk_sage": g_sage, "wk_ribs": g_ribs, "wk_wallpaper": g_wallpaper, "wk_shelves": g_shelves,
    "wk_poster": g_poster, "wk_signboard": g_signboard, "wk_window": g_window, "wk_door": g_door, "wk_sky": g_wk_sky,
    "wk_wheel": g_wheel,
}
for _name, _fn in GENS.items():
    if _name in T.FIELD_GENS and T.FIELD_GENS[_name] is not _fn:
        raise RuntimeError("texture generator name clash: %s" % _name)
    T.FIELD_GENS[_name] = _fn
