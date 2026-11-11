"""Tool orchestration; state is owned by game projects, never Hermes config."""
import hashlib
import json
from pathlib import Path
import uuid
from .adapters import Components
from .patching import apply_patch, diff
from .safety import Fault, JSON_LIMIT, OUTPUT_LIMIT, Project, encode, fail, inspect_path, relative, strict_json
from .schemas import SCHEMAS, OPERATION, validate
from .templates import premise_spec
from .packs import Packs, validate_pack, fingerprint


def source_guard(spec):
    if not isinstance(spec, dict) or spec.get('contract_version') not in ('1.0.0', '1.1.0', '1.2.0'):
        fail('spec', 'Expected a story JSON object, contract 1.0.0, 1.1.0 or 1.2.0')
    encode(spec)
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'asset' and isinstance(child, str):
                    relative(child)
                if key == 'kit_refs' and isinstance(child, list):
                    for ref in child:
                        relative(ref)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(spec)
    return spec


def proof_accepted(report, spec):
    """'proved', or 'conditional' under the game's own declared module policy (the hermes64_module_edit rule,
    story/modules/edits.accepted). Older games have no gameplay policy, so they still need 'proved'."""
    policy = (spec.get('gameplay') or {}).get('verification_policy') if isinstance(spec, dict) else None
    return report.get('status') == 'proved' or (report.get('status') == 'conditional' and policy == 'conditional')


def proof_reason(report, spec):
    """One plain line: the checker status and its first failing rule."""
    bad = [o for o in report.get('obligations', []) if o.get('status') == 'rejected']
    if bad:
        return 'status %s; %s: %s' % (report.get('status'), bad[0].get('id'), ' '.join(str(bad[0].get('explanation', '')).split())[:240])
    if report.get('status') == 'conditional':
        return 'status conditional, but the game does not declare verification_policy conditional'
    for key in ('softlock_count', 'dead_end_count', 'ambiguous_terminal_count'):
        if report.get(key):
            return 'status %s; %s %s' % (report.get('status'), key.replace('_', ' '), report[key])
    return 'status %s' % report.get('status')


def regression(old_spec, new_spec, old, new, proof, operation):
    old_rooms = {r['id']: r for r in old['rooms']}
    new_rooms = {r['id']: r for r in new['rooms']}
    hashes = {}
    changed, unchanged = [], []
    for rid in sorted(set(old_rooms) | set(new_rooms)):
        a, b = old_rooms.get(rid), new_rooms.get(rid)
        same = a is not None and b is not None and a['build_hash'] == b['build_hash']
        identical = a is not None and b is not None and encode(a) == encode(b)
        (unchanged if same else changed).append(rid)
        hashes[rid] = {'before': a['build_hash'] if a else None, 'after': b['build_hash'] if b else None, 'byte_identical': identical}
    identity = old_spec['id'] == new_spec['id'] and old_spec['contract_version'] == new_spec['contract_version']
    losses = []
    for collection in ('rooms', 'characters', 'items', 'flags', 'dialogues', 'interactions', 'endings', 'collectibles', 'collectible_groups'):
        before = {x['id']: x for x in old_spec.get(collection, [])}
        after = {x['id']: x for x in new_spec.get(collection, [])}
        losses.extend(collection + ':' + x for x in before if x not in after)
        if collection == 'characters':
            identity = identity and all(x in after and before[x]['body_id'] == after[x]['body_id'] and
                                        before[x]['base_rig_id'] == after[x]['base_rig_id'] for x in before)
    identity = identity and not losses
    expected = operation.get('expected_changed_rooms')
    locality = 'not_run' if expected is None else ('passed' if set(changed) == set(expected) else 'failed')
    return {'solvability': proof, 'identity_preserved': bool(identity), 'lost_ids': losses,
            'changed_rooms': changed, 'unchanged_rooms': unchanged, 'room_hashes': hashes,
            'unchanged_byte_identical': all(hashes[r]['byte_identical'] for r in unchanged),
            'expected_room_locality': locality, 'save_migration': {'status': 'not_run', 'reason': 'No pre-edit save supplied'},
            'style_validation': {'status': 'not_run', 'reason': 'Run build_assets on this revision'}}


class Service:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})

    def response(self, value, project):
        raw = encode(value)  # validate canonical file JSON; files/hashes remain UTF-8, unchanged
        wire = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(wire) <= OUTPUT_LIMIT:
            return wire
        report = None
        if project is not None:
            report = '.maker/reports/' + uuid.uuid4().hex + '.json'
            project.write_bytes(report, raw)
        return json.dumps({'ok': value.get('ok', False), 'status': value.get('status', 'report'),
                           'truncated': True, 'report_path': report,
                           'message': 'Response exceeds 24000 bytes; full report saved inside project.' if report else 'Large read-only response omitted; narrow the request.'}, separators=(',', ':'))

    def project(self, name, create=False):
        root = self.settings.get('projects_root')
        if not root:
            fail('configuration', 'Choose an absolute projects_root in adventure-maker settings before writing games. Nothing installed or configured automatically.')
        return Project(root, name, create=create)

    def folder(self, project, kind):
        rel = '.maker/runs/' + kind + '-' + uuid.uuid4().hex
        project.path(rel).mkdir(parents=True)
        return rel

    def current(self, project):
        if not project.path('.maker/current.json').is_file():
            fail('no_build', 'No current build; compile a source spec first')
        value = project.read_json('.maker/current.json')
        if not isinstance(value, dict) or set(value) != {'spec', 'game'}:
            fail('project', 'Invalid current revision pointer')
        for path in value.values():
            project.read_json(path)
        return value

    def handle(self, name, args, **kwargs):
        project = None
        try:
            if name not in SCHEMAS:
                fail('arguments', 'Unknown adventure tool')
            validate(args, SCHEMAS[name]['parameters'])
            encode(args)
            action = name[len('hermes64_'):]
            if action == 'kits':
                return self.response(self.kits(args), None)
            if action == 'packs':
                project = self.project(args['project']) if 'project' in args else None
                packs = Packs(self.settings, project)
                if args['action'] == 'inspect':
                    if 'id' not in args:
                        fail('arguments', 'inspect requires id')
                    result = {'ok': True, 'pack': packs.get(args['id'])}
                else:
                    if 'id' in args:
                        fail('arguments', 'list does not accept id')
                    result = {'ok': True, 'packs': packs.list()}
                return self.response(result, None)
            if action == 'scaffold':
                return self.scaffold(args)
            if action == 'doctor':
                return self.response(self.doctor_anywhere(args), None)
            project = self.project(args['project'])
            with project.lock():
                result = getattr(self, action)(project, args)
                return self.response(result, project)
        except Fault as exc:
            out = {'ok': False, 'error': {'code': exc.code, 'message': str(exc)[:2000]}}
            if getattr(exc, 'next', None):  # auto-repair plan for a failed compile (adventure_maker/repair.py)
                out.update(next=exc.next, repair=exc.repair)
            out.update(getattr(exc, 'created', None) or {})   # REUSE: a scaffold says whether it made a folder
            return json.dumps(out, ensure_ascii=True)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            return json.dumps(dict({'ok': False, 'error': {'code': 'local_error', 'message': type(exc).__name__ + ': ' + str(exc)[:2000]}},
                                   **(getattr(exc, 'created', None) or {})), ensure_ascii=True)
        except Exception as exc:
            # Public Hermes handler contract: JSON on every ordinary error; never fabricate success.
            return json.dumps({'ok': False, 'error': {'code': 'internal_error', 'message': type(exc).__name__ + ': ' + str(exc)[:1000]}})

    def scaffold(self, args):
        """hermes64_scaffold: a new source project under exactly the given name. REUSE: an existing name is refused
        with one plain line naming what is there and how to continue it (never reused, never written into); every
        reply states created, project_dir, seconds and assets_built (scaffold never builds assets)."""
        import time
        started = time.monotonic()
        made = None
        try:
            # Validate all caller data before creating a new directory.
            if ('premise' in args) == ('spec_json' in args):
                fail('arguments', 'Supply exactly one of premise or spec_json')
            pack = Packs(self.settings).get(args['pack'])
            spec = source_guard(strict_json(args['spec_json']) if 'spec_json' in args else premise_spec(args['premise'], args['project'], pack))
            if not isinstance(spec.get('metadata'), dict):
                fail('spec', 'Spec metadata must be an object')
            try:
                project = self.project(args['project'], create=True)
            except Fault as exc:
                if exc.code != 'exists':
                    raise
                from .newgame import continue_line, describe_existing, existing_line
                info = describe_existing(self.settings['projects_root'], args['project'])
                refused = Fault('exists', 'Nothing was created: %s already exists at %s; %s, or scaffold under a new '
                                'project name.' % (args['project'], existing_line(info), continue_line(info)))
                setattr(refused, 'created', {'created': False, 'project_dir': info['project_dir'], 'existing': info,
                                             'assets_built': False, 'seconds': round(time.monotonic() - started, 3)})
                raise refused from None
            made = str(project.root)
            with project.lock():
                spec['metadata']['hermes64_pack'] = Packs(self.settings, project).snapshot(pack)
                project.write_json('source/spec.json', spec)
                project.write_bytes('AUTHORING.md', b'Author source with Hermes64 tools. Compile and check after every edit. Never hand-edit generated revisions. This is a starter, not a finished demo.\n')
        except Exception as exc:
            if getattr(exc, 'created', None) is None:
                setattr(exc, 'created', {'created': made is not None, 'project_dir': made, 'assets_built': False,
                                         'seconds': round(time.monotonic() - started, 3)})
            raise
        return self.response({'ok': True, 'status': 'scaffolded_unvalidated', 'created': True, 'project_dir': str(project.root),
                              'assets_built': False, 'seconds': round(time.monotonic() - started, 3),
                              'spec_path': 'source/spec.json', 'next': 'hermes64_compile then hermes64_check'}, project)

    def doctor_anywhere(self, args):
        """The doctor is a new user's first step, so it must work before any projects_root or game exists.
        An existing game is probed under its own lock as before; otherwise the sandboxed Python probe runs in a
        throwaway folder that is removed afterwards. Nothing under projects_root is created."""
        project = None
        if args.get('project'):
            try:
                project = self.project(args['project'])
            except Fault as exc:
                if exc.code not in ('configuration', 'project'):
                    raise
        if project is not None:
            with project.lock():
                return self.doctor(project, args)
        import shutil
        import tempfile
        scratch = Path(tempfile.mkdtemp(prefix='hermes64-doctor-')).resolve()
        try:
            result = self.doctor(Project(str(scratch), 'doctor', create=True), args)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        result['note'] = 'No game needed: the Python probe ran in a temporary folder that was then removed.'
        return result

    def doctor(self, project, args):
        from .doctor import check
        report = check(Components(self.settings, project))
        if not report['features']['build_static_kits']['available'] and report['python'].get('supported'):
            # Without numpy the Blender note's "set builder to python or auto" cannot work; say what does.
            report['guidance'] = list(report['guidance']) + [
                'numpy is missing from the Python Hermes64 uses (%s). Room asset builds without Blender, new character '
                'bodies and reference packs need it. Set python_path in the hermes64 plugin settings to a Python 3.9+ '
                'that has numpy (check with: <that python> -c "import numpy"). Hermes64 never installs packages.'
                % (report['programs'].get('python', {}).get('path') or 'python3')]
        table = 'Feature | Available | Needs\n--- | --- | ---\n' + '\n'.join(
            name.replace('_', ' ') + ' | ' + ('yes' if row['available'] else 'no') + ' | ' + row['needs']
            for name, row in report['features'].items())
        from . import setup_check
        py = report['python']
        numpy = py.get('supported') and py.get('selected_interpreter_verified') and py['numpy']['available']
        pillow = py.get('supported') and py.get('selected_interpreter_verified') and (py.get('pillow') or {}).get('available')
        rows = setup_check.check(self.settings,
                                 probe_numpy=lambda _exe: py['numpy'].get('version') if numpy else None,
                                 probe_pillow=lambda _exe: (py.get('pillow') or {}).get('version') if pillow else None,
                                 blender_present=report['programs']['blender']['available'],
                                 templates=report['export_templates'])
        setup = {'rows': rows, 'message': setup_check.render(rows),
                 'download_plan': setup_check.run(self.settings, fetch=True, yes=False,
                                                  include_templates=True, interactive=False)}
        out = {'ok': True, 'status': 'capabilities_detected_not_verified', 'capabilities': report, 'table': table,
               'guidance': report['guidance'], 'setup': setup}
        from .character_waiver import all_waivers
        waived = all_waivers(self.settings.get('projects_root'), args.get('project'))
        if waived:      # WAIVER (docs/WAIVER.md): every character bound with an owner waiver, read-only
            out['waived_characters'] = waived
            out['guidance'] = list(out['guidance']) + [
                '%d character(s) bound with an owner waiver; the rig kit reports their failures as WAIVED, and hub pack/'
                'publish refuse them unless waived=true: %s' % (len(waived), '; '.join(
                    '%s/%s (%s, %s: %s)' % (w['project'], w['id'], w['owner'], w['approved_on'], ', '.join(w['checks'] or []))
                    for w in waived))]
        return out

    def pack_from_refs(self, project, args):
        from .reference_tools import draft_pack
        return draft_pack(self, project, args)

    def pack_create(self, project, args):
        pack = validate_pack(strict_json(args['pack_json']))
        path = 'packs/' + pack['id'] + '/pack.json'
        if project.path(path).exists():
            fail('exists', 'Pack exists; use a new ID to preserve builds')
        ref = Packs(self.settings, project).snapshot(pack)
        return {'ok': True, 'status': 'created', 'pack': ref, 'path': path, 'render_validation': 'not_run'}

    def pack_validate(self, project, args):
        pack = Packs(self.settings, project).get(args['pack'])
        return {'ok': True, 'status': 'data_valid', 'pack': pack['id'], 'sha256': fingerprint(pack),
                'render_validation': 'not_run', 'audio_validation': 'not_run',
                'note': 'Data checks only; kit asset availability and rendered budgets require build_assets.'}

    def pack_select(self, project, args):
        packs = Packs(self.settings, project)
        ref = packs.snapshot(packs.get(args['pack']))
        if project.path('.maker/current.json').exists():
            operation = {'kind': 'json-patch', 'patch_json': json.dumps([
                {'op': 'add', 'path': '/metadata/hermes64_pack', 'value': ref}])}
            result, revision = self.edit_candidate(project, self.current(project), operation)
            if result['ok']:
                project.write_json('.maker/current.json', revision)
                result['play_runtime'] = self.refresh_play(project)
            return result
        spec = source_guard(project.read_json('source/spec.json'))
        spec['metadata']['hermes64_pack'] = ref
        project.write_json('source/spec.json', spec)
        return {'ok': True, 'status': 'selected_uncompiled', 'pack': ref, 'next': 'hermes64_compile then hermes64_check'}

    def kits(self, args):
        root = Path(self.settings.get('bundle_root') or Path(__file__).resolve().parents[1])
        if not root.is_absolute() or '..' in root.parts:
            fail('configuration', 'bundle_root must be an absolute path without traversal')
        def read(rel):
            path = inspect_path(root / relative(rel))
            if not path.is_file():
                fail('component_unavailable', 'Assembled kit/style data missing: ' + str(path))
            with path.open('rb') as f:
                return strict_json(f.read(JSON_LIMIT + 1))
        if args['action'] == 'style':
            if 'id' not in args:
                fail('arguments', 'style requires id')
            return {'ok': True, 'style': Packs(self.settings).get(args['id'])}
        manifest = read('kits/manifest.json')
        if args['action'] == 'inspect':
            if 'id' not in args:
                fail('arguments', 'inspect requires id')
            for kit in manifest.get('assets', manifest.get('kits', [])):
                if kit.get('id') == args['id']:
                    return {'ok': True, 'kit': kit}
            fail('not_found', 'Kit ID not found')
        if 'id' in args:
            fail('arguments', 'list does not accept id')
        return {'ok': True, 'manifest': manifest}

    def compile(self, project, args):
        spec = source_guard(project.read_json(args['spec_path']))
        if 'patch_json' in args:  # a repair patch from a `next` step; the source file itself is never rewritten
            spec = source_guard(apply_patch(spec, strict_json(args['patch_json'])))
        Packs(self.settings, project).selected(spec)
        try:  # SCENES: scene cards/results are presentation data with their own closed checks
            if '.' in (__package__ or ''):  # installed plugin: story is a sibling package (see repair._story)
                from ..story.presentation.scenes import validate_spec as validate_scenes
            else:
                from story.presentation.scenes import validate_spec as validate_scenes
            validate_scenes(spec)
        except ValueError as exc:
            raise Fault('compile_failed', 'scenes: ' + str(exc)[:2000]) from exc
        folder = self.folder(project, 'compile')
        project.write_json(folder + '/spec.json', spec)
        try:
            game, report = Components(self.settings, project).compile(folder + '/spec.json', folder + '/game.json', folder + '/compile.process.json')
        except Fault as exc:
            if exc.code == 'compile_failed':
                from . import repair
                planned = repair.plan(project.root.name, spec, folder + '/spec.json', compile_error=str(exc))
                exc.next, exc.repair = planned['next'], repair_view(planned)
            raise
        current = {'spec': folder + '/spec.json', 'game': folder + '/game.json'}
        project.write_json('.maker/current.json', current)
        return {'ok': True, 'status': 'compiled', 'revision': current, 'report': report,
                'solvability': 'not_run', 'patched': 'patch_json' in args, 'next': 'hermes64_check',
                'play_runtime': self.refresh_play(project)}

    def check(self, project, args):
        if args.get('action') == 'audit':
            from .audit import run as audit_run
            return audit_run(self, project, args)
        if 'views' in args:
            fail('arguments', 'views applies to action=audit only')
        current = self.current(project)
        folder = self.folder(project, 'check')
        proof = Components(self.settings, project).check(current['game'], folder + '/proof.json', args.get('max_states', 100000))
        result = {'ok': proof['status'] == 'proved', 'status': proof['status'], 'proof': proof,
                  'witnesses': readable_witnesses(proof), 'report_path': folder + '/proof.json'}
        if proof['status'] in ('rejected', 'invalid'):
            from . import repair
            spec = project.read_json(current['spec'])
            planned = repair.plan(project.root.name, spec, current['spec'], proof=proof)
            project.write_json(folder + '/repair.json', planned)
            result.update(next=planned['next'], repair=repair_view(planned))
        elif proof['status'] in ('proved', 'conditional'):
            from . import repair
            spec = project.read_json(current['spec'])
            dead = repair.lint(spec)
            if dead:  # still proves, but some authored content can never happen (e.g. an unreachable dialogue branch)
                planned = repair.plan(project.root.name, spec, current['spec'], audit_findings=dead, proved=proof['status'] == 'proved',
                                      include_warn=True)
                result.update(lint=repair_view(planned), next=planned['next'])
        return result

    def edit(self, project, args):
        result, revision = self.edit_candidate(project, self.current(project), args['operation'], args.get('save_path'), args.get('expected_spec_hash'))
        if result['ok']:
            project.write_json('.maker/current.json', revision)
            result['play_runtime'] = self.refresh_play(project)
        return result

    def refresh_play(self, project):
        """Keep `/hermes64 new`'s Play folder (play/runtime) on the adopted revision.

        Without this the Play command printed on the new-game card keeps opening the pre-edit game. A fresh
        copy is staged first and swapped in only when complete; the old folder is then removed. Projects
        without a Play folder are left alone."""
        if not project.path('play/runtime/project.godot').is_file():
            return 'none'
        import shutil
        token = uuid.uuid4().hex
        staged, old = '.maker/runs/play-next-' + token, '.maker/runs/play-old-' + token
        try:
            project.path(staged).mkdir(parents=True)
            Components(self.settings, project).prepare_runtime(self.current(project)['game'], staged)
            project.path('play').rename(project.path(old))
            project.path(staged).rename(project.path('play'))
        except (Fault, OSError) as exc:
            if project.path(staged).is_dir():
                shutil.rmtree(project.path(staged), ignore_errors=True)
            return 'stale: play/runtime still shows the previous revision (' + str(exc)[:200] + ')'
        shutil.rmtree(project.path(old), ignore_errors=True)
        return 'refreshed'

    def edit_candidate(self, project, current, operation, save=None, expected_hash=None):
        validate(operation, OPERATION)
        old_spec = source_guard(project.read_json(current['spec']))
        old = project.read_json(current['game'])
        if expected_hash is not None and old['spec_hash'] != expected_hash:
            fail('conflict', 'Current spec hash differs; inspect current build before editing')
        folder = self.folder(project, 'edit')
        components = Components(self.settings, project)
        baseline = components.check(current['game'], folder + '/baseline-proof.json')
        if not proof_accepted(baseline, old_spec):  # GAPS2 G5: a combat game's proof is 'conditional' by its own policy
            fail('baseline_unproved', 'The current game does not pass its checker (' + proof_reason(baseline, old_spec) +
                 '); repair or recompile it, then edit.')
        kind = operation['kind']
        manifest = None
        if kind == 'json-patch':
            spec = source_guard(apply_patch(old_spec, strict_json(operation['patch_json'])))
            project.write_json(folder + '/spec.json', spec)
            game, _report = components.compile(folder + '/spec.json', folder + '/game.json', folder + '/compile.process.json')
        else:
            argv = ['edit', str(project.path(current['spec'])), kind, '--out-dir', str(project.path(folder))]
            if kind == 'move-entrance':
                for key in ('room', 'door', 'wall', 'position'):
                    argv.extend(['--' + key, str(operation[key])])
            elif kind == 'change-role':
                for key in ('character', 'role'):
                    argv.extend(['--' + key, operation[key]])
            else:
                project.write_json(folder + '/ending.json', strict_json(operation['ending_json']))
                argv.extend(['--ending', str(project.path(folder + '/ending.json'))])
            code, report = components.story(argv, folder + '/edit.process.json')
            if report.get('status') not in ('edited', 'candidate_rejected'):
                fail('edit_failed', 'Story edit failed: ' + str(report.get('reason', report))[:2000])
            if code == 3:
                fail('edit_failed', 'Story edit inconclusive')
            spec = source_guard(project.read_json(folder + '/spec.json'))
            # Independent compile of the emitted source prevents accepting stale game output.
            game, _report = components.compile(folder + '/spec.json', folder + '/game.json', folder + '/compile.process.json')
            manifest = folder + '/migration.json'
            project.read_json(manifest)
        Packs(self.settings, project).selected(spec)
        proof = components.check(folder + '/game.json', folder + '/proof.json')
        delta = diff(old_spec, spec)
        reg = regression(old_spec, spec, old, game, proof, operation)
        if save:
            reg['save_migration'] = components.migrate(save, current['game'], folder + '/game.json', folder, manifest)
        # GAPS2 G5: the proof is re-run on the edited game; it must pass under the old AND the new policy (a patch cannot
        # loosen its own bar). A refusal carries one plain reason.
        reasons = []
        if not (proof_accepted(proof, old_spec) and proof_accepted(proof, spec)):
            reasons.append('the edited game does not pass its checker (' + proof_reason(proof, spec) + ')')
        if not reg['identity_preserved']:
            reasons.append('the edit removes or rebinds ids (' + (', '.join(reg['lost_ids'][:6]) or 'id/contract/body changed') + ')')
        if not reg['unchanged_byte_identical']:
            reasons.append('a room the edit did not change compiled differently')
        if reg['expected_room_locality'] == 'failed':
            reasons.append('changed rooms ' + str(reg['changed_rooms']) + ' differ from expected_changed_rooms')
        if reg['save_migration']['status'] == 'rejected':
            reasons.append('the save cannot be migrated')
        good = not reasons
        project.write_json(folder + '/plugin-diff.json', delta)
        project.write_json(folder + '/plugin-regression.json', reg)
        revision = {'spec': folder + '/spec.json', 'game': folder + '/game.json'}
        out = {'ok': bool(good), 'status': 'edited' if good else 'candidate_rejected', 'revision': revision,
               'proof_status': proof['status'], 'diff': delta, 'regression': reg, 'report_path': folder + '/plugin-regression.json'}
        if reasons:
            out['reason'] = 'Edit not adopted: ' + '; '.join(reasons) + '. The current game is unchanged.'
        elif proof['status'] == 'conditional':
            out['note'] = 'Proof re-run: conditional (logical proof passed; fights are not proved). Run hermes64_playtest on this revision.'
        return out, revision

    def build_assets(self, project, args):
        # MERGE5: a STORY 1.3 (puzzle) build behind the module pointer builds for its lowered 1.2 build (export.py).
        from .export import build_source, runtime_game
        current = build_source(self, project)
        folder = self.folder(project, 'assets')
        game = runtime_game(project, current['game'], folder)
        report = Components(self.settings, project).assets(game, folder, args['seed'], Packs(self.settings, project).selected(project.read_json(current['spec'])))
        return {'ok': report['status'] == 'passed', 'status': report['status'], 'assets': report,
                'report_path': folder + '/assets/report.json'}

    def replay(self, project, args):
        current = self.current(project)
        folder = self.folder(project, 'replay')
        components = Components(self.settings, project)
        proof_path = folder + '/proof.json'
        proof = components.check(current['game'], proof_path)
        if proof['status'] == 'conditional' and project.read_json(current['game']).get('contract_version') == '1.2.0':
            from .module_replay import run as module_replay
            return module_replay(self, project, current, proof, folder)
        if proof['status'] != 'proved':
            fail('unproved', 'Godot replay requires a current proved checker report')
        report = components.replay(current['game'], proof_path, folder)
        return {'ok': report['status'] == 'passed', 'status': report['status'], 'replay': report,
                'report_path': folder + '/replay.json'}

    def open(self, project, args):
        current = self.current(project)
        folder = self.folder(project, 'open')
        try:
            result = Components(self.settings, project).open(current['game'], folder, args['seconds'], args.get('screenshots', False))
            project.write_json(folder + '/open.process.json', result)
        except Fault as exc:
            if exc.code != 'timeout':
                raise
            result = {'status': 'preview_timeout', 'message': str(exc), 'verified_playable': False}
            project.write_json(folder + '/open.process.json', result)
            return {'ok': False, **result, 'report_path': folder + '/open.process.json'}
        capture = result.get('capture')
        ok = result['returncode'] == 0 and 'SCRIPT ERROR' not in result['stderr'] and 'ERROR:' not in result['stderr']
        if args.get('screenshots'): ok = ok and isinstance(capture, dict) and capture.get('status') == 'passed'
        out = {'ok': bool(ok), 'status': 'captured' if capture else 'exited', 'process': result,
               'capture': capture, 'report_path': folder + '/open.process.json', 'verified_playable': False}
        if args.get('screenshots') and isinstance(capture, dict):
            out.update(self.look_verdict(project, folder, result.get('theme_path')))
        return out

    def look_verdict(self, project, folder, theme_path):
        """Measured style gate on the fresh captures (+ golden regression when this project has blessed goldens).
        A verdict on measurable defects only; not human art approval."""
        from . import style_gate, golden
        screens = project.path(folder + '/screens')
        theme = json.loads(Path(theme_path).read_text(encoding='utf-8')) if theme_path and Path(theme_path).is_file() else {}
        gate = style_gate.gate_directory(screens, theme)
        project.write_json(folder + '/style-gate.json', gate)
        verdict = {'style_gate': {'status': gate['status'], 'scope': gate['scope'], 'set_reasons': gate['set_reasons'],
                                  'rooms': [{'id': r['id'], 'status': r['status'], 'reasons': r['reasons']} for r in gate['rooms']],
                                  'report_path': folder + '/style-gate.json'}}
        goldens = project.path('goldens')
        if (goldens / 'manifest.json').is_file():
            g = golden.compare(screens, goldens)
            project.write_json(folder + '/golden.json', g)
            verdict['golden'] = {'status': g['status'], 'note': g['note'], 'report_path': folder + '/golden.json',
                                 'rooms': [{'id': r['id'], 'status': r['status'], 'reasons': r['reasons']} for r in g['rooms']]}
        return verdict

    def benchmark(self, project, args):
        from .benchmark import run
        return run(self, project, args)


def repair_view(planned):
    """Short findings list for a tool result; full ops stay in the next steps / repair.json."""
    return {'classes': planned['classes'], 'manual': planned['manual'],
            'findings': [{'class': f['class'], 'where': f['where'], 'says': f['says'], 'auto': f.get('auto', False)}
                         for f in planned['findings']][:12]}


def readable_witnesses(proof):
    out = []
    for kind in ('endings', 'collectibles'):
        rows = proof.get(kind, {})
        if not isinstance(rows, dict):
            continue
        for name, result in list(sorted(rows.items()))[:24]:
            if not isinstance(result, dict):
                continue
            witness = result.get('witness', [])
            steps = []
            for index, step in enumerate(witness[:80] if isinstance(witness, list) else []):
                text = step.get('label', step.get('action', step.get('id', str(step)))) if isinstance(step, dict) else str(step)
                steps.append('{}. {}'.format(index + 1, str(text)[:200]))
            out.append({'kind': kind, 'id': name, 'reachable': result.get('reachable'), 'steps': steps,
                        'steps_truncated': isinstance(witness, list) and len(witness) > 80})
    return {'examples': out, 'examples_bounded': True, 'note': 'Full exact counts, witnesses and failures are in proof/report_path.'}
