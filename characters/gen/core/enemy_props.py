"""Enemy props (lane-combat-art): the reed burr, an optional lobbed projectile for reed_warden (<= 200 tris).
A rounded seed ball with six short tapered spines; origin at its centre. Painted by role (burr, burr_tip)."""
import math

from . import enemies as EN

PROJ_ID = 'reed_burr'
NODE_NAME = 'kit_acc_projectile_reed_burr'
TAU = 2 * math.pi


class PropMesh:
    def __init__(self):
        self.vertices = []; self.faces = []; self.uv = []; self.roles = []; self.tiles = []; self.weights = []
        self.parts = {}; self.part_info = {}; self.kind = 'prop'


def burr():
    m = PropMesh()
    R = .055
    Z = (0., 0., 1.)
    rings = []
    for k, (z, r) in enumerate(((-.92, .38), (-.45, .90), (.20, .98), (.75, .62))):
        rings.append(EN.section(6, (0., 0., z * R), Z, (0., -1., 0.), r * R, r * R, ex=2., bulge=EN._wobble(k * 1.7, .05)))
    EN.loft(m, 'core', rings, 0, 'root', caps=('centre', 'centre'), uv_rect=(.04, .04, .46, .96))
    dirs = [(1, 0, .2), (-1, 0, .2), (0, 1, -.1), (0, -1, -.1), (.3, .2, 1), (-.2, -.3, -1)]
    for i, d in enumerate(dirs):
        n = math.sqrt(sum(c * c for c in d)); d = tuple(c / n for c in d)
        base = tuple(c * R * .70 for c in d); tip = tuple(c * R * 1.75 for c in d)
        rr = [EN.section(3, base, d, (0., 0., 1.) if abs(d[2]) < .9 else (1., 0., 0.), .016, .016, ex=2.),
              EN.section(3, tip, d, (0., 0., 1.) if abs(d[2]) < .9 else (1., 0., 0.), .003, .003, ex=2.)]
        EN.loft(m, 'spine_%d' % i, rr, 1, 'root', uv_rect=(.54, .04, .96, .96))
    return m


def texture(pack, roles):
    import numpy as np
    from . import paint as P0
    from .combat_paint import Painter
    N = 32
    y, x = np.mgrid[0:N, 0:N]
    u = (x + .5) / N; v = 1 - (y + .5) / N
    P = Painter(pack, roles, N, N)
    core = P.paint_ramp(P.ramp('weave_dark', 'burr', 'burr_tip'), .35 + .25 * np.cos(TAU * u * 2) * .5 + .35 * v)
    spine = P.paint_ramp(P.ramp('burr', 'burr_tip'), .3 + .65 * v)
    out = np.where((u < .5)[:, :, None], core, spine)
    return P0.quantize(out, P0.palette(pack))
