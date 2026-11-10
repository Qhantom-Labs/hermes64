"""ANCIENTKIT painted texture fields (theme-agnostic; every texel ends up a pack palette colour).

Field generators in the kits/core/texgen.py contract: (rs, n, params) -> float field in [0, 1], row 0 = TOP of the
image, tileable unless a recipe is used on normalized-UV panels. They are registered into texgen.FIELD_GENS under an
`anc_` prefix when this module is imported (by the ANCIENTKIT generator modules), so no core file changes and no name
can collide with the core or another lane's generators.

Painting rules (docs/N64-LOOK-CONVENTIONS.md): soft mid-frequency structure, short ramps, lit top edges and shadowed
bottom edges painted into the texture (the way N64 artists painted light into stone), low per-texel noise so the
convention's mottle quantization and three-point filtering give the soft blotchy look. Carvings are painted, never
modelled. The glyphs come from an original shape grammar on a 3x3 lattice (no real script is intentionally copied;
visual review is still needed because a shape grammar is not a real-script resemblance classifier).
"""
import math

import numpy as np

from . import texgen as T

# ---------------------------------------------------------------- small numpy helpers


def _uv(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    return (xx + 0.5) / n, 1.0 - (yy + 0.5) / n          # u right, v up (row 0 = top)


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _wrapd(a):
    """Wrapped distance on the unit interval (tileable)."""
    a = np.abs(a) % 1.0
    return np.minimum(a, 1.0 - a)


def _blur(f, passes=1):
    return T.soften(f, passes)


def _segment(field_lo, field_hi, mask, split=0.5):
    """Two hue families on one ramp (stone steps then moss steps): mask 0 -> [0, split), 1 -> [split, 1]."""
    lo = np.clip(field_lo, 0.0, 1.0) * (split - 0.02)
    hi = split + np.clip(field_hi, 0.0, 1.0) * (1.0 - split)
    return np.where(mask > 0.5, hi, lo)


def _shift(m, du, dv):
    """Shift a field by whole texels (wrapped): du right, dv up."""
    return np.roll(np.roll(m, int(du), axis=1), -int(dv), axis=0)


def _emboss(mask, k=1):
    """Light from the top-left: + on lit edges of raised shapes, - on shadowed edges (wrapped, in texels)."""
    return _shift(mask, k, -k) - _shift(mask, -k, k)


# ---------------------------------------------------------------- sandstone / masonry


def g_ashlar(rs, n, p):
    """Dressed sandstone courses: big blocks per row (staggered), soft per-block tone, a painted top light and bottom
    shade inside each block, worn joints, chipped corners and weathering blotches. params: rows, cols (blocks per
    row, float), joint (texels), weather (0..1), chip (0..1), lit (0..1), stagger (0..1), drift (sand in joints)."""
    u, v = _uv(n)
    rows = int(p.get("rows", 4))
    cols = float(p.get("cols", 1.5))
    jt = float(p.get("joint", 1.0)) / n
    r = np.floor(v * rows).astype(int) % rows
    fv = (v * rows) % 1.0
    offs = rs.random(rows + 1) * float(p.get("stagger", 1.0))
    widths = 0.6 + 0.8 * rs.random((rows + 1, 8))
    uu = (u + offs[r]) % 1.0
    # irregular block widths per row: cumulative, normalised so each row tiles
    k = max(1, int(round(cols)))
    edges = np.cumsum(widths[:, :k], axis=1)
    edges = edges / edges[:, -1:]
    idx = np.zeros_like(uu, dtype=int)
    left = np.zeros_like(uu)
    right = np.ones_like(uu)
    for j in range(k):
        e1 = edges[r, j]
        e0 = np.where(j == 0, 0.0, edges[r, j - 1]) if j else np.zeros_like(uu)
        inside = (uu >= e0) & (uu < e1)
        idx = np.where(inside, j, idx)
        left = np.where(inside, e0, left)
        right = np.where(inside, e1, right)
    fu = (uu - left) / np.maximum(right - left, 1e-6)
    bw = (right - left)
    tone = rs.random((rows + 1, 9))[r, idx]
    body_lo, body_hi = float(p.get("body_lo", 0.32)), float(p.get("body_hi", 0.82))
    f = body_lo + (body_hi - body_lo) * (0.45 + 0.55 * tone)
    # painted light inside the block: brighter top, darker bottom (soft)
    lit = float(p.get("lit", 0.5))
    f = f + lit * 0.22 * (_sstep(0.55, 1.0, fv) - 0.6 * _sstep(0.35, 0.0, fv))
    # weathering: low-frequency blotches + a few soft vertical rain streaks
    w = float(p.get("weather", 0.5))
    f = f + w * 0.22 * (T._norm(T.fbm(rs, n, 3, 3)) - 0.5)
    f = f + w * 0.10 * (T._norm(T.fbm(rs, n, 2, 2, sx=6, sy=0.5)) - 0.5)
    # joints (worn, slightly soft) and chipped corners
    ju = np.minimum(fu, 1 - fu) * bw          # distance to the vertical joint in u units
    jv = np.minimum(fv, 1 - fv) / rows        # distance to the horizontal joint in v units
    chip = float(p.get("chip", 0.5))
    cnoise = T._norm(T.fbm(rs, n, 6, 2))
    corner = (ju < jt * (1.6 + 3.0 * chip * cnoise)) & (jv < jt * (1.6 + 3.0 * chip * cnoise))
    joint = (ju < jt) | (jv < jt) | corner
    jval = float(p.get("joint_level", 0.06))
    edge_lit = (jv < jt * 2.2) & (fv > 0.5) & ~joint          # lit lip under the joint above
    f = np.where(edge_lit, f + 0.08 * lit, f)
    drift = float(p.get("drift", 0.0))
    if drift > 0:  # sand settled in the lower joints
        jval = jval + drift * (fv < 0.5)
    f = np.where(joint, jval, f)
    return np.clip(f, 0.0, 1.0)


def g_dressed(rs, n, p):
    """Smooth dressed stone for mouldings, shafts and slabs: a soft vertical gradient, faint tool streaks and gentle
    blotches (no joints). params: streak, blotch, grad."""
    u, v = _uv(n)
    f = 0.55 + float(p.get("grad", 0.12)) * (v - 0.5)
    f = f + float(p.get("blotch", 0.3)) * 0.4 * (T._norm(T.fbm(rs, n, 3, 3)) - 0.5)
    f = f + float(p.get("streak", 0.3)) * 0.25 * (T._norm(T.fbm(rs, n, 2, 2, sx=8, sy=0.5)) - 0.5)
    return np.clip(f, 0.0, 1.0)


def g_rubble(rs, n, p):
    """Rough weathered stone: Voronoi chunks with soft facets (lit up-left), dark cracks, eroded pits."""
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 7)))
    tone = rs.random(ids.max() + 1)[ids]
    facet = 1.0 - T._norm(f1)
    f = 0.3 + 0.35 * tone + 0.28 * facet + 0.15 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    crack = (f2 - f1) < float(p.get("crack", 0.022))
    f = np.where(crack, 0.06, f)
    return np.clip(f, 0.0, 1.0)


def g_paving(rs, n, p):
    """Large worn flagstones in offset rows with sand-filled joints; slabs keep a soft worn centre and a few cracks.
    params: rows, cols, joint (texels), sand (joint level 0..1), crack."""
    u, v = _uv(n)
    rows = int(p.get("rows", 3))
    cols = int(p.get("cols", 2))
    jt = float(p.get("joint", 1.2)) / n
    r = np.floor(v * rows).astype(int) % rows
    fv = (v * rows) % 1.0
    offs = rs.random(rows + 1)
    uu = (u + offs[r]) % 1.0
    c = np.floor(uu * cols).astype(int) % cols
    fu = (uu * cols) % 1.0
    tone = rs.random((rows + 1, cols + 1))[r, c]
    worn = 1.0 - np.sqrt((fu - 0.5) ** 2 + (fv - 0.5) ** 2) * 1.2
    f = 0.38 + 0.3 * tone + 0.14 * worn + 0.16 * (T._norm(T.fbm(rs, n, 3, 3)) - 0.5)
    crack_noise = T._norm(T.fbm(rs, n, 5, 2, sx=3, sy=1))
    crack = (np.abs(crack_noise - 0.5) < float(p.get("crack", 0.012))) & (tone > 0.55)
    f = np.where(crack, 0.1, f)
    joint = (np.minimum(fu, 1 - fu) / cols < jt) | (np.minimum(fv, 1 - fv) / rows < jt)
    f = np.where(joint, float(p.get("sand", 0.8)), f)
    return np.clip(f, 0.0, 1.0)


def g_coffer(rs, n, p):
    """Coffered ceiling: recessed square panels with a lit lower rim and a shadowed upper rim (seen from below)."""
    u, v = _uv(n)
    k = int(p.get("cells", 2))
    fu, fv = (u * k) % 1.0, (v * k) % 1.0
    d = np.maximum(np.abs(fu - 0.5), np.abs(fv - 0.5))
    rim = (d > 0.34) & (d < 0.42)
    recess = d <= 0.34
    f = np.full_like(u, 0.62)
    f = np.where(rim & (fv < 0.5), 0.8, np.where(rim, 0.3, f))
    f = np.where(recess, 0.42 + 0.12 * (0.34 - d) / 0.34, f)
    f = f + 0.12 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    return np.clip(f, 0.0, 1.0)


# ---------------------------------------------------------------- carved relief and glyphs


def _disc(u, v, cx, cy, r):
    return np.sqrt((u - cx) ** 2 + (v - cy) ** 2) < r


def _ring(u, v, cx, cy, r0, r1):
    d = np.sqrt((u - cx) ** 2 + (v - cy) ** 2)
    return (d >= r0) & (d < r1)


def _rect(u, v, x0, y0, x1, y1):
    return (u >= x0) & (u < x1) & (v >= y0) & (v < y1)


def _trap(u, v, cx, y0, y1, w0, w1):
    t = np.clip((v - y0) / max(y1 - y0, 1e-6), 0, 1)
    w = w0 + (w1 - w0) * t
    return (v >= y0) & (v < y1) & (np.abs(u - cx) < w / 2)


def _rays(u, v, cx, cy, r0, r1, count, width, phase=0.0):
    d = np.sqrt((u - cx) ** 2 + (v - cy) ** 2)
    a = np.arctan2(v - cy, u - cx) + phase
    s = np.abs(np.sin(a * count / 2.0))
    return (d >= r0) & (d < r1) & (s < width)


def motif_mask(name, u, v, rs):
    """Raised-area mask of an ORIGINAL relief motif on a unit panel (u right, v up)."""
    m = np.zeros_like(u, dtype=bool)
    if name == "sunwheel":
        # a rayed disc over three stepped bars: the "patient sun" emblem of the kit
        m |= _disc(u, v, 0.5, 0.58, 0.13)
        m |= _ring(u, v, 0.5, 0.58, 0.17, 0.205)
        m |= _rays(u, v, 0.5, 0.58, 0.23, 0.33, 12, 0.22)
        for i, w in enumerate((0.62, 0.46, 0.3)):
            m |= _rect(u, v, 0.5 - w / 2, 0.2 - i * 0.06 + 0.06, 0.5 + w / 2, 0.2 - i * 0.06 + 0.1)
    elif name == "procession":
        # three abstract bearers (round head, bell robe, raised arms carrying discs) between two wave bands
        for i, cx in enumerate((0.2, 0.5, 0.8)):
            m |= _disc(u, v, cx, 0.66, 0.055)
            m |= _trap(u, v, cx, 0.24, 0.58, 0.2, 0.08)
            m |= _rect(u, v, cx - 0.11, 0.56, cx + 0.11, 0.6)
            m |= _rect(u, v, cx - 0.11, 0.6, cx - 0.085, 0.76)
            m |= _rect(u, v, cx + 0.085, 0.6, cx + 0.11, 0.76)
            m |= _disc(u, v, cx, 0.82, 0.045 + 0.01 * (i == 1))
        wave_t = 0.9 + 0.025 * np.sin(u * math.tau * 4)
        wave_b = 0.12 + 0.025 * np.sin(u * math.tau * 4 + 1.5)
        m |= np.abs(v - wave_t) < 0.02
        m |= np.abs(v - wave_b) < 0.02
    elif name == "tree":
        # a branching tree of life with fruit discs and a root arc
        m |= _rect(u, v, 0.47, 0.18, 0.53, 0.7)
        for k, (y, s) in enumerate(((0.36, 0.22), (0.5, 0.18), (0.64, 0.13))):
            for sx in (-1, 1):
                t = np.clip((u - 0.5) * sx / s, 0, 1)
                curve = y + 0.12 * t * t
                m |= (np.abs(v - curve) < 0.022) & ((u - 0.5) * sx >= 0) & ((u - 0.5) * sx < s)
                m |= _disc(u, v, 0.5 + sx * s, y + 0.12 + 0.03, 0.04)
        m |= _disc(u, v, 0.5, 0.78, 0.06)
        m |= _ring(u, v, 0.5, 0.06, 0.16, 0.2) & (v > 0.1)
    elif name == "waves":
        for k in range(4):
            y = 0.18 + k * 0.21
            m |= np.abs(v - (y + 0.05 * np.sin(u * math.tau * 3 + k))) < 0.03
            m |= _disc(u, v, (0.17 + 0.33 * k) % 1.0, y + 0.1, 0.035)
    elif name == "stars":
        m |= _ring(u, v, 0.5, 0.5, 0.32, 0.36)
        pts = [(0.5, 0.5)] + [(0.5 + 0.22 * math.cos(a), 0.5 + 0.22 * math.sin(a)) for a in np.linspace(0, math.tau, 7)[:-1]]
        for x, y in pts:
            m |= _disc(u, v, x, y, 0.035)
        for x, y in pts[1:]:
            t = np.clip(((u - 0.5) * (x - 0.5) + (v - 0.5) * (y - 0.5)) / ((x - 0.5) ** 2 + (y - 0.5) ** 2), 0, 1)
            d = np.sqrt((u - 0.5 - t * (x - 0.5)) ** 2 + (v - 0.5 - t * (y - 0.5)) ** 2)
            m |= d < 0.012
    else:
        raise ValueError("unknown relief motif %r" % name)
    return m


def g_relief(rs, n, p):
    """Carved relief panel (normalized UVs): a raised frame and an ORIGINAL motif, embossed with a painted top-left
    light; the sunk ground keeps a soft weathering. params: motif, frame (0..0.2), depth (emboss strength), weather."""
    u, v = _uv(n)
    fr = float(p.get("frame", 0.08))
    inner = _rect(u, v, fr, fr, 1 - fr, 1 - fr)
    frame = ~inner
    mu = (u - fr) / (1 - 2 * fr)
    mv = (v - fr) / (1 - 2 * fr)
    mot = motif_mask(p.get("motif", "sunwheel"), mu, mv, rs) & inner
    raised = (frame | mot).astype(np.float64)
    base = 0.42 + 0.24 * raised
    e = _emboss(raised, max(1, n // 64))
    base = base + float(p.get("depth", 0.22)) * e
    base = base + float(p.get("weather", 0.4)) * 0.2 * (T._norm(T.fbm(rs, n, 3, 3)) - 0.5)
    return np.clip(base, 0.0, 1.0)


LATTICE = [(x, y) for y in (0.0, 0.5, 1.0) for x in (0.0, 0.5, 1.0)]


def glyph(rs):
    """One original glyph: 2-4 strokes on a 3x3 lattice (bars between lattice points, rings, dots, a crescent).
    Returns a list of primitives in the unit cell (x right, y up)."""
    prims = []
    kinds = ["bar", "bar", "ring", "dot", "arc", "hook"]
    count = 2 + int(rs.integers(0, 3))
    used = set()
    for _ in range(count):
        k = kinds[int(rs.integers(0, len(kinds)))]
        if k == "bar" or k == "hook":
            a, b = rs.choice(9, 2, replace=False)
            if (min(a, b), max(a, b)) in used:
                continue
            used.add((min(a, b), max(a, b)))
            pa, pb = LATTICE[int(a)], LATTICE[int(b)]
            prims.append(("bar", pa, pb))
            if k == "hook":
                d = (pb[1] - pa[1], -(pb[0] - pa[0]))
                ln = math.hypot(*d) or 1.0
                prims.append(("bar", pb, (pb[0] + 0.35 * d[0] / ln, pb[1] + 0.35 * d[1] / ln)))
        elif k == "ring":
            c = LATTICE[int(rs.integers(0, 9))]
            prims.append(("ring", c, 0.18 + 0.1 * float(rs.random())))
        elif k == "dot":
            c = LATTICE[int(rs.integers(0, 9))]
            prims.append(("dot", c, 0.09))
        else:
            c = LATTICE[4]
            prims.append(("arc", c, 0.34, float(rs.random()) * math.tau))
    if not any(pr[0] in ("ring", "dot", "arc") for pr in prims):
        prims.append(("dot", LATTICE[int(rs.integers(0, 9))], 0.09))
    return prims


def glyph_mask(prims, gu, gv, stroke=0.085):
    """Rasterise glyph primitives into a boolean mask over cell coordinates gu, gv in [0, 1] (margin applied)."""
    x = (gu - 0.18) / 0.64
    y = (gv - 0.18) / 0.64
    m = np.zeros_like(gu, dtype=bool)
    for pr in prims:
        if pr[0] == "bar":
            (ax, ay), (bx, by) = pr[1], pr[2]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1e-9
            t = np.clip(((x - ax) * dx + (y - ay) * dy) / L2, 0, 1)
            m |= np.sqrt((x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2) < stroke
        elif pr[0] == "ring":
            (cx, cy), r = pr[1], pr[2]
            d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            m |= np.abs(d - r) < stroke * 0.8
        elif pr[0] == "dot":
            (cx, cy), r = pr[1], pr[2]
            m |= np.sqrt((x - cx) ** 2 + (y - cy) ** 2) < r + stroke * 0.3
        else:
            (cx, cy), r, a0 = pr[1], pr[2], pr[3]
            d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            a = (np.arctan2(y - cy, x - cx) - a0) % math.tau
            m |= (np.abs(d - r) < stroke * 0.8) & (a < math.pi * 1.1)
    return m


def g_glyphs(rs, n, p):
    """Glyph tablet (normalized UVs or tiled): rows x cols of ORIGINAL glyphs (glyph() grammar) incised into a smooth
    face: dark strokes with a lit lower-right lip (incised = light from the top-left), incised row rules and a
    border. params: rows, cols, border, depth, weather, seed_offset."""
    u, v = _uv(n)
    rows, cols = int(p.get("rows", 4)), int(p.get("cols", 3))
    b = float(p.get("border", 0.06))
    inner = _rect(u, v, b, b, 1 - b, 1 - b)
    gu = ((u - b) / (1 - 2 * b)) * cols
    gv = ((v - b) / (1 - 2 * b)) * rows
    ci = np.clip(np.floor(gu).astype(int), 0, cols - 1)
    ri = np.clip(np.floor(gv).astype(int), 0, rows - 1)
    fu, fv = gu - np.floor(gu), gv - np.floor(gv)
    grs = np.random.default_rng(int(p.get("seed_offset", 0)) + 7919)
    cut = np.zeros_like(u, dtype=bool)
    for r_ in range(rows):
        for c_ in range(cols):
            prims = glyph(grs)
            sel = (ri == r_) & (ci == c_) & inner
            if sel.any():
                cut |= sel & glyph_mask(prims, fu, fv)
    rule = inner & (np.abs(fv - 0.02) < 0.035) & (ri > 0)
    cut |= rule
    cutf = cut.astype(np.float64)
    f = 0.62 + float(p.get("weather", 0.3)) * 0.22 * (T._norm(T.fbm(rs, n, 3, 3)) - 0.5)
    f = np.where(~inner, 0.5 + 0.1 * (v - 0.5), f)
    f = f - 0.4 * cutf
    f = f - float(p.get("depth", 0.18)) * _emboss(cutf, max(1, n // 64))
    return np.clip(f, 0.0, 1.0)


def g_inlay(rs, n, p):
    """Floor / keystone inlay (normalized): concentric bands and twelve rays around a sun disc on a dressed ground;
    a three-family ramp (stone low, turquoise mid, gold high) is mapped by value."""
    u, v = _uv(n)
    d = np.sqrt((u - 0.5) ** 2 + (v - 0.5) ** 2)
    a = np.arctan2(v - 0.5, u - 0.5)
    f = 0.18 + 0.12 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    f = np.where((d > 0.36) & (d < 0.44), 0.5, f)
    f = np.where((d > 0.2) & (d < 0.33) & (np.abs(np.sin(a * 6)) < 0.45), 0.52, f)
    f = np.where(d < 0.16, 0.88, f)
    f = np.where((d >= 0.16) & (d < 0.19), 0.7, f)
    return np.clip(f, 0.0, 1.0)


# ---------------------------------------------------------------- terrain


def g_dune(rs, n, p):
    """Desert sand: long soft wind ripples bent by a warp field over big painted blotches (low per-texel energy)."""
    u, v = _uv(n)
    warp = T.fbm(rs, n, 2, 2)
    rip = 0.5 + 0.5 * np.sin((v * int(p.get("ripples", 6)) + float(p.get("bend", 0.6)) * warp) * math.tau)
    rip = _sstep(0.15, 0.85, rip)
    big = T._norm(T.fbm(rs, n, 2, 3))
    f = 0.5 + float(p.get("ripple", 0.25)) * (rip - 0.5) + float(p.get("blotch", 0.45)) * (big - 0.5)
    return np.clip(f, 0.0, 1.0)


def g_patchy(rs, n, p):
    """Overgrown ground on a split ramp: soft organic patches of moss / grass (upper ramp segment) on earth (lower
    segment). The mask is a sum of wrapped round blobs of varied size, edge-warped by noise (value-noise iso-lines at
    low frequency come out square and paint a checkerboard); each family keeps its own painted value blotches."""
    u, v = _uv(n)
    acc = np.zeros((n, n))
    for _ in range(int(p.get("blobs", 9))):
        cx, cy, rad = rs.random(), rs.random(), 0.08 + 0.14 * rs.random()
        d2 = (_wrapd(u - cx) / rad) ** 2 + (_wrapd(v - cy) / (rad * (0.7 + 0.6 * rs.random()))) ** 2
        acc = acc + np.exp(-d2)
    warp = T._norm(T.fbm(rs, n, 4, 3))
    mask = ((acc + 0.45 * (warp - 0.5)) > float(p.get("cover", 0.5))).astype(np.float64)
    earth = 0.2 + 0.7 * T._norm(T.fbm(rs, n, 3, 3))
    moss = 0.15 + 0.75 * T._norm(T.fbm(rs, n, 4, 2))
    return _segment(earth, moss, mask, float(p.get("split", 0.5)))


def g_strata(rs, n, p):
    """Sandstone cliff: warped horizontal strata bands with soft vertical erosion streaks and dark undercut seams."""
    u, v = _uv(n)
    warp = T._norm(T.fbm(rs, n, 2, 2))
    k = float(p.get("bands", 4))
    s = (v * k + 0.35 * warp) % 1.0
    band = 0.35 + 0.4 * _sstep(0.0, 0.7, s) - 0.25 * _sstep(0.8, 1.0, s)
    streak = T._norm(T.fbm(rs, n, 4, 2, sx=float(p.get("streaks", 5)), sy=0.4))
    f = band + 0.22 * (streak - 0.5) + 0.12 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    seam = (s > 0.93)
    f = np.where(seam, 0.08, f)
    return np.clip(f, 0.0, 1.0)


def g_moss(rs, n, p):
    """Mossy masonry on a split ramp: stone blocks (lower ramp segment) with moss creeping down from the top edge
    and out of the joints (upper segment). params: rows, cols, moss (0..1), split (ramp share of the stone steps)."""
    stone = g_ashlar(rs, n, dict(p, weather=p.get("weather", 0.6)))
    u, v = _uv(n)
    rows = int(p.get("rows", 4))
    fv = (v * rows) % 1.0
    nz = T._norm(T.fbm(rs, n, 4, 3))
    amt = float(p.get("moss", 0.45))
    cover = nz * 0.7 + 0.5 * _sstep(0.4, 1.0, fv) * 0.6 + 0.35 * (stone < 0.12)
    mask = (cover > (1.0 - amt)).astype(np.float64)
    mval = 0.25 + 0.6 * T._norm(T.fbm(rs, n, 6, 2)) + 0.2 * _sstep(0.5, 1.0, fv)
    return _segment(stone, mval, mask, float(p.get("split", 0.55)))


def g_water(rs, n, p):
    """Oasis water: soft broad swells and a few long pale glints (scrolls slowly in the runtime)."""
    u, v = _uv(n)
    warp = T.fbm(rs, n, 2, 2)
    sw = 0.5 + 0.5 * np.sin((v * int(p.get("swells", 3)) + 0.5 * warp + 0.12 * np.sin(u * math.tau)) * math.tau)
    f = float(p.get("depth", 0.32)) + 0.38 * _sstep(0.2, 0.9, sw) + 0.12 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    glint = (sw > 0.97) & (T._norm(T.fbm(rs, n, 4, 2, sx=4, sy=1)) > 0.55)
    return np.clip(np.where(glint, 0.95, f), 0.0, 1.0)


def g_sky(rs, n, p):
    """Painted sky dome card (v = elevation 0 horizon .. 1 zenith): ramp low = deep zenith, high = pale horizon and
    the sun. A soft sun glow at (sun_u, sun_v), long thin cloud streaks and a horizon haze band; palette ramp order
    deep -> pale -> sun, so the brightest step only appears in the sun."""
    u, v = _uv(n)
    hz = float(p.get("haze", 0.18))
    g = 1.0 - np.clip(v, 0, 1) ** float(p.get("gamma", 0.7))       # 1 at the horizon, 0 at the zenith
    f = 0.08 + 0.7 * g
    f = f + float(p.get("haze_amt", 0.12)) * _sstep(hz, 0.0, v)      # pale haze band at the horizon (= fog colour)
    clouds = T._norm(T.fbm(rs, n, 2, 3, sx=float(p.get("stretch", 4)), sy=1))
    band = _sstep(0.2, 0.45, v) * _sstep(0.85, 0.55, v)
    f = f + float(p.get("clouds", 0.35)) * band * _sstep(0.55, 0.85, clouds) * 0.35
    su, sv = float(p.get("sun_u", 0.3)), float(p.get("sun_v", 0.55))
    du = _wrapd(u - su)
    d = np.sqrt((du * 2.0) ** 2 + (v - sv) ** 2)
    glow = float(p.get("glow", 0.6))
    f = f + glow * 0.3 * _sstep(0.32, 0.0, d)
    # everything but the sun disc stays below the top step, and the horizon rows land exactly on the haze step (the
    # exterior fog colour), so the painted horizon and the fogged distance share one colour
    f = np.where(d < float(p.get("sun_r", 0.05)), 1.0, np.minimum(f, 0.78))
    return np.clip(f, 0.0, 1.0)


# ---------------------------------------------------------------- vegetation, wood, clay, gold


def g_frond(rs, n, p):
    """Palm / jungle leaf strip (u across, v along): a pale midrib, diagonal leaflet bands from the rib outward with
    dark gaps, darker edges. Tiles along v."""
    u, v = _uv(n)
    k = float(p.get("leaflets", 6))
    off = np.abs(u - 0.5)
    band = (v * k + off * float(p.get("slant", 1.4))) % 1.0
    leaf = _sstep(0.0, 0.25, band) * _sstep(1.0, 0.7, band)
    f = 0.25 + 0.5 * leaf - 0.25 * _sstep(0.32, 0.5, off) + 0.1 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    rib = off < float(p.get("rib", 0.04))
    return np.clip(np.where(rib, 0.82, f), 0.0, 1.0)


def g_leafy(rs, n, p):
    """Leaf mass that reads on frond strips AND canopy blobs: staggered rows of elongated leaflets slanting away from
    a soft central rib, each leaflet lit at its upper edge, with dark shade between them (painted, tileable)."""
    u, v = _uv(n)
    rows = int(p.get("rows", 4))
    cols = int(p.get("cols", 2))
    r = np.floor(v * rows).astype(int)
    uu = (u + 0.5 * (r % 2) / cols) % 1.0
    fu = (uu * cols) % 1.0
    fv = (v * rows) % 1.0
    side = np.where(fu < 0.5, -1.0, 1.0)
    du = (fu - 0.5) * side                                   # 0 at the rib, 0.5 at the edge
    slant = float(p.get("slant", 0.9))
    lv = fv - slant * du                                     # leaflets sweep upward away from the rib
    lv = lv - np.floor(lv)
    leaf = _sstep(0.0, 0.18, lv) * _sstep(0.95, 0.55, lv) * _sstep(0.5, 0.36, du)
    lit = _sstep(0.4, 0.9, lv)
    f = 0.1 + 0.55 * leaf + 0.25 * leaf * lit
    f = f + 0.14 * (T._norm(T.fbm(rs, n, 2, 2)) - 0.5)
    rib = (du < float(p.get("rib", 0.03))) & (leaf > 0.05)
    f = np.where(rib, np.maximum(f, 0.62), f)
    return np.clip(f, 0.0, 1.0)


def g_trunk(rs, n, p):
    """Palm trunk: rows of overlapping leaf-base scales (chevrons) with a lit upper lip and a dark under-edge."""
    u, v = _uv(n)
    rows = int(p.get("rows", 4))
    cols = int(p.get("cols", 3))
    r = np.floor(v * rows).astype(int)
    uu = (u + 0.5 * (r % 2) / cols) % 1.0
    fu = (uu * cols) % 1.0
    fv = (v * rows) % 1.0
    chevron = fv - 0.35 * np.abs(fu - 0.5)
    f = 0.3 + 0.45 * _sstep(-0.1, 0.6, chevron) + 0.1 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    f = np.where(np.abs(chevron - 0.02) < 0.06, 0.1, f)
    return np.clip(f, 0.0, 1.0)


def g_bark(rs, n, p):
    """Jungle bark on a split ramp: vertical fissured ridges (lower segment) with moss patches (upper segment)."""
    u, v = _uv(n)
    ridges = T._norm(T.fbm(rs, n, 4, 3, sx=float(p.get("ridges", 3)), sy=0.25))
    fis = ridges < 0.18
    bark = np.where(fis, 0.05, 0.3 + 0.6 * ridges)
    nz = T._norm(T.fbm(rs, n, 3, 3))
    mask = (nz > (1.0 - float(p.get("moss", 0.3)))).astype(np.float64)
    return _segment(bark, 0.3 + 0.6 * T._norm(T.fbm(rs, n, 6, 2)), mask, float(p.get("split", 0.6)))


def g_vine(rs, n, p):
    """Hanging vine strand (u across, v along): a thin stem with alternating leaf blobs; gaps read as dark shade."""
    u, v = _uv(n)
    k = float(p.get("leaves", 4))
    side = np.where((np.floor(v * k) % 2) == 0, 0.32, 0.68)
    fv = (v * k) % 1.0
    leaf = ((u - side) / 0.22) ** 2 + ((fv - 0.5) / 0.42) ** 2 < 1.0
    stem = np.abs(u - 0.5) < 0.05
    f = np.where(leaf, 0.45 + 0.4 * (1.0 - fv), np.where(stem, 0.35, 0.08))
    f = f + 0.08 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    return np.clip(f, 0.0, 1.0)


def g_clay(rs, n, p):
    """Terracotta on a split ramp: warm clay body (lower segment) with painted bands and a zigzag frieze (upper
    segment = pigment steps). params: bands (v centres), zigzag (bool), split."""
    u, v = _uv(n)
    body = 0.35 + 0.35 * v + 0.2 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    paint = np.zeros_like(u)
    val = np.zeros_like(u)
    for c in p.get("bands", [0.22, 0.78]):
        paint = np.maximum(paint, (np.abs(v - float(c)) < 0.035))
        val = np.where(np.abs(v - float(c)) < 0.035, 0.3, val)
    if p.get("zigzag", True):
        zz = 0.5 + 0.07 * (2.0 * np.abs(((u * 6) % 1.0) - 0.5) - 0.5) * 2
        z = np.abs(v - zz) < 0.03
        paint = np.maximum(paint, z)
        val = np.where(z, 0.85, val)
    return _segment(body, val, paint.astype(np.float64), float(p.get("split", 0.6)))


def g_gold(rs, n, p):
    """Gold leaf: smooth burnished gradient with a few soft hammered spots and a lit band (never a flat colour)."""
    u, v = _uv(n)
    f = 0.45 + 0.3 * np.sin(v * math.pi) + 0.15 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    f = f + 0.12 * _sstep(0.06, 0.0, np.abs(v - 0.62))
    return np.clip(f, 0.0, 1.0)


def g_cloth(rs, n, p):
    """Woven banner (normalized): a field with a border band and an original emblem (a rayed sun) on a split ramp."""
    u, v = _uv(n)
    weave = ((np.floor(u * n / 2) + np.floor(v * n / 2)) % 2) * 0.04
    field = 0.3 + 0.3 * v + weave + 0.08 * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    emb = _disc(u, v, 0.5, 0.58, 0.12) | _rays(u, v, 0.5, 0.58, 0.16, 0.26, 8, 0.25)
    bord = ~_rect(u, v, 0.08, 0.08, 0.92, 0.92)
    mask = (emb | bord).astype(np.float64)
    return _segment(field, 0.4 + 0.5 * v, mask, float(p.get("split", 0.55)))


GENS = {
    "anc_ashlar": g_ashlar, "anc_dressed": g_dressed, "anc_rubble": g_rubble, "anc_paving": g_paving,
    "anc_coffer": g_coffer, "anc_relief": g_relief, "anc_glyphs": g_glyphs, "anc_inlay": g_inlay,
    "anc_dune": g_dune, "anc_patchy": g_patchy, "anc_strata": g_strata, "anc_moss": g_moss, "anc_water": g_water, "anc_sky": g_sky,
    "anc_frond": g_frond, "anc_leafy": g_leafy, "anc_trunk": g_trunk, "anc_bark": g_bark, "anc_vine": g_vine, "anc_clay": g_clay,
    "anc_gold": g_gold, "anc_cloth": g_cloth,
}


def register():
    """Idempotent: add the anc_* field generators to texgen.FIELD_GENS (never replaces another generator)."""
    for name, fn in GENS.items():
        cur = T.FIELD_GENS.get(name)
        if cur is not None and cur is not fn:
            raise RuntimeError("texture generator name collision: %s" % name)
        T.FIELD_GENS[name] = fn


register()
