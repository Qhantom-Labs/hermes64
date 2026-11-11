"""Installed-layout loader for precompiled, data-only pack rooms (no tools imports).

Sources, first found wins:
  1. the games folder: <games folder>/rooms/<pack>/rooms.json   (your own room data; checked like pack data)
  2. the plugin pack:  kits/packs/<pack>/pack-rooms.json          (packs whose rooms.json holds room plans)
  3. the plugin pack:  kits/packs/<pack>/rooms.json               (castle_keep layout)
A pack whose rooms.json says {"rooms_from": "<pack>"} uses that pack's compiled rooms.
"""
import copy
import hashlib
import math
from pathlib import Path

from .safety import JSON_LIMIT, fail, inspect_path, strict_json
from .schemas import ID, validate

FORMAT = 'hermes64-pack-rooms/1'
PLANS_FORMAT = 'hermes64-room-plans/1'
USER_DIR = 'rooms'
TRI_DEFAULT, TRI_CEILING = 6000, 8000
RAIN_KEYS = {'enabled': bool, 'streaks': int, 'color': str, 'alpha': float, 'length': float, 'speed': float,
             'slant': float, 'width': float, 'seed': int}


def _read(path):
    with path.open('rb') as stream:
        raw = stream.read(JSON_LIMIT + 1)
    if len(raw) > JSON_LIMIT:
        fail('template_rooms', 'too large (over %d bytes)' % JSON_LIMIT)
    return raw, strict_json(raw)


def _finite(p):
    return isinstance(p, list) and len(p) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in p)


def check(data, pack, accept=()):
    """Raise Fault('template_rooms', <plain reason>) unless `data` is usable hermes64-pack-rooms/1 room data."""
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('pack') not in (pack,) + tuple(accept):
        fail('template_rooms', 'Pack rooms format/id mismatch; regenerate this pack room data.')
    rows = data.get('rooms')
    if not isinstance(rows, list) or not 3 <= len(rows) <= 32:
        fail('template_rooms', 'Pack rooms must contain 3–32 compiled rooms.')
    ids = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('room'), dict) or not isinstance(row.get('presentation'), dict):
            fail('template_rooms', 'Each pack room needs compiled room and presentation objects.')
        rid = row.get('id')
        validate(rid, ID)
        ids.append(rid)
        if row['room'].get('id') != rid or not row['presentation'].get('kit_shell'):
            fail('template_rooms', 'Pack rooms need matching ids and a built kit shell, not a bare grid.')
        anchors = row.get('anchors', {})
        if not isinstance(anchors, dict):
            fail('template_rooms', 'Pack room %s anchors must be an object.' % rid)
        points = [anchors.get('hero_start'), anchors.get('checkpoint'), anchors.get('interact')]
        points += [anchors[k] for k in ('captive',) if k in anchors]
        for key, minimum in (('spawns', 8), ('boss', 3)):
            values = anchors.get(key)
            if not isinstance(values, list) or len(values) < minimum:
                fail('template_rooms', 'Pack room %s needs %d %s anchors.' % (rid, minimum, key))
            points.extend(values)
        arena = anchors.get('arena') if isinstance(anchors.get('arena'), dict) else {}
        points.extend([arena.get('min'), arena.get('max')])
        if not all(_finite(p) for p in points):
            fail('template_rooms', 'Pack room anchors must be finite xyz coordinates.')
        if any(a >= b for a, b in zip(arena['min'], arena['max'])):
            fail('template_rooms', 'Pack room arena bounds must have positive volume.')
        budget = row['presentation'].get('budget', {})
        cap = budget.get('room_tris', TRI_DEFAULT) if isinstance(budget, dict) else TRI_DEFAULT
        if type(cap) is not int or not 0 < cap <= TRI_CEILING:
            fail('template_rooms', 'Pack room %s budget room_tris must be 1-%d.' % (rid, TRI_CEILING))
        if not isinstance(row.get('tri_estimate'), int) or not 0 < row['tri_estimate'] <= cap:
            fail('template_rooms', 'Pack room triangle estimate exceeds %d or is missing.' % cap)
    if len(ids) != len(dict.fromkeys(ids)):
        fail('template_rooms', 'Duplicate pack room ids.')
    weather = data.get('weather', {})
    rain = weather.get('rain', {}) if isinstance(weather, dict) else None
    if not isinstance(weather, dict) or set(weather) - {'rain'} or not isinstance(rain, dict) or any(
            k not in RAIN_KEYS or not (isinstance(v, RAIN_KEYS[k]) or (RAIN_KEYS[k] is float and type(v) is int))
            or isinstance(v, bool) != (RAIN_KEYS[k] is bool) for k, v in rain.items()):
        fail('template_rooms', 'Pack rooms weather must be {"rain": {...}} with known rain fields.')
    return data


def load(settings, pack, games_root=None):
    validate(pack, ID)
    root = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    folder = root / 'kits' / 'packs' / pack
    if games_root:
        user = Path(games_root) / USER_DIR / pack / 'rooms.json'
        inspect_path(user)
        if user.is_file():
            where = 'Room data in your games folder (%s/%s/rooms.json): ' % (USER_DIR, pack)
            try:
                raw, data = _read(user)
                data = check(data, pack)
            except Exception as exc:  # one plain line naming the file; never fall back silently to other data
                fail('template_rooms', where + ' '.join(str(exc).split())[:300] + ' Fix it, or remove the file to use '
                     'the plugin pack rooms. Nothing was created.')
            data = copy.deepcopy(data)
            data['source'] = '%s/%s/rooms.json@%s' % (USER_DIR, pack, hashlib.sha256(raw).hexdigest())
            return data
    accept = ()
    plans = folder / 'rooms.json'
    inspect_path(plans)
    if plans.is_file():
        head = _read(plans)[1]
        if isinstance(head, dict) and isinstance(head.get('rooms_from'), str) and head.get('format', PLANS_FORMAT) == PLANS_FORMAT:
            validate(head['rooms_from'], ID)
            accept, folder = (head['rooms_from'],), root / 'kits' / 'packs' / head['rooms_from']
    for path in (folder / 'pack-rooms.json', folder / 'rooms.json'):
        inspect_path(path)
        if not path.is_file():
            continue
        data = _read(path)[1]
        if isinstance(data, dict) and data.get('format') == PLANS_FORMAT:
            continue  # room plans, not compiled rooms
        return copy.deepcopy(check(data, pack, accept))
    fail('template_rooms', 'Arena games need compiled pack room data; %s has none. Choose castle_keep or '
         'neon_city_night, put hermes64-pack-rooms/1 data in your games folder at %s/%s/rooms.json, or install a pack '
         'with it. Nothing was created.' % (pack, USER_DIR, pack))


def instantiate(row, hero='hero'):
    """Preserve authored door walls/positions; the template supplies targets and gates."""
    room, presentation = copy.deepcopy(row['room']), copy.deepcopy(row['presentation'])
    room['character_ids'] = [hero]
    presentation.pop('characters', None)
    presentation['player_start'] = copy.deepcopy(row['anchors']['hero_start'])
    return room, presentation
