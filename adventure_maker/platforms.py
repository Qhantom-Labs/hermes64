"""Host-platform facts in one place: where Godot, Blender, Python and the export templates live on macOS, Windows
and Linux, the user override env vars, and the Windows readiness checklist. Standard library only, read-only.

Every function takes the platform, environment and home folder as arguments (defaulting to this computer), so the
Windows and Linux branches are exercised on a Mac with `platform='win32'` / `'linux'`, a fake environment and pure
paths (tests/test_windows_paths.py, tests/test_linux_platform.py). Nothing here installs anything or touches the
network, and nothing launches a program except isolation() on a real Linux host, which asks linux_sandbox for its
bubblewrap probe (one short sandboxed run per process).

Override env vars (checked before any default location, on every platform):
  HERMES64_GODOT      full path of the Godot 4.6.2 executable
  HERMES64_BLENDER    full path of the Blender executable
  HERMES64_PYTHON     full path of the Python 3.9+ interpreter for child builds
  HERMES64_TEMPLATES  folder holding the Godot 4.6.2.stable export templates (version.txt + template files)
A plugin setting (godot_path, blender_path, python_path) still wins over the env var.
Runner opt-ins: HERMES64_WINDOWS_RUNNER=job (Windows Job Object), HERMES64_LINUX_RUNNER=unconfined (Linux without a
working bubblewrap). Neither gives OS-enforced network or write confinement.
"""
import ntpath
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys

GODOT_VERSION = '4.6.2'
TEMPLATE_VERSION = '4.6.2.stable'
OVERRIDE_ENV = {'godot': 'HERMES64_GODOT', 'blender': 'HERMES64_BLENDER', 'python': 'HERMES64_PYTHON'}
TEMPLATES_ENV = 'HERMES64_TEMPLATES'
# Windows child isolation is opt-in (see runner.py and docs/WINDOWS.md): the macOS sandbox has no one-line
# Windows equivalent, so children run in a Job Object (kill-on-close, process and memory caps, private profile
# folders) but without OS-enforced network or write confinement. The owner turns it on knowingly.
WINDOWS_RUNNER_ENV = 'HERMES64_WINDOWS_RUNNER'
WINDOWS_RUNNER_VALUE = 'job'
# Linux: bubblewrap by default (linux_sandbox.py); this opt-in is used only when bwrap is missing or fails its probe.
LINUX_RUNNER_ENV = 'HERMES64_LINUX_RUNNER'
LINUX_RUNNER_VALUE = 'unconfined'
SANDBOXED_PACKAGE_NOTE = ('snap and flatpak programs start through their own sandbox launcher, which is not expected to '
                          'work inside the Hermes64 Linux sandbox, and they would not see your project folder (not '
                          'tested). Use the official Linux build instead and set HERMES64_GODOT / HERMES64_BLENDER or '
                          'godot_path / blender_path to it (docs/LINUX.md).')


def host(platform=None):
    """'darwin', 'win32' or 'linux' (anything else is reported as itself)."""
    value = platform or sys.platform
    if value.startswith('win') or value == 'cygwin':
        return 'win32'
    if value.startswith('linux'):
        return 'linux'
    return value


def is_windows(platform=None):
    return host(platform) == 'win32'


def pure(platform=None):
    """The pure path class that builds paths for that platform (PureWindowsPath on Windows)."""
    return PureWindowsPath if is_windows(platform) else PurePosixPath


def looks_like_path(value, platform=None):
    """True for a value with a folder part (C:\\x\\godot.exe, ./godot, /usr/bin/godot); False for a bare name."""
    if is_windows(platform):
        return '\\' in value or '/' in value or ntpath.splitdrive(value)[0] != ''
    return '/' in value


def exe_name(name, platform=None):
    """'godot' -> 'godot.exe' on Windows; unchanged elsewhere or when it already has the suffix."""
    if is_windows(platform) and not name.lower().endswith('.exe'):
        return name + '.exe'
    return name


def python_command(platform=None):
    """How a person starts Python 3 in a terminal on that platform (docs and messages)."""
    return 'py' if is_windows(platform) else 'python3'


def command_line(argv, platform=None):
    """One line a person can paste into the usual terminal: POSIX sh quoting, or PowerShell on Windows
    (`& 'C:\\Program Files\\Godot\\godot.exe' --path 'C:\\games\\fox'`)."""
    if is_windows(platform):
        def q(part):
            if part and all(c.isalnum() or c in '-_=.:\\/' for c in part):
                return part
            return "'" + part.replace("'", "''") + "'"
        return '& ' + ' '.join(q(p) for p in argv)
    import shlex
    return ' '.join(shlex.quote(p) for p in argv)


def console_text(text, stream=None):
    """Keep human output printable on legacy Windows consoles; UTF-8 surfaces retain all characters."""
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, 'encoding', None) or 'utf-8'
    try:
        return str(text).encode(encoding, 'backslashreplace').decode(encoding)
    except LookupError:
        return str(text).encode('ascii', 'backslashreplace').decode('ascii')


def split_args(raw, platform=None):
    """shlex.split that keeps Windows backslashes literal (C:\\games stays C:\\games)."""
    import shlex
    text = raw or ''
    if is_windows(platform):
        text = text.replace('\\', '\\\\')
    return shlex.split(text)


def _env(env):
    return os.environ if env is None else env


def _home(home, platform):
    return pure(platform)(home if home is not None else Path.home())


def override(tool, env=None):
    value = (_env(env).get(OVERRIDE_ENV[tool]) or '').strip().strip('"')
    return value or None


def _win_dirs(env, home):
    """The Windows folders Godot/Blender installers use, built with ntpath so they are correct on any host."""
    W = PureWindowsPath
    e = _env(env)
    local = W(e.get('LOCALAPPDATA') or (home / 'AppData' / 'Local'))
    roaming = W(e.get('APPDATA') or (home / 'AppData' / 'Roaming'))
    progs = [W(e[k]) for k in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)') if e.get(k)]
    if not progs:
        progs = [W('C:/Program Files')]
    scoop = W(e.get('SCOOP') or (home / 'scoop'))
    return local, roaming, progs, scoop


def godot_candidates(platform=None, env=None, home=None):
    """Ordered places to look for Godot 4.6.2 (after a configured godot_path). Strings; bare names mean PATH."""
    plat = host(platform)
    e = _env(env)
    found = [override('godot', e)] if override('godot', e) else []
    # Only inspect the real user's verified cache for real-host discovery.
    # Keep explicit godot_path and HERMES64_GODOT ahead of automatic candidates;
    # simulated Windows path inventories must not read the host's cache.
    if platform is None and env is None and home is None:
        from .godot_fetch import cached_godot
        cached = cached_godot()
        found += [str(cached)] if cached else []
    if plat == 'win32':
        h = _home(home, plat)
        local, _roaming, progs, scoop = _win_dirs(e, h)
        names = ('Godot_v4.6.2-stable_win64.exe', 'Godot_v4.6.2-stable_win64_console.exe', 'Godot.exe', 'godot.exe')
        roots = [local / 'Programs' / 'Godot', local / 'Godot'] + [p / 'Godot' for p in progs] + [
            scoop / 'apps' / 'godot' / 'current', scoop / 'apps' / 'godot' / GODOT_VERSION,
            h / 'Godot', h / 'Downloads' / 'Godot_v4.6.2-stable_win64.exe', h / 'Downloads', h / 'Desktop']
        for root in roots:
            found += [str(root / n) for n in names]
        # winget installs unpack under Packages\GodotEngine.GodotEngine_<source id>\ and link a shim in Links\.
        winget = local / 'Microsoft' / 'WinGet'
        found += [str(winget / 'Links' / n) for n in ('godot.exe', 'Godot.exe')]
        found += [str(p) for p in _glob_windows(winget / 'Packages', 'GodotEngine.GodotEngine*', names, e)]
        found += [str(scoop / 'shims' / 'godot.exe')]
        found += ['Godot_v4.6.2-stable_win64.exe', 'godot.exe', 'godot4.exe', 'godot', 'godot4']
    elif plat == 'darwin':
        found += ['/Applications/Godot.app/Contents/MacOS/Godot',
                  str(_home(home, plat) / 'Applications/Godot.app/Contents/MacOS/Godot'), 'godot']
    else:
        h = _home(home, plat)
        official = ('Godot_v4.6.2-stable_linux.x86_64', 'Godot_v4.6.2-stable_linux.arm64')
        roots = ['/usr/local/bin', '/usr/bin', '/opt/godot', '/opt/Godot', '/opt', str(h / '.local/bin'), str(h / 'bin'),
                 str(h / 'Applications'), str(h / 'Applications/Godot'), str(h / 'Godot'), str(h / 'Downloads')]
        # The official 4.6.2 file names first: a distro `godot` may be another version (exports check the version).
        found += [r + '/' + n for r in roots for n in official]
        found += [str(h / 'Downloads' / n / n) for n in official]          # unzipped into a folder of the same name
        found += ['/usr/bin/godot', '/usr/local/bin/godot', str(h / '.local/bin/godot'), str(h / 'bin/godot'),
                  '/usr/local/bin/godot4', '/usr/bin/godot4', str(h / '.local/bin/godot4')]
        found += [str(p) for p in _glob_linux(PurePosixPath('/opt'), 'godot*', official + ('godot',))]
        # Found only so locate() can say why it skips them (sandboxed_package).
        found += ['/snap/bin/godot', '/snap/bin/godot-4', '/var/lib/flatpak/exports/bin/org.godotengine.Godot',
                  str(h / '.local/share/flatpak/exports/bin/org.godotengine.Godot')]
        found += list(official) + ['godot4', 'godot']
    return _unique(found)


def blender_candidates(platform=None, env=None, home=None):
    plat = host(platform)
    e = _env(env)
    found = [override('blender', e)] if override('blender', e) else []
    if plat == 'win32':
        h = _home(home, plat)
        local, _roaming, progs, scoop = _win_dirs(e, h)
        for p in progs:
            found += [str(x) for x in _glob_windows(p / 'Blender Foundation', 'Blender*', ('blender.exe',), e)]
        found += [str(scoop / 'apps' / 'blender' / 'current' / 'blender.exe')]
        # Steam installs Blender under steamapps\common\Blender; the portable zip unpacks to blender-<v>-windows-x64.
        found += [str(p / 'Steam' / 'steamapps' / 'common' / 'Blender' / 'blender.exe') for p in progs]
        for folder in (h / 'Downloads', h / 'Desktop', h):
            found += [str(x) for x in _glob_windows(folder, 'blender-*-windows-x64', ('blender.exe',), e)]
        found += ['blender.exe', 'blender']
    elif plat == 'darwin':
        found += ['/opt/homebrew/bin/blender', '/Applications/Blender.app/Contents/MacOS/Blender', 'blender']
    else:
        h = _home(home, plat)
        found += ['/usr/bin/blender', '/usr/local/bin/blender', '/opt/blender/blender']
        found += [str(p) for p in _glob_linux(PurePosixPath('/opt'), 'blender*', ('blender',))]
        found += [str(h / '.local/bin/blender'), str(h / 'bin/blender'), str(h / 'Applications/blender/blender')]
        for folder in (h / 'Applications', h, h / 'Downloads'):         # official tarball: blender-<v>-linux-x64/
            found += [str(p) for p in _glob_linux(folder, 'blender-*', ('blender',))]
        # Found only so locate() can say why it skips them (sandboxed_package).
        found += ['/snap/bin/blender', '/var/lib/flatpak/exports/bin/org.blender.Blender',
                  str(h / '.local/share/flatpak/exports/bin/org.blender.Blender'), 'blender']
    return _unique(found)


def sandboxed_package(path, resolved=None):
    """'snap' or 'flatpak' when a Linux program path (or what it resolves to) belongs to one, else None."""
    for value in (str(path or ''), str(resolved or '')):
        if value.startswith('/snap/') or value in ('/usr/bin/snap', '/usr/lib/snapd/snap-confine') or \
                value.startswith('/var/lib/snapd/'):
            return 'snap'
        if '/flatpak/exports/bin/' in value or value.startswith('/var/lib/flatpak/') or \
                '/.local/share/flatpak/' in value or value == '/usr/bin/flatpak':
            return 'flatpak'
    return None


def ffmpeg_candidates(platform=None, env=None):
    """Common install folders after configured/bundled/PATH lookup; never download ffmpeg."""
    if is_windows(platform):
        W = PureWindowsPath
        return [str(W(_env(env).get('ProgramFiles') or r'C:\Program Files') / 'ffmpeg' / 'bin' / 'ffmpeg.exe'),
                str(W(r'C:\ffmpeg') / 'bin' / 'ffmpeg.exe')]
    root = PurePosixPath('/')
    if host(platform) == 'linux':
        return [str(root / 'usr' / 'local' / 'bin' / 'ffmpeg'), str(root / 'usr' / 'bin' / 'ffmpeg')]
    return [str(root / 'opt' / 'homebrew' / 'bin' / 'ffmpeg'),
            str(root / 'usr' / 'local' / 'bin' / 'ffmpeg'), str(root / 'usr' / 'bin' / 'ffmpeg')]


def environment_pythons(platform=None):
    """Python executables of the virtual environments whose packages this process imports without running their python.

    The Hermes launcher (`hermes`) starts its managed base interpreter (sys.executable) with -I and puts its own
    environment's site-packages on sys.path, so Hermes imports numpy and Pillow while a child `sys.executable -I` cannot.
    That environment's python (its pyvenv.cfg sits next to it) starts with those packages. Environments that hold numpy
    come first. Empty when this process already runs a virtual environment's python (sys.executable then carries the
    packages itself) and for simulated platforms. Reads only the folders already on sys.path."""
    if host(platform) != host() or sys.prefix != getattr(sys, 'base_prefix', sys.prefix):
        return []
    windows = host() == 'win32'
    found = []
    for entry in sys.path:
        site = Path(entry) if entry else None
        if site is None or site.name.lower() != 'site-packages':
            continue
        parents = site.parents      # <env>\Lib\site-packages on Windows, <env>/lib/pythonX.Y/site-packages elsewhere
        if len(parents) < (2 if windows else 3):
            continue
        root = parents[1] if windows else parents[2]
        try:
            if not (root / 'pyvenv.cfg').is_file():
                continue
            names = ('Scripts/python.exe',) if windows else ('bin/python3', 'bin/python')
            exe = next((root / name for name in names if (root / name).is_file()), None)
            if exe is not None:      # absolute, never resolved: the venv's own name is what makes it use pyvenv.cfg
                found.append((not (site / 'numpy').is_dir(), str(exe.absolute())))
        except OSError:
            continue
    return _unique(exe for _without_numpy, exe in sorted(found, key=lambda row: row[0]))


def python_candidates(platform=None, env=None, executable=None):
    """Hermes's own interpreter first (it carries numpy/Pillow), then the platform's usual names. Under the Hermes
    launcher that interpreter is its environment's python (environment_pythons), not the bare sys.executable."""
    plat = host(platform)
    e = _env(env)
    found = [override('python', e)] if override('python', e) else []
    if executable is None:
        found += environment_pythons(platform)
    exe = sys.executable if executable is None else executable
    if exe:
        found.append(exe)
    found += ['python.exe', 'python3.exe', 'py.exe'] if plat == 'win32' else ['python3']
    return _unique(found)


def candidates(tool, platform=None, env=None, home=None):
    if tool == 'godot':
        return godot_candidates(platform, env, home)
    if tool == 'blender':
        return blender_candidates(platform, env, home)
    return python_candidates(platform, env)


def templates_dir(platform=None, env=None, home=None):
    """Where the Godot editor installs 4.6.2.stable export templates on that platform (or HERMES64_TEMPLATES)."""
    plat = host(platform)
    e = _env(env)
    if (e.get(TEMPLATES_ENV) or '').strip():
        return pure(plat)(e[TEMPLATES_ENV].strip().strip('"'))
    h = _home(home, plat)
    if plat == 'win32':
        roaming = PureWindowsPath(e.get('APPDATA') or (h / 'AppData' / 'Roaming'))
        return roaming / 'Godot' / 'export_templates' / TEMPLATE_VERSION
    if plat == 'darwin':
        return h / 'Library' / 'Application Support' / 'Godot' / 'export_templates' / TEMPLATE_VERSION
    data = PurePosixPath(e.get('XDG_DATA_HOME') or (h / '.local' / 'share'))
    return data / 'godot' / 'export_templates' / TEMPLATE_VERSION


def project_local_dir(local, platform=None):
    """Child-process profile folders inside a project's .maker/local (keys = env var names)."""
    if is_windows(platform):
        return {'USERPROFILE': local / 'home', 'HOME': local / 'home', 'APPDATA': local / 'config',
                'LOCALAPPDATA': local / 'cache', 'TEMP': local / 'tmp', 'TMP': local / 'tmp'}
    return {'HOME': local / 'home', 'TMPDIR': local / 'tmp', 'XDG_CONFIG_HOME': local / 'config',
            'XDG_CACHE_HOME': local / 'cache', 'XDG_DATA_HOME': local / 'data'}


def windows_runner_enabled(env=None):
    return (_env(env).get(WINDOWS_RUNNER_ENV) or '').strip().lower() == WINDOWS_RUNNER_VALUE


def isolation(platform=None, env=None):
    """{'mode', 'available', 'network_blocked', 'writes_confined', 'note'} for child processes on that platform."""
    plat = host(platform)
    if plat == 'darwin':
        ok = Path('/usr/bin/sandbox-exec').is_file() if host() == 'darwin' else True
        return {'mode': 'sandbox-exec', 'available': ok, 'network_blocked': True, 'writes_confined': True,
                'note': 'macOS sandbox: no network, writes confined to the project folder.'}
    if plat == 'win32':
        on = windows_runner_enabled(env)
        return {'mode': 'job-object' if on else 'off', 'available': on, 'network_blocked': False,
                'writes_confined': False,
                'note': ('Windows Job Object: the child and everything it starts are stopped together, with process '
                         'and memory caps and private profile folders inside the project. Windows does not block '
                         'its network or confine its writes the way the macOS sandbox does.') if on else
                        ('Making and rebuilding games is off on Windows until you opt in: run '
                         '$env:%s = "%s" in PowerShell (or set it as a user environment variable) and restart '
                         'Hermes. Children then run in a Windows Job Object without OS network/write '
                         'confinement (docs/WINDOWS.md).' % (WINDOWS_RUNNER_ENV, WINDOWS_RUNNER_VALUE))}
    if plat == 'linux':
        if host() == 'linux':
            from . import linux_sandbox
            return linux_sandbox.status(env)
        return {'mode': 'off', 'available': False, 'network_blocked': False, 'writes_confined': False,
                'note': ('Linux runner not checked: this computer is not Linux (simulation). On Linux, Hermes64 runs '
                         'children only inside a working bubblewrap (bwrap) sandbox, or unconfined after the %s=%s '
                         'opt-in (docs/LINUX.md).' % (LINUX_RUNNER_ENV, LINUX_RUNNER_VALUE))}
    return {'mode': 'off', 'available': False, 'network_blocked': False, 'writes_confined': False,
            'note': 'No supported child-process sandbox on this system; making games is off.'}


def windows_checklist(report=None, env=None, home=None):
    """Plain lines for a Windows owner: each item OK/MISSING/OFF with the exact fix. report = doctor.probe()."""
    report = report or {}
    e = _env(env)
    lines = []
    py = report.get('python') or {}
    lines.append('%s  Python 3.9+ (%s)' % ('OK     ' if py.get('supported') else 'MISSING', py.get('version') or '?'))
    for key, label in (('numpy', 'numpy (static kit and character builds)'), ('pillow', 'Pillow (JPEG references)')):
        ok = (py.get(key) or {}).get('available')
        lines.append('%s  %s%s' % ('OK     ' if ok else 'MISSING', label, '' if ok else ': py -m pip install ' + key))
    godot = (report.get('programs') or {}).get('godot') or {}
    lines.append('%s  Godot 4.6.2 standard build%s' % (
        'OK     ' if godot.get('available') else 'MISSING',
        ' at ' + godot['path'] if godot.get('path') else
        ': unzip Godot_v4.6.2-stable_win64.exe.zip (e.g. to %s) or set $env:HERMES64_GODOT to the .exe' %
        (PureWindowsPath(e.get('LOCALAPPDATA') or 'C:/Users/you/AppData/Local') / 'Programs' / 'Godot')))
    tpl = report.get('export_templates') or {}
    lines.append('%s  Export templates %s in %s (installed targets: %s)' % (
        'OK     ' if 'windows' in (tpl.get('targets') or []) else 'MISSING', TEMPLATE_VERSION,
        tpl.get('folder') or templates_dir('win32', e, home), ', '.join(tpl.get('targets') or []) or 'none'))
    iso = isolation('win32', e)
    lines.append('%s  Child runner (%s): %s' % ('OK     ' if iso['available'] else 'OFF    ', iso['mode'], iso['note']))
    blender = (report.get('programs') or {}).get('blender') or {}
    lines.append('%s  Blender (optional)' % ('OK     ' if blender.get('available') else 'absent '))
    lines.append('INFO     Long paths: keep the plugin and projects in short folders (e.g. C:\\H64) or enable '
                 'Windows long paths; unzip the plugin ZIP with Explorer or Expand-Archive, not git with autocrlf.')
    return lines


LINUX_DISK_MIN = 2 * 1024 ** 3        # bytes free: a game and its exports, or the 1.25 GB templates download


def linux_checklist(report=None, env=None, home=None, iso=None, disk=None):
    """Plain lines for a Linux owner, the first four required: Python, numpy, child runner, Godot. Each line is
    OK/MISSING/OFF/LOW/absent with the exact fix. report = doctor.probe(); iso = isolation('linux');
    disk = (free bytes, folder) or None."""
    report = report or {}
    e = _env(env)
    h = _home(home, 'linux')
    lines = []
    py = report.get('python') or {}
    lines.append('%s  Python 3.9+ (%s)' % ('OK     ' if py.get('supported') else 'MISSING', py.get('version') or '?'))
    ok = (py.get('numpy') or {}).get('available')
    lines.append('%s  numpy (room models without Blender, character bodies)%s' % (
        'OK     ' if ok else 'MISSING', '' if ok else ': approve numpy when Hermes asks (hermes plugins enable '
        'hermes64), or point python_path at a Python that has it'))
    iso = iso or isolation('linux', e)
    ready = iso['available'] and iso['mode'] == 'bwrap' and iso.get('runner_probe_ok', False)
    note = iso['note'] + ('' if ready or not iso['available'] else
                          ' No sandboxed Runner.run readiness child passed; READY is withheld.')
    lines.append('%s  Child runner (%s): %s' % (
        'OK     ' if ready else 'MISSING' if iso['available'] else 'OFF    ', iso['mode'], note))
    godot = (report.get('programs') or {}).get('godot') or {}
    lines.append('%s  Godot 4.6.2 standard build%s' % (
        'OK     ' if godot.get('available') else 'MISSING',
        ' at ' + godot['path'] if godot.get('path') else
        ': download Godot_v4.6.2-stable_linux.x86_64.zip (or .arm64) from the official 4.6.2-stable release, check it '
        'against SHA512-SUMS.txt, unzip, chmod +x, and set HERMES64_GODOT (or godot_path) to the file; snap and '
        'flatpak builds are not used (docs/LINUX.md)'))
    ok = (py.get('pillow') or {}).get('available')
    lines.append('%s  Pillow (JPEG references)%s' % ('OK     ' if ok else 'absent ', '' if ok else
                                                     ': optional; approve it with numpy'))
    tpl = report.get('export_templates') or {}
    lines.append('%s  Export templates %s in %s (installed targets: %s; from Linux: web and windows; no native Linux '
                 'or macOS export)' % ('OK     ' if 'web' in (tpl.get('targets') or []) else 'absent ', TEMPLATE_VERSION,
                                       tpl.get('folder') or templates_dir('linux', e, h),
                                       ', '.join(tpl.get('targets') or []) or 'none'))
    blender = (report.get('programs') or {}).get('blender') or {}
    lines.append('%s  Blender (optional)' % ('OK     ' if blender.get('available') else 'absent '))
    ffmpeg = report.get('ffmpeg') or {}
    lines.append('%s  ffmpeg (optional: FLAC/M4A/Opus/AIFF audio import)' % ('OK     ' if ffmpeg.get('available')
                                                                               else 'absent '))
    if disk:
        free, folder = disk
        lines.append('%s  Disk space: %.1f GiB free in %s (keep at least %d GiB)' % (
            'OK     ' if free >= LINUX_DISK_MIN else 'LOW    ', free / 1024 ** 3, folder, LINUX_DISK_MIN // 1024 ** 3))
    lines.append('INFO     Authoring is headless on Linux: Godot runs without a display, so screenshots and the '
                 'measured style audit are skipped (reported as such). Web exports play in a browser from a local '
                 '127.0.0.1 server (Studio Play, or python3 -m http.server --bind 127.0.0.1).')
    return lines


def _unique(items):
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _natural(path):
    """Sort key that orders 'Blender 4.10' after 'Blender 4.9' (numbers compared as numbers)."""
    import re
    return [(0, int(part), '') if part.isdigit() else (1, 0, part.lower())
            for part in re.split(r'(\d+)', Path(str(path)).name)]


def _glob_windows(root, pattern, names, env):
    """Real directory listing only when running on Windows (on other hosts the folder cannot exist). Newest first."""
    if host() != 'win32':
        return []
    try:
        folders = sorted(Path(str(root)).glob(pattern), key=_natural, reverse=True)
    except OSError:
        return []
    return [PureWindowsPath(str(f)) / n for f in folders for n in names]


def _glob_linux(root, pattern, names):
    """Real directory listing only when running on Linux (simulations on other hosts list nothing). Newest first."""
    if host() != 'linux':
        return []
    try:
        folders = sorted((f for f in Path(str(root)).glob(pattern) if f.is_dir()), key=_natural, reverse=True)
    except OSError:
        return []
    return [PurePosixPath(str(f)) / n for f in folders for n in names]


__all__ = ['host', 'is_windows', 'command_line', 'split_args', 'pure', 'looks_like_path', 'exe_name', 'python_command', 'override', 'candidates',
           'godot_candidates', 'blender_candidates', 'python_candidates', 'templates_dir', 'project_local_dir',
           'isolation', 'windows_checklist', 'windows_runner_enabled', 'linux_checklist', 'sandboxed_package',
           'PureWindowsPath', 'PurePosixPath']
