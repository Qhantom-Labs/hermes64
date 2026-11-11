"""Measure private style references into NUMBERS ONLY for the style bible (plan 07 section 2.3).

    python3 -B -m tools.style_ref_measure --group env=<folder> --group character=<folder> \
        --group brand=<folder> --out kits/core/style_ref_numbers.json

Study-only rule: the reference folders never enter the repo. This tool reads them with the existing
refpack measurement math (refpack/measure_np.py, refpack/decode.py) and writes aggregate image statistics
per group: no file names, no paths, no pixels, no thumbnails, no per-image rows. Files whose name starts with
`ours-` are our own renders kept beside the references and are skipped. A group fingerprint (sha256 over the
sorted per-file sha256 list) lets a later run show it measured the same inputs without naming them.

Needs Pillow for JPEG (refpack.decode says so and installs nothing). Run by a person or a Fable session that
has the private folders; tests only read the committed numbers file.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
if str(R) not in sys.path:
    sys.path.insert(0, str(R))

from refpack import measure_np as M  # noqa: E402
from refpack.decode import load_rgba  # noqa: E402

EXT = {".png", ".jpg", ".jpeg"}
FORMAT = "hermes64-style-ref-numbers/1"
ACCENT_CHROMA = M.ACCENT_CHROMA  # OKLab chroma that counts as an accent cluster (refpack constant)


def _q(values, q):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 4)


def _summary(values):
    return {"p10": _q(values, 0.1), "median": _q(values, 0.5), "p90": _q(values, 0.9)}


def measure_one(path):
    rgba, _ = load_rgba(str(path))
    res = M.measure([{"index": 0, "srgba": rgba, "weight": 1.0, "use_palette": True}])
    st = res["references"][0]["stats"]
    clusters = res["pooled"]["clusters"]
    accent = sum(c["coverage"] for c in clusters if c["chroma"] >= ACCENT_CHROMA)
    vert = st["vertical"]
    return {
        "L_mean": st["L_mean"], "L_p5": st["L"][0], "L_p95": st["L"][4],
        "contrast_p95_p5": round(st["L"][4] - st["L"][0], 4), "rms_contrast": st["rms_contrast"],
        "chroma_mean": st["chroma_mean"], "chroma_p90": st["chroma_p90"], "colourfulness": st["colourfulness"],
        "flat": st["texture"]["flat"], "edges": st["texture"]["edges"],
        "gradient_L_top_minus_bottom": vert["gradient_L"],
        "ground_darkening_mid_minus_bottom": round(vert["mid"][0] - vert["bottom"][0], 4),
        "accent_cluster_share": round(accent, 4), "clusters": len(clusters),
        "_hue_hist": st["hue_hist"],
    }


def measure_group(folder):
    files = sorted(p for p in Path(folder).iterdir()
                   if p.is_file() and p.suffix.lower() in EXT and not p.name.lower().startswith("ours-"))
    rows, failed, digests = [], 0, []
    for p in files:
        digests.append(hashlib.sha256(p.read_bytes()).hexdigest())
        try:
            rows.append(measure_one(p))
        except Exception:  # the reason may contain the file name: count only
            failed += 1
    out = {"images_measured": len(rows), "images_failed": failed,
           "fingerprint": hashlib.sha256("\n".join(sorted(digests)).encode()).hexdigest()}
    if rows:
        keys = [k for k in rows[0] if not k.startswith("_")]
        out["stats"] = {k: _summary([r[k] for r in rows]) for k in keys}
        hh = [sum(r["_hue_hist"][i] for r in rows) / len(rows) for i in range(12)]
        out["hue_hist_30deg_oklab"] = [round(x, 4) for x in hh]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--group", action="append", required=True, help="label=folder")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    groups = {}
    for g in a.group:
        label, _, folder = g.partition("=")
        if not label or not folder:
            ap.error("--group needs label=folder")
        groups[label] = measure_group(folder)
    doc = {"format": FORMAT,
           "rule": "aggregate image statistics only; no file names, paths, pixels or images from the private "
                   "study references (study only; never copy, trace, bake or name)",
           "method": "refpack/measure_np.py measure() per image (OKLab, analysis max side %d), then p10/median/p90 "
                     "per group; accent share = coverage of clusters with OKLab chroma >= %.2f"
                     % (M.ANALYSIS_MAX_SIDE, ACCENT_CHROMA),
           "groups": groups}
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding='utf-8')
    print("wrote %s: %s" % (a.out, {k: v["images_measured"] for k, v in groups.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
