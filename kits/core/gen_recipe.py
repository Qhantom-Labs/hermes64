"""Closed, bounded JSON recipes. No source loading, expressions, paths, imports or eval.

Mesh coordinates are the native meshkit convention (+Z up, front -Y, metres).
Only project/recipes/<generic-id>.json is discoverable; never register project data globally.
"""
import hashlib
import json
import math
from pathlib import Path
import re
from typing import NoReturn

from . import meshkit as K, schema as S
from .asset import GenSpec, Node
from .genutil import finalize
from .packs import CORE_CLASSES, CORE_ROLES, OPTIONAL_ROLES

MAX_BYTES = 65536
MAX_OPERATIONS = 128
MAX_INSTANCES = 256
MAX_VERTICES = 8192
MAX_TRIANGLES = 4096
MAX_DEPTH = 12
ROLES = frozenset(CORE_ROLES) | frozenset(OPTIONAL_ROLES)
ID = re.compile(r'^[a-z][a-z0-9_]{1,47}$')
# This is a conservative input guard, not an IP/person detector. Callers add brief.ip_terms.
IP_TERMS = ('harry potter', 'hogwarts', 'pokemon', 'pikachu', 'zelda', 'mario', 'star wars',
            'disney', 'marvel', 'batman', 'superman', 'teknium', 'elon musk', 'donald trump')

# Exactly the real primitive signatures we expose. Unsupported kwargs are refused before allocation.
ARGS = {
    'box': (('cx', 'cy', 'cz', 'sx', 'sy', 'sz'), ()),
    'prism': (('outline', 'z0', 'z1'), ()),
    'lathe': (('profile', 'segs'), ('rx', 'ry')),
    'loft': (('rings',), ()),
    'tube': (('path', 'radius', 'sides'), ()),
    'blob': (('cx', 'cy', 'cz', 'rx', 'ry', 'rz'), ('segs', 'rings', 'squash_bottom')),
    'torus': (('R', 'r', 'segs', 'sides'), ()),
    'card': (('w', 'h'), ()),
    'grid_surface': (('nu', 'nv', 'width', 'depth', 'heights'), ()),
}


class RecipeError(S.ParamError):
    """One-line, actionable refusal, never an interpreter traceback in the CLI."""


def refuse(message) -> NoReturn:
    raise RecipeError(' '.join(str(message).splitlines())[:240])


def generic_id(value, forbidden_terms=()):
    if not isinstance(value, str) or not ID.fullmatch(value):
        refuse('recipe id: use 2-48 lowercase letters, digits and underscores, starting with a letter')
    words = value.replace('_', ' ')
    for term in tuple(IP_TERMS) + tuple(forbidden_terms):
        term = re.sub(r'[^a-z0-9]+', ' ', str(term).lower()).strip()
        if term and term in words:
            refuse('recipe id: use a generic piece name, not a franchise or real-person name')
    return value


def _keys(value, allowed, required=(), where='recipe'):
    if not isinstance(value, dict):
        refuse(where + ': expected object')
    unknown = sorted(set(value) - set(allowed))
    missing = sorted(set(required) - set(value))
    if unknown:
        refuse(where + ': unknown field ' + str(unknown[0]))
    if missing:
        refuse(where + ': missing field ' + str(missing[0]))


def _bounded_tree(value, depth=0, counter=None, where='recipe'):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > MAX_DEPTH or counter[0] > 12000:
        refuse('recipe nesting/data budget exceeded')
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str) or len(k) > 64:
                refuse('recipe keys must be short strings')
            _bounded_tree(v, depth + 1, counter, where + '.' + k)
    elif isinstance(value, list):
        if len(value) > 256:
            refuse('recipe array budget exceeded')
        for i, v in enumerate(value):
            _bounded_tree(v, depth + 1, counter, where + '[%d]' % i)
    elif isinstance(value, str):
        if len(value) > 160 or any(ord(c) < 32 for c in value):
            refuse('recipe strings must be short single-line values')
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if abs(value) > 1e6:
            refuse(where + ': finite numeric magnitude exceeds data budget')
        if not math.isfinite(value):
            refuse('recipe numbers must be finite')
    elif value is not None and not isinstance(value, bool):
        refuse('recipe contains a non-JSON value')


def canonical(doc):
    _bounded_tree(doc)
    try:
        raw = json.dumps(doc, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError):
        refuse('recipe must be finite JSON data')
    if len(raw) > MAX_BYTES:
        refuse('recipe byte budget exceeded')
    return raw


def recipe_hash(doc):
    return hashlib.sha256(canonical(doc)).hexdigest()


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            refuse('recipe JSON: duplicate field ' + k)
        d[k] = v
    return d


def decode(raw):
    if len(raw) > MAX_BYTES:
        refuse('recipe byte budget exceeded')
    try:
        doc = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda x: refuse('recipe numbers must be finite'))
    except (ValueError, RecursionError, UnicodeError) as e:
        refuse('recipe JSON: ' + str(e))
    canonical(doc)
    return doc


def load_recipe(project_dir, gid):
    if not isinstance(gid, str) or not gid.startswith('gen:'):
        refuse('recipe id must start with gen:')
    slug = generic_id(gid[4:])
    root = Path(project_dir).resolve()
    folder = root / 'recipes'
    path = folder / (slug + '.json')
    if folder.is_symlink() or path.is_symlink():
        refuse('recipe symlinks are not allowed')
    if not path.is_file():
        refuse('project recipe not found: ' + gid)
    if path.stat().st_size > MAX_BYTES:
        refuse('recipe byte budget exceeded')
    with path.open('rb') as f:
        doc = decode(f.read(MAX_BYTES + 1))
    if not isinstance(doc, dict):
        refuse('recipe JSON must be an object')
    if doc.get('id') != slug:
        refuse('recipe id must match its project filename')
    return doc


def _number(value, params):
    if isinstance(value, dict):
        _keys(value, ('param', 'mul', 'add'), ('param',), 'number reference')
        name = value['param']
        if not isinstance(name, str) or name not in params:
            refuse('number reference: unknown parameter')
        mul, add = value.get('mul', 1), value.get('add', 0)
        for x in (mul, add):
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > 100:
                refuse('number reference: finite mul/add in [-100,100] required')
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            refuse('number reference requires a numeric parameter')
        value = value * mul + add
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        refuse('expected number or bounded parameter reference')
    if not math.isfinite(value):
        refuse('recipe numbers must be finite')
    if abs(value) > 100:
        refuse('recipe number outside [-100,100]')
    return value


def _vec(value, params, n=3):
    if not isinstance(value, list) or len(value) != n:
        refuse('coordinate requires %d numbers' % n)
    return [_number(x, params) for x in value]


def _integer(value, params, lo=3, hi=32, label='segments'):
    try:
        x = _number(value, params)
    except RecipeError:
        refuse('%s: integer in [%d,%d] required' % (label, lo, hi))
    if int(x) != x or not lo <= x <= hi:
        refuse('%s: integer in [%d,%d] required' % (label, lo, hi))
    return int(x)


def _role(value, params):
    if isinstance(value, dict):
        _keys(value, ('param',), ('param',), 'role reference')
        if not isinstance(value['param'], str):
            refuse('role reference requires a named parameter')
        value = params.get(value['param'])
    if not isinstance(value, str) or value not in ROLES:
        refuse('unknown palette/texture role; use a named pack role, never an RGB colour or path')
    return value


def _resolved_args(op, params):
    prim, raw = op['primitive'], op['args']
    req, optional = ARGS[prim]
    _keys(raw, req + optional, req, prim + ' args')
    args = {}
    for k, v in raw.items():
        if k in ('outline', 'profile', 'path'):
            n = 3 if k == 'path' else 2
            if not isinstance(v, list) or not (2 if k != 'outline' else 3) <= len(v) <= 32:
                refuse(k + ': need 2-32 points (3 for an outline)')
            args[k] = [_vec(p, params, n) for p in v]
        elif k == 'rings' and prim == 'loft':
            if not isinstance(v, list) or not 2 <= len(v) <= 16:
                refuse('loft rings: need 2-16 rings')
            if not isinstance(v[0], list) or not 3 <= len(v[0]) <= 32:
                refuse('loft ring: need 3-32 points')
            if any(not isinstance(ring, list) or len(ring) != len(v[0]) for ring in v):
                refuse('loft rings must be lists with equal point counts')
            args[k] = [[_vec(p, params) for p in ring] for ring in v]
        elif k == 'heights':
            if not isinstance(v, list):
                refuse('grid heights must be a list of rows')
            args[k] = [[_number(x, params) for x in row] for row in v if isinstance(row, list)]
            if len(args[k]) != len(v):
                refuse('grid heights must be rows of numbers')
        elif k in ('segs', 'sides', 'rings', 'nu', 'nv'):
            args[k] = _integer(v, params, 1 if k in ('nu', 'nv') else 3, 24, k)
        else:
            args[k] = _number(v, params)
    for k in ('sx', 'sy', 'sz', 'rx', 'ry', 'rz', 'R', 'r', 'radius', 'w', 'h', 'width', 'depth'):
        if k in args and args[k] <= 0:
            refuse(k + ': positive size required')
    if prim == 'prism' and args['z1'] <= args['z0']:
        refuse('prism z1 must exceed z0')
    if prim == 'lathe':
        prof = args['profile']
        if any(r < 0 for r, z in prof) or any(b[1] <= a[1] for a, b in zip(prof, prof[1:])):
            refuse('lathe: nonnegative radii and strictly increasing profile heights required')
    if prim == 'blob' and not 0 <= args.get('squash_bottom', 0) < 1:
        refuse('blob squash_bottom must be in [0,1)')
    if prim == 'torus' and args['r'] >= args['R']:
        refuse('torus minor radius must be less than major radius')
    if prim == 'tube' and any(a == b for a, b in zip(args['path'], args['path'][1:])):
        refuse('tube path points must be distinct')
    if prim == 'grid_surface':
        if len(args['heights']) != args['nv'] + 1 or any(len(row) != args['nu'] + 1 for row in args['heights']):
            refuse('grid heights must be (nv+1) rows of (nu+1) numbers')
    return args


def _parameters(doc):
    raw = doc.get('parameters', {})
    if not isinstance(raw, dict) or len(raw) > 16:
        refuse('parameters: at most 16 bounded values')
    props = {}
    for name, p in raw.items():
        generic_id(name)
        _keys(p, ('type', 'default', 'minimum', 'maximum', 'enum'), ('type', 'default'), 'parameter')
        if p['type'] in ('number', 'integer'):
            _keys(p, ('type', 'default', 'minimum', 'maximum'), ('minimum', 'maximum'), 'numeric parameter')
            lo, hi, default = [_number(p[k], {}) for k in ('minimum', 'maximum', 'default')]
            if lo > hi or not lo <= default <= hi:
                refuse('parameter default outside its bounds')
            if p['type'] == 'integer' and any(int(x) != x for x in (lo, hi, default)):
                refuse('integer parameter bounds and default must be integers')
        elif p['type'] == 'string':
            _keys(p, ('type', 'default', 'enum'), ('enum',), 'role parameter')
            if not isinstance(p['enum'], list) or not 1 <= len(p['enum']) <= 8:
                refuse('role parameter needs 1-8 palette roles')
            for role in p['enum'] + [p['default']]:
                _role(role, {})
            if p['default'] not in p['enum']:
                refuse('role parameter default outside enum')
        else:
            refuse('parameter type must be number, integer or palette-role string')
        props[name] = p
    return props


def validate_recipe(doc, forbidden_terms=()):
    canonical(doc)
    _keys(doc, ('format', 'id', 'class', 'licence', 'parameters', 'operations', 'sockets'),
          ('format', 'id', 'class', 'licence', 'operations'))
    if doc['format'] != 'hermes64-recipe/1':
        refuse('recipe format must be hermes64-recipe/1')
    generic_id(doc['id'], forbidden_terms)
    if not isinstance(doc['class'], str) or doc['class'] not in CORE_CLASSES or doc['class'] in ('character', 'animal'):
        refuse('unknown or out-of-scope recipe class (characters/animals use their own maker)')
    if not isinstance(doc['licence'], str) or not re.fullmatch(r'[A-Za-z0-9.+-]{2,64}', doc['licence']):
        refuse('licence: a single SPDX identifier or LicenseRef identifier is required')
    props = _parameters(doc)
    params = {k: v['default'] for k, v in props.items()}
    ops = doc['operations']
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPERATIONS:
        refuse('operations: need 1-%d primitive operations' % MAX_OPERATIONS)
    instances = 0
    for op in ops:
        _keys(op, ('primitive', 'args', 'role', 'smooth', 'transform', 'repeat', 'mirror'),
              ('primitive', 'args', 'role'), 'operation')
        if not isinstance(op['primitive'], str) or op['primitive'] not in ARGS:
            refuse('unknown primitive; allowed: ' + ', '.join(ARGS))
        _role(op['role'], params)
        _resolved_args(op, params)
        if 'smooth' in op and not isinstance(op['smooth'], bool):
            refuse('smooth must be boolean')
        tr = op.get('transform', {})
        _keys(tr, ('translate', 'rotate', 'scale'), where='transform')
        for k, v in tr.items():
            vec = _vec(v, params)
            if k == 'scale' and any(x <= 0 or x > 10 for x in vec):
                refuse('transform scale outside (0,10]')
        repeat = op.get('repeat', {'count': 1})
        _keys(repeat, ('count', 'step', 'rotate'), ('count',), 'repeat')
        if not isinstance(repeat['count'], int) or isinstance(repeat['count'], bool):
            refuse('repeat count: integer in [1,32] required')
        count = _integer(repeat['count'], {}, 1, 32, 'repeat count')
        for k in ('step', 'rotate'):
            if k in repeat:
                _vec(repeat[k], params)
        if op.get('mirror') not in (None, 'x', 'y', 'z'):
            refuse('mirror must be x, y or z')
        instances += count * (2 if op.get('mirror') else 1)
    if instances > MAX_INSTANCES:
        refuse('expanded instance budget exceeded')
    sockets = doc.get('sockets', [])
    if not isinstance(sockets, list) or len(sockets) > 16:
        refuse('sockets: at most 16')
    names = []
    for s in sockets:
        _keys(s, ('id', 'position', 'facing'), ('id', 'position', 'facing'), 'socket')
        generic_id(s['id']); _vec(s['position'], params)
        if s['id'] in names or s['facing'] not in ('n', 'e', 's', 'w', 'up', 'down'):
            refuse('socket: unique id and a cardinal facing required')
        names.append(s['id'])
    return props


def _primitive(op, params):
    args = _resolved_args(op, params)
    prim = op['primitive']
    role = _role(op['role'], params)
    smooth = op.get('smooth', False)
    if prim == 'grid_surface':
        nu, nv = args['nu'], args['nv']
        heights = args['heights']
        def point(u, v):
            return ((u - .5) * args['width'], (v - .5) * args['depth'], heights[round(v * nv)][round(u * nu)])
        return K.grid_surface(nu, nv, point, role, smooth=smooth)
    fn = {'box': K.box, 'prism': K.prism, 'lathe': K.lathe, 'loft': K.loft,
          'tube': K.tube, 'blob': K.blob, 'torus': K.torus, 'card': K.card}[prim]
    args['role'] = role
    if prim == 'prism':
        args['smooth_sides'] = smooth
    elif prim != 'card':
        args['smooth'] = smooth
    return fn(**args)


def build_recipe(doc, params=None, seed=0):
    props = validate_recipe(doc)
    try:
        P = S.resolve(S.obj(props), [('params', params or {})], None)
    except S.ParamError as e:
        refuse(e)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**31:
        refuse('seed must be an integer in [0,2^31]')
    nodes, vertices, triangles = [], 0, 0
    limit = CORE_CLASSES[doc['class']]
    for op in doc['operations']:
        # Primitive arguments are bounded before allocation, even at non-default parameters.
        m = _primitive(op, P)
        tr, repeat = op.get('transform', {}), op.get('repeat', {'count': 1})
        scale = _vec(tr.get('scale', [1, 1, 1]), P)
        if any(x <= 0 or x > 10 for x in scale):
            refuse('transform scale outside (0,10]')
        m.scale(*scale)
        for axis, ang in zip('xyz', _vec(tr.get('rotate', [0, 0, 0]), P)):
            getattr(m, 'rotate_' + axis)(math.radians(ang))
        m.translate(*_vec(tr.get('translate', [0, 0, 0]), P))
        for i in range(repeat['count']):
            part = m.copy()
            for axis, ang in zip('xyz', _vec(repeat.get('rotate', [0, 0, 0]), P)):
                getattr(part, 'rotate_' + axis)(math.radians(i * ang))
            part.translate(*[i * x for x in _vec(repeat.get('step', [0, 0, 0]), P)])
            parts = [part]
            if op.get('mirror'):
                dims = [-1 if a == op['mirror'] else 1 for a in 'xyz']
                parts.append(part.copy().scale(*dims))
            for part in parts:
                vertices += len(part.v); triangles += part.tri_count()
                if vertices > MAX_VERTICES or triangles > min(limit, MAX_TRIANGLES):
                    refuse('budget: %d triangles > %d or %d vertices > %d; simplify or reduce repeats/segments' %
                           (triangles, min(limit, MAX_TRIANGLES), vertices, MAX_VERTICES))
                if not all(math.isfinite(c) and abs(c) <= 1000 for v in part.v for c in v):
                    refuse('mesh coordinates must be finite and bounded')
                kind = 'card' if op['primitive'] == 'card' else ('shell' if op['primitive'] == 'grid_surface' else 'solid')
                nodes.append(Node('%s_%03d' % (doc['id'], len(nodes)), part, kind=kind, double_sided=kind == 'card'))
    asset = finalize(nodes, {'recipe_sha256': recipe_hash(doc), 'recipe_id': doc['id'], 'seed': seed})
    # Mesh centring/grounding applies to sockets too; sockets are authored in pre-finalize mesh space.
    # Match sfkit.socket: metadata positions are glTF +Y-up (x,z,-y), not meshkit +Z-up.
    delta = nodes[0].origin
    sockets = []
    for s in doc.get('sockets', []):
        x, y, z = [float(v + d) for v, d in zip(_vec(s['position'], P), delta)]
        sockets.append(dict(s, type='anchor', position=[round(x, 4), round(z, 4), round(-y, 4)]))
    asset.meta['sockets'] = sockets
    return asset


def spec_from_recipe(doc, forbidden_terms=()):
    props = validate_recipe(doc, forbidden_terms)
    # Detach the closure from mutable caller data. Project data never enters REGISTRY.
    frozen = json.loads(canonical(doc))
    return GenSpec('gen:' + frozen['id'], '1.0.0', frozen['class'], props,
                   'Project JSON recipe ' + frozen['id'], lambda P, seed: build_recipe(frozen, P, seed))
