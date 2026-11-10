"""Room shells from pack data (ROOMLOOK).

Every interior room of a compiled game becomes a real enclosed kit shell (`arch.room_shell`): plan, ceiling,
coves and lighting rings come from pack data (`packs/<pack>/view.json` "shells"), door openings are cut where
the story's doors are, and window openings are sized to the pack's own window modules so the runtime can drop
the bound door/window kit pieces exactly into the holes. Theme-agnostic: no colours or styles live here.

Pure data planning (no Blender): `plan_game` returns build requests + the per-room placement plan the runtime
reads. Feasibility mirrors the kit rules conservatively; the kit pipeline stays the authority (rejected or
over-budget shells fall back to simpler candidates, then to the legacy cutaway, never to a failed build).
"""
import math

WALL = {'north': 'n', 'south': 's', 'east': 'e', 'west': 'w'}
DOOR_OPENING = {'hatch': 'oval', 'oval': 'oval', 'rect': 'rect', 'arch': 'arch', 'round_top': 'arch', 'gothic': 'gothic'}
SHELL_KEYS = ('plan', 'height', 'cove', 'ceiling', 'ceiling_rise', 'wall_segments', 'floor_rings', 'ring_bias', 'cap_center', 'ceiling_panel',
              'trim', 'floor_role', 'wall_role', 'ceiling_role')
LIMITS = {'width': (2.5, 16.0), 'depth': (2.5, 16.0)}
OFFSET_SCHEMES = ((0.0, -0.22, 0.22, -0.38, 0.38), (0.06, -0.3, 0.3, -0.14, 0.14), (0.12, -0.36, 0.36))


def merged(shells, kit_refs):
    cfg = dict(shells.get('default', {}))
    for ref in kit_refs:
        cfg.update(shells.get('by_kit_ref', {}).get(ref, {}))
    return cfg


def module_params(manifest, bindings, ref):
    """Params of the library build a binding ref points at (door/window modules), or None."""
    row = bindings.get('assets', {}).get(ref) if ref else None
    if not isinstance(row, dict):
        return None
    glb = str(row.get('glb', ''))
    for kit in manifest.get('kits', []):
        for b in kit.get('builds', []):
            if 'kits/' + b.get('glb', '') == glb:
                return {'kit_id': kit['id'], **b.get('params', {})}
    return None


def corner(plan, w, d):
    return 0.3 * min(w, d) * 0.5 if plan == 'rounded_rect' else 0.0


def perimeter(plan, w, d, k):
    if plan == 'round':
        w = d = min(w, d)
    if plan in ('round', 'oval'):
        a, b = w / 2.0, d / 2.0
        # polygon with k vertices on the ellipse (the kit builds exactly this outline)
        pts = [(a * math.cos(2 * math.pi * i / k), b * math.sin(2 * math.pi * i / k)) for i in range(k)]
        return sum(math.dist(pts[i], pts[(i + 1) % k]) for i in range(k))
    c = corner(plan, w, d)
    return 2 * (w + d) - 8 * c + 2 * math.pi * c


def half_span(plan, w, d, k, wall):
    if plan in ('rect', 'rounded_rect'):
        side = w if wall in ('n', 's') else d
        return (side - 2 * corner(plan, w, d)) / 2.0
    return perimeter(plan, w, d, k) / 8.0


def door_offset(door, w, d, half):
    """Fraction along the kit wall (CCW plan path) for a story door at grid position `position`."""
    p = float(door.get('position', 0)) + 0.5
    wall = WALL[door['wall']]
    if wall == 'n':
        along = -(p - w / 2.0)
    elif wall == 's':
        along = p - w / 2.0
    elif wall == 'e':
        along = -(p - d / 2.0)
    else:
        along = p - d / 2.0
    return along / (2.0 * half) if half > 0 else 0.0


def inside(plan, w, d, x, z, margin):
    """Grid point (x, z) inside the plan outline (centre w/2, d/2) with a margin in metres."""
    u, v = x - w / 2.0, z - d / 2.0
    if plan in ('rect', 'rounded_rect'):
        return abs(u) <= w / 2.0 - margin and abs(v) <= d / 2.0 - margin
    if plan == 'round':
        r = min(w, d) / 2.0 - margin
        return u * u + v * v <= r * r
    a, b = w / 2.0 - margin, d / 2.0 - margin
    return a > 0 and b > 0 and (u / a) ** 2 + (v / b) ** 2 <= 1.0


def camera_side(room, pres, w, d):
    cams = pres.get('cameras') or room.get('cameras') or []
    p = cams[0]['position'] if cams else [w * 1.1, w * 0.7, d * 1.3]
    return float(p[0]) - w / 2.0, float(p[2]) - d / 2.0


def window_walls(dx, dz):
    far_z = 'n' if dz >= 0 else 's'
    far_x = 'w' if dx >= 0 else 'e'
    near_z = {'n': 's', 's': 'n'}[far_z]
    near_x = {'w': 'e', 'e': 'w'}[far_x]
    return [far_z, far_x, near_x, near_z] if abs(dz) >= abs(dx) else [far_x, far_z, near_z, near_x]


def opening_fits(op, plan, w, d, k, height, cove, placed):
    half = half_span(plan, w, d, k, op['wall'])
    ow = op['width'] if op['shape'] != 'round' else min(op['width'], op['height'])
    oh = op['height'] if op['shape'] != 'round' else ow
    margin = 0.05 if plan in ('rect', 'rounded_rect') else 0.15
    if abs(op['offset'] * 2 * half) + ow / 2.0 > half - 0.05 - margin:
        return False
    zb, zt = cove, height - cove
    sill = (zb + 0.08 if op['shape'] in ('oval', 'round') else zb) if op['kind'] == 'door' else max(op['sill'], zb + 0.05)
    if sill + oh > zt - 0.05:
        return False
    s = op['offset'] * 2 * half
    for q in placed:
        if q['wall'] != op['wall']:
            continue
        qw = q['width'] if q['shape'] != 'round' else min(q['width'], q['height'])
        if abs(q['offset'] * 2 * half - s) < (ow + qw) / 2.0 + 0.1 + margin:
            return False
    return True


def candidates(cfg):
    """Preferred shell, then progressively safer variants (same openings)."""
    first = {k: cfg[k] for k in SHELL_KEYS if k in cfg}
    out = [first]
    out.append(dict(first, wall_segments=min(int(first.get('wall_segments', 24)), 20), floor_rings=min(int(first.get('floor_rings', 0)), 2)))
    out.append(dict(first, plan='rounded_rect' if first.get('plan') in ('round', 'oval') else first.get('plan', 'rect'),
                    ceiling='flat' if first.get('ceiling') == 'dome' else first.get('ceiling', 'flat'), wall_segments=16, floor_rings=1))
    out.append(dict(first, plan='rect', ceiling='flat', cove=0.0, wall_segments=12, floor_rings=0, ceiling_panel=0.0))
    seen, uniq = set(), []
    for c in out:
        key = tuple(sorted(c.items()))
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def plan_room(room, pres, shells, door_mod, window_mods):
    """Shell candidates (params lists) + runtime plan for one room, or None when the room keeps the legacy look."""
    if pres.get('exterior') or pres.get('shell') is False:
        return None
    cfg = merged(shells, room.get('kit_refs', []))
    cfg.update({k: v for k, v in (pres.get('shell') or {}).items() if k in SHELL_KEYS or k in ('window', 'windows', 'door')})
    gw, gd = room['grid_size']
    w = max(LIMITS['width'][0], min(LIMITS['width'][1], float(gw)))
    d = max(LIMITS['depth'][0], min(LIMITS['depth'][1], float(gd)))
    if (w, d) != (float(gw), float(gd)):
        return None  # outside the kit's room range: keep the legacy room rather than distort the grid
    door_mod = door_mod or {}
    dshape = DOOR_OPENING.get(str(door_mod.get('shape', 'rect')), 'rect')
    dw = float(door_mod.get('width', 1.0))
    dh = max(float(door_mod.get('height', 2.1)), dw) if door_mod.get('shape') == 'hatch' else float(door_mod.get('height', 2.1))
    threshold = float(door_mod.get('frame_width', 0.1)) if dshape in ('oval', 'round') else 0.0
    # Every story position must stay inside the plan; otherwise use the safer plan up front.
    points = [p.get('position', [0, 0, 0]) for p in room.get('props', [])]
    points += [(pres.get('props', {}).get(p['id'], {}).get('position')) for p in room.get('props', [])]
    points += [p.get('position') for p in pres.get('pieces', [])]
    # Only positions inside the grid matter (pieces outside it, e.g. a tree behind a window, are intentional).
    points = [p for p in points if isinstance(p, list) and len(p) == 3 and 0.0 <= float(p[0]) <= w and 0.0 <= float(p[2]) <= d]
    dx, dz = camera_side(room, pres, w, d)
    results = []
    for cand, scheme in [(c, sc) for c in candidates(cfg) for sc in OFFSET_SCHEMES]:
        plan = cand.get('plan', 'rect')
        if plan in ('round', 'oval') and not all(inside(plan, w, d, float(p[0]), float(p[2]), 0.45) for p in points):
            continue
        if plan == 'round' and abs(w - d) > 0.01:
            continue
        k = int(cand.get('wall_segments', 24))
        height = float(cand.get('height', 3.0))
        cove = float(cand.get('cove', 0.0))
        openings, rows = [], []
        ok = True
        for door in room.get('doors', []):
            wall = WALL.get(door.get('wall'))
            if wall is None:
                ok = False
                break
            half = half_span(plan, w, d, k, wall)
            want = door_offset(door, w, d, half)
            op = None
            for off in [want] + [want * f for f in (0.75, 0.5, 0.25, 0.0)]:
                trial = {'wall': wall, 'offset': round(max(-0.45, min(0.45, off)), 4), 'width': dw, 'height': dh, 'sill': 0.0,
                         'kind': 'door', 'shape': dshape}
                if opening_fits(trial, plan, w, d, k, height, cove, openings):
                    op = trial
                    break
            if op is None:
                ok = False
                break
            rows.append({'index': len(openings), 'kind': 'door', 'ref': cfg.get('door'), 'door_id': door.get('id'), 'threshold': threshold})
            openings.append(op)
        if not ok:
            continue
        win_ref = cfg.get('window')
        wm = window_mods.get(win_ref) or {}
        if wm:
            shape = str(wm.get('shape', 'rect'))
            ww, wh = float(wm.get('width', 1.2)), float(wm.get('height', 1.0))
            if shape == 'round':
                ww = wh = min(ww, wh)
            walls = window_walls(dx, dz)
            for i in range(int(cfg.get('windows', 0))):
                placed = None
                for wall in walls[i % 2:] + walls[:i % 2]:  # alternate the two far walls
                    for off in scheme:
                        trial = {'wall': wall, 'offset': off, 'width': ww, 'height': wh, 'sill': float(wm.get('sill', 0.9)),
                                 'kind': 'window', 'shape': shape}
                        if opening_fits(trial, plan, w, d, k, height, cove, openings):
                            placed = trial
                            break
                    if placed:
                        break
                if placed is None:
                    break
                rows.append({'index': len(openings), 'kind': 'window', 'ref': win_ref})
                openings.append(placed)
        if len(openings) > 8:
            continue
        params = dict(cand, width=w, depth=d, openings=openings)
        if any(r['params'] == params for r in results):
            continue
        results.append({'params': params, 'openings': rows})
    if not results:
        return None
    return {'room': room['id'], 'candidates': results}


def plan_game(game, shells, manifest, bindings):
    """{room_id: plan} for every interior room that gets a shell (pack data permitting)."""
    if not shells or not shells.get('default'):
        return {}
    pres_all = game.get('metadata', {}).get('presentation', {}).get('rooms', {})
    cfg_door = shells['default'].get('door')
    door_mod = module_params(manifest, bindings, cfg_door)
    out = {}
    for room in game.get('rooms', []):
        cfg = merged(shells, room.get('kit_refs', []))
        refs = {cfg.get('window')} | {s.get('window') for s in shells.get('by_kit_ref', {}).values()}
        window_mods = {r: module_params(manifest, bindings, r) for r in refs if r}
        dm = module_params(manifest, bindings, cfg.get('door', cfg_door)) or door_mod
        plan = plan_room(room, pres_all.get(room['id'], {}), shells, dm, window_mods)
        if plan:
            out[room['id']] = plan
    return out
