"""Typed, pure candidate edits. No source mutation or adoption on a failed gate."""
import copy
from ..compiler import canonical, compile_spec
from ..checker import check_game
from ..edits import structured_diff
from ..errors import SpecError
from ..saves import migration_manifest, migrate_save
from . import enabled
from . import schema as S
from .registry import index, entity_map


def partial(schema):
    return dict(schema, required=[])


def operation_schema():
    def op(kind, **fields):
        schema = S.obj(kind={'const': kind}, **fields)
        schema['properties']['expected_changed_rooms'] = S.array(S.ID, 100, unique=True)
        return schema
    enemy_changes = partial(S.obj(**{k: v for k, v in S.ENEMY['properties'].items() if k != 'id'}))
    arena_changes = partial(S.obj(**{k: S.ENCOUNTER['properties'][k] for k in ('arena', 'spawns', 'room')}))
    grant = {'oneOf': [S.obj(kind={'const': 'initial'}), S.obj(kind={'const': 'interaction'}, id=S.ID), S.obj(kind={'const': 'challenge'}, id=S.ID)]}
    return {'oneOf': [op('add-enemy', enemy=S.ENEMY), op('modify-enemy', id=S.ID, changes=enemy_changes),
        op('change-arena', id=S.ID, changes=arena_changes),
        op('gate-region', id=S.ID, endpoint=S.enum('a', 'b'), conditions=S.CONDITIONS),
        op('change-course-checkpoints', id=S.ID, checkpoints=S.COURSE['properties']['checkpoints']),
        op('add-ability', ability=S.ABILITY, grant=grant)]}


def accepted(report, spec):
    return report['status'] == 'proved' or (report['status'] == 'conditional' and spec['gameplay']['verification_policy'] == 'conditional')


def edit(spec, operation, expected_spec_hash, expected_game_hash, save=None):
    old = compile_spec(spec)
    if not enabled(spec):
        raise SpecError('module edits require STORY 1.2.0')
    if old['spec_hash'] != expected_spec_hash or old['game_hash'] != expected_game_hash:
        raise SpecError('revision conflict: expected source/build hashes differ')
    S.validate(operation, operation_schema(), 'operation')
    baseline = check_game(old)
    if not accepted(baseline, spec):
        raise SpecError('baseline has not passed its declared module proof policy')
    candidate = copy.deepcopy(spec)
    mods = index(candidate)
    kind = operation['kind']
    def target(mid, collection, eid):
        values = entity_map(candidate, mid, collection)
        if eid not in values:
            raise SpecError('missing edit target: ' + eid)
        return values[eid]
    if kind == 'add-enemy':
        if 'combat' not in mods:
            raise SpecError('combat module is not enabled')
        mods['combat']['entities']['archetypes'].append(copy.deepcopy(operation['enemy']))
    elif kind == 'modify-enemy':
        if not operation['changes']:
            raise SpecError('empty enemy changes')
        target('combat', 'archetypes', operation['id']).update(copy.deepcopy(operation['changes']))
    elif kind == 'change-arena':
        if not operation['changes']:
            raise SpecError('empty arena changes')
        target('combat', 'encounters', operation['id']).update(copy.deepcopy(operation['changes']))
        if 'room' in operation['changes']:
            for c in entity_map(candidate, 'challenge', 'challenges').values():
                if c['kind'] == 'combat' and c['subject'] == operation['id']:
                    c['room'] = operation['changes']['room']
    elif kind == 'gate-region':
        endpoint = target('regions', 'links', operation['id'])[operation['endpoint']]
        region = target('regions', 'regions', endpoint['region'])
        room = next(r for r in candidate['rooms'] if r['id'] == region['room'])
        door = next(d for d in room['doors'] if d['id'] == endpoint['door'])
        door['conditions'] = copy.deepcopy(operation['conditions'])
    elif kind == 'change-course-checkpoints':
        target('course', 'tracks', operation['id'])['checkpoints'] = copy.deepcopy(operation['checkpoints'])
    elif kind == 'add-ability':
        aid = operation['ability']['id']
        mods['abilities']['entities']['abilities'].append(copy.deepcopy(operation['ability']))
        grant = operation['grant']
        if grant['kind'] == 'initial':
            candidate['start']['modules']['abilities'].append(aid)
            candidate['start']['modules']['abilities'].sort()
        elif grant['kind'] == 'challenge':
            target('challenge', 'challenges', grant['id'])['rewards']['abilities'].append(aid)
        else:
            actions = {a['id']: a for a in candidate['interactions']}
            if grant['id'] not in actions:
                raise SpecError('missing grant interaction')
            actions[grant['id']]['effects'].append({'unlock': aid})
    new = compile_spec(candidate)
    proof = check_game(new)
    old_rooms = {r['id']: r for r in old['rooms']}
    changed, unchanged, hashes = [], [], {}
    for room in new['rooms']:
        rid = room['id']
        same = canonical(room) == canonical(old_rooms[rid])
        (unchanged if same else changed).append(rid)
        hashes[rid] = {'before': old_rooms[rid]['build_hash'], 'after': room['build_hash'], 'byte_identical': same}
    manifest = migration_manifest(old, new)
    migrated = migrate_save(save, old, new, manifest) if save is not None else {'status': 'not_run', 'reason': 'No save supplied'}
    expected = operation.get('expected_changed_rooms')
    locality = 'not_run' if expected is None else 'passed' if sorted(expected) == changed else 'failed'
    identity = canonical(spec['characters']) == canonical(candidate['characters']) and spec['id'] == candidate['id']
    good = accepted(proof, candidate) and migrated['status'] != 'rejected' and locality != 'failed' and identity
    reg = {'solvability': proof, 'changed_rooms': changed, 'unchanged_rooms': unchanged, 'room_hashes': hashes,
           'unchanged_byte_identical': all(hashes[r]['byte_identical'] for r in unchanged),
           'identity_preserved': identity, 'expected_room_locality': locality}
    return {'ok': good, 'status': 'edited_data_only' if good else 'candidate_rejected', 'spec': candidate,
            'game': new, 'proof': proof, 'diff': structured_diff(spec, candidate), 'regression': reg,
            'migration': manifest, 'save_migration': migrated,
            'evidence_invalidated': {'physical': 'all_for_changed_build', 'human': 'all_for_changed_build',
                                     'affected_rooms': changed, 'runtime': 'not_run'}}
