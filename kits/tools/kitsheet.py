"""Kit overview contact sheet per pack (run inside Blender):
  blender -b --factory-startup --python tools/kitsheet.py -- --packs polar_pod,forest_village --gens all \
      [--variants N] --out sheets/kits_<pack>.png
Builds each generator's default (pack default preset applied) plus N seeded variants, renders each
re-imported GLB at 160x120 and tiles them with labels."""
import argparse
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from core.sampling import sample_params  # noqa: E402
from tools import preview  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", default="polar_pod,forest_village")
    ap.add_argument("--gens", default="all")
    ap.add_argument("--variants", type=int, default=0)
    ap.add_argument("--presets", action="store_true")
    ap.add_argument("--tag", default="kits")
    ap.add_argument("--cols", type=int, default=6)
    a = ap.parse_args(argv)
    reg = pipeline.load_generators()
    gens = sorted(reg) if a.gens == "all" else a.gens.split(",")
    for pk in a.packs.split(","):
        pack = pipeline.get_pack(pk)
        tmp = os.path.join(LANE, "reports", "tmp", "sheet_" + pk)
        cells, labels = [], []
        for gid in gens:
            jobs = [(None, {}, 0, gid.split(".")[1])]
            if a.presets:
                for pname in sorted(pack.presets.get(gid, {})):
                    if pname != "default":
                        jobs.append((pname, {}, 0, pname))
            for v in range(a.variants):
                P, _ = sample_params(reg[gid], pack.palette_names, 99, v)
                jobs.append((None, P, 7 + v, "%s v%d" % (gid.split(".")[1], v)))
            for preset, params, seed, label in jobs:
                out = os.path.join(tmp, "%s_%s.glb" % (gid, label.replace(" ", "_")))
                st, rep = pipeline.build_one(gid, pk, preset, params, seed, out, tex_dir=os.path.join(tmp, "tex"), keep_failed=True)
                if not os.path.exists(out):
                    print("SHEET skip", gid, label, st, rep.get("error"))
                    continue
                png_path = out[:-4] + ".png"
                if reg[gid].cls == "sky":  # seen from its centre, as consumed
                    preview.thumb(out, pack, png_path, res=(160, 120), inside=True)
                else:
                    sc = preview.new_scene(pack, (160, 120), samples=4, fog="none")
                    objs = preview.import_glb(out, pack=pack, sc=sc)
                    preview.frame_objects(sc, objs, az=32, el=20, fov=34)
                    preview.render(sc, png_path)
                cells.append(preview.load_png(png_path))
                labels.append(("%s %s" % (label, "" if st == "passed" else st.upper())).strip())
        outp = os.path.join(LANE, "sheets", "%s_%s.png" % (a.tag, pk))
        preview.sheet(cells, a.cols, outp, cell_scale=2, labels=labels, title="%s  %s" % (a.tag, pk))
        print("SHEET", outp, len(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
