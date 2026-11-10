"""Closed project-bound adapter for the opt-in Python reference-pack CLI."""
import hashlib
from pathlib import Path
from .adapters import Components
from .runner import locate
from .safety import fail, strict_json


def draft_pack(service, project, args):
    # Service owns the cooperative project lock; all caller paths stay inside it.
    target = 'packs/' + args['pack_id']
    if project.path(target).exists():
        fail('exists', 'Reference pack destination exists; choose a fresh pack_id')
    refs = [project.path(path) for path in args['reference_paths']]
    if any(not path.is_file() for path in refs):
        fail('arguments', 'Every reference must be an existing project-local image')
    project.read_json(args['notes_path'])  # bounded strict JSON, not executable notes
    notes = project.path(args['notes_path'])
    components = Components(service.settings, project)
    components.shipped('refpack/__main__.py')
    python = locate('python', service.settings.get('python_path', ''))
    argv = [python, '-B', '-m', 'refpack', '--refs'] + [str(p) for p in refs] + [
        '--notes', str(notes), '--pack-id', args['pack_id'], '--project', str(project.root),
        '--read-root', str(project.root), '--python-path', python, '--timeout', '120',
        '--mode', args.get('mode', 'albedo')]
    if not args.get('render_proof', True):
        argv.append('--no-proof')
    if not args.get('ref_thumbnails', False):
        argv.append('--no-ref-thumbs')
    if service.settings.get('godot_path'):
        argv += ['--godot-path', locate('godot', service.settings['godot_path'])]
    folder = service.folder(project, 'reference-pack')
    process = components.runner.run(argv, components.root, timeout=180)
    project.write_json(folder + '/process.json', dict(process, argv=argv))
    report = strict_json(process['stdout'])
    if not isinstance(report, dict) or type(report.get('ok')) is not bool:
        fail('component_protocol', 'Reference pack child must return a structured verdict')
    project.write_json(folder + '/report.json', report)
    if process['returncode'] != 0 or not report['ok']:
        return {'ok': False, 'status': 'reference_draft_failed', 'report_path': folder + '/report.json',
                'errors': report.get('errors', []), 'approval': None}
    # Read back exact targets, never trust a child-reported path or success flag.
    pack = project.read_json(target + '/pack.json')
    provenance = project.read_json(target + '/PROVENANCE.json')
    validation = project.read_json(target + '/validation.json')
    if pack.get('refpack', {}).get('status') != 'draft_unapproved' or provenance.get('status') != 'draft_unapproved' or validation.get('ok') is not True:
        fail('component_protocol', 'Reference draft status/validation readback failed')
    for filename in ('pack.json', 'audio.json'):
        actual = hashlib.sha256(project.path(target + '/' + filename).read_bytes()).hexdigest()
        if actual != report.get('hashes', {}).get(filename) or actual != provenance.get('outputs', {}).get(filename):
            fail('component_protocol', 'Reference draft hash readback failed: ' + filename)
    return {'ok': True, 'status': 'draft_unapproved', 'approval': None, 'runtime_ready': False,
            'pack_path': target + '/pack.json', 'report_path': folder + '/report.json',
            'validation_path': target + '/validation.json',
            'note': 'Draft only; no selected pack, game pointer or human approval changed.'}
