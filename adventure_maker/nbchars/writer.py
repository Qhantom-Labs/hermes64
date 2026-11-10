"""Scene -> GLB bytes in pure Python + numpy, laid out the way the Blender 5.2 glTF exporter lays out the published
character GLBs (export settings of core/blender.export: Y-up, extras, ACTIONS, no sampling, normals, texcoords,
active vertex colour, skins, rest-position armature, no leaf bones, no optimisation).

Layout rules (each one checked against the published oracle files, see docs/NBCHARS-RESULT.md):
  * one primitive per used material (ascending material index); per primitive the corner "dots"
    (vertex index, normal, uv, colour) are de-duplicated with numpy.unique over a byte view of the record, which orders
    glTF vertices by Blender vertex index first; indices are the inverse map in triangle order;
  * attributes POSITION, NORMAL, TEXCOORD_0, COLOR_0 (unsigned short, normalized), JOINTS_0 (unsigned byte), WEIGHTS_0;
  * objects are numbered by the exporter's post-order traversal (node children, then mesh, then skin: inverse binds
    before joints); every accessor has its own bufferView, images get theirs when their material is first reached;
  * animations sorted by name; channels per pose bone in bone creation order (rotation, then translation); one shared
    16-key time accessor; STEP interpolation.
"""
import math

import numpy as np

from . import blendmath as BM
from ..rigkit import gltf
from ..rigkit.rig import skin_order

F32 = np.float32
GENERATOR = 'adventure-maker nbchars (pure python)'
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
IBM_ROT = [1., -0., 0., -0., -0., 1., -0., 0., 0., -0., 1., -0.]   # column-major rotation part Blender writes


class WriteError(ValueError):
    pass


def _f(x):
    return float(F32(x))


def _zup2yup(a):
    a[:, [1, 2]] = a[:, [2, 1]]
    a[:, 2] *= -1


class _Doc:
    def __init__(self):
        self.doc = {'asset': {'generator': GENERATOR, 'version': '2.0'}, 'nodes': [], 'materials': [], 'meshes': [],
                    'textures': [], 'images': [], 'accessors': [], 'bufferViews': [], 'samplers': []}
        self.bin = bytearray()
        self.used_ext = []
        self.req_ext = []

    def view(self, raw, target=None):
        pad = (4 - len(self.bin) % 4) % 4
        self.bin += b'\0' * pad
        bv = {'buffer': 0, 'byteLength': len(raw), 'byteOffset': len(self.bin)}
        if target is not None:
            bv['target'] = target
        self.bin += raw
        self.doc['bufferViews'].append(bv)
        return len(self.doc['bufferViews']) - 1

    def accessor(self, arr, ctype, typ, target=None, minmax=False, normalized=None):
        arr = np.ascontiguousarray(arr)
        acc = {'bufferView': self.view(arr.tobytes(), target), 'componentType': ctype, 'count': int(len(arr))}
        if minmax:
            acc['max'] = np.amax(arr, axis=0).tolist() if arr.ndim > 1 else [float(np.amax(arr))]
            acc['min'] = np.amin(arr, axis=0).tolist() if arr.ndim > 1 else [float(np.amin(arr))]
        if normalized:
            acc['normalized'] = True
        acc['type'] = typ
        self.doc['accessors'].append(acc)
        return len(self.doc['accessors']) - 1

    def ext(self, name, required=False):
        if name not in self.used_ext:
            self.used_ext.append(name)
        if required and name not in self.req_ext:
            self.req_ext.append(name)


# ------------------------------------------------------------------ mesh -> primitives
def _vert_bones(mesh, joint_index):
    out = []
    for vw in mesh.weights:
        bones = []
        for g, w in vw:
            if w <= 0.0001:
                continue
            j = joint_index.get(mesh.groups[g])
            if j is None:
                continue
            bones.append((j, w))
        bones.sort(key=lambda x: x[1], reverse=True)
        if not bones:
            raise WriteError('%s: a vertex has no bone influence (Blender would add a neutral bone)' % mesh.name)
        out.append(bones)
    return out


def primitives(mesh, joint_index=None):
    """-> list of dicts {material, POSITION, NORMAL, TEXCOORD_0, COLOR_0, [JOINTS_0, WEIGHTS_0], indices}."""
    F = mesh.faces
    nl = 3 * len(F)
    vert = F.reshape(-1).astype(np.uint32)
    # POSITION: object matrix (identity) through numpy float64 then back to float32, then Z-up -> Y-up
    locs = mesh.vertices.astype(F32).copy()
    with np.errstate(all='ignore'):
        locs[:] = np.matmul(locs, np.eye(3)) + np.zeros(3)
    _zup2yup(locs)
    normals = BM.export_normals(mesh.vertex_normals[vert])
    _zup2yup(normals)
    uvs = mesh.corner_uv.astype(F32).copy()
    uvs[:, 1] *= -1
    uvs[:, 1] += 1
    col = BM.SRGB_TO_LINEAR[mesh.corner_color[:, :3]]
    alpha = (mesh.corner_color[:, 3].astype(F32) / F32(255.)).astype(F32)
    fields = [('vertex_index', np.uint32)] + [('NORMAL%d' % i, F32) for i in range(3)] + \
             [('TEXCOORD_0%d' % i, F32) for i in range(2)] + [('COLOR_0%d' % i, F32) for i in range(4)]
    dots = np.empty(nl, dtype=np.dtype(fields))
    dots['vertex_index'] = vert
    for i in range(3):
        dots['NORMAL%d' % i] = normals[:, i]
    for i in range(2):
        dots['TEXCOORD_0%d' % i] = uvs[:, i]
    for i in range(3):
        dots['COLOR_0%d' % i] = col[:, i]
    dots['COLOR_03'] = alpha
    vb = _vert_bones(mesh, joint_index) if joint_index is not None else None
    tri_mat = mesh.face_material.astype(np.uint32)
    loop_mat = np.repeat(tri_mat, 3)
    loops = np.arange(nl, dtype=np.uint32)
    out = []
    for mi in np.unique(tri_mat):
        pd = dots[loops[loop_mat == mi]]
        for name in pd.dtype.names:
            if pd.dtype[name].kind == 'f':
                pd[name][pd[name] == -0.0] = 0.0
        size = pd.dtype.itemsize
        view_dt = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}.get(size)
        if view_dt is None:
            view_dt = np.dtype((np.str_, size // 4)) if size % 4 == 0 else np.dtype((np.bytes_, size))
        uniq, inv = np.unique(pd.view(view_dt), return_inverse=True)
        uniq = uniq.view(pd.dtype)
        inv = inv.reshape(-1)
        bidx = uniq['vertex_index']
        prim = {'material': int(mi)}
        prim['POSITION'] = locs[bidx]
        nrm = np.empty((len(uniq), 3), F32)
        for i in range(3):
            nrm[:, i] = uniq['NORMAL%d' % i]
        prim['NORMAL'] = nrm
        uv = np.empty((len(uniq), 2), F32)
        for i in range(2):
            uv[:, i] = uniq['TEXCOORD_0%d' % i]
        prim['TEXCOORD_0'] = uv
        c = np.empty((len(uniq), 4), F32)
        for i in range(4):
            c[:, i] = uniq['COLOR_0%d' % i]
        prim['COLOR_0'] = BM.color_u16(c)
        if vb is not None:
            nsets = (max(len(vb[v]) for v in bidx) + 3) // 4
            joints, weights = [], []
            for v in bidx:
                bones = vb[v]
                for j in range(4 * nsets):
                    jt, wt = bones[j] if j < len(bones) else (0, 0.0)
                    if j < 4:
                        joints.append(jt); weights.append(wt)
            jarr = np.array(joints).reshape(-1, 4)
            jdt = np.uint8 if jarr.max() < 256 else np.uint16
            prim['JOINTS_0'] = jarr.astype(jdt)
            w = np.array(weights, dtype=F32).reshape(-1, 4)
            tot = w.sum(axis=1).reshape(-1, 1)
            w /= tot
            prim['WEIGHTS_0'] = w
        idx = inv.astype(np.uint16 if inv.max() < 65535 else np.uint32)
        prim['indices'] = idx
        out.append(prim)
    return out


# ------------------------------------------------------------------ writer
class _Writer:
    def __init__(self, scene, generator=GENERATOR):
        self.sc = scene
        self.d = _Doc()
        self.d.doc['asset']['generator'] = generator
        self.mat_index = {}
        self.img_index = {}
        self.node_index = {}
        self.sampler = None

    # materials ------------------------------------------------------
    def material(self, m):
        if m.name in self.mat_index:
            return self.mat_index[m.name]
        doc = self.d.doc
        if self.sampler is None:
            doc['samplers'].append({'magFilter': 9729, 'minFilter': 9987})
            self.sampler = len(doc['samplers']) - 1
        if m.image_name not in self.img_index:
            bv = self.d.view(m.png)
            doc['images'].append({'bufferView': bv, 'mimeType': 'image/png', 'name': m.image_name})
            self.img_index[m.image_name] = len(doc['images']) - 1
        doc['textures'].append({'sampler': self.sampler, 'source': self.img_index[m.image_name]})
        tex = len(doc['textures']) - 1
        info = {'index': tex}
        if m.atlas_cell is not None:
            cell, cols, rows = m.atlas_cell
            sx, sy = _f(1. / cols), _f(1. / rows)
            lx, ly = _f(cell % cols / cols), _f(cell // cols / rows)
            off = [lx - sy * math.sin(0.), 1 - ly - sy * math.cos(0.)]
            tt = {}
            if off != [0., 0.]:
                tt['offset'] = off
            if [sx, sy] != [1., 1.]:
                tt['scale'] = [sx, sy]
            if tt:
                info = {'extensions': {'KHR_texture_transform': tt}, 'index': tex}
                self.d.ext('KHR_materials_unlit')
                self.d.ext('KHR_texture_transform', required=True)
        self.d.ext('KHR_materials_unlit')
        doc['materials'].append({'extensions': {'KHR_materials_unlit': {}}, 'extras': {'n64': m.n64}, 'name': m.name,
                                 'pbrMetallicRoughness': {'baseColorTexture': info, 'metallicFactor': 0,
                                                          'roughnessFactor': 0.9}})
        self.mat_index[m.name] = len(doc['materials']) - 1
        return self.mat_index[m.name]

    def mesh(self, me, joint_index=None):
        prims = []
        for p in primitives(me, joint_index):
            attrs = {}
            attrs['POSITION'] = self.d.accessor(p['POSITION'], 5126, 'VEC3', ARRAY_BUFFER, minmax=True)
            attrs['NORMAL'] = self.d.accessor(p['NORMAL'], 5126, 'VEC3', ARRAY_BUFFER)
            attrs['TEXCOORD_0'] = self.d.accessor(p['TEXCOORD_0'], 5126, 'VEC2', ARRAY_BUFFER)
            attrs['COLOR_0'] = self.d.accessor(p['COLOR_0'], 5123, 'VEC4', ARRAY_BUFFER, normalized=True)
            if 'JOINTS_0' in p:
                attrs['JOINTS_0'] = self.d.accessor(p['JOINTS_0'], 5121 if p['JOINTS_0'].dtype == np.uint8 else 5123,
                                                    'VEC4', ARRAY_BUFFER)
                attrs['WEIGHTS_0'] = self.d.accessor(p['WEIGHTS_0'], 5126, 'VEC4', ARRAY_BUFFER)
            ind = self.d.accessor(p['indices'], 5123 if p['indices'].dtype == np.uint16 else 5125, 'SCALAR',
                                  ELEMENT_ARRAY_BUFFER)
            mat = self.material(me.materials[p['material']])
            prims.append({'attributes': attrs, 'indices': ind, 'material': mat})
        self.d.doc['meshes'].append({'name': me.name, 'primitives': prims})
        return len(self.d.doc['meshes']) - 1

    # tree -------------------------------------------------------------
    def build(self):
        sc = self.sc
        doc = self.d.doc
        if sc.rig is None:
            node = {'mesh': self.mesh(sc.body), 'name': sc.body_object}
            if sc.body_extras:
                node = {'extras': sc.body_extras, 'mesh': node['mesh'], 'name': sc.body_object}
            doc['nodes'].append(node)
            doc['scene'] = 0
            doc['scenes'] = [{'name': 'Scene', 'nodes': [0]}]
            return
        rig = sc.rig
        order = list(rig.bones)
        chain = BM.bone_chain(rig.bones, rig.parents, order)
        self.arm = {n: chain[n]['arm_t'] for n in order}
        joints = skin_order(rig.parents)
        self.joints = joints
        jindex = {n: i for i, n in enumerate(joints)}
        kids = {n: sorted(c for c in order if rig.parents[c] == n) for n in order}
        socks = {}
        for s in sc.sockets:
            socks.setdefault(s.bone, []).append(s)
        for b in socks:
            socks[b].sort(key=lambda s: s.name)
        emitted = {}

        def emit(key, obj):
            doc['nodes'].append(obj)
            emitted[key] = len(doc['nodes']) - 1
            return emitted[key]

        def socket_node(s):
            if ('s', s.name) in emitted:
                return emitted[('s', s.name)]
            node = {}
            if s.extras:
                node['extras'] = s.extras
            if s.mesh is not None:
                node['mesh'] = self.mesh(s.mesh)
            node['name'] = s.name
            if s.rotation is not None:
                node['rotation'] = [_f(x) for x in s.rotation]
            if s.translation is not None:
                node['translation'] = [_f(x) for x in s.translation]
            return emit(('s', s.name), node)

        def bone_node(b):
            if ('b', b) in emitted:
                return emitted[('b', b)]
            ch = [bone_node(c) for c in kids[b]] + [socket_node(s) for s in socks.get(b, [])]
            node = {}
            if ch:
                node['children'] = ch
            node['name'] = b
            t = self.rest_translation(b)
            if any(x != 0 for x in t):
                node['translation'] = t
            return emit(('b', b), node)

        # rig object: children = [kit_body object] + [root bones]; kit_body's skin reaches the joints first
        body_mesh = self.mesh(sc.body, jindex)
        ibm = []
        for b in joints:
            g = self.arm[b]
            tx, ty, tz = -float(g[0]), -float(g[2]), float(g[1])
            tx = tx if tx != 0 else -0.
            ty = ty if ty != 0 else 0.
            tz = tz if tz != 0 else -0.
            ibm += IBM_ROT + [tx, ty, tz, 1.]
        ibm_acc = self.d.accessor(np.array(ibm, dtype=F32).reshape(-1, 16), 5126, 'MAT4')
        jnodes = [bone_node(b) for b in joints]
        doc.setdefault('skins', []).append({'inverseBindMatrices': ibm_acc, 'joints': jnodes, 'name': rig.object_name})
        body_node = emit(('o', sc.body_object), {'mesh': body_mesh, 'name': sc.body_object, 'skin': 0})
        roots = [b for b in order if rig.parents[b] is None]
        rig_node = emit(('o', rig.object_name), {'children': [body_node] + [bone_node(r) for r in sorted(roots)],
                                                 'extras': rig.extras, 'name': rig.object_name})
        doc['scene'] = 0
        doc['scenes'] = [{'name': 'Scene', 'nodes': [rig_node]}]
        self.emitted = emitted
        self.animations()

    def rest_translation(self, b):
        p = self.sc.rig.parents[b]
        c = self.arm[b]
        if p is None:
            return [_f(c[0]), _f(c[2]), _f(-c[1])]
        q = self.arm[p]
        return [float(F32(c[0] - q[0])), float(F32(c[2] - q[2])), float(F32(q[1] - c[1]))]

    def animations(self):
        sc = self.sc
        if not sc.clips:
            return
        doc = self.d.doc
        doc['animations'] = []
        times_acc = {}
        for clip in sorted(sc.clips, key=lambda c: c.name):
            channels, samplers = [], []
            key = clip.times.astype(F32).tobytes()
            for bone, path in clip.channel_order:
                if key not in times_acc:
                    times_acc[key] = self.d.accessor(clip.times.astype(F32), 5126, 'SCALAR', minmax=True)
                if path == 'rotation':
                    q = np.array(clip.rotations[bone], dtype=np.float64)
                    q = np.where(q[:, 3:4] < 0, -q, q)          # Blender's matrix->quaternion keeps w >= 0
                    out = self.d.accessor(q.astype(F32), 5126, 'VEC4')
                else:
                    rest = np.array(self.rest_translation(bone), dtype=F32)
                    vals = (rest[None, :] + np.asarray(clip.translations[bone], dtype=np.float64).astype(F32)).astype(F32)
                    out = self.d.accessor(vals, 5126, 'VEC3')
                samplers.append({'input': times_acc[key], 'interpolation': 'STEP', 'output': out})
                channels.append({'sampler': len(samplers) - 1,
                                 'target': {'node': self.emitted[('b', bone)], 'path': path}})
            an = {'channels': channels, 'name': clip.name, 'samplers': samplers}
            if clip.extras:
                an['extras'] = clip.extras
            doc['animations'].append(an)

    def finish(self):
        doc = self.d.doc
        if self.d.used_ext:
            doc['extensionsUsed'] = list(self.d.used_ext)
        if self.d.req_ext:
            doc['extensionsRequired'] = list(self.d.req_ext)
        for k in ('materials', 'meshes', 'textures', 'images', 'samplers', 'accessors', 'bufferViews'):
            if not doc.get(k):
                doc.pop(k, None)
        doc['buffers'] = [{'byteLength': len(self.d.bin)}]
        return gltf.encode(doc, bytes(self.d.bin), fix=True)


def write_scene(scene, generator=GENERATOR):
    """Scene -> GLB bytes (deterministic: same scene -> same bytes)."""
    w = _Writer(scene, generator)
    w.build()
    return w.finish()
