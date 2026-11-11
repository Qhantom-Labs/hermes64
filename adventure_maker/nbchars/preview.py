"""Blender-free preview path: Godot import check (every clip plays, headless) and contact sheets (front / three-quarter
/ side / back turntable + clip keys, and an in-room game-scale shot) rendered by Godot, not Blender.

Drives tools/nbchars_godot (runtime GLTFDocument import, no editor cache). Godot's HOME/user data go to a scratch
directory, never into the repository. Stdlib only.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / 'tools' / 'nbchars_godot'
GODOT_DEFAULTS = ('/Applications/Godot.app/Contents/MacOS/Godot', 'godot4', 'godot')
TURNTABLE = [(0, 'front'), (45, 'three-quarter'), (90, 'side'), (180, 'back')]


def godot_path(configured=None):
    from .. import platforms
    if configured:
        cands = [configured]
    elif platforms.is_windows():
        cands = platforms.godot_candidates()
    else:
        cands = [c for c in (platforms.override('godot'),) if c] + list(GODOT_DEFAULTS)
    for c in cands:
        p = shutil.which(c) if not platforms.looks_like_path(c) else c
        if p and Path(p).is_file() and os.access(p, os.X_OK):
            return p
    return None


# Only what a headless/windowed Godot needs; never API keys, tokens, proxies or Hermes flags from the parent.
_ENV_KEEP = ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR',
             'SYSTEMROOT', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS',
             'PROCESSOR_ARCHITECTURE', 'TMPDIR', 'TEMP', 'TMP')


def child_env(home, base=None):
    """Scrubbed env for the Godot preview child: an allow-list of OS basics plus a scratch HOME (all OSes)."""
    base = os.environ if base is None else base
    env = {k: base[k] for k in _ENV_KEEP if k in base}
    env.setdefault('PATH', os.defpath)
    home = str(home)
    env.update(HOME=home, USERPROFILE=home, APPDATA=home, LOCALAPPDATA=home,
               XDG_CONFIG_HOME=home, XDG_DATA_HOME=home, XDG_CACHE_HOME=home)
    return env


def _run(godot, args, timeout, home):
    env = child_env(home)
    try:
        p = subprocess.run([godot, '--path', str(PROJECT)] + args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or ''), 'timeout'


def _clips_of(path):
    from ..rigkit import gltf
    doc, _ = gltf.parse(Path(path).read_bytes())
    return [a['name'] for a in doc.get('animations', [])]


def _bounds(path):
    """(height, horizontal extent) of the rest mesh from the POSITION accessor bounds, metres."""
    from ..rigkit import gltf
    doc, _ = gltf.parse(Path(path).read_bytes())
    lo, hi = None, None
    for m in doc.get('meshes', []):
        for p in m['primitives']:
            a = doc['accessors'][p['attributes']['POSITION']]
            if 'min' in a and 'max' in a:
                lo = list(a['min']) if lo is None else [min(x, y) for x, y in zip(lo, a['min'])]
                hi = list(a['max']) if hi is None else [max(x, y) for x, y in zip(hi, a['max'])]
    if lo is None:
        return 1.0, 1.0
    return hi[1] - lo[1], max(hi[0] - lo[0], hi[2] - lo[2])


def _height(path):
    return _bounds(path)[0]


def import_check(glbs, out, godot_path_=None, clips=None, timeout=600):
    """Headless: every GLB imports and every clip (default: every animation in the file) plays at 15 fps STEP."""
    godot = godot_path(godot_path_)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not godot:
        return {'ok': False, 'reason': 'Godot not found; configure godot_path'}
    spec = [{'path': str(Path(g).resolve()), 'clips': list(clips) if clips else _clips_of(g)} for g in glbs]
    sp = out / 'godot_play_spec.json'
    sp.write_bytes(json.dumps(spec, indent=1).encode('utf-8'))
    home = Path(tempfile.mkdtemp(prefix='nbchars-godot-', dir=os.environ.get('TMPDIR')))
    rc, so, se = _run(godot, ['--headless', '--', 'mode=play', 'spec=' + str(sp), 'watchdog=%d' % (timeout - 20)], timeout, home)
    (out / 'godot_play.log').write_bytes((so + '\n--- stderr ---\n' + se).encode('utf-8'))
    shutil.rmtree(home, ignore_errors=True)
    rep = {'godot': None, 'play': {}, 'exit_code': rc}
    for line in so.splitlines():
        m = re.match(r'CHECK godot=(\S+)', line)
        if m:
            rep['godot'] = m.group(1)
        m = re.match(r'CHECK (\S+\.glb) clip (\S+) (PLAYS|FAIL|MISSING)(.*)', line)
        if m:
            rep['play'].setdefault(m.group(1), {})[m.group(2)] = {'status': m.group(3), 'info': m.group(4).strip()}
    n_ok = sum(1 for f in rep['play'].values() for c in f.values() if c['status'] == 'PLAYS')
    n_exp = sum(len(s['clips']) for s in spec)
    rep['summary'] = {'files': len(spec), 'files_reported': len(rep['play']), 'clips_expected': n_exp,
                      'clips_playing': n_ok}
    rep['ok'] = rc == 0 and n_ok == n_exp and len(rep['play']) == len(spec)
    (out / 'godot_play_report.json').write_bytes(json.dumps(rep, indent=1, sort_keys=True).encode('utf-8'))
    return rep


def contact_sheets(glbs, out, godot_path_=None, clips=('idle', 'walk'), per_sheet=5, room=True, timeout=240,
                   keys=(4, 8)):
    """Windowed Godot captures: <out>/sheet_NN.png (rows = files; columns = front/three-quarter/side/back at the first
    clip key 0, then clip keys) and <out>/room.png (every file at game scale in a room with a 1 m cube)."""
    godot = godot_path(godot_path_)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not godot:
        return {'ok': False, 'reason': 'Godot not found; configure godot_path'}
    home = Path(tempfile.mkdtemp(prefix='nbchars-godot-', dir=os.environ.get('TMPDIR')))
    shots = []
    glbs = sorted((str(Path(g).resolve()) for g in glbs), key=lambda g: -_height(g))   # similar sizes share a sheet
    for s in range(0, len(glbs), per_sheet):
        rows = []
        for g in glbs[s:s + per_sheet]:
            have = _clips_of(g)
            first = next((c for c in clips if c in have), have[0] if have else '')
            views = [[yaw, first, 0] for yaw, _ in TURNTABLE]
            for c in clips:
                if c in have:
                    views += [[35, c, k] for k in keys]
            rows.append({'path': g, 'label': Path(g).stem, 'views': views})
        name = out / ('sheet_%02d.png' % (s // per_sheet))
        b = [_bounds(g) for g in glbs[s:s + per_sheet]]
        h = max(x[0] for x in b)
        ext = max(x[1] for x in b)
        row_h = max(0.75, 1.3 * h)
        spacing = max(0.55, 0.7 * h, 1.05 * ext)
        cols = max(len(r['views']) for r in rows)
        cam = max(row_h * len(rows) + 0.3 * h, (cols * spacing + 2.0 * row_h) * 9.0 / 16.0)
        spec = {'out': str(name), 'rows': rows, 'cam_size': cam, 'row_h': row_h, 'spacing': spacing,
                'label_size': max(0.0012, 0.0024 * h)}
        sp = out / ('sheet_%02d.json' % (s // per_sheet))
        sp.write_bytes(json.dumps(spec, indent=1).encode('utf-8'))
        rc, so, se = _run(godot, ['--resolution', '1600x900', '--', 'mode=sheet', 'spec=' + str(sp), 'watchdog=%d' % (timeout - 20)],
                          timeout, home)
        (out / ('sheet_%02d.log' % (s // per_sheet))).write_bytes((so + '\n--- stderr ---\n' + se).encode('utf-8'))
        shots.append({'png': str(name) if name.is_file() else None, 'exit_code': rc, 'files': [r['label'] for r in rows]})
    if room:
        rows = [{'path': g, 'label': Path(g).stem,
                 'views': [[20, next((c for c in clips if c in _clips_of(g)), ''), 0]]} for g in glbs[:10]]
        spec = {'out': str(out / 'room.png'), 'rows': rows, 'room': True, 'spacing': 0.95}
        sp = out / 'room.json'
        sp.write_bytes(json.dumps(spec, indent=1).encode('utf-8'))
        rc, so, se = _run(godot, ['--resolution', '1600x900', '--', 'mode=sheet', 'spec=' + str(sp), 'watchdog=%d' % (timeout - 20)],
                          timeout, home)
        (out / 'room.log').write_bytes((so + '\n--- stderr ---\n' + se).encode('utf-8'))
        shots.append({'png': str(out / 'room.png') if (out / 'room.png').is_file() else None, 'exit_code': rc, 'room': True})
    shutil.rmtree(home, ignore_errors=True)
    rep = {'ok': all(s['png'] for s in shots), 'shots': shots, 'renderer': 'Godot (no Blender)'}
    (out / 'contact_sheets.json').write_bytes(json.dumps(rep, indent=1).encode('utf-8'))
    return rep
