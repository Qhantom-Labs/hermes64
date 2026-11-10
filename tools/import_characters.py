"""Verified local cast import. Python 3.9 stdlib only; never runs source-lane code.

python3 -B tools/import_characters.py
python3 -B tools/import_characters.py --source ../lane-combat-art/published
python3 -B tools/import_characters.py --public-package evidence/characters/public-source
python3 -B tools/import_characters.py --capture evidence/characters/round-01

A combat export (manifest with `enemies`/`props`, plus SHA256SUMS) also imports its enemy
and weapon/projectile GLBs into characters/combat/ with a hash-guarded manifest. Over an
existing import, a character file may only change when the source manifest declares the
change (`changed_hashes_vs_published_r21`) and the new GLB keeps every byte and JSON object
of the old one (appended animations only); anything else is rejected before any write.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r'^[a-z][a-z0-9_]*$')
SHA = re.compile(r'^[0-9a-f]{64}$')
RESTRICTED_IDS = ('cameo_visor_01',)
ROLES = {
    'returning_daughter': ('forest_village', 'fv_scribe'),
    'clue_giver': ('forest_village', 'fv_warden'),
    'antagonist': ('forest_village', 'fv_elder'),
    'arrival': ('polar_pod', 'new_arrival'), 'host': ('polar_pod', 'tavi'),
    'helper': ('polar_pod', 'neri'), 'saboteur': ('polar_pod', 'neri'),
    'gardener': ('polar_pod', 'sol'), 'pathkeeper': ('polar_pod', 'ivo'),
    'dome_keeper': ('polar_pod', 'luma'),
}
COATS = {
    'silver_tabby': 'cat_tabby', 'black_tuxedo': 'cat_tuxedo',
    'blue_solid': 'cat_black', 'cream_point': 'cat_white',
    'black_solid': 'cat_black', 'ginger_tabby': 'cat_tabby',
    'calico': 'cat_calico', 'white_solid': 'cat_white',
    'tortoiseshell': 'cat_calico', 'brown_mackerel': 'cat_tabby',
    'smoky_longhair': 'cat_black', 'spotted_cream': 'cat_calico',
}


COMBAT_CLIPS = ('idle_combat', 'swing', 'hurt', 'death', 'roll', 'block')
ENEMY_CLIPS = ('attack', 'death', 'hurt', 'idle', 'move', 'recover', 'telegraph')
FSM_STATES = ('idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead')
GRIP_ROTATION = [0.8660254, 0.0, 0.0, 0.5]


class CharacterError(ValueError):
    """Fail-closed import/release contract error."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    write_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def write_bytes(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.import-tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def contained(root, rel):
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise CharacterError('unsafe relative path: ' + str(rel))
    out = Path(root) / path
    if Path(root).resolve() not in out.resolve().parents:
        raise CharacterError('path escapes root: ' + str(rel))
    if any(p.is_symlink() for p in [out] + list(out.parents) if p != Path(root).parent):
        raise CharacterError('symlink not admitted: ' + str(rel))
    return out


def glb_document(raw):
    if len(raw) < 28 or raw[:4] != b'glTF':
        raise CharacterError('invalid GLB header')
    version, length, chunk_length, kind = struct.unpack_from('<IIII', raw, 4)
    if version != 2 or length != len(raw) or kind != 0x4e4f534a or chunk_length + 20 > length:
        raise CharacterError('invalid GLB length/version/JSON')
    try:
        g = json.loads(raw[20:20 + chunk_length])
    except (ValueError, UnicodeError) as exc:
        raise CharacterError('invalid GLB JSON') from exc
    for entry in g.get('buffers', []) + g.get('images', []):
        if 'uri' in entry:
            raise CharacterError('external GLB resource not admitted')
    return g


def inspect_glb(raw, row):
    g = glb_document(raw)
    body, props, total = 0, {}, 0
    for mesh in g['meshes']:
        count = 0
        for primitive in mesh['primitives']:
            if primitive.get('mode', 4) != 4:
                raise CharacterError('non-triangle primitive')
            accessor = g['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]
            if accessor['count'] % 3:
                raise CharacterError('incomplete triangle')
            count += accessor['count'] // 3
        name = mesh.get('name', '')
        if name.startswith('kit_body'):
            body += count
        elif name.startswith('kit_acc_'):
            props[name] = props.get(name, 0) + count
        else:
            raise CharacterError('unclassified mesh: ' + name)
        total += count
    if not 0 < body < 700 or not 0 < row['tris_body'] < 700:
        raise CharacterError('body budget must be < 700: ' + row['id'])
    if any(v > 200 for v in props.values()):
        raise CharacterError('prop budget must be <= 200: ' + row['id'])
    if (body, total) != (row['tris_body'], row['tris_glb_total']):
        raise CharacterError('manifest triangle counts differ from GLB: ' + row['id'])
    joints = [g['nodes'][i]['name'] for skin in g.get('skins', []) for i in skin['joints']]
    clips = sorted(x['name'] for x in g.get('animations', []))
    if joints != row['joints'] or clips != sorted(row['clips']) or len(joints) != 16:
        raise CharacterError('rig/clip inventory mismatch: ' + row['id'])
    if not all(c in clips for c in ['idle', 'walk']):
        raise CharacterError('missing required clip')
    if any(s.get('interpolation', 'LINEAR') != 'STEP' for a in g['animations'] for s in a['samplers']):
        raise CharacterError('unheld animation keys')
    return {'body_triangles': body, 'prop_triangles': props, 'total_triangles': total,
            'joints': joints, 'clips': clips, 'materials': [m.get('extras', {}).get('n64', {}) for m in g['materials']]}


def latest_export(lane):
    lane = Path(lane)
    candidates = list((lane / 'build').glob('export*/manifest.json'))
    candidates += list((lane / 'published').glob('manifest.json'))
    if not candidates:
        raise CharacterError('no character export manifest found')
    # Fail on an incomplete newest export, never silently downgrade to an older good one.
    return max(candidates, key=lambda p: (p.stat().st_mtime_ns, str(p))).parent


def validate_export(source):
    source = Path(source).resolve()
    original = (source / 'manifest.json').read_bytes()
    m = json.loads(original)
    rows = m.get('characters', [])
    if not rows or m.get('count') != len(rows):
        raise CharacterError('manifest count mismatch')
    seen, result = {}, []
    for original_row in rows:
        row = copy.deepcopy(original_row)
        if not all(ID.fullmatch(str(row.get(k, ''))) for k in ['id', 'pack']):
            raise CharacterError('invalid character identifier')
        key = row['pack'] + '/' + row['id']
        if key in seen:
            raise CharacterError('duplicate character: ' + key)
        seen[key] = True
        if row.get('audit_pass') is not True or row.get('gate_pass') is not True or row.get('audit_errors') or row.get('gate_errors'):
            raise CharacterError('source gate failed: ' + key)
        if not SHA.fullmatch(str(row.get('sha256', ''))):
            raise CharacterError('invalid sha256 token: ' + key)
        path = contained(source, row['file'])
        if not path.is_file():
            raise CharacterError('missing GLB: ' + row['file'])
        raw = path.read_bytes()
        if sha(raw) != row['sha256']:
            raise CharacterError('hash mismatch: ' + row['file'])
        if row['bytes'] != len(raw):
            raise CharacterError('byte count mismatch: ' + key)
        row['measured'] = inspect_glb(raw, row)
        row['internal_only'] = bool(row.get('restricted')) or row['id'] in RESTRICTED_IDS or bool(row.get('internal_only')) or row.get('public_release') is False
        row['public_release'] = not row['internal_only']
        row['glb'] = 'characters/{}/{}/{}.glb'.format('internal' if row['internal_only'] else 'assets', row['pack'], row['id'])
        result.append((row, raw))
    if (source / 'manifest.json').read_bytes() != original:
        raise CharacterError('source export changed during import; retry after export completes')
    return original, result


def glb_chunks(raw):
    """(JSON document, BIN chunk bytes) of a GLB admitted by glb_document."""
    g = glb_document(raw)
    offset = 20 + struct.unpack_from('<I', raw, 12)[0]
    if offset == len(raw):
        return g, b''
    if offset + 8 > len(raw):
        raise CharacterError('truncated GLB BIN chunk')
    length, kind = struct.unpack_from('<II', raw, offset)
    if kind != 0x004E4942 or offset + 8 + length > len(raw):
        raise CharacterError('invalid GLB BIN chunk')
    return g, raw[offset + 8:offset + 8 + length]


def verify_additive(old, new):
    """The new GLB is the old one plus appended combat animations; nothing old may change."""
    od, ob = glb_chunks(old)
    nd, nb = glb_chunks(new)
    if nb[:len(ob)] != ob:
        raise CharacterError('character GLB rewrote existing BIN bytes')
    if set(nd) != set(od):
        raise CharacterError('character GLB changed its top-level glTF keys')
    for key, value in od.items():
        if key in ('accessors', 'bufferViews', 'animations'):
            if nd[key][:len(value)] != value:
                raise CharacterError('character GLB changed existing ' + key)
        elif key == 'buffers':
            strip = lambda rows: [{k: v for k, v in r.items() if k != 'byteLength'} for r in rows]
            if strip(nd[key]) != strip(value) or any(n.get('byteLength', 0) < o.get('byteLength', 0) for n, o in zip(nd[key], value)):
                raise CharacterError('character GLB changed its buffers')
        elif nd[key] != value:
            raise CharacterError('character GLB changed ' + key)
    added = [a.get('name') for a in nd['animations'][len(od.get('animations', [])):]]
    if sorted(added) != sorted(COMBAT_CLIPS):
        raise CharacterError('character GLB must append exactly the six combat clips')


def read_sums(source):
    """SHA256SUMS of a combat export: one `<sha256>  <relative path>` line per GLB."""
    path = Path(source) / 'SHA256SUMS'
    if not path.is_file():
        raise CharacterError('combat export requires SHA256SUMS')
    sums = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-f]{64})\s+\*?(\S+)', line.strip())
        if not match:
            raise CharacterError('malformed SHA256SUMS line')
        digest, rel = match.groups()
        contained(source, rel)
        if rel in sums:
            raise CharacterError('duplicate SHA256SUMS entry: ' + rel)
        sums[rel] = digest
    present = sorted(p.relative_to(source).as_posix() for p in Path(source).rglob('*.glb'))
    if present != sorted(sums):
        raise CharacterError('SHA256SUMS does not list exactly the exported GLBs')
    for rel, digest in sums.items():
        if sha(contained(source, rel).read_bytes()) != digest:
            raise CharacterError('SHA256SUMS hash mismatch: ' + rel)
    return sums


def mesh_triangles(g, mesh):
    count = 0
    for primitive in mesh['primitives']:
        if primitive.get('mode', 4) != 4:
            raise CharacterError('non-triangle primitive')
        accessor = g['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]
        if accessor['count'] % 3:
            raise CharacterError('incomplete triangle')
        count += accessor['count'] // 3
    return count


def inspect_enemy(raw, row):
    g = glb_document(raw)
    body = 0
    for mesh in g['meshes']:
        if not mesh.get('name', '').startswith('kit_body'):
            raise CharacterError('unclassified enemy mesh: ' + mesh.get('name', ''))
        body += mesh_triangles(g, mesh)
    if not 0 < body < 500 or body != row.get('tris_body'):
        raise CharacterError('enemy body budget must be < 500 and match the manifest: ' + row['id'])
    joints = [g['nodes'][i]['name'] for skin in g.get('skins', []) for i in skin['joints']]
    clips = sorted(a['name'] for a in g.get('animations', []))
    if joints != row.get('joints') or clips != sorted(row.get('clips', [])) or clips != sorted(ENEMY_CLIPS):
        raise CharacterError('enemy rig/clip inventory mismatch: ' + row['id'])
    if any(s.get('interpolation', 'LINEAR') != 'STEP' for a in g['animations'] for s in a['samplers']):
        raise CharacterError('unheld enemy animation keys')
    root = {i for i, node in enumerate(g['nodes']) if node.get('name') == 'root'}
    if any(c['target'].get('node') in root for a in g['animations'] for c in a['channels']):
        raise CharacterError('enemy root joint is animated (root motion): ' + row['id'])
    return {'body_triangles': body, 'joints': joints, 'clips': clips}


def inspect_prop(raw, row):
    g = glb_document(raw)
    if g.get('skins') or g.get('animations'):
        raise CharacterError('prop must be one rigid unanimated mesh: ' + row['id'])
    total = 0
    for mesh in g['meshes']:
        if not mesh.get('name', '').startswith('kit_acc_'):
            raise CharacterError('unclassified prop mesh: ' + mesh.get('name', ''))
        total += mesh_triangles(g, mesh)
    if not 0 < total <= 200 or total != row.get('tris'):
        raise CharacterError('prop budget must be <= 200 and match the manifest: ' + row['id'])
    if row.get('node') not in [node.get('name') for node in g['nodes']]:
        raise CharacterError('prop node missing: ' + row['id'])
    return {'triangles': total}


def validate_combat(source, manifest, records):
    """Enemy/prop rows of a combat export, verified like character rows; None for a cast-only export."""
    if 'enemies' not in manifest and 'props' not in manifest:
        return None
    source = Path(source).resolve()
    sums = read_sums(source)
    for row, _ in records:
        if sums.get(row['file']) != row['sha256']:
            raise CharacterError('SHA256SUMS disagrees with the manifest: ' + row['file'])
    rows, raws = {'enemies': [], 'props': []}, []
    for kind, folder in (('enemies', 'enemies'), ('props', 'props')):
        seen = {}
        for original in manifest.get(kind, []):
            row = copy.deepcopy(original)
            if not all(ID.fullmatch(str(row.get(k, ''))) for k in ['id', 'pack']):
                raise CharacterError('invalid combat identifier')
            key = row['pack'] + '/' + row['id']
            if key in seen:
                raise CharacterError('duplicate combat row: ' + key)
            seen[key] = True
            if not SHA.fullmatch(str(row.get('sha256', ''))):
                raise CharacterError('invalid sha256 token: ' + key)
            path = contained(source, row['file'])
            if not path.is_file():
                raise CharacterError('missing GLB: ' + row['file'])
            raw = path.read_bytes()
            if sha(raw) != row['sha256'] or sums.get(row['file']) != row['sha256']:
                raise CharacterError('hash mismatch: ' + row['file'])
            if row.get('bytes') != len(raw):
                raise CharacterError('byte count mismatch: ' + key)
            if kind == 'enemies':
                states = row.get('fsm_state_clip', {})
                if row.get('archetype_id') != row['id'] or not ID.fullmatch(str(row.get('template', ''))):
                    raise CharacterError('enemy archetype/template invalid: ' + key)
                if sorted(states) != sorted(FSM_STATES) or any(clip not in row.get('clips', []) for clip in states.values()):
                    raise CharacterError('enemy FSM clip map incomplete: ' + key)
                row['measured'] = inspect_enemy(raw, row)
            else:
                row['measured'] = inspect_prop(raw, row)
            row['glb'] = 'characters/combat/{}/{}/{}.glb'.format(folder, row['pack'], row['id'])
            rows[kind].append(row)
            raws.append((row['glb'], raw))
    for row, _ in records:
        block = row.get('combat')
        if block is None:
            continue
        grip = block.get('weapon_grip', {})
        move = grip.get('translation')
        if (row['internal_only'] or not all(clip in row['clips'] for clip in COMBAT_CLIPS) or grip.get('joint') != 'hand_r'
                or grip.get('rotation_xyzw') != GRIP_ROTATION or not isinstance(move, list) or len(move) != 3
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 0.5 for v in move)):
            raise CharacterError('combatant clips or weapon grip invalid: ' + row['id'])
    clips = manifest.get('character_clips', {})
    if sorted(clips.get('combat_metadata', {})) != sorted(COMBAT_CLIPS):
        raise CharacterError('combat clip metadata incomplete')
    if not any(row.get('kind') == 'weapon' for row in rows['props']):
        raise CharacterError('combat export has no weapon prop')
    templates = {}
    for row in rows['enemies']:
        templates.setdefault(row['template'], row['id'])
    data = {'schema': 'hermes64-combat/1', 'source_sha256sums': sha((source / 'SHA256SUMS').read_bytes()),
            'character_clips': clips, 'conventions': manifest.get('conventions', {}), 'templates': templates,
            'enemies': rows['enemies'], 'props': rows['props']}
    return data, raws


def existing_rows(root):
    rows = {}
    for rel in ('characters/manifest.json', 'characters/internal/manifest.json'):
        path = Path(root) / rel
        if path.is_file():
            for row in read_json(path).get('characters', []):
                rows[row['pack'] + '/' + row['id']] = row
    return rows


def check_changes(root, manifest, records):
    """Over an existing import, only declared additive file changes are admitted; no row may vanish."""
    before = existing_rows(root)
    if not before:
        return []
    incoming = {row['pack'] + '/' + row['id'] for row, _ in records}
    dropped = sorted(set(before) - incoming)
    if dropped:
        raise CharacterError('import would drop existing characters: ' + ', '.join(dropped))
    declared = {row.get('file'): row for row in manifest.get('changed_hashes_vs_published_r21', [])}
    changed = []
    for row, raw in records:
        old = before.get(row['pack'] + '/' + row['id'])
        if old is None or old['sha256'] == row['sha256']:
            continue
        claim = declared.get(row['file'])
        if not claim or claim.get('published_r21') != old['sha256'] or claim.get('combat') != row['sha256']:
            raise CharacterError('undeclared character hash change: ' + row['file'])
        old_path = contained(root, old['glb'])
        if not old_path.is_file():
            raise CharacterError('previous character bytes missing: ' + old['glb'])
        old_raw = old_path.read_bytes()
        if sha(old_raw) != old['sha256']:
            raise CharacterError('previous character bytes changed: ' + old['glb'])
        verify_additive(old_raw, raw)
        changed.append({'file': row['file'], 'before': old['sha256'], 'after': row['sha256']})
    return changed


def build_bindings(fallbacks, records):
    index = {(r['pack'], r['id']): r for r, _ in records}
    out = []
    for fallback in fallbacks['characters']:
        role = fallback['authored_variant']
        key = ('polar_pod', COATS[fallback['params']['coat']]) if role == 'cat' else ROLES.get(role)
        if key not in index or index[key]['internal_only']:
            raise CharacterError('no public character mapping for ' + role)
        r = index[key]
        row = copy.deepcopy(fallback)
        row.update(glb=r['glb'], sha256=r['sha256'], placeholder=False,
                   character_id=r['id'], character_pack=r['pack'], source_rig=r['skeleton'],
                   bone_names=r['joints'], animations=r['clips'], tri_count=r['tris_glb_total'],
                   vertex_color_encoding='linear_gltf', fallback=copy.deepcopy(fallback),
                   body_triangles=r['tris_body'], prop_triangles=r['measured']['prop_triangles'],
                   internal_only=False, public_release=True,
                   reason='real exported cast; story identity retained, no rig retargeting',
                   fidelity=('approximate coat family; original coat identity preserved' if role == 'cat' else
                             'cast stand-in; not a bespoke Last Light costume' if key[0] == 'forest_village' else 'authored polar cast'))
        out.append(row)
    return {'schema': 'hermes64-characters/1', 'characters': out}


def import_characters(source, root=ROOT):
    root, source = Path(root), Path(source)
    raw_manifest, records = validate_export(source)
    manifest = json.loads(raw_manifest)
    combat = validate_combat(source, manifest, records)
    bindings = build_bindings(read_json(root / 'kits/bindings.json'), records)
    changed = check_changes(root, manifest, records)
    # Validate everything before the first destination write. Immutable source hashes guard later loads.
    for row, raw in records:
        write_bytes(root / row['glb'], raw)
    for rel, raw in (combat[1] if combat else []):
        write_bytes(root / rel, raw)
    write_bytes(root / 'characters/internal/source-manifest.json', raw_manifest)
    write_bytes(root / 'characters/.gitignore', b'/internal/\n**/cameo_visor_01.glb\n*.import-tmp\n')
    shared = {'schema': 'hermes64-characters/1', 'source_manifest_sha256': sha(raw_manifest),
              'source_export': source.name}
    public = [r for r, _ in records if not r['internal_only']]
    private = [r for r, _ in records if r['internal_only']]
    # Restricted params/hashes are internal data too, not just the binary likeness.
    write_json(root / 'characters/internal/manifest.json', dict(shared, count=len(private), characters=private))
    write_json(root / 'characters/manifest.json', dict(shared, count=len(public), characters=public))
    if combat:
        write_json(root / 'characters/combat/manifest.json', dict(combat[0], source_manifest_sha256=sha(raw_manifest),
                                                                  source_export=source.name))
    write_json(root / 'bindings.json', bindings)
    result = {'status': 'imported', 'count': len(records), 'bindings': len(bindings['characters']),
              'internal': sum(r['internal_only'] for r, _ in records), 'source_manifest_sha256': sha(raw_manifest),
              'changed_files': len(changed)}
    if combat:
        result.update(enemies=len(combat[0]['enemies']), props=len(combat[0]['props']),
                      combatants=sum('combat' in r for r, _ in records))
    return result


def package_public(root, target):
    """Allowlisted source bundle, not an engine binary export. Restricted bytes never copied."""
    root, target = Path(root).resolve(), Path(target).resolve()
    if target.exists():
        raise CharacterError('public package destination must be fresh')
    manifest = read_json(root / 'characters/manifest.json')
    private_path = root / 'characters/internal/manifest.json'
    private = read_json(private_path)['characters'] if private_path.is_file() else []
    blocked = {r['glb']: r['sha256'] for r in manifest['characters'] + private if r.get('internal_only') or not r.get('public_release', False) or r['id'] in RESTRICTED_IDS}
    allowed = [r for r in manifest['characters'] if r['glb'] not in blocked]
    for row in allowed:
        raw = contained(root, row['glb']).read_bytes()
        if sha(raw) != row['sha256'] or sha(raw) in blocked.values():
            raise CharacterError('release hash mismatch or restricted bytes')
    # Exclude evidence, internal manifests, references and arbitrary untracked files by construction.
    roots = ['adventure_maker', 'story', 'runtime/godot', 'kits', 'packs', 'examples', 'tools', 'characters']
    files = []
    for base in roots:
        for p in (root / base).rglob('*'):
            rel = p.relative_to(root).as_posix()
            if not p.is_file() or p.is_symlink() or any(x in p.parts for x in ['internal', '__pycache__', '.godot', '.git']):
                continue
            if p.suffix in ['.pyc', '.pyo'] or rel in blocked or rel == 'characters/manifest.json':
                continue
            if p.suffix == '.glb' and (sha(p.read_bytes()) in blocked.values() or p.stem in RESTRICTED_IDS):
                continue
            files.append((rel, p.read_bytes()))
    target.mkdir(parents=True)
    for rel, raw in files:
        write_bytes(target / rel, raw)
    public_manifest = dict(manifest, count=len(allowed), characters=allowed)
    write_json(target / 'characters/manifest.json', public_manifest)
    bindings = read_json(root / 'bindings.json')
    bindings['characters'] = [r if r.get('public_release', False) and not r.get('internal_only') else r['fallback'] for r in bindings['characters']]
    write_json(target / 'bindings.json', bindings)
    report = {'status': 'packaged', 'scope': 'public source package, not Godot binary export',
              'excluded': sorted(blocked), 'characters': len(allowed)}
    write_json(target / 'release-report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='export directory; default newest local manifest (fail closed)')
    parser.add_argument('--public-package', type=Path)
    parser.add_argument('--capture', type=Path, help='fresh evidence/characters directory for real all-room capture/replay')
    args = parser.parse_args(argv)
    source = args.source or latest_export(ROOT.parent / 'lane-characters')
    print(json.dumps(import_characters(source), sort_keys=True), flush=True)
    if args.public_package:
        print(json.dumps(package_public(ROOT, args.public_package), sort_keys=True), flush=True)
    if args.capture:
        sys.path.insert(0, str(ROOT))
        from characters.integration import capture_games
        capture_games(args.capture.resolve())
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (CharacterError, OSError, KeyError, ValueError) as exc:
        print('CHARACTERS REJECTED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
