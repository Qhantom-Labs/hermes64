"""Face-head people v2 for the Hermes64 humanoid (lane-characters).

Pure Python 3.9, no Blender. The the owner-approved masked/hooded expedition figure stays on
geometry.humanoid (frozen in approved/masked_v1) and is never built here. This module builds every
FACE-head person, including the visor cameo, as ONE fixed topology `human16_face_v2`: identical
vertex count, triangles, UVs, material roles and skin weights for every parameter value. Hair
styles, costumes, ages and builds are vertex positions plus painted textures. Skeleton: the shared
human16_v1 bone names/parents; only rest positions scale.

Head construction (head-local units hh = chin-to-crown height, origin at the chin, -Y = front):
  face loft  10 sides x 4 rings (neck, jaw/chin, cheek, brow) -> painted face via fixed planar UVs
  nose       3-sided wedge, face material
  ears       3-sided flaps (tucked inside the skull when hair covers them)
  hair shell 10 sides x 4 rings + crown vertex: hairline, fringe, sideburns, nape, volume
  extra      5 sides x 3 rings: ponytail / bun / braid / visor, or tucked away
"""
import math

try:
    from . import geometry as G
    from . import proportion as PRP
except ImportError:  # loaded by file path (tests)
    import importlib.util as _iu
    import pathlib as _pl
    _spec = _iu.spec_from_file_location('geometry', _pl.Path(__file__).with_name('geometry.py'))
    G = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(G)
    _spec = _iu.spec_from_file_location('proportion', _pl.Path(__file__).with_name('proportion.py'))
    PRP = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(PRP)

TAU = 2 * math.pi
PARENTS = G.HUMAN_PARENTS
COLLAR_SINK = .006   # round 21: x H, collar bottom ring below the torso top ring (all collar styles but the shawl)
NECK_SINK = .010     # round 21: x H, neck stump below the torso top ring (.004 left 3 mm in a head-down stance)
TOPOLOGY = 'human16_face_v3'   # round 13: 12 hair locks; 6-sided trousers/boots, 5-sided mitts fund them

COLOR_KEYS = ['skin', 'hair_color', 'eye_color', 'brow_color', 'lip_color', 'top_color', 'garment_color',
              'trim_color', 'accent_color', 'bottom_color', 'boot_color', 'glove_color', 'belt_color',
              'collar_color', 'extra_color', 'extra_color_2']
DEFAULTS = dict(head_mode='face', height=1.65, build=1.0, head_size=1.0, age='adult', jaw=1.0, cheek=1.0,
                chin=0.0, nose=1.0, ear=1.0, ear_point=0.0, hair='crop', hair_volume=1.0, part=0.0,
                visor=False, collar='none', garment='sweater', hem=0.0, belly=0.0, sleeves='long', puff=1.0,
                trouser_volume=1.0, cargo=False, boots='boots', hands='bare', brows='straight',
                brow_tilt=0.3, eye_shape='almond', gaze=0.0, mouth='neutral', beard='none', freckles=False,
                scar=False, lashes=False, wrinkles=0.0, top_pattern='fabric', buttons=False, zip=False,
                belt=True, patch=False, strap='none', star_back=False, chevrons=False, leaf_tufts=False,
                wear=0.3, expression=0,
                # round 13 (STEER-5 §4) face-shape / painted-feature variety
                face_length=0.0, brow_ridge=0.0, nose_shape='straight', eye_spacing=0.0, eye_tilt=0.0,
                brow_height=0.0, brow_gap=0.0, mouth_width=0.0, mole=False)
for _k in COLOR_KEYS:
    DEFAULTS[_k] = None
RANGES = dict(height=(1.0, 2.05), build=(.8, 1.3), head_size=(.85, 1.2), jaw=(.85, 1.2), cheek=(.85, 1.2),
              chin=(-1, 1), nose=(.6, 1.5), ear=(.7, 1.3), ear_point=(0, 1), hair_volume=(.6, 1.5),
              part=(-1, 1), hem=(0, 1), belly=(0, 1), puff=(.9, 1.35), trouser_volume=(.75, 1.45),
              brow_tilt=(-1, 1), gaze=(-1, 1), wrinkles=(0, 1), wear=(0, 1), expression=(0, 7),
              face_length=(-1, 1), brow_ridge=(0, 1), eye_spacing=(-1, 1), eye_tilt=(-1, 1), brow_height=(-1, 1),
              brow_gap=(-1, 1), mouth_width=(-1, 1))
ENUMS = dict(head_mode=['face'], age=['child', 'teen', 'adult', 'elder'],
             hair=['bald', 'crop', 'swept', 'long', 'bob', 'ponytail', 'bun', 'braid', 'curls', 'beanie', 'spiky'],
             collar=['none', 'flat', 'high', 'scarf', 'ruff', 'shawl', 'hood_down'],
             garment=['sweater', 'tunic', 'coverall', 'parka', 'jacket', 'apron', 'robe', 'vest'],
             sleeves=['long', 'rolled', 'short'], boots=['heavy', 'boots', 'shoes', 'cuffed'],
             hands=['bare', 'gloves', 'fingerless'], brows=['straight', 'arched', 'heavy', 'thin'],
             eye_shape=['narrow', 'almond', 'round'], mouth=['neutral', 'thin', 'full'],
             beard=['none', 'stubble', 'short', 'full', 'moustache'],
             top_pattern=['fabric', 'knit', 'stripes', 'checks', 'quilted', 'plain'],
             strap=['none', 'diagonal', 'satchel'], nose_shape=['straight', 'broad', 'hooked', 'button'])
BOOLS = ['visor', 'cargo', 'freckles', 'scar', 'lashes', 'buttons', 'zip', 'belt', 'patch', 'star_back', 'chevrons',
         'leaf_tufts', 'mole']
EXPRESSIONS = ['neutral', 'blink', 'talk_a', 'talk_b', 'smile', 'worried', 'surprised', 'sleepy']
# (head ratio, hip height, shoulder width, limb thickness, neck length), fractions of height
AGE = {'child': (.268, .405, .84, .90, .024), 'teen': (.238, .44, .93, .95, .026),
       'adult': (.212, .47, 1.0, 1.0, .028), 'elder': (.205, .455, .97, .98, .026)}
EARS_TUCKED = ('long', 'bob', 'beanie', 'curls')

# Costume atlas regions (UV space, v up) of the 128x128 costume texture.
REGIONS = {'torso': (0, .5, .5, 1), 'sleeve': (.5, .5, .75, 1), 'trouser': (.75, .5, 1, 1),
           'collar': (0, .25, .5, .5), 'boot': (.5, .25, .75, .5), 'mitt': (.75, .25, 1, .5)}
# Face-cell areas reused for parts that are not the painted face (UV inside one 64x64 cell).
SKIN_PATCH = (.02, .02, .10, .10)
EAR_PATCH = (.86, .02, .98, .14)
FACE_WF = .41           # half width of the planar face projection, hh units
FACE_V0, FACE_V1 = -.10, .62   # z of neck ring and brow ring (projection v = 0 .. 1)


def resolve(values):
    p = dict(DEFAULTS)
    for k, v in values.items():
        if k not in p:
            raise ValueError('unknown parameter ' + k)
        p[k] = v
    for k, (lo, hi) in RANGES.items():
        v = p[k]
        if isinstance(v, bool) or type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(k + ' outside declared range')
    for k, opts in ENUMS.items():
        if p[k] not in opts:
            raise ValueError(k + ' invalid enum')
    for k in BOOLS:
        if type(p[k]) is not bool:
            raise ValueError(k + ' must be boolean')
    if type(p['expression']) is not int:
        raise ValueError('expression must be integer')
    for k in COLOR_KEYS:
        if p[k] is not None and not isinstance(p[k], str):
            raise ValueError(k + ' must be a palette name')
    return p


# ---------------------------------------------------------------- small vector helpers
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0., 0., 1.)


def _newell(ring):
    nx = ny = nz = 0.
    for i in range(len(ring)):
        a = ring[i]; b = ring[(i + 1) % len(ring)]
        nx += (a[1] - b[1]) * (a[2] + b[2]); ny += (a[2] - b[2]) * (a[0] + b[0]); nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def _orient(rings, direction):
    """Same vertex order for every ring, CCW seen from the destination end (outward normals)."""
    if _dot(_newell(rings[0]), direction) < 0:
        rings = [[r[0]] + list(reversed(r[1:])) for r in rings]
    return rings


def _interp(z, knots, vals):
    if z <= knots[0]:
        return vals[0]
    for i in range(len(knots) - 1):
        if z <= knots[i + 1]:
            t = (z - knots[i]) / (knots[i + 1] - knots[i])
            return vals[i] + (vals[i + 1] - vals[i]) * t
    return vals[-1]


def zring(n, cx, cy, cz, rx, ry, tweak=None):
    """Ring for a +Z loft. phi = 0 is the front (-Y); j=0 is the back. Same order as geometry.Mesh.loft."""
    pts = []
    for j in range(n):
        f = TAU * (j / n - .5)
        pt = (cx + rx * math.sin(f), cy - ry * math.cos(f), cz)
        if tweak:
            pt = tweak(j, f, pt)
        pts.append(pt)
    return pts


def framering(n, centre, direction, up, a, b, phase=-math.pi / 2):
    """Ring of n points in the plane normal to `direction` (U x V = direction -> CCW from the end)."""
    d = _norm(direction)
    v = _sub(up, _mul(d, _dot(up, d)))
    v = _norm(v) if _dot(v, v) > 1e-10 else _norm(_cross(d, (1., 0., 0.)))
    u = _cross(v, d)
    return [_add(centre, _add(_mul(u, a * math.cos(phase + TAU * j / n)), _mul(v, b * math.sin(phase + TAU * j / n))))
            for j in range(n)]


# ---------------------------------------------------------------- mesh assembly
def _add_loft(m, name, rings, role, weights, uvf, caps=('flat', 'flat'), centre=None, tile=0):
    """Closed loft. uvf(k, j, col) -> uv for ring vertex (k, j) when used by band column `col` (col=None: cap).
    caps: 'flat' fan or 'center' (end only, uses `centre` point)."""
    n = len(rings[0]); nr = len(rings); start = len(m.vertices)
    for k, ring in enumerate(rings):
        assert len(ring) == n
        for pt in ring:
            m.vertices.append(tuple(pt))
            m.weights.append({weights: 1.} if isinstance(weights, str) else dict(weights[k]))
    m.parts[name] = list(range(start, len(m.vertices)))

    def face(ids, uv):
        m.faces.append(tuple(start + i for i in ids)); m.uv.append(uv); m.roles.append(role); m.tiles.append(tile)
    for k in range(nr - 1):
        for j in range(n):
            a = k * n + j; b = k * n + (j + 1) % n; c = (k + 1) * n + (j + 1) % n; d = (k + 1) * n + j
            ua = uvf(k, j, j); ub = uvf(k, j + 1, j); uc = uvf(k + 1, j + 1, j); ud = uvf(k + 1, j, j)
            face((a, b, c), [ua, ub, uc]); face((a, c, d), [ua, uc, ud])
    for end, kind in zip((0, nr - 1), caps):
        ids = [end * n + j for j in range(n)]
        uvs = [uvf(end, j, None) for j in range(n)]
        if kind == 'center':
            assert end == nr - 1 and centre is not None
            ci = len(m.vertices) - start
            m.vertices.append(tuple(centre['pos']))
            m.weights.append({weights: 1.} if isinstance(weights, str) else dict(weights[end]))
            m.parts[name].append(start + ci)
            for j in range(n):
                face((ci, ids[j], ids[(j + 1) % n]), [centre['uv'], uvs[j], uvs[(j + 1) % n]])
            continue
        if end == 0:
            ids = list(reversed(ids)); uvs = list(reversed(uvs))
        for j in range(1, n - 1):
            face((ids[0], ids[j], ids[j + 1]), [uvs[0], uvs[j], uvs[j + 1]])


def _region_uv(region, mirror=False, closed_u=True):
    u0, v0, u1, v1 = region
    iu = (u1 - u0) * .03; iv = (v1 - v0) * .03

    def make(n, nr):
        def uvf(k, j, col):
            u = j / n
            if mirror:
                u = 1 - u
            return (u0 + iu + (u1 - u0 - 2 * iu) * u, v0 + iv + (v1 - v0 - 2 * iv) * (k / (nr - 1)))
        return uvf
    return make


# ---------------------------------------------------------------- head (head-local hh units)
SK_Z = [-.10, .09, .34, .62, .74, .86, .95, 1.02]
SK_RX = [.165, .30, .355, .368, .372, .315, .20, .02]
SK_RY = [.165, .36, .42, .448, .452, .385, .255, .02]
SK_CY = [.07, .01, .02, .035, .04, .05, .05, .05]
RING_Z = (.74, .86, .95)      # hair shell rings above the hem: temple, upper dome, crown ring


def _skull(z):
    return _interp(z, SK_Z, SK_RX), _interp(z, SK_Z, SK_RY), _interp(z, SK_Z, SK_CY)


def _cf(c):
    return c if c <= 0 else c ** .8   # flatter face plane in front, round back


def face_rings(p, z_neck=-.10):
    jaw = p['jaw']; ck = p['cheek']; chin = p['chin']; age = p['age']
    fl = p.get('face_length', 0.); br = p.get('brow_ridge', 0.)
    # round 13: face_length drops (long) / lifts (short) the jaw ring and chin; brow_ridge pushes the brow front out
    defs = [(z_neck, .07, .165, .165), (.09 - .04 * fl, .01, .30 * jaw * (1 - .05 * fl), .36), (.34 - .012 * fl, .02, .355 * ck, .42),
            (.62, .035, .365, .445)]
    if age == 'child':
        defs[1] = (.10, .015, .275 * jaw, .34); defs[2] = (.34, .02, .37 * ck, .42)
    if age == 'elder':
        defs[1] = (.09, .01, .29 * jaw, .36)
    rings = []
    for k, (z, cy, rx, ry) in enumerate(defs):
        ring = []
        for j in range(10):
            f = TAU * (j / 10 - .5); s = math.sin(f); c = math.cos(f)
            x = rx * s; y = cy - ry * _cf(c); zz = z
            if k == 1:
                if j == 5:
                    zz = .03 - .015 * chin; y -= .025 + .03 * chin
                elif j in (4, 6):
                    zz -= .035 + (.012 if age == 'elder' else 0); y -= .012
                elif j in (3, 7):
                    zz += .01
                elif j in (2, 8):
                    zz += .05
                else:
                    zz += .09
                if age == 'child' and j == 5:
                    y += .012
            if k == 2:
                if j in (3, 7):
                    x *= 1.03 if age != 'elder' else .99
                if j in (4, 6):
                    y -= .008
            if k == 3:
                if j in (4, 6):
                    y -= .022 + .022 * br; zz -= .012 * br
                if j == 5:
                    y -= .014 + .018 * br; zz -= .008 * br
            ring.append((x, y, zz))
        rings.append(ring)
    return rings


def nose_rings(p):
    ns = p['nose']; w = .85 if p['age'] == 'child' else 1.0
    sh = p.get('nose_shape', 'straight')
    # round 13: nose shapes - broad (wide wings, flat tip), hooked (tip low and forward, high bridge), button (short, up)
    bw = {'straight': 1., 'broad': 1.35, 'hooked': .95, 'button': .9}[sh] * w
    tz = {'straight': 0., 'broad': -.012, 'hooked': -.03, 'button': .02}[sh]
    ty = {'straight': 0., 'broad': .012, 'hooked': -.022, 'button': .028}[sh]
    base = [(0, -.352, .47 + (.02 if sh == 'hooked' else 0.)), (-.072 * bw, -.355, .272), (.072 * bw, -.355, .272)]
    tip = [(0, -.392 - .062 * ns * w + ty, .372 - .01 * ns + tz), (-.041 * bw * ns ** .5, -.392 - .05 * ns * w + ty * .5, .268),
           (.041 * bw * ns ** .5, -.392 - .05 * ns * w + ty * .5, .268)]
    return _orient([base, tip], (0, -1, 0))


def ear_rings(p, s):
    e = p['ear']; pt = p['ear_point']
    base = [(s * .318, .01, .49), (s * .318, .095, .29), (s * .318, -.025, .30)]
    if p['hair'] in EARS_TUCKED:
        tip = [(s * .30, .02, .46), (s * .30, .075, .33), (s * .30, .0, .34)]
    else:
        tip = [(s * (.362 + .03 * e), .075, .50 + .07 * pt * e + .02 * (e - 1)),
               (s * (.368 + .025 * e), .135, .305), (s * (.356 + .025 * e), .045, .305)]
    return _orient([base, tip], (s, 0, 0))


# hair styles: front hem z, side hem z, back hem z, thickness, top volume, hem flare
HAIR = {'bald': (.585, .40, .14, .004, 0., 0.), 'crop': (.585, .44, .20, .022, .010, 0.),
        'swept': (.565, .38, .14, .040, .040, 0.), 'long': (.585, .05, -.50, .036, .025, .05),
        'bob': (.555, .10, .12, .050, .030, .045), 'ponytail': (.585, .44, .22, .016, .008, 0.),
        'bun': (.585, .44, .22, .016, .008, 0.), 'braid': (.585, .44, .22, .016, .008, 0.),
        'curls': (.575, .33, .14, .060, .030, .02), 'beanie': (.59, .42, .30, .036, .040, 0.),
        'spiky': (.60, .38, .14, .050, .030, 0.)}
LOCKS = ('crop', 'swept', 'long', 'bob', 'ponytail', 'bun', 'braid')


def hair_rings(p):
    st = p['hair']; vol = p['hair_volume']; part = p['part']
    zf, zs, zb, t, tv, flare = HAIR[st]
    t *= .7 + .3 * vol
    clear = .008
    sgn = 1 if part >= 0 else -1

    def hem_z(j, c, s):
        z = zs + (zf - zs) * c ** 1.3 if c >= 0 else zs + (zb - zs) * (-c) ** 1.3
        if st in LOCKS:
            if c > .9:
                z -= .012                                  # centre lock tip on the forehead
            else:
                z += -.045 if j % 2 else .012              # pointed lock tips along the hem
        if st == 'swept':
            if j == 5 + sgn:
                z = .49                                    # one heavy side lock beside the eye, never over it
            if j == 5 - sgn:
                z += .025
        if st == 'spiky' and c < .5:
            z -= .09 if j % 2 == 0 else -.01               # spikes at sides/back only; the front stays clear
        if st == 'curls':
            z -= .035 if j % 2 else 0
        return z

    def point(f, z, extra, ridge=True, zskull=None, front_t=1.):
        rx, ry, cy = _skull(z if zskull is None else zskull)
        s = math.sin(f); c = math.cos(f)
        tt = t * (front_t if c > .5 else 1.)
        x = (rx + tt + clear + extra) * s
        y = cy - (ry + tt + clear + extra) * _cf(c) - (.022 * max(0., c) ** 3 if ridge else 0)
        return [x, y, z]

    rings = []
    hem = []
    for j in range(10):
        f = TAU * (j / 10 - .5); c = math.cos(f); s = math.sin(f)
        z = hem_z(j, c, s)
        zsk = max(z, .25) if st in ('long', 'bob', 'curls') else max(z, .12)
        pt = point(f, z, flare * (1 if z < .3 else .3), zskull=zsk, front_t=.45)
        if st == 'long' and c < 0:
            pt[1] += .12 * (-c)
        if st == 'bob' and c < .3:
            pt[1] += .03 * (-c if c < 0 else 0)
        hem.append(tuple(pt))
    rings.append(hem)
    for k, (z, ev) in enumerate([(RING_Z[0], .016), (RING_Z[1], .022), (RING_Z[2], .012)]):
        ring = []
        for j in range(10):
            f = TAU * (j / 10 - .5); c = math.cos(f); s = math.sin(f)
            extra = ev * tv / .03 * vol if tv else 0.
            zz = z + (tv * .3 if k == 2 else 0)
            if st in LOCKS and k < 2:
                extra += (.022 if j % 2 else -.006) * (1. if k == 0 else .6)   # lumpy lock masses
            if st == 'spiky':
                if k == 0 and j % 2 == 0 and c < .6:
                    extra += .07; zz -= .02                # side spikes
                if k == 1 and j % 2 == 1:
                    extra += .10; zz += .06                # up-and-out spikes
                if k == 2 and j % 2 == 0:
                    extra += .05; zz += .11                # crown spikes
                if k == 2 and j % 2 == 1:
                    extra -= .04
            if st == 'curls':
                extra += .03 * (1 if (j + k) % 2 else -.5)
            if st == 'swept' and k == 0 and c > .3:
                extra += .03 * c; zz += .025 * c
            if st == 'beanie':
                extra += .012 if k == 0 else 0
                zz += .015 * k
            if st == 'bob' and k == 0:
                extra += .015
            pt = point(f, zz, extra, ridge=(k == 0), front_t=.7 if k == 0 else 1.)
            ring.append(tuple(pt))
        rings.append(ring)
    crown_z = 1.02 + t + tv * .5 + (.03 if st == 'spiky' else 0) + (.02 if st == 'beanie' else 0)
    return rings, (0., .05, crown_z)


# ---------------------------------------------------------------- hair clumps (round 13, STEER-5 §4)
# 12 flat blade locks (4 tris each) on top of the hair shell give every style a real clump silhouette:
# fringe/bangs (F, 3), temple/side locks (S, 4), back/nape locks (B, 3), crown tufts (T, 2). A style that has no
# use for a lock tucks it inside the skull (hidden, non-degenerate), so the topology never changes.
# spec = (phi deg [0 front, + wearer's left], anchor z, direction (x, y, z) head-local, length, half-width)
LOCK_N = 12
_HIDE = None


def _mirror(spec):
    phi, z, d, L, w = spec
    return (-phi, z, (-d[0], d[1], d[2]), L, w)


# sleeve rings cuff -> shoulder (x, y, z in units of W / height) and their skin weights
# (round 12: elbow bend spread over rings 1..3 - tight bends collapsed the inner elbow on the sweep)
# round 13 (STEER-5 §3): the shoulder ring sits further out over the joint (.105 -> .130 W, a touch higher) and the
# deltoid/shoulder weights blend more evenly (.70/.20 -> .45/.55), so a front reach folds the shoulder over a wider
# band instead of collapsing the inner edge (probes/pose/probe_shoulder_geom.py: worst ratio .09 -> .38 raw;
# the pose fallback in core/pose.py covers the rest)
SLEEVE_POS = [(.237, -.018, .448), (.224, -.011, .49), (.204, -.005, .568), (.168, 0., .655), (.130, .005, .735)]
SLEEVE_W = [{'fa': 1.}, {'fa': .82, 'ua': .18}, {'fa': .5, 'ua': .5}, {'ua': .70, 'fa': .1, 'sp': .2}, {'ua': .45, 'sp': .55}]


def lock_specs(p):
    st = p['hair']; vol = p['hair_volume']; sg = 1 if p['part'] >= 0 else -1
    if st == 'crop':
        F = [(-22, .60, (-.15, -.55, -.82), .11, .055), (0, .62, (0., -.62, -.78), .12, .06), (22, .60, (.15, -.55, -.82), .11, .055)]
        S = [(-80, .50, (-.35, -.10, -.93), .11, .05), (-112, .42, (-.30, .30, -.90), .10, .05)]
        B = [(160, .34, (-.10, .45, -.88), .10, .055), (180, .32, (0., .45, -.89), .09, .05), (200, .34, (.10, .45, -.88), .10, .055)]
        T = [(-30, .93, (-.25, .85, .45), .09, .06), (30, .93, (.25, .85, .45), .09, .06)]   # flat, swept back (no horns)
        S = S + [_mirror(s) for s in S]
    elif st == 'swept':
        # side part: the fringe sweeps across the forehead away from the part; one heavy lock hangs by the cheek
        F = [(sg * 30, .65, (-sg * .78, -.45, -.43), .29, .085), (sg * 5, .66, (-sg * .82, -.40, -.40), .31, .09),
             (-sg * 22, .62, (-sg * .55, -.45, -.70), .25, .075)]
        S = [(-sg * 76, .54, (-sg * .22, -.18, -.96), .33, .075), (-sg * 108, .46, (-sg * .30, .25, -.92), .16, .06),
             (sg * 80, .50, (sg * .35, -.05, -.93), .10, .05), (sg * 110, .44, (sg * .30, .30, -.90), .10, .05)]
        B = [(160, .36, (-.10, .50, -.86), .12, .06), (180, .34, (0., .50, -.87), .11, .055), (200, .36, (.10, .50, -.86), .12, .06)]
        T = [(sg * 25, .98, (-sg * .30, .70, .65), .14, .07), (-sg * 20, .97, (-sg * .45, .60, .66), .13, .065)]
    elif st == 'long':
        F = [(-18, .63, (-.62, -.50, -.60), .19, .06), (0, .645, (0., -.65, -.76), .08, .04), (18, .63, (.62, -.50, -.60), .19, .06)]
        S = [(-80, .50, (-.16, -.05, -.99), .44, .07), (-116, .46, (-.22, .25, -.94), .46, .07)]
        S = S + [_mirror(s) for s in S]
        B = [(160, .40, (-.06, .30, -.95), .46, .075), (180, .38, (0., .30, -.95), .50, .08), (200, .40, (.06, .30, -.95), .46, .075)]
        T = [(-30, .94, (-.25, .85, .45), .08, .05), (30, .94, (.25, .85, .45), .08, .05)]
    elif st == 'bob':
        F = [(-24, .62, (-.10, -.60, -.79), .13, .065), (0, .63, (0., -.62, -.78), .13, .07), (24, .62, (.10, -.60, -.79), .13, .065)]
        S = [(-78, .50, (-.05, -.12, -.99), .30, .07), (-112, .46, (-.10, .20, -.97), .28, .07)]
        S = S + [_mirror(s) for s in S]
        B = [(160, .40, (-.05, .30, -.95), .25, .075), (180, .40, (0., .30, -.95), .25, .075), (200, .40, (.05, .30, -.95), .25, .075)]
        T = [(-30, .94, (-.25, .85, .45), .08, .055), (30, .94, (.25, .85, .45), .08, .055)]
    elif st in ('ponytail', 'bun', 'braid'):
        F = [(-20, .63, (-.45, -.55, -.70), .14, .055), (20, .63, (.45, -.55, -.70), .14, .055)]
        F = F + ([(0, .64, (0., -.62, -.78), .12, .06)] if st == 'braid' else [_HIDE])
        S = [(-82, .52, (-.20, -.15, -.97), .16, .045), (-112, .44, (-.25, .30, -.92), .10, .045)]
        S = S + [_mirror(s) for s in S]
        B = [(165, .36, (-.10, .55, -.83), .09, .05), (195, .36, (.10, .55, -.83), .09, .05), _HIDE]
        T = [_HIDE, _HIDE]
    elif st == 'curls':
        out = lambda phi, up: (math.sin(math.radians(phi)), -math.cos(math.radians(phi)) * .9, up)  # noqa: E731
        F = [(phi, .63, out(phi, -.25), .09, .085) for phi in (-30, 0, 30)]
        S = [(phi, .52, out(phi, -.35), .10, .085) for phi in (-75, -115, 75, 115)]
        B = [(phi, .45, out(phi, -.45), .10, .09) for phi in (150, 180, 210)]
        T = [(phi, .93, out(phi, .85), .09, .085) for phi in (-40, 40)]
    elif st == 'beanie':
        # hair out under the cap: fringe under the brim, locks over the ears and at the nape
        F = [(-20, .575, (-.25, -.50, -.83), .12, .055), (0, .58, (.05, -.55, -.83), .11, .055), (24, .575, (.30, -.45, -.84), .12, .055)]
        S = [(-84, .44, (-.25, -.05, -.97), .14, .05), (-112, .40, (-.25, .30, -.92), .12, .05)]
        S = S + [_mirror(s) for s in S]
        B = [(160, .32, (-.10, .40, -.91), .12, .055), (180, .31, (0., .40, -.92), .11, .055), (200, .32, (.10, .40, -.91), .12, .055)]
        T = [_HIDE, _HIDE]
    elif st == 'spiky':
        out = lambda phi, up: (math.sin(math.radians(phi)) * .7, -math.cos(math.radians(phi)) * .5 + .2, up)  # noqa: E731
        F = [(phi, .66, out(phi, .5), .16, .06) for phi in (-25, 0, 25)]
        S = [(phi, .62, out(phi, .45), .18, .065) for phi in (-80, -120, 80, 120)]
        B = [(phi, .60, out(phi, .3), .16, .065) for phi in (150, 180, 210)]
        T = [(phi, .97, out(phi, 1.), .18, .07) for phi in (-30, 30)]
    else:                                   # bald: every lock tucked away inside the skull
        F = [_HIDE] * 3; S = [_HIDE] * 4; B = [_HIDE] * 3; T = [_HIDE] * 2
    specs = F + S + B + T
    assert len(specs) == LOCK_N, (st, len(specs))
    return [None if s is None else (s[0], s[1], s[2], s[3] * (.85 + .15 * vol), s[4] * (.9 + .1 * vol)) for s in specs]


def lock_piece(spec, p, k):
    """Blade lock in head-local units: 2 root verts spread along the scalp, 1 root vert sunk under the shell,
    and the tip. Hidden locks: a tiny blade at the skull centre (never visible, never degenerate)."""
    if spec is None:
        c = (.0, .03 + .004 * k, .50 + .01 * k)
        return [_add(c, (.02, 0., 0.)), _add(c, (-.02, 0., 0.)), _add(c, (0., .02, -.01)), _add(c, (0., -.004, .03))]
    phi, z, d, L, w = spec
    st = p['hair']
    t = HAIR[st][3] * (.7 + .3 * p['hair_volume'])
    rx, ry, cy = _skull(max(z, .12))
    f = math.radians(phi); s = math.sin(f); c = math.cos(f)
    A = ((rx + t * .6) * s, cy - (ry + t * .6) * _cf(c), z)
    n = _norm((rx * s, -ry * _cf(c) - .001, .35 * max(0., z - .6)))
    d = _norm(d)
    tv = _cross(d, n)
    tv = _norm(tv) if _dot(tv, tv) > 1e-8 else _norm(_cross(d, (0., 0., 1.)))
    nn = _norm(_cross(tv, d))
    if _dot(nn, n) < 0:
        nn = _mul(nn, -1.)
    root = _sub(A, _mul(d, w * .4))
    return [_add(root, _mul(tv, w)), _add(root, _mul(tv, -w)), _sub(_add(root, _mul(d, w * .2)), _mul(nn, w * .6)),
            _add(_add(A, _mul(d, L)), _mul(nn, .012))]


def _add_blade(m, name, verts, bone='head'):
    """Closed 4-vertex lock; faces oriented outward from the centroid. UVs in the hair texture's lower strip:
    the visible outer face spans the strip (strands run root -> tip), the inner faces sit in its dark root zone."""
    start = len(m.vertices)
    cen = _mul(_add(_add(verts[0], verts[1]), _add(verts[2], verts[3])), .25)
    for v in verts:
        m.vertices.append(tuple(v)); m.weights.append({bone: 1.})
    m.parts[name] = list(range(start, start + 4))
    faces = [((0, 1, 3), [(.12, .03), (.88, .03), (.5, .215)]), ((1, 2, 3), [(.88, .03), (.94, .02), (.6, .12)]),
             ((2, 0, 3), [(.06, .02), (.12, .03), (.4, .12)]), ((0, 2, 1), [(.12, .03), (.5, .015), (.88, .03)])]
    for f, uv in faces:
        a, b, c = (verts[i] for i in f)
        nrm = _cross(_sub(b, a), _sub(c, a))
        fc = _mul(_add(_add(a, b), c), 1. / 3)
        if _dot(nrm, _sub(fc, cen)) < 0:
            f = (f[0], f[2], f[1]); uv = [uv[0], uv[2], uv[1]]
        m.faces.append(tuple(start + i for i in f)); m.uv.append(list(uv)); m.roles.append('headwear'); m.tiles.append(0)


def extra_rings(p):
    st = p['hair']; up = (0., 0., 1.)
    if p['visor']:
        # wide slanted plate across both eyes, outside the hair: high on -x, low on +x
        cs = [(-.475, -.17, .57), (0., -.50, .475), (.475, -.17, .40)]
        dirs = [(.55, -.8, -.12), (1., 0., -.18), (.55, .8, -.12)]
        rings = [framering(5, cs[0], dirs[0], up, .022, .066), framering(5, cs[1], dirs[1], up, .026, .088),
                 framering(5, cs[2], dirs[2], up, .022, .06)]
        mid = rings[1]
        mid[0] = (mid[0][0], mid[0][1], mid[0][2] - .03)     # slight V over the nose bridge
        return _orient(rings, (1., 0., 0.))
    if st == 'ponytail':
        cs = [(0., .43, .80), (0., .66, .60), (0., .70, .12)]; rs = [.085, .105, .035]
    elif st == 'bun':
        cs = [(0., .33, .84), (0., .45, .91), (0., .55, .96)]; rs = [.10, .16, .07]
    elif st == 'braid':
        cs = [(0., .45, .40), (0., .53, -.15), (0., .57, -.70)]; rs = [.075, .075, .04]
    else:
        cs = [(0., .05, .45), (0., .06, .46), (0., .07, .47)]; rs = [.010, .012, .008]
    d = _sub(cs[2], cs[0])
    rings = [framering(5, c, d, (0., 1., 0.) if abs(d[2]) > abs(d[1]) else up, r, r) for c, r in zip(cs, rs)]
    return _orient(rings, d)


def _face_uv_project(pt):
    return (.5 + pt[0] / (2 * FACE_WF), (pt[2] - FACE_V0) / (FACE_V1 - FACE_V0))


def _patch(area, pt, scale=1.):
    u0, v0, u1, v1 = area
    a = (math.atan2(pt[0], -pt[1]) / TAU) % 1.0
    return (u0 + (u1 - u0) * a, v0 + (v1 - v0) * min(1., max(0., (pt[2] + .1) / .8)))


# round 17: band columns 2 and 7 are the cheek SIDE planes: both edge vertices project to ~the same u (.08/.09), so
# the planar projection stretched a 1-texel strip of the face cell across the side of the head (each texel row read
# as a horizontal cheek stripe). They now take the solid skin patch like the other side/back columns.
FRONT_COLS = (3, 4, 5, 6)   # face-loft band columns that receive the planar face projection


def _canonical_uvs():
    p = resolve({})
    fr = face_rings(p); nr = nose_rings(p)
    face = {}
    for k, ring in enumerate(fr):
        for j, pt in enumerate(ring):
            face[(k, j)] = _face_uv_project(pt)
            face[('patch', k, j)] = _patch(SKIN_PATCH, pt)
    nose = {}
    for k, ring in enumerate(nr):
        for j, pt in enumerate(ring):
            nose[(k, j)] = _face_uv_project(pt)
    return face, nose


_FACE_UV, _NOSE_UV = _canonical_uvs()

# landmarks for the painter (canonical projection, cell UV space, v up)
FACE_LAYOUT = {
    'v_chin': _FACE_UV[(1, 5)][1], 'v_jaw': (.09 - FACE_V0) / (FACE_V1 - FACE_V0),
    'v_cheek': (.34 - FACE_V0) / (FACE_V1 - FACE_V0), 'v_brow_ring': 1.0,
    'mouth_v': (.182 - FACE_V0) / (FACE_V1 - FACE_V0), 'nose_v': (.282 - FACE_V0) / (FACE_V1 - FACE_V0),
    'eye_v': (.448 - FACE_V0) / (FACE_V1 - FACE_V0), 'brow_v': (.553 - FACE_V0) / (FACE_V1 - FACE_V0),
    'eye_du': .168, 'u_side': _FACE_UV[(2, 7)][0] - .5,
    'skin_patch': SKIN_PATCH, 'ear_patch': EAR_PATCH,
}


# ---------------------------------------------------------------- the person
def person(values):
    p = resolve(values)
    H = p['height']; B = p['build']
    hr, leg, sw, limb, neck = AGE[p['age']]
    hr *= p['head_size']
    hh = hr * H
    zc = H - hh                  # chin
    S = zc - neck * H            # neck base / torso top
    L = leg * H                  # hip joint

    def Z(c):                    # canonical masked-adult height fraction -> metres for these proportions
        return c / .46 * L if c <= .46 else L + (c - .46) / .285 * (S - L)
    W = B * sw                   # shoulder/torso width factor
    LW = B * (.5 + .5 * sw)      # leg spacing factor
    tw = (.6 + .4 * B) * sw      # torso depth factor
    bones = {'root': (0., 0., 0.), 'pelvis': (0., 0., Z(.46)), 'spine': (0., 0., Z(.52)), 'head': (0., 0., S + .006 * H)}
    for side, s in (('l', 1), ('r', -1)):
        bones['upper_arm_' + side] = (s * .143 * W * H, 0., Z(.69))
        bones['forearm_' + side] = (s * .204 * W * H, -.005 * H, Z(.57))
        bones['hand_' + side] = (s * .23 * W * H, -.018 * H, Z(.46))
        bones['thigh_' + side] = (s * .085 * LW * H, 0., Z(.46))
        bones['shin_' + side] = (s * .1 * LW * H, -.006 * H, Z(.28))
        bones['foot_' + side] = (s * .108 * LW * H, 0., Z(.09))
    m = G.Mesh(p, bones, PARENTS, 'human')
    m.topology = TOPOLOGY

    def ring(n, x, y, z, rx, ry, tweak=None):
        return zring(n, x * H, y * H, z, rx * H, ry * H, tweak)

    hem = p['hem']; bel = p['belly']; pf = p['puff']; V = p['trouser_volume']
    # ---- torso
    torso = [ring(8, 0, 0, Z(.452 - .19 * hem), (.103 + .064 * hem) * W * pf, (.074 + .032 * hem + .012 * bel) * tw * pf),
             ring(8, 0, -.003 - .014 * bel, Z(.53), (.111 + .012 * bel) * W * pf, (.086 + .024 * bel) * tw * pf),
             ring(8, 0, .005, Z(.655), .150 * W * pf, (.092 + .004 * bel) * tw * pf),
             ring(8, 0, .010, Z(.738), .118 * W * pf, .068 * tw * pf)]      # shoulder line (no yoke on face-heads)
    _add_loft(m, 'torso', torso, 'costume', [{'pelvis': .7, 'spine': .3}, {'spine': 1}, {'spine': 1}, {'spine': 1}],
              _region_uv(REGIONS['torso'])(8, 4))
    # ---- collar (one 2-ring loft; style = shape)
    cs = p['collar']
    torso_top = Z(.738)          # the torso's top ring (shoulder line)
    cdef = {'none': ((S - .012 * H, .068 * W, .053, 0.), (S - .004 * H, .064 * W, .05, 0.)),
            'flat': ((S - .007 * H, .086 * W, .068, 0.), (S + .004 * H, .079 * W, .062, 0.)),
            'high': ((S - .004 * H, .088 * W, .07, 0.), (zc - .006 * H, .066 * W, .062, .004)),
            'scarf': ((S - .010 * H, .112 * W, .09, 0.), (S + .024 * H, .098 * W, .08, .004)),
            'ruff': ((S - .016 * H, .138 * W, .108, 0.), (S + .022 * H, .118 * W, .098, .006)),
            'shawl': ((Z(.655), .168 * W * pf, .108, 0.), (S + .006 * H, .09 * W, .072, 0.)),
            # round 21: the bottom ring has the torso's depth and no back offset (it was deeper than the torso and
            # pushed back, so on broad builds the hood's lower edge hung 2-3 cm off the upper back); the fold ring
            # behind the neck is unchanged
            'hood_down': ((S - .004 * H, .104 * W, .068, 0.), (S + .032 * H, .108 * W, .086, .05))}[cs]
    if cs != 'shawl':
        # round 21 (STEER-8 §2): every collar's bottom ring sits inside the torso, at least COLLAR_SINK below its top
        # ring ('high' and 'hood_down' started 5-6 mm ABOVE it: a thin slit all round the neck). Both rings are on the
        # spine, so the overlap holds in every clip. The shawl's bottom ring is its hem, low on the chest already.
        cdef = ((min(cdef[0][0], torso_top - COLLAR_SINK * H),) + tuple(cdef[0][1:]), cdef[1])

    def ctweak(k):
        def tw_(j, f, pt):
            if cs == 'ruff':
                bump = .012 * H * (1 if j % 2 else -.4)
                return (pt[0] + bump * math.sin(f), pt[1] - bump * math.cos(f), pt[2] + (.006 * H * (j % 2) if k else 0))
            if cs == 'hood_down' and math.cos(f) < -.3 and k == 1:      # round 21: only the fold ring lies back
                return (pt[0], pt[1] + .03 * H * (-math.cos(f)), pt[2] + .02 * H * k)
            if cs == 'scarf' and k == 0 and math.cos(f) > .5:
                return (pt[0], pt[1], pt[2] - .01 * H)
            return pt
        return tw_
    collar = [zring(8, 0., (.012 + c[3]) * H, c[0], c[1] * H, c[2] * H * tw, ctweak(k)) for k, c in enumerate(cdef)]
    _add_loft(m, 'collar', collar, 'costume', [{'spine': 1}, {'spine': .75, 'head': .25}], _region_uv(REGIONS['collar'])(8, 2))
    # ---- arms
    sl = p['sleeves']
    gl = {'gloves': 1.08, 'fingerless': 1.04, 'bare': 1.0}[p['hands']]
    for side, s in (('l', 1), ('r', -1)):
        rr = [(.031, .032), (.045 * pf, .044 * pf), (.043 * pf, .043 * pf), (.052 * pf, .052 * pf), (.047 * pf, .048 * pf)]
        if sl == 'rolled':
            rr[0] = (.027, .028); rr[1] = (.036, .035); rr[2] = (.052 * pf, .051 * pf)
        if sl == 'short':
            rr[0] = (.026, .027); rr[1] = (.034, .033); rr[2] = (.033, .033); rr[3] = (.058 * pf, .057 * pf)
        rr[3] = (rr[3][0] * 1.02, rr[3][1] * 1.02); rr[4] = (.040 * pf, .042 * pf)
        arm = [ring(6, s * x * W, y, Z(z), a * W * limb, b * limb) for (x, y, z), (a, b) in zip(SLEEVE_POS, rr)]
        _add_loft(m, 'sleeve_' + side, arm, 'costume',
                  [{k.replace('ua', 'upper_arm_' + side).replace('fa', 'forearm_' + side).replace('sp', 'spine'): v
                    for k, v in w.items()} for w in SLEEVE_W],
                  _region_uv(REGIONS['sleeve'], s < 0)(6, 5))
        mitt = [ring(5, s * .241 * W, -.027, Z(.385), .016 * gl * limb, .019 * gl * limb),
                ring(5, s * .244 * W, -.027, Z(.407), .036 * gl * limb, .024 * gl * limb),
                ring(5, s * .237 * W, -.018, Z(.452), .029 * gl * limb, .024 * gl * limb)]
        _add_loft(m, 'mitt_' + side, mitt, 'costume', 'hand_' + side, _region_uv(REGIONS['mitt'], s < 0)(5, 3))
        thumb = [ring(3, s * .205 * W, -.04, Z(.406), .013 * gl * limb, .016 * gl * limb),
                 ring(3, s * .219 * W, -.032, Z(.438), .019 * gl * limb, .02 * gl * limb)]
        mu0, mv0, mu1, mv1 = REGIONS['mitt']
        _add_loft(m, 'thumb_' + side, thumb, 'costume', 'hand_' + side,
                  lambda k, j, col, mu0=mu0, mv0=mv0, mu1=mu1, mv1=mv1: (mu0 + (mu1 - mu0) * (.2 + .2 * (j / 3)), mv0 + (mv1 - mv0) * (.45 + .2 * k)))
    # ---- legs: STEER-5 proportion rule (core/proportion.leg_bounds) bounds every trouser ring and the boots by the
    # hip (waistband / torso hem) and torso half-widths; figures already inside the bound are unchanged
    boot = {'heavy': 1.08, 'boots': 1., 'shoes': .9, 'cuffed': 1.02}[p['boots']] * (1.06 if p['age'] == 'child' else 1.)
    tz = [(Z(.452 - .19 * hem) / H, (.103 + .064 * hem) * W * pf), (Z(.53) / H, (.111 + .012 * bel) * W * pf),
          (Z(.655) / H, .150 * W * pf), (Z(.738) / H, .118 * W * pf)]
    zl = L / H
    hip_half = max(.149 * LW, PRP.profile_max(tz, zl - .03, zl + .03))
    torso_half = PRP.profile_max(tz, Z(.52) / H, Z(.69) / H - .035)
    pocket = .016 if p['cargo'] else 0.
    # round 19 (STEER-7 §3): heavy builds (leg factor LW > 1: fv_smith, pp_engineer) read chunky in the legs even
    # inside the rule - above build 1 their lower legs and boots stop thickening (thighs grow at half rate), so the
    # legs taper under the broad torso, and the legs are planned against a bound tightened by up to 10% (margin
    # under the leg rule). LW <= 1 bodies are bit-identical.
    heavy = max(0., LW - 1.)
    LT = LW - heavy                               # ankle/calf/knee + boots: no thicker than a build-1 body (tapered)
    LTT = LW - .5 * heavy                         # thigh: half the build's growth (stays sturdy)
    km = 1. - min(.10, .8 * heavy)
    (c0, r0), (c1, r1), (c2, r2), (c3, r3) = PRP.plan_legs([
        (.108 * LW, .051 * LT * limb, 0.), (.106 * LW, .072 * LT * V * limb, 0.), (.1 * LW, .059 * LT * V * limb, 0.),
        (.085 * LW, .084 * LTT * V * limb, pocket)], hip_half * km, torso_half * km, gap=-.0035 * LW, scale=LW)
    gb = PRP.boot_bounds(hip_half * km)
    bt_r = [.057 * LT * boot, .065 * LT * boot, (.056 if p['boots'] == 'cuffed' else .043) * LT]
    bts = [gb(c0, r) for r in bt_r]
    cb = min(c for c, r in bts); c0 = min(c0, cb)
    for side, s in (('l', 1), ('r', -1)):
        m.bones['shin_' + side] = (s * c2 * H, m.bones['shin_' + side][1], m.bones['shin_' + side][2])
        m.bones['foot_' + side] = (s * cb * H, m.bones['foot_' + side][1], m.bones['foot_' + side][2])
    for side, s in (('l', 1), ('r', -1)):
        def cargo(j, f, pt, s=s):
            if p['cargo'] and math.sin(f) * s > .45:
                return (pt[0] + s * .016 * H, pt[1] + .004 * H, pt[2])
            return pt
        leg = [ring(6, s * c0, 0, Z(.109), r0, .052 * limb),
               ring(6, s * c1, .008, Z(.174), r1, .067 * V * limb),
               ring(6, s * c2, -.012, Z(.275), r2, .064 * V * limb),
               ring(6, s * c3, .006, Z(.396), r3, .083 * V * limb, cargo),
               ring(6, s * .077 * LW, 0, Z(.48), .072 * LW, .068)]
        _add_loft(m, 'trouser_' + side, leg, 'costume',
                  [{'shin_' + side: 1}, {'shin_' + side: 1}, {'shin_' + side: .5, 'thigh_' + side: .5},
                   {'thigh_' + side: 1}, {'thigh_' + side: .7, 'pelvis': .3}], _region_uv(REGIONS['trouser'], s < 0)(6, 5))

        def toe(j, f, pt):
            return (pt[0], pt[1], pt[2] - .018 * H * max(0., math.cos(f)))
        top = (Z(.15), .056, .062) if p['boots'] == 'cuffed' else (Z(.125), .043, .048)
        bt = [ring(6, s * cb, -.028, Z(.008), bts[0][1], .099 * boot),
              ring(6, s * cb, -.024, Z(.053), bts[1][1], .108 * boot, toe),
              ring(6, s * cb, .006, top[0], bts[2][1], top[2])]
        _add_loft(m, 'boot_' + side, bt, 'costume', 'foot_' + side, _region_uv(REGIONS['boot'], s < 0)(6, 3))
    # ---- head (head-local -> world)
    def W3(pt):
        return (pt[0] * hh, pt[1] * hh, zc + pt[2] * hh)
    # round 21: the neck stump (face loft ring 0) reaches below the torso top as well, not just into the collar
    fr = [[W3(pt) for pt in r] for r in face_rings(p, min(-.10, -(neck * H) / hh - .035, (torso_top - NECK_SINK * H - zc) / hh))]

    def face_uv(k, j, col):
        jj = j % 10
        if col is not None and col in FRONT_COLS:
            return _FACE_UV[(k, jj)]
        return _FACE_UV[('patch', k, jj)]
    _add_loft(m, 'face', fr, 'face', 'head', face_uv)
    nr = [[W3(pt) for pt in r] for r in nose_rings(p)]
    _add_loft(m, 'nose', nr, 'face', 'head', lambda k, j, col: _NOSE_UV[(k, j % 3)])
    for side, s in (('l', 1), ('r', -1)):
        er = [[W3(pt) for pt in r] for r in ear_rings(p, s)]
        _add_loft(m, 'ear_' + side, er, 'face', 'head',
                  lambda k, j, col: (EAR_PATCH[0] + (EAR_PATCH[2] - EAR_PATCH[0]) * ((j % 3) / 2.),
                                     EAR_PATCH[1] + (EAR_PATCH[3] - EAR_PATCH[1]) * (.25 + .5 * k)))
    hr_, crown = hair_rings(p)
    hrw = [[W3(pt) for pt in r] for r in hr_]
    hv = [.25, .50, .75, .92]
    _add_loft(m, 'hair', hrw, 'headwear', 'head', lambda k, j, col: (j / 10., hv[k]), caps=('flat', 'center'),
              centre={'pos': W3(crown), 'uv': (.5, 1.0)})
    xr = [[W3(pt) for pt in r] for r in extra_rings(p)]
    _add_loft(m, 'extra', xr, 'headwear', 'head', lambda k, j, col: (.02 + .96 * (j / 5.), .03 + .09 * k))
    for k, spec in enumerate(lock_specs(p)):
        _add_blade(m, 'lock_%02d' % k, [W3(v) for v in lock_piece(spec, p, k)])
    m.finish()
    return m


def stats(m):
    by = {}
    for name, ids in m.parts.items():
        by[name] = len(ids)
    return {'tris': len(m.faces), 'vertices': len(m.vertices), 'parts': by}
