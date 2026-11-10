"""Image measurement core (numpy; runs inside Blender's Python). No bpy here, so it is unit-testable.

Input images are float arrays (H, W, 4) of straight-alpha sRGB values in [0,1], rows TOP-DOWN.
Everything returned is plain numbers/lists rounded for deterministic JSON. No pixels are returned."""
import numpy as np

ANALYSIS_MAX_SIDE = 160
KMEANS_BOXES = 24
KMEANS_ITERS = 16
MERGE_OK = 0.025
MIN_COVERAGE = 0.003
ACCENT_CHROMA = 0.10
ACCENT_MIN_COVERAGE = 0.0005
R4 = 4  # decimals for OKLab / fractions


class MeasureError(ValueError):
    pass


# ---------------------------------------------------------------- colour (vectorised twins of colour.py)

def srgb_to_lin(a):
    a = np.asarray(a, dtype=np.float64)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(a):
    a = np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M2I = np.array([[1.0, 0.3963377774, 0.2158037573],
                 [1.0, -0.1055613458, -0.0638541728],
                 [1.0, -0.0894841775, -1.2914855480]])
_M1I = np.array([[4.0767416621, -3.3077115913, 0.2309699292],
                 [-1.2684380046, 2.6097574011, -0.3413193965],
                 [-0.0041960863, -0.7034186147, 1.7076147010]])


def _matmul3(a, m):
    # explicit elementwise products (no BLAS) so results are bit-stable across runs
    return np.stack([a[..., 0] * m[i, 0] + a[..., 1] * m[i, 1] + a[..., 2] * m[i, 2] for i in range(3)], axis=-1)


def lin_to_oklab(lin):
    lms = _matmul3(np.asarray(lin, dtype=np.float64), _M1)
    lms = np.cbrt(lms)
    return _matmul3(lms, _M2)


def oklab_to_lin(lab):
    lms = _matmul3(np.asarray(lab, dtype=np.float64), _M2I)
    return _matmul3(lms ** 3, _M1I)


def lab_to_hex(lab):
    lin = np.clip(oklab_to_lin(np.asarray(lab, dtype=np.float64).reshape(1, 3)), 0, 1)
    s = np.round(lin_to_srgb(lin)[0] * 255).astype(int)
    return "#%02x%02x%02x" % tuple(int(x) for x in s)


def rnd(x, d=R4):
    if isinstance(x, (list, tuple, np.ndarray)):
        return [rnd(v, d) for v in x]
    v = float(round(float(x), d))
    return 0.0 if v == 0 else v


def srgb8_to_cielab(rgb8):
    """(..., 3) uint8 sRGB -> CIELAB (D65), vectorised (no BLAS)."""
    lin = srgb_to_lin(np.asarray(rgb8, dtype=np.float64) / 255.0)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = _matmul3(lin, M) / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def de2000_np(lab1, lab2):
    """Vectorised CIEDE2000 (Sharma et al. 2005)."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2)
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2))
    hbp = np.where(C1p * C2p == 0, hs, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


# ---------------------------------------------------------------- geometry helpers

def apply_crop(img, crop):
    if not crop:
        return img
    h, w = img.shape[:2]
    x0, y0, x1, y1 = crop
    c0, c1 = int(np.floor(x0 * w)), int(np.ceil(x1 * w))
    r0, r1 = int(np.floor(y0 * h)), int(np.ceil(y1 * h))
    return img[max(0, r0):min(h, r1), max(0, c0):min(w, c1)]


def exclusion_mask(h, w, boxes):
    m = np.ones((h, w), dtype=bool)
    for x0, y0, x1, y1 in boxes or ():
        m[int(np.floor(y0 * h)):int(np.ceil(y1 * h)), int(np.floor(x0 * w)):int(np.ceil(x1 * w))] = False
    return m


def trim_uniform_edges(img, tol=3.0 / 255.0, max_frac=0.25):
    """Remove letterbox/pillarbox bands: edge rows/cols that are one flat colour. Returns (img, [t,b,l,r])."""
    h, w = img.shape[:2]
    rgb = img[..., :3]

    def flat_row(r):
        return float(np.max(np.abs(r - r[0]))) <= tol

    t = 0
    while t < int(h * max_frac) and flat_row(rgb[t]):
        t += 1
    b = 0
    while b < int(h * max_frac) and flat_row(rgb[h - 1 - b]):
        b += 1
    l = 0
    while l < int(w * max_frac) and flat_row(rgb[:, l]):
        l += 1
    r = 0
    while r < int(w * max_frac) and flat_row(rgb[:, w - 1 - r]):
        r += 1
    # a band only counts when it is at least 2% of the side (a 1-px frame line is not letterbox)
    t = t if t >= 0.02 * h else 0
    b = b if b >= 0.02 * h else 0
    l = l if l >= 0.02 * w else 0
    r = r if r >= 0.02 * w else 0
    return img[t:h - b, l:w - r], [t, b, l, r]


def area_downscale(lin_rgb, alpha, max_side=ANALYSIS_MAX_SIDE):
    """Box-average in linear light to <= max_side (integer bin edges, deterministic).
    Returns (lin (h,w,3), alpha (h,w)). Colour is alpha-weighted."""
    h, w = alpha.shape
    s = max(h, w)
    if s <= max_side:
        return lin_rgb.copy(), alpha.copy()
    oh = max(1, int(round(h * max_side / s)))
    ow = max(1, int(round(w * max_side / s)))
    ys = (np.arange(oh + 1) * h) // oh
    xs = (np.arange(ow + 1) * w) // ow
    wc = lin_rgb * alpha[..., None]

    def box(a):
        c = np.zeros((h + 1, w + 1) + a.shape[2:], dtype=np.float64)
        c[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
        return c[ys[1:]][:, xs[1:]] - c[ys[:-1]][:, xs[1:]] - c[ys[1:]][:, xs[:-1]] + c[ys[:-1]][:, xs[:-1]]

    area = ((ys[1:] - ys[:-1])[:, None] * (xs[1:] - xs[:-1])[None, :]).astype(np.float64)
    asum = box(alpha)
    csum = box(wc)
    a_out = asum / area
    with np.errstate(invalid="ignore", divide="ignore"):
        c_out = np.where(asum[..., None] > 1e-9, csum / np.maximum(asum[..., None], 1e-12), 0.0)
    return c_out, a_out


# ---------------------------------------------------------------- clustering

def _wvar(points, w):
    sw = w.sum()
    if sw <= 0:
        return np.zeros(points.shape[1]), np.zeros(points.shape[1])
    mu = (points * w[:, None]).sum(0) / sw
    var = (((points - mu) ** 2) * w[:, None]).sum(0) / sw
    return mu, var


def median_cut(points, w, k):
    boxes = [np.arange(len(points))]
    while len(boxes) < k:
        best, best_score = -1, 0.0
        for i, idx in enumerate(boxes):
            if len(idx) < 2:
                continue
            _, var = _wvar(points[idx], w[idx])
            score = float(var.max() * w[idx].sum())
            if score > best_score + 1e-15:
                best, best_score = i, score
        if best < 0:
            break
        idx = boxes[best]
        _, var = _wvar(points[idx], w[idx])
        ax = int(np.argmax(var))
        order = idx[np.argsort(points[idx, ax], kind="stable")]
        cw = np.cumsum(w[order])
        cut = int(np.searchsorted(cw, cw[-1] / 2.0))
        cut = min(max(cut, 1), len(order) - 1)
        boxes[best:best + 1] = [order[:cut], order[cut:]]
    cents = []
    for idx in boxes:
        sw = w[idx].sum()
        cents.append((points[idx] * w[idx][:, None]).sum(0) / sw if sw > 0 else points[idx].mean(0))
    return np.array(cents)


def assign(points, cents):
    d = ((points[:, None, :] - cents[None, :, :]) ** 2).sum(-1)
    return np.argmin(d, axis=1)


def kmeans(points, w, cents, iters=KMEANS_ITERS):
    cents = cents.copy()
    for _ in range(iters):
        lab = assign(points, cents)
        for j in range(len(cents)):
            m = lab == j
            sw = w[m].sum()
            if sw > 0:
                cents[j] = (points[m] * w[m][:, None]).sum(0) / sw
    return cents, assign(points, cents)


def merge_close(cents, cov, thr=MERGE_OK):
    cents = [c.copy() for c in cents]
    cov = list(cov)
    while len(cents) > 1:
        best = None
        for i in range(len(cents)):
            for j in range(i + 1, len(cents)):
                d = float(np.sqrt(((cents[i] - cents[j]) ** 2).sum()))
                if d < thr and (best is None or d < best[0]):
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        t = cov[i] + cov[j]
        cents[i] = (cents[i] * cov[i] + cents[j] * cov[j]) / t if t > 0 else cents[i]
        cov[i] = t
        del cents[j]
        del cov[j]
    return np.array(cents), np.array(cov)


# ---------------------------------------------------------------- per-image statistics

def _percentiles(v, w, qs):
    order = np.argsort(v, kind="stable")
    cw = np.cumsum(w[order])
    tot = cw[-1]
    return [float(v[order[min(len(v) - 1, int(np.searchsorted(cw, q * tot)))]]) for q in qs]


def _min_filter(a, r):
    h, w = a.shape
    p = np.pad(a, r, mode="edge")
    out = a.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out = np.minimum(out, p[r + dy:r + dy + h, r + dx:r + dx + w])
    return out


def _local_std(a, r):
    h, w = a.shape
    p = np.pad(a, r, mode="edge")
    s = np.zeros_like(a)
    s2 = np.zeros_like(a)
    n = (2 * r + 1) ** 2
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            v = p[r + dy:r + dy + h, r + dx:r + dx + w]
            s += v
            s2 += v * v
    return np.sqrt(np.maximum(s2 / n - (s / n) ** 2, 0.0))


def image_stats(srgb, lab, wmask, native_srgb):
    """srgb/lab: analysis arrays (h,w,3); wmask (h,w) weights; native_srgb: native-res (H,W,3) for texture stats."""
    h, w = wmask.shape
    L = lab[..., 0]
    C = np.hypot(lab[..., 1], lab[..., 2])
    wf = wmask.ravel()
    sw = wf.sum()
    Lf, Cf = L.ravel(), C.ravel()
    p5, p25, p50, p75, p95 = _percentiles(Lf, wf, (0.05, 0.25, 0.5, 0.75, 0.95))
    muL = float((Lf * wf).sum() / sw)
    rms = float(np.sqrt(((Lf - muL) ** 2 * wf).sum() / sw))
    rg = (srgb[..., 0] - srgb[..., 1]).ravel()
    yb = (0.5 * (srgb[..., 0] + srgb[..., 1]) - srgb[..., 2]).ravel()

    def wstd(v):
        m = (v * wf).sum() / sw
        return float(np.sqrt(((v - m) ** 2 * wf).sum() / sw)), float(m)

    srg, mrg = wstd(rg)
    syb, myb = wstd(yb)
    colourfulness = float(np.sqrt(srg ** 2 + syb ** 2) + 0.3 * np.sqrt(mrg ** 2 + myb ** 2))
    c_mean = float((Cf * wf).sum() / sw)
    c_p90 = _percentiles(Cf, wf, (0.9,))[0]
    hue = (np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0).ravel()
    hh = np.zeros(12)
    bins = np.minimum((hue // 30).astype(int), 11)
    np.add.at(hh, bins, Cf * wf)
    hh = hh / hh.sum() if hh.sum() > 0 else hh
    # vertical structure: weighted row means, Otsu split over rows
    rw = wmask.sum(1)
    rmean = np.where(rw[:, None] > 0, (lab * wmask[..., None]).sum(1) / np.maximum(rw[:, None], 1e-9), 0.0)
    feat = rmean * np.array([1.0, 2.0, 2.0])
    best_s, best_v = h // 2, -1.0
    tot_w = rw.sum()
    gmu = (feat * rw[:, None]).sum(0) / tot_w
    tot_var = float((((feat - gmu) ** 2).sum(1) * rw).sum() / tot_w)
    for s in range(max(1, int(0.15 * h)), max(2, int(0.85 * h))):
        w0, w1 = rw[:s].sum(), rw[s:].sum()
        if w0 <= 0 or w1 <= 0:
            continue
        m0 = (feat[:s] * rw[:s, None]).sum(0) / w0
        m1 = (feat[s:] * rw[s:, None]).sum(0) / w1
        v = float(w0 * w1 / tot_w ** 2 * ((m0 - m1) ** 2).sum())
        if v > best_v + 1e-12:
            best_v, best_s = v, s

    def band_mean(r0, r1):
        m = wmask[r0:r1]
        sm = m.sum()
        if sm <= 0:
            return [0.0, 0.0, 0.0]
        return list((lab[r0:r1] * m[..., None]).sum((0, 1)) / sm)

    t3, b3 = max(1, h // 3), max(1, (2 * h) // 3)
    top, mid, bot = band_mean(0, t3), band_mean(t3, b3), band_mean(b3, h)
    above, below = band_mean(0, best_s), band_mean(best_s, h)
    # the sky band just above the horizon split (what distant geometry fades into by day)
    hb = max(1, h // 10)
    horizon = band_mean(max(0, best_s - hb), best_s) if best_s > 0 else top
    top10 = band_mean(0, max(1, h // 10))
    # haze (dark channel prior on the analysis image)
    dc = _min_filter(srgb.min(axis=2), 2)
    dflat = dc.ravel()
    thr = _percentiles(dflat, wf, (0.995,))[0]
    sel = (dflat >= thr) & (wf > 0)
    A = srgb.reshape(-1, 3)[sel].mean(0) if sel.any() else np.array([1.0, 1.0, 1.0])
    A = np.maximum(A, 0.05)
    tdc = _min_filter((srgb / A[None, None, :]).min(axis=2), 2)
    haze = float(np.clip((tdc.ravel() * wf).sum() / sw, 0.0, 1.0))
    A_lab = lin_to_oklab(srgb_to_lin(A.reshape(1, 3)))[0]
    ls = _local_std(L, 2)
    hr0, hr1 = max(0, best_s - max(1, h // 10)), min(h, best_s + max(1, h // 10))
    br0 = int(0.75 * h)

    def band_ls(r0, r1):
        m = wmask[r0:r1]
        return float((ls[r0:r1] * m).sum() / max(m.sum(), 1e-9))

    falloff = band_ls(hr0, hr1) / max(band_ls(br0, h), 1e-4)
    # shadow / highlight tints
    lo3, lo15, hi90 = _percentiles(Lf, wf, (0.03, 0.15, 0.90))
    labf = lab.reshape(-1, 3)
    m_sh = (Lf >= lo3) & (Lf <= lo15) & (wf > 0)
    shadow = (labf[m_sh] * wf[m_sh, None]).sum(0) / wf[m_sh].sum() if m_sh.any() else labf[np.argmin(Lf)]
    m_hi = (Lf >= hi90) & (Cf <= 0.08) & (wf > 0)
    if m_hi.sum() < max(3, 0.01 * len(Lf)):
        m_hi = (Lf >= hi90) & (wf > 0)
    highlight = (labf[m_hi] * wf[m_hi, None]).sum(0) / wf[m_hi].sum()
    # texture / dithering statistics on a native-resolution centre crop (<= 256 px)
    H, W = native_srgb.shape[:2]
    cs = min(256, H, W)
    y0, x0 = (H - cs) // 2, (W - cs) // 2
    crop = native_srgb[y0:y0 + cs, x0:x0 + cs]
    nl = lin_to_oklab(srgb_to_lin(crop))[..., 0]
    dx = np.abs(np.diff(nl, axis=1))
    flat = float((dx <= 0.002).mean())
    smooth = float(((dx > 0.002) & (dx <= 0.02)).mean())
    edges = float((dx > 0.08).mean())
    if cs >= 4:
        cb = np.abs(nl[:-1, :-1] - nl[1:, :-1] - nl[:-1, 1:] + nl[1:, 1:])
        grad = np.abs(nl[:-1, 1:] - nl[:-1, :-1]) + np.abs(nl[1:, :-1] - nl[:-1, :-1])
        checker = float(cb.mean() / max(grad.mean(), 1e-6))
    else:
        checker = 0.0
    q = np.round(crop * 31).astype(np.int64)
    codes = q[..., 0] * 1024 + q[..., 1] * 32 + q[..., 2]
    distinct5 = int(len(np.unique(codes)))
    return {
        "L": rnd([p5, p25, p50, p75, p95]), "L_mean": rnd(muL), "rms_contrast": rnd(rms),
        "colourfulness": rnd(colourfulness), "chroma_mean": rnd(c_mean), "chroma_p90": rnd(c_p90),
        "hue_hist": rnd(hh.tolist()),
        "vertical": {"split": rnd(best_s / h), "strength": rnd(best_v / tot_var if tot_var > 0 else 0.0),
                     "top": rnd(top), "mid": rnd(mid), "bottom": rnd(bot), "above": rnd(above), "below": rnd(below),
                     "horizon": rnd(horizon), "top10": rnd(top10), "gradient_L": rnd(top[0] - bot[0])},
        "haze": {"airlight": rnd(A_lab.tolist()), "density": rnd(haze), "contrast_falloff": rnd(falloff)},
        "shadow": rnd(list(shadow)), "highlight": rnd(list(highlight)),
        "texture": {"flat": rnd(flat), "smooth": rnd(smooth), "edges": rnd(edges), "checker": rnd(checker),
                    "distinct5": distinct5, "crop_px": int(cs)},
    }


REGION_KEYS = ("walls", "floor", "ceiling", "sky", "ground", "furniture", "soft", "metal", "accent", "foliage",
               "water", "view")


def region_stats(srgba, regions):
    """Robust colour inside each agent-marked box (boxes are in ORIGINAL image coordinates): the mean OKLab of
    the pixels between the 25th and 75th lightness percentile (texture body, not its gaps or glints)."""
    if not regions:
        return {}
    lin_s, alpha_s = area_downscale(srgb_to_lin(srgba[..., :3]), srgba[..., 3])
    lab = lin_to_oklab(lin_s)
    h, w = alpha_s.shape
    out = {}
    for name in sorted(regions):
        x0, y0, x1, y1 = regions[name]
        r0, c0 = int(np.floor(y0 * h)), int(np.floor(x0 * w))
        r1, c1 = max(int(np.ceil(y1 * h)), r0 + 1), max(int(np.ceil(x1 * w)), c0 + 1)
        sub = lab[r0:r1, c0:c1].reshape(-1, 3)
        a = alpha_s[r0:r1, c0:c1].ravel()
        sub = sub[a > 0.5]
        if len(sub) < 4:
            continue
        Lr = sub[:, 0]
        lo, hi = np.percentile(Lr, 25), np.percentile(Lr, 75)
        body = sub[(Lr >= lo) & (Lr <= hi)]
        if len(body) < 2:
            body = sub
        # patterned surfaces (checked rugs, prints): the more colourful half of the region, so a teal pattern on
        # cream reads teal instead of a grey average
        Cr = np.hypot(sub[:, 1], sub[:, 2])
        colourful = sub[Cr >= np.median(Cr)]
        out[name] = {"lab": rnd([float(body[:, 0].mean()), float(body[:, 1].mean()), float(body[:, 2].mean())]),
                     "lab_chroma": rnd([float(colourful[:, 0].mean()), float(colourful[:, 1].mean()),
                                        float(colourful[:, 2].mean())]),
                     "L_p10": rnd(float(np.percentile(Lr, 10))), "L_p90": rnd(float(np.percentile(Lr, 90))),
                     "px": int(len(sub))}
    return out


def zero_variance_reason(srgb, wmask):
    """Return a reason string if the image carries no usable colour information, else None."""
    wf = wmask.ravel() > 0
    if wf.sum() < 16:
        return "fewer than 16 usable pixels after crop/exclusions/alpha"
    px = srgb.reshape(-1, 3)[wf]
    lum = px[:, 0] * 0.2126 + px[:, 1] * 0.7152 + px[:, 2] * 0.0722
    q = np.round(px * 31).astype(np.int64)
    codes = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    u, cnt = np.unique(codes, return_counts=True)
    populated = int((cnt >= max(1, 0.001 * len(codes))).sum())
    if float(lum.std()) < 1.5 / 255.0 and float(px.std(axis=0).max()) < 1.5 / 255.0:
        mean = np.round(px.mean(0) * 255).astype(int)
        return "zero-variance image: every pixel is ~#%02x%02x%02x (std < 1.5/255); nothing to measure" % tuple(mean)
    if populated < 4:
        return "only %d populated colours (need >= 4); a flat or near-single-colour image cannot define a palette" % populated
    return None


# ---------------------------------------------------------------- whole job

def measure(images):
    """images: list of dicts {index, srgba (H,W,4 top-down float), weight, use_palette, crop, exclude}.
    Returns the measurements dict (numbers only)."""
    per, pool_lab, pool_w, pool_band, pool_img = [], [], [], [], []
    for im in images:
        a = apply_crop(im["srgba"], im.get("crop"))
        a, trimmed = trim_uniform_edges(a)
        hN, wN = a.shape[:2]
        if hN < 8 or wN < 8:
            raise MeasureError("reference %d: crop/trim leaves %dx%d px" % (im["index"], wN, hN))
        alpha = a[..., 3] * exclusion_mask(hN, wN, im.get("exclude"))
        lin = srgb_to_lin(a[..., :3])
        lin_s, alpha_s = area_downscale(lin, alpha)
        srgb_s = lin_to_srgb(lin_s)
        lab_s = lin_to_oklab(lin_s)
        reason = zero_variance_reason(srgb_s, alpha_s)
        if reason:
            raise MeasureError("reference %d: %s" % (im["index"], reason))
        st = image_stats(srgb_s, lab_s, alpha_s, a[..., :3])
        h, w = alpha_s.shape
        rows = np.repeat(np.arange(h)[:, None], w, axis=1).ravel()
        # bands relative to this image's own strongest horizontal split (wall/floor indoors, sky/ground
        # outdoors): top = upper 40% of the region above the split, mid = the rest above it, bottom = below.
        # Fixed thirds put the floor into 'mid' for elevated interior cameras.
        sp = min(0.85, max(0.15, st["vertical"]["split"]))
        s_row = max(2, int(round(sp * h)))
        t_row = max(1, int(round(0.4 * s_row)))
        band = np.where(rows < t_row, 0, np.where(rows < s_row, 1, 2))
        st["vertical"]["bands_def"] = {"top_end": rnd(t_row / h), "split": rnd(s_row / h)}
        st["regions"] = region_stats(im["srgba"], im.get("regions"))
        wf = alpha_s.ravel()
        if im.get("use_palette", True) and im.get("weight", 1.0) > 0:
            pool_lab.append(lab_s.reshape(-1, 3))
            pool_w.append(wf / wf.sum() * float(im.get("weight", 1.0)))
            pool_band.append(band)
            pool_img.append(np.full(len(wf), im["index"]))
        per.append({"index": im["index"], "analysed": [int(w), int(h)], "trimmed": trimmed, "stats": st,
                    "_lab": lab_s.reshape(-1, 3), "_w": wf, "_band": band})
    P = np.concatenate(pool_lab)
    Wt = np.concatenate(pool_w)
    B = np.concatenate(pool_band)
    I = np.concatenate(pool_img)
    keep = Wt > 0
    P, Wt, B, I = P[keep], Wt[keep], B[keep], I[keep]
    Wt = Wt / Wt.sum()
    init = median_cut(P, Wt, KMEANS_BOXES)
    cents, lab_idx = kmeans(P, Wt, init)
    cov = np.array([Wt[lab_idx == j].sum() for j in range(len(cents))])
    cents, cov = merge_close(cents, cov)
    lab_idx = assign(P, cents)
    cov = np.array([Wt[lab_idx == j].sum() for j in range(len(cents))])
    clusters = []
    for j in range(len(cents)):
        m = lab_idx == j
        if not m.any():
            continue
        Lc, ac, bc = cents[j]
        chroma = float(np.hypot(ac, bc))
        if cov[j] < MIN_COVERAGE and not (chroma >= ACCENT_CHROMA and cov[j] >= ACCENT_MIN_COVERAGE):
            continue
        bw = np.array([Wt[m & (B == k)].sum() for k in range(3)])
        imgs = sorted(int(x) for x in np.unique(I[m]) if Wt[m & (I == x)].sum() >= 0.002)
        spread = float(np.sqrt((((P[m] - cents[j]) ** 2).sum(1) * Wt[m]).sum() / Wt[m].sum()))
        clusters.append({"hex": lab_to_hex(cents[j]), "lab": rnd(cents[j].tolist()), "coverage": rnd(cov[j]),
                         "chroma": rnd(chroma), "hue": rnd(float(np.degrees(np.arctan2(bc, ac)) % 360.0), 2),
                         "bands": rnd((bw / bw.sum()).tolist()), "images": imgs, "spread": rnd(spread)})
    clusters.sort(key=lambda c: (-c["coverage"], c["hex"]))
    kept = np.array([c["lab"] for c in clusters])
    # per-image band dominants over the kept clusters
    for p in per:
        idx = assign(p["_lab"], kept)
        bands = []
        for k in range(3):
            m = p["_band"] == k
            hist = np.zeros(len(kept))
            np.add.at(hist, idx[m], p["_w"][m])
            tot = hist.sum()
            order = np.argsort(-hist, kind="stable")[:3]
            bands.append([[int(o), rnd(hist[o] / tot if tot > 0 else 0.0)] for o in order if hist[o] > 0])
        hist = np.zeros(len(kept))
        np.add.at(hist, idx, p["_w"])
        p["cluster_share"] = [[int(o), rnd(hist[o] / hist.sum())] for o in np.argsort(-hist, kind="stable")[:10] if hist[o] > 0]
        p["band_clusters"] = {"top": bands[0], "mid": bands[1], "bottom": bands[2]}
        for k in ("_lab", "_w", "_band"):
            del p[k]
    # pooled stats (coverage-weighted means over palette-contributing images)
    pooled = {"clusters": clusters, "n_pixels": int(len(P))}
    return {"references": per, "pooled": pooled,
            "analysis": {"max_side": ANALYSIS_MAX_SIDE, "boxes": KMEANS_BOXES, "iters": KMEANS_ITERS,
                         "merge_ok": MERGE_OK, "min_coverage": MIN_COVERAGE}}
