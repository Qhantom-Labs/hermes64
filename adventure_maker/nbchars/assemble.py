"""Blender-free assembly: vendored generator -> Scene.

A line-by-line port of the Blender-side assembly (core/blender.py assemble/_finish/add_prop/pose/make_actions and
core/combat_blender.py assemble_enemy/make_enemy_actions/export_weapon/export_projectile). Where Blender computed a
value the bytes depend on (smooth vertex normals for the baked vertex light, the BYTE_COLOR conversion, the armature
deform used for the grounding offset) the float32 behaviour is reproduced by blendmath.py / numpy.
"""
import hashlib
import json
import math
import struct
import zlib

import numpy as np

from . import blendmath as BM
from . import gen as GEN
from .scene import Scene, SceneClip, SceneMaterial, SceneMesh, SceneRig, SceneSocket

F32 = np.float32
FPS = 15
KEYS = 16
HUMAN_ROLE_SLOT = {'costume': 0, 'coat': 0, 'face': 1, 'animal_face': 1, 'headwear': 2}
SLOT_BONE = {'hand_l': 'hand_l', 'hand_r': 'hand_r', 'head': 'head', 'back': 'spine', 'belt': 'pelvis'}
ATTACH_SLOTS = [('hand_l', 'hand_l'), ('hand_r', 'hand_r'), ('head', 'head'), ('back', 'spine'), ('belt', 'pelvis')]
SQRT_HALF = float(F32(math.sqrt(.5)))
ENEMY_SOCKETS = {'cairn_dasher': [('attach_ram', 'head', (0, -.30, -.02)), ('attach_core', 'chest', (0, -.05, .02))],
                 'reed_warden': [('attach_lob', 'crest', (0, .02, .24)), ('attach_core', 'body', (0, -.02, .16))]}
ENEMY_ROOT_MOTION = 'none: root never animated; body bone carries vertical offset only'


class AssemblyError(RuntimeError):
    pass


# ------------------------------------------------------------------ helpers
def png_bytes(arr):
    """Byte-identical to core/paint.png (8-bit RGB/RGBA, filter 0 rows, zlib level 9), without touching disk."""
    arr = np.asarray(arr, dtype=np.uint8)
    h, w, c = arr.shape

    def chunk(t, p):
        return struct.pack('!I', len(p)) + t + p + struct.pack('!I', zlib.crc32(t + p) & 0xffffffff)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(b''.join(b'\0' + r.tobytes() for r in arr), 9)) + chunk(b'IEND', b'')
    return data


def _light():
    """mathutils Vector((-.45, -.7, .8)).normalized(): float32 storage, double length, float32 reciprocal multiply."""
    lx = np.array([-.45, -.7, .8], F32)
    norm = math.sqrt(float(F32(lx[2] * lx[2])) + float(F32(lx[1] * lx[1])) + float(F32(lx[0] * lx[0])))
    return (lx * F32(F32(1.0) / F32(norm))).astype(F32)


LIGHT = _light()


def _vdot(n, light=LIGHT):
    """mathutils Vector.dot: float32 products accumulated in double, last component first."""
    return float(F32(n[2] * light[2])) + float(F32(n[1] * light[1])) + float(F32(n[0] * light[0]))


def _material(name, image_name, png, pack_id, role, kind='baked_unlit', atlas=None):
    n64 = {'kind': kind, 'role': role, 'pack': pack_id, 'texture': image_name, 'vertex_color_encoding': 'linear_gltf'}
    if atlas:
        n64['atlas'] = atlas
    cell = (int(atlas['cell']), int(atlas['cols']), int(atlas['rows'])) if atlas else None
    return SceneMaterial(name=name, image_name=image_name, png=png, n64=n64, atlas_cell=cell)


def _bake_colors(V32, F, vn, ramp, shade):
    """Corner BYTE_COLOR sRGB bytes exactly as the Blender loops did (round(shade * (N - 1)) into the light ramp)."""
    N = len(ramp)
    out = np.empty((len(F) * 3, 4), np.uint8)
    rampb = [tuple(int(c) for c in r) for r in ramp]
    k = 0
    for f in F:
        for vi in f:
            ix = max(0, min(N - 1, round(shade(int(vi), vn[vi]) * (N - 1))))
            r = rampb[ix]
            out[k] = (r[0], r[1], r[2], 255)
            k += 1
    return out


def _mesh(name, vertices, faces, face_material, uv, materials):
    V32 = np.asarray(vertices, dtype=np.float64).astype(F32)
    F = np.asarray(faces, dtype=np.int64)
    if F.ndim != 2 or F.shape[1] != 3:
        raise AssemblyError('%s: only triangle meshes are supported (got face sizes %s)' % (name, sorted({len(f) for f in faces})))
    cuv = np.asarray([pt for tri in uv for pt in tri], dtype=np.float64).astype(F32).reshape(-1, 2)
    if len(cuv) != 3 * len(F):
        raise AssemblyError('%s: %d UV corners for %d triangles' % (name, len(cuv), len(F)))
    vn = BM.vertex_normals(V32, F)
    return SceneMesh(name=name, vertices=V32, faces=F, face_material=np.asarray(face_material, dtype=np.int64),
                     corner_uv=cuv, corner_color=None, materials=materials, vertex_normals=vn)


def _ramp(G, pack):
    paint = G.core('paint')
    return [paint.color(pack, c) for c in pack['light_ramp']]


# ------------------------------------------------------------------ LBS for the grounding offset
def _fk(PO, bones, parents, local):
    qw, pos = PO._fk_world(bones, parents, local)
    return qw, pos


def _quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


class _Skinner:
    """Blender armature-modifier equivalent (all influences, divided by the total weight) in float64."""

    def __init__(self, bones, parents, vertices, weights):
        self.bones, self.parents = bones, parents
        self.names = list(bones)
        idx = {n: i for i, n in enumerate(self.names)}
        self.V = np.asarray(vertices, dtype=np.float64)
        n = len(self.V)
        W = np.zeros((n, len(self.names)))
        for i, w in enumerate(weights):
            for b, x in w.items():
                W[i, idx[b]] += float(F32(x))
        tot = W.sum(1, keepdims=True)
        self.W = np.where(tot > 1e-4, W / np.where(tot > 1e-4, tot, 1.), 0.)
        self.H = np.array([bones[b] for b in self.names], dtype=np.float64)

    def pose(self, PO, local):
        qw, pos = PO._fk_world(self.bones, self.parents, local)
        out = np.zeros_like(self.V)
        for j, b in enumerate(self.names):
            w = self.W[:, j]
            if not w.any():
                continue
            R = _quat_mat(qw[b])
            p = (self.V - self.H[j]) @ R.T + np.asarray(pos[b])
            out += w[:, None] * p
        return out


# ------------------------------------------------------------------ characters
def _character_textures(G, packname, pack, values, animal, seed):
    paint = G.core('paint')
    geometry = G.core('geometry')
    if not animal and values and values.get('head_mode') == 'visor':
        try:
            cameo = G.core('cameo')
            cameo_paint = G.core('cameo_paint')
        except ImportError as e:
            raise AssemblyError('visor cameo characters need core/cameo.py + core/cameo_paint.py, which are restricted '
                                'likeness code and not vendored; pass a generator root that has them') from e
        people_paint = G.core('people_paint')
        p = dict(pack.get('face_defaults', {})); p.update(values)
        a = cameo.person(p); p = a.params
        h = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10]
        tex = [('tex_' + h + '_cloth', cameo_paint.costume_atlas(pack, p)), ('tex_' + h + '_face', people_paint.face_atlas(pack, p)),
               ('tex_' + h + '_hair', cameo_paint.headwear(pack, p))]
        spec = [('costume', 'baked_unlit', None), ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': p['expression']}),
                ('headwear', 'baked_unlit', None)]
        return a, p, h, tex, spec
    if not animal and values and values.get('head_mode') == 'face' and 'hair' in values:
        people = G.core('people'); people_paint = G.core('people_paint')
        p = dict(pack.get('face_defaults', {})); p.update(values or {})
        a = people.person(p); p = a.params
        h = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10]
        tex = [('tex_' + h + '_cloth', people_paint.costume_atlas(pack, p)), ('tex_' + h + '_face', people_paint.face_atlas(pack, p)),
               ('tex_' + h + '_hair', people_paint.hair_texture(pack, p))]
        spec = [('costume', 'baked_unlit', None), ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': p['expression']}),
                ('headwear', 'baked_unlit', None)]
        return a, p, h, tex, spec
    p = dict(pack['animal_defaults' if animal else 'character_defaults']); p.update(values or {})
    a = geometry.quadruped(p) if animal else geometry.humanoid(p); p = a.params
    h = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10]
    kind = 'quad' if animal else 'human'
    cloth = paint.paint(pack, p, kind, seed)
    face = paint.face_atlas(pack, p, kind)
    hairparams = dict(p)
    if not animal and p['headwear'] == 'bald':
        hairparams['headwear_color'] = p['skin']
    hair = paint.hair(pack, dict(headwear_color=p['coat_color_1'])) if animal else paint.hair(pack, hairparams)
    if not animal and p['head_mode'] == 'faceless':
        hair = paint.hood(pack, p)
    tex = [('tex_' + h + '_cloth', cloth), ('tex_' + h + '_face', face), ('tex_' + h + '_hair', hair)]
    spec = [('coat' if animal else 'costume', 'baked_unlit', None),
            ('face', 'face_atlas', {'cols': 2, 'rows': 1, 'cell': 0, 'clip_cells': {'sleep_curled': 1}} if animal else {'cols': 4, 'rows': 2, 'cell': p['face']}),
            ('headwear', 'baked_unlit', None)]
    return a, p, h, tex, spec


def character(packname, values=None, animal=False, seed=19, stance=None, props=(), clips=None, G=None):
    """core/blender.assemble(packname, values, animal, seed, actions=True, stance, prop_list) without Blender.
    clips: clip names to key (default the 7 shared clips of the kind)."""
    G = G or GEN.load()
    PO = G.core('pose')
    pack = G.pack(packname)
    a, p, h, tex, spec = _character_textures(G, packname, pack, values, animal, seed)
    prop_list = list(props or ())
    if not animal and stance:
        PC = G.core('posecheck')
        stance, prop_list, _tried = PC.resolve_stance(a, stance, prop_list)
    mats = []
    for (img_name, arr), (role, kind, atlas), slot in zip(tex, spec, ('costume', 'face', 'headwear')):
        mats.append(_material('mat_%s_char_%s_%s' % (packname, slot, h), img_name, png_bytes(arr), pack['id'], role, kind, atlas))
    fmat = [HUMAN_ROLE_SLOT[r] for r in a.roles]
    body = _mesh('kit_body_mesh', a.vertices, a.faces, fmat, a.uv, mats)
    ramp = _ramp(G, pack)
    soft = set(a.parts.get('head', [])) | set(a.parts.get('neck', [])) if animal else set(a.parts.get('hood', []))
    V32 = body.vertices
    low = a.params['height'] * .12 if not animal else 0.0

    def shade(vi, n):
        d = _vdot(n)
        s = .76 + .23 * max(-.7, d) if vi not in soft else .82 + .14 * max(-.35, d)
        if not animal and float(V32[vi, 2]) < low:
            s -= .045
        return s
    body.corner_color = _bake_colors(V32, body.faces, body.vertex_normals, ramp, shade)
    order = list(a.bones)
    body.groups = order
    gi = {n: i for i, n in enumerate(order)}
    body.weights = [[(gi[n], float(F32(w))) for n, w in wts.items()] for wts in a.weights]
    skeleton = 'quad16_v1' if animal else 'human16_v1'
    extras = {'skeleton': skeleton, 'params_json': json.dumps(p, sort_keys=True), 'stance': stance or 'neutral',
              'topology': getattr(a, 'topology', 'human16_hood_v1' if not animal else 'quad16_v1')}
    rig = SceneRig(object_name='rig_' + skeleton, skeleton=skeleton, bones={n: tuple(a.bones[n]) for n in order},
                   parents={n: a.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='animal' if animal else 'human', rig=rig, body=body)
    if not animal:
        for slot, bone in ATTACH_SLOTS:
            sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(SQRT_HALF, 0., 0., SQRT_HALF)))
        for kind in prop_list:
            sc.sockets.append(_prop_socket(G, a, pack, packname, kind, stance))
    clip_names = list(clips) if clips is not None else list(PO.HCLIPS if not animal else PO.ACLIPS)
    sk = _Skinner(a.bones, a.parents, a.vertices, a.weights)
    metrics = PO.body_metrics(a)
    for clip in clip_names:
        sc.clips.append(_character_clip(PO, a, sk, metrics, clip, stance, order))
    # the face atlas cell Blender leaves in the Mapping node is the one of the last keyed clip
    for m in mats:
        at = m.n64.get('atlas')
        if at and clip_names:
            cells = dict(at.get('clip_cells', {}))
            m.atlas_cell = (int(cells.get(clip_names[-1], at['cell'])), int(at['cols']), int(at['rows']))
    sc.info = {'params': p, 'hash': h, 'stance': stance or 'neutral', 'props': prop_list, 'pack': packname,
               'topology': extras['topology'], 'skeleton': skeleton, 'generator': a}
    return sc


def _prop_socket(G, a, pack, packname, kind, stance):
    props = G.core('props'); attach = G.core('attach')
    m = props.build(kind)
    bone = SLOT_BONE[m.slot]
    q_r, t_r = attach.attach(a, stance, kind)
    mat = _material('mat_' + packname + '_prop_' + kind, 'tex_' + packname + '_prop_' + kind,
                    png_bytes(props.texture(pack, kind)), pack['id'], 'prop')
    me = _mesh('kit_acc_%s_%s_mesh' % (m.slot, kind), m.vertices, m.faces, [0] * len(m.faces), m.uv, [mat])
    ramp = _ramp(G, pack)
    me.corner_color = _bake_colors(me.vertices, me.faces, me.vertex_normals, ramp,
                                   lambda vi, n: .8 + .2 * max(-.7, _vdot(n)))
    head = a.bones[bone]
    tr = _to_gltf((t_r[0] - head[0], t_r[1] - head[1], t_r[2] - head[2]))
    w, x, y, z = q_r
    extras = {'n64_prop': {'kind': kind, 'slot': m.slot, 'tris': len(m.faces), 'rest_q': list(q_r), 'rest_t': list(t_r)}}
    return SceneSocket(name='kit_acc_%s_%s' % (m.slot, kind), bone=bone, translation=tr, rotation=(x, z, -y, w),
                       mesh=me, extras=extras)


def pose_order(order, parents):
    """rig.pose.bones order: depth-first over the hierarchy, roots and children in bone creation order (Blender
    rebuilds pose channels by walking armature.bonebase / bone.childbase, which keep creation order)."""
    kids = {n: [c for c in order if parents[c] == n] for n in order}
    out = []

    def visit(n):
        out.append(n)
        for c in kids[n]:
            visit(c)
    for n in order:
        if parents[n] is None:
            visit(n)
    return out


def _to_gltf(v):
    return (v[0], v[2], -v[1])


def _q_gltf(q):
    w, x, y, z = q
    return (x, z, -y, w)


def _times():
    return np.array([f / FPS for f in range(KEYS)], dtype=np.float64).astype(F32)


def _character_clip(PO, a, sk, metrics, clip, stance, order):
    rots = {n: np.zeros((KEYS, 4)) for n in order}
    root_t = np.zeros((KEYS, 3))
    H = a.params.get('height', 1.)
    for f in range(KEYS):
        local = PO.local_rotations(a.bones, H, a.kind, clip, f / FPS, stance or 'neutral', metrics)
        for n in order:
            rots[n][f] = _q_gltf(local.get(n, (1., 0., 0., 0.)))
        full = {n: local.get(n, (1., 0., 0., 0.)) for n in order}
        V = sk.pose(PO, full)
        bottom = float(F32(V[:, 2].min()))
        root_t[f] = (0., -bottom, 0.)
    chan = []
    for n in pose_order(order, a.parents):
        chan.append((n, 'rotation'))
        if n == 'root':
            chan.append((n, 'translation'))
    return SceneClip(name=clip, times=_times(), rotations=rots, translations={'root': root_t}, channel_order=chan)


# ------------------------------------------------------------------ enemies
def _enemy_order(parents):
    out, seen = [], set()

    def visit(n):
        if n in seen:
            return
        if parents[n]:
            visit(parents[n])
        seen.add(n); out.append(n)
    for n in parents:
        visit(n)
    return out


def enemy(packname, eid, G=None):
    """core/combat_blender.assemble_enemy(packname, eid, actions=True) without Blender."""
    G = G or GEN.load()
    EN = G.core('enemies'); EPO = G.core('enemy_pose'); EPA = G.core('enemy_paint')
    pack = G.pack(packname)
    m = EN.build(eid)
    roles, fell = EPA.roles_for(pack, eid)
    atlas = {'cols': 2, 'rows': 2, 'cell': 0, 'clip_cells': dict(EPO.FACE_CELLS['clip_cells'])}
    mc = _material('mat_%s_%s_coat' % (packname, eid), 'tex_%s_%s_coat' % (packname, eid),
                   png_bytes(EPA.coat_atlas(pack, eid)), pack['id'], 'coat')
    mf = _material('mat_%s_%s_face' % (packname, eid), 'tex_%s_%s_face' % (packname, eid),
                   png_bytes(EPA.face_atlas(pack, eid)), pack['id'], 'face', 'face_atlas', atlas)
    mc.n64['roles'] = roles
    mf.n64['cells'] = EPO.FACE_CELLS['cells']
    fmat = [1 if r == 'face' else 0 for r in m.roles]
    body = _mesh('kit_body_mesh', m.vertices, m.faces, fmat, m.uv, [mc, mf])
    ramp = _ramp(G, pack)
    H = max(v[2] for v in m.vertices)
    floor_dark = .10 * H
    V32 = body.vertices

    def shade(vi, n):
        s = .78 + .22 * max(-.6, _vdot(n))
        if float(V32[vi, 2]) < floor_dark:
            s -= .045
        return s
    body.corner_color = _bake_colors(V32, body.faces, body.vertex_normals, ramp, shade)
    order = _enemy_order(m.parents)
    body.groups = order
    gi = {n: i for i, n in enumerate(order)}
    body.weights = [[(gi[n], float(F32(w))) for n, w in wts.items()] for wts in m.weights]
    extras = {'skeleton': m.rig, 'topology': m.topology, 'enemy_id': eid, 'template': EN.TEMPLATE[eid],
              'clips': json.dumps(EPO.ENEMY_CLIPS), 'fsm_clip': json.dumps(EPO.FSM_CLIP, sort_keys=True),
              'root_motion': ENEMY_ROOT_MOTION}
    rig = SceneRig(object_name='rig_' + m.rig, skeleton=m.rig, bones={n: tuple(m.bones[n]) for n in order},
                   parents={n: m.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='enemy', rig=rig, body=body)
    for nm, bone, off in ENEMY_SOCKETS[eid]:
        sc.sockets.append(SceneSocket(name=nm, bone=bone, translation=_to_gltf(off)))
    bodyb = EPO.BODY_BONE[m.id]
    for clip in EPO.ENEMY_CLIPS:
        rots = {n: np.zeros((KEYS, 4)) for n in order if n != 'root'}
        tr = np.zeros((KEYS, 3))
        for f in range(KEYS):
            local, dz, lift = EPO.local_pose(m, clip, f / FPS)
            for n in rots:
                rots[n][f] = _q_gltf(local.get(n, (1., 0., 0., 0.)))
            tr[f] = (0., dz, 0.)          # pose location (bone Y = glTF Y), added to the rest translation by the writer
        chan = []
        for n in pose_order(order, m.parents):
            if n == 'root':
                continue
            chan.append((n, 'rotation'))
            if n == bodyb:
                chan.append((n, 'translation'))
        sc.clips.append(SceneClip(name=clip, times=_times(), rotations=rots, translations={bodyb: tr}, channel_order=chan))
    # Mapping node keeps the cell of the last keyed clip
    last = EPO.ENEMY_CLIPS[-1]
    mf.atlas_cell = (int(atlas['clip_cells'].get(last, atlas['cell'])), 2, 2)
    sc.info = {'pack': packname, 'enemy_id': eid, 'roles': roles, 'roles_fallback': fell, 'skeleton': m.rig,
               'topology': m.topology, 'template': EN.TEMPLATE[eid], 'tris_body': len(m.faces), 'generator': m}
    return sc


def weapon_socket(G, sc, packname):
    """core/combat_blender.add_weapon: the trail staff as a rigid node on hand_r at its rest grip."""
    WP = G.core('weapon'); RL = G.core('roles'); PO = G.core('pose')
    pack = G.pack(packname)
    a = sc.info['generator']
    m = WP.build()
    roles, _ = RL.resolve(pack, ['wood', 'wood_dark', 'wrap', 'metal', 'metal_dark', 'accent'])
    mat = _material('mat_%s_weapon_%s' % (packname, WP.WEAPON_ID), 'tex_%s_weapon_%s' % (packname, WP.WEAPON_ID),
                    png_bytes(WP.texture(pack, roles)), pack['id'], 'prop')
    me = _mesh(WP.NODE_NAME + '_mesh', m.vertices, m.faces, [0] * len(m.faces), m.uv, [mat])
    me.corner_color = _bake_colors(me.vertices, me.faces, me.vertex_normals, _ramp(G, pack),
                                   lambda vi, n: .80 + .20 * max(-.7, _vdot(n)))
    body = PO.body_metrics(a)
    g = WP.grip_offset(a.bones, body)
    extras = {'n64_prop': {'kind': WP.WEAPON_ID, 'slot': 'hand_r', 'tris': len(m.faces), 'grip': WP.grip_gltf(a.bones, body)}}
    return SceneSocket(name=WP.NODE_NAME, bone='hand_r', translation=_to_gltf(g), rotation=_q_gltf(WP.REST_Q_BLENDER),
                       mesh=me, extras=extras)


# ------------------------------------------------------------------ static props (weapon, projectile)
def weapon(packname, G=None):
    G = G or GEN.load()
    WP = G.core('weapon'); RL = G.core('roles')
    pack = G.pack(packname)
    m = WP.build()
    roles, fell = RL.resolve(pack, ['wood', 'wood_dark', 'wrap', 'metal', 'metal_dark', 'accent'])
    mat = _material('mat_%s_weapon_%s' % (packname, WP.WEAPON_ID), 'tex_%s_weapon_%s' % (packname, WP.WEAPON_ID),
                    png_bytes(WP.texture(pack, roles)), pack['id'], 'prop')
    mat.n64['roles'] = roles
    me = _mesh(WP.NODE_NAME + '_mesh', m.vertices, m.faces, [0] * len(m.faces), m.uv, [mat])
    me.corner_color = _bake_colors(me.vertices, me.faces, me.vertex_normals, _ramp(G, pack),
                                   lambda vi, n: .80 + .20 * max(-.7, _vdot(n)))
    extras = {'n64_prop': {'kind': WP.WEAPON_ID, 'slot': 'hand_r', 'tris': len(m.faces), 'origin': 'grip centre',
                           'axis': '+Y glTF (shaft toward the tip)', 'tip_m': WP.TIP_LEN, 'pommel_m': WP.POMMEL_LEN,
                           'rest_rotation_on_hand_r_xyzw': WP.REST_Q_GLTF_XYZW, 'roles_fallback': fell}}
    return Scene(kind='prop', rig=None, body=me, body_object=WP.NODE_NAME, body_extras=extras,
                 info={'pack': packname, 'id': WP.WEAPON_ID, 'kind': 'weapon', 'tris': len(m.faces), 'roles': roles,
                       'roles_fallback': fell})


def projectile(packname, G=None):
    G = G or GEN.load()
    EPR = G.core('enemy_props'); RL = G.core('roles')
    pack = G.pack(packname)
    m = EPR.burr()
    roles, fell = RL.resolve(pack, ['burr', 'burr_tip', 'weave_dark'])
    mat = _material('mat_%s_%s' % (packname, EPR.PROJ_ID), 'tex_%s_%s' % (packname, EPR.PROJ_ID),
                    png_bytes(EPR.texture(pack, roles)), pack['id'], 'prop')
    mat.n64['roles'] = roles
    me = _mesh(EPR.NODE_NAME + '_mesh', m.vertices, m.faces, [0] * len(m.faces), m.uv, [mat])
    me.corner_color = _bake_colors(me.vertices, me.faces, me.vertex_normals, _ramp(G, pack),
                                   lambda vi, n: .80 + .20 * max(-.7, _vdot(n)))
    extras = {'n64_prop': {'kind': EPR.PROJ_ID, 'tris': len(m.faces), 'origin': 'centre',
                           'used_by': 'reed_warden attach_lob (optional)'}}
    return Scene(kind='prop', rig=None, body=me, body_object=EPR.NODE_NAME, body_extras=extras,
                 info={'pack': packname, 'id': EPR.PROJ_ID, 'kind': 'projectile', 'tris': len(m.faces), 'roles': roles,
                       'roles_fallback': fell})
