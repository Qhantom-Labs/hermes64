"""Headphones of nous_girl (lane CAST2): a separate prop mesh on the head bone, never part of the body mesh.

build(H) -> Prop with vertices in character space (metres, rest pose; front = -y, z up), faces, per-corner uv.
A headband (rectangular section, BAND_SEG segments) over the bob from ear to ear, a yoke block at each end, and at
each ear a six-sided cup with a smaller six-sided face plate. Built as her right half and mirrored: left-right
symmetric by construction. The texture is three plain tones and one ring; no mark, letter or logo.
All numbers x H unless named otherwise.
"""
import math

import numpy as np

from . import paint as P0
from . import people_paint as PPP

KIND = 'headphones'
SLOT = 'head'
BUDGET = 200
BAND_Y = .005                 # centre of the band, fore-aft (the bob's centre)
BAND_W = .017                 # fore-aft width
BAND_T = .007                 # thickness
# centre line of the band, her LEFT half from the top down to the cup: (x, z)
# (the stations sit on the bob's side profile at y = BAND_Y, 1.5 to 2 thousandths of H clear of it)
BAND = [(0., 1.0090), (.0325, .9950), (.0600, .9680), (.0710, .9220), (.0765, .8980)]
CUP = {'x0': .0725, 'x1': .0870, 'y': .004, 'z': .872, 'r': .031}        # inner x, outer x, centre, hex radius
PLATE = {'x1': .0930, 'r': .021}
YOKE = {'x0': .0770, 'x1': .0850, 'hy': .0075, 'z0': .894, 'z1': .910}
UV = {'band': (.05, .55, .95, .95), 'cup': (.05, .05, .45, .45), 'plate': (.55, .05, .95, .45)}


class Prop:
    def __init__(self):
        self.vertices = []; self.faces = []; self.uv = []; self.slot = SLOT; self.kind = KIND; self.parts = {}

    def v(self, part, p):
        self.vertices.append((float(p[0]), float(p[1]), float(p[2])))
        self.parts.setdefault(part, []).append(len(self.vertices) - 1)
        return len(self.vertices) - 1

    def tri(self, a, b, c, ua, ub, uc):
        self.faces.append((a, b, c)); self.uv.append([ua, ub, uc])

    def quad(self, a, b, c, d, ua, ub, uc, ud):
        self.tri(a, b, c, ua, ub, uc); self.tri(a, c, d, ua, uc, ud)


def _box(r):
    return lambda s, t: (r[0] + (r[2] - r[0]) * s, r[1] + (r[3] - r[1]) * t)


def build(H):
    m = Prop()
    # ---- band: full arc, stations from her right cup over the top to her left cup
    line = [(-x, z) for x, z in reversed(BAND[1:])] + list(BAND)
    n = len(line)
    sec = []
    for i, (x, z) in enumerate(line):
        a = line[max(0, i - 1)]; b = line[min(n - 1, i + 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, tz)
        nx, nz = -tz / L, tx / L                      # outward normal (up at the top)
        if nx * x + nz * (z - CUP['z']) < 0:          # away from the head
            nx, nz = -nx, -nz
        h = BAND_T / 2.; w = BAND_W / 2.
        ring = [(x + nx * h, BAND_Y - w, z + nz * h), (x + nx * h, BAND_Y + w, z + nz * h),
                (x - nx * h, BAND_Y + w, z - nz * h), (x - nx * h, BAND_Y - w, z - nz * h)]
        sec.append([m.v('band', (p[0] * H, p[1] * H, p[2] * H)) for p in ring])
    uvb = _box(UV['band'])
    for i in range(n - 1):
        for k in range(4):
            k1 = (k + 1) % 4
            a, b, c, d = sec[i][k], sec[i + 1][k], sec[i + 1][k1], sec[i][k1]
            s0, s1 = i / float(n - 1), (i + 1) / float(n - 1)
            m.quad(a, b, c, d, uvb(s0, k / 4.), uvb(s1, k / 4.), uvb(s1, (k + 1) / 4.), uvb(s0, (k + 1) / 4.))
    for s in (-1, 1):
        def P(x, y, z, part):
            return m.v(part, (s * x * H, y * H, z * H))

        def flip(a, b, c, ua, ub, uc):
            if s > 0:
                m.tri(a, b, c, ua, ub, uc)
            else:
                m.tri(a, c, b, ua, uc, ub)

        def prism(part, x0, x1, r, uvr, cy, cz):
            uvf = _box(uvr)
            inner = []; outer = []; cap = []
            for j in range(6):
                f = math.tau * j / 6.
                y = cy + r * math.cos(f); z = cz + r * math.sin(f)
                inner.append(P(x0, y, z, part)); outer.append(P(x1, y, z, part)); cap.append(P(x1, y, z, part))
            c0 = P(x1, cy, cz, part)
            for j in range(6):
                j1 = (j + 1) % 6
                f0 = math.tau * j / 6.; f1 = math.tau * j1 / 6.
                # wall (outward = away from the prism axis), then the outer cap fan (outward = +x for her left)
                flip(inner[j], inner[j1], outer[j1], uvf(.02, .5), uvf(.02, .5), uvf(.10, .5))
                flip(inner[j], outer[j1], outer[j], uvf(.02, .5), uvf(.10, .5), uvf(.10, .5))
                flip(c0, cap[j], cap[j1], uvf(.5, .5), uvf(.5 + .5 * math.cos(f0), .5 + .5 * math.sin(f0)),
                     uvf(.5 + .5 * math.cos(f1), .5 + .5 * math.sin(f1)))
        prism('cup', CUP['x0'], CUP['x1'], CUP['r'], UV['cup'], CUP['y'], CUP['z'])
        prism('plate', CUP['x1'], PLATE['x1'], PLATE['r'], UV['plate'], CUP['y'], CUP['z'])
        # yoke: a block between the band end and the cup (4 walls + top)
        y0, y1 = CUP['y'] - YOKE['hy'], CUP['y'] + YOKE['hy']
        lo = [P(YOKE['x0'], y0, YOKE['z0'], 'yoke'), P(YOKE['x1'], y0, YOKE['z0'], 'yoke'),
              P(YOKE['x1'], y1, YOKE['z0'], 'yoke'), P(YOKE['x0'], y1, YOKE['z0'], 'yoke')]
        up = [P(YOKE['x0'], y0, YOKE['z1'], 'yoke'), P(YOKE['x1'], y0, YOKE['z1'], 'yoke'),
              P(YOKE['x1'], y1, YOKE['z1'], 'yoke'), P(YOKE['x0'], y1, YOKE['z1'], 'yoke')]
        t = uvb(.5, .5)
        for k in range(4):
            k1 = (k + 1) % 4
            flip(lo[k], lo[k1], up[k1], t, t, t); flip(lo[k], up[k1], up[k], t, t, t)
        flip(up[0], up[1], up[2], t, t, t); flip(up[0], up[2], up[3], t, t, t)
    return m


def symmetry_mm(m):
    P = m.vertices
    worst = 0.
    for (x, y, z) in P:
        worst = max(worst, min((x + q[0]) ** 2 + (y - q[1]) ** 2 + (z - q[2]) ** 2 for q in P))
    return round(math.sqrt(worst) * 1000., 3)


def texture(pack):
    """32 x 32: band tone on the top half; cup (dark) bottom left; face plate (dark, one lighter ring) bottom right."""
    T = PPP.Tones(pack)
    pc = pack['prop_colors']
    c = PPP.Canvas(T, 32, 32, pc['body'])
    u, v = c.u, c.v
    c.put((v > .5) & (v < .62), pc['body'], -1)                     # underside of the band
    c.put(v < .5, pc['dark'])
    c.put((v < .5) & (u < .5) & (u > .40), pc['dark'], 1)
    r = np.sqrt(((u - .75) / .20) ** 2 + ((v - .25) / .20) ** 2)
    c.put((v < .5) & (u > .5) & (r > .52) & (r < .80), pc['metal'])   # ring on the face plate
    return P0.quantize(c.img, P0.palette(pack))
