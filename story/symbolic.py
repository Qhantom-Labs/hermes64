"""Exact symbolic BFS and reverse fixed points over identity-set ROBDDs."""
from collections import deque
from typing import NamedTuple
from .bdd import BDD, BudgetExceeded
from .engine import Engine
from .errors import SpecError, StateError
from .collectible_checks import threshold_sites, threshold_result


class Edge(NamedTuple):
    id: str
    label: str
    target: tuple
    guard: int
    bit: object


class SymbolicSearch:
    def __init__(self, engine, max_bdd_nodes=200000):
        self.engine = engine
        self.ids = tuple(sorted(engine.collectibles))
        self.indices = {cid: i for i, cid in enumerate(self.ids)}
        self.group_indices = {g: tuple(self.indices[c] for c in members) for g, members in engine.groups.items()}
        self.bdd = BDD(len(self.ids), max_bdd_nodes)
        self.reachable, self.layers = {}, []
        self.edges, self.incoming, self.condition_cache, self.ending_cache = {}, {}, {}, {}
        self.complete = False

    def bits(self, st):
        return sum(1 << self.indices[cid] for cid in st.collected)

    def concrete(self, core, bits):
        return core._replace(collected=tuple(cid for i, cid in enumerate(self.ids) if bits & (1 << i)))

    def expression(self, conditions, core):
        key = (core, tuple(tuple(sorted(c.items())) for c in conditions))
        if key in self.condition_cache:
            return self.condition_cache[key]
        b = self.bdd
        out = 1
        for c in conditions:
            if 'collected' in c:
                value = b.var(self.indices[c['collected']])
            elif 'group' in c:
                value = b.threshold(self.group_indices[c['group']], c['at_least'])
            else:
                value = int(self.engine.matches([c], core))
            out = b.intersect(out, value)
            if not out:
                break
        self.condition_cache[key] = out
        return out

    def terminals(self, core):
        if core not in self.ending_cache:
            self.ending_cache[core] = {e['id']: self.expression(e['conditions'], core) for e in self.engine.game['endings']}
        return self.ending_cache[core]

    def terminal_union(self, core):
        out = 0
        for value in self.terminals(core).values():
            out = self.bdd.union(out, value)
        return out

    def transitions(self, core):
        if core in self.edges:
            return self.edges[core]
        b = self.bdd
        nonterminal = b.negate(self.terminal_union(core))
        edges = []
        for plan in self.engine.templates(core):
            target = plan.state._replace(collected=())
            guard = b.intersect(nonterminal, self.expression(plan.before, core))
            after = self.expression(plan.after, target)
            bit = self.indices[plan.collect] if plan.collect else None
            if bit is not None:
                guard = b.intersect(guard, b.negate(b.var(bit)))
                after = b.restrict(after, bit, True)
            if plan.recall:
                guard = b.intersect(guard, b.var(self.indices[plan.recall]))
            guard = b.intersect(guard, after)
            if guard:
                edge = Edge(plan.id, plan.label, target, guard, bit)
                edges.append(edge)
                self.incoming.setdefault(target, []).append((core, edge))
        self.edges[core] = edges
        return edges

    def run(self, max_states=100000):
        if type(max_states) is not int or max_states < 1:
            raise SpecError('max_states must be a positive integer')
        b = self.bdd
        initial = self.engine.start
        core = initial._replace(collected=())
        value = b.assignment(self.bits(initial))
        self.reachable = {core: value}
        frontier = {core: value}
        while frontier:
            self.layers.append(frontier)
            following = {}
            for current in sorted(frontier):
                value = frontier[current]
                for edge in self.transitions(current):
                    image = b.intersect(value, edge.guard)
                    if edge.bit is not None:
                        image = b.add_image(image, edge.bit)
                    fresh = b.difference(image, self.reachable.get(edge.target, 0))
                    if not fresh:
                        continue
                    if edge.target not in self.reachable and len(self.reachable) >= max_states:
                        raise BudgetExceeded('core state cap reached')
                    self.reachable[edge.target] = b.union(self.reachable.get(edge.target, 0), fresh)
                    following[edge.target] = b.union(following.get(edge.target, 0), fresh)
            frontier = following
        self.complete = True
        return self

    def contains(self, st):
        return self.bdd.evaluate(self.reachable.get(st._replace(collected=()), 0), self.bits(st))

    def backward(self, seeds):
        b = self.bdd
        winning = {core: b.intersect(value, self.reachable.get(core, 0)) for core, value in seeds.items() if value}
        queue = deque(sorted(winning))
        queued = set(queue)
        while queue:
            target = queue.popleft()
            queued.remove(target)
            value = winning[target]
            for source, edge in self.incoming.get(target, []):
                if source not in self.reachable:
                    continue
                pre = b.add_preimage(value, edge.bit) if edge.bit is not None else value
                pre = b.intersect(b.intersect(pre, edge.guard), self.reachable[source])
                old = winning.get(source, 0)
                combined = b.union(old, pre)
                if combined != old:
                    winning[source] = combined
                    if source not in queued:
                        queued.add(source)
                        queue.append(source)
        return winning

    def first_point(self, values):
        b = self.bdd
        for depth, layer in enumerate(self.layers):
            for core in sorted(layer):
                both = b.intersect(layer[core], values.get(core, 0))
                if both:
                    return core, b.pick(both), depth
        return None

    def witness(self, core, bits, depth=None):
        b = self.bdd
        if depth is None:
            depth = next(i for i, layer in enumerate(self.layers) if b.evaluate(layer.get(core, 0), bits))
        steps = []
        while depth:
            found = None
            for source, edge in self.incoming.get(core, []):
                if edge.bit is not None and not bits & (1 << edge.bit):
                    continue
                previous = bits & ~(1 << edge.bit) if edge.bit is not None else bits
                if b.evaluate(self.layers[depth - 1].get(source, 0), previous) and b.evaluate(edge.guard, previous):
                    found = source, edge, previous
                    break
            if found is None:
                raise AssertionError('symbolic witness has no concrete predecessor')
            source, edge, previous = found
            steps.append({'action': edge.id, 'label': edge.label, 'location': core.location,
                          'tide': {'state': core.tide, 'tick': core.tick}})
            core, bits, depth = source, previous, depth - 1
        return list(reversed(steps))

    def reachability(self, values):
        point = self.first_point(values)
        if point is None:
            return {'reachable': False, 'witness': [], 'reason': 'no reachable state satisfies this objective'}
        core, bits, depth = point
        return {'reachable': True, 'witness': self.witness(core, bits, depth),
                'final_state': self.engine.to_dict(self.concrete(core, bits))}

    def examples(self, values, reason, limit=10):
        b, out = self.bdd, []
        for core in sorted(values):
            remaining = values[core]
            while remaining and len(out) < limit:
                bits = b.pick(remaining)
                out.append({'state': self.engine.to_dict(self.concrete(core, bits)), 'reason': reason,
                            'witness': self.witness(core, bits)})
                remaining = b.difference(remaining, b.assignment(bits))
            if len(out) == limit:
                break
        return out

    def total(self, values):
        return sum(self.bdd.count(value) for value in values.values())


def report_search(s, max_states, max_bdd_nodes):
    from .checker import condition_sites
    b, e, reachable = s.bdd, s.engine, s.reachable
    seeds, ambiguous, terminal_values = {}, {}, {}
    ending_sets = {ending['id']: {} for ending in e.game['endings']}
    for core, value in reachable.items():
        seen, overlap = 0, 0
        masks = s.terminals(core)
        for mask in masks.values():
            overlap = b.union(overlap, b.intersect(seen, mask))
            seen = b.union(seen, mask)
        terminal_values[core] = b.intersect(value, seen)
        ambiguous[core] = b.intersect(value, overlap)
        seeds[core] = b.difference(terminal_values[core], overlap)
        for eid, mask in masks.items():
            ending_sets[eid][core] = b.difference(b.intersect(value, mask), overlap)
    endings = {eid: s.reachability(values) for eid, values in ending_sets.items()}
    winning = s.backward(seeds)
    nonterminal = {core: b.difference(value, terminal_values[core]) for core, value in reachable.items()}
    softlocks = {core: b.difference(value, winning.get(core, 0)) for core, value in nonterminal.items()}
    dead = {}
    for core, value in nonterminal.items():
        changing = 0
        for edge in s.transitions(core):
            if edge.target != core or edge.bit is not None:
                changing = b.union(changing, edge.guard)
        dead[core] = b.difference(value, changing)
    collectibles, missable = {}, {}
    for cid, index in s.indices.items():
        values = {core: b.intersect(value, b.var(index)) for core, value in reachable.items()}
        collectibles[cid] = s.reachability(values)
        recoverable = s.backward(values)
        unsafe = {core: b.difference(value, recoverable.get(core, 0)) for core, value in nonterminal.items()}
        total = s.total(unsafe)
        if total:
            missable[cid] = {'state_count': total, 'examples': s.examples(unsafe, 'this missing collectible can never be acquired before termination')}
    groups, thresholds = {}, []
    for g in e.game.get('collectible_groups', []):
        mask = b.threshold(s.group_indices[g['id']], g['required'])
        attainable = any(b.intersect(value, mask) for value in reachable.values())
        groups[g['id']] = threshold_result(g['id'], g['required'], len(e.groups[g['id']]), attainable)
    for path, cond in threshold_sites(e.game):
        mask = b.threshold(s.group_indices[cond['group']], cond['at_least'])
        attainable = any(b.intersect(value, mask) for value in reachable.values())
        row = threshold_result(cond['group'], cond['at_least'], len(e.groups[cond['group']]), attainable)
        row['path'] = path
        thresholds.append(row)
    diagnostics = []
    for path, conditions, room, cursor in condition_sites(e.game):
        possible = any(b.intersect(value, s.expression(conditions, core)) for core, value in reachable.items()
                       if (room is None or core.location == room) and (cursor is None or dict(core.dialogue).get(cursor[0]) == cursor[1]))
        if not possible:
            diagnostics.append({'path': path, 'conditions': conditions, 'reason': 'no jointly reachable state satisfies these prerequisites in this context'})
    ambiguous_examples = s.examples(ambiguous, 'multiple endings match')
    for example in ambiguous_examples:
        example['endings'] = e.endings(e.from_dict(example['state']))
    soft_count, dead_count, amb_count = s.total(softlocks), s.total(dead), s.total(ambiguous)
    good = (all(x['reachable'] for x in endings.values()) and all(x['reachable'] for x in collectibles.values()) and
            all(x['attainable'] for x in groups.values()) and all(x['attainable'] for x in thresholds) and
            not soft_count and not amb_count and not missable)
    report = {'status': 'proved' if good else 'rejected', 'complete': True, 'strategy': 'symbolic',
            'reason': 'exact identity-set symbolic fixed point; no optimistic collection closure',
            'game_hash': e.game['game_hash'], 'state_count': s.total(reachable), 'core_state_count': len(reachable),
            'bdd_nodes': len(b.nodes), 'bdd_node_cap': max_bdd_nodes, 'state_cap': max_states, 'bfs_layers': len(s.layers),
            'endings': endings, 'collectibles': collectibles, 'groups': groups, 'thresholds': thresholds,
            'softlock_count': soft_count, 'softlocks': s.examples(softlocks, 'no ending is reachable from this state'),
            'dead_end_count': dead_count, 'dead_ends': s.examples(dead, 'no state-changing successor'),
            'ambiguous_terminal_count': amb_count, 'ambiguous_terminals': ambiguous_examples,
            'permanently_missable': missable, 'permanently_missable_collectible_count': len(missable),
            'missing_prerequisites': diagnostics, 'example_limit': 10}
    report['bdd_nodes'] = len(b.nodes)
    return report


def check_symbolic(game, max_states=100000, max_bdd_nodes=200000):
    from .modules import enabled
    if enabled(game):
        from .modules.analysis import failure
        return failure('STORY 1.2 is not admitted by the collectible symbolic solver')
    search = None
    try:
        search = SymbolicSearch(Engine(game), max_bdd_nodes)
        search.run(max_states)
        return report_search(search, max_states, max_bdd_nodes)
    except BudgetExceeded as exc:
        return {'status': 'inconclusive', 'complete': False, 'strategy': 'symbolic', 'reason': str(exc),
                'softlock_count': None, 'dead_end_count': None, 'state_count': None,
                'core_state_count': len(search.reachable) if search else 0,
                'bdd_nodes': len(search.bdd.nodes) if search else 0, 'state_cap': max_states, 'bdd_node_cap': max_bdd_nodes,
                'endings': {}, 'collectibles': {}, 'permanently_missable': None}
    except (SpecError, StateError, ValueError) as exc:
        return {'status': 'invalid', 'complete': False, 'strategy': 'symbolic', 'reason': str(exc),
                'softlock_count': None, 'dead_end_count': None, 'endings': {}, 'collectibles': {}}
