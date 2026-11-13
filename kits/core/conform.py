"""STYLEENGINE: conform any mesh or texture to the house N64 rules as TRANSFORMS (the gates stay as they are).

  decimate_tris    quadric-error (Garland-Heckbert) HALF-EDGE collapse to a triangle budget. A collapse moves u onto
                   v and creates no new position, so every surviving corner keeps one of its original UV/colour values
                   exactly. Open rims, group (role) borders and attribute seams get x100 constraint planes and may only
                   slide along themselves; collapses that break the link condition, flip or degenerate a face are
                   skipped. Above 8x the target (and 20,000 triangles) a numpy vertex-clustering pass runs first.
  decimate_mesh    the same on a meshkit Mesh (polygons are triangulated; groups = (role, smooth flag)).
  decimate_nodes   a budget shared over an asset's nodes in proportion to their triangles (12 kept per node).
  conform_texture  any RGB image -> a palette-exact square texture: area downsample, nearest-pair palette
                   quantization with the pack's threshold map (mottle or Bayer), then the energy loop (soften passes,
                   then less dither) until the n64_look texture rule holds.
  soften_plan      for pack-role textures: the smallest extra soften / dither change that makes look.continuity's
                   texture-energy rules pass on exactly the textures an asset uses (the same measure, unchanged).
  (the gate-line hints live in adventure_maker/styleengine.py: hint_for, pure Python for the parent process)

numpy only; no file, network or process access. Deterministic for equal input.
"""
import heapq
import json
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONSTRAINT_WEIGHT = 100.0
FLIP_DOT_MIN = 0.2          # a free vertex may turn a face by up to ~78 degrees
SLIDE_DOT_MIN = 0.7         # a vertex sliding along a rim/border/seam by up to ~45 (folds otherwise accumulate)
MIN_NODE_TRIS = 12
CLUSTER_ABOVE = 20000


def _conv():
    with open(os.path.join(HERE, "n64_look.json"), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


# ----------------------------------------------------------------------------------------------- triangle meshes
def _plane_q(a, b, c, w=1.0):
    """10-coefficient quadric of the plane through a, b, c (area weighted unless w is given as 'unit')."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-18:
        return None
    area = 0.5 * ln
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    d = -(nx * a[0] + ny * a[1] + nz * a[2])
    k = w * area
    return [k * nx * nx, k * nx * ny, k * nx * nz, k * nx * d, k * ny * ny, k * ny * nz, k * ny * d,
            k * nz * nz, k * nz * d, k * d * d]


def _q_add(q, r):
    for i in range(10):
        q[i] += r[i]


def _q_eval(q, p):
    x, y, z = p
    return (q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + 2 * q[3] * x + q[4] * y * y + 2 * q[5] * y * z
            + 2 * q[6] * y + q[7] * z * z + 2 * q[8] * z + q[9])


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def weld(V, F, eps=1e-6):
    """Positions equal after rounding to eps share one vertex. Returns (V', F')."""
    V = np.asarray(V, dtype=np.float64)
    key = np.round(V / eps).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    return V[first], inv[np.asarray(F, dtype=np.int64)]


def _cluster(V, F, groups, attrs, target):
    """Uniform-grid vertex clustering (fast first pass for very large inputs)."""
    lo, hi = V.min(0), V.max(0)
    tri = V[F]
    area = float(np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum() / 2)
    cell = max(math.sqrt(max(area, 1e-12) / (2.0 * target)), 1e-6)
    for _ in range(24):
        key = np.floor((V - lo) / cell).astype(np.int64)
        _, rep, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = np.asarray(inv).reshape(-1)
        sums = np.zeros((len(rep), 3))
        np.add.at(sums, inv, V)
        cnt = np.bincount(inv, minlength=len(rep)).astype(np.float64)
        NV = sums / cnt[:, None]
        NF = inv[F]
        keep = (NF[:, 0] != NF[:, 1]) & (NF[:, 1] != NF[:, 2]) & (NF[:, 0] != NF[:, 2])
        if keep.sum() <= 4 * target or cell > float(np.linalg.norm(hi - lo)):
            break
        cell *= 1.3
    NF = NF[keep]
    g = [groups[i] for i in np.nonzero(keep)[0]]
    a = attrs[keep]
    # drop exact duplicate faces (same vertex set)
    seen, rows = set(), []
    for i, f in enumerate(NF.tolist()):
        k = tuple(sorted(f))
        if k not in seen:
            seen.add(k)
            rows.append(i)
    return NV, NF[rows], [g[i] for i in rows], a[rows]


def decimate_tris(V, F, target, groups=None, corner_attrs=None, weld_eps=1e-6, relax_groups=False):
    """Triangle mesh -> at most `target` triangles where a legal collapse exists.

    V (n,3) floats; F (m,3) ints; groups: m hashable labels (faces of different labels keep their border);
    corner_attrs: (m,3) ints naming each corner's attribute value (UV/colour); equal ids = continuous.
    Returns dict(V, F, groups, corner_attrs, stats). Already within budget: returned unchanged (identity)."""
    import time
    t0 = time.monotonic()
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64).reshape(-1, 3)
    m0 = len(F)
    groups = list(groups) if groups is not None else [0] * m0
    attrs = np.asarray(corner_attrs, dtype=np.int64).reshape(-1, 3) if corner_attrs is not None else np.zeros((m0, 3), np.int64)
    target = int(target)
    if m0 <= target:
        return {'V': V, 'F': F, 'groups': groups, 'corner_attrs': attrs,
                'stats': {'in_tris': m0, 'out_tris': m0, 'changed': False, 'seconds': 0.0, 'clustered': False}}
    V, F = weld(V, F, weld_eps)
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F, attrs = F[ok], attrs[ok]
    groups = [g for g, k in zip(groups, ok.tolist()) if k]
    clustered = False
    if len(F) > max(CLUSTER_ABOVE, 8 * target):
        V, F, groups, attrs = _cluster(V, F, groups, attrs, target)
        clustered = True
    P = [tuple(p) for p in V.tolist()]
    faces = [list(f) for f in F.tolist()]
    fattr = [list(a) for a in attrs.tolist()]
    fgrp = list(groups)
    n = len(P)
    vf = [set() for _ in range(n)]
    for fi, f in enumerate(faces):
        for v in f:
            vf[v].add(fi)
    # edges -> faces
    ef = {}
    for fi, f in enumerate(faces):
        for j in range(3):
            a, b = f[j], f[(j + 1) % 3]
            ef.setdefault((a, b) if a < b else (b, a), []).append(fi)

    def attr_at(fi, v):
        return fattr[fi][faces[fi].index(v)]

    def edge_constrained(a, b, fl):
        if len(fl) != 2:
            return True
        f0, f1 = fl
        return (fgrp[f0] != fgrp[f1] and not relax_groups) or attr_at(f0, a) != attr_at(f1, a) or \
            attr_at(f0, b) != attr_at(f1, b)

    Q = [[0.0] * 10 for _ in range(n)]
    for f in faces:
        q = _plane_q(P[f[0]], P[f[1]], P[f[2]])
        if q:
            for v in f:
                _q_add(Q[v], q)
    for (a, b), fl in ef.items():
        if not edge_constrained(a, b, fl):
            continue
        f = faces[fl[0]]
        nf = _normal(P[f[0]], P[f[1]], P[f[2]])
        # constraint plane: contains the edge, perpendicular to the face
        e = (P[b][0] - P[a][0], P[b][1] - P[a][1], P[b][2] - P[a][2])
        pn = (e[1] * nf[2] - e[2] * nf[1], e[2] * nf[0] - e[0] * nf[2], e[0] * nf[1] - e[1] * nf[0])
        ln = math.sqrt(pn[0] ** 2 + pn[1] ** 2 + pn[2] ** 2)
        el2 = e[0] ** 2 + e[1] ** 2 + e[2] ** 2
        if ln < 1e-18 or el2 < 1e-24:
            continue
        pn = (pn[0] / ln, pn[1] / ln, pn[2] / ln)
        d = -(pn[0] * P[a][0] + pn[1] * P[a][1] + pn[2] * P[a][2])
        k = CONSTRAINT_WEIGHT * el2
        q = [k * pn[0] * pn[0], k * pn[0] * pn[1], k * pn[0] * pn[2], k * pn[0] * d, k * pn[1] * pn[1],
             k * pn[1] * pn[2], k * pn[1] * d, k * pn[2] * pn[2], k * pn[2] * d, k * d * d]
        _q_add(Q[a], q)
        _q_add(Q[b], q)
    alive_f = len(faces)
    dead = [False] * n
    ver = [0] * n
    heap = []

    def neighbours(v):
        s = set()
        for fi in vf[v]:
            s.update(faces[fi])
        s.discard(v)
        return s

    def push(u, v):
        q = [Q[u][i] + Q[v][i] for i in range(10)]
        heapq.heappush(heap, (_q_eval(q, P[v]), u, v, ver[u], ver[v]))

    for (a, b) in ef:
        push(a, b)
        push(b, a)

    def try_collapse(u, v):
        shared = vf[u] & vf[v]
        if not shared or len(shared) > 2:
            return None
        nu, nv = neighbours(u), neighbours(v)
        if len(nu & nv) != len(shared):
            return None                                   # link condition
        # constrained vertices only slide along a constrained edge they sit in the middle of
        cons = [w for w in nu if edge_constrained(u, w, sorted(vf[u] & vf[w]))]
        if cons and (len(cons) != 2 or v not in cons):
            return None
        # no back-to-back pair: a moved face may not land on a face v already has (a tetrahedron is the smallest solid)
        at_v = {frozenset(faces[fi]) for fi in vf[v] if fi not in shared}
        for fi in vf[u]:
            if fi not in shared and frozenset(v if x == u else x for x in faces[fi]) in at_v:
                return None
        # fan components around u (connected across edges with equal group and equal attr at u)
        fl = [fi for fi in vf[u]]
        parent = {fi: fi for fi in fl}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        by_w = {}
        for fi in fl:
            for w in faces[fi]:
                if w != u:
                    by_w.setdefault(w, []).append(fi)
        for w, l in by_w.items():
            if len(l) == 2:
                f0, f1 = l
                if fgrp[f0] == fgrp[f1] and attr_at(f0, u) == attr_at(f1, u):
                    parent[find(f0)] = find(f1)
        comp_attr = {}
        for g in shared:
            r = find(g)
            a = attr_at(g, v)
            if comp_attr.get(r, a) != a:
                return None
            comp_attr[r] = a
        new_attr = {}
        for fi in fl:
            if fi in shared:
                continue
            r = find(fi)
            if r not in comp_attr:
                return None
            new_attr[fi] = comp_attr[r]
            f = faces[fi]
            pts = [P[v] if x == u else P[x] for x in f]
            n0 = _normal(P[f[0]], P[f[1]], P[f[2]])
            n1 = _normal(*pts)
            l0 = math.sqrt(n0[0] ** 2 + n0[1] ** 2 + n0[2] ** 2)
            l1 = math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
            if l1 < 1e-14 * max(1.0, l0) or l0 < 1e-18:
                return None
            if (n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2]) / (l0 * l1) < (SLIDE_DOT_MIN if cons else FLIP_DOT_MIN):
                return None
        return shared, new_attr

    while alive_f > target and heap:
        cost, u, v, vu, vv = heapq.heappop(heap)
        if dead[u] or dead[v] or vu != ver[u] or vv != ver[v]:
            continue
        got = try_collapse(u, v)
        if got is None:
            continue
        shared, new_attr = got
        for fi in shared:
            for x in faces[fi]:
                vf[x].discard(fi)
            faces[fi] = None
            alive_f -= 1
        for fi in list(vf[u]):
            f = faces[fi]
            k = f.index(u)
            f[k] = v
            fattr[fi][k] = new_attr[fi]
            vf[v].add(fi)
        vf[u] = set()
        dead[u] = True
        _q_add(Q[v], Q[u])
        ver[v] += 1
        nb = neighbours(v)
        for w in nb:
            ver[w] += 1
        for w in nb:
            push(v, w)
            push(w, v)
            for x in neighbours(w):
                if x != v and not dead[x]:
                    push(w, x)
                    push(x, w)
    keep = [fi for fi, f in enumerate(faces) if f is not None]
    used = sorted({x for fi in keep for x in faces[fi]})
    remap = {old: i for i, old in enumerate(used)}
    NV = np.array([P[i] for i in used], dtype=np.float64).reshape(-1, 3)
    NF = np.array([[remap[x] for x in faces[fi]] for fi in keep], dtype=np.int64).reshape(-1, 3)
    return {'V': NV, 'F': NF, 'groups': [fgrp[fi] for fi in keep],
            'corner_attrs': np.array([fattr[fi] for fi in keep], dtype=np.int64).reshape(-1, 3),
            'stats': {'in_tris': m0, 'out_tris': len(keep), 'changed': True, 'clustered': clustered,
                      'seconds': round(time.monotonic() - t0, 3), 'reached': len(keep) <= target,
                      'relaxed_groups': bool(relax_groups)}}


def surface_error(Va, Fa, Vb, samples=2000, seed=0):
    """One-sided distance from points sampled on mesh A to the nearest VERTEX/face-centre cloud of mesh B (metres):
    a cheap silhouette-drift measure for tests and reports (an upper bound of the true surface distance)."""
    Va, Fa, Vb = np.asarray(Va, float), np.asarray(Fa, int), np.asarray(Vb, float)
    rs = np.random.default_rng(seed)
    tri = Va[Fa]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    pick = rs.choice(len(Fa), size=samples, p=area / area.sum())
    r1, r2 = rs.random(samples), rs.random(samples)
    s = np.sqrt(r1)
    pts = (1 - s)[:, None] * tri[pick, 0] + (s * (1 - r2))[:, None] * tri[pick, 1] + (s * r2)[:, None] * tri[pick, 2]
    cloud = Vb
    d = np.sqrt(((pts[:, None, :] - cloud[None, :, :]) ** 2).sum(-1)).min(1)
    return float(d.max()), float(d.mean())


# ------------------------------------------------------------------------------------------------ meshkit meshes
def triangulate_mesh(mesh, keep_metric_uv=False):
    """meshkit Mesh -> (V, F, groups (role, smooth), corner uv keys, uv table). Metric ('m') UVs are dropped unless
    asked: the Python builder re-derives a box projection in metres for faces without UVs, and per-face metric frames
    would turn every edge into a seam. Normalised ('n') UVs (alpha cards, signs) are kept as seams."""
    from .triangulate import polygon3d
    V = np.asarray(mesh.v, dtype=np.float64).reshape(-1, 3)
    F, groups, attrs, table = [], [], [], {None: 0}
    uvs = getattr(mesh, 'uv', None) or [None] * len(mesh.f)
    for fi, face in enumerate(mesh.f):
        u = uvs[fi]
        if u is not None and u[0] == 'm' and not keep_metric_uv:
            u = None
        tris = [(0, 1, 2)] if len(face) == 3 else polygon3d([mesh.v[v] for v in face])
        for t in tris:
            F.append([face[t[0]], face[t[1]], face[t[2]]])
            groups.append((mesh.r[fi], bool(mesh.s[fi])))
            if u is None:
                attrs.append([0, 0, 0])
            else:
                row = []
                for c in t:
                    k = (u[0], tuple(round(float(x), 7) for x in u[1][c]))
                    row.append(table.setdefault(k, len(table)))
                attrs.append(row)
    return V, np.asarray(F, dtype=np.int64).reshape(-1, 3), groups, np.asarray(attrs, dtype=np.int64).reshape(-1, 3), table


def decimate_mesh(mesh, target):
    """meshkit Mesh -> (new Mesh of triangles, stats). Under budget: the same mesh object back (identity)."""
    from .meshkit import Mesh
    if mesh.tri_count() <= target:
        return mesh, {'in_tris': mesh.tri_count(), 'out_tris': mesh.tri_count(), 'changed': False}
    V, F, groups, attrs, table = triangulate_mesh(mesh)
    out = decimate_tris(V, F, target, groups, attrs)
    if not out['stats']['reached']:
        # material borders held the strict pass above the budget: a second pass lets border vertices move too (each
        # face keeps its own role; UV seams stay locked)
        first = out['stats']
        out = decimate_tris(out['V'], out['F'], target, out['groups'], out['corner_attrs'], relax_groups=True)
        out['stats'].update(in_tris=first['in_tris'], strict_pass_tris=first['out_tris'],
                            seconds=round(first['seconds'] + out['stats']['seconds'], 3))
    inv = {i: k for k, i in table.items()}
    # smoothing is undefined where a vertex's smooth face normals cancel (thin sheets after a collapse): shade those
    # faces flat, so every exported normal stays unit length
    NV, NF = out['V'], out['F']
    fn = np.cross(NV[NF[:, 1]] - NV[NF[:, 0]], NV[NF[:, 2]] - NV[NF[:, 0]])
    fl = np.linalg.norm(fn, axis=1)
    acc = np.zeros_like(NV)
    tot = np.zeros(len(NV))
    smooth = np.array([g[1] for g in out['groups']], dtype=bool)
    unit = fn / np.maximum(fl[:, None], 1e-30)
    for k in range(3):
        np.add.at(acc, NF[smooth, k], unit[smooth])
        np.add.at(tot, NF[smooth, k], 1.0)
    weak = np.linalg.norm(acc, axis=1) < 0.35 * np.maximum(tot, 1e-9)
    flat = smooth & weak[NF].any(1)
    out['groups'] = [(g[0], g[1] and not bool(x)) for g, x in zip(out['groups'], flat)]
    out['stats']['flat_shaded'] = int(flat.sum())
    m = Mesh()
    m.v = [tuple(p) for p in out['V'].tolist()]
    for f, g, a in zip(out['F'].tolist(), out['groups'], out['corner_attrs'].tolist()):
        m.f.append(tuple(f))
        m.r.append(g[0])
        m.s.append(g[1])
        keys = [inv[x] for x in a]
        m.uv.append(None if keys[0] is None else (keys[0][0], [k[1] for k in keys]))
    return m, out['stats']


def decimate_nodes(nodes, target):
    """Share `target` over nodes by their triangle counts (each node keeps up to MIN_NODE_TRIS); replaces node meshes
    in place. Returns stats: in/out triangles, per node, and whether the budget was reached."""
    counts = [n.mesh.tri_count() for n in nodes]
    total = sum(counts)
    stats = {'in_tris': total, 'target': int(target), 'nodes': []}
    if total <= target:
        stats.update(out_tris=total, changed=False, reached=True)
        return stats
    floor = [min(c, MIN_NODE_TRIS) for c in counts]
    spare = max(0, int(target) - sum(floor))
    extra = [c - fl for c, fl in zip(counts, floor)]
    share = sum(extra) or 1
    wants = [fl + int(spare * ex / share) for fl, ex in zip(floor, extra)]
    originals = [n.mesh for n in nodes]
    results = [None] * len(nodes)
    for _round in range(3):
        # a node that cannot reach its share (borders, smallest solids) leaves an overshoot: the nodes that did reach
        # theirs give it back pro rata, from their original meshes
        for i, (m0, want) in enumerate(zip(originals, wants)):
            if results[i] is None or results[i][0].tri_count() > want:
                results[i] = decimate_mesh(m0, want)
        got = [r[0].tri_count() for r in results]
        over = sum(got) - int(target)
        movable = [i for i, (g, w) in enumerate(zip(got, wants)) if g <= w and w > floor[i]]
        if over <= 0 or not movable:
            break
        room = sum(wants[i] - floor[i] for i in movable) or 1
        for i in movable:
            wants[i] = max(floor[i], wants[i] - int(math.ceil(over * (wants[i] - floor[i]) / room)))
            results[i] = None
    out = 0
    for n, c, want, (new, _st) in zip(nodes, counts, wants, results):
        n.mesh = new
        got = new.tri_count()
        out += got
        stats['nodes'].append({'node': n.name, 'in': c, 'target': want, 'out': got})
    stats.update(out_tris=out, changed=True, reached=out <= target)
    return stats


# ------------------------------------------------------------------------------------------------------ textures
def _area_resample(img, size):
    """(H, W, C) float -> (size, size, C) by exact area weights (box filter)."""
    def weights(n_in, n_out):
        W = np.zeros((n_out, n_in))
        scale = n_in / n_out
        for o in range(n_out):
            a, b = o * scale, (o + 1) * scale
            for i in range(int(math.floor(a)), min(n_in, int(math.ceil(b)))):
                W[o, i] = min(b, i + 1) - max(a, i)
        return W / W.sum(1, keepdims=True)
    h, w = img.shape[:2]
    Wy, Wx = weights(h, size), weights(w, size)
    return np.einsum('oh,hwc->owc', Wy, np.einsum('pw,hwc->hpc', Wx, img))


def _blur_clamped(img):
    """[1 2 1]^2/16 blur with clamped edges (images from outside do not tile)."""
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode='edge')
    h = (p[:, :-2] + 2 * p[:, 1:-1] + p[:, 2:]) / 4.0
    return (h[:-2] + 2 * h[1:-1] + h[2:]) / 4.0


def quantize_palette(img, pal_rgb8, dither=1.0, thresholds=None):
    """(H, W, 3) floats in 0..255 -> palette-exact uint8. Nearest-pair ordered dither: each texel picks between its
    nearest palette colour and the second nearest by its position along that pair, against the threshold map."""
    pal = np.asarray(pal_rgb8, dtype=np.float64)
    h, w = img.shape[:2]
    x = img.reshape(-1, 3)
    wts = np.array([3.0, 4.0, 2.0])
    d = (((x[:, None, :] - pal[None, :, :]) ** 2) * wts).sum(-1)
    order = np.argsort(d, axis=1, kind='stable')
    i1, i2 = order[:, 0], order[:, 1] if len(pal) > 1 else order[:, 0]
    p1, p2 = pal[i1], pal[i2]
    seg = p2 - p1
    t = np.clip(((x - p1) * seg * wts).sum(1) / np.maximum((seg * seg * wts).sum(1), 1e-9), 0.0, 1.0)
    if thresholds is None:
        from .palette import BAYER4
        yy, xx = np.mgrid[0:h, 0:w]
        thr = BAYER4[yy % 4, xx % 4].reshape(-1)
    else:
        thr = np.asarray(thresholds, dtype=np.float64).reshape(-1)
    amount = float(dither or 0.0)
    # the same rule as palette.quantize_field on a two-colour ramp: floor(t + 0.5 + (thr - 0.5) * amount)
    pick2 = (t + (thr - 0.5) * amount) >= 0.5
    idx = np.where(pick2, i2, i1)
    return pal[idx].astype(np.uint8).reshape(h, w, 3)


def conform_texture(rgb, pal_rgb8, size=64, dither=1.0, pattern='mottle', hf_max=None, seed=0, max_soften=4):
    """Any image -> (palette-exact (size, size, 3) uint8, record). The energy target defaults to the n64_look
    `gate.library.hf_energy_median_max` (a single texture is its own set median)."""
    from .look import hf_energy
    from .palette import mottle_thresholds
    conv = _conv()
    lib = conv.get('gate', {}).get('library', {})
    hf_max = float(lib.get('hf_energy_median_max', 0.05) if hf_max is None else hf_max)
    src = np.asarray(rgb, dtype=np.float64)[..., :3]
    base = _area_resample(src, int(size)) if src.shape[0] != size or src.shape[1] != size else src.copy()
    clump = int(conv.get('textures', {}).get('mottle_clump', 0))
    thr = mottle_thresholds(np.random.default_rng(seed), size, size, clump) if pattern == 'mottle' else None
    attempts, best = [], None
    plans = [(k, dither) for k in range(max_soften + 1)] + [(k, round(dither * 0.5, 3)) for k in range(max_soften + 1)] \
        + [(k, 0.0) for k in range(max_soften + 1)]
    for k, d in plans:
        f = base
        for _ in range(k):
            f = _blur_clamped(f)
        img = quantize_palette(f, pal_rgb8, d, thr)
        e = hf_energy(img)
        attempts.append({'soften': k, 'dither': d, 'hf_energy': round(e, 5)})
        if best is None or e < best[1]:
            best = (img, e, k, d)
        if e <= hf_max:
            best = (img, e, k, d)
            break
    img, e, k, d = best
    colours = int(len(np.unique(img.reshape(-1, 3), axis=0)))
    return img, {'size': int(size), 'soften': k, 'dither': d, 'hf_energy': round(e, 5), 'hf_max': hf_max,
                 'ok': e <= hf_max, 'colours': colours, 'attempts': attempts, 'pattern': pattern}


def soften_plan(paint, roles, gate, max_extra=4):
    """paint(role, extra_soften, dither_or_None) -> image; gate(images) -> look.continuity result.
    Returns {'soften': k, 'dither': d, 'before': ..., 'after': ..., 'tried': [...]} for the first plan whose
    texture-energy errors are gone, or None when no plan clears them (the gate's numbers stand)."""
    def energy_errors(res):
        return [e for e in res['errors'] if 'texture energy' in e or 'hf energy' in e or 'noisy texture' in e]
    before = gate({r: paint(r, 0, None) for r in roles})
    if not energy_errors(before):
        return None
    tried = []
    # least change first: more soften with the pack's dither, then partial dither, clean bands last
    plans = [(1, None), (2, None), (3, None), (4, None), (1, 0.75), (2, 0.75), (1, 0.5), (2, 0.5), (3, 0.5),
             (1, 0.25), (2, 0.25), (0, 0.0), (1, 0.0), (2, 0.0)]
    for k, d in plans:
        if k > max_extra:
            continue
        res = gate({r: paint(r, k, d) for r in roles})
        row = {'soften': k, 'dither': d, 'median_hf': res['set']['median_hf'], 'errors': energy_errors(res)}
        tried.append(row)
        if not row['errors']:
            return {'soften': k, 'dither': d, 'before': {'median_hf': before['set']['median_hf'],
                                                         'errors': energy_errors(before)},
                    'after': {'median_hf': res['set']['median_hf'], 'errors': res['errors']}, 'tried': tried}
    return {'soften': None, 'dither': None, 'before': {'median_hf': before['set']['median_hf'],
                                                       'errors': energy_errors(before)}, 'after': None, 'tried': tried}


def conformed_texture_spec(spec, extra_soften=0, dither=None, conv=None):
    """A pack material texture spec with k more soften passes and/or another dither amount (texgen keys). Readable
    (crisp) generators and env/scene cards are left alone."""
    conv = conv or _conv()
    tx = conv.get('textures', {})
    gen = spec.get('gen')
    if gen in ('env', 'scene') or gen in tx.get('crisp_gens', []):
        return spec
    out = dict(spec)
    if extra_soften:
        base = int(spec.get('soften', tx.get('soften_gens', {}).get(gen, tx.get('soften', 0))))
        out['soften'] = base + int(extra_soften)
    if dither is not None:
        out['dither'] = float(dither)
    return out
