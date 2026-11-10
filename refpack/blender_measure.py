"""Blender entry point: decode reference images with bpy and measure them (numbers only).

  blender -b --factory-startup --python-exit-code 4 --python refpack/blender_measure.py -- JOB.json

JOB.json = {"images": [{"index", "path", "width", "height", "weight", "use_palette", "crop", "exclude"}],
            "out": "<pack>/.work/measurements.json"}
Exit 0 = measured; 2 = a reference was rejected (corrupt / zero variance / size mismatch); the out file
then holds {"ok": false, "errors": [...]} so the caller can report the exact image and reason."""
import sys

sys.dont_write_bytecode = True  # never write __pycache__ next to imported code
import json  # noqa: E402
import os  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from refpack import measure_np as M  # noqa: E402


def load_rgba(path, want_w, want_h):
    try:
        im = bpy.data.images.load(path, check_existing=False)
    except Exception as e:  # bpy raises RuntimeError for undecodable files
        raise M.MeasureError("cannot decode: %s" % str(e).strip().splitlines()[0][:200])
    try:
        w, h = int(im.size[0]), int(im.size[1])
        if w == 0 or h == 0 or not im.has_data:
            raise M.MeasureError("decoder returned no pixels (corrupt or unsupported file)")
        if (w, h) != (want_w, want_h):
            raise M.MeasureError("decoded size %dx%d differs from the header %dx%d (corrupt file)" % (w, h, want_w, want_h))
        ch = int(im.channels)
        a = np.empty(w * h * ch, dtype=np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(h, w, ch)[::-1].astype(np.float64)  # Blender rows are bottom-up
        if ch == 3:
            a = np.concatenate([a, np.ones((h, w, 1))], axis=2)
        elif ch == 1:
            a = np.concatenate([a, a, a, np.ones((h, w, 1))], axis=2)
        elif ch == 2:
            a = np.concatenate([a[..., :1], a[..., :1], a[..., :1], a[..., 1:2]], axis=2)
        if im.is_float:  # float buffers (16-bit PNG) are scene-linear in Blender
            a[..., :3] = M.lin_to_srgb(a[..., :3])
        a = np.clip(a, 0.0, 1.0)
        if not np.isfinite(a).all():
            raise M.MeasureError("decoded pixels contain NaN/Inf")
        return a, {"is_float": bool(im.is_float), "channels": ch, "depth": int(im.depth)}
    finally:
        bpy.data.images.remove(im)


def main(job_path):
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)
    errors, images, decode_info = [], [], []
    for spec in job["images"]:
        try:
            rgba, info = load_rgba(spec["path"], spec["width"], spec["height"])
            images.append({"index": spec["index"], "srgba": rgba, "weight": spec.get("weight", 1.0),
                           "use_palette": spec.get("use_palette", True), "crop": spec.get("crop"),
                           "exclude": spec.get("exclude", []), "regions": spec.get("regions", {})})
            decode_info.append(dict(info, index=spec["index"]))
        except M.MeasureError as e:
            errors.append({"index": spec["index"], "reason": str(e)})
    result = None
    if not errors:
        try:
            result = M.measure(images)
        except M.MeasureError as e:
            msg = str(e)
            idx = None
            if msg.startswith("reference "):
                try:
                    idx = int(msg.split()[1].rstrip(":"))
                except ValueError:
                    idx = None
            errors.append({"index": idx, "reason": msg})
    out = {"schema": "hermes64.refpack.measurements", "version": "1.0.0"}
    if errors:
        out.update({"ok": False, "errors": errors})
        code = 2
    else:
        out.update({"ok": True, "decode": decode_info, "blender": bpy.app.version_string})
        out.update(result)
        code = 0
    with open(job["out"], "w", encoding="utf-8") as f:
        json.dump(out, f, sort_keys=True, indent=1)
        f.write("\n")
    print("REFPACK_MEASURE", "ok" if code == 0 else "rejected", len(job["images"]))
    return code


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    code = main(argv[0])
    sys.stdout.flush()
    sys.exit(code)
