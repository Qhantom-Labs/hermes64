"""Recipe -> GLB -> gates. One pass builds a batch with the selected character exporter; a second pass proves
determinism; every item then runs the full gate set (adventure_maker.character_gate) before anything is shown.

    res = build(recipes, lock, out_dir, invoke=fn, exporter='python', python='/usr/bin/python3', blender=None)

Exporters (adventure_maker.nbchars.select_exporter, setting `character_exporter` = auto | python | blender):
  python   `python -m adventure_maker.nbchars export --job` (nbchars.build_job): skinned + animated GLBs in pure
           Python + numpy, no Blender. Every item kind builds, robots through adventure_maker.character_robot.
  blender  characters/gen/build.py under Blender (the original pipeline, kept as the oracle and fallback).
Review renders (front / three-quarter / side + the game-scale room shot) feed the contact sheets and the silhouette
gate. They are Blender renders: with the python exporter and Blender configured, Blender renders its own build of
the same items (equivalent within tolerance, docs/MERGE4-LOG.md) and the shipped GLB stays the python one; without
Blender there are no renders, the silhouette gate is reported as not run (never as passed) and every other gate
runs. A Blender-free renderer for sheets is a follow-up (docs/MERGE4-RESULT.md).

`invoke(argv, cwd, timeout)` runs one child process and returns {'returncode', 'stdout', 'stderr'}: the plugin passes
adventure_maker.runner.Runner(project).run (macOS sandbox, project-confined writes, no network); repository proofs
pass tools.charsys_blender's scrubbed-environment runner.
"""
import hashlib
import json
import shutil
from pathlib import Path

from . import character_gate as GATE
from . import character_recipe as CR

ROOT = Path(__file__).resolve().parents[1]
BUILD_PY = ROOT / 'characters' / 'gen' / 'build.py'
VIEWS = ['front', 'three_quarter', 'side']
NO_RENDERER = ('no review renders: Blender is not configured (renders are Blender-only for now); the silhouette gate '
               'did not run and no contact sheet was made')
AUDIT_KIND = {'person': 'human', 'masked': 'human', 'animal': 'quad'}


def blender_argv(blender, job_path, out_dir):
    return [str(blender), '--background', '--factory-startup', '--disable-autoexec', '--python', str(BUILD_PY), '--',
            '--job', str(job_path), '--out', str(out_dir)]


def python_argv(python, job_path, out_dir):
    return [str(python), '-B', '-m', 'adventure_maker.nbchars', 'export', '--job', str(job_path), '--out', str(out_dir),
            '--exporter', 'python']


def doctor(blender, exporter=None):
    """One line: can this host generate new character bodies (and review renders)?"""
    if exporter == 'python':
        tail = (' Blender at %s adds review renders (contact sheets, silhouette gate).' % blender if blender else
                ' Blender is optional: without it there are no review renders (no contact sheets, silhouette gate not run).')
        return {'ok': True, 'message': 'New bodies, rigs and clips build without Blender (python exporter, numpy).' + tail}
    if blender and Path(blender).is_file():
        return {'ok': True, 'message': 'Blender found at %s: new bodies, rigs and clips can be generated.' % blender}
    return {'ok': False, 'message': ('No character exporter: the python exporter needs numpy in python_path (and a PASS '
                                     'parity verdict for character_exporter=auto); character_exporter=blender needs '
                                     'blender_path. Already-exported characters can still be bound and validated.')}


def _write_job(items, packs, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / 'job.json'
    jp.write_bytes(json.dumps({'schema': 'hermes64-charsys-job/1', 'packs': packs, 'items': items}, indent=1, sort_keys=True).encode('utf-8'))
    return out_dir, jp


def _run_job(items, packs, out_dir, invoke, blender, timeout):
    out_dir, jp = _write_job(items, packs, out_dir)
    res = invoke(blender_argv(blender, jp, out_dir), ROOT, timeout)
    if res.get('returncode') != 0 or 'BUILD COMPLETE' not in res.get('stdout', ''):
        tail = (res.get('stdout', '') + res.get('stderr', ''))[-1500:]
        raise RuntimeError('blender build failed (exit %s): %s' % (res.get('returncode'), tail))
    return json.loads((out_dir / 'build-report.json').read_text(encoding='utf-8'))


def _glb_height(path):
    """Top of the rest-pose body (glTF +Y = the generator's +Z): the build report's height_m."""
    raw, doc, binary = GATE._load(path)
    top = None
    skinned = {n['mesh'] for n in doc.get('nodes', []) if 'mesh' in n and 'skin' in n}
    for mi, _pi, prim in GATE._skinned_prims(doc):
        if mi not in skinned:
            continue
        pos = GATE._acc(doc, binary, prim['attributes']['POSITION']).reshape(-1, 3)
        y = float(pos[:, 1].max())
        top = y if top is None else max(top, y)
    return top or 0.


def _complete(info, item, out_dir):
    """Fill a python report row up to characters/gen/build.py's row (audit, triangle split, height, robot facts)."""
    path = Path(out_dir) / info['file']
    kind = item['kind']
    n_clips = len(item['clips']) if item.get('clips') else (len(info['clips']) if kind == 'robot' else 7)
    au = CR.gen_module('core.glb').GLB(path).audit(kind=AUDIT_KIND.get(kind), n_clips=n_clips)
    info.update(tris_glb_total=au['tris'], tris_props=au['tris_props'], clips=[x['name'] for x in au['animations']],
                audit_errors=au['errors'], height_m=round(_glb_height(path), 4))
    if kind == 'robot':
        _, doc, _ = GATE._load(path)
        rig = next((n.get('extras', {}) for n in doc.get('nodes', []) if n.get('name', '').startswith('rig_')), {})
        info.update(tris_crown=au['tris_props'].get('kit_acc_head_crown', 0), hover_m=rig.get('hover_m', 0.),
                    robot_body=rig.get('robot_body'))
    return info


def _run_job_python(items, packs, out_dir, invoke, python, timeout):
    out_dir, jp = _write_job(items, packs, out_dir)
    res = invoke(python_argv(python, jp, out_dir), ROOT, timeout)
    if res.get('returncode') != 0 or 'BUILD COMPLETE' not in res.get('stdout', ''):
        tail = (res.get('stdout', '') + res.get('stderr', ''))[-1500:]
        raise RuntimeError('python character export failed (exit %s): %s' % (res.get('returncode'), tail))
    rep = json.loads((out_dir / 'build-report.json').read_text(encoding='utf-8'))
    by_id = {it['id']: it for it in items}
    for info in rep['items']:
        _complete(info, by_id[info['id']], out_dir)
    (out_dir / 'build-report.json').write_bytes(json.dumps(rep, indent=1, sort_keys=True).encode('utf-8'))
    return rep


def _review_renders(items, packs, out_dir, invoke, blender, timeout):
    """Blender review renders of the same items next to the python-built GLBs (renders/<id>_<view>.png); Blender's
    own GLBs stay in the scratch folder, which is removed."""
    scratch = Path(out_dir) / '.review'
    _run_job(items, packs, scratch, invoke, blender, timeout)
    dest = Path(out_dir) / 'renders'
    dest.mkdir(parents=True, exist_ok=True)
    for png in sorted((scratch / 'renders').glob('*.png')):
        shutil.copyfile(png, dest / png.name)
    shutil.rmtree(scratch, ignore_errors=True)


def room_colours(lock):
    pal = dict(lock.colours)
    # the wall must not match the sheet background (cloth_light), or the room reads as an empty slab
    return {'floor': pal[lock.resolve('metal_mid').split('+')[0]], 'wall': pal[lock.resolve('metal_light').split('+')[0]]}


def compile_all(recipes, lock, render=True):
    items, reports, refused = [], {}, {}
    spec = {'views': VIEWS, 'room': room_colours(lock)} if render else None
    for rec in recipes:
        rid = rec.get('id', '?') if isinstance(rec, dict) else '?'
        try:
            item, rep = CR.compile_build(rec, lock, out='%s.glb' % rid, render=spec)
        except CR.RecipeError as exc:
            refused[rid] = {'code': exc.code, 'message': str(exc)}
            continue
        items.append(item)
        reports[rid] = rep
    return items, reports, refused


def _bare(items):
    out = [dict(it) for it in items]
    for it in out:
        it.pop('render', None)
    return out


def build(recipes, lock, out_dir, *, invoke, blender=None, render=True, determinism=True, rigkit_root=None, keys='all',
          timeout=900, exporter='blender', python=None):
    """exporter 'blender' (default: the original pipeline the repository proofs use) or 'python' (python = an
    interpreter with numpy; blender is then optional and only renders the review images)."""
    if exporter not in ('blender', 'python'):
        raise ValueError('exporter must be blender or python, got %r' % (exporter,))
    out_dir = Path(out_dir)
    items, reports, refused = compile_all(recipes, lock, render)
    result = {'schema': 'hermes64-character-build/1.0.0', 'lock': lock.receipt(), 'items': {}, 'refused': refused,
              'exporter': exporter}
    if not items:
        return result
    packs = lock.inline()
    review = None
    if exporter == 'python':
        built = {x['id']: x for x in _run_job_python(_bare(items), packs, out_dir, invoke, python, timeout)['items']}
        if render and blender:
            _review_renders(items, packs, out_dir, invoke, blender, timeout)
        elif render:
            review = NO_RENDERER
    else:
        built = {x['id']: x for x in _run_job(items, packs, out_dir, invoke, blender, timeout)['items']}
    result['review_renders'] = None if not render else ('blender' if blender else 'unavailable')
    again = {}
    if determinism:
        det_dir = out_dir / '.determinism'
        if exporter == 'python':
            again = {x['id']: x for x in _run_job_python(_bare(items), packs, det_dir, invoke, python, timeout)['items']}
        else:
            again = {x['id']: x for x in _run_job(_bare(items), packs, det_dir, invoke, blender, timeout)['items']}
        shutil.rmtree(det_dir, ignore_errors=True)
    palette = [h for _, h in lock.colours]
    for it in items:
        rid = it['id']
        info, rep = built[rid], reports[rid]
        glb = out_dir / info['file']
        renders = [str(out_dir / 'renders' / ('%s_%s.png' % (rid, v))) for v in VIEWS] if render else []
        renders = [p for p in renders if Path(p).is_file()]
        det = None
        if determinism:
            same = again.get(rid, {}).get('sha256') == info['sha256']
            det = {'ok': same, 'errors': [] if same else ['determinism: second build differs (%s vs %s)' % (
                info['sha256'][:12], again.get(rid, {}).get('sha256', '?')[:12])], 'sha256': info['sha256']}
        rig_id = rep['rig'].split('@')[0]
        gates = GATE.run(glb, rig=rig_id, clips=rep['clips'], profile='hover' if rep['hover'] else 'grounded',
                         palette_hex=palette, kind=it['kind'], params_json=info.get('params_json') if it['kind'] == 'person' else None,
                         audit_errors=info.get('audit_errors', []), renders=renders, determinism=det,
                         rigkit_root=rigkit_root, keys=keys, review=review)
        result['items'][rid] = {'ok': gates['ok'], 'glb': str(glb), 'sha256': info['sha256'], 'bytes': info['bytes'],
                                'tris_body': info.get('tris_body'), 'clips': info['clips'], 'height_m': info.get('height_m'),
                                'renders': renders, 'recipe': rep, 'gates': gates, 'exporter': exporter}
    (out_dir / 'gates.json').write_bytes(json.dumps(result, indent=1, sort_keys=True).encode('utf-8'))
    return result


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
