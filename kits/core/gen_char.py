"""Two fixed-connectivity segmented bases. Shapes and semantic slots only; no pack branches.

Every triangle corner has a stable UV seam. This deliberately prevents glTF's attribute
merging from changing vertex counts when proportions, lighting or materials change.
Rigid overlapping segments are a period-style choice, not a soft anatomical skin.
"""
import math
import numpy as np
from . import meshkit as K, schema as S
from .asset import Asset, Node, register

HUMAN_PARENTS = {'root': None, 'pelvis': 'root', 'spine': 'pelvis', 'head': 'spine',
    'upper_arm_l': 'spine', 'forearm_l': 'upper_arm_l', 'hand_l': 'forearm_l',
    'upper_arm_r': 'spine', 'forearm_r': 'upper_arm_r', 'hand_r': 'forearm_r',
    'thigh_l': 'pelvis', 'shin_l': 'thigh_l', 'foot_l': 'shin_l',
    'thigh_r': 'pelvis', 'shin_r': 'thigh_r', 'foot_r': 'shin_r'}
QUAD_PARENTS = {'root': None, 'hips': 'root', 'chest': 'hips', 'neck': 'chest', 'head': 'neck',
    'tail_1': 'hips', 'tail_2': 'tail_1', 'tail_3': 'tail_2', 'leg_fl': 'chest', 'paw_fl': 'leg_fl',
    'leg_fr': 'chest', 'paw_fr': 'leg_fr', 'leg_bl': 'hips', 'paw_bl': 'leg_bl',
    'leg_br': 'hips', 'paw_br': 'leg_br'}
HUMAN_CLIPS = ['idle', 'walk', 'run', 'interact', 'talk', 'carry', 'sit']
QUAD_CLIPS = ['idle', 'walk', 'run', 'sit', 'loaf', 'sleep_curled', 'stretch']
ATTACH = {'attach_hand_l': 'hand_l', 'attach_hand_r': 'hand_r', 'attach_head': 'head',
          'attach_back': 'spine', 'attach_belt': 'pelvis'}


class Body:
    def __init__(self):
        self.mesh = K.Mesh()
        self.weights = []
        self.uvs = []
        self.part_bounds = {}

    def add(self, name, mesh, bone, tile=0, role='costume', face_uv=False):
        # Fixed fan triangulation: convex primitive faces only, never geometry-dependent.
        base = len(self.mesh.v)
        self.mesh.v.extend(mesh.v)
        self.weights.extend([bone] * len(mesh.v))
        P = np.asarray(mesh.v)
        lo, hi = P.min(0), P.max(0)
        self.part_bounds[name] = [lo.tolist(), hi.tolist()]
        for f in mesh.f:
            for j in range(1, len(f)-1):
                tri = [f[0], f[j], f[j+1]]
                self.mesh.f.append(tuple(base+k for k in tri))
                self.mesh.r.append(role)
                self.mesh.s.append(True)
                self.mesh.uv.append(None)
                # Local projection of the canonical topology, not deformed positions.
                # Per-corner seams survive exporter vertex welding; precision fits float32.
                n = len(self.mesh.f)
                eps = n * 0.000003
                if face_uv:
                    # Geometry is an ellipsoid whose indexed coordinates are proportional.
                    uv = [((P[k,0]-lo[0]) / (hi[0]-lo[0]), (P[k,2]-lo[2]) / (hi[2]-lo[2])) for k in tri]
                else:
                    uv = [(0.08,0.08), (0.92,0.08), (0.5,0.92)]
                if role in ('costume', 'coat'):
                    x,y = tile % 4, tile // 4
                    uv = [((x+u*0.92+0.04)/4, (3-y+v*0.92+0.04)/4) for u,v in uv]
                self.uvs.append([(u+eps,v+eps*0.31) for u,v in uv])
        return self


def ell(c, r, seg=6, rings=3):
    return K.sphere(*c, *r, seg, rings, 'costume', start=math.pi/6)


def finish(body, P, seed, skeleton, heads, parents, clips, attachments):
    # Center the rest footprint once; offsets affect root placement, never bone orientation.
    pts = np.asarray(body.mesh.v)
    lo,hi = pts.min(0),pts.max(0)
    off = np.array([(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]])
    body.mesh.translate(*(-off))
    h = {n: (np.asarray(p)-off).tolist() for n,p in heads.items()}
    h['root'] = [0,0,0]
    a = Asset([], {'body_id': 'char.humanoid' if skeleton=='human16_v1' else 'char.quadruped',
                    'skeleton': skeleton, 'segmented_rigid_skin': True})
    a.character = {'skeleton': skeleton, 'body': Node('body',body.mesh), 'weights': body.weights,
        'uvs': body.uvs, 'params': P, 'seed': seed, 'heads': h, 'bones': list(parents),
        'parents': parents, 'clips': clips, 'attachments': attachments,
        'reference': {'names': list(parents), 'parent': parents,
                      'world_rot': {n: np.eye(3).tolist() for n in parents}}}
    return a


HUMAN = {
 'height': S.num(1.72,1.25,2.05), 'build': S.num(1.0,0.8,1.25), 'head_size': S.num(1,0.85,1.2),
 'head_mode': S.enum('face',['face','faceless']), 'face': S.integer(0,0,7),
 'headwear': S.enum('crop',['bald','crop','bob','long','ponytail','bun','hood','helmet','cap']),
 'headwear_finish': S.enum('matte',['matte','sheen']),
 'top_pattern': S.enum('fabric',['fabric','knit','checks','stripes','flat']),
 'vest': S.enum('none',['none','quilted_wave','quilted_diamond','leather','apron']),
 'mantle': S.num(0,0,1), 'skirt': S.num(0,0,1), 'trouser_volume': S.num(1,0.85,1.3),
 'wear': S.num(0,0,1), 'hands': S.enum('bare',['bare','gloves']),
 'boots': S.enum('boots',['heavy','boots','shoes']), 'armband': S.boolean(False), 'patch': S.boolean(False),
 'acc_head': S.enum('none',['none','badge','goggles']), 'acc_back': S.enum('none',['none','pack','roll']),
 'acc_belt': S.enum('none',['none','pouch','flask'])}
for key in ['skin','headwear_color','top_color','vest_color','vest_trim_color','mantle_color',
            'skirt_color','bottom_color','glove_color','boot_color','belt_color','armband_color']:
    HUMAN[key] = S.color('white')


@register('char.humanoid','3.0.0','character',HUMAN,'Fixed-topology 16-joint segmented humanoid; 7 held clips, face or faceless head.')
def humanoid(P,seed):
    H,B,Q = P['height'],P['build'],P['head_size']
    b = Body()
    heads = {'root': (0,0,0), 'pelvis': (0,0,.47*H), 'spine': (0,0,.52*H), 'head': (0,0,.77*H)}
    b.add('hips', ell((0,0,.47*H),(.115*H*B,.08*H,.095*H)), 'pelvis', 2)
    b.add('torso', ell((0,0,.63*H),(.145*H*B,.091*H,.16*H),8,4), 'spine', 0)
    # Separate closed bib/mantle/skirt stay present: options move/reshape, never add faces.
    vb = 1.025 if P['vest']!='none' else .90
    b.add('bib',ell((0,-.012*H,.635*H),(.14*H*B*vb,.09*H*vb,.145*H),6,3),'spine',1)
    b.add('mantle',ell((0,.007*H,.713*H),((.12+.055*P['mantle'])*H*B,.095*H,(.025+.035*P['mantle'])*H),6,3),'spine',6)
    skirt=P['skirt']
    b.add('skirt',ell((0,0,(.47-.065*skirt)*H),((.108+.06*skirt)*H*B,.09*H,(.025+.12*skirt)*H),6,3),'pelvis',7)
    for side,s in [('l',1),('r',-1)]:
        x=.215*H*B
        heads['upper_arm_'+side]=(x,0,.704*H)
        heads['forearm_'+side]=(x,0,.57*H)
        heads['hand_'+side]=(x,0,.438*H)
        for part,z,rz,rad,tile in [('upper_arm',.651,.095,.061,0),('forearm',.515,.092,.052,0),('hand',.411,.05,.046,4)]:
            b.add(part+side,ell((x,0,z*H),(rad*H*B,rad*H,rz*H)),part+'_'+side,tile)
        lx=.075*H*B
        heads['thigh_'+side]=(s*lx,0,.455*H)
        heads['shin_'+side]=(s*lx,0,.262*H)
        heads['foot_'+side]=(s*lx,0,.072*H)
        tr=P['trouser_volume']
        b.add('thigh'+side,ell((s*lx,0,.369*H),(.068*H*B*tr,.073*H*tr,.128*H)), 'thigh_'+side,2)
        b.add('shin'+side,ell((s*lx,0,.185*H),(.057*H*B*tr,.06*H*tr,.118*H)), 'shin_'+side,2)
        boot={'heavy':1.16,'boots':1.,'shoes':.89}[P['boots']]
        b.add('foot'+side,ell((s*lx,-.026*H,.046*H),(.063*H*B*boot,.105*H*boot,.046*H),6,3),'foot_'+side,3)
    # Correct mirrored arm coordinates without changing connectivity.
    start = b.part_bounds['upper_armr'][0][0]
    # Arms on right were generated at +x; mirror only their vertex ranges by their bone labels.
    for i,bone in enumerate(b.weights):
        if bone in ('upper_arm_r','forearm_r','hand_r'):
            x,y,z=b.mesh.v[i]; b.mesh.v[i]=(-x,y,z)
    for n in ('upper_arm_r','forearm_r','hand_r'):
        x,y,z=heads[n];heads[n]=(-x,y,z)
    # Reflection changes winding on right-arm faces.
    for i,f in enumerate(b.mesh.f):
        if b.weights[f[0]] in ('upper_arm_r','forearm_r','hand_r'):
            b.mesh.f[i]=tuple(reversed(f)); b.uvs[i]=list(reversed(b.uvs[i]))
    hr=.115*H*Q
    b.add('head',ell((0,0,.848*H),(hr,.91*hr,1.12*hr),8,4),'head',5)
    style=P['headwear']
    shell=style in ('hood','helmet')
    # Low-poly closed hair cap, shrunk inside head for bald. Fixed 8x3 topology.
    rad={'bald':.72,'crop':1.01,'bob':1.06,'long':1.06,'ponytail':1.02,'bun':1.02,'hood':1.13,'helmet':1.14,'cap':1.07}[style]
    z=.872*H if not shell else .85*H
    rz=hr*(.72 if not shell else 1.19)
    b.add('headwear',ell((0,.021*H,z),(hr*rad,hr*.9*rad,rz),8,3),'head',0,'headwear')
    b.add('face',ell((0,-hr*.9,.849*H),(hr*.78,hr*.17,hr*.79),8,3),'head',0,'face',True)
    # Additional hair mass: embedded unless long/bob/tied style, constant topology.
    ext=style in ('long','bob','ponytail','bun')
    hy=.064*H if ext else .021*H
    hz=(.77 if style=='long' else .82 if style=='ponytail' else .91 if style=='bun' else .83)*H
    rr=hr*(.55 if ext else .2)
    b.add('hair_tail',ell((0,hy,hz),(rr,rr*.65,rr*(1.65 if style=='long' else 1)),5,3),'head',0,'headwear')
    # Opening material retained as a distinct slot, neck/void seal.
    b.add('neck',ell((0,0,.758*H),(.047*H,.044*H,.06*H),6,3),'head',0,'opening')
    # Optional add-ons keep fixed triangles and skin: embedded when absent.
    for name,bone,c,rr,tile in [('acc_head','head',(0,-.085*H,.93*H),.031*H,8),
        ('acc_back','spine',(0,.103*H,.63*H),.078*H,9),('acc_belt','pelvis',(.122*H*B,0,.45*H),.04*H,10)]:
        enabled=P[name]!='none'
        if not enabled: c=tuple(heads[bone]);rr*=.14
        b.add(name,ell(c,(rr,rr*.55,rr*1.2),5,3),bone,tile)
    return finish(b,P,seed,'human16_v1',heads,HUMAN_PARENTS,HUMAN_CLIPS,ATTACH)


QUAD={'species': S.enum('cat',['cat','dog','deer']), 'size':S.num(1,.65,1.4),
      'leg_length':S.num(1,.75,1.3),'snout_length':S.num(1,.7,1.3),
      'ear_shape':S.enum('pointed',['pointed','round','floppy']), 'tail_length':S.num(1,.35,1.3),
      'chubby':S.num(1,.85,1.25),'antlers':S.boolean(False),
      'coat_pattern':S.enum('solid',['solid','tuxedo','tabby','calico','spotted','socks','saddle'])}
for key in ['coat_color_1','coat_color_2','coat_color_3','eye_color']:
    QUAD[key]=S.color('white')


@register('char.quadruped','3.0.0','animal',QUAD,'Fixed-topology 16-joint cat/dog/deer-like base with 7 held clips and palette coat patterns.')
def quadruped(P,seed):
    sz=P['size'];sp=P['species'];th=P['chubby']
    L,lh,hr,snout={'cat':(.44,.19,.105,.055),'dog':(.58,.30,.12,.105),'deer':(.65,.46,.11,.12)}[sp]
    L*=sz;lh*=sz*P['leg_length'];hr*=sz;snout*=sz*P['snout_length']
    z=lh+.08*sz
    b=Body()
    heads={'root':(0,0,0),'hips':(0,L*.27,z),'chest':(0,-L*.27,z),
           'neck':(0,-L*.4,z+.045*sz),'head':(0,-L*.56,z+.12*sz)}
    b.add('body',ell((0,0,z),(.13*sz*th,L*.65,.135*sz*th),6,3),'hips',0,'coat')
    b.add('chest',ell((0,-L*.26,z+.015*sz),(.115*sz*th,.135*sz,.14*sz),5,3),'chest',0,'coat')
    hc=(0,-L*.56,z+.12*sz)
    b.add('head',ell(hc,(hr,hr,hr),6,3),'head',1,'coat')
    b.add('muzzle',ell((0,hc[1]-hr*.62,hc[2]-.027*sz),(.07*sz,snout,.045*sz),5,2),'head',2,'coat')
    for side,s in [('l',1),('r',-1)]:
        # 8-triangle tapered ears and one small fixed-topology antler spike per side.
        earh=hr*(.9 if P['ear_shape']=='pointed' else .55 if P['ear_shape']=='round' else .8)
        ez=hc[2]+hr*.76
        ey=hc[1]+hr*.05
        ear=K.lathe([(.038*sz,0),(.018*sz,earh*.75),(0,earh)],3,'coat',start=.2).translate(s*hr*.68,ey,ez)
        b.add('ear'+side,ear,'head',3,'coat')
        ar=.012*sz if P['antlers'] else .004*sz
        ah=.18*sz if P['antlers'] else .016*sz
        ant=K.lathe([(ar,0),(0,ah)],3,'coat').translate(s*hr*.5,hc[1]+.025*sz,hc[2]+.073*sz)
        b.add('antler'+side,ant,'head',3,'coat')
        for end,y in [('f',-L*.32),('b',L*.32)]:
            nm=end+side;x=s*.087*sz
            heads['leg_'+nm]=(x,y,z)
            heads['paw_'+nm]=(x,y,.045*sz)
            b.add('leg'+nm,ell((x,y,(z+.04*sz)/2),(.043*sz,.046*sz,(z-.015*sz)/2),4,2),'leg_'+nm,0,'coat')
            b.add('paw'+nm,ell((x,y-.022*sz,.035*sz),(.045*sz,.065*sz,.035*sz),4,2),'paw_'+nm,2,'coat')
    length=(.34 if sp=='cat' else .29 if sp=='dog' else .14)*sz*P['tail_length']
    for i in range(3):
        t=(i+.5)/3
        cy=L*.54+length*t;cz=z+.025*sz+t*.04*sz
        heads['tail_'+str(i+1)]=(0,L*.54+length*i/3,z+.025*sz+i/3*.04*sz)
        b.add('tail'+str(i),ell((0,cy,cz),(.032*sz,length*.21,.031*sz),4,2),'tail_'+str(i+1),0,'coat')
    return finish(b,P,seed,'quad16_v1',heads,QUAD_PARENTS,QUAD_CLIPS,{})
