"""Concrete-oracle collectible obligations, independent of BDD operations."""
from collections import deque


def threshold_sites(game):
    from .checker import condition_sites
    for path, conditions, room, cursor in condition_sites(game):
        for i, c in enumerate(conditions):
            if 'group' in c:
                yield path + '/conditions/' + str(i), c


def threshold_result(group, required, supply, attainable):
    return {'group': group, 'required': required, 'supply': supply, 'attainable': attainable,
            'reason': 'attainable' if attainable else
            'required {} exceeds declared supply {}'.format(required, supply) if required > supply else
            'no reachable state meets threshold {}'.format(required)}


def concrete_obligations(search, report):
    e = search.engine
    report.update(strategy='exhaustive', core_state_count=len({s._replace(collected=()) for s in search.states}),
                  collectibles={}, groups={}, thresholds=[], permanently_missable={}, example_limit=10)
    if not search.complete:
        return report
    nonterminal = {i for i, st in enumerate(search.states) if not e.endings(st)}

    def backward(seed):
        found = set(seed)
        queue = deque(sorted(found))
        while queue:
            for parent in search.reverse[queue.popleft()]:
                if parent not in found:
                    found.add(parent)
                    queue.append(parent)
        return found

    for cid in sorted(e.collectibles):
        found = [i for i, st in enumerate(search.states) if cid in st.collected]
        info = {'reachable': bool(found), 'witness': []}
        if found:
            info.update(witness=search.witness(found[0]), final_state=e.to_dict(search.states[found[0]]))
        else:
            info['reason'] = 'no reachable collection; inspect its room/gate/conditions'
        report['collectibles'][cid] = info
        missing = sorted(nonterminal - backward(found))
        if missing:
            report['permanently_missable'][cid] = {'state_count': len(missing), 'examples': [
                {'state': e.to_dict(search.states[i]), 'witness': search.witness(i),
                 'reason': 'this missing collectible can never be acquired before termination'} for i in missing[:10]]}
    for g in e.game['collectible_groups']:
        attainable = any(e.matches([{'group': g['id'], 'at_least': g['required']}], s) for s in search.states)
        report['groups'][g['id']] = threshold_result(g['id'], g['required'], len(e.groups[g['id']]), attainable)
    for path, cond in threshold_sites(e.game):
        row = threshold_result(cond['group'], cond['at_least'], len(e.groups[cond['group']]), any(e.matches([cond], s) for s in search.states))
        row['path'] = path
        report['thresholds'].append(row)
    report['permanently_missable_collectible_count'] = len(report['permanently_missable'])
    good = (all(x['reachable'] for x in report['collectibles'].values()) and
            all(x['attainable'] for x in report['groups'].values()) and
            all(x['attainable'] for x in report['thresholds']) and not report['permanently_missable'])
    if not good:
        report['status'] = 'rejected'
    return report
