"""Native conditional-module replay; never credit analysis assumptions as inputs."""
from .runner import locate
from .safety import fail


def verify_movie(component, runtime, movie, folder):
    project=component.project
    project.path(folder).mkdir(parents=True,exist_ok=True)
    config={'movie':str(project.path(movie)), 'report':str(project.path(folder+'/native.json')),
            'save':str(project.path(folder+'/checkpoint.json'))}
    project.write_json(runtime+'/author-replay-config.json',config)
    argv=[locate('godot',component.settings.get('godot_path','')),'--headless','--fixed-fps','60','--disable-vsync',
          '--path',str(project.path(runtime)),'--script','res://tests/author_module_replay.gd']
    process=component.runner.run(argv,project.root,timeout=180)
    project.write_json(folder+'/process.json',dict(process,argv=argv))
    report=project.read_json(folder+'/native.json')
    result=dict(report.get('movie',{}),save_round_trip=report.get('save_round_trip',False),endings=report.get('endings',[]),game_hash=report.get('game_hash'))
    result['ok']=bool(report.get('ok') and process['returncode']==0 and not any(t in process['stderr']+process['stdout'] for t in ('SCRIPT ERROR','ERROR:','CRASH')))
    return result


def run(service, project, current, proof, folder):
    from .adapters import Components
    from .module_playtest import physical
    game=project.read_json(current['game'])
    if game.get('contract_version')!='1.2.0' or proof['status']!='conditional':
        fail('unproved','Module replay requires explicit STORY 1.2 conditional proof.')
    component=Components(service.settings,project)
    tested=physical(project,service.settings,current['game'],proof,folder+'/physical',False)
    required={m['id'] for m in game['gameplay']['modules'] if m['id'] in ('combat','course','regions')}
    if tested.get('verdict') not in ('PLAYABLE','SOLID') or not tested.get('completed') or not required.issubset(tested.get('modules_tested',[])):
        fail('module_replay_unplayed','Fresh physical module paths did not pass; inspect '+folder+'/physical/report.json')
    movies=tested.get('replay_files',[])
    if len(movies)!=1:
        fail('module_replay_missing','Expected one complete module movie; inspect physical report.')
    movie=folder+'/physical/'+movies[0]
    played=verify_movie(component,folder+'/physical/runtime',movie,folder+'/verify')
    endings={id:{'status':'passed' if row.get('passed') else 'failed'} for row in tested.get('paths',[]) if (id:=row.get('ending'))}
    expected=set(proof.get('endings',{}))
    # Current module runner records one continuous run. Refuse multi-ending coverage it cannot reproduce.
    good=bool(played.get('ok') and played.get('save_round_trip') and played.get('game_hash')==game['game_hash'] and
              set(endings)==expected and all(row['status']=='passed' for row in endings.values()) and
              len(expected)==1 and set(played.get('endings',[]))==expected)
    report=dict(status='passed' if good else 'failed',game_hash=game['game_hash'],proof_status='conditional',
                save_round_trip=played.get('save_round_trip',False),movie=played,movie_path=movie,endings=endings,
                physical={'verdict':tested['verdict'],'report_path':folder+'/physical/report.json','modules_tested':tested['modules_tested']},
                scope='Fresh real-input completion plus strict recorded movie checkpoint hashes and initial disk save round-trip. Logical status stays conditional; no human balance or multi-ending module claim.')
    project.write_json(folder+'/replay.json',report)
    return {'ok':good,'status':report['status'],'replay':report,'report_path':folder+'/replay.json'}
