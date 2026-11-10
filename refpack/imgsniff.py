"""Stdlib image header sniffing (no decoding): format by magic bytes, dimensions from the PNG IHDR or
the JPEG SOFn marker. Used to refuse non-images and decompression bombs BEFORE Blender decodes anything."""
import struct


class SniffError(ValueError):
    pass


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def sniff(path, max_scan=4 * 1024 * 1024):
    """Returns {"format": "png"|"jpeg", "width": int, "height": int, ...}. Raises SniffError."""
    with open(path, "rb") as f:
        head = f.read(32)
        if head.startswith(PNG_MAGIC):
            if len(head) < 24 or head[12:16] != b"IHDR":
                raise SniffError("PNG header is truncated or has no IHDR chunk")
            w, h = struct.unpack(">II", head[16:24])
            depth, ctype = head[24], head[25]
            if depth not in (1, 2, 4, 8, 16) or ctype not in (0, 2, 3, 4, 6):
                raise SniffError("PNG IHDR has an invalid bit depth/colour type (%d/%d)" % (depth, ctype))
            return {"format": "png", "width": w, "height": h, "bit_depth": depth, "colour_type": ctype}
        if head[:3] == b"\xff\xd8\xff":
            f.seek(2)
            data = f.read(max_scan)
            return _jpeg_dims(data)
    raise SniffError("not a PNG or JPEG file (magic bytes %s)" % head[:8].hex())


def verify_container(path, fmt, max_bytes=64 * 1024 * 1024):
    """Cheap integrity checks without decoding pixels.
    PNG: every chunk's CRC must match, IHDR first, at least one IDAT, IEND present.
    JPEG: an end-of-image marker (FFD9) must exist in the last 1 MiB (catches truncation).
    (Corrupted JPEG entropy data that still has its markers cannot be detected without decoding.)"""
    import zlib
    with open(path, "rb") as f:
        if fmt == "png":
            data = f.read(max_bytes + 1)
            pos, first, n_idat, seen_iend = 8, True, 0, False
            while pos + 12 <= len(data):
                (ln,) = struct.unpack(">I", data[pos:pos + 4])
                tag = data[pos + 4:pos + 8]
                if pos + 12 + ln > len(data):
                    raise SniffError("PNG chunk %r at byte %d runs past the end of the file (truncated)" % (tag, pos))
                body = data[pos + 8:pos + 8 + ln]
                (crc,) = struct.unpack(">I", data[pos + 8 + ln:pos + 12 + ln])
                if zlib.crc32(tag + body) & 0xFFFFFFFF != crc:
                    raise SniffError("PNG chunk %r at byte %d fails its CRC (corrupt)" % (tag, pos))
                if first and tag != b"IHDR":
                    raise SniffError("PNG does not start with IHDR")
                first = False
                n_idat += tag == b"IDAT"
                pos += 12 + ln
                if tag == b"IEND":
                    seen_iend = True
                    break
            if not seen_iend:
                raise SniffError("PNG has no IEND chunk (truncated)")
            if n_idat == 0:
                raise SniffError("PNG has no image data (IDAT)")
            return True
        if fmt == "jpeg":
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - (1 << 20)))
            tail = f.read()
            if b"\xff\xd9" not in tail:
                raise SniffError("JPEG has no end-of-image marker (truncated)")
            return True
    raise SniffError("unknown format %r" % fmt)


def _jpeg_dims(data):
    i = 0
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            raise SniffError("JPEG marker stream is corrupt at byte %d" % (i + 2))
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            break
        if i + 2 > n:
            break
        (seglen,) = struct.unpack(">H", data[i:i + 2])
        if seglen < 2:
            raise SniffError("JPEG segment length %d is invalid" % seglen)
        if marker in SOF_MARKERS:
            if i + 7 > n:
                break
            prec, h, w, comps = struct.unpack(">BHHB", data[i + 2:i + 8])
            if w == 0 or h == 0:
                raise SniffError("JPEG frame has zero width/height")
            return {"format": "jpeg", "width": w, "height": h, "precision": prec, "components": comps}
        i += seglen
    raise SniffError("JPEG has no frame header (SOF) in the first bytes: truncated or corrupt")
