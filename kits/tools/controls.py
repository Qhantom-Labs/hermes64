"""Known-bad controls: every validator must reject a deliberately broken input (run inside Blender):
  blender -b --factory-startup --python tools/controls.py -- --tag NAME
Each control states the check that must reject it; it counts as PROVEN only if that check reports
ok=False (other checks may fail too and are listed). A positive control must pass every check.
Report: reports/controls/<tag>.json; exit 0 only if every control behaved as expected, else 3.
Scope note: the rig/deformation validator belongs to character assets (frozen in this lane; people and
animals are owned by lane-characters) and is not exercised here."""
import argparse
import json
import os
import shutil
import struct
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

import numpy as np  # noqa: E402

from core import pipeline, png  # noqa: E402
from core import meshkit as K  # noqa: E402
from core.asset import Asset, Node  # noqa: E402

from core.genutil import finalize  # noqa: E402
from core.packs import CORE_CLASSES  # noqa: E402
from tools import glbedit, visdiff  # noqa: E402

REG = pipeline.load_generators()
BUILDER = "blender"
REPORT_ROOT = os.path.join(LANE, "reports")


def tmpdir(tag):
    d = os.path.join(REPORT_ROOT, "tmp", "controls_" + tag)
    os.makedirs(d, exist_ok=True)
    return d


def export_asset(asset, pack, out, tex_dir, mutate=None):
    if BUILDER == "python":
        from core.pybuild import build
        build(asset, pack, out, tex_dir)
    else:
        from core import blendio
        from core.assemble import assemble
        blendio.reset()
        assemble(asset, pack, tex_dir)
        blendio.export_glb(out)
    if mutate:
        doc, binary = glbedit.read_glb(out)
        mutate(doc)
        glbedit.write_glb(out, doc, binary)
    return out


def validate(out, gid, pack, tri_limit=None):
    spec = REG[gid]
    lim = tri_limit or pack.tri_limit(spec.cls, CORE_CLASSES[spec.cls])
    res = pipeline.validate_file(out, spec, pack, lim)
    res.pop("_hashes", None)
    return res


def box_faces():
    return [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def box_verts(sx=0.3, sy=0.3, sz=0.3):
    return [(-sx, -sy, 0), (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0), (-sx, -sy, 2 * sz), (sx, -sy, 2 * sz), (sx, sy, 2 * sz), (-sx, sy, 2 * sz)]


def solid(verts, faces, role="body"):
    return K.Mesh().add(verts, faces, role, False)


def main(argv):
    global BUILDER, REPORT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="controls")
    ap.add_argument("--builder", choices=["python", "blender"], default="blender")
    ap.add_argument("--report-root", default=REPORT_ROOT)
    a = ap.parse_args(argv)
    BUILDER = a.builder
    REPORT_ROOT = os.path.abspath(a.report_root)
    original_build = pipeline.build_one
    def selected_build(*args, **kwargs):
        kwargs['builder'] = BUILDER
        return original_build(*args, **kwargs)
    pipeline.build_one = selected_build
    d = tmpdir(a.tag)
    tex = os.path.join(d, "tex")
    polar = pipeline.get_pack("polar_pod")
    village = pipeline.get_pack("forest_village")
    results = []

    def record(cid, check, desc, res=None, status=None, expect_fail=True, note=""):
        failed = sorted(k for k, v in (res or {}).items() if not v["ok"])
        if res is None:  # input-level control: status from build_one
            proven = (status == "rejected") if expect_fail else (status == "passed")
            reason = note
        else:
            proven = (check in failed) if expect_fail else not failed
            reason = res[check]["reason"] if check in res else ""
        results.append({"id": cid, "validator": check, "control": desc, "expected": "reject" if expect_fail else "pass",
                        "proven": bool(proven), "failed_checks": failed, "reason": reason, "status": status})
        print("CONTROL %-4s %-12s %-8s %s | %s" % (cid, check, "PROVEN" if proven else "NOT-PROVEN", desc, (reason or "")[:150]))

    # ---- positive control
    out = os.path.join(d, "good_table.glb")
    st, rep = pipeline.build_one("furn.table", "polar_pod", None, {}, 0, out, tex_dir=tex, keep_failed=True)
    record("G0", "all", "known-good furn.table default passes every check", rep.get("validation"), st, expect_fail=False)

    # ---- budget
    big = finalize([Node("blob", K.sphere(0, 0, 0, 0.3, 0.3, 0.3, 48, 24, "body"))])
    out = export_asset(big, polar, os.path.join(d, "over_tris.glb"), tex)
    record("B1", "budget", "2208-tri sphere validated as a prop (limit 150)", validate(out, "prop.key", polar))
    pj = json.load(open(polar.path))
    pj["materials"]["body"]["texture"]["size"] = 128
    bad_pack = os.path.join(d, "pack_bigtex.json")
    json.dump(pj, open(bad_pack, "w"))
    out = os.path.join(d, "big_texture.glb")
    st, rep = pipeline.build_one("furn.table", "polar_pod", None, {"top_role": "body", "base_role": "body"}, 0, out, tex_dir=os.path.join(d, "tex_big"),
                                 pack_path=bad_pack, keep_failed=True)
    record("B2", "budget", "128 px baked texture (limit 64 for baked_unlit)", rep.get("validation"), st)

    # ---- palette
    out = os.path.join(d, "good_table.glb")
    record("P1", "palette", "polar_pod-built asset checked against the forest_village palette/ramp", validate(out, "furn.table", village))
    js, binc = glbedit.read_glb(out)
    arr = png.decode(glbedit.view_bytes(js, binc, js["images"][0]["bufferView"]))
    bad = arr.copy()
    bad[0, 0, :3] = (255, 0, 255)
    nb = glbedit.replace_image(js, binc, 0, glbedit.png_rgba(bad))
    p2 = os.path.join(d, "off_palette_texel.glb")
    glbedit.write_glb(p2, js, nb)
    record("P2", "palette", "one off-palette texel (255,0,255) in an embedded texture", validate(p2, "furn.table", polar))
    js, binc = glbedit.read_glb(out)
    rgba = np.concatenate([arr[:, :, :3], np.full(arr.shape[:2] + (1,), 255, np.uint8)], 2)
    rgba[1, 1, 3] = 128
    nb = glbedit.replace_image(js, binc, 0, glbedit.png_rgba(rgba))
    p3 = os.path.join(d, "partial_alpha.glb")
    glbedit.write_glb(p3, js, nb)
    record("P3", "palette", "one texel with partial alpha (128)", validate(p3, "furn.table", polar))
    js, binc = glbedit.read_glb(out)
    glbedit.set_vertex_color(js, binc, (1.0, 0.0, 1.0))
    p4 = os.path.join(d, "off_ramp_vertex_colour.glb")
    glbedit.write_glb(p4, js, binc)
    record("P4", "palette", "one vertex colour (magenta) off the pack light ramp", validate(p4, "furn.table", polar))

    # ---- naming
    good_box = finalize([Node("box", K.box(0, 0, 0.3, 0.6, 0.6, 0.6, "body"))])
    bad_name = finalize([Node("Bad Name.001", K.box(0, 0, 0.3, 0.6, 0.6, 0.6, "body"))])
    out = export_asset(bad_name, polar, os.path.join(d, "bad_node_name.glb"), tex)
    record("N1", "naming", "node named 'kit_Bad Name.001'", validate(out, "furn.container", polar))

    def scale_it(doc):
        for node in doc['nodes']:
            node['scale'] = [2.0, 2.0, 2.0]
    out = export_asset(good_box, polar, os.path.join(d, "node_scale.glb"), tex, scale_it)
    record("N2", "naming", "node carries scale (2,2,2) instead of baked geometry", validate(out, "furn.container", polar))

    def rename_mat(doc):
        for mat in doc['materials']:
            mat['name'] = "Material.001"
    out = export_asset(good_box, polar, os.path.join(d, "bad_material_name.glb"), tex, rename_mat)
    record("N3", "naming", "material named 'Material.001'", validate(out, "furn.container", polar))

    # (ctl1 lesson: renaming the bpy image does not rename the exported image -- the exporter names it from
    # the file -- so the control edits the GLB JSON directly)
    out = export_asset(good_box, polar, os.path.join(d, "bad_image_src.glb"), tex)
    js, binc = glbedit.read_glb(out)
    js["images"][0]["name"] = "Image 1"
    n4 = os.path.join(d, "bad_image_name.glb")
    glbedit.write_glb(n4, js, binc)
    record("N4", "naming", "embedded image named 'Image 1'", validate(n4, "furn.container", polar))

    # ---- origin / scale
    off = Asset([Node("box", K.box(1.0, 0, 0.3, 0.6, 0.6, 0.6, "body"))])
    out = export_asset(off, polar, os.path.join(d, "off_centre.glb"), tex)
    record("O1", "origin_scale", "footprint centred 1 m off the origin", validate(out, "furn.container", polar))
    flo = Asset([Node("box", K.box(0, 0, 0.8, 0.6, 0.6, 0.6, "body"))])
    out = export_asset(flo, polar, os.path.join(d, "floating.glb"), tex)
    record("O2", "origin_scale", "asset floating 0.5 m above the floor (min Y 0.5)", validate(out, "furn.container", polar))
    long_prop = finalize([Node("rod", K.box(0, 0, 0.05, 3.0, 0.1, 0.1, "body"))])
    out = export_asset(long_prop, polar, os.path.join(d, "prop_too_long.glb"), tex)
    record("O3", "origin_scale", "3 m object declared as a prop (max extent 1.6 m)", validate(out, "prop.key", polar))

    # ---- topology
    v, f = box_verts(), box_faces()
    cases = [
        ("T1", "box with one face removed (hole in a closed solid)", solid(v, f[1:])),
        ("T2", "box + a fin triangle on an existing edge (non-manifold)", solid(v + [(0.0, -0.9, 0.3)], f + [(0, 1, 8)])),
        ("T3", "box with one face wound backwards", solid(v, f[:-1] + [tuple(reversed(f[-1]))])),
        ("T4", "box + zero-area triangle (three collinear vertices)", solid(v + [(0.5, 0.5, 0.1), (0.6, 0.5, 0.1), (0.7, 0.5, 0.1)],
                                                                          f + [(8, 9, 10)])),
    ]
    # (ctl1 lesson: a box with its top pushed below the bottom is only inside-out, not self-intersecting;
    # ctl2: a 180-degree twisted box only touches itself at one edge point.) A closed tube whose path
    # crosses itself (Z-shaped polyline, first and third legs cross at the same height) is one island
    # whose crossing faces share no vertices.
    zpath = [(-0.5, -0.3, 0.2), (0.5, 0.3, 0.2), (0.5, -0.3, 0.2), (-0.5, 0.3, 0.2)]
    cases.append(("T5", "closed tube whose path crosses itself (self-intersection)", K.tube(zpath, 0.08, 6, "body", smooth=False)))
    for cid, desc, mesh in cases:
        if cid == "T5" and BUILDER == "python":
            # This deliberately crossing tube also has crossing quad outlines;
            # author those faces as triangles so the intersection gate, rather
            # than polygon-input rejection, sees the known-bad surface.
            faces = [(f[0],f[i],f[i+1]) for f in mesh.f for i in range(1,len(f)-1)]
            mesh = K.Mesh().add(mesh.v,faces,"body",False)
        if cid == "T4" and BUILDER == "python":
            # The Python triangulator refuses zero-area polygons before export.
            # Corrupt an already exported triangle to exercise the *validator* too.
            out = export_asset(good_box, polar, os.path.join(d, "topo_T4.glb"), tex)
            doc, binary = glbedit.read_glb(out)
            primitive = doc['meshes'][0]['primitives'][0]
            ia = doc['accessors'][primitive['indices']]
            iv = doc['bufferViews'][ia['bufferView']]
            fmt = {5123:'H',5125:'I'}[ia['componentType']]
            ids = struct.unpack_from('<'+fmt*3,binary,iv.get('byteOffset',0)+ia.get('byteOffset',0))
            pa = doc['accessors'][primitive['attributes']['POSITION']]
            pv = doc['bufferViews'][pa['bufferView']]
            base = pv.get('byteOffset',0)+pa.get('byteOffset',0)
            stride = pv.get('byteStride',12)
            binary[base+ids[2]*stride:base+ids[2]*stride+12] = binary[base+ids[0]*stride:base+ids[0]*stride+12]
            glbedit.write_glb(out,doc,binary)
            record(cid,"topology",desc+" (post-export mutation; authoring path rejects earlier)",validate(out,"furn.container",polar))
            continue
        out = export_asset(finalize([Node("bad", mesh)]), polar, os.path.join(d, "topo_%s.glb" % cid), tex)
        record(cid, "topology", desc, validate(out, "furn.container", polar))
    card = K.card(1.0, 1.0, "view", facing="-y")
    card.v[0] = (card.v[0][0], card.v[0][1] + 0.05, card.v[0][2])
    out = export_asset(finalize([Node("box", K.box(0, 0, 0.3, 0.6, 0.6, 0.6, "body")), Node("view", card, "card")]), polar,
                       os.path.join(d, "card_not_planar.glb"), tex)
    record("T6", "topology", "view card with one corner bent 5 cm out of plane", validate(out, "furn.container", polar))

    # ---- visible difference
    t_a = os.path.join(d, "vd_a.png")
    t_b = os.path.join(d, "vd_b.png")
    t_c = os.path.join(d, "vd_c.png")
    def thumb(path, target):
        if BUILDER == "blender":
            from tools import preview
            preview.thumb(path, polar, target)
        else:
            sys.path.append(os.path.dirname(LANE))
            from adventure_maker.static_preview import frame, theme_for, software
            software(frame([{'glb':path}],target,theme_for(polar,os.path.join(d,'env'))))
    thumb(os.path.join(d, "good_table.glb"), t_a)
    shutil.copy(t_a, t_b)
    o2 = os.path.join(d, "table_round.glb")
    pipeline.build_one("furn.table", "polar_pod", "disc_orb", {}, 0, o2, tex_dir=tex, keep_failed=True)
    thumb(o2, t_c)
    imgs = [("a", '{"p": 1}', png.read(t_a)[:, :, :3]), ("b", '{"p": 2}', png.read(t_b)[:, :, :3])]
    mn, fl = visdiff.flag_pairs(imgs, visdiff.DEFAULT_MIN)
    results.append({"id": "V1", "validator": "visdiff", "control": "two different param sets rendering identically",
                    "expected": "reject", "proven": bool(fl), "failed_checks": ["visdiff"] if fl else [],
                    "reason": "min pair diff %.5f < %.3f" % (mn, visdiff.DEFAULT_MIN), "status": None})
    print("CONTROL V1   visdiff      %s identical renders for different params | diff %.5f" % ("PROVEN" if fl else "NOT-PROVEN", mn))
    imgs = [("a", '{"p": 1}', png.read(t_a)[:, :, :3]), ("c", '{"p": 3}', png.read(t_c)[:, :, :3])]
    mn, fl = visdiff.flag_pairs(imgs, visdiff.DEFAULT_MIN)
    results.append({"id": "V0", "validator": "visdiff", "control": "default vs disc_orb table (really different) is not flagged",
                    "expected": "pass", "proven": not fl, "failed_checks": [], "reason": "diff %.5f" % mn, "status": None})
    print("CONTROL V0   visdiff      %s different presets not flagged | diff %.5f" % ("PROVEN" if not fl else "NOT-PROVEN", mn))

    # ---- input schema / rules (fail-closed, no output file)
    inputs = [
        ("S1", "unknown param", "furn.table", "polar_pod", None, {"colour": "red"}, 0),
        ("S2", "out-of-range value", "furn.table", "polar_pod", None, {"height": 9.0}, 0),
        ("S3", "wrong type", "furn.table", "polar_pod", None, {"height": "tall"}, 0),
        ("S4", "bad enum", "furn.table", "polar_pod", None, {"legs": "seven"}, 0),
        ("S5", "violated cross-param rule (chaise narrower than 1.4 m)", "furn.pod", "polar_pod", None, {"kind": "chaise", "width": 1.0}, 0),
        ("S6", "unknown preset", "furn.table", "polar_pod", "no_such_preset", {}, 0),
        ("S7", "unknown pack", "furn.table", "no_such_pack", None, {}, 0),
        ("S8", "unknown generator id", "furn.sofa_xl", "polar_pod", None, {}, 0),
        ("S9", "negative seed", "furn.table", "polar_pod", None, {}, -1),
        ("S10", "detail that cannot fit the budget (pod rule)", "furn.pod", "polar_pod", None,
         {"kind": "bowl", "lobes": 5, "portholes": 4, "feet": 3}, 0),
    ]
    for cid, desc, gid, pk, pre, params, seed in inputs:
        out = os.path.join(d, "input_%s.glb" % cid)
        st, rep = pipeline.build_one(gid, pk, pre, params, seed, out, tex_dir=tex)
        record(cid, "input", desc, None, st, note=(rep.get("error") or "") + ("" if not os.path.exists(out) else " (FILE WRITTEN!)"))
        if os.path.exists(out):
            results[-1]["proven"] = False

    # ---- failed validation deletes the output (CLI exit 3 path)
    pj = json.load(open(polar.path))
    pj["validator_thresholds"]["tri_limits"] = {"furniture": 40}
    tight = os.path.join(d, "pack_tight.json")
    json.dump(pj, open(tight, "w"))
    out = os.path.join(d, "deleted_on_fail.glb")
    st, rep = pipeline.build_one("furn.table", "polar_pod", None, {}, 0, out, tex_dir=tex, pack_path=tight)
    ok = st == "failed" and not os.path.exists(out) and rep.get("deleted_failed_output")
    results.append({"id": "F1", "validator": "budget", "control": "pack lowers furniture budget to 40: build fails and the GLB is deleted",
                    "expected": "reject", "proven": bool(ok), "failed_checks": [k for k, v in rep.get("validation", {}).items() if not v["ok"]],
                    "reason": rep.get("validation", {}).get("budget", {}).get("reason", ""), "status": st})
    print("CONTROL F1   budget       %s failed build deletes its GLB | %s" % ("PROVEN" if ok else "NOT-PROVEN", st))

    n_ok = sum(1 for r in results if r["proven"])
    report = {"tag": a.tag, "controls": results, "proven": n_ok, "total": len(results),
              "scope_note": "rig/deformation validator applies to character assets only (frozen here; owned by lane-characters)",
              "exit_code": 0 if n_ok == len(results) else 3}
    rd = os.path.join(REPORT_ROOT, "controls")
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, a.tag + ".json"), "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print("CONTROLS TOTAL proven=%d/%d -> exit %d" % (n_ok, len(results), report["exit_code"]))
    pipeline.build_one = original_build
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
