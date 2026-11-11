"""Bounded asset loop, driven by a brief and taxonomy gaps, not by a noun whitelist.

Agent-authored recipes are supplied as data or by a synchronous author callback.
No network/model client is hidden here. Every author/build/adjust/drop is audited.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

from . import asset_report, gen_tools, provenance
from .gen_tools import RecipeError
from .safety import Fault


EXAMPLES = Path(__file__).resolve().parents[1] / 'skills/hermes64-generators/recipes'


def _normal(want):
    from .taxonomy import norm_text
    return ' '.join(w for w in norm_text(want.replace('_', ' ')).split() if w not in ('on', 'with', 'a', 'an'))


def _choose(root, want, candidates, author, brief, p):
    choice = candidates.get(want)
    if choice is None:
        for row in gen_tools.list_recipes(root):
            if _normal(row['id'][4:]) == _normal(want):
                choice = row['id']; break
    if choice is None:
        for file in sorted(EXAMPLES.glob('*.json')):
            if _normal(file.stem) == _normal(want):
                choice = {'recipe': gen_tools.decode(file.read_bytes()), 'model': 'bundled-original-example'}
                break
    if choice is None and author is not None:
        gen_tools.log_call(p, 'author_request', brief_line=want)
        choice = author(want, brief)
        gen_tools.log_call(p, 'author_response', brief_line=want, supplied=choice is not None)
    if choice is None:
        return None, 'unspecified'
    if isinstance(choice, str):
        return gen_tools.load_recipe(root, choice), 'project-recipe'
    if not isinstance(choice, dict):
        raise RecipeError('candidate must be recipe data, gen: id or an author response')
    if 'recipe' in choice:
        return copy.deepcopy(choice['recipe']), choice.get('model', 'unspecified')
    return copy.deepcopy(choice), 'agent-supplied-data'


def _adjust(recipe, params, errors):
    """Change selected parameter values inside their original bounds; never move a gate."""
    reason = ' '.join(errors).lower()
    props = recipe.get('parameters', {})
    new = dict(params)
    changes = []
    if 'budget' in reason or 'triangles' in reason:
        names = {value['param'] for op in recipe['operations'] for key, value in op['args'].items()
                 if key in ('segs', 'sides', 'rings', 'nu', 'nv') and isinstance(value, dict) and 'param' in value}
        for name in sorted(names):
            prop = props[name]
            if prop['type'] not in ('number', 'integer'):
                continue
            old = new[name]
            value = max(prop['minimum'], int(old * .65))
            if value < old:
                new[name] = value; changes.append({'parameter': name, 'from': old, 'to': value, 'why': 'simplify tessellation'})
    elif 'extent' in reason or 'scale' in reason:
        # Numeric class-extent errors carry measured side and bounds. Use the existing size control only.
        m = re.search(r'largest side ([0-9.]+).*?\[([0-9.]+),\s*([0-9.]+)\]', reason)
        ratio = None
        if m:
            measured, lo, hi = map(float, m.groups())
            ratio = (.95 * hi / measured) if measured > hi else (1.05 * lo / measured)
        for name in ('scale', 'size', 'height', 'length', 'width', 'depth', 'taper'):
            if name not in props or props[name]['type'] not in ('number', 'integer'):
                continue
            prop = props[name]; old = new[name]
            value = max(prop['minimum'], min(prop['maximum'], old * (ratio or .8)))
            if prop['type'] == 'integer':
                value = int(value)
            if value != old:
                new[name] = value; changes.append({'parameter': name, 'from': old, 'to': value, 'why': 'class extent/scale'})
    elif any(word in reason for word in ('palette', 'emission', 'neon', 'texture energy')):
        # Only declared palette-role alternatives are eligible. Arbitrary off-palette input is never repaired.
        for name, prop in props.items():
            if prop['type'] == 'string':
                values = prop['enum']
                index = values.index(new[name])
                if index + 1 < len(values):
                    new[name] = values[index + 1]
                    changes.append({'parameter': name, 'from': params[name], 'to': new[name], 'why': 'declared mood-role alternative'})
    return new, changes


def _kit(root, matches, pack_id, seed, python_path=''):
    from core import pipeline
    registry = pipeline.load_generators()
    gid = next((id_ for id_ in matches if id_ in registry), None)
    if gid is None:
        raise RecipeError('taxonomy has no buildable native generator for this need')
    return gid, gen_tools.build(root, gid, pack_id, seed=seed, sweep=False, python_path=python_path)


def run(root, brief, gaps, pack_id, *, candidates=None, author=None, max_tries=4, seed=0, placements=(), python_path=''):
    if isinstance(max_tries, bool) or not isinstance(max_tries, int) or not 1 <= max_tries <= 4:
        raise ValueError('max_tries must be an integer in [1,4]')
    p = gen_tools.workspace(root)
    pack = gen_tools.resolve_pack(p.root, pack_id)
    rows_in = gaps.get('rows')
    if not isinstance(rows_in, list) or len(rows_in) > 128:
        raise ValueError('gap report must have at most 128 rows')
    wants = [r['want'] for r in rows_in]
    if len(wants) != len(set(wants)):
        raise ValueError('duplicate gap want')
    rows = []
    candidates = candidates or {}
    for gap in rows_in:
        want = gap['want']
        row = {'want': want, 'status': 'failed', 'reason': '', 'gap_status': gap.get('status', 'missing'),
               'attempts': [], 'seed': seed, 'pack': pack_id}
        if gap.get('status') == 'not covered':
            row.update(status='not covered', reason=gap.get('why', 'outside environment generator scope'))
            rows.append(row); continue
        try:
            recipe, model = _choose(p.root, want, candidates, author, brief, p)
            if recipe is None:
                if gap.get('status') != 'exists':
                    raise RecipeError('no recipe supplied or available; no stand-in substituted')
                gid, built = _kit(p.root, gap.get('matches', []), pack_id, seed, python_path)
                row.update(id=gid, source='kit', kit_id=gid, licence='MIT', model='native-library')
                row['attempts'].append({'try': 1, 'params': {}, 'ok': built['ok'], 'errors': built['errors'], 'stage': built['stage']})
            else:
                spec = gen_tools.spec_from_recipe(recipe, brief.get('ip_terms', ()))
                gen_tools.author(p.root, recipe, model=model, brief_line=want,
                                 forbidden_terms=brief.get('ip_terms', ()), replace=(p.path('recipes/' + recipe['id'] + '.json').exists()))
                P = spec.defaults()
                gid = spec.id
                row.update(id=gid, source='generated', licence=recipe['licence'], model=model,
                           recipe_sha256=gen_tools.recipe_hash(recipe))
                built = None
                for n in range(max_tries):
                    built = gen_tools.build(p.root, gid, pack_id, params=P, seed=seed, sweep=False, python_path=python_path)
                    attempt = {'try': n + 1, 'params': dict(P), 'ok': built['ok'], 'errors': built['errors'],
                               'stage': built['stage'], 'gate_scope': 'selected parameters; exemplar ranges swept separately'}
                    row['attempts'].append(attempt)
                    gen_tools.log_call(p, 'attempt', brief_line=want, id=gid, **attempt)
                    if built['ok']:
                        break
                    P, changes = _adjust(recipe, P, built['errors'])
                    if not changes:
                        break
                    attempt['next_changes'] = changes
                    gen_tools.log_call(p, 'adjust', brief_line=want, changes=changes)
            if built is None or not built['ok']:
                raise RecipeError('; '.join((built or {}).get('errors', ['candidate not built'])))
            row.update(status=('generated' if recipe is not None else ('remapped' if pack.d.get('mood') else 'existed')),
                       reason='', file=built['file'], sha256=built['sha256'], tri_count=built['tri_count'],
                       pack_sha256=built['pack_sha256'], gates={'ok': True, 'bible': built['screen'],
                           'file': built['validation'], 'texture': built['texture_fidelity'],
                           'structure': built['structure'], 'determinism': built['determinism']},
                       params=row['attempts'][-1]['params'])
            provenance.record(p.root, dict(row, licence_required=True))
            gen_tools.log_call(p, 'keep', brief_line=want, id=gid, file=row['file'], sha256=row['sha256'])
        except (RecipeError, ValueError, Fault) as e:
            reason = ' '.join(str(e).splitlines())[:400]
            row.update(status='failed', reason=reason)
            if not row['attempts']:
                row['attempts'].append({'try': 1, 'ok': False, 'errors': [reason], 'params': {}})
            gen_tools.log_call(p, 'drop', brief_line=want, reason=reason, attempts=len(row['attempts']))
        rows.append(row)
        # Persist after every need, so timeout/interruption does not erase completed work.
        partial = asset_report.make(p.root, rows, brief, placements=())
        p.write_json('.maker/generators/progress.json', partial)
    report = asset_report.make(p.root, rows, brief, placements=placements)
    return asset_report.write(p.root, report)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', required=True); ap.add_argument('--brief', required=True)
    ap.add_argument('--gaps', required=True); ap.add_argument('--pack', required=True)
    ap.add_argument('--candidates', help='JSON mapping of brief lines to recipe data or gen: ids')
    ap.add_argument('--tries', type=int, default=4); ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args(argv)
    try:
        report = run(a.project, json.loads(Path(a.brief).read_text(encoding='utf-8')), json.loads(Path(a.gaps).read_text(encoding='utf-8')), a.pack,
                     candidates=json.loads(Path(a.candidates).read_text(encoding='utf-8')) if a.candidates else {}, max_tries=a.tries, seed=a.seed)
        print(asset_report.text(report), end='')
        return 0 if report['counts']['failed'] == 0 else 3
    except (ValueError, Fault) as e:
        print('REJECTED: ' + ' '.join(str(e).splitlines())[:240]); return 2


if __name__ == '__main__': sys.exit(main())
