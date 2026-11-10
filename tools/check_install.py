"""Check an installed Hermes64 plugin folder against the PACKAGE-MANIFEST.json it was packaged with; prints PASS or FAIL.

    python3 tools/check_install.py [PLUGIN_FOLDER]     (Windows: py tools\\check_install.py [PLUGIN_FOLDER])

PLUGIN_FOLDER defaults to the plugin this script is installed in (<plugin>/tools/..) or, for the copy that sits next
to the unpacked folder in a release-candidate directory, ./hermes64. Standard library only and
read-only: it never writes, installs, launches an engine or touches the network. Checks:

1. PACKAGE-MANIFEST.json is there and lists the files; every listed file is present with the same size and sha256.
2. Nothing unexpected sits next to them (Python caches and OS litter are ignored; extra files are reported as a
   warning, not a failure, since Hermes and your own tools may add some).
3. The layout Hermes and the Studio need: plugin.yaml (name hermes64, the tool count it was packaged with),
   __init__.py, the Studio's Desktop and backend halves, the rig kit, the bundled skills, the hub registry and catalog.
4. The optional cameo pack is either complete (model hash matches cameo/cameo.json, LICENSE-CAMEO.md present) or
   absent (deleting the cameo/ folder is the one-step removal). Half a pack fails.

Exit code 0 on PASS, 1 on FAIL, 2 when the folder cannot be read at all.
"""
import hashlib
import json
from pathlib import Path
import sys

MANIFEST = 'PACKAGE-MANIFEST.json'
IGNORED_PARTS = ('__pycache__', '.DS_Store', 'Thumbs.db', 'desktop.ini')
REQUIRED = ('plugin.yaml', '__init__.py', 'adventure_maker/tools.py', 'desktop/plugin.js', 'dashboard/manifest.json',
            'dashboard/plugin_api.py', 'rigs/human16_v1/rig.json', 'rigs/quad16_v1/rig.json', 'skills/hermes64/SKILL.md',
            'hub/index.json', 'catalog/catalog.json', 'catalog/names.json', 'runtime/godot/project.godot')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check(folder):
    """{'ok': bool, 'fail': [...], 'warn': [...], 'checked': n, ...} for one installed plugin folder."""
    folder = Path(folder)
    fail, warn = [], []
    try:
        record = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
        rows = record['files']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'ok': False, 'fail': ['%s missing or unreadable in %s (%s)' % (MANIFEST, folder, type(exc).__name__)],
                'warn': [], 'checked': 0, 'unreadable': True}
    optional = tuple(record.get('optional') or ())
    listed = {r['path'] for r in rows}
    cameo_rows = [r for r in rows if r['path'].startswith(optional)] if optional else []
    cameo_present = [r for r in cameo_rows if (folder / r['path']).is_file()]
    cameo_removed = bool(cameo_rows) and not cameo_present and not (folder / 'cameo').exists()
    checked = 0
    for row in rows:
        path = folder / row['path']
        if cameo_removed and row['path'].startswith(optional):
            continue
        if not path.is_file():
            fail.append('missing: ' + row['path'])
            continue
        checked += 1
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            fail.append('changed (size or sha256 differs): ' + row['path'])
    for path in sorted(folder.rglob('*')):
        rel = path.relative_to(folder).as_posix()
        if path.is_dir() or rel == MANIFEST or any(part in IGNORED_PARTS for part in path.parts) or rel.endswith('.pyc'):
            continue
        if rel not in listed:
            warn.append('extra file (not in the package): ' + rel)
    for rel in REQUIRED:
        if rel not in listed:
            fail.append('the package itself lacks a required file: ' + rel)
    try:
        meta = json.loads((folder / 'plugin.yaml').read_text(encoding='utf-8'))
        if meta.get('name') != 'hermes64':
            fail.append('plugin.yaml name is %r, expected hermes64' % meta.get('name'))
        if len(meta.get('provides_tools', [])) != record.get('tools'):
            fail.append('plugin.yaml lists %d tools, the package was made with %s'
                        % (len(meta.get('provides_tools', [])), record.get('tools')))
    except (OSError, ValueError) as exc:
        fail.append('plugin.yaml unreadable (%s)' % type(exc).__name__)
    if cameo_rows and not cameo_removed:
        if len(cameo_present) != len(cameo_rows):
            fail.append('the optional cameo pack is incomplete: delete the whole cameo/ folder or reinstall the package')
        else:
            try:
                info = json.loads((folder / 'cameo/cameo.json').read_text(encoding='utf-8'))
                if sha256(folder / 'cameo' / info['model']) != info['expected_sha256']:
                    fail.append('cameo model sha256 differs from cameo/cameo.json')
                if not (folder / 'cameo' / info['notice']).is_file():
                    fail.append('cameo notice missing: cameo/' + info['notice'])
            except (OSError, ValueError, KeyError) as exc:
                fail.append('cameo/cameo.json unreadable (%s)' % type(exc).__name__)
    return {'ok': not fail, 'fail': fail, 'warn': warn, 'checked': checked, 'listed': len(rows),
            'cameo': 'removed' if cameo_removed else ('present' if cameo_rows else 'not in package'),
            'source': record.get('source'), 'version': record.get('version')}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        folder = Path(argv[0])
    else:
        here = Path(__file__).resolve()
        folder = next((c for c in (here.parents[1], here.parent / 'hermes64') if (c / MANIFEST).is_file()), here.parents[1])
    result = check(folder)
    for line in result['fail']:
        print('FAIL  ' + line)
    for line in result['warn'][:20]:
        print('WARN  ' + line)
    if len(result['warn']) > 20:
        print('WARN  ... and %d more extra files' % (len(result['warn']) - 20))
    source = result.get('source') or {}
    print('%s  hermes64 %s at %s: %d/%d files verified (sha256), cameo %s, source %s (%s tree)' % (
        'PASS' if result['ok'] else 'FAIL', result.get('version') or '?', folder, result['checked'],
        result.get('listed', 0), result.get('cameo', '?'), (source.get('commit') or '?')[:12], source.get('tree') or '?'))
    if result.get('unreadable'):
        return 2
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
