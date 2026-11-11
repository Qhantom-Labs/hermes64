"""Blender assembly, held clips, baked light and export. Imports only lane-local code."""
import math,json,hashlib
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector,Euler,Quaternion,Matrix
from . import geometry,paint,people,people_paint,props
from . import pose as posing

ROOT=Path(__file__).resolve().parents[1]
HCLIPS=['idle','walk','run','interact','talk','carry','sit']
ACLIPS=['idle','walk','run','sit','loaf','sleep_curled','stretch']


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps=15

def loadpack(name):return json.loads((ROOT/'packs'/name/'pack.json').read_text(encoding='utf-8'))

def image(name,arr,folder):
    path=Path(folder)/(name+'.png');paint.png(path,arr)
    im=bpy.data.images.load(str(path),check_existing=True);im.name=name
    im.colorspace_settings.name='sRGB'
    return im

def simplemat(name,im,pack,role,kind='baked_unlit',atlas=None,chrome=False):
    m=bpy.data.materials.new(name);nt=m.node_tree;nt.nodes.clear()
    out=nt.nodes.new('ShaderNodeOutputMaterial');bg=nt.nodes.new('ShaderNodeBackground')
    tex=nt.nodes.new('ShaderNodeTexImage');tex.image=im;tex.interpolation='Linear';tex.extension='REPEAT'
    if atlas:
        uv=nt.nodes.new('ShaderNodeTexCoord');mp=nt.nodes.new('ShaderNodeMapping');mp.name='expression_offset'
        cell=atlas['cell'];cols=atlas['cols'];rows=atlas['rows'];mp.inputs['Scale'].default_value=(1/cols,1/rows,1);mp.inputs['Location'].default_value=(cell%cols/cols,cell//cols/rows,0)
        nt.links.new(uv.outputs['UV'],mp.inputs['Vector']);nt.links.new(mp.outputs['Vector'],tex.inputs['Vector'])
    if chrome:
        geom=nt.nodes.new('ShaderNodeNewGeometry');tr=nt.nodes.new('ShaderNodeVectorTransform');tr.vector_type='NORMAL';tr.convert_from='WORLD';tr.convert_to='CAMERA'
        nt.links.new(geom.outputs['Normal'],tr.inputs['Vector'])
        vm=nt.nodes.new('ShaderNodeVectorMath');vm.operation='MULTIPLY_ADD';vm.inputs[1].default_value=(.5,.5,.5);vm.inputs[2].default_value=(.5,.5,.5)
        nt.links.new(tr.outputs['Vector'],vm.inputs[0]);nt.links.new(vm.outputs['Vector'],tex.inputs['Vector'])
    vc=nt.nodes.new('ShaderNodeVertexColor');vc.layer_name='Col'
    mx=nt.nodes.new('ShaderNodeMixRGB');mx.blend_type='MULTIPLY';mx.inputs[0].default_value=1
    nt.links.new(tex.outputs['Color'],mx.inputs[1]);nt.links.new(vc.outputs['Color'],mx.inputs[2]);nt.links.new(mx.outputs['Color'],bg.inputs['Color']);nt.links.new(bg.outputs[0],out.inputs['Surface'])
    m['n64']={'kind':kind,'role':role,'pack':pack['id'],'texture':im.name,'vertex_color_encoding':'linear_gltf'}
    if atlas:m['n64']['atlas']=atlas
    if chrome:m['n64']['env']='tex_'+pack['id']+'_env';m['n64']['recipe']='view-normal XY * 0.5 + 0.5; env * COLOR_0'
    m.use_backface_culling=True
    return m


def is_face_v2(values):
    return bool(values) and values.get('head_mode')=='face' and 'hair' in values


def assemble(packname,values=None,animal=False,seed=0,folder=None,actions=True,stance=None,prop_list=()):
    props_=prop_list
    pack=loadpack(packname);folder=folder or ROOT/'build'/'textures'/packname
    if not animal and values and values.get('head_mode')=='visor':
        # Visor cameo: own topology human16_visor_v1 on the shared rig, own palette pack.
        from . import cameo,cameo_paint
        p=dict(pack.get('face_defaults',{}));p.update(values)
        a=cameo.person(p);p=a.params
        h=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:10]
        costume=image('tex_'+h+'_cloth',cameo_paint.costume_atlas(pack,p),folder)
        face=image('tex_'+h+'_face',people_paint.face_atlas(pack,p),folder)
        hair=image('tex_'+h+'_hair',cameo_paint.headwear(pack,p),folder)
        mats=[simplemat('mat_'+packname+'_char_costume_'+h,costume,pack,'costume'),
          simplemat('mat_'+packname+'_char_face_'+h,face,pack,'face','face_atlas',{'cols':4,'rows':2,'cell':p['expression']}),
          simplemat('mat_'+packname+'_char_headwear_'+h,hair,pack,'headwear')]
        return _finish(pack,packname,a,p,h,mats,animal,actions,stance,props_,folder)
    v2=not animal and is_face_v2(values)
    if v2:
        # Face-head people v2: own fixed topology, painted face atlas, hair texture.
        p=dict(pack.get('face_defaults',{}));p.update(values or {})
        a=people.person(p);p=a.params
        h=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:10]
        costume=image('tex_'+h+'_cloth',people_paint.costume_atlas(pack,p),folder)
        face=image('tex_'+h+'_face',people_paint.face_atlas(pack,p),folder)
        hair=image('tex_'+h+'_hair',people_paint.hair_texture(pack,p),folder)
        mats=[simplemat('mat_'+packname+'_char_costume_'+h,costume,pack,'costume'),
          simplemat('mat_'+packname+'_char_face_'+h,face,pack,'face','face_atlas',{'cols':4,'rows':2,'cell':p['expression']}),
          simplemat('mat_'+packname+'_char_headwear_'+h,hair,pack,'headwear')]
        return _finish(pack,packname,a,p,h,mats,animal,actions,stance,props_,folder)
    p=dict(pack['animal_defaults' if animal else 'character_defaults']);p.update(values or {})
    a=geometry.quadruped(p) if animal else geometry.humanoid(p);p=a.params
    h=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:10]
    costume=image('tex_'+h+'_cloth',paint.paint(pack,p,'quad' if animal else 'human',seed),folder)
    face=image('tex_'+h+'_face',paint.face_atlas(pack,p,'quad' if animal else 'human'),folder)
    hairparams=dict(p)
    if not animal and p['headwear']=='bald':hairparams['headwear_color']=p['skin']
    hair=image('tex_'+h+'_hair',paint.hair(pack,dict(headwear_color=p['coat_color_1'])) if animal else paint.hair(pack,hairparams),folder)
    if not animal and p['head_mode']=='faceless':
        # STEER-6 masked v2: painted pearl hood (folds, seam, rim catch) as a plain baked texture - no chrome_env,
        # so it renders the same in every runtime without an environment map
        hair=image('tex_'+h+'_hair',paint.hood(pack,p),folder)
    mats=[simplemat('mat_'+packname+'_char_costume_'+h,costume,pack,'coat' if animal else 'costume'),
      simplemat('mat_'+packname+'_char_face_'+h,face,pack,'face','face_atlas',{'cols':2,'rows':1,'cell':0,'clip_cells':{'sleep_curled':1}} if animal else {'cols':4,'rows':2,'cell':p['face']}),
      simplemat('mat_'+packname+'_char_headwear_'+h,hair,pack,'headwear','baked_unlit')]
    return _finish(pack,packname,a,p,h,mats,animal,actions,stance,props_,folder)


def _finish(pack,packname,a,p,h,mats,animal,actions,stance,prop_list,folder):
    if not animal and stance:
        # round 13: per-body stance fallback (core/posecheck.resolve_stance); the tuned cast never falls back
        from . import posecheck as _PC
        stance,prop_list,_tried=_PC.resolve_stance(a,stance,prop_list)
    me=bpy.data.meshes.new('kit_body_mesh');me.from_pydata(a.vertices,[],a.faces);me.update()
    for m in mats:me.materials.append(m)
    roles={'costume':0,'coat':0,'face':1,'animal_face':1,'headwear':2}
    for poly,role in zip(me.polygons,a.roles):poly.material_index=roles[role];poly.use_smooth=True
    uv=me.uv_layers.new(name='UVMap')
    for poly,uvs in zip(me.polygons,a.uv):
        for li,pt in zip(poly.loop_indices,uvs):uv.data[li].uv=pt
    ca=me.color_attributes.new(name='Col',type='BYTE_COLOR',domain='CORNER');me.color_attributes.active_color=ca
    ramp=np.array([paint.color(pack,c) for c in pack['light_ramp']])/255
    light=Vector((-.45,-.7,.8)).normalized()
    # round 13 (STEER-5 §7): animal heads turn far from their rest orientation (sleep curl tucks the face up toward
    # the camera); their baked lighting is flatter so rest-pose underside shading never shows as a dark ring
    soft=set(a.parts.get('head',[]))|set(a.parts.get('neck',[])) if animal else set(a.parts.get('hood',[]))   # masked hood: keep the pearl paint bright
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi=me.loops[li].vertex_index;v=me.vertices[vi];n=v.normal
            shade=.76+.23*max(-.7,n.dot(light)) if vi not in soft else .82+.14*max(-.35,n.dot(light))
            # Dark hems, underarms, inside elbow and between thighs; no hard flat per-part colour.
            if not animal and v.co.z<a.params['height']*.12:shade-=.045
            ix=max(0,min(len(ramp)-1,round(shade*(len(ramp)-1))))
            ca.data[li].color_srgb=tuple(ramp[ix])+(1.,)
    ob=bpy.data.objects.new('kit_body',me);bpy.context.scene.collection.objects.link(ob)
    rigdata=bpy.data.armatures.new('human16_v1' if not animal else 'quad16_v1')
    rig=bpy.data.objects.new('rig_'+rigdata.name,rigdata);bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for name,xyz in a.bones.items():
        bone=rigdata.edit_bones.new(name);bone.head=xyz;bone.tail=Vector(xyz)+Vector((0,0,.05))
        if a.parents[name]:bone.parent=rigdata.edit_bones[a.parents[name]]
    bpy.ops.object.mode_set(mode='OBJECT');ob.parent=rig
    for name in a.bones:ob.vertex_groups.new(name=name)
    for i,weights in enumerate(a.weights):
        for name,w in weights.items():ob.vertex_groups[name].add([i],w,'REPLACE')
    mod=ob.modifiers.new('skin','ARMATURE');mod.object=rig
    if not animal:
        for slot,bone in [('hand_l','hand_l'),('hand_r','hand_r'),('head','head'),('back','spine'),('belt','pelvis')]:
            e=bpy.data.objects.new('attach_'+slot,None);bpy.context.scene.collection.objects.link(e)
            e.parent=rig;e.parent_type='BONE';e.parent_bone=bone;e.location=(0,-.05,0)
        for kind in prop_list or ():add_prop(rig,a,pack,packname,kind,folder,stance)
    rig['skeleton']='quad16_v1' if animal else 'human16_v1';rig['params_json']=json.dumps(p,sort_keys=True)
    rig['stance']=stance or 'neutral';rig['topology']=getattr(a,'topology','human16_hood_v1' if not animal else 'quad16_v1')
    if actions:make_actions(rig,ob,a)
    return rig,ob,a,pack


SLOT_BONE={'hand_l':'hand_l','hand_r':'hand_r','head':'head','back':'spine','belt':'pelvis'}


def add_prop(rig,a,pack,packname,kind,folder,stance=None):
    """Rigid prop on an attachment bone (separate node kit_acc_<slot>_<kind>, prop class budget).
    Rest transform from core/attach.py: lands upright/in-hand at the stance's idle pose."""
    from . import attach
    m=props.build(kind)
    bone=SLOT_BONE[m.slot]
    q_r,t_r=attach.attach(a,stance,kind)
    me=bpy.data.meshes.new('kit_acc_%s_%s_mesh'%(m.slot,kind));me.from_pydata(m.vertices,[],m.faces);me.update()
    im=image('tex_'+packname+'_prop_'+kind,props.texture(pack,kind),folder)
    mat=simplemat('mat_'+packname+'_prop_'+kind,im,pack,'prop');me.materials.append(mat)
    uv=me.uv_layers.new(name='UVMap')
    for poly,uvs in zip(me.polygons,m.uv):
        poly.use_smooth=True
        for li,pt in zip(poly.loop_indices,uvs):uv.data[li].uv=pt
    ca=me.color_attributes.new(name='Col',type='BYTE_COLOR',domain='CORNER');me.color_attributes.active_color=ca
    ramp=np.array([paint.color(pack,c) for c in pack['light_ramp']])/255;light=Vector((-.45,-.7,.8)).normalized()
    for poly in me.polygons:
        for li in poly.loop_indices:
            n=me.vertices[me.loops[li].vertex_index].normal;shade=.8+.2*max(-.7,n.dot(light))
            ix=max(0,min(len(ramp)-1,round(shade*(len(ramp)-1))));ca.data[li].color_srgb=tuple(ramp[ix])+(1.,)
    ob=bpy.data.objects.new('kit_acc_%s_%s'%(m.slot,kind),me);bpy.context.scene.collection.objects.link(ob)
    ob['n64_prop']={'kind':kind,'slot':m.slot,'tris':len(m.faces)}
    bpy.context.view_layer.update()
    ob.parent=rig;ob.parent_type='BONE';ob.parent_bone=bone
    bpy.context.view_layer.update()
    ob.matrix_world=Matrix.Translation(Vector(t_r))@Quaternion(q_r).to_matrix().to_4x4()
    ob['n64_prop']['rest_q']=list(q_r);ob['n64_prop']['rest_t']=list(t_r)
    return ob


def rotations(kind,clip,t):
    d={};wave=math.sin(t*math.tau)
    def r(n,x=0,y=0,z=0):d[n]=(x,y,z)
    if kind=='human':
        r('pelvis',0,.025*wave,.012);r('spine',.025*wave,-.065,.025+.025*wave);r('head',-.045,.07,.12*wave)
        for s,sg in [('l',1),('r',-1)]:
            r('upper_arm_'+s,-.10,sg*.065,sg*.035);r('forearm_'+s,-.24-.07*sg*wave)
        if clip=='idle':r('thigh_l',-.055);r('shin_l',.12)
        if clip in ('walk','run','carry'):
            amp=.5 if clip!='run' else .85
            r('spine',-.10 if clip=='run' else -.025,0,.05*wave)
            for s,sg in [('l',1),('r',-1)]:
                r('thigh_'+s,amp*sg*wave);r('shin_'+s,.10+max(0,sg*wave)*(.9 if clip=='run' else .5));r('foot_'+s,-.08)
                r('upper_arm_'+s,-amp*.65*sg*wave,0,sg*.05);r('forearm_'+s,-.2 if clip!='run' else -.65)
            if clip=='carry':
                for s,sg in [('l',1),('r',-1)]:r('upper_arm_'+s,-.22,sg*.18,sg*.02);r('forearm_'+s,-1.15)
        if clip=='interact':
            k=.5-.5*math.cos(t*math.tau);r('upper_arm_r',-1.0*k);r('forearm_r',-.4*k);r('spine',-.13*k)
        if clip=='talk':
            r('upper_arm_l',-.28-.2*wave,-.2,-.12);r('forearm_l',-.8-.18*wave);r('hand_l',.05,.15,.15)
            r('upper_arm_r',-.3+.1*wave,.12,.16);r('forearm_r',-.45+.2*wave);r('head',.07*wave,0,.15*wave)
        if clip=='sit':
            for s,sg in [('l',1),('r',-1)]:r('thigh_'+s,-1.35);r('shin_'+s,1.28);r('upper_arm_'+s,-.3);r('forearm_'+s,-.65)
    else:
        r('head',0,0,.04*wave);r('tail_1',0,0,.06*wave);r('tail_2',0,0,.12*wave)
        if clip in ('walk','run'):
            amp=.4 if clip=='walk' else .65
            for limb,sg in [('fl',1),('br',1),('fr',-1),('bl',-1)]:r('leg_'+limb,amp*sg*wave);r('paw_'+limb,-amp*sg*wave*.6)
        if clip=='sit':
            r('hips',-.6);r('chest',.45);r('neck',.15)
            for s in ('l','r'):r('leg_b'+s,-1);r('paw_b'+s,1.25);r('leg_f'+s,.15)
            r('tail_1',0,0,1.0);r('tail_2',0,0,.55);r('tail_3',0,0,.4)
        if clip in ('loaf','sleep_curled'):
            for s in ('l','r'):r('leg_f'+s,1.42);r('paw_f'+s,-1.42);r('leg_b'+s,-1.42);r('paw_b'+s,1.42)
            r('neck',.14)
            if clip=='sleep_curled':
                r('chest',0,0,.65);r('neck',.42,0,.55);r('head',.62,0,.55)
                r('tail_1',-.45,0,1.1);r('tail_2',0,0,.85);r('tail_3',0,0,.8)
        if clip=='stretch':
            r('chest',-.32);r('neck',.28)
            for s in ('l','r'):r('leg_f'+s,-.8);r('paw_f'+s,.8);r('leg_b'+s,.3)
    return d


def pose(rig,ob,a,clip,t=0,ground=True,stance=None):
    """Shared clip at time t plus the character's stance (rig['stance'] if not given)."""
    basis=Quaternion((1,0,0),math.pi/2)
    st=stance if stance is not None else rig.get('stance','neutral')
    d=posing.local_rotations(a.bones,a.params.get('height',1.),a.kind,clip,t,st,posing.body_metrics(a))
    for pb in rig.pose.bones:
        pb.rotation_mode='QUATERNION';q=Quaternion(d.get(pb.name,(1,0,0,0)))
        pb.rotation_quaternion=basis.inverted()@q@basis;pb.location=(0,0,0)
    bpy.context.view_layer.update()
    # round 13: face atlas cell per clip (extras n64.atlas.clip_cells, e.g. closed eyes while sleeping)
    for m in ob.data.materials:
        at=(m.get('n64') or {}).get('atlas') if m else None
        mp=m.node_tree.nodes.get('expression_offset') if (m and at) else None
        if mp is not None:
            cells=dict(at.get('clip_cells',{}));cell=int(cells.get(clip,at['cell']));cols=int(at['cols']);rows=int(at['rows'])
            mp.inputs['Location'].default_value=(cell%cols/cols,cell//cols/rows,0)
    if ground:
        deps=bpy.context.evaluated_depsgraph_get();ev=ob.evaluated_get(deps)
        bottom=min(v.co.z for v in ev.data.vertices)
        rig.pose.bones['root'].location=(0,-bottom,0)
    bpy.context.view_layer.update()


def fcurves(act):
    return [fc for l in act.layers for s in l.strips for c in s.channelbags for fc in c.fcurves]


def make_actions(rig,ob,a):
    rig.animation_data_create();bpy.context.scene.render.fps=15
    for clip in (HCLIPS if a.kind=='human' else ACLIPS):
        act=bpy.data.actions.new(clip);rig.animation_data.action=act
        for f in range(16):
            pose(rig,ob,a,clip,f/15)
            for pb in rig.pose.bones:pb.keyframe_insert('rotation_quaternion',frame=f)
            rig.pose.bones['root'].keyframe_insert('location',frame=f)
        for fc in fcurves(act):
            for kp in fc.keyframe_points:kp.interpolation='CONSTANT'
        tr=rig.animation_data.nla_tracks.new();tr.name=clip;tr.strips.new(clip,0,act);tr.mute=True
        rig.animation_data.action=None
    for pb in rig.pose.bones:pb.rotation_quaternion=(1,0,0,0);pb.location=(0,0,0)
    bpy.context.scene.frame_set(0);bpy.context.view_layer.update()


def export(path):
    # Chrome recipe retains a metallic fallback in GLB; preview uses period sphere map.
    for m in bpy.data.materials:
        if m.get('n64',{}).get('kind')=='chrome_env':
            nt=m.node_tree;nt.nodes.clear();p=nt.nodes.new('ShaderNodeBsdfPrincipled');o=nt.nodes.new('ShaderNodeOutputMaterial')
            tint=paint.color(loadpack(m['n64']['pack']),'white')/255
            tint=np.where(tint<=.04045,tint/12.92,((tint+.055)/1.055)**2.4)
            p.inputs['Base Color'].default_value=tuple(tint)+(1,);p.inputs['Metallic'].default_value=1;p.inputs['Roughness'].default_value=.2
            nt.links.new(p.outputs[0],o.inputs['Surface'])
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_yup=True,export_extras=True,
      export_cameras=False,export_lights=False,export_force_sampling=False,export_vertex_color='ACTIVE',
      export_animation_mode='ACTIONS',export_image_format='AUTO',export_apply=False,export_texcoords=True,
      export_normals=True,export_skins=True,export_morph=False,export_def_bones=False,export_leaf_bone=False,
      export_optimize_animation_size=False,export_reset_pose_bones=True,export_rest_position_armature=True,check_existing=False)
