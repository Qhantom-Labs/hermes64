"""Blender-free scene builder for CHARSYS robots (build item kind 'robot'), registered with the python exporter.

A line-by-line port of characters/gen/ext/robot_blender.py (assemble_robot, crown_mesh, _pose, make_actions) onto
the nbchars scene model, the same way adventure_maker/nbchars/assemble.py ports core/blender.py and
core/combat_blender.py: same generator calls in the same order, same names, materials, sockets, rig extras and
16-key STEP clips. The generator (core + ext) is loaded under a private package with the CPython 3.13 number
semantics nbchars uses (pycompat), because the Blender builds ran inside Blender's Python 3.13.

    nbchars.register_builder('robot', robot_scene)      # done lazily by adventure_maker.nbchars
    scene = robot_scene(item, pack)                     # item = a compiled CHARSYS build item, pack = its pack dict

Not covered by the published parity verdict (adventure_maker/nbchars/PARITY.json has no robot oracle); the robot
comparison against Blender builds is recorded in docs/MERGE4-LOG.md.
"""
import hashlib
import importlib
import importlib.util
import json
import math
import sys
import types
from pathlib import Path

import numpy as np

from .nbchars import assemble as A
from .nbchars import blendmath as BM
from .nbchars import gen as NG
from .nbchars.scene import Scene, SceneClip, SceneRig, SceneSocket

GEN = Path(__file__).resolve().parents[1] / 'characters' / 'gen'
PKG = '_hermes64_robotgen'
KEYS = 16
FPS = 15
INLINE = {}          # pack id -> {'pack', 'combat_roles'}: the job's inline packs (build.py INLINE, same rule)


class _Finder:
    """PKG.core.<m> / PKG.ext.<m> -> characters/gen/<core|ext>/<m>.py through the nbchars compat loader."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(PKG + '.'):
            return None
        parts = fullname[len(PKG) + 1:].split('.')
        if parts[0] not in ('core', 'ext') or len(parts) > 2:
            return None
        if len(parts) == 1:
            init = GEN / parts[0] / '__init__.py'
            return importlib.util.spec_from_file_location(fullname, str(init), loader=NG._CompatLoader(fullname, str(init)),
                                                          submodule_search_locations=[str(GEN / parts[0])])
        f = GEN / parts[0] / (parts[1] + '.py')
        if not f.is_file():
            return None
        return importlib.util.spec_from_file_location(fullname, str(f), loader=NG._CompatLoader(fullname, str(f)))

    def invalidate_caches(self):
        pass


def _install():
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(GEN)]
        pkg.__package__ = PKG
        sys.modules[PKG] = pkg
        roles = importlib.import_module(PKG + '.core.roles')
        original = roles.load_roles

        def load_roles(pack):                      # characters/gen/build.py _load_roles
            if pack['id'] in INLINE:
                return dict(INLINE[pack['id']].get('combat_roles', {}))
            return original(pack)
        roles.load_roles = load_roles


def mod(dotted):
    """A generator module ('core.pose', 'ext.robots') of the private robot package."""
    _install()
    return importlib.import_module(PKG + '.' + dotted)


def _blender_normals(mesh):
    """Smooth vertex normals with Blender's face-normal rule for zero-area triangles: such a face gets (0, 0, 1),
    not a zero vector, and still adds its corner-angle share. The boss crown has ten of them (coincident ring
    vertices between its points); measured against Blender 5.2.1 (docs/MERGE4-LOG.md). Identical to
    nbchars.blendmath.vertex_normals on meshes without degenerate faces."""
    fn = BM.face_normals(mesh.vertices, mesh.faces)
    zero = ~fn.any(axis=1)
    if zero.any():
        fn = fn.copy()
        fn[zero] = np.array([0., 0., 1.], dtype=np.float32)
    mesh.vertex_normals = BM.vertex_normals(mesh.vertices, mesh.faces, fn=fn)
    return mesh


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def crown_mesh(m):
    """ext/robot_blender.crown_mesh without mathutils (the Vector math there only decides the winding sign)."""
    ids = m.parts['face']
    top = max(m.vertices[i][2] for i in ids)
    H = m.params['height']
    near = [m.vertices[i] for i in ids if top - .05 * H < m.vertices[i][2] < top - .015 * H]
    near = near or [m.vertices[i] for i in ids if m.vertices[i][2] > top - .06 * H]
    cx = sum(v[0] for v in near) / len(near); cy = sum(v[1] for v in near) / len(near)
    rad = max(math.hypot(v[0] - cx, v[1] - cy) for v in near) * 1.10
    n = 10
    rings = []
    for k, (dz, rk, spike) in enumerate(((-.06, .80, 0.), (-.035, 1.0, 0.), (.0, 1.05, 0.), (.0, 1.05, 1.))):
        ring = []
        for j in range(n):
            a = 2 * math.pi * (j + .5) / n
            up = spike and j % 2 == 0
            z = top + dz * H + (.04 * H if up else 0.)
            r = rad * rk * (1.10 if up else 1.)
            ring.append((cx + r * math.sin(a), cy - r * math.cos(a), z))
        rings.append(ring)
    V = [p for r in rings for p in r]
    F = []
    for k in range(3):
        for j in range(n):
            a = k * n + j; b = k * n + (j + 1) % n; c = (k + 1) * n + (j + 1) % n; d = (k + 1) * n + j
            F += [(a, b, c), (a, c, d)]
    for end, rev in ((0, True), (3, False)):
        ids_ = [end * n + j for j in range(n)]
        seq = list(reversed(ids_)) if rev else ids_
        for j in range(1, n - 1):
            F.append((seq[0], seq[j], seq[j + 1]))
    vol = sum(_dot(V[i], _cross(V[j], V[k])) for i, j, k in F)
    if vol < 0:
        F = [(a, c, b) for a, b, c in F]
    uv = []
    for f in F:
        uv.append([(((math.atan2(V[i][0] - cx, -(V[i][1] - cy)) / (2 * math.pi)) % 1.),
                    min(1., max(0., (V[i][2] - top + .05 * H) / (.10 * H)))) for i in f])
    return V, F, uv


def robot_scene(item, pack, generator=None):
    """One compiled robot build item -> nbchars Scene (ext/robot_blender.assemble_robot with actions)."""
    G = generator or NG.load()
    INLINE.clear()
    INLINE.update(G.inline)
    R = mod('ext.robots'); RP = mod('ext.robot_paint'); RPO = mod('ext.robot_pose')
    PO = mod('core.pose'); GEO = mod('core.geometry'); paint = mod('core.paint')
    pack_id = item['pack_id']
    spec = item['robot']
    body = spec['body']
    m = R.build(body, spec.get('params', {}))
    p = m.params
    roles, fell = RP.resolve_roles(pack, spec.get('roles'))
    h = hashlib.sha256(json.dumps([body, p, roles], sort_keys=True).encode()).hexdigest()[:10]
    atlas = {'cols': 4, 'rows': 2, 'cell': 0, 'clip_cells': dict(RP.CLIP_CELLS)}
    mc = A._material('mat_%s_robot_%s_coat' % (pack_id, h), 'tex_%s_robot_%s_coat' % (pack_id, h),
                     A.png_bytes(RP.coat_atlas(pack, roles, p, body)), pack['id'], 'coat')
    mf = A._material('mat_%s_robot_%s_face' % (pack_id, h), 'tex_%s_robot_%s_face' % (pack_id, h),
                     A.png_bytes(RP.face_atlas(pack, roles, p)), pack['id'], 'face', 'face_atlas', atlas)
    mc.n64['roles'] = roles
    mf.n64['cells'] = {str(v): k for k, v in RP.CELLS.items()}
    fmat = [1 if r == 'face' else 0 for r in m.roles]
    mesh = _blender_normals(A._mesh('kit_body_mesh', m.vertices, m.faces, fmat, m.uv, [mc, mf]))
    ramp = [paint.color(pack, c) for c in pack['light_ramp']]
    H = max(v[2] for v in m.vertices)
    floor_dark = .10 * H
    V32 = mesh.vertices

    def shade(vi, n):                              # combat_blender._vcol_bake(shade_fn=.78 + .22 * ..., floor_dark)
        s = .78 + .22 * max(-.6, A._vdot(n))
        if float(V32[vi, 2]) < floor_dark:
            s -= .045
        return s
    mesh.corner_color = A._bake_colors(V32, mesh.faces, mesh.vertex_normals, ramp, shade)
    order = list(GEO.HUMAN_PARENTS)
    mesh.groups = order
    gi = {n: i for i, n in enumerate(order)}
    mesh.weights = [[(gi[n], float(np.float32(w))) for n, w in wts.items()] for wts in m.weights]
    clips = list(spec.get('clips') or RPO.clips_for(body, p.get('boss', False)))
    hover = getattr(m, 'hover', 0.)
    extras = {'skeleton': R.RIG, 'topology': m.topology, 'robot_body': body, 'params_json': json.dumps(p, sort_keys=True),
              'stance': 'neutral', 'clips': json.dumps(clips), 'fsm_clip': json.dumps(RPO.FSM_CLIP, sort_keys=True),
              'combat_metadata': json.dumps({c: RPO.PHASES[c] for c in clips if c in RPO.PHASES}, sort_keys=True),
              'hover_m': round(hover, 6),
              'root_motion': 'none: root carries only the vertical grounding offset (floor + hover + lift)'}
    rig = SceneRig(object_name='rig_' + R.RIG, skeleton=R.RIG, bones={n: tuple(m.bones[n]) for n in order},
                   parents={n: m.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    crown_tris = 0
    if spec.get('crown'):
        V, F, CU = crown_mesh(m)
        mat = A._material('mat_%s_robot_%s_crown' % (pack_id, h), 'tex_%s_robot_%s_crown' % (pack_id, h),
                          A.png_bytes(RP.crown_texture(pack, roles)), pack['id'], 'prop')
        cm = _blender_normals(A._mesh('kit_acc_head_crown_mesh', V, F, [0] * len(F), CU, [mat]))
        cm.corner_color = A._bake_colors(cm.vertices, cm.faces, cm.vertex_normals, ramp,
                                         lambda vi, n: .80 + .20 * max(-.7, A._vdot(n)))
        crown_tris = len(F)
        head = m.bones['head']
        # matrix_world = identity under the head bone: the node sits at -head in the joint's frame (core/blender
        # add_prop convention with rest_q identity and rest_t at the origin)
        w, x, y, z = (1., 0., 0., 0.)
        sc.sockets.append(SceneSocket(name='kit_acc_head_crown', bone='head', translation=A._to_gltf((-head[0], -head[1], -head[2])),
                                      rotation=(x, z, -y, w), mesh=cm,
                                      extras={'n64_prop': {'kind': 'crown', 'slot': 'head', 'tris': crown_tris}}))
    chan = []
    for n in A.pose_order(order, m.parents):
        chan.append((n, 'rotation'))
        if n == 'root':
            chan.append((n, 'translation'))
    for clip in clips:
        rots = {n: np.zeros((KEYS, 4)) for n in order}
        root_t = np.zeros((KEYS, 3))
        for f in range(KEYS):
            local, lift = RPO.local_rotations(m, clip, f / FPS)
            V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
            dz = -min(v[2] for v in V) + hover + lift
            for n in order:
                rots[n][f] = A._q_gltf(local.get(n, (1., 0., 0., 0.)))
            root_t[f] = (0., dz, 0.)
        sc.clips.append(SceneClip(name=clip, times=A._times(), rotations=rots, translations={'root': root_t},
                                  channel_order=list(chan)))
    # the Mapping node keeps the cell of the last keyed clip (ext/robot_blender._pose during make_actions)
    mf.atlas_cell = (int(atlas['clip_cells'].get(clips[-1], atlas['cell'])), 4, 2)
    sc.info = {'params': p, 'hash': h, 'pack': pack_id, 'topology': m.topology, 'skeleton': R.RIG, 'robot_body': body,
               'hover_m': round(hover, 6), 'tris_crown': crown_tris, 'roles': roles, 'roles_fallback': fell,
               'height_m': round(H, 4), 'generator': m}
    return sc
