"""Assemble a generated Asset into the Blender scene with a pack's materials (bpy)."""
from . import bake, blendio


def assemble(asset, pack, tex_dir):
    mf = blendio.MaterialFactory(pack, tex_dir)
    ramp = [pack.pal.rgb(i) for i in pack.light_ramp]
    rig = bake.asset_rig(pack.light_rig, asset)  # DUNGEONKIT: opt-in baked point lights / ray AO (pack data)
    info = {"animations": False}
    for node in asset.nodes:
        blendio.make_mesh_object(node, mf, rig, ramp)
    if asset.character:
        from . import charrig
        info["animations"] = True
        info["character"] = charrig.assemble_character(asset, pack, mf, ramp)
    info["textures"] = mf.written
    return info
