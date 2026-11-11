"""Blender-free draft validation and proof; approval is never granted here."""
import json
import math
from pathlib import Path
import sys
import traceback

from .blender_proof import validate_data, assemble_room, compose_sheet, style_match, sha, measure_png
from .decode import load_rgba
from . import measure_np as M


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding='utf-8'))
    pdir = Path(job['pack_dir']); proof = pdir/'proof'; proof.mkdir(exist_ok=True)
    report = {'ok':False,'stage':'setup','builder':'python','status':'draft_unapproved'}
    try:
        sys.path.append(job['kits_dir'])
        from core import pipeline,packs,schema,png
        from kits.tools import pixfont
        from adventure_maker.static_preview import theme_for,capture
        report['stage'] = 'validate'
        vrep,pack = validate_data(pipeline,packs,schema,job['pack_json'])
        report.update(vrep)
        if pack is None or not vrep['registry']['ok']:
            return report
        layout_id = job.get('layout','lounge')
        if not layout_id.isidentifier():
            raise ValueError('layout must name a shipped layout')
        layout = json.loads((Path(job['kits_dir'])/'library/layouts'/(layout_id+'.json')).read_text(encoding='utf-8'))
        report['stage'] = 'build'
        pieces,problems,checks = assemble_room(pipeline,layout,pack,job['pack_json'],str(proof/'rooms'/layout_id),str(proof/'textures'),builder='python')
        report['room'] = {'layout':layout_id,'pieces':len(pieces),
                          'expected':1+len(layout.get('openings',{}))+len(layout['fixtures']),
                          'room_tris':sum(p['tris'] for p in pieces),'problems':problems,'asset_checks':checks,
                          'piece_hashes':{p['slot']:p['sha256'] for p in pieces}}
        renders = {}
        if job.get('render',True) and pieces:
            report['stage'] = 'render'
            theme = theme_for(pack,proof/'env')
            # Same physical cameras as kits/tools/room.py, transformed to Y-up.
            views = {'main':((0,.1,.8),3.25,0,24,74),'corner':((.5,.2,.8),3.6,-40,22,70)}
            frames = []
            for name in job.get('views',['main','corner']):
                target,dist,az,el,fov = views[name]
                az,el = math.radians(az),math.radians(el)
                x,y,z = target
                eye = [x+dist*math.cos(el)*math.sin(az),z+dist*math.sin(el),-(y-dist*math.cos(el)*math.cos(az))]
                out = proof/('room_'+name+'.png'); renders[name] = str(out)
                frames.append({'pieces':pieces,'out':str(out),'theme':theme,'target':[x,z,-y],'eye':eye,'fov':fov})
            captured = capture(frames,proof/'capture',godot=job.get('godot_path'),size=tuple(job['res']),allow_software=True)
            report['renderer'] = captured.get('renderer','Godot shipped assets.gd + N64 shader')
            report['lower_fidelity'] = report['renderer']=='software_lower_fidelity'
            report['renders'] = {k:str(Path(v).relative_to(pdir)) for k,v in renders.items()}
            report['render_sha256'] = {k:sha(v) for k,v in renders.items()}
            if job.get('ref_measurements'):
                measured = M.measure([{'index':i,'srgba':measure_png(png,p),'weight':1.} for i,p in enumerate(renders.values())])
                report['style_match'] = style_match(json.loads(Path(job['ref_measurements']).read_text(encoding='utf-8')),measured)
        else:
            report.update(renderer='none',lower_fidelity=None)
        refs,labels = [],[]
        if job.get('ref_thumbnails',True):
            for r in job.get('refs',[]):
                refs.append(load_rgba(r['path'])[0]); labels.append('REF %d  %s'%(r['index'],r.get('label','')))
        sheet = compose_sheet(png,pixfont,refs,list(renders.values()),pack.d,str(proof/'proof_sheet.png'),
                              'DRAFT '+pack.id.upper()+' - '+report['renderer'].upper(),labels)
        report['proof_sheet'] = str(Path(sheet).relative_to(pdir))
        report['ok'] = bool(vrep['pack_validator']['ok'] and not problems and all(c['fail']==0 for c in checks.values()) and len(pieces)==report['room']['expected'])
        report['stage'] = 'done'
    except Exception as exc:
        report.update(ok=False,error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc()[-4000:])
    finally:
        Path(job['out']).write_text(json.dumps(report,indent=1,sort_keys=True)+'\n', encoding='utf-8')
    return report
