"""Props of the cast_v1 family (lane CAST1): separate rigid meshes on a bone, never part of the body budget.

build(kind, m, colors, pack) -> {'kind', 'slot', 'bone', 'vertices', 'faces', 'uv', 'texture'} in body space (the
caller re-bases the vertices to the bone head, as nbchars/adult._prop_socket does). Every prop is placed from the
measured mesh `m` (mitt centre, sleeve extent, stature), so it follows the SHAPE dials of the body it is built for.

  key_staff       slung across the back (bone spine): shaft from outside the right thigh to above the left
                  shoulder, ring bow on top, two teeth near the low end
  launcher_case   long case under the right hand: grip bar through the mitt, two posts, muzzle at the front end,
                  one band
  ring_buckler    open ring on the outside of the left forearm, on a boss sunk in the sleeve and one spoke

Texture: 16 x 16, four flat quadrants (main, dark / accent, light); colours are palette names of the pack.

form (bind gates): 'box' builds the pieces as authored. 'faceted' builds every box piece as an octagonal prism
along its longest axis whose two largest faces bevel toward their long edges at FACET['draft'] degrees, the bevels
covering FACET['share'] of the piece's area (the house cuboid gate counts a piece as a box when >= 90 % of its area
lies within 4 degrees of three orthogonal axes). Position, size and every other piece are unchanged.
"""
import math

import numpy as np

from . import paint as P0
from . import people as PP

TAU = 2. * math.pi
KINDS = ('key_staff', 'launcher_case', 'ring_buckler')
FORMS = ('box', 'faceted')
# degrees from the face; bevel area share; bevel width <= .9 x half. The smallest bevel the cuboid gate passes with a
# margin: 5 deg (gate 4 deg), 12 % of the area (axis share 0.879, gate 0.90).
FACET = {'draft': 5., 'share': .12, 'max_w': .9}
QUAD = {'main': (.25, .75), 'dark': (.75, .75), 'accent': (.25, .25), 'light': (.75, .25)}
DEFAULT_COLORS = {'main': 'grey_0', 'dark': 'k_1', 'accent': 'red', 'light': 'off_white'}


class PropError(ValueError):
    pass


class _B:
    def __init__(self, form='box'):
        self.V = []; self.F = []; self.UV = []
        self.form = form

    def solid(self, pts, faces, q):
        """Convex chunk: every face is wound to point away from the centroid of its points."""
        base = len(self.V)
        self.V += [tuple(float(c) for c in p) for p in pts]
        cen = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
        cu, cv = QUAD[q]
        uv = [(cu - .08, cv - .08), (cu + .08, cv - .08), (cu, cv + .08)]
        for f in faces:
            a, b, c = (pts[i] for i in f)
            n = PP._cross(PP._sub(b, a), PP._sub(c, a))
            fc = PP._mul(PP._add(PP._add(a, b), c), 1. / 3)
            if PP._dot(n, PP._sub(fc, cen)) < 0:
                f = (f[0], f[2], f[1])
            self.F.append(tuple(base + i for i in f)); self.UV.append(list(uv))

    def box(self, c, h, q):
        if self.form == 'faceted':
            return self.faceted(c, h, q)
        pts = [(c[0] + sx * h[0], c[1] + sy * h[1], c[2] + sz * h[2]) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
        quads = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
        self.solid(pts, [t for a, b, c2, d in quads for t in ((a, b, c2), (a, c2, d))], q)

    def faceted(self, c, h, q):
        """The box (centre c, half extents h) as an octagonal prism along its longest axis L: the two faces spanned
        by L and the middle axis A bevel over a width w next to their long edges, dropping w tan(draft) toward the
        short axis B. w makes the bevels FACET['share'] of the box area. 16 points, 28 triangles."""
        L, A, S = sorted(range(3), key=lambda k: (-h[k], k))
        hl, u, v = h[L], h[A], h[S]
        t = math.tan(math.radians(FACET['draft']))
        total = 8. * (hl * u + hl * v + u * v)
        w = min(FACET['max_w'] * u, FACET['share'] * total / (8. * hl * math.sqrt(1. + t * t)))
        d = w * t
        sec = [(u - w, v), (u, v - d), (u, d - v), (u - w, -v), (w - u, -v), (-u, d - v), (-u, v - d), (w - u, v)]

        def pt(a, b, l):
            p = [0., 0., 0.]
            p[A] = c[A] + a; p[S] = c[S] + b; p[L] = c[L] + l
            return tuple(p)
        pts = [pt(a, b, -hl) for a, b in sec] + [pt(a, b, hl) for a, b in sec]
        faces = []
        for i in range(8):
            j = (i + 1) % 8
            faces += [(i, j, 8 + j), (i, 8 + j, 8 + i)]
        for k in range(1, 7):                               # caps: fans from corner 0 (convex octagons)
            faces += [(0, k, k + 1), (8, 8 + k, 9 + k)]
        self.solid(pts, faces, q)

    def prism(self, p0, p1, r, n, q, e1, e2):
        """n-sided prism from p0 to p1 (caps as fans around their centres); e1, e2 span the section."""
        ring = lambda p: [tuple(p[k] + r * (math.cos(TAU * i / n) * e1[k] + math.sin(TAU * i / n) * e2[k]) for k in range(3)) for i in range(n)]
        pts = ring(p0) + ring(p1) + [tuple(p0), tuple(p1)]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces += [(i, j, n + j), (i, n + j, n + i), (2 * n, i, j), (2 * n + 1, n + i, n + j)]
        self.solid(pts, faces, q)

    def ring(self, c, e1, e2, en, R, w, t, n, q, segs=None):
        """Ring of n box segments in the plane (e1, e2), normal en: radius R, radial half width w, half thickness
        t. segs: the segment indices to build (an open ring gets end caps)."""
        segs = list(range(n)) if segs is None else list(segs)

        def corner(i, dr, dn):
            a = TAU * i / n
            return tuple(c[k] + (R + dr) * (math.cos(a) * e1[k] + math.sin(a) * e2[k]) + dn * en[k] for k in range(3))
        for i in segs:
            pts = [corner(i + s, dr, dn) for s in (0, 1) for dr, dn in ((-w, -t), (w, -t), (w, t), (-w, t))]
            faces = []
            for k in range(4):
                k1 = (k + 1) % 4
                faces += [(k, k1, 4 + k1), (k, 4 + k1, 4 + k)]
            if (i - 1) % n not in segs:
                faces += [(0, 1, 2), (0, 2, 3)]
            if (i + 1) % n not in segs:
                faces += [(4, 5, 6), (4, 6, 7)]
            self.solid(pts, faces, q)


def _centre(m, part):
    P = [m.vertices[vi] for vi in m.parts[part]]
    return tuple(sum(p[k] for p in P) / len(P) for k in range(3))


X, Y, Z = (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)


STAFF = {'low': (-.19, .22), 'high': (.15, .98), 'r': .011, 'bow': .070, 'clear': .008, 'teeth': (.10, .19), 'tooth': .060}


def _key_staff(b, m, H):
    """Slung across the back (slot back, bone spine): a hand-held staff needs a holding pose, which the family's
    clips do not have; the hanging hand turns up to 105 degrees in them."""
    g = STAFF
    yb = max(v[1] for v in m.vertices) + (g['r'] + g['clear']) * H             # plane behind the back, hair and coat
    lo = (g['low'][0] * H, yb, g['low'][1] * H); hi = (g['high'][0] * H, yb, g['high'][1] * H)
    L = math.hypot(hi[0] - lo[0], hi[2] - lo[2])
    ax = ((hi[0] - lo[0]) / L, 0., (hi[2] - lo[2]) / L)
    out = (-ax[2], 0., ax[0])                                                  # in the plane, toward the low end's side
    b.prism(lo, hi, g['r'] * H, 6, 'main', out, Y)
    R = g['bow'] * H
    b.ring(tuple(hi[k] + ax[k] * (R - .012 * H) for k in range(3)), X, Z, Y, R, .015 * H, .010 * H, 8, 'accent')
    for t in g['teeth']:                                                       # two teeth near the low end
        p0 = tuple(lo[k] + ax[k] * t * L for k in range(3))
        p1 = tuple(p0[k] - out[k] * g['tooth'] * H for k in range(3))
        b.prism(p0, p1, .016 * H, 4, 'accent', ax, (0., .55, 0.))
    return 'back', 'spine'


CASE = {'half': (.030, .150, .070), 'out': .018, 'fore': .035, 'drop': .030}


def _launcher_case(b, m, H):
    """Carried by a grip bar through the mitt; the case hangs `drop` under the mitt, `out` further from the body
    than the hand and `fore` ahead of it, so that it clears the thigh."""
    g = CASE
    mx, my, mz = _centre(m, 'mitt_r')
    zb = min(m.vertices[vi][2] for vi in m.parts['mitt_r'])
    hx, hy, hz = (c * H for c in g['half'])
    zg = zb + .012 * H                                  # grip bar: through the lower half of the mitt, front to back
    top = zb - g['drop'] * H                            # top face of the case
    cx, cy, cz = mx - g['out'] * H, my - g['fore'] * H, top - hz
    b.box((mx, my, zg), (.006 * H, .052 * H, .006 * H), 'dark')
    for sy in (-1, 1):                                  # two posts from the bar's ends to the case
        b.box((mx, my + sy * .046 * H, .5 * (zg + top)), (.005 * H, .006 * H, .5 * (zg - top) + .004 * H), 'dark')
    b.box((cx, cy, cz), (hx, hy, hz), 'main')                                          # case
    b.box((cx, cy - .25 * hy, cz), (hx * 1.06, .016 * H, hz * 1.04), 'accent')         # band
    b.prism((cx, cy - hy - .045 * H, cz + .2 * hz), (cx, cy - hy + .005 * H, cz + .2 * hz), .034 * H, 6, 'dark', X, Z)   # muzzle
    return 'hand_r', 'hand_r'


def _sleeve_outer_x(m, part, z):
    """Outermost x of a sleeve at height z, between its rings (6 vertices each)."""
    ids = m.parts[part]
    rings = sorted((sum(m.vertices[v][2] for v in ids[k:k + 6]) / 6., max(m.vertices[v][0] for v in ids[k:k + 6]))
                   for k in range(0, len(ids), 6))
    for (z0, x0), (z1, x1) in zip(rings, rings[1:]):
        if z0 <= z <= z1:
            return x0 + (x1 - x0) * (z - z0) / (z1 - z0)
    return rings[0][1] if z < rings[0][0] else rings[-1][1]


def _ring_buckler(b, m, H):
    f, h = m.bones['forearm_l'], m.bones['hand_l']
    cz = .5 * (f[2] + h[2]); cy = .5 * (f[1] + h[1])
    arm_x = _sleeve_outer_x(m, 'sleeve_l', cz)
    cx = arm_x + .024 * H                               # ring plane: .014 H clear of the sleeve
    b.ring((cx, cy, cz), Y, Z, X, .082 * H, .017 * H, .010 * H, 8, 'accent', segs=range(1, 8))
    b.box((arm_x + .004 * H, cy, cz), (.016 * H, .022 * H, .022 * H), 'main')           # boss: .012 H into the sleeve
    b.box((cx - .004 * H, cy, cz), (.005 * H, .082 * H, .009 * H), 'dark')              # spoke
    return 'forearm_l', 'forearm_l'


_BUILD = {'key_staff': _key_staff, 'launcher_case': _launcher_case, 'ring_buckler': _ring_buckler}


def texture(pack, colors):
    cols = dict(DEFAULT_COLORS); cols.update(colors or {})
    img = np.zeros((16, 16, 3), dtype=np.uint8)
    for q, (u, v) in QUAD.items():
        if q not in cols:
            raise PropError('prop colour %r missing' % q)
        x0 = 0 if u < .5 else 8; y0 = 0 if v > .5 else 8          # image row 0 = v 1
        img[y0:y0 + 8, x0:x0 + 8] = np.asarray(P0.color(pack, cols[q]), dtype=np.uint8)
    unknown = set(cols) - set(QUAD)
    if unknown:
        raise PropError('unknown prop colours %s' % sorted(unknown))
    return img


def build(kind, m, colors, pack, form='box'):
    if kind not in _BUILD:
        raise PropError('prop kind is one of %s, not %r' % (KINDS, kind))
    if form not in FORMS:
        raise PropError('prop form is one of %s, not %r' % (FORMS, form))
    b = _B(form)
    slot, bone = _BUILD[kind](b, m, m.params['height'])
    return {'kind': kind, 'slot': slot, 'bone': bone, 'vertices': b.V, 'faces': b.F, 'uv': b.UV,
            'texture': texture(pack, colors)}
