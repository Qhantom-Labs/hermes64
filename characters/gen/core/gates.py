"""Independent numeric gates. No claim that a number proves art quality."""
import math,hashlib,json


def digest(v):return hashlib.sha256(json.dumps(v,separators=(',',':'),sort_keys=True).encode()).hexdigest()

def dist(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

# STEER-5 §5 (Main's decision): body mesh incl. hair/clothing < 700 tris (humanoid), <= 300 (animal); every held/worn
# prop is its own node with its own budget <= 200 tris
BODY_BUDGET_HUMAN=700   # strict: tris < 700
BODY_BUDGET_ANIMAL=300  # tris <= 300
PROP_BUDGET=200         # tris <= 200 per prop node

def body_over_budget(kind,tris):
    return tris>=BODY_BUDGET_HUMAN if kind=='human' else tris>BODY_BUDGET_ANIMAL

def prop(m):
    """Held/worn prop mesh gate: own budget, finite, no zero-area faces."""
    errors=[]
    if len(m.faces)>PROP_BUDGET:errors.append('prop_over_budget')
    if any(not math.isfinite(c) for v in m.vertices for c in v):errors.append('nonfinite')
    for f in m.faces:
        a,b,c=(m.vertices[i] for i in f);u=[b[k]-a[k] for k in range(3)];w=[c[k]-a[k] for k in range(3)]
        cr=(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0])
        if math.sqrt(sum(x*x for x in cr))<1e-12:errors.append('zero_area');break
    return {'pass':not errors,'errors':errors,'tris':len(m.faces)}

def mesh(a):
    errors=[]
    if body_over_budget(a.kind,len(a.faces)):errors.append('over_budget')
    if len(a.bones)!=16:errors.append('bone_count')
    if any(not math.isfinite(c) for v in a.vertices for c in v):errors.append('nonfinite')
    if abs(min(v[2] for v in a.vertices))>.01:errors.append('floor_origin')
    if any(abs(sum(w.values())-1)>1e-6 or any(n not in a.bones or v<0 for n,v in w.items()) for w in a.weights):errors.append('invalid_skin')
    edges={};zero=0;volume=0
    for f in a.faces:
        p,q,r=[a.vertices[i] for i in f];u=[q[j]-p[j] for j in range(3)];v=[r[j]-p[j] for j in range(3)]
        c=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(x*x for x in c)<1e-14:zero+=1
        for j in range(3):
            x,y=f[j],f[(j+1)%3];key=tuple(sorted((x,y)));edges.setdefault(key,[]).append(x<y)
    if zero:errors.append('zero_area')
    if any(len(ds)!=2 or sum(ds)!=1 for ds in edges.values()):errors.append('open_or_inconsistent_winding')
    # Closed overlapping clothing islands are deliberate; this gate does not prohibit inter-island overlap.
    return {'pass':not errors,'errors':errors,'tris':len(a.faces),'vertices':len(a.vertices),'edges':len(edges),
      'topology_sha256':digest(a.faces),'uv_sha256':digest(a.uv),'skin_sha256':digest(a.weights),'geometry_sha256':digest(a.vertices)}

def deformation(rest,posed,faces):
    edges={tuple(sorted((f[j],f[(j+1)%3]))) for f in faces for j in range(3)}
    ratios=[dist(posed[x],posed[y])/dist(rest[x],rest[y]) for x,y in edges]
    lo,hi=min(ratios),max(ratios);errors=[]
    if lo<.45 or hi>1.8:errors.append('edge_stretch')
    if any(not math.isfinite(c) for v in posed for c in v):errors.append('nonfinite_pose')
    return {'pass':not errors,'errors':errors,'edge_ratio_min':lo,'edge_ratio_max':hi,'limits':[.45,1.8]}

def palette(pixels,allowed):
    have={tuple(int(c) for c in p) for p in pixels};pal={tuple(int(c) for c in p) for p in allowed}
    bad=sorted(have-pal)
    return {'pass':not bad,'errors':['off_palette'] if bad else [],'unique':len(have),'outside':bad[:12]}
