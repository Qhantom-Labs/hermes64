"""Canonical module compilation and room-local transitive dependency closures."""
import copy
import threading
from .registry import contracts, index, entity_map, api_version
from ..compiler import digest

# The gameplay API version of the game being compiled. story/compiler.py's compile_spec normalizes the source (this
# module's normalize) and then asks for contract() without arguments; keeping the version here lets a 1.1.0 game carry
# its own contract while story/compiler.py (pinned by the style-core toolchain identity) stays unchanged.
_compiling = threading.local()


def normalize(spec):
    _compiling.api_version = api_version(spec)
    spec['gameplay']['modules'].sort(key=lambda m: m['id'])
    for m in spec['gameplay']['modules']:
        for rows in m['entities'].values():
            rows.sort(key=lambda e: e['id'])
        if m['id'] == 'abilities':
            for ability in m['entities']['abilities']:
                ability['requires'].sort()
        if m['id'] == 'challenge':
            for challenge in m['entities']['challenges']:
                for values in challenge['rewards'].values():
                    values.sort()
        if m['id'] == 'combat':
            for encounter in m['entities']['encounters']:
                encounter['spawns'].sort(key=lambda s: s['id'])
            # 1.1.0 boss: pattern definitions by id; phases keep their (validated, descending) order and each
            # phase keeps its authored pattern order, which is the in-fight cycle order.
            for archetype in m['entities']['archetypes']:
                if 'boss' in archetype:
                    archetype['boss']['patterns'].sort(key=lambda p: p['id'])
        if m['id'] == 'regions':
            for region in m['entities']['regions']:
                region['landmarks'].sort(key=lambda l: l['id'])


def implementation_digest():
    """Pin trusted source, not timestamps, absolute paths, caches or runtime claims."""
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    paths = sorted(list(root.glob('*.py')) + list((root / 'modules').glob('*.py')))
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def contract(version=None):
    """Module contract block of a compiled game: the explicit version, else the version of the game being compiled
    (set by normalize), else 1.0.0."""
    version = version or getattr(_compiling, 'api_version', None) or '1.0.0'
    return {'api_version': version, 'state_version': '1.0.0', 'analysis_version': '1.0.0',
            'schema_hash': digest(contracts(version)), 'implementation_hash': implementation_digest(), 'runtime_status': 'not_implemented',
            'physical_evidence': 'not_run', 'human_evidence': 'not_run'}


def room_content(spec, rid):
    mods = index(spec)
    result = {}
    challenges = [c for c in entity_map(spec, 'challenge', 'challenges').values() if c['room'] == rid]
    checkpoints = [c for c in entity_map(spec, 'challenge', 'checkpoints').values()
                   if c['room'] == rid or any(ch['checkpoint'] == c['id'] for ch in challenges)]
    if challenges or checkpoints:
        result['challenge'] = {'config': mods['challenge']['config'], 'challenges': challenges, 'checkpoints': checkpoints}
    encounters = [e for e in entity_map(spec, 'combat', 'encounters').values() if e['room'] == rid]
    if encounters:
        used = {s['archetype'] for e in encounters for s in e['spawns']}
        result['combat'] = {'config': mods['combat']['config'], 'encounters': encounters,
                            'archetypes': [a for a in entity_map(spec, 'combat', 'archetypes').values() if a['id'] in used]}
    tracks = [t for t in entity_map(spec, 'course', 'tracks').values() if t['room'] == rid]
    if tracks:
        result['course'] = {'config': mods['course']['config'], 'tracks': tracks}
    regions = entity_map(spec, 'regions', 'regions')
    local = [r for r in regions.values() if r['room'] == rid]
    if local:
        links = [l for l in entity_map(spec, 'regions', 'links').values()
                 if any(regions[l[k]['region']]['room'] == rid for k in ('a', 'b'))]
        endpoint_doors = {(regions[l[k]['region']]['room'], l[k]['door']) for l in links for k in ('a', 'b')}
        endpoint_regions = sorted({l[k]['region'] for l in links for k in ('a', 'b')})
        checkpoint_map = entity_map(spec, 'challenge', 'checkpoints')
        result['regions'] = {'config': mods['regions']['config'], 'regions': local, 'links': links,
            'arrivals': [{'region': r, 'checkpoint': checkpoint_map[regions[r]['checkpoint']]} for r in endpoint_regions],
            'doors': [{'room': room['id'], 'doors': [d for d in room['doors'] if (room['id'], d['id']) in endpoint_doors]}
                      for room in spec['rooms'] if any(pair[0] == room['id'] for pair in endpoint_doors)]}
    # Ability definitions used by a room, including transitive prerequisites.
    used = set()
    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ('ability', 'unlock'):
                    used.add(x)
                elif k == 'abilities' and isinstance(x, list):
                    used.update(x)
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(result)
    walk([r for r in spec['rooms'] if r['id'] == rid])
    walk([a for a in spec['interactions'] if a['room'] == rid])
    local_room = next(r for r in spec['rooms'] if r['id'] == rid)
    local_collectibles = [c for c in spec.get('collectibles', []) if c['room'] == rid]
    walk(local_collectibles)
    dialogue_ids = {c['dialogue'] for c in local_collectibles if c['dialogue']}
    walk([d for d in spec['dialogues'] if d['character'] in local_room['character_ids'] or d['id'] in dialogue_ids])
    abilities = entity_map(spec, 'abilities', 'abilities')
    pending = list(used)
    while pending:
        for dep in abilities[pending.pop()]['requires']:
            if dep not in used:
                used.add(dep)
                pending.append(dep)
    if used or encounters:
        result['abilities'] = {'config': mods['abilities']['config'],
                               'abilities': [a for aid, a in abilities.items() if aid in used]}
    return copy.deepcopy(result)
