"""Typed, pure STORY 1.3 candidate edits: every 1.2 kind plus four puzzle kinds. No generic patching."""
import copy
from ..compiler import canonical
from ..edits import structured_diff
from ..errors import SpecError
from ..modules import schema as S
from ..modules.edits import operation_schema as operation_schema12, accepted
from ..modules.registry import index, entity_map
from . import is13
from .compiler import compile_spec
from .analysis import check
from .saves import migration_manifest, migrate_save
from .rules import CELL, LINK

PUZZLE_KINDS = ('add-switch', 'link-door', 'move-block', 'set-solution-hint')
CORE_KINDS = ('add-enemy', 'modify-enemy', 'change-arena', 'gate-region', 'change-course-checkpoints', 'add-ability')


def puzzle_operations():
    def op(kind, **fields):
        schema = S.obj(kind={'const': kind}, **fields)
        schema['properties']['expected_changed_rooms'] = S.array(S.ID, 100, unique=True)
        return schema
    switch = S.obj(id=S.ID, cell=CELL, mode=S.enum('toggle', 'latch'))
    return [op('add-switch', puzzle=S.ID, switch=switch),
            op('link-door', puzzle=S.ID, door=S.ID, when=LINK),
            op('move-block', puzzle=S.ID, block=S.ID, cell=CELL),
            op('set-solution-hint', puzzle=S.ID, hint=S.array(S.ID, 16, unique=True))]


def operation_schema():
    """The 1.2 union (unchanged members, same order) with the four puzzle members appended."""
    return {'oneOf': operation_schema12()['oneOf'] + puzzle_operations()}


def puzzle_edit(candidate, operation):
    puzzles = entity_map(candidate, 'puzzle', 'puzzles')
    if operation['puzzle'] not in puzzles:
        raise SpecError('missing edit target: ' + operation['puzzle'])
    p = puzzles[operation['puzzle']]
    elements = {e['id']: e for e in p['elements']}
    kind = operation['kind']
    if kind == 'add-switch':
        sw = operation['switch']
        if sw['id'] in elements:
            raise SpecError('duplicate element id ' + sw['id'])
        p['elements'].append({'id': sw['id'], 'kind': 'switch', 'cell': list(sw['cell']), 'mode': sw['mode']})
    elif kind == 'link-door':
        if operation['door'] == 'goal':
            p['goal']['when'] = copy.deepcopy(operation['when'])
        else:
            target = elements.get(operation['door'])
            if target is None or target['kind'] not in ('door', 'timed_gate', 'bridge'):
                raise SpecError('link-door needs a door, timed gate, bridge or goal: ' + operation['door'])
            target['when'] = copy.deepcopy(operation['when'])
    elif kind == 'move-block':
        target = elements.get(operation['block'])
        if target is None or target['kind'] != 'block':
            raise SpecError('move-block needs a block: ' + operation['block'])
        target['cell'] = list(operation['cell'])
    else:
        p['hint'] = list(operation['hint'])


def core_edit(candidate, operation):
    """The STORY 1.2 typed kinds, applied to a 1.3 source with identical semantics."""
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
        raise SpecError('regions are not available with the STORY 1.3.0 puzzle family')
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


def changed_rooms(old, new):
    old_rooms = {r['id']: r for r in old['rooms']}
    old_side, new_side = old['puzzle']['room_hashes'], new['puzzle']['room_hashes']
    changed, unchanged, hashes = [], [], {}
    for room in new['rooms']:
        rid = room['id']
        same = canonical(room) == canonical(old_rooms[rid]) and old_side.get(rid) == new_side.get(rid)
        (unchanged if same else changed).append(rid)
        hashes[rid] = {'before': old_rooms[rid]['build_hash'], 'after': room['build_hash'],
                       'puzzle_before': old_side.get(rid, ''), 'puzzle_after': new_side.get(rid, ''), 'byte_identical': same}
    return changed, unchanged, hashes


def edit(spec, operation, expected_spec_hash, expected_game_hash, save=None):
    if not is13(spec):
        raise SpecError('puzzle edits require STORY 1.3.0')
    old = compile_spec(spec)
    if old['spec_hash'] != expected_spec_hash or old['game_hash'] != expected_game_hash:
        raise SpecError('revision conflict: expected source/build hashes differ')
    S.validate(operation, operation_schema(), 'operation')
    baseline = check(old)
    if not accepted(baseline, spec):
        raise SpecError('baseline has not passed its declared module proof policy')
    candidate = copy.deepcopy(spec)
    if operation['kind'] in PUZZLE_KINDS:
        puzzle_edit(candidate, operation)
    else:
        core_edit(candidate, operation)
    new = compile_spec(candidate)
    proof = check(new)
    changed, unchanged, hashes = changed_rooms(old, new)
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
