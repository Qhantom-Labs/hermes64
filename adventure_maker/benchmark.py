"""A sequential measured edit benchmark; never counts unrun checks as passed."""
from pathlib import Path
from .adapters import Components
from .packs import Packs
from .schemas import OPERATION, validate
from .safety import strict_json, fail, Fault

def look_gate(service,project,components,revision):
    """Render the revision (bounded Godot capture) and run the measured style gate; a failed render is a failure."""
    import json
    from . import style_gate
    folder=service.folder(project,'benchmark-look')
    try:
        result=components.open(revision['game'],folder,60,True)
    except Fault as exc:
        return {'status':'failed','reason':str(exc)}
    capture=result.get('capture')
    if not isinstance(capture,dict) or capture.get('status')!='passed':
        return {'status':'failed','reason':'capture did not pass'}
    theme=json.loads(Path(result['theme_path']).read_text(encoding='utf-8')) if Path(result.get('theme_path','')).is_file() else {}
    gate=style_gate.gate_directory(project.path(folder+'/screens'),theme)
    project.write_json(folder+'/style-gate.json',gate)
    return {'status':gate['status'],'report_path':folder+'/style-gate.json','failed_rooms':[r['id'] for r in gate['rooms'] if r['status']!='passed'],'scope':gate['scope']}

def run(service,project,args):
    operations=strict_json(args['operations_json'])
    validate(operations,{'type':'array','items':OPERATION,'minItems':1,'maxItems':20})
    if any('expected_changed_rooms' not in o for o in operations): fail('arguments','Every benchmark operation requires expected_changed_rooms; no self-grading locality')
    folder=service.folder(project,'benchmark'); current=service.current(project); original=project.path('.maker/current.json').read_bytes()
    save=args.get('save_path'); rows=[]; components=Components(service.settings,project)
    for index,op in enumerate(operations):
        row={'index':index+1,'operation':op,'valid_output':False,'passed':False}
        try:
            result,revision=service.edit_candidate(project,current,op,save)
            reg=result['regression'];row.update(valid_output=result['ok'],revision=revision,regression=reg)
            reg['runtime_replay']={'status':'not_run'}
            if result['ok']:
                if args['build_assets']:
                    reg['style_validation']=components.assets(revision['game'],service.folder(project,'benchmark-assets'),7,Packs(service.settings,project).selected(project.read_json(revision['spec'])))
                migrated=str(Path(revision['spec']).parent/'save.json') if save and reg['save_migration']['status'] in ('as_is','migrated') else None
                try:
                    replay_folder=service.folder(project,'benchmark-replay')
                    proof=replay_folder+'/proof.json';components.check(revision['game'],proof)
                    reg['runtime_replay']=components.replay(revision['game'],proof,replay_folder,migrated)
                except Fault as exc:
                    reg['runtime_replay']={'status':'failed','code':exc.code,'reason':str(exc)}
                current=revision;save=migrated
                checks=[reg['identity_preserved'],reg['unchanged_byte_identical'],reg['expected_room_locality']=='passed',reg['solvability']['status']=='proved',reg['save_migration']['status'] in ('as_is','migrated'),reg['style_validation']['status']=='passed',reg['runtime_replay']['status']=='passed']
                if args.get('style_gate'):
                    reg['style_gate']=look_gate(service,project,components,revision)
                    checks.append(reg['style_gate']['status']=='passed')
                row['passed']=all(checks)
        except Fault as exc: row['error']={'code':exc.code,'message':str(exc)}
        rows.append(row)
        project.write_json(folder+'/rows.json',rows)
    valid=sum(r['valid_output'] for r in rows); passed=sum(r['passed'] for r in rows)
    unchanged=project.path('.maker/current.json').read_bytes()==original
    complete=passed==len(rows) and unchanged
    status='passed' if complete else ('partial' if valid==len(rows) else 'failed')
    report={'status':status,'count':len(rows),'valid_output_passed':valid,'fully_verified_passed':passed,'results':rows,'live_revision_unchanged':unchanged,'runtime_replay':'per_revision; inspect each row','scope':'Explicit listed edits only; not arbitrary-language editing, character fidelity or human-feel proof'}
    project.write_json(folder+'/benchmark.json',report)
    return {'ok':complete,'status':status,'benchmark':report,'report_path':folder+'/benchmark.json'}
