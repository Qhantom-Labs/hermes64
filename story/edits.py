"""Pure spec edits; every returned candidate includes proof and hash regression."""
import copy
from .compiler import canonical, compile_spec
from .checker import check_game
from .errors import SpecError
from .saves import migration_manifest


def structured_diff(before, after, path=''):
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(set(before) | set(after)):
            at = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                rows.append({'path': at, 'before': copy.deepcopy(before.get(key)), 'after': copy.deepcopy(after.get(key))})
            else:
                rows.extend(structured_diff(before[key], after[key], at))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        all_values = before + after
        if all_values and all(isinstance(x, dict) and 'id' in x for x in all_values):
            return structured_diff({x['id']: x for x in before}, {x['id']: x for x in after}, path)
    return [{'path': path or '/', 'before': copy.deepcopy(before), 'after': copy.deepcopy(after)}]


def finish(original, candidate):
    old, new = compile_spec(original), compile_spec(candidate)
    old_rooms, new_rooms = ({r['id']: r for r in g['rooms']} for g in (old, new))
    hashes, changed, unchanged = {}, [], []
    for rid in sorted(set(old_rooms) | set(new_rooms)):
        a, b = old_rooms.get(rid), new_rooms.get(rid)
        same = a is not None and b is not None and a['build_hash'] == b['build_hash']
        identical = a is not None and b is not None and canonical(a) == canonical(b)
        (unchanged if same else changed).append(rid)
        hashes[rid] = {'before': a['build_hash'] if a else None, 'after': b['build_hash'] if b else None,
                       'byte_identical': identical}
    return {'spec': copy.deepcopy(candidate), 'game': new, 'diff': structured_diff(original, candidate),
            'regression': {'solvability': check_game(new), 'changed_rooms': changed, 'unchanged_rooms': unchanged,
                           'room_hashes': hashes, 'unchanged_byte_identical': all(hashes[r]['byte_identical'] for r in unchanged)},
            'migration': migration_manifest(old, new)}


def lookup(values, id, kind):
    for x in values:
        if x['id'] == id:
            return x
    raise SpecError('{} {} not found'.format(kind, id))


def move_entrance(spec, room, door, wall, position):
    compile_spec(spec)
    candidate = copy.deepcopy(spec)
    r = lookup(candidate['rooms'], room, 'room')
    d = lookup(r['doors'], door, 'door')
    d.update(wall=wall, position=position)
    return finish(spec, candidate)


def change_role(spec, character, role):
    compile_spec(spec)
    candidate = copy.deepcopy(spec)
    c = lookup(candidate['characters'], character, 'character')
    if role not in c['role_profiles']:
        raise SpecError('unknown role {} for {}'.format(role, character))
    old_role = c['role']
    c['role'] = role
    c['params'] = copy.deepcopy(c['role_profiles'][role])

    def rewrite(value):
        if isinstance(value, dict):
            for condition in value.get('conditions', []):
                if condition.get('role') == character and condition.get('equals') == old_role:
                    condition['equals'] = role
            for key, child in value.items():
                if key != 'metadata':
                    rewrite(child)
        elif isinstance(value, list):
            for child in value:
                rewrite(child)
    rewrite(candidate)
    for dialogue in candidate['dialogues']:
        if dialogue['character'] == character:
            for node in dialogue['nodes']:
                if role in node.get('role_text', {}):
                    node['text'] = node['role_text'][role]
    return finish(spec, candidate)


def add_ending(spec, id, conditions, text, trigger):
    compile_spec(spec)
    candidate = copy.deepcopy(spec)
    flag_id = 'ending_' + id
    if any(e['id'] == id for e in candidate['endings']):
        raise SpecError('ending {} already exists'.format(id))
    if any(f['id'] == flag_id for f in candidate['flags']):
        raise SpecError('flag {} already exists'.format(flag_id))
    if not isinstance(trigger, dict) or 'id' not in trigger:
        raise SpecError('trigger requires interaction id')
    if any(a['id'] == trigger['id'] for a in candidate['interactions']):
        raise SpecError('trigger interaction {} already exists'.format(trigger['id']))
    candidate['flags'].append({'id': flag_id, 'initial': False, 'description': 'Explicit trigger for ending ' + id})
    candidate['start']['flags'][flag_id] = False
    candidate['endings'].append({'id': id, 'conditions': copy.deepcopy(conditions) + [{'flag': flag_id, 'equals': True}], 'text': text})
    interaction = copy.deepcopy(trigger)
    if not isinstance(interaction.get('effects'), list):
        raise SpecError('trigger effects must be array')
    interaction['effects'].append({'flag': flag_id, 'value': True})
    candidate['interactions'].append(interaction)
    return finish(spec, candidate)
