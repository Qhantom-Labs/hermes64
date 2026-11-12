"""Rendered style gate: measures real 320x240 room captures against pack thresholds (stdlib only).

Inputs per room (written by the Godot capture harness, see runtime/godot/main.gd):
  <id>-clean.png  world frame without UI
  <id>-key.png    same frame with a magenta clear colour (exposes uncovered background / cutaway void)
  capture.json    triangle counts plus a geometry audit (floating pieces, uncut doors, camera placement)

Every check is a measured number compared with a threshold from pack data (view.json "style_gate"),
falling back to theme-agnostic CORE_DEFAULTS. Failures are returned as readable sentences. Nothing here
claims human art approval: it rejects measurable defects (washed-out fog, flat frames, void, floating
pieces, off-palette colour), it does not certify beauty.
"""
import colorsys
import json
import math
import struct
import sys
import zlib
from pathlib import Path

CORE_DEFAULTS = {
    # luminance distribution (Rec.601 luma of display values, 0..1)
    'contrast_range_min': 0.42,     # p95 - p5
    'black_point_max': 0.16,        # p2 must reach a real dark
    'white_point_min': 0.80,        # p99.5 must reach a highlight / glint
    'mean_luma_min': 0.12, 'mean_luma_max': 0.70,
    # fog: share of drawn pixels that are within `fog_near_dist` of the fog colour
    'fog_near_dist': 0.07, 'fog_swallowed_max': 0.22,
    # detail: near-uniform 3x3 neighbourhoods and edge density
    'flat_std': 0.006, 'flat_fraction_max': 0.40,
    'edge_threshold': 0.07, 'edge_density_min': 0.07, 'edge_density_max': 0.42,
    # colour: palette hue-family adherence and accent budget
    'palette_hue_tol_deg': 20.0, 'palette_adherence_min': 0.88,
    'accent_fraction_max': 0.15, 'accent_hues': [[8.0, 62.0]], 'accent_sat_min': 0.25,
    # composition
    'void_fraction_max_interior': 0.01, 'void_fraction_max_exterior': 0.45,
    'floating_max': 0, 'uncut_doors_max': 0,
    'camera_inside_interior': True,
    # set-level
    'accent_rooms_min_fraction': 0.0,
    # exteriors (depth + region-mask passes): sky gradient, haze tinted to the horizon, three depth bands
    # with distinct values, a landmark in view, painted low-frequency ground variation
    'ext_near_m': 10.0, 'ext_far_m': 32.0,
    'ext_sky_fraction_min': 0.06, 'ext_sky_gradient_min': 0.06,
    'ext_far_haze_max': 0.16, 'ext_near_haze_min': 0.12,
    'ext_band_coverage_min': 0.03, 'ext_band_gap_min': 0.03, 'ext_band_range_min': 0.08,
    'ext_ground_flat_max': 0.6, 'ext_ground_lowfreq_min': 0.012, 'ext_landmarks_min': 1,
}


# ------------------------------------------------------------------ PNG (8-bit, non-interlaced)
def read_png(path):
    data = Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG: %s' % path)
    pos, idat, w = 8, [], None
    while pos < len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif tag == b'IDAT':
            idat.append(body)
        elif tag == b'IEND':
            break
    if w is None or depth != 8 or interlace != 0:
        raise ValueError('unsupported PNG (need 8-bit non-interlaced): %s' % path)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b''.join(idat))
    stride = w * ch
    prev = bytearray(stride)
    rgb = bytearray(w * h * 3)
    i = 0
    for y in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ft == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        o = y * w * 3
        if ch == 3:
            rgb[o:o + w * 3] = line
        elif ch == 4:
            for x in range(w):
                rgb[o + 3 * x:o + 3 * x + 3] = line[4 * x:4 * x + 3]
        else:
            for x in range(w):
                v = line[x * ch]
                rgb[o + 3 * x:o + 3 * x + 3] = bytes((v, v, v))
        prev = line
    return w, h, bytes(rgb)


def hex_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _hue_dist(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def palette_families(palette, sat_min=0.15):
    hues, neutral = [], False
    for c in palette:
        r, g, b = hex_rgb(c)
        hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
        if ss >= sat_min and vv > 0.08:
            hues.append(hh * 360.0)
        else:
            neutral = True
    return sorted(set(round(x, 1) for x in hues)), neutral


# ------------------------------------------------------------------ image metrics
def sky_mask(mask):
    """Region pass (n64_debug x=2) -> bytearray, 1 where the sky dome / view planes of the sky were drawn."""
    w, h, mpx = mask
    out = bytearray(w * h)
    for i in range(w * h):
        if mpx[3 * i] < 60 and mpx[3 * i + 1] < 60 and mpx[3 * i + 2] > 190:
            out[i] = 1
    return out


def image_metrics(clean, key=None, fog_colour=None, palette=None, th=None, exclude=None):
    """clean/key: (w, h, rgb bytes). Returns measured numbers (no pass/fail).
    exclude: optional bytearray (1 = skip) for the fog-proximity and flatness counts only. Exteriors pass the sky
    region here: a smooth dome that meets the fog colour at the horizon is the intended N64 construction, so only
    geometry is tested for being swallowed by fog or lacking detail (the sky has its own gradient/haze checks)."""
    th = dict(CORE_DEFAULTS, **(th or {}))
    w, h, px = clean
    n = w * h
    void = bytearray(n)
    if key is not None:
        kw, kh, kpx = key
        if (kw, kh) != (w, h):
            raise ValueError('clean/key size mismatch')
        for i in range(n):
            if kpx[3 * i] >= 250 and kpx[3 * i + 1] <= 5 and kpx[3 * i + 2] >= 250:
                void[i] = 1
    luma = [0.0] * n
    for i in range(n):
        luma[i] = (0.299 * px[3 * i] + 0.587 * px[3 * i + 1] + 0.114 * px[3 * i + 2]) / 255.0
    drawn = [i for i in range(n) if not void[i]]
    nd = max(1, len(drawn))
    sl = sorted(luma[i] for i in drawn) if drawn else [0.0]
    out = {'pixels': n, 'drawn_pixels': len(drawn), 'void_fraction': round(1.0 - len(drawn) / n, 4),
           'luma_p2': round(_pct(sl, 0.02), 4), 'luma_p5': round(_pct(sl, 0.05), 4),
           'luma_p50': round(_pct(sl, 0.5), 4), 'luma_p95': round(_pct(sl, 0.95), 4),
           'luma_p995': round(_pct(sl, 0.995), 4), 'luma_mean': round(sum(sl) / len(sl), 4)}
    out['contrast_range'] = round(out['luma_p95'] - out['luma_p5'], 4)
    # fog proximity over drawn pixels
    if fog_colour:
        fr, fg, fb = hex_rgb(fog_colour)
        near = 0
        dist_sum = 0.0
        lim = th['fog_near_dist']
        geo = [i for i in drawn if not (exclude and exclude[i])]
        nd_fog = max(1, len(geo))
        for i in geo:
            dr = px[3 * i] / 255.0 - fr
            dg = px[3 * i + 1] / 255.0 - fg
            db = px[3 * i + 2] / 255.0 - fb
            dd = math.sqrt((dr * dr + dg * dg + db * db) / 3.0)
            dist_sum += dd
            if dd < lim:
                near += 1
        out['fog_swallowed_fraction'] = round(near / nd_fog, 4)
        out['fog_mean_distance'] = round(dist_sum / nd_fog, 4)
    # 3x3 flatness + Sobel edge density (interior pixels, drawn only)
    flat = edges = counted = 0
    fstd, ethr = th['flat_std'], th['edge_threshold']
    for y in range(1, h - 1):
        row = y * w
        for x in range(1, w - 1):
            i = row + x
            if void[i] or (exclude and exclude[i]):
                continue
            counted += 1
            a, b, c = luma[i - w - 1], luma[i - w], luma[i - w + 1]
            d, e, f = luma[i - 1], luma[i], luma[i + 1]
            g, hh, k = luma[i + w - 1], luma[i + w], luma[i + w + 1]
            m = (a + b + c + d + e + f + g + hh + k) / 9.0
            var = ((a - m) ** 2 + (b - m) ** 2 + (c - m) ** 2 + (d - m) ** 2 + (e - m) ** 2 + (f - m) ** 2 +
                   (g - m) ** 2 + (hh - m) ** 2 + (k - m) ** 2) / 9.0
            if var < fstd * fstd:
                flat += 1
            gx = (c + 2 * f + k) - (a + 2 * d + g)
            gy = (g + 2 * hh + k) - (a + 2 * b + c)
            if math.sqrt(gx * gx + gy * gy) / 4.0 > ethr:
                edges += 1
    counted = max(1, counted)
    out['flat_fraction'] = round(flat / counted, 4)
    out['edge_density'] = round(edges / counted, 4)
    # colour: hue families from the pack palette; warm/other accent share
    if palette:
        fam, neutral_ok = palette_families(palette)
        tol = th['palette_hue_tol_deg']
        accents = [tuple(r) for r in th['accent_hues']]
        good = acc = 0
        cache = {}
        for i in drawn:
            key3 = (px[3 * i] >> 2, px[3 * i + 1] >> 2, px[3 * i + 2] >> 2)
            hit = cache.get(key3)
            if hit is None:
                r, g, b = px[3 * i] / 255.0, px[3 * i + 1] / 255.0, px[3 * i + 2] / 255.0
                hh_, ss, vv = colorsys.rgb_to_hsv(r, g, b)
                hue = hh_ * 360.0
                if vv <= 0.10 or ss < 0.12:
                    ok = neutral_ok or vv <= 0.10
                else:
                    ok = any(_hue_dist(hue, f_) <= tol for f_ in fam)
                is_acc = ss >= th['accent_sat_min'] and vv >= 0.25 and any(lo <= hue <= hi for lo, hi in accents)
                hit = (ok, is_acc)
                cache[key3] = hit
            good += hit[0]
            acc += hit[1]
        out['palette_adherence'] = round(good / nd, 4)
        out['accent_fraction'] = round(acc / nd, 4)
    return out


def exterior_metrics(clean, depth, mask, depth_scale, th=None):
    """Exterior composition numbers from the clean frame + distance pass + region mask (no pass/fail)."""
    th = dict(CORE_DEFAULTS, **(th or {}))
    w, h, px = clean
    _, _, dpx = depth
    _, _, mpx = mask
    n = w * h
    luma = [(0.299 * px[3 * i] + 0.587 * px[3 * i + 1] + 0.114 * px[3 * i + 2]) / 255.0 for i in range(n)]
    sky = bytearray(n)
    ground = bytearray(n)
    void = bytearray(n)
    dist = [0.0] * n
    for i in range(n):
        r, g, b = mpx[3 * i], mpx[3 * i + 1], mpx[3 * i + 2]
        dr = dpx[3 * i]
        if r < 60 and g < 60 and b > 190:
            sky[i] = 1
        elif r < 60 and g > 190 and b > 190:
            ground[i] = 1
        if dr >= 254 and r < 8 and g < 8 and b < 8:
            void[i] = 1
        dist[i] = dr / 255.0 * depth_scale
    out = {'sky_fraction': round(sum(sky) / n, 4), 'ground_fraction': round(sum(ground) / n, 4)}
    # sky gradient: mean luma of sky pixels per row (rows with enough sky), top band vs horizon band
    rows = []
    for y in range(h):
        idx = [y * w + x for x in range(w) if sky[y * w + x]]
        if len(idx) >= 8:
            rows.append((y, sum(luma[i] for i in idx) / len(idx), idx))
    if len(rows) >= 4:
        k = max(1, len(rows) // 8)
        top = sum(r[1] for r in rows[:k]) / k
        low = sum(r[1] for r in rows[-k:]) / k
        out['sky_gradient'] = round(abs(low - top), 4)
        hz = [i for r in rows[-k:] for i in r[2]]
        horizon = tuple(sum(px[3 * i + c] for i in hz) / (255.0 * len(hz)) for c in range(3))
    else:
        out['sky_gradient'] = 0.0
        horizon = None
    # depth bands over drawn, non-sky pixels
    near_m, far_m = th['ext_near_m'], th['ext_far_m']
    bands = {'near': [], 'mid': [], 'far': []}
    for i in range(n):
        if sky[i] or void[i]:
            continue
        d = dist[i]
        bands['near' if d < near_m else ('mid' if d < far_m else 'far')].append(i)
    for name, idx in bands.items():
        out['band_%s_coverage' % name] = round(len(idx) / n, 4)
        out['band_%s_luma' % name] = round(sum(luma[i] for i in idx) / len(idx), 4) if idx else None
        if horizon is not None and idx:
            mean = [sum(px[3 * i + c] for i in idx) / (255.0 * len(idx)) for c in range(3)]
            out['band_%s_haze' % name] = round(math.sqrt(sum((mean[c] - horizon[c]) ** 2 for c in range(3)) / 3.0), 4)
    present = [out['band_%s_luma' % b] for b in ('near', 'mid', 'far') if out['band_%s_coverage' % b] >= th['ext_band_coverage_min']]
    srt = sorted(present)
    out['band_count'] = len(present)
    out['band_range'] = round(srt[-1] - srt[0], 4) if len(srt) >= 2 else 0.0
    out['band_min_gap'] = round(min(b - a for a, b in zip(srt, srt[1:])), 4) if len(srt) >= 2 else 0.0
    # ground: near-uniform 3x3 share and low-frequency (8x8 block) variation over ground pixels
    flat = cnt = 0
    fstd = th['flat_std']
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            if not ground[i]:
                continue
            nb = [luma[i + dy * w + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
            m = sum(nb) / 9.0
            if sum((v - m) ** 2 for v in nb) / 9.0 < fstd * fstd:
                flat += 1
            cnt += 1
    out['ground_flat_fraction'] = round(flat / cnt, 4) if cnt else None
    blocks = []
    for by in range(0, h - 7, 8):
        for bx in range(0, w - 7, 8):
            idx = [(by + yy) * w + bx + xx for yy in range(8) for xx in range(8)]
            g = [i for i in idx if ground[i]]
            if len(g) >= 48:
                blocks.append(sum(luma[i] for i in g) / len(g))
    if len(blocks) >= 6:
        mb = sum(blocks) / len(blocks)
        out['ground_lowfreq'] = round(math.sqrt(sum((v - mb) ** 2 for v in blocks) / len(blocks)), 4)
    else:
        out['ground_lowfreq'] = None
    return out


def judge_exterior(m, audit, th):
    th = dict(CORE_DEFAULTS, **(th or {}))
    why = []

    def need(cond, text):
        if not cond:
            why.append(text)
    need(m['sky_fraction'] >= th['ext_sky_fraction_min'],
         'no sky/horizon in view: %.1f%% sky (min %.0f%%)' % (100 * m['sky_fraction'], 100 * th['ext_sky_fraction_min']))
    need(m['sky_gradient'] >= th['ext_sky_gradient_min'],
         'flat sky: zenith-to-horizon luma range %.3f < %.2f (paint a gradient dome)' % (m['sky_gradient'], th['ext_sky_gradient_min']))
    far = m.get('band_far_haze')
    need(far is not None and far <= th['ext_far_haze_max'],
         'distance haze not tinted to the horizon: far band %s from the horizon colour (max %.2f)' % (
             'absent' if far is None else '%.3f' % far, th['ext_far_haze_max']))
    near = m.get('band_near_haze')
    need(near is not None and near >= th['ext_near_haze_min'],
         'near ground swallowed by haze: near band %s from the horizon colour (min %.2f)' % (
             'absent' if near is None else '%.3f' % near, th['ext_near_haze_min']))
    need(m['band_count'] == 3 and m['band_range'] >= th['ext_band_range_min'] and m['band_min_gap'] >= th['ext_band_gap_min'],
         'depth layering: %d/3 near/mid/far bands present, value range %.3f (min %.2f), smallest gap %.3f (min %.2f)' % (
             m['band_count'], m['band_range'], th['ext_band_range_min'], m['band_min_gap'], th['ext_band_gap_min']))
    gf = m.get('ground_flat_fraction')
    need(gf is not None and gf <= th['ext_ground_flat_max'],
         'ground is a flat colour: %s near-uniform (max %.0f%%)' % ('no ground in view' if gf is None else '%.0f%%' % (100 * gf), 100 * th['ext_ground_flat_max']))
    lf = m.get('ground_lowfreq')
    need(lf is not None and lf >= th['ext_ground_lowfreq_min'],
         'ground lacks painted large-scale variation: 8x8 block luma std %s (min %.3f)' % ('n/a' if lf is None else '%.4f' % lf, th['ext_ground_lowfreq_min']))
    if audit is not None:
        need(audit.get('landmarks_in_view', 0) >= th['ext_landmarks_min'],
             'no landmark in view (%d placed, %d visible; min %d)' % (len(audit.get('landmarks', [])), audit.get('landmarks_in_view', 0), th['ext_landmarks_min']))
    return why


def judge(metrics, audit, th, exterior=False):
    """Compare one room's metrics with thresholds -> list of readable failure reasons."""
    th = dict(CORE_DEFAULTS, **(th or {}))
    why = []
    m = metrics

    def need(cond, text):
        if not cond:
            why.append(text)
    need(m['contrast_range'] >= th['contrast_range_min'],
         'low contrast: luma p95-p5 = %.3f < %.2f (washed out; add darks/highlights)' % (m['contrast_range'], th['contrast_range_min']))
    need(m['luma_p2'] <= th['black_point_max'],
         'no real darks: luma p2 = %.3f > %.2f' % (m['luma_p2'], th['black_point_max']))
    need(m['luma_p995'] >= th['white_point_min'],
         'no highlights/glints: luma p99.5 = %.3f < %.2f' % (m['luma_p995'], th['white_point_min']))
    need(th['mean_luma_min'] <= m['luma_mean'] <= th['mean_luma_max'],
         'exposure: mean luma %.3f outside [%.2f, %.2f]' % (m['luma_mean'], th['mean_luma_min'], th['mean_luma_max']))
    if 'fog_swallowed_fraction' in m:
        need(m['fog_swallowed_fraction'] <= th['fog_swallowed_max'],
             'fog flattens the frame: %.0f%% of drawn (non-sky) pixels sit within %.2f of the fog colour (max %.0f%%)' % (
                 100 * m['fog_swallowed_fraction'], th['fog_near_dist'], 100 * th['fog_swallowed_max']))
    need(m['flat_fraction'] <= th['flat_fraction_max'],
         'flat frame: %.0f%% near-uniform 3x3 neighbourhoods (max %.0f%%)' % (100 * m['flat_fraction'], 100 * th['flat_fraction_max']))
    need(th['edge_density_min'] <= m['edge_density'] <= th['edge_density_max'],
         'detail: edge density %.3f outside [%.2f, %.2f]' % (m['edge_density'], th['edge_density_min'], th['edge_density_max']))
    if 'palette_adherence' in m:
        need(m['palette_adherence'] >= th['palette_adherence_min'],
             'off-palette colour: %.1f%% of pixels in pack hue families (min %.0f%%)' % (100 * m['palette_adherence'], 100 * th['palette_adherence_min']))
        need(m['accent_fraction'] <= th['accent_fraction_max'],
             'accent overuse: %.1f%% accent pixels (max %.0f%%)' % (100 * m['accent_fraction'], 100 * th['accent_fraction_max']))
    vmax = th['void_fraction_max_exterior'] if exterior else th['void_fraction_max_interior']
    need(m['void_fraction'] <= vmax,
         'cutaway/void: %.1f%% of the frame shows uncovered background (max %.1f%%)' % (100 * m['void_fraction'], 100 * vmax))
    if audit is not None:
        fl = audit.get('floating', [])
        need(len(fl) <= th['floating_max'],
             'floating pieces: %s' % ', '.join('%s(%s, %.2fm up)' % (f['name'], f['kind'], f['bottom']) for f in fl[:6]))
        need(audit.get('uncut_doors', 0) <= th['uncut_doors_max'],
             'doors without a wall opening: %d free-standing door frame(s)' % audit.get('uncut_doors', 0))
        cam = audit.get('camera') or {}
        if th['camera_inside_interior'] and not exterior and cam:
            need(bool(cam.get('inside_bounds')),
                 'camera outside the room shell at %s (cutaway diorama framing)' % (cam.get('position'),))
    return why


def gate_directory(folder, theme=None, thresholds=None, rooms=None):
    """Run the gate over a capture folder. theme = runtime theme.json dict (fog colour, palette)."""
    folder = Path(folder)
    cap = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
    theme = theme or {}
    th = dict(CORE_DEFAULTS)
    th.update((theme.get('style_gate') or {}))
    th.update(thresholds or {})
    palette = theme.get('palette_colors') or []
    rows = []
    for row in cap['rooms']:
        rid = row['id']
        if rooms and rid not in rooms:
            continue
        clean = folder / row.get('clean', rid + '-clean.png')
        key = folder / row.get('key', rid + '-key.png')
        audit = row.get('audit')
        exterior = bool((audit or {}).get('exterior', False))
        if not clean.is_file():
            rows.append({'id': rid, 'status': 'failed', 'reasons': ['missing clean capture ' + clean.name]})
            continue
        fog = (audit or {}).get('fog_color') or (theme.get('fog') or {}).get('color')
        depth = folder / row.get('depth', rid + '-depth.png')
        mask = folder / row.get('mask', rid + '-mask.png')
        skip = sky_mask(read_png(mask)) if exterior and mask.is_file() else None
        metrics = image_metrics(read_png(clean), read_png(key) if key.is_file() else None, fog, palette, th, skip)
        if skip is not None:
            metrics['detail_scope'] = 'fog/flatness over non-sky pixels'
        reasons = judge(metrics, audit, th, exterior)
        if exterior:
            if depth.is_file() and mask.is_file():
                ext = exterior_metrics(read_png(clean), read_png(depth), read_png(mask), float(row.get('depth_scale_m', 120)), th)
                metrics['exterior'] = ext
                reasons += judge_exterior(ext, audit, th)
            else:
                reasons.append('exterior capture lacks depth/mask passes (re-capture with the current harness)')
        rows.append({'id': rid, 'status': 'passed' if not reasons else 'failed', 'exterior': exterior,
                     'metrics': metrics, 'reasons': reasons})
    set_reasons = []
    measured = [r for r in rows if 'metrics' in r]
    if measured and th.get('accent_rooms_min_fraction', 0) > 0:
        with_acc = sum(1 for r in measured if r['metrics'].get('accent_fraction', 0) >= 0.002)
        if with_acc / len(measured) < th['accent_rooms_min_fraction']:
            set_reasons.append('accents: only %d/%d rooms show a warm/accent light (min %.0f%%)' % (
                with_acc, len(measured), 100 * th['accent_rooms_min_fraction']))
    ok = rows and all(r['status'] == 'passed' for r in rows) and not set_reasons
    return {'status': 'passed' if ok else 'failed', 'rooms': rows, 'set_reasons': set_reasons,
            'thresholds': th, 'scope': 'measured captures at their recorded dimensions vs pack thresholds; not human art approval'}


def summary_lines(report):
    lines = ['STYLE GATE %s' % report['status'].upper()]
    for r in report['rooms']:
        m = r.get('metrics', {})
        lines.append('  %-18s %-6s contrast=%.2f fog=%.2f flat=%.2f edges=%.2f void=%.3f palette=%.2f' % (
            r['id'], r['status'], m.get('contrast_range', 0), m.get('fog_swallowed_fraction', 0), m.get('flat_fraction', 0),
            m.get('edge_density', 0), m.get('void_fraction', 0), m.get('palette_adherence', 0)))
        ext = m.get('exterior')
        if ext:
            lines.append('      exterior: sky=%.2f grad=%.3f bands=%d range=%.3f gap=%.3f near_haze=%s far_haze=%s ground_flat=%s lowfreq=%s' % (
                ext['sky_fraction'], ext['sky_gradient'], ext['band_count'], ext['band_range'], ext['band_min_gap'],
                ext.get('band_near_haze'), ext.get('band_far_haze'), ext.get('ground_flat_fraction'), ext.get('ground_lowfreq')))
        for why in r.get('reasons', []):
            lines.append('      - ' + why)
    for why in report.get('set_reasons', []):
        lines.append('  set: ' + why)
    return lines


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='style_gate')
    ap.add_argument('folder')
    ap.add_argument('--theme', help='runtime theme.json (fog colour, palette, style_gate thresholds)')
    ap.add_argument('--out', help='write the JSON report here')
    a = ap.parse_args(argv)
    theme = json.loads(Path(a.theme).read_text(encoding='utf-8')) if a.theme else {}
    report = gate_directory(a.folder, theme)
    if a.out:
        Path(a.out).write_bytes(json.dumps(report, indent=2).encode('utf-8'))
    print('\n'.join(summary_lines(report)))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
