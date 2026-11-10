"""Nature-free CYBERKIT street dressing. Small recognisable silhouettes, no real brands or text."""
import math
from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .gen_cyberkit_tower import slot_rect
from .gen_cyberkit_room import done

V='1.0.0'


@register('cydress.bin',V,'furniture',{},'Octagonal street bin with domed lid and inset waste slot.',origin='floor_center')
def bin_(P,seed):
    m=C.lathe_at(0,0,0,[(0.32,0),(0.38,0.12),(0.38,0.85),(0.31,1.02),(0,1.07)],8,'body',smooth=False)
    q=C.face_card(0,-0.385,0.66,0.35,0.16,'opening')
    return done(m,q)


@register('cydress.bench',V,'furniture',{},'Tapered cantilever street bench with a sloped back and painted metal slats.',origin='floor_center')
def bench(P,seed):
    m=C.slab(0,0,0.43,2.4,0.6,0.12,'wood',c=0.08)
    for x in (-0.85,0.85):
        m.merge(C.taper(x,0,0,0.45,0.4,0.65,0.22,0.4,0.06,0.04,'trim'))
    m.merge(C.taper(0,0.27,0.5,1.0,2.4,0.14,2.25,0.12,0.04,0.03,'wood'))
    return done(m)


@register('cydress.crates',V,'furniture',{},'Stacked chamfered delivery cases with straps and inset panel faces.',origin='floor_center')
def crates(P,seed):
    m=C.slab(-0.27,0,0,1.1,0.8,0.65,'body_alt',c=0.1)
    m.merge(C.slab(0.28,0.10,0.63,0.7,0.65,0.52,'body',c=0.09))
    m.merge(C.slab(-0.27,-0.41,0.07,0.12,0.03,0.5,'band',c=0.01))
    return done(m)


@register('cydress.barrel',V,'furniture',{},'Hexagonal industrial drum with rolled rims and a recessed top.',origin='floor_center')
def barrel(P,seed):
    return done(C.lathe_at(0,0,0,[(0.35,0),(0.41,0.07),(0.38,0.12),(0.38,0.85),(0.41,0.9),(0.4,0.98),(0.32,0.98),(0.32,0.93),(0,0.93)],8,'body',smooth=False))


@register('cydress.cart',V,'furniture',{},'Delivery trolley with tapered cargo case, handles and two low-poly wheels.',origin='floor_center')
def cart(P,seed):
    m=C.slab(0,0,0.18,0.8,0.7,0.12,'metal',c=0.06)
    m.merge(C.slab(0,0,0.30,0.72,0.6,0.75,'body_alt',c=0.1))
    for x in (-0.42,0.42):
        wheel=C.cyl(0,0,0,0.14,0.12,8,'rope').rotate_y(math.pi/2).translate(x,0.2,0.15)
        m.merge(wheel)
        m.merge(C.rod((x,0.33,0.31),(x,0.33,1.3),0.035,4,'metal'))
    m.merge(C.rod((-0.42,0.32,1.3),(0.42,0.32,1.3),0.035,4,'metal'))
    return done(m)


@register('cydress.awning',V,'furniture_large',{'accent':S.enum('b',list(C.SLOTS))},'Folded shop awning with scalloped painted valance and two thin braces.',origin='opening')
def awning(P,seed):
    m=C.wedge(0,-0.6,0.4,3.5,1.2,0.08,0.6,'fabric',c=0.05)
    for x in (-1.5,1.5):
        m.merge(C.rod((x,0,0),(x,-1.1,0.4),0.04,4,'post'))
    return C.finish([Node('awning',m,'solid')],C.grid_meta('wall_face',None,[C.sock('wall_mount',(0,0,0),'n')]),cy=False)


@register('cydress.shutter',V,'furniture_large',{},'Recessed roll shutter in a chamfered steel portal.',origin='opening')
def shutter(P,seed):
    m=K.Mesh()
    for x in (-1.7,1.7):
        m.merge(C.slab(x,0,0,0.2,0.3,3.5,'frame',c=0.04))
    m.merge(C.slab(0,0,3.4,3.6,0.4,0.3,'frame',c=0.05))
    q=C.face_card(0,0.05,0,3.2,3.4,'door')
    return done(m,q)


@register('cydress.ac',V,'furniture',{},'Wall AC unit with a painted fan grille, drip pipe and bevelled case.',origin='floor_center')
def ac(P,seed):
    m=C.slab(0,0,0,1.1,0.65,0.72,'body_alt',c=0.08)
    q=C.face_card(0,-0.335,0.1,0.58,0.5,'metal')
    m.merge(C.rod((0.42,0,0),(0.42,0,-0.3),0.035,4,'metal'))
    return done(m,q)


@register('cydress.water_tank',V,'structure',{},'Rooftop six-sided water tank with conical rain cap and splayed support legs.',origin='floor_center')
def water_tank(P,seed):
    m=C.lathe_at(0,0,1,[(1.1,0),(1.1,2.1),(0.2,2.7),(0,2.72)],8,'metal',smooth=False)
    for k in range(4):
        a=k*K.TAU/4
        m.merge(C.rod((1.3*math.cos(a),1.3*math.sin(a),0),(0.8*math.cos(a),0.8*math.sin(a),1.2),0.09,4,'post'))
    return done(m)


@register('cydress.pipe_elbow',V,'furniture',{},'Bent wall drainpipe with socket collars; original industrial silhouette.',origin='floor_center')
def pipe_elbow(P,seed):
    m=C.tube([(0,0,0),(0,0,1.4),(0,-0.15,1.6),(0,-0.55,1.6)],0.13,6,'metal')
    for z in (0.12,1.1):
        m.merge(C.cyl(0,0,z,0.17,0.12,6,'trim'))
    return done(m)


@register('cydress.bollard',V,'furniture',{},'Tapered street bollard with an amber painted cap.',origin='floor_center')
def bollard(P,seed):
    m=C.lathe_at(0,0,0,[(0.19,0),(0.15,0.1),(0.12,0.8),(0.08,0.94),(0,0.96)],6,'post',smooth=False)
    q=C.face_card(0,-0.125,0.64,0.13,0.12,'light',slot_rect('c'))
    return done(m,q)


@register('cydress.traffic_signal',V,'structure',{},'Traffic signal on bent arm; three dim painted lamps, not an emissive flood.',origin='floor_center')
def traffic_signal(P,seed):
    m=C.frustum(0,0,0,4.5,0.12,0.07,6,'post')
    m.merge(C.rod((0,0,4.4),(1.4,0,4.4),0.07,4,'post'))
    m.merge(C.slab(1.3,0,3.2,0.42,0.35,1.3,'frame',c=0.08))
    q=K.Mesh()
    for k,s in enumerate(('b','c','a')):
        q.merge(C.face_card(1.3,-0.19,3.32+k*0.35,0.23,0.23,'light',slot_rect(s)))
    return done(m,q)


@register('cydress.speaker',V,'furniture',{},'Club speaker with splayed case and two painted recessed cones.',origin='floor_center')
def speaker(P,seed):
    m=C.taper(0,0,0,1.6,0.8,0.7,0.65,0.6,0.1,0.08,'body_alt')
    q=K.Mesh()
    for z in (0.4,1.1):
        q.merge(C.face_card(0,-0.355,z-0.23,0.46,0.46,'metal'))
    return done(m,q)


@register('cydress.cup',V,'prop',{},'Small tapered reusable drink cup with rolled rim, lid and straw.',origin='floor_center')
def cup(P,seed):
    m=C.lathe_at(0,0,0,[(0.065,0),(0.09,0.18),(0.10,0.2),(0,0.2)],8,'body',smooth=False)
    m.merge(C.rod((0.03,0,0.18),(0.06,0,0.36),0.008,4,'post'))
    return done(m)
