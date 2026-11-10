"""Hermes64 Studio backend: routes under /api/plugins/hermes64/ for desktop/plugin.js.

Mounted by the Hermes dashboard plugin loader (``dashboard/manifest.json``) only when
``hermes64`` is in ``plugins.enabled``. Python stdlib plus the FastAPI router the host
provides. What it reads and serves:

- ``GET  /studio/catalogue``          the catalogue built by adventure_maker/studio_catalogue.py
  from the configured ``projects_root`` (read-only, confined, bounded; no absolute paths).
- ``GET  /studio/cover/<id>/<n>/<tag>`` one cover/shot PNG as a data URL, re-derived from disk.
- ``GET  /studio/sound/<cue>``         one of ten UI cue WAVs from this plugin's audio/ folder.
- ``GET  /studio/folder/<id>``         the project's absolute folder, for an explicit
  "Open folder" click (the desktop half calls ctx.os.revealPath with it).

Side effects, each only on an explicit click in the Studio:

- ``POST /studio/play``   serves ONE confined web export on 127.0.0.1 (random port, random
  path token) for the SDK's SandboxedFrame. One server at a time; it stops on
  ``/studio/stop``, on the next play, or after 30 idle minutes.
- ``POST /studio/stop``   stops that server.
- ``POST /studio/launch`` macOS only: ``/usr/bin/open -n`` on the exported .app that the
  scan finds for that game (never a client-supplied path).

No network beyond 127.0.0.1, no uploads, no writes. Handlers are plain ``def`` so the
host runs them off the event loop.
"""
import base64
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLUGIN_ID = 'hermes64'
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r'[a-z][a-z0-9_-]{0,63}')
TAG = re.compile(r'[0-9a-f]{12}')
CUE = re.compile(r'[a-z0-9][a-z0-9.]{0,63}')
UI_CUES = ('ui.move', 'ui.select', 'ui.back', 'hatch.open', 'core.ui.move.02', 'core.hatch.slide.open',
           'core.machine.computer.accept', 'core.magic.chime', 'core.ui.confirm.01', 'core.ui.error.01')
EXPORT_FILE_LIMIT = 512 * 1024 * 1024
IDLE_SECONDS = 30 * 60
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.wasm': 'application/wasm',
         '.pck': 'application/octet-stream', '.png': 'image/png', '.json': 'application/json', '.svg': 'image/svg+xml',
         '.ico': 'image/x-icon', '.webp': 'image/webp', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg'}
# A running web build owns the keyboard: its canvas takes focus inside an out-of-process,
# sandboxed frame, so neither the Studio nor the Desktop sees a single key while it plays.
# The play server adds this to the export's entry page only. Holding Esc (0.6 s) asks the
# Studio to eject; a short Esc stays with the game (pause menus). It reads nothing and
# posts one fixed message; the Studio accepts it only from its own frame.
# The timer ejects while Esc is still held; the keyup check (event timestamps) covers frames
# whose timers are throttled, so a 0.6 s hold always ejects and a short press never does.
EJECT_BRIDGE = (b'<script>/* hermes64-studio: hold Esc to eject */(function(){var t=null,d=0;'
                b'function c(){if(t){clearTimeout(t);t=null}d=0}'
                b'function go(){c();try{parent.postMessage({hermes64:"eject"},"*")}catch(x){}}'
                b'addEventListener("keydown",function(e){if(e.key!=="Escape"||e.repeat||d)return;'
                b'd=e.timeStamp||1;t=setTimeout(go,600)},true);'
                b'addEventListener("keyup",function(e){if(e.key!=="Escape")return;'
                b'if(d&&e.timeStamp-d>=600)go();else c()},true);'
                b'addEventListener("blur",c)})()</script>')
BRIDGE_PAGE_LIMIT = 2 * 1024 * 1024


def with_eject_bridge(html):
    """The entry page with EJECT_BRIDGE as the first thing in <head> (or first in the file)."""
    m = re.search(rb'<head\b[^>]*>', html[:65536], re.I)
    at = m.end() if m else 0
    return html[:at] + EJECT_BRIDGE + html[at:]


def _load_scanner():
    # The host imports this file by path, so the package is loaded by path as well.
    name = 'hermes64_studio_catalogue'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(PLUGIN_ROOT / 'adventure_maker' / 'studio_catalogue.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load_scanner()


def settings_from_config():
    """projects_root from plugins.entries.hermes64.settings (legacy: .config), as the agent half reads it."""
    try:
        from hermes_cli.config import load_config_readonly
    except Exception:  # pragma: no cover - only inside the Hermes gateway
        return {}
    cfg = load_config_readonly() or {}
    entry = ((cfg.get('plugins') or {}).get('entries') or {}).get(PLUGIN_ID) or {}
    for key in ('settings', 'config'):
        block = entry.get(key)
        if isinstance(block, dict) and isinstance(block.get('projects_root'), str) and block['projects_root']:
            return {'projects_root': block['projects_root']}
    return default_games_settings()


def default_games_settings():
    """With projects_root blank, `/hermes64 new` puts games in ``<plugin data>/games`` (adventure_maker.plugin_settings).
    Show that same folder, once it exists, so a first game made with no settings appears on the shelf.
    Both halves use the documented plugins.plugin_storage.plugin_data_dir (Hermes 0.20.4+)."""
    try:
        from plugins.plugin_storage import plugin_data_dir
        games = Path(str(plugin_data_dir(PLUGIN_ID))) / 'games'
    except Exception:  # pragma: no cover - older hosts without plugin data folders
        return {}
    return {'projects_root': str(games)} if games.is_absolute() and games.is_dir() and not games.is_symlink() else {}


def _fail(code, message):
    return {'ok': False, 'code': code, 'message': message}


def _root(settings):
    root = (settings or {}).get('projects_root') or ''
    if not root:
        raise sc.ScanError('CONFIG', 'No projects folder yet: set Projects root in Settings ▸ Plugins ▸ Hermes64 Studio, then try again.')
    return root


_known = None


def known_styles():
    """Labels/colours of the plugin's own bundled packs (trusted plugin files, not user data)."""
    global _known
    if _known is None:
        out = {}
        packs = PLUGIN_ROOT / 'packs'
        if packs.is_dir() and not packs.is_symlink():
            for d in sorted(packs.iterdir()):
                f = d / 'pack.json'
                if d.is_symlink() or not f.is_file() or f.is_symlink() or f.stat().st_size > sc.LIMITS['json_bytes']:
                    continue
                try:
                    doc = sc.parse_json(f.read_bytes())
                except sc.ScanError:
                    continue
                if isinstance(doc, dict) and isinstance(doc.get('id'), str) and sc.ID.fullmatch(doc['id']):
                    pip, pal = sc.summarise_palette(doc.get('palette') if isinstance(doc.get('palette'), list) else [])
                    out[doc['id']] = {'label': str(doc.get('name') or doc['id'])[:40], 'colour': pip, 'palette': pal}
        _known = out
    return _known


def api_catalogue(settings):
    try:
        cat = sc.scan(_root(settings), known_styles())
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)
    for g in cat['games']:
        cover = g.get('cover') or {}
        if 'sha256' in cover:
            cover['src'] = 'cover/' + g['id'] + '/0/' + cover['sha256'][:12]
        for i, shot in enumerate(g.get('shots', [])):
            if 'sha256' in shot:
                shot['src'] = 'cover/' + g['id'] + '/' + str(i + 1) + '/' + shot['sha256'][:12]
    return {'ok': True, 'catalogue': cat}


def api_cover(settings, game, index, tag):
    if not isinstance(game, str) or not SLUG.fullmatch(game) or not isinstance(tag, str) or not TAG.fullmatch(tag) or str(index) not in ('0', '1', '2', '3'):
        return _fail('ARGUMENT', 'bad image request')
    try:
        raw = sc.find_image(_root(settings), game, int(index), tag, known_styles())
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)
    return {'ok': True, 'data_url': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')}


def api_sound(cue):
    if not isinstance(cue, str) or not CUE.fullmatch(cue) or cue not in UI_CUES:
        return _fail('ARGUMENT', 'unknown cue')
    try:
        catalog = sc.parse_json((PLUGIN_ROOT / 'audio' / 'catalog.json').read_bytes())
    except (OSError, sc.ScanError):
        return _fail('MISSING', 'audio catalog unavailable')
    row = next((a for a in catalog.get('assets', []) if isinstance(a, dict) and a.get('id') == cue), None)
    rel = 'wav/' + cue + '.wav' if cue.startswith(('ui.', 'hatch.')) else 'stock/wav/' + cue + '.wav'
    if row is None:
        return _fail('MISSING', 'cue not in the audio catalog')
    try:
        with sc.Root(str(PLUGIN_ROOT / 'audio')) as root:
            raw = root.read(rel, 1024 * 1024)
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        return _fail('FORMAT', 'not a WAV file')
    return {'ok': True, 'data_url': 'data:audio/wav;base64,' + base64.b64encode(raw).decode('ascii')}


def api_folder(settings, game):
    try:
        return {'ok': True, 'path': sc.project_dir(_root(settings), game)}
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)


def _export(settings, game, target):
    if not isinstance(game, str) or not SLUG.fullmatch(game):
        raise sc.ScanError('ARGUMENT', 'bad game id')
    root = _root(settings)
    with sc.Root(root) as r:
        if (r.entry(game) or ('',))[0] != 'dir':
            raise sc.ScanError('MISSING', 'no such project')
        row, _styles = sc.scan_project(r, game, known_styles())
    found = next((e for e in row.get('exports', []) if e.get('target') == target), None)
    if not found:
        raise sc.ScanError('NO_EXPORT', 'No ' + target + ' export found for this game. Export it first.')
    return root, game + '/' + found['path'], found['entry']


class _PlayServer:
    """At most one localhost static server for one confined web export."""
    lock = threading.Lock()
    current = None

    @classmethod
    def start(cls, projects_root, base_rel, entry):
        cls.stop()
        token = secrets.token_urlsafe(18)
        state = {'last': time.monotonic()}

        class Handler(BaseHTTPRequestHandler):
            server_version = 'Hermes64Studio'
            sys_version = ''

            def log_message(self, *args):  # keep the gateway log quiet
                pass

            def _send_error(self, code):
                self.send_response(code)
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()

            def do_HEAD(self):
                self.do_GET(head=True)

            def do_GET(self, head=False):
                state['last'] = time.monotonic()
                path = self.path.split('?', 1)[0].split('#', 1)[0]
                prefix = '/' + token + '/'
                if not path.startswith(prefix):
                    return self._send_error(404)
                rel = path[len(prefix):] or entry
                try:
                    with sc.Root(projects_root) as r:
                        fd, size = r.open_regular(base_rel + '/' + rel, EXPORT_FILE_LIMIT)
                except sc.ScanError:
                    return self._send_error(404)
                try:
                    ext = os.path.splitext(rel)[1].lower()
                    body = None
                    if rel == entry and ext == '.html' and size <= BRIDGE_PAGE_LIMIT:
                        raw = b''
                        while len(raw) < size:
                            chunk = os.read(fd, size - len(raw))
                            if not chunk:
                                break
                            raw += chunk
                        body = with_eject_bridge(raw)
                    self.send_response(200)
                    self.send_header('Content-Type', TYPES.get(ext) or mimetypes.types_map.get(ext, 'application/octet-stream'))
                    self.send_header('Content-Length', str(len(body) if body is not None else size))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    # The SandboxedFrame document has an opaque origin, so its fetches are cross-origin.
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.end_headers()
                    if body is not None:
                        if not head:
                            self.wfile.write(body)
                    elif not head:
                        sent = 0
                        while sent < size:
                            chunk = os.read(fd, min(1024 * 1024, size - sent))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            sent += len(chunk)
                finally:
                    os.close(fd)

            def do_POST(self):
                self._send_error(405)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name='hermes64-studio-play', daemon=True)
        thread.start()

        def reaper():
            while cls.current is not None and cls.current['server'] is server:
                time.sleep(15)
                if time.monotonic() - state['last'] > IDLE_SECONDS:
                    cls.stop(server)
                    return
        threading.Thread(target=reaper, name='hermes64-studio-reaper', daemon=True).start()
        with cls.lock:
            cls.current = {'server': server, 'token': token}
        return 'http://127.0.0.1:%d/%s/%s' % (server.server_address[1], token, entry)

    @classmethod
    def stop(cls, only=None):
        with cls.lock:
            cur = cls.current
            if cur is None or (only is not None and cur['server'] is not only):
                return False
            cls.current = None
        cur['server'].shutdown()
        cur['server'].server_close()
        return True


def api_play(settings, body):
    body = body if isinstance(body, dict) else {}
    if body.get('target', 'web') != 'web':
        return _fail('ARGUMENT', 'only web exports play inside the Studio')
    try:
        root, base_rel, entry = _export(settings, body.get('game'), 'web')
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)
    return {'ok': True, 'url': _PlayServer.start(root, base_rel, entry), 'note': 'Local 127.0.0.1 server for this one export; stops on eject or after 30 idle minutes.'}


def api_stop():
    return {'ok': True, 'stopped': _PlayServer.stop()}


def api_launch(settings, body, runner=subprocess.run):
    body = body if isinstance(body, dict) else {}
    if body.get('target') != 'macos':
        return _fail('ARGUMENT', 'only macOS builds launch natively here')
    if sys.platform != 'darwin':
        return _fail('PLATFORM', 'macOS builds open only on macOS')
    try:
        root, base_rel, entry = _export(settings, body.get('game'), 'macos')
        with sc.Root(root) as r:
            kind = (r.entry(base_rel + '/' + entry) or ('',))[0]
    except sc.ScanError as exc:
        return _fail(exc.code, exc.detail)
    if kind != 'dir' or not entry.endswith('.app'):
        return _fail('NO_EXPORT', 'the macOS export is not an app bundle')
    proc = runner(['/usr/bin/open', '-n', os.path.join(root, base_rel, entry)], stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15, check=False)
    if proc.returncode != 0:
        return _fail('LAUNCH', 'macOS refused to open the build (unsigned local builds may need right-click → Open once)')
    return {'ok': True}


try:  # FastAPI exists inside the Hermes gateway; the test harness calls the api_* functions directly.
    from fastapi import APIRouter, Body
except Exception:  # pragma: no cover
    APIRouter = None

if APIRouter is not None:
    router = APIRouter()

    @router.get('/studio/catalogue')
    def _catalogue():
        return api_catalogue(settings_from_config())

    @router.get('/studio/cover/{game}/{index}/{tag}')
    def _cover(game: str, index: str, tag: str):
        return api_cover(settings_from_config(), game, index, tag)

    @router.get('/studio/sound/{cue}')
    def _sound(cue: str):
        return api_sound(cue)

    @router.get('/studio/folder/{game}')
    def _folder(game: str):
        return api_folder(settings_from_config(), game)

    @router.post('/studio/play')
    def _play(body: dict = Body(default_factory=dict)):
        return api_play(settings_from_config(), body)

    @router.post('/studio/stop')
    def _stop(body: dict = Body(default_factory=dict)):
        return api_stop()

    @router.post('/studio/launch')
    def _launch(body: dict = Body(default_factory=dict)):
        return api_launch(settings_from_config(), body)
