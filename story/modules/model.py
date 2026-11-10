"""Finite macro-state semantics. Hypothetical outcomes are analysis-only actions."""
from typing import NamedTuple
from ..engine import Engine, State, Template
from ..errors import StateError
from .registry import entity_map


class ModuleState(NamedTuple):
    abilities: tuple
    completed: tuple
    active: str
    failed: str
    checkpoint: str
    discovered: tuple


class CombinedState(NamedTuple):
    location: str
    inventory: tuple
    flags: tuple
    dialogue: tuple
    tide: str
    tick: int
    collected: tuple
    modules: ModuleState


def from_data(data):
    return ModuleState(tuple(data['abilities']), tuple(data['completed']), data['active'], data['failed'],
                       data['checkpoint'], tuple(data['discovered']))


def to_data(state):
    return {key: list(value) if isinstance(value, tuple) else value for key, value in state._asdict().items()}


class ModuleEngine(Engine):
    abstract_outcomes = False

    def __init__(self, game):
        self.abilities = entity_map(game, 'abilities', 'abilities')
        self.challenges = entity_map(game, 'challenge', 'challenges')
        self.checkpoints = entity_map(game, 'challenge', 'checkpoints')
        self.regions = entity_map(game, 'regions', 'regions')
        super().__init__(game)

    def from_dict(self, data):
        core = super().from_dict(data)
        return CombinedState(*core, from_data(data['modules']))

    def to_dict(self, st):
        out = super().to_dict(st)
        out['modules'] = to_data(st.modules)
        return out

    def matches(self, conditions, st):
        for condition in conditions:
            if 'ability' in condition:
                if condition['ability'] not in st.modules.abilities:
                    return False
            elif 'challenge' in condition:
                if condition['challenge'] not in st.modules.completed:
                    return False
            elif not super().matches([condition], st):
                return False
        return True

    def endings(self, st):
        if st.modules.active or st.modules.failed:
            return []
        return super().endings(st)

    def discover(self, st):
        found = {rid for rid, region in self.regions.items() if region['room'] == st.location}
        return st._replace(modules=st.modules._replace(discovered=tuple(sorted(set(st.modules.discovered) | found))))

    def _effect_state(self, st, effects, cursor=None):
        abilities = set(st.modules.abilities)
        for effect in effects:
            if 'unlock' in effect:
                aid = effect['unlock']
                if not all(dep in abilities for dep in self.abilities[aid]['requires']):
                    return None
                abilities.add(aid)
        out = super()._effect_state(st, effects, cursor)
        if out is None:
            return None
        return self.discover(out._replace(modules=out.modules._replace(abilities=tuple(sorted(abilities)))))

    def can_start(self, st, cid):
        c = self.challenges[cid]
        return (not st.modules.active and not st.modules.failed and not any(n for d, n in st.dialogue)
                and cid not in st.modules.completed and st.location == c['room'] and self.matches(c['conditions'], st))

    def outcome(self, st, success):
        """Private macro reducer, NOT a live executor validation or physical observation."""
        cid = st.modules.active
        if not cid:
            raise StateError('no active challenge')
        c = self.challenges[cid]
        if success:
            return st._replace(inventory=tuple(sorted(set(st.inventory) | set(c['rewards']['items']))),
                modules=st.modules._replace(active='', completed=tuple(sorted(st.modules.completed + (cid,))),
                    abilities=tuple(sorted(set(st.modules.abilities) | set(c['rewards']['abilities'])))))
        return self.discover(st._replace(location=self.checkpoints[c['checkpoint']]['room'],
            modules=st.modules._replace(active='', failed=cid, checkpoint=c['checkpoint'])))

    def templates(self, st):
        ms = st.modules
        if ms.active:
            cid = ms.active
            failed = self.outcome(st, False)
            plans = [Template('challenge:abort:' + cid, 'Abort ' + cid + ' and return to its safe checkpoint', failed)]
            if self.abstract_outcomes:
                plans += [Template('assume:complete:' + cid, 'ASSUME ' + cid + ' can be completed (not physical evidence)', self.outcome(st, True)),
                          Template('assume:fail:' + cid, 'Model failure of ' + cid + '; no permanent resource loss', failed)]
            return plans
        if ms.failed:
            cid = ms.failed
            return [Template('challenge:retry:' + cid, 'Reset attempt at checkpoint; return to ' + cid + ' to restart',
                             st._replace(modules=ms._replace(failed='')))]
        plans = [p._replace(state=self.discover(p.state)) for p in super().templates(st)]
        if not any(n for d, n in st.dialogue):
            for cid in sorted(self.challenges):
                if self.can_start(st, cid):
                    c = self.challenges[cid]
                    plans.append(Template('challenge:start:' + cid, 'Start ' + cid,
                        st._replace(modules=ms._replace(active=cid, checkpoint=c['checkpoint']))))
            for pid, p in sorted(self.checkpoints.items()):
                if p['room'] == st.location:
                    plans.append(Template('checkpoint:' + pid, 'Commit safe checkpoint ' + pid,
                        st._replace(modules=ms._replace(checkpoint=pid))))
        return sorted(plans, key=lambda p: p.id)


class AnalysisEngine(ModuleEngine):
    """Explicit opt-in semantic analysis harness. Never expose its actions to gameplay UI."""
    abstract_outcomes = True
