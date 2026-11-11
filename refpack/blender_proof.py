"""Blender entry point: validate a draft pack with the lane-kits validators, build + render the proof room,
measure the proof renders and compose the proof sheet.

  blender -b --factory-startup --python-exit-code 4 --python refpack/blender_proof.py -- JOB.json

All outputs go under JOB.pack_dir/proof/ (GLBs, textures, env maps, renders, sheet) and JOB.out (report).
lane-kits is imported read-only: sys.dont_write_bytecode is set first, and tools/preview.env_image (which
writes into lane-kits/kits/<pack>/env/) is replaced in-process by a writer that targets the pack dir."""
import sys

sys.dont_write_bytecode = True
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

from refpack import measure_np as M  # noqa: E402

LAYOUT_SLOTS_KEY = "fixtures"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def setup_kits(kits_dir, env_dir):
    sys.path.insert(0, kits_dir)
    from core import pipeline, packs, schema, png  # noqa: F401
    from core.texgen import make_texture
    from tools import preview
    import bpy

    def env_image(pack, name):  # same bytes as lane-kits preview.env_image, written into the pack dir
        os.makedirs(env_dir, exist_ok=True)
        p = os.path.join(env_dir, name + ".png")
        arr = make_texture(pack.env_maps[name], pack.pal, pack.id, name)
        data = png.encode(arr)
        if not (os.path.exists(p) and open(p, "rb").read() == data):
            with open(p, "wb") as f:
                f.write(data)
        key = "envprev_" + pack.id + "_" + name
        if key in bpy.data.images:
            return bpy.data.images[key]
        im = bpy.data.images.load(p)
        im.name = key
        return im

    preview.env_image = env_image
    return pipeline, packs, schema, png, preview


def validate_data(pipeline, packs_mod, schema, pack_json):
    rep = {"pack_validator": {"ok": False, "errors": []}, "registry": {"ok": False, "problems": [], "presets": 0, "fixtures": 0}}
    with open(pack_json, "r", encoding="utf-8") as f:
        d = json.load(f)
    errs = packs_mod.validate_pack_dict(d)
    rep["pack_validator"] = {"ok": not errs, "errors": errs, "validator": "lane-kits core/packs.py validate_pack_dict"}
    if errs:
        return rep, None
    pack = pipeline.get_pack(d["id"], pack_json)
    reg = pipeline.load_generators()
    probs, n_p, n_f = [], 0, 0
    for gid, presets in sorted(pack.presets.items()):
        if gid not in reg:
            probs.append("unknown generator %s" % gid)
            continue
        for name in sorted(presets):
            n_p += 1
            try:
                pipeline.resolve(reg[gid], pack, None if name == "default" else name, {})
            except schema.ParamError as e:
                probs.append("%s/%s: %s" % (gid, name, e))
    for slot, b in sorted(pack.fixtures.items()):
        n_f += 1
        gid = b["generator"]
        if gid not in reg:
            probs.append("fixture %s: unknown generator %s" % (slot, gid))
            continue
        pre = b.get("preset", "default")
        try:
            pipeline.resolve(reg[gid], pack, None if pre == "default" else pre, b.get("params", {}))
        except schema.ParamError as e:
            probs.append("fixture %s: %s" % (slot, e))
    rep["registry"] = {"ok": not probs, "problems": probs, "presets": n_p, "fixtures": n_f,
                       "checker": "re-implementation of lane-kits tools/packcheck.py resolution (packcheck loads only lane-kits packs)"}
    return rep, pack


def assemble_room(pipeline, layout, pack, pack_json, out_dir, tex_dir, builder="blender"):
    os.makedirs(out_dir, exist_ok=True)
    pieces, problems, checks = [], [], {}

    def build(gid, preset, params, out):
        st, rep = pipeline.build_one(gid, pack.id, None if preset in (None, "default") else preset, params, 0, out,
                                     tex_dir=tex_dir, pack_path=pack_json, builder=builder)
        for k, v in (rep.get("validation") or {}).items():
            c = checks.setdefault(k, {"pass": 0, "fail": 0})
            c["pass" if v["ok"] else "fail"] += 1
        return st, rep

    sh = layout["shell"]
    out = os.path.join(out_dir, "shell.glb")
    st, rep = build(sh["generator"], None, sh["params"], out)
    if st != "passed":
        problems.append("shell %s: %s %s" % (st, rep.get("error"), {k: v["reason"] for k, v in (rep.get("validation") or {}).items() if not v["ok"]}))
        return pieces, problems, checks
    meta = rep["meta"]
    pieces.append({"slot": "shell", "generator": sh["generator"], "preset": "default", "glb": out, "tris": rep["tri_count"],
                   "pos": [0.0, 0.0, 0.0], "rot_y_deg": 0.0, "sha256": sha(out)})
    for slot, oi in sorted(layout.get("openings", {}).items(), key=lambda kv: kv[1]):
        b = pack.fixtures.get(slot)
        if b is None:
            problems.append("no binding for opening slot %s" % slot)
            continue
        op = next(o for o in meta["openings"] if o["index"] == oi)
        params = dict(b.get("params", {}))
        if b["generator"] == "arch.window":
            params.update({"shape": op["shape"], "width": op["width"], "height": op["height"], "sill": op["sill"]})
        elif b["generator"] == "arch.door":
            dshape = {"rect": "rect", "arch": "arch", "round_top": "round_top", "gothic": "gothic", "oval": "oval", "round": "hatch"}
            params.update({"shape": dshape.get(op["shape"], "rect"), "width": op["width"], "height": op["height"]})
        out = os.path.join(out_dir, "%s.glb" % slot)
        st, rep = build(b["generator"], b.get("preset"), params, out)
        if st != "passed":
            problems.append("%s: %s %s" % (slot, st, rep.get("error") or {k: v["reason"] for k, v in (rep.get("validation") or {}).items() if not v["ok"]}))
            continue
        pieces.append({"slot": slot, "generator": b["generator"], "preset": b.get("preset"), "glb": out, "tris": rep["tri_count"],
                       "pos": op["pos_gltf"], "rot_y_deg": op["yaw_deg"], "sha256": sha(out)})
    for fx in layout["fixtures"]:
        b = pack.fixtures.get(fx["slot"])
        if b is None:
            problems.append("no binding for slot %s" % fx["slot"])
            continue
        params = dict(b.get("params", {}))
        params.update(fx.get("params", {}))
        out = os.path.join(out_dir, "%s.glb" % fx["slot"])
        st, rep = build(b["generator"], b.get("preset"), params, out)
        if st != "passed":
            problems.append("%s: %s %s" % (fx["slot"], st, rep.get("error") or {k: v["reason"] for k, v in (rep.get("validation") or {}).items() if not v["ok"]}))
            continue
        pieces.append({"slot": fx["slot"], "generator": b["generator"], "preset": b.get("preset"), "glb": out, "tris": rep["tri_count"],
                       "pos": fx["pos"], "rot_y_deg": fx["rot_y_deg"], "sha256": sha(out)})
    return pieces, problems, checks


def render_views(preview, room_mod, pack, pieces, views, res, out_dir, samples=8, png_mod=None):
    """Render the layout views. With png_mod (lane-kits core/png), each render is re-encoded from its pixels:
    Blender stamps Date and cycles render_time text chunks into PNGs, which made identical renders differ
    byte-wise between runs (eval/determinism finding); the re-encode keeps the pixels and drops the metadata."""
    paths = {}
    for view in views:
        v = room_mod.VIEWS[view]
        sc = preview.new_scene(pack, res, samples=samples, fog="none" if v.get("ortho") else "interior")
        for p in pieces:
            objs = preview.import_glb(p["glb"], loc=room_mod.gltf_to_blender(p["pos"]), rot_z=math.radians(p["rot_y_deg"]), pack=pack, sc=sc)
            for o in objs:
                if any(o.name.startswith(h) for h in v.get("hide", ())):
                    o.hide_render = True
        preview.camera(sc, v["target"], v["dist"], v["az"], v["el"], v["fov"], ortho=v.get("ortho"))
        out = os.path.join(out_dir, "room_%s.png" % view)
        preview.render(sc, out)
        if png_mod is not None:
            png_mod.write(out, png_mod.read(out))
        paths[view] = out
    return paths


def load_ref_rgba(path):
    import bpy
    im = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = im.size
        a = np.empty(w * h * im.channels, dtype=np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(h, w, im.channels)[::-1].astype(np.float64)
        if im.channels == 3:
            a = np.concatenate([a, np.ones((h, w, 1))], 2)
        if im.is_float:
            a[..., :3] = M.lin_to_srgb(a[..., :3])
        return np.clip(a, 0, 1)
    finally:
        bpy.data.images.remove(im)


def thumb(rgba, box_w, box_h):
    lin = M.srgb_to_lin(rgba[..., :3])
    h, w = lin.shape[:2]
    s = min(box_w / w, box_h / h)
    ms = max(int(round(w * s)), int(round(h * s)))
    lin_s, _ = M.area_downscale(lin, np.ones((h, w)), max_side=max(1, ms))
    return np.round(M.lin_to_srgb(lin_s) * 255).astype(np.uint8)


def measure_png(png_mod, path):
    a = png_mod.read(path)[..., :3].astype(np.float64) / 255.0
    rgba = np.concatenate([a, np.ones(a.shape[:2] + (1,))], 2)
    return rgba


def compose_sheet(png_mod, pixfont, refs_rgba, renders, pack_d, out, title, ref_labels):
    W = 1220
    pad = 8
    rows = []
    bg = np.array([14, 16, 22], dtype=np.uint8)
    fg = (235, 235, 240)

    def canvas(h):
        c = np.zeros((h, W, 3), dtype=np.uint8)
        c[:, :] = bg
        return c

    top = canvas(26)
    pixfont.draw_text(top, title, pad, 6, (255, 214, 120), scale=3)
    rows.append(top)
    if refs_rgba:
        n = len(refs_rgba)
        cols = min(4, n)
        bw = (W - pad * (cols + 1)) // cols
        bh = int(bw * 0.62)
        thumbs = [thumb(rgba, bw, bh) for rgba in refs_rgba]
        nrow = (n + cols - 1) // cols
        row_h = [max(t.shape[0] for t in thumbs[r * cols:(r + 1) * cols]) for r in range(nrow)]
        c = canvas(sum(h + pad + 12 for h in row_h) + 18)
        pixfont.draw_text(c, "REFERENCES (PRIVATE STUDY, DOWNSCALED, REVIEW ONLY)", pad, 4, fg, scale=2)
        y = 18
        for r in range(nrow):
            for cc in range(cols):
                k = r * cols + cc
                if k >= n:
                    break
                t = thumbs[k]
                x = pad + cc * (bw + pad)
                c[y:y + t.shape[0], x:x + t.shape[1]] = t
                pixfont.draw_text(c, ref_labels[k][:40], x, y + row_h[r] + 2, fg, scale=1)
            y += row_h[r] + pad + 12
        rows.append(c)
    if renders:
        imgs = [png_mod.read(p)[..., :3] for p in renders]
        k = max(1, min(2, len(imgs)))
        cw = (W - pad * (k + 1)) // k
        scale = max(1, cw // imgs[0].shape[1])
        ups = [np.repeat(np.repeat(im, scale, 0), scale, 1) for im in imgs]
        hh = max(u.shape[0] for u in ups)
        c = canvas(hh + pad + 18)
        pixfont.draw_text(c, "PROOF RENDERS: SEE VALIDATION.JSON FOR RENDERER AND FIDELITY", pad, 4, fg, scale=2)
        for i, u in enumerate(ups[:k]):
            x = pad + i * (cw + pad)
            c[18:18 + u.shape[0], x:x + min(cw, u.shape[1])] = u[:, :min(cw, u.shape[1])]
        rows.append(c)
    names, cols_hex = pack_d["palette_names"], pack_d["palette"]
    sw = (W - pad * 2) // 16
    c = canvas(2 * (sw + 14) + 44)
    pixfont.draw_text(c, "PALETTE (%d)  LIGHT RAMP  FOG EXT / INT" % len(cols_hex), pad, 4, fg, scale=2)
    for i, (n, h) in enumerate(zip(names, cols_hex)):
        r, cc = divmod(i, 16)
        y = 18 + r * (sw + 14)
        x = pad + cc * sw
        rgb = [int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
        c[y:y + sw - 4, x:x + sw - 4] = rgb
        pixfont.draw_text(c, n[:9], x, y + sw - 2, fg, scale=1)
    y = 18 + 2 * (sw + 14)
    lr = pack_d["light_ramp"]
    lw = (W // 2 - pad) // max(1, len(lr))
    for i, n in enumerate(lr):
        h = cols_hex[names.index(n)]
        c[y:y + 20, pad + i * lw:pad + (i + 1) * lw] = [int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
    for j, key in enumerate(("color",)):
        for k2, h in enumerate((cols_hex[names.index(pack_d["fog"]["color"])], cols_hex[names.index(pack_d["fog"]["interior"]["color"])])):
            x = W // 2 + 40 + k2 * 120
            c[y:y + 20, x:x + 100] = [int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
    rows.append(c)
    foot = canvas(20)
    pixfont.draw_text(foot, "STATUS: DRAFT - NOT APPROVED. APPROVAL IS A HUMAN DECISION OUTSIDE THIS TOOL.", pad, 6, (255, 150, 120), scale=2)
    rows.append(foot)
    sheet = np.concatenate(rows, 0)
    png_mod.write(out, sheet)
    return out


def style_match(ref_meas, proof_meas):
    """Coverage-weighted nearest-cluster distance between reference and proof palettes (OKLab x100 and CIEDE2000)."""
    from refpack import colour as Cm
    rc = ref_meas["pooled"]["clusters"]
    pc = proof_meas["pooled"]["clusters"]

    def one_way(A, B):
        tot = sum(a["coverage"] for a in A) or 1.0
        s_ok = s_de = 0.0
        for a in A:
            d_ok = min(Cm.ok_dist(a["lab"], b["lab"]) for b in B)
            d_de = min(Cm.de2000_hex(a["hex"], b["hex"]) for b in B)
            s_ok += a["coverage"] * d_ok
            s_de += a["coverage"] * d_de
        return s_ok / tot, s_de / tot

    a1, d1 = one_way(rc, pc)
    a2, d2 = one_way(pc, rc)

    def agg(meas, key):
        vals = [r["stats"][key] for r in meas["references"]]
        return sum(vals) / len(vals)

    def aggL(meas):
        return sum(r["stats"]["L"][2] for r in meas["references"]) / len(meas["references"])

    return {"ref_to_proof_de2000": round(d1, 3), "proof_to_ref_de2000": round(d2, 3),
            "symmetric_de2000": round(0.5 * (d1 + d2), 3), "symmetric_oklab": round(0.5 * (a1 + a2), 4),
            "median_L": {"refs": round(aggL(ref_meas), 4), "proof": round(aggL(proof_meas), 4)},
            "chroma_mean": {"refs": round(agg(ref_meas, "chroma_mean"), 4), "proof": round(agg(proof_meas, "chroma_mean"), 4)},
            "rms_contrast": {"refs": round(agg(ref_meas, "rms_contrast"), 4), "proof": round(agg(proof_meas, "rms_contrast"), 4)}}


def main(job_path):
    t0 = time.time()
    job = json.load(open(job_path, "r", encoding="utf-8"))
    pdir = job["pack_dir"]
    proof = os.path.join(pdir, "proof")
    os.makedirs(proof, exist_ok=True)
    report = {"ok": False, "stage": "setup"}
    try:
        pipeline, packs_mod, schema, png_mod, preview = setup_kits(job["kits_dir"], os.path.join(proof, "env"))
        from tools import room as room_mod
        from tools import pixfont
        report["stage"] = "validate"
        vrep, pack = validate_data(pipeline, packs_mod, schema, job["pack_json"])
        report.update(vrep)
        if pack is None or not vrep["registry"]["ok"]:
            report["ok"] = False
            return report
        report["stage"] = "build"
        layout = json.load(open(os.path.join(job["kits_dir"], "kits", "layouts", job.get("layout", "lounge") + ".json"), encoding='utf-8'))
        pieces, problems, checks = assemble_room(pipeline, layout, pack, job["pack_json"], os.path.join(proof, "rooms", layout["layout_id"]),
                                                 os.path.join(proof, "textures"))
        report["room"] = {"layout": layout["layout_id"], "pieces": len(pieces), "expected": 1 + len(layout.get("openings", {})) + len(layout["fixtures"]),
                          "room_tris": sum(p["tris"] for p in pieces), "problems": problems, "asset_checks": checks,
                          "piece_hashes": {p["slot"]: p["sha256"] for p in pieces}}
        renders = {}
        if job.get("render", True) and pieces:
            report["stage"] = "render"
            renders = render_views(preview, room_mod, pack, pieces, job.get("views", ["main", "corner"]), tuple(job.get("res", [400, 300])), proof,
                                   png_mod=png_mod)
            report["renders"] = {k: os.path.relpath(v, pdir) for k, v in renders.items()}
            report["render_sha256"] = {k: sha(v) for k, v in renders.items()}
            if job.get("ref_measurements"):
                ref_meas = json.load(open(job["ref_measurements"], encoding='utf-8'))
                imgs = [{"index": i, "srgba": measure_png(png_mod, p), "weight": 1.0} for i, p in enumerate(renders.values())]
                pm = M.measure(imgs)
                report["proof_measurements"] = {"pooled_clusters": len(pm["pooled"]["clusters"])}
                report["style_match"] = style_match(ref_meas, pm)
        report["stage"] = "sheet"
        refs_rgba, labels = [], []
        if job.get("ref_thumbnails", True):
            for r in job.get("refs", []):
                refs_rgba.append(load_ref_rgba(r["path"]))
                labels.append("REF %d  %s" % (r["index"], r.get("label", "")))
        d = json.load(open(job["pack_json"], encoding='utf-8'))
        sheet = compose_sheet(png_mod, pixfont, refs_rgba, list(renders.values()), d, os.path.join(proof, "proof_sheet.png"),
                              "DRAFT PACK %s  (HERMES64_PACK_FROM_REFS)" % d["id"].upper(), labels)
        report["proof_sheet"] = os.path.relpath(sheet, pdir)
        report["ok"] = bool(vrep["pack_validator"]["ok"] and vrep["registry"]["ok"] and not problems and
                            all(c["fail"] == 0 for c in checks.values()) and len(pieces) == report["room"]["expected"])
        report["stage"] = "done"
    except Exception as e:  # report, never crash silently
        report["error"] = "%s: %s" % (type(e).__name__, e)
        report["traceback"] = traceback.format_exc()[-4000:]
        report["ok"] = False
    finally:
        report["seconds"] = round(time.time() - t0, 2)
        with open(job["out"], "w", encoding="utf-8") as f:
            json.dump(report, f, sort_keys=True, indent=1)
            f.write("\n")
        print("REFPACK_PROOF", "ok" if report.get("ok") else "failed", report.get("stage"), report.get("error", ""))
    return report


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rep = main(argv[0])
    sys.stdout.flush()
    sys.exit(0 if rep.get("ok") else 3)
