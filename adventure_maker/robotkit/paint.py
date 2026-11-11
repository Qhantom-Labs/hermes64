"""Palette-exact textures for the robotkit bodies: a 64 x 64 coat atlas of 16 texel tiles and a 64 x 32 visor atlas
(4 x 2 cells, the same cell convention as the stock robots' face atlas). Every texel is a named palette colour of the
pack; roles and liveries come from the recipe file (characters/robotkit/<pack>.json). numpy only."""
import numpy as np

from . import bodies as B

CELLS = {'calm': 0, 'dim': 1, 'talk_a': 2, 'talk_b': 3, 'bright': 4, 'hurt': 5, 'flare': 6, 'off': 7}
CLIP_CELLS = {'telegraph': 6, 'attack': 6, 'swing': 6, 'hurt': 5, 'death': 7, 'recover': 1}
MARKS = ('ring', 'bars', 'key')


def rgb(data, name):
    if name not in data['palette_names']:
        raise ValueError('off-palette name %r' % (name,))
    h = data['palette'][data['palette_names'].index(name)].lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def colours(data, livery):
    """Role -> palette name for one livery (the shared roles plus the livery's dark / main / bright)."""
    L = data['liveries'][livery]
    c = dict(data['roles'])
    c.update({'dark': L['dark'], 'main': L['main'], 'bright': L['bright']})
    return c


def mark_mask(kind, n, aspect):
    """n x n boolean mask of a company mark, squashed so it is undistorted on a tile `aspect` times as wide as tall."""
    if kind not in MARKS:
        raise ValueError('unknown mark %r (have %s)' % (kind, ', '.join(MARKS)))
    a = float(aspect or 1.)
    y, x = np.mgrid[0:n, 0:n]
    X = ((x + .5) / n * 2. - 1.) * a
    Y = 1. - (y + .5) / n * 2.
    k = min(1., a)
    X = X / k; Y = Y / k
    r = np.hypot(X, Y)
    if kind == 'ring':
        return (r <= .82) & (r >= .46)
    if kind == 'bars':
        return (np.abs(X) <= .80) & (np.abs(Y) >= .20) & (np.abs(Y) <= .68)
    disc = np.hypot(X, Y - .32) <= .50
    wedge = (Y <= .20) & (Y >= -.84) & (np.abs(X) <= .17 + .36 * (.20 - Y))
    return disc | wedge


def coat_atlas(data, livery, aspects=None):
    """(64, 64, 3) uint8. aspects: {'mark': w/h, 'mark_top': w/h} measured on the body (bodies.tile_aspect)."""
    c = colours(data, livery)
    col = lambda role: rgb(data, c[role])
    T = B.TILE
    img = np.zeros((B.ATLAS, B.ATLAS, 3), np.uint8)
    img[:, :] = col('shell')
    aspects = aspects or {}

    def tile(name):
        cc, r, n = B.TILE_CELLS[name]
        return img[r * T:(r + n) * T, cc * T:(cc + n) * T]

    t = tile('shell'); t[:] = col('shell'); t[0:2] = col('shell_hi'); t[13:16] = col('shell_lo'); t[7] = col('shell_lo')
    t = tile('livery'); t[:] = col('main'); t[0:3] = col('bright'); t[13:16] = col('dark')
    t = tile('trim'); t[:] = col('trim'); t[5:11] = col('main'); t[7:9] = col('bright')
    t = tile('joint'); t[:] = col('joint'); t[3::4] = col('joint_hi')
    t = tile('vent'); t[:] = col('vent'); t[2::4] = col('vent_hi'); t[3::4] = col('vent_hi')
    t = tile('light'); t[:] = col('bright'); t[3:13, 3:13] = col('rim')
    t = tile('tip'); t[:] = col('main'); t[0:10] = col('bright'); t[0:4] = col('rim')
    t = tile('top'); t[:] = col('top'); t[0:5] = col('top_hi'); t[14:16] = col('shell_hi')
    t = tile('sole'); t[:] = col('sole')
    for name in ('mark', 'mark_top'):
        t = tile(name)
        n = t.shape[0]
        t[:] = col('dark')
        t[mark_mask(data['liveries'][livery]['mark'], n, aspects.get(name))] = col('bright')
        e = max(1, n // 16)
        t[:e] = col('main'); t[-e:] = col('main'); t[:, :e] = col('main'); t[:, -e:] = col('main')
    return img


def face_atlas(data, livery):
    """(32, 64, 3) uint8: eight 16 x 16 visor cells, cell = row * 4 + col with row 0 the lower image row.
    The strip runs along u; `flare` (telegraph, attack) is the widest and brightest, `off` (death) is unlit."""
    c = colours(data, livery)
    col = lambda role: rgb(data, c[role])
    img = np.zeros((32, 64, 3), np.uint8)
    # Lit rows per 16-row cell. The strip is 10 rows in the calm cell because the runtime frame showed a calm strip of
    # 8 rows as one bright pixel row on a brute 33 px tall (tower_roof_finale, camera 14 m; docs/ROBOTS-RESULT.md).
    spec = {'calm': (3, 13, 'bright', (5, 11)), 'dim': (5, 11, 'main', None), 'talk_a': (3, 13, 'bright', (5, 11)),
            'talk_b': (2, 14, 'bright', (5, 11)), 'bright': (2, 14, 'bright', (4, 12)), 'hurt': (4, 12, 'hurt', None),
            'flare': (0, 16, 'bright', (2, 14)), 'off': (7, 9, 'dark', None)}
    for name, cell in CELLS.items():
        r, cc = cell // 4, cell % 4
        y0 = (1 - r) * 16; x0 = cc * 16
        t = img[y0:y0 + 16, x0:x0 + 16]
        t[:] = col('eye_off')
        a, b, role, core = spec[name]
        t[a:b] = col(role)
        if core:
            t[core[0]:core[1]] = col('eye_core')
        if name == 'hurt':
            t[a:b, 6:10] = col('eye_off')            # a broken strip
        if name == 'talk_a':
            t[a:b, 0:2] = col('main'); t[a:b, 14:16] = col('main')
    return img


def palette_exact(img, data):
    """Number of texels whose colour is not a palette entry (0 for every atlas this module paints)."""
    pal = {rgb(data, n) for n in data['palette_names']}
    flat = img.reshape(-1, 3)
    return int(sum(1 for px in {tuple(int(v) for v in p) for p in flat} if px not in pal))
