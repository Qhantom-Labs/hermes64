"""Numpy triangle-intersection fallback for the kit topology gate.

Matches the existing BVH policy: same welded island only, pairs sharing any
vertex excluded. Broad-phase AABB pruning; coplanar overlap is tested in 2D.
"""
import numpy as np
from core.triangulate import cross


def triangles_intersect(a, b, eps=1e-8):
    na = np.cross(a[1]-a[0],a[2]-a[0])
    nb = np.cross(b[1]-b[0],b[2]-b[0])
    la,lb = np.linalg.norm(na),np.linalg.norm(nb)
    if la < 1e-15 or lb < 1e-15:
        return False  # degenerate gate reports this separately
    na,nb = na/la,nb/lb
    da,db = (b-a[0])@na,(a-b[0])@nb
    if np.all(da>eps) or np.all(da<-eps) or np.all(db>eps) or np.all(db<-eps):
        return False
    if np.max(np.abs(da)) < eps and np.max(np.abs(db)) < eps:
        axes = [i for i in range(3) if i!=int(np.argmax(np.abs(na)))]
        aa,bb = a[:,axes],b[:,axes]
        # Clip the triangles and require positive area. Edge/point-only
        # contact (including T junctions) is not a BVH self-intersection.
        poly = list(aa)
        sign = 1 if cross(bb[0],bb[1],bb[2]) >= 0 else -1
        for j in range(3):
            clipped = []
            for k,p in enumerate(poly):
                q = poly[(k+1)%len(poly)]
                dp = sign*cross(bb[j],bb[(j+1)%3],p)
                dq = sign*cross(bb[j],bb[(j+1)%3],q)
                if dp >= 0:
                    clipped.append(p)
                if (dp < 0) != (dq < 0):
                    clipped.append(p+(q-p)*(dp/(dp-dq)))
            poly = clipped
            if len(poly) < 3:
                return False
        area2 = abs(sum(cross(poly[0],poly[k],poly[k+1]) for k in range(1,len(poly)-1)))
        return area2 > eps*eps
    # Both planes must cut the other triangle's interior. A triangle edge
    # merely resting on another face is contact, not a BVH intersection.
    if min(da) >= -eps or max(da) <= eps or min(db) >= -eps or max(db) <= eps:
        return False
    def edges_hit(t, u, normal):
        for i in range(3):
            p,q = t[i],t[(i+1)%3]
            d0,d1 = float(np.dot(p-u[0],normal)),float(np.dot(q-u[0],normal))
            if (d0>eps and d1>eps) or (d0<-eps and d1<-eps) or abs(d0-d1)<1e-15:
                continue
            x = p+(q-p)*(d0/(d0-d1))
            signs = [float(np.dot(np.cross(u[(j+1)%3]-u[j],x-u[j]),normal)) for j in range(3)]
            if min(signs)>=-eps:
                return True
        return False
    return edges_hit(a,b,nb) or edges_hit(b,a,na)


def count_intersections(points, triangles, islands):
    coords = points[triangles]
    lo,hi = coords.min(1),coords.max(1)
    count = 0
    for i in range(len(triangles)):
        candidates = np.nonzero(np.all(hi[i]+1e-8>=lo[i+1:],axis=1)&np.all(hi[i+1:]+1e-8>=lo[i],axis=1))[0]+i+1
        for j in candidates:
            if islands[i]!=islands[j] or any(v in triangles[j] for v in triangles[i]):
                continue
            if triangles_intersect(coords[i],coords[j]):
                count += 1
    return count
