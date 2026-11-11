"""One-command local demo and isolated public registration for SHIP tools."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from .schemas import COMMON, ID, obj, validate
from .safety import Fault, fail
from .service import Service
from .tools import SETTINGS, available

SHIP_SCHEMAS = {
    'hermes64_playtest': {'name':'hermes64_playtest','description':'Run bounded deterministic physical Godot winning-path/explorer probes. Local reports, heatmaps and optional real rendered frames. Cannot judge fun.',
        'parameters':obj(dict(COMMON,mode={'enum':['winning','monkey','both']},seconds={'type':'integer','minimum':1,'maximum':120},seed={'type':'integer','minimum':0,'maximum':2147483647},drought_seconds={'type':'integer','minimum':1,'maximum':120},render={'type':'boolean'}),['project'])},
    'hermes64_export': {'name':'hermes64_export','description':'Build local web/no-threads, macOS and/or Windows exports from verified portable public assets. No download/upload. Windows execution unverified on Mac.',
        'parameters':obj(dict(COMMON,targets={'type':'array','items':{'enum':['web','macos','windows']},'minItems':1,'maxItems':3},module_preview={'type':'boolean','description':'Explicit local conditional-module preview; requires a fresh complete real-input bot. No human/art/rendered/public-release approval.'}),['project','targets'])},
    'hermes64_demo': {'name':'hermes64_demo','description':'Scaffold or resume a provenance-bound bundled example; compile/check/build/playtest/export web. Local only, no installs or uploads.',
        'parameters':obj(dict(COMMON,example={'enum':['last_light','thaw','starter']},seed={'type':'integer','minimum':0,'maximum':2147483647}),['project'])}}


def register_tools(ctx):
    from .plugin_settings import plugin_settings, default_games_root
    from .newgame import NEW_SCHEMA
    from . import wire
    def handler_for(name):
        def handler(args, **kwargs):
            return handle(plugin_settings(ctx,SETTINGS),name,args,default_root=default_games_root(ctx))
        return handler
    for name,schema in SHIP_SCHEMAS.items():
        # Compact advertised copy; handle() validates against the full schemas. hermes64_demo also
        # advertises the one-command start (premise/style), validated by newgame.NEW_SCHEMA.
        extra = {k:NEW_SCHEMA['properties'][k] for k in ('premise','style')} if name=='hermes64_demo' else None
        wire.register(ctx,name,schema,handler_for(name),available,extra_properties=extra,
                      required=[] if name=='hermes64_demo' else None)


def handle(settings, name, args, default_root=None):
    service=Service(settings); project=None
    try:
        if name not in SHIP_SCHEMAS: fail('arguments','Unknown SHIP tool')
        if name=='hermes64_demo' and isinstance(args,dict) and 'premise' in args:
            from .newgame import run_tool
            return run_tool(settings,args,default_root)
        validate(args,SHIP_SCHEMAS[name]['parameters'])
        if name=='hermes64_demo':
            value=run(service,args)
            project=service.project(args['project'])
        else:
            project=service.project(args['project'])
            with project.lock():
                if name=='hermes64_playtest':
                    from .playtest import run as action
                else:
                    from .export import run as action
                value=action(service,project,args)
                if name=='hermes64_playtest' and not value.get('ok'):
                    value.update(playtest_repair(service,project,value))
        return service.response(value,project)
    except Fault as exc:
        return json.dumps(dict({'ok':False,'error':{'code':exc.code,'message':str(exc)[:2000]}},**(getattr(exc,'created',None) or {})))
    except Exception as exc:
        return json.dumps(dict({'ok':False,'error':{'code':'local_error','message':type(exc).__name__+': '+str(exc)[:2000]}},**(getattr(exc,'created',None) or {})))


def playtest_repair(service, project, value):
    """Auto-repair plan for a failed playtest: proof causes first, then module envelope lint (repair.py)."""
    from . import repair
    from .service import repair_view
    current=service.current(project)
    spec=project.read_json(current['spec'])
    report=project.read_json(value['report_path']) if project.path(value['report_path']).is_file() else {'verdict':value.get('verdict')}
    proof_path=Path(value['report_path']).parent.as_posix()+'/proof.json'
    proof=project.read_json(proof_path) if project.path(proof_path).is_file() else None
    planned=repair.plan(project.root.name,spec,current['spec'],proof=proof if proof and proof.get('status') in ('rejected','invalid') else None,
                        playtest=report,then=[{'tool':'hermes64_playtest','args':{'project':project.root.name},'why':'play it again'}])
    return {'next':planned['next'],'repair':repair_view(planned)}


def run(service,args):
    """The bundled example under project=NAME: scaffolded when the name is free, else RESUMED when that folder is this
    demo's own unchanged project. REUSE: the reply says which (created / resumed), with project_dir, seconds and
    assets_built; a failure says whether this call made the folder."""
    started=time.monotonic(); state={'made':False,'dir':None}
    try:
        return _run(service,args,started,state)
    except Exception as exc:
        setattr(exc,'created',{'created':state['made'],'project_dir':state['dir'],'assets_built':False,
                               'seconds':round(time.monotonic()-started,3)})
        raise


def _run(service,args,started,state):
    from . import playtest, export
    example=args.get('example','last_light'); seed=args.get('seed',7); name=args['project']
    # Establish configured project boundary before attempting any writes.
    root=service.settings.get('projects_root','')
    if not root or not Path(root).is_absolute() or not Path(root).is_dir(): fail('configuration','Choose an existing absolute projects_root; nothing created.')
    bundle=Path(service.settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    stages=[]
    def call(stage,payload):
        begin=time.monotonic()
        result=json.loads(service.handle('hermes64_'+stage,dict(project=name,**payload)))
        if result.get('truncated'): result=service.project(name).read_json(result['report_path'])
        stages.append({'stage':stage,'seconds':round(time.monotonic()-begin,3),'status':result.get('status',result.get('error'))})
        if not result.get('ok'): fail('demo_'+stage,json.dumps(result)[:1800])
        return result
    exists=(Path(root)/name).exists()
    state['dir']=str(Path(root)/name) if exists else None
    if exists:
        project=service.project(name)
        if not project.path('.maker/demo.json').is_file(): fail('demo_conflict','Existing project is not owned by this demo; choose a new name.')
        marker=project.read_json('.maker/demo.json')
        if marker.get('example')!=example or marker.get('seed')!=seed: fail('demo_conflict','Existing demo has different example/seed; use a new name.')
        if hashlib.sha256(project.path('source/spec.json').read_bytes()).hexdigest()!=marker['source_sha256']:
            fail('demo_conflict','Demo source was edited; refusing to reset it.')
        if project.path('.maker/current.json').is_file():
            cur=service.current(project)
            if project.read_json(cur['spec'])!=project.read_json('source/spec.json'): fail('demo_conflict','Current revision was edited; refusing to reset it.')
    else:
        if example=='starter':
            payload={'premise':'Recover the keepsake and return.','pack':'n64_v0'}
        else:
            if '.' in (__package__ or ''):
                from ..characters.integration import apply_presentation
            else:
                from characters.integration import apply_presentation
            spec=json.loads((bundle/'examples'/example/'spec.json').read_text(encoding='utf-8'))
            # Exactly the bundled showcase presentation; logical source fields are unchanged.
            spec=apply_presentation(spec,example)
            payload={'spec_json':json.dumps(spec),'pack':{'last_light':'n64_v0','thaw':'polar_pod'}[example]}
        call('scaffold',payload)
        state.update(made=True,dir=str(Path(root)/name))
        project=service.project(name)
        project.write_json('.maker/demo.json',{'example':example,'seed':seed,'source_sha256':hashlib.sha256(project.path('source/spec.json').read_bytes()).hexdigest()})
    call('compile',{'spec_path':'source/spec.json'}); call('check',{}); call('build_assets',{'seed':seed})
    with project.lock():
        begin=time.monotonic(); tested=playtest.run(service,project,{'mode':'both','seconds':20,'seed':seed})
        stages.append({'stage':'playtest','seconds':round(time.monotonic()-begin,3),'status':tested['status'],'report_path':tested['report_path']})
        # Keep the failing physical report; never export a demo falsely labelled passing.
        if not tested['ok']: fail('demo_playtest','Physical playtest '+tested['status']+'; inspect '+tested['report_path'])
        begin=time.monotonic(); exported=export.run(service,project,{'targets':['web']})
        stages.append({'stage':'export_web','seconds':round(time.monotonic()-begin,3),'status':exported['status'],'report_path':exported['report_path']})
        result={'ok':True,'status':'demo_ready_local','example':example,'project_dir':str(project.root),'seconds':round(time.monotonic()-started,3),'stages':stages,'playtest':tested,'export':exported,'report_path':'.maker/demo-latest.json','limits':['Browser execution is a separate smoke test.','Cannot judge human fun.','No upload or public release.'],
                'created':not exists,'resumed':exists,'assets_built':True}
        if exists:
            result['note']=('Resumed the existing %s demo project at %s (made by an earlier call); no new project was created. '
                            'Its source was unchanged, so it was rebuilt and re-checked in place.' % (example,project.root))
        project.write_json('.maker/demo-latest.json',result)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--projects-root',default=str(Path.cwd()),help='existing owner-chosen root; CLI default is the current directory'); p.add_argument('--project',default='hermes64-demo'); p.add_argument('--example',choices=['last_light','thaw','starter'],default='last_light'); p.add_argument('--seed',type=int,default=7)
    a=p.parse_args(argv)
    result=json.loads(handle({'projects_root':a.projects_root,'python_path':sys.executable},'hermes64_demo',{'project':a.project,'example':a.example,'seed':a.seed}))
    if not result.get('ok'):
        print('HERMES64 DEMO FAILED: '+json.dumps(result.get('error',result)),file=sys.stderr)
        return 1
    print('HERMES64 — local demo ready\nProject: '+result['project_dir'])
    for row in result['stages']: print('{stage:16} {seconds:8.3f}s  {status}'.format(**row))
    print('Total: %.3fs (cold target ~600s; measured, not guaranteed)' % result['seconds'])
    print('Playtest: '+result['playtest']['verdict']+' — '+str(Path(result['project_dir'])/result['playtest']['html_path']))
    print('Web/share: '+str(Path(result['project_dir'])/result['export']['share_path']))
    print('ZIP: '+str(Path(result['project_dir'])/result['export']['zip_path']))
    print('Local only. No upload. Browser/other-machine execution and human fun require separate verification.')
    return 0

if __name__=='__main__': sys.exit(main())
