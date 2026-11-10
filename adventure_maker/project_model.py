"""Portable source-only projects. No service mutation, engine or approval action.

A project root is supplied explicitly. Paths never resolve relative to the cwd
or the plugin's packs directory. Manifest arrays fix assembly order. Story,
room files and cast have exclusive logical field ownership.
"""
import copy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import platform

from . import style_profile as style

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0'
ENCODING = 'python-json-sorted-utf8-v1'


class ProjectError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def require(condition, code, message):
    if not condition:
        raise ProjectError(code, message)


def _read(root, rel):
    try:
        return style.parse_json(style.read_confined(root, rel))
    except style.StyleError as exc:
        raise ProjectError(exc.code, str(exc)) from exc


def _schema(value, rel):
    try:
        style.canonical_bytes(value)
        style.validate_schema(value, _read(ROOT, rel))
    except style.StyleError as exc:
        raise ProjectError(exc.code, str(exc)) from exc


def validate_manifest(manifest):
    _schema(manifest, 'contracts/project/1.0.0.json')
    content, selected = manifest['content'], manifest['style']
    paths = ['project.json', content['story'], content['cast'], content['bindings'], selected['profile'], selected['lock']]
    paths += content['rooms'] + [row['path'] for row in selected['parents']]
    identities = [(row['id'], row['version']) for row in selected['parents']]
    require(len(set(identities)) == len(identities), 'DUPLICATE_OWNER', 'duplicate parent identity')
    require(len({p.casefold() for p in paths}) == len(paths), 'DUPLICATE_OWNER', 'duplicate content/style path')
    try:
        for path in paths:
            style.relative_path(path)
    except style.StyleError as exc:
        raise ProjectError('PATH', str(exc)) from exc
    return copy.deepcopy(manifest)


def migrate_manifest(manifest, target_version=VERSION):
    require(isinstance(manifest, dict) and manifest.get('schema_version') == VERSION and target_version == VERSION,
            'MIGRATION_REQUIRED', 'No cross-version migration is implemented; preserve the old project and lock.')
    return {'status': 'unchanged', 'manifest': validate_manifest(manifest)}


def empty_bindings():
    return {'schema_version': VERSION, 'assets': {}, 'cast': {}, 'audio': {}, 'icons': {}}


def _unique(rows, domain):
    require(isinstance(rows, list), 'CONTENT', domain + ' must be an array')
    ids = []
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('id'), str), 'CONTENT', domain + ' requires IDs')
        require(row['id'] not in ids, 'DUPLICATE_OWNER', domain + '/' + row['id'])
        ids.append(row['id'])


def assemble_content(story, rooms, cast, bindings):
    """Pure merge; never chooses a winner for duplicate owners, even equal values."""
    require(isinstance(story, dict), 'CONTENT', 'story must be an object')
    require(not any(k in story for k in ('rooms', 'characters', 'bindings')), 'DUPLICATE_OWNER', 'story owns neither rooms, cast nor bindings')
    require(isinstance(cast, dict) and set(cast) == {'schema_version', 'characters'} and cast['schema_version'] == VERSION,
            'CONTENT', 'cast requires version and characters only')
    _unique(rooms, 'rooms')
    _unique(cast['characters'], 'characters')
    _schema(bindings, 'contracts/project/bindings-1.0.0.json')
    spec = copy.deepcopy(story)
    spec.update(rooms=copy.deepcopy(rooms), characters=copy.deepcopy(cast['characters']))
    try:
        from story.validation import validate
        validate(spec)
        style.canonical_bytes(spec)
    except (ValueError, style.StyleError) as exc:
        raise ProjectError('CONTENT', str(exc)) from exc
    character_ids = {row['id'] for row in cast['characters']}
    require(set(bindings['cast']) <= character_ids, 'REFERENCE', 'cast binding has no story identity')
    result = {'spec': spec, 'bindings': copy.deepcopy(bindings)}
    result['content_sha256'] = style.digest(result)
    result['owners'] = {'rooms': 'rooms', 'characters': 'cast', 'bindings': 'bindings',
                        'story': sorted(story.keys())}
    return result


def split_legacy_spec(spec):
    """In-memory migration preview only; no file writes and no inferred cast assets."""
    from story.validation import validate
    try:
        validate(spec)
    except ValueError as exc:
        raise ProjectError('CONTENT', str(exc)) from exc
    story = copy.deepcopy(spec)
    rooms = story.pop('rooms')
    cast = {'schema_version': VERSION, 'characters': story.pop('characters')}
    return {'story': story, 'rooms': rooms, 'cast': cast, 'bindings': empty_bindings()}


def read_legacy_current(root):
    """Current pointer wins. A corrupt/missing pointer never resets to starter."""
    root = Path(root).absolute()
    pointer = _read(root, '.maker/current.json')
    require(isinstance(pointer, dict) and set(pointer) == {'spec', 'game'}, 'CURRENT_MISMATCH', 'invalid current pointer')
    spec, game = _read(root, pointer['spec']), _read(root, pointer['game'])
    from story.compiler import compile_spec, validate_game
    try:
        validate_game(game)
        expected = compile_spec(spec)
    except ValueError as exc:
        raise ProjectError('CURRENT_MISMATCH', str(exc)) from exc
    require(style.canonical_bytes(expected) == style.canonical_bytes(game), 'CURRENT_MISMATCH', 'current source/compiled game disagree')
    starter = None
    path = root / 'source/spec.json'
    if path.exists() or path.is_symlink():
        starter = _read(root, 'source/spec.json')
    return {'spec': spec, 'game': game, 'paths': copy.deepcopy(pointer),
            'starter_differs': starter != spec if starter is not None else None,
            'spec_hash': game['spec_hash'], 'game_hash': game['game_hash'], 'status': 'legacy_current_verified'}


def toolchain_identity():
    """Pin this implemented slice, not an invented plugin release or engine ABI."""
    names = ['adventure_maker/style_profile.py', 'adventure_maker/project_model.py',
             'contracts/style/1.0.0.json', 'contracts/style/capabilities-1.0.0.json',
             'contracts/project/1.0.0.json', 'contracts/project/bindings-1.0.0.json']
    names += [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / 'story').glob('*.py'))]
    files = {name: hashlib.sha256(style.read_confined(ROOT, name)).hexdigest() for name in names}
    return {'plugin': {'version': VERSION, 'scope': 'style_core_source_slice', 'sha256': style.digest(files)},
            'files': files, 'python': platform.python_version(),
            'renderer': {'status': 'not_bound'}, 'generator': {'status': 'not_bound'},
            'characters': {'status': 'not_bound'}, 'validator_runtime': {'status': 'not_bound'},
            'godot': {'status': 'not_bound'}, 'blender': {'status': 'not_bound'}}


def make_style_lock(resolved, toolchain=None):
    """Return bytes-to-record data; writing/adoption is an explicit caller action."""
    closure = style.parse_json(resolved.lock_bytes)
    toolchain = toolchain_identity() if toolchain is None else copy.deepcopy(toolchain)
    style.canonical_bytes(toolchain)
    record = {'schema_version': VERSION, 'canonical_encoding': ENCODING,
              'profile': {'id': resolved.profile['id'], 'version': resolved.profile['version']},
              'closure_sha256': resolved.closure_sha256, 'closure': closure,
              'toolchain': toolchain, 'approval': None, 'status': 'data_valid_runtime_pending', 'runtime_ready': False}
    record['lock_sha256'] = style.digest(record)
    return record


@dataclass
class Project:
    root: Path
    manifest: dict

    def _unchanged_manifest(self):
        require(_read(self.root, 'project.json') == self.manifest, 'PROJECT_CHANGED', 'manifest changed; reload explicitly')

    def assemble(self):
        self._unchanged_manifest()
        content = self.manifest['content']
        result = assemble_content(_read(self.root, content['story']),
                                  [_read(self.root, p) for p in content['rooms']],
                                  _read(self.root, content['cast']), _read(self.root, content['bindings']))
        require(result['spec']['id'] == self.manifest['id'], 'CONTENT', 'project/story identity mismatch')
        resolved = self.resolve_style()
        sections, bindings = resolved.profile['sections'], result['bindings']
        domains = {'assets': sections['props']['recipes'], 'cast': sections['characters']['families'],
                   'audio': sections['audio']['cues'], 'icons': [sections['ui']['icons']]}
        for group, mapping in bindings.items():
            if group == 'schema_version':
                continue
            require(all(value in domains[group] for value in mapping.values()), 'REFERENCE', 'unknown ' + group + ' style binding')
        return result

    def resolve_style(self, require_runtime=False):
        selected = self.manifest['style']
        parents = {(row['id'], row['version']): row['path'] for row in selected['parents']}
        try:
            resolved = style.resolve_profile(self.root, selected['profile'], parents=parents, require_runtime=require_runtime)
        except style.StyleError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        require((resolved.profile['id'], resolved.profile['version']) == (selected['id'], selected['version']),
                'LOCK_MISMATCH', 'selected profile identity mismatch')
        return resolved

    def verify_style(self, toolchain=None, require_runtime=False):
        self._unchanged_manifest()
        selected = self.manifest['style']
        record = _read(self.root, selected['lock'])
        resolved = self.resolve_style(require_runtime=require_runtime)
        expected = make_style_lock(resolved, toolchain=toolchain)
        require(style.digest(record) == selected['lock_sha256'] and
                style.canonical_bytes(record) == style.canonical_bytes(expected), 'LOCK_MISMATCH', 'style/resource/toolchain/lock changed; explicit new revision required')
        return {'status': 'data_valid_runtime_pending', 'runtime_ready': False, 'approval': None,
                'closure_sha256': resolved.closure_sha256, 'lock_sha256': record['lock_sha256']}


def load_project(root):
    root = Path(root).absolute()
    manifest = validate_manifest(_read(root, 'project.json'))
    for path in [manifest['content']['story'], manifest['content']['cast'], manifest['content']['bindings'],
                 manifest['style']['profile'], manifest['style']['lock']] + manifest['content']['rooms'] + [p['path'] for p in manifest['style']['parents']]:
        # Opening is intentional: fail missing/nonregular/symlink inputs before
        # creating an object; never follow an unvalidated manifest path later.
        _read(root, path)
    return Project(root, manifest)
