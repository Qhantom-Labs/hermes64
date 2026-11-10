"""Character atlas painters. All colour selections resolve through the active pack palette."""
import hashlib
import json
import numpy as np
from . import texgen
from .palette import quantize_field
from .blendio import build_material


def ramp(pack, name):
    c=np.array(pack.pal.rgb(name), dtype=float)
    idx=pack.pal.nearest_index(np.array([c*.60,c*.82,c,np.minimum(255,c*1.1+12)]))
    return pack.pal.rgb8[idx]


def tile(pack, name, pattern, n, seed, wear=0):
    f=texgen.field(pattern,n,{},seed)
    if wear:
        f=np.clip(f + wear*.2*(texgen.field('noise',n,{},seed+51)-.5),0,1)
    return quantize_field(f,ramp(pack,name),True)


def faces(pack,P):
    n=32
    atlas=np.empty((n*2,n*4,3),dtype=np.uint8)
    skin=np.array(pack.pal.rgb(P['skin']))
    ink=pack.pal.rgb8[np.argmin(pack.pal.rgb8 @ np.array([.21,.72,.07]))]
    shine=pack.pal.rgb8[np.argmax(pack.pal.rgb8 @ np.array([.21,.72,.07]))]
    for i in range(8):
        a=np.empty((n,n,3),dtype=np.uint8);a[:]=skin
        if P['head_mode']=='faceless':
            a[:]=ink
        else:
            for ex in (10,21):
                ey=13+(i//4)
                a[ey:ey+(1 if i==1 else 4),ex:ex+3]=ink
                if i!=1:a[ey,ex]=shine
                if i in (3,5):a[ey-3,ex-1:ex+4]=ink
            if i in (2,6):a[23:26,14:18]=ink
            elif i in (4,7):
                a[23,12:20]=ink;a[22,11:13]=ink;a[22,19:21]=ink
            else:a[24,14:18]=ink
        r,c=divmod(i,4);atlas[r*n:(r+1)*n,c*n:(c+1)*n]=a
    return atlas


def human_atlas(pack,P,seed):
    specs=[('top_color',P['top_pattern']),('vest_color',{'none':P['top_pattern'],'quilted_wave':'quilt_wave',
        'quilted_diamond':'quilt_diamond','leather':'leather','apron':'fabric'}[P['vest']]),
        ('bottom_color','fabric'),('boot_color','leather'),
        ('skin' if P['hands']=='bare' else 'glove_color','flat' if P['hands']=='bare' else 'knit'),
        ('skin','flat'),('mantle_color','fabric'),('skirt_color','fabric'),
        ('belt_color','leather'),('vest_trim_color','fabric'),('belt_color','leather')]
    out=np.empty((128,128,3),dtype=np.uint8)
    for i in range(16):
        key,pat=specs[i%len(specs)]
        col=P['top_color'] if i==1 and P['vest']=='none' else P[key]
        a=tile(pack,col,pat,32,seed+i,P['wear'])
        if i==0 and P['armband']:a[8:13,:]=pack.pal.rgb(P['armband_color'])
        if i==1:
            a[:,1:3]=pack.pal.rgb(P['vest_trim_color']);a[:,-3:-1]=pack.pal.rgb(P['vest_trim_color'])
            if P['patch']:a[5:12,19:26]=pack.pal.rgb(P['armband_color'])
        y,x=divmod(i,4);out[y*32:(y+1)*32,x*32:(x+1)*32]=a
    return out


def animal_atlas(pack,P,seed):
    out=np.empty((64,64,3),dtype=np.uint8)
    yy,xx=np.mgrid[:16,:16]; pat=P['coat_pattern']
    for i in range(16):
        a=tile(pack,P['coat_color_1'],'fur',16,seed+i)
        c2=pack.pal.rgb(P['coat_color_2']);c3=pack.pal.rgb(P['coat_color_3'])
        if pat=='tabby':a[((xx+yy//3)%5)<2]=c2
        elif pat=='spotted':a[((xx%6-3)**2+(yy%6-3)**2)<3]=c2
        elif pat=='calico':
            noise=texgen.field('noise',16,{},seed+i);a[noise>.6]=c2;a[noise<.3]=c3
        elif pat in ('tuxedo','saddle'):a[(yy>9) if pat=='tuxedo' else (yy<7)]=c2
        elif pat=='socks' and i==2:a[:]=c2
        if i==1:
            for ex in (4,11):
                a[5:8,ex:ex+2]=pack.pal.rgb(P['eye_color'])
        y,x=divmod(i,4);out[y*16:(y+1)*16,x*16:(x+1)*16]=a
    return out


def materials(pack,mf,ch):
    P=ch['params'];seed=ch['seed']
    sig=hashlib.sha256(json.dumps([P,seed],sort_keys=True).encode()).hexdigest()[:12]
    prefix='char_'+sig
    def textured(role,arr,kind='baked_unlit',mapping=None,extra=None):
        im=mf.image_from_array('tex_'+pack.id+'_'+prefix+'_'+role,arr)
        return build_material('mat_'+pack.id+'_'+prefix+'_'+role,{'kind':kind},pack,im,role,mapping,extra)
    if ch['skeleton']=='quad16_v1':
        return {'coat':textured('coat',animal_atlas(pack,P,seed))}
    out={'costume':textured('costume',human_atlas(pack,P,seed))}
    cell=P['face'];col,row=cell%4,cell//4
    out['face']=textured('face',faces(pack,P),'face_atlas',(col/4,(1-row)/2,.25,.5),{'atlas':{'cols':4,'rows':2,'cell':cell}})
    if P['headwear_finish']=='sheen':
        spec={'kind':'chrome_env','tint':P['headwear_color'],'env':pack.mat('metal')['env']}
        out['headwear']=build_material('mat_'+pack.id+'_'+prefix+'_headwear',spec,pack,None,'headwear')
    else:
        out['headwear']=textured('headwear',tile(pack,P['headwear_color'],'fabric',16,seed))
    out['opening']=mf.get('opening')
    return out
