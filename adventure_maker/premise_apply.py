"""Apply a story file's presentation and boss fields to a generated arena_run_v1 spec (data only, deterministic).

Called by newgame.starter_spec after templates.build. What it does (docs/TEMPLATES.md, "Premise fields applied"):
- scenes: the simple cards (`opening`, `pre_finale`, `ending`) become runtime scenes (docs/SCENES.md): a held shot from
  the named room camera, actors placed on the room's anchors, `line` as the subtitle, `voice` as the voice line.
  `scenes.list` holds full runtime scenes, appended as written. Both are checked here with the plugin's scene
  validator and refused with the premise path of the bad field.
- results, weather (pack rain look, or off), npc clips (played by the room when the body has the clip), boss
  `robot` block and `speed_mps`.
- text_boxes: generated arena games show no room-description or narration boxes unless the story sets it true.
- audio: the slot names are kept in the project (audio/premise-slots.json) until the files are imported.
"""
import copy
import re

from .safety import Fault, fail

APPLIED = ('scenes', 'results', 'weather')
AUDIO_FILE = 'audio/premise-slots.json'
AUDIO_FORMAT = 'hermes64-premise-audio/1'
TRIGGERS = (('opening', {'on': 'start'}), ('pre_finale', None), ('ending', {'on': 'ending'}))


def _scenes_module():
    if '.' in (__package__ or ''):  # installed plugin: story is a sibling package (as service.py imports it)
        from ..story.presentation import scenes
    else:
        from story.presentation import scenes
    return scenes


def apply(spec, slots, rooms):
    meta = spec['metadata']
    pres = meta['presentation']
    pres['text_boxes'] = bool(slots.get('text_boxes', False))
    order = [r['id'] for r in spec['rooms']]
    anchors = {r['id']: r['anchors'] for r in rooms['rooms']}
    weather(pres, slots.get('weather', {}), order, rooms.get('weather', {}))
    npc_clips(spec, slots.get('npcs', []))
    bosses(spec, slots.get('bosses', []))
    if slots.get('results'):
        pres['results'] = results(slots['results'])
    scenes = translate(spec, slots, anchors, order)
    extra = copy.deepcopy(slots.get('scenes', {}).get('list', []))
    if scenes or extra:
        pres['scenes'] = scenes + extra
        check_scenes(spec, [s['id'] for s in scenes], len(extra))
    return spec


def weather(pres, asked, order, pack_weather):
    for rid, kind in sorted(asked.items()):
        if rid not in order:
            fail('premise_weather', 'weather names room %r, which is not in rooms.order.' % rid)
        layer = pres['rooms'][rid].setdefault('weather', {})
        if kind == 'none':
            layer['rain'] = False
        elif not (isinstance(layer.get('rain'), dict) and layer['rain'].get('enabled', True)):
            layer['rain'] = copy.deepcopy(pack_weather.get('rain') or {'enabled': True})
            layer['rain']['enabled'] = True


def npc_clips(spec, npcs):
    meta = spec['metadata']
    for npc in npcs:
        clip = npc.get('clip', 'idle')
        if clip != 'idle':
            meta['presentation']['rooms'][npc['room']]['characters'][npc['id']]['clip'] = clip
    pending = [p for p in meta.get('template_pending', []) if p != 'npcs.clip (idle fallback)']
    if pending:
        meta['template_pending'] = pending
    else:
        meta.pop('template_pending', None)


def bosses(spec, rows):
    combat = next(m for m in spec['gameplay']['modules'] if m['id'] == 'combat')
    archetypes = {a['id']: a for a in combat['entities']['archetypes']}
    for row in rows:
        archetype = archetypes[row['id']]
        archetype['robot'].update(copy.deepcopy(row.get('robot', {})))
        if 'speed_mps' in row:
            archetype['speed_mps'] = row['speed_mps']


def results(row):
    out = {'enabled': row.get('enabled', True)}
    if 'title' in row:
        limit = _scenes_module().MAX_TITLE
        if len(row['title']) > limit:
            fail('premise_results', 'results.title has %d characters; the results card fits %d.' % (len(row['title']), limit))
        out['title'] = row['title']
    return out


def translate(spec, slots, anchors, order):
    S = _scenes_module()
    hero = spec['metadata'].get('protagonist', 'hero')
    npcs = {n['id']: n for n in slots.get('npcs', [])}
    bosses = {b['id'] for b in slots.get('bosses', [])}
    finale = slots.get('finale', {}).get('room') or order[-1]
    cameras = {rid: [c.get('id') for c in row.get('cameras', [])] for rid, row in spec['metadata']['presentation']['rooms'].items()}
    out = []
    for key, trigger in TRIGGERS:
        cards = slots.get('scenes', {}).get(key) or []
        if not cards:
            continue
        rows = []
        for i, c in enumerate(cards):
            at = 'scenes.%s[%d]' % (key, i)
            rid = c['room']
            if rid not in order:
                fail('premise_scenes', '%s: room %r is not in rooms.order.' % (at, rid))
            if c['camera'] not in cameras[rid]:
                fail('premise_scenes', '%s: room %s has no camera %r (cameras: %s).' % (at, rid, c['camera'], ', '.join(cameras[rid])))
            if c['hold_ticks'] > S.MAX_HOLD_TICKS:
                fail('premise_scenes', '%s: hold_ticks %d is over %d (30 s per card).' % (at, c['hold_ticks'], S.MAX_HOLD_TICKS))
            card = {'room': rid, 'hold': c['hold_ticks'], 'shot': {'kind': 'hold', 'camera': c['camera']}}
            actors = []
            for a in c.get('actors', []):
                actors.append(actor(a, at, rid, hero, npcs, bosses, anchors, [x['at'] for x in actors]))
            if len(actors) > S.MAX_ACTORS:
                fail('premise_scenes', '%s: %d actors; a card shows at most %d.' % (at, len(actors), S.MAX_ACTORS))
            if actors:
                card.update(actors=actors, cast_only=True)
            if 'line' in c:
                line = c['line']
                if len(line['text']) > S.MAX_SUBTITLE or len(line['speaker']) > S.MAX_SPEAKER:
                    fail('premise_scenes', '%s: line must fit the subtitle strip (text %d, speaker %d characters at most).'
                         % (at, S.MAX_SUBTITLE, S.MAX_SPEAKER))
                card['subtitle'] = {'speaker': line['speaker'], 'text': line['text']}
            if 'voice' in c:
                card['voice'] = c['voice']
            rows.append(card)
        out.append({'id': key, 'trigger': dict(trigger or {'on': 'enter', 'room': finale}), 'cards': rows})
    return out


def actor(a, at, rid, hero, npcs, bosses, anchors, taken):
    """Runtime actor on the room's anchors: the hero at hero_start, an npc on its own anchor in its room (else at
    interact). Actors sharing a spot step 1 m apart along x."""
    room = anchors[rid]
    if a['id'] == hero:
        cid, point = 'protagonist', room['hero_start']
    elif a['id'] in npcs:
        npc = npcs[a['id']]
        cid = a['id']
        point = room.get(npc['anchor'], room['interact']) if npc['room'] == rid else room['interact']
    elif a['id'] in bosses:
        fail('premise_scenes', '%s: %s is a boss; scene actors are the hero or an npc (boss scene cast: DEMO-STATUS G10).'
             % (at, a['id']))
    else:
        fail('premise_scenes', '%s: actor %r is not the hero or an npc of this story.' % (at, a['id']))
    spot = [float(point[0]), float(point[2])]
    while spot in taken:
        spot = [spot[0] + 1.0, spot[1]]
    return {'character': cid, 'at': spot, 'yaw': 180, 'clip': a['clip']}


def check_scenes(spec, translated, extra):
    """The plugin's own closed scene check, with the failing path mapped back to the story file."""
    S = _scenes_module()
    try:
        S.validate_spec(spec)
    except ValueError as exc:
        text, where = ' '.join(str(exc).split()), 'scenes'
        found = re.match(r'metadata/presentation/scenes/(\d+)(/[^:]*)?: (.*)', text)
        if found:
            index = int(found.group(1))
            where = ('scenes.%s' % translated[index]) if index < len(translated) else 'scenes.list[%d]' % (index - len(translated))
            text = ((found.group(2) or '').lstrip('/') + ': ' if found.group(2) else '') + found.group(3)
        raise Fault('premise_scenes', '%s: %s' % (where, text[:300])) from exc


def audio_doc(record, audio):
    return {'format': AUDIO_FORMAT, 'story': record['id'] + '@' + record['sha256'] if record else '', 'slots': copy.deepcopy(audio)}


def assets_named(slots):
    music = slots.get('music', {})
    names = [v for k, v in music.items() if isinstance(v, str)]
    names += [v for k in ('scenes', 'waves', 'events') for v in music.get(k, {}).values()]
    names += [row['asset'] if isinstance(row, dict) else row for row in slots.get('voice', {}).values()]
    names += list(slots.get('cues', {}).values())
    return sorted(dict.fromkeys(names))


def assign_imported(project, manifest, slots_file='audio/slots.json'):
    """After an import: assign the story's audio block once every asset it names is imported (never over an existing
    audio/slots.json). Returns a short status for the import result, or {} when the project has no story audio."""
    if project.path(slots_file).is_file() or not project.path(AUDIO_FILE).is_file():
        return {}
    doc = project.read_json(AUDIO_FILE)
    slots = doc.get('slots', {}) if isinstance(doc, dict) else {}
    missing = [n for n in assets_named(slots) if n not in manifest['assets']]
    if missing:
        return {'story_audio': 'waiting for ' + ', '.join(missing[:8]) + (' ...' if len(missing) > 8 else '')}
    from . import audio_import as ai
    try:
        checked = ai.validate_slots(slots, manifest['assets'])
    except Fault as exc:
        return {'story_audio': 'not assigned: ' + ' '.join(str(exc).split())[:200]}
    project.write_json(slots_file, checked)
    return {'story_audio': 'assigned from the story file', 'slots': slots_file}
