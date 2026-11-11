"""n64_adult body family (lane CHARS3): adult N64/PS1-era proportions for the human cast, rig human16_v3.

Lives in ext/ (the vendored core/ stays byte-identical, so tall_v2 = every character built without a preset is the
round-21 build). Loaded into the core package by adventure_maker/nbchars/gen.Generator.ext('adult').

Body plan (fractions of the skull height H; hair rises above H):
  hero band        head 0.18-0.21 H (4.8-5.6 heads), a real neck, shoulders 1.6-2.2 head widths, hip joint
                   0.43-0.47 H, mitten fists 0.45-0.60 head widths, boots 0.17-0.24 H
  caricature band  head 0.23-0.28 H, hip joint 0.30-0.40 H, adult shoulders and hands (the CEOs)
  girl             head 0.25-0.28 H, small shoulders, large painted face (the Nous girl)
Construction: separate closed tubes per segment that overlap at the joints (torso, sleeves, mitts, trouser legs,
boots, head), the way N64/PS1 bodies were built, so no join can open under any pose. Every ring is horizontal.
Same 16 bone names, parents and creation order as human16_v1; only rest positions change.

Axes: Z up, the character faces -Y, +X is the character's left. Units: metres (params['height'] = skull top).
UVs are per triangle corner in Blender space (v up). Texture regions are owned by ext/adult_paint.py (REGIONS).
"""
import math

try:                                    # loaded into the core package (nbchars gen.Generator.ext)
    from . import pose as PO
except ImportError:                     # plain import with characters/gen on sys.path
    from core import pose as PO

PRESET = 'n64_adult'
PRESET_CARICATURE = 'n64_adult_caricature'
PRESETS = (PRESET, PRESET_CARICATURE)
SKELETON = 'human16_v3'
TOPOLOGY = 'human16_adult_a1'
TAU = 2 * math.pi
BONES = ['root', 'pelvis', 'spine', 'head', 'upper_arm_l', 'forearm_l', 'hand_l', 'thigh_l', 'shin_l', 'foot_l',
         'upper_arm_r', 'forearm_r', 'hand_r', 'thigh_r', 'shin_r', 'foot_r']
ROLE_SLOT = {'costume': 0, 'face': 1, 'headwear': 2, 'emblem': 3}

# texture regions in pixels (x, y, w, h), origin top-left. cloth 128x128, hair 64x64, face cell 64x64, emblem 32x32
CLOTH = 128
HAIR = 64
REGIONS = {
    'jacket': (0, 0, 128, 44), 'sleeve': (0, 44, 64, 36), 'trouser': (64, 44, 64, 36),
    'boot': (0, 80, 48, 24), 'foot': (0, 104, 48, 24), 'mitt': (48, 80, 32, 24), 'belt': (80, 80, 48, 10),
    'pouch': (80, 90, 24, 14), 'skin': (104, 90, 24, 14), 'collar': (48, 104, 80, 12), 'seat': (48, 116, 40, 12),
    'extra': (88, 116, 40, 12),
}
HAIR_REGIONS = {'side': (0, 0, 24, 32), 'back': (24, 0, 40, 32), 'top': (0, 32, 32, 32), 'spike': (32, 32, 16, 32),
                'spike_tip': (48, 32, 16, 32)}

ANG8 = [22.5 + 45. * k for k in range(8)]                 # torso rings: flat front, back and side faces
ANG6 = [60. * k for k in range(6)]                        # limb rings: flat front and back faces
HEAD8 = [22., 65., 115., 158., 198., 240., 300., 342.]    # head rings: a wide flat face (240..300 = front)
U8_FRONT, U8_BACK, U8_LEFT, U8_RIGHT = 5.5 / 8, 1.5 / 8, 7.5 / 8, 3.5 / 8

DEFAULTS = {
    'preset': PRESET, 'band': 'hero', 'height': 1.74,
    'head': .198, 'head_w': .88, 'head_d': .88, 'neck': .15, 'neck_r': .044, 'hip': .462,
    'shoulder': .114, 'chest': .124, 'chest_d': .132, 'waist': .118, 'waist_d': .122, 'band_r': .106, 'belly': 0.,
    'arm_r': 1.0, 'leg_r': 1.0, 'hand': .100, 'fist_w': 1.0, 'stance': 1.0, 'boot_h': .180, 'boot_len': .214, 'boot_r': 1.0, 'sleeve': 'long',
    'torso': 'bomber', 'hem': 0., 'hair': 'spikes', 'emblem': 'back', 'pouches': True, 'legs': 'cargo',
}


def _sgn(v):
    return -1. if v < 0 else 1.


def ring(angles, cx, cy, z, rx, ry, e=2.6):
    """Superellipse ring, counter-clockwise seen from above (standard angle: 0 = +X, 90 = +Y = back)."""
    out = []
    for a in angles:
        t = math.radians(a)
        c, s = math.cos(t), math.sin(t)
        out.append((cx + rx * _sgn(c) * abs(c) ** (2. / e), cy + ry * _sgn(s) * abs(s) ** (2. / e), z))
    return out


class Mesh:
    """The generator mesh contract assemble.py reads (same fields as core/geometry meshes)."""

    def __init__(self, params):
        self.params = params
        self.kind = 'human'
        self.topology = TOPOLOGY
        self.vertices, self.faces, self.uv, self.roles, self.weights = [], [], [], [], []
        self.parts = {}
        self.bones, self.parents = {}, dict(PO.HUMAN_PARENTS)
        self.tiles = {}
        self.landmarks = {}

    def v(self, p, w, part):
        self.vertices.append((float(p[0]), float(p[1]), float(p[2])))
        self.weights.append(dict(w))
        self.parts.setdefault(part, []).append(len(self.vertices) - 1)
        return len(self.vertices) - 1

    def vs(self, pts, w, part):
        return [self.v(p, w[i] if isinstance(w, list) else w, part) for i, p in enumerate(pts)]

    def tri(self, a, b, c, ua, ub, uc, role='costume'):
        self.faces.append((a, b, c)); self.uv.append((ua, ub, uc)); self.roles.append(role)

    def quad(self, a, b, c, d, ua, ub, uc, ud, role='costume'):
        self.tri(a, b, c, ua, ub, uc, role); self.tri(a, c, d, ua, uc, ud, role)

    def loft(self, lo, hi, uv_lo, uv_hi, role='costume'):
        """Band between two rings of equal count (lo below hi, both CCW from above). uv_*: n + 1 corners (wrap)."""
        n = len(lo)
        for j in range(n):
            k = (j + 1) % n
            self.quad(lo[j], lo[k], hi[k], hi[j], uv_lo[j], uv_lo[j + 1], uv_hi[j + 1], uv_hi[j], role)

    def cap(self, rng, uv, up=True, role='costume'):
        """Close a ring (counter-clockwise seen from above) with n-2 flat triangles and no new vertex. Hidden caps make
        every tube a closed solid, so the tubes are joined by real interpenetration (rigkit seams 'inside' test)."""
        for j in range(1, len(rng) - 1):
            if up:
                self.tri(rng[0], rng[j], rng[j + 1], uv, uv, uv, role)
            else:
                self.tri(rng[0], rng[j + 1], rng[j], uv, uv, uv, role)

    def fan_up(self, rng, apex, uv_ring, uv_apex, role='costume'):
        n = len(rng)
        for j in range(n):
            self.tri(rng[j], rng[(j + 1) % n], apex, uv_ring[j], uv_ring[j + 1], uv_apex, role)

    def fan_down(self, rng, apex, uv_ring, uv_apex, role='costume'):
        n = len(rng)
        for j in range(n):
            self.tri(rng[(j + 1) % n], rng[j], apex, uv_ring[j + 1], uv_ring[j], uv_apex, role)


def _reg(name, u, v, table=REGIONS, size=CLOTH, inset=.75):
    """Region-local (u, v) with v = 0 at the region top -> texture UV (Blender, v up), inset from the border."""
    x, y, w, h = table[name]
    px = x + inset + u * (w - 2 * inset)
    py = y + inset + v * (h - 2 * inset)
    return (px / size, 1. - py / size)


def _wrap(name, n, v, table=REGIONS, size=CLOTH, shift=0.):
    return [_reg(name, (j + shift) / float(n), v, table, size) for j in range(n + 1)]


def dims(p):
    """Landmarks in metres from the proportion parameters."""
    H = p['height']
    hh = p['head']
    D = {'H': H, 'hh': hh * H, 'hw': p['head_w'] * hh * H, 'hd': p['head_d'] * hh * H}
    chin = 1. - hh
    tt = chin - p['neck'] * hh                 # torso top (neck base)
    hip = p['hip']
    k = hip / .455                             # leg scale against the hero band
    D.update(chin=chin * H, tt=tt * H, hip=hip * H, sh_z=(tt - .021) * H, sh_x=p['shoulder'] * H,
             knee=hip * .56 * H, ankle=.062 * (.5 + .5 * k) * H, boot_top=p['boot_h'] * H,
             wrist=(hip - .030) * H, hip_x=.084 * H * p.get('stance', 1.), leg_k=k)
    D['elbow'] = (D['sh_z'] + D['wrist']) / 2. + .005 * H
    return D


def bones_for(p, D):
    H = D['H']
    b = {'root': (0., 0., 0.), 'pelvis': (0., 0., D['hip'] + .020 * H),
         'spine': (0., 0., D['hip'] + .090 * H), 'head': (0., .008 * H, D['chin'] - .006 * H)}
    for s, sg in (('l', 1.), ('r', -1.)):
        b['upper_arm_' + s] = (sg * D['sh_x'], 0., D['sh_z'])
        # the arm hangs far enough out that the fist clears the trouser at rest (wide builds get a wider A-pose)
        tr = (.092 if p.get('legs') != 'slim' else .080) * p['leg_r']
        thigh = max(D['hip_x'], (tr + .004) * H) + tr * H      # the thigh's outer side (see the midline clamp in leg)
        fist = p['hand'] * H / 2. * .82 * p.get('fist_w', 1.) * 1.02
        out = max(.104 * H, thigh + fist + .006 * H - D['sh_x'])
        b['forearm_' + s] = (sg * (D['sh_x'] + .5 * out), .004 * H, D['elbow'])
        b['hand_' + s] = (sg * (D['sh_x'] + out), -.010 * H, D['wrist'])
        b['thigh_' + s] = (sg * D['hip_x'], 0., D['hip'])
        b['shin_' + s] = (sg * (D['hip_x'] + (.008 + .06 * (p.get('stance', 1.) - 1.)) * H), -.004 * H, D['knee'])
        b['foot_' + s] = (sg * (D['hip_x'] + (.016 + .12 * (p.get('stance', 1.) - 1.)) * H), .006 * H, D['ankle'])
    return {n: b[n] for n in BONES}


# ------------------------------------------------------------------ torso
def torso(m, p, D):
    H = D['H']
    hip, tt = D['hip'], D['tt']
    bel = p['belly'] * H
    cr, cd, wr, wd, br = p['chest'] * H, p['chest_d'] * H, p['waist'] * H, p['waist_d'] * H, p['band_r'] * H
    bd = br * .88
    hem = p['hem'] * H                         # coat: the hem hangs this far below the hip
    span = tt - hip
    # (z, rx, ry, cy, weights)
    rows = [
        (hip + .007 * H - hem, br * (1. + .9 * p['hem']), bd * (1. + .9 * p['hem']), .008 * H, {'pelvis': 1.}),
        (hip + .042 * H, br * 1.02, bd * 1.02 + .4 * bel, .012 * H - .3 * bel, {'pelvis': 1.}),
        (hip + .36 * span, wr, wd + bel, -.5 * bel, {'pelvis': .5, 'spine': .5}),
        (tt - .25 * span, cr, cd + .3 * bel, -.014 * H - .2 * bel, {'spine': 1.}),
        (tt - .024 * H, cr * .90, cd * .88, 0., {'spine': 1.}),
        (tt, .052 * H, .050 * H, .002 * H, {'spine': 1.}),
    ]
    zs = [r[0] for r in rows]
    span_v = zs[-1] - zs[0]
    rings = []
    for z, rx, ry, cy, w in rows:
        rings.append(m.vs(ring(ANG8, 0., cy, z, rx, ry, 3.0), w, 'torso'))
    for i in range(len(rows) - 1):
        m.loft(rings[i], rings[i + 1], _wrap('jacket', 8, 1. - (zs[i] - zs[0]) / span_v),
               _wrap('jacket', 8, 1. - (zs[i + 1] - zs[0]) / span_v))
    m.cap(rings[0], _reg('seat', .5, .5), up=False)
    m.cap(rings[-1], _reg('collar', .5, .9))
    m.landmarks.update(torso_rows=[(r[0], r[1], r[2], r[3]) for r in rows], torso_top=tt)
    # back emblem: a decal quad just off the flat back face between the waist and chest rings
    if p.get('emblem') in ('back', 'chest'):
        front = p['emblem'] == 'chest'
        z1 = rows[4][0] - .022 * H
        z0 = max(rows[2][0] + .02 * H, z1 - .215 * H)
        if front:
            z0, z1 = rows[2][0] + .52 * (rows[3][0] - rows[2][0]), rows[3][0] + .25 * (rows[4][0] - rows[3][0])

        def face_y(z):
            for a, b in zip(rows[:-1], rows[1:]):
                if a[0] <= z <= b[0]:
                    t = (z - a[0]) / (b[0] - a[0])
                    ya = a[3] + a[2] * math.sin(math.radians(67.5)) ** (2. / 3.)
                    yb = b[3] + b[2] * math.sin(math.radians(67.5)) ** (2. / 3.)
                    y = ya + (yb - ya) * t
                    cya = a[3] + (b[3] - a[3]) * t
                    return (2 * cya - y) if front else y
            return 0.
        zc = rows[3][0]
        hw = min(.5 * (z1 - z0), .040 * H if front else .064 * H, .96 * min(rows[3][1], rows[4][1]) * math.cos(math.radians(67.5)) ** (2. / 3.0))
        off = (-.0015 if front else .0015) * H           # 2.6 mm: inside the 3 mm seam tolerance, clear of z-fighting
        s = -1. if front else 1.

        def wz(z):                               # the decal moves with the cloth under it
            for a, b in zip(rows[:-1], rows[1:]):
                if a[0] <= z <= b[0]:
                    t = (z - a[0]) / (b[0] - a[0])
                    w = {}
                    for src, k in ((a[4], 1. - t), (b[4], t)):
                        for n, x in src.items():
                            w[n] = w.get(n, 0.) + x * k
                    return {n: x for n, x in w.items() if x > 1e-6}
            return {'spine': 1.}
        vc = (zc - z0) / (z1 - z0)
        if front:
            q = [m.v((sx * hw, face_y(z) + off, z), wz(z), 'emblem') for z in (z0, zc, z1) for sx in (s, -s)]
            m.quad(q[0], q[1], q[3], q[2], (0., 0.), (1., 0.), (1., vc), (0., vc), 'emblem')
            m.quad(q[2], q[3], q[5], q[4], (0., vc), (1., vc), (1., 1.), (0., 1.), 'emblem')
        else:
            # the back emblem is wider than the flat back facet, so the decal bends onto the two facets beside it

            def ring_at(z):
                for i, (a, b) in enumerate(zip(rows[:-1], rows[1:])):
                    if a[0] <= z <= b[0]:
                        t = (z - a[0]) / (b[0] - a[0])
                        return [tuple(m.vertices[rings[i][j]][c] + (m.vertices[rings[i + 1][j]][c] - m.vertices[rings[i][j]][c]) * t
                                      for c in range(3)) for j in range(4)]
            ext = .036 * H
            grid, us = [], None
            for z in (z0, zc, z1):
                P = ring_at(z)
                fa = min(.8, ext / math.dist(P[0], P[1]))
                fb = min(.8, ext / math.dist(P[3], P[2]))
                pa = [P[1][c] + (P[0][c] - P[1][c]) * fa for c in range(2)]
                pb = [P[2][c] + (P[3][c] - P[2][c]) * fb for c in range(2)]
                row = [(pa[0] + .7 * off, pa[1] + .7 * off, z), (P[1][0], P[1][1] + off, z),
                       (P[2][0], P[2][1] + off, z), (pb[0] - .7 * off, pb[1] + .7 * off, z)]
                grid.append([m.v(q_, wz(z), 'emblem') for q_ in row])
                if z == zc:
                    wd = math.dist(P[1][:2], P[2][:2])
                    us = [0., ext / (wd + 2 * ext), (ext + wd) / (wd + 2 * ext), 1.]
            vs_ = [0., vc, 1.]
            for r_ in range(2):
                for c_ in range(3):
                    m.quad(grid[r_][c_], grid[r_][c_ + 1], grid[r_ + 1][c_ + 1], grid[r_ + 1][c_],
                           (us[c_], vs_[r_]), (us[c_ + 1], vs_[r_]), (us[c_ + 1], vs_[r_ + 1]), (us[c_], vs_[r_ + 1]), 'emblem')
    # collar: a low knit band around the neck base
    c0 = m.vs(ring(ANG8, 0., .002 * H, tt - .006 * H, .060 * H, .058 * H, 2.4), {'spine': 1.}, 'collar')
    if p['torso'] in ('bomber', 'coat'):         # stand-up collar: high behind the nape, low under the chin
        c0 = m.vs(ring(ANG8, 0., .004 * H, tt - .012 * H, .064 * H, .062 * H, 2.4), {'spine': 1.}, 'collar')
        top = [(x, y, z + .030 * H + .22 * y) for x, y, z in ring(ANG8, 0., .010 * H, tt, .082 * H, .078 * H, 2.4)]
        c1 = m.vs(top, {'spine': 1.}, 'collar')
    else:
        c1 = m.vs(ring(ANG8, 0., .006 * H, tt + .013 * H, .058 * H, .058 * H, 2.4), {'spine': 1.}, 'collar')
    m.loft(c0, c1, _wrap('collar', 8, .95), _wrap('collar', 8, .05))
    # neck
    nr = p['neck_r'] * H
    n0 = m.vs(ring(ANG6, 0., .004 * H, tt - .012 * H, nr * 1.08, nr * 1.08, 2.2), {'spine': 1.}, 'neck')
    n1 = m.vs(ring(ANG6, 0., -.004 * H, D['chin'] + .035 * H, nr, nr, 2.2), {'head': 1.}, 'neck')
    m.loft(n0, n1, _wrap('skin', 6, .95), _wrap('skin', 6, .05))
    # belt + seat under the jacket band
    if p['torso'] != 'coat':
        zb = hip + .010 * H
        b0 = m.vs(ring(ANG8, 0., 0., zb - .026 * H, br * .98, bd * .98, 3.0), {'pelvis': 1.}, 'belt')
        b1 = m.vs(ring(ANG8, 0., 0., zb, br * 1.0, bd * 1.0, 3.0), {'pelvis': 1.}, 'belt')
        m.loft(b0, b1, _wrap('belt', 8, .95), _wrap('belt', 8, .05))
        m.cap(b0, _reg('seat', .5, .5), up=False)


def _box(m, c, half, w, part, region, sg=1.):
    """Five-sided box (the face toward the body is left open). sg: +1 on the left side (outer face = +X)."""
    hx, hy, hz = half
    P = {}
    for ix in (0, 1):
        for iy in (0, 1):
            for iz in (0, 1):
                P[(ix, iy, iz)] = m.v((c[0] + sg * (hx if ix else -hx), c[1] + (hy if iy else -hy), c[2] + (hz if iz else -hz)), w, part)

    def f(a, b, cc, d, u0, v0, u1, v1):
        vs = [P[a], P[b], P[cc], P[d]]
        if sg < 0:
            vs = [vs[1], vs[0], vs[3], vs[2]]
            uv = [_reg(region, u1, v1), _reg(region, u0, v1), _reg(region, u0, v0), _reg(region, u1, v0)]
        else:
            uv = [_reg(region, u0, v1), _reg(region, u1, v1), _reg(region, u1, v0), _reg(region, u0, v0)]
        m.quad(vs[0], vs[1], vs[2], vs[3], uv[0], uv[1], uv[2], uv[3])
    f((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1), .2, 0., .8, 1.)        # outer
    f((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), 0., 0., .2, 1.)        # front
    f((1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1), .8, 0., 1., 1.)        # back
    f((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1), .2, 0., .8, .25)       # top
    f((0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0), .2, .8, .8, 1.)        # bottom


# ------------------------------------------------------------------ arms
def arm(m, p, D, side):
    H = D['H']
    sg = 1. if side == 'l' else -1.
    k = p['arm_r']
    ua, fa, ha, sp = 'upper_arm_' + side, 'forearm_' + side, 'hand_' + side, 'spine'
    S, E, W = m.bones[ua], m.bones[fa], m.bones[ha]
    ang = ANG6 if sg > 0 else [180. - a for a in reversed(ANG6)]   # mirrored ring, still CCW from above
    part = 'sleeve_' + side

    def at(z):                                   # arm centre line at height z
        if z >= E[2]:
            t = (S[2] - z) / (S[2] - E[2]); a, b = S, E
        else:
            t = (E[2] - z) / (E[2] - W[2]); a, b = E, W
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    puff = .037 if p['torso'] in ('bomber', 'coat', 'armor') else .033
    rows = [(S[2] + .010 * H, .052 * k, {ua: 1.}), (E[2], .040 * k, {ua: .5, fa: .5}),
            (W[2] + .050 * H, puff * k, {fa: 1.}), (W[2] + .018 * H, .030 * k, {fa: 1.}), (W[2] - .004 * H, .028 * k, {fa: 1.})]
    if p['torso'] == 'top':                      # sleeveless: bare arms
        rows = [(S[2] + .010 * H, .040 * k, {ua: 1.}), (E[2], .034 * k, {ua: .5, fa: .5}),
                (W[2] + .050 * H, .032 * k, {fa: 1.}), (W[2] + .018 * H, .028 * k, {fa: 1.}), (W[2] - .004 * H, .027 * k, {fa: 1.})]
    vs_ = None
    if p.get('sleeve') == 'puff34' and p['torso'] != 'top':
        # three-quarter bomber sleeve: full upper arm, a puffed cuff below the elbow, then the bare forearm
        zc = W[2] + .42 * (E[2] - W[2])
        rows = [(S[2] + .010 * H, .056 * k, {ua: 1.}), (E[2], .066 * k, {ua: .5, fa: .5}),
                (zc + .014 * H, .070 * k, {fa: 1.}), (zc, .038 * k, {fa: 1.}), (W[2] - .004 * H, .034 * k, {fa: 1.})]
        vs_ = [.08, .50, .72, .77, 1.]
    zs = [r[0] for r in rows]
    rings = []
    for i, (z, r, w) in enumerate(rows):
        cx, cy = at(z)
        pts = ring(ang, cx, cy, z, r * H, r * H * 1.04, 2.3)
        ws = [dict(w) for _ in pts]
        if i == 0:                               # armpit side of the shoulder ring follows the chest a little
            for j, q in enumerate(pts):
                if sg * (q[0] - cx) < -.5 * r * H:
                    ws[j] = {ua: .85, sp: .15}
        rings.append(m.vs(pts, ws, part))
    span = zs[0] - zs[-1]
    if vs_ is None:
        vs_ = [(zs[0] - z) / span * .92 + .08 for z in zs]
    for i in range(len(rows) - 1):
        m.loft(rings[i + 1], rings[i], _wrap('sleeve', 6, vs_[i + 1]), _wrap('sleeve', 6, vs_[i]))
    cap = m.v((S[0] - sg * .006 * H, S[1], S[2] + .034 * H * k), {ua: .8, sp: .2}, part)
    m.fan_up(rings[0], cap, _wrap('sleeve', 6, .08), _reg('sleeve', .5, 0.))
    # hidden shoulder root: one triangle from the armpit side of the ring to a vertex that stays inside the chest, so
    # the sleeve is anchored to the torso in every pose (rigkit seams join) without a skin spanning the joint
    root = m.v((S[0] - sg * .016 * H, S[1], S[2] - .020 * H), {sp: 1.}, part)
    inner = sorted(range(len(rings[0])), key=lambda j: sg * m.vertices[rings[0][j]][0])[:2]
    uv = _reg('sleeve', .5, .10)
    m.tri(rings[0][inner[0]], rings[0][inner[1]], root, uv, uv, uv)
    # mitten fist: thickness along X, width along Y (the palm faces the thigh)
    hw = p['hand'] * H / 2.
    ht = hw * .82 * p.get('fist_w', 1.)
    cx, cy = W[0] + sg * .004 * H, W[1]
    mp = 'mitt_' + side
    r0 = m.vs(ring(ang, cx, cy, W[2] + .012 * H, ht * .92, hw * .70, 2.4), {ha: .7, fa: .3}, mp)
    r1 = m.vs(ring(ang, cx, cy - .004 * H, W[2] - .034 * H, ht * 1.02, hw, 3.0), {ha: 1.}, mp)
    r2 = m.vs(ring(ang, cx, cy - .006 * H, W[2] - .034 * H - hw * 1.05, ht * .94, hw * .90, 3.0), {ha: 1.}, mp)
    L = (W[2] + .012 * H) - (W[2] - .034 * H - hw * 1.05)
    m.cap(r0, _reg('mitt', .5, .04))
    m.loft(r1, r0, _wrap('mitt', 6, .40), _wrap('mitt', 6, .04))
    m.loft(r2, r1, _wrap('mitt', 6, .86), _wrap('mitt', 6, .40))
    m.cap(r2, _reg('mitt', .5, 1.), up=False)        # flat-bottomed block fist
    # thumb: a small wedge on the front of the fist
    tp = 'thumb_' + side
    zt = W[2] - .030 * H
    a = m.v((cx - sg * ht * .3, cy - hw * .62, zt + .004 * H), {ha: 1.}, tp)
    b = m.v((cx + sg * ht * .5, cy - hw * .62, zt + .004 * H), {ha: 1.}, tp)
    c = m.v((cx + sg * ht * .1, cy - hw * .84, zt - hw * .75), {ha: 1.}, tp)
    d = m.v((cx + sg * ht * .1, cy - hw * 1.16, zt - .006 * H), {ha: 1.}, tp)
    ua_, ub_, uc_, ud_ = _reg('mitt', .30, .30), _reg('mitt', .70, .30), _reg('mitt', .5, .62), _reg('mitt', .5, .40)
    for tri, uvs in (((a, d, b), (ua_, ud_, ub_)), ((b, d, c), (ub_, ud_, uc_)), ((c, d, a), (uc_, ud_, ua_))):
        if sg > 0:
            m.tri(tri[0], tri[1], tri[2], uvs[0], uvs[1], uvs[2])
        else:
            m.tri(tri[0], tri[2], tri[1], uvs[0], uvs[2], uvs[1])
    m.landmarks['mitt_len_' + side] = L


# ------------------------------------------------------------------ legs
def leg(m, p, D, side):
    H = D['H']
    sg = 1. if side == 'l' else -1.
    k = p['leg_r']
    th, sh, ft, pe = 'thigh_' + side, 'shin_' + side, 'foot_' + side, 'pelvis'
    T, K, A = m.bones[th], m.bones[sh], m.bones[ft]
    ang = ANG6 if sg > 0 else [180. - a for a in reversed(ANG6)]
    part = 'trouser_' + side
    bt = D['boot_top']
    slim = p.get('legs') == 'slim'
    rows = [(T[2] + .030 * H, .068 * k, .086 * k, T[0] - sg * .003 * H, .004 * H, {th: .7, pe: .3}),
            (T[2] - .055 * H * D['leg_k'], (.080 if slim else .092) * k, .098 * k,
             # the thighs never cross the midline: two solids that touch at rest would be read as joined
             T[0] + sg * max(0., ((.080 if slim else .092) * k + .004) * H - abs(T[0])), -.004 * H, {th: 1.}),
            (K[2], (.050 if slim else .094) * k, (.054 if slim else .100) * k, K[0], K[1], {th: .5, sh: .5}),
            (bt + .024 * H, (.047 if slim else .096) * k, (.050 if slim else .104) * k, A[0], .008 * H, {sh: 1.}),
            (bt - .012 * H, .050 * k, .054 * k, A[0], .003 * H, {sh: 1.})]
    zs = [r[0] for r in rows]
    span = zs[0] - zs[-1]
    # Two rigid solids per leg (thigh, shin) that overlap at the knee: nothing spans the joint, so a deep knee bend
    # (roll, sit) folds like a period model instead of stretching a skin. The shin's capped top sits inside the thigh.
    kz, krx, kry, kx, ky, _ = rows[2]
    rows = [rows[0], rows[1], (kz - .014 * H, krx, kry, kx, ky, {th: 1.}),
            (kz + .016 * H, krx * .90, kry * .90, kx, ky, {sh: 1.}), rows[3], rows[4]]
    zs = [r[0] for r in rows]
    vv = [(zs[0] - z) / span for z in zs]
    vv[3] = vv[2]                                # the hidden overlap repeats the knee row of the sheet
    rings = [m.vs(ring(ang, cx, cy, z, rx * H, ry * H, 2.5), w, part) for z, rx, ry, cx, cy, w in rows]
    for i in (0, 1, 3, 4):
        m.loft(rings[i + 1], rings[i], _wrap('trouser', 6, vv[i + 1]), _wrap('trouser', 6, vv[i]))
    m.cap(rings[2], _reg('trouser', .5, vv[2]), up=False)
    m.cap(rings[0], _reg('trouser', .5, vv[0]))        # closed thigh: the shin's top ring is anchored inside it
    m.landmarks['thigh_row'] = rows[1][:5]
    if p.get('pouches') is True and p.get('torso') in ('bomber', 'coat', 'shirt', 'armor', 'hood', 'top'):
        # thigh holster on the back-outer corner: rigid with the thigh, clear of the hanging fist and of the pelvis
        z, rx, ry, cx, cy = rows[1][:5]
        _box(m, (cx + sg * rx * H * .62, cy + ry * H * .66, z - .012 * H), (.020 * H, .022 * H, .030 * H), {th: 1.}, 'pouch', 'pouch', sg)
    m.cap(rings[3], _reg('trouser', .5, vv[2]))
    # boot shaft
    bp = 'boot_' + side
    br = p['boot_r']
    srows = [(bt, .072 * br, .080 * br, .003 * H, {sh: 1.}), (A[2] + .022 * H, .068 * br, .074 * br, .004 * H, {sh: .55, ft: .45}),
             (A[2] - .022 * H, .066 * br, .072 * br, .004 * H, {ft: 1.})]
    szs = [r[0] for r in srows]
    srings = [m.vs(ring(ang, A[0], cy, z, rx * H, ry * H, 2.6), w, bp) for z, rx, ry, cy, w in srows]
    for i in range(len(srows) - 1):
        m.loft(srings[i + 1], srings[i], _wrap('boot', 6, (szs[0] - szs[i + 1]) / (szs[0] - szs[-1])),
               _wrap('boot', 6, (szs[0] - szs[i]) / (szs[0] - szs[-1])))
    # foot: three box sections along the length (heel, instep, toe), sole on the floor
    m.cap(srings[0], _reg('boot', .5, .02))
    m.cap(srings[-1], _reg('boot', .5, .98), up=False)
    L = p['boot_len'] * H
    y_heel = A[1] + .36 * L
    secs = [(y_heel, .062 * br * H, .068 * H, .0), (y_heel - .42 * L, .072 * br * H, .084 * H, .0),
            (y_heel - .86 * L, .078 * br * H, .070 * H, .0), (y_heel - L, .066 * br * H, .048 * H, .004 * H)]
    top_z = max(s[2] for s in secs)

    def fuv(y, z):
        return _reg('foot', (y_heel - y) / L, 1. - z / (top_z * 1.02))
    S = []
    for y, hw, zt, z0 in secs:
        pts = [(A[0] - hw, y, z0), (A[0] + hw, y, z0), (A[0] + hw * .88, y, zt), (A[0] - hw * .88, y, zt)]
        S.append([m.v(q, {ft: 1.}, bp) for q in pts])
    for a, b in zip(S[:-1], S[1:]):              # a behind b (b toward the toe, -Y)
        ya, yb = m.vertices[a[0]][1], m.vertices[b[0]][1]
        za, zb = m.vertices[a[2]][2], m.vertices[b[2]][2]
        m.quad(a[1], a[0], b[0], b[1], fuv(ya, 0), fuv(ya, 0), fuv(yb, 0), fuv(yb, 0))                 # sole
        m.quad(a[2], a[1], b[1], b[2], fuv(ya, za), fuv(ya, 0), fuv(yb, 0), fuv(yb, zb))             # +X side
        m.quad(a[0], a[3], b[3], b[0], fuv(ya, 0), fuv(ya, za), fuv(yb, zb), fuv(yb, 0))             # -X side
        m.quad(a[3], a[2], b[2], b[3], fuv(ya, za), fuv(ya, za), fuv(yb, zb), fuv(yb, zb))           # top
    h, t = S[0], S[-1]
    yh, yt = m.vertices[h[0]][1], m.vertices[t[0]][1]
    m.quad(h[0], h[1], h[2], h[3], fuv(yh, 0), fuv(yh, 0), fuv(yh, secs[0][2]), fuv(yh, secs[0][2]))   # heel cap
    m.quad(t[1], t[0], t[3], t[2], fuv(yt, 0), fuv(yt, 0), fuv(yt, secs[-1][2]), fuv(yt, secs[-1][2]))  # toe cap


# ------------------------------------------------------------------ head
def head(m, p, D):
    H = D['H']
    hh, hw, hd = D['hh'], D['hw'] / 2., D['hd'] / 2.
    z0 = D['chin']
    cy = -.012 * H
    w = {'head': 1.}
    girl = p['band'] == 'girl'
    # (z / hh, rx / half width, ry / half depth, cy / hh)
    rows = [(.09, .76, .70, -.07), (.32, .96, .95, -.02), (.68, 1.0, 1.0, .0), (.90, .76, .80, .03)]
    if girl:
        rows = [(.09, .50, .58, -.05), (.33, .98, .94, -.01), (.66, 1.0, 1.0, .0), (.90, .78, .82, .03)]
    hv = {'spikes': 1.22, 'curly': 1.12, 'bob': 1.12, 'short': 1.04}.get(p['hair'], 1.)   # the hair mass flares the skull
    if hv > 1.1:                                 # hair fills the nape: the back of the two lower rows moves out, the face does not
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] + .13, rows[0][3] + .055)
        rows[1] = (rows[1][0], rows[1][1], rows[1][2] + .08, rows[1][3] + .035)
    rows[2] = (rows[2][0], rows[2][1] * hv, rows[2][2] * hv, rows[2][3] + (hv - 1.) * .25)
    rows[3] = (rows[3][0], rows[3][1] * (1. + (hv - 1.) * 1.4), rows[3][2] * (1. + (hv - 1.) * 1.4), rows[3][3] + (hv - 1.) * .25)
    rings = [m.vs(ring(HEAD8, 0., cy + c * hh, z0 + z * hh, rx * hw, ry * hd, 2.2), w, 'face') for z, rx, ry, c in rows]
    chin = m.v((0., cy - .16 * hh, z0), w, 'face')
    crown = m.v((0., cy + .03 * hh, z0 + hh), w, 'face')
    fw = hw * 1.0                                 # the face cell spans +-fw in x, chin .. top ring in z
    ztop = rows[-1][0] * hh

    def fuv(i):
        x, y, z = m.vertices[i]
        return (min(1., max(0., .5 + .5 * x / fw)) * .96 + .02, min(1., max(0., (z - z0) / ztop)) * .96 + .02)

    def huv(i, col):
        x, y, z = m.vertices[i]
        v = 1. - min(1., max(0., (z - z0) / hh))
        if col in (3, 7):                         # side panels: +Y (back) to the right of the region
            return _reg('side', min(1., max(0., .5 + .5 * (y - cy) / hd)), v, HAIR_REGIONS, HAIR)
        return _reg('back', min(1., max(0., .5 - .5 * x / hw)), v, HAIR_REGIONS, HAIR)
    for i in range(len(rings) - 1):
        lo, hi = rings[i], rings[i + 1]
        for j in range(8):
            k = (j + 1) % 8
            if j in (4, 5, 6):
                m.quad(lo[j], lo[k], hi[k], hi[j], fuv(lo[j]), fuv(lo[k]), fuv(hi[k]), fuv(hi[j]), 'face')
            else:
                m.quad(lo[j], lo[k], hi[k], hi[j], huv(lo[j], j), huv(lo[k], j), huv(hi[k], j), huv(hi[j], j), 'headwear')
    for j in range(8):
        k = (j + 1) % 8
        lo = rings[0]
        if j in (4, 5, 6):
            m.tri(lo[k], lo[j], chin, fuv(lo[k]), fuv(lo[j]), fuv(chin), 'face')
        else:
            m.tri(lo[k], lo[j], chin, _reg('skin', .2, .5), _reg('skin', .8, .5), _reg('skin', .5, .8), 'costume')
        hi = rings[-1]

        def tuv(i):
            x, y, z = m.vertices[i]
            return _reg('top', .5 + .5 * x / hw, .5 + .5 * (y - cy) / hd, HAIR_REGIONS, HAIR)
        m.tri(hi[j], hi[k], crown, tuv(hi[j]), tuv(hi[k]), tuv(crown), 'headwear')
    # nose: a small wedge on the flat front face
    def front_y(zr):
        a, b = rows[1], rows[2]
        t = (zr - a[0]) / (b[0] - a[0])
        s = abs(math.sin(math.radians(240.))) ** (2. / 2.2)
        ya = cy + a[3] * hh - a[2] * hd * s
        yb = cy + b[3] * hh - b[2] * hd * s
        return ya + (yb - ya) * t
    nz0, nz1 = (.44, .30) if not girl else (.40, .31)
    nt = .13 if not girl else .07
    a = m.v((.050 * hh, front_y(nz0) + .004 * H, z0 + nz0 * hh), w, 'nose')
    b = m.v((-.050 * hh, front_y(nz0) + .004 * H, z0 + nz0 * hh), w, 'nose')
    c = m.v((0., front_y(nz1) + .004 * H, z0 + (nz1 - .02) * hh), w, 'nose')
    t = m.v((0., front_y(nz1) - nt * hh, z0 + (nz1 + .03) * hh), w, 'nose')
    m.tri(a, t, c, fuv(a), fuv(t), fuv(c), 'face')
    m.tri(b, c, t, fuv(b), fuv(c), fuv(t), 'face')
    m.tri(a, b, t, fuv(a), fuv(b), fuv(t), 'face')
    if p['hair'] not in ('bob', 'hood'):          # ears: a three-face wedge on each side panel
        for sg in (1., -1.):
            ex = sg * hw * .92                       # the ear's base sits inside the skull
            ey = cy + .10 * hd
            e0 = m.v((ex, ey - .16 * hd, z0 + .50 * hh), w, 'ear')
            e1 = m.v((ex, ey - .10 * hd, z0 + .30 * hh), w, 'ear')
            e2 = m.v((ex, ey + .16 * hd, z0 + .40 * hh), w, 'ear')
            e3 = m.v((ex + sg * .095 * hh, ey + .12 * hd, z0 + .43 * hh), w, 'ear')
            sk = [_reg('skin', .15, .9), _reg('skin', .30, .9), _reg('skin', .22, .6)]
            for a_, b_, c_ in ((e0, e1, e3), (e1, e2, e3), (e2, e0, e3)):
                if sg > 0:
                    m.tri(a_, b_, c_, sk[0], sk[1], sk[2], 'costume')
                else:
                    m.tri(a_, c_, b_, sk[0], sk[2], sk[1], 'costume')
    m.landmarks.update(head_cy=cy, face_fw=fw, face_ztop=ztop)
    return cy


KEY = (-.45, -.40, .80)                                   # key light direction used to pick a facet's painted tone


def _spike(m, base, r, tip, sides=4, part='hair', region='spike', rv=1., sink=.8):
    """Open pyramid rooted in the head: base ring perpendicular to the axis (rv flattens it into a wedge), apex at tip.
    Each facet takes one of three flat tones (lit, mid, dark columns of its hair-sheet region) from its normal."""
    ax = PO._sub(tip, base)
    n = math.sqrt(sum(c * c for c in ax)) or 1.
    ax = tuple(c / n for c in ax)
    ref = (0., 0., 1.) if abs(ax[2]) < .9 else (0., 1., 0.)
    u = PO._cross(ax, ref); un = math.sqrt(sum(c * c for c in u)); u = tuple(c / un for c in u)
    v = PO._cross(ax, u)
    w = {'head': 1.}
    base = tuple(base[i] - ax[i] * r * sink for i in range(3))   # the whole base rim sits inside the skull: no gap under it
    rng = []
    for j in range(sides):
        t = TAU * j / sides                      # diamond section: a ridge on top and on each side, so a side view shows a lit upper facet over a dark lower one
        rng.append(m.v(tuple(base[i] + r * (math.cos(t) * u[i] + rv * math.sin(t) * v[i]) for i in range(3)), w, part))
    apex = m.v(tip, w, part)
    ds = []
    for j in range(sides):
        k = (j + 1) % sides
        A, B = m.vertices[rng[j]], m.vertices[rng[k]]
        nrm = PO._cross(PO._sub(B, A), PO._sub(tip, A))
        nl = math.sqrt(sum(c * c for c in nrm)) or 1.
        mid = tuple((A[i] + B[i]) / 2. - base[i] for i in range(3))
        if sum(nrm[i] * mid[i] for i in range(3)) < 0.:
            nrm = tuple(-c for c in nrm)
        ds.append(sum(nrm[i] * KEY[i] for i in range(3)) / nl)
    # tones are ranked inside the spike: its most lit facet is light and its least lit is dark wherever it points, so a
    # spike on the unlit back of the head still shows a ridge
    order = sorted(range(sides), key=lambda j: (-ds[j], j))
    tone = {}
    for n_, j in enumerate(order):
        tone[j] = .16 if n_ == 0 else (.84 if n_ >= sides - 1 - (1 if sides > 4 else 0) else .50)
    for j in range(sides):
        k = (j + 1) % sides
        uc = tone[j]
        m.tri(rng[j], rng[k], apex, _reg(region, uc - .10, 1., HAIR_REGIONS, HAIR), _reg(region, uc + .10, 1., HAIR_REGIONS, HAIR),
              _reg(region, uc, 0., HAIR_REGIONS, HAIR), 'headwear')


# hair styles: (base, radius, tip, region, flatten) in head heights: x left, y back (-y is the face), z up from the chin.
# Bases sit ON the flared skull with radii about half the spike length, so the chunks overlap into one mass.
SPIKES = {
    'spikes': [
        # three wedge bangs hanging over the brow (crown tint)
        ((0., -.36, .82), .22, (.03, -.58, .62), 'spike_tip', .62),
        ((.28, -.30, .82), .21, (.44, -.50, .60), 'spike_tip', .62),
        ((-.28, -.30, .82), .21, (-.46, -.48, .64), 'spike_tip', .62),
        # front crest: two tinted spikes standing up over the forehead, leaning apart
        ((.23, -.12, .94), .34, (.50, -.26, 1.58), 'spike_tip', 1.),
        ((-.22, -.06, .95), .34, (-.56, .04, 1.44), 'spike_tip', 1.),
        # the mass behind them: one big spike up and back, two out over the ears, one straight back, one down the nape
        # (nothing here is mirrored: the mass sweeps back and a little to one side, one tinted spike ties the colours)
        ((-.04, .22, .90), .48, (-.14, .86, 1.56), 'spike', 1.),
        ((.34, .24, .84), .38, (.92, .72, 1.16), 'spike', 1.),
        ((-.34, .26, .76), .38, (-.98, .64, .86), 'spike', 1.),
        ((.08, .42, .62), .44, (.24, 1.22, .74), 'spike', 1.),
        ((-.05, .40, .36), .40, (-.18, .90, .10), 'spike', 1.)],
}


def hair(m, p, D, cy):
    hh, z0 = D['hh'], D['chin']
    style = p['hair']
    for base, r, tip, region, rv in SPIKES.get(style, []):
        _spike(m, (base[0] * hh, cy + base[1] * hh, z0 + base[2] * hh), r * hh,
               (tip[0] * hh, cy + tip[1] * hh, z0 + tip[2] * hh), part='hair', region=region, rv=rv)


def resolve(values):
    p = dict(DEFAULTS)
    p.update(values or {})
    if p['preset'] not in PRESETS:
        raise ValueError('ext/adult builds presets %s, not %r' % (PRESETS, p['preset']))
    return p


def mirror(m, v0, f0):
    """Right-side copy of everything built since (v0, f0): x -> -x, bone / part names _l -> _r, winding reversed,
    same UVs (so both sides share their texture region exactly)."""
    n = len(m.vertices)
    part_of = {}
    for name, idx in m.parts.items():
        for i in idx:
            if i >= v0:
                part_of[i] = name
    swap = lambda s: s[:-2] + '_r' if s.endswith('_l') else s
    remap = {}
    for i in range(v0, n):
        x, y, z = m.vertices[i]
        remap[i] = m.v((-x, y, z), {swap(b): w for b, w in m.weights[i].items()}, swap(part_of[i]))
    for fi in range(f0, len(m.faces)):
        a, b, c = m.faces[fi]
        ua, ub, uc = m.uv[fi]
        m.tri(remap[a], remap[c], remap[b], ua, uc, ub, m.roles[fi])


def person(values):
    p = resolve(values)
    m = Mesh(p)
    D = dims(p)
    m.bones = bones_for(p, D)
    torso(m, p, D)
    v0, f0 = len(m.vertices), len(m.faces)
    arm(m, p, D, 'l')
    leg(m, p, D, 'l')
    mirror(m, v0, f0)
    if p.get('pouches') == 'right':               # one strapped holster, on the right thigh only
        z, rx, ry, cx, cy = m.landmarks['thigh_row']
        H = D['H']
        _box(m, (-cx - rx * H * .62, cy + ry * H * .66, z - .012 * H), (.022 * H, .024 * H, .034 * H), {'thigh_r': 1.}, 'pouch', 'pouch', -1.)
    cy = head(m, p, D)
    hair(m, p, D, cy)
    m.landmarks['dims'] = D
    return m
