"""Box bodies for the locomotion tests and docs: a skinned GLB made of boxes on a human16 armature, with every
proportion a dial. Not a character; a body with known measurements, so a test can say what the bake must measure,
and known-bad bodies (crossed legs, no hip height, scaled joints, a body facing backward) on demand.

    glb = box_body(height=1.1, hip=.44, ...)        # bytes

Sizes are fractions of the height unless the name ends in _deg. glTF space: y up, the body faces +z, left is +x.
"""
import math

import numpy as np

from ..rigkit import gltfedit
from .core import _quat

PRESETS = {
    # three bodies of different proportions (none of them is the reference build)
    'short_stocky': dict(height=1.42, hip=.43, hip_half=.075, leg_w=.115, torso_w=.40, torso_d=.26, shoulder_half=.225,
                         shoulder=.80, head=.17, upper_arm=.15, forearm=.13, boot=(.13, .06), arm_w=.085, arm_deg=16.),
    'tall_thin': dict(height=1.98, hip=.55, hip_half=.055, leg_w=.07, torso_w=.24, torso_d=.13, shoulder_half=.145,
                      shoulder=.84, head=.105, upper_arm=.175, forearm=.165, boot=(.10, .04), arm_w=.045, arm_deg=9.),
    'child': dict(height=1.08, hip=.41, hip_half=.07, leg_w=.10, torso_w=.33, torso_d=.21, shoulder_half=.185,
                  shoulder=.74, head=.24, upper_arm=.14, forearm=.12, boot=(.12, .055), arm_w=.07, arm_deg=14.),
    # known-bad bodies
    'legs_cross': dict(height=1.7, hip_half=.02, leg_w=.11),
    'no_hip_height': dict(height=1.7, hip=.12, ankle=.05),
}
BONES = ('root', 'pelvis', 'spine', 'head', 'upper_arm_l', 'forearm_l', 'hand_l', 'upper_arm_r', 'forearm_r', 'hand_r',
         'thigh_l', 'shin_l', 'foot_l', 'thigh_r', 'shin_r', 'foot_r')
PARENT = {'pelvis': 'root', 'spine': 'pelvis', 'head': 'spine', 'upper_arm_l': 'spine', 'upper_arm_r': 'spine',
          'forearm_l': 'upper_arm_l', 'forearm_r': 'upper_arm_r', 'hand_l': 'forearm_l', 'hand_r': 'forearm_r',
          'thigh_l': 'pelvis', 'thigh_r': 'pelvis', 'shin_l': 'thigh_l', 'shin_r': 'thigh_r', 'foot_l': 'shin_l',
          'foot_r': 'shin_r', 'toe_l': 'foot_l', 'toe_r': 'foot_r', 'finger_l': 'hand_l', 'finger_r': 'hand_r'}
FACES = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))   # corner = 4 i + 2 j + k
COLOURS = {'torso': (.25, .42, .62), 'leg': (.2, .2, .25), 'boot': (.1, .1, .1), 'skin': (.8, .62, .5)}


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def _frame(u):
    """Right-handed frame (e1, u, e3) around a segment direction."""
    u = _unit(u)
    ref = np.array([0., 0., 1.]) if abs(u[2]) < .9 else np.array([1., 0., 0.])
    e1 = _unit(np.cross(u, ref))
    return e1, u, np.cross(e1, u)


def box_body(height=1.7, hip=.5, hip_half=.085, leg_w=.10, boot=(.115, .05), ankle=.045, knee=.5, shoulder=.82,
             shoulder_half=.18, torso_w=.32, torso_d=.18, head=.13, upper_arm=.165, forearm=.15, hand=.05, arm_w=.06,
             arm_deg=12., rest='identity', toes=False, fingers=False, root=True, names=None, joint_scale=None,
             floor=0.):
    """A box body as GLB bytes. rest: 'identity' (every joint unrotated) or 'bone_y' (each joint's +Y runs along its
    bone, as most DCC exports do). names: {base bone: name in the file}. A boot longer behind the ankle than ahead of
    it (boot=(.05, .115)) is a body facing backward.
    joint_scale: {bone: scale} puts a non-unit scale on a joint (a body the bake must refuse)."""
    H = float(height)
    hipy, anky, shy = hip * H, ankle * H, shoulder * H
    J = {'root': (0., 0., 0.), 'pelvis': (0., hipy + .03 * H, 0.), 'spine': (0., hipy + .11 * H, 0.),
         'head': (0., shy + .035 * H, 0.)}
    d = {}
    for s, sg in (('l', 1.), ('r', -1.)):
        x = sg * hip_half * H
        J['thigh_' + s] = (x, hipy, 0.)
        J['shin_' + s] = (x, anky + (1. - knee) * (hipy - anky), .004 * H)
        J['foot_' + s] = (x, anky, 0.)
        d[s] = np.array([sg * math.sin(math.radians(arm_deg)), -math.cos(math.radians(arm_deg)), 0.])
        a = np.array([sg * shoulder_half * H, shy, 0.])
        J['upper_arm_' + s] = tuple(a)
        J['forearm_' + s] = tuple(a + d[s] * upper_arm * H)
        J['hand_' + s] = tuple(a + d[s] * (upper_arm + forearm) * H)
        if toes:
            J['toe_' + s] = (x, .4 * anky, boot[0] * H * .5)
        if fingers:
            J['finger_' + s] = tuple(a + d[s] * (upper_arm + forearm + hand * .5) * H)
    J = {k: np.array(v, dtype=np.float64) for k, v in J.items()}
    order = [b for b in BONES if root or b != 'root'] + sorted(k for k in J if k not in BONES)
    parent = {b: PARENT.get(b) for b in order}
    if not root:
        parent['pelvis'] = None
    child = {'pelvis': 'spine', 'spine': 'head', 'thigh_l': 'shin_l', 'shin_l': 'foot_l', 'thigh_r': 'shin_r',
             'shin_r': 'foot_r', 'upper_arm_l': 'forearm_l', 'forearm_l': 'hand_l', 'upper_arm_r': 'forearm_r',
             'forearm_r': 'hand_r'}
    R = {}
    for b in order:
        R[b] = np.eye(3)
        if rest == 'bone_y' and b in child:
            e1, u, e3 = _frame(J[child[b]] - J[b])
            R[b] = np.stack([e1, u, e3], axis=1)
        elif rest == 'bone_y' and b.startswith(('hand_', 'foot_', 'toe_', 'finger_')):
            R[b] = R[parent[b]] if b.startswith(('hand_', 'finger_')) else np.stack(_frame((0., -.3, 1.)), axis=1)
    P, N, JI, MAT, TRI = [], [], [], [], {}

    def box(bone, corners, colour):
        base = len(P)
        c = np.asarray(corners, dtype=np.float64)
        for f in FACES:
            q = c[list(f)]
            n = _unit(np.cross(q[1] - q[0], q[2] - q[0]))
            k = len(P)
            for v in q:
                P.append(v)
                N.append(n)
                JI.append(order.index(bone))
            TRI.setdefault(colour, []).extend([(k, k + 1, k + 2), (k, k + 2, k + 3)])
        return base

    def aligned(bone, lo, hi, colour):
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
        box(bone, [(lo[0] if i == 0 else hi[0], lo[1] if j == 0 else hi[1], lo[2] if k == 0 else hi[2])
                   for i in (0, 1) for j in (0, 1) for k in (0, 1)], colour)

    def limb(bone, a, b, w, colour):
        e1, u, e3 = _frame(b - a)
        box(bone, [a + (b - a) * j + e1 * w * (i - .5) + e3 * w * (k - .5) for i in (0, 1) for j in (0, 1) for k in (0, 1)], colour)

    td, lw = torso_d * H / 2., leg_w * H
    aligned('pelvis', (-(hip_half * H + lw / 2.), hipy - .02 * H, -td), (hip_half * H + lw / 2., hipy + .10 * H, td), 'leg')
    aligned('spine', (-torso_w * H / 2., hipy + .10 * H, -td), (torso_w * H / 2., shy + .03 * H, td), 'torso')
    aligned('head', (-head * H / 2., shy + .04 * H, -head * H * .55), (head * H / 2., H, head * H * .55), 'skin')
    for s, sg in (('l', 1.), ('r', -1.)):
        x = J['foot_' + s][0]
        limb('thigh_' + s, J['thigh_' + s], J['shin_' + s], lw, 'leg')
        limb('shin_' + s, J['shin_' + s], J['foot_' + s], lw * .9, 'leg')
        zt, zh = boot[0] * H, -boot[1] * H
        if toes:
            zs = max(zt * .5, lw * .6)                              # the split is ahead of the shin, which stands on the foot
            aligned('foot_' + s, (x - lw * .55, 0., zh), (x + lw * .55, anky, zs), 'boot')
            aligned('toe_' + s, (x - lw * .5, 0., zs), (x + lw * .5, anky * .8, zt), 'boot')   # narrower: its own piece
        else:
            aligned('foot_' + s, (x - lw * .55, 0., zh), (x + lw * .55, anky, zt), 'boot')
        aw = arm_w * H
        limb('upper_arm_' + s, J['upper_arm_' + s], J['forearm_' + s], aw, 'torso')
        limb('forearm_' + s, J['forearm_' + s], J['hand_' + s], aw * .9, 'torso')
        tip = J['hand_' + s] + d[s] * hand * H
        if fingers:
            mid = J['finger_' + s]
            limb('hand_' + s, J['hand_' + s], mid, aw * .8, 'skin')
            limb('finger_' + s, mid, tip, aw * .7, 'skin')
        else:
            limb('hand_' + s, J['hand_' + s], tip, aw * .8, 'skin')
    PA, NA = np.array(P) + np.array([0., floor, 0.]), np.array(N)
    names = dict(names or {})
    doc = {'asset': {'version': '2.0', 'generator': 'hermes64 locomotion box body'}, 'scene': 0, 'nodes': [],
           'materials': [], 'meshes': [{'name': 'body', 'primitives': []}]}
    for b in order:
        J[b] = J[b] + np.array([0., floor, 0.])
    for b in order:
        p = parent[b]
        rp = R[p] if p else np.eye(3)
        t = rp.T @ (J[b] - (J[p] if p else 0.))
        node = {'name': names.get(b, b), 'translation': [float(v) for v in t], 'rotation': _quat(rp.T @ R[b])}
        if joint_scale and b in joint_scale:
            node['scale'] = [float(joint_scale[b])] * 3
        kids = [order.index(c) for c in order if parent[c] == b]
        if kids:
            node['children'] = kids
        doc['nodes'].append(node)
    bld = gltfedit.Builder(doc)
    ibm = []
    for b in order:
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = R[b], J[b]
        ibm.append(np.linalg.inv(m).T.reshape(16))               # column-major
    j4 = np.zeros((len(PA), 4), dtype=np.uint8)
    j4[:, 0] = JI
    w4 = np.zeros((len(PA), 4), dtype=np.float32)
    w4[:, 0] = 1.
    att = {'POSITION': bld.accessor(PA, 5126, 'VEC3', 34962, minmax=True), 'NORMAL': bld.accessor(NA, 5126, 'VEC3', 34962),
           'JOINTS_0': bld.accessor(j4, 5121, 'VEC4', 34962), 'WEIGHTS_0': bld.accessor(w4, 5126, 'VEC4', 34962)}
    for colour in sorted(TRI):
        tri = np.array(TRI[colour], dtype=np.uint16)
        doc['materials'].append({'name': colour, 'pbrMetallicRoughness': {'baseColorFactor': list(COLOURS[colour]) + [1.], 'metallicFactor': 0., 'roughnessFactor': 1.}})
        doc['meshes'][0]['primitives'].append({'attributes': dict(att), 'indices': bld.accessor(tri.reshape(-1), 5123, 'SCALAR', 34963),
                                               'material': len(doc['materials']) - 1})
    doc['skins'] = [{'joints': list(range(len(order))), 'inverseBindMatrices': bld.accessor(np.array(ibm), 5126, 'MAT4'),
                     'skeleton': 0}]
    doc['nodes'].append({'name': 'body', 'mesh': 0, 'skin': 0})
    doc['scenes'] = [{'nodes': [0, len(order)]}]
    return bld.finish()


def preset(name, **over):
    return box_body(**dict(PRESETS[name], **over))
