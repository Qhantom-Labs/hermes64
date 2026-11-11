"""Data-only generator surface (CLI + skill, zero new Hermes tool schemas).

python -m adventure_maker.gen_tools {author,screen,build,list} --project PROJECT ...
Builds run in the existing no-network/write-confined Runner, with deterministic replay.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'kits') not in sys.path:
    sys.path.append(str(ROOT / 'kits'))

from core.gen_recipe import RecipeError, canonical, decode, generic_id, load_recipe, recipe_hash, spec_from_recipe
from core.packs import Pack
from adventure_maker.safety import Project, inspect_path, Fault
from adventure_maker.gen_screen import screen


def workspace(root):
    root = inspect_path(Path(root).absolute())
    root.mkdir(parents=True, exist_ok=True)
    marker = inspect_path(root / '.maker/project.json')
    if not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(json.dumps({'format': 1, 'name': root.name}).encode('utf-8'))
    return Project(root.parent, root.name)


def log_call(project, action, **fields):
    path = project.path('.maker/generators/calls.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(dict(action=action, **fields), sort_keys=True, allow_nan=False) + '\n')


def author(root, recipe, *, model='unspecified', brief_line='', forbidden_terms=(), replace=False):
    spec = spec_from_recipe(recipe, forbidden_terms)
    p = workspace(root)
    path = p.path('recipes/' + recipe['id'] + '.json')
    if path.exists() and not replace:
        raise RecipeError('project recipe already exists; use explicit replace')
    p.write_bytes(str(path.relative_to(p.root)), canonical(recipe) + b'\n')
    row = {'id': spec.id, 'recipe_sha256': recipe_hash(recipe), 'model': model, 'brief_line': brief_line,
           'licence': recipe['licence'], 'replaced': replace}
    p.write_json('.maker/generators/authors/' + recipe['id'] + '.json', row)
    log_call(p, 'author', **row)
    return row


def list_recipes(root):
    p = workspace(root)
    folder = p.path('recipes')
    out = []
    paths = sorted(folder.glob('*.json')) if folder.exists() else []
    if len(paths) > 64:
        raise RecipeError('project recipe count exceeds 64')
    for path in paths:
        doc = load_recipe(p.root, 'gen:' + path.stem)
        spec = spec_from_recipe(doc)
        out.append({'id': spec.id, 'class': spec.cls, 'recipe_sha256': recipe_hash(doc), 'licence': doc['licence']})
    return out


def resolve_pack(root, pack_id):
    # Only an id, never a caller-controlled path. Project packs take priority.
    if not isinstance(pack_id, str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', pack_id):
        raise RecipeError('pack id must be a lowercase slug')
    p = workspace(root)
    local = p.path('kits/packs/' + pack_id + '/pack.json')
    path = local if local.is_file() else ROOT / 'kits/packs' / pack_id / 'pack.json'
    if not path.is_file():
        raise RecipeError('pack not found: ' + pack_id)
    pack = Pack(str(path))
    if pack.id != pack_id:
        raise RecipeError('pack id must match its folder')
    return pack


def screen_project(root, gid, pack_id, params=None, seed=0, *, sweep=True, forbidden_terms=()):
    p = workspace(root)
    result = screen(load_recipe(p.root, gid), resolve_pack(p.root, pack_id), params, seed, forbidden_terms, sweep)
    log_call(p, 'screen', id=gid, pack=pack_id, ok=result['ok'], errors=result['errors'])
    return result


def _texture_gate(pack, textures):
    from core import look, png
    values = {}
    prefix = 'tex_' + pack.id + '_'
    for name, row in textures.items():
        # Native builders report absolute PNG file paths; none are accepted from recipe input.
        role = name[len(prefix):] if name.startswith(prefix) else name
        values[role] = png.read(str(row['path']))
    return look.continuity(values, pack.d)


def child(request_file):
    """Trusted child entry point. No recipe can supply code or select a module to load."""
    from core import pipeline
    from adventure_maker.glb_validate import validate as structural
    req = json.loads(Path(request_file).read_text(encoding='utf-8'))
    p = workspace(req['project'])
    is_recipe = req['id'].startswith('gen:')
    doc = load_recipe(p.root, req['id']) if is_recipe else None
    pack = resolve_pack(p.root, req['pack'])
    if is_recipe:
        gate = screen(doc, pack, req['params'], req['seed'], sweep=req['sweep'])
    else:
        from adventure_maker.gen_screen import SB
        spec = pipeline.load_generators().get(req['id'])
        if spec is None:
            raise RecipeError('unknown native generator id')
        P = pipeline.resolve(spec, pack, params=req['params'])
        gate = SB.check_asset(SB.load(), SB.summarize_asset(spec.build(P, req['seed']), spec.cls))
    result = {'ok': False, 'screen': gate, 'errors': list(gate['errors']),
              'pack_sha256': hashlib.sha256(pack.raw_bytes).hexdigest(), 'seed': req['seed']}
    if is_recipe:
        result['recipe_sha256'] = recipe_hash(doc)
    stage = p.path(req['stage'])
    if gate['ok']:
        reports = []
        for i in range(2):
            out = stage / ('check%d.glb' % i)
            out.parent.mkdir(parents=True, exist_ok=True)
            status, rep = pipeline.build_one(req['id'], req['pack'], params=req['params'], seed=req['seed'],
                out=str(out), tex_dir=str(stage / ('textures%d' % i)), builder='python',
                pack_path=pack.path, project_dir=p.root)
            reports.append(dict(rep, status=status))
            if status != 'passed':
                result['errors'].append(rep.get('error') or '; '.join(k + ': ' + v.get('reason', '')
                    for k, v in rep.get('validation', {}).items() if not v.get('ok')))
                break
        result['builds'] = reports
        if len(reports) == 2 and not result['errors']:
            a, b = reports
            result['determinism'] = {'ok': a['sha256'] == b['sha256'], 'sha256': a['sha256'], 'repeat_sha256': b['sha256']}
            if not result['determinism']['ok']:
                result['errors'].append('non-deterministic GLB build')
            limit = a['tri_limit']
            struct = structural((stage / 'check0.glb').read_bytes(), 'recipe.glb', limit)
            result['structure'] = {'ok': struct.ok, 'issues': struct.issues}
            if not struct.ok:
                result['errors'].append('GLB structure failed')
            texture_gate = _texture_gate(pack, a['textures_written'])
            result['texture_fidelity'] = texture_gate
            if not texture_gate['ok']:
                result['errors'] += texture_gate['errors']
            result.update(sha256=a['sha256'], tri_count=a['tri_count'], bytes=a['bytes'],
                          validation=a['validation'], meta=a['meta'])
        result['ok'] = not result['errors']
    p.write_json(req['stage'] + '/result.json', result)
    return 0 if result['ok'] else 3


def build(root, gid, pack_id, *, params=None, seed=0, sweep=True, python_path='') -> dict:
    from adventure_maker.runner import Runner, locate
    p = workspace(root)
    is_recipe = isinstance(gid, str) and gid.startswith('gen:')
    doc = load_recipe(p.root, gid) if is_recipe else None
    pack = resolve_pack(p.root, pack_id)
    if is_recipe:
        spec_from_recipe(doc)
        slug = doc['id']
    else:
        from core import pipeline
        if gid not in pipeline.load_generators():
            raise RecipeError('unknown native generator id')
        slug = gid.replace('.', '_')
    source_hash = hashlib.sha256(b''.join(f.read_bytes() for f in sorted((ROOT / 'kits/core').glob('*.py')))).hexdigest()
    key_data = {'recipe': recipe_hash(doc) if is_recipe else gid, 'pack': hashlib.sha256(pack.raw_bytes).hexdigest(),
                'params': params or {}, 'seed': seed, 'sweep': sweep, 'generator_sources': source_hash}
    key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    stage_rel = '.maker/local/gen/' + slug + '/' + key
    stage = p.path(stage_rel); stage.mkdir(parents=True, exist_ok=True)
    request = {'project': str(p.root), 'id': gid, 'pack': pack_id, 'params': params or {}, 'seed': seed,
               'stage': stage_rel, 'sweep': sweep}
    p.write_json(stage_rel + '/request.json', request)
    argv = [locate('python', python_path), '-I', '-B', str(Path(__file__).resolve()), '_build-child', str(stage / 'request.json')]
    runner = Runner(p)
    sandbox_argv = runner.sandbox_argv(argv)
    if (stage / 'result.json').is_file():
        (stage / 'result.json').unlink()   # never read a stale receipt from an earlier run of the same key
    process = runner.run(argv, p.root, timeout=180)
    p.write_json(stage_rel + '/process.json', dict(process, argv=argv, sandbox_argv=sandbox_argv))
    result = p.read_json(stage_rel + '/result.json') if (stage / 'result.json').is_file() else {
        'ok': False, 'errors': ['recipe child failed: ' + (process['stderr'] or process['stdout'])[-400:].replace('\n', ' ')]}
    if not isinstance(result, dict):
        raise RecipeError('recipe child returned a non-object receipt')
    result['process'] = {'returncode': process['returncode'], 'argv': argv, 'sandbox_argv': sandbox_argv,
                         'elapsed_seconds': process['elapsed_seconds']}
    result['stage'] = stage_rel
    result['ok'] = result['ok'] and process['returncode'] == 0
    if not result['ok'] and not result.get('errors'):
        result['errors'] = ['recipe child exited with code %s' % process['returncode']]
    if result['ok']:
        dest = ('assets/generated/' if is_recipe else 'assets/kit/') + slug + '/' + key + '/asset.glb'
        raw = (stage / 'check0.glb').read_bytes()
        if hashlib.sha256(raw).hexdigest() != result['sha256']:
            raise RecipeError('staged recipe GLB hash changed')
        p.write_bytes(dest, raw)
        if is_recipe:
            p.write_bytes(dest.replace('asset.glb', 'recipe.json'), canonical(doc) + b'\n')
        result['file'] = dest
        p.write_json(dest.replace('asset.glb', 'gates.json'), result)
        from adventure_maker import provenance
        author_meta = p.path('.maker/generators/authors/' + slug + '.json')
        model = p.read_json(str(author_meta.relative_to(p.root))).get('model', 'unspecified') if author_meta.is_file() else 'native-library'
        record = {'id': gid, 'file': dest, 'sha256': result['sha256'], 'seed': seed,
                  'source': 'generated' if is_recipe else 'kit', 'model': model,
                  'licence': doc['licence'] if is_recipe else 'MIT', 'licence_required': True,
                  'pack': pack_id, 'pack_sha256': result['pack_sha256'], 'params': params or {},
                  'gates': {'ok': True, 'bible': result['screen'], 'file': result['validation'],
                            'texture': result['texture_fidelity'], 'structure': result['structure'],
                            'determinism': result['determinism']}}
        if is_recipe:
            record['recipe_sha256'] = result['recipe_sha256']
        else:
            record['kit_id'] = gid
        provenance.record(p.root, record)
    else:
        # Failed candidates are not exported or promoted. Keep diagnostics, not failed meshes.
        for file in stage.glob('check*.glb'):
            file.unlink()
    log_call(p, 'build', id=gid, pack=pack_id, recipe_sha256=recipe_hash(doc) if is_recipe else None, seed=seed,
             ok=result['ok'], errors=result['errors'], file=result.get('file'))
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '_build-child':
        return child(argv[1])
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['author', 'screen', 'build', 'list'])
    ap.add_argument('--project', required=True)
    ap.add_argument('--recipe', help='JSON data file to copy into the project; never Python')
    ap.add_argument('--id', help='gen:<generic_name>')
    ap.add_argument('--pack', default='castle_keep')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--params', default='{}')
    ap.add_argument('--model', default='unspecified')
    ap.add_argument('--brief-line', default='')
    ap.add_argument('--replace', action='store_true')
    args = ap.parse_args(argv)
    try:
        if args.action == 'author':
            if not args.recipe:
                raise RecipeError('author requires --recipe JSON file')
            out = author(args.project, decode(Path(args.recipe).read_bytes()), model=args.model,
                         brief_line=args.brief_line, replace=args.replace)
        elif args.action == 'list':
            out = list_recipes(args.project)
        else:
            if not args.id:
                raise RecipeError('screen/build requires --id gen:<name>')
            params = json.loads(args.params)
            out = screen_project(args.project, args.id, args.pack, params, args.seed) if args.action == 'screen' else \
                  build(args.project, args.id, args.pack, params=params, seed=args.seed)
        print(json.dumps(out, sort_keys=True, allow_nan=False))
        return 0 if not isinstance(out, dict) or out.get('ok', True) else 3
    except (RecipeError, Fault, ValueError, OSError) as e:
        print('REJECTED: ' + ' '.join(str(e).splitlines())[:240])
        return 2


if __name__ == '__main__':
    sys.exit(main())
