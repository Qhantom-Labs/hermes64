"""Offline candidate transactions using the existing project lock/path/atomic writer.

The isolated data pointer cannot authorize the old Godot runtime. Existing
Service compile/edit/build/replay gates are deliberately untouched.
"""
import copy
import json
if '.' in (__package__ or ''):
    from ..adventure_maker.service import Service
    from ..adventure_maker.safety import Fault, encode, fail
    from ..story.compiler import canonical
    # Version-dispatching facade: STORY 1.3 (puzzle) sources go to story/puzzle, 1.2 to the unchanged core.
    from ..story.puzzle.api import compile_spec, validate_game, check_game, edit, accepted, is13
    from ..story.errors import SpecError, StateError
    from ..story.modules import enabled, schema as S
    from ..story.modules.registry import registry
    from ..story.validation import obj
else:
    from adventure_maker.service import Service
    from adventure_maker.safety import Fault, encode, fail
    from story.compiler import canonical
    # Version-dispatching facade: STORY 1.3 (puzzle) sources go to story/puzzle, 1.2 to the unchanged core.
    from story.puzzle.api import compile_spec, validate_game, check_game, edit, accepted, is13
    from story.errors import SpecError, StateError
    from story.modules import enabled, schema as S
    from story.modules.registry import registry
    from story.validation import obj
from .schemas import SCHEMAS

POINTER = '.maker/modules/current.json'


class ModuleService(Service):
    def current(self, project):
        value = project.read_json(POINTER)
        fields = ('spec', 'game', 'proof', 'scope') + (('save',) if 'save' in value else ())
        obj(value, fields, 'module pointer')
        if value['scope'] != 'data_only':
            raise SpecError('module pointer scope must be data_only')
        game = validate_game(project.read_json(value['game']))
        if canonical(compile_spec(project.read_json(value['spec']))) != canonical(game):
            raise SpecError('module revision source/build mismatch')
        proof = project.read_json(value['proof'])
        if proof.get('game_hash') != game['game_hash']:
            raise SpecError('module revision proof/build mismatch')
        return value

    def expected(self, project, args):
        if 'expected_spec_hash' not in args or 'expected_game_hash' not in args:
            raise SpecError('expected source/build revisions required for adoption')
        if project.path(POINTER).is_file():
            pointer = self.current(project)
            old = project.read_json(pointer['game'])
            wanted = (old['spec_hash'], old['game_hash'])
        else:
            wanted = ('', '')
        if (args['expected_spec_hash'], args['expected_game_hash']) != wanted:
            raise SpecError('revision conflict: expected source/build hashes differ')

    def adopt(self, project, revision):
        # All immutable payload writes and gates precede this single commit point.
        path = project.path(POINTER)
        previous = path.read_bytes() if path.is_file() else None
        try:
            project.write_json(POINTER, revision)
            if project.read_json(POINTER) != revision:
                raise SpecError('data pointer readback mismatch')
        except (Fault, SpecError, OSError) as exc:
            try:
                if previous is None:
                    if project.path(POINTER).exists():
                        project.path(POINTER).unlink()
                    if project.path(POINTER).exists():
                        raise OSError('new pointer removal failed')
                else:
                    project.write_bytes(POINTER, previous)
                    if project.path(POINTER).read_bytes() != previous:
                        raise OSError('previous pointer restoration mismatch')
            except (Fault, OSError) as rollback:
                raise SpecError('COMMIT_UNCERTAIN: adoption and restoration failed; inspect the exact data pointer: ' + str(rollback)) from exc
            raise SpecError('data adoption rejected; previous pointer restored: ' + str(exc)) from exc

    def store(self, project, result, kind):
        folder = self.folder(project, 'modules-' + kind)
        for key in ('spec', 'game', 'proof', 'diff', 'regression', 'migration', 'save_migration'):
            if key in result:
                project.write_json(folder + '/' + key + '.json', result[key])
        revision = {'spec': folder + '/spec.json', 'game': folder + '/game.json',
                    'proof': folder + '/proof.json', 'scope': 'data_only'}
        migration = result.get('save_migration', {})
        if migration.get('status') in ('as_is', 'migrated'):
            revision['save'] = folder + '/save.json'
            project.write_json(revision['save'], migration['save'])
        # Read back every exact payload needed by the pointer before adoption.
        for key in ('spec', 'game', 'proof', 'save'):
            if key in revision:
                project.read_json(revision[key])
        return revision

    def module_check(self, project, args):
        if args['adopt']:
            self.expected(project, args)
        spec = project.read_json(args['spec_path'])
        if not (enabled(spec) or is13(spec)):
            raise SpecError('module_check requires explicit STORY 1.2 or 1.3 source; legacy sources are not silently upgraded')
        game = compile_spec(spec)
        proof = check_game(game, max_states=args.get('max_states', 100000))
        good = accepted(proof, spec)
        result = {'spec': spec, 'game': game, 'proof': proof}
        revision = self.store(project, result, 'check')
        return {'ok': good, 'status': proof['status'], 'adopted_data': bool(args['adopt'] and good),
                '_adopt_revision': revision if args['adopt'] and good else None,
                'spec_hash': game['spec_hash'], 'game_hash': game['game_hash'], 'revision': revision,
                'proof': proof, 'runtime_status': 'not_run'}

    def edit_candidate(self, project, current, operation, save=None, expected_hash=None, expected_game_hash=None):
        spec = project.read_json(current['spec'])
        old = validate_game(project.read_json(current['game']))
        result = edit(spec, operation, expected_hash or old['spec_hash'], expected_game_hash or old['game_hash'],
                      project.read_json(save) if save else None)
        revision = self.store(project, result, 'edit')
        return result, revision

    def module_edit(self, project, args):
        self.expected(project, args)
        current = self.current(project)
        result, revision = self.edit_candidate(project, current, args['operation'], args.get('save_path'),
                                               args['expected_spec_hash'], args['expected_game_hash'])
        return {'ok': result['ok'], 'status': result['status'], 'revision': revision,
                '_adopt_revision': revision if result['ok'] else None,
                'spec_hash': result['game']['spec_hash'], 'game_hash': result['game']['game_hash'],
                'regression': result['regression'], 'save_migration': result['save_migration'],
                'evidence_invalidated': result['evidence_invalidated']}

    def module_add(self, project, args):
        if args['operation']['kind'] not in ('add-enemy', 'add-ability', 'add-switch'):
            raise SpecError('module_add accepts only add-enemy, add-ability or add-switch; use module_edit for changes')
        return self.module_edit(project, args)

    def module_benchmark(self, project, args):
        from .benchmark import run
        self.expected(project, args)
        return run(self, project, args)

    def handle(self, name, args, **kwargs):
        project = None
        try:
            if name not in SCHEMAS:
                raise SpecError('unknown module tool')
            encode(args)
            S.validate(args, SCHEMAS[name]['parameters'], 'arguments')
            action = name[len('hermes64_'):]
            if action == 'modules':
                entries = registry()
                if args['action'] == 'inspect':
                    if args.get('id') not in entries:
                        raise SpecError('inspect requires a registered module ID')
                    result = {'ok': True, 'module': entries[args['id']]}
                else:
                    if 'id' in args:
                        raise SpecError('list does not accept id')
                    result = {'ok': True, 'modules': entries}
                return self.response(result, None)
            project = self.project(args['project'])
            with project.lock():
                result = getattr(self, action)(project, args)
                revision = result.pop('_adopt_revision', None)
                # Large-response encoding/report IO is also a pre-commit gate.
                response = self.response(result, project)
                if revision is not None:
                    self.adopt(project, revision)
                return response
        except (Fault, SpecError, StateError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            return json.dumps({'ok': False, 'error': {'code': getattr(exc, 'code', 'module_error'), 'message': str(exc)[:2000]}})
