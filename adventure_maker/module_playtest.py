"""Bounded native module run, with exact game/runtime/resource/input receipt pins."""
import copy
import hashlib
import json
from pathlib import Path
from .adapters import Components
from .runner import locate
from .safety import Fault
from .playtest import verdict, write_reports, SCOPE


def physical(project, settings, game_path, proof, folder, render=False):
    component = Components(settings, project)
    project.path(folder).mkdir(parents=True, exist_ok=True)
    runtime = component.prepare_runtime(game_path, folder)
    game = project.read_json(game_path)
    traces = [{'ending': name, 'actions': [s['action'] for s in row.get('witness', [])]}
              for name, row in sorted(proof.get('endings', {}).items()) if row.get('reachable')]
    config = {'output': str(project.path(folder)), 'traces': traces, 'seed': game['gameplay']['seed']}
    project.write_json(folder + '/runtime/playtest-config.json', config)
    argv = [locate('godot', settings.get('godot_path', ''))] + ([] if render else ['--headless'])
    argv += ['--fixed-fps', '60', '--disable-vsync', '--path', str(runtime), '--script', 'res://playtest/module_runner.gd']
    try:
        process = component.runner.run(argv, project.root, timeout=180)
    except Fault as exc:
        process = {'returncode': 124, 'stdout': '', 'stderr': str(exc)}
    project.write_json(folder + '/process.json', dict(process, argv=argv))
    path = project.path(folder + '/native.json')
    native = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if native and native.get('game_hash') != game['game_hash']:
        raise ValueError('native module build mismatch')
    rating, reasons = verdict(native, proof, process)
    pins = {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in runtime.rglob('*') if p.is_file() and '.godot' not in p.parts}
    bindings = project.read_json(folder + '/runtime/bindings.json')
    resources = {}
    for row in list(bindings['assets'].values()) + bindings['characters']:
        asset = Path(row['path'])
        if asset.is_file():
            actual = hashlib.sha256(asset.read_bytes()).hexdigest()
            if actual != row['sha256']: raise ValueError('resource changed during physical run')
            resources[asset.relative_to(component.root).as_posix() if component.root in asset.parents else str(asset.relative_to(project.root))] = actual
    combat_path = project.path(folder + '/runtime/combat.json')
    if combat_path.is_file():
        combat = json.loads(combat_path.read_text(encoding='utf-8'))
        for row in list(combat['enemies'].values()) + list(combat['weapons'].values()):
            asset = Path(row['path'])
            actual = hashlib.sha256(asset.read_bytes()).hexdigest()
            if actual != row['sha256']: raise ValueError('combat art changed during physical run')
            resources[asset.relative_to(component.root).as_posix() if component.root in asset.parents else str(asset.relative_to(project.root))] = actual
    trace = project.path(folder + '/module-inputs.jsonl')
    for name, row in project.read_json(folder + '/runtime/audio.json').items():
        asset = Path(row['path'])
        actual = hashlib.sha256(asset.read_bytes()).hexdigest()
        if actual != row['sha256']: raise ValueError('audio changed during physical run')
        resources['audio:' + name] = actual
    receipt = {'game_hash': game['game_hash'], 'runtime_files': pins, 'resources': resources,
               'input_sha256': hashlib.sha256(trace.read_bytes()).hexdigest() if trace.exists() else None,
               'process_returncode': process['returncode']}
    project.write_json(folder + '/physical-receipt.json', receipt)
    report = dict(native, verdict=rating, reasons=reasons, scope=SCOPE + ' Module skill outcomes remain conditional; no human balance claim.',
                  game_hash=game['game_hash'], proof_status=proof['status'], receipt=folder + '/physical-receipt.json')
    write_reports(project.path(folder), report)
    tested = copy.deepcopy(proof)
    tested['evidence']['physically_tested_by_bot'] = {
        'status': 'tested' if rating in ('PLAYABLE', 'SOLID') else 'failed',
        'verdict': rating, 'receipt': folder + '/physical-receipt.json',
        'game_hash': game['game_hash'], 'input_sha256': receipt['input_sha256']}
    # No logical/conditional/human field is promoted by the bot.
    project.write_json(folder + '/proof-with-physical.json', tested)
    return report
