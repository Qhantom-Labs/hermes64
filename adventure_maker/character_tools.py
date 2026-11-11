"""hermes64_character: recipe-driven house-style characters (lane CHARSYS).

Actions
  list     what=parts|bodies|styles|recipes|cast              read-only
  info     id=<part/body/style/recipe id>                      read-only
  propose  brief (+references, style) -> three recipes, built and gated, one contact sheet per variant
           (front / three-quarter / side + a game-scale room shot) under characters/proposals/<id>/; never adopted
  edit     recipe + typed edits -> a new validated recipe (clamps reported); render=true also rebuilds the sheet
  build    recipe -> characters/built/<id>.glb + clips + gates report + manifest entry + catalog.json row (hub shape)
  bind     id (built) or glb (cameo pack / community file) + display_name -> characters/cast.json, only after the
           rig kit validator passes (the same validator every generated character passes); people keep
           placeholder: true until Dylan names them
Writes only inside the managed project (adventure_maker.safety.Project); Blender runs through
adventure_maker.runner.Runner (macOS sandbox, no network, project-confined writes); no shell strings.
"""
import hashlib
import json
import re
from pathlib import Path

from .character_schemas import CHARACTER_SCHEMA
from .schemas import validate
from .safety import Fault, Project, encode, fail
from . import character_style as CS
from . import character_recipe as CR
from . import character_gate as GATE
from . import character_pipeline as PL
from . import character_propose as PR
from . import catalog as CAT
from . import wire

ACTIONS = {
    'list': (('action', 'what', 'project', 'style'), ('what',)),
    'info': (('action', 'id', 'project', 'style'), ('id',)),
    'propose': (('action', 'project', 'brief', 'references', 'style'), ('project', 'brief')),
    'edit': (('action', 'project', 'recipe', 'edits', 'style', 'render'), ('project', 'recipe', 'edits')),
    'build': (('action', 'project', 'recipe', 'style'), ('project', 'recipe')),
    'bind': (('action', 'project', 'id', 'glb', 'display_name', 'placeholder', 'source', 'legacy', 'waive', 'owner_approved',
              'brief'), ('project', 'display_name')),
    'locomotion': (('action', 'project', 'id', 'glb'), ('project',)),
}
# A project has one catalog.json (hermes64-catalog/1.0.0) with one write path, adventure_maker/catalog.py
# (read_project -> upsert -> write_project), shared with /hermes64 hub install. A loose community file has no known
# licence, so it stays internal until it arrives through the hub (whose install row, with its licence, is reused).
# The optional cameo binds only from its hub install (/hermes64 hub install character.cameo.<id>): its row, archive
# hash and notice come from the hub, so removing the pack never leaves a second copy behind.
ID_PREFIX = {'generated': 'character:project/', 'community': 'character:community/'}
SOURCE_LANE = {'generated': 'charsys', 'community': 'community'}
LICENCE = {'generated': 'MIT', 'community': 'NOASSERTION'}
VISIBILITY = {'generated': 'public', 'community': 'internal'}
CAMEO_NOTICE_FILE = 'LICENSE-CAMEO.md'


ROOT = Path(__file__).resolve().parents[1]


def builtin_cast(root=ROOT):
    """The plugin's own characters with display names from catalog/names.json (the one names file, hub lane);
    without it, the hub's fallback rule (id as title, placeholder) applies."""
    try:
        names = json.loads((Path(root) / 'catalog/names.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        names = {'people': {'new_arrival': {'name': 'Qhantom', 'placeholder': False}}, 'creatures': {}}   # the lead, until
        # catalog/names.json (the one editable names file) is present
    out = {}
    for row in json.loads((Path(root) / 'characters/manifest.json').read_text(encoding='utf-8'))['characters']:
        if row['id'] in out:
            continue
        if row['kind'] == 'animal':
            out[row['id']] = {'name': names.get('creatures', {}).get(row['id'], row['id'].replace('_', ' ').title())}
        else:
            ent = names.get('people', {}).get(row['id'])
            out[row['id']] = ({'name': ent['name'], 'placeholder': bool(ent.get('placeholder', True))} if isinstance(ent, dict)
                              else {'name': row['id'].replace('_', ' ').title(), 'placeholder': True})
    return out


def _tag(t):
    t = re.sub(r'[^a-z0-9_.-]+', '-', str(t).lower()).strip('-_.')[:40]
    return t if t and re.match(r'^[a-z0-9]', t) else None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CharacterService:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})

    # ------------------------------------------------------------------ entry
    def handle(self, args, **kwargs):
        try:
            validate(args, CHARACTER_SCHEMA['parameters'])
            encode(args)
            allowed, required = ACTIONS[args['action']]
            if any(k not in allowed for k in args) or any(k not in args for k in required):
                fail('arguments', 'Missing required or inapplicable argument for action ' + args['action'])
            if args['action'] in ('list', 'info') and 'project' not in args:
                return json.dumps(dict(self.dispatch(None, args), ok=True), allow_nan=False)
            if not self.settings.get('projects_root'):
                fail('configuration', 'Choose an existing projects_root and scaffold the project first')
            project = Project(self.settings['projects_root'], args['project'])
            with project.lock():
                result = self.dispatch(project, args)
            return json.dumps(dict(result, ok=result.get('ok', True)), allow_nan=False)
        except Fault as exc:
            return json.dumps({'ok': False, 'error': {'code': exc.code, 'message': str(exc)[:2000]}})
        except (CR.RecipeError, CS.CharacterStyleError) as exc:
            return json.dumps({'ok': False, 'error': {'code': exc.code, 'message': str(exc)[:2000]}})
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            return json.dumps({'ok': False, 'error': {'code': 'local_error', 'message': type(exc).__name__ + ': ' + str(exc)[:1000]}})

    def dispatch(self, project, args):
        return getattr(self, 'do_' + args['action'])(project, args)

    # ------------------------------------------------------------------ helpers
    def lock(self, project, args):
        name = args.get('style')
        if not name and project is not None and project.path('characters/style.json').is_file():
            name = project.read_json('characters/style.json').get('lock')
        return CS.load_lock(name or 'n64_base')

    def blender(self):
        from .runner import locate
        try:
            return locate('blender', self.settings.get('blender_path', ''))
        except Fault:
            return None

    def invoke(self, project):
        from .runner import Runner
        r = Runner(project)

        def run(argv, cwd, timeout):
            return r.run(argv, cwd, timeout=min(int(timeout), 180))
        return run

    def recipe_path(self, project, ref):
        if ref.endswith('.json'):
            return ref
        if '.' in ref and ref.split('.')[0]:
            pid, var = ref.rsplit('.', 1)
            return 'characters/proposals/%s/%s.json' % (pid, var)
        return 'characters/recipes/%s.json' % ref

    def read_recipe(self, project, ref):
        rel = self.recipe_path(project, ref)
        if not project.path(rel).is_file():
            fail('missing', 'No recipe at ' + rel)
        return rel, project.read_json(rel)

    def numpy_version(self, project, python):
        """numpy version of the build interpreter (one short sandboxed child), or None."""
        res = self.invoke(project)([python, '-B', '-c', 'import numpy; print(numpy.__version__)'], ROOT, 60)
        out = (res.get('stdout') or '').strip().splitlines()
        return out[-1] if res.get('returncode') == 0 and out else None

    def exporter(self, project):
        """-> (exporter, python, blender) from character_exporter (auto | python | blender; docs/NBCHARS-API.md 6):
        auto builds with the python exporter (no Blender) when the build interpreter has numpy and the committed
        parity verdict is PASS, else with Blender when configured. Blender, when present, also renders review images."""
        from .nbchars import select as SEL
        from .runner import locate
        blender = self.blender()
        want = self.settings.get('character_exporter') or 'auto'
        python, npv = None, None
        if want in ('auto', 'python'):
            try:
                python = locate('python', self.settings.get('python_path', ''))
            except Fault:
                python = None
            npv = self.numpy_version(project, python) if python else None
        choice = SEL.select_exporter({'character_exporter': want}, numpy=npv or False, blender=blender or False)
        if choice['exporter'] is None:
            fail('missing_tool', choice['reason'] + '. ' + PL.doctor(blender)['message'])
        return choice['exporter'], python, blender

    def _sheet(self, project, rel_dir, rid, renders):
        """Front / three-quarter / side over snow and dark halves + the room shot -> one PNG (nearest-neighbour x2)."""
        from PIL import Image
        views = [renders.get(v) for v in PL.VIEWS]
        tiles = []
        for p in views:
            im = Image.open(p).convert('RGBA')
            w, h = im.size
            bg = Image.new('RGBA', (w, h), tuple(int(c * 255) for c in GATE.SNOW) + (255,))
            dark = Image.new('RGBA', (w, h // 2), tuple(int(c * 255) for c in GATE.DARK) + (255,))
            bg.paste(dark, (0, h - h // 2))
            bg.alpha_composite(im)
            tiles.append(bg.convert('RGB'))
        room = Image.open(renders['room']).convert('RGB') if renders.get('room') else None
        th = tiles[0].size[1]
        if room is not None:
            room = room.resize((int(room.size[0] * th / room.size[1]), th), Image.NEAREST)
        width = sum(t.size[0] for t in tiles) + (room.size[0] if room is not None else 0)
        sheet = Image.new('RGB', (width, th), (0, 0, 0))
        x = 0
        for t in tiles + ([room] if room is not None else []):
            sheet.paste(t, (x, 0)); x += t.size[0]
        sheet = sheet.resize((sheet.size[0] * 2, sheet.size[1] * 2), Image.NEAREST)
        from io import BytesIO
        buf = BytesIO()
        sheet.save(buf, 'PNG', optimize=False)
        rel = '%s/%s_sheet.png' % (rel_dir, rid)
        project.write_bytes(rel, buf.getvalue())
        return rel

    def _run(self, project, recipes, lock, rel_dir, render=True):
        exporter, python, blender = self.exporter(project)
        out = project.path(rel_dir)
        res = PL.build(recipes, lock, out, invoke=self.invoke(project), blender=blender, render=render,
                       rigkit_root=self.settings.get('rigkit_root') or None, exporter=exporter, python=python)
        return res

    def _sheet_or_note(self, project, rel_dir, rid, it):
        """Contact sheet from the review renders, or (None, why) when this host has no renderer."""
        if len(it.get('renders') or []) < len(PL.VIEWS):
            return None, it['gates'].get('not_run', {}).get('silhouette', PL.NO_RENDERER)
        renders = {'front': it['renders'][0], 'three_quarter': it['renders'][1], 'side': it['renders'][2]}
        room = project.path('%s/renders/%s_room.png' % (rel_dir, rid))
        if room.is_file():
            renders['room'] = str(room)
        return self._sheet(project, rel_dir, rid, renders), None

    # ------------------------------------------------------------------ actions
    def do_list(self, project, args):
        what = args['what']
        lib = CR.load_parts()
        if what == 'parts':
            by = {}
            for pid, row in sorted(lib['parts'].items()):
                by.setdefault(row['kind'], []).append(pid)
            return {'parts': by, 'count': len(lib['parts'])}
        if what == 'bodies':
            return {'bodies': {k: {'archetype': v['archetype'], 'rig': '%s@%s' % (v['rig']['id'], v['rig']['version']),
                                   'tris': v['tris'], 'clip_sets': v['clip_sets']} for k, v in lib['bodies'].items()}}
        if what == 'styles':
            return {'styles': CS.list_locks()}
        if what == 'cast' and project is None:
            return {'builtin': builtin_cast()}
        if what == 'recipes':
            d = project.path('characters/recipes')
            return {'recipes': sorted(p.stem for p in d.glob('*.json')) if d.is_dir() else []}
        cast = project.read_json('characters/cast.json') if project.path('characters/cast.json').is_file() else {}
        out = {'cast': cast.get('cast', []), 'builtin': builtin_cast()}
        from .character_waiver import line, waived_rows
        if waived_rows(cast):           # WAIVER: every character bound with an owner waiver, named
            out['waived_characters'] = [line(i, r) for i, r in waived_rows(cast)]
        return out

    def do_info(self, project, args):
        lib = CR.load_parts()
        key = args['id']
        if key in lib['parts']:
            return {'part': key, **lib['parts'][key]}
        if key in lib['bodies']:
            return {'body': key, **lib['bodies'][key]}
        if key in CS.list_locks():
            lk = CS.load_lock(key)
            return {'style': key, 'kind': lk.kind, 'roles': lk.roles, 'proportions': lk.proportions, 'budgets': lk.budgets,
                    'receipt': lk.receipt()}
        if project is not None:
            rel, rec = self.read_recipe(project, key)
            item, rep = CR.compile_build(rec, self.lock(project, args))
            return {'recipe': rel, 'summary': CR.summary(rec), 'clamps': rep['clamps'], 'parts': rep['parts'], 'tris': rep['tris']}
        fail('missing', 'Unknown id ' + key)

    def do_propose(self, project, args):
        lock = self.lock(project, args)
        refs = [str(project.path(r)) for r in args.get('references', [])]
        recs = PR.propose(args['brief'], lock, refs)
        pid = 'p_' + hashlib.sha256((args['brief'] + '|' + lock.id + '|' + '|'.join(args.get('references', []))).encode()).hexdigest()[:10]
        rel_dir = 'characters/proposals/' + pid
        letters = 'abc'
        for rec, v in zip(recs, letters):
            project.write_json('%s/%s.json' % (rel_dir, v), rec)
        res = self._run(project, recs, lock, rel_dir)
        variants = []
        for rec, v in zip(recs, letters):
            it = res['items'].get(rec['id'])
            if it is None:
                variants.append({'variant': '%s.%s' % (pid, v), 'refused': res['refused'].get(rec['id'])})
                continue
            sheet, why = self._sheet_or_note(project, rel_dir, rec['id'], it)
            row = {'variant': '%s.%s' % (pid, v), 'summary': CR.summary(rec), 'notes': rec.get('notes'),
                   'gates_ok': it['ok'], 'errors': it['gates']['errors'][:4], 'clamps': it['recipe']['clamps'],
                   'sheet': sheet, 'recipe': '%s/%s.json' % (rel_dir, v)}
            if why:
                row['no_sheet'] = why
            variants.append(row)
        return {'proposal': pid, 'style': lock.id, 'variants': variants, 'exporter': res.get('exporter'),
                'next': ('show the sheets; the user picks one; then build recipe=<variant> (or edit it first)'
                         if res.get('review_renders') == 'blender' else
                         'no contact sheets on this host: describe each variant from its summary; the user picks one; '
                         'then build recipe=<variant> (or edit it first)')}

    def do_edit(self, project, args):
        lock = self.lock(project, args)
        rel, rec = self.read_recipe(project, args['recipe'])
        for e in args['edits']:
            rec = CR.apply_edit(rec, e)
        item, rep = CR.compile_build(rec, lock)
        new_rel = 'characters/recipes/%s.json' % rec['id']
        if project.path(new_rel).is_file():
            old = project.read_json(new_rel)
            project.write_json('characters/recipes/history/%s-%s.json' % (rec['id'], CR.recipe_digest(old)[:8]), old)
        project.write_json(new_rel, rec)
        out = {'recipe': new_rel, 'summary': CR.summary(rec), 'clamps': rep['clamps'], 'warnings': rep['warnings'],
               'edits_applied': len(args['edits'])}
        if args.get('render'):
            rel_dir = 'characters/previews/' + rec['id']
            res = self._run(project, [rec], lock, rel_dir)
            it = res['items'][rec['id']]
            sheet, why = self._sheet_or_note(project, rel_dir, rec['id'], it)
            out.update(sheet=sheet, gates_ok=it['ok'], errors=it['gates']['errors'][:4], exporter=res.get('exporter'))
            if why:
                out['no_sheet'] = why
        return out

    def do_build(self, project, args):
        lock = self.lock(project, args)
        rel, rec = self.read_recipe(project, args['recipe'])
        rel_dir = 'characters/built/' + rec['id']
        res = self._run(project, [rec], lock, rel_dir)
        if rec['id'] in res['refused']:
            return {'ok': False, 'refused': res['refused'][rec['id']]}
        it = res['items'][rec['id']]
        if not it['ok']:
            return {'ok': False, 'id': rec['id'], 'errors': it['gates']['errors'][:12], 'report': rel_dir + '/gates.json'}
        project.write_json('characters/recipes/%s.json' % rec['id'], rec)
        glb_rel = '%s/%s.glb' % (rel_dir, rec['id'])
        rep = it['recipe']
        not_run = it['gates'].get('not_run', {})
        entry = {'id': rec['id'], 'glb': glb_rel, 'sha256': it['sha256'], 'bytes': it['bytes'], 'rig': rec['rig'],
                 'body': rec['body'], 'archetype': rec['archetype'], 'role': rec['role'], 'clips': it['clips'],
                 'tris': rep['tris'], 'height_m': it['height_m'], 'style_lock': rep['lock'], 'recipe_sha256': rep['recipe_sha256'],
                 'gates': 'passed' if not not_run else 'passed (not run: %s)' % ', '.join(sorted(not_run)),
                 'hover': rep['hover'], 'exporter': it.get('exporter', 'blender')}
        loco = self._locomotion(project, rec['id'], glb_rel, rec['rig']['id'], 'hover' if entry['hover'] else 'grounded')
        if loco.get('ok'):
            entry['locomotion'] = loco['entry']
        man = project.read_json('characters/manifest.json') if project.path('characters/manifest.json').is_file() else {
            'schema': 'hermes64-project-characters/1', 'characters': []}
        man['characters'] = [c for c in man['characters'] if c['id'] != rec['id']] + [entry]
        man['characters'].sort(key=lambda c: c['id'])
        project.write_json('characters/manifest.json', man)
        thumb = '%s/renders/%s_front.png' % (rel_dir, rec['id'])
        aid = self._catalog(project, rec['id'], rec['name']['display'], rec['name']['placeholder'], entry, 'generated',
                            thumb if project.path(thumb).is_file() else None, style=lock.id)
        out = {'id': rec['id'], 'glb': glb_rel, 'sha256': it['sha256'], 'clips': it['clips'], 'gates': entry['gates'],
               'exporter': entry['exporter'], 'rig': '%s@%s' % (rec['rig']['id'], rec['rig']['version']),
               'manifest': 'characters/manifest.json', 'catalog': 'catalog.json', 'catalog_id': aid,
               'next': 'bind id=%s display_name=... to add it to the project cast' % rec['id']}
        if not_run:
            out['not_run'] = not_run
        out['locomotion'] = loco['summary']
        return out

    # ------------------------------------------------------------------ base locomotion (docs/LOCOMOTION.md)
    @staticmethod
    def _loco():
        """The locomotion base needs numpy (as the rig kit does); the plugin itself must load without it."""
        try:
            from . import locomotion
        except ImportError as e:
            fail('missing', 'Base locomotion needs numpy in this Python (%s)' % e)
        return locomotion

    def _locomotion(self, project, cid, glb_rel, rig, profile='grounded'):
        """Bake run + walk for one project file into characters/locomotion/<id>.glb (the source file is not changed).
        A body the base refuses keeps its own clips; the reason is returned in plain words."""
        if profile != 'grounded' or not rig.startswith('human16'):
            return {'ok': False, 'summary': {'baked': False, 'why': 'base locomotion is for walking human16 bodies (this one: %s, %s)' % (rig, profile)}}
        try:
            LOCO = self._loco()
        except Exception as e:                                # no numpy: the build still succeeds, with its own clips
            return {'ok': False, 'summary': {'baked': False, 'why': str(e)[:300]}}
        res = LOCO.attach(project.path(glb_rel).read_bytes(), rig=rig)
        if not res['ok']:
            return {'ok': False, 'summary': {'baked': False, 'code': res['refused']['code'], 'why': res['refused']['message'][:600],
                                             'kept': 'the clips the file already has'}}
        rel = 'characters/locomotion/%s.glb' % cid
        project.path(rel).parent.mkdir(parents=True, exist_ok=True)
        project.path(rel).write_bytes(res['glb'])
        rep = res['report']
        project.write_json('characters/locomotion/%s.json' % cid, dict(rep, rig_contract=res['rig_contract']))
        blk = rep['block']
        entry = {'format': blk['format'], 'base': blk['base'], 'glb': rel, 'sha256': rep['sha256'], 'bytes': rep['bytes'],
                 'clips': rep['clips_in_file'], 'source_sha256': blk['source_sha256']}
        summary = {'baked': True, 'glb': rel, 'report': 'characters/locomotion/%s.json' % cid, 'sha256': rep['sha256'],
                   'walk_stride_mps': blk['walk']['stride_mps'], 'run_stride_mps': blk['run']['stride_mps'],
                   'run_enter_mps': blk['run']['enter_mps'], 'run_exit_mps': blk['run']['exit_mps'],
                   'changed_to_fit': {c: rep['clips'][c]['dials_moved'] for c in LOCO.CLIPS if rep['clips'][c].get('dials_moved')}}
        return {'ok': True, 'entry': entry, 'summary': summary}

    def do_locomotion(self, project, args):
        if ('id' in args) == ('glb' in args):
            fail('arguments', 'locomotion needs id (a character built here) or glb (a character file in the project), not both')
        man = None
        if 'id' in args:
            man = project.read_json('characters/manifest.json') if project.path('characters/manifest.json').is_file() else {'characters': []}
            entry = next((c for c in man['characters'] if c['id'] == args['id']), None)
            if entry is None:
                fail('missing', 'Build %s first (no manifest entry)' % args['id'])
            cid, glb_rel, rig, profile = entry['id'], entry['glb'], entry['rig']['id'], 'hover' if entry.get('hover') else 'grounded'
        else:
            glb_rel, cid = args['glb'], Path(args['glb']).stem
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', cid):
                fail('arguments', 'the file name must be a lowercase slug')
            if not project.path(glb_rel).is_file():
                fail('missing', 'No GLB at ' + glb_rel)
            if glb_rel.startswith('characters/locomotion/'):
                fail('arguments', 'that file is already a baked copy; bake from the original file')
            doc, _ = GATE.GLB.read(project.path(glb_rel).read_bytes())
            rig = next((s.get('name', '')[4:] for s in doc.get('skins', []) if s.get('name', '').startswith('rig_')), 'human16_v1')
            profile = 'grounded'
        loco = self._locomotion(project, cid, glb_rel, rig, profile)
        if not loco['ok']:
            return {'ok': False, 'id': cid, 'refused': loco['summary']}
        if man is not None:
            entry['locomotion'] = loco['entry']
            project.write_json('characters/manifest.json', man)
        return dict(loco['summary'], id=cid, source=glb_rel,
                    next=('bind id=%s display_name=... (legacy=true binds the clips it had before)' % cid) if man is not None
                    else 'bind glb=%s source=... display_name=...' % loco['summary']['glb'])

    def read_catalog(self, project):
        return CAT.read_project(project)

    def _catalog(self, project, cid, name, placeholder, entry, source, thumb, style='any', waiver=None):
        """Add or replace this character's row in the project catalog (hub asset shape); returns the row id.
        waiver: the cast row's owner waiver record (lane WAIVER): tag owner-waiver, and the provenance says so."""
        cat = self.read_catalog(project)
        kind = 'creature' if entry.get('archetype') == 'creature' else 'person'
        tris = entry.get('tris')
        body_tris = tris.get('body') if isinstance(tris, dict) else tris
        total = sum(v for v in tris.values() if isinstance(v, int)) if isinstance(tris, dict) else tris
        rig = entry['rig']
        tags = []
        for t in ('rig-' + rig['id'], entry.get('archetype'), entry.get('role'), (entry.get('body') or '').split('.')[-1],
                  'owner-waiver' if waiver else None):
            t = _tag(t) if t else None
            if t and t not in tags:
                tags.append(t)
        f = {'path': entry['glb'], 'sha256': entry['sha256'], 'bytes': int(entry['bytes'])}
        if isinstance(total, int):
            f['tris'] = total
        budgets = {'bytes': int(entry['bytes'])}
        if isinstance(total, int):
            budgets['tris'] = total
        if isinstance(body_tris, int):
            budgets['tris_body'] = body_tris
        hashes = {'glb': entry['sha256']}
        if entry.get('recipe_sha256'):
            hashes['recipe'] = entry['recipe_sha256']
        prov = {'generated': 'hermes64_character recipe %s (rig %s %s, style lock %s); every gate passed incl. the rig kit '
                             'validator.' % (cid, rig['id'], rig['version'], style),
                'community': 'Community character bound with hermes64_character; rig kit validator passed (rig %s %s); '
                             'licence not asserted.' % (rig['id'], rig['version'])}[source]
        if waiver:
            prov = prov.replace('validator passed', 'validator passed with an owner waiver of %s (%s, %s)' % (
                ', '.join(waiver['scope']['checks']), waiver['owner'], waiver['approved_on']), 1)
        row = {'id': ID_PREFIX[source] + cid, 'name': name[:80], 'kind': kind, 'source_lane': SOURCE_LANE[source],
               'source': {'generated': 'characters/manifest.json'}.get(source, entry['glb'])[:200],
               'files': [f], 'hashes': hashes, 'budgets': budgets, 'tags': tags[:24], 'licence': LICENCE[source],
               'provenance': prov[:300], 'preview': thumb if thumb and re.fullmatch(r'[a-z0-9_./-]+\.png', thumb) else None,
               'visibility': VISIBILITY[source], 'used_by': [], 'style': style[:64], 'status': 'available'}
        if kind == 'person':
            row['placeholder'] = bool(placeholder)
        CAT.write_project(project, CAT.upsert(cat, row))
        return row['id']

    def _cameo_pack(self, project, glb_rel, raw):
        """The optional cameo binds only as the hub installed it: an installed catalog row tagged cameo
        (public-with-notice) lists this exact file and hash, and the install folder keeps LICENSE-CAMEO.md."""
        how = ('install it first: /hermes64 hub install character.cameo.<id> %s, then bind '
               'glb=assets/hub/character.cameo.<id>/models/<file>.glb' % project.root.name)
        row = next((a for a in self.read_catalog(project)['assets'] if a.get('status') == 'installed'
                    and 'cameo' in a.get('tags', []) and any(f['path'] == glb_rel for f in a['files'])), None)
        if row is None:
            fail('cameo_pack', 'A cameo binds only from its hub install; ' + how)
        if row['visibility'] != 'public-with-notice' or not row.get('notice'):
            fail('cameo_pack', 'The installed cameo row lost its notice; reinstall the cameo from the hub unchanged')
        if next(f['sha256'] for f in row['files'] if f['path'] == glb_rel) != _sha(raw):
            fail('cameo_pack', 'The cameo model differs from its hub install (sha256); reinstall it unchanged')
        notice = 'assets/hub/%s/%s' % (row['hub'], CAMEO_NOTICE_FILE)
        if not project.path(notice).is_file():
            fail('cameo_pack', 'The cameo install must keep its notice ' + notice)
        return row, notice

    def do_bind(self, project, args):
        source = args.get('source', 'generated')
        from . import character_waiver as WV
        refusal = WV.check_args(args)          # WAIVER: waive=true needs owner_approved=<name> + brief=<owner's words>
        if refusal:
            return {'ok': False, 'reason': 'Refused: ' + refusal}
        if 'id' in args and 'glb' not in args:
            if source != 'generated':
                fail('arguments', 'id binds a character built here; a %s character binds with glb=...' % source)
            man = project.read_json('characters/manifest.json') if project.path('characters/manifest.json').is_file() else {'characters': []}
            entry = next((c for c in man['characters'] if c['id'] == args['id']), None)
            if entry is None:
                fail('missing', 'Build %s first (no manifest entry)' % args['id'])
            glb_rel, cid = entry['glb'], entry['id']
            rig, clips, profile = entry['rig']['id'], entry['clips'], 'hover' if entry.get('hover') else 'grounded'
            if entry.get('locomotion') and not args.get('legacy'):
                glb_rel = entry['locomotion']['glb']      # baked run + walk (docs/LOCOMOTION.md); legacy=true binds the build's own clips
        elif 'glb' in args:
            if source == 'generated':
                fail('arguments', 'a file binds with source=cameo_pack or source=community')
            glb_rel = args['glb']
            cid = args.get('id') or Path(glb_rel).stem
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', cid):
                fail('arguments', 'id must be a lowercase slug (or pass id=...)')
            rig, clips, profile = 'auto', None, 'grounded'
            entry = None
        else:
            fail('arguments', 'bind needs id (a built character) or glb (a cameo pack / community file)')
            return {}
        path = project.path(glb_rel)
        if not path.is_file():
            fail('missing', 'No GLB at ' + glb_rel)
        raw = path.read_bytes()
        hub_row, notice = None, None
        if source == 'cameo_pack':
            hub_row, notice = self._cameo_pack(project, glb_rel, raw)
        if rig == 'auto':
            doc, _ = GATE.GLB.read(raw)
            skins = [s.get('name', '') for s in doc.get('skins', [])]
            rig = next((s[4:] for s in skins if s.startswith('rig_')), 'human16_v1')
            # CHARBIND: a file is held to every clip it carries (plus idle), like a built character; the clips a game
            # role needs are checked when the runtime is staged (adventure_maker/cast_binding.py).
            clips = sorted({a.get('name') for a in doc.get('animations', []) if a.get('name')} | {'idle'})
        from .cast_binding import plain_reason
        cast = project.read_json('characters/cast.json') if project.path('characters/cast.json').is_file() else {
            'schema': 'hermes64-project-cast/1', 'note': 'Project-owned character bindings (hermes64_character bind).', 'cast': []}
        prior = next((c for c in cast['cast'] if c['id'] == cid), None)
        # WAIVER (docs/WAIVER.md): waive=true writes characters/waived/<id>.glb with the owner's waiver block; a file
        # that already carries a block is granted only when this project's cast row recorded exactly that block.
        wblock, wv, source_glb, source_sha = None, None, glb_rel, _sha(raw)
        if args.get('waive'):
            pre = GATE.glb_gate(path)['errors'] + GATE.cuboid_gate(path)['errors']
            if pre:
                return {'ok': False, 'id': cid, 'reason': plain_reason(pre, rig), 'errors': pre[:12], 'rig': rig}
            _gids, player = WV.roles(project, cid, {c['id']: c for c in cast['cast']})
            try:
                raw, wblock, wv = WV.grant(raw, rig, clips, profile, args['owner_approved'], args['brief'], player)
            except WV.Refusal as exc:
                return {'ok': False, 'id': cid, 'reason': 'Refused: ' + str(exc), 'errors': exc.errors[:12], 'rig': rig}
            glb_rel = '%s/%s.glb' % (WV.WAIVED_DIR, cid)
            project.write_bytes(glb_rel, raw)
            path = project.path(glb_rel)
        granted = wblock is not None or (prior is not None and prior.get('glb') == glb_rel and WV.granted(prior, raw))
        foreign = not granted and WV.W.block_of(raw) is not None
        rg = GATE.rig_gate(path, rig, clips=clips, profile=profile, rigkit_root=self.settings.get('rigkit_root') or None,
                           waiver=granted)
        gb = GATE.glb_gate(path)
        cb = GATE.cuboid_gate(path)
        block = self._loco().block_of(raw) if b'hermes64_locomotion' in raw else None
        rig_errors, waived = self._loco().waive_flight(rg['errors'], block) if block else (rg['errors'], [])
        errors = rig_errors + gb['errors'] + cb['errors']
        if errors:
            reason = plain_reason(errors, rig)
            if foreign:
                reason += ('. The file carries an owner waiver that this project did not grant; a waiver is granted only '
                           'through bind waive=true owner_approved=<name> brief=<their words>')
            return {'ok': False, 'id': cid, 'reason': reason, 'errors': errors[:12], 'rig': rig}
        if source == 'community':
            hub_row = next((a for a in self.read_catalog(project)['assets']
                            if a.get('status') == 'installed' and any(f['path'] == glb_rel for f in a['files'])), None)
        version = rg.get('rig', rig + '@1.0.0').split('@')[-1]
        row = {'id': cid, 'display_name': args['display_name'], 'placeholder': bool(args.get('placeholder', True)),
               'glb': glb_rel, 'sha256': _sha(raw), 'rig': {'id': rig, 'version': version},
               'clips': rg.get('checks', {}).get('clips', {}).get('checked') or clips, 'source': source,
               'visibility': hub_row['visibility'] if hub_row else VISIBILITY[source], 'validated': 'rig kit validate_character passed'}
        if notice:
            row['notice'] = notice
        if block:
            row['locomotion'] = {'format': block['format'], 'base': block['base'], 'run_flight_keys_off_the_floor': len(waived)}
        rec = None
        if granted:
            rec = WV.record(wblock, source_glb, source_sha, wv['waived']) if wblock is not None else prior['waiver']
            row['waiver'] = rec
            row['validated'] = 'rig kit validate_character passed with an owner waiver (WAIVED: %s)' % ', '.join(rec['scope']['checks'])
        if hub_row is None:
            if entry is None:
                entry = {'tris': rg.get('metrics', {}).get('body_tris'), 'archetype': 'person'}
            entry = dict(entry, glb=glb_rel, sha256=row['sha256'], bytes=len(raw), rig=row['rig'])
            row['catalog_id'] = self._catalog(project, cid, args['display_name'], row['placeholder'], entry, source, None,
                                              style=(entry.get('style_lock') or {}).get('lock', 'any')
                                              if isinstance(entry.get('style_lock'), dict) else entry.get('style_lock', 'any'),
                                              waiver=rec)
        else:
            row['catalog_id'] = hub_row['id']
        cast['cast'] = sorted([c for c in cast['cast'] if c['id'] != cid] + [row], key=lambda c: c['id'])
        project.write_json('characters/cast.json', cast)
        used = []
        if project.path('.maker/current.json').is_file():      # CHARBIND: which ids of the current game use it
            from .cast_binding import uses
            cur = project.read_json('.maker/current.json')
            if cur.get('game') and project.path(cur['game']).is_file():
                used = uses(project.read_json(cur['game']), {c['id']: c for c in cast['cast']}).get(cid, [])
        out = {'id': cid, 'cast': 'characters/cast.json', 'rig': '%s@%s' % (rig, version), 'visibility': row['visibility'],
               'catalog_id': row['catalog_id'], 'used_by': used,
               'next': ('rebuild the runtime (hermes64_playtest or hermes64_open) to see it'
                        if used else 'no game id uses %s yet: bind with id=<character, robot, boss or scene actor id> or '
                                     'name it in a premise binding' % cid)}
        if rec is not None:          # WAIVER: the waived failures with their numbers, never hidden
            out.update(glb=glb_rel, waiver=WV.line(cid, rec), waived=rg.get('waived_lines', []) + [
                l for l in rec.get('waived', []) if 'fight clip' in l])
        every = WV.waived_rows(cast)
        if every:
            out['waived_characters'] = [WV.line(i, r) for i, r in every]
        return out


def register_character_tools(ctx):
    def handler(args, **kwargs):
        settings = {k: ctx.get_config(k, '') for k in ('projects_root', 'blender_path', 'python_path', 'character_exporter',
                                                       'rigkit_root')}
        return CharacterService(settings).handle(args, **kwargs)
    # Advertised copy is compact (wire.py, docs/TOKEN-DIET.md); handle() still validates the full CHARACTER_SCHEMA.
    wire.register(ctx, 'hermes64_character', CHARACTER_SCHEMA, handler, lambda: True)
