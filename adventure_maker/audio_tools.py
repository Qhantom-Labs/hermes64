"""Offline hermes64_audio tool. No playback, downloads or network.

The catalog/render/bank actions never spawn a process. Only the AUDIOPIPE import action runs a local ffmpeg
(configured ffmpeg_path, bundled tools/bin/<platform>/ffmpeg, or PATH; see adventure_maker/audio_import.py).

Registration is separate to keep Main's plugin merge to two entrypoint lines and
one manifest entry. Each handler reads config per call; exports require an
existing managed project and its cooperative operation lock.
"""
import copy
import json
from pathlib import Path
from .audio_schemas import AUDIO_SCHEMA
from .schemas import validate
from .safety import Fault, Project, encode, fail
from . import audio_dsp as d
from . import audio_catalog as c
from . import audio_bank as b

ACTIONS = {
    'list': (('action','category','tags','limit','offset'),()),
    'search': (('action','query','category','tags','limit','offset'),()),
    'preview': (('action','project','export','id','transform'),('project','export','id')),
    'variation': (('action','project','export','id','seed','ordinal','transform'),('project','export','id','seed','ordinal')),
    'music': (('action','project','export','music','transform'),('project','export','music')),
    'voice': (('action','project','export','voice','text','transform'),('project','export','text')),
    'bank': (('action','project','export','palette','profile_path','max_bytes','max_assets'),('project','export')),
    'validate': (('action','project','export'),('project','export')),
    'import': (('action','project','sources','items','kind','options','replace'),('project',)),
    'assign': (('action','project','slots_json'),('project','slots_json')),
    'imported': (('action','project'),('project',))}
IMPORT_DIR = 'audio/import'
SLOTS_FILE = 'audio/slots.json'


def _generated(identity, category, recipe, loop):
    return {'id':identity,'category':category,'purpose':'User-parameterized original '+category,
            'tags':[category,'generated','n64'],'loop':loop,'recipe':recipe,'seed':recipe['params']['seed'],
            'licence':'CC0-1.0','style_tags':['general','n64'],
            'variation_pool':{'id':identity+'.pool','size':4,'seed':recipe['params']['seed'],
                              'pitch_cents':[-32,28,-18,41],'policy':'seeded-shuffle-no-immediate-repeat'}}


class AudioService:
    def __init__(self,settings=None):
        self.settings = dict(settings or {})

    def handle(self,args,**kwargs):
        try:
            validate(args,AUDIO_SCHEMA['parameters'])
            encode(args)
            action = args['action']
            allowed,required = ACTIONS[action]
            if any(k not in allowed for k in args) or any(k not in args for k in required):
                fail('arguments','Missing required or inapplicable action argument')
            configured = self.settings.get('bundle_root')
            if configured and Path(configured).absolute()!=c.ROOT:
                fail('configuration','Audio tool must use its own trusted bundle_root; no external recipe loading')
            if action in ('list','search'):
                result = c.search(query=args.get('query',''),tags=args.get('tags',()),
                    category=args.get('category'),limit=args.get('limit',20),offset=args.get('offset',0))
                fields = ('id','category','purpose','tags','duration','loop','style_tags','licence',
                          'peak','loudness_rms_dbfs','review_status','variation_pool')
                result['assets'] = [{k:r[k] for k in fields if k in r} for r in result['assets']]
                result['ok'] = True
                return json.dumps(result,allow_nan=False)
            if not self.settings.get('projects_root'):
                fail('configuration','Choose an existing projects_root and scaffold the project first')
            project = Project(self.settings['projects_root'],args['project'])
            with project.lock():
                result = self.dispatch(project,args)
            return json.dumps(result,allow_nan=False)
        except (Fault,d.AudioError) as exc:
            return json.dumps({'ok':False,'error':{'code':exc.code,'message':str(exc)[:2000]}})
        except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
            return json.dumps({'ok':False,'error':{'code':'local_error','message':type(exc).__name__+': '+str(exc)[:1000]}})

    def dispatch(self,project,args):
        action = args['action']
        if action in ('import','assign','imported'):
            return self.byo(project,args)
        if action=='validate':
            return b.validate_bank(project,args['export'])
        effect = copy.deepcopy(args.get('transform',{}))
        c.transform(effect)
        palette_id = None
        if action in ('preview','variation'):
            row = c.get(args['id'])
            if action=='variation':
                row = c.variation(row,args['ordinal'],args['seed'])
            rows = [row]
            bindings = {'preview':{'ids':[row['id']],'gain':.5}}
        elif action=='music':
            from . import audio_music
            params = audio_music.resolve(args['music'])
            row = _generated('h64.generated.music','music',{'engine':'music','params':params},True)
            rows, bindings = [row], {'music':{'ids':[row['id']],'gain':.3}}
        elif action=='voice':
            from . import audio_voice
            params = dict(args.get('voice',{}))
            params.setdefault('seed',64)
            audio_voice.resolve(params)
            row = _generated('h64.generated.voice','voices',{'engine':'voice','params':params,'text':args['text']},False)
            rows, bindings = [row], {'dialogue':{'ids':[row['id']],'gain':.4}}
        else:
            if 'profile_path' in args and 'palette' in args:
                fail('arguments','Choose profile_path OR palette, not both')
            palette = (b.resolve_profile(project.read_json(args['profile_path'])) if 'profile_path' in args
                       else b.select_palette(args.get('palette','neutral')))
            palette_id, effect, bindings = palette['id'],palette['transform'],palette['bindings']
            identities = sorted(dict.fromkeys(i for binding in bindings.values() for i in binding['ids']))
            rows = [c.get(i) for i in identities]
        return b.export_bank(project,args['export'],rows,bindings,transform=effect,
            max_bytes=args.get('max_bytes',b.MAX_BYTES),max_assets=args.get('max_assets',b.MAX_ASSETS),palette_id=palette_id)


    def byo(self,project,args):
        """Bring-your-own audio (AUDIOPIPE). Files land in audio/import/, slot assignments in audio/slots.json;
        the next build stages them into runtime audio.json rows (assets_v3.runtime_snapshot)."""
        from . import audio_import as ai
        action = args['action']
        folder = project.path(IMPORT_DIR)
        if action=='import':
            if 'sources' not in args and 'items' not in args:
                fail('arguments','import needs sources (files/folders) and/or items')
            ffmpeg = ai.find_ffmpeg(self.settings.get('ffmpeg_path',''),c.ROOT)
            options = dict(args.get('options',{}))
            budget = options.pop('max_total_bytes',ai.DEFAULT_TOTAL_BYTES)
            folder.mkdir(parents=True,exist_ok=True)
            manifest,new = ai.import_audio(folder,args.get('sources',[]),ffmpeg,kind=args.get('kind','auto'),
                items=args.get('items'),options=options,replace=args.get('replace',False),base=project.root,
                max_total_bytes=budget)
            from .premise_apply import assign_imported   # GAPS2 G3: a story file's audio block assigns itself
            return dict(summary(manifest,new),ok=True,manifest=IMPORT_DIR+'/manifest.json',
                        next='hermes64_audio action=assign with slots, then rebuild/open the game',
                        **assign_imported(project,manifest,SLOTS_FILE))
        if not project.path(IMPORT_DIR+'/manifest.json').is_file():
            fail('not_imported','Nothing imported yet: run hermes64_audio action=import first')
        manifest,problems = ai.verify(folder)
        if action=='assign':
            if problems:
                fail('asset_integrity','Imported audio changed on disk: '+'; '.join(problems[:5]))
            from .safety import strict_json
            slots = ai.validate_slots(strict_json(args['slots_json'].encode('utf-8')),manifest['assets'])
            project.write_json(SLOTS_FILE,slots)
            return {'ok':True,'slots':SLOTS_FILE,'assigned':slots,
                    'runtime_rows':sorted(ai.runtime_rows(slots,manifest['assets'],folder))}
        slots = project.read_json(SLOTS_FILE) if project.path(SLOTS_FILE).is_file() else None
        return dict(summary(manifest,[]),ok=not problems,problems=problems,slots=slots)


def summary(manifest,new):
    rows = []
    for ident,a in manifest['assets'].items():
        rows.append({'id':ident,'kind':a['kind'],'seconds':a['seconds'],'bytes':a['bytes'],
                     'format':'%d Hz %s' % (a['sample_rate'],'mono' if a['channels']==1 else 'stereo'),
                     'output_lufs':a['loudness']['output_lufs'],
                     'seam':(a['loop'] or {}).get('seam'),'warnings':a['warnings'],'new':ident in new})
    return {'assets':rows,'budget':manifest['budget'],'ffmpeg':manifest['ffmpeg']}


def register_audio_tools(ctx):
    from .plugin_settings import plugin_settings
    from . import wire
    def handler(args,**kwargs):
        settings = plugin_settings(ctx,('projects_root','bundle_root','ffmpeg_path'))
        return AudioService(settings).handle(args,**kwargs)
    # Compact advertised copy; AudioService.handle validates against the full AUDIO_SCHEMA.
    wire.register(ctx,'hermes64_audio',AUDIO_SCHEMA,handler,lambda:True)
