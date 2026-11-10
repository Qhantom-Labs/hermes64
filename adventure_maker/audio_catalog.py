"""Recipe-first audio library. IDs are data, not hard-coded runtime branches."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
from . import audio_dsp as d
from .safety import inspect_path, relative
from importlib import import_module

# The plugin loader supplies a package prefix; CLI/tests use the top-level tree.
stock_synth = import_module('..audio.thaw_audio.stock_synth', __package__) if '.' in (__package__ or '') else import_module('audio.thaw_audio.stock_synth')

ROOT = Path(__file__).resolve().parents[1]


def source_fingerprints():
    """Bind measured metadata to the exact recipe/DSP/preset source, not IDs."""
    paths = list((ROOT/'adventure_maker').glob('audio_*.py'))
    paths.extend((ROOT/'audio/thaw_audio').glob('*.py'))
    paths.extend(d.DATA/name for name in ('identity.json','music.json','voices.json',
                                         'palettes.json','recipes.json'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def definitions():
    source = json.loads((d.DATA/'recipes.json').read_text())
    rows = source['assets']
    seen = {}
    for row in rows:
        d.require(isinstance(row['id'],str) and re.fullmatch(r'h64\.[a-z0-9_.-]+',row['id']) and
                  row['id'] not in seen,'catalog','invalid/duplicate recipe ID')
        seen[row['id']] = True
        d.require(row['licence']=='CC0-1.0','licence','generated recipe must be CC0')
        d.require(type(row['loop']) is bool and bool(row['tags']) and bool(row['purpose']),
                  'catalog','missing recipe metadata')
        d.uint(row['seed'])
    return rows


def all_records():
    legacy = json.loads((ROOT/'audio/catalog.json').read_text())['assets']
    rows = definitions()
    measured = d.DATA/'catalog.json'
    if measured.is_file():
        saved_catalog = json.loads(measured.read_text())
        valid = saved_catalog.get('source_sha256')==source_fingerprints()
        index = {r['id']:r for r in saved_catalog['assets']} if valid else {}
        for row in rows:
            saved = index.get(row['id'],{})
            if saved.get('recipe') == row['recipe']:
                for key in ('duration','frames','bytes','sha256','sample_rate','peak','rms','dc','seam',
                            'loudness_rms_dbfs','loudness_method','review_status','cache_file'):
                    if key in saved:
                        row[key] = saved[key]
    for old in legacy:
        row = copy.deepcopy(old)
        row.update(licence='CC0-1.0',seed=old['params']['seed'],purpose='Preserved legacy cue: '+old['id'],
                   style_tags=['general','n64'],recipe={'engine':'legacy','file':old['file']},
                   variation_pool={'id':old['id']+'.legacy','size':1,'policy':'frozen'},
                   loudness_rms_dbfs=20*math.log10(old['rms']),
                   loudness_method='20*log10(unweighted RMS), not LUFS')
        rows.append(row)
    return sorted(rows,key=lambda r:r['id'])


def get(identity):
    d.require(isinstance(identity,str) and re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}',identity),
              'catalog','invalid sound ID')
    for row in all_records():
        if row['id']==identity:
            return row
    raise d.AudioError('catalog','unknown sound ID: '+identity)


def search(query='', tags=(), category=None, limit=20, offset=0):
    d.uint(limit,'limit',50); d.uint(offset,'offset',10000)
    rows = all_records()
    words = query.casefold().split()
    matches = [r for r in rows if (category is None or r['category']==category)
               and all(t in r['tags'] for t in tags)
               and all(w in ' '.join([r['id'],r['purpose']]+r['tags']).casefold() for w in words)]
    selected = matches[offset:offset+limit]
    return {'total':len(rows),'matched':len(matches),'returned':len(selected),
            'has_more':offset+len(selected)<len(matches),
            'next_offset':offset+len(selected) if offset+len(selected)<len(matches) else None,
            'assets':selected}


def variation(row, ordinal, seed):
    d.uint(seed); d.uint(ordinal,'variation ordinal',1023)
    d.require(row['recipe']['engine']!='legacy','parameters','legacy files are frozen; choose an h64 ID')
    result = copy.deepcopy(row)
    pool = row['variation_pool']
    # Shuffle blocks, rotating each block when its first member repeats the last
    # of the previous one. Same actor seed + ordinal always gives the same member.
    size = pool['size']
    rng = random.Random(seed ^ pool['seed'])
    previous = None
    order = list(range(size))
    for _ in range(ordinal//size+1):
        rng.shuffle(order)
        if order[0]==previous:
            order = order[1:]+order[:1]
        previous = order[-1]
    member = order[ordinal%size]
    variant_seed = int.from_bytes(hashlib.sha256((str(seed)+':'+row['id']+':'+str(member)).encode()).digest()[:4],'little')
    result['seed'] = variant_seed
    result['recipe']['params']['seed'] = variant_seed
    result['variant'] = {'ordinal':ordinal,'member':member,'actor_seed':seed}
    if result['recipe']['engine']=='sfx':
        p = result['recipe']['params']
        p['pitch'] *= 2**(pool['pitch_cents'][member]/1200)
        # Existing validation remains authoritative rather than clamping input.
        result['recipe']['params'] = stock_synth.resolve(result['recipe']['generator'],p)
    return result


def transform(value=None):
    p = d.identity()
    defaults = {key:p[key] for key in ('filter_hz','reverb_mix','reverb_ms','sample_rate')}
    defaults.update(pitch_semitones=0.,instruments={})
    value = {} if value is None else value
    d.require(isinstance(value,dict) and all(k in defaults for k in value),'parameters','transform fields')
    defaults.update(value)
    d.number(defaults['pitch_semitones'],-12,12,'pitch_semitones')
    for key in ('filter_hz','reverb_mix','reverb_ms','sample_rate'):
        p[key] = defaults[key]
    d.check_identity(p)
    d.require(isinstance(defaults['instruments'],dict),'parameters','instrument object')
    return defaults,p


def render(row, transform=None):
    effect,mastering = globals()['transform'](transform)
    recipe = copy.deepcopy(row['recipe'])
    engine = recipe['engine']
    if engine=='legacy':
        d.require(not transform,'parameters','legacy originals are immutable; use h64 recipes for transforms')
        path = inspect_path(ROOT/'audio'/relative(recipe['file']))
        raw = path.read_bytes()
        d.require(hashlib.sha256(raw).hexdigest()==row['sha256'],'integrity','legacy WAV hash mismatch')
        return {'wav':raw,'files':{'loop.wav' if row['loop'] else 'sound.wav':raw},'recipe':recipe}
    p = recipe['params']
    factor = 2**(effect['pitch_semitones']/12)
    if engine=='music':
        from . import audio_music
        # Shift actual melodic MIDI notes, not key classes modulo 12: C down one
        # semitone must fall, and an octave shift must not disappear. Drums stay.
        d.require(float(effect['pitch_semitones']).is_integer(),'parameters','music pitch requires whole semitones')
        if effect['instruments']:
            p['instruments'].update(effect['instruments'])
        rendered = audio_music.render(p,mastering,transpose=int(effect['pitch_semitones']))
        return {'wav':rendered['files']['loop.wav'],'files':rendered['files'],'recipe':recipe,'score':rendered['score']}
    if engine=='voice':
        from . import audio_voice
        if factor != 1:
            p['pitch'] = audio_voice.resolve(p)['pitch']*factor
        rendered = audio_voice.render_line(recipe['text'],p,mastering)
        timing = (json.dumps(rendered['timing'],sort_keys=True,indent=2)+'\n').encode()
        return {'wav':rendered['wav'],'files':{'voice.wav':rendered['wav'],'timing.json':timing},'recipe':recipe}
    d.require(engine=='sfx','catalog','unknown engine')
    d.require(not effect['instruments'],'parameters','instruments apply to music only')
    p['pitch'] *= factor
    p = stock_synth.resolve(recipe['generator'],p)
    mastering['filter_hz'] = min(mastering['filter_hz'],p['lowpass_hz'])
    rng = random.Random(p['seed'])
    count = round(p['duration']*d.SR)
    if recipe['generator']=='environment':
        samples = stock_synth.environment(p,rng,count)
        if not p['loop']:
            # The analytic sin(pi*t/duration)**0.7 envelope is exactly zero at
            # both endpoints. The frozen helper can round its final angle just
            # above pi and produce a tiny complex value. Enforce the analytic
            # endpoints in this additive path; never rewrite the frozen DSP.
            samples[0] = samples[-1] = 0.0
    elif recipe['generator']=='machine':
        samples = stock_synth.machine(p,rng,count)
    else:
        samples = stock_synth.one_shot(recipe['generator'],p,rng,count)
    d.require(not recipe['layers'],'catalog','unsupported composite layer')
    phase = recipe.get('loop_phase',0.)
    d.number(phase,0,1,'loop_phase')
    d.require(row['loop'] or phase==0,'parameters','loop phase on one-shot')
    if phase:
        origin = round(phase*len(samples)) % len(samples)
        samples = samples[origin:]+samples[:origin]
    samples = d.master(samples,mastering,row['loop'])
    raw = d.encode(samples,mastering['sample_rate'])
    recipe['params'] = p
    return {'wav':raw,'files':{'sound.wav':raw},'recipe':recipe}
