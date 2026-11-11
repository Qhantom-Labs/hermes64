"""Data-only world outline compiler and design lint. No model, scripts, installs or network.

python3 -B -m adventure_maker.author --help
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

from .safety import strict_json

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
WALLS = ('north', 'east', 'south', 'west')


class AuthorError(ValueError):
    """An actionable author-facing admission error, never an automatic repair."""


def fields(value, allowed, required=(), where='outline'):
    if not isinstance(value, dict):
        raise AuthorError(where + ': expected a JSON object.')
    extra = sorted(set(value) - set(allowed))
    missing = sorted(set(required) - set(value))
    if extra:
        raise AuthorError('Unknown fields in ' + where + ': ' + ', '.join(extra))
    if missing:
        raise AuthorError(where + ': missing ' + ', '.join(missing))


def identity(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise AuthorError(repr(value) + ': use lowercase letters, digits and underscores; start with a letter. IDs are never renamed for you.')
    return value


def rows(value, where):
    if not isinstance(value, list) or len(value) > 100:
        raise AuthorError(where + ': expected an array of at most 100 entries.')
    return value


def index(values, where):
    out = {}
    for row in rows(values, where):
        if not isinstance(row, dict) or 'id' not in row:
            raise AuthorError(where + ': every entry needs an id.')
        key = identity(row['id'])
        if key in out:
            raise AuthorError('Duplicate ' + where + ' id: ' + key)
        out[key] = row
    return out


def library():
    return strict_json((Path(__file__).with_name('author_patterns.json')).read_bytes())


def expand(world):
    world = copy.deepcopy(world)
    patterns = library()['patterns']
    for instance in rows(world.pop('patterns', []), 'patterns'):
        fields(instance, ('use', 'args'), ('use', 'args'), 'pattern instance')
        name = instance['use']
        if name not in patterns:
            raise AuthorError('Unknown author pattern: ' + str(name))
        pattern = patterns[name]
        args = instance['args']
        fields(args, pattern['args'], pattern['args'], 'pattern ' + name)
        def substitute(value):
            if isinstance(value, str) and re.fullmatch(r'\$\{[a-z_]+\}', value):
                return copy.deepcopy(args[value[2:-1]])
            if isinstance(value, list):
                return [substitute(v) for v in value]
            if isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            return value
        for collection, entries in substitute(pattern['emit']).items():
            world.setdefault(collection, []).extend(entries)
    return world


def catalog(pack, root=ROOT):
    from .packs import Packs
    pack_data = Packs({'bundle_root': str(root)}).get(pack)
    assets = strict_json((root / 'packs' / pack_data['kit_pack_id'] / 'bindings.json').read_bytes())['assets']
    cast = [r for r in strict_json((root / 'bindings.json').read_bytes())['characters']
            if r.get('public_release') and not r.get('internal_only') and not r.get('placeholder')]
    return {'pack': pack, 'assets': sorted(assets), 'cast': [{'id': r['character_id'], 'body': r['body_id']} for r in cast]}


def anchor(value, room, where):
    if not isinstance(value, list) or len(value) != 3 or any(type(v) not in (float, int) for v in value):
        raise AuthorError(where + ': anchor must be [x, y, z] metres.')
    w, d = room['grid_size']
    if not (0.5 <= value[0] <= w-0.5 and 0 <= value[1] <= 2 and 0.5 <= value[2] <= d-0.5):
        raise AuthorError(where + ': anchor outside the safe room interior. Keep x/z at least 0.5 m from walls and y in 0..2.')
    return value


def cutaway(room):
    """Neutral kit modules, split around actual doors; collision stays with the runtime.

    These are deliberately modest cutaways, not themed bespoke architecture.
    """
    w, d = room['grid_size']
    pieces = []
    for wall in WALLS:
        length = w if wall in ('north', 'south') else d
        spans = [(max(0, dr['position']-0.25), min(length, dr['position']+1.25))
                 for dr in room['doors'] if dr['wall'] == wall]
        cursor = 0
        for lo, hi in sorted(spans) + [(length, length)]:
            if lo > cursor:
                mid = (lo+cursor)/2
                at = {'north':[mid,0,0], 'south':[mid,0,d], 'west':[0,0,mid], 'east':[w,0,mid]}[wall]
                pieces.append({'asset':'_wall', 'position':at, 'scale':[(lo-cursor)/2,0.32 if wall == 'south' else 1,1],
                               'yaw':{'north':0,'east':-90,'south':180,'west':90}[wall], 'kind':'wall'})
            cursor = max(cursor, hi)
    return pieces


def compile_outline(world, root=ROOT):
    """Return a new valid STORY 1.1/1.2 spec. Logical rejection is lint, not schema admission."""
    allowed = ('format','id','title','brief','pack','start','hero','rooms','links','cast','items','flags','actions',
               'dialogues','quests','endings','courses','patterns','mood')
    fields(world, allowed, ('format','id','title','brief','pack','start','hero','rooms','cast','endings'))
    if world['format'] != 'hermes64-world/1':
        raise AuthorError('Unsupported outline format; use hermes64-world/1.')
    world = expand(world)
    identity(world['id'])
    room_rows = index(world['rooms'], 'rooms')
    if not room_rows:
        raise AuthorError('Add at least one room.')
    def need_room(id):
        if id not in room_rows:
            raise AuthorError(str(id) + ': no such room; declare it in rooms before linking or placing anything.')
    need_room(world['start'])
    known = catalog(world['pack'], root)
    cast_rows = {r['character_id']:r for r in strict_json((root/'bindings.json').read_bytes())['characters']
                 if r.get('public_release') and not r.get('internal_only') and not r.get('placeholder')}
    s = {'contract_version':'1.1.0','id':world['id'],'title':world['title'],'description':world['brief'],
         'metadata':{'authoring':'hermes64-world/1','protagonist':world['hero'],'presentation':{'rooms':{}},
                     'asset_disclosure':{'cast':'Explicit reused public cast, not bespoke characters.', 'architecture':'Neutral kit-module cutaways; review the runtime.'}},
         'start':{'location':world['start'],'inventory':[],'flags':{},'dialogue':{},'collected':[], 'tide':{'state':'still','tick':0}},
         'rooms':[],'characters':[],'items':[],'flags':[],'interactions':[],'dialogues':[],'quests':[],'endings':[],
         'collectible_groups':[],'collectibles':[],
         'tide':{'id':'cycle','states':[{'id':'still','label':'Still','duration':1}], 'wait_label':'Wait','wait_text':'A moment passes.'}}
    rooms = {}
    for rid, row in room_rows.items():
        fields(row, ('id','name','description','size','outdoors','pieces','look','camera'), ('id','name'), 'room '+rid)
        size = row.get('size', [10,10])
        if not isinstance(size,list) or len(size)!=2 or any(type(n) is not int or not 4<=n<=16 for n in size):
            raise AuthorError('Room '+rid+': size must be two whole metres in 4..16.')
        r = dict(id=rid,name=row['name'],description=row.get('description',row['name']),grid_size=size,kit_refs=[],doors=[],props=[],character_ids=[],
                 cameras=[dict(id='main',position=[size[0]/2,8,size[1]+3],look_at=[size[0]/2,0,size[1]/2])])
        if 'camera' in row:
            fields(row['camera'], ('position','look_at'), ('position','look_at'), 'camera '+rid)
            r['cameras'][0].update(row['camera'])
        rooms[rid]=r; s['rooms'].append(r)
    used=set()
    for row in rows(world.get('links',[]),'links'):
        fields(row, ('a','b','when','back_when','position','back_position','label','back_label'), ('a','b'), 'link')
        ends=[]
        for key, pos_key in [('a','position'),('b','back_position')]:
            try: rid, wall = row[key].split(':')
            except (ValueError,AttributeError): raise AuthorError('Link endpoint must be room:north|east|south|west.')
            need_room(rid)
            if wall not in WALLS: raise AuthorError('Unknown wall '+wall+' on room '+rid)
            size=rooms[rid]['grid_size'][0 if wall in ('north','south') else 1]
            pos=row.get(pos_key, size//2)
            if type(pos) is not int or not 0<=pos<size: raise AuthorError('Door position outside room '+rid)
            if (rid,wall,pos) in used: raise AuthorError('A door slot is already occupied in '+rid+' on '+wall+'. Choose another position.')
            used.add((rid,wall,pos)); ends.append((rid,wall,pos))
        for i, (rid,wall,pos) in enumerate(ends):
            other=ends[1-i][0]; did='to_'+other
            if any(dr['id']==did for dr in rooms[rid]['doors']): raise AuthorError('A door to '+other+' already exists in '+rid+'; use an intermediate room for parallel links.')
            rooms[rid]['doors'].append(dict(id=did,wall=wall,position=pos,to_room=other,to_door='to_'+rid,
                                           label=row.get('label' if i==0 else 'back_label','Enter '+rooms[other]['name']),
                                           conditions=copy.deepcopy(row.get('when' if i==0 else 'back_when',[]))))
    moods=library()['moods']
    if world.get('mood') and world['mood'] not in moods: raise AuthorError('Unknown mood '+str(world['mood'])+'; inspect patterns for supported data presets.')
    for rid,row in room_rows.items():
        p={'exterior':row.get('outdoors',False),'kit_shell':True,'pieces':cutaway(rooms[rid]),'interactions':{},'characters':{}}
        if row.get('outdoors'): p['pieces']=[]
        p['look']=copy.deepcopy(moods.get(world.get('mood'),{}))
        p['look'].update(copy.deepcopy(row.get('look',{})))
        # Restrict this convenience surface to consumed controls, not arbitrary metadata wiring.
        fields(p['look'], ('fog','background','grade','ambient','key','fill','key_dir','fill_dir','bake_desaturate'), where='room look '+rid)
        if 'grade' in p['look']:
            fields(p['look']['grade'], ('contrast','saturation','gamma','exposure','lift','gain'), where='grade '+rid)
        for piece in rows(row.get('pieces',[]),'pieces '+rid):
            fields(piece, ('asset','position','scale','yaw','kind','mounted'), ('asset','position'), 'piece '+rid)
            if piece['asset'] not in known['assets']: raise AuthorError(str(piece['asset'])+' is not bound in '+world['pack']+'; inspect catalog. No substitution was made.')
            p['pieces'].append(copy.deepcopy(piece))
        s['metadata']['presentation']['rooms'][rid]=p
    for cid,row in index(world['cast'],'cast').items():
        fields(row, ('id','name','role','asset','room','at'), ('id','name','role','asset'), 'cast '+cid)
        if row['asset'] not in cast_rows: raise AuthorError(str(row['asset'])+' is not available in public cast; inspect catalog. No substitution was made.')
        binding=cast_rows[row['asset']]; params=copy.deepcopy(binding['params'])
        s['characters'].append(dict(id=cid,name=row['name'],role=row['role'],body_id=binding['body_id'],base_rig_id=binding['base_rig_id'],params=params,role_profiles={row['role']:copy.deepcopy(params)}))
        if row.get('room'):
            rid=row['room']; need_room(rid); rooms[rid]['character_ids'].append(cid)
            at=anchor(row.get('at',[2,0,2]),rooms[rid],'cast '+cid)
            s['metadata']['presentation']['rooms'][rid]['characters'][cid]={'position':at}
    if world['hero'] not in {c['id'] for c in s['characters']}: raise AuthorError('hero must name a declared cast id; no placeholder protagonist will be inserted.')
    for id,row in index(world.get('items',[]),'items').items():
        fields(row, ('id','name','description','asset'), ('id','name'), 'item '+id)
        s['items'].append(dict(id=id,name=row['name'],description=row.get('description',row['name']),asset=row.get('asset','inventory/'+id)))
    fields(world.get('flags',{}), world.get('flags',{}), where='flags')
    for id,value in world.get('flags',{}).items():
        identity(id)
        if type(value) is not bool: raise AuthorError('Flag '+id+' initial value must be true or false, not a counter.')
        s['flags'].append(dict(id=id,initial=value,description=id.replace('_',' '))); s['start']['flags'][id]=value
    actions=copy.deepcopy(world.get('actions',[]))
    for id,row in index(world.get('dialogues',[]),'dialogues').items():
        fields(row, ('id','character','room','at','nodes','label'), ('id','character','room','nodes'), 'dialogue '+id)
        need_room(row['room'])
        nodes=[]
        for nid,node in index(row['nodes'],'dialogue nodes').items():
            fields(node, ('id','text','when','choices'), ('id','text','choices'), 'dialogue node '+nid)
            choices=[]
            for choice in rows(node['choices'],'choices'):
                fields(choice, ('id','text','when','effects','next'), ('id','text'), 'choice')
                choices.append(dict(id=choice['id'],text=choice['text'],conditions=choice.get('when',[]),effects=choice.get('effects',[]),next=choice.get('next','')))
            nodes.append(dict(id=nid,text=node['text'],conditions=node.get('when',[]),choices=choices))
        if not nodes: raise AuthorError('Dialogue '+id+' needs at least one node.')
        s['dialogues'].append(dict(id=id,character=row['character'],start_node=nodes[0]['id'],nodes=nodes)); s['start']['dialogue'][id]=''
        actions.append(dict(id='talk_'+id,room=row['room'],at=row.get('at',[3,0,3]),kind='talk',target=row['character'],
                            label=row.get('label','Speak with '+row['character']),effects=[{'dialogue':id,'node':nodes[0]['id']}]))
    item_ids={x['id'] for x in s['items']}; char_ids={x['id'] for x in s['characters']}
    for id,row in index(actions,'actions').items():
        fields(row, ('id','room','label','text','kind','target','when','effects','at'), ('id','room','label','effects'), 'action '+id)
        rid=row['room']; need_room(rid); kind=row.get('kind','use'); target=row.get('target',id)
        if kind=='take' and target not in item_ids: raise AuthorError('Action '+id+': take target must name a declared item.')
        if kind=='talk' and target not in char_ids: raise AuthorError('Action '+id+': talk target must name a declared character.')
        s['interactions'].append(dict(id=id,room=rid,kind=kind,target=target,label=row['label'],text=row.get('text',row['label']),conditions=row.get('when',[]),effects=row['effects']))
        at=anchor(row.get('at',[rooms[rid]['grid_size'][0]/2,0,rooms[rid]['grid_size'][1]/2]),rooms[rid],'action '+id)
        s['metadata']['presentation']['rooms'][rid]['interactions']['interact:'+id]={'position':at}
    for id,row in index(world.get('quests',[]),'quests').items():
        fields(row, ('id','title','description','when'), ('id','title','description','when'), 'quest '+id)
        s['quests'].append(dict(id=id,title=row['title'],description=row['description'],conditions=row['when']))
    for id,row in index(world['endings'],'endings').items():
        fields(row, ('id','text','when'), ('id','text','when'), 'ending '+id)
        s['endings'].append(dict(id=id,text=row['text'],conditions=row['when']))
    if world.get('courses'): add_courses(s,world['courses'],rooms)
    try:
        from .export import _puzzle_api
        api,_,_=_puzzle_api(); api.compile_spec(s)
    except (ValueError,TypeError,KeyError) as exc:
        raise AuthorError('Story contract refused this design: '+str(exc)+'. Fix the named record; no fields were guessed.') from exc
    return s


def add_courses(spec, courses, rooms):
    tracks=[]; challenges=[]; checkpoints=[]
    for id,row in index(courses,'courses').items():
        fields(row, ('id','room','start','checkpoints','deadline_ticks','par_ticks','countdown_ticks','when'),
               ('id','room','start','checkpoints','deadline_ticks','par_ticks'), 'course '+id)
        rid=row['room']
        if rid not in rooms: raise AuthorError(rid+': course room is missing.')
        at=anchor(row['start'],rooms[rid],'course start '+id)
        checkpoint=id+'_safe'; subject=id+'_track'
        checkpoints.append(dict(id=checkpoint,room=rid,position_m=at))
        challenges.append(dict(id=id,room=rid,kind='course',subject=subject,checkpoint=checkpoint,conditions=row.get('when',[]),retry='checkpoint',rewards={'items':[],'abilities':[]}))
        points=[dict(id='mark_'+str(i+1),position_m=anchor(p,rooms[rid],'course checkpoint'),radius_m=0.8) for i,p in enumerate(rows(row['checkpoints'],'course checkpoints'))]
        tracks.append(dict(id=subject,room=rid,start_position_m=at,checkpoints=points,countdown_ticks=row.get('countdown_ticks',60),par_ticks=row['par_ticks'],time_limit_ticks=row['deadline_ticks'],laps=1,pause_policy='freeze'))
    # A real safe start is required even if the first challenge starts in a different room.
    safe=next((c['id'] for c in checkpoints if c['room']==spec['start']['location']),None)
    if safe is None:
        safe='author_start'; checkpoints.append(dict(id=safe,room=spec['start']['location'],position_m=[2,0,2]))
    spec['contract_version']='1.2.0'
    spec['start']['modules']=dict(abilities=[],completed=[],active='',failed='',checkpoint=safe,discovered=[])
    spec['gameplay']=dict(api_version='1.0.0',seed=7,verification_policy='conditional',modules=[
        dict(id='abilities',version='1.0.0',config={'max_health':6},entities={'abilities':[]}),
        dict(id='challenge',version='1.0.0',config=dict(max_active=1,entry_cost='none',failure_progress='unchanged'),entities=dict(challenges=challenges,checkpoints=checkpoints)),
        dict(id='course',version='1.0.0',config=dict(mover='on_foot',max_speed_mps=4,simulation_hz=60),entities={'tracks':tracks})])


def lint(spec):
    """Bounded exact logic plus explainable structural heuristics, not a fun score."""
    from .export import _puzzle_api
    api,_,_=_puzzle_api()
    issues=[]
    def issue(code,severity,message): issues.append(dict(code=code,severity=severity,message=message))
    try:
        proof=api.check_game(api.compile_spec(spec),max_states=100000)
    except (ValueError,TypeError,KeyError) as exc:
        return {'ok':False,'proof_status':'invalid','issues':[dict(code='contract',severity='error',message=str(exc))],'scope':'Design diagnostics, not a fun verdict.'}
    status=proof['status']
    if status in ('rejected','invalid','inconclusive'):
        issue('unplayable' if status=='rejected' else status,'error',
              'The checker '+status+' this design: inspect unreachable endings, self-locked keys, overlapping endings, permanent loss and one-way gates. '+str(proof.get('failures',proof.get('reason','')) )[:1500])
    if status=='rejected':
        for id,row in proof.get('endings',{}).items():
            if not row.get('reachable'):
                issue('unreachable_ending','error','Ending '+id+' cannot be reached: '+row.get('reason','no reachable state satisfies its conditions')+'. Check its trigger and the route to that trigger.')
        for row in proof.get('missing_prerequisites',[])[:20]:
            needs=[]
            for condition in row.get('conditions',[]):
                if 'item' in condition:
                    needs.append(('carry ' if condition['present'] else 'not carry ')+condition['item'])
                elif 'flag' in condition:
                    needs.append(condition['flag']+' must be '+str(condition['equals']).lower())
                else:
                    needs.append(json.dumps(condition,sort_keys=True))
            issue('blocked_prerequisites','error',row['path']+' cannot be enabled in any reachable context'+('; needs '+', '.join(needs) if needs else ' (the room or dialogue context itself is unreachable)')+'. Move its producer before the gate or restore a return route. At most 20 blocked records are shown; the full proof is retained.')
        if proof.get('softlock_count'):
            issue('softlock','error',str(proof['softlock_count'])+' reachable state(s) have no route to any ending. Inspect proof.softlocks for exact states and witnesses; do not add an always-true ending to hide the trap.')
        if proof.get('ambiguous_terminal_count'):
            issue('overlapping_endings','error','Multiple endings match the same reachable state. Use mutually exclusive explicit finish triggers.')
    if status=='conditional': issue('skill_assumptions','warning','Logic depends on named skill assumptions. A real-input bot and replay must complete each module; this is not human feasibility proof.')
    if len(spec.get('rooms',[]))<3: issue('small_world','warning','Fewer than three rooms. A focused course can be valid; an exploration game may lack discovery.')
    if not any(d.get('conditions') for r in spec.get('rooms',[]) for d in r['doors']) and not spec.get('dialogues') and not spec.get('gameplay'):
        issue('shallow_finish','warning','No gated travel, dialogue or mechanic. The ending may be a walk to an unconditional button; add a meaningful decision or transformation, not more empty rooms.')
    if len(spec.get('endings',[]))==1 and not spec.get('dialogues'): issue('linear','warning','One ending and no conversations. Consider an optional branch or a clue that changes how the player proceeds.')
    if any(not e['conditions'] for e in spec.get('endings',[])): issue('instant_ending','warning','An unguarded ending terminates immediately. Add an explicit finish trigger if that is not intended.')
    by_room=spec.get('metadata',{}).get('presentation',{}).get('rooms',{})
    for r in spec.get('rooms',[]):
        pieces=by_room.get(r['id'],{}).get('pieces',[])
        if not pieces: issue('bare_room','warning','Room '+r['id']+' has no authored scenery. Check floor, landmarks, door silhouettes and the actual runtime.')
        if not any(p.get('kind','piece') not in ('wall','floor','ceiling','shell') for p in pieces):
            issue('undressed_room','warning','Room '+r['id']+' has only structure, not a landmark or meaningful scenery. Generated walls do not make a distinct place; add a visible clue, destination or purposeful prop.')
    for a in spec.get('interactions',[]):
        if 'interact:'+a['id'] not in by_room.get(a['room'],{}).get('interactions',{}): issue('unanchored','warning','Action '+a['id']+' has no physical anchor. Logical reachability does not show where to walk.')
    return dict(ok=status in ('proved','conditional'),proof_status=status,issues=issues,proof=proof,scope='Bounded logic and structural heuristics, not a fun verdict. Captures are not art approval.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('compile'); p.add_argument('outline'); p.add_argument('--out',required=True)
    p=sub.add_parser('lint'); p.add_argument('spec'); p.add_argument('--report')
    sub.add_parser('patterns')
    p=sub.add_parser('catalog'); p.add_argument('--pack',required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='compile':
            result=compile_outline(strict_json(Path(args.outline).read_bytes()))
            # Exclusive creation: neither owned nor interrupted output is silently replaced.
            with Path(args.out).open('x',encoding='utf-8') as f: json.dump(result,f,indent=2,ensure_ascii=True); f.write('\n')
            result={'ok':True,'status':'authored_source_not_playtested','spec_path':args.out}
        elif args.action=='lint':
            result=lint(strict_json(Path(args.spec).read_bytes()))
            if args.report:
                with Path(args.report).open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
        elif args.action=='patterns': result=library()
        else: result=catalog(args.pack)
        print(json.dumps(result,ensure_ascii=True)); return 0 if result.get('ok',True) else 1
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)})); return 1


if __name__=='__main__': sys.exit(main())
