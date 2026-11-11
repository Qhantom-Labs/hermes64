"""Cover render boundary: stage the shared Godot runtime once per project, write a job, run the staged cover scene
(runtime/godot/cover/cover.tscn) through the sandboxed argv-only Runner in a real window, read its report.

Asset rows, the N64 look convention merge and the character admission rules are the ones the game runtime uses
(assets_v3.runtime_snapshot, characters.integration.stage_runtime): kit GLBs and cast models are hash-checked here
and again by the Godot resolver. Every write stays inside the project; the job carries absolute paths only to
hash-verified bundle files and to the project's own output folder.
"""
import hashlib
import json
import os
from pathlib import Path

from . import cover_style
from .adapters import Components
from .assets_v3 import data, digest, n64_look
from .runner import locate
from .safety import encode, fail, inspect_path

# output name -> render size (px). card renders at 4x the 245x170 box card so the finished card is a clean box
# downsample; banner/square render natively at their export sizes (higher internal resolution than gameplay).
SIZES = {'card': (980, 680), 'banner': (1280, 640), 'square': (1080, 1080)}
GATE_PASSES = ['subject', 'depth', 'mask', 'noglow', 'classic']
TILE_M = {'snowfield': 2.4, 'ice': 4.0, 'meadow': 3.6, 'dunes': 4.5, 'cobbles': 2.0, 'earth': 3.0, 'stone': 2.4, 'deck': 1.6}
RESTRICTED_IDS = ('cameo_visor_01',)
SKIP_DIRS = ('.godot', '.git', '__pycache__')


def runtime_digest(source):
    h = hashlib.sha256()
    for parent, dirs, files in os.walk(str(source), followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(parent) / name
            inspect_path(path)
            h.update(path.relative_to(source).as_posix().encode() + b'\0')
            h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def admitted_characters(root):
    """Cast rows the runtime may load: public, non-internal, hash-verified (stage_runtime's admission rules)."""
    root = Path(root)
    path = root / 'bindings.json'
    if not path.is_file():
        return []
    bound = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    for row in bound.get('characters', []):
        if row.get('internal_only') or not row.get('public_release', False) or row.get('character_id') in RESTRICTED_IDS:
            continue
        if 'internal' in Path(row['glb']).parts:
            continue
        glb = inspect_path(root / row['glb'])
        if not glb.is_file() or hashlib.sha256(glb.read_bytes()).hexdigest() != row['sha256']:
            fail('asset_integrity', 'Cast binding hash differs: ' + row['glb'])
        out = dict(row, path=str(glb))
        fb = row.get('fallback')
        if isinstance(fb, dict) and fb.get('glb'):
            fp = inspect_path(root / fb['glb'])
            out['fallback'] = dict(fb, path=str(fp))
        rows.append(out)
    return rows


class CoverRenderer:
    def __init__(self, settings, project):
        self.settings = dict(settings or {})
        self.project = project
        self.c = Components(self.settings, project)
        self.root = self.c.root

    # -------------------------------------------------------------- runtime staging (cached per runtime digest)
    def stage(self):
        source = self.c.shipped('runtime/godot')
        self.c.shipped('runtime/godot/cover/cover.tscn')
        tag = runtime_digest(source)[:16]
        rel = '.maker/cover/runtime-' + tag
        dest = self.project.path(rel)
        marker = rel + '/cover-stage.json'
        if self.project.path(marker).is_file() and self.project.read_json(marker).get('runtime') == tag:
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
                self.project.write_bytes(rel + '/' + path.relative_to(source).as_posix(), path.read_bytes())
        self.project.write_json(marker, {'runtime': tag, 'files': count})
        return rel

    # -------------------------------------------------------------- job
    def theme(self, style):
        theme = json.loads(json.dumps(style.view)) if style.view else {}
        theme['pack_id'] = style.id
        theme['n64'] = n64_look(self.c, theme)
        theme['env_root'] = str(self.c.shipped('kits/library/' + style.kit_pack + '/env'))
        theme.setdefault('fog', {'color': '#808080', 'near': 10, 'far': 50})
        return theme

    def assets(self, style, refs):
        mapping = {}
        for ref in sorted(refs):
            row = style.kit_row(ref)
            path = self.c.shipped(row['glb'])
            if digest(path.read_bytes()) != row['sha256']:
                fail('asset_integrity', 'Hash differs for ' + ref)
            mapping[ref] = dict(row, path=str(path))
        return mapping

    def textures(self, style, presets):
        out = {}
        for preset in sorted(presets):
            rel, role = style.ground_texture(preset)
            path = self.c.shipped(rel)
            out[preset] = {'path': str(path), 'sha256': digest(path.read_bytes()), 'role': role, 'tile_m': TILE_M[preset]}
        return out

    def job(self, style, ctx, items, folder):
        """items: [(scene, out_rel_dir, [(output_name, passes)])] -> job dict (absolute paths inside the project)."""
        refs, presets, renders = {'terrain.vista'}, set(), []
        for scene, out_rel, outputs in items:
            refs.update(r['kit'] for r in scene['hero'] + scene['props'])
            presets.add(scene['ground']['preset'])
            self.project.path(out_rel).mkdir(parents=True, exist_ok=True)
            cast = {}
            for a in scene['cast']:
                row = ctx.cast[a['id']]
                cast[a['id']] = {'id': a['id'], 'body_id': row['body_id'], 'base_rig_id': row['base_rig_id'], 'params': row['params']}
            # in-engine grade at the top of the convention's ranges for the mood (punchy but still N64-legal);
            # the finishing pass adds the scene's own finish.contrast/saturation on top
            rng = cover_style.ranges(scene['mood'], self.root)
            grade = {'contrast': round(min(rng['grade.contrast'][1], 1.1), 3), 'saturation': round(rng['grade.saturation'][1], 3)}
            renders.append({'scene': scene, 'out_dir': str(self.project.path(out_rel)), 'cast': cast,
                            'remap': style.remap, 'grade': grade,
                            'outputs': [{'name': name, 'size': list(SIZES['card' if name.startswith('card') else name]),
                                         'passes': list(passes)} for name, passes in outputs]})
        return {'format': 'hermes64.cover_job/1', 'report': str(self.project.path(folder + '/report.json')),
                'theme': self.theme(style), 'assets': self.assets(style, refs), 'characters': admitted_characters(self.root),
                'textures': self.textures(style, presets), 'renders': renders}

    # -------------------------------------------------------------- run
    def run(self, job, folder, timeout=180):
        exe = locate('godot', self.settings.get('godot_path', ''))
        runtime = self.stage()
        self.project.write_json(folder + '/job.json', job)
        # frame budget: a script that fails to load never quits by itself; --quit-after bounds the window's life
        grabs = sum(1 + len(o['passes']) for r in job['renders'] for o in r['outputs'])
        argv = [exe, '--audio-driver', 'Dummy', '--quit-after', str(900 + 40 * grabs), '--path', str(self.project.path(runtime)),
                'res://cover/cover.tscn', '--', '--job=' + str(self.project.path(folder + '/job.json'))]
        process = self.c.runner.run(argv, self.project.root, timeout=timeout)
        self.project.write_json(folder + '/godot.process.json', dict(process, argv=argv))
        report_path = folder + '/report.json'
        if not self.project.path(report_path).is_file():
            fail('component_protocol', 'Cover renderer produced no report (exit %s): %s' % (
                process['returncode'], (process['stderr'][-1500:] + process['stdout'][-300:]).strip()))
        report = self.project.read_json(report_path)
        if not isinstance(report, dict) or report.get('format') != 'hermes64.cover_report/1':
            fail('component_protocol', 'Cover report has the wrong format')
        report['process'] = {'returncode': process['returncode'], 'elapsed_seconds': process['elapsed_seconds']}
        if report.get('status') != 'rendered':
            errs = list(report.get('errors') or [])
            for r in report.get('renders') or []:
                errs += r.get('errors') or []
            fail('render_failed', 'Cover render failed: ' + '; '.join(str(e) for e in errs[:6]) +
                 ((' | stderr: ' + process['stderr'][-800:]) if process['returncode'] else ''))
        return report


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(value):
    return encode(value)
