"""Hermes64 Hub registry index (schema hub/1.0.0): validation, loading, search.

The plugin's own schema copy (contracts/hub/1.0.0.json) and licence allow-list are the trust
root: a registry can never widen them. An index carries ``entries_sha256`` (sha256 of the
canonical entries list), so a hand-edited index is refused; each entry must then match the
HUB.json inside its archive at install time, so an edited entry with a recomputed hash is
still refused.

Locations: a local registry folder (default: the bundled ``hub/``), a ``file://`` URL, or an
``https://`` URL under the ``hub_url`` setting. ``hub_url`` is blank by default, which keeps
the network off: nothing is ever downloaded unless the owner sets it.
"""
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from .hub_archive import CONTRACT, sha256
from .safety import Fault, fail, strict_json

SCHEMA = 'hub/1.0.0'
KINDS = ('style', 'kit', 'character', 'sound', 'cover', 'game')
LICENCES = ('CC0-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC')
RECOMMENDED = {'assets': 'CC-BY-4.0', 'data': 'MIT'}
TIERS = ('playtested', 'proved', 'owner-approved', 'validated', 'machine-checked', 'data-checked', 'data-only', 'draft')
INDEX_LIMIT = 8 * 1024 * 1024
ENTRY_LIMIT = 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r'[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}')
SEMVER = re.compile(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})')
EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
KIND_WORDS = {'style': 'style', 'styles': 'style', 'pack': 'style', 'packs': 'style', 'theme': 'style', 'themes': 'style',
              'kit': 'kit', 'kits': 'kit', 'character': 'character', 'characters': 'character', 'people': 'character',
              'cast': 'character', 'sound': 'sound', 'sounds': 'sound', 'audio': 'sound', 'sfx': 'sound',
              'cover': 'cover', 'covers': 'cover', 'game': 'game', 'games': 'game'}
STOP = {'a', 'an', 'the', 'of', 'for', 'and', 'with', 'to', 'in', 'on'}
_SCHEMA_CACHE = {}


def version_tuple(text):
    match = SEMVER.fullmatch(text or '')
    return tuple(int(x) for x in match.groups()) if match else None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def entries_digest(entries):
    return sha256(canonical(entries))


def pretty(value):
    """Deterministic, diff-friendly JSON bytes for files we write."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + '\n').encode('utf-8')


def schema():
    if 'hub' not in _SCHEMA_CACHE:
        _SCHEMA_CACHE['hub'] = json.loads((ROOT / 'contracts/hub/1.0.0.json').read_text(encoding='utf-8'))
    return _SCHEMA_CACHE['hub']


def _schema_check(value, ref, label):
    from .style_profile import StyleError, validate_schema
    root = schema()
    try:
        validate_schema(value, root['$defs'][ref] if ref else root, root)
    except StyleError as exc:
        where = str(exc).split(': ', 1)[-1]
        fail('hub_entry', 'Refused %s: its registry entry is malformed (%s); the registry needs fixing.' % (label, where[:160]))


def validate_entry(entry, label=None):
    """Friendly explicit checks first (licence, contract, author, id/version), then the schema."""
    if not isinstance(entry, dict):
        fail('hub_entry', 'Refused a registry entry: it is not a JSON object.')
    label = label or (entry.get('id') if isinstance(entry.get('id'), str) else 'entry')[:64]
    if not isinstance(entry.get('id'), str) or not ID.fullmatch(entry['id']) or len(entry['id']) > 64:
        fail('hub_entry', 'Refused %s: ids look like kind.name (lowercase letters, digits, _ and dots).' % label)
    if 'licence' not in entry or entry.get('licence') in (None, ''):
        fail('hub_licence', 'Refused %s: it has no licence. Every hub entry needs an SPDX licence id (%s).'
             % (label, ', '.join(LICENCES)))
    if entry['licence'] not in LICENCES:
        fail('hub_licence', 'Refused %s: licence %r is not allowed in the hub; use one of %s (CC-BY-4.0 recommended for '
             'assets, MIT for data).' % (label, str(entry['licence'])[:40], ', '.join(LICENCES)))
    contract = (entry.get('compat') or {}).get('contract') if isinstance(entry.get('compat'), dict) else None
    if contract != CONTRACT:
        fail('hub_contract', 'Refused %s: it needs hub contract %r, but this Hermes64 reads %s. Update Hermes64 or ask the '
             'author to repack it.' % (label, str(contract)[:40], CONTRACT))
    author = entry.get('author')
    if isinstance(author, str) and EMAIL.search(author):
        fail('hub_entry', 'Refused %s: the author field contains an email address; use a name only.' % label)
    if version_tuple(entry.get('version')) is None:
        fail('hub_entry', 'Refused %s: version must look like 1.0.0.' % label)
    _schema_check(entry, 'entry', label)
    if entry.get('visibility') == 'public-with-notice' and not entry.get('notice'):
        fail('hub_entry', 'Refused %s: public-with-notice entries must carry their notice.' % label)
    return entry


def plugin_version(root=ROOT):
    """The plugin's release core (``1.0.0-rc`` -> ``1.0.0``): hub compat floors are plain X.Y.Z."""
    try:
        version = json.loads((Path(root) / 'plugin.yaml').read_text(encoding='utf-8'))['version']
    except (OSError, ValueError, KeyError):
        return '0.0.0'
    return re.split(r'[-+]', str(version), maxsplit=1)[0]


def check_plugin(entry, root=ROOT):
    need = version_tuple(entry['compat']['plugin'][2:])
    have = version_tuple(plugin_version(root)) or (0, 0, 0)
    if need is None or have < need:
        fail('hub_compat', 'Refused %s: it needs Hermes64 %s or newer (this is %s); update the plugin first.'
             % (entry['id'], entry['compat']['plugin'][2:], '.'.join(map(str, have))))


def validate_index(doc, label='registry index'):
    if not isinstance(doc, dict):
        fail('hub_index', 'The %s is not a JSON object; fix the registry or clear hub_url/hub_registry.' % label)
    if doc.get('schema') != SCHEMA:
        fail('hub_index', 'The %s uses schema %r, but this Hermes64 reads %s; update Hermes64.' % (label, str(doc.get('schema'))[:40], SCHEMA))
    entries = doc.get('entries')
    if not isinstance(entries, list):
        fail('hub_index', 'The %s has no entries list; the registry needs rebuilding.' % label)
    if doc.get('entries_sha256') != entries_digest(entries):
        fail('hub_tampered', 'The %s failed its integrity check (entries_sha256 does not match): it was edited by hand. '
             'Rebuild it with python3 -B -m tools.hub build, or get a fresh copy.' % label)
    seen = {}
    for entry in entries:
        validate_entry(entry)
        key = (entry['id'], entry['version'])
        if key in seen:
            fail('hub_duplicate', 'The %s lists %s %s twice%s; a registry may hold each id and version once.' % (
                label, entry['id'], entry['version'],
                ' with different hashes' if seen[key] != entry['sha256'] else ''))
        seen[key] = entry['sha256']
    if [(e['id'], version_tuple(e['version'])) for e in entries] != sorted((e['id'], version_tuple(e['version'])) for e in entries):
        fail('hub_index', 'The %s is not sorted by id and version; rebuild it with python3 -B -m tools.hub build.' % label)
    _schema_check(doc, None, label)
    return doc


def make_index(entries, name, version, note=None, pending=None, base_url=None):
    entries = sorted(entries, key=lambda e: (e['id'], version_tuple(e['version'])))
    registry = {'name': name, 'contract': CONTRACT, 'plugin_version': version}
    if note:
        registry['note'] = note
    if base_url:
        registry['base_url'] = base_url
    doc = {'schema': SCHEMA, 'registry': registry,
           'licences': {'allowed': list(LICENCES), 'recommended': dict(RECOMMENDED)},
           'entries': entries, 'entries_sha256': entries_digest(entries)}
    if pending:
        doc['pending'] = pending
    return validate_index(doc)


# ---------------------------------------------------------------- locations and fetching
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_url(text):
    return isinstance(text, str) and re.match(r'^(https?|file)://', text) is not None


def _read_local(path, limit, what):
    path = Path(path)
    try:
        from .safety import inspect_path
        inspect_path(path)
        if not path.is_file():
            fail('hub_missing', '%s not found at %s.' % (what, path))
        if path.stat().st_size > limit:
            fail('hub_oversize', '%s at %s is larger than %d bytes.' % (what, path, limit))
        with path.open('rb') as handle:
            return handle.read(limit + 1)
    except Fault:
        raise
    except OSError as exc:
        fail('hub_missing', 'Could not read %s at %s (%s).' % (what, path, exc.strerror or type(exc).__name__))


def fetch(url, settings, limit, what='file'):
    """Read a file:// URL, or download an http(s) URL inside the hub_url scope. Network is off by default."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == 'file':
        if parts.netloc not in ('', 'localhost'):
            fail('hub_url', 'Refused %s: file:// URLs must point at this computer.' % url[:120])
        return _read_local(urllib.request.url2pathname(parts.path), limit, what)
    if parts.scheme not in ('http', 'https'):
        fail('hub_url', 'Unsupported address %r; use a registry folder, a file:// URL or an https:// URL.' % url[:120])
    base = (settings.get('hub_url') or '').strip().rstrip('/')
    if not base:
        fail('hub_network_off', 'Downloads are off: set hub_url in the hermes64 plugin settings to a registry you trust, '
             'then try again. Nothing was downloaded.')
    if not (url == base or url.startswith(base + '/')):
        fail('hub_url_scope', 'Refused %s: it is outside the configured hub_url (%s); Hermes64 only downloads from that '
             'registry.' % (url[:120], base[:120]))
    host = parts.hostname or ''
    if parts.scheme == 'http' and host not in LOOPBACK:
        fail('hub_insecure', 'Refused %s: plain http is only allowed for a registry on this computer; use https.' % url[:120])
    handlers = [_NoRedirect()]
    if host in LOOPBACK:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={'User-Agent': 'hermes64-hub/1', 'Accept-Encoding': 'identity'})
    try:
        with opener.open(request, timeout=20) as response:
            declared = response.headers.get('Content-Length')
            if declared and declared.isdigit() and int(declared) > limit:
                fail('hub_oversize', 'Refused %s: the server says it is %s bytes, over the %d-byte limit.' % (what, declared, limit))
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            fail('hub_redirect', 'The registry redirected %s; put the final address in hub_url.' % url[:120])
        fail('hub_download', 'Download failed for %s (HTTP %d); check hub_url or try later.' % (url[:120], exc.code))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, 'reason', exc)
        fail('hub_download', 'Download failed for %s (%s); check hub_url and your connection.' % (url[:120], str(reason)[:120]))
    if len(data) > limit:
        fail('hub_oversize', 'Refused %s: it is larger than %d bytes.' % (what, limit))
    return data


def join(base, rel):
    """Resolve an entry's relative download/preview path against its registry location."""
    from .safety import relative
    if is_url(rel):
        return rel
    relative(rel)
    if is_url(base):
        return base.rstrip('/') + '/' + urllib.parse.quote(rel)
    return str(Path(base) / rel)


def load(location, settings, label=None):
    """Load and validate an index from a folder, index.json path, file:// or https:// URL."""
    if is_url(location):
        url = location if location.endswith('.json') else location.rstrip('/') + '/index.json'
        raw = fetch(url, settings, INDEX_LIMIT, 'registry index')
        base = url.rsplit('/', 1)[0]
    else:
        path = Path(location)
        path = path if path.suffix == '.json' else path / 'index.json'
        raw = _read_local(path, INDEX_LIMIT, 'Registry index')
        base = str(path.parent)
    try:
        doc = strict_json(raw) if len(raw) <= 1024 * 1024 else json.loads(raw.decode('utf-8'))
    except (Fault, ValueError, UnicodeError):
        fail('hub_index', 'The registry index at %s is not valid JSON; rebuild it or fix hub_url/hub_registry.' % str(location)[:160])
    return validate_index(doc, label or 'registry index'), base


def load_entry(location, settings):
    """A single entry.json (a publish draft or community entry) from a path or URL; returns (entry, base)."""
    raw = fetch(location, settings, ENTRY_LIMIT, 'entry') if is_url(location) else _read_local(location, ENTRY_LIMIT, 'Entry file')
    try:
        entry = strict_json(raw)
    except Fault:
        fail('hub_entry', 'The entry file %s is not valid JSON.' % str(location)[:160])
    base = location.rsplit('/', 1)[0] if is_url(location) else str(Path(location).parent)
    return validate_entry(entry), base


# ---------------------------------------------------------------- search
def words(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


# Everyday words for things the index names differently. Search only: ids and tags never change.
ALIASES = {'step': 'footsteps', 'steps': 'footsteps', 'footstep': 'footsteps', 'walking': 'footsteps',
           'ice': 'snow', 'icy': 'snow', 'winter': 'snow', 'cold': 'snow', 'frozen': 'snow', 'arctic': 'polar',
           'woods': 'forest', 'woodland': 'forest', 'scifi': 'sci', 'ambient': 'ambience',
           'song': 'music', 'soundtrack': 'music', 'tune': 'music', 'kitten': 'cat', 'kitty': 'cat',
           'hero': 'lead', 'protagonist': 'lead', 'npc': 'person', 'people': 'person', 'villager': 'person',
           'click': 'ui', 'button': 'ui', 'interface': 'ui'}


def _fields(entry, style_words):
    tags = entry.get('tags', [])
    return {'name': words(entry['name']), 'tags': set(tags) | set(words(' '.join(tags))), 'id': words(entry['id']),
            'summary': words(entry.get('summary', '')), 'style': style_words.get(entry['compat']['style'], set())}


def _score(word, entry, fields):
    single = word[:-1] if len(word) > 3 and word.endswith('s') else word
    for candidate in dict.fromkeys((word, single)):
        if candidate in fields['name']:
            return 5
        if candidate in fields['tags'] or candidate == entry['kind'] or candidate == entry['compat']['style']:
            return 4
        if candidate in fields['id']:
            return 3
        if any(t.startswith(candidate) for t in fields['name']) or any(t.startswith(candidate) for t in fields['tags']):
            return 2
        if candidate in fields['style']:
            return 2            # words of the entry's style pack: a polar kit answers "snow"
        if candidate in fields['summary'] or any(t.startswith(candidate) for t in fields['summary']):
            return 1
    return 0


def style_words(entries):
    """Each style pack's words (tags and name) by pack id; entries locked to that style answer to them in search."""
    out = {}
    for entry in entries:
        if entry['kind'] == 'style':
            tags = entry.get('tags', [])
            out[entry['id'].split('.', 1)[1]] = set(tags) | set(words(' '.join(tags))) | set(words(entry['name']))
    return out


def search(entries, query='', kind=None, limit=20):
    """AND search over name, tags, id, kind, style (and that style's own tags) and summary; best matches first."""
    terms = [w for w in words(query) if w not in STOP]
    if kind is None and terms and KIND_WORDS.get(terms[-1]) and len(terms) > 1:
        kind, terms = KIND_WORDS[terms[-1]], terms[:-1]
    styles = style_words(entries)
    ranked = []
    for entry in entries:
        if kind and entry['kind'] != kind:
            continue
        fields = _fields(entry, styles)
        total = 0
        for term in terms:
            score = _score(term, entry, fields)
            if not score and term in ALIASES:
                score = _score(ALIASES[term], entry, fields)
            if not score and KIND_WORDS.get(term) == entry['kind']:
                score = 2
            if not score:
                total = None
                break
            total += score
        if total is not None:
            ranked.append((-total, entry['id'], entry))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in ranked[:limit]], len(ranked), kind
