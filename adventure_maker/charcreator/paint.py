"""Creator atlas painter (numpy + Pillow): one 64x64 texture with baked light, in the card's art style.

Each part owns a rectangle of the atlas (LAYOUT). Triangles are rasterised in atlas space; every covered texel gets
the interpolated surface normal, height and part-local (u, v). Its base colour comes from the part's region rules
(outfit, belt, cuffs, boots, hat band, cape lining ...); the light is baked from a key, a fill and an ambient term
plus a small gloss highlight; seeded blotchy jitter (70% 2x2-texel blotches) picks between the base colour's 4 ramp
levels, and island border texels sit 0.7 level lighter, as the card measured (no ordered
dither, no border darkening: the card measured neither). The atlas is then reduced to the card's colour count.
Mirrored parts (both arms, legs, hands, boots, ears) share their rectangle; the left side paints it.
"""
import hashlib
import io
import math

import numpy as np

ATLAS = 64
LAYOUT = {
    'head': (0, 0, 28, 18), 'hair': (28, 0, 20, 10), 'beard': (48, 0, 8, 10), 'muzzle': (56, 0, 8, 6), 'ears': (58, 6, 6, 6),
    'torso': (0, 18, 16, 12), 'arm': (16, 18, 6, 12), 'hand': (22, 18, 5, 5), 'horns': (22, 24, 6, 6),
    'leg': (0, 30, 8, 16), 'boot': (8, 30, 10, 8), 'tail': (18, 30, 6, 10),
    'hat': (28, 10, 16, 16), 'cape': (44, 10, 14, 14), 'pack': (28, 26, 10, 10), 'held': (38, 26, 10, 10),
}
SHARED = {'arm', 'hand', 'leg', 'boot', 'ears'}
GLOSS = {'cloth': .15, 'metal': .6, 'hair': .38, 'skin': .12, 'fur': .16, 'eye': .5}
KEY = np.array([.38, .78, .5]) / np.linalg.norm([.38, .78, .5])
FILL = np.array([-.55, .15, .62]) / np.linalg.norm([-.55, .15, .62])
HALF = (KEY + np.array([0., 0., 1.])) / np.linalg.norm(KEY + np.array([0., 0., 1.]))


from . import ramp, master_palette  # noqa: E402,F401  (stdlib ramps: the palette gate uses the same list)


JITTER = 2.5                         # peak-to-peak ramp-level jitter per texel (the card's texel noise)
BLOCK = .7                          # share of the jitter that is 2x2-texel blotches (the card's noise is blotchy, not checkered)
RIM = .7                            # ramp levels added on island border texels (the card's borders are lighter)


def _noise(seed, n):
    h = hashlib.sha256(('creator-noise|%s' % seed).encode()).digest()
    rng = np.random.default_rng(int.from_bytes(h[:8], 'little'))
    return rng.random(n)


def _bary_raster(tri_px, W, H):
    """Yield (ys, xs, l0, l1, l2) for texel centres inside a triangle given in pixel space."""
    (x0, y0), (x1, y1), (x2, y2) = tri_px
    xa, xb = int(max(0, math.floor(min(x0, x1, x2)))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
    ya, yb = int(max(0, math.floor(min(y0, y1, y2)))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
    if xb < xa or yb < ya:
        return None
    ys, xs = np.mgrid[ya:yb + 1, xa:xb + 1]
    px, py = xs + .5, ys + .5
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(d) < 1e-12:
        return None
    l0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / d
    l1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / d
    l2 = 1 - l0 - l1
    eps = -1e-6
    m = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
    if not m.any():
        return None
    return ys[m], xs[m], l0[m], l1[m], l2[m]


def atlas_uv(part, uv):
    x, y, w, h = LAYOUT[part]
    u, v = uv
    # keep corners half a texel inside the rectangle so bilinear filtering never reaches a neighbour
    u = min(max(u, 0.), 1.)
    v = min(max(v, 0.), 1.)
    px = x + .5 + u * (w - 1.)
    py = y + .5 + v * (h - 1.)
    return px / ATLAS, py / ATLAS


class Painter:
    def __init__(self, params, data):
        self.p, self.d = params, data
        self.cols = params['colours']
        self.mods = set(params['modules'])
        self.kinds = {data['modules'][m]['kind']: m for m in params['modules']}
        self.slot = np.full((ATLAS, ATLAS), -1, np.int32)        # index into self.names
        self.shade = np.zeros((ATLAS, ATLAS))
        self.gloss = np.zeros((ATLAS, ATLAS))
        self.names = []                                           # palette colour names in slot order
        self.part = np.full((ATLAS, ATLAS), '', object)

    def _idx(self, slotname):
        name = self.cols[slotname]
        if name not in self.names:
            self.names.append(name)
        return self.names.index(name)

    # ------------------------------------------------------------ region rules: (part, u, v, normal, y) -> slot
    def region(self, part, u, v, n, ylocal):
        k = self.kinds
        outfit = k.get('outfit', 'outfit.tunic')
        if part == 'head':
            return 'skin'
        if part in ('hair', 'beard'):
            return 'hair'
        if part in ('ears', 'tail', 'muzzle'):
            return 'skin'
        if part == 'horns':
            return 'eyes' if (k.get('horns') == 'horns.antenna' and v < .25) else ('extra' if k.get('horns') == 'horns.antenna' else 'top2')
        if part == 'hand':
            return 'gloves' if 'gloves' in k else 'skin'
        if part == 'arm':
            if 'gloves' in k and v > .9:
                return 'gloves'
            if outfit == 'outfit.panels':
                return 'extra' if abs(v - .45) < .06 else 'top'
            if v > .88:
                return 'top2' if outfit in ('outfit.jacket', 'outfit.robe') else 'top'
            return 'top'
        if part == 'torso':
            front = abs(u - .5) < .17
            if 'belt' in k and .8 <= v <= .9:
                if k['belt'] == 'belt.buckle' and abs(u - .5) < .045:
                    return 'hat2' if 'hat' in k else 'top2'
                return 'belt'
            if 'scarf' in k and v < .16:
                return 'top2'
            if outfit == 'outfit.jacket':
                if abs(u - .5) < .055 and v > .1:
                    return 'top2'
                if v < .16 and front:
                    return 'top2'
                return 'top'
            if outfit == 'outfit.robe':
                if abs(u - .5) < .03 and v > .14:
                    return 'top2'
                return 'top'
            if outfit == 'outfit.apron':
                return 'top2' if (abs(u - .5) < .12 and v > .3) else 'top'
            if outfit == 'outfit.overalls':
                if v > .62 or (abs(u - .5) < .1 and v > .25):
                    return 'legs'
                return 'top'
            if outfit == 'outfit.armor':
                return 'extra' if abs(v - .42) < .035 or abs(v - .66) < .035 else 'top'
            if outfit == 'outfit.panels':
                if abs(v - .5) < .04 or abs(u - .5) < .02:
                    return 'extra'
                if abs(u - .5) < .07 and abs(v - .32) < .07:
                    return 'eyes'
                return 'top'
            return 'top2' if v < .1 else 'top'
        if part == 'leg':
            if v > .8:
                return 'boots'
            if outfit == 'outfit.robe' and v < .6:
                return 'top2' if v > .53 else 'top'
            if outfit == 'outfit.panels' and abs(v - .5) < .05:
                return 'extra'
            return 'legs'
        if part == 'boot':
            return 'boots'
        if part == 'hat':
            if v > .82 and k.get('hat') not in ('hat.crown', 'hat.hood'):
                return 'hat2'
            return 'hat'
        if part == 'cape':
            return 'cape2' if (u > .5 or v > .93) else 'cape'
        if part == 'pack':
            return 'extra' if v < .25 else 'pack'
        if part == 'held':
            item = k.get('held', '')
            if item == 'held.staff' and v < .45:
                return 'eyes'
            if item == 'held.lantern' and .3 < v < .7:
                return 'eyes'
            if item == 'held.book' and abs(n[0]) < .5:
                return 'top2'
            return 'held'
        return 'top'

    def family(self, name):
        return self.d['palette'][name]['family']

    # ------------------------------------------------------------ raster
    def paint_faces(self, faces):
        """faces: list of (part, side, [(u,v)]*3, [pos]*3, [normal]*3, height)."""
        for part, side, uvs, pos, nrm, height in faces:
            if part in SHARED and side == 'r':
                continue
            x, y, w, h = LAYOUT[part]
            px = [(x + .5 + min(max(u, 0), 1) * (w - 1), y + .5 + min(max(v, 0), 1) * (h - 1)) for u, v in uvs]
            r = _bary_raster(px, ATLAS, ATLAS)
            if r is None:
                continue
            ys, xs, l0, l1, l2 = r
            P = np.outer(l0, pos[0]) + np.outer(l1, pos[1]) + np.outer(l2, pos[2])
            N = np.outer(l0, nrm[0]) + np.outer(l1, nrm[1]) + np.outer(l2, nrm[2])
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            U = l0 * uvs[0][0] + l1 * uvs[1][0] + l2 * uvs[2][0]
            V = l0 * uvs[0][1] + l1 * uvs[1][1] + l2 * uvs[2][1]
            for i in range(len(ys)):
                sl = self.region(part, U[i], V[i], N[i], P[i][1] / height)
                idx = self._idx(sl)
                fam = self.family(self.names[idx])
                n = N[i]
                diff = max(0., float(n @ KEY))
                fill = max(0., float(n @ FILL))
                up = .5 + .5 * float(n[1])
                s = .38 + .52 * diff + .14 * fill + .12 * up
                if part == 'cape' and U[i] > .5:
                    s *= .78                                     # the lining faces the body: in shadow
                g = GLOSS.get(fam, .2) * max(0., float(n @ HALF)) ** 10
                self.slot[ys[i], xs[i]] = idx
                self.shade[ys[i], xs[i]] = s
                self.gloss[ys[i], xs[i]] = g
                self.part[ys[i], xs[i]] = part

    def dilate(self, passes=2):
        """Copy covered texels into uncovered neighbours inside each rectangle (bilinear filtering bleeds)."""
        for _ in range(passes):
            s, sh, gl = self.slot.copy(), self.shade.copy(), self.gloss.copy()
            for part, (x, y, w, h) in LAYOUT.items():
                for yy in range(y, y + h):
                    for xx in range(x, x + w):
                        if self.slot[yy, xx] >= 0:
                            continue
                        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                            ny, nx = yy + dy, xx + dx
                            if y <= ny < y + h and x <= nx < x + w and self.slot[ny, nx] >= 0:
                                s[yy, xx], sh[yy, xx], gl[yy, xx] = self.slot[ny, nx], self.shade[ny, nx], self.gloss[ny, nx]
                                break
            self.slot, self.shade, self.gloss = s, sh, gl

    # ------------------------------------------------------------ face and painted modules (texel space)
    def _set(self, part, u, v, slotname, level):
        x, y, w, h = LAYOUT[part]
        xx = int(round(x + u * (w - 1)))
        yy = int(round(y + v * (h - 1)))
        if x <= xx < x + w and y <= yy < y + h:
            self.slot[yy, xx] = self._idx(slotname)
            self.shade[yy, xx] = {'dark': .3, 'mid': .7, 'base': 1., 'hi': 1.6}[level]
            self.gloss[yy, xx] = 0.

    def face(self):
        f = self.p['face']
        style, mouth = f.get('style', 'round'), f.get('mouth', 'line')
        x, y, w, h = LAYOUT['head']
        du = 1. / (w - 1)
        ey, my, by = .46, .7, .37
        el, er = .5 + 2.2 * du, .5 - 2.2 * du
        if style == 'visor':
            for i in range(-4, 5):
                for dv in (-.03, .03):
                    self._set('head', .5 + i * du, ey + dv, 'eyes', 'hi' if abs(i) < 3 else 'base')
        elif style == 'button':
            for c in (el, er):
                self._set('head', c, ey, 'eyes', 'hi')
        elif style != 'none':
            for c in (el, er):
                if style == 'dot':
                    self._set('head', c, ey, 'eyes', 'dark')
                elif style == 'sleepy':
                    self._set('head', c - du * .5, ey + .02, 'eyes', 'dark')
                    self._set('head', c + du * .5, ey + .02, 'eyes', 'dark')
                elif style == 'round':
                    self._set('head', c, ey, 'eyes', 'dark')
                    self._set('head', c, ey + 1. / (h - 1), 'eyes', 'mid')
                    self._set('head', c + (du if c > .5 else -du) * .9, ey, 'eyes', 'hi')
                elif style == 'anime':
                    self._set('head', c, ey - 1. / (h - 1), 'eyes', 'dark')
                    self._set('head', c, ey, 'eyes', 'mid')
                    self._set('head', c, ey + 1. / (h - 1), 'eyes', 'base')
                    self._set('head', c + (du if c > .5 else -du) * .9, ey - 1. / (h - 1), 'eyes', 'hi')
                if self.p['skin_kind'] != 'metal':
                    self._set('head', c, by, 'hair', 'dark')                   # brow
        if self.p['skin_kind'] != 'metal' and style not in ('none',):
            self._set('head', .5, (ey + my) / 2. + .02, 'skin', 'mid')       # nose shadow
        if mouth != 'none':
            pts = {'line': [(-1, 0), (0, 0), (1, 0)], 'smile': [(-1, -1), (0, 0), (1, -1)], 'frown': [(-1, 1), (0, 0), (1, 1)],
                   'open': [(0, 0), (0, 1)]}[mouth]
            for di, dj in pts:
                self._set('head', .5 + di * du, my + dj * .5 / (h - 1) * 2, 'skin', 'dark')
        g = self.kinds.get('glasses')
        if g:
            for c in (el, er):
                for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)) if g == 'glasses.round' else ((-1, 0), (1, 0), (0, 0)):
                    self._set('head', c + di * du, ey + dj / (h - 1), 'extra' if g == 'glasses.round' else 'eyes',
                              'dark' if g == 'glasses.round' else 'hi')
            if g == 'glasses.goggles':
                for i in range(0, w):
                    uu = i * du
                    if abs(uu - .5) > 3.5 * du:
                        self._set('head', uu, ey, 'extra', 'mid')
        if self.kinds.get('beard') == 'beard.stubble':
            rng = _noise('%s|stubble' % self.p['seed'], 64)
            k = 0
            for i in range(-4, 5):
                for j in range(2):
                    if rng[k] > .45:
                        self._set('head', .5 + i * du, my + (j + .5) * 1.5 / (h - 1), 'hair', 'mid')
                    k += 1
        if self.kinds.get('hat') == 'hat.star_wizard':
            rng = _noise('%s|stars' % self.p['seed'], 32)
            for i in range(6):
                u0, v0 = .08 + .84 * rng[2 * i], .15 + .55 * rng[2 * i + 1]
                hx, hy, hw, hh = LAYOUT['hat']
                for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    self._set('hat', u0 + di / (hw - 1), v0 + dj / (hh - 1), 'hat2', 'hi' if (di, dj) == (0, 0) else 'base')

    # ------------------------------------------------------------ colours
    def colours(self):
        """Pick a ramp level per texel (seeded jitter between neighbouring levels), reduce to the card's count."""
        jit = _noise(self.p['seed'], ATLAS * ATLAS).reshape(ATLAS, ATLAS)
        lvl = np.zeros((ATLAS, ATLAS), np.int32)
        cov = self.slot >= 0
        val = self.shade + self.gloss * 2.2
        # continuous level position: 0 dark .. 2 base .. 3 highlight
        pos = np.interp(val, [.3, .62, .95, 1.45], [0., 1., 2., 3.])
        if BLOCK:
            blk = _noise('%s|blk' % self.p['seed'], (ATLAS // 2) ** 2).reshape(ATLAS // 2, ATLAS // 2)
            jit = BLOCK * np.kron(blk, np.ones((2, 2))) + (1. - BLOCK) * jit
        pos = pos + (jit - .5) * JITTER
        if RIM:
            sl = self.slot
            edge = np.zeros_like(cov)
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = np.roll(np.roll(sl, dy, 0), dx, 1)
                edge |= cov & (nb != sl)
            pos = pos + RIM * edge
        lvl[cov] = np.clip(np.round(pos[cov]), 0, 3).astype(np.int32)
        # reduce: drop the least-used (colour, level) pairs into a neighbouring level until the count fits
        cap = self.d['card']['unique_colours_max']
        while True:
            pairs = {}
            for s, l in zip(self.slot[cov].tolist(), lvl[cov].tolist()):
                pairs[(s, l)] = pairs.get((s, l), 0) + 1
            if len(pairs) <= cap:
                break
            (s, l), _ = min(pairs.items(), key=lambda kv: (kv[1], kv[0]))
            others = sorted((abs(l2 - l), l2) for (s2, l2) in pairs if s2 == s and l2 != l)
            sel = cov & (self.slot == s) & (lvl == l)
            if others:
                lvl[sel] = others[0][1]
                continue
            # a colour left with one level: its texels take the nearest other (colour, level) in RGB
            mine = np.array(ramp(self.d['palette'][self.names[s]]['hex'])[l], float)
            best = min(((float(np.sum((np.array(ramp(self.d['palette'][self.names[s2]]['hex'])[l2], float) - mine) ** 2)), s2, l2)
                        for (s2, l2) in pairs if s2 != s))
            self.slot[sel] = best[1]
            lvl[sel] = best[2]
        self.level = lvl
        return lvl

    def image(self):
        d = self.d
        ramps = [ramp(d['palette'][n]['hex']) for n in self.names]
        img = np.zeros((ATLAS, ATLAS, 4), np.uint8)
        img[..., 3] = 255
        cov = self.slot >= 0
        for i, r in enumerate(ramps):
            for l in range(4):
                sel = cov & (self.slot == i) & (self.level == l)
                img[sel, :3] = r[l]
        # texels no triangle reaches take the most used colour (no extra colour, inside the palette)
        keys, counts = np.unique(img[cov][:, :3], axis=0, return_counts=True)
        img[~cov, :3] = keys[np.argmax(counts)] if len(keys) else (128, 128, 128)
        return img


def png_bytes(img):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, 'PNG', optimize=False, compress_level=9)
    return buf.getvalue()


def paint(params, data, faces):
    P = Painter(params, data)
    P.paint_faces(faces)
    P.dilate(2)
    P.face()
    P.colours()
    img = P.image()
    used = sorted({tuple(c) for c in img.reshape(-1, 4)[:, :3].tolist()})
    return img, {'base_colours': list(P.names), 'unique_colours': len(used)}
