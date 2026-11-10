"""Minimal deterministic PNG writer/reader (stdlib zlib + numpy). 8-bit RGB/RGBA/indexed/grey."""
import struct
import zlib

import numpy as np


def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def encode(arr):
    """arr: (H, W, 3|4) uint8. Filter 0 rows, zlib level 9 -> byte-stable output."""
    a = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w, c = a.shape
    ct = {3: 2, 4: 6}[c]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)) +
            _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def write(path, arr):
    data = encode(arr)
    with open(path, "wb") as f:
        f.write(data)
    return data


def decode(data):
    """Returns (H, W, C) uint8 array (C = 3 or 4; indexed expanded to RGB/RGBA, grey to RGB)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    idat = b""
    plte = None
    trns = None
    w = h = depth = ctype = interlace = None
    while pos < len(data):
        ln, t = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if t == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif t == b"PLTE":
            plte = np.frombuffer(body, dtype=np.uint8).reshape(-1, 3)
        elif t == b"tRNS":
            trns = np.frombuffer(body, dtype=np.uint8)
        elif t == b"IDAT":
            idat += body
        elif t == b"IEND":
            break
    if w is None or h is None:
        raise ValueError("missing PNG dimensions")
    if depth != 8 or interlace != 0:
        raise ValueError("unsupported PNG (depth %r interlace %r)" % (depth, interlace))
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    stride = w * ch
    if not 0 < w <= 16384 or not 0 < h <= 16384 or w*h > 64000000:
        raise ValueError("PNG dimensions exceed decode limit")
    expected = h*(stride+1)
    inflater = zlib.decompressobj()
    raw = inflater.decompress(idat, expected+1)
    if len(raw) != expected or not inflater.eof or inflater.unused_data:
        raise ValueError("PNG inflate length differs from dimensions")
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int64)
    p = 0
    for y in range(h):
        ft = raw[p]
        line = np.frombuffer(raw[p + 1:p + 1 + stride], dtype=np.uint8).astype(np.int64)
        p += 1 + stride
        cur = np.zeros(stride, dtype=np.int64)
        if ft == 0:
            cur = line
        elif ft == 2:
            cur = (line + prev) & 255
        else:
            for i in range(stride):
                a = cur[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                if ft == 1:
                    v = line[i] + a
                elif ft == 3:
                    v = line[i] + ((a + b) >> 1)
                elif ft == 4:
                    pp = a + b - c
                    pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    v = line[i] + pr
                else:
                    raise ValueError("bad filter %d" % ft)
                cur[i] = v & 255
        out[y] = cur.astype(np.uint8)
        prev = cur
    img = out.reshape(h, w, ch)
    if ctype == 3:
        rgb = plte[img[:, :, 0]]
        if trns is not None:
            alpha = np.full(len(plte), 255, dtype=np.uint8)
            alpha[:len(trns)] = trns
            return np.concatenate([rgb, alpha[img[:, :, 0]][:, :, None]], 2)
        return rgb
    if ctype == 0:
        rgb = np.repeat(img, 3, axis=2)
        if trns is not None:
            key = struct.unpack('>H', trns.tobytes())[0]
            return np.concatenate([rgb, np.where(img == key, 0, 255).astype(np.uint8)], 2)
        return rgb
    if ctype == 4:
        return np.concatenate([np.repeat(img[:, :, :1], 3, axis=2), img[:, :, 1:]], 2)
    if ctype == 2 and trns is not None:
        key = np.array(struct.unpack('>HHH', trns.tobytes()))
        alpha = np.where(np.all(img == key, axis=2), 0, 255).astype(np.uint8)
        return np.concatenate([img, alpha[:, :, None]], 2)
    return img


def read(path):
    with open(path, "rb") as f:
        return decode(f.read())
