"""Rebuild selected library builds and/or derived pack tables inside Blender (repo layout):

  blender -b --factory-startup --disable-autoexec --python kits/tools/rebuild.py -- \
      --jobs JOBS.json --root kits/library --report OUT.json

JOBS.json: {"packs": ["polar_pod"], "builds": [{"id": "prop.vessel", "pack": "polar_pod", "preset": "mug"}]}
Every build goes through the same pipeline.build_one + validators as tools/manifest.py; failing builds are
reported (and deleted by the pipeline), never listed. The orchestrator (tools/kits_refresh.py) converts
outputs to explicit sRGB8 and updates kits/manifest.json + pack bindings with the measured hashes."""
import argparse
import json
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from tools.manifest import pack_tables  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    jobs = json.load(open(a.jobs))
    out = {"packs": {}, "builds": [], "kits": {}}
    reg = pipeline.load_generators()
    from core.packs import CORE_CLASSES
    for gid in sorted({j["id"] for j in jobs.get("builds", [])}):
        spec = reg[gid]
        out["kits"][gid] = {"id": gid, "version": spec.version, "class": spec.cls, "tri_limit": CORE_CLASSES[spec.cls],
                            "description": spec.description, "params_schema": spec.schema, "defaults": spec.defaults(),
                            "seed_default": 0, "wall_mounted": spec.wall_mounted, "origin_rule": spec.origin}
    for pk in jobs.get("packs", []):
        out["packs"][pk] = pack_tables(pipeline.get_pack(pk), root)
    for j in jobs.get("builds", []):
        gid, pk, preset = j["id"], j["pack"], j.get("preset")
        sub = "presets" if preset else "assets"
        name = ("%s__%s.glb" % (gid, preset)) if preset else ("%s.glb" % gid)
        path = os.path.join(root, pk, sub, name)
        st, rep = pipeline.build_one(gid, pk, preset, {}, 0, path, tex_dir=os.path.join(root, pk, "textures"))
        pipeline.write_sidecar(path, st, rep)
        row = {"id": gid, "pack": pk, "preset": preset, "status": st, "glb": os.path.relpath(path, root),
               "error": rep.get("error"), "params": rep.get("params"), "tri_count": rep.get("tri_count"),
               "tri_limit": rep.get("tri_limit"), "sha256": rep.get("sha256"), "hashes": rep.get("hashes"),
               "meta": rep.get("meta"), "validation": {k: v["ok"] for k, v in (rep.get("validation") or {}).items()},
               "fails": {k: v["reason"] for k, v in (rep.get("validation") or {}).items() if not v["ok"]},
               "textures": {}}
        for t, tw in sorted((rep.get("textures_written") or {}).items()):
            tpa = tw["path"] if isinstance(tw, dict) else str(tw)
            row["textures"][t] = {"file": os.path.relpath(tpa, root), "size": list(tw.get("size", [])) if isinstance(tw, dict) else None}
        out["builds"].append(row)
        print("REBUILD", st.upper(), gid, pk, preset, "tris=%s" % rep.get("tri_count"), rep.get("error") or "", row["fails"] or "")
    json.dump(out, open(a.report, "w"), indent=1, sort_keys=True, default=str)
    bad = [b for b in out["builds"] if b["status"] != "passed"]
    print("REBUILD TOTAL builds=%d failed=%d packs=%d" % (len(out["builds"]), len(bad), len(out["packs"])))
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
