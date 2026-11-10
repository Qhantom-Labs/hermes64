"""Original rounded loft characters. Pure Python 3.9; no Blender, no theme branches."""
import math

TAU=2*math.pi
HUMAN_PARENTS={'root':None,'pelvis':'root','spine':'pelvis','head':'spine',
 'upper_arm_l':'spine','forearm_l':'upper_arm_l','hand_l':'forearm_l',
 'upper_arm_r':'spine','forearm_r':'upper_arm_r','hand_r':'forearm_r',
 'thigh_l':'pelvis','shin_l':'thigh_l','foot_l':'shin_l',
 'thigh_r':'pelvis','shin_r':'thigh_r','foot_r':'shin_r'}
QUAD_PARENTS={'root':None,'hips':'root','chest':'hips','neck':'chest','head':'neck',
 'tail_1':'hips','tail_2':'tail_1','tail_3':'tail_2','leg_fl':'chest','paw_fl':'leg_fl',
 'leg_fr':'chest','paw_fr':'leg_fr','leg_bl':'hips','paw_bl':'leg_bl','leg_br':'hips','paw_br':'leg_br'}
HUMAN_DEFAULTS=dict(height=1.65,build=1.,head_size=1.,head_mode='faceless',headwear='hood',
 headwear_finish='sheen',face=0,top_pattern='knit',vest='quilted_wave',mantle=.6,skirt=0.,
 trouser_volume=1.,wear=.3,hands='gloves',boots='heavy',armband=False,patch=False,
 acc_head='none',acc_back='none',acc_belt='pouch',hood_tilt=0.)
# STEER-6 masked cleanup: new fixed topology (recessed hood opening + capelet collar roll; 7-sided trousers/boots,
# 5-sided mitts fund the extra rings). approved/masked_v1 keeps the old human16_hood_v1 generator frozen.
MASKED_TOPOLOGY='human16_hood_v2'
# vest/torso rings (z, half-width per build, half-depth), fractions of height
VEST=[(.452,.112,.080),(.53,.108,.088),(.672,.142,.097),(.742,.080,.064)]
# sleeve ring radii (cuff, forearm, elbow, upper arm, shoulder) per height; v1 was (.031,.045,.043,.052,.047)
SLEEVE_R=(.034,.047,.047,.059,.055)   # round 15: forearm .054 crossed at 0.09 overlap (limit .05)
COLORS=['skin','headwear_color','top_color','vest_color','vest_trim_color','mantle_color',
 'skirt_color','bottom_color','glove_color','boot_color','belt_color','armband_color']
for _k in COLORS:HUMAN_DEFAULTS[_k]='white'
QUAD_DEFAULTS=dict(species='cat',size=1.,leg_length=1.,snout_length=1.,ear_shape='pointed',tail_length=1.,
 chubby=1.,antlers=False,coat_pattern='tuxedo',coat_color_1='white',coat_color_2='white',coat_color_3='white',eye_color='white')


def resolve(values, defaults):
    p=dict(defaults)
    for k,v in values.items():
        if k not in p:raise ValueError('unknown parameter '+k)
        p[k]=v
    ranges={'height':(1.25,2.05),'build':(.8,1.25),'head_size':(.85,1.2),'trouser_volume':(.85,1.4),
      'wear':(0,1),'mantle':(0,1),'skirt':(0,1),'size':(.65,1.4),'leg_length':(.75,1.3),
      'snout_length':(.7,1.3),'tail_length':(.35,1.3),'chubby':(.85,1.25),'face':(0,7),'hood_tilt':(-1,1)}
    enums={'head_mode':['face','faceless'],'headwear':['bald','crop','bob','long','ponytail','bun','hood','helmet','cap'],
      'headwear_finish':['matte','sheen'],'top_pattern':['fabric','knit','checks','stripes','flat'],
      'vest':['none','quilted_wave','quilted_diamond','leather','apron'], 'hands':['bare','gloves'],
      'boots':['heavy','boots','shoes'],'acc_head':['none','badge','goggles'],'acc_back':['none','pack','roll'],
      'acc_belt':['none','pouch','flask'],'species':['cat','dog'], 'ear_shape':['pointed','round','floppy'],
      'coat_pattern':['solid','tuxedo','tabby','calico','spotted','socks','saddle']}
    for k,(lo,hi) in ranges.items():
        if k in p and (type(p[k]) not in (float,int) or not math.isfinite(p[k]) or not lo<=p[k]<=hi):raise ValueError(k+' outside declared range')
    for k,opts in enums.items():
        if k in p and p[k] not in opts:raise ValueError(k+' invalid enum')
    for k in ('armband','patch','antlers'):
        if k in p and type(p[k]) is not bool:raise ValueError(k+' must be boolean')
    if 'face' in p and type(p['face']) is not int:raise ValueError('face must be integer')
    if p.get('antlers'):raise ValueError('antlers not implemented for cat/dog')
    return p


class Mesh:
    def __init__(self,p,bones,parents,kind):
        self.params=p;self.bones=bones;self.parents=parents;self.kind=kind
        self.vertices=[];self.faces=[];self.uv=[];self.weights=[];self.roles=[];self.parts={};self.tiles=[]
    def loft(self,name,rings,n,tile,bone,axis='z',centercaps=False,role='costume',bulge=None):
        # rings: centre x,y,z + ellipse radius a,b; one weight dict per ring or a bone name.
        start=len(self.vertices);nr=len(rings)
        for k,(x,y,z,a,b) in enumerate(rings):
            for j in range(n):
                theta=TAU*(j/n-.5)
                dx=a*math.sin(theta);dy=-b*math.cos(theta)
                pos=(x+dx,y+dy,z) if axis=='z' else (x+dx,y,z-dy)
                if bulge:pos=bulge(pos,k,j,theta)
                self.vertices.append(tuple(pos))
                self.weights.append({bone:1.} if isinstance(bone,str) else dict(bone[k]))
        self.parts[name]=list(range(start,len(self.vertices)))
        def tex(u,v):
            if role in ('face','headwear','animal_face'):return (u,v)
            return ((tile%4+.04+.92*u)/4,(tile//4+.04+.92*v)/4)
        def face(ids,uv,mat=role):
            self.faces.append(tuple(start+i for i in ids));self.uv.append(uv);self.roles.append(mat);self.tiles.append(tile)
        for k in range(nr-1):
            for j in range(n):
                a=k*n+j;b=k*n+(j+1)%n;c=(k+1)*n+(j+1)%n;d=(k+1)*n+j
                uv=[tex(j/n,k/(nr-1)),tex((j+1)/n,k/(nr-1)),tex((j+1)/n,(k+1)/(nr-1)),tex(j/n,(k+1)/(nr-1))]
                face((a,b,c),[uv[0],uv[1],uv[2]]);face((a,c,d),[uv[0],uv[2],uv[3]])
        for end in (0,nr-1):
            ids=[end*n+j for j in range(n)]
            uv=[tex(.5+.5*math.sin(TAU*(j/n-.5)),.5-.5*math.cos(TAU*(j/n-.5))) for j in range(n)]
            mat=role
            if centercaps and end==0:
                mat='face' if self.kind=='human' else 'animal_face'
                uv=[(.5+.5*math.sin(TAU*(j/n-.5)),.5+.5*math.cos(TAU*(j/n-.5))) for j in range(n)]
            if centercaps:
                c=len(self.vertices)-start
                x,y,z,a,b=rings[end]
                self.vertices.append((x,y+(-.008 if end==0 else .008),z))
                self.weights.append({bone:1.} if isinstance(bone,str) else dict(bone[end]))
                self.parts[name].append(c+start)
                for j in range(n):
                    if end==0:face((c,ids[(j+1)%n],ids[j]),[(.5,.5),uv[(j+1)%n],uv[j]],mat)
                    else:face((c,ids[j],ids[(j+1)%n]),[tex(.5,.5),uv[j],uv[(j+1)%n]],mat)
            else:
                if end==0:ids.reverse();uv.reverse()
                for j in range(1,n-1):face((ids[0],ids[j],ids[j+1]),[uv[0],uv[j],uv[j+1]])
        return self
    def finish(self):
        # Base footprint centred in x/y. Z grounded. All object transforms remain identity.
        floor=min(v[2] for v in self.vertices)
        self.vertices=[(x,y,z-floor) for x,y,z in self.vertices]
        self.bones={k:(x,y,z-floor) for k,(x,y,z) in self.bones.items()}
        self.bones['root']=(0.,0.,0.)
        return self


def _leg_plan(B,V,skirt,boot):
    """STEER-5 leg proportion rule (core/proportion.leg_bounds): ring centres/half-widths of the trouser rings
    (ankle, calf, knee, thigh; the waistband ring is the hip line and stays) and boots, bounded by the hip and torso
    half-widths, in units of height. Unchanged for figures already inside the bound."""
    try:
        from . import proportion as PRP
    except ImportError:                    # loaded standalone (tests load core/geometry.py by file path)
        import importlib.util,os
        spec=importlib.util.spec_from_file_location('proportion',os.path.join(os.path.dirname(os.path.abspath(__file__)),'proportion.py'))
        PRP=importlib.util.module_from_spec(spec);spec.loader.exec_module(PRP)
    prof=[(VEST[0][0]-.17*skirt,(VEST[0][1]+.055*skirt)*B)]+[(z,r*B) for z,r,_ in VEST[1:]]
    hip=max(.077*B+.072*B,PRP.profile_max(prof[:2],.43,.49))
    torso=PRP.profile_max(prof,.52,.655)
    # STEER-6: baggy straight wool trousers - near-uniform wide rings bunching over the boot; the rule keeps the
    # pair inside the hip line, so they read as two broad columns instead of thin sticks
    legs=PRP.plan_legs([(.104*B,.066*B,0.),(.104*B,.074*B*V,0.),(.098*B,.072*B*V,0.),(.086*B,.084*B*V,0.)],hip,torso,gap=-.0035*B,scale=B)
    g=PRP.boot_bounds(hip)
    c0=legs[0][0]
    boots=[g(c0,r) for r in (.062*B*boot,.070*B*boot,.056*B)]   # chunky boots with a flared cuff
    cb=min(c for c,r in boots)
    boots=[(cb,r) for c,r in boots]
    if cb<c0:legs[0]=(cb,legs[0][1])
    return legs,boots


ROLL_DEPTH=.012  # round 21 (STEER-8): metres - the capelet's collar roll (yoke top ring, hidden in the hood) sits at
                 # least this deep inside the hood at rest; a small, strongly tilted hood left it 0.5 mm inside and the
                 # join opened in idle (sweep seed 11). The 8 approved residents are 12.9-44.6 mm deep: unchanged.


def _roll_depth(b):
    try:
        from . import connectivity as CN
    except ImportError:                    # loaded standalone (tests load core/geometry.py by file path)
        import importlib.util,os
        spec=importlib.util.spec_from_file_location('connectivity',os.path.join(os.path.dirname(os.path.abspath(__file__)),'connectivity.py'))
        CN=importlib.util.module_from_spec(spec);spec.loader.exec_module(CN)
    st=CN.structure(b)
    hood=CN._Solid([tuple(b.vertices[i] for i in b.faces[fi]) for fi in st['hood'][2]])
    out=[]
    for q in CN.seam_points(b,b.vertices,'yoke',-1,st):
        d=math.sqrt(hood.dist_sq(q));out.append(d if hood.inside(q) else -d)
    return min(out)


def _sink_roll(b):
    """Narrow the hidden collar-roll top ring until it sits ROLL_DEPTH inside the hood (no-op when it already does)."""
    if _roll_depth(b)>=ROLL_DEPTH:return
    ids=b.parts['yoke'][24:32];orig={i:b.vertices[i] for i in ids}
    cx=sum(orig[i][0] for i in ids)/8;cy=sum(orig[i][1] for i in ids)/8
    for sc in (.92,.85,.78,.70,.62,.55):
        for i in ids:x,y,z=orig[i];b.vertices[i]=(cx+(x-cx)*sc,cy+(y-cy)*sc,z)
        if _roll_depth(b)>=ROLL_DEPTH:return


def humanoid(values):
    """Masked resident v2 (STEER-6). Same rig/bones as v1; new fixed topology MASKED_TOPOLOGY for every param."""
    p=resolve(values,HUMAN_DEFAULTS);H=p['height'];B=p['build'];Q=p['head_size']*1.10;V=p['trouser_volume']
    tilt=p['hood_tilt']
    bootk={'heavy':1.08,'boots':1.,'shoes':.88}[p['boots']]
    legs,boots=_leg_plan(B,V,p['skirt'],bootk)
    bones={'root':(0,0,0),'pelvis':(0,0,.46),'spine':(0,0,.52),'head':(0,0,.755)}
    for side,s in [('l',1),('r',-1)]:
        for n,x,y,z in [('upper_arm',.143*B,0,.69),('forearm',.204*B,-.005,.57),('hand',.23*B,-.018,.46),
           ('thigh',.085*B,0,.46),('shin',legs[2][0],-.006,.28),('foot',legs[0][0],0,.09)]:bones[n+'_'+side]=(s*x,y,z)
    bones={n:tuple(c*H for c in v) for n,v in bones.items()}
    b=Mesh(p,bones,HUMAN_PARENTS,'human');b.topology=MASKED_TOPOLOGY
    def rings(seq):return [tuple(c*H for c in r) for r in seq]
    def add(name,seq,n,tile,bone,**kw):b.loft(name,rings(seq),n,tile,bone,**kw)
    sk=p['skirt']
    # ---- vest (torso): flared quilted hem, firm waist, full chest - a garment layer, not a puffy tube
    add('torso',[(0,0,VEST[0][0]-.17*sk,(VEST[0][1]+.055*sk)*B,VEST[0][2]+.018*sk),(0,-.003,VEST[1][0],VEST[1][1]*B,VEST[1][2]),
        (0,.005,VEST[2][0],VEST[2][1]*B,VEST[2][2]),(0,.012,VEST[3][0],VEST[3][1]*B,VEST[3][2])],8,0,
        [{'pelvis':.7,'spine':.3},{'spine':1},{'spine':1},{'spine':1}])
    # ---- capelet: the hood fabric drapes over the shoulders (hem drops front and back) and rises into a collar roll
    m=p['mantle'] if p['head_mode']=='faceless' else p['mantle']*.65
    mk=.84+.32*m
    add('yoke',[(0,.010,.684,.150*B,.104),(0,.004,.728,.138*B,.100),(0,-.004,.760,.092,.084),(0,0,.782,.064,.058)],8,5,'spine',
       bulge=lambda pos,k,j,t:(pos[0]*(mk if k<2 else 1.),pos[1],pos[2]-(.012*H*math.cos(t)**2 if k==0 else 0)))
    for side,s in [('l',1),('r',-1)]:
        # baggy knit sleeves tapering to a ribbed cuff (v1 arms read as sticks beside the vest)
        R=SLEEVE_R
        arm=[(s*.236*B,-.018,.446,R[0]*B,R[0]),(s*.222*B,-.011,.49,R[1]*B,R[1]*.97),
          (s*.203*B,-.005,.568,R[2]*B,R[2]*.98),(s*.176*B,0,.64,R[3]*B,R[3]*.98),(s*.138*B,.005,.704,R[4]*B,R[4])]
        weights=[{'forearm_'+side:1},{'forearm_'+side:1},{'forearm_'+side:.5,'upper_arm_'+side:.5},{'upper_arm_'+side:1},{'upper_arm_'+side:1}]
        add('sleeve_'+side,arm,6,1,weights)
        # bigger light knit mitts with a real thumb (v1: small black dots)
        add('mitt_'+side,[(s*.241*B,-.028,.382,.021,.024),(s*.244*B,-.028,.405,.041,.029),(s*.237*B,-.019,.45,.034,.028)],5,3,'hand_'+side)
        add('thumb_'+side,[(s*.207*B,-.044,.405,.016,.019),(s*.219*B,-.035,.437,.022,.024)],4,3,'hand_'+side)
        (c0,r0),(c1,r1),(c2,r2),(c3,r3)=legs
        leg=[(s*c0,0,.109,r0,.058),(s*c1,.008,.174,r1,.070*V),
          (s*c2,-.012,.275,r2,.068*V),(s*c3,.006,.396,r3,.083*V),(s*.077*B,0,.48,.072*B,.068)]
        lw=[{'shin_'+side:1},{'shin_'+side:1},{'shin_'+side:.5,'thigh_'+side:.5},{'thigh_'+side:1},{'thigh_'+side:.7,'pelvis':.3}]
        add('trouser_'+side,leg,7,2,lw,
            bulge=lambda pos,k,j,t:(pos[0],pos[1]-(.006*H*math.cos(t) if k==2 and math.cos(t)>.3 else 0),pos[2]))   # knee crease
        boot=bootk;(bc0,br0),(bc1,br1),(bc2,br2)=boots
        add('boot_'+side,[(s*bc0,-.030,.008,br0,.104*boot),
          (s*bc1,-.026,.054,br1,.114*boot),(s*bc2,.004,.13,br2,.056)],7,4,'foot_'+side,
          bulge=lambda pos,k,j,t:(pos[0],pos[1],pos[2]-(.018*H*max(0,math.cos(t)) if k==1 else 0)))
    # ---- hood: lining ring (recessed behind the rim) -> rim -> dome -> crown -> back; front cap = the void
    z=.857;face=p['head_mode']=='face';style=p['headwear']
    # round 15: ~8% less hood volume (read as a sack wider than the shoulders in the room) and a wider-than-tall
    # opening (the tall oval read as a screaming mouth)
    # round 16 (studied on the expedition sheet): a compact cowl, not a ball - narrower sides, the back drops toward
    # the capelet, and a tall shield opening under a beaked peak (rim ring taller than wide; the peak pull below)
    Qh=Q*.95                                    # round 17: 5% smaller hood (still read large on the shoulders in the room)
    hr=[(0,-.080*Qh,z-.008,.056*Qh,.064*Qh),(0,-.112*Qh,z-.002,.078*Qh,.090*Qh),(0,-.083*Qh,z+.006,.100*Qh,.121*Qh),
        (0,.014*Qh,z+.004,.104*Qh,.124*Qh),(0,.104*Qh,z-.020,.036*Qh,.050*Qh)]
    if face:   # legacy painted-face head on the masked rig: ring 0 is a front plate ahead of the jaw ring
        hr=[(0,-.118*Q,z-.002,.084*Q,.094*Q),(0,-.106*Q,z,.094*Q,.105*Q),(0,-.07*Q,z+.01,.108*Q,.124*Q),
            (0,.026*Q,z+.012,.112*Q,.128*Q),(0,.10*Q,z+.012,.057*Q,.078*Q)]
    def hood_shape(pos,k,j,t):
        x,y,zz=pos
        up=max(0.,math.cos(t));dn=max(0.,-math.cos(t))
        if not face:
            if k in (0,1,2):
                # forward overhanging brow and a central peak; the lining follows the rim at 70%
                f=.7 if k==0 else 1.
                y-=.025*H*up*f;zz-=.015*H*up**10*f
                if k==1:y-=.016*H*up**6;zz+=.010*H*up**6   # beaked peak juts forward over the opening
                x+=.006*H*tilt*up**4*f                 # the peak slumps a little to one side (per resident)
                if k in (0,1):x*=.84+.16*(math.cos(t)+1)/2
            if k in (2,3):zz+=.005*H*up**16            # centre seam ridge
            if k in (3,4):
                # fabric volume: the lower back falls onto the shoulders, more on one side
                zz-=.022*H*dn**1.4*(1. if k==3 else .7)*(1+.35*tilt*math.sin(t))
                y+=.008*H*dn
        if face and style in ('bob','long') and k>1:
            zz-=H*(.050 if style=='bob' else .10)*max(0,-math.cos(t))
            x*=1.06
        if face and style=='crop' and k==2:
            zz+=H*.018*max(0,math.cos(t))*(1+.5*math.sin(t*3))
        if face and style=='cap' and k==2 and math.cos(t)>.1:y-=H*.065
        return (x,y,zz)
    hf0=len(b.faces)
    add('hood',hr,12,6,'head',axis='y',centercaps=True,role='headwear',bulge=hood_shape)
    hv0=b.parts['hood'][0]
    def polar(vi):
        k,j=divmod(vi-hv0,12);th=TAU*(j/12-.5);r=.34 if k==0 else .5
        return (.5+r*math.sin(th),.5+r*math.cos(th))
    for fi in range(hf0,hf0+24):                # lining band -> face atlas (outer ring of the void cell)
        b.roles[fi]='face';b.uv[fi]=[polar(vi) for vi in b.faces[fi]]
    fc0=hf0+2*12*4
    for fi in range(fc0,fc0+12):                # void cap: lining ring at UV radius .34, centre at the cell centre
        b.uv[fi]=[(.5+(u-.5)*.68,.5+(v-.5)*.68) for u,v in b.uv[fi]]
    for fi in range(fc0+12,fc0+24):             # back cap samples the back stripe of the hood texture
        b.uv[fi]=[(u,.93+(v-.5)*.08) for u,v in b.uv[fi]]
    ci=hv0+5*12                                 # dished void: the cap centre sits well behind the lining ring
    x,y,zz=b.vertices[ci];b.vertices[ci]=(x,y+.008+(.030*Q*H if not face else 0.),zz)
    if tilt:                                    # whole hood rolls a few degrees (per-resident attitude)
        ang=.07*tilt;ca,sa=math.cos(ang),math.sin(ang);zc=z*H
        for vi in b.parts['hood']:
            x,y,zz=b.vertices[vi];dz=zz-zc
            b.vertices[vi]=(x*ca-dz*sa,y,zc+x*sa+dz*ca)
    _sink_roll(b)                               # round 21: the collar roll stays buried in the hood
    # Three permanently present authored curved add-ons. Hidden options stay non-degenerate inside body.
    for name,bone,xyz,rad,tile in [('acc_head','head',(0,.108,.87),.035,6),('acc_back','spine',(0,.102,.615),.084,7),('acc_belt','pelvis',(.13*B,-.012,.462),.04,8)]:
        on=p[name]!='none' or (name=='acc_head' and style in ('ponytail','bun'))
        if not on:xyz=tuple(v/H for v in bones[bone]);rad=.009
        if name=='acc_head' and style=='bun':xyz=(0,.088,.965)
        x,y,z0=xyz
        rx,ry,rz=rad,rad*.75,rad
        if on and name=='acc_belt' and p[name]=='flask':rx*=.63;ry*=.8;rz*=1.5
        if on and name=='acc_back' and p[name]=='roll':rx*=1.4;rz*=.45
        if on and name=='acc_head' and p[name] in ('badge','goggles'):
            y=-.125;x=0;z0=.91;rx=.073 if p[name]=='goggles' else .026;ry=.018;rz=.018
        add(name,[(x,y,z0-rz,rx*.6,ry*.67),(x,y,z0+rz,rx,ry)],5,tile,bone)
    return b.finish()


def quadruped(values):
    p=resolve(values,QUAD_DEFAULTS);S=p['size'];dog=p['species']=='dog';C=p['chubby']
    L=.34 if not dog else .46;Z=(.22 if not dog else .235)*p['leg_length'];R=.115 if not dog else .14  # round 11: shorter dog legs
    hx=0;hy=-L*.68;hz=Z+.13
    bones={'root':(0,0,0),'hips':(0,L*.27,Z),'chest':(0,-L*.24,Z),'neck':(0,-L*.41,Z+.055),'head':(0,hy,hz)}
    tl=(.28 if not dog else .24)*p['tail_length']  # round 12: tail joints follow the actual tail length (short tails tore in sleep)
    for i in range(3):bones['tail_'+str(i+1)]=(0,L*.52+tl*(0,.35,.72)[i],Z+(.035,.08,.16)[i])
    for side,s in [('l',1),('r',-1)]:
        for end,y in [('f',-L*.33),('b',L*.34)]:
            bones['leg_'+end+side]=(s*.088,y,Z);bones['paw_'+end+side]=(s*.088,y,.065)
    b=Mesh(p,{k:tuple(q*S for q in v) for k,v in bones.items()},QUAD_PARENTS,'quad')
    def add(name,seq,n,tile,bone,**kw):b.loft(name,[tuple(v*S for v in r) for r in seq],n,tile,bone,**kw)
    add('body',[(0,-L*.59,Z,.073*C,.083*C),(0,-L*.27,Z+.02,.125*C,.14*C),(0,L*.24,Z+.018,.14*C,.14*C),(0,L*.57,Z,.082*C,.08*C)],8,0,
       [{'chest':1},{'hips':.3,'chest':.7},{'hips':1},{'hips':1}],axis='y',role='coat')
    add('neck',[(0,-L*.33,Z-.055,.085,.079),(0,hy,hz-.015,.088,.078)],6,0,
       [{'chest':1},{'head':.7,'neck':.3}],role='coat')
    hs=len(b.vertices);hf=len(b.faces)
    sn=(.043 if not dog else .088)*p['snout_length']
    if dog:
        # round 13 (STEER-5 §7): rounder dog head - shorter snout with a fuller, lower nose end, a narrower but
        # taller muzzle base, a domed skull and a full back of the head (the long 8-sided cone read as a box)
        hr=[(0,hy-R*.74-sn,hz-.06,.056,.046),(0,hy-R*.62,hz-.012,.088,.086),(0,hy+.012,hz+.02,R*1.04,R*1.06),(0,hy+R*.78,hz+.006,.086,.084)]
    else:
        hr=[(0,hy-R*.78-sn,hz-.045,.048,.033),(0,hy-R*.68,hz,.098,.09),(0,hy+.015,hz+.012,R*1.12,R),(0,hy+R*.8,hz,.068,.070)]
    add('head',hr,8,1,'head',axis='y',centercaps=True,role='headwear')
    # The snout and cheeks are continuous, not a separate plugged-in muzzle.
    # Canonical projection preserves UVs across cat/dog and all size parameters.
    face_uv={}
    for k in (0,1):
        for j in range(8):
            t=TAU*(j/8-.5)
            face_uv[hs+k*8+j]=(.5+( .23 if k==0 else .5)*math.sin(t),(.27 if k==0 else .5)+(.18 if k==0 else .5)*math.cos(t))
    face_uv[hs+32]=(.5,.27)
    for fi in list(range(hf,hf+16))+list(range(hf+48,hf+56)):
        b.roles[fi]='animal_face';b.uv[fi]=[face_uv[i] for i in b.faces[fi]]
    for side,s in [('l',1),('r',-1)]:
        earz=hz+R*.7
        pointed=p['ear_shape']=='pointed' and not dog
        ear0=(s*R*.75,hy,earz,.052,.033)
        ear1=(s*R*.92,hy+.007,earz+.075,.012,.014)
        if not pointed:
            ear0=(s*R*1.12,hy-.008,earz-.10,.032,.022)
            ear1=(s*R*.84,hy+.005,earz+.018,.047,.035)
        add('ear_'+side,[ear0,ear1],3,3,'head',role='coat')
        for end,y in [('f',-L*.33),('b',L*.34)]:
            nm=end+side
            add('leg_'+nm,[(s*.088,y-.028,.009,.051,.068),(s*.088,y,.067,.035,.038),(s*.088,y,Z+.02,.045,.05)],5,4,
              [{'paw_'+nm:1},{'leg_'+nm:.5,'paw_'+nm:.5},{'leg_'+nm:1}],role='coat')
    length=(.28 if not dog else .24)*p['tail_length']
    add('tail',[(0,L*.52,Z+.035,.032,.032),(0,L*.52+length*.35,Z+.08,.035,.035),
        (0,L*.52+length*.72,Z+.16,.027,.027),(0,L*.52+length,Z+.20,.017,.017)],5,5,
        [{'tail_1':1},{'tail_1':.3,'tail_2':.7},{'tail_2':.3,'tail_3':.7},{'tail_3':1}],axis='y',role='coat')
    return b.finish()
