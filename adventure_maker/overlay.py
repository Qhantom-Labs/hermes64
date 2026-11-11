"""Texture slot values and the separable OVERLAY folder (lane L3).

Two sources fill a pack's texture slots (declared in kits/packs/<kit pack>/slots.json, kits/core/mask_recipe.py):

1. the project's own values, `textures/slots.json`:
       {"format": "hermes64-texture-values/1", "slots": {"banner_crest": {<hermes64-mask/1 recipe>}}}
   They are part of the game and ship in every export.
2. an OVERLAY, the project folder `overlay/` that can be removed without touching the game:
       overlay/overlay.json   {"format": "hermes64-overlay/1", "name", "enabled": true, "licence", "source",
                               "textures": {slot: {"file": "textures/<slot>.mask.json", "sha256", "licence",
                                                   "source"}},
                               "audio": {"slots": "audio/slots.json", "import": "audio/import",
                                         "licence", "source"}}
       overlay/textures/*.mask.json   mask recipes (JSON only: no images, no paths inside)
       overlay/<any>/*.png|jpg|jpeg   IMAGE values (overlay only, sheet slots declaring "image"): a texture row
                                      {"kind": "image", "file", "sha256", "licence", "source", "permission", "crop",
                                       "grid", "mask", "mode", "filter", "colours"}; checks + conversion in
                                      overlay_image.py (Pillow only when an overlay build bakes one)
       overlay/audio/...              AUDIOPIPE's own slots.json + import folder (its schema and verifier, unchanged)
   Overlay values win over project values. Mode "neutral" (export/build option, or "enabled": false) ignores the
   overlay entirely; `leak_check` proves a staged tree carries none of the overlay's bytes.

Build: `apply_build` is called once by assets_v3.runtime_snapshot. It bakes the slot atlases/sheets into
<folder>/runtime/slots/<sha256>.png, adds theme["texture_slots"] for runtime/godot/view/slots.gd, merges overlay
audio rows into audio.json (rows lowered by AUDIOPIPE's runtime_rows), and writes <folder>/slots-report.json.
"""
import hashlib
import json
from pathlib import Path

from .safety import fail

OVERLAY_FORMAT = 'hermes64-overlay/1'
VALUES_FORMAT = 'hermes64-texture-values/1'
OVERLAY_KEYS = {'format', 'name', 'enabled', 'licence', 'source', 'textures', 'audio', 'note'}
TEXTURE_KEYS = {'file', 'sha256', 'licence', 'source'}
AUDIO_KEYS = {'slots', 'import', 'licence', 'source'}
MAX_OVERLAY_FILES = 64
MAX_RECIPE_FILE = 16384


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _mask():
    try:
        from ..kits.core import mask_recipe
    except ImportError:
        from kits.core import mask_recipe
    return mask_recipe


def _inside(base, rel, what):
    """A relative file path inside `base`, no traversal, no absolute path, no symlink escape."""
    if not isinstance(rel, str) or not rel or rel.startswith(('/', '\\')) or '..' in Path(rel).parts or ':' in rel:
        fail('overlay_path', '%s must be a relative path inside the overlay folder' % what)
    path = (base / rel)
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        fail('overlay_missing', '%s not found: %s' % (what, rel))
    if base.resolve() not in resolved.parents:
        fail('overlay_path', '%s escapes the overlay folder' % what)
    return resolved


def _faults(fn):
    """Recipe and image-value errors surface as ordinary plugin faults (same stable code)."""
    def wrapped(*a, **k):
        M = _mask()
        from .overlay_image import ImageSlotError
        try:
            return fn(*a, **k)
        except (M.MaskError, ImageSlotError) as e:
            fail(e.code, str(e))
    wrapped.__name__, wrapped.__doc__ = fn.__name__, fn.__doc__
    return wrapped


@_faults
def load_overlay(folder):
    """Read and verify an overlay folder. Returns {'root', 'manifest', 'textures': {slot: recipe},
    'files': [{'path', 'sha256', 'bytes', 'kind', 'slot'}]} or None when there is no overlay.json."""
    root = Path(folder)
    if not (root / 'overlay.json').is_file():
        return None
    raw = (root / 'overlay.json').read_bytes()
    try:
        man = json.loads(raw)
    except ValueError:
        fail('overlay_format', 'overlay.json is not JSON')
    if not isinstance(man, dict) or man.get('format') != OVERLAY_FORMAT:
        fail('overlay_format', 'overlay.json format must be %r' % OVERLAY_FORMAT)
    extra = set(man) - OVERLAY_KEYS
    if extra:
        fail('overlay_format', 'overlay.json: unknown field(s) %s' % sorted(extra))
    for k in ('licence', 'source'):
        if not isinstance(man.get(k), str) or not man[k].strip():
            fail('overlay_licence', 'overlay.json needs a %s field (who made it, under what terms)' % k)
    files = [{'path': 'overlay.json', 'sha256': digest(raw), 'bytes': len(raw), 'kind': 'manifest', 'slot': None}]
    textures = {}
    M = _mask()
    from . import overlay_image as OI
    for slot, row in sorted((man.get('textures') or {}).items()):
        if OI.is_image_row(row):
            spec = OI.validate_spec(row, 'textures.%s' % slot)
            path, data, dims = OI.resolve_file(root, row['file'], 'textures.%s' % slot)
            OI.check_crop(spec, dims, 'textures.%s' % slot)
            if row['sha256'] != digest(data):
                fail('asset_integrity', 'textures.%s: image hash differs from overlay.json' % slot)
            textures[slot] = {'kind': 'image', 'spec': spec, 'raw': data, 'dims': list(dims),
                              'licence': row['licence'], 'source': row['source'], 'permission': row['permission']}
            files.append({'path': row['file'], 'sha256': digest(data), 'bytes': len(data), 'kind': 'image',
                          'slot': slot, 'licence': row['licence'], 'permission': row['permission']})
            continue
        if not isinstance(row, dict) or set(row) - TEXTURE_KEYS or 'file' not in row:
            fail('overlay_format', 'textures.%s needs {file, sha256, licence?, source?}' % slot)
        if not str(row['file']).endswith('.mask.json'):
            fail('overlay_path', 'textures.%s: overlay textures are mask recipes (*.mask.json), not images' % slot)
        path = _inside(root, row['file'], 'textures.%s.file' % slot)
        data = path.read_bytes()
        if len(data) > MAX_RECIPE_FILE:
            fail('mask_size', 'textures.%s: recipe file is %d bytes' % (slot, len(data)))
        if row.get('sha256') and row['sha256'] != digest(data):
            fail('asset_integrity', 'textures.%s: file hash differs from overlay.json' % slot)
        try:
            recipe = json.loads(data)
        except ValueError:
            fail('overlay_format', 'textures.%s is not JSON' % slot)
        M.validate(recipe)
        textures[slot] = recipe
        files.append({'path': row['file'], 'sha256': digest(data), 'bytes': len(data), 'kind': 'texture', 'slot': slot})
    audio = man.get('audio')
    if audio is not None:
        if not isinstance(audio, dict) or set(audio) - AUDIO_KEYS or 'slots' not in audio:
            fail('overlay_format', 'audio needs {slots, import?, licence?, source?}')
        sp = _inside(root, audio['slots'], 'audio.slots')
        imp = _inside(root, audio.get('import', 'audio/import'), 'audio.import')
        files.append({'path': audio['slots'], 'sha256': digest(sp.read_bytes()), 'bytes': sp.stat().st_size,
                      'kind': 'audio_slots', 'slot': None})
        for p in sorted(imp.rglob('*')):
            if p.is_file():
                rel = p.relative_to(root.resolve()).as_posix()
                files.append({'path': rel, 'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size,
                              'kind': 'audio', 'slot': None})
    if len(files) > MAX_OVERLAY_FILES + 1:
        fail('overlay_format', 'overlay has more than %d files' % MAX_OVERLAY_FILES)
    return {'root': root, 'manifest': man, 'textures': textures, 'files': files}


def overlay_audio_rows(ov):
    """Overlay audio through AUDIOPIPE's own verifier/slot schema/lowering (no audio code here)."""
    audio = ov['manifest'].get('audio')
    if not audio:
        return {}
    from . import audio_import as ai
    folder = _inside(ov['root'], audio.get('import', 'audio/import'), 'audio.import')
    if not (folder / 'manifest.json').is_file():
        fail('audio_import', 'overlay audio import folder has no manifest.json (import with hermes64_audio / tools/audio_import.py --out)')
    manifest, problems = ai.verify(folder)
    if problems:
        fail('asset_integrity', 'Overlay audio changed: ' + '; '.join(problems[:5]))
    slots = ai.validate_slots(json.loads(_inside(ov['root'], audio['slots'], 'audio.slots').read_text(encoding='utf-8')), manifest['assets'])
    return ai.runtime_rows(slots, manifest['assets'], folder)


def project_values(project):
    if not project.path('textures/slots.json').is_file():
        return {}
    doc = project.read_json('textures/slots.json')
    if not isinstance(doc, dict) or doc.get('format') != VALUES_FORMAT or not isinstance(doc.get('slots'), dict):
        fail('texture_slots', 'textures/slots.json format must be %r with a slots object' % VALUES_FORMAT)
    for k, v in doc['slots'].items():
        if isinstance(v, dict) and 'kind' in v:
            fail('image_overlay_only', 'textures/slots.json %s: picture values belong in overlay/ only (removable, '
                 'never shipped by a neutral export); project values are mask recipes' % k)
    return dict(doc['slots'])


def pack_slots(root, kit_pack):
    """The kit pack's slot declarations (validated) or None when the pack declares none."""
    path = Path(root) / 'kits/packs' / kit_pack / 'slots.json'
    if not path.is_file():
        return None, None
    M = _mask()
    try:
        from ..kits.core.packs import Pack
    except ImportError:
        from kits.core.packs import Pack
    pack = Pack(str(Path(root) / 'kits/packs' / kit_pack / 'pack.json'))
    doc = M.validate_slots(json.loads(path.read_text(encoding='utf-8')), kit_pack, pack.palette_names,
                           lambda role: len(pack.mat(role)['texture']['ramp']))
    return doc, pack


SHEET_CONSUMERS = ('sky_signal', 'character_emblem')


def consumers_in(game):
    """Sheet consumers this game actually shows: room presentation keys (sky_signal); character_emblem has no
    runtime consumer in this build."""
    rooms = ((game or {}).get('metadata', {}).get('presentation', {}) or {}).get('rooms', {}) or {}
    return {'sky_signal'} if any(isinstance(r, dict) and 'sky_signal' in r for r in rooms.values()) else set()


@_faults
def bake(root, kit_pack, values, sources=None, consumers=None, images='bake'):
    """Bake filled slots of `kit_pack`. values: {slot: recipe | overlay image value}. Returns ({'atlases': {role:
    png bytes + slots}, 'sheets': {slot: png bytes + consumer}}, rows) where rows report every slot (filled /
    default / pack). images='reference' checks image values but does not decode them (no Pillow; the row has no
    png_sha256): used by the neutral leak check."""
    M = _mask()
    try:
        from ..kits.core import png
    except ImportError:
        from kits.core import png
    doc, pack = pack_slots(root, kit_pack)
    sources = sources or {}
    if doc is None:
        if values:
            fail('texture_slots', 'pack %s declares no texture slots; cannot fill %s' % (kit_pack, sorted(values)))
        return {'atlases': {}, 'sheets': {}}, []
    decl = doc['slots']
    unknown = set(values) - set(decl)
    if unknown:
        fail('texture_slots', 'unknown slot(s) %s for pack %s (declared: %s)' % (sorted(unknown), kit_pack, sorted(decl)))
    fills, sheets, rows = {}, {}, []
    for sid, s in sorted(decl.items()):
        value = values.get(sid)
        src = sources.get(sid, 'project') if value is not None else None
        if value is None and isinstance(s.get('default'), dict) and (s['target'] == 'atlas' or consumers is None
                                                                      or s.get('consumer') in consumers):
            value, src = s['default'], 'pack_default'
        if value is None:
            rows.append({'slot': sid, 'source': 'pack', 'target': s['target']})
            continue
        if isinstance(value, dict) and value.get('kind') == 'image':
            from . import overlay_image as OI
            spec = value['spec']
            if src != 'overlay':
                fail('image_overlay_only', 'slot %s: picture values come from an overlay only' % sid)
            if s['target'] != 'sheet' or not isinstance(s.get('image'), dict):
                fail('image_slot', 'slot %s of pack %s does not accept pictures (no "image" in its slots.json)' % (sid, kit_pack))
            if spec['grid'] not in s['image']['grids']:
                fail('image_range', 'slot %s accepts picture grids %s, not %d' % (sid, s['image']['grids'], spec['grid']))
            row = {'slot': sid, 'source': src, 'target': 'sheet', 'kind': 'image', 'consumer': s['consumer'],
                   'recipe_sha256': OI.spec_sha256(spec), 'image': dict(spec, source_file=Path(spec['file']).name,
                   dims=value['dims'], licence=value['licence'], source=value['source'], permission=value['permission'])}
            if images == 'bake':
                raw = OI.bake(value['raw'], spec, 'textures.%s' % sid)
                sheets[sid] = {'png': raw, 'consumer': s['consumer']}
                row['png_sha256'] = digest(raw)
            rows.append(row)
            continue
        rc = M.validate(value, set(s['tones']))
        row = {'slot': sid, 'source': src, 'target': s['target'], 'recipe_sha256': M.recipe_sha256(rc)}
        if s['target'] == 'atlas':
            fills.setdefault(s['role'], []).append((s['cell'], rc, s['tones']))
            row.update(role=s['role'], cell=s['cell'], pieces=s.get('pieces', []))
        else:
            raw = png.encode(M.bake_sheet(s, rc, pack.pal))
            sheets[sid] = {'png': raw, 'consumer': s['consumer']}
            row.update(consumer=s['consumer'], png_sha256=digest(raw))
        rows.append(row)
    atlases = {}
    for role, fl in sorted(fills.items()):
        spec = pack.mat(role)['texture']
        raw = png.encode(M.bake_atlas(spec, pack.pal, pack.id, role, fl))
        atlases[role] = {'png': raw, 'slots': [r['slot'] for r in rows if r.get('role') == role and r.get('recipe_sha256')]}
        for r in rows:
            if r.get('role') == role and r.get('recipe_sha256'):
                r['png_sha256'] = digest(raw)
    return {'atlases': atlases, 'sheets': sheets}, rows


def overlay_mode(c):
    return getattr(c, 'overlay_mode', 'apply')


def plan(c, kit_pack, mode, game=None):
    """(baked, rows, overlay or None) for one build mode, nothing written."""
    if mode not in ('apply', 'neutral'):
        fail('arguments', 'overlay mode must be apply or neutral')
    # A legacy pack with no slot inputs is a true no-op, including in an isolated
    # plugin interpreter without the numeric bake dependencies. Any authored
    # declaration/value/overlay still takes the existing validation path below.
    if (not (Path(c.root) / 'kits/packs' / kit_pack / 'slots.json').is_file()
            and not c.project.path('textures/slots.json').is_file()
            and not c.project.path('overlay/overlay.json').is_file()):
        return {'atlases': {}, 'sheets': {}}, [], None
    ov = load_overlay(c.project.path('overlay')) if mode == 'apply' else None
    if ov is not None and ov['manifest'].get('enabled', True) is False:
        ov = None
    values = project_values(c.project)
    sources = {k: 'project' for k in values}
    if ov is not None:
        for k, v in ov['textures'].items():
            values[k] = v
            sources[k] = 'overlay'
    baked, rows = bake(c.root, kit_pack, values, sources, consumers_in(game))
    return baked, rows, ov


def overlay_reference(c, kit_pack, game=None):
    """What an overlay build WOULD contain (overlay files + overlay-baked PNG hashes), for the neutral leak check.
    Image values are checked but not decoded here (the neutral path never imports Pillow); the PNGs earlier
    overlay builds of this project baked from them are added from their slots-report.json files."""
    overlay_folder = c.project.path('overlay')
    if not (overlay_folder / 'overlay.json').is_file():
        return None
    ov = load_overlay(overlay_folder)
    if ov is None:
        return None
    values = dict(project_values(c.project))
    values.update(ov['textures'])
    baked, rows = bake(c.root, kit_pack, values, {k: 'overlay' for k in ov['textures']}, consumers_in(game),
                       images='reference')
    return {'slots': rows + prior_image_rows(c.project.root), 'overlay': {'files': ov['files']}}


def prior_image_rows(project_root, limit=400):
    """Overlay image rows (with their baked png_sha256) from earlier overlay builds' slots-report.json."""
    out = []
    for i, p in enumerate(sorted(Path(project_root).glob('**/slots-report.json'))):
        if i >= limit:
            break
        try:
            rep = json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        for r in rep.get('slots', []) if isinstance(rep, dict) else []:
            if isinstance(r, dict) and r.get('kind') == 'image' and r.get('source') == 'overlay' and r.get('png_sha256'):
                out.append({'slot': r['slot'], 'source': 'overlay', 'kind': 'image', 'recipe_sha256': r['recipe_sha256'],
                            'png_sha256': r['png_sha256']})
    return out


def apply_build(c, game, kit_pack, folder, sound, theme):
    """assets_v3.runtime_snapshot hook. Mutates `sound` (overlay audio rows) and `theme` (texture_slots); writes the
    baked PNGs and <folder>/slots-report.json. Projects with no slot values, no overlay and no pack default change
    nothing (theme gains no key, so games built before slots stage the same runtime data)."""
    mode = overlay_mode(c)
    baked, rows, ov = plan(c, kit_pack, mode, game)
    report = {'mode': mode, 'pack': kit_pack, 'slots': rows, 'overlay': None, 'written': []}
    if ov is not None:
        audio_rows = overlay_audio_rows(ov)
        for event, row in sorted(audio_rows.items()):
            sound[event] = row
        report['overlay'] = {'name': ov['manifest'].get('name', ''), 'licence': ov['manifest']['licence'],
                             'source': ov['manifest']['source'], 'files': ov['files'],
                             'audio_events': sorted(audio_rows)}
    if not baked['atlases'] and not baked['sheets']:
        c.project.write_json(folder + '/slots-report.json', report)
        return report
    out = {'pack': kit_pack, 'atlases': {}, 'sheets': {}}
    for kind in ('atlases', 'sheets'):
        for key, row in sorted(baked[kind].items()):
            sha = digest(row['png'])
            rel = folder + '/runtime/slots/' + sha + '.png'
            c.project.write_bytes(rel, row['png'])
            entry = {'path': str(c.project.path(rel)), 'sha256': sha}
            entry.update({'slots': row['slots']} if kind == 'atlases' else {'consumer': row['consumer']})
            out[kind][key] = entry
            report['written'].append({'kind': kind[:-1], 'key': key, 'sha256': sha, 'bytes': len(row['png'])})
    theme['texture_slots'] = out
    c.project.write_json(folder + '/slots-report.json', report)
    return report


def release_slots(theme, media):
    """export.stage hook: re-home baked slot PNGs as hash-checked release media (res://media/<sha>.png)."""
    ts = theme.get('texture_slots')
    if not ts:
        return
    for kind in ('atlases', 'sheets'):
        for row in ts.get(kind, {}).values():
            row['path'] = media(row['path'], row['sha256'])


# ---------------------------------------------------------------- leak check
def overlay_fingerprints(report):
    """sha256 set of every overlay source file and every artifact baked from an overlay value."""
    hashes = set()
    ov = report.get('overlay') or {}
    for f in ov.get('files', []):
        hashes.add(f['sha256'])
    for r in report.get('slots', []):
        if r.get('source') == 'overlay':
            hashes.add(r['recipe_sha256'])
            if r.get('png_sha256'):
                hashes.add(r['png_sha256'])
    return hashes


def leak_check(tree, overlay_root, applied_report):
    """Prove a staged/exported tree contains none of an overlay's bytes. Checks every file (and zip members) for:
    an exact hash match with an overlay file or an overlay-derived baked PNG, an overlay recipe hash in its text,
    and any overlay source file's bytes embedded as a substring (files of 64+ bytes). Returns
    {'ok', 'scanned', 'leaks': [...]}."""
    import io
    import zipfile
    ov = load_overlay(overlay_root)
    needles = []
    if ov is not None:
        for f in ov['files']:
            raw = (Path(overlay_root) / f['path']).read_bytes()
            if len(raw) >= 64:
                needles.append((f['path'], raw))
    bad = overlay_fingerprints(applied_report)
    leaks, scanned = [], 0

    def scan(raw, name, depth=0):
        nonlocal scanned
        scanned += 1
        h = digest(raw)
        if h in bad:
            leaks.append({'file': name, 'why': 'hash', 'sha256': h})
        for path, needle in needles:
            if needle in raw:
                leaks.append({'file': name, 'why': 'embedded overlay file', 'overlay_file': path})
        if raw[:4] == b'PK\x03\x04' and depth < 2:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for info in z.infolist():
                        if not info.is_dir():
                            scan(z.read(info), name + '!' + info.filename, depth + 1)
            except zipfile.BadZipFile:
                pass
        if len(raw) < 4 * 1024 * 1024:
            text = raw.decode('latin-1')
            for x in bad:
                if x in text and h != x:
                    leaks.append({'file': name, 'why': 'overlay hash referenced', 'sha256': x})

    for p in sorted(Path(tree).rglob('*')):
        if p.is_file():
            scan(p.read_bytes(), p.relative_to(tree).as_posix())
    return {'ok': not leaks, 'scanned': scanned, 'leaks': leaks}
