"""Bounded data and project paths. No external storage or network."""
import contextlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile

JSON_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 24000
WINDOWS_RESERVED = frozenset(['con', 'prn', 'aux', 'nul'] + ['com%d' % i for i in range(1, 10)] +
                             ['lpt%d' % i for i in range(1, 10)])
_NAME_SURROGATE = 0x20000000      # reparse-tag bit of junctions and symlinks (not OneDrive/cloud placeholders)


class Fault(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def fail(code, message):
    raise Fault(code, message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('invalid_json', 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def bounded(value, depth=0, budget=None):
    if budget is None:
        budget = [50000]
    budget[0] -= 1
    if depth > 48 or budget[0] < 0:
        fail('limit', 'JSON depth/node limit exceeded')
    if isinstance(value, float) and not math.isfinite(value):
        fail('invalid_json', 'Nonfinite JSON number')
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                fail('invalid_json', 'Object keys must be strings')
            bounded(child, depth + 1, budget)
    elif isinstance(value, list):
        for child in value:
            bounded(child, depth + 1, budget)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        fail('invalid_json', 'Not a JSON value')
    return value


def encode(value):
    bounded(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError) as exc:
        fail('invalid_json', str(exc))
    if len(raw) > JSON_LIMIT:
        fail('limit', 'JSON byte limit exceeded')
    return raw


def strict_json(raw):
    if not isinstance(raw, (str, bytes)):
        fail('invalid_json', 'Expected JSON text')
    try:
        if len(raw.encode('utf-8') if isinstance(raw, str) else raw) > JSON_LIMIT:
            fail('limit', 'JSON byte limit exceeded')
        text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=lambda x: fail('invalid_json', 'Nonfinite JSON constant ' + x))
        return bounded(value)
    except (ValueError, UnicodeError, RecursionError) as exc:
        fail('invalid_json', 'Malformed JSON: ' + str(exc)[:300])


def relative(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        fail('path', 'Invalid relative path')
    if '\\' in value or '\x00' in value or ':' in value or any(ord(c) < 32 for c in value):
        fail('path', 'Invalid path characters')
    parts = value.split('/')
    if any(p in ('', '.', '..') for p in parts) or value.startswith('/'):
        fail('path', 'Absolute/traversal path rejected')
    # Same rule on every OS so a project made on a Mac opens on Windows: NTFS refuses <>"|?*, drops a trailing dot or
    # space (foo. == foo) and maps reserved device names (con, nul, aux.txt, com1...) to devices.
    for part in parts:
        if any(c in '<>"|?*' for c in part) or part[-1] in '. ' or \
                part.split('.')[0].rstrip(' ').lower() in WINDOWS_RESERVED:
            fail('path', 'Name not allowed on Windows: ' + part)
    return Path(*parts)


def inspect_path(path):
    """Reject symlinks at every existing ancestor, plus hardlinks/special files."""
    path = Path(path)
    for node in reversed((path,) + tuple(path.parents)):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            fail('path', 'symlink path rejected: ' + str(node))
        # Windows: a directory junction is a reparse point that lstat reports as a plain directory.
        if getattr(info, 'st_reparse_tag', 0) & _NAME_SURROGATE:
            fail('path', 'junction/reparse-point path rejected: ' + str(node))
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            fail('path', 'hardlink path rejected: ' + str(node))
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            fail('path', 'special-file path rejected: ' + str(node))
    return path


class Project:
    def __init__(self, projects_root, name, create=False):
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name):
            fail('path', 'Project name must be a single lowercase slug; not a path')
        relative(name)  # project ids, not just files inside them, must be NTFS-safe (con/nul/etc.)
        base = Path(projects_root)
        if not base.is_absolute() or '..' in base.parts:
            fail('configuration', 'projects_root must be an absolute path without traversal')
        inspect_path(base)
        if not base.is_dir():
            fail('configuration', 'projects_root must be an existing directory; no parent directories were created')
        self.root = inspect_path(base / name)
        if create:
            if self.root.exists() or self.root.is_symlink():
                fail('exists', 'Project already exists; scaffold never overwrites')
            try:  # REUSE: atomic, so of two creates racing for one name exactly one wins and the other gets 'exists'
                self.root.mkdir()
            except FileExistsError:
                fail('exists', 'Project already exists; scaffold never overwrites')
            self.write_json('.maker/project.json', {'format': 1, 'name': name})
        elif not self.root.is_dir() or not self.path('.maker/project.json').is_file():
            fail('project', 'Not a managed adventure project; scaffold first')
        elif self.read_json('.maker/project.json') != {'format': 1, 'name': name}:
            fail('project', 'Invalid managed project marker')

    def path(self, rel):
        return inspect_path(self.root / relative(rel))

    def audit(self):
        inspect_path(self.root)
        count = 0
        for parent, dirs, files in os.walk(self.root, followlinks=False):
            for name in dirs + files:
                count += 1
                if count > 10000:
                    fail('limit', 'Project file-count limit exceeded')
                inspect_path(Path(parent) / name)

    def read_json(self, rel):
        path = self.path(rel)
        with path.open('rb') as f:
            raw = f.read(JSON_LIMIT + 1)
        return strict_json(raw)

    def write_bytes(self, rel, data):
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        inspect_path(path)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix='.maker-', delete=False) as f:
                temp = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            inspect_path(path)
            os.replace(str(temp), str(path))
        finally:
            if temp is not None and temp.exists():
                temp.unlink()

    def write_json(self, rel, value):
        self.write_bytes(rel, encode(value))

    @contextlib.contextmanager
    def lock(self):
        lock = self.path('.maker/operation.lock')
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            fail('busy', 'Project busy: operation.lock exists; inspect interrupted work before removing it')
        try:
            os.close(fd)
            self.audit()
            yield
        finally:
            inspect_path(lock)
            lock.unlink()
