"""Per-project asset provenance. Declarations are recorded, not legally verified.

This is distinct from tools/provenance_audit.py, which audits the plugin's assembled
source-copy receipts (not project assets). No source-lane audit files are rewritten.
"""
import hashlib
import re
from pathlib import Path

from .gen_tools import workspace
from .safety import relative, inspect_path

FORMAT = 'hermes64-provenance/1'
MANIFEST = 'assets/PROVENANCE.json'
KNOWN_LOCAL = frozenset(('MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'CC0-1.0',
                         'CC-BY-4.0', 'CC-BY-SA-4.0', 'CC-BY-NC-4.0', 'CC-BY-NC-SA-4.0', 'LicenseRef-Private'))
HUB = KNOWN_LOCAL - {'CC-BY-NC-4.0', 'CC-BY-NC-SA-4.0', 'LicenseRef-Private'}


def load(root):
    p = workspace(root)
    if p.path(MANIFEST).exists():
        doc = p.read_json(MANIFEST)
        if not isinstance(doc, dict) or doc.get('format') != FORMAT or not isinstance(doc.get('assets'), list):
            raise ValueError('invalid project provenance manifest')
        return doc
    return {'format': FORMAT, 'note': 'Licence and rights declarations are recorded, not independently verified.', 'assets': []}


def _asset_path(project, row, bundle_root=None):
    if row.get('source_scope') == 'bundle':
        if row.get('source') != 'kit':
            raise ValueError('only trusted bundled kit files may use bundle scope')
        base = inspect_path(Path(bundle_root or Path(__file__).resolve().parents[1]).absolute())
        return inspect_path(base / relative(row['bundle_file']))
    return project.path(relative(row['file']).as_posix())


def record(root, row, *, bundle_root=None):
    p = workspace(root)
    row = dict(row)
    if row.get('source') not in ('kit', 'generated', 'converted', 'audio'):
        raise ValueError('provenance source must be kit, generated, converted or audio')
    if row['source'] == 'converted':
        original = row.get('converted_from') or {}
        if not isinstance(original, dict) or not isinstance(original.get('sha256'), str) or \
           not re.fullmatch(r'[0-9a-f]{64}', original['sha256']) or not isinstance(original.get('name'), str) or \
           not original['name'] or any(c in original['name'] for c in ('/', chr(92), ':')) or \
           any(ord(c) < 32 for c in original['name']) or row.get('rights_declared') is not True:
            raise ValueError('converted provenance requires source basename, hash, licence and boolean declared rights')
        if not original.get('licence'):
            raise ValueError('converted provenance requires source licence')
    file = relative(row.get('file')).as_posix()
    path = _asset_path(p, dict(row, file=file), bundle_root)
    if not path.is_file():
        raise ValueError('provenance file is missing: ' + file)
    measured = hashlib.sha256(path.read_bytes()).hexdigest()
    if row.get('sha256') and row['sha256'] != measured:
        raise ValueError('provenance file hash mismatch: ' + file)
    row.update(file=file, sha256=measured, licence_required=row.get('licence_required', True))
    if not isinstance(row['licence_required'], bool):
        raise ValueError('licence_required must be boolean')
    if row['source'] == 'generated' and not re.fullmatch(r'[0-9a-f]{64}', row.get('recipe_sha256', '')):
        raise ValueError('generated provenance requires recipe_sha256')
    if not isinstance(row.get('gates'), dict) or row['gates'].get('ok') is not True:
        raise ValueError('provenance requires passing gate results')
    doc = load(p.root)
    doc['assets'] = sorted([r for r in doc['assets'] if r['file'] != file] + [row], key=lambda r: r['file'])
    p.write_json(MANIFEST, doc)
    return row


def validate_export(root, files=None, *, hub=False, bundle_root=None):
    p = workspace(root)
    doc = load(p.root)
    index = {row['file']: row for row in doc['assets']}
    errors = []
    if len(index) != len(doc['assets']):
        errors.append('duplicate provenance file rows')
    files = sorted(index) if files is None else list(files)
    for file in files:
        row = index.get(file)
        if row is None:
            errors.append('missing provenance row: ' + file); continue
        try:
            path = _asset_path(p, row, bundle_root)
        except (ValueError, KeyError):
            errors.append('invalid provenance file path'); continue
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get('sha256'):
            errors.append('missing/changed asset: ' + file)
        licence = row.get('licence')
        licences = [licence]
        if row.get('source') == 'converted':
            original = row.get('converted_from') or {}
            licences.append(original.get('licence') if isinstance(original, dict) else None)
            if row.get('rights_declared') is not True:
                errors.append('converted source rights not declared: ' + file)
        if row.get('licence_required', True) and any(not isinstance(l, str) or l not in KNOWN_LOCAL for l in licences):
            errors.append('required licence missing or unknown: ' + file)
        if hub and any(not isinstance(l, str) or l not in HUB for l in licences):
            errors.append('licence is not admitted for hub redistribution: ' + file)
        if any(isinstance(l, str) and l.startswith('CC-BY') for l in licences) and not row.get('credit'):
            errors.append('attribution licence needs a credit: ' + file)
        if not isinstance(row.get('gates'), dict) or row['gates'].get('ok') is not True:
            errors.append('asset gates not passed: ' + file)
    return {'ok': not errors, 'errors': errors, 'files': files, 'hub': hub}


def require_export(root, files=None, *, hub=False, bundle_root=None):
    result = validate_export(root, files, hub=hub, bundle_root=bundle_root)
    if not result['ok']:
        raise ValueError('export refused: ' + '; '.join(result['errors']))
    return result


def credits(root, files=None):
    doc = load(root)
    selected = None if files is None else frozenset(files)
    lines = []
    for row in doc['assets']:
        if selected is not None and row['file'] not in selected:
            continue
        original = row.get('converted_from') or {}
        licences = [row.get('licence')]
        if row.get('source') == 'converted' and isinstance(original, dict):
            licences.append(original.get('licence'))
        attribution = [l for l in licences if isinstance(l, str) and l.startswith('CC-BY')]
        if attribution:
            lines.append('%s — %s — %s%s' % (row.get('id', row['file']), row.get('credit', ''),
                         ' + '.join(dict.fromkeys(attribution)), ' — ' + row['source_url'] if row.get('source_url') else ''))
    return '\n'.join(lines) + ('\n' if lines else '')


def capture_bindings(root, bindings, bundle_root, *, pack=''):
    """Record every bound environment GLB, not just the new recipes. No cast/audio edits.

    Bundle rows use a virtual bundle/ prefix and an explicitly trusted bundle root;
    they never copy private absolute machine paths into provenance. Native binding
    seeds absent from the source binding are recorded as unknown, not invented.
    """
    from .glb_validate import validate
    p = workspace(root)
    bundle_root = inspect_path(Path(bundle_root).absolute())
    known = {r['file']: r for r in load(root)['assets']}
    out = []
    for ref, binding in sorted(bindings.items()):
        path = inspect_path(Path(binding['path']).absolute())
        if p.root in path.parents:
            file = path.relative_to(p.root).as_posix()
            if file not in known and not file.startswith('.maker/cache/assets/'):
                raise ValueError('missing required project asset provenance: ' + ref)
            row = dict(known.get(file) or {'id': 'binding:' + ref, 'file': file, 'source': 'kit',
                                          'licence': 'MIT', 'seed': binding.get('seed')})
        elif bundle_root in path.parents:
            rel = path.relative_to(bundle_root).as_posix()
            file = 'bundle/' + rel
            row = dict(known.get(file) or {'id': 'binding:' + ref, 'file': file, 'bundle_file': rel, 'source_scope': 'bundle',
                   'source': 'kit', 'kit_id': binding.get('kit_id'), 'licence': 'MIT', 'seed': binding.get('seed'),
                   'seed_note': 'source binding has no seed' if 'seed' not in binding else ''})
            row.update(bundle_file=rel, source_scope='bundle', source='kit')
        else:
            raise ValueError('bound environment asset is outside the project/bundle')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding.get('sha256'):
            raise ValueError('binding hash mismatch: ' + ref)
        gate = validate(raw, 'bound.glb', 1500)
        if not gate.ok:
            raise ValueError('bound environment GLB structure failed: ' + ref)
        row.update(sha256=binding['sha256'], pack=pack or row.get('pack', ''), licence_required=True,
                   binding_ids=sorted(set(row.get('binding_ids', []) + [ref])))
        if 'gates' not in row:
            row['gates'] = {'ok': True, 'structure': {'ok': gate.ok, 'issues': gate.issues},
                            'scope': 'bound GLB hash/structure; original class/file gates belong to source build'}
        row = record(p.root, row, bundle_root=bundle_root)
        known[file] = row
        out.append(dict(row, binding_id=ref))
    return out


def prepare_export(root, files, destination, *, hub=False, bundle_root=None):
    """Explicit export guard for the integrator; validate before writing credits/manifest."""
    p = workspace(root)
    result = require_export(p.root, files, hub=hub, bundle_root=bundle_root)
    target = p.path(destination)
    target.mkdir(parents=True, exist_ok=True)
    selected = frozenset(result['files'])
    rows = []
    for row in load(root)['assets']:
        if row['file'] in selected:
            target_file = files[row['file']] if isinstance(files, dict) else row['file']
            target_file = relative(target_file).as_posix()
            exported = dict(row, file=target_file, source_file=row['file'])
            if 'bundle_file' in exported:
                exported['source_bundle_file'] = exported.pop('bundle_file')
                exported.pop('source_scope', None)
            rows.append(exported)
    p.write_json(destination + '/PROVENANCE.json', dict(load(root), assets=rows))
    p.write_bytes(destination + '/CREDITS.txt', credits(root, files).encode())
    return result
