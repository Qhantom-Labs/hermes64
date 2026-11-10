"""python3 -m adventure_maker.nbchars {export | doctor | parity | preview} (docs/NBCHARS-API.md)."""
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m adventure_maker.nbchars')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('export', help='export characters without Blender')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--cast', help="'all' or comma list of cast ids")
    g.add_argument('--combat', action='store_true', help='enemies, weapon, projectile')
    g.add_argument('--job', help='CHARSYS job JSON (hermes64-charsys-job/1)')
    g.add_argument('--recipe', help='one build item JSON, or a CHARSYS recipe when adventure_maker.character_recipe exists')
    p.add_argument('--out', required=True)
    p.add_argument('--exporter', default='auto', choices=['python', 'blender', 'auto'])
    p.add_argument('--blender-path', default='')
    p.add_argument('--layout', default='published', choices=['published', 'single'])
    p.add_argument('--generator-root', default=None)
    sub.add_parser('doctor', help='one-line truth about the character exporter')
    p = sub.add_parser('parity', help='parity run against the Blender-published oracle')
    p.add_argument('--oracle', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--only', default='')
    p.add_argument('--generator-root', default=None)
    p.add_argument('--visor-root', default=None, help='generator root with the restricted cameo modules (read only)')
    p.add_argument('--reexport-blender', default='', help='comma list of ids to re-export with Blender for the oracle check')
    p.add_argument('--blender-path', default='')
    p.add_argument('--write-verdict', action='store_true', help='write adventure_maker/nbchars/PARITY.json (full set only)')
    p = sub.add_parser('preview', help='Godot contact sheets (no Blender)')
    p.add_argument('--glb', nargs='+', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--godot-path', default='')
    p.add_argument('--clips', default='idle,walk')
    p.add_argument('--play-only', action='store_true', help='headless import/play check only (no windowed sheets)')
    a = ap.parse_args(argv)
    from . import api
    settings = {}
    if getattr(a, 'blender_path', ''):
        settings['blender_path'] = a.blender_path
    if a.cmd == 'doctor':
        print(api.doctor_line(settings))
        return 0
    if a.cmd == 'export':
        if a.cast:
            only = None if a.cast == 'all' else [x for x in a.cast.split(',') if x]
            man = api.export_cast(a.out, only=only, exporter=a.exporter, settings=settings, layout=a.layout,
                                  root=a.generator_root)
            bad = [m['id'] for m in man['characters'] if not m.get('skipped') and not (m.get('audit_pass') and m.get('gate_pass'))]
            print('EXPORT COMPLETE %d files; failures %s' % (man['count'], bad))
            return 1 if bad else 0
        if a.combat:
            rec = api.export_combat(a.out, exporter=a.exporter, settings=settings, root=a.generator_root)
            print('EXPORT COMPLETE enemies %d props %d' % (len(rec['enemies']), len(rec['props'])))
            return 0
        if a.job:
            rep = api.build_job(json.loads(Path(a.job).read_text()), a.out, exporter=a.exporter, settings=settings,
                                root=a.generator_root)
            print('BUILD COMPLETE %d' % len(rep['items']))
            return 0
        doc = json.loads(Path(a.recipe).read_text())
        if 'kind' not in doc or 'pack_id' not in doc:
            try:
                from .. import character_recipe as CR      # CHARSYS (present after the lanes merge)
            except ImportError:
                print('export --recipe: %s is not a build item and adventure_maker.character_recipe is not present '
                      '(CHARSYS); pass a compiled build item' % a.recipe, file=sys.stderr)
                return 2
            job = CR.compile_build([doc]) if hasattr(CR, 'compile_build') else None
            if job is None:
                print('export --recipe: character_recipe has no compile_build()', file=sys.stderr)
                return 2
            rep = api.build_job(job, a.out, exporter=a.exporter, settings=settings, root=a.generator_root)
            print(json.dumps(rep['items'], indent=1))
            return 0
        info = api.build_item(doc, a.out, exporter=a.exporter, settings=settings, root=a.generator_root)
        print(json.dumps(info, indent=1, sort_keys=True))
        return 0
    if a.cmd == 'parity':
        from . import parity
        rep = parity.run(a.oracle, a.out, only=[x for x in a.only.split(',') if x] or None, root=a.generator_root,
                         visor_root=a.visor_root, reexport=[x for x in a.reexport_blender.split(',') if x],
                         blender_path=a.blender_path or None, write_verdict=a.write_verdict)
        print(json.dumps(rep['summary'], indent=1, sort_keys=True))
        return 0 if rep['summary']['verdict'] == 'PASS' else 1
    if a.cmd == 'preview':
        from . import preview
        play = preview.import_check(a.glb, a.out, a.godot_path or None)
        rep = {'play': play.get('summary', play), 'play_ok': play.get('ok')}
        if not a.play_only:
            sheets = preview.contact_sheets(a.glb, a.out, a.godot_path or None, clips=[c for c in a.clips.split(',') if c])
            rep.update(sheets_ok=sheets.get('ok'), shots=[s.get('png') for s in sheets.get('shots', [])])
        print(json.dumps(rep, indent=1, sort_keys=True))
        return 0 if rep.get('play_ok') and rep.get('sheets_ok', True) else 1
    return 2


if __name__ == '__main__':
    sys.exit(main())
