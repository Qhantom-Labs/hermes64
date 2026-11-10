"""Hermes64 kit build CLI (run inside Blender 5.2.1):

  blender -b --factory-startup --python build.py -- --id furn.table --pack polar_pod \
      [--preset NAME] [--params JSON] [--seed N] --out OUT.glb [--tex-dir DIR]
  blender -b --factory-startup --python build.py -- --batch JOBS.json --out-dir DIR

Exit 0 = built and passed validators; 2 = rejected input (no file written); 3 = built but failed
validation (GLB deleted, OUT.glb.json explains); 4 = internal build error.
"""
import argparse
import json
import os
import sys

LANE = os.path.dirname(os.path.abspath(__file__))
if LANE not in sys.path:
    sys.path.insert(0, LANE)

try:
    from core import pipeline  # noqa: E402
except ImportError as exc:
    sys.exit("Configure python_path with Python 3.9+ and numpy; nothing was installed. " + str(exc))

CODES = {"passed": 0, "rejected": 2, "failed": 3, "error": 4}


def main(argv):
    ap = argparse.ArgumentParser(prog="build.py")
    ap.add_argument("--builder", choices=["python", "blender", "auto"], default="blender")
    ap.add_argument("--id")
    ap.add_argument("--pack")
    ap.add_argument("--preset", default=None)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out")
    ap.add_argument("--tex-dir", default=None)
    ap.add_argument("--batch", default=None)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if a.batch:
        jobs = json.load(open(a.batch))
        results = []
        worst = 0
        for j in jobs:
            out = os.path.join(a.out_dir, j["out"])
            st, rep = pipeline.build_one(j["id"], j["pack"], j.get("preset"), j.get("params", {}), j.get("seed", 0),
                                         out, tex_dir=a.tex_dir, builder=a.builder)
            if st != "rejected":
                pipeline.write_sidecar(out, st, rep)
            results.append({"out": j["out"], "status": st, "error": rep.get("error")})
            worst = max(worst, CODES[st])
        json.dump(results, open(os.path.join(a.out_dir, "batch_result.json"), "w"), indent=1)
        print("BATCH", json.dumps({s: sum(1 for r in results if r["status"] == s) for s in CODES}))
        return worst
    if not (a.id and a.pack and a.out):
        print("REJECTED: --id, --pack and --out are required")
        return 2
    try:
        params = json.loads(a.params)
    except Exception as e:
        print("REJECTED: --params is not JSON: %s" % e)
        return 2
    st, rep = pipeline.build_one(a.id, a.pack, a.preset, params, a.seed, os.path.abspath(a.out), tex_dir=a.tex_dir, builder=a.builder)
    if st == "rejected":
        print("REJECTED:", rep.get("error"))
        return 2
    pipeline.write_sidecar(os.path.abspath(a.out), st, rep)
    print("BUILD", st.upper(), a.id, a.pack, "tris=%s" % rep.get("tri_count"), "sha256=%s" % rep.get("sha256"))
    if st != "passed":
        for k, v in (rep.get("validation") or {}).items():
            if not v["ok"]:
                print("  FAIL", k, v["reason"])
        if rep.get("error"):
            print("  ERROR", rep["error"])
    return CODES[st]


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    code = main(argv)
    sys.stdout.flush()
    sys.exit(code)
