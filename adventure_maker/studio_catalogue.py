"""Hermes64 Studio catalogue scanner: read-only, confined, deterministic.

Describes every game project under the plugin's configured ``projects_root`` for
the Studio tab (``desktop/plugin.js`` through ``dashboard/plugin_api.py``).
Python stdlib only. Nothing is written, executed, uploaded or fetched.

Confinement. ``projects_root`` must be an absolute existing directory that is not
itself a symlink. Below it, every path is opened component by component against
an open directory descriptor with ``O_NOFOLLOW``, so a symlink anywhere in a path
is refused instead of followed; FIFOs, sockets and devices are refused before
any read; every read and listing is bounded (``LIMITS``). Hard links are ordinary
files inside the tree and are read as such.

Determinism. Listings are sorted, output keys are sorted, and the catalogue
carries no timestamps, absolute paths or user names. Where several runs exist,
the newest is chosen by (directory mtime, name), which is fixed for a given tree.

Honesty. A verdict only counts as current when its report names the current
build's ``game_hash``. Reports that cannot be tied to the current build are shown
as stale. Human playtest is ``not_yet`` unless an explicit local marker matches.

    python3 -B -m adventure_maker.studio_catalogue /absolute/projects_root [--out new-file.json]
"""
import errno
import hashlib
import json
import os
import re
import stat
import struct
import sys

SCHEMA_ID = 'hermes64.studio.catalogue/1'
GENERATOR = {'name': 'adventure_maker.studio_catalogue', 'version': '1'}
LIMITS = {
    'projects': 512,          # entries considered directly under projects_root
    'dir_entries': 4096,      # entries considered in any one directory listing
    'json_bytes': 2 * 1024 * 1024,
    'png_bytes': 4 * 1024 * 1024,
    'png_side': 4096,
    'proof_reads': 64,        # newest proof files read per project
    'report_reads': 32,       # newest replay/playtest/asset reports read per project
    'export_reads': 8,        # newest export folders inspected per project
    'files_rows': 20000,      # rows summed from one export FILES.json
}
SLUG = re.compile(r'[a-z][a-z0-9_-]{0,63}')
ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
REL = re.compile(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*')
HEX = re.compile(r'#[0-9a-fA-F]{6}')
HASH = re.compile(r'[0-9a-f]{64}')
VERDICTS = ('SOLID', 'PLAYABLE', 'ROUGH', 'BROKEN')
MODULES = ('story', 'combat', 'region', 'course')
PROOF_STATUS = {'proved': 'proved', 'rejected': 'rejected', 'invalid': 'rejected', 'inconclusive': 'inconclusive'}
PNG_SIG = b'\x89PNG\r\n\x1a\n'
_CLOEXEC = getattr(os, 'O_CLOEXEC', 0)
# The no-follow directory descriptors below are POSIX. Where they do not exist (Windows) the module still imports,
# so the plugin and its backend load, and Root refuses with one sentence instead of reading without the guarantee.
POSIX_DESCRIPTORS = (all(hasattr(os, f) for f in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
                     and os.open in os.supports_dir_fd)
_DIR = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | _CLOEXEC) if POSIX_DESCRIPTORS else None
_FILE = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | _CLOEXEC) if POSIX_DESCRIPTORS else None
PLATFORM_SENTENCE = ("The Studio shelf can't read projects on this computer yet: it needs macOS (or Linux) no-follow "
                     "folder reads, and no Settings change fixes that. Ask Hermes to run hermes64_doctor for what works "
                     "here; the web play builds run in any browser.")
# Without descriptors (Windows) Root reads by checked path instead: every component is lstat'ed and refused when it is
# a symlink or any reparse point (junctions included), and an opened file must be the same file (st_dev, st_ino) the
# check saw, so a swap between check and open is refused. Weaker than descriptor confinement against a concurrent
# local attacker; equal for the read-only shelf's purpose (no link is ever followed). docs/WINDOWS.md.
_REPARSE = 0x400          # FILE_ATTRIBUTE_REPARSE_POINT
_PATH_FILE = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOINHERIT', 0)


def _kind(st):
    if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & _REPARSE:
        return 'symlink'
    return 'dir' if stat.S_ISDIR(st.st_mode) else 'file' if stat.S_ISREG(st.st_mode) else 'other'


class ScanError(Exception):
    def __init__(self, code, detail):
        super().__init__(code + ': ' + detail)
        self.code = code
        self.detail = detail


def _parts(rel):
    if not isinstance(rel, str) or len(rel) > 240 or REL.fullmatch(rel) is None:
        raise ScanError('PATH', 'not a confined relative path')
    parts = rel.split('/')
    if any(p in ('.', '..') for p in parts):
        raise ScanError('PATH', 'dot path component')
    return parts


def _oserror(exc, rel):
    if exc.errno in (errno.ELOOP, errno.EMLINK):
        return ScanError('SYMLINK', 'symlink refused: ' + rel)
    if exc.errno in (errno.ENOENT,):
        return ScanError('MISSING', rel)
    if exc.errno in (errno.ENOTDIR,):
        return ScanError('NOT_DIR', rel)
    if exc.errno in (errno.EACCES, errno.EPERM):
        return ScanError('DENIED', rel)
    return ScanError('IO', rel + ' (' + errno.errorcode.get(exc.errno, 'error') + ')')


class Root:
    """An open projects_root; all access goes through descriptors."""

    def __init__(self, path):
        if not isinstance(path, str) or not path or not os.path.isabs(path):
            raise ScanError('CONFIG', 'projects_root must be an absolute path')
        if '..' in path.split(os.sep):
            raise ScanError('CONFIG', 'projects_root must not contain ..')
        self.fd = None
        self.paths = not POSIX_DESCRIPTORS
        try:
            st = os.lstat(path)
        except OSError:
            raise ScanError('CONFIG', 'projects_root does not exist')
        if _kind(st) == 'symlink':
            raise ScanError('CONFIG', 'projects_root must not be a symlink')
        if not stat.S_ISDIR(st.st_mode):
            raise ScanError('CONFIG', 'projects_root must be a directory')
        if self.paths:
            self.path = path
            return
        try:
            self.fd = os.open(path, _DIR)
        except OSError as exc:
            raise ScanError('CONFIG', 'projects_root cannot be opened: ' + _oserror(exc, '.').code)
        self.path = path

    def close(self):
        if self.paths:
            self.path = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _walk(self, parts, rel):
        """Path mode: the checked absolute path of parts (each existing component lstat'ed, links refused)."""
        if self.path is None:
            raise ScanError('CLOSED', 'projects_root is closed')
        here = self.path
        for i, part in enumerate(parts):
            here = os.path.join(here, part)
            try:
                st = os.lstat(here)
            except FileNotFoundError:
                raise ScanError('MISSING', rel)
            except OSError as exc:
                raise _oserror(exc, rel)
            kind = _kind(st)
            if kind == 'symlink':
                raise ScanError('SYMLINK', 'symlink refused: ' + rel)
            if i < len(parts) - 1 and kind != 'dir':
                raise ScanError('NOT_DIR', rel)
        return here

    def _open_checked(self, parts, rel):
        full = self._walk(parts, rel)
        before = os.lstat(full)
        if _kind(before) != 'file':
            raise ScanError('NOT_FILE', 'not a regular file: ' + rel)
        try:
            fd = os.open(full, _PATH_FILE)
        except OSError as exc:
            raise _oserror(exc, rel)
        after = os.fstat(fd)
        if (before.st_ino, before.st_dev) != (after.st_ino, after.st_dev):
            os.close(fd)
            raise ScanError('SYMLINK', 'file changed between check and open: ' + rel)
        return fd

    def _dir(self, parts, rel):
        if self.fd is None:
            raise ScanError('CLOSED', 'projects_root is closed')
        fd = os.dup(self.fd)
        try:
            for part in parts:
                nfd = os.open(part, _DIR, dir_fd=fd)
                os.close(fd)
                fd = nfd
            return fd
        except OSError as exc:
            os.close(fd)
            raise _oserror(exc, rel)

    def entry(self, rel):
        """('dir'|'file'|'symlink'|'other', size, mtime_ns), or None when missing."""
        parts = _parts(rel)
        if self.paths:
            try:
                folder = self._walk(parts[:-1], rel)
            except ScanError as exc:
                if exc.code in ('MISSING', 'NOT_DIR'):
                    return None
                raise
            try:
                st = os.lstat(os.path.join(folder, parts[-1]))
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise _oserror(exc, rel)
            return _kind(st), st.st_size, st.st_mtime_ns
        try:
            dfd = self._dir(parts[:-1], rel)
        except ScanError as exc:
            if exc.code in ('MISSING', 'NOT_DIR'):
                return None
            raise
        try:
            st = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise _oserror(exc, rel)
        finally:
            os.close(dfd)
        mode = st.st_mode
        kind = 'symlink' if stat.S_ISLNK(mode) else 'dir' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'other'
        return kind, st.st_size, st.st_mtime_ns

    def listdir(self, rel=''):
        """Sorted (name, kind, size, mtime_ns) rows, at most LIMITS['dir_entries'], plus truncation flag."""
        parts = _parts(rel) if rel else []
        if self.paths:
            folder = self._walk(parts, rel or '.')
            if parts and _kind(os.lstat(folder)) != 'dir':
                raise ScanError('NOT_DIR', rel)
            names = sorted(os.listdir(folder))
            rows = []
            for name in names[:LIMITS['dir_entries']]:
                try:
                    st = os.lstat(os.path.join(folder, name))
                except OSError:
                    continue
                rows.append((name, _kind(st), st.st_size, st.st_mtime_ns))
            return rows, len(names) > LIMITS['dir_entries']
        fd = self._dir(parts, rel or '.')
        rows = []
        try:
            names = sorted(os.listdir(fd))
            truncated = len(names) > LIMITS['dir_entries']
            for name in names[:LIMITS['dir_entries']]:
                try:
                    st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except OSError:
                    continue
                mode = st.st_mode
                kind = 'symlink' if stat.S_ISLNK(mode) else 'dir' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'other'
                rows.append((name, kind, st.st_size, st.st_mtime_ns))
        finally:
            os.close(fd)
        return rows, truncated

    def open_regular(self, rel, limit):
        """(fd, size) of a confined regular file for streaming; the caller closes fd."""
        parts = _parts(rel)
        if self.paths:
            fd = self._open_checked(parts, rel)
        else:
            dfd = self._dir(parts[:-1], rel)
            try:
                fd = os.open(parts[-1], _FILE, dir_fd=dfd)
            except OSError as exc:
                raise _oserror(exc, rel)
            finally:
                os.close(dfd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            os.close(fd)
            raise ScanError('NOT_FILE' if not stat.S_ISREG(st.st_mode) else 'LIMIT', rel)
        return fd, st.st_size

    def read(self, rel, limit):
        parts = _parts(rel)
        if self.paths:
            fd = self._open_checked(parts, rel)
        else:
            dfd = self._dir(parts[:-1], rel)
            try:
                fd = os.open(parts[-1], _FILE, dir_fd=dfd)
            except OSError as exc:
                raise _oserror(exc, rel)
            finally:
                os.close(dfd)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ScanError('NOT_FILE', 'not a regular file: ' + rel)
            if st.st_size > limit:
                raise ScanError('LIMIT', 'file exceeds ' + str(limit) + ' bytes: ' + rel)
            chunks, total = [], 0
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    raise ScanError('LIMIT', 'file grew past ' + str(limit) + ' bytes: ' + rel)
            return b''.join(chunks)
        finally:
            os.close(fd)


def parse_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ScanError('JSON', 'duplicate key')
            out[key] = value
        return out

    def nonfinite(_):
        raise ScanError('JSON', 'non-finite number')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except ScanError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ScanError('JSON', 'invalid JSON')


def png_info(raw):
    """Width and height from a PNG header; refuses anything that is not a PNG."""
    if len(raw) < 33 or raw[:8] != PNG_SIG or raw[12:16] != b'IHDR' or struct.unpack('>I', raw[8:12])[0] != 13:
        raise ScanError('PNG', 'not a PNG image')
    w, h = struct.unpack('>II', raw[16:24])
    if not (1 <= w <= LIMITS['png_side'] and 1 <= h <= LIMITS['png_side']):
        raise ScanError('PNG', 'PNG dimensions out of range')
    return w, h


def display_label(value):
    """Style labels for the Studio UI: the third-party 'N64' mark is never shown as a name."""
    return re.sub(r'\bN64\b', 'Classic', value, flags=re.I)


def _text(value, limit):
    if not isinstance(value, str):
        return ''
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '\u2026'


def _hexes(values):
    return [v.lower() for v in values if isinstance(v, str) and HEX.fullmatch(v)]


def _luma(c):
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _chroma(c):
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    hi, lo = max(r, g, b), min(r, g, b)
    light = (hi + lo) / 510.0
    return (hi - lo) / 255.0 * (1 - abs(2 * light - 1))


def summarise_palette(colours):
    """Pip colour plus up to 6 representative colours, darkest to lightest."""
    seen, uniq = {}, []
    for c in _hexes(colours)[:64]:
        if c not in seen:
            seen[c] = True
            uniq.append(c)
    if not uniq:
        return '#8a8fb8', []
    pip = sorted(uniq[:16], key=lambda c: (-round(_chroma(c), 3), c))[0]
    ordered = sorted(uniq, key=lambda c: (_luma(c), c))
    if len(ordered) <= 6:
        picks = ordered
    else:
        picks = [ordered[round(i * (len(ordered) - 1) / 5)] for i in range(6)]
    if pip not in picks:
        picks = sorted(picks[:5] + [pip], key=lambda c: (_luma(c), c))
    return pip, picks


def procedural_recipe(game_id, palette):
    """A deterministic original cover for games without a capture (rendered by covers.js)."""
    pal = palette or ['#1d2a5c', '#3d4a86', '#5a6fb8', '#8e9ff5', '#f2b98a', '#fff1c4']
    dark, light = pal[0], pal[-1]
    mid = pal[len(pal) // 2]
    low = pal[max(0, len(pal) // 2 - 1)]
    seed = int(hashlib.sha256(game_id.encode('utf-8')).hexdigest()[:8], 16)
    landmarks = ('dome', 'clocktower', 'observatory', 'harbor', 'greenhouse', 'station', 'windtower')
    layers = ('hills', 'mountains', 'pines')
    return {
        'seed': game_id,
        'sky': [dark, light],
        'fog': light,
        'horizon': 0.6,
        'sun': {'x': 0.25 + (seed % 50) / 100.0, 'y': 0.36, 'r': 8, 'colour': '#fff1c4', 'glow': light},
        'layers': [{'kind': layers[seed % len(layers)], 'colour': low, 'base': 0.62, 'height': 0.2}],
        'ground': mid,
        'groundTop': 0.72,
        'landmark': {'kind': landmarks[(seed >> 4) % len(landmarks)], 'x': 0.5, 'scale': 1.0, 'colour': light, 'light': '#ffd27a', 'base': 0.74},
    }


class _Project:
    def __init__(self, root, name, known_styles):
        self.root = root
        self.name = name
        self.known = known_styles or {}
        self.issues = []
        self.styles = []

    def issue(self, code, detail, path=None):
        if len(self.issues) < 16:
            row = {'code': code, 'detail': _text(detail, 200)}
            if path and REL.fullmatch(path) and len(path) <= 240:
                row['path'] = path
            self.issues.append(row)

    def rel(self, path):
        return self.name + '/' + path

    def json(self, path, missing_ok=True):
        try:
            return parse_json(self.root.read(self.rel(path), LIMITS['json_bytes']))
        except ScanError as exc:
            if exc.code == 'MISSING' and missing_ok:
                return None
            self.issue(exc.code, exc.detail.replace(self.name + '/', '', 1), path)
            return None

    def runs(self):
        try:
            rows, truncated = self.root.listdir(self.rel('.maker/runs'))
        except ScanError as exc:
            if exc.code != 'MISSING':
                self.issue(exc.code, 'runs folder unreadable', '.maker/runs')
            return []
        if truncated:
            self.issue('LIMIT', 'more runs than the listing limit; oldest names skipped', '.maker/runs')
        out = []
        for name, kind, _size, mtime in rows:
            if kind == 'symlink':
                self.issue('SYMLINK', 'symlinked run folder skipped', '.maker/runs/' + name if REL.fullmatch(name) else None)
            elif kind == 'dir' and REL.fullmatch(name):
                out.append((mtime, name))
        out.sort(key=lambda r: (-r[0], r[1]))  # newest first, ties by name
        return [n for _m, n in out]

    def style_from_pack(self, pack_id):
        known = self.known.get(pack_id)
        pack = self.json('packs/' + pack_id + '/pack.json') if ID.fullmatch(pack_id) else None
        if isinstance(pack, dict) and pack.get('id') == pack_id:
            pip, pal = summarise_palette(pack.get('palette') if isinstance(pack.get('palette'), list) else [])
            ref = {'id': pack_id, 'label': display_label(_text(pack.get('name'), 40) or pack_id), 'colour': pip, 'palette': pal, 'source': 'pack'}
        elif isinstance(known, dict):
            ref = {'id': pack_id, 'label': display_label(_text(known.get('label'), 40) or pack_id), 'colour': known.get('colour') if HEX.fullmatch(str(known.get('colour'))) else '#8a8fb8',
                   'palette': _hexes(known.get('palette') or [])[:8], 'source': 'pack'}
        else:
            ref = {'id': pack_id, 'label': display_label(pack_id.replace('_', ' ').title()[:40]), 'colour': '#8a8fb8', 'palette': [], 'source': 'unknown'}
        return ref

    def style_from_profile(self, manifest):
        style = manifest.get('style') if isinstance(manifest.get('style'), dict) else {}
        sid = style.get('id') if isinstance(style.get('id'), str) and ID.fullmatch(style.get('id')) else None
        if sid is None:
            return None, None
        colours = {}
        prof_path = style.get('profile')
        if isinstance(prof_path, str):
            try:
                _parts(prof_path)
                prof = self.json(prof_path)
            except ScanError as exc:
                self.issue(exc.code, 'style profile path refused', None)
                prof = None
            if isinstance(prof, dict):
                pal = ((prof.get('sections') or {}).get('palette') or {}) if isinstance(prof.get('sections'), dict) else {}
                colours = pal.get('colors') if isinstance(pal, dict) and isinstance(pal.get('colors'), dict) else {}
        values = [v for _k, v in sorted(colours.items())]
        pip = colours.get('accent') if isinstance(colours.get('accent'), str) and HEX.fullmatch(colours.get('accent')) else None
        default_pip, pal = summarise_palette(values)
        ref = {'id': sid, 'label': display_label(sid.replace('_', ' ').title()[:40]), 'colour': (pip or default_pip).lower(), 'palette': pal, 'source': 'profile'}
        lock_path = style.get('lock')
        lock = None
        if isinstance(lock_path, str):
            try:
                _parts(lock_path)
                lock = self.json(lock_path)
            except ScanError:
                lock = None
        approved = isinstance(lock, dict) and lock.get('approval') not in (None, False, '')
        status = 'approved' if approved else 'data_valid_runtime_pending'
        return ref, status


def _verification_default():
    return {'proof': {'status': 'not_run'}, 'replay': {'status': 'not_run'},
            'playtest': {'verdict': 'UNTESTED', 'status': 'none'},
            'style_gate': {'status': 'not_run'}, 'human': {'status': 'not_yet'}}


def _report_hash(doc):
    for key in ('game_hash', 'game_sha256'):
        value = doc.get(key)
        if isinstance(value, str) and HASH.fullmatch(value):
            return value
    return None


def scan_project(root, name, known_styles=None):
    """One game row for projects_root/<name>, plus its styles; raises ScanError if not a project."""
    p = _Project(root, name, known_styles)
    marker = p.json('.maker/project.json')
    manifest = p.json('project.json')
    managed = marker == {'format': 1, 'name': name}
    if marker is not None and not managed:
        p.issue('MARKER', 'managed project marker does not match this folder', '.maker/project.json')
    modelled = isinstance(manifest, dict) and manifest.get('schema_version') == '1.0.0' and isinstance(manifest.get('content'), dict)
    if not managed and not modelled:
        raise ScanError('NOT_A_PROJECT', 'no managed marker or project.json')
    game = {'id': name, 'title': name, 'sample': False, 'owner': 'local', 'modules': [],
            'verification': _verification_default(), 'exports': []}
    game['project'] = {'kind': 'managed+project_model' if managed and modelled else 'managed' if managed else 'project_model', 'path': name}
    style = None
    style_status = None
    doc = None
    game_hash = None
    if managed:
        cur = p.json('.maker/current.json')
        if cur is not None and not (isinstance(cur, dict) and set(cur) == {'spec', 'game'} and all(isinstance(v, str) for v in cur.values())):
            p.issue('CURRENT', 'invalid current revision pointer', '.maker/current.json')
            cur = None
        if cur is not None:
            try:
                _parts(cur['game'])
                doc = p.json(cur['game'], missing_ok=False)
            except ScanError:
                p.issue('PATH', 'current pointer is not a confined path', '.maker/current.json')
                doc = None
            if isinstance(doc, dict) and isinstance(doc.get('game_hash'), str) and HASH.fullmatch(doc['game_hash']) and isinstance(doc.get('rooms'), list):
                game_hash = doc['game_hash']
                game['project']['current'] = 'verified_pointer'
            else:
                if doc is not None:
                    p.issue('GAME', 'compiled game lacks game_hash/rooms', cur['game'])
                doc = None
        if doc is None:
            doc = p.json('source/spec.json')
            game['project']['current'] = 'starter_only' if isinstance(doc, dict) else 'missing'
    if modelled and doc is None:
        story_path = manifest['content'].get('story')
        if isinstance(story_path, str):
            try:
                _parts(story_path)
                doc = p.json(story_path)
            except ScanError:
                p.issue('PATH', 'story path refused', 'project.json')
        game['project'].setdefault('current', 'project_model')
    if not isinstance(doc, dict):
        doc = {}
    title = _text(doc.get('title'), 60) or (_text(manifest.get('name'), 60) if modelled else '') or name
    game['title'] = title
    premise = _text(doc.get('description'), 280)
    if premise:
        game['premise'] = premise
    if isinstance(doc.get('rooms'), list):
        game['rooms'] = min(len(doc['rooms']), 999)
    if isinstance(doc.get('endings'), list):
        game['endings'] = min(len(doc['endings']), 99)
    meta = doc.get('metadata') if isinstance(doc.get('metadata'), dict) else {}
    mods = ['story'] if game.get('rooms') else []
    if isinstance(meta.get('modules'), list):
        mods += [m for m in meta['modules'] if m in MODULES]
    game['modules'] = [m for m in MODULES if m in mods]
    pack_id = None
    hp = meta.get('hermes64_pack')
    if isinstance(hp, dict) and isinstance(hp.get('id'), str):
        pack_id = hp['id']
    elif isinstance(meta.get('style_pack'), str):
        pack_id = meta['style_pack']
    if pack_id and ID.fullmatch(pack_id):
        style = p.style_from_pack(pack_id)
        style_status = 'in_use'
    if style is None and modelled:
        style, style_status = p.style_from_profile(manifest)
    if style is None:
        style = {'id': 'unknown', 'label': 'No style yet', 'colour': '#8a8fb8', 'palette': [], 'source': 'unknown'}
    game['style'] = style
    if style['source'] != 'unknown':
        row = {'id': style['id'], 'label': style['label'], 'colour': style['colour'], 'palette': style['palette'],
               'status': style_status, 'kind': 'pack' if style['source'] == 'pack' else 'profile'}
        p.styles.append(row)

    v = game['verification']
    runs = p.runs() if managed else []
    cover_frames = []
    if game_hash:
        # Story proof: checker reports are deterministic per game_hash; a matching proof decides.
        proofs, reads = [], 0
        for run in runs:
            if not run.startswith(('check-', 'replay-', 'edit-')) or reads >= LIMITS['proof_reads']:
                continue
            reads += 1
            rp = p.json('.maker/runs/' + run + '/proof.json')
            if isinstance(rp, dict) and rp.get('status') in PROOF_STATUS and _report_hash(rp):
                proofs.append((_report_hash(rp) == game_hash, PROOF_STATUS[rp['status']], '.maker/runs/' + run + '/proof.json'))
        current = [x for x in proofs if x[0]]
        if current:
            best = next((x for x in current if x[1] == 'proved'), current[0])
            v['proof'] = {'status': best[1], 'report': best[2]}
        elif proofs:
            v['proof'] = {'status': 'stale'}
        # Godot replay of the proof witnesses.
        reads = 0
        replays = []
        for run in runs:
            if not run.startswith('replay-') or reads >= LIMITS['report_reads']:
                continue
            reads += 1
            rr = p.json('.maker/runs/' + run + '/replay.json')
            if isinstance(rr, dict) and rr.get('status') in ('passed', 'failed'):
                replays.append((_report_hash(rr) == game_hash, rr['status'], '.maker/runs/' + run + '/replay.json'))
        current = [x for x in replays if x[0]]
        if current:
            v['replay'] = {'status': current[0][1], 'report': current[0][2]}
        elif replays:
            v['replay'] = {'status': 'stale'}
        # Bot playtest (SHIP lane layout): verdict counts only when tied to this build.
        reads = 0
        plays = []
        for run in runs:
            if not run.startswith('playtest-') or reads >= LIMITS['report_reads']:
                continue
            reads += 1
            pr = p.json('.maker/runs/' + run + '/report.json')
            if isinstance(pr, dict) and pr.get('verdict') in VERDICTS:
                plays.append((_report_hash(pr) == game_hash, pr, run))
        chosen = next((x for x in plays if x[0]), plays[0] if plays else None)
        if chosen:
            ok, pr, run = chosen
            reasons = [_text(r, 120) for r in (pr.get('reasons') if isinstance(pr.get('reasons'), list) else []) if isinstance(r, str)][:3]
            v['playtest'] = {'verdict': pr['verdict'], 'status': 'current' if ok else 'stale', 'by': 'bot',
                             'reasons': [r for r in reasons if r], 'report': '.maker/runs/' + run + '/report.json'}
            if ok:
                cover_frames = _frames(p, '.maker/runs/' + run)
        # Style gate: asset build report for this build.
        reads = 0
        for run in runs:
            if not run.startswith('assets-') or reads >= LIMITS['report_reads']:
                continue
            reads += 1
            ar = p.json('.maker/runs/' + run + '/assets/report.json')
            if isinstance(ar, dict) and _report_hash(ar) == game_hash:
                sv = ar.get('style_validation') if isinstance(ar.get('style_validation'), dict) else {}
                if sv.get('status') in ('passed', 'failed'):
                    v['style_gate'] = {'status': sv['status'], 'applies_to': 'latest_capture', 'report': '.maker/runs/' + run + '/assets/report.json'}
                break
        # Human playtest: only an explicit local marker for this exact build.
        hm = p.json('.maker/studio/human-playtest.json')
        if isinstance(hm, dict) and hm.get('status') == 'played' and hm.get('game_hash') == game_hash:
            v['human'] = {'status': 'played'}
    if managed:
        game['exports'] = _exports(p, runs)
    game['cover'], shots = _cover(p, cover_frames, name, style, manifest if modelled else None)
    if shots:
        game['shots'] = shots
    if p.issues:
        game['issues'] = p.issues
    return game, p.styles


def _frames(p, folder):
    try:
        rows, _t = p.root.listdir(p.rel(folder))
    except ScanError:
        return []
    names = [n for n, kind, size, _m in rows if kind == 'file' and n.endswith('.png') and n != 'contact-sheet.png' and 0 < size <= LIMITS['png_bytes'] and REL.fullmatch(n)]
    return [folder + '/' + n for n in names[:4]]


def _image(p, path):
    try:
        raw = p.root.read(p.rel(path), LIMITS['png_bytes'])
        w, h = png_info(raw)
    except ScanError as exc:
        if exc.code != 'MISSING':
            p.issue(exc.code, 'cover image refused', path)
        return None
    return {'path': path, 'width': w, 'height': h, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _box_art(p, manifest):
    """The cover tool's adopted, finished box art (logotype, band and corner mark already drawn), or None.

    Portable projects record it in project.json `cover.box` (adventure_maker/project_cover.py); managed games in
    .maker/cover/current.json `exports["box-2x"].path`. Read as raw JSON (the scanner never validates project.json
    against the closed 1.0.0 contract), then through the same confined PNG reader as every other cover."""
    block = manifest.get('cover') if isinstance(manifest, dict) else None
    rel = title = None
    if isinstance(block, dict) and isinstance(block.get('box'), str):
        rel, title = block['box'], block.get('title_position')
    else:
        current = p.json('.maker/cover/current.json')
        exports = current.get('exports') if isinstance(current, dict) else None
        box = exports.get('box-2x') if isinstance(exports, dict) else None
        if isinstance(box, dict) and isinstance(box.get('path'), str):
            rel, title = box['path'], current.get('title_position')
    if rel is None:
        return None
    if not REL.fullmatch(rel) or '..' in rel.split('/') or len(rel) > 200:
        p.issue('PATH', 'cover box path refused', rel[:80])
        return None
    chosen = _image(p, rel)
    if chosen:
        chosen['kind'] = 'box'
        if title in ('top', 'bottom'):
            chosen['title'] = title
    return chosen


def _cover(p, frames, name, style, manifest=None):
    boxed = _box_art(p, manifest)
    if boxed:
        return boxed, []
    chosen = _image(p, '.maker/studio/cover.png')
    if chosen:
        chosen['kind'] = 'file'
        return chosen, []
    images = [x for x in (_image(p, f) for f in frames) if x]
    if images:
        first = dict(images[0], kind='capture')
        stem = images[0]['path'].rsplit('/', 1)[-1][:-4]
        if ID.fullmatch(stem):
            first['room'] = stem
        shots = []
        for img in images[1:4]:
            row = {'path': img['path'], 'sha256': img['sha256']}
            s = img['path'].rsplit('/', 1)[-1][:-4]
            if ID.fullmatch(s):
                row['room'] = s
            shots.append(row)
        return first, shots
    return {'kind': 'procedural', 'recipe': procedural_recipe(name, style.get('palette'))}, []


def _exports(p, runs):
    reads = 0
    for run in runs:
        if not run.startswith('export-') or reads >= LIMITS['export_reads']:
            continue
        reads += 1
        base = '.maker/runs/' + run + '/share'
        found = []
        web = p.root.entry(p.rel(base + '/web/index.html'))
        if web and web[0] == 'file':
            found.append({'target': 'web', 'path': base + '/web', 'entry': 'index.html'})
        for target, test in (('macos', lambda n, k: k == 'dir' and n.endswith('.app')), ('windows', lambda n, k: k == 'file' and n.endswith('.exe'))):
            try:
                rows, _t = p.root.listdir(p.rel(base + '/' + target))
            except ScanError:
                continue
            hits = [n for n, kind, _s, _m in rows if test(n, kind) and REL.fullmatch(n)]
            if hits:
                found.append({'target': target, 'path': base + '/' + target, 'entry': hits[0]})
        if not found:
            continue
        for row in found:
            files = p.json(row['path'] + '/FILES.json')
            if isinstance(files, list) and len(files) <= LIMITS['files_rows'] and all(isinstance(r, dict) and type(r.get('bytes')) is int and r['bytes'] >= 0 for r in files):
                row['bytes'] = sum(r['bytes'] for r in files)
            row['verified'] = False  # the export lane's smoke results are not yet a stable format on main
        return found
    return []


def _style_rows(p_styles):
    out = {}
    for row in p_styles:
        prev = out.get(row['id'])
        if prev is None or (prev['status'] != 'in_use' and row['status'] == 'in_use'):
            out[row['id']] = row
    return [out[k] for k in sorted(out)]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def scan(projects_root, known_styles=None):
    """The whole catalogue for one projects_root (dict, schema hermes64.studio.catalogue/1)."""
    games, styles, skipped = [], [], []
    truncated = False
    with Root(projects_root) as root:
        rows, over = root.listdir('')
        if over or len(rows) > LIMITS['projects']:
            truncated = True
        for name, kind, _size, _m in rows[:LIMITS['projects']]:
            if name.startswith('.'):
                continue
            label = name if len(name) <= 80 else name[:79] + '\u2026'
            if kind == 'symlink':
                skipped.append({'entry': label, 'code': 'SYMLINK'})
                continue
            if kind != 'dir':
                continue
            if SLUG.fullmatch(name) is None:
                skipped.append({'entry': label, 'code': 'NAME', 'detail': 'project folders are lowercase slugs'})
                continue
            try:
                game, found = scan_project(root, name, known_styles)
            except ScanError as exc:
                skipped.append({'entry': label, 'code': exc.code if re.fullmatch(r'[A-Z][A-Z0-9_]{1,39}', exc.code) else 'ERROR', 'detail': _text(exc.detail, 200)})
                continue
            games.append(game)
            styles.extend(found)
    cat = {'schema': SCHEMA_ID, 'source': 'projects_root', 'generator': dict(GENERATOR),
           'games': games, 'styles': _style_rows(styles), 'skipped': skipped,
           'limits': {k: v for k, v in sorted(LIMITS.items())}, 'truncated': truncated}
    cat['digest'] = hashlib.sha256(canonical(cat)).hexdigest()
    return cat


def find_image(projects_root, game_id, index, tag=None, known_styles=None):
    """Bytes of a game's cover (index 0) or shot (1..3), re-derived from disk, never from a client path."""
    if not isinstance(game_id, str) or SLUG.fullmatch(game_id) is None or type(index) is not int or not 0 <= index <= 3:
        raise ScanError('ARGUMENT', 'bad image request')
    with Root(projects_root) as root:
        if (root.entry(game_id) or ('',))[0] != 'dir':
            raise ScanError('MISSING', 'no such project')
        game, _styles = scan_project(root, game_id, known_styles)
        rows = [game['cover']] + game.get('shots', [])
        if index >= len(rows) or 'path' not in rows[index]:
            raise ScanError('MISSING', 'no such image')
        row = rows[index]
        if tag is not None and not row['sha256'].startswith(tag):
            raise ScanError('STALE', 'image changed since the catalogue was built')
        raw = root.read(game_id + '/' + row['path'], LIMITS['png_bytes'])
        png_info(raw)
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ScanError('STALE', 'image changed while reading')
        return raw


def project_dir(projects_root, game_id):
    """Absolute folder of one project, for an explicit user 'Open folder' action only."""
    if not isinstance(game_id, str) or SLUG.fullmatch(game_id) is None:
        raise ScanError('ARGUMENT', 'bad project id')
    with Root(projects_root) as root:
        if (root.entry(game_id) or ('',))[0] != 'dir':
            raise ScanError('MISSING', 'no such project')
        scan_project(root, game_id)
        return os.path.join(root.path, game_id)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    out = None
    if '--out' in args:
        i = args.index('--out')
        out = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if len(args) != 1 or (out is not None and not out):
        print('usage: python3 -B -m adventure_maker.studio_catalogue /absolute/projects_root [--out new-file.json]', file=sys.stderr)
        return 2
    try:
        cat = scan(args[0])
    except ScanError as exc:
        print(json.dumps({'ok': False, 'code': exc.code, 'detail': exc.detail}), file=sys.stderr)
        return 1
    text = json.dumps(cat, sort_keys=True, ensure_ascii=False, indent=1) + '\n'
    if out:
        try:
            with open(out, 'x', encoding='utf-8') as fh:  # exclusive create: never overwrites
                fh.write(text)
        except FileExistsError:
            print(json.dumps({'ok': False, 'code': 'EXISTS', 'detail': 'output file exists; nothing overwritten'}), file=sys.stderr)
            return 1
        print(json.dumps({'ok': True, 'games': len(cat['games']), 'styles': len(cat['styles']), 'skipped': len(cat['skipped']), 'digest': cat['digest'], 'out': out}))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
