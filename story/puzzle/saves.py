"""STORY 1.3 checkpoint saves: the 1.2 save v2 shape plus puzzle facts and the puzzle contract pin.

A checkpoint in a puzzle room sits on the puzzle start cell and committing it resets the room, so a save
never holds transient grid state and its ``entry`` is always empty. Solved/taken/opened/latched facts are
monotone and survive save/load.
"""
import copy
from ..compiler import canonical, digest
from ..errors import SpecError, StateError
from ..validation import obj
from ..modules.analysis import ModuleSearch
from ..modules import save_codec as save12
from . import is13
from .compiler import validate_game
from .model import PuzzleAnalysisEngine
from .rules import EMPTY_FACTS

SAVE_VERSION = '2.0.0'
FIELDS = ('save_version', 'contract_version', 'spec_hash', 'game_hash', 'module_contract_hash', 'puzzle_contract_hash', 'state')


def reachable_state(game, state, max_states=100000):
    if type(max_states) is not int or not 1 <= max_states <= 100000:
        raise StateError('state cap must be from 1 to 100000')
    engine = PuzzleAnalysisEngine(game)
    wanted = engine.from_dict(state)
    search = ModuleSearch(engine, max_states)
    if not search.complete:
        raise StateError('state cap reached; checkpoint membership proof incomplete')
    if wanted not in search.index:
        raise StateError('unreachable puzzle checkpoint state')
    if len(engine.endings(wanted)) > 1:
        raise StateError('ambiguous terminal checkpoint state')
    return engine, wanted


def safe(engine, st):
    if st.modules.active or st.modules.failed:
        raise StateError('active/failed attempt is not a committed checkpoint; retry or abort then reset first')
    if st.location != engine.checkpoints[st.modules.checkpoint]['room']:
        raise StateError('save location is not the committed safe checkpoint room')
    if st.entry:
        raise StateError('transient puzzle visits are never saved')
    return st


def make_save(game, state, timestamps=None, max_states=100000):
    validate_game(game)
    engine, st = reachable_state(game, state, max_states)
    safe(engine, st)
    result = {'save_version': SAVE_VERSION, 'contract_version': game['contract_version'],
              'spec_hash': game['spec_hash'], 'game_hash': game['game_hash'],
              'module_contract_hash': digest(game['module_contract']),
              'puzzle_contract_hash': digest(game['puzzle_contract']), 'state': copy.deepcopy(state)}
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
    obj(save, FIELDS + (('timestamps',) if isinstance(save, dict) and 'timestamps' in save else ()), 'save')
    if save['save_version'] != SAVE_VERSION or save['contract_version'] != game['contract_version']:
        raise SpecError('unsupported puzzle save version')
    for key in ('spec_hash', 'game_hash'):
        if save[key] != game[key]:
            raise SpecError('save provenance/hash mismatch: ' + key)
    if save['module_contract_hash'] != digest(game['module_contract']):
        raise SpecError('save module contract hash mismatch')
    if save['puzzle_contract_hash'] != digest(game['puzzle_contract']):
        raise SpecError('save puzzle contract hash mismatch')
    engine, st = reachable_state(game, save['state'], max_states)
    safe(engine, st)
    if save['state']['inventory'] != sorted(save['state']['inventory']) or save['state']['collected'] != sorted(save['state']['collected']):
        raise SpecError('checkpoint inventory/collected must be sorted')
    if 'timestamps' in save and not isinstance(save['timestamps'], dict):
        raise SpecError('timestamps must be an object')
    canonical(save)
    return copy.deepcopy(save['state'])


RUNTIME_STATE_LIMIT = 4096


def runtime_states(game, max_states=100000):
    """Every safe checkpoint state of a 1.3 build in the lowered (runtime) shape, sorted canonically.

    The Godot runtime executes the lowered 1.2 build, whose own membership search cannot set reserved puzzle
    flags; the build ships this proved set in the puzzle sidecar and the module save codec checks membership
    against it instead (runtime/godot/modules/save_codec.gd)."""
    from ..modules.model import ModuleEngine
    validate_game(game)
    engine = PuzzleAnalysisEngine(game)
    search = ModuleSearch(engine, max_states)
    if not search.complete:
        raise StateError('state cap reached; runtime checkpoint membership set incomplete')
    rows = {}
    for st in search.states:
        if st.entry or st.modules.active or st.modules.failed:
            continue
        if st.location != engine.checkpoints[st.modules.checkpoint]['room'] or len(engine.endings(st)) > 1:
            continue
        low = ModuleEngine.to_dict(engine, st)
        rows[canonical(low)] = low
    if len(rows) > RUNTIME_STATE_LIMIT:
        raise StateError('more than ' + str(RUNTIME_STATE_LIMIT) + ' safe checkpoint states; split the game or reduce checkpoints')
    return [rows[k] for k in sorted(rows)]


def from_runtime_save(save, game, max_states=100000):
    """A checkpoint written by the Godot runtime (lowered 1.2 save of the embedded build) -> 1.3 save.

    Provenance is checked against the embedded 1.2 identity; membership is proved by ``make_save`` under the
    1.3 semantics (puzzle transitions included)."""
    from .compiler import lowered_game
    from .lowering import raise_state
    validate_game(game)
    low = lowered_game(game)
    obj(save, ('save_version', 'contract_version', 'spec_hash', 'game_hash', 'module_contract_hash', 'state')
        + (('timestamps',) if isinstance(save, dict) and 'timestamps' in save else ()), 'save')
    if save['save_version'] != '2.0.0' or save['contract_version'] != '1.2.0':
        raise SpecError('runtime save is not a v2 STORY 1.2 checkpoint')
    for key in ('spec_hash', 'game_hash'):
        if save[key] != low[key]:
            raise SpecError('runtime save provenance mismatch: ' + key)
    if save['module_contract_hash'] != digest(low['module_contract']):
        raise SpecError('runtime save module contract hash mismatch')
    return make_save(game, raise_state(save['state'], ''), save.get('timestamps'), max_states)


def to_runtime_save(save, game, max_states=100000):
    """Inverse of ``from_runtime_save``: the exact lowered checkpoint the Godot runtime loads."""
    from .compiler import lowered_game
    from .lowering import lower_state
    from .rules import fact_rows
    state = validate_save(save, game, max_states)
    low = lowered_game(game)
    flat, entry = lower_state(state, fact_rows({'entities': {'puzzles': game['puzzle']['puzzles']}}))
    if entry:
        raise StateError('transient puzzle visits are never saved')
    result = {'save_version': '2.0.0', 'contract_version': '1.2.0', 'spec_hash': low['spec_hash'], 'game_hash': low['game_hash'],
              'module_contract_hash': digest(low['module_contract']), 'state': flat}
    if 'timestamps' in save:
        result['timestamps'] = copy.deepcopy(save['timestamps'])
    canonical(result)
    return result


def migration_manifest(old, new):
    validate_game(new)
    if is13(old):
        validate_game(old)
        mode = 'identity_puzzles'
    elif isinstance(old, dict) and old.get('contract_version') == '1.2.0':
        from ..compiler import validate_game as validate12
        validate12(old)
        mode = 'initialize_puzzles'
    else:
        raise SpecError('unsupported puzzle migration version pair')
    return {'migration_version': '1.0.0', 'mode': mode, 'from_contract_version': old['contract_version'],
            'to_contract_version': new['contract_version'], 'from_spec_hash': old['spec_hash'],
            'from_game_hash': old['game_hash'], 'to_spec_hash': new['spec_hash'], 'to_game_hash': new['game_hash']}


def migrate_save(save, old, new, manifest=None, max_states=100000):
    """Carry a checkpoint to a new 1.3 build without renames: facts must still name existing elements and the
    state must be a reachable safe checkpoint of the new build. 1.2 to 1.3 needs the explicit manifest."""
    try:
        expected = migration_manifest(old, new)
        if expected['mode'] == 'initialize_puzzles' and manifest is None:
            raise SpecError('MIGRATION_REQUIRED: explicit 1.2.0 to 1.3.0 initialize_puzzles manifest required')
        if manifest is not None and canonical(manifest) != canonical(expected):
            raise SpecError('migration manifest provenance/mode mismatch; remapping IDs is not supported by this converter')
        if old['id'] != new['id']:
            raise SpecError('checkpoint migration requires the same game identity')
        changes = []
        if expected['mode'] == 'identity_puzzles':
            state = validate_save(save, old, max_states)
            if old['game_hash'] == new['game_hash']:
                return {'status': 'as_is', 'save': copy.deepcopy(save), 'report': [], 'reason': 'exact checkpoint and build match'}
        else:
            state = save12.validate_save(save, old, max_states)
            state['modules']['puzzle'] = copy.deepcopy(EMPTY_FACTS)
            changes.append({'action': 'initialized_puzzles', 'reason': 'Explicit conversion; no puzzle credited, no key or lock fact invented.'})
        result = make_save(new, state, save.get('timestamps'), max_states)
        changes.append({'action': 'rebound_build', 'from': old['game_hash'], 'to': new['game_hash'],
                        'reason': 'Source provenance and target checkpoint membership checked; physical history not certified.'})
        return {'status': 'migrated', 'save': result, 'report': changes,
                'reason': 'Checkpoint migrated without replaying puzzles; physical receipts invalidated.'}
    except (SpecError, StateError, ValueError, TypeError, KeyError) as exc:
        return {'status': 'rejected', 'save': None, 'report': [], 'reason': str(exc)}
