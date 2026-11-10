"""Painted textures for the mechanical family (lane CHARSYS). numpy only; every texel quantised to the pack palette.

Same rules as the cast and the enemies: art is painted by palette ROLE (core/roles.py binding or intent fallback),
value changes are painted shapes in ramp steps with 4x4 ordered dither (core/combat_paint.Painter), never raw
gradients, never text or logos.

coat_atlas(pack, roles, p) -> 128x128, a 4x4 grid of 32 px tiles (ext/robots.tube tiles):
  0 hull     shell lit from above, two panel seams with rivets, a hazard band low on the hull (accent role), scuffs
  1 head     cap shell, a seam ring, darker rim toward the visor band
  2 arms     shell with dark joint rings at the elbow
  3 hands    dark grip rubber with lit knuckle plates
  4 legs     ribbed dark joint sleeve with a lit shin plate
  5 feet     shell with a dark sole band
  6 pods     shoulder domes / backpack / ear pods: shell, one hazard stripe, rivets
  7 small    antenna, vents, vanes: dark stem, glowing tip
face_atlas(pack, roles, p) -> 256x128, 4x2 cells of 64 px in core/people.EXPRESSIONS order (so the runtime's blink
  and talk cell swaps work): 0 calm, 1 dim (blink), 2 talk_a, 3 talk_b, 4 bright, 5 hurt, 6 flare (telegraph /
  attack), 7 off (death). Cell c sits at column c % 4, row c // 4 counted from the BOTTOM (UV v up).
crown_texture / emblem: the boss crown (attachment) and the chest emblem (paint only): an original abstract mark,
  a ring with three dots and a bar, matching no real company mark.
"""
import math

import numpy as np

try:
    from ..core import paint as P0
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import paint as P0
try:
    from ..core import roles as RL
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import roles as RL
try:
    from ..core.combat_paint import Painter
except ImportError:  # Blender job: characters/gen is on sys.path
    from core.combat_paint import Painter
TAU = 2 * math.pi
ROBOT_ROLE_SPECS = {
    'shell': (.42, 0., .40, None), 'shell_light': (.78, 0., .30, None), 'shell_alt': (.60, .10, .60, None),
    'shell_dark': (.18, 0., .40, None),
    'joint': (.09, 0., .35, None), 'lens': (.82, .35, 1., 45.), 'visor': (.05, 0., .5, None),
    'warning': (.55, .45, 1., 40.), 'emblem': (.62, .35, 1., 15.),
}
for _k, _v in ROBOT_ROLE_SPECS.items():
    RL.ROLE_SPECS.setdefault(_k, _v)
ROLES = list(ROBOT_ROLE_SPECS)
CELLS = {'calm': 0, 'dim': 1, 'talk_a': 2, 'talk_b': 3, 'bright': 4, 'hurt': 5, 'flare': 6, 'off': 7}
CLIP_CELLS = {'telegraph': 6, 'attack': 6, 'attack_sweep': 6, 'attack_slam': 6, 'swing': 6, 'hurt': 5, 'death': 7,
              'recover': 1}


def resolve_roles(pack, bound=None):
    """{role: palette name}: explicit recipe bindings first, then the pack's combat_roles, then intent fallback."""
    roles, fell = RL.resolve(pack, ROLES)
    for k, v in (bound or {}).items():
        if v not in pack['palette_names']:
            raise ValueError('robot role %s bound to off-palette %s' % (k, v))
        roles[k] = v
        if k in fell:
            fell.remove(k)
    return roles, fell


def _tile_grid(N=128):
    y, x = np.mgrid[0:N, 0:N]
    T = N // 4
    u = ((x % T) + .5) / T
    v = 1. - ((y % T) + .5) / T
    tile = (3 - y // T) * 4 + x // T
    return u, v, tile


def _noise(u, v, s):
    return np.sin(u * 17 + v * 13 + s) * .48 + np.sin(u * 39 - v * 23 + s * .7) * .28 + np.sin(u * 71 + v * 59 + s * 1.3) * .13


def _front(u):
    """1 at the front of a vertical loft (u = 0 / 1), 0 at the back (u = .5)."""
    return .5 + .5 * np.cos(TAU * u)


def emblem_mask(x, y):
    """Original abstract mark in a unit square centred at (0, 0) (radius ~1): a ring around a rounded arch (a doorway,
    the threshold motif) standing on a short sill. No letters, no face-like dot layout, matches no real mark."""
    r = np.hypot(x, y)
    ring = (r > .66) & (r < .88)
    arch_out = ((np.abs(x) < .30) & (y < .10) & (y > -.42)) | ((np.hypot(x, y - .10) < .30) & (y >= .10))
    arch_in = ((np.abs(x) < .14) & (y < .10) & (y > -.42)) | ((np.hypot(x, y - .10) < .14) & (y >= .10))
    sill = (np.abs(y + .47) < .06) & (np.abs(x) < .40)
    return ring, (arch_out & ~arch_in) | sill


def _rect_grid(N=128):
    """Per-pixel (local u, local v, part tile) for the robot atlas layout (ext/robots.RECTS, inset like the UVs)."""
    try:
        from .robots import RECTS, _inset
    except ImportError:  # Blender job: characters/gen is on sys.path
        from ext.robots import RECTS, _inset
    y, x = np.mgrid[0:N, 0:N]
    U = (x + .5) / N; V = 1. - (y + .5) / N
    tile = np.full((N, N), -1)
    lu = np.zeros((N, N)); lv = np.zeros((N, N))
    for t, r in RECTS.items():
        u0, v0, u1, v1 = r
        m = (U >= u0) & (U < u1) & (V >= v0) & (V < v1)
        i0, j0, i1, j1 = _inset(r)
        tile[m] = t
        lu[m] = np.clip((U[m] - i0) / (i1 - i0), 0, 1); lv[m] = np.clip((V[m] - j0) / (j1 - j0), 0, 1)
    return lu, lv, tile


def coat_atlas(pack, roles, p, body='walker'):
    N = 128
    u, v, tile = _rect_grid(N)
    P = Painter(pack, roles, N, N)
    wear = float(p.get('wear', .25))
    out = np.zeros((N, N, 3))
    shell = P.ramp('shell_dark', 'shell', 'shell_light')
    alt = P.ramp('shell_dark', 'shell_alt', 'shell_light')
    dark = P.ramp('joint', 'shell_dark')
    hot = P.ramp('shell_dark', 'warning')
    up = np.cos(TAU * u)
    fr = _front(u)
    scuff = (_noise(u * 2.1, v * 1.7, 5.) > (1.15 - .40 * wear))
    # 0 hull: broad painted value (lit shoulders and front, darker belly), one seam with sparse rivets, a hazard band
    val = .40 + .30 * np.clip(v, 0, 1) ** .7 + .12 * fr
    hull = P.paint_ramp(shell, val)
    seam = np.abs(v - .62) < .018
    hull[seam] = P.paint_ramp(shell, val - .28)[seam]
    riv = (np.abs(v - .665) < .016) & (np.abs(((u * 8.) % 1.) - .5) < .045)
    hull[riv] = P.paint_ramp(shell, val + .22)[riv]
    if body == 'floater':
        # nozzle: the narrow underside glows, a dark ring above it, the hazard band higher up
        noz = v < .14
        hull[noz] = P.paint_ramp(P.ramp('shell_dark', 'lens'), .55 + .45 * (1. - v / .14))[noz]
        ring = (v >= .14) & (v < .20)
        hull[ring] = P.paint_ramp(dark, .40 + 0 * u)[ring]
        band = (v > .30) & (v < .37)
    else:
        band = (v > .14) & (v < .22)
        foot = v < .07
        hull[foot] = P.paint_ramp(dark, .45 + .2 * up)[foot]
    stripes = ((u * 12. + v * 3.) % 1.) < .5
    hull[band & stripes] = P.paint_ramp(hot, .9 + 0 * u)[band & stripes]
    hull[band & ~stripes] = P.paint_ramp(dark, .5 + 0 * u)[band & ~stripes]
    if p.get('boss'):
        # chest emblem, front centre (u = 0 wraps): a ring, three dots and a bar on a dark disc
        uu = np.where(u > .5, u - 1., u)
        ex, ey = uu * 7.0, (v - .45) * 3.6
        ring, glyph = emblem_mask(ex, ey)
        disc = np.hypot(ex, ey) < .98
        hull[disc] = P.paint_ramp(dark, .35 + 0 * u)[disc]
        hull[ring & disc] = P.paint_ramp(P.ramp('shell_dark', 'emblem'), .92 + 0 * u)[ring & disc]
        hull[glyph & disc] = P.paint_ramp(shell, .95 + 0 * u)[glyph & disc]
    sc = scuff & (v > .25) & ~seam
    hull[sc] = P.paint_ramp(shell, val - .14)[sc]
    # 1 head cap: lit dome, darker rim toward the visor band (v low), a light catch on top
    hv = .40 + .40 * v + .10 * fr
    head = P.paint_ramp(alt, hv)
    head[v < .09] = P.paint_ramp(dark, .55 + 0 * u)[v < .09]
    head[(v > .78) & (fr > .60)] = P.paint_ramp(alt, .97 + 0 * u)[(v > .78) & (fr > .60)]
    # 2 arms: shell, dark joint rings at the elbow and the cuff
    av = .45 + .30 * up
    arms = P.paint_ramp(shell, av)
    jr = (np.abs(v - .45) < .08) | (v > .92)
    arms[jr] = P.paint_ramp(dark, .40 + .25 * up)[jr]
    # 3 hands: dark grip, lit knuckle plate on the back of the hand
    hands = P.paint_ramp(dark, .32 + .30 * up)
    plate = (up > .1) & (v > .30) & (v < .80)
    hands[plate] = P.paint_ramp(alt, .50 + .35 * up)[plate]
    # 4 legs: shell plating with a ribbed dark knee joint (vanes on the floater: shell with glowing tips)
    lv_ = .45 + .30 * up
    legs = P.paint_ramp(shell, lv_)
    if body == 'floater':
        tip = v > .78
        legs[tip] = P.paint_ramp(P.ramp('shell_dark', 'lens'), .55 + .45 * np.clip((v - .78) / .22, 0, 1))[tip]
        edge = np.abs(np.cos(TAU * u)) > .92
        legs[edge & ~tip] = P.paint_ramp(dark, .45 + 0 * u)[edge & ~tip]
    else:
        knee = np.abs(v - .50) < .09
        legs[knee] = P.paint_ramp(dark, .35 + .20 * up)[knee]
        hip = v < .08
        legs[hip] = P.paint_ramp(dark, .35 + 0 * u)[hip]
    # 5 feet: shell, dark sole band at the bottom (last ring = sole)
    fv = .45 + .30 * (1. - v) + .10 * fr
    feet = P.paint_ramp(alt, fv)
    feet[v > .74] = P.paint_ramp(dark, .30 + 0 * u)[v > .74]
    # 6 pods: shell dome, one hazard stripe, a light catch
    pv = .40 + .40 * v + .08 * up
    pods = P.paint_ramp(alt, pv)
    ps = (np.abs(v - .42) < .07) & (((u * 8.) % 1.) < .5)
    pods[ps] = P.paint_ramp(hot, .9 + 0 * u)[ps]
    # 7 small parts: dark stem, glowing tip toward the end
    small = P.paint_ramp(dark, .35 + .25 * up)
    tp = v > .78
    small[tp] = P.paint_ramp(P.ramp('shell_dark', 'lens'), .6 + .4 * np.clip((v - .78) / .22, 0, 1))[tp]
    planes = {0: hull, 1: head, 2: arms, 3: hands, 4: legs, 5: feet, 6: pods, 7: small}
    for t, img in planes.items():
        m = tile == t
        out[m] = img[m]
    rest = tile < 0
    out[rest] = P.paint_ramp(dark, .3 + 0 * u)[rest]
    return P0.quantize(out, P0.palette(pack))


def face_atlas(pack, roles, p):
    """Visor cells. u across the visor (0 .. 1, .5 straight ahead), v up the head band (0 .. 1)."""
    W, H = 256, 128
    y, x = np.mgrid[0:H, 0:W]
    col = x // 64; row = 1 - y // 64
    cell = row * 4 + col
    u = ((x % 64) + .5) / 64.; v = 1. - ((y % 64) + .5) / 64.
    P = Painter(pack, roles, W, H)
    out = np.zeros((H, W, 3))
    style = p.get('visor', 'twin')
    glass = P.ramp('joint', 'visor', 'shell_dark')
    lamp = P.ramp('visor', 'lens')
    shell = P.ramp('shell_dark', 'shell_alt', 'shell')
    # frame: shell above and below the glass; glass a rounded strip whose height depends on the style
    gh = {'twin': .30, 'band': .20, 'slit': .13, 'grille': .30}[style]
    edge = np.abs(v - .5) / gh
    side = np.clip((np.abs(u - .5) - .40) / .10, 0, 1)
    gl = (edge < 1.) & (np.abs(u - .5) < .47)
    out[:] = P.paint_ramp(shell, .55 + .3 * v)
    gv = .35 + .25 * (v - .5) / gh - .2 * side + .03 * _noise(u, v, 3.)
    out[gl] = P.paint_ramp(glass, gv)[gl]
    rim = (edge >= 1.) & (edge < 1.22) & (np.abs(u - .5) < .49)
    out[rim] = P.paint_ramp(shell, .25 + 0 * u)[rim]
    if style == 'grille':
        gr = gl & (np.abs(((v - .5) / gh * 3.5) % 1. - .5) < .12)
        out[gr] = P.paint_ramp(glass, .05 + 0 * u)[gr]
    ex = {'twin': (.33, .67), 'band': (.36, .64), 'slit': (.38, .62), 'grille': (.34, .66)}[style]
    for c in range(8):
        m = cell == c
        if style == 'band':
            # a lit strip across the glass, brighter points for the eyes
            strip = gl & (np.abs(v - .5) < gh * .35) & m
            lvl = {0: .55, 1: .25, 2: .65, 3: .45, 4: .75, 5: .40, 6: .95, 7: 0.}[c]
            if lvl > 0:
                out[strip] = P.paint_ramp(lamp, lvl * (1. - .4 * np.abs(u - .5)))[strip]
        for cx in ex:
            if c == 7:                                            # off: dark lid lines
                lid = (np.abs(v - .5) < .025) & (np.abs(u - cx) < .07) & m
                out[lid] = P.rgb('joint')
                continue
            rx, ry = {'twin': (.075, .17), 'band': (.06, .09), 'slit': (.05, .055), 'grille': (.07, .15)}[style]
            if c == 1:
                ry *= .25                                         # dim: a narrow line (blink)
            if c == 6:
                rx *= 1.3; ry *= 1.25                              # flare: big hot eyes
            if c == 5:
                ry *= .45                                         # hurt: squeezed
            dy = 0.
            if c == 4:
                dy = .02                                          # bright: lifted
            e = ((u - cx) / rx) ** 2 + ((v - .5 - dy) / ry) ** 2
            core = (e < 1.) & m
            out[core] = P.paint_ramp(lamp, np.clip(1.25 - e * .7, 0, 1))[core]
            hi = (e < .18) & m
            out[hi] = P.paint_ramp(P.ramp('lens', 'shell'), .95 + 0 * u)[hi]
            if c == 6:
                halo = (e >= 1.) & (e < 2.4) & m & gl
                out[halo] = P.paint_ramp(lamp, .45 + 0 * u)[halo]
            if c == 5:                                            # hurt: angled dark brow bar over each eye
                s = 1. if cx < .5 else -1.
                brow = (np.abs((v - .5 - ry * 1.6) + s * (u - cx) * .6) < .025) & (np.abs(u - cx) < rx * 1.3) & m
                out[brow] = P.rgb('joint')
            if c == 4:                                            # bright: a lower lid curve (smile shape)
                lid = (e < 1.) & (v < .5 - ry * .25 + 6. * (u - cx) ** 2) & m
                out[lid] = P.paint_ramp(glass, .30 + 0 * u)[lid]
        if c in (2, 3):                                           # talk: a small speaker bar below the eyes
            bar = gl & (np.abs(u - .5) < (.10 if c == 2 else .06)) & (np.abs(v - .5 + gh * .62) < .025) & m
            out[bar] = P.paint_ramp(lamp, .8 + 0 * u)[bar]
    return P0.quantize(out, P0.palette(pack))


def crown_texture(pack, roles):
    N = 32
    y, x = np.mgrid[0:N, 0:N]
    u = (x + .5) / N; v = 1. - (y + .5) / N
    P = Painter(pack, roles, N, N)
    val = .50 + .42 * v                       # gold all the way up: darker band base, bright points
    img = P.paint_ramp(P.ramp('shell_dark', 'emblem'), val)
    gem = (np.abs(v - .30) < .10) & (np.abs(((u * 5.) % 1.) - .5) < .12)
    img[gem] = P.paint_ramp(P.ramp('visor', 'lens'), .9 + 0 * u)[gem]
    return P0.quantize(img, P0.palette(pack))
