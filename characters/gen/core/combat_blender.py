"""Blender assembly for lane-combat-art: characters with the combat clips, the weapon, the enemies, the burr.
Imports only lane-local code (core/blender.py is the frozen character pipeline copy; nothing in it changes).
"""
import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Quaternion, Matrix

from . import blender as B
from . import paint, pose as PO, weapon as WP, enemies as EN, enemy_pose as EPO, enemy_paint as EPA, roles as RL
from . import enemy_props as EPR
from .combat import COMBAT_CLIPS

ROOT = Path(__file__).resolve().parents[1]
BASIS = Quaternion((1, 0, 0), math.pi / 2)


# ------------------------------------------------------------------ characters: 7 shared + 6 combat clips
def make_actions_clips(rig, ob, a, clips):
    """core/blender.make_actions with an explicit clip list (same keys: 16 STEP keys, root location grounding)."""
    rig.animation_data_create(); bpy.context.scene.render.fps = 15
    for clip in clips:
        act = bpy.data.actions.new(clip); rig.animation_data.action = act
        for f in range(16):
            B.pose(rig, ob, a, clip, f / 15)
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


def assemble_character(packname, params, stance, props, folder, clips=None, weapon=False):
    rig, ob, a, pk = B.assemble(packname, params, False, seed=19, folder=folder, actions=False, stance=stance,
                                prop_list=props)
    if clips:
        make_actions_clips(rig, ob, a, clips)
    w = add_weapon(rig, a, pk, packname, folder) if weapon else None
    return rig, ob, a, pk, w


def _vcol_bake(me, pack, soft=(), shade_fn=None, floor_dark=None):
    ca = me.color_attributes.new(name='Col', type='BYTE_COLOR', domain='CORNER'); me.color_attributes.active_color = ca
    ramp = np.array([paint.color(pack, c) for c in pack['light_ramp']]) / 255
    light = Vector((-.45, -.7, .8)).normalized()
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index; v = me.vertices[vi]; n = v.normal
            shade = (.80 + .20 * max(-.7, n.dot(light))) if shade_fn is None else shade_fn(vi, v, n, light)
            if floor_dark is not None and v.co.z < floor_dark:
                shade -= .045
            ix = max(0, min(len(ramp) - 1, round(shade * (len(ramp) - 1))))
            ca.data[li].color_srgb = tuple(ramp[ix]) + (1.,)
    return ca


def add_weapon(rig, a, pack, packname, folder):
    """The trail staff as a rigid node on hand_r at its rest grip (core/weapon.py); moves with the clips."""
    m = WP.build()
    roles, _ = RL.resolve(pack, ['wood', 'wood_dark', 'wrap', 'metal', 'metal_dark', 'accent'])
    me = bpy.data.meshes.new(WP.NODE_NAME + '_mesh'); me.from_pydata(m.vertices, [], m.faces); me.update()
    im = B.image('tex_%s_weapon_%s' % (packname, WP.WEAPON_ID), WP.texture(pack, roles), folder)
    mat = B.simplemat('mat_%s_weapon_%s' % (packname, WP.WEAPON_ID), im, pack, 'prop'); me.materials.append(mat)
    uv = me.uv_layers.new(name='UVMap')
    for poly, uvs in zip(me.polygons, m.uv):
        poly.use_smooth = True
        for li, pt in zip(poly.loop_indices, uvs):
            uv.data[li].uv = pt
    _vcol_bake(me, pack)
    ob = bpy.data.objects.new(WP.NODE_NAME, me); bpy.context.scene.collection.objects.link(ob)
    body = PO.body_metrics(a)
    g = WP.grip_offset(a.bones, body)
    j = a.bones['hand_r']
    t_r = (j[0] + g[0], j[1] + g[1], j[2] + g[2])
    ob['n64_prop'] = {'kind': WP.WEAPON_ID, 'slot': 'hand_r', 'tris': len(m.faces), 'grip': WP.grip_gltf(a.bones, body)}
    bpy.context.view_layer.update()
    ob.parent = rig; ob.parent_type = 'BONE'; ob.parent_bone = 'hand_r'
    bpy.context.view_layer.update()
    ob.matrix_world = Matrix.Translation(Vector(t_r)) @ Quaternion(WP.REST_Q_BLENDER).to_matrix().to_4x4()
    return ob


def export_weapon(packname, path, folder):
    """Standalone weapon GLB: one unskinned mesh node at the grip origin, shaft along +Z (glTF +Y)."""
    B.clear()
    pack = B.loadpack(packname)
    m = WP.build()
    roles, fell = RL.resolve(pack, ['wood', 'wood_dark', 'wrap', 'metal', 'metal_dark', 'accent'])
    me = bpy.data.meshes.new(WP.NODE_NAME + '_mesh'); me.from_pydata(m.vertices, [], m.faces); me.update()
    im = B.image('tex_%s_weapon_%s' % (packname, WP.WEAPON_ID), WP.texture(pack, roles), folder)
    mat = B.simplemat('mat_%s_weapon_%s' % (packname, WP.WEAPON_ID), im, pack, 'prop'); me.materials.append(mat)
    mat['n64']['roles'] = roles
    uv = me.uv_layers.new(name='UVMap')
    for poly, uvs in zip(me.polygons, m.uv):
        poly.use_smooth = True
        for li, pt in zip(poly.loop_indices, uvs):
            uv.data[li].uv = pt
    _vcol_bake(me, pack)
    ob = bpy.data.objects.new(WP.NODE_NAME, me); bpy.context.scene.collection.objects.link(ob)
    ob['n64_prop'] = {'kind': WP.WEAPON_ID, 'slot': 'hand_r', 'tris': len(m.faces), 'origin': 'grip centre',
                      'axis': '+Y glTF (shaft toward the tip)', 'tip_m': WP.TIP_LEN, 'pommel_m': WP.POMMEL_LEN,
                      'rest_rotation_on_hand_r_xyzw': WP.REST_Q_GLTF_XYZW, 'roles_fallback': fell}
    B.export(path)
    return len(m.faces), roles, fell


# ------------------------------------------------------------------ enemies
def _enemy_materials(pack, packname, eid, folder):
    roles, fell = EPA.roles_for(pack, eid)
    coat = B.image('tex_%s_%s_coat' % (packname, eid), EPA.coat_atlas(pack, eid), folder)
    face = B.image('tex_%s_%s_face' % (packname, eid), EPA.face_atlas(pack, eid), folder)
    atlas = {'cols': 2, 'rows': 2, 'cell': 0, 'clip_cells': dict(EPO.FACE_CELLS['clip_cells'])}
    mc = B.simplemat('mat_%s_%s_coat' % (packname, eid), coat, pack, 'coat')
    mf = B.simplemat('mat_%s_%s_face' % (packname, eid), face, pack, 'face', 'face_atlas', atlas)
    mc['n64']['roles'] = roles; mf['n64']['cells'] = EPO.FACE_CELLS['cells']
    return [mc, mf], roles, fell


def assemble_enemy(packname, eid, folder, actions=True):
    pack = B.loadpack(packname)
    m = EN.build(eid)
    me = bpy.data.meshes.new('kit_body_mesh'); me.from_pydata(m.vertices, [], m.faces); me.update()
    mats, roles, fell = _enemy_materials(pack, packname, eid, folder)
    for mt in mats:
        me.materials.append(mt)
    for poly, role in zip(me.polygons, m.roles):
        poly.material_index = 1 if role == 'face' else 0; poly.use_smooth = True
    uv = me.uv_layers.new(name='UVMap')
    for poly, uvs in zip(me.polygons, m.uv):
        for li, pt in zip(poly.loop_indices, uvs):
            uv.data[li].uv = pt
    H = max(v[2] for v in m.vertices)
    _vcol_bake(me, pack, shade_fn=lambda vi, v, n, light: .78 + .22 * max(-.6, n.dot(light)), floor_dark=.10 * H)
    ob = bpy.data.objects.new('kit_body', me); bpy.context.scene.collection.objects.link(ob)
    rigdata = bpy.data.armatures.new(m.rig)
    rig = bpy.data.objects.new('rig_' + m.rig, rigdata); bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
    order = _order(m.parents)
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
    # sockets (empties on joints) for the runtime: hit/hurt centre, and the warden's lob socket at the crest
    sockets = {'cairn_dasher': [('attach_ram', 'head', (0, -.30, -.02)), ('attach_core', 'chest', (0, -.05, .02))],
               'reed_warden': [('attach_lob', 'crest', (0, .02, .24)), ('attach_core', 'body', (0, -.02, .16))]}[eid]
    for nm, bone, off in sockets:
        e = bpy.data.objects.new(nm, None); bpy.context.scene.collection.objects.link(e)
        e.parent = rig; e.parent_type = 'BONE'; e.parent_bone = bone
        bpy.context.view_layer.update()
        e.matrix_world = Matrix.Translation(Vector(m.bones[bone]) + Vector(off))
    rig['skeleton'] = m.rig; rig['topology'] = m.topology; rig['enemy_id'] = eid; rig['template'] = EN.TEMPLATE[eid]
    rig['clips'] = json.dumps(EPO.ENEMY_CLIPS); rig['fsm_clip'] = json.dumps(EPO.FSM_CLIP, sort_keys=True)
    rig['root_motion'] = 'none: root never animated; body bone carries vertical offset only'
    if actions:
        make_enemy_actions(rig, ob, m)
    return rig, ob, m, pack, roles, fell


def _order(parents):
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


def enemy_pose(rig, ob, m, clip, t):
    local, dz, lift = EPO.local_pose(m, clip, t)
    body = EPO.BODY_BONE[m.id]
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        q = Quaternion(local.get(pb.name, (1, 0, 0, 0)))
        pb.rotation_quaternion = BASIS.inverted() @ q @ BASIS
        pb.location = (0, 0, 0)
    rig.pose.bones[body].location = (0, dz, 0)
    bpy.context.view_layer.update()
    for mt in ob.data.materials:
        at = (mt.get('n64') or {}).get('atlas') if mt else None
        mp = mt.node_tree.nodes.get('expression_offset') if (mt and at) else None
        if mp is not None:
            cells = dict(at.get('clip_cells', {})); cell = int(cells.get(clip, at['cell'])); cols = int(at['cols']); rows = int(at['rows'])
            mp.inputs['Location'].default_value = (cell % cols / cols, cell // cols / rows, 0)
    bpy.context.view_layer.update()


def make_enemy_actions(rig, ob, m):
    rig.animation_data_create(); bpy.context.scene.render.fps = 15
    body = EPO.BODY_BONE[m.id]
    for clip in EPO.ENEMY_CLIPS:
        act = bpy.data.actions.new(clip); rig.animation_data.action = act
        for f in range(16):
            enemy_pose(rig, ob, m, clip, f / 15)
            for pb in rig.pose.bones:
                if pb.name != 'root':
                    pb.keyframe_insert('rotation_quaternion', frame=f)
            rig.pose.bones[body].keyframe_insert('location', frame=f)
        for fc in B.fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = 'CONSTANT'
        tr = rig.animation_data.nla_tracks.new(); tr.name = clip; tr.strips.new(clip, 0, act); tr.mute = True
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    bpy.context.scene.frame_set(0); bpy.context.view_layer.update()


def export_projectile(packname, path, folder):
    B.clear()
    pack = B.loadpack(packname)
    m = EPR.burr()
    roles, fell = RL.resolve(pack, ['burr', 'burr_tip', 'weave_dark'])
    me = bpy.data.meshes.new(EPR.NODE_NAME + '_mesh'); me.from_pydata(m.vertices, [], m.faces); me.update()
    im = B.image('tex_%s_%s' % (packname, EPR.PROJ_ID), EPR.texture(pack, roles), folder)
    mat = B.simplemat('mat_%s_%s' % (packname, EPR.PROJ_ID), im, pack, 'prop'); me.materials.append(mat)
    mat['n64']['roles'] = roles
    uv = me.uv_layers.new(name='UVMap')
    for poly, uvs in zip(me.polygons, m.uv):
        poly.use_smooth = True
        for li, pt in zip(poly.loop_indices, uvs):
            uv.data[li].uv = pt
    _vcol_bake(me, pack)
    ob = bpy.data.objects.new(EPR.NODE_NAME, me); bpy.context.scene.collection.objects.link(ob)
    ob['n64_prop'] = {'kind': EPR.PROJ_ID, 'tris': len(m.faces), 'origin': 'centre', 'used_by': 'reed_warden attach_lob (optional)'}
    B.export(path)
    return len(m.faces), roles, fell
