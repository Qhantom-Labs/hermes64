"""Theme-agnostic low-poly mesh toolkit (Blender space: +Z up, model front faces -Y).

A Mesh is a polygon soup with per-face role (semantic material role), smooth flag and optional
explicit UVs. Closed primitives are oriented outward automatically (signed volume check).
"""
import math
import sys

import numpy as np

try:
    if 'bpy' not in sys.modules:
        raise ImportError('ordinary Python uses the deterministic portable triangulator')
    from mathutils.geometry import tessellate_polygon as _tess
except Exception:  # pragma: no cover - outside Blender
    _tess = None

TAU = 2 * math.pi


class Mesh:
    __slots__ = ("v", "f", "r", "s", "uv")

    def __init__(self):
        self.v = []
        self.f = []
        self.r = []
        self.s = []
        self.uv = []

    # -- construction
    def add(self, verts, faces, role, smooth=False, uvs=None):
        base = len(self.v)
        self.v.extend([tuple(float(c) for c in p) for p in verts])
        for i, f in enumerate(faces):
            self.f.append(tuple(base + j for j in f))
            self.r.append(role[i] if isinstance(role, (list, tuple)) else role)
            self.s.append(smooth[i] if isinstance(smooth, (list, tuple)) else smooth)
            self.uv.append(None if uvs is None else uvs[i])
        return self

    def merge(self, *others):
        for o in others:
            if o is None:
                continue
            base = len(self.v)
            self.v.extend(o.v)
            self.f.extend(tuple(base + j for j in f) for f in o.f)
            self.r.extend(o.r)
            self.s.extend(o.s)
            self.uv.extend(o.uv)
        return self

    def copy(self):
        m = Mesh()
        m.v = list(self.v)
        m.f = list(self.f)
        m.r = list(self.r)
        m.s = list(self.s)
        m.uv = list(self.uv)
        return m

    # -- transforms (in place, return self)
    def apply(self, fn):
        if not self.v:
            return self
        a = np.asarray(self.v, dtype=np.float64)
        b = fn(a)
        self.v = [tuple(p) for p in b.tolist()]
        return self

    def translate(self, x=0.0, y=0.0, z=0.0):
        return self.apply(lambda a: a + np.array([x, y, z]))

    def scale(self, sx=1.0, sy=None, sz=None):
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        self.apply(lambda a: a * np.array([sx, sy, sz]))
        g = abs(sx * sy * sz) ** (1.0 / 3.0)
        if abs(g - 1.0) > 1e-9:
            self.uv = [u if (u is None or u[0] != "m") else ("m", [(a * g, b * g) for a, b in u[1]]) for u in self.uv]
        if sx * sy * sz < 0:
            self.flip()
        return self

    def rotate_z(self, ang):
        c, s = math.cos(ang), math.sin(ang)
        M = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        return self.apply(lambda a: a @ M.T)

    def rotate_x(self, ang):
        c, s = math.cos(ang), math.sin(ang)
        M = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        return self.apply(lambda a: a @ M.T)

    def rotate_y(self, ang):
        c, s = math.cos(ang), math.sin(ang)
        M = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return self.apply(lambda a: a @ M.T)

    def mirror_x(self):
        self.apply(lambda a: a * np.array([-1.0, 1.0, 1.0]))
        return self.flip()

    def flip(self):
        self.f = [tuple(reversed(f)) for f in self.f]
        self.uv = [None if u is None else (u[0], list(reversed(u[1]))) for u in self.uv]
        return self

    def set_role(self, role):
        self.r = [role] * len(self.f)
        return self

    # -- queries
    def tri_count(self):
        return sum(len(f) - 2 for f in self.f)

    def bounds(self):
        a = np.asarray(self.v)
        return a.min(0), a.max(0)

    def signed_volume(self):
        a = np.asarray(self.v)
        vol = 0.0
        for f in self.f:
            p0 = a[f[0]]
            for i in range(1, len(f) - 1):
                vol += np.dot(p0, np.cross(a[f[i]], a[f[i + 1]]))
        return vol / 6.0

    def orient_outward(self):
        if self.signed_volume() < 0:
            self.flip()
        return self


# ---------------------------------------------------------------- 2D outlines (CCW)
def circle2d(r, k, start=0.0, rx=None, ry=None):
    rx = r if rx is None else rx
    ry = r if ry is None else ry
    return [(rx * math.cos(start + TAU * i / k), ry * math.sin(start + TAU * i / k)) for i in range(k)]


def superellipse2d(a, b, k, e=2.0, start=0.0):
    pts = []
    for i in range(k):
        t = start + TAU * i / k
        c, s = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2.0 / e), c)
        y = b * math.copysign(abs(s) ** (2.0 / e), s)
        pts.append((x, y))
    return pts


def rounded_rect2d(w, d, rad, k_corner=3):
    rad = max(0.0, min(rad, w / 2 - 1e-4, d / 2 - 1e-4))
    if rad < 1e-4:
        return [(w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2), (-w / 2, -d / 2)]
    pts = []
    centers = [(w / 2 - rad, -d / 2 + rad, -90), (w / 2 - rad, d / 2 - rad, 0),
               (-w / 2 + rad, d / 2 - rad, 90), (-w / 2 + rad, -d / 2 + rad, 180)]
    for cx, cy, a0 in centers:
        for j in range(k_corner + 1):
            a = math.radians(a0 + 90.0 * j / k_corner)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def plan2d(shape, w, d, k=16, corner=0.3):
    """Room/furniture plan outlines centred at origin, CCW."""
    if shape == "rect":
        return rounded_rect2d(w, d, 0.0)
    if shape == "rounded_rect":
        return rounded_rect2d(w, d, corner * min(w, d) * 0.5, max(2, k // 8))
    if shape == "round":
        r = min(w, d) / 2
        return circle2d(r, k)
    if shape == "oval":
        return circle2d(0, k, rx=w / 2, ry=d / 2)
    if shape == "squircle":
        return superellipse2d(w / 2, d / 2, k, 4.0)
    if shape == "flower":
        pts = []
        petals = 6
        for i in range(k):
            t = TAU * i / k
            rr = 1.0 + 0.12 * math.cos(petals * t)
            pts.append((w / 2 * rr * math.cos(t) / 1.12, d / 2 * rr * math.sin(t) / 1.12))
        return pts
    if shape == "kidney":
        pts = []
        for i in range(k):
            t = TAU * i / k
            rr = 1.0 - 0.22 * max(0.0, math.sin(t)) ** 3
            pts.append((w / 2 * math.cos(t), d / 2 * rr * math.sin(t)))
        return pts
    raise ValueError("unknown plan shape %r" % shape)


def opening2d(shape, w, h, k=12):
    """Window/door opening outline in (x, z) with bottom at z=0, CCW. Shapes: rect, rounded_rect,
    oval, round, arch (round top), gothic (pointed), round_top (alias arch), hatch (round)."""
    if shape == "rect":
        return [(-w / 2, 0), (w / 2, 0), (w / 2, h), (-w / 2, h)]
    if shape == "rounded_rect":
        pts = rounded_rect2d(w, h, min(w, h) * 0.3, 3)
        return [(x, y + h / 2) for x, y in pts]
    if shape in ("oval", "round", "hatch"):
        ww = min(w, h) if shape in ("round", "hatch") else w
        hh = min(w, h) if shape in ("round", "hatch") else h
        return [(x, y + h / 2) for x, y in circle2d(0, k, start=-math.pi / 2, rx=ww / 2, ry=hh / 2)]
    if shape in ("arch", "round_top"):
        r = w / 2
        rise = min(r, h * 0.95)
        hs = h - rise
        pts = [(-w / 2, 0), (w / 2, 0)]
        if hs > 1e-4:
            pts.append((w / 2, hs))
        kk = max(4, k // 2)
        for i in range(1, kk):
            a = math.pi * i / kk
            pts.append((r * math.cos(a), hs + rise * math.sin(a)))
        if hs > 1e-4:
            pts.append((-w / 2, hs))
        return pts
    if shape == "rounded_top":
        rad = min(w, h) * 0.3
        pts = [(-w / 2, 0), (w / 2, 0), (w / 2, h - rad)]
        for i in range(1, 3):
            a = math.pi / 2 * i / 3
            pts.append((w / 2 - rad + rad * math.cos(a), h - rad + rad * math.sin(a)))
        pts += [(w / 2 - rad, h), (-w / 2 + rad, h)]
        for i in range(1, 3):
            a = math.pi / 2 + math.pi / 2 * i / 3
            pts.append((-w / 2 + rad + rad * math.cos(a), h - rad + rad * math.sin(a)))
        pts.append((-w / 2, h - rad))
        return pts
    if shape == "gothic":
        # equilateral pointed arch: each arc centred on the opposite springing point
        rise = min(h, 0.866 * w)
        hs = h - rise
        sy = rise / (0.866 * w)
        kk = max(3, k // 4)
        pts = [(-w / 2, 0), (w / 2, 0)]
        if hs > 1e-4:
            pts.append((w / 2, hs))
        for i in range(1, kk + 1):
            a = math.radians(60.0 * i / kk)
            pts.append((-w / 2 + w * math.cos(a), hs + w * math.sin(a) * sy))
        for i in range(kk - 1, -1, -1):
            a = math.radians(180.0 - 60.0 * i / kk)
            pts.append((w / 2 + w * math.cos(a), hs + w * math.sin(a) * sy))
        if hs <= 1e-4:
            pts.pop()  # last point would duplicate the start corner
        return pts
    raise ValueError("unknown opening shape %r" % shape)


def polygon_area2d(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def ccw(pts):
    return pts if polygon_area2d(pts) > 0 else list(reversed(pts))


def tessellate(outer, holes=()):
    """Triangulate outer polygon (+holes) in 2D -> list of index triples into outer+holes concat."""
    loops = [list(outer)] + [list(h) for h in holes]
    if _tess is not None:
        from mathutils import Vector
        vl = [[Vector((p[0], p[1], 0.0)) for p in loop] for loop in loops]
        tris = _tess(vl)
        # tessellate_polygon returns indices into the flattened list of points
        return [tuple(t) for t in tris]
    from .triangulate import triangulate
    return triangulate(outer, holes)


def _ear_clip(pts):
    idx = list(range(len(pts)))
    if polygon_area2d(pts) < 0:
        idx.reverse()
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            a, b, c = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            ax, ay = pts[a]
            bx, by = pts[b]
            cx, cy = pts[c]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 1e-12:
                continue
            ok = True
            for o in idx:
                if o in (a, b, c):
                    continue
                px, py = pts[o]
                d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if d1 >= 0 and d2 >= 0 and d3 >= 0:
                    ok = False
                    break
            if ok:
                tris.append((a, b, c))
                idx.pop(k)
                break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


# ---------------------------------------------------------------- closed primitives
def box(cx, cy, cz, sx, sy, sz, role, smooth=False, roles=None):
    x0, x1 = cx - sx / 2, cx + sx / 2
    y0, y1 = cy - sy / 2, cy + sy / 2
    z0, z1 = cz - sz / 2, cz + sz / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    # roles order: bottom, top, front(-y), right(+x), back(+y), left(-x)
    r = roles if roles else role
    return Mesh().add(v, f, r, smooth)


def prism(outline, z0, z1, role, role_top=None, role_bottom=None, holes=(), smooth_sides=False):
    """Extrude a CCW 2D outline (with optional CW-or-any holes) between z0 and z1. Closed."""
    outer = ccw(list(outline))
    hl = [list(reversed(ccw(list(h)))) for h in holes]
    loops = [outer] + hl
    flat = [p for loop in loops for p in loop]
    n = len(flat)
    m = Mesh()
    verts = [(x, y, z0) for x, y in flat] + [(x, y, z1) for x, y in flat]
    tris = tessellate(outer, hl)
    faces, roles, sm, uvs = [], [], [], []
    for a, b, c in tris:
        faces.append((a + n, b + n, c + n))
        roles.append(role_top or role)
        sm.append(False)
        uvs.append(None)
        faces.append((c, b, a))
        roles.append(role_bottom or role)
        sm.append(False)
        uvs.append(None)
    off = 0
    for loop in loops:
        k = len(loop)
        ul = [0.0]
        for i in range(k):
            p0, p1 = loop[i], loop[(i + 1) % k]
            ul.append(ul[-1] + math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        for i in range(k):
            a = off + i
            b = off + (i + 1) % k
            faces.append((a, b, b + n, a + n))
            roles.append(role)
            sm.append(smooth_sides)
            uvs.append(("m", [(ul[i], z0), (ul[i + 1], z0), (ul[i + 1], z1), (ul[i], z1)]))
        off += k
    m.add(verts, faces, roles, sm, uvs)
    return m.orient_outward()


def lathe(profile, segs, role, smooth=True, roles=None, start=0.0, cap_roles=None, rx=1.0, ry=1.0):
    """Revolve profile [(r, z), ...] bottom->top around +Z. r==0 endpoints become poles, other
    endpoints get flat caps. roles: optional per profile segment. rx/ry squash to ellipses.
    UVs: metric cylindrical (u = arc length at the band's mean radius, v = profile length)."""
    prof = [(max(0.0, r), z) for r, z in profile]
    m = Mesh()
    verts = []
    ring_idx = []
    for r, z in prof:
        if r < 1e-7:
            ring_idx.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ids = []
            for i in range(segs):
                t = start + TAU * i / segs
                ids.append(len(verts))
                verts.append((r * rx * math.cos(t), r * ry * math.sin(t), z))
            ring_idx.append(ids)
    plen = [0.0]
    for j in range(1, len(prof)):
        plen.append(plen[-1] + math.hypot(prof[j][0] - prof[j - 1][0], prof[j][1] - prof[j - 1][1]))
    sc = (rx + ry) * 0.5
    faces, rl, sm, uvs = [], [], [], []
    for j in range(len(prof) - 1):
        A, B = ring_idx[j], ring_idx[j + 1]
        rr = roles[j] if roles else role
        if len(A) == 1 and len(B) == 1:
            continue
        rm = max(1e-3, 0.5 * (prof[j][0] + prof[j + 1][0]) * sc)
        va, vb = plen[j], plen[j + 1]
        for i in range(segs):
            ua = rm * TAU * i / segs
            ub = rm * TAU * (i + 1) / segs
            if len(A) == 1:
                faces.append((A[0], B[(i + 1) % segs], B[i]))
                uvs.append(("m", [((ua + ub) / 2, va), (ub, vb), (ua, vb)]))
            elif len(B) == 1:
                faces.append((A[i], A[(i + 1) % segs], B[0]))
                uvs.append(("m", [(ua, va), (ub, va), ((ua + ub) / 2, vb)]))
            else:
                faces.append((A[i], A[(i + 1) % segs], B[(i + 1) % segs], B[i]))
                uvs.append(("m", [(ua, va), (ub, va), (ub, vb), (ua, vb)]))
            rl.append(rr)
            sm.append(smooth)
    cr = cap_roles or (role, role)
    if len(ring_idx[0]) > 1:
        faces.append(tuple(reversed(ring_idx[0])))
        rl.append(cr[0])
        sm.append(False)
        uvs.append(None)
    if len(ring_idx[-1]) > 1:
        faces.append(tuple(ring_idx[-1]))
        rl.append(cr[1])
        sm.append(False)
        uvs.append(None)
    m.add(verts, faces, rl, sm, uvs)
    return m.orient_outward()


def cylinder(cx, cy, z0, r, h, segs, role, smooth=True, cap_roles=None):
    return lathe([(r, 0.0), (r, h)], segs, role, smooth, cap_roles=cap_roles).translate(cx, cy, z0)


def sphere(cx, cy, cz, rx, ry, rz, segs, rings, role, smooth=True, start=0.0):
    ra = 0.5 * (rx + ry)
    prof = [(ra * math.sin(math.pi * j / rings), -rz * math.cos(math.pi * j / rings)) for j in range(rings + 1)]
    prof[0] = (0.0, -rz)
    prof[-1] = (0.0, rz)
    m = lathe(prof, segs, role, smooth, rx=rx / ra, ry=ry / ra, start=start)
    return m.translate(cx, cy, cz)


def loft(rings, role, smooth=True, cap0=True, cap1=True, roles=None, cap_roles=None):
    """rings: list of point lists (equal length k). Faces between consecutive rings, caps at ends.
    Orientation is fixed afterwards by signed volume (requires caps for a closed result)."""
    k = len(rings[0])
    verts = [p for ring in rings for p in ring]
    R = [np.asarray(r, dtype=np.float64) for r in rings]
    # metric UVs: u = perimeter distance along the ring, v = distance between ring centroids
    cen = [r.mean(0) for r in R]
    vlen = [0.0]
    for j in range(1, len(R)):
        vlen.append(vlen[-1] + float(np.linalg.norm(cen[j] - cen[j - 1])))
    faces, rl, sm, uvs = [], [], [], []
    for j in range(len(rings) - 1):
        rr = roles[j] if roles else role
        per = 0.5 * (R[j] + R[j + 1])
        ulen = [0.0]
        for i in range(k):
            ulen.append(ulen[-1] + float(np.linalg.norm(per[(i + 1) % k] - per[i])))
        for i in range(k):
            a = j * k + i
            b = j * k + (i + 1) % k
            faces.append((a, b, b + k, a + k))
            rl.append(rr)
            sm.append(smooth)
            uvs.append(("m", [(ulen[i], vlen[j]), (ulen[i + 1], vlen[j]), (ulen[i + 1], vlen[j + 1]), (ulen[i], vlen[j + 1])]))
    cr = cap_roles or (role, role)
    if cap0:
        faces.append(tuple(reversed(range(k))))
        rl.append(cr[0])
        sm.append(False)
        uvs.append(None)
    if cap1:
        last = (len(rings) - 1) * k
        faces.append(tuple(range(last, last + k)))
        rl.append(cr[1])
        sm.append(False)
        uvs.append(None)
    m = Mesh().add(verts, faces, rl, sm, uvs)
    if cap0 and cap1:
        m.orient_outward()
    return m


def frames_along(path):
    """Parallel-transport frames (tangent, normal, binormal) along a 3D polyline."""
    P = np.asarray(path, dtype=np.float64)
    n = len(P)
    T = np.zeros((n, 3))
    for i in range(n):
        if i == 0:
            d = P[1] - P[0]
        elif i == n - 1:
            d = P[-1] - P[-2]
        else:
            d = P[i + 1] - P[i - 1]
        T[i] = d / max(np.linalg.norm(d), 1e-12)
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = np.cross(T[0], ref)
    N /= np.linalg.norm(N)
    Ns = [N]
    for i in range(1, n):
        b = np.cross(T[i - 1], T[i])
        if np.linalg.norm(b) > 1e-9:
            b /= np.linalg.norm(b)
            ang = math.acos(max(-1.0, min(1.0, float(np.dot(T[i - 1], T[i])))))
            N = _rot(N, b, ang)
        Ns.append(N)
    Ns = np.array(Ns)
    B = np.cross(T, Ns)
    return T, Ns, B


def _rot(v, axis, ang):
    c, s = math.cos(ang), math.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1 - c)


def tube(path, radius, sides, role, smooth=True, cap0=True, cap1=True, ry=None, twist=0.0):
    """Loft a circular (or elliptic) section along a polyline. radius: float or per-point list."""
    T, N, B = frames_along(path)
    rings = []
    for i, p in enumerate(path):
        r = radius[i] if isinstance(radius, (list, tuple)) else radius
        r2 = (ry[i] if isinstance(ry, (list, tuple)) else ry) if ry is not None else r
        ring = []
        for k in range(sides):
            a = TAU * k / sides + twist
            ring.append(tuple(np.asarray(p) + N[i] * r * math.cos(a) + B[i] * r2 * math.sin(a)))
        rings.append(ring)
    return loft(rings, role, smooth, cap0, cap1)


def ring3d(cx, cy, z, pts2d):
    return [(cx + x, cy + y, z) for x, y in pts2d]


def lathe_closed(loop, segs, role, smooth=True, rx=1.0, ry=1.0, roles=None, start=0.0):
    """Revolve a CLOSED 2D loop [(r, z), ...] (all r > 0, CCW in the r-z plane) around +Z.
    Produces a closed ring-shaped solid (rims, shades, thick bowls, hoops). No caps needed."""
    k = len(loop)
    verts = []
    for i in range(segs):
        t = start + TAU * i / segs
        c, s = math.cos(t), math.sin(t)
        for r, z in loop:
            verts.append((r * rx * c, r * ry * s, z))
    faces, rl, uvs = [], [], []
    plen = [0.0]
    for j in range(k):
        a, b = loop[j], loop[(j + 1) % k]
        plen.append(plen[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    sc = (rx + ry) * 0.5
    for i in range(segs):
        i2 = (i + 1) % segs
        for j in range(k):
            j2 = (j + 1) % k
            faces.append((i * k + j, i2 * k + j, i2 * k + j2, i * k + j2))
            rl.append(roles[j] if roles else role)
            rm = max(1e-3, 0.5 * (loop[j][0] + loop[j2][0]) * sc)
            ua, ub = rm * TAU * i / segs, rm * TAU * (i + 1) / segs
            uvs.append(("m", [(ua, plen[j]), (ub, plen[j]), (ub, plen[j + 1]), (ua, plen[j + 1])]))
    return Mesh().add(verts, faces, rl, smooth, uvs).orient_outward()


def rounded_box(cx, cy, cz, sx, sy, sz, role, bevel=0.3, smooth=True, k_corner=2):
    """Pillowy/molded box: loft of rounded-rect rings (bevelled top/bottom). bevel in 0..1."""
    b = max(0.0, min(0.95, bevel))
    rad = b * 0.5 * min(sx, sy)
    zb = b * 0.5 * sz
    outline = rounded_rect2d(sx, sy, max(rad, 0.02 * min(sx, sy)), k_corner)
    fx = max(0.05, (sx - 2 * zb * 0.6) / sx)
    fy = max(0.05, (sy - 2 * zb * 0.6) / sy)
    inner = [(x * fx, y * fy) for x, y in outline]
    rings = [ring3d(cx, cy, cz - sz / 2, inner), ring3d(cx, cy, cz - sz / 2 + zb, outline),
             ring3d(cx, cy, cz + sz / 2 - zb, outline), ring3d(cx, cy, cz + sz / 2, inner)]
    if zb < 1e-4:
        rings = [ring3d(cx, cy, cz - sz / 2, outline), ring3d(cx, cy, cz + sz / 2, outline)]
    return loft(rings, role, smooth)


def blob(cx, cy, cz, rx, ry, rz, role, segs=8, rings=5, squash_bottom=0.0, smooth=True):
    """Squashed sphere (cushion lobes, puffs). squash_bottom flattens the lower half."""
    m = sphere(0, 0, 0, rx, ry, rz, segs, rings, role, smooth)
    if squash_bottom > 0:
        m.apply(lambda a: np.where(a[:, 2:3] < 0, a * np.array([1, 1, 1 - squash_bottom]), a))
    return m.translate(cx, cy, cz)


def torus(R, r, segs, sides, role, smooth=True):
    verts, faces = [], []
    for i in range(segs):
        a = TAU * i / segs
        for j in range(sides):
            b = TAU * j / sides
            verts.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(segs):
        for j in range(sides):
            a = i * sides + j
            b = ((i + 1) % segs) * sides + j
            c = ((i + 1) % segs) * sides + (j + 1) % sides
            d = i * sides + (j + 1) % sides
            faces.append((a, b, c, d))
    return Mesh().add(verts, faces, role, smooth).orient_outward()


def card(w, h, role, facing="-y", uv=None, double=False):
    """Planar single-sided card centred at origin bottom edge at z=0 (kit_card_ nodes)."""
    v = [(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, 0, h), (-w / 2, 0, h)]
    uvs = [("n", uv or [(0, 0), (1, 0), (1, 1), (0, 1)])]
    m = Mesh().add(v, [(0, 1, 2, 3)], role, False, uvs)
    if facing == "+y":
        m.flip()
    return m


def grid_surface(nu, nv, fn, role, smooth=True, uv_fn=None):
    """Open surface z = fn(u,v) style: fn(u,v)->(x,y,z) for u,v in [0,1]. Faces point +Z if fn is
    monotone in x/y like a terrain."""
    verts = []
    for j in range(nv + 1):
        for i in range(nu + 1):
            verts.append(fn(i / nu, j / nv))
    faces = []
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            faces.append((a, a + 1, a + nu + 2, a + nu + 1))
    return Mesh().add(verts, faces, role, smooth)


def edge_stats(m, weld=1e-5):
    """Return (#boundary edges, #non-manifold edges, #inconsistent edges) after welding positions."""
    key = {}
    vid = []
    for p in m.v:
        k = (round(p[0] / weld), round(p[1] / weld), round(p[2] / weld))
        if k not in key:
            key[k] = len(key)
        vid.append(key[k])
    count = {}
    directed = {}
    for f in m.f:
        ids = [vid[i] for i in f]
        for i in range(len(ids)):
            a, b = ids[i], ids[(i + 1) % len(ids)]
            if a == b:
                continue
            e = (min(a, b), max(a, b))
            count[e] = count.get(e, 0) + 1
            directed[(a, b)] = directed.get((a, b), 0) + 1
    boundary = sum(1 for c in count.values() if c == 1)
    nonman = sum(1 for c in count.values() if c > 2)
    incons = sum(1 for d, c in directed.items() if c > 1)
    return boundary, nonman, incons
