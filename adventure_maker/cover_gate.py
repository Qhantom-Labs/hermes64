"""Cover gate (stdlib only): measured reasons to reject a staged cover render before it is finished as box art.

Built from the existing gates, applied at the size a cover is judged at (the 245x170 box card, a 4x box downsample
of the 980x680 card render), plus cover-specific composition checks:

  style_gate.image_metrics     palette adherence + accent budget, luma range/black/white points, flatness, detail
  style_gate.exterior_metrics  sky + gradient, near/mid/far depth bands, haze tinted to the horizon (exteriors)
  n64_gate measures            blown-out glare (clip), neon, glow/modern-light energy (noglow/classic passes),
                               fog/horizon match, and pixel-crisp edges on a native-resolution crop (no sharpening)
  cover checks                 a staged subject in view (subject pass coverage), subject separation from its
                               surroundings at card size, brightness for the mood, a calm title zone

Every failure is a readable sentence; thresholds live in COVER_THRESHOLDS (documented in docs/COVER.md) and the
shared convention (kits/core/n64_look.json gate). Known-bad controls (a flat room crop, a blown-out render, an empty
frame) are rejected; nothing here certifies beauty or human taste.
"""
import math
from pathlib import Path

from . import n64_gate, style_gate
from .cover_finish import Img, box_down, load

COVER_THRESHOLDS = {
    # composition
    'subject_coverage_min': 0.035, 'subject_coverage_max': 0.72,
    'subject_contrast_min': 0.07, 'subject_delta_e_min': 14.0,
    'subject_inside_min': 0.85,           # share of the subject's box inside the frame
    # brightness by mood (mean luma at card size) and range
    'mean_luma_min': {'night': 0.24, 'interior': 0.24, 'dusk': 0.30, 'dawn': 0.32, 'day': 0.34},
    'mean_luma_max': 0.80,
    'contrast_range_min': 0.34, 'black_point_max': 0.22,
    # detail / flatness on non-sky pixels at card size
    'flat_fraction_max': 0.55, 'edge_density_min': 0.04, 'edge_density_max': 0.5,
    # colour
    'palette_adherence_min': 0.82, 'accent_fraction_max': 0.18,
    # exteriors (depth + mask passes)
    'sky_fraction_min': 0.06, 'depth_bands_min': 2, 'depth_range_min': 0.05,
    # n64 measures (card size unless noted)
    'clip_fraction_max': 0.02, 'neon_fraction_max': 0.02, 'glow_energy_max': 0.02, 'modern_light_energy_max': 0.006,
    'crisp_edge_fraction_max': 0.45, 'fog_horizon_delta_max': 0.10,
    # title zone (top or bottom 26% of the frame): busy detail behind the logotype hurts legibility
    'title_zone_edge_max': 0.42,
}
CARD = (245, 170)
DEPTH_SCALE = 120.0


def _tuple(img):
    return (img.w, img.h, bytes(img.px))


def _nearest(img, W, H):
    """Nearest sample at block centres (keeps categorical mask colours exact)."""
    out = bytearray(W * H * 3)
    for y in range(H):
        sy = min(img.h - 1, int((y + 0.5) * img.h / H))
        for x in range(W):
            sx = min(img.w - 1, int((x + 0.5) * img.w / W))
            i = (sy * img.w + sx) * 3
            out[(y * W + x) * 3:(y * W + x) * 3 + 3] = img.px[i:i + 3]
    return Img(W, H, 3, out)


def _card(img):
    if (img.w, img.h) == CARD:
        return img
    if img.w % CARD[0] == 0 and img.w // CARD[0] == img.h // CARD[1] and img.h % CARD[1] == 0:
        return box_down(img, img.w // CARD[0])
    from .cover_finish import resample
    return resample(img, CARD[0], CARD[1])


def subject_mask(img):
    """Subject pass: everything that is not the magenta clear colour."""
    px = img.px
    n = img.w * img.h
    m = bytearray(n)
    for i in range(n):
        r, g, b = px[3 * i], px[3 * i + 1], px[3 * i + 2]
        if not (r >= 200 and g <= 60 and b >= 200):
            m[i] = 1
    return m


def _dilate(w, h, m, r):
    from .cover_finish import dilate
    return dilate(w, h, m, r)


def _lab(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(v)) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
    return (116.0 * f(y) - 16.0, 500.0 * (f(x) - f(y)), 200.0 * (f(y) - f(z)))


def subject_metrics(beauty, subj):
    """Coverage, frame containment and separation of the staged subject at card size."""
    w, h, px = beauty.w, beauty.h, beauty.px
    m = subject_mask(subj)
    n = w * h
    cov = sum(m) / float(n)
    out = {'subject_coverage': round(cov, 4)}
    if not any(m):
        out.update(subject_contrast=0.0, subject_delta_e=0.0, subject_inside=0.0)
        return out
    ring = _dilate(w, h, m, 4)
    sl = [0.0, 0.0, 0.0, 0]
    rl = [0.0, 0.0, 0.0, 0]
    edge_touch = 0
    for i in range(n):
        if m[i]:
            sl[0] += px[3 * i]
            sl[1] += px[3 * i + 1]
            sl[2] += px[3 * i + 2]
            sl[3] += 1
            x, y = i % w, i // w
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                edge_touch += 1
        elif ring[i]:
            rl[0] += px[3 * i]
            rl[1] += px[3 * i + 1]
            rl[2] += px[3 * i + 2]
            rl[3] += 1
    smean = [sl[k] / max(1, sl[3]) for k in range(3)]
    rmean = [rl[k] / max(1, rl[3]) for k in range(3)]
    ls = (0.299 * smean[0] + 0.587 * smean[1] + 0.114 * smean[2]) / 255.0
    lr = (0.299 * rmean[0] + 0.587 * rmean[1] + 0.114 * rmean[2]) / 255.0
    a, b = _lab(smean), _lab(rmean)
    out['subject_contrast'] = round(abs(ls - lr), 4)
    out['subject_delta_e'] = round(math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3))), 2)
    # local contrast: per-pixel luma difference across the subject's silhouette edge (what makes it pop)
    lum = [(0.299 * px[3 * i] + 0.587 * px[3 * i + 1] + 0.114 * px[3 * i + 2]) / 255.0 for i in range(n)]
    diffs = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            if not m[i]:
                continue
            for j in (i - 1, i + 1, i - w, i + w):
                if not m[j]:
                    diffs.append(abs(lum[i] - lum[j]))
    diffs.sort()
    out['silhouette_contrast'] = round(diffs[len(diffs) // 2], 4) if diffs else 0.0
    # perimeter touching the frame edge relative to the subject's height: a cut-off subject
    out['subject_inside'] = round(1.0 - min(1.0, edge_touch / max(1.0, math.sqrt(sl[3]) * 2.0)), 4)
    return out


def title_zone_edges(beauty, placement, frac=0.26):
    w, h, px = beauty.w, beauty.h, beauty.px
    y0, y1 = (0, int(h * frac)) if placement == 'top' else (int(h * (1 - frac)), h)
    lum = [(0.299 * px[3 * i] + 0.587 * px[3 * i + 1] + 0.114 * px[3 * i + 2]) / 255.0 for i in range(w * h)]
    e = cnt = 0
    for y in range(max(1, y0), min(h - 1, y1)):
        for x in range(1, w - 1):
            i = y * w + x
            gx = lum[i + 1] - lum[i - 1]
            gy = lum[i + w] - lum[i - w]
            cnt += 1
            if math.sqrt(gx * gx + gy * gy) / 2.0 > 0.07:
                e += 1
    return round(e / max(1, cnt), 4)


def native_crop(img, size=(320, 240)):
    """Centre crop at native render resolution (judges filtering/sharpening, not the downsample)."""
    from .cover_finish import crop
    w, h = min(size[0], img.w), min(size[1], img.h)
    return crop(img, (img.w - w) // 2, (img.h - h) // 2, w, h)


def measure(files, scene, palette, conv=None):
    """files: {'beauty': path, 'subject'?, 'depth'?, 'mask'?, 'noglow'?, 'classic'?} -> metrics (no verdict)."""
    full = load(files['beauty'])
    beauty = _card(full)
    m = {'measured_at': list(CARD), 'render_size': [full.w, full.h]}
    mask = depth = None
    sky = None
    if files.get('mask') and Path(files['mask']).is_file():
        mask = _nearest(load(files['mask']), CARD[0], CARD[1])
        sky = style_gate.sky_mask(_tuple(mask))
    if files.get('depth') and Path(files['depth']).is_file():
        depth = _nearest(load(files['depth']), CARD[0], CARD[1])
    th = dict(style_gate.CORE_DEFAULTS)
    th.update({'palette_hue_tol_deg': 24.0})
    im = style_gate.image_metrics(_tuple(beauty), None, fog_hex(scene), palette, th, exclude=sky)
    for k in ('luma_p2', 'luma_p50', 'luma_p95', 'luma_p995', 'luma_mean', 'contrast_range', 'flat_fraction',
              'edge_density', 'palette_adherence', 'accent_fraction', 'fog_swallowed_fraction'):
        if k in im:
            m[k] = im[k]
    if mask is not None and depth is not None:
        ex = style_gate.exterior_metrics(_tuple(beauty), _tuple(depth), _tuple(mask), DEPTH_SCALE,
                                         dict(th, ext_near_m=8.0, ext_far_m=26.0, ext_band_coverage_min=0.02))
        for k in ('sky_fraction', 'sky_gradient', 'band_count', 'band_range', 'band_min_gap', 'band_near_coverage',
                  'band_mid_coverage', 'band_far_coverage', 'band_far_haze', 'ground_flat_fraction', 'ground_lowfreq'):
            if k in ex:
                m[k] = ex[k]
        hz = n64_gate.horizon_colour(_tuple(beauty), _tuple(mask))
        if hz is not None:
            ex = float(scene['sky'].get('exposure', 1.0))
            f = [c * ex for c in n64_gate.hex_rgb(scene['fog']['color'])]
            m['fog_horizon_delta'] = round(math.sqrt(sum((hz[c] - f[c]) ** 2 for c in range(3)) / 3.0), 4)
    m['clip_fraction'], m['neon_fraction'] = n64_gate.colour_stats(_tuple(beauty))
    m['crisp_edge_fraction'], m['strong_edges'] = n64_gate.crisp_edges(_tuple(native_crop(full)))
    for key, name, pos in (('classic', 'modern_light', False), ('noglow', 'glow', True)):
        if files.get(key) and Path(files[key]).is_file():
            e, cov = n64_gate.light_delta(_tuple(beauty), _tuple(_card(load(files[key]))), positive_only=pos)
            m[name + '_energy'] = e
            m[name + '_coverage'] = cov
    if files.get('subject') and Path(files['subject']).is_file():
        m.update(subject_metrics(beauty, _nearest(load(files['subject']), CARD[0], CARD[1])))
    m['title_zone_edge_density'] = title_zone_edges(beauty, scene['title']['placement'])
    m['warm_palette'] = warm_palette(palette)
    return m


def fog_hex(scene):
    """The fog colour the renderer actually used: the scene fog colour dimmed by sky.exposure."""
    ex = float(scene['sky'].get('exposure', 1.0))
    r, g, b = (int(scene['fog']['color'][i:i + 2], 16) for i in (1, 3, 5))
    return '#%02x%02x%02x' % tuple(int(round(v * ex)) for v in (r, g, b))


def warm_palette(palette, lo=8.0, hi=62.0):
    """True when at least 40% of the style's chromatic colours sit in the accent (warm) hue range."""
    import colorsys
    chroma = warm = 0
    for c in palette or []:
        r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        h, s_, v = colorsys.rgb_to_hsv(r, g, b)
        if s_ < 0.15 or v < 0.12:
            continue
        chroma += 1
        warm += lo <= h * 360.0 <= hi
    return chroma > 0 and warm / float(chroma) >= 0.4


def judge(m, scene, th=None):
    th = dict(COVER_THRESHOLDS, **(th or {}))
    why = []

    def need(cond, text):
        if not cond:
            why.append(text)
    mood = scene['mood']
    if 'subject_coverage' not in m:
        why.append('no staged subject: the subject pass is missing (a flat crop or screenshot is not a staged cover)')
    else:
        need(m['subject_coverage'] >= th['subject_coverage_min'],
             'empty frame: the staged subject covers %.1f%% of the card (min %.1f%%); aim the camera at the set' % (
                 100 * m['subject_coverage'], 100 * th['subject_coverage_min']))
        need(m['subject_coverage'] <= th['subject_coverage_max'],
             'subject fills %.0f%% of the card (max %.0f%%): a wall-to-wall crop with no room for sky, depth or title' % (
                 100 * m['subject_coverage'], 100 * th['subject_coverage_max']))
        if m['subject_coverage'] >= th['subject_coverage_min']:
            need(m.get('subject_contrast', 0) >= th['subject_contrast_min'] or m.get('subject_delta_e', 0) >= th['subject_delta_e_min']
                 or m.get('silhouette_contrast', 0) >= th['subject_contrast_min'],
                 'subject does not separate from its surroundings at card size: luma %.3f (min %.2f), colour dE %.1f (min %.0f)' % (
                     m.get('subject_contrast', 0), th['subject_contrast_min'], m.get('subject_delta_e', 0), th['subject_delta_e_min']))
            need(m.get('subject_inside', 0) >= th['subject_inside_min'],
                 'subject cut off by the frame edge (containment %.2f, min %.2f)' % (m.get('subject_inside', 0), th['subject_inside_min']))
    lo = th['mean_luma_min'][mood] if isinstance(th['mean_luma_min'], dict) else th['mean_luma_min']
    need(lo <= m['luma_mean'] <= th['mean_luma_max'],
         'brightness: mean luma %.3f outside [%.2f, %.2f] for a %s cover (covers must read bright on a shelf)' % (
             m['luma_mean'], lo, th['mean_luma_max'], mood))
    need(m['contrast_range'] >= th['contrast_range_min'],
         'low contrast at card size: luma p95-p5 = %.3f (min %.2f)' % (m['contrast_range'], th['contrast_range_min']))
    need(m['luma_p2'] <= th['black_point_max'],
         'no real darks: luma p2 = %.3f (max %.2f); silhouettes need a dark anchor' % (m['luma_p2'], th['black_point_max']))
    need(m['flat_fraction'] <= th['flat_fraction_max'],
         'flat frame: %.0f%% of non-sky 3x3 neighbourhoods are uniform (max %.0f%%)' % (100 * m['flat_fraction'], 100 * th['flat_fraction_max']))
    need(th['edge_density_min'] <= m['edge_density'] <= th['edge_density_max'],
         'detail at card size: edge density %.3f outside [%.2f, %.2f]' % (m['edge_density'], th['edge_density_min'], th['edge_density_max']))
    if 'palette_adherence' in m:
        need(m['palette_adherence'] >= th['palette_adherence_min'],
             'off-palette colour: %.1f%% of pixels in the style\'s hue families (min %.0f%%)' % (100 * m['palette_adherence'], 100 * th['palette_adherence_min']))
        if not m.get('warm_palette'):
            # a warm-dominant palette (desert, forest browns) has no separate warm accent to over-use
            need(m['accent_fraction'] <= th['accent_fraction_max'],
                 'accent overuse: %.1f%% warm-accent pixels (max %.0f%%)' % (100 * m['accent_fraction'], 100 * th['accent_fraction_max']))
    exterior = mood != 'interior'
    if exterior:
        if 'sky_fraction' in m:
            need(m['sky_fraction'] >= th['sky_fraction_min'],
                 'no sky band: %.1f%% sky (min %.0f%%); covers need air above the subject for the title' % (100 * m['sky_fraction'], 100 * th['sky_fraction_min']))
            need(m['band_count'] >= th['depth_bands_min'] and m['band_range'] >= th['depth_range_min'],
                 'depth separation: %d near/mid/far bands present (min %d), value range %.3f (min %.2f)' % (
                     m['band_count'], th['depth_bands_min'], m['band_range'], th['depth_range_min']))
        else:
            why.append('depth separation not measurable: depth/mask passes missing')
    need(m['clip_fraction'] <= th['clip_fraction_max'],
         'blown-out whites: %.2f%% of pixels at luma >= 0.97 (max %.1f%%)' % (100 * m['clip_fraction'], 100 * th['clip_fraction_max']))
    need(m['neon_fraction'] <= th['neon_fraction_max'],
         'neon colour: %.2f%% saturated very bright pixels (max %.1f%%)' % (100 * m['neon_fraction'], 100 * th['neon_fraction_max']))
    need(m['crisp_edge_fraction'] <= th['crisp_edge_fraction_max'],
         'pixel-crisp/sharpened render: %.0f%% of strong edges step in one native pixel (max %.0f%%)' % (
             100 * m['crisp_edge_fraction'], 100 * th['crisp_edge_fraction_max']))
    for key, tkey, text in (('glow_energy', 'glow_energy_max', 'glow cards add %.4f mean luma (max %.3f)'),
                            ('modern_light_energy', 'modern_light_energy_max', 'non-N64 lighting adds %.4f mean luma (max %.3f)'),
                            ('fog_horizon_delta', 'fog_horizon_delta_max', 'fog not tinted to the sky horizon: %.3f (max %.2f)')):
        if key in m:
            need(m[key] <= th[tkey], text % (m[key], th[tkey]))
    need(m['title_zone_edge_density'] <= th['title_zone_edge_max'],
         'busy title zone: edge density %.2f behind the logotype (max %.2f); calm the sky/top of frame' % (
             m['title_zone_edge_density'], th['title_zone_edge_max']))
    return why


def gate(files, scene, palette, th=None):
    m = measure(files, scene, palette)
    why = judge(m, scene, th)
    return {'status': 'passed' if not why else 'failed', 'metrics': m, 'reasons': why,
            'scope': 'cover gate: measured defects at card size; not human taste approval'}


def gate_image_only(path, scene, palette, th=None):
    """A bare image (e.g. an old room crop) without render passes: judged with what it has."""
    return gate({'beauty': str(path)}, scene, palette, th)


def blow_out(src, dst, gain=2.2):
    """Known-bad control: a real render pushed to overexposure (x gain), for gate rejection evidence."""
    from .cover_finish import save
    img = load(src)
    lut = bytes(min(255, int(round(v * gain))) for v in range(256))
    img.px = bytearray(bytes(img.px).translate(lut))
    save(img, dst)
    return dst
