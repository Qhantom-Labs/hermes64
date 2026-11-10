"""Character staging used by the default plugin build/open path and evidence harness."""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import shutil
import sys

if '.' in (__package__ or ''):
    from ..adventure_maker.adapters import Components
    from ..adventure_maker.service import Service
    from ..adventure_maker.runner import locate
    from ..tools.import_characters import read_json, write_json, write_bytes, CharacterError, contained, RESTRICTED_IDS
else:
    from adventure_maker.adapters import Components
    from adventure_maker.service import Service
    from adventure_maker.runner import locate
    from tools.import_characters import read_json, write_json, write_bytes, CharacterError, contained, RESTRICTED_IDS

ROOT = Path(__file__).resolve().parents[1]
PACKS = {'thaw': 'polar_pod', 'last_light': 'n64_v0'}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def fresh(path):
    path = Path(path).resolve()
    if ROOT / 'evidence/characters' not in path.parents:
        raise CharacterError('fixture/evidence output must be under evidence/characters')
    path.mkdir(parents=True, exist_ok=False)
    return path


def apply_presentation(spec, game):
    spec = copy.deepcopy(spec)
    presentation = read_json(ROOT / 'examples' / game / 'presentation.json')
    overlay = read_json(ROOT / 'characters/presentation.json')
    for room, characters in overlay['games'][game].items():
        presentation['rooms'][room].setdefault('characters', {}).update(characters)
    for room, overrides in overlay.get('room_overrides', {}).get(game, {}).items():
        presentation['rooms'][room].update(overrides)
    spec['metadata']['presentation'] = presentation
    return spec


def stage_runtime(runtime, root=ROOT):
    runtime, root = Path(runtime), Path(root)
    original = read_json(runtime / 'bindings.json')
    bound = read_json(root / 'bindings.json')
    for row in bound['characters']:
        if row.get('internal_only') or not row.get('public_release', False) or row.get('character_id') in RESTRICTED_IDS or 'internal' in Path(row['glb']).parts:
            raise CharacterError('restricted character binding is not admitted')
        for candidate in [row, row['fallback']]:
            path = contained(root, candidate['glb'])
            if not path.is_file() and candidate is row['fallback']:
                raise CharacterError('missing character fallback: ' + candidate['glb'])
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != candidate['sha256']:
                raise CharacterError('runtime binding hash mismatch: ' + candidate['glb'])
            candidate['path'] = str(path)
    original['characters'] = bound['characters']
    write_json(runtime / 'bindings.json', original)
    stage_combat(runtime, root)
    # Generated project only; preserve the shared scene/shader templates.
    write_bytes(runtime / 'main.tscn', (root / 'runtime/godot/actors/main.tscn').read_bytes())
    write_json(runtime / 'character-source-hashes.json', {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for base in ['runtime/godot', 'characters'] for p in (root / base).rglob('*')
        if p.is_file() and not any(x in p.parts for x in ['internal', '__pycache__', '.godot'])})


def stage_combat(runtime, root=ROOT):
    """Runtime combat art (`combat.json`): enemy archetype models and phases for the theme's kit pack, the
    trail_staff weapon per character pack, each public combatant's grip, and the clip phase metadata.

    Every GLB is hash-checked against characters/combat/manifest.json. The module host reads it to bind real
    clips; it is a no-op (no file) before the combat art is imported."""
    runtime, root = Path(runtime), Path(root)
    source = root / 'characters/combat/manifest.json'
    if not source.is_file():
        return None
    combat = read_json(source)
    theme = read_json(runtime / 'theme.json') if (runtime / 'theme.json').is_file() else {}
    # runtime_snapshot points env_root at kits/library/<kit pack>/env.
    kit = Path(str(theme.get('env_root', ''))).parent.name
    packs = sorted({row['pack'] for row in combat['enemies']})
    pack = kit if kit in packs else ('forest_village' if 'forest_village' in packs else packs[0])

    def admit(row):
        path = contained(root, row['glb'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise CharacterError('combat art hash mismatch: ' + row['glb'])
        return str(path)

    enemies = {row['id']: {'id': row['id'], 'template': row['template'], 'rig': row['rig'], 'pack': row['pack'],
                           'path': admit(row), 'sha256': row['sha256'], 'clips': row['clips'],
                           'fsm_state_clip': row['fsm_state_clip'], 'phases': row['phases'],
                           'face_atlas': row['face_atlas'], 'tris_body': row['tris_body']}
               for row in combat['enemies'] if row['pack'] == pack}
    weapons = {row['pack']: {'id': row['id'], 'pack': row['pack'], 'path': admit(row), 'sha256': row['sha256'],
                             'node': row['node'], 'slot': row['slot'], 'tris': row['tris'],
                             'rotation_xyzw': row['grip_rotation_on_hand_r_xyzw']}
               for row in combat['props'] if row.get('kind') == 'weapon'}
    grips = {}
    for row in read_json(root / 'characters/manifest.json')['characters']:
        block = row.get('combat')
        if block and row.get('public_release', False) and not row.get('internal_only') and row['id'] not in RESTRICTED_IDS:
            grips[row['id']] = {'pack': row['pack'], 'translation': block['weapon_grip']['translation'],
                                'stance_props': block.get('stance_props_hidden_in_combat', [])}
    data = {'api_version': '1.0.0', 'schema': 'hermes64-combat-runtime/1', 'pack': pack, 'kit_pack': kit,
            'templates': combat['templates'], 'clips': combat['character_clips']['combat_metadata'],
            'enemies': enemies, 'weapons': weapons, 'grips': grips,
            'source_manifest_sha256': combat['source_manifest_sha256']}
    stage_robots(data, runtime, root, admit)
    write_json(runtime / 'combat.json', data)
    return data


def game_templates(runtime):
    """FSM templates of the staged game's combat archetypes (prepare_runtime writes game.json first)."""
    path = Path(runtime) / 'game.json'
    game = read_json(path) if path.is_file() else {}
    return {str((row.get('fsm') or {}).get('template', '')) for module in (game.get('gameplay') or {}).get('modules', [])
            for row in (module.get('entities') or {}).get('archetypes', []) if isinstance(row, dict)}


def stage_robots(data, runtime, root, admit):
    """MERGE5 robot art seam: the character-system robots (characters/combat/robots.json, built and gated by
    tools/merge5_robots.py) for the robot templates this game uses, in its kit pack. Each becomes an enemy row
    plus a templates alias, so the module host binds it before the modules/combat/robots.json stand-ins. A game
    without robot templates gets no robot rows (its combat.json is unchanged). Every GLB is hash-checked."""
    source = Path(root) / 'characters/combat/robots.json'
    if not source.is_file():
        return
    side = read_json(source)
    used = game_templates(runtime)
    added = []
    for row in side['enemies']:
        if row['pack'] != data['pack'] or row['template'] not in used or row['id'] in data['enemies']:
            continue
        if side['templates'].get(row['template']) != row['id']:
            raise CharacterError('robot art row is not its template alias: ' + row['id'])
        data['enemies'][row['id']] = {'id': row['id'], 'template': row['template'], 'rig': row['rig'], 'pack': row['pack'],
                                      'path': admit(row), 'sha256': row['sha256'], 'clips': row['clips'],
                                      'fsm_state_clip': row['fsm_state_clip'], 'phases': row['phases'],
                                      'face_atlas': row['face_atlas'], 'tris_body': row['tris_body'],
                                      'tris_glb': row['tris_glb']}
        added.append(row['id'])
    if added:
        data['templates'] = dict(data['templates'], **{data['enemies'][i]['template']: i for i in added})
        data['robot_art'] = {'schema': side['schema'], 'rows': sorted(added),
                             'manifest_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}


# Backward-compatible name for room-look's harness, not a second activation path.
CharacterComponents = Components


def call(svc, project, name, **args):
    result = json.loads(svc.handle('hermes64_' + name, dict(project=project, **args)))
    if result.get('truncated'):
        result = svc.project(project).read_json(result['report_path'])
    if not result.get('ok'):
        raise CharacterError(name + ': ' + json.dumps(result)[:3000])
    return result


def create_game(out, game, build=False):
    svc = Service({'bundle_root': str(ROOT), 'projects_root': str(out / 'projects'), 'python_path': sys.executable})
    (out / 'projects').mkdir(exist_ok=True)
    spec = apply_presentation(read_json(ROOT / 'examples' / game / 'spec.json'), game)
    receipts = []
    for name, args in [('scaffold', {'pack': PACKS[game], 'spec_json': json.dumps(spec)}),
                       ('compile', {'spec_path': 'source/spec.json'}), ('check', {})]:
        receipts.append(call(svc, game, name, **args))
    if build:
        receipts.append(call(svc, game, 'build_assets', seed=7))
    write_json(out / (game + '-facade.json'), receipts)
    project = svc.project(game)
    component = Components(svc.settings, project)
    current = svc.current(project)
    # Use a fresh checker receipt at a named stable owned location.
    check_folder = svc.folder(project, 'character-check')
    proof = check_folder + '/proof.json'
    component.check(current['game'], proof)
    return svc, project, component, current['game'], proof


def actor_test(component, game, folder):
    runtime = component.prepare_runtime(game, folder)
    argv = [locate('godot'), '--headless', '--path', str(runtime), '--script', 'res://actors/test.gd']
    process = component.runner.run(argv, component.project.root, timeout=90)
    component.project.write_json(folder + '/actor.process.json', dict(process, argv=argv))
    if process['returncode'] or process['stderr']:
        raise CharacterError('headless actors: ' + json.dumps(process)[-7000:])
    report = read_json(runtime / 'actor-test.json')
    if report['status'] != 'passed': raise CharacterError('actor assertions failed')
    # Prove the movement oracle rejects a clock-coupled controller, not just happy input.
    negative_argv = argv + ['--', '--character-bad-clock']
    negative = component.runner.run(negative_argv, component.project.root, timeout=90)
    component.project.write_json(folder + '/actor-clock-negative.process.json', dict(negative, argv=negative_argv))
    bad_report = read_json(runtime / 'actor-test.json')
    component.project.write_json(folder + '/actor-clock-negative.json', bad_report)
    write_json(runtime / 'actor-test.json', report)
    expected = ['movement independent of pose fps', 'real controller speed 2.4 m/s']
    if negative['returncode'] != 1 or negative['stderr'] or bad_report['errors'] != expected:
        raise CharacterError('movement negative control did not reject exactly the injected coupling')
    report['negative_clock'] = {'status': 'rejected', 'errors': bad_report['errors'], 'motion': bad_report['motion']}
    return report


def actor_replay(component, game, proof, folder):
    runtime = component.prepare_runtime(game, folder)
    report_path = component.project.path(folder + '/replay.json')
    argv = [locate('godot'), '--headless', '--path', str(runtime), '--script', 'res://actors/replay.gd', '--',
            '--game', str(component.project.path(game)), '--proof', str(component.project.path(proof)), '--report', str(report_path)]
    process = component.runner.run(argv, component.project.root, timeout=180)
    component.project.write_json(folder + '/replay.process.json', dict(process, argv=argv))
    if process['returncode'] or process['stderr']:
        raise CharacterError('actor replay: ' + json.dumps(process)[-7000:])
    report = read_json(report_path)
    if report['status'] != 'passed' or not report['save_round_trip']:
        raise CharacterError('actor replay assertions failed')
    return report


def verify_headless():
    out = fresh(ROOT / 'evidence/characters' / ('headless-' + stamp()))
    result = {'status': 'passed', 'replays': {}, 'evidence': str(out.relative_to(ROOT))}
    for game in PACKS:
        svc, project, component, path, proof = create_game(out, game)
        if game == 'thaw': result.update(actor_test(component, path, svc.folder(project, 'actor-test')))
        result['replays'][game] = actor_replay(component, path, proof, svc.folder(project, 'actor-replay'))
    write_json(out / 'summary.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'replays']}), flush=True)
    return result


def capture_games(out):
    out = fresh(out)
    result = {'games': {}, 'scope': 'default plugin Components build/open; real main.gd capture; teleported initial-state visual coverage'}
    for game in PACKS:
        svc, project, component, path, proof = create_game(out, game, build=True)
        folder = svc.folder(project, 'actor-capture')
        opened = component.open(path, folder, 90, screenshots=True)
        project.write_json(folder + '/capture.process.json', opened)
        if opened['returncode'] or opened['stderr']:
            # Preserve failed room-budget captures for diagnosis instead of deleting the images.
            print('CAPTURE PROCESS', game, opened['returncode'], opened['stderr'][-2500:], flush=True)
        if not (project.path(folder) / 'screens/capture.json').is_file():
            raise CharacterError('capture produced no report: ' + json.dumps(opened)[-4000:])
        dest = out / game
        shutil.copytree(project.path(folder) / 'screens', dest)
        capture = read_json(dest / 'capture.json')
        try:
            replay = actor_replay(component, path, proof, svc.folder(project, 'actor-replay'))
        except Exception as exc:
            # A failed replay remains failed; continue independent visual coverage for the other game.
            replay = {'status': 'failed', 'error': str(exc), 'exception': type(exc).__name__}
        result['games'][game] = {'capture': capture, 'replay': replay, 'process_exit': opened['returncode'], 'stderr': opened['stderr']}
        write_json(out / 'summary.json', result)
        print(game, 'capture', capture['status'], 'rooms', len(capture['rooms']), 'replay', replay['status'], flush=True)
    from tools.roomlook import Canvas
    from adventure_maker.style_gate import read_png
    rooms = [(game,r) for game,v in result['games'].items() for r in v['capture']['rooms']]
    canvas = Canvas(1288, ((len(rooms)+1)//2)*520+36)
    canvas.text('CHARACTERS - REAL RUNTIME - 320X240',8,10,scale=3)
    for i, (game,row) in enumerate(rooms):
        x, y = (i%2)*644+4, (i//2)*520+36
        canvas.text(game+'/'+row['id'], x,y+4,scale=2)
        canvas.blit(read_png(out/game/(row['id']+'-clean.png')),x,y+24,2)
    canvas.save(out/'contact-sheet.png')
    result['rooms'] = len(rooms)
    result['status'] = 'passed' if all(v['capture']['status']=='passed' and v['replay']['status']=='passed' and not v['stderr'] for v in result['games'].values()) else 'failed'
    write_json(out/'summary.json',result)
    print(json.dumps({'status':result['status'],'rooms':len(rooms),'contact_sheet':str(out/'contact-sheet.png')}),flush=True)
    if result['status'] != 'passed': raise CharacterError('capture gates failed; inspect retained evidence')
    return result
