"""Plain mannequins skinned to the rig-kit skeletons (deterministic, numpy, <= 400 tris).

Every limb is a rigid closed piece weighted 100 % to one joint. Each piece starts with an apex vertex exactly at its
joint pivot, buried inside the parent piece; a point at the pivot never moves relative to the parent, so the piece
stays attached on every key of every clip (rig-kit generic connectivity, 3 mm) by construction, and rigid pieces
never stretch (edge ratio 1). This is the reference subject for docs, tools and new builders: build a character the
same way (or skin a continuous mesh) and the rig's clip pack plays on it unchanged.

Coordinates are glTF (metres, +Y up, the character faces +Z, left = +X).
"""
import math

import numpy as np

from . import gltfedit
from .rig import load_rig

LIGHT = np.array([-.45, .8, .7]) / np.linalg.norm([-.45, .8, .7])    # the cast's bake light, glTF axes
WOOD = (0.80, 0.70, 0.56)
WOOD_L = (0.87, 0.77, 0.61)
WOOD_R = (0.70, 0.60, 0.48)


def _frame(axis, hint):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    h = np.asarray(hint, float)
    u = h - a * float(h @ a)
    if np.linalg.norm(u) < 1e-6:
        h = np.array([0., 0., 1.]) if abs(a[2]) < .9 else np.array([1., 0., 0.])
        u = h - a * float(h @ a)
    u = u / np.linalg.norm(u)
    v = np.cross(a, u)
    return a, u, v


class Piece:
    """Closed piece: optional apex at t = 0, rings at t > 0 along `axis` from `origin`, flat cap or tip apex."""

    def __init__(self, bone, color, origin, axis, hint, rings, n, apex=True, tip=None, offsets=None):
        self.bone = bone
        self.color = color
        a, u, v = _frame(axis, hint)
        o = np.asarray(origin, float)
        verts = []
        if apex:
            verts.append(o.copy())
        ring_idx = []
        for k, (t, ru, rv) in enumerate(rings):
            c = o + a * t
            if offsets is not None:
                c = c + np.asarray(offsets[k], float)
            ids = []
            for i in range(n):
                ang = 2 * math.pi * i / n
                verts.append(c + u * (ru * math.cos(ang)) + v * (rv * math.sin(ang)))
                ids.append(len(verts) - 1)
            ring_idx.append(ids)
        tris = []
        if apex:
            r0 = ring_idx[0]
            for i in range(n):
                tris.append((0, r0[(i + 1) % n], r0[i]))
        else:                                              # flat start cap (fan from ring vertex 0)
            r0 = ring_idx[0]
            for i in range(1, n - 1):
                tris.append((r0[0], r0[i + 1], r0[i]))
        for ra, rb in zip(ring_idx, ring_idx[1:]):
            for i in range(n):
                j = (i + 1) % n
                tris.append((ra[i], ra[j], rb[j]))
                tris.append((ra[i], rb[j], rb[i]))
        last = ring_idx[-1]
        if tip is not None:
            verts.append(o + a * tip)
            t_id = len(verts) - 1
            for i in range(n):
                tris.append((last[i], last[(i + 1) % n], t_id))
        else:
            for i in range(1, n - 1):
                tris.append((last[0], last[i], last[i + 1]))
        self.vertices = np.array(verts, float)
        self.tris = np.array(tris, int)
        self._orient()

    def _orient(self):
        """Make every triangle face outward (signed volume positive)."""
        V, T = self.vertices, self.tris
        c = V.mean(axis=0)
        vol = sum(float(np.dot(V[a] - c, np.cross(V[b] - c, V[d] - c))) for a, b, d in T)
        if vol < 0:
            self.tris = T[:, [0, 2, 1]]


def _rest(rig):
    return {b: np.array(rig.rest[b], float) for b in rig.bones}


def _seg(R, a, b):
    d = R[b] - R[a]
    return d, float(np.linalg.norm(d))


def human_pieces(rig):
    R = _rest(rig)
    P = []
    # pelvis: hex prism (the main piece; root carries no geometry)
    py = R['pelvis'][1]
    P.append(Piece('pelvis', WOOD, (0., py - .066, 0.), (0, 1, 0), (1, 0, 0), [(0., .17, .10), (.19, .16, .105)], 6,
                   apex=False))
    # chest on spine: apex at the spine pivot (inside the pelvis); contains the shoulder and neck pivots
    s = R['spine']
    top = R['head'][1]
    P.append(Piece('spine', WOOD, s, (0, 1, 0), (1, 0, 0),
                   [(py + .116 - s[1], .15, .095), (top - .0926 - s[1], .28, .12), (top + .0274 - s[1], .12, .085)], 6))
    # head: apex at the neck pivot (inside the chest), skull rings, tip apex
    h = R['head']
    P.append(Piece('head', WOOD, h, (0, 1, 0), (1, 0, 0), [(.0174, .045, .045), (.1274, .10, .11), (.2674, .105, .115)],
                   6, tip=.3874, offsets=[(0, 0, 0), (0, 0, .012), (0, 0, .012)]))
    for side, col in (('l', WOOD_L), ('r', WOOD_R)):
        # arm chain
        d, L = _seg(R, 'upper_arm_' + side, 'forearm_' + side)
        P.append(Piece('upper_arm_' + side, col, R['upper_arm_' + side], d, (0, 0, 1),
                       [(.035, .038, .038), (L + .03, .034, .034)], 6))
        d, L = _seg(R, 'forearm_' + side, 'hand_' + side)
        P.append(Piece('forearm_' + side, col, R['forearm_' + side], d, (0, 0, 1),
                       [(.025, .026, .026), (L + .025, .024, .024)], 6))
        P.append(Piece('hand_' + side, col, R['hand_' + side], d, (0, 0, 1),
                       [(.02, .017, .017), (.15, .03, .014)], 6))
        # leg chain
        d, L = _seg(R, 'thigh_' + side, 'shin_' + side)
        P.append(Piece('thigh_' + side, col, R['thigh_' + side], d, (0, 0, 1),
                       [(.04, .075, .075), (L + .035, .05, .05)], 6))
        d, L = _seg(R, 'shin_' + side, 'foot_' + side)
        P.append(Piece('shin_' + side, col, R['shin_' + side], d, (0, 0, 1),
                       [(.028, .045, .045), (L + .03, .033, .033)], 6))
        a = R['foot_' + side]
        y0 = float(a[1])
        P.append(Piece('foot_' + side, col, a, (0, -1, 0), (1, 0, 0),
                       [(.025, .025, .025), (y0, .048, .105)], 6,
                       offsets=[(0, 0, 0), (0, 0, .05)]))
    return P


def quad_pieces(rig):
    R = _rest(rig)
    P = []
    hy = R['hips'][1]
    P.append(Piece('hips', WOOD, (0., hy, -.20), (0, 0, 1), (1, 0, 0), [(0., .10, .075), (.29, .11, .08)], 6,
                   apex=False))
    c = R['chest']
    P.append(Piece('chest', WOOD, c, (0, 0, 1), (1, 0, 0), [(.006, .095, .075), (.0884, .10, .085)], 6))
    for leg, paw, col in (('leg_fl', 'paw_fl', WOOD_L), ('leg_fr', 'paw_fr', WOOD_R),
                          ('leg_bl', 'paw_bl', WOOD_L), ('leg_br', 'paw_br', WOOD_R)):
        d, L = _seg(R, leg, paw)
        P.append(Piece(leg, col, R[leg], d, (1, 0, 1), [(.02, .022, .022), (L + .025, .022, .022)], 4))
        a = R[paw]
        y0 = float(a[1])
        P.append(Piece(paw, col, a, (0, -1, 0), (1, 0, 0), [(.016, .014, .014), (y0, .025, .035)], 4,
                       offsets=[(0, 0, 0), (0, 0, .015)]))
    d, L = _seg(R, 'neck', 'head')
    P.append(Piece('neck', WOOD, R['neck'], d, (1, 0, 0), [(.02, .03, .03), (L + .03, .03, .03)], 4))
    P.append(Piece('head', WOOD, R['head'], (0, 0, 1), (1, 0, 0), [(.015, .02, .02), (.04, .055, .05), (.10, .04, .035)],
                   6, tip=.14))
    for a_, b_, r0, r1 in (('tail_1', 'tail_2', .016, .014), ('tail_2', 'tail_3', .013, .011)):
        d, L = _seg(R, a_, b_)
        P.append(Piece(a_, WOOD, R[a_], d, (1, 0, 0), [(.012, r0, r0), (L + .02, r1, r1)], 4))
    d, _ = _seg(R, 'tail_2', 'tail_3')
    P.append(Piece('tail_3', WOOD, R['tail_3'], d, (1, 0, 0), [(.012, .009, .009), (.07, .007, .007)], 4, tip=.10))
    return P


BUILDERS = {'human16_v1': human_pieces, 'quad16_v1': quad_pieces}


def _srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def build(rig_id):
    """-> GLB bytes: the rig's mannequin at the reference rest pose, no clips (attach_clips adds them)."""
    rig = load_rig(rig_id)
    pieces = BUILDERS[rig.id](rig)
    jindex = {b: i for i, b in enumerate(rig.bones)}
    pos, nrm, col, joints, tris = [], [], [], [], []
    for pc in pieces:
        V = pc.vertices
        for a, b, c in pc.tris:
            n = np.cross(V[b] - V[a], V[c] - V[a])
            n = n / np.linalg.norm(n)
            shade = .78 + .22 * max(-.7, float(n @ LIGHT))
            rgb = np.clip(np.array(pc.color) * shade, 0, 1)
            base = len(pos)
            for vi in (a, b, c):
                pos.append(V[vi]); nrm.append(n); col.append(rgb); joints.append(jindex[pc.bone])
            tris.append((base, base + 1, base + 2))
    pos = np.array(pos, np.float32)
    nrm = np.array(nrm, np.float32)
    lin = _srgb_to_linear(np.array(col))
    c16 = np.round(np.concatenate([lin, np.ones((len(lin), 1))], axis=1) * 65535).astype(np.uint16)
    J = np.zeros((len(pos), 4), np.uint8)
    J[:, 0] = joints
    W = np.zeros((len(pos), 4), np.float32)
    W[:, 0] = 1.0
    idx = np.array(tris, np.uint16).reshape(-1)
    doc = {'asset': {'generator': 'adventure-maker rigkit mannequin', 'version': '2.0'},
           'extensionsUsed': ['KHR_materials_unlit'], 'scene': 0, 'nodes': []}
    nodes = doc['nodes']
    for b in rig.bones:
        n = {'name': b}
        kids = [jindex[c] for c in rig.bones if rig.parents[c] == b]
        if kids:
            n = {'children': kids, 'name': b}
        t = [float(np.float32(x)) for x in rig.rest_local[b]]
        if any(x != 0 for x in t):
            n['translation'] = t
        nodes.append(n)
    B = gltfedit.Builder(doc)
    attrs = {'POSITION': B.accessor(pos, 5126, 'VEC3', gltfedit.ARRAY_BUFFER, minmax=True),
             'NORMAL': B.accessor(nrm, 5126, 'VEC3', gltfedit.ARRAY_BUFFER),
             'COLOR_0': B.accessor(c16, 5123, 'VEC4', gltfedit.ARRAY_BUFFER, normalized=True),
             'JOINTS_0': B.accessor(J, 5121, 'VEC4', gltfedit.ARRAY_BUFFER),
             'WEIGHTS_0': B.accessor(W, 5126, 'VEC4', gltfedit.ARRAY_BUFFER)}
    ind = B.accessor(idx, 5123, 'SCALAR', gltfedit.ELEMENT_ARRAY_BUFFER)
    ibm = []
    world = {}
    for b in rig.bones:
        p = rig.parents[b]
        t = np.array([float(np.float32(x)) for x in rig.rest_local[b]])
        world[b] = t if p is None else world[p] + t
        ibm.append([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -world[b][0], -world[b][1], -world[b][2], 1])
    ibm_acc = B.accessor(np.array(ibm, np.float32), 5126, 'MAT4')
    doc['materials'] = [{'extensions': {'KHR_materials_unlit': {}},
                         'extras': {'n64': {'kind': 'mannequin', 'shading': 'baked_unlit_vertex_color'}},
                         'name': 'kit_mannequin',
                         'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0,
                                                  'roughnessFactor': 0.9}}]
    doc['meshes'] = [{'name': 'kit_body_mesh', 'primitives': [{'attributes': attrs, 'indices': ind, 'material': 0}]}]
    doc['skins'] = [{'inverseBindMatrices': ibm_acc, 'joints': list(range(len(rig.bones))), 'name': 'rig_' + rig.id}]
    body = len(nodes)
    nodes.append({'mesh': 0, 'name': 'kit_body', 'skin': 0})
    roots = [jindex[b] for b in rig.bones if rig.parents[b] is None]
    nodes.append({'children': [body] + roots, 'extras': {'skeleton': rig.id, 'rig': rig.tag, 'builder': 'rigkit.mannequin',
                                                          'mannequin': True, 'tris': int(len(tris))},
                  'name': 'rig_' + rig.id})
    doc['scenes'] = [{'name': 'Scene', 'nodes': [len(nodes) - 1]}]
    return B.finish()
