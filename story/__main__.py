"""Offline CLI. Reports use stdout JSON; artifacts use canonical UTF-8 JSON."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from .compiler import canonical, compile_spec, digest, load_json, validate_game
from .checker import check_game
from .edits import move_entrance, change_role, add_ending
from .saves import migrate_save
from .errors import SpecError, StateError


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic per file, not a transaction over an entire edit artifact directory.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=str(target.parent), prefix='.story-', delete=False) as f:
            temporary = Path(f.name)
            f.write(canonical(value))
        os.replace(str(temporary), str(target))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def parser():
    p = argparse.ArgumentParser(prog='python3 -m story', description='Offline deterministic story compiler and checker (contracts 1.0.0, 1.1.0 and data-only 1.2.0).')
    commands = p.add_subparsers(dest='command', required=True)
    compile_p = commands.add_parser('compile', help='compile source JSON to canonical game.json')
    compile_p.add_argument('spec')
    compile_p.add_argument('-o', '--output', required=True)
    check_p = commands.add_parser('check', help='prove a source spec or compiled game; JSON report')
    check_p.add_argument('input')
    check_p.add_argument('--max-states', type=int, default=100000)
    check_p.add_argument('--strategy', choices=['auto', 'symbolic', 'exhaustive'], default='auto')
    check_p.add_argument('--max-bdd-nodes', type=int, default=200000)
    check_p.add_argument('--report')
    edit_p = commands.add_parser('edit', help='write an edited candidate, diff, proof, hashes and migration')
    edit_p.add_argument('spec')
    edit_p.add_argument('operation', choices=['move-entrance', 'change-role', 'add-ending'])
    edit_p.add_argument('--out-dir', required=True)
    edit_p.add_argument('--save', help='optional source-game save to migrate with this edit')
    for name in ['room', 'door', 'wall', 'character', 'role', 'ending']:
        edit_p.add_argument('--' + name)
    edit_p.add_argument('--position', type=int)
    module_p = commands.add_parser('module-edit', help='typed data-only candidate transaction; never adopts a runtime')
    module_p.add_argument('spec')
    module_p.add_argument('operation', help='closed operation JSON file')
    module_p.add_argument('--expected-spec-hash', required=True)
    module_p.add_argument('--expected-game-hash', required=True)
    module_p.add_argument('--out-dir', required=True, help='new directory; existing directory is refused')
    module_p.add_argument('--save', help='optional checkpoint save to migrate')
    migrate_p = commands.add_parser('migrate', help='validate/load or migrate save with explicit source provenance')
    migrate_p.add_argument('save')
    migrate_p.add_argument('--from-game', required=True)
    migrate_p.add_argument('--to-game', required=True)
    migrate_p.add_argument('--manifest')
    migrate_p.add_argument('--max-states', type=int, default=100000)
    migrate_p.add_argument('-o', '--output', required=True, help='save output; never written on rejection')
    migrate_p.add_argument('--report')
    return p


def required(args, *names):
    for name in names:
        if getattr(args, name) is None:
            raise SpecError('--{} is required for {}'.format(name, args.operation))


def run(args):
    if args.command == 'compile':
        if Path(args.spec).resolve() == Path(args.output).resolve():
            raise SpecError('source and output must differ')
        game = compile_spec(load_json(args.spec))
        write_json(args.output, game)
        return 0, {'status': 'compiled', 'output': args.output, 'spec_hash': game['spec_hash'],
                   'game_hash': game['game_hash'], 'file_sha256': digest(game),
                   'room_hashes': {r['id']: r['build_hash'] for r in game['rooms']}}
    if args.command == 'check':
        data = load_json(args.input)
        game = validate_game(data) if isinstance(data, dict) and 'game_hash' in data else compile_spec(data)
        report = check_game(game, max_states=args.max_states, strategy=args.strategy, max_bdd_nodes=args.max_bdd_nodes)
        if args.report:
            write_json(args.report, report)
        return (0 if report['status'] == 'proved' else 4 if report['status'] == 'conditional' else 3 if report['status'] == 'inconclusive' else 2), report
    if args.command == 'module-edit':
        from .modules.edits import edit
        result = edit(load_json(args.spec), load_json(args.operation), args.expected_spec_hash, args.expected_game_hash,
                      load_json(args.save) if args.save else None)
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=False)
        for key in ('spec', 'game', 'proof', 'diff', 'regression', 'migration', 'save_migration'):
            write_json(out / (key + '.json'), result[key])
        if result['save_migration']['status'] in ('as_is', 'migrated'):
            write_json(out / 'save.json', result['save_migration']['save'])
        return (0 if result['ok'] else 2), {'status': result['status'], 'output_dir': str(out),
                                          'game_hash': result['game']['game_hash'], 'adopted_runtime': False}
    if args.command == 'edit':
        spec = load_json(args.spec)
        if args.operation == 'move-entrance':
            required(args, 'room', 'door', 'wall', 'position')
            result = move_entrance(spec, args.room, args.door, args.wall, args.position)
        elif args.operation == 'change-role':
            required(args, 'character', 'role')
            result = change_role(spec, args.character, args.role)
        else:
            required(args, 'ending')
            payload = load_json(args.ending)
            result = add_ending(spec, **payload)
        out = Path(args.out_dir)
        migrated = None
        if args.save:
            migrated = migrate_save(load_json(args.save), compile_spec(spec), result['game'], result['migration'])
        for key in ['spec', 'game', 'diff', 'regression', 'migration']:
            write_json(out / (key + '.json'), result[key])
        if migrated is not None:
            write_json(out / 'save-migration.json', migrated)
            if migrated['status'] != 'rejected':
                write_json(out / 'save.json', migrated['save'])
        good = result['regression']['solvability']['status'] == 'proved' and result['regression']['unchanged_byte_identical']
        good = good and (migrated is None or migrated['status'] != 'rejected')
        response = {k: result[k] for k in ['diff', 'regression', 'migration']}
        response.update(status='edited' if good else 'candidate_rejected', output_dir=str(out),
                        game_hash=result['game']['game_hash'], save_migration=migrated)
        return (0 if good else 2), response
    old, new = load_json(args.from_game), load_json(args.to_game)
    manifest = load_json(args.manifest) if args.manifest else None
    response = migrate_save(load_json(args.save), old, new, manifest, args.max_states)
    if response['status'] != 'rejected':
        write_json(args.output, response['save'])
    if args.report:
        write_json(args.report, response)
    return (2 if response['status'] == 'rejected' else 0), response


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        code, report = run(args)
    except (SpecError, StateError, OSError, ValueError, TypeError) as exc:
        code, report = 2, {'status': 'invalid', 'reason': str(exc)}
    print(canonical(report).decode('utf-8'))
    return code


if __name__ == '__main__':
    sys.exit(main())
