"""Stdlib colour maths: sRGB <-> linear, OKLab/OKLCh, CIELAB (D65), CIEDE2000, hex, generic hue names.
Pure Python (Python 3.9), deterministic. The Blender measurement side has numpy twins of the OKLab
conversions in measure_np.py; tests check both agree."""
import math

# ---------------------------------------------------------------- hex / sRGB

def hex_to_rgb8(h):
    h = h.lstrip("#")
    if len(h) != 6:
        raise ValueError("bad colour %r" % h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb8_to_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x)))) for x in c[:3])


def srgb_to_lin1(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin_to_srgb1(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb8_to_lin(c):
    return tuple(srgb_to_lin1(x / 255.0) for x in c)


def lin_to_rgb8(c):
    return tuple(int(round(lin_to_srgb1(x) * 255.0)) for x in c)


# ---------------------------------------------------------------- OKLab (Ottosson 2020)

def lin_to_oklab(c):
    r, g, b = c
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l_, m_, s_))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_lin(lab):
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def hex_to_oklab(h):
    return lin_to_oklab(rgb8_to_lin(hex_to_rgb8(h)))


def in_gamut(lin, eps=1e-6):
    return all(-eps <= x <= 1 + eps for x in lin)


def oklab_to_hex(lab):
    """Gamut-map by reducing chroma (keeps L and hue) until the colour fits sRGB, then encode."""
    L, a, b = lab
    L = max(0.0, min(1.0, L))
    lin = oklab_to_lin((L, a, b))
    if not in_gamut(lin):
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if in_gamut(oklab_to_lin((L, a * mid, b * mid))):
                lo = mid
            else:
                hi = mid
        lin = oklab_to_lin((L, a * lo, b * lo))
    return rgb8_to_hex(lin_to_rgb8(tuple(max(0.0, min(1.0, x)) for x in lin)))


def oklch(lab):
    L, a, b = lab
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0
    return L, C, h


def from_oklch(L, C, h):
    r = math.radians(h)
    return (L, C * math.cos(r), C * math.sin(r))


def ok_dist(p, q):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(p, q)))


def ok_mix(p, q, t):
    return tuple(x + (y - x) * t for x, y in zip(p, q))


# ---------------------------------------------------------------- CIELAB / CIEDE2000

_XN, _YN, _ZN = 0.95047, 1.0, 1.08883


def lin_to_xyz(c):
    r, g, b = c
    return (0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
            0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
            0.0193339 * r + 0.1191920 * g + 0.9503041 * b)


def _f(t):
    return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29


def xyz_to_lab(xyz):
    x, y, z = xyz
    fx, fy, fz = _f(x / _XN), _f(y / _YN), _f(z / _ZN)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def rgb8_to_lab(c):
    return xyz_to_lab(lin_to_xyz(rgb8_to_lin(c)))


def hex_to_lab(h):
    return rgb8_to_lab(hex_to_rgb8(h))


def ciede2000(lab1, lab2):
    """CIEDE2000 (Sharma et al. 2005), kL=kC=kH=1."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7))) if Cb > 0 else 0.0
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p > 0 else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p > 0 else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dth = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) if Cbp > 0 else 0.0
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dth)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def de2000_hex(h1, h2):
    return ciede2000(hex_to_lab(h1), hex_to_lab(h2))


# ---------------------------------------------------------------- generic hue names (theme-free)
# OKLCh hue angle bands -> plain colour words (used only to NAME palette ramps).
HUE_WORDS = ((15.0, "rose"), (45.0, "red"), (65.0, "orange"), (85.0, "amber"), (105.0, "yellow"),
             (125.0, "lime"), (160.0, "green"), (185.0, "teal"), (215.0, "cyan"), (245.0, "azure"),
             (275.0, "blue"), (305.0, "indigo"), (330.0, "violet"), (350.0, "magenta"), (360.0, "rose"))


def hue_word(h):
    for edge, word in HUE_WORDS:
        if h < edge:
            return word
    return "rose"


# coarse hue words used by the notes vocabulary -> OKLCh hue centre
NOTE_HUES = {"red": 30.0, "orange": 60.0, "yellow": 100.0, "green": 145.0, "teal": 185.0, "blue": 260.0,
             "purple": 310.0, "pink": 350.0, "brown": 60.0}


def hue_diff(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def contrast_ratio(h1, h2):
    """WCAG relative-luminance contrast ratio between two hex colours."""
    def rl(h):
        r, g, b = rgb8_to_lin(hex_to_rgb8(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    a, b = rl(h1), rl(h2)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
