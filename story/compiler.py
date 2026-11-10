"""Canonical story compiler and strict compiled-game integrity validation."""
import copy
import hashlib
import json
from pathlib import Path
from .errors import SpecError
from .validation import collections_for, validate
from .extensions import extended


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def normalize(spec):
    result = copy.deepcopy(spec)
    for key in collections_for(spec):
        result[key].sort(key=lambda x: x['id'])
    for room in result['rooms']:
        for key in ('doors', 'cameras', 'props'):
            room[key].sort(key=lambda x: x['id'])
        room['character_ids'].sort()
        room['kit_refs'].sort()
    for dialogue in result['dialogues']:
        dialogue['nodes'].sort(key=lambda x: x['id'])
    result['start']['inventory'].sort()
    if extended(spec):
        result['start']['collected'].sort()
    from .modules import enabled
    if enabled(spec):
        from .modules.compiler import normalize as normalize_modules
        normalize_modules(result)
    return result


def item_references(value):
    found = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ('item', 'give', 'take') and isinstance(v, str):
                found.add(v)
            else:
                found.update(item_references(v))
        if value.get('kind') == 'take':
            found.add(value['target'])
    elif isinstance(value, list):
        for v in value:
            found.update(item_references(v))
    return found


def compile_spec(spec):
    validate(spec)
    source = normalize(spec)
    game = copy.deepcopy(source)
    game['spec_hash'] = digest(source)
    from .modules import enabled
    if enabled(source):
        from .modules.compiler import contract
        game['module_contract'] = contract()
    for room in game['rooms']:
        content = {
            'characters': [copy.deepcopy(c) for c in source['characters'] if c['id'] in room['character_ids']],
            'interactions': [copy.deepcopy(a) for a in source['interactions'] if a['room'] == room['id']],
            'dialogues': [copy.deepcopy(d) for d in source['dialogues'] if d['character'] in room['character_ids']],
        }
        if extended(source):
            content['collectibles'] = [copy.deepcopy(c) for c in source['collectibles'] if c['room'] == room['id']]
            dialogue_ids = {d['id'] for d in content['dialogues']} | {c['dialogue'] for c in content['collectibles'] if c['dialogue']}
            content['dialogues'] = [copy.deepcopy(d) for d in source['dialogues'] if d['id'] in dialogue_ids]
        if enabled(source):
            from .modules.compiler import room_content
            content['modules'] = room_content(source, room['id'])
        refs = item_references(content)
        if enabled(source):
            from .modules.registry import entities
            refs.update(item for c in entities(source, 'challenge', 'challenges') if c['room'] == room['id'] for item in c['rewards']['items'])
        content['items'] = [copy.deepcopy(i) for i in source['items'] if i['id'] in refs]
        room['content'] = content
        room['build_hash'] = digest(room)
    game['game_hash'] = digest(game)
    return game


def validate_game(game):
    if not isinstance(game, dict) or 'game_hash' not in game or 'spec_hash' not in game:
        raise SpecError('game requires game_hash and spec_hash')
    source = copy.deepcopy(game)
    source.pop('game_hash')
    source.pop('spec_hash')
    from .modules import enabled
    if enabled(game):
        if 'module_contract' not in source:
            raise SpecError('compiled game requires module_contract')
        source.pop('module_contract')
    if not isinstance(source.get('rooms'), list):
        raise SpecError('game rooms must be an array')
    for room in source['rooms']:
        if not isinstance(room, dict) or 'content' not in room or 'build_hash' not in room:
            raise SpecError('compiled room requires content and build_hash')
        room.pop('content')
        room.pop('build_hash')
    expected = compile_spec(source)
    if canonical(expected) != canonical(game):
        raise SpecError('compiled game integrity/hash/canonical-order mismatch; recompile source')
    return game


def load_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise SpecError('duplicate JSON key ' + k)
            out[k] = v
        return out

    def nonfinite(value):
        raise SpecError('nonfinite JSON number ' + value)

    try:
        return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                          parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise SpecError('invalid JSON {}: {}'.format(path, exc)) from exc
