"""Confined export banks, native style/pack adapters and read-back validation."""
import copy
import hashlib
import json
import re
from . import audio_catalog as c
from . import audio_dsp as d
from .safety import encode, fail, relative

MAX_BYTES = 32*1024*1024
MAX_ASSETS = 64
METRICS = ('duration','frames','sample_rate','peak','rms','dc','seam',
           'loudness_rms_dbfs','loudness_method','bytes','sha256')


def palettes():
    return json.loads((d.DATA/'palettes.json').read_text())


def check_palette(palette):
    d.require(isinstance(palette,dict) and sorted(palette)==['bindings','format','id','transform']
              and type(palette['format']) is int and palette['format']==2,
              'palette','expected format/id/transform/bindings')
    d.require(isinstance(palette['id'],str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',palette['id']),
              'palette','palette slug')
    c.transform(palette['transform'])
    # Validate instrument values even if this palette currently selects no music.
    if palette['transform'].get('instruments'):
        from .audio_music import resolve
        resolve({'instruments':palette['transform']['instruments']})
    bindings = palette['bindings']
    d.require(isinstance(bindings,dict) and 1 <= len(bindings) <= 64,'palette','binding count')
    for event,binding in bindings.items():
        d.require(isinstance(event,str) and re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}',event), 'palette','event ID')
        d.require(isinstance(binding,dict) and sorted(binding)==['gain','ids'], 'palette','binding fields')
        d.number(binding['gain'],0,1,'binding gain')
        d.require(isinstance(binding['ids'],list) and 1 <= len(binding['ids']) <= 16,
                  'palette','binding IDs')
        for identity in binding['ids']:
            c.get(identity)
    return copy.deepcopy(palette)


def resolve_profile(document):
    """Accept audio-only v2, existing style sections.audio, or pack sound_palette.

    This resolves AUDIO ONLY, not visual profile inheritance or visual validity.
    Cue adapters and transformations are data in palettes.json, never theme code.
    """
    d.require(isinstance(document,dict),'palette','profile object')
    if 'audio_palette' in document:
        return check_palette(document['audio_palette'])
    if document.get('format')==2 and 'bindings' in document:
        return check_palette(document)
    if 'sound_palette' in document:
        paths = {('audio/'+r['file']):r['id'] for r in c.all_records() if 'file' in r}
        bindings = {}
        d.require(isinstance(document['sound_palette'],dict),'palette','pack sound_palette object')
        for event,value in document['sound_palette'].items():
            d.require(isinstance(value,str) and value in paths,'palette','unknown canonical audio path')
            bindings[event] = {'ids':[paths[value]],'gain':.5}
        return check_palette({'format':2,'id':'pack_audio','transform':{},'bindings':bindings})
    sections = document.get('sections',{})
    d.require(isinstance(sections,dict),'palette','profile sections object')
    audio = sections.get('audio')
    d.require(isinstance(audio,dict) and isinstance(audio.get('cues'),dict), 'palette', 'profile needs resolved audio cues')
    mapping = palettes()['style_cues']
    bindings, transforms = {}, {}
    for event,cue in audio['cues'].items():
        d.require(isinstance(cue,dict) and all(k in cue for k in ('generator','preset','gain_db','loop')),
                  'palette','style cue fields')
        key = str(cue['generator'])+':'+str(cue['preset'])
        d.require(key in mapping,'palette','unknown style cue: '+key)
        mapped = mapping[key]
        row = c.get(mapped['id'])
        d.require(type(cue['loop']) is bool and row['loop']==cue['loop'],'palette','cue loop mismatch')
        d.number(cue['gain_db'],-60,0,'gain_db')
        bindings[event] = {'ids':[mapped['id']],'gain':10**(cue['gain_db']/20)}
        for k,v in mapped['transform'].items():
            d.require(k not in transforms or transforms[k]==v,'palette','conflicting audio transforms')
            transforms[k] = v
    return check_palette({'format':2,'id':'style_audio','transform':transforms,'bindings':bindings})


def select_palette(name):
    domain = palettes()['palettes']
    d.require(isinstance(name,str) and name in domain,'palette','unknown palette')
    return check_palette(domain[name])


def effective_transform(row, transform):
    value = copy.deepcopy(transform)
    if row['recipe']['engine']!='music':
        value.pop('instruments',None)
    return value


def export_bank(project, export, rows, bindings, transform=None, max_bytes=MAX_BYTES,
                max_assets=MAX_ASSETS, palette_id=None):
    d.uint(max_bytes,'max_bytes',MAX_BYTES); d.uint(max_assets,'max_assets',MAX_ASSETS)
    d.require(len(rows) <= max_assets and len(rows)>0,'budget','bank asset count')
    relative(export)
    d.require(re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',export),'path','export slug')
    directory = 'exports/audio/'+export
    if project.path(directory).exists():
        fail('exists','Audio export already exists; choose a new export slug')
    # Rendering and all domain validation finish before the first output write.
    payloads, assets, artifacts, total = {}, [], [], 0
    for original in rows:
        row = copy.deepcopy(original)
        identity = row['id']
        d.require(re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}',identity),'catalog','asset ID')
        d.require(row.get('licence')=='CC0-1.0','licence','generated CC0 only')
        effect = effective_transform(row,transform or {})
        rendered = c.render(row,effect)
        primary = next(name for name,raw in rendered['files'].items() if raw==rendered['wav'])
        metrics = d.validate_wav(rendered['wav'],loop=row['loop'])
        for name,raw in sorted(rendered['files'].items()):
            filename = identity+'/'+name
            relative(filename)
            d.require(filename not in payloads,'catalog','duplicate output')
            total += len(raw)
            d.require(total <= max_bytes,'budget','export payload bytes exceeded')
            payloads[filename] = raw
            artifact = {'file':filename,'asset_id':identity,'licence':'CC0-1.0',
                        'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            if name.endswith('.wav'):
                artifact['metrics'] = d.validate_wav(raw,loop=row['loop'],sparse=name.startswith('stem-'))
            artifacts.append(artifact)
        row.update(metrics)
        row.update(file=identity+'/'+primary,transform=effect,review_status=d.REVIEW)
        assets.append(row)
    d.validate_collection(assets,max_bytes=max_bytes,max_assets=max_assets)
    manifest = {'format':2,'generator_version':'2.0.0','review_status':d.REVIEW,
                'palette':palette_id,'assets':assets,'artifacts':artifacts,'bindings':bindings,
                'budgets':{'max_bytes':max_bytes,'max_assets':max_assets},'payload_bytes':total,
                'notes':['RMS approximation is not LUFS.','Source-file peak is not runtime mix headroom.',
                         'Music stems/layers share a clock; crossfade, do not restart.']}
    encoded = encode(manifest)
    project.path(directory).mkdir(parents=True,exist_ok=False)
    for filename,raw in payloads.items():
        project.write_bytes(directory+'/'+filename,raw)
    project.write_bytes(directory+'/bank.json',encoded)
    # Exact output readback is part of successful export; deterministic rerender
    # is performed by validate, rather than claiming it from a single render.
    report = validate_bank(project,export,determinism=False)
    return {'ok':True,'status':'machine_checked_not_human_approved','directory':directory,
            'manifest':directory+'/bank.json','assets':len(assets),'payload_bytes':total,
            'readback':report,'next':'validate for independent rerender; then listen quietly'}


def _read(project,directory,filename):
    relative(filename)
    path = project.path(directory+'/'+filename)
    d.require(path.is_file() and path.stat().st_size <= MAX_BYTES,'budget','missing/oversized artifact')
    with path.open('rb') as f:
        raw = f.read(MAX_BYTES+1)
    d.require(len(raw)<=MAX_BYTES,'budget','oversized artifact')
    return raw


def validate_bank(project,export,determinism=True):
    relative(export)
    d.require(re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',export),'path','export slug')
    directory = 'exports/audio/'+export
    bank = project.read_json(directory+'/bank.json')
    d.require(isinstance(bank,dict) and bank.get('format')==2,'catalog','bank format')
    rows, artifacts = bank.get('assets'), bank.get('artifacts')
    d.require(isinstance(rows,list) and 1 <= len(rows)<=MAX_ASSETS and isinstance(artifacts,list)
              and 1<=len(artifacts)<=MAX_ASSETS*11,'catalog','asset/artifact inventory')
    assert isinstance(rows,list) and isinstance(artifacts,list)  # narrowed after the checked gate
    d.require(all(isinstance(r,dict) and type(r.get('loop')) is bool for r in rows)
              and all(isinstance(a,dict) for a in artifacts), 'catalog','asset/artifact objects and loop booleans')
    d.require(isinstance(bank.get('budgets'),dict) and isinstance(bank.get('bindings'),dict),
              'catalog','budget and binding objects')
    budgets = bank['budgets']
    d.uint(budgets['max_bytes'],'max_bytes',MAX_BYTES); d.uint(budgets['max_assets'],'max_assets',MAX_ASSETS)
    d.require(len(rows)<=budgets['max_assets'],'budget','asset budget')
    for row in rows:
        d.require(row.get('licence')=='CC0-1.0','licence','CC0 required')
        relative(row['file'])
    ids = [r['id'] for r in rows]
    d.require(len(ids)==len(dict.fromkeys(ids)),'catalog','duplicate bank id')
    for binding in bank['bindings'].values():
        d.require(isinstance(binding,dict) and isinstance(binding.get('ids'),list)
                  and bool(binding['ids']) and all(i in ids for i in binding['ids']),
                  'catalog','unresolved event binding')
        d.number(binding['gain'],0,1,'binding gain')
    files, total = {}, 0
    for artifact in artifacts:
        filename = artifact['file']
        relative(filename)
        d.require(filename not in files and artifact['asset_id'] in ids,'catalog','artifact inventory')
        d.require(filename.startswith(artifact['asset_id']+'/'),'path','artifact prefix')
        raw = _read(project,directory,filename)
        total += len(raw)
        d.require(total <= budgets['max_bytes'],'budget','payload byte budget')
        d.require(artifact.get('licence')=='CC0-1.0','licence','artifact licence')
        row = next(r for r in rows if r['id']==artifact['asset_id'])
        if filename.endswith('.wav'):
            metrics = d.validate_wav(raw,loop=row['loop'],sparse=filename.split('/')[-1].startswith('stem-'))
            d.require(metrics==artifact.get('metrics'),'integrity','artifact metrics mismatch')
        d.require(len(raw)==artifact['bytes'] and hashlib.sha256(raw).hexdigest()==artifact['sha256'],
                  'integrity','artifact bytes/hash mismatch')
        files[filename] = raw
    root = project.path(directory)
    present = []
    for path in root.rglob('*'):
        project.path(directory+'/'+path.relative_to(root).as_posix())
        if path.is_file():
            present.append(path.relative_to(root).as_posix())
            d.require(len(present)<=MAX_ASSETS*11+1,'budget','export file count')
    d.require(sorted(present)==sorted(list(files)+['bank.json']),'catalog','unlisted/missing export file')
    d.require(total==bank['payload_bytes'],'integrity','payload size mismatch')
    reports = []
    checked = 0
    for row in rows:
        d.require(row['file'] in files,'catalog','primary artifact absent')
        report = d.validate_wav(files[row['file']],loop=row['loop'])
        d.require(all(report[k]==row[k] for k in METRICS),'integrity','asset metrics/hash mismatch')
        reports.append(dict(report,id=row['id'],category=row['category'],licence=row['licence']))
        if determinism:
            rendered = c.render(row,row['transform'])
            expected = {row['id']+'/'+name:raw for name,raw in rendered['files'].items()}
            actual = {name:raw for name,raw in files.items() if name.startswith(row['id']+'/')}
            d.require(sorted(expected)==sorted(actual),'catalog','missing or extra generated artifact')
            for name in expected:
                d.require_identical(expected[name],actual[name])
            checked += 1
    numeric = d.validate_collection(reports,max_bytes=budgets['max_bytes'],max_assets=budgets['max_assets'])
    return {'ok':True,'status':'machine_checked_not_human_approved','assets':len(rows),
            'artifacts':len(files),'payload_bytes':total,'numeric':numeric,
            'determinism_checked':checked,'review_status':d.REVIEW}
