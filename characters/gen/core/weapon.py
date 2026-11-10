"""Trail staff: the original melee weapon prop for the combat clips (lane-combat-art). Pure Python (+numpy paint).

A short ash-wood fighting staff (0.82 m): rounded metal pommel knob, leather-wrapped grip, a hexagonal shaft that
swells to a banded collar and a carved bulb head, and a short accent ribbon tied under the head so the weapon reads
at 320x240. One separate rigid mesh, <= 200 triangles, painted by palette role (core/roles.py).

Weapon-local frame (Blender axes): origin = grip centre (the middle of the fist), shaft along +Z (tip up), pommel
below. glTF (Y-up): shaft along +Y. Grip on the character: child of joint `hand_r`, rest rotation Rx(+90 deg) (the
shaft leaves the fist forward, -Y in Blender / +Z in glTF), translation = the mitt centre relative to the hand_r
joint (per character, see grip_offset / the manifest's weapon_grip).
"""
import math

from . import people as PP

TAU = 2 * math.pi
WEAPON_ID = 'trail_staff'
NODE_NAME = 'kit_acc_hand_r_trail_staff'
TIP_LEN = .690          # grip -> tip (m)
POMMEL_LEN = .135       # grip -> pommel end (m)
SIDES = 6
# (z, radius, band) along the shaft; band picks the paint (pommel, wrap, wood, collar, head)
PROFILE = [(-.135, .011, 'pommel'), (-.126, .022, 'pommel'), (-.108, .027, 'pommel'), (-.092, .019, 'pommel'),
           (-.080, .021, 'wrap'), (.000, .0215, 'wrap'), (.075, .021, 'wrap'), (.088, .0185, 'wood'),
           (.330, .0195, 'wood'), (.540, .0235, 'wood'), (.565, .030, 'collar'), (.588, .029, 'collar'),
           (.640, .039, 'head'), (.672, .031, 'head'), (.690, .012, 'head')]
# Rest grip: weapon +Z -> core/combat.GRIP_AXIS = forward, leaning GRIP_TILT toward the forearm's extension
# (a cocked fist: with the forearm level the staff points up-forward). Rest rotation Rx(90 deg + GRIP_TILT).
GRIP_TILT = math.radians(float(__import__('os').environ.get('COMBAT_GRIP_TILT_DEG', '30')))
GRIP_REST_ANGLE = math.pi / 2 + GRIP_TILT
REST_Q_BLENDER = (math.cos(GRIP_REST_ANGLE / 2), math.sin(GRIP_REST_ANGLE / 2), 0., 0.)
REST_Q_GLTF_XYZW = [math.sin(GRIP_REST_ANGLE / 2), 0., 0., math.cos(GRIP_REST_ANGLE / 2)]   # same rotation, glTF axes
STOW = {'joint': 'spine', 'note': 'diagonal across the back while exploring (runtime option; not baked into clips)',
        'translation_blender': (.0, .135, .02), 'euler_blender': (0., .62, 0.)}


U_STAFF = .84           # the staff uses u in [0, .84]; the ribbon lives in u [.88, .98]


class WeaponMesh:
    def __init__(self):
        self.vertices = []; self.faces = []; self.uv = []; self.weights = []; self.roles = []; self.parts = {}
        self.tiles = []; self.slot = 'hand_r'; self.kind = WEAPON_ID


def _v_of(z):
    return (z + POMMEL_LEN) / (TIP_LEN + POMMEL_LEN)


def build():
    m = WeaponMesh()
    n = SIDES
    rings = []
    for z, r, band in PROFILE:
        # slightly flattened hexagon with rounded (bulged) flats: reads round under smooth shading, never a box
        rings.append(PP.zring(n, 0., 0., z, r, r * .94))
    nr = len(rings)

    def uvf(k, j, col):
        if col is None:                       # caps: centre of the pommel / head band
            return (U_STAFF * (.5 + .2 * math.sin(TAU * j / n)), _v_of(PROFILE[k][0]))
        return (U_STAFF * min(j, n) / float(n), _v_of(PROFILE[k][0]))
    PP._add_loft(m, 'staff', rings, 'prop', 'hand_r', uvf, caps=('flat', 'flat'))
    # accent ribbon: a thin 3-sided tapered strip hanging from just under the head, tied on the shaft side
    rib = [(.024, -.004, .552, .007, .004), (.040, -.012, .470, .010, .004), (.048, -.016, .392, .006, .003)]
    rr = [PP.zring(3, x, y, z, a, b) for x, y, z, a, b in rib]

    def uvr(k, j, col):
        return (.9 + .04 * (j % 3), .05 + .1 * k)
    PP._add_loft(m, 'ribbon', rr, 'prop', 'hand_r', uvr, caps=('flat', 'flat'))
    return m


def grip_offset(bones, body=None):
    """Rest-frame offset (Blender axes, metres) from the hand_r joint to the grip centre (= mitt centre)."""
    if body and body.get('mitt_r') is not None:
        c = body['mitt_r']
        h = bones['hand_r']
        return (c[0] - h[0], c[1] - h[1], c[2] - h[2])
    H = bones['head'][2] / .755 if bones.get('head') else 1.65
    return (-.010 * H, -.008 * H, -.05 * H)


def grip_gltf(bones, body=None):
    """The documented grip transform: weapon node as a child of joint hand_r, glTF axes (Y-up)."""
    dx, dy, dz = grip_offset(bones, body)
    return {'joint': 'hand_r', 'translation': [round(dx, 6), round(dz, 6), round(-dy, 6)],
            'rotation_xyzw': [round(c, 7) for c in REST_Q_GLTF_XYZW], 'scale': [1., 1., 1.],
            'weapon_axis': '+Y (glTF) = shaft toward the tip; origin = grip centre'}


def texture(pack, roles):
    """64x32 painted staff texture (u around the shaft, v from pommel (0) to tip (1)), quantised to the pack."""
    import numpy as np
    from . import paint as P0
    from . import combat_paint as CP
    W, H = 32, 64
    y, x = np.mgrid[0:H, 0:W]
    uu = (x + .5) / W; v = 1 - (y + .5) / H
    u = np.clip(uu / U_STAFF, 0., 1.)          # around-the-shaft coordinate of the staff region
    T = CP.Painter(pack, roles, W, H)
    wood = T.ramp('wood_dark', 'wood', 'metal')
    val = .55 + .12 * np.sin(u * TAU * 3 + v * 9) * .5 + .10 * np.sin(v * 70 + np.sin(u * TAU) * 2) * .4
    val += .18 * np.cos(TAU * (u - .30))                      # lit side of the shaft
    out = T.paint_ramp(wood, val)
    # grain streaks
    streak = (np.abs(np.sin(u * TAU * 5 + v * 3.1)) > .93)
    out[streak] = T.paint_ramp(wood, val - .22)[streak]
    vb = lambda z: _v_of(z)
    wrap = (v > vb(-.084)) & (v < vb(.080))
    wr = T.ramp('hide_dark' if 'hide_dark' in roles else 'wood_dark', 'wrap', 'accent')
    wv = .52 + .30 * (np.abs(((u * 4 + v * 26) % 1.) - .5) < .22) + .14 * np.cos(TAU * (u - .3))
    out[wrap] = T.paint_ramp(wr, wv)[wrap]
    met = T.ramp('metal_dark', 'metal', 'metal')
    pom = v < vb(-.090)
    mv = .45 + .45 * np.cos(TAU * (u - .3)) * .5 + .35 * np.exp(-((v - vb(-.11)) / .02) ** 2)
    out[pom] = T.paint_ramp(met, mv)[pom]
    col = (v > vb(.553)) & (v < vb(.598))
    out[col] = T.paint_ramp(met, mv + .1 * np.sin(v * 300))[col]
    head = v > vb(.598)
    hv = .58 + .25 * np.cos(TAU * (u - .3)) + .12 * np.sin(u * TAU * 6) * (v < vb(.66))
    out[head] = T.paint_ramp(wood, hv)[head]
    rib = (uu > U_STAFF)
    out[rib] = T.paint_ramp(T.ramp('wrap', 'accent'), .55 + .3 * np.sin(v * 40))[rib]
    return P0.quantize(out, P0.palette(pack))
