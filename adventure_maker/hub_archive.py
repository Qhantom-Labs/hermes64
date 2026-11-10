"""Hermes64 Hub archives: deterministic data-only ZIPs and the validator every install runs.

Build: stored (uncompressed) members, sorted names, fixed 1980-01-01 timestamps, 0644 regular
files and no extra fields or comments. This module writes the ZIP bytes itself, so the same
files give the same bytes and sha256 on every Python version.

Validate: refuses anything that is not plain data, by path, type, size, ZIP header and content,
before a single byte reaches a project. Allowed: json, glb, png, wav, ogg, md, txt. Refused:
scripts and programs, unknown types, nested archives, symlinks, executable bits, traversal,
hidden files, oversize members, zip bombs (ratio, total size, overlapping members, lying
headers), CRC errors, malformed media, GLBs over the triangle budget, and any member that
the archive's own HUB.json manifest does not list with the same sha256.
"""
import hashlib
import io
import re
import stat
import struct
import zipfile
import zlib

from .safety import Fault, fail, strict_json

CONTRACT = 'hermes64-hub-pack/1'
MANIFEST = 'HUB.json'
MIB = 1024 * 1024
LIMITS = {'archive': 64 * MIB, 'file': 16 * MIB, 'total': 128 * MIB, 'files': 512, 'ratio': 100,
          'path': 160, 'depth': 6, 'text': MIB}
TYPES = {'.json': 'json', '.glb': 'glb', '.png': 'png', '.wav': 'wav', '.ogg': 'ogg', '.md': 'text', '.txt': 'text'}
SCRIPTS = frozenset((
    '.gd', '.gdshader', '.gdns', '.tscn', '.tres', '.godot', '.py', '.pyc', '.pyo', '.js', '.mjs', '.cjs', '.ts',
    '.sh', '.bash', '.zsh', '.fish', '.command', '.bat', '.cmd', '.ps1', '.vbs', '.lua', '.rb', '.pl', '.php',
    '.exe', '.dll', '.so', '.dylib', '.bin', '.app', '.jar', '.class', '.wasm', '.html', '.htm', '.svg', '.xml',
    '.scpt', '.applescript', '.msi', '.deb', '.rpm', '.apk'))
NESTED = frozenset(('.zip', '.gz', '.tgz', '.tar', '.7z', '.rar', '.xz', '.bz2', '.zst', '.lz4', '.lzma', '.cab',
                    '.dmg', '.pkg', '.iso', '.whl', '.egg', '.pck'))
KIND_TYPES = {'style': {'json', 'text', 'png'}, 'kit': {'glb', 'png', 'json', 'text'},
              'character': {'glb', 'png', 'json', 'text'}, 'sound': {'wav', 'ogg', 'json', 'text'},
              'cover': {'png', 'json', 'text'}, 'game': {'json', 'text', 'png', 'glb', 'wav', 'ogg'}}
# Hard per-GLB triangle caps by entry kind (N64-era budgets: room shell 1500, character body+props).
TRI_CAPS = {'kit': 1500, 'character': 1000, 'game': 1500}
SEGMENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
WAV_CHUNKS = frozenset((b'fmt ', b'data', b'LIST', b'fact', b'cue ', b'smpl'))
DOS_DATE = (0 << 9) | (1 << 5) | 1      # 1980-01-01
REGULAR = 0o100644 << 16                 # unix regular file, rw-r--r--
ALLOWED_TEXT = 'json, glb, png, wav, ogg, md, txt'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def kind_of(path):
    """('json'|'glb'|...|None, extension) for an archive member name."""
    dot = path.rfind('.')
    ext = path[dot:].lower() if dot > path.rfind('/') else ''
    return TYPES.get(ext), ext


def check_path(path, label='pack'):
    """A portable relative member name: no traversal, absolute, drive, hidden or odd characters."""
    if not isinstance(path, str) or not path:
        fail('hub_path', 'Refused %s: an archive member has no name; rebuild it with /hermes64 hub pack.' % label)
    shown = repr(path[:80])
    if path.startswith('/') or '\\' in path or ':' in path or '\x00' in path:
        fail('hub_path', 'Refused %s: archive path %s is absolute or not portable; do not install it.' % (label, shown))
    parts = path.split('/')
    if any(p in ('', '.', '..') for p in parts):
        fail('hub_path', 'Refused %s: archive path %s escapes the pack folder; do not install it and tell the '
             'registry maintainers.' % (label, shown))
    if len(path) > LIMITS['path'] or len(parts) > LIMITS['depth']:
        fail('hub_path', 'Refused %s: archive path %s is too long or too deep; rebuild it with /hermes64 hub pack.'
             % (label, shown))
    for part in parts:
        if part.startswith('.'):
            fail('hub_path', 'Refused %s: hidden file %s is not allowed in a pack; rebuild it without it.' % (label, shown))
        if not SEGMENT.fullmatch(part):
            fail('hub_path', 'Refused %s: archive path %s uses characters outside A-Z a-z 0-9 . _ -; rename and '
                 'rebuild it.' % (label, shown))
    return path


def check_type(path, kind, label='pack'):
    found, ext = kind_of(path)
    if ext in NESTED:
        fail('hub_nested', 'Refused %s: it contains another archive (%s); packs may not nest archives. Ask the author '
             'for a flat data-only pack.' % (label, path))
    if ext in SCRIPTS:
        fail('hub_script', 'Refused %s: it contains a script or program (%s); packs may hold data only (%s). '
             'Ask the author for a data-only pack.' % (label, path, ALLOWED_TEXT))
    if found is None:
        fail('hub_type', 'Refused %s: %s is an unknown file type; packs may hold only %s.' % (label, path, ALLOWED_TEXT))
    if kind in KIND_TYPES and found not in KIND_TYPES[kind]:
        fail('hub_type', 'Refused %s: a %s pack may not contain %s files (%s).' % (label, kind, ext, path))
    return found


# ---------------------------------------------------------------- content checks (data only)
def check_text(data, path, label):
    if len(data) > LIMITS['text'] or b'\x00' in data:
        fail('hub_content', 'Refused %s: %s is not a small plain-text file.' % (label, path))
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        fail('hub_content', 'Refused %s: %s is not UTF-8 text.' % (label, path))
    if data.startswith(b'#!'):
        fail('hub_script', 'Refused %s: %s starts like a script (#!); packs may hold data only.' % (label, path))


def check_json(data, path, label):
    if data.startswith(b'\xef\xbb\xbf'):
        fail('hub_content', 'Refused %s: %s starts with a byte-order mark; save it as plain UTF-8 JSON.' % (label, path))
    try:
        return strict_json(data)
    except Fault as exc:
        fail('hub_content', 'Refused %s: %s is not valid strict JSON (%s).' % (label, path, str(exc)[:120]))


def check_png(data, path, label):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        fail('hub_content', 'Refused %s: %s is not a PNG image.' % (label, path))
    pos, first, count, size = 8, True, 0, None
    while True:
        if pos + 12 > len(data):
            fail('hub_content', 'Refused %s: %s is a truncated PNG.' % (label, path))
        length, tag = struct.unpack_from('>I4s', data, pos)
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length or pos + 12 + length > len(data) or not tag.isalpha():
            fail('hub_content', 'Refused %s: %s has a malformed PNG chunk.' % (label, path))
        (crc,) = struct.unpack_from('>I', data, pos + 8 + length)
        if zlib.crc32(tag + body) & 0xFFFFFFFF != crc:
            fail('hub_content', 'Refused %s: %s has a PNG checksum error.' % (label, path))
        if first:
            if tag != b'IHDR' or length != 13:
                fail('hub_content', 'Refused %s: %s does not start with a PNG header.' % (label, path))
            width, height, depth, colour, method, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not (0 < width <= 4096 and 0 < height <= 4096 and depth in (1, 2, 4, 8, 16) and
                    colour in (0, 2, 3, 4, 6) and method == 0 and filtering == 0 and interlace in (0, 1)):
                fail('hub_content', 'Refused %s: %s has an unsupported PNG header (max 4096x4096).' % (label, path))
            size = (width, height)
            first = False
        pos += 12 + length
        count += 1
        if tag == b'IEND':
            break
        if count > 4096:
            fail('hub_content', 'Refused %s: %s has too many PNG chunks.' % (label, path))
    if pos != len(data):
        fail('hub_content', 'Refused %s: %s has hidden data after the image end.' % (label, path))
    return size


def check_wav(data, path, label):
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        fail('hub_content', 'Refused %s: %s is not a WAV file.' % (label, path))
    if struct.unpack_from('<I', data, 4)[0] != len(data) - 8:
        fail('hub_content', 'Refused %s: %s has a WAV size that does not match the file.' % (label, path))
    pos, fmt, frames = 12, None, None
    while pos < len(data):
        if pos + 8 > len(data):
            fail('hub_content', 'Refused %s: %s is a truncated WAV.' % (label, path))
        tag, length = struct.unpack_from('<4sI', data, pos)
        if tag not in WAV_CHUNKS:
            fail('hub_content', 'Refused %s: %s carries an unknown WAV chunk %r.' % (label, path, tag))
        if pos + 8 + length > len(data):
            fail('hub_content', 'Refused %s: %s has a WAV chunk past the end of the file.' % (label, path))
        if tag == b'fmt ' and length >= 16:
            fmt = struct.unpack_from('<HHIIHH', data, pos + 8)
        elif tag == b'data':
            frames = length
        pos += 8 + length + (length & 1)
    if fmt is None or frames is None:
        fail('hub_content', 'Refused %s: %s lacks WAV format or audio data.' % (label, path))
    audio, channels, rate, _byte_rate, _align, bits = fmt
    if audio not in (1, 3, 0xFFFE) or channels not in (1, 2) or not 8000 <= rate <= 96000 or bits not in (8, 16, 24, 32):
        fail('hub_content', 'Refused %s: %s is not a plain PCM WAV (mono/stereo, 8-96 kHz).' % (label, path))
    seconds = frames / float(rate * channels * bits // 8)
    if seconds > 600:
        fail('hub_content', 'Refused %s: %s is longer than 10 minutes.' % (label, path))
    return round(seconds, 3)


def check_ogg(data, path, label):
    if len(data) < 27 or data[:4] != b'OggS' or data[4] != 0 or not data[5] & 0x02:
        fail('hub_content', 'Refused %s: %s is not an Ogg audio stream.' % (label, path))


def glb_triangles(doc):
    total = 0
    accessors = doc.get('accessors', [])
    for mesh in doc.get('meshes', []):
        for prim in mesh.get('primitives', []):
            index = prim['indices'] if 'indices' in prim else prim.get('attributes', {}).get('POSITION')
            total += accessors[index]['count'] // 3
    return total


def check_glb(data, path, label, cap=None):
    from . import glb_validate
    report = glb_validate.validate(data, path)
    errors = [issue for issue in report.issues if issue['severity'] == 'error']
    if errors:
        fail('hub_content', 'Refused %s: %s is not a valid GLB (%s).' % (label, path, errors[0]['message'][:120]))
    json_length = struct.unpack_from('<I', data, 12)[0]
    try:
        doc = strict_json(data[20:20 + json_length].rstrip(b' \x00'))
    except Fault:
        fail('hub_content', 'Refused %s: %s has an unreadable model description.' % (label, path))
    binary = 0
    pos = 20 + json_length
    if pos + 8 <= len(data):
        binary = struct.unpack_from('<I', data, pos)[0]
    buffers = doc.get('buffers', [])
    if any('uri' in buf for buf in buffers) or any('uri' in image for image in doc.get('images', [])):
        fail('hub_content', 'Refused %s: %s points at external files; a pack GLB must be self-contained.' % (label, path))
    declared = sum(int(buf.get('byteLength', 0)) for buf in buffers)
    if binary - declared > 3:
        fail('hub_content', 'Refused %s: %s carries %d unused bytes inside the model.' % (label, path, binary - declared))
    tris = glb_triangles(doc)
    if cap is not None and tris > cap:
        fail('hub_glb_budget', 'Refused %s: %s has %d triangles, over the %d-triangle budget; ask the author for a '
             'lighter model.' % (label, path, tris, cap))
    return tris


def check_content(found, data, path, label, kind=None):
    """Validate one member's bytes for its type; returns extra facts (tris for GLB)."""
    if found == 'json':
        check_json(data, path, label)
    elif found == 'text':
        check_text(data, path, label)
    elif found == 'png':
        check_png(data, path, label)
    elif found == 'wav':
        check_wav(data, path, label)
    elif found == 'ogg':
        check_ogg(data, path, label)
    elif found == 'glb':
        return {'tris': check_glb(data, path, label, TRI_CAPS.get(kind))}
    return {}


# ---------------------------------------------------------------- deterministic build
def file_rows(files, kind=None, label='pack'):
    rows = []
    for name in sorted(files):
        data = files[name]
        check_path(name, label)
        if name == MANIFEST:
            fail('hub_path', 'Refused %s: %s is reserved for the pack manifest.' % (label, MANIFEST))
        found = check_type(name, kind, label)
        if len(data) > LIMITS['file']:
            fail('hub_oversize', 'Refused %s: %s is %d bytes, over the %d-byte file limit.' % (label, name, len(data), LIMITS['file']))
        row = {'path': name, 'sha256': sha256(data), 'bytes': len(data)}
        row.update(check_content(found, data, name, label, kind))
        rows.append(row)
    if not rows or len(rows) + 1 > LIMITS['files']:
        fail('hub_oversize', 'Refused %s: a pack holds 1-%d files.' % (label, LIMITS['files'] - 1))
    if len({r['path'].casefold() for r in rows}) != len(rows):
        fail('hub_path', 'Refused %s: two files differ only by letter case.' % label)
    if sum(r['bytes'] for r in rows) > LIMITS['total']:
        fail('hub_oversize', 'Refused %s: the files total more than %d bytes.' % (label, LIMITS['total']))
    return rows


def manifest_bytes(manifest):
    import json
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + '\n').encode('utf-8')


def build(files, meta):
    """Deterministic data-only ZIP. files: {path: bytes}; meta: entry fields for HUB.json.

    Returns (zip_bytes, manifest). HUB.json lists every other member with sha256 and bytes
    (and tris for GLBs) and is written first; members follow in sorted order.
    """
    kind = meta.get('kind')
    label = meta.get('id', 'pack')
    rows = file_rows(files, kind, label)
    manifest = dict(meta, contract=CONTRACT, files=rows)
    payload = [(MANIFEST, manifest_bytes(manifest))] + [(row['path'], files[row['path']]) for row in rows]
    out, central = bytearray(), bytearray()
    for name, data in payload:
        raw = name.encode('ascii')
        crc = zlib.crc32(data) & 0xFFFFFFFF
        offset = len(out)
        out += struct.pack('<IHHHHHIIIHH', 0x04034B50, 20, 0, 0, 0, DOS_DATE, crc, len(data), len(data), len(raw), 0)
        out += raw + data
        central += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014B50, (3 << 8) | 20, 20, 0, 0, 0, DOS_DATE, crc,
                               len(data), len(data), len(raw), 0, 0, 0, 0, REGULAR, offset) + raw
    end = struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, len(payload), len(payload), len(central), len(out), 0)
    blob = bytes(out + central + end)
    if len(blob) > LIMITS['archive']:
        fail('hub_oversize', 'Refused %s: the archive would be %d bytes, over the %d-byte limit.' % (label, len(blob), LIMITS['archive']))
    return blob, manifest


# ---------------------------------------------------------------- validation (every install, publish and merge)
def _layout(blob, archive, infos, label):
    """Strict hub layout: members back to back from byte 0, then the directory, then the end record.

    Rejects overlapping members (the non-recursive 'overlap' zip bomb), gaps or prefixes that
    could hide a second payload, trailing data and archive comments.
    """
    end_record = len(blob) - 22
    if archive.comment or end_record < 0 or blob[end_record:end_record + 4] != b'PK\x05\x06':
        fail('hub_archive', 'Refused %s: the archive has a comment or trailing data; rebuild it with /hermes64 hub pack.' % label)
    directory_size, directory_offset = struct.unpack_from('<II', blob, end_record + 12)
    if directory_offset + directory_size != end_record:
        fail('hub_archive', 'Refused %s: the archive directory is not where the end record says; do not install it.' % label)
    spans = []
    for info in infos:
        start = info.header_offset
        if start + 30 > len(blob) or blob[start:start + 4] != b'PK\x03\x04':
            fail('hub_archive', 'Refused %s: the archive has a broken member header; download it again.' % label)
        name_len, extra_len = struct.unpack_from('<HH', blob, start + 26)
        spans.append((start, start + 30 + name_len + extra_len + info.compress_size))
    spans.sort()
    for (_a, end), (start, _b) in zip(spans, spans[1:]):
        if end > start:
            fail('hub_bomb', 'Refused %s: archive members overlap (a zip-bomb trick); do not install it.' % label)
    if spans[0][0] != 0 or spans[-1][1] != directory_offset or any(
            end != start for (_a, end), (start, _b) in zip(spans, spans[1:])):
        fail('hub_archive', 'Refused %s: the archive has gaps or hidden data between members; rebuild it with '
             '/hermes64 hub pack.' % label)


def validate(blob, entry=None, label=None):
    """Full data-only validation. Returns {'manifest', 'files', 'tris_max', 'bytes'}; raises Fault."""
    label = label or (entry or {}).get('id') or 'archive'
    if not isinstance(blob, (bytes, bytearray)):
        fail('hub_archive', 'Refused %s: no archive bytes.' % label)
    if len(blob) > LIMITS['archive']:
        fail('hub_oversize', 'Refused %s: the archive is %d bytes, over the %d-byte limit.' % (label, len(blob), LIMITS['archive']))
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(blob)))
        infos = archive.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, EOFError, struct.error):
        fail('hub_archive', 'Refused %s: the file is not a readable ZIP archive; download it again.' % label)
    if not infos or len(infos) > LIMITS['files']:
        fail('hub_oversize', 'Refused %s: an archive holds 1-%d members.' % (label, LIMITS['files']))
    kind = (entry or {}).get('kind')
    names, folded, total = set(), set(), 0
    for info in infos:
        name = info.filename
        if name.endswith('/'):
            fail('hub_path', 'Refused %s: the archive contains folder entries; rebuild it with /hermes64 hub pack.' % label)
        check_path(name, label)
        if name in names or name.casefold() in folded:
            fail('hub_path', 'Refused %s: %s appears twice in the archive.' % (label, name))
        names.add(name)
        folded.add(name.casefold())
        if info.flag_bits & 0x1:
            fail('hub_archive', 'Refused %s: %s is encrypted; packs must be readable data.' % (label, name))
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            fail('hub_archive', 'Refused %s: %s uses an unsupported compression method.' % (label, name))
        mode = info.external_attr >> 16
        if info.create_system == 3 and mode:
            if stat.S_ISLNK(mode):
                fail('hub_symlink', 'Refused %s: %s is a symbolic link; packs may hold regular files only.' % (label, name))
            if not stat.S_ISREG(mode):
                fail('hub_symlink', 'Refused %s: %s is not a regular file.' % (label, name))
            if mode & 0o111:
                fail('hub_exec', 'Refused %s: %s is marked executable; packs may hold data only.' % (label, name))
        elif info.external_attr & 0x10:
            fail('hub_path', 'Refused %s: %s is a folder entry.' % (label, name))
        if name != MANIFEST:
            check_type(name, kind, label)
        if info.file_size > LIMITS['file']:
            fail('hub_oversize', 'Refused %s: %s unpacks to %d bytes, over the %d-byte file limit.' % (label, name, info.file_size, LIMITS['file']))
        if info.file_size and (info.compress_size == 0 or info.file_size > LIMITS['ratio'] * info.compress_size):
            fail('hub_bomb', 'Refused %s: %s expands more than %dx (a zip bomb); do not install it.' % (label, name, LIMITS['ratio']))
        total += info.file_size
        if total > LIMITS['total']:
            fail('hub_bomb', 'Refused %s: the archive unpacks to more than %d bytes (a zip bomb).' % (label, LIMITS['total']))
    if MANIFEST not in names:
        fail('hub_manifest', 'Refused %s: the archive has no %s manifest; rebuild it with /hermes64 hub pack.' % (label, MANIFEST))
    _layout(bytes(blob), archive, infos, label)
    contents = {}
    for info in infos:
        try:
            with archive.open(info) as handle:
                data = handle.read(info.file_size + 1)
                if handle.read(1):
                    data += b'x'
        except (zipfile.BadZipFile, zlib.error, OSError, EOFError, RuntimeError, NotImplementedError):
            fail('hub_archive', 'Refused %s: %s is corrupt (checksum or compression error); download it again.' % (label, info.filename))
        if len(data) != info.file_size:
            fail('hub_bomb', 'Refused %s: %s does not unpack to its declared size (a zip-bomb trick).' % (label, info.filename))
        contents[info.filename] = data
    manifest = check_json(contents.pop(MANIFEST), MANIFEST, label)
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
        fail('hub_manifest', 'Refused %s: %s is not a pack manifest.' % (label, MANIFEST))
    if manifest.get('contract') != CONTRACT:
        fail('hub_contract', 'Refused %s: it was made for hub contract %r, but this Hermes64 reads %s. Update Hermes64 or '
             'ask the author to repack it.' % (label, str(manifest.get('contract'))[:40], CONTRACT))
    kind = kind or manifest.get('kind')
    rows = file_rows(contents, kind, label)
    if manifest['files'] != rows:
        listed = {r.get('path') for r in manifest['files'] if isinstance(r, dict)}
        actual = {r['path'] for r in rows}
        extra = sorted(actual - listed)
        missing = sorted(listed - actual)
        detail = ('unlisted file %s' % extra[0]) if extra else ('missing file %s' % missing[0]) if missing else 'a file hash differs'
        fail('hub_tampered', 'Refused %s: the archive does not match its own manifest (%s); do not install it.' % (label, detail))
    if entry is not None:
        for key in ('id', 'version', 'kind', 'licence', 'author', 'name'):
            if manifest.get(key) != entry.get(key):
                fail('hub_tampered', 'Refused %s: the registry entry and the archive disagree on %s; the index was edited '
                     'or the archive swapped. Do not install it.' % (label, key))
        if entry.get('files') != rows:
            fail('hub_tampered', 'Refused %s: the registry entry lists different files or hashes than the archive; the index '
                 'was edited. Do not install it.' % label)
        budget = (entry.get('budget') or {}).get('tris_max')
        measured = max([r.get('tris', 0) for r in rows] or [0])
        if isinstance(budget, int) and measured > budget:
            fail('hub_glb_budget', 'Refused %s: a model has %d triangles, over the entry budget of %d.' % (label, measured, budget))
    return {'manifest': manifest, 'files': rows, 'contents': contents,
            'tris_max': max([r.get('tris', 0) for r in rows] or [0]), 'bytes': sum(r['bytes'] for r in rows)}
