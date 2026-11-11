"""Public ctx APIs only; closures bind each handler without global profile state."""
from pathlib import Path
import re
import time

from .schemas import SCHEMAS
from .service import Service
from .plugin_settings import plugin_settings
from . import wire

SETTINGS = ('projects_root', 'bundle_root', 'python_path', 'blender_path', 'godot_path', 'builder')
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
# BFIX: a clock read only (no I/O at registration). Files of this plugin created or rewritten after this moment mean
# the running Hermes process still executes the copy it loaded earlier (stale_notice below).
LOADED_AT = time.time()
# Files whose replacement means the running /hermes64 code is out of date (the routing and new-game paths).
WATCHED = ('__init__.py', 'plugin.yaml', 'adventure_maker/tools.py', 'adventure_maker/newgame.py',
           'adventure_maker/setup_check.py', 'adventure_maker/builders.py', 'adventure_maker/runner.py')
# Characters pasted text can carry that str.split() does not treat as spaces.
_INVISIBLE = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), ' ')
_NAMES = ('/hermes64', 'hermes64')
_HELP_WORDS = ('', 'help', '-h', '--help', '?')


def available():
    # Discovery/scaffold are useful even when optional local engines are absent.
    # Per-operation prerequisite errors are returned by the service.
    return True


def register_tools(ctx):
    def make_handler(name):
        def handler(args, **kwargs):
            return Service(plugin_settings(ctx, SETTINGS)).handle(name, args, **kwargs)
        return handler
    for name, schema in SCHEMAS.items():
        # Advertised copy is compact (wire.py); the handler validates against the full schema.
        wire.register(ctx, name, schema, make_handler(name), available)


def command_words(raw_args=None, **kwargs):
    """(subcommand, rest) from the text after `/hermes64`, whatever shape the host delivered it in.

    Hermes hands a plugin command the words after its name as one string (classic CLI `_run_plugin_slash_command`,
    gateway `slash.exec` -> `_hm_run_plugin_handler(args=...)`, TUI `slash.exec`/`command.dispatch`). This also takes a
    keyword instead of the positional argument, a token list, an event-like object, the command name echoed back,
    zero-width characters and a leading slash on the subcommand, so `new`, `setup` and `hub` route on any of them."""
    value = raw_args
    if value is None or value == '':
        for key in ('args', 'arg', 'text', 'command', 'input'):
            if kwargs.get(key) not in (None, ''):
                value = kwargs[key]
                break
    if isinstance(value, (list, tuple)):
        value = ' '.join(str(part) for part in value)
    elif value is not None and not isinstance(value, str):
        getter = getattr(value, 'get_command_args', None)
        try:
            value = getter() if callable(getter) else getattr(value, 'text', '')
        except Exception:
            value = ''
    text = value.translate(_INVISIBLE) if isinstance(value, str) else ''
    parts = text.split(None, 1)
    if parts and parts[0].lower() in _NAMES:
        parts = parts[1].split(None, 1) if len(parts) > 1 else []
    word = parts[0].lower().lstrip('/') if parts else ''
    return word, (parts[1] if len(parts) > 1 else '')


def build_label(root=None):
    """'Hermes64 1.0.0-rc (546d92a54d64)' from plugin.yaml and the package manifest; read when asked, never at load."""
    root = Path(root or PLUGIN_ROOT)
    version, commit = '', ''
    try:
        found = re.search(r'"version"\s*:\s*"([^"]+)"', (root / 'plugin.yaml').read_text(encoding='utf-8'))
        version = found.group(1) if found else ''
    except (OSError, UnicodeDecodeError):
        pass
    try:
        with open(root / 'PACKAGE-MANIFEST.json', 'rb') as handle:  # source commit sits at the end of the manifest
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 4096))
            found = re.search(rb'"commit"\s*:\s*"([0-9a-f]{7,64})"', handle.read())
        commit = found.group(1).decode()[:12] if found else ''
    except OSError:
        pass
    return 'Hermes64' + (' ' + version if version else '') + (' (%s)' % commit if commit else '')


def other_copies(root=None):
    """[(folder, version)] of other Hermes64 copies beside this one in the same plugins folder (an old copy left next to
    a new one, e.g. `hermes64 2` from unzipping next to an existing folder). Read when asked, never at load."""
    root = Path(root or PLUGIN_ROOT)
    found = []
    try:
        siblings = sorted(root.parent.iterdir())
    except OSError:
        return found
    for folder in siblings:
        if folder == root or folder.name.startswith('.'):
            continue
        try:
            with open(folder / 'plugin.yaml', encoding='utf-8', errors='replace') as handle:
                head = handle.read(600)
        except OSError:
            continue
        if re.search(r'"name"\s*:\s*"hermes64"', head):
            version = re.search(r'"version"\s*:\s*"([^"]+)"', head)
            found.append((str(folder), version.group(1) if version else '?'))
    return found


def running_line(root=None):
    """One closing line naming the copy that ran (and any other copy beside it), so a report pins the exact build."""
    root = Path(root or PLUGIN_ROOT)
    line = 'This is %s running from %s.' % (build_label(root), root)
    others = other_copies(root)
    if others:
        line += (' Another Hermes64 copy is installed beside it: %s. Keep one copy: remove the others, then restart '
                 'Hermes.' % '; '.join('%s (version %s)' % row for row in others[:3]))
    return line


def stale_notice(root=None, loaded_at=None):
    """One plain paragraph when this plugin's files were replaced after Hermes loaded them, else ''.

    A Hermes process keeps the plugin code it imported: a new copy unzipped over (or next to) an old one, while a
    Hermes CLI, desktop app or its background gateway is still running, is not what `/hermes64` executes. unzip keeps
    the archive's modification times, so the inode change time (set by any write) is compared too. Windows ctime is
    creation time, not metadata-change time: in-place replacement with restored mtime can evade this advisory.
    The running build line and a full owner-controlled restart remain the authoritative reload check."""
    root = Path(root or PLUGIN_ROOT)
    loaded_at = LOADED_AT if loaded_at is None else loaded_at
    newer = []
    for rel in WATCHED:
        try:
            info = (root / rel).stat()
        except OSError:
            continue
        if max(info.st_mtime, info.st_ctime) > loaded_at + 2:
            newer.append(rel)
    if not newer:
        return ''
    return ('Note: the Hermes64 files in %s were replaced after this Hermes process loaded them (%s), so it is still '
            'running the earlier copy. Quit every Hermes window and the desktop app, run: hermes gateway restart, then '
            'try again.\n' % (root, ', '.join(newer[:3])))


def help_command(raw_args='', **kwargs):
    word, _rest = command_words(raw_args, **kwargs)
    unknown = '' if word in _HELP_WORDS else ('"%s" is not a /hermes64 command. ' % word[:40])
    # NATIVE: short lines in the chat-safe subset (adventure_maker/chat_text.py); the agent path comes first.
    return '\n'.join((
        unknown + build_label() + ' makes N64-era-style 3D adventures. No commands needed: ask your agent, for '
        'example "make me a game about a lighthouse keeper and a storm".',
        '- Your agent follows the skill `hermes64:hermes64-create`: `create_flow plan`, then `create_flow run`, then '
        '`hermes64_edit`, `hermes64_check`, `hermes64_playtest`, `hermes64_open` and `hermes64_export`.',
        '- Checkup: /hermes64 setup prints a checklist (Godot, Blender optional, numpy/Pillow, ffmpeg optional, '
        'games folder) with the next step for anything missing; /hermes64 setup --fetch explicitly offers a pinned '
        'Godot download.',
        '- Quick start without the agent: /hermes64 new "a one-sentence premise" and optionally village, forest or '
        'polar: it builds, proof-checks and bot-plays the game, then prints a proof badge and the command to play it.',
        '- Your own story spec: `hermes64_packs`, `hermes64_scaffold` (pack=ID), `hermes64_compile`, '
        '`hermes64_check`; check after every edit. Setup trouble: `hermes64_doctor`.',
        '- Characters, audio, enemies and puzzles, styles, box art: only when asked (see the skill). Share and reuse: '
        '/hermes64 hub search and your words (then hub info, hub install, hub pack, hub publish).',
        '- Never hand-edit generated files. Other downloads require `hub_url`. Other /hermes64 text only shows this '
        'help; it is never executed.'))


def make_command(ctx):
    """`/hermes64 setup` prints the checklist, `/hermes64 new ...` creates a game (data only), `/hermes64 hub ...` runs a
    hub action; anything else is help. A copy replaced on disk after Hermes loaded it is named first (stale_notice)."""
    def command(raw_args='', **kwargs):
        word, rest = command_words(raw_args, **kwargs)
        if word == 'new':
            from .newgame import command as run
        elif word == 'hub':
            from .hub import command as run
        elif word == 'setup':
            from .setup_check import command as run
        else:
            run = None
        text = run(ctx, rest) if run is not None else help_command(raw_args, **kwargs)
        notice = stale_notice()
        from .platforms import console_text
        from .chat_text import tidy   # NATIVE: no escape codes or deep indentation in a chat reply
        return console_text(tidy(notice + text if notice else text))
    return command
