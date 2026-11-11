"""cast_v1: the character family on the approved hero body (lane CAST1), built as a DELTA on tall_v3 revision 3.

tall_v3 is a delta on the round-21 builder; cast_v1 is a delta on tall_v3. `person(cameo, tall_v3, spec)` builds the
hero mesh at 1.80 m (same rings, same 16 bones of human16_v1, same alignment fixes), then
  1. STYLE  swaps head and costume pieces: hair (spikes | crop | swept | tufts | curls | hood), visor (wedge | band |
            glasses | none), coat skirt, shoulder guards, chest plate. Removed pieces free triangles (spikes and
            leaves 92, visor 36); every added piece is mirror-symmetric (left half authored, right half mirrored).
  2. SHAPE  moves vertices and bones together with one smooth map per body group (legs, torso, collar, head, arms):
            leg / torso / arm length, head scale, shoulder / chest / waist / hip width, depth, stance width, limb
            thickness, then one uniform scale to the asked height. Every map is linear along a leg and
            mirror-symmetric, so the plumb-leg and left-right gates of tall_v3 hold by construction and are measured
            again on the result (gate()).
With the default spec nothing is changed: the result is the hero mesh, vertex for vertex.

A spec is data: {'params': cameo / face / colour keys, 'shape': SHAPE dials, 'style': STYLE dials}. Nothing here
names a character; the presets live in adventure_maker/nbchars/cast.py.
"""
import math
import struct

from . import people as PP

PRESET = 'cast_v1'
TOPOLOGY = 'human16_cast_v1'
H0 = 1.80
TAU = 2. * math.pi

SHAPE = dict(height=1.80, leg=1., torso=1., arm=1., head=1., neck_w=1., shoulder_w=1., chest_w=1., waist_w=1.,
             hip_w=1., depth=1., belly=0., stance_w=1., leg_w=1., boot=1., arm_w=1.)
SHAPE_RANGES = dict(height=(1.0, 2.1), leg=(.75, 1.15), torso=(.85, 1.15), arm=(.8, 1.15), head=(.9, 1.4),
                    neck_w=(.85, 1.3), shoulder_w=(.85, 1.35), chest_w=(.85, 1.35), waist_w=(.85, 1.4),
                    hip_w=(.85, 1.4), depth=(.85, 1.3), belly=(0., .3), stance_w=(.5, 1.3), leg_w=(.8, 1.3),
                    boot=(.8, 1.3), arm_w=(.8, 1.35))
STYLE = dict(hair='spikes', visor='wedge', coat=0., coat_flare=1.04, guards=False, plate=False)
# Bind dials: what the rig kit's bind gates (hermes64_character bind) need of a cast body. Their defaults build the
# earlier meshes bit for bit, and a dial at its default is not recorded in the mesh's cast record (so earlier files
# keep their bytes).
#   coat_top     'hem': the skirt's top ring is the jacket's hem ring (shared vertices: the jacket is no longer a
#                closed volume, so the rig kit cannot see the collar, sleeves and legs seated inside it).
#                'tucked': the skirt has its own top ring, a copy of the hem ring COAT_TUCK x H above it (a few
#                micrometres: distinct float32 positions, so the rig kit sees two pieces and a closed jacket), with
#                the hem ring's weights (the band's per-corner UVs are unchanged); the rings are twins (m.cast_twins) so the
#                builder can shade them as one vertex. Every other skirt vertex is where it was.
#   coat_seam    0: the skirt's hip ring (COAT['drop'] under the hem) is weighted to the pelvis (+ its thigh share)
#                as authored. c in (0, 1]: its non-thigh share takes c of the jacket hem's own weights (pelvis /
#                spine mix), so the short first band does not stretch past the rig kit's edge limit when the spine
#                turns against the pelvis (run).
#   guard_clear  0: shoulder guards as authored. > 0 (x H): each guard pair is moved up or down (rigid, both sides
#                alike) by the smallest step that keeps every other body part except the jacket this far from it,
#                while the guard stays seated inside the jacket. A stray contact at rest (another part grazing the
#                guard) is a seam the rig kit then holds in every clip, and the arm-weighted guard leaves it.
BIND_STYLE = dict(coat_top='hem', coat_seam=0., guard_clear=0.)
STYLE.update(BIND_STYLE)
HAIR = ('spikes', 'crop', 'swept', 'tufts', 'curls', 'hood')
VISOR = ('wedge', 'band', 'glasses', 'none')
COAT_RANGE = (.12, .40)             # z of the coat's lower edge, x H (0 = no coat)
COAT_TOP = ('hem', 'tucked')
GUARD_CLEAR_RANGE = (0., .01)
COAT_TUCK = .000005                 # x H: tucked top ring above the hem ring (8.8 um at 1.76 m; float32 step there 0.06 um)
GUARD_STEP = .0005                  # x H: guard_clear search step (up to GUARD_STEPS steps up or down)
GUARD_STEPS = 24

# landmarks of the hero mesh, x H0, grounded (z = 0 at the sole)
Z_ANKLE, Z_HIP, Z_TOP = .094, .474, .772
TORSO_Z = (.466, .559, .679, .772)              # hem, waist, chest, top ring
TORSO_CY = (.002, .000, .007, .006)
COLLAR_CY = .014
NECK_PIVOT = (0., .018, .766)                   # centre of the neck base ring (stays in the collar)

# extra atlas regions. Costume atlas: the bottom quarter is unused by the round-21 painter.
CR = {'coat': (0., 0., .5, .25), 'plate': (.5, 0., .75, .25), 'guard': (.75, 0., 1., .25)}
# Headwear atlas: the round-21 regions (cameo.HW) are reused by position.
HWR = {'hood': (.5, .5, 1., 1.), 'lining': (0., .25, .5, .5), 'lock': (.5, .5, .75, 1.), 'lens': (0., 0., 1., .25),
       'frame': (.5, .25, 1., .5)}

GROUPS = {'torso': ('torso', 'collar', 'coat', 'plate'), 'arms': ('sleeve_', 'mitt_', 'thumb_', 'acc_guard_'),
          'legs': ('trouser_', 'boot_'), 'head': ('face', 'nose', 'visor', 'hood', 'acc_glasses'),
          'hair': ('hair', 'spike_', 'leaf_')}
SYMMETRY_LIMIT = .0005              # x H, as tall_v3
GATE = {'cast_asymmetry': (0., SYMMETRY_LIMIT), 'leg_gap_half': (0., None)}


class SpecError(ValueError):
    pass


def resolve(spec):
    """(params overrides, shape, style) with defaults filled and ranges checked."""
    spec = spec or {}
    unknown = set(spec) - {'params', 'shape', 'style'}
    if unknown:
        raise SpecError('unknown spec keys %s' % sorted(unknown))
    shape = dict(SHAPE); style = dict(STYLE)
    for name, dst in (('shape', shape), ('style', style)):
        for k, v in (spec.get(name) or {}).items():
            if k not in dst:
                raise SpecError('unknown %s dial %r' % (name, k))
            dst[k] = v
    for k, (lo, hi) in SHAPE_RANGES.items():
        v = shape[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise SpecError('shape %s = %r outside %s..%s' % (k, v, lo, hi))
    if style['hair'] not in HAIR or style['visor'] not in VISOR:
        raise SpecError('hair is one of %s, visor one of %s' % (HAIR, VISOR))
    c = style['coat']
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not (c == 0. or COAT_RANGE[0] <= c <= COAT_RANGE[1]):
        raise SpecError('coat = 0 or %s..%s' % COAT_RANGE)
    for k in ('guards', 'plate'):
        if type(style[k]) is not bool:
            raise SpecError(k + ' must be boolean')
    if style['coat_top'] not in COAT_TOP:
        raise SpecError('coat_top is one of %s' % (COAT_TOP,))
    c = style['coat_seam']
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or not 0. <= c <= 1.:
        raise SpecError('coat_seam = %r outside 0..1' % (c,))
    g = style['guard_clear']
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not math.isfinite(g) or not \
            GUARD_CLEAR_RANGE[0] <= g <= GUARD_CLEAR_RANGE[1]:
        raise SpecError('guard_clear = %r outside %s..%s' % ((g,) + GUARD_CLEAR_RANGE))
    return dict(spec.get('params') or {}), shape, style


# ---------------------------------------------------------------------------------------------- mesh editing
def _strip(m, prefixes):
    """Remove whole parts (vertices and their triangles) and re-index everything that holds vertex ids."""
    drop = {vi for part, ids in m.parts.items() if part.startswith(prefixes) for vi in ids}
    if not drop:
        return
    keep = [i for i, f in enumerate(m.faces) if not (f[0] in drop or f[1] in drop or f[2] in drop)]
    remap = {}
    V = []; W = []
    for i in range(len(m.vertices)):
        if i not in drop:
            remap[i] = len(V); V.append(m.vertices[i]); W.append(m.weights[i])
    faces = [tuple(remap[j] for j in m.faces[i]) for i in keep]
    for attr in ('uv', 'roles', 'tiles'):
        setattr(m, attr, [getattr(m, attr)[i] for i in keep])
    m.faces = faces; m.vertices = V; m.weights = W
    m.parts = {part: [remap[i] for i in ids] for part, ids in m.parts.items() if not part.startswith(prefixes)}
    m.ao = {remap[i]: v for i, v in getattr(m, 'ao', {}).items() if i in remap}
    m.neck_rings = {k: [remap[i] for i in ids] for k, ids in getattr(m, 'neck_rings', {}).items()}


def _verts(m, part, pts, weights):
    start = len(m.vertices)
    for k, pt in enumerate(pts):
        m.vertices.append((float(pt[0]), float(pt[1]), float(pt[2])))
        m.weights.append(dict(weights[k] if isinstance(weights, (list, tuple)) else weights))
    ids = list(range(start, len(m.vertices)))
    m.parts[part] = list(m.parts.get(part, [])) + ids
    return ids


def _tri(m, ids, uvs, role, away, inward=False):
    """One triangle (global vertex ids), wound to face away from the point `away` (or toward it: inward)."""
    a, b, c = (m.vertices[i] for i in ids)
    n = PP._cross(PP._sub(b, a), PP._sub(c, a))
    fc = PP._mul(PP._add(PP._add(a, b), c), 1. / 3)
    out = PP._dot(n, PP._sub(fc, away)) >= 0
    if out == inward:
        ids = (ids[0], ids[2], ids[1]); uvs = [uvs[0], uvs[2], uvs[1]]
    m.faces.append(tuple(ids)); m.uv.append([tuple(uvs[0]), tuple(uvs[1]), tuple(uvs[2])]); m.roles.append(role); m.tiles.append(0)


def _reg(region, u, v):
    u0, v0, u1, v1 = region
    return (u0 + (u1 - u0) * (.04 + .92 * u), v0 + (v1 - v0) * (.04 + .92 * v))


def _mirror(pts):
    return [(-p[0], p[1], p[2]) for p in pts]


def _ring8(rx, ry, cy, z, front=None):
    """8 points, j = 0 back (+y), 2 the wearer's right (-x), 4 front (-y), 6 left; exactly mirror-symmetric."""
    s = math.sqrt(.5)
    half = [(0., cy + ry, z), (-rx * s, cy + ry * s, z), (-rx, cy, z), (-rx * s, cy - ry * s, z),
            front if front is not None else (0., cy - ry, z)]
    return half + [(-half[j][0], half[j][1], half[j][2]) for j in (3, 2, 1)]


def _bands(m, lower, upper, uv, role, away, inward=False):
    """Triangles between two 8-column rings given as {j: vertex id} (a column may be missing: an opening)."""
    for j in range(8):
        j1 = (j + 1) % 8
        L = [lower.get(j), lower.get(j1)]; U = [upper.get(j), upper.get(j1)]
        ua, ub, uc, ud = uv(j, 0), uv(j + 1, 0), uv(j + 1, 1), uv(j, 1)
        if None not in L and None not in U:
            _tri(m, (L[0], L[1], U[1]), [ua, ub, uc], role, away, inward)
            _tri(m, (L[0], U[1], U[0]), [ua, uc, ud], role, away, inward)
        elif None not in L and U.count(None) == 1:
            k = 0 if U[0] is not None else 1
            _tri(m, (L[0], L[1], U[k]), [ua, ub, ud if k == 0 else uc], role, away, inward)
        elif None not in U and L.count(None) == 1:
            k = 0 if L[0] is not None else 1
            _tri(m, (L[k], U[1], U[0]), [ua if k == 0 else ub, uc, ud], role, away, inward)


# ---------------------------------------------------------------------------------------------- style pieces
def _head_local(T3):
    hh = .158 * H0
    z0 = H0 - hh - (T3.FLOOR + T3.NECK_DROP) * H0
    return lambda x, y, z: (x * hh, y * hh, z0 + z * hh)


# blades: (base a, base b, base c, tip) in head-local units; a centre blade has a/b mirrored and c, tip on x = 0;
# the others are authored on the left (+x) and mirrored
BLADES = {
    'crop': {'centre': [], 'side': []},
    'swept': {'centre': [((-.16, -.44, .86), (.16, -.44, .86), (0., -.20, .98), (0., -.52, 1.13)),
                         ((-.15, -.05, 1.02), (.15, -.05, 1.02), (0., .25, .95), (0., .44, 1.13))],
              'side': [((.30, -.36, .80), (.34, -.02, .80), (.20, -.20, .95), (.45, .24, .93)),
                       ((.30, .05, .70), (.30, .38, .62), (.20, .20, .85), (.41, .57, .56)),
                       ((.05, .46, .60), (.28, .40, .55), (.15, .35, .75), (.16, .63, .36))]},
    'tufts': {'centre': [((-.14, -.42, .90), (.14, -.42, .90), (0., -.20, 1.00), (0., -.53, 1.12)),
                         ((-.12, -.10, 1.04), (.12, -.10, 1.04), (0., .12, 1.04), (0., 0., 1.30))],
              'side': [((.20, -.30, .92), (.33, -.10, .86), (.15, -.10, 1.00), (.42, -.26, 1.12)),
                       ((.30, .00, .80), (.30, .30, .74), (.16, .15, .95), (.50, .20, .92)),
                       ((.08, .42, .74), (.30, .34, .68), (.15, .25, .90), (.22, .60, .80))]},
}
SPIKE_FACES = [(0, 1, 3), (1, 2, 3), (2, 0, 3), (0, 2, 1)]
# curls: direction from the skull centre (x, y, z), size; centre curls have x = 0
CURL_O = (0., .025, .60)
CURL_R = (.37, .50, .50)
CURLS = {'centre': [((0., -.75, .66), .17), ((0., 0., 1.), .18), ((0., .70, .72), .18), ((0., 1., .10), .17)],
         'side': [((.55, -.55, .62), .16), ((.70, 0., .72), .17), ((.95, -.05, .12), .15), ((.62, .65, .44), .17)]}


def _convex(m, part, pts, faces, uv, role='headwear'):
    ids = _verts(m, part, pts, {'head': 1.})
    cen = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
    for f in faces:
        _tri(m, tuple(ids[i] for i in f), [uv(i) for i in f], role, cen)


def _add_blades(m, hl, style):
    tab = BLADES[style]
    uvs = {0: _reg(HWR['lock'], .08, .1), 1: _reg(HWR['lock'], .42, .1), 2: _reg(HWR['lock'], .25, .1), 3: _reg(HWR['lock'], .25, .9)}
    n = 0
    for b in tab['centre']:
        _convex(m, 'hair_lock_%d' % n, [hl(*p) for p in b], SPIKE_FACES, uvs.get); n += 1
    for b in tab['side']:
        pts = [hl(*p) for p in b]
        _convex(m, 'hair_lock_%d' % n, pts, SPIKE_FACES, uvs.get); n += 1
        _convex(m, 'hair_lock_%d' % n, _mirror(pts), SPIKE_FACES, uvs.get); n += 1


def _add_curls(m, hl):
    faces = [(0, 2, 3), (0, 3, 4), (0, 4, 2), (1, 3, 2), (1, 4, 3), (1, 2, 4)]
    uvs = {0: _reg(HWR['lock'], .25, .62), 1: _reg(HWR['lock'], .25, .05), 2: _reg(HWR['lock'], .05, .30),
           3: _reg(HWR['lock'], .25, .30), 4: _reg(HWR['lock'], .45, .30)}
    n = 0

    def curl(d, r):
        d = PP._norm(d)
        c = tuple(CURL_O[k] + d[k] * CURL_R[k] for k in range(3))
        e1 = (1., 0., 0.) if abs(d[0]) < 1e-12 else PP._norm(PP._cross(d, (0., 0., 1.)))
        e2 = PP._norm(PP._cross(d, e1))
        ring = [PP._add(c, PP._mul(e2, r)), PP._add(c, PP._add(PP._mul(e2, -.5 * r), PP._mul(e1, .866 * r))),
                PP._add(c, PP._add(PP._mul(e2, -.5 * r), PP._mul(e1, -.866 * r)))]
        return [hl(*p) for p in [PP._add(c, PP._mul(d, .95 * r)), PP._add(c, PP._mul(d, -.55 * r))] + ring]
    for d, r in CURLS['centre']:
        _convex(m, 'hair_curl_%d' % n, curl(d, r), faces, uvs.get); n += 1
    for d, r in CURLS['side']:
        pts = curl(d, r)
        _convex(m, 'hair_curl_%d' % n, pts, faces, uvs.get); n += 1
        _convex(m, 'hair_curl_%d' % n, _mirror(pts), faces, uvs.get); n += 1


HOOD = {'r0': (.58, .54, .08, -.40), 'r1': (.52, .50, .06, .10), 'r2': (.53, .56, .08, .55), 'r3': (.47, .58, .10, .92),
        'peak': (0., -.60, .93), 'apex': (0., .22, 1.30), 'lining_in': .90, 'v': (0., .30, .60, .85, 1.)}
HOOD_AO = {'lining': .62, 'face': .90}


def _add_hood(m, hl):
    """Hood shell around the head: closed ring on the shoulders, face opening from the chin ring to the brow peak,
    pointed crown; lining (inward faces) from the chin ring up, sharing the opening rim with the outer shell."""
    h = HOOD
    rings = [_ring8(*h['r0']), _ring8(*h['r1']), _ring8(*h['r2']), _ring8(*h['r3'], front=h['peak'])]
    wts = [{'spine': 1.}, {'head': .5, 'spine': .5}, {'head': 1.}, {'head': 1.}]
    outer = []
    for k, (pts, w) in enumerate(zip(rings, wts)):
        cols = [j for j in range(8) if not (k in (1, 2) and j == 4)]
        ids = _verts(m, 'hood', [hl(*pts[j]) for j in cols], w)
        outer.append(dict(zip(cols, ids)))
    apex = _verts(m, 'hood', [hl(*h['apex'])], {'head': 1.})[0]
    m.cast_anchor = set(getattr(m, 'cast_anchor', ())) | set(outer[0].values())
    axis = hl(0., .08, .45)

    def uv(region, k):
        return lambda j, top: _reg(region, j / 8., h['v'][k + (1 if top else 0)])
    for k in range(3):
        _bands(m, outer[k], outer[k + 1], uv(HWR['hood'], k), 'headwear', axis)
    for j in range(8):
        _tri(m, (outer[3][j], outer[3][(j + 1) % 8], apex),
             [_reg(HWR['hood'], j / 8., h['v'][3]), _reg(HWR['hood'], (j + 1) / 8., h['v'][3]), _reg(HWR['hood'], (j + .5) / 8., 1.)],
             'headwear', axis)
    s = h['lining_in']
    inner = [None]
    for k in (1, 2, 3):
        rim = (3, 5) if k < 3 else (3, 4, 5)
        cols = [j for j in outer[k] if j not in rim]
        pts = [(rings[k][j][0] * s, h['r%d' % k][2] + (rings[k][j][1] - h['r%d' % k][2]) * s, rings[k][j][2]) for j in cols]
        ids = _verts(m, 'hood', [hl(*p) for p in pts], wts[k])
        d = dict(zip(cols, ids))
        d.update({j: outer[k][j] for j in rim})
        inner.append(d)
        for vi in ids:
            m.ao[vi] = HOOD_AO['lining']
    ax, ay, az = h['apex']
    iapex = _verts(m, 'hood', [hl(ax, ay, az - .07)], {'head': 1.})[0]
    m.ao[iapex] = HOOD_AO['lining']
    for k in (1, 2):
        _bands(m, inner[k], inner[k + 1], uv(HWR['lining'], k), 'headwear', axis, inward=True)
    for j in range(8):
        _tri(m, (inner[3][j], inner[3][(j + 1) % 8], iapex),
             [_reg(HWR['lining'], j / 8., h['v'][3]), _reg(HWR['lining'], (j + 1) / 8., h['v'][3]), _reg(HWR['lining'], (j + .5) / 8., 1.)],
             'headwear', axis, inward=True)
    for part in ('face', 'nose', 'hair'):
        for vi in m.parts[part]:
            if vi not in m.ao:
                m.ao[vi] = HOOD_AO['face']


GLASSES = {'lens': (.150, -.470, .448), 'r': (.115, .100), 'wrap': .045, 'bridge': (.040, .455, .490, -.478),
           'temple': (.37, -.05, .47, .018)}


def _add_glasses(m, hl):
    g = GLASSES
    cx, cy, cz = g['lens']; rx, rz = g['r']
    ring = []
    for k in range(8):
        a = TAU * (k + .5) / 8.
        x = cx + rx * math.cos(a)
        ring.append((x, cy + g['wrap'] * max(0., (x - cx) / rx), cz + rz * math.sin(a)))
    left = [(cx, cy - .012, cz)] + ring
    away = hl(0., .1, .45)
    for side, pts, uc in (('l', left, .25), ('r', _mirror(left), .75)):
        ids = _verts(m, 'acc_glasses', [hl(*p) for p in pts], {'head': 1.})
        uvs = [(uc, .5)] + [(uc + .21 * math.cos(TAU * (k + .5) / 8.) * (1 if side == 'l' else -1), .5 + .42 * math.sin(TAU * (k + .5) / 8.)) for k in range(8)]
        for k in range(8):
            f = (0, 1 + k, 1 + (k + 1) % 8)
            _tri(m, tuple(ids[i] for i in f), [_reg(HWR['lens'], *uvs[i]) for i in f], 'headwear', away)
    bx, z0, z1, by = g['bridge']
    q = [(-bx, by, z0), (bx, by, z0), (bx, by, z1), (-bx, by, z1)]
    fuv = [_reg(HWR['frame'], .1, .1), _reg(HWR['frame'], .9, .1), _reg(HWR['frame'], .9, .9), _reg(HWR['frame'], .1, .9)]
    ids = _verts(m, 'acc_glasses', [hl(*p) for p in q], {'head': 1.})
    for f in ((0, 1, 2), (0, 2, 3)):
        _tri(m, tuple(ids[i] for i in f), [fuv[i] for i in f], 'headwear', away)
    tx, ty, tz, th = g['temple']
    x0 = cx + rx * math.cos(TAU * .5 / 8.); y0 = cy + g['wrap'] * math.cos(TAU * .5 / 8.)
    tl = [(x0, y0, cz - th), (tx, ty, tz - th), (tx, ty, tz + th), (x0, y0, cz + th)]
    for pts in (tl, _mirror(tl)):
        ids = _verts(m, 'acc_glasses', [hl(*p) for p in pts], {'head': 1.})
        for f in ((0, 1, 2), (0, 2, 3)):
            _tri(m, tuple(ids[i] for i in f), [fuv[i] for i in f], 'headwear', away)


BAND_VISOR = .50        # visor height factor of the 'band' style (each of the 5 rings about its own centre)


def _band_visor(m):
    ids = m.parts['visor']
    for k in range(len(ids) // 4):
        ring = ids[k * 4:(k + 1) * 4]
        zc = sum(m.vertices[vi][2] for vi in ring) / 4.
        for vi in ring:
            x, y, z = m.vertices[vi]
            m.vertices[vi] = (x, y, zc + (z - zc) * BAND_VISOR)


COAT_W = [{'pelvis': .4, 'thigh_l': .3, 'thigh_r': .3}, {'thigh_r': .7, 'pelvis': .3}, {'thigh_r': .8, 'pelvis': .2},
          {'thigh_r': .8, 'pelvis': .2}, {'pelvis': .4, 'thigh_l': .3, 'thigh_r': .3}, {'thigh_l': .8, 'pelvis': .2},
          {'thigh_l': .8, 'pelvis': .2}, {'thigh_l': .7, 'pelvis': .3}]


COAT = {'drop': .010, 'kx': .86, 'ky': .80, 'clear': .006}


def _ring8k(rx, ry, cy, z, kx, ky):
    """_ring8 with the diagonal corners at (kx rx, ky ry): a squarer ring, to wrap two legs."""
    half = [(0., cy + ry, z), (-rx * kx, cy + ry * ky, z), (-rx, cy, z), (-rx * kx, cy - ry * ky, z), (0., cy - ry, z)]
    return half + [(-half[j][0], half[j][1], half[j][2]) for j in (3, 2, 1)]


def _seam_weights(hip_w, hem_w, c):
    """coat_seam: the hip-ring weights with their non-thigh share moved c of the way to the hem's weights."""
    t = sum(v for k, v in hip_w.items() if k.startswith('thigh'))
    target = {k: v * (1. - t) for k, v in hem_w.items()}
    for k, v in hip_w.items():
        if k.startswith('thigh'):
            target[k] = target.get(k, 0.) + v
    keys = sorted(set(hip_w) | set(target))
    return {k: (1. - c) * hip_w.get(k, 0.) + c * target.get(k, 0.) for k in keys if (1. - c) * hip_w.get(k, 0.) + c * target.get(k, 0.) > 0.}


def _add_coat(m, T3, z_edge, flare, top='hem', seam=0.):
    """Coat skirt: the jacket hem ring (shared vertices), a hip ring `drop` under it and the lower ring at
    z_edge x H0: 2 bands of 8 quads. `_fit_coat` sets the width of the two new rings after the shape stage.
    top='tucked': the first band ends on a ring of its own (part 'coat', ids 16..23) instead of the hem ring; it is
    placed by `_tuck_coat` after the fit, and carries the hem ring's weights (the band's per-corner UVs are as before)."""
    hem = T3._ring_ids(m, 'torso', 8, 0)
    B = m.params['build']
    rx, ry, cy = T3.TORSO[0][2] * B * H0, T3.TORSO[0][3] * H0, T3.TORSO[0][1] * H0
    z_hem = T3.TORSO[0][0]
    z_hip = z_hem - COAT['drop']
    hip_w = [{'pelvis': 1.}] + [{'pelvis': .75, 'thigh_r': .25}] * 3 + [{'pelvis': 1.}] + [{'pelvis': .75, 'thigh_l': .25}] * 3
    if seam:
        hip_w = [_seam_weights(w, m.weights[hem[j]], seam) for j, w in enumerate(hip_w)]
    hip = _verts(m, 'coat', _ring8k(rx, ry, cy, z_hip * H0, COAT['kx'], COAT['ky']), hip_w)
    low = _verts(m, 'coat', _ring8k(rx * flare, ry * flare, cy, z_edge * H0, COAT['kx'], COAT['ky']), COAT_W)
    v_hip = 1. - COAT['drop'] / (z_hem - z_edge)
    if top == 'tucked':
        hem = _verts(m, 'coat', [m.vertices[vi] for vi in hem], [m.weights[vi] for vi in hem])
    away = (0., TORSO_CY[0] * H0, .5 * (z_edge + TORSO_Z[0]) * H0)
    _bands(m, dict(enumerate(hip)), dict(enumerate(hem)), lambda j, top: _reg(CR['coat'], j / 8., 1. if top else v_hip),
           'costume', away)
    _bands(m, dict(enumerate(low)), dict(enumerate(hip)), lambda j, top: _reg(CR['coat'], j / 8., v_hip if top else 0.),
           'costume', away)
    # the bands are wound against a point on the axis at mid height: every quad faces away from the legs


def _tuck_coat(m, T3):
    """Place the tucked top ring: each hem-ring vertex copied COAT_TUCK x H higher. The skirt keeps its shape (the
    first band's top edge moves by micrometres), the jacket keeps its closed volume, and the two rings touch, so
    the rig kit holds them as a seam in every clip (same weights: they move together). Records m.cast_twins."""
    ids = m.parts['coat']
    hem = T3._ring_ids(m, 'torso', 8, 0)
    up = COAT_TUCK * m.params['height']
    twins = {}
    for j in range(8):
        x, y, z = m.vertices[hem[j]]
        m.vertices[ids[16 + j]] = (x, y, z + up)
        if struct.pack('<f', z + up) == struct.pack('<f', z):
            raise SpecError('tucked coat: the top ring is not apart from the hem ring in float32')
        twins[ids[16 + j]] = hem[j]
    m.cast_twins = twins


def _fit_coat(m):
    """Widen the coat's hip and lower rings about their own centre, both by one factor, until every trouser
    vertex between them is `clear` x H inside the skirt (the legs change with the shape dials). Returns the factor."""
    ids = m.parts['coat']
    H = m.params['height']
    cy = .5 * (m.vertices[ids[0]][1] + m.vertices[ids[4]][1])
    z_hi, z_lo = m.vertices[ids[0]][2], m.vertices[ids[8]][2]
    legs = [m.vertices[vi] for part in ('trouser_l', 'trouser_r') for vi in m.parts[part]]
    zs = sorted({round(p[2], 9) for p in legs})
    b_lo = max([z for z in zs if z <= z_lo] or zs[:1]); b_hi = min([z for z in zs if z >= z_hi] or zs[-1:])
    # the leg rings between the two coat rings and the nearest ring outside each (a short skirt has none between)
    legs = [(abs(p[0]), abs(p[1] - cy), min(z_hi, max(z_lo, p[2]))) for p in legs if b_lo - 1e-9 <= p[2] <= b_hi + 1e-9]

    def inside(k):
        for px, py, pz in legs:
            t = (z_hi - pz) / (z_hi - z_lo)
            ring = [tuple(m.vertices[ids[j]][c] + (m.vertices[ids[8 + j]][c] - m.vertices[ids[j]][c]) * t for c in (0, 1))
                    for j in (6, 7, 0)]                                    # left, back-left, back: one quadrant
            q = [(abs(x) * k, abs(y - cy) * k) for x, y in ring]
            for (ax, ay), (bx, by) in ((q[0], q[1]), (q[1], q[2])):
                ex, ey = bx - ax, by - ay
                if ((px - ax) * ey - (py - ay) * ex) / math.hypot(ex, ey) > -COAT['clear'] * H:
                    return False
        return True

    k = 1.
    while not inside(k):
        k += .01
        if k > 1.6:
            raise SpecError('the coat cannot wrap the legs')
    for vi in ids:
        x, y, z = m.vertices[vi]
        m.vertices[vi] = (x * k, cy + (y - cy) * k, z)
    return k


# Shoulder guard: a 13-vertex dome seated on the sleeve's top ring (hero: ring centre (.112, .006, .738) x H, top
# z .749, outer x .154). apex / r1 / r2 = (cx, cy, cz, rx, ry, tilt); the inner edge of r2 lies inside the jacket
# under the collar, the outer edge stands .024 H outside the sleeve, the front and back edges .010 H.
GUARD = {'apex': (.116, .006, .768), 'r1': (.118, .006, .762, .032, .036, .006), 'r2': (.124, .006, .738, .066, .072, .022)}


def _add_guards(m):
    B = m.params['build']
    g = GUARD

    def ring(cx, cy, cz, rx, ry, tilt):
        return [((cx * B + rx * math.cos(TAU * k / 6.)) * H0, (cy + ry * math.sin(TAU * k / 6.)) * H0,
                 (cz - tilt * math.cos(TAU * k / 6.)) * H0) for k in range(6)]
    left = [(g['apex'][0] * B * H0, g['apex'][1] * H0, g['apex'][2] * H0)] + ring(*g['r1']) + ring(*g['r2'])
    uvs = [(.5, .5)] + [(.5 + .24 * math.cos(TAU * k / 6.), .5 + .24 * math.sin(TAU * k / 6.)) for k in range(6)] + \
          [(.5 + .47 * math.cos(TAU * k / 6.), .5 + .47 * math.sin(TAU * k / 6.)) for k in range(6)]
    for side, pts in (('l', left), ('r', _mirror(left))):
        ids = _verts(m, 'acc_guard_' + side, pts, {'spine': .65, 'upper_arm_' + side: .35})
        away = (pts[0][0], pts[0][1], pts[0][2] - .10 * H0)
        faces = []
        for k in range(6):
            k1 = (k + 1) % 6
            faces += [(0, 1 + k, 1 + k1), (1 + k, 7 + k, 7 + k1), (1 + k, 7 + k1, 1 + k1)]
        for f in faces:
            _tri(m, tuple(ids[i] for i in f), [_reg(CR['guard'], *uvs[i]) for i in f], 'costume', away)


PLATE = {'z': .668, 'rx': .078, 'rz': .088, 'embed': .006, 'raise': .014, 'hub': .020, 'inset': .80}


def _front_y(m, x, z):
    """y of the torso's front surface at (x, z): the first hit of a ray along +y on the torso triangles."""
    ids = set(m.parts['torso'])
    best = None
    for f in m.faces:
        if not all(v in ids for v in f):
            continue
        a, b, c = (m.vertices[v] for v in f)
        d = (b[0] - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (b[2] - a[2])
        if abs(d) < 1e-12:
            continue
        u = ((x - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (z - a[2])) / d
        v = ((b[0] - a[0]) * (z - a[2]) - (x - a[0]) * (b[2] - a[2])) / d
        if u < -1e-9 or v < -1e-9 or u + v > 1. + 1e-9:
            continue
        y = a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])
        best = y if best is None or y < best else best
    if best is None:
        raise SpecError('plate: (%.3f, %.3f) is off the torso front' % (x, z))
    return best


def _add_plate(m):
    """Octagonal slab that follows the chest: outer ring `embed` under the jacket surface, a ring `raise` in front of
    it, hub vertex `hub` in front of it on the centre line. Every vertex is placed by a ray on the torso front, so
    the slab bends along the chest's centre ridge and has one thickness everywhere."""
    B = m.params['build']
    p = PLATE
    c, s = math.cos(TAU / 16.), math.sin(TAU / 16.)
    half = [(c, s), (s, c), (s, -c), (c, -s)]                       # the wearer's left half, top to bottom
    unit = half + [(-x, z) for x, z in reversed(half)]              # 8 points, mirror-symmetric

    def at(x, z, off):
        x, z = abs(x) * p['rx'] * B * H0 * (1 if x >= 0 else -1), (p['z'] + z * p['rz']) * H0
        return (x, _front_y(m, abs(x), z) + off * H0, z)            # |x|: the same ray for both halves
    k = p['inset']
    outer = [at(x, z, p['embed']) for x, z in unit]
    raised = [at(x * k, z * k, -p['raise']) for x, z in unit]
    hub = at(0., 0., -p['hub'])
    ids = _verts(m, 'plate', outer + raised + [hub], {'spine': 1.})
    uvs = [(.5 + .46 * x, .5 + .46 * z) for x, z in unit] + [(.5 + .46 * k * x, .5 + .46 * k * z) for x, z in unit] + [(.5, .5)]
    away = (0., hub[1] + .08 * H0, p['z'] * H0)
    faces = []
    for j in range(8):
        j1 = (j + 1) % 8
        faces += [(j, j1, 8 + j1), (j, 8 + j1, 8 + j), (8 + j, 8 + j1, 16)]
    for f in faces:
        _tri(m, tuple(ids[i] for i in f), [_reg(CR['plate'], *uvs[i]) for i in f], 'costume', away)


# ---------------------------------------------------------------------------------------------- contact geometry
# The rig kit's seam rule (adventure_maker/rigkit/seams.py, generic method) joins two body pieces when a vertex of one
# lies within 3 mm of the other's triangles or inside it (closed pieces only). These helpers let the bind dials
# measure the same relations on the generator mesh (rest pose).
_RAY = (0.5773503, 0.5773603, 0.5773403)


def _part_tris(m, part):
    ids = set(m.parts[part])
    return [f for f in m.faces if f[0] in ids and f[1] in ids and f[2] in ids]


def _closed(tris):
    count = {}
    for f in tris:
        for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            e = (min(e), max(e))
            count[e] = count.get(e, 0) + 1
    return bool(count) and all(n == 2 for n in count.values())


def _inside(V, tris, p):
    """Ray parity of point p against a closed triangle set (vertex positions V)."""
    hits = 0
    for f in tris:
        a, b, c = V[f[0]], V[f[1]], V[f[2]]
        e1 = PP._sub(b, a); e2 = PP._sub(c, a)
        h = PP._cross(_RAY, e2)
        det = PP._dot(e1, h)
        if abs(det) < 1e-14:
            continue
        s = PP._sub(p, a)
        u = PP._dot(s, h) / det
        if u < 0. or u > 1.:
            continue
        q = PP._cross(s, e1)
        v = PP._dot(_RAY, q) / det
        if v < 0. or u + v > 1.:
            continue
        if PP._dot(e2, q) / det > 1e-12:
            hits += 1
    return hits % 2 == 1


def _pt_tri_d2(p, a, b, c):
    """Squared distance of point p to triangle abc (closest point by region, Ericson 5.1.5)."""
    ab = PP._sub(b, a); ac = PP._sub(c, a); ap = PP._sub(p, a)
    d1 = PP._dot(ab, ap); d2 = PP._dot(ac, ap)
    if d1 <= 0. and d2 <= 0.:
        q = a
    else:
        bp = PP._sub(p, b); d3 = PP._dot(ab, bp); d4 = PP._dot(ac, bp)
        cp = PP._sub(p, c); d5 = PP._dot(ab, cp); d6 = PP._dot(ac, cp)
        vc = d1 * d4 - d3 * d2; vb = d5 * d2 - d1 * d6; va = d3 * d6 - d5 * d4
        if d3 >= 0. and d4 <= d3:
            q = b
        elif vc <= 0. and d1 >= 0. and d3 <= 0.:
            q = PP._add(a, PP._mul(ab, d1 / (d1 - d3)))
        elif d6 >= 0. and d5 <= d6:
            q = c
        elif vb <= 0. and d2 >= 0. and d6 <= 0.:
            q = PP._add(a, PP._mul(ac, d2 / (d2 - d6)))
        elif va <= 0. and (d4 - d3) >= 0. and (d5 - d6) >= 0.:
            q = PP._add(b, PP._mul(PP._sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6))))
        else:
            den = 1. / (va + vb + vc)
            q = PP._add(a, PP._add(PP._mul(ab, vb * den), PP._mul(ac, vc * den)))
    d = PP._sub(p, q)
    return PP._dot(d, d)


def _bbox(P):
    return [min(p[k] for p in P) for k in range(3)], [max(p[k] for p in P) for k in range(3)]


def _clear_guards(m, clear):
    """guard_clear (STYLE): move both guards by the same dz (rigid, z only) so that no vertex of another body part
    (the jacket excepted) is within `clear` x H of a guard triangle, no guard vertex is within it of another part's
    triangle or inside a closed part, and at least one guard vertex stays inside the jacket. dz = 0, +s, -s, +2s ...
    (s = GUARD_STEP x H); the first that holds is applied. Returns dz (m)."""
    H = m.params['height']
    lim2 = (clear * H) ** 2
    step = GUARD_STEP * H
    gl = m.parts['acc_guard_l']
    G = set(gl)
    gtris = [tuple(gl.index(v) for v in f) for f in m.faces if f[0] in G and f[1] in G and f[2] in G]
    torso = _part_tris(m, 'torso')
    reach = clear * H + GUARD_STEPS * step
    g0 = [m.vertices[vi] for vi in gl]
    lo, hi = _bbox(g0)
    near = []
    for part, ids in sorted(m.parts.items()):
        if part.startswith('acc_guard_') or part == 'torso' or not ids:
            continue
        P = [m.vertices[vi] for vi in ids]
        plo, phi = _bbox(P)
        if any(plo[k] > hi[k] + reach or phi[k] < lo[k] - reach for k in range(3)):
            continue
        tris = _part_tris(m, part)
        near.append((part, P, [tuple(m.vertices[v] for v in f) for f in tris], _closed(tris)))

    def holds(dz):
        g = [(p[0], p[1], p[2] + dz) for p in g0]
        gt = [(g[a], g[b], g[c]) for a, b, c in gtris]
        if not any(_inside(m.vertices, torso, p) for p in g):
            return False
        for part, P, T, closed in near:
            for p in g:
                if any(_pt_tri_d2(p, *t) < lim2 for t in T):
                    return False
            if closed and any(_inside_tris(T, p) for p in g):
                return False
            for p in P:
                if any(_pt_tri_d2(p, *t) < lim2 for t in gt):
                    return False
        return True
    for k in range(GUARD_STEPS + 1):
        for dz in ((0.,) if k == 0 else (k * step, -k * step)):
            if holds(dz):
                for side in ('l', 'r'):
                    for vi in m.parts['acc_guard_' + side]:
                        x, y, z = m.vertices[vi]
                        m.vertices[vi] = (x, y, z + dz)
                return dz
    raise SpecError('guard_clear: no guard placement within %d steps keeps %.4f x H clear' % (GUARD_STEPS, clear))


def _inside_tris(T, p):
    """_inside on triangles given as point triples."""
    V = [q for t in T for q in t]
    return _inside(V, [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(T))], p)


# ---------------------------------------------------------------------------------------------- shape
def _tab(tab, z):
    if z <= tab[0][0]:
        return tab[0][1]
    for (z0, v0), (z1, v1) in zip(tab, tab[1:]):
        if z <= z1:
            return v0 + (v1 - v0) * (z - z0) / (z1 - z0)
    return tab[-1][1]


def _group(part):
    if part.startswith(GROUPS['legs']):
        return 'leg'
    if part.startswith(GROUPS['arms']):
        return 'arm'
    if part == 'collar':
        return 'collar'
    if part.startswith(GROUPS['head']) or part.startswith(GROUPS['hair']):
        return 'head'
    return 'torso'


def _centres(m, part, n):
    """(z, centre x, centre y) of each n-vertex ring of a part; centre = middle of the extent, as tall_v3.alignment."""
    ids = m.parts[part]
    out = []
    for k in range(len(ids) // n):
        P = [m.vertices[vi] for vi in ids[k * n:(k + 1) * n]]
        xs = [p[0] for p in P]; ys = [p[1] for p in P]
        out.append((sum(p[2] for p in P) / n, (min(xs) + max(xs)) / 2., (min(ys) + max(ys)) / 2.))
    return out


def _reshape(m, sh):
    """Move every vertex and bone with the map of its body group (module docstring, SHAPE). Widths and depths scale
    about the measured ring centres of the hero mesh, so the centre lines the alignment gate measures do not move
    fore-aft and the leg line only scales with stance_w."""
    za, zh, zt = Z_ANKLE * H0, Z_HIP * H0, Z_TOP * H0
    zh2 = za + (zh - za) * sh['leg']; zt2 = zh2 + (zt - zh) * sh['torso']

    def zmap(z):
        if z <= za:
            return z
        if z <= zh:
            return za + (z - za) * sh['leg']
        if z <= zt:
            return zh2 + (z - zh) * sh['torso']
        return zt2 + (z - zt)
    tc = _centres(m, 'torso', 8)
    tz = [c[0] for c in tc]
    sx = list(zip(tz, (sh['hip_w'], sh['waist_w'], sh['chest_w'], sh['shoulder_w'])))
    d = sh['depth']
    sd = list(zip(tz, (d * (1. + .5 * sh['belly']), d * (1. + sh['belly']), d, .5 * (d + 1.))))
    cyt = [(c[0], c[2]) for c in tc]

    def torso(p):
        x, y, z = p
        cy = _tab(cyt, z)
        return (x * _tab(sx, z), cy + (y - cy) * _tab(sd, z), zmap(z))

    def collar(p):
        x, y, z = p
        c = COLLAR_CY * H0
        return (x * sh['neck_w'], c + (y - c) * sh['neck_w'], zmap(z))
    pv = tuple(c * H0 for c in NECK_PIVOT)
    pv2 = collar(pv)

    def head(p):
        return tuple(pv2[k] + sh['head'] * (p[k] - pv[k]) for k in range(3))

    def arm(side):
        S, F, Hd = (m.bones[n + '_' + side] for n in ('upper_arm', 'forearm', 'hand'))
        S2 = (S[0] * sh['shoulder_w'], S[1], zmap(S[2]))

        def axis(z):
            a, b = (S, F) if z >= F[2] else (F, Hd)
            t = min(1., max(0., (a[2] - z) / (a[2] - b[2])))
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t

        def f(p, thick=True):
            x, y, z = p
            if thick:
                ax, ay = axis(z)
                x = ax + (x - ax) * sh['arm_w']; y = ay + (y - ay) * sh['arm_w']
            return (S2[0] + sh['arm'] * (x - S[0]), S2[1] + sh['arm'] * (y - S[1]), S2[2] + sh['arm'] * (z - S[2]))
        return f
    lc = _centres(m, 'trouser_l', 6)                    # the left leg; the right leg is its mirror image
    lcx = [(c[0], c[1]) for c in lc]; lcy = [(c[0], c[2]) for c in lc]

    def leg(side, w):
        s = 1. if side == 'l' else -1.

        def f(p):
            x, y, z = p
            cx = s * _tab(lcx, z); cy = _tab(lcy, z)
            return (cx * sh['stance_w'] + (x - cx) * w, cy + (y - cy) * w, zmap(z))
        return f
    arms = {s: arm(s) for s in 'lr'}
    anchor = set(getattr(m, 'cast_anchor', ())) | set(getattr(m, 'neck_rings', {}).get('base', ()))
    for part, ids in m.parts.items():
        g = _group(part)
        side = part[-1] if g in ('leg', 'arm') else None
        if g == 'leg':
            fn = leg(side, sh['boot'] if part.startswith('boot_') else sh['leg_w'])
        elif g == 'arm':
            fn = arms[side]
        else:
            fn = {'torso': torso, 'collar': collar, 'head': head}[g]
        for vi in ids:
            m.vertices[vi] = (collar if vi in anchor else fn)(m.vertices[vi])
    B = dict(m.bones)
    out = {}
    for n, b in B.items():
        if n in ('pelvis', 'spine'):
            out[n] = (b[0], b[1], zmap(b[2]))
        elif n == 'head':
            out[n] = head(b)
        elif n.startswith(('upper_arm', 'forearm', 'hand')):
            out[n] = arms[n[-1]](b, thick=False)
        elif n.startswith(('thigh', 'shin', 'foot')):
            out[n] = (b[0] * sh['stance_w'], b[1], zmap(b[2]))
        else:
            out[n] = b
    for n in B:
        m.bones[n] = out[n]
    return head


def person(cameo, T3, spec=None):
    """The cast mesh of a spec (rest pose, Z up, faces -Y, grounded). cameo: the restricted round-21 builder,
    T3: ext/tall_v3 (both loaded by the caller)."""
    over, sh, st = resolve(spec)
    if 'height' in over:
        raise SpecError("height is a shape dial (spec['shape']['height']), not a cameo param")
    vals = dict(over)
    vals['height'] = H0
    m = T3.person(cameo, vals)
    hl = _head_local(T3)
    top0 = max(m.vertices[vi][2] for vi in m.parts['hair'])     # stature = top of the hair cap, as the hero
    m.cast_anchor = set()
    if st['hair'] != 'spikes':
        _strip(m, ('spike_', 'leaf_'))
        if st['hair'] in BLADES:
            _add_blades(m, hl, st['hair'])
        elif st['hair'] == 'curls':
            _add_curls(m, hl)
        elif st['hair'] == 'hood':
            _add_hood(m, hl)
    if st['visor'] in ('none', 'glasses'):
        _strip(m, ('visor',))
        if st['visor'] == 'glasses':
            _add_glasses(m, hl)
    elif st['visor'] == 'band':
        _band_visor(m)
    if st['coat']:
        _add_coat(m, T3, st['coat'], st['coat_flare'], st['coat_top'], st['coat_seam'])
    if st['guards']:
        _add_guards(m)
    if st['plate']:
        _add_plate(m)
    plain = sh == SHAPE
    if not plain:
        head = _reshape(m, sh)
        top = max(m.vertices[vi][2] for vi in m.parts['hair'])
        k = sh['height'] * (top0 / H0) / top
        m.vertices = [(v[0] * k, v[1] * k, v[2] * k) for v in m.vertices]
        for n, b in list(m.bones.items()):
            m.bones[n] = (b[0] * k, b[1] * k, b[2] * k)
        hf = getattr(m, 'head_frame', None)
        if isinstance(hf, dict) and 'hh' in hf:
            cz = head((0., 0., hf['chin_z']))[2] * k
            m.head_frame = dict(hf, hh=hf['hh'] * sh['head'] * k, chin_z=cz)
        m.params['height'] = sh['height']
    if st['coat']:
        _fit_coat(m)
        if st['coat_top'] == 'tucked':
            _tuck_coat(m, T3)
    bind = {}
    if st['guards'] and st['guard_clear']:
        bind['guard_dz_m'] = round(_clear_guards(m, st['guard_clear']), 6)
    floor = min(v[2] for v in m.vertices)
    if abs(floor) > 1e-9:
        raise SpecError('cast mesh is not grounded (floor %r)' % floor)
    if not plain or st != STYLE:
        m.preset = PRESET
        m.topology = TOPOLOGY
    # bind dials at their default are left out of the record: earlier specs keep their record and their bytes
    m.cast = {'shape': sh, 'style': {k: v for k, v in st.items() if k not in BIND_STYLE or v != BIND_STYLE[k]}}
    m.cast_bind = bind
    return m


# ---------------------------------------------------------------------------------------------- measurement
def _ids(m, prefixes):
    return sorted({vi for part, ids in m.parts.items() if part.startswith(tuple(prefixes)) for vi in ids})


def symmetry(m, verts=None):
    """Left-right asymmetry per group (GROUPS: the tall_v3 groups plus the cast pieces; hair included), as
    tall_v3.symmetry measures it: mirror every vertex in x = 0, distance to the nearest vertex of its group."""
    H = m.params['height']
    V = verts if verts is not None else m.vertices
    out = {}
    for g, prefixes in GROUPS.items():
        P = [tuple(float(c) for c in V[vi]) for vi in _ids(m, prefixes)]
        worst = 0.
        for (x, y, z) in P:
            worst = max(worst, min((x + q[0]) ** 2 + (y - q[1]) ** 2 + (z - q[2]) ** 2 for q in P))
        worst = math.sqrt(worst)
        out[g] = {'mm': round(worst * 1000., 2), 'x_h': round(worst / H, 5)}
    return out


def leg_gap(m, verts=None):
    """Half the free gap between the legs, x H: the smallest distance of a leg or boot vertex from the centre plane
    on its own side. Negative = a leg crosses the centre plane (the two legs cross or overlap)."""
    H = m.params['height']
    V = verts if verts is not None else m.vertices
    g = None
    for part, ids in m.parts.items():
        if part.startswith(GROUPS['legs']):
            s = 1. if part.endswith('_l') else -1.
            for vi in ids:
                d = s * float(V[vi][0])
                g = d if g is None else min(g, d)
    return round(g / H, 4)


def gate(T3, m):
    """tall_v3's alignment gate plus the cast checks. Returns (values, bad). The hair group is gated too, except the
    hero's own spikes (asymmetric by design, reported as in tall_v3)."""
    a, _ = T3.gate(m)
    sym = symmetry(m)
    groups = [g for g in sym if not (g == 'hair' and m.cast['style']['hair'] == 'spikes')]
    a['cast_asymmetry'] = max(sym[g]['x_h'] for g in groups)
    a['leg_gap_half'] = leg_gap(m)
    limits = dict(T3.GATE); limits.update(GATE)
    bad = {k: v for k, v in a.items()
           if (limits[k][0] is not None and v < limits[k][0]) or (limits[k][1] is not None and v > limits[k][1])}
    return a, bad


def measure(T3, m):
    """Proportion numbers of a cast mesh (rest pose). Lengths x H unless named _m. heads = stature / head height
    (chin to the top of the hair cap; hood, spikes and curls not counted in either)."""
    H = m.params['height']
    hm = T3.head_measure(m)

    def ext(prefixes, k, fn):
        return fn(m.vertices[vi][k] for vi in _ids(m, prefixes))
    top = max(v[2] for v in m.vertices)
    cap = hm['hair_cap_top_z'] * H
    hem = [m.vertices[vi] for vi in T3._ring_ids(m, 'torso', 8, 0)]
    hip_z = sum(m.vertices[vi][2] for vi in T3._ring_ids(m, 'trouser_l', 6, 4)) / 6.
    r = lambda v: round(v, 4)
    return {'height_param_m': r(H), 'top_m': r(top), 'hair_cap_top_m': r(cap), 'head_h': hm['head_h'],
            'heads': round(cap / (hm['head_h'] * H), 2), 'head_h_per_cap_top': r(hm['head_h'] * H / cap),
            'neck_front_per_head_h': hm['neck_front_per_head_h'],
            'shoulder_w': r(2. * ext(('sleeve_',), 0, max) / H), 'hem_w': r(2. * max(p[0] for p in hem) / H),
            'leg_len': r(hip_z / H), 'shoulder_w_m': r(2. * ext(('sleeve_',), 0, max)),
            'shoulder_per_head_w': r(2. * ext(('sleeve_',), 0, max) / (hm['head_w_hair_cap'] * H)),
            'depth': r((ext(('torso',), 1, max) - ext(('torso',), 1, min)) / H), 'tris': len(m.faces)}
