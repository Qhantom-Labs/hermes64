"""hermes64_pack_from_refs: reference images + agent notes -> DRAFT theme pack + validation + proof sheet.

Stdlib orchestration (Python 3.9+), numpy workers, optional Pillow for JPEG and Godot for proofs.
No Blender subprocess. The tool never marks a pack approved."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from . import audio as audio_mod
from . import config, draft, guard, library
from . import notes as notes_mod

HERE = os.path.dirname(os.path.abspath(__file__))


def canonical_json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def write_bytes(pack_dir, rel, data):
    p = guard.safe_join(pack_dir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    return p


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def run_python(python_path, kind, job_path, timeout, work):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", work),
           "TMPDIR": work, "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C", "LC_ALL": "C"}
    cmd = [python_path, "-B", os.path.join(HERE, "worker.py"), kind, job_path]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, env=env, cwd=work)
    except subprocess.TimeoutExpired:
        return None, "timed out after %d s" % timeout, time.time() - t0
    except OSError as e:
        return None, "cannot run Python (%s); configure python_path: %s" % (python_path, e), time.time() - t0
    tail = p.stdout.decode("utf-8", "replace")[-3000:]
    return p.returncode, tail, time.time() - t0


def strip_measurements(meas):
    """The drafter only sees numbers: drop decoder/version info so pack.json never depends on it."""
    m = {k: v for k, v in meas.items() if k not in ("decode", "blender")}
    return m


def notes_md(pack, d, refs, nn, audio_dec, warnings):
    dec = d["decisions"]
    L = ["# %s (DRAFT, not approved)" % pack["id"], "",
         "Drafted by `%s` %s from %d reference image(s). Approval is a human decision; this file explains the "
         "draft so it can be reviewed. References are private study material: only hashes are recorded and no "
         "pixels are stored in `pack.json`/`audio.json`." % (config.TOOL_ID, config.TOOL_VERSION, len(refs)), "",
         "## Inputs", ""]
    for r in refs:
        nr = nn["references"][r["index"]]
        L.append("- ref %d: `%s` sha256 `%s...` %dx%d, kind %s, setting %s, weight %s, use %s" % (
            r["index"], r["basename"], r["sha256"][:16], r["width"], r["height"], nr["kind"], nr["setting"], nr["weight"],
            "/".join(nr["use"])))
    L += ["", "## Palette (%d colours)" % len(pack["palette"]), ""]
    for f in dec["families"]:
        L.append("- family `%s`: %d steps, coverage %.1f%%, hue %.0f%s" % (f["name"], f["steps"], 100 * f["coverage"], f["hue"],
                                                                      " (neutral)" if f["neutral"] else ""))
    L.append("- light ramp: %s (%d steps, shadow tint -> white)" % (", ".join(pack["light_ramp"]), len(pack["light_ramp"])))
    srcs = pack["refpack"]["palette_sources"]
    counts = {}
    for s in srcs.values():
        counts[s] = counts.get(s, 0) + 1
    L.append("- colour sources: %s" % ", ".join("%s %d" % (k, v) for k, v in sorted(counts.items())))
    L += ["", "## Surfaces and materials", ""]
    for k, v in sorted(dec["surfaces"].items()):
        L.append("- %s: %s (target %s)" % (k, v, dec["targets"].get(k, "-")))
    L += ["", "## Light and fog", "",
          "- light rig: %s" % json.dumps(pack["light_rig"], sort_keys=True),
          "- fog: exterior %s %.1f..%.1f m, interior %s %.1f..%.1f m (density notes %.2f, ext %.2f, int %.2f)" % (
              pack["fog"]["color"], pack["fog"]["start"], pack["fog"]["end"], pack["fog"]["interior"]["color"],
              pack["fog"]["interior"]["start"], pack["fog"]["interior"]["end"], dec["fog"]["density_notes"],
              dec["fog"]["density_ext"], dec["fog"]["density_int"]),
          "", "## Kit presets (chosen from the library, never invented)", ""]
    for slot, v in sorted(dec["presets"].items()):
        L.append("- %s -> `%s` (score %d)" % (slot, v["entry"], v["score"]))
    L += ["", "## Sound palette (catalog tags)", "", "- %s" % json.dumps(audio_dec, sort_keys=True), ""]
    if warnings:
        L += ["## Warnings", ""] + ["- %s" % w for w in warnings] + [""]
    L += ["## Known limits", "", "- Pixels cannot separate albedo from light colour; textures are inverse-lit estimates.",
          "- Shapes come only from existing presets/enum variants; new silhouettes need authored presets.",
          "- Proof uses the shipped Godot N64 material pipeline, or an explicitly lower-fidelity software preview when Godot is absent. See validation.json.", ""]
    return "\n".join(L).encode("utf-8")


def pack_from_refs(reference_paths, notes, pack_id, project_dir, read_root=None, render_proof=True,
                   ref_thumbnails=True, layout="lounge", proof_res=(400, 300), timeout_s=900, kits_dir=None,
                   audio_dir=None, blender=None, mode="albedo", keep_work=False, measure_timeout_s=180,
                   python_path=None, godot_path=None):
    t0 = time.time()
    res = {"ok": False, "status": "rejected", "tool": config.TOOL_ID, "tool_version": config.TOOL_VERSION,
           "pack_dir": None, "pack_json": None, "audio_json": None, "provenance": None, "validation_report": None,
           "proof_sheet": None, "errors": [], "warnings": [], "hashes": {}, "timings": {}}
    created = False
    try:
        guard.check_pack_id(pack_id)
        refs = guard.check_references(reference_paths, read_root)
        raw_notes, notes_bytes = notes_mod.load_notes(notes)
        nn = notes_mod.validate_notes(raw_notes, len(refs), [r["sha256"] for r in refs])
        if mode not in ("albedo", "measured"):
            raise guard.GuardError("mode must be 'albedo' or 'measured'")
        if not (isinstance(proof_res, (list, tuple)) and len(proof_res) == 2 and all(isinstance(v, int) and 64 <= v <= 1024 for v in proof_res)):
            raise guard.GuardError("proof_res must be two integers in 64..1024")
        if not (isinstance(timeout_s, int) and 30 <= timeout_s <= 3600):
            raise guard.GuardError("timeout_s must be an integer in 30..3600")
        existed = os.path.isdir(os.path.join(os.path.realpath(project_dir), "packs", pack_id)) if isinstance(project_dir, str) else False
        pdir = guard.prepare_pack_dir(project_dir, pack_id)
        created = not existed
    except (guard.GuardError, notes_mod.NotesError) as e:
        res["errors"].append(str(e))
        res["timings"]["total"] = round(time.time() - t0, 2)
        return res
    res["pack_dir"] = pdir
    kits = config.kits_dir(kits_dir)
    python_bin = python_path or sys.executable
    # blender remains an ignored compatibility argument; never an implicit fallback.
    work = guard.safe_join(pdir, ".work")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    try:
        # ---------------- measure
        meas_path = os.path.join(work, "measurements.json")
        job = {"images": [{"index": r["index"], "path": r["real"], "width": r["width"], "height": r["height"],
                           "weight": nn["references"][r["index"]]["weight"],
                           "use_palette": "palette" in nn["references"][r["index"]]["use"],
                           "crop": nn["references"][r["index"]].get("crop"),
                           "exclude": nn["references"][r["index"]].get("exclude", []),
                           "regions": nn["references"][r["index"]].get("regions", {})} for r in refs], "out": meas_path}
        jp = os.path.join(work, "measure_job.json")
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1, sort_keys=True)
        code, tail, secs = run_python(python_bin, "measure", jp, measure_timeout_s, work)
        res["timings"]["measure"] = round(secs, 2)
        if code is None:
            res["errors"].append("measure stage: %s" % tail)
            return _reject(res, pdir, created, keep_work, t0)
        if not os.path.exists(meas_path):
            res["errors"].append("measure stage failed (exit %s): %s" % (code, tail[-600:]))
            return _reject(res, pdir, created, keep_work, t0)
        meas = json.load(open(meas_path, "r", encoding="utf-8"))
        if not meas.get("ok"):
            for e in meas.get("errors", []):
                i = e.get("index")
                name = refs[i]["basename"] if isinstance(i, int) and 0 <= i < len(refs) else "?"
                res["errors"].append("reference %s (%s): %s" % (i, name, e["reason"]))
            return _reject(res, pdir, created, keep_work, t0)
        # ---------------- draft
        t1 = time.time()
        lib = library.load()
        cn = notes_mod.controlled_view(nn)
        d = draft.draft(strip_measurements(meas), cn, lib, pack_id, mode=mode)
        pack = d["pack"]
        pack["refpack"]["references"] = [{"index": r["index"], "sha256": r["sha256"], "bytes": r["bytes"],
                                          "width": r["width"], "height": r["height"]} for r in refs]
        pack["refpack"]["notes_sha256"] = sha256(notes_bytes)
        pack["refpack"]["tool"] = config.TOOL_ID
        pack["refpack"]["tool_version"] = config.TOOL_VERSION
        pack["refpack"]["mode"] = mode
        catalog, cat_raw = audio_mod.load_catalog(audio_dir)
        aud, adec = audio_mod.select_palette(pack_id, cn, d["surfaces"], catalog, lib["audio_map"])
        audio_errs = audio_mod.check_palette(aud, catalog)
        pack_bytes = canonical_json_bytes(pack)
        audio_bytes = canonical_json_bytes(aud)
        write_bytes(pdir, "pack.json", pack_bytes)
        write_bytes(pdir, "audio.json", audio_bytes)
        res["warnings"].extend(d["warnings"])
        write_bytes(pdir, "NOTES.md", notes_md(pack, d, refs, nn, adec, d["warnings"]))
        meas_bytes = canonical_json_bytes(strip_measurements(meas))
        prov = {"tool": config.TOOL_ID, "tool_version": config.TOOL_VERSION, "status": "draft_unapproved",
                "statement": ("No reference pixels are stored in pack.json or audio.json: palette entries are k-means "
                              "cluster centroids, inverse-lit estimates or OKLab interpolations of them, plus notes-requested "
                              "accent hues (labelled in refpack.palette_sources). proof/ contains downscaled reference "
                              "thumbnails for private human review only; it is not part of a distributable pack."),
                "references": [{"index": r["index"], "basename": r["basename"], "sha256": r["sha256"], "bytes": r["bytes"],
                                "format": r["format"], "width": r["width"], "height": r["height"]} for r in refs],
                "notes_sha256": sha256(notes_bytes), "notes_free_text_copied": False,
                "measurements_sha256": sha256(meas_bytes), "mode": mode,
                "library": library.hashes(), "catalog_sha256": sha256(cat_raw),
                "lane_kits_validator_sha256": sha256(open(os.path.join(kits, "core", "packs.py"), "rb").read()),
                "outputs": {"pack.json": sha256(pack_bytes), "audio.json": sha256(audio_bytes)},
                "approval": "never set by this tool"}
        write_bytes(pdir, "PROVENANCE.json", canonical_json_bytes(prov))
        write_bytes(pdir, "proof/measurements.json", meas_bytes)
        res["timings"]["draft"] = round(time.time() - t1, 2)
        res["hashes"] = {"pack.json": sha256(pack_bytes), "audio.json": sha256(audio_bytes), "measurements": sha256(meas_bytes)}
        res["pack_json"] = os.path.join(pdir, "pack.json")
        res["audio_json"] = os.path.join(pdir, "audio.json")
        res["provenance"] = os.path.join(pdir, "PROVENANCE.json")
        # ---------------- validate + proof
        pj = {"pack_json": res["pack_json"], "pack_dir": pdir, "kits_dir": kits, "layout": layout,
              "res": list(proof_res), "views": ["main", "corner"], "render": bool(render_proof), "godot_path": godot_path,
              "ref_thumbnails": bool(ref_thumbnails), "ref_measurements": os.path.join(pdir, "proof", "measurements.json"),
              "refs": [{"index": r["index"], "path": r["real"], "label": r["basename"]} for r in refs],
              "out": os.path.join(work, "proof_report.json")}
        pjp = os.path.join(work, "proof_job.json")
        with open(pjp, "w", encoding="utf-8") as f:
            json.dump(pj, f, indent=1, sort_keys=True)
        code, tail, secs = run_python(python_bin, "proof", pjp, timeout_s, work)
        res["timings"]["proof"] = round(secs, 2)
        rep = json.load(open(pj["out"], encoding='utf-8')) if os.path.exists(pj["out"]) else {"ok": False, "error": "no report: %s" % tail[-800:]}
        if code is None:
            rep = {"ok": False, "error": "proof stage %s" % tail}
        validation = {"tool": config.TOOL_ID, "pack": pack_id, "pack_json_sha256": res["hashes"]["pack.json"],
                      "lane_kits": {k: rep.get(k) for k in ("pack_validator", "registry", "room")},
                      "audio_palette": {"ok": not audio_errs, "errors": audio_errs,
                                        "checker": "mirror of lane-audio stock_catalog.resolve_palette v1.1"},
                      "refpack_checks": refpack_checks(pack),
                      "style_match": rep.get("style_match"), "renders": rep.get("renders"),
                      "render_sha256": rep.get("render_sha256"), "proof_error": rep.get("error"),
                      "stage": rep.get("stage"), "renderer": rep.get("renderer"), "lower_fidelity": rep.get("lower_fidelity")}
        refpack_ok = all(v["ok"] for v in validation["refpack_checks"].values())
        validation["ok"] = bool(rep.get("ok")) and not audio_errs and refpack_ok
        vbytes = canonical_json_bytes(validation)
        write_bytes(pdir, "validation.json", vbytes)
        res["validation_report"] = os.path.join(pdir, "validation.json")
        if rep.get("proof_sheet"):
            res["proof_sheet"] = os.path.join(pdir, rep["proof_sheet"])
        res["validation"] = {"ok": validation["ok"], "pack_validator": (rep.get("pack_validator") or {}).get("ok"),
                             "registry": (rep.get("registry") or {}).get("ok"),
                             "room_pieces": (rep.get("room") or {}).get("pieces"),
                             "asset_checks": (rep.get("room") or {}).get("asset_checks"),
                             "audio": not audio_errs, "refpack_checks": refpack_ok, "style_match": rep.get("style_match")}
        if rep.get("error"):
            res["errors"].append("proof stage: %s" % rep["error"])
        res["ok"] = validation["ok"]
        res["status"] = "draft" if validation["ok"] else "invalid"
        return res
    finally:
        if not keep_work and os.path.isdir(work):
            shutil.rmtree(work, ignore_errors=True)
        res["timings"]["total"] = round(time.time() - t0, 2)


def _reject(res, pdir, created, keep_work, t0):
    res["status"] = "rejected"
    work = os.path.join(pdir, ".work")
    if not keep_work and os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    if created and os.path.isdir(pdir) and not [e for e in os.listdir(pdir) if e != ".work"]:
        shutil.rmtree(pdir, ignore_errors=True)
        parent = os.path.dirname(pdir)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    res["pack_dir"] = None
    res["timings"]["total"] = round(time.time() - t0, 2)
    return res


def refpack_checks(pack):
    from . import colour as C
    names = pack["palette_names"]
    hexes = pack["palette"]
    lab = {n: C.hex_to_oklab(h) for n, h in zip(names, hexes)}
    lr = pack["light_ramp"]
    mono = all(lab[a][0] < lab[b][0] for a, b in zip(lr, lr[1:]))
    out = {
        "palette_size": {"ok": 3 <= len(hexes) <= 32, "value": len(hexes)},
        "light_ramp_monotone": {"ok": mono and len(lr) >= 3, "value": [round(lab[n][0], 3) for n in lr]},
        "ui_text_contrast": {"ok": C.contrast_ratio(pack["ui"]["text"], pack["ui"]["fill"][:7]) >= 4.5,
                             "value": round(C.contrast_ratio(pack["ui"]["text"], pack["ui"]["fill"][:7]), 2)},
        "fog_order": {"ok": 0 <= pack["fog"]["start"] < pack["fog"]["end"] and
                      0 <= pack["fog"]["interior"]["start"] < pack["fog"]["interior"]["end"], "value": None},
        "status_is_draft": {"ok": pack.get("refpack", {}).get("status") == "draft_unapproved", "value": pack.get("refpack", {}).get("status")},
        "no_free_text": {"ok": True, "value": "pack strings come from controlled vocab, numbers and hashes"},
    }
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m refpack", description="hermes64_pack_from_refs: draft a theme pack from reference images")
    ap.add_argument("--refs", nargs="+", required=True)
    ap.add_argument("--notes", required=True, help="reference notes JSON file")
    ap.add_argument("--pack-id", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--read-root", default=None)
    ap.add_argument("--no-proof", action="store_true")
    ap.add_argument("--no-ref-thumbs", action="store_true")
    ap.add_argument("--mode", default="albedo", choices=["albedo", "measured"])
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--python-path", help="Python 3.9+ with numpy; JPEG additionally needs Pillow")
    ap.add_argument("--godot-path", help="Existing Godot executable; absent uses labelled software preview")
    a = ap.parse_args(argv)
    r = pack_from_refs(a.refs, a.notes, a.pack_id, a.project, read_root=a.read_root, render_proof=not a.no_proof,
                       ref_thumbnails=not a.no_ref_thumbs, mode=a.mode, timeout_s=a.timeout, keep_work=a.keep_work,
                       python_path=a.python_path, godot_path=a.godot_path)
    print(json.dumps(r, indent=1, sort_keys=True))
    return 0 if r["ok"] else (2 if r["status"] == "rejected" else 3)
