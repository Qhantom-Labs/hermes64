"""Local-only Godot release exports: fail-closed portable data closure, no uploader."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import zipfile
from .adapters import Components
from .runner import locate, silent_godot
from . import platforms
from .safety import fail, inspect_path

SAVE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
WINDOWS_DEVICE = re.compile(r'^(con|prn|aux|nul|com[0-9]|lpt[0-9])$', re.I)
RUNTIME_USER_DIR = 'config/custom_user_dir_name="AdventureRuntime"'


def user_dir_name(game_id):
    """Per-game save folder under the OS data dir (Godot application/config/custom_user_dir_name)."""
    if not isinstance(game_id,str) or not SAVE_ID.match(game_id) or WINDOWS_DEVICE.match(game_id):
        fail('release_save_dir','Game id must be 1-64 letters, digits, _ or - (not a Windows device name) to key its save folder')
    return 'Hermes64/'+game_id


def user_dir_project(project, game_id):
    """Point the exported project's user:// at Hermes64/<game_id>; fail if the runtime template lost the key."""
    if project.count(RUNTIME_USER_DIR)!=1 or 'config/use_custom_user_dir=true' not in project:
        fail('release_save_dir','Runtime project.godot no longer carries the per-game save folder setting')
    return project.replace(RUNTIME_USER_DIR,'config/custom_user_dir_name="'+user_dir_name(game_id)+'"')


TEMPLATES = {'web':'web_nothreads_release.zip','macos':'macos.zip','windows':'windows_release_x86_64.exe'}
TEMPLATE_HASHES = {'web':'7d91986ea27d901b37963ace014a88ab6ba8e4bfe830031043bcf89ebac307dc',
                   'macos':'bf4bc195bb4dbe5edf7067582c5b1c428de70eaf552b9c284dd533a8c3d70717',
                   'windows':'3b2d3f99bd640961aad1a1a200f0f7233b7de45b02801ce22d3224dc294d93d1'}
LICENSE_HASHES = {'LICENSE.txt':'b0435e3b3e4e55238f05f4b306f30524a1b2e20147810d436eaa554fa6855c80',
                  'COPYRIGHT.txt':'dc043a7dbf69632560219e72fbc61ef9fa7338c7a773660acd81b51590b69104'}
PRIVATE = re.compile(rb'cameo_visor_01|characters[/\\]internal[/\\]|/Users/[^\x00\s"\x27]+|(?<![A-Za-z0-9_./-])/home/[^\x00\s"\x27]+|[A-Za-z]:[/\\]Users[/\\]',re.I)
# Release runtime allow-list. Under RELEASE_DIRS only scripts/shaders and the RELEASE_DATA files are copied; a data
# file the shipped scripts read that is not listed is silently absent from exported games (tests/test_feel4_export.py).
RELEASE_DIRS = ('core','view','look','shaders','input','modules')
RELEASE_DATA = ('input/defaults.json','input/keyhud.json','input/GLYPHS-LICENSE.txt','modules/combat/readability.json','modules/combat/robots.json',
                'view/shell_kit_metadata.json','view/solid_kit_metadata.json')


def digest(raw): return hashlib.sha256(raw).hexdigest()


def public_data(value):
    """Reject policy flags/references, including nested metadata. Never sanitize a refusal into a pass."""
    if isinstance(value, dict):
        if value.get('internal_only') or value.get('restricted') or value.get('public_release') is False:
            fail('release_private', 'Internal-only/restricted data cannot be exported')
        for key, child in value.items():
            if key.lower() in ('private_reference', 'private_references', 'reference_images', 'source_home'):
                fail('release_private', 'Private reference metadata cannot be exported')
            public_data(child)
    elif isinstance(value, list):
        for item in value: public_data(item)
    elif isinstance(value, str):
        if PRIVATE.search(value.encode()) or value.startswith(('http://','https://','file://')):
            fail('release_private', 'Private, external or absolute home reference cannot be exported')


def scan_bytes(raw, name, depth=0):
    if PRIVATE.search(raw): fail('release_private', 'Private/home reference in release payload: '+name)
    if raw[:4] == b'PK\x03\x04':
        if depth > 4: fail('release_scan', 'Archive nesting exceeds scan bound')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > 1024*1024*1024: fail('release_scan','Archive scan size bound')
            for item in z.infolist():
                if item.is_dir(): continue
                if item.filename.startswith('/') or '..' in Path(item.filename).parts: fail('release_scan','Unsafe archive path')
                scan_bytes(z.read(item),name+'!'+item.filename,depth+1)


def portable_web_vfs(raw):
    # Official Emscripten virtual HOME is not a host leak, but relocate it to
    # /data so even a literal home-path scan stays clean. Same-length WASM data
    # replacement preserves section sizes/offsets; JS creates the matching root.
    return raw.replace(b'/home/web_user', b'/data/web_user').replace(b'FS.mkdir("/home")', b'FS.mkdir("/data")')


def native_diagnostic_paths(raw):
    # Only the known official Rust source-root prefix, not arbitrary user paths.
    # Exact-length replacement retains Mach-O layout; caller must ad-hoc re-sign.
    return raw.replace(b'/Users/runner/.cargo/', b'/build/runner/.cargo/').replace(b'/home/runner/.cargo/', b'/data/runner/.cargo/')


def scan_tree(root):
    rows=[]
    for path in sorted(Path(root).rglob('*')):
        inspect_path(path)
        if not path.is_file(): continue
        raw=path.read_bytes(); name=path.relative_to(root).as_posix()
        scan_bytes(raw,name)
        rows.append({'path':name,'bytes':len(raw),'sha256':digest(raw)})
    return rows


_WINDOWS_HOST=os.name=='nt'


def _executable(path):
    # Windows reports every file as executable (os.access X_OK); zip modes must not depend on the host.
    # No macOS app is exported on Windows (refused), and Windows/web files carry no mode bit.
    if _WINDOWS_HOST:
        return False
    return os.access(path,os.X_OK)


def zip_tree(root, output):
    """Deterministic sorted list, fixed timestamps and executable permissions; bytes aren't engine reproducibility."""
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(Path(root).rglob('*')):
            inspect_path(path)
            if not path.is_file(): continue
            info=zipfile.ZipInfo(path.relative_to(root).as_posix(),(1980,1,1,0,0,0))
            info.create_system=3
            info.external_attr=((stat.S_IFREG | (0o755 if _executable(path) else 0o644)) << 16)
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,path.read_bytes())


def preset_template(target,host_template,local_templates,platform=None):
    """The template path written into export_presets.cfg. Linux: the bubblewrap sandbox hides $HOME, so the preset
    names the hash-checked copy inside the project (local_templates); macOS and Windows keep the host template."""
    return local_templates/TEMPLATES[target] if platforms.host(platform)=='linux' else host_template


def template_path(target):
    base=Path(str(platforms.templates_dir()))   # macOS ~/Library/..., Windows %APPDATA%\Godot\..., or HERMES64_TEMPLATES
    version=inspect_path(base/'version.txt')
    path=inspect_path(base/TEMPLATES[target])
    if not version.is_file() or version.read_text(encoding='utf-8').strip()!='4.6.2.stable' or not path.is_file():
        stub=_stub_template(target)
        if stub: return stub
        from .doctor import templates_help
        fail('export_template_missing',templates_help()+' (Missing target: %s.)' % target)
    if digest(path.read_bytes())!=TEMPLATE_HASHES[target]: fail('export_template_hash','Official target template hash mismatch')
    return path


def _stub_template(target):
    """Official player kept by `setup --fetch --templates` in the per-user cache (adventure_maker/stubs.py), else None."""
    from . import stubs
    try: return stubs.template(target)
    except ValueError as exc: fail('export_template_hash',str(exc))


def _stub_accepted(target, path):
    from . import stubs
    return stubs.accepted(target, path)


MODULE_POINTER='.maker/modules/current.json'


def _puzzle_api():
    if '.' in (__package__ or ''):
        from ..story.puzzle import api
        from ..story.puzzle.compiler import lowered_game
        from ..story.compiler import canonical
    else:
        from story.puzzle import api
        from story.puzzle.compiler import lowered_game
        from story.compiler import canonical
    return api, lowered_game, canonical


def build_source(service, project):
    """The build to export: {'spec','game','pointer'}. MERGE5: a STORY 1.3 (puzzle) build can only live behind the
    module data pointer (hermes64_module_check adopt=true; the 1.0-1.2 compile path does not accept 1.3 sources), so a
    1.3 game there is exported, with the same source/build check the module tools apply. Otherwise the current build."""
    if project.path(MODULE_POINTER).is_file():
        pointer=project.read_json(MODULE_POINTER)
        game=project.read_json(pointer['game']) if isinstance(pointer,dict) and isinstance(pointer.get('game'),str) else None
        if isinstance(game,dict) and game.get('contract_version')=='1.3.0':
            api,_,canonical=_puzzle_api()
            if pointer.get('scope')!='data_only' or canonical(api.compile_spec(project.read_json(pointer['spec'])))!=canonical(api.validate_game(game)):
                fail('export_source','STORY 1.3 module pointer source/build mismatch; re-run hermes64_module_check with adopt=true')
            return {'spec':pointer['spec'],'game':pointer['game'],'pointer':MODULE_POINTER}
    return dict(service.current(project),pointer='.maker/current.json')


def runtime_game(project, game_path, folder):
    """Project path of the game JSON the Godot runtime plays: the build itself, or for a STORY 1.3 build its embedded
    lowered STORY 1.2 build (validated, written to folder/lowered-game.json). Used by export and hermes64_build_assets."""
    game=project.read_json(game_path)
    if game.get('contract_version')!='1.3.0':
        return game_path
    api,lowered_game,_=_puzzle_api()
    low=lowered_game(api.validate_game(game))
    api.validate_game(low)
    project.write_json(folder+'/lowered-game.json',low)
    return folder+'/lowered-game.json'


def overlay_gate(c, project, game_path, folder, release):
    """L3: report what the overlay filled; in neutral mode prove the staged release carries none of the overlay's
    bytes (overlay files, overlay-baked textures), failing the export with overlay_leak otherwise."""
    from .overlay import leak_check, overlay_reference
    path=folder+'/slots-report.json'
    report=project.read_json(path) if project.path(path).is_file() else {'mode':getattr(c,'overlay_mode','apply')}
    if report.get('mode')=='neutral' and report.get('pack'):
        ref=overlay_reference(c,report['pack'],project.read_json(game_path))
        if ref is not None:
            report['leak_check']=leak_check(release,project.path('overlay'),ref)
            project.write_json(path,report)
            if not report['leak_check']['ok']:
                fail('overlay_leak','Neutral export contains overlay bytes: '+json.dumps(report['leak_check']['leaks'][:3]))
    return report


def stage(c, game_path, folder):
    """Prepare only trusted runtime source + verified referenced media; never copy a repository/PCK wholesale."""
    game=c.project.read_json(game_path)
    public_data(game)
    # Check all source binding policy flags before stage_runtime can add host paths.
    source_bindings=json.loads(c.shipped('bindings.json').read_text(encoding='utf-8'))
    public_data(source_bindings)
    manifest=json.loads(c.shipped('characters/manifest.json').read_text(encoding='utf-8'))
    public_data(manifest)
    puzzle=None
    if game.get('contract_version')=='1.3.0':
        # MERGE5: STORY 1.3 ships the lowered STORY 1.2 build the runtime plays, its puzzle.json sidecar (bound to both
        # build hashes) and the puzzle cue rows in audio.json: exactly what tools/puzzle_play.py gives the puzzle bot.
        from .puzzle_runtime import sidecar, audio_rows
        story13=game
        game_path=runtime_game(c.project,game_path,folder)   # validates the 1.3 build and its lowered 1.2 build
        game=c.project.read_json(game_path)
        puzzle=sidecar(story13,c.root)
    generated=c.prepare_runtime(game_path,folder)
    if puzzle is not None:
        sound=json.loads((generated/'audio.json').read_text(encoding='utf-8'))
        sound.update(audio_rows(c.root))
        (generated/'audio.json').write_bytes(json.dumps(sound,sort_keys=True).encode('utf-8'))
        (generated/'puzzle.json').write_bytes(json.dumps(puzzle,sort_keys=True).encode('utf-8'))
    output=c.project.path(folder+'/release'); output.mkdir()
    allowed_dirs=RELEASE_DIRS
    allowed_actor=('main.gd','assets.gd','bridge.gd','character.gd')
    for path in sorted(generated.rglob('*')):
        if not path.is_file(): continue
        rel=path.relative_to(generated)
        if rel.parts[0] in allowed_dirs or (rel.parts[0]=='actors' and rel.name in allowed_actor) or rel.as_posix()=='main.gd':
            if path.suffix not in ('.gd','.gdshader','.uid') and rel.as_posix() not in RELEASE_DATA: continue
            dest=output/rel; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(path.read_bytes())
    (output/'ship').mkdir()
    (output/'ship/main.gd').write_bytes(c.shipped('runtime/godot/playtest/release.gd').read_bytes())
    (output/'main.tscn').write_bytes('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://ship/main.gd" id="1"]\n[node name="Adventure" type="Node"]\nscript = ExtResource("1")\n'.encode('utf-8'))
    project=(generated/'project.godot').read_text(encoding='utf-8')
    project=project.replace('renderer/rendering_method="mobile"','renderer/rendering_method="gl_compatibility"').replace('renderer/rendering_method.mobile="mobile"','renderer/rendering_method.mobile="gl_compatibility"')
    project=user_dir_project(project,game['id'])
    project=project.replace('[rendering]', '[rendering]\ntextures/vram_compression/import_etc2_astc=true')
    # Same game, same bytes: the engine's text-to-binary conversion of main.tscn writes fresh node_ids on every
    # export (docs/INTEG5-EXPORT.md); keeping text resources as text makes repeated exports byte-identical.
    project+='\n[editor]\n\nexport/convert_text_resources_to_binary=false\n'
    (output/'project.godot').write_bytes(project.encode('utf-8'))
    bindings=json.loads((generated/'bindings.json').read_text(encoding='utf-8'))
    # Real characters must be members of the public frozen manifest, not merely self-declared public.
    records=manifest.get('characters',manifest.get('assets',[]))
    if isinstance(records,dict): records=list(records.values())
    admitted={row['sha256'] for row in records}
    closure=[]
    provenance_files={}
    def media(path, expected, suffix=None):
        path=inspect_path(Path(path))
        if not path.is_file(): fail('release_asset','Release requires every bound asset, not an absent fallback')
        if c.root not in path.parents and c.project.root not in path.parents: fail('release_asset','Asset outside trusted bundle/project')
        raw=path.read_bytes()
        if digest(raw)!=expected: fail('release_asset','Binding digest mismatch')
        scan_bytes(raw,'bound media')
        rel='media/'+expected+(suffix or path.suffix)
        dest=output/rel; dest.parent.mkdir(exist_ok=True)
        if not dest.exists():
            dest.write_bytes(raw)
            # Runtime GLTFDocument/Image/AudioStreamWAV need original bytes, not importer remaps.
            dest.with_name(dest.name+'.import').write_bytes('[remap]\nimporter="keep"\n'.encode('utf-8'))
            closure.append({'path':rel,'sha256':expected,'bytes':len(raw)})
        return 'res://'+rel
    def bind(row, actor=False, licence_scope=True):
        row=copy.deepcopy(row)
        original=row.pop('path',None)
        row.pop('glb',None)
        if actor and not row.get('placeholder') and row['sha256'] not in admitted:
            fail('release_private','Character hash not admitted by public manifest')
        bound=inspect_path(Path(original))
        project_asset=c.project.root in bound.parents
        rel=bound.relative_to(c.project.root).as_posix() if project_asset else ''
        manifest=c.project.path('assets/PROVENANCE.json').is_file()
        required=row.get('licence_required',False) or (licence_scope and (rel.startswith(('assets/generated/','assets/imported/','assets/kit/')) or (manifest and not actor)))
        if required:
            if project_asset: provenance_id=rel
            elif c.root in bound.parents and not actor: provenance_id='bundle/'+bound.relative_to(c.root).as_posix()
            else: fail('release_licence','Required asset provenance is outside project/bundle')
            from .provenance import require_export
            try: require_export(c.project.root,[provenance_id],bundle_root=c.root)
            except ValueError as exc: fail('release_licence',str(exc))
            provenance_files[provenance_id]='media/'+row['sha256']+bound.suffix
        row['path']=media(original,row['sha256'])
        if 'fallback' in row: row['fallback']=bind(row['fallback'],licence_scope=licence_scope and not actor)
        public_data(row)
        return row
    bindings['assets']={k:bind(row) for k,row in bindings['assets'].items()}
    bindings['characters']=[bind(row,True) for row in bindings['characters'] if any(row['body_id']==ch['body_id'] and row['base_rig_id']==ch['base_rig_id'] and row['params']==ch['params'] for ch in game['characters'])]
    # Combat art (module games only): enemy models for the staged kit pack and the weapon of each bound
    # character's pack, as hash-checked media like every other bound asset.
    combat=None
    if game.get('contract_version')=='1.2.0' and (generated/'combat.json').is_file():
        combat=json.loads((generated/'combat.json').read_text(encoding='utf-8'))
        packs={row.get('character_pack') for row in bindings['characters']}
        combat['enemies']={k:dict(row,path=media(row['path'],row['sha256'])) for k,row in combat['enemies'].items()}
        combat['weapons']={k:dict(row,path=media(row['path'],row['sha256'])) for k,row in combat['weapons'].items() if k in packs}
    theme=json.loads((generated/'theme.json').read_text(encoding='utf-8'))
    env=inspect_path(Path(theme.pop('env_root')))
    if c.root not in env.parents: fail('release_asset','Environment outside bundle')
    (output/'env').mkdir()
    for p in sorted(env.glob('*.png')):
        inspect_path(p); raw=p.read_bytes(); scan_bytes(raw,p.name)
        (output/'env'/p.name).write_bytes(raw)
        (output/'env'/(p.name+'.import')).write_bytes('[remap]\nimporter="keep"\n'.encode('utf-8'))
    theme['env_root']='res://env'
    from .overlay import release_slots; release_slots(theme,media)   # L3: baked texture slot PNGs as release media
    audio=json.loads((generated/'audio.json').read_text(encoding='utf-8'))
    for row in audio.values(): row['path']=media(row['path'],row['sha256'])
    for name,value in [('game',game),('bindings',bindings),('theme',theme),('audio',audio)]+([('combat',combat)] if combat is not None else [])+([('puzzle',puzzle)] if puzzle is not None else []):
        public_data(value); (output/(name+'.json')).write_bytes(json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8'))
    (output/'licenses').mkdir()
    for name,expected in LICENSE_HASHES.items():
        raw=c.shipped('licenses/godot-4.6.2/'+name).read_bytes()
        if digest(raw)!=expected: fail('license_hash','Godot legal notice hash mismatch')
        (output/'licenses'/('GODOT_'+name)).write_bytes(raw)
    (output/'licenses/HERMES64_LICENSE.txt').write_bytes(c.shipped('LICENSE').read_bytes())
    if provenance_files:
        from .provenance import prepare_export
        prepare_export(c.project.root,provenance_files,str(output.relative_to(c.project.root)),bundle_root=c.root)
    rows=scan_tree(output)
    record={'game_hash':game['game_hash'],'files':rows,'media':closure}
    if puzzle is not None:
        record['puzzle_game_hash']=puzzle['game_hash']   # the STORY 1.3 build; game_hash is its lowered 1.2 build
    c.project.write_json(folder+'/closure.json',record)
    return output


def preset(target, template):
    platform={'web':'Web','macos':'macOS','windows':'Windows Desktop'}[target]
    common='[preset.0]\nname="Ship"\nplatform='+json.dumps(platform)+'\nrunnable=true\nexport_filter="all_resources"\ninclude_filter="*.json,*.glb,*.png,*.wav,*.txt"\nexclude_filter=""\nscript_export_mode=0\n\n[preset.0.options]\ncustom_template/release='+json.dumps(str(template))+'\n'
    if target=='web': return common+'variant/extensions_support=false\nvariant/thread_support=false\nvram_texture_compression/for_desktop=true\nvram_texture_compression/for_mobile=false\nhtml/export_icon=false\nhtml/experimental_virtual_keyboard=false\nprogressive_web_app/enabled=false\n'
    if target=='macos': return common+'binary_format/architecture="universal"\napplication/bundle_identifier="org.hermes64.adventure"\napplication/app_category="public.app-category.games"\ncodesign/codesign=0\nnotarization/notarization=0\n'
    return common+'binary_format/architecture="x86_64"\nbinary_format/embed_pck=false\ncodesign/enable=false\napplication/modify_resources=false\ndebug/export_console_wrapper=0\n'


def qualify(service, project, component, current, folder, module_preview=False):
    game = project.read_json(current['game'])
    if game.get('contract_version') == '1.3.0':
        # STORY 1.3: the puzzle checker (story.puzzle.analysis via the version facade), in process like the module
        # tools; only a proved build exports (no conditional preview path for puzzles).
        api,_,_ = _puzzle_api()
        proof = api.check_game(api.validate_game(game))
        project.write_json(folder+'/proof.json', proof)
        if proof.get('status') != 'proved':
            fail('export_unproved','Export of a STORY 1.3 game requires a current proved puzzle build (status %s); see %s/proof.json' % (proof.get('status'), folder))
        return proof, None
    proof = component.check(current['game'], folder+'/proof.json')
    if proof['status'] == 'proved': return proof, None
    if not module_preview or game.get('contract_version') != '1.2.0' or proof['status'] != 'conditional':
        fail('export_unproved','Export requires a current proved story, or explicit module_preview with fresh physical qualification')
    from .module_playtest import physical
    report = physical(project,service.settings,current['game'],proof,folder+'/physical',False)
    required = [m['id'] for m in game['gameplay']['modules'] if m['id'] in ('combat','course','regions')]
    if report['verdict'] != 'PLAYABLE' or not report.get('completed') or not required or not all(m in report.get('modules_tested',[]) for m in required):
        fail('export_module_unplayed','Conditional preview requires a complete current real-input module bot; see '+folder+'/physical/report.json')
    return proof, report


def run(service, project, args):
    targets=args.get('targets',['web'])
    if len(targets)!=len(set(targets)): fail('arguments','Duplicate export target')
    if 'macos' in targets and platforms.host()!='darwin':
        fail('export_target','The macos target needs a Mac (local ad-hoc signing with codesign); export web and windows here, '
             'or export macos on a Mac. Nothing was exported.')
    templates={t:template_path(t) for t in targets}
    folder=service.folder(project,'export'); c=Components(service.settings,project)
    c.overlay_mode=args.get('overlay','apply')   # L3: 'neutral' ignores overlay/ and proves no overlay byte ships
    current=build_source(service,project)
    proof, physical=qualify(service,project,c,current,folder,args.get('module_preview',False))
    release=stage(c,current['game'],folder)
    overlay_gate(c,project,current['game'],folder,release)
    exe=locate('godot',service.settings.get('godot_path',''))
    if platforms.host()=='darwin':
        # Supported self-contained editor mode. Preserve the signed app bundle;
        # copying just its Mach-O breaks the Info.plist seal and macOS kills it.
        source_app=Path(exe).parents[2]
        if source_app.suffix!='.app': fail('engine_bundle','macOS export needs the existing official Godot.app bundle')
        local_app=project.path('.maker/local/export-editor/Godot.app')
        if not local_app.exists():
            local_app.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(source_app,local_app)
        local_engine=local_app/'Contents/MacOS/Godot'
    else:
        # Windows/Linux: Godot is one executable; self-contained mode reads _sc_ and editor_data/ beside it.
        local_app=project.path('.maker/local/export-editor/'+platforms.exe_name('godot'))
        if not local_app.exists():
            local_app.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(exe,local_app)
        local_engine=local_app
    if digest(local_engine.read_bytes())!=digest(Path(exe).read_bytes()): fail('engine_hash','Project-local editor copy differs; use a new project')
    (local_app.parent/'_sc_').touch(exist_ok=True)
    # macOS preset validation checks the shared zip even with custom_template.
    local_templates=local_app.parent/'editor_data/export_templates/4.6.2.stable'
    local_templates.mkdir(parents=True,exist_ok=True)
    for target,template in templates.items():
        dest=local_templates/TEMPLATES[target]
        if not dest.is_file(): dest.write_bytes(template.read_bytes())
        if digest(dest.read_bytes())!=TEMPLATE_HASHES[target] and not _stub_accepted(target,dest): fail('export_template_hash','Local template cache differs')
    (local_templates/'version.txt').write_bytes('4.6.2.stable\n'.encode('utf-8'))
    exe=str(local_engine)
    version=c.runner.run(silent_godot([exe,'--version']),project.root)
    project.write_json(folder+'/engine-version.process.json',version)
    if not version['stdout'].startswith('4.6.2.stable.official.'): fail('engine_version','Export requires official Godot 4.6.2')
    share=project.path(folder+'/share'); share.mkdir()
    rows=[]
    for target in targets:
        (release/'export_presets.cfg').write_bytes(preset(target,preset_template(target,templates[target],local_templates)).encode('utf-8'))
        dest=share/target; dest.mkdir()
        artifact=dest/({'web':'index.html','macos':'Adventure.zip','windows':'Adventure.exe'}[target])
        # Explicit import pass makes export behavior independent of editor history.
        for phase,tail in [('import',['--editor','--import']),('export',['--export-release','Ship',str(artifact)])]:
            argv=silent_godot([exe,'--headless','--path',str(release)]+tail)
            proc=c.runner.run(argv,project.root,timeout=180)
            project.write_json(folder+'/'+target+'-'+phase+'.process.json',dict(proc,argv=argv))
            if proc['returncode'] or 'SCRIPT ERROR' in proc['stderr'] or 'ERROR:' in proc['stderr']:
                fail('export_failed',target+' '+phase+' failed; see '+folder+'/'+target+'-'+phase+'.process.json: '+proc['stderr'][-1200:])
        if not artifact.is_file(): fail('export_failed','Godot produced no '+target+' artifact')
        if target=='macos':
            with zipfile.ZipFile(artifact) as z:
                for info in z.infolist():
                    if info.is_dir(): continue
                    rel=Path(info.filename)
                    if rel.is_absolute() or '..' in rel.parts: fail('export_archive','Unsafe app archive')
                    p=dest/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(z.read(info))
                    if (info.external_attr>>16)&0o111: p.chmod(0o755)
            artifact.unlink()
        shutil.copytree(release/'licenses',dest/'licenses')
        (dest/'README.txt').write_bytes(('Hermes64 local export. Keyboard: WASD/arrows move (Shift run; Alt precision); E act/confirm; Q or Backspace cancel; hold Z Focus; Space dodge in combat/courses (confirm in menus); Tab action menu; I inventory; Esc pause/settings; F5/F9 quick save/load; hold R retry from checkpoint; C optional camera.\n'+
            ('Serve this directory over localhost HTTP (python3 -m http.server --bind 127.0.0.1; Windows: py -m http.server --bind 127.0.0.1). Open index.html; WebGL2 required. No threads/PWA/service worker. Browser saves use local IndexedDB.\n' if target=='web' else 'Saves are local Godot user data, under Hermes64/game-id.\n')+
            ('Windows: unsigned, so SmartScreen may warn: More info, then Run anyway. Saves and the log (logs\\godot.log): %APPDATA%\\Hermes64\\<game id>.\n' if target=='windows' else '')+
            ('Windows recipient execution UNVERIFIED on this Mac.\n' if target=='windows' and platforms.host()!='win32' else '')+
            ('Locally ad-hoc signed, not Developer ID signed/notarized: recipient Gatekeeper acceptance is NOT verified.\n' if target=='macos' else '')+
            'No upload, telemetry or external service. Engine and third-party notices are in licenses/. Human fun and other machines are unverified.\n').encode('utf-8'))
        if target=='web':
            for suffix in ('.js','.wasm'):
                payload=artifact.with_suffix(suffix)
                payload.write_bytes(portable_web_vfs(payload.read_bytes()))
            (dest/'licenses/WEB_VFS_MODIFICATION.txt').write_bytes('Generated Godot 4.6.2 web payload modification: virtual /home/web_user relocated to /data/web_user in JS/WASM with equal-length byte replacements. No host path was present in that upstream virtual default. Engine source license remains MIT.\n'.replace('/home/web_user','Emscripten HOME').encode('utf-8'))
            text=artifact.read_text(encoding='utf-8').replace('</head>','<link rel="icon" href="data:,"></head>')
            text=text.replace('</body>','<a style="position:fixed;bottom:4px;right:4px;color:white" href="licenses/GODOT_COPYRIGHT.txt">Engine &amp; third-party notices</a></body>'); artifact.write_bytes(text.encode('utf-8'))
        if target=='windows':
            artifact.write_bytes(native_diagnostic_paths(artifact.read_bytes()))
            (dest/'licenses/NATIVE_MODIFICATION.txt').write_bytes('Official Godot 4.6.2 Rust diagnostic source-root prefix relocated to /data/runner/.cargo/ with equal-length replacements. Windows executable is unsigned and execution UNVERIFIED. Engine remains MIT.\n'.encode('utf-8'))
        verified='not_run'
        entry=artifact.relative_to(share).as_posix()
        if target=='windows' and platforms.host()=='win32':
            # On Windows the exported game itself can be booted headless, like the macOS smoke below.
            argv=[str(artifact),'--headless','--','--quit_after=2']
            proc=c.runner.run(argv,project.root,timeout=60)
            project.write_json(folder+'/windows-smoke.process.json',dict(proc,argv=argv))
            verified='passed' if proc['returncode']==0 and 'BOOT game=' in proc['stdout'] else 'failed'
            if verified!='passed': fail('export_smoke','Windows export smoke failed; inspect '+folder+'/windows-smoke.process.json')
        if target=='macos':
            binaries=list(dest.glob('*.app/Contents/MacOS/*'))
            if len(binaries)!=1: fail('export_failed','Unexpected macOS executable roster')
            binaries[0].write_bytes(native_diagnostic_paths(binaries[0].read_bytes()))
            app=binaries[0].parents[2]
            entry=app.relative_to(share).as_posix()
            signing=c.runner.run(['/usr/bin/codesign','--force','--sign','-','--timestamp=none',str(app)],project.root)
            project.write_json(folder+'/macos-adhoc.process.json',signing)
            if signing['returncode']: fail('export_sign','Local ad-hoc signing failed; no identity/notarization requested')
            (dest/'licenses/NATIVE_MODIFICATION.txt').write_bytes('Official Godot 4.6.2 Rust diagnostic source-root prefix relocated to /build/runner/.cargo/ with equal-length replacements. Local ad-hoc signature only; not Developer ID signed or notarized. Engine remains MIT.\n'.encode('utf-8'))
            argv=[str(binaries[0]),'--headless','--','--quit_after=2']
            proc=c.runner.run(argv,project.root,timeout=30)
            project.write_json(folder+'/macos-smoke.process.json',dict(proc,argv=argv))
            verified='passed' if proc['returncode']==0 and 'BOOT game=' in proc['stdout'] and not proc['stderr'] else 'failed'
            if verified!='passed': fail('export_smoke','macOS export smoke failed; inspect '+folder+'/macos-smoke.process.json')
        files=scan_tree(dest)
        (dest/'FILES.json').write_bytes(json.dumps(files,sort_keys=True,indent=2).encode('utf-8'))
        zipped=share/(target+'.zip'); zip_tree(dest,zipped)
        rows.append({'target':target,'bytes':sum(r['bytes'] for r in files),'files':len(files),'zip_bytes':zipped.stat().st_size,'zip_sha256':digest(zipped.read_bytes()),'verification':verified if target!='windows' or verified=='passed' else 'UNVERIFIED: not executed on Windows','entry':entry})
    (share/'README.txt').write_bytes('Hermes64 LOCAL share bundle. Nothing was uploaded. See target README files, licenses, and deterministic FILES.json manifests. Windows execution and other machines unverified. Engine export bytes can vary; file inventories/hashes describe this exact build.\n'.encode('utf-8'))
    if physical is not None:
        (share/'CONDITIONAL-PREVIEW.txt').write_bytes('LOCAL MODULE PREVIEW ONLY. Logical progression is conditional on named skill assumptions. A fresh real-input native bot completed this exact game; this is not human balance, rendered performance, art approval or public-release clearance. Combat uses the imported combat-art clips and enemy models (no art approval claimed).\n'.encode('utf-8'))
    all_files=scan_tree(share)
    (share/'FILES.json').write_bytes(json.dumps(all_files,sort_keys=True,indent=2).encode('utf-8'))
    zip_tree(share,project.path(folder+'/share.zip'))
    report={'ok':True,'status':'exported_local_only','targets':rows,'share_path':folder+'/share','zip_path':folder+'/share.zip','report_path':folder+'/report.json','bytes':sum(r['bytes'] for r in all_files),'privacy_scan':'passed: explicit portable closure + nested-archive/home-path scan','proof_status':proof['status'],'network':'none; no upload','scope':'Build success is not browser/recipient execution; see per-target verification.'}
    report['module_preview'] = physical is not None
    report['physical_report'] = folder+'/physical/report.json' if physical is not None else None
    report['build_pointer'] = current['pointer']
    if project.read_json(current['game']).get('contract_version') == '1.3.0':
        report['story_version'] = '1.3.0'
        report['puzzle'] = 'puzzle.json sidecar + puzzle cue rows staged (lowered STORY 1.2 build plays)'
    project.write_json(folder+'/report.json',report)
    return report
