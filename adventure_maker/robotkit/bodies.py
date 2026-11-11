"""Segmented low-poly robot bodies on the human16_v1 rig (ROBOTS lane).

Three archetypes, each a handful of rigid lofted parts (one bone per vertex, no blended skin): `walker` (hunched pod
on bent legs with two long prods), `brute` (wide chest, block fists, two back stacks), `drone` (flat hull, eye pod,
under-slung barrel, two finned side pods, tail fin, belly emitter; hovers). Every body is mirrored about x = 0 from one side, so the
rest mesh is bilaterally symmetric by construction. Generator space: z up, the front is -y, the robot's left is +x.

The mesh object carries the attributes the shared pose library reads (core/pose.body_metrics, ext/robot_pose):
kind, body (the stock pose family: walker / brute / floater), bones, parents, vertices, faces, uv, roles, weights,
parts, params, hover. Stdlib only.
"""
import math

RIG = 'human16_v1'
PARENTS = {'root': None, 'pelvis': 'root', 'spine': 'pelvis', 'head': 'spine',
           'upper_arm_l': 'spine', 'forearm_l': 'upper_arm_l', 'hand_l': 'forearm_l',
           'upper_arm_r': 'spine', 'forearm_r': 'upper_arm_r', 'hand_r': 'forearm_r',
           'thigh_l': 'pelvis', 'shin_l': 'thigh_l', 'foot_l': 'shin_l',
           'thigh_r': 'pelvis', 'shin_r': 'thigh_r', 'foot_r': 'shin_r'}
ARCHETYPES = ('walker', 'brute', 'drone')
POSE_BODY = {'walker': 'walker', 'brute': 'brute', 'drone': 'floater'}      # stock clip family (ext/robot_pose)
TEMPLATE = {'walker': 'walker_patrol_v1', 'brute': 'brute_slam_v1', 'drone': 'hover_drone_v1'}
HOVERS = ('drone',)
DEFAULTS = {'walker': {'height': 1.20, 'build': 1.0}, 'brute': {'height': 1.95, 'build': 1.0},
            'drone': {'height': 1.30, 'build': 1.0}}
# coat atlas: 64 x 64 texels on a 16 texel grid; name -> (column, row from the top, span). The mark gets a 2 x 2 block.
TILE_CELLS = {'shell': (0, 0, 1), 'livery': (1, 0, 1), 'trim': (2, 0, 1), 'joint': (3, 0, 1),
              'vent': (0, 1, 1), 'light': (1, 1, 1), 'tip': (2, 1, 1), 'top': (3, 1, 1),
              'mark': (0, 2, 2), 'mark_top': (2, 2, 1), 'sole': (3, 2, 1)}
TILES = list(TILE_CELLS)
ATLAS = 64          # coat atlas edge in texels
TILE = 16           # grid step in texels


def tile_rect(name):
    """(u0, v0, u1, v1) of a tile, v up, inset half a texel."""
    c, r, n = TILE_CELLS[name]
    return ((c * TILE + .5) / ATLAS, 1. - ((r + n) * TILE - .5) / ATLAS, ((c + n) * TILE - .5) / ATLAS, 1. - (r * TILE + .5) / ATLAS)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def R(cx, cy, z, hx, hy):
    """Horizontal rectangle ring; side 0 is the front (-y) face, side 2 the back."""
    return [(cx - hx, cy - hy, z), (cx + hx, cy - hy, z), (cx + hx, cy + hy, z), (cx - hx, cy + hy, z)]


def HX(cx, cy, z, hx, hy, f=.6):
    """Horizontal hexagon ring with flat front and back; side 0 is the front face, side 3 the back."""
    w = hx * f
    return [(cx - w, cy - hy, z), (cx + w, cy - hy, z), (cx + hx, cy, z), (cx + w, cy + hy, z), (cx - w, cy + hy, z), (cx - hx, cy, z)]


def RY(cx, y, cz, hx, hz):
    """Rectangle ring in the x/z plane (for parts that run front to back); side 2 is the top face."""
    return [(cx - hx, y, cz - hz), (cx + hx, y, cz - hz), (cx + hx, y, cz + hz), (cx - hx, y, cz + hz)]


def RX(x, cy, cz, hy, hz):
    """Rectangle ring in the y/z plane (for parts that run sideways)."""
    return [(x, cy - hy, cz - hz), (x, cy + hy, cz - hz), (x, cy + hy, cz + hz), (x, cy - hy, cz + hz)]


def _side(name, suffix):
    """`x_s` -> `x_l` / `x_r`; only the trailing side tag (torso_stack_s must not become torso_ltack_l)."""
    return name[:-2] + suffix if name.endswith('_s') else name


class Body:
    kind = 'human'
    rig = RIG
    skeleton = RIG

    def __init__(self, archetype, params):
        self.archetype = archetype
        self.body = POSE_BODY[archetype]
        self.id = 'robotkit_' + archetype
        self.topology = 'robotkit_%s_v1' % archetype
        self.params = params
        self.parents = dict(PARENTS)
        self.bones = {}
        self.vertices, self.faces, self.uv, self.roles, self.tiles, self.weights = [], [], [], [], [], []
        self.parts, self.part_info, self.open_roots, self.cleared = {}, {}, [], 0
        self.local_uv = []
        self.hover = 0.
        self._s = float(params['height'])
        self._b = float(params.get('build', 1.))

    # ---------------------------------------------------------------- primitives (unit design space)
    def _p(self, p, sign):
        return (p[0] * sign * self._s * self._b, p[1] * self._s * self._b, p[2] * self._s)

    def _v(self, p, bone, part):
        self.vertices.append(p)
        self.weights.append({bone: 1.})
        self.parts.setdefault(part, []).append(len(self.vertices) - 1)
        return len(self.vertices) - 1

    def _tri(self, ids, uvs, tile, centre):
        a, b, c = (self.vertices[i] for i in ids)
        n = _cross(_sub(b, a), _sub(c, a))
        f = tuple((a[k] + b[k] + c[k]) / 3. for k in range(3))
        if centre is not None and _dot(n, _sub(f, centre)) < 0:
            ids = (ids[0], ids[2], ids[1]); uvs = (uvs[0], uvs[2], uvs[1])
        if tile == 'eye':
            rect = (.02, .02, .98, .98); role = 'face'
        else:
            rect = tile_rect(tile); role = 'coat'
        u0, v0, u1, v1 = rect
        self.faces.append(tuple(ids))
        self.uv.append([(u0 + (u1 - u0) * u, v0 + (v1 - v0) * v) for u, v in uvs])
        self.roles.append(role)
        self.tiles.append(tile)
        self.local_uv.append(tuple(uvs))

    def loft(self, part, rings, bone, tiles='shell', cap0=None, cap1=None, sign=1.):
        """Rings of equal point count joined by quad bands; caps are fans. bone: one name or one per ring (`_s` is
        replaced by the side). tiles: a name, or f(band, side) -> name. Faces are wound outward from the centroid."""
        n = len(rings[0])
        suffix = '_l' if sign > 0 else '_r'
        part = _side(part, suffix)
        bones = [bone] * len(rings) if isinstance(bone, str) else list(bone)
        pts = [[self._p(p, sign) for p in ring] for ring in rings]
        flat = [p for ring in pts for p in ring]
        centre = tuple(sum(p[k] for p in flat) / len(flat) for k in range(3))
        ids = [[self._v(p, _side(b, suffix), part) for p in ring] for ring, b in zip(pts, bones)]
        for k in range(len(rings) - 1):
            for j in range(n):
                t = tiles(k, j) if callable(tiles) else tiles
                if t is None:
                    continue
                a, b, c, d = ids[k][j], ids[k][(j + 1) % n], ids[k + 1][(j + 1) % n], ids[k + 1][j]
                self._tri((a, b, c), ((0, 0), (1, 0), (1, 1)), t, centre)
                self._tri((a, c, d), ((0, 0), (1, 1), (0, 1)), t, centre)
        for ring_ids, ring, t in ((ids[0], pts[0], cap0), (ids[-1], pts[-1], cap1)):
            if t is None:
                continue
            ext = [max(p[k] for p in ring) - min(p[k] for p in ring) for k in range(3)]
            ax = sorted(range(3), key=lambda k: -ext[k])[:2]
            ax.sort()
            lo = [min(p[k] for p in ring) for k in ax]
            sp = [max(1e-9, ext[k]) for k in ax]
            uv = [((p[ax[0]] - lo[0]) / sp[0], (p[ax[1]] - lo[1]) / sp[1]) for p in ring]
            for j in range(1, n - 1):
                self._tri((ring_ids[0], ring_ids[j], ring_ids[j + 1]), (uv[0], uv[j], uv[j + 1]), t, centre)
        self.part_info.setdefault(part, {'n': n, 'rings': len(rings), 'role': 'coat'})

    def blade(self, part, tri, bone, tile='livery', sign=1.):
        """A flat triangle drawn on both sides (two faces, own vertices), for fins."""
        suffix = '_l' if sign > 0 else '_r'
        part = _side(part, suffix); bone = _side(bone, suffix)
        pts = [self._p(p, sign) for p in tri]
        for order in ((0, 1, 2), (0, 2, 1)):
            ids = tuple(self._v(pts[i], bone, part) for i in order)
            self._tri(ids, tuple(((0, 0), (1, 0), (.5, 1))[i] for i in order), tile, None)

    def set_bones(self, half):
        """half: {name or name_s: (x, y, z)} in unit space; `_s` names are mirrored to _l / _r."""
        for name, p in half.items():
            if name.endswith('_s'):
                self.bones[name[:-2] + '_l'] = self._p(p, 1.)
                self.bones[name[:-2] + '_r'] = self._p(p, -1.)
            else:
                self.bones[name] = self._p(p, 1.)
        missing = [n for n in PARENTS if n not in self.bones]
        if missing:
            raise ValueError('robot body %s lacks bones %s' % (self.archetype, missing))
        self.bones = {n: self.bones[n] for n in PARENTS}


# -------------------------------------------------------------------- archetypes (unit design space: top = 1.0)
# Joint rule (rig kit connectivity gate, 3 mm): at every joint one piece is the socket (a closed loft that contains
# the child bone's pivot) and the other is the pin (a ring centred on that pivot). Rotating a ring about its own
# centre keeps part of it inside the socket, so rigid one-bone parts stay joined on every key.
def walker(m):
    """Hunched pod on reverse-knee legs, wide visor head pushed forward, two downward prods."""
    m.set_bones({'root': (0, 0, 0), 'pelvis': (0, 0, .44), 'spine': (0, 0, .50), 'head': (0, -.06, .735),
                 'upper_arm_s': (.17, 0, .67), 'forearm_s': (.215, -.01, .53), 'hand_s': (.225, -.04, .39),
                 'thigh_s': (.10, 0, .40), 'shin_s': (.12, .04, .25), 'foot_s': (.125, 0, .075)})
    m.loft('torso', [R(0, .01, .44, .11, .085), R(0, -.015, .62, .19, .135), R(0, -.03, .76, .16, .11)], 'spine',
           lambda k, j: ('mark' if j == 0 else 'vent' if j == 2 else 'shell') if k == 1 else ('trim' if j == 0 else 'shell'),
           cap0='sole', cap1='top')
    m.loft('hips', [R(0, 0, .33, .12, .07), R(0, 0, .43, .13, .075), R(0, 0, .50, .05, .04)], 'pelvis', 'joint',
           cap0='sole', cap1='sole')
    m.loft('face', [R(0, -.06, .735, .07, .055), R(0, -.10, .79, .14, .115), R(0, -.065, .87, .10, .085)], 'head',
           lambda k, j: 'eye' if (k, j) == (1, 0) else ('livery' if k == 1 else 'shell'), cap1='top')
    m.blade('spike_fin', [(0, -.10, .87), (0, .015, .87), (0, .10, 1.0)], 'head', 'livery')    # base on the head's top cap
    m.blade('spike_fin', [(-.035, 0, .87), (.035, 0, .87), (0, .10, 1.0)], 'head', 'livery')    # cross blade: the fin also shows from the front and back
    for sg in (1., -1.):
        m.loft('sleeve_s', [RX(.17, 0, .67, .045, .045), RX(.215, 0, .685, .07, .068), RX(.275, 0, .685, .055, .052)],
               'upper_arm_s', lambda k, j: 'top' if j == 2 else 'livery', cap0='sole', cap1='light', sign=sg)
        m.loft('sleeve_s', [R(.238, 0, .64, .026, .03), R(.215, -.01, .53, .028, .03)], 'upper_arm_s', 'joint', sign=sg)   # clear of the torso: only the shoulder ring may touch it
        m.loft('mitt_s', [R(.215, -.01, .555, .045, .048), R(.224, -.038, .375, .04, .042)], 'forearm_s', 'trim',
               cap0='sole', cap1='top', sign=sg)
        m.loft('mitt_s', [R(.225, -.04, .39, .024, .024), R(.232, -.07, .19, .003, .003)], 'hand_s', 'tip', cap1='tip', sign=sg)
        m.loft('trouser_s', [R(.10, 0, .41, .045, .055), R(.12, .04, .235, .04, .048)], 'thigh_s', 'shell',
               cap0='top', cap1='sole', sign=sg)
        m.loft('trouser_s', [R(.12, .04, .25, .028, .03), R(.125, 0, .075, .026, .028)], 'shin_s', 'joint', sign=sg)
        m.loft('boot_s', [R(.125, -.03, 0., .05, .10), R(.125, -.015, .095, .038, .06)], 'foot_s', 'shell',
               cap0='sole', cap1='light', sign=sg)


def brute(m):
    """Tall inverted wedge: wide chest, livery pauldrons, block gauntlets and fists, small sunk head, two back stacks."""
    m.set_bones({'root': (0, 0, 0), 'pelvis': (0, 0, .455), 'spine': (0, 0, .53), 'head': (0, -.05, .83),
                 'upper_arm_s': (.21, 0, .70), 'forearm_s': (.305, 0, .645), 'hand_s': (.32, -.03, .47),
                 'thigh_s': (.10, 0, .45), 'shin_s': (.12, 0, .265), 'foot_s': (.135, 0, .085)})
    m.loft('torso', [R(0, 0, .44, .13, .10), R(0, -.01, .62, .21, .15), R(0, -.02, .86, .245, .155)], 'spine',
           lambda k, j: ('mark' if j == 0 else 'vent' if j == 2 else 'shell') if k == 1 else ('trim' if j == 0 else 'shell'),
           cap0='sole', cap1='top')
    m.loft('hips', [R(0, 0, .36, .15, .085), R(0, 0, .46, .16, .09), R(0, 0, .53, .07, .05)], 'pelvis', 'joint',
           cap0='sole', cap1='sole')
    m.loft('face', [R(0, -.05, .83, .075, .08), R(0, -.055, .95, .065, .07)], 'head',
           lambda k, j: 'eye' if j == 0 else 'shell', cap1='light')
    for sg in (1., -1.):
        m.loft('torso_stack_s', [R(.15, .13, .80, .04, .04), R(.15, .14, 1.0, .035, .035)], 'spine', 'trim', cap1='tip', sign=sg)
        m.loft('sleeve_s', [RX(.21, 0, .70, .06, .06), RX(.255, -.005, .74, .115, .115), RX(.375, -.005, .74, .095, .10)],
               'upper_arm_s', lambda k, j: 'top' if j == 2 else 'livery', cap0='sole', cap1='light', sign=sg)
        m.loft('mitt_s', [R(.305, -.005, .645, .05, .055), R(.315, -.02, .58, .08, .095), R(.32, -.03, .45, .085, .105)],
               'forearm_s', lambda k, j: 'joint' if k == 0 else 'trim', cap0='sole', cap1='sole', sign=sg)
        m.loft('mitt_s', [R(.32, -.03, .47, .045, .05), R(.325, -.035, .43, .09, .115), R(.325, -.035, .31, .085, .11)],
               'hand_s', lambda k, j: 'joint' if k == 0 else ('tip' if j == 0 else 'shell'), cap1='sole', sign=sg)
        m.loft('trouser_s', [R(.10, 0, .45, .035, .04), R(.12, 0, .265, .045, .05)], 'thigh_s', 'joint', sign=sg)
        m.loft('trouser_s', [R(.12, 0, .29, .07, .075), R(.135, 0, .07, .085, .09)], 'shin_s',
               lambda k, j: 'trim' if j == 0 else 'shell', cap0='sole', cap1='top', sign=sg)
        m.loft('boot_s', [R(.135, -.035, 0., .10, .15), R(.135, 0, .085, .055, .06)], 'foot_s', 'shell', cap0='sole', sign=sg)


def drone(m):
    """Hovering flat hex hull, nose eye pod with an under-slung barrel, two finned side pods, tail fin, belly emitter.
    The hull rides in the upper half of the rig's height; the leg joints carry no vertices (rig.json hover)."""
    m.set_bones({'root': (0, 0, 0), 'pelvis': (0, 0, .56), 'spine': (0, 0, .64), 'head': (0, -.22, .66),
                 'upper_arm_s': (.17, 0, .68), 'forearm_s': (.31, 0, .66), 'hand_s': (.34, 0, .75),
                 'thigh_s': (.07, .06, .52), 'shin_s': (.08, .10, .38), 'foot_s': (.09, .13, .23)})
    m.loft('torso', [HX(0, 0, .57, .12, .13), HX(0, 0, .63, .25, .26), HX(0, 0, .71, .23, .24), HX(0, 0, .765, .17, .18)], 'spine',
           lambda k, j: ('vent' if j == 3 else 'joint') if k == 0 else (('trim' if j in (0, 3) else 'shell') if k == 1 else 'livery'),
           cap0='sole', cap1='mark_top')
    m.loft('hips', [R(0, 0, .50, .025, .025), R(0, 0, .555, .075, .075), R(0, 0, .64, .05, .05)], 'pelvis',
           lambda k, j: 'trim' if k == 0 else 'joint', cap0='tip')
    m.loft('face', [RY(0, -.22, .66, .085, .04), RY(0, -.33, .655, .115, .07), RY(0, -.40, .65, .105, .06)], 'head',
           lambda k, j: 'top' if j == 2 else 'shell', cap0='sole', cap1='eye')
    m.loft('face_barrel', [RY(0, -.30, .60, .025, .025), RY(0, -.50, .60, .02, .02)], 'head', 'joint', cap1='tip')
    m.blade('spike_fin', [(0, .08, .74), (0, .25, .72), (0, .30, 1.0)], 'spine', 'livery')
    m.blade('spike_fin', [(-.05, .21, .72), (.05, .21, .72), (0, .30, 1.0)], 'spine', 'livery')       # cross blade
    for sg in (1., -1.):
        m.loft('sleeve_s', [RX(.17, 0, .68, .03, .022), RX(.31, 0, .66, .03, .022)], 'upper_arm_s', 'joint', sign=sg)
        m.loft('mitt_s', [R(.335, 0, .57, .035, .06), R(.335, 0, .66, .055, .095), R(.335, 0, .78, .04, .07)], 'forearm_s',
               lambda k, j: 'trim' if k == 0 else ('mark' if j == 1 else 'livery'), cap0='tip', cap1='light', sign=sg)   # side 1 = the outer face
        m.blade('spike_pod_s', [(.34, -.05, .75), (.34, .06, .75), (.34, .10, .93)], 'hand_s', 'livery', sign=sg)
        m.blade('spike_pod_s', [(.308, .01, .75), (.368, .01, .75), (.34, .10, .93)], 'hand_s', 'livery', sign=sg)   # cross blade


BUILDERS = {'walker': walker, 'brute': brute, 'drone': drone}


def build(archetype, params=None):
    if archetype not in BUILDERS:
        raise ValueError('unknown robot archetype %r (have %s)' % (archetype, ', '.join(ARCHETYPES)))
    p = dict(DEFAULTS[archetype])
    for k, v in (params or {}).items():
        if k not in p:
            raise ValueError('unknown %s parameter %r' % (archetype, k))
        p[k] = float(v)
    m = Body(archetype, p)
    BUILDERS[archetype](m)
    if archetype in HOVERS:                       # a hovering body rides where it is drawn: hover = its lowest vertex
        m.hover = min(v[2] for v in m.vertices)
    # the design's highest point is z = 1.0, so the top of the mesh is exactly `height` above the floor
    top = max(v[2] for v in m.vertices)
    if abs(top - p['height']) > 1e-9:
        raise ValueError('%s: design top %.4f != height %.4f' % (archetype, top, p['height']))
    return m


def tile_aspect(m, tile):
    """Width / height in metres of one tile as it lies on the model (area-weighted over its triangles), or None.
    The painter squashes the company mark by this, so the mark is undistorted on the mesh."""
    num = den = 0.
    for f, uv, t in zip(m.faces, m.local_uv, m.tiles):
        if t != tile:
            continue
        p0, p1, p2 = (m.vertices[i] for i in f)
        e1, e2 = _sub(p1, p0), _sub(p2, p0)
        du1, dv1 = uv[1][0] - uv[0][0], uv[1][1] - uv[0][1]
        du2, dv2 = uv[2][0] - uv[0][0], uv[2][1] - uv[0][1]
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            continue
        pu = tuple((e1[k] * dv2 - e2[k] * dv1) / det for k in range(3))
        pv = tuple((e2[k] * du1 - e1[k] * du2) / det for k in range(3))
        area = math.sqrt(_dot(_cross(e1, e2), _cross(e1, e2)))
        num += area * math.sqrt(_dot(pu, pu)); den += area * math.sqrt(_dot(pv, pv))
    return num / den if den else None


def symmetry(m):
    """Largest distance from a vertex's mirror image (x -> -x) to the nearest vertex, in metres."""
    worst = 0.
    for x, y, z in m.vertices:
        worst = max(worst, min(math.dist((-x, y, z), q) for q in m.vertices))
    return worst
