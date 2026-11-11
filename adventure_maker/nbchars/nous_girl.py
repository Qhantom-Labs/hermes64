"""Blender-free assembly of nous_girl (lane CAST2): the captive girl -> Scene -> GLB.

She is a delta on the approved hero base (ext/tall_v3.py revision 3, rig human16_v1): ext/nous_girl.py builds the
body, ext/nous_girl_paint.py her palette and atlases, ext/nous_girl_props.py the headphones (a separate rigid mesh on
the head bone, removable), ext/clips_nous_girl.py her clips. The base builder needs the restricted round-21 modules
exactly as nbchars/tall_v3.py does (loaded read-only at build time, never vendored); nothing of the hero's paint,
palette or head gear is in her GLB.

Seated clips (captive, captive_look, captive_struggle) carry a root translation that puts her on the captive chair
when her origin is the chair's origin (see ext/clips_nous_girl.py and seat_report()).
"""
import hashlib
import json

import numpy as np

from . import assemble as A
from . import tall_v3 as TV
from .scene import Scene, SceneClip, SceneRig, SceneSocket

F32 = np.float32
PRESET = 'nous_girl'
ID = 'nous_girl'
SKELETON = 'human16_v1'
BUDGET = {'body': 700, 'prop': 200}
PROPS = ('headphones',)


def modules(G=None):
    """(G, cameo, tall_v3, nous_girl, nous_girl_paint, nous_girl_props, clips_nous_girl, pose, tall_v3_paint)."""
    G, CAM, CAMP, T3, T3P, CL, PO = TV.modules(G)
    NG = G.ext('nous_girl'); NGP = G.ext('nous_girl_paint'); NPR = G.ext('nous_girl_props'); CLN = G.ext('clips_nous_girl')
    if NGP.PACK_ID not in G.inline:
        G.inline[NGP.PACK_ID] = {'pack': NGP.PACK}
    return G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P


def recipe(**over):
    """Her recipe: the base family's cast entry as the parameter carrier, then her own values (ext/nous_girl.PARAMS)."""
    params, _ = TV.r21_params()
    params.update(over)
    return {'id': ID, 'preset': PRESET, 'params': params, 'stance': 'neutral', 'props': list(PROPS)}


def body(rec, G=None):
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    return NG.person(T3, CAM, rec['params'])


def textures(rec, a, G=None):
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    pack = G.pack(NGP.PACK_ID)
    p = a.params
    return NGP.costume_atlas(pack, p), NGP.face_atlas(pack, p, T3P._lower_face), NGP.hair_texture(pack, p)


def seat_offset(rec=None, G=None, a=None):
    """Root translation (x, y, z) m of the seated clips (character space: front = -y, z up), solved on key 0 of
    `captive`."""
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    a = a if a is not None else body(rec or recipe(), G)
    sk = A._Skinner(a.bones, a.parents, a.vertices, a.weights)
    local, _ = CLN.sample(a, 'captive', 0, PO.body_metrics(a))
    V = sk.pose(PO, {n: local.get(n, (1., 0., 0., 0.)) for n in a.bones})
    return tuple(float(F32(c)) for c in CLN.seat(a, V))


def _clip(G, a, sk, name, order, metrics, seat_t):
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    rots = {n: np.zeros((A.KEYS, 4)) for n in order}
    root_t = np.zeros((A.KEYS, 3))
    for f in range(A.KEYS):
        local, lift = CLN.sample(a, name, f, metrics)
        full = {n: local.get(n, (1., 0., 0., 0.)) for n in order}
        for n in order:
            rots[n][f] = A._q_gltf(full[n])
        if name in CLN.SEATED:
            root_t[f] = A._to_gltf(seat_t)
        else:
            V = sk.pose(PO, full)
            root_t[f] = (0., float(F32(-V[:, 2].min() + lift)), 0.)
    chan = []
    for n in A.pose_order(order, a.parents):
        chan.append((n, 'rotation'))
        if n == 'root':
            chan.append((n, 'translation'))
    return SceneClip(name=name, times=A._times(), rotations=rots, translations={'root': root_t}, channel_order=chan)


def _prop_socket(G, a, pack, kind, h, ramp):
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    if kind != NPR.KIND:
        raise A.AssemblyError('nous_girl has the prop %r, not %r' % (NPR.KIND, kind))
    m = NPR.build(a.params['height'])
    if len(m.faces) > BUDGET['prop']:
        raise A.AssemblyError('prop %s: %d tris > %d' % (kind, len(m.faces), BUDGET['prop']))
    mat = A._material('mat_%s_prop_%s_%s' % (pack['id'], kind, h), 'tex_%s_prop_%s' % (h, kind),
                      A.png_bytes(NPR.texture(pack)), pack['id'], 'prop')
    me = A._mesh('kit_acc_%s_%s_mesh' % (m.slot, kind), m.vertices, m.faces, [0] * len(m.faces), m.uv, [mat])
    me.corner_color = A._bake_colors(me.vertices, me.faces, me.vertex_normals, ramp,
                                     lambda vi, n: .84 + .15 * max(-.6, A._vdot(n)))
    bone = A.SLOT_BONE[m.slot]
    # vertices are authored in body space; the socket sits at the bone head (rest pose), so re-base them
    me.vertices = (np.asarray(m.vertices, dtype=np.float64) - np.asarray(a.bones[bone])).astype(F32)
    extras = {'n64_prop': {'kind': kind, 'slot': m.slot, 'tris': len(m.faces), 'removable': True}}
    return SceneSocket(name='kit_acc_%s_%s' % (m.slot, kind), bone=bone, translation=(0., 0., 0.),
                       rotation=(0., 0., 0., 1.), mesh=me, extras=extras)


def character(rec=None, clips=None, G=None, props=None):
    G, CAM, T3, NG, NGP, NPR, CLN, PO, T3P = modules(G)
    rec = rec or recipe()
    PP = G.core('people')
    pack = G.pack(NGP.PACK_ID)
    a = body(rec, G)
    p = a.params
    if len(a.faces) >= BUDGET['body']:
        raise A.AssemblyError('%s: body %d tris, budget < %d' % (rec['id'], len(a.faces), BUDGET['body']))
    h = hashlib.sha256(json.dumps([rec['preset'], NG.REVISION, p], sort_keys=True).encode()).hexdigest()[:10]
    cloth, face, hair = textures(rec, a, G)
    names = list(clips) if clips is not None else list(CLN.CLIPS)
    cells = {c: PP.EXPRESSIONS.index(e) for c, e in sorted(CLN.EXPRESSION.items()) if c in names}
    tex = [('tex_' + h + '_cloth', cloth), ('tex_' + h + '_face', face), ('tex_' + h + '_hair', hair)]
    spec = [('costume', 'baked_unlit', None),
            ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': p['expression'], 'clip_cells': cells}),
            ('headwear', 'baked_unlit', None)]
    mats = []
    for (img_name, arr), (role, kind, atlas), slot in zip(tex, spec, ('costume', 'face', 'headwear')):
        mats.append(A._material('mat_%s_char_%s_%s' % (pack['id'], slot, h), img_name, A.png_bytes(arr), pack['id'], role, kind, atlas))
    fmat = [A.HUMAN_ROLE_SLOT[r] for r in a.roles]
    mesh = A._mesh('kit_body_mesh', a.vertices, a.faces, fmat, a.uv, mats)
    ramp = A._ramp(G, pack)
    V32 = mesh.vertices
    low = p['height'] * .12
    soft = set()
    ao = getattr(a, 'ao', {})
    for part in ('face', 'nose'):
        soft |= set(a.parts.get(part, []))

    def shade(vi, n):                      # the hero's baked light (nbchars/tall_v3.character), unchanged
        d = A._vdot(n)
        s = .76 + .23 * max(-.7, d) if vi not in soft else .84 + .14 * max(-.5, d)
        if float(V32[vi, 2]) < low:
            s -= .045
        return s * ao.get(vi, 1.)
    mesh.corner_color = A._bake_colors(V32, mesh.faces, mesh.vertex_normals, ramp, shade)
    order = list(a.bones)
    mesh.groups = order
    gi = {n: i for i, n in enumerate(order)}
    mesh.weights = [[(gi[n], float(F32(w))) for n, w in wts.items()] for wts in a.weights]
    extras = {'skeleton': SKELETON, 'params_json': json.dumps(p, sort_keys=True), 'stance': rec['stance'],
              'topology': a.topology, 'preset': rec['preset'], 'revision': NG.REVISION}
    rig = SceneRig(object_name='rig_' + SKELETON, skeleton=SKELETON, bones={n: tuple(a.bones[n]) for n in order},
                   parents={n: a.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    kinds = list(rec.get('props', PROPS)) if props is None else list(props)
    prop_tris = {}
    for kind in kinds:
        s = _prop_socket(G, a, pack, kind, h, ramp)
        prop_tris[kind] = len(s.mesh.faces)
        sc.sockets.append(s)
    sk = A._Skinner(a.bones, a.parents, a.vertices, a.weights)
    metrics = PO.body_metrics(a)
    seat_t = seat_offset(G=G, a=a)
    for name in names:
        sc.clips.append(_clip(G, a, sk, name, order, metrics, seat_t))
    for m in mats:
        at = m.n64.get('atlas')
        if at and names:
            m.atlas_cell = (int(at.get('clip_cells', {}).get(names[-1], at['cell'])), int(at['cols']), int(at['rows']))
    sc.info = {'params': p, 'hash': h, 'stance': rec['stance'], 'props': kinds, 'prop_tris': prop_tris, 'pack': pack['id'],
               'topology': a.topology, 'skeleton': SKELETON, 'generator': a, 'tris': len(a.faces), 'preset': rec['preset'],
               'seat': seat_t}
    return sc


def character_bytes(rec=None, clips=None, G=None, props=None):
    from . import writer
    sc = character(rec, clips=clips, G=G, props=props)
    return writer.write_scene(sc, writer.GENERATOR), sc
