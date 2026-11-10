"""Closed runtime-observation contract, NOT a physical test or mutation API.

Only the later trusted host may supply observations. Shape/consistency checks do
not authenticate a sender, validate collision history, or grant rewards.
"""
from story.errors import StateError
from . import schema as S
from .registry import entity_map, index
from .course import minimum_ticks

HASH = {'type': 'string', 'minLength': 64, 'maxLength': 64, 'pattern': '^[0-9a-f]{64}$'}


def event_schema():
    kinds = {
        'combat_completed': S.obj(defeated_spawns=S.array(S.ID, 24, 1, True), player_alive={'const': True}),
        'combat_failed': S.obj(reason=S.enum('player_defeated', 'aborted')),
        'course_checkpoint': S.obj(checkpoint=S.ID, index=S.integer(0, 31), elapsed_ticks=S.integer(0, 216000)),
        'course_completed': S.obj(checkpoints=S.array(S.ID, 32, 1, True), elapsed_ticks=S.integer(1, 216000)),
        'course_failed': S.obj(reason=S.enum('deadline', 'aborted')),
    }
    return {'oneOf': [S.obj(api_version={'const': '1.0.0'}, build_hash=HASH, challenge=S.ID,
                           attempt=S.integer(1, 2147483647), sequence=S.integer(1, 2147483647),
                           physics_tick=S.integer(0, 2147483647), kind={'const': kind}, payload=payload)
                      for kind, payload in kinds.items()]}


def validate_event(game, event, active, attempt, last_sequence):
    """Validate one fresh observation against host-owned context, without mutation."""
    S.validate(event, event_schema(), 'runtime observation (including player_alive, sequence and payload)')
    if event['build_hash'] != game['game_hash']:
        raise StateError('observation build hash mismatch')
    if event['challenge'] != active or active not in entity_map(game, 'challenge', 'challenges'):
        raise StateError('observation challenge is not the active challenge')
    if event['attempt'] != attempt:
        raise StateError('observation attempt mismatch')
    if event['sequence'] != last_sequence + 1:
        raise StateError('observation sequence gap or duplicate; no transition permitted')
    challenge = entity_map(game, 'challenge', 'challenges')[active]
    if not event['kind'].startswith(challenge['kind'] + '_'):
        raise StateError('observation kind does not match active challenge')
    payload = event['payload']
    if event['kind'] == 'combat_completed':
        encounter = entity_map(game, 'combat', 'encounters')[challenge['subject']]
        if sorted(payload['defeated_spawns']) != sorted(s['id'] for s in encounter['spawns']):
            raise StateError('combat completion requires every declared spawn in every wave')
    if event['kind'].startswith('course_'):
        track = entity_map(game, 'course', 'tracks')[challenge['subject']]
        checkpoints = [c['id'] for c in track['checkpoints']]
        if event['kind'] == 'course_completed':
            if payload['checkpoints'] != checkpoints:
                raise StateError('course completion requires ordered checkpoints, without omission')
            if payload['elapsed_ticks'] > track['time_limit_ticks']:
                raise StateError('course completion exceeds deadline')
            if payload['elapsed_ticks'] < minimum_ticks(game, track):
                raise StateError('course observation violates geometric minimum duration')
        if event['kind'] == 'course_checkpoint':
            if payload['index'] >= len(checkpoints) or checkpoints[payload['index']] != payload['checkpoint']:
                raise StateError('course checkpoint/index mismatch')
            if payload['elapsed_ticks'] > track['time_limit_ticks']:
                raise StateError('course checkpoint exceeds deadline')
    return event
