"""One-command start: `/hermes64 new "<premise>" [style]` and hermes64_demo(premise=...).

Order: inputs, doctor, games folder, then the existing creation path (premise starter
template -> hermes64_scaffold -> hermes64_compile -> hermes64_check -> hermes64_build_assets),
a short headless bot playtest, the play runtime, the style audit (when a window can open), a
proof badge, a game card (project.json) and the exact command to play.
Every refusal is one plain-English line with the next step, and nothing is created until
the inputs and the required tools pass. The premise is data: it is never executed.
"""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time

from .safety import Fault, fail
from .schemas import ID, obj, text, validate
from .runner import locate
from .templates import premise_spec
from . import badge as badges
from .creation_reply import reply_notes

MAX_PREMISE = 300
NAME = re.compile(r'[a-z][a-z0-9_-]{0,63}')
# Friendly style names and pack IDs -> bundled pack.
STYLES = {'village': 'n64_v0', 'harbor': 'n64_v0', 'harbour': 'n64_v0', 'classic': 'n64_v0', 'n64': 'n64_v0',
          'n64_v0': 'n64_v0', 'forest': 'forest_village', 'woods': 'forest_village', 'forest_village': 'forest_village',
          'polar': 'polar_pod', 'snow': 'polar_pod', 'ice': 'polar_pod', 'scifi': 'polar_pod', 'sci-fi': 'polar_pod',
          'polar_pod': 'polar_pod'}
STYLE_NAMES = {'n64_v0': 'village', 'forest_village': 'forest', 'polar_pod': 'polar'}
# MERGE6: explicit genre ids only; preserve legacy aliases and automatic premise matching.
from .genre_kits import PACKS as GENRE_PACKS
STYLES.update({pid: pid for pid in GENRE_PACKS})
STYLE_NAMES.update({pid: row['name'] for pid, row in GENRE_PACKS.items()})
STYLE_CHOICES = 'village, forest or polar; genre pack ids: ' + ', '.join(GENRE_PACKS)
# Premise words -> pack, in tie-break priority order. Most hits wins; no hit -> DEFAULT_PACK.
KEYWORDS = (
    ('polar_pod', {'snow', 'ice', 'icy', 'frozen', 'freeze', 'polar', 'arctic', 'antarctic', 'glacier', 'winter',
                   'blizzard', 'frost', 'cold', 'thaw', 'aurora', 'penguin', 'space', 'station', 'pod', 'habitat',
                   'lab', 'laboratory', 'robot', 'android', 'future', 'futuristic', 'sci-fi', 'scifi', 'expedition',
                   'orbit', 'starship', 'moon', 'mars'}),
    ('forest_village', {'forest', 'woods', 'wood', 'woodland', 'tree', 'meadow', 'farm', 'garden', 'village',
                        'cottage', 'mill', 'orchard', 'mushroom', 'fox', 'deer', 'owl', 'grove', 'hollow', 'glade'}),
    ('n64_v0', {'harbor', 'harbour', 'lighthouse', 'sea', 'ocean', 'boat', 'ship', 'ferry', 'pier', 'dock', 'port',
                'coast', 'island', 'fisher', 'fishing', 'lantern', 'storm', 'fog', 'tide', 'beach', 'bay', 'keeper'}),
)
DEFAULT_PACK = 'n64_v0'
# Public bundled cast (bindings.json character_id) for the player and the starter's inhabitant.
CAST = {'n64_v0': ('fv_scribe', 'fv_warden'), 'forest_village': ('fv_scribe', 'fv_warden'),
        'polar_pod': ('new_arrival', 'tavi')}
CAST.update({pid: row['cast'] for pid, row in GENRE_PACKS.items()})
COLLECTIBLE_ASSET = 'prop.key'
PLAYTEST = {'mode': 'both', 'seconds': 10, 'seed': 7}
ASSET_SEED = 7   # the seed the audit's own `next` uses for hermes64_build_assets
NEW_SCHEMA = obj({'project': ID, 'premise': text(6000), 'style': text(64)}, ['premise'])
STOP = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'for', 'and', 'or', 'its', 'his', 'her', 'their', 'my', 'your',
        'at', 'by', 'with', 'from', 'into', 'who', 'that', 'this', 'is', 'are', 'was', 'be', 'as', 'it', 'must',
        'has', 'have', 'will', 'can', 'after', 'before', 'over', 'under'}
QUOTES = {'"': '"', "'": "'", '“': '”', '‘': '’'}  # straight and curly quotes
EXAMPLE = '/hermes64 new "A fox searches the village for its lost lantern"'


def one_line(message):
    return ' '.join(str(message).split())


def words(value):
    return re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', value.lower())


def normalize_premise(premise):
    if not isinstance(premise, str) or not premise.strip():
        fail('new_premise_empty', 'Give a one-sentence premise, e.g. ' + EXAMPLE + '.')
    clean = ''.join(ch for ch in ' '.join(premise.split()) if ch.isprintable())
    if not clean or not any(ch.isalnum() for ch in clean):
        fail('new_premise_empty', 'Give a one-sentence premise, e.g. ' + EXAMPLE + '.')
    if len(clean) > MAX_PREMISE:
        fail('new_premise_long', 'That premise is %d characters; keep it to one sentence under %d characters and try again.'
             % (len(clean), MAX_PREMISE))
    return clean


def pick_style(premise, style=None):
    """(pack, reason). An explicit style must be known; otherwise premise keywords decide."""
    if isinstance(style, str) and style.strip():
        pack = STYLES.get(style.strip().lower().replace(' ', '_'))
        if pack is None:
            fail('new_style', 'Unknown style %r; choose %s (or a pack id: n64_v0, forest_village, polar_pod).'
                 % (one_line(style)[:40], STYLE_CHOICES))
        return pack, 'chosen'
    if style not in (None, ''):
        fail('new_style', 'Style must be a word: ' + STYLE_CHOICES + '.')
    tokens = words(premise)
    best, hits = DEFAULT_PACK, []
    for pack, keys in KEYWORDS:
        found = [w for w in tokens if w in keys or (w.endswith('s') and w[:-1] in keys)]
        if len(found) > len(hits):
            best, hits = pack, found
    if not hits:
        from .brief import from_prompt
        asked = from_prompt(premise)
        defaults = json.loads((Path(__file__).resolve().parents[1] / 'kits/template-fallbacks.json').read_text(encoding='utf-8'))
        genre = asked['setting']['genre']
        candidate = defaults['brief_genres'].get(genre)
        if candidate in STYLES:
            # REUSE: say whether the palette was asked for or only assumed by the keyword fallback, and what is missing.
            assumed = any(str(note).startswith('palette: no colour words') for note in asked.get('assumptions', []))
            palette = ('the %s default %s palette (assumed: you named no colours)' % (genre, asked['palette_mood']['dominant'])
                       if assumed else 'the %s palette you asked for' % asked['palette_mood']['dominant'])
            return candidate, ('auto: brief fallback (no style words) read this as %s, so the shipped %s look; %s is not '
                               'applied and no new pieces were generated: this build has no mood packs or asset generators. '
                               'For another look add a style word: village, forest, polar or a pack id'
                               % (genre, candidate, palette))
        return best, 'auto: no style words in the premise, so the default'
    return best, 'auto: matched ' + ', '.join('"%s"' % w for w in dict.fromkeys(hits))


def slug(premise):
    content = [w for w in words(premise) if w not in STOP] or ['game']
    name = '-'.join(content[:4])[:40].strip('-')
    if not NAME.fullmatch(name):
        name = ('game-' + name)[:40].strip('-')
    return name if NAME.fullmatch(name) else 'game'


def check_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        fail('new_name', 'Project name %r is not allowed; use a short lowercase name like fox-lantern '
             '(letters, digits, - or _), not a path.' % one_line(name)[:60])
    return name


MAX_SUFFIX = 99
KINDS = {'game': 'a Hermes64 game', 'source': 'a Hermes64 project that was scaffolded but never compiled',
         'folder': 'a folder that is not a Hermes64 project'}


def candidate_names(base):
    """REUSE: the names a new game may take, in order: ``base``, then ``base-2`` ... ``base-99`` (trimmed to fit)."""
    yield base
    for number in range(2, MAX_SUFFIX + 1):
        tail = '-%d' % number
        yield base[:64 - len(tail)].rstrip('-_') + tail


def taken(root, name):
    path = Path(root) / name
    return path.exists() or path.is_symlink()


def describe_existing(root, name):
    """What already holds ``name`` in ``root``: its real folder (on a case-insensitive disk a folder made in Finder may
    differ in case), whether it is a Hermes64 game, a scaffolded source or another folder, and when it was made.
    Read-only (REUSE)."""
    root = Path(root)
    path = root / name
    try:
        entries = os.listdir(root)
    except OSError:
        entries = []
    if name not in entries:
        path = root / next((entry for entry in sorted(entries) if entry.lower() == name), name)
    kind = 'folder'
    if (path / '.maker' / 'project.json').is_file():
        kind = 'game' if (path / '.maker' / 'current.json').is_file() else 'source'
    made = None
    for rel in ('.maker/new.json', 'project.json', '.maker/project.json', ''):
        try:
            made = time.strftime('%Y-%m-%d %H:%M', time.localtime((path / rel).stat().st_mtime))
            break
        except OSError:
            continue
    return {'name': path.name, 'project_dir': str(path), 'kind': kind, 'made': made}


def continue_line(info):
    """One clause: how to carry on with what already holds a name."""
    if info['kind'] == 'game':
        return 'continue it with hermes64_check, hermes64_edit or hermes64_playtest (project=%s)' % info['name']
    if info['kind'] == 'source':
        return 'continue it with hermes64_compile (project=%s, spec_path=source/spec.json)' % info['name']
    return 'it was left untouched'


def existing_line(info):
    """'<folder> (a Hermes64 game, made 2026-11-10 14:02)': the earlier project, named plainly."""
    return '%s (%s%s)' % (info['project_dir'], KINDS[info['kind']], ', made ' + info['made'] if info['made'] else '')


def reserve(service, root, base, spec_for, pack, stages):
    """Scaffold the new game under the first free name: ``base``, ``base-2``, ``base-3`` ... (REUSE). A name that is
    already taken is never reused or written into, and two creates racing for one name cannot both get it: the folder
    is made atomically (safety.Project) and the loser moves on to the next name. Returns (name, taken names)."""
    begin = time.monotonic()
    names = []
    for candidate in candidate_names(base):
        if taken(root, candidate):
            names.append(candidate)
            continue
        result = json.loads(service.handle('hermes64_scaffold', {'project': candidate, 'pack': pack,
                                                                 'spec_json': json.dumps(spec_for(candidate))}))
        error = result['error'] if isinstance(result.get('error'), dict) else {}
        if result.get('ok'):
            stages.append({'stage': 'scaffold', 'seconds': round(time.monotonic() - begin, 3), 'status': result['status']})
            return candidate, names
        if error.get('code') == 'exists':      # another create took it between the check and the scaffold
            names.append(candidate)
            continue
        stages.append({'stage': 'scaffold', 'seconds': round(time.monotonic() - begin, 3), 'status': error.get('code')})
        where = (' The half-made project stays at %s; inspect it, or pass --name to start fresh.' % (root / candidate)
                 if taken(root, candidate) else ' Nothing was created.')
        fail('new_scaffold', 'Scaffold failed: %s.%s' % (one_line(error.get('message', result.get('status')))[:300], where))
    raise Fault('new_exists', 'Games named %s through %s already exist in %s; pick a new name with --name <new-name> '
                '(or project=...). Nothing was created.' % (base, names[-1], root))


def plain_reason(reason, project, tested, pack):
    """A playtest reason in plain words: 'missing_assets: 1' also names the piece and why it is missing (REUSE)."""
    if not re.fullmatch(r'missing_assets: \d+', reason):
        return reason
    try:
        refs = [str(ref) for ref in project.read_json(tested['report_path']).get('missing_assets') or []]
    except (Fault, OSError, ValueError, KeyError):
        refs = []
    what = ', '.join(refs[:3]) + (' and %d more' % (len(refs) - 3) if len(refs) > 3 else '') if refs else 'a piece'
    return ('%s (%s %s no model in the %s style, so the game draws a placeholder box there; kit/pack work, not your '
            'premise)' % (reason, what, 'has' if len(refs) <= 1 else 'have', pack))


def title_for(premise):
    value = premise.rstrip(' .!?')
    if len(value) > 60:
        value = value[:57].rsplit(' ', 1)[0].rstrip(' ,;:') + '...'
    return value[:1].upper() + value[1:]


def preflight(settings):
    """Doctor before creating anything: plain-English fixes; Blender is optional."""
    from . import platforms
    if platforms.is_windows():
        if not platforms.windows_runner_enabled():
            fail('new_platform', platforms.isolation('win32')['note'] + ' Nothing was created.')
    elif platforms.host() == 'linux':
        iso = platforms.isolation('linux')
        if not iso['available']:
            fail('new_platform', iso['note'] + ' Nothing was created.')
    elif sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        fail('new_platform', 'Hermes64 makes games on macOS (built-in sandbox-exec) and, after an opt-in, on Windows; '
             'this computer has neither, so nothing was created.')
    from .doctor import godot_help
    notes = {}
    for tool, label, fix in (
            ('python', 'Python 3.9+', 'install Python 3 or set python_path in the hermes64 plugin settings'),
            ('godot', 'Godot 4.6.2', None)):
        configured = settings.get(tool + '_path', '') or ''
        try:
            notes[tool] = locate(tool, configured)
        except Fault:
            if tool == 'godot':      # the doctor's one message: exact version, where to get it, per-OS steps
                fail('new_godot', godot_help(configured) + ' Then try again; nothing was created.')
            where = ' at the configured %s_path %r' % (tool, configured[:240]) if configured else ''
            fail('new_' + tool, "%s wasn't found%s; %s, then try again. Nothing was created." % (label, where, fix))
    try:
        notes['blender'] = locate('blender', settings.get('blender_path', '') or '')
    except Fault:
        notes['blender'] = None
    return notes


def resolve_root(settings, default_root):
    """(root, uses_default). A configured projects_root wins; else the profile's default games folder."""
    configured = settings.get('projects_root') or ''
    if configured:
        path = Path(configured)
        if not path.is_absolute() or not path.is_dir():
            fail('new_root', 'projects_root %r is not an existing absolute folder; fix it in the hermes64 plugin settings '
                 'or clear it to use the default games folder.' % configured[:200])
        return path, default_root is not None and path == Path(default_root)
    if default_root is None:
        fail('new_root', 'No games folder yet: set projects_root in the hermes64 plugin settings to an existing folder, then try again.')
    return Path(str(default_root)), True


def starter_spec(settings, premise, name, pack_id, template=None, slots=None, games_root=None):
    """Existing premise template, dressed with bundled public cast and a bound keepsake asset."""
    from .creation_reply import generic_prompt
    title_premise = premise
    if not slots:
        premise = generic_prompt(premise)
    from .packs import Packs
    pack = Packs(settings).get(pack_id)
    from . import templates, pack_rooms
    template = templates.pick_template(premise, explicit=template)[0]
    rooms = pack_rooms.load(settings, pack_id, games_root) if template == 'arena_run_v1' else None
    bundle = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    combat2 = ((bundle / 'contracts/gameplay/1.2.0/manifest.json').is_file()
               and (bundle / 'runtime/godot/modules/combat/run.gd').is_file())
    spec = templates.build(template, premise, name, pack, rooms, slots, combat2=combat2)
    if rooms and rooms.get('source'):  # GAPS2: games-folder room data, recorded like the premise (path@sha256)
        spec['metadata']['rooms_source'] = rooms['source']
    if template == 'arena_run_v1':  # GAPS2 G3/G4/G9: story scenes, results, weather, npc clips, boss robot; no text boxes
        from .premise_apply import apply
        apply(spec, slots or {}, rooms)
    elif slots:
        spec['metadata'].setdefault('presentation', {})['text_boxes'] = bool(slots.get('text_boxes', False))
    spec['title'] = (slots or {}).get('title') or title_for(title_premise)
    bundle = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    path = bundle / 'bindings.json'
    rows = json.loads(path.read_text(encoding='utf-8')).get('characters', []) if path.is_file() else []
    cast = {row.get('character_id'): row for row in rows if isinstance(row, dict) and row.get('public_release')}
    player, local = CAST[pack_id]

    def bind(character, row):
        character.update(body_id=row['body_id'], base_rig_id=row['base_rig_id'], params=copy.deepcopy(row['params']))
        character['role_profiles'] = {role: copy.deepcopy(row['params']) for role in character['role_profiles']}

    if template == 'arena_run_v1':
        # CHARBIND: a binding that is no bundled public character names a project cast row (hermes64_character bind);
        # it is recorded in metadata.presentation.cast and applied when the runtime is staged, bundled body until then.
        project_cast = {}
        requested = (slots or {}).get('hero', {}).get('binding', player)
        if requested not in cast:
            project_cast[spec['characters'][0]['id']] = requested
        if player in cast:
            bind(spec['characters'][0], cast.get(requested, cast[player]))
        by_id = {c['id']: c for c in spec['characters']}
        for npc in (slots or {}).get('npcs', []):
            requested = npc.get('binding', local)
            if requested not in cast:
                project_cast[npc['id']] = requested
            if local in cast:
                bind(by_id[npc['id']], cast.get(requested, cast[local]))
        for row in (slots or {}).get('bosses', []) + (slots or {}).get('robots', []):
            if row.get('binding'):
                project_cast[row['id']] = row['binding']
        if project_cast:
            spec['metadata']['presentation']['cast'] = project_cast
            spec['metadata'].setdefault('template_pending', []).append(
                'binding %s (project cast, applied once bound with hermes64_character)' % ', '.join(sorted(set(project_cast.values()))))
    elif player in cast and local in cast:
        hero = {'id': 'traveller', 'name': 'Traveller', 'role': 'protagonist', 'role_profiles': {'protagonist': {}}}
        bind(hero, cast[player])
        bind(spec['characters'][0], cast[local])
        spec['characters'].insert(0, hero)
        spec['metadata']['protagonist'] = 'traveller'
        spec['collectibles'][0]['asset'] = (GENRE_PACKS[pack_id]['collectible']
                                             if pack_id in GENRE_PACKS else COLLECTIBLE_ASSET)
    if template == 'two_room_collect_v1':
        templates.name_starter(spec, premise, pack)
    spec['metadata']['created_by'] = 'hermes64 new'
    # UI5: new games show the keycap interact prompt and the corner controls hint (runtime/godot/input/keyhud.json);
    # games without this block (every existing golden/replay game) keep the legacy prompt and no hint.
    spec['metadata']['hud'] = {'interact_prompt': 'keycap', 'controls_hint': 'corner'}
    return spec


def create(settings, premise, style=None, name=None, default_root=None, story=None, scale=None):
    """Run the one-command start. Returns a result dict; raises Fault with a one-line message.

    REUSE: every call makes a NEW project. When the name (derived from the premise, or given) is already taken, the
    game gets the next free name (-2, -3 ...) and the reply names the earlier project, which is left unchanged; an
    earlier project is never reused, written into or reported as made. The result states ``created``,
    ``project_dir``, ``seconds`` and ``assets_built``. A Fault raised after this call made its folder carries
    ``created_dir`` (a half-made project of this call, never an earlier one)."""
    from .service import Service
    started = time.monotonic()
    stages = []
    premise = normalize_premise(premise)
    from . import brief as briefs
    try:
        asked = briefs.from_prompt(premise)
    except Fault:
        asked = None
    from .templates import pick_template
    from .premise_packs import resolve
    root, uses_default = resolve_root(settings, default_root)
    record = resolve(settings, premise, story=story, games_root=root)
    slots = record['data'] if record else {}
    if record:
        pack, reason = slots['style'], 'premise file ' + record['id']
        if style and pick_style(premise, style)[0] != pack:
            fail('premise_style', 'The story chooses %s; remove the conflicting style or edit your story file.' % pack)
    else:
        pack, reason = pick_style(premise, style)
    template, template_reason = pick_template(premise, explicit=slots.get('template'))
    base = slug(premise) if name in (None, '') else check_name(name)
    spec = starter_spec(settings, premise, base, pack, template, slots, games_root=root)
    # SCALE: room-scale dial (adventure_maker/room_scale.py). New games default to medium (about 4x the legacy floor
    # area); small keeps the legacy 4 x 4 m starter byte-identical; templates other than the starter keep their rooms.
    from . import room_scale
    scale, scale_reason = room_scale.pick(premise, explicit=scale, brief=asked, slots=slots)
    spec, scaled = room_scale.apply(spec, scale, pack, premise,
                                    Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1]))
    scaled['reason'] = scale_reason if scaled.get('applied') else scaled.get('reason', scale_reason)
    unapplied = list(spec['metadata'].get('template_pending', []))
    from .premise_apply import APPLIED  # GAPS2 G3: applied by arena_run_v1; audio slot names wait in the project
    applied = APPLIED if template == 'arena_run_v1' else ()
    unapplied += [key for key in ('moveset', 'scenes', 'textures', 'results', 'weather') if slots.get(key) and key not in applied]
    if spec.get('gameplay', {}).get('api_version') != '1.2.0':
        if any(key != 'max_health' for key in slots.get('run', {})):
            unapplied.append('run (except max_health)')
        if slots.get('finale', {}).get('attack_budget'):
            unapplied.append('finale.attack_budget')
        if len(slots.get('finale', {}).get('bosses', [])) > 1:
            unapplied.append('finale.bosses (sequential on legacy combat)')
    elif 'moveset' in unapplied:
        unapplied.remove('moveset')

    def spec_for(candidate):
        """The starter spec under one candidate project name, dressed with the story record and pending slots."""
        value = spec if candidate == base else starter_spec(settings, premise, candidate, pack, template, slots,
                                                             games_root=root)
        if candidate != base:   # SCALE: the same room-scale plan for a renamed project
            value = room_scale.apply(value, scale, pack, premise, Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1]))[0]
        if record:
            value['metadata']['premise'] = record['id'] + '@' + record['sha256']
        if unapplied:
            value['metadata']['template_pending'] = list(unapplied)
        return value

    spec_for(base)
    tools = preflight(settings)
    stages.append({'stage': 'doctor', 'seconds': round(time.monotonic() - started, 3), 'status': 'ready'})
    if uses_default:
        root.mkdir(parents=True, exist_ok=True)
    settings = dict(settings, projects_root=str(root))
    service = Service(settings)
    name, names = reserve(service, root, base, spec_for, pack, stages)
    earlier = dict(describe_existing(root, names[0]), also_taken=names[1:]) if names else None
    try:
        return finish(settings, service, root, uses_default, name, earlier, premise, asked, record, pack, reason,
                      template, template_reason, spec_for(name), unapplied, tools, stages, started, scaled)
    except Exception as exc:
        setattr(exc, 'created_dir', str(root / name))   # this call's own half-made folder, never an earlier project
        raise


def finish(settings, service, root, uses_default, name, earlier, premise, asked, record, pack, reason, template,
           template_reason, spec, unapplied, tools, stages, started, scaled=None):
    """Everything after the new project's source is scaffolded: compile, check, assets, playtest, play runtime, audit,
    badge, game card and the reply."""
    from .adapters import Components
    from . import playtest
    from . import brief as briefs
    from .doctor import BLENDER_NOTE, godot_version, other_godot
    from . import room_scale
    scaled = scaled or {'scale': 'small', 'applied': False, 'reason': 'not planned'}
    project = None
    slots = record['data'] if record else {}   # as in create(): GAPS2's audio-slot steps run here since REUSE's split

    def call(stage, tool, payload, required=True) -> dict:
        begin = time.monotonic()
        result: dict = json.loads(service.handle('hermes64_' + tool, dict(project=name, **payload)))
        if result.get('truncated') and result.get('report_path'):
            stored = service.project(name).read_json(result['report_path'])
            result = stored if isinstance(stored, dict) else result
        error: dict = result['error'] if isinstance(result.get('error'), dict) else {}
        stages.append({'stage': stage, 'seconds': round(time.monotonic() - begin, 3),
                       'status': result.get('status', error.get('code'))})
        if required and not result.get('ok'):
            where = (' The half-made project stays at %s; inspect it, or pass --name to start fresh.' % (root / name)
                     if (root / name).exists() else ' Nothing was created.')
            fail('new_' + stage, '%s failed: %s.%s' % (stage.capitalize(), one_line(error.get('message', result.get('status')))[:300], where))
        return result

    project = service.project(name)
    if slots.get('audio'):  # GAPS2 G3: assigned by hermes64_audio action=import once every named file is imported
        from .premise_apply import AUDIO_FILE, audio_doc
        project.write_json(AUDIO_FILE, audio_doc(record, slots['audio']))
    if asked is not None and not project.path('brief.json').exists():
        project.write_json('brief.json', asked)
    call('compile', 'compile', {'spec_path': 'source/spec.json'})
    checked = call('check', 'check', {}, required=False)
    # MERGE5: build the room shells/kit assets before the playtest, play runtime and style audit (an unbuilt game is
    # a cutaway void the audit can only fail). BFIX: blank builder = auto (plugin.yaml): Blender when found, else the
    # Python builder; an explicit builder is never switched, and no usable builder reads "NOT BUILT" with the fix.
    builder, why = asset_builder(settings, tools, numpy_probe(settings, project))
    if builder is None:
        stages.append({'stage': 'build_assets', 'seconds': 0.0, 'status': 'not_run'})
        assets = {'status': 'not_run', 'reason': why}
    else:
        built = call('build_assets', 'build_assets', {'seed': ASSET_SEED}, required=False)
        assets = {'status': 'passed' if built.get('ok') else 'failed', 'builder': builder,
                  'report_path': built.get('report_path') if built.get('ok') else None}
        if not built.get('ok'):
            assets['reason'] = one_line((built.get('error') or {}).get('message') or built.get('status'))[:300]
    with project.lock():
        begin = time.monotonic()
        tested = playtest.run(service, project, dict(PLAYTEST))
        stages.append({'stage': 'playtest', 'seconds': round(time.monotonic() - begin, 3), 'status': tested['status']})
        begin = time.monotonic()
        current = service.current(project)
        project.path('play').mkdir()
        Components(settings, project).prepare_runtime(current['game'], 'play')
        stages.append({'stage': 'play_runtime', 'seconds': round(time.monotonic() - begin, 3), 'status': 'prepared'})
        audited = quick_audit(service, project, stages)
        badge = badges.from_paths(proof=checked.get('report_path'), playtest=tested.get('report_path'), base=project.root,
                                  audit=audited['badge'], assets=assets,
                                  required_modules=[m['id'] for m in spec.get('gameplay', {}).get('modules', [])
                                                    if m['id'] in ('combat', 'course', 'regions')])
        argv = [tools['godot'], '--path', str(project.root / 'play' / 'runtime'), '--', '--pack=res://theme.json']
        from .platforms import command_line
        command = command_line(argv)
        paths = {'source': 'source/spec.json', 'current': '.maker/current.json', 'proof': checked.get('report_path'),
                 'playtest': tested['report_path'], 'playtest_html': tested['html_path'], 'play_runtime': 'play/runtime',
                 'game_card': 'project.json', 'receipt': '.maker/new.json'}
        if asked is not None:
            paths['brief'] = 'brief.json'
        if assets.get('report_path'):
            paths['assets'] = assets['report_path']
        if audited['result']:
            paths.update(style_audit=audited['result']['report_path'], contact_sheet=audited['result']['contact_sheet'])
        title = project.read_json('source/spec.json')['title']
        gversion = godot_version(tools['godot'])
        made_at = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        card = {'format': 'hermes64-game/1', 'name': name, 'title': title, 'premise': premise,
                'style': {'pack': pack, 'name': STYLE_NAMES[pack], 'reason': reason},
                'template': {'id': template, 'reason': template_reason},
                'proof_badge': badge, 'paths': paths, 'play': {'argv': argv, 'command': command},
                'doctor': {'python': tools['python'], 'godot': tools['godot'], 'godot_version': gversion,
                           'blender': tools['blender'] or 'not found. ' + BLENDER_NOTE},
                'made_at': made_at, 'earlier_project': earlier,
                'note': ('Game card written by /hermes64 new. It is not the portable source-project manifest '
                         '(contracts/project/1.0.0.json) and no tool reads it; the current build pointer is .maker/current.json.')}
        if asked is not None:
            card['brief'] = briefs.summary(asked)
        story_card = ({k: record[k] for k in ('id', 'sha256', 'reason')} if record else None)
        card['story'] = story_card
        card['rooms'] = room_scale.card(scaled)
        card['not_applied'] = unapplied
        project.write_json('project.json', card)
        ok = badge['ok']
        # REUSE: a taken name gave this game the next free one; say so, and name the earlier project (left unchanged).
        made = 'Made "%s" %sin %s' % (title, 'as new project %s ' % name if earlier else '', project.root)
        first = made + (' (default games folder)' if uses_default else '')
        if not ok:
            reasons = [plain_reason(r, project, tested, pack) for r in tested.get('reasons', [])
                       if isinstance(r, str)] if not tested.get('ok') else []
            if not reasons and assets['status'] != 'passed':
                reasons = ['room assets not built (%s); run hermes64_build_assets' % assets.get('reason', assets['status'])]
            if not reasons and audited['result'] and audited['result']['status'] == 'FAIL':
                reasons = [audited['result']['summary'] + '; run the style audit next steps (hermes64_check action=audit)']
            first = '%s, but it needs work: %s' % (made, (reasons or ['see the badge'])[0])
        style_line = 'Style: %s (%s), %s' % (STYLE_NAMES[pack], pack, reason)
        lines = [first, style_line, room_scale.summary_line(scaled), 'Badge: ' + badge['text'], 'Play: ' + command]
        notes = reply_notes(premise, asked, spec, template)
        lines.extend(notes)
        if template != 'two_room_collect_v1' or record:
            lines.insert(3, 'Template: %s (%s)' % (template, template_reason))
        if record:
            lines.insert(4, 'Story: %s (%s)' % (record['id'], record['reason']))
        if earlier:
            more = earlier['also_taken']
            lines.insert(1, 'Earlier: an earlier project with that name exists at %s; it was left unchanged%s.'
                         % (existing_line(earlier), ' (taken too: %s)' % ', '.join(more[:4]) if more else ''))
        if spec['metadata'].get('rooms_source'):
            lines.insert(len(lines) - 2, 'Rooms: your games folder ' + spec['metadata']['rooms_source'].split('@')[0])
        if slots.get('audio'):
            lines.append('Audio: the story names its music/voice slots; import the files with hermes64_audio action=import '
                         'and they are assigned (' + AUDIO_FILE + ')')
        if unapplied:
            lines.append('Not yet applied: ' + ', '.join(unapplied))
        if audited['result'] and audited['result'].get('contact_sheet'):
            lines.append('Style audit sheet: ' + str(project.root / audited['result']['contact_sheet']))
        if audited['result']:
            from .creation_reply import audit_details
            detail = audit_details(project.read_json(audited['result']['report_path']))
            if detail:
                lines.append(detail)
        engine = other_godot(gversion, tools['godot'], lead='Made and played with')
        if engine:
            lines.append('Godot: ' + engine + '.')
        from . import platforms
        if platforms.host() == 'linux' and platforms.isolation('linux')['mode'] == 'unconfined':
            lines.append('Runner: unconfined Linux runner by your HERMES64_LINUX_RUNNER=unconfined opt-in: no '
                         'OS-enforced network or write confinement; process-group kill and rlimits only.')
        if not tools['blender']:
            lines.append(blender_line(settings, assets))
        message = '\n'.join(lines)
        steps = list((audited['result'] or {}).get('next', []))
        if audited['result'] and audited['result']['status'] == 'FAIL' and not steps:
            # Widescreen can expose cutaway/kit defects with NO safe automatic edit.
            # Keep FAIL and say manual work is required, rather than return a dead end.
            steps.append({'tool': 'hermes64_check', 'args': {'project': name, 'action': 'audit', 'views': 1},
                          'why': 'Manual kit/framing work required; no automatic fix is available. Review the audit '
                                 'findings and re-audit after manual changes: ' + audited['result']['summary']})
        if assets['status'] != 'passed' and not any(s.get('tool') == 'hermes64_build_assets' for s in steps if isinstance(s, dict)):
            steps.insert(0, {'tool': 'hermes64_build_assets', 'args': {'project': name, 'seed': ASSET_SEED},
                             'why': 'build the room shells/kit assets (%s)' % assets.get('reason', assets['status'])})
        result = {'ok': ok, 'status': 'new_game_ready' if ok else 'new_game_needs_work', 'project': name,
                  'created': True, 'assets_built': assets['status'] == 'passed', 'earlier_project': earlier,
                  'made_at': made_at,
                  'style_audit': audited['line'], 'assets': assets, 'next': steps,
                  'project_dir': str(project.root), 'title': title, 'premise': premise,
                  'story': story_card, 'not_applied': unapplied, 'notes': notes,
                  'template': card['template'], 'style': card['style'], 'rooms': card['rooms'], 'badge': badge['text'],
                  'proof_badge': badge, 'play_command': command,
                  'play_argv': argv, 'paths': paths, 'default_games_folder': uses_default, 'stages': stages,
                  'seconds': round(time.monotonic() - started, 3), 'message': message}
        project.write_json('.maker/new.json', result)
    return result


def asset_builder(settings, tools, has_numpy=None):
    """(builder, None) when hermes64_build_assets can run, else (None, one plain line with the next step).

    The builder setting goes through builders.effective: absent or blank means auto, as plugin.yaml documents, so
    Blender builds the rooms when it is found and the Python builder when it is not. An explicit builder=blender stays
    strict (no fallback) and an explicit builder=python never uses Blender. Blender presence is the preflight lookup
    (tools['blender']), so the card's Blender line and the builder agree. The Python builder needs numpy in python_path
    (default: Hermes's own Python environment); ``has_numpy(exe)`` checks it before anything is built."""
    from .builders import effective, select
    try:
        builder = select(dict(settings, builder=effective(settings)), blender_present=bool(tools.get('blender')))
    except Fault as exc:
        return None, one_line(exc)[:200]
    if builder == 'blender' and not tools.get('blender'):
        return None, 'Blender not found; install Blender or set builder to auto with a numpy Python'
    if builder == 'python' and has_numpy is not None and not has_numpy(tools.get('python')):
        from .setup_check import numpy_command
        return None, ('the Python room builder needs numpy, which %s cannot import; next step: %s'
                      % (tools.get('python'), numpy_command(tools.get('python'))))
    return builder, None


def numpy_probe(settings, project):
    """``has_numpy(exe)`` for asset_builder: one `import numpy` in the same sandbox the builds use (no network,
    writes confined to the new game's folder), under the game's lock."""
    from .adapters import Components

    def has_numpy(exe):
        if not exe:
            return False
        try:
            with project.lock():
                result = Components(settings, project).runner.run([exe, '-I', '-B', '-c', 'import numpy'], project.root,
                                                                  timeout=30)
        except (Fault, OSError):
            return False
        return result.get('returncode') == 0
    return has_numpy


def blender_line(settings, assets):
    """The card's closing line when Blender was not found: what built the rooms, or what would."""
    from .builders import effective
    if effective(settings) == 'blender':
        return ('Optional: Blender not found; your builder=blender setting needs it. Clear builder (the default is auto) '
                'to build room models with the Python builder instead.')
    if assets.get('builder') == 'python' and assets.get('status') == 'passed':
        return ('Optional: Blender not found; it is not needed: the Python builder made the room models (builder=%s).'
                % effective(settings))
    return ('Optional: Blender not found; it is not needed once the Python builder can run (builder=auto needs numpy in '
            'python_path).')


def quick_audit(service, project, stages):
    """Style audit after the playtest when a real window can open; otherwise an honest 'not run (no display)'."""
    from . import audit
    begin = time.monotonic()
    available, why = audit.display_available()
    if not available:
        stages.append({'stage': 'audit', 'seconds': round(time.monotonic() - begin, 3), 'status': 'not_run'})
        return {'line': 'style audit: not run (no display)', 'result': None,
                'badge': {'status': 'not_run', 'rendered': False, 'not_run_reason': 'no display'}}
    try:
        result = audit.run(service, project, {'views': 1})
    except Fault as exc:
        stages.append({'stage': 'audit', 'seconds': round(time.monotonic() - begin, 3), 'status': 'not_run'})
        return {'line': 'style audit: not run (%s)' % one_line(exc)[:160], 'result': None,
                'badge': {'status': 'not_run', 'rendered': False, 'not_run_reason': 'render failed'}}
    stages.append({'stage': 'audit', 'seconds': round(time.monotonic() - begin, 3), 'status': result['status']})
    return {'line': result['summary'], 'result': result, 'badge': result['report_path']}


def parse(raw, include_story=False, include_scale=False):
    """Quoted premise and optional style/name/story (and room scale: a small/medium/large/open word after the quoted
    premise, or scale=...); legacy callers retain their three-tuple."""
    value = (raw or '').strip()
    premise, style, name, story, scale, positional = None, None, None, None, None, []
    if value[:1] in QUOTES:
        end = value.find(QUOTES[value[0]], 1)
        if end < 0:
            fail('new_quote', 'The premise is missing its closing quote; try ' + EXAMPLE + '.')
        premise, value = value[1:end], value[end + 1:]
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    lexer.escape = ''  # paths and premise text keep literal backslashes (including Windows paths)
    if premise is None:
        lexer.quotes = '"'  # an apostrophe in an unquoted sentence is text, not an opening quote
    try:
        tokens = list(lexer)
    except ValueError:
        fail('new_quote', 'An option is missing its closing quote; use --name fox-lantern.')
    index = 0
    while index < len(tokens):
        token = tokens[index]
        key, _, inline = token.partition('=')
        options = ('style', 'name', 'story') + (('scale',) if include_scale else ())
        if token in tuple('--' + o for o in options):
            if index + 1 >= len(tokens):
                fail('new_option', token + ' needs a value, e.g. ' + token + ' polar.')
            key, inline, index = token[2:], tokens[index + 1], index + 1
        elif key.lstrip('-') in options and key in options + tuple('--' + o for o in options) and inline:
            key = key.lstrip('-')
        else:
            key = None
        if key == 'scale':
            scale = inline
        elif key == 'style':
            style = inline
        elif key == 'name':
            name = inline
        elif key == 'story':
            story = inline
        else:
            positional.append(token)
        index += 1
    if premise is None:
        premise = ' '.join(positional)
        positional = []
    elif include_scale and scale is None and positional and positional[-1].lower() in ('small', 'medium', 'large', 'open'):
        scale = positional.pop()
    if positional:
        if len(positional) > 1 or style is not None:
            fail('new_extra', 'Unexpected text after the premise (%r); use ' % one_line(' '.join(positional))[:60]
                 + EXAMPLE + ' polar.')
        style = positional[0]
    if story is not None and not include_story:
        fail('new_option', 'Story options require the story-aware command path.')
    if include_scale:
        return premise, style, name, story, scale
    return (premise, style, name, story) if include_story else (premise, style, name)


def failure(exc):
    if isinstance(exc, ModuleNotFoundError) and exc.name in ('numpy', 'PIL'):
        return {'ok': False, 'error': {'code': 'new_dependency', 'message':
            'The Python running Hermes cannot import %s. Use a Hermes Python with that dependency available '
            'before retrying; python_path is the separate build Python, so its setup check does not check this interpreter.' % exc.name}}
    if isinstance(exc, Fault):
        return {'ok': False, 'error': {'code': exc.code, 'message': one_line(exc)[:1000]}}
    return {'ok': False, 'error': {'code': 'new_internal', 'message': one_line(
        'Something went wrong (%s: %s); try again, or run /hermes64 for help.' % (type(exc).__name__, str(exc)[:300]))}}


def run_tool(settings, args, default_root=None):
    """hermes64_demo with a premise. Friendly checks run before the strict schema check. Every reply states
    ``created`` (whether this call made a new project folder; never true for an earlier one), ``project_dir``,
    ``seconds`` and ``assets_built`` (REUSE)."""
    started = time.monotonic()
    try:
        if not isinstance(args, dict):
            fail('arguments', 'Arguments must be an object with a premise.')
        normalize_premise(args.get('premise'))
        if 'example' in args or 'seed' in args:
            fail('new_extra', 'Use premise for a new game or example for a bundled demo, not both.')
        pick_style(args.get('premise', ''), args.get('style'))
        if args.get('project') not in (None, ''):
            check_name(args['project'])
        validate(args, NEW_SCHEMA)
        result = create(settings, args['premise'], args.get('style'), args.get('project'), default_root)
        return json.dumps(result, ensure_ascii=True, sort_keys=True)
    except Exception as exc:  # every refusal is one line of JSON; never a fabricated success
        made = getattr(exc, 'created_dir', None)
        return json.dumps(dict(failure(exc), created=bool(made), project_dir=made, assets_built=False,
                               seconds=round(time.monotonic() - started, 3)), ensure_ascii=True)


def split_create(raw):
    """A leading `--create` routes `/hermes64 new` to the create flow (brief, mood, gap report, generated pieces,
    dressed rooms, honest report): adventure_maker/create_flow.py. Anything else is the classic starter path."""
    value = (raw or '').strip()
    if value == '--create' or value.startswith('--create '):
        return True, value[len('--create'):].strip()
    return False, raw


def command(ctx, raw):
    """Slash command text: the four-line success summary, or one plain-English failure line."""
    from .tools import SETTINGS
    from .plugin_settings import default_games_root
    try:
        settings = {key: ctx.get_config(key, '') for key in SETTINGS}
        create_mode, raw = split_create(raw)
        if create_mode:     # FINALINT2: a trailing small/medium/large/open word is the room scale, not a style
            premise, style, name, _story, scale = parse(raw, include_scale=True)
            from .create_flow import command_create
            return command_create(settings, premise, style, name, default_games_root(ctx), scale=scale)
        premise, style, name, story, scale = parse(raw, include_story=True, include_scale=True)
        return create(settings, premise, style, name, default_games_root(ctx), story=story, scale=scale)['message']
    except Exception as exc:
        return 'Hermes64 new: ' + failure(exc)['error']['message']
