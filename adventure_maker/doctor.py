"""Read-only capability probe. Stdlib; does not install, launch engines or change settings.

For the selected child interpreter, run this module through Components.runner
with python_path (see NOBLENDER-INTEGRATION.md). A direct probe reports only the
current interpreter, and explicitly flags a different unprobed python_path.
"""
import importlib
import json
from pathlib import Path
import sys

try:
    from . import platforms
except ImportError:          # run as a script by path (doctor.py --runtime-json): no package parent
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import platforms

# The one supported engine (runtime/godot targets it; export templates are hash-pinned to it).
GODOT_VERSION = '4.6.2'
GODOT_RELEASE = 'https://github.com/godotengine/godot/releases/tag/4.6.2-stable'


def godot_help(configured=''):
    """The one Godot-missing message (doctor, /hermes64 new): exact version, where to get it, per-OS steps. One line."""
    where = ' at the configured godot_path %r' % configured[:240] if configured else ''
    return ("Godot wasn't found%s. Hermes64 supports Godot %s, the standard build (not the .NET build): %s . "
            "Run /hermes64 setup --fetch for an explicit, hash-verified download into your user cache. "
            "macOS: unzip Godot_v4.6.2-stable_macos.universal.zip, move Godot.app to Applications, then Control-click it "
            "and choose Open once; Hermes64 finds /Applications/Godot.app by itself (or set godot_path). "
            "Windows: unzip Godot_v4.6.2-stable_win64.exe.zip anywhere and set godot_path in the hermes64 plugin "
            "settings to that .exe (or the HERMES64_GODOT environment variable); Hermes64 finds it by itself in "
            "%%LOCALAPPDATA%%\\Programs\\Godot, Program Files\\Godot, winget and scoop installs." % (where, GODOT_VERSION, GODOT_RELEASE))


def godot_version(path):
    """The version a macOS Godot.app declares (Contents/Info.plist CFBundleShortVersionString), else None. Reads one
    file; never launches the engine."""
    if sys.platform != 'darwin' or not path:
        return None
    plist = Path(path).parents[1] / 'Info.plist' if len(Path(path).parents) > 1 else None
    if plist is None or not plist.is_file():
        return None
    import plistlib
    try:
        value = plistlib.loads(plist.read_bytes()).get('CFBundleShortVersionString')
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def other_godot(version, path, lead='Found'):
    """REUSE: one line when the Godot found is not the proven GODOT_VERSION ('' when it is, or when its version is
    unknown). Message only: the pin, discovery and every gate are unchanged (docs/REUSE-RESULT.md, Godot policy)."""
    if not version or version == GODOT_VERSION:
        return ''
    return ('%s Godot %s at %s; Hermes64 is proven on %s; fetch the pinned %s (recommended, one command: /hermes64 setup '
            '--fetch --yes; Hermes64 then uses it and your %s stays) or set godot_path to it at your own risk (unproven; '
            'exports need %s)' % (lead, version, path, GODOT_VERSION, GODOT_VERSION, version, GODOT_VERSION))


TEMPLATES_DIR = Path('Library/Application Support/Godot/export_templates/4.6.2.stable')   # macOS, under the home folder


def templates_help():
    """The export-templates message (doctor, hermes64_export / hermes64_demo refusals). One line."""
    return ("Godot 4.6.2 export templates aren't installed. The demo, the web build and standalone game files need them; "
            "making, playing and replaying games do not. Download Godot_v4.6.2-stable_export_templates.tpz (about 1.25 GB) "
            "from %s , open any project in Godot, choose Editor > Manage Export Templates > Install from File and pick that "
            "file (they land in %s). This check never downloads or installs them; the user may type "
            "/hermes64 setup --fetch --yes --templates for the explicit official-only fetch. Hermes64 checks their "
            "official hashes when it exports." % (GODOT_RELEASE, templates_location()))


def templates_location(platform=None):
    if platforms.is_windows(platform):
        return '%APPDATA%\\Godot\\export_templates\\4.6.2.stable, or set HERMES64_TEMPLATES'
    if platforms.host(platform) == 'darwin':
        return '~/Library/Application Support/Godot/export_templates/4.6.2.stable'
    return '~/.local/share/godot/export_templates/4.6.2.stable'


def export_templates(home=None, platform=None, env=None):
    """Which official 4.6.2 targets are installed (presence and version only; the exporter checks each hash)."""
    from .export import TEMPLATES
    base = Path(str(platforms.templates_dir(platform, env, home)))
    try:
        version = (base / 'version.txt').read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        version = ''
    targets = sorted(t for t, name in TEMPLATES.items() if version == '4.6.2.stable' and (base / name).is_file())
    return {'available': bool(targets), 'targets': targets, 'version': version or None, 'hash_checked_on_export': True,
            'folder': str(platforms.templates_dir(platform, env, '~' if home is None else home))}


BLENDER_NOTE = ('Blender: not required. Making and playing games, the bundled kits and cast, and new character bodies '
                '(python exporter, numpy) work without it; with the default builder=auto, room models use the Python '
                'builder (numpy) when Blender is missing; only builder=blender needs it (set builder to python or auto). Blender (optional, set blender_path) also adds '
                'character review renders.')

PLATFORM_NOTE = ('This computer is not a Mac: Hermes64 runs Godot, Blender and its Python probe only inside a child '
                 'sandbox. macOS has one built in (sandbox-exec); on Windows making and rebuilding games works after '
                 'you opt in to the Windows Job Object runner (no OS network or write confinement): see the Windows '
                 'checklist (python -m adventure_maker.doctor --windows-checklist). Playing exported games and the web '
                 'play builds needs no opt-in.')
LINUX_NOTE = ('This computer is Linux: Hermes64 has no Linux child sandbox yet, so making games is off; exported web '
              'builds run in any browser.')


def guidance(programs, platform=None, templates=None, env=None):
    """Plain-English lines for what is missing: platform runner, Godot (exact version, link, per-OS steps), its
    export templates, Blender (not required)."""
    lines = []
    plat = platforms.host(platform)
    if plat == 'win32':
        if not platforms.windows_runner_enabled(env):
            lines.append(PLATFORM_NOTE)
    elif plat != 'darwin':
        lines.append(LINUX_NOTE)
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
            'export_templates':templates,'guidance':guidance(programs,templates=templates),
            'platform':{'host':platforms.host(),'isolation':platforms.isolation(),
                        'python_command':platforms.python_command(),
                        'override_env':dict(platforms.OVERRIDE_ENV,templates=platforms.TEMPLATES_ENV)}}


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


def windows_report(platform='win32'):
    """The Windows checklist lines for this computer (or, with platform='win32' on a Mac, a simulation of what a
    Windows computer with this environment would see; program lookups use the Windows candidate list)."""
    report = probe({'python_path':sys.executable},python_capabilities())
    if platforms.host() != 'win32':
        report['programs']['godot'] = {'available':False}
        report['programs']['blender'] = {'available':False}
        home = platforms.PureWindowsPath('C:/Users/you')
        report['export_templates'] = dict(export_templates(platform='win32',env={},home=home),available=False,targets=[])
        return platforms.windows_checklist(report,env={},home=home)
    return platforms.windows_checklist(report)


def main():
    if '--runtime-json' in sys.argv:
        print(json.dumps(python_capabilities(),sort_keys=True))
    elif '--windows-checklist' in sys.argv:
        if platforms.host() != 'win32':
            print('SIMULATED: this computer is %s, not Windows; program lookups below are not real.' % platforms.host())
        lines = windows_report()
        for line in lines:
            print(line)
        print('RESULT  %s' % ('READY to make games' if all(not l.startswith(('MISSING','OFF')) for l in lines[:6])
                              else 'NOT READY: fix the MISSING/OFF lines above'))
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
