"""nous_girl: the captive girl (lane CAST2), built as a DELTA on the approved hero base tall_v3 revision 3.

person(T3, cameo, values) calls ext/tall_v3.person (rig human16_v1, the same collar, neck, torso stacking and gates) at
her own height and build and then edits the finished mesh:

  1. HEAD GEAR  the hero's hair cap, spikes, leaves and visor are removed, vertices and faces (150 triangles).
  2. BOB        a 12-sided bob with a flat fringe: closed crown, fringe edge above the eyes, two side locks in front
                of the cheeks, hem at chin level a little wider than the ring above it, a strip under the fringe and
                an inner wall for the lowest band (the inside shows beside the neck). Built as one half and mirrored,
                so it is left-right symmetric by construction.
  3. LEGS       slimmer leg columns (one straight line hip -> ankle, as the base) and boots scaled to them; no thigh
                pouch.
  4. WAIST      the waist ring is narrower; hem, chest and top rings are the base rings at her build.

No vertex of torso, collar, sleeves, hands, face or neck is added or removed. Nothing here carries a logo, a star or
text: the surface is paint (ext/nous_girl_paint.py), the headphones are a separate prop (ext/nous_girl_props.py).
All numbers are x H (H = params['height']) in the finished, grounded mesh unless named otherwise. Front = -y, z up,
x > 0 = her left.
"""
import math

PRESET = 'nous_girl'
REVISION = 1
HEIGHT = 1.60                 # m. plans/05C gives no figure for her; the lane brief's fallback
BUILD = .90                   # lowest build of the base family range
PARAMS = {'height': HEIGHT, 'build': BUILD, 'eye_shape': 'round', 'brows': 'thin', 'mouth': 'neutral'}
STRIP = ('hair', 'visor', 'spike_', 'leaf_')

# ---- legs: (z, centre y, rx, ry) from the ankle up; centre x on the straight line LEG_X[0] (ankle) -> LEG_X[1] (hip)
LEG = [(.100, .002, .036, .038), (.172, .003, .044, .050), (.280, -.001, .040, .046),
       (.388, .002, .050, .058), (.480, .002, .052, .058)]
LEG_X = (.066, .058)
BOOT_SCALE = .88              # boots in x and y about the ankle centre (height unchanged)
WAIST = (.565, .000, .066, .066)          # z, centre y, rx, ry (the base ring at build .9 is rx .0756)

# ---- bob. Rings: (z, centre y, rx, ry); 12 points, j = 0 back, 3 her right, 6 front, 9 her left.
BOB_N = 12
BOB_APEX = (.006, .998)                   # y, z: the top of the figure
BOB_RINGS = {'A': (.984, .006, .030, .036), 'B': (.958, .006, .056, .066), 'C': (.915, .005, .066, .078),
             'D': (.868, .006, .071, .080), 'E': (.826, .008, .075, .080)}
FRINGE = (.899, .005, .0665, .0785)       # fringe edge: ring C dropped to this z, j = 4..8
FRINGE_IN = (.905, .005, .058, .0715)     # inner edge of the strip under the fringe (at the forehead)
LOCK = {'D': (.050, -.054), 'E': (.052, -.054)}     # |x|, y of the side lock's front edge (j = 4 and 8)
BOB_V = {'apex': .97, 'A': .90, 'B': .80, 'C': .66, 'F': .585, 'D': .47, 'E': .30}   # texture v of each level
BOB_U = (.03, .97)
BOB_DARK = (.06, .94, .05, .20)           # u0, u1, v0, v1: texels of the inner wall and the fringe underside
BOB_AO = {'lining': .55, 'under': .62}
BOB_BACK = (8, 9, 10, 11, 0, 1, 2, 3)     # ring segments j -> j + 1 of the side and back panels (below ring C)


def values(v):
    v = dict(v)
    v.update(PARAMS)
    return v


def _strip(m, prefixes):
    """Remove whole parts: their vertices and every face on them; everything else is re-indexed."""
    n = len(m.vertices)
    for name, val in vars(m).items():
        if name not in ('vertices', 'weights') and isinstance(val, list) and len(val) == n and name not in ('faces', 'uv', 'roles', 'tiles'):
            raise ValueError('nous_girl._strip: unknown per-vertex list %r' % name)
    gone = set()
    for part in [p for p in m.parts if p.startswith(tuple(prefixes))]:
        gone |= set(m.parts.pop(part))
    keep = [i for i, f in enumerate(m.faces) if not (f[0] in gone or f[1] in gone or f[2] in gone)]
    dropped = len(m.faces) - len(keep)
    for attr in ('faces', 'uv', 'roles', 'tiles'):
        setattr(m, attr, [getattr(m, attr)[i] for i in keep])
    for part, ids in m.parts.items():
        if gone & set(ids):
            raise ValueError('nous_girl._strip: part %s shares vertices with a removed part' % part)
    remap = {}
    verts = []; weights = []
    for i in range(n):
        if i in gone:
            continue
        remap[i] = len(verts)
        verts.append(m.vertices[i]); weights.append(m.weights[i])
    m.vertices = verts; m.weights = weights
    m.faces = [(remap[f[0]], remap[f[1]], remap[f[2]]) for f in m.faces]
    m.parts = {k: [remap[v] for v in ids] for k, ids in m.parts.items()}
    m.ao = {remap[k]: v for k, v in getattr(m, 'ao', {}).items()}
    if hasattr(m, 'neck_rings'):
        m.neck_rings = {k: [remap[v] for v in ids] for k, ids in m.neck_rings.items()}
    return dropped


def _half_ring(H, z, cy, rx, ry, lock=None):
    """12 points, built for j = 0..6 and mirrored in x = 0 (exactly symmetric)."""
    pts = [None] * BOB_N
    for j in range(0, BOB_N // 2 + 1):
        f = math.tau * (j / float(BOB_N) - .5)
        x = 0. if j in (0, BOB_N // 2) else rx * math.sin(f)          # x <= 0 for j = 1..5 (her right)
        y = cy - ry * math.cos(f)
        if lock is not None and j == 4:
            x, y = -lock[0], lock[1]
        pts[j] = (x * H, y * H, z * H)
        if 0 < j < BOB_N // 2:
            pts[BOB_N - j] = (-x * H, y * H, z * H)
    return pts


def bob(m, role='headwear', tile=0):
    """Add the bob (part 'hair', bone head). Returns the triangle count."""
    H = m.params['height']
    start_f = len(m.faces)
    m.parts['hair'] = []

    def add(pts, ao=None):
        ids = []
        for pt in pts:
            m.vertices.append((float(pt[0]), float(pt[1]), float(pt[2])))
            m.weights.append({'head': 1.})
            ids.append(len(m.vertices) - 1)
            if ao is not None:
                m.ao[ids[-1]] = ao
        m.parts['hair'] += ids
        return ids

    def tri(f, t):
        m.faces.append(tuple(f)); m.uv.append(list(t)); m.roles.append(role); m.tiles.append(tile)

    def quad(a, b, c, d, ua, ub, uc, ud, inward=False):
        for f, t in (((a, b, c), (ua, ub, uc)), ((a, c, d), (ua, uc, ud))):
            if inward:
                f = (f[0], f[2], f[1]); t = (t[0], t[2], t[1])
            tri(f, t)

    def uv(j, level):
        return (BOB_U[0] + (BOB_U[1] - BOB_U[0]) * j / float(BOB_N), BOB_V[level])

    def duv(j, top):
        u0, u1, v0, v1 = BOB_DARK
        return (u0 + (u1 - u0) * j / float(BOB_N), v1 if top else v0)

    R = {k: add(_half_ring(H, *BOB_RINGS[k], lock=LOCK.get(k))) for k in ('A', 'B', 'C', 'D', 'E')}
    apex = add([(0., BOB_APEX[0] * H, BOB_APEX[1] * H)])[0]
    N = BOB_N
    for j in range(N):                                              # crown
        tri((R['A'][j], R['A'][(j + 1) % N], apex), (uv(j, 'A'), uv(j + 1, 'A'), uv(j + .5, 'apex')))
    for lo, up in (('B', 'A'), ('C', 'B')):
        for j in range(N):
            j1 = (j + 1) % N
            quad(R[lo][j], R[lo][j1], R[up][j1], R[up][j], uv(j, lo), uv(j + 1, lo), uv(j + 1, up), uv(j, up))
    for lo, up in (('D', 'C'), ('E', 'D')):                         # side and back panels down to the hem
        for j in BOB_BACK:
            j1 = (j + 1) % N
            quad(R[lo][j], R[lo][j1], R[up][j1], R[up][j], uv(j, lo), uv(j + 1, lo), uv(j + 1, up), uv(j, up))
    fr = _half_ring(H, *FRINGE)
    F = {j: v for j, v in zip(range(4, 9), add([fr[j] for j in range(4, 9)]))}
    for j in range(4, 8):                                           # fringe
        quad(F[j], F[j + 1], R['C'][j + 1], R['C'][j], uv(j, 'F'), uv(j + 1, 'F'), uv(j + 1, 'C'), uv(j, 'C'))
    # the fringe corners run into the side locks
    tri((R['D'][4], F[4], R['C'][4]), (uv(4, 'D'), uv(4.3, 'F'), uv(4, 'C')))
    tri((F[8], R['D'][8], R['C'][8]), (uv(7.7, 'F'), uv(8, 'D'), uv(8, 'C')))
    gi = _half_ring(H, *FRINGE_IN)
    G = {j: v for j, v in zip(range(4, 9), add([gi[j] for j in range(4, 9)], BOB_AO['under']))}
    FU = {j: v for j, v in zip(range(4, 9), add([fr[j] for j in range(4, 9)], BOB_AO['under']))}
    for j in range(4, 8):                                           # strip under the fringe, facing down
        quad(G[j], G[j + 1], FU[j + 1], FU[j], duv(j, 0), duv(j + 1, 0), duv(j + 1, 1), duv(j, 1))
    Di = add([m.vertices[vi] for vi in R['D']], BOB_AO['lining'])
    Ei = add([m.vertices[vi] for vi in R['E']], BOB_AO['lining'])
    for j in BOB_BACK:                                              # inner wall of the lowest band
        j1 = (j + 1) % N
        quad(Ei[j], Ei[j1], Di[j1], Di[j], duv(j, 0), duv(j + 1, 0), duv(j + 1, 1), duv(j, 1), inward=True)
    return len(m.faces) - start_f


def person(T3, cameo, vals):
    m = T3.person(cameo, values(vals), T3.FIXES)
    H = m.params['height']
    PP = T3.PP

    def ring(n, x, y, z, rx, ry, tweak=None):
        return PP.zring(n, x * H, y * H, (z - T3.FLOOR) * H, rx * H, ry * H, tweak)
    stripped = _strip(m, STRIP)
    z, cy, rx, ry = WAIST
    T3._put(m, 'torso', 8, 1, ring(8, 0., cy, z, rx, ry))
    for side, s in (('l', 1), ('r', -1)):
        def knee(j, f, pt):
            c = math.cos(f)
            return (pt[0], pt[1] - T3.KNEE_FWD * H * max(0., c) ** 2, pt[2]) if c > .51 else pt
        ids = m.parts['boot_' + side]
        old_c = sum(m.vertices[vi][0] for vi in ids[:7]) / 7.
        for k, (z, cy, rx, ry) in enumerate(LEG):
            t = (z - LEG[0][0]) / (LEG[-1][0] - LEG[0][0])
            cx = LEG_X[0] + t * (LEG_X[1] - LEG_X[0])
            T3._put(m, 'trouser_' + side, 6, k, ring(6, s * cx, cy, z, rx, ry, knee if k == 2 else None))
        cx = s * LEG_X[0] * H; cy = LEG[0][1] * H
        for vi in ids:
            x, y, z = m.vertices[vi]
            m.vertices[vi] = (cx + (x - old_c) * BOOT_SCALE, cy + (y - cy) * BOOT_SCALE, z)
        for bone, t in (('thigh', 1.), ('shin', .5), ('foot', 0.)):
            bx, by, bz = m.bones[bone + '_' + side]
            m.bones[bone + '_' + side] = (s * (LEG_X[0] + t * (LEG_X[1] - LEG_X[0])) * H, by, bz)
    hair = bob(m)
    floor = min(v[2] for v in m.vertices)
    assert abs(floor) < 1e-9, 'nous_girl must stay grounded (floor %r)' % floor
    m.preset = PRESET
    m.cast2 = {'stripped_tris': stripped, 'hair_tris': hair}
    return m


# ------------------------------------------------------------------ gates and measures
HAIR_SYMMETRY_LIMIT = .0005     # x H, same limit as the body groups of the base


def hair_symmetry(T3, m, verts=None):
    H = m.params['height']
    V = verts if verts is not None else m.vertices
    P = [tuple(float(c) for c in V[vi]) for vi in m.parts['hair']]
    worst = 0.
    for (x, y, z) in P:
        worst = max(worst, min((x + q[0]) ** 2 + (y - q[1]) ** 2 + (z - q[2]) ** 2 for q in P))
    worst = math.sqrt(worst)
    return {'mm': round(worst * 1000., 2), 'x_h': round(worst / H, 5)}


def gate(T3, m):
    """The base alignment gate (legs inside the hem, straight plumb leg columns, stacked torso, left-right symmetry of
    torso / arms / legs / head skin) plus the bob's symmetry. -> (numbers, failures)."""
    a, bad = T3.gate(m)
    hs = hair_symmetry(T3, m)
    a['hair_left_right_asymmetry'] = hs['x_h']
    if hs['x_h'] > HAIR_SYMMETRY_LIMIT:
        bad['hair_left_right_asymmetry'] = hs['x_h']
    return a, bad


def torso_ring_tv(m, k, region):
    """Texture v (0..1 inside the painter's torso canvas, PPP._region_canvas tv) of torso ring k."""
    ids = set(T3_ring(m, 'torso', 8, k))
    u0, v0, u1, v1 = region
    for f, t in zip(m.faces, m.uv):
        for vi, (u, v) in zip(f, t):
            if vi in ids:
                return (((v - v0) / (v1 - v0)) - .03) / .94
    raise ValueError(k)


def T3_ring(m, part, n, k):
    ids = m.parts[part]
    return ids[k * n:(k + 1) * n]


def measure(m):
    """Numbers of the built figure (rest pose), metres unless named x_h."""
    H = m.params['height']
    V = m.vertices
    top = max(v[2] for v in V)

    def ext(prefixes):
        ids = [vi for part, lst in m.parts.items() if part.startswith(tuple(prefixes)) for vi in lst]
        return ids
    hair = [V[vi] for vi in m.parts['hair']]
    face = [V[vi] for vi in T3_ring(m, 'face', 10, 1)]
    sl = [V[vi] for vi in ext(('sleeve_',))]
    hem = [V[vi] for vi in T3_ring(m, 'torso', 8, 0)]
    waist = [V[vi] for vi in T3_ring(m, 'torso', 8, 1)]
    r = lambda x: round(x, 4)
    return {'height_param_m': H, 'top_of_hair_m': r(top), 'chin_m': r(min(p[2] for p in face)),
            'head_h_chin_to_top_m': r(top - min(p[2] for p in face)),
            'heads_tall': round(top / (top - min(p[2] for p in face)), 2),
            'hair_w_m': r(2 * max(p[0] for p in hair)), 'hair_hem_m': r(min(p[2] for p in hair)),
            'fringe_edge_m': r(FRINGE[0] * H), 'shoulder_w_m': r(2 * max(p[0] for p in sl)),
            'hem_w_m': r(2 * max(p[0] for p in hem)), 'waist_w_m': r(2 * max(p[0] for p in waist)),
            'hip_joint_m': r(m.bones['thigh_l'][2]), 'triangles': len(m.faces), 'vertices': len(V)}
