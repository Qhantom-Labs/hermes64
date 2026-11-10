"""SCIFIKIT painted texture field generators (theme-agnostic; every texel ends on a pack palette ramp step).

Registered additively into kits/core/texgen.FIELD_GENS (new names only, existing generators untouched). Each returns a
tileable float field in [0, 1] (row 0 = top of the image); kits/core/texgen.make_texture softens/quantizes it onto the
recipe ramp exactly as the N64 look convention says (mottle threshold, crisp generators clean). Large painted shapes,
soft gradients and few strong edges keep the per-texel energy inside the n64_fidelity library bounds.

  plating      hull / wall panels: per-panel painted gradient, groove + light bevel seams, optional inset sub-panel
  hexplate     hexagonal deck plates (Voronoi of a near-regular hex lattice that tiles the square), bevelled plates
  grille       vent / grate slats with dark gaps
  hazard       diagonal two-tone warning stripes (band trims)
  lightstrip   luminous diffuser strip / panel (bright core, soft falloff, darker segment joints)
  brushed      brushed metal: faint streaks over a soft gradient
  starscape    deep-space card: gradient, nebula wisps, an optional lit planet disc, stars (values on ramp steps)
  planet       sphere-mapped planet: wavy latitude bands, longitude terminator shading (lit side at u = `lit_u`)
  crystal      faceted crystal: flat Voronoi facets with bright ridges
  strata       layered alien rock: wavy strata bands broken by vertical streaks
  organic      soft rounded cells (flora skin, caps, bulbs) with optional glowing spots
  regolith     planet ground: big soft blotches, faint drift ripples, sparse pebbles
"""
import math

import numpy as np

from . import texgen as T


def _wrap(d):
    return d - np.round(d)


def g_plating(rs, n, p):
    u, v = T._grid(n)
    cols, rows = int(p.get("cols", 2)), int(p.get("rows", 2))
    fu, fv = (u * cols) % 1.0, (v * rows) % 1.0
    ci = np.floor(u * cols).astype(int) % cols
    ri = np.floor(v * rows).astype(int) % rows
    tone = rs.random((rows, cols))
    # base = the panel body's place on the ramp (default 0.56, between two steps: an even mottle); a base on a ramp
    # step gives clean enamel panels where only the top-light gradient and the seams dither
    f = float(p.get("base", 0.56)) + float(p.get("grad", 0.22)) * (fv - 0.5) + float(p.get("tone", 0.08)) * (tone[ri, ci] - 0.5)
    f = f + float(p.get("mottle", 0.1)) * (T._norm(T.fbm(rs, n, 3, 2)) - 0.5)
    px_u, px_v = cols / float(n), rows / float(n)
    groove = (fu < px_u) | (fv < px_v)
    bevel = ((fu >= px_u) & (fu < 2 * px_u)) | ((fv > 1.0 - px_v))
    if p.get("inset"):
        a = float(p["inset"])
        inn = (fu > a) & (fu < 1 - a) & (fv > a) & (fv < 1 - a)
        rim = inn & ~((fu > a + px_u) & (fu < 1 - a - px_u) & (fv > a + px_v) & (fv < 1 - a - px_v))
        f = np.where(inn, f - 0.06, f)
        f = np.where(rim, f - 0.14, f)
    f = np.where(bevel, f + float(p.get("bevel", 0.12)), f)
    f = np.where(groove, f - float(p.get("seam", 0.32)), f)
    if p.get("rivets"):
        rv = ((np.abs(fu - 0.08) < px_u * 0.9) | (np.abs(fu - 0.92) < px_u * 0.9)) & (
            (np.abs(fv - 0.1) < px_v * 0.9) | (np.abs(fv - 0.9) < px_v * 0.9))
        f = np.where(rv, f + 0.18, f)
    return np.clip(f, 0, 1)


def _hex_lattice(k, m):
    pts = []
    for i in range(k):
        for j in range(m):
            pts.append(((i + 0.5) / k, (j + 0.5 + 0.5 * (i % 2)) / m))
    return np.asarray(pts)


def g_hexplate(rs, n, p):
    """k columns x m rows of flat-top hexagons (k even); k=6, m=5 is within 4% of regular and tiles the square."""
    k, m = int(p.get("cols", 6)), int(p.get("rows", 5))
    u, v = T._grid(n)
    C = _hex_lattice(k, m)
    best1 = np.full((n, n), 99.0)
    best2 = np.full((n, n), 99.0)
    ids = np.zeros((n, n), dtype=int)
    dys = np.zeros((n, n))
    for i, (cx, cy) in enumerate(C):
        # distances in the idealised lattice (column pitch 1.5 r, row pitch sqrt(3) r, r = 1)
        dx = _wrap(u - cx) * k * 1.5
        dy = _wrap(v - cy) * m * math.sqrt(3)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < best1
        best2 = np.where(closer, best1, np.minimum(best2, d))
        ids = np.where(closer, i, ids)
        dys = np.where(closer, dy, dys)
        best1 = np.where(closer, d, best1)
    tone = rs.random(len(C))
    edge = best2 - best1
    f = 0.55 + float(p.get("tone", 0.1)) * (tone[ids] - 0.5)
    f = f + float(p.get("grad", 0.1)) * np.clip(dys, -1, 1)
    f = f + float(p.get("mottle", 0.06)) * (T._norm(T.fbm(rs, n, 4, 2)) - 0.5)
    g = float(p.get("groove", 0.22))
    f = np.where((edge < g * 2.2) & (dys > 0), f + float(p.get("bevel", 0.1)), f)
    f = np.where(edge < g, 0.06, f)
    if p.get("bolt"):
        f = np.where(best1 < float(p["bolt"]), f + 0.22, f)
    return np.clip(f, 0, 1)


def g_grille(rs, n, p):
    u, v = T._grid(n)
    k = int(p.get("slats", 8))
    a = v if p.get("axis", "h") == "h" else u
    fa = (a * k) % 1.0
    gap = float(p.get("gap", 0.38))
    slat = 0.42 + 0.4 * np.sin(np.clip(fa / max(1e-6, 1 - gap), 0, 1) * math.pi) ** 0.7
    f = np.where(fa > 1 - gap, 0.04, slat)
    f = f + 0.06 * (T._norm(T.fbm(rs, n, 3, 1)) - 0.5)
    if p.get("frame"):
        fw = float(p["frame"])
        f = np.where((u < fw) | (u > 1 - fw) | (v < fw) | (v > 1 - fw), 0.5, f)
    return np.clip(f, 0, 1)


def g_hazard(rs, n, p):
    u, v = T._grid(n)
    k = int(p.get("count", 4))
    s = ((u + v) * k) % 1.0
    lit = s < float(p.get("ratio", 0.5))
    f = np.where(lit, 0.82, 0.14)
    f = f + float(p.get("wear", 0.1)) * (T._norm(T.fbm(rs, n, 4, 2)) - 0.5)
    return np.clip(f, 0, 1)


def g_lightstrip(rs, n, p):
    u, v = T._grid(n)
    k = int(p.get("cells", 4))
    fu = (u * k) % 1.0
    core = 1.0 - np.abs(v - 0.5) * 2.0 * float(p.get("falloff", 0.55))
    seg = 1.0 - float(p.get("joint", 0.3)) * (np.abs(fu - 0.5) * 2.0) ** 6
    f = np.clip(core, 0, 1) * seg
    jw = float(p.get("joint_w", 0.06))
    f = np.where((fu < jw) | (fu > 1 - jw), f * float(p.get("joint_level", 0.45)), f)
    return np.clip(f, 0, 1)


def g_brushed(rs, n, p):
    u, v = T._grid(n)
    streak = T._norm(T.fbm(rs, n, 3, 2, sx=float(p.get("stretch", 10)), sy=0.5))
    f = 0.5 + float(p.get("grad", 0.2)) * (v - 0.5) + float(p.get("streak", 0.22)) * (streak - 0.5)
    return np.clip(f, 0, 1)


def _steps(p):
    return max(2, len(p.get("ramp", [0, 1])))


def _at(step, nsteps):
    return step / float(nsteps - 1)


def g_starscape(rs, n, p):
    """Values sit exactly on ramp steps (dither off in the recipe): ramp = [void, space.., planet.., star]."""
    ns = _steps(p)
    space = int(p.get("space_steps", 4))
    u, v = T._grid(n)
    hz = float(p.get("glow_v", 0.0))
    g = np.clip((1.0 - np.abs(v - hz)) ** float(p.get("glow_gamma", 2.0)), 0, 1)
    neb = T._norm(T.fbm(rs, n, 3, 3, sx=float(p.get("neb_stretch", 3)), sy=1))
    band = np.exp(-((v - float(p.get("neb_v", 0.6)) - 0.12 * np.sin(u * math.tau)) / float(p.get("neb_w", 0.18))) ** 2)
    val = g * 0.45 + float(p.get("nebula", 0.55)) * band * neb
    lvl = np.clip(np.floor(val * space + 0.5 * (val > 0.0)), 0, space - 1)
    f = np.vectorize(lambda s: _at(s, ns))(lvl)
    if p.get("planet"):
        cx, cy, r = float(p.get("planet_u", 0.72)), float(p.get("planet_v", 0.32)), float(p.get("planet_r", 0.2))
        dx, dy = (u - cx) / r, (v - cy) / r
        d2 = dx * dx + dy * dy
        inside = d2 <= 1.0
        nz = np.sqrt(np.clip(1.0 - d2, 0, 1))
        lx, ly = -0.55, 0.45
        lam = np.clip(dx * lx + dy * ly + nz * 0.7, 0, 1)
        bands = 0.12 * np.sin((dy * 5.0 + 0.4 * T._norm(T.fbm(rs, n, 2, 2))) * math.pi)
        pl = np.clip(lam + bands, 0, 1)
        pst = len(p.get("ramp")) - space - 1
        idx = space + np.clip(np.floor(pl * pst * 0.999), 0, pst - 1)
        f = np.where(inside, np.vectorize(lambda s: _at(s, ns))(idx), f)
        if p.get("planet_rim", True):
            rim = (d2 > 0.86) & inside & (dx * lx + dy * ly > 0.1)
            f = np.where(rim, _at(ns - 2, ns), f)
    cnt = int(p.get("stars", 60))
    sx = rs.integers(0, n, cnt)
    sy = rs.integers(0, n, cnt)
    br = rs.random(cnt)
    for x, y, b in zip(sx, sy, br):
        if p.get("planet"):
            cx, cy, r = float(p.get("planet_u", 0.72)), float(p.get("planet_v", 0.32)), float(p.get("planet_r", 0.2))
            uu, vv = (x + 0.5) / n, 1.0 - (y + 0.5) / n
            if (uu - cx) ** 2 + (vv - cy) ** 2 < (r * 1.08) ** 2:
                continue
        f[y, x] = _at(ns - 1, ns) if b > 0.35 else _at(space - 1, ns)
        if b > 0.93 and x + 1 < n:
            f[y, x + 1] = _at(space - 1, ns)
    return f


def g_planet(rs, n, p):
    u, v = T._grid(n)
    lat = (v - 0.5) * math.pi
    turb = T._norm(T.fbm(rs, n, 3, 3, sx=4, sy=1))
    bands = 0.5 + 0.5 * np.sin((v * float(p.get("bands", 7)) + float(p.get("swirl", 0.35)) * turb) * math.tau)
    lit = np.cos((u - float(p.get("lit_u", 0.25))) * math.tau)
    lit = np.clip(lit * 0.75 + 0.35, 0, 1) * np.cos(lat) ** 0.5
    f = 0.08 + 0.62 * lit + float(p.get("band_amp", 0.22)) * (bands - 0.5) * lit
    if p.get("craters"):
        f1, f2, _ = T._cells(rs, n, int(p["craters"]))
        f = f - 0.18 * (f1 < 0.05) * lit + 0.1 * ((f1 > 0.05) & (f1 < 0.07)) * lit
    return np.clip(f, 0, 1)


def g_crystal(rs, n, p):
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 8)))
    tone = rs.random(ids.max() + 1)
    u, v = T._grid(n)
    f = 0.3 + 0.5 * tone[ids] + 0.25 * (v - 0.5)
    ridge = (f2 - f1) < float(p.get("edge", 0.03))
    f = np.where(ridge, 0.97, f)
    return np.clip(f, 0, 1)


def g_strata(rs, n, p):
    u, v = T._grid(n)
    warp = T._norm(T.fbm(rs, n, 2, 3, sx=1.5, sy=1))
    layers = int(p.get("layers", 5))
    s = (v * layers + float(p.get("wave", 0.35)) * warp) % 1.0
    tone = np.floor((v * layers + float(p.get("wave", 0.35)) * warp)).astype(int) % layers
    lt = rs.random(layers + 1)
    f = 0.32 + 0.4 * lt[tone] + 0.18 * s
    streak = T._norm(T.fbm(rs, n, 6, 2, sx=float(p.get("columns", 4)), sy=0.3))
    f = f + float(p.get("streak", 0.18)) * (streak - 0.5)
    f = np.where(s < 1.0 / n * layers * 1.2, f - 0.2, f)
    return np.clip(f, 0, 1)


def g_organic(rs, n, p):
    f1, f2, ids = T._cells(rs, n, int(p.get("cells", 10)))
    tone = rs.random(ids.max() + 1)
    lobe = 1.0 - T._norm(f1)
    f = 0.25 + 0.45 * lobe ** 0.8 + 0.2 * tone[ids]
    if p.get("veins"):
        f = np.where((f2 - f1) < 0.025, f - 0.22, f)
    if p.get("spots"):
        f = np.where(f1 < float(p["spots"]), 0.98, f)
    return np.clip(f, 0, 1)


def g_regolith(rs, n, p):
    big = T._norm(T.fbm(rs, n, int(p.get("lattice", 2)), 2))
    mid = T._norm(T.fbm(rs, n, 4, 2))
    rip = T._norm(T.fbm(rs, n, 3, 2, sx=2.0, sy=7.0))
    f = 0.5 + float(p.get("contrast", 0.8)) * (0.6 * (big - 0.5) + 0.25 * (mid - 0.5)) + float(p.get("ripple", 0.12)) * (rip - 0.5)
    peb = rs.random((n, n)) > (1.0 - float(p.get("pebbles", 0.012)))
    f = np.where(peb, f + 0.25, f)
    return np.clip(f, 0, 1)


GENS = {"plating": g_plating, "hexplate": g_hexplate, "grille": g_grille, "hazard": g_hazard,
        "lightstrip": g_lightstrip, "brushed": g_brushed, "starscape": g_starscape, "planet": g_planet,
        "crystal": g_crystal, "strata": g_strata, "organic": g_organic, "regolith": g_regolith}

for _name, _fn in GENS.items():
    if _name == "crystal":
        # The dungeon's existing crystal field stays global; retain sci-fi's token and RNG seed pack-locally.
        for _pack in ("space_station", "alien_world"):
            T.FIELD_GENS_BY_PACK[(_pack, _name)] = _fn
        continue
    if T.FIELD_GENS.get(_name, _fn) is not _fn and _name in T.FIELD_GENS:
        raise RuntimeError("texture generator name %r already taken" % _name)
    T.FIELD_GENS.setdefault(_name, _fn)
