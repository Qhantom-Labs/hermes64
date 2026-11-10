"""Closed JSON Schema subset and dependency-free admission checks (Python 3.9)."""
import math
import re
from ..errors import SpecError


def obj(**fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


def array(items, maximum=32, minimum=0, unique=False):
    out = {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}
    if unique:
        out['uniqueItems'] = True
    return out


def integer(low, high):
    return {'type': 'integer', 'minimum': low, 'maximum': high}


def number(low, high):
    return {'type': 'number', 'minimum': low, 'maximum': high}


def enum(*values):
    return {'enum': list(values)}


ID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,63}$', 'minLength': 1, 'maxLength': 64}
TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 256}
EMPTY_ID = {'oneOf': [ID, {'const': ''}]}
VEC = array(number(-1024, 1024), 3, 3)
IDS = array(ID, 32, unique=True)
CONDITION = {'oneOf': [obj(ability=ID), obj(challenge=ID, status=enum('completed')),
    obj(item=ID, present={'type': 'boolean'}), obj(flag=ID, equals={'type': 'boolean'}),
    obj(location=ID), obj(tide=ID), obj(dialogue=ID, node=EMPTY_ID), obj(role=ID, equals=ID),
    obj(collected=ID), obj(group=ID, at_least=integer(0, 128))]}
CONDITIONS = array(CONDITION)
ABILITY = obj(id=ID, name=TEXT, requires=IDS)
CHECKPOINT = obj(id=ID, room=ID, position_m=VEC)
CHALLENGE = obj(id=ID, kind=enum('combat', 'course'), subject=ID, room=ID, checkpoint=ID,
                conditions=CONDITIONS, retry=enum('checkpoint'), rewards=obj(items=IDS, abilities=IDS))
ENEMY = obj(id=ID, name=TEXT, max_health=integer(1, 64), speed_mps=number(0.1, 20),
    aggro_range_m=number(0.1, 64), leash_range_m=number(0.1, 64), attack_range_m=number(0.1, 8),
    fsm=obj(template=enum('melee_approach_v1', 'melee_dash_v1'), initial=enum('idle'),
            states=array(enum('idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead'), 7, 7, True)),
    attack=obj(windup_ticks=integer(1, 600), active_ticks=integer(1, 120), recovery_ticks=integer(1, 600),
               damage=integer(1, 64)))
ENCOUNTER = obj(id=ID, room=ID, arena=obj(min=VEC, max=VEC),
    spawns=array(obj(id=ID, archetype=ID, position_m=VEC, wave=integer(0, 7)), 24, 1),
    win=enum('all_spawns_defeated'), lose=enum('player_health_zero'), double_ko=enum('failure'))
COURSE = obj(id=ID, room=ID, start_position_m=VEC, countdown_ticks=integer(0, 600),
    par_ticks=integer(1, 216000), time_limit_ticks=integer(1, 216000), laps=enum(1), pause_policy=enum('freeze'),
    checkpoints=array(obj(id=ID, position_m=VEC, radius_m=number(0.1, 4)), 32, 1))
REGION = obj(id=ID, room=ID, checkpoint=ID,
    landmarks=array(obj(id=ID, name=TEXT, position_m=VEC), 16, 1))
ENDPOINT = obj(region=ID, door=ID)
LINK = obj(id=ID, a=ENDPOINT, b=ENDPOINT)
STATE = obj(abilities=IDS, completed=array(ID, 16, unique=True), active=EMPTY_ID, failed=EMPTY_ID,
            checkpoint=ID, discovered=array(ID, 32, unique=True))

# ---------------------------------------------------------------- gameplay API 1.1.0 (additive; COMBAT lane)
# 1.0.0 data stays valid unchanged under 1.1.0. The new archetype forms are selected by fsm.template; every new
# object is closed like the 1.0.0 ones. `cue` names an audio catalog id (presentation only, never simulated).
CUE = {'oneOf': [{'type': 'string', 'pattern': '^[a-z][a-z0-9_]*(\\.[a-z0-9_]+){1,5}$', 'minLength': 3, 'maxLength': 96},
                 {'const': ''}]}
STATES = array(enum('idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead'), 7, 7, True)
ATTACK = obj(windup_ticks=integer(1, 600), active_ticks=integer(1, 120), recovery_ticks=integer(1, 600),
             damage=integer(1, 64))
ROBOT_TEMPLATES = ('walker_patrol_v1', 'brute_slam_v1', 'hover_drone_v1')
BOSS_TEMPLATES = ('boss_phases_v1',)
# Shared robot tuning: stagger, knockback taken, push given, tiny hit-stop, armour (until_recover: hits only land
# while the robot recovers from its own attack), reward drop (health restored when picked up), telegraph cue.
ROBOT = obj(hurt_ticks=integer(1, 60), knockback_m=number(0, 1.5), push_m=number(0, 1.5), hitstop_ticks=integer(0, 3),
            armor=enum('none', 'until_recover'), heal_drop=integer(0, 4), cue=CUE)
WALKER = obj(patrol_m=number(0, 8), spot_ticks=integer(0, 60), bump_speed_mps=number(0.5, 12))
BRUTE = obj(slam_radius_m=number(0.3, 4), wave_speed_mps=number(0.5, 12), wave_max_m=number(0.5, 12),
            wave_width_m=number(0.1, 2))
SHOT = obj(speed_mps=number(0.5, 20), radius_m=number(0.05, 2), lifetime_ticks=integer(1, 600),
           deflectable={'type': 'boolean'})
HOVER = obj(keep_distance_m=number(0.5, 12), strafe_mps=number(0, 8), strafe_ticks=integer(1, 600),
            hover_m=number(0, 2), shot=SHOT)
# Boss patterns reuse the robot attacks (bump, slam, shot) plus the signature surge (dash lane ending in a
# shockwave). speed_mps / size_m / count mean, per kind: bump lunge speed / contact reach / -; slam shockwave speed /
# shockwave reach / -; shot projectile speed / projectile radius / fan count; surge dash speed / shockwave reach / -.
PATTERN = obj(id=ID, kind=enum('bump', 'slam', 'shot', 'surge'), windup_ticks=integer(1, 600),
              active_ticks=integer(1, 120), recovery_ticks=integer(1, 600), damage=integer(1, 64),
              speed_mps=number(0.5, 20), size_m=number(0.05, 12), count=integer(1, 5),
              deflectable={'type': 'boolean'}, cue=CUE)
# A phase is active while health <= health_permille / 1000 of max_health (first phase 1000, strictly descending);
# its patterns run in order, cycling. An empty pattern list compiles (the checker rejects the stalled fight).
PHASE = obj(id=ID, health_permille=integer(1, 1000), patterns=array(ID, 8, 0))
BOSS = obj(phases=array(PHASE, 4, 1), patterns=array(PATTERN, 8, 1), defeat_hitstop_ticks=integer(0, 6))


def _archetype(templates, with_attack=True, **extra):
    fields = dict(id=ID, name=TEXT, max_health=integer(1, 64), speed_mps=number(0.1, 20),
                  aggro_range_m=number(0.1, 64), leash_range_m=number(0.1, 64), attack_range_m=number(0.1, 8),
                  fsm=obj(template=enum(*templates), initial=enum('idle'), states=STATES))
    if with_attack:
        fields['attack'] = ATTACK
    fields.update(extra)
    return obj(**fields)


ENEMY_FORMS_1_1 = {
    'melee_approach_v1': ENEMY, 'melee_dash_v1': ENEMY,
    'walker_patrol_v1': _archetype(('walker_patrol_v1',), robot=ROBOT, walker=WALKER),
    'brute_slam_v1': _archetype(('brute_slam_v1',), robot=ROBOT, brute=BRUTE),
    'hover_drone_v1': _archetype(('hover_drone_v1',), robot=ROBOT, hover=HOVER),
    'boss_phases_v1': _archetype(('boss_phases_v1',), with_attack=False, robot=ROBOT, boss=BOSS),
}
ENEMY_1_1 = {'oneOf': [ENEMY] + [ENEMY_FORMS_1_1[t] for t in ROBOT_TEMPLATES + BOSS_TEMPLATES]}
# Encounter 1.1.0: `boss` names the spawn whose defeat is the boss beat ('' = none); `gate` names a door of the
# encounter room that stays shut until the owning challenge completes (its own conditions must say so; '' = none).
ENCOUNTER_1_1 = obj(id=ID, room=ID, arena=obj(min=VEC, max=VEC),
    spawns=array(obj(id=ID, archetype=ID, position_m=VEC, wave=integer(0, 7)), 24, 1),
    win=enum('all_spawns_defeated'), lose=enum('player_health_zero'), double_ko=enum('failure'),
    boss=EMPTY_ID, gate=EMPTY_ID)


def optional(base, **fields):
    """Add closed optional properties without changing inherited required fields."""
    import copy
    out = copy.deepcopy(base)
    out['properties'].update(fields)
    return out


RUN = obj(clock=enum('first_control_to_last_challenge'), death_penalty_ticks=integer(0, 216000),
          max_health=integer(1, 64), reset_encounter_on_death={'const': True},
          pause_clock_in_cutscene={'const': True}, hit_invulnerability_ticks=integer(18, 600))
ENCOUNTER_1_2 = optional(ENCOUNTER, boss=EMPTY_ID, gate=EMPTY_ID,
    bosses=array(ID, 3, 0, unique=True), attack_budget=integer(1, 3),
    attack_gap_ticks=integer(0, 600), label=TEXT)


def enemy_form(value):
    """The closed archetype schema a 1.1.0 row is checked against (its fsm.template picks it)."""
    template = value.get('fsm', {}).get('template') if isinstance(value, dict) and isinstance(value.get('fsm'), dict) else None
    return ENEMY_FORMS_1_1[template] if isinstance(template, str) and template in ENEMY_FORMS_1_1 else ENEMY_1_1


def validate(value, schema, path='gameplay'):
    def bad(message):
        raise SpecError(path + ': ' + message)
    if 'oneOf' in schema:
        count = 0
        for child in schema['oneOf']:
            try:
                validate(value, child, path)
                count += 1
            except SpecError:
                pass
        if count != 1:
            bad('unknown or malformed typed value')
        return
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        bad('unexpected constant/version')
    if 'enum' in schema and not any(type(value) is type(v) and value == v for v in schema['enum']):
        bad('value outside enum')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if kind in types and type(value) is not types[kind]:
        bad('expected ' + kind)
    if kind == 'object':
        props = schema['properties']
        if set(value) - set(props) or set(schema['required']) - set(value):
            bad('missing fields {} or unknown fields {}'.format(sorted(set(props) - set(value)), sorted(set(value) - set(props))))
        for key, child in value.items():
            validate(child, props[key], path + '/' + key)
    elif kind == 'array':
        if not schema['minItems'] <= len(value) <= schema['maxItems']:
            bad('array/state bounds exceeded')
        for i, child in enumerate(value):
            validate(child, schema['items'], path + '/' + str(i))
        if schema.get('uniqueItems') and any(v in value[:i] for i, v in enumerate(value)):
            bad('duplicate value')
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 256):
            bad('string bounds exceeded')
        if 'pattern' in schema and re.fullmatch(schema['pattern'], value) is None:
            bad('invalid ID format; paths and executable references are not admitted')
    elif kind in ('integer', 'number'):
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            bad('expected finite number')
        if not schema['minimum'] <= value <= schema['maximum']:
            bad('number outside minimum/maximum bounds')
    return value
