"""Conversions into the rig kit character form (lane CHARBIND). Python API for converters and builders; no tool.

rigid_pieces_to_props(glb, rig='human16_v1', tol_m=0.003) -> (bytes, report)
    Lossless. A group of skinned mesh pieces that the validator calls floating (not joined to the body through rest
    contacts within tol_m, seams.prepare generic method) and whose every vertex is weighted 1.0 to one joint moves
    exactly like that joint. It becomes an unskinned prop node on that joint, the rig kit prop form (budget.prop,
    n64_prop extras), with its vertices in the joint's rest frame (inverse bind matrix): every key of every clip shows
    it where skinning showed it. A floating group on more than one joint is left as it is and the validator keeps
    refusing it.
keep_clips(glb, clips) -> bytes     Lossy and explicit: only the named animations stay.
drop_props(glb, kinds) -> bytes     Lossy and explicit: prop nodes (unskinned meshes) whose n64_prop.kind is listed go.
Outputs are compacted (no unreferenced accessors or views) and byte-identical for the same input.
"""
import copy
from pathlib import Path

import numpy as np

from . import gltf, gltfedit, lbs, seams
from . import validate as V
from .rig import load_rig

RIGID_W = 1. - 1e-4
ARRAY, ELEMENTS = 34962, 34963


class ConformError(ValueError):
    pass


def _raw(glb):
    return bytes(glb) if isinstance(glb, (bytes, bytearray, memoryview)) else Path(glb).read_bytes()


def _encode(doc, binary):
    doc, binary = gltfedit.compact(doc, binary)
    return gltf.encode(doc, binary, fix=True)


def floating_groups(doc, binary, rig, tol_m=0.003):
    """-> (ctx, sc, [sorted welded ids of one floating group]) by the validator's own rule (seams.py)."""
    ctx = V._rig(V.Report(rig, ''), rig, doc, binary)
    if not ctx['body']:
        return ctx, None, []
    sc = seams.prepare(doc, binary, ctx, rig, tol_m)
    if sc['method'] != 'generic' or not sc.get('error'):
        return ctx, sc, []
    ptris = sc['ptris']
    sizes = [len(np.unique(t.ravel())) for t in ptris]
    comp = list(range(len(ptris)))

    def root(x):
        while comp[x] != x:
            comp[x] = comp[comp[x]]
            x = comp[x]
        return x
    for a, b, _s in sc['joins']:
        comp[root(a)] = root(b)
    groups = {}
    for p in range(len(ptris)):
        groups.setdefault(root(p), []).append(p)
    body = max(groups.values(), key=lambda g: (sum(sizes[p] for p in g), -min(g)))
    out = [np.unique(np.concatenate([ptris[p].ravel() for p in g])) for g in groups.values() if g is not body]
    return ctx, sc, sorted(out, key=lambda ids: int(ids[0]))


def rigid_pieces_to_props(glb, rig='human16_v1', tol_m=0.003):
    raw = _raw(glb)
    rig = load_rig(rig) if isinstance(rig, str) else rig
    doc, binary = gltf.parse(raw)
    ctx, sc, groups = floating_groups(doc, binary, rig, tol_m)
    report = {'moved': [], 'left': []}
    if not groups:
        return raw, report
    work = copy.deepcopy(doc)
    b = gltfedit.Builder(work, binary)
    ibm = lbs.inverse_binds(doc, binary)
    nodes = work['nodes']
    names = {n.get('name') for n in nodes}
    drop = {}                                  # (mesh, prim) -> bool mask of triangles that leave the body
    for ids in groups:
        parts, joints = [], set()
        for pi, (g, r) in enumerate(zip(sc['gid'], ctx['body'])):
            tri = r['indices'].reshape(-1, 3)
            inside = np.isin(g[tri[:, 0]], ids)
            if not inside.any():
                continue
            rows = np.unique(tri[inside].ravel())
            w, j = r['weights'][rows], r['joints'][rows]
            top = np.argmax(w, axis=1)
            if not (w[np.arange(len(rows)), top] >= RIGID_W).all():
                joints.add(-1)
            joints.update(int(x) for x in j[np.arange(len(rows)), top])
            parts.append((pi, r, tri, inside, rows))
        nverts = int(len(ids))
        if len(joints) != 1 or -1 in joints:
            report['left'].append({'vertices': nverts, 'joints': sorted(x for x in joints if x >= 0)})
            continue
        k = joints.pop()
        skin = work['skins'][parts[0][1]['skin']]
        jnode = skin['joints'][k]
        jname = nodes[jnode].get('name', 'joint%d' % k)
        M = np.asarray(ibm[k], dtype=np.float64)
        prims, ntris = [], 0
        for pi, r, tri, inside, rows in parts:
            src = work['meshes'][r['mesh']]['primitives'][r['prim']]
            attrs = {}
            for name, ai in sorted(src['attributes'].items()):
                if name.startswith(('JOINTS_', 'WEIGHTS_')):
                    continue
                acc = doc['accessors'][ai]
                vals = gltf.read_accessor(doc, binary, ai, normalize=False)[rows]
                if name == 'POSITION':
                    p = vals.astype(np.float64)
                    vals = (p @ M[:3, :3].T + M[:3, 3]).astype(np.float32)
                elif name in ('NORMAL', 'TANGENT'):
                    v = vals.astype(np.float64)
                    xyz = v[:, :3] @ M[:3, :3].T
                    xyz /= np.maximum(np.linalg.norm(xyz, axis=1, keepdims=True), 1e-12)
                    v[:, :3] = xyz
                    vals = v.astype(np.float32)
                attrs[name] = b.accessor(vals, acc['componentType'], acc['type'], target=ARRAY,
                                         minmax=(name == 'POSITION'), normalized=acc.get('normalized'))
            local = np.searchsorted(rows, tri[inside]).reshape(-1)
            prim = {'attributes': attrs, 'indices': b.accessor(local, 5123 if len(rows) < 65536 else 5125, 'SCALAR',
                                                               target=ELEMENTS)}
            for key in ('material', 'mode'):
                if key in src:
                    prim[key] = src[key]
            prims.append(prim)
            ntris += int(inside.sum())
            key = (r['mesh'], r['prim'])
            drop[key] = drop.get(key, np.zeros(len(tri), dtype=bool)) | inside
        base = 'kit_acc_%s_piece' % jname
        n = 0
        while '%s%d' % (base, n) in names:
            n += 1
        name = '%s%d' % (base, n)
        names.add(name)
        source = work['meshes'][parts[0][1]['mesh']].get('name', 'mesh%d' % parts[0][1]['mesh'])
        work['meshes'].append({'name': name + '_mesh', 'primitives': prims})
        nodes.append({'name': name, 'mesh': len(work['meshes']) - 1,
                      'extras': {'n64_prop': {'kind': 'rigid_piece', 'slot': jname, 'tris': ntris, 'removable': False},
                                 'hermes64_conform': {'rule': 'rigid floating piece', 'from_mesh': source,
                                                      'vertices': nverts}}})
        nodes[jnode]['children'] = list(nodes[jnode].get('children', [])) + [len(nodes) - 1]
        report['moved'].append({'node': name, 'joint': jname, 'vertices': nverts, 'tris': ntris, 'from_mesh': source})
    for (mi, pi), mask in sorted(drop.items()):
        src = work['meshes'][mi]['primitives'][pi]
        acc = doc['accessors'][src['indices']]
        tri = gltf.read_accessor(doc, binary, src['indices'], normalize=False).reshape(-1, 3)
        keep = tri[~mask].reshape(-1)
        if not len(keep):
            raise ConformError('mesh %d primitive %d would keep no triangle' % (mi, pi))
        src['indices'] = b.accessor(keep, acc['componentType'], 'SCALAR', target=ELEMENTS)
    if not report['moved']:
        return raw, report
    out = b.finish()
    d2, b2 = gltf.parse(out)
    return _encode(d2, b2), report


def keep_clips(glb, clips):
    doc, binary = gltf.parse(_raw(glb))
    have = [a.get('name') for a in doc.get('animations', [])]
    missing = [c for c in clips if c not in have]
    if missing or not clips:
        raise ConformError('no clip named %s in this file (it has %s)' % (', '.join(missing) or '(none given)', have))
    doc = copy.deepcopy(doc)
    doc['animations'] = [a for a in doc['animations'] if a.get('name') in set(clips)]
    return _encode(doc, binary)


def drop_props(glb, kinds):
    doc, binary = gltf.parse(_raw(glb))
    drop = [i for i, n in enumerate(doc.get('nodes', [])) if 'mesh' in n and 'skin' not in n
            and ((n.get('extras') or {}).get('n64_prop') or {}).get('kind') in set(kinds)]
    if not drop:
        raise ConformError('no prop of kind %s in this file' % ', '.join(kinds))
    doc = gltfedit.remove_nodes(doc, drop)
    used = sorted({n['mesh'] for n in doc['nodes'] if 'mesh' in n})
    mmap = {old: new for new, old in enumerate(used)}
    doc['meshes'] = [doc['meshes'][i] for i in used]
    for n in doc['nodes']:
        if 'mesh' in n:
            n['mesh'] = mmap[n['mesh']]
    return _encode(doc, binary)
