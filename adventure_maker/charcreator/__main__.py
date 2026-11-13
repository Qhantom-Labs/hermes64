"""Creator build child (numpy + Pillow): python -B -m adventure_maker.charcreator build --job JOB.json --out DIR

The plugin runs this through adventure_maker.runner.Runner (sandboxed, sanitised environment, project-confined
writes), like the python character exporter. For every job item it writes DIR/<id>.glb, and when the item asks for
renders: DIR/renders/<id>_<view>.png (transparent; the silhouette gate's inputs) and DIR/<id>_sheet.png (contact
sheet). DIR/build-report.json carries triangles, height, colours, the card fit and the guard's softened keys.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def _guarded(raw):
    from ..rigkit import gltf
    doc, _ = gltf.parse(raw)
    out = {}
    for a in doc.get('animations', []):
        g = (a.get('extras') or {}).get('rigkit_guard')
        if g:
            out[a['name']] = len(g) if isinstance(g, list) else g
    return out


def build_job(job, out_dir):
    from . import data
    from . import build as B
    from . import measure as MS
    from . import render as R
    d = data()
    card = json.loads((Path(__file__).resolve().parents[2] / d['card']['source']).read_text(encoding='utf-8'))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for it in job['items']:
        t0 = time.time()
        params = it['params']
        raw, meta, _img = B.glb(params, d)
        (out / it['out']).write_bytes(raw)
        row = {'id': it['id'], 'file': it['out'], 'sha256': meta['sha256'], 'bytes': meta['bytes'], 'height_m': meta['height_m'],
               'tris_body': meta['tris_body'], 'tris_props': meta['tris_props'], 'unique_colours': meta['paint']['unique_colours'],
               'base_colours': meta['paint']['base_colours'], 'guard_softened': _guarded(raw), 'exporter': 'creator'}
        if it.get('measure', True):
            mm = MS.model(raw)
            row['card_fit'] = MS.card_fit(mm, card)
            row['clips'] = [c['name'] for c in mm['rig']['clips']]
        if it.get('render'):
            views = R.render(raw)
            rd = out / 'renders'
            rd.mkdir(exist_ok=True)
            row['renders'] = []
            for v in R.VIEWS:
                p = rd / ('%s_%s.png' % (it['id'], v))
                p.write_bytes(R.png(views[v]))
                if v in R.GATE_VIEWS:
                    row['renders'].append(str(p))
            note = '%s %s, %d tris, %.2f m' % (params['species'], params['build'], meta['tris_body'], meta['height_m'])
            (out / ('%s_sheet.png' % it['id'])).write_bytes(R.sheet(views, label=it['id'], notes=note))
            row['sheet'] = '%s_sheet.png' % it['id']
        row['seconds'] = round(time.time() - t0, 2)
        rows.append(row)
    rep = {'schema': 'hermes64-creator-build-report/1', 'items': rows}
    (out / 'build-report.json').write_text(json.dumps(rep, indent=1, sort_keys=True), encoding='utf-8')
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m adventure_maker.charcreator')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--job', required=True)
    b.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    job = json.loads(Path(a.job).read_text(encoding='utf-8'))
    if job.get('schema') != 'hermes64-creator-job/1':
        print('unknown job schema %r' % job.get('schema'), file=sys.stderr)
        return 2
    rep = build_job(job, a.out)
    print('BUILD COMPLETE %d' % len(rep['items']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
