"""Unrolled-wall meshing: a wall strip in (s, z) with shaped holes and floor notches is tessellated,
split along vertical lines (plan vertices) so every piece is planar on its wall panel, and mapped
onto a plan polyline in 3D. Used by room shells and corridors (theme-agnostic)."""
import bisect
import math

import numpy as np

from . import meshkit as K


def split_convex(poly, c):
    """Split a convex polygon [(s,z)] by the line s=c -> (left, right) (either may be None)."""
    left, right = [], []
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        da, db = a[0] - c, b[0] - c
        if da <= 1e-12:
            left.append(a)
        if da >= -1e-12:
            right.append(a)
        if (da < -1e-12 and db > 1e-12) or (da > 1e-12 and db < -1e-12):
            t = da / (da - db)
            p = (c, a[1] + t * (b[1] - a[1]))
            left.append(p)
            right.append(p)
    def clean(p):
        out = []
        for q in p:
            if not out or abs(q[0] - out[-1][0]) > 1e-9 or abs(q[1] - out[-1][1]) > 1e-9:
                out.append(q)
        if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
            out.pop()
        return out if len(out) >= 3 and abs(K.polygon_area2d(out)) > 1e-10 else None
    return clean(left), clean(right)


def _snap(loop, snap, eps=5e-4):
    out = []
    for s, z in loop:
        for c in snap:
            if abs(s - c) < eps:
                s = c
                break
        out.append((s, z))
    return out


def strip_polys(length, zb, zt, holes, notches, snap=()):
    """Tessellate the unrolled wall rectangle [0,length]x[zb,zt]. holes: list of closed (s,z) loops
    strictly inside; notches: list of (s_left, s_right, path) where path runs from (s_left, zb) up
    and around to (s_right, zb) (floor-level openings). Returns list of triangles [(s,z)x3]."""
    outer = [(0.0, zb)]
    for sl, sr, path in sorted(notches, key=lambda n: n[0]):
        outer.extend(path)
    outer.extend([(length, zb), (length, zt), (0.0, zt)])
    outer = _dedupe2(_snap(outer, snap))
    hl = [list(reversed(K.ccw(_dedupe2(_snap(list(h), snap))))) for h in holes]
    flat = [p for loop in [outer] + hl for p in loop]  # must match tessellate()'s loop order
    tris = K.tessellate(outer, hl)
    out = []
    for a, b, c in tris:
        t = [flat[a], flat[b], flat[c]]
        if abs(K.polygon_area2d(t)) > 1e-10:
            out.append(t if K.polygon_area2d(t) > 0 else [t[0], t[2], t[1]])
    return out


def _dedupe2(pts):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def weld_polys(polys, tol=3e-4):
    """Merge 2D points closer than tol across ALL polygons (one representative per cluster), then drop
    repeated / back-tracking vertices and polygons that collapse. Removes the near-T-junction slivers
    that splitting produces next to snapped vertices (they would weld into degenerate triangles at the
    validator's 1e-4 m weld)."""
    pts = [p for poly in polys for p in poly]
    cell = {}
    rep = {}
    reps = []
    for p in pts:
        key = (int(math.floor(p[0] / tol)), int(math.floor(p[1] / tol)))
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ri in cell.get((key[0] + dx, key[1] + dy), ()):
                    q = reps[ri]
                    if abs(q[0] - p[0]) <= tol and abs(q[1] - p[1]) <= tol:
                        best = ri
                        break
                if best is not None:
                    break
            if best is not None:
                break
        if best is None:
            best = len(reps)
            reps.append(p)
            cell.setdefault(key, []).append(best)
        rep[p] = best
    out = []
    for poly in polys:
        ids = []
        for p in poly:
            r = rep[p]
            if not ids or ids[-1] != r:
                ids.append(r)
        if len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        changed = True
        while changed and len(ids) >= 3:  # remove spikes a-b-a
            changed = False
            for i in range(len(ids)):
                if ids[i - 1] == ids[(i + 1) % len(ids)]:
                    del ids[i]
                    if len(ids) > 1 and ids[i % len(ids) - 1] == ids[i % len(ids)]:
                        del ids[i % len(ids)]
                    changed = True
                    break
        if len(ids) < 3:
            continue
        q = [reps[i] for i in ids]
        if abs(K.polygon_area2d(q)) <= tol * tol:
            continue
        out.append(q)
    return out


def tri_convex(poly, eps=1e-10):
    """Triangulate a convex polygon that may contain collinear (180 degree) vertices without producing
    zero-area triangles: clip only real corners and never leave a collinear remainder."""
    idx = list(range(len(poly)))

    def area(ids):
        return K.polygon_area2d([poly[i] for i in ids])
    sign = 1.0 if area(idx) >= 0 else -1.0
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 1000:
        guard += 1
        n = len(idx)
        done = False
        for k in range(n):
            a, b, c = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            if sign * area([a, b, c]) <= eps:
                continue  # collinear vertex: not an ear
            rest = idx[:k] + idx[k + 1:]
            if sign * area(rest) <= eps:
                continue
            if len(rest) == 3 and sign * area(rest) <= eps:
                continue
            tris.append((a, b, c))
            idx = rest
            done = True
            break
        if not done:
            break
    if len(idx) == 3 and sign * area(idx) > eps:
        tris.append(tuple(idx))
    return tris


def split_all(polys, cuts):
    out = polys
    for c in cuts:
        nxt = []
        for p in out:
            lo = min(q[0] for q in p)
            hi = max(q[0] for q in p)
            if lo < c - 1e-9 and hi > c + 1e-9:
                l, r = split_convex(p, c)
                if l:
                    nxt.append(l)
                if r:
                    nxt.append(r)
            else:
                nxt.append(p)
        out = nxt
    return out


class PlanPath:
    """Closed plan polyline (CCW from above) parametrised by arc length s from a seam offset."""

    def __init__(self, pts, seam=0.0):
        self.pts = [np.array(p, dtype=np.float64) for p in pts]
        n = len(self.pts)
        self.s = [0.0]
        for i in range(n):
            self.s.append(self.s[-1] + float(np.linalg.norm(self.pts[(i + 1) % n] - self.pts[i])))
        self.length = self.s[-1]
        self.seam = seam % self.length

    def local_cuts(self):
        """Plan vertex positions in seam-shifted coordinates (sorted, excluding 0 and length)."""
        cuts = sorted(((sk - self.seam) % self.length) for sk in self.s[:-1])
        return [c for c in cuts if 1e-9 < c < self.length - 1e-9]

    def point(self, s_local):
        s = s_local + self.seam
        while s >= self.length:
            s -= self.length
        while s < 0:
            s += self.length
        k = max(0, min(len(self.pts) - 1, bisect.bisect_right(self.s, s) - 1))
        a = self.pts[k]
        b = self.pts[(k + 1) % len(self.pts)]
        seg = self.s[k + 1] - self.s[k]
        t = 0.0 if seg < 1e-12 else (s - self.s[k]) / seg
        return a + (b - a) * t

    def normal_in(self, s_local):
        """Inward horizontal normal (plan is CCW so inward = left of the direction)."""
        s = (s_local + self.seam) % self.length
        k = max(0, min(len(self.pts) - 1, bisect.bisect_right(self.s, s) - 1))
        a = self.pts[k]
        b = self.pts[(k + 1) % len(self.pts)]
        d = b - a
        d = d / max(1e-12, np.linalg.norm(d))
        return np.array([-d[1], d[0]])


def map_polys(polys, path):
    """(s,z) polygons -> list of 3D point lists on the plan wall."""
    out = []
    for p in polys:
        q = []
        for s, z in p:
            xy = path.point(s)
            q.append((float(xy[0]), float(xy[1]), float(z)))
        out.append(q)
    return out


def offset_outline(pts, d):
    """Offset a convex CCW outline inward by distance d (miter, clamped)."""
    n = len(pts)
    P = [np.array(p, dtype=np.float64) for p in pts]
    out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        e1 = b - a
        e2 = c - b
        e1 /= max(1e-12, np.linalg.norm(e1))
        e2 /= max(1e-12, np.linalg.norm(e2))
        n1 = np.array([-e1[1], e1[0]])
        n2 = np.array([-e2[1], e2[0]])
        m = n1 + n2
        ln = np.linalg.norm(m)
        if ln < 1e-9:
            m = n1
            sc = d
        else:
            m /= ln
            cos_half = max(0.25, float(np.dot(m, n1)))
            sc = d / cos_half
        out.append(tuple(b + m * sc))
    return out
