"""Small, deterministic game-template registry. Theme and story specifics are data."""
import copy
import re

from .safety import fail

DEFAULT_TEMPLATE = 'two_room_collect_v1'
ARENA_WORDS = frozenset(('fight', 'wave', 'robot', 'boss', 'bosses', 'beat', 'brawl', 'arena', 'rescue', 'fastest', 'time'))
TEMPLATES = {'two_room_collect_v1': {'contract': '1.1.0'}, 'arena_run_v1': {'contract': '1.2.0'}}


def pick_template(premise, explicit=None):
    if explicit is not None:
        if explicit not in TEMPLATES:
            fail('new_template', 'Unknown template; choose ' + ', '.join(TEMPLATES) + '.')
        return explicit, 'chosen'
    tokens = re.findall(r'[a-z]+', premise.lower())
    hits = list(dict.fromkeys(w for w in tokens if w in ARENA_WORDS or w.rstrip('s') in ARENA_WORDS))
    if len(hits) >= 2:
        return 'arena_run_v1', 'auto: matched ' + ', '.join(hits)
    return DEFAULT_TEMPLATE, 'default starter'


def wave_spawns(waves, anchors, prefix='enemy'):
    """Preserve authored groups, splitting each into <=3-live consecutive wave indices."""
    out, index = [], 0
    for group in waves:
        robots = []
        for row in group:
            count = row.get('count')
            if type(count) is not int or not 1 <= count <= 24:
                fail('template_waves', 'Robot counts must be integers from 1 to 24.')
            robots.extend([row['robot']] * count)
        if not robots:
            fail('template_waves', 'A wave group cannot be empty.')
        for offset in range(0, len(robots), 3):
            if index > 7 or len(out) + len(robots[offset:offset + 3]) > 24:
                fail('template_waves', 'An encounter supports at most eight groups and 24 spawns; split the arena.')
            for robot in robots[offset:offset + 3]:
                out.append({'id': '%s_%d' % (prefix, len(out)), 'archetype': robot,
                            'position_m': copy.deepcopy(anchors[len(out) % len(anchors)]), 'wave': index})
            index += 1
    return out


def stock_robots():
    """Trusted reusable robot behaviours; premise rows rename/override these, not code."""
    states = ['idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead']
    def base(rid, template, hp, speed, reach, windup, active, recovery):
        return {'id': rid, 'name': rid.title(), 'max_health': hp, 'speed_mps': speed,
                'aggro_range_m': 12, 'leash_range_m': 20, 'attack_range_m': reach,
                'fsm': {'template': template, 'initial': 'idle', 'states': list(states)},
                'attack': {'windup_ticks': windup, 'active_ticks': active, 'recovery_ticks': recovery, 'damage': 1},
                'robot': {'hurt_ticks': 14, 'knockback_m': 0.5, 'push_m': 0.4, 'hitstop_ticks': 2,
                          'armor': 'none', 'heal_drop': 0, 'cue': 'core.machine.servo.short'}}
    walker = base('walker', 'walker_patrol_v1', 1, 1.4, 1.1, 30, 10, 34)
    walker['walker'] = {'patrol_m': 1.5, 'spot_ticks': 20, 'bump_speed_mps': 4.5}
    brute = base('brute', 'brute_slam_v1', 2, 0.9, 2.2, 48, 12, 70)
    brute['brute'] = {'slam_radius_m': 1.3, 'wave_speed_mps': 5, 'wave_max_m': 4, 'wave_width_m': 0.5}
    drone = base('drone', 'hover_drone_v1', 1, 1.3, 6, 36, 6, 50)
    drone['hover'] = {'keep_distance_m': 3.5, 'strafe_mps': 1, 'strafe_ticks': 90, 'hover_m': 0.6,
                      'shot': {'speed_mps': 4.5, 'radius_m': 0.25, 'lifetime_ticks': 180, 'deflectable': True}}
    boss = base('guardian', 'boss_phases_v1', 3, 1.2, 2.4, 48, 12, 72)
    boss.pop('attack')
    boss['robot']['armor'] = 'until_recover'
    boss['boss'] = {'defeat_hitstop_ticks': 6,
                    'phases': [{'id': 'guard', 'health_permille': 1000, 'patterns': ['charge']}],
                    'patterns': [{'id': 'charge', 'kind': 'bump', 'windup_ticks': 48, 'active_ticks': 14,
                                  'recovery_ticks': 72, 'damage': 1, 'speed_mps': 5, 'size_m': 1.2,
                                  'count': 1, 'deflectable': False, 'cue': 'core.combat.swing.light'}]}
    return [walker, brute, drone, boss]


def arena_spec(premise, project, pack, rooms, slots=None):
    from .pack_rooms import instantiate
    slots = slots or {}
    available = {r['id']: r for r in rooms['rooms']}
    order = slots.get('rooms', {}).get('order') or list(available)
    if len(order) < 3 or len(order) != len(dict.fromkeys(order)) or any(r not in available for r in order):
        fail('template_rooms', 'Choose at least three distinct room ids from the selected pack.')
    selected = [available[r] for r in order]
    hero_id = slots.get('hero', {}).get('id', 'hero')
    spec = premise_spec(premise, project, pack)
    spec.update(contract_version='1.2.0', rooms=[], characters=[], collectible_groups=[], collectibles=[])
    spec['metadata'].update(template='arena_run_v1', authoring_status='generated_template', protagonist=hero_id,
                            style_pack=pack['id'], presentation={'rooms': {}, 'challenges': {}})
    params = {'costume': 'plain', 'colour': pack['palette'][0], 'voice_tags': []}
    spec['characters'] = [{'id': hero_id, 'name': slots.get('hero', {}).get('name', 'Champion'), 'role': 'protagonist',
                           'body_id': 'core_humanoid', 'base_rig_id': 'human_16', 'params': params,
                           'role_profiles': {'protagonist': copy.deepcopy(params)}}]
    spec['start']['location'] = order[0]
    spec['interactions'][0].update(room=order[-1], conditions=[], label=slots.get('goal', {}).get('label', 'Finish the run'),
                                   text=slots.get('goal', {}).get('text', 'The keep is safe.'))
    spec['endings'][0]['text'] = slots.get('goal', {}).get('ending', 'The run is complete.')
    challenges, checkpoints, encounters = [], [], []
    archetypes = stock_robots()
    stock = {r['id']: r for r in archetypes}
    for row in slots.get('robots', []):
        if row['base'] not in stock or row['base'] == 'guardian':
            fail('template_robot', 'Robot base must be walker, brute or drone.')
        new = copy.deepcopy(stock[row['base']])
        new.update(id=row['id'], name=row['name'], max_health=row.get('max_health', new['max_health']))
        new['attack']['damage'] = row.get('damage', 1)
        archetypes.append(new)
    boss_ids = []
    for row in slots.get('bosses', []):
        new = copy.deepcopy(stock['guardian'])
        new.update(id=row['id'], name=row['name'], max_health=row.get('max_health', 3))
        if row.get('patterns'):
            new['boss']['patterns'] = copy.deepcopy(row['patterns'])
            new['boss']['phases'][0]['patterns'] = [p['id'] for p in row['patterns']]
        archetypes.append(new)
        boss_ids.append(new['id'])
    arenas = {a['room']: a for a in slots.get('arenas', [])}
    prior = []
    for i, row in enumerate(selected):
        rid = row['id']
        room, presentation = instantiate(row, hero_id)
        spec['rooms'].append(room)
        spec['metadata']['presentation']['rooms'][rid] = presentation
        cp = rid + '_safe'
        checkpoints.append({'id': cp, 'room': rid, 'position_m': copy.deepcopy(row['anchors']['checkpoint'])})
        doors = {d['id']: d for d in room['doors']}
        # Door ids may differ across packs; choose authored forward/back by explicit connection metadata or walls.
        front = doors.get('forward') or doors.get('north')
        back = doors.get('back') or doors.get('south')
        needed = ([back] if i else []) + ([front] if i + 1 < len(order) else [])
        if any(d is None for d in needed):
            fail('template_rooms', 'Pack room %s needs authored forward/back door positions.' % rid)
        room['doors'] = needed
        for door in needed:
            forward = door is front
            target = selected[i + (1 if forward else -1)]['room']
            candidates = ('back', 'south') if forward else ('forward', 'north')
            dest = next((d for d in target['doors'] if d['id'] in candidates), None)
            if dest is None:
                fail('template_rooms', 'Pack door chain has no matching entrance.')
            door.update(to_room=target['id'], to_door=dest['id'], conditions=[])
        if i == 0:
            continue
        final = i == len(order) - 1
        names = slots.get('finale', {}).get('bosses') or boss_ids or ['guardian']
        groups = names if final else [None]
        for j, boss in enumerate(groups):
            cid = rid + ('_boss_%d' % j if final else '_wave')
            eid = cid + '_encounter'
            label = arenas.get(rid, {}).get('label', room['name'])
            challenges.append({'id': cid, 'kind': 'combat', 'subject': eid, 'room': rid, 'checkpoint': cp,
                               'conditions': copy.deepcopy(prior), 'retry': 'checkpoint', 'rewards': {'items': [], 'abilities': []}})
            waves = arenas.get(rid, {}).get('waves', [[{'robot': 'walker', 'count': 2}], [{'robot': 'walker', 'count': 1}]])
            spawns = ([{'id': cid + '_enemy', 'archetype': boss, 'position_m': row['anchors']['boss'][j], 'wave': 0}]
                      if final else wave_spawns(waves, row['anchors']['spawns'], cid))
            encounters.append({'id': eid, 'room': rid, 'arena': copy.deepcopy(row['anchors']['arena']), 'spawns': spawns,
                               'win': 'all_spawns_defeated', 'lose': 'player_health_zero', 'double_ko': 'failure',
                               'boss': spawns[0]['id'] if final else '', 'gate': front['id'] if front and not final else ''})
            spec['metadata']['presentation']['challenges'][cid] = {'label': label}
            prior = [{'challenge': cid, 'status': 'completed'}]
        if front and not final:
            front['conditions'] = copy.deepcopy(prior)
    spec['interactions'][0]['conditions'] = copy.deepcopy(prior)
    spec['metadata']['presentation']['rooms'][order[-1]]['interactions'] = {
        'interact:finish': {'position': copy.deepcopy(selected[-1]['anchors']['interact'])}}
    for npc in slots.get('npcs', []):
        if npc['room'] not in order or npc['id'] in [c['id'] for c in spec['characters']]:
            fail('template_cast', 'NPC ids must be unique and use a room in this story.')
        source = available[npc['room']]
        position = source['anchors'].get(npc['anchor'])
        if position is None:
            fail('template_cast', 'The pack room has no ' + npc['anchor'] + ' anchor.')
        spec['characters'].append({'id': npc['id'], 'name': npc['name'], 'role': 'companion',
                                   'body_id': 'core_humanoid', 'base_rig_id': 'human_16', 'params': copy.deepcopy(params),
                                   'role_profiles': {'companion': copy.deepcopy(params)}})
        next(r for r in spec['rooms'] if r['id'] == npc['room'])['character_ids'].append(npc['id'])
        placed = spec['metadata']['presentation']['rooms'][npc['room']].setdefault('characters', {})
        placed[npc['id']] = {'position': copy.deepcopy(position), 'yaw': 180}
        if npc.get('clip', 'idle') != 'idle':   # CHARBIND: the actor bridge plays it (idle when the body lacks it)
            placed[npc['id']]['clip'] = npc['clip']
    spec['start']['modules'] = {'abilities': [], 'completed': [], 'active': '', 'failed': '',
                                'checkpoint': checkpoints[0]['id'], 'discovered': []}
    spec['gameplay'] = {'api_version': '1.1.0', 'seed': 7, 'verification_policy': 'conditional', 'modules': [
        {'id': 'abilities', 'version': '1.1.0', 'config': {'max_health': slots.get('run', {}).get('max_health', 3)}, 'entities': {'abilities': []}},
        {'id': 'challenge', 'version': '1.1.0', 'config': {'max_active': 1, 'entry_cost': 'none', 'failure_progress': 'unchanged'},
         'entities': {'checkpoints': checkpoints, 'challenges': challenges}},
        {'id': 'combat', 'version': '1.1.0', 'config': {'max_simultaneous': 3}, 'entities': {'archetypes': archetypes, 'encounters': encounters}}]}
    return spec


def adopt_combat2(spec, slots, boss_anchors):
    """Adopt L1's gameplay 1.2.0 contract; called only when that contract/runtime ships."""
    gameplay = spec['gameplay']
    gameplay.update(api_version='1.2.0', movement_combat_profile='combat2_v1')
    rules = dict(clock='first_control_to_last_challenge', death_penalty_ticks=600, max_health=3,
                 reset_encounter_on_death=True, pause_clock_in_cutscene=True, hit_invulnerability_ticks=45)
    rules.update(slots.get('run', {}))
    gameplay['run'] = rules
    modules = {m['id']: m for m in gameplay['modules']}
    for module in modules.values():
        module['version'] = '1.2.0'
    modules['abilities']['config'].update(max_health=rules['max_health'], moveset=slots.get('moveset', 'brawler_v1'))
    challenges = modules['challenge']['entities']['challenges']
    encounters = modules['combat']['entities']['encounters']
    finale_room = spec['rooms'][-1]['id']
    final_challenges = [c for c in challenges if c['room'] == finale_room]
    first = final_challenges[0]
    removed = {c['id'] for c in final_challenges[1:]}
    final_encounters = {c['subject'] for c in final_challenges}
    finale = next(e for e in encounters if e['id'] == first['subject'])
    bosses = slots.get('finale', {}).get('bosses') or [s['archetype'] for e in encounters if e['id'] in final_encounters for s in e['spawns']]
    if not 1 <= len(bosses) <= 3:
        fail('template_bosses', 'A finale needs one to three boss archetypes.')
    finale['spawns'] = [{'id': first['id'] + '_enemy_%d' % i, 'archetype': bid,
                         'position_m': copy.deepcopy(boss_anchors[i]), 'wave': 0} for i, bid in enumerate(bosses)]
    finale['boss'] = ''
    finale['bosses'] = [s['id'] for s in finale['spawns']]
    budget = slots.get('finale', {}).get('attack_budget', {'count': 1, 'gap_ticks': 30})
    finale.update(attack_budget=budget['count'], attack_gap_ticks=budget['gap_ticks'])
    modules['challenge']['entities']['challenges'] = [c for c in challenges if c['id'] not in removed]
    modules['combat']['entities']['encounters'] = [e for e in encounters if e['room'] != finale_room or e is finale]
    spec['interactions'][0]['conditions'] = [{'challenge': first['id'], 'status': 'completed'}]
    labels = spec['metadata']['presentation']['challenges']
    for cid in removed:
        labels.pop(cid, None)
    for encounter in modules['combat']['entities']['encounters']:
        owner = next(c for c in modules['challenge']['entities']['challenges'] if c['subject'] == encounter['id'])
        encounter['label'] = labels[owner['id']]['label']
    return spec


def build(template, premise, project, pack, rooms=None, slots=None, combat2=False):
    pick_template(premise, explicit=template)
    if template == DEFAULT_TEMPLATE:
        return premise_spec(premise, project, pack)
    spec = arena_spec(premise, project, pack, rooms, slots)
    if combat2:
        final_id = spec['rooms'][-1]['id']
        anchors = next(r['anchors']['boss'] for r in rooms['rooms'] if r['id'] == final_id)
        adopt_combat2(spec, slots or {}, anchors)
    return spec



def name_starter(spec, premise, pack):
    """R10: deterministic display-text only; ids, progression and structure never change."""
    tokens = re.findall(r'[a-z]+', premise.lower())
    verbs = {'searches', 'finds', 'repairs', 'relights', 'explores', 'seeks', 'collects', 'rescues', 'restores', 'visits'}
    action = next((i for i, token in enumerate(tokens) if token in verbs), None)
    subject = [w for w in tokens[:action] if w not in ('a', 'an', 'the')] if action else []
    hero = ' '.join(subject[:4]).title() or pack['name'] + ' Explorer'
    places = {'village', 'station', 'lighthouse', 'forest', 'castle', 'tower', 'world', 'island', 'harbor', 'harbour', 'temple'}
    index = next((i for i, token in reversed(list(enumerate(tokens))) if token in places and (action is None or i > action)), None)
    if index is None:
        place = pack['name']
    else:
        start = index
        while start > (action + 1 if action is not None else 0) and index - start < 2 and tokens[start - 1] not in ('a', 'an', 'the', 'in', 'for', 'to', 'its'):
            start -= 1
        place = ' '.join(tokens[start:index + 1]).title()
    objects = {'lantern', 'key', 'gem', 'flower', 'crystal', 'relic', 'book', 'star', 'bell', 'seed', 'map'}
    found = next((token for token in reversed(tokens) if token in objects), None)
    item = found.title() if found else place + ' Token'
    spec['rooms'][0]['name'] = place + ' Approach'
    spec['rooms'][1]['name'] = place
    for character in spec['characters']:
        if character['id'] == spec['metadata'].get('protagonist'):
            character['name'] = hero
    spec['collectibles'][0].update(name=item, label='Collect the ' + item.lower(), text='You found the ' + item.lower() + '.')
    spec['collectible_groups'][0]['name'] = item + ' Collection'
    spec['interactions'][0]['text'] = 'The ' + item.lower() + ' has been recovered.'
    spec['endings'][0]['text'] = hero + ' completes the journey through ' + place + '.'
    return spec


def premise_spec(premise, project, pack):
    def door(to):
        return {'id': 'passage', 'wall': 'north', 'position': 1, 'to_room': to,
                'to_door': 'passage', 'label': 'Through the passage', 'conditions': []}
    def room(id, to, people):
        # Pack descriptions are authoring metadata, never player-facing room narration.
        return {'id': id, 'name': id.replace('_', ' ').title(), 'description': premise,
                'grid_size': [4, 4], 'kit_refs': [], 'doors': [door(to)],
                'cameras': [{'id': 'fixed', 'position': [2, 3, 5], 'look_at': [2, 0, 2]}],
                'props': [], 'character_ids': people}
    params = {'costume': 'plain', 'colour': pack['palette'][0], 'voice_tags': []}
    # Project slugs may contain '-', story IDs may not ([a-z][a-z0-9_]*): map it so a hyphenated project compiles.
    return {'contract_version': '1.1.0', 'id': project.replace('-', '_'), 'title': pack['name'] + ' Adventure', 'description': premise,
            'metadata': {'template': 'two_room_collect_v1', 'authoring_status': 'starter_not_demo'},
            'start': {'location': 'room_a', 'inventory': [], 'flags': {'finished': False},
                      'dialogue': {}, 'tide': {'state': 'calm', 'tick': 0}, 'collected': []},
            'rooms': [room('room_a', 'room_b', ['inhabitant']), room('room_b', 'room_a', [])],
            'characters': [{'id': 'inhabitant', 'name': 'Inhabitant', 'role': 'host', 'body_id': 'core_humanoid',
                            'base_rig_id': 'human_16', 'params': dict(params),
                            'role_profiles': {'host': dict(params), 'guide': dict(params)}}],
            'items': [], 'flags': [{'id': 'finished', 'initial': False, 'description': 'Finish the journey.'}],
            'dialogues': [], 'quests': [],
            'interactions': [{'id': 'finish', 'room': 'room_a', 'kind': 'use', 'target': 'rest', 'label': 'Finish the journey',
                              'text': 'The keepsake has been recovered.', 'conditions': [{'group': 'keepsakes', 'at_least': 1}],
                              'effects': [{'flag': 'finished', 'value': True}]}],
            'tide': {'id': 'cycle', 'states': [{'id': 'calm', 'label': 'Calm', 'duration': 1}],
                     'wait_label': 'Wait', 'wait_text': 'A moment passes.'},
            'endings': [{'id': 'rest', 'conditions': [{'flag': 'finished', 'equals': True}], 'text': 'The journey ends.'}],
            'collectible_groups': [{'id': 'keepsakes', 'name': 'Keepsakes', 'kind': 'keepsake', 'required': 1}],
            'collectibles': [{'id': 'keepsake', 'group': 'keepsakes', 'room': 'room_b', 'name': 'Keepsake',
                              'label': 'Collect the keepsake', 'text': 'Something worth finding.', 'asset': 'core/keepsake',
                              'character': '', 'dialogue': '', 'follower_flag': '', 'conditions': []}]}
