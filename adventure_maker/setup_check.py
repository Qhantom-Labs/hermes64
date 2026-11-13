"""One-step setup checklist and explicit opt-in fetch; stdlib only.

Checklist/doctor never download. Mac behavior is unchanged; Linux separately probes a
tiny rendered capture through Runner, and non-Mac Blender rows probe --version. Only
explicit --fetch plus confirmation invokes pinned first-run fetching.
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
    from .doctor import godot_version
    try:
        path = locate('godot', settings.get('godot_path', '') or '')
    except Fault:
        return None, None
    return path, godot_version(path)


def _python(settings, probe=None):
    from .runner import locate
    from .safety import Fault
    try:
        exe = locate('python', settings.get('python_path', '') or '')
    except Fault:
        return None, None
    if probe is not None:
        return exe, probe(exe)
    from .runner import scratch_env
    try:
        with scratch_env() as env:
            out = subprocess.run([exe, '-I', '-B', '-c', 'import numpy; print(numpy.__version__)'],
                                 capture_output=True, text=True, encoding='utf-8', timeout=20, env=env, **_no_window())
        return exe, (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return exe, None


def _pillow(exe, probe=None):
    """Pillow version importable by ``exe`` (the same isolated probe as numpy), else None."""
    if not exe:
        return None
    if probe is not None:
        return probe(exe)
    from .runner import scratch_env
    try:
        with scratch_env() as env:
            out = subprocess.run([exe, '-I', '-B', '-c', 'import PIL; print(PIL.__version__)'],
                                 capture_output=True, text=True, encoding='utf-8', timeout=20, env=env, **_no_window())
        return (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _no_window():
    """Windows: a console program (python.exe) started by a Hermes without a console would flash a console window."""
    return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)} if os.name == 'nt' else {}


def runner_row(platform=None, env=None, iso=None):
    """(status, detail, command) for the child runner on Linux and Windows; None on macOS (sandbox-exec is built in)."""
    from . import platforms
    plat = platforms.host(platform)
    if plat not in ('linux', 'win32'):
        return None
    iso = iso or platforms.isolation(platform, env)
    if plat == 'linux' and iso['available'] and not (
            iso['mode'] == 'bwrap' and iso.get('runner_probe_ok', False)):
        return ('missing', '%s: %s No sandboxed Runner.run readiness child passed; READY is withheld.' %
                (iso['mode'], iso['note']), 'run python3 -m adventure_maker.doctor --linux-checklist; fix the runner failure')
    if iso['available']:
        return 'ok', '%s: %s' % (iso['mode'], iso['note']), None
    if plat == 'win32':
        command = '$env:%s = "%s" in PowerShell (or a user environment variable), then restart Hermes' % (
            platforms.WINDOWS_RUNNER_ENV, platforms.WINDOWS_RUNNER_VALUE)
    else:
        command = ('install bubblewrap (Debian/Ubuntu: sudo apt install bubblewrap) or fix what the note names, '
                   'then restart Hermes; or, knowingly, %s=%s' % (platforms.LINUX_RUNNER_ENV, platforms.LINUX_RUNNER_VALUE))
    return 'missing', '%s: %s' % (iso['mode'], iso['note']), command


def numpy_command(exe, platform=None, home=None):
    """An isolated private venv; PowerShell 5.1 requires & and cannot use &&. Human runs it, never setup."""
    from . import platforms
    windows = platforms.is_windows(platform)
    venv = platforms.pure(platform)(home or Path.home()) / '.hermes64-python'
    py = venv / ('Scripts/python.exe' if windows else 'bin/python')
    if windows:
        create = platforms.command_line([str(exe), '-m', 'venv', str(venv)], 'win32')
        install = platforms.command_line([str(py), '-m', 'pip', 'install', 'numpy', 'pillow'], 'win32')
        return '%s; if ($LASTEXITCODE -eq 0) { %s }   (then set python_path to %s)' % (create, install, py)
    return '"%s" -m venv "%s" && "%s" -m pip install numpy pillow   (then set python_path to %s)' % (exe, venv, py, py)


def games_folder(settings, games_root=None):
    """(status, detail, command) for where `/hermes64 new` puts games: projects_root when set, else the profile's
    default games folder (created by the first `new`)."""
    configured = str(settings.get('projects_root') or '')
    if configured:
        path = Path(configured)
        if games_root is not None and path == Path(str(games_root)):
            return 'ok', '%s (default games folder)' % path, None
        if path.is_absolute() and path.is_dir():
            return 'ok', '%s (projects_root)' % path, None
        return ('missing', 'projects_root %s is not an existing absolute folder' % configured[:200],
                'fix projects_root in the hermes64 plugin settings, or clear it to use the default games folder')
    if games_root is None:
        return ('missing', 'no host games storage (Hermes 0.18.2 needs projects_root)',
                'set projects_root in plugins.entries.hermes64.settings to an existing absolute games folder')
    note = 'default games folder' if Path(str(games_root)).is_dir() else 'default games folder, made by your first /hermes64 new'
    return 'ok', '%s (%s)' % (games_root, note), None


def check(settings, probe_numpy=None, blender_present=None, templates=None, stub_status=None, ffmpeg=None,
          probe_pillow=None, games_root=None):
    """Rows of {item, status: ok|missing|optional, detail, needed_for, command}. Arguments after ``settings``
    exist so tests can simulate a machine without the programs. A simulated numpy probe without a Pillow probe
    leaves Pillow unprobed (reported as not importable) rather than starting a real interpreter."""
    from . import builders, doctor, stubs, audio_formats, platforms
    from .export import TEMPLATES
    from .safety import Fault
    rows = []

    def add(item, status, detail, needed_for, command=None):
        rows.append({'item': item, 'status': status, 'detail': detail, 'needed_for': needed_for, 'command': command})

    add('Python', 'ok' if sys.version_info >= (3, 9) else 'missing', sys.version.split()[0], 'everything',
        None if sys.version_info >= (3, 9) else _open('https://www.python.org/downloads/'))
    runner = runner_row()
    if runner is not None:          # Linux and Windows only: macOS rows are unchanged
        add('Child runner', runner[0], runner[1], 'making and rebuilding games', runner[2])
    gpath, gver = _godot(settings)
    if not gpath:
        add('Godot 4.6.2', 'missing', 'not found', 'playing, replaying, screenshots and exporting games', '/hermes64 setup --fetch')
    elif gver and gver != doctor.GODOT_VERSION:
        # REUSE: name what was found and the one-line choice; the pin itself is unchanged.
        add('Godot 4.6.2', 'missing', doctor.other_godot(gver, gpath), 'playing and exporting games',
            '/hermes64 setup --fetch --yes')
    else:
        add('Godot 4.6.2', 'ok', gpath + ('' if gver else ' (version not read on this system; exports check it)'),
            'playing and exporting games')

    if platforms.host() == 'linux':
        from .linux_display import status as display_status
        display = display_status(settings)
        add('capture display', 'ok' if display['ok'] else 'optional',
            display['detail'] if display['ok'] else 'missing, install xvfb (sudo apt install xvfb); reason: ' + display['detail'],
            'rendered style/N64 gates (logic builds and bots still run)')
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
    pil = _pillow(exe, probe_pillow if probe_pillow is not None or probe_numpy is None else (lambda _exe: None))
    present = builders.blender_available(settings) if blender_present is None else blender_present
    try:
        builder_line = builders.explain(settings, blender_present=present, numpy_present=bool(npv))
        chosen = builders.select(dict(settings, builder=builders.effective(settings)), blender_present=present)
    except Fault as exc:      # an unknown builder value: one row with the fix, never a crashed checklist
        builder_line, chosen = str(exc), None
    if npv:
        add('numpy in python_path', 'ok', '%s (%s)' % (npv, exe), 'room models without Blender, new character bodies, reference packs')
    else:
        status = 'missing' if chosen == 'python' else 'optional'
        add('numpy in python_path', status, 'not importable by %s' % (exe or 'any python'),
            'room models without Blender, new character bodies, reference packs',
            numpy_command(exe) if exe else _open('https://www.python.org/downloads/'))
    if pil:
        add('Pillow in python_path', 'ok', '%s (%s)' % (pil, exe), 'JPEG and other non-basic PNG reference images')
    else:
        add('Pillow in python_path', 'optional', 'not importable by %s' % (exe or 'any python'),
            'JPEG and other non-basic PNG reference images (games do not need it)',
            ('the numpy command above (it installs Pillow too)' if not npv else numpy_command(exe)) if exe else None)
    if chosen is None:
        add('Room model builder', 'missing', builder_line, 'room models',
            'set builder to auto (or clear it) in the hermes64 plugin settings')
    elif chosen == 'blender' and not present:
        add('Room model builder', 'missing', builder_line, 'room models', 'set builder to auto in the hermes64 plugin settings')
    else:
        ok = chosen == 'blender' or bool(npv)
        add('Room model builder', 'ok' if ok else 'missing', builder_line, 'room models (bundled kits work without)',
            None if ok else 'the numpy command above')
    add('Blender', 'ok' if present else 'optional', 'found' if present else
        'not found (optional: with builder=auto, room models use the Python builder)',
        'builder=blender and character review renders', None)
    from . import platforms
    if present and platforms.host() in ('linux', 'win32'):
        from . import blender_version
        from .runner import locate
        try:
            version = blender_version.probe(locate('blender', settings.get('blender_path') or ''))
        except Fault:
            version = None
        rows[-1].update(status='ok' if version == blender_version.TESTED else 'optional',
                        detail=blender_version.note(version))

    fexe, why = ffmpeg if ffmpeg is not None else audio_formats.find_ffmpeg()
    add('Audio', 'ok', 'WAV read in pure Python; OGG Vorbis and MP3 play natively in Godot', 'game sound', None)
    add('ffmpeg', 'ok' if fexe else 'optional', fexe or 'not used: only needed to convert FLAC/M4A/Opus/AIFF', 'other audio formats',
        None)
    status, detail, command = games_folder(settings, games_root)
    add('Games folder', status, detail, 'saving the games /hermes64 new makes', command)
    return rows


# NATIVE: no space padding (a chat shows proportional text, so padded columns never line up).
SYMBOL = {'ok': '[ok]', 'missing': '[MISSING]', 'optional': '[optional]'}


def summary(rows):
    by = {r['item']: r['status'] for r in rows}
    make = by['Python'] == 'ok' and by.get('Games folder', 'ok') == 'ok' and by.get('Child runner', 'ok') == 'ok'
    play = make and by['Godot 4.6.2'] == 'ok'
    return ('Ready: make games %s; play %s; room models %s; export %s.' % (
        'yes' if make else 'no', 'yes' if play else 'no',
        'yes' if by['Room model builder'] == 'ok' else 'no (bundled kits still work)',
        'yes' if play and by['Game players (export)'] == 'ok' else 'no'))


def render(rows, fetched=False):
    lines = ['Hermes64 setup check after explicit fetch.' if fetched else
             'Hermes64 setup check. Nothing was installed or downloaded.']
    for r in rows:
        lines.append('- %s %s: %s' % (SYMBOL[r['status']], r['item'], r['detail']))
        if r['status'] != 'ok' and r.get('command'):
            lines.append('  needed for %s. Next step: %s' % (r['needed_for'], r['command']))
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


def run(settings, fetch=False, yes=False, include_templates=False, interactive=False, emit=None, confirm=None,
        games_root=None):
    """Shared CLI/slash path (the model tool never passes yes). Noninteractive surfaces get the plan plus the command
    the human must type; never stdin. ``games_root`` is the profile's default games folder for the checklist row."""
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
        rows = check(settings, games_root=games_root)
        report(render(rows, fetched=fetch))
        by = {r['item']: r['status'] for r in rows}
        return {'ok': by['Python'] == 'ok' and by['Godot 4.6.2'] == 'ok' and by['Games folder'] == 'ok' and
                by.get('Child runner', 'ok') == 'ok',
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
    from .plugin_settings import default_games_root, plugin_settings
    from .tools import SETTINGS, running_line
    try:  # chat apps and autocorrect turn -- into an em dash and - into an en dash
        flags = shlex.split((raw or '').replace('\u2014\u2014', '--').replace('\u2014', '--').replace('\u2013', '-'))
    except ValueError as exc:
        return 'Setup failed: ' + str(exc)
    if flags == ['--fetch-plan']:
        return fetch_plan()
    if any(f not in ('--fetch', '--yes', '--templates') for f in flags):
        return 'Unknown setup option. Use /hermes64 setup [--fetch [--yes] [--templates]] or --fetch-plan. Nothing downloaded.'
    message = run(plugin_settings(ctx, SETTINGS), fetch='--fetch' in flags,
                  yes='--yes' in flags, include_templates='--templates' in flags,
                  games_root=default_games_root(ctx))['message']
    return message + '\n' + running_line()   # BFIX: names the exact copy that answered (MAC TEST 1 ran an older one)
