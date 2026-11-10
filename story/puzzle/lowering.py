"""Exact, invertible lowering of a STORY 1.3 source/state onto STORY 1.2.

- the ``puzzle`` module leaves ``gameplay.modules`` (it becomes the compiled sidecar);
- every permanent puzzle fact gets a reserved flag (``puzzle__s__``/``t__``/``o__``/``l__``), initially false,
  that only the puzzle module sets;
- every condition ``{"puzzle": id, "status": "solved"}`` becomes ``{"flag": "puzzle__s__<id>", "equals": true}``;
- ``start.modules.puzzle`` / ``state.modules.puzzle`` facts become those flags; ``entry`` rides beside the
  1.2 state (it is always empty in a saved checkpoint).

Authored flags may not use the reserved prefix, so ``raise_*`` is the exact inverse of ``lower_*``.
"""
import copy
from ..errors import SpecError
from ..modules import schema as S
from . import PREFIX, VERSION, flag, fact_flag, parse_flag
from .rules import CONDITION, EMPTY_FACTS, FACTS, MODULE, module_of, fact_rows

DESCRIPTIONS = {'solved': 'Puzzle solved', 'taken': 'Puzzle key taken', 'opened': 'Puzzle lock opened',
                'latched': 'Puzzle latch set'}


def _walk(value, fn):
    if isinstance(value, dict):
        replaced = fn(value)
        if replaced is not None:
            return replaced
        return {k: _walk(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    return value


def lower_conditions(value, puzzle_ids, path='spec'):
    def fn(node):
        if 'puzzle' in node:
            S.validate(node, CONDITION, path + '/condition')
            if node['puzzle'] not in puzzle_ids:
                raise SpecError(path + ': missing puzzle reference ' + str(node['puzzle']))
            return {'flag': flag(node['puzzle']), 'equals': True}
        if isinstance(node.get('flag'), str) and node['flag'].startswith(PREFIX):
            raise SpecError(path + ': reserved puzzle__ flags cannot be authored; use a puzzle condition')
        return None
    return _walk(value, fn)


def raise_conditions(value):
    def fn(node):
        if set(node) == {'flag', 'equals'} and isinstance(node['flag'], str) and node['flag'].startswith(PREFIX):
            parsed = parse_flag(node['flag'])
            if parsed is None or parsed[0] != 'solved' or node['equals'] is not True:
                raise SpecError('only solved puzzle flags with equals true may appear in lowered conditions')
            return {'puzzle': parsed[1], 'status': 'solved'}
        return None
    return _walk(value, fn)


def split(spec):
    """Return (1.2 source without puzzle data, puzzle module, start facts); the module is schema-checked."""
    if not isinstance(spec, dict) or spec.get('contract_version') != VERSION:
        raise SpecError('expected a STORY 1.3.0 source')
    if not isinstance(spec.get('gameplay'), dict) or not isinstance(spec['gameplay'].get('modules'), list):
        raise SpecError('STORY 1.3.0 source requires gameplay.modules')
    if not isinstance(spec.get('start'), dict) or not isinstance(spec.get('flags'), list):
        raise SpecError('STORY 1.3.0 source requires start and flags')
    module = module_of(spec)
    if module is None:
        raise SpecError('STORY 1.3.0 requires the puzzle module')
    S.validate(module, MODULE, 'gameplay/puzzle')
    base = copy.deepcopy(spec)
    base['contract_version'] = '1.2.0'
    base['gameplay']['modules'] = [m for m in base['gameplay']['modules'] if not (isinstance(m, dict) and m.get('id') == 'puzzle')]
    start_modules = base['start'].get('modules')
    if not isinstance(start_modules, dict) or 'puzzle' not in start_modules:
        raise SpecError('start/modules/puzzle facts are required in STORY 1.3.0')
    facts = start_modules.pop('puzzle')
    return base, copy.deepcopy(module), facts


def lower_spec(spec):
    base, module, facts = split(spec)
    if facts != EMPTY_FACTS:
        raise SpecError('start/modules/puzzle: initial puzzle facts must be empty with no entry door')
    ids = {p['id'] for p in module['entities']['puzzles']}
    reserved = [f for f in base['flags'] if isinstance(f, dict) and str(f.get('id', '')).startswith(PREFIX)]
    if reserved:
        raise SpecError('flags/' + str(reserved[0].get('id')) + ': the puzzle__ flag prefix is reserved')
    if not isinstance(base['start'].get('flags'), dict):
        raise SpecError('start/flags must be an object')
    for key in [k for k in base if k != 'contract_version']:
        base[key] = lower_conditions(base[key], ids, key)
    for field, eid in fact_rows(module):
        name = fact_flag(field, eid)
        if any(f.get('id') == name for f in base['flags'] if isinstance(f, dict)):
            raise SpecError('duplicate reserved flag ' + name)
        base['flags'].append({'id': name, 'description': DESCRIPTIONS[field] + ' (set only by the puzzle module).', 'initial': False})
        base['start']['flags'][name] = False
    return base, module


def raise_spec(base, module):
    """Inverse of lower_spec on a normalized 1.2 source."""
    spec = copy.deepcopy(base)
    spec['contract_version'] = VERSION
    spec['flags'] = [f for f in spec['flags'] if not f['id'].startswith(PREFIX)]
    spec['start']['flags'] = {k: v for k, v in spec['start']['flags'].items() if not k.startswith(PREFIX)}
    for key in [k for k in spec if k != 'contract_version']:
        spec[key] = raise_conditions(spec[key])
    spec['start']['modules']['puzzle'] = copy.deepcopy(EMPTY_FACTS)
    spec['gameplay']['modules'].append(copy.deepcopy(module))
    spec['gameplay']['modules'].sort(key=lambda m: m['id'])
    return spec


def lower_state(state, rows):
    """1.3 state dict -> (1.2 state dict, entry). ``rows`` = fact_rows of the game's puzzle module."""
    if not isinstance(state, dict) or not isinstance(state.get('modules'), dict) or 'puzzle' not in state['modules']:
        raise SpecError('state/modules/puzzle facts are required in STORY 1.3.0')
    out = copy.deepcopy(state)
    facts = out['modules'].pop('puzzle')
    S.validate(facts, FACTS, 'state/modules/puzzle')
    known = set(rows)
    for field in ('solved', 'taken', 'opened', 'latched'):
        if facts[field] != sorted(facts[field]):
            raise SpecError('state/modules/puzzle/' + field + ': IDs must be sorted')
        for eid in facts[field]:
            if (field, eid) not in known:
                raise SpecError('state/modules/puzzle/' + field + ': unknown or ineligible ID ' + eid)
    if not isinstance(out.get('flags'), dict):
        raise SpecError('state/flags must be an object')
    stray = [k for k in out['flags'] if k.startswith(PREFIX)]
    if stray:
        raise SpecError('state/flags/' + stray[0] + ': reserved flags are not part of a 1.3 state; use modules.puzzle')
    for field, eid in rows:
        out['flags'][fact_flag(field, eid)] = eid in facts[field]
    return out, facts['entry']


def raise_state(state, entry):
    out = copy.deepcopy(state)
    facts = {'solved': [], 'taken': [], 'opened': [], 'latched': []}
    for name, value in out['flags'].items():
        parsed = parse_flag(name)
        if parsed is not None and value:
            facts[parsed[0]].append(parsed[1])
    out['flags'] = {k: v for k, v in out['flags'].items() if not k.startswith(PREFIX)}
    out['modules']['puzzle'] = {key: sorted(values) for key, values in facts.items()}
    out['modules']['puzzle']['entry'] = entry
    return out
