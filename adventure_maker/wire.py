"""Compact advertised tool schemas: the per-request token diet (docs/TOKEN-DIET.md).

Validation is unchanged. Every handler still validates its arguments against the full
schema in adventure_maker.schemas, adventure_modules.schemas, audio_schemas, demo or
cover_schemas.
This module only builds the copy shown to the model: a looser projection that keeps
tool and parameter names, types, enums, integer bounds, ID patterns, required fields and
the top-level ``additionalProperties: false``, and drops nested shapes, length limits and
prose that the bundled skills and docs carry. Anything the wire copy accepts but the full
schema rejects still fails with the same validation error as before.
"""
import copy

SKILL = 'skill hermes64:hermes64'
MODULE_SKILL = 'skill hermes64:hermes64-gameplay-modules'

# One or two sentences each; every word here is paid on every request.
SHORT = {
    # First sentence = the deferred tool listing's line (hosts 0.19.1+): the trigger for plain game requests (NATIVE).
    'hermes64_demo': ('For any game request, load skill hermes64:hermes64-create first. Quick path: a premise sentence '
                      '(optional style) builds, proof-checks and bot-plays a game; or run a bundled example '
                      '(project + example).'),
    'hermes64_doctor': 'Read-only Python, Godot, Blender and setup/download plans. No engine launch, download or install.',
    'hermes64_pack_from_refs': ('Draft an unapproved theme pack from 1-8 project-local PNG/JPEG references plus a notes file. '
                                'Local only; never auto-selected.'),
    'hermes64_scaffold': 'Create source from spec_json or a starter. Original games: skill hermes64:hermes64-author. Unvalidated: compile and check next.',
    'hermes64_kits': 'List or inspect the bundled kit manifest, or a style pack (action=style). Read-only.',
    'hermes64_packs': 'List or inspect bundled and project-local theme packs. Read-only.',
    'hermes64_pack_create': 'Create a new data-only theme pack (pack_json) inside a project. Never overwrites.',
    'hermes64_pack_select': 'Select a validated pack; a compiled game is recompiled and rechecked before adoption.',
    'hermes64_pack_validate': 'Validate pack data (palette, materials, fog, budgets). Not a rendered or audio check.',
    'hermes64_compile': 'Compile a project source spec (patch_json: a repair patch) into a new build. Not a proof: run check next.',
    'hermes64_check': ('Proof-check the current build (endings, softlocks, collectibles); action=audit scores the rendered style. '
                       'Failures return next: the calls that fix and retry.'),
    'hermes64_edit': ('Apply one story edit, recompile and re-check it; only a passing candidate is adopted. '
                      'Always check after editing; never hand-edit generated files.'),
    'hermes64_build_assets': 'Build and validate theme assets with the configured kit builder (auto default). No downloads.',
    'hermes64_replay': 'Replay checker witnesses in the Godot bot: every ending plus a save/load round trip.',
    'hermes64_benchmark': 'Measure 1-20 sequential story edits in isolated candidates without moving the live build; unrun gates report NOT RUN.',
    'hermes64_open': 'Open the current game in a bounded Godot preview (closes after seconds); screenshots=true also runs the measured style gate.',
    'hermes64_modules': 'List or inspect the data-only gameplay module contracts and their evidence status.',
    'hermes64_module_check': 'Compile and check a STORY 1.2/1.3 module source. adopt=true moves only the data pointer, after the proof policy passes.',
    'hermes64_module_add': 'Add an enemy, ability or puzzle switch to a STORY 1.2/1.3 game as a checked typed transaction.',
    'hermes64_module_edit': 'Apply one typed module edit with exact source/build hashes. Failed checks keep the previous data pointer.',
    'hermes64_module_benchmark': 'Measure 1-20 typed module edits without moving any pointer. Data checks only.',
    'hermes64_audio': ('Retro audio: catalog search, render preview/variation/music/voice/style bank, validate; import your '
                       'own MP3/OGG/WAV music/voices and assign scene/boss/menu/voice slots. Offline; args in skill hermes64:hermes64-audio.'),
    'hermes64_playtest': 'Run bounded Godot bots (winning paths and/or explorer) on the current build: a SOLID/PLAYABLE/ROUGH/BROKEN tier. Cannot judge fun.',
    'hermes64_export': 'Build local web, macOS and/or Windows exports of a verified game. No upload; Windows execution unverified on Mac.',
    'hermes64_cover': ('Box-art covers: propose 3 variants for the user to pick, apply typed edits, render with the cover '
                       'gate, export. adopt=true only on the user\'s explicit choice. Local Godot; writes only inside '
                       'the project.'),
    'hermes64_hub': ('Local Hermes64 Hub: search/info styles, kits, characters, sounds, games; install into a '
                     'game after hash, data-only, style and rig checks; pack an asset or game; publish = local PR draft. '
                     'Never uploads.'),
    # WAIVER: 25 characters shorter (same facts) to make room for bind waive/owner_approved and hub waived, budget unchanged
    'hermes64_character': ('House-style characters: propose 3 variants, edit, build the user\'s pick (GLB, clips, all gates '
                           'incl. rig kit; no Blender needed), list/info parts, bind to the cast, locomotion = bake run/walk. '
                           'Never auto-adopts.'),
}

COVER_SKILL = 'skill hermes64:hermes64-cover'
CHARACTER_SKILL = 'skill hermes64:hermes64-characters'
CHARACTER_EDITS = ['height', 'build', 'hair', 'color', 'swap', 'face', 'prop', 'name']
COVER_OPS = ['move', 'nudge', 'replace', 'add', 'remove', 'lighting', 'camera', 'title', 'particles', 'pose', 'finish',
             'reframe']

# MERGE5: the field list (MERGE4's kind{fields}) moved to the main skill, which lists every shape (docs/TOKEN-DIET.md).
EDIT_OPERATION = 'Fields per kind: ' + SKILL + '; optional expected_changed_rooms.'
MODULE_KINDS = ['add-enemy', 'modify-enemy', 'change-arena', 'gate-region', 'change-course-checkpoints', 'add-ability',
                'add-switch', 'link-door', 'move-block', 'set-solution-hint']


def module_operation(kinds):
    """The kinds this tool accepts (its enum). MERGE5: the per-kind field lists (MERGE4's kind{fields}) moved to the
    gameplay-modules skill, which already carried the full shapes the fields only named (and now the four STORY 1.3
    puzzle kinds): headroom for the recipes/converter lanes (docs/TOKEN-DIET.md)."""
    text = 'Fields per kind: ' + MODULE_SKILL + '; plus expected_changed_rooms.'
    return {'type': 'object', 'properties': {'kind': {'enum': kinds}}, 'required': ['kind'], 'description': text}


# Per-tool parameter overrides: replace a nested shape with a short pointer, or add a one-line doc.
PARAMS = {
    'hermes64_edit': {'operation': {'type': 'object', 'properties': {'kind': {'enum': ['move-entrance', 'change-role', 'add-ending', 'json-patch']}},
                                    'required': ['kind'], 'description': EDIT_OPERATION}},
    'hermes64_benchmark': {'operations_json': {'type': 'string', 'description': 'JSON array of 1-20 hermes64_edit operations.'}},
    'hermes64_module_add': {'operation': module_operation(['add-enemy', 'add-ability', 'add-switch'])},
    'hermes64_module_edit': {'operation': module_operation(MODULE_KINDS)},
    # MERGE5: benchmark takes hermes64_module_edit's operations; it points there instead of repeating the kind list
    # (as hermes64_benchmark points at hermes64_edit). The enum and required kind stay.
    'hermes64_module_benchmark': {'operations': {'type': 'array', 'items': dict(module_operation(MODULE_KINDS),
                                                                                description='One hermes64_module_edit operation.')}},
    'hermes64_scaffold': {'spec_json': {'type': 'string', 'description': 'Serialized story spec; use instead of premise.'}},
    # TIERS: agents passed absolute spec paths (3 of 12 condition-A runs, both models); the handler rejects them.
    'hermes64_compile': {'spec_path': {'type': 'string', 'description': 'Project-relative, e.g. source/spec.json.'}},
    'hermes64_export': {'module_preview': {'type': 'boolean', 'description': 'Local module preview; needs a fresh real-input bot run.'}},
    'hermes64_audio': {'music': {'type': 'object', 'description': 'mood, mode, key, tempo, bars, seed, style, instruments.'},
                       'voice': {'type': 'object', 'description': 'character, emotion, seed, pitch, rate, timbre, formant.'},
                       'transform': {'type': 'object', 'description': 'pitch_semitones, filter_hz, reverb_ms, reverb_mix, sample_rate, instruments.'},
                       'options': {'type': 'object'}, 'items': {'type': 'array', 'items': {'type': 'object'}}},
    'hermes64_demo': {'premise': {'type': 'string', 'description': 'One sentence; makes a new game.'},
                      'style': {'type': 'string', 'description': 'village, forest, polar or a pack id; omitted: picked from the premise.'}},
    'hermes64_cover': {'edits': {'type': 'array', 'items': {'type': 'object', 'properties': {'op': {'enum': COVER_OPS}},
                                                            'required': ['op']},
                                 'description': '1-12 typed edits {op, target?, ...}; shapes in ' + COVER_SKILL + '.'}},
    'hermes64_hub': {'id': {'type': 'string', 'description': 'Hub entry id (style.polar_pod); pack also takes a catalog id '
                                                               '(kit:furn.lamp) or one of your games.'}},
    'hermes64_character': {'edits': {'type': 'array', 'items': {'type': 'object', 'properties': {'kind': {'enum': CHARACTER_EDITS}},
                                                                'required': ['kind']},
                                     'description': '1-8 typed edits; shapes in ' + CHARACTER_SKILL + '.'}},
}


def json_type(schema):
    if 'type' in schema:
        return schema['type']
    if 'const' in schema:
        return {str: 'string', bool: 'boolean', int: 'integer', float: 'number'}.get(type(schema['const']))
    if schema.get('enum') and all(isinstance(value, str) for value in schema['enum']):
        return 'string'
    return None


def slim(schema, depth=0) -> dict:
    """Looser projection of a validation schema. Never narrows what a value may be."""
    if 'oneOf' in schema:
        # A union collapses to its one shared JSON type (or to "anything"); alternatives live in the skills.
        kinds = {json_type(child) for child in schema['oneOf']}
        return {'type': kinds.pop()} if len(kinds) == 1 and None not in kinds else {}
    out: dict = {}
    kind = schema.get('type')
    if kind:
        out['type'] = kind
    if 'enum' in schema:
        out['enum'] = copy.deepcopy(schema['enum'])
    if 'const' in schema:
        out['const'] = copy.deepcopy(schema['const'])
    if kind in ('integer', 'number'):
        for key in ('minimum', 'maximum'):
            if key in schema:
                out[key] = schema[key]
    if kind == 'string' and depth == 1 and 'pattern' in schema and schema.get('maxLength', 0) <= 64:
        out['pattern'] = schema['pattern']
    if kind == 'array' and 'items' in schema:
        out['items'] = slim(schema['items'], depth + 1)
    if kind == 'object' or 'properties' in schema:
        if depth == 0:
            out['properties'] = {key: slim(child, 1) for key, child in schema.get('properties', {}).items()}
            out['required'] = list(schema.get('required', []))
            out['additionalProperties'] = False
        elif depth == 1 and 'properties' in schema:
            out['properties'] = {key: slim(child, 3) for key, child in schema['properties'].items()}
    return out


def advertise(name, full, extra_properties=None, required=None):
    """Wire schema for one tool: SHORT description, slim parameters, PARAMS overrides."""
    parameters = slim(full['parameters'])
    properties = parameters['properties']
    for key, child in (extra_properties or {}).items():
        properties[key] = slim(child, 1)
    for key, override in PARAMS.get(name, {}).items():
        properties[key] = copy.deepcopy(override)
    if required is not None:
        parameters['required'] = list(required)
    return {'name': name, 'description': SHORT[name], 'parameters': parameters}


def register(ctx, name, full, handler, check_fn, extra_properties=None, required=None):
    schema = advertise(name, full, extra_properties, required)
    ctx.register_tool(name=name, toolset='hermes64', schema=schema, handler=handler, check_fn=check_fn,
                      requires_env=[], description=schema['description'])
