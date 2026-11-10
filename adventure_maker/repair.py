"""Auto-repair planner: typed findings with exact fixes and a machine-readable `next` list (docs/AUTOREPAIR.md).

Every failing proof, compile, playtest or style audit is mapped to failure classes. Each finding carries the
JSON Patch ops that fix it (computed on a working copy, so every op is valid in order) and the tool calls that
apply it with the EXISTING tools:

  broken build  -> hermes64_compile(project, spec_path=<current spec>, patch_json=[...]) then hermes64_check
  proved build  -> hermes64_edit(project, operation={kind:'json-patch', patch_json:[...]})  (check is built in)
  style finding -> the same, then hermes64_check(action='audit') to re-measure

One round repairs the deepest causes first (a blocked producer before the ending that needs it), so a cheap
model can run `next` verbatim, read the new result and repeat. Heuristic fixes are labelled; findings without
a safe mechanical fix are listed with `auto: false` and no step, never a guessed edit. Deterministic: same
inputs, same plan. No clocks, randomness, network or engine.
"""
import copy
import difflib
import json
import math
import re

from .patching import apply_patch

FORMAT = 'hermes64-repair/1'
# Failure classes (code -> one-line meaning). Order is the documented "top 15+" list.
CLASSES = {
    'missing_exit': 'room has no door path from the start room',
    'locked_gate': 'door/region gate needs a value nothing in the game ever produces',
    'unreachable_item': 'an item/ability/interaction is gated by a value nothing produces',
    'unreachable_ending': 'an ending has no route',
    'unreachable_collectible': 'a collectible cannot be collected',
    'impossible_threshold': 'collectible group requires more than exist',
    'dead_end_dialogue': 'a dialogue node can trap the player (no usable choice)',
    'softlock': 'reachable state with no route to any ending',
    'ambiguous_ending': 'two endings match the same final state',
    'broken_reference': 'compile error: reference to a missing id',
    'door_not_reciprocal': 'compile error: door pair does not point back',
    'missing_camera': 'compile error: room has no camera anchor',
    'bad_door_position': 'compile error: door outside wall or on an occupied slot',
    'bad_module_config': 'module data out of range (par/deadline, arena box, spawns, waves)',
    'impossible_course_time': 'course deadline below the minimum distance/speed bound',
    'unwinnable_arena': 'enemy stats outside the winnable envelope / bot lost the arena',
    'unreachable_checkpoint': 'course checkpoint out of reach on foot',
    'missing_binding': 'piece, prop or character binds to an asset that does not exist (cuboid placeholder)',
    'over_budget': 'scene over the triangle or draw budget',
    'palette_drift': 'colours outside the style lock palette',
    'flat_room': 'flat or low-contrast frame',
    'fog_swallow': 'fog swallows the frame',
    'character_off_frame': 'room characters are not in the camera frame',
}
# Winnable-arena envelope = the bounds of the shipped Reedland Relay archetypes that the module bot beats
# (tools/modrt_examples.py: health 2-4, speed <= 1.5 m/s, reach 1.3 m, windup >= 36, active <= 12, recovery >= 36,
# damage <= 2 against 6 player health). Outside it the fix resets the stat to the bound; it is not a balance claim.
ENVELOPE = {'max_health': 4, 'speed_mps': 1.5, 'attack_range_m': 1.3, 'windup_ticks': 36, 'active_ticks': 12,
            'recovery_ticks': 36}
ON_FOOT_MAX_Y = 1.0


def pointer(*parts):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts)


class Builder:
    """Records JSON Patch ops while applying them to a working copy, so later ops see earlier ones."""

    def __init__(self, doc):
        self.doc = copy.deepcopy(doc)
        self.ops = []

    def op(self, kind, path, value=None):
        row = {'op': kind, 'path': path} if kind == 'remove' else {'op': kind, 'path': path, 'value': copy.deepcopy(value)}
        self.doc = apply_patch(self.doc, [row])
        self.ops.append(row)

    def ensure(self, *parts):
        node = self.doc
        for i, part in enumerate(parts):
            if not isinstance(node, dict):
                return
            if part not in node:
                self.op('add', pointer(*parts[:i + 1]), {})
                node = self.doc
                for p in parts[:i + 1]:
                    node = node[p]
            else:
                node = node[part]


def index_of(rows, ident):
    for i, row in enumerate(rows or []):
        if isinstance(row, dict) and row.get('id') == ident:
            return i
    return None


def finding(cls, where, says, fixer=None, heuristic=False, severity='error', **extra):
    row = {'class': cls, 'where': where, 'says': says, 'severity': severity, 'auto': fixer is not None}
    if heuristic:
        row['heuristic'] = True
    row.update(extra)
    if fixer is not None:
        row['_fix'] = fixer
    return row


# ---------------------------------------------------------------- producers ("can this value ever occur?")
def producers(spec):
    flags, gives, takes, unlocks, nodes = {}, set(), set(), set(), set()
    for f in spec.get('flags', []):
        flags.setdefault(f['id'], set()).add(bool(f.get('initial')))
    start = spec.get('start', {})
    for fid, value in (start.get('flags') or {}).items():
        flags.setdefault(fid, set()).add(bool(value))
    held = set(start.get('inventory') or [])

    def effects(rows):
        for e in rows or []:
            if not isinstance(e, dict):
                continue
            if 'flag' in e and 'value' in e:
                flags.setdefault(e['flag'], set()).add(bool(e['value']))
            if 'give' in e:
                gives.add(e['give'])
            if 'take' in e:
                takes.add(e['take'])
            if 'unlock' in e:
                unlocks.add(e['unlock'])
            if 'dialogue' in e and 'node' in e:
                nodes.add((e['dialogue'], e['node']))
    for a in spec.get('interactions', []):
        effects(a.get('effects'))
    for d in spec.get('dialogues', []):
        for n in d.get('nodes', []):
            for c in n.get('choices', []):
                effects(c.get('effects'))
                nodes.add((d['id'], c.get('next', '')))
    for c in spec.get('collectibles', []):
        if c.get('follower_flag'):
            flags.setdefault(c['follower_flag'], set()).add(True)
    for m in (spec.get('gameplay') or {}).get('modules', []):
        for ch in (m.get('entities') or {}).get('challenges', []):
            for item in (ch.get('rewards') or {}).get('items', []):
                gives.add(item)
            for ab in (ch.get('rewards') or {}).get('abilities', []):
                unlocks.add(ab)
    for d, node in (start.get('dialogue') or {}).items():
        nodes.add((d, node))
    return {'flags': flags, 'gives': gives, 'takes': takes, 'held': held, 'unlocks': unlocks, 'nodes': nodes}


def never_occurs(spec, cond, prod, rooms_reached):
    """True when no effect, start value or door path can ever make this condition true (by construction)."""
    if not isinstance(cond, dict):
        return False
    if 'flag' in cond and 'equals' in cond:
        return bool(cond['equals']) not in prod['flags'].get(cond['flag'], set())
    if 'item' in cond and 'present' in cond:
        if cond['present']:
            return cond['item'] not in prod['gives'] and cond['item'] not in prod['held']
        return cond['item'] in prod['held'] and cond['item'] not in prod['takes']
    if 'location' in cond:
        return cond['location'] not in rooms_reached
    if 'ability' in cond:
        initial = set(((spec.get('start') or {}).get('modules') or {}).get('abilities') or [])
        return cond['ability'] not in prod['unlocks'] and cond['ability'] not in initial
    if 'dialogue' in cond and 'node' in cond and cond['node'] != '':
        return (cond['dialogue'], cond['node']) not in prod['nodes']
    return False


def door_graph_reach(spec):
    start = (spec.get('start') or {}).get('location')
    rooms = {r['id']: r for r in spec.get('rooms', [])}
    seen, todo = set(), [start] if start in rooms else []
    while todo:
        rid = todo.pop()
        if rid in seen:
            continue
        seen.add(rid)
        for d in rooms[rid].get('doors', []):
            if d.get('to_room') in rooms:
                todo.append(d['to_room'])
    for a in spec.get('interactions', []):  # teleport effects also reach rooms
        for e in a.get('effects', []):
            if isinstance(e, dict) and 'location' in e and a.get('room') in seen:
                seen.add(e['location'])
    return seen


def free_slot(room, wall, avoid=()):
    extent = room['grid_size'][0 if wall in ('north', 'south') else 1]
    used = {d['position'] for d in room.get('doors', []) if d.get('wall') == wall} | set(avoid)
    middle = extent // 2
    for offset in range(extent):
        for p in (middle + offset, middle - offset):
            if 0 <= p < extent and p not in used:
                return p
    return None


OPPOSITE = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'}


# ---------------------------------------------------------------- fixers (operate on Builder by id, never raw index)
def fix_remove_conditions(collection, ident, conds, sub=None):
    """Remove the listed conditions from collection[id].conditions (or a nested door/choice)."""
    def run(b):
        rows = b.doc.get(collection) if sub is None else None
        if sub is None:
            i = index_of(rows, ident)
            if i is None:
                return
            base = [collection, i, 'conditions']
            target = rows[i].get('conditions', [])
        else:
            base, target = sub(b.doc)
            if base is None:
                return
        for k in sorted((k for k, c in enumerate(target) if c in conds), reverse=True):
            b.op('remove', pointer(*base, k))
    return run


def door_sub(rid, did):
    def sub(doc):
        ri = index_of(doc.get('rooms'), rid)
        if ri is None:
            return None, []
        di = index_of(doc['rooms'][ri].get('doors'), did)
        if di is None:
            return None, []
        return ['rooms', ri, 'doors', di, 'conditions'], doc['rooms'][ri]['doors'][di]['conditions']
    return sub


def choice_sub(did, nid, cid=None):
    def sub(doc):
        di = index_of(doc.get('dialogues'), did)
        if di is None:
            return None, []
        ni = index_of(doc['dialogues'][di]['nodes'], nid)
        if ni is None:
            return None, []
        if cid is None:
            return ['dialogues', di, 'nodes', ni, 'conditions'], doc['dialogues'][di]['nodes'][ni]['conditions']
        ci = index_of(doc['dialogues'][di]['nodes'][ni]['choices'], cid)
        if ci is None:
            return None, []
        return (['dialogues', di, 'nodes', ni, 'choices', ci, 'conditions'],
                doc['dialogues'][di]['nodes'][ni]['choices'][ci]['conditions'])
    return sub


def fix_add_exit(target, source):
    def run(b):
        rooms = b.doc['rooms']
        si, ti = index_of(rooms, source), index_of(rooms, target)
        for wall in ('east', 'north', 'west', 'south'):
            sp, tp = free_slot(rooms[si], wall), free_slot(rooms[ti], OPPOSITE[wall])
            if sp is not None and tp is not None:
                break
        else:
            return
        a, z = 'to_' + target, 'to_' + source
        b.op('add', pointer('rooms', si, 'doors', '-'), {'id': a[:64], 'wall': wall, 'position': sp, 'to_room': target,
                                                       'to_door': z[:64], 'label': 'Go to ' + rooms[ti]['name'], 'conditions': []})
        b.op('add', pointer('rooms', ti, 'doors', '-'), {'id': z[:64], 'wall': OPPOSITE[wall], 'position': tp, 'to_room': source,
                                                       'to_door': a[:64], 'label': 'Back to ' + rooms[si]['name'], 'conditions': []})
    return run


def fix_replace(path_fn, value):
    def run(b):
        path = path_fn(b.doc)
        if path:
            b.op('replace', path, value)
    return run


def module_entities(doc, module, kind):
    for mi, m in enumerate((doc.get('gameplay') or {}).get('modules', [])):
        if m.get('id') == module:
            return mi, (m.get('entities') or {}).get(kind, [])
    return None, []


def condition_sites(spec):
    """(class, where, conditions, fixer_for(missing)) for every authored condition list."""
    for r in spec.get('rooms', []):
        for d in r.get('doors', []):
            yield ('locked_gate', 'rooms/%s/doors/%s' % (r['id'], d['id']), d.get('conditions', []),
                   lambda m, rid=r['id'], did=d['id']: fix_remove_conditions(None, None, m, door_sub(rid, did)))
    for a in spec.get('interactions', []):
        yield ('unreachable_item', 'interactions/' + a['id'], a.get('conditions', []),
               lambda m, aid=a['id']: fix_remove_conditions('interactions', aid, m))
    for c in spec.get('collectibles', []):
        yield ('unreachable_collectible', 'collectibles/' + c['id'], c.get('conditions', []),
               lambda m, cid=c['id']: fix_remove_conditions('collectibles', cid, m))
    for d in spec.get('dialogues', []):
        for n in d.get('nodes', []):
            yield ('dead_end_dialogue', 'dialogues/%s/%s' % (d['id'], n['id']), n.get('conditions', []),
                   lambda m, did=d['id'], nid=n['id']: fix_remove_conditions(None, None, m, choice_sub(did, nid)))
            for c in n.get('choices', []):
                yield ('dead_end_dialogue', 'dialogues/%s/%s/%s' % (d['id'], n['id'], c['id']), c.get('conditions', []),
                       lambda m, did=d['id'], nid=n['id'], cid=c['id']: fix_remove_conditions(None, None, m, choice_sub(did, nid, cid)))
    mi, challenges = module_entities(spec, 'challenge', 'challenges')
    for ch in challenges:
        def sub(doc, cid=ch['id']):
            m, rows = module_entities(doc, 'challenge', 'challenges')
            i = index_of(rows, cid)
            return (None, []) if i is None else (['gameplay', 'modules', m, 'entities', 'challenges', i, 'conditions'], rows[i]['conditions'])
        yield ('locked_gate', 'challenges/' + ch['id'], ch.get('conditions', []), lambda m, sub=sub: fix_remove_conditions(None, None, m, sub))
    for e in spec.get('endings', []):
        yield ('unreachable_ending', 'endings/' + e['id'], e.get('conditions', []),
               lambda m, eid=e['id']: fix_remove_conditions('endings', eid, m))


def producer_rooms(spec, cond):
    """Rooms where an effect can make `cond` true, or None when unknown/initially true."""
    if 'flag' in cond and 'equals' in cond:
        if bool((spec.get('start') or {}).get('flags', {}).get(cond['flag'])) == bool(cond['equals']):
            return None
        hit = lambda e: e.get('flag') == cond['flag'] and e.get('value') == cond['equals']
    elif 'item' in cond and cond.get('present'):
        if cond['item'] in ((spec.get('start') or {}).get('inventory') or []):
            return None
        hit = lambda e: e.get('give') == cond['item']
    else:
        return None
    rooms = set()
    talk = {}
    for a in spec.get('interactions', []):
        for e in a.get('effects', []):
            if isinstance(e, dict):
                if hit(e):
                    rooms.add(a['room'])
                if 'dialogue' in e:
                    talk.setdefault(e['dialogue'], set()).add(a['room'])
    for c in spec.get('collectibles', []):
        if c.get('dialogue'):
            talk.setdefault(c['dialogue'], set()).add(c['room'])
    for d in spec.get('dialogues', []):
        if any(hit(e) for n in d.get('nodes', []) for c in n.get('choices', []) for e in c.get('effects', []) if isinstance(e, dict)):
            if d['id'] not in talk:
                return None
            rooms |= talk[d['id']]
    return rooms


def circular(spec, where, conds):
    """Door conditions whose every producer lies only behind this same door (a gate that needs its own key)."""
    parts = where.split('/')
    if parts[0] != 'rooms' or len(parts) != 4:
        return []
    rid, did = parts[1], parts[3]
    door_row = next((d for r in spec['rooms'] if r['id'] == rid for d in r['doors'] if d['id'] == did), None)
    if door_row is None:
        return []
    trimmed = copy.deepcopy(spec)
    for r in trimmed['rooms']:
        r['doors'] = [d for d in r['doors'] if not ((r['id'], d['id']) == (rid, did) or
                                                    (r['id'], d['id']) == (door_row['to_room'], door_row['to_door']))]
    reach = door_graph_reach(trimmed)
    out = []
    for c in conds:
        rooms = producer_rooms(spec, c) if isinstance(c, dict) else None
        if rooms and not rooms & reach:
            out.append(c)
    return out


def _story():
    if '.' in (__package__ or ''):
        from ..story.compiler import compile_spec
        from ..story.checker import check_game
    else:
        from story.compiler import compile_spec
        from story.checker import check_game
    return compile_spec, check_game


def first_proving(spec, fixers, limit=12):
    """Try candidate fixes in-process (local story compiler/checker) and return the first whose result proves.
    Used only where a mechanical rule cannot know the author's intent (ambiguous/unreachable endings)."""
    compile_spec, check_game = _story()
    for fixer in fixers[:limit]:
        b = Builder(spec)
        try:
            fixer(b)
            if not b.ops:
                continue
            report = check_game(compile_spec(b.doc), max_states=20000)
        except Exception:
            continue
        if report.get('status') in ('proved', 'conditional'):
            return fixer
    return None


# ---------------------------------------------------------------- analysers
def from_proof(spec, proof):
    """Findings for a rejected/invalid proof report (story 1.0/1.1 and STORY 1.2 module analysis)."""
    out = []
    if not isinstance(proof, dict):
        return out
    reached = door_graph_reach(spec)
    prod = producers(spec)
    rooms = {r['id']: r for r in spec.get('rooms', [])}
    for rid in rooms:
        if rid not in reached and reached:
            source = sorted(reached, key=lambda r: [x['id'] for x in spec['rooms']].index(r))[0]
            out.append(finding('missing_exit', 'rooms/' + rid, 'room %s has no door path from the start; add a door pair to %s' % (rid, source),
                               fix_add_exit(rid, source)))
    # Deepest causes: condition sites whose required value can never occur by construction (or only behind the
    # very gate that needs it). Scans the spec itself, so symbolic and module reports are covered as well.
    deep = []
    for kind, where, conds, fixer_for in condition_sites(spec):
        missing = [c for c in conds if never_occurs(spec, c, prod, reached)]
        if kind == 'locked_gate' and not missing:
            missing = circular(spec, where, conds)
        if missing:
            deep.append(finding(kind, where, '%s needs %s, which %s: drop that condition' % (
                where, json.dumps(missing), 'nothing produces' if kind != 'locked_gate' or any(never_occurs(spec, c, prod, reached) for c in missing)
                else 'is only produced behind this gate'), fixer_for(missing)))
    order = {'endings': 1, 'quests': 1}
    if any(order.get(f['where'].split('/')[0], 0) == 0 for f in deep):
        deep = [f for f in deep if order.get(f['where'].split('/')[0], 0) == 0] + [
            dict(f, deferred=True, auto=False, _fix=None) for f in deep if order.get(f['where'].split('/')[0], 0) == 1]
    out += deep
    for gid, g in sorted((proof.get('groups') or {}).items()):
        if isinstance(g, dict) and not g.get('attainable') and g.get('required', 0) > g.get('supply', 0):
            gi = index_of(spec.get('collectible_groups'), gid)
            out.append(finding('impossible_threshold', 'collectible_groups/' + gid, 'group %s requires %d but only %d exist: require %d' % (gid, g['required'], g['supply'], g['supply']),
                               fix_replace(lambda d, gi=gi: pointer('collectible_groups', gi, 'required'), g['supply'])))
    for row in proof.get('thresholds') or []:
        if not row.get('attainable') and row.get('required', 0) > row.get('supply', 0) and row.get('path'):
            parts = row['path'].split('/')
            out.append(finding('impossible_threshold', row['path'], 'threshold at %s asks %d of %d: ask %d' % (row['path'], row['required'], row['supply'], row['supply']),
                               threshold_fixer(parts, row['supply'])))
    for row in proof.get('counterexamples') or []:
        out += module_counterexample(spec, row)
    ambiguous = (proof.get('ambiguous_terminals') or [])[:1]
    for row in ambiguous:
        out += ambiguous_findings(spec, row)
    if any(f.get('auto') for f in out) or ambiguous:
        return dedupe(out)  # softlocks / unreachable endings are usually consequences: fix causes first
    for eid, v in sorted((proof.get('endings') or {}).items()):
        if not (isinstance(v, dict) and v.get('reachable') is False):
            continue
        ending = spec['endings'][index_of(spec['endings'], eid)]
        conds = ending.get('conditions', [])
        options = [(c, fix_remove_conditions('endings', eid, [c])) for c in reversed(conds)]
        picked = first_proving(spec, [f for _, f in options])
        if picked is not None:
            cond = next(c for c, f in options if f is picked)
            out.append(finding('unreachable_ending', 'endings/' + eid, 'ending %s has no route: dropping its condition %s makes the game prove (checked in-process)' % (eid, json.dumps(cond)),
                               picked, heuristic=True, verified=True))
        else:
            out.append(finding('unreachable_ending', 'endings/' + eid, 'ending %s has no route and no single condition removal fixes it (no automatic fix)' % eid))
    for cid, c in sorted((proof.get('collectibles') or {}).items()):
        if isinstance(c, dict) and c.get('reachable') is False:
            out.append(finding('unreachable_collectible', 'collectibles/' + cid, 'collectible %s cannot be collected; inspect its gate/dialogue (no safe automatic fix)' % cid))
    for row in (proof.get('softlocks') or [])[:3]:
        out += softlock_findings(spec, row, prod, reached)
    return dedupe(out)


def threshold_fixer(parts, supply):
    # path like interactions/<id>/conditions/<k> or endings/<id>/conditions/<k>
    def run(b):
        coll, ident = parts[0], parts[1]
        if coll in ('interactions', 'endings', 'quests', 'collectibles'):
            i = index_of(b.doc.get(coll), ident)
            if i is not None and parts[-2] == 'conditions':
                b.op('replace', pointer(coll, i, 'conditions', int(parts[-1]), 'at_least'), supply)
    return run


def softlock_findings(spec, row, prod, reached):
    state = row.get('state') or {}
    out = []
    room = next((r for r in spec.get('rooms', []) if r['id'] == state.get('location')), None)
    flags = state.get('flags') or {}
    inventory = set(state.get('inventory') or [])

    def holds(c):
        if 'flag' in c:
            return flags.get(c['flag']) == c.get('equals')
        if 'item' in c:
            return (c['item'] in inventory) == bool(c.get('present'))
        return True
    if room:
        for d in room.get('doors', []):
            blocked = [c for c in d.get('conditions', []) if isinstance(c, dict) and not holds(c)]
            if blocked:
                out.append(finding('softlock', 'rooms/%s/doors/%s' % (room['id'], d['id']),
                                   'softlock in %s: the way out (%s) stays shut once %s is false: drop that condition' % (room['id'], d['id'], json.dumps(blocked)),
                                   fix_remove_conditions(None, None, blocked, door_sub(room['id'], d['id'])), heuristic=True))
    if not out:
        needed = {c['item'] for e in spec.get('endings', []) for c in e.get('conditions', []) if isinstance(c, dict) and c.get('item') and c.get('present')}
        for a in spec.get('interactions', []):
            for k, e in enumerate(a.get('effects', [])):
                if isinstance(e, dict) and e.get('take') in needed and e['take'] not in inventory:
                    out.append(finding('softlock', 'interactions/' + a['id'], 'softlock: %s consumes %s that an ending still needs: keep the item' % (a['id'], e['take']),
                                       remove_effect(a['id'], e), heuristic=True))
    if not out:
        out.append(finding('softlock', 'state', 'softlock at %s with no safe automatic fix; see proof softlocks witness' % state.get('location')))
    return out


def remove_effect(aid, effect):
    def run(b):
        i = index_of(b.doc.get('interactions'), aid)
        if i is None:
            return
        for k in sorted((k for k, e in enumerate(b.doc['interactions'][i]['effects']) if e == effect), reverse=True):
            b.op('remove', pointer('interactions', i, 'effects', k))
    return run


def ambiguous_findings(spec, row):
    """Two endings match one final state: the more general one also requires a flag value that separates them.
    Candidates (NOT a flag of the specific ending first, then any other flag value) are checked in-process."""
    names = row.get('endings') or []
    if len(names) < 2:
        return []
    a, b = (spec['endings'][index_of(spec['endings'], n)] for n in names[:2])
    general, specific = (a, b) if len(a.get('conditions', [])) <= len(b.get('conditions', [])) else (b, a)
    own = {c.get('flag') for c in general.get('conditions', []) if isinstance(c, dict)}
    gid = general['id']
    wanted = [{'flag': c['flag'], 'equals': not c['equals']} for c in specific.get('conditions', []) if isinstance(c, dict) and 'flag' in c and c['flag'] not in own]
    for f in spec.get('flags', []):
        for value in (True, False):
            cand = {'flag': f['id'], 'equals': value}
            if f['id'] not in own and cand not in wanted:
                wanted.append(cand)

    def adder(cond):
        def run(b):
            i = index_of(b.doc['endings'], gid)
            if i is not None and cond not in b.doc['endings'][i]['conditions']:
                b.op('add', pointer('endings', i, 'conditions', '-'), cond)
        return run
    options = [(c, adder(c)) for c in wanted]
    picked = first_proving(spec, [f for _, f in options], limit=16)
    if picked is None:
        return [finding('ambiguous_ending', 'endings/' + gid, 'endings %s overlap; no single extra flag condition separates them (no automatic fix)' % ', '.join(names))]
    cond = next(c for c, f in options if f is picked)
    return [finding('ambiguous_ending', 'endings/' + gid, 'endings %s match the same final state: %s also requires %s (checked in-process)' % (
        ', '.join(names), gid, json.dumps(cond)), picked, heuristic=True, verified=True)]


def module_counterexample(spec, row):
    oid = row.get('obligation', '')
    if oid.startswith(('gate:', 'region:')):
        # A region gate that never opens before an ending (often a condition only true at the end): open it.
        if oid.startswith('gate:'):
            _, rid, did = oid.split(':', 2)
            doors = [(rid, did)]
        else:
            region = next((r for m in (spec.get('gameplay') or {}).get('modules', []) if m.get('id') == 'regions'
                           for r in (m.get('entities') or {}).get('regions', []) if r.get('id') == oid.split(':', 1)[1]), None)
            target = (region or {}).get('room')
            doors = [(r['id'], d['id']) for r in spec.get('rooms', []) for d in r.get('doors', []) if d.get('to_room') == target and d.get('conditions')]
        out = []
        for rid, did in doors:
            d = next((x for r in spec.get('rooms', []) if r['id'] == rid for x in r.get('doors', []) if x['id'] == did), None)
            if d and d.get('conditions'):
                out.append(finding('locked_gate', 'rooms/%s/doors/%s' % (rid, did), 'gate %s/%s never opens before an ending (%s): drop its conditions' % (
                    rid, did, json.dumps(d['conditions'])), fix_remove_conditions(None, None, list(d['conditions']), door_sub(rid, did)), heuristic=True))
        return out
    if oid.startswith('metric:'):
        tid = oid.split(':', 1)[1]
        m = re.search(r'at least (\d+) ticks', row.get('explanation', ''))
        if not m:
            return []
        bound = int(m.group(1))
        limit = int(math.ceil(bound * 1.5))

        def run(b):
            mi, tracks = module_entities(b.doc, 'course', 'tracks')
            ti = index_of(tracks, tid)
            if ti is None:
                return
            b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'tracks', ti, 'time_limit_ticks'), limit)
            if tracks[ti].get('par_ticks', 0) > limit:
                b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'tracks', ti, 'par_ticks'), limit)
        return [finding('impossible_course_time', 'tracks/' + tid, 'course %s needs at least %d ticks: set time_limit_ticks to %d' % (tid, bound, limit), run)]
    return []


def lint_modules(spec):
    """Static module checks that compile cannot see: unwinnable arena stats and off-foot checkpoints."""
    out = []
    mods = {m.get('id'): m for m in (spec.get('gameplay') or {}).get('modules', [])}
    hp = ((mods.get('abilities') or {}).get('config') or {}).get('max_health', 6)
    for a in ((mods.get('combat') or {}).get('entities') or {}).get('archetypes', []):
        changes = {}
        for key in ('max_health', 'speed_mps', 'attack_range_m'):
            if a.get(key, 0) > ENVELOPE[key]:
                changes[key] = ENVELOPE[key]
        att = dict(a.get('attack') or {})
        if att.get('windup_ticks', 99) < ENVELOPE['windup_ticks']:
            att['windup_ticks'] = ENVELOPE['windup_ticks']
        if att.get('active_ticks', 0) > ENVELOPE['active_ticks']:
            att['active_ticks'] = ENVELOPE['active_ticks']
        if att.get('recovery_ticks', 99) < ENVELOPE['recovery_ticks']:
            att['recovery_ticks'] = ENVELOPE['recovery_ticks']
        if att.get('damage', 0) > max(1, hp // 3):
            att['damage'] = max(1, hp // 3)
        if att != (a.get('attack') or {}):
            changes['attack'] = att
        if changes:
            aid = a['id']

            def run(b, aid=aid, changes=changes):
                mi, rows = module_entities(b.doc, 'combat', 'archetypes')
                i = index_of(rows, aid)
                for key, value in sorted(changes.items()):
                    b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'archetypes', i, key), value)
            out.append(finding('unwinnable_arena', 'archetypes/' + aid, 'enemy %s is outside the winnable envelope (%s): reset to %s' % (
                aid, ', '.join(sorted(changes)), json.dumps(changes, sort_keys=True)), run))
    course = (mods.get('course') or {})
    if (course.get('config') or {}).get('mover', 'on_foot') == 'on_foot':
        for t in (course.get('entities') or {}).get('tracks', []):
            for cp in t.get('checkpoints', []):
                if cp['position_m'][1] > ON_FOOT_MAX_Y:
                    tid, cpid = t['id'], cp['id']

                    def run(b, tid=tid, cpid=cpid):
                        mi, tracks = module_entities(b.doc, 'course', 'tracks')
                        ti = index_of(tracks, tid)
                        ci = index_of(tracks[ti]['checkpoints'], cpid)
                        b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'tracks', ti, 'checkpoints', ci, 'position_m', 1), 0)
                    out.append(finding('unreachable_checkpoint', 'tracks/%s/%s' % (tid, cpid), 'checkpoint %s is %.1f m up, out of reach on foot: put it on the ground (y=0)' % (cpid, cp['position_m'][1]), run))
    return out + module_config_findings(spec)


def module_config_findings(spec):
    out = []
    mods = {m.get('id'): m for m in (spec.get('gameplay') or {}).get('modules', [])}
    for t in ((mods.get('course') or {}).get('entities') or {}).get('tracks', []):
        if t.get('par_ticks', 0) > t.get('time_limit_ticks', 0):
            tid = t['id']
            out.append(finding('bad_module_config', 'tracks/' + tid, 'course %s par %d exceeds its deadline %d: set par to the deadline' % (tid, t['par_ticks'], t['time_limit_ticks']),
                               lambda b, tid=tid: _set_track(b, tid, 'par_ticks', None)))
    combat = (mods.get('combat') or {})
    bound = (combat.get('config') or {}).get('max_simultaneous', 3)
    for e in (combat.get('entities') or {}).get('encounters', []):
        lo, hi = e['arena']['min'], e['arena']['max']
        eid = e['id']
        if any(a >= b for a, b in zip(lo, hi)):
            out.append(finding('bad_module_config', 'encounters/' + eid, 'arena %s min/max are crossed: swap them per axis' % eid,
                               lambda b, eid=eid: _fix_arena(b, eid)))
            continue
        waves = sorted({s['wave'] for s in e.get('spawns', [])})
        counts = {w: sum(1 for s in e['spawns'] if s['wave'] == w) for w in waves}
        outside = [s['id'] for s in e.get('spawns', []) if not all(lo[k] <= s['position_m'][k] <= hi[k] for k in range(3))]
        if outside or waves != list(range(len(waves))) or any(c > bound for c in counts.values()):
            out.append(finding('bad_module_config', 'encounters/' + eid, 'arena %s spawns invalid (outside box %s, waves %s, max %d at once): move inside, renumber waves' % (
                eid, outside, waves, bound), lambda b, eid=eid, bound=bound: _fix_spawns(b, eid, bound)))
    return out


def _set_track(b, tid, key, value):
    mi, tracks = module_entities(b.doc, 'course', 'tracks')
    ti = index_of(tracks, tid)
    b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'tracks', ti, 'par_ticks'), tracks[ti]['time_limit_ticks'])


def _fix_arena(b, eid):
    mi, rows = module_entities(b.doc, 'combat', 'encounters')
    i = index_of(rows, eid)
    lo, hi = rows[i]['arena']['min'], rows[i]['arena']['max']
    new_lo = [min(a, c) for a, c in zip(lo, hi)]
    new_hi = [max(a, c) if a != c else a + 1 for a, c in zip(lo, hi)]
    b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'encounters', i, 'arena'), {'min': new_lo, 'max': new_hi})


def _fix_spawns(b, eid, bound):
    mi, rows = module_entities(b.doc, 'combat', 'encounters')
    i = index_of(rows, eid)
    lo, hi = rows[i]['arena']['min'], rows[i]['arena']['max']
    spawns = copy.deepcopy(rows[i]['spawns'])
    order = sorted(range(len(spawns)), key=lambda k: (spawns[k]['wave'], k))
    for rank, k in enumerate(order):
        spawns[k]['wave'] = rank // max(1, bound)
        spawns[k]['position_m'] = [min(max(v, lo[a] + 0.5 if hi[a] - lo[a] > 1 else lo[a]), hi[a] - 0.5 if hi[a] - lo[a] > 1 else hi[a]) for a, v in enumerate(spawns[k]['position_m'])]
    b.op('replace', pointer('gameplay', 'modules', mi, 'entities', 'encounters', i, 'spawns'), spawns)


# ---------------------------------------------------------------- compile errors
def from_compile_error(spec, message):
    """Findings for a compile failure (story SpecError text)."""
    text = str(message or '')
    m = None
    for line in text.splitlines()[::-1]:
        m = next((x for x in re.finditer(r'([A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)+): (.+)$', line.strip()) if x), None)
        if m:
            break
    out = module_config_findings(spec) if (spec.get('gameplay') or {}).get('modules') else []
    if not m:
        return out
    path, reason = m.group(1), m.group(2)
    parts = path.split('/')
    rooms = {r['id']: r for r in spec.get('rooms', [])}
    if 'at least one camera anchor required' in reason and parts[0] == 'rooms':
        rid = parts[1]
        w, d = rooms[rid]['grid_size']
        cam = {'id': 'main', 'position': [w / 2.0, 6, d + 4], 'look_at': [w / 2.0, 1, d / 2.0]}
        out.append(finding('missing_camera', path, 'room %s has no camera: add camera "main" looking at the room centre' % rid,
                           lambda b, rid=rid, cam=cam: b.op('add', pointer('rooms', index_of(b.doc['rooms'], rid), 'cameras', '-'), cam)))
    elif ('outside wall extent' in reason or 'duplicate door position' in reason) and parts[0] == 'rooms':
        rid, did = parts[1], parts[3]

        def run(b, rid=rid, did=did):
            ri = index_of(b.doc['rooms'], rid)
            room = b.doc['rooms'][ri]
            di = index_of(room['doors'], did)
            others = copy.deepcopy(room)
            others['doors'] = [x for x in room['doors'] if x['id'] != did]
            b.op('replace', pointer('rooms', ri, 'doors', di, 'position'), free_slot(others, room['doors'][di]['wall']))
        out.append(finding('bad_door_position', path, 'door %s/%s sits off the wall or on another door: move it to a free slot' % (rid, did), run))
    elif 'door is not reciprocal' in reason or ('missing reference' in reason and len(parts) == 3 and parts[1] == 'door'):
        rid, did = parts[0], parts[2]
        door = next(x for x in rooms[rid]['doors'] if x['id'] == did)
        target = door['to_room']

        def run(b, rid=rid, did=did, target=target):
            ri, ti = index_of(b.doc['rooms'], rid), index_of(b.doc['rooms'], target)
            di = index_of(b.doc['rooms'][ri]['doors'], did)
            # A door in the target room that already leads back here: link the pair to each other.
            for bi, back_door in enumerate(b.doc['rooms'][ti]['doors']):
                if back_door['to_room'] == rid:
                    b.op('replace', pointer('rooms', ri, 'doors', di, 'to_door'), back_door['id'])
                    if back_door['to_door'] != did:
                        b.op('replace', pointer('rooms', ti, 'doors', bi, 'to_door'), did)
                    return
            wall = OPPOSITE[b.doc['rooms'][ri]['doors'][di]['wall']]
            back = ('back_' + rid)[:64]
            while index_of(b.doc['rooms'][ti]['doors'], back) is not None:
                back = (back + '_')[:64]
            b.op('add', pointer('rooms', ti, 'doors', '-'), {'id': back, 'wall': wall, 'position': free_slot(b.doc['rooms'][ti], wall), 'to_room': rid,
                                                           'to_door': did, 'label': 'Back to ' + b.doc['rooms'][ri]['name'], 'conditions': []})
            b.op('replace', pointer('rooms', ri, 'doors', di, 'to_door'), back)
        out.append(finding('door_not_reciprocal', path, 'door %s/%s has no matching door back in %s: add one and link them' % (rid, did, target), run))
    elif 'missing reference' in reason:
        ref = re.search(r"missing reference '?([^']+)'?", reason)
        value = ref.group(1) if ref else None
        out.append(finding('broken_reference', path, '%s points at missing %r: remove that reference' % (path, value), remove_reference(parts, value)))
    elif 'unknown or malformed' in reason and 'conditions' in parts or 'effects' in parts:
        out.append(finding('broken_reference', path, '%s is malformed: remove it' % path, remove_reference(parts, None)))
    return dedupe(out)


def remove_reference(parts, value):
    """Remove the array entry (character id, door, condition/effect) that holds a missing reference."""
    def run(b):
        node, trail = b.doc, []
        for p in parts:
            if isinstance(node, list):
                i = index_of(node, p) if not p.isdigit() else int(p)
                if i is None or i >= len(node):
                    break
                node, trail = node[i], trail + [i]
            elif isinstance(node, dict) and p in node:
                node, trail = node[p], trail + [p]
            else:
                break
        if isinstance(node, list) and value is not None and value in node:
            b.op('remove', pointer(*trail, node.index(value)))
        elif isinstance(node, dict) and len(trail) >= 2 and isinstance(trail[-1], int):
            b.op('remove', pointer(*trail))
        elif isinstance(node, str) and len(trail) >= 3 and isinstance(trail[-2], int) and trail[-1] in ('to_room',):
            b.op('remove', pointer(*trail[:-1]))
    return run


# ---------------------------------------------------------------- playtest
def from_playtest(spec, report):
    out = []
    if not isinstance(report, dict):
        return out
    if (spec.get('gameplay') or {}).get('modules'):
        lint = lint_modules(spec)
        if report.get('verdict') in ('ROUGH', 'BROKEN') or not report.get('completed', True):
            out += lint
        else:
            out += [dict(f, severity='warn') for f in lint]
    return out


# ---------------------------------------------------------------- planning
def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        key = (r['class'], r['where'])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def build(spec, findings, limit=100):
    """Apply every auto fix on one working copy, in order. Fixes that fail are marked, never half-applied."""
    b = Builder(spec)
    applied = []
    for f in findings:
        fix = f.pop('_fix', None)
        if fix is None:
            continue
        before_doc, before_ops = copy.deepcopy(b.doc), list(b.ops)
        try:
            fix(b)
        except Exception as exc:  # a fixer that cannot apply must not corrupt the plan
            b.doc, b.ops = before_doc, before_ops
            f['auto'] = False
            f['fix_error'] = type(exc).__name__
            continue
        f['ops'] = b.ops[len(before_ops):]
        if not f['ops']:
            f['auto'] = False
        elif len(b.ops) > limit:
            b.doc, b.ops = before_doc, before_ops
            f['auto'] = False
            f['deferred'] = True
            f.pop('ops', None)
        else:
            applied.append(f['class'])
    for f in findings:
        f.pop('_fix', None)
    return b.ops, applied


def next_steps(project, ops, current, proved, then=None, pre=None):
    """Ordered exact tool calls for one repair round."""
    steps = [dict(step) for step in pre or []]
    if ops:
        patch = json.dumps(ops, separators=(',', ':'), sort_keys=True)
        if proved:
            steps.append({'tool': 'hermes64_edit', 'args': {'project': project, 'operation': {'kind': 'json-patch', 'patch_json': patch}},
                          'why': 'apply the fixes as one checked edit (adopted only if it still proves)'})
        else:
            steps.append({'tool': 'hermes64_compile', 'args': {'project': project, 'spec_path': current, 'patch_json': patch},
                          'why': 'compile the current source with the fixes applied'})
            steps.append({'tool': 'hermes64_check', 'args': {'project': project}, 'why': 're-prove; read its next list again'})
    for step in then or []:
        steps.append(step)
    for i, row in enumerate(steps):
        row['step'] = i + 1
    return steps


def plan(project, spec, current, proof=None, compile_error=None, playtest=None, audit_findings=None, proved=False, then=None,
         pre=None, include_warn=False):
    """{'findings': [...], 'next': [...], 'classes': [...]} for one repair round. `pre`: tool steps that run first
    (e.g. hermes64_build_assets); `then`: steps after the fix (e.g. re-audit)."""
    findings = []
    if compile_error is not None:
        findings += from_compile_error(spec, compile_error)
    if proof is not None:
        findings += from_proof(spec, proof)
    if playtest is not None:
        findings += from_playtest(spec, playtest)
    if audit_findings:
        findings += audit_findings
    findings = dedupe(findings)
    actionable = [f for f in findings if f.get('severity', 'error') == 'error' or (include_warn and f.get('_fix'))]
    ops, applied = build(spec, actionable)
    for f in findings:
        f.pop('_fix', None)
    # Identity-changing fixes (character rebinding) cannot pass hermes64_edit's identity guard: compile instead.
    if any(f.get('route') == 'compile' and f.get('ops') for f in actionable):
        proved = False
    steps = next_steps(project, ops, current, proved, then if (ops or pre) else None, pre)
    return {'format': FORMAT, 'findings': findings, 'classes': sorted(set(applied)), 'next': steps,
            'manual': [f['says'] for f in findings if not f.get('auto') and f.get('severity', 'error') == 'error'][:8]}


def lint(spec):
    """Dead content in a build that still proves: conditions nothing can ever satisfy (warn, with fixes)."""
    prod, reached = producers(spec), door_graph_reach(spec)
    out = []
    for kind, where, conds, fixer_for in condition_sites(spec):
        missing = [c for c in conds if never_occurs(spec, c, prod, reached)]
        if missing:
            out.append(finding(kind, where, '%s can never happen: it needs %s, which nothing produces' % (where, json.dumps(missing)),
                               fixer_for(missing), severity='warn'))
    return out


def nearest_asset(ref, known):
    """Closest known asset id for an unknown ref (same family first)."""
    family = re.split(r'[./]', ref, 1)[0]
    same = sorted(k for k in known if k.startswith(family + '.'))
    pick = difflib.get_close_matches(ref, same or sorted(known), n=1, cutoff=0.0)
    return pick[0] if pick else None
