"""Paint delta of the cast_v1 family (lane CAST1): edits the tall_v3 atlases, never repaints them whole.

repaint(pack, p, style, paint, cloth, face, hair) -> (cloth, face, hair). Input = the three images tall_v3 returns
(costume 128 x 128, face atlas, headwear 64 x 64; image row 0 = v 1). Only the regions a spec asks for are painted:

  costume atlas   outfit 'plain': torso and sleeve regions in the plain garment tone (hem, placket, cuffs, one soft
                  light on the chest) instead of the round-21 bomber marks; an abstract mark on the left chest;
                  the three regions of the bottom quarter that round 21 leaves empty: coat, plate, guard
                  (ext/cast_v1.CR).
  headwear atlas  locks (blades, curls), hood shell and lining, lens and frame of the glasses, the stripe colour of
                  the visor (ext/cast_v1.HWR; the round-21 regions are reused by position, a style never uses a
                  region for two things).
The face atlas is returned as tall_v3 painted it.

Marks are abstract shapes (MARKS): an open ring, two bars in a square frame, a disc over a wedge. No text, no logos.
With the default paint and style nothing is touched: the result is the hero's atlases byte for byte.
"""
import numpy as np

from . import paint as P0
from . import people as PP
from . import people_paint as PPP

PAINT = dict(outfit='bomber', mark=None, mark_color=None, mark_ground=None, coat_color=None, plate_color=None,
             guard_color=None, guard_rim=None, hood_color=None, lens_color=None, frame_color=None, visor_stripe=None,
             belt=False)
OUTFITS = ('bomber', 'plain')
MARKS = ('ring', 'bars', 'key')
COLOR_DIALS = ('mark_color', 'mark_ground', 'coat_color', 'plate_color', 'guard_color', 'guard_rim', 'hood_color',
               'lens_color', 'frame_color', 'visor_stripe')
CHEST_MARK = (.615, .56, .075)         # centre u, v and radius in the torso region (the wearer's left chest)
VISOR_STRIPE_SRC = 'red'               # the round-21 visor stripes


class PaintError(ValueError):
    pass


def resolve(pack, paint):
    out = dict(PAINT)
    for k, v in (paint or {}).items():
        if k not in out:
            raise PaintError('unknown paint dial %r' % k)
        out[k] = v
    if out['outfit'] not in OUTFITS:
        raise PaintError('outfit is one of %s' % (OUTFITS,))
    if out['mark'] is not None and out['mark'] not in MARKS:
        raise PaintError('mark is one of %s or null' % (MARKS,))
    if type(out['belt']) is not bool:
        raise PaintError('belt must be boolean')
    for k in COLOR_DIALS:
        if out[k] is not None and out[k] not in pack['palette_names']:
            raise PaintError('%s: %r is not a colour of pack %s' % (k, out[k], pack['id']))
    return out


def mark_mask(kind, x, y):
    """The mark as a mask over local coordinates (x right, y up, the mark fills the unit disc)."""
    r = np.hypot(x, y)
    if kind == 'ring':                                   # open ring: gap toward the upper right
        ang = np.arctan2(y, x)
        return (r <= 1.) & (r >= .55) & ~((ang > .25) & (ang < 1.25))
    if kind == 'bars':                                   # two horizontal bars in a square frame
        box = (np.abs(x) <= .95) & (np.abs(y) <= .95)
        frame = box & ((np.abs(x) >= .70) | (np.abs(y) >= .70))
        bars = (np.abs(x) <= .45) & ((np.abs(y - .28) <= .14) | (np.abs(y + .28) <= .14))
        return frame | bars
    if kind == 'key':                                    # keyhole: disc over a wedge
        disc = np.hypot(x, y - .35) <= .48
        wedge = (y <= .25) & (y >= -.95) & (np.abs(x) <= .14 + .30 * (.25 - y) / 1.2)
        return disc | wedge
    raise PaintError('mark %r' % (kind,))


def _put_mark(c, kind, cu, cv, r, col, ground=None):
    w = c.u.shape[1]; h = c.u.shape[0]
    x = (c.u - cu) * w / (r * w)
    y = (c.v - cv) * h / (r * w)
    if ground is not None:
        c.put(np.hypot(x, y) <= 1.35, ground)
    c.put(mark_mask(kind, x, y), col)


def _store(pack, img, c, box):
    img[box[2]:box[3], box[0]:box[1]] = P0.quantize(c.img, P0.palette(pack))


def _swap(pack, T, img, region, src, dst, size):
    """Replace the tones of colour `src` by the same tones of `dst` inside a region."""
    u0, v0, u1, v1 = region
    x0 = int(round(u0 * size)); x1 = int(round(u1 * size)); y0 = int(round((1 - v1) * size)); y1 = int(round((1 - v0) * size))
    px = img[y0:y1, x0:x1]
    orig = px.copy()
    for k in range(-3, 4):
        a = P0.color(pack, T(src, k)); b = P0.color(pack, T(dst, k))
        px[(orig == np.asarray(a, dtype=orig.dtype)).all(axis=2)] = np.asarray(b, dtype=px.dtype)


def repaint(pack, p, style, paint, cloth, face, hair, CR, HWR, HW):
    """CR / HWR: ext/cast_v1 region tables; HW: the round-21 headwear regions (cameo.HW)."""
    paint = resolve(pack, paint)
    T = PPP.Tones(pack)
    C = PPP._colors(pack, p)
    g = C['garment_color']; trim = C['trim_color']
    cloth = np.array(cloth, copy=True); hair = np.array(hair, copy=True)
    one = None

    if paint['outfit'] == 'plain':
        c, box = PPP._region_canvas(T, g, PP.REGIONS['torso'])
        u, v = c.tu, c.tv
        front = np.abs(u - .5) < .22
        c.dither(front & (v > .50) & (v < .92), np.clip(1. - np.abs(u - .5) / .22, 0., 1.) * .75, g, 1)   # soft chest light
        c.put(np.abs(np.abs(u - .5) - .25) < .035, g, -1)                # under the arms
        c.put(v > .93, g, -1)                                            # seam under the collar
        c.put((np.abs(u - .5) < .012) & (v < .93), g, -1)                # placket
        c.put(v < .07, C['belt_color'] if paint['belt'] else g, 0 if paint['belt'] else -1)       # hem / belt
        if paint['mark'] and not style['plate']:                         # with a plate the mark is on the plate
            _put_mark(c, paint['mark'], .03 + .94 * CHEST_MARK[0], .03 + .94 * CHEST_MARK[1], CHEST_MARK[2],
                      paint['mark_color'] or trim, paint['mark_ground'])
        _store(pack, cloth, c, box)
        c, box = PPP._region_canvas(T, g, PP.REGIONS['sleeve'])
        u, v = c.tu, c.tv
        c.dither(v > .55, np.clip((v - .55) / .45, 0., 1.) * .6, g, 1)   # shoulder catches the light
        c.put(v < .10, trim)                                             # cuff
        c.put((v >= .10) & (v < .14), g, -1)
        _store(pack, cloth, c, box)
    elif paint['mark']:
        raise PaintError("a chest mark needs outfit 'plain' (the bomber chest is taken by its own marks)")

    if style['coat']:
        cc = paint['coat_color'] or g
        c, box = PPP._region_canvas(T, cc, CR['coat'])
        u, v = c.tu, c.tv
        c.put(v < .14, trim)                                             # lower edge
        c.put((v >= .14) & (v < .22), cc, -1)
        c.put(np.abs(u - .5) < .02, cc, -2)                              # front opening
        c.put(np.abs(np.abs(u - .5) - .25) < .03, cc, -1)                # side folds
        c.dither(v > .6, np.clip((v - .6) / .4, 0., 1.) * .5, cc, -1)    # shadow under the jacket hem
        _store(pack, cloth, c, box)
    if style['plate']:
        pc = paint['plate_color'] or 'grey_0'
        c, box = PPP._region_canvas(T, pc, CR['plate'])
        d = np.hypot(c.u - .5, c.v - .5) / .46
        c.put(d > .78, pc, -1)                                           # sunk rim
        c.put((d > .70) & (d <= .78), pc, 1)                             # edge of the raised face
        if paint['mark']:
            _put_mark(c, paint['mark'], .5, .5, .25, paint['mark_color'] or trim, paint['mark_ground'])
        _store(pack, cloth, c, box)
    if style['guards']:
        gc = paint['guard_color'] or g
        c, box = PPP._region_canvas(T, gc, CR['guard'])
        d = np.hypot(c.u - .5, c.v - .5) / .47
        c.put(d < .35, gc, 1)                                            # crown of the guard
        c.put(d > .80, paint['guard_rim'] or trim)                       # rim
        _store(pack, cloth, c, box)

    hc = C['hair_color']
    if style['hair'] in ('crop', 'swept', 'tufts', 'curls'):
        c, box = PPP._region_canvas(T, hc, HWR['lock'], size=64)
        c.put(c.tv < .30, hc, -1)                                        # root
        c.put(c.tv > .72, hc, 1)                                         # tip
        _store(pack, hair, c, box)
    if style['hair'] == 'hood':
        hd = paint['hood_color'] or g
        c, box = PPP._region_canvas(T, hd, HWR['hood'], size=64)
        u, v = c.tu, c.tv
        c.put(v < .14, hd, -1)                                           # where the hood lies on the shoulders
        c.put((np.abs(u - .5) < .17) & (v > .26) & (v < .90), hd, 1)     # rim of the face opening
        c.dither(v > .80, np.clip((v - .80) / .2, 0., 1.) * .6, hd, 1)   # crown
        c.put(np.abs(u - 0.) < .03, hd, -1); c.put(np.abs(u - 1.) < .03, hd, -1)      # back seam
        _store(pack, hair, c, box)
        c, box = PPP._region_canvas(T, hd, HWR['lining'], size=64)
        c.put(np.ones(c.u.shape, dtype=bool), hd, -2)
        _store(pack, hair, c, box)
    if style['visor'] == 'glasses':
        fc = paint['frame_color'] or 'k_0'; lc = paint['lens_color'] or 'off_white'
        c, box = PPP._region_canvas(T, fc, HWR['lens'], size=64)
        for uc in (.25, .75):
            x = (c.u - (.04 + .92 * uc)) / (.92 * .21); y = (c.v - .5) / (.92 * .42)
            d = np.hypot(x, y)
            c.put(d < .74, lc)
            c.put((d < .74) & (y > .25) & (x * (1 if uc < .5 else -1) < -.1), lc, 1)      # glint, mirrored
        _store(pack, hair, c, box)
        c, box = PPP._region_canvas(T, fc, HWR['frame'], size=64)
        _store(pack, hair, c, box)
    elif style['visor'] in ('wedge', 'band') and paint['visor_stripe']:
        for name in ('visor_front', 'visor_edge'):
            _swap(pack, T, hair, HW[name], VISOR_STRIPE_SRC, paint['visor_stripe'], 64)
    return cloth, face, hair
