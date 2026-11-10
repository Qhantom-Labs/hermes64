"""STORY 1.3 validation, canonical compilation and strict integrity, by exact lowering onto STORY 1.2.

The compiled 1.3 game is the compiled 1.2 game of the lowered source, plus three additive keys:
``puzzle`` (normalized puzzle data, reserved flag map, per-room hashes), ``puzzle_contract`` and ``lowered``
(the embedded 1.2 identity). ``contract_version``, ``spec_hash`` and ``game_hash`` are the 1.3 identity.
"""
import copy
import hashlib
from pathlib import Path
from ..compiler import canonical, digest, compile_spec as compile12, validate_game as validate_game12, normalize as normalize12
from ..validation import validate as validate12
from ..errors import SpecError
from ..modules.registry import contracts as contracts12
from . import VERSION, PUZZLE_API, flag
from .lowering import lower_spec, raise_spec
from .rules import validate as validate_rules, normalize as normalize_module, MODULE, FACTS, CONDITION

SIDE = ('puzzle', 'puzzle_contract', 'lowered')
SCHEMA_URI = 'https://json-schema.org/draft/2020-12/schema'


def implementation_digest():
    """Pin every trusted source file the 1.3 build depends on (1.2 core and modules plus this package)."""
    root = Path(__file__).resolve().parents[1]
    paths = sorted(list(root.glob('*.py')) + list((root / 'modules').glob('*.py')) + list((root / 'puzzle').glob('*.py')))
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def contracts():
    """Closed 1.3 contracts: the unchanged 1.2 set plus the puzzle module, facts and condition."""
    out = contracts12()
    for name, schema in (('puzzle', MODULE), ('puzzle_state', FACTS), ('puzzle_condition', CONDITION)):
        out[name] = dict(copy.deepcopy(schema), **{'$schema': SCHEMA_URI})
    return out


def contract():
    return {'story_version': VERSION, 'puzzle_api': PUZZLE_API, 'state_version': '1.1.0', 'analysis_version': '1.1.0',
            'lowering': 'puzzle_flags_v1', 'schema_hash': digest(contracts()), 'implementation_hash': implementation_digest(),
            'physical_evidence': 'not_run', 'human_evidence': 'not_run'}


def validate(spec):
    base, module = lower_spec(spec)
    validate12(base)
    validate_rules(spec, module)
    return base, module


def normalize(spec):
    base, module = lower_spec(spec)
    normalize_module(module)
    return raise_spec(normalize12(base), module)


def compile_spec(spec):
    base, module = validate(spec)
    game = compile12(base)
    source = normalize(spec)
    normalize_module(module)
    puzzles = module['entities']['puzzles']
    out = copy.deepcopy(game)
    out['contract_version'] = VERSION
    out['lowered'] = {'contract_version': '1.2.0', 'spec_hash': game['spec_hash'], 'game_hash': game['game_hash']}
    out['puzzle'] = {'api_version': PUZZLE_API, 'config': module['config'], 'puzzles': puzzles,
                     'flags': {p['id']: flag(p['id']) for p in puzzles},
                     'room_hashes': {p['room']: digest(p) for p in puzzles}}
    out['puzzle_contract'] = contract()
    out['spec_hash'] = digest(source)
    out.pop('game_hash')
    out['game_hash'] = digest(out)
    return out


def lowered_game(game):
    """The exact embedded STORY 1.2 build (validated separately)."""
    if not isinstance(game, dict) or game.get('contract_version') != VERSION or not all(k in game for k in SIDE + ('game_hash', 'spec_hash')):
        raise SpecError('STORY 1.3.0 game requires puzzle, puzzle_contract, lowered, spec_hash and game_hash')
    low = copy.deepcopy(game)
    for key in SIDE:
        low.pop(key)
    lowered = game['lowered']
    if not isinstance(lowered, dict) or set(lowered) != {'contract_version', 'spec_hash', 'game_hash'} or lowered['contract_version'] != '1.2.0':
        raise SpecError('lowered identity must name the embedded STORY 1.2.0 build')
    low.update(contract_version='1.2.0', spec_hash=lowered['spec_hash'], game_hash=lowered['game_hash'])
    return low


def source_of(game):
    """Reconstruct the normalized 1.3 source from a compiled 1.3 game."""
    low = validate_game12(lowered_game(game))
    base = copy.deepcopy(low)
    for key in ('game_hash', 'spec_hash', 'module_contract'):
        base.pop(key)
    for room in base['rooms']:
        room.pop('content')
        room.pop('build_hash')
    side = game['puzzle']
    if not isinstance(side, dict) or not isinstance(side.get('puzzles'), list):
        raise SpecError('puzzle sidecar is malformed')
    module = {'id': 'puzzle', 'version': '1.0.0', 'config': copy.deepcopy(side.get('config')),
              'entities': {'puzzles': copy.deepcopy(side['puzzles'])}}
    return raise_spec(base, module)


def validate_game(game):
    expected = compile_spec(source_of(game))
    if canonical(expected) != canonical(game):
        raise SpecError('compiled 1.3 game integrity/hash/canonical-order mismatch; recompile source')
    return game
