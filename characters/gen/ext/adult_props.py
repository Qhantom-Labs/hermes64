"""Removable props of the n64_adult family (lane CHARS3). A prop is a rigid mesh on one bone with its own small texture;
the body under it is complete (a visor never replaces the painted face). build(kind, a, recipe) returns
{'slot', 'bone', 'vertices', 'faces', 'uv', 'texture'} in body space (Z up, the character faces -Y).

Props fit the body they are built for: the visor is laid on the measured outline of that head, so a wider or
longer head gets a wider or longer visor without a per-character number."""
import math

import numpy as np

KINDS = ('visor',)


def _hex(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _slice(a, verts, z):
    """Points where the triangles made only of `verts` cross the height z."""
    out = []
    for f in a.faces:
        if not all(i in verts for i in f):
            continue
        for i, j in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            p, q = a.vertices[i], a.vertices[j]
            if (p[2] - z) * (q[2] - z) < 0.:
                t = (z - p[2]) / (q[2] - p[2])
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _support(pts, c, th):
    """Distance from c to the outline of pts along the direction th (0 = front, + = the character's left)."""
    dx, dy = math.sin(th), -math.cos(th)
    return max((x - c[0]) * dx + (y - c[1]) * dy for x, y in pts)


class _Prop:
    def __init__(self):
        self.vertices, self.faces, self.uv = [], [], []

    def v(self, p):
        self.vertices.append(tuple(float(x) for x in p))
        return len(self.vertices) - 1

    def tri(self, i, j, k, uv, out):
        """A triangle wound so its normal points along `out`."""
        p, q, r = (np.asarray(self.vertices[n]) for n in (i, j, k))
        if float(np.dot(np.cross(q - p, r - p), np.asarray(out))) < 0.:
            j, k = k, j
            uv = (uv[0], uv[2], uv[1])
        self.faces.append((i, j, k))
        self.uv.append(tuple(uv))

    def quad(self, i, j, k, l, uv, out):
        self.tri(i, j, k, (uv[0], uv[1], uv[2]), out)
        self.tri(i, k, l, (uv[0], uv[2], uv[3]), out)

    def box(self, c, h, uv, skip=()):
        x, y, z = c
        hx, hy, hz = h
        I = [self.v((x + sx * hx, y + sy * hy, z + sz * hz)) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
        sides = {'-x': ((0, 2, 6, 4), (-1, 0, 0)), '+x': ((1, 3, 7, 5), (1, 0, 0)), '-y': ((0, 1, 5, 4), (0, -1, 0)),
                 '+y': ((2, 3, 7, 6), (0, 1, 0)), '-z': ((0, 1, 3, 2), (0, 0, -1)), '+z': ((4, 5, 7, 6), (0, 0, 1))}
        for name in sorted(sides):
            if name in skip:
                continue
            q, n = sides[name]
            self.quad(I[q[0]], I[q[1]], I[q[2]], I[q[3]], (uv, uv, uv, uv), n)


def visor_texture(recipe):
    """32x16, row 0 at the top: rows 0..11 are the front of the visor (a frame-colour border two texels wide around
    a pale lens with a lighter upper band), rows 12..15 the plain frame colour for the edges and temple blocks."""
    C = recipe.get('colors', {})
    frame = _hex(C.get('visor', '#d8343a'))
    lens = _hex(C.get('visor_lens', '#f4f6f2'))
    t = np.zeros((16, 32, 3), dtype=np.uint8)
    t[:, :] = frame
    t[3:9, 2:30] = tuple(int(c * .91) for c in lens)
    t[3:6, 2:30] = lens
    return t


def visor(a, recipe):
    """A wrap-around visor over the eyes: a faceted band from temple to temple with two temple blocks."""
    H = a.params['height']
    D_hh = a.params['head'] * H
    skull = set(a.parts['face']) | set(a.parts.get('nose', []))
    head = a.bones['head']
    z0 = H - D_hh                                   # chin
    lo, hi = z0 + .385 * D_hh, z0 + .615 * D_hh
    S = {z: _slice(a, skull, z) for z in (lo, hi)}
    cx = 0.
    cy = sum(y for z in S for _, y in S[z]) / max(1, sum(len(S[z]) for z in S))
    c = (cx, cy)
    gap, thick = .002 * H, .010 * H
    m = _Prop()
    cols = [-94., -70., -40., 0., 40., 70., 94.]
    ring = []
    for deg in cols:
        th = math.radians(deg)
        d = (math.sin(th), -math.cos(th))
        row = []
        for z in (lo, hi):
            r = _support(S[z], c, th) + gap
            row.append((m.v((c[0] + d[0] * r, c[1] + d[1] * r, z)),
                        m.v((c[0] + d[0] * (r + thick), c[1] + d[1] * (r + thick), z))))
        ring.append((row, d))
    n = len(cols)
    FR = (.5, .12)                                  # a texel of the frame colour
    for i in range(n - 1):
        (r0, d0), (r1, d1) = ring[i], ring[i + 1]
        out = (d0[0] + d1[0], d0[1] + d1[1], 0.)
        u0, u1 = .02 + .96 * i / (n - 1), .02 + .96 * (i + 1) / (n - 1)
        m.quad(r0[0][1], r1[0][1], r1[1][1], r0[1][1], ((u0, .27), (u1, .27), (u1, .98), (u0, .98)), out)   # lens
        m.quad(r0[1][0], r1[1][0], r1[1][1], r0[1][1], (FR, FR, FR, FR), (0., 0., 1.))                      # top edge
        m.quad(r0[0][0], r1[0][0], r1[0][1], r0[0][1], (FR, FR, FR, FR), (0., 0., -1.))                     # bottom edge
    for (row, d), sg in ((ring[0], -1.), (ring[-1], 1.)):                                                   # ends
        m.quad(row[0][0], row[0][1], row[1][1], row[1][0], (FR, FR, FR, FR), (-d[1] * -sg, d[0] * -sg, 0.))
    for row, d in (ring[0], ring[-1]):              # temple blocks, sunk into the band so nothing floats
        p = np.asarray(m.vertices[row[0][1]]) * .5 + np.asarray(m.vertices[row[1][1]]) * .5
        m.box((p[0] - d[0] * thick * .5, p[1] - d[1] * thick * .5 + .024 * H, p[2]),
              (.005 * H, .030 * H, .30 * (hi - lo)), FR)
    return {'slot': 'head', 'bone': 'head', 'vertices': m.vertices, 'faces': m.faces, 'uv': m.uv,
            'texture': visor_texture(recipe)}


def build(kind, a, recipe):
    if kind == 'visor':
        return visor(a, recipe)
    raise KeyError('unknown prop kind %r (known: %s)' % (kind, ', '.join(KINDS)))
