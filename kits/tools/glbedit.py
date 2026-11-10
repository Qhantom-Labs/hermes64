"""Minimal GLB rewriter for known-bad controls (pure python + numpy): read/write the JSON + BIN chunks,
replace an embedded image (re-packing every bufferView) and poke vertex colours in place."""
import json
import struct

import numpy as np


def read_glb(path):
    data = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and ver == 2, "not a glTF 2 binary"
    off = 12
    js, binc = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, bytearray(binc)


def write_glb(path, js, binc):
    jb = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jb += b" " * ((4 - len(jb) % 4) % 4)
    bb = bytes(binc) + b"\0" * ((4 - len(binc) % 4) % 4)
    total = 12 + 8 + len(jb) + 8 + len(bb)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<II", len(jb), 0x4E4F534A))
        f.write(jb)
        f.write(struct.pack("<II", len(bb), 0x004E4942))
        f.write(bb)


def view_bytes(js, binc, vi):
    v = js["bufferViews"][vi]
    o = v.get("byteOffset", 0)
    return bytes(binc[o:o + v["byteLength"]])


def repack(js, binc, replace=None):
    """Rebuild the BIN chunk view by view (4-byte aligned). replace: {bufferView index: new bytes}."""
    replace = replace or {}
    out = bytearray()
    for vi, v in enumerate(js["bufferViews"]):
        data = replace.get(vi, view_bytes(js, binc, vi))
        out += b"\0" * ((4 - len(out) % 4) % 4)
        v["byteOffset"] = len(out)
        v["byteLength"] = len(data)
        out += data
    js["buffers"][0]["byteLength"] = len(out)
    return out


def replace_image(js, binc, image_index, png_bytes):
    vi = js["images"][image_index]["bufferView"]
    return repack(js, binc, {vi: png_bytes})


def set_vertex_color(js, binc, rgb01, mesh_index=0, prim_index=0, vertex=0):
    """Overwrite COLOR_0 of one vertex in place (same byte length)."""
    acc = js["accessors"][js["meshes"][mesh_index]["primitives"][prim_index]["attributes"]["COLOR_0"]]
    v = js["bufferViews"][acc["bufferView"]]
    ctype = acc["componentType"]
    ncomp = {"VEC3": 3, "VEC4": 4}[acc["type"]]
    size = {5126: 4, 5121: 1, 5123: 2}[ctype]
    stride = v.get("byteStride", ncomp * size)
    base = v.get("byteOffset", 0) + acc.get("byteOffset", 0) + vertex * stride
    vals = list(rgb01) + [1.0] * (ncomp - 3)
    for c, x in enumerate(vals):
        if ctype == 5126:
            struct.pack_into("<f", binc, base + c * 4, float(x))
        elif ctype == 5121:
            struct.pack_into("<B", binc, base + c, int(round(x * 255)))
        else:
            struct.pack_into("<H", binc, base + c * 2, int(round(x * 65535)))
    return binc


def png_rgba(arr):
    from core import png
    return png.encode(np.ascontiguousarray(arr.astype(np.uint8)))
