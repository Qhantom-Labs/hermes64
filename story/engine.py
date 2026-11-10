"""Shared deterministic transition templates and direct concrete execution."""
from typing import NamedTuple
from .compiler import validate_game
from .errors import StateError
from .validation import validate_state
from .extensions import extended


class State(NamedTuple):
    location: str
    inventory: tuple
    flags: tuple
    dialogue: tuple
    tide: str
    tick: int
    collected: tuple = ()


class Action(NamedTuple):
    id: str
    label: str
    state: State


class Template(NamedTuple):
    id: str
    label: str
    state: State
    before: tuple = ()
    after: tuple = ()
    collect: str = ''
    recall: str = ''


class Engine:
    def __new__(cls, game):
        from .modules import enabled
        if cls is Engine and enabled(game):
            from .modules.model import ModuleEngine
            return object.__new__(ModuleEngine)
        return object.__new__(cls)

    def __init__(self, game):
        validate_game(game)
        self.game = game
        self.rooms = {x['id']: x for x in game['rooms']}
        self.characters = {x['id']: x for x in game['characters']}
        self.dialogues = {x['id']: x for x in game['dialogues']}
        self.nodes = {x['id']: {n['id']: n for n in x['nodes']} for x in game['dialogues']}
        self.tides = game['tide']['states']
        self.tide_indices = {x['id']: i for i, x in enumerate(self.tides)}
        self.local = {rid: [x for x in game['interactions'] if x['room'] == rid] for rid in self.rooms}
        self.collectibles = {x['id']: x for x in game.get('collectibles', [])}
        self.groups = {g['id']: tuple(c['id'] for c in self.collectibles.values() if c['group'] == g['id'])
                       for g in game.get('collectible_groups', [])}
        self.local_collectibles = {rid: [x for x in self.collectibles.values() if x['room'] == rid] for rid in self.rooms}
        self.start = self.from_dict(game['start'])
        if not self._valid_dialogue(self.start):
            raise StateError('initial active dialogue conditions do not hold')

    def from_dict(self, data):
        validate_state(data, self.game)
        return State(data['location'], tuple(sorted(data['inventory'])), tuple(sorted(data['flags'].items())),
                     tuple(sorted(data['dialogue'].items())), data['tide']['state'], data['tide']['tick'],
                     tuple(sorted(data.get('collected', []))))

    def to_dict(self, st):
        out = {'location': st.location, 'inventory': list(st.inventory), 'flags': dict(st.flags),
               'dialogue': dict(st.dialogue), 'tide': {'state': st.tide, 'tick': st.tick}}
        if extended(self.game):
            out['collected'] = list(st.collected)
        return out

    def group_counts(self, st):
        return {g: sum(cid in st.collected for cid in members) for g, members in self.groups.items()}

    def follower_flags(self, st):
        return {c['follower_flag']: c['id'] in st.collected for c in self.collectibles.values() if c['follower_flag']}

    def matches(self, conditions, st):
        flags, dialogue = dict(st.flags), dict(st.dialogue)
        for c in conditions:
            if 'collected' in c:
                ok = c['collected'] in st.collected
            elif 'group' in c:
                ok = sum(cid in st.collected for cid in self.groups[c['group']]) >= c['at_least']
            elif 'flag' in c:
                ok = flags[c['flag']] == c['equals']
            elif 'item' in c:
                ok = (c['item'] in st.inventory) == c['present']
            elif 'location' in c:
                ok = st.location == c['location']
            elif 'tide' in c:
                ok = st.tide == c['tide']
            elif 'role' in c:
                ok = self.characters[c['role']]['role'] == c['equals']
            else:
                ok = dialogue[c['dialogue']] == c['node']
            if not ok:
                return False
        return True

    def endings(self, st):
        return [e['id'] for e in self.game['endings'] if self.matches(e['conditions'], st)]

    def node_guards(self, st):
        return tuple(c for d, n in st.dialogue if n for c in self.nodes[d][n]['conditions'])

    def _valid_dialogue(self, st):
        return sum(bool(n) for d, n in st.dialogue) <= 1 and self.matches(self.node_guards(st), st)

    def _effect_state(self, st, effects, cursor=None):
        inventory, flags, dialogue = set(st.inventory), dict(st.flags), dict(st.dialogue)
        location, tide, tick = st.location, st.tide, st.tick
        for effect in effects:
            if 'flag' in effect:
                flags[effect['flag']] = effect['value']
            elif 'give' in effect:
                inventory.add(effect['give'])
            elif 'take' in effect:
                if effect['take'] not in inventory:
                    return None
                inventory.remove(effect['take'])
            elif 'dialogue' in effect:
                dialogue[effect['dialogue']] = effect['node']
            elif 'location' in effect:
                location = effect['location']
            elif 'tide' in effect:
                tide, tick = effect['tide'], 0
        if cursor is not None:
            dialogue[cursor[0]] = cursor[1]
        if sum(bool(n) for n in dialogue.values()) > 1:
            return None
        return st._replace(location=location, inventory=tuple(sorted(inventory)), flags=tuple(sorted(flags.items())),
                           dialogue=tuple(sorted(dialogue.items())), tide=tide, tick=tick)

    def templates(self, st):
        """Unevaluated guards, core effects already atomic. Terminal filtering is separate."""
        plans = []
        active = [(d, n) for d, n in st.dialogue if n]
        if active:
            did, nid = active[0]
            node = self.nodes[did][nid]
            for choice in node['choices']:
                out = self._effect_state(st, choice['effects'], (did, choice['next']))
                if out is not None:
                    plans.append(Template('choose:{}:{}:{}'.format(did, nid, choice['id']), choice['text'], out,
                                          tuple(node['conditions'] + choice['conditions']), self.node_guards(out)))
            out = st._replace(dialogue=tuple((d, '' if d == did else n) for d, n in st.dialogue))
            plans.append(Template('cancel:' + did, 'End conversation', out))
        else:
            for door in self.rooms[st.location]['doors']:
                plans.append(Template('move:{}:{}'.format(st.location, door['id']), door['label'],
                                      st._replace(location=door['to_room']), tuple(door['conditions'])))
            for a in self.local[st.location]:
                out = self._effect_state(st, a['effects'])
                if out is not None:
                    plans.append(Template('interact:' + a['id'], a['label'], out, tuple(a['conditions']), self.node_guards(out)))
            for c in self.local_collectibles[st.location]:
                out = st
                if c['dialogue']:
                    out = self._effect_state(st, [], (c['dialogue'], self.dialogues[c['dialogue']]['start_node']))
                after = self.node_guards(out)
                plans.append(Template('collect:' + c['id'], c['label'], out, tuple(c['conditions']), after, c['id']))
                if c['dialogue']:
                    plans.append(Template('recall:' + c['id'], 'Recall ' + c['name'], out, (), after, '', c['id']))
        index = self.tide_indices[st.tide]
        tick = st.tick + 1
        if tick >= self.tides[index]['duration']:
            index = (index + 1) % len(self.tides)
            tick = 0
        plans.append(Template('wait', self.game['tide']['wait_label'], st._replace(tide=self.tides[index]['id'], tick=tick)))
        return sorted(plans, key=lambda a: a.id)

    def actions(self, st):
        if self.endings(st):
            return []
        actions = []
        for plan in self.templates(st):
            if plan.collect in st.collected or (plan.recall and plan.recall not in st.collected):
                continue
            if not self.matches(plan.before, st):
                continue
            out = plan.state
            if plan.collect:
                out = out._replace(collected=tuple(sorted(st.collected + (plan.collect,))))
            if self.matches(plan.after, out):
                actions.append(Action(plan.id, plan.label, out))
        return actions

    def step(self, st, action_id):
        for action in self.actions(st):
            if action.id == action_id:
                return action.state
        raise StateError('action {} unavailable at {}'.format(action_id, st.location))
