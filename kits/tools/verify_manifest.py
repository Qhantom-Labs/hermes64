"""Verify kits/manifest.json against the files on disk (pure python):
  python3 tools/verify_manifest.py [kits]
Every listed GLB / texture / env map / pack table / layout / room (and each room piece) must exist with
the listed sha256; every build must have passed every validator; no unlisted GLB may sit in
kits/<pack>/assets or kits/<pack>/presets. Exit 0 if clean, else 3."""
import hashlib
import json
import os
import sys


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(argv):
    root = argv[0] if argv else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kits")
    m = json.load(open(os.path.join(root, "manifest.json"), encoding='utf-8'))
    problems, counts = [], {"glb": 0, "texture_refs": 0, "env": 0, "pack_files": 0, "rooms": 0, "room_pieces": 0, "layouts": 0}

    def check(path, want, kind):
        p = os.path.join(root, path)
        if not os.path.exists(p):
            problems.append("missing %s %s" % (kind, path))
        elif sha(p) != want:
            problems.append("sha256 mismatch %s %s" % (kind, path))

    for k in m["kits"]:
        for b in k["builds"]:
            counts["glb"] += 1
            check(b["glb"], b["sha256"], "glb")
            if not all(b["validation"].values()):
                problems.append("build not fully validated %s" % b["glb"])
            for t in b["textures"]:
                counts["texture_refs"] += 1
                check(t["file"], t["sha256"], "texture")
    for p in m["packs"]:
        for key in ("palette", "lut", "materials", "style_pack_copy"):
            counts["pack_files"] += 1
            check(p[key], p[key + "_sha256"], key)
        for e in p["env_maps"]:
            counts["env"] += 1
            check(e["file"], e["sha256"], "env")
    for r in m["layouts"]:
        counts["layouts"] += 1
        check(r["file"], r["sha256"], "layout")
    for r in m["rooms"]:
        counts["rooms"] += 1
        check(r["file"], r["sha256"], "room")
        for pc in json.load(open(os.path.join(root, r["file"]), encoding='utf-8'))["pieces"]:
            counts["room_pieces"] += 1
            check(pc["glb"], pc["sha256"], "room piece")
    listed = {b["glb"] for k in m["kits"] for b in k["builds"]}
    on_disk = set()
    for pk in [p["id"] for p in m["packs"]]:
        for sub in ("assets", "presets"):
            d = os.path.join(root, pk, sub)
            if os.path.isdir(d):
                on_disk |= {os.path.join(pk, sub, fn) for fn in os.listdir(d) if fn.endswith(".glb")}
    for extra in sorted(on_disk - listed):
        problems.append("unlisted GLB on disk %s" % extra)
    for pr in problems[:20]:
        print("VERIFY PROBLEM", pr)
    print("VERIFY counts", json.dumps(counts, sort_keys=True))
    print("VERIFY TOTAL problems=%d -> exit %d" % (len(problems), 3 if problems else 0))
    return 3 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
