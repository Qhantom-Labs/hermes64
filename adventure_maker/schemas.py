"""Strict provider-neutral schemas; independently checked in handlers."""
import re
from .safety import fail, encode


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def text(maximum=512, **kw):
    return dict(type='string', minLength=1, maxLength=maximum, **kw)


ID = text(64, pattern=r'^[a-z][a-z0-9_-]*$')
PATH = text(512)
JSON_TEXT = text(1048576)
COMMON = {'project': ID}
OPERATION = {'oneOf': [
    obj({'kind': {'const': 'move-entrance'}, 'room': ID, 'door': ID,
         'wall': {'enum': ['north', 'south', 'east', 'west']},
         'position': {'type': 'integer', 'minimum': 0, 'maximum': 10000},
         'expected_changed_rooms': {'type': 'array', 'items': ID, 'maxItems': 100}},
        ['kind', 'room', 'door', 'wall', 'position']),
    obj({'kind': {'const': 'change-role'}, 'character': ID, 'role': ID,
         'expected_changed_rooms': {'type': 'array', 'items': ID, 'maxItems': 100}}, ['kind', 'character', 'role']),
    obj({'kind': {'const': 'add-ending'}, 'ending_json': JSON_TEXT,
         'expected_changed_rooms': {'type': 'array', 'items': ID, 'maxItems': 100}}, ['kind', 'ending_json']),
    obj({'kind': {'const': 'json-patch'}, 'patch_json': JSON_TEXT,
         'expected_changed_rooms': {'type': 'array', 'items': ID, 'maxItems': 100}}, ['kind', 'patch_json'])]}

DEFINITIONS = {
    'doctor': ('Read-only capability discovery for the configured Python, numpy/Pillow and existing Godot/Blender. No installs, engine launch, network or settings changes. Detection is not runtime/export-template verification. project is optional: it works before any game or projects_root exists.',
        obj(COMMON)),
    'pack_from_refs': ('Explicitly draft an unapproved theme pack from project-local PNG/JPEG references and structured notes, using the opt-in Python path. Supports varied looks; no single style is imposed. Sandboxed, local only, no Blender/downloads, approval or automatic selection. Proofs and optional reference thumbnails are private review artifacts.',
        obj(dict(COMMON, reference_paths={'type': 'array', 'items': PATH, 'minItems': 1, 'maxItems': 8},
                 notes_path=PATH, pack_id=text(40, pattern=r'^[a-z][a-z0-9_]{2,39}$'),
                 render_proof={'type': 'boolean'}, ref_thumbnails={'type': 'boolean'},
                 mode={'enum': ['albedo', 'measured']}), ['project', 'reference_paths', 'notes_path', 'pack_id'])),
    'scaffold': ('Create a new local source project from an original premise template OR serialized story spec. Does not invent a full game or certify it; compile and check next.',
        obj(dict(COMMON, premise=text(6000), spec_json=JSON_TEXT, pack=ID), ['project', 'pack'])),
    'kits': ('List/inspect the assembled local kit manifest or a data-only theme/style pack. No network and no writes.',
        obj({'action': {'enum': ['list', 'inspect', 'style']}, 'id': text(64, pattern=r'^[a-z][a-z0-9_.-]*$')}, ['action'])),
    'packs': ('List or inspect bundled and optional project-local theme packs. No network and no writes.',
        obj({'action': {'enum': ['list', 'inspect']}, 'id': ID, 'project': ID}, ['action'])),
    'pack_create': ('Validate and create a new data-only pack inside one existing game project. Never overwrites a pack or changes core code.',
        obj(dict(COMMON, pack_json=JSON_TEXT), ['project', 'pack_json'])),
    'pack_select': ('Select a validated pack. A compiled project is recompiled and rechecked before adoption; uncompiled source remains unvalidated.',
        obj(dict(COMMON, pack=ID), ['project', 'pack'])),
    'pack_validate': ('Validate pack schema, palette, material, fog, reference and budget data. Does NOT certify rendered assets or audio.',
        obj(dict(COMMON, pack=ID), ['project', 'pack'])),
    'compile': ('Compile a project-relative source JSON spec using the local story CLI. Returns immutable build paths; not a solvability claim. Optional patch_json (RFC6902 add/remove/replace/test) is applied to that source first, as listed in a repair next step.',
        obj(dict(COMMON, spec_path=PATH, patch_json=JSON_TEXT), ['project', 'spec_path'])),
    'check': ('Check the current compiled game, endings and 1.1 collectibles; return readable witnesses and truthful failures/inconclusive results, plus a repair next list on failure. action=audit renders and measures the style audit (per-room scores, fix hints, contact sheet); not human art approval.',
        obj(dict(COMMON, max_states={'type': 'integer', 'minimum': 1, 'maximum': 100000}, action={'enum': ['proof', 'audit']},
                 views={'type': 'integer', 'minimum': 0, 'maximum': 2}), ['project'])),
    'edit': ('Apply a named story edit or validated RFC6902 add/remove/replace/test patch. Recompile, check, report diff, identity and room hashes; adopt only passing candidates. Never hand-edit generated files.',
        obj(dict(COMMON, operation=OPERATION, save_path=PATH, expected_spec_hash=text(64, pattern=r'^[0-9a-f]{64}$')), ['project', 'operation'])),
    'build_assets': ('Build theme-selected local assets through the trusted kit builder; Blender is default and Python/auto are explicit opt-ins. Validates output, never silently falls back or downloads dependencies.',
        obj(dict(COMMON, seed={'type': 'integer', 'minimum': 0, 'maximum': 2147483647}), ['project', 'seed'])),
    'replay': ('Replay current checker witnesses through the trusted Godot playthrough bot, requiring every ending and save/load report. Not equivalent to a symbolic proof.',
        obj(COMMON, ['project'])),
    'benchmark': ('Run 1-20 sequential edits in isolated candidate revisions without changing the live pointer. Report measured precision dimensions and NOT RUN save/style gates honestly. style_gate=true also renders each passing revision and requires the measured room-look gate (not human art approval).',
        obj(dict(COMMON, operations_json=JSON_TEXT, save_path=PATH, build_assets={'type': 'boolean'}, style_gate={'type': 'boolean'}), ['project', 'operations_json', 'build_assets'])),
    'open': ('Explicitly open a trusted-copy Godot game in a bounded foreground preview. It closes at timeout; no detached background service. With screenshots, returns the measured room-look style gate per room (and golden regression when the project has blessed goldens); not human art approval.',
        obj(dict(COMMON, seconds={'type': 'integer', 'minimum': 1, 'maximum': 120}, screenshots={'type': 'boolean'}), ['project', 'seconds']))}
SCHEMAS = {('hermes64_' + name): {'name': 'hermes64_' + name, 'description': desc, 'parameters': schema}
           for name, (desc, schema) in DEFINITIONS.items()}


def validate(value, schema, at='$'):
    if 'oneOf' in schema:
        matches = 0
        for child in schema['oneOf']:
            try:
                validate(value, child, at)
                matches += 1
            except Exception:
                pass
        if matches != 1:
            fail('arguments', at + ': must match exactly one operation schema')
        return
    if 'const' in schema and value != schema['const']:
        fail('arguments', at + ': unexpected value')
    if 'enum' in schema and value not in schema['enum']:
        fail('arguments', at + ': value outside enum')
    kind = schema.get('type')
    good = {'object': isinstance(value, dict), 'array': isinstance(value, list),
            'string': isinstance(value, str), 'integer': type(value) is int,
            'number': type(value) in (float, int), 'boolean': type(value) is bool}.get(kind, True)
    if not good:
        fail('arguments', at + ': expected ' + str(kind))
    if kind == 'object':
        props = schema['properties']
        if any(k not in props for k in value) or any(k not in value for k in schema.get('required', [])):
            fail('arguments', at + ': missing required or unknown arguments')
        for key, child in value.items():
            validate(child, props[key], at + '.' + key)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 100):
            fail('arguments', at + ': array length out of bounds')
        for child in value:
            validate(child, schema['items'], at + '[]')
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 1048576):
            fail('arguments', at + ': string length out of bounds')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            fail('arguments', at + ': string format invalid')
    elif kind in ('integer', 'number'):
        if not schema.get('minimum', value) <= value <= schema.get('maximum', value):
            fail('arguments', at + ': integer out of bounds')
