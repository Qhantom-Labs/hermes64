"""STORY 1.3 macro semantics: the unchanged 1.2 module engine on the lowered build, plus puzzle transitions.

Permanent puzzle facts are reserved flags in the 1.2 state; the only extra component is ``entry`` (the door
the current puzzle-room visit started from, '' = start cell). Puzzle transitions are deterministic and
executable (a proved grid route), so they are exposed to both the gameplay and the analysis engines; only
challenge outcomes stay analysis-only, exactly as in 1.2.
"""
from typing import NamedTuple
from ..compiler import digest
from ..engine import Template
from ..errors import StateError
from ..modules.model import ModuleEngine, ModuleState
from . import fact_flag, parse_flag
from .compiler import validate_game, lowered_game
from .lowering import lower_state, raise_state
from .rules import Grid, event_token, fact_rows


# Per-visit grid summaries depend only on (room doors/size, puzzle data, config, entry, permanent facts), so
# repeated proofs of the same build (save validation, edit baselines) reuse them. Bounded, in-process only.
_SUMMARIES = {}
_SUMMARY_LIMIT = 64


def cached_summary(signature, entry, ctx_key, compute):
    key = (signature, entry, ctx_key)
    if key not in _SUMMARIES:
        value = compute()
        while len(_SUMMARIES) >= _SUMMARY_LIMIT:
            _SUMMARIES.pop(next(iter(_SUMMARIES)))
        _SUMMARIES[key] = value
    return _SUMMARIES[key]


class PuzzleState(NamedTuple):
    location: str
    inventory: tuple
    flags: tuple
    dialogue: tuple
    tide: str
    tick: int
    collected: tuple
    modules: ModuleState
    entry: str


class PuzzleEngine(ModuleEngine):
    abstract_outcomes = False

    def __init__(self, game):
        validate_game(game)
        self.game13 = game
        low = lowered_game(game)
        rooms = {r['id']: r for r in low['rooms']}
        config = game['puzzle']['config']
        self.grids = {p['id']: Grid(rooms[p['room']], p, config) for p in game['puzzle']['puzzles']}
        self.signatures = {p['id']: digest({'room': {k: rooms[p['room']][k] for k in ('id', 'grid_size', 'doors')},
                                            'puzzle': p, 'config': config}) for p in game['puzzle']['puzzles']}
        self.room_grid = {g.room: g for g in self.grids.values()}
        self.rows = fact_rows({'entities': {'puzzles': game['puzzle']['puzzles']}})
        self.summaries, self.summary_order = {}, []
        super().__init__(low)

    # ---- state conversion (1.3 dicts outside, lowered tuples inside)
    def from_dict(self, data):
        if isinstance(data, dict) and isinstance(data.get('modules'), dict) and 'puzzle' in data['modules']:
            low, entry = lower_state(data, self.rows)
            if entry:
                grid = self.room_grid.get(low.get('location'))
                if grid is None or entry not in grid.exits:
                    raise StateError('state/modules/puzzle/entry: entry must be a door of the current puzzle room')
        else:
            low, entry = data, ''
        base = super().from_dict(low)
        return PuzzleState(*base, entry)

    def to_dict(self, st):
        return raise_state(super().to_dict(st), st.entry)

    # ---- puzzle facts (reserved flags)
    def facts(self, st):
        out = {'solved': [], 'taken': [], 'opened': [], 'latched': []}
        for name, value in st.flags:
            parsed = parse_flag(name)
            if parsed is not None and value:
                out[parsed[0]].append(parsed[1])
        return out

    def context(self, st, grid):
        f = self.facts(st)
        return grid.ctx(f['solved'], f['taken'], f['opened'], f['latched'], st.inventory)

    def summary(self, st, grid):
        ctx = self.context(st, grid)
        key = (grid.id, st.entry, ctx.key())
        if key not in self.summaries:
            self.summaries[key] = (ctx, cached_summary(self.signatures[grid.id], st.entry, ctx.key(),
                                                       lambda: grid.summary(ctx, st.entry)))
            self.summary_order.append(key)
        return self.summaries[key][1]

    def apply_events(self, st, grid, events):
        flags, inventory = dict(st.flags), set(st.inventory)
        for ev in events:
            if ev[0] == 'take':
                flags[fact_flag('taken', ev[1])] = True
                inventory.add(grid.el[ev[1]]['item'])
            elif ev[0] == 'unlock':
                flags[fact_flag('opened', ev[1])] = True
                inventory.discard(ev[2])
            elif ev[0] == 'latch':
                flags[fact_flag('latched', ev[1])] = True
            elif ev[0] == 'solve':
                flags[fact_flag('solved', grid.id)] = True
                inventory.update(grid.goal['rewards']['items'])
        return st._replace(flags=tuple(sorted(flags.items())), inventory=tuple(sorted(inventory)))

    def entered(self, st, plan):
        """A door into a puzzle room enters at that door's cell; any other relocation enters at the start
        cell; committing a checkpoint inside a puzzle room resets it with the player on the start cell."""
        out = plan.state
        if out.location == st.location:
            if plan.id.startswith('checkpoint:') and out.location in self.room_grid:
                return out._replace(entry='')
            return out
        entry = ''
        if plan.id.startswith('move:') and out.location in self.room_grid:
            door = plan.id.split(':', 2)[2]
            entry = next(d['to_door'] for d in self.rooms[st.location]['doors'] if d['id'] == door)
        return out._replace(entry=entry)

    def templates(self, st):
        plans = super().templates(st)
        grid = self.room_grid.get(st.location)
        summary = None
        if grid is not None and not st.modules.active and not st.modules.failed and not any(n for d, n in st.dialogue):
            summary = self.summary(st, grid)
        out = []
        for plan in plans:
            if summary is not None and plan.id.startswith('move:') and plan.id.split(':', 2)[2] not in summary['exits']:
                continue  # that exit cell is not reachable on the grid with the current permanent facts
            out.append(plan._replace(state=self.entered(st, plan)))
        if summary is not None and grid is not None:
            for key in sorted(summary['edges']):
                row = summary['edges'][key]
                label = grid.name + ': ' + ', '.join(event_token(e) for e in row['events']) + ' (proved grid route, ' + str(len(row['route'])) + ' steps)'
                out.append(Template('puzzle:' + grid.id + ':' + key, label, self.apply_events(st, grid, row['events'])))
        return sorted(out, key=lambda p: p.id)


class PuzzleAnalysisEngine(PuzzleEngine):
    """Explicit opt-in analysis harness (challenge outcomes become hypothetical actions, as in 1.2)."""
    abstract_outcomes = True
