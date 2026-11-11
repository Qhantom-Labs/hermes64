"""Blender-free assembly of the tall_v3 visor body (lane CHARS4): the fixed round-21 character -> Scene -> GLB.

tall_v3 is a delta on the round-21 builder (characters/gen/ext/tall_v3.py). The round-21 builder and its paint
(core/cameo.py, core/cameo_paint.py) and the cameo pack are restricted likeness code: they are NOT vendored into this
repository. They are loaded read-only from the oracle lane at build time (NBCHARS_RESTRICTED_ROOT, default the
sibling lane-characters checkout) into the vendored generator package, exactly as the parity tool reproduces the
frozen cameo. Without that root the build stops with a clear error; the built GLB is the shipped artefact.

preset 'tall_v2' through this module rebuilds round 21 itself (same mesh, 'confident' stance, shared clips): the
same-scale control for stills and the parity fixture. It never replaces cameo/cameo_visor_01.glb.
"""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

from . import assemble as A
from . import gen as GEN
from .scene import Scene, SceneClip, SceneRig, SceneSocket

F32 = np.float32
PACK = 'cameo_visor'
SKELETON = 'human16_v1'
CLIPS = ['carry', 'idle', 'interact', 'run', 'sit', 'talk', 'walk']
BUDGET = {'body': 700, 'prop': 200}
CAST_ID = 'cameo_visor_01'
RESTRICTED = ('cameo', 'cameo_paint')


class RestrictedSourceError(A.AssemblyError):
    pass


def restricted_root():
    return Path(os.environ.get('NBCHARS_RESTRICTED_ROOT') or GEN.REPO.parent / 'lane-characters').resolve()


def modules(G=None):
    """(G, cameo, cameo_paint, tall_v3, tall_v3_paint, clips_tall_v3, pose). Loads the two restricted modules from
    the oracle lane into the vendored core package (their `from . import people` binds the vendored modules)."""
    G = G or GEN.load()
    root = restricted_root()
    mods = []
    for name in RESTRICTED:
        full = G.pkg + '.' + name
        if full not in sys.modules:
            f = root / 'core' / (name + '.py')
            if not f.is_file():
                raise RestrictedSourceError('tall_v3 needs the restricted round-21 builder core/%s.py (not vendored); '
                                            'set NBCHARS_RESTRICTED_ROOT (looked in %s)' % (name, root))
            spec = importlib.util.spec_from_file_location(full, str(f), loader=GEN._CompatLoader(full, str(f)))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[full] = mod
            try:
                spec.loader.exec_module(mod)
            except BaseException:
                sys.modules.pop(full, None)
                raise
        mods.append(sys.modules[full])
    if PACK not in G.inline:
        G.inline[PACK] = {'pack': json.loads((root / 'packs' / PACK / 'pack.json').read_text(encoding='utf-8'))}
    G.ext('clips_adult')         # the planted-foot cycle clips_tall_v3 retargets (its `from . import clips_adult`)
    return (G, mods[0], mods[1], G.ext('tall_v3'), G.ext('tall_v3_paint'), G.ext('clips_tall_v3'), G.core('pose'))


def r21_params():
    """The round-21 cast entry of the visor character (params, stance) from the restricted pack."""
    doc = json.loads((restricted_root() / 'packs' / 'forest_village' / 'pack.json').read_text(encoding='utf-8'))
    for c in doc['cameo_cast']:
        if c['id'] == CAST_ID:
            return dict(c['params']), c['stance']
    raise RestrictedSourceError('no %s in the restricted cast' % CAST_ID)


def recipe(preset='tall_v3', revision=None, **over):
    params, stance = r21_params()
    params.update(over)
    return {'revision': revision, 'id': CAST_ID if preset == 'tall_v2' else 'teknium_tall_v3', 'preset': preset, 'params': params,
            'stance': stance if preset == 'tall_v2' else 'neutral'}


def body(rec, G=None):
    G, CAM, CAMP, T3, T3P, CL, PO = modules(G)
    fixes = T3.FIXES if rec['preset'] == 'tall_v3' else ()
    if rec['preset'] == 'tall_v3' and rec.get('revision') is not None:
        # earlier revisions stay buildable for before/after measurements (1: stills-01..04, 2: stills-05)
        if rec['revision'] not in T3.FIXES_BY_REVISION:
            raise A.AssemblyError('tall_v3 has revisions %s, not %r' % (sorted(T3.FIXES_BY_REVISION), rec['revision']))
        fixes = T3.FIXES_BY_REVISION[rec['revision']]
    return T3.person(CAM, rec['params'], fixes)


def textures(rec, a, G=None):
    G, CAM, CAMP, T3, T3P, CL, PO = modules(G)
    PPT = G.core('people_paint')
    pack = G.pack(PACK)
    p = a.params
    cloth = CAMP.costume_atlas(pack, p); face = PPT.face_atlas(pack, p); hair = CAMP.headwear(pack, p)
    if rec['preset'] == 'tall_v3':
        cloth, face, hair = T3P.repaint(pack, p, cloth, face, hair)
    return cloth, face, hair


def _clip(G, a, sk, name, order, metrics, rec):
    G, CAM, CAMP, T3, T3P, CL, PO = modules(G)
    if rec['preset'] != 'tall_v3':
        return A._character_clip(PO, a, sk, metrics, name, rec['stance'], order)
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


def character(rec, clips=None, G=None):
    G, CAM, CAMP, T3, T3P, CL, PO = modules(G)
    pack = G.pack(PACK)
    a = body(rec, G)
    p = a.params
    if len(a.faces) >= BUDGET['body']:
        raise A.AssemblyError('%s: body %d tris, budget < %d' % (rec['id'], len(a.faces), BUDGET['body']))
    h = hashlib.sha256(json.dumps([rec['preset'], p], sort_keys=True).encode()).hexdigest()[:10]
    cloth, face, hair = textures(rec, a, G)
    tex = [('tex_' + h + '_cloth', cloth), ('tex_' + h + '_face', face), ('tex_' + h + '_hair', hair)]
    spec = [('costume', 'baked_unlit', None), ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': p['expression']}),
            ('headwear', 'baked_unlit', None)]
    mats = []
    for (img_name, arr), (role, kind, atlas), slot in zip(tex, spec, ('costume', 'face', 'headwear')):
        mats.append(A._material('mat_%s_char_%s_%s' % (PACK, slot, h), img_name, A.png_bytes(arr), pack['id'], role, kind, atlas))
    fmat = [A.HUMAN_ROLE_SLOT[r] for r in a.roles]
    mesh = A._mesh('kit_body_mesh', a.vertices, a.faces, fmat, a.uv, mats)
    ramp = A._ramp(G, pack)
    V32 = mesh.vertices
    low = p['height'] * .12
    soft = set()
    ao = getattr(a, 'ao', {})
    if rec['preset'] == 'tall_v3':
        for part in ('face', 'nose'):
            soft |= set(a.parts.get(part, []))

    def shade(vi, n):
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
              'topology': a.topology, 'preset': rec['preset']}
    rig = SceneRig(object_name='rig_' + SKELETON, skeleton=SKELETON, bones={n: tuple(a.bones[n]) for n in order},
                   parents={n: a.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    names = list(clips) if clips is not None else list(CLIPS)
    sk = A._Skinner(a.bones, a.parents, a.vertices, a.weights)
    metrics = PO.body_metrics(a)
    for name in names:
        sc.clips.append(_clip(G, a, sk, name, order, metrics, rec))
    for m in mats:
        at = m.n64.get('atlas')
        if at and names:
            cells = dict(at.get('clip_cells', {}))
            m.atlas_cell = (int(cells.get(names[-1], at['cell'])), int(at['cols']), int(at['rows']))
    sc.info = {'params': p, 'hash': h, 'stance': rec['stance'], 'props': [], 'pack': PACK, 'topology': a.topology,
               'skeleton': SKELETON, 'generator': a, 'tris': len(a.faces), 'preset': rec['preset']}
    return sc


def character_bytes(rec, clips=None, G=None):
    from . import writer
    sc = character(rec, clips=clips, G=G)
    return writer.write_scene(sc, writer.GENERATOR), sc
