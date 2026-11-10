"""Validate a published character set (manifest.json with characters / enemies / props) against the rig kit and
write one report per file: python3 -m adventure_maker.rigkit report --oracle DIR --out FILE.json [--md FILE.md]"""
import json
import time
from pathlib import Path

from .clips import detect_rig
from .validate import validate_character, validate_prop


def _row(kind, rec, rep, seconds):
    c = rep['checks']
    return {'file': rec['file'], 'kind': kind, 'id': rec['id'], 'pack': rec.get('pack'), 'rig': rep['rig'], 'ok': rep['ok'],
            'errors': rep['errors'], 'warnings': rep['warnings'], 'sha256': rep['file_sha256'],
            'expected_sha256': rec.get('sha256'),
            'connectivity': c.get('connectivity'), 'deformation': c.get('deformation'), 'silhouette': c.get('silhouette'),
            'skin': c.get('skin'), 'clips': c.get('clips'), 'budget': c.get('budget'), 'rig_check': c.get('rig'),
            'prop': c.get('prop'), 'seconds': round(seconds, 1)}


def report(oracle, keys='all', log=print):
    oracle = Path(oracle)
    man = json.loads((oracle / 'manifest.json').read_text())
    rows = []
    for kind, recs in (('character', man.get('characters', [])), ('enemy', man.get('enemies', []))):
        for rec in recs:
            raw = (oracle / rec['file']).read_bytes()
            t0 = time.time()
            rep = validate_character(raw, detect_rig(raw), expect_sha256=rec.get('sha256'), keys=keys)
            rows.append(_row(kind, rec, rep, time.time() - t0))
            log('%s %-8s %-44s %s' % ('PASS' if rep['ok'] else 'FAIL', kind, rec['file'], rep['rig']))
    for rec in man.get('props', []):
        raw = (oracle / rec['file']).read_bytes()
        t0 = time.time()
        slot = 'hand_r' if rec.get('kind') == 'weapon' else None
        rep = validate_prop(raw, 'human16_v1', slot=slot, expect_sha256=rec.get('sha256'))
        rows.append(_row(rec.get('kind', 'prop'), rec, rep, time.time() - t0))
        log('%s %-8s %-44s %s' % ('PASS' if rep['ok'] else 'FAIL', rec.get('kind', 'prop'), rec['file'], rep['rig']))
    return {'schema': 'hermes64-rig-validate-set/1.0.0', 'oracle': str(oracle), 'keys': keys,
            'summary': {'files': len(rows), 'pass': sum(r['ok'] for r in rows),
                        'by_kind': {k: [sum(1 for r in rows if r['kind'] == k and r['ok']), sum(1 for r in rows if r['kind'] == k)]
                                    for k in sorted({r['kind'] for r in rows})}},
            'files': rows}


def markdown(doc):
    out = ['| file | kind | rig | result | connectivity max gap (m) | edge ratio | floor dev (m) | clips | tris |',
           '|---|---|---|---|---|---|---|---|---|']
    for r in doc['files']:
        cn = r.get('connectivity') or {}
        de = r.get('deformation') or {}
        si = r.get('silhouette') or {}
        cl = r.get('clips') or {}
        bu = r.get('budget') or {}
        tris = bu.get('body_tris', '') if r['kind'] in ('character', 'enemy') else ', '.join('%s' % v for v in (bu.get('prop_tris') or {}).values())
        out.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['file'], r['kind'], r['rig'], 'PASS' if r['ok'] else 'FAIL: ' + '; '.join(e['code'] for e in r['errors'][:3]),
            cn.get('max_gap_m', '-'), ('%s..%s' % (de.get('edge_ratio_min'), de.get('edge_ratio_max'))) if de else '-',
            si.get('floor_dev_max_m', '-'), len(cl.get('checked', [])) if cl else '-', tris))
    return '\n'.join(out) + '\n'
