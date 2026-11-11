"""Assemble a theme-agnostic layout in a pack and render it (run inside Blender):
  blender -b --factory-startup --python tools/room.py -- --layout lounge --packs polar_pod,forest_village \
      [--res 400x300] [--views main,top]
For each pack: builds the shell (layout params over the pack's room_shell default), fills the shell's
openings with the pack's door/window bindings (module takes the opening's shape and size), builds every
fixture slot from pack.json -> fixtures, writes kits/<pack>/rooms/<layout>/*.glb and
kits/<pack>/rooms/<layout>.json (files, sha256, transforms, resolved params, room tri total), and renders
the same camera(s) for every pack -> sheets/room_<layout>_<pack>_<view>.png + sheets/room_<layout>_dual.png.
Exit 0 only if every piece passed validation."""
import argparse
import hashlib
import json
import math
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402
from tools import preview  # noqa: E402

VIEWS = {  # Blender-space target / distance / azimuth / elevation / fov, shared by every pack. Cameras sit
    # INSIDE the room (Cycles renders back faces, so a dollhouse view through a wall is not possible).
    "main": {"target": (0.0, 0.1, 0.8), "dist": 3.25, "az": 0.0, "el": 24.0, "fov": 74.0},
    "corner": {"target": (0.5, 0.2, 0.8), "dist": 3.6, "az": -40.0, "el": 22.0, "fov": 70.0},
    "top": {"target": (0.0, 0.0, 0.0), "dist": 20.0, "az": 0.0, "el": 89.0, "fov": 30.0, "ortho": 8.4, "hide": ("kit_shell_ceiling",)},
}


def gltf_to_blender(p):
    return (p[0], -p[2], p[1])


def build_piece(gid, pack, preset, params, out, tex):
    st, rep = pipeline.build_one(gid, pack, None if preset in (None, "default") else preset, params, 0, out, tex_dir=tex)
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None
    return st, rep, sha


def assemble_room(layout, pk, root):
    pack = pipeline.get_pack(pk)
    d = os.path.join(root, pk, "rooms", layout["layout_id"])
    tex = os.path.join(root, pk, "textures")
    os.makedirs(d, exist_ok=True)
    pieces, problems = [], []
    sh = layout["shell"]
    out = os.path.join(d, "shell.glb")
    st, rep, sha = build_piece(sh["generator"], pk, None, sh["params"], out, tex)
    if st != "passed":
        problems.append("shell %s: %s %s" % (st, rep.get("error"), rep.get("validation")))
        return pieces, problems, None
    meta = rep["meta"]
    pieces.append({"slot": "shell", "generator": sh["generator"], "preset": "default", "params": rep["params"],
                   "glb": os.path.relpath(out, root), "sha256": sha, "tris": rep["tri_count"], "pos": [0.0, 0.0, 0.0], "rot_y_deg": 0.0})
    for slot, oi in sorted(layout.get("openings", {}).items(), key=lambda kv: kv[1]):
        b = pack.fixtures.get(slot)
        if b is None:
            problems.append("pack %s has no binding for opening slot %s" % (pk, slot))
            continue
        op = next(o for o in meta["openings"] if o["index"] == oi)
        params = dict(b.get("params", {}))
        if b["generator"] == "arch.window":
            params.update({"shape": op["shape"], "width": op["width"], "height": op["height"], "sill": op["sill"]})
        elif b["generator"] == "arch.door":
            dshape = {"rect": "rect", "arch": "arch", "round_top": "round_top", "gothic": "gothic", "oval": "oval", "round": "hatch"}
            params.update({"shape": dshape.get(op["shape"], "rect"), "width": op["width"], "height": op["height"]})
        out = os.path.join(d, "%s.glb" % slot)
        st, rep, sha = build_piece(b["generator"], pk, b.get("preset"), params, out, tex)
        if st != "passed":
            problems.append("%s: %s %s" % (slot, st, rep.get("error") or {k: v["reason"] for k, v in rep.get("validation", {}).items() if not v["ok"]}))
            continue
        pieces.append({"slot": slot, "generator": b["generator"], "preset": b.get("preset", "default"), "params": rep["params"],
                       "glb": os.path.relpath(out, root), "sha256": sha, "tris": rep["tri_count"], "pos": op["pos_gltf"],
                       "rot_y_deg": op["yaw_deg"], "opening": oi})
    for fx in layout["fixtures"]:
        b = pack.fixtures.get(fx["slot"])
        if b is None:
            problems.append("pack %s has no binding for slot %s" % (pk, fx["slot"]))
            continue
        params = dict(b.get("params", {}))
        params.update(fx.get("params", {}))
        out = os.path.join(d, "%s.glb" % fx["slot"])
        st, rep, sha = build_piece(b["generator"], pk, b.get("preset"), params, out, tex)
        if st != "passed":
            problems.append("%s: %s %s" % (fx["slot"], st, rep.get("error") or {k: v["reason"] for k, v in rep.get("validation", {}).items() if not v["ok"]}))
            continue
        pieces.append({"slot": fx["slot"], "generator": b["generator"], "preset": b.get("preset", "default"), "params": rep["params"],
                       "glb": os.path.relpath(out, root), "sha256": sha, "tris": rep["tri_count"], "pos": fx["pos"], "rot_y_deg": fx["rot_y_deg"]})
    room = {"layout_id": layout["layout_id"], "layout_version": layout["version"], "pack": pk, "pack_version": pack.version,
            "pieces": pieces, "room_tris": sum(p["tris"] for p in pieces), "problems": problems,
            "coordinates": "glTF: pos [x, y(up), z]; rot_y_deg about +Y; shell floor centre = origin"}
    with open(os.path.join(root, pk, "rooms", layout["layout_id"] + ".json"), "w", encoding='utf-8') as f:
        json.dump(room, f, indent=1, sort_keys=True)
    return pieces, problems, room


def render_room(pk, pieces, root, view, res, out_png):
    pack = pipeline.get_pack(pk)
    v = VIEWS[view]
    sc = preview.new_scene(pack, res, samples=8, fog="none" if v.get("ortho") else "interior")
    for p in pieces:
        objs = preview.import_glb(os.path.join(root, p["glb"]), loc=gltf_to_blender(p["pos"]), rot_z=math.radians(p["rot_y_deg"]),
                                  pack=pack, sc=sc)
        for o in objs:
            if any(o.name.startswith(h) for h in v.get("hide", ())):
                o.hide_render = True
    preview.camera(sc, v["target"], v["dist"], v["az"], v["el"], v["fov"], ortho=v.get("ortho"))
    return preview.render(sc, out_png)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default="lounge")
    ap.add_argument("--packs", default="polar_pod,forest_village")
    ap.add_argument("--res", default="400x300")
    ap.add_argument("--views", default="main,corner")
    a = ap.parse_args(argv)
    rw, rh = (int(x) for x in a.res.split("x"))
    root = os.path.join(LANE, "kits")
    layout = json.load(open(os.path.join(root, "layouts", a.layout + ".json"), encoding='utf-8'))
    pipeline.load_generators()
    cells, labels, bad = [], [], 0
    for view in a.views.split(","):
        for pk in a.packs.split(","):
            pieces, problems, room = assemble_room(layout, pk, root) if view == a.views.split(",")[0] else (None, None, None)
            if pieces is None:
                room = json.load(open(os.path.join(root, pk, "rooms", a.layout + ".json"), encoding='utf-8'))
                pieces, problems = room["pieces"], room["problems"]
            else:
                bad += len(problems)
                for pr in problems:
                    print("ROOM PROBLEM", pk, pr)
                print("ROOM", pk, a.layout, "pieces", len(pieces), "tris", room["room_tris"] if room else None)
            png_path = os.path.join(LANE, "sheets", "room_%s_%s_%s.png" % (a.layout, pk, view))
            render_room(pk, pieces, root, view, (rw, rh), png_path)
            cells.append(preview.load_png(png_path))
            labels.append("%s  %s  %s" % (a.layout, pk, view))
    dual = os.path.join(LANE, "sheets", "room_%s_dual.png" % a.layout)
    preview.sheet(cells, len(a.packs.split(",")), dual, cell_scale=2, labels=labels,
                  title="same layout '%s', same cameras, two packs (data only)" % a.layout)
    print("ROOMSHEET", dual, "problems", bad)
    return 0 if bad == 0 else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
