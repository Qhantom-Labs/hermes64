"""Connectivity (3 mm seams) on the numpy-LBS-skinned GLB data.

Two methods, chosen per file by prepare():
  generator  the file names a generator topology (rig node extras 'topology' + 'params_json' or 'enemy_id'): rebuild
             the generator mesh, map every generator vertex to its GLB vertex by rest position (+ weights), and apply
             the generator's own join table (core/connectivity.JOINS: buried / sector / anchored) to the GLB's
             skinned positions. Exactly the published gate semantics, on the 4-influence data the runtime plays.
  generic    any other builder: mesh pieces = connected components after welding by rest position; every piece
             that touches or interpenetrates another piece at rest (within tol) must stay within tol of it on every
             key ("anchored": the smallest distance from its rest contact set to the other piece). Pieces that are
             not connected to the body through rest contacts are reported as floating.
"""
import json
import math

import numpy as np

_RAY = np.array([0.5773503, 0.5773603, 0.5773403])


# ------------------------------------------------------------------ numpy geometry
def point_tri_dist2(P, A, B, C):
    """Squared distance of points P (N,3) to triangles (M,3,3 split as A,B,C each (M,3)) -> (N, M)."""
    P = P[:, None, :]
    ab = (B - A)[None]; ac = (C - A)[None]; ap = P - A[None]
    d1 = (ab * ap).sum(-1); d2 = (ac * ap).sum(-1)
    bp = P - B[None]; d3 = (ab * bp).sum(-1); d4 = (ac * bp).sum(-1)
    cp = P - C[None]; d5 = (ab * cp).sum(-1); d6 = (ac * cp).sum(-1)
    vc = d1 * d4 - d3 * d2; vb = d5 * d2 - d1 * d6; va = d3 * d6 - d5 * d4
    with np.errstate(divide='ignore', invalid='ignore'):
        den = va + vb + vc
        v = np.where(den != 0, vb / den, 0.); w = np.where(den != 0, vc / den, 0.)
        q = A[None] + ab * v[..., None] + ac * w[..., None]
        # edge / vertex regions
        t_ab = np.where((d1 - d3) != 0, d1 / (d1 - d3), 0.)
        q_ab = A[None] + ab * t_ab[..., None]
        t_ac = np.where((d2 - d6) != 0, d2 / (d2 - d6), 0.)
        q_ac = A[None] + ac * t_ac[..., None]
        den_bc = (d4 - d3) + (d5 - d6)
        t_bc = np.where(den_bc != 0, (d4 - d3) / den_bc, 0.)
        q_bc = B[None] + (C - B)[None] * t_bc[..., None]
    Aq = np.broadcast_to(A[None], q.shape); Bq = np.broadcast_to(B[None], q.shape); Cq = np.broadcast_to(C[None], q.shape)
    r_a = (d1 <= 0) & (d2 <= 0)
    r_b = (d3 >= 0) & (d4 <= d3)
    r_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    r_c = (d6 >= 0) & (d5 <= d6)
    r_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    r_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    out = q
    out = np.where(r_bc[..., None], q_bc, out)
    out = np.where(r_ac[..., None], q_ac, out)
    out = np.where(r_c[..., None], Cq, out)
    out = np.where(r_ab[..., None], q_ab, out)
    out = np.where(r_b[..., None], Bq, out)
    out = np.where(r_a[..., None], Aq, out)
    e = P - out
    return (e * e).sum(-1)


def inside(P, A, B, C):
    """Ray-parity inside test of points P against a closed triangle set -> bool (N,)."""
    e1 = B - A; e2 = C - A
    h = np.cross(_RAY, e2)                       # (M,3)
    det = (e1 * h).sum(-1)                       # (M,)
    ok = np.abs(det) > 1e-14
    f = np.where(ok, 1. / np.where(ok, det, 1.), 0.)
    s = P[:, None, :] - A[None]                  # (N,M,3)
    u = f[None] * (s * h[None]).sum(-1)
    q = np.cross(s, e1[None])
    v = f[None] * (q * _RAY).sum(-1)
    t = f[None] * (q * e2[None]).sum(-1)
    hit = ok[None] & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-12)
    return (hit.sum(1) % 2) == 1


# ------------------------------------------------------------------ welding / pieces
def _weld(body):
    """Global welded vertex ids for the skinned primitives (by exact rest position bits)."""
    keys = {}
    gid = []
    for r in body:
        pos32 = r['positions'].astype(np.float32)
        ids = np.empty(len(pos32), dtype=np.int64)
        for i, row in enumerate(pos32):
            k = row.tobytes()
            if k not in keys:
                keys[k] = len(keys)
            ids[i] = keys[k]
        gid.append(ids)
    return gid, len(keys)


def _components(tris, n):
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in tris:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    roots = np.array([find(i) for i in range(n)])
    return roots


# ------------------------------------------------------------------ generator method
def _generator_mesh(doc, rig):
    arm = None
    for n in doc.get('nodes', []):
        if n.get('name') == 'rig_' + rig.id:
            arm = n
    ex = (arm or {}).get('extras') or {}
    topo = ex.get('topology')
    if not topo:
        return None, 'no generator topology in rig node extras'
    try:
        from ..nbchars import gen
        G = gen.load()
        if ex.get('enemy_id'):
            return G.core('enemies').build(ex['enemy_id']), None
        params = json.loads(ex.get('params_json', '{}'))
        if topo == 'quad16_v1':
            return G.core('geometry').quadruped(params), None
        if topo.startswith('human16_face'):
            return G.core('people').person(params), None
        if topo.startswith('human16_hood'):
            return G.core('geometry').humanoid(params), None
        if topo.startswith('human16_visor'):
            try:
                return G.core('cameo').person(params), None
            except ImportError:
                return None, 'visor topology needs core/cameo.py (not vendored: restricted likeness code)'
        return None, 'unknown topology %s' % topo
    except Exception as e:     # noqa: BLE001
        return None, 'generator rebuild failed: %s' % e


def _map_generator(m, body):
    """generator vertex index -> (primitive index, row) of a GLB vertex with the same rest position and weights."""
    V = np.asarray(m.vertices, dtype=np.float64)
    Vg = np.stack([V[:, 0], V[:, 2], -V[:, 1]], axis=1).astype(np.float32)
    table = {}
    for pi, r in enumerate(body):
        pos32 = r['positions'].astype(np.float32)
        for i, row in enumerate(pos32):
            table.setdefault(row.tobytes(), []).append((pi, i))
    out = []
    for gi, row in enumerate(Vg):
        cands = table.get(row.tobytes())
        if not cands:
            return None
        out.append(cands[0])
    return out


def prepare(doc, binary, ctx, rig, tol):
    body = ctx['body']
    prim_index = [i for i, r in enumerate(ctx['prims']) if r['joints'] is not None]
    m, why = _generator_mesh(doc, rig)
    if m is not None:
        try:
            from ..nbchars import gen
            CN = gen.load().core('connectivity')
            joins = CN.joins_for(m)
            mp = _map_generator(m, body)
            if mp is not None and joins:
                st = CN.structure(m)
                return {'method': 'generator', 'CN': CN, 'm': m, 'st': st, 'map': mp, 'prim_index': prim_index,
                        'n_joins': len(joins), 'tol': tol}
            why = 'generator vertices could not be mapped to the GLB' if mp is None else 'no joins for topology'
        except Exception as e:     # noqa: BLE001
            why = 'generator join table unavailable: %s' % e
    # generic
    gid, n = _weld(body)
    tris = np.concatenate([g[r['indices'].reshape(-1, 3)] for g, r in zip(gid, body)])
    roots = _components(tris, n)
    used = np.zeros(n, dtype=bool)
    used[tris.ravel()] = True                    # unreferenced vertices are not geometry: they form no piece
    labels = {r: k for k, r in enumerate(sorted(set(roots[used].tolist())))}
    piece = np.array([labels[r] if u else -1 for r, u in zip(roots.tolist(), used.tolist())], dtype=np.int64)
    npieces = len(labels)
    rest = np.zeros((n, 3))
    for g, r in zip(gid, body):
        rest[g] = r['positions']
    # one representative (prim, row) per welded id
    rep_of = [None] * n
    for pi, (g, r) in enumerate(zip(gid, body)):
        for row, k in enumerate(g):
            if rep_of[k] is None:
                rep_of[k] = (pi, row)
    ptris = [tris[piece[tris[:, 0]] == p] for p in range(npieces)]
    closed = []
    for p in range(npieces):
        t = ptris[p]
        e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        e.sort(axis=1)
        _, cnt = np.unique(e, axis=0, return_counts=True)
        closed.append(bool(len(cnt)) and bool((cnt == 2).all()))
    verts = [np.nonzero(piece == p)[0] for p in range(npieces)]
    joins = []
    for a in range(npieces):
        for b in range(npieces):
            if a == b or len(ptris[b]) == 0:
                continue
            P = rest[verts[a]]
            T = rest[ptris[b]]
            d2 = point_tri_dist2(P, T[:, 0], T[:, 1], T[:, 2]).min(1)
            ins = inside(P, T[:, 0], T[:, 1], T[:, 2]) if closed[b] else np.zeros(len(P), bool)
            sel = (d2 <= tol * tol) | ins
            if sel.any():
                joins.append((a, b, verts[a][sel]))
    # A join is one piece inserted into / resting on another: of the two contact directions of a pair keep the one
    # with the larger contact set (the inserted root ring), so a stray vertex of the host that merely grazes the
    # inserted piece's surface at rest is not checked as if it were a seam.
    best = {}
    for a, b, S in joins:
        k = (min(a, b), max(a, b))
        if k not in best or len(S) > len(best[k][2]) or (len(S) == len(best[k][2]) and a > best[k][0]):
            best[k] = (a, b, S)
    joins = [best[k] for k in sorted(best)]
    err = None
    if npieces > 1:
        # the pieces must form ONE body through their rest contacts: union pieces along joins, the component with
        # the most vertices is the body, every other component floats
        comp = list(range(npieces))

        def root(x):
            while comp[x] != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x
        for a, b, _S in joins:
            comp[root(a)] = root(b)
        groups = {}
        for p in range(npieces):
            groups.setdefault(root(p), []).append(p)
        sizes = [len(v) for v in verts]
        body = max(groups.values(), key=lambda g: (sum(sizes[p] for p in g), -min(g)))
        floating = sorted(p for g in groups.values() if g is not body for p in g)
        if floating:
            err = '%d mesh piece(s) are not connected to the body at rest (floating): sizes %s' % (
                len(floating), [sizes[p] for p in floating])
    return {'method': 'generic', 'gid': gid, 'n': n, 'ptris': ptris, 'closed': closed, 'joins': joins, 'prim_index': prim_index,
            'n_joins': len(joins), 'tol': tol, 'error': err, 'why_generic': why}


def _posed_welded(sctx, posed_all):
    n = sctx['n']
    P = np.zeros((n, 3))
    for g, pi in zip(sctx['gid'], sctx['prim_index']):
        P[g] = posed_all[pi]
    return P


def gaps(sctx, posed_all):
    """-> (worst gap metres, join name) for one pose; posed_all aligned with lbs.primitives()."""
    if sctx['method'] == 'generator':
        CN = sctx['CN']; m = sctx['m']
        body = [posed_all[i] for i in sctx['prim_index']]
        V = []
        for pi, row in sctx['map']:
            x, y, z = body[pi][row]
            V.append((float(x), -float(z), float(y)))         # glTF -> generator (Blender Z-up)
        r = CN.check(m, V, sctx['st'], sctx['tol'])
        if not r['gaps']:
            return 0.0, None
        k = max(r['gaps'], key=lambda j: r['gaps'][j])
        return float(r['gaps'][k]), k
    P = _posed_welded(sctx, posed_all)
    worst = (0.0, None)
    for a, b, S in sctx['joins']:
        T = P[sctx['ptris'][b]]
        pts = P[S]
        if sctx['closed'][b] and inside(pts, T[:, 0], T[:, 1], T[:, 2]).any():
            continue
        g = math.sqrt(float(point_tri_dist2(pts, T[:, 0], T[:, 1], T[:, 2]).min()))
        if g > worst[0]:
            worst = (g, 'piece%d->piece%d' % (a, b))
    return worst
