"""Pack data gate (run inside Blender):
  blender -b --factory-startup --python tools/packcheck.py -- --packs polar_pod,forest_village [--build] --tag NAME
Resolves every kit preset and every fixture binding of each pack against the generator registry
(fail-closed: unknown generator/preset/param, wrong type/range/enum, violated rule). With --build each
preset is also built, exported, re-read and validated like a sweep sample. Exit 0 only if everything
resolves (and, with --build, passes); 3 otherwise. Report: reports/packcheck/<tag>.json"""
import argparse
import json
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from core import schema as S  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", default="polar_pod,forest_village")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--tag", default="packcheck")
    a = ap.parse_args(argv)
    reg = pipeline.load_generators()
    report = {"tag": a.tag, "packs": {}}
    bad = 0
    for pk in a.packs.split(","):
        pack = pipeline.get_pack(pk)
        pr = {"presets": [], "fixtures": [], "unknown_generators": []}
        for gid, presets in sorted(pack.presets.items()):
            if gid not in reg:
                pr["unknown_generators"].append(gid)
                bad += 1
                print("PACKCHECK %s unknown generator %s" % (pk, gid))
                continue
            for name in sorted(presets):
                rec = {"id": gid, "preset": name}
                try:
                    P = pipeline.resolve(reg[gid], pack, None if name == "default" else name, {})
                    rec["resolved"] = "ok"
                except S.ParamError as e:
                    rec["resolved"] = "rejected: %s" % e
                    bad += 1
                    print("PACKCHECK %s %s/%s REJECTED %s" % (pk, gid, name, e))
                    pr["presets"].append(rec)
                    continue
                if a.build:
                    out = os.path.join(LANE, "reports", "tmp", "packcheck_" + a.tag, pk, "%s__%s.glb" % (gid, name))
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    st, rep = pipeline.build_one(gid, pk, None if name == "default" else name, {}, 0, out,
                                                 tex_dir=os.path.join(os.path.dirname(out), "tex"))
                    rec["status"] = st
                    rec["tri_count"] = rep.get("tri_count")
                    rec["fails"] = {k: v["reason"] for k, v in rep.get("validation", {}).items() if not v["ok"]}
                    if st != "passed":
                        bad += 1
                        print("PACKCHECK %s %s/%s %s %s %s" % (pk, gid, name, st, rec["fails"], rep.get("error")))
                pr["presets"].append(rec)
        for slot, b in sorted(pack.fixtures.items()):
            rec = {"slot": slot, "generator": b["generator"], "preset": b.get("preset", "default")}
            gid = b["generator"]
            if gid not in reg:
                rec["resolved"] = "unknown generator"
                bad += 1
            else:
                pre = b.get("preset", "default")
                try:
                    pipeline.resolve(reg[gid], pack, None if pre == "default" else pre, b.get("params", {}))
                    rec["resolved"] = "ok"
                except S.ParamError as e:
                    rec["resolved"] = "rejected: %s" % e
                    bad += 1
            if rec["resolved"] != "ok":
                print("PACKCHECK %s fixture %s -> %s" % (pk, slot, rec["resolved"]))
            pr["fixtures"].append(rec)
        n_ok = sum(1 for r in pr["presets"] if r["resolved"] == "ok" and r.get("status", "passed") == "passed")
        print("PACKCHECK %s presets %d/%d ok, fixtures %d/%d ok" % (
            pk, n_ok, len(pr["presets"]), sum(1 for r in pr["fixtures"] if r["resolved"] == "ok"), len(pr["fixtures"])))
        report["packs"][pk] = pr
    report["problems"] = bad
    report["exit_code"] = 3 if bad else 0
    d = os.path.join(LANE, "reports", "packcheck")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, a.tag + ".json"), "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print("PACKCHECK TOTAL problems=%d -> exit %d" % (bad, report["exit_code"]))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
