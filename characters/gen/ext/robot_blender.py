"""Blender assembly for the mechanical family (lane CHARSYS). Imports only the vendored core + ext modules.

assemble_robot(pack_id, spec, folder) -> (rig, body object, mesh)
  spec = {'body': walker|brute|floater, 'params': robots.resolve values, 'roles': {role: palette name} (optional),
          'clips': [...] (default robot_pose.clips_for), 'crown': bool}
Same export conventions as the cast and the enemies: one skinned 'kit_body' mesh on a human16_v1 armature (bones
created in core/geometry.HUMAN_PARENTS order), materials made by core/blender.simplemat (baked_unlit coat + painted
face atlas 4x2 with clip cells), baked vertex light from the pack light ramp, attach_* empties on the shared slots,
16-key STEP clips as NLA tracks, rig extras for the runtime and the gates. The boss crown is a rigid attachment
node (kit_acc_head_crown) on the head bone, budgeted as a prop.
"""
import hashlib
import json
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

try:
    from ..core import blender as B
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import blender as B
try:
    from ..core import combat_blender as CB
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import combat_blender as CB
try:
    from ..core import geometry as G
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import geometry as G
try:
    from ..core import pose as PO
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import pose as PO
from ext import robots as R
from ext import robot_paint as RP
from ext import robot_pose as RPO

BASIS = Quaternion((1, 0, 0), math.pi / 2)


def _pose(rig, ob, m, clip, t):
    local, lift = RPO.local_rotations(m, clip, t)
    V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
    dz = -min(v[2] for v in V) + getattr(m, 'hover', 0.) + lift
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = BASIS.inverted() @ Quaternion(local.get(pb.name, (1, 0, 0, 0))) @ BASIS
        pb.location = (0, 0, 0)
    rig.pose.bones['root'].location = (0, dz, 0)
    for mt in ob.data.materials:
        at = (mt.get('n64') or {}).get('atlas') if mt else None
        mp = mt.node_tree.nodes.get('expression_offset') if (mt and at) else None
        if mp is not None:
            cells = dict(at.get('clip_cells', {})); cell = int(cells.get(clip, at['cell'])); cols = int(at['cols']); rows = int(at['rows'])
            mp.inputs['Location'].default_value = (cell % cols / cols, cell // cols / rows, 0)
    bpy.context.view_layer.update()


def make_actions(rig, ob, m, clips):
    rig.animation_data_create(); bpy.context.scene.render.fps = 15
    for clip in clips:
        act = bpy.data.actions.new(clip); rig.animation_data.action = act
        for f in range(16):
            _pose(rig, ob, m, clip, f / 15)
            for pb in rig.pose.bones:
                pb.keyframe_insert('rotation_quaternion', frame=f)
            rig.pose.bones['root'].keyframe_insert('location', frame=f)
        for fc in B.fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = 'CONSTANT'
        tr = rig.animation_data.nla_tracks.new(); tr.name = clip; tr.strips.new(clip, 0, act); tr.mute = True
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    bpy.context.scene.frame_set(0); bpy.context.view_layer.update()


def crown_mesh(m):
    """Boss crown: a short closed band of five rounded points around the head top (prop class, rigid on 'head')."""
    ids = m.parts['face']
    top = max(m.vertices[i][2] for i in ids)
    H = m.params['height']
    near = [m.vertices[i] for i in ids if top - .05 * H < m.vertices[i][2] < top - .015 * H]
    near = near or [m.vertices[i] for i in ids if m.vertices[i][2] > top - .06 * H]
    cx = sum(v[0] for v in near) / len(near); cy = sum(v[1] for v in near) / len(near)
    rad = max(math.hypot(v[0] - cx, v[1] - cy) for v in near) * 1.10
    n = 10
    rings = []
    # base buried in the head top, a solid band that reads at game scale, then a crest ring whose even vertices
    # rise into five short points with a slight flare (a crown, not a brush)
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
    vol = sum(Vector(V[i]).dot(Vector(V[j]).cross(Vector(V[k]))) for i, j, k in F)
    if vol < 0:
        F = [(a, c, b) for a, b, c in F]
    uv = []
    for f in F:
        uv.append([(((math.atan2(V[i][0] - cx, -(V[i][1] - cy)) / (2 * math.pi)) % 1.), min(1., max(0., (V[i][2] - top + .05 * H) / (.10 * H)))) for i in f])
    return V, F, uv


def assemble_robot(pack_id, spec, folder):
    pack = B.loadpack(pack_id)
    body = spec['body']
    m = R.build(body, spec.get('params', {}))
    p = m.params
    roles, fell = RP.resolve_roles(pack, spec.get('roles'))
    h = hashlib.sha256(json.dumps([body, p, roles], sort_keys=True).encode()).hexdigest()[:10]
    coat = B.image('tex_%s_robot_%s_coat' % (pack_id, h), RP.coat_atlas(pack, roles, p, body), folder)
    face = B.image('tex_%s_robot_%s_face' % (pack_id, h), RP.face_atlas(pack, roles, p), folder)
    atlas = {'cols': 4, 'rows': 2, 'cell': 0, 'clip_cells': dict(RP.CLIP_CELLS)}
    mc = B.simplemat('mat_%s_robot_%s_coat' % (pack_id, h), coat, pack, 'coat')
    mf = B.simplemat('mat_%s_robot_%s_face' % (pack_id, h), face, pack, 'face', 'face_atlas', atlas)
    mc['n64']['roles'] = roles; mf['n64']['cells'] = {str(v): k for k, v in RP.CELLS.items()}
    me = bpy.data.meshes.new('kit_body_mesh'); me.from_pydata(m.vertices, [], m.faces); me.update()
    me.materials.append(mc); me.materials.append(mf)
    for poly, role in zip(me.polygons, m.roles):
        poly.material_index = 1 if role == 'face' else 0; poly.use_smooth = True
    uv = me.uv_layers.new(name='UVMap')
    for poly, uvs in zip(me.polygons, m.uv):
        for li, pt in zip(poly.loop_indices, uvs):
            uv.data[li].uv = pt
    H = max(v[2] for v in m.vertices)
    CB._vcol_bake(me, pack, shade_fn=lambda vi, v, n, light: .78 + .22 * max(-.6, n.dot(light)), floor_dark=.10 * H)
    ob = bpy.data.objects.new('kit_body', me); bpy.context.scene.collection.objects.link(ob)
    rigdata = bpy.data.armatures.new(R.RIG)
    rig = bpy.data.objects.new('rig_' + R.RIG, rigdata); bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
    order = list(G.HUMAN_PARENTS)
    for name in order:
        bone = rigdata.edit_bones.new(name); bone.head = m.bones[name]; bone.tail = Vector(m.bones[name]) + Vector((0, 0, .05))
        if m.parents[name]:
            bone.parent = rigdata.edit_bones[m.parents[name]]
    bpy.ops.object.mode_set(mode='OBJECT'); ob.parent = rig
    for name in order:
        ob.vertex_groups.new(name=name)
    for i, weights in enumerate(m.weights):
        for name, w in weights.items():
            ob.vertex_groups[name].add([i], w, 'REPLACE')
    mod = ob.modifiers.new('skin', 'ARMATURE'); mod.object = rig
    for slot, bone in (('hand_l', 'hand_l'), ('hand_r', 'hand_r'), ('head', 'head'), ('back', 'spine'), ('belt', 'pelvis')):
        e = bpy.data.objects.new('attach_' + slot, None); bpy.context.scene.collection.objects.link(e)
        e.parent = rig; e.parent_type = 'BONE'; e.parent_bone = bone; e.location = (0, -.05, 0)
    crown_tris = 0
    if spec.get('crown'):
        V, F, CU = crown_mesh(m)
        cm = bpy.data.meshes.new('kit_acc_head_crown_mesh'); cm.from_pydata(V, [], F); cm.update()
        im = B.image('tex_%s_robot_%s_crown' % (pack_id, h), RP.crown_texture(pack, roles), folder)
        mat = B.simplemat('mat_%s_robot_%s_crown' % (pack_id, h), im, pack, 'prop'); cm.materials.append(mat)
        cu = cm.uv_layers.new(name='UVMap')
        for poly, uvs in zip(cm.polygons, CU):
            poly.use_smooth = True
            for li, pt in zip(poly.loop_indices, uvs):
                cu.data[li].uv = pt
        CB._vcol_bake(cm, pack)
        co = bpy.data.objects.new('kit_acc_head_crown', cm); bpy.context.scene.collection.objects.link(co)
        crown_tris = len(F)
        co['n64_prop'] = {'kind': 'crown', 'slot': 'head', 'tris': crown_tris}
        bpy.context.view_layer.update()
        co.parent = rig; co.parent_type = 'BONE'; co.parent_bone = 'head'
        bpy.context.view_layer.update()
        co.matrix_world = Matrix.Identity(4)
    clips = list(spec.get('clips') or RPO.clips_for(body, p.get('boss', False)))
    rig['skeleton'] = R.RIG; rig['topology'] = m.topology; rig['robot_body'] = body
    rig['params_json'] = json.dumps(p, sort_keys=True); rig['stance'] = 'neutral'
    rig['clips'] = json.dumps(clips); rig['fsm_clip'] = json.dumps(RPO.FSM_CLIP, sort_keys=True)
    rig['combat_metadata'] = json.dumps({c: RPO.PHASES[c] for c in clips if c in RPO.PHASES}, sort_keys=True)
    rig['hover_m'] = round(getattr(m, 'hover', 0.), 6)
    rig['root_motion'] = 'none: root carries only the vertical grounding offset (floor + hover + lift)'
    make_actions(rig, ob, m, clips)
    m.crown_tris = crown_tris
    return rig, ob, m
