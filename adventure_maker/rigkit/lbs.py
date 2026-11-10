"""Numpy linear-blend-skinning reference (glTF semantics) — the deformation oracle that replaces Blender's armature
modifier for every check (posecheck/connectivity/deformation, parity, validator).

glTF skinning: v' = sum_i w_i * (W_joint_i @ IBM_i) @ v, with W the joint's world matrix; the skinned mesh node's own
transform is ignored (spec). Clips are sampled per key: STEP channels hold the value of the last key <= t.
All maths in float64.
"""
import numpy as np

from . import gltf

KEY_FPS = 15.0


def quat_matrix(q):
    """glTF quaternion [x, y, z, w] -> 3x3 rotation (float64)."""
    x, y, z, w = (float(c) for c in q)
    n = x * x + y * y + z * z + w * w
    s = 2.0 / n if n > 0 else 0.0
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array([[1 - yy - zz, xy - wz, xz + wy],
                     [xy + wz, 1 - xx - zz, yz - wx],
                     [xz - wy, yz + wx, 1 - xx - yy]], dtype=np.float64)


def trs_matrix(t=None, r=None, s=None, m=None):
    if m is not None:
        return np.array(m, dtype=np.float64).reshape(4, 4).T     # glTF matrices are column-major
    out = np.eye(4)
    rot = quat_matrix(r) if r is not None else np.eye(3)
    sc = np.array(s, dtype=np.float64) if s is not None else np.ones(3)
    out[:3, :3] = rot * sc[None, :]
    if t is not None:
        out[:3, 3] = np.array(t, dtype=np.float64)
    return out


def node_trs(node):
    return (node.get('translation'), node.get('rotation'), node.get('scale'), node.get('matrix'))


def clip_overrides(doc, binary, clip, key=0, time=None):
    """{node_index: {'translation'|'rotation'|'scale': value}} of one clip at key `key` (t = key/15) or `time`."""
    if clip is None:
        return {}
    anims = [a for a in doc.get('animations', []) if a.get('name') == clip]
    if not anims:
        raise KeyError('clip %r not in file' % clip)
    an = anims[0]
    t = (key / KEY_FPS) if time is None else float(time)
    out = {}
    for ch in an['channels']:
        s = an['samplers'][ch['sampler']]
        times = gltf.read_accessor(doc, binary, s['input'])[:, 0].astype(np.float64)
        vals = gltf.read_accessor(doc, binary, s['output']).astype(np.float64)
        interp = s.get('interpolation', 'LINEAR')
        if interp == 'CUBICSPLINE':
            vals = vals.reshape(len(times), 3, -1)[:, 1, :]
        i = int(np.searchsorted(times, t + 1e-6, side='right') - 1)
        i = max(0, min(len(times) - 1, i))
        if interp == 'LINEAR' and i + 1 < len(times) and t > times[i] + 1e-9:
            f = (t - times[i]) / (times[i + 1] - times[i])
            v = vals[i] * (1 - f) + vals[i + 1] * f
            if ch['target']['path'] == 'rotation':
                v = v / np.linalg.norm(v)
        else:
            v = vals[i]
        out.setdefault(ch['target']['node'], {})[ch['target']['path']] = v
    return out


def world_matrices(doc, overrides=None):
    """World matrix of every node (list of 4x4), with optional per-node TRS overrides."""
    nodes = doc.get('nodes', [])
    parents = gltf.node_parents(doc)
    overrides = overrides or {}
    local = []
    for i, n in enumerate(nodes):
        t, r, s, m = node_trs(n)
        o = overrides.get(i)
        if o:
            t = o.get('translation', t)
            r = o.get('rotation', r)
            s = o.get('scale', s)
            m = None if m is None else m
        local.append(trs_matrix(t, r, s, m if not o else None))
    world = [None] * len(nodes)

    def get(i):
        if world[i] is None:
            p = parents.get(i)
            world[i] = local[i] if p is None else get(p) @ local[i]
        return world[i]
    for i in range(len(nodes)):
        get(i)
    return world


def inverse_binds(doc, binary, skin_index=0):
    sk = doc['skins'][skin_index]
    if 'inverseBindMatrices' not in sk:
        return None
    arr = gltf.read_accessor(doc, binary, sk['inverseBindMatrices']).astype(np.float64)
    return arr.reshape(-1, 4, 4).transpose(0, 2, 1)          # column-major -> row-major


def joint_matrices(doc, binary, clip=None, key=0, skin_index=0, time=None):
    """Skin matrices W_j @ IBM_j (J, 4, 4) for one key (clip None = rest)."""
    world = world_matrices(doc, clip_overrides(doc, binary, clip, key, time))
    sk = doc['skins'][skin_index]
    ibm = inverse_binds(doc, binary, skin_index)
    if ibm is None:
        ibm = np.repeat(np.eye(4)[None], len(sk['joints']), axis=0)
    return np.stack([world[j] for j in sk['joints']]) @ ibm


def skin(positions, joints, weights, skin_mats):
    """Vectorised LBS: positions (N,3), joints (N,K) int, weights (N,K) float, skin_mats (J,4,4) -> (N,3)."""
    p = np.asarray(positions, dtype=np.float64)
    ph = np.concatenate([p, np.ones((len(p), 1))], axis=1)
    out = np.zeros((len(p), 3))
    for k in range(joints.shape[1]):
        m = skin_mats[joints[:, k]]                         # (N,4,4)
        out += weights[:, k:k + 1] * np.einsum('nij,nj->ni', m[:, :3, :], ph)
    return out


def primitives(doc, binary):
    """Every mesh primitive placed by a node: [{'node', 'name', 'skin', 'mesh', 'prim', 'positions', 'indices', 'used',
    'joints', 'weights'}] in node order then primitive order (joints/weights None for rigid props). 'used' marks the
    vertices a triangle references (glTF allows unreferenced vertices; they are not geometry)."""
    out = []
    for ni, n in enumerate(doc.get('nodes', [])):
        if 'mesh' not in n:
            continue
        for pi, p in enumerate(doc['meshes'][n['mesh']]['primitives']):
            a = p['attributes']
            row = {'node': ni, 'name': n.get('name', 'node%d' % ni), 'skin': n.get('skin'), 'mesh': n['mesh'],
                   'prim': pi, 'positions': gltf.read_accessor(doc, binary, a['POSITION']).astype(np.float64),
                   'indices': (gltf.read_accessor(doc, binary, p['indices'])[:, 0].astype(np.int64)
                               if 'indices' in p else None),
                   'joints': None, 'weights': None}
            row['used'] = np.ones(len(row['positions']), dtype=bool)
            if row['indices'] is not None:
                row['used'][:] = False
                row['used'][row['indices'][(row['indices'] >= 0) & (row['indices'] < len(row['positions']))]] = True
            if n.get('skin') is not None and 'JOINTS_0' in a and 'WEIGHTS_0' in a:
                js = [gltf.read_accessor(doc, binary, a['JOINTS_0'], normalize=False).astype(np.int64)]
                ws = [gltf.read_accessor(doc, binary, a['WEIGHTS_0']).astype(np.float64)]
                s = 1
                while ('JOINTS_%d' % s) in a and ('WEIGHTS_%d' % s) in a:
                    js.append(gltf.read_accessor(doc, binary, a['JOINTS_%d' % s], normalize=False).astype(np.int64))
                    ws.append(gltf.read_accessor(doc, binary, a['WEIGHTS_%d' % s]).astype(np.float64))
                    s += 1
                row['joints'] = np.concatenate(js, axis=1)
                row['weights'] = np.concatenate(ws, axis=1)
            out.append(row)
    return out


def posed(doc, binary, clip=None, key=0, prims=None, time=None):
    """Posed world positions of every primitive at one key: list aligned with primitives(doc, binary)."""
    prims = prims if prims is not None else primitives(doc, binary)
    ov = clip_overrides(doc, binary, clip, key, time)
    world = world_matrices(doc, ov)
    mats = {}
    out = []
    for r in prims:
        if r['joints'] is not None:
            si = r['skin']
            if si not in mats:
                sk = doc['skins'][si]
                ibm = inverse_binds(doc, binary, si)
                if ibm is None:
                    ibm = np.repeat(np.eye(4)[None], len(sk['joints']), axis=0)
                mats[si] = np.stack([world[j] for j in sk['joints']]) @ ibm
            out.append(skin(r['positions'], r['joints'], r['weights'], mats[si]))
        else:
            w = world[r['node']]
            out.append(r['positions'] @ w[:3, :3].T + w[:3, 3])
    return out


def skin_vertices(glb, clip=None, key=0):
    """(N,3) skinned positions of every skinned primitive (file order) for a GLB (bytes or path)."""
    if not isinstance(glb, (bytes, bytearray)):
        from pathlib import Path
        glb = Path(glb).read_bytes()
    doc, binary = gltf.parse(glb)
    prims = primitives(doc, binary)
    pos = posed(doc, binary, clip, key, prims)
    sel = [p for p, r in zip(pos, prims) if r['joints'] is not None]
    return np.concatenate(sel, axis=0) if sel else np.zeros((0, 3))


def clip_keys(doc, binary, clip):
    """Key times of a clip (union of its samplers' inputs)."""
    an = [a for a in doc.get('animations', []) if a.get('name') == clip][0]
    ts = set()
    for s in an['samplers']:
        for t in gltf.read_accessor(doc, binary, s['input'])[:, 0]:
            ts.add(round(float(t), 6))
    return sorted(ts)
