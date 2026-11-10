"""Theme-agnostic texture generators. Every output texel is a palette colour.

A recipe (from a pack) = {"gen": name, "size": N, "ramp": [palette names dark->bright], ...}.
Field generators return a tileable float field in [0,1] (row 0 = TOP of the image); it is softened and mapped
onto the ramp as the shared N64 look convention says (kits/core/n64_look.json "textures": no ordered dither, `soften`
wrapped blur passes first, so the few ramp colours form soft painted shapes that bilinear filtering blends; legacy
recipes without the convention keep 4x4 Bayer dithering). A recipe may override `dither`/`soften` explicitly.
Painter generators (env, scene, faces) place palette colours directly. Deterministic: numpy PCG64 seeded from
sha256 tags.
"""
import json
import math
from pathlib import Path

import numpy as np

from .palette import mottle_thresholds, quantize_field
from .rng import sub_seed

GEN_PARAMS = {}  # gen -> documented params (for the contract/notes)
_CONVENTION = None


def convention_textures():
    """The convention's texture rules ({} when kits/core/n64_look.json is absent: legacy dithered output)."""
    global _CONVENTION
    if _CONVENTION is None:
        p = Path(__file__).with_name("n64_look.json")
        _CONVENTION = json.loads(p.read_text()).get("textures", {}) if p.is_file() else {}
    return _CONVENTION


def recipe_dither(recipe):
    """Dither amount for a recipe: explicit recipe value, else the convention's (True = legacy full Bayer)."""
    v = recipe.get("dither", convention_textures().get("dither", True))
    return v if isinstance(v, bool) else float(v)


def soften(f, passes):
    """Wrapped [1 2 1]^2 / 16 blur passes on a tileable field (keeps tiling seamless)."""
    f = np.asarray(f, dtype=np.float64)
    for _ in range(int(passes)):
        h = (np.roll(f, 1, 1) + 2.0 * f + np.roll(f, -1, 1)) / 4.0
        f = (np.roll(h, 1, 0) + 2.0 * h + np.roll(h, -1, 0)) / 4.0
    return f


def _rs(*tags):
    return np.random.default_rng(sub_seed("tex", *tags))


def _grid(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    u = (xx + 0.5) / n
    v = 1.0 - (yy + 0.5) / n
    return u, v


def _smooth(t):
    return t * t * (3 - 2 * t)


def vnoise(rs, lat, n, sx=1, sy=1):
    """Tileable value noise; lattice lat*sx by lat*sy; output n x n (rows top->bottom)."""
    lx, ly = max(1, int(lat * sx)), max(1, int(lat * sy))
    L = rs.random((ly, lx))
    cx = np.arange(n) * lx / n
    cy = np.arange(n) * ly / n
    x0 = np.floor(cx).astype(int)
    y0 = np.floor(cy).astype(int)
    fx = _smooth(cx - x0)
    fy = _smooth(cy - y0)
    x1 = (x0 + 1) % lx
    y1 = (y0 + 1) % ly
    x0 %= lx
    y0 %= ly
    a = L[y0][:, x0]
    b = L[y0][:, x1]
    c = L[y1][:, x0]
    d = L[y1][:, x1]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(rs, n, lat=4, oct=3, sx=1, sy=1, gain=0.5):
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(oct):
        out += amp * vnoise(rs, lat * (2 ** o), n, sx, sy)
        tot += amp
        amp *= gain
    return out / tot


def _norm(f):
    lo, hi = float(f.min()), float(f.max())
    if hi - lo < 1e-9:
        return np.full_like(f, 0.5)
    return (f - lo) / (hi - lo)


def _contrast(f, c=1.0, mid=0.5):
    return np.clip((f - 0.5) * c + mid, 0, 1)


def _cells(rs, n, count):
    """Tileable Worley: returns (F1 distance, F2 distance, cell id) on an n x n grid."""
    pts = rs.random((count, 2))
    u, v = _grid(n)
    best1 = np.full((n, n), 9.0)
    best2 = np.full((n, n), 9.0)
    ids = np.zeros((n, n), dtype=int)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(u - px)
        dx = np.minimum(dx, 1 - dx)
        dy = np.abs(v - py)
        dy = np.minimum(dy, 1 - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < best1
        best2 = np.where(closer, best1, np.minimum(best2, d))
        ids = np.where(closer, i, ids)
        best1 = np.where(closer, d, best1)
    return best1, best2, ids


# ---------------------------------------------------------------- field generators
def g_flat(rs, n, p):
    return np.full((n, n), float(p.get("level", 0.5)))


def g_noise(rs, n, p):
    f = _norm(fbm(rs, n, int(p.get("lat", 4)), int(p.get("oct", 3))))
    return _contrast(f, p.get("contrast", 1.0), p.get("mid", 0.5))


def g_plaster(rs, n, p):
    f = 0.7 * _norm(fbm(rs, n, 3, 3)) + 0.3 * _norm(fbm(rs, n, 8, 2))
    return _contrast(_norm(f), p.get("contrast", 0.6), p.get("mid", 0.55))


def g_gloss(rs, n, p):
    """Molded glossy plastic: almost flat bright tone, faint low-frequency swirl, rare glints.
    3.2 (optional, defaults keep old textures byte-identical): `mottle` fine painted variation, `panels` molded
    panel seams per tile (dark groove + light bevel)."""
    f = _norm(fbm(rs, n, 2, 2))
    out = 0.55 + 0.25 * (f - 0.5) * p.get("contrast", 1.0)
    if p.get("mottle"):
        out = out + float(p["mottle"]) * (_norm(fbm(rs, n, 8, 2)) - 0.5)
    if p.get("panels"):
        k = int(p["panels"])
        u, v = _grid(n)
        fu, fv = (u * k) % 1.0, (v * k) % 1.0
        px = 1.0 / n * k
        groove = (fu < px) | (fv < px)
        bevel = ((fu >= px) & (fu < 2 * px)) | ((fv >= px) & (fv < 2 * px))
        out = np.where(groove, out - float(p.get("seam", 0.3)), np.where(bevel, out + 0.12, out))
    if p.get("grain"):
        # 3.3 (optional): per-texel grain like hand-painted/downsampled N64 textures, from its own stream so the
        # glint positions of existing recipes stay put
        out = out + float(p["grain"]) * (_rs("gloss-grain", n).random((n, n)) - 0.5)
    glints = rs.random((n, n)) > (1.0 - p.get("glints", 0.01))
    out = np.where(glints, 1.0, out)
    return np.clip(out, 0, 1)


def g_planks(rs, n, p):
    boards = int(p.get("boards", 4))
    u, v = _grid(n)
    row = np.floor(v * boards).astype(int)
    tone = rs.random(boards + 1)
    offs = rs.random(boards + 1)
    lu = (u + offs[row]) % 1.0
    grain = fbm(rs, n, 2, 3, sx=1, sy=8)
    f = 0.35 + 0.35 * tone[row] + 0.3 * (_norm(grain) - 0.5)
    seam_v = (v * boards) % 1.0
    seam = (seam_v < 1.5 / n * boards) | (seam_v > 1 - 0.5 / n * boards)
    butt = (lu < 1.0 / n)
    f = np.where(seam | butt, 0.02, f)
    return np.clip(f, 0, 1)


def g_grain(rs, n, p):
    g = fbm(rs, n, 2, 3, sx=1, sy=6)
    rings = 0.5 + 0.5 * np.sin(_norm(g) * math.pi * float(p.get("rings", 6)))
    return _contrast(0.6 * _norm(g) + 0.4 * rings, p.get("contrast", 0.8))


def g_blocks(rs, n, p):
    rows = int(p.get("rows", 4))
    cols = int(p.get("cols", 2))
    u, v = _grid(n)
    r = np.floor(v * rows).astype(int)
    shift = np.where(r % 2 == 1, 0.5 / cols, 0.0)
    uu = (u + shift) % 1.0
    c = np.floor(uu * cols).astype(int)
    tone = rs.random((rows + 1, cols + 1))
    f = 0.45 + 0.35 * tone[r % rows, c % cols] + 0.2 * (_norm(fbm(rs, n, 6, 2)) - 0.5)
    mv = (v * rows) % 1.0
    mu = (uu * cols) % 1.0
    mort = float(p.get("mortar", 1.0))
    edge = (mv < mort * rows / n) | (mu < mort * cols / n)
    f = np.where(edge, 0.05, f)
    return np.clip(f, 0, 1)


def g_cobbles(rs, n, p):
    f1, f2, ids = _cells(rs, n, int(p.get("cells", 10)))
    tone = rs.random(ids.max() + 1)
    edge = (f2 - f1) < float(p.get("gap", 0.035))
    f = 0.35 + 0.45 * tone[ids] + 0.25 * (1 - _norm(f1))
    return np.clip(np.where(edge, 0.03, f), 0, 1)


def g_shingles(rs, n, p):
    rows = int(p.get("rows", 4))
    cols = int(p.get("cols", 4))
    u, v = _grid(n)
    r = np.floor(v * rows).astype(int)
    uu = (u + np.where(r % 2 == 1, 0.5 / cols, 0)) % 1.0
    fu = (uu * cols) % 1.0
    fv = (v * rows) % 1.0
    # rounded bottom edge of each tile (scallop)
    curve = 0.25 * (1 - np.sqrt(np.clip(1 - (2 * fu - 1) ** 2, 0, 1)))
    shade = np.clip((fv - curve) * 1.4, 0, 1)
    tone = rs.random((rows + 1, cols + 1))
    c = np.floor(uu * cols).astype(int)
    f = 0.2 + 0.55 * shade + 0.2 * tone[r % rows, c % cols]
    f = np.where(fv < curve + 0.06, 0.03, f)
    return np.clip(f, 0, 1)


def g_thatch(rs, n, p):
    streak = fbm(rs, n, 3, 3, sx=6, sy=0.5)
    bands = 0.5 + 0.5 * np.cos(_grid(n)[1] * math.pi * 2 * int(p.get("rows", 3)))
    return _contrast(0.75 * _norm(streak) + 0.25 * bands, 1.2)


def g_quilt_diamond(rs, n, p):
    k = int(p.get("cells", 3))
    u, v = _grid(n)
    a = (u + v) * k
    b = (u - v) * k
    fa, fb = a % 1.0, b % 1.0
    lobe = np.sin(fa * math.pi) * np.sin(fb * math.pi)
    f = 0.25 + 0.75 * lobe ** 0.6
    stitch = (np.minimum(fa, 1 - fa) < 0.6 * k / n) | (np.minimum(fb, 1 - fb) < 0.6 * k / n)
    f = np.where(stitch, 0.05, f)
    return np.clip(f + 0.08 * (_norm(fbm(rs, n, 8, 1)) - 0.5), 0, 1)


def g_quilt_wave(rs, n, p):
    k = int(p.get("channels", 3))
    amp = float(p.get("amp", 0.12))
    u, v = _grid(n)
    w = v * k + amp * np.sin(2 * math.pi * u * int(p.get("waves", 1)))
    fw = w % 1.0
    lobe = np.sin(fw * math.pi)
    f = 0.2 + 0.8 * lobe ** 0.7
    f = np.where(np.minimum(fw, 1 - fw) < 0.7 * k / n, 0.04, f)
    return np.clip(f, 0, 1)


def g_knit(rs, n, p):
    cols = int(p.get("cols", 8))
    rows = int(p.get("rows", 8))
    u, v = _grid(n)
    cu = (u * cols) % 1.0
    cv = (v * rows) % 1.0
    vshape = np.abs(cu - 0.5) * 1.2 + cv
    st = (vshape % 1.0)
    f = 0.25 + 0.7 * np.sin(st * math.pi) ** 1.5
    gap = np.minimum(cu, 1 - cu) < 0.08
    f = np.where(gap, 0.08, f)
    return np.clip(f + 0.1 * (_norm(fbm(rs, n, 4, 2)) - 0.5), 0, 1)


def g_fur(rs, n, p):
    s = fbm(rs, n, 4, 3, sx=1, sy=float(p.get("stretch", 4)))
    clumps = fbm(rs, n, 3, 2)
    return _contrast(0.6 * _norm(s) + 0.4 * _norm(clumps), p.get("contrast", 1.3), p.get("mid", 0.6))


def g_snow(rs, n, p):
    f = 0.7 + 0.2 * (_norm(fbm(rs, n, 3, 3)) - 0.5)
    sparkle = rs.random((n, n)) > (1 - float(p.get("sparkle", 0.03)))
    f = np.where(sparkle, 1.0, f)
    dimple = rs.random((n, n)) > (1 - float(p.get("dimple", 0.02)))
    return np.clip(np.where(dimple, 0.45, f), 0, 1)


def g_grass(rs, n, p):
    blades = fbm(rs, n, 6, 2, sx=1, sy=float(p.get("stretch", 3)))
    patch = fbm(rs, n, 2, 2)
    f = 0.55 * _norm(blades) + 0.45 * _norm(patch)
    return _contrast(f, p.get("contrast", 1.4))


def g_sand(rs, n, p):
    u, v = _grid(n)
    warp = fbm(rs, n, 2, 2)
    rip = 0.5 + 0.5 * np.sin((v * int(p.get("ripples", 5)) + 0.3 * warp) * 2 * math.pi)
    fine = rs.random((n, n))
    return np.clip(0.45 * rip + 0.35 * _norm(warp) + 0.2 * fine, 0, 1)


def g_rock(rs, n, p):
    f1, f2, ids = _cells(rs, n, int(p.get("cells", 7)))
    crack = (f2 - f1) < 0.02
    base = 0.6 * _norm(fbm(rs, n, 4, 3)) + 0.4 * rs.random(ids.max() + 1)[ids]
    return np.clip(np.where(crack, 0.04, _contrast(base, 1.1)), 0, 1)


def g_dirt(rs, n, p):
    f = 0.6 * _norm(fbm(rs, n, 5, 3))
    pebble = rs.random((n, n)) > 0.96
    return np.clip(np.where(pebble, 0.95, f + 0.2), 0, 1)


def g_water(rs, n, p):
    u, v = _grid(n)
    warp = fbm(rs, n, 2, 2)
    rip = 0.5 + 0.5 * np.sin((v * int(p.get("ripples", 4)) + 0.6 * warp + 0.2 * np.sin(u * 6.28)) * 6.28)
    return np.clip(_contrast(rip, 0.9) * 0.85 + 0.15 * _norm(fbm(rs, n, 6, 1)), 0, 1)


def g_leaves(rs, n, p):
    f1, f2, ids = _cells(rs, n, int(p.get("cells", 14)))
    tone = rs.random(ids.max() + 1)
    lobe = 1 - _norm(f1)
    f = 0.25 + 0.5 * lobe + 0.25 * tone[ids]
    f = np.where((f2 - f1) < 0.02, 0.04, f)
    return np.clip(f, 0, 1)


def g_bark(rs, n, p):
    ridges = fbm(rs, n, 4, 3, sx=float(p.get("ridges", 3)), sy=0.25)
    return _contrast(_norm(ridges), 1.6)


def g_panel(rs, n, p):
    u, v = _grid(n)
    k = int(p.get("panels", 2))
    fu, fv = (u * k) % 1.0, (v * k) % 1.0
    f = 0.55 + 0.15 * (_norm(fbm(rs, n, 3, 2)) - 0.5) + 0.15 * (fv - 0.5)
    seam = (fu < 1.0 * k / n) | (fv < 1.0 * k / n)
    rivet = ((np.abs(fu - 0.12) < 0.04) | (np.abs(fu - 0.88) < 0.04)) & ((np.abs(fv - 0.12) < 0.04) | (np.abs(fv - 0.88) < 0.04))
    f = np.where(seam, 0.08, f)
    return np.clip(np.where(rivet, 0.95, f), 0, 1)


def g_screen(rs, n, p):
    """Readable-looking display: dark field, bright glyph rows, a graph line and a frame."""
    u, v = _grid(n)
    yy, xx = np.mgrid[0:n, 0:n]
    f = np.full((n, n), 0.15)
    f += 0.08 * ((yy % 2) == 0)  # scanlines
    rows = int(p.get("rows", 6))
    gl = rs.random((rows, 12))
    for r in range(rows):
        y0 = int((0.55 + 0.4 * r / rows) * n)
        if y0 + 1 >= n:
            continue
        for g in range(12):
            if gl[r, g] < 0.35:
                continue
            x0 = int((0.08 + g * 0.07) * n)
            w = max(1, int(0.05 * n * gl[r, g]))
            f[y0:y0 + max(1, n // 32), x0:x0 + w] = 0.9
    # graph in the upper half
    pts = np.cumsum(rs.normal(0, 0.06, n)) * 0.5
    pts = 0.25 + 0.2 * _norm(pts)
    for x in range(int(0.08 * n), int(0.92 * n)):
        y = int((pts[x]) * n)
        f[max(0, y - 0):y + 1, x] = 1.0
    f[:, :1] = 0.5
    f[:, -1:] = 0.5
    f[:1, :] = 0.5
    f[-1:, :] = 0.5
    return np.clip(f, 0, 1)


def g_glow(rs, n, p):
    """Soft emissive falloff. 3.3 (optional): `cells` diffuser grid (each cell brightest at its centre, dark
    `frame` mullions at `frame_level`) so luminous panels read as lit fixtures instead of clipped white."""
    u, v = _grid(n)
    d = np.sqrt((u - 0.5) ** 2 + (v - float(p.get("cy", 0.5))) ** 2) * 2
    out = np.clip(1.0 - d * float(p.get("falloff", 0.6)), 0, 1)
    if p.get("cells"):
        k = int(p["cells"])
        fu, fv = (u * k) % 1.0, (v * k) % 1.0
        cd = np.sqrt((fu - 0.5) ** 2 + (fv - 0.5) ** 2) * 2
        out = out * (1.0 - float(p.get("cell_falloff", 0.35)) * cd)
        fw = float(p.get("frame", 0.12))
        out = np.where((fu < fw) | (fv < fw), out * float(p.get("frame_level", 0.35)), out)
    return np.clip(out, 0, 1)


def g_paper(rs, n, p):
    u, v = _grid(n)
    f = 0.85 + 0.1 * (_norm(fbm(rs, n, 4, 2)) - 0.5)
    lines = int(p.get("lines", 6))
    lv = (v * lines) % 1.0
    marks = fbm(rs, n, 8, 1, sx=4, sy=0.5) > 0.5
    ink = (lv < 1.2 * lines / n) & marks & (u > 0.1) & (u < 0.9)
    return np.clip(np.where(ink, 0.15, f), 0, 1)


def g_spines(rs, n, p):
    u, v = _grid(n)
    k = int(p.get("books", 8))
    edges = np.sort(rs.random(k))
    idx = np.searchsorted(edges, u) % k
    tone = rs.random(k + 1)
    f = 0.15 + 0.75 * tone[idx]
    band = (np.abs(v - 0.8) < 0.04) | (np.abs(v - 0.2) < 0.04)
    f = np.where(band, np.clip(f + 0.3, 0, 1), f)
    gap = np.zeros_like(u, dtype=bool)
    for e in edges:
        gap |= np.abs(u - e) < 0.6 / n
    return np.where(gap, 0.02, f)


def g_fabric(rs, n, p):
    yy, xx = np.mgrid[0:n, 0:n]
    weave = ((xx // 2 + yy // 2) % 2).astype(float)
    return np.clip(0.4 + 0.2 * weave + 0.3 * (_norm(fbm(rs, n, 4, 2)) - 0.5), 0, 1)


def g_leather(rs, n, p):
    f1, f2, ids = _cells(rs, n, 24)
    return _contrast(0.6 * _norm(f2 - f1) + 0.4 * _norm(fbm(rs, n, 3, 2)), 1.1, 0.5)


def g_stripes(rs, n, p):
    u, v = _grid(n)
    k = int(p.get("count", 4))
    axis = u if p.get("axis", "h") == "v" else v
    s = ((axis * k) % 1.0) < float(p.get("ratio", 0.5))
    return np.where(s, 0.85, 0.2) + 0.08 * (_norm(fbm(rs, n, 6, 1)) - 0.5)


def g_checks(rs, n, p):
    u, v = _grid(n)
    k = int(p.get("count", 4))
    a = ((u * k) % 1.0) < 0.5
    b = ((v * k) % 1.0) < 0.5
    return np.where(a ^ b, 0.8, 0.25) + 0.06 * (_norm(fbm(rs, n, 6, 1)) - 0.5)


def g_rope(rs, n, p):
    u, v = _grid(n)
    k = int(p.get("twists", 4))
    s = ((u + v) * k) % 1.0
    return np.clip(0.2 + 0.8 * np.sin(s * math.pi) ** 0.8, 0, 1)


def g_fire(rs, n, p):
    u, v = _grid(n)
    nz = fbm(rs, n, 4, 3, sx=1, sy=2)
    f = (1 - v) * 1.2 + 0.5 * (_norm(nz) - 0.5) - 0.6 * np.abs(u - 0.5)
    return np.clip(f, 0, 1)


def g_ice(rs, n, p):
    f1, f2, ids = _cells(rs, n, 6)
    crack = (f2 - f1) < 0.012
    f = 0.65 + 0.25 * (_norm(fbm(rs, n, 3, 2)) - 0.5)
    return np.clip(np.where(crack, 0.98, f), 0, 1)


def g_blotch(rs, n, p):
    """Big painted ground (3.2): low-frequency colour blotches (1-3 m at the pack tile size), very low
    fine-detail contrast, no grain. N64-era terrain reads as soft painted patches, not noise."""
    big = _norm(fbm(rs, n, int(p.get("lattice", 2)), 2))
    mid = _norm(fbm(rs, n, 4, 2))
    fine = rs.random((n, n))
    f = 0.5 + float(p.get("contrast", 0.8)) * (0.62 * (big - 0.5) + 0.28 * (mid - 0.5)) + float(p.get("fine", 0.05)) * (fine - 0.5)
    if p.get("ripple"):  # wind-drift ripples: elongated mid-frequency streaks (snow sastrugi, sand ripples)
        f = f + float(p["ripple"]) * (_norm(fbm(rs, n, 3, 2, sx=2.0, sy=8.0)) - 0.5)
    return np.clip(f, 0, 1)


def g_streaks(rs, n, p):
    """Cliff faces (3.2): vertical streaks with faint strata, dark crevices; tile vertically on rock walls."""
    u, v = _grid(n)
    cols = fbm(rs, n, 6, 2, sx=float(p.get("columns", 5)), sy=0.35)
    strata = 0.5 + 0.5 * np.sin((v * float(p.get("strata", 3)) + 0.15 * _norm(fbm(rs, n, 2, 1))) * 2 * math.pi)
    f = 0.62 * _norm(cols) + 0.18 * strata + 0.2 * _norm(fbm(rs, n, 3, 2))
    crev = _norm(cols) < float(p.get("crevice", 0.12))
    return np.clip(np.where(crev, 0.05, _contrast(f, float(p.get("contrast", 1.15)))), 0, 1)


def g_vgrad(rs, n, p):
    """Vertical gradient with soft painted noise (distant silhouettes, haze bands). v=0 bottom."""
    u, v = _grid(n)
    base = (v if p.get("up", True) else 1.0 - v)
    f = float(p.get("strength", 0.7)) * base + (1 - float(p.get("strength", 0.7))) * 0.5
    return np.clip(f + float(p.get("noise", 0.08)) * (_norm(fbm(rs, n, 3, 2)) - 0.5), 0, 1)


FIELD_GENS = {
    "flat": g_flat, "noise": g_noise, "plaster": g_plaster, "gloss": g_gloss, "planks": g_planks,
    "grain": g_grain, "blocks": g_blocks, "cobbles": g_cobbles, "shingles": g_shingles,
    "thatch": g_thatch, "quilt_diamond": g_quilt_diamond, "quilt_wave": g_quilt_wave,
    "knit": g_knit, "fur": g_fur, "snow": g_snow, "grass": g_grass, "sand": g_sand, "rock": g_rock,
    "dirt": g_dirt, "water": g_water, "leaves": g_leaves, "bark": g_bark, "panel": g_panel,
    "screen": g_screen, "glow": g_glow, "paper": g_paper, "spines": g_spines, "fabric": g_fabric,
    "leather": g_leather, "stripes": g_stripes, "checks": g_checks, "rope": g_rope, "fire": g_fire,
    "ice": g_ice, "blotch": g_blotch, "streaks": g_streaks, "vgrad": g_vgrad,
}


# Pack-local implementations may share an authored generator token without changing its RNG seed.
# MERGE6: sci-fi and dungeon both authored "crystal" independently; the established global remains dungeon.
FIELD_GENS_BY_PACK = {}


def field(gen, n, params, *seed_tags):
    fn = FIELD_GENS_BY_PACK.get((seed_tags[0], gen)) if seed_tags else None
    if fn is None:
        fn = FIELD_GENS.get(gen)
    if fn is None:
        raise ValueError("unknown texture generator %r" % gen)
    return fn(_rs(gen, *seed_tags), n, params)


# ---------------------------------------------------------------- painters
def paint_env(n, pal, p):
    """Sphere/matcap environment map. stops: palette names from DOWN (floor) to UP (ceiling)."""
    u, v = _grid(n)
    x = u * 2 - 1
    y = v * 2 - 1
    r2 = x * x + y * y
    inside = r2 <= 1.0
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    # treat view-space normal y as "up"; add a horizon wobble
    up = y * 0.85 + 0.15 * nz
    t = np.clip(up * 0.5 + 0.5, 0, 1)
    if "below" in p and "above" in p:
        # Split studio map (3.2): dark floor reflection under a crisp horizon, bright ceiling above it.
        hz = float(p.get("horizon", 0.5))
        lo = quantize_field(np.clip(t / max(hz, 1e-6), 0, 1), pal.ramp_rgb(p["below"]), dither=recipe_dither(p))
        hi = quantize_field(np.clip((t - hz) / max(1.0 - hz, 1e-6), 0, 1), pal.ramp_rgb(p["above"]), dither=recipe_dither(p))
        img = np.where((t < hz)[:, :, None], lo, hi)
        if p.get("horizon_color"):
            img[(np.abs(t - hz) < float(p.get("horizon_width", 0.012))) & inside] = pal.rgb(p["horizon_color"])
    else:
        ramp = pal.ramp_rgb(p["stops"])
        img = quantize_field(t, ramp, dither=recipe_dither(p))
    if p.get("rim"):  # grazing-angle brightening (Fresnel) as a ring at the disc edge
        rw = float(p.get("rim_width", 0.06))
        img[(r2 > (1.0 - rw) ** 2) & inside] = pal.rgb(p["rim"])
    for px_, py_, pw_, ph_, pc_ in p.get("panels", []):  # soft light panels: [u, v_from_top, w, h, colour]
        img[(np.abs(u - px_) < pw_ / 2) & (np.abs((1 - v) - py_) < ph_ / 2) & inside] = pal.rgb(pc_)
    edge = pal.rgb(p.get("edge", (p.get("stops") or p.get("below"))[0]))
    img[~inside] = edge
    for gx, gy, gr in p.get("glints", []):
        d = np.sqrt((u - gx) ** 2 + ((1 - v) - gy) ** 2)
        img[(d < gr) & inside] = pal.rgb(p.get("glint", (p.get("stops") or p.get("above"))[-1]))
    for band in p.get("bands", []):  # dark window bands etc: [v_center, half_width, colour]
        m = (np.abs((1 - v) - band[0]) < band[1]) & inside
        img[m] = pal.rgb(band[2])
    return img


def _silhouette(rs, n, kind, base, height, count):
    """Return per-column skyline height (0..1 from bottom) for a horizon silhouette kind."""
    xs = np.arange(n) / n
    h = np.full(n, base)
    if kind == "hills":
        h = base + height * _norm(np.interp(xs, np.linspace(0, 1, 6), rs.random(6))) * 0.8
    elif kind == "mountains":
        pts = rs.random(count + 1)
        pts[-1] = pts[0]
        h = base + height * np.interp(xs, np.linspace(0, 1, count + 1), pts)
    elif kind in ("domes", "huts", "trees", "forest", "roofs"):
        h = np.full(n, base)
        cs = np.sort(rs.random(count))
        for c in cs:
            w = (0.03 + 0.05 * rs.random()) * (2 if kind == "domes" else 1)
            hh = height * (0.5 + 0.5 * rs.random())
            d = np.abs(xs - c)
            d = np.minimum(d, 1 - d)
            if kind == "domes":
                prof = base + hh * np.sqrt(np.clip(1 - (d / w) ** 2, 0, 1))
            elif kind in ("huts", "roofs"):
                prof = base + hh * np.clip(1 - d / w, 0, 1) * (d < w) + (d < w) * hh * 0.3
            else:  # trees / forest: pointy
                prof = base + hh * np.clip(1 - d / (w * 0.6), 0, 1) * 1.4
            h = np.maximum(h, np.where(d < w * 1.2, prof, base))
    return h


def paint_scene(n_w, n_h, pal, p, *tags):
    """Scene card (window view / sky backdrop). Layers drawn bottom-up, palette colours only.
    p: sky (ramp names, bottom->top), stars {count, color}, layers [{kind, base, height, count,
    color, lights{color, count}}], ground {ramp, height}."""
    rs = _rs("scene", *tags)
    yy, xx = np.mgrid[0:n_h, 0:n_w]
    vy = 1.0 - (yy + 0.5) / n_h  # 0 bottom .. 1 top
    sky = pal.ramp_rgb(p["sky"])
    lo, hi = p.get("sky_range", [0.0, 1.0])     # 3.2: map the ramp over the part of the dome a fixed camera sees
    vg = np.clip((vy - float(lo)) / max(float(hi) - float(lo), 1e-6), 0.0, 1.0) ** float(p.get("sky_gamma", 1.0))
    dither = recipe_dither(p)                  # 3.2: False = clean bands (bilinear filtering softens them)
    if bool(p.get("painted", convention_textures().get("painted_sky", False))):
        # N64 look convention: aurora / cloud / haze layers are painted INTO the sky gradient (they pull the
        # gradient toward the sky-ramp step nearest their colour with a soft mask), so their edges are soft steps of
        # the sky ramp instead of hard stair-stepped stamps. Palette-exact: only ramp colours (+ stars) are used.
        img = _painted_sky(rs, vg, vy, xx, n_w, n_h, pal, sky, p, dither)
        _stars(rs, img, vy, n_w, n_h, pal, p)
        return _scene_silhouettes(rs, img, vy, n_w, n_h, pal, p, sky_layers=False)
    img = quantize_field(np.broadcast_to(vg, (n_h, n_w)).copy(), sky, dither=dither)
    st = p.get("stars")
    if st:
        cnt = int(st.get("count", 40))
        sx = rs.integers(0, n_w, cnt)
        sy = rs.integers(0, n_h, cnt)
        keep = vy[sy, 0] > st.get("min_v", 0.45)
        img[sy[keep], sx[keep]] = pal.rgb(st["color"])
    for li, layer in enumerate(p.get("layers", [])):
        if layer["kind"] in ("aurora", "clouds", "haze"):
            # 3.2 sky layers: aurora ribbon, soft cloud banks, horizon haze band (palette colours, dithered)
            v0, hgt = layer.get("base", 0.5), layer.get("height", 0.2)
            if layer["kind"] == "haze":
                t = np.clip(1.0 - (vy - v0) / max(hgt, 1e-6), 0, 1) * (vy >= v0 - 0.02)
                dith = rs.random((n_h, n_w)) if dither else np.full((n_h, n_w), 0.5)
                img[(t > dith) & (vy >= v0 - 0.02)] = pal.rgb(layer["color"])
                continue
            nz = _norm(fbm(rs, max(n_w, n_h), 3 if layer["kind"] == "clouds" else 2, 3, sx=float(layer.get("stretch", 3)), sy=1)[:n_h, :n_w])
            if layer["kind"] == "aurora":
                wave = v0 + hgt * 0.5 * (1 + np.sin(xx / n_w * math.tau * float(layer.get("waves", 2)) + 2 * nz))
                band = np.abs(vy - wave) < (0.035 + 0.05 * nz) * float(layer.get("thickness", 1.0))
                core = np.abs(vy - wave) < 0.018
                img[band & ((rs.random((n_h, n_w)) > 0.35) | (not dither))] = pal.rgb(layer["color"])
                if layer.get("core"):
                    img[core] = pal.rgb(layer["core"])
            else:
                env = np.clip(1.0 - np.abs(vy - v0 - hgt / 2) / max(hgt / 2, 1e-6), 0, 1)
                cl = nz * env
                thr = float(layer.get("cover", 0.45))
                img[cl > thr] = pal.rgb(layer["color"])
                if layer.get("shade"):
                    img[(cl > thr) & (cl < thr + 0.08)] = pal.rgb(layer["shade"])
            continue
        prof = _silhouette(rs, n_w, layer["kind"], layer.get("base", 0.3), layer.get("height", 0.2),
                           int(layer.get("count", 8)))
        mask = vy <= prof[None, :]
        if "ramp" in layer:
            shade = np.clip((vy - layer.get("base", 0.3) + 0.15) / max(1e-6, layer.get("height", 0.2) + 0.15), 0, 1)
            col = quantize_field(shade, pal.ramp_rgb(layer["ramp"]), dither=True)
            img[mask] = col[mask]
        else:
            img[mask] = pal.rgb(layer["color"])
        lights = layer.get("lights")
        if lights:
            cnt = int(lights.get("count", 10))
            lx = rs.integers(0, n_w, cnt)
            for x in lx:
                top = prof[x]
                y = int((1 - (layer.get("base", 0.3) + (top - layer.get("base", 0.3)) * 0.35)) * n_h)
                y = int(np.clip(y, 0, n_h - 2))
                img[y:y + 2, x:x + 2] = pal.rgb(lights["color"])
    g = p.get("ground")
    if g:
        gh = g.get("height", 0.25)
        mask = vy < gh
        shade = np.clip(vy / max(gh, 1e-6), 0, 1)
        nz = 0.25 * (fbm(rs, max(n_w, n_h), 3, 2)[:n_h, :n_w] - 0.5)
        col = quantize_field(np.clip(shade + nz, 0, 1), pal.ramp_rgb(g["ramp"]), dither=True)
        img[mask] = col[mask]
    return img


def _nearest_ramp_index(ramp_rgb8, rgb):
    d = ((np.asarray(ramp_rgb8, dtype=np.float64) - np.asarray(rgb, dtype=np.float64)[None, :]) ** 2).sum(-1)
    return int(np.argmin(d))


def _painted_sky(rs, vg, vy, xx, n_w, n_h, pal, sky, p, dither):
    """Sky gradient field with aurora / cloud / haze layers blended in as soft masks toward sky-ramp steps."""
    n = len(sky)
    f = np.broadcast_to(vg, (n_h, n_w)).copy()
    for layer in p.get("layers", []):
        kind = layer["kind"]
        if kind not in ("aurora", "clouds", "haze"):
            continue
        v0, hgt = layer.get("base", 0.5), layer.get("height", 0.2)
        target = _nearest_ramp_index(sky, pal.rgb(layer["color"])) / max(n - 1, 1)
        if kind == "haze":
            a = _smooth(np.clip(1.0 - (vy - v0) / max(hgt, 1e-6), 0, 1)) * (vy >= v0 - 0.02)
            f = f + (target - f) * a
            continue
        nz = _norm(fbm(rs, max(n_w, n_h), 3 if kind == "clouds" else 2, 3, sx=float(layer.get("stretch", 3)), sy=1)[:n_h, :n_w])
        if kind == "aurora":
            wave = v0 + hgt * 0.5 * (1 + np.sin(xx / n_w * math.tau * float(layer.get("waves", 2)) + 2 * nz))
            width = (0.035 + 0.05 * nz) * float(layer.get("thickness", 1.0))
            a = 0.85 * np.exp(-((vy - wave) / np.maximum(width, 1e-6)) ** 2)
            f = f + (target - f) * a
            if layer.get("core"):
                tc = _nearest_ramp_index(sky, pal.rgb(layer["core"])) / max(n - 1, 1)
                f = f + (tc - f) * (0.7 * np.exp(-((vy - wave) / 0.02) ** 2))
        else:
            env = np.clip(1.0 - np.abs(vy - v0 - hgt / 2) / max(hgt / 2, 1e-6), 0, 1)
            cl = nz * env
            thr = float(layer.get("cover", 0.45))
            a = _smooth(np.clip((cl - thr + 0.1) / 0.2, 0, 1))
            f = f + (target - f) * a
    return quantize_field(np.clip(f, 0, 1), sky, dither=dither)


def _stars(rs, img, vy, n_w, n_h, pal, p):
    st = p.get("stars")
    if st:
        cnt = int(st.get("count", 40))
        sx = rs.integers(0, n_w, cnt)
        sy = rs.integers(0, n_h, cnt)
        keep = vy[sy, 0] > st.get("min_v", 0.45)
        img[sy[keep], sx[keep]] = pal.rgb(st["color"])


def _scene_silhouettes(rs, img, vy, n_w, n_h, pal, p, sky_layers=False):
    """Silhouette layers + ground of a scene card (painted-sky path), dithered as the convention says."""
    dither = recipe_dither(p)
    for layer in p.get("layers", []):
        if layer["kind"] in ("aurora", "clouds", "haze"):
            continue
        prof = _silhouette(rs, n_w, layer["kind"], layer.get("base", 0.3), layer.get("height", 0.2),
                           int(layer.get("count", 8)))
        mask = vy <= prof[None, :]
        if "ramp" in layer:
            shade = np.clip((vy - layer.get("base", 0.3) + 0.15) / max(1e-6, layer.get("height", 0.2) + 0.15), 0, 1)
            col = quantize_field(shade, pal.ramp_rgb(layer["ramp"]), dither=dither)
            img[mask] = col[mask]
        else:
            img[mask] = pal.rgb(layer["color"])
        lights = layer.get("lights")
        if lights:
            cnt = int(lights.get("count", 10))
            lx = rs.integers(0, n_w, cnt)
            for x in lx:
                top = prof[x]
                y = int((1 - (layer.get("base", 0.3) + (top - layer.get("base", 0.3)) * 0.35)) * n_h)
                y = int(np.clip(y, 0, n_h - 2))
                img[y:y + 2, x:x + 2] = pal.rgb(lights["color"])
    g = p.get("ground")
    if g:
        gh = g.get("height", 0.25)
        mask = vy < gh
        shade = np.clip(vy / max(gh, 1e-6), 0, 1)
        nz = 0.25 * (fbm(rs, max(n_w, n_h), 3, 2)[:n_h, :n_w] - 0.5)
        col = quantize_field(np.clip(shade + nz, 0, 1), pal.ramp_rgb(g["ramp"]), dither=dither)
        img[mask] = col[mask]
    return img


def alpha_mask(shape, n, *tags):
    """Binary alpha (0/255) masks for card_alpha textures."""
    u, v = _grid(n)
    x, y = u - 0.5, v - 0.5
    r = np.sqrt(x * x + y * y)
    if shape == "disc":
        m = r < 0.42
    elif shape == "flake":
        ang = np.arctan2(y, x)
        arms = np.abs(np.cos(3 * ang)) > 0.82
        m = ((r < 0.46) & arms) | (r < 0.14)
    elif shape == "blade":
        m = np.zeros((n, n), dtype=bool)
        for cx, w in ((0.3, 0.09), (0.5, 0.12), (0.72, 0.08)):
            m |= (np.abs(u - cx) < w * (1 - v)) & (v < 0.95)
    elif shape == "leaf":
        m = (x / 0.42) ** 2 + (y / 0.25) ** 2 < 1
    elif shape == "spark":
        m = ((np.abs(x) < 0.08) & (np.abs(y) < 0.45)) | ((np.abs(y) < 0.08) & (np.abs(x) < 0.45))
    elif shape == "puff":
        nz = fbm(_rs("puff", *tags), n, 3, 2)
        m = (r + 0.25 * (nz - 0.5)) < 0.36
    elif shape == "web":
        # DUNGEONKIT corner cobweb: radial threads from the (0, 1) corner plus sagging catenary rings
        cx, cy = u, 1.0 - v
        rr = np.sqrt(cx * cx + cy * cy)
        ang = np.arctan2(cy, cx)
        px = 1.6 / n
        spokes = np.zeros((n, n), dtype=bool)
        for k in range(7):
            a = (k + 0.5) * (np.pi / 2) / 7
            spokes |= np.abs(np.sin(ang - a)) * rr < px
        rings = np.abs(np.sin(rr * (1.0 + 0.18 * np.sin(ang * 14.0)) * np.pi * 5.0)) < 0.09
        m = (spokes | rings) & (rr < 0.97) & (rr > 0.03)
    else:
        m = np.ones((n, n), dtype=bool)
    return np.where(m, 255, 0).astype(np.uint8)


def make_texture(recipe, pal, *tags):
    """recipe -> (H, W, 3) uint8 palette-exact image."""
    gen = recipe["gen"]
    if gen == "env":
        return paint_env(int(recipe.get("size", 128)), pal, recipe)
    if gen == "scene":
        return paint_scene(int(recipe.get("width", 128)), int(recipe.get("height", 64)), pal, recipe, *tags)
    n = int(recipe.get("size", 32))
    f = field(gen, n, recipe, *tags)
    tx = convention_textures()
    # organic generators (ground, rock, snow, fur...) are softened into painted blotches; structured ones (planks,
    # grain, blocks, patterns) keep their shapes; readable ones (screens, text) are quantized clean
    passes = int(recipe.get("soften", tx.get("soften_gens", {}).get(gen, tx.get("soften", 0))))
    if passes:
        f = soften(f, passes)
    ramp = pal.ramp_rgb(recipe["ramp"])
    dither = recipe_dither(recipe)
    if gen in tx.get("crisp_gens", []) and "dither" not in recipe:
        dither = False
    thr = None
    pattern = recipe.get("dither_pattern", tx.get("dither_pattern", "bayer"))
    if dither and pattern == "mottle":
        thr = mottle_thresholds(_rs("mottle", *tags), f.shape[0], f.shape[1], int(tx.get("mottle_clump", 1)))
    return quantize_field(f, ramp, dither=dither, thresholds=thr)


# DUNGEONKIT additive field generators (kits/core/texgen_dungeon.py registers into FIELD_GENS on import).
from . import texgen_dungeon  # noqa: E402,F401
