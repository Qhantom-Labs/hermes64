"""Creator build orchestration in the plugin process (stdlib; the gates use numpy as the existing gates do).

compile (stdlib) -> job file -> the build child through the caller's sandboxed invoke (Runner) -> a second child run
into a scratch folder for the determinism gate -> character_gate.run on every GLB (GLB audit, rig kit with every
clip and every key, palette = the creator's master palette, no cuboids, silhouette on the child's renders,
determinism). Result rows have the shape character_pipeline.build returns, plus card_fit and the contact sheet.
"""
import json
import shutil
from pathlib import Path

from . import CreatorError, ROOT, compile as compile_recipe, data, master_palette

CHILD = ['-B', '-m', 'adventure_maker.charcreator', 'build']


def child_argv(python, job, out):
    return [str(python)] + CHILD + ['--job', str(job), '--out', str(out)]


def _run_child(items, out_dir, invoke, python, timeout):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    job = out_dir / 'job.json'
    job.write_text(json.dumps({'schema': 'hermes64-creator-job/1', 'items': items}, indent=1, sort_keys=True), encoding='utf-8')
    res = invoke(child_argv(python, job, out_dir), ROOT, timeout)
    if res.get('returncode') != 0 or 'BUILD COMPLETE' not in (res.get('stdout') or ''):
        tail = ((res.get('stdout') or '') + (res.get('stderr') or ''))[-1500:]
        raise RuntimeError('creator build failed (exit %s): %s' % (res.get('returncode'), tail))
    return {r['id']: r for r in json.loads((out_dir / 'build-report.json').read_text(encoding='utf-8'))['items']}


def _audit(path, n_clips):
    from ..character_recipe import gen_module
    au = gen_module('core.glb').GLB(path).audit(kind='human', n_clips=n_clips)
    return au.get('errors', [])


def build(recipes, out_dir, *, invoke, python, render=True, determinism=True, rigkit_root=None, keys='all', timeout=600):
    from .. import character_gate as GATE
    out_dir = Path(out_dir)
    d = data()
    items, reports, refused = [], {}, {}
    for rec in recipes:
        rid = rec.get('id', '?') if isinstance(rec, dict) else '?'
        try:
            params, rep = compile_recipe(rec)
        except CreatorError as exc:
            refused[rid] = {'code': exc.code, 'message': str(exc)}
            continue
        items.append({'id': rid, 'params': params, 'out': '%s.glb' % rid, 'render': bool(render)})
        reports[rid] = rep
    result = {'schema': 'hermes64-character-build/1.0.0', 'lock': {'lock': 'creator64', 'kind': 'creator'}, 'items': {},
              'refused': refused, 'exporter': 'creator', 'review_renders': 'software' if render else None}
    if not items:
        return result
    built = _run_child(items, out_dir, invoke, python, timeout)
    again = {}
    if determinism:
        det_dir = out_dir / '.determinism'
        again = _run_child([dict(it, render=False, measure=False) for it in items], det_dir, invoke, python, timeout)
        shutil.rmtree(det_dir, ignore_errors=True)
    palette = master_palette()
    clips = list(d['clips'])
    for it in items:
        rid = it['id']
        info, rep = built[rid], reports[rid]
        glb = out_dir / info['file']
        det = None
        if determinism:
            same = again.get(rid, {}).get('sha256') == info['sha256']
            det = {'ok': same, 'errors': [] if same else ['determinism: second build differs (%s vs %s)' % (
                info['sha256'][:12], again.get(rid, {}).get('sha256', '?')[:12])], 'sha256': info['sha256']}
        renders = [p for p in info.get('renders', []) if Path(p).is_file()]
        gates = GATE.run(glb, rig='human16_v1', clips=clips, profile='grounded', palette_hex=palette, kind='creator',
                         params_json=None, audit_errors=_audit(glb, len(clips)), renders=renders, determinism=det,
                         rigkit_root=rigkit_root, keys=keys, review=None if render else 'renders not requested')
        rep = dict(rep, tris={'body': info['tris_body'], 'props': info['tris_props']})
        result['items'][rid] = {'ok': gates['ok'], 'glb': str(glb), 'sha256': info['sha256'], 'bytes': info['bytes'],
                                'tris_body': info['tris_body'], 'tris_props': info['tris_props'], 'clips': info.get('clips', clips),
                                'height_m': info['height_m'], 'renders': renders, 'recipe': rep, 'gates': gates,
                                'exporter': 'creator', 'card_fit': info.get('card_fit'), 'unique_colours': info['unique_colours'],
                                'guard_softened': info.get('guard_softened', {}),
                                'sheet': str(out_dir / info['sheet']) if info.get('sheet') else None}
    (out_dir / 'gates.json').write_text(json.dumps(result, indent=1, sort_keys=True), encoding='utf-8')
    return result
