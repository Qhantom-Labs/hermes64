"""Deterministic ear clipping, with visibility bridges for disjoint interior holes.

Returns indices into the original flattened rings, CCW. Invalid/crossing outlines
fail closed, never return a partial mesh. Standard library only.
"""
import math

EPS = 1e-12


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def area(points):
    return sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(points, points[1:]+points[:1])) / 2


def inside(p, ring):
    hit = False
    for a, b in zip(ring, ring[1:]+ring[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                hit = not hit
    return hit


def intersects(a, b, c, d):
    # Closed segments, including collinear overlap and endpoint contact.
    def on(p, q, r):
        return (abs(cross(p, q, r)) <= EPS and
                min(p[0], q[0])-EPS <= r[0] <= max(p[0], q[0])+EPS and
                min(p[1], q[1])-EPS <= r[1] <= max(p[1], q[1])+EPS)
    x, y, z, w = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
    return ((x*y < -EPS and z*w < -EPS) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b))


def triangulate(outer, holes=()):
    loops = [[tuple(float(v) for v in p) for p in loop] for loop in [outer]+list(holes)]
    for loop in loops:
        if len(loop) < 3 or abs(area(loop)) <= EPS or any(not math.isfinite(v) for p in loop for v in p):
            raise ValueError('invalid polygon: short, nonfinite or zero area')
        for i in range(len(loop)):
            for j in range(i+1, len(loop)):
                if j == i+1 or (i == 0 and j == len(loop)-1):
                    continue
                if intersects(loop[i], loop[(i+1)%len(loop)], loop[j], loop[(j+1)%len(loop)]):
                    raise ValueError('invalid polygon: crossing edges')
    pts = [p for loop in loops for p in loop]
    rings = []
    offset = 0
    for n, loop in enumerate(loops):
        ids = list(range(offset, offset+len(loop)))
        if (area(loop) > 0) != (n == 0):
            ids.reverse()
        rings.append(ids)
        offset += len(loop)
    # Reject touching/outside/nested holes before making weakly-simple bridges.
    for n, hole in enumerate(loops[1:], 1):
        if not inside(hole[0], loops[0]) or any(inside(hole[0], h) for h in loops[1:n]):
            raise ValueError('invalid polygon hole')
        for other in loops[:n]:
            if any(intersects(a,b,c,d) for a,b in zip(hole,hole[1:]+hole[:1])
                   for c,d in zip(other,other[1:]+other[:1])):
                raise ValueError('invalid polygon: touching holes')
    path = rings[0][:]
    for hole in rings[1:]:
        candidates = []
        for hi, h in enumerate(hole):
            for oi, o in enumerate(path):
                a, b = pts[h], pts[o]
                mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                if not inside(mid, loops[0]) or any(inside(mid, r) for r in loops[1:]):
                    continue
                visible = True
                for ring in rings + [path]:
                    for c, d in zip(ring, ring[1:]+ring[:1]):
                        if h in (c,d) or o in (c,d):
                            continue
                        if intersects(a,b,pts[c],pts[d]):
                            visible = False
                            break
                    if not visible:
                        break
                if visible:
                    candidates.append(((a[0]-b[0])**2+(a[1]-b[1])**2, oi, hi))
        if not candidates:
            raise ValueError('cannot bridge polygon hole')
        _, oi, hi = min(candidates)
        path = path[:oi+1] + hole[hi:] + hole[:hi+1] + [path[oi]] + path[oi+1:]
    tris = []
    while len(path) > 3:
        found = False
        # Start at corner 1: convex quad uses Blender's usual 0-2 diagonal.
        for k in list(range(1,len(path))) + [0]:
            a, b, c = path[k-1], path[k], path[(k+1)%len(path)]
            pa,pb,pc = pts[a],pts[b],pts[c]
            if cross(pa,pb,pc) <= EPS:
                continue
            if any(pts[o] not in (pa,pb,pc) and cross(pa,pb,pts[o]) >= -EPS and
                   cross(pb,pc,pts[o]) >= -EPS and cross(pc,pa,pts[o]) >= -EPS for o in path):
                continue
            tris.append((a,b,c))
            path.pop(k)
            found = True
            break
        if not found:
            raise ValueError('cannot triangulate polygon (degenerate or crossing)')
    if cross(*(pts[i] for i in path)) <= EPS:
        raise ValueError('degenerate final polygon triangle')
    tris.append(tuple(path))
    return tris


def polygon3d(points):
    """Project along dominant Newell normal; preserve input winding."""
    n = [0.,0.,0.]
    for a,b in zip(points, points[1:]+points[:1]):
        n[0] += (a[1]-b[1])*(a[2]+b[2])
        n[1] += (a[2]-b[2])*(a[0]+b[0])
        n[2] += (a[0]-b[0])*(a[1]+b[1])
    axis = max(range(3), key=lambda i: abs(n[i]))
    axes = [i for i in range(3) if i != axis]
    p = [(a[axes[0]],a[axes[1]]) for a in points]
    reverse = area(p) < 0
    triangles = triangulate(p)
    return [(a,c,b) if reverse else (a,b,c) for a,b,c in triangles]
