"""Honest one-row-per-need asset report with disk/placement consistency checks."""
from collections import Counter
import hashlib

from .gen_tools import workspace
from .safety import relative

STATUSES = ('failed', 'not covered', 'generated', 'converted', 'remapped', 'existed', 'substituted')
READY = frozenset(('generated', 'converted', 'remapped', 'existed', 'substituted'))


def make(root, rows, brief=None, placements=()):
    rows = [dict(r) for r in rows]
    wants = [r['want'] for r in rows]
    if len(wants) != len(set(wants)):
        raise ValueError('duplicate wanted asset report row')
    for r in rows:
        if r.get('status') not in STATUSES:
            raise ValueError('unknown asset report status')
    rows.sort(key=lambda r: STATUSES.index(r['status']))
    counts = Counter(r['status'] for r in rows)
    return {'format': 'hermes64-asset-report/1', 'brief': brief or {}, 'rows': rows,
            'total': len(rows), 'ready': sum(counts[k] for k in READY),
            'counts': {k: counts[k] for k in STATUSES}, 'placements': list(placements),
            'note': 'Numeric checks are not appearance approval. Appearance is for the owner to judge.'}


def with_bindings(root, report, bindings, bundle_root, *, placements=()):
    from .provenance import capture_bindings
    rows = capture_bindings(root, bindings, bundle_root)
    return dict(report, bindings=[{k: r.get(k) for k in ('binding_id', 'file', 'sha256', 'source', 'licence')}
                                  for r in rows], placements=list(placements))


def verify(root, report, *, bundle_root=None):
    p = workspace(root)
    errors = []
    ready = [r for r in report['rows'] if r['status'] in READY]
    if report.get('total') != len(report['rows']):
        errors.append('report total disagrees with rows')
    counts = Counter(r['status'] for r in report['rows'])
    if report.get('counts') != {k: counts[k] for k in STATUSES} or report.get('ready') != len(ready):
        errors.append('report counts disagree with rows')
    ids = {r.get('id') for r in ready}
    for row in ready:
        file = row.get('file')
        if not file:
            errors.append('ready row has no file: ' + row['want']); continue
        path = p.path(relative(file).as_posix())
        if not path.is_file():
            errors.append('missing file: ' + file)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row.get('sha256'):
            errors.append('changed file hash: ' + file)
    bound = report.get('bindings', [])
    if bound:
        from .provenance import validate_export, load as load_provenance
        binding_check = validate_export(p.root, [r['file'] for r in bound], bundle_root=bundle_root)
        errors += binding_check['errors']
        index = {r['file']: r for r in load_provenance(p.root)['assets']}
        for r in bound:
            expected = index.get(r['file'], {})
            if expected.get('sha256') != r.get('sha256') or r['binding_id'] not in expected.get('binding_ids', []):
                errors.append('binding/report provenance mismatch: ' + r['binding_id'])
        ids.update(r['binding_id'] for r in bound)
    for id_ in report.get('placements', []):
        if id_ not in ids:
            errors.append('unlisted or failed room placement: ' + str(id_))
    return {'ok': not errors, 'errors': errors, 'files_checked': len(ready),
            'placements_checked': len(report.get('placements', []))}


def text(report):
    def names(statuses):
        return '; '.join(r['want'] + (' (' + r['reason'] + ')' if r.get('reason') else '')
                         for r in report['rows'] if r['status'] in statuses) or 'none'
    return '\n'.join([
        'Assets: %d of %d needs ready.' % (report['ready'], report['total']),
        'Not made: ' + names(('failed', 'not covered')),
        'Made new: ' + names(('generated',)),
        'Library: ' + names(('existed', 'remapped')),
        'Converted: ' + names(('converted',)) + '. Stand-ins: ' + names(('substituted',)),
        'Appearance is for the owner to judge.'
    ]) + '\n'


def write(root, report, *, bundle_root=None):
    p = workspace(root)
    result = verify(root, report, bundle_root=bundle_root)
    if not result['ok']:
        raise ValueError('asset report inconsistent: ' + '; '.join(result['errors']))
    report = dict(report, consistency=result)
    p.write_json('ASSET-REPORT.json', report)
    p.write_bytes('ASSET-REPORT.txt', text(report).encode())
    return report
