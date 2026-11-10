"""Exact bounded macro graph with named physical assumptions and counterexamples."""
from collections import deque
from ..compiler import digest
from ..checker import Search, diagnose
from ..collectible_checks import concrete_obligations
from ..errors import SpecError, StateError
from .model import AnalysisEngine
from .registry import entity_map, api_version
from .course import minimum_ticks


class ModuleSearch(Search):
    """Exact graph, bounded by both discovered states and enumerated transitions."""
    def __init__(self, engine, max_states=100000, max_edges=1000000):
        if type(max_edges) is not int or not 1 <= max_edges <= 1000000:
            raise SpecError('edge cap must be an integer from 1 to 1000000')
        original = engine.actions
        remaining = [max_edges]
        self.limit_reason = 'state cap reached'
        class EdgeLimit(Exception):
            pass
        def bounded_actions(st):
            actions = original(st)
            remaining[0] -= len(actions)
            if remaining[0] < 0:
                raise EdgeLimit()
            return actions
        engine.actions = bounded_actions
        try:
            super().__init__(engine, max_states)
        except EdgeLimit:
            self.complete = False
            self.limit_reason = 'edge cap reached'
        finally:
            engine.actions = original
        self.edge_cap = max_edges

    def backward(self, seeds):
        reached = set(seeds)
        queue = deque(sorted(reached))
        while queue:
            for parent in self.reverse[queue.popleft()]:
                if parent not in reached:
                    reached.add(parent)
                    queue.append(parent)
        return reached


def assumptions(game):
    rows = [{'id': 'spatial_access', 'kind': 'abstraction',
             'statement': 'Logically available doors, interactions, checkpoints and challenge entry anchors can be physically reached. Geometry is not modeled.',
             'evidence': 'not_run'}]
    for cid, c in sorted(entity_map(game, 'challenge', 'challenges').items()):
        rows.append({'id': c['kind'] + '_' + cid + '_completable', 'kind': 'challenge_completion',
                     'challenge': cid, 'statement': ('The player can clear encounter ' if c['kind'] == 'combat' else 'The player can finish the ordered course before its deadline: ') + cid,
                     'evidence': 'not_run'})
    return rows


def failure(reason, status='invalid', game=None, cap=100000):
    return {'status': status, 'complete': False, 'reason': reason, 'state_count': None,
            'softlock_count': None, 'dead_end_count': None, 'endings': {}, 'obligations': [],
            'counterexamples': [], 'assumptions': assumptions(game) if game and 'gameplay' in game else [],
            'bounds': {'state_cap': cap}, 'evidence': {
                'logical_proof': {'status': status}, 'conditional_on_assumptions': {'status': 'not_run'},
                'physically_tested_by_bot': {'status': 'not_run'}, 'human_tested': {'status': 'not_run'}}}


def report_search(search, max_states):
    e, game = search.engine, search.engine.game
    if not search.complete:
        report = failure(getattr(search, 'limit_reason', 'state cap reached') + '; no completeness or softlock claim', 'inconclusive', game, max_states)
        report['state_count'] = len(search.states)
        return report
    states = search.states
    nonterminal = {i for i, st in enumerate(states) if not e.endings(st)}
    winning = search.backward(search.terminals)
    softlocks = sorted(nonterminal - winning)
    endings = {}
    def witness(indices):
        if not indices:
            return {'reachable': False, 'witness': [], 'reason': 'no reachable state satisfies this obligation'}
        i = min(indices)
        return {'reachable': True, 'witness': search.witness(i), 'final_state': e.to_dict(states[i])}
    for ending in game['endings']:
        endings[ending['id']] = witness([i for i, eid in search.terminals.items() if eid == ending['id']])
    report = {'status': 'proved', 'complete': True, 'analysis_version': '1.0.0',
        'strategy': 'module_exact', 'model_id': 'finite_checkpoint_challenges_v1',
        'model_hash': digest({'game': game['game_hash'], 'model': 'finite_checkpoint_challenges_v1'}),
        'game_hash': game['game_hash'], 'reason': 'Complete finite graph; skill outcomes are hypothetical, not executable player choices.',
        'state_count': len(states), 'edge_count': search.edges, 'state_cap': max_states,
        'bounds': {'state_cap': max_states, 'challenge_count': len(e.challenges), 'active_challenge_cap': 1,
                   'health_cap': 64, 'max_waves': 8, 'max_simultaneous_enemies': 3},
        'endings': endings, 'softlock_count': len(softlocks), 'dead_end_count': len(search.dead_ends),
        'ambiguous_terminal_count': len(search.ambiguous),
        'softlocks': [{'state': e.to_dict(states[i]), 'witness': search.witness(i), 'reason': 'no ending is reachable from this state, even assuming skill success'} for i in softlocks[:10]],
        'dead_ends': [{'state': e.to_dict(states[i]), 'witness': search.witness(i), 'reason': 'no state-changing successor'} for i in search.dead_ends[:10]],
        'ambiguous_terminals': [{'state': e.to_dict(states[i]), 'witness': search.witness(i), 'endings': e.endings(states[i])} for i in search.ambiguous[:10]],
        'missing_prerequisites': diagnose(search), 'assumptions': assumptions(game), 'obligations': [], 'counterexamples': []}
    # Keep inherited 1.1 collectible identity, threshold and missability obligations exact.
    concrete_obligations(search, report)
    report['strategy'] = 'module_exact'
    def obligation(oid, good, text, conditional=False, example=None):
        status = ('conditional' if conditional else 'proved') if good else 'rejected'
        report['obligations'].append({'id': oid, 'status': status, 'explanation': text})
        if not good:
            i = example if example is not None else 0
            report['counterexamples'].append({'obligation': oid, 'explanation': text,
                'state': e.to_dict(states[i]), 'witness': search.witness(i)})
    for eid, value in endings.items():
        obligation('ending:' + eid, value['reachable'], 'Ending ' + eid + (' has an abstract route.' if value['reachable'] else ' has no abstract route; inspect missing prerequisites: ' + str(report['missing_prerequisites'])), bool(e.challenges))
    obligation('no_softlocks', not softlocks, 'Every reachable nonterminal state has an ending route under the named assumptions.' if not softlocks else 'A reachable state has no ending route even if all skill outcomes were possible.', bool(e.challenges), softlocks[0] if softlocks else None)
    obligation('unambiguous_endings', not search.ambiguous, 'Exactly one ending may match a terminal state.', example=search.ambiguous[0] if search.ambiguous else None)
    obligation('bounded_resources', True, 'No entry fees, scarce ammunition or random essential drops. Attempt health refills, failures preserve permanent resources, rewards are unique once-only tokens.')
    for cid, c in sorted(e.challenges.items()):
        available = [i for i, st in enumerate(states) if not e.endings(st) and e.can_start(st, cid)]
        obligation('access:' + cid, bool(available), 'Challenge ' + cid + ' needs a reachable entry with conditions ' + str(c['conditions']) + '.', bool(e.challenges))
        achieved = [i for i, st in enumerate(states) if cid in st.modules.completed]
        obligation('reward:' + cid, bool(achieved), 'Guaranteed once-only reward for ' + cid + ': ' + str(c['rewards']) + (' is available after assumed success.' if achieved else ' is unavailable; it may be gated behind its own challenge.'), True)
        recovery = search.backward(available)
        failed = [i for i, st in enumerate(states) if st.modules.failed == cid and i not in recovery]
        obligation('retry:' + cid, not failed, 'Failure must return to a safe checkpoint with a route back to start ' + cid + '; no completion event may be needed to escape the retry.', example=failed[0] if failed else None)
    for aid in sorted(e.abilities):
        found = any(aid in st.modules.abilities for st in states)
        obligation('ability:' + aid, found, 'Ability ' + aid + ' must have a reachable producer or initial grant.', bool(e.challenges))
    for rid, region in sorted(e.regions.items()):
        found = any(st.location == region['room'] for st in states)
        obligation('region:' + rid, found, 'Region ' + rid + ' must be reachable through its finite gates.', bool(e.challenges))
    for room in game['rooms']:
        for door in room['doors']:
            aid = 'move:' + room['id'] + ':' + door['id']
            found = any(st.location == room['id'] and any(a.id == aid for a in e.actions(st)) for st in states)
            obligation('gate:' + room['id'] + ':' + door['id'], found,
                       'Gate ' + aid + ' must be usable; required conditions: ' + str(door['conditions']), bool(e.challenges))
    for tid, track in entity_map(game, 'course', 'tracks').items():
        bound = minimum_ticks(game, track)
        obligation('metric:' + tid, track['time_limit_ticks'] >= bound,
                   'Course ' + tid + ' requires at least ' + str(bound) + ' ticks by the minimum distance/speed metric; deadline is ' + str(track['time_limit_ticks']) + '. Passing this bound does not establish steering feasibility.')
    if api_version(game) != '1.0.0':
        combat_obligations(game, e, states, search, obligation, report)
    collectible_good = report['status'] != 'rejected'
    obligation('collectibles', collectible_good, 'Inherited collectible identity, threshold and non-missability obligations must all hold.', bool(e.challenges))
    permitted = game['gameplay']['verification_policy'] == 'conditional' or not e.challenges
    obligation('policy', permitted, 'Project policy must explicitly permit conditional challenge completion; it cannot be silently upgraded to proof.')
    good = all(o['status'] != 'rejected' for o in report['obligations'])
    report['status'] = ('conditional' if e.challenges else 'proved') if good else 'rejected'
    report['evidence'] = {
        'logical_proof': {'status': 'proved' if good else 'rejected', 'scope': 'finite abstract graph only; physical skill is not proved'},
        'conditional_on_assumptions': {'status': 'conditional' if good and e.challenges else 'not_required' if good else 'rejected', 'assumption_ids': [a['id'] for a in report['assumptions']]},
        'physically_tested_by_bot': {'status': 'not_run', 'receipt': None},
        'human_tested': {'status': 'not_run', 'receipt': None}}
    report['not_run'] = ['Godot execution', 'physical collision/traversal/combat/course replay', 'human playability', 'combat feel', 'animation/audio/style acceptance']
    return report


def combat_obligations(game, e, states, search, obligation, report):
    """Gameplay API 1.1.0 combat rules (COMBAT lane): simulation bounds per encounter (stall, strength, projectile,
    shockwave) and the boss gate. 1.0.0 games never get these rows, so their proofs are unchanged."""
    from .combat_bounds import encounter_bounds
    archetypes = entity_map(game, 'combat', 'archetypes')
    health = game['gameplay']['modules'][[m['id'] for m in game['gameplay']['modules']].index('abilities')]['config']['max_health']
    challenges = entity_map(game, 'challenge', 'challenges')
    report['combat_bounds'] = {}
    for eid, encounter in sorted(entity_map(game, 'combat', 'encounters').items()):
        bounds = encounter_bounds(game, encounter, health, archetypes)
        report['combat_bounds'][eid] = {k: v for k, v in bounds.items() if k != 'problems'}
        for rule in ('stall', 'strength', 'projectile', 'shockwave'):
            found = [text for kind, text in bounds['problems'] if kind == rule]
            obligation('combat_' + rule + ':' + eid, not found, ('Encounter ' + eid + ': ' + '; '.join(found)) if found else
                       'Encounter ' + eid + ' passes the ' + rule + ' bound (optimistic perfect-play simulation bound; not a fairness or fun claim).')
        gate = encounter.get('gate', '')
        if gate:
            owners = [cid for cid, c in challenges.items() if c['kind'] == 'combat' and c['subject'] == eid]
            aid = 'move:' + encounter['room'] + ':' + gate
            opened = [i for i, st in enumerate(states) if st.location == encounter['room'] and any(cid in st.modules.completed for cid in owners)
                      and any(a.id == aid for a in e.actions(st))]
            obligation('boss_gate:' + eid, bool(opened), 'Gate ' + aid + (' opens after the boss falls.' if opened else
                       ' never opens after the boss falls: its other conditions are unreachable, so the arena stays locked.'), True)


def check(game, max_states=100000, max_edges=1000000):
    try:
        if type(max_states) is not int or not 1 <= max_states <= 100000:
            raise SpecError('module state cap must be an integer from 1 to 100000')
        return report_search(ModuleSearch(AnalysisEngine(game), max_states, max_edges), max_states)
    except (SpecError, StateError) as exc:
        return failure(str(exc))
