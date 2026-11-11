"""Structural GLB validation (stdlib only), run on every shipped/exported GLB.

Our own checks, written for the Hermes64 asset contract; not a replacement for the Khronos glTF-Validator, which
users can run as an optional external check (it is not bundled and nothing here depends on it). It cannot judge
our intentionally nonstandard display-space vertex colours either; that encoding is checked separately.

Checks: container (magic/version/length/chunk alignment, BIN size), buffer views (bounds, byteStride rules),
accessors (component/type, alignment, data inside the view, element size <= stride, POSITION min/max present and
matching the data, finite floats, normalized only on integer types), primitives (accessor refs, equal attribute
counts, triangle mode, index range, index count multiple of 3), normals (unit length), UV range, skins (joint
nodes, inverse bind count, JOINTS < joint count, WEIGHTS non-negative and summing to 1), names (nodes/meshes/
materials named, ASCII, node names unique; unnamed meshes/materials are warnings), references (materials, textures, images, samplers, scenes, node
graph without cycles) and an optional triangle budget.

  python3 -m adventure_maker.glb_validate FILE.glb [...] [--budget N] [--json]
  python3 -m adventure_maker.glb_validate --library [--controls]     # every kit/placeholder GLB + known-bad controls
"""
import json
import math
import struct
import sys
from pathlib import Path

COMPONENTS = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
UV_LIMIT = 64.0          # |u|,|v| beyond this is almost certainly broken data for 16-64 px tiling textures
NORMAL_TOL = 0.02
WEIGHT_TOL = 0.01
BOUNDS_TOL = 1e-4


class Report:
    def __init__(self, name=''):
        self.name = name
        self.issues = []
        self.stats = {}

    def error(self, code, path, msg):
        self.issues.append({'severity': 'error', 'code': code, 'path': path, 'message': msg})

    def warn(self, code, path, msg):
        self.issues.append({'severity': 'warning', 'code': code, 'path': path, 'message': msg})

    @property
    def ok(self):
        return not any(i['severity'] == 'error' for i in self.issues)

    def as_dict(self):
        return {'file': self.name, 'ok': self.ok, 'issues': self.issues, 'stats': self.stats}


def _container(data, rep):
    if len(data) < 20:
        rep.error('container.size', '', 'file shorter than a GLB header')
        return None, None
    magic, version, length = struct.unpack_from('<4sII', data)
    if magic != b'glTF':
        rep.error('container.magic', '', 'bad magic %r' % magic)
        return None, None
    if version != 2:
        rep.error('container.version', '', 'GLB version %d (need 2)' % version)
    if length != len(data):
        rep.error('container.length', '', 'header length %d != file size %d' % (length, len(data)))
    pos, doc, binary, first = 12, None, None, True
    while pos + 8 <= min(length, len(data)):
        n, kind = struct.unpack_from('<I4s', data, pos)
        if n % 4:
            rep.error('container.alignment', 'chunk@%d' % pos, 'chunk length %d not 4-byte aligned' % n)
        if pos + 8 + n > len(data):
            rep.error('container.truncated', 'chunk@%d' % pos, 'chunk runs past the end of the file')
            break
        body = data[pos + 8:pos + 8 + n]
        if kind == b'JSON':
            if not first:
                rep.error('container.order', 'chunk@%d' % pos, 'JSON chunk must be first')
            try:
                doc = json.loads(body)
            except ValueError as e:
                rep.error('container.json', 'chunk@%d' % pos, 'invalid JSON: %s' % e)
        elif kind == b'BIN\0':
            binary = bytes(body)
        first = False
        pos += 8 + n
    if doc is None:
        rep.error('container.json', '', 'missing JSON chunk')
    return doc, binary


def _ref(rep, doc, kind, index, path):
    arr = doc.get(kind, [])
    if not isinstance(index, int) or not 0 <= index < len(arr):
        rep.error('ref.' + kind, path, '%s index %r out of range (%d)' % (kind, index, len(arr)))
        return False
    return True


def _read_accessor(doc, binary, i):
    a = doc['accessors'][i]
    v = doc['bufferViews'][a['bufferView']]
    fmt, size = COMPONENTS[a['componentType']]
    width = WIDTH[a['type']]
    stride = v.get('byteStride', size * width)
    off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    rows = [struct.unpack_from('<' + fmt * width, binary, off + k * stride) for k in range(a['count'])]
    if a.get('normalized') and fmt != 'f':
        scale = {'B': 255.0, 'b': 127.0, 'H': 65535.0, 'h': 32767.0}[fmt]
        rows = [tuple(max(-1.0, x / scale) for x in r) for r in rows]
    return rows


def _views(doc, binary, rep):
    blen = len(binary) if binary is not None else 0
    bufs = doc.get('buffers', [])
    if bufs:
        bl = bufs[0].get('byteLength', 0)
        if bl > blen:
            rep.error('buffer.length', 'buffers[0]', 'byteLength %d > BIN chunk %d' % (bl, blen))
        if len(bufs) > 1 or bufs[0].get('uri'):
            rep.error('buffer.external', 'buffers', 'external buffers are not allowed in shipped GLBs')
    index_views = set()
    for m in doc.get('meshes', []):
        for p in m.get('primitives', []):
            if isinstance(p.get('indices'), int) and p['indices'] < len(doc.get('accessors', [])):
                bv = doc['accessors'][p['indices']].get('bufferView')
                if bv is not None:
                    index_views.add(bv)
    for vi, v in enumerate(doc.get('bufferViews', [])):
        path = 'bufferViews[%d]' % vi
        off, n = v.get('byteOffset', 0), v.get('byteLength', 0)
        if off < 0 or n <= 0 or off + n > blen:
            rep.error('view.bounds', path, 'range %d+%d outside the %d-byte buffer' % (off, n, blen))
        if 'byteStride' in v:
            s = v['byteStride']
            if not isinstance(s, int) or s < 4 or s > 252 or s % 4:
                rep.error('view.stride', path, 'byteStride %r invalid (must be 4..252, multiple of 4)' % (s,))
            if vi in index_views:
                rep.error('view.stride', path, 'index buffer views must not define byteStride')


def _accessors(doc, binary, rep):
    good = set()
    for ai, a in enumerate(doc.get('accessors', [])):
        path = 'accessors[%d]' % ai
        if a.get('componentType') not in COMPONENTS or a.get('type') not in WIDTH:
            rep.error('accessor.type', path, 'componentType %r / type %r invalid' % (a.get('componentType'), a.get('type')))
            continue
        if a.get('count', 0) < 1:
            rep.error('accessor.count', path, 'count must be >= 1')
            continue
        if a.get('bufferView') is None:
            rep.error('accessor.view', path, 'sparse/zero accessors are not used by the kit pipeline')
            continue
        if not _ref(rep, doc, 'bufferViews', a['bufferView'], path):
            continue
        v = doc['bufferViews'][a['bufferView']]
        fmt, size = COMPONENTS[a['componentType']]
        elem = size * WIDTH[a['type']]
        stride = v.get('byteStride', elem)
        if a.get('byteOffset', 0) % size or (v.get('byteOffset', 0) + a.get('byteOffset', 0)) % size:
            rep.error('accessor.alignment', path, 'byte offset not aligned to the %d-byte component' % size)
            continue
        if isinstance(stride, int) and stride < elem:
            rep.error('accessor.stride', path, 'element size %d > byteStride %d (interleaving overlap)' % (elem, stride))
            continue
        need = a.get('byteOffset', 0) + (stride if isinstance(stride, int) else elem) * (a['count'] - 1) + elem
        if need > v.get('byteLength', 0) or v.get('byteOffset', 0) + v.get('byteLength', 0) > (len(binary) if binary else 0):
            rep.error('accessor.bounds', path, 'needs %d bytes, view has %d' % (need, v.get('byteLength', 0)))
            continue
        if a.get('normalized') and fmt == 'f':
            rep.error('accessor.normalized', path, 'normalized is only valid for integer components')
        good.add(ai)
        if fmt == 'f':
            rows = _read_accessor(doc, binary, ai)
            if any(not math.isfinite(x) for r in rows for x in r):
                rep.error('accessor.nan', path, 'NaN/Inf values')
                good.discard(ai)
    return good


def _check_bounds(doc, binary, rep, ai, path):
    a = doc['accessors'][ai]
    if 'min' not in a or 'max' not in a:
        rep.error('position.bounds', path, 'POSITION accessor lacks min/max')
        return None
    rows = _read_accessor(doc, binary, ai)
    lo = [min(r[k] for r in rows) for k in range(3)]
    hi = [max(r[k] for r in rows) for k in range(3)]
    if any(abs(lo[k] - a['min'][k]) > BOUNDS_TOL * max(1.0, abs(lo[k])) or abs(hi[k] - a['max'][k]) > BOUNDS_TOL * max(1.0, abs(hi[k]))
           for k in range(3)):
        rep.error('position.bounds', path, 'declared min/max %s/%s differ from data %s/%s' % (
            a['min'], a['max'], [round(x, 4) for x in lo], [round(x, 4) for x in hi]))
    return lo, hi


def _primitives(doc, binary, rep, good):
    tris = 0
    uv_lo, uv_hi = [math.inf, math.inf], [-math.inf, -math.inf]
    for mi, m in enumerate(doc.get('meshes', [])):
        for pi, p in enumerate(m.get('primitives', [])):
            path = 'meshes[%d].primitives[%d]' % (mi, pi)
            attrs = p.get('attributes', {})
            if 'POSITION' not in attrs:
                rep.error('primitive.position', path, 'no POSITION attribute')
                continue
            if p.get('mode', 4) != 4:
                rep.error('primitive.mode', path, 'mode %r (kit meshes are triangle lists)' % p.get('mode'))
            counts = {}
            ok = True
            for name, ai in attrs.items():
                if not _ref(rep, doc, 'accessors', ai, path + '.' + name):
                    ok = False
                    continue
                counts[name] = doc['accessors'][ai]['count']
                if ai not in good:
                    ok = False
            if len(set(counts.values())) > 1:
                rep.error('primitive.counts', path, 'attribute counts differ: %s' % counts)
                ok = False
            if 'material' in p:
                _ref(rep, doc, 'materials', p['material'], path + '.material')
            if not ok:
                continue
            nvert = counts['POSITION']
            _check_bounds(doc, binary, rep, attrs['POSITION'], path + '.POSITION')
            if 'indices' in p:
                if not _ref(rep, doc, 'accessors', p['indices'], path + '.indices') or p['indices'] not in good:
                    continue
                ia = doc['accessors'][p['indices']]
                if ia['componentType'] not in (5121, 5123, 5125) or ia['type'] != 'SCALAR':
                    rep.error('indices.type', path, 'indices must be unsigned SCALAR')
                    continue
                idx = [r[0] for r in _read_accessor(doc, binary, p['indices'])]
                if ia['count'] % 3:
                    rep.error('indices.count', path, 'index count %d not a multiple of 3' % ia['count'])
                bad = [i for i in idx if i >= nvert]
                if bad:
                    rep.error('indices.range', path, '%d indices >= vertex count %d (max %d)' % (len(bad), nvert, max(bad)))
                tris += ia['count'] // 3
            else:
                if nvert % 3:
                    rep.error('indices.count', path, 'non-indexed vertex count %d not a multiple of 3' % nvert)
                tris += nvert // 3
            if 'NORMAL' in attrs:
                bad = [r for r in _read_accessor(doc, binary, attrs['NORMAL']) if abs(math.sqrt(sum(x * x for x in r)) - 1.0) > NORMAL_TOL]
                if bad:
                    rep.error('normal.length', path, '%d normals are not unit length' % len(bad))
            for name in [k for k in attrs if k.startswith('TEXCOORD_')]:
                rows = _read_accessor(doc, binary, attrs[name])
                for k in range(2):
                    uv_lo[k] = min(uv_lo[k], min(r[k] for r in rows))
                    uv_hi[k] = max(uv_hi[k], max(r[k] for r in rows))
                if any(abs(x) > UV_LIMIT for r in rows for x in r):
                    rep.error('uv.range', path + '.' + name, 'UVs beyond +-%g (got %s..%s)' % (
                        UV_LIMIT, [round(min(r[k] for r in rows), 2) for k in range(2)], [round(max(r[k] for r in rows), 2) for k in range(2)]))
            if 'JOINTS_0' in attrs or 'WEIGHTS_0' in attrs:
                _skin_attrs(doc, binary, rep, attrs, path)
    rep.stats['tri_count'] = tris
    if uv_lo[0] != math.inf:
        rep.stats['uv_range'] = [[round(uv_lo[0], 3), round(uv_lo[1], 3)], [round(uv_hi[0], 3), round(uv_hi[1], 3)]]
    return tris


def _skin_attrs(doc, binary, rep, attrs, path):
    if 'JOINTS_0' not in attrs or 'WEIGHTS_0' not in attrs:
        rep.error('skin.attributes', path, 'JOINTS_0 and WEIGHTS_0 must come together')
        return
    users = [n for n in doc.get('nodes', []) if 'skin' in n]
    njoints = max((len(doc['skins'][n['skin']].get('joints', [])) for n in users if 0 <= n['skin'] < len(doc.get('skins', []))), default=0)
    joints = _read_accessor(doc, binary, attrs['JOINTS_0'])
    weights = _read_accessor(doc, binary, attrs['WEIGHTS_0'])
    if njoints and any(j >= njoints for r in joints for j in r):
        rep.error('skin.joints', path, 'JOINTS_0 references joint >= %d' % njoints)
    if any(w < -1e-6 for r in weights for w in r):
        rep.error('skin.weights', path, 'negative weights')
    bad = [r for r in weights if abs(sum(r) - 1.0) > WEIGHT_TOL]
    if bad:
        rep.error('skin.weights', path, '%d vertices with weights not summing to 1 (e.g. %.3f)' % (len(bad), sum(bad[0])))


def _skins(doc, binary, rep, good):
    for si, s in enumerate(doc.get('skins', [])):
        path = 'skins[%d]' % si
        joints = s.get('joints', [])
        if not joints:
            rep.error('skin.joints', path, 'skin without joints')
        for j in joints:
            _ref(rep, doc, 'nodes', j, path + '.joints')
        if 'inverseBindMatrices' in s and _ref(rep, doc, 'accessors', s['inverseBindMatrices'], path + '.inverseBindMatrices'):
            a = doc['accessors'][s['inverseBindMatrices']]
            if a.get('type') != 'MAT4' or a.get('count') != len(joints):
                rep.error('skin.ibm', path, 'inverseBindMatrices must be %d MAT4 (got %s x %s)' % (len(joints), a.get('count'), a.get('type')))


def _names_refs(doc, rep):
    seen = {}
    single = {'nodes': 'node', 'meshes': 'mesh', 'materials': 'material'}
    for kind in ('nodes', 'meshes', 'materials'):
        for i, o in enumerate(doc.get(kind, [])):
            nm = o.get('name', '')
            if not nm:
                # node names are the runtime contract (lookups, kit naming); mesh/material names are advisory
                (rep.error if kind == 'nodes' else rep.warn)('names.missing', '%s[%d]' % (kind, i), 'unnamed %s' % single[kind])
            elif not all(32 <= ord(ch) < 127 for ch in nm):
                rep.error('names.ascii', '%s[%d]' % (kind, i), 'non-ASCII name %r' % nm)
            if kind == 'nodes' and nm:
                if nm in seen:
                    rep.error('names.duplicate', 'nodes[%d]' % i, 'node name %r repeats nodes[%d]' % (nm, seen[nm]))
                seen[nm] = i
    for i, n in enumerate(doc.get('nodes', [])):
        if 'mesh' in n:
            _ref(rep, doc, 'meshes', n['mesh'], 'nodes[%d].mesh' % i)
        if 'skin' in n:
            _ref(rep, doc, 'skins', n['skin'], 'nodes[%d].skin' % i)
        for c in n.get('children', []):
            _ref(rep, doc, 'nodes', c, 'nodes[%d].children' % i)
    # node graph: every node at most one parent, no cycles
    parent = {}
    for i, n in enumerate(doc.get('nodes', [])):
        for c in n.get('children', []):
            if c in parent:
                rep.error('nodes.parent', 'nodes[%d]' % c, 'node has two parents')
            parent[c] = i
    for start in parent:
        cur, hops = start, 0
        while cur in parent and hops <= len(doc.get('nodes', [])):
            cur, hops = parent[cur], hops + 1
        if hops > len(doc.get('nodes', [])):
            rep.error('nodes.cycle', 'nodes[%d]' % start, 'node hierarchy cycle')
            break
    for si, s in enumerate(doc.get('scenes', [])):
        for n in s.get('nodes', []):
            _ref(rep, doc, 'nodes', n, 'scenes[%d]' % si)
    for i, m in enumerate(doc.get('materials', [])):
        t = m.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if t is not None:
            _ref(rep, doc, 'textures', t.get('index'), 'materials[%d].baseColorTexture' % i)
    for i, t in enumerate(doc.get('textures', [])):
        if 'source' in t:
            _ref(rep, doc, 'images', t['source'], 'textures[%d].source' % i)
        if 'sampler' in t:
            _ref(rep, doc, 'samplers', t['sampler'], 'textures[%d].sampler' % i)


def _images(doc, binary, rep):
    for i, im in enumerate(doc.get('images', [])):
        if im.get('uri'):
            rep.error('image.external', 'images[%d]' % i, 'external image URIs are not allowed in shipped GLBs')
            continue
        if not _ref(rep, doc, 'bufferViews', im.get('bufferView'), 'images[%d]' % i):
            continue
        v = doc['bufferViews'][im['bufferView']]
        head = binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + 8] if binary else b''
        if im.get('mimeType') == 'image/png' and head != b'\x89PNG\r\n\x1a\n':
            rep.error('image.png', 'images[%d]' % i, 'mimeType image/png but data is not a PNG')


def validate(data, name='', budget=None):
    rep = Report(name)
    doc, binary = _container(data, rep)
    if doc is None:
        return rep
    if doc.get('asset', {}).get('version') != '2.0':
        rep.error('asset.version', 'asset', 'asset.version must be "2.0"')
    binary = binary or b''
    _views(doc, binary, rep)
    good = _accessors(doc, binary, rep)
    tris = _primitives(doc, binary, rep, good)
    _skins(doc, binary, rep, good)
    _names_refs(doc, rep)
    _images(doc, binary, rep)
    rep.stats.update(meshes=len(doc.get('meshes', [])), nodes=len(doc.get('nodes', [])), skins=len(doc.get('skins', [])),
                     vertex_color_encoding=doc.get('asset', {}).get('extras', {}).get('vertex_color_encoding'))
    if budget is not None and tris > budget:
        rep.error('budget.triangles', '', '%d triangles > budget %d' % (tris, budget))
    return rep


def validate_path(path, budget=None):
    return validate(Path(path).read_bytes(), str(path), budget)


# ------------------------------------------------------------------ library sweep + known-bad controls
def library(root):
    """Every GLB the bundle ships, with the manifest triangle limit where the build is listed."""
    root = Path(root)
    limits = {}
    man = root / 'kits' / 'manifest.json'
    if man.is_file():
        m = json.loads(man.read_text(encoding='utf-8'))
        for k in m.get('kits', []):
            for b in k.get('builds', []):
                limits[str((root / 'kits' / b['glb']).resolve())] = k.get('tri_limit')
    rows = []
    for p in sorted((root / 'kits').rglob('*.glb')):
        rows.append(validate_path(p, limits.get(str(p.resolve()))))
    return rows


def _rebuild(doc, binary):
    from .glb import encode
    return encode(doc, bytearray(binary))


def controls(good_glb):
    """Malformed variants of a good GLB; each must be rejected with the named check."""
    from .glb import read
    base = Path(good_glb).read_bytes()
    out = []

    def mutate(name, expect, fn):
        doc, b = read(base)
        doc = json.loads(json.dumps(doc))
        b = bytearray(b)
        data = fn(doc, b)
        if data is None:
            data = _rebuild(doc, b)
        rep = validate(data, 'control:' + name, budget=10 if name == 'over_budget' else None)
        codes = sorted({i['code'] for i in rep.issues if i['severity'] == 'error'})
        out.append({'control': name, 'expect': expect, 'flagged': expect in codes, 'codes': codes})

    def pos_accessor(doc):
        return doc['meshes'][0]['primitives'][0]['attributes']['POSITION']

    def bad_stride(doc, b):
        doc['bufferViews'][doc['accessors'][pos_accessor(doc)]['bufferView']]['byteStride'] = 6

    def overflow(doc, b):
        doc['accessors'][pos_accessor(doc)]['count'] += 1000

    def index_range(doc, b):
        p = doc['meshes'][0]['primitives'][0]
        a = doc['accessors'][p['indices']]
        v = doc['bufferViews'][a['bufferView']]
        fmt, size = COMPONENTS[a['componentType']]
        off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        struct.pack_into('<' + fmt, b, off, min(doc['accessors'][p['attributes']['POSITION']]['count'] + 7, 2 ** (8 * size) - 1))

    def wrong_bounds(doc, b):
        a = doc['accessors'][pos_accessor(doc)]
        a['max'] = [x + 5.0 for x in a['max']]

    def nan_position(doc, b):
        a = doc['accessors'][pos_accessor(doc)]
        v = doc['bufferViews'][a['bufferView']]
        struct.pack_into('<f', b, v.get('byteOffset', 0) + a.get('byteOffset', 0), float('nan'))

    def uv_range(doc, b):
        p = doc['meshes'][0]['primitives'][0]
        if 'TEXCOORD_0' not in p['attributes']:
            return None
        a = doc['accessors'][p['attributes']['TEXCOORD_0']]
        v = doc['bufferViews'][a['bufferView']]
        struct.pack_into('<f', b, v.get('byteOffset', 0) + a.get('byteOffset', 0), 5000.0)

    def unnamed(doc, b):
        doc['nodes'][0].pop('name', None)

    def truncated(doc, b):
        data = bytearray(_rebuild(doc, b))
        return bytes(data[:-16])

    def misaligned(doc, b):
        doc['accessors'][pos_accessor(doc)]['byteOffset'] = doc['accessors'][pos_accessor(doc)].get('byteOffset', 0) + 2

    def bad_weights(doc, b):
        # add a 2-joint skin whose weights do not sum to 1
        p = doc['meshes'][0]['primitives'][0]
        n = doc['accessors'][p['attributes']['POSITION']]['count']
        b.extend(b'\0' * (-len(b) % 4))
        jv = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': 4 * n})
        b.extend(bytes([0, 1, 0, 0]) * n)
        wv = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': 16 * n})
        b.extend(struct.pack('<4f', 0.6, 0.6, 0.0, 0.0) * n)
        ja = len(doc['accessors'])
        doc['accessors'].append({'bufferView': jv, 'componentType': 5121, 'count': n, 'type': 'VEC4'})
        doc['accessors'].append({'bufferView': wv, 'componentType': 5126, 'count': n, 'type': 'VEC4'})
        p['attributes'].update(JOINTS_0=ja, WEIGHTS_0=ja + 1)
        doc['nodes'].append({'name': 'ctl_joint_a'})
        doc['nodes'].append({'name': 'ctl_joint_b'})
        doc['skins'] = [{'joints': [len(doc['nodes']) - 2, len(doc['nodes']) - 1]}]
        doc['nodes'][0]['skin'] = 0

    for name, expect, fn in [('bad_byte_stride', 'view.stride', bad_stride), ('accessor_overflow', 'accessor.bounds', overflow),
                             ('index_out_of_range', 'indices.range', index_range), ('wrong_position_bounds', 'position.bounds', wrong_bounds),
                             ('nan_position', 'accessor.nan', nan_position), ('uv_out_of_range', 'uv.range', uv_range),
                             ('unnamed_node', 'names.missing', unnamed), ('truncated_bin', 'container.truncated', truncated),
                             ('misaligned_accessor', 'accessor.alignment', misaligned), ('bad_skin_weights', 'skin.weights', bad_weights),
                             ('over_budget', 'budget.triangles', lambda d, b: None)]:
        try:
            mutate(name, expect, fn)
        except (KeyError, IndexError, struct.error) as e:
            out.append({'control': name, 'expect': expect, 'flagged': False, 'codes': [], 'error': str(e)})
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='glb_validate')
    ap.add_argument('files', nargs='*')
    ap.add_argument('--budget', type=int)
    ap.add_argument('--library', action='store_true', help='validate every GLB under kits/ (manifest triangle limits)')
    ap.add_argument('--controls', action='store_true', help='also require every known-bad control to be rejected')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    reps = [validate_path(f, a.budget) for f in a.files]
    if a.library:
        reps += library(root)
    bad = [r for r in reps if not r.ok]
    ctl = []
    if a.controls:
        ctl = controls(root / 'kits' / 'library' / 'polar_pod' / 'assets' / 'nature.tree.glb')
    missed = [c for c in ctl if not c['flagged']]
    if a.json:
        print(json.dumps({'files': [r.as_dict() for r in reps], 'controls': ctl}, indent=2))
    else:
        for r in bad:
            for i in r.issues:
                if i['severity'] == 'error':
                    print('INVALID %s %s %s: %s' % (r.name, i['code'], i['path'], i['message']))
        for c in ctl:
            print('CONTROL %-22s %s (%s)' % (c['control'], 'rejected' if c['flagged'] else 'MISSED', ', '.join(c['codes']) or c.get('error', '')))
        print('GLB VALIDATION files=%d invalid=%d controls=%d missed=%d' % (len(reps), len(bad), len(ctl), len(missed)))
    return 0 if not bad and not missed else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
