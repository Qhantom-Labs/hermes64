"""Closed puzzle data, the exact deterministic grid rules, and bounded per-visit search.

The same rules run in ``runtime/godot/modules/puzzle/rules.gd``; ``tools/puzzle_vectors.py`` binds the two
with shared transition vectors. Solver time unit: one grid step (``config.step_ticks`` simulation ticks).
Transient state (player cell, blocks, switches, plates, torches, orbs, doors, bridges, timers) is never saved.
"""
from collections import deque
from ..errors import SpecError
from ..modules import schema as S
from . import PREFIX

DIRS = {'n': (0, -1), 'e': (1, 0), 's': (0, 1), 'w': (-1, 0)}
ORDER = ('n', 'e', 's', 'w')
OPPOSITE = {'n': 's', 's': 'n', 'e': 'w', 'w': 'e'}
SOURCES = ('switch', 'plate', 'torch', 'orb')
GOAL_SOURCES = SOURCES + ('lock',)
ACTABLE = ('switch', 'torch', 'lock', 'key', 'orb')
INTERACTIVE = ('switch', 'plate', 'torch', 'lock', 'key', 'block', 'orb')
SOLID = ('switch', 'torch', 'orb', 'shutter', 'key')
LIMITS = {'cells': 16, 'blocks': 3, 'stateful_bits': 23, 'timed_gates': 2, 'open_steps': 15, 'elements': 32}

PID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,47}$', 'minLength': 1, 'maxLength': 48}
EID = PID  # element ids share the 48-character bound so reserved fact flags stay within 64 characters
CELL = S.array(S.integer(0, 15), 2, 2)
LINK = S.obj(of=S.array(EID, 8, 1, True), at_least=S.integer(1, 8), invert={'type': 'boolean'})
ROW = {'type': 'string', 'pattern': '^[.#_]{3,16}$', 'minLength': 3, 'maxLength': 16}


def element(kind, **fields):
    return S.obj(id=EID, kind={'const': kind}, **fields)


ELEMENT = {'oneOf': [
    element('switch', cell=CELL, mode=S.enum('toggle', 'latch')),
    element('plate', cell=CELL, weight=S.integer(1, 2), mode=S.enum('momentary', 'latch')),
    element('torch', cell=CELL, order=S.integer(0, 8)),
    element('lock', cell=CELL, accepts=S.array(S.ID, 8, 1, True)),
    element('key', cell=CELL, item=S.ID),
    element('block', cell=CELL, pull={'type': 'boolean'}),
    element('bridge', cells=S.array(CELL, 8, 1, True), when=LINK, mode=S.enum('momentary', 'latch')),
    element('door', cell=CELL, when=LINK),
    element('timed_gate', cell=CELL, when=LINK, open_ticks=S.integer(60, 3600)),
    element('orb', cell=CELL, reach=S.integer(1, 8)),
    element('shutter', cell=CELL, dir=S.enum('n', 'e', 's', 'w'))]}
GOAL = S.obj(when=LINK, opens=S.array(EID, 8, unique=True), rewards=S.obj(items=S.IDS))
PUZZLE = S.obj(id=PID, room=S.ID, name=S.TEXT, layout=S.array(ROW, 16, 3), start=CELL,
               persistence=S.enum('reset_on_leave', 'persistent'), reset=S.enum('hold', 'none'),
               elements=S.array(ELEMENT, 32, 1), goal=GOAL, hint=S.array(EID, 16, unique=True),
               max_states=S.integer(1, 200000))
# Hold R is the controls profile's existing hold-to-retry gesture (Actions ``reset``); in a puzzle room it
# resets the room instead of returning to the last checkpoint.
CONFIG = S.obj(cell_m={'const': 1}, player_weight={'const': 1}, block_weight={'const': 2},
               step_ticks=S.integer(12, 120), reset_action={'const': 'reset'})
ENTITIES = S.obj(puzzles=S.array(PUZZLE, 16, 1))
MODULE = S.obj(id={'const': 'puzzle'}, version={'const': '1.0.0'}, config=CONFIG, entities=ENTITIES)
FACTS = S.obj(solved=S.array(PID, 16, unique=True), taken=S.array(EID, 64, unique=True),
              opened=S.array(EID, 64, unique=True), latched=S.array(EID, 64, unique=True), entry=S.EMPTY_ID)
CONDITION = S.obj(puzzle=PID, status=S.enum('solved'))
EMPTY_FACTS = {'solved': [], 'taken': [], 'opened': [], 'latched': [], 'entry': ''}


def require(ok, path, reason):
    if not ok:
        raise SpecError(path + ': ' + reason)


def door_cell(door, room):
    """Exit/entry cell of a STORY door on the 1 m grid (cell centres match view/room.gd door_position)."""
    w, d = room['grid_size']
    p = door['position']
    return {'north': (p, 0), 'south': (p, d - 1), 'west': (0, p), 'east': (w - 1, p)}[door['wall']]


def module_of(spec):
    for m in spec.get('gameplay', {}).get('modules', []):
        if isinstance(m, dict) and m.get('id') == 'puzzle':
            return m
    return None


def fact_rows(module):
    """Every reserved fact flag of a (validated) puzzle module: [(field, id)] in a fixed order."""
    rows = []
    for p in sorted(module['entities']['puzzles'], key=lambda p: p['id']):
        rows.append(('solved', p['id']))
        for e in sorted(p['elements'], key=lambda e: e['id']):
            if e['kind'] == 'key':
                rows.append(('taken', e['id']))
            elif e['kind'] == 'lock':
                rows.append(('opened', e['id']))
            elif p['persistence'] == 'persistent' and e['kind'] in ('switch', 'plate') and e['mode'] == 'latch':
                rows.append(('latched', e['id']))
    return rows


def normalize(module):
    """Order-free sets are canonicalized; layout rows and the authored hint order stay meaningful."""
    for p in module['entities']['puzzles']:
        p['elements'].sort(key=lambda e: e['id'])
        p['goal']['opens'].sort()
        p['goal']['rewards']['items'].sort()
        p['goal']['when']['of'].sort()
        for e in p['elements']:
            if 'when' in e:
                e['when']['of'].sort()
            if 'accepts' in e:
                e['accepts'].sort()
            if 'cells' in e:
                e['cells'].sort()
    module['entities']['puzzles'].sort(key=lambda p: p['id'])


# --------------------------------------------------------------------------- admission


def validate(spec, module):
    """Bounded-data and cross-reference rules for the puzzle family on the 1.3 source."""
    S.validate(module, MODULE, 'gameplay/puzzle')
    rooms = {r['id']: r for r in spec['rooms']}
    items = {i['id'] for i in spec['items']}
    mods = {m['id']: m for m in spec['gameplay']['modules']}
    require('challenge' in mods, 'puzzle', 'missing module dependency challenge')
    require('regions' not in mods, 'puzzle', 'puzzle and regions modules cannot be combined in STORY 1.3.0')
    for f in spec['flags']:
        require(not f['id'].startswith(PREFIX), 'flags/' + f['id'], 'the puzzle__ flag prefix is reserved')
    config = module['config']
    seen_rooms, element_ids, rewards, key_items, puzzle_ids = set(), set(), [], [], set()
    challenge_rooms = {c['room'] for c in mods['challenge']['entities']['challenges']}
    for p in module['entities']['puzzles']:
        at = 'puzzle/' + p['id']
        require(p['id'] not in puzzle_ids, at, 'duplicate puzzle id')
        puzzle_ids.add(p['id'])
        require(p['room'] in rooms, at, 'missing room ' + p['room'])
        require(p['room'] not in seen_rooms, at, 'one puzzle per room')
        require(p['room'] not in challenge_rooms, at, 'a puzzle room cannot host a challenge')
        for cp in mods['challenge']['entities']['checkpoints']:
            # Committing a checkpoint in a puzzle room resets the room with the player on its start cell, so a
            # save never holds transient grid state.
            require(cp['room'] != p['room'] or cp['position_m'] == [p['start'][0] + 0.5, 0, p['start'][1] + 0.5],
                    'checkpoint/' + cp['id'], 'a checkpoint in a puzzle room must sit on the puzzle start cell centre')
        seen_rooms.add(p['room'])
        room = rooms[p['room']]
        cols, rows = room['grid_size']
        require(cols <= LIMITS['cells'] and rows <= LIMITS['cells'], at, 'puzzle rooms are at most 16 x 16 cells')
        require(len(p['layout']) == rows and all(len(row) == cols for row in p['layout']), at,
                'layout needs one row per metre of room depth and one column per metre of width')

        def terrain(cell):
            return p['layout'][cell[1]][cell[0]]

        def inside(cell, where):
            require(0 <= cell[0] < cols and 0 <= cell[1] < rows, at + '/' + where, 'cell outside room grid')
        occupied, kinds = {}, {}
        for e in p['elements']:
            require(e['id'] not in element_ids, at + '/' + e['id'], 'element IDs must be unique across all puzzles')
            require(e['id'] != 'goal', at + '/goal', 'goal is a reserved element id')
            element_ids.add(e['id'])
            kinds[e['id']] = e
            cells = [tuple(c) for c in e['cells']] if e['kind'] == 'bridge' else [tuple(e['cell'])]
            for cell in cells:
                inside(cell, e['id'])
                want = '_' if e['kind'] == 'bridge' else '.'
                require(terrain(cell) == want, at + '/' + e['id'], 'element must stand on ' + ('a pit' if want == '_' else 'floor'))
                other = occupied.get(cell)
                pair = sorted([e['kind'], kinds[other]['kind']]) if other else None
                require(other is None or pair == ['block', 'plate'], at + '/' + e['id'], 'cell already holds ' + str(other))
                occupied[cell] = e['id']
        blocks = [e for e in p['elements'] if e['kind'] == 'block']
        timed = [e for e in p['elements'] if e['kind'] == 'timed_gate']
        require(len(blocks) <= LIMITS['blocks'], at, 'at most 3 blocks per puzzle')
        require(len(timed) <= LIMITS['timed_gates'], at, 'at most 2 timed gates per puzzle')
        for g in timed:
            steps = g['open_ticks'] // config['step_ticks']
            require(1 <= steps <= LIMITS['open_steps'], at + '/' + g['id'], 'open_ticks / step_ticks must be 1 to 15 solver steps')
        bits = sum({'switch': 1, 'torch': 1, 'orb': 1, 'door': 1, 'bridge': 1, 'timed_gate': 2}.get(e['kind'], 0)
                   + (1 if e['kind'] == 'plate' and e['mode'] == 'latch' else 0) for e in p['elements'])
        require(bits <= LIMITS['stateful_bits'], at, 'at most 23 stateful element bits per puzzle')
        start = tuple(p['start'])
        inside(start, 'start')
        require(terrain(start) == '.', at + '/start', 'start must be floor')
        require(start not in occupied or kinds[occupied[start]]['kind'] == 'plate', at + '/start', 'start cell is occupied')
        for door in room['doors']:
            cell = door_cell(door, room)
            require(terrain(cell) == '.', at + '/door/' + door['id'], 'door exit cell must be floor')
            require(cell not in occupied, at + '/door/' + door['id'], 'door exit cell must be clear of elements')
        latch_ids = {e['id'] for e in p['elements'] if e['kind'] in ('switch', 'plate') and e['mode'] == 'latch'}
        transient = {e['id'] for e in p['elements'] if e['kind'] in SOURCES} - latch_ids

        def link(value, where, sources=SOURCES, invertible=True, timed_gate=False):
            require(value['at_least'] <= len(value['of']), at + '/' + where, 'at_least exceeds linked sources')
            for sid in value['of']:
                require(sid in kinds and kinds[sid]['kind'] in sources, at + '/' + where,
                        'links reference only ' + ', '.join(sources) + ' elements: ' + sid)
            if value['invert']:
                require(invertible and all(s in transient for s in value['of']), at + '/' + where,
                        'inverted links may reference only non-latching sources')
            if timed_gate:
                require(not set(value['of']) & latch_ids, at + '/' + where, 'timed gates react to edges; latch sources are not admitted')
        for e in p['elements']:
            if e['kind'] in ('bridge', 'door', 'timed_gate'):
                link(e['when'], e['id'], timed_gate=e['kind'] == 'timed_gate')
            if e['kind'] == 'lock':
                for item in e['accepts']:
                    require(item in items, at + '/' + e['id'], 'missing accepted item ' + item)
            if e['kind'] == 'key':
                require(e['item'] in items, at + '/' + e['id'], 'missing key item ' + e['item'])
                require(e['item'] not in key_items, at + '/' + e['id'], 'a key item has exactly one pickup')
                key_items.append(e['item'])
            if e['kind'] == 'shutter':
                dx, dy = DIRS[e['dir']]
                for cell in ((e['cell'][0] - dx, e['cell'][1] - dy), (e['cell'][0] + dx, e['cell'][1] + dy)):
                    require(0 <= cell[0] < cols and 0 <= cell[1] < rows and terrain(cell) == '.' and cell not in occupied,
                            at + '/' + e['id'], 'a one-way shutter needs clear floor on both sides')
        goal = p['goal']
        link(goal['when'], 'goal', GOAL_SOURCES, invertible=False)
        for oid in goal['opens']:
            require(oid in kinds and kinds[oid]['kind'] in ('door', 'timed_gate', 'bridge', 'shutter'), at + '/goal',
                    'goal.opens may name doors, timed gates, bridges or shutters')
        for item in goal['rewards']['items']:
            require(item in items, at + '/goal', 'missing reward item ' + item)
            require(item not in rewards, at + '/goal', 'a reward item has one owner')
            rewards.append(item)
        for hid in p['hint']:
            require(hid in kinds and kinds[hid]['kind'] in INTERACTIVE, at + '/hint', 'hint must name an interactive element')
    exclusive = set(rewards) | set(key_items)
    require(not exclusive & set(spec['start']['inventory']), 'start', 'key pickups and puzzle rewards cannot be initially owned')
    challenge_rewards = {i for c in mods['challenge']['entities']['challenges'] for i in c['rewards']['items']}
    require(not exclusive & challenge_rewards, 'puzzle', 'a key or puzzle reward cannot also be a challenge reward')

    def walk(value, path):
        # Key pickups and rewards have exactly one producer; rewards are permanent.
        if isinstance(value, dict):
            for key, child in value.items():
                require(not (key == 'give' and child in exclusive), path, 'key pickups and puzzle rewards have one producer: ' + str(child))
                require(not (key == 'take' and child in rewards), path, 'puzzle reward items are permanent and cannot be taken')
                walk(child, path + '/' + key)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, path + '/' + str(i))
    for key in ('interactions', 'dialogues', 'collectibles'):
        walk(spec.get(key, []), key)
    return puzzle_ids


# --------------------------------------------------------------------------- micro rules


class Ctx(object):
    """Permanent facts relevant to one puzzle, fixed during a per-visit search."""
    __slots__ = ('taken', 'opened', 'latched', 'solved', 'inventory')

    def __init__(self, taken=(), opened=(), latched=(), solved=False, inventory=()):
        self.taken = frozenset(taken)
        self.opened = frozenset(opened)
        self.latched = frozenset(latched)
        self.solved = bool(solved)
        self.inventory = frozenset(inventory)

    def key(self):
        return (tuple(sorted(self.taken)), tuple(sorted(self.opened)), tuple(sorted(self.latched)),
                self.solved, tuple(sorted(self.inventory)))

    def after(self, events, grid):
        taken, opened, latched, inv, solved = set(self.taken), set(self.opened), set(self.latched), set(self.inventory), self.solved
        for ev in events:
            if ev[0] == 'take':
                taken.add(ev[1])
                inv.add(grid.el[ev[1]]['item'])
            elif ev[0] == 'unlock':
                opened.add(ev[1])
                inv.discard(ev[2])
            elif ev[0] == 'latch':
                latched.add(ev[1])
            elif ev[0] == 'solve':
                solved = True
        return Ctx(taken, opened, latched, solved, inv & grid.relevant_items)


def event_token(ev):
    return '.'.join(ev)


def events_key(events):
    return '+'.join(sorted(event_token(e) for e in events))


class Grid(object):
    """One compiled puzzle room."""

    def __init__(self, room, puzzle, config):
        self.id = puzzle['id']
        self.room = room['id']
        self.name = puzzle['name']
        self.cols, self.rows = room['grid_size']
        self.layout = puzzle['layout']
        self.persistent = puzzle['persistence'] == 'persistent'
        self.resettable = puzzle['reset'] == 'hold'
        self.max_states = puzzle['max_states']
        self.hint = list(puzzle['hint'])
        self.goal = puzzle['goal']
        self.opens = frozenset(puzzle['goal']['opens'])
        self.el = {e['id']: e for e in puzzle['elements']}
        self.ids = sorted(self.el)
        self.blocks = [i for i in self.ids if self.el[i]['kind'] == 'block']
        self.timed = [i for i in self.ids if self.el[i]['kind'] == 'timed_gate']
        self.step_ticks = config['step_ticks']
        self.open_steps = {i: self.el[i]['open_ticks'] // self.step_ticks for i in self.timed}
        self.cell_of, self.bridge_at = {}, {}
        for i in self.ids:
            e = self.el[i]
            if e['kind'] == 'bridge':
                for c in e['cells']:
                    self.bridge_at[tuple(c)] = i
            elif e['kind'] != 'block':
                self.cell_of[tuple(e['cell'])] = i
        self.bits = []
        for i in self.ids:
            k, e = self.el[i]['kind'], self.el[i]
            if k in ('switch', 'torch', 'orb') or (k == 'plate' and e['mode'] == 'latch'):
                self.bits.append((i, 'on'))
            elif k in ('door', 'bridge'):
                self.bits.append((i, 'open'))
            elif k == 'timed_gate':
                self.bits.extend([(i, 'open'), (i, 'prev')])
        self.bit = {b: 1 << n for n, b in enumerate(self.bits)}
        self.ordered = [i for i in self.ids if self.el[i]['kind'] == 'torch' and self.el[i]['order'] > 0]
        self.ordered_mask = 0
        for i in self.ordered:
            self.ordered_mask |= self.bit[(i, 'on')]
        self.latchable = frozenset(i for i in self.ids if self.persistent and self.el[i]['kind'] in ('switch', 'plate')
                                   and self.el[i]['mode'] == 'latch')
        self.exits = {d['id']: door_cell(d, room) for d in room['doors']}
        self.exit_cells = {}
        for did, cell in sorted(self.exits.items()):
            self.exit_cells.setdefault(cell, []).append(did)
        self.start = tuple(puzzle['start'])
        self.locks = [i for i in self.ids if self.el[i]['kind'] == 'lock']
        self.relevant_items = frozenset(item for i in self.locks for item in self.el[i]['accepts'])

    # ---- context and packing
    def ctx(self, solved, taken, opened, latched, inventory):
        return Ctx([x for x in taken if x in self.el], [x for x in opened if x in self.el],
                   [x for x in latched if x in self.latchable], self.id in solved,
                   [i for i in inventory if i in self.relevant_items])

    def index(self, cell):
        return cell[1] * self.cols + cell[0]

    def key(self, st):
        """Exact 63-bit state key, identical in rules.gd: player | blocks << 8n | timers << 32 | bits << 40."""
        p, blocks, on, tm = st
        k = self.index(p)
        for n, b in enumerate(blocks):
            k |= self.index(b) << (8 * (n + 1))
        for n, t in enumerate(tm):
            k |= t << (32 + 4 * n)
        return k | (on << 40)

    # ---- static queries
    def inside(self, c):
        return 0 <= c[0] < self.cols and 0 <= c[1] < self.rows

    def terrain(self, c):
        return self.layout[c[1]][c[0]]

    def has(self, st, eid, role='on'):
        return bool(st[2] & self.bit[(eid, role)])

    def weight_at(self, st, cell):
        if st[0] == cell:
            return 1
        return 2 if cell in st[1] else 0

    def source(self, st, ctx, sid):
        e = self.el[sid]
        if e['kind'] == 'lock':
            return sid in ctx.opened
        if e['kind'] == 'plate':
            if e['mode'] == 'latch' and (self.has(st, sid) or sid in ctx.latched):
                return True
            return self.weight_at(st, tuple(e['cell'])) >= e['weight']
        return sid in ctx.latched or self.has(st, sid)

    def link(self, st, ctx, link):
        count = sum(1 for sid in link['of'] if self.source(st, ctx, sid))
        return (count >= link['at_least']) != link['invert']

    def floor_like(self, st, cell):
        if not self.inside(cell):
            return False
        t = self.terrain(cell)
        if t == '#':
            return False
        if t == '_':
            b = self.bridge_at.get(cell)
            return b is not None and self.has(st, b, 'open')
        return True

    def solid(self, st, ctx, cell):
        """True if the element at ``cell`` blocks movement and strikes (blocks are checked separately)."""
        eid = self.cell_of.get(cell)
        if eid is None:
            return False
        k = self.el[eid]['kind']
        if k in SOLID:
            return True
        if k == 'lock':
            return eid not in ctx.opened
        if k in ('door', 'timed_gate'):
            return not self.has(st, eid, 'open')
        return False

    def walkable(self, st, ctx, cell):
        return self.floor_like(st, cell) and not self.solid(st, ctx, cell) and cell not in st[1]

    def block_free(self, st, ctx, cell, player_leaves=False):
        return (self.floor_like(st, cell) and not self.solid(st, ctx, cell)
                and cell not in st[1] and (player_leaves or cell != st[0]))

    def occupied(self, st, cell):
        return st[0] == cell or cell in st[1]

    @staticmethod
    def adjacent(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    def strike_clear(self, st, ctx, a, b):
        dx = (b[0] > a[0]) - (b[0] < a[0])
        dy = (b[1] > a[1]) - (b[1] < a[1])
        c = (a[0] + dx, a[1] + dy)
        while c != b:
            if self.terrain(c) == '#' or c in st[1] or self.solid(st, ctx, c):
                return False
            c = (c[0] + dx, c[1] + dy)
        return True

    # ---- actions (no time passes inside apply)
    def apply(self, st, ctx, token):
        p, blocks, on, tm = st
        if token.startswith('move.'):
            d = token[5:]
            dx, dy = DIRS[d]
            t = (p[0] + dx, p[1] + dy)
            if not self.inside(t):
                return None
            eid = self.cell_of.get(t)
            if eid is not None and self.el[eid]['kind'] == 'shutter':
                sd = self.el[eid]['dir']
                if d != sd and not (ctx.solved and eid in self.opens and d == OPPOSITE[sd]):
                    return None
                t2 = (t[0] + dx, t[1] + dy)
                if not self.walkable(st, ctx, t2):
                    return None
                return (t2, blocks, on, tm), ()
            if t in blocks:
                n = blocks.index(t)
                t2 = (t[0] + dx, t[1] + dy)
                if not self.block_free(st, ctx, t2):
                    return None
                nb = list(blocks)
                nb[n] = t2
                return (t, tuple(nb), on, tm), ()
            if not self.walkable(st, ctx, t):
                return None
            return (t, blocks, on, tm), ()
        if token.startswith('pull.'):
            dx, dy = DIRS[token[5:]]
            t = (p[0] + dx, p[1] + dy)
            b = (p[0] - dx, p[1] - dy)
            if b not in blocks or not self.el[self.blocks[blocks.index(b)]]['pull']:
                return None
            if not self.walkable(st, ctx, t) or not self.block_free(st, ctx, p, player_leaves=True):
                return None
            nb = list(blocks)
            nb[blocks.index(b)] = p
            return (t, tuple(nb), on, tm), ()
        if token.startswith('act.'):
            return self.act(st, ctx, token[4:])
        if token == 'wait':
            return (st, ()) if any(tm) else None
        return None

    def act(self, st, ctx, eid):
        if eid not in self.el:
            return None
        p, blocks, on, tm = st
        e = self.el[eid]
        k = e['kind']
        if k not in ACTABLE:
            return None
        cell = tuple(e['cell'])
        if k == 'switch':
            if not self.adjacent(p, cell):
                return None
            bit = self.bit[(eid, 'on')]
            if e['mode'] == 'latch':
                if on & bit or eid in ctx.latched:
                    return None
                return (p, blocks, on | bit, tm), ((('latch', eid),) if eid in self.latchable else ())
            return (p, blocks, on ^ bit, tm), ()
        if k == 'torch':
            if not self.adjacent(p, cell) or on & self.bit[(eid, 'on')]:
                return None
            if e['order'] > 0 and any(self.el[o]['order'] < e['order'] and not on & self.bit[(o, 'on')] for o in self.ordered):
                return (p, blocks, on & ~self.ordered_mask, tm), ()
            return (p, blocks, on | self.bit[(eid, 'on')], tm), ()
        if k == 'lock':
            if not self.adjacent(p, cell) or eid in ctx.opened:
                return None
            held = [i for i in sorted(e['accepts']) if i in ctx.inventory]
            if not held:
                return None
            return st, (('unlock', eid, held[0]),)
        if k == 'key':
            if eid in ctx.taken or not self.adjacent(p, cell):
                return None
            return st, (('take', eid),)
        # orb: struck along a row or column within reach, first obstacle on the ray
        if not (p[0] == cell[0] or p[1] == cell[1]) or p == cell:
            return None
        if abs(p[0] - cell[0]) + abs(p[1] - cell[1]) > e['reach'] or not self.strike_clear(st, ctx, p, cell):
            return None
        return (p, blocks, on ^ self.bit[(eid, 'on')], tm), ()

    def settle(self, st, ctx, steps=1):
        """Time passes; latch plates, doors, bridges and gates update in sorted id order; goal is checked."""
        p, blocks, on, tm = st
        tm = [max(0, t - steps) for t in tm]
        events = []
        for i in self.ids:
            e = self.el[i]
            if e['kind'] == 'plate' and e['mode'] == 'latch':
                if self.weight_at(st, tuple(e['cell'])) >= e['weight'] and not on & self.bit[(i, 'on')] and i not in ctx.latched:
                    on |= self.bit[(i, 'on')]
                    if i in self.latchable:
                        events.append(('latch', i))
        cur = (p, blocks, on, tuple(tm))
        for i in self.ids:
            e = self.el[i]
            k = e['kind']
            if k not in ('door', 'bridge', 'timed_gate'):
                continue
            forced = ctx.solved and i in self.opens
            ob = self.bit[(i, 'open')]
            was = bool(on & ob)
            value = self.link(cur, ctx, e['when'])
            if k == 'door':
                now = value or forced or (was and self.occupied(cur, tuple(e['cell'])))
            elif k == 'bridge':
                if e['mode'] == 'latch':
                    now = was or value or forced
                else:
                    now = value or forced or (was and any(self.occupied(cur, tuple(c)) for c in e['cells']))
            else:
                n = self.timed.index(i)
                pb = self.bit[(i, 'prev')]
                if value and not on & pb:
                    tm[n] = self.open_steps[i]
                now = tm[n] > 0 or forced or (was and self.occupied(cur, tuple(e['cell'])))
                on = (on | pb) if value else (on & ~pb)
            on = (on | ob) if now else (on & ~ob)
            cur = (p, blocks, on, tuple(tm))
        if not ctx.solved and self.link(cur, ctx, self.goal['when']):
            events.append(('solve',))
        return cur, tuple(events)

    def advance(self, st, ctx, token):
        out = self.apply(st, ctx, token)
        if out is None:
            return None
        nxt, events = out
        nxt, more = self.settle(nxt, ctx, 1)
        return nxt, events + more

    def canonical(self, ctx, entry=''):
        p = self.start if entry == '' else self.exits[entry]
        blocks = tuple(tuple(self.el[b]['cell']) for b in self.blocks)
        on = 0
        for i in ctx.latched:
            on |= self.bit[(i, 'on')]
        return self.settle((p, blocks, on, tuple(0 for _ in self.timed)), ctx, 0)

    def tokens(self, st):
        out = ['move.' + d for d in ORDER] + ['pull.' + d for d in ORDER] + ['act.' + i for i in self.ids if self.el[i]['kind'] in ACTABLE]
        if any(st[3]):
            out.append('wait')
        return out

    def successors(self, st, ctx):
        for token in self.tokens(st):
            out = self.advance(st, ctx, token)
            if out is not None:
                yield token, out[0], out[1]

    # ---- bounded per-visit search with fixed permanent facts
    def summary(self, ctx, entry='', cap=None):
        """Exhaustive search of one visit with facts fixed.

        A transition that changes a permanent fact (take, unlock, latch, solve) leaves this graph: it is
        recorded (all sources, shortest route, post-event micro states) but not expanded. ``reset`` (hold R,
        ``reset: hold`` only) returns to the canonical state and is not stored as a graph edge.
        """
        cap = cap or self.max_states
        root, root_events = self.canonical(ctx, entry)
        seen = {self.key(root): 0}
        states, forward = [root], [[]]
        parent: list = [None]
        edges, exits = {}, {}
        open_ever = set()
        if root_events:
            edges[events_key(root_events)] = {'events': root_events, 'route': [], 'sources': [0], 'posts': [root], 'token': ''}
        complete = True
        i = 0
        while i < len(states):
            st = states[i]
            for did in self.exit_cells.get(st[0], ()):
                exits.setdefault(did, i)
            for (eid, role) in self.bits:
                if role == 'open' and st[2] & self.bit[(eid, role)]:
                    open_ever.add(eid)
            for token, nxt, events in self.successors(st, ctx):
                if events:
                    key = events_key(events)
                    row = edges.get(key)
                    if row is None:
                        row = edges[key] = {'events': events, 'from': i, 'token': token, 'sources': [], 'posts': []}
                    if not row['sources'] or row['sources'][-1] != i:
                        row['sources'].append(i)
                    row['posts'].append(nxt)
                    continue
                k2 = self.key(nxt)
                j = seen.get(k2)
                if j is None:
                    if len(states) >= cap:
                        complete = False
                        break
                    j = len(states)
                    seen[k2] = j
                    states.append(nxt)
                    parent.append((i, token))
                    forward.append([])
                forward[i].append(j)
            if not complete:
                break
            i += 1

        def route(j):
            out = []
            while parent[j] is not None:
                out.append(parent[j][1])
                j = parent[j][0]
            return list(reversed(out))
        for row in edges.values():
            if 'route' not in row:
                row['route'] = route(row['from']) + [row['token']]
        return {'root_events': root_events, 'states': states, 'parent': parent, 'forward': forward, 'seen': seen,
                'edges': edges, 'exits': {d: route(j) for d, j in exits.items()}, 'exit_states': exits,
                'complete': complete, 'open_ever': open_ever, 'route': route}

    def returns(self, summary):
        """Indices of states that can return to the canonical state without reset."""
        n = len(summary['states'])
        reverse = [[] for _ in range(n)]
        for a, outs in enumerate(summary['forward']):
            for b in outs:
                reverse[b].append(a)
        seen = {0}
        queue = deque([0])
        while queue:
            for a in reverse[queue.popleft()]:
                if a not in seen:
                    seen.add(a)
                    queue.append(a)
        return seen

    def reaches(self, start, ctx, goal_key, cap):
        """Bounded forward search (facts fixed, no reset) from ``start`` to a state with key ``goal_key``."""
        k0 = self.key(start)
        if k0 == goal_key:
            return True
        seen = {k0}
        queue = deque([start])
        while queue:
            st = queue.popleft()
            for token, nxt, events in self.successors(st, ctx):
                if events:
                    continue
                k = self.key(nxt)
                if k == goal_key:
                    return True
                if k not in seen:
                    if len(seen) >= cap:
                        return None
                    seen.add(k)
                    queue.append(nxt)
        return False

    def visit_route(self, ctx, entry='', cap=None):
        """Shortest continuous route of one visit from entry to the ``solve`` event, letting permanent facts
        change on the way (keys taken, locks opened, latches set). Returns the token list or None."""
        cap = cap or self.max_states
        root, events = self.canonical(ctx, entry)
        if any(ev[0] == 'solve' for ev in events):
            return []
        if events:
            ctx = ctx.after(events, self)
            root = self.settle(root, ctx, 0)[0]
        start = (self.key(root), ctx.key())
        seen = {start}
        queue = deque([(root, ctx, [])])
        while queue:
            st, c, path = queue.popleft()
            for token, nxt, evs in self.successors(st, c):
                if any(ev[0] == 'solve' for ev in evs):
                    return path + [token]
                c2 = c.after(evs, self) if evs else c
                if evs:
                    nxt, more = self.settle(nxt, c2, 0)
                    if any(ev[0] == 'solve' for ev in more):
                        return path + [token]
                    if more:
                        c2 = c2.after(more, self)
                k = (self.key(nxt), c2.key())
                if k in seen:
                    continue
                if len(seen) >= cap:
                    return None
                seen.add(k)
                queue.append((nxt, c2, path + [token]))
        return None

    def describe(self, st):
        """Plain diagnostic for a counterexample micro state (never a synthetic physical trace)."""
        return {'player': list(st[0]), 'blocks': {b: list(c) for b, c in zip(self.blocks, st[1])},
                'on': sorted(i for (i, role) in self.bits if role == 'on' and self.has(st, i)),
                'open': sorted(i for (i, role) in self.bits if role == 'open' and self.has(st, i, 'open')),
                'timers': {g: t for g, t in zip(self.timed, st[3]) if t}}


def route_plan(grid, state, ctx, target, entry='', cap=None):
    """Shortest micro route from a concrete state to ``target(token, nxt, events)`` with facts fixed until the
    final transition; ``reset`` (hold R) returns to the visit's canonical state for ``reset: hold`` puzzles.
    Returns a list of (token, state, events); [] if ``target('', state, ())`` already holds; None if none."""
    if target('', state, ()):
        return []
    cap = cap or grid.max_states
    seen = {grid.key(state)}
    queue = deque([(state, [])])
    canon, canon_events = grid.canonical(ctx, entry)
    while queue:
        st, path = queue.popleft()
        options = list(grid.successors(st, ctx))
        if grid.resettable and not canon_events and grid.key(st) != grid.key(canon):
            options.append(('reset', canon, ()))
        for token, nxt, events in options:
            if target(token, nxt, events):
                return path + [(token, nxt, events)]
            if events:
                continue
            k = grid.key(nxt)
            if k in seen:
                continue
            if len(seen) >= cap:
                return None
            seen.add(k)
            queue.append((nxt, path + [(token, nxt, events)]))
    return None
