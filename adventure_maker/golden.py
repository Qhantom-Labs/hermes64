"""Golden-image regression for 320x240 room captures (stdlib only).

A perceptual pixel diff in the style of pixelmatch (ISC; re-implemented here, no dependency): YIQ colour distance
with a threshold, anti-aliasing tolerance (a differing pixel that is an anti-aliased edge in either image is not
counted) and region masks taken from the capture harness's region pass (`<room>-mask.png`: chrome/glass, window
views, sky, emissive, ground). Every room is compared with a blessed golden; mismatch is reported per region.

Goldens live in `goldens/<game>/<room>.png` with `goldens/<game>/manifest.json`. `bless` copies the current capture
(an explicit, deliberate act: re-bless after an intended look change). `approve` records that a human looked at
the goldens and accepted them. Similarity to a golden is NOT art approval: it only proves "unchanged since the
blessed render", and a blessed-but-unapproved golden says so in every report.

  python3 -m adventure_maker.golden compare CAPTURE_DIR --goldens goldens/thaw
  python3 -m adventure_maker.golden bless CAPTURE_DIR --goldens goldens/thaw --by NAME [--note TEXT]
  python3 -m adventure_maker.golden approve --goldens goldens/thaw --by NAME
  python3 -m adventure_maker.golden controls [CAPTURE_DIR] --goldens goldens/thaw --out DIR
"""
import datetime
import hashlib
import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

from .style_gate import read_png

MAX_DELTA = 35215.0
REGIONS = {  # mask colour (r, g, b) bits written by n64_world.gdshader debug pass 2
    'chrome': (1, 0, 0), 'window': (0, 1, 0), 'sky': (0, 0, 1), 'emissive': (1, 1, 0), 'ground': (0, 1, 1),
}
DEFAULT_LIMITS = {'frame': 0.02, 'chrome': 0.06, 'window': 0.06, 'sky': 0.06, 'emissive': 0.08, 'ground': 0.06}
MIN_REGION_PX = 40


def _yiq(r, g, b):
    return (r * 0.29889531 + g * 0.58662247 + b * 0.11448223,
            r * 0.59597799 - g * 0.27417610 - b * 0.32180189,
            r * 0.21147017 - g * 0.52261711 + b * 0.31114694)


def colour_delta(a, b):
    y1, i1, q1 = _yiq(*a)
    y2, i2, q2 = _yiq(*b)
    return 0.5053 * (y1 - y2) ** 2 + 0.299 * (i1 - i2) ** 2 + 0.1957 * (q1 - q2) ** 2


def _px(img, x, y):
    w, _, rgb = img
    o = 3 * (y * w + x)
    return rgb[o], rgb[o + 1], rgb[o + 2]


def _bright(c):
    return _yiq(*c)[0]


def _many_siblings(img, x1, y1):
    w, h, _ = img
    c = _px(img, x1, y1)
    zeros = 1 if x1 in (0, w - 1) or y1 in (0, h - 1) else 0
    for y in range(max(y1 - 1, 0), min(y1 + 1, h - 1) + 1):
        for x in range(max(x1 - 1, 0), min(x1 + 1, w - 1) + 1):
            if (x, y) != (x1, y1) and _px(img, x, y) == c:
                zeros += 1
                if zeros > 2:
                    return True
    return False


def antialiased(img, x1, y1, other):
    """pixelmatch's anti-aliasing detector (Vysniauskas 2009): an edge pixel between a darkest and a brightest
    neighbour that both have flat siblings in both images."""
    w, h, _ = img
    zeros = 1 if x1 in (0, w - 1) or y1 in (0, h - 1) else 0
    mn = mx = 0.0
    minp = maxp = None
    b0 = _bright(_px(img, x1, y1))
    for y in range(max(y1 - 1, 0), min(y1 + 1, h - 1) + 1):
        for x in range(max(x1 - 1, 0), min(x1 + 1, w - 1) + 1):
            if (x, y) == (x1, y1):
                continue
            delta = _bright(_px(img, x, y)) - b0
            if delta == 0:
                zeros += 1
                if zeros > 2:
                    return False
            elif delta < mn:
                mn, minp = delta, (x, y)
            elif delta > mx:
                mx, maxp = delta, (x, y)
    if mn == 0 or mx == 0 or minp is None or maxp is None:
        return False
    return ((_many_siblings(img, *minp) and _many_siblings(other, *minp)) or
            (_many_siblings(img, *maxp) and _many_siblings(other, *maxp)))


def region_of(mask, i):
    if mask is None:
        return None
    _, _, m = mask
    bits = (int(m[3 * i] > 127), int(m[3 * i + 1] > 127), int(m[3 * i + 2] > 127))
    for name, want in REGIONS.items():
        if bits == want:
            return name
    return None


def diff(a, b, mask=None, threshold=0.1, include_aa=False):
    """Compare two (w, h, rgb) images. Returns counts per region and the list of differing pixel indices."""
    w, h, pa = a
    w2, h2, pb = b
    if (w, h) != (w2, h2):
        raise ValueError('image sizes differ: %sx%s vs %sx%s' % (w, h, w2, h2))
    limit = MAX_DELTA * threshold * threshold
    counts = {'frame': [0, w * h]}
    for name in REGIONS:
        counts[name] = [0, 0]
    aa = 0
    bad = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            reg = region_of(mask, i)
            if reg:
                counts[reg][1] += 1
            ca = (pa[3 * i], pa[3 * i + 1], pa[3 * i + 2])
            cb = (pb[3 * i], pb[3 * i + 1], pb[3 * i + 2])
            if ca == cb:
                continue
            if colour_delta(ca, cb) <= limit:
                continue
            if not include_aa and (antialiased(a, x, y, b) or antialiased(b, x, y, a)):
                aa += 1
                continue
            counts['frame'][0] += 1
            if reg:
                counts[reg][0] += 1
            bad.append(i)
    return {'counts': counts, 'antialiased_ignored': aa, 'bad': bad}


def judge(result, limits=None):
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    why = []
    frac = {}
    for name, (n_bad, n_all) in result['counts'].items():
        if n_all < (1 if name == 'frame' else MIN_REGION_PX):
            continue
        f = n_bad / n_all
        frac[name] = round(f, 4)
        if f > limits.get(name, 1.0):
            why.append('%s region changed: %.1f%% of %d px differ (limit %.1f%%)' % (name, 100 * f, n_all, 100 * limits[name]))
    return frac, why


def _manifest(goldens):
    p = Path(goldens) / 'manifest.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {'format': 'hermes64-goldens/1', 'rooms': {}, 'approved': None}


def compare(capture, goldens, limits=None, threshold=0.1):
    capture, goldens = Path(capture), Path(goldens)
    man = _manifest(goldens)
    cap = json.loads((capture / 'capture.json').read_text(encoding='utf-8'))
    rows = []
    for row in cap['rooms']:
        rid = row['id']
        gold = goldens / (rid + '.png')
        if not gold.is_file():
            rows.append({'id': rid, 'status': 'no_golden', 'reasons': ['no blessed golden for this room']})
            continue
        clean = capture / row.get('clean', rid + '-clean.png')
        mask = capture / row.get('mask', rid + '-mask.png')
        if not mask.is_file():
            mask = goldens / (rid + '-mask.png')
        if not clean.is_file():
            rows.append({'id': rid, 'status': 'changed', 'reasons': ['capture missing ' + clean.name]})
            continue
        res = diff(read_png(gold), read_png(clean), read_png(mask) if mask.is_file() else None, threshold)
        frac, why = judge(res, limits)
        rows.append({'id': rid, 'status': 'passed' if not why else 'changed', 'fractions': frac, 'reasons': why,
                     'antialiased_ignored': res['antialiased_ignored']})
    approved = man.get('approved')
    status = 'passed' if rows and all(r['status'] == 'passed' for r in rows) else 'changed'
    return {'status': status, 'rooms': rows, 'approved': approved,
            'note': ('goldens approved by %s on %s' % (approved['by'], approved['at'])) if approved else
                    'goldens are blessed renders NOT yet approved by a human; similarity is not art approval',
            'scope': 'perceptual pixel diff vs blessed goldens (YIQ threshold %.2f, anti-aliasing tolerant, per-region)' % threshold}


def bless(capture, goldens, by, note=''):
    capture, goldens = Path(capture), Path(goldens)
    goldens.mkdir(parents=True, exist_ok=True)
    man = _manifest(goldens)
    cap = json.loads((capture / 'capture.json').read_text(encoding='utf-8'))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for row in cap['rooms']:
        src = capture / row.get('clean', row['id'] + '-clean.png')
        dst = goldens / (row['id'] + '.png')
        shutil.copyfile(src, dst)
        msk = capture / row.get('mask', row['id'] + '-mask.png')
        if msk.is_file():
            shutil.copyfile(msk, goldens / (row['id'] + '-mask.png'))
        man['rooms'][row['id']] = {'sha256': hashlib.sha256(dst.read_bytes()).hexdigest(), 'blessed_by': by, 'blessed_at': stamp,
                                   'note': note}
    man['approved'] = None  # any re-bless needs a fresh human approval
    (goldens / 'manifest.json').write_bytes((json.dumps(man, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return man


def approve(goldens, by):
    goldens = Path(goldens)
    man = _manifest(goldens)
    for rid, row in man['rooms'].items():
        if hashlib.sha256((goldens / (rid + '.png')).read_bytes()).hexdigest() != row['sha256']:
            raise SystemExit('golden %s changed since it was blessed; re-bless first' % rid)
    man['approved'] = {'by': by, 'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    (goldens / 'manifest.json').write_bytes((json.dumps(man, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return man


# ------------------------------------------------------------------ known-bad controls
def write_png(path, img):
    w, h, rgb = img
    raw = b''.join(b'\x00' + bytes(rgb[3 * y * w:3 * (y + 1) * w]) for y in range(h))

    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def control(img, mask, kind, fog=(150, 160, 200)):
    """Synthesise a known-bad variant of a good capture: washed_out, flat_chrome, empty_window, missing_vista."""
    w, h, rgb = img
    out = bytearray(rgb)
    regions = [region_of(mask, i) for i in range(w * h)] if mask is not None else [None] * (w * h)

    def mean(sel):
        idx = [i for i in range(w * h) if regions[i] in sel]
        if not idx:
            return None
        return tuple(sum(rgb[3 * i + c] for i in idx) // len(idx) for c in range(3))
    if kind == 'washed_out':
        for i in range(w * h):
            for c in range(3):
                v = rgb[3 * i + c] * 0.45 + fog[c] * 0.55
                out[3 * i + c] = int(max(0, min(255, (v - 128) * 0.7 + 128)))
    elif kind in ('flat_chrome', 'empty_window', 'missing_vista'):
        sel = {'flat_chrome': ('chrome',), 'empty_window': ('window',), 'missing_vista': ('sky', 'window')}[kind]
        fill = mean(sel) if kind == 'flat_chrome' else (mean((None,)) or fog)
        if kind == 'missing_vista':
            fill = fog
        for i in range(w * h):
            if regions[i] in sel and fill is not None:
                out[3 * i:3 * i + 3] = bytes(fill)
    else:
        raise ValueError('unknown control %r' % kind)
    return w, h, bytes(out)


def controls(capture, goldens, out_dir, kinds=('washed_out', 'flat_chrome', 'empty_window', 'missing_vista')):
    """Build each control from the golden itself and check that the diff flags it (where the region exists).
    capture may be None: the blessed goldens and their region masks are used directly."""
    goldens, out_dir = Path(goldens), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rids = sorted(_manifest(goldens)['rooms']) if capture is None else [r['id'] for r in json.loads((Path(capture) / 'capture.json').read_text(encoding='utf-8'))['rooms']]
    rows = []
    for rid in rids:
        gold = goldens / (rid + '.png')
        mpath = (Path(capture) / (rid + '-mask.png')) if capture is not None else None
        if mpath is None or not mpath.is_file():
            mpath = goldens / (rid + '-mask.png')
        if not gold.is_file() or not mpath.is_file():
            continue
        g, m = read_png(gold), read_png(mpath)
        present = {}
        for i in range(g[0] * g[1]):
            reg = region_of(m, i)
            present[reg] = present.get(reg, 0) + 1
        needs = {'flat_chrome': ('chrome',), 'empty_window': ('window',), 'missing_vista': ('sky', 'window')}
        for kind in kinds:
            bad = control(g, m, kind)
            area = sum(present.get(r, 0) for r in needs.get(kind, ())) if kind in needs else g[0] * g[1]
            if bad[2] == g[2] or area < MIN_REGION_PX:
                # the room has no (measurable) region of that kind: nothing to break, nothing claimed
                rows.append({'id': rid, 'control': kind, 'status': 'not_applicable', 'region_px': area})
                continue
            res = diff(g, bad, m, include_aa=True)
            if res['counts']['frame'][0] < MIN_REGION_PX:
                # the defect is already present (e.g. chrome that is flat in the golden): the control changes
                # nothing measurable, so it cannot test anything here
                rows.append({'id': rid, 'control': kind, 'status': 'not_applicable', 'changed_px': res['counts']['frame'][0]})
                continue
            write_png(out_dir / ('%s-%s.png' % (rid, kind)), bad)
            frac, why = judge(diff(g, bad, m))
            rows.append({'id': rid, 'control': kind, 'status': 'flagged' if why else 'MISSED', 'reasons': why})
    missed = [r for r in rows if r['status'] == 'MISSED']
    return {'status': 'passed' if rows and not missed else 'failed', 'controls': rows}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='golden')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('compare'); c.add_argument('capture'); c.add_argument('--goldens', required=True)
    b = sub.add_parser('bless'); b.add_argument('capture'); b.add_argument('--goldens', required=True); b.add_argument('--by', required=True)
    b.add_argument('--note', default='')
    a = sub.add_parser('approve'); a.add_argument('--goldens', required=True); a.add_argument('--by', required=True)
    k = sub.add_parser('controls'); k.add_argument('capture', nargs='?'); k.add_argument('--goldens', required=True); k.add_argument('--out', required=True)
    x = ap.parse_args(argv)
    if x.cmd == 'compare':
        r = compare(x.capture, x.goldens)
        print(json.dumps(r, indent=2))
        return 0 if r['status'] == 'passed' else 1
    if x.cmd == 'bless':
        bless(x.capture, x.goldens, x.by, x.note)
        print('blessed', x.goldens, '(not approved; run approve after a human review)')
        return 0
    if x.cmd == 'approve':
        approve(x.goldens, x.by)
        print('approved', x.goldens, 'by', x.by)
        return 0
    r = controls(x.capture, x.goldens, x.out)
    print(json.dumps(r, indent=2))
    return 0 if r['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
