"""Cross-reference, ownership and bounded-data checks for the closed module ABI."""
from . import schema as S
from .registry import DEPENDENCIES, API_VERSIONS, contracts, module_schema, index, entity_map
from ..errors import SpecError


def require(ok, path, reason):
    if not ok:
        raise SpecError(path + ': ' + reason)


def ref(value, values, path):
    require(value in values, path, 'missing reference ' + str(value))


def unique(values, path):
    ids = [v['id'] for v in values]
    require(len(ids) == len(set(ids)), path, 'duplicate ID')


def inside(point, room, path):
    require(0 <= point[0] <= room['grid_size'][0] and 0 <= point[2] <= room['grid_size'][1]
            and 0 <= point[1] <= 32, path, 'position outside declared room bounds')


def validate_header(spec):
    manifest = spec['gameplay']
    # API 1.1.0 is additive; an unknown version is checked against 1.0.0 and fails its version constant.
    version = manifest.get('api_version') if isinstance(manifest, dict) and manifest.get('api_version') in API_VERSIONS else '1.0.0'
    schema = contracts(version)['manifest']
    if isinstance(manifest, dict) and isinstance(manifest.get('modules'), list) and all(isinstance(m, dict) and isinstance(m.get('id'), str) for m in manifest['modules']):
        unique(manifest['modules'], 'gameplay/modules')
    # Pick the registered closed schema explicitly, retaining useful error paths.
    header = dict(schema, properties=dict(schema['properties'], modules=S.array(S.obj(id=S.ID, version={'const': version}, config={}, entities={}), 5)))
    S.validate(manifest, header)
    unique(manifest['modules'], 'gameplay/modules')
    mods = index(spec)
    require('abilities' in mods and 'challenge' in mods, 'gameplay', 'dependency requires abilities and challenge')
    for mid, m in mods.items():
        require(mid in DEPENDENCIES, 'gameplay/modules', 'unknown module ' + mid)
        if version != '1.0.0' and mid == 'combat' and isinstance(m.get('entities'), dict):
            # Precise error paths for the template-selected archetype forms and the two encounter forms.
            for i, row in enumerate(m['entities'].get('archetypes', []) if isinstance(m['entities'].get('archetypes'), list) else []):
                S.validate(row, S.enemy_form(row), 'gameplay/combat/archetypes/' + str(i))
            for i, row in enumerate(m['entities'].get('encounters', []) if isinstance(m['entities'].get('encounters'), list) else []):
                form = S.ENCOUNTER_1_2 if version == '1.2.0' else (S.ENCOUNTER_1_1 if isinstance(row, dict) and ('boss' in row or 'gate' in row) else S.ENCOUNTER)
                S.validate(row, form, 'gameplay/combat/encounters/' + str(i))
        S.validate(m, module_schema(mid, version), 'gameplay/' + mid)
        require(all(dep in mods for dep in DEPENDENCIES[mid]), mid, 'missing module dependency')
        for kind, values in m['entities'].items():
            unique(values, mid + '/' + kind)
    advanced = 'run' in manifest or any('moveset' in m['config'] for m in mods.values()) or any(
        any(k in e for k in ('bosses', 'attack_budget', 'attack_gap_ticks'))
        for e in entity_map(spec, 'combat', 'encounters').values())
    require(not advanced or manifest.get('movement_combat_profile') == 'combat2_v1', 'gameplay',
            'new simulation fields require movement_combat_profile combat2_v1')
    return mods


def validate_logic_reference(c, spec, effect=False):
    """Return True only for recognized 1.2 conditions/effects; core owns the rest."""
    abilities = entity_map(spec, 'abilities', 'abilities')
    challenges = entity_map(spec, 'challenge', 'challenges')
    if not effect and set(c) == {'ability'}:
        S.validate(c['ability'], S.ID, 'ability')
        ref(c['ability'], abilities, 'ability')
        return True
    if not effect and set(c) == {'challenge', 'status'}:
        S.validate(c, S.obj(challenge=S.ID, status=S.enum('completed')), 'challenge')
        ref(c['challenge'], challenges, 'challenge')
        return True
    if effect and set(c) == {'unlock'}:
        S.validate(c['unlock'], S.ID, 'unlock')
        ref(c['unlock'], abilities, 'unlock')
        return True
    return False


def validate_boss(aid, boss):
    """boss_phases_v1 structure: unique ids, first phase at full health, strictly descending thresholds, phase
    patterns that exist. An empty phase compiles on purpose: the checker reports the stalled fight."""
    path = aid + '/boss'
    unique(boss['patterns'], path + '/patterns')
    unique(boss['phases'], path + '/phases')
    patterns = {p['id'] for p in boss['patterns']}
    marks = [p['health_permille'] for p in boss['phases']]
    require(marks[0] == 1000, path + '/phases', 'first phase must start at full health (health_permille 1000)')
    require(all(a > b for a, b in zip(marks, marks[1:])), path + '/phases', 'phase thresholds must strictly descend')
    for phase in boss['phases']:
        for pid in phase['patterns']:
            ref(pid, patterns, path + '/phases/' + phase['id'])


def validate_boss_encounter(eid, encounter, archetypes, rooms, challenges):
    """Encounter 1.1.0: the boss spawn is a boss_phases_v1 in the last wave, every boss spawn is the named one, and
    the gate is a door of the room whose own conditions open it on the owning challenge's completion (module gates)."""
    bosses = [s['id'] for s in encounter['spawns'] if 'boss' in archetypes[s['archetype']]]
    named = encounter.get('bosses', [encounter.get('boss')] if encounter.get('boss') else [])
    require(not (encounter.get('bosses') and encounter.get('boss')), eid + '/boss', 'use boss OR bosses, not both')
    require(sorted(bosses) == sorted(named), eid + '/boss',
            'every named boss must be a boss_phases_v1 spawn and every boss spawn must be named')
    for bid in named:
        spawn = next(s for s in encounter['spawns'] if s['id'] == bid)
        require(spawn['wave'] == max(s['wave'] for s in encounter['spawns']), eid + '/boss', 'the boss must be in the last wave')
    gate = encounter.get('gate', '')
    if gate:
        doors = {d['id']: d for d in rooms[encounter['room']]['doors']}
        ref(gate, doors, eid + '/gate')
        owners = [cid for cid, c in challenges.items() if c['kind'] == 'combat' and c['subject'] == eid]
        require(any({'challenge': cid, 'status': 'completed'} in doors[gate]['conditions'] for cid in owners), eid + '/gate',
                'the gate door must list the owning challenge completion among its conditions (it opens on defeat)')


def validate(spec, logic):
    mods = index(spec)
    rooms = {r['id']: r for r in spec['rooms']}
    abilities = entity_map(spec, 'abilities', 'abilities')
    checkpoints = entity_map(spec, 'challenge', 'checkpoints')
    challenges = entity_map(spec, 'challenge', 'challenges')
    visited = set()
    def visit(aid, stack):
        require(aid not in stack, 'abilities/' + aid, 'prerequisite cycle')
        if aid in visited:
            return
        for dep in abilities[aid]['requires']:
            ref(dep, abilities, 'abilities/' + aid)
            visit(dep, stack + (aid,))
        visited.add(aid)
    for aid in abilities:
        visit(aid, ())
    for cid, point in checkpoints.items():
        ref(point['room'], rooms, 'checkpoint/' + cid)
        inside(point['position_m'], rooms[point['room']], 'checkpoint/' + cid)
    rewards = []
    subjects = []
    for cid, challenge in challenges.items():
        ref(challenge['room'], rooms, 'challenge/' + cid)
        ref(challenge['checkpoint'], checkpoints, 'challenge/' + cid + '/checkpoint')
        collection = 'encounters' if challenge['kind'] == 'combat' else 'tracks'
        targets = entity_map(spec, challenge['kind'], collection)
        ref(challenge['subject'], targets, 'challenge/' + cid + '/subject')
        require(targets[challenge['subject']]['room'] == challenge['room'], cid, 'subject room mismatch')
        pair = (challenge['kind'], challenge['subject'])
        require(pair not in subjects, cid, 'duplicate challenge subject owner')
        subjects.append(pair)
        logic(challenge['conditions'], 'challenge/' + cid + '/conditions')
        for item in challenge['rewards']['items']:
            ref(item, {i['id'] for i in spec['items']}, cid + '/reward')
            require(item not in rewards, cid, 'duplicate reward owner')
            rewards.append(item)
        for aid in challenge['rewards']['abilities']:
            ref(aid, abilities, cid + '/reward')
            require(not abilities[aid]['requires'], cid, 'reward abilities must have no prerequisites; gate the challenge instead')
    # Permanent unique reward tokens cannot be farmed, removed, or granted by another producer.
    def scan(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('give', 'take') and child in rewards:
                    require(False, path, 'challenge reward token has exclusive once-only ownership')
                scan(child, path + '/' + key)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scan(child, path + '/' + str(i))
    for key in ('interactions', 'dialogues'):
        scan(spec[key], key)
    require(not set(rewards).intersection(spec['start']['inventory']), 'start', 'reward token cannot be initially owned')
    archetypes = entity_map(spec, 'combat', 'archetypes')
    for aid, enemy in archetypes.items():
        require(enemy['leash_range_m'] >= enemy['aggro_range_m'] >= enemy['attack_range_m'], aid, 'invalid ordered ranges')
        if 'boss' in enemy:
            validate_boss(aid, enemy['boss'])
    for eid, encounter in entity_map(spec, 'combat', 'encounters').items():
        ref(encounter['room'], rooms, eid)
        require(('combat', eid) in subjects, eid, 'encounter needs exactly one challenge owner')
        lo, hi = encounter['arena']['min'], encounter['arena']['max']
        require(all(a < b for a, b in zip(lo, hi)), eid, 'arena minimum must precede maximum')
        inside(lo, rooms[encounter['room']], eid)
        inside(hi, rooms[encounter['room']], eid)
        unique(encounter['spawns'], eid + '/spawns')
        waves = sorted({s['wave'] for s in encounter['spawns']})
        require(waves == list(range(len(waves))), eid, 'spawn waves must be contiguous from zero')
        for wave in waves:
            require(sum(s['wave'] == wave for s in encounter['spawns']) <= mods['combat']['config']['max_simultaneous'], eid, 'spawn wave exceeds simultaneous bound')
        for spawn in encounter['spawns']:
            ref(spawn['archetype'], archetypes, eid + '/spawn')
            require(all(a <= p <= b for a, p, b in zip(lo, spawn['position_m'], hi)), eid, 'spawn outside arena')
        validate_boss_encounter(eid, encounter, archetypes, rooms, challenges)
    for tid, track in entity_map(spec, 'course', 'tracks').items():
        ref(track['room'], rooms, tid)
        require(('course', tid) in subjects, tid, 'course needs exactly one challenge owner')
        require(track['par_ticks'] <= track['time_limit_ticks'], tid, 'par time exceeds deadline')
        inside(track['start_position_m'], rooms[track['room']], tid)
        unique(track['checkpoints'], tid + '/checkpoints')
        for point in track['checkpoints']:
            inside(point['position_m'], rooms[track['room']], tid)
    regions = entity_map(spec, 'regions', 'regions')
    region_rooms = []
    for rid, region in regions.items():
        ref(region['room'], rooms, rid)
        require(region['room'] not in region_rooms, rid, 'duplicate region room owner')
        region_rooms.append(region['room'])
        ref(region['checkpoint'], checkpoints, rid)
        require(checkpoints[region['checkpoint']]['room'] == region['room'], rid, 'checkpoint belongs to a different region')
        unique(region['landmarks'], rid + '/landmarks')
        for landmark in region['landmarks']:
            inside(landmark['position_m'], rooms[region['room']], rid)
    if 'regions' in mods:
        require(set(region_rooms) == set(rooms), 'regions', 'each room must have exactly one region owner')
    endpoints = []
    for lid, link in entity_map(spec, 'regions', 'links').items():
        require(link['a']['region'] != link['b']['region'], lid, 'region link cannot be a self link')
        for here, there in ((link['a'], link['b']), (link['b'], link['a'])):
            ref(here['region'], regions, lid)
            ref(there['region'], regions, lid)
            rid = regions[here['region']]['room']
            doors = {d['id']: d for d in rooms[rid]['doors']}
            ref(here['door'], doors, lid + '/door')
            door = doors[here['door']]
            require((door['to_room'], door['to_door']) == (regions[there['region']]['room'], there['door']), lid, 'link disagrees with authoritative reciprocal door')
            endpoint = (rid, here['door'])
            require(endpoint not in endpoints, lid, 'duplicate link endpoint')
            endpoints.append(endpoint)
    if regions:
        require(set(endpoints) == {(rid, d['id']) for rid, r in rooms.items() for d in r['doors']}, 'regions', 'every door needs one region link')
    return spec


def validate_state(data, game, initial=False):
    S.validate(data, S.STATE, 'modules/state')
    abilities = entity_map(game, 'abilities', 'abilities')
    challenges = entity_map(game, 'challenge', 'challenges')
    checkpoints = entity_map(game, 'challenge', 'checkpoints')
    regions = entity_map(game, 'regions', 'regions')
    for field, domain in (('abilities', abilities), ('completed', challenges), ('discovered', regions)):
        for value in data[field]:
            ref(value, domain, 'modules/state/' + field)
        require(data[field] == sorted(data[field]), 'modules/state/' + field, 'IDs must be sorted')
    ref(data['checkpoint'], checkpoints, 'modules/state/checkpoint')
    for key in ('active', 'failed'):
        if data[key]:
            ref(data[key], challenges, 'modules/state/' + key)
            require(data[key] not in data['completed'], 'modules/state', 'completed challenge cannot be active/failed')
    require(not (data['active'] and data['failed']), 'modules/state', 'one active or failed challenge only')
    for aid in data['abilities']:
        require(all(dep in data['abilities'] for dep in abilities[aid]['requires']), aid, 'missing ability prerequisite')
    if initial:
        require(not data['completed'] and not data['active'] and not data['failed'], 'start/modules', 'initial challenge state must be ready')
        require(checkpoints[data['checkpoint']]['room'] == game['start']['location'], 'start', 'checkpoint must match initial room')
        expected = sorted(rid for rid, r in regions.items() if r['room'] == game['start']['location'])
        require(data['discovered'] == expected, 'start/modules', 'initial discovery must match start region')
