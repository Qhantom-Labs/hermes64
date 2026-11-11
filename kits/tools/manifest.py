"""Build every generator default + every named pack preset for both packs and write the hashed manifest
(run inside Blender):
  blender -b --factory-startup --python tools/manifest.py -- [--out-root kits] [--no-manifest] [--tag NAME]
Writes kits/<pack>/assets/<id>.glb (+ .glb.json sidecar), kits/<pack>/presets/<id>__<preset>.glb,
kits/<pack>/{palette.json, lut16.png, materials.json}, and kits/manifest.json. Only builds that pass every
validator are listed (with that exact file's sha256); anything else goes to reports/manifest/<tag>.json
and makes the exit code 3. --out-root elsewhere + --no-manifest = a second independent build for the
determinism comparison."""
import argparse
import hashlib
import json
import os
import sys
import time

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

import bpy  # noqa: E402

from core import pipeline, png  # noqa: E402
from core.texgen import make_texture  # noqa: E402
from core.packs import CORE_CLASSES  # noqa: E402

CONTRACT_VERSION = "3.1.0"
CHAR_CLASSES = ("character", "animal")  # kept for contract compatibility; owned by lane-characters since 3.1.0


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def pack_tables(pack, root):
    d = os.path.join(root, pack.id)
    os.makedirs(d, exist_ok=True)
    names = list(pack.pal.names)
    pal = {"pack_id": pack.id, "version": pack.version, "colors": list(pack.d["palette"]), "names": names,
           "ramps": {k: [names.index(n) for n in v] for k, v in (pack.d.get("ramps") or {}).items()},
           "light_ramp": list(pack.light_ramp)}
    pj = os.path.join(d, "palette.json")
    json.dump(pal, open(pj, "w", encoding='utf-8'), indent=1, sort_keys=True)
    lut = os.path.join(d, "lut16.png")
    png.write(lut, pack.pal.lut16())
    mats = {}
    for role, m in sorted(pack.materials.items()):
        e = {"role": role, "pack": pack.id, "kind": m["kind"]}
        for k in ("tint", "env", "tile_m"):
            if k in m:
                e[k] = m[k]
        if "texture" in m:
            e["texture_gen"] = m["texture"].get("gen")
        mats["mat_%s_%s" % (pack.id, role)] = e
    mj = os.path.join(d, "materials.json")
    json.dump(mats, open(mj, "w", encoding='utf-8'), indent=1, sort_keys=True)
    envs = []
    for name in sorted(pack.env_maps):  # env maps for chrome_env / glass_env (runtime inputs, not embedded)
        ep = os.path.join(d, "env", name + ".png")
        os.makedirs(os.path.dirname(ep), exist_ok=True)
        with open(ep, "wb") as f:
            f.write(png.encode(make_texture(pack.env_maps[name], pack.pal, pack.id, name)))
        envs.append({"name": name, "file": os.path.relpath(ep, root), "sha256": sha(ep)})
    sp = os.path.join(root, "style-packs", pack.id + ".json")  # byte copy for the plugin's discovery path
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    open(sp, "wb").write(open(pack.path, "rb").read())
    return {"id": pack.id, "version": pack.version, "pack_json": os.path.relpath(pack.path, LANE), "sha256": sha(pack.path),
            "palette": os.path.relpath(pj, root), "palette_sha256": sha(pj), "lut": os.path.relpath(lut, root), "lut_sha256": sha(lut),
            "materials": os.path.relpath(mj, root), "materials_sha256": sha(mj),
            "style_pack_copy": os.path.relpath(sp, root), "style_pack_copy_sha256": sha(sp), "env_maps": envs,
            "notes": os.path.relpath(os.path.join(os.path.dirname(pack.path), "NOTES.md"), LANE)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.path.join(LANE, "kits"))
    ap.add_argument("--no-manifest", action="store_true")
    ap.add_argument("--tag", default="manifest")
    ap.add_argument("--packs", default="polar_pod,forest_village")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.out_root)
    reg = pipeline.load_generators()
    entries = {}
    problems = []
    packs = []
    t0 = time.time()
    for pk in a.packs.split(","):
        pack = pipeline.get_pack(pk)
        packs.append(pack_tables(pack, root))
        tex = os.path.join(root, pk, "textures")
        for gid in sorted(reg):
            spec = reg[gid]
            jobs = [(None, os.path.join(root, pk, "assets", "%s.glb" % gid))]
            for name in sorted(pack.presets.get(gid, {})):
                if name != "default":
                    jobs.append((name, os.path.join(root, pk, "presets", "%s__%s.glb" % (gid, name))))
            for preset, out in jobs:
                st, rep = pipeline.build_one(gid, pk, preset, {}, 0, out, tex_dir=tex)
                pipeline.write_sidecar(out, st, rep)
                if st != "passed":
                    problems.append({"id": gid, "pack": pk, "preset": preset, "status": st, "error": rep.get("error"),
                                     "fails": {k: v["reason"] for k, v in rep.get("validation", {}).items() if not v["ok"]}})
                    print("MANIFEST FAIL", gid, pk, preset, st)
                    continue
                e = entries.setdefault(gid, {
                    "id": gid, "version": spec.version, "class": spec.cls, "tri_limit": CORE_CLASSES[spec.cls],
                    "description": spec.description, "params_schema": spec.schema, "defaults": spec.defaults(),
                    "seed_default": 0, "wall_mounted": spec.wall_mounted, "origin_rule": spec.origin, "builds": []})
                texs = []
                for t, tw in sorted((rep.get("textures_written") or {}).items()):
                    # MaterialFactory.written = {name: {path, sha256, size}} (verify_manifest caught the
                    # first version stringifying this dict into "file")
                    tpa = tw["path"] if isinstance(tw, dict) else str(tw)
                    tpa = tpa if os.path.isabs(tpa) else os.path.join(tex, tpa)
                    texs.append({"name": t, "file": os.path.relpath(tpa, root), "sha256": sha(tpa),
                                 "size": list(tw.get("size", [])) if isinstance(tw, dict) else None})
                e["builds"].append({
                    "pack": pk, "preset": preset, "params": rep["params"], "seed": 0, "glb": os.path.relpath(out, root),
                    "sha256": rep["sha256"], "geometry_sha256": rep["hashes"]["geometry_sha256"],
                    "topology_sha256": rep["hashes"]["topology_sha256"], "uv_sha256": rep["hashes"]["uv_sha256"],
                    "shape_sha256": rep["hashes"].get("shape_sha256"),
                    "tri_count": rep["tri_count"], "tri_limit": rep["tri_limit"], "textures": texs,
                    "validation": {k: v["ok"] for k, v in rep["validation"].items()}, "meta": rep.get("meta")})
    builds = sum(len(e["builds"]) for e in entries.values())
    layouts = []
    for fn in sorted(os.listdir(os.path.join(LANE, "kits", "layouts"))):
        p = os.path.join(LANE, "kits", "layouts", fn)
        layouts.append({"id": fn[:-5], "file": os.path.relpath(p, os.path.join(LANE, "kits")), "sha256": sha(p)})
    rooms = []
    for pk in a.packs.split(","):
        rd = os.path.join(LANE, "kits", pk, "rooms")
        if os.path.isdir(rd):
            for fn in sorted(os.listdir(rd)):
                if fn.endswith(".json"):
                    p = os.path.join(rd, fn)
                    r = json.load(open(p, encoding='utf-8'))
                    rooms.append({"layout": r["layout_id"], "pack": pk, "file": os.path.relpath(p, os.path.join(LANE, "kits")),
                                  "sha256": sha(p), "room_tris": r["room_tris"], "pieces": len(r["pieces"])})
    report = {"tag": a.tag, "builds_passed": builds, "problems": problems, "seconds": round(time.time() - t0, 1),
              "out_root": root, "blender": bpy.app.version_string}
    os.makedirs(os.path.join(LANE, "reports", "manifest"), exist_ok=True)
    json.dump(report, open(os.path.join(LANE, "reports", "manifest", a.tag + ".json"), "w", encoding='utf-8'), indent=1, sort_keys=True)
    if not a.no_manifest:
        man = {"contract_version": CONTRACT_VERSION, "blender": bpy.app.version_string,
               "generated": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
               "note": "A file exists for consumers only if listed here with its sha256. Characters (people/animals) are "
                       "supplied by lane-characters and are not listed by this lane. Gate/sweep/control evidence: reports/.",
               "packs": packs, "classes": dict(CORE_CLASSES),
               "classes_owned_elsewhere": {c: "lane-characters" for c in CHAR_CLASSES},
               "skeletons": {}, "kits": [entries[k] for k in sorted(entries)],
               "layouts": layouts, "rooms": rooms}
        mp = os.path.join(root, "manifest.json")
        json.dump(man, open(mp, "w", encoding='utf-8'), indent=1, sort_keys=True)
        print("MANIFEST", mp, "kits", len(entries), "builds", builds, "sha256", sha(mp))
    print("MANIFEST TOTAL builds_passed=%d problems=%d -> exit %d" % (builds, len(problems), 3 if problems else 0))
    return 3 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
