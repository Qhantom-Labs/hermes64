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
    if not clean:
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
        candidate = defaults['brief_genres'].get(asked['setting']['genre'])
        if candidate in STYLES:
            return candidate, ('auto: brief fallback for %s; using shipped %s, requested %s assets/palette not generated; '
                               'brief.json records the gaps' % (asked['setting']['genre'], candidate, asked['palette_mood']['dominant']))
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


def title_for(premise):
    value = premise.rstrip(' .!?')
    if len(value) > 60:
        value = value[:57].rsplit(' ', 1)[0].rstrip(' ,;:') + '...'
    return value[:1].upper() + value[1:]


def preflight(settings):
    """Doctor before creating anything: plain-English fixes; Blender is optional."""
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        fail('new_platform', 'Hermes64 currently runs only on macOS (it needs the built-in sandbox-exec); nothing was created.')
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


def starter_spec(settings, premise, name, pack_id, template=None, slots=None):
    """Existing premise template, dressed with bundled public cast and a bound keepsake asset."""
    from .packs import Packs
    pack = Packs(settings).get(pack_id)
    from . import templates, pack_rooms
    template = templates.pick_template(premise, explicit=template)[0]
    rooms = pack_rooms.load(settings, pack_id) if template == 'arena_run_v1' else None
    bundle = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    combat2 = ((bundle / 'contracts/gameplay/1.2.0/manifest.json').is_file()
               and (bundle / 'runtime/godot/modules/combat/run.gd').is_file())
    spec = templates.build(template, premise, name, pack, rooms, slots, combat2=combat2)
    spec['title'] = (slots or {}).get('title') or title_for(premise)
    bundle = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    path = bundle / 'bindings.json'
    rows = json.loads(path.read_text(encoding='utf-8')).get('characters', []) if path.is_file() else []
    cast = {row.get('character_id'): row for row in rows if isinstance(row, dict) and row.get('public_release')}
    player, local = CAST[pack_id]

    def bind(character, row):
        character.update(body_id=row['body_id'], base_rig_id=row['base_rig_id'], params=copy.deepcopy(row['params']))
        character['role_profiles'] = {role: copy.deepcopy(row['params']) for role in character['role_profiles']}

    if template == 'arena_run_v1':
        requested = (slots or {}).get('hero', {}).get('binding', player)
        if requested not in cast:
            spec['metadata'].setdefault('template_pending', []).append('hero.binding (bundled fallback)')
        if player in cast:
            bind(spec['characters'][0], cast.get(requested, cast[player]))
        by_id = {c['id']: c for c in spec['characters']}
        for npc in (slots or {}).get('npcs', []):
            requested = npc.get('binding', local)
            if requested not in cast:
                spec['metadata'].setdefault('template_pending', []).append('npcs.binding (bundled fallback)')
            if local in cast:
                bind(by_id[npc['id']], cast.get(requested, cast[local]))
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
    return spec


def create(settings, premise, style=None, name=None, default_root=None, story=None):
    """Run the one-command start. Returns a result dict; raises Fault with a one-line message."""
    from .service import Service
    from .adapters import Components
    from . import playtest
    from .doctor import BLENDER_NOTE
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
    name = slug(premise) if name in (None, '') else check_name(name)
    spec = starter_spec(settings, premise, name, pack, template, slots)
    if record:
        spec['metadata']['premise'] = record['id'] + '@' + record['sha256']
    unapplied = list(spec['metadata'].get('template_pending', []))
    unapplied += [key for key in ('moveset', 'scenes', 'audio', 'textures', 'results', 'weather') if slots.get(key)]
    if spec.get('gameplay', {}).get('api_version') != '1.2.0':
        if any(key != 'max_health' for key in slots.get('run', {})):
            unapplied.append('run (except max_health)')
        if slots.get('finale', {}).get('attack_budget'):
            unapplied.append('finale.attack_budget')
        if len(slots.get('finale', {}).get('bosses', [])) > 1:
            unapplied.append('finale.bosses (sequential on legacy combat)')
    elif 'moveset' in unapplied:
        unapplied.remove('moveset')
    if unapplied:
        spec['metadata']['template_pending'] = unapplied
    tools = preflight(settings)
    stages.append({'stage': 'doctor', 'seconds': round(time.monotonic() - started, 3), 'status': 'ready'})
    if (root / name).exists() or (root / name).is_symlink():
        fail('new_exists', 'A game named %r already exists in %s; pick another with --name <new-name> (or project=...) '
             'or open it with hermes64_open.' % (name, root))
    if uses_default:
        root.mkdir(parents=True, exist_ok=True)
    settings = dict(settings, projects_root=str(root))
    service = Service(settings)
    project = None

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

    call('scaffold', 'scaffold', {'pack': pack, 'spec_json': json.dumps(spec)})
    project = service.project(name)
    if asked is not None and not project.path('brief.json').exists():
        project.write_json('brief.json', asked)
    call('compile', 'compile', {'spec_path': 'source/spec.json'})
    checked = call('check', 'check', {}, required=False)
    # MERGE5: build the room shells/kit assets before the playtest, play runtime and style audit (an unbuilt game is
    # a cutaway void the audit can only fail). Never a silent builder switch: no usable builder reads "NOT BUILT".
    builder, why = asset_builder(settings, tools)
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
        command = ' '.join(shlex.quote(part) for part in argv)
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
        card = {'format': 'hermes64-game/1', 'name': name, 'title': title, 'premise': premise,
                'style': {'pack': pack, 'name': STYLE_NAMES[pack], 'reason': reason},
                'template': {'id': template, 'reason': template_reason},
                'proof_badge': badge, 'paths': paths, 'play': {'argv': argv, 'command': command},
                'doctor': {'python': tools['python'], 'godot': tools['godot'],
                           'blender': tools['blender'] or 'not found. ' + BLENDER_NOTE},
                'note': ('Game card written by /hermes64 new. It is not the portable source-project manifest '
                         '(contracts/project/1.0.0.json) and no tool reads it; the current build pointer is .maker/current.json.')}
        if asked is not None:
            card['brief'] = briefs.summary(asked)
        story_card = ({k: record[k] for k in ('id', 'sha256', 'reason')} if record else None)
        card['story'] = story_card
        card['not_applied'] = unapplied
        project.write_json('project.json', card)
        ok = badge['ok']
        first = 'Made "%s" in %s%s' % (title, project.root, ' (default games folder)' if uses_default else '')
        if not ok:
            reasons = [r for r in tested.get('reasons', []) if isinstance(r, str)] if not tested.get('ok') else []
            if not reasons and assets['status'] != 'passed':
                reasons = ['room assets not built (%s); run hermes64_build_assets' % assets.get('reason', assets['status'])]
            if not reasons and audited['result'] and audited['result']['status'] == 'FAIL':
                reasons = [audited['result']['summary'] + '; run the style audit next steps (hermes64_check action=audit)']
            first = 'Made "%s" in %s, but it needs work: %s' % (title, project.root, (reasons or ['see the badge'])[0])
        style_line = 'Style: %s (%s), %s' % (STYLE_NAMES[pack], pack, reason)
        lines = [first, style_line, 'Badge: ' + badge['text'], 'Play: ' + command]
        if template != 'two_room_collect_v1' or record:
            lines.insert(2, 'Template: %s (%s)' % (template, template_reason))
        if record:
            lines.insert(3, 'Story: %s (%s)' % (record['id'], record['reason']))
        if unapplied:
            lines.append('Not yet applied: ' + ', '.join(unapplied))
        if audited['result'] and audited['result'].get('contact_sheet'):
            lines.append('Style audit sheet: ' + str(project.root / audited['result']['contact_sheet']))
        if not tools['blender']:
            lines.append('Optional: Blender not found; only builder=blender (the default) needs it. Set builder to auto '
                         'to build room assets with Python + numpy instead.')
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
                  'style_audit': audited['line'], 'assets': assets, 'next': steps,
                  'project_dir': str(project.root), 'title': title, 'premise': premise,
                  'story': story_card, 'not_applied': unapplied,
                  'template': card['template'], 'style': card['style'], 'badge': badge['text'], 'proof_badge': badge, 'play_command': command,
                  'play_argv': argv, 'paths': paths, 'default_games_folder': uses_default, 'stages': stages,
                  'seconds': round(time.monotonic() - started, 3), 'message': message}
        project.write_json('.maker/new.json', result)
    return result


def asset_builder(settings, tools):
    """(builder, None) when hermes64_build_assets can run with the configured builder, else (None, reason). The
    builder policy (adventure_maker/builders.py: blender unless configured) is kept, never switched for availability."""
    from .builders import select
    try:
        builder = select(settings)
    except Fault as exc:
        return None, one_line(exc)[:200]
    if builder == 'blender' and not tools.get('blender'):
        return None, 'Blender not found; install Blender or set builder to auto with a numpy Python'
    return builder, None


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


def parse(raw, include_story=False):
    """Quoted premise and optional style/name/story; legacy callers retain their three-tuple."""
    value = (raw or '').strip()
    premise, style, name, story, positional = None, None, None, None, []
    if value[:1] in QUOTES:
        end = value.find(QUOTES[value[0]], 1)
        if end < 0:
            fail('new_quote', 'The premise is missing its closing quote; try ' + EXAMPLE + '.')
        premise, value = value[1:end], value[end + 1:]
    tokens = value.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        key, _, inline = token.partition('=')
        if token in ('--style', '--name', '--story'):
            if index + 1 >= len(tokens):
                fail('new_option', token + ' needs a value, e.g. ' + token + ' polar.')
            key, inline, index = token[2:], tokens[index + 1], index + 1
        elif key in ('style', 'name', 'story', '--style', '--name', '--story') and inline:
            key = key.lstrip('-')
        else:
            key = None
        if key == 'style':
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
    elif positional:
        if len(positional) > 1 or style is not None:
            fail('new_extra', 'Unexpected text after the premise (%r); use ' % one_line(' '.join(positional))[:60]
                 + EXAMPLE + ' polar.')
        style = positional[0]
    if story is not None and not include_story:
        fail('new_option', 'Story options require the story-aware command path.')
    return (premise, style, name, story) if include_story else (premise, style, name)


def failure(exc):
    if isinstance(exc, Fault):
        return {'ok': False, 'error': {'code': exc.code, 'message': one_line(exc)[:1000]}}
    return {'ok': False, 'error': {'code': 'new_internal', 'message': one_line(
        'Something went wrong (%s: %s); try again, or run /hermes64 for help.' % (type(exc).__name__, str(exc)[:300]))}}


def run_tool(settings, args, default_root=None):
    """hermes64_demo with a premise. Friendly checks run before the strict schema check."""
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
        return json.dumps(result, ensure_ascii=False, sort_keys=True)
    except Exception as exc:  # every refusal is one line of JSON; never a fabricated success
        return json.dumps(failure(exc), ensure_ascii=True)


def command(ctx, raw):
    """Slash command text: the four-line success summary, or one plain-English failure line."""
    from .tools import SETTINGS
    from .plugin_settings import default_games_root
    try:
        settings = {key: ctx.get_config(key, '') for key in SETTINGS}
        premise, style, name, story = parse(raw, include_story=True)
        return create(settings, premise, style, name, default_games_root(ctx), story=story)['message']
    except Exception as exc:
        return 'Hermes64 new: ' + failure(exc)['error']['message']
