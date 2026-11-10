"""Mechanical archetype family on the shared human16_v1 rig (lane CHARSYS). Pure Python 3.9, no Blender.

Three original body types, every piece a closed loft of rounded superellipse sections (core/enemies.section,
exponent <= 2.6, >= 5 sides except the 3-sided antenna blade), painted by palette ROLE, under creature budgets:
  walker   a stout "kettle" porter: bottom-heavy round hull, a lid-like dome head with a visor band, short ball-socket
           arms with rounded mitts, short legs on round pad feet.                      height .85-1.25 m, < 500 tris
  brute    a tall hauler: inverted-pear barrel chest, a small dome head sunk between two round shoulder domes, long
           arms with heavy gauntlet forearms and big round fists, stocky legs.          height 1.70-2.30 m, < 500 tris
  floater  a hover unit: onion hull narrowing to a glowing thruster nozzle, a wide lid head with a visor slit, thin
           manipulator arms, two vanes underneath (the leg chains), hovering above the floor. 1.10-1.60 m, < 500 tris
The rig is human16_v1 (core/geometry.HUMAN_PARENTS, same bone names and order) so every human clip, the six
combat clips and the archetype templates (ext/robot_pose.py) play on all three. The floater maps its vanes onto the
leg chains (thigh/shin/foot) and its hull onto pelvis/spine: documented in docs/CHARACTERS.md.

Design rules carried from the enemies: every bone pivots at the centre of the root ring of the piece it carries,
which sits inside its host (ball sockets), so a rotation tilts that ring in place instead of opening a gap.
No real-world mark, logo, product silhouette or protected character is modelled (no single cyclops eye, no
dome-on-tripod, no box head, no letters).

Mesh layout matches core/enemies.loft (connectivity.structure reads it): parts = {name: vertex ids},
part_info = {name: {n, rings, tile, role}}, roles 'coat' | 'face', uv per face, weights per vertex.
"""
import math

try:
    from ..core import enemies as EN
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import enemies as EN
try:
    from ..core import geometry as G
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import geometry as G
try:
    from ..core import connectivity as CN
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import connectivity as CN
TAU = 2 * math.pi
BODIES = ('walker', 'brute', 'floater')
TOPOLOGY = {'walker': 'robot_walker_v1', 'brute': 'robot_brute_v1', 'floater': 'robot_floater_v1'}
RIG = 'human16_v1'
BUDGET = 500                      # creature body budget: tris < 500
HEIGHT = {'walker': (1.00, 1.30, 1.10), 'brute': (1.70, 2.30, 2.00), 'floater': (1.00, 1.40, 1.15)}
BUILD = {'walker': (.85, 1.2), 'brute': (.95, 1.1), 'floater': (.85, 1.15)}
HOVER = {'floater': .20}          # metres above the floor at rest (fraction of height), the grounding offset

# optional pieces per body: id -> (bodies that accept it, triangle cost estimate used by the recipe gate)
OPTIONS = {
    'head': {'walker': ['dome', 'lantern'], 'brute': ['dome', 'helm'], 'floater': ['lid', 'dome']},
    'hands': {'walker': ['mitt', 'pincer'], 'brute': ['fist', 'mitt'], 'floater': ['pincer', 'mitt']},
    'feet': {'walker': ['pad', 'long'], 'brute': ['pad', 'long'], 'floater': ['none']},
    'extras': ['antenna', 'backpack', 'pauldrons', 'ear_pods', 'vents'],
}
DEFAULTS = {'height': None, 'build': 1.0, 'head_size': 1.0, 'head': None, 'hands': None, 'feet': None,
            'extras': (), 'visor': 'twin', 'wear': .25, 'boss': False}
RANGES = {'head_size': (.85, 1.2), 'wear': (0., 1.)}
VISORS = ('twin', 'band', 'slit', 'grille')


class RobotMesh:
    """Human16-rigged mechanical body (kind 'human' so core pose/combat clips and body_metrics apply)."""

    def __init__(self, body, p, bones):
        self.id = 'robot_' + body; self.body = body; self.kind = 'human'; self.topology = TOPOLOGY[body]
        self.rig = RIG; self.skeleton = RIG
        self.bones = bones; self.parents = dict(G.HUMAN_PARENTS)
        self.vertices = []; self.faces = []; self.uv = []; self.roles = []; self.tiles = []; self.weights = []
        self.parts = {}; self.part_info = {}; self.open_roots = []
        self.params = dict(p)


def resolve(body, values):
    if body not in BODIES:
        raise ValueError('unknown robot body ' + str(body))
    p = dict(DEFAULTS)
    for k, v in values.items():
        if k not in p:
            raise ValueError('unknown robot parameter ' + k)
        p[k] = v
    lo, hi, d = HEIGHT[body]
    if p['height'] is None:
        p['height'] = d
    if isinstance(p['height'], bool) or type(p['height']) not in (int, float) or not lo <= p['height'] <= hi:
        raise ValueError('height outside declared range for ' + body)
    for k, (a, b) in list(RANGES.items()) + [('build', BUILD[body])]:
        v = p[k]
        if isinstance(v, bool) or type(v) not in (int, float) or not math.isfinite(v) or not a <= v <= b:
            raise ValueError(k + ' outside declared range')
    for k in ('head', 'hands', 'feet'):
        opts = OPTIONS[k][body]
        if p[k] is None:
            p[k] = opts[0]
        if p[k] not in opts:
            raise ValueError('%s %r not available on %s' % (k, p[k], body))
    ex = tuple(sorted(set(p['extras'])))
    for e in ex:
        if e not in OPTIONS['extras']:
            raise ValueError('unknown extra ' + str(e))
    if 'pauldrons' in ex and body != 'brute':
        raise ValueError('pauldrons only fit the brute')
    p['extras'] = list(ex)
    if p['visor'] not in VISORS:
        raise ValueError('unknown visor ' + str(p['visor']))
    if type(p['boss']) is not bool:
        raise ValueError('boss must be boolean')
    p['height'] = float(p['height']); p['build'] = float(p['build']); p['head_size'] = float(p['head_size'])
    p['wear'] = float(p['wear'])
    return p


# ------------------------------------------------------------------ loft helpers
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0., 0., 1.)


# robot coat atlas layout (u0, v0, u1, v1), 128 px: the hull gets a 64x64 quadrant, the head a 32x64 strip
RECTS = {0: (0., .5, .5, 1.), 1: (.5, .5, .75, 1.), 2: (.75, .75, 1., 1.), 3: (.75, .5, 1., .75), 4: (0., .25, .25, .5),
         5: (.25, .25, .5, .5), 6: (.5, .25, .75, .5), 7: (.75, .25, 1., .5)}


def _inset(r, px=1.5, N=128.):
    d = px / N
    return (r[0] + d, r[1] + d, r[2] - d, r[3] - d)


def tube(m, name, pts, weights, tile, n=6, ex=2.2, up=(0., -1., 0.), caps=('flat', 'flat'), bulge=None,
         direction=None, role='coat', open_root=False):
    """Loft through points [(centre, a, b), ...]; ring directions follow the polyline (or `direction`).
    open_root=<parent part>: drop the first ring's cap of a piece whose root is buried inside that parent. An open
    piece never 'contains' the parent's vertices, so the rig kit's generic connectivity checks only the buried-root ->
    parent contact (which holds near the joint pivot); _finish() then keeps every parent vertex >= 4.5 mm off the open
    piece's surface so no accidental reverse contact forms. The hidden cap costs no triangles."""
    rr = []
    for k, (c, a, b) in enumerate(pts):
        d = direction or _sub(pts[min(k + 1, len(pts) - 1)][0], pts[max(k - 1, 0)][0])
        bu = bulge(k) if bulge else None
        rr.append(EN.section(n, c, d, up, a, b, ex=ex, bulge=bu))
    start, f0 = len(m.vertices), len(m.faces)
    EN.loft(m, name, rr, tile, weights, role=role, caps=('flat', caps[1]) if open_root else caps,
            uv_rect=_inset(RECTS[tile]))
    if open_root:
        keep = [i for i in range(f0, len(m.faces)) if not all(start <= v < start + n for v in m.faces[i])]
        for arr in (m.faces, m.uv, m.roles, m.tiles):
            arr[f0:] = [arr[i] for i in keep]
        m.open_roots.append((name, open_root))
    return m


def clear_pair(m, open_piece, other):
    """Also keep `other`'s vertices >= CLEAR off `open_piece`'s surface (a socket's far side, e.g. sleeve vs mitt)."""
    m.open_roots.append((open_piece, other))


CLEAR = .0045


def _seg_tri_dist(p, a, b, c):
    """Closest point on triangle abc to p (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab = _sub(b, a); ac = _sub(c, a); ap = _sub(p, a)
    d1 = _dot(ab, ap); d2 = _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = _sub(p, b); d3 = _dot(ab, bp); d4 = _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return _add(a, _mul(ab, d1 / (d1 - d3)))
    cp = _sub(p, c); d5 = _dot(ab, cp); d6 = _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return _add(a, _mul(ac, d2 / (d2 - d6)))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return _add(b, _mul(_sub(c, b), w))
    den = 1. / (va + vb + vc)
    return _add(a, _add(_mul(ab, vb * den), _mul(ac, vc * den)))


def _clear_contacts(m):
    """Push any parent vertex closer than CLEAR to an open-rooted child's surface out to CLEAR (deterministic, at most
    a few millimetres; keeps the rig kit's generic contact sets one-directional)."""
    V = list(m.vertices)
    moved = 0
    for child, parent in m.open_roots:
        cset = set(m.parts[child])
        tris = [f for f in m.faces if f[0] in cset and f[1] in cset and f[2] in cset]
        for vi in sorted(set(m.parts[parent])):
            p = V[vi]
            best, bq = None, None
            for f in tris:
                q = _seg_tri_dist(p, V[f[0]], V[f[1]], V[f[2]])
                d = math.sqrt(_dot(_sub(p, q), _sub(p, q)))
                if best is None or d < best:
                    best, bq = d, q
            if best is not None and best < CLEAR:
                if best < 1e-9:
                    continue
                V[vi] = _add(bq, _mul(_sub(p, bq), CLEAR / best))
                moved += 1
    m.vertices = V
    m.cleared = moved


def face_band(m, part, k_lo, front_deg=150.):
    """Faces of `part` between rings k_lo and k_lo+1 whose centre lies within +-front_deg/2 of straight ahead (-Y)
    become the painted face (visor) and get cell-local UVs: u = bearing (-half .. +half -> 0 .. 1), v = up the band."""
    info = m.part_info[part]; n = info['n']; start = m.parts[part][0]
    ring = lambda k: [m.vertices[start + k * n + j] for j in range(n)]
    lo = ring(k_lo); hi = ring(k_lo + 1)
    cx = sum(p[0] for p in lo + hi) / (2. * n); cy = sum(p[1] for p in lo + hi) / (2. * n)
    z0 = sum(p[2] for p in lo) / n; z1 = sum(p[2] for p in hi) / n
    half = math.radians(front_deg / 2.)
    for fi, f in enumerate(m.faces):
        if not all(start <= v < start + n * info['rings'] for v in f):
            continue
        ks = [(v - start) // n for v in f]
        if min(ks) != k_lo or max(ks) != k_lo + 1:
            continue
        pts = [m.vertices[v] for v in f]
        mx = sum(p[0] for p in pts) / 3.; my = sum(p[1] for p in pts) / 3.
        bear = math.atan2(mx - cx, -(my - cy))          # 0 = straight ahead (-Y), + toward +X (character's left)
        if abs(bear) > half:
            continue
        uvs = []
        for p in pts:
            b = math.atan2(p[0] - cx, -(p[1] - cy))
            if abs(b - bear) > math.pi:
                b += TAU if b < bear else -TAU
            uvs.append((max(0., min(1., .5 + b / (2. * half))), max(0., min(1., (p[2] - z0) / (z1 - z0 or 1.)))))
        m.roles[fi] = 'face'; m.uv[fi] = uvs


def _finish(m, hover=0.):
    _clear_contacts(m)
    floor = min(v[2] for v in m.vertices)
    m.vertices = [(x, y, z - floor) for x, y, z in m.vertices]
    m.bones = {k: (x, y, z - floor) for k, (x, y, z) in m.bones.items()}
    m.bones['root'] = (0., 0., 0.)
    m.hover = hover
    return m


def _bones(spec, H):
    out = {'root': (0., 0., 0.)}
    for k, v in spec.items():
        out[k] = tuple(float(c) * H for c in v)
    return out


def _w(*pairs):
    return dict(pairs)


# ------------------------------------------------------------------ walker
def walker(p):
    H = p['height']; B = p['build']; Q = p['head_size']; ex = p['extras']
    sx = .215 * (1. + .4 * (B - 1.))          # shoulder pivots stay inside the hull and inside the rig's arm range
    spec = {'pelvis': (0, 0, .40), 'spine': (0, 0, .47), 'head': (0, -.005, .745),
            'upper_arm_l': (sx, 0, .615), 'forearm_l': (.345 * B, -.012, .53), 'hand_l': (.385 * B, -.03, .43),
            'upper_arm_r': (-sx, 0, .615), 'forearm_r': (-.345 * B, -.012, .53), 'hand_r': (-.385 * B, -.03, .43),
            'thigh_l': (.10 * B, 0, .36), 'shin_l': (.125 * B, -.015, .22), 'foot_l': (.14 * B, 0, .07),
            'thigh_r': (-.10 * B, 0, .36), 'shin_r': (-.125 * B, -.015, .22), 'foot_r': (-.14 * B, 0, .07)}
    m = RobotMesh('walker', p, _bones(spec, H))
    S = lambda *v: tuple(c * H for c in v)
    Z = (0., 0., 1.)
    # hull: stout kettle, widest low, a lid ledge at the top where the head sits
    hull = [(.27, .15, .13), (.33, .26, .23), (.45, .32 * B, .285), (.58, .315 * B, .28), (.68, .25 * B, .225), (.76, .16, .145)]
    rings = [(S(0, .01, z), a * H, b * H) for z, a, b in hull]
    tube(m, 'torso', rings, [_w(('pelvis', 1.)), _w(('pelvis', .7), ('spine', .3)), _w(('pelvis', .3), ('spine', .7)),
                             _w(('spine', 1.)), _w(('spine', 1.)), _w(('spine', 1.))], 0, n=10, ex=2.05, direction=Z)
    # head: a lid-like dome over the hull top; ring 0 sits inside the hull (the socket)
    if p['head'] == 'dome':
        head = [(.705, .10, .095), (.765, .195, .185), (.83, .215, .205), (.90, .17, .165), (.945, .075, .07)]
    else:                                   # lantern: taller, straighter head with a rounded crown
        head = [(.705, .10, .095), (.765, .17, .165), (.86, .18, .175), (.935, .155, .15), (.975, .06, .06)]
    head = [(z, a * Q, b * Q) for z, a, b in head]
    tube(m, 'face', [(S(0, -.005, z), a * H, b * H) for z, a, b in head], 'head', 1, n=8, ex=2.05, direction=Z,
         caps=('flat', 'centre'))
    face_band(m, 'face', 1, 160.)
    # arms: ball shoulder (root ring centred on the pivot, inside the hull) -> elbow -> wrist sleeve end past the pivot
    for s, sd in ((1, 'l'), (-1, 'r')):
        bu = m.bones; ua = bu['upper_arm_' + sd]; fa = bu['forearm_' + sd]; hd = bu['hand_' + sd]
        wr = _add(hd, _mul(_norm(_sub(hd, fa)), .028 * H))
        tube(m, 'sleeve_' + sd, [(ua, .072 * H, .072 * H), (_add(ua, _mul(_norm(_sub(fa, ua)), .045 * H)), .074 * H, .072 * H),
                                 (fa, .058 * H, .056 * H), (wr, .056 * H, .054 * H)],
             [_w(('upper_arm_' + sd, 1.)), _w(('upper_arm_' + sd, 1.)), _w(('upper_arm_' + sd, .5), ('forearm_' + sd, .5)),
              _w(('forearm_' + sd, 1.))], 2, n=5, ex=2.0, open_root='torso')
        if p['hands'] == 'mitt':
            mt = [(hd, .036 * H, .036 * H), (_add(hd, S(0, -.012, -.05)), .062 * H, .05 * H), (_add(hd, S(0, -.02, -.105)), .03 * H, .028 * H)]
        else:                               # pincer: a longer, flatter two-lobed grip (one loft, notched by the bulge)
            mt = [(hd, .036 * H, .036 * H), (_add(hd, S(0, -.016, -.06)), .066 * H, .04 * H), (_add(hd, S(0, -.03, -.125)), .042 * H, .016 * H)]
        bulge = (lambda k: (lambda th: 1. - .22 * max(0., math.cos(2 * th)) if k == 2 else 1.)) if p['hands'] == 'pincer' else None
        tube(m, 'mitt_' + sd, mt, 'hand_' + sd, 3, n=5, ex=2.1, caps=('flat', 'centre'), bulge=bulge)
        clear_pair(m, 'sleeve_' + sd, 'mitt_' + sd)
        # legs: hip socket inside the hull -> knee -> ankle end past the foot pivot
        th = bu['thigh_' + sd]; sh = bu['shin_' + sd]; ft = bu['foot_' + sd]
        an = _add(ft, S(0, -.004, -.012))
        tube(m, 'trouser_' + sd, [(th, .085 * H, .08 * H), (sh, .075 * H, .072 * H), (an, .062 * H, .06 * H)],
             [_w(('thigh_' + sd, 1.)), _w(('thigh_' + sd, .5), ('shin_' + sd, .5)), _w(('shin_' + sd, 1.))], 4, n=6,
             open_root='torso')
        if p['feet'] == 'pad':
            fp = [(_add(ft, S(0, 0, .012)), .04 * H, .04 * H), (_add(ft, S(0, -.03, -.03)), .095 * H, .12 * H),
                  (_add(ft, S(0, -.03, -.075)), .088 * H, .112 * H)]
        else:
            fp = [(_add(ft, S(0, 0, .012)), .04 * H, .04 * H), (_add(ft, S(0, -.05, -.03)), .085 * H, .15 * H),
                  (_add(ft, S(0, -.055, -.075)), .08 * H, .14 * H)]
        tube(m, 'boot_' + sd, fp, 'foot_' + sd, 5, n=6, ex=2.3, direction=(0., 0., -1.))
        clear_pair(m, 'trouser_' + sd, 'boot_' + sd)
    _extras(m, p, H, S)
    return _finish(m)


# ------------------------------------------------------------------ brute
def brute(p):
    H = p['height']; B = p['build']; Q = p['head_size']; ex = p['extras']
    sx = .20 * (1. + .5 * (B - 1.))
    spec = {'pelvis': (0, 0, .44), 'spine': (0, 0, .52), 'head': (0, -.01, .815),
            'upper_arm_l': (sx, .005, .73), 'forearm_l': (.27 * B, -.015, .56), 'hand_l': (.30 * B, -.04, .395),
            'upper_arm_r': (-sx, .005, .73), 'forearm_r': (-.27 * B, -.015, .56), 'hand_r': (-.30 * B, -.04, .395),
            'thigh_l': (.085 * B, 0, .445), 'shin_l': (.115 * B, -.01, .24), 'foot_l': (.13 * B, 0, .075),
            'thigh_r': (-.085 * B, 0, .445), 'shin_r': (-.115 * B, -.01, .24), 'foot_r': (-.13 * B, 0, .075)}
    m = RobotMesh('brute', p, _bones(spec, H))
    S = lambda *v: tuple(c * H for c in v)
    Z = (0., 0., 1.)
    chest = [(.385, .155 * B, .12), (.47, .18 * B, .14), (.60, .215 * B, .155), (.72, .25 * B, .17), (.835, .155, .13)]
    tube(m, 'torso', [(S(0, .012, z), a * H, b * H) for z, a, b in chest],
         [_w(('pelvis', 1.)), _w(('pelvis', .6), ('spine', .4)), _w(('spine', 1.)), _w(('spine', 1.)), _w(('spine', 1.))],
         0, n=8, ex=2.05, direction=Z)
    if p['head'] == 'dome':
        head = [(.795, .055, .06), (.835, .085, .09), (.885, .092, .097), (.93, .072, .077), (.955, .03, .032)]
    else:                                   # helm: a lower, broader cap with a brow ridge (bulge)
        head = [(.795, .055, .06), (.83, .095, .10), (.875, .10, .105), (.915, .085, .09), (.94, .035, .037)]
    head = [(z, a * Q, b * Q) for z, a, b in head]
    brow = (lambda k: (lambda th: 1. + .10 * max(0., math.cos(th)) ** 3 if k == 2 else 1.)) if p['head'] == 'helm' else None
    tube(m, 'face', [(S(0, -.012, z), a * H, b * H) for z, a, b in head], 'head', 1, n=8, ex=2.05, direction=Z,
         caps=('flat', 'centre'), bulge=brow)
    face_band(m, 'face', 1, 150.)
    for s, sd in ((1, 'l'), (-1, 'r')):
        bu = m.bones; ua = bu['upper_arm_' + sd]; fa = bu['forearm_' + sd]; hd = bu['hand_' + sd]
        if 'pauldrons' in ex:
            # shoulder dome fixed to the chest; the arm's root ring turns inside it
            c = _add(ua, S(s * .03, 0, .025))
            root = (s * .15 * B * H, ua[1], c[2] - .01 * H)
            tube(m, 'pauldron_' + sd, [(root, .05 * H, .05 * H), (c, .105 * H, .10 * H), (_add(c, S(s * .055, 0, .01)), .062 * H, .06 * H)],
                 'spine', 6, n=6, ex=2.3, direction=(s * 1., 0., .25), up=(0., 0., 1.), caps=('flat', 'centre'), open_root='torso')
        dirf = _norm(_sub(hd, fa))
        cuff = _add(hd, _mul(dirf, -.012 * H))
        plug = _add(hd, _mul(dirf, .03 * H))
        mid = _add(fa, _mul(_sub(hd, fa), .45))
        tube(m, 'sleeve_' + sd, [(ua, .056 * H, .056 * H), (fa, .055 * H, .055 * H), (mid, .078 * H, .074 * H),
                                 (cuff, .064 * H, .062 * H), (plug, .026 * H, .025 * H)],
             [_w(('upper_arm_' + sd, 1.)), _w(('upper_arm_' + sd, .5), ('forearm_' + sd, .5)), _w(('forearm_' + sd, 1.)),
              _w(('forearm_' + sd, 1.)), _w(('forearm_' + sd, 1.))], 2, n=6, open_root='torso')
        if p['hands'] == 'fist':
            mt = [(hd, .04 * H, .04 * H), (_add(hd, S(0, -.01, -.055)), .072 * H, .066 * H), (_add(hd, S(0, -.016, -.11)), .045 * H, .042 * H)]
        else:
            mt = [(hd, .04 * H, .04 * H), (_add(hd, S(0, -.012, -.055)), .06 * H, .05 * H), (_add(hd, S(0, -.02, -.115)), .032 * H, .028 * H)]
        tube(m, 'mitt_' + sd, mt, 'hand_' + sd, 3, n=5 if p['hands'] == 'fist' else 6, ex=2.3, caps=('flat', 'centre'))
        clear_pair(m, 'sleeve_' + sd, 'mitt_' + sd)
        th = bu['thigh_' + sd]; sh = bu['shin_' + sd]; ft = bu['foot_' + sd]
        an = _add(ft, S(0, -.004, -.012))
        tube(m, 'trouser_' + sd, [(th, .055 * H, .052 * H), (sh, .078 * H, .074 * H), (an, .062 * H, .06 * H)],
             [_w(('thigh_' + sd, 1.)), _w(('thigh_' + sd, .5), ('shin_' + sd, .5)), _w(('shin_' + sd, 1.))], 4, n=6, open_root='torso')
        if p['feet'] == 'pad':
            fp = [(_add(ft, S(0, 0, .01)), .036 * H, .036 * H), (_add(ft, S(0, -.025, -.03)), .075 * H, .095 * H),
                  (_add(ft, S(0, -.025, -.075)), .07 * H, .09 * H)]
        else:
            fp = [(_add(ft, S(0, 0, .01)), .036 * H, .036 * H), (_add(ft, S(0, -.04, -.03)), .068 * H, .12 * H),
                  (_add(ft, S(0, -.045, -.075)), .064 * H, .112 * H)]
        tube(m, 'boot_' + sd, fp, 'foot_' + sd, 5, n=6, ex=2.3, direction=(0., 0., -1.))
        clear_pair(m, 'trouser_' + sd, 'boot_' + sd)
    _extras(m, p, H, S)
    return _finish(m)


# ------------------------------------------------------------------ floater
def floater(p):
    """Hover unit mapped onto human16_v1 as RIGKIT-API section 6 publishes: hull + vanes + nozzle rigid on the spine
    (the rig kit maps the shell to pelvis + spine; one rigid bone means zero deformation), lid -> head, arm pods ->
    arm chains; the six leg joints stay in the skeleton with zero weight (walk and run read as a glide). Mesh floor =
    nozzle tip at 0; the hover height is a grounding offset (rig node extras hover_m, validated with profile='hover')."""
    H = p['height']; B = p['build']; Q = p['head_size']; ex = p['extras']
    sx = .19 * (1. + .4 * (B - 1.)); bk = 1. + .4 * (B - 1.)
    spec = {'pelvis': (0, 0, .42), 'spine': (0, 0, .48), 'head': (0, -.01, .72),
            'upper_arm_l': (sx, 0, .54), 'forearm_l': (.37 * bk, -.02, .465), 'hand_l': (.40 * bk, -.05, .36),
            'upper_arm_r': (-sx, 0, .54), 'forearm_r': (-.37 * bk, -.02, .465), 'hand_r': (-.40 * bk, -.05, .36),
            'thigh_l': (.07, 0, .38), 'shin_l': (.08, 0, .23), 'foot_l': (.085, 0, .08),
            'thigh_r': (-.07, 0, .38), 'shin_r': (-.08, 0, .23), 'foot_r': (-.085, 0, .08)}
    m = RobotMesh('floater', p, _bones(spec, H))
    S = lambda *v: tuple(c * H for c in v)
    Z = (0., 0., 1.)
    hull = [(0., .045, .045), (.07, .15, .145), (.19, .27 * B, .26), (.35, .32 * B, .305), (.50, .305 * B, .29), (.62, .22, .21)]
    tube(m, 'torso', [(S(0, .005, z), a * H, b * H) for z, a, b in hull], 'spine', 0, n=10, ex=2.05, direction=Z)
    # slim neck buried in the hull, then the lid flares above the hull's top ring (no hull vertex inside the head)
    if p['head'] == 'lid':
        head = [(.55, .09, .088), (.62, .13, .125), (.67, .315, .30), (.76, .33, .315), (.88, .255, .245), (.97, .10, .095)]
    else:
        head = [(.55, .09, .088), (.62, .13, .125), (.68, .27, .26), (.79, .29, .28), (.91, .22, .21), (1.0, .08, .077)]
    head = [(z, a * Q, b * Q) for z, a, b in head]
    tube(m, 'face', [(S(0, -.006, z), a * H, b * H) for z, a, b in head], 'head', 1, n=10, ex=2.05, direction=Z,
         caps=('flat', 'centre'))
    face_band(m, 'face', 1, 150.)
    for s, sd in ((1, 'l'), (-1, 'r')):
        bu = m.bones; ua = bu['upper_arm_' + sd]; fa = bu['forearm_' + sd]; hd = bu['hand_' + sd]
        wr = _add(hd, _mul(_norm(_sub(hd, fa)), .022 * H))
        tube(m, 'sleeve_' + sd, [(ua, .055 * H, .055 * H), (fa, .046 * H, .045 * H), (wr, .042 * H, .041 * H)],
             [_w(('upper_arm_' + sd, 1.)), _w(('upper_arm_' + sd, .5), ('forearm_' + sd, .5)), _w(('forearm_' + sd, 1.))],
             2, n=6, open_root='torso')
        if p['hands'] == 'pincer':
            mt = [(hd, .032 * H, .032 * H), (_add(hd, S(0, -.014, -.055)), .062 * H, .036 * H), (_add(hd, S(0, -.024, -.115)), .04 * H, .014 * H)]
        else:
            mt = [(hd, .032 * H, .032 * H), (_add(hd, S(0, -.012, -.05)), .055 * H, .046 * H), (_add(hd, S(0, -.02, -.10)), .027 * H, .024 * H)]
        bulge = (lambda k: (lambda th: 1. - .25 * max(0., math.cos(2 * th)) if k == 2 else 1.)) if p['hands'] == 'pincer' else None
        tube(m, 'mitt_' + sd, mt, 'hand_' + sd, 3, n=5, ex=2.2, caps=('flat', 'centre'), bulge=bulge)
        clear_pair(m, 'sleeve_' + sd, 'mitt_' + sd)
        # vanes: flattened fins rooted inside the lower hull, swept out and back; rigid on the pelvis
        root = S(s * .10, .03, .13); mid = S(s * .22, .08, .085); tip = S(s * .31, .12, .04)
        tube(m, 'trouser_' + sd, [(root, .05 * H, .03 * H), (mid, .06 * H, .02 * H), (tip, .016 * H, .007 * H)],
             'spine', 4, n=5, ex=2.2, up=(0., 0., 1.), caps=('flat', 'centre'), open_root='torso')
    _extras(m, p, H, S)
    return _finish(m, hover=HOVER['floater'] * H)


# ------------------------------------------------------------------ shared optional pieces
def _extras(m, p, H, S):
    ex = p['extras']; body = m.body; bu = m.bones
    top = max(v[2] for v in (m.vertices[i] for i in m.parts['face']))
    if 'antenna' in ex:
        b0 = _add(bu['head'], S(.035, .03, 0.))
        b0 = (b0[0], b0[1], top - .03 * H)
        pts = [(b0, .014 * H), (_add(b0, S(.012, .02, .09)), .010 * H), (_add(b0, S(.02, .035, .16)), .004 * H)]
        rr = []
        for k, (c, r) in enumerate(pts):
            d = _sub(pts[min(k + 1, 2)][0], pts[max(k - 1, 0)][0])
            rr.append(EN.section(3, c, d, (0., -1., 0.), r * 1.2, r * .8, ex=2.))
        EN.loft(m, 'acc_head', rr, 7, 'head', uv_rect=_inset(RECTS[7]))
    if 'ear_pods' in ex:
        n = m.part_info['face']['n']; st = m.parts['face'][0]
        widest = max(range(m.part_info['face']['rings']), key=lambda k: max(abs(m.vertices[st + k * n + j][0]) for j in range(n)))
        ring = [m.vertices[st + widest * n + j] for j in range(n)]
        z = sum(v[2] for v in ring) / n; hw = max(abs(v[0]) for v in ring)
        for s, sd in ((1, 'l'), (-1, 'r')):
            c = (s * (hw - .045 * H), bu['head'][1], z)
            tube(m, 'acc_ear_' + sd, [(c, .022 * H, .022 * H), (_add(c, (s * .055 * H, 0., 0.)), .05 * H, .05 * H),
                                      (_add(c, (s * .075 * H, 0., 0.)), .036 * H, .036 * H)], 'head', 6,
                 n=6, ex=2.3, direction=(s * 1., 0., 0.), caps=('flat', 'centre'), open_root='face')
    if 'backpack' in ex:
        sp = bu['spine']
        back = max(m.vertices[i][1] for i in m.parts['torso'] if abs(m.vertices[i][2] - sp[2] - .12 * H) < .08 * H)
        c = (0., back - .03 * H, sp[2] + .12 * H)
        rr = [(c, .10 * H, .11 * H), (_add(c, S(0, .05, 0)), .12 * H, .13 * H), (_add(c, S(0, .10, 0)), .08 * H, .09 * H)]
        tube(m, 'acc_back', rr, 'spine', 6, n=6, ex=2.4, direction=(0., 1., 0.), up=(0., 0., 1.), caps=('flat', 'centre'), open_root='torso')
    if 'vents' in ex:
        # two rounded exhaust stubs on the upper back, angled out
        sp = bu['spine']
        for s, sd in ((1, 'l'), (-1, 'r')):
            hz = sp[2] + (.20 if body != 'walker' else .17) * H
            near = sorted(m.parts['torso'], key=lambda i: abs(m.vertices[i][2] - hz))[:12]
            back = max(m.vertices[i][1] for i in near)
            c = (s * .08 * H * p['build'], back - .04 * H, hz)
            tube(m, 'acc_vent_' + sd, [(c, .03 * H, .03 * H), (_add(c, S(s * .02, .07, .05)), .026 * H, .026 * H)], 'spine', 7,
                 n=5, ex=2.2, caps=('flat', 'flat'), open_root='torso')


def build(body, values):
    p = resolve(body, values)
    m = {'walker': walker, 'brute': brute, 'floater': floater}[body](p)
    if len(m.faces) >= BUDGET:
        raise ValueError('robot %s over budget: %d tris (limit < %d)' % (body, len(m.faces), BUDGET))
    return m


# ------------------------------------------------------------------ connectivity joins (registered on the core table)
def _robot_joins():
    out = [('neck', 'face', 0, ('torso',), 'buried', None)]
    for s in 'lr':
        out += [('shoulder_' + s, 'sleeve_' + s, 0, ('torso', 'pauldron_' + s), 'anchored', None),
                ('wrist_' + s, 'mitt_' + s, 0, ('sleeve_' + s,), 'buried', None),
                ('hip_' + s, 'trouser_' + s, 0, ('torso',), 'buried', None),
                ('ankle_' + s, 'boot_' + s, 0, ('trouser_' + s,), 'buried', None),
                ('pauldron_' + s, 'pauldron_' + s, 0, ('torso',), 'buried', None),
                ('ear_' + s, 'acc_ear_' + s, 0, ('face',), 'buried', None),
                ('vent_' + s, 'acc_vent_' + s, 0, ('torso',), 'buried', None)]
    out += [('antenna', 'acc_head', 0, ('face',), 'buried', None), ('backpack', 'acc_back', 0, ('torso',), 'buried', None)]
    return out


for _t in TOPOLOGY.values():
    CN.JOINS.setdefault(_t, _robot_joins())
