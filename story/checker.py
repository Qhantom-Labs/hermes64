"""BFS reachability plus reverse reachability; fail closed on resource limits."""
from collections import deque
from .engine import Engine
from .compiler import canonical
from .errors import SpecError, StateError


class Search:
    def __init__(self, engine, max_states=100000):
        if type(max_states) is not int or max_states < 1:
            raise SpecError('max_states must be a positive integer')
        self.engine = engine
        self.states = [engine.start]
        self.index = {engine.start: 0}
        self.parents = [None]
        self.reverse = [[]]
        self.terminals = {}
        self.ambiguous = []
        self.dead_ends = []
        self.complete = True
        self.edges = 0
        queue = deque([0])
        while queue:
            i = queue.popleft()
            st = self.states[i]
            endings = engine.endings(st)
            if endings:
                if len(endings) > 1:
                    self.ambiguous.append(i)
                else:
                    self.terminals[i] = endings[0]
                continue
            actions = engine.actions(st)
            if not any(a.state != st for a in actions):
                self.dead_ends.append(i)
            for a in actions:
                j = self.index.get(a.state)
                if j is None:
                    if len(self.states) >= max_states:
                        self.complete = False
                        return
                    j = len(self.states)
                    self.index[a.state] = j
                    self.states.append(a.state)
                    self.parents.append((i, a.id, a.label))
                    self.reverse.append([])
                    queue.append(j)
                self.reverse[j].append(i)
                self.edges += 1

    def witness(self, index):
        steps = []
        while self.parents[index] is not None:
            parent, aid, label = self.parents[index]
            st = self.states[index]
            steps.append({'action': aid, 'label': label, 'location': st.location,
                          'tide': {'state': st.tide, 'tick': st.tick}})
            index = parent
        return list(reversed(steps))

    def winning_states(self):
        winning = set(self.terminals)
        queue = deque(sorted(winning))
        while queue:
            for parent in self.reverse[queue.popleft()]:
                if parent not in winning:
                    winning.add(parent)
                    queue.append(parent)
        return winning


def condition_sites(game):
    for c in game.get('collectibles', []):
        yield 'collectibles/' + c['id'], c['conditions'], c['room'], None
    for a in game['interactions']:
        yield 'interactions/' + a['id'], a['conditions'], a['room'], None
    for r in game['rooms']:
        for d in r['doors']:
            yield 'rooms/{}/doors/{}'.format(r['id'], d['id']), d['conditions'], r['id'], None
    for d in game['dialogues']:
        for n in d['nodes']:
            yield 'dialogues/{}/{}'.format(d['id'], n['id']), n['conditions'], None, (d['id'], n['id'])
            for c in n['choices']:
                yield 'dialogues/{}/{}/{}'.format(d['id'], n['id'], c['id']), n['conditions'] + c['conditions'], None, (d['id'], n['id'])
    for kind in ('quests', 'endings'):
        for x in game[kind]:
            yield kind + '/' + x['id'], x['conditions'], None, None


def diagnose(search):
    e = search.engine
    result = []
    for path, conditions, room, cursor in condition_sites(e.game):
        candidates = [st for st in search.states if (room is None or st.location == room) and
                      (cursor is None or dict(st.dialogue).get(cursor[0]) == cursor[1])]
        if any(e.matches(conditions, st) for st in candidates):
            continue
        missing = []
        for c in conditions:
            if not any(e.matches([c], st) for st in search.states):
                missing.append({'condition': c, 'reason': 'required value never occurs in reachable states; no reachable prerequisite producer'})
        result.append({'path': path, 'missing': missing,
                       'reason': 'missing prerequisites' if missing else 'no jointly reachable state satisfies these conditions in this location/dialogue context'})
    return result


def check_exhaustive(game, max_states=100000):
    from .modules import enabled
    if enabled(game):
        from .modules.analysis import check
        return check(game, max_states)
    try:
        engine = Engine(game)
        search = Search(engine, max_states)
    except (SpecError, StateError) as exc:
        return {'status': 'invalid', 'complete': False, 'reason': str(exc), 'endings': {},
                'softlock_count': None, 'dead_end_count': None, 'missing_prerequisites': []}
    endings = {}
    for ending in game['endings']:
        matching = [i for i, eid in search.terminals.items() if eid == ending['id']]
        if matching:
            i = matching[0]
            endings[ending['id']] = {'reachable': True, 'witness': search.witness(i),
                                      'final_state': engine.to_dict(search.states[i])}
        else:
            endings[ending['id']] = {'reachable': False if search.complete else None, 'witness': [],
                                      'reason': 'no reachable terminal satisfies ending conditions' if search.complete else 'search limit; reachability unknown'}
    complete = search.complete
    winning = search.winning_states() if complete else set()
    softlocks = [i for i, st in enumerate(search.states) if i not in winning and not engine.endings(st)] if complete else []
    diagnostics = diagnose(search) if complete else []
    ambiguous = [{'state': engine.to_dict(search.states[i]), 'endings': engine.endings(search.states[i]),
                  'witness': search.witness(i)} for i in search.ambiguous[:10]]
    good = all(x['reachable'] for x in endings.values()) and not softlocks and not search.ambiguous
    status = ('proved' if good else 'rejected') if complete else 'inconclusive'
    report = {'status': status, 'complete': complete, 'game_hash': game['game_hash'],
              'reason': 'exhaustive reachable-state graph' if complete else 'state cap reached; no completeness or softlock proof',
              'state_count': len(search.states), 'edge_count': search.edges, 'state_cap': max_states,
              'endings': endings, 'softlock_count': len(softlocks) if complete else None,
              'dead_end_count': len(search.dead_ends) if complete else None,
              'softlocks': [{'state': engine.to_dict(search.states[i]), 'reason': 'no ending is reachable from this state',
                             'witness': search.witness(i)} for i in softlocks[:10]],
              'dead_ends': [{'state': engine.to_dict(search.states[i]), 'reason': 'no state-changing successor',
                            'witness': search.witness(i)} for i in search.dead_ends[:10]] if complete else [],
              'ambiguous_terminal_count': len(search.ambiguous), 'ambiguous_terminals': ambiguous,
              'missing_prerequisites': diagnostics}
    from .extensions import extended
    if extended(game):
        from .collectible_checks import concrete_obligations
        return concrete_obligations(search, report)
    return report


def check_game(game, max_states=100000, strategy='auto', max_bdd_nodes=200000):
    from .modules import enabled
    if enabled(game):
        from .modules.analysis import check, failure
        if strategy not in ('auto', 'exhaustive'):
            return failure('STORY 1.2 requires exact module analysis; symbolic strategy is unsupported')
        return check(game, max_states)
    from .extensions import extended
    if strategy == 'symbolic' or (strategy == 'auto' and extended(game)):
        from .symbolic import check_symbolic
        return check_symbolic(game, max_states, max_bdd_nodes)
    if strategy not in ('auto', 'exhaustive'):
        return {'status': 'invalid', 'complete': False, 'reason': 'unknown checker strategy'}
    return check_exhaustive(game, max_states)
