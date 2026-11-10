"""Painted textures for face-head people v2 (lane-characters).

  costume_atlas(pack, p) -> 128x128 (regions: core/people.REGIONS)
  face_atlas(pack, p)    -> 256x128, 8 cells of 64x64 (people.EXPRESSIONS order, 4 cols x 2 rows)
  hair_texture(pack, p)  -> 64x64 (top 3/4: hair shell, bottom strip: extra piece / visor)

Every texel is a pack palette colour. Shading is painted as deliberate shapes in palette tones
(steps along the pack's colour ramps) with 4x4 ordered dither for soft edges, so the palette never
bands a gradient. Runtime light is the baked vertex colour multiplied on top.
"""
import math
import numpy as np

try:
    from . import paint as P0
    from . import people as PP
except ImportError:  # pragma: no cover - loaded by path
    import importlib.util as _iu
    import pathlib as _pl
    def _load(n):
        s = _iu.spec_from_file_location(n, _pl.Path(__file__).with_name(n + '.py'))
        m = _iu.module_from_spec(s); s.loader.exec_module(m); return m
    P0 = _load('paint'); PP = _load('people')

BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + .5) / 16.


def lum(c):
    return .299 * c[0] + .587 * c[1] + .114 * c[2]


class Tones:
    """tone(name, k): k steps lighter (+) / darker (-).

    Tokens are palette names or two-colour dither MIXES 'a+b' (both palette names; painted as a 2x2
    checker, blended by bilinear filtering at runtime). pack['skin_ramps'][token] = [line, deep, shadow,
    base, highlight] gives curated skin shading; otherwise the pack/char ramp containing the name is used.
    """
    def __init__(self, pack):
        self.pack = pack
        names = pack['palette_names']
        self.fam = []
        for src in (pack.get('char_ramps', {}), pack.get('ramps', {})):
            for lst in src.values():
                lst = [c for c in lst if c in names]
                self.fam.append(sorted(dict.fromkeys(lst), key=lambda c: lum(P0.color(pack, c))))
        self.pal = P0.palette(pack)
        self.skin = pack.get('skin_ramps', {})

    def check(self, name):
        for part in str(name).split('+'):
            if part not in self.pack['palette_names']:
                raise ValueError('off-palette name ' + str(name))

    def __call__(self, name, k=0):
        self.check(name)
        if name in self.skin:
            r = self.skin[name]
            return r[max(0, min(len(r) - 1, 3 + k))]
        if k == 0:
            return name
        if '+' in name:
            return '+'.join(self(part, k) for part in name.split('+'))
        for f in self.fam:
            if name in f:
                return f[max(0, min(len(f) - 1, f.index(name) + k))]
        c = P0.color(self.pack, name) * (1.2 ** k)
        d = ((self.pal - np.clip(c, 0, 255)) ** 2 * np.array([.3, .5, .2])).sum(1)
        return self.pack['palette_names'][int(np.argmin(d))]

    def rgb(self, name, k=0):
        tok = self(name, k)
        parts = tok.split('+')
        return sum(P0.color(self.pack, q) for q in parts) / len(parts)

    def pair(self, name, k=0):
        tok = self(name, k)
        parts = tok.split('+')
        return P0.color(self.pack, parts[0]), P0.color(self.pack, parts[-1])


class Canvas:
    def __init__(self, tones, w, h, base):
        self.t = tones
        self.img = np.zeros((h, w, 3))
        y, x = np.mgrid[0:h, 0:w]
        self.x = x; self.y = y
        self.u = (x + .5) / w
        self.v = 1 - (y + .5) / h
        self.bayer = BAYER[y % 4, x % 4]
        self.checker = ((x + y) % 2) == 0
        self.put(np.ones((h, w), dtype=bool), base)

    def put(self, mask, name, k=0):
        a, b = self.t.pair(name, k)
        self.img[mask & self.checker] = a
        self.img[mask & ~self.checker] = b

    def dither(self, mask, alpha, name, k=0):
        """Paint `name` where mask and alpha > ordered-dither threshold (alpha may be an array)."""
        a = np.broadcast_to(np.asarray(alpha, float), self.u.shape)
        self.put(mask & (a > self.bayer), name, k)


def _colors(pack, p):
    """Resolve colour params (None -> pack face defaults)."""
    d = dict(pack.get('face_defaults', {}))
    out = {}
    for k in PP.COLOR_KEYS:
        out[k] = p[k] if p.get(k) is not None else d.get(k)
        if out[k] is None:
            raise ValueError('no colour for ' + k + ' in pack ' + pack['id'])
    return out


def _hash(i, j, s=0):
    return (math.sin(i * 12.9898 + j * 78.233 + s * 37.719) * 43758.5453) % 1.0


# ------------------------------------------------------------------------------------------- face
L = PP.FACE_LAYOUT
_JAW = sorted(PP._FACE_UV[(1, j)] for j in range(3, 8))
_JAW_U = [q[0] for q in _JAW]; _JAW_V = [q[1] for q in _JAW]


def _jaw_v(u):
    return np.interp(u, _JAW_U, _JAW_V)


def _half(v):
    return np.interp(v, [0, .25, .611, 1], [.191, .336, .424, .423])


def face_cell_r6(pack, p, expr, T=None):
    """Round-6 face painter, superseded by core/face_paint.py (kept for the round-6 record)."""
    T = T or Tones(pack)
    C = _colors(pack, p)
    sk = C['skin']; hl = T(sk, 1); sh = T(sk, -1); dp = T(sk, -2); ln = T(sk, -4)
    line = pack.get('face_line', ln)
    c = Canvas(T, 64, 64, sk)
    u, v = c.u, c.v
    age = p['age']; child = age == 'child'; elder = age == 'elder'
    d = np.abs(u - .5) / _half(v)
    jaw = _jaw_v(u)
    # ---- form shading: temples/cheek edges, jaw, neck, under-chin
    c.dither((d > .74) & (v > jaw), np.clip((d - .74) / .16, 0, 1), sh)
    c.put((d > .93) & (v > jaw), sh)
    c.dither((d > .96) & (v > jaw), .5, dp)
    neck = v < jaw - .004
    c.put(neck, sh)
    c.dither(neck & (v > jaw - .07) & (np.abs(u - .5) < .2), .65, dp)
    c.dither(neck & (v < .07), .5, dp)
    # cheekbone light, brow-ridge light, chin light
    eye_v = L['eye_v']; brow_v = L['brow_v']; mouth_v = L['mouth_v']; nose_v = L['nose_v']
    for s in (-1, 1):
        cb = ((u - (.5 + s * .17)) / .085) ** 2 + ((v - (eye_v - .115)) / .05) ** 2
        c.dither(cb < 1, np.clip(1 - cb, 0, 1) * (.55 if not child else .35), hl)
    c.dither((np.abs(u - .5) < .05) & (np.abs(v - (L['v_chin'] + .05)) < .022), .6, hl)
    # ---- eyes
    ew = .072 if not child else .084
    eh = {'narrow': .030, 'almond': .040, 'round': .050}[p['eye_shape']] * (1.22 if child else 1.)
    if elder:
        eh *= .9
    gaze = p['gaze'] * .018
    lid_drop = 0.
    if expr == 'sleepy':
        lid_drop = .62
    if expr == 'surprised':
        eh *= 1.35
    for s in (-1, 1):
        ex = .5 + s * L['eye_du']; ey = eye_v
        t = (u - ex) / ew
        inside_w = np.abs(t) < 1
        # socket shading between the lid and the brow (deep-set, serious)
        so = ((u - ex) / (ew * 1.25)) ** 2 + ((v - (ey + eh * .9)) / (eh * 1.6 + .02)) ** 2
        c.dither(so < 1, np.clip((1 - so) * 1.3, 0, 1) * .7, sh)
        if expr == 'blink':
            curve = ey - .004 - .010 * (1 - t ** 2)
            c.put(inside_w & (np.abs(v - curve) < .011), line)
            c.put((np.abs(t) < .8) & (np.abs(v - (curve - .016)) < .006), sh)
            if p['lashes']:
                c.put((t * s > .65) & (t * s < 1.2) & (np.abs(v - (curve + .008)) < .01), line)
            continue
        # outer corner slightly raised (alert, not cute); worried = inner corner raised
        tilt = .010 * t * s
        if expr == 'worried':
            tilt = -.014 * t * s
        up = ey + eh * np.clip(1 - t ** 2, 0, 1) ** .55 + tilt
        lo_h = eh * (.62 if expr != 'smile' else .25)
        lo = ey - lo_h * np.clip(1 - t ** 2, 0, 1) ** .9 + tilt * .5
        if lid_drop:
            up = np.minimum(up, ey + eh * (1 - lid_drop) + tilt)
        eye = inside_w & (v < up) & (v > lo)
        c.put(eye, pack.get('eye_white', 'white'))
        c.put(eye & (v > up - .018), sh)                       # lid shadow on the white
        ir = (.030 if not child else .036) * (1.0 if expr != 'surprised' else .88)
        ix = ex + gaze; iy = ey - .002 + (.004 if expr == 'surprised' else 0)
        r2 = ((u - ix) / ir) ** 2 + ((v - iy) / (ir * 1.06)) ** 2
        c.put(eye & (r2 < 1), C['eye_color'])
        c.put(eye & (r2 < 1) & (v < iy - ir * .35), C['eye_color'], 1)
        c.put(eye & (r2 < .30), line)
        c.put(eye & (((u - (ix - ir * .38)) / .012) ** 2 + ((v - (iy + ir * .42)) / .012) ** 2 < 1), 'white' if 'white' in pack['palette_names'] else pack.get('eye_white', 'white'))
        # upper lid line: heavy, thicker toward the outer corner
        lw = .016 + .012 * np.clip(t * s, 0, 1)
        c.put(inside_w & (v >= up) & (v < up + lw), line)
        c.put((np.abs(t) < 1.18) & (t * s > .82) & (v >= up - .01) & (v < up + lw), line)
        if p['lashes']:
            c.put((t * s > .7) & (t * s < 1.3) & (v > up + .004) & (v < up + .024 + .012 * (t * s - .7)), line)
        c.put((np.abs(t) < .85) & (v < lo) & (v > lo - .012), sh)  # lower lid
        if elder or p['wrinkles'] > .3:
            bag = lo - .03 - .006 * (1 - t ** 2)
            c.put((np.abs(t) < .7) & (np.abs(v - bag) < .006), sh)
            for kk in range(3):
                yy = ey + .012 - kk * .018
                c.put((t * s > 1.12) & (t * s < 1.45) & (np.abs(v - (yy - .02 * (t * s - 1.1))) < .005), dp)
        if expr == 'smile':
            c.put((np.abs(t) < .8) & (np.abs(v - (lo - .016)) < .006), sh)
    # ---- brows (straight/heavy/thin/arched; tilt = serious inner-low)
    bt = {'straight': .030, 'heavy': .044, 'thin': .020, 'arched': .028}[p['brows']]
    bc = C['brow_color']
    for s in (-1, 1):
        x0 = .5 + s * .062; x1 = .5 + s * .262
        t = np.clip((u - x0) / (x1 - x0), -1, 2)
        span = (t >= 0) & (t <= 1)
        tilt = p['brow_tilt']
        lift = 0.
        if expr == 'worried':
            tilt = -.9
        if expr == 'surprised':
            lift = .045; tilt = -.2
        if expr == 'smile':
            lift = .008
        if expr == 'sleepy':
            lift = -.008; tilt = .1
        yv = brow_v + lift - tilt * .030 * (1 - t) + .006 * t
        if p['brows'] == 'arched' or expr == 'surprised':
            yv = yv + .022 * np.sin(np.clip(t, 0, 1) * math.pi)
        thick = bt * (1.15 - .45 * t)
        c.put(span & (np.abs(v - yv) < thick / 2), bc)
        c.put(span & (np.abs(v - yv) < thick / 2) & (v > yv + thick * .15) & (t > .15) & (t < .7), bc, 1)
        c.put(span & (v < yv - thick / 2) & (v > yv - thick / 2 - .012) & (t < .8), sh)
    if expr == 'worried' or p['brow_tilt'] > .6:
        c.put((np.abs(u - .5) < .012) & (v > brow_v - .03) & (v < brow_v + .01), sh)  # frown crease
    # ---- nose
    nb = np.abs(u - .5)
    c.dither((u > .506) & (u < .548) & (v > nose_v + .01) & (v < eye_v - .005), .8, sh)        # shaded flank
    c.put((u > .506) & (u < .54) & (v > nose_v + .02) & (v < nose_v + .1), sh)
    c.dither((u > .47) & (u < .5) & (v > nose_v + .05) & (v < eye_v - .02), .5, hl)            # bridge light
    c.put((nb < .05) & (v > nose_v - .03) & (v < nose_v - .006), sh)                           # under-nose
    for s in (-1, 1):
        c.put((np.abs(u - (.5 + s * .027)) < .010) & (np.abs(v - (nose_v - .004)) < .008), dp)
    c.put((nb < .016) & (np.abs(v - (nose_v + .045)) < .012), hl)                               # tip light
    if not child:
        c.put((nb < .009) & (v > mouth_v + .025) & (v < nose_v - .03), sh)                      # philtrum
    # ---- age / character marks
    if elder or p['wrinkles'] > .5:
        for s in (-1, 1):
            tt = np.clip((v - mouth_v) / (nose_v - mouth_v), 0, 1)
            fold_u = .5 + s * (.105 - .03 * tt)
            c.put((v > mouth_v - .01) & (v < nose_v) & (np.abs(u - fold_u) < .009), dp)
        c.put((d > .6) & (np.abs(v - (jaw + .03)) < .01) & (np.abs(u - .5) > .16), sh)        # jowl
    if p['freckles']:
        for i in range(26):
            fu = .5 + (_hash(i, 1) - .5) * .5; fv = nose_v + .03 + _hash(i, 2) * .12
            if abs(fu - .5) > .04:
                c.put((np.abs(u - fu) < .009) & (np.abs(v - fv) < .009), sh)
    if child:
        for s in (-1, 1):
            bl = ((u - (.5 + s * .19)) / .06) ** 2 + ((v - (nose_v - .005)) / .035) ** 2
            c.dither(bl < 1, .45, pack.get('blush', T(sk, -1)))
    # ---- beard (painted on the jaw; drawn before the mouth)
    beard = p['beard']
    bcol = C['hair_color']
    if beard != 'none':
        region = (v < mouth_v + .055 + .3 * np.clip(d - .55, 0, 1)) & (v > jaw - .05) & (d < 1.02)
        if beard == 'full':
            region = (v < mouth_v + .13 + .25 * np.clip(d - .3, 0, 1)) & (v > jaw - .09) & (d < 1.02)
            region &= ~((np.abs(u - .5) < .1) & (v > mouth_v + .03) & (v < nose_v - .02) & False)
        if beard == 'moustache':
            region = (np.abs(u - .5) < .115 - 2.2 * np.clip(mouth_v + .045 - v, 0, 1) * 0) & (v > mouth_v + .012) & (v < mouth_v + .055)
        if beard == 'stubble':
            c.dither(region, .45, T(sk, -2) if lum(T.rgb(bcol)) < lum(T.rgb(sk)) else bcol)
        else:
            c.put(region, bcol)
            c.dither(region, .35 + .3 * np.sin(u * 90) ** 2, bcol, -1)
            c.put(region & (v < jaw - .02), bcol, -1)
            c.dither(region & (np.abs(u - .5) < .2) & (v > mouth_v), .3, bcol, 1)
    # ---- mouth
    mw = {'neutral': .080, 'thin': .072, 'full': .086}[p['mouth']] * (.82 if child else 1.)
    lip = C['lip_color']
    mu = (u - .5) / mw
    inside = np.abs(mu) < 1
    if expr in ('talk_a', 'talk_b', 'surprised'):
        oh = {'talk_a': .026, 'talk_b': .042, 'surprised': .040}[expr]
        ow = {'talk_a': .78, 'talk_b': .9, 'surprised': .55}[expr]
        r2 = (mu / ow) ** 2 + ((v - (mouth_v - oh * .25)) / oh) ** 2
        c.put(r2 < 1.35, lip)
        c.put(r2 < 1, line)
        if expr == 'talk_b':
            c.put((r2 < 1) & (v > mouth_v + oh * .25), pack.get('teeth', 'white'))
        c.put((r2 > 1.35) & (r2 < 2.6) & (v < mouth_v - oh * .9), sh)
    else:
        curve = 0.
        if expr == 'smile':
            curve = .022 * mu ** 2
        elif expr == 'worried':
            curve = -.016 * mu ** 2 + .004 * np.sin(mu * 6)
        elif expr in ('neutral', 'sleepy', 'blink'):
            curve = -.007 * mu ** 2          # corners slightly down: serious, not cute
        my = mouth_v + curve
        c.put(inside & (np.abs(v - my) < .011), line)
        c.put(inside & (np.abs(mu) < .8) & (v < my - .011) & (v > my - .03), lip)          # lower lip
        c.put(inside & (np.abs(mu) < .5) & (v < my - .016) & (v > my - .026), lip, 1)
        c.put((np.abs(mu) < .7) & (v < my - .03) & (v > my - .046), sh)                    # under-lip shadow
        c.put(inside & (np.abs(mu) < .9) & (v > my + .011) & (v < my + .02), sh)           # upper lip
        if expr == 'smile':
            for s in (-1, 1):
                c.put((np.abs(u - (.5 + s * mw * 1.08)) < .01) & (np.abs(v - (my + .012)) < .014), sh)
    if p['scar']:
        sx = .5 + .17 * (1 if p['part'] >= 0 else -1)
        c.put((np.abs((u - sx) - (v - eye_v) * .35) < .007) & (v > eye_v + .045) & (v < brow_v + .05), hl)
    # ---- patches used by back-of-head and ear faces: clean skin with a little shading
    sp = PP.SKIN_PATCH; ep = PP.EAR_PATCH
    c.put((u > sp[0] - .02) & (u < sp[2] + .02) & (v > sp[1] - .02) & (v < sp[3] + .02), sk)
    earm = (u > ep[0] - .015) & (u < ep[2] + .015) & (v > ep[1] - .015) & (v < ep[3] + .015)
    c.put(earm, sk)
    c.put(earm & (np.abs(u - (ep[0] + ep[2]) / 2) < .025) & (np.abs(v - (ep[1] + ep[3]) / 2) < .035), sh)
    return c.img


def face_atlas(pack, p):
    """256x128: 8 expression cells (4 cols x 2 rows; cell index -> UV offset in blender.simplemat)."""
    from . import face_paint
    T = Tones(pack)
    C = _colors(pack, p)
    out = np.zeros((128, 256, 3))
    for cell, expr in enumerate(PP.EXPRESSIONS):
        col = cell % 4; row = cell // 4
        y0 = (1 - row) * 64
        c = Canvas(T, 64, 64, C['skin'])
        face_paint.paint_cell(c, pack, p, C, expr)
        out[y0:y0 + 64, col * 64:(col + 1) * 64] = c.img
    return P0.quantize(out, P0.palette(pack))


# ------------------------------------------------------------------------------------------- hair
def hair_texture(pack, p):
    T = Tones(pack)
    C = _colors(pack, p)
    st = p['hair']
    hc = C['skin'] if st == 'bald' else C['hair_color']
    c = Canvas(T, 64, 64, hc)
    u, v = c.u, c.v
    shell = v > .235
    hv = np.clip((v - .25) / .75, 0, 1)        # 0 hem .. 1 crown
    fu = np.minimum(np.abs(u - .5), 1)          # 0 front .. .5 back
    sk = C['skin']
    if st == 'bald':
        c.put(shell & (hv > .6) & (fu < .22), sk, 1)                     # round 10: solid planes, no dither
        c.put(shell & (hv < .12), sk, -1)
        if p['age'] == 'elder' or p['wrinkles'] > .4:
            for k in range(3):
                c.put(shell & (fu < .1) & (np.abs(hv - (.13 + .07 * k)) < .012), sk, -1)
    elif st == 'beanie':
        rib = (np.floor(u * 64) % 3 == 0)
        c.put(shell & rib, hc, -1)
        brim = shell & (hv < .2)
        c.put(brim, hc, 1)
        c.put(brim & (np.floor(v * 64) % 2 == 0), hc)
        c.put(shell & (np.abs(hv - .2) < .025), hc, -2)
        c.put(shell & (hv > .93), C['accent_color'])
        c.put(shell & (hv > .45) & (hv < .8) & (fu < .12) & ~rib, hc, 1)
    else:
        # strands: grooves following the flow from crown to hem, with sweep/part shaping
        part = p['part']
        # smooth sculpted shading (round 8): dark hem -> base -> highlight band, a few broad lock splits
        flow = u * 5 + part * hv * .6 + .06 * np.sin(hv * 4 + u * 12)
        fr = flow % 1.0
        # round 10: solid painted planes only (the ordered dither read as knitting); the hem darkens only
        # inside each lock's root shadow, never as a full band (a full dark band read as a hat brim)
        lock_sh = np.abs(fr - .5) < .16 + .10 * np.clip((.30 - hv) / .30, 0, 1)
        c.put(shell & (hv < .30) & lock_sh, hc, -1)
        if st == 'curls':
            blob = np.sin(u * 32) * np.sin(v * 26 + np.sin(u * 16) * 1.5)
            c.put(shell & (blob > .3), hc, 1)
            c.put(shell & (blob < -.6), hc, -1)
            c.put(shell & (hv > .5) & (blob > .62), hc, 2)
        else:
            split = (np.abs(fr - .5) < .045) & (hv < .8)
            c.put(shell & split, hc, -1)
            # highlight band follows each lock (wavy edge per lock), a brighter core on the lit side of the lock
            band = np.abs(hv - (.62 + .05 * np.sin(fr * 2 * math.pi))) < .085
            c.put(shell & ~split & band, hc, 1)
            core = (np.abs(hv - .63) < .045) & (np.abs(fr - .25) < .10)
            c.put(shell & core & ~split, hc, 2)
        c.put(shell & (hv < .05) & (np.abs(fr - .5) < .2), hc, -2)   # shadow only between the lock tips
        if abs(part) > .2 and st in ('swept', 'long', 'bob', 'crop'):
            pu = .5 + part * .06
            c.put(shell & (np.abs(u - pu) < .008) & (hv > .55), hc, -2)
        # visible forehead for swept-back styles (painted skin on the front band of the shell)
        if st in ('crop', 'ponytail', 'bun', 'braid', 'long'):
            reced = .14 + (.12 if p['age'] == 'elder' else 0) + (.04 if st == 'crop' else 0)
            fh = shell & (fu < .115 + .025 * np.cos(u * 40)) & (hv < reced - .05 * (fu / .115) ** 2)
            c.put(fh, sk)
            c.put(fh & (hv < .04), sk, -1)
            c.put(fh & (hv > .04) & (hv < reced * .5) & (fu < .05), sk, 1)
            if p['age'] == 'elder' or p['wrinkles'] > .5:
                for k in range(2):
                    c.put(fh & (np.abs(hv - (.05 + .035 * k)) < .008) & (fu < .08), sk, -1)
        if p['leaf_tufts']:
            lf = C['accent_color']
            for i in range(9):
                lu = (i / 9. + .03) % 1.0; lv = .62 + .3 * _hash(i, 7)
                du = np.minimum(np.abs(u - lu), 1 - np.abs(u - lu)); dv = (v - lv)
                rot = .7 if i % 2 else -.7
                a = (du * math.cos(rot) - dv * math.sin(rot)) / .045; b = (du * math.sin(rot) + dv * math.cos(rot)) / .022
                leaf = shell & (a * a + b * b < 1)
                c.put(leaf, lf)
                c.put(leaf & (b > .2), lf, 1)
                c.put(leaf & (np.abs(b) < .25), lf, -1)
    # extra strip (bottom): ponytail/bun/braid strands or the visor plate
    ex = v < .235
    ev = np.clip(v / .235, 0, 1)
    if p['visor']:
        # extra-piece UVs: u = cross-section (0...4 back/inside, .4-.6 top, .6-1 front face), ev = along the visor
        base = C['extra_color']; red = C['extra_color_2']; dark = pack.get('face_line', T(base, -4))
        c.put(ex, base)
        c.put(ex & (u < .4), T(base, -3))
        front = ex & (u >= .58)
        stripe = np.abs(((ev * 2.2 + (u - .58) * 2.4) % 1.0) - .5) < .17
        c.put(front & stripe, red)
        c.put(front & stripe & (u > .9), red, -1)
        c.put(ex & (np.abs(u - .6) < .025), dark)
        c.put(ex & (u > .975), dark)
        c.put(front & ~stripe & (u > .62) & (u < .7), base, -1)
    else:
        if st == 'braid':
            chev = (np.abs(((v * 64 / 3) + np.abs(u - .5) * 6) % 2 - 1) < .35)
            c.put(ex & chev, hc, -1)
        else:
            c.put(ex & (np.abs(((u * 12) % 1.0) - .5) < .14), hc, -1)
            c.put(ex & (ev > .36) & (ev < .62) & (np.abs(((u * 12) % 1.0) - .5) > .2), hc, 1)
    return P0.quantize(c.img, P0.palette(pack))


# ---------------------------------------------------------------------------------------- costume
def _region_canvas(T, base, region, size=128):
    u0, v0, u1, v1 = region
    x0 = int(round(u0 * size)); x1 = int(round(u1 * size)); y0 = int(round((1 - v1) * size)); y1 = int(round((1 - v0) * size))
    c = Canvas(T, x1 - x0, y1 - y0, base)
    c.tu = np.clip((c.u - .03) / .94, 0, 1)
    c.tv = np.clip((c.v - .03) / .94, 0, 1)
    return c, (x0, x1, y0, y1)


def _fabric(c, mask, col, kind, seed=0):
    u, v = c.tu, c.tv
    if kind == 'knit':
        c.put(mask & (np.floor(c.x) % 3 == 0), col, -1)        # round 11: vertical rib, not a checker
    elif kind == 'quilted':
        ch = (v * 7) % 1.0
        c.put(mask & (ch < .1), col, -1)
        c.put(mask & (ch > .4) & (ch < .7), col, 1)          # round 11: solid quilt light band
    elif kind == 'stripes':
        pass
    elif kind == 'checks':
        c.put(mask & ((np.floor(u * 8) + np.floor(v * 8)) % 2 == 0), col, -1)
    elif kind == 'fabric':
        n = np.sin(c.x * 1.7 + seed) * np.sin(c.y * 2.3 + seed * .7)
        c.put(mask & (n > .55), col, -1)
    # 'plain': no texture


def costume_atlas(pack, p):
    T = Tones(pack)
    C = _colors(pack, p)
    out = np.zeros((128, 128, 3))
    out[:] = T.rgb(C['bottom_color'])
    g = p['garment']; wear = p['wear']
    top = C['top_color']; gar = C['garment_color']; trim = C['trim_color']; acc = C['accent_color']
    belt = C['belt_color']; sk = C['skin']
    sleeve_col = top if g in ('tunic', 'apron', 'vest') else gar
    # ------------------------------------------------ torso
    c, box = _region_canvas(T, top, PP.REGIONS['torso'])
    u, v = c.tu, c.tv
    front = np.abs(u - .5)                       # 0 at the front centre, .25 at the sides, .5 at the back
    allm = np.ones_like(u, dtype=bool)
    _fabric(c, allm, top, p['top_pattern'], 1)
    if g in ('sweater',):
        c.put(allm, gar)
        _fabric(c, allm, gar, p['top_pattern'] if p['top_pattern'] != 'fabric' else 'knit', 2)
        if p['top_pattern'] == 'stripes':
            c.put((np.abs(((v * 5) % 1.0) - .5) < .12) & (v > .2) & (v < .85), acc)
        c.put(v < .1, gar, -1); c.put((v < .1) & (np.floor(c.x) % 2 == 0), gar)
        c.put(v > .92, gar, -1)
    elif g in ('tunic', 'robe', 'coverall', 'parka', 'jacket'):
        c.put(allm, gar)
        _fabric(c, allm, gar, 'quilted' if g == 'parka' else ('fabric' if g != 'coverall' else 'plain'), 3)
        if g == 'tunic':
            vn = (v > .66) & (front < .095 * (v - .66) / .34)
            c.put(vn, top)
            c.put((v > .64) & (np.abs(front - .095 * (v - .66) / .34) < .014), trim)
            c.put(v < .075, trim); c.put((v < .075) & (np.floor(c.x) % 4 == 0), trim, -1)
            for k in range(6):
                fx = .5 + (k - 2.5) * .07
                c.put((np.abs(u - fx - (.3 - v) * .08 * (k - 2.5)) < .006) & (v < .27) & (v > .08), gar, -1)
        if g == 'robe':
            for k in range(8):
                c.put((np.abs(((u * 8) % 1.0) - .5) < .05) & (v < .55), gar, -1)
            c.put((np.abs((u - .5) - (v - .82) * -.25) < .012) & (v > .45), trim)
            c.put(v < .05, trim)
        if g == 'coverall':
            c.put((front < .008) & (v > .22), gar, -2)
            c.put((front < .02) & (front > .008) & (v > .22) & (np.floor(c.y) % 2 == 0), gar, 1)
            for s in (-1, 1):
                pk = (np.abs(u - (.5 + s * .1)) < .045) & (v > .6) & (v < .74)
                c.put(pk, gar, 1); c.put(pk & (v > .71), gar, -1)
                c.put(pk & ((np.abs(np.abs(u - (.5 + s * .1)) - .045) < .006) | (np.abs(v - .6) < .008)), gar, -1)
            c.put((np.abs(u - .63) < .028) & (np.abs(v - .79) < .03), acc)
            c.put((np.abs(front - .25) < .006), gar, -1)
        if g == 'parka':
            c.put((front < .01) & (v > .08), gar, -2)
            for s in (-1, 1):
                c.put((np.abs(u - (.5 + s * .13)) < .05) & (np.abs(v - .2) < .03), gar, -1)
            c.put(v < .06, gar, -1)
        if g == 'jacket':
            c.put((front < .007) & (v > .1), trim)
            if p['chevrons']:
                for s in (-1, 1):
                    cu = .5 + s * .2
                    chev = (np.abs(np.abs(u - cu) * 1.6 - (v - .45)) < .05) & (v > .45) & (v < .8)
                    c.put(chev, trim)
            c.put(v < .07, gar, -1)
    elif g == 'apron':
        _fabric(c, allm, top, p['top_pattern'], 4)
        pan = (front < .14) & (v < .80)
        c.put(pan, gar)
        c.dither(pan, .3 + .25 * np.sin(c.y * .9) ** 2, gar, -1)
        c.put(pan & ((np.abs(front - .14) < .012) | (v < .03)), gar, -2)
        for s in (-1, 1):
            c.put((np.abs(u - (.5 + s * .085)) < .018) & (v >= .78), gar)
        c.put((np.abs(v - .44) < .022), gar, -1)
        pk = (front < .06) & (v > .2) & (v < .34)
        c.put(pk & ((np.abs(front - .06) < .01) | (np.abs(v - .34) < .01)), gar, -2)
        for i in range(6):
            c.put((np.abs(u - (.5 + (_hash(i, 3) - .5) * .2)) < .015) & (np.abs(v - (.5 + _hash(i, 4) * .25)) < .012) & pan, gar, 1)
    elif g == 'vest':
        _fabric(c, allm, top, p['top_pattern'], 5)
        vm = (front > .065 + .04 * np.clip((.35 - v) / .35, 0, 1)) & (v > .04)
        c.put(vm, gar)
        _fabric(c, vm, gar, 'quilted' if p['top_pattern'] == 'quilted' else 'fabric', 6)
        c.put(vm & (np.abs(front - (.065 + .04 * np.clip((.35 - v) / .35, 0, 1))) < .016), trim)
        for k in range(4):
            c.put((np.abs(front - .085) < .012) & (np.abs(v - (.3 + k * .14)) < .015), acc)
    # belt / straps / buttons / patch / star
    if p['belt'] and g not in ('robe', 'sweater', 'parka'):
        bm = (v > .27) & (v < .345)
        c.put(bm, belt)
        c.put(bm & (np.abs(v - .307) < .01), belt, 1)
        c.put((front < .03) & (v > .26) & (v < .355), acc)
        c.put((front < .015) & (v > .285) & (v < .33), belt, -1)
        if g == 'jacket':
            for s in (-1, 1):
                pk = (np.abs(u - (.5 + s * .17)) < .045) & (v > .18) & (v < .35)
                c.put(pk, belt, 1); c.put(pk & (v > .31), belt)
    if g == 'robe':
        c.put((v > .36) & (v < .42), acc)
        c.put((np.abs(u - .72) < .02) & (v > .2) & (v < .42), acc)
    if p['strap'] in ('diagonal', 'satchel'):
        # from the right shoulder (front-right) down to the left hip, around the back
        su = np.where(u < .5, u + 1, u)
        line_front = np.abs((u - .5) - (-.10 + (1 - v) * .26)) < .028
        line_back = np.abs((su - 1.0) - (.12 - (1 - v) * .26)) < .028
        sm = (line_front | line_back) & (v > .12)
        c.put(sm, belt)
        c.put(sm & (np.floor(c.y) % 6 == 0), belt, 1)
    if p['buttons']:
        for k in range(5):
            c.put((front < .016) & (np.abs(v - (.42 + k * .1)) < .016), acc)
    if p['patch']:
        pm = (np.abs(u - .33) < .045) & (np.abs(v - .62) < .05)
        c.put(pm, acc); c.put(pm & (np.floor(c.x + c.y) % 3 == 0), acc, -1)
    if p['star_back']:
        bu = np.minimum(np.abs(u - 0.), np.abs(u - 1.))
        bv = v - .66
        star = (np.abs(bu) / .11) ** .55 + (np.abs(bv) / .16) ** .55 < 1.0
        c.put(star, trim)
    # torso form shading: under-arm sides, waist crease, chest light, wear
    c.dither((np.abs(front - .25) < .05) & (v > .55), .5, None or (gar if g not in ('apron', 'vest') else top), -1)
    c.dither((front < .2) & (v > .62) & (v < .86), .25, (gar if g not in ('apron', 'vest') else top), 1)
    c.dither(v < .03, .7, (gar if g not in ('apron', 'vest') else top), -1)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    # ------------------------------------------------ sleeves (u: 0 back, .25 inner, .5 front, .75 outer)
    c, box = _region_canvas(T, sleeve_col, PP.REGIONS['sleeve'])
    u, v = c.tu, c.tv
    allm = np.ones_like(u, dtype=bool)
    _fabric(c, allm, sleeve_col, 'quilted' if g == 'parka' else ('knit' if g == 'sweater' else p['top_pattern']), 7)
    if g == 'sweater' and p['top_pattern'] == 'stripes':
        c.put((np.abs(((v * 4) % 1.0) - .5) < .1) & (v > .25), acc)
    bare = None
    if p['sleeves'] == 'rolled':
        bare = v < .36
        c.put((v >= .36) & (v < .53), sleeve_col, 1)
        c.put((np.abs(v - .45) < .015) | (np.abs(v - .37) < .012), sleeve_col, -1)
    elif p['sleeves'] == 'short':
        bare = v < .62
        c.put((v >= .62) & (v < .7), trim if g == 'tunic' else sleeve_col, -1 if g != 'tunic' else 0)
    else:
        c.put(v < .08, sleeve_col, -1)
        c.put((v < .08) & (np.floor(c.x) % 2 == 0), sleeve_col)
        c.dither((np.abs(v - .5) < .07) & (np.abs(u - .5) < .3), .45, sleeve_col, -1)
        if wear > .35:
            c.dither((np.abs(v - .5) < .06) & ((u < .12) | (u > .88)), wear, sleeve_col, 1)
    if bare is not None:
        c.put(bare, sk)
        c.put(bare & (np.abs(u - .25) < .1), sk, -1)
        c.dither(bare & (np.abs(u - .75) < .12) & (v > .1), .4, sk, 1)
    if p['chevrons']:
        for k in range(2):
            cv = .62 + k * .14
            chev = (np.abs(np.abs(u - .75) * 1.2 - (v - cv) * 1.0) < .05) & (v > cv) & (v < cv + .12) & (np.abs(u - .75) < .2)
            c.put(chev, trim)
    c.put(v > .95, sleeve_col, -1)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    # ------------------------------------------------ trousers (v: ankle .. hip; u .75 outer)
    bot = C['bottom_color']
    c, box = _region_canvas(T, bot, PP.REGIONS['trouser'])
    u, v = c.tu, c.tv
    allm = np.ones_like(u, dtype=bool)
    tights = p['trouser_volume'] < .86
    if not tights:
        n = np.sin(c.x * 1.3 + c.y * .4) * np.sin(c.y * 1.9)
        c.put(n > .6, bot, -1)
        for k in range(3):
            c.put((np.abs(((u * 3 + v * 2.2 + k * .33) % 1.0) - .5) < .06) & (v < .2), bot, -1)
        c.put(np.abs(u - .75) < .02, bot, -1)
        c.dither((np.abs(u - .5) < .17) & (np.abs(v - .44) < .07), .3 + .55 * wear, bot, 1)
    else:
        c.dither(np.abs(u - .25) < .12, .5, bot, -1)
        c.dither((np.abs(u - .5) < .1) & (v > .3), .35, bot, 1)
    if p['cargo']:
        pk = (np.abs(u - .76) < .13) & (v > .56) & (v < .78)
        c.put(pk, bot, 1)
        c.put(pk & (v > .73), bot)
        c.put(pk & ((np.abs(np.abs(u - .76) - .13) < .02) | (np.abs(v - .56) < .015)), bot, -1)
    if p['patch'] and g != 'robe':
        km = (np.abs(u - .5) < .1) & (np.abs(v - .44) < .06)
        c.put(km, acc); c.put(km & (np.floor(c.x + c.y) % 3 == 0), acc, -1)
    c.put(v < .045, bot, -1)
    c.put(v > .96, bot, -1)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    # ------------------------------------------------ boots (v: sole .. top; u .5 toe)
    bc = C['boot_color']
    c, box = _region_canvas(T, bc, PP.REGIONS['boot'])
    u, v = c.tu, c.tv
    c.put(v < .2, pack.get('sole', T(bc, -3)))
    c.dither((np.abs(u - .5) < .12) & (v > .2) & (v < .5), .7, bc, 1)
    c.put((np.abs(v - .62) < .03), bc, -1)
    if p['boots'] in ('heavy', 'boots'):
        for k in range(4):
            c.put((np.abs(u - .5) < .07) & (np.abs(v - (.55 + k * .1)) < .022), bc, 2)
    if p['boots'] == 'cuffed':
        c.put(v > .74, C['collar_color'] if p['collar'] in ('ruff', 'hood_down') else bc, 1)
        c.put(np.abs(v - .74) < .03, bc, -2)
    if p['boots'] == 'heavy' and (p['chevrons'] or p['cargo']):
        for k in (.55, .8):                                   # grey buckle straps
            c.put(np.abs(v - k) < .04, bc, 2)
            c.put((np.abs(v - k) < .04) & (np.abs(u - .75) < .05), bc, 3)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    # ------------------------------------------------ mitts (v: fingertips .. wrist)
    gc = C['glove_color'] if p['hands'] != 'bare' else sk
    c, box = _region_canvas(T, gc, PP.REGIONS['mitt'])
    u, v = c.tu, c.tv
    if p['hands'] == 'gloves':
        c.put((np.floor(c.x) + np.floor(c.y)) % 2 == 0, gc, -1)
        c.put(v > .82, gc, 1)
    elif p['hands'] == 'fingerless':
        c.put(v < .36, sk)
        c.put((v < .36) & (v > .3), sk, -1)
        c.put((v >= .36) & ((np.floor(c.x) + np.floor(c.y)) % 2 == 0), gc, -1)
    if p['hands'] == 'bare':
        c.put(v < .1, sk, -1)
        for k in range(3):
            c.put((np.abs(v - .42) < .02) & (np.abs(u - (.62 + k * .09)) < .025), sk, -1)
        c.put(v > .9, sk, -1)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    # ------------------------------------------------ collar
    cc = C['collar_color']
    cs = p['collar']
    c, box = _region_canvas(T, cc if cs != 'none' else top, PP.REGIONS['collar'])
    u, v = c.tu, c.tv
    front = np.abs(u - .5)
    if cs == 'flat':
        c.put(np.floor(c.x) % 3 == 0, cc, -1)
        c.put(v < .2, cc, -1)
    elif cs == 'high':
        c.put(front < .012, cc, -2)
        c.put((front < .03) & (np.floor(c.y) % 2 == 0), trim)
        c.put(v > .82, cc, 1)
        c.put(v < .1, cc, -1)
    elif cs == 'scarf':
        c.put(np.abs(((u * 10) % 1.0) - .5) < .14, acc)
        c.put((np.floor(c.y) % 2 == 0) & (np.floor(c.x) % 2 == 0), cc, -1)
        c.put((front < .07), cc, -1)
    elif cs == 'ruff':
        n = np.sin(c.x * 2.1 + np.sin(c.y * 1.3) * 2) * np.sin(c.y * 1.7 + c.x * .3)
        c.put(n > .3, cc, 1)
        c.put(n < -.5, cc, -1)
        c.put(v < .12, cc, -1)
    elif cs == 'shawl':
        c.put((np.floor(c.x / 2) + np.floor(c.y / 2)) % 2 == 0, cc, -1)
        c.put((v < .15) & (np.floor(c.x) % 2 == 0), cc, -2)
        c.put(np.abs(v - .55) < .06, acc)
    elif cs == 'hood_down':
        c.put(v > .7, C['trim_color'])
        c.put((v > .7) & (np.sin(c.x * 1.9) > .4), C['trim_color'], 1)
        c.put(np.abs(u - .0) < .02, cc, -1)
    out[box[2]:box[3], box[0]:box[1]] = c.img
    return P0.quantize(out, P0.palette(pack))
