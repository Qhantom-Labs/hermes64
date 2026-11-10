"""python3 -m adventure_maker.rigkit {list | info ID | validate FILE.glb... | attach IN OUT | derive --oracle DIR}"""
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m adventure_maker.rigkit')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    p = sub.add_parser('info'); p.add_argument('rig')
    p = sub.add_parser('validate')
    p.add_argument('files', nargs='+')
    p.add_argument('--rig', default='auto')
    p.add_argument('--clips', default='')
    p.add_argument('--expect-sha256', default=None)
    p.add_argument('--profile', default='grounded', choices=['grounded', 'hover'])
    p.add_argument('--keys', default='all')
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('attach')
    p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--rig', default='human16_v1')
    p.add_argument('--clips', default='')
    p.add_argument('--mode', default='copy', choices=['copy'])
    p = sub.add_parser('derive'); p.add_argument('--oracle', required=True); p.add_argument('--out', default=None)
    p = sub.add_parser('build-kits'); p.add_argument('--out', default=None)
    p = sub.add_parser('report', help='validate every file of a published set (manifest.json)')
    p.add_argument('--oracle', required=True); p.add_argument('--out', required=True); p.add_argument('--md', default=None)
    p.add_argument('--keys', default='all')
    a = ap.parse_args(argv)
    from . import list_rigs, load_rig, validate_character, attach_clips
    if a.cmd == 'list':
        print('\n'.join(list_rigs()))
        return 0
    if a.cmd == 'info':
        r = load_rig(a.rig)
        print(json.dumps({'id': r.id, 'version': r.version, 'kind': r.kind, 'bones': r.bones,
                          'clips': r.clips.get('required'), 'combat': r.clips.get('combat', []), 'budgets': r.budgets},
                         indent=1))
        return 0
    if a.cmd == 'validate':
        bad = 0
        out = []
        for f in a.files:
            rig = a.rig
            if rig == 'auto':
                from .clips import detect_rig
                rig = detect_rig(Path(f).read_bytes())
            rep = validate_character(f, rig, clips=[c for c in a.clips.split(',') if c] or None,
                                     expect_sha256=a.expect_sha256, profile=a.profile,
                                     keys='all' if a.keys == 'all' else int(a.keys))
            rep['file'] = f
            out.append(rep)
            bad += not rep['ok']
            if not a.json:
                c = rep['checks']
                print('%s %s %s conn %s edge %s..%s%s' % ('PASS' if rep['ok'] else 'FAIL', rep['rig'], f,
                      c.get('connectivity', {}).get('max_gap_m'), c.get('deformation', {}).get('edge_ratio_min'),
                      c.get('deformation', {}).get('edge_ratio_max'),
                      '' if rep['ok'] else ' errors: ' + '; '.join('%s %s' % (e['code'], e['message']) for e in rep['errors'][:4])))
        if a.json:
            print(json.dumps(out, indent=1, sort_keys=True))
        return 1 if bad else 0
    if a.cmd == 'attach':
        raw = attach_clips(Path(a.src).read_bytes(), a.rig, clips=[c for c in a.clips.split(',') if c] or None, mode=a.mode)
        Path(a.dst).write_bytes(raw)
        print(json.dumps({'written': a.dst, 'bytes': len(raw)}))
        return 0
    if a.cmd == 'derive':
        from .derive import derive
        print(json.dumps(derive(a.oracle, a.out)))
        return 0
    if a.cmd == 'report':
        from .report import report, markdown
        doc = report(a.oracle, keys='all' if a.keys == 'all' else int(a.keys))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
        if a.md:
            Path(a.md).write_text(markdown(doc))
        print(json.dumps(doc['summary']))
        return 0 if doc['summary']['pass'] == doc['summary']['files'] else 1
    if a.cmd == 'build-kits':
        from .kits import build_kits
        print(json.dumps(build_kits(a.out), indent=1))
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
