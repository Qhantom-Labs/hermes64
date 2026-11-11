"""Hand-keyed textures for the n64_adult body family (lane CHARS3). Pure numpy, deterministic, no pack palette.

  cloth(p)        128x128 costume sheet (regions = ext/adult.REGIONS)
  hair(p)         64x64 hair / head-side sheet (ext/adult.HAIR_REGIONS)
  face_atlas(p)   256x128, eight 64x64 expression cells in core/people.EXPRESSIONS order
  emblem(p)       32x32 shared back / chest emblem (default: a plain four-point star of our own drawing)

Every surface is painted with three or four flat tones per colour (shadow, base, light, line): no gradients, no noise,
no dithering, so texels stay readable through the N64 three-point filter. Light comes from the upper left of the
viewer (the runtime key light), so shadows sit on the viewer's right and underneath.
"""
import math

import numpy as np

try:
    from . import adult as AD
except ImportError:
    from ext import adult as AD

EXPRESSIONS = ['neutral', 'blink', 'talk_a', 'talk_b', 'smile', 'worried', 'surprised', 'sleepy']
COOL = np.array([52., 46., 104.])
WARM = np.array([255., 244., 214.])

COLORS = {
    'skin': '#e2ae86', 'hair': '#3fb060', 'hair_tip': '#3d8fd6', 'brow': '#1f4a34', 'eye': '#2a5a8c',
    'jacket': '#2f8a4c', 'panel': '#dfe9cf', 'trim': '#1c3d30', 'trouser': '#3a4262', 'boot': '#2e2f40',
    'sole': '#9a9cab', 'glove': '#22242e', 'belt': '#6a4c30', 'buckle': '#e0c765', 'pouch': '#7a6442',
    'emblem': '#f4f0dc', 'shirt': '#c9c9d2', 'lip': '#a86a5a',
}
FACE = {'brow': 'stern', 'eye_h': 4, 'eye_w': 10, 'fringe': 'spiky', 'mouth': 'flat', 'glasses': False, 'lash': False,
        'stubble': False, 'blush': False, 'hairline': 19}


def rgb(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float)


def tones(c):
    """(line, shadow, base, light) for a hex colour: shadows lean cool, lights lean warm."""
    b = rgb(c) if isinstance(c, str) else np.asarray(c, float)
    return (np.clip(b * .42 * .8 + COOL * .2, 0, 255), np.clip(b * .72 * .88 + COOL * .12, 0, 255), b,
            np.clip(b * 1.14 * .86 + WARM * .14, 0, 255))


class Canvas:
    def __init__(self, w, h, fill=(0, 0, 0)):
        self.w, self.h = w, h
        self.img = np.zeros((h, w, 3), float)
        self.img[:] = fill

    def rect(self, x0, y0, x1, y1, c):
        """Inclusive pixel rectangle, clipped."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        if x1 < x0 or y1 < y0:
            return
        self.img[max(0, y0):min(self.h, y1 + 1), max(0, x0):min(self.w, x1 + 1)] = c

    def px(self, x, y, c):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.img[y, x] = c

    def line(self, x0, y0, x1, y1, c, t=1):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n):
            f = i / float(max(1, n - 1))
            x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            for k in range(t):
                self.px(x, y + k, c)

    def poly(self, pts, c):
        """Filled convex or concave polygon (even-odd scanline at pixel centres)."""
        ys = [p[1] for p in pts]
        for y in range(int(math.floor(min(ys))), int(math.ceil(max(ys))) + 1):
            yc = y + .5
            xs = []
            for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
                if (ya <= yc < yb) or (yb <= yc < ya):
                    xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                self.rect(math.ceil(a - .5), y, math.floor(b - .5), y, c)

    def blit(self, other, x, y):
        self.img[y:y + other.h, x:x + other.w] = other.img


class Region(Canvas):
    """A canvas for one sheet region; paste() writes it back."""

    def __init__(self, table, name, fill):
        x, y, w, h = table[name]
        Canvas.__init__(self, w, h, fill)
        self.at = (x, y)


def colors(p):
    c = dict(COLORS)
    c.update(p.get('colors') or {})
    return c


def face_params(p):
    f = dict(FACE)
    f.update(p.get('face') or {})
    return f


# ------------------------------------------------------------------ costume sheet
def _jacket(p, C):
    style = p.get('torso', 'bomber')
    base = {'bomber': 'jacket', 'coat': 'jacket', 'shirt': 'shirt', 'top': 'shirt', 'armor': 'jacket', 'hood': 'jacket'}[style]
    L, S, B, Hh = tones(C[base])
    tl, ts, tb, th = tones(C['trim'])
    r = Region(AD.REGIONS, 'jacket', B)
    w, h = r.w, r.h
    # form shading: sides under the arms and the right-hand diagonal are in shadow, upper chest and back catch light
    r.rect(48, 0, 63, h - 1, S); r.rect(112, 0, 127, h - 1, S)
    r.rect(64, 5, 111, 12, Hh); r.rect(4, 5, 43, 9, Hh)
    r.rect(100, 13, 111, h - 1, S)                       # viewer-right front diagonal
    r.rect(0, 0, w - 1, 2, S)                            # under the collar
    if style in ('bomber', 'hood'):
        # raglan shoulder seams, front zip with a pale placket, chest pocket flaps, knit waistband with ribs
        r.line(66, 3, 76, 12, L); r.line(110, 3, 100, 12, L)
        r.line(2, 3, 10, 10, L); r.line(45, 3, 37, 10, L)
        r.rect(87, 2, 87, h - 1, Hh); r.rect(88, 2, 88, h - 1, L)
        for x0 in (70, 96):
            r.rect(x0, 15, x0 + 9, 15, L); r.rect(x0, 16, x0 + 9, 16, Hh); r.px(x0 + 4, 17, L)
        for (x0, y0, x1, y1) in ((72, 24, 77, 31), (104, 22, 99, 30), (68, 30, 74, 35), (8, 24, 14, 31), (40, 22, 34, 30)):
            r.line(x0, y0, x1, y1, S)                     # fold strokes above the waistband
        r.line(24, 4, 24, 37, S)                          # back centre seam
        r.rect(0, 38, w - 1, h - 1, tb)
        for x in range(0, w, 2):
            r.rect(x, 39, x, h - 1, ts)
        r.rect(0, 38, w - 1, 38, L)
        if p.get('tail'):                                 # untucked shirt tail showing under a shorter waistband
            pl, ps, pb, ph = tones(C['panel'])
            r.rect(0, 33, w - 1, 37, tb)
            for x in range(0, w, 2):
                r.rect(x, 34, x, 37, ts)
            r.rect(0, 33, w - 1, 33, L)
            r.rect(0, 38, w - 1, h - 1, pb); r.rect(0, 38, w - 1, 38, ps)
        if p.get('panel_chest'):
            pl, ps, pb, ph = tones(C['panel'])
            r.rect(64, 6, 111, 9, pb); r.rect(64, 10, 111, 10, ps); r.rect(0, 6, 47, 9, pb); r.rect(0, 10, 47, 10, ps)
            r.rect(87, 6, 88, 10, L)
    elif style == 'coat':
        # long coat: lapels, a button row, belt-less, hem shadow
        r.poly([(88, 2), (78, 4), (84, 18), (88, 22)], Hh); r.poly([(88, 2), (98, 4), (92, 18), (88, 22)], S)
        r.line(78, 4, 84, 18, L); r.line(98, 4, 92, 18, L); r.line(84, 18, 88, 22, L); r.line(92, 18, 88, 22, L)
        r.rect(88, 22, 88, h - 1, L)
        for y in (25, 30, 35):
            r.rect(85, y, 86, y + 1, tones(C['buckle'])[2])
        r.line(24, 4, 24, h - 1, S)
        r.rect(0, h - 2, w - 1, h - 1, S)
        for x0 in (70, 98):
            r.rect(x0, 28, x0 + 8, 28, L)
    elif style in ('shirt', 'top'):
        r.rect(88, 3, 88, h - 4, S)
        r.line(80, 2, 88, 7, L); r.line(96, 2, 88, 7, L)   # collar points
        for y in (10, 16, 22, 28):
            r.px(88, y, L)
        r.rect(0, h - 3, w - 1, h - 1, S)
        for (x0, y0, x1, y1) in ((72, 24, 78, 31), (104, 22, 98, 30), (10, 26, 16, 32)):
            r.line(x0, y0, x1, y1, S)
    elif style == 'armor':
        pl, ps, pb, ph = tones(C['panel'])
        r.rect(66, 5, 110, 30, pb); r.rect(66, 5, 110, 6, ph); r.rect(66, 29, 110, 30, ps); r.rect(104, 7, 110, 30, ps)
        r.rect(66, 5, 66, 30, pl); r.rect(110, 5, 110, 30, pl); r.rect(66, 4, 110, 4, pl); r.rect(66, 31, 110, 31, pl)
        cx, cy = 88, 18                                   # vault door: ring, spokes, bolts
        for a in range(0, 360, 15):
            r.px(cx + 9 * math.cos(math.radians(a)), cy + 9 * math.sin(math.radians(a)), pl)
        for a in range(0, 360, 60):
            r.line(cx, cy, cx + 6 * math.cos(math.radians(a)), cy + 6 * math.sin(math.radians(a)), pl)
        r.rect(cx - 1, cy - 1, cx + 1, cy + 1, tones(C['buckle'])[2])
        for bx, by in ((69, 8), (107, 8), (69, 27), (107, 27)):
            r.px(bx, by, pl)
        r.rect(4, 6, 43, 30, pb); r.rect(4, 6, 43, 7, ph); r.rect(4, 29, 43, 30, ps); r.rect(4, 5, 43, 5, pl); r.rect(4, 31, 43, 31, pl)
        r.rect(22, 8, 25, 28, ps)
        r.rect(0, 38, w - 1, h - 1, tb); r.rect(0, 38, w - 1, 38, L)
    return r


def _sleeve(p, C):
    style = p.get('torso', 'bomber')
    if style == 'top':                                    # bare arms
        L, S, B, Hh = tones(C['skin'])
        r = Region(AD.REGIONS, 'sleeve', B)
        r.rect(26, 0, 40, r.h - 1, S); r.rect(58, 3, 63, 30, Hh); r.rect(0, 3, 4, 30, Hh)
        r.rect(0, 19, r.w - 1, 19, S)
        return r
    base = 'shirt' if style == 'shirt' else 'jacket'
    L, S, B, Hh = tones(C[base])
    tl, ts, tb, th = tones(C['trim'])
    pl, ps, pb, ph = tones(C['panel'])
    r = Region(AD.REGIONS, 'sleeve', B)
    w, h = r.w, r.h
    if p.get('sleeve') == 'puff34':
        # rows by the fixed sleeve v layout of ext/adult.arm: 3..17 upper arm, 18..25 puffed cuff, 26..27 its
        # underside, 28.. bare forearm. The pale panel sits above the elbow, its top edge slanted like half a chevron.
        kl, ks, kb, kh = tones(C['skin'])
        r.rect(24, 0, 40, 25, S)
        r.rect(56, 3, 63, 8, Hh); r.rect(0, 3, 6, 8, Hh)
        r.rect(0, 3, w - 1, 3, L)
        for x in range(w):
            d = min((x + .5) / w, 1. - (x + .5) / w)           # 0 on the outer side, .5 on the inner side
            y0 = 10. - d * 4.
            r.rect(x, y0, x, 17, pb if not 24 <= x <= 40 else ps); r.px(x, y0, ph); r.px(x, y0 - 1, L)
        r.rect(0, 18, w - 1, 18, L)
        r.rect(0, 19, w - 1, 25, B); r.rect(24, 19, 40, 25, S); r.rect(0, 19, 6, 21, Hh); r.rect(56, 19, 63, 21, Hh)
        for x in range(3, w, 8):
            r.rect(x, 23, x, 25, S)                            # gathers
        r.rect(0, 26, w - 1, 27, L)
        r.rect(0, 28, w - 1, h - 1, kb); r.rect(24, 28, 40, h - 1, ks); r.rect(0, 28, w - 1, 28, ks)
        return r
    r.rect(24, 0, 40, h - 1, S)                           # inner side
    r.rect(56, 3, 63, 12, Hh); r.rect(0, 3, 6, 12, Hh)    # shoulder light on the outer side
    r.rect(0, 3, w - 1, 3, L)                             # shoulder seam
    if style in ('bomber', 'hood', 'armor', 'coat') and p.get('chevron', style == 'bomber'):
        for x in range(w):
            u = (x + .5) / w
            d = min(u, 1. - u)
            yc = 14. + d * 15.
            r.rect(x, yc, x, yc + 3, pb); r.px(x, yc + 4, L); r.px(x, yc - 1, S)
            r.px(x, yc, ph)
    for (x0, y0, x1, y1) in ((10, 25, 16, 29), (48, 26, 54, 29)):
        r.line(x0, y0, x1, y1, S)
    if style == 'shirt':
        r.rect(0, 33, w - 1, h - 1, Hh); r.rect(0, 32, w - 1, 32, L)
    else:
        r.rect(0, 33, w - 1, h - 1, tb)
        for x in range(0, w, 2):
            r.rect(x, 33, x, h - 1, ts)
        r.rect(0, 32, w - 1, 32, L)
    return r


def _trouser(p, C):
    L, S, B, Hh = tones(C['trouser'])
    r = Region(AD.REGIONS, 'trouser', B)
    w, h = r.w, r.h
    r.rect(22, 0, 42, h - 1, S)                           # inner leg
    if p.get('legs', 'cargo') == 'cargo':
        for x0, x1 in ((0, 8), (55, 63)):                 # cargo pocket on the outer side (wraps the seam)
            r.rect(x0, 11, x1, 22, Hh); r.rect(x0, 14, x1, 14, S); r.rect(x0, 23, x1, 23, S)
        r.rect(9, 11, 9, 23, S); r.rect(54, 11, 54, 23, S)
    r.rect(44, 25, 54, 25, S)                             # knee crease
    r.rect(0, 30, 12, 30, S); r.rect(44, 31, w - 1, 31, S)  # two flat folds where the cloth bunches over the boot
    r.rect(0, 33, w - 1, 33, Hh)
    r.rect(0, 34, w - 1, h - 1, S)
    r.rect(48, 0, 48, 24, S) if p.get('legs') == 'slim' else None
    return r


def _boot(p, C):
    L, S, B, Hh = tones(C['boot'])
    sl, ss, sb, sh = tones(C['sole'])
    r = Region(AD.REGIONS, 'boot', B)
    w, h = r.w, r.h
    r.rect(0, 0, w - 1, 3, Hh); r.rect(0, 4, w - 1, 4, L)   # cuff
    r.rect(16, 5, 30, h - 1, S)                           # inner side
    for y in (8, 12, 16, 20):                             # laces on the front (u = .75)
        r.rect(33, y, 39, y, sb); r.px(36, y + 1, L)
    r.rect(0, 5, 2, h - 1, Hh); r.rect(45, 5, 47, h - 1, Hh)
    r.rect(0, 12, w - 1, 13, sb); r.rect(0, 14, w - 1, 14, L)       # ankle strap all round
    r.rect(0, 11, 4, 14, tones(C['buckle'])[2]); r.rect(43, 11, 47, 14, tones(C['buckle'])[2])   # buckle on the outer side
    f = Region(AD.REGIONS, 'foot', B)
    f.rect(0, 0, f.w - 1, 2, Hh)                          # top edge light
    f.rect(30, 3, f.w - 1, 12, Hh); f.rect(30, 3, 30, 17, L)   # toe cap
    f.rect(0, 16, f.w - 1, f.h - 1, sb); f.rect(0, 16, f.w - 1, 16, sh)
    for x in range(3, f.w, 6):
        f.rect(x, 20, x, f.h - 1, ss)                     # tread
    f.rect(0, 15, f.w - 1, 15, L)
    return r, f


def _mitt(p, C):
    gl, gs, gb, gh = tones(C['glove'])
    kl, ks, kb, kh = tones(C['skin'])
    r = Region(AD.REGIONS, 'mitt', gb)
    w, h = r.w, r.h
    fingerless = p.get('gloves', 'fingerless') == 'fingerless'
    bare = p.get('gloves') == 'none'
    if bare:
        r.rect(0, 0, w - 1, h - 1, kb)
    r.rect(0, 0, w - 1, 1, gh if not bare else kh); r.rect(0, 2, w - 1, 2, gl if not bare else ks)   # wrist strap
    if not bare:
        r.rect(0, 6, w - 1, 6, gh)                        # knuckle guard
    if fingerless or bare:
        y = 13 if bare else 19                            # a fingerless glove covers the fist down to the last knuckle
        r.rect(0, y, w - 1, h - 1, kb)
        if not bare:
            r.rect(0, y - 1, w - 1, y - 1, gl)
        for x in (5, 11, 16, 21, 27):
            r.rect(x, y + 1, x, 20, ks)                   # finger lines
        r.rect(0, 21, w - 1, h - 1, ks)
    else:
        for x in (5, 11, 16, 21, 27):
            r.rect(x, 12, x, 20, gl)
        r.rect(0, 20, w - 1, h - 1, gs)
    return r


def cloth(p):
    C = colors(p)
    sheet = Canvas(AD.CLOTH, AD.CLOTH, tones(C['trouser'])[1])
    boot, foot = _boot(p, C)
    parts = [_jacket(p, C), _sleeve(p, C), _trouser(p, C), boot, foot, _mitt(p, C)]
    # belt with a buckle at the front
    bl, bs, bb, bh = tones(C['belt'])
    r = Region(AD.REGIONS, 'belt', bb)
    r.rect(0, 0, r.w - 1, 1, bh); r.rect(0, r.h - 2, r.w - 1, r.h - 1, bs)
    k = tones(C['buckle'])
    r.rect(30, 2, 35, 7, k[2]); r.rect(30, 2, 35, 2, k[3]); r.rect(32, 4, 33, 5, bl)
    for x in (4, 10, 16, 22, 42):
        r.px(x, 4, bl)
    parts.append(r)
    pl, ps, pb, ph = tones(C['pouch'])
    r = Region(AD.REGIONS, 'pouch', pb)
    r.rect(0, 0, r.w - 1, 4, ph); r.rect(0, 5, r.w - 1, 5, pl); r.rect(11, 6, 12, 7, tones(C['buckle'])[2])
    r.rect(0, r.h - 2, r.w - 1, r.h - 1, ps); r.rect(0, 0, 4, r.h - 1, ps)
    parts.append(r)
    kl, ks, kb, kh = tones(C['skin'])
    r = Region(AD.REGIONS, 'skin', kb)
    r.rect(0, 0, r.w - 1, 5, ks); r.rect(14, 0, r.w - 1, r.h - 1, ks)     # under the chin, viewer-right side
    parts.append(r)
    tl, ts, tb, th = tones(C['trim'] if p.get('torso', 'bomber') != 'shirt' else C['shirt'])
    r = Region(AD.REGIONS, 'collar', tb)
    for x in range(0, r.w, 2):
        r.rect(x, 1, x, r.h - 1, ts)
    r.rect(0, 0, r.w - 1, 0, th)
    if p.get('torso', 'bomber') in ('bomber', 'coat'):    # stand-up collar: body colour, knit edge on top
        jl, js, jb, jh = tones(C['jacket'] if p.get('torso', 'bomber') == 'bomber' else C.get('coat', C['jacket']))
        r.rect(0, 0, r.w - 1, r.h - 1, jb); r.rect(0, 0, r.w - 1, 1, jh); r.rect(0, 9, r.w - 1, r.h - 1, js)
    parts.append(r)
    r = Region(AD.REGIONS, 'seat', tones(C['trouser'])[2])
    parts.append(r)
    for r in parts:
        sheet.blit(r, r.at[0], r.at[1])
    return np.clip(np.rint(sheet.img), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ hair sheet
def hair(p):
    C = colors(p)
    hl, hs, hb, hh = tones(C['hair'])
    tl, ts, tb, th = tones(C.get('hair_tip', C['hair']))
    kl, ks, kb, kh = tones(C['skin'])
    sheet = Canvas(AD.HAIR, AD.HAIR, hb)
    style = p.get('hair', 'spikes')
    bald = style == 'bald'
    hood = style == 'hood'
    if hood:
        hl, hs, hb, hh = tones(C['jacket'])
    # side of the head: v = 0 at the crown, the face is on the left of the region. Flat tones only, like the spikes.
    two = 'hair_tip' in C and not hood and not bald
    r = Region(AD.HAIR_REGIONS, 'side', kb)
    line = {'spikes': 15, 'bob': 29, 'curly': 15, 'short': 12, 'hood': 32, 'bald': 0, 'receding': 11}.get(style, 13)
    if not bald:
        r.poly([(0, 0), (r.w, 0), (r.w, min(r.h, line + 9)), (15, line + 3), (9, line + 8), (6, line), (0, line - 2)], hb)
        r.poly([(13, 8), (r.w, 8), (r.w, min(r.h, line + 9)), (15, line + 3)], hs * .5 + hb * .5)
    r.rect(0, 28, r.w - 1, r.h - 1, ks)                   # under the jaw
    sheet.blit(r, r.at[0], r.at[1])
    r = Region(AD.HAIR_REGIONS, 'back', kb)
    bl = {'spikes': 28, 'bob': 32, 'curly': 23, 'short': 18, 'hood': 32, 'bald': 0, 'receding': 17}.get(style, 22)
    if not bald:
        r.rect(0, 0, r.w - 1, bl, hs * .5 + hb * .5)
        r.rect(0, 0, r.w - 1, 6, hb)
    r.rect(0, 29, r.w - 1, r.h - 1, ks)
    sheet.blit(r, r.at[0], r.at[1])
    r = Region(AD.HAIR_REGIONS, 'top', hb if not bald else kb)
    if two:                                               # v = 0 is the forehead: the tint is the front third, cut in points
        r.rect(0, 0, r.w - 1, 8, tb)
        for x in range(0, r.w, 8):
            r.poly([(x, 9), (x + 8, 9), (x + 4, 14)], tb)
    sheet.blit(r, r.at[0], r.at[1])
    for name, tip in (('spike', False), ('spike_tip', True)):   # columns: lit, mid, dark; v = 0 at the tip
        r = Region(AD.HAIR_REGIONS, name, hb)
        a_, b_, c_ = (th, tb, tb * .55 + ts * .45) if (tip and two) else (hh, hb, hb * .5 + hs * .5)
        r.rect(0, 0, 4, r.h - 1, a_); r.rect(5, 0, 10, r.h - 1, b_); r.rect(11, 0, r.w - 1, r.h - 1, c_)
        sheet.blit(r, r.at[0], r.at[1])
    return np.clip(np.rint(sheet.img), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ face
def _eye(c, cx, cy, w, h, C, F, expr, side):
    """One painted eye centred on (cx, cy). side: -1 = the eye on the viewer's left. Built like the period faces
    that survive distance: a heavy upper lid, a white, a large saturated iris cut by the lid, a dark pupil and a
    two-texel highlight. The lid drops toward the nose for a level, serious look; nothing is drawn under the eye
    but one short shadow at the outer corner."""
    kl, ks, kb, kh = tones(C['skin'])
    il, is_, ib, ih = tones(C['eye'])
    line = np.array([26., 22., 34.])
    white = np.array([248., 248., 242.])
    hot = np.array([255., 255., 255.])
    x0 = cx - w // 2
    x1 = x0 + w - 1
    inner, outer = (x1, x0) if side < 0 else (x0, x1)
    if expr == 'blink':
        c.rect(x0 - 1, cy + 1, x1 + 1, cy + 2, line); c.px(outer + side, cy, line)
        return
    hh = h + (2 if expr == 'surprised' else 0)
    top = cy - hh // 2
    bot = top + hh - 1
    if expr == 'sleepy':
        top += max(1, hh // 2)
    big = hh >= 7
    c.rect(x0, top, x1, bot, white)
    c.rect(x0, top, x1, top, white * .80)                             # the lid's shadow on the white
    c.px(outer, bot, kb); c.px(inner, bot, kb)                        # rounded lower corners
    if big:
        c.px(outer, bot - 1, white * .80); c.px(outer - side, bot, white * .80); c.px(inner + side, bot, white * .80)
    iw = max(3, int(round(w * (.58 if big else .5))))
    ix0 = cx - iw // 2 - (1 if side < 0 and iw % 2 == 0 else 0)
    ix1 = ix0 + iw - 1
    c.rect(ix0, top, ix1, bot, ib)
    c.rect(ix0, top, ix1, top + (1 if big else 0), is_ * .7 + line * .3)   # upper iris in the lid's shadow
    if big:
        c.rect(ix0 + 1, bot - 1, ix1 - 1, bot, ih)                     # lit lower iris
        c.px(ix0, bot, white * .80); c.px(ix1, bot, white * .80)       # round iris
        pw = max(2, iw // 2 - 1)
        px0 = ix0 + (iw - pw) // 2
        pm = (top + bot) // 2
        c.rect(px0, pm - pw // 2, px0 + pw - 1, pm - pw // 2 + pw - 1, line)   # square pupil, as wide as it is tall
        c.rect(ix0 + 1, top + 2, ix0 + 2, top + 3, hot)                # highlight (key light: viewer's upper left)
    elif iw >= 4:
        c.rect(ix0 + 1, top + 1, ix1 - 1, max(top + 1, bot - 1), line)
        if bot - top >= 2:
            c.px(ix0 + 1, top + 1, hot); c.rect(ix0 + 1, bot, ix1 - 1, bot, ih)
    else:
        c.rect(ix0 + 1, top, ix0 + 1, bot, line)
        if bot - top >= 2:
            c.px(ix0 + 1, top + 1, hot)
    t = 2 if big else 1                                               # upper lid, heavier on a big eye
    c.rect(x0, top - t, x1, top - 1, line)
    c.px(outer + side, top - 1, line); c.px(outer + side, top, line)
    if big:
        if F.get('brow') in ('stern', 'heavy') and expr in ('neutral', 'talk_a', 'talk_b'):
            c.rect(min(inner, inner - 3 * side), top, max(inner, inner - 3 * side), top, line)   # lid dips at the nose
    if F.get('lash'):
        c.rect(x0 - 1, top - t - 1, x1 + 1, top - t - 1, line); c.px(outer + side, top - t - 1, line)
        c.px(outer + 2 * side, top - t - 2, line); c.px(outer + 3 * side, top - t - 2, line)
    c.rect(min(outer, outer - 3 * side), bot + 1, max(outer, outer - 3 * side), bot + 1, ks)   # outer lower lid only


def _fringe(c, F, C):
    hl, hs, hb, hh = tones(C.get('hair_tip', C['hair']))    # the fringe takes the crown tint
    kl, ks, kb, kh = tones(C['skin'])
    hy = F['hairline']
    style = F['fringe']
    if style == 'spiky':
        # five chunky pointed bangs; each has a lit left half and a shaded right half
        c.rect(0, 0, 63, hy - 8, hb)
        for x0, x1, tipx, d in ((-4, 12, 6, 5), (10, 25, 15, 9), (23, 38, 33, 6), (36, 52, 46, 10), (50, 68, 58, 5)):
            c.poly([(x0, hy - 9), (x1, hy - 9), (tipx, hy - 8 + d)], hb)
            c.poly([((x0 + x1) / 2. + 1, hy - 9), (x1, hy - 9), (tipx, hy - 8 + d)], hs)
        c.rect(0, 0, 63, 3, hh)
        gb = tones(C['hair'])[2]                          # the temples are the base colour, like the side of the head
        c.rect(0, 0, 5, hy - 4, gb); c.rect(58, 0, 63, hy - 4, gb)
    elif style == 'blunt':
        c.rect(0, 0, 63, hy, hb); c.rect(0, 0, 63, 3, hh)
        for x in range(5, 64, 9):
            c.rect(x, 5, x, hy - 2, hs)
        c.rect(0, 0, 10, 54, hb); c.rect(53, 0, 63, 54, hb); c.rect(9, hy, 10, 54, hs); c.rect(53, hy, 54, 54, hs)
        c.rect(11, hy + 1, 52, hy + 2, ks)
    elif style == 'curly':
        c.rect(0, 0, 63, hy - 4, hb)
        for i, x in enumerate(range(-2, 64, 8)):
            c.rect(x, hy - 4, x + 5, hy - 1 + (i % 2) * 2, hb); c.rect(x + 3, hy - 6, x + 5, hy - 1 + (i % 2) * 2, hs)
        c.rect(0, 0, 63, 3, hh)
    elif style == 'hood':
        tl, ts, tb, th = tones(C['jacket'])
        c.rect(0, 0, 63, hy, ts); c.rect(0, 0, 12, 63, ts); c.rect(51, 0, 63, 63, ts)
        c.rect(0, hy + 1, 63, hy + 1, tl); c.rect(12, hy, 12, 63, tl); c.rect(51, hy, 51, 63, tl)
        c.rect(13, hy + 2, 50, hy + 5, ks)                # the hood shades the brow
    elif style == 'receding':
        c.rect(0, 0, 63, hy - 8, hb); c.rect(0, 0, 13, hy + 2, hb); c.rect(50, 0, 63, hy + 2, hb); c.rect(0, 0, 63, 3, hh)
        c.rect(50, hy - 7, 63, hy + 2, hs)
    elif style == 'bald':
        c.rect(18, 4, 34, 7, kh)


def paint_cell(p, expr):
    C = colors(p)
    F = face_params(p)
    kl, ks, kb, kh = tones(C['skin'])
    line = np.array([26., 22., 34.])
    bl = tones(C['brow'])[0] * .7
    c = Canvas(64, 64, kb)
    girl = p.get('band') == 'girl'
    # head form: the viewer-right side panel and the underside of the jaw are one flat shadow tone
    # head form, symmetric (the baked vertex light gives the side): cheeks fall away under the cheekbones, jaw shadow
    c.poly([(0, 44), (12, 63), (0, 63)], ks); c.poly([(63, 44), (51, 63), (63, 63)], ks)
    c.rect(0, 61, 63, 63, ks)
    eye_y = F.get('eye_y', 31 if not girl else 34)
    ew, eh = F['eye_w'], F['eye_h']
    gap = F.get('eye_gap', 6)
    lx, rx = 32 - gap - (ew + 1) // 2, 32 + gap + ew // 2
    _fringe(c, F, C)
    top = eye_y - eh // 2
    kind = F['brow']
    for side, cx in ((-1, lx), (1, rx)):
        x0 = cx - ew // 2
        x1 = x0 + ew - 1
        inner, outer = (x1 + 1, x0 - 1) if side < 0 else (x0 - 1, x1 + 1)
        dy_in, dy_out, t = {'stern': (3, -1, 2), 'flat': (1, 1, 2), 'soft': (0, 1, 1), 'heavy': (2, 1, 3)}[kind]
        if expr == 'worried':
            dy_in, dy_out = -1, 2
        if expr == 'surprised':
            dy_in, dy_out = -2, -2
        if expr == 'smile':
            dy_in, dy_out = min(dy_in, 1), dy_out
        lid = 2 if eh >= 7 else 1
        by = top - lid - (4 + t) + (1 if girl else 0) - (2 if expr == 'surprised' else 0)
        c.line(outer, by + dy_out, inner, by + dy_in, bl, t + (1 if eh >= 7 and kind != 'soft' else 0))
        _eye(c, cx, eye_y, ew, eh, C, F, expr, side)
    if F.get('glasses'):
        g = np.array([24., 22., 36.])
        gy0, gy1 = top - 3, top + eh + 2
        for cx in (lx, rx):
            x0, x1 = cx - ew // 2 - 2, cx - ew // 2 + ew + 1
            c.rect(x0, gy0, x1, gy0, g); c.rect(x0, gy1, x1, gy1, g); c.rect(x0, gy0, x0, gy1, g); c.rect(x1, gy0, x1, gy1, g)
            c.px(x0 + 1, gy0 + 1, np.array([255., 255., 255.])); c.px(x0 + 2, gy0 + 1, np.array([255., 255., 255.]))
        c.rect(lx - ew // 2 + ew + 1, eye_y - 1, rx - ew // 2 - 2, eye_y - 1, g)
        c.rect(0, eye_y - 1, lx - ew // 2 - 2, eye_y - 1, g); c.rect(rx - ew // 2 + ew + 1, eye_y - 1, 63, eye_y - 1, g)
    # nose: the wedge geometry carries the form; paint only its shaded flank and the shadow under the tip
    ny0, ny1 = (eye_y + 4, eye_y + 10) if not girl else (eye_y + 6, eye_y + 9)
    c.rect(34, ny0 + 1, 34, ny1 - 1, ks)                    # bridge, shaded flank
    c.rect(29, ny1, 34, ny1, kl * .5 + ks * .5)             # under the tip
    c.px(28, ny1 - 1, ks); c.px(35, ny1 - 1, ks)            # nostril wings
    # mouth
    my = F.get('mouth_y', eye_y + 17 if not girl else eye_y + 15)
    lip = tones(C['lip'])
    mw = F.get('mouth_w', 6 if not girl else 4)
    teeth = np.array([240., 240., 232.])
    if expr == 'talk_a':
        c.rect(32 - mw + 1, my - 1, 32 + mw - 1, my + 2, line); c.rect(32 - mw + 2, my + 1, 32 + mw - 2, my + 2, lip[1])
    elif expr == 'talk_b':
        c.rect(32 - mw + 2, my - 1, 32 + mw - 2, my + 3, line); c.rect(32 - mw + 3, my - 1, 32 + mw - 3, my - 1, teeth)
        c.rect(32 - mw + 3, my + 2, 32 + mw - 3, my + 3, lip[1])
    elif expr == 'surprised':
        c.rect(30, my - 1, 34, my + 3, line); c.rect(31, my, 33, my + 2, lip[0])
    elif expr == 'smile':
        c.rect(32 - mw, my, 32 + mw, my, line); c.px(32 - mw - 1, my - 1, line); c.px(32 + mw + 1, my - 1, line)
        c.rect(32 - mw + 2, my + 1, 32 + mw - 2, my + 1, lip[2])
    else:
        c.rect(32 - mw, my, 32 + mw, my, line)
        c.rect(32 - mw + 1, my + 1, 32 + mw - 1, my + 1, lip[1])                 # two texels thick: survives 230 px
        if F['mouth'] == 'flat':
            c.px(32 - mw - 1, my, ks); c.px(32 + mw + 1, my, ks); c.px(32 - mw, my + 1, line); c.px(32 + mw, my + 1, line)
        if expr == 'worried':
            c.px(32 - mw - 1, my + 1, line); c.px(32 + mw + 1, my + 1, line)
        if F['mouth'] == 'soft':
            c.rect(32 - mw + 1, my + 1, 32 + mw - 1, my + 1, lip[2])
    c.rect(32 - mw + 3, my + 3, 32 + mw - 3, my + 3, kb * .5 + ks * .5)             # shadow under the lower lip
    if F.get('stubble'):
        st = kb * .8 + np.array([60., 60., 70.]) * .2
        c.poly([(13, my - 6), (51, my - 6), (46, 63), (18, 63)], st)
        c.rect(32 - mw - 2, my - 3, 32 + mw + 2, my + 2, kb)
        c.rect(32 - mw, my, 32 + mw, my, line)
    if F.get('blush'):
        b = kb * .72 + np.array([232., 110., 110.]) * .28
        c.rect(14, eye_y + 6, 19, eye_y + 7, b); c.rect(45, eye_y + 6, 50, eye_y + 7, b)
    return c.img


def face_atlas(p):
    out = np.zeros((128, 256, 3))
    for cell, expr in enumerate(EXPRESSIONS):
        col, row = cell % 4, cell // 4
        y0 = (1 - row) * 64          # same cell layout as core/people_paint.face_atlas
        out[y0:y0 + 64, col * 64:(col + 1) * 64] = paint_cell(p, expr)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ emblem
def emblem(p):
    """32x32 emblem decal on the jacket colour. 'star4' (default) is a plain four-point star drawn here."""
    C = colors(p)
    base = {'bomber': 'jacket', 'coat': 'jacket', 'shirt': 'shirt', 'top': 'shirt', 'armor': 'panel', 'hood': 'jacket'}[p.get('torso', 'bomber')]
    L, S, B, Hh = tones(C[base])
    el, es, eb, eh = tones(C['emblem'])
    c = Canvas(32, 32, B)
    kind = p.get('emblem_kind', 'star4')
    if kind == 'star4':
        pts, out = [], []
        for k in range(8):
            a = math.radians(45. * k - 90.)
            r = (15.5 if k % 4 == 0 else 12.5) if k % 2 == 0 else 4.6      # the upright arm is the longer one
            pts.append((16 + r * math.cos(a), 16 + r * math.sin(a))); out.append((16 + (r + 1.2) * math.cos(a), 16 + (r + 1.2) * math.sin(a)))
        c.poly(out, S); c.poly(pts, eh)
    elif kind == 'diamond':
        c.poly([(16, 2), (28, 16), (16, 30), (4, 16)], L); c.poly([(16, 4), (26, 16), (16, 28), (6, 16)], eb)
    elif kind == 'none':
        pass
    return np.clip(np.rint(c.img), 0, 255).astype(np.uint8)
