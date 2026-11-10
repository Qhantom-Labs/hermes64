"""Exterior yards from pack data (ROOMLOOK outdoors).

Every exterior room of a compiled game becomes a kit landscape (`terrain.yard`): the playfield is the room grid,
ringed by terraces/ledges and an enclosing ridge wall with passes cut where the story's doors are, path strips from
those exits to the centre and optional ice slabs/ponds. Keys come from `packs/<pack>/view.json "yards"` (default <-
by_kit_ref in room order <- presentation room "yard"). Theme-agnostic; the kit pipeline stays the authority and
rejected candidates fall back to simpler yards, then to the legacy floor.
"""
import math

from .shells import WALL, half_span, door_offset, merged, camera_side

YARD_KEYS = ('plan', 'segments', 'floor_rings', 'terraces', 'terrace_rise', 'terrace_run', 'ridge_height', 'ridge_run',
             'jag', 'path_width', 'ground_role', 'tread_role', 'cliff_role', 'cap_role', 'path_role', 'pond_role', 'bowl', 'view_gap',
             'view_gap_width')
MAX_HALF_EXTENT = 19.6   # kit shell class: largest extent <= 40 m


def _points(room, pres):
    pts = [p.get('position') for p in room.get('props', [])]
    pts += [pres.get('props', {}).get(p['id'], {}).get('position') for p in room.get('props', [])]
    pts += [p.get('position') for p in pres.get('pieces', [])]
    return [p for p in pts if isinstance(p, list) and len(p) == 3]


def _pond_ok(pond, w, d, points, exits_xy):
    cx, cz = w / 2.0 + pond['x'] * w, d / 2.0 - pond['y'] * d   # kit +y (north) is runtime -z
    rx, ry = pond['rx'] + 0.6, pond['ry'] + 0.6
    if not (0.4 < cx - rx and cx + rx < w - 0.4 and 0.4 < cz - ry and cz + ry < d - 0.4):
        return False
    for p in list(points) + exits_xy:
        if ((float(p[0]) - cx) / rx) ** 2 + ((float(p[-1]) - cz) / ry) ** 2 <= 1.0:
            return False
    # keep ponds off the straight exit -> centre paths
    for ex, ez in exits_xy:
        for t in (0.25, 0.5, 0.75, 1.0):
            px, pz = ex + (w / 2.0 - ex) * t, ez + (d / 2.0 - ez) * t
            if ((px - cx) / rx) ** 2 + ((pz - cz) / ry) ** 2 <= 1.0:
                return False
    return True


def plan_room(room, pres, yards):
    if not pres.get('exterior') or pres.get('yard') is False:
        return None
    cfg = merged(yards, room.get('kit_refs', []))
    cfg.update({k: v for k, v in (pres.get('yard') or {}).items() if k in YARD_KEYS or k in ('ponds', 'exit_width')})
    w, d = (float(x) for x in room['grid_size'])
    if not (4.0 <= w <= 16.0 and 4.0 <= d <= 16.0):
        return None
    plan = cfg.get('plan', 'rounded_rect')
    k = int(cfg.get('segments', 28))
    exits, exits_xy = [], []
    for door in room.get('doors', []):
        wall = WALL.get(door.get('wall'))
        if wall is None:
            return None
        half = half_span(plan, w, d, k, wall)
        ew = float(cfg.get('exit_width', 2.2))
        off = door_offset(door, w, d, half)
        lim = max(0.0, (half - ew / 2.0 - 0.2) / (2.0 * half)) if half > 0 else 0.0
        off = max(-min(0.45, lim), min(min(0.45, lim), off))
        exits.append({'wall': wall, 'offset': round(off, 4), 'width': ew})
        p = float(door.get('position', 0)) + 0.5
        exits_xy.append({'n': (p, 0.0), 's': (p, d), 'e': (w, p), 'w': (0.0, p)}[wall])
    points = _points(room, pres)
    ponds = [pd for pd in cfg.get('ponds', []) if _pond_ok(pd, w, d, points, exits_xy)]
    base = {key: cfg[key] for key in YARD_KEYS if key in cfg}
    base.update(width=w, depth=d, exits=exits, ponds=ponds)
    # keep the whole landscape inside the kit's 40 m shell extent (scale ledge/ridge runs, never the playfield)
    T = int(base.get('terraces', 2))
    run, rr = float(base.get('terrace_run', 2.5)), float(base.get('ridge_run', 5.0))
    allowed = MAX_HALF_EXTENT - max(w, d) / 2.0
    total = T * run + rr
    if total > allowed:
        f = max(allowed, 1.0) / total
        base['terrace_run'] = round(max(0.8, run * f), 3)
        base['ridge_run'] = round(max(1.0, rr * f), 3)
    # lower the ridge where the fixed exterior camera looks (room.gd exterior_camera: from the authored anchor side
    # across the centre) so the distant layers and the landmark read (pack: view_gap). Runtime (x, z) -> kit (x, -z).
    if float(base.get('view_gap', 0.0)) > 0:
        dx, dz = camera_side(room, pres, w, d)
        if abs(dx) + abs(dz) > 1e-6:
            base['view_gap_azimuth'] = round(math.degrees(math.atan2(dz, -dx)) % 360.0, 2)
    cands = [base,
             dict(base, segments=min(int(base.get('segments', 28)), 20), floor_rings=min(int(base.get('floor_rings', 3)), 2)),
             dict(base, terraces=max(0, int(base.get('terraces', 2)) - 1), segments=16, ponds=[]),
             dict(base, terraces=0, ridge_height=0.0, segments=12, floor_rings=1, ponds=[], plan='rect')]
    uniq = []
    for c in cands:
        if c not in uniq:
            uniq.append(c)
    return {'room': room['id'], 'candidates': [{'params': c, 'exits': [{'index': i, 'door_id': door.get('id')} for i, door in
                                                                       enumerate(room.get('doors', []))]} for c in uniq]}


def plan_game(game, yards):
    if not yards or not yards.get('default'):
        return {}
    pres_all = game.get('metadata', {}).get('presentation', {}).get('rooms', {})
    out = {}
    for room in game.get('rooms', []):
        plan = plan_room(room, pres_all.get(room['id'], {}), yards)
        if plan:
            out[room['id']] = plan
    return out
