"""Bounded, closed data-only story files; installed or user games-folder premises."""
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .safety import fail, inspect_path, strict_json
from .schemas import obj, text, validate as validate_schema

ROOT = Path(__file__).resolve().parents[1]
ID = text(48, pattern=r'^[a-z][a-z0-9_]*$')
STORY_ID = text(64, pattern=r'^[a-z][a-z0-9_-]*$')
ASSET = text(64, pattern=r'^[a-z][a-z0-9_.-]*$')
LIMIT = 262144


def array(item, maximum=32, minimum=0):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': maximum}


def integer(lo, hi):
    return {'type': 'integer', 'minimum': lo, 'maximum': hi}


def mapping(item):
    return {'type': 'object', 'additionalProperties': item, 'maxProperties': 64,
            'propertyNames': {'pattern': r'^[a-z0-9][a-z0-9_.:-]{0,63}$'}}


PATTERN = obj({'id': ID, 'kind': {'enum': ['bump', 'slam', 'shot', 'surge']},
               'windup_ticks': integer(1, 600), 'active_ticks': integer(1, 600), 'recovery_ticks': integer(1, 600),
               'damage': integer(1, 64), 'speed_mps': {'type': 'number', 'minimum': 0.1, 'maximum': 20},
               'size_m': {'type': 'number', 'minimum': 0.1, 'maximum': 10}, 'count': integer(1, 8),
               'deflectable': {'type': 'boolean'}, 'cue': ASSET},
              ['id', 'kind', 'windup_ticks', 'active_ticks', 'recovery_ticks', 'damage', 'speed_mps', 'size_m', 'count', 'deflectable', 'cue'])
CARD = obj({'room': ID, 'camera': ID, 'actors': array(obj({'id': ID, 'clip': ID}, ['id', 'clip']), 8),
            'line': obj({'id': ID, 'speaker': text(80), 'text': text(240)}, ['id', 'speaker', 'text']),
            'voice': ASSET, 'hold_ticks': integer(1, 3600)}, ['room', 'camera', 'hold_ticks'])
# GAPS2: a full runtime scene (docs/SCENES.md), bounded here and closed-checked by story/presentation/scenes.py at create.
RUNTIME_SCENE = {'type': 'object', 'x-validated-by': 'story/presentation/scenes.py'}
# GAPS2 G4: boss robot tuning, inside the gameplay contract's ROBOT bounds; speed_mps stops at the checker's player run
# speed (story/modules/combat_bounds.PLAYER_RUN_MPS) so a boss can always be outrun.
BOSS_ROBOT = obj({'armor': {'enum': ['none', 'until_recover']}, 'hurt_ticks': integer(1, 60),
                  'knockback_m': {'type': 'number', 'minimum': 0, 'maximum': 1.5}})
BOSS_SPEED = {'type': 'number', 'minimum': 0.1, 'maximum': 2.4}
MUSIC = obj({k: ASSET for k in ('default', 'menu', 'boss', 'results')})
MUSIC['properties'].update({k: mapping(ASSET) for k in ('scenes', 'waves', 'events')})
AUDIO = obj({'music': MUSIC,
             'voice': mapping(obj({'asset': ASSET, 'on_scene': ID, 'on_action': text(128), 'on_event': ID}, ['asset'])),
             'cues': mapping(ASSET),
             'mix': obj({k: {'type': 'number', 'minimum': -60, 'maximum': 6} for k in ('music_db', 'voice_db', 'sfx_db')})})
AUDIO['properties']['mix']['properties']['crossfade_s'] = {'type': 'number', 'minimum': 0, 'maximum': 10}
SCHEMA = obj({
    'format': {'const': 'hermes64-premise/1'}, 'id': STORY_ID, 'title': text(120),
    'template': {'enum': ['two_room_collect_v1', 'arena_run_v1']}, 'style': ID,
    'room_scale': {'enum': ['small', 'medium', 'large', 'open']},
    'hero': obj({'id': ID, 'name': text(80), 'binding': ASSET}, ['id', 'name']),
    'npcs': array(obj({'id': ID, 'name': text(80), 'binding': ASSET, 'room': ID,
                       'anchor': {'enum': ['captive', 'interact']}, 'clip': ID}, ['id', 'name', 'room', 'anchor']), 8),
    'rooms': obj({'order': array(ID, 16, 3)}, ['order']),
    'robots': array(obj({'id': ID, 'name': text(80), 'base': {'enum': ['walker', 'brute', 'drone']},
                         'max_health': integer(1, 64), 'damage': integer(1, 64), 'binding': ASSET}, ['id', 'name', 'base']), 12),
    'bosses': array(obj({'id': ID, 'name': text(80), 'max_health': integer(1, 64), 'patterns': array(PATTERN, 8, 1),
                         'binding': ASSET}, ['id', 'name']), 3),
    'arenas': array(obj({'room': ID, 'label': text(80), 'waves': array(array(obj({'robot': ID, 'count': integer(1, 24)},
                                                                            ['robot', 'count']), 16, 1), 8, 1)},
                        ['room', 'label', 'waves']), 14),
    'finale': obj({'room': ID, 'bosses': array(ID, 3, 1),
                   'attack_budget': obj({'count': integer(1, 3), 'gap_ticks': integer(0, 600)}, ['count', 'gap_ticks'])},
                  ['room', 'bosses']),
    'goal': obj({'label': text(80), 'text': text(1000), 'ending': text(2000)}, ['label', 'text', 'ending']),
    'run': obj({'max_health': integer(1, 64), 'death_penalty_ticks': integer(0, 36000),
                'clock': {'enum': ['first_control_to_last_challenge']}, 'reset_encounter_on_death': {'const': True},
                'pause_clock_in_cutscene': {'const': True}, 'hit_invulnerability_ticks': integer(18, 600)}),
    'moveset': {'enum': ['brawler_v1']},
    'scenes': obj({k: array(CARD, 16) for k in ('opening', 'pre_finale', 'ending')}),
    'results': obj({'enabled': {'type': 'boolean'}, 'title': text(120)}),
    'audio': AUDIO, 'textures': mapping(ASSET), 'weather': mapping({'enum': ['rain', 'none']})
}, ['format', 'id', 'title', 'template', 'style'])
# GAPS2 (one block, so the rows above merge cleanly with other lanes): G4 boss robot block + speed; G3 full runtime
# scenes in scenes.list; G9 text_boxes (default off for arena_run_v1).
SCHEMA['properties']['bosses']['items']['properties'].update(robot=BOSS_ROBOT, speed_mps=BOSS_SPEED)
SCHEMA['properties']['scenes']['properties']['list'] = array(RUNTIME_SCENE, 32)
SCHEMA['properties']['text_boxes'] = {'type': 'boolean'}


def _opaque(value, at, depth=0):
    """Bounded JSON for a runtime scene: short lowercase keys, finite numbers, short strings; closed rules come later."""
    if depth > 8:
        fail('premise', at + ': nested too deep')
    if isinstance(value, dict):
        if len(value) > 64:
            fail('premise', at + ': too many fields')
        for key, child in value.items():
            if not re.fullmatch(r'[a-z_]{1,32}', str(key)):
                fail('premise', at + ': unknown field ' + str(key)[:40])
            _opaque(child, at + '.' + key, depth + 1)
    elif isinstance(value, list):
        if len(value) > 64:
            fail('premise', at + ': array length out of bounds')
        for child in value:
            _opaque(child, at + '[]', depth + 1)
    elif isinstance(value, str):
        if len(value) > 240:
            fail('premise', at + ': text over 240 characters')
    elif not (isinstance(value, bool) or (isinstance(value, (int, float)) and abs(value) < 1e9)):
        fail('premise', at + ': expected JSON text, numbers or booleans')


def _check(value, schema, at='$'):
    """The normal validator's primitive rules plus explicitly bounded dynamic slot maps."""
    if schema.get('x-validated-by'):
        if not isinstance(value, dict):
            fail('premise', at + ': expected an object')
        return _opaque(value, at)
    if schema.get('type') == 'object':
        if not isinstance(value, dict):
            fail('premise', at + ': expected an object')
        props = schema.get('properties', {})
        dynamic = schema.get('additionalProperties')
        if len(value) > schema.get('maxProperties', 64) or any(k not in value for k in schema.get('required', [])):
            fail('premise', at + ': missing fields or too many slots')
        for key, child in value.items():
            if key in props:
                _check(child, props[key], at + '.' + key)
            elif isinstance(dynamic, dict) and re.fullmatch(schema['propertyNames']['pattern'], key):
                _check(child, dynamic, at + '.' + key)
            else:
                fail('premise', at + ': unknown field ' + str(key))
    elif schema.get('type') == 'array':
        if not isinstance(value, list) or not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 32):
            fail('premise', at + ': array length out of bounds')
        for child in value:
            _check(child, schema['items'], at + '[]')
    else:
        if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
            fail('premise', at + ': unexpected constant')
        validate_schema(value, schema, at)


def validate(data: Any) -> dict:
    _check(data, SCHEMA)
    for collection in ('robots', 'bosses', 'npcs'):
        ids = [r['id'] for r in data.get(collection, [])]
        if len(ids) != len(dict.fromkeys(ids)):
            fail('premise', 'Duplicate ' + collection + ' ids')
    order = data.get('rooms', {}).get('order', [])
    if len(order) != len(dict.fromkeys(order)):
        fail('premise', 'Duplicate room ids')
    for row in data.get('arenas', []) + data.get('npcs', []):
        if row['room'] not in order:
            fail('premise', 'Premise references a room outside rooms.order')
    if any(room not in order for room in data.get('weather', {})):
        fail('premise', 'weather names a room outside rooms.order')
    if data.get('finale') and (not order or data['finale']['room'] != order[-1]):
        fail('premise', 'Finale must use the last room in rooms.order')
    builtins = ['walker', 'brute', 'drone', 'guardian']
    custom = [r['id'] for kind in ('robots', 'bosses') for r in data.get(kind, [])]
    if len(builtins + custom) != len(dict.fromkeys(builtins + custom)) or len(builtins + custom) > 16:
        fail('premise', 'Robot/boss ids must be distinct from stock ids; at most 16 archetypes including stock.')
    robots = builtins[:3] + [r['id'] for r in data.get('robots', [])]
    bosses = ['guardian'] + [r['id'] for r in data.get('bosses', [])]
    arenas = data.get('arenas', [])
    if len([a['room'] for a in arenas]) != len(dict.fromkeys(a['room'] for a in arenas)):
        fail('premise', 'Only one arena roster may be defined per room.')
    for arena in arenas:
        if arena['room'] not in order[1:-1]:
            fail('premise', 'Arena rosters must use intermediate rooms, not the opening/finale.')
        groups = 0
        for group in arena['waves']:
            if any(row['robot'] not in robots for row in group):
                fail('premise', 'A wave names an unknown robot archetype.')
            count = sum(row['count'] for row in group)
            groups += (count + 2) // 3
        if groups > 8:
            fail('premise', 'Wave cap exceeded: split into at most eight groups of three spawns.')
    if any(bid not in bosses for bid in data.get('finale', {}).get('bosses', [])):
        fail('premise', 'Finale names an unknown boss archetype.')
    return data


def load(folder, expected=None):
    folder = Path(folder)
    path = folder / 'premise.json'
    inspect_path(path)
    if not path.is_file():
        fail('premise_missing', 'Story file is missing; put premise.json in premises/<story-id>/ inside your games folder.')
    with path.open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        fail('premise', 'Story file exceeds 256 KiB; split it into smaller stories.')
    data = validate(strict_json(raw))
    if data['id'] != (expected or folder.name):
        fail('premise', 'Story directory and declared id differ.')
    return {'id': data['id'], 'sha256': hashlib.sha256(raw).hexdigest(), 'data': data}


def resolve(settings, premise, story=None, games_root=None):
    bundle = Path(settings.get('bundle_root') or ROOT)
    roots = ([Path(games_root) / 'premises'] if games_root else []) + [bundle / 'premises']
    if story is not None:
        validate_schema(story, STORY_ID)
        for root in roots:
            path = root / story
            if path.exists() or path.is_symlink():
                return dict(load(path, story), reason='premise file, chosen with --story')
        fail('premise_missing', 'Story %r was not found; install it in the games folder premises/<id>/ or choose a bundled story.' % story)
    title = premise.split(':', 1)[0].strip().casefold()
    for root in roots:
        inspect_path(root)
        if not root.is_dir():
            continue
        folders = sorted(root.iterdir())
        if len(folders) > 100:
            fail('premise', 'More than 100 story entries; move unused stories out of this premises folder.')
        matches = []
        for folder in folders:
            inspect_path(folder)
            if folder.is_dir() and (folder / 'premise.json').is_file():
                record = load(folder)
                if record['data']['title'].strip().casefold() == title:
                    matches.append(record)
        if len(matches) > 1:
            fail('premise_ambiguous', 'More than one story matches this title; choose --story <id>.')
        if matches:
            return dict(matches[0], reason='premise file, matched by title')
    return None
