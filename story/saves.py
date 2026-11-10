"""Provenance-bound saves and explicit, audited state migrations."""
import copy
import re
from .compiler import canonical, validate_game
from .engine import Engine
from .checker import Search
from .errors import SpecError, StateError
from .validation import obj
from .extensions import extended

STATE_KEYS = ('location', 'inventory', 'flags', 'dialogue', 'tide')
MAP_KEYS = ('rooms', 'items', 'flags', 'dialogues', 'nodes', 'tides')


def state_keys(game):
    return STATE_KEYS + (('collected',) if extended(game) else ())


def map_keys(game):
    return MAP_KEYS + (('collectibles',) if extended(game) else ())


def same_version(old, new):
    if old['contract_version'] != new['contract_version']:
        raise SpecError('cross-contract version migration is not supported')


def domains(game):
    result = {k: {x['id'] for x in game[k]} for k in ('rooms', 'items', 'flags', 'dialogues')}
    result['nodes'] = {d['id'] + ':' + n['id'] for d in game['dialogues'] for n in d['nodes']}
    result['tides'] = {x['id'] for x in game['tide']['states']}
    if extended(game):
        result['collectibles'] = {x['id'] for x in game['collectibles']}
    return result


def migration_manifest(source_game, target_game):
    from .modules import enabled
    if enabled(source_game) or enabled(target_game):
        from .modules.save_codec import migration_manifest as module_manifest
        return module_manifest(source_game, target_game)
    validate_game(source_game)
    validate_game(target_game)
    same_version(source_game, target_game)
    return {'contract_version': source_game['contract_version'], 'from_spec_hash': source_game['spec_hash'],
            'from_game_hash': source_game['game_hash'], 'to_spec_hash': target_game['spec_hash'],
            'to_game_hash': target_game['game_hash'],
            'maps': {k: {key: key.split(':', 1)[1] if k == 'nodes' else key for key in sorted(values)}
                     for k, values in domains(source_game).items()}}


def reachable_state(game, state, max_states):
    from .modules import enabled
    if enabled(game):
        from .modules.save_codec import reachable_state as module_reachable
        return module_reachable(game, state, max_states)
    engine = Engine(game)
    wanted = engine.from_dict(state)
    if extended(game):
        from .symbolic import SymbolicSearch
        from .bdd import BudgetExceeded
        try:
            search = SymbolicSearch(engine).run(max_states)
        except BudgetExceeded as exc:
            raise StateError(str(exc) + '; save membership proof incomplete') from exc
        reachable = search.contains(wanted)
    else:
        search = Search(engine, max_states)
        if not search.complete:
            raise StateError('state cap reached; save membership proof incomplete')
        reachable = wanted in search.index
    if not reachable:
        raise StateError('unreachable save state in game ' + game['game_hash'])
    if len(engine.endings(wanted)) > 1:
        raise StateError('ambiguous terminal save state')
    return wanted


def make_save(game, state, timestamps=None):
    from .modules import enabled
    if enabled(game):
        from .modules.save_codec import make_save as module_save
        return module_save(game, state, timestamps)
    validate_game(game)
    reachable_state(game, state, 100000)
    result = copy.deepcopy(state)
    result['inventory'].sort()
    if extended(game):
        result['collected'].sort()
    result.update(contract_version=game['contract_version'], spec_hash=game['spec_hash'], game_hash=game['game_hash'])
    if timestamps is not None:
        if not isinstance(timestamps, dict):
            raise SpecError('timestamps must be an object')
        canonical(timestamps)
        result['timestamps'] = copy.deepcopy(timestamps)
    return result


def validate_save(save, game, max_states):
    from .modules import enabled
    if enabled(game):
        from .modules.save_codec import validate_save as module_validate_save
        return module_validate_save(save, game, max_states)
    if not isinstance(save, dict):
        raise SpecError('save must be an object')
    keys = state_keys(game) + ('contract_version', 'spec_hash', 'game_hash')
    obj(save, keys + (('timestamps',) if 'timestamps' in save else ()), 'save')
    if save['contract_version'] != game['contract_version']:
        raise SpecError('unsupported save contract version')
    for key in ('spec_hash', 'game_hash'):
        if not isinstance(save[key], str) or re.fullmatch('[0-9a-f]{64}', save[key]) is None:
            raise SpecError('save ' + key + ' is not a valid hash')
        if save[key] != game[key]:
            raise SpecError('save {} does not match exact source game'.format(key))
    state = {k: copy.deepcopy(save[k]) for k in state_keys(game)}
    reachable_state(game, state, max_states)
    if save['inventory'] != sorted(save['inventory']):
        raise SpecError('save inventory must be sorted')
    if extended(game) and save['collected'] != sorted(save['collected']):
        raise SpecError('save collected IDs must be sorted')
    if 'timestamps' in save and not isinstance(save['timestamps'], dict):
        raise SpecError('timestamps must be an object')
    canonical(save)
    return state


def validate_manifest(manifest, old, new):
    obj(manifest, ('contract_version', 'from_spec_hash', 'from_game_hash', 'to_spec_hash', 'to_game_hash', 'maps'), 'manifest')
    same_version(old, new)
    if manifest['contract_version'] != old['contract_version']:
        raise SpecError('unsupported manifest contract version')
    for prefix, game in [('from_', old), ('to_', new)]:
        for key in ('spec_hash', 'game_hash'):
            if manifest[prefix + key] != game[key]:
                raise SpecError('manifest provenance mismatch: ' + prefix + key)
    maps = manifest['maps']
    obj(maps, map_keys(old), 'manifest/maps')
    old_domains, new_domains = domains(old), domains(new)
    for kind in map_keys(old):
        if not isinstance(maps[kind], dict):
            raise SpecError('manifest map must be object: ' + kind)
        if set(maps[kind]) - old_domains[kind]:
            raise SpecError('manifest has unknown source mapping: ' + kind)
        occupied = set()
        for key in sorted(old_domains[kind]):
            default = key.split(':', 1)[1] if kind == 'nodes' else key
            target = maps[kind].get(key, default)
            if target is None:
                if kind not in ('items', 'flags', 'dialogues', 'collectibles'):
                    raise SpecError('cannot drop ' + kind + ' mapping')
                continue
            if not isinstance(target, str):
                raise SpecError('manifest target must be string or permitted null')
            target_key = target
            if kind == 'nodes':
                did = key.split(':', 1)[0]
                target_did = maps['dialogues'].get(did, did)
                if target_did is None:
                    continue
                target_key = target_did + ':' + target
            # Identity for a deleted but unused source ID is checked at state mapping time.
            # Explicit renames, unlike identities, must always name a real destination.
            if target != default and target_key not in new_domains[kind]:
                raise SpecError('manifest missing destination {}/{}'.format(kind, target_key))
            if target_key in occupied:
                raise SpecError('manifest mapping collision in ' + kind)
            occupied.add(target_key)
    return maps


def migrate_save(save, source_game, target_game, manifest=None, max_states=100000):
    from .modules import enabled
    if enabled(source_game) or enabled(target_game):
        from .modules.save_codec import migrate_save as module_migrate_save
        return module_migrate_save(save, source_game, target_game, manifest, max_states)
    report = []
    try:
        validate_game(source_game)
        validate_game(target_game)
        same_version(source_game, target_game)
        state = validate_save(save, source_game, max_states)
        maps = {k: {} for k in map_keys(source_game)}
        if manifest is not None:
            maps = validate_manifest(manifest, source_game, target_game)
        same = all(source_game[k] == target_game[k] for k in ('spec_hash', 'game_hash'))
        if same:
            if any(value != (key.split(':', 1)[1] if kind == 'nodes' else key)
                   for kind in map_keys(source_game) for key, value in maps[kind].items()):
                raise SpecError('same-game save cannot apply nonidentity migration maps')
            return {'status': 'as_is', 'save': copy.deepcopy(save), 'report': [], 'reason': 'exact version, hashes and reachable state match'}
        new_domains = domains(target_game)

        def record(action, path, before, after, reason):
            report.append({'action': action, 'path': path, 'before': before, 'after': after, 'reason': reason})

        def mapped(kind, key, path, allow_drop=False):
            target = maps[kind].get(key, key)
            if target is None:
                if not allow_drop:
                    raise SpecError('cannot drop ' + path)
                record('dropped', path, key, None, 'explicit null mapping in migration manifest')
                return None
            if target not in new_domains[kind]:
                raise SpecError('missing target reference {}/{}; explicit remap/drop required'.format(kind, target))
            if target != key:
                record('remapped', path, key, target, 'explicit stable-ID mapping in migration manifest')
            return target

        state['location'] = mapped('rooms', state['location'], '/location')
        inventory = [mapped('items', item, '/inventory/' + item, True) for item in state['inventory']]
        state['inventory'] = sorted(i for i in inventory if i is not None)
        if extended(source_game):
            collected = [mapped('collectibles', cid, '/collected/' + cid, True) for cid in state['collected']]
            state['collected'] = sorted(cid for cid in collected if cid is not None)
        flags = {}
        for fid, value in sorted(state['flags'].items()):
            target = mapped('flags', fid, '/flags/' + fid, True)
            if target is not None:
                if target in flags:
                    raise SpecError('flag mapping collision')
                flags[target] = value
        for flag in target_game['flags']:
            if flag['id'] not in flags:
                flags[flag['id']] = flag['initial']
                record('added', '/flags/' + flag['id'], None, flag['initial'], 'new target flag initialized from declared default')
        state['flags'] = flags
        dialogue = {}
        for did, cursor in sorted(state['dialogue'].items()):
            if cursor and maps['dialogues'].get(did, did) is None:
                raise SpecError('cannot drop active dialogue ' + did)
            target = mapped('dialogues', did, '/dialogue/' + did, True)
            if target is None:
                continue
            new_cursor = maps['nodes'].get(did + ':' + cursor, cursor) if cursor else ''
            if cursor and new_cursor != cursor:
                record('remapped', '/dialogue/' + did + '/node', cursor, new_cursor, 'explicit node mapping in migration manifest')
            if target in dialogue:
                raise SpecError('dialogue mapping collision')
            dialogue[target] = new_cursor
        for did in sorted(new_domains['dialogues']):
            if did not in dialogue:
                dialogue[did] = target_game['start']['dialogue'][did]
                record('added', '/dialogue/' + did, None, dialogue[did], 'new target dialogue initialized from declared default')
        state['dialogue'] = dialogue
        state['tide']['state'] = mapped('tides', state['tide']['state'], '/tide/state')
        reachable_state(target_game, state, max_states)
        result = copy.deepcopy(save)
        result.update(state)
        for key in ('spec_hash', 'game_hash'):
            result[key] = target_game[key]
            record('rebound', '/' + key, save[key], result[key], 'validated source-to-target content revision; state retained except listed changes')
        return {'status': 'migrated', 'save': result, 'report': report, 'reason': 'source verified; explicit migration yields reachable target state'}
    except (SpecError, StateError, ValueError, TypeError) as exc:
        return {'status': 'rejected', 'save': None, 'report': report, 'reason': str(exc)}
