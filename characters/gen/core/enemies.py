"""Two original enemy archetypes for Hermes64 combat (lane-combat-art). Pure Python 3.9, no Blender.

Archetype ids match the STORY 1.2 module data (wt-modules examples/gameplay-*: combat archetypes):
  cairn_dasher  template melee_dash_v1      a lumbering, low, shaggy beast carrying a cairn of three lichen-spotted
                                            stones grown into its back; a broad stone brow plate for ramming. It
                                            patrols heavily, rears and paws to telegraph, then charges head-down.
  reed_warden   template melee_approach_v1  a small hopping sentinel of woven reeds: an egg-shaped wicker body with a
                                            pale face plate and two glowing slit eyes, a fan crest of five reed blades,
                                            stubby leaf wings and thin bird legs. It hops in, squashes and fans its
                                            crest to telegraph, then springs and whips its crest down. A crest-tip
                                            socket lets a runtime lob a burr (core/enemy_props.py) instead.
Neither is modelled on any existing game creature: no tusks, trunk, shell-turtle, snout tube, propeller leaves,
single eye, fuse or mask-face mascot. Every part is a closed loft of rounded (superellipse-bulged) sections with
>= 5 sides (3-sided only for thin tapered reed blades / ear flaps), tapered ends, no box parts.

Each mesh: vertices, faces (outward CCW), uv, roles (coat | face), tiles, per-vertex bone weights, parts (lofts in
the ring layout core/connectivity.structure reads), bones (rest heads; every bone rests pointing +Z like the
shared rigs) and parents. Rig ids: dasher16_v1 (16 bones), warden15_v1 (15 bones).
"""
import math

TAU = 2 * math.pi
ENEMY_IDS = ['cairn_dasher', 'reed_warden']
TEMPLATE = {'cairn_dasher': 'melee_dash_v1', 'reed_warden': 'melee_approach_v1'}
RIG = {'cairn_dasher': 'dasher16_v1', 'reed_warden': 'warden15_v1'}
TOPOLOGY = {'cairn_dasher': 'cairn_dasher_v1', 'reed_warden': 'reed_warden_v1'}
BUDGET = 500                       # creature body budget: tris < 500

DASHER_PARENTS = {'root': None, 'hips': 'root', 'chest': 'hips', 'neck': 'chest', 'head': 'neck',
                  'cairn_low': 'chest', 'cairn_top': 'cairn_low', 'tail': 'hips',
                  'leg_fl': 'chest', 'paw_fl': 'leg_fl', 'leg_fr': 'chest', 'paw_fr': 'leg_fr',
                  'leg_bl': 'hips', 'paw_bl': 'leg_bl', 'leg_br': 'hips', 'paw_br': 'leg_br'}
WARDEN_PARENTS = {'root': None, 'body': 'root', 'head': 'body', 'crest': 'head', 'crest_l': 'head', 'crest_r': 'head',
                  'wing_l': 'body', 'wing_r': 'body', 'thigh_l': 'body', 'shin_l': 'thigh_l', 'foot_l': 'shin_l',
                  'thigh_r': 'body', 'shin_r': 'thigh_r', 'foot_r': 'shin_r', 'tail': 'body'}


# rest fold of the reed warden's ruff groups (axis-angle as quaternions): crest pitches back about X, crest_l / crest_r
# swing back about Z. core/enemy_pose._ruff applies the exact inverse for the flare.
RUFF_FOLD_ANGLE = 1.30


def _qaxis(axis, ang):
    s = math.sin(ang / 2.)
    return (math.cos(ang / 2.), axis[0] * s, axis[1] * s, axis[2] * s)


def _qrot(q, v):
    w, x, y, z = q
    # v' = q v q*
    tx = 2 * (y * v[2] - z * v[1]); ty = 2 * (z * v[0] - x * v[2]); tz = 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


RUFF_FOLD = {'crest': _qaxis((1., 0., 0.), -RUFF_FOLD_ANGLE), 'crest_l': _qaxis((0., 0., 1.), RUFF_FOLD_ANGLE),
             'crest_r': _qaxis((0., 0., 1.), -RUFF_FOLD_ANGLE)}


class EnemyMesh:
    def __init__(self, eid, bones, parents):
        self.id = eid; self.kind = 'enemy'; self.bones = bones; self.parents = parents
        self.vertices = []; self.faces = []; self.uv = []; self.roles = []; self.tiles = []; self.weights = []
        self.parts = {}; self.part_info = {}; self.topology = TOPOLOGY[eid]; self.rig = RIG[eid]
        self.params = {'height': 1.}


# ------------------------------------------------------------------ vector helpers
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return _mul(a, 1. / n) if n > 1e-12 else (0., 0., 1.)


def section(n, centre, direction, up, a, b, ex=2.2, bulge=None, phase=0.):
    """Rounded section: n points of a superellipse (exponent ex; 2 = ellipse) in the plane normal to `direction`.
    `up` fixes the section's b axis; bulge(theta) -> radial factor (per-angle sculpting). theta = 0 is 'up'."""
    d = _norm(direction)
    v = _sub(up, _mul(d, _dot(up, d)))
    v = _norm(v) if _dot(v, v) > 1e-10 else _norm(_cross(d, (1., 0., 0.)))
    u = _cross(v, d)
    pts = []
    for j in range(n):
        th = TAU * j / n + phase
        c, s = math.cos(th), math.sin(th)
        # superellipse radius scaling keeps it rounded but fuller than an ellipse (never a box: ex <= 2.6)
        k = (abs(c) ** ex + abs(s) ** ex) ** (-1. / ex)
        f = bulge(th) if bulge else 1.
        x = a * s * k * f; y = b * c * k * f
        pts.append(_add(centre, _add(_mul(u, x), _mul(v, y))))
    return pts


def _signed_volume(V, faces):
    vol = 0.
    for i, j, k in faces:
        vol += _dot(V[i], _cross(V[j], V[k]))
    return vol / 6.


def loft(m, name, rings, tile, weights, role='coat', caps=('flat', 'flat'), uv_rect=None, cap_role=(None, None),
         face_uv=None):
    """Closed loft in the ring layout of core/geometry.Mesh.loft: ring k vertices [k*n, (k+1)*n), bands first (first
    face (0, 1, n + 1)), caps after; outward winding is guaranteed by re-ordering the ring points (never the faces).
    weights: bone name or one {bone: w} per ring. uv_rect: (u0, v0, u1, v1) of the part in the 4x4 coat atlas
    (default: tile cell). face_uv(k, j) -> uv for faces given cap_role/band role 'face'."""
    n = len(rings[0]); nr = len(rings)
    if uv_rect is None:
        uv_rect = ((tile % 4 + .04) / 4., (tile // 4 + .04) / 4., (tile % 4 + .96) / 4., (tile // 4 + .96) / 4.)
    u0, v0, u1, v1 = uv_rect

    def build(rr):
        V = [p for ring in rr for p in ring]
        F = []
        for k in range(nr - 1):
            for j in range(n):
                a = k * n + j; b = k * n + (j + 1) % n; c = (k + 1) * n + (j + 1) % n; d = (k + 1) * n + j
                F.append((a, b, c)); F.append((a, c, d))
        caps_f = []
        extra = []
        for end, kind in zip((0, nr - 1), caps):
            ids = [end * n + j for j in range(n)]
            if kind == 'centre':
                cen = tuple(sum(rr[end][j][q] for j in range(n)) / n for q in range(3))
                ax = _norm(_sub(cen, tuple(sum(rr[1 if end == 0 else nr - 2][j][q] for j in range(n)) / n for q in range(3))))
                cen = _add(cen, _mul(ax, .25 * math.sqrt(sum((rr[end][0][q] - cen[q]) ** 2 for q in range(3)))))
                ci = len(V) + len(extra); extra.append(cen)
                for j in range(n):
                    caps_f.append(((ci, ids[(j + 1) % n], ids[j]) if end == 0 else (ci, ids[j], ids[(j + 1) % n]), end))
            else:
                seq = list(reversed(ids)) if end == 0 else ids
                for j in range(1, n - 1):
                    caps_f.append(((seq[0], seq[j], seq[j + 1]), end))
        return V + extra, F, caps_f
    V, F, CF = build(rings)
    if _signed_volume(V, F + [c for c, _ in CF]) < 0:
        rings = [[r[0]] + list(reversed(r[1:])) for r in rings]
        V, F, CF = build(rings)
    start = len(m.vertices)
    for idx, p in enumerate(V):
        m.vertices.append(tuple(p))
        k = min(idx // n, nr - 1) if idx < n * nr else (0 if idx == n * nr and caps[0] == 'centre' else nr - 1)
        m.weights.append({weights: 1.} if isinstance(weights, str) else dict(weights[k]))
    m.parts[name] = list(range(start, start + len(V)))
    m.part_info[name] = {'n': n, 'rings': nr, 'tile': tile, 'role': role}

    def uv_band(k, j):
        return (u0 + (u1 - u0) * (j / float(n)), v0 + (v1 - v0) * (k / float(max(1, nr - 1))))
    for fi, f in enumerate(F):
        k0 = f[0] // n
        uvs = []
        for vi in f:
            k, j = divmod(vi, n)
            if j == 0 and any((x % n) == n - 1 for x in f):
                j = n                           # seam column: wrap u to 1 instead of 0
            uvs.append(uv_band(k, j))
        m.faces.append(tuple(start + vi for vi in f)); m.uv.append(uvs); m.roles.append(role); m.tiles.append(tile)
    for f, end in CF:
        r = cap_role[0 if end == 0 else 1] or role
        uvs = []
        for vi in f:
            if r == 'face' and face_uv is not None:
                uvs.append(face_uv(vi, V))
            elif vi >= n * nr:
                uvs.append(((u0 + u1) / 2., (v0 if end == 0 else v1)))
            else:
                k, j = divmod(vi, n)
                th = TAU * j / n
                uvs.append(((u0 + u1) / 2. + (u1 - u0) * .3 * math.sin(th), (v0 if end == 0 else v1) + (v1 - v0) * .08 * math.cos(th) * (1 if end == 0 else -1)))
        m.faces.append(tuple(start + vi for vi in f)); m.uv.append(uvs); m.roles.append(r); m.tiles.append(tile)
    return m


def _finish(m):
    floor = min(v[2] for v in m.vertices)
    m.vertices = [(x, y, z - floor) for x, y, z in m.vertices]
    m.bones = {k: (x, y, z - floor) for k, (x, y, z) in m.bones.items()}
    m.bones['root'] = (0., 0., 0.)
    return m


def _wobble(seed, amp):
    """Deterministic organic per-angle radius variation (stones, hide tufts)."""
    return lambda th: 1. + amp * (math.sin(3 * th + seed) * .6 + math.sin(5 * th + seed * 1.7) * .4)


# ------------------------------------------------------------------ cairn dasher
def cairn_dasher():
    """v2: a low musk-heavy beast. Dark hide barrel whose shaggy coat hangs in a skirt over short legs, a pale
    shaggy mane that IS the neck (a thick collar between the shoulders and the head), a stone brow plate over
    glowing eyes, ears behind the plate, a tufted tail and a three-stone cairn grown into the shoulder hump."""
    # every bone pivots at the centre of the root ring of the piece it carries, so a rotation tilts that ring in
    # place inside its host instead of swinging it out (connectivity in every key)
    bones = {'root': (0, 0, 0), 'hips': (0, .26, .58), 'chest': (0, -.20, .62), 'neck': (0, -.42, .68),
             'head': (0, -.62, .58), 'cairn_low': (0, -.10, .90), 'cairn_top': (-.015, -.07, 1.085), 'tail': (0, .44, .64),
             'leg_fl': (.17, -.30, .56), 'paw_fl': (.21, -.31, .22), 'leg_fr': (-.17, -.30, .56), 'paw_fr': (-.21, -.31, .22),
             'leg_bl': (.14, .26, .56), 'paw_bl': (.20, .30, .22), 'leg_br': (-.14, .26, .56), 'paw_br': (-.20, .30, .22)}
    m = EnemyMesh('cairn_dasher', {k: tuple(float(c) for c in v) for k, v in bones.items()}, DASHER_PARENTS)
    Y = (0., 1., 0.); Z = (0., 0., 1.)

    def body_bulge(k):
        def f(th):
            c = math.cos(th)
            up = max(0., c)
            g = 1. + (.18 * up ** 3 if k in (1, 2) else .06 * up ** 2)          # shoulder hump under the cairn
            side = abs(((th + math.pi) % TAU) - math.pi)                         # 0 at the top .. pi at the belly
            g += .20 * math.exp(-((side - 2.25) / .42) ** 2) * (1. if 0 < k < 5 else .4)   # coat skirt hangs low
            g -= .06 * math.exp(-((side - math.pi) / .35) ** 2)                 # belly tucked between the skirts
            g *= 1. + .035 * math.sin(5 * th + 1.7 * k)                          # shag tufts on the outline
            return g
        return f
    body = [((0, -.52, .64), .17, .16), ((0, -.37, .65), .31, .29), ((0, -.13, .645), .335, .30),
            ((0, .13, .62), .31, .27), ((0, .36, .60), .25, .22), ((0, .50, .59), .13, .12)]
    rings = [section(10, c, Y, Z, a, b, ex=2.15, bulge=body_bulge(k)) for k, (c, a, b) in enumerate(body)]
    loft(m, 'body', rings, 0, [{'chest': 1.}, {'chest': 1.}, {'chest': .6, 'hips': .4}, {'hips': .7, 'chest': .3},
                               {'hips': 1.}, {'hips': 1.}])
    # mane = neck: a thick pale shaggy collar from inside the shoulders to around the back of the head
    def mane_bulge(k):
        def f(th):
            if k != 1:
                return 1.
            side = abs(((th + math.pi) % TAU) - math.pi)                        # 0 top .. pi under the chin
            return 1. + .20 * math.exp(-((side - math.pi) / .75) ** 2) + .035 * math.sin(5 * th + .8)   # hanging bib
        return f
    mane = [((0, -.40, .70), .19, .17), ((0, -.55, .68), .27, .28), ((0, -.65, .60), .14, .13)]
    md = (0., -1., -.35)
    loft(m, 'mane', [section(8, c, md, Z, a, b, ex=2.0, bulge=mane_bulge(k)) for k, (c, a, b) in enumerate(mane)], 4,
         [{'chest': 1.}, {'neck': 1.}, {'neck': .25, 'head': .75}])
    # head: back of the skull inside the mane, broad muzzle; face band = upper front (eyes under the brow plate)
    head = [((0, -.60, .60), .155, .145), ((0, -.71, .56), .185, .165), ((0, -.83, .49), .150, .130),
            ((0, -.92, .44), .085, .075)]
    loft(m, 'head', [section(8, c, (0, -1., -.45), Z, a, b, ex=2.1) for c, a, b in head], 1, 'head')
    _face_band(m, 'head', 1, 8, (.5, .62), eye_y=.66)
    # brow plate: the stone ram shield over the forehead and eyes
    plate = [((0, -.63, .70), .13, .05), ((0, -.75, .675), .20, .07), ((0, -.865, .585), .12, .045)]
    loft(m, 'plate', [section(6, c, (0, -1., -.35), Z, a, b, ex=2.4) for c, a, b in plate], 2, 'head')
    # ears: small round flaps behind the plate, angled out and back
    for s, side in ((1, 'l'), (-1, 'r')):
        e = [((s * .13, -.63, .66), .042, .028), ((s * .245, -.58, .70), .012, .009)]
        loft(m, 'ear_' + side, [section(3, c, (s * .9, .35, .3), Z, a, b, ex=2.) for c, a, b in e], 1, 'head')
    # legs: short, thick tapered columns flaring into a broad hoof; tops buried in the barrel
    for nm, x, y in (('fl', .21, -.30), ('fr', -.21, -.30), ('bl', .20, .31), ('br', -.20, .31)):
        front = nm[0] == 'f'
        xi = x * (.80 if front else .70)
        yi = y if front else y - .05
        lg = [((xi, yi, .58), .085, .085), ((x, y - .01, .20), .072, .075), ((x, y - .025, 0.), .092, .10)]
        loft(m, 'leg_' + nm, [section(5, c, (0, 0, -1.), (0, -1., 0), a, b, ex=2.2) for c, a, b in lg], 3,
             [{'leg_' + nm: 1.}, {'paw_' + nm: 1.}, {'paw_' + nm: 1.}])
    # tail: a short tuft
    tl = [((0, .44, .64), .045, .042), ((0, .61, .69), .05, .045), ((0, .72, .64), .012, .012)]
    loft(m, 'tail', [section(4, c, (0, 1., .3), Z, a, b) for c, a, b in tl], 1, [{'tail': 1.}] * 3)
    # cairn: three flat, rounded, lichen-spotted stones stacked on the hump, each a little offset
    stones = [('stone_1', (0., -.10, .95), .25, .19, .060, 1.3, 'cairn_low'),
              ('stone_2', (.03, -.08, 1.05), .17, .13, .050, 2.9, 'cairn_low'),
              ('stone_3', (-.015, -.06, 1.135), .11, .085, .042, 4.1, 'cairn_top')]
    for nm, (cx, cy, cz), a, b, h, seed, bone in stones:
        bu = _wobble(seed, .07)
        first = nm == 'stone_1'
        rr = [section(6, (cx, cy, cz - h * (2.4 if first else 1.)), Z, (0, -1., 0), a * (.55 if first else .80),
                      b * (.55 if first else .80), ex=2.3, bulge=bu),
              section(6, (cx, cy, cz), Z, (0, -1., 0), a, b, ex=2.3, bulge=bu),
              section(6, (cx, cy, cz + h * .9), Z, (0, -1., 0), a * .72, b * .72, ex=2.3, bulge=bu)]
        loft(m, nm, rr, 2, bone)
    return _finish(m)


def _face_band(m, part, k_lo, n, vrange=None, eye_y=None):
    """Make band k_lo -> k_lo+1 of a loft the 'face' material, UV-mapped round the loft into one face-atlas cell:
    u = position round the section (0/1 = the top, under the brow plate; .25 / .75 = the two flanks, where the eyes
    are painted), v = 0 at ring k_lo .. 1 at ring k_lo+1. Eyes on the flanks read from the front, side and 3-4."""
    start = m.parts[part][0]
    for fi, f in enumerate(m.faces):
        if not all(start <= v < start + n * m.part_info[part]['rings'] for v in f):
            continue
        ks = [(v - start) // n for v in f]
        if min(ks) != k_lo or max(ks) != k_lo + 1:
            continue
        js = [(v - start) % n for v in f]
        if max(js) == n - 1 and min(js) == 0:
            js = [j if j else n for j in js]           # wrap the seam column to u = 1
        m.roles[fi] = 'face'
        m.uv[fi] = [(j / float(n), float(k - k_lo)) for j, k in zip(js, ks)]


# ------------------------------------------------------------------ reed warden
def _blade(m, name, pts, bone, tile, flat=1.25, thin=.7, up=(0., -1., 0.)):
    rr = []
    for k, (c, r) in enumerate(pts):
        d = _sub(pts[min(k + 1, len(pts) - 1)][0], pts[max(k - 1, 0)][0])
        rr.append(section(3, c, d, up, r * flat, r * thin, ex=2.))
    loft(m, name, rr, tile, bone)


def reed_warden():
    """v3: a small woven-reed sentinel with a ruff. A forward-leaning woven body (low-contrast coils), a big pale face
    shield with two glowing slit eyes and a short beak, and a RUFF of seven reed blades rooted round the rim of the
    shield: swept back along the head at rest, flared into a sunburst around the face to telegraph. Broad leaf wings,
    thin bird legs with long feet, a short reed tail fan."""
    bones = {'root': (0, 0, 0), 'body': (0, 0, .32), 'head': (0, -.03, .54), 'crest': (0, -.15, .645),
             'crest_l': (.118, -.15, .545), 'crest_r': (-.118, -.15, .545), 'wing_l': (.13, .03, .50),
             'wing_r': (-.13, .03, .50), 'thigh_l': (.075, .01, .33), 'shin_l': (.085, -.025, .17), 'foot_l': (.09, -.005, .034),
             'thigh_r': (-.075, .01, .33), 'shin_r': (-.085, -.025, .17), 'foot_r': (-.09, -.005, .034), 'tail': (0, .14, .38)}
    m = EnemyMesh('reed_warden', {k: tuple(float(c) for c in v) for k, v in bones.items()}, WARDEN_PARENTS)
    Z = (0., 0., 1.)
    def weave_bulge(k):
        return lambda th: 1. + .025 * math.sin(8 * th + k * 1.3)
    axis = _norm((0., -.22, 1.))                       # the body leans forward
    egg = [(.27, .075, .07), (.33, .17, .16), (.44, .215, .205), (.56, .205, .195), (.655, .15, .145), (.71, .06, .058)]
    rings = []
    for k, (z, a, b) in enumerate(egg):
        t = (z - .27) / axis[2]
        c = (0., axis[1] * t + .01, z)
        rings.append(section(10, c, axis, (0, -1., 0), a, b, ex=2.05, bulge=weave_bulge(k)))
    loft(m, 'body', rings, 0, [{'body': 1.}, {'body': 1.}, {'body': 1.}, {'body': .4, 'head': .6}, {'head': 1.},
                               {'head': 1.}])
    # face shield: a broad pale oval standing proud of the woven front; its front cap carries the eyes (face atlas)
    fc = (0., .545)
    fp = [((0, -.10, fc[1]), .15, .13), ((0, -.245, fc[1]), .165, .14), ((0, -.28, fc[1]), .12, .10)]

    def face_uv(vi, V):
        p = V[vi]
        return (.5 + p[0] / .30, .5 + (p[2] - fc[1]) / .25)
    loft(m, 'mask', [section(8, c, (0, -1., 0), Z, a, b, ex=2.3) for c, a, b in fp], 1, 'head',
         caps=('flat', 'flat'), cap_role=(None, 'face'), face_uv=face_uv)
    # beak: short, under the eyes, poking out of the shield
    bk = [((0, -.27, .48), .03, .022), ((0, -.34, .455), .004, .003)]
    loft(m, 'beak', [section(3, c, (0, -1., -.35), Z, a, b, ex=2.) for c, a, b in bk], 2, 'head')
    # ruff: seven reed blades rooted round the shield rim. Each blade is built in its FLARED state (pointing along its
    # rim radial, broad side to the front, a slight forward cup), then folded back about its group pivot by the group's
    # FOLD rotation: that folded state is the rest pose, so the telegraph (the inverse rotation on the group bone,
    # core/enemy_pose._ruff) restores an exact radial sunburst round the face.
    # roots of a group lie on its pivot's rotation axis (top three on an X-parallel line along the shield's crown,
    # each side pair on a vertical line at the shield's flank), so folding / flaring never moves a root
    ruff = [('ruff_t', 0., 'crest', .30, (0., -.15, .645)), ('ruff_l1', 38., 'crest', .28, (.07, -.15, .645)),
            ('ruff_r1', -38., 'crest', .28, (-.07, -.15, .645)),
            ('ruff_l2', 76., 'crest_l', .24, (.118, -.15, .595)), ('ruff_r2', -76., 'crest_r', .24, (-.118, -.15, .595)),
            ('ruff_l3', 114., 'crest_l', .18, (.118, -.15, .495)), ('ruff_r3', -114., 'crest_r', .18, (-.118, -.15, .495))]
    for nm, deg, bone, L, root in ruff:
        A = math.radians(deg)
        rad = (math.sin(A), 0., math.cos(A)); fwd = (0., -1., 0.); tan = (math.cos(A), 0., -math.sin(A))
        pts = []
        for t, r in ((0., .022), (.5, .02), (1., .004)):
            pts.append((_add(root, _add(_mul(rad, L * t), _mul(fwd, .10 * L * t * t))), r))
        rr = []
        for k, (c, r) in enumerate(pts):
            d = _sub(pts[min(k + 1, 2)][0], pts[max(k - 1, 0)][0])
            rr.append(section(3, c, d, _cross(_norm(d), tan), r * 1.3, r * .65, ex=2.))
        start = len(m.vertices)
        loft(m, nm, rr, 3, bone)
        piv = m.bones[bone]
        qf = RUFF_FOLD[bone]
        m.vertices[start:] = [_add(piv, _qrot(qf, _sub(v, piv))) for v in m.vertices[start:]]
    # wings: broad leaf wings at the sides, tips down-back
    for s, side in ((1, 'l'), (-1, 'r')):
        wp = [((s * .13, .03, .50), .024, .05), ((s * .25, .07, .43), .028, .085), ((s * .30, .13, .31), .006, .022)]
        rr = []
        for k, (c, a, b) in enumerate(wp):
            d = _sub(wp[min(k + 1, 2)][0], wp[max(k - 1, 0)][0])
            rr.append(section(5, c, d, (0, -1., .2), a, b, ex=2.2))
        loft(m, 'wing_' + side, rr, 4, 'wing_' + side)
    # legs: thin bird legs, knee forward
    for s, side in ((1, 'l'), (-1, 'r')):
        lg = [((s * .075, .01, .33), .042, .042), ((s * .085, -.025, .17), .027, .027), ((s * .09, -.005, .034), .019, .019)]
        rr = [section(5, c, (0, 0, -1.), (0, -1., 0), a, b) for c, a, b in lg]
        loft(m, 'leg_' + side, rr, 5, [{'thigh_' + side: 1.}, {'thigh_' + side: .5, 'shin_' + side: .5}, {'foot_' + side: 1.}])
        ft = [((s * .09, .045, .024), .032, .022), ((s * .09, -.02, .028), .062, .028), ((s * .09, -.09, .012), .046, .010)]
        loft(m, 'foot_' + side, [section(5, c, (0, -1., 0), Z, a, b, ex=2.3) for c, a, b in ft], 5, 'foot_' + side)
    # tail fan: two reed blades out the back, low
    for nm, sx, up_ in (('tail_l', .05, .0), ('tail_c', 0., .03), ('tail_r', -.05, .0)):
        pts = [((sx * .6, .13, .38), .022), ((sx * 1.8, .26, .41 + up_), .018), ((sx * 2.8, .36, .47 + up_ * 1.5), .004)]
        _blade(m, nm, pts, 'tail', 3, up=Z)
    return _finish(m)


def build(eid):
    if eid == 'cairn_dasher':
        return cairn_dasher()
    if eid == 'reed_warden':
        return reed_warden()
    raise ValueError('unknown enemy ' + str(eid))
