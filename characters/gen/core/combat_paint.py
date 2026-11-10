"""Painted-gradient helpers for combat art (lane-combat-art). numpy only.

Painter(pack, roles, w, h): ramps are built from role colours plus the pack palette colours that lie between them
(near the RGB segment, sorted along it), and painted with 4x4 ordered dithering between neighbouring ramp steps -
the N64 look: few palette colours, soft painted value changes once bilinear filtering blends the dither. Output
is always quantised to the pack palette by the caller.
"""
import numpy as np

from . import paint as P0

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], float) / 16. + 1. / 32.


def _hue_sat(c):
    c = np.asarray(c, float) / 255.
    mx, mn = c.max(), c.min(); d = mx - mn
    if d < 1e-6:
        return 0., 0.
    r, g, b = c
    h = ((g - b) / d) % 6 if mx == r else ((b - r) / d + 2 if mx == g else (r - g) / d + 4)
    return h * 60., d / max(mx, 1e-6)


def _hue_ok(c, p, tol):
    hc, sc = _hue_sat(c); hp, sp = _hue_sat(p)
    if sc < .18 or sp < .18:
        return True                  # greys: hue meaningless
    return abs(((hc - hp) + 180.) % 360. - 180.) <= tol


class Painter:
    def __init__(self, pack, roles, w, h):
        self.pack = pack; self.roles = roles; self.w = w; self.h = h
        self.pal = P0.palette(pack).astype(float)
        y, x = np.mgrid[0:h, 0:w]
        self.bayer = BAYER[y % 4, x % 4]

    def rgb(self, role):
        return P0.color(self.pack, self.roles[role]).astype(float)

    def ramp(self, *roles, between=True, tol=22., hue_tol=28.):
        """Ordered RGB steps from the first role to the last, with in-between palette colours. A palette colour joins
        the ramp only if it lies near the RGB segment (tol) AND, when it is saturated, near the hue of the segment
        point it projects to (hue_tol degrees) - so a dark brown ramp never picks up a dark green step."""
        stops = [self.rgb(r) for r in roles]
        out = [stops[0]]
        for a, b in zip(stops[:-1], stops[1:]):
            seg = b - a; L2 = float((seg ** 2).sum())
            mids = []
            if between and L2 > 1.:
                for c in self.pal:
                    t = float(((c - a) * seg).sum()) / L2
                    if .08 < t < .92:
                        p = a + t * seg
                        d = np.sqrt(((p - c) ** 2).sum())
                        if d < tol and _hue_ok(c, p, hue_tol):
                            mids.append((t, c))
            for t, c in sorted(mids, key=lambda q: q[0]):
                if not any(np.allclose(c, o) for o in out):
                    out.append(c)
            if not any(np.allclose(b, o) for o in out):
                out.append(b)
        return np.array(out)

    def paint_ramp(self, ramp, val):
        """val (h, w) in 0..1 -> RGB (h, w, 3), dithered between neighbouring ramp steps."""
        val = np.clip(np.asarray(val, float), 0., .9999)
        pos = val * (len(ramp) - 1)
        lo = np.floor(pos).astype(int); fr = pos - lo
        hi = np.minimum(lo + 1, len(ramp) - 1)
        pick = np.where(fr > self.bayer, hi, lo)
        return ramp[pick]
