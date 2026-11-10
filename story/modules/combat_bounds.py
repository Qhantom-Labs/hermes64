"""Combat simulation bounds for gameplay API 1.1.0 encounters (COMBAT lane checker rules).

Pure, bounded arithmetic over the fixed-tick rules of runtime/godot/modules/combat (constants mirrored below and
pinned by tests). It is an optimistic bound for the player: perfect swings, no travel time, every wave enemy hit at
once. When even that bound fails, the encounter is rejected; passing it does NOT prove the fight is fair or fun.

Rules, per encounter:
  stall      a boss phase with no attack pattern (the boss stops fighting; armoured bosses can never be hit), or an
             armoured robot that never recovers
  strength   minimum clear time over the tick bound (the playtest bot's per-challenge budget), or unavoidable damage
             (attacks with no readable dodge) adding up to the player's health
  projectile a shot that can be neither side-stepped (run + roll before it arrives) nor rolled through (its pass
             over the player outlasts the roll's i-frames)
  shockwave  a ring that cannot be rolled through and reaches the whole arena
"""
import math

# Mirrored from runtime/godot/modules/combat/runtime.gd (tests pin them against the GDScript source).
PLAYER_WINDUP, PLAYER_ACTIVE, PLAYER_RECOVERY = 8, 7, 15
PLAYER_CYCLE = PLAYER_WINDUP + PLAYER_ACTIVE + PLAYER_RECOVERY
ROLL_IFRAMES, ROLL_MOVE_TICKS, ROLL_SPEED_MPS = 15, 18, 4.0
ROLL_DISTANCE_M = ROLL_SPEED_MPS * ROLL_MOVE_TICKS / 60.0
PLAYER_RADIUS_M = 0.3
PLAYER_RUN_MPS = 2.4
READABLE_WINDUP = 6
TICK_BOUND = 5400


def pattern_rows(archetype):
    """[(id, kind, windup, active, recovery, damage, params)] for one archetype, in cycle order per phase.

    Returns {phase_id: rows}; non-boss templates have a single implicit phase."""
    template = archetype['fsm']['template']
    if template == 'boss_phases_v1':
        defs = {p['id']: p for p in archetype['boss']['patterns']}
        out = {}
        for phase in archetype['boss']['phases']:
            out[phase['id']] = [(p['id'], p['kind'], p['windup_ticks'], p['active_ticks'], p['recovery_ticks'], p['damage'],
                                 {'speed_mps': p['speed_mps'], 'size_m': p['size_m'], 'count': p['count'], 'width_m': 0.6,
                                  'distance_m': archetype['attack_range_m']})
                                for p in (defs[pid] for pid in phase['patterns'])]
        return out
    a = archetype['attack']
    kind = {'walker_patrol_v1': 'bump', 'brute_slam_v1': 'slam', 'hover_drone_v1': 'shot'}.get(template, 'melee')
    params = {}
    if kind == 'slam':
        b = archetype['brute']
        params = {'speed_mps': b['wave_speed_mps'], 'size_m': b['wave_max_m'], 'width_m': b['wave_width_m']}
    elif kind == 'shot':
        s = archetype['hover']['shot']
        params = {'speed_mps': s['speed_mps'], 'size_m': s['radius_m'], 'count': 1, 'distance_m': archetype['hover']['keep_distance_m']}
    return {'main': [(template, kind, a['windup_ticks'], a['active_ticks'], a['recovery_ticks'], a['damage'], params)]}


def phase_shares(archetype):
    """Health each phase must remove: [(phase_id, hp)] (non-boss: everything in one phase)."""
    hp = archetype['max_health']
    if 'boss' not in archetype:
        return [('main', hp)]
    phases = archetype['boss']['phases']
    out = []
    for i, phase in enumerate(phases):
        top = math.floor(hp * phase['health_permille'] / 1000)
        bottom = math.floor(hp * phases[i + 1]['health_permille'] / 1000) if i + 1 < len(phases) else 0
        out.append((phase['id'], max(0, top - bottom)))
    return out


def hits_in_window(ticks):
    """Most player hits landing inside a vulnerable window of `ticks` (swing hits are >= PLAYER_CYCLE apart)."""
    return 0 if ticks <= 0 else (ticks - 1) // PLAYER_CYCLE + 1


def projectile_avoidable(windup, speed_mps, radius_m, distance_m):
    """(side_step_ok, roll_through_ok, detail) for a shot fired after `windup` ticks from `distance_m` away."""
    travel = distance_m / max(speed_mps, 0.001) * 60.0
    side = PLAYER_RUN_MPS * (windup + travel) / 60.0 + ROLL_DISTANCE_M
    need = radius_m + PLAYER_RADIUS_M
    through = (2.0 * radius_m + 2.0 * PLAYER_RADIUS_M) / (speed_mps / 60.0)
    return side >= need, through <= ROLL_IFRAMES, {'side_step_m': round(side, 3), 'clearance_m': round(need, 3),
                                                   'pass_ticks': round(through, 2), 'iframes': ROLL_IFRAMES}


def wave_avoidable(speed_mps, width_m, reach_m, arena_half_m):
    through = (width_m + 2.0 * PLAYER_RADIUS_M) / (speed_mps / 60.0)
    return through <= ROLL_IFRAMES or reach_m < arena_half_m, {'pass_ticks': round(through, 2), 'reach_m': reach_m,
                                                               'arena_half_m': round(arena_half_m, 3)}


def unavoidable(row, arena_half_m):
    """Damage this attack deals per use when no readable dodge exists (0 when it can be dodged)."""
    _id, kind, windup, active, _recovery, damage, params = row
    if kind == 'shot':
        side, through, _ = projectile_avoidable(windup, params['speed_mps'], params['size_m'], params.get('distance_m', 3.0))
        return 0 if side or through else damage * params.get('count', 1)
    if windup < READABLE_WINDUP and active > ROLL_IFRAMES:
        return damage
    if kind in ('slam', 'surge'):
        ok, _ = wave_avoidable(params['speed_mps'] if kind == 'slam' else 6.0, params.get('width_m', 0.6), params['size_m'], arena_half_m)
        return 0 if ok else damage
    return 0


def encounter_bounds(game, encounter, max_health, archetypes):
    """Bound report for one encounter: {'min_ticks', 'unavoidable_damage', 'problems': [(rule, text)], 'spawns'}."""
    lo, hi = encounter['arena']['min'], encounter['arena']['max']
    arena_half = min(hi[0] - lo[0], hi[2] - lo[2]) / 2.0
    problems = []
    if game.get('gameplay', {}).get('movement_combat_profile') == 'combat2_v1':
        max_health = game['gameplay'].get('run', {}).get('max_health', max_health)
        if len(encounter.get('bosses', [])) > 1 and (encounter.get('attack_budget', 3) != 1 or encounter.get('attack_gap_ticks', 0) < 30):
            problems.append(('strength', 'multi-boss overlap has no established safe read window: require budget 1 and at least 30 gap ticks'))
    waves = {}
    spawns = []
    unavoidable_total = 0
    for spawn in sorted(encounter['spawns'], key=lambda s: s['id']):
        archetype = archetypes[spawn['archetype']]
        brawler = game.get('gameplay', {}).get('movement_combat_profile') == 'combat2_v1' and any(
            m['id'] == 'abilities' and m['config'].get('moveset') == 'brawler_v1'
            for m in game['gameplay']['modules'])
        armored = archetype.get('robot', {}).get('armor', 'none') == 'until_recover' and not brawler
        phases = pattern_rows(archetype)
        ticks = 0
        unavoidable_spawn = 0
        for phase_id, share in phase_shares(archetype):
            rows = phases.get(phase_id, [])
            if not rows:
                problems.append(('stall', '%s: boss phase %s has no attack pattern; the boss stops fighting there%s, so the fight stalls'
                                 % (spawn['id'], phase_id, ' and its armour never opens' if armored else '')))
                ticks = math.inf
                continue
            cycle = sum(r[2] + r[3] + r[4] for r in rows)
            hits = sum(hits_in_window(r[4]) for r in rows) if armored else max(1, cycle // PLAYER_CYCLE)
            if hits <= 0:
                problems.append(('stall', '%s: never vulnerable in phase %s' % (spawn['id'], phase_id)))
                ticks = math.inf
                continue
            cycles = math.ceil(share / hits) if share > 0 else 0
            ticks += cycles * cycle if armored else (min(share * 19, math.ceil(share / 2) * 28) if brawler else share * PLAYER_CYCLE)
            per_cycle = sum(unavoidable(r, arena_half) for r in rows)
            unavoidable_spawn += per_cycle * max(cycles, 1 if share > 0 else 0)
            for r in rows:
                if r[1] == 'shot':
                    side, through, detail = projectile_avoidable(r[2], r[6]['speed_mps'], r[6]['size_m'], r[6].get('distance_m', archetype['attack_range_m']))
                    if not side and not through:
                        problems.append(('projectile', '%s pattern %s: projectile cannot be side-stepped (%.2f m of %.2f m) or rolled through (%.1f ticks over the player > %d i-frames)'
                                         % (spawn['id'], r[0], detail['side_step_m'], detail['clearance_m'], detail['pass_ticks'], ROLL_IFRAMES)))
                if r[1] in ('slam', 'surge'):
                    ok, detail = wave_avoidable(r[6]['speed_mps'] if r[1] == 'slam' else 6.0, r[6].get('width_m', 0.6), r[6]['size_m'], arena_half)
                    if not ok:
                        problems.append(('shockwave', '%s pattern %s: shockwave covers the arena and cannot be rolled through (%.1f ticks > %d i-frames)'
                                         % (spawn['id'], r[0], detail['pass_ticks'], ROLL_IFRAMES)))
        unavoidable_total += unavoidable_spawn
        waves.setdefault(spawn['wave'], []).append(ticks)
        spawns.append({'spawn': spawn['id'], 'archetype': archetype['id'], 'armored': armored,
                       'min_ticks': ticks if ticks != math.inf else None, 'unavoidable_damage': unavoidable_spawn})
    total = sum(max(v) for v in waves.values())
    if total != math.inf and total > TICK_BOUND:
        problems.append(('strength', 'needs at least %d ticks with perfect play (bound %d, the playtest budget per challenge): too strong'
                         % (total, TICK_BOUND)))
    if unavoidable_total >= max_health:
        problems.append(('strength', 'unavoidable damage %d reaches the player health %d: unwinnable' % (unavoidable_total, max_health)))
    return {'min_ticks': total if total != math.inf else None, 'tick_bound': TICK_BOUND, 'unavoidable_damage': unavoidable_total,
            'player_health': max_health, 'spawns': spawns, 'problems': problems}
