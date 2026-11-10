"""Data-only style v1 resolution. No imports of generators or runtime engines.

The bundled catalog is a versioned validation domain, not evidence that its APIs
are installed. `require_runtime=True` fails closed until steps 4–6 supply a real
adapter/proof contract. A data-valid style is never a build or aesthetic approval.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
JSON_LIMIT = 1024 * 1024
RESOURCE_LIMIT = 8 * 1024 * 1024
CLOSURE_LIMIT = 32 * 1024 * 1024
MAX_DEPTH = 16
SECTIONS = ('render', 'palette', 'materials', 'lighting', 'camera', 'kits', 'geometry',
            'characters', 'props', 'exterior', 'ui', 'audio', 'validators', 'variation')


class StyleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def require(condition, code, message):
    if not condition:
        raise StyleError(code, message)


def _finite(value, depth=0):
    require(depth <= 48, 'LIMIT', 'JSON nesting')
    if isinstance(value, dict):
        for key, item in value.items():
            require(isinstance(key, str), 'SCHEMA', 'JSON keys must be strings')
            _finite(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _finite(item, depth + 1)
    elif isinstance(value, float):
        require(math.isfinite(value), 'NONFINITE', 'JSON numbers must be finite')
    else:
        require(value is None or type(value) in (str, int, bool), 'SCHEMA', 'not JSON data')


def canonical_bytes(value):
    """UTF-8, sorted keys, compact separators, no NaN; array order is authored."""
    _finite(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StyleError('SCHEMA', 'noncanonical JSON') from exc


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_json(raw):
    require(isinstance(raw, (bytes, str)), 'SCHEMA', 'expected JSON bytes or text')
    require(len(raw) <= JSON_LIMIT, 'LIMIT', 'JSON byte limit')

    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'DUPLICATE_KEY', key)
            result[key] = value
        return result

    def nonfinite(_):
        raise StyleError('NONFINITE', 'JSON nonfinite literal')
    try:
        text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        require(len(text.encode('utf-8')) <= JSON_LIMIT, 'LIMIT', 'JSON byte limit')
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
        _finite(result)
        return result
    except StyleError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StyleError('SCHEMA', 'invalid JSON') from exc


def relative_path(rel):
    require(isinstance(rel, str) and len(rel) <= 240 and
            re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', rel) is not None,
            'PATH', 'expected a confined portable relative path')
    require(all(p not in ('.', '..') for p in rel.split('/')), 'PATH', 'dot path component')
    return rel


def confined_path(root, rel):
    relative_path(rel)
    root = Path(root).absolute()
    require(not any(p.is_symlink() for p in (root,) + tuple(root.parents)), 'PATH', 'symlink root')
    path = root
    for part in rel.split('/'):
        path = path / part
        require(not path.is_symlink(), 'PATH', 'symlink component: ' + rel)
    return path


def read_confined(root, rel, limit=JSON_LIMIT):
    """No-follow open on every component; size/identity checked on one descriptor."""
    confined_path(root, rel)
    descriptors = []
    try:
        fd = os.open(str(Path(root).absolute()), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        parts = rel.split('/')
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'PATH', 'nonregular input: ' + rel)
        require(not before.st_mode & 0o111, 'EXECUTABLE_RESOURCE', rel)
        require(before.st_size <= limit, 'LIMIT', rel)
        blocks, remaining = [], limit + 1
        while remaining:
            block = os.read(fd, min(remaining, 65536))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        raw = b''.join(blocks)
        after = os.fstat(fd)
        require(len(raw) <= limit, 'LIMIT', rel)
        require((before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns), 'RESOURCE_CHANGED', rel)
        return raw
    except OSError as exc:
        raise StyleError('PATH', 'missing or unsafe input: ' + rel) from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _same(a, b):
    # JSON equality: booleans are never numbers, though 1 and 1.0 are equal.
    return (type(a) is bool) == (type(b) is bool) and a == b


def validate_schema(value, schema, root_schema=None, path='$'):
    """Bounded evaluator for the exact bundled schema subset, not Draft conformance."""
    root_schema = schema if root_schema is None else root_schema
    if isinstance(schema, bool):
        require(schema, 'SCHEMA', path + ': forbidden')
        return
    if '$ref' in schema:
        ref = schema['$ref']
        require(ref.startswith('#/'), 'SCHEMA', 'external schema reference')
        target = root_schema
        for token in ref[2:].split('/'):
            target = target[token.replace('~1', '/').replace('~0', '~')]
        validate_schema(value, target, root_schema, path)
    for child in schema.get('allOf', []):
        validate_schema(value, child, root_schema, path)
    if 'if' in schema:
        try:
            validate_schema(value, schema['if'], root_schema, path)
            condition = True
        except StyleError:
            condition = False
        validate_schema(value, schema.get('then' if condition else 'else', {}), root_schema, path)
    if 'oneOf' in schema:
        matches = 0
        for child in schema['oneOf']:
            try:
                validate_schema(value, child, root_schema, path)
                matches += 1
            except StyleError:
                pass
        require(matches == 1, 'SCHEMA', path + ': oneOf')
    if 'const' in schema:
        require(_same(value, schema['const']), 'SCHEMA', path + ': const')
    if 'enum' in schema:
        require(any(_same(value, x) for x in schema['enum']), 'SCHEMA', path + ': enum')
    kind = schema.get('type')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'boolean': type(value) is bool,
             'number': type(value) in (int, float), 'integer': type(value) is int, 'null': value is None}
    require(not kind or valid.get(kind, False), 'SCHEMA', path + ': type')
    if isinstance(value, dict):
        require(all(k in value for k in schema.get('required', [])), 'SCHEMA', path + ': missing field')
        require(schema.get('minProperties', 0) <= len(value) <= schema.get('maxProperties', 100000), 'SCHEMA', path + ': object size')
        props = schema.get('properties', {})
        for key, item in value.items():
            if 'propertyNames' in schema:
                validate_schema(key, schema['propertyNames'], root_schema, path + '.key')
            validate_schema(item, props.get(key, schema.get('additionalProperties', True)), root_schema, path + '.' + key)
    elif isinstance(value, list):
        require(schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 100000), 'SCHEMA', path + ': length')
        if schema.get('uniqueItems'):
            require(len({canonical_bytes(x) for x in value}) == len(value), 'DUPLICATE_ID', path)
        for item in value:
            validate_schema(item, schema.get('items', True), root_schema, path + '[]')
    elif isinstance(value, str):
        require(schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', JSON_LIMIT), 'SCHEMA', path + ': text length')
        if 'pattern' in schema:
            require(re.fullmatch(schema['pattern'], value) is not None, 'SCHEMA', path + ': pattern')
    elif type(value) in (int, float):
        require(type(value) is int or math.isfinite(value), 'NONFINITE', path)
        require(schema.get('minimum', value) <= value <= schema.get('maximum', value), 'SCHEMA', path + ': bounds')
        require('exclusiveMinimum' not in schema or value > schema['exclusiveMinimum'], 'SCHEMA', path + ': minimum')
        require('exclusiveMaximum' not in schema or value < schema['exclusiveMaximum'], 'SCHEMA', path + ': maximum')


def _rule(rule):
    _finite(rule)
    require(isinstance(rule, dict), 'STYLE_RANGE', 'rule must be an object')
    kind = rule.get('type', 'number')
    require(kind in ('number', 'integer', 'enum', 'boolean'), 'STYLE_RANGE', 'unknown rule type')
    if kind in ('number', 'integer'):
        require(all(type(rule.get(k)) in (int, float) for k in ('min', 'max', 'default')), 'STYLE_RANGE', 'numeric rule')
        require(rule['min'] <= rule['default'] <= rule['max'], 'STYLE_RANGE', 'reversed range or default outside domain')
        if kind == 'integer':
            require(all(type(rule[k]) is int for k in ('min', 'max', 'default')), 'STYLE_RANGE', 'integer rule')
        require(rule.get('behavior', 'reject') in ('reject', 'clamp_explicit'), 'STYLE_RANGE', 'rule behavior')
    elif kind == 'enum':
        values = rule.get('values', [])
        require(isinstance(values, list) and values, 'STYLE_RANGE', 'empty enum')
        require(len({canonical_bytes(x) for x in values}) == len(values), 'DUPLICATE_ID', 'enum')
        require(any(_same(rule.get('default'), x) for x in values), 'STYLE_RANGE', 'enum default')
    else:
        require(type(rule.get('default')) is bool, 'STYLE_RANGE', 'boolean default')
    return kind


def effective_bounds(*rules):
    """Intersect core → profile → variation; never widen or silently choose defaults."""
    require(bool(rules), 'STYLE_RANGE', 'no domains')
    kinds = [_rule(rule) for rule in rules]
    require(len(set(kinds)) == 1, 'STYLE_RANGE', 'domain type disagreement')
    result = copy.deepcopy(rules[-1])
    result['type'] = kinds[0]
    if kinds[0] in ('number', 'integer'):
        result.update(min=max(r['min'] for r in rules), max=min(r['max'] for r in rules))
        result['behavior'] = 'clamp_explicit' if all(r.get('behavior') == 'clamp_explicit' for r in rules) else 'reject'
    elif kinds[0] == 'enum':
        result['values'] = [v for v in rules[0]['values'] if all(any(_same(v, x) for x in r['values']) for r in rules[1:])]
    _rule(result)
    return result


def constrain(value, bounds, clamp_explicit=False):
    kind = _rule(bounds)
    _finite(value)
    effective = value
    if kind in ('number', 'integer'):
        require(type(value) in ((int,) if kind == 'integer' else (int, float)), 'STYLE_RANGE', 'parameter type')
        if not bounds['min'] <= value <= bounds['max']:
            require(clamp_explicit and bounds.get('behavior') == 'clamp_explicit', 'STYLE_RANGE', 'outside effective bounds')
            effective = max(bounds['min'], min(bounds['max'], value))
    elif kind == 'enum':
        require(any(_same(value, x) for x in bounds['values']), 'STYLE_RANGE', 'outside enum')
    else:
        require(type(value) is bool, 'STYLE_RANGE', 'not boolean')
    return {'requested': value, 'effective': effective, 'clamped': not _same(value, effective), 'bounds': copy.deepcopy(bounds)}


def _core_rule(schema):
    if 'enum' in schema:
        return {'type': 'enum', 'values': schema['enum'], 'default': schema['default']}
    if schema['type'] == 'boolean':
        return {'type': 'boolean', 'default': schema['default']}
    require(schema['type'] in ('number', 'integer'), 'UNSUPPORTED_CAPABILITY', 'non-scalar parameter override')
    return {'type': schema['type'], 'min': schema['minimum'], 'max': schema['maximum'],
            'default': schema['default'], 'behavior': 'reject'}


def palette_contains(palette, rgb, allowed_set=None, source='texel', tolerance=0):
    require(source in ('texel', 'material_factor', 'vertex'), 'STYLE_RANGE', 'source palette checks are not lit-pixel checks')
    limit = 0 if source == 'texel' else palette[source + '_tolerance_rgb8']
    require(type(tolerance) is int and 0 <= tolerance <= limit, 'STYLE_RANGE', 'invalid conversion tolerance')
    require(isinstance(rgb, (list, tuple)) and len(rgb) == 3 and all(type(x) is int and 0 <= x <= 255 for x in rgb), 'STYLE_RANGE', 'expected RGB8')
    colors = palette['colors']
    if allowed_set is not None:
        require(allowed_set in palette['allowed_sets'], 'REFERENCE', 'unknown palette set')
        colors = {k: colors[k] for k in palette['allowed_sets'][allowed_set]}
    return any(all(abs(a - b) <= tolerance for a, b in zip(rgb, bytes.fromhex(code[1:]))) for code in colors.values())


def require_palette(palette, samples, **kwargs):
    for index, rgb in enumerate(samples):
        require(palette_contains(palette, rgb, **kwargs), 'PALETTE', 'off-palette source sample ' + str(index))
    return True


def _semantic(doc, catalog):
    s = doc['sections']
    require(set(s) == set(SECTIONS), 'SCHEMA', 'incomplete resolved profile')
    require(doc['requirements'] == catalog['requirements'], 'UNSUPPORTED_CAPABILITY', 'API contract mismatch')

    def walk(value):
        if isinstance(value, dict):
            if all(k in value for k in ('min', 'max', 'default')) or value.get('type') in ('enum', 'boolean'):
                _rule(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(s)

    def ref(value, domain):
        require(value in domain, 'REFERENCE', 'unknown reference: ' + str(value))

    def cap(value, category):
        require(value in catalog['categories'][category], 'UNSUPPORTED_CAPABILITY', category + ': ' + str(value))

    pal, mats, kits = s['palette'], s['materials'], s['kits']['selected']
    colors, ramps, sets = pal['colors'], pal['ramps'], pal['allowed_sets']
    require(len(set(colors.values())) == len(colors), 'DUPLICATE_ID', 'duplicate palette RGB')
    for seq in list(ramps.values()) + list(sets.values()) + [list(pal['roles'].values())]:
        for value in seq:
            ref(value, colors)
    ref(pal['vertex_light_ramp'], ramps)
    for mat in mats['library'].values():
        ref(mat['color'], colors)
        tex = mat['texture']
        if tex is not None:
            ref(tex['ramp'], ramps)
            cap(tex['generator'], 'texture_generators')
            # v1 admits reviewed presets only; new free-form texture parameters
            # require an explicit catalog/schema extension, never a script hook.
            require(not tex['params'], 'UNSUPPORTED_CAPABILITY', 'texture parameters not registered')
            require(tex['size_px'] <= s['validators']['budgets']['texture_px'], 'STYLE_RANGE', 'texture budget')
        if mat['environment'] is not None:
            ref(mat['environment'], mats['environments'])
        if mat['kind'] in ('chrome_env', 'glass_env'):
            require(mats['chrome_glass']['enabled'] and mat['environment'] is not None, 'REFERENCE', 'reflection without environment')
    for env in mats['environments'].values():
        cap(env['generator'], 'environment_generators')
        for color in env['stops']:
            ref(color, colors)
        require(env['size_px'] <= s['validators']['budgets']['texture_px'], 'STYLE_RANGE', 'environment budget')
    for role, material in mats['role_bindings'].items():
        ref(material, mats['library'])
        if mats['library'][material]['kind'] in ('chrome_env', 'glass_env'):
            ref(role, mats['chrome_glass']['allowed_roles'])
    for role in mats['chrome_glass']['allowed_roles']:
        ref(role, mats['role_bindings'])
    light, moods = s['lighting'], s['lighting']['moods']
    for value in [light['interior_default'], light['exterior_default']] + s['variation']['room_moods']:
        ref(value, moods)
    cap(light['shadow_recipe'], 'shadow_recipes')
    for mood in moods.values():
        for key in ('ambient', 'key', 'fill', 'rim', 'fog'):
            ref(mood[key]['color'], colors)
        for key in ('key', 'fill'):
            require(any(mood[key]['direction']), 'STYLE_RANGE', 'zero light direction')
        for key in ('lift', 'gain'):
            ref(mood['grade'][key], colors)
        require(mood['fog']['near_m'] < mood['fog']['far_m'], 'STYLE_RANGE', 'fog order')
    camera = s['camera']
    require(camera['near_m'] < camera['far_m'], 'STYLE_RANGE', 'camera clipping order')
    require(1 <= camera['fov_deg']['min'] <= camera['fov_deg']['max'] < 180, 'STYLE_RANGE', 'FOV range')
    require(camera['height_m']['min'] > 0, 'STYLE_RANGE', 'camera height')
    for mode in camera['modes']:
        cap(mode, 'camera_modes')
    for field in ('shape_vocabulary', 'silhouette_checks'):
        for value in s['geometry'][field]:
            cap(value, field)
    round_rule = dict(s['geometry']['round_segments'], type='integer')
    _rule(round_rule)
    require(3 <= round_rule['min'] <= round_rule['max'] <= 64, 'STYLE_RANGE', 'round segment ceiling')
    ceilings = {'shell': 1500, 'prop': 150, 'character': 700, 'terrain': 512, 'flora': 512, 'sky': 128}
    for name, value in s['geometry']['triangle_caps'].items():
        require(name in ceilings, 'UNSUPPORTED_CAPABILITY', 'unknown budget class')
        require(value <= ceilings[name], 'STYLE_RANGE', 'class budget exceeded')
    for group in (s['geometry']['proportions'], s['characters']['proportions']):
        require(all(r['min'] > 0 for r in group.values()), 'STYLE_RANGE', 'nonpositive proportions')
    ch = s['characters']
    for key in ('families', 'rigs', 'costume_recipes', 'face_styles', 'hair_set', 'clip_ids', 'attachment_slots'):
        for value in ch[key]:
            cap(value, key)
    cap(ch['animation_set'], 'animation_sets')
    cap(ch['pose_validator'], 'pose_validators')
    for value in list(ch['costume_palettes'].values()) + [ch['skin_palette']]:
        ref(value, sets)
    require(ch['body_triangles_max'] <= ch['total_actor_triangles_max'], 'STYLE_RANGE', 'body exceeds actor total')
    for value in s['variation']['character_costume_sets']:
        ref(value, ch['costume_palettes'])
    for role in s['props']['allowed_material_roles'] + s['exterior']['allowed_ground_roles'] + s['variation']['asset_roles']:
        ref(role, mats['role_bindings'])
    for key in s['variation']['room_numeric']:
        cap(key, 'room_numeric')
        require(s['variation']['room_numeric'][key]['min'] > 0, 'STYLE_RANGE', 'nonpositive scale')
    for color in s['ui']['colors'].values():
        ref(color, colors)
    for field, category in [('font', 'fonts'), ('frame_recipe', 'frames'), ('icons', 'icons'), ('layout', 'layouts')]:
        cap(s['ui'][field], category)
    for value in s['props']['vocabulary']:
        ref(value, s['props']['recipes'])
    for key, selected in kits.items():
        require(key in catalog['generators'], 'UNSUPPORTED_CAPABILITY', 'unknown generator ' + key)
        gen = catalog['generators'][key]
        props = gen['params_schema']['properties']
        for param, rule in selected['parameter_rules'].items():
            require(param in props, 'UNSUPPORTED_CAPABILITY', 'unknown parameter ' + param)
            effective_bounds(_core_rule(props[param]), rule)
        needed = list(gen['static_roles'])
        for param in gen['role_parameters']:
            needed += selected['parameter_rules'].get(param, {}).get('values', props[param]['enum'])
        for role in needed:
            ref(role, mats['role_bindings'])
        for recipe in selected['presets'].values():
            require(recipe['generator'] == key, 'REFERENCE', 'preset generator differs from owner')

    def recipe_check(recipe, owned=False):
        key = recipe['generator']
        require(key in catalog['generators'], 'UNSUPPORTED_CAPABILITY', 'unknown generator ' + key)
        ref(key, kits)
        gen = catalog['generators'][key]
        ref(recipe['preset'], gen['presets'] if owned else kits[key]['presets'])
        params = dict(gen['defaults'])
        for name, rule in kits[key]['parameter_rules'].items():
            params[name] = rule['default']
        if not owned:
            params.update(kits[key]['presets'][recipe['preset']]['params'])
        params.update(recipe['params'])
        props = gen['params_schema']['properties']
        require(all(key in props for key in params), 'UNSUPPORTED_CAPABILITY', 'unknown generator parameter')
        for name, value in params.items():
            validate_schema(value, props[name])
            if name in kits[key]['parameter_rules']:
                constrain(value, effective_bounds(_core_rule(props[name]), kits[key]['parameter_rules'][name]))
    for selected in kits.values():
        for recipe in selected['presets'].values():
            recipe_check(recipe, owned=True)
    for recipe in list(s['props']['recipes'].values()) + [s['exterior']['terrain'], s['exterior']['sky']] + s['exterior']['flora']:
        recipe_check(recipe)
    for value in s['kits']['required_slots'].values():
        ref(value, kits)
    graph = s['kits']['fallbacks']
    for key, values in graph.items():
        ref(key, kits)
        for value in values:
            ref(value, kits)
    def visit(key, active):
        require(key not in active, 'REFERENCE', 'fallback cycle')
        for value in graph.get(key, []):
            visit(value, active + [key])
    for key in graph:
        visit(key, [])
    cap(s['exterior']['climate'], 'climates')
    a, b, c = s['exterior']['depth_bands_m']
    require(a < b < c <= camera['far_m'], 'STYLE_RANGE', 'exterior depth order/range')
    audio = s['audio']
    cap(audio['sound_set'], 'sound_sets')
    for value in audio['allowed_tags']:
        cap(value, 'audio_tags')
    for cue in audio['cues'].values():
        require(cue['generator'] in catalog['audio_generators'], 'UNSUPPORTED_CAPABILITY', 'audio generator')
        ref(cue['preset'], catalog['audio_generators'][cue['generator']])
        constrain(cue['gain_db'], audio['gain_db'])
    budgets = s['validators']['budgets']
    require(len(colors) <= budgets['palette_colors'] and light['point_lights_max'] <= budgets['visible_lights'], 'STYLE_RANGE', 'palette/light budget')
    seen, mandatory = set(), set()
    for metric in s['validators']['metrics']:
        validator = catalog['validators'].get(metric['validator'])
        require(validator is not None, 'UNSUPPORTED_CAPABILITY', 'validator')
        require(metric['version'] == validator['version'] and metric['metric'] in validator['metrics'] and
                metric['scope'] in validator['scopes'], 'UNSUPPORTED_CAPABILITY', 'metric version/name/scope')
        key = (metric['validator'], metric['scope'], metric['metric'])
        require(key not in seen, 'DUPLICATE_ID', 'metric')
        seen.add(key)
        value = metric['value']
        if metric['op'] == 'between':
            require(isinstance(value, list) and value[0] <= value[1], 'STYLE_RANGE', 'metric interval')
        else:
            require(type(value) in (int, float), 'STYLE_RANGE', 'numeric metric')
        if metric['on_missing'] != 'fail':
            require(metric['scope'] in validator['absence_scopes'], 'REFERENCE', 'unregistered absence evidence')
        if metric['scope'] == 'room' and metric['severity'] == 'error' and metric['on_missing'] == 'fail':
            mandatory.add(metric['metric'])
    require(set(catalog['mandatory_metrics']) <= mandatory, 'REFERENCE', 'missing mandatory error gates')
    for key, category in [('known_bad_controls', 'known_bad_controls')]:
        for value in s['validators'][key]:
            cap(value, category)
    for value in s['validators']['golden']['regions']:
        cap(value, 'golden_regions')


def _png(raw):
    require(raw.startswith(b'\x89PNG\r\n\x1a\n'), 'RESOURCE_TYPE', 'PNG signature')
    offset, chunks, compressed, palette = 8, [], bytearray(), None
    width = height = channels = 0
    while offset < len(raw):
        require(offset + 12 <= len(raw), 'RESOURCE_TYPE', 'PNG chunk header')
        size = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size
        require(end <= len(raw), 'RESOURCE_TYPE', 'PNG chunk length')
        data = raw[offset + 8:end - 4]
        require(zlib.crc32(kind + data) == struct.unpack_from('>I', raw, end - 4)[0], 'RESOURCE_TYPE', 'PNG CRC')
        require(kind in (b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'), 'RESOURCE_TYPE', 'PNG metadata/extension not admitted')
        require(chunks or kind == b'IHDR', 'RESOURCE_TYPE', 'PNG first chunk must be IHDR')
        if kind == b'IHDR':
            require(not chunks and size == 13, 'RESOURCE_TYPE', 'PNG IHDR')
            width, height, depth, color, comp, filt, interlace = struct.unpack('>IIBBBBB', data)
            require(0 < width <= 128 and 0 < height <= 128 and depth == 8 and color in (2, 3, 6) and
                    (comp, filt, interlace) == (0, 0, 0), 'RESOURCE_TYPE', 'bounded PNG format')
            channels = {2: 3, 3: 1, 6: 4}[color]
        elif kind == b'PLTE':
            require(palette is None and not compressed and size % 3 == 0 and 0 < size <= 768, 'RESOURCE_TYPE', 'PNG PLTE')
            palette = data
        elif kind == b'tRNS':
            require(b'tRNS' not in chunks and not compressed and color == 3 and palette is not None and size <= len(palette) // 3, 'RESOURCE_TYPE', 'PNG transparency')
        elif kind == b'IDAT':
            require(chunks and (chunks[-1] == b'IDAT' or b'IDAT' not in chunks), 'RESOURCE_TYPE', 'PNG IDAT order')
            compressed.extend(data)
        elif kind == b'IEND':
            require(size == 0 and end == len(raw) and compressed, 'RESOURCE_TYPE', 'PNG trailing bytes/empty pixels')
        chunks.append(kind)
        offset = end
    require(chunks and chunks[0] == b'IHDR' and chunks[-1] == b'IEND', 'RESOURCE_TYPE', 'PNG structure')
    require(channels != 1 or palette is not None, 'RESOURCE_TYPE', 'PNG indexed palette missing')
    expected = height * (width * channels + 1)
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), expected + 1)
        require(len(pixels) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'RESOURCE_TYPE', 'PNG compressed payload size/trailing bytes')
        require(all(pixels[y * (width * channels + 1)] <= 4 for y in range(height)), 'RESOURCE_TYPE', 'PNG filter')
    except zlib.error as exc:
        raise StyleError('RESOURCE_TYPE', 'PNG compression') from exc


def _glb(raw):
    require(len(raw) >= 20, 'RESOURCE_TYPE', 'GLB header')
    magic, version, size = struct.unpack_from('<III', raw)
    require((magic, version, size) == (0x46546c67, 2, len(raw)), 'RESOURCE_TYPE', 'GLB header/length')
    chunks, pos = [], 12
    while pos < len(raw):
        require(pos + 8 <= len(raw), 'RESOURCE_TYPE', 'GLB chunk')
        size, kind = struct.unpack_from('<II', raw, pos)
        require(size % 4 == 0 and pos + 8 + size <= len(raw), 'RESOURCE_TYPE', 'GLB chunk length')
        chunks.append((kind, raw[pos + 8:pos + 8 + size]))
        pos += size + 8
    require([k for k, _ in chunks] in ([0x4e4f534a], [0x4e4f534a, 0x004e4942]), 'RESOURCE_TYPE', 'GLB chunk types')
    doc = parse_json(chunks[0][1])
    require(isinstance(doc, dict) and isinstance(doc.get('asset'), dict) and doc['asset'].get('version') == '2.0', 'RESOURCE_TYPE', 'GLB asset')
    require(set(doc) <= {'asset', 'accessors', 'animations', 'buffers', 'bufferViews', 'cameras', 'images',
                         'materials', 'meshes', 'nodes', 'samplers', 'scene', 'scenes', 'skins', 'textures'},
            'RESOURCE_TYPE', 'unknown GLB root field')
    require(set(doc['asset']) <= {'version', 'minVersion', 'generator', 'copyright'}, 'RESOURCE_TYPE', 'unknown GLB asset field')
    def walk(value):
        if isinstance(value, dict):
            require(not any(k in value for k in ('uri', 'extensions', 'extensionsUsed', 'extensionsRequired', 'extras', 'script', 'shader')), 'RESOURCE_TYPE', 'GLB external/active/opaque payload')
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(doc)
    buffers = doc.get('buffers', [])
    require(isinstance(buffers, list) and len(buffers) <= 1, 'RESOURCE_TYPE', 'GLB buffers')
    if buffers:
        require(isinstance(buffers[0], dict) and set(buffers[0]) <= {'name', 'byteLength'}, 'RESOURCE_TYPE', 'GLB buffer fields')
        length = buffers[0].get('byteLength')
        require(type(length) is int and length >= 0 and len(chunks) == 2 and
                length <= len(chunks[1][1]) <= length + 3, 'RESOURCE_TYPE', 'GLB buffer length')
        require(all(x == 0 for x in chunks[1][1][length:]), 'RESOURCE_TYPE', 'GLB padding')
    else:
        require(len(chunks) == 1, 'RESOURCE_TYPE', 'GLB unowned binary chunk')


def _resource_type(row, raw):
    suffix = PurePosixPath(row['path']).suffix.lower()
    if row['kind'] in ('texture', 'atlas', 'font', 'lut') and suffix == '.png':
        _png(raw)
    elif row['kind'] in ('glb', 'animation') and suffix == '.glb':
        _glb(raw)
    elif row['kind'] == 'audio' and suffix == '.wav':
        require(len(raw) >= 44 and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE' and
                struct.unpack_from('<I', raw, 4)[0] + 8 == len(raw), 'RESOURCE_TYPE', 'WAV header')
        pos, chunks = 12, {}
        while pos < len(raw):
            require(pos + 8 <= len(raw), 'RESOURCE_TYPE', 'WAV chunk')
            kind, size = raw[pos:pos + 4], struct.unpack_from('<I', raw, pos + 4)[0]
            require(kind in (b'fmt ', b'data') and kind not in chunks and pos + 8 + size <= len(raw), 'RESOURCE_TYPE', 'WAV unsupported/truncated chunk')
            chunks[kind] = raw[pos + 8:pos + 8 + size]
            pos += 8 + size + size % 2
        require(pos == len(raw) and len(chunks.get(b'fmt ', b'')) == 16 and b'data' in chunks, 'RESOURCE_TYPE', 'WAV PCM chunks')
        fmt, channels, rate, byte_rate, block, bits = struct.unpack('<HHIIHH', chunks[b'fmt '])
        require(fmt == 1 and channels in (1, 2) and rate in (11025, 22050, 44100) and bits in (8, 16) and
                block == channels * bits // 8 and byte_rate == rate * block and len(chunks[b'data']) % block == 0 and
                len(chunks[b'data']) <= byte_rate * 180, 'RESOURCE_TYPE', 'WAV PCM domain')
    else:
        raise StyleError('RESOURCE_TYPE', 'unadmitted resource encoding: ' + row['kind'])


def _inventory(root, profile_path, allowed):
    directory = confined_path(root, profile_path).parent
    found, case_names = [], set()
    for folder, dirs, files in os.walk(str(directory), followlinks=False):
        for name in sorted(dirs + files):
            path = Path(folder) / name
            rel = path.relative_to(directory).as_posix()
            require(not path.is_symlink(), 'PATH', 'symlink in profile inventory')
            require(rel.casefold() not in case_names, 'PATH', 'case collision')
            case_names.add(rel.casefold())
            if name in files:
                require(rel in allowed, 'UNLISTED_RESOURCE', rel)
                found.append(rel)
            else:
                require(any(p.startswith(rel + '/') for p in allowed), 'UNLISTED_RESOURCE', 'unowned directory ' + rel)
            require(len(case_names) <= 512, 'LIMIT', 'profile inventory')
    require(set(found) == set(allowed), 'PATH', 'missing declared resource')


@dataclass(frozen=True)
class ResolvedStyle:
    profile: dict
    canonical_bytes: bytes
    parents: tuple
    resources: tuple
    resource_bytes: dict
    closure_sha256: str
    lock_bytes: bytes
    status: str = 'data_valid_runtime_pending'


def resolve_profile(root, path, parents=None, require_runtime=False):
    """Resolve exact local ancestry. Parent pins hash canonical AUTHORED documents.

    Parent sources/resources remain in the closure even if a child replaces their
    sections. Resource IDs are profile-scoped. No ambient registry or legacy pack
    fallback is used. Returned bytes are snapshots, not paths to reopen at build.
    """
    root = Path(root).absolute()
    schema = parse_json(read_confined(ROOT, 'contracts/style/1.0.0.json'))
    catalog = parse_json(read_confined(ROOT, 'contracts/style/capabilities-1.0.0.json'))
    explicit = parents or {}
    chain, visiting, identities = [], [], {}

    def load(rel):
        relative_path(rel)
        require(len(visiting) < MAX_DEPTH, 'LIMIT', 'inheritance depth')
        require(rel not in visiting, 'INHERITANCE_CYCLE', rel)
        raw = read_confined(root, rel)
        doc = parse_json(raw)
        validate_schema(doc, schema)
        identity = (doc['id'], doc['version'])
        require(identity not in identities or identities[identity] == rel, 'DUPLICATE_ID', 'profile identity')
        identities[identity] = rel
        visiting.append(rel)
        parent = doc['extends']
        if parent:
            parent_path = explicit.get((parent['id'], parent['version']), parent['id'] + '/profile.json')
            base = load(parent_path)
            require(base['id'] == parent['id'] and base['version'] == parent['version'], 'REFERENCE', 'parent identity')
            require(digest(base) == parent['sha256'], 'PARENT_HASH', parent['id'])
            require(base['requirements'] == doc['requirements'], 'UNSUPPORTED_CAPABILITY', 'inherited API mismatch')
        visiting.pop()
        chain.append((rel, raw, doc))
        return doc
    load(path)
    sources, resources, payloads, sections = [], [], {}, {}
    total = 0
    for rel, raw, doc in chain:
        prefix = str(PurePosixPath(rel).parent)
        own_paths, own_ids = set(), set()
        for row in doc['resources']:
            require(row['id'] not in own_ids, 'DUPLICATE_ID', 'resource ID')
            own_ids.add(row['id'])
            rpath = relative_path(row['path'])
            require(rpath.casefold() not in own_paths, 'PATH', 'case-colliding resource path')
            own_paths.add(rpath.casefold())
        allowed = [PurePosixPath(rel).name] + [r['path'] for r in doc['resources']]
        require(len({p.casefold() for p in allowed}) == len(allowed), 'PATH', 'resource aliases profile')
        _inventory(root, rel, allowed)
        for row in doc['resources']:
            local = row['path'] if prefix == '.' else prefix + '/' + row['path']
            blob = read_confined(root, local, RESOURCE_LIMIT)
            total += len(blob)
            require(total <= CLOSURE_LIMIT, 'LIMIT', 'resource closure bytes')
            require(hashlib.sha256(blob).hexdigest() == row['sha256'], 'RESOURCE_HASH', row['id'])
            _resource_type(row, blob)
            key = doc['id'] + '@' + doc['version'] + '/' + row['id']
            payloads[key] = blob
            resources.append(dict(row, owner=doc['id'], version=doc['version'], bytes=len(blob)))
        sources.append({'id': doc['id'], 'version': doc['version'], 'sha256': digest(doc)})
        sections.update(copy.deepcopy(doc['sections']))
        intermediate = dict(doc, sections=copy.deepcopy(sections))
        _semantic(intermediate, catalog)
    resolved = copy.deepcopy(chain[-1][2])
    resolved['sections'] = sections
    _semantic(resolved, catalog)
    require(not require_runtime, 'UNSUPPORTED_CAPABILITY', 'runtime style adapters/proof are not implemented in steps 1–3')
    canonical = canonical_bytes(resolved)
    closure = {'schema_version': '1.0.0', 'profile_sha256': hashlib.sha256(canonical).hexdigest(),
               'sources': sources, 'resources': sorted(resources, key=lambda r: (r['owner'], r['version'], r['id'])),
               'schema_sha256': digest(schema), 'capabilities_sha256': digest(catalog),
               'resolver_sha256': hashlib.sha256(read_confined(ROOT, 'adventure_maker/style_profile.py')).hexdigest(),
               'status': 'data_valid_runtime_pending'}
    closure_hash = digest(closure)
    lock = dict(closure, closure_sha256=closure_hash)
    return ResolvedStyle(resolved, canonical, tuple(sources[:-1]), tuple(closure['resources']), payloads,
                         closure_hash, canonical_bytes(lock))


def legacy_pack_projection(root, pack_id):
    """Lossless read-only projection of explicit legacy fields, never a v1 profile.

    The legacy descriptor and view remain separate authorities in this receipt.
    Their discrepancies are not auto-reconciled and no kit-pack fallback is run.
    """
    require(isinstance(pack_id, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', pack_id) is not None, 'PATH', 'pack id')
    sources, docs = [], {}
    for name in ('pack.json', 'view.json'):
        rel = 'packs/' + pack_id + '/' + name
        raw = read_confined(root, rel)
        docs[name] = parse_json(raw)
        sources.append({'path': rel, 'sha256': hashlib.sha256(raw).hexdigest()})
    pack, view = docs['pack.json'], docs['view.json']
    require(pack.get('id') == pack_id and view.get('pack_id') == pack_id, 'REFERENCE', 'legacy identity')
    projection = {'palette': {'descriptor': pack.get('palette'), 'view': view.get('palette'), 'view_colors': view.get('palette_colors')},
                  'materials': {'descriptor': pack.get('materials'), 'look': view.get('look', {}).get('materials')},
                  'lighting': {'descriptor': pack.get('lighting'), 'fog': view.get('fog'), 'rig': view.get('light_rig'),
                               'moods': view.get('look', {}).get('profiles')},
                  'kits': {'descriptor_id': pack.get('kit_pack_id'), 'view_id': view.get('kit_pack_id'), 'presets': pack.get('presets')},
                  'exterior': {'look': view.get('look', {}).get('exterior'), 'yards': view.get('yards')},
                  'ui': view.get('ui'), 'audio': pack.get('sound_palette'),
                  'validators': {'thresholds': pack.get('thresholds'), 'style_gate': view.get('style_gate')}}
    return {'status': 'legacy_projection_incomplete', 'id': pack_id, 'sources': sources, 'projection': projection,
            'projection_sha256': digest(projection), 'unresolved_sections': list(SECTIONS),
            'note': 'Partial fields are mapped, not completed or accepted. Legacy bytes and palettes may disagree; all v1 sections still require validation.'}
