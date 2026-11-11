"""Visible-difference validator (sweep level, pure python + numpy):
  python3 tools/visdiff.py reports/sweep/<tag> [--min 0.02]
For every generator x pack in a sweep, compare the 64x64 thumbnails of all passed samples pairwise.
Metric: mean absolute RGB difference (0..1) over the OBJECT pixels only (union of the pixels that differ
from the flat world background in either image), so thin or small objects are not diluted by background.
A pair is tested only when its parameters differ MATERIALLY: some render-relevant parameter differs by
>= 10% of its schema range (numbers) or changes value (enums, booleans, strings, integers with range < 10).
A tested pair whose renders differ by less than the threshold is flagged (a real parameter change that
produced no visible change), unless the asset's bbox differs by > 5% on any axis (auto-framed thumbnails
cancel out pure size changes; size is visible in the world).
Render-relevant parameters: all, except those the schema marks `x-runtime` (act only in the runtime:
fx emitter behaviour, sky placement radius) or `x-lod` (tessellation only: sky rings/segments, terrain
resolution, round room-shell wall segments). Writes <tag>/visdiff.json; exit 0 if nothing is flagged,
else 3. Schema ranges/annotations come from reports/schema_dump.json (tools/schemadump.py)."""
import json
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

import numpy as np  # noqa: E402

from core import png  # noqa: E402

DEFAULT_MIN = 0.02
MATERIAL = 0.10
NO_SIZE_RULE = ("sky",)  # a sky is seen from its centre: its size is not visible


def img_diff(a, b, bg_tol=6.0 / 255.0):
    a = a.astype(np.float64)[:, :, :3] / 255.0
    b = b.astype(np.float64)[:, :, :3] / 255.0
    bg = a[0, 0]
    fg = (np.abs(a - bg).max(2) > bg_tol) | (np.abs(b - bg).max(2) > bg_tol)
    if not fg.any():
        return 0.0
    return float(np.abs(a - b).mean(2)[fg].mean())


def size_differs(a, b, rel=0.05):
    """True if two bbox sizes differ by more than rel on any axis."""
    if not a or not b:
        return False
    return any(abs(x - y) > rel * max(abs(x), abs(y), 1e-6) for x, y in zip(a, b))


def param_distance(pa, pb, schema):
    """max normalised difference over the params (0..1); schema = {name: {type, minimum, maximum, ...}}"""
    dmax = 0.0
    for k in set(pa) | set(pb):
        va, vb = pa.get(k), pb.get(k)
        if va == vb:
            continue
        s = (schema or {}).get(k, {})
        if s.get("type") == "number" or (s.get("type") == "integer" and s.get("maximum", 0) - s.get("minimum", 0) >= 10):
            rng = float(s.get("maximum", 1.0)) - float(s.get("minimum", 0.0))
            d = abs(float(va) - float(vb)) / rng if rng > 0 else 1.0
        else:
            d = 1.0
        dmax = max(dmax, d)
    return dmax


def flag_pairs(items, thr, stats=None, schema=None):
    """items: [(key, params (json str or dict), image[, bbox])] -> (min_diff over tested pairs, flagged)."""
    flagged, mn = [], None
    st = stats if stats is not None else {}
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            pa, pb = items[i][1], items[j][1]
            pa = json.loads(pa) if isinstance(pa, str) else pa
            pb = json.loads(pb) if isinstance(pb, str) else pb
            if pa == pb:
                continue
            if schema is not None and param_distance(pa, pb, schema) < MATERIAL:
                st["immaterial"] = st.get("immaterial", 0) + 1
                continue
            st["tested"] = st.get("tested", 0) + 1
            dv = img_diff(items[i][2], items[j][2])
            mn = dv if mn is None else min(mn, dv)
            if dv < thr:
                if len(items[i]) > 3 and size_differs(items[i][3], items[j][3]):
                    st["size_only"] = st.get("size_only", 0) + 1
                    continue
                flagged.append((items[i][0], items[j][0], round(dv, 5)))
    return mn, flagged


def main(argv):
    root = argv[0]
    thr = float(argv[argv.index("--min") + 1]) if "--min" in argv else DEFAULT_MIN
    sd = json.load(open(os.path.join(LANE, "reports", "schema_dump.json"), encoding='utf-8'))
    sd = sd.get("generators", sd)
    groups, classes = {}, {}
    for line in open(os.path.join(root, "samples.jsonl"), encoding='utf-8'):
        r = json.loads(line)
        if r.get("status") != "passed" or not r.get("thumb"):
            continue
        img = png.read(os.path.join(LANE, r["thumb"]))[:, :, :3]
        classes[r["gen"]] = r.get("class")
        props = (sd.get(r["gen"], {}).get("schema") or {}).get("properties", {})
        vis = {k: v for k, v in r["params"].items() if not (props.get(k, {}).get("x-runtime") or props.get(k, {}).get("x-lod"))}
        bbox = None if r.get("class") in NO_SIZE_RULE else r.get("bbox")
        groups.setdefault((r["gen"], r["pack"]), []).append(("%s#%d" % (r["pack"], r["i"]), vis, img, bbox))
    out = {"threshold": thr, "metric": "mean abs RGB diff over object pixels (union of non-background pixels)",
           "material_rule": "a pair is tested if some render-relevant param differs by >= %.0f%% of its range or changes "
                            "a discrete value" % (MATERIAL * 100),
           "size_rule": "pairs whose bbox differs > 5% on any axis count as visibly different",
           "excluded_params": {g: sorted(k for k, v in (e.get("schema") or {}).get("properties", {}).items()
                                         if v.get("x-runtime") or v.get("x-lod")) for g, e in sorted(sd.items())
                               if any(v.get("x-runtime") or v.get("x-lod") for v in (e.get("schema") or {}).get("properties", {}).values())},
           "size_rule_off_for_classes": list(NO_SIZE_RULE), "groups": {}}
    total_flag = 0
    for (gid, pk), items in sorted(groups.items()):
        st = {}
        schema = (sd.get(gid, {}).get("schema") or {})
        schema = schema.get("properties", schema)
        mn, fl = flag_pairs(items, thr, st, schema)
        out["groups"]["%s|%s" % (gid, pk)] = {"samples": len(items), "min_pair_diff": None if mn is None else round(mn, 5),
                                               "tested_pairs": st.get("tested", 0), "immaterial_pairs": st.get("immaterial", 0),
                                               "size_only_pairs": st.get("size_only", 0), "flagged": fl}
        total_flag += len(fl)
        print("VISDIFF %-22s %-15s n=%2d tested=%3d min=%s size_only=%d flagged=%d" % (
            gid, pk, len(items), st.get("tested", 0), "-" if mn is None else "%.4f" % mn, st.get("size_only", 0), len(fl)))
    out["flagged_total"] = total_flag
    out["exit_code"] = 3 if total_flag else 0
    with open(os.path.join(root, "visdiff.json"), "w", encoding='utf-8') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print("VISDIFF TOTAL groups=%d flagged=%d -> exit %d" % (len(groups), total_flag, out["exit_code"]))
    return out["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
