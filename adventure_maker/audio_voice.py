"""Original nonverbal character babble and sample-clock typewriter timing.

Not speech/TTS. One Unicode codepoint per timing entry; a UI using grapheme
clusters must map indices explicitly. No recognisable words or sampled voices.
"""
import json
import math
import random
from . import audio_dsp as d
from importlib import import_module

stock_synth = import_module('..audio.thaw_audio.stock_synth', __package__) if '.' in (__package__ or '') else import_module('audio.thaw_audio.stock_synth')


def library():
    return json.loads((d.DATA/'voices.json').read_text(encoding='utf-8'))


def resolve(params):
    lib = library()
    d.require(isinstance(params,dict), 'parameters', 'voice parameter object')
    allowed = ('character','emotion','seed','pitch','rate','timbre','formant')
    d.require(all(k in allowed for k in params), 'parameters', 'unknown voice parameter')
    character, emotion = params.get('character','narrator'), params.get('emotion','neutral')
    d.require(isinstance(character,str) and character in lib['characters'] and
              isinstance(emotion,str) and emotion in lib['emotions'], 'parameters', 'voice/ emotion enum')
    p = dict(lib['characters'][character], character=character, emotion=emotion, seed=params.get('seed',64))
    for k in ('pitch','rate','timbre','formant'):
        if k in params:
            p[k] = params[k]
    d.uint(p['seed'])
    for key,lo,hi in (('pitch',60,500),('rate',4,40),('timbre',0,0.8),('formant',250,1800)):
        d.number(p[key],lo,hi,key)
    return p


def render_line(text, params=None, mastering=None):
    p = resolve({} if params is None else params)
    d.require(isinstance(text,str) and 1 <= len(text) <= 1000 and any(c.isalnum() for c in text),
              'parameters','voice line must contain 1..1000 codepoints including a letter/number')
    d.require(all(ord(c)>=32 or c in '\n\t' for c in text), 'parameters','control characters')
    emotion = library()['emotions'][p['emotion']]
    rng = random.Random(p['seed'])
    glyphs, blips, cursor, next_blip = [], [], 0., 0.
    for index,char in enumerate(text):
        frame = round(cursor*d.SR)
        glyphs.append({'index':index,'text':char,'at_frame':frame})
        interval = 1/(p['rate']*emotion['rate'])
        if char in '.!?。！？':
            interval += .22
        elif char in ',;:，；：':
            interval += .10
        elif char == '\n':
            interval += .3
        if char.isalnum() and cursor >= next_blip:
            length = min(.13,max(.07,interval*.85))
            pitch = p['pitch']*emotion['pitch']*2**(rng.uniform(-1.5,1.5)/12)
            recipe = stock_synth.resolve('voice', {'seed':rng.randrange(2**32),'duration':length,
                'pitch':pitch,'brightness':min(.98,p['timbre']*emotion['timbre']),
                'formant':p['formant'],'breath':p['breath'],'robot':p['robot'],
                'flutter':p['flutter'],'vibrato':p['vibrato'],'glide':emotion['glide'],
                'pulse':.16 if p['character']=='creature' else .06})
            blips.append({'glyph_index':index,'start_frame':frame,'end_frame':frame+round(length*d.SR),'recipe':recipe})
            next_blip = cursor+max(.075,length+.008)
        cursor += interval
    duration = max(cursor, max(b['end_frame']/d.SR for b in blips))+.18
    d.require(duration <= 60,'budget','voice exceeds 60 seconds; split line explicitly')
    samples = [0.]*round(duration*d.SR)
    for blip in blips:
        raw = stock_synth.one_shot('voice',blip['recipe'],random.Random(blip['recipe']['seed']),
                                  blip['end_frame']-blip['start_frame'])
        for i,value in enumerate(raw):
            samples[blip['start_frame']+i] += value*.22
    master = d.check_identity(d.identity() if mastering is None else mastering)
    samples = d.master(samples,master,False)
    sr = master['sample_rate']
    for glyph in glyphs:
        glyph['at_frame'] = round(glyph['at_frame']*sr/d.SR)
        glyph['at_seconds'] = glyph['at_frame']/sr
    for blip in blips:
        for key in ('start_frame','end_frame'):
            blip[key] = round(blip[key]*sr/d.SR)
    timing = {'format':2,'text':text,'index_unit':'unicode_codepoint','sample_rate':sr,
              'frames':len(samples),'glyphs':glyphs,'blips':blips,'params':p,
              'mastering':master,'licence':'CC0-1.0','review_status':d.REVIEW,
              'note':'Original nonverbal babble, not TTS; timing uses audio playback clock.'}
    return {'wav':d.encode(samples,sr),'timing':timing}
