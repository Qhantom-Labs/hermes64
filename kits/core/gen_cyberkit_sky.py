"""CYBERKIT skyline silhouette cards, holo-line dressing and static aircraft. No traced/reference geometry."""
import math
from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .rng import rng
from .gen_cyberkit_tower import slot_rect, gem
from .gen_cyberkit_room import done

V='1.0.0'
SLOT=S.enum('a',list(C.SLOTS))


def skyline(P,seed,kind):
    r=rng(seed,'cyber-sky-'+kind)
    w,h=P['width'],P['height'];count=8
    m=K.Mesh();role='vista_far' if kind=='far' else 'vista'
    for k in range(count):
        x0=-w/2+w*k/count;x1=-w/2+w*(k+1)/count
        hh=h*(0.4+0.6*r.random())
        shoulder=0.16*(x1-x0)
        if kind=='needle':
            top=[(x0,hh*0.72),(x0+shoulder,hh*0.72),((x0+x1)/2,hh),(x1-shoulder,hh*0.72),(x1,hh*0.72)]
        elif kind=='stepped':
            top=[(x0,hh*0.7),(x0+shoulder,hh*0.7),(x0+shoulder,hh),(x1-shoulder,hh),(x1-shoulder,hh*0.85),(x1,hh*0.85)]
        elif kind=='arch':
            top=[(x0,hh*0.8),(x0+shoulder,hh),(x1-shoulder,hh),(x1,hh*0.8)]
        else:
            top=[(x0,hh*0.9),(x0+shoulder,hh),(x1-shoulder,hh),(x1,hh*0.9)]
        drop=P.get('base_drop',12.0)
        pts=[(x0,0,-drop),(x1,0,-drop)]+[(x,0,z) for x,z in reversed(top)]
        uv=('n',[(0.5+x/w,z/h) for x,y,z in pts])
        # Fan around an interior bottom point yields a convex painted tower with a bevelled/stepped crown.
        m.add(pts,[tuple(range(len(pts)))],role,False,[uv])
    return C.finish([Node('skyline',m,'card')],C.grid_meta('free',None,[],layer=kind,backdrop=True),ground=False)


def register_skyline(kind,description):
    @register('cysky.'+kind,V,'sky',{'width':S.num(56,24,80),'height':S.num(24,12,36),'base_drop':S.num(12,0,24,'painted skyline continuing below a roof deck')},description,origin='terrain_center')
    def build(P,seed):
        return skyline(P,seed,kind)
    return build


near=register_skyline('near','Near skyline card: eight original chamfer-crown silhouettes, painted windows.')
far=register_skyline('far','Far skyline card in haze-role values for a distinct city depth layer.')
needle=register_skyline('needle','Skyline card of varied needle silhouettes, not a single flat rectangle.')
stepped=register_skyline('stepped','Stepped residential skyline layer with uneven parapet rhythm.')
arch=register_skyline('arch','Bevelled-crown skyline card for the megastructure horizon.')


@register('cysky.corner',V,'sky',{},'Two perpendicular skyline cards closing a distant city corner.',origin='terrain_center')
def corner(P,seed):
    a=skyline({'width':32,'height':18},seed,'near').nodes[0].mesh
    b=skyline({'width':32,'height':23},seed+7,'far').nodes[0].mesh
    a.translate(-16,16,0);b.rotate_z(math.pi/2).translate(0,0,0)
    return C.finish([Node('skyline_a',a,'card'),Node('skyline_b',b,'card')],C.grid_meta('free',None,[],backdrop=True),ground=False)


@register('cysky.megatower',V,'structure',{'accent':SLOT},'Distant megatower: octagonal taper and offset observation halo, a skyline anchor.',origin='floor_center')
def megatower(P,seed):
    m=C.lathe_at(0,0,0,[(7,0),(6.2,14),(4.8,38),(3,45),(0.15,55)],8,'wall_alt',smooth=False)
    q=C.ring(0,0,40,6,0.12,12,4,'trim')
    q.merge(gem(0,0,55,0.3,P['accent']))
    m.apply(lambda a: a * 0.65)
    q.apply(lambda a: a * 0.65)
    return C.finish([Node('body',m,'solid'),Node('beacons',q,'solid')],C.grid_meta('free'))


@register('cysky.hololine',V,'sky',{'length':S.num(24,8,48),'accent':SLOT},'Single subdued holographic line card linking skyline nodes.',origin='terrain_center')
def hololine(P,seed):
    m=C.strip((-P['length']/2,0,0),(P['length']/2,0,1.2),0.055,'light',(0,-1,0),slot_rect(P['accent']))
    return C.finish([Node('line',m,'card')],C.grid_meta('free',None,[],holo=True),ground=False)


@register('cysky.network',V,'sky',{'accent':SLOT},'Sparse original holo network card: six points joined by a broken diagonal rhythm.',origin='terrain_center')
def network(P,seed):
    pts=[(-18,0,2),(-10,0,9),(-2,0,6),(7,0,15),(15,0,10),(20,0,18)]
    m=K.Mesh()
    for a,b in zip(pts,pts[1:]):
        m.merge(C.strip(a,b,0.05,'light',(0,-1,0),slot_rect(P['accent'])))
    return C.finish([Node('network',m,'card')],C.grid_meta('free',None,[],holo=True),ground=False)


@register('cysky.halocard',V,'sky',{'accent':SLOT},'Broken projected halo sign made of sparse line cards, no logo or real glyph.',origin='terrain_center')
def halocard(P,seed):
    m=K.Mesh()
    for k in range(10):
        a=k*K.TAU/12;b=(k+0.78)*K.TAU/12
        m.merge(C.strip((3*math.cos(a),0,3+3*math.sin(a)),(3*math.cos(b),0,3+3*math.sin(b)),0.1,'light',(0,-1,0),slot_rect(P['accent'])))
    return C.finish([Node('projection',m,'card')],C.grid_meta('free',None,[],holo=True),ground=False)


def aircraft(P,seed,kind):
    # Distinct loft profiles: delta courier, broad cargo lifter, compact shuttle, cigar airship.
    if kind=='airship':
        m=C.lathe_at(0,0,0,[(0,0),(0.8,0.8),(1.2,2.5),(1.0,5),(0,6.5)],10,'hull',smooth=True)
        m.rotate_x(math.pi/2).translate(0,3.25,1.0)
        m.merge(C.taper(0,0,0,0.7,0.8,2,0.6,1.5,0.1,0.08,'body_alt'))
    else:
        w={'courier':2.7,'cargo':3.6,'shuttle':1.8}[kind]
        l={'courier':3.4,'cargo':4.8,'shuttle':3.5}[kind]
        rings=[]
        for y,sc,h in ((-l/2,0.12,0.3),(-l/4,0.55,0.7),(l/4,1,0.65),(l/2,0.65,0.35)):
            rings.append([(-w*sc/2,y,0),(w*sc/2,y,0),(w*sc*0.32,y,h),(-w*sc*0.32,y,h)])
        m=K.loft(rings,'hull',smooth=False)
        if kind=='cargo':
            for x in (-1.5,1.5):
                m.merge(C.taper(x,0,-0.25,0.6,0.65,3.2,0.55,2.8,0.12,0.1,'body_alt'))
    q=gem(0,0,0.8,0.08,P['accent'],'bright')
    return C.finish([Node('body',m,'solid'),Node('beacons',q,'solid')],C.grid_meta('free'))


def register_aircraft(kind,description):
    @register('cysky.'+kind,V,'vehicle',{'accent':SLOT},description,origin='floor_center')
    def build(P,seed):
        return aircraft(P,seed,kind)
    return build


courier=register_aircraft('courier','Static delta courier aircraft: swept lofted hull, small navigation beacon.')
cargo=register_aircraft('cargo','Static cargo lifter with broad hull and underslung twin engine nacelles.')
shuttle=register_aircraft('shuttle','Static compact city shuttle with a narrow swept hull.')
airship=register_aircraft('airship','Static advertising airship with a cigar envelope and small gondola; no real brands.')
