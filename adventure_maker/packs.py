"""Data-only theme packs; no generators, engine code or executable fields."""
import hashlib
from pathlib import Path
from .safety import JSON_LIMIT, encode, fail, inspect_path, relative, strict_json
from .schemas import ID, obj, text, validate

COLOUR = text(7, pattern=r'^#[0-9A-F]{6}$')
ASSET_ID = text(64, pattern=r'^(?:gen:[a-z][a-z0-9_]{1,47}|[a-z][a-z0-9_.]*)$')
MATERIAL = obj({'id': ID, 'kind': {'enum': ['baked_unlit', 'chrome_env', 'glass_env', 'emissive', 'card_alpha']}, 'colour': COLOUR}, ['id', 'kind', 'colour'])
LIGHT = obj({'fog_enabled': {'type': 'boolean', 'const': True}, 'fog_colour': COLOUR, 'ambient_colour': COLOUR,
             'fog_start': {'type': 'number', 'minimum': 0, 'maximum': 1000},
             'fog_end': {'type': 'number', 'minimum': 1, 'maximum': 1000}},
            ['fog_enabled', 'fog_colour', 'ambient_colour', 'fog_start', 'fog_end'])
LIMITS = {'character_tris': 700, 'kit_tris': 1500, 'prop_tris': 150, 'room_tris': 6000, 'texture_px': 128}
PACK = obj({'format': {'type': 'integer', 'const': 1}, 'id': ID, 'name': text(120), 'description': text(3000),
            'palette': {'type': 'array', 'items': COLOUR, 'minItems': 2, 'maxItems': 32},
            'materials': {'type': 'array', 'items': MATERIAL, 'minItems': 1, 'maxItems': 32},
            'lighting': LIGHT,
            'presets': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': obj({'id': ID, 'asset_id': ASSET_ID, 'params_json': text(8000)}, ['id', 'asset_id', 'params_json'])},
            'sound_palette': obj({'ambient': text(), 'interact': text()}, ['ambient', 'interact']),
            'thresholds': obj({k: {'type': 'integer', 'minimum': 1, 'maximum': v} for k, v in LIMITS.items()}, list(LIMITS)),
            'kit_pack_id': ID},
           ['format', 'id', 'name', 'description', 'palette', 'materials', 'lighting', 'presets', 'sound_palette', 'thresholds', 'kit_pack_id'])


def validate_pack(data):
    encode(data)
    validate(data, PACK)
    if len(set(data['palette'])) != len(data['palette']):
        fail('pack', 'Palette colours must be unique')
    if data['lighting']['fog_end'] <= data['lighting']['fog_start']:
        fail('pack', 'Fog end must exceed fog start')
    for colour in [data['lighting']['fog_colour'], data['lighting']['ambient_colour']] + [x['colour'] for x in data['materials']]:
        if colour not in data['palette']:
            fail('pack', 'Material/light colours must occur in the palette')
    for collection in ('materials', 'presets'):
        ids = [x['id'] for x in data[collection]]
        if len(set(ids)) != len(ids):
            fail('pack', 'Duplicate ' + collection + ' IDs')
    for preset in data['presets']:
        params = strict_json(preset['params_json'])
        if not isinstance(params, dict) or any(not isinstance(k, str) or not k for k in params):
            fail('pack', 'Preset params must be a JSON object')
        # Parameter values are data only; per-kit bounds belong to the kit manifest.
        for value in params.values():
            if type(value) not in (str, int, float, bool):
                fail('pack', 'Preset parameter values must be scalar')
    for path in data['sound_palette'].values():
        relative(path)
    return data


def fingerprint(data):
    return hashlib.sha256(encode(data)).hexdigest()


class Packs:
    def __init__(self, settings, project=None):
        root = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
        if not root.is_absolute() or '..' in root.parts:
            fail('configuration', 'bundle_root must be an absolute path without traversal')
        self.root = inspect_path(root)
        self.project = project

    def get(self, id):
        validate(id, ID)
        rel = 'packs/' + id + '/pack.json'
        path = self.project.path(rel) if self.project else self.root / rel
        if not path.is_file():
            path = self.root / rel
        inspect_path(path)
        if not path.is_file():
            fail('component_unavailable', 'Pack not found: ' + id)
        with path.open('rb') as f:
            data = validate_pack(strict_json(f.read(JSON_LIMIT + 1)))
        if data['id'] != id:
            fail('pack', 'Pack directory and declared ID differ')
        return data

    def list(self):
        directories = [self.root / 'packs']
        if self.project:
            directories.append(self.project.path('packs'))
        ids = set()
        for directory in directories:
            inspect_path(directory)
            if directory.is_dir():
                for child in directory.iterdir():
                    inspect_path(child)
                    if child.is_dir():
                        validate(child.name, ID)
                        ids.add(child.name)
                        if len(ids) > 100:
                            fail('limit', 'Pack count exceeds 100')
        if not ids and not directories[0].is_dir():
            fail('component_unavailable', 'Assembled packs/ directory is missing')
        return [{'id': id, 'name': self.get(id)['name']} for id in sorted(ids)]

    def snapshot(self, data):
        validate_pack(data)
        path = 'packs/' + data['id'] + '/pack.json'
        if self.project.path(path).exists():
            if self.project.read_json(path) != data:
                fail('pack', 'Existing pack differs; create a new ID instead of overwriting')
        else:
            self.project.write_json(path, data)
        return {'id': data['id'], 'sha256': fingerprint(data)}

    def selected(self, spec):
        ref = spec.get('metadata', {}).get('hermes64_pack')
        if not isinstance(ref, dict) or set(ref) != {'id', 'sha256'}:
            fail('pack', 'Source must bind an immutable Hermes64 pack; use pack_select')
        # Compiled builds may not silently fall back to a changed bundled pack.
        data = validate_pack(self.project.read_json('packs/' + str(relative(ref['id'])) + '/pack.json'))
        if data['id'] != ref['id'] or fingerprint(data) != ref['sha256']:
            fail('pack', 'Pack changed since selection; select a new validated pack revision')
        return data
