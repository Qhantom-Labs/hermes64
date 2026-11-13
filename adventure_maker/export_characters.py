"""Character admission for local exports only, never Hub publication.

Build/rights declarations are recorded evidence, not legal certification. A rig
quality waiver is not a licence. Do not copy raw machine-path build receipts.
"""
import hashlib
import json
import re
from pathlib import Path

from .safety import fail, inspect_path

HEX = re.compile(r'^[0-9a-f]{64}$')
HELP = ('Character export refused: %s. Use the character creator to build and bind a project character, '
        'or have the owner record explicit rights/licence provenance in assets/PROVENANCE.json '
        '(see docs/EXPORT.md). A rig-quality waiver alone grants no redistribution rights; '
        'private/restricted/cameo characters cannot be exported.')


def refuse(reason):
    fail('release_private', HELP % reason)


def policy(value):
    """Denials have precedence over declarations, including nested GLB extras."""
    if isinstance(value, dict):
        if (value.get('internal_only') or value.get('restricted') or value.get('private') or
                value.get('public_release') is False or
                value.get('visibility') in ('private', 'internal', 'restricted', 'public-with-notice') or
                value.get('source') == 'cameo_pack' or
                value.get('licence') in ('LicenseRef-Private', 'NOASSERTION', 'unknown') or
                'cameo' in value.get('tags', [])):
            reason = 'private/restricted or unlicensed character metadata'
            if value.get('visibility') == 'internal' and value.get('rights_declared') is not True:
                reason += ('; visibility internal: the owner must correct the community visibility only if legitimately releasable'
                           '; no owner-rights declaration on this metadata: the owner must record explicit rights/licence'
                           ' provenance in assets/PROVENANCE.json (separate from visibility)')
            refuse(reason)
        for child in value.values():
            policy(child)
    elif isinstance(value, list):
        for child in value:
            policy(child)


def catalog_policy(project, bundle, path, expected):
    """A known denial follows bytes through renames and every transformation link."""
    project_file = path.relative_to(project.root).as_posix() if project.root in path.parents else None
    registries = [project.path('catalog.json'), project.path('assets/PROVENANCE.json'),
                  inspect_path(Path(bundle) / 'catalog/catalog.json'),
                  inspect_path(Path(bundle) / 'characters/manifest.json')]
    for registry in registries:
        if not registry.is_file():
            continue
        doc = json.loads(registry.read_text(encoding='utf-8'))
        records = doc.get('assets', doc.get('characters', []))
        if isinstance(records, dict):
            records = list(records.values())
        for row in records:
            files = row.get('files', []) + [row]
            if any(f.get('sha256') == expected or
                   (registry in registries[:2] and project_file and
                    (f.get('path') == project_file or f.get('file') == project_file)) for f in files):
                policy(row)


def measured(project, file, expected, bundle=None):
    path = project.path(file)
    if not HEX.fullmatch(expected or '') or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        refuse('missing/changed character source or hash')
    if bundle is not None:
        catalog_policy(project, bundle, path, expected)
    return path


def glb_policy(path):
    """Read GLB JSON without numpy; all privacy/reference checks still apply."""
    from .export import public_data, scan_bytes
    raw = path.read_bytes()
    scan_bytes(raw, 'character')
    if raw[:4] != b'glTF' or len(raw) < 20 or raw[16:20] != b'JSON':
        refuse('character is not a GLB with JSON metadata')
    try:
        doc = json.loads(raw[20:20 + int.from_bytes(raw[12:16], 'little')].decode('utf-8'))
    except (ValueError, UnicodeError):
        refuse('invalid character GLB metadata')
    policy(doc)
    public_data(doc)


def generated(project, cast, bundle):
    cid = cast['id']
    manifest = project.read_json('characters/manifest.json') if project.path('characters/manifest.json').is_file() else {}
    entries = [r for r in manifest.get('characters', []) if r.get('id') == cid]
    if len(entries) != 1:
        refuse('missing unique project character build provenance')
    entry = entries[0]
    policy(entry)
    base = measured(project, entry['glb'], entry['sha256'], bundle)
    glb_policy(base)
    recipe = project.read_json('characters/recipes/' + cid + '.json')
    policy(recipe)
    # Creator64's writer uses ensure_ascii=True; the original recipe writer uses False.
    creator = recipe.get('schema') == 'hermes64-creator-recipe/1'
    exporter = entry.get('exporter', 'blender')
    if exporter not in (('creator',) if creator else ('python', 'blender')):
        refuse('unsupported or inconsistent character generator')
    recipe_hash = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=creator, allow_nan=False).encode('utf-8')).hexdigest()
    receipt = project.read_json('characters/built/' + cid + '/gates.json')
    item = receipt.get('items', {}).get(cid, {})
    if (recipe.get('id') != cid or receipt.get('schema') != 'hermes64-character-build/1.0.0' or
            recipe_hash != entry.get('recipe_sha256') or recipe_hash != item.get('recipe', {}).get('recipe_sha256') or
            item.get('ok') is not True or item.get('gates', {}).get('ok') is not True or
            item.get('sha256') != entry['sha256'] or item.get('exporter', 'blender') != exporter):
        refuse('character recipe/hash/generator or passing character_gate evidence is missing or changed')
    source = {'glb': entry['glb'], 'sha256': entry['sha256']}
    if cast['glb'] != source['glb'] and entry.get('locomotion', {}).get('glb') == cast['glb']:
        source = entry['locomotion']
        rep = project.read_json('characters/locomotion/' + cid + '.json')
        if (source.get('source_sha256') != entry['sha256'] or rep.get('ok') is not True or
                rep.get('sha256') != source['sha256'] or rep.get('block', {}).get('source_sha256') != entry['sha256']):
            refuse('locomotion provenance chain is missing or changed')
    if cast['glb'] != source['glb'] or cast['sha256'] != source['sha256']:
        refuse('cast does not match the generated character source')
    return {'admission': 'user-generated, not part of the public manifest', 'generator': exporter,
            'recipe_sha256': recipe_hash, 'build_sha256': entry['sha256'],
            'not_run': item['gates'].get('not_run', {})}


def owned(project, cast):
    from .provenance import load, require_export
    rows = [r for r in load(project.root)['assets'] if r.get('file') == cast['glb']]
    if len(rows) != 1:
        refuse('unknown character provenance (no owner rights declaration)')
    row = rows[0]
    policy(row)
    owner = row.get('owner_approved')
    if (row.get('rights_declared') is not True or not isinstance(owner, str) or not owner.strip() or
            row.get('source') != 'converted' or row.get('sha256') != cast['sha256'] or
            row.get('licence_required', True) is not True):
        refuse('explicit owner, source licence and rights declaration required')
    original = row.get('converted_from') or {}
    name = original.get('name')
    if (not isinstance(name, str) or not name or any(c in name for c in ('/', chr(92), ':')) or
            any(ord(c) < 32 for c in name) or not HEX.fullmatch(original.get('sha256', ''))):
        refuse('invalid original character provenance')
    try:
        require_export(project.root, [cast['glb']])
    except ValueError as exc:
        refuse(str(exc))
    return {'admission': 'user-owned, not part of the public manifest', 'rights_declared': True,
            'owner_approved': owner, 'licence': row['licence'], 'converted_from': original,
            'credit': row.get('credit', '')}


def admit(project, bundle, binding, admitted):
    """Return a portable disclosure for a non-manifest actor, None for legacy public/placeholder.

    No caller in hub.py uses this local-only exception. Paths and hashes are still
    rechecked by export.media. Cast sources, locomotion and role derivatives must
    be linked; an arbitrary cache location is never authority.
    """
    policy(binding)
    if binding.get('placeholder'):
        return None
    try:
        path = inspect_path(Path(binding['path']))
        catalog_policy(project, bundle, path, binding['sha256'])
        if binding['sha256'] in admitted:
            return None
        if project.root not in path.parents:
            refuse('non-manifest character is outside this project')
        measured(project, path.relative_to(project.root).as_posix(), binding['sha256'], bundle)
        cast_doc = project.read_json('characters/cast.json')
        cid = binding.get('cast_id') or binding.get('character_id')
        rows = [r for r in cast_doc.get('cast', []) if r.get('id') == cid]
        if len(rows) != 1:
            refuse('unknown character cast provenance')
        cast = rows[0]
        policy(cast)
        source = measured(project, cast['glb'], cast['sha256'], bundle)
        glb_policy(source)
        authorization = dict(cast)
        waiver = cast.get('waiver')
        if waiver:
            from .character_waiver import granted
            if not granted(cast, source.read_bytes()):
                refuse('cast waiver does not match the owner-approved GLB block')
            authorization.update(glb=waiver['source_glb'], sha256=waiver['source_sha256'])
            glb_policy(measured(project, authorization['glb'], authorization['sha256'], bundle))
        info = generated(project, authorization, bundle) if cast.get('source') == 'generated' else owned(project, authorization)
        if path != source:
            rel = path.relative_to(project.root).as_posix()
            if not rel.startswith('.maker/cache/cast/'):
                refuse('unrecognized character transformation')
            side = project.read_json(str(Path(rel).with_suffix('.json')))
            if (side.get('ok') is not True or side.get('source_sha256') != cast['sha256'] or
                    side.get('sha256') != binding['sha256'] or side.get('kind') not in ('player', 'enemy')):
                refuse('derived character provenance chain is missing or changed')
        glb_policy(path)
        result = dict(info, cast_id=cid, source_file=authorization['glb'], source_sha256=authorization['sha256'],
                      sha256=binding['sha256'], file='media/' + binding['sha256'] + path.suffix,
                      public_manifest=False)
        if waiver:
            result['rig_waiver'] = {k: waiver[k] for k in ('owner', 'approved_on', 'scope', 'block_sha256')}
        return result
    except (KeyError, TypeError, ValueError, OSError) as exc:
        refuse('incomplete character provenance (%s)' % type(exc).__name__)
