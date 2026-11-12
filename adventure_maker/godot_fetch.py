"""Explicit, pinned Godot fetch. Stdlib only; importing/discovery never downloads or executes.

Only official upstream files are fetched: the Godot 4.6.2 editor zip for this OS and (optionally) the official
export_templates.tpz, both from github.com/godotengine/godot-builds, each pinned by its published SHA-512. From the
.tpz only the three players exports use are kept (each sha256-checked against export.TEMPLATE_HASHES), then the
.tpz is deleted. Consent is human-only: fetch() runs from the typed CLI or `/hermes64 setup --fetch --yes`, never
from a model tool call (setup_check.tool_handler cannot pass yes).
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .runner import scratch_env

MANIFEST = Path(__file__).resolve().parents[1] / 'tools/fetch-manifest.json'
VERSION = '4.6.2'
MAX_DOWNLOAD = 1400 * 1024 * 1024          # hard ceiling for any one file (the official .tpz is about 1.25 GB)
MAX_UNPACKED = 1024 * 1024 * 1024
MAX_MEMBERS = 4096
MAX_TEMPLATE_MEMBER = 600 * 1024 * 1024
EXECUTABLES = {'darwin': 'Godot.app/Contents/MacOS/Godot', 'windows': 'Godot_v4.6.2-stable_win64.exe'}
ARTIFACTS = {'darwin': 'godot-4.6.2-macos-editor', 'windows': 'godot-4.6.2-windows-editor'}
TEMPLATES_ARTIFACT = 'godot-4.6.2-export-templates'
TEMPLATE_VERSION = '4.6.2.stable'
# The one origin a pinned row may name; redirects may only go to GitHub's release-asset hosts.
ORIGIN = 'https://github.com/godotengine/godot-builds/releases/download/4.6.2-stable/'
HOSTS = ('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')


class FetchError(ValueError):
    """Plain, fail-closed setup refusal."""


def platform_key():
    return 'darwin' if sys.platform == 'darwin' else 'windows' if os.name == 'nt' else 'linux'


def cache_dir(platform=None):
    key = platform or platform_key()
    if key == 'darwin':
        return Path.home() / 'Library/Caches/hermes64'
    if key == 'windows':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / 'hermes64'
    raise FetchError('Godot fetch is unsupported on Linux/this platform; no Linux archive hash is pinned.')


def artifacts():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))['artifacts']


def godot_artifact(platform=None):
    key = platform or platform_key()
    if key not in ARTIFACTS:
        raise FetchError('Godot fetch is unsupported on Linux/this platform; no Linux archive hash is pinned.')
    return dict(artifacts()[ARTIFACTS[key]], executable=EXECUTABLES[key])


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https':
        raise FetchError('HTTPS is required; HTTP downloads and redirect downgrades are refused.')
    host = (parsed.hostname or '').lower()
    allowed = host in HOSTS
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        valid_port = False
    if not allowed or not valid_port or parsed.username or parsed.password or parsed.fragment:
        raise FetchError('Download/redirect host refused: only %s over HTTPS are allowed.' % ', '.join(HOSTS))


def validate_origin(url):
    """A pinned row's own URL: exactly an official godot-builds 4.6.2-stable release asset (redirects: validate_url)."""
    validate_url(url)
    name = url[len(ORIGIN):] if url.startswith(ORIGIN) else ''
    if not name or '/' in name or '?' in name or '..' in name:
        raise FetchError('Source refused: only official files under %s are fetched.' % ORIGIN)


def _pin(row):
    """Every fetched file is an official Godot file pinned by its published SHA-512; nothing weaker is accepted."""
    value = row.get('sha512', '')
    if isinstance(value, str) and re.fullmatch('[0-9a-f]{128}', value):
        return 'sha512', value
    raise FetchError('No valid official SHA-512 pin; nothing was downloaded.')


def _digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with open(path, 'rb') as src:
        for block in iter(lambda: src.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy):
        self.policy = policy
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 5:
            raise FetchError('Too many download redirects (limit 5).')
        self.policy(newurl)  # Refuse before urllib creates/sends the redirected request.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(row, dest, emit=print, *, _url_policy=None, timeout=600):
    """Clean restart, not byte-range resume. Any failure removes this attempt's file.

    _url_policy is a private dependency-injection seam for loopback fixtures, never a CLI/config option.
    Proxies are disabled so neither ambient credentials nor proxy routing alter the pinned origin.
    """
    policy = _url_policy or validate_url
    algorithm, pin = _pin(row)
    url = row.get('url', '')
    policy(url)
    cap = min(int(row.get('max_bytes', MAX_DOWNLOAD)), MAX_DOWNLOAD)
    if cap <= 0 or timeout <= 0:
        raise FetchError('Invalid download size cap or timeout.')
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    # Exclusive create: do not follow/overwrite a stale partial symlink.
    part.unlink(missing_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirects(policy))
    started = last = time.monotonic()
    count = 0
    h = hashlib.new(algorithm)
    emit('Downloading %s: 0 bytes (cap %s bytes)' % (url, cap))
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hermes64-setup/1', 'Accept-Encoding': 'identity'})
        with opener.open(req, timeout=min(5, timeout)) as src, part.open('xb') as out:
            if src.status != 200:
                raise FetchError('Download returned HTTP %s; expected 200.' % src.status)
            length = src.headers.get('Content-Length')
            expected = int(length) if length is not None else None
            if expected is not None and (expected < 0 or expected > cap):
                raise FetchError('Download exceeds size cap (%s bytes).' % cap)
            while True:
                if time.monotonic() - started >= timeout:
                    raise FetchError('Download timeout; rerun setup --fetch to restart cleanly.')
                block = src.read1(64 * 1024)
                if not block:
                    break
                count += len(block)
                if count > cap:
                    raise FetchError('Download exceeds size cap (%s bytes).' % cap)
                h.update(block)
                out.write(block)
                now = time.monotonic()
                if now - last >= 2:
                    emit('Downloading: %s%s bytes' % (count, ('/%s' % expected) if expected is not None else ''))
                    last = now
            if expected is not None and count != expected:
                raise FetchError('Download truncated: received %s of %s bytes; rerun setup --fetch.' % (count, expected))
            if h.hexdigest() != pin:
                raise FetchError('Archive hash mismatch (%s); partial file deleted. Nothing was unpacked or run.' % algorithm)
        os.replace(part, dest)
        emit('Verified %s: %s bytes (%s).' % (algorithm, count, pin))
        return dest
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as exc:
        part.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        if isinstance(exc, FetchError):
            raise
        raise FetchError('Download failed: %s. Partial file deleted; rerun setup --fetch to restart.' % str(exc)[:400]) from exc
    except BaseException:
        part.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise


def check_roster(infos, member_cap=MAX_DOWNLOAD, total_cap=MAX_UNPACKED):
    """Refuse the whole archive on any traversal, absolute/drive path, symlink/device, duplicate or size bomb."""
    seen = set()
    total = 0
    if len(infos) > MAX_MEMBERS:
        raise FetchError('Archive has too many members.')
    for info in infos:
        name = info.filename
        parts = PurePosixPath(name).parts
        kind = stat.S_IFMT(info.external_attr >> 16)
        if (not parts or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or
                any(p in ('.', '..') or p.endswith(('.', ' ')) for p in parts) or
                kind not in (0, stat.S_IFREG, stat.S_IFDIR) or name.casefold() in seen):
            raise FetchError('Unsafe archive member (path traversal, symlink or duplicate): ' + name[:160])
        seen.add(name.casefold())
        total += info.file_size
        if info.file_size > member_cap or (total_cap is not None and total > total_cap):
            raise FetchError('Archive unpacked size cap exceeded.')


def unpack(archive, dest):
    """Validate the whole roster before any writes; no symlinks, devices, traversal or zip bombs."""
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            check_roster(infos)
            for info in infos:
                path = Path(dest).joinpath(*PurePosixPath(info.filename).parts)
                if info.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, path.open('xb') as out:
                        shutil.copyfileobj(src, out, 64 * 1024)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        if isinstance(exc, FetchError):
            raise
        raise FetchError('Could not unpack verified archive: ' + str(exc)[:300]) from exc


def clear_quarantine(app):
    """Only the newly hash-verified extracted Godot.app, never a parent or another install."""
    xattr = shutil.which('xattr', path=os.defpath)
    if not xattr:
        raise FetchError('Could not find the system xattr tool; quarantine was not changed.')
    with scratch_env() as env:
        out = subprocess.run([xattr, '-r', '-d', 'com.apple.quarantine', str(app)],
                             capture_output=True, text=True, encoding='utf-8', timeout=15,
                             stdin=subprocess.DEVNULL, env=env)
    errors = [line for line in out.stderr.splitlines() if line.strip()]
    absent_only = bool(errors) and all('No such xattr: com.apple.quarantine' in line for line in errors)
    if out.returncode and not absent_only:
        raise FetchError('Could not clear quarantine on the verified Godot.app. Gatekeeper may require Control-click > Open: ' + out.stderr[:300])


def version_check(exe):
    # Runner's minimal environment (scratch HOME/TMPDIR, system PATH): never Hermes's variables or provider keys.
    with scratch_env() as env:
        out = subprocess.run([str(exe), '--version'], capture_output=True, text=True, encoding='utf-8',
                             timeout=15, stdin=subprocess.DEVNULL, env=env)
    version = out.stdout.strip()
    if out.returncode or not re.fullmatch(r'4\.6\.2\.stable(?:\.[A-Za-z0-9_-]+)*', version):
        raise FetchError('Verified Godot failed --version check (expected 4.6.2.stable): ' + version[:160])
    return version


def _tree_hashes(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise FetchError('Symlink in Godot cache; refusing reuse.')
        if path.is_file() and path.name != '.receipt.json':
            result[path.relative_to(root).as_posix()] = _digest(path)
    return result


def _cached(row, folder):
    try:
        if folder.is_symlink():
            return None
        receipt = json.loads((folder / '.receipt.json').read_text(encoding='utf-8'))
        algorithm, pin = _pin(row)
        exe = folder / row['executable']
        if (receipt['pin'] == {algorithm: pin} and receipt['version'].startswith('4.6.2.stable') and
                receipt['executable'] == row['executable'] and exe.is_file() and
                receipt['files'] == _tree_hashes(folder)):
            return exe
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def cached_godot(platform=None):
    """Read-only finder candidate. No process, HTTP request or quarantine changes."""
    key = platform or platform_key()
    if key not in ARTIFACTS:
        return None
    return _cached(godot_artifact(key), cache_dir(key) / 'godot' / VERSION / key)


def install_godot(row, cache, platform, emit=print, *, _url_policy=None):
    if platform not in EXECUTABLES or row.get('executable') != EXECUTABLES[platform]:
        raise FetchError('Unsupported platform or unexpected Godot executable layout.')
    # Godot archives must use Main's official SHA-512 pin, never a weaker fallback field.
    if not re.fullmatch('[0-9a-f]{128}', row.get('sha512', '')):
        raise FetchError('Godot requires a valid official SHA-512 archive pin; nothing was downloaded.')
    (_url_policy or validate_origin)(row['url'])
    folder = Path(cache) / 'godot' / VERSION / platform
    existing = _cached(row, folder)
    if existing:
        emit('Already present and integrity-checked: %s (no download).' % existing)
        return existing
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.fetch-', dir=str(folder.parent)) as work:
            work = Path(work)
            zipped = download(row, work / 'godot.zip', emit, _url_policy=_url_policy)
            stage = work / 'engine'
            stage.mkdir()
            unpack(zipped, stage)
            exe = stage / row['executable']
            if not exe.is_file():
                raise FetchError('Verified zip lacks the expected Godot executable: ' + row['executable'])
            if platform == 'darwin':
                exe.chmod(0o755)
                clear_quarantine(stage / 'Godot.app')
            version = version_check(exe)  # First and only engine execution during setup.
            algorithm, pin = _pin(row)
            receipt = {'pin': {algorithm: pin}, 'executable': row['executable'], 'version': version, 'files': _tree_hashes(stage)}
            (stage / '.receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
            if folder.is_symlink():
                raise FetchError('Godot cache destination is a symlink; refusing replacement.')
            if folder.exists():
                shutil.rmtree(folder)
            os.replace(stage, folder)
        emit('Godot %s ready: %s' % (version, folder / row['executable']))
        return folder / row['executable']
    except (OSError, subprocess.SubprocessError) as exc:
        raise FetchError('Godot setup failed; nothing unverified was adopted: ' + str(exc)[:400]) from exc


def templates_artifact():
    return dict(artifacts()[TEMPLATES_ARTIFACT])


def template_dir(cache):
    """Where the kept official players live: <hermes64 cache>/templates/4.6.2.stable (never the plugin folder)."""
    return Path(cache) / 'templates' / TEMPLATE_VERSION


def _template_pins():
    from .export import TEMPLATES, TEMPLATE_HASHES
    return {TEMPLATES[t]: TEMPLATE_HASHES[t] for t in TEMPLATES}


def _templates_present(folder, pins):
    try:
        return (not folder.is_symlink() and (folder / 'version.txt').read_text(encoding='utf-8').strip() == TEMPLATE_VERSION
                and all((folder / name).is_file() and not (folder / name).is_symlink() and _digest(folder / name) == pin
                        for name, pin in pins.items()))
    except OSError:
        return False


def install_templates(row, cache, emit=print, *, _url_policy=None):
    """Download the official .tpz, keep only the pinned players (member by name, never path extraction), delete it."""
    if not re.fullmatch('[0-9a-f]{128}', row.get('sha512', '')):
        raise FetchError('Export templates require the official SHA-512 pin; nothing was downloaded.')
    (_url_policy or validate_origin)(row['url'])
    pins = _template_pins()
    folder = template_dir(cache)
    if _templates_present(folder, pins):
        emit('Export templates already present and hash-checked: %s (no download).' % folder)
        return folder
    for p in (folder, folder.parent, Path(cache)):
        if p.is_symlink():
            raise FetchError('Template cache path is a symlink; refusing.')
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.fetch-', dir=str(folder.parent)) as work:
            work = Path(work)
            tpz = work / 'export_templates.tpz'
            try:
                download(row, tpz, emit, _url_policy=_url_policy)
                stage = work / 'stage'
                stage.mkdir()
                with zipfile.ZipFile(tpz) as z:
                    check_roster(z.infolist(), member_cap=MAX_TEMPLATE_MEMBER, total_cap=None)
                    try:
                        version_info = z.getinfo('templates/version.txt')
                    except KeyError:
                        raise FetchError('Verified .tpz lacks templates/version.txt; nothing kept.')
                    if version_info.file_size > 64 or z.read(version_info).decode('utf-8', 'replace').strip() != TEMPLATE_VERSION:
                        raise FetchError('Verified .tpz is not %s; nothing kept.' % TEMPLATE_VERSION)
                    (stage / 'version.txt').write_text(TEMPLATE_VERSION + '\n', encoding='utf-8')
                    for name, pin in sorted(pins.items()):
                        try:
                            info = z.getinfo('templates/' + name)
                        except KeyError:
                            raise FetchError('Verified .tpz lacks templates/%s; nothing kept.' % name)
                        h = hashlib.sha256()
                        with z.open(info) as src, (stage / name).open('xb') as out:
                            for block in iter(lambda: src.read(1 << 20), b''):
                                h.update(block)
                                out.write(block)
                        if h.hexdigest() != pin:
                            raise FetchError('Template %s does not match its pinned sha256; nothing kept.' % name)
            finally:
                if tpz.exists():
                    tpz.unlink()
                    emit('Deleted the downloaded .tpz (kept only the players exports use).')
            if folder.is_symlink():
                raise FetchError('Template cache destination is a symlink; refusing replacement.')
            if folder.exists():
                shutil.rmtree(folder)
            os.replace(stage, folder)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise FetchError('Export template setup failed; nothing unverified was kept: ' + str(exc)[:400]) from exc
    emit('Export templates ready: %s (%s)' % (folder, ', '.join(sorted(pins))))
    return folder


def plan(platform=None, include_templates=False):
    """The disclosure shown before any download: files, official URLs, SHA-512 pins, caps, cache folder."""
    key = platform or platform_key()
    rows = [('Godot 4.6.2 editor', godot_artifact(key))]
    if include_templates:
        rows.append(('Godot 4.6.2 export templates (optional)', templates_artifact()))
    lines = ['Hermes64 setup download (official Godot release files only; Godot is MIT licensed, notices: licenses/godot-4.6.2/).',
             'Destination (per-user cache, not the plugin): %s' % cache_dir(key)]
    for name, item in rows:
        algorithm, pin = _pin(item)
        validate_url(item['url'])
        size = str(item['bytes']) + ' bytes' if isinstance(item.get('bytes'), int) else str(item.get('bytes') or 'size unknown')
        lines += ['%s: %s; hard download cap %s bytes.' % (name, size, item.get('max_bytes', MAX_DOWNLOAD)),
                  'Source: %s' % item['url'], '%s: %s; licence: %s' % (algorithm, pin, item.get('licence', 'MIT'))]
    lines += ['Each file is checked against its official SHA-512 before anything is unpacked; a mismatch deletes it.',
              'Godot unpacked cap: %s bytes; download timeout: 600 s per file (5 s socket inactivity).' % MAX_UNPACKED,
              'macOS: remove quarantine only from this newly verified Godot.app; run only --version after verification.']
    if include_templates:
        lines.append('Templates: keep only web_nothreads_release.zip, macos.zip and windows_release_x86_64.exe '
                     '(each sha256-pinned) in %s, then delete the .tpz.' % template_dir(cache_dir(key)))
    else:
        lines.append('Export templates not requested (making and playing games do not need them); add --templates to include them.')
    return '\n'.join(lines)


def fetch(yes=False, include_templates=False, emit=print, confirm=input):
    """Only the human-typed CLI or `/hermes64 setup --fetch` calls this; no automatic or model-initiated fetch."""
    key = platform_key()
    emit(plan(key, include_templates))  # Always disclose before asking/doing anything.
    if not yes:
        try:
            answer = confirm('Download and verify these files? [y/N] ')
        except (EOFError, OSError):
            answer = ''
        if answer.strip().lower() not in ('y', 'yes'):
            emit('Nothing downloaded. To confirm explicitly, rerun setup --fetch --yes.')
            return None
    exe = install_godot(godot_artifact(key), cache_dir(key), key, emit)
    if include_templates:
        install_templates(templates_artifact(), cache_dir(key), emit)
    return exe
