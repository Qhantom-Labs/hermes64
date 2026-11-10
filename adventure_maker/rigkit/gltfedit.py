"""Deterministic in-place GLB editing for the rig kit: drop nodes, garbage-collect accessors/bufferViews, append
accessors. Used by attach_clips (any builder's GLB) and by the kit builder (clip packs, mannequins)."""
import copy

import numpy as np

from . import gltf

ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963


class EditError(ValueError):
    pass


def _check_single_buffer(doc):
    bufs = doc.get('buffers', [])
    if len(bufs) > 1 or any('uri' in b for b in bufs):
        raise EditError('only self-contained GLBs with one binary buffer are supported')


def referenced_accessors(doc):
    used = set()
    for m in doc.get('meshes', []):
        for p in m.get('primitives', []):
            used.update(p.get('attributes', {}).values())
            if 'indices' in p:
                used.add(p['indices'])
            for t in p.get('targets', []):
                used.update(t.values())
    for s in doc.get('skins', []):
        if 'inverseBindMatrices' in s:
            used.add(s['inverseBindMatrices'])
    for an in doc.get('animations', []):
        for smp in an.get('samplers', []):
            used.add(smp['input'])
            used.add(smp['output'])
    return used


def compact(doc, binary):
    """-> (doc, binary) without unreferenced accessors / bufferViews; kept views are re-packed in their original
    order with 4-byte alignment (deterministic)."""
    _check_single_buffer(doc)
    doc = copy.deepcopy(doc)
    acc = doc.get('accessors', [])
    keep_acc = sorted(referenced_accessors(doc))
    amap = {old: new for new, old in enumerate(keep_acc)}
    views = set()
    for i in keep_acc:
        a = acc[i]
        if 'bufferView' in a:
            views.add(a['bufferView'])
        sp = a.get('sparse')
        if sp:
            views.add(sp['indices']['bufferView'])
            views.add(sp['values']['bufferView'])
    for im in doc.get('images', []):
        if 'bufferView' in im:
            views.add(im['bufferView'])
    keep_views = sorted(views)
    vmap = {old: new for new, old in enumerate(keep_views)}
    out = bytearray()
    new_views = []
    for old in keep_views:
        bv = dict(doc['bufferViews'][old])
        start = bv.get('byteOffset', 0)
        raw = bytes(binary[start:start + bv['byteLength']])
        out += b'\0' * ((4 - len(out) % 4) % 4)
        bv['byteOffset'] = len(out)
        bv['buffer'] = 0
        out += raw
        new_views.append(bv)
    new_acc = []
    for i in keep_acc:
        a = dict(acc[i])
        if 'bufferView' in a:
            a['bufferView'] = vmap[a['bufferView']]
        if a.get('sparse'):
            sp = copy.deepcopy(a['sparse'])
            sp['indices']['bufferView'] = vmap[sp['indices']['bufferView']]
            sp['values']['bufferView'] = vmap[sp['values']['bufferView']]
            a['sparse'] = sp
        new_acc.append(a)
    for m in doc.get('meshes', []):
        for p in m.get('primitives', []):
            p['attributes'] = {k: amap[v] for k, v in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = amap[p['indices']]
            if 'targets' in p:
                p['targets'] = [{k: amap[v] for k, v in t.items()} for t in p['targets']]
    for s in doc.get('skins', []):
        if 'inverseBindMatrices' in s:
            s['inverseBindMatrices'] = amap[s['inverseBindMatrices']]
    for an in doc.get('animations', []):
        for smp in an.get('samplers', []):
            smp['input'] = amap[smp['input']]
            smp['output'] = amap[smp['output']]
    for im in doc.get('images', []):
        if 'bufferView' in im:
            im['bufferView'] = vmap[im['bufferView']]
    for k, v in (('accessors', new_acc), ('bufferViews', new_views)):
        if v:
            doc[k] = v
        else:
            doc.pop(k, None)
    if out:
        doc['buffers'] = [{'byteLength': len(out)}]
    else:
        doc.pop('buffers', None)
    return doc, bytes(out)


def remove_nodes(doc, drop):
    """-> doc without the given node indices (children, skins, animation channels and scenes remapped)."""
    doc = copy.deepcopy(doc)
    drop = set(drop)
    nodes = doc.get('nodes', [])
    nmap, kept = {}, []
    for i, n in enumerate(nodes):
        if i not in drop:
            nmap[i] = len(kept)
            kept.append(n)
    for n in kept:
        if 'children' in n:
            ch = [nmap[c] for c in n['children'] if c in nmap]
            if ch:
                n['children'] = ch
            else:
                n.pop('children')
    doc['nodes'] = kept
    for s in doc.get('skins', []):
        if any(j in drop for j in s['joints']):
            raise EditError('cannot remove a skin joint')
        s['joints'] = [nmap[j] for j in s['joints']]
        if 'skeleton' in s:
            s['skeleton'] = nmap[s['skeleton']]
    for an in doc.get('animations', []):
        chans = []
        for ch in an['channels']:
            node = ch['target'].get('node')
            if node is None or node in nmap:
                if node is not None:
                    ch = dict(ch, target=dict(ch['target'], node=nmap[node]))
                chans.append(ch)
        used = sorted({ch['sampler'] for ch in chans})
        smap = {o: k for k, o in enumerate(used)}
        an['samplers'] = [an['samplers'][o] for o in used]
        an['channels'] = [dict(ch, sampler=smap[ch['sampler']]) for ch in chans]
    for sc in doc.get('scenes', []):
        sc['nodes'] = [nmap[i] for i in sc.get('nodes', []) if i in nmap]
    return doc


class Builder:
    """Append-only accessor writer over (doc, binary): one bufferView per accessor, 4-byte aligned."""

    def __init__(self, doc, binary=b''):
        _check_single_buffer(doc)
        self.doc = doc
        self.bin = bytearray(binary)
        self.doc.setdefault('accessors', [])
        self.doc.setdefault('bufferViews', [])

    def view(self, raw, target=None):
        self.bin += b'\0' * ((4 - len(self.bin) % 4) % 4)
        bv = {'buffer': 0, 'byteLength': len(raw), 'byteOffset': len(self.bin)}
        if target is not None:
            bv['target'] = target
        self.bin += raw
        self.doc['bufferViews'].append(bv)
        return len(self.doc['bufferViews']) - 1

    def accessor(self, arr, ctype, typ, target=None, minmax=False, normalized=None):
        arr = np.ascontiguousarray(arr, dtype=gltf.NP_DTYPE[ctype])
        n = gltf.NCOMP[typ]
        arr2 = arr.reshape(-1, n)
        a = {'bufferView': self.view(arr2.tobytes(), target), 'componentType': ctype, 'count': int(len(arr2)), 'type': typ}
        if normalized:
            a['normalized'] = True
        if minmax and len(arr2):
            a['max'] = [float(x) if ctype == 5126 else int(x) for x in arr2.max(axis=0)]
            a['min'] = [float(x) if ctype == 5126 else int(x) for x in arr2.min(axis=0)]
        self.doc['accessors'].append(a)
        return len(self.doc['accessors']) - 1

    def finish(self):
        for k in ('accessors', 'bufferViews'):
            if not self.doc.get(k):
                self.doc.pop(k, None)
        if self.bin:
            self.doc['buffers'] = [{'byteLength': len(self.bin)}]
        return gltf.encode(self.doc, bytes(self.bin), fix=True)
