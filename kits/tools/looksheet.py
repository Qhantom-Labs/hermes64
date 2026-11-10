"""Look-critique sheet: named pack presets rendered larger than the kit sheet (run inside Blender):
  blender -b --factory-startup --python tools/looksheet.py -- --pack polar_pod \
      --items furn.pod:default,furn.pod:chaise,vehicle.craft:default --tag look_r1 [--res 256x192] [--cols 4] [--az 32 --el 18]
Each item = generator[:preset] (preset 'default' = pack default layer). Builds through the normal
pipeline (validated; failures are labelled), re-imports the GLB and renders it with the preview
material recipes (emission-only, baked vertex light, matcap chrome). Writes sheets/<tag>_<pack>.png."""
import argparse
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from tools import preview  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="polar_pod")
    ap.add_argument("--items", required=True)
    ap.add_argument("--tag", default="look")
    ap.add_argument("--res", default="256x192")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--az", type=float, default=32.0)
    ap.add_argument("--el", type=float, default=18.0)
    ap.add_argument("--fog", default="none")
    a = ap.parse_args(argv)
    rw, rh = (int(x) for x in a.res.split("x"))
    pipeline.load_generators()
    pack = pipeline.get_pack(a.pack)
    tmp = os.path.join(LANE, "reports", "tmp", "look_" + a.tag + "_" + a.pack)
    cells, labels = [], []
    for item in a.items.split(","):
        gid, _, preset = item.partition(":")
        preset = preset or "default"
        label = "%s:%s" % (gid.split(".")[1], preset)
        out = os.path.join(tmp, "%s__%s.glb" % (gid, preset))
        st, rep = pipeline.build_one(gid, a.pack, None if preset == "default" else preset, {}, 0, out,
                                     tex_dir=os.path.join(tmp, "tex"), keep_failed=True)
        if not os.path.exists(out):
            print("LOOK skip", item, st, rep.get("error"))
            continue
        png_path = out[:-4] + ".png"
        sc = preview.new_scene(pack, (rw, rh), samples=8, fog=a.fog)
        objs = preview.import_glb(out, pack=pack, sc=sc)
        preview.frame_objects(sc, objs, az=a.az, el=a.el, fov=34, margin=1.08)
        preview.render(sc, png_path)
        cells.append(preview.load_png(png_path))
        tag = "" if st == "passed" else " " + st.upper()
        labels.append("%s %dt%s" % (label, rep.get("tri_count") or 0, tag))
        print("LOOK", item, st, rep.get("tri_count"))
    outp = os.path.join(LANE, "sheets", "%s_%s.png" % (a.tag, a.pack))
    preview.sheet(cells, a.cols, outp, cell_scale=a.scale, labels=labels, title="%s  %s" % (a.tag, a.pack))
    print("LOOKSHEET", outp, len(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
