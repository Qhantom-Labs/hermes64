"""Calibrate how each lane-kits texture generator USES its ramp (Blender python for numpy; lane-kits read-only).

For every (generator, ramp length) the material library uses, paint the texture with a synthetic ramp of
greys equally spaced in OKLab L and record the fractional ramp position of the texture's robust mean
(mean of the pixels between the 25th and 75th L percentile, the same statistic region measurement uses).
The drafter then places the measured surface colour at that position of the ramp instead of a hand guess,
so the rendered texture averages back to the measured colour.

  blender -b --factory-startup --python-exit-code 4 --python refpack/calibrate_gens.py -- OUT.json"""
import sys

sys.dont_write_bytecode = True
import json  # noqa: E402
import os  # noqa: E402

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)
import numpy as np  # noqa: E402

from refpack import config  # noqa: E402
from refpack import measure_np as M  # noqa: E402


def main(out):
    sys.path.insert(0, config.kits_dir())
    from core.palette import Palette
    from core.texgen import make_texture
    mats = json.load(open(config.library_path("materials.json"), encoding='utf-8'))
    jobs = {}
    for word, t in mats["materials"].items():
        if t["kind"] in ("chrome_env", "glass_env") or "ramp" not in t or "gen" not in t:
            continue
        jobs[(t["gen"], t["ramp"]["steps"])] = dict(t.get("extra", {}), size=t.get("size", 32))
    for role, ov in mats["role_gen_overrides"].items():
        if role.startswith("_"):
            continue
        for word, (gen, extra) in ov.items():
            steps = mats["materials"].get(word, {}).get("ramp", {}).get("steps", 4) if word != "*" else 4
            jobs.setdefault((gen, steps), dict(extra, size=32))
    res = {}
    for (gen, n), extra in sorted(jobs.items()):
        Ls = [0.25 + 0.6 * i / (n - 1) for i in range(n)] if n > 1 else [0.6]
        hexes = []
        for L in Ls:
            lin = M.oklab_to_lin(np.array([[L, 0.0, 0.0]]))[0]
            s = np.clip(M.lin_to_srgb(lin), 0, 1)
            hexes.append("#%02x%02x%02x" % tuple(int(round(v * 255)) for v in s))
        names = ["g%d" % i for i in range(n)]
        pal = Palette(hexes, names)
        recipe = dict(extra, gen=gen, ramp=names)
        try:
            img = make_texture(recipe, pal, "calib", gen)
        except Exception as e:  # generator needs params we do not have: report, never guess
            res["%s/%d" % (gen, n)] = {"error": "%s: %s" % (type(e).__name__, e)}
            continue
        lab = M.lin_to_oklab(M.srgb_to_lin(img[..., :3].astype(np.float64) / 255.0)).reshape(-1, 3)
        L = lab[:, 0]
        lo, hi = np.percentile(L, 25), np.percentile(L, 75)
        mL = float(L[(L >= lo) & (L <= hi)].mean())
        pos = (mL - Ls[0]) / (Ls[-1] - Ls[0]) * (n - 1) if n > 1 else 0.0
        res["%s/%d" % (gen, n)] = {"mean_pos": round(pos, 3), "steps": n}
    with open(out, "w", encoding='utf-8') as f:
        json.dump({"_note": "fractional ramp index of each generator's robust mean (0 = darkest step); "
                            "measured by refpack/calibrate_gens.py from lane-kits core/texgen.py", "gens": res},
                  f, indent=1, sort_keys=True)
        f.write("\n")
    print("CALIB", len(res))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:][0])
