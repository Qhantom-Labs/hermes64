"""GLB container + accessors for the rig kit (stdlib; numpy optional for array reads).

parse(data) -> (doc, binary); encode(doc, binary) -> bytes uses the Blender glTF exporter's byte conventions
(top-level key order, compact separators, ASCII JSON, integral floats written as ints, JSON padded with spaces,
BIN padded with zeros) so a document that came from Blender round-trips byte-identically.
"""
import json
import math
import struct
from collections import OrderedDict

JSON_T = 0x4E4F534A
BIN_T = 0x004E4942
COMP = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
NP_DTYPE = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
NORM_DEN = {5120: 127., 5121: 255., 5122: 32767., 5123: 65535.}
SORT_ORDER = ['asset', 'extensionsUsed', 'extensionsRequired', 'extensions', 'extras', 'scene', 'scenes', 'nodes',
              'cameras', 'animations', 'materials', 'meshes', 'textures', 'images', 'skins', 'accessors',
              'bufferViews', 'samplers', 'buffers']


class GLBError(ValueError):
    pass


def parse(data):
    data = bytes(data)
    if len(data) < 20:
        raise GLBError('file shorter than a GLB header')
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or version != 2 or length != len(data):
        raise GLBError('invalid GLB header')
    n, typ = struct.unpack_from('<II', data, 12)
    if typ != JSON_T:
        raise GLBError('first chunk is not JSON')
    doc = json.loads(data[20:20 + n].decode('utf-8'))
    off = 20 + n
    binary = b''
    if off < len(data):
        n2, typ2 = struct.unpack_from('<II', data, off)
        if typ2 != BIN_T:
            raise GLBError('second chunk is not BIN')
        binary = data[off + 8:off + 8 + n2]
    return doc, binary


def _fix(obj):
    """Blender exporter __fix_json: integral floats become ints (recursively, extras included verbatim)."""
    if isinstance(obj, dict):
        return {k: (v if k == 'extras' else _fix(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix(v) for v in obj]
    if isinstance(obj, float) and math.isfinite(obj) and int(obj) == obj:
        return int(obj)
    return obj


def dumps(doc, fix=False):
    d = _fix(doc) if fix else doc
    ordered = OrderedDict(sorted(d.items(), key=lambda kv: SORT_ORDER.index(kv[0]) if kv[0] in SORT_ORDER else 99))
    return json.dumps(ordered, indent=None, separators=(',', ':'), allow_nan=False)


def encode(doc, binary, fix=False):
    js = dumps(doc, fix).encode()
    js += b' ' * ((4 - (len(js) & 3)) & 3)
    b = bytes(binary)
    b += b'\0' * ((4 - (len(b) & 3)) & 3)
    total = 12 + 8 + len(js) + (8 + len(b) if b else 0)
    out = [struct.pack('<4sII', b'glTF', 2, total), struct.pack('<II', len(js), JSON_T), js]
    if b:
        out += [struct.pack('<II', len(b), BIN_T), b]
    return b''.join(out)


def accessor_bytes(doc, binary, ai):
    a = doc['accessors'][ai]
    bv = doc['bufferViews'][a['bufferView']]
    fmt, size = COMP[a['componentType']]
    elem = size * NCOMP[a['type']]
    stride = bv.get('byteStride', elem)
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    if stride == elem:
        return bytes(binary[start:start + elem * a['count']])
    return b''.join(bytes(binary[start + i * stride:start + i * stride + elem]) for i in range(a['count']))


def read_accessor(doc, binary, ai, normalize=True):
    """numpy array (count, ncomp) (float64 for normalized ints when normalize=True, native dtype otherwise)."""
    import numpy as np
    a = doc['accessors'][ai]
    raw = accessor_bytes(doc, binary, ai)
    arr = np.frombuffer(raw, dtype=NP_DTYPE[a['componentType']]).reshape(a['count'], NCOMP[a['type']])
    if a.get('normalized') and normalize and a['componentType'] in NORM_DEN:
        arr = np.maximum(arr.astype(np.float64) / NORM_DEN[a['componentType']], -1.)
    return arr


def read_accessor_py(doc, binary, ai):
    """stdlib fallback: list of tuples."""
    a = doc['accessors'][ai]
    fmt, size = COMP[a['componentType']]
    n = NCOMP[a['type']]
    raw = accessor_bytes(doc, binary, ai)
    st = struct.Struct('<' + fmt * n)
    rows = [st.unpack_from(raw, i * st.size) for i in range(a['count'])]
    if a.get('normalized') and a['componentType'] in NORM_DEN:
        den = NORM_DEN[a['componentType']]
        rows = [tuple(max(-1., x / den) for x in r) for r in rows]
    return rows


def node_parents(doc):
    return {c: i for i, n in enumerate(doc.get('nodes', [])) for c in n.get('children', [])}


def node_by_name(doc):
    out = {}
    for i, n in enumerate(doc.get('nodes', [])):
        out.setdefault(n.get('name'), i)
    return out
