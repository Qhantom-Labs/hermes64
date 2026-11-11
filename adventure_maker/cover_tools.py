"""hermes64_cover: staged box-art covers for a managed Hermes64 project.

    propose  -> .maker/cover/scenes/<id>-{a,b,c}.json + previews (render passes, box previews, gate verdicts)
    edit     -> a new scene revision from typed edits (optional preview)
    render   -> final renders of one scene (card 980x680 + gate passes, banner 1280x640, square 1080x1080) + gate
    export   -> finished box art from a PASSED render; adopt=true (the user's explicit choice) records the project cover
    list     -> scenes, renders, exports, adopted cover

Confinement: every path is project-relative through safety.Project (no traversal, no symlinks, size limits) and every
identifier is a slug; the only child process is Godot through the sandboxed argv-only Runner (writes confined to the
project, network denied). Registration is separate (register_cover_tools) so the plugin merge is two entrypoint lines
and one manifest entry; see docs/COVER-INTEGRATION.md.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path

from . import cover_finish, cover_gate, cover_scene, cover_style, wire
from .cover_render import SIZES, CoverRenderer, GATE_PASSES
from .cover_schemas import COVER_SCHEMA, EXPORT_NAMES
from .packs import Packs
from .safety import Fault, OUTPUT_LIMIT, Project, encode, fail
from .schemas import validate

ROOT = Path(__file__).resolve().parents[1]
BASE = '.maker/cover'
ACTIONS = {
    'propose': (('action', 'project', 'seed', 'style_profile', 'title'), ('project',)),
    'edit': (('action', 'project', 'scene', 'edits', 'new_id', 'preview'), ('project', 'scene', 'edits')),
    'render': (('action', 'project', 'scene'), ('project', 'scene')),
    'export': (('action', 'project', 'scene', 'sizes', 'adopt'), ('project', 'scene')),
    'list': (('action', 'project'), ('project',)),
}
SLUG = re.compile(r'^[a-z][a-z0-9_-]{0,47}$')


def _scene_rel(sid):
    if not SLUG.fullmatch(sid or ''):
        fail('arguments', 'scene id must be a lowercase slug')
    return BASE + '/scenes/' + sid + '.json'


def write_scene(project, scene):
    project.write_bytes(_scene_rel(scene['id']), (json.dumps(scene, sort_keys=True, indent=1) + '\n').encode('ascii'))
    return _scene_rel(scene['id'])


class CoverService:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.root = Path(self.settings.get('bundle_root') or ROOT)

    # ---------------------------------------------------------------- entry
    def handle(self, args, **kwargs):
        try:
            validate(args, COVER_SCHEMA['parameters'])
            encode(args)
            allowed, required = ACTIONS[args['action']]
            if any(k not in allowed for k in args) or any(k not in args for k in required):
                fail('arguments', 'Missing required or inapplicable argument for action ' + args['action'])
            if not self.settings.get('projects_root'):
                fail('configuration', 'Choose an existing projects_root and scaffold the project first')
            project = Project(self.settings['projects_root'], args['project'])
            with project.lock():
                result = getattr(self, args['action'])(project, args)
            raw = encode(result)
            if len(raw) > OUTPUT_LIMIT:
                rel = BASE + '/reports/' + uuid.uuid4().hex + '.json'
                project.write_bytes(rel, raw)
                return json.dumps({'ok': result.get('ok', False), 'status': result.get('status'), 'truncated': True,
                                   'report_path': rel})
            return raw.decode('utf-8')
        except Fault as exc:
            return json.dumps({'ok': False, 'error': {'code': exc.code, 'message': str(exc)[:2000]}})
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            return json.dumps({'ok': False, 'error': {'code': 'local_error', 'message': type(exc).__name__ + ': ' + str(exc)[:1000]}})

    # ---------------------------------------------------------------- context
    def spec(self, project):
        if not project.path('source/spec.json').is_file():
            fail('project', 'No source/spec.json; scaffold the project first')
        return project.read_json('source/spec.json')

    def context(self, project, spec, style_id=None, source=None, kit_pack=None):
        if source == 'profile' or (style_id in cover_style.PROFILES and source != 'pack'):
            style = cover_style.from_profile(style_id, self.root, kit_pack)
        else:
            style = cover_style.resolve(spec, Packs(self.settings, project), self.root)
            if style_id and style.id != style_id:
                fail('cover_scene', 'Scene style %s does not match the project pack %s' % (style_id, style.id))
        bind = json.loads((self.root / 'bindings.json').read_text(encoding='utf-8')) if (self.root / 'bindings.json').is_file() else {}
        cast = cover_scene.cast_table(spec, bind, self.root)
        return cover_scene.CoverContext(style, cast, self.root)

    def scene_context(self, project, scene):
        st = scene.get('style') if isinstance(scene, dict) else None
        if not isinstance(st, dict):
            fail('cover_scene', 'Scene has no style block')
        return self.context(project, self.spec(project), st.get('id'), st.get('source'), st.get('kit_pack'))

    def load_scene(self, project, sid):
        rel = _scene_rel(sid)
        if not project.path(rel).is_file():
            fail('not_found', 'No cover scene %s; run propose or list' % sid)
        scene = project.read_json(rel)
        ctx = self.scene_context(project, scene)
        return cover_scene.validate(scene, ctx), ctx

    def renderer(self, project):
        return CoverRenderer(dict(self.settings, bundle_root=str(self.root)), project)

    def folder(self, project, kind):
        rel = BASE + '/runs/' + kind + '-' + uuid.uuid4().hex[:16]
        project.path(rel).mkdir(parents=True)
        return rel

    # ---------------------------------------------------------------- previews / gate
    def _render(self, project, ctx, items, kind):
        folder = self.folder(project, kind)
        rend = self.renderer(project)
        job = rend.job(ctx.style, ctx, items, folder)
        return rend.run(job, folder), folder

    def _gate_rows(self, project, ctx, report, out_name='card'):
        rows = {}
        for r in report['renders']:
            out = next(o for o in r['outputs'] if o['name'] == out_name)
            scene = None
            for cand in report.get('_scenes', []):
                if cand['id'] == r['id']:
                    scene = cand
            res = cover_gate.gate(out['files'], scene, ctx.style.palette)
            res['subject_screen'] = out.get('subject_screen')
            res['triangles'] = out.get('triangles')
            rows[r['id']] = res
        return rows

    def _rel(self, project, path):
        return str(Path(path).resolve().relative_to(project.root.resolve()))

    def preview(self, project, scenes, ctx):
        items = [(sc, BASE + '/previews/' + sc['id'], [('card', GATE_PASSES)]) for sc in scenes]
        report, folder = self._render(project, ctx, items, 'preview')
        report['_scenes'] = scenes
        gates = self._gate_rows(project, ctx, report)
        out = []
        for sc in scenes:
            pdir = project.path(BASE + '/previews/' + sc['id'])
            card = pdir / (sc['id'] + '-card.png')
            written, layout = cover_finish.finish_all({'card': str(card)}, sc, pdir, sc['id'] + '-preview', ctx.style.label)
            project.write_json(BASE + '/previews/' + sc['id'] + '/gate.json', dict(gates[sc['id']], scene_sha256=cover_scene.scene_hash(sc)))
            out.append({'scene': sc['id'], 'scene_path': _scene_rel(sc['id']),
                        'preview_box_2x': self._rel(project, written['box-2x']['path']),
                        'preview_box_1x': self._rel(project, written['box-1x']['path']),
                        'render': self._rel(project, card),
                        'gate': {'status': gates[sc['id']]['status'], 'reasons': gates[sc['id']]['reasons']},
                        'summary': describe(sc)})
        return out, report, folder

    # ---------------------------------------------------------------- actions
    def propose(self, project, args):
        spec = self.spec(project)
        ctx = self.context(project, spec, args.get('style_profile'), 'profile' if args.get('style_profile') else None)
        if args.get('title'):
            spec = dict(spec, title=args['title'])
        scenes = cover_scene.propose(spec, ctx, seed=args.get('seed', 7))
        for sc in scenes:
            write_scene(project, sc)
        rows, report, folder = self.preview(project, scenes, ctx)
        return {'ok': True, 'status': 'proposed_not_adopted', 'variants': rows, 'run': folder,
                'engine': report.get('engine'), 'renderer': report.get('renderer'), 'device': report.get('device'),
                'next': 'Show the three previews to the user and let them pick one (or edit). Then render the chosen scene, '
                        'then export; pass adopt=true only when the user explicitly adopts it.'}

    def edit(self, project, args):
        scene, ctx = self.load_scene(project, args['scene'])
        ops = []
        for op in args['edits']:
            op = dict(op)
            if 'target_point' in op:
                if op['op'] != 'camera':
                    fail('cover_edit', 'target_point applies to camera edits')
                op['target'] = op.pop('target_point')
            ops.append(op)
        new = cover_scene.apply_edits(scene, ops, ctx, final_id=args.get('new_id'))
        if project.path(_scene_rel(new['id'])).is_file():
            fail('exists', 'Scene %s already exists; choose new_id' % new['id'])
        write_scene(project, new)
        result = {'ok': True, 'status': 'edited_not_rendered', 'scene': new['id'], 'parent': scene['id'],
                  'scene_path': _scene_rel(new['id']), 'changes': changes(scene, new), 'summary': describe(new)}
        if args.get('preview'):
            rows, report, folder = self.preview(project, [new], ctx)
            result.update(status='edited_previewed', preview=rows[0], run=folder)
        return result

    def render(self, project, args):
        scene, ctx = self.load_scene(project, args['scene'])
        out_rel = BASE + '/renders/' + scene['id']
        items = [(scene, out_rel, [('card', GATE_PASSES), ('banner', []), ('square', [])])]
        report, folder = self._render(project, ctx, items, 'render')
        report['_scenes'] = [scene]
        gate = self._gate_rows(project, ctx, report)[scene['id']]
        files = {o['name']: o['files']['beauty'] for o in report['renders'][0]['outputs']}
        record = {'scene': scene['id'], 'scene_sha256': cover_scene.scene_hash(scene), 'gate': gate,
                  'renders': {k: {'path': self._rel(project, v), 'sha256': hashlib.sha256(Path(v).read_bytes()).hexdigest()}
                              for k, v in files.items()},
                  'engine': report.get('engine'), 'renderer': report.get('renderer'), 'device': report.get('device'),
                  'run': folder}
        project.write_json(out_rel + '/render.json', record)
        status = 'rendered_gate_passed' if gate['status'] == 'passed' else 'rejected_by_gate'
        return {'ok': True, 'status': status, 'scene': scene['id'], 'renders': record['renders'],
                'gate': {'status': gate['status'], 'reasons': gate['reasons']},
                'next': 'export (sizes) when passed; otherwise edit the scene to address the reasons and render again'}

    def export(self, project, args):
        scene, ctx = self.load_scene(project, args['scene'])
        rec_rel = BASE + '/renders/' + scene['id'] + '/render.json'
        if not project.path(rec_rel).is_file():
            fail('not_rendered', 'Render scene %s first' % scene['id'])
        record = project.read_json(rec_rel)
        if record.get('scene_sha256') != cover_scene.scene_hash(scene):
            fail('stale_render', 'The scene changed after its render; render it again')
        if record['gate']['status'] != 'passed':
            fail('gate_failed', 'The render failed the cover gate: ' + '; '.join(record['gate']['reasons'][:4]))
        renders = {}
        for name, row in record['renders'].items():
            p = project.path(row['path'])
            if hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
                fail('integrity', 'Render %s changed on disk; render again' % name)
            renders[name] = str(p)
        sizes = args.get('sizes') or EXPORT_NAMES
        wanted = {'card': any(s in sizes for s in ('box-1x', 'box-2x', 'card-alpha', 'studio-art')),
                  'banner': 'banner' in sizes, 'square': 'square' in sizes}
        out_rel = BASE + '/exports/' + scene['id']
        written, layout = cover_finish.finish_all({k: v for k, v in renders.items() if wanted.get(k)}, scene,
                                                  project.path(out_rel), scene['id'], ctx.style.label)
        written = {k: v for k, v in written.items() if k in sizes}
        manifest = {'scene': scene['id'], 'scene_sha256': record['scene_sha256'], 'title': scene['title']['text'],
                    'style': scene['style']['id'], 'exports': {k: dict(v, path=self._rel(project, v['path'])) for k, v in written.items()},
                    'layout': layout}
        project.write_json(out_rel + '/exports.json', manifest)
        result = {'ok': True, 'status': 'exported_not_adopted', 'scene': scene['id'], 'exports': manifest['exports']}
        if args.get('adopt'):
            if 'studio-art' not in written or 'box-2x' not in written:
                fail('arguments', 'adopt needs the studio-art and box-2x exports')
            new_manifest = None
            if project.path('project.json').is_file():
                # portable project: record the optional `cover` field (validated before anything is written)
                from . import project_cover
                block = project_cover.cover_block(BASE + '/scenes/' + scene['id'] + '.json', scene,
                                                  {k: v['path'] for k, v in manifest['exports'].items()},
                                                  scene['title']['placement'])
                try:
                    new_manifest = project_cover.with_cover(project.read_json('project.json'), block, project.root)
                except (project_cover.CoverFieldError, ValueError) as exc:
                    fail('cover_project', 'project.json cover field refused: %s' % exc)
            art = project.path(manifest['exports']['studio-art']['path'])   # project-relative (finish_all paths are absolute)
            project.write_bytes('.maker/studio/cover.png', art.read_bytes())
            if new_manifest is not None:
                project.write_bytes('project.json', project_cover.manifest_bytes(new_manifest))
                result['project_cover'] = 'project.json#cover'
            current = {'format': 'hermes64.cover_current/1', 'scene': scene['id'], 'scene_sha256': record['scene_sha256'],
                       'exports': manifest['exports'], 'studio_cover': '.maker/studio/cover.png',
                       'title_position': scene['title']['placement']}
            project.write_json(BASE + '/current.json', current)
            result.update(status='exported_and_adopted', studio_cover='.maker/studio/cover.png', current=BASE + '/current.json')
        return result

    def list(self, project, args):
        out = {'ok': True, 'status': 'listed', 'scenes': [], 'adopted': None}
        sdir = project.path(BASE + '/scenes')
        if sdir.is_dir():
            for p in sorted(sdir.glob('*.json'), key=lambda q: q.stem):
                sid = p.stem
                row = {'scene': sid, 'path': _scene_rel(sid)}
                try:
                    sc = project.read_json(_scene_rel(sid))
                    row.update(summary=describe(sc), parent=sc.get('parent'), revision=sc.get('revision'))
                except Fault as exc:
                    row['error'] = str(exc)[:200]
                for kind in ('previews', 'renders', 'exports'):
                    rel = BASE + '/' + kind + '/' + sid
                    if project.path(rel).is_dir():
                        row[kind] = rel
                g = BASE + '/renders/' + sid + '/render.json'
                if project.path(g).is_file():
                    row['render_gate'] = project.read_json(g)['gate']['status']
                out['scenes'].append(row)
        if project.path(BASE + '/current.json').is_file():
            out['adopted'] = project.read_json(BASE + '/current.json')
        return out


def describe(sc):
    cast = ', '.join('%s (%s)' % (a['id'], a['clip']) for a in sc['cast']) or 'no cast'
    hero = ', '.join(h['kit'] for h in sc['hero'])
    return '%s | %s %s | hero: %s | cast: %s | camera %gmm el %g az %g | title %s/%s' % (
        sc['id'], sc['mood'], sc['camera']['framing'], hero, cast, sc['camera']['focal_mm'], sc['camera']['elevation_deg'],
        sc['camera']['azimuth_deg'], sc['title']['placement'], sc['title']['letter'])


def changes(old, new):
    out = []

    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if k in ('id', 'revision', 'parent'):
                    continue
                walk(a.get(k), b.get(k), path + '.' + k if path else k)
        elif a != b:
            out.append({'path': path, 'from': a, 'to': b})
    walk(old, new, '')
    return out[:40]


def register_cover_tools(ctx):
    def handler(args, **kwargs):
        settings = {k: ctx.get_config(k, '') for k in ('projects_root', 'bundle_root', 'godot_path')}
        return CoverService(settings).handle(args, **kwargs)
    # Advertised copy is compact (wire.py, docs/TOKEN-DIET.md); handle() still validates the full COVER_SCHEMA.
    wire.register(ctx, 'hermes64_cover', COVER_SCHEMA, handler, lambda: True)
