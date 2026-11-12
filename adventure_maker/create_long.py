"""LONGSTORY: a story block that names 3 or more places builds one room per place (lane LONGSTORY).

The two-room create game stays exactly as it was for stories with 0 to 2 places. Here every place becomes a room, up to
`max_rooms` (create_long.json, 64: a build safety ceiling, not a game cap): outdoor places form the spine, joined by the kit's own edge gates; indoor places
hang off the outdoor room before them through doorway buildings (kit interiors have one door socket each). Each room
is a create pattern instance (create_patterns.json) with its own layout variant or shell variant, dressing seed,
people, story spots, keys and fights. The story runs across the rooms: beats in order, keys that open the door they
name, a fight per room that holds foes (the last boss is the final boss), the finish where the last beat is.
Anything that cannot be built as asked is a not-applied row with the reason and the fix, never a silent drop.
Pure apart from the compile/dress calls the create flow already makes.
"""
import copy
import json
import math
from pathlib import Path
import re

DATA = Path(__file__).with_name('create_long.json')
TEMPLATE = 'create_long_story_v1'
MIRROR = {'e': 'w', 'w': 'e'}


def load(path=None):
    return json.loads(Path(path or DATA).read_text(encoding='utf-8'))


def room_count(story, data=None):
    """How many rooms the story asks for: every place (3+), or story.rooms; 0 = the two-room game."""
    if not story or story.get('empty') or not story.get('places'):
        return 0
    asked = story.get('rooms')
    n = len(story['places']) if asked is None else min(int(asked), len(story['places']))
    return n if n >= 3 else 0


def wants(ctx):
    """True when the rooms stage should build the long game (read from create/story.json)."""
    from . import create_story as CS
    if not ctx.exists('create/story.json'):
        return False
    story = ctx.read_json('create/story.json')
    if not (story.get('format') == CS.FORMAT and room_count(story) > 0):
        return False
    mood = ctx.read_json('create/mood.json') if ctx.exists('create/mood.json') else {}
    return supported(mood)


def supported(mood, data=None):
    """LONGSTORY-2: can the long path build this pack/setting? A family or setting without long-story data builds the
    two-room game (its extra places are reported by the story layout), never a refusal."""
    from . import create_flow as CF
    data = data or load()
    setting = mood.get('setting')
    if setting and setting.get('setting') in (data.get('settings') or {}):
        return True
    family = setting.get('family') if setting else CF.family_for(mood.get('base') or '')
    if family is None:
        return False
    fam = CF.load_patterns()['families'][family]
    return any(p['id'] in data['outdoor_slots'] for p in fam['outdoor'])


# ------------------------------------------------------------------------------------------------ the room graph
def _words(text):
    return set(re.findall(r'[a-z]+', str(text).lower().replace('-', ' ')))


def plan_graph(story, brief, data, slots_for, entry_slots):
    """Places -> rooms and links. Returns {'rooms': [...], 'links': [...], 'rows': [...], 'folded': {...}}.
    slots_for(kind) -> (inside slot count, road slot count) for an outdoor room of the family."""
    from . import create_story as CS
    cap = int(data['max_rooms'])
    places = [dict(p) for p in story['places']]
    asked = story.get('rooms')
    n = room_count(story, data)
    rows, folded = [], {}
    if asked is not None and int(asked) > len(places):
        rows.append({'feature': 'rooms', 'asked': str(asked), 'status': 'closest',
                     'reason': 'the story names %d places; a room is built for each place' % len(places),
                     'closest': '%d rooms' % len(places), 'fix': 'name a place for every room you want'})
    keep = places[:min(n, cap)]
    why = {}
    for p in places[len(keep):]:
        folded[p['name']] = None
        why[p['name']] = (('story.rooms asks for %d rooms' % n, 'raise story.rooms (up to %d)' % cap) if n < min(len(places), cap)
                          else ('the create flow builds at most %d rooms per game (create_long.json max_rooms: a build safety '
                                'ceiling for run time; the triangle budget is per room)' % cap, 'fewer places, or hand-author more rooms (skill hermes64)'))
    if not any(p['kind'] == 'outdoor' for p in keep):
        name = ' '.join(w.capitalize() for w in re.findall(r'[a-z]+', str(brief['setting'].get('place', '')).lower())[:4]) or 'Outside'
        if name.lower() in {p['name'].lower() for p in places}:
            name = name + ' Road'
        keep.insert(0, {'name': name[:40], 'kind': 'outdoor', 'about': '%s.' % name[:40], 'added': True})
        rows.append({'feature': 'place', 'asked': 'an outdoor place', 'status': 'closest',
                     'reason': 'the kit\'s interiors have one door each, so they join through an outdoor room',
                     'closest': 'added the outdoor room %s' % name[:40], 'fix': 'name an outdoor place in story.places'})
        if len(keep) > cap:
            drop = keep.pop()
            folded[drop['name']] = None
            why[drop['name']] = ('the create flow builds at most %d rooms per game (create_long.json max_rooms) and an '
                                 'outdoor room was added' % cap, 'name an outdoor place among the first %d' % cap)
    taken = set()
    rooms = []
    for i, p in enumerate(keep):
        rid = CS.slug(p['name'], taken, 'room')
        taken.add(rid)
        rooms.append({'id': rid, 'name': p['name'], 'kind': p['kind'], 'about': p.get('about'), 'order': i,
                      'added': bool(p.get('added'))})
    outs = [r for r in rooms if r['kind'] == 'outdoor']
    entry = outs[0]
    free = {}
    for r in outs:
        ni, nr = (entry_slots if r is entry else slots_for)()
        free[r['id']] = {'inside': ni, 'road': nr}
    links = []
    bfs = [entry]
    for r in outs[1:]:              # the spine: hub first (breadth-first), so the entry is the hub that is revisited
        parent = next((q for q in bfs if free[q['id']]['road'] > 0), None)
        if parent is None or free[r['id']]['road'] < 1:
            folded[r['name']] = None
            why[r['name']] = ('every outdoor room\'s road gates are taken (create_long.json outdoor_slots)',
                              'fewer outdoor places, or make one of them indoor')
            continue
        free[parent['id']]['road'] -= 1
        free[r['id']]['road'] -= 1
        links.append({'kind': 'road', 'a': parent['id'], 'b': r['id']})
        r['parent'] = parent['id']
        bfs.append(r)
    built_out = [q for q in rooms if q['kind'] == 'outdoor' and (q is entry or q.get('parent'))]
    for r in rooms:
        if r['kind'] != 'indoor':
            continue
        before = [q for q in built_out if q['order'] < r['order']] or [entry]
        order = [before[-1]] + [q for q in built_out if q is not before[-1]]
        host = next((q for q in order if free[q['id']]['inside'] > 0), None)
        if host is None:
            folded[r['name']] = None
            why[r['name']] = ('every outdoor room\'s doorways are taken (create_long.json outdoor_slots)',
                              'fewer indoor places, or add an outdoor place')
            continue
        free[host['id']]['inside'] -= 1
        links.append({'kind': 'inside', 'a': host['id'], 'b': r['id']})
        r['parent'] = host['id']
    built = [r for r in rooms if r is entry or r.get('parent')]
    for name in list(folded):
        host = None
        src = next((p for p in places if p['name'] == name), None)
        if src is not None:
            idx = places.index(src)
            prior = [r for r in built if any(p['name'] == r['name'] for p in places[:idx])]
            host = (prior[-1] if prior else entry)
        folded[name] = (host or entry)['id']
        reason, fix = why[name]
        rows.append({'feature': 'place', 'asked': name, 'status': 'closest', 'reason': reason,
                     'closest': 'a named story spot in %s' % next(r['name'] for r in built if r['id'] == folded[name]),
                     'fix': fix})
    return {'rooms': built, 'links': links, 'rows': rows, 'folded': folded, 'entry': entry['id']}


# ------------------------------------------------------------------------------------------------ pattern instances
def door_point(side, cell, w, d):
    along = 0.5 + 4.0 * float(cell) + 2.0
    return {'n': [along, 1.0], 's': [along, d - 1.0], 'w': [1.0, along], 'e': [w - 1.0, along]}[side]


def mirror_slot(slot, cells_x):
    s = copy.deepcopy(slot)
    if s.get('side') in ('n', 's'):
        s['cell'] = cells_x - 1 - s['cell']
    elif s.get('side') in ('e', 'w'):
        s['side'] = MIRROR[s['side']]
    if s.get('edge'):
        cx, cz, side = s['edge']
        s['edge'] = [cells_x - 1 - cx, cz, MIRROR.get(side, side)]
    return s


def outdoor_patterns(CF, fam, family, keys, data=None):
    """Every usable outdoor pattern of the family: the shipped ones, the create_craft layout variants, then the
    long-story key-swap variants (create_long.json outdoor_variants)."""
    from . import create_craft
    data = data or load()
    pool = [dict(copy.deepcopy(p), _base=p['id'], _mirror=False) for p in fam['outdoor']
            if set(p.get('only_if_keys', [])) <= keys]
    by_id = {p['id']: p for p in fam['outdoor']}
    for v in create_craft.load()['layouts'].get(family, []):
        if v['from'] in by_id:
            pat = create_craft.variant_pattern(by_id[v['from']], v, CF.pattern_size_m(by_id[v['from']])[0])
            if set(pat['only_if_keys']) <= keys:
                pool.append(dict(pat, _base=v['from'], _mirror=bool(v.get('mirror'))))
    for base_id, rows in sorted((k, v) for k, v in data.get('outdoor_variants', {}).items() if k in by_id):
        for v in rows:
            pat = copy.deepcopy(by_id[base_id])
            for pc in pat['plan']['pieces']:
                pc['key'] = v['swap'].get(pc['key'], pc['key'])
            if not set(v['swap'].values()) <= keys:
                continue
            pat.update(id=v['id'], tags=list(v['tags']), _base=base_id, _mirror=False,
                       source='create_long.json variant %s: the %s pattern with %s' % (
                           v['id'], base_id, ', '.join('%s -> %s' % kv for kv in sorted(v['swap'].items()))))
            pool.append(pat)
    return pool


def pick(pool, words, used, first=None):
    """The pattern whose tags name most of the place's words; unused patterns first (rooms are not copies)."""
    if first is not None:
        return first
    score = lambda p: (used.get(p['id'], 0), -len(set(p.get('tags', [])) & words), pool.index(p))
    return sorted(pool, key=score)[0]


def close_inside(CF, mod, plan, door_id, closed):
    """An unused @door slot: the doorway building becomes its shipped closed twin at the same spot (no door)."""
    piece = next((pc for pc in plan['pieces'] if pc.get('door_to') == door_id or (pc.get('kind') == 'landmark' and 'lot' in pc
                                                                                   and pc['key'] in closed)), None)
    own = next((d for d in plan['doors'] if d['id'] == door_id), None)
    plan['doors'] = [d for d in plan['doors'] if d['id'] != door_id]
    if piece is None and own is not None:     # LONGSTORY-2: a door wall on the plot edge (ancient ruin.wall__door)
        cx, cz = plan['plot_cells']
        c = int(own['cell'])
        edge = {'w': [0, c, 'w'], 'e': [cx - 1, c, 'e'], 'n': [c, 0, 'n'], 's': [c, cz - 1, 's']}.get(own['side'])
        hit = next((pc for pc in plan['pieces'] if pc.get('edge') == edge and pc['key'] in closed), None)
        if hit is not None:
            hit['key'] = closed[hit['key']]
            return None
    if piece is None or piece['key'] not in closed:
        return 'no closed twin for the entry building; door kept closed'
    if 'lot' in piece:
        piece['key'] = closed[piece['key']]
        return None
    probe = copy.deepcopy(plan)
    probe.update(id='probe', name='probe', description='probe', protagonist='traveller')
    probe['doors'].append({'id': door_id, 'side': piece['_side'], 'cell': piece['_cell'], 'to_room': 'x', 'to_door': 'y', 'label': 'x'})
    probe['pieces'] = [dict(pc) for pc in probe['pieces']]
    for pc in probe['pieces']:
        pc.pop('_side', None); pc.pop('_cell', None)
    _room, pres, _rep = mod.compile_room(probe)
    row = next(r for r in pres['pieces'] if r['asset'] == piece['key'])
    piece.clear()
    piece.update(key=closed[row['asset']], at_m=[row['position'][0], row['position'][2]], yaw=row['yaw'], kind='landmark')
    return None


def outdoor_room(CF, mod, pat, slots, closed, rid, name, desc, inside_links, road_links):
    """(pattern instance with a compiled-ready plan, notes). Links: [{'id', 'to_room', 'to_door', 'label', 'conditions'}]."""
    pat = copy.deepcopy(pat)
    plan = pat['plan']
    cells_x = plan['plot_cells'][0]
    w, d = CF.pattern_size_m(pat)
    notes, lanes = [], []
    own = next(dd for dd in plan['doors'] if dd['id'] == '@door')
    for pc in plan['pieces']:
        if pc.get('door_to') == '@door':
            pc['_side'], pc['_cell'] = own['side'], own['cell']
    sl_in = [mirror_slot(s, cells_x) if pat.get('_mirror') and 'use' not in s else s for s in slots['inside']]
    sl_road = [mirror_slot(s, cells_x) if pat.get('_mirror') else s for s in slots['road']]
    for i, slot in enumerate(sl_in):
        link = inside_links[i] if i < len(inside_links) else None
        if slot.get('use') == '@door':
            if link is None:
                why = close_inside(CF, mod, plan, '@door', closed)
                if why:
                    notes.append(why)
                continue
            own.update(id=link['id'], to_room=link['to_room'], to_door=link['to_door'], label=link['label'],
                       conditions=list(link.get('conditions', [])))
            for pc in plan['pieces']:
                if pc.get('door_to') == '@door':
                    pc['door_to'] = link['id']
            lanes.append(door_point(own['side'], own['cell'], w, d))
            continue
        if link is None:
            continue
        plan['doors'].append({'id': link['id'], 'side': slot['side'], 'cell': slot['cell'], 'to_room': link['to_room'],
                              'to_door': link['to_door'], 'label': link['label'], 'conditions': list(link.get('conditions', []))})
        if slot.get('door_to'):
            plan['pieces'].append({'key': slot['door_to'], 'door_to': link['id']})
        if slot.get('lot'):
            plan['pieces'] = [pc for pc in plan['pieces'] if pc.get('lot') != slot['lot']]
            plan['pieces'].append(dict({'key': slot['piece'], 'lot': list(slot['lot'])}, **({'kind': slot['kind']} if slot.get('kind') else {})))
            pat['lots'] = [lt for lt in pat.get('lots', []) if list(lt) != list(slot['lot'])]
        if slot.get('edge') or slot.get('at_m'):
            edge_or_anchor_piece(plan, slot)
        lanes.append(door_point(slot['side'], slot['cell'], w, d))
    for i, link in enumerate(road_links):
        slot = sl_road[i]
        plan['doors'].append({'id': link['id'], 'side': slot['side'], 'cell': slot['cell'], 'to_room': link['to_room'],
                              'to_door': link['to_door'], 'label': link['label'], 'conditions': list(link.get('conditions', []))})
        if slot.get('edge'):
            hit = [pc for pc in plan['pieces'] if pc.get('edge') == slot['edge']]
            if hit:
                hit[0]['key'] = slot['piece']
                hit[0].pop('kind', None)           # still a wall to the compiler; not swapped by a layout's wall key
            else:
                plan['pieces'].append({'key': slot['piece'], 'edge': list(slot['edge'])})
        if slot.get('lot'):
            plan['pieces'] = [pc for pc in plan['pieces'] if pc.get('lot') != slot['lot']]
            plan['pieces'].append(dict({'key': slot['piece'], 'lot': list(slot['lot'])}, **({'kind': slot['kind']} if slot.get('kind') else {})))
        if slot.get('at_m'):
            edge_or_anchor_piece(plan, slot)
        lanes.append(door_point(slot['side'], slot['cell'], w, d))
    for pc in plan['pieces']:
        pc.pop('_side', None); pc.pop('_cell', None)
    plan.update(id=rid, name=name, description=desc, protagonist='traveller')
    if lanes:
        pat['door_point_m'] = lanes[0]
        pat['extra_lanes_m'] = [[list(pat['centre_m']), p] for p in lanes[1:]]
        pat['extra_clear_m'] = [[p[0], p[1], 1.6] for p in lanes]
    return pat, notes


def pattern_tris(mod, pat):
    """LONGSTORY-2: the kit compiler's triangle estimate of a room pattern's own pieces (doors as dummies), or None."""
    plan = json.loads(json.dumps(pat['plan']).replace('@door', 'd0').replace('@next', 'd1'))
    plan.update(id='probe', name='probe', description='probe', protagonist='traveller')
    for dd in plan.get('doors', []):
        dd.update(to_room='x', to_door='y', label='z')
    try:
        return int(mod.compile_room(plan)[2].get('tri_estimate') or 0)
    except Exception:
        return None


def edge_or_anchor_piece(plan, slot):
    """LONGSTORY-2: the kit piece that carries an extra door of a setting pattern: a wall edge swapped for the kit's
    door wall (ancient ruin.wall__door), or a door-anchor piece standing on the plot edge (an exterior's airlock, the
    way the surface pattern's own door is cut)."""
    if slot.get('edge'):
        hit = [pc for pc in plan['pieces'] if pc.get('edge') == list(slot['edge'])]
        if hit:
            hit[0]['key'] = slot['piece']
            hit[0].pop('kind', None)
        else:
            plan['pieces'].append({'key': slot['piece'], 'edge': list(slot['edge'])})
    if slot.get('at_m'):
        plan['pieces'].append(dict({'key': slot['piece'], 'at_m': list(slot['at_m']), 'yaw': slot.get('yaw', 0)},
                                   **({'kind': slot['kind']} if slot.get('kind') else {})))


def chain_room(pat, rid, name, desc, back, nxt):
    """LONGSTORY-2 chain rooms (station kit shells): the pattern's own @door is the way back (the entry: the way on),
    @next (two-door link shells) the way on. Returns the instance with door points for lanes, people and fights."""
    pat = copy.deepcopy(pat)
    first, second = (back, nxt) if back is not None else (nxt, None)
    plan = pat['plan']
    doors = []
    for dd in plan['doors']:
        link = first if dd['id'] == '@door' else second if dd['id'] == '@next' else None
        if link is None:
            continue
        doors.append(dict(dd, id=link['id'], to_room=link['to_room'], to_door=link['to_door'], label=link['label'],
                          conditions=list(link.get('conditions', []))))
    plan['doors'] = doors
    plan.update(id=rid, name=name, description=desc, protagonist='traveller')
    if second is not None and pat.get('next_point_m'):
        pat['extra_lanes_m'] = [[list(pat['centre_m']), list(pat['next_point_m'])]]
        pat['extra_clear_m'] = [[pat['door_point_m'][0], pat['door_point_m'][1], 1.6],
                                [pat['next_point_m'][0], pat['next_point_m'][1], 1.6]]
    return pat


def long_patterns(CF, fam, setting, base, lset):
    """LONGSTORY-2: a derived setting's patterns for a long story: the row's entry (framed and looked as the row says,
    create_flow.setting_patterns), then the setting's spine/link/end/indoor patterns of the family with the reference
    pack's own look profiles (create_patterns.json look_profile_for)."""
    entry = CF.setting_patterns(fam, setting, base)['outdoor'][:1]

    def own(p):
        prof = (p.get('look_profile_for') or {}).get(base)
        return dict(p, plan=dict(p['plan'], look_profile=prof)) if prof else p
    every = {p['id']: own(p) for p in fam['outdoor'] + fam['indoor']}
    named = lambda ids: [every[i] for i in ids if i in every]
    spine = named(lset.get('spine', []))
    outs = entry + [p for p in spine if p['id'] != entry[0]['id']]
    ins = named(lset['indoor']) if 'indoor' in lset else [own(p) for p in fam['indoor'] if not p.get('long_only')]
    return dict(fam, outdoor=outs, indoor=ins, link=named(lset.get('link', [])), end=named(lset.get('end', [])))


def chain_graph(story, brief, data):
    """LONGSTORY-2 chain topology: every place a room in story order (up to max_rooms), each joined to the next."""
    from . import create_story as CS
    cap = int(data['max_rooms'])
    places = [dict(p) for p in story['places']]
    n = room_count(story, data)
    keep = places[:min(n, cap)]
    rows, folded, taken, rooms, links = [], {}, set(), [], []
    for i, p in enumerate(keep):
        rid = CS.slug(p['name'], taken, 'room')
        taken.add(rid)
        rooms.append({'id': rid, 'name': p['name'], 'kind': 'outdoor' if i == 0 else 'indoor', 'asked_kind': p['kind'],
                      'about': p.get('about'), 'order': i, 'added': False})
        if i:
            rooms[-1]['parent'] = rooms[i - 1]['id']
            links.append({'kind': 'road', 'a': rooms[i - 1]['id'], 'b': rid})
    for p in places[len(keep):]:
        folded[p['name']] = rooms[-1]['id']
        why = ('story.rooms asks for %d rooms' % n) if n < min(len(places), cap) else \
            'the create flow builds at most %d rooms per game (create_long.json max_rooms, a safety ceiling)' % cap
        rows.append({'feature': 'place', 'asked': p['name'], 'status': 'closest', 'reason': why,
                     'closest': 'a named story spot in %s' % rooms[-1]['name'], 'fix': 'raise story.rooms, or fewer places'})
    return {'rooms': rooms, 'links': links, 'rows': rows, 'folded': folded, 'entry': rooms[0]['id']}


def indoor_room(pat, shell_row, rid, name, desc, link):
    pat = copy.deepcopy(pat)
    plan = json.loads(json.dumps(pat['plan']).replace('@door', link['id']))
    if shell_row:
        shell, ceiling = shell_row['shell'], shell_row.get('ceiling')
        for pc in plan['pieces']:
            if pc.get('block') == [0, 0]:
                if 'ceiling' in pc['key']:
                    if ceiling:
                        pc['key'] = ceiling
                else:
                    pc['key'] = shell
        pat['shell'] = shell
    for dd in plan['doors']:
        dd.update(to_room=link['to_room'], to_door=link['to_door'], label=link['label'], conditions=list(link.get('conditions', [])))
    plan.update(id=rid, name=name, description=desc, protagonist='traveller')
    pat['plan'] = plan
    return pat


# ------------------------------------------------------------------------------------------------ story layout
def _match(text, rooms, folded, places_by_name):
    """Room id for a place text: a built room by name words, else the room a folded place was put in."""
    from .create_story import STOP
    # LONGSTORY-2: the same name is that room, and numbers count ("Cell 2" is not "Cell 1")
    exact = next((r['id'] for r in rooms if ' '.join(re.findall(r'[a-z0-9]+', r['name'].lower())) ==
                  ' '.join(re.findall(r'[a-z0-9]+', str(text).lower()))), None)
    if exact:
        return exact
    t = (_words(text) | set(re.findall(r'\d+', str(text)))) - STOP
    if not t:
        return None
    # the most shared name words wins ("Ghost Town" is the ghost town, not the frontier town); ties keep place order
    best = max(((len(t & ((_words(r['name']) | set(re.findall(r'\d+', r['name']))) - STOP)), -i, r['id'])
                for i, r in enumerate(rooms)), default=(0, 0, None))
    if best[0]:
        return best[2]
    best = max(((len(t & (_words(n) - STOP)), -i, h) for i, (n, h) in enumerate(folded.items())), default=(0, 0, None))
    return best[2] if best[0] else None


def long_mechanic_rows(CS, story, data):
    """create_story.mechanic_rows with the long-story rows (create_long.json mechanics) read first."""
    rows = data.get('mechanics', {}).get('rows', [])
    out = []
    for m in story.get('mechanics', []):
        w = ' %s ' % ' '.join(re.findall(r'[a-z0-9/-]+', m.lower()))
        if any(' %s ' % ph in w for row in rows for ph in row['words']):
            continue                                     # made in a long story
        r = CS.mechanic_row(m)
        if r['status'] != 'made':
            out.append({k: r[k] for k in ('feature', 'asked', 'status', 'reason', 'closest', 'fix') if k in r})
    return out


def _yaw(spot, centre):
    return round(math.degrees(math.atan2(centre[0] - spot[0], centre[1] - spot[1])) % 360.0 / 15.0) * 15.0


def descendants(links, rid):
    out, todo = {rid}, [rid]
    while todo:
        cur = todo.pop()
        for ln in links:
            if ln['a'] == cur and ln['b'] not in out:
                out.add(ln['b'])
                todo.append(ln['b'])
    return out


def stage_rooms(ctx):
    """The rooms stage for a story with 3+ places. Same outputs as create_flow.stage_rooms."""
    from . import create_flow as CF, create_story as CS, create_craft
    from .packs import Packs, fingerprint, validate_pack
    from .newgame import CAST, COLLECTIBLE_ASSET, title_for
    from .genre_kits import PACKS as GP
    data = load()
    brief = ctx.read_json('brief.json')
    assets = ctx.read_json('create/assets.json')
    mood = ctx.read_json('create/mood.json')
    prompt = ctx.read_json('create/prompt.json')['prompt']
    story = ctx.read_json('create/story.json')
    pack_id, base = mood['pack'], mood['base']
    style = Packs(ctx.settings, ctx.service.project(ctx.name)).get(pack_id)
    keys, bdoc = CF.bindings_keys(ctx, pack_id)
    setting = mood.get('setting')          # LONGSTORY-2: a derived setting builds its long story in its own family
    family = setting['family'] if setting else CF.family_for(base)
    if family is None:
        raise CF.CreateError('create_rooms', 'no room pattern or kit compiler covers the %s pack family yet' % base,
                             'pass --style with a medieval or western pack, or hand-author the rooms (skills/hermes64-create)')
    fam = CF.load_patterns()['families'][family]
    lset = (data.get('settings') or {}).get(setting['setting']) if setting else None
    if setting:
        fam = long_patterns(CF, fam, setting, base, lset or {})
    chain = bool(lset) and lset.get('topology') == 'chain'
    mod = CF.bundle_import(ctx, fam['compiler'])
    gen_ok = CF.gen_presets_supported()
    bw = set(CF.brief_words(brief))
    items, skipped, presets = CF.plan_dressing(ctx, assets, family, keys, bdoc, gen_ok)
    for it in items:
        it['placed'] = False
    placed, notes = [], []
    brief, not_applied = CF.story_hints(brief, story)
    not_applied += list(story.get('notes', []))
    scale, scale_reason = CF.brief_room_scale(brief)
    slot_data = data['outdoor_slots']
    if chain:                      # LONGSTORY-2: kit rooms with one or two doors join in story order
        pool = []
        g = chain_graph(story, brief, data)
    else:
        pool = [p for p in outdoor_patterns(CF, fam, family, keys, data) if p['_base'] in slot_data]
        if not pool:
            raise CF.CreateError('create_rooms', 'no outdoor create pattern of the %s family has door slots for a long story' % family,
                                 'set story.rooms to 2 for the two-room game, or hand-author the rooms (skill hermes64)')
        n_in = min(len(slot_data[p['_base']]['inside']) for p in pool)
        n_road = min(len(slot_data[p['_base']]['road']) for p in pool)
        g = plan_graph(story, brief, data, lambda: (n_in, n_road), lambda: (n_in, n_road))
    not_applied += g['rows']
    rooms, links, folded, entry_id = g['rooms'], g['links'], g['folded'], g['entry']
    by_id = {r['id']: r for r in rooms}
    outside = [r['name'] for r in rooms if chain and r.get('asked_kind') == 'outdoor' and r['id'] != entry_id]
    if outside:                    # said, not silent: the station kit has no outdoor rooms
        not_applied.append({'feature': 'place', 'asked': '%s (outdoor)' % ', '.join(outside), 'status': 'closest',
                            'reason': 'the %s setting\'s rooms are interiors joined door to door' % setting['setting'],
                            'closest': 'interior rooms of the %s kit' % family, 'fix': 'none needed; the rooms are built'})
    # ---- patterns per room (rooms are not copies: unused layouts first, shells rotate)
    if setting:                    # LONGSTORY-2: the setting row's entry pattern, as its two-room game uses it
        first, layout_why = fam['outdoor'][0], 'setting %s: its entry pattern %s' % (setting['setting'], fam['outdoor'][0]['id'])
    else:
        first, layout_why = CF.entry_pattern(fam, family, bw, keys, scale, dict(brief, prompt=prompt))
    if not chain:
        first = next((p for p in pool if p['id'] == first['id']), None)
    used, pair_used = {}, {}
    indoor_pool = [p for p in fam['indoor'] if set(p.get('only_if_keys', [])) <= keys]
    pairs = []                       # (pattern, shell row): an interior is a pattern with one of its shipped shells
    for p in indoor_pool:
        rows_ = [s for s in data['indoor_shells'].get(p['id'], []) if s['shell'] in keys and s.get('ceiling') in (None,) + tuple(keys)]
        pairs += [(p, s) for s in rows_] or [(p, None)]
    for r in rooms:
        words = _words(r['name']) | _words(r.get('about') or '')
        if chain:                  # entry first; the last room an end pattern by its words; link patterns between
            if r['id'] == entry_id:
                r['pat'] = first
            elif r is rooms[-1]:
                ends = fam['end'] or fam['indoor']
                r['pat'] = sorted(ends, key=lambda p: (-len(set(p.get('tags', [])) & words), ends.index(p)))[0]
            else:
                r['pat'] = pick(fam['link'], words, used)
            r['shell'] = None
            used[r['pat']['id']] = used.get(r['pat']['id'], 0) + 1
        elif r['kind'] == 'outdoor':
            r['pat'] = pick(pool, words, used, first if r['id'] == entry_id else None)
            used[r['pat']['id']] = used.get(r['pat']['id'], 0) + 1
        else:
            # an unused (pattern, shell) first, so two interiors are not copies; then the place's words; then data order
            score = lambda ps: (pair_used.get((ps[0]['id'], (ps[1] or {}).get('shell')), 0),
                                -len((set(ps[0].get('tags', [])) | set((ps[1] or {}).get('words', []))) & words), pairs.index(ps))
            pat, shell = sorted(pairs, key=score)[0]
            r['pat'], r['shell'] = pat, shell
            k = (pat['id'], (shell or {}).get('shell'))
            pair_used[k] = pair_used.get(k, 0) + 1
    # ---- doors: ids and labels (conditions come from keys and locks below)
    for r in rooms:
        r['inside_links'], r['road_links'], r['back'] = [], [], None
    for ln in links:
        a, b = by_id[ln['a']], by_id[ln['b']]
        down = {'id': 'to_' + b['id'], 'to_room': b['id'], 'to_door': 'to_' + a['id'], 'conditions': [],
                'label': ('Enter %s' if ln['kind'] == 'inside' else 'Go to %s') % b['name']}
        up = {'id': 'to_' + a['id'], 'to_room': a['id'], 'to_door': 'to_' + b['id'], 'conditions': [],
              'label': 'Back to %s' % a['name']}
        (a['inside_links'] if ln['kind'] == 'inside' else a['road_links']).append(down)
        b['back'] = up
        if b['kind'] == 'outdoor':
            b['road_links'].insert(0, up)
    # ---- who and what stands where
    places_by = {p['name']: p for p in story.get('places', [])}
    order_ids = [r['id'] for r in rooms]
    # LONGSTORY-2: people per room from the room's triangle budget (the art-style cap), not a fixed count: what the
    # room's own pieces leave of ROOM_CAP - ROOM_RESERVE, less the fighters a fight room keeps free, in people of
    # PERSON_TRIS each (at least 1). Story spots carry no triangles: as many as the room has free floor (Slots).
    foe_rooms = {_match(c.get('place') or '', rooms, folded, places_by) for c in story.get('cast', []) if c['role'] in CS.FOE_ROLES}
    cap_people = {}
    for r in rooms:
        est = pattern_tris(mod, r['pat'])
        free = CF.ROOM_CAP - CF.ROOM_RESERVE - CS.PERSON_TRIS - (est if est is not None else 0) - \
            (FIGHTER_TRIS * CS.MAX_AT_ONCE if r['id'] in foe_rooms else 0)
        # a room whose own pieces leave no person's worth of triangles holds nobody (its people stand in the next room
        # and that is said); measured: jungle sun_road 6,418 runtime triangles with a forced 1 person
        cap_people[r['id']] = max(0, free // CS.PERSON_TRIS) if est is not None else data['people'][r['kind']]
        r['people_budget'] = {'room_tris_estimate': est, 'people': cap_people[r['id']]}
    actors, foes = [], []
    taken = {'traveller', 'inhabitant', 'keepsake'}
    beats = story.get('beats', [])
    speaker_room = {}
    for k, b in enumerate(beats):
        rid = _match(b.get('place') or '', rooms, folded, places_by)
        if rid:
            speaker_room.setdefault((b.get('who') or '').lower(), rid)
    rr = 0
    for c in story.get('cast', []):
        want = _match(c.get('place') or '', rooms, folded, places_by)
        if c['role'] in CS.FOE_ROLES:
            foes.append({'name': c['name'], 'role': c['role'], 'room': want})
            continue
        cid = CS.slug(c['name'], taken, 'person')
        taken.add(cid)
        if c['role'] == 'captive':
            actors.append({'cid': cid, 'name': c['name'], 'role': c['role'], 'room': want, 'captive': True, 'says': c.get('says')})
            continue
        if want is None:
            want = speaker_room.get(c['name'].lower())
        if want is None:
            want = order_ids[rr % len(order_ids)]
            rr += 1
        order = [want] + [x for x in order_ids if x != want]
        room = next((x for x in order if cap_people[x] > 0), None)
        if room is None:
            not_applied.append({'feature': 'cast', 'asked': '%s (%s)' % (c['name'], c['role']), 'status': 'not_made',
                                'reason': 'every room\'s triangle budget is full of people (%d people across %d rooms; '
                                          '%d triangles each)' % (len(actors), len(rooms), CS.PERSON_TRIS),
                                'closest': 'none', 'fix': 'name another place, or merge minor people'})
            continue
        cap_people[room] -= 1
        if room != want and c.get('place'):
            not_applied.append({'feature': 'cast', 'asked': '%s in %s' % (c['name'], c['place']), 'status': 'closest',
                                'reason': 'that room\'s triangle budget was full (%d people)' % by_id[want]['people_budget']['people'],
                                'closest': 'stands in %s' % by_id[room]['name'], 'fix': 'move someone else'})
        actors.append({'cid': cid, 'name': c['name'], 'role': c['role'], 'room': room, 'says': c.get('says')})
    # fights: every boss in its place; the last boss is the final boss (last indoor room by default)
    indoor_ids = [r['id'] for r in rooms if r['kind'] == 'indoor']
    bosses = [f for f in foes if f['role'] == 'boss']
    free_fight = [x for x in (indoor_ids or order_ids)]
    if bosses and bosses[-1]['room'] is None:
        bosses[-1]['room'] = (indoor_ids or order_ids)[-1]
    for f in bosses:
        if f['room'] is None:
            f['room'] = next((x for x in free_fight if x not in [q['room'] for q in bosses]), free_fight[0])
    enemies = [f for f in foes if f['role'] == 'enemy']
    for f in enemies:
        if f['room'] is None:
            f['room'] = bosses[0]['room'] if bosses else (indoor_ids or order_ids)[0]
    no_fight = any(CS.mechanic_row(m).get('route') == '-combat' for m in story.get('mechanics', []))
    fight_rooms = [] if no_fight else [x for x in order_ids if any(f['room'] == x for f in foes)]
    if foes and no_fight:
        not_applied.append({'feature': 'cast', 'asked': ', '.join('%s (%s)' % (f['name'], f['role']) for f in foes),
                            'status': 'not_made', 'reason': 'the story says no combat', 'closest': 'none',
                            'fix': 'remove "no combat" from story.mechanics'})
    # beats: by who, then place, then the room of the beat before
    blay, prev = [], entry_id
    by_name = {a['name'].lower(): a for a in actors}
    for k, b in enumerate(beats, 1):
        who = by_name.get((b.get('who') or '').lower())
        if who is not None and not who.get('captive') and who.get('room'):
            blay.append({'k': k, 'room': who['room'], 'who': who['cid'], 'spot': None})
            prev = who['room']
            continue
        rid = _match(b.get('place') or '', rooms, folded, places_by) or prev
        spot = b['place'] if b.get('place') and not (_words(b['place']) & _words(by_id[rid]['name'])) else None
        blay.append({'k': k, 'room': rid, 'who': None, 'spot': spot})
        prev = rid
        if b.get('who') and who is None:
            not_applied.append({'feature': 'beat', 'asked': 'beat %d spoken by %s' % (k, b['who']), 'status': 'closest',
                                'reason': '%s is not a cast person standing in a room' % b['who'],
                                'closest': 'a story spot with the text', 'fix': 'add them to story.cast with a non-fighting role'})
    finish_room = blay[-1]['room'] if blay else entry_id
    # the item (or the captive) and the keys
    final_fight = fight_rooms[-1] if fight_rooms else None
    item = story.get('item') or {}
    captive = next((a for a in actors if a.get('captive')), None)
    item_room = _match(item.get('place') or '', rooms, folded, places_by) or (captive or {}).get('room') or final_fight \
        or (indoor_ids or order_ids)[-1]
    if captive is not None:
        captive['room'] = item_room
    keys_out = []
    for i, kd in enumerate(story.get('keys', []), 1):
        opens = _match(kd.get('opens') or '', rooms, folded, places_by)
        if kd.get('opens') and opens is None:
            not_applied.append({'feature': 'key', 'asked': '%s opens %s' % (kd['name'], kd['opens']), 'status': 'closest',
                                'reason': '%s is not a room of this game' % kd['opens'], 'closest': 'the key opens the finish',
                                'fix': 'name a place of story.places in keys[].opens'})
        if opens == entry_id:
            not_applied.append({'feature': 'key', 'asked': '%s opens %s' % (kd['name'], kd['opens']), 'status': 'closest',
                                'reason': '%s is where the game starts, so no door into it is locked' % by_id[opens]['name'],
                                'closest': 'the key opens the finish', 'fix': 'name a later place in keys[].opens'})
            opens = None
        behind = descendants(links, opens) if opens else set()
        rid = _match(kd.get('place') or '', rooms, folded, places_by)
        if rid is None or rid in behind:
            if rid in behind:
                not_applied.append({'feature': 'key', 'asked': '%s in %s' % (kd['name'], kd.get('place')), 'status': 'closest',
                                    'reason': 'the key would lie behind the door it opens', 'closest': 'it lies in the room before',
                                    'fix': 'put the key in an earlier place'})
            ok = [x for x in order_ids if x not in behind]
            rid = ok[(i - 1) % len(ok)] if not kd.get('place') else (by_id[opens]['parent'] if opens else ok[0])
        kid = CS.slug('key ' + kd['name'], taken, 'key')
        taken.add(kid)
        keys_out.append({'id': kid, 'name': kd['name'], 'room': rid, 'opens': opens})
    # door locks: keys open the door into their room; door_lock keeps the old meaning (the first indoor room)
    lock_rows = []
    gates = {}
    for kk in keys_out:
        if kk['opens']:
            gates.setdefault(kk['opens'], []).append({'collected': kk['id']})
    lock = story.get('door_lock')
    lock_room = indoor_ids[0] if (lock and indoor_ids) else None
    # ---- positions: people first, then story spots and keys (the dresser keeps them clear)
    for r in rooms:
        r['inst'] = None
    for r in rooms:
        if chain:
            pat = chain_room(r['pat'], r['id'], r['name'], r.get('about') or '%s.' % r['name'], r['back'],
                             (r['road_links'] or [None])[0])
        elif r['kind'] == 'outdoor':
            pat, nts = outdoor_room(CF, mod, r['pat'], slot_data[r['pat']['_base']], data['closed'], r['id'], r['name'],
                                    r.get('about') or '%s.' % r['name'], r['inside_links'], r['road_links'])
            notes += ['%s: %s' % (r['id'], n) for n in nts]
        else:
            pat = indoor_room(r['pat'], r['shell'], r['id'], r['name'], r.get('about') or '%s.' % r['name'], r['back'])
        r['inst'] = pat
    slots = {r['id']: CF.Slots(dict(r['inst']), '%s:story:%s' % (CF.SEED, r['id'])) for r in rooms}
    first_person = {}
    for a in actors:
        if a.get('captive'):
            continue
        pat = by_id[a['room']]['inst']
        if a['room'] not in first_person:
            pos = list(pat['npc_m'])
            first_person[a['room']] = a['cid']
        else:
            pos = slots[a['room']].take(CS.ACTOR_R)
            if pos is None:
                pos = list(pat['centre_m'])
                notes.append('%s: no free spot for %s; stands at the room centre' % (a['room'], a['name']))
        a['pos'], a['yaw'] = pos, _yaw(pos, pat['centre_m'])
    reserve = {r['id']: [] for r in rooms}
    for a in actors:
        if a.get('pos') and first_person.get(a['room']) != a['cid']:
            reserve[a['room']].append([a['pos'][0], a['pos'][1], CS.ACTOR_R])
    for x in blay:
        if x['who'] is not None:
            continue
        pos = slots[x['room']].take(CS.SPOT_R)
        x['pos'] = pos
        if pos is not None:
            reserve[x['room']].append([pos[0], pos[1], CS.SPOT_R])
        else:
            not_applied.append({'feature': 'beat', 'asked': 'beat %d: %s' % (x['k'], beats[x['k'] - 1]['text'][:60]),
                                'status': 'closest', 'reason': 'no free story spot left in %s' % by_id[x['room']]['name'],
                                'closest': 'the beat is an action without a spot (menu only)', 'fix': 'fewer beats in that place'})
    for kk in keys_out:
        pos = slots[kk['room']].take(CS.SPOT_R) or list(by_id[kk['room']]['inst']['centre_m'])
        kk['pos'] = pos
        reserve[kk['room']].append([pos[0], pos[1], CS.SPOT_R])
    # door conditions (into the gated room, on the parent's door)
    flags_needed = set()
    lock_cond = None
    if lock:
        if lock[0] == 'beat':
            need_rooms = {x['room'] for x in blay if x['k'] <= lock[1]}
        else:
            a = by_name.get(lock[1].lower())
            need_rooms = {a['room']} if a else {None}
        if lock_room is None or need_rooms & descendants(links, lock_room) or None in need_rooms:
            lock_rows.append({'feature': 'door_lock', 'asked': '%s %s' % (lock[0], lock[1]), 'status': 'not_made',
                              'reason': 'what opens it happens behind the door it would lock' if lock_room else 'no indoor room to lock',
                              'closest': 'the door is open', 'fix': 'set those beats in an earlier place'})
        else:
            lock_cond = lock
            if lock[0] == 'talk':
                flags_needed.add(lock[1].lower())
    not_applied += lock_rows
    lock_flags = []
    if lock_cond:
        if lock_cond[0] == 'beat':
            lock_flags = [{'flag': 'beat_%d' % lock_cond[1], 'equals': True}]
        else:
            a = by_name[lock_cond[1].lower()]
            spoke = next((x['k'] for x in blay if x['who'] == a['cid']), None)
            lock_flags = [{'flag': ('beat_%d' % spoke) if spoke else 'talked_%s' % a['cid'], 'equals': True}]
    for r in rooms:
        for ln in r['inside_links'] + r['road_links']:
            tgt = ln['to_room']
            if by_id[tgt].get('parent') != r['id']:
                continue
            ln['conditions'] = list(gates.get(tgt, [])) + (list(lock_flags) if lock_cond and tgt == lock_room else [])
    # rebuild the outdoor instances now that the door conditions are known (positions stay: same pattern, same slots)
    for r in rooms:
        if chain:
            r['inst'] = chain_room(r['pat'], r['id'], r['name'], r.get('about') or '%s.' % r['name'], r['back'],
                                   (r['road_links'] or [None])[0])
        elif r['kind'] == 'outdoor':
            r['inst'], _n = outdoor_room(CF, mod, r['pat'], slot_data[r['pat']['_base']], data['closed'], r['id'], r['name'],
                                         r.get('about') or '%s.' % r['name'], r['inside_links'], r['road_links'])
    # ---- dress every room: interiors first (props that do not fit may stand outside), then outdoor rooms
    fighters = {x: 0 for x in order_ids}     # most fighters at once in the room (triangles kept free)
    people_n = {x: sum(1 for a in actors if a.get('room') == x) for x in order_ids}
    for x in fight_rooms:
        # LONGSTORY-2: fighters at once from the room's triangle budget (was a flat 2): what the room's own pieces, its
        # people and the player leave of ROOM_CAP - ROOM_RESERVE, FIGHTER_TRIS per fighter, at most the module's 3
        room_est = by_id[x].get('people_budget', {}).get('room_tris_estimate')
        fit = (CF.ROOM_CAP - CF.ROOM_RESERVE - room_est - CS.PERSON_TRIS * (people_n[x] + 1)) // FIGHTER_TRIS if room_est else CS.MAX_AT_ONCE
        asked = max(fight_waves(story, foes, x, fight_rooms, at_once=MODULE_AT_ONCE) + [1])
        fighters[x] = max(1, min(asked, MODULE_AT_ONCE, fit))
        if asked > fighters[x]:
            not_applied.append({'feature': 'waves', 'asked': '%d at once in %s' % (asked, by_id[x]['name']), 'status': 'closest',
                                'reason': ('the room\'s triangle budget holds %d fighters at once' % fighters[x]) if fit < asked
                                else 'the combat module runs at most %d at once' % MODULE_AT_ONCE,
                                'closest': 'waves of %d, one after another' % fighters[x], 'fix': 'none needed; every fighter comes'})
    inner_name = next((r['name'] for r in rooms if r['kind'] == 'indoor'), rooms[0]['name'])
    kinds = {'indoor': [r for r in rooms if r['kind'] == 'indoor'], 'outdoor': [r for r in rooms if r['kind'] == 'outdoor']}
    share, turn = {}, {'indoor': 0, 'outdoor': 0}
    for it in items:                      # round robin per kind, so the brief's pieces spread over the rooms
        kind = 'indoor' if it['where'] == 'indoor' and kinds['indoor'] else 'outdoor'
        group = kinds[kind]
        share[id(it)] = (kind, group[turn[kind] % len(group)]['id'])
        turn[kind] += 1
    compiled = {}
    entry_room = by_id[entry_id]
    for phase in ('indoor', 'outdoor'):
        if phase == 'outdoor':
            for it in items:
                if not it['placed'] and it['where'] == 'indoor':
                    it['overflow'] = True
                    share[id(it)] = ('outdoor', entry_id)
        for r in kinds[phase]:
            pat = dict(r['inst'], extra_clear_m=list(r['inst'].get('extra_clear_m', [])) + reserve[r['id']],
                       reserve_tris=CS.PERSON_TRIS * (people_n[r['id']] + 1) + FIGHTER_TRIS * fighters[r['id']],   # + the player
                       at_once=fighters[r['id']] or 1)
            mine = [it for it in items if not it['placed'] and (share[id(it)][1] == r['id'] or r is entry_room and it['where'] == 'vista')]
            if r is entry_room:
                CF.mark_landmark(mine, brief, inner_name, pat)
                create_craft.mark_landmark(mine, pat, assets)
            plan = copy.deepcopy(pat['plan'])
            room, pres, rep = CF.dress(mod, plan, pat, mine, '%s:%s' % (CF.SEED, r['id']), placed, None, r['kind'])
            compiled[r['id']] = (room, pres, rep, pat)
    not_placed = skipped + [{'want': it['want'], 'id': it['id'], 'instance': it['instance'],
                             'reason': it.get('why', 'no room took it')} for it in items if not it['placed']]
    lamps = False
    for r in rooms:
        lamps = CF.accent_lamps(compiled[r['id']][1], compiled[r['id']][3]) or lamps
    if lamps:
        presets.append({'id': 'cf_accent_lamp', 'asset_id': 'furn.lamp', 'params_json': json.dumps({
            'kind': 'floor', 'height': 1.8, 'shade': 'drum', 'shade_size': 0.8, 'base': 'tripod', 'stand_role': 'metal'})})
    # ---- project pack (as the two-room flow)
    pack = copy.deepcopy(style)
    used_assets = {p['asset'] for p in placed} | {pc.get('asset') for x in compiled.values() for pc in x[1]['pieces']}
    keep = [p for p in pack['presets'] if 'preset/' + p['id'] in used_assets]
    mine = [p for p in presets if 'preset/' + p['id'] in used_assets]
    pack['presets'] = (keep + mine)[:32] or pack['presets'][:1]
    pack['name'] = (pack['name'] + ' (create: ' + ctx.name + ')')[:120]
    body = dict(pack); body.pop('id')
    pack['id'] = ('cf_' + re.sub(r'[^a-z0-9]', '_', ctx.name)[:40] + '_' + CF.sha(CF.canon(body))[:8])
    validate_pack(pack)
    ref = {'id': pack['id'], 'sha256': fingerprint(pack)}
    spec = build_spec(ctx, CF, CS, story, brief, prompt, style, pack_id, ref, base, rooms, compiled, actors, foes, blay,
                      keys_out, item, item_room, captive, finish_room, fight_rooms, lock_cond, flags_needed, entry_id, not_applied,
                      CAST, COLLECTIBLE_ASSET, GP, title_for)
    spec, made = spec
    not_applied += long_mechanic_rows(CS, story, data)
    not_applied += CF.name_rows(prompt, brief, story)
    not_applied += CF.weather_rows(ctx, brief, mood)
    not_applied += create_craft.report_rows(assets)
    spec = create_craft.apply_cast(spec, assets)
    size = lambda p: '%g x %g m' % CF.pattern_size_m(p)
    line = 'rooms: %d (story places): %s' % (len(rooms), ', '.join('%s %s %s' % (r['id'], r['inst']['id'], size(r['inst'])) for r in rooms))
    _routed, unrouted = CF.route_modules(sorted(set(brief['setting'].get('genre_hints', []))))
    covered = set(brief['setting'].get('genre_hints', [])) - set(unrouted)
    hints = sorted(((set(brief['setting'].get('genre_hints', [])) | set(brief.get('unrecognised', [])) | bw)
                    & CF.GAMEPLAY_WORDS) - covered - ({'combat', 'boss', 'fight', 'battle'} if fight_rooms else set()))
    acts = act_lines(blay, keys_out, fight_rooms, by_id, finish_room, entry_id)
    rooms_doc = {'format': 'hermes64-create-rooms/1', 'family': family, 'place_api': bool(CF.place_api()), 'pack': pack_id,
                 'layout': {'entry': entry_room['inst']['id'], 'why': layout_why}, 'template': TEMPLATE,
                 'entry_source': 'create pattern %s (%s)' % (entry_room['inst']['id'], entry_room['inst'].get('source', '')),
                 'inner_source': '%d more rooms: %s' % (len(rooms) - 1, ', '.join('%s (%s)' % (r['id'], r['inst']['id'] + (
                     '/' + r['inst']['shell'] if r['inst'].get('shell') else '')) for r in rooms if r['id'] != entry_id)),
                 'rooms': [{'id': r['id'], 'name': r['name'], 'kind': r['kind'], 'pattern': r['inst']['id'],
                            'shell': r['inst'].get('shell'), 'parent': r.get('parent'), 'people_budget': r.get('people_budget'),
                            'pattern_doc': {k: v for k, v in r['inst'].items() if not k.startswith('_')},
                            'report': compiled[r['id']][2]} for r in rooms],
                 'links': links, 'folded': folded, 'acts': acts,
                 'open_seconds': min(150, max(40, 14 * len(rooms))),
                 'room_scale': {'scale': scale, 'reason': scale_reason, 'line': line, 'entry_plot_m': list(CF.pattern_size_m(entry_room['inst'])),
                                'inside_plot_m': None},
                 'placed': placed, 'not_placed': not_placed, 'notes': notes,
                 'gameplay_template': 'long story: %d rooms' % len(rooms) + (' + ' + ', '.join(m['module'] for m in made) if made else ''),
                 'gameplay_made': made, 'gameplay_modules_not_made': [], 'gameplay_not_made': hints,
                 'gen_presets_supported': gen_ok, 'pack_ref': ref, 'not_applied': not_applied}
    if setting:                    # LONGSTORY-2: the rooms and capture stages read the setting as the two-room game does
        rooms_doc.update(setting=setting['setting'], topology='chain' if chain else 'hub')
    if scale != CF.brief_room_scale({})[0]:
        not_applied.append({'feature': 'room scale', 'asked': scale, 'status': 'closest',
                            'reason': 'a long story uses each place\'s create pattern at its own size', 'closest': line,
                            'fix': 'story.rooms 2 builds the two-room game, which follows room_scale'})
    if story.get('course'):
        not_applied.append({'feature': 'course', 'asked': '%d s, %s' % (story['course']['seconds'], ', '.join(story['course']['checkpoints'])),
                            'status': 'not_made', 'reason': 'a long story does not build the timed course yet',
                            'closest': 'none', 'fix': 'story.rooms 2 builds the two-room game with the course'})
    return {'create/rooms.json': rooms_doc, 'create/pack.json': pack, 'source/spec.json': spec}


MODULE_AT_ONCE = 3      # the combat module's max_simultaneous (story/modules/registry.py, gameplay API contract)
FIGHTER_TRIS = 500      # LONGSTORY-2 measured: one enemy body adds 476 (reed_warden) / 500 (cairn_dasher) runtime triangles
MODULE_WAVES, MODULE_SPAWNS = 8, 24     # waves 0..7 and spawns per encounter (story/modules/schema.py ENCOUNTER)
MODULE_FIGHTS, MODULE_KINDS = 16, 16    # encounters/challenges and archetypes per game (story/modules/registry.py)


def fight_waves(story, foes, rid, fight_rooms, at_once=None):
    """Enemy waves in one fight room, at most `at_once` at a time (the room's triangle budget; the boss comes alone
    after them). LONGSTORY-2: was a flat MAX_AT_ONCE (2)."""
    from .create_story import MAX_AT_ONCE
    MAX_AT_ONCE = at_once or MAX_AT_ONCE    # noqa: N806
    enemies = sum(1 for f in foes if f['room'] == rid and f['role'] == 'enemy')
    first = next((x for x in fight_rooms if any(f['room'] == x and f['role'] == 'enemy' for f in foes)), None)
    asked = list(story.get('waves') or []) if rid == (first or (fight_rooms[0] if fight_rooms else None)) else []
    if not asked and enemies:
        asked = [enemies]
    out = []
    for n in asked:
        while n > 0:
            out.append(min(n, MAX_AT_ONCE))
            n -= MAX_AT_ONCE
    return out


def story_order(spec, blay, keys_out, made):
    """LONGSTORY-2: the story goes on once what it passed is done. Beat k also needs every key taken and every fight won
    in the rooms of beats 1..k-1 (the player was in each of those rooms for its beat). Nothing becomes unwinnable: a key
    or fight in a passed room needs nothing later. This keeps the exact proof's state count near linear in the places
    (independent keys and fights multiply it: 30 places measured past the proof's 100,000-state cap without it)."""
    by_id = {i['id']: i for i in spec['interactions']}
    challenge_needs, challenge_rows = {}, {}
    for m in spec.get('gameplay', {}).get('modules', []):
        for c in (m.get('entities') or {}).get('challenges', []):
            challenge_needs[c['id']] = {x.get('flag') for x in c.get('conditions', []) if x.get('flag')}
            challenge_rows[c['id']] = c
    # ... and a key or fight is there once the story reaches its room (the beat before the room's first beat), so each
    # one is open for a window of the story instead of from the start
    first = {}
    for x in sorted(blay, key=lambda b: b['k']):
        first.setdefault(x['room'], x['k'])
    beat_room = {x['k']: x['room'] for x in blay}
    reach = {room: [{'flag': 'beat_%d' % (k - 1), 'equals': True}] for room, k in first.items() if k > 1 and 'beat_%d' % (k - 1) in by_id}
    early = set()       # rooms whose key the story needs before it reaches them (the key opens the way to an earlier beat)
    for kk in keys_out:
        if kk['room'] not in reach:
            continue
        cut = {(r['id'], d['to_room']) for r in spec['rooms'] for d in r['doors'] if {'collected': kk['id']} in d['conditions']}
        seen, todo = {spec['start']['location']}, [spec['start']['location']]
        while todo:
            here = todo.pop()
            for r in spec['rooms']:
                if r['id'] == here:
                    for d in r['doors']:
                        if (here, d['to_room']) not in cut and d['to_room'] not in seen:
                            seen.add(d['to_room'])
                            todo.append(d['to_room'])
        if any(beat_room[j] not in seen for j in range(1, first[kk['room']]) if j in beat_room):
            early.add(kk['room'])
    for room in early:
        reach.pop(room, None)
    for c in spec.get('collectibles', []):
        if c['id'] in {kk['id'] for kk in keys_out} and c['room'] in reach:
            c['conditions'] = list(c['conditions']) + reach[c['room']]
    for mm in made:
        row = challenge_rows.get(mm['challenge'])
        if row is not None and mm['room'] in reach:
            row['conditions'] = list(row['conditions']) + reach[mm['room']]
            challenge_needs[mm['challenge']] = challenge_needs.get(mm['challenge'], set()) | {reach[mm['room']][0]['flag']}
    passed, done = [], set()
    for x in sorted(blay, key=lambda b: b['k']):
        row = by_id.get('beat_%d' % x['k'])
        if row is None:
            continue
        later = {'beat_%d' % j for j in range(x['k'], len(blay) + 1)}
        need = [{'collected': kk['id']} for kk in keys_out if kk['room'] in passed and kk['id'] not in done]
        need += [{'challenge': m['challenge'], 'status': 'completed'} for m in made
                 if m['room'] in passed and m['challenge'] not in done and not (challenge_needs.get(m['challenge'], set()) & later)]
        row['conditions'] = list(row['conditions']) + need
        done |= {c.get('collected') or c.get('challenge') for c in need}
        if x['room'] not in passed:
            passed.append(x['room'])


def spawn_ring(j):
    """LONGSTORY-2: a spawn offset for the 4th and later fighter of one wave (the first three keep their offsets)."""
    a = math.radians(45.0 * (j - 3) + 22.5)
    return (round(2.2 * math.sin(a), 2), round(-1.0 - 2.2 * math.cos(a), 2))


def act_lines(blay, keys_out, fight_rooms, by_id, finish_room, entry_id):
    """Three acts for the report (setup, escalation, finale): beats split in thirds; keys and middle fights in act 2."""
    n = len(blay)
    cut1, cut2 = -(-n // 3), -(-2 * n // 3)
    acts = []
    for i, (name, part) in enumerate((('setup', blay[:cut1]), ('escalation', blay[cut1:cut2]), ('finale', blay[cut2:]))):
        rooms = list(dict.fromkeys(by_id[x['room']]['name'] for x in part))
        row = {'act': i + 1, 'name': name, 'beats': [x['k'] for x in part], 'rooms': rooms}
        if i == 1:
            row['keys'] = [k['name'] for k in keys_out]
            row['gates'] = sorted({by_id[k['opens']]['name'] for k in keys_out if k['opens']})
            row['fights'] = [by_id[x]['name'] for x in fight_rooms[:-1]]
        if i == 2:
            row['fights'] = [by_id[fight_rooms[-1]]['name']] if fight_rooms else []
            row['finish'] = by_id[finish_room]['name'] + (' (the entry, revisited)' if finish_room == entry_id else '')
        acts.append(row)
    return acts


def build_spec(ctx, CF, CS, story, brief, prompt, style, pack_id, ref, base, rooms, compiled, actors, foes, blay, keys_out,
               item, item_room, captive, finish_room, fight_rooms, lock_cond, flags_needed, entry_id, rows,
               CAST, COLLECTIBLE_ASSET, GP, title_for):
    """(spec, made): the long story on the dressed rooms."""
    cast = CAST.get(base) or CAST.get(CF.DEFAULT_PACK)
    collect = GP[base]['collectible'] if base in GP else COLLECTIBLE_ASSET
    params = {'costume': 'plain', 'colour': style['palette'][0], 'voice_tags': []}
    traveller = {'id': 'traveller', 'name': 'Traveller', 'role': 'protagonist', 'body_id': 'core_humanoid',
                 'base_rig_id': 'human_16', 'params': dict(params), 'role_profiles': {'protagonist': dict(params)}}
    template = {'id': 'inhabitant', 'name': 'Inhabitant', 'role': 'host', 'body_id': 'core_humanoid', 'base_rig_id': 'human_16',
                'params': dict(params), 'role_profiles': {'host': dict(params), 'guide': dict(params)}}
    bindings_path = ctx.bundle / 'bindings.json'
    brows = json.loads(bindings_path.read_text(encoding='utf-8')).get('characters', []) if bindings_path.is_file() else []
    public = {r.get('character_id'): r for r in brows if isinstance(r, dict) and r.get('public_release')}
    for ch, cid in zip((traveller, template), cast):
        if cid in public:
            r = public[cid]
            ch.update(body_id=r['body_id'], base_rig_id=r['base_rig_id'], params=copy.deepcopy(r['params']))
            ch['role_profiles'] = {role: copy.deepcopy(r['params']) for role in ch['role_profiles']}
    pool = list(cast) + [c for c in ('fv_elder', 'neri', 'sol', 'ivo', 'luma') if c in public and cast[0] in public
                         and public[c]['body_id'] == public[cast[0]]['body_id']]
    bodies = [public[c] for c in dict.fromkeys(pool) if c in public]
    bodies = bodies[1:] or bodies
    characters = [traveller]
    if story.get('player'):
        traveller['name'] = story['player']['name']

    def person(i, cid, name):
        ch = copy.deepcopy(template)
        ch.update(id=cid, name=name)
        if bodies:
            body = bodies[i % len(bodies)]
            ch.update(body_id=body['body_id'], base_rig_id=body['base_rig_id'], params=copy.deepcopy(body['params']))
            ch['role_profiles'] = {k: copy.deepcopy(body['params']) for k in ch['role_profiles']}
        characters.append(ch)
        return ch

    pres_rooms, spec_rooms = {}, []
    for r in rooms:
        room, pres, _rep, pat = compiled[r['id']]
        room = copy.deepcopy(room)
        pres = copy.deepcopy(pres)
        room['name'], room['description'] = r['name'], r.get('about') or '%s.' % r['name']
        room['character_ids'] = ['traveller']
        spec_rooms.append(room)
        pres_rooms[r['id']] = pres
    rooms_by = {room['id']: room for room in spec_rooms}
    pats = {r['id']: compiled[r['id']][3] for r in rooms}
    for i, a in enumerate(actors):
        person(i, a['cid'], a['name'])
        if a.get('captive'):
            continue
        rooms_by[a['room']]['character_ids'].append(a['cid'])
        pres_rooms[a['room']].setdefault('characters', {})[a['cid']] = {'position': [a['pos'][0], 0, a['pos'][1]], 'yaw': a['yaw']}
    flags = [{'id': 'finished', 'initial': False, 'description': 'The journey is done.'}]
    start_flags = {'finished': False}

    def flag(fid, text):
        if not any(f['id'] == fid for f in flags):
            flags.append({'id': fid, 'initial': False, 'description': text[:120] or fid})
            start_flags[fid] = False

    interactions, dialogues, quests, endings = [], [], [], []
    for q in story.get('quests', []):
        if q['done_when'][0] == 'talk':
            flags_needed.add(q['done_when'][1].lower())
    speaking = {x['who'] for x in blay if x.get('who')}
    talk_flags = {}
    for a in actors:
        if a.get('captive') or a['cid'] in speaking:
            continue
        effects = []
        if a['name'].lower() in flags_needed:
            fid = 'talked_%s' % a['cid']
            flag(fid, 'Talked to %s' % a['name'])
            effects = [{'flag': fid, 'value': True}]
            talk_flags[a['name'].lower()] = fid
        interactions.append({'id': 'talk_%s' % a['cid'], 'room': a['room'], 'kind': 'talk', 'target': a['cid'],
                             'label': 'Talk to %s' % a['name'], 'text': a.get('says') or '%s nods.' % a['name'],
                             'conditions': [], 'effects': effects})
    # beats in order, on a story clock when they say when
    beats = story.get('beats', [])
    whens = []
    for b in beats:
        if b.get('when') and CS.slug(b['when']) not in [CS.slug(w) for w in whens]:
            whens.append(b['when'])
    tide = {'id': 'cycle', 'states': [{'id': 'calm', 'label': 'Calm', 'duration': 1}], 'wait_label': 'Wait', 'wait_text': 'A moment passes.'}
    start_tide = {'state': 'calm', 'tick': 0}
    if len(whens) >= 2:
        tide = {'id': 'story_clock', 'states': [{'id': CS.slug(w, fallback='phase'), 'label': w[:1].upper() + w[1:], 'duration': 3}
                                                for w in whens], 'wait_label': 'Wait', 'wait_text': 'Time passes.'}
        start_tide = {'state': CS.slug(whens[0], fallback='phase'), 'tick': 0}
    elif len(whens) == 1:
        rows.append({'feature': 'beat timing', 'asked': whens[0], 'status': 'closest', 'reason': 'one time word is not a clock',
                     'closest': 'beats in order', 'fix': 'give two or more beats a `when`'})
    names = {c['id']: c['name'] for c in characters}
    beat_flags = []
    for x, b in zip(blay, beats):
        k = x['k']
        fid = 'beat_%d' % k
        beat_flags.append(fid)
        flag(fid, b['text'])
        conds = [{'flag': 'beat_%d' % (k - 1), 'equals': True}] if k > 1 else []
        if len(whens) >= 2 and b.get('when'):
            conds.append({'tide': CS.slug(b['when'], fallback='phase')})
        effects = [{'flag': fid, 'value': True}]
        nxt = beats[k].get('when') if k < len(beats) else None
        if len(whens) >= 2 and nxt and CS.slug(nxt) != CS.slug(b.get('when') or ''):
            effects.append({'tide': CS.slug(nxt, fallback='phase')})
        if x.get('who'):
            label = b.get('label') or 'Talk to %s' % names[x['who']]
            row = {'id': fid, 'room': x['room'], 'kind': 'talk', 'target': x['who'], 'label': label[:60], 'text': b['text'],
                   'conditions': conds, 'effects': effects}
            talk_flags.setdefault(names[x['who']].lower(), fid)
        else:
            spot = x.get('spot')
            label = b.get('label') or (spot[:1].upper() + spot[1:] if spot else ' '.join(b['text'].split()[:5]) + '...')
            row = {'id': fid, 'room': x['room'], 'kind': 'examine', 'target': fid, 'label': label[:60], 'text': b['text'],
                   'conditions': conds, 'effects': effects}
            if x.get('pos') is not None:
                pres_rooms[x['room']].setdefault('interactions', {})[fid] = {'position': [x['pos'][0], 0, x['pos'][1]]}
        interactions.append(row)
    # the item (or the captive) and the keys
    keep_at = CF.keepsake_spot(pats[item_room], pres_rooms[item_room], None) or [0.0, 0.0, 0.0]
    keepsake = {'id': 'keepsake', 'group': 'keepsakes', 'room': item_room, 'name': 'Keepsake', 'label': 'Collect the keepsake',
                'text': 'Something worth finding.', 'asset': collect, 'character': '', 'dialogue': '', 'follower_flag': '',
                'conditions': []}
    group_name = 'Keepsakes'
    if captive is not None:
        rooms_by[item_room]['character_ids'].append(captive['cid'])
        pres_rooms[item_room].setdefault('characters', {})[captive['cid']] = {'position': list(keep_at), 'yaw': 180}
        keepsake.update(name=captive['name'], label='Free %s' % captive['name'], character=captive['cid'],
                        follower_flag='%s_follows' % captive['cid'], text='%s is free and follows you.' % captive['name'])
        group_name = 'Rescued'
        if item:
            rows.append({'feature': 'item', 'asked': item['name'], 'status': 'not_made',
                         'reason': 'the captive %s is the one thing collected' % captive['name'], 'closest': 'none',
                         'fix': 'drop the captive, or make the item a key (story.keys)'})
    elif item:
        nm = item['name']
        keepsake.update(name=nm, label='Take the %s' % nm if not nm.lower().startswith('the ') else 'Take %s' % nm,
                        text=item.get('about') or 'You have the %s.' % nm)
        group_name = nm
    pres_rooms[item_room].setdefault('collectibles', {})['keepsake'] = {'position': list(keep_at)}
    collectibles = [keepsake]
    groups = [{'id': 'keepsakes', 'name': group_name[:40], 'kind': 'keepsake', 'required': 1}]
    for kk in keys_out:
        nm = kk['name']
        collectibles.append({'id': kk['id'], 'group': 'keys', 'room': kk['room'], 'name': nm,
                             'label': 'Take the %s' % nm if not nm.lower().startswith('the ') else 'Take %s' % nm,
                             'text': 'You take the %s.' % nm if not nm.lower().startswith('the ') else 'You take %s.' % nm,
                             'asset': collect, 'character': '', 'dialogue': '', 'follower_flag': '', 'conditions': []})
        pres_rooms[kk['room']].setdefault('collectibles', {})[kk['id']] = {'position': [kk['pos'][0], 0.0, kk['pos'][1]]}
    if keys_out:
        groups.append({'id': 'keys', 'name': 'Keys', 'kind': 'key', 'required': len(keys_out)})
    finish = {'id': 'finish', 'room': finish_room, 'kind': 'use', 'target': 'rest', 'label': 'Finish the journey',
              'text': 'The journey is done.', 'conditions': [{'group': 'keepsakes', 'at_least': 1}],
              'effects': [{'flag': 'finished', 'value': True}]}
    if beat_flags:
        finish['conditions'].append({'flag': beat_flags[-1], 'equals': True})
    finish['conditions'] += [{'collected': kk['id']} for kk in keys_out if not kk['opens']]   # a key with no door: the finish
    interactions.append(finish)
    endings.append({'id': 'rest', 'conditions': [{'flag': 'finished', 'equals': True}], 'text': story.get('win') or 'The journey ends.'})
    ch = story.get('choice')
    if ch:
        asker = next((a for a in actors if ch.get('who') and a['name'].lower() == ch['who'].lower() and not a.get('captive')), None)
        asker = asker or next((a for a in actors if a['room'] == finish_room and not a.get('captive')), None) \
            or next((a for a in actors if not a.get('captive')), None)
        if asker is None:
            rows.append({'feature': 'choice', 'asked': ch['ask'], 'status': 'not_made', 'reason': 'nobody stands in a room to ask it',
                         'closest': 'none', 'fix': 'add a cast person (npc)'})
        else:
            flag('choice_right', 'Chose %s' % ch['right'])
            flag('choice_wrong', 'Chose wrongly')
            choices = [{'id': 'opt_%d' % (i + 1), 'text': o, 'conditions': [],
                        'effects': [{'flag': 'choice_right' if o.lower() == ch['right'].lower() else 'choice_wrong', 'value': True}],
                        'next': ''} for i, o in enumerate(ch['options'])]
            dialogues.append({'id': 'story_choice', 'character': asker['cid'], 'start_node': 'ask',
                              'nodes': [{'id': 'ask', 'text': ch['ask'], 'conditions': [], 'choices': choices}]})
            interactions.append({'id': 'ask_choice', 'room': asker['room'], 'kind': 'talk', 'target': asker['cid'],
                                 'label': ch['ask'][:40], 'text': ch['ask'],
                                 'conditions': ([{'flag': beat_flags[-1], 'equals': True}] if beat_flags else []) +
                                 [{'flag': 'choice_right', 'equals': False}, {'flag': 'choice_wrong', 'equals': False}],
                                 'effects': [{'dialogue': 'story_choice', 'node': 'ask'}]})
            finish['conditions'].append({'flag': 'choice_right', 'equals': True})
            endings.append({'id': 'wrong_choice', 'conditions': [{'flag': 'choice_wrong', 'equals': True}],
                            'text': story.get('lose') or 'That was the wrong answer. The story ends here.'})
    elif story.get('lose'):
        rows.append({'feature': 'lose', 'asked': story['lose'][:80], 'status': 'closest' if fight_rooms else 'not_made',
                     'reason': 'there is no fail ending without a story.choice',
                     'closest': 'a lost fight restarts at the checkpoint' if fight_rooms else 'none',
                     'fix': 'add a story.choice, or hand-author a fail ending'})
    spec = {'contract_version': '1.1.0', 'id': re.sub(r'[^a-z0-9_]', '_', ctx.name), 'title': story.get('title') or title_for(prompt),
            'description': CF.one_line(prompt)[:200],
            'metadata': {'template': TEMPLATE, 'authoring_status': 'create_flow_not_demo', 'created_by': 'hermes64 create',
                         'protagonist': 'traveller', 'style_pack': pack_id, 'hermes64_pack': ref,
                         'presentation': {'convention': 'hermes64-presentation/1', 'rotation_order': 'YXZ',
                                          'rotation_units': 'degrees', 'rooms': pres_rooms}},
            'start': {'location': entry_id, 'inventory': [], 'flags': start_flags, 'dialogue': {}, 'tide': start_tide, 'collected': []},
            'rooms': spec_rooms, 'characters': characters, 'items': [], 'flags': flags, 'dialogues': dialogues, 'quests': quests,
            'interactions': interactions, 'tide': tide, 'endings': endings, 'collectible_groups': groups, 'collectibles': collectibles}
    if dialogues:
        spec['start']['dialogue']['story_choice'] = ''
    made = []
    if fight_rooms:
        spec, made = attach_fights(CF, CS, spec, story, foes, fight_rooms, pats, rooms_by, entry_id, rows)
        collectibles, quests = spec['collectibles'], spec['quests']
        finish = next(i for i in spec['interactions'] if i['id'] == 'finish')
        for c in collectibles:
            fr = next((m for m in made if m['room'] == c['room']), None)
            if fr:
                c['conditions'] = list(c['conditions']) + [{'challenge': fr['challenge'], 'status': 'completed'}]
        finish['conditions'] = list(finish['conditions']) + [{'challenge': m['challenge'], 'status': 'completed'} for m in made]
    story_order(spec, blay, keys_out, made)
    for i, q in enumerate(story.get('quests', []), 1):
        kind, arg = q['done_when']
        cond = None
        if kind == 'beat':
            cond = [{'flag': beat_flags[arg - 1], 'equals': True}] if arg - 1 < len(beat_flags) else None
        elif kind == 'talk':
            cond = [{'flag': talk_flags[arg.lower()], 'equals': True}] if arg.lower() in talk_flags else None
        elif kind == 'item':
            cond = [{'collected': 'keepsake'}]
        elif kind == 'fight':
            cond = [{'challenge': made[-1]['challenge'], 'status': 'completed'}] if made else None
        elif kind == 'choice':
            cond = [{'flag': 'choice_right', 'equals': True}] if ch else None
        elif kind == 'end':
            cond = [{'flag': 'finished', 'equals': True}]
        if cond is None:
            rows.append({'feature': 'quest', 'asked': q['title'], 'status': 'not_made',
                         'reason': 'done_when %s %s is not in this game' % (kind, arg or ''), 'closest': 'none',
                         'fix': 'point done_when at a beat, a talk or the item'})
            continue
        quests.append({'id': 'quest_%d' % i, 'title': q['title'], 'description': q['title'], 'conditions': cond})
    return spec, made


def attach_fights(CF, CS, spec, story, foes, fight_rooms, pats, rooms_by, entry_id, rows=None):
    """One combat challenge per fight room (STORY 1.2 modules), each with its own checkpoint at the room's door."""
    table = CF.load_modules()
    m = table['modules']['combat_arena']
    a = m['archetype']
    archetypes, encounters, challenges, made = [], [], [], []
    ec = pats[entry_id]['centre_m']
    checkpoints = [{'id': '%s_safe' % entry_id, 'position_m': [ec[0], 0, ec[1]], 'room': entry_id}]
    taken = set()

    def arche(name, boss=False):
        aid = CS.slug(name, taken, 'boss' if boss else 'rival')
        taken.add(aid)
        row = {'id': aid, 'name': name[:40], 'max_health': CS.BOSS_HEALTH if boss else a['max_health'],
               'speed_mps': 1.3 if boss else a['speed_mps'], 'aggro_range_m': a['aggro_range_m'], 'leash_range_m': a['leash_range_m'],
               'attack_range_m': a['attack_range_m'], 'attack': dict(a['attack']),
               'fsm': {'initial': 'idle', 'template': a['template'], 'states': ['idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead']}}
        archetypes.append(row)
        return aid

    if len(fight_rooms) > MODULE_FIGHTS:     # LONGSTORY-2: said, not a failed build (combat module: 16 fights per game)
        keep = fight_rooms[:MODULE_FIGHTS - 1] + fight_rooms[-1:]
        if rows is not None:
            rows.append({'feature': 'fights', 'asked': '%d fights' % len(fight_rooms), 'status': 'closest',
                         'reason': 'one game runs at most %d fights (the combat module contract)' % MODULE_FIGHTS,
                         'closest': 'fights in %s' % ', '.join(rooms_by[r]['name'] for r in keep),
                         'fix': 'put several fighters in one place'})
        fight_rooms = keep
    n_boss = sum(1 for f in foes if f['role'] == 'boss' and f['room'] in fight_rooms)
    enemy_ids = {}
    for f in foes:
        if f['role'] == 'enemy' and f['name'].lower() not in enemy_ids:
            if len(set(enemy_ids.values())) >= MODULE_KINDS - n_boss - 1:   # 16 archetypes per game: later names share
                enemy_ids[f['name'].lower()] = sorted(set(enemy_ids.values()))[len(enemy_ids) % len(set(enemy_ids.values()))]
                continue
            enemy_ids[f['name'].lower()] = arche(f['name'])
    default_enemy = None
    extra_hp = 0
    offs = [(-1.5, -1.0), (1.5, -1.0), (0.0, -1.8)]
    for i, rid in enumerate(fight_rooms):
        pat = pats[rid]
        cx, cz = pat['centre_m']
        dx, dz = pat['door_point_m']
        x0, z0, x1, z1 = pat.get('arena_m') or pat['dress_rect_m']      # LONGSTORY-2: a pattern may name its arena

        def inside(x, z, m=0.6):                                         # LONGSTORY-2: spawns stay in the arena
            return [round(min(max(x, x0 + m), x1 - m), 2), 0, round(min(max(z, z0 + m), z1 - m), 2)]
        cid = 'fight_%s' % rid
        waves = fight_waves(story, foes, rid, fight_rooms, at_once=pat.get('at_once'))
        bosses = [f for f in foes if f['room'] == rid and f['role'] == 'boss']
        # LONGSTORY-2: the combat module contract holds waves 0..7 and 24 spawns per fight (story/modules/schema.py);
        # past that the rest is said, never a failed build
        room_waves, room_spawns = MODULE_WAVES - len(bosses), MODULE_SPAWNS - len(bosses)
        kept, total = [], 0
        for n in waves:
            if len(kept) < room_waves and total + n <= room_spawns:
                kept.append(n)
                total += n
        if kept != waves and rows is not None:
            rows.append({'feature': 'waves', 'asked': '%d fighters in %s' % (sum(waves), rooms_by[rid]['name']), 'status': 'closest',
                         'reason': 'one fight runs at most %d waves and %d fighters (the combat module contract)' % (MODULE_WAVES, MODULE_SPAWNS),
                         'closest': '%d fighters in %d waves' % (sum(kept), len(kept)), 'fix': 'put the other fighters in another place'})
        waves = kept
        names = [enemy_ids[f['name'].lower()] for f in foes if f['room'] == rid and f['role'] == 'enemy']
        if waves and not names:
            if default_enemy is None:
                default_enemy = arche(m['enemy_default'].title())
            names = [default_enemy]
        spawns = []
        for w, n in enumerate(waves):
            for j in range(n):
                ox, oz = offs[j] if j < len(offs) else spawn_ring(j)
                spawns.append({'id': '%s_%d_%d' % (rid, w + 1, j + 1), 'archetype': names[(w * 2 + j) % len(names)], 'wave': w,
                               'position_m': inside(cx + ox, cz + oz)})
        for j, b in enumerate(bosses):
            spawns.append({'id': '%s_boss_%d' % (rid, j + 1), 'archetype': arche(b['name'], True), 'wave': len(waves) + j,
                           'position_m': inside(cx, cz - 1.8)})
        extra_hp = max(extra_hp, max(0, sum(waves) - 2) + (CS.BOSS_HEALTH // 2) * len(bosses))
        checkpoints.append({'id': '%s_safe' % rid, 'position_m': [dx, 0, dz], 'room': rid})
        challenges.append({'id': cid, 'kind': 'combat', 'room': rid, 'subject': cid + '_arena', 'checkpoint': '%s_safe' % rid,
                           'conditions': [], 'retry': 'checkpoint', 'rewards': {'abilities': [], 'items': []}})
        encounters.append({'id': cid + '_arena', 'room': rid, 'arena': {'min': [x0, 0, z0], 'max': [x1, 4, z1]}, 'double_ko': 'failure',
                           'lose': 'player_health_zero', 'win': 'all_spawns_defeated', 'spawns': spawns})
        by_arch = {r['id']: r['name'] for r in archetypes}
        text = 'a fight in %s: %s' % (rooms_by[rid]['name'], ' then '.join(
            ['%d %s' % (n, by_arch[names[0]]) for n in waves] + [b['name'] for b in bosses]))
        made.append({'word': 'combat', 'module': 'combat_arena', 'room': rid, 'challenge': cid,
                     'enemies': [s['id'] for s in spawns], 'text': text + (' (final boss)' if i == len(fight_rooms) - 1 and bosses else '')})
    spec = copy.deepcopy(spec)
    spec['contract_version'] = '1.2.0'
    spec['gameplay'] = {'api_version': '1.0.0', 'seed': CF.SEED, 'verification_policy': 'conditional', 'modules': [
        {'id': 'abilities', 'version': '1.0.0', 'config': {'max_health': min(64, m['max_health'] + CS.PLAYER_HP_PER_ENEMY * extra_hp)},
         'entities': {'abilities': []}},
        {'id': 'challenge', 'version': '1.0.0', 'config': {'entry_cost': 'none', 'failure_progress': 'unchanged', 'max_active': 1},
         'entities': {'challenges': challenges, 'checkpoints': checkpoints}},
        {'id': 'combat', 'version': '1.0.0', 'config': {'max_simultaneous': 3}, 'entities': {'archetypes': archetypes, 'encounters': encounters}}]}
    spec['start']['modules'] = {'abilities': [], 'active': '', 'checkpoint': '%s_safe' % entry_id, 'completed': [],
                                'discovered': [], 'failed': ''}
    spec['metadata']['template'] = TEMPLATE.replace('_v1', '_modules_v1')
    return spec, made


def plan_lines(story, brief, family, keys=()):
    """(made, notes) for `create_flow plan` when the story builds the long game: the rooms, how they join, the keys,
    the fights and every place that becomes a story spot. Same room graph as the rooms stage (create_long.json slots)."""
    data = load()
    slot_data = data['outdoor_slots']
    fam = __import__('adventure_maker.create_flow', fromlist=['load_patterns']).load_patterns()['families'][family]
    bases = [p['id'] for p in fam['outdoor'] if p['id'] in slot_data and set(p.get('only_if_keys', [])) <= set(keys or [p['id']])]
    bases = bases or [p for p in slot_data if p in {q['id'] for q in fam['outdoor']}]
    if not bases:
        return [], ['long story: the %s family has no outdoor pattern with door slots; the two-room game is built' % family]
    n_in = min(len(slot_data[b]['inside']) for b in bases)
    n_road = min(len(slot_data[b]['road']) for b in bases)
    g = plan_graph(story, brief, data, lambda: (n_in, n_road), lambda: (n_in, n_road))
    names = {r['id']: r['name'] for r in g['rooms']}
    made = ['%d rooms, one per story place: %s' % (len(g['rooms']), ', '.join(
        '%s (%s%s)' % (r['name'], r['kind'], ', start' if r['id'] == g['entry'] else '') for r in g['rooms']))]
    made.append('ways: ' + '; '.join('%s -> %s (%s)' % (names[ln['a']], names[ln['b']], 'gate' if ln['kind'] == 'road' else 'door')
                                     for ln in g['links']))
    if story.get('keys'):
        made.append('keys: ' + '; '.join('%s in %s opens %s' % (k['name'], k.get('place') or 'a room', k.get('opens') or 'the finish')
                                         for k in story['keys']))
    foes = [c for c in story.get('cast', []) if c['role'] in ('enemy', 'boss')]
    if foes:
        made.append('fights: ' + '; '.join('%s in %s' % (c['name'], c.get('place') or 'the last room') for c in foes)
                    + ' (the last boss is the final boss)')
    beats = story.get('beats', [])
    if beats:
        made.append('%d beats in order across the rooms; it ends where the last beat is' % len(beats))
    notes = ['%s: %s (closest: %s; fix: %s)' % (r['asked'], r['reason'], r['closest'], r['fix']) for r in g['rows']]
    return made, notes
