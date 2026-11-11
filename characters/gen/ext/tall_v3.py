"""tall_v3: the fixed round-21 visor body (lane CHARS4), built as a DELTA on the round-21 builder.

The round-21 character (preset tall_v2, cameo/cameo_visor_01.glb) stays frozen and selectable. tall_v3 is the same
character with three corrections asked for in review:

  1. COLLAR  the stand-up tube that hid the neck, chin and mouth becomes a low rib collar: about 5 cm at the nape, a
             little lower at the sides and open in a V at the throat, so neck, jaw and mouth show.
  2. FACE    the green cheek mark is gone (cheek_leaf False; nothing else on the face changes).
  3. LEGS    the two trouser lofts and boots are one plumb column per leg: ring centres on a straight line from the hip
             to the ankle, under the jacket hem in both views; the hem is a touch wider than the legs (in r21 the
             trousers stuck out past the hem), the leg bones follow the ring centres, and the torso rings stack over
             the same fore-aft line. The standing pose is symmetric (ext/clips_tall_v3 idle), not the r21 'confident'
             weight shift that splayed one leg.

  4. NECK    lowering the collar exposes what the tube hid, so round 2 gives the head a real neck: the old neck stump
             ring becomes an under-jaw ring (jaw break, chin overhang) and a 10-sided neck column runs from it into the
             collar; the collar gets an inner wall (lining) instead of a flat lid; the back of the skull is pulled
             inside the 6-sided hair cap it used to poke through (bare patch at the back of the head).

Nothing here copies the round-21 builder: `person(cameo, values)` calls the restricted core/cameo.py that the caller
loaded (adventure_maker/nbchars/tall_v3.py) and then edits the finished mesh: rings are moved, four hidden caps are
dropped (16 + 12 triangles) and the neck column and collar lining are added (20 + 16). 698 triangles, the 16 bones of
human16_v1 untouched. With FIXES = () the result is the round-21 mesh, vertex for vertex (tools/chars4_build.py
--parity).

REVISION 2 (lane CHARS5, review of stills-04): two more fixes, both on by default, revision 1 stays buildable with
fixes=FIXES_R1 (the before column of every measurement):
  5. NECK SHORT  the head (skin, nose, hair, visor and the head bone) sits NECK_DROP lower on the same shoulders, so
                 less neck shows in the V of the collar. Collar, torso and neck base do not move.
  6. FACE WIDE   the jaw-line ring and the cheek ring are wider (FACE_WIDE, x only; the vertices under the hair cap
                 keep their place) and the under-jaw ring follows. The brow ring, hair and visor keep their width, so
                 the head size is unchanged.
  Also: the knee tweak of the trouser ring used `cos > .5` on a 6-sided ring, where two vertices sit at cos = .5 up to
  float rounding; one leg took the tweak and the mirrored leg did not (2.7 mm, measured by symmetry()). The test has a
  margin now and both legs are equal.

REVISION 3 (lane CHARS6, review of stills-05: "the chest a bit less pointy"): one more fix, on by default; revision 2
stays buildable with fixes=FIXES_R2, revision 1 with FIXES_R1, round 21 with ():
  7. CHEST FLAT  the torso is four 8-sided rings (hem, waist, chest, top). In the side view its front is two straight
                 runs that meet at the chest ring, and in revision 2 that ring stood .039 H (6.9 cm) in front of the
                 line from the top ring to the waist ring: one peak at .679 H. The front three vertices of the chest
                 ring come back by CHEST_FLAT (x cos of the ring angle: a shallower half ellipse, so the plan view
                 stays a smooth arc and the two side vertices, the width, do not move). Nothing else moves: no vertex
                 is added, the top ring (collar, neck), waist, hem, sleeves and every UV are as in revision 2.
                 chest_measure() gives the numbers; CHEST_FLAT_STEPS are the settings offered for review.
"""
import math

from . import people as PP

PRESET = 'tall_v3'
REVISION = 3
FIXES_R1 = ('collar', 'neck', 'legs', 'torso', 'skull')                 # stills-01..04
FIXES_R2 = FIXES_R1 + ('neck_short', 'face_wide', 'knee_even')          # revision 2 (stills-05)
FIXES = FIXES_R2 + ('chest_flat',)                                      # revision 3 (stills-06)
FIXES_BY_REVISION = {1: FIXES_R1, 2: FIXES_R2, 3: FIXES}
FLOOR = .006            # x H: round-21 Mesh.finish() grounds the boot sole ring (authored at .006 H)

# ---- collar (x H, authored z: before grounding). A low rib collar: outer wall B -> rim T, lining T -> inner ring I.
TORSO_TOP = .778
COLLAR_B = (.010, .070, .066, .768)         # centre y, rx, ry, z: sunk .010 into the torso like round 21
COLLAR_T = (.014, .050, .050)               # rim: centre y, rx, ry (leans in a little; a stand collar, not a cone)
# rim height over the torso top by ring vertex (j = 0 nape, 2 / 6 sides, 4 throat): open V at the front
COLLAR_RISE = (.052, .049, .041, .024, .010, .024, .041, .049)
COLLAR_I = (.017, .0435, .0430, .772)       # lining bottom ring, just under the torso top, close around the neck
COLLAR_W_RIM = {'spine': .9, 'head': .1}    # r21 .55 / .45 followed the head: right for a tube, wrong for a low collar
COLLAR_UV = (.015, .258, .47, .234)         # u0, v0, du, dv of the collar atlas region as round 21 mapped it
COLLAR_V = {'outer': (.62, 1.), 'lining': (0., .38)}   # region v of the outer wall (bottom, rim) / lining (bottom, rim)
# ---- neck (x H, authored z). Face loft ring 0 (r21: a 9 cm stump inside the tube) becomes the under-jaw ring; a new
# 10-sided ring N at the collar base makes the neck column.
JAW_UNDER = (.007, .0285, .0310, .841, .016)   # centre y, rx, ry, z, tilt: back .016 higher / throat .016 lower
NECK_BASE = (.018, .0400, .0390, .772)         # centre y, rx, ry, z (inside the collar): wider and further back, so
#                                                the neck tapers up and leans forward into the head
NECK_AO = {'jaw': .84, 'under': .70, 'throat': .60, 'top': .62, 'base': .82, 'lining': .58}     # vertex shade multipliers (assembly)
# ---- revision 2
NECK_DROP = .020                    # x H: the whole head and the head bone come down by this (3.6 cm at 1.80 m)
FACE_WIDE = {1: 1.12, 2: 1.08}      # face loft ring -> x scale (1 jaw line, 2 cheek); ring 3 (brow) is not touched
JAW_UNDER_RX_WIDE = .0310           # under-jaw ring half-width with the wider jaw (JAW_UNDER has .0285)
HEAD_PARTS = ('face', 'nose', 'hair', 'visor', 'spike_', 'leaf_')
# ---- skull under the hair cap: back/side vertices of the brow ring and back vertices of the cheek ring are scaled
# toward the head axis so the 10-sided skull stays inside the 6-sided cap (r21: bare skin patch at the back)
SKULL_IN = .86
SKULL_UNDER_CAP = {3: (0, 1, 2, 8, 9), 2: (0, 1, 9)}
# ---- torso rings (z, centre y, rx, ry) x H: hem a touch wider than the legs, rings stacked on one fore-aft line,
# chest 2 cm shallower so the back does not overhang the legs in the side view
TORSO = [(.472, .002, .124, .094), (.565, .000, .084, .076), (.685, .002, .132, .116), (.778, .006, .079, .081)]
# ---- legs: (z, centre x, centre y, rx, ry) x H from the ankle up; centres on one straight line hip -> ankle
LEG = [(.100, .0680, .002, .046, .045), (.172, .0665, .003, .058, .064), (.280, .0640, -.001, .057, .066),
       (.388, .0615, .002, .062, .074), (.480, .0600, .002, .062, .066)]
# ---- revision 3: chest front. x H the front of the chest ring (TORSO[CHEST_RING]) comes back; 0 = revision 2.
CHEST_RING = 2
CHEST_FLAT = .010                           # default: one step flatter than revision 2 (1.8 cm at 1.80 m)
CHEST_FLAT_STEPS = (0., .010, .018, .026)   # the dial as offered for review (stills-06 options sheet)
# The alignment gate wants the torso ring centres stacked within .008 H fore-aft. Taking .010 off the front only moves
# the chest ring's centre back .005 (spread .006 -> .007). Past that the back of the ring comes in by the excess, so
# every setting of the dial keeps that stacking; at the default the back does not move.
CHEST_FLAT_FRONT_ONLY = .010
KNEE_FWD = .006
POUCH = (.008, .003)
BOOT_X = .068                               # boot centre = ankle centre (r21: .078, outside the knee)
LEG_BONES = {'thigh': (.0600, .002), 'shin': (.0640, -.002), 'foot': (.0680, .002)}   # (x, y) x H; z as round 21


def values(v):
    """Round-21 cameo params -> tall_v3 params (the cheek mark off)."""
    v = dict(v)
    v['cheek_leaf'] = False
    return v


def _ring_ids(m, part, n, k):
    ids = m.parts[part]
    return ids[k * n:(k + 1) * n]


def _put(m, part, n, k, pts):
    for vi, pt in zip(_ring_ids(m, part, n, k), pts):
        m.vertices[vi] = (float(pt[0]), float(pt[1]), float(pt[2]))


def _drop(m, pred):
    keep = [i for i, f in enumerate(m.faces) if not pred(f)]
    for attr in ('faces', 'uv', 'roles', 'tiles'):
        setattr(m, attr, [getattr(m, attr)[i] for i in keep])


def _face_meta(m, part):
    ids = set(m.parts[part])
    for i, f in enumerate(m.faces):
        if f[0] in ids and f[1] in ids and f[2] in ids:
            return m.roles[i], m.tiles[i]
    raise ValueError(part)


def _add_ring(m, part, pts, weight):
    start = len(m.vertices)
    for pt in pts:
        m.vertices.append((float(pt[0]), float(pt[1]), float(pt[2])))
        m.weights.append(dict(weight))
    ids = list(range(start, len(m.vertices)))
    m.parts[part] = list(m.parts[part]) + ids
    return ids


def _band(m, lower, upper, uv, role, tile, inward=False):
    """Quads between two rings of equal size (loft winding: outward unless inward). uv(j, top) -> atlas uv."""
    n = len(lower)
    for j in range(n):
        j1 = (j + 1) % n
        a, b, c, d = lower[j], lower[j1], upper[j1], upper[j]
        ua, ub, uc, ud = uv(j, 0), uv(j + 1, 0), uv(j + 1, 1), uv(j, 1)
        tris = [((a, b, c), [ua, ub, uc]), ((a, c, d), [ua, uc, ud])]
        for f, t in tris:
            if inward:
                f = (f[0], f[2], f[1]); t = [t[0], t[2], t[1]]
            m.faces.append(f); m.uv.append(t); m.roles.append(role); m.tiles.append(tile)


def person(cameo, vals, fixes=FIXES):
    m = cameo.person(values(vals) if fixes else dict(vals))
    H = m.params['height']; B = m.params['build']; V = m.params['trouser_volume']

    def Z(f):
        return (f - FLOOR) * H

    def ring(n, x, y, z, rx, ry, tweak=None):
        return PP.zring(n, x * H, y * H, Z(z), rx * H, ry * H, tweak)

    def chest(j, f, pt):
        c = math.cos(f)                         # +1 front, 0 sides, -1 back; equal for a vertex and its mirror
        d = CHEST_FLAT if c > 0. else max(0., CHEST_FLAT - CHEST_FLAT_FRONT_ONLY)
        if abs(c) < 1e-9 or not d:
            return pt                           # side vertices (cos = 6e-17) and an unmoved back stay bit for bit
        return (pt[0], pt[1] + d * H * c, pt[2])
    if 'torso' in fixes:
        for k, (z, cy, rx, ry) in enumerate(TORSO):
            _put(m, 'torso', 8, k, ring(8, 0., cy, z, rx * B, ry, chest if k == CHEST_RING and 'chest_flat' in fixes else None))
    m.ao = {}
    if 'collar' in fixes:
        role, tile = _face_meta(m, 'collar')
        B = _ring_ids(m, 'collar', 8, 0); T = _ring_ids(m, 'collar', 8, 1)
        cy, rx, ry, z = COLLAR_B
        _put(m, 'collar', 8, 0, ring(8, 0., cy, z, rx, ry))
        cy, rx, ry = COLLAR_T
        _put(m, 'collar', 8, 1, ring(8, 0., cy, TORSO_TOP, rx, ry, lambda j, f, pt: (pt[0], pt[1], pt[2] + COLLAR_RISE[j] * H)))
        for vi in T:
            m.weights[vi] = dict(COLLAR_W_RIM)
        cy, rx, ry, z = COLLAR_I
        inner = ring(8, 0., cy, z, rx, ry)
        inner = [(pt[0], pt[1], min(pt[2], m.vertices[T[j]][2] - .004 * H)) for j, pt in enumerate(inner)]
        cs = set(m.parts['collar'])
        _drop(m, lambda f: f[0] in cs and f[1] in cs and f[2] in cs)        # wall is rebuilt, both lids go
        I = _add_ring(m, 'collar', inner, {'spine': 1.})
        u0, v0, du, dv = COLLAR_UV

        def cuv(span):
            return lambda j, top: (u0 + du * j / 8., v0 + dv * span[1 if top else 0])
        _band(m, B, T, cuv(COLLAR_V['outer']), role, tile)
        _band(m, I, T, cuv(COLLAR_V['lining']), role, tile, inward=True)
        for vi in I:
            m.ao[vi] = NECK_AO['lining']
    if 'face_wide' in fixes:
        for k, sx in FACE_WIDE.items():
            ids = _ring_ids(m, 'face', 10, k)
            for j, vi in enumerate(ids):
                if j in SKULL_UNDER_CAP.get(k, ()):
                    continue                                    # stays inside the hair cap
                x, y, z = m.vertices[vi]
                m.vertices[vi] = (x * sx, y, z)
    if 'neck' in fixes:
        role, tile = _face_meta(m, 'face')
        R0 = _ring_ids(m, 'face', 10, 0); R3 = set(_ring_ids(m, 'face', 10, 3)); r0 = set(R0)
        _drop(m, lambda f: (f[0] in r0 and f[1] in r0 and f[2] in r0) or (f[0] in R3 and f[1] in R3 and f[2] in R3))
        cy, rx, ry, z, tilt = JAW_UNDER
        if 'face_wide' in fixes:
            rx = JAW_UNDER_RX_WIDE
        _put(m, 'face', 10, 0, ring(10, 0., cy, z, rx, ry, lambda j, f, pt: (pt[0], pt[1], pt[2] - tilt * H * math.cos(f))))
        cy, rx, ry, z = NECK_BASE
        N = _add_ring(m, 'face', ring(10, 0., cy, z, rx, ry), {'spine': 1.})
        su0, sv0, su1, sv1 = PP.SKIN_PATCH
        # the neck column gets its own top ring (same place as the under-jaw ring): its own normals and its own shade,
        # so the shadow under the chin lies on the neck and the jaw plane above it keeps a clean edge
        NT = _add_ring(m, 'face', [m.vertices[vi] for vi in R0], {'head': 1.})
        m.neck_rings = {'base': N, 'top': NT}
        _band(m, N, NT, lambda j, top: (su0 + (su1 - su0) * (.1 + .8 * (j % 11) / 10.), sv0 + (sv1 - sv0) * (.7 if top else .3)), role, tile)
        # the under-jaw plane (jaw line -> under-jaw ring) is rebuilt on its own copy of the jaw-line ring: own normals
        # (it faces down, so the baked light darkens it), flat skin texels, own shade. The jaw is then drawn by a mesh
        # edge, not by the stepped texel band the shared face painter puts under the chin.
        R1 = _ring_ids(m, 'face', 10, 1); band = r0 | set(R1)
        _drop(m, lambda f: f[0] in band and f[1] in band and f[2] in band)
        J = _add_ring(m, 'face', [m.vertices[vi] for vi in R1], {'head': 1.})
        _band(m, R0, J, lambda j, top: (su0 + (su1 - su0) * (.1 + .8 * (j % 11) / 10.), sv0 + (sv1 - sv0) * (.7 if top else .3)), role, tile)
        for vi in J:
            m.ao[vi] = NECK_AO['jaw']
        for j, vi in enumerate(R0):
            m.ao[vi] = NECK_AO['throat'] if j in (4, 5, 6) else NECK_AO['under']
        for vi in NT:
            m.ao[vi] = NECK_AO['top']
        for vi in N:
            m.ao[vi] = NECK_AO['base']
    if 'skull' in fixes:
        ax = sum(m.vertices[vi][1] for vi in _ring_ids(m, 'face', 10, 3)) / 10.
        for k, js in SKULL_UNDER_CAP.items():
            ids = _ring_ids(m, 'face', 10, k)
            for j in js:
                x, y, z = m.vertices[ids[j]]
                m.vertices[ids[j]] = (x * SKULL_IN, ax + (y - ax) * SKULL_IN, z)
    if 'legs' in fixes:
        for side, s in (('l', 1), ('r', -1)):
            def knee(j, f, pt):
                c = math.cos(f)
                # revision 1 compared with .5 exactly: the two ring vertices at cos = .5 fell on either side of it
                # by float rounding, differently for the mirrored leg (2.7 mm left-right difference)
                return (pt[0], pt[1] - KNEE_FWD * H * max(0., c) ** 2, pt[2]) if c > (.51 if 'knee_even' in fixes else .5) else pt

            def pouch(j, f, pt, s=s):
                if math.sin(f) * s > .5:
                    return (pt[0] + s * POUCH[0] * H, pt[1] + POUCH[1] * H, pt[2])
                return pt
            tw = [None, None, knee, pouch, None]
            for k, (z, cx, cy, rx, ry) in enumerate(LEG):
                vol = V if k in (1, 2, 3) else 1.
                _put(m, 'trouser_' + side, 6, k, ring(6, s * cx, cy, z, rx * vol, ry * vol, tw[k]))
            # boots: same shape, re-centred under the ankle ring
            ids = m.parts['boot_' + side]
            c0 = sum(m.vertices[vi][0] for vi in ids[:7]) / 7.
            dx = s * BOOT_X * H - c0
            for vi in ids:
                x, y, z = m.vertices[vi]
                m.vertices[vi] = (x + dx, y + LEG[0][2] * H, z)
            for bone, (bx, by) in LEG_BONES.items():
                z = m.bones[bone + '_' + side][2]
                m.bones[bone + '_' + side] = (s * bx * H, by * H, z)
    if 'neck_short' in fixes:
        d = NECK_DROP * H
        base = set(getattr(m, 'neck_rings', {}).get('base', ()))
        for part, ids in m.parts.items():
            if not part.startswith(HEAD_PARTS):
                continue
            for vi in ids:
                if vi in base:
                    continue                                    # the neck base ring stays in the collar
                x, y, z = m.vertices[vi]
                m.vertices[vi] = (x, y, z - d)
        bx, by, bz = m.bones['head']
        m.bones['head'] = (bx, by, bz - d)
    floor = min(v[2] for v in m.vertices)
    assert abs(floor) < 1e-9, 'tall_v3 must stay grounded like round 21 (floor %r)' % floor
    m.preset = PRESET if fixes else 'tall_v2'
    return m


def alignment(m):
    """Measured leg/torso alignment of a visor-body mesh (rest pose), x H. Used as the gate and its known-bad control
    (round 21): legs inside the hem, leg ring centres on a straight line, fore-aft centres stacked."""
    H = m.params['height']

    def rings(part, n):
        ids = m.parts[part]
        out = []
        for k in range(len(ids) // n if part != 'face' else 4):
            pts = [m.vertices[vi] for vi in ids[k * n:(k + 1) * n]]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            out.append({'z': sum(p[2] for p in pts) / n / H, 'x0': min(xs) / H, 'x1': max(xs) / H,
                        'cx': (min(xs) + max(xs)) / 2 / H, 'cy': (min(ys) + max(ys)) / 2 / H,
                        'y0': min(ys) / H, 'y1': max(ys) / H})
        return out
    torso = rings('torso', 8); leg = rings('trouser_l', 6); boot = rings('boot_l', 7)
    hem = torso[0]
    # the widest trouser ring (the thigh pouch included) against the hem
    over = max(r['x1'] for r in leg) - hem['x1']
    # straightness: max distance of a ring centre from the hip->ankle line (front view), pouch ring excluded
    top, ank = leg[-1], leg[0]
    dev = 0.
    for r in leg[:3] + leg[4:]:
        t = (r['z'] - ank['z']) / (top['z'] - ank['z'])
        dev = max(dev, abs(r['cx'] - (ank['cx'] + t * (top['cx'] - ank['cx']))))
    fa = [r['cy'] for r in leg]
    return {
        'leg_outer_minus_hem': round(over, 4),              # > 0: trousers stick out past the jacket hem
        'leg_centre_line_dev': round(dev, 4),               # front view, x H
        'leg_fore_aft_spread': round(max(fa) - min(fa), 4),   # side view zig-zag of ring centres
        'hip_minus_torso_fore_aft': round(leg[-1]['cy'] - hem['cy'], 4),
        'torso_fore_aft_spread': round(max(r['cy'] for r in torso) - min(r['cy'] for r in torso), 4),
        'boot_minus_ankle_x': round(boot[2]['cx'] - leg[0]['cx'], 4),
        'thigh_bone_minus_hip_ring_x': round(m.bones['thigh_l'][0] / H - leg[-1]['cx'], 4),
        'left_right_asymmetry': symmetry_max(symmetry(m)),  # rest mesh, torso / arms / legs / head skin, x H
    }


BODY_GROUPS = {'torso': ('torso', 'collar'), 'arms': ('sleeve_', 'mitt_', 'thumb_'), 'legs': ('trouser_', 'boot_'),
               'head': ('face', 'nose', 'visor')}
HAIR_GROUP = ('hair', 'spike_', 'leaf_')        # the spikes are asymmetric by design: reported, not gated
SYMMETRY_LIMIT = .0005                          # x H (0.9 mm at 1.80 m); round 21 rest mesh: .0025 (legs)


def _group_ids(m, prefixes):
    return sorted({vi for part, ids in m.parts.items() if part.startswith(tuple(prefixes)) for vi in ids})


def symmetry(m, verts=None):
    """Left-right asymmetry of the mesh: every vertex of a group is mirrored in the x = 0 plane and the distance to
    the nearest vertex of the same group is taken; the largest such distance per group, in mm and x H. verts: posed
    vertex positions (default: the rest mesh)."""
    H = m.params['height']
    V = verts if verts is not None else m.vertices
    out = {}
    for g, prefixes in list(BODY_GROUPS.items()) + [('hair_not_gated', HAIR_GROUP)]:
        P = [tuple(float(c) for c in V[vi]) for vi in _group_ids(m, prefixes)]
        worst = 0.
        for (x, y, z) in P:
            best = min((x + q[0]) ** 2 + (y - q[1]) ** 2 + (z - q[2]) ** 2 for q in P)
            worst = max(worst, best)
        worst = math.sqrt(worst)
        out[g] = {'mm': round(worst * 1000., 2), 'x_h': round(worst / H, 5)}
    return out


def symmetry_max(sym):
    return max(v['x_h'] for g, v in sym.items() if g in BODY_GROUPS)


def head_measure(m):
    """Neck and face numbers of a tall_v3 mesh (needs the neck fix), x H and as ratios. head height = chin (lowest
    point of the jaw-line ring) to the top of the hair cap, spikes not counted. neck_front = chin down to the collar
    rim at the throat (what shows in the V); neck_side = jaw corner down to the collar rim at the side;
    neck_column = under-jaw ring centre down to the neck base ring."""
    H = m.params['height']

    def ring(part, n, k):
        return [m.vertices[vi] for vi in _ring_ids(m, part, n, k)]
    jaw, cheek, brow, under = ring('face', 10, 1), ring('face', 10, 2), ring('face', 10, 3), ring('face', 10, 0)
    rim = ring('collar', 8, 1)
    base = [m.vertices[vi] for vi in m.neck_rings['base']]
    chin = min(p[2] for p in jaw)
    top = max(m.vertices[vi][2] for vi in m.parts['hair'])
    head_h = top - chin
    corner = max(jaw, key=lambda p: p[0])
    rim_side = max(rim, key=lambda p: p[0])
    w = lambda pts: 2. * max(p[0] for p in pts)
    head_w = 2. * max(m.vertices[vi][0] for vi in m.parts['hair'])
    r = lambda v: round(v, 4)
    out = {'head_h': r(head_h / H), 'head_w_hair_cap': r(head_w / H), 'chin_z': r(chin / H), 'hair_cap_top_z': r(top / H),
           'neck_front': r((chin - min(p[2] for p in rim)) / H), 'neck_side': r((corner[2] - rim_side[2]) / H),
           'neck_column': r((sum(p[2] for p in under) / 10. - sum(p[2] for p in base) / 10.) / H),
           'jaw_w': r(w(jaw) / H), 'cheek_w': r(w(cheek) / H), 'brow_w': r(w(brow) / H), 'under_jaw_w': r(w(under) / H)}
    for k in ('neck_front', 'neck_side', 'neck_column'):
        out[k + '_per_head_h'] = r(out[k] / out['head_h'])
    for k in ('jaw_w', 'cheek_w'):
        out[k + '_per_head_h'] = r(out[k] / out['head_h'])
        out[k + '_per_head_w'] = r(out[k] / out['head_w_hair_cap'])
    return out


def chest_measure(m):
    """Chest front of a visor-body mesh (rest pose), x H unless named otherwise. Front = -y; torso rings are hem,
    waist, chest, top with vertex 4 on the centre line at the front and 3 / 5 beside it.
    sternum line = the straight line, in the side view, from the front of the top ring (where the collar sits) to the
    front of the waist ring. projection = how far the front-most chest vertex stands in front of that line at its own
    height. profile_bend_deg = the angle between the two straight runs of the front profile at the chest ring (0 = one
    straight line from waist to top). plan_tip_bend_deg = the same for the plan view at the centre vertex.
    quarter_view_projection = the same projection for the outline seen 45 degrees off the front (far-side outline of
    the torso rings, sleeves not counted)."""
    H = m.params['height']
    R = [[m.vertices[vi] for vi in _ring_ids(m, 'torso', 8, k)] for k in range(4)]
    waist, chest, top = R[1], R[CHEST_RING], R[3]

    def line_at(p0, p1, z):         # p = (forward, z)
        return p0[0] + (p1[0] - p0[0]) * (z - p0[1]) / (p1[1] - p0[1])

    def proj(fwd):
        f = [(max(fwd(p) for p in ring), ring[0][2]) for ring in (waist, chest, top)]
        return f[1][0] - line_at(f[0], f[2], f[1][1]), f
    p_side, f = proj(lambda p: -p[1])
    up = math.degrees(math.atan2(f[1][0] - f[2][0], f[2][1] - f[1][1]))
    down = math.degrees(math.atan2(f[1][0] - f[0][0], f[1][1] - f[0][1]))
    s = math.sqrt(.5)
    p_q, _ = proj(lambda p: (-p[1] - p[0]) * s)
    tip, beside = chest[4], chest[5]
    plan = 2. * math.degrees(math.atan2(beside[1] - tip[1], beside[0] - tip[0]))
    shoulder = 2. * max(m.vertices[vi][0] for part, ids in m.parts.items() if part.startswith('sleeve_') for vi in ids)
    chest_w = max(p[0] for p in chest) - min(p[0] for p in chest)
    r = lambda v: round(v, 4)
    return {'chest_front_y': r(-f[1][0] / H), 'top_front_y': r(-f[2][0] / H), 'waist_front_y': r(-f[0][0] / H),
            'chest_z': r(f[1][1] / H), 'projection': r(p_side / H), 'projection_cm': round(p_side * 100., 2),
            'projection_per_shoulder_w': r(p_side / shoulder), 'projection_per_chest_ring_w': r(p_side / chest_w),
            'shoulder_w': r(shoulder / H), 'chest_ring_w': r(chest_w / H),
            'chest_depth': r((max(p[1] for p in chest) - min(p[1] for p in chest)) / H),
            'chest_back_y': r(max(p[1] for p in chest) / H), 'waist_w': r((max(p[0] for p in waist) - min(p[0] for p in waist)) / H),
            'profile_bend_deg': round(up + down, 1), 'profile_upper_run_deg': round(up, 1), 'profile_lower_run_deg': round(down, 1),
            'plan_tip_bend_deg': round(plan, 1), 'quarter_view_projection': r(p_q / H)}


GATE = {'leg_outer_minus_hem': (None, 0.), 'leg_centre_line_dev': (0., .003), 'leg_fore_aft_spread': (0., .008),
        'hip_minus_torso_fore_aft': (-.003, .003), 'torso_fore_aft_spread': (0., .008), 'boot_minus_ankle_x': (-.003, .003),
        'thigh_bone_minus_hip_ring_x': (-.004, .004), 'left_right_asymmetry': (0., SYMMETRY_LIMIT)}


def gate(m):
    a = alignment(m)
    bad = {k: v for k, v in a.items() if (GATE[k][0] is not None and v < GATE[k][0]) or v > GATE[k][1]}
    return a, bad
