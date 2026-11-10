"""Build refpack/library/kits.json from the shipped lane-kits packs (read-only) + kit_variants.json.

  blender -b --factory-startup --python-exit-code 4 --python refpack/build_library.py -- [--kits DIR] [--out FILE]

Every entry is resolved fail-closed by the lane-kits registry (exit 3 on any rejection). For each entry
the generator is RUN (pure geometry, no export) to measure triangle area per material role, so the
drafter knows which roles a chosen preset actually paints and how much (role usage map)."""
import sys

sys.dont_write_bytecode = True
import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from refpack import config  # noqa: E402

GEN_CLASS = {
    "arch.room_shell": "architecture", "arch.house": "architecture", "arch.roof": "architecture",
    "arch.column": "architecture", "arch.corridor": "architecture", "arch.stairs": "architecture",
    "arch.railing": "architecture", "arch.wall_module": "architecture", "arch.floor_module": "architecture",
    "arch.ceiling_module": "architecture", "arch.pier": "architecture", "arch.bridge": "architecture",
    "arch.door": "openings", "arch.window": "openings",
    "furn.pod": "seating", "furn.bench": "seating", "furn.chair": "seating",
    "furn.table": "furniture", "furn.bed": "furniture", "furn.shelf": "furniture", "furn.console": "furniture",
    "furn.container": "furniture", "furn.hearth": "furniture", "furn.lamp": "furniture", "furn.rug": "furniture",
    "soft.pillow": "furniture", "soft.blanket": "furniture",
    "prop.sign": "props", "prop.book": "props", "prop.key": "props", "prop.tool": "props", "prop.vessel": "props",
    "prop.device": "props", "vehicle.craft": "vehicles", "vehicle.boat": "vehicles",
    "nature.tree": "nature", "nature.bush": "nature", "nature.rock": "nature", "nature.grass_tuft": "nature",
    "terrain.patch": "nature", "terrain.water": "nature", "sky.backdrop": "nature", "fx.particles": "nature",
}


def tri_area(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return 0.5 * math.sqrt((uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2)


def role_areas(spec, P):
    asset = spec.build(P, 0)
    areas = {}
    for node in asset.nodes:
        m = node.mesh
        for fi, f in enumerate(m.f):
            a = 0.0
            for k in range(1, len(f) - 1):
                a += tri_area(m.v[f[0]], m.v[f[k]], m.v[f[k + 1]])
            areas[m.r[fi]] = areas.get(m.r[fi], 0.0) + a
    return {r: round(v, 4) for r, v in sorted(areas.items()) if v > 0}


def file_sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kits", default=None)
    ap.add_argument("--out", default=config.library_path("kits.json"))
    a = ap.parse_args(argv)
    kits = config.kits_dir(a.kits)
    sys.path.insert(0, kits)
    from core import pipeline  # noqa: E402
    from core import schema as S  # noqa: E402
    reg = pipeline.load_generators()
    tags = json.load(open(config.library_path("kit_tags.json")))
    variants = json.load(open(config.library_path("kit_variants.json")))["variants"]
    layout = json.load(open(os.path.join(kits, "kits", "layouts", "lounge.json")))
    shell_layer = layout["shell"]["params"]
    packs = ["polar_pod", "forest_village"]
    entries, problems = {}, []
    source_fixtures = {}
    sources = {}
    for pk in packs:
        pack = pipeline.get_pack(pk)
        sources[pk] = {"pack_json": "packs/%s/pack.json" % pk, "sha256": file_sha(pack.path)}
        for gid, presets in sorted(pack.presets.items()):
            for name in sorted(presets):
                eid = "%s:%s:%s" % (pk, gid, name)
                try:
                    P = pipeline.resolve(reg[gid], pack, None if name == "default" else name, {})
                except S.ParamError as e:
                    problems.append("%s: %s" % (eid, e))
                    continue
                Pa = P
                if gid == "arch.room_shell":
                    Pa = pipeline.resolve(reg[gid], pack, None if name == "default" else name, shell_layer)
                t = tags["entries"].get(eid)
                if t is None:
                    problems.append("%s: no tags in kit_tags.json" % eid)
                    t = tags["pack_defaults"][pk]
                entries[eid] = {"generator": gid, "class": GEN_CLASS[gid], "params": P, "tags": sorted(set(t)),
                                "source": pk, "preset": name, "is_default": name == "default",
                                "role_area": role_areas(reg[gid], Pa), "slots": []}
        source_fixtures[pk] = {}
        for slot, b in sorted(pack.fixtures.items()):
            eid = "%s:%s:%s" % (pk, b["generator"], b.get("preset", "default"))
            if b.get("params"):
                problems.append("%s fixture %s has params; library cannot copy it verbatim" % (pk, slot))
            source_fixtures[pk][slot] = eid
            if eid in entries:
                entries[eid]["slots"].append(slot)
    for v in variants:
        gid = v["generator"]
        spec = reg.get(gid)
        if spec is None:
            problems.append("%s: unknown generator" % v["id"])
            continue
        try:
            P = S.resolve(spec.schema, [("variant", v["params"])], None)
            if spec.rules:
                msg = spec.rules(P)
                if msg:
                    raise S.ParamError("rule: %s" % msg)
            Pa = S.resolve(spec.schema, [("variant", v["params"]), ("layout", shell_layer)], None) if gid == "arch.room_shell" else P
        except S.ParamError as e:
            problems.append("%s: %s" % (v["id"], e))
            continue
        entries[v["id"]] = {"generator": gid, "class": GEN_CLASS[gid], "params": P, "tags": sorted(set(v["tags"])),
                            "source": "variant", "preset": v["id"].split(":")[-1], "is_default": bool(v.get("default")),
                            "role_area": role_areas(spec, Pa), "slots": list(v.get("slots", []))}
    # slot candidates: source bindings + every preset of the generators used for that slot + variants for it
    slot_gens = {}
    for pk in packs:
        pack = pipeline.get_pack(pk)
        for slot, b in pack.fixtures.items():
            slot_gens.setdefault(slot, []).append(b["generator"])
    slots = {}
    for slot in sorted(slot_gens):
        gens = sorted(set(slot_gens[slot]))
        cands = [eid for eid, e in sorted(entries.items())
                 if (e["source"] != "variant" and e["generator"] in gens) or slot in e["slots"]]
        slots[slot] = {"generators": gens, "candidates": cands}
    defaults = {}
    for eid, e in sorted(entries.items()):
        if e["is_default"]:
            defaults.setdefault(e["generator"], []).append(eid)
    out = {"schema": "hermes64.refpack.kit_library", "version": "1.0.0", "contract": "KITS 3.1.0",
           "sources": sources, "variants_sha256": file_sha(config.library_path("kit_variants.json")),
           "tags_sha256": file_sha(config.library_path("kit_tags.json")),
           "layout_shell_params": shell_layer, "generator_class": GEN_CLASS,
           "entries": entries, "slots": slots, "defaults": defaults, "source_fixtures": source_fixtures}
    for p in problems:
        print("LIBRARY PROBLEM", p)
    if problems:
        print("LIBRARY FAILED problems=%d (nothing written)" % len(problems))
        return 3
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, sort_keys=True, indent=1)
        f.write("\n")
    print("LIBRARY OK entries=%d slots=%d defaults=%d -> %s sha256=%s" % (
        len(entries), len(slots), len(defaults), a.out, file_sha(a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
