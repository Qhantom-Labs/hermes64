"""Runtime-shader Godot capture and explicitly lower-fidelity numpy fallback.

No engines are installed. Captures copy the runtime under the supplied output
root and confine engine cache/home/temp there. A failed installed Godot is an
error, not permission to silently substitute software or bless evidence.
"""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT/'kits') not in sys.path:
    sys.path.append(str(ROOT/'kits'))


def theme_for(pack, out):
    from core import png
    from core.texgen import make_texture
    out = Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    for name,spec in pack.env_maps.items():
        png.write(str(out/(name+'.png')),make_texture(spec,pack.pal,pack.id,name))
    fog = pack.fog
    return {'light_rig':pack.light_rig,'env_root':str(out),
            'fog':{'color':pack.d['palette'][pack.pal.idx(fog['color'])],
                   'near':fog['start'],'far':fog['end']}}


def geometry(pieces):
    from validate.glb import GLB
    for piece in pieces:
        g = GLB(piece['glb'])
        a = math.radians(piece.get('rot_y_deg',0))
        rot = np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
        for i in g.mesh_nodes():
            geo = g.node_geometry(i)
            geo['pos'] = geo['pos']@rot.T+np.array(piece.get('pos',[0,0,0]))
            yield geo


def frame(pieces, out, theme):
    points = np.concatenate([g['pos'] for g in geometry(pieces)])
    lo,hi = points.min(0),points.max(0)
    centre = (lo+hi)/2
    scale = max(float((hi-lo).max()),.1)
    return {'pieces':pieces,'out':str(Path(out).resolve()),'theme':theme,
            'target':centre.tolist(),'eye':(centre+scale*np.array([1.3,.9,1.6])).tolist(),'ortho':scale*1.65}


def software(frame, size=(320,240)):
    """Z-buffered vertex-colour preview; NO textures, chrome, fog, shader or shadows."""
    from core import png
    from kits.tools import pixfont
    width,height = size
    eye,target = np.array(frame['eye']),np.array(frame['target'])
    forward = target-eye; forward /= np.linalg.norm(forward)
    right = np.cross(forward,[0,1,0]); right /= np.linalg.norm(right)
    up = np.cross(right,forward)
    image = np.full((height,width,3),20,dtype=np.uint8)
    depth = np.full((height,width),np.inf)
    for geo in geometry(frame['pieces']):
        p = geo['pos']-eye
        z = p@forward
        if 'ortho' in frame:
            factor = np.full(len(p),height/frame['ortho'])
        else:
            factor = height/(2*math.tan(math.radians(frame.get('fov',70))/2)*np.maximum(z,1e-6))
        screen = np.column_stack([width/2+(p@right)*factor,height/2-(p@up)*factor])
        for tri in geo['idx']:
            if np.any(z[tri]<=.01): continue
            xy = screen[tri]
            low = np.maximum(np.floor(xy.min(0)).astype(int),[0,0])
            high = np.minimum(np.ceil(xy.max(0)).astype(int),[width-1,height-1])
            if np.any(high<low): continue
            yy,xx = np.mgrid[low[1]:high[1]+1,low[0]:high[0]+1]
            a,b,c = xy
            den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)<1e-8: continue
            u = ((b[1]-c[1])*(xx+.5-c[0])+(c[0]-b[0])*(yy+.5-c[1]))/den
            v = ((c[1]-a[1])*(xx+.5-c[0])+(a[0]-c[0])*(yy+.5-c[1]))/den
            weights = np.stack([u,v,1-u-v],2)
            dz = weights@z[tri]
            old = depth[low[1]:high[1]+1,low[0]:high[0]+1]
            mask = np.all(weights>=0,2)&(dz<old)
            old[mask] = dz[mask]
            rgb = np.clip(weights@geo['col'][tri,:3]*255,0,255).astype(np.uint8)
            image[low[1]:high[1]+1,low[0]:high[0]+1][mask] = rgb[mask]
    pixfont.draw_text(image,'SOFTWARE - LOWER FIDELITY - DRAFT',4,4,(255,180,80))
    png.write(frame['out'],image)
    return {'out':frame['out'],'ok':True,'renderer':'software_lower_fidelity'}


def capture(frames, out, godot=None, size=(320,240), allow_software=False, timeout=180):
    out = Path(out).resolve(); out.mkdir(parents=True,exist_ok=True)
    if godot:
        exe = shutil.which(godot)
    else:
        from .platforms import godot_candidates
        exe = next((shutil.which(c) for c in godot_candidates() if shutil.which(c)), None)
    if not exe:
        if not allow_software:
            raise RuntimeError('Godot not found; configure godot_path. No parity render can be certified with software.')
        report = {'ok':True,'renderer':'software_lower_fidelity','frames':[software(f,size) for f in frames]}
        (out/'capture.json').write_bytes(json.dumps(report,indent=1).encode('utf-8'))
        return report
    runtime = out/'runtime'
    shutil.copytree(ROOT/'runtime/godot',runtime,dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.godot','*.uid'))
    job = out/'job.json'; report_path = out/'capture.json'
    job.write_bytes(json.dumps({'frames':frames,'size':list(size),'report':str(report_path)},indent=1).encode('utf-8'))
    env = {k:os.environ[k] for k in ('PATH','LANG','LC_ALL','SystemRoot','WINDIR','PATHEXT') if k in os.environ}
    for key in ('HOME','TMPDIR','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME')+(('USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP') if os.name=='nt' else ()):
        path = out/key.lower(); path.mkdir(exist_ok=True); env[key] = str(path)
    argv = [str(Path(exe).resolve()),'--path',str(runtime),'--resolution','320x240',
            '--script','res://noblender_capture.gd','--',str(job)]
    with (out/'godot.log').open('w') as log:
        proc = subprocess.run(argv,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=timeout)
    (out/'process.json').write_bytes(json.dumps({'argv':argv,'returncode':proc.returncode},indent=1).encode('utf-8'))
    if proc.returncode or not report_path.exists():
        raise RuntimeError('Godot capture failed; configure godot_path or inspect '+str(out/'godot.log'))
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if not report['ok'] or len(report['frames'])!=len(frames):
        raise RuntimeError('Godot returned incomplete captures; see '+str(report_path))
    return report
