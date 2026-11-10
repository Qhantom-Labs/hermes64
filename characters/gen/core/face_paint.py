"""Painted face cells for face-head people v2 (round 7+).

One 64x64 cell per expression, painted in the fixed canonical face UV space of core/people.py.
Style target: serious N64-era painted faces (study of the young-hero reference, nothing copied):
almond eyes with a heavy upper lid and crease, iris tucked under the lid, tapered brows, a nose
drawn with a flank shadow + nostrils, a mouth with lip planes; skin planes as solid painted shapes
with ordered-dither only on transition bands. Every texel is a palette colour or a 2-colour mix.
"""
import math
import numpy as np

try:
    from . import people as PP
except ImportError:  # pragma: no cover
    import importlib.util as _iu
    import pathlib as _pl
    _s = _iu.spec_from_file_location('people', _pl.Path(__file__).with_name('people.py'))
    PP = _iu.module_from_spec(_s); _s.loader.exec_module(PP)

L = PP.FACE_LAYOUT
_JAW = sorted(PP._FACE_UV[(1, j)] for j in range(3, 8))
_JAW_U = [q[0] for q in _JAW]
_JAW_V = [q[1] for q in _JAW]
_HALF = sorted((PP._FACE_UV[(k, 7)][1], PP._FACE_UV[(k, 7)][0] - .5) for k in range(4))
_HALF_V = [q[0] for q in _HALF]
_HALF_U = [q[1] for q in _HALF]


def _hash2(x, y, s=0):
    return np.modf(np.sin(x * 12.9898 + y * 78.233 + s * 37.719) * 43758.5453)[0] % 1.0


def jaw_v(u):
    return np.interp(u, _JAW_U, _JAW_V)


def half(v):
    return np.interp(v, _HALF_V, _HALF_U)


def paint_cell(c, pack, p, C, expr):
    """Paint one expression into Canvas `c` (64x64). C = resolved colour names."""
    T = c.t
    u, v = c.u, c.v
    sk = C['skin']
    # round 9: no ordered dither on faces. Every soft transition becomes a solid painted plane (alpha >= .5);
    # bilinear filtering softens the plane edges at runtime. Kills the checker "noise" seen in close-ups.
    _put = c.put
    _canvas = c

    class _Solid:
        def __getattr__(self, name):
            return getattr(_canvas, name)

        @staticmethod
        def put(mask, name, k=0):
            _put(mask, name, k)

        @staticmethod
        def dither(mask, alpha, name, k=0):
            a = np.broadcast_to(np.asarray(alpha, float), mask.shape)
            _put(mask & (a >= .5), name, k)
    c_solid = _Solid()
    c, c_canvas = c_solid, c
    hl, sh, dp, ln = T(sk, 1), T(sk, -1), T(sk, -2), T(sk, -3)
    line = pack.get('face_line', T(sk, -4))
    age = p['age']; child = age == 'child'; elder = age == 'elder'
    wr = max(p['wrinkles'], .8 if elder else 0.)
    d = np.abs(u - .5) / np.maximum(half(v), 1e-3)
    jaw = jaw_v(u)
    eye_v, brow_v, nose_v, mouth_v = L['eye_v'], L['brow_v'], L['nose_v'], L['mouth_v']
    du = L['eye_du'] + (.008 if child else 0) + .016 * p.get('eye_spacing', 0.)     # round 13: eye spacing
    etilt = .014 * p.get('eye_tilt', 0.)                                             # outer corners up (+) / down
    brr = p.get('brow_ridge', 0.)
    face = v > jaw
    # ---------------- skin planes
    # round 17: only a thin shadow edge on the face outline (the wide sh/dp side planes - ember/berry on glow_0 skin -
    # wrapped onto the low-poly head sides as red/magenta cheek bars; the baked vertex light shades the sides)
    c.put(face & (d >= .96) & (d < 1.06) & (v < .8) & (np.abs(u - .5) < .40), sh)   # thin edge band only (the face mask runs past the oval; no horizontal run at the sides)
    c.dither(face & (v > .86) & (d > .62), np.clip((d - .62) / .25, 0, 1) * np.clip((v - .86) / .1, 0, 1), sh)
    for s in (-1, 1):
        hol = ((u - (.5 + s * .25)) / .075) ** 2 + ((v - (nose_v - .02)) / .07) ** 2
        # round 16: cheek hollows only on elders (on glow_0 skins the shadow step is ember: solid red cheek patches);
        # no cheekbone highlight bar (a thin white bar under each eye read as a stripe)
        pass                                   # round 17: no cheek hollows (solid squares at 64 px)
    c.dither(face & (np.abs(u - .5) < .03) & (v > eye_v + .06) & (v < .97), .45, hl)
    neck = ~face
    c.put(neck & (v < jaw + .02) & (np.abs(u - .5) < .30), sh)   # round 17: throat shadow only; the outer columns stay skin
    c.put(neck & (v > jaw - .035) & (np.abs(u - .5) < .24), dp)
    c.dither(neck & (v > jaw - .07) & (v <= jaw - .035) & (np.abs(u - .5) < .2), .5, dp)
    c.put(face & (v < jaw + .018) & (d > .45), sh)
    chin = ((u - .5) / .045) ** 2 + ((v - (L['v_chin'] + .045)) / .025) ** 2
    c.put(face & (chin < 1), hl)
    # ---------------- eyes
    ew = .094 if child else .088
    eh = {'narrow': .040, 'almond': .046, 'round': .058}[p['eye_shape']]     # round 13: smaller adult openings (serious)
    if child:
        eh += .010
    if elder:
        eh *= .9
    ir = .056 if child else .047          # larger than the opening: clipped by both lids (serious, not startled)
    if expr == 'surprised':
        eh *= 1.3
    gaze = p['gaze'] * .022
    for s in (-1, 1):
        ex = .5 + s * du; ey = eye_v
        t = (u - ex) / ew * s                  # -1 inner corner .. +1 outer corner
        span = np.abs(t) <= 1
        droop = -.010 if elder else .006
        tilt_up = droop * t + etilt * t
        if expr == 'worried':
            tilt_up = -.016 * t
        top = ey + eh * np.clip(1 - t * t, 0, 1) ** .6 + tilt_up
        bot = ey - eh * (.55 if expr != 'smile' else .22) * np.clip(1 - t * t, 0, 1) ** .8 + .004 * t
        if expr == 'sleepy':
            top = np.minimum(top, ey + eh * .12 + tilt_up)
        # socket: soft shadow from the brow down to the lid crease
        sock = span & (v > top) & (v < brow_v - .015) & (np.abs(t) < 1.15)
        c.dither(sock, np.clip((v - top) / (brow_v - top + 1e-3), 0, 1) * .25 + .35 + .2 * brr, sh)
        if brr > .45:                        # round 13: heavy brow ridge - deep-set eyes, dark band under the brow
            c.put(span & (np.abs(t) < 1.05) & (v > top + .03) & (v < brow_v - .02), dp)
        if expr == 'blink':
            arc = ey - .004 - .012 * np.clip(1 - t * t, 0, 1)
            c.put((np.abs(t) < 1.05) & (np.abs(v - arc) < .016), line)
            c.put((np.abs(t) < .9) & (v > arc + .016) & (v < arc + .05), sh)
            if p['lashes']:
                c.put((t > .75) & (t < 1.25) & (np.abs(v - (arc + .012 + .02 * (t - .75))) < .01), line)
            continue
        eye = span & (v < top) & (v > bot)
        c.put(eye, pack.get('eye_white', 'white'))
        c.put(eye & (v > top - .022), sh)                                 # lid shadow on the white
        ix = ex + gaze - s * .006; iy = ey + .006 + (.004 if expr == 'surprised' else 0)
        rr = ((u - ix) / ir) ** 2 + ((v - iy) / (ir * 1.05)) ** 2
        iris = eye & (rr < 1)
        c.put(iris, C['eye_color'])
        c.put(iris & (v > iy + ir * .25), C['eye_color'], -1)
        c.put(iris & (v < iy - ir * .45) & (rr > .25), C['eye_color'], 1)
        c.put(eye & (rr < .19), line)
        hlx = ((u - (ix - s * 0 - ir * .38)) / .012) ** 2 + ((v - (iy + ir * .38)) / .012) ** 2
        if child or p['eye_shape'] == 'round':     # round 13: no glint on adult narrow/almond eyes (less cute)
            c.put(eye & (hlx < 1), pack.get('eye_glint', 'white'))
        # heavy upper lid, thicker at the outer end, small wing past the corner
        lw = .032 + .014 * np.clip(t, 0, 1)
        c.put((t > -1.05) & (t < 1.12) & (v >= top - .004) & (v < top + lw), line)
        c.put((t >= 1.0) & (t < 1.3) & (v > top - .004 - .03 * (t - 1)) & (v < top + .02), line)
        if not child:
            crease = top + .05 + .004 * (1 - t * t)
            c.put((t > -.55) & (t < .95) & (np.abs(v - crease) < .009), sh if not elder else dp)
        c.put((t > -.35) & (t < 1.0) & (v < bot + .004) & (v > bot - .014), dp)   # lower lash line
        if p['lashes']:
            for k in range(2):
                tx = .62 + .22 * k
                c.put((np.abs(t - tx) < .07) & (v > top + lw - .004) & (v < top + lw + .03), line)
        if wr > .3:
            bag = bot - .035 - .008 * np.clip(1 - t * t, 0, 1)
            c.put((t > -.5) & (t < .8) & (np.abs(v - bag) < .007), sh)
            for k in range(3):
                yy = ey + .016 - k * .022
                c.put((t > 1.2) & (t < 1.6) & (np.abs(v - (yy - .03 * (t - 1.2))) < .006), sh)
        if expr == 'smile':
            c.put((t > -.6) & (t < .9) & (np.abs(v - (bot - .02)) < .007), sh)
    # ---------------- brows
    thick0 = {'straight': .048, 'heavy': .062, 'thin': .032, 'arched': .044}[p['brows']]
    arch = {'straight': .3, 'heavy': .2, 'thin': .6, 'arched': 1.0}[p['brows']]
    tilt = p['brow_tilt']; lift = .02 * p.get('brow_height', 0.)
    bgap = .02 * p.get('brow_gap', 0.)
    if expr == 'worried':
        tilt = -.95; lift = .004
    elif expr == 'surprised':
        lift += .048; tilt = -.15; arch = max(arch, .8)
    elif expr == 'smile':
        lift += .006; tilt = min(tilt, .2)
    elif expr == 'sleepy':
        lift -= .006; tilt = .05
    for s in (-1, 1):
        x0 = .5 + s * (.072 + bgap); x1 = .5 + s * (.288 + .4 * bgap)
        t = (u - x0) / (x1 - x0)
        span = (t >= 0) & (t <= 1)
        mid = brow_v + lift - tilt * .034 * (1 - t) + .02 * arch * np.sin(np.clip(t, 0, 1) * math.pi) + .006 * t
        th = thick0 * (1.25 - .75 * t)
        b = span & (np.abs(v - mid) < th / 2)
        c.put(b, C['brow_color'])
        c.put(b & (v < mid - th * .15), C['brow_color'], -1)
        c.put(span & (t < .85) & (v < mid - th / 2) & (v > mid - th / 2 - .014), sh)
    if expr == 'worried' or (p['brow_tilt'] > .55 and expr not in ('surprised', 'smile')):
        c.put((np.abs(u - .5) < .011) & (v > brow_v - .045) & (v < brow_v + .005), sh)
    # ---------------- nose
    nsh = p.get('nose_shape', 'straight')
    nw = (.85 if child else 1.) * {'straight': 1., 'broad': 1.35, 'hooked': .95, 'button': .9}[nsh]
    ftop = eye_v - .02 if nsh != 'button' else nose_v + .1
    c.put((u > .5 + .010 * nw) & (u < .5 + .030 * nw) & (v > nose_v + .045) & (v < ftop), sh)   # flank line
    c.put((u > .5 + .016 * nw) & (u < .5 + .052 * nw) & (v > nose_v - .004) & (v < nose_v + .045), sh)  # wing
    if nsh == 'hooked':                      # round 13: bridge bump shadow + dark under the drooping tip
        c.put((u > .5 + .004) & (u < .5 + .03) & (v > nose_v + .1) & (v < nose_v + .14), dp)
        c.put((np.abs(u - .5) < .03) & (v > nose_v - .03) & (v < nose_v - .012), dp)
    if nsh == 'broad':
        for s in (-1, 1):
            c.put((np.abs(u - (.5 + s * .06)) < .012) & (v > nose_v - .002) & (v < nose_v + .03), dp)
    c.dither((u > .5 - .05 * nw) & (u <= .5 - .016 * nw) & (v > nose_v - .004) & (v < nose_v + .04), .5, sh)
    c.put((np.abs(u - .5) < .05 * nw) & (v > nose_v - .022) & (v < nose_v - .004), sh)              # under-nose
    for s in (-1, 1):
        c.put((np.abs(u - (.5 + s * .026 * nw)) < .011) & (np.abs(v - (nose_v + .004)) < .009), dp)
    c.put((u > .5 - .016) & (u < .5 + .004) & (v > nose_v + .05 - (.02 if nsh == 'button' else 0)) & (v < nose_v + .085), hl)  # tip light
    c.put((u > .5 - .013) & (u < .5 - .002) & (v > nose_v + .09) & (v < eye_v - .03), hl)            # bridge light
    if not child:
        c.put((np.abs(u - .5) < .007) & (v > mouth_v + .035) & (v < nose_v - .025), sh)               # philtrum
    if wr > .5:
        for s in (-1, 1):
            tt = np.clip((v - (mouth_v - .01)) / (nose_v - mouth_v + .01), 0, 1)
            fu = .5 + s * (.115 - .055 * tt)
            c.put((v > mouth_v - .02) & (v < nose_v + .01) & (np.abs(u - fu) < .009), sh)
        pass                                   # round 17: no jowl line (read as a horizontal cheek stripe)
    # ---------------- skin marks
    if p['freckles']:                      # single texels must be solid palette colours (never a 2-colour mix)
        n = _hash2(c.x, c.y, 3)
        fr = (n < .07) & (v > nose_v + .03) & (v < eye_v - .05) & (np.abs(u - .5) < .25) & (np.abs(u - .5) > .04)
        c.put(fr & face, sh.split('+')[0])
    if child:
        for s in (-1, 1):
            bl = ((u - (.5 + s * .2)) / .07) ** 2 + ((v - (nose_v - .01)) / .04) ** 2
            c.dither(face & (bl < 1), (1 - bl) * .8, pack.get('blush', sh))
    # ---------------- beard (under the mouth)
    beard = p['beard']; bc = C['hair_color']
    if beard != 'none':
        aw = np.abs(u - .5)
        jawband = face & (d > .5) & (v < eye_v - .14 - .1 * np.clip(.85 - d, 0, 1))
        chinr = face & (v < mouth_v + .01) & (aw < .25)
        region = jawband | chinr
        if beard == 'full':
            region = face & (v < eye_v - .1 - .16 * np.clip(.9 - d, 0, 1)) & ~((aw < .09) & (v > mouth_v + .055))
        if beard == 'moustache':
            region = np.zeros_like(face)
        if beard == 'stubble':
            # round 12: stubble = a solid shadow plane over the jaw with a sparse hair-colour grain only along
            # its lower edge (single random texels over the whole jaw read as grey frost/noise)
            n = _hash2(c.x, c.y, 11)
            stub = region & ((v < mouth_v - .03) | (d > .55))
            c.put(stub, sh)                  # round 15: solid shadow plane only (the grain read as dirt dots)
        else:
            c.put(region, bc)
            n = _hash2(c.x, c.y, 13)
            c.put(region & (n < .3), bc, -1)
            c.put(region & (n > .82) & (v > jaw), bc, 1)
            c.put(region & (v < jaw + .02), bc, -1)
        if beard in ('full', 'moustache', 'short'):
            aw = np.abs(u - .5)
            mo = (aw < .13) & (aw > .007) & (v > mouth_v + .012 - .032 * (aw / .13) ** 2) & (v < mouth_v + .058 - .022 * (aw / .13))
            c.put(mo, bc)
            c.put(mo & (v < mouth_v + .022 - .032 * (aw / .13) ** 2), bc, -1)
            c.put(mo & (_hash2(c.x, c.y, 17) > .78), bc, 1)
    # ---------------- mouth
    mw = {'neutral': .098, 'thin': .09, 'full': .104}[p['mouth']] * (.78 if child else 1.) * (1 + .14 * p.get('mouth_width', 0.))
    lip = C['lip_color']
    t = (u - .5) / mw
    span = np.abs(t) <= 1
    if expr in ('talk_a', 'talk_b', 'surprised'):
        oh = {'talk_a': .030, 'talk_b': .046, 'surprised': .046}[expr]
        ow = {'talk_a': .72, 'talk_b': .86, 'surprised': .48}[expr]
        oy = mouth_v - oh * .35
        r = (t / ow) ** 2 + ((v - oy) / oh) ** 2
        c.put(r < 1.5, lip)
        c.put((r < 1.5) & (v > oy + oh * .6), lip, -1)
        c.put(r < 1, line)
        if expr == 'talk_b':
            c.put((r < 1) & (v > oy + oh * .45), pack.get('teeth', 'white'))
        c.put((r >= 1.5) & (r < 2.6) & (v < oy - oh), sh)
    else:
        bend = {'smile': .018, 'worried': -.016}.get(expr, -.008)
        my = mouth_v + bend * t * t
        if expr == 'worried':
            my = my + .004 * np.sin(t * 5)
        full = p['mouth'] == 'full'
        if full:
            c.put(span & (np.abs(t) < .9) & (v > my + .010) & (v < my + .022), lip, -1)                     # upper lip
        c.put(span & (np.abs(v - my) < .009), line)                                                         # mouth line
        if full:
            c.put(span & (np.abs(t) < .7) & (v < my - .009) & (v > my - .032), lip)                         # lower lip
            c.put((np.abs(t) < .32) & (v < my - .013) & (v > my - .022), lip, 1)
        else:
            c.put(span & (np.abs(t) < .55) & (v < my - .009) & (v > my - .022), sh)                         # lower-lip shade
            c.dither(span & (np.abs(t) < .45) & (v <= my - .022) & (v > my - .034), .5, hl)
        c.put((np.abs(t) < .5) & (v <= my - .034) & (v > my - .048), sh)                                   # under-lip
        for s in (-1, 1):
            c.put((np.abs(u - (.5 + s * mw * 1.04)) < .009) & (np.abs(v - (my + (.006 if expr == 'smile' else 0))) < .012), dp)
        if expr == 'smile':
            for s in (-1, 1):
                c.put((np.abs(u - (.5 + s * mw * 1.25)) < .009) & (v > my - .01) & (v < my + .03), sh)
    if p.get('mole'):                        # round 13: one solid mark, side follows the hair part
        mx = .5 - .19 * (1 if p['part'] >= 0 else -1); my_ = nose_v - .05
        c.put(face & (np.abs(u - mx) < .014) & (np.abs(v - my_) < .014), dp)
    if p['scar']:
        sx = .5 + .175 * (1 if p['part'] >= 0 else -1)
        sc = np.abs((u - sx) - (v - eye_v) * .3) < .009
        c.put(sc & (((v > eye_v + .06) & (v < brow_v + .05)) | ((v < eye_v - .05) & (v > eye_v - .13))), hl)
    # ---------------- painted leaf mark on the wearer's-left cheek (visor cameo only)
    if p.get('cheek_leaf'):
        lc = pack.get('cheek_leaf', C['accent_color'])
        for cu, cv, ang, sz in ((.70, .55, .9, .055), (.765, .60, .45, .042)):
            du = u - cu; dv = v - cv
            a_ = (du * math.cos(ang) + dv * math.sin(ang)) / sz
            b_ = (-du * math.sin(ang) + dv * math.cos(ang)) / (sz * .42)
            leaf = face & (a_ * a_ + b_ * b_ < 1)
            c.put(leaf, lc)
            c.put(leaf & (np.abs(b_) < .25) & (a_ > -.7), lc, -1)
    # ---------------- patches for back-of-head and ear faces
    sp = PP.SKIN_PATCH; ep = PP.EAR_PATCH
    c.put((u > sp[0] - .02) & (u < sp[2] + .02) & (v > sp[1] - .02) & (v < sp[3] + .02), sk)
    em = (u > ep[0] - .015) & (u < ep[2] + .015) & (v > ep[1] - .015) & (v < ep[3] + .015)
    c.put(em, sk)
    c.put(em & (np.abs(u - (ep[0] + ep[2]) / 2) < .03) & (np.abs(v - (ep[1] + ep[3]) / 2) < .04), sh)
    return c_canvas
