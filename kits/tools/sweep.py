"""Parameter sweep (run inside Blender):
  blender -b --factory-startup --python tools/sweep.py -- --gens all|id,id --packs polar_pod,forest_village \
      --n 30 --tag NAME [--thumbs] [--keep-glb]
For each generator and pack: n seeded random param sets (schema-driven, rules respected), each built,
exported, re-read and validated. Optional thumbnails feed the visible-difference check.
Writes reports/sweep/<tag>/summary.json (+ per-sample JSON lines)."""
import argparse
import json
import os
import shutil
import sys
import time

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from core.sampling import sample_params  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", default="all")
    ap.add_argument("--packs", default="polar_pod,forest_village")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--builder", choices=["python", "blender", "auto"], default="blender")
    ap.add_argument("--tag", default="sweep")
    ap.add_argument("--report-root", default=os.path.join(LANE,"reports"))
    ap.add_argument("--thumbs", action="store_true")
    ap.add_argument("--keep-glb", action="store_true")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--fixed", default="", help="JSON params pinned for every sample (coverage sweeps of one kind)")
    a = ap.parse_args(argv)
    if a.thumbs and a.builder != "blender":
        ap.error("--thumbs uses Cycles and needs builder=blender / blender_path; Python GLB sweeps need no Blender")
    fixed = json.loads(a.fixed) if a.fixed else None
    reg = pipeline.load_generators()
    gens = sorted(reg) if a.gens == "all" else a.gens.split(",")
    gens = [g for g in gens if g not in a.exclude.split(",")]
    root = os.path.join(a.report_root, "sweep", a.tag)
    tmp = os.path.join(a.report_root, "tmp", "sweep_" + a.tag)
    if os.path.exists(os.path.join(root, "samples.jsonl")):
        # Preserve earlier (possibly failing) runs as evidence: never overwrite a tag.
        print("SWEEP REFUSED: tag %r already has results in %s; choose a new --tag" % (a.tag, root))
        return 2
    os.makedirs(root, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    lines = open(os.path.join(root, "samples.jsonl"), "w")
    summary = {"tag": a.tag, "n_per_generator_per_pack": a.n, "generators": {}, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
               "fixed_params": fixed}
    thumbs = {}
    if a.thumbs:
        from tools import preview
    for gid in gens:
        spec = reg[gid]
        for pk in a.packs.split(","):
            pack = pipeline.get_pack(pk)
            st = {"passed": 0, "failed": 0, "error": 0, "rejected": 0, "tris_max": 0, "tris_min": 10 ** 9, "failures": []}
            for i in range(a.n):
                P, attempts = sample_params(spec, pack.palette_names, 1234, i, fixed=fixed)
                seed = 1000 + i
                out = os.path.join(tmp, "%s__%s__%02d.glb" % (gid, pk, i))
                status, rep = pipeline.build_one(gid, pk, None, P, seed, out, tex_dir=os.path.join(tmp, "tex"), builder=a.builder, keep_failed=a.keep_glb)
                st[status] += 1
                tc = rep.get("tri_count")
                if tc is not None:
                    st["tris_max"] = max(st["tris_max"], tc)
                    st["tris_min"] = min(st["tris_min"], tc)
                fails = {k: v["reason"] for k, v in (rep.get("validation") or {}).items() if not v["ok"]}
                if status != "passed":
                    st["failures"].append({"i": i, "status": status, "params": P, "fails": fails,
                                           "error": rep.get("error"), "trace": (rep.get("traceback") or "")[-600:]})
                rec = {"gen": gid, "pack": pk, "i": i, "seed": seed, "status": status, "tris": tc, "params": P,
                       "fails": fails, "hashes": rep.get("hashes"), "sha256": rep.get("sha256"), "sec": rep.get("seconds"),
                       "bbox": (rep.get("meta") or {}).get("bbox_size_m"), "class": rep.get("class")}
                if a.thumbs and status == "passed":
                    tp = os.path.join(root, "thumbs", gid, "%s_%02d.png" % (pk, i))
                    preview.thumb(out, pack, tp, inside=(spec.cls == "sky"))
                    rec["thumb"] = os.path.relpath(tp, LANE)
                lines.write(json.dumps(rec, sort_keys=True) + "\n")
                lines.flush()
                if not a.keep_glb and os.path.exists(out):
                    os.remove(out)
                    if os.path.exists(out + ".json"):
                        os.remove(out + ".json")
            if st["tris_min"] == 10 ** 9:
                st["tris_min"] = None
            summary["generators"].setdefault(gid, {})[pk] = st
            print("SWEEP %-22s %-15s pass=%d fail=%d err=%d rej=%d tris=%s..%s" % (
                gid, pk, st["passed"], st["failed"], st["error"], st["rejected"], st["tris_min"], st["tris_max"]))
            sys.stdout.flush()
    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tot = {k: sum(st[k] for g in summary["generators"].values() for st in g.values())
           for k in ("passed", "failed", "error", "rejected")}
    summary["totals"] = tot
    bad = tot["failed"] + tot["error"] + tot["rejected"]
    summary["exit_code"] = 3 if bad else 0
    json.dump(summary, open(os.path.join(root, "summary.json"), "w"), indent=1, sort_keys=True)
    if not a.keep_glb:
        shutil.rmtree(tmp, ignore_errors=True)
    print("SWEEP TOTAL tag=%s samples=%d passed=%d failed=%d error=%d rejected=%d -> exit %d" % (
        a.tag, sum(tot.values()), tot["passed"], tot["failed"], tot["error"], tot["rejected"], summary["exit_code"]))
    sys.stdout.flush()
    # Any failing/erroring/rejected sample makes the sweep fail (exit 3); 0 only when every sample passed.
    return summary["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
