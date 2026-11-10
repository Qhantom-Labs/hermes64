"""Connectivity check (round 21, STEER-8 §3): the joins between head, neck, collar and torso - and the limb roots,
wrists, ankles, thumbs, ears, and the animal neck/head/tail - stay closed on every character in every key pose of
every clip.

Every body part is a closed loft (rings + end caps). A join names one end ring of part A and the part(s) B it must
sit in (gap = metres outside B; 0 inside):
  'buried'   every seam point of A's end ring (ring vertices + edge midpoints) must lie inside the union of B's closed
             solids; gap = the largest distance of a seam point outside B. Where A's end cap must be hidden: the neck
             stump in the collar/torso, the masked collar roll in the hood, an animal's neck/tail roots.
  'sector'   two pieces that must meet all the way round the seam, however they nest (a high collar inside the
             torso top or a shawl over it; a mitt inside the cuff, the cuff over the mitt or the two crossing; a boot
             in a baggy trouser leg; an animal's neck/tail roots in the body). Around the seam axis (A's loft axis)
             12 angular sectors; in each, the gap is the smallest distance between the two pieces near the seam: A's
             seam band (end ring -> next ring, 5 steps, vertices + edge midpoints) to B's solid and, when B has a
             matching end, B's seam band to A's solid; 0 where they intersect. gap = the worst sector. A collar
             floating above the torso fails in every sector, one lifted off at the back fails in the back sectors;
             crossing or draped pieces pass.
  'anchored' limb-like roots: A's root may stick out of B (a sleeve's shoulder cap over the torso slope, a thumb on the
             mitt, an ear on the head, an animal leg or a tail that curls and tilts its root cap out of the rump) but
             must stay attached: gap = the smallest distance from any point of A's root band (end ring, next ring, the
             midpoints between them) to B.
A join fails when gap > TOL in any key pose. Pure stdlib: runs in the sweeps, the cast audit, the tests and the
export (Blender's Python).
"""
import math

TOL = .003                      # metres: 3 mm (about 1/6 of a pixel for a 1.8 m figure at the 320x240 room camera)

_FACE = [('neck', 'face', 0, ('collar', 'torso'), 'buried', None),
         ('collar', 'collar', 0, ('torso',), 'sector', ('torso', -1, ('collar',)))]


def _side(spec, s):
    nm, part, end, bs, mode, rev = spec
    f = lambda x: x.replace('%s', s)
    return (f(nm), f(part), end, tuple(f(b) for b in bs), mode,
            None if rev is None else (f(rev[0]), rev[1], tuple(f(b) for b in rev[2])))


_LIMB_SPECS = [('shoulder_%s', 'sleeve_%s', -1, ('torso', 'collar', 'yoke'), 'anchored', None),
               ('hip_%s', 'trouser_%s', -1, ('torso',), 'anchored', None),
               ('wrist_%s', 'mitt_%s', -1, ('sleeve_%s',), 'sector', ('sleeve_%s', 0, ('mitt_%s',))),
               ('thumb_%s', 'thumb_%s', 0, ('mitt_%s',), 'anchored', None),
               ('ankle_%s', 'trouser_%s', 0, ('boot_%s',), 'sector', ('boot_%s', -1, ('trouser_%s',)))]
_LIMBS = [_side(sp, s) for s in 'lr' for sp in _LIMB_SPECS]
_EARS = [('ear_%s' % s, 'ear_%s' % s, 0, ('face', 'hair'), 'anchored', None) for s in 'lr']
_MASKED = [('collar_roll', 'yoke', -1, ('hood',), 'buried', None),
           ('torso_top', 'torso', -1, ('yoke', 'hood'), 'buried', None)]
_QUAD = [('neck_body', 'neck', 0, ('body',), 'sector', None),
         ('neck_head', 'neck', -1, ('head',), 'sector', None),
         ('tail', 'tail', 0, ('body',), 'anchored', None)] + \
        [('leg_%s' % e, 'leg_%s' % e, -1, ('body',), 'anchored', None) for e in ('fl', 'fr', 'bl', 'br')] + \
        [('ear_%s' % s, 'ear_%s' % s, 0, ('head',), 'anchored', None) for s in 'lr']
# lane-combat-art enemies: every attached piece must stay on its host in every key of every clip
_DASHER = [('mane_root', 'mane', 0, ('body',), 'buried', None), ('mane_head', 'mane', -1, ('head',), 'buried', None),
           ('brow_plate', 'plate', 0, ('head',), 'anchored', None)] + \
          [('ear_%s' % s, 'ear_%s' % s, 0, ('head', 'plate'), 'anchored', None) for s in 'lr'] + \
          [('leg_%s' % e, 'leg_%s' % e, 0, ('body',), 'buried', None) for e in ('fl', 'fr', 'bl', 'br')] + \
          [('tail', 'tail', 0, ('body',), 'buried', None), ('stone_1', 'stone_1', 0, ('body',), 'buried', None),
           ('stone_2', 'stone_2', 0, ('stone_1',), 'anchored', None), ('stone_3', 'stone_3', 0, ('stone_2',), 'anchored', None)]
_WARDEN = [('mask', 'mask', 0, ('body',), 'buried', None), ('beak', 'beak', 0, ('mask', 'body'), 'buried', None)] + \
          [(b, b, 0, ('mask', 'body'), 'buried', None) for b in ('ruff_t', 'ruff_l1', 'ruff_r1', 'ruff_l2', 'ruff_r2',
                                                                  'ruff_l3', 'ruff_r3')] + \
          [('wing_%s' % s, 'wing_%s' % s, 0, ('body',), 'buried', None) for s in 'lr'] + \
          [('hip_%s' % s, 'leg_%s' % s, 0, ('body',), 'buried', None) for s in 'lr'] + \
          [('ankle_%s' % s, 'leg_%s' % s, -1, ('foot_%s' % s,), 'buried', None) for s in 'lr'] + \
          [(b, b, 0, ('body',), 'buried', None) for b in ('tail_l', 'tail_c', 'tail_r')]
JOINS = {'cairn_dasher_v1': _DASHER, 'reed_warden_v1': _WARDEN,
         'human16_face_v3': _FACE + _LIMBS + _EARS,
         'human16_visor_v1': _FACE + _LIMBS,
         'human16_visor_v2': _FACE + _LIMBS,
         'human16_hood_v2': _MASKED + _LIMBS,
         'quad16_v1': _QUAD}


def joins_for(m):
    js = JOINS.get(getattr(m, 'topology', None))
    if js is None:
        if m.kind == 'enemy':
            raise ValueError('no connectivity joins declared for enemy topology %r' % getattr(m, 'topology', None))
        js = _QUAD if m.kind != 'human' else _FACE + _LIMBS
    # only parts this mesh has; B lists keep the parts that exist
    out = []
    for nm, a, end, bs, mode, rev in js:
        bb = tuple(b for b in bs if b in m.parts)
        if rev is not None and (rev[0] not in m.parts or not any(b in m.parts for b in rev[2])):
            rev = None
        if a in m.parts and bb:
            out.append((nm, a, end, bb, mode, rev))
    return out


# ------------------------------------------------------------------ geometry helpers
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _closest_sq(p, a, b, c):
    """Squared distance from p to triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab = _sub(b, a); ac = _sub(c, a); ap = _sub(p, a)
    d1 = _dot(ab, ap); d2 = _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return _dot(ap, ap)
    bp = _sub(p, b); d3 = _dot(ab, bp); d4 = _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return _dot(bp, bp)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3); q = (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2]); e = _sub(p, q)
        return _dot(e, e)
    cp = _sub(p, c); d5 = _dot(ab, cp); d6 = _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return _dot(cp, cp)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6); q = (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2]); e = _sub(p, q)
        return _dot(e, e)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); bc = _sub(c, b)
        q = (b[0] + w * bc[0], b[1] + w * bc[1], b[2] + w * bc[2]); e = _sub(p, q)
        return _dot(e, e)
    den = 1. / (va + vb + vc); v = vb * den; w = vc * den
    q = (a[0] + ab[0] * v + ac[0] * w, a[1] + ab[1] * v + ac[1] * w, a[2] + ab[2] * v + ac[2] * w); e = _sub(p, q)
    return _dot(e, e)


_RAY = (0.5773503, 0.5773603, 0.5773403)      # fixed, slightly skewed so rays never run along loft edges


def _hits(o, a, b, c):
    e1 = _sub(b, a); e2 = _sub(c, a); h = _cross(_RAY, e2); det = _dot(e1, h)
    if -1e-14 < det < 1e-14:
        return False
    f = 1. / det; s = _sub(o, a); u = f * _dot(s, h)
    if u < 0. or u > 1.:
        return False
    q = _cross(s, e1); v = f * _dot(_RAY, q)
    if v < 0. or u + v > 1.:
        return False
    return f * _dot(e2, q) > 1e-12


class _Solid:
    """Closed part surface in one pose: triangles + bounding box."""

    def __init__(self, tris):
        self.tris = tris
        xs = [p[0] for t in tris for p in t]; ys = [p[1] for t in tris for p in t]; zs = [p[2] for t in tris for p in t]
        self.lo = (min(xs), min(ys), min(zs)); self.hi = (max(xs), max(ys), max(zs))

    def box_sq(self, p):
        d = 0.
        for k in range(3):
            if p[k] < self.lo[k]:
                d += (self.lo[k] - p[k]) ** 2
            elif p[k] > self.hi[k]:
                d += (p[k] - self.hi[k]) ** 2
        return d

    def inside(self, p):
        if self.box_sq(p) > 0.:
            return False
        n = 0
        for a, b, c in self.tris:
            if _hits(p, a, b, c):
                n += 1
        return n % 2 == 1

    def dist_sq(self, p, best=float('inf')):
        if self.box_sq(p) >= best:
            return best
        for a, b, c in self.tris:
            d = _closest_sq(p, a, b, c)
            if d < best:
                best = d
        return best


# ------------------------------------------------------------------ mesh structure (no generator changes needed)
def structure(m):
    """{part: (ring_size, ring_count, face indices)} from the loft layout: a loft's first face is (0, 1, n + 1)."""
    owner = {}
    for name, ids in m.parts.items():
        for i in ids:
            owner[i] = name
    faces = {}
    for fi, f in enumerate(m.faces):
        faces.setdefault(owner.get(f[0]), []).append(fi)
    out = {}
    for name, ids in m.parts.items():
        fl = faces.get(name, [])
        if not fl:
            continue
        start = ids[0]
        f0 = m.faces[fl[0]]
        n = f0[2] - start - 1
        if n < 3 or f0[0] != start or f0[1] != start + 1:
            out[name] = (None, None, fl)                 # not a loft (convex blade/spike pieces)
            continue
        out[name] = (n, len(ids) // n, fl)
    return out


def seam_points(m, V, part, end, st, band=False):
    """End ring vertices + edge midpoints; band=True adds the next ring inward and the midpoints between the two."""
    n, nr, _ = st[part]
    k = 0 if end == 0 else nr - 1
    ring = [V[i] for i in m.parts[part][k * n:(k + 1) * n]]
    pts = ring + [tuple((ring[j][q] + ring[(j + 1) % n][q]) * .5 for q in range(3)) for j in range(n)]
    if band and nr > 1:
        k2 = 1 if end == 0 else nr - 2
        ring2 = [V[i] for i in m.parts[part][k2 * n:(k2 + 1) * n]]
        pts += ring2 + [tuple((ring[j][q] + ring2[j][q]) * .5 for q in range(3)) for j in range(n)]
    return pts


def check(m, V=None, st=None, tol=TOL):
    """Gaps of every join in one pose (V: posed vertices; default rest). -> {join: gap_m}, fails, pass."""
    V = m.vertices if V is None else V
    st = st or structure(m)
    solids = {}

    def solid(name):
        if name not in solids:
            solids[name] = _Solid([tuple(V[i] for i in m.faces[fi]) for fi in st[name][2]])
        return solids[name]

    def dist(p, sb):
        if any(s.inside(p) for s in sb):
            return 0.
        best = float('inf')
        for s in sb:
            best = s.dist_sq(p, best)
        return math.sqrt(best)

    def buried(a, end, bs):
        sb = [solid(b) for b in bs if st.get(b) and st[b][0] is not None]
        if st.get(a, (None,))[0] is None or not sb:
            return None
        return max(dist(p, sb) for p in seam_points(m, V, a, end, st))
    def band(part, end, steps=5):
        n, nr, _ = st[part]
        k = 0 if end == 0 else nr - 1
        k2 = 1 if end == 0 else nr - 2
        r0 = [V[i] for i in m.parts[part][k * n:(k + 1) * n]]
        r1 = [V[i] for i in m.parts[part][k2 * n:(k2 + 1) * n]]
        pts = []
        for s_ in range(steps):
            f = s_ / float(steps - 1) if steps > 1 else 0.
            ring = [tuple(r0[j][q] + (r1[j][q] - r0[j][q]) * f for q in range(3)) for j in range(n)]
            # 4 samples per ring edge: on flat elliptical rings the vertices are uneven in polar angle, and every
            # 30-degree sector must hold samples of A
            pts += [tuple(ring[j][q] + (ring[(j + 1) % n][q] - ring[j][q]) * w for q in range(3))
                    for j in range(n) for w in (0., .25, .5, .75)]
        c0 = tuple(sum(p[q] for p in r0) / n for q in range(3)); c1 = tuple(sum(p[q] for p in r1) / n for q in range(3))
        # seam axis = the end ring's own plane normal (Newell), pointing away from the next ring; centroid-to-centroid
        # tilts when a costume tweak shifts the next ring (hood_down's back lift)
        nx = ny = nz = 0.
        for j in range(n):
            p0 = r0[j]; p1 = r0[(j + 1) % n]
            nx += (p0[1] - p1[1]) * (p0[2] + p1[2]); ny += (p0[2] - p1[2]) * (p0[0] + p1[0]); nz += (p0[0] - p1[0]) * (p0[1] + p1[1])
        ax = (nx, ny, nz)
        if _dot(ax, ax) < 1e-18:
            ax = _sub(c0, c1)
        if _dot(ax, _sub(c0, c1)) < 0:
            ax = (-ax[0], -ax[1], -ax[2])
        return pts, c0, ax

    def sector(a, end, bs, rev, K=12):
        sa = [solid(x) for x in bs if st.get(x) and st[x][0] is not None]
        if st.get(a, (None,))[0] is None or not sa:
            return None
        pa, c0, u = band(a, end)
        ln = math.sqrt(_dot(u, u)) or 1.; u = (u[0] / ln, u[1] / ln, u[2] / ln)
        ref = (1., 0., 0.) if abs(u[0]) < .9 else (0., 1., 0.)
        e1 = _cross(u, ref); l1 = math.sqrt(_dot(e1, e1)); e1 = (e1[0] / l1, e1[1] / l1, e1[2] / l1); e2 = _cross(u, e1)

        def sec(p):
            d = _sub(p, c0)
            return int(((math.atan2(_dot(d, e2), _dot(d, e1)) + math.pi) / (2 * math.pi)) * K) % K
        best = {}
        for p in pa:
            k = sec(p)
            if best.get(k, 1.) > 0.:
                best[k] = min(best.get(k, float('inf')), dist(p, sa))
        if rev is not None:          # B's seam band can only close sectors A occupies, never add new ones
            b, end_b, bs_b = rev
            sb = [solid(x) for x in bs_b if st.get(x) and st[x][0] is not None]
            if st.get(b, (None,))[0] is not None and sb:
                pb, _, _ = band(b, end_b)
                for q in pb:
                    k = sec(q)
                    if k in best and best[k] > 0.:
                        best[k] = min(best[k], dist(q, sb))
        return max(best.values()) if best else None

    gaps = {}
    for nm, a, end, bs, mode, rev in joins_for(m):
        if mode == 'anchored':
            sb = [solid(b) for b in bs if st.get(b) and st[b][0] is not None]
            if st.get(a, (None,))[0] is None or not sb:
                continue
            g = float('inf')
            for p in seam_points(m, V, a, end, st, band=True):
                g = min(g, dist(p, sb))
                if g == 0.:
                    break
        elif mode == 'sector':
            g = sector(a, end, bs, rev)
            if g is None:
                continue
        else:
            g = buried(a, end, bs)
            if g is None:
                continue
        gaps[nm] = g
    bad = {k: v for k, v in gaps.items() if v > tol}
    return {'pass': not bad, 'gaps': gaps, 'fails': sorted(bad, key=lambda k: -bad[k])}


def check_poses(m, stance=None, clips=None, frames=(0., .25, .5, .75), tol=TOL, include_rest=True):
    """Every key pose of every clip (stance baked in as in the export). -> pass, fails ['join@clip@t gap'],
    worst {join: [gap, pose]}, max_gap, max_at."""
    from . import pose as PO
    H = m.params.get('height', 1.)
    clips = clips or (PO.HCLIPS if m.kind == 'human' else PO.ACLIPS)
    st = structure(m)
    worst = {}
    fails = []
    poses = [('rest', None)] if include_rest else []
    metrics = PO.body_metrics(m)
    for clip in clips:
        for t in frames:
            poses.append(('%s@%.2f' % (clip, t), (clip, t)))
    for label, ct in poses:
        if ct is None:
            V = m.vertices
        else:
            local = PO.local_rotations(m.bones, H, m.kind, ct[0], ct[1], stance if m.kind == 'human' else None, metrics)
            V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
        r = check(m, V, st, tol)
        for j, g in r['gaps'].items():
            if j not in worst or g > worst[j][0]:
                worst[j] = [round(g, 5), label]
            if g > tol:
                fails.append('%s@%s %.4f' % (j, label, g))
    mx = max(worst.items(), key=lambda kv: kv[1][0]) if worst else (None, [0., None])
    return {'pass': not fails, 'fails': fails[:12], 'n_fails': len(fails), 'worst': worst,
            'max_gap': mx[1][0], 'max_at': '%s %s' % (mx[0], mx[1][1]), 'tol': tol}
