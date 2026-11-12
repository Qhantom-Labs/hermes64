"""Capture the scene cards, room entries and results card of a module game from a bot movie (GAPS2 G14).

    python3 -B -m adventure_maker.scene_capture --game-dir <games folder>/<game> --out <new folder> [--tail 90]
    python3 -B -m adventure_maker.scene_capture --runtime <prepared runtime> --movie <x.h64movie.json> --out <new folder>

With --game-dir the newest hermes64_playtest run that recorded a movie is used (its runtime and modules.h64movie.json).
The game's own runtime replays the movie with `--capture_scenes`: the replay keeps running past its final hash, so the
ending scene and the results card play; one frame is saved per scene card, per room entry and for the results card,
plus capture.json (file names, ticks, whether a text box or room-name card was on screen). Needs a display: frames
come from a rendered window. Reads the project; writes only into --out (which must not exist yet).
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def newest_run(game_dir):
    runs = sorted((p for p in (Path(game_dir) / '.maker/runs').glob('playtest-*')
                   if (p / 'modules.h64movie.json').is_file() and (p / 'runtime/project.godot').is_file()),
                  key=lambda p: (p / 'modules.h64movie.json').stat().st_mtime)
    if not runs:
        raise SystemExit('No playtest run with a movie in %s; run hermes64_playtest first.' % game_dir)
    return runs[-1] / 'runtime', runs[-1] / 'modules.h64movie.json'


def command(godot, runtime, movie, out, tail):
    return [godot, '--fixed-fps', '60', '--disable-vsync', '--path', str(runtime), '--',
            '--pack=res://theme.json', '--bindings=res://bindings.json', '--replay', str(movie),
            '--capture_scenes=' + str(out), '--capture_tail=%d' % tail]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game-dir', type=Path)
    ap.add_argument('--runtime', type=Path)
    ap.add_argument('--movie', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--tail', type=int, default=90, help='seconds to keep running after the movie ends (default 90)')
    ap.add_argument('--godot', default='')
    a = ap.parse_args(argv)
    if a.game_dir:
        runtime, movie = newest_run(a.game_dir)
    elif a.runtime and a.movie:
        runtime, movie = a.runtime, a.movie
    else:
        raise SystemExit('Give --game-dir, or --runtime and --movie.')
    out = a.out.resolve()
    if out.exists():
        raise SystemExit('Output folder exists; choose a new one: %s' % out)
    from .runner import locate, scratch_env
    godot = locate('godot', a.godot)
    out.mkdir(parents=True)
    argv_run = command(godot, Path(runtime).resolve(), Path(movie).resolve(), out, a.tail)
    with scratch_env() as env:
        done = subprocess.run(argv_run, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=a.tail + 1800, check=False, env=env)
    process = json.dumps({'argv': argv_run, 'returncode': done.returncode,
                          'stdout_tail': done.stdout[-4000:], 'stderr_tail': done.stderr[-4000:]}, indent=2)
    (out / 'process.json').write_text(process, encoding='utf-8')
    receipt = out / 'capture.json'
    if not receipt.is_file():
        print('No capture receipt (exit %d); see %s' % (done.returncode, out / 'process.json'))
        return 1
    data = json.loads(receipt.read_text(encoding='utf-8'))
    frames = data.get('frames', [])
    print('capture: %s, %d frames (%d scene, %d room, %d results), text boxes on %d, replay ok=%s'
          % (data.get('status'), len(frames), sum(f['kind'] == 'scene' for f in frames), sum(f['kind'] == 'room' for f in frames),
             sum(f['kind'] == 'results' for f in frames), sum(bool(f.get('text_box')) for f in frames), data.get('replay', {}).get('ok')))
    return 0 if data.get('status') == 'results_captured' else 1


if __name__ == '__main__':
    sys.exit(main())
