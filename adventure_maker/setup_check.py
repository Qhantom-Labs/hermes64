"""One-step setup checklist and explicit opt-in fetch; stdlib only.

Checklist/doctor never download or launch Godot. Only an explicit --fetch plus confirmation invokes
pinned first-run fetching; the selected Python is probed for numpy as before.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FETCH_MANIFEST = ROOT / 'tools' / 'fetch-manifest.json'
GODOT_PAGE = 'https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable'


def _platform():
    return 'darwin' if sys.platform == 'darwin' else 'windows' if os.name == 'nt' else 'linux'


def _open(url):
    return {'darwin': 'open ' + url, 'windows': 'start ' + url}.get(_platform(), 'xdg-open ' + url)


def _godot(settings):
    from .runner import locate
    from .safety import Fault
    try:
        path = locate('godot', settings.get('godot_path', '') or '')
    except Fault:
        return None, None
    version = None
    plist = Path(path).parents[1] / 'Info.plist' if sys.platform == 'darwin' else None
    if plist and plist.is_file():
        import plistlib
        try:
            version = plistlib.loads(plist.read_bytes()).get('CFBundleShortVersionString')
        except Exception:
            version = None
    return path, version


def _python(settings, probe=None):
    from .runner import locate
    from .safety import Fault
    try:
        exe = locate('python', settings.get('python_path', '') or '')
    except Fault:
        return None, None
    if probe is not None:
        return exe, probe(exe)
    try:
        out = subprocess.run([exe, '-I', '-B', '-c', 'import numpy; print(numpy.__version__)'],
                             capture_output=True, text=True, encoding='utf-8', timeout=20)
        return exe, (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return exe, None


def numpy_command(exe):
    """Hermes64 runs python_path isolated (-I), so a `pip install --user` is invisible to it. A private venv is
    the one route that works for every interpreter; the user runs it, then sets python_path."""
    venv = Path.home() / '.hermes64-python'
    py = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return '"%s" -m venv "%s" && "%s" -m pip install numpy pillow   (then set python_path to %s)' % (exe, venv, py, py)


def check(settings, probe_numpy=None, blender_present=None, templates=None, stub_status=None, ffmpeg=None):
    """Rows of {item, status: ok|missing|optional, detail, needed_for, command}. Arguments after ``settings``
    exist so tests can simulate a machine without the programs."""
    from . import builders, doctor, stubs, audio_formats
    from .export import TEMPLATES
    rows = []

    def add(item, status, detail, needed_for, command=None):
        rows.append({'item': item, 'status': status, 'detail': detail, 'needed_for': needed_for, 'command': command})

    add('Python', 'ok' if sys.version_info >= (3, 9) else 'missing', sys.version.split()[0], 'everything',
        None if sys.version_info >= (3, 9) else _open('https://www.python.org/downloads/'))
    gpath, gver = _godot(settings)
    if not gpath:
        add('Godot 4.6.2', 'missing', 'not found', 'playing, replaying, screenshots and exporting games', '/hermes64 setup --fetch')
    elif gver and gver != doctor.GODOT_VERSION:
        add('Godot 4.6.2', 'missing', 'found version %s at %s; Hermes64 needs exactly 4.6.2' % (gver, gpath),
            'playing and exporting games', '/hermes64 setup --fetch')
    else:
        add('Godot 4.6.2', 'ok', gpath + ('' if gver else ' (version checked when a game runs)'), 'playing and exporting games')

    official = templates if templates is not None else doctor.export_templates()
    st = stub_status if stub_status is not None else stubs.status()
    have = {t: (t in official.get('targets', [])) or st['targets'].get(t, False) for t in TEMPLATES}
    sources = []
    if official.get('targets'):
        sources.append('official templates (%s)' % ', '.join(official['targets']))
    if st.get('cache'):
        sources.append('fetched official templates in %s' % st['cache'])
    missing = sorted(t for t, ok in have.items() if not ok)
    if not missing:
        add('Game players (export)', 'ok', '; '.join(sources), 'exporting web, macOS and Windows builds')
    else:
        cmd = '/hermes64 setup --fetch --templates'
        add('Game players (export)', 'optional', 'missing for: %s%s' % (', '.join(missing),
            ('; have ' + '; '.join(sources)) if sources else ''),
            'exporting (making and playing games do not need them)', cmd)

    exe, npv = _python(settings, probe_numpy)
    present = builders.blender_available(settings) if blender_present is None else blender_present
    builder_line = builders.explain(settings, blender_present=present, numpy_present=bool(npv))
    chosen = builders.select(dict(settings, builder=settings.get('builder') or builders.DEFAULT_BUILDER), blender_present=present)
    if npv:
        add('numpy in python_path', 'ok', '%s (%s)' % (npv, exe), 'room models without Blender, new character bodies, reference packs')
    else:
        status = 'missing' if chosen == 'python' else 'optional'
        add('numpy in python_path', status, 'not importable by %s' % (exe or 'any python'),
            'room models without Blender, new character bodies, reference packs',
            numpy_command(exe) if exe else _open('https://www.python.org/downloads/'))
    if chosen == 'blender' and not present:
        add('Room model builder', 'missing', builder_line, 'room models', 'set builder to auto in the hermes64 plugin settings')
    else:
        ok = chosen == 'blender' or bool(npv)
        add('Room model builder', 'ok' if ok else 'missing', builder_line, 'room models (bundled kits work without)',
            None if ok else 'the numpy command above')
    add('Blender', 'ok' if present else 'optional', 'found' if present else 'not found (not required)',
        'builder=blender and character review renders', None)

    fexe, why = ffmpeg if ffmpeg is not None else audio_formats.find_ffmpeg()
    add('Audio', 'ok', 'WAV read in pure Python; OGG Vorbis and MP3 play natively in Godot', 'game sound', None)
    add('ffmpeg', 'ok' if fexe else 'optional', fexe or 'not used: only needed to convert FLAC/M4A/Opus/AIFF', 'other audio formats',
        None)
    return rows


SYMBOL = {'ok': '[ok]      ', 'missing': '[MISSING] ', 'optional': '[optional]'}


def summary(rows):
    by = {r['item']: r['status'] for r in rows}
    make = by['Python'] == 'ok'
    play = make and by['Godot 4.6.2'] == 'ok'
    return ('Ready: make games %s; play %s; room models %s; export %s.' % (
        'yes' if make else 'no', 'yes' if play else 'no',
        'yes' if by['Room model builder'] == 'ok' else 'no (bundled kits still work)',
        'yes' if play and by['Game players (export)'] == 'ok' else 'no'))


def render(rows, fetched=False):
    lines = ['Hermes64 setup check after explicit fetch.' if fetched else
             'Hermes64 setup check. Nothing was installed or downloaded.']
    for r in rows:
        lines.append('%s %s: %s' % (SYMBOL[r['status']], r['item'], r['detail']))
        if r['status'] != 'ok' and r.get('command'):
            lines.append('            needed for %s. Run: %s' % (r['needed_for'], r['command']))
    lines.append(summary(rows))
    return '\n'.join(lines)


def fetch_plan():
    """All artifact pins, printed without connecting; only Godot and optional stubs are fetched by --fetch."""
    data = json.loads(FETCH_MANIFEST.read_text(encoding='utf-8'))
    lines = ['Hermes64 fetch plan (NOT run; nothing is downloaded by this command).']
    for name, row in sorted(data['artifacts'].items()):
        algorithm = 'sha512' if row.get('sha512') else 'sha256'
        pin = row.get(algorithm, 'EMPTY')
        ready = row.get('url') and not str(row['url']).startswith('TODO') and pin != 'EMPTY' and not pin.startswith('TODO')
        lines.append('%s %s: %s' % ('[ready]  ' if ready else '[blocked]', name, row.get('why', '')))
        lines.append('    url=%s %s=%s bytes=%s' % (row.get('url') or 'EMPTY', algorithm, pin, row.get('bytes', 'unknown')))
    return '\n'.join(lines)


def human_command(include_templates=False):
    return '/hermes64 setup --fetch --yes' + (' --templates' if include_templates else '')


def run(settings, fetch=False, yes=False, include_templates=False, interactive=False, emit=None, confirm=None):
    """Shared CLI/slash path (the model tool never passes yes). Noninteractive surfaces get the plan plus the command
    the human must type; never stdin."""
    from . import godot_fetch
    lines = []

    def report(line):
        lines.append(line)
        if emit is not None:
            emit(line)

    try:
        if (yes or include_templates) and not fetch:
            raise godot_fetch.FetchError('--yes and --templates require --fetch. Nothing downloaded.')
        if fetch:
            if not yes and not interactive:
                report(godot_fetch.plan(include_templates=include_templates))
                report('Nothing was downloaded. To download these files, the user types this command themselves: %s '
                       '(or runs python3 tools/hermes64_setup.py --fetch in a terminal).' % human_command(include_templates))
                return {'ok': False, 'status': 'confirmation_required', 'message': '\n'.join(lines), 'rows': []}
            exe = godot_fetch.fetch(yes=yes, include_templates=include_templates, emit=report, confirm=confirm or input)
            if exe is None:
                return {'ok': False, 'status': 'cancelled', 'message': '\n'.join(lines), 'rows': []}
            if settings.get('godot_path') and Path(settings['godot_path']).absolute() != exe.absolute():
                report('Your explicit godot_path still takes precedence. Clear it or change it to %s to use the fetched Godot.' % exe)
        rows = check(settings)
        report(render(rows, fetched=fetch))
        by = {r['item']: r['status'] for r in rows}
        return {'ok': by['Python'] == 'ok' and by['Godot 4.6.2'] == 'ok',
                'status': 'checked_after_fetch' if fetch else 'checked', 'message': '\n'.join(lines), 'rows': rows}
    except (godot_fetch.FetchError, OSError, ValueError) as exc:
        report('Setup failed: ' + str(exc))
        return {'ok': False, 'status': 'failed', 'message': '\n'.join(lines), 'rows': []}


SETUP_SCHEMA = {
    'name': 'hermes64_setup',
    'description': 'Setup checklist. fetch=true lists the official Godot downloads (URL, SHA-512, cap, cache folder) and the command the user must type; this tool never downloads. templates=true adds export templates.',
    'parameters': {'type': 'object', 'properties': {
        'fetch': {'type': 'boolean'}, 'templates': {'type': 'boolean'}},
        'required': [], 'additionalProperties': False}}


def tool_handler(ctx, args):
    """Model-facing: report only. Consent to download is never a tool argument; the human types the command."""
    from .plugin_settings import plugin_settings
    from .tools import SETTINGS
    from .schemas import validate
    from .safety import Fault
    try:
        validate(args, SETUP_SCHEMA['parameters'])
        return json.dumps(run(plugin_settings(ctx, SETTINGS), fetch=args.get('fetch', False), yes=False,
                              include_templates=args.get('templates', False), interactive=False))
    except (Fault, OSError, ValueError, TypeError) as exc:
        return json.dumps({'ok': False, 'status': 'failed', 'message': str(exc)})


def command(ctx, raw=''):
    """/hermes64 setup [--fetch [--yes] [--templates]], typed by the user; plain setup has no engine/network action."""
    import shlex
    from .plugin_settings import plugin_settings
    from .tools import SETTINGS
    try:
        flags = shlex.split(raw)
    except ValueError as exc:
        return 'Setup failed: ' + str(exc)
    if flags == ['--fetch-plan']:
        return fetch_plan()
    if any(f not in ('--fetch', '--yes', '--templates') for f in flags):
        return 'Unknown setup option. Use /hermes64 setup [--fetch [--yes] [--templates]] or --fetch-plan. Nothing downloaded.'
    return run(plugin_settings(ctx, SETTINGS), fetch='--fetch' in flags,
               yes='--yes' in flags, include_templates='--templates' in flags)['message']
