"""Blender-free assembly of the n64_adult body family (lane CHARS3): recipe -> Scene -> GLB.

A recipe is one flat JSON object: {'id', 'preset', body proportion fields (characters/gen/ext/adult.DEFAULTS),
'colors': {...}, 'face': {...}, 'props': [...]}. The body, its four textures (costume, face atlas, hair, emblem) and
all 13 clips come from characters/gen/ext/{adult,adult_paint,clips_adult}.py; core/ is only read (pose math, the six
combat clips). tall_v2 / masked characters never reach this module.
"""
import hashlib
import json

import numpy as np

from . import assemble as A
from . import gen as GEN
from .scene import Scene, SceneClip, SceneRig, SceneSocket

F32 = np.float32
PACK_ID = 'neon_city_night'
SKELETON = 'human16_v3'
CLIPS = ['carry', 'idle', 'interact', 'run', 'sit', 'talk', 'walk', 'idle_combat', 'swing', 'hurt', 'death', 'roll', 'block']
SLOTS = ('costume', 'face', 'headwear', 'emblem')
# vertex light ramp: cool violet shadow to white (the bake only reaches the upper half)
RAMP = [(36, 34, 78), (52, 50, 100), (70, 68, 122), (88, 86, 142), (106, 104, 160), (124, 122, 176), (142, 141, 191),
        (160, 160, 205), (180, 180, 218), (200, 201, 230), (220, 221, 241), (239, 240, 250), (255, 255, 255)]
BUDGET = {'body': 700, 'prop': 200}


class BudgetError(A.AssemblyError):
    pass


def modules(G=None):
    G = G or GEN.load()
    AD = G.ext('adult')
    return G, AD, G.ext('adult_paint'), G.ext('clips_adult'), G.core('pose')


def recipe_hash(recipe):
    return hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:10]


def body(recipe, G=None):
    """The generator mesh of a recipe (rest pose, Z-up)."""
    G, AD, AP, CL, PO = modules(G)
    return AD.person(recipe)


def _bake(mesh, a, soft):
    V32 = mesh.vertices
    low = a.params['height'] * .10

    def shade(vi, n):
        d = A._vdot(n)
        s = .78 + .21 * max(-.7, d) if vi not in soft else .86 + .12 * max(-.5, d)
        if float(V32[vi, 2]) < low:
            s -= .04
        return s
    return A._bake_colors(V32, mesh.faces, mesh.vertex_normals, RAMP, shade)


def _prop_socket(G, a, recipe, kind, h):
    AD = G.ext('adult')
    PR = G.ext('adult_props')
    m = PR.build(kind, a, recipe)
    mat = A._material('mat_%s_prop_%s_%s' % (PACK_ID, kind, h), 'tex_%s_prop_%s' % (h, kind), A.png_bytes(m['texture']),
                      PACK_ID, 'prop')
    me = A._mesh('kit_acc_%s_%s_mesh' % (m['slot'], kind), m['vertices'], m['faces'], [0] * len(m['faces']), m['uv'], [mat])
    if len(m['faces']) > BUDGET['prop']:
        raise BudgetError('prop %s: %d tris > %d' % (kind, len(m['faces']), BUDGET['prop']))
    me.corner_color = A._bake_colors(me.vertices, me.faces, me.vertex_normals, RAMP, lambda vi, n: .84 + .15 * max(-.6, A._vdot(n)))
    bone = m['bone']
    head = a.bones[bone]
    # prop vertices are authored in body space; the socket sits at the bone head, so re-base them
    me.vertices = (np.asarray(m['vertices'], dtype=np.float64) - np.asarray(head)).astype(F32)
    extras = {'n64_prop': {'kind': kind, 'slot': m['slot'], 'tris': len(m['faces']), 'removable': True}}
    return SceneSocket(name='kit_acc_%s_%s' % (m['slot'], kind), bone=bone, translation=(0., 0., 0.),
                       rotation=(0., 0., 0., 1.), mesh=me, extras=extras)


def clip(G, a, sk, name, order, metrics=None):
    """One 16-key clip: rotations from ext/clips_adult (core/ for the clips it does not re-author), root height =
    grounded lowest vertex + the clip's authored lift (the flight phase of the run)."""
    _, AD, AP, CL, PO = modules(G)
    rots = {n: np.zeros((A.KEYS, 4)) for n in order}
    root_t = np.zeros((A.KEYS, 3))
    for f in range(A.KEYS):
        local, lift = CL.sample(a, name, f, metrics)
        full = {n: local.get(n, (1., 0., 0., 0.)) for n in order}
        for n in order:
            rots[n][f] = A._q_gltf(full[n])
        V = sk.pose(PO, full)
        root_t[f] = (0., float(F32(-V[:, 2].min() + lift)), 0.)
    chan = []
    for n in A.pose_order(order, a.parents):
        chan.append((n, 'rotation'))
        if n == 'root':
            chan.append((n, 'translation'))
    return SceneClip(name=name, times=A._times(), rotations=rots, translations={'root': root_t}, channel_order=chan)


def character(recipe, clips=None, G=None):
    G, AD, AP, CL, PO = modules(G)
    a = AD.person(recipe)
    p = a.params
    h = recipe_hash(recipe)
    cid = recipe.get('id', 'adult')
    if len(a.faces) >= BUDGET['body']:
        raise BudgetError('%s: body %d tris, budget < %d' % (cid, len(a.faces), BUDGET['body']))
    tex = [('tex_' + h + '_cloth', AP.cloth(recipe)), ('tex_' + h + '_face', AP.face_atlas(recipe)),
           ('tex_' + h + '_hair', AP.hair(recipe)), ('tex_emblem_' + recipe.get('emblem_kind', 'star4'), AP.emblem(recipe))]
    spec = [('costume', 'baked_unlit', None), ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': int(recipe.get('expression', 0))}),
            ('headwear', 'baked_unlit', None), ('emblem', 'baked_unlit', None)]
    mats = []
    for (img_name, arr), (role, kind, atlas), slot in zip(tex, spec, SLOTS):
        mats.append(A._material('mat_%s_char_%s_%s' % (PACK_ID, slot, h), img_name, A.png_bytes(arr), PACK_ID, role, kind, atlas))
    used = sorted({AD.ROLE_SLOT[r] for r in a.roles})
    mats = [mats[i] for i in used]
    remap = {s: i for i, s in enumerate(used)}
    fmat = [remap[AD.ROLE_SLOT[r]] for r in a.roles]
    mesh = A._mesh('kit_body_mesh', a.vertices, a.faces, fmat, a.uv, mats)
    soft = set()
    for part in ('face', 'nose', 'hair', 'neck'):
        soft |= set(a.parts.get(part, []))
    mesh.corner_color = _bake(mesh, a, soft)
    order = list(a.bones)
    mesh.groups = order
    gi = {n: i for i, n in enumerate(order)}
    mesh.weights = [[(gi[n], float(F32(w))) for n, w in wts.items()] for wts in a.weights]
    extras = {'skeleton': SKELETON, 'params_json': json.dumps(recipe, sort_keys=True), 'stance': 'neutral',
              'topology': a.topology, 'preset': p['preset']}
    rig = SceneRig(object_name='rig_' + SKELETON, skeleton=SKELETON, bones={n: tuple(a.bones[n]) for n in order},
                   parents={n: a.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    for kind in recipe.get('props', []):
        sc.sockets.append(_prop_socket(G, a, recipe, kind, h))
    names = list(clips) if clips is not None else list(CLIPS)
    sk = A._Skinner(a.bones, a.parents, a.vertices, a.weights)
    metrics = PO.body_metrics(a)
    for name in names:
        sc.clips.append(clip(G, a, sk, name, order, metrics))
    sc.info = {'params': recipe, 'hash': h, 'stance': 'neutral', 'props': list(recipe.get('props', [])), 'pack': PACK_ID,
               'topology': a.topology, 'skeleton': SKELETON, 'generator': a, 'tris': len(a.faces)}
    return sc


def character_bytes(recipe, clips=None, G=None):
    from . import writer
    sc = character(recipe, clips=clips, G=G)
    return writer.write_scene(sc, writer.GENERATOR), sc
