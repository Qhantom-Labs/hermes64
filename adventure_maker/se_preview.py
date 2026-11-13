"""STYLEENGINE-2 look-and-fix loop: render a made piece in the game's shading from fixed angles.

`hermes64_character action=make ... render=true` (or `make id=<built id> render=true` alone, no rebuild) renders the
piece through the production asset shading (runtime view/assets.gd + the N64 world shader) in the pack's light
profile: front, side, back, top, three-quarter and one game-distance view, as one sheet PNG (3 x 2 tiles in that
order) plus one PNG per view, with the numbers (triangles, colours, size, texture energy, budget, gates). A
vision-capable agent looks at the sheet, compares it with its intent and calls make again with a revised spec.

Godot runs through the sandboxed Runner (writes only in the project, no network) in a real window, like the cover
renderer and `hermes64_open screenshots`; a host without a graphical Godot gets the numbers and a plain reason.
"""
import hashlib
import json
import os
from pathlib import Path
import time

from .safety import fail, inspect_path

SCRIPT = Path(__file__).with_name('se_preview.gd')
TILE = 320
VIEWS = ('front', 'side', 'back', 'top', 'three_quarter', 'game')
SKIP_DIRS = ('.godot', '.git', '__pycache__')


def _digest(source):
    h = hashlib.sha256()
    for parent, dirs, files in os.walk(str(source), followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(parent) / name
            h.update(path.relative_to(source).as_posix().encode() + b'\0' + path.read_bytes())
    h.update(SCRIPT.read_bytes())
    return h.hexdigest()


def stage(c, project):
    """The shipped runtime + the preview script under .maker/local (cached by digest)."""
    source = c.shipped('runtime/godot')
    tag = _digest(source)[:16]
    rel = '.maker/local/styleengine/preview/runtime-' + tag
    marker = rel + '/preview-stage.json'
    if project.path(marker).is_file():
        return rel
    count = total = 0
    for parent, dirs, files in os.walk(str(source), followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(parent) / name
            inspect_path(path)
            if path.suffix in ('.pyc', '.pyo'):
                fail('component_protocol', 'Runtime template cannot contain Python bytecode')
            count += 1
            total += path.stat().st_size
            if count > 1000 or total > 32 * 1024 * 1024:
                fail('limit', 'Runtime template file/size limit exceeded')
            project.write_bytes(rel + '/' + path.relative_to(source).as_posix(), path.read_bytes())
    project.write_bytes(rel + '/se_preview.gd', SCRIPT.read_bytes())
    project.write_json(marker, {'runtime': tag, 'files': count + 1})
    return rel


def theme(c, pack_id):
    """The pack's view block (light profiles, n64 convention, fog) as the game uses it; neutral when unknown."""
    from .assets_v3 import n64_look
    out = {}
    for pid in dict.fromkeys([pack_id, pack_id.split('_m')[0], pack_id.split('_s')[0], 'castle_keep']):
        path = Path(c.root) / 'packs' / pid / 'view.json'
        if path.is_file():
            out = json.loads(path.read_text(encoding='utf-8'))
            out['pack_id'] = pid
            break
    try:
        out['n64'] = n64_look(c, out)
    except Exception:
        out['n64'] = {}
    env = Path(c.root) / 'kits/library' / pack_id / 'env'
    base_env = Path(c.root) / 'kits/library' / str(out.get('kit_pack_id') or out.get('pack_id') or '') / 'env'
    out['env_root'] = str(env if env.is_dir() else base_env)
    out.setdefault('fog', {'color': '#808080', 'near': 40, 'far': 200})
    if isinstance(out.get('fog'), dict):                 # a preview is close-up: keep fog from greying the piece
        out['fog'] = dict(out['fog'], near=max(float(out['fog'].get('near', 40) or 40), 60.0),
                          far=max(float(out['fog'].get('far', 200) or 200), 240.0))
    return out


def render(settings, project, pack_id, pieces, out_rel, profile='exterior', timeout=150):
    """pieces: [{'id', 'parts': [{'glb': abs path, 'at': [x, y, z], 'yaw': deg, 'scale': s}]}] -> report dict with
    project-relative sheet/shot paths, or {'ok': False, 'why': ...} when no graphical Godot ran."""
    from .adapters import Components
    from .runner import locate
    t0 = time.monotonic()
    c = Components(settings, project)
    try:
        exe = locate('godot', settings.get('godot_path', ''))
    except Exception as e:
        return {'ok': False, 'why': 'no Godot for previews here (%s); the numbers above still hold' % str(e)[:160]}
    rel = stage(c, project)
    for p in pieces:
        p['out_dir'] = str(project.path(out_rel + '/' + p['id']))
        project.path(out_rel + '/' + p['id']).mkdir(parents=True, exist_ok=True)
    job = {'theme': theme(c, pack_id), 'tile': TILE, 'profile': profile, 'pieces': pieces,
           'report': str(project.path(out_rel + '/report.json'))}
    project.write_json(out_rel + '/job.json', job)
    if project.path(out_rel + '/report.json').is_file():
        project.path(out_rel + '/report.json').unlink()
    argv = [exe, '--audio-driver', 'Dummy', '--quit-after', '2400', '--path', str(project.path(rel)),
            '--script', 'res://se_preview.gd', '--', str(project.path(out_rel + '/job.json'))]
    from . import platforms
    if platforms.host() == 'linux':     # MERGEPREP-2: PLATFORMS' capture route (private Xvfb inside the Runner sandbox)
        from .linux_display import prepare
        from .safety import Fault
        try:
            argv = prepare([exe] + argv[3:], settings)      # prepare adds --audio-driver Dummy itself
        except Fault as e:
            return {'ok': False, 'why': 'no display for previews here (%s); the numbers above still hold' % str(e)[:160],
                    'seconds': round(time.monotonic() - t0, 2)}
    proc = c.runner.run(argv, project.root, timeout=timeout)
    project.write_json(out_rel + '/godot.process.json', {k: proc.get(k) for k in ('returncode', 'elapsed_seconds')})
    if not project.path(out_rel + '/report.json').is_file():
        return {'ok': False, 'why': 'the preview renderer wrote no report (exit %s): %s' % (
            proc.get('returncode'), ((proc.get('stderr') or '')[-300:]).replace('\n', ' ')),
            'seconds': round(time.monotonic() - t0, 2)}
    rep = project.read_json(out_rel + '/report.json')
    root = str(project.root) + '/'
    out = {'ok': bool(rep.get('ok')), 'seconds': round(time.monotonic() - t0, 2), 'views': list(VIEWS),
           'sheet_layout': 'top row: front, side, back; bottom row: top, three-quarter, game distance', 'pieces': []}
    for p in rep.get('pieces', []):
        out['pieces'].append({'id': p.get('id'), 'ok': p.get('ok'),
                              'sheet': str(p.get('sheet', '')).replace(root, ''),
                              'sheet_abs': str(p.get('sheet', '')),
                              'shots': {k: str(v).replace(root, '') for k, v in (p.get('shots') or {}).items()},
                              'size_m': [round(float(x), 3) for x in p.get('size_m', [])]})
    return out


def latest_file(project, rid):
    """The newest built GLB of a project recipe id (assets/PROVENANCE.json), or None."""
    if not project.path('assets/PROVENANCE.json').is_file():
        return None
    rows = [r for r in (project.read_json('assets/PROVENANCE.json') or {}).get('assets', [])
            if r.get('id') in (rid, 'gen:' + rid) and r.get('file')]
    return rows[-1]['file'] if rows else None
