"""Palette utilities: hex/sRGB/linear, nearest colour, LUT (2.0.0 layout), Bayer dithering."""
import numpy as np

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float64) / 16.0 + 1.0 / 32.0


def hex_to_rgb8(h):
    h = h.lstrip("#")
    if len(h) != 6:
        raise ValueError("bad colour %r" % h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb8_to_hex(c):
    return "#%02x%02x%02x" % tuple(int(x) for x in c[:3])


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


class Palette:
    def __init__(self, colors, names):
        if len(colors) != len(names):
            raise ValueError("palette colours/names length mismatch")
        if len(colors) > 32:
            raise ValueError("palette has %d colours (> 32)" % len(colors))
        if len(set(names)) != len(names):
            raise ValueError("duplicate palette names")
        self.hex = [c.lower() for c in colors]
        self.names = list(names)
        self.rgb8 = np.array([hex_to_rgb8(c) for c in self.hex], dtype=np.int64)
        self.index = {n: i for i, n in enumerate(self.names)}

    def idx(self, name_or_index):
        if isinstance(name_or_index, int):
            if not 0 <= name_or_index < len(self.hex):
                raise ValueError("palette index out of range: %r" % name_or_index)
            return name_or_index
        if name_or_index not in self.index:
            raise ValueError("unknown palette colour %r" % name_or_index)
        return self.index[name_or_index]

    def rgb(self, name):
        return tuple(int(x) for x in self.rgb8[self.idx(name)])

    def ramp_rgb(self, names):
        return np.array([self.rgb8[self.idx(n)] for n in names], dtype=np.int64)

    def nearest_index(self, rgb8_array):
        a = np.asarray(rgb8_array, dtype=np.int64).reshape(-1, 3)
        # perceptual-ish weights
        w = np.array([3, 4, 2], dtype=np.int64)
        d = (((a[:, None, :] - self.rgb8[None, :, :]) ** 2) * w).sum(-1)
        return d.argmin(1)

    def contains_rgb8(self, rgb8_array, tol=0):
        a = np.asarray(rgb8_array, dtype=np.int64).reshape(-1, 3)
        d = np.abs(a[:, None, :] - self.rgb8[None, :, :]).max(-1)
        return d.min(1) <= tol

    def lut16(self):
        """256x16 RGB: x = b*16 + r, y = g (4-bit sRGB) -> nearest palette colour."""
        out = np.zeros((16, 256, 3), dtype=np.uint8)
        lv = np.round(np.arange(16) * 255.0 / 15.0).astype(np.int64)
        for g in range(16):
            rr, bb = np.meshgrid(np.arange(16), np.arange(16))  # bb rows, rr cols
            rgb = np.stack([lv[rr.ravel()], np.full(256, lv[g]), lv[bb.ravel()]], 1)
            idx = self.nearest_index(rgb)
            cols = self.rgb8[idx].astype(np.uint8)
            xs = bb.ravel() * 16 + rr.ravel()
            out[g, xs] = cols
        return out


def mottle_thresholds(rs, h, w, clump=1):
    """Irregular dither thresholds (uniform in (0, 1), tileable): seeded white noise, optionally clumped by `clump`
    wrapped blur passes, then rank-equalised so the mean colour is unbiased. Band boundaries become irregular painted
    mottles instead of the regular 4x4 Bayer grid."""
    t = rs.random((h, w))
    for _ in range(int(clump)):
        hh = (np.roll(t, 1, 1) + 2.0 * t + np.roll(t, -1, 1)) / 4.0
        t = (np.roll(hh, 1, 0) + 2.0 * hh + np.roll(hh, -1, 0)) / 4.0
    order = np.argsort(t, axis=None, kind="stable")
    ranks = np.empty(h * w, dtype=np.float64)
    ranks[order] = (np.arange(h * w) + 0.5) / (h * w)
    return ranks.reshape(h, w)


def quantize_field(field, ramp_rgb8, dither: "bool | float" = True, ox=0, oy=0, thresholds=None):
    """Map a float field in [0,1] (H,W) onto ramp colours (darkest first) with 4x4 Bayer dithering.

    dither: True/1.0 = full ordered dither, False/0 = plain rounding (clean bands), a float in (0, 1) = partial
    dither (the threshold scaled around 0.5): only texels near a band boundary flip. thresholds = optional (H, W)
    array in (0, 1) used instead of the Bayer matrix (irregular mottle, see mottle_thresholds)."""
    f = np.clip(np.asarray(field, dtype=np.float64), 0.0, 1.0)
    h, w = f.shape
    n = len(ramp_rgb8)
    amount = 1.0 if dither is True else (0.0 if dither is False or dither is None else float(dither))
    if n == 1:
        idx = np.zeros((h, w), dtype=np.int64)
    else:
        x = f * (n - 1)
        if amount > 0.0:
            if thresholds is not None:
                t = np.asarray(thresholds, dtype=np.float64)
            else:
                yy, xx = np.mgrid[0:h, 0:w]
                t = BAYER4[(yy + oy) % 4, (xx + ox) % 4]
            idx = np.floor(x + 0.5 + (t - 0.5) * amount).astype(np.int64)
        else:
            idx = np.floor(x + 0.5).astype(np.int64)
        idx = np.clip(idx, 0, n - 1)
    return np.asarray(ramp_rgb8, dtype=np.uint8)[idx]
