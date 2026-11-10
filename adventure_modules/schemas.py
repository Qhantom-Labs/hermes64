"""Provider-neutral tool schemas. No look, renderer, or physical pass is implied."""
if '.' in (__package__ or ''):
    from ..story.modules import schema as S
    from ..story.puzzle.edits import operation_schema  # STORY 1.2 kinds (unchanged) + the four puzzle kinds
else:
    from story.modules import schema as S
    from story.puzzle.edits import operation_schema  # STORY 1.2 kinds (unchanged) + the four puzzle kinds

HASH = {'type': 'string', 'minLength': 64, 'maxLength': 64, 'pattern': '^[0-9a-f]{64}$'}
OPTIONAL_HASH = {'oneOf': [HASH, {'const': ''}]}
PROJECT = {'type': 'string', 'minLength': 1, 'maxLength': 64, 'pattern': '^[a-z][a-z0-9_-]*$'}
PATH = {'type': 'string', 'minLength': 1, 'maxLength': 512}


def parameters(required, **fields):
    schema = S.obj(**fields)
    schema['required'] = required
    return schema


EDIT = parameters(['project', 'operation', 'expected_spec_hash', 'expected_game_hash'],
    project=PROJECT, operation=operation_schema(), expected_spec_hash=HASH, expected_game_hash=HASH, save_path=PATH)
DEFINITIONS = {
    'modules': ('Inspect registered data-only mechanics and their evidence status. Does not certify a playable runtime or prescribe a visual style.',
                parameters(['action'], action=S.enum('list', 'inspect'), id=S.ID)),
    'module_check': ('Compile and check a STORY 1.2 or 1.3 (puzzle) data candidate. Explicit adoption advances only the isolated DATA pointer after the declared proof policy passes. Never creates runtime verification.',
        parameters(['project', 'spec_path', 'adopt'], project=PROJECT, spec_path=PATH, adopt={'type': 'boolean'},
                   expected_spec_hash=OPTIONAL_HASH, expected_game_hash=OPTIONAL_HASH, max_states=S.integer(1, 100000))),
    'module_add': ('Add an enemy archetype, finite ability or puzzle switch using a typed transaction; recheck progression and migrate an optional checkpoint. No scripts or style assumptions.', EDIT),
    'module_edit': ('Apply a typed enemy, arena, region-gate, course-checkpoint, ability or puzzle (link-door, move-block, set-solution-hint) edit with exact source/build revisions. Failed validation, proof, locality or save migration leaves the data pointer unchanged.', EDIT),
    'module_benchmark': ('Measure 1-20 sequential typed module edits without moving the data or runtime pointer. Reports data checks separately from unrun engine, bot and human evidence.',
        parameters(['project', 'operations', 'expected_spec_hash', 'expected_game_hash'], project=PROJECT,
                   operations=S.array(operation_schema(), 20, 1), expected_spec_hash=HASH, expected_game_hash=HASH, save_path=PATH)),
}
SCHEMAS = {'hermes64_' + key: {'name': 'hermes64_' + key, 'description': description, 'parameters': schema}
           for key, (description, schema) in DEFINITIONS.items()}
