"""Hermes64 one-step setup check.

    python3 tools/hermes64_setup.py                 plain checklist, one command per missing item
    python3 tools/hermes64_setup.py --json          the same rows as JSON
    python3 tools/hermes64_setup.py --fetch-plan    the pinned-hash download plan (printed only, never run)
    [--godot-path P] [--python-path P] [--blender-path P] [--builder auto|python|blender]

    python3 tools/hermes64_setup.py --fetch         disclose and ask before downloading the official, SHA-512-pinned Godot
    python3 tools/hermes64_setup.py --fetch --yes   explicit consent typed by you (noninteractive)
    [--templates]                                 also the official export templates (.tpz, about 1.25 GB; the three
                                                  players exports use are kept, the .tpz is deleted)

Plain checklist/--fetch-plan download nothing. Exit 0 when making and playing works, 1 otherwise.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adventure_maker import setup_check  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description='Hermes64 setup checklist; --fetch explicitly offers pinned downloads')
    p.add_argument('--json', action='store_true')
    p.add_argument('--fetch-plan', action='store_true')
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--yes', action='store_true')
    p.add_argument('--templates', action='store_true')
    for name in ('godot', 'python', 'blender'):
        p.add_argument('--%s-path' % name, default='')
    p.add_argument('--builder', default='')
    a = p.parse_args(argv)
    if a.fetch_plan:
        if a.fetch or a.yes or a.templates:
            p.error('--fetch-plan cannot be combined with --fetch/--yes/--templates')
        print(setup_check.fetch_plan())
        return 0
    conf = {'godot_path': a.godot_path, 'python_path': a.python_path, 'blender_path': a.blender_path, 'builder': a.builder}
    def progress(line):
        print(line, file=sys.stderr if a.json else sys.stdout, flush=True)
    result = setup_check.run(conf, fetch=a.fetch, yes=a.yes, include_templates=a.templates, interactive=True,
                             emit=progress if a.fetch else None)
    if a.json:
        print(json.dumps(result if a.fetch else result['rows'], indent=2))
    elif not a.fetch:
        print(result['message'])
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
