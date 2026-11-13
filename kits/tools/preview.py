"""Preview renderer = reference implementation of the KITS runtime material recipes (Cycles,
emission-only, so colours are exactly texture x COLOR_0, matcap chrome, distance fog).
Renders re-imported GLBs (round trip), at low resolution, upscaled nearest for sheets."""
import math
import os
import sys

import bpy
import numpy as np

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if LANE not in sys.path:
    sys.path.insert(0, LANE)

from core import png  # noqa: E402
from core.palette import srgb_to_linear  # noqa: E402
from core.texgen import make_texture  # noqa: E402


def env_image(pack, name):
    d = os.path.join(LANE, "kits", pack.id, "env")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".png")
    arr = make_texture(pack.env_maps[name], pack.pal, pack.id, name)
    data = png.encode(arr)
    if not (os.path.exists(p) and open(p, "rb").read() == data):
        open(p, "wb").write(data)
    key = "envprev_" + pack.id + "_" + name
    if key in bpy.data.images:
        return bpy.data.images[key]
    im = bpy.data.images.load(p)
    im.name = key
    return im


def lin(pack, name):
    c = srgb_to_linear(np.array(pack.pal.rgb(name)) / 255.0)
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


def new_scene(pack, res=(320, 240), samples=4, fog="interior"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.device = "CPU"
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.filter_size = 0.75
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    f = pack.fog.get("interior", pack.fog) if fog == "interior" else pack.fog
    if fog == "none":
        f = None
    w = bpy.data.worlds.new("w")
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    col = lin(pack, (f or pack.fog)["color"])
    bg.inputs["Color"].default_value = col
    sc["fog"] = {"color": list(col), "start": float(f["start"]) if f else 1e6, "end": float(f["end"]) if f else 2e6}
    return sc


def _fog_mix(nt, color_socket, sc):
    f = sc["fog"]
    lp = nt.nodes.new("ShaderNodeLightPath")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = f["start"]
    mr.inputs["From Max"].default_value = f["end"]
    mr.clamp = True
    nt.links.new(lp.outputs["Ray Length"], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[7].default_value = tuple(f["color"])
    nt.links.new(mr.outputs["Result"], mix.inputs[0])
    nt.links.new(color_socket, mix.inputs[6])
    return mix.outputs[2]


def preview_material(src, pack, sc):
    info = dict(src.get("n64", {})) if src is not None else {}
    kind = info.get("kind", "baked_unlit")
    img = None
    mapping = None
    tint = (1, 1, 1, 1)
    if src is not None and src.node_tree:
        for n in src.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image is not None and img is None:
                img = n.image
            if n.type == "MAPPING":
                mapping = (tuple(n.inputs["Location"].default_value), tuple(n.inputs["Scale"].default_value))
            if n.type == "BSDF_PRINCIPLED":
                tint = tuple(n.inputs["Base Color"].default_value)
    if info.get("tint") and pack is not None:
        # the exported baseColorFactor comes back from the importer wired into a vertex-colour multiply, so the
        # BSDF default_value is NOT the tint; use the material's own extras.n64.tint (palette name). (Before
        # this fix every chrome_env/glass_env preview used the importer's default 0.8 grey.)
        c = np.array(pack.pal.rgb(info["tint"]), dtype=float) / 255.0
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        tint = (float(c[0]), float(c[1]), float(c[2]), 1.0)
    m = bpy.data.materials.new("prev_" + (src.name if src else "none"))
    if m.node_tree is None:  # Blender 4.x; leave the existing 5.x tree untouched
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Color"
    if kind in ("chrome_env", "glass_env"):
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        vt = nt.nodes.new("ShaderNodeVectorTransform")
        vt.vector_type = "NORMAL"
        vt.convert_from = "WORLD"
        vt.convert_to = "CAMERA"
        nt.links.new(geo.outputs["Normal"], vt.inputs["Vector"])
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(vt.outputs["Vector"], sep.inputs["Vector"])
        cmb = nt.nodes.new("ShaderNodeCombineXYZ")
        for i, ax in enumerate(("X", "Y")):
            ma = nt.nodes.new("ShaderNodeMath")
            ma.operation = "MULTIPLY_ADD"
            ma.inputs[1].default_value = 0.5
            ma.inputs[2].default_value = 0.5
            nt.links.new(sep.outputs[ax], ma.inputs[0])
            nt.links.new(ma.outputs[0], cmb.inputs[ax])
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = env_image(pack, info.get("env", list(pack.env_maps)[0]))
        t.interpolation = "Linear"
        t.extension = "EXTEND"
        nt.links.new(cmb.outputs["Vector"], t.inputs["Vector"])
        m1 = nt.nodes.new("ShaderNodeMix")
        m1.data_type = "RGBA"
        m1.blend_type = "MULTIPLY"
        m1.inputs[0].default_value = 1.0
        nt.links.new(t.outputs["Color"], m1.inputs[6])
        m1.inputs[7].default_value = tint
        m2 = nt.nodes.new("ShaderNodeMix")
        m2.data_type = "RGBA"
        m2.blend_type = "MULTIPLY"
        m2.inputs[0].default_value = 1.0
        nt.links.new(m1.outputs[2], m2.inputs[6])
        nt.links.new(vc.outputs["Color"], m2.inputs[7])
        col = m2.outputs[2]
    else:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        t.interpolation = "Linear"
        t.extension = "REPEAT"
        if mapping:
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Location"].default_value = mapping[0]
            mp.inputs["Scale"].default_value = mapping[1]
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        col = t.outputs["Color"]
        if kind in ("baked_unlit", "water", "face_atlas"):
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 1.0
            nt.links.new(col, mx.inputs[6])
            nt.links.new(vc.outputs["Color"], mx.inputs[7])
            col = mx.outputs[2]
    if kind != "view_plane":
        col = _fog_mix(nt, col, sc)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    shader = em.outputs[0]
    if kind == "card_alpha" and img is not None:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        gt = nt.nodes.new("ShaderNodeMath")
        gt.operation = "GREATER_THAN"
        gt.inputs[1].default_value = 0.5
        nt.links.new(t.outputs["Alpha"], gt.inputs[0])
        mxs = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(gt.outputs[0], mxs.inputs[0])
        nt.links.new(tr.outputs[0], mxs.inputs[1])
        nt.links.new(shader, mxs.inputs[2])
        shader = mxs.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    m.use_backface_culling = src.use_backface_culling if src is not None else True
    return m


def import_glb(path, loc=(0, 0, 0), rot_z=0.0, pack=None, sc=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    from mathutils import Matrix
    bpy.context.view_layer.update()
    for o in roots:
        # placement = translate(loc) * rotateZ(rot_z) * the node's own transform (asset origin = pivot).
        # (Earlier code set o.location first and then multiplied a stale matrix_world, which moved
        # rotated pieces toward the room centre.)
        m0 = o.matrix_world.copy()
        o.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(rot_z, 4, "Z") @ m0
    cache = {}
    for o in new:
        if o.type != "MESH":
            if o.type == "EMPTY" and o.empty_display_type != "PLAIN_AXES":
                pass
            continue
        for i, ms in enumerate(o.material_slots):
            src = ms.material
            key = src.name if src else None
            if key not in cache:
                cache[key] = preview_material(src, pack, sc)
            ms.material = cache[key]
    # hide armature bone shapes
    for o in new:
        if o.type == "MESH" and o.name.lower().startswith("icosphere"):
            o.hide_render = True
    return new


def camera(sc, target, dist, az_deg, el_deg, fov_deg=40.0, ortho=None):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    az, el = math.radians(az_deg), math.radians(el_deg)
    tx, ty, tz = target
    cam.location = (tx + dist * math.cos(el) * math.sin(az), ty - dist * math.cos(el) * math.cos(az), tz + dist * math.sin(el))
    d = np.array(target) - np.array(cam.location)
    from mathutils import Vector
    cam.rotation_euler = Vector(d).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov_deg)
    cam.data.clip_start = 0.02
    cam.data.clip_end = max(500.0, dist * 4.0)  # large skies are framed from far away
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    sc.camera = cam
    return cam


def scene_bounds(objs):
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for o in objs:
        if o.type != "MESH" or o.hide_render:
            continue
        M = np.array(o.matrix_world)
        for c in o.bound_box:
            p = M @ np.array([c[0], c[1], c[2], 1.0])
            lo = np.minimum(lo, p[:3])
            hi = np.maximum(hi, p[:3])
    return lo, hi


def render(sc, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def frame_objects(sc, objs, az=35, el=22, fov=36, margin=1.15):
    lo, hi = scene_bounds(objs)
    c = (lo + hi) / 2
    r = float(np.linalg.norm(hi - lo)) / 2 * margin
    dist = r / math.tan(math.radians(fov) / 2)
    return camera(sc, tuple(c), dist, az, el, fov)


def thumb(glb_path, pack, out_png, res=(64, 64), az=35, el=22, inside=False):
    """inside=True (sky class): the viewer stands at the origin and looks at the horizon, as the asset is
    consumed (an inward-facing dome seen from outside shows mostly its back faces)."""
    sc = new_scene(pack, res, samples=1, fog="none")
    objs = import_glb(glb_path, pack=pack, sc=sc)
    if inside:
        cam = camera(sc, (0.0, 1.0, 1.6 + math.tan(math.radians(18.0))), 1.0, 0.0, -18.0, 100.0)
        cam.location = (0.0, 0.0, 1.6)
        # skies reach 1800 m: the default 500 m clip hid every large sky (core30_e thumbs were empty, which
        # the visdiff size rule then excused; found when the size rule was turned off for skies)
        cam.data.clip_end = 4000.0
    else:
        frame_objects(sc, objs, az, el)
    return render(sc, out_png)


def load_png(path):
    return png.read(path)[:, :, :3]


def upscale(arr, k):
    return np.repeat(np.repeat(arr, k, 0), k, 1)


def sheet(cells, cols, out, cell_scale=2, pad=4, bg=(10, 12, 24), labels=None, label_color=(235, 235, 245), title=None):
    from tools.pixfont import draw_text
    imgs = [upscale(c, cell_scale) for c in cells]
    h = max(i.shape[0] for i in imgs)
    w = max(i.shape[1] for i in imgs)
    rows = (len(imgs) + cols - 1) // cols
    top = 16 if title else 0
    H = rows * (h + pad) + pad + top
    W = cols * (w + pad) + pad
    S = np.zeros((H, W, 3), dtype=np.uint8)
    S[:, :] = bg
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        y = top + pad + r * (h + pad)
        x = pad + c * (w + pad)
        S[y:y + im.shape[0], x:x + im.shape[1]] = im
        if labels:
            draw_text(S, labels[k][:max(1, w // 8)], x + 3, y + 3, label_color, scale=2 if w >= 200 else 1)
    if title:
        draw_text(S, title, pad, 4, label_color, scale=2)
    png.write(out, S)
    return out
