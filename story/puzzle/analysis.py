"""STORY 1.3 proof: the exact 1.2 macro graph with bounded per-visit grid search folded in.

Puzzle obligations (per puzzle): ``solvable`` (with shortest grid solution), ``opens:<door|gate|bridge>``,
``key:<id>``/``lock:<id>`` (no dead key logic), ``recoverable`` (hold-R reset, or full reversibility when
``reset: none``) and ``hint`` (the authored hint is consistent with the shortest proved solution).
"""
from ..compiler import digest
from ..errors import SpecError, StateError
from ..modules.analysis import ModuleSearch, report_search, failure as failure12
from . import flag, fact_flag
from .model import PuzzleAnalysisEngine
from .rules import route_plan, events_key, event_token, LIMITS

MODEL_ID = 'finite_checkpoint_challenges_puzzle_grid_v1'
NOT_RUN = ['Godot execution of puzzle rooms (see the puzzle bot receipt)', 'human playability', 'puzzle feel',
           'animation/audio/style acceptance']


def assumption():
    return {'id': 'puzzle_grid_model', 'kind': 'abstraction',
            'statement': 'Puzzle rooms are proved on their declared 1 m grid rules (cells, pushes, pulls, plates, links, '
                         'timers in whole steps). The Godot puzzle executor must enforce the same rules; that fidelity is '
                         'a separate parity-vector and physical bot receipt.', 'evidence': 'not_run'}


def failure(reason, status='invalid', game=None, cap=100000):
    report = failure12(reason, status, None, cap)
    report['assumptions'] = [assumption()]
    if isinstance(game, dict) and 'game_hash' in game:
        report['game_hash'] = game['game_hash']
    return report


def check(game, max_states=100000, max_edges=1000000):
    try:
        if type(max_states) is not int or not 1 <= max_states <= 100000:
            raise SpecError('module state cap must be an integer from 1 to 100000')
        engine = PuzzleAnalysisEngine(game)
        search = ModuleSearch(engine, max_states, max_edges)
        incomplete = [k for k in engine.summary_order if not engine.summaries[k][1]['complete']]
        if incomplete:
            report = failure('puzzle grid search reached max_states for ' + incomplete[0][0] + '; no solvability or softlock claim',
                             'inconclusive', game, max_states)
            report['state_count'] = len(search.states)
            return report
        report = report_search(search, max_states)
        if not search.complete:
            report['assumptions'].append(assumption())
            report['game_hash'] = game['game_hash']
            return report
        rebind(report, game, engine)
        puzzle_obligations(search, report)
        return report
    except (SpecError, StateError) as exc:
        return failure(str(exc), game=game if isinstance(game, dict) else None)


def rebind(report, game, engine):
    report['game_hash'] = game['game_hash']
    report['lowered_game_hash'] = engine.game['game_hash']
    report['analysis_version'] = '1.1.0'
    report['model_id'] = MODEL_ID
    report['model_hash'] = digest({'game': game['game_hash'], 'model': MODEL_ID})
    report['strategy'] = 'module_exact_puzzle_grid'
    report['assumptions'].append(assumption())


def puzzle_obligations(search, report):
    e, states = search.engine, search.states
    cond = bool(e.challenges)

    def obligation(oid, good, text, example=None, structural=False):
        status = ('conditional' if cond and not structural else 'proved') if good else 'rejected'
        report['obligations'].append({'id': oid, 'status': status, 'explanation': text})
        if not good:
            i = example if example is not None else 0
            report['counterexamples'].append({'obligation': oid, 'explanation': text,
                                              'state': e.to_dict(states[i]), 'witness': search.witness(i)})
    rows = {}
    for pid, grid in sorted(e.grids.items()):
        summaries = [(key, e.summaries[key]) for key in e.summary_order if key[0] == pid]
        solved_at = [i for i, st in enumerate(states) if dict(st.flags).get(flag(pid))]
        first = next((i for i, st in enumerate(states) if st.location == grid.room), None)
        row = rows[pid] = {'room': grid.room, 'name': grid.name, 'reset': 'hold' if grid.resettable else 'none',
                           'persistence': 'persistent' if grid.persistent else 'reset_on_leave',
                           'contexts_searched': len(summaries), 'grid_states': sum(len(s['states']) for _, (c, s) in summaries),
                           'step_ticks': grid.step_ticks, 'solvable': bool(solved_at), 'max_states': grid.max_states}
        # Shortest full-visit solution from the first reachable entry into this room (facts may change on the way).
        best = None
        if first is not None:
            ctx0 = e.context(states[first], grid)
            entry0 = states[first].entry
            route = grid.visit_route(ctx0, entry0)
            if route is not None:
                best = (ctx0, entry0, route)
        row['shortest_solution_steps'] = len(best[2]) if best else None
        if best:
            row['shortest_solution'] = {'route': best[2], 'entry': best[1], 'from_state': first,
                                        'facts': {'taken': sorted(best[0].taken), 'opened': sorted(best[0].opened),
                                                  'latched': sorted(best[0].latched), 'items': sorted(best[0].inventory)}}
        obligation('puzzle:' + pid + ':solvable', bool(solved_at),
                   ('Puzzle ' + pid + ' is solvable from a reachable state; shortest grid solution ' + str(row['shortest_solution_steps']) + ' steps.')
                   if solved_at else ('Puzzle ' + pid + ' is unsolvable: its goal ' + str(grid.goal['when']) +
                                      ' is never satisfied in any reachable grid state (for example a plate count that no block layout reaches).'),
                   first)
        for eid in grid.ids:
            kind = grid.el[eid]['kind']
            if kind in ('door', 'timed_gate', 'bridge'):
                ever = any(eid in s['open_ever'] for _, (c, s) in summaries)
                obligation('puzzle:' + pid + ':opens:' + eid, ever,
                           ('The ' + kind + ' ' + eid + ' opens in some reachable grid state.') if ever else
                           ('The ' + kind + ' ' + eid + ' never opens: its link ' + str(grid.el[eid]['when']) + ' is never satisfied and the goal never forces it.'),
                           first)
            elif kind == 'key':
                taken = any(dict(st.flags).get(fact_flag('taken', eid)) for st in states)
                obligation('puzzle:' + pid + ':key:' + eid, taken,
                           'Key ' + eid + (' can be picked up.' if taken else ' can never be reached: dead key logic.'), first)
            elif kind == 'lock':
                opened = any(dict(st.flags).get(fact_flag('opened', eid)) for st in states)
                obligation('puzzle:' + pid + ':lock:' + eid, opened,
                           'Lock ' + eid + (' can be opened.' if opened else ' can never be opened (for example its key lies behind it): dead-end key logic.'), first)
        # Recoverability: hold-R reset, or full reversibility (including right after every fact event).
        stuck, example, needs_reset = 0, None, 0
        for key, (ctx, s) in summaries:
            back = grid.returns(s)
            bad = [j for j in range(len(s['states'])) if j not in back]
            needs_reset += len(bad)
            if bad and example is None:
                example = {'entry': key[1], 'grid_state': grid.describe(s['states'][bad[0]]), 'route': s['route'](bad[0])}
            if not grid.resettable:
                stuck += len(bad)
                for ekey, edge in sorted(s['edges'].items()):
                    if any(ev[0] == 'solve' for ev in edge['events']) and len(edge['events']) == 1:
                        continue  # a solved visit has no further obligation to return
                    after = ctx.after(edge['events'], grid)
                    canon = grid.canonical(after, key[1])[0]
                    seen_posts = set()
                    for post in edge['posts']:
                        settled = grid.settle(post, after, 0)[0]
                        k = grid.key(settled)
                        if k in seen_posts:
                            continue
                        seen_posts.add(k)
                        ok = grid.reaches(settled, after, grid.key(canon), grid.max_states)
                        if not ok:
                            stuck += 1
                            if example is None:
                                example = {'entry': key[1], 'after_event': ekey, 'grid_state': grid.describe(settled)}
        row['states_needing_reset'] = needs_reset
        row['unrecoverable_states'] = 0 if grid.resettable else stuck
        good = grid.resettable or stuck == 0
        obligation('puzzle:' + pid + ':recoverable', good,
                   ('Hold-R reset restores the visit\'s entry configuration; ' + str(needs_reset) + ' explored grid states rely on it.')
                   if grid.resettable else
                   ('Without a reset every explored grid state can return to its entry configuration.' if good else
                    'Softlockable: reset is none and ' + str(stuck) + ' grid states can never return to the entry configuration '
                    '(for example a block pushed into a corner). Example: ' + str(example)), first, structural=True)
        if example is not None:
            row['reset_example'] = example
        if grid.hint:
            touched = set()
            if best:
                ctx = best[0]
                st, evs = grid.canonical(ctx, best[1])
                if evs:
                    ctx = ctx.after(evs, grid)
                for token in best[2]:
                    if token.startswith('act.'):
                        touched.add(token[4:])
                    out = grid.advance(st, ctx, token)
                    if out is None:
                        break
                    before, st = st, out[0]
                    if out[1]:
                        ctx = ctx.after(out[1], grid)
                        st = grid.settle(st, ctx, 0)[0]
                    touched.update(b for b, a, c in zip(grid.blocks, before[1], st[1]) if a != c)
                    touched.update(i for i in grid.ids if grid.el[i]['kind'] == 'plate' and grid.source(st, ctx, i))
            missing = [h for h in grid.hint if h not in touched]
            obligation('puzzle:' + pid + ':hint', not missing,
                       'Solution hint ' + str(grid.hint) + (' matches the shortest proved solution.' if not missing else
                                                          ' names elements the shortest proved solution never uses: ' + str(missing)),
                       first, structural=True)
        row['hint'] = list(grid.hint)
    report['puzzles'] = rows
    good = all(o['status'] != 'rejected' for o in report['obligations'])
    report['status'] = ('conditional' if e.challenges else 'proved') if good else 'rejected'
    report['evidence']['logical_proof'] = {'status': 'proved' if good else 'rejected',
                                           'scope': 'finite macro graph with exhaustive bounded grid search per puzzle visit; physical skill and executor fidelity are not proved'}
    report['evidence']['conditional_on_assumptions'] = {'status': 'conditional' if good and e.challenges else 'not_required' if good else 'rejected',
                                                        'assumption_ids': [a['id'] for a in report['assumptions']]}
    report['bounds']['puzzle_limits'] = dict(LIMITS)
    report['bounds']['puzzle_grid_states'] = sum(r['grid_states'] for r in rows.values())
    report['not_run'] = NOT_RUN
    report['puzzle_routes'] = {eid: witness_routes(e, value['witness'])
                               for eid, value in sorted(report['endings'].items()) if value.get('reachable')}


def interaction_cell(game, room, aid):
    """Grid cell of an authored presentation anchor for a room action (metadata.presentation.rooms.*.interactions)."""
    rooms = game.get('metadata', {}).get('presentation', {}).get('rooms', {})
    row = rooms.get(room, {}).get('interactions', {}).get(aid) if isinstance(rooms, dict) else None
    if not isinstance(row, dict) or not isinstance(row.get('position'), list) or len(row['position']) != 3:
        return None
    return (int(row['position'][0] // 1), int(row['position'][2] // 1))


def witness_routes(e, witness):
    """Turn one macro witness into continuous executable grid routes: the physical bot plan.

    Each puzzle step is planned from the micro state the previous step actually left (not from a fresh
    entry) with the exact rules; ``reset`` appears only where the planner genuinely needs it."""
    st = e.start
    micro = None
    rows = []
    for index, step in enumerate(witness):
        aid = step['action']
        grid = e.room_grid.get(st.location)
        nxt = e.step(st, aid)
        row = {'index': index, 'action': aid, 'room': st.location, 'route': []}
        if grid is not None:
            ctx = e.context(st, grid)
            entry = st.entry
            row['entry'] = entry
            if micro is None:
                micro = grid.canonical(ctx, entry)[0]
            path = []
            if aid.startswith('puzzle:' + grid.id + ':'):
                want = aid.split(':', 2)[2]
                cur, evs = grid.settle(micro, ctx, 0)
                if evs and events_key(evs) == want:
                    path, micro = [], cur  # the event fires on the same tick as the previous one
                    row['immediate'] = True
                else:
                    path = route_plan(grid, micro, ctx, lambda tok, s2, ev: bool(ev) and events_key(ev) == want, entry)
            elif aid.startswith('move:' + st.location + ':'):
                cell = grid.exits[aid.split(':')[2]]
                path = route_plan(grid, micro, ctx, lambda tok, s2, ev: not ev and s2[0] == cell, entry)
                row['exit_cell'] = list(cell)
                row['exit_dir'] = next(d['wall'] for d in e.rooms[st.location]['doors'] if d['id'] == aid.split(':')[2])
            elif aid.startswith('checkpoint:'):
                # The commit needs the player on the start cell; it then resets the room (entry '').
                path = route_plan(grid, micro, ctx, lambda tok, s2, ev: not ev and s2[0] == grid.start, entry)
            else:
                anchor = interaction_cell(e.game, st.location, aid)
                if anchor is not None:
                    # Face the anchor from a neighbouring cell (E reaches the faced cell), else stand on it.
                    path = route_plan(grid, micro, ctx, lambda tok, s2, ev: not ev and abs(s2[0][0] - anchor[0]) + abs(s2[0][1] - anchor[1]) == 1, entry)
                    if path is None:
                        path = route_plan(grid, micro, ctx, lambda tok, s2, ev: not ev and s2[0] == anchor, entry)
                    row['target_cell'] = list(anchor)
            if path is None:
                row['error'] = 'no continuous grid route for this witness step'
                path = []
            after_ctx = e.context(nxt, grid) if nxt.location == st.location else ctx
            for tok, s2, evs in path:
                if evs:
                    s2 = grid.settle(s2, after_ctx, 0)[0]
                micro = s2
                row['route'].append({'token': tok, 'key': str(grid.key(s2)), 'events': [event_token(x) for x in evs]})
            row['end_key'] = str(grid.key(micro))
            if aid.startswith('checkpoint:'):
                micro = None  # committed: the room resets with the player on the start cell
        if nxt.location != st.location:
            micro = None
        # Expected macro facts after this step (reserved flags + inventory), for the physical bot to compare.
        row['flags'] = {k: v for k, v in nxt.flags if k.startswith('puzzle__')}
        row['inventory'] = list(nxt.inventory)
        row['location'] = nxt.location
        st = nxt
        rows.append(row)
    return rows
