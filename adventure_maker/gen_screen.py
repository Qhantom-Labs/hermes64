"""Screen data-only recipes: closed schema, bounded sweep, bible and deterministic meshes.

File gates and texture fidelity run during build; room/frame gates cannot be inferred here.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'kits') not in sys.path:
    sys.path.append(str(ROOT / 'kits'))

from core.gen_recipe import RecipeError, canonical, recipe_hash, spec_from_recipe


def bundle_tool(name):
    """tools/<name>.py of this bundle, loaded by path: inside a Hermes process `tools` is Hermes's own package."""
    import importlib.util
    key = 'hermes64_bundle_tools_' + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, ROOT / 'tools' / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return sys.modules[key]


SB = bundle_tool('style_bible')


def check_determinism(build):
    """Compare canonical content, not reprs/timestamps or elapsed seconds."""
    try:
        def fingerprint():
            value = build()
            if hasattr(value, 'nodes'):
                value = {'nodes': [{'name': n.name, 'kind': n.kind, 'v': n.mesh.v, 'f': n.mesh.f,
                                    'roles': n.mesh.r, 'smooth': n.mesh.s, 'uv': n.mesh.uv,
                                    'origin': n.origin} for n in value.nodes], 'meta': value.meta}
            raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            return hashlib.sha256(raw).hexdigest()
        first, second = fingerprint(), fingerprint()
        return {'ok': first == second, 'sha256': first, 'repeat_sha256': second,
                'reason': '' if first == second else 'non-deterministic build'}
    except (TypeError, ValueError) as e:
        return {'ok': False, 'reason': 'non-deterministic/non-finite build: ' + str(e).splitlines()[0]}


def variants(spec):
    default = spec.defaults()
    out = [('default', default)]
    for name, p in spec.schema['properties'].items():
        values = p.get('enum', [p.get('minimum'), p.get('maximum')])
        for index, value in enumerate(values):
            if value != default[name]:
                out.append((name + ':' + str(index), dict(default, **{name: value})))
    return out


def screen(recipe, pack, params=None, seed=0, forbidden_terms=(), sweep=True, project_dir=None):
    result = {'ok': False, 'errors': [], 'warnings': [], 'sweep': [], 'gates_scope':
              'closed recipe + parameter extremes + in-memory bible + mesh determinism; not frame/style approval'}
    try:
        spec = spec_from_recipe(recipe, forbidden_terms, project_dir)
        result['recipe_sha256'] = recipe_hash(recipe)
        bible = SB.load()
        cp = SB.check_pack(bible, pack.d)
        if not cp['ok']:
            raise RecipeError('; '.join(cp['errors']))
        tries = variants(spec) if sweep else [('selected', params or spec.defaults())]
        if params is not None and sweep:
            tries.append(('selected', params))
        for label, P in tries:
            try:
                a = spec.build(P, seed)
                summary = SB.summarize_asset(a, spec.cls)
                used = summary['roles']
                missing = [r for r in used if r not in pack.materials]
                if missing:
                    raise RecipeError('pack has no material for role ' + missing[0])
                gate = SB.check_asset(bible, summary)
                deterministic = check_determinism(lambda: spec.build(P, seed))
                errors = gate['errors'] + ([] if deterministic['ok'] else [deterministic['reason']])
                row = {'label': label, 'params': P, 'ok': not errors, 'summary': summary,
                       'bible': gate, 'determinism': deterministic, 'errors': errors}
                result['warnings'] += gate['warnings']
            except (RecipeError, ValueError) as e:
                row = {'label': label, 'params': P, 'ok': False, 'errors': [' '.join(str(e).splitlines())]}
            result['sweep'].append(row)
            result['errors'] += [label + ': ' + e for e in row['errors']]
        result['ok'] = not result['errors']
    except (RecipeError, ValueError, KeyError) as e:
        result['errors'].append(' '.join(str(e).splitlines())[:240])
    return result
