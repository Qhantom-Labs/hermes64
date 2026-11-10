"""Strict, dependency-free validator for the documented 1.0.0 contract."""
import math
import re
from .errors import SpecError
from .extensions import extended, validate_params, validate_collectibles
from .modules import enabled as modules_enabled

VERSION = '1.0.0'
SUPPORTED_VERSIONS = ('1.0.0', '1.1.0', '1.2.0')
COLLECTIONS = ('rooms', 'characters', 'items', 'flags', 'interactions', 'dialogues', 'quests', 'endings')


def collections_for(spec):
    return COLLECTIONS + (('collectible_groups', 'collectibles') if extended(spec) else ())


def fail(path, text):
    raise SpecError('{}: {}'.format(path, text))


def obj(value, fields, path):
    if not isinstance(value, dict):
        fail(path, 'expected object')
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        fail(path, 'missing fields {}; unknown fields {}'.format(missing, extra))


def text(v, p):
    if not isinstance(v, str) or not v:
        fail(p, 'expected nonempty string')


def ident(v, p):
    if not isinstance(v, str) or re.fullmatch('[a-z][a-z0-9_]*', v) is None:
        fail(p, 'invalid ID {!r}'.format(v))


def boolean(v, p):
    if type(v) is not bool:
        fail(p, 'expected bool')


def integer(v, p, minimum=0):
    if type(v) is not int or v < minimum:
        fail(p, 'expected integer >= {}'.format(minimum))


def array(v, p):
    if not isinstance(v, list):
        fail(p, 'expected array')


def strings(v, p, validator=text):
    array(v, p)
    for i, x in enumerate(v):
        validator(x, '{}/{}'.format(p, i))
    if len(v) != len(set(v)):
        fail(p, 'duplicate value')


def vector(v, p, length=3, grid=False):
    array(v, p)
    if len(v) != length:
        fail(p, 'expected {} coordinates'.format(length))
    for i, x in enumerate(v):
        if grid:
            integer(x, p + '/' + str(i), 1)
        elif type(x) not in (int, float) or not math.isfinite(x):
            fail(p, 'expected finite number')


def asset(v, p):
    text(v, p)
    if v.startswith(('/', '\\')) or ':' in v or '\\' in v or '..' in v.split('/'):
        fail(p, 'asset reference must be relative, without traversal or URL')


def json_value(v, p='spec'):
    if isinstance(v, dict):
        for key, value in v.items():
            if not isinstance(key, str):
                fail(p, 'JSON object keys must be strings')
            if key == 'timestamps':
                fail(p, 'timestamps are allowed only in saves')
            json_value(value, p + '/' + key)
    elif isinstance(v, list):
        for i, value in enumerate(v):
            json_value(value, p + '/' + str(i))
    elif isinstance(v, float) and not math.isfinite(v):
        fail(p, 'expected finite number')
    elif v is not None and type(v) not in (str, bool, int, float):
        fail(p, 'not a JSON value')


def entities(v, p):
    array(v, p)
    result = {}
    for i, x in enumerate(v):
        at = p + '/' + str(i)
        if not isinstance(x, dict) or 'id' not in x:
            fail(at, 'entity requires id')
        ident(x['id'], at + '/id')
        if x['id'] in result:
            fail(at, 'duplicate ID ' + x['id'])
        result[x['id']] = x
    return result


def reference(v, targets, p):
    if not isinstance(v, str) or v not in targets:
        fail(p, 'missing reference {!r}'.format(v))


def validate(spec):
    json_value(spec)
    obj(spec, ('contract_version', 'id', 'title', 'description', 'metadata', 'start', 'tide') + collections_for(spec) + (('gameplay',) if modules_enabled(spec) else ()), 'spec')
    if modules_enabled(spec):
        from .modules.validation import validate_header
        validate_header(spec)
    if spec['contract_version'] not in SUPPORTED_VERSIONS:
        fail('contract_version', 'unsupported version ' + str(spec['contract_version']))
    ident(spec['id'], 'id')
    text(spec['title'], 'title')
    text(spec['description'], 'description')
    if not isinstance(spec['metadata'], dict):
        fail('metadata', 'expected object')
    ix = {k: entities(spec[k], k) for k in collections_for(spec)}
    if not ix['rooms'] or not ix['endings']:
        fail('spec', 'at least one room and ending are required')
    tide = spec['tide']
    obj(tide, ('id', 'states', 'wait_label', 'wait_text'), 'tide')
    ident(tide['id'], 'tide/id')
    text(tide['wait_label'], 'tide/wait_label')
    text(tide['wait_text'], 'tide/wait_text')
    ix['tides'] = entities(tide['states'], 'tide/states')
    if not ix['tides']:
        fail('tide/states', 'at least one state is required')
    for t in tide['states']:
        obj(t, ('id', 'label', 'duration'), 'tide/' + t['id'])
        text(t['label'], 'tide/label')
        integer(t['duration'], 'tide/duration', 1)
    nodes = {}
    for d in spec['dialogues']:
        p = 'dialogues/' + d['id']
        obj(d, ('id', 'character', 'start_node', 'nodes'), p)
        reference(d['character'], ix['characters'], p + '/character')
        nodes[d['id']] = entities(d['nodes'], p + '/nodes')
        reference(d['start_node'], nodes[d['id']], p + '/start_node')

    def logic(v, p, effect=False):
        array(v, p)
        for i, c in enumerate(v):
            at = p + '/' + str(i)
            if not isinstance(c, dict):
                fail(at, 'condition/effect must be object')
            if modules_enabled(spec):
                from .modules.validation import validate_logic_reference
                if validate_logic_reference(c, spec, effect):
                    continue
            keys = set(c)
            flag_key = 'value' if effect else 'equals'
            if not effect and extended(spec) and keys == {'collected'}:
                reference(c['collected'], ix['collectibles'], at)
            elif not effect and extended(spec) and keys == {'group', 'at_least'}:
                reference(c['group'], ix['collectible_groups'], at)
                integer(c['at_least'], at + '/at_least')
            elif keys == {'flag', flag_key}:
                reference(c['flag'], ix['flags'], at)
                boolean(c[flag_key], at + '/' + flag_key)
            elif not effect and keys == {'item', 'present'}:
                reference(c['item'], ix['items'], at)
                boolean(c['present'], at + '/present')
            elif effect and (keys == {'give'} or keys == {'take'}):
                reference(next(iter(c.values())), ix['items'], at)
            elif keys == {'location'}:
                reference(c['location'], ix['rooms'], at)
            elif keys == {'tide'}:
                reference(c['tide'], ix['tides'], at)
            elif keys == {'dialogue', 'node'}:
                reference(c['dialogue'], nodes, at)
                if c['node'] != '':
                    reference(c['node'], nodes[c['dialogue']], at)
            elif not effect and keys == {'role', 'equals'}:
                reference(c['role'], ix['characters'], at)
                reference(c['equals'], ix['characters'][c['role']]['role_profiles'], at)
            else:
                fail(at, 'unknown or malformed {} {}'.format('effect' if effect else 'condition', sorted(keys)))

    for f in spec['flags']:
        obj(f, ('id', 'initial', 'description'), 'flags/' + f['id'])
        boolean(f['initial'], 'flags/' + f['id'] + '/initial')
        text(f['description'], 'flags/description')
    for c in spec['characters']:
        p = 'characters/' + c['id']
        obj(c, ('id', 'name', 'role', 'body_id', 'base_rig_id', 'params', 'role_profiles'), p)
        for k in ('name', 'body_id', 'base_rig_id'):
            text(c[k], p + '/' + k)
        ident(c['role'], p + '/role')
        if not isinstance(c['role_profiles'], dict):
            fail(p, 'role_profiles must be object')
        reference(c['role'], c['role_profiles'], p + '/role')
        for role in c['role_profiles']:
            ident(role, p + '/role_profiles')
        for params in [c['params']] + list(c['role_profiles'].values()):
            validate_params(params, p, extended(spec))
    for item in spec['items']:
        obj(item, ('id', 'name', 'description', 'asset'), 'items/' + item['id'])
        text(item['name'], 'items/name')
        text(item['description'], 'items/description')
        asset(item['asset'], 'items/asset')
    door_indexes = {}
    for r in spec['rooms']:
        p = 'rooms/' + r['id']
        obj(r, ('id', 'name', 'description', 'grid_size', 'kit_refs', 'doors', 'cameras', 'props', 'character_ids'), p)
        text(r['name'], p + '/name')
        text(r['description'], p + '/description')
        vector(r['grid_size'], p + '/grid_size', 2, True)
        strings(r['kit_refs'], p + '/kit_refs', asset)
        strings(r['character_ids'], p + '/character_ids', ident)
        for cid in r['character_ids']:
            reference(cid, ix['characters'], p + '/character_ids')
        doors = entities(r['doors'], p + '/doors')
        door_indexes[r['id']] = doors
        occupied = set()
        for d in doors.values():
            at = p + '/doors/' + d['id']
            obj(d, ('id', 'wall', 'position', 'to_room', 'to_door', 'label', 'conditions'), at)
            if d['wall'] not in ('north', 'east', 'south', 'west'):
                fail(at + '/wall', 'invalid wall')
            integer(d['position'], at + '/position')
            extent = r['grid_size'][0 if d['wall'] in ('north', 'south') else 1]
            if d['position'] >= extent:
                fail(at + '/position', 'outside wall extent ' + str(extent))
            coord = (d['wall'], d['position'])
            if coord in occupied:
                fail(at, 'duplicate door position')
            occupied.add(coord)
            reference(d['to_room'], ix['rooms'], at + '/to_room')
            ident(d['to_door'], at + '/to_door')
            text(d['label'], at + '/label')
            logic(d['conditions'], at + '/conditions')
        cameras = entities(r['cameras'], p + '/cameras')
        if not cameras:
            fail(p + '/cameras', 'at least one camera anchor required')
        for camera in cameras.values():
            obj(camera, ('id', 'position', 'look_at'), p + '/cameras')
            vector(camera['position'], p + '/cameras/position')
            vector(camera['look_at'], p + '/cameras/look_at')
        for prop in entities(r['props'], p + '/props').values():
            obj(prop, ('id', 'asset', 'position', 'rotation'), p + '/props')
            asset(prop['asset'], p + '/props/asset')
            vector(prop['position'], p + '/props/position')
            vector(prop['rotation'], p + '/props/rotation')
    for rid, doors in door_indexes.items():
        for d in doors.values():
            reference(d['to_door'], door_indexes[d['to_room']], rid + '/door/' + d['id'])
            back = door_indexes[d['to_room']][d['to_door']]
            if (back['to_room'], back['to_door']) != (rid, d['id']):
                fail(rid + '/door/' + d['id'], 'door is not reciprocal')
    for a in spec['interactions']:
        p = 'interactions/' + a['id']
        obj(a, ('id', 'room', 'kind', 'target', 'label', 'text', 'conditions', 'effects'), p)
        reference(a['room'], ix['rooms'], p + '/room')
        if a['kind'] not in ('examine', 'take', 'use', 'talk'):
            fail(p + '/kind', 'invalid interaction kind')
        for k in ('target', 'label', 'text'):
            text(a[k], p + '/' + k)
        if a['kind'] == 'take':
            reference(a['target'], ix['items'], p + '/target')
        if a['kind'] == 'talk':
            reference(a['target'], ix['characters'], p + '/target')
        logic(a['conditions'], p + '/conditions')
        logic(a['effects'], p + '/effects', True)
    for d in spec['dialogues']:
        for n in d['nodes']:
            p = 'dialogues/' + d['id'] + '/' + n['id']
            obj(n, ('id', 'text', 'conditions', 'choices') + (('role_text',) if extended(spec) and 'role_text' in n else ()), p)
            text(n['text'], p + '/text')
            if 'role_text' in n:
                if not isinstance(n['role_text'], dict):
                    fail(p + '/role_text', 'expected role-to-text map')
                for role, words in n['role_text'].items():
                    reference(role, ix['characters'][d['character']]['role_profiles'], p + '/role_text')
                    text(words, p + '/role_text/' + role)
            logic(n['conditions'], p + '/conditions')
            for c in entities(n['choices'], p + '/choices').values():
                at = p + '/choices/' + c['id']
                obj(c, ('id', 'text', 'conditions', 'effects', 'next'), at)
                text(c['text'], at + '/text')
                logic(c['conditions'], at + '/conditions')
                logic(c['effects'], at + '/effects', True)
                if c['next'] != '':
                    reference(c['next'], nodes[d['id']], at + '/next')
    for q in spec['quests']:
        p = 'quests/' + q['id']
        obj(q, ('id', 'title', 'description', 'conditions'), p)
        text(q['title'], p + '/title')
        text(q['description'], p + '/description')
        logic(q['conditions'], p + '/conditions')
    for e in spec['endings']:
        p = 'endings/' + e['id']
        obj(e, ('id', 'conditions', 'text'), p)
        text(e['text'], p + '/text')
        logic(e['conditions'], p + '/conditions')
    if extended(spec):
        validate_collectibles(spec, ix, logic)
    if modules_enabled(spec):
        from .modules.validation import validate as validate_modules
        validate_modules(spec, logic)
    validate_state(spec['start'], spec, 'start', initial=True)
    return spec


def validate_state(state, game, path='state', initial=False):
    obj(state, ('location', 'inventory', 'flags', 'dialogue', 'tide') + (('collected',) if extended(game) else ()) + (('modules',) if modules_enabled(game) else ()), path)
    if modules_enabled(game):
        from .modules.validation import validate_state as validate_module_state
        validate_module_state(state['modules'], game, initial)
    if extended(game):
        strings(state['collected'], path + '/collected', ident)
        for cid in state['collected']:
            reference(cid, {c['id'] for c in game['collectibles']}, path + '/collected')
    reference(state['location'], {r['id'] for r in game['rooms']}, path + '/location')
    strings(state['inventory'], path + '/inventory', ident)
    for i in state['inventory']:
        reference(i, {x['id'] for x in game['items']}, path + '/inventory')
    flags = {f['id']: f['initial'] for f in game['flags']}
    obj(state['flags'], flags, path + '/flags')
    for fid, v in state['flags'].items():
        boolean(v, path + '/flags/' + fid)
        if initial and v != flags[fid]:
            fail(path + '/flags/' + fid, 'initial disagrees with Flag.initial')
    dialogues = {d['id']: {n['id'] for n in d['nodes']} for d in game['dialogues']}
    obj(state['dialogue'], dialogues, path + '/dialogue')
    for did, cursor in state['dialogue'].items():
        if cursor != '':
            reference(cursor, dialogues[did], path + '/dialogue/' + did)
    if sum(bool(x) for x in state['dialogue'].values()) > 1:
        fail(path + '/dialogue', 'at most one active dialogue')
    obj(state['tide'], ('state', 'tick'), path + '/tide')
    tides = {t['id']: t for t in game['tide']['states']}
    reference(state['tide']['state'], tides, path + '/tide/state')
    integer(state['tide']['tick'], path + '/tide/tick')
    if state['tide']['tick'] >= tides[state['tide']['state']]['duration']:
        fail(path + '/tide/tick', 'tick outside tide duration')
