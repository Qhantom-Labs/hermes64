"""Tiny stdlib PNG encoder/decoder (8-bit RGB/RGBA, no interlace). Used for test fixtures, thumbnails
assembled outside Blender and for reading back proof renders in stdlib code. Not a general decoder:
it reads only what it writes plus the 8-bit RGB/RGBA PNGs Blender saves (filter types 0-4)."""
import struct
import zlib


def encode(width, height, rows, alpha=False):
    """rows: list of bytes/bytearray, each width*3 (or *4) bytes. Returns PNG bytes."""
    ch = 4 if alpha else 3
    raw = bytearray()
    for r in rows:
        if len(r) != width * ch:
            raise ValueError("row length %d != %d" % (len(r), width * ch))
        raw.append(0)
        raw.extend(r)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def solid(width, height, rgb):
    row = bytes(rgb) * width
    return encode(width, height, [row] * height)


def decode(data):
    """Returns (width, height, channels, rows[list of bytearray]). 8-bit RGB/RGBA only."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    idat = bytearray()
    w = h = None
    ch = None
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, depth, ctype, _c, _f, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or inter != 0:
                raise ValueError("unsupported PNG (depth %d, colour type %d, interlace %d)" % (depth, ctype, inter))
            ch = 3 if ctype == 2 else 4
        elif tag == b"IDAT":
            idat.extend(body)
        elif tag == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    rows = []
    prev = bytearray(stride)
    p = 0
    for _y in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ValueError("bad PNG filter %d" % ft)
        rows.append(line)
        prev = line
    return w, h, ch, rows
