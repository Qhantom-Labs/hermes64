"""Deterministic glTF 2 binary container. Standard library only, no engine process.

All buffer views start on four-byte boundaries. Accessor bounds describe stored
values (float32, not the caller's higher precision). No paths or clock in bytes.
"""
import json
import math
import struct

VERSION = 'hermes64-python/1'
FORMATS = {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def f32(x):
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


class Writer:
    def __init__(self):
        self.doc = {'asset': {'version': '2.0', 'generator': VERSION}, 'bufferViews': [], 'accessors': []}
        self.binary = bytearray()

    def view(self, data, target=None):
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        view = {'buffer': 0, 'byteOffset': len(self.binary), 'byteLength': len(data)}
        if target is not None:
            view['target'] = target
        self.doc['bufferViews'].append(view)
        self.binary.extend(data)
        return len(self.doc['bufferViews']) - 1

    def accessor(self, rows, typ, component, normalized=False, target=34962):
        width = WIDTHS[typ]
        rows = [tuple(row) for row in rows]
        if not rows or any(len(row) != width for row in rows):
            raise ValueError('empty or wrong-width accessor')
        if any(not math.isfinite(x) for row in rows for x in row):
            raise ValueError('accessor values must be finite')
        if component == 5126:
            rows = [tuple(f32(x) for x in row) for row in rows]
        raw = b''.join(struct.pack('<' + FORMATS[component] * width, *row) for row in rows)
        acc = {'bufferView': self.view(raw, target), 'componentType': component,
               'count': len(rows), 'type': typ,
               'min': [min(row[i] for row in rows) for i in range(width)],
               'max': [max(row[i] for row in rows) for i in range(width)]}
        if normalized:
            acc['normalized'] = True
        self.doc['accessors'].append(acc)
        return len(self.doc['accessors']) - 1

    def encode(self):
        doc = dict(self.doc, buffers=[{'byteLength': len(self.binary)}])
        j = json.dumps(doc, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        j += b' ' * (-len(j) % 4)
        b = bytes(self.binary) + b'\0' * (-len(self.binary) % 4)
        return (struct.pack('<4sII', b'glTF', 2, 28 + len(j) + len(b)) +
                struct.pack('<I4s', len(j), b'JSON') + j + struct.pack('<I4s', len(b), b'BIN\0') + b)
