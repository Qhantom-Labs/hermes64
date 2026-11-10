"""Installed-layout loader for precompiled, data-only pack rooms (no tools imports)."""
import copy
import math
from pathlib import Path

from .safety import JSON_LIMIT, fail, inspect_path, strict_json
from .schemas import ID, validate

FORMAT = 'hermes64-pack-rooms/1'


def load(settings, pack):
    validate(pack, ID)
    root = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    path = root / 'kits' / 'packs' / pack / 'rooms.json'
    inspect_path(path)
    if not path.is_file():
        fail('template_rooms', 'Arena games need compiled pack room data; %s has none. Choose castle_keep '
             'or install a pack with hermes64-pack-rooms/1 rooms.json. Nothing was created.' % pack)
    with path.open('rb') as stream:
        data = strict_json(stream.read(JSON_LIMIT + 1))
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('pack') != pack:
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
        points = [anchors.get('hero_start'), anchors.get('checkpoint'), anchors.get('interact')]
        for key, minimum in (('spawns', 8), ('boss', 3)):
            values = anchors.get(key)
            if not isinstance(values, list) or len(values) < minimum:
                fail('template_rooms', 'Pack room %s needs %d %s anchors.' % (rid, minimum, key))
            points.extend(values)
        arena = anchors.get('arena', {})
        points.extend([arena.get('min'), arena.get('max')])
        if not all(isinstance(p, list) and len(p) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in p)
                   for p in points):
            fail('template_rooms', 'Pack room anchors must be finite xyz coordinates.')
        if any(a >= b for a, b in zip(arena['min'], arena['max'])):
            fail('template_rooms', 'Pack room arena bounds must have positive volume.')
        if not isinstance(row.get('tri_estimate'), int) or not 0 < row['tri_estimate'] <= 6000:
            fail('template_rooms', 'Pack room triangle estimate exceeds 6000 or is missing.')
    if len(ids) != len(dict.fromkeys(ids)):
        fail('template_rooms', 'Duplicate pack room ids.')
    return copy.deepcopy(data)


def instantiate(row, hero='hero'):
    """Preserve authored door walls/positions; the template supplies targets and gates."""
    room, presentation = copy.deepcopy(row['room']), copy.deepcopy(row['presentation'])
    room['character_ids'] = [hero]
    presentation.pop('characters', None)
    presentation['player_start'] = copy.deepcopy(row['anchors']['hero_start'])
    return room, presentation
