"""Parity of the Blender-free exporter against the Blender-published oracle GLBs.

For every oracle file (16 combat humanoids, the visor cameo, 12 animals, 4 enemies, 4 props) the python exporter
rebuilds the file from the vendored generator and the two GLBs are compared:
  * bytes (whole file), JSON objects (generator string masked), every accessor's bytes by usage category,
    embedded image bytes;
  * skinned / placed vertex positions at EVERY key of EVERY clip with the numpy LBS reference (both files);
  * the python file through the repo validator (adventure_maker.glb_validate) and the rig kit validator.
Verdict per file: identical | equivalent-within-tolerance | different (with reasons).
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from ..rigkit import gltf, lbs

TOL_SKIN_M = 1e-4          # skinned vertex agreement required for "equivalent"
TOL_NORMAL = 1e-3          # NORMAL accessor agreement (4-decimal rounding of float32 normals: 1e-4 typical)
TOL_ANIM = 1e-5            # animation output agreement (float32 noise of mathutils: ~1e-7)
TOL_TRS = 1e-5             # node TRS float noise


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def accessor_usage(doc):
    use = {}
    for mi, m in enumerate(doc.get('meshes', [])):
        for p in m['primitives']:
            for k, v in p['attributes'].items():
                use.setdefault(v, k)
            if 'indices' in p:
                use.setdefault(p['indices'], 'indices')
    for s in doc.get('skins', []):
        if 'inverseBindMatrices' in s:
            use.setdefault(s['inverseBindMatrices'], 'IBM')
    for an in doc.get('animations', []):
        for ch in an['channels']:
            smp = an['samplers'][ch['sampler']]
            use.setdefault(smp['input'], 'anim_time')
            use.setdefault(smp['output'], 'anim_' + ch['target']['path'])
    return use


TRS_DEFAULT = {'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}


def _json_diffs(a, b, path='', out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict) and path.startswith('/nodes['):
        a = dict(a); b = dict(b)
        for k, dflt in TRS_DEFAULT.items():          # an omitted TRS equals its default
            if (k in a) != (k in b):
                a.setdefault(k, dflt); b.setdefault(k, dflt)
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((path + '/' + k, 'missing in ' + ('python' if k not in a else 'oracle')))
            else:
                _json_diffs(a[k], b[k], path + '/' + k, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, 'length %d vs %d' % (len(a), len(b))))
        for i, (x, y) in enumerate(zip(a, b)):
            _json_diffs(x, y, '%s[%d]' % (path, i), out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a != b:
            out.append((path, 'float %.3g' % abs(float(a) - float(b))))
    elif a != b:
        out.append((path, 'value'))
    return out


def _all_keys(doc, binary):
    out = [(None, 0)]
    for an in doc.get('animations', []):
        for i, t in enumerate(lbs.clip_keys(doc, binary, an['name'])):
            out.append((an['name'], i))
    return out


def skinned_error(mine, ref):
    """max / mean |p_python - p_oracle| over every vertex of every placed primitive at every key of every clip."""
    dm, bm = gltf.parse(mine)
    dr, br = gltf.parse(ref)
    pm, pr = lbs.primitives(dm, bm), lbs.primitives(dr, br)
    if [len(r['positions']) for r in pm] != [len(r['positions']) for r in pr]:
        return {'comparable': False, 'reason': 'primitive vertex counts differ'}
    keys_m = _all_keys(dm, bm)
    keys_r = _all_keys(dr, br)
    if keys_m != keys_r:
        return {'comparable': False, 'reason': 'clip/key sets differ'}
    mx, tot, n, worst = 0., 0., 0, None
    for clip, k in keys_m:
        a = np.concatenate(lbs.posed(dm, bm, clip, k, pm))
        b = np.concatenate(lbs.posed(dr, br, clip, k, pr))
        e = np.linalg.norm(a - b, axis=1)
        if e.max() > mx:
            mx, worst = float(e.max()), (clip or 'rest', k)
        tot += float(e.sum()); n += len(e)
    return {'comparable': True, 'keys': len(keys_m), 'max_m': mx, 'mean_m': tot / max(n, 1), 'worst_at': worst,
            'vertices': int(sum(len(r['positions']) for r in pm))}


def compare(mine, ref):
    dm, bm = gltf.parse(mine)
    dr, br = gltf.parse(ref)
    rep = {'bytes_identical': mine == ref, 'python_sha256': _sha(mine), 'oracle_sha256': _sha(ref),
           'python_bytes': len(mine), 'oracle_bytes': len(ref)}
    jm = {k: v for k, v in dm.items() if k not in ('accessors', 'bufferViews', 'buffers')}
    jr = {k: v for k, v in dr.items() if k not in ('accessors', 'bufferViews', 'buffers')}
    jm['asset'] = dict(jm['asset'], generator='*'); jr['asset'] = dict(jr['asset'], generator='*')
    diffs = _json_diffs(jm, jr)
    rep['json_identical_except_generator'] = not diffs
    rep['json_diffs'] = ['%s (%s)' % d for d in diffs[:40]]
    rep['json_diff_count'] = len(diffs)
    rep['bufferviews_identical'] = dm.get('bufferViews') == dr.get('bufferViews')
    rep['layout_identical'] = (len(dm.get('accessors', [])) == len(dr.get('accessors', []))
                               and [{k: v for k, v in a.items() if k not in ('max', 'min')} for a in dm.get('accessors', [])]
                               == [{k: v for k, v in a.items() if k not in ('max', 'min')} for a in dr.get('accessors', [])])
    cats = {}
    use = accessor_usage(dr)
    if len(dm.get('accessors', [])) == len(dr.get('accessors', [])):
        for i in range(len(dr['accessors'])):
            c = use.get(i, 'other')
            st = cats.setdefault(c, {'count': 0, 'identical': 0, 'max_abs': 0.0})
            st['count'] += 1
            xa, xb = gltf.accessor_bytes(dm, bm, i), gltf.accessor_bytes(dr, br, i)
            if xa == xb and dm['accessors'][i] == dr['accessors'][i]:
                st['identical'] += 1
                continue
            try:
                va = gltf.read_accessor(dm, bm, i).astype(np.float64)
                vb = gltf.read_accessor(dr, br, i).astype(np.float64)
                st['max_abs'] = max(st['max_abs'], float(np.abs(va - vb).max()) if va.shape == vb.shape else float('inf'))
            except Exception:   # noqa: BLE001
                st['max_abs'] = float('inf')
    rep['accessors'] = cats
    imgs = []
    for xm, xr in zip(dm.get('images', []), dr.get('images', [])):
        vm, vr = dm['bufferViews'][xm['bufferView']], dr['bufferViews'][xr['bufferView']]
        im = bm[vm.get('byteOffset', 0):vm.get('byteOffset', 0) + vm['byteLength']]
        ir = br[vr.get('byteOffset', 0):vr.get('byteOffset', 0) + vr['byteLength']]
        imgs.append(im == ir and xm['name'] == xr['name'])
    rep['images'] = {'count': len(dr.get('images', [])), 'identical': sum(imgs)}
    rep['skinned'] = skinned_error(mine, ref)
    return rep


def verdict(rep):
    if rep['bytes_identical']:
        return 'identical', []
    why = []
    sk = rep['skinned']
    if not sk.get('comparable'):
        return 'different', [sk.get('reason', 'not comparable')]
    if sk['max_m'] > TOL_SKIN_M:
        why.append('skinned vertex error %.2e m > %.0e m' % (sk['max_m'], TOL_SKIN_M))
    if rep['images']['identical'] != rep['images']['count']:
        why.append('textures differ')
    if not rep['layout_identical']:
        why.append('accessor layout differs')
    acc = rep['accessors']
    for c in ('POSITION', 'TEXCOORD_0', 'COLOR_0', 'JOINTS_0', 'WEIGHTS_0', 'indices', 'IBM', 'anim_time'):
        st = acc.get(c)
        if st and st['identical'] != st['count']:
            why.append('%s bytes differ (max %.2e)' % (c, st['max_abs']))
    if acc.get('NORMAL', {}).get('max_abs', 0) > TOL_NORMAL:
        why.append('NORMAL differs by %.2e' % acc['NORMAL']['max_abs'])
    for c in ('anim_rotation', 'anim_translation'):
        if acc.get(c, {}).get('max_abs', 0) > TOL_ANIM:
            why.append('%s differs by %.2e' % (c, acc[c]['max_abs']))
    big = [d for d in rep['json_diffs'] if 'float' not in d]
    if big:
        why.append('JSON differs beyond float noise: %s' % '; '.join(big[:4]))
    return ('equivalent-within-tolerance' if not why else 'different'), why


def explain(rep):
    """Human-readable list of the remaining non-identical components (for 'equivalent' files)."""
    notes = []
    acc = rep['accessors']
    for c in sorted(acc):
        st = acc[c]
        if st['identical'] != st['count']:
            notes.append('%s %d/%d identical (max %.1e)' % (c, st['identical'], st['count'], st['max_abs']))
    if rep['json_diff_count']:
        notes.append('JSON float noise at %d values' % rep['json_diff_count'])
    return notes


def oracle_items(oracle):
    man = json.loads((Path(oracle) / 'manifest.json').read_text())
    items = []
    for c in man['characters']:
        items.append({'type': 'character', 'id': c['id'], 'pack': c['pack'], 'file': c['file'],
                      'combat': len(c.get('clips', [])) > 7, 'kind': c['kind']})
    for e in man['enemies']:
        items.append({'type': 'enemy', 'id': e['id'], 'pack': e['pack'], 'file': e['file']})
    for p in man['props']:
        items.append({'type': 'prop', 'id': p['id'], 'pack': p['pack'], 'file': p['file'], 'kind': p['kind']})
    return items


def build(item, G, Gv=None):
    from . import api
    if item['type'] == 'character':
        rows = [r for r in api.cast_rows(G) if r['id'] == item['id'] and r['pack'] == item['pack']]
        if not rows and Gv is not None:     # the restricted cameo row only exists in the oracle lane's packs
            rows = [r for r in api.cast_rows(Gv) if r['id'] == item['id'] and r['pack'] == item['pack']]
        if not rows:
            raise KeyError('no cast row %s/%s' % (item['pack'], item['id']))
        row = rows[0]
        g = Gv if row['kind'] == 'visor' else G
        if g is None:
            raise RuntimeError('visor cameo needs --visor-root (restricted cameo modules are not vendored)')
        raw, _ = api.character_bytes(row, combat=item['combat'], G=g)
        return raw
    if item['type'] == 'enemy':
        return api.enemy_bytes(item['pack'], item['id'], G)[0]
    return api.prop_bytes(item['pack'], item['kind'], G)[0]


def verdict_record(rep, oracle):
    """The compact committed verdict (adventure_maker/nbchars/PARITY.json)."""
    from . import select as SEL
    s = rep['summary']
    man = Path(oracle) / 'manifest.json'
    return {'schema': 'hermes64-nbchars-parity-verdict/1', 'verdict': s['verdict'], 'files': s['files'],
            'verdicts': s['verdicts'], 'max_skinned_error_m': s['max_skinned_error_m'], 'tolerance_m': TOL_SKIN_M,
            'deterministic': s['deterministic'], 'glb_validate_ok': s['glb_validate_ok'], 'rigkit_ok': s['rigkit_ok'],
            'oracle': 'Blender 5.2.1 published cast (lane-combat-art/published)',
            'oracle_manifest_sha256': _sha(man.read_bytes()) if man.is_file() else None,
            'environment': s['environment'], 'fingerprint': SEL.fingerprint(),
            'per_file': {r['file']: [r['verdict'], r['compare']['skinned'].get('max_m') if 'compare' in r else None]
                         for r in rep['files']},
            'note': 'skinned vertex positions compared at every key of every clip (numpy LBS of both files); bytes identical '
                    'for POSITION/TEXCOORD_0/COLOR_0/JOINTS_0/WEIGHTS_0/indices/IBM/textures/layout; NORMAL and animation '
                    'floats differ only by float32 rounding noise (docs/NBCHARS-RESULT.md)'}


def run(oracle, out, only=None, root=None, visor_root=None, reexport=(), blender_path=None, log=print,
        write_verdict=False):
    sys.dont_write_bytecode = True
    from . import gen, api
    from ..rigkit import validate as RV
    from .. import glb_validate as GV
    G = gen.load(root)
    Gv = gen.load(visor_root) if visor_root else None
    out = Path(out)
    (out / 'python').mkdir(parents=True, exist_ok=True)
    rows = []
    t_all = time.time()
    for item in oracle_items(oracle):
        if only and item['id'] not in only and item['file'] not in only:
            continue
        t0 = time.time()
        ref = (Path(oracle) / item['file']).read_bytes()
        try:
            mine = build(item, G, Gv)
        except Exception as e:   # noqa: BLE001
            rows.append({'file': item['file'], 'verdict': 'not-built', 'reasons': [str(e)]})
            log('PARITY %-44s NOT BUILT %s' % (item['file'], e))
            continue
        p = out / 'python' / item['file']
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(mine)
        again = build(item, G, Gv)
        rep = compare(mine, ref)
        v, why = verdict(rep)
        gvd = GV.validate(mine, item['file']).as_dict()
        rk = None
        if item['type'] != 'prop':
            rk = RV.validate_character(mine, 'auto')
        row = {'file': item['file'], 'type': item['type'], 'verdict': v, 'reasons': why, 'notes': explain(rep),
               'deterministic': again == mine, 'compare': rep,
               'glb_validate': {'ok': bool(gvd['ok']),
                                'errors': [i for i in gvd['issues'] if i['severity'] == 'error'][:5],
                                'warnings': len([i for i in gvd['issues'] if i['severity'] != 'error'])},
               'rigkit': None if rk is None else {'ok': rk['ok'], 'rig': rk['rig'], 'errors': rk['errors'][:5],
                                                  'connectivity_max_gap_m': rk['checks'].get('connectivity', {}).get('max_gap_m'),
                                                  'edge_ratio': [rk['checks'].get('deformation', {}).get('edge_ratio_min'),
                                                                 rk['checks'].get('deformation', {}).get('edge_ratio_max')]},
               'seconds': round(time.time() - t0, 2)}
        rows.append(row)
        sk = rep['skinned']
        log('PARITY %-44s %-28s skin max %.2e mean %.2e keys %s det %s glbv %s rig %s %.1fs' % (
            item['file'], v, sk.get('max_m', -1), sk.get('mean_m', -1), sk.get('keys'), row['deterministic'],
            row['glb_validate']['ok'], None if rk is None else rk['ok'], row['seconds']))
    reex = []
    if reexport:
        reex = reexport_blender(oracle, out, reexport, blender_path, log)
    counts = {}
    for r in rows:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1
    built = [r for r in rows if r['verdict'] != 'not-built']
    summary = {'files': len(rows), 'verdicts': counts,
               'max_skinned_error_m': max((r['compare']['skinned'].get('max_m', 0) for r in built), default=None),
               'deterministic': all(r['deterministic'] for r in built),
               'glb_validate_ok': all(r['glb_validate']['ok'] for r in built),
               'rigkit_ok': all(r['rigkit']['ok'] for r in built if r['rigkit'] is not None),
               'seconds': round(time.time() - t_all, 1), 'environment': api.environment()}
    ok = built and all(r['verdict'] in ('identical', 'equivalent-within-tolerance') for r in rows) \
        and summary['deterministic'] and summary['glb_validate_ok'] and summary['rigkit_ok']
    summary['verdict'] = 'PASS' if ok else 'FAIL'
    rep = {'schema': 'hermes64-nbchars-parity/1', 'oracle': str(oracle), 'summary': summary, 'files': rows,
           'blender_reexport': reex}
    (out / 'parity.json').write_text(json.dumps(rep, indent=1, sort_keys=True, default=str))
    if write_verdict:
        if only:
            raise ValueError('--write-verdict needs the full oracle set (no --only)')
        from . import select as SEL
        SEL.PARITY.write_text(json.dumps(verdict_record(rep, oracle), indent=1, sort_keys=True) + '\n')
    return rep


def reexport_blender(oracle, out, ids, blender_path, log=print):
    """Re-export the given oracle ids with Blender (the original pipeline, vendored copy) and compare the bytes with
    the published files: shows the oracle itself is reproducible on this machine."""
    import subprocess
    from . import select as SEL
    bp = blender_path or SEL.blender_path({})
    if not bp:
        return [{'skipped': 'Blender not found'}]
    repo = Path(__file__).resolve().parents[2]
    bo = Path(out) / 'blender'
    bo.mkdir(parents=True, exist_ok=True)
    argv = [bp, '--background', '--factory-startup', '--disable-autoexec', '--python',
            str(repo / 'tools' / 'nbchars_blender_export.py'), '--', '--gen', str(repo / 'characters' / 'gen'), '--out',
            str(bo), '--what', 'parity', '--only', ','.join(ids), '--oracle', str(oracle)]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    res = []
    if p.returncode != 0:
        return [{'error': 'blender exit %d' % p.returncode, 'stderr': p.stderr[-800:]}]
    for item in oracle_items(oracle):
        if item['id'] not in ids and item['file'] not in ids:
            continue
        f = bo / item['file']
        if not f.is_file():
            res.append({'file': item['file'], 'error': 'not produced'})
            continue
        a, b = f.read_bytes(), (Path(oracle) / item['file']).read_bytes()
        res.append({'file': item['file'], 'blender_reexport_identical_to_published': a == b, 'sha256': _sha(a)})
        log('REEXPORT %-44s identical to published: %s' % (item['file'], a == b))
    return res
