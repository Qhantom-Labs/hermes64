"""Blender-side assembly: pack materials/textures, mesh objects (UVs, baked COLOR_0), armatures,
actions, deterministic GLB export. Only module (with gen_char) that imports bpy."""
import hashlib
import json
import os

import bpy
import numpy as np

from . import bake, png
from .packs import TEXTURED_KINDS
from .palette import srgb_to_linear
from .texgen import make_texture

EXPORT_OPTS = dict(
    export_format="GLB", export_yup=True, export_extras=True, export_cameras=False, export_lights=False,
    export_force_sampling=False, export_vertex_color="ACTIVE", export_animation_mode="ACTIONS",
    export_image_format="AUTO", export_apply=False, export_texcoords=True, export_normals=True,
    export_materials="EXPORT", export_skins=True, export_morph=False, export_def_bones=False,
    export_leaf_bone=False, export_optimize_animation_size=False, export_reset_pose_bones=True,
    export_rest_position_armature=True, check_existing=False, export_tangents=False,
)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 12


def _nt_clear(m):
    # 4.x materials start without nodes; 5.x already has a tree. Do not touch the
    # deprecated use_nodes property on 5.x: preserve its exported material bytes.
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return nt


class MaterialFactory:
    """Creates pack materials on demand. Textures are written once per pack to tex_dir (content
    addressed by role) and loaded from file so the GLB embeds our exact palette PNG bytes."""

    def __init__(self, pack, tex_dir):
        self.pack = pack
        self.tex_dir = tex_dir
        os.makedirs(tex_dir, exist_ok=True)
        self.cache = {}
        self.images = {}
        self.written = {}

    def image_from_array(self, name, arr):
        if name in self.images:
            return self.images[name]
        path = os.path.join(self.tex_dir, name + ".png")
        data = png.encode(arr)
        if not (os.path.exists(path) and open(path, "rb").read() == data):
            with open(path, "wb") as f:
                f.write(data)
        im = bpy.data.images.load(path, check_existing=True)
        im.name = name
        im.colorspace_settings.name = "sRGB"
        self.images[name] = im
        self.written[name] = {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": [int(arr.shape[1]), int(arr.shape[0])]}
        return im

    def role_image(self, role):
        spec = self.pack.mat(role)
        arr = make_texture(spec["texture"], self.pack.pal, self.pack.seed_id, role)
        if spec["kind"] == "card_alpha":
            from .texgen import alpha_mask
            a = alpha_mask(spec["texture"].get("alpha", "disc"), arr.shape[0], self.pack.seed_id, role)
            arr = np.concatenate([arr, a[:, :, None]], 2)
        return self.image_from_array("tex_%s_%s" % (self.pack.id, role), arr)

    def tile_m(self, role):
        return float(self.pack.mat(role).get("tile_m", 1.0))

    def kind(self, role):
        return self.pack.mat(role)["kind"]

    def get(self, role):
        if role in self.cache:
            return self.cache[role]
        spec = self.pack.mat(role)
        m = build_material("mat_%s_%s" % (self.pack.id, role), spec, self.pack,
                           self.role_image(role) if spec["kind"] in TEXTURED_KINDS else None, role)
        self.cache[role] = m
        return m


def build_material(name, spec, pack, image, role, mapping=None, extra=None):
    kind = spec["kind"]
    m = bpy.data.materials.new(name)
    nt = _nt_clear(m)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    info = {"kind": kind, "role": role, "pack": pack.id}
    if spec.get("tile_m"):
        info["tile_m"] = float(spec["tile_m"])
    if kind in ("chrome_env", "glass_env"):
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tint = srgb_to_linear(np.array(pack.pal.rgb(spec["tint"])) / 255.0)
        b.inputs["Base Color"].default_value = (float(tint[0]), float(tint[1]), float(tint[2]), 1.0)
        b.inputs["Metallic"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.2 if kind == "chrome_env" else 0.05
        nt.links.new(b.outputs[0], o.inputs["Surface"])
        info["env"] = spec["env"]
        info["tint"] = spec["tint"]
    else:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image
        t.interpolation = "Linear"
        t.extension = "REPEAT"
        if mapping is not None:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Location"].default_value = (mapping[0], mapping[1], 0.0)
            mp.inputs["Scale"].default_value = (mapping[2], mapping[3], 1.0)
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        if kind == "card_alpha":
            em = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(t.outputs["Color"], em.inputs["Color"])
            lp = nt.nodes.new("ShaderNodeLightPath")
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            mx = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0])
            nt.links.new(tr.outputs[0], mx.inputs[1])
            nt.links.new(em.outputs[0], mx.inputs[2])
            lt = nt.nodes.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            lt.inputs[1].default_value = 0.5
            nt.links.new(t.outputs["Alpha"], lt.inputs[0])
            sb = nt.nodes.new("ShaderNodeMath")
            sb.operation = "SUBTRACT"
            sb.inputs[0].default_value = 1.0
            nt.links.new(lt.outputs[0], sb.inputs[1])
            mx2 = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(sb.outputs[0], mx2.inputs[0])
            nt.links.new(tr.outputs[0], mx2.inputs[1])
            nt.links.new(mx.outputs[0], mx2.inputs[2])
            nt.links.new(mx2.outputs[0], o.inputs["Surface"])
        else:
            src = t.outputs["Color"]
            if kind in ("baked_unlit", "water", "face_atlas"):
                vc = nt.nodes.new("ShaderNodeVertexColor")
                vc.layer_name = "Col"
                mix = nt.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs[0].default_value = 1.0
                nt.links.new(src, mix.inputs[6])
                nt.links.new(vc.outputs["Color"], mix.inputs[7])
                src = mix.outputs[2]
            bg = nt.nodes.new("ShaderNodeBackground")
            nt.links.new(src, bg.inputs["Color"])
            nt.links.new(bg.outputs[0], o.inputs["Surface"])
        if kind == "water":
            info["scroll"] = list(spec.get("scroll", [0.02, 0.01]))
        info["texture"] = image.name
    m.use_backface_culling = not spec.get("double_sided", False) and kind != "card_alpha"
    if extra:
        info.update(extra)
    m["n64"] = info
    return m


def make_mesh_object(node, mf, rig, ramp_rgb8, name_override=None, materials=None, uv_override=None):
    """node: core.asset.Node. mf: MaterialFactory (materials per role) unless `materials` maps
    role -> bpy material (characters). Returns the bpy object (linked to the scene)."""
    mesh = node.mesh
    ox, oy, oz = node.origin
    roles = []
    for r in mesh.r:
        if r not in roles:
            roles.append(r)
    slot = {r: i for i, r in enumerate(roles)}
    me = bpy.data.meshes.new((name_override or node.name) + "_mesh")
    verts = [(x - ox, y - oy, z - oz) for x, y, z in mesh.v]
    me.from_pydata(verts, [], [list(f) for f in mesh.f])
    for r in roles:
        me.materials.append(materials[r] if materials else mf.get(r))
    me.polygons.foreach_set("material_index", [slot[r] for r in mesh.r])
    me.polygons.foreach_set("use_smooth", [bool(s) for s in mesh.s])
    # UVs
    kind_of = (lambda r: materials[r]["n64"]["kind"]) if materials else mf.kind
    tile_of = (lambda r: 1.0) if materials else mf.tile_m
    uvs = uv_override if uv_override is not None else bake.corner_uvs(mesh, tile_of)
    flat_uv = [c for face in uvs for uv in face for c in uv]
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", flat_uv)
    # baked light -> COLOR_0 (corner, sRGB bytes = light-ramp palette colours)
    steps = bake.bake_corner_light(mesh, rig, len(ramp_rgb8), kind_of, origin_z=0.0)
    cols = []
    for face in steps:
        for s in face:
            c = ramp_rgb8[s]
            cols.extend((c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0))
    ca = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    ca.data.foreach_set("color_srgb", cols)
    me.color_attributes.active_color = ca
    me.update()
    ob = bpy.data.objects.new(name_override or node.name, me)
    ob.location = (ox, oy, oz)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def export_glb(path, animations=False):
    opts = dict(EXPORT_OPTS)
    opts["export_animations"] = bool(animations)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    r = bpy.ops.export_scene.gltf(filepath=path, **opts)
    if "FINISHED" not in r:
        raise RuntimeError("glTF export failed: %r" % (r,))
    with open(path, "rb") as f:
        return f.read()


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
