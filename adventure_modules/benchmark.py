"""Data-only extension of the existing sequential edit benchmark contract."""
import time
from .service import POINTER, SpecError


def run(service, project, args):
    operations = args['operations']
    if any('expected_changed_rooms' not in op for op in operations):
        raise SpecError('every benchmark edit needs expected_changed_rooms; no self-grading locality')
    current = service.current(project)
    original = project.path(POINTER).read_bytes()
    save = args.get('save_path')
    rows = []
    stopped = False
    folder = service.folder(project, 'modules-benchmark')
    for i, op in enumerate(operations):
        if stopped:
            rows.append({'index': i + 1, 'status': 'not_run', 'data_passed': False, 'seconds': 0,
                         'reason': 'previous candidate failed; benchmark did not continue on the wrong baseline'})
            continue
        start = time.monotonic()
        try:
            result, revision = service.edit_candidate(project, current, op, save)
            passed = result['ok'] and result['regression']['expected_room_locality'] == 'passed'
            passed = passed and result['save_migration']['status'] in ('as_is', 'migrated')
            row = {'index': i + 1, 'operation': op, 'status': 'passed_data_only' if passed else 'failed',
                   'data_passed': passed, 'fully_verified': False, 'revision': revision,
                   'game_hash': result['game']['game_hash'], 'regression': result['regression'],
                   'save_migration': result['save_migration']['status'], 'runtime': 'not_run',
                   'physically_tested_by_bot': 'not_run', 'human_tested': 'not_run'}
            if passed:
                current, save = revision, revision.get('save')
            else:
                stopped = True
        except (SpecError, OSError, ValueError, TypeError) as exc:
            row = {'index': i + 1, 'status': 'failed', 'data_passed': False, 'reason': str(exc)}
            stopped = True
        row['seconds'] = round(time.monotonic() - start, 6)
        rows.append(row)
        project.write_json(folder + '/rows.json', rows)
    passed = sum(row['data_passed'] for row in rows)
    unchanged = project.path(POINTER).read_bytes() == original
    report = {'status': 'passed_data_only' if passed == len(rows) and unchanged else 'failed',
              'count': len(rows), 'data_verified_passed': passed, 'fully_verified_passed': 0,
              'live_revision_unchanged': unchanged, 'results': rows,
              'scope': 'Explicit module edits only. No Godot, physical bot, human, style or audio evidence.'}
    project.write_json(folder + '/benchmark.json', report)
    if project.read_json(folder + '/benchmark.json') != report:
        raise SpecError('benchmark report readback failed')
    return {'ok': passed == len(rows) and unchanged, 'status': report['status'],
            'benchmark': report, 'report_path': folder + '/benchmark.json'}
