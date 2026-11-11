"""Determinism findings from real artifacts (pure python):
  python3 tools/determinism.py --sweeps core30_c,core30_d [--rebuild-a kits --rebuild-b reports/determinism/runB]
1. cross-process: the same (generator, pack, sample) in two separate sweep runs -> compare GLB sha256 and
   geometry hash when the resolved params are identical (generators whose code changed between the runs
   have different params or geometry and are reported separately, not hidden);
2. cross-pack: inside one sweep, the same (generator, sample) params in both packs -> geometry_sha256 must
   match (packs change materials only);
3. rebuild: every GLB listed under two independent full builds (tools/manifest.py run twice into two
   roots) -> byte comparison.
Writes reports/determinism.json; exit 0 only if no unexplained mismatch."""
import argparse
import hashlib
import json
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(tag):
    out = {}
    for line in open(os.path.join(LANE, "reports", "sweep", tag, "samples.jsonl"), encoding='utf-8'):
        r = json.loads(line)
        out[(r["gen"], r["pack"], r["i"])] = r
    return out


def files_under(root):
    """GLBs that tools/manifest.py builds (kits/<pack>/assets, kits/<pack>/presets). Room pieces
    (kits/<pack>/rooms/, built by tools/room.py) are not part of the manifest rebuild and are excluded."""
    res = {}
    for dp, _, fns in os.walk(root):
        if os.path.basename(dp) not in ("assets", "presets"):
            continue
        for fn in fns:
            if fn.endswith(".glb"):
                p = os.path.join(dp, fn)
                res[os.path.relpath(p, root)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return res


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweeps", default="core30_c,core30_d")
    ap.add_argument("--rebuild-a", default=None)
    ap.add_argument("--rebuild-b", default=None)
    a = ap.parse_args(argv)
    rep = {}
    bad = 0
    ta, tb = a.sweeps.split(",")
    A, B = load(ta), load(tb)
    same_params = same_sha = same_geo = 0
    changed_params = {}
    mism = []
    for k, ra in A.items():
        rb = B.get(k)
        if rb is None or ra["status"] != "passed" or rb["status"] != "passed":
            continue
        if ra["params"] != rb["params"]:
            changed_params[k[0]] = changed_params.get(k[0], 0) + 1
            continue
        same_params += 1
        if ra["sha256"] == rb["sha256"]:
            same_sha += 1
        if ra["hashes"]["geometry_sha256"] == rb["hashes"]["geometry_sha256"]:
            same_geo += 1
        elif len(mism) < 40:
            mism.append(list(k))
    geo_diff = same_params - same_geo
    rep["cross_process"] = {"runs": [ta, tb], "samples_same_params": same_params, "identical_glb_sha256": same_sha,
                            "identical_geometry": same_geo, "geometry_mismatch": geo_diff, "mismatch_examples": mism,
                            "generators_with_changed_params_between_runs": changed_params,
                            "note": "a GLB-byte difference with identical geometry would come from exporter metadata; "
                                    "geometry differences between runs for unchanged code would be real non-determinism"}
    print("DETERMINISM cross-process %s vs %s: %d samples with identical params; GLB sha256 identical %d; geometry identical %d"
          % (ta, tb, same_params, same_sha, same_geo))
    print("DETERMINISM params changed between runs (code/rules edited in between):", json.dumps(changed_params, sort_keys=True))
    # cross-pack shape (shape_sha256: canonical welded triangles; geometry_sha256 also reported -- it hashes the
    # exported vertex arrays, whose split pattern follows pack-specific vertex colours / UV tiling)
    pairs = eq = geq = 0
    diff = []
    for (g, pk, i), r in B.items():
        if pk != "polar_pod" or r["status"] != "passed":
            continue
        o = B.get((g, "forest_village", i))
        if not o or o["status"] != "passed" or o["params"] != r["params"]:
            continue
        pairs += 1
        geq += o["hashes"]["geometry_sha256"] == r["hashes"]["geometry_sha256"]
        if o["hashes"].get("shape_sha256") and o["hashes"].get("shape_sha256") == r["hashes"].get("shape_sha256"):
            eq += 1
        elif len(diff) < 40:
            diff.append([g, i])
    rep["cross_pack"] = {"run": tb, "pairs_same_params": pairs, "identical_shape": eq, "identical_geometry_arrays": geq,
                         "shape_differences": diff}
    print("DETERMINISM cross-pack (%s): %d same-param pairs, identical shape %d, identical exported vertex arrays %d"
          % (tb, pairs, eq, geq))
    bad += (geo_diff > 0) + (eq != pairs)
    if a.rebuild_a and a.rebuild_b:
        fa = files_under(os.path.join(LANE, a.rebuild_a))
        fb = files_under(os.path.join(LANE, a.rebuild_b))
        common = sorted(set(fa) & set(fb))
        same = [p for p in common if fa[p] == fb[p]]
        differ = [p for p in common if fa[p] != fb[p]]
        rep["rebuild"] = {"a": a.rebuild_a, "b": a.rebuild_b, "files_a": len(fa), "files_b": len(fb), "common": len(common),
                          "byte_identical": len(same), "different": differ[:60], "only_a": sorted(set(fa) - set(fb))[:20],
                          "only_b": sorted(set(fb) - set(fa))[:20]}
        print("DETERMINISM rebuild %s vs %s: %d common GLBs, byte-identical %d, different %d" % (
            a.rebuild_a, a.rebuild_b, len(common), len(same), len(differ)))
        bad += bool(differ) + bool(set(fa) ^ set(fb))
    rep["exit_code"] = 3 if bad else 0
    json.dump(rep, open(os.path.join(LANE, "reports", "determinism.json"), "w", encoding='utf-8'), indent=1, sort_keys=True)
    print("DETERMINISM TOTAL -> exit %d" % rep["exit_code"])
    return rep["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
