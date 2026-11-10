"""Box-art finishing for staged covers (stdlib only; Pillow is never required, numpy is never imported).

Input: the cover renderer's beauty PNGs (runtime/godot/cover). Output: finished box art in fixed sizes. Everything is
integer/deterministic Python, so the same render + scene give byte-identical PNGs on any machine. PNG encoding
matches kits/core/png.py (filter 0 rows, zlib level 9); decoding uses style_gate.read_png (stdlib).

Composition (all original, drawn here): subtle grade and vignette, a soft scrim behind the title, the title logotype
in the original pixel face (cover_font) at an integer scale with a vertical gradient fill, a top-edge bevel, a dark
outline, a solid extrude and an offset drop shadow, a style band in the style colour along one edge carrying the style
label, and a small original star-disc corner mark. The console trade dress (a red band down the right edge with a
logo in the top-right corner) is deliberately not used: the band defaults to the bottom edge in the style colour.
"""
import math
import re
import struct
import zlib
from pathlib import Path

from . import cover_font
from .style_gate import read_png

EXPORTS = {
    # name: (width, height, source render, title scale floor)
    'box-1x': (245, 170, 'card', 2),
    'box-2x': (490, 340, 'card', 4),
    'banner': (1280, 640, 'banner', 6),
    'square': (1080, 1080, 'square', 7),
}
STUDIO_ART = (440, 308)      # 2x of the Studio cartridge art window (220x154); title-free, the Studio draws its own
ALPHA_PAD = (14, 10, 16, 22)  # left, top, right, bottom transparent margin around the 2x card (room for the shadow)


# ------------------------------------------------------------------ image + PNG
class Img:
    __slots__ = ('w', 'h', 'c', 'px')

    def __init__(self, w, h, c=3, px=None, fill=(0, 0, 0, 0)):
        self.w, self.h, self.c = w, h, c
        self.px = bytearray(px) if px is not None else bytearray(bytes(fill[:c]) * (w * h))
        if len(self.px) != w * h * c:
            raise ValueError('pixel buffer size mismatch')

    def copy(self):
        return Img(self.w, self.h, self.c, self.px)


def _chunk(tag, body):
    return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)


def encode_png(img):
    """Byte-compatible with kits/core/png.py encode (filter 0, zlib 9)."""
    ct = {3: 2, 4: 6}[img.c]
    stride = img.w * img.c
    raw = b''.join(b'\x00' + bytes(img.px[y * stride:(y + 1) * stride]) for y in range(img.h))
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', img.w, img.h, 8, ct, 0, 0, 0)) +
            _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


_DECODED = {}


def load(path):
    """Decode a PNG to RGB. Decodes are cached by (resolved path, mtime_ns, size) for the life of the process, so the
    gate and the finisher reading the same render twice pay for one pure-Python unfilter; callers get a fresh copy."""
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    hit = _DECODED.get(key)
    if hit is None:
        w, h, px = read_png(str(p))
        hit = (w, h, bytes(px))
        if len(_DECODED) >= 8:
            _DECODED.pop(next(iter(_DECODED)))
        _DECODED[key] = hit
    return Img(hit[0], hit[1], 3, bytearray(hit[2]))


def save(img, path):
    data = encode_png(img)
    Path(path).write_bytes(data)
    return data


def hex_rgb(v):
    v = v.lstrip('#')
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def luma(rgb):
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ------------------------------------------------------------------ resampling
def box_down(img, f):
    """Integer box-filter downsample (averaging, no sharpening)."""
    if f == 1:
        return img.copy()
    W, H, c = img.w // f, img.h // f, img.c
    src, w = img.px, img.w
    out = bytearray(W * H * c)
    n = f * f
    half = n // 2
    for y in range(H):
        acc = [0] * (W * c)
        for yy in range(f):
            row = memoryview(src)[(y * f + yy) * w * c:(y * f + yy + 1) * w * c]
            for x in range(W):
                base = x * f * c
                for k in range(c):
                    s = 0
                    for xx in range(f):
                        s += row[base + xx * c + k]
                    acc[x * c + k] += s
        o = y * W * c
        for i in range(W * c):
            out[o + i] = (acc[i] + half) // n
    return Img(W, H, c, out)


def _weights(n_in, n_out):
    """Area-resample weights: for each output index, [(input index, weight 0..65536)]."""
    scale = n_in / float(n_out)
    rows = []
    for o in range(n_out):
        a, b = o * scale, (o + 1) * scale
        lst = []
        i = int(math.floor(a))
        while i < b and i < n_in:
            lo, hi = max(a, i), min(b, i + 1)
            if hi > lo:
                lst.append((i, hi - lo))
            i += 1
        tot = sum(wt for _, wt in lst)
        ints = [(i, int(round(wt / tot * 65536))) for i, wt in lst]
        drift = 65536 - sum(wt for _, wt in ints)
        j = max(range(len(ints)), key=lambda k: ints[k][1])
        ints[j] = (ints[j][0], ints[j][1] + drift)
        rows.append(ints)
    return rows


def resample(img, W, H):
    """Separable area resample to any size (fixed-point weights; deterministic)."""
    c = img.c
    wx, wy = _weights(img.w, W), _weights(img.h, H)
    tmp = [0] * (W * img.h * c)
    src = img.px
    for y in range(img.h):
        base = y * img.w * c
        ob = y * W * c
        for x, taps in enumerate(wx):
            for k in range(c):
                s = 0
                for i, wt in taps:
                    s += src[base + i * c + k] * wt
                tmp[ob + x * c + k] = s
    out = bytearray(W * H * c)
    for y, taps in enumerate(wy):
        ob = y * W * c
        for x in range(W * c):
            s = 0
            for i, wt in taps:
                s += tmp[i * W * c + x] * wt
            out[ob + x] = max(0, min(255, (s + (1 << 31)) >> 32))
    return Img(W, H, c, out)


def crop(img, x, y, w, h):
    c = img.c
    out = bytearray(w * h * c)
    for yy in range(h):
        o = ((y + yy) * img.w + x) * c
        out[yy * w * c:(yy + 1) * w * c] = img.px[o:o + w * c]
    return Img(w, h, c, out)


def crop_aspect(img, aspect):
    """Centre crop to an aspect ratio (w/h)."""
    if img.w / float(img.h) > aspect:
        w = int(round(img.h * aspect))
        return crop(img, (img.w - w) // 2, 0, w, img.h)
    h = int(round(img.w / aspect))
    return crop(img, 0, (img.h - h) // 2, img.w, h)


# ------------------------------------------------------------------ grade, vignette, scrim
def grade(img, contrast=1.0, lift=0.0, saturation=1.0):
    """Per-channel contrast about mid grey and a black lift (one LUT through bytes.translate), then saturation."""
    lut = bytes(max(0, min(255, int(round((((v / 255.0) - 0.5) * contrast + 0.5) * (1.0 - lift) * 255.0 + lift * 255.0))))
                for v in range(256))
    if img.c == 3:
        img.px = bytearray(bytes(img.px).translate(lut))
    else:
        px = img.px
        for i in range(0, len(px), 4):
            px[i] = lut[px[i]]
            px[i + 1] = lut[px[i + 1]]
            px[i + 2] = lut[px[i + 2]]
    if abs(saturation - 1.0) > 1e-6:
        s = int(round(saturation * 1024))
        px, c = img.px, img.c
        for i in range(0, len(px), c):
            r, g, b = px[i], px[i + 1], px[i + 2]
            l = (299 * r + 587 * g + 114 * b) // 1000
            px[i] = max(0, min(255, l + ((r - l) * s >> 10)))
            px[i + 1] = max(0, min(255, l + ((g - l) * s >> 10)))
            px[i + 2] = max(0, min(255, l + ((b - l) * s >> 10)))
    return img


def vignette(img, amount):
    """Darken toward the corners: factor 1 - amount * r^2.4 on an ellipse fitted to the frame."""
    if amount <= 0:
        return img
    w, h, c, px = img.w, img.h, img.c, img.px
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    fy = [((y - cy) / cy) ** 2 for y in range(h)]
    fx = [((x - cx) / cx) ** 2 for x in range(w)]
    for y in range(h):
        o = y * w * c
        ry = fy[y]
        for x in range(w):
            r2 = (fx[x] + ry) / 2.0
            f = int(round((1.0 - amount * (r2 ** 1.2)) * 1024))
            if f >= 1024:
                continue
            i = o + x * c
            px[i] = px[i] * f >> 10
            px[i + 1] = px[i + 1] * f >> 10
            px[i + 2] = px[i + 2] * f >> 10
    return img


def scrim(img, y0, y1, strength, colour, fade_down=True):
    """Soft darkening band (title readability) between rows y0..y1, strongest at the edge of the frame."""
    if strength <= 0 or y1 <= y0:
        return img
    w, c, px = img.w, img.c, img.px
    cr, cg, cb = colour
    span = float(y1 - y0)
    for y in range(max(0, y0), min(img.h, y1)):
        t = (y - y0) / span
        a = strength * ((1.0 - t) if fade_down else t) ** 1.6
        ai = int(round(a * 1024))
        if ai <= 0:
            continue
        o = y * w * c
        for x in range(w):
            i = o + x * c
            px[i] = px[i] + ((cr - px[i]) * ai >> 10)
            px[i + 1] = px[i + 1] + ((cg - px[i + 1]) * ai >> 10)
            px[i + 2] = px[i + 2] + ((cb - px[i + 2]) * ai >> 10)
    return img


# ------------------------------------------------------------------ masks
def scale_mask(w, h, m, k):
    W, H = w * k, h * k
    out = bytearray(W * H)
    for y in range(h):
        row = bytearray()
        for x in range(w):
            row += bytes((m[y * w + x],)) * k
        for yy in range(k):
            out[(y * k + yy) * W:(y * k + yy + 1) * W] = row
    return W, H, out


def pad_mask(w, h, m, p):
    W, H = w + 2 * p, h + 2 * p
    out = bytearray(W * H)
    for y in range(h):
        out[(y + p) * W + p:(y + p) * W + p + w] = m[y * w:(y + 1) * w]
    return W, H, out


def dilate(w, h, m, r):
    """Square dilation by r pixels (prefix sums; O(w*h))."""
    if r <= 0:
        return bytearray(m)
    tmp = bytearray(w * h)
    for y in range(h):
        acc = [0] * (w + 1)
        s = 0
        base = y * w
        for x in range(w):
            s += m[base + x]
            acc[x + 1] = s
        for x in range(w):
            if acc[min(w, x + r + 1)] - acc[max(0, x - r)]:
                tmp[base + x] = 1
    out = bytearray(w * h)
    for x in range(w):
        acc = [0] * (h + 1)
        s = 0
        for y in range(h):
            s += tmp[y * w + x]
            acc[y + 1] = s
        for y in range(h):
            if acc[min(h, y + r + 1)] - acc[max(0, y - r)]:
                out[y * w + x] = 1
    return out


def shift(w, h, m, dx, dy):
    """Mask translated by (dx, dy), cells shifted in from outside are 0 (row slices)."""
    out = bytearray(w * h)
    for y in range(h):
        sy = y - dy
        if not 0 <= sy < h:
            continue
        x0, x1 = max(0, dx), min(w, w + dx)
        if x1 <= x0:
            continue
        row = bytes(1 if v else 0 for v in m[sy * w + x0 - dx:sy * w + x1 - dx])
        out[y * w + x0:y * w + x1] = row
    return out


_RUN = re.compile(rb'[^\x00]+')


def stamp(img, ox, oy, w, h, m, rgb, alpha=1.0):
    """Paint rgb where mask is set (alpha 0..1) at offset (ox, oy). Walks runs of set mask cells per row (same
    per-pixel arithmetic as a full scan; zero cells are skipped wholesale)."""
    a = int(round(alpha * 1024))
    c, px = img.c, img.px
    r, g, b = rgb
    solid = bytes((r, g, b))
    mb = bytes(m)
    for y in range(h):
        ty = oy + y
        if not 0 <= ty < img.h:
            continue
        mrow = y * w
        for run in _RUN.finditer(mb, mrow, mrow + w):
            x0 = max(run.start() - mrow + ox, 0)
            x1 = min(run.end() - mrow + ox, img.w)
            if x1 <= x0:
                continue
            base = (ty * img.w + x0) * c
            if a >= 1024 and c == 3:
                px[base:base + 3 * (x1 - x0)] = solid * (x1 - x0)
                continue
            for tx in range(x0, x1):
                i = (ty * img.w + tx) * c
                if a >= 1024:
                    px[i], px[i + 1], px[i + 2] = r, g, b
                else:
                    px[i] = px[i] + ((r - px[i]) * a >> 10)
                    px[i + 1] = px[i + 1] + ((g - px[i + 1]) * a >> 10)
                    px[i + 2] = px[i + 2] + ((b - px[i + 2]) * a >> 10)
                if c == 4:
                    px[i + 3] = max(px[i + 3], min(255, a * 255 >> 10))


# ------------------------------------------------------------------ title logotype
SIZE_FRAC = {'xl': 0.9, 'l': 0.76, 'm': 0.62}


def title_layout(text, letter, size, safe_w, max_h, k_floor):
    """Pick lines + integer scale k for the logotype.

    Candidates: the one-line title and every two-line split at a word boundary. A candidate's height includes the
    logotype rings and extrude for its own k. Preference: the largest k that fits the width target and max_h; among
    equal k, fewer lines, then the most balanced split. If no candidate reaches the legibility floor k_floor inside
    max_h, the floor wins over max_h (a taller title band beats unreadable 9 px letters) as long as the width fits."""
    target = safe_w * SIZE_FRAC[size]
    words = text.split(' ')
    options = [[text]] + [[' '.join(words[:i]), ' '.join(words[i:])] for i in range(1, len(words))]

    def block_h(bh, k):
        r = logo_rings(k)
        return bh * k + 2 * sum(r[:3]) + r[3]

    best = None
    for lines in options:
        bw, bh, _ = cover_font.text_mask(lines, letter)
        k = int(target // bw)
        while k > 1 and block_h(bh, k) > max_h:
            k -= 1
        k = max(1, k)
        if k < k_floor and bw * k_floor <= safe_w and block_h(bh, k_floor) <= max_h:
            k = k_floor   # the size target is soft; the safe width and the title band are hard
        widths = [cover_font.line_mask(t, letter)[0] for t in lines]
        balance = min(widths) / float(max(widths))
        score = (k, -len(lines), balance)
        if best is None or score > best[0]:
            best = (score, lines, k)
    lines, k = best[1], best[2]
    if k < k_floor:
        for lines2 in sorted(options, key=lambda ls: cover_font.text_mask(ls, letter)[0]):
            bw, bh, _ = cover_font.text_mask(lines2, letter)
            if bw * k_floor <= safe_w:
                return lines2, k_floor
    return lines, max(1, k)


def logo_rings(k):
    """Ring widths (inner ink line, light plate, outer ink) and extrude depth for an integer letter scale k."""
    r1 = max(1, k // 3)
    r2 = max(1, (k + 1) // 2)
    r3 = max(1, k // 3)
    ex = max(2, int(round(k * 0.9)))
    return r1, r2, r3, ex


def draw_title(img, title, region, k_floor, align='center'):
    """region = (x, y, w, h) safe box for the title block. Returns the block's bounding box.

    Logotype layers (bottom to top): offset drop shadow, solid extrude, outer ink ring, light plate ring (joins the
    letters into one sticker-like plate), inner ink line, then the letters in a three-step vertical gradient
    (light cap, fill, accent base) with a one-pixel bevel on stroke tops."""
    letter = title['letter']
    text = title['text'].upper()
    rx, ry, rw, rh = region
    lines, k = title_layout(text, letter, title['size'], rw, rh, k_floor)
    bw, bh, base = cover_font.text_mask(lines, letter, align='center')
    W, H, m = scale_mask(bw, bh, base, k)
    r1, r2, r3, ex = logo_rings(k)
    ring = r1 + r2 + r3
    pad = ring + ex + 2
    W, H, m = pad_mask(W, H, m, pad)
    inner = dilate(W, H, m, r1)
    plate = dilate(W, H, m, r1 + r2)
    outer = dilate(W, H, m, ring)
    extrude = bytearray(W * H)
    for d in range(1, ex + 1):
        sh = shift(W, H, outer, (d + 1) // 2, d)
        for i in range(W * H):
            if sh[i]:
                extrude[i] = 1
    shadow = shift(W, H, outer, ex // 2 + 2, ex + 2)
    ox = rx + (rw - W) // 2 if align == 'center' else rx - pad
    block_h = bh * k + 2 * ring + ex
    oy = ry - pad + ring + (0 if title['placement'] == 'top' else max(0, rh - block_h))
    fill, fill2 = hex_rgb(title['fill']), hex_rgb(title['fill2'])
    out_c, sh_c = hex_rgb(title['outline']), hex_rgb(title['shadow'])
    plate_c = mix(fill, (255, 255, 255), 0.6)
    stamp(img, ox, oy, W, H, shadow, sh_c, 0.5)
    stamp(img, ox, oy, W, H, extrude, mix(out_c, sh_c, 0.4))
    stamp(img, ox, oy, W, H, outer, out_c)
    stamp(img, ox, oy, W, H, plate, plate_c)
    stamp(img, ox, oy, W, H, inner, out_c)
    lh = (cover_font.text_mask([lines[0]], letter)[1]) * k
    gap = cover_font.LINE_GAP * k
    cap_c = mix(fill, (255, 255, 255), 0.4)
    mid_c = mix(fill, fill2, 0.45)
    for y in range(H):
        ly = y - pad
        if ly < 0 or ly >= bh * k:
            continue
        t = (ly % (lh + gap)) / float(lh)
        colour = cap_c if t < 0.3 else (mid_c if t < 0.58 else fill2)
        row = y * W
        for x in range(W):
            if m[row + x]:
                bevel = not m[row - W + x]
                cc = mix(colour, (255, 255, 255), 0.6) if bevel else colour
                tx, ty = ox + x, oy + y
                if 0 <= tx < img.w and 0 <= ty < img.h:
                    i = (ty * img.w + tx) * img.c
                    img.px[i], img.px[i + 1], img.px[i + 2] = cc
                    if img.c == 4:
                        img.px[i + 3] = 255
    return {'x': ox + pad - ring, 'y': oy + pad - ring, 'w': W - 2 * pad + 2 * ring + ex, 'h': block_h,
            'k': k, 'lines': lines}


def draw_subtitle(img, text, x, y, w, colour, ink, s):
    if not text:
        return
    mw, mh, m = cover_font.small_mask(text)
    W, H, mm = scale_mask(mw, mh, m, s)
    ox = x + (w - W) // 2
    stamp(img, ox + s, y + s, W, H, mm, ink, 0.8)
    stamp(img, ox, y, W, H, mm, colour)


# ------------------------------------------------------------------ band + mark
def draw_band(img, edge, colour, label, unit):
    """Style band along an edge in the style colour, with a highlight line, an ink line and the style label."""
    if edge == 'none':
        return None
    col = hex_rgb(colour)
    ink = (10, 12, 24)
    t = max(6, int(round(unit * 0.052)))
    if edge == 'bottom':
        x0, y0, x1, y1 = 0, img.h - t, img.w, img.h
    elif edge == 'top':
        x0, y0, x1, y1 = 0, 0, img.w, t
    elif edge == 'left':
        x0, y0, x1, y1 = 0, 0, t, img.h
    else:
        x0, y0, x1, y1 = img.w - t, 0, img.w, img.h
    c, px = img.c, img.px
    hl = mix(col, (255, 255, 255), 0.55)
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * img.w + x) * c
            inner = (edge == 'bottom' and y == y0) or (edge == 'top' and y == y1 - 1) or \
                    (edge == 'left' and x == x1 - 1) or (edge == 'right' and x == x0)
            cc = hl if inner else col
            px[i], px[i + 1], px[i + 2] = cc
            if c == 4:
                px[i + 3] = 255
    # thin ink line between band and art
    for y in range(img.h):
        for x in range(img.w):
            on = (edge == 'bottom' and y == y0 - 1) or (edge == 'top' and y == y1) or \
                 (edge == 'left' and x == x1) or (edge == 'right' and x == x0 - 1)
            if on:
                i = (y * img.w + x) * c
                px[i] = (px[i] + ink[0]) // 2
                px[i + 1] = (px[i + 1] + ink[1]) // 2
                px[i + 2] = (px[i + 2] + ink[2]) // 2
    # label in the small face, scaled to the band thickness
    lab_c = (255, 255, 255) if luma(col) < 0.62 else ink
    s = max(1, (t - 2) // 6)
    mw, mh, m = cover_font.small_mask(label.upper())
    W, H, mm = scale_mask(mw, mh, m, s)
    if edge in ('bottom', 'top'):
        ox = x0 + max(2, t // 2)
        oy = y0 + (t - H) // 2 + (1 if edge == 'bottom' else 0)
        stamp(img, ox, oy, W, H, mm, lab_c)
    else:
        # vertical label reading bottom-to-top
        rot = bytearray(H * W)
        for y in range(H):
            for x in range(W):
                if mm[y * W + x]:
                    rot[(W - 1 - x) * H + y] = 1
        ox = x0 + (t - H) // 2 + (1 if edge == 'left' else 0)
        oy = img.h - W - max(4, t // 2)
        stamp(img, ox, oy, H, W, rot, lab_c)
    return {'edge': edge, 'thickness': t, 'box': [x0, y0, x1 - x0, y1 - y0]}


def mark_mask(size):
    """Original corner mark: a disc with a four-point star cut-out, as (fill mask, star mask) at `size` px."""
    disc = bytearray(size * size)
    star = bytearray(size * size)
    c = (size - 1) / 2.0
    R = size / 2.0
    for y in range(size):
        for x in range(size):
            dx, dy = x - c, y - c
            if dx * dx + dy * dy <= (R - 0.25) ** 2:
                disc[y * size + x] = 1
                ax, ay = abs(dx) / (R * 0.82), abs(dy) / (R * 0.82)
                if ax ** 0.55 + ay ** 0.55 <= 1.0:
                    star[y * size + x] = 1
    return disc, star


def draw_mark(img, x, y, size, band_hex):
    """Corner mark: ink ring, style-colour disc, white four-point star (all original geometry)."""
    size = max(7, size)
    disc, star = mark_mask(size)
    ring = dilate(size + 2, size + 2, pad_mask(size, size, disc, 1)[2], 1)
    stamp(img, x - 1 + 1, y - 1 + 1, size + 2, size + 2, ring, (6, 8, 20), 0.5)
    stamp(img, x - 1, y - 1, size + 2, size + 2, ring, (10, 12, 26))
    stamp(img, x, y, size, size, disc, hex_rgb(band_hex))
    stamp(img, x, y, size, size, star, (255, 255, 255))
    return {'x': x, 'y': y, 'size': size}


# ------------------------------------------------------------------ compose
def compose(art, scene, kind, style_label):
    """Finish one export: art = Img already at the export size."""
    img = art.copy()
    fin, title = scene['finish'], scene['title']
    grade(img, contrast=fin['contrast'], lift=fin['lift'], saturation=fin['saturation'])
    vignette(img, fin['vignette'])
    unit = min(img.w, int(img.h * 245 / 170.0))
    k_floor = EXPORTS[kind][3]
    edge = fin['band_edge']
    band_t = max(6, int(round(unit * 0.052))) if edge != 'none' else 0
    margin = max(4, int(round(unit * 0.035)))
    safe = [margin, margin, img.w - 2 * margin, img.h - 2 * margin]
    if edge == 'left':
        safe[0] += band_t
        safe[2] -= band_t
    elif edge == 'right':
        safe[2] -= band_t
    elif edge == 'bottom':
        safe[3] -= band_t
    elif edge == 'top':
        safe[1] += band_t
        safe[3] -= band_t
    # title block height cap (letters + rings + extrude): short titles stay bold without burying the art
    max_h = int(img.h * {'box-1x': 0.25, 'box-2x': 0.24, 'banner': 0.3, 'square': 0.2}[kind])
    # scrim behind the title zone: the title colour's opposite (dark ink) at low strength
    ink = hex_rgb(title['shadow'])
    zone = int(img.h * 0.34)
    if title['placement'] == 'top':
        scrim(img, 0, zone, 0.26, ink, fade_down=True)
        region = (safe[0], safe[1], safe[2], max_h)
    else:
        scrim(img, img.h - zone - band_t, img.h - band_t, 0.3, ink, fade_down=False)
        region = (safe[0], safe[1] + safe[3] - max_h, safe[2], max_h)
    box = draw_title(img, title, region, k_floor)
    if title.get('subtitle'):
        s = max(1, box['k'] // 2)
        sy = box['y'] + box['h'] + s * 2 if title['placement'] == 'top' else box['y'] - 7 * s
        draw_subtitle(img, title['subtitle'], safe[0], sy, safe[2], hex_rgb(title['fill']), hex_rgb(title['outline']), s)
    band = draw_band(img, edge, scene['style']['band'], style_label, unit)
    mark = None
    if fin['mark']:
        ms = max(9, int(round(unit * 0.075)))
        if edge == 'bottom':
            mx, my = img.w - margin - ms, img.h - band_t - ms - max(3, margin // 2)
        elif edge == 'left':
            mx, my = (band_t - ms) // 2 if ms < band_t else band_t + margin // 2, margin
        else:
            mx, my = img.w - margin - ms - (band_t if edge == 'right' else 0), img.h - margin - ms
        if title['placement'] == 'bottom' and edge != 'left':
            my = margin
        mark = draw_mark(img, mx, my, ms, scene['style']['band'])
    return img, {'title': box, 'band': band, 'mark': mark}


def studio_art(card):
    """Title-free art for the Studio cartridge window (2x of 220x154): centre crop to its aspect + area resample."""
    return resample(crop_aspect(card, STUDIO_ART[0] / float(STUDIO_ART[1])), STUDIO_ART[0], STUDIO_ART[1])


def card_alpha(box2x):
    """Transparent-edged card: the 2x box with stepped rounded corners, an ink border and a soft drop shadow."""
    l, t, r, b = ALPHA_PAD
    W, H = box2x.w + l + r, box2x.h + t + b
    out = Img(W, H, 4)
    rad = 10

    def inside(x, y, w, h, radius):
        cx = min(max(x, radius), w - 1 - radius)
        cy = min(max(y, radius), h - 1 - radius)
        return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
    # shadow: offset, 3 alpha steps (pixel-art soft shadow)
    for step, (off, alpha) in enumerate(((10, 40), (7, 60), (4, 90))):
        for y in range(box2x.h):
            for x in range(box2x.w):
                if not inside(x, y, box2x.w, box2x.h, rad):
                    continue
                tx, ty = x + l + off - 2, y + t + off
                if 0 <= tx < W and 0 <= ty < H:
                    i = (ty * W + tx) * 4
                    out.px[i + 3] = max(out.px[i + 3], alpha)
    for y in range(box2x.h):
        for x in range(box2x.w):
            if not inside(x, y, box2x.w, box2x.h, rad):
                continue
            border = not inside(x - 2, y - 2, box2x.w - 4, box2x.h - 4, rad - 2)
            si = (y * box2x.w + x) * 3
            rgb = (12, 14, 28) if border else tuple(box2x.px[si:si + 3])
            i = ((y + t) * W + x + l) * 4
            out.px[i], out.px[i + 1], out.px[i + 2], out.px[i + 3] = rgb[0], rgb[1], rgb[2], 255
    return out


def finish_all(renders, scene, out_dir, prefix, style_label):
    """renders: {'card': path, 'banner': path, 'square': path} -> written exports {name: {path, sha256, size}}."""
    import hashlib
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    layout = {}
    src = {k: load(v) for k, v in renders.items() if v}

    def put(name, img):
        p = out_dir / ('%s-%s.png' % (prefix, name))
        data = save(img, p)
        written[name] = {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'size': [img.w, img.h], 'channels': img.c}
    if 'card' in src:
        card = src['card']
        one = box_down(card, card.w // 245) if card.w % 245 == 0 else resample(card, 245, 170)
        two = box_down(card, card.w // 490) if card.w % 490 == 0 else resample(card, 490, 340)
        b1, layout['box-1x'] = compose(one, scene, 'box-1x', style_label)
        b2, layout['box-2x'] = compose(two, scene, 'box-2x', style_label)
        put('box-1x', b1)
        put('box-2x', b2)
        put('card-alpha', card_alpha(b2))
        put('studio-art', studio_art(card))
    for name in ('banner', 'square'):
        if name in src:
            img, layout[name] = compose(src[name], scene, name, style_label)
            put(name, img)
    return written, layout
