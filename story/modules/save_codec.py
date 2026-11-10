"""Checkpoint-only save v2 with exact build pins and explicit legacy conversion."""
import copy
from ..compiler import canonical, digest, validate_game
from ..errors import SpecError, StateError
from ..validation import obj
from . import enabled
from .model import AnalysisEngine
from .analysis import ModuleSearch
from .registry import entity_map

SAVE_VERSION = '2.0.0'


def reachable_state(game, state, max_states=100000):
    if type(max_states) is not int or not 1 <= max_states <= 100000:
        raise StateError('state cap must be from 1 to 100000')
    engine = AnalysisEngine(game)
    wanted = engine.from_dict(state)
    search = ModuleSearch(engine, max_states)
    if not search.complete:
        raise StateError('state cap reached; checkpoint membership proof incomplete')
    if wanted not in search.index:
        raise StateError('unreachable module checkpoint state')
    if len(engine.endings(wanted)) > 1:
        raise StateError('ambiguous terminal checkpoint state')
    return wanted


def safe(game, state):
    engine = AnalysisEngine(game)
    st = engine.from_dict(state)
    if st.modules.active or st.modules.failed:
        raise StateError('active/failed attempt is not a committed checkpoint; retry or abort then reset first')
    if st.location != engine.checkpoints[st.modules.checkpoint]['room']:
        raise StateError('save location is not the committed safe checkpoint room')
    return st


def make_save(game, state, timestamps=None):
    validate_game(game)
    safe(game, state)
    reachable_state(game, state)
    result = {'save_version': SAVE_VERSION, 'contract_version': '1.2.0',
              'spec_hash': game['spec_hash'], 'game_hash': game['game_hash'],
              'module_contract_hash': digest(game['module_contract']), 'state': copy.deepcopy(state)}
    result['state']['inventory'].sort()
    result['state']['collected'].sort()
    if timestamps is not None:
        if not isinstance(timestamps, dict):
            raise SpecError('timestamps must be an object')
        result['timestamps'] = copy.deepcopy(timestamps)
    canonical(result)
    return result


def validate_save(save, game, max_states=100000):
    validate_game(game)
    obj(save, ('save_version', 'contract_version', 'spec_hash', 'game_hash', 'module_contract_hash', 'state')
        + (('timestamps',) if isinstance(save, dict) and 'timestamps' in save else ()), 'save')
    if save['save_version'] != SAVE_VERSION or save['contract_version'] != '1.2.0':
        raise SpecError('unsupported module save version')
    for key in ('spec_hash', 'game_hash'):
        if save[key] != game[key]:
            raise SpecError('save provenance/hash mismatch: ' + key)
    if save['module_contract_hash'] != digest(game['module_contract']):
        raise SpecError('save module contract hash mismatch')
    st = safe(game, save['state'])
    reachable_state(game, save['state'], max_states)
    if save['state']['inventory'] != sorted(save['state']['inventory']) or save['state']['collected'] != sorted(save['state']['collected']):
        raise SpecError('checkpoint inventory/collected must be sorted')
    if 'timestamps' in save and not isinstance(save['timestamps'], dict):
        raise SpecError('timestamps must be an object')
    canonical(save)
    return copy.deepcopy(save['state'])


def migration_manifest(old, new):
    validate_game(old)
    validate_game(new)
    if not enabled(new) or old['contract_version'] not in ('1.1.0', '1.2.0'):
        raise SpecError('unsupported checkpoint migration version pair')
    return {'migration_version': '1.0.0', 'mode': 'initialize_modules' if not enabled(old) else 'identity_checkpoint',
            'from_contract_version': old['contract_version'], 'to_contract_version': new['contract_version'],
            'from_spec_hash': old['spec_hash'], 'from_game_hash': old['game_hash'],
            'to_spec_hash': new['spec_hash'], 'to_game_hash': new['game_hash']}


def migrate_save(save, old, new, manifest=None, max_states=100000):
    from ..saves import validate_save as validate_any_save
    try:
        expected = migration_manifest(old, new)
        if not enabled(old) and manifest is None:
            raise SpecError('MIGRATION_REQUIRED: explicit 1.1.0 to 1.2.0 initialize_modules manifest required')
        if manifest is not None and canonical(manifest) != canonical(expected):
            raise SpecError('migration manifest provenance/mode mismatch; remapping IDs is not supported by this converter')
        state = validate_any_save(save, old, max_states)
        if old['id'] != new['id']:
            raise SpecError('checkpoint migration requires the same game identity')
        if old['game_hash'] == new['game_hash']:
            return {'status': 'as_is', 'save': copy.deepcopy(save), 'report': [], 'reason': 'exact checkpoint and build match'}
        changes = []
        if not enabled(old):
            state['modules'] = copy.deepcopy(new['start']['modules'])
            state['modules']['completed'] = []
            state['modules']['active'] = ''
            state['modules']['failed'] = ''
            checkpoints = entity_map(new, 'challenge', 'checkpoints')
            possible = sorted(cid for cid, p in checkpoints.items() if p['room'] == state['location'])
            if not possible:
                raise StateError('no approved safe checkpoint in legacy saved room')
            state['modules']['checkpoint'] = possible[0]
            state['modules']['discovered'] = sorted(rid for rid, r in entity_map(new, 'regions', 'regions').items() if r['room'] == state['location'])
            changes.append({'action': 'initialized_modules', 'reason': 'Explicit conversion; no challenges credited. Abstract target membership is required.'})
        if enabled(old):
            old_ids = entity_map(old, 'abilities', 'abilities')
            added = [aid for aid in new['start']['modules']['abilities'] if aid not in old_ids]
            if added:
                state['modules']['abilities'] = sorted(set(state['modules']['abilities']) | set(added))
                changes.append({'action': 'initialized_new_abilities', 'abilities': added,
                                'reason': 'New stable IDs with explicit initial grants; existing abilities unchanged.'})
        safe(new, state)
        reachable_state(new, state, max_states)
        result = make_save(new, state, save.get('timestamps'))
        changes.append({'action': 'rebound_build', 'from': old['game_hash'], 'to': new['game_hash'],
                        'reason': 'Source provenance and target abstract checkpoint membership checked; physical history not certified.'})
        return {'status': 'migrated', 'save': result, 'report': changes,
                'reason': 'Checkpoint migrated without replaying rewards; physical receipts invalidated.'}
    except (SpecError, StateError, ValueError, TypeError) as exc:
        return {'status': 'rejected', 'save': None, 'report': [], 'reason': str(exc)}
