"""Base locomotion format: measure a body, bake its run and walk, validate them (docs/LOCOMOTION.md).

    spec = load_spec('base_v1')                  the data file next to this module
    body = read_body(glb_bytes, spec)            joints, skin, measurements; LocomotionError when the body cannot walk
    out, report = bake(glb_bytes)                a GLB with run and walk for this body + the locomotion block
    report = check(glb_bytes)                    the same metrics on the run / walk a file already carries

The cycle is the planted-foot solver of characters/gen/ext/clips_adult.py (lane CHARS3), moved here unchanged in its
maths and driven by the spec: each leg has a phase, a planted foot travels backward under the hip at the clip's ground
speed (pivoting on the heel at strike and on the toe at push-off), a two-bone solve in the fore-aft plane gives thigh
and shin, the run has a ballistic flight. Distances are in standing hip heights, so the ground speed scales with the leg.

What is new here is that it works on a FILE: the body is measured from the skinned mesh and the rest joints of any GLB
whose armature carries the listed bones, and the result is written as world-space turns converted to each joint's own
rest frame, so rest rotations, extra joints (toes, fingers, twist bones) and joint order do not matter.

Solver space is the generator's: x to the character's left, y backward, z up. glTF is x left, y up, z forward.
numpy only.
"""
import copy
import hashlib
import json
import math
import re
import types
from pathlib import Path

import numpy as np

from ..rigkit import gltf, gltfedit, lbs, seams

HERE = Path(__file__).resolve().parent
FORMAT = 'hermes64-locomotion-base/1.0.0'
BLOCK = 'hermes64_locomotion'
RAD = math.pi / 180.
C = np.array([[1., 0., 0.], [0., 0., 1.], [0., -1., 0.]])        # solver space -> glTF
SIDES = (('l', 1.), ('r', -1.))
ORDER = ('pelvis', 'spine', 'head', 'upper_arm_l', 'forearm_l', 'upper_arm_r', 'forearm_r',
         'thigh_l', 'shin_l', 'foot_l', 'thigh_r', 'shin_r', 'foot_r')
CLIPS = ('run', 'walk')


class LocomotionError(Exception):
    """A refusal in plain words. code is stable (tests, callers); report carries what was measured so far."""

    def __init__(self, code, message, report=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.report = report or {}


# spec -----------------------------------------------------------------------------------------------------------------
def load_spec(name='base_v1'):
    if isinstance(name, dict):
        spec = name
    else:
        p = Path(name) if str(name).endswith('.json') else HERE / (str(name) + '.json')
        if not p.is_file():
            raise LocomotionError('no_spec', 'there is no locomotion base named %s (looked for %s)' % (name, p))
        spec = json.loads(p.read_text(encoding='utf-8'))
    check_spec(spec)
    return spec


def check_spec(spec):
    if spec.get('schema') != FORMAT:
        raise LocomotionError('bad_spec', 'the locomotion base must have schema %s, this one has %r' % (FORMAT, spec.get('schema')))
    t = spec['timing']
    if t['keys'] != 2 * t['step_keys'] or t['cycle_keys'] != t['keys']:
        raise LocomotionError('bad_spec', 'timing: one cycle must be two steps (keys = cycle_keys = 2 x step_keys)')
    for clip in CLIPS:
        c = spec['cycles'].get(clip)
        if c is None:
            raise LocomotionError('bad_spec', 'the locomotion base has no %s cycle' % clip)
        if len(c['pitch_deg']) != c['stance'] + 1:
            raise LocomotionError('bad_spec', '%s: pitch_deg needs one value per planted key (stance + 1 = %d)' % (clip, c['stance'] + 1))
        if len(c['hip']) != t['step_keys']:
            raise LocomotionError('bad_spec', '%s: hip needs one value per key of a step (%d)' % (clip, t['step_keys']))
        want = [str(k) for k in range(c['stance'] + 1, t['keys'])]
        if sorted(c['swing'], key=int) != want:
            raise LocomotionError('bad_spec', '%s: swing needs exactly the keys %s..%s' % (clip, want[0], want[-1]))
        if c['swing_mode'] not in ('angles', 'ankle_path'):
            raise LocomotionError('bad_spec', '%s: swing_mode must be angles or ankle_path' % clip)


def cycle(spec, clip, tuning=None):
    """The cycle of one clip with a body's own tuning laid over it ({clip: {field: value}})."""
    c = copy.deepcopy(spec['cycles'][clip])
    for k, v in ((tuning or {}).get(clip) or {}).items():
        if k not in c:
            raise LocomotionError('bad_tuning', '%s has no field %r to tune (fields: %s)' % (clip, k, ', '.join(sorted(c))))
        c[k] = copy.deepcopy(v)
    return c


# small maths ----------------------------------------------------------------------------------------------------------
def _qm(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def _qa(axis, ang):
    s = math.sin(ang / 2)
    return (math.cos(ang / 2), axis[0] * s, axis[1] * s, axis[2] * s)


def _qe(x, y, z):
    """Euler 'XYZ' (X applied first) -> quaternion (w, x, y, z); core/pose.qe."""
    return _qm(_qa((0, 0, 1), z), _qm(_qa((0, 1, 0), y), _qa((1, 0, 0), x)))


def _mat(q):
    return lbs.quat_matrix((q[1], q[2], q[3], q[0]))


def _quat(m):
    """3x3 rotation -> glTF quaternion [x, y, z, w], w >= 0."""
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0.:
        s = math.sqrt(t + 1.) * 2.
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, .25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1. + m[0, 0] - m[1, 1] - m[2, 2]) * 2.
        q = [.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1. + m[1, 1] - m[0, 0] - m[2, 2]) * 2.
        q = [(m[0, 1] + m[1, 0]) / s, .25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1. + m[2, 2] - m[0, 0] - m[1, 1]) * 2.
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, .25 * s, (m[1, 0] - m[0, 1]) / s]
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])   # written out: see _hyp
    q = [c / n for c in q]
    if q[3] < 0. or (q[3] == 0. and next((c for c in q if c != 0.), 1.) < 0.):
        q = [-c for c in q]
    return q


def _rot(v, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _wrap(x):
    while x > math.pi:
        x -= math.tau
    while x < -math.pi:
        x += math.tau
    return x


def _g(v):
    """glTF vector -> solver space."""
    return (float(v[0]), -float(v[2]), float(v[1]))


# body -----------------------------------------------------------------------------------------------------------------
class Body:
    pass


def read_body(glb, spec=None, bone_map=None):
    """Parse a GLB and measure the body. bone_map = {spec bone: joint name in this file} for armatures with other names."""
    spec = load_spec(spec or 'base_v1')
    try:
        doc, binary = gltf.parse(bytes(glb))
    except Exception as e:  # noqa: BLE001 - any parse failure is the same plain refusal
        raise LocomotionError('not_glb', 'this is not a readable GLB file (%s)' % e)
    prims = lbs.primitives(doc, binary)
    skinned = [r for r in prims if r['joints'] is not None]
    if not skinned or not doc.get('skins'):
        raise LocomotionError('no_skin', 'this file has no skinned mesh: a character needs a mesh bound to an armature '
                              'before it can be given a run and a walk')
    b = Body()
    b.spec, b.doc, b.binary = spec, doc, binary
    b.skin = skinned[0]['skin']
    skinned = [r for r in skinned if r['skin'] == b.skin]
    b.joints = list(doc['skins'][b.skin]['joints'])
    by_name = {}
    for j in b.joints:
        by_name.setdefault(doc['nodes'][j].get('name'), j)
    bone_map = dict(bone_map or {})
    need, opt = list(spec['bones']['required']), list(spec['bones']['optional'])
    b.node_of, missing = {}, []
    for bone in need + opt:
        nm = bone_map.get(bone, bone)
        if nm in by_name:
            b.node_of[bone] = by_name[nm]
        elif bone in need:
            missing.append(nm)
    if missing:
        raise LocomotionError('missing_bones', 'the armature has no joint named %s. The base needs: %s. If this armature '
                              'uses other names, pass a bone map (base name -> name in the file).' % (', '.join(missing), ', '.join(need)))
    b.parents = gltf.node_parents(doc)
    for bone, par in spec['bones']['hierarchy'].items():
        if bone in b.node_of and par in b.node_of:
            n = b.parents.get(b.node_of[bone])
            while n is not None and n != b.node_of[par]:
                n = b.parents.get(n)
            if n is None:
                raise LocomotionError('hierarchy', 'the joint %s is not under %s in this armature; the base needs %s to '
                                      'follow %s' % (bone_map.get(bone, bone), bone_map.get(par, par), bone, par))
    b.world = lbs.world_matrices(doc)
    for j in b.joints:
        m = b.world[j][:3, :3]
        if np.abs(m.T @ m - np.eye(3)).max() > 1e-3 or np.linalg.det(m) < 0.:
            raise LocomotionError('scale', 'the joint %s is scaled or sheared in the rest pose; apply the scale to the '
                                  'armature and the mesh before baking (every joint must be at unit scale)' % doc['nodes'][j].get('name'))
    b.rw = [w[:3, :3] for w in b.world]
    b.jp = {bone: b.world[n][:3, 3].copy() for bone, n in b.node_of.items()}
    b.ground = b.node_of.get('root', b.node_of['pelvis'])
    ibm = lbs.inverse_binds(doc, binary, b.skin)
    b.ibm = ibm if ibm is not None else np.repeat(np.eye(4)[None], len(b.joints), axis=0)
    k = max(r['joints'].shape[1] for r in skinned)
    pos, jj, ww, used, faces, off = [], [], [], [], [], 0
    for r in skinned:
        n = len(r['positions'])
        pad = k - r['joints'].shape[1]
        pos.append(r['positions'])
        jj.append(np.pad(r['joints'], ((0, 0), (0, pad))))
        ww.append(np.pad(r['weights'], ((0, 0), (0, pad))))
        used.append(r['used'])
        mode = doc['meshes'][r['mesh']]['primitives'][r['prim']].get('mode', 4)
        if mode == 4:
            idx = r['indices'] if r['indices'] is not None else np.arange(n)
            faces.append(idx[:len(idx) // 3 * 3].reshape(-1, 3) + off)
        off += n
    b.bind = np.concatenate(pos)
    b.J = np.concatenate(jj)
    b.W = np.concatenate(ww)
    tot = b.W.sum(axis=1, keepdims=True)
    b.W = b.W / np.where(tot > 0., tot, 1.)
    b.used = np.concatenate(used)
    b.F = np.concatenate(faces) if faces else np.zeros((0, 3), dtype=np.int64)
    if b.used.sum() < 8:
        raise LocomotionError('no_mesh', 'the skinned mesh has almost no vertices; there is no body to measure')
    # weight of every listed bone per vertex; a joint that is not listed counts for its nearest listed ancestor
    spec_node = {n: bone for bone, n in b.node_of.items()}
    owner = []
    for j in b.joints:
        n = j
        while n is not None and n not in spec_node:
            n = b.parents.get(n)
        owner.append(spec_node.get(n))
    b.Wb = {bone: np.zeros(len(b.bind)) for bone in b.node_of}
    for c in range(b.J.shape[1]):
        for ji in np.unique(b.J[:, c]):
            o = owner[int(ji)] if int(ji) < len(owner) else None
            if o is not None:
                sel = b.J[:, c] == ji
                b.Wb[o][sel] += b.W[sel, c]
    b.rest = pose(b, {})
    _measure(b)
    # pieces that touch at rest must stay together on every key: the rig kit's own seam check (generator joins when the
    # file carries its topology, else rest contacts between mesh pieces), so the bake and the rig gate agree
    b.prims, b.skinned_at = prims, [i for i, r in enumerate(prims) if r['joints'] is not None and r['skin'] == b.skin]
    rig_id = next((n['name'][4:] for n in doc['nodes'] if str(n.get('name', '')).startswith('rig_')), '')
    try:
        b.seam = seams.prepare(doc, binary, {'body': [r for r in prims if r['joints'] is not None], 'prims': prims},
                               types.SimpleNamespace(id=rig_id), spec['limits']['seam_gap_max_m'])
    except Exception:  # noqa: BLE001 - a mesh the seam check cannot read has no seams to measure
        b.seam = None
    return b


def seam_gap(b, V):
    """-> (worst gap in metres between pieces that touch at rest, where) for skinned positions V."""
    if not b.seam:
        return 0., None
    posed, off = [r['positions'] for r in b.prims], 0
    for i in b.skinned_at:
        n = len(b.prims[i]['positions'])
        posed[i] = V[off:off + n]
        off += n
    g, where = seams.gaps(b.seam, posed)
    return float(g), where


def pose(b, overrides):
    """Skinned world positions (N, 3) for per-node TRS overrides."""
    world = lbs.world_matrices(b.doc, overrides) if overrides else b.world
    mats = np.stack([world[j] for j in b.joints]) @ b.ibm
    return lbs.skin(b.bind, b.J, b.W, mats)


def _measure(b):
    spec, L = b.spec, b.spec['limits']
    ms = spec['measurements']
    P, used = b.rest, b.used
    floor = float(P[used, 1].min())
    H = float(P[used, 1].max()) - floor
    if not ms['height_m']['min'] <= H <= ms['height_m']['max']:
        raise LocomotionError('height', 'the body is %.2f m tall; the base handles %.1f to %.1f m (is the file in metres?)'
                              % (H, ms['height_m']['min'], ms['height_m']['max']))
    if b.jp['thigh_l'][0] <= b.jp['thigh_r'][0]:
        raise LocomotionError('mirrored', 'thigh_l is not on +X of thigh_r: the base expects the character to face +Z with '
                              'its left side on +X')
    b.boot, M, m = {}, {}, {}
    for s, sg in SIDES:
        sel = used & (b.Wb['foot_' + s] >= .5)
        if int(sel.sum()) < ms['boot_outline']['min_vertices']:
            raise LocomotionError('no_boot', 'only %d vertices follow the joint foot_%s; the bake needs the boot (or foot) '
                                  'geometry to plant it on the ground' % (int(sel.sum()), s))
        b.boot[s] = np.nonzero(sel)[0]
    hips = [float(b.jp['thigh_' + s][1] - P[b.boot[s], 1].min()) for s, _ in SIDES]
    hip0 = sum(hips) / 2.
    if hip0 < ms['hip_height_m']['min_fraction_of_height'] * H:
        raise LocomotionError('no_hip_height', 'the hip joints (thigh_l, thigh_r) are %.1f cm above the soles, %.0f %% of the '
                              'body height (%.0f cm). A run and a walk need legs: the hips must be at least %.0f %% of the '
                              'height above the ground.' % (hip0 * 100., 100. * hip0 / H, H * 100.,
                                                            100. * ms['hip_height_m']['min_fraction_of_height']))
    clear = min(L['clear_m'], L['clear_max_fraction_of_hip'] * hip0)
    for (s, sg), hip_s in zip(SIDES, hips):
        hip, knee, ank = (_g(b.jp[n + s]) for n in ('thigh_', 'shin_', 'foot_'))
        d1 = (knee[1] - hip[1], knee[2] - hip[2])
        d2 = (ank[1] - knee[1], ank[2] - knee[2])
        l1, l2 = _hyp(*d1), _hyp(*d2)
        for nm, ln in (('thigh', l1), ('shin', l2)):
            if ln < ms[nm + '_len_m']['min_fraction_of_hip'] * hip0:
                raise LocomotionError('short_leg_segment', 'the %s_%s is %.1f cm long in the fore-aft plane, under %.0f %% of '
                                      'the hip height (%.0f cm); the leg cannot be solved with a knee'
                                      % (nm, s, ln * 100., 100. * ms[nm + '_len_m']['min_fraction_of_hip'], hip0 * 100.))
        idx = b.boot[s]
        B = P[idx]
        low = float(B[:, 1].min())
        sole = B[B[:, 1] < low + clear]
        toe, heel = float(-sole[:, 2].max()), float(-sole[:, 2].min())          # solver y: toe is the most forward
        rigid = used & (b.Wb['foot_' + s] > .99)
        if int(rigid.sum()) < ms['boot_outline']['min_vertices']:
            rigid = np.zeros(len(P), dtype=bool)
            rigid[idx] = True
        O = P[rigid]
        M[s] = {'l1': l1, 'a1': math.atan2(d1[1], d1[0]), 'l2': l2, 'a2': math.atan2(d2[1], d2[0]),
                'toe': (ank[1] - toe, ank[2] - low), 'heel': (ank[1] - heel, ank[2] - low), 'hip': hip_s,
                'outline': np.stack([-O[:, 2] - ank[1], O[:, 1] - ank[2]], axis=1)}
        if heel - toe < ms['boot_outline']['min_length_fraction_of_hip'] * hip0:
            raise LocomotionError('no_boot_length', 'the sole of boot %s is %.1f cm long, under %.0f %% of the hip height; '
                                  'there is no heel and toe to roll over' % (s, (heel - toe) * 100., 100. * ms['boot_outline']['min_length_fraction_of_hip']))
        if M[s]['toe'][0] <= -M[s]['heel'][0]:
            raise LocomotionError('facing', 'boot %s reaches %.1f cm behind the ankle and %.1f cm ahead of it: the character '
                                  'seems to face -Z. The base expects it to face +Z.' % (s, -M[s]['heel'][0] * 100., M[s]['toe'][0] * 100.))
        gap = float((sg * B[:, 0]).min())
        if gap < L['boot_gap_min_m']:
            raise LocomotionError('legs_cross', 'the %s boot reaches %.1f cm across the centre line in the rest pose: the legs '
                                  'cross (or the body is not centred on x = 0). The boots must stay on their own side.'
                                  % ('left' if s == 'l' else 'right', -gap * 100.))
        m['boot_gap_' + s + '_m'] = gap
        m['sole_' + s] = {'toe_ahead_of_ankle_m': M[s]['toe'][0], 'heel_behind_ankle_m': -M[s]['heel'][0],
                          'ankle_height_m': M[s]['toe'][1], 'outline_vertices': int(len(O))}
        cx = float(B[:, 0].mean())
        rf = b.rw[b.node_of['foot_' + s]]
        jf = b.jp['foot_' + s]
        m['_sole_' + s] = {'toe': (rf.T @ (np.array([cx, low, -toe]) - jf)).tolist(),
                           'heel': (rf.T @ (np.array([cx, low, -heel]) - jf)).tolist()}
        pts = sole[np.lexsort((sole[:, 0], sole[:, 2]))]         # the sole's own vertices, in the foot joint's frame:
        pts = pts[np.unique(np.linspace(0, len(pts) - 1, min(len(pts), 24)).round().astype(int))]   # what a player can
        b.__dict__.setdefault('sole_points', {})[s] = [(rf.T @ (p - jf)).tolist() for p in pts]       # follow in play
        up = b.jp['forearm_' + s] - b.jp['upper_arm_' + s]
        ul = float(np.linalg.norm(up))
        if 'hand_' + s in b.jp:
            fl = float(np.linalg.norm(b.jp['hand_' + s] - b.jp['forearm_' + s]))
        else:
            fv = P[used & (b.Wb['forearm_' + s] >= .5)]
            fl = float(np.linalg.norm(fv - b.jp['forearm_' + s], axis=1).max()) if len(fv) else 0.
        if ul < 1e-4 or fl < 1e-4:
            raise LocomotionError('no_arm', 'the %s arm has no length (upper arm %.1f cm, forearm %.1f cm)'
                                  % ('left' if s == 'l' else 'right', ul * 100., fl * 100.))
        m['upper_arm_%s_m' % s], m['forearm_%s_m' % s] = ul, fl
        m['arm_rest_abduction_%s_deg' % s] = math.degrees(math.atan2(sg * up[0], -up[1]))
        m['thigh_%s_m' % s], m['shin_%s_m' % s] = l1, l2
    mis = max(abs(M['l'][k] - M['r'][k]) for k in ('l1', 'l2', 'hip'))
    if mis > ms['left_right_mismatch_m']['max_fraction_of_hip'] * hip0:
        raise LocomotionError('asymmetric_legs', 'the left and right leg differ by %.1f cm (limit %.0f %% of the hip height); '
                              'the base bakes one gait for both legs' % (mis * 100., 100. * ms['left_right_mismatch_m']['max_fraction_of_hip']))
    b.M, b.hip0, b.H, b.floor, b.clear = M, hip0, H, floor, clear
    band = ms['arm_rest_abduction_deg']
    b.arm_fix, b.arm_fix_all, b.arm_q = {}, {}, {}

    def rz(phi):                                                    # about +Z (fore-aft axis), glTF space
        c, sn = math.cos(phi), math.sin(phi)
        return np.array([[c, -sn, 0.], [sn, c, 0.], [0., 0., 1.]])
    for s, sg in SIDES:
        a = m['arm_rest_abduction_%s_deg' % s]
        if not band['band'][0] <= a <= band['band'][1]:
            b.arm_fix['upper_arm_' + s] = rz(sg * (band['target_when_outside'] - a) * RAD)
            for bone in ('upper_arm_', 'forearm_'):                 # the turn belongs to the rest pose: the whole arm has it
                b.arm_fix_all[bone + s] = b.arm_fix['upper_arm_' + s]
            a = band['target_when_outside']
        # the elbow turns are written for an arm hanging at the reference angle; on an arm that hangs further out (or
        # in) the same turns are made about this arm's own axes, so a bend stays a bend and does not become a twist
        b.arm_q['forearm_' + s] = rz(sg * (a - b.spec['reference']['arm_rest_abduction_deg']) * RAD)
    limb = sum(b.Wb[n + s] for n in ('forearm_', 'shin_', 'foot_') for s in 'lr')
    for s in 'lr':
        if 'hand_' + s in b.Wb:
            limb = limb + b.Wb['hand_' + s]
    b.limb = np.nonzero(used & (limb >= .9))[0]
    names = sorted(b.Wb)
    b.limb_owner = [names[i] for i in np.argmax(np.stack([b.Wb[n][b.limb] for n in names]), axis=0)] if len(b.limb) else []
    tw = b.Wb['pelvis'] + b.Wb['spine']
    b.torso = b.F[(tw[b.F] >= .5).all(axis=1)] if len(b.F) else b.F
    b.rest_inside = _inside(b, P)
    m.update({'height_m': H, 'hip_height_m': hip0, 'hip_height_per_height': hip0 / H,
              'leg_len_m': (M['l']['l1'] + M['l']['l2'] + M['r']['l1'] + M['r']['l2']) / 2.,
              'hip_width_m': float(b.jp['thigh_l'][0] - b.jp['thigh_r'][0]),
              'torso_len_m': float(np.linalg.norm(b.jp['head'] - b.jp['pelvis'])),
              'left_right_mismatch_m': mis, 'clear_m': clear, 'vertices': int(used.sum()), 'triangles': int(len(b.F)),
              'joints': len(b.joints), 'extra_joints': len(b.joints) - len(b.node_of),
              'arm_rest_turned_to_deg': {k[-1]: band['target_when_outside'] for k in b.arm_fix} or None,
              'grounding_joint': b.doc['nodes'][b.ground].get('name')})
    b.sole = {s: m.pop('_sole_' + s) for s in 'lr'}
    b.measured = _round(m)


def _round(x, n=4):
    if isinstance(x, dict):
        return {k: _round(v, n) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v, n) for v in x]
    if isinstance(x, (float, np.floating)):
        return round(float(x), n)
    if isinstance(x, np.integer):
        return int(x)
    return x


def _inside(b, V):
    """Which limb points are inside the torso surface (generalised winding number > 0.5)."""
    if not len(b.limb) or not len(b.torso):
        return np.zeros(len(b.limb), dtype=bool)
    from ..nbchars import meshcheck
    out = np.zeros(len(b.limb), dtype=bool)
    step = max(1, 400000 // max(1, len(b.torso)))
    for i in range(0, len(b.limb), step):
        out[i:i + step] = meshcheck.inside(V, b.torso, V[b.limb[i:i + step]])
    return out


# solver ---------------------------------------------------------------------------------------------------------------
def stride(b, cyc):
    """Ground speed of the cycle at playback rate 1 for this body (scales with the leg)."""
    return cyc['stride_mps'] * cyc.get('stride_scale', 1.) * b.hip0 / b.spec['reference']['hip_height_m']


def _ank_z(M, psi):
    c, s = math.cos(psi), math.sin(psi)
    return -float((M['outline'][:, 0] * s + M['outline'][:, 1] * c).min())


def _planted(b, M, cyc, p):
    """Ankle (y, height over the ground) and foot pitch (rad) of a planted foot at integer phase p."""
    fps = float(b.spec['timing']['fps'])
    k = cyc.get('stride_scale', 1.)                             # a shorter step for legs that cannot reach the written one
    ref = (cyc['toe0'] + cyc['stride_mps'] / b.spec['reference']['hip_height_m'] / fps * p) * k * b.hip0
    psi = cyc['pitch_deg'][p] * RAD
    if psi >= 0.:
        off = _rot(M['toe'], psi)                               # pivot on the toe
        return (ref + off[0], _ank_z(M, psi)), psi
    heel_y = ref + (M['toe'][0] - M['heel'][0])
    off = _rot(M['heel'], psi)                                  # pivot on the heel
    return (heel_y + off[0], _ank_z(M, psi)), psi


def _hyp(x, y):
    """sqrt(x^2 + y^2) from correctly rounded operations only. math.hypot and sum() over floats give answers one
    unit in the last place apart between Python versions (3.9 vs 3.14 measured), and that reaches the file's bytes."""
    return math.sqrt(x * x + y * y)


def _solve(M, target):
    """Two-bone solve, knee forward. target: ankle relative to the hip (y, z). -> thigh angle (world), knee flexion."""
    D = _hyp(*target)
    reach = (M['l1'] + M['l2']) * .999
    if D > reach:
        target = (target[0] * reach / D, target[1] * reach / D)
        D = reach
    g = math.atan2(target[1], target[0])
    c = (M['l1'] ** 2 + D * D - M['l2'] ** 2) / (2. * M['l1'] * D)
    t1 = g - math.acos(max(-1., min(1., c)))
    knee = (M['l1'] * math.cos(t1), M['l1'] * math.sin(t1))
    t2 = math.atan2(target[1] - knee[1], target[0] - knee[0])
    th = _wrap(t1 - M['a1'])
    return th, _wrap(t2 - M['a2']) - th


def _euler(b, cyc, key):
    """Local Euler turns per bone (solver space, rest = identity) and the authored hip height when in flight."""
    keys, step = b.spec['timing']['keys'], b.spec['timing']['step_keys']
    hip0 = b.hip0
    phase = {'l': key % keys, 'r': (key + step) % keys}
    planted = {s: _planted(b, b.M[s], cyc, p) for s, p in phase.items() if p <= cyc['stance']}
    hip = cyc['hip'][key % step] * hip0
    for s, (ank, _psi) in planted.items():                      # never ask a planted leg to reach further than it can
        reach = (b.M[s]['l1'] + b.M[s]['l2']) * .992
        hip = min(hip, ank[1] + math.sqrt(max(1e-6, reach * reach - ank[0] * ank[0])))
    lean_p, lean_s = cyc['lean_deg'][0] * RAD, cyc['lean_deg'][1] * RAD
    w = math.cos(math.tau * (phase['l'] - cyc['arm_peak_key']) / keys)   # +1 when the left arm is furthest forward
    yaw_p = cyc['yaw_deg'][0] * RAD * w
    yaw_s = -cyc['yaw_deg'][1] * RAD * w
    eul = {'pelvis': (lean_p, 0., yaw_p), 'spine': (lean_s, 0., yaw_s - yaw_p),
           'head': (-.80 * (lean_p + lean_s), 0., -yaw_s)}
    for s, sg in SIDES:
        p, M = phase[s], b.M[s]
        if s in planted:
            ank, psi = planted[s]
            th, kn = _solve(M, (ank[0], ank[1] - hip))
        else:
            y, clr, psi = cyc['swing'][str(p)]
            psi *= RAD
            if cyc['swing_mode'] == 'angles':
                th, kn = y * RAD, clr * RAD
            else:
                th, kn = _solve(M, (y * cyc.get('stride_scale', 1.) * hip0, clr * hip0 + _ank_z(M, psi) - hip))
        eul['thigh_' + s] = (th - lean_p, 0., 0.)
        eul['shin_' + s] = (kn, 0., 0.)
        # a swinging foot may follow its shin more closely (fit dial seam_gap); a planted foot keeps its pitch exactly
        eul['foot_' + s] = ((psi - th - kn) * (1. if s in planted else cyc.get('ankle_swing_scale', 1.)), 0., 0.)
        ws = w if s == 'l' else -w
        bias, amp, bend, bsw = (v * RAD for v in cyc['arm_deg'])
        inn, across = (v * RAD for v in cyc['arm_in_deg'])
        eul['upper_arm_' + s] = (bias - amp * ws - (lean_p + lean_s), sg * inn, -sg * across)   # world swing: the lean is taken out
        eul['forearm_' + s] = (bend - bsw * ws, 0., 0.)
    return eul, (None if planted else hip)


def _overrides(b, eul):
    """Node rotation overrides (glTF [x, y, z, w]) and the world turn of every listed bone for one key."""
    hier = b.spec['bones']['hierarchy']
    A, D = {}, {}
    for bone in ORDER:
        m = C @ _mat(_qe(*eul.get(bone, (0., 0., 0.)))) @ C.T
        if bone in b.arm_q:
            m = b.arm_q[bone] @ m @ b.arm_q[bone].T
        A[bone] = A[hier[bone]] @ m if hier.get(bone) in A else m
        D[bone] = A[bone] @ b.arm_fix_all[bone] if bone in b.arm_fix_all else A[bone]
    dn, wr, ov = {}, {}, {}
    spec_node = {n: bone for bone, n in b.node_of.items()}

    def turn(n):
        if n not in dn:
            p = b.parents.get(n)
            bone = spec_node.get(n)
            dn[n] = D[bone] if bone in D else (turn(p) if p is not None else np.eye(3))
            wr[n] = dn[n] @ b.rw[n]
        return dn[n]
    for bone in ORDER:
        n = b.node_of[bone]
        turn(n)
        p = b.parents.get(n)
        if p is None:
            local = wr[n]
        else:
            turn(p)
            local = np.linalg.inv(wr[p]) @ wr[n]
        ov[n] = {'rotation': _quat(local)}
    return ov, D


def frames_baked(b, cyc):
    """Every key of a cycle on this body: overrides (rotations + grounding translation), grounded vertices, joints."""
    out = []
    g = b.ground
    rest_t = np.array(b.doc['nodes'][g].get('translation', [0., 0., 0.]), dtype=np.float64)
    pg = b.parents.get(g)
    inv_p = np.linalg.inv(b.rw[pg]) if pg is not None else np.eye(3)
    boots = np.concatenate([b.boot['l'], b.boot['r']])
    for key in range(b.spec['timing']['keys']):
        eul, fly = _euler(b, cyc, key)
        ov, D = _overrides(b, eul)
        ov.setdefault(g, {})['translation'] = rest_t
        world = lbs.world_matrices(b.doc, ov)
        V = lbs.skin(b.bind, b.J, b.W, np.stack([world[j] for j in b.joints]) @ b.ibm)
        lift = 0.
        if fly is not None:                                     # flight: the authored hip height over the grounded pose
            hipy = (world[b.node_of['thigh_l']][1, 3] + world[b.node_of['thigh_r']][1, 3]) / 2.
            lift = max(0., fly - (hipy - float(V[boots, 1].min())))
        dy = lift + b.floor - float(V[b.used, 1].min())            # the lowest vertex on the body's own floor
        ov[g]['translation'] = rest_t + inv_p @ np.array([0., dy, 0.])
        out.append({'ov': ov, 'V': V + np.array([0., dy, 0.]), 'dp': D['pelvis'],
                    'jw': {bone: world[n][:3, 3] + np.array([0., dy, 0.]) for bone, n in b.node_of.items()}})
    return out


def frames_file(b, clip):
    """Every key of a clip the file already carries (for check())."""
    out = []
    rp = b.rw[b.node_of['pelvis']]
    for key in range(b.spec['timing']['keys']):
        ov = lbs.clip_overrides(b.doc, b.binary, clip, key)
        world = lbs.world_matrices(b.doc, ov)
        V = lbs.skin(b.bind, b.J, b.W, np.stack([world[j] for j in b.joints]) @ b.ibm)
        out.append({'ov': ov, 'V': V, 'dp': world[b.node_of['pelvis']][:3, :3] @ rp.T,
                    'jw': {bone: world[n][:3, 3] for bone, n in b.node_of.items()}})
    return out


# metrics --------------------------------------------------------------------------------------------------------------
def metrics(b, frames, clip, stride_mps):
    """The numbers of one cycle (glTF space: y up, z forward)."""
    L = b.spec['limits']
    fps = float(b.spec['timing']['fps'])
    keys, step = b.spec['timing']['keys'], b.spec['timing']['step_keys']
    clear = b.clear
    cl = [{s: float(f['V'][b.boot[s], 1].min()) - b.floor for s in 'lr'} for f in frames]
    flight = [k for k in range(keys) if min(cl[k].values()) > clear]
    per_step = min(sum(1 for k in flight if k // step == st) for st in (0, 1))
    speed = L[clip]['test_speed_mps'] * stride_mps / b.spec['cycles'][clip]['stride_mps']     # the same gait on this leg
    rate = speed / stride_mps
    slip, pairs = 0., 0
    for s in 'lr':
        idx = b.boot[s]
        for k in range(keys):
            n = (k + 1) % keys
            if cl[k][s] > clear or cl[n][s] > clear:
                continue
            down = (frames[k]['V'][idx, 1] < b.floor + clear) & (frames[n]['V'][idx, 1] < b.floor + clear)   # on the ground at both keys
            if not down.any():
                continue
            back = -float((frames[n]['V'][idx, 2][down] - frames[k]['V'][idx, 2][down]).mean())
            slip = max(slip, abs(back * fps * rate - speed))
            pairs += 1
    py = [float(f['jw']['pelvis'][1]) for f in frames]
    hd = [float(f['jw']['head'][1] - f['jw']['pelvis'][1]) for f in frames]
    lean = [math.degrees(math.atan2(f['jw']['head'][2] - f['jw']['pelvis'][2], f['jw']['head'][1] - f['jw']['pelvis'][1])) for f in frames]
    rest_c = {s: float(b.rest[b.boot[s], 0].mean() - b.jp['thigh_' + s][0]) for s in 'lr'}
    dev, gap, mid, pierce, who = 0., 1e9, 0., 0, set()
    seam = (0., None, None)
    for k, f in enumerate(frames):
        g, where = seam_gap(b, f['V'])
        if g > seam[0]:
            seam = (g, where, k)
        cx = {}
        for s, sg in SIDES:
            B = f['V'][b.boot[s]]
            c = B.mean(axis=0)
            cx[s] = float(c[0])
            gap = min(gap, float((sg * B[:, 0]).min()))
            dev = max(dev, abs(float((f['dp'].T @ (c - f['jw']['thigh_' + s]))[0]) - rest_c[s]))
        mid = max(mid, abs((cx['l'] + cx['r']) / 2.))
        ins = _inside(b, f['V']) & ~b.rest_inside
        pierce = max(pierce, int(ins.sum()))
        who.update(b.limb_owner[i] for i in np.nonzero(ins)[0])
    return {'flight_keys': flight, 'flight_keys_per_step': per_step,
            'bounce_hip': round((max(py) - min(py)) / b.hip0, 4), 'bounce_h': round((max(py) - min(py)) / b.H, 4),
            'lean_deg': round(math.fsum(lean) / len(lean), 2), 'slip_mps': round(slip, 3), 'slip_pairs': pairs,
            'head_bob_h': round((max(hd) - min(hd)) / b.H, 4), 'stride_mps': round(stride_mps, 4),
            'boot_gap_min_m': round(gap, 4), 'leg_plane_dev_m': round(dev, 4), 'leg_mid_off_centre_m': round(mid, 4),
            'limb_in_torso_vertices': pierce, 'limb_in_torso_bones': sorted(who),
            'seam_gap_m': round(seam[0], 4), 'seam_gap_at': ('%s at key %d' % (seam[1], seam[2])) if seam[1] else None}


def verdict(spec, clip, m):
    """[(code, plain sentence)] for every limit the cycle breaks."""
    L, G = spec['limits'][clip], spec['limits']
    bad = []
    if 'flight_keys_per_step_min' in L and m['flight_keys_per_step'] < L['flight_keys_per_step_min']:
        bad.append(('flight', 'the %s leaves the ground for %d keys per step (needs at least %d: a run has a flight phase)'
                    % (clip, m['flight_keys_per_step'], L['flight_keys_per_step_min'])))
    if 'flight_keys_per_step_max' in L and len(m['flight_keys']) > L['flight_keys_per_step_max']:
        bad.append(('flight', 'the %s has both boots off the ground at %d keys (a walk always keeps one foot down)'
                    % (clip, len(m['flight_keys']))))
    lo, hi = L['bounce_hip']
    if not lo <= m['bounce_hip'] <= hi:
        bad.append(('bounce_high' if m['bounce_hip'] > hi else 'bounce_low', 'the hips travel %.1f %% of the standing hip height up and down in the %s (allowed %.1f to %.1f %%)'
                    % (100. * m['bounce_hip'], clip, 100. * lo, 100. * hi)))
    lo, hi = L['lean_deg']
    if m['lean_deg'] > hi:
        bad.append(('lean_high', 'the body leans %.1f degrees forward in the %s (allowed %.0f to %.0f)' % (m['lean_deg'], clip, lo, hi)))
    if m['lean_deg'] < lo:
        bad.append(('lean_low', 'the body leans %.1f degrees forward in the %s (allowed %.0f to %.0f)' % (m['lean_deg'], clip, lo, hi)))
    if m['slip_pairs'] == 0:
        bad.append(('no_contact', 'no boot stays on the ground from one key to the next in the %s, so there is no planted '
                    'foot to measure' % clip))
    if m['slip_mps'] > L['slip_mps_max']:
        bad.append(('slip', 'the planted boot slides %.2f m/s on the ground in the %s (limit %.2f m/s)' % (m['slip_mps'], clip, L['slip_mps_max'])))
    if m['boot_gap_min_m'] <= G['boot_gap_min_m']:
        bad.append(('boots_cross', 'a boot reaches the centre line in the %s (%.1f cm past it at the closest key); the boots must '
                    'stay on their own side' % (clip, -100. * m['boot_gap_min_m'])))
    if m['seam_gap_m'] > G['seam_gap_max_m']:
        bad.append(('seam_gap', 'two parts of the mesh that touch at rest come %.1f mm apart in the %s (%s; limit %.1f mm)%s'
                    % (1000. * m['seam_gap_m'], clip, m['seam_gap_at'], 1000. * G['seam_gap_max_m'],
                       '. Parts that only rest against each other (a hand on the hip) count as joined: move them apart '
                       'in the rest pose' if str(m['seam_gap_at']).startswith('piece') else '')))
    if m['leg_plane_dev_m'] > G['leg_plane_dev_max_m']:
        bad.append(('leg_plane', 'a leg leaves its fore-aft plane by %.1f cm in the %s (limit %.1f cm)' % (100. * m['leg_plane_dev_m'], clip, 100. * G['leg_plane_dev_max_m'])))
    if m['leg_mid_off_centre_m'] > G['leg_mid_off_centre_max_m']:
        bad.append(('off_centre', 'the legs sit %.1f cm off the centre line in the %s (limit %.1f cm)' % (100. * m['leg_mid_off_centre_m'], clip, 100. * G['leg_mid_off_centre_max_m'])))
    if m['limb_in_torso_vertices'] > G['limb_in_torso_vertices_max']:
        legs = [n for n in m['limb_in_torso_bones'] if n.startswith(('shin', 'foot'))]
        arms = [n for n in m['limb_in_torso_bones'] if n not in legs]
        bad.append(('limb_in_torso' if arms else 'leg_in_torso', '%d vertices of %s pass through the torso in the %s%s'
                    % (m['limb_in_torso_vertices'], ', '.join(m['limb_in_torso_bones']), clip,
                       '' if arms else ' (the torso here is every surface that follows the pelvis or spine: a robe, skirt '
                       'or long coat that hangs over the legs counts, and the base has no cloth that moves with the legs)')))
    return bad


# fit + bake -----------------------------------------------------------------------------------------------------------
def _dialled(cyc, st, dials):
    c = copy.deepcopy(cyc)
    c['yaw_deg'] = [c['yaw_deg'][0] * dials['boots_cross']['scale'][st['boots_cross']], c['yaw_deg'][1]]
    k = dials['lean_high']['scale'][st['lean_high']] * dials['lean_low']['scale'][st['lean_low']]
    c['lean_deg'] = [v * k for v in c['lean_deg']]
    c['arm_in_deg'] = [c['arm_in_deg'][0] - dials['limb_in_torso']['add_deg'][st['limb_in_torso']], c['arm_in_deg'][1]]
    c['stride_scale'] = c.get('stride_scale', 1.) * dials['bounce_high']['scale'][st['bounce_high']]
    c['ankle_swing_scale'] = c.get('ankle_swing_scale', 1.) * dials['seam_gap']['scale'][st['seam_gap']]
    return c


def fit(b, clip, tuning=None):
    """Bake one clip for a measured body: the cycle as written, then one dial step per failing metric that has a dial.
    -> (frames, record). record['fail'] is empty when every metric passes."""
    dials = b.spec['fit']['dials']
    base = cycle(b.spec, clip, tuning)
    st = {k: 0 for k in dials}
    tried = []
    while True:
        cyc = _dialled(base, st, dials)
        fr = frames_baked(b, cyc)
        m = metrics(b, fr, clip, stride(b, cyc))
        bad = verdict(b.spec, clip, m)
        tried.append({'dials': dict(st), 'fail': [c for c, _ in bad]})
        move = next((c for c, _ in bad if c in dials and st[c] + 1 < len(dials[c].get('scale', dials[c].get('add_deg')))), None)
        if not bad or move is None or len(tried) > 24:
            break
        st[move] += 1
    rec = {'metrics': m, 'fail': [c for c, _ in bad], 'why': [t for _, t in bad], 'tried': tried,
           'cycle_used': {'lean_deg': _round(cyc['lean_deg'], 3), 'yaw_deg': _round(cyc['yaw_deg'], 3),
                          'arm_in_deg': _round(cyc['arm_in_deg'], 3), 'stride_scale': _round(cyc['stride_scale'], 3),
                          'ankle_swing_scale': _round(cyc['ankle_swing_scale'], 3)},
           'dials_moved': {k: v for k, v in st.items() if v}}
    return fr, rec


def block(b, source_sha, recs):
    t, bl, ref = b.spec['timing'], b.spec['blend'], b.spec['reference']['hip_height_m']
    k = b.hip0 / ref
    return _round({'format': FORMAT, 'base': b.spec['id'], 'source_sha256': source_sha, 'fps': t['fps'], 'cycle_keys': t['cycle_keys'],
                   'hip_height_m': b.hip0,
                   'walk': {'stride_mps': recs['walk']['metrics']['stride_mps']},
                   'run': {'stride_mps': recs['run']['metrics']['stride_mps'], 'flight_keys': recs['run']['metrics']['flight_keys'], 'enter_mps': bl['enter_mps'] * k, 'exit_mps': bl['exit_mps'] * k},
                   'sole': b.sole}, 5)


def bake(glb, spec=None, tuning=None, bone_map=None, keep_legacy=False):
    """GLB bytes -> (GLB bytes with baked run + walk and the locomotion block, report). Refuses with LocomotionError.
    Everything else in the file (mesh, materials, other clips) is kept. keep_legacy: an existing run / walk stays in
    the file as run_legacy / walk_legacy instead of being replaced."""
    glb = bytes(glb)
    b = read_body(glb, spec, bone_map)
    report = {'format': FORMAT, 'base': b.spec['id'], 'source_sha256': hashlib.sha256(glb).hexdigest(), 'ok': False,
              'measurements': b.measured, 'clips': {}}
    frames = {}
    for clip in CLIPS:
        frames[clip], report['clips'][clip] = fit(b, clip, tuning)
    bad = [t for clip in CLIPS for t in report['clips'][clip]['why']]
    if bad:
        raise LocomotionError('clip_refused', 'no run and walk were written for this body: ' + '; '.join(bad) + '.', report)
    report['block'] = block(b, report['source_sha256'], report['clips'])
    doc = copy.deepcopy(b.doc)
    keep = []
    for a in doc.get('animations', []):
        if a.get('name') in CLIPS:
            if not keep_legacy:
                continue
            a = dict(a, name=a['name'] + '_legacy')
        elif keep_legacy and a.get('name') in [c + '_legacy' for c in CLIPS]:
            continue
        keep.append(a)
    doc['animations'] = keep
    doc, binary = gltfedit.compact(doc, b.binary)
    keep = list(doc.get('animations', []))                    # compact() renumbers accessors: take the clips from its copy
    bld = gltfedit.Builder(doc, binary)
    fps = float(b.spec['timing']['fps'])
    keys = b.spec['timing']['keys']
    order = list(range(keys)) + ([0] if b.spec['timing'].get('closing_key') else [])     # the closing key repeats key 0
    times = bld.accessor(np.arange(len(order), dtype=np.float32) / np.float32(fps), 5126, 'SCALAR', minmax=True)
    rest_q = lambda n: [float(v) for v in bld.doc['nodes'][n].get('rotation', [0., 0., 0., 1.])]   # noqa: E731
    for clip in CLIPS:
        channels, samplers = [], []

        def add(node, path, vals, typ):
            samplers.append({'input': times, 'interpolation': b.spec['timing']['interpolation'], 'output': bld.accessor(np.array(vals, dtype=np.float32), 5126, typ)})
            channels.append({'sampler': len(samplers) - 1, 'target': {'node': node, 'path': path}})
        add(b.ground, 'translation', [frames[clip][k]['ov'][b.ground]['translation'] for k in order], 'VEC3')
        for n in b.joints:                                    # every joint gets a rotation channel: one the cycle does not
            #                                                       turn holds its rest rotation (a full clip, rig kit contract)
            add(n, 'rotation', [frames[clip][k]['ov'].get(n, {}).get('rotation') or rest_q(n) for k in order], 'VEC4')
        keep.append({'channels': channels, 'extras': {BLOCK: b.spec['id']}, 'name': clip, 'samplers': samplers})
    bld.doc['animations'] = sorted(keep, key=lambda a: a.get('name', ''))
    bld.doc.setdefault('extras', {})[BLOCK] = report['block']
    out = bld.finish()
    report['ok'] = True
    report['sha256'] = hashlib.sha256(out).hexdigest()
    report['bytes'] = len(out)
    report['clips_in_file'] = [a.get('name') for a in bld.doc['animations']]
    return out, report


def check(glb, spec=None, bone_map=None, clips=CLIPS):
    """The same metrics on the run / walk a file already carries (legacy clips, hand-made clips, a baked file).
    -> report with report['ok']; measurement refusals raise LocomotionError like bake()."""
    glb = bytes(glb)
    b = read_body(glb, spec, bone_map)
    have = [a.get('name') for a in b.doc.get('animations', [])]
    blk = (b.doc.get('extras') or {}).get(BLOCK) or {}
    report = {'format': FORMAT, 'base': b.spec['id'], 'source_sha256': hashlib.sha256(glb).hexdigest(),
              'measurements': b.measured, 'clips': {}, 'block': blk or None, 'ok': True}
    for clip in clips:
        if clip not in have:
            report['clips'][clip] = {'fail': ['missing'], 'why': ['the file has no clip named %s' % clip]}
            report['ok'] = False
            continue
        st = (blk.get(clip) or {}).get('stride_mps') or stride(b, b.spec['cycles'][clip])
        m = metrics(b, frames_file(b, clip), clip, float(st))
        bad = verdict(b.spec, clip, m)
        report['clips'][clip] = {'metrics': m, 'fail': [c for c, _ in bad], 'why': [t for _, t in bad]}
        report['ok'] = report['ok'] and not bad
    return report


def attach(glb, rig=None, keep_legacy=False, tuning=None, bone_map=None, spec=None):
    """The one call for pipelines that produce characters (generated, imported, converted; docs/LOCOMOTION.md).
    Bakes run + walk and, when rig is given, holds the result to that rig kit contract. It never raises for a body it
    refuses: -> {'ok': True, 'glb': baked bytes, 'report', 'rig_contract'} or
    {'ok': False, 'glb': the input bytes unchanged, 'refused': {'code', 'message'}} so the caller keeps what it had."""
    import tempfile
    glb = bytes(glb)
    try:
        out, report = bake(glb, spec=spec, tuning=tuning, bone_map=bone_map, keep_legacy=keep_legacy)
    except LocomotionError as e:
        return {'ok': False, 'glb': glb, 'refused': {'code': e.code, 'message': e.message}}
    rc = None
    if rig:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'c.glb').write_bytes(out)
            rc = rig_contract(Path(tmp) / 'c.glb', rig)
        if not rc['ok']:
            return {'ok': False, 'glb': glb, 'refused': {'code': 'rig_contract', 'message': 'the baked clips do not meet the %s rig '
                                                         'contract: %s' % (rig, '; '.join(rc['errors'][:4]))}}
    return {'ok': True, 'glb': out, 'report': report, 'rig_contract': rc}


def waive_flight(errors, block):
    """Split rig gate errors for a file with baked locomotion (see rig_contract) -> (errors, waived)."""
    flight = set(((block or {}).get('run') or {}).get('flight_keys') or [])
    keep, waived = [], []
    for e in errors:
        m = re.match(r'rig mesh\.silhouette\.floor: run@(\d+) lowest vertex at ([-0-9.]+) m$', e)
        (waived if m and int(m.group(1)) in flight and float(m.group(2)) > 0. else keep).append(e)
    return keep, waived


def block_of(glb):
    """The locomotion block a file carries, or None."""
    try:
        return (gltf.parse(bytes(glb))[0].get('extras') or {}).get(BLOCK) or None
    except Exception:
        return None


def rig_contract(glb_path, rig, clips=None):
    """The rig kit contract for a baked file. One rule is replaced, by name and in the open: a rig whose contract says the
    lowest vertex touches the floor on every key (human16_v1) cannot hold a run with a flight phase, so floor errors at
    exactly the run keys the block lists as flight are moved from 'errors' to 'waived'; the locomotion check covers
    those keys instead (flight keys, bounce). Every other rig error stays an error. -> {'ok', 'errors', 'waived'}"""
    from .. import character_gate
    rep = character_gate.rig_gate(Path(glb_path), rig, clips=clips)
    errors, waived = waive_flight(rep.get('errors', []), block_of(Path(glb_path).read_bytes()))
    return {'ok': not errors, 'errors': errors, 'waived': waived, 'rig': rig}
