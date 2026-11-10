"""Exporter choice + one-line doctor truth. Stdlib only (the doctor imports this without numpy)."""
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARITY = HERE / 'PARITY.json'
# the code a parity verdict was proven on: the vendored generator (VENDORED-GEN.json) + the exporter modules
EXPORTER_FILES = ('adventure_maker/nbchars/api.py', 'adventure_maker/nbchars/assemble.py',
                  'adventure_maker/nbchars/blendmath.py', 'adventure_maker/nbchars/gen.py',
                  'adventure_maker/nbchars/pycompat.py', 'adventure_maker/nbchars/scene.py',
                  'adventure_maker/nbchars/writer.py', 'adventure_maker/rigkit/gltf.py')
CHOICES = ('python', 'blender', 'auto')
BLENDER_DEFAULTS = ('/Applications/Blender.app/Contents/MacOS/Blender', '/opt/homebrew/bin/blender', 'blender')


def numpy_version():
    if importlib.util.find_spec('numpy') is None:
        return None
    try:
        import numpy
        return numpy.__version__
    except Exception:   # noqa: BLE001  (a broken numpy counts as missing)
        return None


def fingerprint(repo=None):
    """sha256 over (path, sha256) of every vendored generator file and exporter module, sorted by path."""
    repo = Path(repo or REPO)
    files = list(EXPORTER_FILES)
    try:
        files += [f['file'] for f in json.loads((HERE / 'VENDORED-GEN.json').read_text())['files']]
    except (OSError, ValueError, KeyError):
        return None
    h = hashlib.sha256()
    for rel in sorted(files):
        try:
            data = (repo / rel).read_bytes()
        except OSError:
            return None
        h.update(('%s %s\n' % (rel, hashlib.sha256(data).hexdigest())).encode())
    return h.hexdigest()


def parity():
    """The committed parity verdict; 'STALE' when the generator or exporter code changed since it was proven."""
    try:
        rec = json.loads(PARITY.read_text())
    except (OSError, ValueError):
        return {'verdict': 'MISSING', 'note': 'no committed parity verdict (adventure_maker/nbchars/PARITY.json)'}
    fp = fingerprint()
    if rec.get('verdict') == 'PASS' and rec.get('fingerprint') != fp:
        return dict(rec, verdict='STALE', proven_verdict='PASS',
                    note='generator or exporter files changed since the parity run; re-run: python3 -m adventure_maker.nbchars '
                         'parity --oracle <published> --out <dir> --write-verdict')
    return rec


def _blender_path(settings):
    """Resolved Blender executable or None. When blender_path is configured it is the only candidate; otherwise the
    standard install locations and PATH are tried."""
    configured = (settings or {}).get('blender_path') or ''
    cands = [configured] if configured else list(BLENDER_DEFAULTS)
    for c in cands:
        p = shutil.which(c) if '/' not in c else c
        if p and Path(p).is_file() and os.access(p, os.X_OK):
            return str(Path(p).resolve())
    return None


def select_exporter(settings=None, numpy=None, blender=None):
    """-> {'exporter': 'python'|'blender'|None, 'reason': str, 'numpy': version|None, 'parity': verdict}.
    numpy / blender: facts already probed for the build interpreter (version string or False / path or False);
    None = probe here (this interpreter, configured or standard Blender locations)."""
    settings = settings or {}
    want = settings.get('character_exporter') or os.environ.get('HERMES64_CHARACTER_EXPORTER') or 'auto'
    if want not in CHOICES:
        return {'exporter': None, 'reason': 'character_exporter must be python, blender or auto (got %r)' % want,
                'numpy': None, 'parity': None}
    npv = numpy_version() if numpy is None else (numpy or None)
    par = parity().get('verdict')

    def blender_path(settings):            # noqa: F811 - the probed fact wins over a fresh lookup
        if blender is None:
            return _blender_path(settings)
        return blender or None
    if want == 'python':
        if not npv:
            return {'exporter': None, 'reason': 'character_exporter=python needs numpy in python_path (nothing was installed)',
                    'numpy': None, 'parity': par}
        return {'exporter': 'python', 'reason': 'configured', 'numpy': npv, 'parity': par}
    if want == 'blender':
        bp = blender_path(settings)
        if not bp:
            return {'exporter': None, 'reason': 'character_exporter=blender but Blender was not found; configure blender_path',
                    'numpy': npv, 'parity': par}
        return {'exporter': 'blender', 'reason': 'configured', 'blender': bp, 'numpy': npv, 'parity': par}
    if npv and par == 'PASS':
        return {'exporter': 'python', 'reason': 'auto: numpy present and parity PASS', 'numpy': npv, 'parity': par}
    bp = blender_path(settings)
    if bp:
        why = 'numpy missing' if not npv else 'parity verdict %s' % par
        return {'exporter': 'blender', 'reason': 'auto: %s, Blender found' % why, 'blender': bp, 'numpy': npv, 'parity': par}
    if npv and par == 'STALE':
        # the python exporter was proven on earlier code and there is no Blender to fall back to: use it, say so
        return {'exporter': 'python', 'reason': 'auto: parity verdict STALE (code changed since the PASS run) and no Blender',
                'numpy': npv, 'parity': par}
    missing = 'numpy' if not npv else 'a PASS parity verdict'
    return {'exporter': None, 'reason': 'auto: no character exporter (python needs %s; Blender not found)' % missing,
            'numpy': npv, 'parity': par}


def blender_path(settings):
    return _blender_path(settings)


def doctor_line(settings=None, numpy=None, blender=None):
    s = select_exporter(settings, numpy=numpy, blender=blender)
    if s['exporter'] == 'python':
        p = parity()
        extra = ', max skinned error %.1e m over %s files' % (p['max_skinned_error_m'], p.get('files')) \
            if isinstance(p.get('max_skinned_error_m'), (int, float)) else ''
        warn = ' (WARNING: verdict stale, re-run the parity check)' if s['parity'] == 'STALE' else ''
        return 'characters: python exporter (numpy %s, parity %s%s) - Blender not required%s' % (
            s['numpy'], s['parity'], extra, warn)
    if s['exporter'] == 'blender':
        return 'characters: blender exporter (%s; %s)' % (s.get('blender'), s['reason'])
    return 'characters: UNAVAILABLE - ' + s['reason']
