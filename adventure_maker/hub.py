"""Hermes64 Hub v0: a local, file-based community registry. Search, info, install, pack, publish.

The registry is a folder (bundled: ``hub/``) holding ``index.json`` (schema hub/1.0.0), archives
and previews. Install verifies the archive sha256 against the entry, runs the data-only
validator, checks the plugin contract and the game's style lock (its pack binding), refuses to
overwrite anything, writes under ``assets/hub/<id>/`` (a theme pack also lands in ``packs/``
so ``hermes64_pack_select`` can use it) and records the install in the game's ``catalog.json``.
Pack builds a deterministic archive + entry in your hub folder; publish turns it into a local
pull-request draft. Nothing is ever uploaded, and downloads stay off unless ``hub_url`` is set.
Every refusal is one plain-English line with the next step.
"""
import json
from pathlib import Path
import re
import shlex

from . import catalog as cat
from . import hub_archive, hub_index, hub_sources
from .hub_index import KINDS, LICENCES, RECOMMENDED, pretty, version_tuple
from .safety import Fault, encode, fail, strict_json
from .schemas import ID, obj, text, validate

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ('search', 'info', 'install', 'pack', 'publish')
SETTINGS = ('projects_root', 'bundle_root', 'python_path', 'godot_path', 'blender_path', 'builder', 'hub_registry', 'hub_url')
HUB_SCHEMA = obj({'action': {'enum': list(ACTIONS)}, 'query': text(200), 'kind': {'enum': list(KINDS)},
                  'id': text(400), 'project': ID,
                  'version': text(16, pattern=r'^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$'),
                  'author': text(80), 'licence': {'enum': list(LICENCES)}}, ['action'])
SCHEMA = {'name': 'hermes64_hub', 'description': 'Hermes64 Hub actions (wire copy: adventure_maker/wire.py SHORT).',
          'parameters': HUB_SCHEMA}
PRIVATE = re.compile(rb'/Users/[^\x00\s"\'<>]+|(?<![A-Za-z0-9_./-])/home/[^\x00\s"\'<>]+|[A-Za-z]:[/\\]Users[/\\]|'
                     rb'cameo_visor_01|characters[/\\]internal[/\\]|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', re.I)
MEDIA = ('glb', 'png', 'wav', 'ogg')
HELP = ('Hermes64 Hub: share styles, kits, characters, sounds and games through a local registry (nothing is uploaded).\n'
        '/hermes64 hub search <words> [kind]\n'
        '/hermes64 hub info <id>\n'
        '/hermes64 hub install <id> [game]\n'
        '/hermes64 hub pack <asset-or-game> [version=1.0.1 licence=CC-BY-4.0 author="Your Name"]\n'
        '/hermes64 hub publish <id>\n'
        'Kinds: style, kit, character, sound, cover, game. Browse offline: %s')


def one_line(message):
    return ' '.join(str(message).split())


def proof_label(status, spec):
    """Checker status in words; 'conditional' counts only under the game's own module policy (story.modules.edits.accepted)."""
    if status == 'conditional' and (spec.get('gameplay') or {}).get('verification_policy') == 'conditional':
        return 'conditional, accepted by its module policy'
    return status


def human_size(size):
    for unit in ('B', 'KB', 'MB'):
        if size < 1024 or unit == 'MB':
            return ('%d %s' % (size, unit)) if unit == 'B' else ('%.1f %s' % (size, unit))
        size /= 1024.0


def slug_for(entry_id):
    return re.sub(r'[^a-z0-9-]+', '-', entry_id.split('.', 1)[-1].replace('_', '-')).strip('-')[:40] or 'hub-game'


def text_files(files):
    """(path, bytes) for every member whose text could leak a private path or address."""
    for path, data in sorted(files.items()):
        found, _ext = hub_archive.kind_of(path)
        if found in ('json', 'text'):
            yield path, data
        elif found == 'glb' and len(data) > 20:
            yield path, data[20:20 + int.from_bytes(data[12:16], 'little')]


class Hub:
    def __init__(self, settings, data_root=None, games_root=None):
        from .service import Service
        self.settings = dict(settings or {})
        self.bundle = Path(self.settings.get('bundle_root') or ROOT)
        if not self.bundle.is_absolute() or '..' in self.bundle.parts:
            fail('configuration', 'bundle_root must be an absolute path without traversal.')
        self.data_root = Path(data_root) if data_root else None
        self.games_root = Path(games_root) if games_root else None
        self.service = Service(self.settings)

    # ------------------------------------------------------------ where things live
    def work(self, create=False):
        """Your hub folder: packed entries, publish drafts and the download cache."""
        if self.data_root is not None:
            path = self.data_root
        else:
            root = self.settings.get('projects_root') or ''
            if not root or not Path(root).is_absolute() or not Path(root).is_dir():
                fail('configuration', 'No hub folder yet: set projects_root in the hermes64 plugin settings (or make a game '
                     'with /hermes64 new first), then try again.')
            path = Path(root) / '.hub'
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def registry(self):
        url = (self.settings.get('hub_url') or '').strip()
        if url:
            index, base = hub_index.load(url, self.settings)
            return index, base, url.rstrip('/')
        folder = (self.settings.get('hub_registry') or '').strip()
        if folder:
            path = Path(folder)
            if not path.is_absolute() or not path.is_dir():
                fail('hub_registry', 'hub_registry %r is not an existing absolute folder; fix it in the hermes64 plugin '
                     'settings, or clear it to use the bundled registry.' % folder[:160])
            index, base = hub_index.load(str(path), self.settings)
            return index, base, str(path)
        index, base = hub_index.load(str(self.bundle / 'hub'), self.settings)
        index = dict(index, entries=[e for e in index['entries'] if not hub_sources.removed_optional(e['id'], self.bundle)])
        return index, base, 'bundled registry'

    def local(self):
        try:
            folder = self.work() / 'packs'
        except Fault:
            return []
        if not folder.is_dir():
            return []
        return [hub_index.load_entry(str(path), self.settings) + ('your packs',) for path in sorted(folder.glob('*.json'))]

    def rows(self):
        index, base, label = self.registry()
        rows = [(entry, base, label) for entry in index['entries']]
        rows += self.local()
        return rows, index, label

    def find(self, entry_id, version=None):
        rows, _index, _label = self.rows()
        hits = [row for row in rows if row[0]['id'] == entry_id and (version is None or row[0]['version'] == version)]
        if not hits:
            near = [row[0]['id'] for row in rows if entry_id.split('.')[-1] in row[0]['id']][:3]
            fail('hub_not_found', 'No hub entry %r%s. Try /hermes64 hub search %s.' % (
                entry_id[:64], (' (did you mean %s?)' % ', '.join(near)) if near else '',
                (entry_id.split('.')[-1] or 'words')[:30]))
        best = max(version_tuple(row[0]['version']) for row in hits)
        top = [row for row in hits if version_tuple(row[0]['version']) == best]
        if len({row[0]['sha256'] for row in top}) > 1:
            fail('hub_duplicate', 'Refused %s %s: your packs and the registry hold different archives under the same id and '
                 'version. Repack yours with a new version (version=...).' % (entry_id, top[0][0]['version']))
        return top[0]

    def resolve(self, ref):
        if hub_index.is_url(ref) or ref.endswith('.json') or '/' in ref:
            entry, base = hub_index.load_entry(ref, self.settings)
            return entry, base, ref
        return self.find(ref)

    def archive(self, entry, base):
        location = hub_index.join(base, entry['download'])
        if hub_index.is_url(location) and not location.startswith('file:'):
            cache = self.work(create=True) / 'cache' / (entry['sha256'] + '.zip')
            if cache.is_file() and hub_archive.sha256(cache.read_bytes()) == entry['sha256']:
                return cache.read_bytes()
            blob = hub_index.fetch(location, self.settings, entry['size'], 'archive')
            if hub_archive.sha256(blob) == entry['sha256']:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(blob)
            return blob
        if hub_index.is_url(location):
            return hub_index.fetch(location, self.settings, entry['size'] + 1, 'archive')
        path = Path(location)
        if path.is_file():
            return hub_index._read_local(path, hub_archive.LIMITS['archive'], 'Archive')
        if entry['source'] == 'bundled':
            recipe = hub_sources.recipe_by_id(entry['id'], self.bundle)
            if recipe is not None:
                blob, _entry = hub_sources.build(recipe, self.bundle, version=entry['version'])
                return blob
        fail('hub_missing', 'The archive for %s is missing from %s; the registry copy is incomplete.' % (entry['id'], base[:160]))

    def verified(self, entry, base):
        hub_index.check_plugin(entry, self.bundle)
        blob = self.archive(entry, base)
        if len(blob) != entry['size'] or hub_archive.sha256(blob) != entry['sha256']:
            fail('hub_hash', 'Refused %s: the archive does not match the sha256 in its entry (got %s...). Do not use it; get a '
                 'fresh copy of the registry%s.' % (entry['id'], hub_archive.sha256(blob)[:12],
                                                   ' (bundled entries rebuild from this plugin: run python3 -B -m tools.hub build)'
                                                   if entry['source'] == 'bundled' else ''))
        return hub_archive.validate(blob, entry)

    # ------------------------------------------------------------ search / info
    def search(self, query='', kind=None):
        rows, index, label = self.rows()
        entries = [row[0] for row in rows]
        found, total, kind = hub_index.search(entries, query or '', kind)
        what = ('"%s"' % query) if query else 'everything'
        if kind:
            what += ' in %ss' % kind
        lines = ['Hub: %d match%s for %s in the %s (%d entries)' % (total, '' if total == 1 else 'es', what, label, len(entries))]
        for entry in found:
            lines.append('%s · %s · %s · %s · %s' % (entry['id'], entry['name'], entry['kind'], entry['licence'], entry['tier']['label']))
        if total > len(found):
            lines.append('…and %d more; add a word or a kind to narrow it.' % (total - len(found)))
        lines.append('Install: /hermes64 hub install <id> [game] · details: /hermes64 hub info <id>' if found else
                     'Try fewer words, or a kind: style, kit, character, sound, cover, game.')
        return {'ok': True, 'status': 'found' if found else 'no_match', 'count': total, 'kind': kind,
                'results': [dict({k: e[k] for k in ('id', 'name', 'kind', 'version', 'licence', 'size')},
                                 tier=e['tier']['label']) for e in found],
                'message': '\n'.join(lines)}

    def info(self, ref):
        entry, _base, label = self.resolve(ref)
        tier = entry['tier']
        style = 'any style' if entry['compat']['style'] == 'any' else entry['compat']['style'].replace('_', ' ') + ' games'
        lines = ['%s (%s %s) · %s · %s · %s' % (entry['name'], entry['id'], entry['version'], entry['kind'], entry['licence'], tier['label']),
                 entry['summary'],
                 'By %s · %d files · %s · for %s · needs Hermes64 %s · from the %s' % (
                     entry['author'], len(entry['files']), human_size(entry['size']), style, entry['compat']['plugin'][2:], label),
                 'Checked: proof %s; playtest %s; style %s; human %s' % (tier['proof'], tier['playtest'], tier['style'], tier['human'])]
        if entry.get('notice'):
            lines.append('Notice: ' + entry['notice'])
        lines.append('Install: /hermes64 hub install %s%s' % (entry['id'], '' if entry['kind'] == 'game' else ' <game>'))
        brief = {k: v for k, v in entry.items() if k != 'files'}
        brief['file_count'] = len(entry['files'])
        return {'ok': True, 'status': 'info', 'entry': brief, 'registry': label, 'message': '\n'.join(lines)}

    # ------------------------------------------------------------ install
    def target(self, name):
        if name:
            return self.service.project(name)
        root = self.settings.get('projects_root') or ''
        games = sorted(p.name for p in Path(root).iterdir() if (p / '.maker/project.json').is_file()) \
            if root and Path(root).is_dir() else []
        if len(games) == 1:
            return self.service.project(games[0])
        fail('hub_project', 'Which game? Add its name: /hermes64 hub install <id> <game>%s.' % (
            ' (your games: %s)' % ', '.join(games[:8]) if games else '; make one first with /hermes64 new "<premise>"'))

    def project_style(self, project):
        """The game's style lock: its immutable pack binding (id + sha256) and that pack's kit family."""
        from .packs import Packs, fingerprint
        spec_path = self.service.current(project)['spec'] if project.path('.maker/current.json').is_file() else 'source/spec.json'
        pack = Packs(self.settings, project).selected(project.read_json(spec_path))
        return {'pack': pack['id'], 'kit_pack': pack['kit_pack_id'], 'sha256': fingerprint(pack)}

    def compat(self, entry, report, style, project_name):
        need = entry['compat']['style']
        rig = entry['compat'].get('rig')
        if rig:
            rig_id, _at, version = rig.partition('@')
            have = self.bundle / 'rigs' / rig_id / 'rig.json'
            have_version = strict_json(have.read_bytes()).get('version') if have.is_file() else None
            if have_version is None or have_version.split('.')[0] != version.split('.')[0]:
                fail('hub_rig', 'Refused %s: it needs the %s rig (version %s), which this Hermes64 %s; update the plugin '
                     'first.' % (entry['id'], rig_id, version, 'does not have' if have_version is None else
                                 'has as %s' % have_version))
        if entry['kind'] == 'style':
            if need != 'any' and not (self.bundle / 'kits/packs' / need / 'pack.json').is_file():
                fail('hub_style', 'Refused %s: it needs the %s kit library, which this Hermes64 does not have.' % (entry['id'], need))
            return
        if need != 'any' and style is not None and need != style['kit_pack']:
            fail('hub_style', 'Refused %s: it is made for %s games, but %s is locked to %s (pack %s). Pick a %s entry, or '
                 'install it into a %s game.' % (entry['id'], need.replace('_', ' '), project_name,
                                                style['kit_pack'].replace('_', ' '), style['pack'],
                                                style['kit_pack'].replace('_', ' '), need.replace('_', ' ')))

    def plan(self, entry, report, project):
        """[(project-relative path, bytes, may_exist_identical)] for one install; nothing written yet."""
        from .packs import validate_pack
        base = 'assets/hub/%s/' % entry['id']
        writes = [(base + hub_archive.MANIFEST, hub_archive.manifest_bytes(report['manifest']), False)]
        writes += [(base + path, data, False) for path, data in sorted(report['contents'].items())]
        if entry['kind'] == 'style' and 'pack.json' in report['contents']:
            pack = validate_pack(strict_json(report['contents']['pack.json']))
            writes.append(('packs/%s/pack.json' % pack['id'], encode(pack), True))
        for rel, _data, _same in writes:
            project.path(rel)
        return writes

    def install(self, ref, project=None):
        entry, base, label = self.resolve(ref)
        report = self.verified(entry, base)
        if entry['kind'] == 'game':
            return self.install_game(entry, report, label, project)
        target = self.target(project)
        with target.lock():
            style = self.project_style(target)
            self.compat(entry, report, style, target.root.name)
            doc = cat.read_project(target)
            if cat.installed(doc, entry['id']):
                old = cat.installed(doc, entry['id'])['installed']
                fail('hub_installed', 'Refused %s: %s already has it installed (version %s); installs never overwrite. Remove '
                     'assets/hub/%s and its catalog.json row first, or install into another game.' % (
                         entry['id'], target.root.name, old['version'], entry['id']))
            writes = self.plan(entry, report, target)
            for rel, data, may_exist in writes:
                path = target.path(rel)
                if path.exists() and not (may_exist and path.read_bytes() == data):
                    if may_exist:
                        fail('hub_exists', 'Refused %s: %s already has a different %s; installing over it is refused. Use a '
                             'game that does not use that pack.' % (entry['id'], target.root.name, rel))
                    fail('hub_exists', 'Refused %s: %s already exists in %s; installs never overwrite.' % (entry['id'], rel, target.root.name))
            written = []
            for rel, data, may_exist in writes:
                if not target.path(rel).exists():
                    target.write_bytes(rel, data)
                written.append((rel, hub_archive.sha256(data), len(data)))
            cat.write_project(target, cat.add_install(doc, entry, written, label))
        if entry['kind'] == 'style' and 'pack.json' in report['contents']:
            pack_id = strict_json(report['contents']['pack.json'])['id']
            nxt = 'Use it: hermes64_pack_select with project=%s pack=%s (recompiles and re-checks the game).' % (target.root.name, pack_id)
        elif entry['kind'] == 'style':
            nxt = 'Style profiles are data for portable projects; the game builder does not read them yet.'
        else:
            nxt = ('Files are in assets/hub/%s/ and listed in catalog.json; bundled games bind assets by id, so placing them in '
                   'a build is a manual step for now.' % entry['id'])
        need = entry['compat']['style']
        fit = ('a new look for this game (%s kits)' % need.replace('_', ' ') if entry['kind'] == 'style' else
               'fits any style' if need == 'any' else 'style matches (%s)' % need.replace('_', ' '))
        message = 'Installed %s (%s %s) into %s: %d files, sha256 verified, data-only check passed, %s.\n%s' % (
            entry['name'], entry['id'], entry['version'], target.root.name, len(written), fit, nxt)
        return {'ok': True, 'status': 'installed', 'entry': entry['id'], 'version': entry['version'], 'project': target.root.name,
                'project_dir': str(target.root), 'files': [w[0] for w in written], 'catalog': 'catalog.json', 'message': message}

    def install_game(self, entry, report, label, name):
        from .packs import validate_pack, fingerprint
        from .service import source_guard
        contents = report['contents']
        if 'source/spec.json' not in contents:
            fail('hub_game', 'Refused %s: a game pack needs source/spec.json.' % entry['id'])
        spec = source_guard(strict_json(contents['source/spec.json']))
        binding = (spec.get('metadata') or {}).get('hermes64_pack')
        if not isinstance(binding, dict) or set(binding) != {'id', 'sha256'}:
            fail('hub_game', 'Refused %s: its story does not lock a style pack (metadata.hermes64_pack).' % entry['id'])
        rel = 'packs/%s/pack.json' % binding['id']
        if rel not in contents:
            fail('hub_game', 'Refused %s: it locks pack %s but does not include %s.' % (entry['id'], binding['id'], rel))
        pack = validate_pack(strict_json(contents[rel]))
        if fingerprint(pack) != binding['sha256']:
            fail('hub_game', "Refused %s: the game's style lock does not match its pack file; do not install it." % entry['id'])
        if not (self.bundle / 'kits/packs' / pack['kit_pack_id'] / 'pack.json').is_file():
            fail('hub_style', 'Refused %s: it needs the %s kit library, which this Hermes64 does not have.' % (entry['id'], pack['kit_pack_id']))
        from .newgame import check_name, resolve_root
        name = check_name(name or slug_for(entry['id']))
        root, uses_default = resolve_root(self.settings, self.games_root)
        if (root / name).exists() or (root / name).is_symlink():
            fail('hub_exists', 'Refused %s: a game named %s already exists; add a new name: /hermes64 hub install %s <new-name>.'
                 % (entry['id'], name, entry['id']))
        if uses_default:
            root.mkdir(parents=True, exist_ok=True)
        self.settings['projects_root'] = self.service.settings['projects_root'] = str(root)
        project = self.service.project(name, create=True)
        side = 'assets/hub/%s/' % entry['id']
        with project.lock():
            written = []
            game_files = {p: d for p, d in contents.items() if p.startswith(('source/', 'packs/', 'assets/')) or p in ('AUTHORING.md',)}
            extra = {p: d for p, d in contents.items() if p not in game_files and p != 'catalog.json'}
            extra[hub_archive.MANIFEST] = hub_archive.manifest_bytes(report['manifest'])
            for path, data in sorted(game_files.items()) + sorted((side + p, d) for p, d in extra.items()):
                if project.path(path).exists():
                    fail('hub_exists', 'Refused %s: %s would be overwritten.' % (entry['id'], path))
                project.write_bytes(path, data)
                written.append((path, hub_archive.sha256(data), len(data)))
            doc = cat.empty_project_catalog()
            if 'catalog.json' in contents:
                carried = strict_json(contents['catalog.json'])
                doc = cat.validate(carried, label="game's carried catalog.json")
            cat.write_project(project, cat.add_install(doc, entry, written, label))
        compiled = json.loads(self.service.handle('hermes64_compile', {'project': name, 'spec_path': 'source/spec.json'}))
        checked = json.loads(self.service.handle('hermes64_check', {'project': name})) if compiled.get('ok') else {}
        status = proof_label(checked.get('status', 'not run'), spec)
        accepted = status == 'proved' or status.startswith('conditional, accepted')
        message = 'Installed game %s (%s %s) as %s in %s: sha256 verified, data-only check passed; compiled, proof %s.\n%s' % (
            entry['name'], entry['id'], entry['version'], name, project.root.parent,
            status, 'Next: hermes64_playtest or hermes64_open with project=%s; edit it like any game.' % name if accepted else
            'It did not pass its proof here; inspect it with hermes64_check before playing.')
        return {'ok': bool(compiled.get('ok')) and accepted, 'status': 'installed_game' if accepted else 'installed_game_unproved',
                'entry': entry['id'], 'version': entry['version'], 'project': name, 'project_dir': str(project.root),
                'proof': status, 'catalog': 'catalog.json', 'message': message}

    # ------------------------------------------------------------ pack / publish
    def is_project(self, name):
        root = self.settings.get('projects_root') or ''
        return bool(root) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name or '') is not None and \
            (Path(root) / name / '.maker/project.json').is_file()

    def recipe_for(self, ref, project, version, author, licence):
        """(recipe, author, licence, source) for a bundled asset, a project's game or a project's theme pack."""
        if project:
            return self.style_from_project(ref, project, licence, author)
        if self.is_project(ref):
            return self.game_from_project(ref, licence, author)
        recipe = hub_sources.recipe_by_id(ref, self.bundle) or hub_sources.single_recipe(ref, self.bundle)
        if recipe is None:
            fail('hub_not_found', 'Nothing to pack called %r: use a hub entry id, a catalog id (kit:furn.lamp, '
                 'character:polar_pod/tavi, sound:ui.select) or one of your games.' % ref[:64])
        if licence and licence != recipe['licence']:
            fail('hub_licence', 'Refused: %s is a bundled asset under %s and keeps that licence.' % (ref, recipe['licence']))
        if author and author != hub_sources.AUTHOR:
            fail('hub_entry', 'Refused: %s is a bundled asset by %s and keeps its author; pack your own game or theme pack '
                 'to publish under your name.' % (ref, hub_sources.AUTHOR))
        return recipe, hub_sources.AUTHOR, recipe['licence'], 'community'

    def style_from_project(self, pack_id, name, licence, author):
        from .packs import validate_pack
        project = self.service.project(name)
        rel = 'packs/%s/pack.json' % pack_id
        if not project.path(rel).is_file():
            fail('hub_not_found', '%s has no theme pack %r; list its packs with hermes64_packs project=%s.' % (name, pack_id, name))
        pack = validate_pack(project.read_json(rel))
        if (self.bundle / 'packs' / pack_id / 'pack.json').is_file():
            fail('hub_duplicate', 'Refused: %s is a bundled style already in the hub (style.%s); pack your own pack id.' % (pack_id, pack_id))
        recipe = {'id': 'style.' + pack_id.replace('-', '_'), 'kind': 'style', 'name': pack['name'][:60],
                  'summary': (pack['description'] or pack['name'])[:160], 'tags': hub_sources.clean_tags(['theme-pack', pack['kit_pack_id']]),
                  'licence': licence or RECOMMENDED['data'], 'style': pack['kit_pack_id'], 'files': {},
                  'generated': {}, 'blobs': {'pack.json': encode(pack)}, 'catalog_ids': [], 'thumb': None,
                  'palette': pack['palette'], 'tier': hub_sources.tier('data-checked', style='pack data validated (not a render)')}
        return recipe, author or 'Hermes64 creator', recipe['licence'], 'community'

    def game_from_project(self, name, licence, author):
        from .adapters import Components
        from .packs import Packs
        from .service import source_guard
        project = self.service.project(name)
        with project.lock():
            current = self.service.current(project) if project.path('.maker/current.json').is_file() else None
            spec = source_guard(project.read_json(current['spec'] if current else 'source/spec.json'))
            pack = Packs(self.settings, project).selected(spec)
            blobs = {'source/spec.json': encode(spec), 'packs/%s/pack.json' % pack['id']: encode(pack)}
            if project.path('catalog.json').is_file():
                blobs['catalog.json'] = project.path('catalog.json').read_bytes()
            hub_root = project.path('assets/hub')
            if hub_root.is_dir():
                for path in sorted(hub_root.rglob('*')):
                    if path.is_file():
                        blobs[path.relative_to(project.root).as_posix()] = path.read_bytes()
            proof = 'not run (no compiled build)'
            if current:
                folder = self.service.folder(project, 'hub-pack')
                proof = proof_label(Components(self.settings, project).check(current['game'], folder + '/proof.json')['status'], spec)
        media = any(hub_archive.kind_of(p)[0] in MEDIA for p in blobs)
        title = spec.get('title') if isinstance(spec.get('title'), str) and spec.get('title').strip() else name
        summary = spec.get('description') if isinstance(spec.get('description'), str) and spec.get('description').strip() else title
        recipe = {'id': 'game.' + name.replace('-', '_'), 'kind': 'game', 'name': title[:60],
                  'summary': ('%s (%d rooms, story %s).' % (summary.rstrip('.'), len(spec.get('rooms', [])), spec['contract_version']))[:160],
                  'tags': hub_sources.clean_tags(['game', 'community', pack['kit_pack_id'], pack['id']]),
                  'licence': licence or (RECOMMENDED['assets'] if media else RECOMMENDED['data']), 'style': pack['kit_pack_id'],
                  'files': {}, 'generated': {'AUTHORING.md': 'Author source with Hermes64 tools. Compile and check after every edit.\n'},
                  'blobs': blobs, 'catalog_ids': [], 'thumb': None, 'story': spec['contract_version'],
                  'tier': hub_sources.tier('proved' if proof == 'proved' else 'validated' if 'accepted' in proof else 'draft',
                                           proof=proof[:80], style='not run')}
        return recipe, author or 'Hermes64 creator', recipe['licence'], 'community'

    def pack(self, ref, project=None, version=None, author=None, licence=None):
        version = version or hub_sources.VERSION
        recipe, author, licence, source = self.recipe_for(ref, project, version, author, licence)
        if hub_index.EMAIL.search(author or ''):
            fail('hub_entry', 'Use a name, not an email address, as the author.')
        recipe = dict(recipe, licence=licence)
        blob, entry = hub_sources.build(recipe, self.bundle, version=version, author=author, source=source)
        report = hub_archive.validate(blob, entry)
        for path, data in text_files(report['contents']):
            match = PRIVATE.search(data)
            if match:
                fail('hub_private', 'Refused to pack %s: %s contains private data (%s...); remove home-folder paths, email '
                     'addresses and internal names, then pack again.' % (entry['id'], path, match.group(0)[:24].decode('utf-8', 'replace')))
        entry.pop('preview', None)
        entry.pop('preview_source', None)
        entry['download'] = '%s-%s.zip' % (entry['id'], version)
        folder = self.work(create=True) / 'packs'
        folder.mkdir(parents=True, exist_ok=True)
        zip_path, entry_path = folder / entry['download'], folder / ('%s-%s.json' % (entry['id'], version))
        if entry_path.is_file():
            old = strict_json(entry_path.read_bytes())
            if old.get('sha256') != entry['sha256']:
                fail('hub_duplicate', 'Refused: you already packed %s %s with different contents; pack it again with a new '
                     'version, e.g. version=%s.' % (entry['id'], version, self.bump(version)))
        zip_path.write_bytes(blob)
        entry_path.write_bytes(pretty(entry))
        message = ('Packed %s (%s %s): %d files, %s, sha256 %s…, licence %s.\nArchive: %s\nNext: /hermes64 hub publish %s' % (
            entry['name'], entry['id'], version, len(entry['files']), human_size(entry['size']), entry['sha256'][:12],
            licence, zip_path, entry['id']))
        return {'ok': True, 'status': 'packed', 'entry': entry['id'], 'version': version, 'archive': str(zip_path),
                'entry_path': str(entry_path), 'sha256': entry['sha256'], 'message': message}

    @staticmethod
    def bump(version):
        major, minor, patch = version_tuple(version) or (1, 0, 0)
        return '%d.%d.%d' % (major, minor, patch + 1)

    def publish(self, ref, version=None):
        rows = [row for row in self.local() if row[0]['id'] == ref and (version is None or row[0]['version'] == version)]
        if not rows:
            fail('hub_not_packed', 'Nothing packed as %r yet; run /hermes64 hub pack %s first.' % (ref[:64], ref[:64]))
        entry, base, _label = max(rows, key=lambda row: version_tuple(row[0]['version']))
        report = self.verified(entry, base)
        name = '%s-%s' % (entry['id'], entry['version'])
        draft = self.work() / 'drafts' / name
        blob = (Path(base) / entry['download']).read_bytes()
        files = {name + '.zip': blob, 'entry.json': pretty(dict(entry, download=name + '.zip')),
                 'README.md': report['contents']['README.md'], 'PR.md': self.pr_text(entry, report).encode('utf-8')}
        if draft.is_dir():
            same = all((draft / f).is_file() and (draft / f).read_bytes() == d for f, d in files.items())
            if not same:
                fail('hub_duplicate', 'Refused: a different publish draft for %s already exists at %s; pack a new version first.'
                     % (name, draft))
        else:
            draft.mkdir(parents=True)
            for fname, data in files.items():
                (draft / fname).write_bytes(data)
        message = ('Publish draft ready: %s\nIt holds entry.json, %s.zip, README.md and PR.md. Nothing was uploaded.\n'
                   'To share it: fork the Hermes64 Hub registry, copy this folder into drafts/, and open a pull request with '
                   'PR.md as the description.' % (draft, name))
        return {'ok': True, 'status': 'draft_ready', 'entry': entry['id'], 'version': entry['version'], 'draft': str(draft),
                'files': sorted(files), 'message': message}

    @staticmethod
    def pr_text(entry, report):
        rows = '\n'.join('| `%s` | %d | `%s` |' % (f['path'], f['bytes'], f['sha256']) for f in entry['files'])
        tier = entry['tier']
        return '\n'.join([
            '# Add %s (`%s` %s) to the Hermes64 Hub' % (entry['name'], entry['id'], entry['version']), '',
            '- Kind: %s · Licence: %s · Author: %s' % (entry['kind'], entry['licence'], entry['author']),
            '- Archive: `%s-%s.zip`, %d bytes, sha256 `%s`' % (entry['id'], entry['version'], entry['size'], entry['sha256']),
            '- Made for: %s · Hub contract %s · Hermes64 %s%s' % (entry['compat']['style'], entry['compat']['contract'],
                                                              entry['compat']['plugin'],
                                                              ' · rig ' + entry['compat']['rig'] if entry['compat'].get('rig') else ''),
            '', '## What it is', '', entry['summary'], '',
            '## Checks already run by `/hermes64 hub publish`', '',
            '- [x] Data-only archive (json, glb, png, wav, ogg, md, txt): no scripts, programs, links or nested archives',
            '- [x] Every file listed in HUB.json with its sha256; the archive hash matches entry.json',
            '- [x] Licence %s is on the hub allow-list' % entry['licence'],
            '- [x] Models within budget (largest: %d triangles)' % report['tris_max'],
            '- [x] No home-folder paths, email addresses or internal names in text files', '',
            '## Verification tier (honest, not upgraded)', '',
            '- Label: %s; proof: %s; playtest: %s; style: %s; human: %s' % (
                tier['label'], tier['proof'], tier['playtest'], tier['style'], tier['human']), '',
            '## For the maintainer', '',
            '- [ ] `python3 -B -m tools.hub add-draft drafts/%s-%s --registry hub`' % (entry['id'], entry['version']),
            '- [ ] `python3 -B -m tools.hub check` stays green', '- [ ] Licence and provenance look right; preview added if available', '',
            '## Files', '', '| path | bytes | sha256 |', '|---|---:|---|', rows, '',
            'I confirm I have the right to share these files under %s.' % entry['licence'], ''])

    # ------------------------------------------------------------ dispatch
    def run(self, action, args):
        if action == 'search':
            return self.search(args.get('query', ''), args.get('kind'))
        if not args.get('id'):
            fail('arguments', 'hub %s needs an id, e.g. /hermes64 hub %s style.polar_pod.' % (action, action))
        if action == 'info':
            return self.info(args['id'])
        if action == 'install':
            return self.install(args['id'], args.get('project'))
        if action == 'pack':
            return self.pack(args['id'], args.get('project'), args.get('version'), args.get('author'), args.get('licence'))
        return self.publish(args['id'], args.get('version'))


def failure(exc, prefix=''):
    if isinstance(exc, Fault):
        return {'ok': False, 'error': {'code': exc.code, 'message': one_line(prefix + str(exc))[:1000]}}
    return {'ok': False, 'error': {'code': 'hub_internal', 'message': one_line(
        'Something went wrong in the hub (%s: %s); nothing was changed that a retry cannot fix.' % (type(exc).__name__, str(exc)[:300]))}}


def run_tool(settings, args, data_root=None, games_root=None):
    try:
        if not isinstance(args, dict):
            fail('arguments', 'Arguments must be an object with an action.')
        validate(args, HUB_SCHEMA)
        result = Hub(settings, data_root, games_root).run(args['action'], args)
        return json.dumps(result, ensure_ascii=False, sort_keys=True)
    except Exception as exc:   # every refusal is one line of JSON; never a fabricated success
        return json.dumps(failure(exc), ensure_ascii=True)


def parse(raw):
    """`hub <action> ...` -> (action, args). key=value / --key value options; quotes allowed."""
    try:
        from .platforms import split_args
        tokens = split_args(raw or '')
    except ValueError:
        fail('arguments', 'A quote is not closed; try /hermes64 hub search cat.')
    if not tokens or tokens[0].lower() in ('help', '-h', '--help'):
        return 'help', {}
    action, rest = tokens[0].lower(), tokens[1:]
    if action not in ACTIONS:
        fail('arguments', 'Unknown hub action %r; use search, info, install, pack or publish.' % action[:20])
    args, positional, index = {'action': action}, [], 0
    while index < len(rest):
        token = rest[index]
        key, _, value = token.partition('=')
        key = key.lstrip('-').lower()
        if token.startswith('--') and not value and key in ('version', 'author', 'licence', 'license', 'kind', 'project'):
            if index + 1 >= len(rest):
                fail('arguments', '%s needs a value.' % token)
            value, index = rest[index + 1], index + 1
        if value and key in ('version', 'author', 'licence', 'license', 'kind', 'project', 'game'):
            args[{'license': 'licence', 'game': 'project'}.get(key, key)] = value
        else:
            positional.append(token)
        index += 1
    if action == 'search':
        if positional and 'kind' not in args and hub_index.KIND_WORDS.get(positional[-1].lower()):
            args['kind'] = hub_index.KIND_WORDS[positional[-1].lower()]
            positional = positional[:-1]
        if positional:
            args['query'] = ' '.join(positional)[:200]
    else:
        if positional:
            args['id'] = positional[0]
        if len(positional) > 1 and 'project' not in args:
            args['project'] = positional[1]
        if len(positional) > 2:
            fail('arguments', 'Too many words after hub %s; use /hermes64 hub %s <id> [game].' % (action, action))
    return action, args


def command(ctx, raw):
    """Slash command text: compact plain lines, or one plain-English failure line."""
    from .plugin_settings import default_games_root, default_hub_root, plugin_settings
    try:
        settings = plugin_settings(ctx, SETTINGS)
        action, args = parse(raw)
        if action == 'help':
            return HELP % (Path(settings.get('bundle_root') or ROOT) / 'hub/site/index.html')
        validate(args, HUB_SCHEMA)
        return Hub(settings, default_hub_root(ctx), default_games_root(ctx)).run(action, args)['message']
    except Exception as exc:
        return 'Hermes64 hub: ' + failure(exc)['error']['message']


def register_tools(ctx):
    """One compact tool; the handler validates against the full HUB_SCHEMA. No I/O at registration."""
    from .plugin_settings import default_games_root, default_hub_root, plugin_settings
    from .tools import available
    from . import wire

    def handler(args, **kwargs):
        return run_tool(plugin_settings(ctx, SETTINGS), args, default_hub_root(ctx), default_games_root(ctx))
    wire.register(ctx, 'hermes64_hub', SCHEMA, handler, available)
