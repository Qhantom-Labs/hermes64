"""Build pipeline used by build.py, sweeps, gates and the manifest builder (inside Blender).

resolve -> generate (theme-agnostic) -> assemble with pack materials -> export GLB ->
re-read GLB -> validators -> sidecar JSON."""
import hashlib
import json
import os
import time
import traceback

from . import CORE_VERSION
from . import schema as S
from .asset import REGISTRY
from .packs import CORE_CLASSES, Pack

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACKS = {}


# People/animals moved to lane-characters (2026-11-07 scope change). core/gen_char.py, charrig.py and
# chartex.py stay in place FROZEN and are deliberately NOT loaded: the core registry, sweeps and the
# manifest contain only theme-agnostic environment generators.
FROZEN_MODULES = ("gen_char", "charrig", "chartex")


def load_generators():
    from . import gen_arch, gen_terrain, gen_nature, gen_furniture, gen_molded, gen_vehicles, gen_props  # noqa: F401
    from . import gen_dungeon, gen_dprops, gen_cave, gen_temple  # noqa: F401  DUNGEONKIT (dgn. dprop. cave. lake. tmpl.)
    from . import gen_scifikit  # noqa: F401  SCIFIKIT (stn. tech. ship. alien. planet. skyx.)
    from . import gen_ancientkit  # noqa: F401  ANCIENTKIT ruin./relic./wild./land. families
    from . import gen_medievalkit_village, gen_medievalkit_village2, gen_medievalkit_castle, gen_medievalkit_props, gen_medievalkit_nature  # noqa: F401,E501  MEDIEVALKIT (vlg. cst. mprop. mnat. mter.)
    from . import gen_westernkit_paint, gen_westernkit_town, gen_westernkit_rail, gen_westernkit_props, gen_westernkit_land  # noqa: F401  WESTERNKIT (wtown. wrail. wmine. wprop. wland. wsky.)
    from . import gen_cyberkit  # noqa: F401  CYBERKIT (cytower. cystreet. cysign. cytech. cyroom. cydress. cysky.)
    return REGISTRY


def get_pack(pack_id, path=None):
    key = path or pack_id
    if key not in _PACKS:
        p = path or os.path.join(LANE, "packs", pack_id, "pack.json")
        if not os.path.exists(p):
            raise S.ParamError("unknown pack %r" % pack_id)
        _PACKS[key] = Pack(p)
    return _PACKS[key]


def resolve(spec, pack, preset=None, params=None):
    layers = []
    presets = pack.presets.get(spec.id, {})
    if "default" in presets:
        layers.append(("pack[%s].kit_presets[%s].default" % (pack.id, spec.id), presets["default"]))
    if preset is not None:
        if preset not in presets:
            raise S.ParamError("unknown preset %r for %s in pack %s (have: %s)" % (preset, spec.id, pack.id, sorted(presets)))
        layers.append(("preset[%s]" % preset, presets[preset]))
    layers.append(("params", params or {}))
    P = S.resolve(spec.schema, layers, pack.palette_names)
    if spec.rules:
        msg = spec.rules(P)
        if msg:
            raise S.ParamError("rule: %s" % msg)
    return P


def build_one(gid, pack_id, preset=None, params=None, seed=0, out=None, tex_dir=None, validate=True,
              pack_path=None, keep_failed=False, builder="blender"):
    """Returns (status, report). builder=python|blender|auto; no implicit subprocesses."""
    t0 = time.time()
    rep = {"id": gid, "pack": pack_id, "preset": preset, "seed": seed, "out": out, "core_version": CORE_VERSION}
    try:
        reg = load_generators()
        if gid not in reg:
            raise S.ParamError("unknown generator id %r" % gid)
        spec = reg[gid]
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0 or seed > 2 ** 31:
            raise S.ParamError("seed must be an integer in [0, 2^31]")
        pack = get_pack(pack_id, pack_path)
        P = resolve(spec, pack, preset, params)
    except S.ParamError as e:
        rep["error"] = str(e)
        return "rejected", rep
    except Exception as e:
        rep["error"] = "pack/param error: %s" % e
        return "rejected", rep
    rep.update({"version": spec.version, "class": spec.cls, "params": P})
    try:
        asset = spec.build(P, seed)
        if builder not in ("python", "blender", "auto"):
            raise ValueError("builder must be python, blender or auto")
        selected = ("blender" if asset.character else "python") if builder == "auto" else builder
        rep["builder"] = selected
        tdir = tex_dir or os.path.join(os.path.dirname(os.path.abspath(out)), "textures")
        if selected == "python":
            from . import pybuild
            data, info = pybuild.build(asset, pack, out, tdir)
        else:
            try:
                from . import blendio
                from .assemble import assemble
            except ImportError as exc:
                raise RuntimeError("Blender Python (bpy) required for builder=blender/armatures; configure blender_path or use builder=python for static kits") from exc
            blendio.reset()
            info = assemble(asset, pack, tdir)
            data = blendio.export_glb(out, animations=info.get("animations", False))
        rep["sha256"] = hashlib.sha256(data).hexdigest()
        rep["bytes"] = len(data)
        rep["meta"] = asset.meta
        rep["textures_written"] = info.get("textures", {})
        if info.get("character"):
            rep["character"] = info["character"]
    except Exception as e:
        rep["error"] = "build error: %s" % e
        rep["traceback"] = traceback.format_exc()[-3000:]
        return "error", rep
    tri_limit = pack.tri_limit(spec.cls, CORE_CLASSES[spec.cls])
    rep["tri_limit"] = tri_limit
    if validate:
        res = validate_file(out, spec, pack, tri_limit, asset)
        rep["validation"] = res
        rep["hashes"] = res.pop("_hashes")
        rep["tri_count"] = res["budget"]["measured"]["tris"]
        ok = all(v["ok"] for v in res.values())
    else:
        ok = True
    rep["seconds"] = round(time.time() - t0, 3)
    if not ok and not keep_failed and out and os.path.exists(out):
        os.remove(out)
        rep["deleted_failed_output"] = True
    return ("passed" if ok else "failed"), rep


def validate_file(path, spec, pack, tri_limit, asset=None):
    from validate.glb import GLB, hashes
    from validate import checks as C
    g = GLB(path)
    res = {}
    res["budget"] = C.check_budget(g, spec.cls, tri_limit)
    res["palette"] = C.check_palette(g, pack.pal, pack.light_ramp)
    bones = asset.character["bones"] if (asset is not None and asset.character) else ()
    res["naming"] = C.check_naming(g, bones)
    res["origin_scale"] = C.check_origin_scale(g, spec.cls, spec.origin)
    res["topology"] = C.check_topology(g)
    if asset is not None and asset.character:
        ch = asset.character
        res["rig"] = C.check_rig(g, ch["reference"], ch["clips"], ch["attachments"],
                                 stretch=tuple(pack.thresholds.get("stretch", (0.45, 1.8))))
    res["_hashes"] = hashes(g)
    return res


def write_sidecar(out, status, rep):
    rep = dict(rep)
    rep["status"] = status
    with open(out + ".json", "w") as f:
        json.dump(rep, f, indent=1, sort_keys=True, default=str)
