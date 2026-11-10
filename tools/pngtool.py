#!/usr/bin/env python3
"""Minimal stdlib PNG tool for lane-look evidence (no PIL available/allowed).

Commands:
  pix  FILE X Y [X Y ...]        print RGBA at coordinates
  info FILE                      size, unique colour count, top colours
  diff A B                       pixels differing, mean abs diff per channel
  sheet OUT COLS SCALE FILE...   nearest-upscaled contact sheet (RGB) with 2px gaps
  crop OUT FILE X Y W H SCALE    crop + nearest upscale
Supports 8-bit RGB/RGBA/grey(+alpha), non-interlaced (what Godot writes).
"""
import struct
import sys
import zlib


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    idat = b""
    w = h = ctype = depth = interlace = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype_tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype_tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif ctype_tag == b"IDAT":
            idat += chunk
        elif ctype_tag == b"IEND":
            break
    assert depth == 8 and interlace == 0, "only 8-bit non-interlaced supported"
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * channels
    rows = []
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ft == 1:
                line[x] = (line[x] + a) & 255
            elif ft == 2:
                line[x] = (line[x] + b) & 255
            elif ft == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        rows.append(bytes(line))
        prev = line
    px = []
    for row in rows:
        r = []
        for x in range(w):
            v = row[x * channels:(x + 1) * channels]
            if channels == 1:
                r.append((v[0], v[0], v[0], 255))
            elif channels == 2:
                r.append((v[0], v[0], v[0], v[1]))
            elif channels == 3:
                r.append((v[0], v[1], v[2], 255))
            else:
                r.append(tuple(v))
        px.append(r)
    return w, h, px


def write_png(path, w, h, px):
    raw = b"".join(b"\x00" + bytes(c for p in row for c in p[:3]) for row in px)

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def main(argv):
    cmd = argv[1]
    if cmd == "pix":
        w, h, px = read_png(argv[2])
        nums = list(map(int, argv[3:]))
        for k in range(0, len(nums), 2):
            x, y = nums[k], nums[k + 1]
            print(f"({x},{y}) = {px[y][x]}")
    elif cmd == "info":
        w, h, px = read_png(argv[2])
        hist = {}
        for row in px:
            for p in row:
                hist[p] = hist.get(p, 0) + 1
        print(f"{argv[2]}: {w}x{h} unique_colours={len(hist)}")
        for col, n in sorted(hist.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {col} x{n}")
    elif cmd == "diff":
        wa, ha, a = read_png(argv[2])
        wb, hb, b = read_png(argv[3])
        assert (wa, ha) == (wb, hb), "size mismatch"
        n = 0
        tot = [0, 0, 0]
        for y in range(ha):
            for x in range(wa):
                pa, pb = a[y][x], b[y][x]
                if pa[:3] != pb[:3]:
                    n += 1
                for c in range(3):
                    tot[c] += abs(pa[c] - pb[c])
        npx = wa * ha
        print(f"differing_pixels={n}/{npx} ({100.0 * n / npx:.2f}%) mean_abs_diff_rgb="
              f"{tot[0] / npx:.2f},{tot[1] / npx:.2f},{tot[2] / npx:.2f}")
    elif cmd == "sheet":
        out, cols, scale = argv[2], int(argv[3]), int(argv[4])
        imgs = [read_png(p) for p in argv[5:]]
        cw = max(i[0] for i in imgs) * scale
        ch = max(i[1] for i in imgs) * scale
        gap = 2
        rows_n = (len(imgs) + cols - 1) // cols
        W = cols * cw + (cols + 1) * gap
        H = rows_n * ch + (rows_n + 1) * gap
        canvas = [[(24, 24, 24)] * W for _ in range(H)]
        for k, (w, h, px) in enumerate(imgs):
            ox = gap + (k % cols) * (cw + gap)
            oy = gap + (k // cols) * (ch + gap)
            for y in range(h * scale):
                src = px[y // scale]
                row = canvas[oy + y]
                for x in range(w * scale):
                    row[ox + x] = src[x // scale][:3]
        write_png(out, W, H, canvas)
        print(f"sheet {out}: {W}x{H} from {len(imgs)} images")
    elif cmd == "crop":
        out, src = argv[2], argv[3]
        x0, y0, cw, ch, scale = map(int, argv[4:9])
        w, h, px = read_png(src)
        canvas = [[px[y0 + y // scale][x0 + x // scale][:3] for x in range(cw * scale)] for y in range(ch * scale)]
        write_png(out, cw * scale, ch * scale, canvas)
        print(f"crop {out}: {cw * scale}x{ch * scale}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
