"""Small held/worn props for character personality (pure Python; separate rigid meshes on attachment
points, DESIGN prop class <= 150 triangles each). Colours are pack palette names via pack['prop_colors'].

build(kind) -> PropMesh with vertices (prop-local metres, origin at the grip), faces, uv, roles,
slot (attachment bone) and the material keys used. Grip conventions: hand props hang from the mitt
centre; +Z up, -Y forward, in the rest orientation of the attachment bone.
"""
import math

from . import people as PP

TAU = 2 * math.pi
KINDS = ['mug', 'lantern', 'datapad', 'cane', 'satchel', 'duffel', 'book', 'thermos']
SLOT = {'mug': 'hand_r', 'lantern': 'hand_r', 'datapad': 'hand_r', 'cane': 'hand_r', 'satchel': 'belt',
        'duffel': 'hand_r', 'book': 'hand_r', 'thermos': 'hand_l'}   # round 10: book in the right hand like the datapad (interact frees the left)
# material key -> tile in the 4x4 prop texture
TILES = {'body': 0, 'dark': 1, 'light': 2, 'metal': 3, 'glass': 4, 'accent': 5, 'cloth': 6, 'wood': 7}


class PropMesh:
    def __init__(self, kind):
        self.kind = kind; self.vertices = []; self.faces = []; self.uv = []; self.weights = []; self.roles = []
        self.parts = {}; self.tiles = []
        self.slot = SLOT[kind]; self.scale = 1.


def _tile_uv(key):
    t = TILES[key]
    u0 = (t % 4) / 4.; v0 = (t // 4) / 4.

    def uvf(k, j, col, nr=2, n=8):
        return (u0 + .03 + .19 * ((j % (n + 1)) / float(n)), v0 + .03 + .19 * (k / max(1., nr - 1.)))
    return uvf


def _cyl(m, name, key, n, rings):
    pts = [PP.zring(n, x, y, z, rx, ry) for (x, y, z, rx, ry) in rings]
    f = _tile_uv(key)
    PP._add_loft(m, name, pts, key, m.slot, lambda k, j, col: f(k, j, col, len(rings), n))


def _frame(m, name, key, n, centres, radii, direction, up=(0., 0., 1.)):
    rings = [PP.framering(n, c, direction, up, a, b) for c, (a, b) in zip(centres, radii)]
    rings = PP._orient(rings, direction)
    f = _tile_uv(key)
    PP._add_loft(m, name, rings, key, m.slot, lambda k, j, col: f(k, j, col, len(rings), n))


def build(kind):
    m = PropMesh(kind)
    if kind == 'mug':
        _cyl(m, 'cup', 'body', 8, [(0, -.04, -.07, .036, .036), (0, -.04, -.005, .041, .041), (0, -.04, .018, .040, .040)])
        _frame(m, 'handle', 'body', 4, [(.038, -.04, -.05), (.062, -.04, -.026), (.04, -.04, -.002)],
               [(.008, .008), (.009, .009), (.008, .008)], (0., 0., 1.), (1., 0., 0.))
        _cyl(m, 'tea', 'dark', 6, [(0, -.04, .008, .035, .035), (0, -.04, .019, .034, .034)])
    elif kind == 'lantern':
        _frame(m, 'bail', 'metal', 4, [(-.03, 0, -.03), (0, 0, .0), (.03, 0, -.03)], [(.004, .004)] * 3, (1., 0., 0.))
        _cyl(m, 'cap', 'metal', 8, [(0, 0, -.06, .03, .03), (0, 0, -.04, .045, .045), (0, 0, -.035, .02, .02)])
        m.scale = 1.5
        _cyl(m, 'globe', 'glass', 8, [(0, 0, -.16, .036, .036), (0, 0, -.11, .052, .052), (0, 0, -.062, .04, .04)])
        _cyl(m, 'base', 'metal', 8, [(0, 0, -.185, .046, .046), (0, 0, -.165, .05, .05), (0, 0, -.155, .04, .04)])
    elif kind == 'datapad':
        _frame(m, 'slab', 'body', 8, [(-.075, -.02, -.01), (.075, -.02, -.01)], [(.012, .055), (.012, .055)], (1., 0., 0.), (0., -.35, 1.))
        # screen on the reader side of the slab (+u), so it faces the holder's eyes
        _frame(m, 'screen', 'glass', 4, [(-.06, -.008, -.006), (.06, -.008, -.006)], [(.002, .04), (.002, .04)], (1., 0., 0.), (0., -.35, 1.))
    elif kind == 'cane':
        _cyl(m, 'shaft', 'wood', 6, [(0, -.01, -.86, .012, .012), (0, -.01, -.45, .015, .015), (0, -.01, .02, .017, .017)])
        _frame(m, 'crook', 'wood', 5, [(0, -.01, .015), (0, -.045, .05), (0, -.075, .02)], [(.016, .016), (.017, .017), (.014, .014)], (0., -1., 0.))
    elif kind == 'satchel':
        _frame(m, 'bag', 'cloth', 8, [(.0, -.06, -.06), (.0, .06, -.06)], [(.05, .065), (.05, .065)], (0., 1., 0.), (0., 0., 1.))
        _frame(m, 'flap', 'dark', 6, [(.0, -.064, -.02), (.0, .064, -.02)], [(.054, .03), (.054, .03)], (0., 1., 0.), (0., 0., 1.))
    elif kind == 'duffel':
        # long axis front-to-back so it hangs beside the leg
        _frame(m, 'bag', 'cloth', 8, [(.0, -.17, -.15), (.0, 0, -.14), (.0, .17, -.15)], [(.07, .075), (.095, .1), (.07, .075)], (0., 1., 0.))
        _frame(m, 'strap', 'dark', 4, [(0, -.07, -.06), (0, 0, -.01), (0, .07, -.06)], [(.009, .009)] * 3, (0., 1., 0.))
    elif kind == 'book':
        _frame(m, 'cover', 'accent', 4, [(-.06, -.02, -.02), (.06, -.02, -.02)], [(.022, .075), (.022, .075)], (1., 0., 0.), (0., 0., 1.))
        _frame(m, 'pages', 'light', 4, [(-.055, -.02, -.02), (.055, -.02, -.02)], [(.017, .07), (.017, .07)], (1., 0., 0.), (0., -.2, 1.))
    elif kind == 'thermos':
        _cyl(m, 'flask', 'body', 8, [(0, -.03, -.09, .03, .03), (0, -.03, .03, .032, .032), (0, -.03, .05, .02, .02)])
        _cyl(m, 'lid', 'accent', 6, [(0, -.03, .045, .024, .024), (0, -.03, .075, .022, .022)])
    else:
        raise ValueError('unknown prop ' + kind)
    # round 10: oversized hand props so they read at game distance (N64 convention); lantern already 1.5
    m.scale = {'mug': 1.3, 'datapad': 1.3, 'book': 1.3, 'thermos': 1.2}.get(kind, m.scale)
    if m.scale != 1.:
        s = m.scale
        m.vertices = [(x * s, y * s, z * s) for (x, y, z) in m.vertices]
    return m


def texture(pack, kind):
    """32x32 prop texture: 4x4 tiles, each a palette colour with painted light/shadow bands."""
    import numpy as np
    from . import paint as P0
    from . import people_paint as PPP
    T = PPP.Tones(pack)
    cols = dict(pack.get('prop_colors', {}))
    img = np.zeros((32, 32, 3))
    for key, t in TILES.items():
        name = cols.get(key) or cols.get('body')
        x0 = (t % 4) * 8; y0 = (3 - t // 4) * 8
        tile = np.zeros((8, 8, 3)); tile[:] = T.rgb(name)
        tile[:2] = T.rgb(name, 1)
        tile[6:] = T.rgb(name, -1)
        if key == 'glass':
            tile[2:4, 1:3] = T.rgb(name, 2)
        img[y0:y0 + 8, x0:x0 + 8] = tile
    return P0.quantize(img, P0.palette(pack))


# grip placement relative to the attachment joint, in units of character height (rest orientation)
GRIP = {'hand_r': (0., -.010, -.042), 'hand_l': (0., -.010, -.042), 'belt': (.115, .0, -.045), 'back': (0., .1, .0), 'head': (0., -.12, .1)}
