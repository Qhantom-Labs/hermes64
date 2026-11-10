"""Static trusted module catalogue. Data cannot register implementations.

API 1.1.0 (COMBAT lane) is an additive minor version: the 1.0.0 schemas, contracts and examples are unchanged, and
1.0.0 module data is also valid under 1.1.0. 1.1.0 adds the robot archetype templates (walker_patrol_v1,
brute_slam_v1, hover_drone_v1), the data-only boss template (boss_phases_v1) and the encounter `boss`/`gate` fields.
"""
import copy
from . import schema as s

API_VERSION = '1.0.0'
API_VERSIONS = ('1.0.0', '1.1.0', '1.2.0')
LATEST = '1.2.0'
DEPENDENCIES = {'abilities': (), 'challenge': ('abilities',), 'combat': ('challenge',),
                'course': ('challenge',), 'regions': ('challenge',)}
MODULES = {
    'abilities': (s.obj(max_health=s.integer(1, 64)), s.obj(abilities=s.array(s.ABILITY))),
    'challenge': (s.obj(max_active={'const': 1}, entry_cost={'const': 'none'}, failure_progress={'const': 'unchanged'}),
                  s.obj(checkpoints=s.array(s.CHECKPOINT, 64, 1), challenges=s.array(s.CHALLENGE, 16))),
    'combat': (s.obj(max_simultaneous=s.integer(1, 3)), s.obj(archetypes=s.array(s.ENEMY, 16, 1), encounters=s.array(s.ENCOUNTER, 16, 1))),
    'course': (s.obj(simulation_hz={'const': 60}, mover={'const': 'on_foot'}, max_speed_mps=s.number(0.1, 12)),
               s.obj(tracks=s.array(s.COURSE, 16, 1))),
    'regions': (s.obj(load_policy={'const': 'one_region'}, fast_travel={'const': False}),
                s.obj(regions=s.array(s.REGION, 32, 1), links=s.array(s.LINK, 64))),
}
# 1.1.0 differs only in the combat entities (each row may also use the 1.0.0 form).
MODULES_1_1 = dict(MODULES, combat=(s.obj(max_simultaneous=s.integer(1, 3)), s.obj(
    archetypes=s.array(s.ENEMY_1_1, 16, 1),
    encounters=s.array({'oneOf': [s.ENCOUNTER, s.ENCOUNTER_1_1]}, 16, 1))))


MODULES_1_2 = dict(MODULES_1_1,
    abilities=(s.optional(MODULES['abilities'][0], moveset=s.enum('brawler_v1')), MODULES['abilities'][1]),
    combat=(MODULES['combat'][0], s.obj(archetypes=s.array(s.ENEMY_1_1, 16, 1),
                                      encounters=s.array(s.ENCOUNTER_1_2, 16, 1))))


def check_version(version):
    if version not in API_VERSIONS:
        raise ValueError('unknown gameplay API version ' + str(version))
    return version


def module_schema(mid, version=API_VERSION):
    config, entities = {'1.0.0': MODULES, '1.1.0': MODULES_1_1, '1.2.0': MODULES_1_2}[check_version(version)][mid]
    return s.obj(id={'const': mid}, version={'const': version}, config=config, entities=entities)


def contracts(version=API_VERSION):
    result = {mid: dict(module_schema(mid, version), **{'$schema': 'https://json-schema.org/draft/2020-12/schema'}) for mid in MODULES}
    result['manifest'] = dict(s.obj(api_version={'const': version}, seed=s.integer(0, 2147483647),
        verification_policy=s.enum('logical_only', 'conditional'), modules=s.array({'oneOf': [module_schema(mid, version) for mid in MODULES]}, 5)),
        **{'$schema': 'https://json-schema.org/draft/2020-12/schema'})
    if version == '1.2.0':
        result['manifest'] = s.optional(result['manifest'], movement_combat_profile=s.enum('combat2_v1'), run=s.RUN)
    result['state'] = dict(s.STATE, **{'$schema': 'https://json-schema.org/draft/2020-12/schema'})
    return copy.deepcopy(result)


def registry(version=API_VERSION):
    return {mid: {'version': version, 'state_version': '1.0.0', 'story_versions': ['1.2.0'],
                  'dependencies': {dep: version for dep in deps},
                  'status': 'contract_only', 'runtime_status': 'not_implemented',
                  'schema': module_schema(mid, version)} for mid, deps in DEPENDENCIES.items()}


def api_version(spec):
    """The manifest's gameplay API version ('1.0.0' when absent or unknown; validation rejects unknown ones)."""
    value = spec.get('gameplay', {}).get('api_version') if isinstance(spec.get('gameplay'), dict) else None
    return value if value in API_VERSIONS else API_VERSION


def index(spec):
    return {m['id']: m for m in spec.get('gameplay', {}).get('modules', [])}


def entities(spec, mid, collection):
    return index(spec).get(mid, {}).get('entities', {}).get(collection, [])


def entity_map(spec, mid, collection):
    return {e['id']: e for e in entities(spec, mid, collection)}
