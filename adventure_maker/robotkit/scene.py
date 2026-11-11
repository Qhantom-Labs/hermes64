"""Recipe -> nbchars Scene -> GLB for the robotkit enemies (no Blender). The scene carries the same rig, sockets,
clip names, face-atlas material extras and rig extras as the stock robots (adventure_maker/character_robot.py
robot_scene), so the runtime and modules/combat treat these as any other robot art."""
import hashlib
import json
from pathlib import Path

import numpy as np

from .. import character_robot as CR
from ..nbchars import assemble as A
from ..nbchars import writer as W
from ..nbchars.scene import Scene, SceneClip, SceneRig, SceneSocket
from . import bodies as B
from . import paint as P
from . import poses as PZ

ROOT = Path(__file__).resolve().parents[2]
RECIPES = ROOT / 'characters' / 'robotkit'


class RecipeError(ValueError):
    pass


def load(pack_id, root=None):
    """The recipe file of a pack, checked: every colour is a palette name, every robot names a known archetype,
    livery and mark."""
    path = Path(root or RECIPES) / (pack_id + '.json')
    if not path.is_file():
        raise RecipeError('no robot recipes for pack %r (%s)' % (pack_id, path))
    d = json.loads(path.read_text(encoding='utf-8'))
    names = set(d['palette_names'])
    if len(d['palette_names']) != len(d['palette']):
        raise RecipeError('palette and palette_names differ in length')
    for role, n in d['roles'].items():
        if n not in names:
            raise RecipeError('role %s: off-palette colour %r' % (role, n))
    for n in d['light_ramp']:
        if n not in names:
            raise RecipeError('light_ramp: off-palette colour %r' % (n,))
    for lid, L in d['liveries'].items():
        for k in ('dark', 'main', 'bright'):
            if L[k] not in names:
                raise RecipeError('livery %s.%s: off-palette colour %r' % (lid, k, L[k]))
        if L['mark'] not in P.MARKS:
            raise RecipeError('livery %s: unknown mark %r' % (lid, L['mark']))
    seen = set()
    for r in d['robots']:
        if r['archetype'] not in d['archetypes'] or r['archetype'] not in B.BUILDERS:
            raise RecipeError('robot %s: unknown archetype %r' % (r['id'], r['archetype']))
        if r['livery'] not in d['liveries']:
            raise RecipeError('robot %s: unknown livery %r' % (r['id'], r['livery']))
        if r['id'] in seen:
            raise RecipeError('duplicate robot id %r' % (r['id'],))
        seen.add(r['id'])
    return d


def robot(data, rid):
    for r in data['robots']:
        if r['id'] == rid:
            return r
    raise RecipeError('unknown robot %r (have %s)' % (rid, ', '.join(r['id'] for r in data['robots'])))


def body_for(data, rid):
    r = robot(data, rid)
    a = data['archetypes'][r['archetype']]
    params = dict(a.get('params', {})); params.update(r.get('params', {}))
    return B.build(r['archetype'], params)


def clips_for(m):
    RPO = CR.mod('ext.robot_pose')
    return list(RPO.clips_for(m.body, False))


def skinned(m, clip, f):
    """World vertices of key f (floor / hover offset applied), for measures and stills."""
    RPO = CR.mod('ext.robot_pose'); PO = CR.mod('core.pose')
    local, lift = PZ.local_rotations(RPO, PO, m, clip, f / CR.FPS)
    V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
    dz = -min(v[2] for v in V) + m.hover + lift
    return [(v[0], v[1], v[2] + dz) for v in V]


def robot_scene(data, rid):
    RPO = CR.mod('ext.robot_pose'); PO = CR.mod('core.pose'); GEO = CR.mod('core.geometry')
    r = robot(data, rid)
    pack_id = data['id']
    m = body_for(data, rid)
    p = m.params
    livery = r['livery']
    L = data['liveries'][livery]
    aspects = {t: B.tile_aspect(m, t) for t in ('mark', 'mark_top')}
    coat = P.coat_atlas(data, livery, aspects)
    face = P.face_atlas(data, livery)
    for name, img in (('coat', coat), ('face', face)):
        off = P.palette_exact(img, data)
        if off:
            raise RecipeError('%s %s atlas: %d off-palette colours' % (rid, name, off))
    h = hashlib.sha256(json.dumps([m.archetype, p, livery, L, data['roles']], sort_keys=True).encode()).hexdigest()[:10]
    atlas = {'cols': 4, 'rows': 2, 'cell': 0, 'clip_cells': dict(P.CLIP_CELLS)}
    mc = A._material('mat_%s_robot_%s_coat' % (pack_id, h), 'tex_%s_robot_%s_coat' % (pack_id, h), A.png_bytes(coat), pack_id, 'coat')
    mf = A._material('mat_%s_robot_%s_face' % (pack_id, h), 'tex_%s_robot_%s_face' % (pack_id, h), A.png_bytes(face), pack_id,
                     'face', 'face_atlas', atlas)
    mc.n64['roles'] = P.colours(data, livery)
    mc.n64['livery'] = {'id': livery, 'mark': L['mark']}
    mf.n64['cells'] = {str(v): k for k, v in P.CELLS.items()}
    fmat = [1 if x == 'face' else 0 for x in m.roles]
    mesh = CR._blender_normals(A._mesh('kit_body_mesh', m.vertices, m.faces, fmat, m.uv, [mc, mf]))
    ramp = [P.rgb(data, c) for c in data['light_ramp']]
    H = max(v[2] for v in m.vertices)
    lo = min(v[2] for v in m.vertices)
    V32 = mesh.vertices

    def shade(vi, n):
        # Top-lit, the same from every side: these enemies are seen from all yaws in unlit dark rooms, so a baked
        # front light would leave the back and side faces on the room's own tones (measured: tools.robots_build
        # readability). Up faces and the upper half of the walls take the top of the light ramp (the light rim); the walls
        # darken one ramp step toward the floor (grounding), undersides one step.
        zrel = (float(V32[vi, 2]) - lo) / (H - lo)
        return .82 + .14 * float(n[2]) + .12 * zrel
    mesh.corner_color = A._bake_colors(V32, mesh.faces, mesh.vertex_normals, ramp, shade)
    order = list(GEO.HUMAN_PARENTS)
    mesh.groups = order
    gi = {n: i for i, n in enumerate(order)}
    mesh.weights = [[(gi[n], float(np.float32(w))) for n, w in wts.items()] for wts in m.weights]
    clips = clips_for(m)
    extras = {'skeleton': B.RIG, 'topology': m.topology, 'robot_body': m.body, 'robot_archetype': m.archetype,
              'robot_livery': livery, 'params_json': json.dumps(p, sort_keys=True), 'stance': 'neutral',
              'clips': json.dumps(clips), 'fsm_clip': json.dumps(RPO.FSM_CLIP, sort_keys=True),
              'combat_metadata': json.dumps({c: RPO.PHASES[c] for c in clips if c in RPO.PHASES}, sort_keys=True),
              'hover_m': round(m.hover, 6),
              'root_motion': 'none: root carries only the vertical grounding offset (floor + hover + lift)'}
    rig = SceneRig(object_name='rig_' + B.RIG, skeleton=B.RIG, bones={n: tuple(m.bones[n]) for n in order},
                   parents={n: m.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    chan = []
    for n in A.pose_order(order, m.parents):
        chan.append((n, 'rotation'))
        if n == 'root':
            chan.append((n, 'translation'))
    for clip in clips:
        rots = {n: np.zeros((CR.KEYS, 4)) for n in order}
        root_t = np.zeros((CR.KEYS, 3))
        for f in range(CR.KEYS):
            local, lift = PZ.local_rotations(RPO, PO, m, clip, f / CR.FPS)
            V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
            dz = -min(v[2] for v in V) + m.hover + lift
            for n in order:
                rots[n][f] = A._q_gltf(local.get(n, (1., 0., 0., 0.)))
            root_t[f] = (0., dz, 0.)
        sc.clips.append(SceneClip(name=clip, times=A._times(), rotations=rots, translations={'root': root_t},
                                  channel_order=list(chan)))
    mf.atlas_cell = (int(atlas['clip_cells'].get(clips[-1], atlas['cell'])), 4, 2)
    sc.info = {'params': p, 'hash': h, 'pack': pack_id, 'topology': m.topology, 'skeleton': B.RIG, 'robot_body': m.body,
               'archetype': m.archetype, 'livery': livery, 'hover_m': round(m.hover, 6), 'tris': len(m.faces),
               'height_m': round(H, 4), 'aspects': aspects, 'generator': m, 'coat': coat, 'face': face}
    return sc


def glb_bytes(data, rid):
    return W.write_scene(robot_scene(data, rid))
