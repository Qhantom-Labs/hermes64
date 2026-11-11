"""Closed validation for `metadata.presentation.scenes` and `metadata.presentation.results`.

Scene cards and results are presentation data (docs/SCENES.md). They never change the
story, saves or movies, but bad data could leave a player stuck, so every card has a
bounded hold, every reference resolves, and unknown fields are refused. Limits match
runtime/godot/view/scene_cards.gd.

This module lives outside the STORY core files on purpose: story/puzzle pins a digest of
story/*.py, so presentation checks do not change the core implementation hash. The plugin
compile step (adventure_maker/service.py) calls validate_spec before compiling.
"""
import math
import re

from ..errors import SpecError

MAX_SCENES = 32
MAX_CARDS = 16
MAX_HOLD_TICKS = 1800          # 30 s per card
MAX_SCENE_TICKS = 5400         # 90 s per scene
MAX_ACTORS = 6
MAX_SUBTITLE = 80              # two lines of 40 characters in the pack pixel font
MAX_SPEAKER = 24
MAX_TITLE = 40
SHOTS = ('cut', 'hold', 'push', 'pan', 'orbit', 'track')
TRIGGERS = ('start', 'door', 'enter', 'event', 'ending')
CUTS = ('cut', 'fade', 'iris')
EVENTS = ('challenge_started', 'encounter_cleared', 'course_completed', 'challenge_failed',
          'checkpoint_ready', 'region_unlocked', 'boss_phase', 'boss_defeated')
SLOT = re.compile(r'^[a-z0-9][a-z0-9_.:-]{0,63}$')
IDENT = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
HEX = re.compile(r'^#?[0-9a-fA-F]{6}$')
LABEL_KEYS = ('time', 'deaths', 'penalty', 'best', 'code', 'again', 'save', 'saved')

SCENE_FIELDS = {'id', 'trigger', 'cards', 'music', 'transition_in', 'transition_out', 'letterbox', 'once', 'room'}
CARD_FIELDS = {'room', 'shot', 'actors', 'subtitle', 'voice', 'title', 'hold', 'cut', 'wait', 'reduced', 'cast_only'}
ACTOR_FIELDS = {'character', 'clip', 'at', 'to', 'yaw', 'moving_clip'}
SHOT_FIELDS = {
    'cut': {'kind', 'from', 'look', 'fov', 'camera'},
    'hold': {'kind', 'from', 'look', 'fov', 'camera'},
    'push': {'kind', 'from', 'look', 'fov', 'camera', 'to', 'amount'},
    'pan': {'kind', 'from', 'look', 'fov', 'camera', 'look_to'},
    'orbit': {'kind', 'look', 'fov', 'radius', 'start_deg', 'sweep_deg', 'height'},
    'track': {'kind', 'fov', 'follow', 'offset', 'look_height'},
}
RESULT_FIELDS = {'enabled', 'title', 'music', 'labels', 'on'}


def fail(path, text):
    raise SpecError('{}: {}'.format(path, text))


def closed(value, allowed, path, required=()):
    if not isinstance(value, dict):
        fail(path, 'expected object')
    extra = sorted(set(value) - set(allowed))
    missing = sorted(set(required) - set(value))
    if extra or missing:
        fail(path, 'missing fields {}; unknown fields {}'.format(missing, extra))


def number(v, path, lo=-1e6, hi=1e6):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        fail(path, 'expected a finite number in [{}, {}]'.format(lo, hi))


def integer(v, path, lo, hi):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        fail(path, 'expected an integer in [{}, {}]'.format(lo, hi))


def text(v, path, limit, empty=False):
    if not isinstance(v, str) or (not empty and not v.strip()) or len(v) > limit or any(c in v for c in '\r\t'):
        fail(path, 'expected text of 1..{} characters'.format(limit))


def vec(v, n, path, bounds):
    if not isinstance(v, list) or len(v) != n:
        fail(path, 'expected {} numbers'.format(n))
    for i, x in enumerate(v):
        number(x, '{}/{}'.format(path, i), *bounds)


def slot(v, path):
    if not isinstance(v, str) or not SLOT.match(v):
        fail(path, 'expected an audio slot or line name (names only, no paths)')


def room_bounds(room):
    w, d = room.get('grid_size', [64, 64])
    span = max(w, d) + 40
    return (-40.0, float(span))


def validate_shot(shot, path, bounds, n_actors, cameras):
    if not isinstance(shot, dict) or shot.get('kind') not in SHOTS:
        fail(path + '/kind', 'expected one of {}'.format(list(SHOTS)))
    closed(shot, SHOT_FIELDS[shot['kind']], path)
    for key in ('from', 'look', 'to', 'look_to', 'offset'):
        if key in shot:
            vec(shot[key], 3, path + '/' + key, bounds if key != 'offset' else (-40.0, 40.0))
    if 'camera' in shot:
        if shot['camera'] not in cameras:
            fail(path + '/camera', 'unknown authored camera {!r}'.format(shot['camera']))
    elif shot['kind'] in ('cut', 'hold', 'push', 'pan') and not {'from', 'look'} <= set(shot):
        fail(path, 'needs from and look, or an authored camera')
    if shot['kind'] == 'orbit' and 'look' not in shot:
        fail(path, 'orbit needs look (the centre)')
    if 'fov' in shot:
        number(shot['fov'], path + '/fov', 20, 100)
    if 'amount' in shot:
        number(shot['amount'], path + '/amount', -20, 20)
    if 'radius' in shot:
        number(shot['radius'], path + '/radius', 0.3, 60)
    for key in ('start_deg', 'sweep_deg'):
        if key in shot:
            number(shot[key], path + '/' + key, -720, 720)
    for key in ('height', 'look_height'):
        if key in shot:
            number(shot[key], path + '/' + key, -10, 60)
    if shot['kind'] == 'track':
        integer(shot.get('follow', 0), path + '/follow', 0, max(0, n_actors - 1))
        if n_actors == 0:
            fail(path, 'track needs an actor to follow')


def validate_scenes(spec, rooms, characters, endings, challenges=()):
    """Raise SpecError on the first problem. rooms: id -> room dict; others: id collections."""
    pres = spec.get('metadata', {}).get('presentation', {})
    if not isinstance(pres, dict):
        return
    if 'results' in pres:
        res = pres['results']
        closed(res, RESULT_FIELDS, 'metadata/presentation/results')
        if 'enabled' in res and not isinstance(res['enabled'], bool):
            fail('metadata/presentation/results/enabled', 'expected boolean')
        if 'title' in res:
            text(res['title'], 'metadata/presentation/results/title', MAX_TITLE)
        if 'music' in res:
            slot(res['music'], 'metadata/presentation/results/music')
        if 'on' in res and res['on'] not in ('ending', 'run_finished'):
            fail('metadata/presentation/results/on', 'expected ending or run_finished')
        if 'labels' in res:
            closed(res['labels'], LABEL_KEYS, 'metadata/presentation/results/labels')
            for k, v in res['labels'].items():
                text(v, 'metadata/presentation/results/labels/' + k, 16)
    if 'scenes' not in pres:
        return
    scenes = pres['scenes']
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        fail('metadata/presentation/scenes', 'expected 1..{} scenes'.format(MAX_SCENES))
    seen = set()
    doors = {(r_id, d['to_room']) for r_id, r in rooms.items() for d in r.get('doors', [])}
    for si, scene in enumerate(scenes):
        sp = 'metadata/presentation/scenes/{}'.format(si)
        closed(scene, SCENE_FIELDS, sp, ('id', 'trigger', 'cards'))
        if not isinstance(scene['id'], str) or not IDENT.match(scene['id']) or scene['id'] in seen:
            fail(sp + '/id', 'expected a unique lowercase id')
        seen.add(scene['id'])
        trig = scene['trigger']
        if not isinstance(trig, dict) or trig.get('on') not in TRIGGERS:
            fail(sp + '/trigger/on', 'expected one of {}'.format(list(TRIGGERS)))
        on = trig['on']
        allowed = {'start': {'on'}, 'door': {'on', 'from', 'to'}, 'enter': {'on', 'room'},
                   'event': {'on', 'kind', 'challenge'}, 'ending': {'on', 'ending'}}[on]
        required = {'start': (), 'door': ('from', 'to'), 'enter': ('room',), 'event': ('kind',), 'ending': ()}[on]
        closed(trig, allowed, sp + '/trigger', required)
        if on == 'door':
            if (trig['from'], trig['to']) not in doors:
                fail(sp + '/trigger', 'no door leads from {!r} to {!r}'.format(trig['from'], trig['to']))
        if on == 'enter' and trig['room'] not in rooms:
            fail(sp + '/trigger/room', 'missing room {!r}'.format(trig['room']))
        if on == 'event':
            if trig['kind'] not in EVENTS:
                fail(sp + '/trigger/kind', 'expected one of {}'.format(list(EVENTS)))
            if 'challenge' in trig and trig['challenge'] not in challenges:
                fail(sp + '/trigger/challenge', 'missing challenge {!r}'.format(trig['challenge']))
        if on == 'ending' and 'ending' in trig and trig['ending'] not in endings:
            fail(sp + '/trigger/ending', 'missing ending {!r}'.format(trig['ending']))
        for key in ('transition_in', 'transition_out'):
            if key in scene and scene[key] not in CUTS:
                fail(sp + '/' + key, 'expected one of {}'.format(list(CUTS)))
        for key in ('letterbox', 'once'):
            if key in scene and not isinstance(scene[key], bool):
                fail(sp + '/' + key, 'expected boolean')
        if 'music' in scene:
            slot(scene['music'], sp + '/music')
        if 'room' in scene and scene['room'] not in rooms:
            fail(sp + '/room', 'missing room {!r}'.format(scene['room']))
        cards = scene['cards']
        if not isinstance(cards, list) or not 1 <= len(cards) <= MAX_CARDS:
            fail(sp + '/cards', 'expected 1..{} cards'.format(MAX_CARDS))
        total = 0
        for ci, card in enumerate(cards):
            cp = '{}/cards/{}'.format(sp, ci)
            closed(card, CARD_FIELDS, cp, ('hold', 'shot'))
            room_id = card.get('room', scene.get('room', trig.get('to', trig.get('room'))))
            if room_id is None:
                fail(cp + '/room', 'needs a room (or a scene room)')
            if room_id not in rooms:
                fail(cp + '/room', 'missing room {!r}'.format(room_id))
            room = rooms[room_id]
            cams = {c.get('id') for c in spec.get('metadata', {}).get('presentation', {}).get('rooms', {}).get(room_id, {}).get('cameras', [])}
            integer(card['hold'], cp + '/hold', 1, MAX_HOLD_TICKS)
            total += card['hold']
            bounds = room_bounds(room)
            actors = card.get('actors', [])
            if not isinstance(actors, list) or len(actors) > MAX_ACTORS:
                fail(cp + '/actors', 'expected at most {} actors'.format(MAX_ACTORS))
            for ai, actor in enumerate(actors):
                ap = '{}/actors/{}'.format(cp, ai)
                closed(actor, ACTOR_FIELDS, ap, ('character', 'at'))
                if actor['character'] != 'protagonist' and actor['character'] not in characters:
                    fail(ap + '/character', 'missing character {!r}'.format(actor['character']))
                vec(actor['at'], 2, ap + '/at', bounds)
                if 'to' in actor:
                    vec(actor['to'], 2, ap + '/to', bounds)
                if 'yaw' in actor:
                    number(actor['yaw'], ap + '/yaw', -720, 720)
                for key in ('clip', 'moving_clip'):
                    if key in actor and (not isinstance(actor[key], str) or not IDENT.match(actor[key])):
                        fail(ap + '/' + key, 'expected a clip name')
            validate_shot(card['shot'], cp + '/shot', bounds, len(actors), cams)
            if 'reduced' in card:
                closed(card['reduced'], {'shot'}, cp + '/reduced', ('shot',))
                validate_shot(card['reduced']['shot'], cp + '/reduced/shot', bounds, len(actors), cams)
            if 'subtitle' in card:
                closed(card['subtitle'], {'speaker', 'text', 'color'}, cp + '/subtitle', ('text',))
                text(card['subtitle']['text'], cp + '/subtitle/text', MAX_SUBTITLE)
                if 'speaker' in card['subtitle']:
                    text(card['subtitle']['speaker'], cp + '/subtitle/speaker', MAX_SPEAKER)
                if 'color' in card['subtitle'] and (not isinstance(card['subtitle']['color'], str) or not HEX.match(card['subtitle']['color'])):
                    fail(cp + '/subtitle/color', 'expected #rrggbb')
            if 'title' in card:
                text(card['title'], cp + '/title', MAX_TITLE)
            if 'voice' in card:
                slot(card['voice'], cp + '/voice')
            if 'cut' in card and card['cut'] not in CUTS:
                fail(cp + '/cut', 'expected one of {}'.format(list(CUTS)))
            if 'cast_only' in card and not isinstance(card['cast_only'], bool):
                fail(cp + '/cast_only', 'expected boolean')
            if 'wait' in card:
                if card['wait'] != 'key' or on != 'start':
                    fail(cp + '/wait', 'only a start-trigger title card may wait for a key')
        if total > MAX_SCENE_TICKS:
            fail(sp, 'scene holds {} ticks; the limit is {}'.format(total, MAX_SCENE_TICKS))


def actor_ids(doc):
    """Ids a card may cast besides story characters (lane CHARBIND): combat archetype ids (shown with the character body
    bound to them) and metadata.presentation.cast keys (project cast rows bound by id). Presentation only."""
    out = set()
    gameplay = doc.get('gameplay') if isinstance(doc, dict) else None
    for module in (gameplay.get('modules', []) if isinstance(gameplay, dict) else []):
        ents = module.get('entities') if isinstance(module, dict) else None
        for row in (ents.get('archetypes') or []) if isinstance(ents, dict) else []:
            if isinstance(row, dict) and isinstance(row.get('id'), str):
                out.add(row['id'])
    meta = doc.get('metadata') if isinstance(doc, dict) else None
    cast = (meta.get('presentation') or {}).get('cast') if isinstance(meta, dict) else None
    if isinstance(cast, dict):
        out.update(k for k in cast if isinstance(k, str))
    return out


def validate_spec(spec):
    """Check a source spec (story contract 1.x). No-op when it has no scenes/results."""
    pres = spec.get('metadata', {}).get('presentation') if isinstance(spec, dict) else None
    if not isinstance(pres, dict) or not ('scenes' in pres or 'results' in pres):
        return
    rooms = {r['id']: r for r in spec.get('rooms', []) if isinstance(r, dict) and 'id' in r}
    chars = {c['id'] for c in spec.get('characters', []) if isinstance(c, dict) and 'id' in c}
    ends = {e['id'] for e in spec.get('endings', []) if isinstance(e, dict) and 'id' in e}
    challenges = set()
    from ..modules import enabled
    if enabled(spec):
        from ..modules.registry import entities
        challenges = {c['id'] for c in entities(spec, 'challenge', 'challenges')}
    validate_scenes(spec, rooms, chars | actor_ids(spec), ends, challenges)


def validate_game(game):
    """Same checks against a compiled game.json (runtime staging and tools)."""
    rooms = {r['id']: r for r in game['rooms']}
    chars = {c['id'] for c in game.get('characters', [])}
    ends = {e['id'] for e in game.get('endings', [])}
    challenges = set()
    gameplay = game.get('gameplay', {})
    for module in (gameplay.get('modules', []) if isinstance(gameplay, dict) else []):
        for c in (module.get('challenges', []) if isinstance(module, dict) else []):
            if isinstance(c, dict) and 'id' in c:
                challenges.add(c['id'])
    validate_scenes(game, rooms, chars | actor_ids(game), ends, challenges)
