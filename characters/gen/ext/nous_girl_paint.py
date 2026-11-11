"""Paint of nous_girl (lane CAST2): her own palette pack and three atlases. Nothing here is read from an image file.

PACK      her character palette (inline pack 'cast2_nous_girl'). The eight greys of the vertex light ramp are the hero
          pack's, so the baked light steps are the same as on the hero; every other colour is authored here.
costume   128 x 128, the region layout of the base family (core/people.REGIONS). Jacket with white stripes: two rings
          round the hem, two rings round the collar wall, two lines down the outside of each sleeve, a centre zip line.
          Shorts over leggings (LEGS = 'bare' paints skin below the shorts), light boots, bare hands.
face      256 x 128, 8 expression cells: the shared face painter with the hero's lower-face delta, then the eyes are
          repainted larger (EYE) with a thick upper lash and one highlight texel block.
hair      64 x 64 for the bob: strand lines, a lighter band round the crown, dark texels for the inner wall.

No logo, star, wordmark or text is painted anywhere: every mark is a ring, a line or a plain block of one tone.
"""
import numpy as np

from . import face_paint as FP
from . import paint as P0
from . import people as PP
from . import people_paint as PPP

PACK_ID = 'cast2_nous_girl'
_PAL = [
    ('k_0', '#121216'), ('k_1', '#1f1f25'), ('near_black', '#3a393f'), ('k_3', '#55545c'), ('grey_0', '#74747c'),
    ('grey_1', '#9a9aa2'), ('ow_0', '#b3aea7'), ('off_white', '#dcd7d1'), ('white', '#f6f3ee'),
    ('hair_0', '#15121c'), ('hair_1', '#211c2d'), ('hair', '#2e2740'), ('hair_3', '#453b5e'), ('hair_4', '#6a5f87'),
    ('jk_0', '#191822'), ('jk_1', '#262533'), ('jacket', '#353449'), ('jk_3', '#4b4a66'),
    ('vi_0', '#2e1f4d'), ('vi_1', '#47307a'), ('violet', '#6846ad'), ('vi_3', '#8d6fd0'), ('vi_4', '#b9a4e8'),
    ('st_0', '#a9a8b8'), ('st_1', '#cfcedb'), ('stripe', '#efeef4'),
    ('skin_0', '#8f5d58'), ('skin_1', '#c98f80'), ('skin_2', '#e3b09b'), ('skin', '#f3ceba'), ('skin_3', '#fce8dc'),
    ('blush', '#eeaa9f'),
]
PACK = {
    'id': PACK_ID, 'version': '0.1.0', 'kind': 'character_palette',
    'note': 'Palette of the CAST2 captive girl. Authored values; the 8 light-ramp greys equal the hero pack.',
    'palette_names': [n for n, _ in _PAL], 'palette': [c for _, c in _PAL],
    'ramps': {'black': ['k_0', 'k_1', 'near_black', 'k_3', 'grey_0', 'grey_1'], 'white': ['ow_0', 'off_white', 'white'],
              'hair': ['hair_0', 'hair_1', 'hair', 'hair_3', 'hair_4'], 'jacket': ['jk_0', 'jk_1', 'jacket', 'jk_3'],
              'violet': ['vi_0', 'vi_1', 'violet', 'vi_3', 'vi_4'], 'stripe': ['st_0', 'st_1', 'stripe'],
              'skin': ['skin_0', 'skin_1', 'skin_2', 'skin', 'skin_3']},
    'char_ramps': {},
    'skin_ramps': {'skin': ['skin_0', 'skin_1', 'skin_2', 'skin', 'skin_3']},
    'light_ramp': ['k_1', 'near_black', 'k_3', 'grey_0', 'grey_1', 'ow_0', 'off_white', 'white'],
    'face_defaults': {'skin': 'skin', 'hair_color': 'hair', 'eye_color': 'vi_1', 'brow_color': 'hair_1', 'lip_color': 'skin_1',
                      'top_color': 'jacket', 'garment_color': 'jacket', 'trim_color': 'stripe', 'accent_color': 'violet',
                      'bottom_color': 'violet', 'boot_color': 'st_1', 'glove_color': 'skin', 'belt_color': 'jk_0',
                      'collar_color': 'jacket', 'extra_color': 'stripe', 'extra_color_2': 'jk_1'},
    'eye_white': 'white', 'eye_glint': 'white', 'face_line': 'k_0', 'teeth': 'off_white', 'sole': 'k_1', 'blush': 'blush',
    'cheek_leaf': 'violet',
    'prop_colors': {'body': 'stripe', 'dark': 'jk_0', 'light': 'white', 'metal': 'st_0', 'glass': 'vi_3', 'accent': 'violet',
                    'cloth': 'jacket', 'wood': 'k_3'},
}
LEGS = 'leggings'            # 'leggings' (dark, the default) or 'bare' (skin below the shorts)
SHORTS_V = .62               # trouser region tv above which the shorts are painted (tv 1 = hip ring, 0 = ankle ring)
STRIPE_HEM = ((.07, .13), (.19, .25))          # torso tv bands (tv 0 = hem ring, 1 = top ring)
STRIPE_COLLAR = ((.66, .74), (.84, .92))       # collar region tv bands on the outer wall (see tall_v3.COLLAR_V)
STRIPE_SLEEVE = ((.665, .715), (.785, .835))   # sleeve tu bands (the outside of the arm is tu .75)
ZIP_HALF = .012                                # torso tu half width of the centre line (front = tu .5)
# eyes, in face-cell uv (64 x 64 texels per cell): centre offset from the face centre line, centre v, half sizes
EYE = {'du': .170, 'v': .745, 'rx': .092, 'ry': .082, 'iris_rx': .060, 'iris_ry': .072, 'lash': .034}
EYE_CLEAR = (.118, .635, .862)                 # half width, v0, v1 of the block returned to plain skin before painting
EYES = {'neutral': 'open', 'blink': 'closed', 'talk_a': 'open', 'talk_b': 'open', 'smile': 'open', 'worried': 'open',
        'surprised': 'wide', 'sleepy': 'half'}


def _q(pack, img):
    return P0.quantize(img, P0.palette(pack))


def costume_atlas(pack, p):
    T = PPP.Tones(pack)
    C = PPP._colors(pack, p)
    g, tr = C['garment_color'], C['trim_color']
    out = np.zeros((128, 128, 3))
    out[:] = P0.color(pack, g)

    def region(name, base):
        c, box = PPP._region_canvas(T, base, PP.REGIONS[name])
        return c, box

    def done(c, box):
        out[box[2]:box[3], box[0]:box[1]] = c.img
    # ---- torso: jacket
    c, box = region('torso', g)
    u, v = c.tu, c.tv
    c.put(v < .045, g, -1)                                          # hem edge
    for lo, hi in STRIPE_HEM:
        c.put((v >= lo) & (v < hi), tr)
    c.put((v > .30) & (v < .36), g, -1)                             # waist shadow
    c.put((v > .62) & (v < .70) & (np.abs(u - .5) < .20), g, 1)     # light across the chest
    c.put((np.abs(u - .5) < ZIP_HALF) & (v > .25), g, -2)           # centre line
    c.put(v > .955, g, -1)                                          # under the collar
    done(c, box)
    # ---- sleeve
    c, box = region('sleeve', g)
    u, v = c.tu, c.tv
    c.put((v > .47) & (v < .53), g, -1)                             # elbow crease (under the stripes)
    for lo, hi in STRIPE_SLEEVE:
        c.put((u >= lo) & (u < hi) & (v > .10), tr)
    c.put(v < .10, g, -1)                                           # cuff
    done(c, box)
    # ---- collar: outer wall on top (stripes), lining below
    c, box = region('collar', C['collar_color'])
    v = c.tv
    outer = v >= .55
    for lo, hi in STRIPE_COLLAR:
        c.put((v >= lo) & (v < hi), tr)
    c.put(outer & (v < .62), g, -1)                                 # shadow at the jacket seam
    c.put(~outer, g, -2)                                            # lining
    c.put(~outer & (v > .30), g, -1)
    done(c, box)
    # ---- legs: shorts over leggings (or skin)
    bc = C['bottom_color']
    leg = C['skin'] if LEGS == 'bare' else C['extra_color_2']
    c, box = region('trouser', leg)
    v = c.tv
    c.put(v >= SHORTS_V, bc)
    c.put((v >= SHORTS_V) & (v < SHORTS_V + .06), bc, -1)           # shorts hem
    c.put(v > .93, bc, -1)                                          # under the jacket
    if LEGS != 'bare':
        c.put((v > .40) & (v < .46), leg, 1)                        # knee light
    done(c, box)
    # ---- boots
    c, box = region('boot', C['boot_color'])
    v = c.tv
    c.put(v < .16, pack['sole'])
    c.put((v > .16) & (v < .24), C['boot_color'], -1)
    c.put((v > .86), C['accent_color'])                             # cuff ring
    done(c, box)
    # ---- hands: bare
    c, box = region('mitt', C['skin'])
    c.put(c.tv > .90, C['skin'], -1)                                # wrist shadow under the cuff
    done(c, box)
    return _q(pack, out)


def _eye(c, pack, T, C, side, mode):
    """One eye into cell canvas c (c.u, c.v in 0..1 of the cell). side -1 = image left."""
    e = EYE
    cu = .5 + side * e['du']; cv = e['v']
    u, v = c.u, c.v
    dx = (u - cu); dy = (v - cv)
    white = (dx / e['rx']) ** 2 + (dy / e['ry']) ** 2 <= 1.
    lash_c = 'k_0'
    if mode == 'closed':
        arc = cv - .030 + .030 * (dx / e['rx']) ** 2
        c.put((np.abs(dx) <= e['rx']) & (np.abs(v - arc) < .017), lash_c)
        return
    k = {'open': 1., 'wide': .84, 'half': 1.}[mode]
    iris = (dx / (e['iris_rx'] * k)) ** 2 + ((dy + .006) / (e['iris_ry'] * k)) ** 2 <= 1.
    c.put(white, pack['eye_white'])
    c.put(white & (dy > e['ry'] * .45), 'st_1')                     # shade under the lash
    c.put(white & iris, C['eye_color'], -1)
    c.put(white & iris & (dy < -.020 * k), C['eye_color'], 1)       # lighter lower iris
    c.put(white & iris & (dy < -.048 * k), C['eye_color'], 2)
    pupil = (dx / (e['iris_rx'] * .50 * k)) ** 2 + ((dy - .004) / (e['iris_ry'] * .55 * k)) ** 2 <= 1.
    c.put(white & pupil, lash_c)
    c.put(white & (dx > -.050) & (dx < -.018) & (dy > .012) & (dy < .046), pack['eye_glint'])   # one block, upper left
    top = cv + (e['ry'] * (.25 if mode == 'half' else 1.))
    if mode == 'half':
        lid = dy > e['ry'] * .25
        c.put(white & lid, C['skin'])
        c.put((np.abs(dx) <= e['rx'] * 1.04) & (np.abs(v - top) < .018), lash_c)
        return
    outer = (dx / (e['rx'] * 1.10)) ** 2 + ((dy - e['lash'] * .5) / (e['ry'] * 1.06)) ** 2 <= 1.
    c.put(outer & ~white & (dy > e['ry'] * .18), lash_c)            # thick upper lash
    tick = (side * dx > e['rx'] * .86) & (side * dx < e['rx'] * 1.22) & (dy > e['ry'] * .30) & (dy < e['ry'] * .62)
    c.put(tick, lash_c)                                             # outer corner
    low = (dx / e['rx']) ** 2 + ((dy + .012) / e['ry']) ** 2 <= 1.
    c.put(white & ~low, C['skin'], -1)                              # lower lid line


def face_atlas(pack, p, lower_face):
    """lower_face = ext/tall_v3_paint._lower_face (the hero's plain jaw / painted mouth delta)."""
    T = PPP.Tones(pack)
    C = PPP._colors(pack, p)
    face = lower_face(pack, T, C, PPP.face_atlas(pack, p))
    out = np.array(face, copy=True)
    hw, v0, v1 = EYE_CLEAR
    for cell, expr in enumerate(PP.EXPRESSIONS):
        c = PPP.Canvas(T, 64, 64, C['skin'])
        keep = np.ones((64, 64), dtype=bool)
        for side in (-1, 1):
            keep &= ~((np.abs(c.u - (.5 + side * EYE['du'])) < hw) & (c.v > v0) & (c.v < v1))
        blush = ((c.u - .5) ** 2 / .30 ** 2 + (c.v - .56) ** 2 / .045 ** 2 <= 1.) & (np.abs(c.u - .5) > .14)
        c.put(blush, pack['blush'])
        for side in (-1, 1):
            _eye(c, pack, T, C, side, EYES[expr])
        y0 = (1 - cell // 4) * 64; x0 = (cell % 4) * 64
        px = out[y0:y0 + 64, x0:x0 + 64]
        new = _q(pack, c.img)
        mask = ~keep | blush
        px[mask] = new[mask]
    return out


def hair_texture(pack, p, V=None):
    """64 x 64. v levels as ext/nous_girl.BOB_V: hem .30, fringe edge .585, ring C .66, crown top .97."""
    T = PPP.Tones(pack)
    h = PPP._colors(pack, p)['hair_color']
    c = PPP.Canvas(T, 64, 64, h)
    u, v = c.u, c.v
    c.put(np.floor(c.x) % 5 == 2, h, -1)                            # strands
    c.put((v > .705) & (v < .775), h, 1)                            # light band round the crown
    c.put((v > .725) & (v < .755) & (np.floor(c.x) % 5 != 2), h, 2)
    c.put((v > .585) & (v < .615), h, -1)                           # fringe edge
    c.put((v > .30) & (v < .335), h, -1)                            # hem edge
    c.put(v < .26, h, -2)                                           # inner wall, underside of the fringe
    return _q(pack, c.img)
