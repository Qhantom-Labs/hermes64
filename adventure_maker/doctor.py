"""Read-only capability probe. Stdlib; does not install, launch engines or change settings.

For the selected child interpreter, run this module through Components.runner
with python_path (see NOBLENDER-INTEGRATION.md). A direct probe reports only the
current interpreter, and explicitly flags a different unprobed python_path.
"""
import importlib
import json
from pathlib import Path
import sys

# The one supported engine (runtime/godot targets it; export templates are hash-pinned to it).
GODOT_VERSION = '4.6.2'
GODOT_RELEASE = 'https://github.com/godotengine/godot/releases/tag/4.6.2-stable'


def godot_help(configured=''):
    """The one Godot-missing message (doctor, /hermes64 new): exact version, where to get it, per-OS steps. One line."""
    where = ' at the configured godot_path %r' % configured[:240] if configured else ''
    return ("Godot wasn't found%s. Hermes64 supports Godot %s, the standard build (not the .NET build): %s . "
            "macOS: unzip Godot_v4.6.2-stable_macos.universal.zip, move Godot.app to Applications, then Control-click it "
            "and choose Open once; Hermes64 finds /Applications/Godot.app by itself (or set godot_path). "
            "Windows: unzip Godot_v4.6.2-stable_win64.exe.zip anywhere and set godot_path in the hermes64 plugin "
            "settings to that .exe." % (where, GODOT_VERSION, GODOT_RELEASE))


TEMPLATES_DIR = Path('Library/Application Support/Godot/export_templates/4.6.2.stable')   # under the home folder


def templates_help():
    """The export-templates message (doctor, hermes64_export / hermes64_demo refusals). One line."""
    return ("Godot 4.6.2 export templates aren't installed. The demo, the web build and standalone game files need them; "
            "making, playing and replaying games do not. Download Godot_v4.6.2-stable_export_templates.tpz (about 1.25 GB) "
            "from %s , open any project in Godot, choose Editor > Manage Export Templates > Install from File and pick that "
            "file. Hermes64 never downloads or installs them, and checks their official hashes when it exports." % GODOT_RELEASE)


def export_templates(home=None):
    """Which official 4.6.2 targets are installed (presence and version only; the exporter checks each hash)."""
    from .export import TEMPLATES
    base = Path(home or Path.home()) / TEMPLATES_DIR
    try:
        version = (base / 'version.txt').read_text().strip()
    except (OSError, UnicodeDecodeError):
        version = ''
    targets = sorted(t for t, name in TEMPLATES.items() if version == '4.6.2.stable' and (base / name).is_file())
    return {'available': bool(targets), 'targets': targets, 'version': version or None, 'hash_checked_on_export': True}


BLENDER_NOTE = ('Blender: not required. Making and playing games, the bundled kits and cast, and new character bodies '
                '(python exporter, numpy) work without it; static kit builds need it only with the default '
                'builder=blender (set builder to python or auto). Blender (optional, set blender_path) also adds '
                'character review renders.')

PLATFORM_NOTE = ('This computer is not a Mac: Hermes64 runs Godot, Blender and its Python probe only inside the macOS '
                 'sandbox (sandbox-exec), so building and playing games needs macOS for now. The web play builds run in '
                 'any browser.')


def guidance(programs, platform=None, templates=None):
    """Plain-English lines for what is missing: Godot (exact version, link, per-OS steps), its export templates,
    Blender (not required)."""
    lines = []
    if (platform or sys.platform) != 'darwin':
        lines.append(PLATFORM_NOTE)
    if not programs['godot']['available']:
        lines.append(godot_help(programs['godot'].get('configured', '')))
    if templates is not None and not templates['available']:
        lines.append(templates_help())
    if not programs['blender']['available']:
        lines.append(BLENDER_NOTE)
    return lines


def python_capabilities():
    result = {'version':sys.version.split()[0],'executable':sys.executable,'supported':sys.version_info >= (3,9)}
    for key,name in [('numpy','numpy'),('pillow','PIL')]:
        try:
            mod = importlib.import_module(name)
            result[key] = {'available':True,'version':mod.__version__}
        except ImportError:
            result[key] = {'available':False,'remedy':'Choose python_path with '+name+' available; nothing was installed.'}
    return result


def probe(settings=None, python_info=None):
    from .runner import locate
    from .safety import Fault
    settings = settings or {}
    py = dict(python_info or python_capabilities())
    configured = settings.get('python_path')
    py['selected_interpreter_verified'] = bool(python_info) or bool(configured and Path(configured).absolute()==Path(sys.executable).absolute())
    if not py['selected_interpreter_verified']:
        py['note'] = 'These packages belong to the current interpreter, not python_path; run the probe through that interpreter before building.'
    programs = {}
    for name in ('godot','blender'):
        try:
            programs[name] = {'available':True,'path':locate(name,settings.get(name+'_path',''))}
        except Fault as e:
            programs[name] = {'available':False,'reason':str(e),'setting':name+'_path',
                              'configured':settings.get(name+'_path','') or ''}
    numpy = py['supported'] and py['numpy']['available'] and py['selected_interpreter_verified']
    godot,blender = programs['godot']['available'],programs['blender']['available']
    def row(available,needs):
        return {'available':bool(available),'needs':needs}
    from .nbchars import select as nbselect
    templates = export_templates()
    npv = py['numpy'].get('version') if numpy else False
    char = nbselect.select_exporter(settings,numpy=npv,blender=programs['blender'].get('path') if blender else False)
    char_ok = char['exporter'] is not None
    char_needs = ('Python 3.9+ with numpy: pure-python skinned + animated GLB exporter (parity %s vs the Blender 5.2 oracle); '
                  'Blender optional (character_exporter=blender + blender_path)' % char['parity'])
    features = {
        'story_authoring_and_pack_data':row(py['supported'],'Python 3.9+ standard library'),
        'build_static_kits':row(numpy,'Python 3.9+ with numpy; builder=python or auto; no Blender'),
        'png_reference_to_pack':row(numpy,'Python + numpy; noninterlaced 8-bit PNG, Pillow for other supported PNG formats'),
        'jpeg_reference_to_pack':row(numpy and py['pillow']['available'],'Python + numpy + Pillow in python_path'),
        'play_replay_screenshot_export':row(godot,'Godot 4.6.2 (standard build); configure godot_path (standalone binary export also needs Godot templates)'),
        'export_and_demo':row(godot and templates['available'],'Godot 4.6.2 + its official export templates (installed targets: %s)' % (', '.join(templates['targets']) or 'none')),
        'new_character_bodies':row(char_ok,char_needs),
        'prebuilt_cast':row(True,'Bundled hash-verified cast can be read/reused without Blender; rendering needs Godot'),
        'proof_preview':row(numpy,'Godot preferred; lower-fidelity software preview when unavailable'),
    }
    return {'python':py,'programs':programs,'features':features,'installs_performed':False,
            'character_exporter':nbselect.doctor_line(settings,numpy=npv,blender=programs['blender'].get('path') if blender else False),
            'export_templates':templates,'guidance':guidance(programs,templates=templates)}


def check(components):
    """Main's tool registration target; probes the actual sandboxed python_path.

    Uses Components' existing Runner and bounds, never direct subprocesses.
    Caller supplies its ordinary project context/lock, just like other tools.
    """
    from .runner import locate
    from .safety import Fault
    settings = components.settings
    try:
        exe = locate('python',settings.get('python_path',''))
        result = components.runner.run([exe,'-B',str(components.shipped('adventure_maker/doctor.py')),'--runtime-json'],
                                       components.project.root,timeout=20)
        if result['returncode'] != 0:
            raise ValueError('Python capability probe failed; change python_path: '+result['stderr'][-500:])
        py = json.loads(result['stdout'])
        report = probe(settings,py)
        report['programs']['python'] = {'available':True,'path':exe}
        return report
    except (Fault,ValueError) as exc:
        py = {'version':None,'executable':None,'supported':False,'numpy':{'available':False},'pillow':{'available':False}}
        report = probe(settings,py)
        report['python']['selected_interpreter_verified'] = False
        report['programs']['python'] = {'available':False,'reason':str(exc),'setting':'python_path'}
        return report


def main():
    if '--runtime-json' in sys.argv:
        print(json.dumps(python_capabilities(),sort_keys=True))
    else:
        report = probe({'python_path':sys.executable},python_capabilities())
        if '--table' in sys.argv:
            print('Feature | Available | Needs')
            print('--- | --- | ---')
            for name,row in report['features'].items():
                print(name.replace('_',' ')+' | '+('yes' if row['available'] else 'no')+' | '+row['needs'])
            for line in report['guidance']:
                print(line)
        else:
            print(json.dumps(report,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
