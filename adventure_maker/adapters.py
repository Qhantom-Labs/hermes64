"""Only process boundary to STORY, Blender and Godot; argv never shell."""
from pathlib import Path
import os
import hashlib
from .schemas import validate
from .packs import validate_pack, fingerprint
from .runner import Runner, locate, silent_godot
from .safety import JSON_LIMIT, fail, inspect_path, relative, strict_json


class Components:
    def __init__(self, settings, project):
        self.settings = settings
        self.project = project
        self.root = Path(settings.get('bundle_root') or Path(__file__).resolve().parents[1])
        if not self.root.is_absolute() or '..' in self.root.parts:
            fail('configuration', 'bundle_root must be an absolute path without traversal')
        inspect_path(self.root)
        self.runner = Runner(project)

    def shipped(self, rel):
        path = inspect_path(self.root / relative(rel))
        if not path.exists():
            fail('component_unavailable', 'Assembled component missing: ' + str(path) + '; see docs/ADAPTERS.md')
        return path

    def story(self, argv, receipt):
        self.shipped('story/__main__.py')
        python = locate('python', self.settings.get('python_path', ''))
        result = self.runner.run([python, '-B', '-m', 'story'] + argv, self.root, timeout=90)
        # Parse before interpreting an exit code: success cannot excuse malformed JSON.
        data = strict_json(result['stdout'])
        if not isinstance(data, dict):
            fail('component_protocol', 'story stdout must be a JSON object')
        self.project.write_json(receipt, dict(result, parsed=data, argv=[python, '-B', '-m', 'story'] + argv))
        if result['returncode'] not in (0, 2, 3, 4):
            fail('component_failed', 'story exit {}: {}'.format(result['returncode'], result['stderr'][:2000]))
        return result['returncode'], data

    def compile(self, source, output, receipt):
        code, report = self.story(['compile', str(self.project.path(source)), '-o', str(self.project.path(output))], receipt)
        if code != 0 or report.get('status') != 'compiled':
            fail('compile_failed', 'story compile failed: ' + str(report.get('reason', report))[:2000])
        game = self.project.read_json(output)
        if not isinstance(game, dict) or not all(k in game for k in ('game_hash', 'spec_hash', 'rooms')):
            fail('component_protocol', 'Compiled game lacks contract hash/room fields')
        return game, report

    def check(self, game, report_path, max_states=100000):
        code, report = self.story(['check', str(self.project.path(game)), '--max-states', str(max_states),
                                  '--report', str(self.project.path(report_path))], report_path + '.process.json')
        if report.get('status') not in ('proved', 'conditional', 'rejected', 'invalid', 'inconclusive'):
            fail('component_protocol', 'Unknown checker status')
        if (code == 0) != (report['status'] == 'proved'):
            fail('component_protocol', 'Checker exit/status mismatch')
        if (code == 4) != (report['status'] == 'conditional'):
            fail('component_protocol', 'Conditional checker exit/status mismatch')
        if self.project.read_json(report_path) != report:
            fail('component_protocol', 'Checker file/stdout mismatch')
        return report

    def migrate(self, save, old_game, new_game, folder, manifest=None):
        self.project.read_json(save)
        args = ['migrate', str(self.project.path(save)), '--from-game', str(self.project.path(old_game)),
                '--to-game', str(self.project.path(new_game)), '-o', str(self.project.path(folder + '/save.json')),
                '--report', str(self.project.path(folder + '/save-migration.json'))]
        if manifest:
            args += ['--manifest', str(self.project.path(manifest))]
        code, report = self.story(args, folder + '/migrate.process.json')
        if report.get('status') not in ('as_is', 'migrated', 'rejected'):
            fail('component_protocol', 'Unknown migration status')
        if code == 0 and report['status'] == 'rejected' or code != 0 and report['status'] != 'rejected':
            fail('component_protocol', 'Migration exit/status mismatch')
        if code == 0:
            self.project.read_json(folder + '/save.json')
        return report

    def assets(self, game, folder, seed, pack):
        """KITS 3.1 real builder; legacy 2.0 protocol remains for boundary fixtures."""
        if self.shipped('kits/manifest.json').is_file():
            current_manifest = strict_json(self.shipped('kits/manifest.json').read_bytes())
            if current_manifest.get('contract_version') == '3.1.0':
                from .assets_v3 import build
                return build(self, game, folder, seed, validate_pack(pack))
        pack = validate_pack(pack)
        exe = locate('blender', self.settings.get('blender_path', ''))
        script = self.shipped('kits/build.py')
        with self.shipped('kits/manifest.json').open('rb') as f:
            manifest = strict_json(f.read(JSON_LIMIT + 1))
        if not isinstance(manifest, dict) or manifest.get('contract_version') != '2.0.0':
            fail('component_protocol', 'Expected KITS 2.0.0 manifest')
        if manifest.get('pack_id') != pack['kit_pack_id']:
            fail('component_protocol', 'KITS manifest does not support selected pack; no theme fallback')
        assets = manifest.get('assets')
        if not isinstance(assets, list):
            fail('component_protocol', 'KITS manifest assets must be an array')
        prepared = []
        for preset in pack['presets']:
            matches = [x for x in assets if isinstance(x, dict) and x.get('id') == preset['asset_id']]
            if len(matches) != 1:
                fail('component_protocol', 'Unknown or duplicate kit ID: ' + preset['asset_id'])
            entry = matches[0]
            params = strict_json(preset['params_json'])
            validate(params, entry['params_schema'])
            prepared.append((preset, entry))
        target = self.project.path(folder + '/assets')
        target.mkdir()
        files, measured = [], []
        for preset, entry in prepared:
            file = preset['id'] + '.glb'
            out = self.project.path(folder + '/assets/' + file)
            argv = [exe, '--background', '--factory-startup', '--disable-autoexec', '--python', str(script),
                    '--', '--id', preset['asset_id'], '--seed', str(seed), '--params', preset['params_json'], '--out', str(out)]
            process = self.runner.run(argv, self.project.root, timeout=180)
            self.project.write_json(folder + '/' + preset['id'] + '.blender.process.json', dict(process, argv=argv))
            if process['returncode'] != 0:
                fail('asset_failed', 'Blender exited {}: {}'.format(process['returncode'], process['stderr'][:2000]))
            inspect_path(out)
            if not out.is_file() or not 0 < out.stat().st_size <= 16 * 1024 * 1024:
                fail('component_protocol', 'Missing or oversized GLB output')
            sidecar = self.project.read_json(folder + '/assets/' + file + '.json')
            if not isinstance(sidecar, dict) or sidecar.get('sha256') != hashlib.sha256(out.read_bytes()).hexdigest():
                fail('component_protocol', 'GLB sidecar hash mismatch')
            tri, limit = sidecar.get('tri_count'), entry.get('tri_limit')
            if type(tri) is not int or type(limit) is not int or tri < 0 or tri > limit:
                fail('asset_failed', 'Reported triangle budget missing or exceeded')
            files.append(file)
            measured.append({'file': file, 'sidecar': sidecar, 'tri_limit': limit})
        report = {'status': 'partial', 'files': files, 'pack_sha256': fingerprint(pack),
                  'game_hash': self.project.read_json(game)['game_hash'],
                  'validators': {'sidecar_hash_and_reported_tri_budget': measured},
                  'style_validation': {'status': 'not_run', 'reason': 'KITS 2.0 per-asset CLI does not certify selected-pack palette, fog, texture or scene budgets'},
                  'note': 'Assets exported; counts are builder-reported, hashes independently checked. No rendered acceptance.'}
        self.project.write_json(folder + '/assets/report.json', report)
        self.project.audit()
        return report

    def prepare_runtime(self, game, folder):
        source = self.shipped('runtime/godot')
        self.shipped('runtime/godot/project.godot')
        destination = self.project.path(folder + '/runtime')
        destination.mkdir()
        total = count = 0
        for parent, dirs, files in os.walk(source, followlinks=False):
            for name in dirs + files:
                inspect_path(Path(parent) / name)
            dirs[:] = [d for d in dirs if d not in ('.godot', '.git', '__pycache__')]
            for name in files:
                path = Path(parent) / name
                if path.suffix in ('.pyc', '.pyo'):
                    fail('component_protocol', 'Runtime template cannot contain Python bytecode')
                count += 1
                total += path.stat().st_size
                if count > 1000 or total > 32 * 1024 * 1024:
                    fail('limit', 'Runtime template file/size limit exceeded')
                rel = folder + '/runtime/' + path.relative_to(source).as_posix()
                self.project.write_bytes(rel, path.read_bytes())
        self.project.write_json(folder + '/runtime/game.json', self.project.read_json(game))
        if (self.root / 'kits/bindings.json').is_file():
            from .assets_v3 import runtime_snapshot
            runtime_snapshot(self, self.project.read_json(game), folder)
            if (self.root / 'bindings.json').is_file():
                if '.' in (__package__ or ''):
                    from ..characters.integration import stage_runtime
                else:
                    from characters.integration import stage_runtime
                stage_runtime(destination, self.root)
            from .cast_binding import stage as stage_cast   # CHARBIND: project cast (hermes64_character bind)
            stage_cast(destination, self.project, self.root)
        return destination

    def replay(self, game, proof_path, folder, save_path=None):
        exe = locate('godot', self.settings.get('godot_path', ''))
        self.shipped('runtime/godot/tests/playthrough.gd')
        runtime = self.prepare_runtime(game, folder)
        report_path = folder + '/replay.json'
        argv = [exe, '--headless', '--path', str(runtime), '--script', 'res://tests/playthrough.gd', '--',
                '--game', str(self.project.path(game)), '--proof', str(self.project.path(proof_path)),
                '--report', str(self.project.path(report_path))]
        if save_path: argv += ['--save', str(self.project.path(save_path))]
        argv = silent_godot(argv)
        process = self.runner.run(argv, self.project.root, timeout=180)
        self.project.write_json(folder + '/godot.process.json', dict(process, argv=argv))
        if process['returncode'] != 0:
            fail('replay_failed', 'Godot exited {}: {}'.format(process['returncode'], process['stderr'][:2000]))
        if not self.project.path(report_path).is_file():
            fail('component_protocol', 'Godot produced no report: ' + process['stderr'][:1800] + process['stdout'][:200])
        report = self.project.read_json(report_path)
        proof = self.project.read_json(proof_path)
        endings = proof.get('endings', {})
        if not isinstance(report, dict) or report.get('status') not in ('passed', 'failed'):
            fail('component_protocol', 'Godot replay report missing passed/failed status')
        if report.get('game_hash') != self.project.read_json(game)['game_hash']:
            fail('component_protocol', 'Godot replay game hash differs from current revision')
        received = report.get('endings')
        if not endings or not isinstance(received, dict) or set(endings) != set(received):
            fail('component_protocol', 'Godot ending coverage does not match proof')
        if report['status'] == 'passed' and (report.get('save_round_trip') is not True or
                any(not isinstance(row, dict) or row.get('status') != 'passed' for row in received.values())):
            fail('component_protocol', 'Godot pass lacks ending/save-round-trip evidence')
        if save_path and report.get('imported_save', {}).get('ok') is not True:
            fail('component_protocol', 'Godot did not load the supplied migrated save')
        self.project.audit()
        return report

    def open(self, game, folder, seconds, screenshots=False):
        exe = locate('godot', self.settings.get('godot_path', ''))
        runtime = self.prepare_runtime(game, folder)
        argv = [exe, '--path', str(runtime), '--', '--game=' + str(self.project.path(game)),
                '--pack=' + str(runtime / 'theme.json'), '--bindings=' + str(runtime / 'bindings.json'),
                '--quit_after=' + str(seconds)]
        if screenshots:
            argv.append('--screens=' + str(self.project.path(folder + '/screens')))
        from . import platforms
        if platforms.host() == 'linux':
            from .linux_display import prepare
            argv = prepare(argv, self.settings)
        result = self.runner.run(argv, self.project.root, timeout=min(seconds + 25, 180))
        result['argv'] = argv
        result['theme_path'] = str(runtime / 'theme.json')
        if screenshots and self.project.path(folder + '/screens/capture.json').exists():
            result['capture'] = self.project.read_json(folder + '/screens/capture.json')
        return result
