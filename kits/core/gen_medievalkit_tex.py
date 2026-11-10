"""MEDIEVALKIT painted texture fields (theme-agnostic: every generator returns a tileable float field in [0, 1]
that the shared N64 convention quantizes onto a pack ramp of palette colours; row 0 = top of the image).

Registered additively into kits.core.texgen.FIELD_GENS on import (prefix mk_). Painted, not noisy: big soft shapes
(courses, cobbles, boards, straw layers) with smooth in-shape gradients, dark joints two texels wide and very little
per-texel grain, so the convention's mottle dither only breaks band edges.
"""
import math

import numpy as np

from . import texgen as T

_grid, _norm, fbm, vnoise, _cells, _smooth = T._grid, T._norm, T.fbm, T.vnoise, T._cells, T._smooth


def _wrapd(a, b):
    d = np.abs(a - b)
    return np.minimum(d, 1.0 - d)


def _soft(f, passes=1):
    return T.soften(f, passes)


def mk_plaster(rs, n, p):
    """Whitewash over daub: broad soft patches, faint trowel swirls, a few pale scuffs. Very low grain."""
    big = _norm(fbm(rs, n, 2, 2))
    mid = _norm(fbm(rs, n, 5, 2))
    f = 0.62 + float(p.get("contrast", 0.55)) * (0.55 * (big - 0.5) + 0.25 * (mid - 0.5))
    u, v = _grid(n)
    swirl = 0.5 + 0.5 * np.sin((u * 3 + 0.6 * big) * math.tau) * np.sin((v * 2 + 0.4 * mid) * math.tau)
    f += 0.05 * (swirl - 0.5)
    return np.clip(_soft(f, 1), 0, 1)


def mk_thatch(rs, n, p):
    """Straw thatch: strands running down the slope (along v), laid in courses whose lower edges cast a soft dark
    shadow line, light catching the top of each course, clumpy tone variation."""
    rows = int(p.get("rows", 3))
    u, v = _grid(n)
    strands = _norm(fbm(rs, n, 3, 2, sx=7, sy=0.6))
    clump = _norm(fbm(rs, n, 3, 2))
    wav = 0.04 * np.sin(u * math.tau * 3 + clump * 2.0)
    cv = ((1.0 - v) * rows + wav) % 1.0          # 0 at the top of each course, 1 at its lower edge
    course = 0.25 + 0.75 * (1.0 - cv) ** 0.7
    shadow = np.clip((cv - 0.82) / 0.18, 0, 1)
    f = 0.18 + 0.5 * course + 0.28 * (strands - 0.5) + 0.18 * (clump - 0.5) - 0.55 * shadow
    return np.clip(f, 0, 1)


def mk_cobble(rs, n, p):
    """Rounded cobbles: Worley cells shaded as domes lit from the upper left, soft dark joints."""
    count = int(p.get("cells", 30))
    f1, f2, ids = _cells(rs, n, count)
    tone = rs.random(count)
    edge = f2 - f1
    gap = float(p.get("gap", 0.05))
    dome = np.clip(edge / (gap * 3.0), 0, 1)
    u, v = _grid(n)
    # light from the upper-left: shift sample of the edge field
    sh = np.roll(np.roll(edge, 1, 0), 1, 1)
    lit = np.clip((sh - edge) * float(n) * 0.9, -1, 1)
    f = 0.32 + 0.32 * tone[ids] + 0.25 * dome + 0.12 * lit
    f = np.where(edge < gap, 0.04 + 0.6 * edge / gap * 0.15, f)
    return np.clip(_soft(f, 0), 0, 1)


def mk_ashlar(rs, n, p):
    """Dressed stone courses: blocks of varied length per course, chisel-softened faces (lighter top edge, darker
    bottom edge), recessed mortar two texels wide, per-block tone."""
    rows = int(p.get("rows", 4))
    u, v = _grid(n)
    r = np.floor((1.0 - v) * rows).astype(int) % rows
    fv = ((1.0 - v) * rows) % 1.0
    edges = []
    for k in range(rows):
        cuts = np.sort(rs.random(int(p.get("cols", 2)) + int(rs.integers(0, 2))))
        edges.append(cuts)
    tone = rs.random((rows, 8))
    f = np.zeros((n, n))
    mort = float(p.get("mortar", 1.6)) / n * rows
    for k in range(rows):
        m = r == k
        cuts = edges[k]
        idx = np.searchsorted(cuts, u, side="right") % len(cuts)
        d = np.min(np.stack([_wrapd(u, c) for c in cuts]), 0)
        face = 0.45 + 0.3 * tone[k][idx] + 0.18 * (0.5 - fv) * 1.0
        face = np.where(d < 1.6 / n, 0.06, face)
        f = np.where(m, face, f)
    f = np.where((fv < mort) | (fv > 1.0 - mort * 0.5), 0.05, f)
    f += 0.08 * (_norm(fbm(rs, n, 6, 2)) - 0.5)
    return np.clip(f, 0, 1)


def mk_rubble(rs, n, p):
    """Fieldstone / rubble wall: irregular rounded stones of mixed size, deep soft joints, tone per stone."""
    count = int(p.get("cells", 18))
    f1, f2, ids = _cells(rs, n, count)
    tone = rs.random(count)
    edge = f2 - f1
    gap = float(p.get("gap", 0.04))
    body = np.clip(edge / (gap * 4.0), 0, 1) ** 0.6
    f = 0.25 + 0.38 * tone[ids] + 0.3 * body
    f = np.where(edge < gap, 0.05, f)
    return np.clip(f, 0, 1)


def mk_slate(rs, n, p):
    """Slate courses: staggered slates, each row's lower edge shadowed, per-slate tone, a faint sheen at the top."""
    rows = int(p.get("rows", 5))
    cols = int(p.get("cols", 4))
    u, v = _grid(n)
    cv = (1.0 - v) * rows
    r = np.floor(cv).astype(int)
    fv = cv % 1.0
    uu = (u + np.where(r % 2 == 1, 0.5 / cols, 0.0)) % 1.0
    c = np.floor(uu * cols).astype(int)
    fu = (uu * cols) % 1.0
    tone = rs.random((rows + 1, cols + 1))
    f = 0.3 + 0.35 * tone[r % rows, c % cols] + 0.25 * (1.0 - fv)
    f = np.where(fv > 0.86, 0.05, f)
    f = np.where((fu < 1.2 * cols / n) & (fv < 0.86), 0.12, f)
    return np.clip(f, 0, 1)


def mk_tiles(rs, n, p):
    """Clay pantiles: rows of curved tiles (each tile lit across its curve), shadowed overlaps, warm tone drift."""
    rows = int(p.get("rows", 4))
    cols = int(p.get("cols", 5))
    u, v = _grid(n)
    cv = (1.0 - v) * rows
    r = np.floor(cv).astype(int)
    fv = cv % 1.0
    uu = (u + np.where(r % 2 == 1, 0.5 / cols, 0.0)) % 1.0
    fu = (uu * cols) % 1.0
    curve = np.sin(fu * math.pi) ** 0.8
    tone = rs.random((rows + 1, cols + 1))
    c = np.floor(uu * cols).astype(int)
    f = 0.2 + 0.5 * curve + 0.2 * tone[r % rows, c % cols] - 0.35 * np.clip((fv - 0.8) / 0.2, 0, 1)
    return np.clip(f, 0, 1)


def mk_planks(rs, n, p):
    """Boards along u: per-board tone, long grain, dark seams two texels wide, sparse nail heads near the ends."""
    boards = int(p.get("boards", 4))
    u, v = _grid(n)
    cv = (1.0 - v) * boards
    row = np.floor(cv).astype(int) % boards
    fv = cv % 1.0
    tone = rs.random(boards + 1)
    offs = rs.random(boards + 1)
    lu = (u + offs[row]) % 1.0
    grain = _norm(fbm(rs, n, 2, 2, sx=1, sy=6))
    f = 0.38 + 0.32 * tone[row] + 0.22 * (grain - 0.5) + 0.1 * np.sin(fv * math.pi)
    seam = (fv < 1.5 / n * boards) | (lu < 1.2 / n)
    f = np.where(seam, 0.04, f)
    nail = (np.abs(lu - 0.06) < 0.9 / n) & (np.abs(fv - 0.5) < 0.9 / n * boards)
    f = np.where(nail, 0.12, f)
    return np.clip(f, 0, 1)


def mk_grain(rs, n, p):
    """Adzed oak beam: grain along u, a soft lighter band where the adze caught, a couple of dark knots."""
    u, v = _grid(n)
    g = _norm(fbm(rs, n, 2, 3, sx=1, sy=5))
    band = 0.5 + 0.5 * np.sin((v + 0.15 * g) * math.tau * float(p.get("bands", 2)))
    f = 0.45 + 0.3 * (g - 0.5) + 0.15 * (band - 0.5)
    for _ in range(int(p.get("knots", 2))):
        kx, ky = rs.random(), rs.random()
        d = np.sqrt(_wrapd(u, kx) ** 2 * 4 + _wrapd(v, ky) ** 2)
        f = np.where(d < 0.05, 0.1, f)
    return np.clip(f, 0, 1)


def mk_door(rs, n, p):
    """Plank door leaf (normalised UVs): vertical boards, two dark iron straps with round ends, a ring pull."""
    u, v = _grid(n)
    boards = int(p.get("boards", 4))
    b = np.floor(u * boards).astype(int)
    fu = (u * boards) % 1.0
    tone = rs.random(boards + 1)
    grain = _norm(fbm(rs, n, 2, 2, sx=6, sy=1))
    f = 0.42 + 0.25 * tone[b % boards] + 0.2 * (grain - 0.5)
    f = np.where(fu < 1.6 / n * boards, 0.08, f)
    for sv in (0.24, 0.74):
        strap = (np.abs(v - sv) < 0.035) & (u > 0.05)
        f = np.where(strap, 0.14, f)
        knob = np.sqrt(((u - 0.08) * 1.0) ** 2 + (v - sv) ** 2) < 0.05
        f = np.where(knob, 0.16, f)
    ring = np.abs(np.sqrt((u - 0.8) ** 2 + (v - 0.46) ** 2) - 0.045) < 0.012
    f = np.where(ring, 0.2, f)
    return np.clip(f, 0, 1)


def _banner_cell(u, v, design, folds_n, tails):
    x, y = u - 0.5, v - 0.5
    folds = 0.06 * np.sin(u * math.tau * float(folds_n))
    f = 0.5 + folds
    if design == "chevron":
        ch = np.abs(y - (0.15 - np.abs(x) * 1.1)) < 0.09
    elif design == "cross":
        ch = (np.abs(x) < 0.08) | (np.abs(y - 0.08) < 0.07)
    elif design == "pale":
        ch = np.abs(x) < 0.14
    elif design == "bend":
        ch = np.abs(x + y) < 0.11
    else:
        ch = np.sqrt(x * x + (y - 0.05) ** 2) < 0.2
    f = np.where(ch, 0.9 + folds, f)
    f = np.where((u < 0.07) | (u > 0.93) | (v > 0.94), 0.08, f)
    if tails:
        f = np.where(v < 0.06, 0.08, f)
    return f


def mk_banner(rs, n, p):
    """Heraldic cloth (normalised UVs): field, an original charge, a dark border and soft cloth folds. 0 = border, mid =
    field, high = charge. atlas=True paints four designs in a 2x2 atlas (chevron, cross, pale, roundel) so one role
    gives four banners (generators pick a quadrant with their UVs); otherwise one `design` fills the texture."""
    u, v = _grid(n)
    if p.get("atlas"):
        qu, qv = (u * 2.0) % 1.0, (v * 2.0) % 1.0
        idx = (u >= 0.5).astype(int) + 2 * (v < 0.5).astype(int)
        out = np.zeros_like(u)
        for k, d in enumerate(("chevron", "cross", "pale", "roundel")):
            out = np.where(idx == k, _banner_cell(qu, qv, d, p.get("folds", 2), p.get("tails", True)), out)
        return np.clip(out, 0, 1)
    design = p.get("design", "chevron")
    x, y = u - 0.5, v - 0.5
    folds = 0.06 * np.sin(u * math.tau * float(p.get("folds", 3)))
    f = 0.5 + folds
    if design == "chevron":
        ch = np.abs(y - (0.15 - np.abs(x) * 1.1)) < 0.09
    elif design == "cross":
        ch = (np.abs(x) < 0.08) | (np.abs(y - 0.08) < 0.07)
    elif design == "pale":
        ch = np.abs(x) < 0.14
    elif design == "bend":
        ch = np.abs(x + y) < 0.11
    else:
        ch = np.sqrt(x * x + (y - 0.05) ** 2) < 0.2
    f = np.where(ch, 0.9 + folds, f)
    border = (u < 0.06) | (u > 0.94) | (v > 0.95)
    f = np.where(border, 0.08, f)
    if p.get("tails", True):
        f = np.where(v < 0.06, 0.08, f)
    return np.clip(f, 0, 1)


def mk_carpet(rs, n, p):
    """Woven runner: a dark border, a lighter inner stripe and a repeating diamond medallion along v."""
    u, v = _grid(n)
    x = np.abs(u - 0.5)
    f = np.full((n, n), 0.55)
    f = np.where(x > 0.42, 0.12, f)
    f = np.where((x > 0.34) & (x <= 0.42), 0.85, f)
    dv = np.abs(((v * float(p.get("repeat", 1))) % 1.0) - 0.5)
    dia = (x + dv) < 0.22
    f = np.where(dia & (x <= 0.34), 0.85, f)
    core = (x + dv) < 0.1
    f = np.where(core, 0.25, f)
    f += 0.05 * (_norm(fbm(rs, n, 6, 1)) - 0.5)
    return np.clip(f, 0, 1)


def mk_iron(rs, n, p):
    """Black-smithed iron: dark, a soft hammered sheen, a few rivet heads."""
    u, v = _grid(n)
    ham = _norm(fbm(rs, n, 5, 2))
    f = 0.3 + 0.3 * (ham - 0.5) + 0.12 * np.sin((u + v) * math.tau)
    for _ in range(int(p.get("rivets", 4))):
        rx, ry = rs.random(), rs.random()
        d = np.sqrt(_wrapd(u, rx) ** 2 + _wrapd(v, ry) ** 2)
        f = np.where(d < 0.06, 0.75, f)
        f = np.where((d >= 0.06) & (d < 0.08), 0.1, f)
    return np.clip(f, 0, 1)


def mk_field(rs, n, p):
    """Ploughed crop field: furrows along u with rows of round green plants (cabbages / sprouting grain), soil
    between. 0..0.35 soil, high = leaves."""
    rows = int(p.get("rows", 6))
    u, v = _grid(n)
    cv = (1.0 - v) * rows
    fv = cv % 1.0
    furrow = 0.5 + 0.5 * np.cos(fv * math.tau)
    plants = int(p.get("plants", 8))
    fu = (u * plants + 0.5 * (np.floor(cv) % 2)) % 1.0
    blob = np.sqrt((fu - 0.5) ** 2 * 1.0 + (fv - 0.5) ** 2 * 1.6)
    leaf = np.clip(1.0 - blob / 0.42, 0, 1)
    f = 0.08 + 0.22 * furrow + 0.7 * np.where(leaf > 0.05, 0.55 + 0.45 * leaf, 0.0)
    f += 0.06 * (_norm(fbm(rs, n, 4, 2)) - 0.5)
    return np.clip(f, 0, 1)


def mk_wheat(rs, n, p):
    """Standing grain seen from above / the side: dense vertical stalk streaks with soft ear clumps."""
    st = _norm(fbm(rs, n, 3, 2, sx=6, sy=0.8))
    clump = _norm(fbm(rs, n, 3, 2))
    return np.clip(0.3 + 0.45 * st + 0.3 * (clump - 0.5), 0, 1)


def mk_meadow(rs, n, p):
    """Painted meadow: big soft light/dark patches, clover clumps, a few pale flower dots (low grain)."""
    big = _norm(fbm(rs, n, 2, 2))
    mid = _norm(fbm(rs, n, 5, 2))
    f = 0.5 + 0.55 * (big - 0.5) + 0.25 * (mid - 0.5)
    dots = rs.random((n, n)) > (1.0 - float(p.get("flowers", 0.006)))
    f = np.where(dots, 0.98, f)
    return np.clip(f, 0, 1)


def mk_foliage(rs, n, p):
    """Leaf clumps: Worley lobes lit from above (bright upper rim of each clump, shaded lower half)."""
    count = int(p.get("cells", 12))
    f1, f2, ids = _cells(rs, n, count)
    u, v = _grid(n)
    tone = rs.random(count)
    lobe = 1.0 - _norm(f1)
    sh = np.roll(f1, 2, 0)
    lit = np.clip((sh - f1) * n * 0.5, -1, 1)
    f = 0.2 + 0.45 * lobe + 0.2 * tone[ids] + 0.15 * lit
    f = np.where((f2 - f1) < 0.018, 0.06, f)
    return np.clip(f, 0, 1)


def mk_flagstone(rs, n, p):
    """Large irregular floor flags (rectangles split per row), worn centres, soft dark joints."""
    rows = int(p.get("rows", 3))
    u, v = _grid(n)
    cv = (1.0 - v) * rows
    r = np.floor(cv).astype(int) % rows
    fv = cv % 1.0
    f = np.zeros((n, n))
    for k in range(rows):
        cuts = np.sort(rs.random(2 + int(rs.integers(0, 2))))
        idx = np.searchsorted(cuts, u, side="right") % len(cuts)
        tone = rs.random(len(cuts))
        d = np.min(np.stack([_wrapd(u, c) for c in cuts]), 0)
        face = 0.4 + 0.35 * tone[idx] + 0.12 * np.sin(fv * math.pi)
        face = np.where(d < 1.5 / n, 0.06, face)
        f = np.where(r == k, face, f)
    f = np.where((fv < 1.5 / n * rows), 0.06, f)
    f += 0.1 * (_norm(fbm(rs, n, 5, 2)) - 0.5)
    return np.clip(f, 0, 1)


def mk_wattle(rs, n, p):
    """Woven hazel wattle: horizontal withies weaving over/under vertical stakes."""
    u, v = _grid(n)
    rows = int(p.get("rows", 6))
    stakes = int(p.get("stakes", 4))
    cv = (1.0 - v) * rows
    r = np.floor(cv).astype(int)
    fv = cv % 1.0
    over = np.sin((u * stakes + 0.5 * (r % 2)) * math.pi) ** 2
    f = 0.25 + 0.45 * np.sin(fv * math.pi) * (0.55 + 0.45 * over)
    stake = ((u * stakes) % 1.0) < 1.5 / n * stakes
    f = np.where(stake, 0.85 * (1.0 - over * 0.3), f)
    f = np.where(fv < 0.08, 0.05, f)
    return np.clip(f, 0, 1)


def mk_parchment(rs, n, p):
    """Blank parchment / sign board face: warm soft blotches, darker worn edges. No text by design."""
    u, v = _grid(n)
    big = _norm(fbm(rs, n, 2, 2))
    edge = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    f = 0.62 + 0.25 * (big - 0.5) - 0.35 * np.clip(1.0 - edge / 0.12, 0, 1)
    return np.clip(f, 0, 1)


def mk_snowpack(rs, n, p):
    """Soft snow cover: broad drifts with blue-shaded hollows, no sparkle grain."""
    big = _norm(fbm(rs, n, 2, 2))
    rip = _norm(fbm(rs, n, 3, 2, sx=2.0, sy=6.0))
    return np.clip(0.62 + 0.45 * (big - 0.5) + 0.18 * (rip - 0.5), 0, 1)


def mk_bark(rs, n, p):
    """Oak bark: vertical ridged furrows (along v), softened, a couple of lighter plates."""
    ridges = _norm(fbm(rs, n, 3, 3, sx=float(p.get("ridges", 4)), sy=0.3))
    plates = _norm(fbm(rs, n, 2, 2))
    return np.clip(0.15 + 0.7 * ridges ** 1.2 + 0.15 * (plates - 0.5), 0, 1)


def mk_moss(rs, n, p):
    """Moss / hedge top: soft green cushions with lit crowns."""
    count = int(p.get("cells", 10))
    f1, f2, ids = _cells(rs, n, count)
    tone = rs.random(count)
    return np.clip(0.25 + 0.5 * (1.0 - _norm(f1)) + 0.2 * tone[ids], 0, 1)


def mk_weave(rs, n, p):
    """Canvas / homespun: soft basket weave, faint stripes (awnings use the stripes param)."""
    u, v = _grid(n)
    k = int(p.get("stripes", 0))
    f = np.full((n, n), 0.55)
    if k:
        f = np.where(((u * k) % 1.0) < 0.5, 0.82, 0.3)
    yy, xx = np.mgrid[0:n, 0:n]
    f = f + 0.05 * (((xx // 2 + yy // 2) % 2) - 0.5)
    f += 0.06 * (_norm(fbm(rs, n, 4, 2)) - 0.5)
    return np.clip(f, 0, 1)


def mk_pane(rs, n, p):
    """Painted window (normalized UVs, one per pane): dark glass brightening toward the top (sky reflection), a soft
    diagonal glint, a cross mullion (or leaded diamonds) and a dark border. 0 = lead / mullion."""
    u, v = _grid(n)
    f = 0.22 + 0.32 * v
    glint = np.exp(-((u - v * 0.9 + 0.15) / 0.07) ** 2)
    f = f + 0.42 * glint * (v > 0.25)
    if p.get("leaded", False):
        d1 = np.abs(((u + v) * 3.0) % 1.0 - 0.5) < 0.06
        d2 = np.abs(((u - v) * 3.0) % 1.0 - 0.5) < 0.06
        f = np.where(d1 | d2, 0.08, f)
    else:
        f = np.where((np.abs(u - 0.5) < 0.05) | (np.abs(v - 0.55) < 0.05), 0.0, f)
    f = np.where((u < 0.07) | (u > 0.93) | (v < 0.07) | (v > 0.93), 0.0, f)
    return np.clip(f, 0, 1)


GENS = {
    "mk_pane": mk_pane,
    "mk_plaster": mk_plaster, "mk_thatch": mk_thatch, "mk_cobble": mk_cobble, "mk_ashlar": mk_ashlar,
    "mk_rubble": mk_rubble, "mk_slate": mk_slate, "mk_tiles": mk_tiles, "mk_planks": mk_planks, "mk_grain": mk_grain,
    "mk_door": mk_door, "mk_banner": mk_banner, "mk_carpet": mk_carpet, "mk_iron": mk_iron, "mk_field": mk_field,
    "mk_wheat": mk_wheat, "mk_meadow": mk_meadow, "mk_foliage": mk_foliage, "mk_flagstone": mk_flagstone,
    "mk_wattle": mk_wattle, "mk_parchment": mk_parchment, "mk_snowpack": mk_snowpack, "mk_bark": mk_bark,
    "mk_moss": mk_moss, "mk_weave": mk_weave,
}


def register():
    for k, fn in GENS.items():
        if T.FIELD_GENS.get(k) not in (None, fn):
            raise RuntimeError("texture generator id clash: %s" % k)
        T.FIELD_GENS[k] = fn


register()
