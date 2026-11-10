"""Slow reference: independent module reducer and per-source forward searches.

Shares strict admission, legacy story templates and obligation definitions, not
module transitions, graph traversal, or reverse reachability implementation.
"""
from collections import deque
from ..engine import Engine, Action
from ..errors import SpecError
from .model import ModuleEngine, from_data
from .analysis import report_search, failure


class ReferenceEngine(ModuleEngine):
    def matches(self, conditions, st):
        data = self.to_dict(st)['modules']
        for c in conditions:
            if 'ability' in c:
                if c['ability'] not in data['abilities']:
                    return False
            elif 'challenge' in c:
                if c['challenge'] not in data['completed']:
                    return False
            elif not Engine.matches(self, [c], st):
                return False
        return True

    def _effect_state(self, st, effects, cursor=None):
        out = Engine._effect_state(self, st, effects, cursor)
        if out is None:
            return None
        unlocked = list(st.modules.abilities)
        for effect in effects:
            if 'unlock' in effect:
                aid = effect['unlock']
                if any(dep not in unlocked for dep in self.abilities[aid]['requires']):
                    return None
                if aid not in unlocked:
                    unlocked.append(aid)
        return out._replace(modules=out.modules._replace(abilities=tuple(sorted(unlocked))))

    def actions(self, st):
        if self.endings(st):
            return []
        data = self.to_dict(st)
        m = data['modules']
        rows = []
        def emit(aid, label, value):
            known = value['modules']['discovered']
            for rid, r in self.regions.items():
                if r['room'] == value['location'] and rid not in known:
                    known.append(rid)
            known.sort()
            rows.append(Action(aid, label, self.from_dict(value)))
        import copy
        if m['active']:
            cid = m['active']
            c = self.challenges[cid]
            for action in ('complete', 'fail', 'abort'):
                out = copy.deepcopy(data)
                out['modules']['active'] = ''
                if action == 'complete':
                    out['modules']['completed'] = sorted(m['completed'] + [cid])
                    for key, dest in [('items', out['inventory']), ('abilities', out['modules']['abilities'])]:
                        for token in c['rewards'][key]:
                            if token not in dest:
                                dest.append(token)
                        dest.sort()
                else:
                    out['location'] = self.checkpoints[c['checkpoint']]['room']
                    out['modules']['checkpoint'] = c['checkpoint']
                    out['modules']['failed'] = cid
                aid = ('challenge:abort:' if action == 'abort' else 'assume:' + action + ':') + cid
                emit(aid, action + ' ' + cid, out)
        elif m['failed']:
            out = copy.deepcopy(data)
            out['modules']['failed'] = ''
            emit('challenge:retry:' + m['failed'], 'retry', out)
        else:
            for plan in Engine.templates(self, st):
                if plan.collect in st.collected or (plan.recall and plan.recall not in st.collected) or not self.matches(plan.before, st):
                    continue
                out = plan.state
                if plan.collect:
                    out = out._replace(collected=tuple(sorted(st.collected + (plan.collect,))))
                if self.matches(plan.after, out):
                    emit(plan.id, plan.label, self.to_dict(out))
            if not any(data['dialogue'].values()):
                for cid, c in self.challenges.items():
                    if cid not in m['completed'] and c['room'] == st.location and self.matches(c['conditions'], st):
                        out = copy.deepcopy(data)
                        out['modules'].update(active=cid, checkpoint=c['checkpoint'])
                        emit('challenge:start:' + cid, 'start ' + cid, out)
                for pid, point in self.checkpoints.items():
                    if point['room'] == st.location:
                        out = copy.deepcopy(data)
                        out['modules']['checkpoint'] = pid
                        emit('checkpoint:' + pid, 'checkpoint ' + pid, out)
        return sorted(rows, key=lambda r: r.id)


class ReferenceSearch:
    def __init__(self, engine, cap):
        self.engine = engine
        self.states = [engine.start]
        self.parents = [None]
        self.reverse = [[]]
        self.forward = [[]]
        self.terminals = {}
        self.ambiguous = []
        self.dead_ends = []
        self.complete = True
        self.edges = 0
        i = 0
        while i < len(self.states):
            st = self.states[i]
            endings = engine.endings(st)
            if len(endings) == 1:
                self.terminals[i] = endings[0]
            elif endings:
                self.ambiguous.append(i)
            else:
                actions = engine.actions(st)
                if not any(a.state != st for a in actions):
                    self.dead_ends.append(i)
                for a in actions:
                    if a.state not in self.states:
                        if len(self.states) >= cap:
                            self.complete = False
                            return
                        self.states.append(a.state)
                        self.parents.append((i, a.id, a.label))
                        self.reverse.append([])
                        self.forward.append([])
                    j = self.states.index(a.state)
                    self.reverse[j].append(i)
                    self.forward[i].append(j)
                    self.edges += 1
            i += 1

    def backward(self, seeds):
        # Intentionally slow independent oracle: search forward from EVERY state.
        result = set()
        for source in range(len(self.states)):
            pending, seen = [source], []
            while pending:
                i = pending.pop()
                if i in seeds:
                    result.add(source)
                    break
                if i not in seen:
                    seen.append(i)
                    pending.extend(self.forward[i])
        return result

    def witness(self, index):
        out = []
        while self.parents[index] is not None:
            prev, aid, label = self.parents[index]
            st = self.states[index]
            out.insert(0, {'action': aid, 'label': label, 'location': st.location,
                           'tide': {'state': st.tide, 'tick': st.tick}})
            index = prev
        return out


def check_reference(game, max_states=100000):
    if type(max_states) is not int or not 1 <= max_states <= 100000:
        return failure('invalid reference state cap')
    return report_search(ReferenceSearch(ReferenceEngine(game), max_states), max_states)
