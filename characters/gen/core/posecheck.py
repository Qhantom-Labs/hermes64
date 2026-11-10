"""Programmatic pose check (STEER-4 B). Python 3.9 + numpy; no Blender.

check(a, stance, clip, t, prop_list=()) -> report dict for one posed character.

Measured on the actual skinned mesh (core/pose.py linear blend skinning, the same rotations Blender uses):
  * interpenetration VOLUMES between closed limb pieces (voxel sampling with vertical-ray parity,
    6 mm grid): left arm vs right arm, forearm vs torso, hand buried in torso/legs/other arm,
    elbow joint inside the torso, left leg vs right leg;
  * hand VISIBILITY: an orthographic z-buffer render (front camera and the hand's own-side 3/4 camera,
    4 mm pixels) counts each hand's visible pixels against the pixels it covers with nothing in front
    (held props included as occluders).

Limb pieces are closed sub-lofts cut from the ring structure of each part (forearm = sleeve rings 0..2,
upper arm = rings 2..4, shin = trouser rings 0..2, thigh = rings 2..4) so designed overlaps (sleeve top
inside the torso, mitt inside the cuff) are never counted. Thresholds are fixed constants below; a pose
is changed to meet them, the thresholds are not tuned to a pose.
"""
import math

import numpy as np

from . import pose as PO
from . import props as PR

LIMITS = {
    'arm_arm': .05,          # overlap / smaller arm (forearm+hand) volume
    'forearm_torso': .20,    # forearm volume inside the torso
    'hand_buried': .45,      # hand volume inside torso / legs / the other arm
    'leg_leg': .06,          # overlap / smaller leg volume
    'hand_vis_front': .30,   # visible / unoccluded hand pixels, front camera
    'hand_vis_34': .30,      # same, the hand's own-side 3/4 camera
    'prop_floor_gap': .01,   # round 16: floor-planted prop (cane) tip may float at most 1 cm (idle t=0)
}
YAW_34 = .65                 # radians; matches the review renders' 3/4 views
ELEV = .19                   # camera pitch (tan), same as the review cameras (0.75 over 4 m)
GRID = .006                  # voxel spacing (m)
PIX = .004                   # pixel size (m)
NR = {'sleeve': 5, 'mitt': 3, 'thumb': 2, 'torso': 4, 'trouser': 5, 'boot': 3, 'yoke': 3, 'collar': 2}

# Views from which a stance's hands are meant to read. Default: front + own-side 3/4.
# 'behind_back' hides the hands from the front by design; it is judged from the back cameras instead.
STANCE_VIEWS = {'behind_back': 'back'}


def _posed(a, stance, clip, t):
    H = a.params.get('height', 1.)
    local = PO.local_rotations(a.bones, H, a.kind, clip, t, stance, PO.body_metrics(a))
    qw, pos = PO._fk_world(a.bones, a.parents, local)
    verts = np.array(PO.skin(a.bones, a.parents, local, a.vertices, a.weights))
    return verts, qw, pos


def _ring_slices(a, part):
    ids = a.parts[part]
    fam = part.split('_')[0]
    nr = NR[fam]
    n = len(ids) // nr
    assert n * nr == len(ids), (part, len(ids), nr)
    return [ids[k * n:(k + 1) * n] for k in range(nr)]


def subloft(V, rings, k0, k1):
    """Closed triangle soup (T,3,3) for rings k0..k1 of a loft (bands + fan caps)."""
    tris = []
    for k in range(k0, k1):
        r0 = rings[k]; r1 = rings[k + 1]; n = len(r0)
        for j in range(n):
            a, b, c, d = r0[j], r0[(j + 1) % n], r1[(j + 1) % n], r1[j]
            tris.append((a, b, c)); tris.append((a, c, d))
    for k in (k0, k1):
        r = rings[k]
        for j in range(1, len(r) - 1):
            tris.append((r[0], r[j], r[j + 1]))
    return V[np.array(tris)]


def part_tris(a, V, part):
    s = set(a.parts[part])
    return V[np.array([f for f in a.faces if f[0] in s and f[1] in s and f[2] in s])]


def pieces(a, V):
    P = {}
    for side in ('l', 'r'):
        sl = _ring_slices(a, 'sleeve_' + side)
        P['forearm_' + side] = subloft(V, sl, 0, 2)
        P['upperarm_' + side] = subloft(V, sl, 2, 4)
        P['sleeve_' + side] = subloft(V, sl, 0, 4)
        P['mitt_' + side] = part_tris(a, V, 'mitt_' + side)
        P['thumb_' + side] = part_tris(a, V, 'thumb_' + side)
        tl = _ring_slices(a, 'trouser_' + side)
        P['shin_' + side] = subloft(V, tl, 0, 2)
        P['thigh_' + side] = subloft(V, tl, 2, 4)
        P['boot_' + side] = part_tris(a, V, 'boot_' + side)
    P['torso'] = part_tris(a, V, 'torso')
    return P


# ------------------------------------------------------------------ voxel inside tests
def _dot3(P, v):
    """P (..., 3) . v without BLAS (avoids spurious Accelerate matmul warnings)."""
    return P[..., 0] * v[0] + P[..., 1] * v[1] + P[..., 2] * v[2]


def _crossings(tris, xs, ys):
    """z of vertical-ray crossings, sorted per ray: array (K, len(xs)*len(ys)) padded with NaN
    (NaN compares False, so padding never counts as a crossing)."""
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    px = X.ravel(); py = Y.ravel()
    p0 = tris[:, 0]; p1 = tris[:, 1]; p2 = tris[:, 2]
    d = (p1[:, 1] - p2[:, 1]) * (p0[:, 0] - p2[:, 0]) + (p2[:, 0] - p1[:, 0]) * (p0[:, 1] - p2[:, 1])
    ok = np.abs(d) > 1e-14
    p0 = p0[ok]; p1 = p1[ok]; p2 = p2[ok]; d = d[ok]
    if len(d) == 0:
        return np.full((1, px.size), np.nan)
    w0 = ((p1[:, 1] - p2[:, 1])[:, None] * (px[None] - p2[:, 0][:, None]) +
          (p2[:, 0] - p1[:, 0])[:, None] * (py[None] - p2[:, 1][:, None])) / d[:, None]
    w1 = ((p2[:, 1] - p0[:, 1])[:, None] * (px[None] - p2[:, 0][:, None]) +
          (p0[:, 0] - p2[:, 0])[:, None] * (py[None] - p2[:, 1][:, None])) / d[:, None]
    w2 = 1 - w0 - w1
    hit = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    z = w0 * p0[:, 2][:, None] + w1 * p1[:, 2][:, None] + w2 * p2[:, 2][:, None]
    z = np.where(hit, z, np.nan)
    z.sort(axis=0)                                   # NaN sorts last
    k = int(max(1, hit.sum(0).max()))
    return z[:k]


def _inside(tris, xs, ys, zs):
    """Boolean (len(xs)*len(ys), len(zs)): grid point inside the closed soup (odd crossings above)."""
    zc = _crossings(tris, xs, ys)
    with np.errstate(invalid='ignore'):
        cnt = (zc[:, :, None] > zs[None, None, :]).sum(0)
    return (cnt % 2) == 1


def _box(*soups):
    allv = np.concatenate([s.reshape(-1, 3) for s in soups])
    return allv.min(0), allv.max(0)


def _grid(lo, hi):
    off = np.array([.37, .61, .23]) * GRID           # irrational-ish offsets avoid rays through vertices
    return [np.arange(lo[i] + off[i], hi[i], GRID) for i in range(3)]


def volume(soups):
    lo, hi = _box(*soups)
    xs, ys, zs = _grid(lo, hi)
    if min(len(xs), len(ys), len(zs)) == 0:
        return 0.
    m = np.zeros((len(xs) * len(ys), len(zs)), bool)
    for s in soups:
        m |= _inside(s, xs, ys, zs)
    return m.sum() * GRID ** 3


def overlap(soups_a, soups_b):
    """Volume inside (union of soups_a) AND inside (union of soups_b)."""
    la, ha = _box(*soups_a); lb, hb = _box(*soups_b)
    lo = np.maximum(la, lb); hi = np.minimum(ha, hb)
    if np.any(hi <= lo):
        return 0.
    xs, ys, zs = _grid(lo, hi)
    if min(len(xs), len(ys), len(zs)) == 0:
        return 0.
    ma = np.zeros((len(xs) * len(ys), len(zs)), bool); mb = ma.copy()
    for s in soups_a:
        ma |= _inside(s, xs, ys, zs)
    for s in soups_b:
        mb |= _inside(s, xs, ys, zs)
    return (ma & mb).sum() * GRID ** 3


def point_inside(soup, p):
    xs = np.array([p[0]]); ys = np.array([p[1]]); zs = np.array([p[2]])
    return bool(_inside(soup, xs, ys, zs)[0, 0])


# ------------------------------------------------------------------ props as occluders
def prop_soups(a, qw, pos, prop_list, stance=None, clip='idle'):
    """Held props posed exactly as core/blender.add_prop places them (core/attach.py)."""
    from . import attach as AT
    out = []
    for kind in prop_list or ():
        m = PR.build(kind)
        if clip == 'carry' and m.slot != 'belt':
            continue                     # runtime rule: hand props are stowed while carrying a load
        bone = AT.SLOT_BONE[m.slot]
        rest, m = AT.place_vertices(a, stance, kind)
        j = a.bones[bone]
        V = []
        for v in rest:
            r = PO.qv(qw[bone], (v[0] - j[0], v[1] - j[1], v[2] - j[2]))
            V.append((pos[bone][0] + r[0], pos[bone][1] + r[1], pos[bone][2] + r[2]))
        V = np.array(V)
        out.append(('prop_' + kind, V[np.array(m.faces)]))
    return out


# ------------------------------------------------------------------ z-buffer visibility
def _camera(yaw):
    d = np.array([-math.sin(yaw), math.cos(yaw), -ELEV]); d /= np.linalg.norm(d)
    right = np.cross(d, [0., 0., 1.]); right /= np.linalg.norm(right)
    up = np.cross(right, d)
    return d, right, up


def render_ids(soups, yaw):
    """soups: list of (id, tris). Returns (idbuf, coverage{id: bool mask})."""
    d, right, up = _camera(yaw)
    allv = np.concatenate([s.reshape(-1, 3) for _, s in soups])
    sx = _dot3(allv, right); sy = _dot3(allv, up)
    x0, y0 = sx.min() - 2 * PIX, sy.min() - 2 * PIX
    W = int((sx.max() - x0) / PIX) + 3; Hh = int((sy.max() - y0) / PIX) + 3
    zbuf = np.full((Hh, W), np.inf); ibuf = np.full((Hh, W), -1, int)
    cover = {}
    names = []
    for idx, (name, tris) in enumerate(soups):
        names.append(name)
        cov = np.zeros((Hh, W), bool)
        P = tris.reshape(-1, 3)
        X = (_dot3(P, right) - x0) / PIX; Y = (_dot3(P, up) - y0) / PIX; Z = _dot3(P, d)
        X = X.reshape(-1, 3); Y = Y.reshape(-1, 3); Z = Z.reshape(-1, 3)
        for t in range(len(tris)):
            xa, xb, xc = X[t]; ya, yb, yc = Y[t]
            den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
            if abs(den) < 1e-9:
                continue
            i0 = max(int(math.floor(min(xa, xb, xc))), 0); i1 = min(int(math.ceil(max(xa, xb, xc))), W - 1)
            j0 = max(int(math.floor(min(ya, yb, yc))), 0); j1 = min(int(math.ceil(max(ya, yb, yc))), Hh - 1)
            if i1 < i0 or j1 < j0:
                continue
            gx, gy = np.meshgrid(np.arange(i0, i1 + 1) + .5, np.arange(j0, j1 + 1) + .5)
            w0 = ((yb - yc) * (gx - xc) + (xc - xb) * (gy - yc)) / den
            w1 = ((yc - ya) * (gx - xc) + (xa - xc) * (gy - yc)) / den
            w2 = 1 - w0 - w1
            m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not m.any():
                continue
            z = w0 * Z[t, 0] + w1 * Z[t, 1] + w2 * Z[t, 2]
            sub_z = zbuf[j0:j1 + 1, i0:i1 + 1]; sub_i = ibuf[j0:j1 + 1, i0:i1 + 1]
            closer = m & (z < sub_z)
            sub_z[closer] = z[closer]; sub_i[closer] = idx
            cov[j0:j1 + 1, i0:i1 + 1] |= m
        cover[name] = cov
    return ibuf, cover, names


def hand_visibility(a, V, P, extra, yaw):
    hands = {'hand_l': np.concatenate([P['mitt_l'], P['thumb_l']]),
             'hand_r': np.concatenate([P['mitt_r'], P['thumb_r']])}
    hs = {i for side in 'lr' for i in a.parts['mitt_' + side] + a.parts['thumb_' + side]}
    body = V[np.array([f for f in a.faces if not (f[0] in hs and f[1] in hs and f[2] in hs)])]
    soups = [('body', body), ('hand_l', hands['hand_l']), ('hand_r', hands['hand_r'])] + list(extra)
    ibuf, cover, names = render_ids(soups, yaw)
    out = {}
    for k in ('hand_l', 'hand_r'):
        idx = names.index(k)
        alone = int(cover[k].sum()); vis = int((ibuf == idx).sum())
        out[k] = (vis / alone if alone else 0., vis, alone)
    return out


# ------------------------------------------------------------------ the check
def check(a, stance, clip='idle', t=0., prop_list=(), views=True):
    V, qw, pos = _posed(a, stance, clip, t)
    P = pieces(a, V)
    rep = {'stance': stance, 'clip': clip, 't': t, 'fails': []}
    arm = {s: [P['forearm_' + s], P['mitt_' + s], P['thumb_' + s]] for s in 'lr'}
    va = {s: volume(arm[s]) for s in 'lr'}
    rep['arm_arm'] = overlap(arm['l'], arm['r']) / max(1e-9, min(va.values()))
    legs = {s: [P['shin_' + s], P['thigh_' + s], P['boot_' + s]] for s in 'lr'}
    vl = {s: volume(legs[s]) for s in 'lr'}
    rep['leg_leg'] = overlap(legs['l'], legs['r']) / max(1e-9, min(vl.values()))
    for s, o in (('l', 'r'), ('r', 'l')):
        vf = volume([P['forearm_' + s]])
        rep['forearm_torso_' + s] = overlap([P['forearm_' + s]], [P['torso']]) / max(1e-9, vf)
        hand = [P['mitt_' + s], P['thumb_' + s]]
        vh = volume(hand)
        hosts = [P['torso'], P['thigh_l'], P['thigh_r'], P['sleeve_' + o]]
        rep['hand_buried_' + s] = overlap(hand, hosts) / max(1e-9, vh)
        rep['elbow_in_torso_' + s] = point_inside(P['torso'], pos['forearm_' + s])
    L = LIMITS
    if rep['arm_arm'] > L['arm_arm']:
        rep['fails'].append('arm_arm_overlap %.2f' % rep['arm_arm'])
    if rep['leg_leg'] > L['leg_leg']:
        rep['fails'].append('leg_leg_overlap %.2f' % rep['leg_leg'])
    for s in 'lr':
        if rep['forearm_torso_' + s] > L['forearm_torso']:
            rep['fails'].append('forearm_%s_in_torso %.2f' % (s, rep['forearm_torso_' + s]))
        if rep['hand_buried_' + s] > L['hand_buried']:
            rep['fails'].append('hand_%s_buried %.2f' % (s, rep['hand_buried_' + s]))
        if rep['elbow_in_torso_' + s]:
            rep['fails'].append('elbow_%s_inside_torso' % s)
    if clip == 'idle' and t == 0.:
        from . import attach as AT
        for kind in prop_list or ():
            gap = AT.floor_gap(a, stance, kind)
            if gap > L['prop_floor_gap']:
                rep['fails'].append('prop_%s_floats %.3f' % (kind, gap))
    if views:
        extra = prop_soups(a, qw, pos, prop_list, stance, clip)
        declared = PO.stance_def(stance).get('views') or STANCE_VIEWS.get(stance, 'front')
        back = declared == 'back' and clip == 'idle'
        base = math.pi if back else 0.
        cams = {'front': base, '34_l': base + (YAW_34 if not back else -YAW_34),
                '34_r': base + (-YAW_34 if not back else YAW_34)}
        rep['views'] = 'back' if back else 'front'
        vis = {c: hand_visibility(a, V, P, extra, y) for c, y in cams.items()}
        rep['hand_vis'] = {c: {k: round(v[0], 3) for k, v in r.items()} for c, r in vis.items()}
        for s in 'lr':
            f = vis['front']['hand_' + s][0]
            q = vis['34_' + s]['hand_' + s][0]
            if f < L['hand_vis_front']:
                rep['fails'].append('hand_%s_hidden_%s %.2f' % (s, 'back' if back else 'front', f))
            if q < L['hand_vis_34']:
                rep['fails'].append('hand_%s_hidden_34 %.2f' % (s, q))
    rep['pass'] = not rep['fails']
    for k, v in list(rep.items()):
        if isinstance(v, float):
            rep[k] = round(v, 4)
    return rep


# ------------------------------------------------------------------ per-body stance fallback (round 13, STEER-5 §3)
# Some stances cannot be reached cleanly on extreme random bodies (very puffy / deep belly / child proportions):
# folded arms interpenetrate over a big belly, elbows sink into a puffy torso behind the back. Rather than baking
# a broken pose, the character falls back along a short, declared chain of calmer stances; the check itself is the
# arbiter (idle t=0 and t=.5, front + 3/4 views, props as occluders). Prop stances keep their prop only while the
# original stance is kept. The tuned cast never falls back (tools/pose_audit records requested == used).
STANCE_FALLBACKS = {
    'arms_crossed': ('hands_hips', 'confident', 'neutral'), 'behind_back': ('hands_hips', 'confident', 'neutral'),
    'shy': ('pockets', 'confident', 'neutral'), 'thinking': ('hands_hips', 'confident', 'neutral'),
    'pockets': ('confident', 'neutral'), 'eager': ('confident', 'neutral'), 'hands_hips': ('confident', 'neutral'),
    'wave': ('confident', 'neutral'), 'guard': ('hands_hips', 'confident', 'neutral'),
    'hold_mug': ('confident', 'neutral'), 'reading': ('confident', 'neutral'), 'lantern_up': ('confident', 'neutral'),
    'satchel': ('confident', 'neutral'), 'duffel': ('confident', 'neutral'), 'stoop_cane': ('confident', 'neutral'),
    'tablet': ('confident', 'neutral'),
}


def _deform_ok(a, stance):
    """Round 21: gates.deformation (edge ratio in [.45, 1.8]) in every clip at the sweep's 4 frames. A random visor body
    in 'thinking' stretched a sleeve edge to 1.803 (fresh seed 1907841; the same in round 20)."""
    from . import gates
    H = a.params.get('height', 1.)
    for clip in PO.HCLIPS:
        for t in (0., .25, .5, .75):
            loc = PO.local_rotations(a.bones, H, a.kind, clip, t, stance, PO.body_metrics(a))
            if not gates.deformation(a.vertices, PO.skin(a.bones, a.parents, loc, a.vertices, a.weights), a.faces)['pass']:
                return False
    return True


def resolve_stance(a, stance, prop_list=()):
    """-> (stance_used, props_used, tried). First stance of [stance] + STANCE_FALLBACKS[stance] whose key poses pass
    this check on body `a` in EVERY clip (t = 0 and .5; round 19: the arbiter used to look at idle only, so a stance
    that broke in another clip was kept and then failed the sweep - fresh seed 4100501 sweep_face_03, a child whose
    book hid the hand while sitting); the last candidate if none passes. The tuned cast passes every clip, so it never
    falls back (tools/pose_audit).
    Round 21 (STEER-8): a stance must also keep every join closed (core/connectivity, every clip at the sweep's 4
    frames): a head-down stance that would lift a random body's hood off its collar roll, or a raised arm that would
    pull a sleeve root off the torso, falls back like any other pose failure; so does a stance that over-stretches an
    edge (gates.deformation)."""
    if stance is None or getattr(a, 'kind', None) != 'human':
        return stance, list(prop_list or ()), []
    from . import connectivity as CN
    cands = [stance] + [s for s in STANCE_FALLBACKS.get(stance, ()) if s != stance]
    tried = []
    for k, st in enumerate(cands):
        props = list(prop_list or ()) if k == 0 else []
        ok = all(check(a, st, clip, t, props)['pass'] for clip in PO.HCLIPS for t in (0., .5))
        if ok:
            ok = CN.check_poses(a, st, include_rest=False)['pass']
        if ok:
            ok = _deform_ok(a, st)
        tried.append((st, ok))
        if ok:
            return st, props, tried
    return cands[-1], [], tried
