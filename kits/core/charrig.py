"""Blender shared rig/STEP actions for the two generic bases. All bone rest axes are +Z.
No species or theme branches here. Root translation accommodates each figure's proportions.
"""
import math
import bpy
import numpy as np
from mathutils import Quaternion
from . import blendio, chartex


def all_fcurves(action):
    result=[]
    for layer in getattr(action,'layers',[]):
        for strip in layer.strips:
            for cb in strip.channelbags:result.extend(cb.fcurves)
    return result


def pose(skeleton,clip,t):
    """Bone-local Euler XYZ radians; pure shared keys, independent of costume/species."""
    d={};wave=math.sin(t*math.tau)
    def rot(n,x=0,y=0,z=0):d[n]=(x,y,z)
    if skeleton=='human16_v1':
        if clip in ('walk','run','carry'):
            amp=.48 if clip!='run' else .8
            for s,sign in [('l',1),('r',-1)]:
                rot('thigh_'+s,sign*amp*wave)
                rot('shin_'+s,max(0,-sign*wave)*amp*.6)
                rot('upper_arm_'+s,-sign*amp*.65*wave)
                rot('forearm_'+s,-.15)
            if clip=='carry':
                rot('upper_arm_l',-.65);rot('upper_arm_r',-.65)
                rot('forearm_l',-.65);rot('forearm_r',-.65)
        elif clip=='sit':
            for s in ('l','r'):
                rot('thigh_'+s,-1.45);rot('shin_'+s,1.42);rot('upper_arm_'+s,-.3);rot('forearm_'+s,-.5)
        elif clip=='interact':
            a=.5-.5*math.cos(t*math.tau)
            rot('upper_arm_r',-1.15*a);rot('forearm_r',-.45*a)
            rot('spine',-.08*a)
        elif clip=='talk':
            rot('head',.06*wave,.12*wave)
            rot('upper_arm_l',-.35-.12*wave,0,-.12)
            rot('forearm_l',-.45-.18*wave)
        else:
            rot('spine',.012*wave);rot('head',0,.055*wave)
    else:
        if clip in ('walk','run'):
            amp=.45 if clip=='walk' else .7
            for limb,sign in [('fl',1),('br',1),('fr',-1),('bl',-1)]:
                rot('leg_'+limb,amp*sign*wave);rot('paw_'+limb,-amp*sign*wave*.5)
        elif clip=='sit':
            rot('leg_bl',-1.25);rot('leg_br',-1.25)
            rot('paw_bl',1.1);rot('paw_br',1.1)
            rot('chest',-.28)
        elif clip in ('loaf','sleep_curled'):
            for limb in ('fl','fr','bl','br'):
                rot('leg_'+limb,-1.25 if limb[0]=='f' else 1.25)
                rot('paw_'+limb,1.2 if limb[0]=='f' else -1.2)
            if clip=='sleep_curled':
                rot('chest',0,.5);rot('neck',.22,.65);rot('head',.28,.35)
                rot('tail_1',0,.8);rot('tail_2',0,.75);rot('tail_3',0,.65)
        elif clip=='stretch':
            rot('chest',.16);rot('neck',-.22)
            for s in ('l','r'):rot('leg_f'+s,-.6);rot('leg_b'+s,.35)
        if clip not in ('sleep_curled',):
            rot('tail_1',0,.08*wave);rot('tail_2',0,.12*wave);rot('head',0,.06*wave)
    return d


def assemble_character(asset,pack,mf,ramp):
    ch=asset.character;name=ch['skeleton'];sc=bpy.context.scene
    arm=bpy.data.armatures.new('rig_'+name)
    rig=bpy.data.objects.new('rig_'+name,arm);sc.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for n in ch['bones']:
        b=arm.edit_bones.new(n);b.head=ch['heads'][n]
        b.tail=(b.head.x,b.head.y,b.head.z+.05)
        p=ch['parents'][n]
        if p:b.parent=arm.edit_bones[p]
    bpy.ops.object.mode_set(mode='OBJECT')
    mats=chartex.materials(pack,mf,ch)
    ob=blendio.make_mesh_object(ch['body'],mf,pack.light_rig,ramp,materials=mats,uv_override=ch['uvs'])
    ob.parent=rig
    for n in ch['bones']:
        vg=ob.vertex_groups.new(name=n)
        ids=[i for i,b in enumerate(ch['weights']) if b==n]
        if ids:vg.add(ids,1,'REPLACE')
    mod=ob.modifiers.new('skin','ARMATURE');mod.object=rig
    for nm,parent in ch['attachments'].items():
        e=bpy.data.objects.new(nm,None);sc.collection.objects.link(e)
        e.parent=rig;e.parent_type='BONE';e.parent_bone=parent
        e.matrix_parent_inverse.identity();e.location=(0,-.05,0)
    rig.animation_data_create();sc.render.fps=12;sc.frame_start=0;sc.frame_end=24
    from mathutils import Euler
    # Each action contains its own full set of rotations. No NLA pose leakage.
    for clip in ch['clips']:
        act=bpy.data.actions.new(clip);rig.animation_data.action=act
        for f in range(0,25,2):
            d=pose(name,clip,f/24)
            for n in ch['bones']:
                pb=rig.pose.bones[n];pb.rotation_mode='QUATERNION'
                pb.rotation_quaternion=Euler(d.get(n,(0,0,0)),'XYZ').to_quaternion()
                pb.location=(0,0,0)
                pb.keyframe_insert('rotation_quaternion',frame=f)
            bpy.context.view_layer.update()
            # Ground every key from evaluated geometry (root motion only; rotations shared).
            deps=bpy.context.evaluated_depsgraph_get();ev=ob.evaluated_get(deps)
            coords=np.array([v.co[:] for v in ev.data.vertices])
            # Local Y of a +Z-oriented bone is world Z.
            root=rig.pose.bones['root'];root.location=(0,-float(coords[:,2].min()),0)
            root.keyframe_insert('location',frame=f)
        for fc in all_fcurves(act):
            for kp in fc.keyframe_points:kp.interpolation='CONSTANT'
        tr=rig.animation_data.nla_tracks.new();tr.name=clip
        st=tr.strips.new(clip,0,act);tr.mute=True
        rig.animation_data.action=None
    for pb in rig.pose.bones:
        pb.rotation_quaternion=(1,0,0,0);pb.location=(0,0,0)
    sc.frame_set(0);bpy.context.view_layer.update()
    return {'skeleton':name,'bones':ch['bones'],'attachments':ch['attachments'],
            'animations':ch['clips'],'fps':12,'interpolation':'STEP',
            'base_triangles':ch['body'].mesh.tri_count(),'segmented_rigid_skin':True}
