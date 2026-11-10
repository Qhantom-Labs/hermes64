"""Physical Godot probes layered on, never substituted for, STORY proofs."""
import hashlib
import copy
import html
import json
from pathlib import Path
from .adapters import Components
from .runner import locate
from .safety import Fault

SCOPE = ('Bounded deterministic physical probes at 60 Hz plus seeded explorer inputs. '
         'This cannot judge fun. No universal geometric proof, perceptual approval, GPU FPS from dummy rendering, '
         'or cross-machine determinism is claimed. Location-scoped interactions without anchors are disclosed. '
         'Production action menus remain contract-level; proximity is a harness constraint, not a new story rule.')


def verdict(native, proof, process):
    reasons = []
    logs = process.get('stderr', '') + process.get('stdout', '')
    fatal = process.get('returncode', 0) != 0 or any(x in logs for x in ['SCRIPT ERROR', 'ERROR:', 'BOOT ERROR', 'signal 11', 'CRASH'])
    if fatal: reasons.append('Engine exit, crash or script/runtime error; inspect retained process receipt.')
    if proof.get('status') == 'rejected': reasons.append('Story checker rejected: logical softlock/unreachable/contract defect; see proof.')
    if fatal or proof.get('status') in ('rejected', 'invalid'): return 'BROKEN', reasons
    rough = False
    conditional_bot = proof.get('status') == 'conditional' and native.get('module_physical') is True and native.get('modules_tested')
    if conditional_bot:
        reasons.append('Progression remains conditional on named skill assumptions; this bot run is not human winnability or balance proof.')
    elif proof.get('status') != 'proved': reasons.append('Story proof is inconclusive or absent.'); rough = True
    if not native.get('completed'): reasons.append('No complete physical winning path demonstrated.'); rough = True
    for key in ['failures', 'stuck', 'unreachable', 'camera_bugs', 'missing_assets', 'transition_errors']:
        if native.get(key): reasons.append(key + ': ' + str(len(native[key]))); rough = True
    if any(r.get('triangles', 0) > 6000 for r in native.get('rooms', {}).values()):
        reasons.append('Measured room geometry exceeds 6,000 triangles.'); rough = True
    if any((r.get('draw_calls') or 0) > 256 for r in native.get('rooms', {}).values()):
        reasons.append('Measured room draw calls exceed the 256-call probe budget.'); rough = True
    timing = native.get('timing', {})
    # Per-frame CPU work from timestamp probes; legacy reports only carry the
    # TIME_PROCESS monitor value (a 1 s maximum including present waits).
    frame_p95 = timing.get('frame_work_p95_ms', timing.get('engine_frame_p95_ms'))
    if native.get('render_verified') and frame_p95 is None:
        reasons.append('Rendered run produced no steady frame-time sample.'); rough = True
    elif native.get('render_verified') and frame_p95 > 33.34:
        reasons.append('Steady frame work p95 exceeds the 33.34ms budget under this harness.'); rough = True
    if 'leaked' in logs.lower() or 'still in use at exit' in logs.lower():
        reasons.append('Engine reported memory/ObjectDB/RID resources at exit.'); rough = True
    if rough: return 'ROUGH', reasons
    if native.get('droughts'): reasons.append('Observed event droughts; not a boredom/fun score.')
    if native.get('explorer_stalls'): reasons.append('Explorer revisited/stalled in cells; see observations, not a geometric softlock proof.')
    if native.get('unlocated_interactions'): reasons.append('Some legal actions are location-scoped without a physical anchor.')
    if native.get('display') == 'headless' or not native.get('render_verified'):
        reasons.append('Physical path passed; rendered performance/complete interaction coverage not certified.')
        return 'PLAYABLE', reasons
    if reasons: return 'PLAYABLE', reasons
    return 'SOLID', ['All requested bounded physical and rendered gates passed; this is not a fun verdict.']


def heatmap(rid, row):
    w, h = row.get('size', [4, 4]); scale = min(30, 300 / max(w, h))
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="340" height="340" viewBox="0 0 340 340">',
             '<rect width="340" height="340" fill="#142030"/>',
             '<text x="10" y="18" fill="white">' + html.escape(rid) + '</text>']
    heat = row.get('heat', {}); peak = max(heat.values(), default=1)
    for cell, count in sorted(heat.items()):
        x, z = map(int, cell.split(',')); light = int(40 + 180 * count / peak)
        parts.append('<rect x="{}" y="{}" width="{}" height="{}" fill="rgb({},140,80)"/>'.format(10+x*scale/2, 30+z*scale/2, scale/2, scale/2, light))
    parts.append('<text x="10" y="330" fill="white">0.5m cells; visit density, not walkability</text></svg>')
    return ''.join(parts)


def write_reports(folder, report):
    folder.mkdir(parents=True, exist_ok=True)
    panels = []
    for index, (rid, row) in enumerate(sorted(report.get('rooms', {}).items())):
        name = 'heat-%03d.svg' % index
        (folder / name).write_text(heatmap(rid, row))
        panels.append('<figure><img src="' + name + '"><figcaption>' + html.escape(rid) + '</figcaption></figure>')
    # Always supply an honest map contact sheet; real rendered PNGs are separate when requested.
    tiles = []
    for i, (rid, row) in enumerate(sorted(report.get('rooms', {}).items())):
        svg = heatmap(rid, row).replace('width="340" height="340"', 'x="%d" y="%d" width="340" height="340"' % ((i%2)*340, (i//2)*340), 1)
        tiles.append(svg)
    (folder / 'contact-sheet.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="680" height="%d">%s</svg>' % (max(1,(len(tiles)+1)//2)*340,''.join(tiles)))
    captures=sorted(p for p in folder.glob('*.png') if p.name!='contact-sheet.png')
    if captures:
        import importlib.util
        spec=importlib.util.spec_from_file_location('hermes64_ship_png',Path(__file__).resolve().parents[1]/'tools/pngtool.py')
        if spec is None or spec.loader is None: raise RuntimeError('Bundled PNG contact sheet helper missing')
        pngtool=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pngtool)
        pngtool.main(['pngtool','sheet',str(folder/'contact-sheet.png'),'2','1']+[str(p) for p in captures])
    text = '# Physical playtest: ' + report['verdict'] + '\n\n' + report.get('scope', SCOPE) + '\n\n'
    text += '\n'.join('- ' + r for r in report['reasons']) + '\n\n'
    text += 'Heatmaps/contact-sheet.svg are measured position maps, not rendered screenshots.\n'
    if captures: text += 'contact-sheet.png contains actual captured runtime frames: '+', '.join(p.name for p in captures)+'.\n'
    text += '\nTiming: '+json.dumps(report.get('timing',{}),sort_keys=True)+'\n'
    text += '\nFirst event (simulation seconds): '+str(report.get('first_event_seconds'))+'\n'
    text += '\nBudgets: 6,000 triangles, 256 draw calls/room; rendered fixed-step p95 33.34ms. Dummy-render draw/FPS values are unmeasured.\n'
    text += '\nMemory / exit diagnostics: '+json.dumps(report.get('memory',{}),sort_keys=True)+' '+json.dumps(report.get('exit_leaks',{}),sort_keys=True)+'\n'
    text += '\n| Room | Triangles | Draw calls | Samples |\n|---|---:|---:|---:|\n'
    for rid, row in sorted(report.get('rooms', {}).items()):
        text += '| {} | {} | {} | {} |\n'.format(rid, row.get('triangles'), row.get('draw_calls', 'unmeasured'), row.get('samples',0))
    (folder / 'report.md').write_text(text)
    (folder / 'report.json').write_text(json.dumps(report, sort_keys=True, indent=2))
    images = ''.join('<img width="320" src="'+html.escape(p.name)+'" alt="actual runtime frame">' for p in sorted(folder.glob('*.png')))
    (folder / 'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Hermes64 playtest</title><style>body{font:16px system-ui;max-width:1100px;margin:2em auto;background:#101720;color:#eee}figure{display:inline-block;margin:4px}pre{white-space:pre-wrap}img{max-width:100%}</style><pre>'+html.escape(text)+'</pre>'+''.join(panels)+images+'<details><summary>Full measured report</summary><pre>'+html.escape(json.dumps(report,indent=2))+'</pre></details>')


def run(service, project, args, control=''):
    current = service.current(project)
    folder = service.folder(project, 'playtest')
    c = Components(service.settings, project)
    if project.read_json(current['game']).get('contract_version') == '1.2.0':
        if '.' in (__package__ or ''):
            from ..story.checker import check_game
        else:
            from story.checker import check_game
        from .module_playtest import physical
        proof = check_game(project.read_json(current['game']))
        project.write_json(folder + '/proof.json', proof)
        report = physical(project, service.settings, current['game'], proof, folder, args.get('render', False))
        return {'ok': report['verdict'] in ('PLAYABLE', 'SOLID'), 'status': report['verdict'],
                'verdict': report['verdict'], 'reasons': report['reasons'],
                'report_path': folder + '/report.json', 'html_path': folder + '/report.html',
                'markdown_path': folder + '/report.md', 'receipt': report['receipt'],
                'replay_files':[folder + '/' + name for name in report.get('replay_files', [])]}
    proof = c.check(current['game'], folder + '/proof.json')
    runtime = c.prepare_runtime(current['game'], folder)
    traces = [{'ending': name, 'actions': [s['action'] for s in row.get('witness', [])]}
              for name, row in sorted(proof.get('endings', {}).items()) if row.get('reachable')]
    mode = args.get('mode', 'both')
    config = {'mode': mode, 'seconds': args.get('seconds', 30), 'seed': args.get('seed', 7),
              'drought_seconds': args.get('drought_seconds', 20), 'control': control,
              'output': str(project.path(folder)), 'traces': traces if mode != 'monkey' else []}
    project.write_json(folder + '/runtime/playtest-config.json', config)
    exe = locate('godot', service.settings.get('godot_path', ''))
    argv = [exe] + ([] if args.get('render', False) else ['--headless'])
    argv += ['--fixed-fps', '60', '--disable-vsync', '--path', str(runtime), '--script', 'res://playtest/runner.gd']
    try:
        process = c.runner.run(argv, project.root, timeout=180)
    except Fault as exc:
        process = {'returncode': 124, 'stderr': exc.code + ': ' + str(exc), 'stdout': ''}
    project.write_json(folder + '/process.json', dict(process, argv=argv))
    output = project.path(folder)
    native_path = output / 'native.json'
    native = json.loads(native_path.read_text()) if native_path.is_file() else {}
    if process.get('elapsed_seconds'):
        native.setdefault('timing',{})['whole_probe_ticks_per_wall_second']=native.get('ticks',0)/process['elapsed_seconds']
    # Hash only deterministic observations, never wall timings/allocator values.
    stable = copy.deepcopy({k: native.get(k) for k in ['actions', 'paths', 'stuck', 'unreachable', 'events', 'ticks', 'rooms']})
    for row in (stable.get('rooms') or {}).values(): row.pop('draw_calls', None)
    trace_hash = hashlib.sha256((output / 'inputs.jsonl').read_bytes()).hexdigest() if (output / 'inputs.jsonl').is_file() else None
    rating, reasons = verdict(native, proof, process)
    report = dict(native, verdict=rating, reasons=reasons, scope=SCOPE, proof_status=proof.get('status'),
                  game_hash=project.read_json(current['game'])['game_hash'], input_trace_sha256=trace_hash,
                  deterministic_sha256=hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest(),
                  exit_leaks={'warnings':[line for line in (process['stderr']+process['stdout']).splitlines() if 'leak' in line.lower() or 'still in use at exit' in line.lower()],
                              'scope':'exit diagnostics, not a proof that every resource is reclaimed'},
                  process_seconds=process.get('elapsed_seconds'), process_returncode=process['returncode'],
                  softlocks={'status':proof.get('status'), 'source':'existing exhaustive/symbolic checker; physical failures are separate bounded observations'})
    report.pop('states', None)
    write_reports(output, report)
    return {'ok': rating in ('SOLID','PLAYABLE'), 'status': rating, 'verdict':rating, 'reasons':reasons,
            'report_path':folder+'/report.json', 'html_path':folder+'/report.html', 'markdown_path':folder+'/report.md',
            'replay_files':[folder + '/' + name for name in native.get('replay_files', [])],
            'contact_sheet':folder+('/contact-sheet.png' if (output/'contact-sheet.png').is_file() else '/contact-sheet.svg'), 'input_trace_sha256':trace_hash}
