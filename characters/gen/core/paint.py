"""Palette-only tiny paint. Numpy is bundled with Blender; PNG uses stdlib."""
import math,struct,zlib,hashlib
from pathlib import Path
import numpy as np


def png(path, arr):
    arr=np.asarray(arr,dtype=np.uint8)
    h,w,c=arr.shape
    def chunk(t,p):return struct.pack('!I',len(p))+t+p+struct.pack('!I',zlib.crc32(t+p)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,6 if c==4 else 2,0,0,0))
    data+=chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r.tobytes() for r in arr),9))+chunk(b'IEND',b'')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def rgb(s):return np.array([int(s[i:i+2],16) for i in (1,3,5)],float)

def palette(pack):return np.array([rgb(c) for c in pack['palette']])

def color(pack,name):
    if name not in pack['palette_names']:raise ValueError('off-palette name '+str(name))
    return palette(pack)[pack['palette_names'].index(name)]

def _lum(c):
    c=np.asarray(c,float)/255
    return .2126*c[...,0]+.7152*c[...,1]+.0722*c[...,2]


def named_ramp(pack,names,lums,max_sat=.45):
    """Masked v2 ramps are authored on the polar palette by name. Other packs (the sweep paints masked residents in
    forest_village too) get the same ramp by luminance: for each target, the pack colour closest in luminance among
    the low-saturation ones (the darkest colour - the pack's near-black - is never used)."""
    if all(n in pack['palette_names'] for n in names):
        return np.array([color(pack,n) for n in names],float)
    pal=palette(pack).astype(float);L=_lum(pal)
    mx=pal.max(1);mn=pal.min(1);sat=np.where(mx>0,(mx-mn)/np.maximum(mx,1e-6),0)
    ok=np.ones(len(pal),bool);ok[np.argmin(L)]=False
    out=[]
    for t in lums:
        cost=np.abs(L-t)+2*np.maximum(0,sat-max_sat)+np.where(ok,0,9)
        out.append(pal[int(np.argmin(cost))])
    return np.array(out,float)


def quantize(arr,pal):
    a=np.asarray(arr).reshape(-1,3)
    d=((a[:,None,:]-pal[None,:,:])**2*np.array([.25,.6,.15])).sum(2)
    ix=np.argmin(d,axis=1)
    return pal[ix].astype(np.uint8).reshape(arr.shape)


def noise(u,v,seed=0):
    # Smooth low-frequency mottling, no unseeded RNG and no source pixels.
    return (np.sin(u*17+v*13+seed)*.48+np.sin(u*39-v*23+seed*.7)*.28+np.sin(u*71+v*59+seed*1.3)*.13)


def paint(pack,p,kind='human',seed=0):
    N=128 if kind=='human' else 64
    yy,xx=np.mgrid[0:N,0:N];u=(xx%(N//4)+.5)/(N//4);v=1-(yy%(N//4)+.5)/(N//4)
    tiles=(3-yy//(N//4))*4+xx//(N//4)
    out=np.zeros((N,N,3),float);pal=palette(pack)
    for tile in range(16):
        mask=tiles==tile
        if kind=='human':
            keys=['top_color','top_color','bottom_color','glove_color','boot_color','mantle_color','headwear_color','vest_color','belt_color']
            base=color(pack,p['skin'] if tile==3 and p['hands']=='bare' else p[keys[min(tile,8)]])
            val=.86+.12*np.sin(np.pi*v)+.075*noise(u,v,seed)
            if tile==1:
                pattern=p['top_pattern']
                if pattern=='knit':val+=.055*np.cos(u*TAU*9+v*4)*np.sin(v*np.pi)**2
                if pattern=='stripes':val+=.16*np.cos(v*TAU*5)
                if pattern=='checks':val+=.12*np.cos(u*TAU*4)*np.cos(v*TAU*4)
            if tile==0:
                vest=(v>.10)&(v<.88)
                vest &= ~(((abs(u-.25)<.045)|(abs(u-.75)<.045))&(v>.63))
                if p['vest']=='none':vest=np.zeros_like(vest)
                cv=color(pack,p['vest_color']);t=np.clip((v+.05*np.cos((u-.5)*6))*5,0,10)
                if p['vest']=='quilted_diamond':t=v*5+np.abs((u-.5)*5)%1
                phase=t%1
                seam=np.exp(-((phase-.08)/.07)**2)
                # STEER-6: chunky quilting - puffed channels with deep stitched seams (reads at 320x240)
                quilt=.80+.26*np.sin(phase*np.pi)-.36*seam
                if p['vest'] in ('apron','leather'):quilt=.92+.04*noise(u,v,seed)
                col=base[None,None,:]*val[:,:,None]
                col[vest]=(cv[None,None,:]*(quilt+.025*noise(u,v,seed))[:,:,None])[vest]
                # accent trim: bold hem band, shoulder edge and a front placket (the resident's vest accent colour)
                trim=(abs(v-.14)<.04)|(abs(v-.855)<.025)          # round 15: no front placket (read as a hi-vis bar)
                col[trim&vest]=color(pack,p['vest_trim_color'])
                if p['patch']:
                    patch=(u>.64)&(u<.74)&(v>.65)&(v<.78);col[patch]=color(pack,p['armband_color'])
                belt=v<.1;col[belt]=color(pack,p['belt_color'])*(.9+.1*np.sin(u*TAU*16))[belt][:,None]
            else:
                if tile==2:
                    val=.86+.16*np.sin(np.pi*v)+.08*noise(u*.6,v*.6,seed)+p['wear']*.14*np.exp(-((v-.48)/.16)**2)
                    # STEER-6: knee creases (front, v~.5), elastic waistband ribs, bunching over the boots
                    front=np.exp(-((u-.5)/.16)**2)
                    for dv,sl in ((.0,.9),(.06,-.8),(-.07,.7)):
                        val-=.22*front*np.exp(-((v-.5-dv-sl*(u-.5))/.018)**2)
                    val+=.10*front*np.exp(-((v-.53)/.05)**2)
                    val+=(.12+.07*np.sin(u*TAU*20))*(v>.9)
                    val-=.16*np.exp(-((v-.07)/.03)**2)+.10*np.exp(-((v-.16)/.025)**2)*(.6+.4*np.cos(u*TAU*3))
                if tile in (1,2):
                    folds=np.exp(-((v-.32)/.07)**2)*np.cos(u*TAU*4+v*8)*.18
                    val+=folds+.06*np.cos(u*TAU*5)*(1-v)**3
                    # Knit cuffs and trouser ankle gathers, broad shadows plus little ribs.
                    val-=.18*np.exp(-((v-.09)/.045)**2)
                    val+=.05*np.sin(u*TAU*12)*(v<.19)
                    val+=p['wear']*.1*np.exp(-((v-.49)/.17)**2)
                if tile==3:val+=.07*np.sin(u*TAU*10)-.08*(v<.18)   # knit ribs, darker cuff edge
                if tile==4:
                    val+=.12*np.exp(-((v-.38)/.12)**2)-.13*np.exp(-((v-.67)/.05)**2)
                    val+=.18*np.exp(-((v-.86)/.05)**2)          # flared cuff catches light
                if tile==5:
                    # capelet: radial drape folds, stitched hem, lit collar roll near the neck
                    val+=.12*np.cos(u*TAU*8+.7)*(1-v)**1.5-.10*np.exp(-((v-.13)/.04)**2)
                    val+=.20*np.exp(-((v-.70)/.07)**2)-.12*np.exp(-((v-.86)/.04)**2)
                    val-=.08*(np.sin(u*TAU*40)>.6)*(abs(v-.12)<.02)
                col=base[None,None,:]*val[:,:,None]
                if tile==5:col[v<.14]=color(pack,p['vest_trim_color'])       # round 16/17: accent band on the capelet hem
                if tile==4:col[v<.13]=named_ramp(pack,['chrome_1'],[.33])[0]*(.9+.1*np.sin(u*TAU*14))[v<.13][:,None]   # lighter sole band
                if tile==1 and p['armband']:col[(v>.61)&(v<.73)]=color(pack,p['armband_color'])
        else:
            c1=color(pack,p['coat_color_1']);c2=color(pack,p['coat_color_2']);c3=color(pack,p['coat_color_3']);pattern=p['coat_pattern']
            val=.86+.16*np.sin(np.pi*v)+.05*noise(u,v,seed)
            col=np.broadcast_to(c1,(N,N,3)).copy()
            if pattern in ('tuxedo','socks'):
                white=(v<.25) if tile==4 else (((u<.21)|(u>.79))&(v<.8) if tile==0 else np.zeros_like(v,dtype=bool))
                col[white]=c2
            if pattern=='tabby':col[np.sin(u*17+np.sin(v*7))>.72]=(c1*.35+c2*.65)
            if pattern=='calico':
                n=noise(u*.40,v*.42,seed+3);col[n>.14]=c2;col[n<-.28]=c3
            if pattern=='spotted':col[noise(u*2,v*2,seed)>.4]=c2
            if pattern=='saddle':col[(v>.35)&(u>.22)&(u<.78)]=c2
            if tile==3:col*=.84
            col*=val[:,:,None]
        out[mask]=col[mask]
    return quantize(out,pal)

TAU=math.pi*2

def face_atlas(pack,p,kind='human'):
    N=128 if kind=='human' else 64
    W=N;HH=64 if kind=='human' else 32
    y,x=np.mgrid[0:HH,0:W]
    if kind=='human':u=((x%32)+.5)/32;v=1-((y%32)+.5)/32;cell=x//32+(1-y//32)*4
    else:u=((x%32)+.5)/32;v=1-(y+.5)/32;cell=x//32
    pal=palette(pack);dark=pal[np.argmin(pal.sum(1))];light=pal[np.argmax(pal.sum(1))]
    if kind=='human' and p['head_mode']=='faceless':return void_atlas(pack,p)
    base=color(pack,p['skin'] if kind=='human' else p['coat_color_1'])
    val=.91+.1*np.exp(-((u-.5)/.4)**2)+.04*noise(u,v,2)
    out=base[None,None,:]*val[:,:,None]
    if kind!='human':
        c2=color(pack,p['coat_color_2'])
        if p['coat_pattern'] in ('tuxedo','calico'):out[((abs(u-.5)<.14)&(v<.61)) | (v<.32)]=c2
        if p['coat_pattern']=='tabby':out[(np.sin(u*30+v*8)>.75)&(v>.67)]=c2
    if kind!='human':
        # Species-specific almond eyes. No human eyebrows, no human mouth.
        out=base[None,None,:]*val[:,:,None]
        if p['coat_pattern'] in ('tuxedo','calico','saddle'):out[(v<.36)|((abs(u-.5)<.10)&(v<.63))]=color(pack,p['coat_color_2'])  # round 12: dog blaze/muzzle
        iris=color(pack,p['eye_color'])
        dog=p['species']=='dog'
        if dog:iris=color(pack,pack.get('dog_eye',p['eye_color'])) if pack.get('dog_eye') else dark*.6+iris*.4
        for cx in (.29,.71):
            eye=np.abs((u-cx)/.13)+((v-.59)/.08)**2 if not dog else ((u-cx)/.082)**2+((v-.59)/.082)**2
            out[eye<1.18]=dark;out[eye<.9]=iris
            if dog:
                # round 11: round dog eye - dark brown iris, round pupil, big glint; no cat slit
                out[((u-cx)/.04)**2+((v-.585)/.04)**2<1]=dark
                out[((u-cx+.025)**2+(v-.615)**2)<.0005]=light
            else:
                out[(abs(u-cx)<.019)&(eye<.95)]=dark
                out[((u-cx+.035)**2+(v-.625)**2)<.00035]=light
            closed=(cell==1)&(eye<1.25)
            out[closed]=(base[None,None,:]*val[:,:,None])[closed]
            arc=.58-.15*(1-((u-cx)/.13)**2)*.18
            out[(cell==1)&(abs(u-cx)<.115)&(abs(v-arc)<.018)]=dark
        out[(abs(u-.5)<(.055*(1-abs(v-.42)/.035)))&(abs(v-.42)<.035)]=dark
        out[(abs(u-.5)<.012)&(v>.32)&(v<.42)]=dark
        out[(abs(v-(.32+abs(u-.5)*.12))<.009)&(abs(u-.5)<.095)]=dark
        return quantize(out,pal)
    for cx in (.315,.685):
        e=((u-cx)/.112)**2+((v-.60)/.075)**2
        out[e<1.35]=dark
        out[e<.91]=light
        iris=color(pack,p['eye_color']) if kind!='human' else color(pack,p['headwear_color'])
        pupil=((u-cx+.007)/.042)**2+((v-.6)/.061)**2
        out[pupil<1]=iris;out[(abs(u-cx+.007)<.015)&(e<.85)]=dark
        out[((u-cx+.026)**2+(v-.63)**2)<.0003]=light
        # Painted eyebrow, sleepy/blink and worried cells vary only in UV cell.
        brow=.735+(cx-.5)*(u-.5)*.23*(cell==3)
        out[(abs(u-cx)<.12)&(abs(v-brow)<.018)]=dark
        blink=(cell==1)|(cell==6)
        out[(e<1.5)&blink]=np.broadcast_to(base,(HH,W,3))[(e<1.5)&blink]
        out[(abs(u-cx)<.105)&(abs(v-.60)<.018)&blink]=dark
    nose=(abs(u-.5)<(.027 if kind=='human' else .052))&(abs(v-.45)<.024);out[nose]=dark*.85
    mouthcurve=.285+.35*(u-.5)**2
    mouth=(abs(u-.5)<.11)&(abs(v-mouthcurve)<.017)
    out[mouth]=dark
    out[(((u-.5)/.07)**2+((v-.29)/.056)**2<1)&((cell==2)|(cell==5))]=dark
    if kind!='human':
        for k in (-1,0,1):
            out[(abs(v-(.37+k*.025))<.006)&((u<.27)&(u>.12)|(u>.73)&(u<.88))]=dark
    return quantize(out,pal)


def hair(pack,p):
    y,x=np.mgrid[0:64,0:64];u=(x+.5)/64;v=1-(y+.5)/64
    c=color(pack,p['headwear_color']);val=.81+.22*v+.09*np.sin(u*30+v*5)+.04*noise(u,v)
    return quantize(c[None,None,:]*val[:,:,None],palette(pack))


def envmap(pack):
    y,x=np.mgrid[0:128,0:128];u=(x+.5)/128;v=(y+.5)/128
    pal=palette(pack);ramp=np.array([color(pack,k) for k in pack.get('character_env',next(iter(pack['env_maps'].values())))['stops']])
    val=.33+.48*(1-v)+.10*np.sin(v*12)+.30*np.exp(-((u-.30)**2+(v-.25)**2)/.017)
    val-=.23*np.exp(-((v-.62)/.065)**2)
    pos=np.clip(val,0,1)*(len(ramp)-1);lo=pos.astype(int);hi=np.minimum(lo+1,len(ramp)-1);a=pos-lo
    return quantize(ramp[lo]*(1-a[:,:,None])+ramp[hi]*a[:,:,None],pal)


def void_atlas(pack,p):
    """STEER-6 hood opening (masked v2). Cell UV radius .5 = the opening rim, .34 = the recessed lining ring (both
    on the lining band), < .34 = the dished void cap. Rim: quilted pale fabric edge; lining: light at the rim,
    shading to navy inside, shadowed under the brow, three folds; an inner lip; the void itself is a navy gradient
    (navy_2 at the lip to navy_0 at the centre) with a faint catch on the lower inner wall - never the palette's
    near-black. All 8 cells identical (faceless)."""
    HH,W=64,128
    y,x=np.mgrid[0:HH,0:W];u=((x%32)+.5)/32;v=1-((y%32)+.5)/32
    d=np.sqrt((u-.5)**2+(v-.5)**2)/.5
    ang=np.arctan2(u-.5,v-.5)                 # 0 = top of the opening (under the brow)
    top=np.cos(ang)
    # round 17: charcoal-navy (wool/knit) instead of saturated navy - under the rooms' blue light the navy void read
    # as a bright blue cave; deepest knit_0 (never the palette's near-black 'void')
    ramp=named_ramp(pack,['knit_0','wool_0','wool_1','chrome_0','chrome_1','chrome_2','chrome_3','lilac_1','pearl_0','pearl_1'],
                    [.06,.11,.19,.20,.33,.49,.67,.80,.88,.94])
    t=np.clip((d-.68)/.32,0,1)
    val=.30+.38*t**1.6-.16*np.clip(top,0,1)*(1-t)                     # round 16: darker lining (the pale ring read as a porthole)
    val=np.where((np.abs(np.sin(ang*1.5+.5))<.10)&(d<.9)&(top<-.2),val-.08,val)   # lining folds, lower half only (no eye-like marks)
    rim=d>.93
    val=np.where(rim,.86+.05*np.sin(ang*22),val)                       # thin quilted rim
    val=np.where(rim&(top>.6),val-.12,val)                             # rim under the peak is in shadow
    val=np.where((d<=.68)&(d>.61),.26,val)                             # inner lip
    cap=d<=.61
    q2=np.sqrt((u-.5)**2+(v-.56)**2)/(.5*.61)                          # darkest just under the brow, not dead centre
    vv=.05+.14*np.clip(q2,0,1)**.8+.06*np.clip(-top,0,1)*d/.61         # round 15: navy_0 under the brow .. navy_2 at the lip, smooth (no pupil)
    val=np.where(cap,vv,val)
    pos=np.clip(val,0,.999)*(len(ramp)-1);lo=pos.astype(int);hi=np.minimum(lo+1,len(ramp)-1);a=pos-lo
    out=ramp[lo]*(1-a[:,:,None])+ramp[hi]*a[:,:,None]
    return quantize(out,palette(pack))


def hood(pack,p):
    """STEER-6 painted pearl/silver hood (masked v2, baked_unlit - no runtime env map needed). Loft UV: u around
    the hood (.5 = top seam, 0/1 = underside), v front->back (.25 = opening rim; v < .25 is the lining band on the
    face atlas). Pearl gradient lit from above, a bright rim catch around the opening, a stitched centre seam,
    three drape folds whose placement shifts with hood_tilt; 'matte' finish compresses the contrast."""
    N=128
    y,x=np.mgrid[0:N,0:N];u=(x+.5)/N;v=1-(y+.5)/N
    up=np.cos(TAU*(u-.5))
    tilt=float(p.get('hood_tilt',0.))
    ramp=named_ramp(pack,['chrome_1','chrome_2','chrome_3','lilac_1','pearl_0','pearl_1','white'],[.33,.49,.67,.80,.88,.94,1.])
    val=.40+.40*up+.06*np.cos(np.pi*np.clip((v-.25)/.75,0,1))
    val+=.22*np.exp(-((up-.80)/.10)**2)*np.exp(-((v-.48)/.16)**2)     # round 15: pearl highlight on the crown
    body=(v>.3)&(v<.92)
    for c0,sl,dep in ((.27+.04*tilt,.10,.18),(.73+.04*tilt,-.10,.18),(.03+.03*tilt,0.,.12)):
        dd=np.abs(((u-(c0+sl*(v-.3))+.5)%1)-.5)
        val-=dep*np.exp(-(dd/.022)**2)*body
        val+=.07*np.exp(-((dd-.04)/.02)**2)*body
    r=np.abs(u-.5)
    val+=.14*np.exp(-(r/.012)**2)*(v>.28)-.10*np.exp(-((r-.022)/.008)**2)*(v>.3)
    val+=.34*np.exp(-((v-.285)/.025)**2)*(.55+.45*np.clip(up+.3,0,1))
    val-=.10*np.clip((v-.85)/.15,0,1)
    if p.get('headwear_finish','sheen')=='matte':val=.55+.55*(val-.55)
    pos=np.clip(val,0,.999)*(len(ramp)-1);lo=pos.astype(int);hi=np.minimum(lo+1,len(ramp)-1);a=pos-lo
    out=ramp[lo]*(1-a[:,:,None])+ramp[hi]*a[:,:,None]
    return quantize(out,palette(pack))
