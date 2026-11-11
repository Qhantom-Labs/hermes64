"""N64-fidelity gate section (stdlib only): measurable tells of a non-1998-N64 frame.

Separate from the defect gate in style_gate.py (whose verdict and thresholds are unchanged). Inputs per room, written by
the Godot capture harness (runtime/godot/main.gd):

  <id>-clean.png    320x240 world frame without UI (the frame the defect gate measures)
  <id>-classic.png  the same frame with the non-N64 lighting features switched off (per-pixel point lights, specular
                    glints, fresnel rims; shader global n64_classic = 0)
  <id>-noglow.png   the same frame without glow/halo cards
  <id>.png          960x720 window capture (the upscaled output a player sees)
  <id>-mask.png     region pass (sky detection for exteriors)
  <id>-closeup.png  optional character close-up (evidence; crispness of actor textures)

Metrics (all measured numbers; thresholds come from kits/core/n64_look.json "gate", overridable by pack view.json
"n64.gate"; nothing here certifies beauty or authenticity):

  modern_light_energy   mean |luma(clean) - luma(classic)|: light contributed by per-pixel/specular/fresnel features
  glow_energy           mean max(0, luma(clean) - luma(noglow)): brightening by glow/halo (bloom-like) cards
  glow_coverage         share of pixels a glow card brightens by more than 0.04
  clip_fraction         share of drawn pixels at luma >= 0.97 (blown-out glare)
  neon_fraction         share of drawn pixels with HSV saturation >= 0.6 and value >= 0.92 (neon glow)
  crisp_edge_fraction   share of strong 4-pixel luma ramps whose change happens in one pixel step (aliased/nearest)
  upscale_nearest_ratio share of textured 3x3 cells of the window capture that are uniform (nearest upscale)
  fog_horizon_delta     exteriors: RMS distance between the fog colour and the measured sky horizon colour
  closeup_crisp_edge_fraction  the crispness measure on the character close-up

Library checks (kit textures + pack material tables): texture_hf_energy per texture (mean |L - 3x3 box blur|, wrapped,
i.e. per-texel noise and dither) and texel density spread per material class.
"""
import colorsys
import json
import math
from pathlib import Path

from .style_gate import read_png, sky_mask

ROOT = Path(__file__).resolve().parents[1]
CONVENTION = ROOT / 'kits' / 'core' / 'n64_look.json'


def convention(path=None):
    return json.loads(Path(path or CONVENTION).read_text(encoding='utf-8'))


def thresholds(theme=None, conv=None):
    conv = conv or convention()
    th = dict(conv.get('gate', {}).get('thresholds', {}))
    th.update(((theme or {}).get('n64') or {}).get('gate', {}).get('thresholds', {}))
    return th


# ------------------------------------------------------------------ helpers
def luma_of(img):
    w, h, px = img
    return [(0.299 * px[3 * i] + 0.587 * px[3 * i + 1] + 0.114 * px[3 * i + 2]) / 255.0 for i in range(w * h)]


def _same_size(a, b):
    if (a[0], a[1]) != (b[0], b[1]):
        raise ValueError('image size mismatch %sx%s vs %sx%s' % (a[0], a[1], b[0], b[1]))


def light_delta(clean, other, positive_only=False, floor=0.04):
    """(mean delta, share of pixels changed by more than `floor`) between two frames of the same view."""
    _same_size(clean, other)
    la, lb = luma_of(clean), luma_of(other)
    tot = 0.0
    big = 0
    for x, y in zip(la, lb):
        d = x - y
        if positive_only:
            d = max(0.0, d)
        else:
            d = abs(d)
        tot += d
        if d > floor:
            big += 1
    n = max(1, len(la))
    return round(tot / n, 5), round(big / n, 5)


def crisp_edges(img, strong=0.20, ratio=0.85, skip=None):
    """Share of strong luma ramps (|L[x+2]-L[x-1]| > strong, monotonic) where one pixel step carries > ratio of the
    change, along rows and columns. A nearest/aliased frame steps in one pixel; a filtered/antialiased one spreads."""
    w, h, _ = img
    L = luma_of(img)
    strong_n = crisp_n = 0
    for (dx, dy) in ((1, 0), (0, 1)):
        for y in range(1, h - 2 if dy else h):
            for x in range(1, w - 2 if dx else w):
                i = y * w + x
                if skip is not None and skip[i]:
                    continue
                a, b, c, d = L[i - dx - dy * w], L[i], L[i + dx + dy * w], L[i + 2 * dx + 2 * dy * w]
                total = d - a
                if abs(total) <= strong:
                    continue
                s1, s2, s3 = b - a, c - b, d - c
                if total > 0 and (s1 < -0.01 or s2 < -0.01 or s3 < -0.01):
                    continue
                if total < 0 and (s1 > 0.01 or s2 > 0.01 or s3 > 0.01):
                    continue
                strong_n += 1
                if max(abs(s1), abs(s2), abs(s3)) > ratio * abs(total):
                    crisp_n += 1
    return round(crisp_n / strong_n, 4) if strong_n else 0.0, strong_n


def upscale_nearest_ratio(window, scale=3, frame=(320, 240)):
    """Share of aligned scale x scale cells (inside the frame area) that are uniform, among cells whose colour differs
    from the next cell to the right (textured content). Nearest-neighbour upscaling gives ~1, bilinear ~0."""
    w, h, px = window
    fw, fh = min(frame[0], w // scale), min(frame[1], h // scale)
    textured = uniform = 0
    for cy in range(fh):
        for cx in range(fw - 1):
            x0, y0 = cx * scale, cy * scale
            first = px[3 * (y0 * w + x0):3 * (y0 * w + x0) + 3]
            nxt = px[3 * (y0 * w + x0 + scale):3 * (y0 * w + x0 + scale) + 3]
            if max(abs(first[k] - nxt[k]) for k in range(3)) < 6:
                continue
            textured += 1
            same = True
            for yy in range(scale):
                o = 3 * ((y0 + yy) * w + x0)
                row = px[o:o + 3 * scale]
                for xx in range(scale):
                    if row[3 * xx:3 * xx + 3] != first:
                        same = False
                        break
                if not same:
                    break
            uniform += same
    return round(uniform / textured, 4) if textured else 0.0


def colour_stats(img, skip=None):
    w, h, px = img
    n = clip = neon = 0
    for i in range(w * h):
        if skip is not None and skip[i]:
            continue
        r, g, b = px[3 * i] / 255.0, px[3 * i + 1] / 255.0, px[3 * i + 2] / 255.0
        n += 1
        if 0.299 * r + 0.587 * g + 0.114 * b >= 0.97:
            clip += 1
        _, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s >= 0.6 and v >= 0.92:
            neon += 1
    n = max(1, n)
    return round(clip / n, 5), round(neon / n, 5)


def horizon_colour(clean, mask):
    """Mean colour of the lowest eighth of sky rows (rows with >= 8 sky pixels), or None."""
    w, h, px = clean
    sky = sky_mask(mask)
    rows = []
    for y in range(h):
        idx = [y * w + x for x in range(w) if sky[y * w + x]]
        if len(idx) >= 8:
            rows.append(idx)
    if len(rows) < 4:
        return None
    k = max(1, len(rows) // 8)
    hz = [i for r in rows[-k:] for i in r]
    return tuple(sum(px[3 * i + c] for i in hz) / (255.0 * len(hz)) for c in range(3))


def hex_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


# ------------------------------------------------------------------ per room / folder
def room_metrics(folder, row, theme=None):
    folder = Path(folder)
    rid = row['id']
    clean_p = folder / row.get('clean', rid + '-clean.png')
    if not clean_p.is_file():
        return {'error': 'missing clean capture'}
    clean = read_png(clean_p)
    m = {}
    exterior = bool((row.get('audit') or {}).get('exterior', False))
    mask_p = folder / row.get('mask', rid + '-mask.png')
    sky = sky_mask(read_png(mask_p)) if (exterior and mask_p.is_file()) else None
    for key, name, pos in (('classic', 'modern_light', False), ('noglow', 'glow', True)):
        p = folder / (row.get(key) or (rid + '-' + key + '.png'))
        if p.is_file():
            e, cov = light_delta(clean, read_png(p), positive_only=pos)
            m[name + '_energy'] = e
            m[name + '_coverage'] = cov
    m['clip_fraction'], m['neon_fraction'] = colour_stats(clean, sky)
    m['crisp_edge_fraction'], m['strong_edges'] = crisp_edges(clean)
    win = folder / row.get('screenshot', rid + '.png')
    if win.is_file():
        wimg = read_png(win)
        if wimg[0] >= 3 * clean[0] and wimg[1] >= 3 * clean[1]:
            m['upscale_nearest_ratio'] = upscale_nearest_ratio(wimg, 3, (clean[0], clean[1]))
    elif row.get('window_crop') and (folder / row['window_crop']).is_file():
        # committed fixtures keep a 3x-aligned crop of the window capture instead of the full 960x720 frame
        wimg = read_png(folder / row['window_crop'])
        m['upscale_nearest_ratio'] = upscale_nearest_ratio(wimg, 3, (wimg[0] // 3, wimg[1] // 3))
    cu = row.get('closeup') or {}
    if isinstance(cu, dict) and cu.get('file') and (folder / cu['file']).is_file():
        m['closeup_crisp_edge_fraction'], _ = crisp_edges(read_png(folder / cu['file']))
    if exterior and mask_p.is_file():
        hz = horizon_colour(clean, read_png(mask_p))
        fog = (row.get('audit') or {}).get('fog_color')
        if hz is not None and fog:
            f = hex_rgb(fog)
            m['fog_horizon_delta'] = round(math.sqrt(sum((hz[c] - f[c]) ** 2 for c in range(3)) / 3.0), 4)
            m['horizon_colour'] = '#%02x%02x%02x' % tuple(int(round(255 * c)) for c in hz)
    return m


CHECKS = (  # (metric, threshold key, comparison, sentence)
    ('modern_light_energy', 'modern_light_energy_max', 'le', 'per-pixel/specular/fresnel light adds %.4f mean luma (max %.4f)'),
    ('glow_energy', 'glow_energy_max', 'le', 'glow/halo cards add %.4f mean luma (max %.4f)'),
    ('glow_coverage', 'glow_coverage_max', 'le', 'glow/halo cards brighten %.1f%% of the frame (max %.1f%%)'),
    ('clip_fraction', 'clip_fraction_max', 'le', 'blown-out glare: %.2f%% of pixels at luma >= 0.97 (max %.2f%%)'),
    ('neon_fraction', 'neon_fraction_max', 'le', 'neon colour: %.2f%% saturated very bright pixels (max %.2f%%)'),
    ('crisp_edge_fraction', 'crisp_edge_fraction_max', 'le', 'pixel-crisp frame: %.0f%% of strong edges step in one pixel (max %.0f%%)'),
    ('upscale_nearest_ratio', 'upscale_nearest_ratio_max', 'le', 'nearest-neighbour upscale: %.0f%% of textured cells uniform (max %.0f%%)'),
    ('fog_horizon_delta', 'fog_horizon_delta_max', 'le', 'fog not tinted to the horizon: %.3f from the sky horizon colour (max %.3f)'),
    ('closeup_crisp_edge_fraction', 'closeup_crisp_edge_fraction_max', 'le', 'character close-up crisp: %.0f%% one-pixel edges (max %.0f%%)'),
)
PERCENT = {'glow_coverage', 'clip_fraction', 'neon_fraction', 'crisp_edge_fraction', 'upscale_nearest_ratio',
           'closeup_crisp_edge_fraction'}


def judge(m, th):
    why = []
    for metric, key, cmp, text in CHECKS:
        if metric not in m or key not in th:
            continue
        v, t = m[metric], th[key]
        ok = v <= t if cmp == 'le' else v >= t
        if not ok:
            k = 100.0 if metric in PERCENT else 1.0
            why.append(text % (v * k, t * k))
    return why


def gate_folder(folder, theme=None, conv=None, rooms=None):
    folder = Path(folder)
    cap = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
    th = thresholds(theme, conv)
    rows = []
    for row in cap['rooms']:
        if rooms and row['id'] not in rooms:
            continue
        m = room_metrics(folder, row, theme)
        why = ['missing clean capture'] if 'error' in m else judge(m, th)
        rows.append({'id': row['id'], 'status': 'passed' if not why else 'failed', 'metrics': m, 'reasons': why})
    ok = bool(rows) and all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'rooms': rows, 'thresholds': th,
            'scope': 'n64_fidelity: measured tells of non-N64 rendering on 320x240 captures; not human art approval'}


def summary_lines(report):
    lines = ['N64 FIDELITY %s' % report['status'].upper()]
    for r in report['rooms']:
        m = r['metrics']
        lines.append('  %-18s %-6s modern=%.4f glow=%.4f/%.3f clip=%.4f neon=%.4f crisp=%.2f upscale=%s fog_hz=%s closeup=%s' % (
            r['id'], r['status'], m.get('modern_light_energy', -1), m.get('glow_energy', -1), m.get('glow_coverage', -1),
            m.get('clip_fraction', -1), m.get('neon_fraction', -1), m.get('crisp_edge_fraction', -1),
            m.get('upscale_nearest_ratio', '-'), m.get('fog_horizon_delta', '-'), m.get('closeup_crisp_edge_fraction', '-')))
        for why in r['reasons']:
            lines.append('      - ' + why)
    return lines


# ------------------------------------------------------------------ library (kit textures, pack tables)
def texture_hf_energy(img):
    """Mean |L - wrapped 3x3 box blur(L)| over a tileable texture: per-texel noise/dither energy (0 = smooth)."""
    w, h, _ = img
    L = luma_of(img)
    tot = 0.0
    for y in range(h):
        for x in range(w):
            s = 0.0
            for dy in (-1, 0, 1):
                yy = (y + dy) % h
                for dx in (-1, 0, 1):
                    s += L[yy * w + (x + dx) % w]
            tot += abs(L[y * w + x] - s / 9.0)
    return round(tot / (w * h), 5)


def role_class(conv, role):
    for cls, spec in conv.get('texel_density', {}).get('classes', {}).items():
        if role in spec.get('roles', []):
            return cls
    return None


def pack_density(conv, kit_pack):
    """Texel density (texels per metre) per textured role of a kit pack, grouped by convention class."""
    mats = kit_pack['materials']
    out = {}
    for role, m in sorted(mats.items()):
        t = m.get('texture') or {}
        if not t or t.get('gen') in ('env', 'scene') or 'tile_m' not in m:
            continue
        cls = role_class(conv, role)
        if cls is None:
            continue
        size = int(t.get('size', 32))
        out.setdefault(cls, {})[role] = {'size': size, 'tile_m': float(m['tile_m']), 'texels_per_m': round(size / float(m['tile_m']), 2)}
    return out


def library_report(root=ROOT, conv=None, packs=None):
    """Texture noise and texel-density consistency for the shipped kit packs."""
    root = Path(root)
    conv = conv or convention(root / 'kits' / 'core' / 'n64_look.json')
    lib = conv.get('gate', {}).get('library', {})
    exempt = set(lib.get('hf_exempt_roles', []))
    report = {'packs': {}, 'status': 'passed', 'reasons': []}
    for pk in packs or sorted(p.name for p in (root / 'kits' / 'packs').iterdir() if (p / 'pack.json').is_file()):
        kp = json.loads((root / 'kits' / 'packs' / pk / 'pack.json').read_text(encoding='utf-8'))
        dens = pack_density(conv, kp)
        spread = {}
        for cls, roles in dens.items():
            vals = [r['texels_per_m'] for r in roles.values()]
            spread[cls] = round(max(vals) / min(vals), 3) if vals else 1.0
            if spread[cls] > lib.get('density_spread_max', 1e9):
                report['reasons'].append('%s: texel density spread in class %s is %.2fx (max %.2fx): %s' % (
                    pk, cls, spread[cls], lib['density_spread_max'], ', '.join('%s %.0f' % (k, v['texels_per_m']) for k, v in sorted(roles.items()))))
        hf = {}
        tex_dir = root / 'kits' / 'library' / pk / 'textures'
        for role in sorted(kp['materials']):
            p = tex_dir / ('tex_%s_%s.png' % (pk, role))
            if p.is_file():
                hf[role] = texture_hf_energy(read_png(p))
        judged = {r: v for r, v in hf.items() if r not in exempt}
        over = {r: v for r, v in judged.items() if v > lib.get('hf_energy_max', 1e9)}
        if over:
            report['reasons'].append('%s: noisy textures (per-texel energy > %.3f): %s' % (
                pk, lib['hf_energy_max'], ', '.join('%s %.3f' % kv for kv in sorted(over.items()))))
        med = sorted(judged.values())[len(judged) // 2] if judged else 0.0
        if judged and med > lib.get('hf_energy_median_max', 1e9):
            report['reasons'].append('%s: median texture energy %.3f > %.3f' % (pk, med, lib['hf_energy_median_max']))
        report['packs'][pk] = {'density': dens, 'density_spread': spread, 'hf_energy': hf, 'hf_energy_median': med}
    report['status'] = 'failed' if report['reasons'] else 'passed'
    return report


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='n64_gate')
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('frames')
    g.add_argument('folder')
    g.add_argument('--theme')
    g.add_argument('--json', help='write the full report here')
    lb = sub.add_parser('library')
    lb.add_argument('--json', help='write the full report here')
    a = ap.parse_args(argv)
    if a.cmd == 'frames':
        theme = json.loads(Path(a.theme).read_text(encoding='utf-8')) if a.theme else {}
        rep = gate_folder(a.folder, theme)
        print('\n'.join(summary_lines(rep)))
    else:
        rep = library_report()
        print(json.dumps({k: v for k, v in rep.items() if k != 'packs'}, indent=1))
        for pk, v in rep['packs'].items():
            print(pk, 'spread', v['density_spread'], 'hf median', v['hf_energy_median'])
    if a.json:
        Path(a.json).write_bytes((json.dumps(rep, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return 0 if rep['status'] == 'passed' else 1


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
