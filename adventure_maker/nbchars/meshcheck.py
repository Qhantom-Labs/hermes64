"""Mechanical mesh checks shared by the character gates (numpy only).

  crossings(V, tris_a, tris_b)   number of triangle pairs (one of A, one of B) whose surfaces cross: an edge of one
                                 passes through the face of the other. Touching at a shared vertex does not count.
  inside(V, tris, points)        which points lie inside the closed-ish surface `tris` (generalised winding number, so
                                 open sleeves and lofts with missing caps do not fool it)
"""
import numpy as np

EPS = 1e-9


def _seg_tri(P, Q, T):
    """Segments P->Q (n, 3) against triangles T (m, 3, 3). -> bool (n, m): the open segment crosses the triangle
    strictly inside (Moller-Trumbore)."""
    d = (Q - P)[:, None, :]                                    # n 1 3
    e1 = (T[:, 1] - T[:, 0])[None]; e2 = (T[:, 2] - T[:, 0])[None]
    h = np.cross(d, e2)
    a = (e1 * h).sum(-1)
    ok = np.abs(a) > EPS
    f = np.where(ok, 1. / np.where(ok, a, 1.), 0.)
    s = P[:, None, :] - T[None, :, 0]
    u = f * (s * h).sum(-1)
    q = np.cross(s, e1)
    v = f * (d * q).sum(-1)
    t = f * (e2 * q).sum(-1)
    m = 1e-6
    return ok & (u > m) & (v > m) & (u + v < 1. - m) & (t > m) & (t < 1. - m)


def crossings(V, tris_a, tris_b):
    V = np.asarray(V, dtype=np.float64)
    A = V[np.asarray(tris_a, dtype=np.int64)]; B = V[np.asarray(tris_b, dtype=np.int64)]
    if not len(A) or not len(B):
        return 0
    hit = np.zeros((len(A), len(B)), dtype=bool)
    for i in range(3):
        hit |= _seg_tri(A[:, i], A[:, (i + 1) % 3], B)
        hit |= _seg_tri(B[:, i], B[:, (i + 1) % 3], A).T
    return int(hit.sum())


def winding(V, tris, points):
    """Generalised winding number of `points` (n, 3) with respect to the triangles (van Oosterom-Strackee solid
    angles). About 1 inside a closed surface, about 0 outside, in between near an open boundary."""
    V = np.asarray(V, dtype=np.float64); P = np.asarray(points, dtype=np.float64)
    T = V[np.asarray(tris, dtype=np.int64)]
    a = T[None, :, 0] - P[:, None]; b = T[None, :, 1] - P[:, None]; c = T[None, :, 2] - P[:, None]
    la = np.linalg.norm(a, axis=-1); lb = np.linalg.norm(b, axis=-1); lc = np.linalg.norm(c, axis=-1)
    num = (a * np.cross(b, c)).sum(-1)
    den = la * lb * lc + (a * b).sum(-1) * lc + (b * c).sum(-1) * la + (c * a).sum(-1) * lb
    return (2. * np.arctan2(num, den)).sum(-1) / (4. * np.pi)


def inside(V, tris, points, level=.5):
    return np.abs(winding(V, tris, points)) > level
