"""Painted textures for the enemies (lane-combat-art). numpy only; every pixel quantised to the pack palette.

coat_atlas(pack, eid) -> 128x128 RGB, a 4x4 grid of 32 px tiles, one per part family (core/enemies.loft tiles):
  cairn_dasher: 0 body (shaggy hide, frosty mane over the shoulders, dark belly), 1 head/neck/ears/tail,
                2 stones + brow plate (lichen-spotted stone), 3 legs (hide darkening to the hoof)
  reed_warden:  0 woven body (diagonal basket weave, belt band, lighter crown), 1 face plate rim, 2 beak,
                3 reed blades (crest, tail; accent tips), 4 leaf wings (vein), 5 legs and feet
face_atlas(pack, eid) -> 64x64 RGB, 2x2 cells of 32 px (core/enemy_pose.FACE_CELLS): 0 eyes, 1 eyes_flare
  (telegraph/attack), 2 eyes_hurt, 3 eyes_closed (death). Cell c sits at column c % 2, row c // 2 counted from the
  BOTTOM of the image (UV v up), matching the material's offset node.
Tile UV convention (core/enemies.loft): u around the section (u = 0 and 1 = the section's 'up' side, .5 = 'down'),
v along the loft from its first ring (0) to its last (1).
"""
import math

import numpy as np

from . import paint as P0
from . import roles as RL
from .combat_paint import Painter

TAU = 2 * math.pi
ROLES = {'cairn_dasher': ['hide', 'hide_dark', 'mane', 'stone', 'stone_dark', 'lichen', 'plate', 'hoof', 'eye', 'eye_glow'],
         'reed_warden': ['weave', 'weave_dark', 'weave_light', 'band', 'mask', 'crest', 'crest_tip', 'leg', 'wing',
                         'core_glow', 'eye']}


def roles_for(pack, eid):
    return RL.resolve(pack, ROLES[eid])


def _tile_grid(N=128):
    y, x = np.mgrid[0:N, 0:N]
    T = N // 4
    u = ((x % T) + .5) / T
    v = 1. - ((y % T) + .5) / T
    tile = (3 - y // T) * 4 + x // T
    return u, v, tile


def _noise(u, v, s):
    return np.sin(u * 17 + v * 13 + s) * .48 + np.sin(u * 39 - v * 23 + s * .7) * .28 + np.sin(u * 71 + v * 59 + s * 1.3) * .13


def coat_atlas(pack, eid):
    roles, _ = roles_for(pack, eid)
    N = 128
    u, v, tile = _tile_grid(N)
    P = Painter(pack, roles, N, N)
    out = np.zeros((N, N, 3))
    up = np.cos(TAU * u)                       # +1 on the section's up side, -1 underneath
    if eid == 'cairn_dasher':
        hide = P.ramp('hide_dark', 'hide')
        # 0 body: dark hide lit from above, long coat strokes hanging down the skirt, darker belly and skirt hem
        side = np.abs(((TAU * u + math.pi) % TAU) - math.pi) / math.pi           # 0 top .. 1 belly
        val = .55 + .30 * up + .06 * _noise(u, v, 1.)
        strokes = .16 * np.sin((u * 13. + .35 * np.sin(v * 9.)) * TAU) * np.clip(side * 1.6, 0, 1)
        val += strokes
        val -= .30 * np.exp(-((side - .62) / .10) ** 2)                         # hem shadow line at the skirt edge
        val -= .25 * np.clip(side - .70, 0, 1) / .3
        body = P.paint_ramp(hide, val)
        frost = np.clip((up - .55) * 2.2, 0, 1) * (v < .55)                     # frosty pale tips over the shoulders
        fr = P.paint_ramp(P.ramp('hide', 'mane'), .25 + .5 * frost + .05 * _noise(u * 3, v * 3, 4.))
        body[frost > .35] = fr[frost > .35]
        # 1 head/ears/tail: hide, darker muzzle tip and around the eyes, lighter crown
        hv = .45 + .25 * up + .05 * _noise(u, v, 3.) - .30 * np.exp(-(v / .20) ** 2)
        head = P.paint_ramp(hide, hv)
        # 4 mane: pale shag lit from above, irregular soft locks (noise, not stripes), darker roots near the body
        locks = _noise(u * 2.3, v * .8, 6.) * .6 + _noise(u * 5.1, v * 1.7, 2.) * .4
        mv = .62 + .28 * up + .10 * locks - .25 * np.clip(.25 - v, 0, .25) / .25
        mane = P.paint_ramp(P.ramp('hide', 'mane'), mv)
        # 2 stone (+ plate): lit crown, shadowed underside, lichen blotches, a crack
        stone = P.ramp('stone_dark', 'stone')
        sv = .30 + .55 * v + .10 * _noise(u * 1.5, v * 1.5, 5.) + .10 * up
        st = P.paint_ramp(stone, sv)
        lich = (_noise(u * 2.2, v * 2.6, 9.) > .40) & (v > .35)
        lc = P.paint_ramp(P.ramp('stone_dark', 'lichen'), .6 + .3 * _noise(u * 4, v * 4, 2.))
        st[lich] = lc[lich]
        crack = np.abs(u - (.38 + .06 * np.sin(v * 9))) < .02
        st[crack & (v > .2) & (v < .85)] = P.rgb('stone_dark')
        # 3 legs: hide darkening to a near-black hoof (v -> 1)
        lv = .55 + .25 * up - .55 * np.clip((v - .70) / .30, 0, 1) + .05 * _noise(u, v, 7.)
        legs = P.paint_ramp(P.ramp('hoof', 'hide_dark', 'hide'), lv)
        planes = {0: body, 1: head, 2: st, 3: legs, 4: mane}
    else:
        weave = P.ramp('weave_dark', 'weave', 'weave_light')
        # 0 body: coiled basket - horizontal rounded coils (v), short diagonal stitches between them, a red rim band,
        # lighter crown, darker base (never a diamond/scale pattern)
        coils = 9.
        cv = (v * coils) % 1.
        row = np.floor(v * coils)
        coil = np.sin(math.pi * cv)                                             # rounded coil profile (soft)
        stitch = (np.abs(((u * 14. + .5 * (row % 2)) % 1.) - .5) < .06) & (cv > .2) & (cv < .8)
        val = .52 + .20 * coil + .24 * up + .12 * np.clip((v - .6) / .4, 0, 1) - .14 * np.clip(.25 - v, 0, .25) / .25
        val += .05 * _noise(u * 3, v * 3, 8.)
        val = np.where(stitch, val - .16, val)
        body = P.paint_ramp(weave, val)
        # 1 face plate rim: pale shield, a red painted ring at the rim (the band role), darker lip inside
        mv = .80 + .16 * up - .40 * (v < .2)
        mask = P.paint_ramp(P.ramp('weave_dark', 'mask'), mv)
        ring = (v > .38) & (v < .62)
        mask[ring] = P.paint_ramp(P.ramp('weave_dark', 'band'), .65 + .2 * up)[ring]
        # 2 beak
        beak = P.paint_ramp(P.ramp('weave_dark', 'crest_tip'), .45 + .3 * up)
        # 3 reed blades: pale reed with a darker centre rib, hot tips
        bv = .55 + .30 * up + .06 * np.sin(v * 30)
        bl = P.paint_ramp(P.ramp('weave_dark', 'crest'), bv)
        rib = np.abs(np.cos(TAU * u)) > .96
        bl[rib] = P.paint_ramp(P.ramp('weave_dark', 'crest'), .35 + 0 * u)[rib]
        tip = v > .70
        tc = P.paint_ramp(P.ramp('crest', 'crest_tip'), np.clip((v - .70) / .30, 0, 1) * .9 + .1)
        bl[tip] = tc[tip]
        # 4 leaf wings: vein down the middle, lighter edge
        wv = .50 + .25 * up + .12 * np.cos(TAU * u * 2)
        wings = P.paint_ramp(P.ramp('weave_dark', 'wing', 'weave_light'), wv)
        vein = np.abs(np.cos(TAU * u)) > .97
        wings[vein] = P.rgb('weave_dark')
        # 5 legs and feet: dark, ringed joints
        lv = .40 + .2 * up + .25 * (np.abs(v - .5) < .06)
        legs = P.paint_ramp(P.ramp('leg', 'weave_dark', 'weave'), lv)
        planes = {0: body, 1: mask, 2: beak, 3: bl, 4: wings, 5: legs}
    for t, img in planes.items():
        m = tile == t
        out[m] = img[m]
    rest = ~np.isin(tile, list(planes))
    out[rest] = planes[0][rest]
    return P0.quantize(out, P0.palette(pack))


def face_atlas(pack, eid):
    roles, _ = roles_for(pack, eid)
    N = 64
    y, x = np.mgrid[0:N, 0:N]
    col = x // 32; row = 1 - y // 32                       # row counted from the bottom
    cell = row * 2 + col
    u = ((x % 32) + .5) / 32.; v = 1. - ((y % 32) + .5) / 32.
    P = Painter(pack, roles, N, N)
    out = np.zeros((N, N, 3))
    if eid == 'cairn_dasher':
        base = P.paint_ramp(P.ramp('hide_dark', 'hide', 'mane'), .30 + .25 * v + .04 * _noise(u, v, 4.))
        out[:] = base
        EY = .50                                             # eyes on the head's flanks (u = .25 / .75 round the loft)
        # on a flank, u runs vertically (toward u = 0 / 1 is up, under the plate) and v runs along the head, so an
        # almond eye is short in u and long in v
        for cx, up_dir in ((.25, -1.), (.75, 1.)):
            for c in range(4):
                m = cell == c
                if c == 3:                                   # closed: a dark lid line along the head
                    lid = (np.abs(u - cx) < .012) & (np.abs(v - EY) < .30) & m
                    out[lid] = P.rgb('eye')
                    continue
                ru, rv = (.036, .40) if c == 0 else ((.05, .48) if c == 1 else (.016, .36))
                e = ((u - cx) / ru) ** 2 + ((v - EY) / rv) ** 2
                ring = (e < 1.7) & m
                out[ring] = P.rgb('eye')
                core = (e < 1.) & m
                glow = P.paint_ramp(P.ramp('hide', 'eye_glow'), np.clip(1.25 - e, 0, 1))
                out[core] = glow[core]
                if c == 1:                                   # flare: a faint halo round the hot eye
                    halo = (e > 1.7) & (e < 3.0) & m
                    out[halo] = P.paint_ramp(P.ramp('hide', 'eye_glow'), .35 + 0 * e)[halo]
                if c == 2:                                   # hurt: a dark pinched brow line above the slit
                    brow = (np.abs(u - (cx + up_dir * .045)) < .012) & (np.abs(v - EY + .05) < .32) & m
                    out[brow] = P.rgb('eye')
    else:
        base = P.paint_ramp(P.ramp('weave_dark', 'mask'), .78 + .18 * v + .03 * _noise(u, v, 2.))
        out[:] = base
        rim = (np.hypot(u - .5, (v - .5) * 1.15) > .44)
        out[rim] = P.paint_ramp(P.ramp('weave_dark', 'mask'), .45 + 0 * u)[rim]
        for cx in (.33, .67):
            for c in range(4):
                m = cell == c
                if c == 3:
                    lid = (np.abs(v - .55) < .03) & (np.abs(u - cx) < .10) & m
                    out[lid] = P.rgb('weave_dark')
                    continue
                rx, ry = (.09, .045) if c == 0 else ((.11, .10) if c == 1 else (.10, .025))
                tilt = (u - cx) * (.35 if cx < .5 else -.35) if c != 1 else 0.
                e = ((u - cx) / rx) ** 2 + ((v - .55 - tilt) / ry) ** 2
                out[(e < 1.7) & m] = P.rgb('eye') if 'eye' in roles else P.rgb('weave_dark')
                glow = P.paint_ramp(P.ramp('band', 'core_glow'), np.clip(1.2 - e, 0, 1))
                out[(e < 1.) & m] = glow[(e < 1.) & m]
    return P0.quantize(out, P0.palette(pack))
