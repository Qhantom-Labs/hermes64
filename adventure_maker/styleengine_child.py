"""STYLEENGINE sandboxed child: run an agent builder script, or convert a GLB/OBJ into a role-mapped project mesh.

    python -I -B styleengine_child.py <request.json>        (always under runner.Runner: no network, writes only in
                                                             the project, reads only project/bundle/interpreter)

mode `script`: the request names a script file inside the project stage. It is parsed, checked against an AST
allow-list (no imports, no dunder names or attributes, no open/eval/exec/compile/getattr/globals/...), then evaluated
node by node by a small interpreter (no exec) that knows only the builder API below, safe builtins and math. Its emitted parts are written as an OBJ (`usemtl <pack role>`).
mode `mesh`: a GLB or OBJ inside the project (+ optional PNG/JPG) -> OBJ in meshkit axes (+Z up, metres) with every
face mapped to the nearest pack role by its material/texture colour (the texture first conformed to the pack palette
with the pack's dither: kits/core/conform.conform_texture).

Builder API (metres, +Z up, front -Y; roles are pack palette roles, never RGB):
  box(sx, sy, sz, at=(0,0,0), role='body')      cylinder(r, h, at, sides=8, role)     cone(r, h, at, sides=8, role)
  sphere(r, at, segs=8, rings=6, role)           blob(rx, ry, rz, at, segs=8, rings=6, squash=0, role)
  torus(R, r, at, segs=12, sides=6, role)        lathe(profile, segs=8, role)          loft(rings, role)
  extrude(outline, z0, z1, role)                 tube(path, r, sides=6, role)          heightfield(rows, width, depth, role)
  card(w, h, role)
  move(p, x, y, z)  rotate(p, rx, ry, rz)  scale(p, sx, sy=None, sz=None)  mirror(p, axis='x') -> [p, copy]
  array(p, n, step=(0,0,0), turn=(0,0,0)) -> list   union(*parts)   paint(p, role)   emit(*parts)
  math, pi, sin, cos, tan, sqrt, atan2, radians, rand(i) (seeded, deterministic)
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'kits') not in sys.path:
    sys.path.append(str(ROOT / 'kits'))

MAX_PARTS = 512
MAX_FILE_PARTS = 64          # a file's nodes beyond this many share the last part
BANNED_NAMES = {'open', 'exec', 'eval', 'compile', '__import__', 'getattr', 'setattr', 'delattr', 'globals', 'locals',
                'vars', 'input', 'breakpoint', 'help', 'dir', 'type', 'object', 'memoryview', 'bytearray', 'super',
                'classmethod', 'staticmethod', 'property', 'exit', 'quit', 'copyright', 'credits', 'license'}
BANNED_ATTRS = {'format', 'format_map', 'mro', 'tofile', 'save', 'load'}
BANNED_NODES = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.AsyncFor,
                ast.AsyncWith, ast.Yield, ast.YieldFrom, ast.ClassDef)


class ScriptError(ValueError):
    pass


def check_script(source):
    """AST allow-list. Raises ScriptError with the line number of the first refused construct."""
    try:
        tree = ast.parse(source, '<builder script>')
    except SyntaxError as e:
        raise ScriptError('syntax error line %s: %s' % (e.lineno, e.msg))
    for node in ast.walk(tree):
        line = getattr(node, 'lineno', '?')
        if isinstance(node, BANNED_NODES):
            raise ScriptError('line %s: %s is not allowed in a builder script' % (line, type(node).__name__))
        if isinstance(node, ast.Name) and (node.id.startswith('_') or node.id in BANNED_NAMES):
            raise ScriptError('line %s: name %r is not allowed' % (line, node.id))
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in BANNED_ATTRS):
            raise ScriptError('line %s: attribute %r is not allowed' % (line, node.attr))
        if isinstance(node, (ast.FunctionDef, ast.Lambda)) and isinstance(node, ast.FunctionDef) and node.name.startswith('_'):
            raise ScriptError('line %s: names starting with _ are not allowed' % line)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and '__' in node.value:
            raise ScriptError('line %s: strings containing "__" are not allowed' % line)
    return tree


# ------------------------------------------------------------------------------------------------ builder API
def api(roles):
    from core import meshkit as K
    import numpy as np

    class Part:
        __slots__ = ('mesh', 'kind', 'group')

        def __init__(self, mesh, kind=None):
            self.mesh = mesh
            self.kind = kind
            self.group = None

    out = []
    count = [0]

    def role_ok(r):
        if r not in roles:
            raise ScriptError('unknown role %r: use a pack palette role (e.g. body, wood, stone, metal, glass, light)' % r)
        return r

    def at3(at):
        if not (isinstance(at, (list, tuple)) and len(at) == 3):
            raise ScriptError('at must be (x, y, z)')
        return [float(c) for c in at]

    def part(mesh):
        count[0] += 1
        if count[0] > 20000:
            raise ScriptError('too many parts made')
        return Part(mesh)

    def parts(*items):
        flat = []
        for it in items:
            if isinstance(it, (list, tuple)):
                flat += parts(*it)
            elif isinstance(it, Part):
                flat.append(it)
            else:
                raise ScriptError('expected parts, got %s' % type(it).__name__)
        return flat

    def box(sx, sy, sz, at=(0, 0, 0), role='body'):
        x, y, z = at3(at)
        return part(K.box(x, y, z, float(sx), float(sy), float(sz), role_ok(role)))

    def cylinder(r, h, at=(0, 0, 0), sides=8, role='body'):
        x, y, z = at3(at)
        return part(K.cylinder(x, y, z, float(r), float(h), int(sides), role_ok(role)))

    def cone(r, h, at=(0, 0, 0), sides=8, role='body'):
        x, y, z = at3(at)
        return part(K.lathe([(float(r), 0.0), (0.0, float(h))], int(sides), role_ok(role)).translate(x, y, z))

    def blob(rx, ry, rz, at=(0, 0, 0), segs=8, rings=6, squash=0.0, role='body'):
        x, y, z = at3(at)
        return part(K.blob(x, y, z, float(rx), float(ry), float(rz), role_ok(role), int(segs), int(rings), float(squash)))

    def sphere(r, at=(0, 0, 0), segs=8, rings=6, role='body'):
        return blob(r, r, r, at, segs, rings, 0.0, role)

    def torus(R, r, at=(0, 0, 0), segs=12, sides=6, role='body'):
        x, y, z = at3(at)
        return part(K.torus(float(R), float(r), int(segs), int(sides), role_ok(role)).translate(x, y, z))

    def lathe(profile, segs=8, role='body'):
        return part(K.lathe([(float(a), float(b)) for a, b in profile], int(segs), role_ok(role)))

    def loft(rings, role='body'):
        return part(K.loft([[tuple(float(c) for c in p) for p in ring] for ring in rings], role_ok(role)))

    def extrude(outline, z0, z1, role='body'):
        return part(K.prism([(float(a), float(b)) for a, b in outline], float(z0), float(z1), role_ok(role)))

    def tube(path, r, sides=6, role='body'):
        # STYLEENGINE-2: r may be one radius per path point (a radius profile: horns, tentacles, tapered legs)
        pts = [tuple(float(c) for c in p) for p in path]
        if len(pts) < 2:
            raise ScriptError('tube/sweep path needs at least 2 points')
        if isinstance(r, (list, tuple)):
            if len(r) != len(pts):
                raise ScriptError('tube/sweep: give one radius per path point (%d points, %d radii)' % (len(pts), len(r)))
            rr = [max(float(x), 0.001) for x in r]
        else:
            rr = float(r)
        return part(K.tube(pts, rr, int(sides), role_ok(role)))

    def heightfield(rows, width, depth, role='body'):
        nv, nu = len(rows) - 1, len(rows[0]) - 1
        if nv < 1 or nu < 1 or any(len(r) != nu + 1 for r in rows):
            raise ScriptError('heightfield rows must be a rectangle of at least 2 x 2 numbers')

        def fn(u, v):
            return ((u - .5) * float(width), (v - .5) * float(depth), float(rows[round(v * nv)][round(u * nu)]))
        return part(K.grid_surface(nu, nv, fn, role_ok(role)))

    def card(w, h, role='body'):
        p = part(K.card(float(w), float(h), role_ok(role)))
        p.kind = 'card'
        return p

    # ---------------------------------------------------------------- STYLEENGINE-2 additions (bounded, no I/O)
    def chamfer_box(sx, sy, sz, c=0.04, at=(0, 0, 0), role='body'):
        """A box with every edge cut at 45 degrees (44 triangles; centred on `at`, like box): reads as machined or
        carved instead of a crate."""
        X, Y, Z = float(sx) / 2, float(sy) / 2, float(sz) / 2
        c = max(0.0, min(float(c), 0.45 * min(X, Y, Z) * 2))
        x0, y0, z0 = at3(at)
        idx, verts = {}, []

        def v(i, j, k, ax):
            key = (i, j, k, ax)
            if key not in idx:
                p = [i * X, j * Y, k * Z]
                for a in range(3):
                    if a != 'xyz'.index(ax):
                        p[a] -= (i, j, k)[a] * c
                idx[key] = len(verts)
                verts.append((p[0] + x0, p[1] + y0, p[2] + z0))
            return idx[key]
        faces = []
        S = (-1, 1)
        for s in S:
            faces.append([v(s, j, k, 'x') for j, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            faces.append([v(i, s, k, 'y') for i, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            faces.append([v(i, j, s, 'z') for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        for j in S:
            for k in S:
                faces.append([v(-1, j, k, 'y'), v(1, j, k, 'y'), v(1, j, k, 'z'), v(-1, j, k, 'z')])
        for i in S:
            for k in S:
                faces.append([v(i, -1, k, 'x'), v(i, 1, k, 'x'), v(i, 1, k, 'z'), v(i, -1, k, 'z')])
        for i in S:
            for j in S:
                faces.append([v(i, j, -1, 'x'), v(i, j, 1, 'x'), v(i, j, 1, 'y'), v(i, j, -1, 'y')])
        for i in S:
            for j in S:
                for k in S:
                    faces.append([v(i, j, k, 'x'), v(i, j, k, 'y'), v(i, j, k, 'z')])
        ctr = np.array([x0, y0, z0])
        tris = []
        for f in faces:
            P = np.array([verts[q] for q in f])
            n = np.cross(P[1] - P[0], P[2] - P[0]) if len(f) == 3 else np.cross(P[2] - P[0], P[3] - P[1])
            if np.dot(n, P.mean(0) - ctr) < 0:
                f = f[::-1]
            tris += [(f[0], f[a], f[a + 1]) for a in range(1, len(f) - 1)]
        m = K.Mesh()
        m.add(verts, tris, role_ok(role), smooth=False)
        return part(m)

    def beam(sx, sy, sz, n=6, at=(0, 0, 0), axis='x', role='body'):
        """A box cut into n segments along `axis` (8n+4 triangles), so bend/twist/taper can curve it (a torii top
        beam, a ship's yard, a curved bench). Centred on `at`, like box."""
        n, a = int(n), _axis(axis)
        if not 1 <= n <= 64:
            raise ScriptError('beam segments must be 1-64')
        size = [float(sx), float(sy), float(sz)]
        x0, y0, z0 = at3(at)
        o = [i for i in range(3) if i != a]
        corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
        verts = []
        for k in range(n + 1):
            for cu, cv in corners:
                p = [0.0, 0.0, 0.0]
                p[a] = -size[a] / 2 + size[a] * k / n
                p[o[0]] = cu * size[o[0]] / 2
                p[o[1]] = cv * size[o[1]] / 2
                verts.append((p[0] + x0, p[1] + y0, p[2] + z0))
        tris = []
        for k in range(n):
            for c in range(4):
                a0, a1 = 4 * k + c, 4 * k + (c + 1) % 4
                b0, b1 = a0 + 4, a1 + 4
                tris += [(a0, a1, b1), (a0, b1, b0)]
        last = 4 * n
        tris += [(0, 2, 1), (0, 3, 2), (last, last + 1, last + 2), (last, last + 2, last + 3)]
        ctr = np.array([x0, y0, z0])
        fixed = []
        for t in tris:
            P = np.array([verts[q] for q in t])
            nrm = np.cross(P[1] - P[0], P[2] - P[0])
            fixed.append(t if np.dot(nrm, P.mean(0) - ctr) >= 0 else t[::-1])
        m = K.Mesh()
        m.add(verts, fixed, role_ok(role), smooth=False)
        return part(m)

    def _group_bounds(ps):
        allv = np.array([v for q in ps for v in q.mesh.v], dtype=np.float64)
        if not len(allv):
            raise ScriptError('nothing to transform')
        return allv.min(0), allv.max(0)

    def _axis(axis):
        if axis not in ('x', 'y', 'z'):
            raise ScriptError('axis must be x, y or z')
        return 'xyz'.index(axis)

    def taper(p, top=0.5, axis='z'):
        """Scale the cross-section from 1 at the low end of `axis` to `top` at the high end (a tree trunk, a horn)."""
        ps, a = parts(p), _axis(axis)
        lo, hi = _group_bounds(ps)
        span = max(hi[a] - lo[a], 1e-9)
        ctr = (lo + hi) / 2
        o = [i for i in range(3) if i != a]
        for q in ps:
            def fn(A, q=q):
                t = (A[:, a] - lo[a]) / span
                k = 1.0 + (float(top) - 1.0) * t
                B = A.copy()
                for i in o:
                    B[:, i] = ctr[i] + (A[:, i] - ctr[i]) * k
                return B
            q.mesh.apply(fn)
        return p

    def twist(p, degrees=90, axis='z'):
        """Rotate cross-sections around `axis`, 0 at the low end to `degrees` at the high end (a unicorn horn)."""
        ps, a = parts(p), _axis(axis)
        lo, hi = _group_bounds(ps)
        span = max(hi[a] - lo[a], 1e-9)
        ctr = (lo + hi) / 2
        i, j = [k for k in range(3) if k != a]
        for q in ps:
            def fn(A, q=q):
                ang = np.radians(float(degrees)) * (A[:, a] - lo[a]) / span
                c, s = np.cos(ang), np.sin(ang)
                B = A.copy()
                u, w = A[:, i] - ctr[i], A[:, j] - ctr[j]
                B[:, i] = ctr[i] + u * c - w * s
                B[:, j] = ctr[j] + u * s + w * c
                return B
            q.mesh.apply(fn)
        return p

    def bend(p, degrees=30, along='x', up='z'):
        """Curve the part along `along` in the (along, up) plane: positive degrees lift both ends (a torii top beam,
        a smile); negative ones droop them (a bow, a sail's belly)."""
        ps, a, b = parts(p), _axis(along), _axis(up)
        if a == b:
            raise ScriptError('bend: along and up must differ')
        th = math.radians(float(degrees))
        if abs(th) < 1e-6:
            return p
        lo, hi = _group_bounds(ps)
        L = max(hi[a] - lo[a], 1e-9)
        R = L / th
        ca, base = (lo[a] + hi[a]) / 2, lo[b]
        for q in ps:
            def fn(A, q=q):
                s = A[:, a] - ca
                u = A[:, b] - base
                ang = s / R
                B = A.copy()
                B[:, a] = ca + (R - u) * np.sin(ang)
                B[:, b] = base + R - (R - u) * np.cos(ang)
                return B
            q.mesh.apply(fn)
        return p

    def displace(p, amount=0.03, seed=0, scale=0.25):
        """Deterministic lumpy noise along the direction from the part's centre (rock, bone, bark): shared corners
        move together, so solids stay closed. amount in metres; scale = noise cell size in metres."""
        ps = parts(p)
        lo, hi = _group_bounds(ps)
        ctr = (lo + hi) / 2
        amt, cell = float(amount), max(float(scale), 1e-3)
        if abs(amt) > 2.0:
            raise ScriptError('displace amount must be within 2 m')

        def lattice(ix, iy, iz):
            h = hashlib.sha256(('%d|%d|%d|%d' % (int(seed), ix, iy, iz)).encode()).digest()
            return int.from_bytes(h[:4], 'big') / float(1 << 31) - 1.0
        cache = {}

        def noise(pt):
            g = [pt[k] / cell for k in range(3)]
            b0 = [math.floor(x) for x in g]
            f = [x - math.floor(x) for x in g]
            f = [t * t * (3 - 2 * t) for t in f]
            total = 0.0
            for dx in (0, 1):
                for dy in (0, 1):
                    for dz in (0, 1):
                        key = (b0[0] + dx, b0[1] + dy, b0[2] + dz)
                        if key not in cache:
                            cache[key] = lattice(*key)
                        w = (f[0] if dx else 1 - f[0]) * (f[1] if dy else 1 - f[1]) * (f[2] if dz else 1 - f[2])
                        total += w * cache[key]
            return total
        for q in ps:
            moved = {}
            nv = []
            for vtx in q.mesh.v:
                key = tuple(round(c, 5) for c in vtx)
                if key not in moved:
                    d = np.array(vtx) - ctr
                    n = np.linalg.norm(d)
                    d = d / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])
                    moved[key] = tuple((np.array(vtx) + d * amt * noise(vtx)).tolist())
                nv.append(moved[key])
            q.mesh.v = nv
        return p

    def polar(p, n, radius=0.0, axis='z'):
        """n copies spaced evenly around `axis` through the origin, each pushed out by `radius` first (cabins on a
        wheel, columns in a ring, petals)."""
        n, a = int(n), _axis(axis)
        if not 1 <= n <= 256:
            raise ScriptError('polar count must be 1-256')
        res = []
        for i in range(n):
            for q in parts(p):
                m = q.mesh.copy()
                off = [0.0, 0.0, 0.0]
                off[(a + 1) % 3] = float(radius)
                m.translate(*off)
                getattr(m, 'rotate_' + 'xyz'[a])(2 * math.pi * i / n)
                cp = part(m)
                cp.kind, cp.group = q.kind, q.group
                res.append(cp)
        return res

    def along(p, path, n, turn=True):
        """n copies spaced evenly along a polyline (teeth on a jaw, posts on a fence, rivets on a seam); turn=True
        also turns each copy to the path's heading around Z."""
        pts = [np.array([float(c) for c in q]) for q in path]
        n = int(n)
        if len(pts) < 2 or not 1 <= n <= 256:
            raise ScriptError('along needs a path of 2+ points and a count of 1-256')
        seg = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]
        total = sum(seg) or 1e-9
        res = []
        for i in range(n):
            d = total * (i / (n - 1) if n > 1 else 0.5)
            k = 0
            while k < len(seg) - 1 and d > seg[k]:
                d -= seg[k]
                k += 1
            t = d / (seg[k] or 1e-9)
            at = pts[k] + (pts[k + 1] - pts[k]) * min(max(t, 0.0), 1.0)
            head = pts[k + 1] - pts[k]
            for q in parts(p):
                m = q.mesh.copy()
                if turn:
                    m.rotate_z(math.atan2(head[1], head[0]))
                m.translate(*at.tolist())
                cp = part(m)
                cp.kind, cp.group = q.kind, q.group
                res.append(cp)
        return res

    def paint_band(p, role, axis='z', lo=-1e9, hi=1e9):
        """Repaint the faces whose centre lies between lo and hi on `axis` (stripes and bands on tessellated
        parts: lathes, sweeps, blobs). On a 12-triangle box, add a thin box instead."""
        role_ok(role)
        a = _axis(axis)
        for q in parts(p):
            for fi, f in enumerate(q.mesh.f):
                c = sum(q.mesh.v[x][a] for x in f) / len(f)
                if float(lo) <= c <= float(hi):
                    q.mesh.r[fi] = role
        return p

    def group(name, *items):
        """Name a set of parts: each named group becomes its own node in the piece (a pendulum, a lid, a wheel),
        ready for later animation; ungrouped parts are merged by kind."""
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,23}', name):
            raise ScriptError('group name: 1-24 lowercase letters, digits, underscores')
        got = parts(*items)
        for q in got:
            q.group = name
        return got

    def move(p, x=0.0, y=0.0, z=0.0):
        for q in parts(p):
            q.mesh.translate(float(x), float(y), float(z))
        return p

    def rotate(p, rx=0.0, ry=0.0, rz=0.0):
        for q in parts(p):
            for axis, ang in zip('xyz', (rx, ry, rz)):
                if ang:
                    getattr(q.mesh, 'rotate_' + axis)(math.radians(float(ang)))
        return p

    def scale(p, sx, sy=None, sz=None):
        for q in parts(p):
            q.mesh.scale(float(sx), None if sy is None else float(sy), None if sz is None else float(sz))
        return p

    def mirror(p, axis='x'):
        if axis not in ('x', 'y', 'z'):
            raise ScriptError('mirror axis must be x, y or z')
        dims = [-1.0 if a == axis else 1.0 for a in 'xyz']
        copies = []
        for q in parts(p):
            cp = part(q.mesh.copy().scale(*dims))
            cp.kind, cp.group = q.kind, q.group
            copies.append(cp)
        return [p, copies]

    def array(p, n, step=(0, 0, 0), turn=(0, 0, 0)):
        n = int(n)
        if not 1 <= n <= 256:
            raise ScriptError('array count must be 1-256')
        res = []
        for i in range(n):
            for q in parts(p):
                m = q.mesh.copy()
                for axis, ang in zip('xyz', turn):
                    if ang:
                        getattr(m, 'rotate_' + axis)(math.radians(i * float(ang)))
                m.translate(*[i * float(c) for c in step])
                cp = part(m)
                cp.kind, cp.group = q.kind, q.group
                res.append(cp)
        return res

    def union(*items):
        m = K.Mesh()
        got = parts(*items)
        for q in got:
            m.merge(q.mesh)
        u = part(m)
        u.kind = 'card' if got and all(q.kind == 'card' for q in got) else None
        u.group = next((q.group for q in got if q.group), None)
        return u

    def paint(p, role):
        role_ok(role)
        for q in parts(p):
            q.mesh.set_role(role)
        return p

    def emit(*items):
        got = parts(*items)
        if len(out) + len(got) > MAX_PARTS:
            raise ScriptError('more than %d emitted parts' % MAX_PARTS)
        out.extend(got)

    def rand(i):
        h = hashlib.sha256(('styleengine:%r' % (i,)).encode()).digest()
        return int.from_bytes(h[:6], 'big') / float(1 << 48)

    names = dict(box=box, cylinder=cylinder, cone=cone, sphere=sphere, blob=blob, torus=torus, lathe=lathe, loft=loft,
                 extrude=extrude, tube=tube, heightfield=heightfield, card=card, move=move, rotate=rotate, scale=scale,
                 mirror=mirror, array=array, union=union, paint=paint, emit=emit, rand=rand, math=math, pi=math.pi,
                 sin=math.sin, cos=math.cos, tan=math.tan, sqrt=math.sqrt, atan2=math.atan2, radians=math.radians,
                 # STYLEENGINE-2
                 sweep=tube, chamfer_box=chamfer_box, beam=beam, taper=taper, twist=twist, bend=bend, displace=displace,
                 polar=polar, along=along, paint_band=paint_band, group=group)
    return names, out


SAFE_BUILTINS = {'abs': abs, 'min': min, 'max': max, 'range': range, 'len': len, 'list': list, 'tuple': tuple,
                 'dict': dict, 'set': set, 'enumerate': enumerate, 'zip': zip, 'sorted': sorted, 'reversed': reversed,
                 'sum': sum, 'round': round, 'int': int, 'float': float, 'bool': bool, 'str': str, 'any': any,
                 'all': all, 'print': print, 'isinstance': isinstance, 'pow': pow, 'divmod': divmod}
SAFE_METHODS = {'append', 'extend', 'insert', 'pop', 'index', 'count', 'reverse', 'copy', 'keys', 'values', 'items',
                'get', 'sort'}
MAX_STEPS = 2000000
MAX_DEPTH = 40


class _Flow(Exception):
    pass


class _Break(_Flow):
    pass


class _Continue(_Flow):
    pass


class _Return(_Flow):
    def __init__(self, value):
        self.value = value


class Interpreter:
    """Runs an AST-checked builder script WITHOUT exec: a small evaluator for the allowed subset (assignments, if/for/
    while, def/return, arithmetic, comparisons, calls to the builder API, safe builtins, math and a few list/dict
    methods). Anything else is refused with its line number. Steps, recursion and range sizes are bounded."""
    BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b}
    CMP = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
           ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b, ast.Is: lambda a, b: a is b,
           ast.IsNot: lambda a, b: a is not b}

    def __init__(self, names):
        self.globals = dict(SAFE_BUILTINS)
        self.globals.update(names)
        self.steps = 0
        self.depth = 0

    def fail(self, node, why):
        raise ScriptError('line %s: %s' % (getattr(node, 'lineno', '?'), why))

    def tick(self, node):
        self.steps += 1
        if self.steps > MAX_STEPS:
            self.fail(node, 'the script ran too long (%d steps)' % MAX_STEPS)

    def run(self, tree):
        self.block(tree.body, self.globals)

    def block(self, body, env):
        for st in body:
            self.stmt(st, env)

    def assign(self, target, value, env):
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            vals = list(value)
            if len(vals) != len(target.elts):
                self.fail(target, 'cannot unpack %d values into %d names' % (len(vals), len(target.elts)))
            for t, v in zip(target.elts, vals):
                self.assign(t, v, env)
        elif isinstance(target, ast.Subscript):
            obj = self.expr(target.value, env)
            if not isinstance(obj, (list, dict)):
                self.fail(target, 'only list and dict items can be assigned')
            obj[self.expr(target.slice, env)] = value
        else:
            self.fail(target, 'cannot assign to %s' % type(target).__name__)

    def stmt(self, st, env):
        self.tick(st)
        if isinstance(st, ast.Expr):
            self.expr(st.value, env)
        elif isinstance(st, ast.Assign):
            v = self.expr(st.value, env)
            for t in st.targets:
                self.assign(t, v, env)
        elif isinstance(st, ast.AugAssign):
            if not isinstance(st.target, ast.Name) or type(st.op) not in self.BIN and not isinstance(st.op, ast.Pow):
                self.fail(st, 'augmented assignment needs a name and + - * / // % **')
            cur = self.name(st.target, env)
            env[st.target.id] = self.binop(st.op, cur, self.expr(st.value, env), st)
        elif isinstance(st, ast.If):
            self.block(st.body if self.expr(st.test, env) else st.orelse, env)
        elif isinstance(st, (ast.For, ast.While)):
            if st.orelse:
                self.fail(st, 'loop else is not supported')
            items = self.expr(st.iter, env) if isinstance(st, ast.For) else None
            it = iter(items) if isinstance(st, ast.For) else None
            while True:
                self.tick(st)
                if isinstance(st, ast.For):
                    try:
                        self.assign(st.target, next(it), env)
                    except StopIteration:
                        break
                elif not self.expr(st.test, env):
                    break
                try:
                    self.block(st.body, env)
                except _Break:
                    break
                except _Continue:
                    continue
        elif isinstance(st, ast.FunctionDef):
            if st.decorator_list or st.args.vararg or st.args.kwarg or st.args.kwonlyargs or st.args.posonlyargs:
                self.fail(st, 'functions take plain parameters only')
            env[st.name] = self.function(st, env)
        elif isinstance(st, ast.Return):
            raise _Return(self.expr(st.value, env) if st.value is not None else None)
        elif isinstance(st, ast.Break):
            raise _Break()
        elif isinstance(st, ast.Continue):
            raise _Continue()
        elif isinstance(st, ast.Pass):
            pass
        else:
            self.fail(st, '%s is not supported in a builder script' % type(st).__name__)

    def function(self, fd, outer):
        names = [a.arg for a in fd.args.args]
        defaults = [self.expr(d, outer) for d in fd.args.defaults]

        def call(*args, **kw):
            if len(args) > len(names) or any(k not in names for k in kw):
                self.fail(fd, '%s() got unexpected arguments' % fd.name)
            local = dict(zip(names[len(names) - len(defaults):], defaults))
            local.update(zip(names, args))
            local.update(kw)
            if any(n not in local for n in names):
                self.fail(fd, '%s() is missing arguments' % fd.name)
            env = _Scope(local, self.globals)
            self.depth += 1
            if self.depth > MAX_DEPTH:
                self.fail(fd, 'recursion deeper than %d' % MAX_DEPTH)
            try:
                self.block(fd.body, env)
            except _Return as r:
                return r.value
            finally:
                self.depth -= 1
            return None
        return call

    def name(self, node, env):
        if node.id in env:
            return env[node.id]
        if isinstance(env, _Scope) and node.id in env.outer:
            return env.outer[node.id]
        self.fail(node, 'unknown name %r' % node.id)

    def binop(self, op, a, b, node):
        if isinstance(op, ast.Pow):
            if isinstance(b, (int, float)) and abs(b) > 64:
                self.fail(node, 'exponent larger than 64')
            return a ** b
        if type(op) not in self.BIN:
            self.fail(node, 'operator %s is not supported' % type(op).__name__)
        if isinstance(op, ast.Mult) and isinstance(a, (list, tuple, str)) and isinstance(b, int) and len(a) * b > 100000:
            self.fail(node, 'sequence repetition too large')
        return self.BIN[type(op)](a, b)

    def comprehension(self, node, env, gens, emit):
        if not gens:
            emit(env)
            return
        g = gens[0]
        for v in self.expr(g.iter, env):
            self.tick(node)
            inner = _Scope({}, env)
            self.assign(g.target, v, inner)
            if all(self.expr(c, inner) for c in g.ifs):
                self.comprehension(node, inner, gens[1:], emit)

    def expr(self, e, env):
        self.tick(e)
        if isinstance(e, ast.Constant):
            return e.value
        if isinstance(e, ast.Name):
            return self.name(e, env)
        if isinstance(e, ast.BinOp):
            return self.binop(e.op, self.expr(e.left, env), self.expr(e.right, env), e)
        if isinstance(e, ast.UnaryOp):
            v = self.expr(e.operand, env)
            if isinstance(e.op, ast.USub):
                return -v
            if isinstance(e.op, ast.UAdd):
                return +v
            if isinstance(e.op, ast.Not):
                return not v
            self.fail(e, 'operator %s is not supported' % type(e.op).__name__)
        if isinstance(e, ast.BoolOp):
            v = None
            for x in e.values:
                v = self.expr(x, env)
                if isinstance(e.op, ast.And) and not v or isinstance(e.op, ast.Or) and v:
                    return v
            return v
        if isinstance(e, ast.Compare):
            left = self.expr(e.left, env)
            for op, right in zip(e.ops, e.comparators):
                r = self.expr(right, env)
                if not self.CMP[type(op)](left, r):
                    return False
                left = r
            return True
        if isinstance(e, ast.IfExp):
            return self.expr(e.body, env) if self.expr(e.test, env) else self.expr(e.orelse, env)
        if isinstance(e, (ast.List, ast.Tuple, ast.Set)):
            vals = [self.expr(x, env) for x in e.elts]
            return vals if isinstance(e, ast.List) else tuple(vals) if isinstance(e, ast.Tuple) else set(vals)
        if isinstance(e, ast.Dict):
            if any(k is None for k in e.keys):
                self.fail(e, 'dict unpacking is not supported')
            return {self.expr(k, env): self.expr(v, env) for k, v in zip(e.keys, e.values)}
        if isinstance(e, ast.Subscript):
            return self.expr(e.value, env)[self.expr(e.slice, env)]
        if isinstance(e, ast.Slice):
            return slice(*(self.expr(x, env) if x is not None else None for x in (e.lower, e.upper, e.step)))
        if isinstance(e, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            out = []
            self.comprehension(e, env, e.generators, lambda sc: out.append(self.expr(e.elt, sc)))
            return set(out) if isinstance(e, ast.SetComp) else out
        if isinstance(e, ast.DictComp):
            out = {}
            self.comprehension(e, env, e.generators, lambda sc: out.__setitem__(self.expr(e.key, sc), self.expr(e.value, sc)))
            return out
        if isinstance(e, ast.Attribute):
            obj = self.expr(e.value, env)
            if obj is math and not e.attr.startswith('_'):
                return getattr(math, e.attr)
            if isinstance(obj, (list, dict)) and e.attr in SAFE_METHODS:
                return getattr(obj, e.attr)
            self.fail(e, 'attribute %r is not available (math.* and list/dict methods only)' % e.attr)
        if isinstance(e, ast.Call):
            fn = self.expr(e.func, env)
            if not callable(fn):
                self.fail(e, 'not a function')
            args = []
            for a in e.args:
                if isinstance(a, ast.Starred):
                    args.extend(self.expr(a.value, env))
                else:
                    args.append(self.expr(a, env))
            kw = {}
            for k in e.keywords:
                if k.arg is None:
                    self.fail(e, '**keyword unpacking is not supported')
                kw[k.arg] = self.expr(k.value, env)
            if fn is range and (len(range(*args)) > 1000000):
                self.fail(e, 'range larger than 1,000,000')
            return fn(*args, **kw)
        self.fail(e, '%s is not supported in a builder script' % type(e).__name__)


class _Scope(dict):
    """A function's local names, falling back to the module names."""
    def __init__(self, local, outer):
        super().__init__(local)
        self.outer = outer

    def __contains__(self, k):
        return dict.__contains__(self, k) or k in self.outer

    def __getitem__(self, k):
        if dict.__contains__(self, k):
            return dict.__getitem__(self, k)
        return self.outer[k]


def write_obj(meshes, path):
    """meshkit meshes -> OBJ text (usemtl <role>, s 1/off) in meshkit axes."""
    lines = ['# hermes64 styleengine mesh (meshkit axes: +Z up, metres)']
    base = 1
    tris = 0
    for m in meshes:
        for v in m.v:
            if not all(math.isfinite(c) and abs(c) <= 1000 for c in v):
                raise ScriptError('coordinates must be finite and within 1000 m')
            lines.append('v %.6f %.6f %.6f' % tuple(v))
        cur = None
        for f, r, s in zip(m.f, m.r, m.s):
            key = (r, bool(s))
            if key != cur:
                lines += ['usemtl ' + r, 's ' + ('1' if s else 'off')]
                cur = key
            lines.append('f ' + ' '.join(str(base + i) for i in f))
            tris += len(f) - 2
        base += len(m.v)
    raw = ('\n'.join(lines) + '\n').encode('utf-8')
    Path(path).write_bytes(raw)
    allv = [v for m in meshes for v in m.v]
    lo = [min(v[i] for v in allv) for i in range(3)] if allv else [0, 0, 0]
    hi = [max(v[i] for v in allv) for i in range(3)] if allv else [0, 0, 0]
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'triangles': tris,
            'vertices': base - 1, 'bounds_m': [round(lo[i], 4) for i in range(3)] + [round(hi[i], 4) for i in range(3)]}


def run_script(req):
    from core.gen_recipe import ROLES, RAW_TRIANGLES
    src = Path(req['script']).read_text(encoding='utf-8')
    tree = check_script(src)
    names, out = api(ROLES)
    try:
        Interpreter(names).run(tree)              # no exec: the script is evaluated node by node (see Interpreter)
    except (_Break, _Continue, _Return) as e:
        raise ScriptError('%s outside a loop or function' % type(e).__name__.strip('_').lower())
    except ScriptError:
        raise
    except (ArithmeticError, LookupError, TypeError, ValueError) as e:
        raise ScriptError('the script failed: %s: %s' % (type(e).__name__, e))
    if not out:
        raise ScriptError('the script emitted nothing: call emit(part, ...)')
    meshes = [p.mesh for p in out]
    tris = sum(m.tri_count() for m in meshes)
    if tris > RAW_TRIANGLES:
        raise ScriptError('%d raw triangles > %d' % (tris, RAW_TRIANGLES))
    rec = write_obj(meshes, req['out'])
    # STYLEENGINE-2: one node per named group; ungrouped parts merged by kind (closed solids / open shells / cards),
    # so an open sail or a card leaf never fails the closed-solid check of a solid node
    buckets = {}
    for p in out:
        if p.group:
            key = 'group:' + p.group
        else:
            key = 'card' if p.kind == 'card' else ('solid' if _mesh_closed(p.mesh) else 'shell')
        buckets.setdefault(key, []).append(p)
    files = []
    for key in sorted(buckets, key=lambda k: (k.startswith('group:'), k)):
        ps = buckets[key]
        if key.startswith('group:'):
            kind = 'card' if all(p.kind == 'card' for p in ps) else (
                'solid' if all(_mesh_closed(p.mesh) for p in ps if p.kind != 'card') and not any(
                    p.kind == 'card' for p in ps) else 'shell')
        else:
            kind = key
        name = 'out_%d.obj' % len(files)
        files.append(dict(write_obj([p.mesh for p in ps], Path(req['out']).parent / name), file=name, kind=kind,
                          group=key[6:] if key.startswith('group:') else None))
    rec['parts'] = files[:MAX_FILE_PARTS]
    return rec


def _mesh_closed(m):
    """Every edge (positions welded to 1e-6 m) is used by exactly two faces."""
    key, count = {}, {}
    weld = [key.setdefault(tuple(round(c, 6) for c in v), len(key)) for v in m.v]
    for f in m.f:
        for i in range(len(f)):
            a, b = weld[f[i]], weld[f[(i + 1) % len(f)]]
            if a == b:
                continue
            e = (min(a, b), max(a, b))
            count[e] = count.get(e, 0) + 1
    return bool(count) and all(n == 2 for n in count.values())


# --------------------------------------------------------------------------------------------- file -> mesh
def _decode_image(raw):
    import numpy as np
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(raw)) as im:
            return np.asarray(im.convert('RGB'), dtype=np.uint8)
    except ImportError:
        from core import png
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png') as f:
            f.write(raw)
            f.flush()
            return png.read(f.name)[..., :3]


def _role_colours(pack):
    out = {}
    for role, m in pack['materials'].items():
        t = m.get('texture') if isinstance(m, dict) else None
        names = (t or {}).get('ramp') or ([m['tint']] if isinstance(m, dict) and m.get('tint') else [])
        pal = dict(zip(pack['palette_names'], pack['palette']))
        cols = [pal[n] for n in names if n in pal]
        if cols:
            out[role] = [sum(int(c[i:i + 2], 16) for c in cols) / len(cols) for i in (1, 3, 5)]
    return out


def _closed(V, F, remap):
    """Every edge (after welding positions to 1e-6 m) used by exactly two faces."""
    import numpy as np
    key = {}
    weld = [key.setdefault(tuple(np.round(p, 6).tolist()), len(key)) for p in V]
    count = {}
    for f in F.tolist():
        a, b, c = (weld[remap[int(x)]] for x in f)
        for e in ((a, b), (b, c), (c, a)):
            e = (min(e), max(e))
            count[e] = count.get(e, 0) + 1
    return bool(count) and all(n == 2 for n in count.values())


def mesh_from_file(req):
    """GLB/OBJ (+ textures) -> role-mapped OBJ. Returns numbers for the report."""
    import numpy as np
    from core import conform as C
    from core.meshkit import Mesh
    pack = json.loads(Path(req['pack']).read_text(encoding='utf-8'))
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in pack['palette']], dtype=np.float64)
    colours = _role_colours(pack)
    cands = [r for r in req.get('candidates') or colours if r in colours]
    names = np.array(cands)
    rc = np.array([colours[r] for r in cands], dtype=np.float64)
    wts = np.array([3.0, 4.0, 2.0])

    def nearest_roles(cols):
        d = (((cols[:, None, :] - rc[None, :, :]) ** 2) * wts).sum(-1)
        return names[d.argmin(1)]
    src = Path(req['source'])
    texture_rec = []
    if src.suffix.lower() == '.obj':
        V, F = [], []
        for line in src.read_text(encoding='utf-8', errors='replace').splitlines():
            p = line.split()
            if p and p[0] == 'v' and len(p) >= 4:
                V.append([float(x) for x in p[1:4]])
            elif p and p[0] == 'f' and len(p) >= 4:
                idx = [int(x.split('/')[0]) for x in p[1:]]
                idx = [(i - 1) if i > 0 else len(V) + i for i in idx]
                for k in range(1, len(idx) - 1):
                    F.append([idx[0], idx[k], idx[k + 1]])
        V = np.array(V, dtype=np.float64).reshape(-1, 3)
        F = np.array(F, dtype=np.int64).reshape(-1, 3)
        face_rgb = np.tile(np.array(req.get('colour') or [160, 160, 160], dtype=np.float64), (len(F), 1))
        part = np.zeros(len(F), np.int64)
        node_names = ['']
        if req.get('textures'):
            texture_rec.append({'note': 'OBJ texture coordinates are not read in M1; the brief colour or grey is used'})
        yup = bool(req.get('y_up', True))
    else:
        from validate.glb import GLB
        g = GLB(path=str(src))
        Vs, Fs, cols, parts, node_names = [], [], [], [], []
        base = 0
        tex_cache = {}
        for pi, ni in enumerate(g.mesh_nodes()):
            geo = g.node_geometry(ni, world=True)
            pos, idx, uv, mat = geo['pos'], geo['idx'], geo['uv'], geo['mat']
            Vs.append(pos)
            Fs.append(idx + base)
            parts.append(np.full(len(idx), min(pi, MAX_FILE_PARTS - 1), np.int64))   # one recipe node per GLB node
            if pi < MAX_FILE_PARTS:
                node_names.append(str(g.nodes[ni].get('name', '')))
            base += len(pos)
            fc = np.zeros((len(idx), 3))
            for mi in np.unique(mat):
                sel = mat == mi
                m = g.materials[int(mi)] if 0 <= int(mi) < len(g.materials) else {}
                own = ((m.get('extras') or {}).get('n64') or {}).get('role')
                if own in colours:          # a house GLB already names its pack role: keep it, no colour guess
                    fc[sel] = colours[own]
                    continue
                pbr = m.get('pbrMetallicRoughness', {})
                factor = np.array(pbr.get('baseColorFactor', [1, 1, 1, 1])[:3], dtype=np.float64)
                srgb = np.where(factor <= 0.0031308, factor * 12.92, 1.055 * np.power(factor, 1 / 2.4) - 0.055) * 255
                ti = (pbr.get('baseColorTexture') or {}).get('index')
                if ti is not None and 'textures' in g.json and ti < len(g.json['textures']):
                    img_i = g.json['textures'][ti].get('source')
                    if img_i not in tex_cache:
                        rgb = _decode_image(g.image_bytes(img_i))
                        conf, rec = C.conform_texture(rgb, pal, size=int(req.get('texture_size', 64)),
                                                      dither=float(req.get('dither', 1.0)), pattern=req.get('pattern', 'mottle'))
                        tex_cache[img_i] = conf
                        texture_rec.append(dict(rec, image=int(img_i), source_size=list(rgb.shape[:2])))
                    conf = tex_cache[img_i]
                    n = conf.shape[0]
                    c_uv = uv[idx[sel]].mean(1)
                    px = np.clip((c_uv[:, 0] % 1.0) * n, 0, n - 1).astype(int)
                    py = np.clip((c_uv[:, 1] % 1.0) * n, 0, n - 1).astype(int)
                    fc[sel] = conf[py, px].astype(np.float64) * (srgb / 255.0)
                else:
                    fc[sel] = srgb
            cols.append(fc)
        V = np.concatenate(Vs) if Vs else np.zeros((0, 3))
        F = np.concatenate(Fs) if Fs else np.zeros((0, 3), np.int64)
        face_rgb = np.concatenate(cols) if cols else np.zeros((0, 3))
        part = np.concatenate(parts) if parts else np.zeros(0, np.int64)
        yup = True
    if not len(F):
        raise ScriptError('no triangles in the file')
    if yup:                                     # glTF/OBJ +Y up -> meshkit +Z up, front -Y
        V = np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)
    lo, hi = V.min(0), V.max(0)
    size = float((hi - lo).max())
    want = req.get('size_m')
    k = 1.0
    if want:
        k = float(want) / max(size, 1e-9)
    elif req.get('class_range'):
        a, b = req['class_range']
        if size > b or size < a:
            k = (min(max(size, a), b) * (0.95 if size > b else 1.05)) / max(size, 1e-9)
    V = (V - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])) * k
    roles = nearest_roles(face_rgb)
    used, counts = np.unique(roles, return_counts=True)
    keep = set(used[np.argsort(-counts)][:8].tolist())
    if len(used) > 8:                           # at most 8 roles: the rest take their nearest kept role
        kept = [r for r in cands if r in keep]
        kc = np.array([colours[r] for r in kept])
        far = ~np.isin(roles, list(keep))
        d = (((face_rgb[far][:, None, :] - kc[None, :, :]) ** 2) * wts).sum(-1)
        roles[far] = np.array(kept)[d.argmin(1)]
    out_dir = Path(req['out']).parent
    files = []
    for pi in sorted(set(part.tolist())):           # each source node stays its own part (topology is per node)
        sel = np.nonzero(part == pi)[0]
        used = np.unique(F[sel])
        remap = {int(v): i for i, v in enumerate(used.tolist())}
        m = Mesh()
        m.v = [tuple(p) for p in V[used].tolist()]
        for fi in sel[np.argsort(roles[sel], kind='stable')].tolist():
            m.f.append(tuple(remap[int(x)] for x in F[fi]))
            m.r.append(str(roles[fi]))
            m.s.append(True)
            m.uv.append(None)
        name = 'out_%d.obj' % len(files)
        src_name = node_names[pi] if pi < len(node_names) else ''
        kind = 'card' if src_name.startswith('kit_card_') else 'shell' if src_name.startswith('kit_shell_') else \
            ('solid' if _closed(V[used], F[sel], remap) else 'shell')
        files.append(dict(write_obj([m], out_dir / name), file=name, kind=kind))
    rec = {'parts': files, 'triangles': sum(f['triangles'] for f in files), 'sha256': files[0]['sha256']}
    rec.update(scale=round(k, 6), source_size_m=round(size, 4), size_m=round(size * k, 4), textures=texture_rec,
               roles={r: int(c) for r, c in zip(*np.unique(roles, return_counts=True))},
               source_triangles=int(len(F)))
    return rec


def main(argv):
    req = json.loads(Path(argv[0]).read_text(encoding='utf-8'))
    out = {'ok': False}
    try:
        out = dict(run_script(req) if req['mode'] == 'script' else mesh_from_file(req), ok=True)
    except ScriptError as e:
        out = {'ok': False, 'error': str(e)[:600]}
    except Exception as e:      # the sandboxed child reports every failure as data, never a traceback dump
        out = {'ok': False, 'error': ('%s: %s' % (type(e).__name__, e))[:600]}
    Path(req['result']).write_text(json.dumps(out, sort_keys=True), encoding='utf-8')
    return 0 if out.get('ok') else 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
