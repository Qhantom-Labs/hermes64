"""Additive animation graft for GLB files (lane-combat-art). Pure stdlib (runs in Blender's Python and in python3).

graft(base, donor, clips, extras=None) -> bytes
  Appends the donor GLB's animations named in `clips` to the base GLB:
  * every byte of the base BIN chunk stays at its offset (mesh, skin, textures and the 7 shared clips untouched);
    the new keyframe data is appended after it, 4-byte aligned;
  * every base JSON object stays as it was; new accessors / bufferViews / animations are appended at the end of their
    arrays, so every existing index stays valid; buffers[0].byteLength grows;
  * channels are re-targeted by node NAME (donor node -> name -> base node), so the donor only has to share the rig.
verify(base, grafted, donor, clips) -> list of problems (empty = clean): byte-identical BIN prefix, identical original
  JSON objects, donor's copies of the base clips identical to the base clips (same pipeline), new clips present.
"""
import json
import struct

JSON_T = 0x4E4F534A
BIN_T = 0x004E4942
COMP = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def parse(data):
    magic, ver, length = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or ver != 2 or length != len(data):
        raise ValueError('invalid GLB header')
    n, typ = struct.unpack_from('<II', data, 12)
    if typ != JSON_T:
        raise ValueError('first chunk is not JSON')
    doc = json.loads(data[20:20 + n])
    off = 20 + n
    binc = b''
    if off < len(data):
        n2, typ2 = struct.unpack_from('<II', data, off)
        if typ2 != BIN_T:
            raise ValueError('second chunk is not BIN')
        binc = data[off + 8:off + 8 + n2]
    return doc, binc


def build(doc, binc):
    js = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    js += b' ' * ((4 - len(js) % 4) % 4)
    b = bytes(binc) + b'\0' * ((4 - len(binc) % 4) % 4)
    total = 12 + 8 + len(js) + (8 + len(b) if b else 0)
    out = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<II', len(js), JSON_T) + js
    if b:
        out += struct.pack('<II', len(b), BIN_T) + b
    return out


def accessor_bytes(doc, binc, ai):
    a = doc['accessors'][ai]
    bv = doc['bufferViews'][a['bufferView']]
    elem = COMP[a['componentType']] * NCOMP[a['type']]
    stride = bv.get('byteStride', elem)
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    if stride == elem:
        return bytes(binc[start:start + elem * a['count']])
    return b''.join(bytes(binc[start + i * stride:start + i * stride + elem]) for i in range(a['count']))


def _node_index(doc):
    idx = {}
    for i, n in enumerate(doc['nodes']):
        nm = n.get('name')
        if nm in idx:
            raise ValueError('duplicate node name %r' % nm)
        idx[nm] = i
    return idx


def graft(base, donor, clips, extras=None):
    bd, bb = parse(base)
    dd, db = parse(donor)
    names_b = _node_index(bd)
    have = {a['name'] for a in bd.get('animations', [])}
    bb = bytearray(bb)
    acc_map = {}
    for clip in clips:
        found = [a for a in dd.get('animations', []) if a['name'] == clip]
        if len(found) != 1:
            raise ValueError('donor has %d animations named %r' % (len(found), clip))
        if clip in have:
            raise ValueError('base already has animation %r' % clip)
        an = found[0]
        samplers = []
        for s in an['samplers']:
            ns = dict(s)
            for key in ('input', 'output'):
                ai = s[key]
                if ai not in acc_map:
                    raw = accessor_bytes(dd, db, ai)
                    bb += b'\0' * ((4 - len(bb) % 4) % 4)
                    bd['bufferViews'].append({'buffer': 0, 'byteLength': len(raw), 'byteOffset': len(bb)})
                    bb += raw
                    acc = {k: v for k, v in dd['accessors'][ai].items() if k not in ('bufferView', 'byteOffset')}
                    acc['bufferView'] = len(bd['bufferViews']) - 1
                    bd['accessors'].append(acc)
                    acc_map[ai] = len(bd['accessors']) - 1
                ns[key] = acc_map[ai]
            samplers.append(ns)
        channels = []
        for c in an['channels']:
            nm = dd['nodes'][c['target']['node']].get('name')
            if nm not in names_b:
                raise ValueError('donor channel targets node %r missing from base' % nm)
            channels.append({'sampler': c['sampler'], 'target': {'node': names_b[nm], 'path': c['target']['path']}})
        new = {'channels': channels, 'name': clip, 'samplers': samplers}
        if extras and clip in extras:
            new['extras'] = extras[clip]
        bd.setdefault('animations', []).append(new)
    bd['buffers'][0]['byteLength'] = len(bb)
    return build(bd, bytes(bb))


def _anim_signature(doc, binc, an):
    """{(node name, path): (interpolation, input bytes, output bytes)} - index-free description of one clip."""
    out = {}
    for c in an['channels']:
        s = an['samplers'][c['sampler']]
        key = (doc['nodes'][c['target']['node']].get('name'), c['target']['path'])
        out[key] = (s.get('interpolation', 'LINEAR'), accessor_bytes(doc, binc, s['input']),
                    accessor_bytes(doc, binc, s['output']))
    return out


def verify(base, grafted, donor, clips):
    problems = []
    bd, bb = parse(base)
    gd, gb = parse(grafted)
    dd, db = parse(donor)
    if gb[:len(bb)] != bb:
        problems.append('base BIN bytes changed')
    for k, v in bd.items():
        if k in ('buffers', 'animations', 'accessors', 'bufferViews'):
            continue
        if gd.get(k) != v:
            problems.append('JSON %s changed' % k)
    for k in ('accessors', 'bufferViews'):
        if gd[k][:len(bd[k])] != bd[k]:
            problems.append('existing %s changed' % k)
    if gd['animations'][:len(bd['animations'])] != bd['animations']:
        problems.append('existing animations changed')
    names = [a['name'] for a in gd['animations']]
    if names != [a['name'] for a in bd['animations']] + list(clips):
        problems.append('animation list %s' % names)
    # the donor's copies of the base clips must equal the base clips: the donor came from the same pipeline
    dmap = {a['name']: a for a in dd['animations']}
    for an in bd['animations']:
        if an['name'] not in dmap:
            problems.append('donor lacks base clip %s' % an['name'])
        elif _anim_signature(bd, bb, an) != _anim_signature(dd, db, dmap[an['name']]):
            problems.append('donor clip %s differs from base' % an['name'])
    # the grafted clips equal the donor's
    gmap = {a['name']: a for a in gd['animations']}
    for clip in clips:
        if clip in gmap and clip in dmap and _anim_signature(gd, gb, gmap[clip]) != _anim_signature(dd, db, dmap[clip]):
            problems.append('grafted clip %s differs from donor' % clip)
    return problems
