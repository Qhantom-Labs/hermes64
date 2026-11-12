"""ROOMLOOK round harness: real facade build + real Godot captures + style gate + reference contact sheets.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.roomlook capture --round 3 [--games thaw,last_light]
        [--refs PRIVATE.json --private-out DIR_OUTSIDE_REPO] [--rooms snow_field,fog_street]
  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.roomlook gate DIR --theme THEME.json

Projects are created fresh under evidence/roomlook/<round>/projects through the same Service facade a
user drives (scaffold -> compile -> check -> build_assets -> open screenshots). The committed tool names no
reference images: private study references are supplied at run time by a JSON file kept outside the
repository ({room_id: [absolute image paths]}); sheets that contain reference pixels are written only to a
--private-out directory outside the repository. The in-repo sheet (gitignored evidence/) shows our renders,
gate verdicts and, for exteriors, the distance/region passes the gate measured.
"""
from pathlib import Path
import argparse, datetime, json, shutil, subprocess, sys, time
from adventure_maker.service import Service
from adventure_maker import golden, style_gate

R = Path(__file__).resolve().parents[1]
PACKS = {'thaw': 'polar_pod', 'last_light': 'n64_v0'}

# ---------------------------------------------------------------- tiny canvas + 3x5 label font
_G = {
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "110101110100100",
    "Q": "010101101111011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111", "0": "111101101101111", "1": "010110010010111",
    "2": "110001010100111", "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
    "6": "011100111101111", "7": "111001010010010", "8": "111101111101111", "9": "111101111001110",
    ".": "000000000000010", "_": "000000000000111", "-": "000000111000000", " ": "000000000000000",
    ":": "000010000010000", "/": "001001010100100", "=": "000111000111000", "(": "010100100100010",
    ")": "010001001001010", "+": "000010111010000", ",": "000000000010100", "%": "101001010100101",
}


class Canvas:
    def __init__(self, w, h, bg=(18, 18, 22)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def blit(self, img, ox, oy, scale=1):
        w, h, rgb = img
        for y in range(h * scale):
            sy = y // scale
            ty = oy + y
            if not 0 <= ty < self.h:
                continue
            row = rgb[sy * w * 3:(sy + 1) * w * 3]
            if scale == 1:
                line = row
            else:
                line = bytearray(w * scale * 3)
                for x in range(w):
                    c = row[3 * x:3 * x + 3]
                    for k in range(scale):
                        line[3 * (x * scale + k):3 * (x * scale + k) + 3] = c
            n = min(len(line) // 3, self.w - ox)
            self.px[3 * (ty * self.w + ox):3 * (ty * self.w + ox + n)] = line[:3 * n]

    def text(self, s, x, y, col=(235, 235, 240), scale=2):
        s = s.upper()
        for i, ch in enumerate(s):
            g = _G.get(ch, _G[" "])
            for r in range(5):
                for c in range(3):
                    if g[r * 3 + c] == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                X = x + (i * 4 + c) * scale + dx
                                Y = y + r * scale + dy
                                if 0 <= X < self.w and 0 <= Y < self.h:
                                    self.px[3 * (Y * self.w + X):3 * (Y * self.w + X) + 3] = bytes(col)

    def save(self, path):
        import struct, zlib
        raw = b''.join(b'\x00' + bytes(self.px[3 * y * self.w:3 * (y + 1) * self.w]) for y in range(self.h))

        def chunk(tag, body):
            return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)
        Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0)) +
                               chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def outside_repo(path):
    path = Path(path).resolve()
    if path == R or R in path.parents:
        raise SystemExit('private study material must stay outside the repository: %s' % path)
    return path


def ref_crop(src, cache):
    """4:3 centre crop of a private reference, 320x240, via macOS sips into a cache OUTSIDE the repository."""
    src = Path(src)
    import hashlib
    out = outside_repo(cache) / (hashlib.sha1(str(src).encode()).hexdigest()[:16] + '.png')
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    from adventure_maker.runner import scratch_env
    with scratch_env() as env:
        info = subprocess.run(['/usr/bin/sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(src)], capture_output=True, text=True, env=env).stdout
    w = int(info.split('pixelWidth:')[1].split()[0])
    h = int(info.split('pixelHeight:')[1].split()[0])
    cw, ch = (int(h * 4 / 3), h) if w * 3 > h * 4 else (w, int(w * 3 / 4))
    tmp = out.with_suffix('.tmp.png')
    with scratch_env() as env:
        subprocess.run(['/usr/bin/sips', '-s', 'format', 'png', '-c', str(ch), str(cw), str(src), '--out', str(tmp)], check=True, capture_output=True, env=env)
        subprocess.run(['/usr/bin/sips', '-z', '240', '320', str(tmp), '--out', str(out)], check=True, capture_output=True, env=env)
    tmp.unlink()
    return out


def contact_sheet(rows, out, title, cols=2):
    """rows: [(label, [png, ...], [caption, ...], verdict_lines)] -> up to `cols` 640x480 cells per row."""
    cell_w, cell_h, pad, head = 640, 480, 8, 56
    W = pad + cols * (cell_w + pad)
    H = 40 + len(rows) * (cell_h + head + pad)
    cv = Canvas(W, H)
    cv.text(title, pad, 12, scale=3)
    y = 40
    for label, images, captions, verdict in rows:
        cv.text(label, pad, y + 4, (255, 230, 160), 2)
        for k, line in enumerate(verdict[:3]):
            cv.text(line[:200], pad, y + 18 + 12 * k, (190, 200, 230) if 'PASS' in line else (255, 150, 140), 2)
        for j, img in enumerate(images[:cols]):
            pic = style_gate.read_png(img)
            sc = 2 if pic[0] <= 320 else 1
            cv.blit(pic, pad + j * (cell_w + pad), y + head, sc)
            if j < len(captions) and captions[j]:
                cv.text(captions[j], pad + j * (cell_w + pad) + 6, y + head + 6, (255, 255, 255), 2)
        y += cell_h + head + pad
    cv.save(out)
    return out


def false_colour(depth_png, mask_png, out):
    """Readable 320x240 visual of the gate's passes: distance bands tinted (near warm, mid green, far blue),
    sky white, void magenta."""
    w, h, d = style_gate.read_png(depth_png)
    _, _, m = style_gate.read_png(mask_png)
    cv = Canvas(w, h)
    for i in range(w * h):
        r, g, b = m[3 * i], m[3 * i + 1], m[3 * i + 2]
        v = d[3 * i]
        if r < 60 and g < 60 and b > 190:
            c = (235, 235, 245)
        elif v >= 254 and r < 8 and g < 8 and b < 8:
            c = (255, 0, 255)
        else:
            dist = v / 255.0 * 120.0
            shade = max(0.35, 1.0 - dist / 140.0)
            base = (230, 140, 60) if dist < 10 else ((90, 200, 90) if dist < 32 else (90, 120, 230))
            c = tuple(int(x * shade) for x in base)
        cv.px[3 * i:3 * i + 3] = bytes(c)
    cv.save(out)
    return out


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def capture(round_id, games, seconds=40, refs=None, private_out=None, only_rooms=None, actors=False, out_root='evidence/roomlook'):
    refs = refs or {}
    if private_out:
        private_out = outside_repo(private_out)
    out = R / out_root / ('round-' + str(round_id))
    out.mkdir(parents=True, exist_ok=False)
    projects = out / 'projects'
    projects.mkdir()
    svc = Service({'bundle_root': str(R), 'projects_root': str(projects)})
    log = []

    def call(name, project, **args):
        t0 = time.monotonic()
        result = json.loads(svc.handle('hermes64_' + name, dict(project=project, **args)))
        if result.get('truncated'):
            result = json.loads((projects / project / result['report_path']).read_text(encoding='utf-8'))
        log.append({'tool': name, 'project': project, 'seconds': round(time.monotonic() - t0, 2),
                    'status': result.get('status', result.get('error')), 'ok': result.get('ok')})
        (out / 'calls.json').write_text(json.dumps(log, indent=2), encoding='utf-8')
        print(project, name, result.get('status', result.get('error')), '%.1fs' % (time.monotonic() - t0), flush=True)
        return result

    summary = {'round': round_id, 'started': stamp(), 'games': {}}
    for game in games:
        source = json.loads((R / 'examples' / game / 'spec.json').read_text(encoding='utf-8'))
        source['metadata']['presentation'] = json.loads((R / 'examples' / game / 'presentation.json').read_text(encoding='utf-8'))
        if actors:
            # Real imported characters through the character lane's additive adapter (read-only use: staging
            # overlay + generated-runtime bindings). The ordinary facade keeps its markers until Main adopts it.
            from characters.integration import apply_presentation
            source = apply_presentation(source, game)
        assert call('scaffold', game, pack=PACKS[game], spec_json=json.dumps(source))['ok']
        assert call('compile', game, spec_path='source/spec.json')['ok']
        assert call('check', game)['ok']
        built = call('build_assets', game, seed=7)
        if not built.get('ok'):
            print(json.dumps(built)[:3000])
            raise SystemExit('build_assets failed')
        if actors:
            from characters.integration import CharacterComponents
            project = svc.project(game)
            folder = svc.folder(project, 'actor-capture')
            opened = CharacterComponents(svc.settings, project).open(svc.current(project)['game'], folder, seconds, screenshots=True)
            (projects / game / folder / 'open.process.json').write_text(json.dumps(opened, indent=1), encoding='utf-8')
            print(game, 'open (real actors)', opened.get('returncode'), flush=True)
            run = projects / game / folder
        else:
            opened = call('open', game, seconds=seconds, screenshots=True)
            run = projects / game / Path(opened.get('report_path', '.')).parent
        cap = opened.get('capture')
        if not isinstance(cap, dict):
            print(json.dumps(opened)[:4000])
            raise SystemExit('capture failed')
        dest = out / game
        shutil.copytree(run / 'screens', dest)
        theme = json.loads((run / 'runtime' / 'theme.json').read_text(encoding='utf-8'))
        (dest / 'theme.json').write_text(json.dumps(theme, indent=2), encoding='utf-8')
        report = style_gate.gate_directory(dest, theme)  # full metrics (the service returns a summary)
        (dest / 'style-gate.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        lines = style_gate.summary_lines(report)
        gold = None
        gdir = R / 'goldens' / (game + ('-actors' if actors else ''))
        if (gdir / 'manifest.json').is_file():
            gold = golden.compare(dest, gdir)
            (dest / 'golden.json').write_text(json.dumps(gold, indent=2), encoding='utf-8')
            lines += ['GOLDEN %s (%s)' % (gold['status'].upper(), gold['note'])]
            lines += ['  %-18s %s %s' % (g['id'], g['status'], '; '.join(g['reasons'])) for g in gold['rooms']]
        (dest / 'style-gate.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print('\n'.join(lines))
        rows, private_rows = [], []
        for r in report['rooms']:
            if only_rooms and r['id'] not in only_rooms:
                continue
            m = r.get('metrics', {})
            crow = next((x for x in cap['rooms'] if x['id'] == r['id']), {})
            split = crow.get('triangles_split') or {}
            tris = '%s (env %s + actors %s)' % (crow.get('triangles', '?'), split.get('environment', '?'),
                                                split.get('actors', 0) + split.get('player', 0)) if split else crow.get('triangles', '?')
            verdict = ['%s  contrast %.2f  fog %.2f  flat %.2f  p2 %.2f  edges %.2f  void %.3f  tris %s' % (
                'PASS' if r['status'] == 'passed' else 'FAIL', m.get('contrast_range', 0), m.get('fog_swallowed_fraction', 0),
                m.get('flat_fraction', 0), m.get('luma_p2', 0), m.get('edge_density', 0), m.get('void_fraction', 0), tris)]
            verdict += ['- ' + w for w in r.get('reasons', [])[:2]]
            clean = dest / (r['id'] + '-clean.png')
            images, captions = [clean], ['']
            if r.get('exterior') and (dest / (r['id'] + '-depth.png')).is_file():
                images.append(false_colour(dest / (r['id'] + '-depth.png'), dest / (r['id'] + '-mask.png'), dest / (r['id'] + '-bands.png')))
                captions.append('GATE PASSES: NEAR / MID / FAR / SKY')
            rows.append((r['id'], images, captions, verdict))
            if private_out and refs.get(r['id']):
                crops = [ref_crop(x, private_out / 'ref-cache') for x in refs[r['id']][:2] if Path(x).is_file()]
                private_rows.append((r['id'], [clean] + crops, [''] + ['PRIVATE STUDY REF'] * len(crops), verdict))
        title = 'ROOMLOOK ROUND %s  %s%s  GATE %s' % (round_id, game, ' REAL ACTORS' if actors else '', report['status'].upper())
        sheet = contact_sheet(rows, out / ('sheet-' + game + '.png'), title)
        if private_rows:
            psheet = private_out / ('round-%s-sheet-%s.png' % (round_id, game))
            psheet.parent.mkdir(parents=True, exist_ok=True)
            contact_sheet(private_rows, psheet, title, cols=3)
            print('private study sheet (outside repo):', psheet)
        summary['games'][game] = {'gate': report['status'], 'sheet': str(sheet.relative_to(R)), 'golden': gold and gold['status'],
                                  'rooms': {r['id']: {'status': r['status'], 'metrics': r.get('metrics'), 'reasons': r.get('reasons')} for r in report['rooms']},
                                  'triangles': {x['id']: x['triangles'] for x in cap['rooms']},
                                  'triangles_split': {x['id']: x.get('triangles_split') for x in cap['rooms']}, 'actors': actors}
    summary['finished'] = stamp()
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({g: v['gate'] for g, v in summary['games'].items()}))
    return summary


def main(argv):
    ap = argparse.ArgumentParser(prog='roomlook')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--round', required=True)
    c.add_argument('--games', default='thaw,last_light')
    c.add_argument('--seconds', type=int, default=40)
    c.add_argument('--refs', help='private JSON {room_id: [absolute image paths]} kept outside the repository')
    c.add_argument('--private-out', help='directory outside the repository for sheets containing reference pixels')
    c.add_argument('--rooms', default='', help='only these rooms on the sheets (all rooms are still gated)')
    c.add_argument('--actors', action='store_true', help='stage the imported real characters (character-lane adapter)')
    c.add_argument('--out-root', default='evidence/roomlook', help='evidence folder (inside the repository, gitignored)')
    g = sub.add_parser('gate')
    g.add_argument('folder')
    g.add_argument('--theme')
    a = ap.parse_args(argv)
    if a.cmd == 'capture':
        refs = json.loads(outside_repo(a.refs).read_text(encoding='utf-8')) if a.refs else {}
        capture(a.round, a.games.split(','), a.seconds, refs, a.private_out, [x for x in a.rooms.split(',') if x], a.actors,
                a.out_root)
        return 0
    theme = json.loads(Path(a.theme).read_text(encoding='utf-8')) if a.theme else {}
    report = style_gate.gate_directory(a.folder, theme)
    print('\n'.join(style_gate.summary_lines(report)))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
