"""Palette roles for combat art (lane-combat-art). Pure Python + numpy.

Same idea as the packs' `prop_colors` and the kits' material roles: art is painted by ROLE, and each pack binds a
role to one of its own palette names in `packs/<pack>/combat_roles.json` ({"roles": {role: palette_name}}). A pack
that does not bind a role still works: the role falls back to the pack colour nearest its declared luminance /
saturation / hue intent (ROLE_SPECS), so the enemies and the weapon can be exported for any palette pack.

Every pixel that leaves core/combat_paint.py is quantised to the pack palette (core/paint.quantize).
"""
import json
from pathlib import Path

import numpy as np

from . import paint as P0

ROOT = Path(__file__).resolve().parents[1]

# role -> (target luminance 0..1, min saturation, max saturation, preferred hue in degrees or None)
ROLE_SPECS = {
    # cairn_dasher
    'hide': (.16, 0., .45, None), 'hide_dark': (.07, 0., .5, None), 'mane': (.78, 0., .35, None),
    'stone': (.55, 0., .25, None), 'stone_dark': (.32, 0., .25, None), 'lichen': (.62, .25, 1., 90.),
    'plate': (.66, 0., .3, None), 'hoof': (.06, 0., .4, None), 'eye': (.03, 0., .4, None),
    'eye_glow': (.75, .45, 1., 40.),
    # reed_warden
    'weave': (.42, .15, .8, 45.), 'weave_dark': (.18, .1, .8, 35.), 'weave_light': (.68, .1, .7, 50.),
    'band': (.30, .3, 1., 0.), 'mask': (.85, 0., .35, None), 'crest': (.36, .2, 1., 100.), 'crest_tip': (.62, .4, 1., 15.),
    'leg': (.12, 0., .5, None), 'wing': (.50, .15, .8, 80.), 'core_glow': (.82, .4, 1., 40.),
    # weapon / projectile
    'wood': (.48, .2, .8, 35.), 'wood_dark': (.24, .2, .8, 30.), 'wrap': (.20, .2, 1., 0.), 'metal': (.62, 0., .25, None),
    'metal_dark': (.33, 0., .25, None), 'accent': (.45, .45, 1., 10.), 'burr': (.35, .2, 1., 40.), 'burr_tip': (.80, .3, 1., 45.),
}


def load_roles(pack):
    p = ROOT / 'packs' / pack['id'] / 'combat_roles.json'
    if p.is_file():
        return json.loads(p.read_text(encoding='utf-8'))['roles']
    return {}


def _lum(c):
    c = np.asarray(c, float) / 255.
    return .2126 * c[..., 0] + .7152 * c[..., 1] + .0722 * c[..., 2]


def _sat_hue(c):
    c = np.asarray(c, float) / 255.
    mx = c.max(-1); mn = c.min(-1); d = mx - mn
    sat = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    h = np.where(d < 1e-6, 0., np.where(mx == r, ((g - b) / np.maximum(d, 1e-6)) % 6,
                                         np.where(mx == g, (b - r) / np.maximum(d, 1e-6) + 2, (r - g) / np.maximum(d, 1e-6) + 4)))
    return sat, h * 60.


def fallback(pack, role):
    """Pack palette name nearest the role's intent (used when the pack does not bind the role)."""
    lum_t, smin, smax, hue = ROLE_SPECS[role]
    pal = P0.palette(pack)
    L = _lum(pal); S, Hh = _sat_hue(pal)
    cost = np.abs(L - lum_t) * 2. + np.maximum(0, smin - S) + np.maximum(0, S - smax)
    if hue is not None:
        dh = np.abs(((Hh - hue) + 180.) % 360. - 180.) / 180.
        cost = cost + .6 * dh * (S > .12)
    return pack['palette_names'][int(np.argmin(cost))]


def resolve(pack, roles_needed):
    """{role: palette name} for every role needed (bound by the pack or by fallback) + which ones fell back."""
    bound = load_roles(pack)
    out, fell = {}, []
    for r in roles_needed:
        if r in bound:
            if bound[r] not in pack['palette_names']:
                raise ValueError('combat role %s bound to off-palette %s in %s' % (r, bound[r], pack['id']))
            out[r] = bound[r]
        else:
            out[r] = fallback(pack, r); fell.append(r)
    return out, fell


def rgb(pack, name):
    return P0.color(pack, name)
