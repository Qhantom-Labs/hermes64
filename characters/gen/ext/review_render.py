"""Review renders inside the Blender build session (lane CHARSYS): front / three-quarter / side at 320x240.

The materials are the export materials (core/blender.simplemat: texture x baked vertex light through a Background
node = unlit, like the runtime's baked_unlit path), so the image shows exactly what was exported, not a re-lit
version. Film is transparent; the caller composites the alpha over snow and dark backgrounds for the readability
gate and the contact sheet. Cycles, 8 samples, orthographic camera, deterministic settings.
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector

VIEWS = {'front': 0., 'three_quarter': -math.pi / 4, 'side': -math.pi / 2}


def _scene(w, h):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 8; sc.cycles.use_denoising = False
    sc.cycles.seed = 0
    sc.render.resolution_x = w; sc.render.resolution_y = h; sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'
    if sc.world is None:
        sc.world = bpy.data.worlds.new('review_world')
    return sc


def _camera(target, yaw, ortho, elev, dist=6.):
    sc = bpy.context.scene
    cam = sc.objects.get('review_camera')
    if cam is None:
        camd = bpy.data.cameras.new('review_camera'); cam = bpy.data.objects.new('review_camera', camd)
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    cam.location = target + Vector((math.sin(yaw) * dist, -math.cos(yaw) * dist, elev))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    return cam


def render_views(out_dir, stem, height, views=('front', 'three_quarter', 'side'), w=240, h=320, hover=0., extent=0.):
    """Render the posed scene from each view -> {view: png path}. Character height in metres frames the shot."""
    sc = _scene(w, h)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    if sc.objects.get('review_shadow') is None:
        # the runtime's blob shadow (actors/character.gd: radius .32, flattened .7, alpha .28): shows hover and
        # grounding in the sheet exactly where the game will draw it
        mat = bpy.data.materials.new('review_shadow_mat'); nt = mat.node_tree; nt.nodes.clear()
        em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (.04, .04, .08, 1)
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); mix = nt.nodes.new('ShaderNodeMixShader')
        mix.inputs[0].default_value = .28
        o = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], o.inputs[0])
        me = bpy.data.meshes.new('review_shadow_mesh')
        import math as _m
        verts = [(0., 0., .004)] + [(_m.cos(_m.tau * i / 24) * .32, _m.sin(_m.tau * i / 24) * .32 * .7, .004) for i in range(24)]
        faces = [(0, 1 + i, 1 + (i + 1) % 24) for i in range(24)]
        me.from_pydata(verts, [], faces); me.update(); me.materials.append(mat)
        sh = bpy.data.objects.new('review_shadow', me); sc.collection.objects.link(sh)
    top = height + hover
    target = Vector((0, 0, top * .5))
    ortho = max(top, extent * .9) * 1.22        # long bodies (quadrupeds) are framed by their length
    paths = {}
    for v in views:
        _camera(target, VIEWS[v], ortho, elev=top * .18)
        path = out_dir / ('%s_%s.png' % (stem, v))
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths[v] = str(path)
    return paths


def _lin(hexs):
    c = [int(hexs[i:i + 2], 16) / 255. for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c) + (1.,)


def _flat_mat(name, hexs):
    mat = bpy.data.materials.new(name); nt = mat.node_tree; nt.nodes.clear()
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = _lin(hexs); em.inputs['Strength'].default_value = 1.
    o = nt.nodes.new('ShaderNodeOutputMaterial'); nt.links.new(em.outputs[0], o.inputs[0])
    return mat


def render_room(out_dir, stem, height, floor_hex, wall_hex, hover=0., w=320, h=240):
    """Game-scale preview: the character in a plain unlit room seen like the runtime's showcase cameras (about 5.2 m
    away, 1.9 m above the target, 62 degree vertical FOV) at the runtime's internal 320x240. A Blender preview of the
    framing, not a runtime capture (golden sheets use the Godot runtime)."""
    sc = _scene(w, h)
    sc.render.film_transparent = False
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, size, loc, rot, hexs in (('room_floor', 9., (0., 1., 0.), (0., 0., 0.), floor_hex),
                                       ('room_wall', 9., (0., 3.2, 4.5), (math.pi / 2, 0., 0.), wall_hex),
                                       ('room_side', 9., (-3.4, 1., 4.5), (0., math.pi / 2, 0.), wall_hex)):
        me = bpy.data.meshes.new(name + '_mesh')
        s = size / 2.
        me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)]); me.update()
        me.materials.append(_flat_mat(name + '_mat', hexs))
        ob = bpy.data.objects.new(name, me); ob.location = loc; ob.rotation_euler = rot
        sc.collection.objects.link(ob); made.append(ob)
    cam = sc.objects.get('room_camera')
    if cam is None:
        camd = bpy.data.cameras.new('room_camera'); cam = bpy.data.objects.new('room_camera', camd)
        sc.collection.objects.link(cam)
    cam.data.type = 'PERSP'; cam.data.sensor_fit = 'VERTICAL'; cam.data.angle_y = math.radians(62.)
    target = Vector((0., 0., .9 if height > 1.2 else height * .6))
    cam.location = target + Vector((2.2, -4.2, 1.9))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    path = out_dir / ('%s_room.png' % stem)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for ob in made:
        bpy.data.objects.remove(ob, do_unlink=True)
    sc.render.film_transparent = True
    return str(path)
