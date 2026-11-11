"""Cyber grid/socket compiler to the normal plugin room/presentation data path. No runtime changes."""
import json
from pathlib import Path
from tools.dungeonkit_rooms import rot, rot_facing, OPPOSITE

R=Path(__file__).resolve().parents[1]
TOL=0.011

class PlanError(ValueError):
    pass


DEFAULT_DOOR_X=6.5      # cell 1 of the plot (the historical 3x3 datum); shells with door_m move it


def door_x(plan,sockets,side):
    """Door centre (plot metres) on the n/s wall: the plan's door_x_m, else the shell's cut door socket on that side,
    else the historical datum. Generic: works for any shell size."""
    if 'door_x_m' in plan: return float(plan['door_x_m'])
    xs=[s['at'][0] for s in sockets if s['type']=='door' and s['face']==side and s.get('key','').startswith('cyroom.')
        and s['key']!='cyroom.portal']
    return round(xs[0],3) if xs else DEFAULT_DOOR_X


STYLE_BIBLE=R/'kits/core/style_bible.json'


def budget_profile(plan):
    """(name, profile) from kits/core/style_bible.json budget_profiles. No field -> 'default' (6,000). A profile is
    refused if the plan lacks a block the profile requires (arena profile -> the plan's 'arena' clearance block)."""
    profiles=json.loads(STYLE_BIBLE.read_text(encoding='utf-8'))['budget_profiles']['profiles']
    name=plan.get('budget_profile','default')
    if name not in profiles: raise PlanError('unknown budget profile %r (style bible has %s)'%(name,sorted(profiles)))
    prof=profiles[name]
    missing=[b for b in prof.get('requires',[]) if not plan.get(b)]
    if missing: raise PlanError('budget profile %r requires plan block(s) %s'%(name,missing))
    return name,prof


def compile_room(plan):
    pieces=json.loads((R/'kits/library/cyberkit-sockets.json').read_text(encoding='utf-8'))['pieces']
    sx,sz=plan['plot_cells'];w,d=4*sx+1,4*sz+1
    placed=[];sockets=[];tris=0
    for p in plan['pieces']:
        key=p['key']
        if key not in pieces: raise PlanError('not a cyber kit: '+key)
        info=pieces[key];yaw=p.get('yaw',0);anchor=info['anchor']
        if anchor in ('cell_block_centre','cell_edge','door_anchor','wall_face') and yaw%90:
            raise PlanError('non-interlocking: grid yaw must be a multiple of 90')
        if 'block' in p:
            if anchor!='cell_block_centre': raise PlanError('non-interlocking: not a cell block')
            a,b=info['cells']
            if yaw%180: a,b=b,a
            x,z=0.5+4*(p['block'][0]+a/2),0.5+4*(p['block'][1]+b/2)
        elif 'edge' in p:
            if anchor!='cell_edge': raise PlanError('non-interlocking: not a cell edge')
            x,z=p['edge']
            if abs((x-.5)/4-round((x-.5)/4))>TOL and abs((z-.5)/4-round((z-.5)/4))>TOL:
                raise PlanError('non-interlocking: facade off grid')
        else:
            if anchor in ('cell_block_centre','cell_edge'): raise PlanError('non-interlocking: grid piece at free metres')
            x,z=p['at_m']
        y=p.get('y',0)
        row={'asset':key,'position':[x,y,z],'yaw':yaw,'scale':[1,1,1],'kind':p.get('kind','shell' if info['class']=='shell' else 'piece')}
        if p.get('mounted') or y>0.08: row['mounted']=True
        placed.append(row);tris+=info['tris']
        for s in info['sockets']:
            xx,yy,zz=s['position'];rx,rz=rot(xx,zz,yaw)
            sockets.append(dict(s,at=[x+rx,y+yy,z+rz],face=rot_facing(s['facing'],yaw),key=key))
    open_ends=plan.get('open_streets',[])
    for s in sockets:
        if s['type']!='street_end': continue
        paired=any(t is not s and t['type']=='street_end' and t['face']==OPPOSITE[s['face']] and
                   max(abs(a-b) for a,b in zip(t['at'],s['at']))<TOL and abs(t['width_m']-s['width_m'])<TOL for t in sockets)
        boundary=any(max(abs(a-b) for a,b in zip(e,s['at']))<TOL for e in open_ends)
        if not paired and not boundary: raise PlanError('non-interlocking: unpaired street '+str(s['at']))
    doors=[]
    for dr in plan['doors']:
        side=dr['side'];z=1 if side=='n' else d-1
        x=door_x(plan,sockets,side)
        if not plan.get('open_transitions'):
            if not any(s['type']=='door' and s['face']==side and abs(s['at'][0]-x)<TOL and abs(s['at'][2]-z)<TOL for s in sockets):
                raise PlanError('non-interlocking: door has no cut socket')
        doors.append({'id':dr['id'],'wall':'north' if side=='n' else 'south','position':int(round(x-0.5)),'to_room':dr['to_room'],
                      'to_door':dr['to_door'],'label':dr['label'],'conditions':[]})
        tris+=pieces['cyroom.portal']['tris']
    people=1+len(plan.get('characters',{}))
    name,prof=budget_profile(plan)
    # Conservative runtime allowance: painted sky dome, region marker, collision, blob shadows and lamp pools.
    overhead=prof['overhead_exterior'] if plan.get('exterior') else prof['overhead_interior']
    robots=int((plan.get('arena') or {}).get('robots',0))      # simultaneous combat robots the room is built for
    estimate=tris+people*prof['person_tris']+robots*prof['robot_tris']+overhead
    if estimate>prof['room_tris']: raise PlanError('over budget: %d > %d (%s profile)'%(estimate,prof['room_tris'],name))
    cam=plan.get('camera') or plan['cameras']['a']
    room={'id':plan['id'],'name':plan['name'],'description':plan['description'],'grid_size':[w,d],
          'kit_refs':[],'doors':doors,'cameras':[{'id':'game','position':cam['position'],'look_at':cam['look_at']}],'props':[],
          'character_ids':['pilgrim']+list(plan.get('characters',{}))}
    pres={'exterior':bool(plan.get('exterior')),'kit_shell':True,'floor':'','look_profile':plan['look_profile'],
          'wall_height':4.5,'camera':'game','cameras':[dict(cam,id='game')],'pieces':placed,
          'characters':plan.get('characters',{})}
    for k in ('weather','sky_signal','combat'):  # presentation-only layers (rain, sky sign, readability override), plan data
        if k in plan: pres[k]=plan[k]
    if name!='default': pres['budget']={'profile':name,'room_tris':prof['room_tris']}
    rep={'id':plan['id'],'tri_estimate':estimate,'kit_tris':tris,'people':people,'robots':robots,'pieces':len(placed),
         'budget_profile':name,'room_tris_cap':prof['room_tris'],
         'checks':['kit-only','grid anchors','paired streets or explicit open boundaries','doors on sockets','budget']}
    if plan.get('arena'):
        rep['arena']=arena_check(plan,room,pres)
        rep['checks'].append('arena clearance + reachability')
    return room,pres,rep


def glb_lookup(pack='neon_city_night'):
    binds=json.loads((R/'packs'/pack/'bindings.json').read_text(encoding='utf-8'))['assets']
    return lambda key:R/binds[key]['glb']


def arena_check(plan,room,pres,pack='neon_city_night'):
    """Plan field "arena": {"min_clear_m": N, "spots": [[x,z],...]} -> every door, actor and spot reachable from the
    entry door and a clear square of at least N metres of floor (tools.room_clearance). Raises PlanError otherwise."""
    from tools.room_clearance import clearance
    a=plan['arena']
    targets={'spot:%d'%i:p for i,p in enumerate(a.get('spots',[]))}
    targets.update({'boss:%d'%i:p[:2] for i,p in enumerate(a.get('boss_spots',[]))})
    targets.update({'crowd:%d'%i:p[:2] for i,p in enumerate(a.get('crowd_spots',[]))})
    if a.get('hero_spot'): targets['hero']=a['hero_spot'][:2]
    lanes=lane_report(a)
    if lanes and lanes['problems']:
        raise PlanError('arena: attack lanes unreadable %s'%lanes['problems'])
    rep=clearance(room,pres,glb_lookup(pack),targets=targets)
    if lanes: rep['lanes']=lanes
    if not rep['all_reachable']:
        raise PlanError('arena: unreachable %s'%[k for k,v in rep['reachable'].items() if not v])
    if rep['clear_square_m']+1e-6<float(a.get('min_clear_m',0)):
        raise PlanError('arena: clear floor %.2f m < %.2f m'%(rep['clear_square_m'],float(a['min_clear_m'])))
    return rep


def lane_report(a):
    """Boss-spot readability (arena 'boss_spots' + 'hero_spot'): every pair of bosses at least boss_spacing_m apart
    (one boss's telegraph shape never covers another), and each boss's straight lane to the hero spot keeps
    lane_clear_m from every other boss (a charge or shot lane is never hidden behind a second boss). {} if unused."""
    bosses=[p[:2] for p in a.get('boss_spots',[])]
    hero=a.get('hero_spot')
    if not bosses: return {}
    spacing=float(a.get('boss_spacing_m',0));clear=float(a.get('lane_clear_m',0))
    probs=[];pairs=[];lane=[]
    dist=lambda p,q:((p[0]-q[0])**2+(p[1]-q[1])**2)**0.5
    for i in range(len(bosses)):
        for j in range(i+1,len(bosses)):
            d=dist(bosses[i],bosses[j]);pairs.append(round(d,2))
            if d+1e-6<spacing: probs.append('boss %d-%d %.2f m < %.2f m'%(i,j,d,spacing))
    if hero:
        h=hero[:2]
        for i,b in enumerate(bosses):
            for j,o in enumerate(bosses):
                if i==j: continue
                vx,vz=h[0]-b[0],h[1]-b[1];L=vx*vx+vz*vz or 1e-9
                t=max(0.0,min(1.0,((o[0]-b[0])*vx+(o[1]-b[1])*vz)/L))
                d=dist(o,(b[0]+t*vx,b[1]+t*vz));lane.append(round(d,2))
                if d+1e-6<clear: probs.append('lane %d->hero passes %.2f m from boss %d (< %.2f m)'%(i,d,j,clear))
    return {'pair_m':pairs,'min_pair_m':min(pairs) if pairs else None,'min_lane_clear_m':min(lane) if lane else None,
            'problems':probs}


# ---- Room plans as pack data (L5 CYBER-ROOMS). Any game/template instantiates them; nothing here names a story.
PLANS_FORMAT='hermes64-room-plans/1'


def plans_path(pack='neon_city_night'):
    """kits/packs/<pack>/rooms.json; a pack may point at another pack's plans with {"rooms_from": "<pack>"}."""
    p=R/'kits/packs'/pack/'rooms.json'
    doc=json.loads(p.read_text(encoding='utf-8'))
    return plans_path(doc['rooms_from']) if 'rooms_from' in doc else p


def load_plans(pack='neon_city_night'):
    doc=json.loads(plans_path(pack).read_text(encoding='utf-8'))
    if doc.get('format')!=PLANS_FORMAT: raise PlanError('room plans: expected format '+PLANS_FORMAT)
    return doc['rooms']


def instantiate(room_id,plan,doors=(),characters=None):
    """A room plan ready for compile_room: the pack plan plus caller-supplied doors and character placements.
    characters maps character id -> {'position','yaw'} or an index into the plan's actor_spots."""
    out={k:v for k,v in plan.items() if k not in ('actor_spots','role','note')}
    spots=plan.get('actor_spots',[])
    out['id']=room_id;out['doors']=list(doors)
    out['characters']={cid:(dict(spots[v]) if isinstance(v,int) else v) for cid,v in (characters or {}).items()}
    return out


def chain(order,pack='neon_city_night',ring=False,characters=None,label='Continue to %s',back='Return to %s'):
    """Plans for rooms in a line (forward door 'north', return door 'south'), or a ring. characters: room id ->
    {character id: spot}. The ends of an open chain keep both door sockets cut; the caller gates or omits them."""
    plans=load_plans(pack);n=len(order);out=[]
    for i,rid in enumerate(order):
        if rid not in plans: raise PlanError('no room plan %r in %s'%(rid,pack))
        doors=[]
        nxt=order[(i+1)%n] if ring or i+1<n else None
        prev=order[(i-1)%n] if ring or i>0 else None
        if nxt: doors.append({'id':'north','side':'n','to_room':nxt,'to_door':'south','label':label%nxt})
        if prev: doors.append({'id':'south','side':'s','to_room':prev,'to_door':'north','label':back%prev})
        out.append(instantiate(rid,plans[rid],doors,(characters or {}).get(rid)))
    return out


def entry_x(room):
    """Checkpoint/entry x for a compiled room: in front of its south door (else north door, else the centre)."""
    doors={d['wall']:d for d in room['doors']}
    d=doors.get('south') or doors.get('north')
    return d['position']+0.5 if d else room['grid_size'][0]/2
