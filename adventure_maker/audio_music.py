"""Deterministic original event sequencer, PCM stems/layers and SMF type-1 MIDI.

All five parts share a clock and one mastering gain. MIDI carries the same notes,
not a transcription guessed from audio. GM timbres approximate, not reproduce WAV.
"""
import hashlib
import json
import math
import random
import struct
from . import audio_dsp as d

PARTS = ('pad', 'melody', 'bass', 'arpeggio', 'drums')
CHANNELS = (0, 1, 2, 3, 9)
MODES = {'major':[0,2,4,5,7,9,11], 'minor':[0,2,3,5,7,8,10],
         'dorian':[0,2,3,5,7,9,10], 'mixolydian':[0,2,4,5,7,9,10],
         'phrygian':[0,1,3,5,7,8,10], 'pentatonic':[0,2,4,7,9]}
KEYS = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,
        'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
LAYERS = {'explore':(1.,1.,.7,.35,.18), 'tension':(1.,.6,1.,.8,.65),
          'danger':(1.,1.,1.,1.,1.)}


def library():
    return json.loads((d.DATA/'music.json').read_text(encoding='utf-8'))


def resolve(params):
    p = {'mood':'explore','mode':'major','key':'C','tempo':96,'bars':4,
         'seed':64,'style':'sequenced','instruments':{}}
    d.require(isinstance(params,dict) and all(k in p for k in params), 'parameters', 'music fields')
    p.update(params)
    d.uint(p['seed'])
    d.require(type(p['bars']) is int and 2 <= p['bars'] <= 16, 'parameters', 'bars 2..16')
    d.number(p['tempo'],40,180,'tempo')
    lib = library()
    d.require(isinstance(p['key'],str) and p['key'] in KEYS and
              isinstance(p['mode'],str) and p['mode'] in MODES and
              isinstance(p['mood'],str) and p['mood'] in lib['moods'] and
              isinstance(p['style'],str) and p['style'] in lib['styles'], 'parameters', 'music enum')
    d.require(p['bars']*4*60/p['tempo'] <= 60, 'budget', 'music exceeds 60 seconds')
    d.require(isinstance(p['instruments'],dict) and all(k in PARTS for k in p['instruments'])
              and all(isinstance(v,str) and v in lib['instruments'] for v in p['instruments'].values()),
              'parameters', 'instrument mapping')
    instruments = dict(lib['styles'][p['style']]); instruments.update(p['instruments'])
    d.require(instruments['drums']=='soft_drums' and all(instruments[k]!='soft_drums' for k in PARTS[:-1]),
              'parameters', 'percussion must stay on drums part')
    p['instruments'] = instruments
    return p


def compose(params, transpose=0):
    p = resolve(params)
    d.number(transpose,-12,12,'transpose')
    d.require(float(transpose).is_integer(),'parameters','whole-semitone transpose required')
    transpose = int(transpose)
    rng = random.Random(p['seed'])
    mood, scale = library()['moods'][p['mood']], MODES[p['mode']]
    tempo_us = round(60000000/p['tempo'])
    beat_seconds, beats = tempo_us/1000000., p['bars']*4
    def note(degree, octave=0):
        return 48+KEYS[p['key']]+scale[degree%len(scale)]+12*(degree//len(scale)+octave)+transpose
    motif = [rng.randrange(len(scale)) for _ in range(8)]
    motif[0] = 0
    parts = {k:[] for k in PARTS}
    chords = []
    def add(part, beat, pitch, length, velocity):
        length = min(length, beats-beat)
        parts[part].append({'beat':beat, 'pitch':pitch, 'length':length, 'velocity':velocity})
    for bar in range(p['bars']):
        degree = mood['progression'][bar%len(mood['progression'])]
        chord = [note(degree+i) for i in (0,2,4)]
        chords.append(chord)
        for pitch in chord:
            add('pad', bar*4, pitch, 4, 54)
        for step in (0,2):
            add('bass', bar*4+step, note(degree,-1), 1.7, 72 if step==0 else 61)
        for i, beat in enumerate(mood['rhythm']):
            if i and rng.random() > mood['density']:
                continue
            # Repeat a recognizable motif with chord-relative answers, not random walks.
            degree_m = motif[(i+bar%2*2)%len(motif)] + (degree if bar%2 else 0)
            pitch = note(degree_m,1)
            length = min(.75 if p['mood'] in ('chase','danger') else 1.1, 4-beat)
            add('melody',bar*4+beat,pitch,length,68+rng.randrange(12))
        for i in range(8):
            add('arpeggio',bar*4+i*.5,chord[(i+bar)%3]+12,.42,48+(i%2)*7)
        for beat,pitch in ((0,36),(1,38),(2,36),(3,38)):
            add('drums',bar*4+beat,pitch,.16,60 if pitch==36 else 48)
        for i in range(8):
            add('drums',bar*4+i*.5,42,.07,28+(i%2)*5)
    score = {'format':2,'params':p,'tempo_us':tempo_us,'beats':beats,
            'frames':round(beats*beat_seconds*d.SR),'sample_rate':d.SR,
            'motif':motif,'chords':chords,'parts':parts,'licence':'CC0-1.0',
            'composition':'Original deterministic motif/degree progression; no borrowed melody or samples.'}
    if transpose:
        score['transpose_semitones'] = transpose
    return score


def _vlq(value):
    result = [value & 127]
    value >>= 7
    while value:
        result.insert(0,(value & 127)|128); value >>= 7
    return bytes(result)


def midi(score):
    end = score['beats']*480
    lib = library()
    def track(events):
        raw, previous = bytearray(), 0
        for tick,priority,event in sorted(events,key=lambda x:(x[0],x[1],x[2])):
            raw.extend(_vlq(tick-previous)); raw.extend(event); previous=tick
        raw.extend(_vlq(end-previous)+b'\xff\x2f\x00')
        return b'MTrk'+struct.pack('>I',len(raw))+raw
    conductor = [(0,0,b'\xff\x51\x03'+score['tempo_us'].to_bytes(3,'big')),
                 (0,1,b'\xff\x58\x04\x04\x02\x18\x08'),
                 (0,2,b'\xff\x06\x09LOOPSTART'),(end,2,b'\xff\x06\x07LOOPEND')]
    chunks = [track(conductor)]
    for part,channel in zip(PARTS,CHANNELS):
        name = part.encode('ascii')
        instrument = score['params']['instruments'][part]
        events = [(0,0,b'\xff\x03'+_vlq(len(name))+name),
                  (0,1,bytes([192+channel,lib['instruments'][instrument]['program']]))]
        for e in score['parts'][part]:
            on, off = round(e['beat']*480), round((e['beat']+e['length'])*480)
            events.append((on,3,bytes([144+channel,e['pitch'],e['velocity']])))
            events.append((off,2,bytes([128+channel,e['pitch'],0])))
        chunks.append(track(events))
    return b'MThd'+struct.pack('>IHHH',6,1,len(chunks),480)+b''.join(chunks)


def _synthesize(score):
    lib = library()
    count = score['frames']
    seconds_per_beat = score['tempo_us']/1e6
    stems = {}
    for part in PARTS:
        output = [0.]*count
        spec = lib['instruments'][score['params']['instruments'][part]]
        table = [sum(a*math.sin(2*math.pi*(h+1)*i/1024) for h,a in enumerate(spec['harmonics']))
                 for i in range(1024)]
        table_gain = sum(spec['harmonics'])
        table = [v/table_gain for v in table]
        for j,event in enumerate(score['parts'][part]):
            rng = random.Random(score['params']['seed']+j*7919+PARTS.index(part)*104729)
            start = round(event['beat']*seconds_per_beat*d.SR)
            held = event['length']*seconds_per_beat
            release = spec['release']
            size = round((held+release)*d.SR)
            pitch = 440*2**((event['pitch']-69)/12)
            phase, increment = rng.random()*1024, pitch/d.SR*1024
            for offset in range(size):
                t = offset/d.SR
                attack = min(1.,t/spec['attack'])
                tail = max(0.,min(1.,(held+release-t)/release))
                env = attack*attack*(3-2*attack)*tail*tail*(3-2*tail)
                if spec['decay']:
                    env *= math.exp(-t/spec['decay'])
                if part == 'drums':
                    if event['pitch']==36:
                        value = math.sin(2*math.pi*(67*t+2.2*(1-math.exp(-t*35))))*math.exp(-t*18)
                    elif event['pitch']==38:
                        value = (.75*rng.uniform(-1,1)+.25*math.sin(2*math.pi*155*t))*math.exp(-t*25)
                    else:
                        value = rng.uniform(-1,1)*math.exp(-t*65)*.65
                else:
                    a = int(phase)%1024
                    f = phase-int(phase)
                    value = table[a]*(1-f)+table[(a+1)%1024]*f
                    phase = (phase+increment)%1024
                gain = {'pad':.15,'melody':.32,'bass':.30,'arpeggio':.25,'drums':.34}[part]
                output[(start+offset)%count] += value*env*gain*event['velocity']/100
        stems[part] = output
    return stems


def render(params, mastering=None, transpose=0):
    score = compose(params,transpose)
    p = d.check_identity(d.identity() if mastering is None else mastering)
    raw = _synthesize(score)
    stems = {part:d.process(samples,p,True) for part,samples in raw.items()}
    count = len(stems['pad'])
    # Worst-case sum of magnitudes bounds EVERY convex adaptive mix, even when
    # individual stems cancel in the full mix. No independent stem normalization.
    envelope_peak = max(sum(abs(stems[k][i]) for k in PARTS) for i in range(count))
    mixed = [sum(stems[k][i] for k in PARTS) for i in range(count)]
    gain = min(p['target_rms']/d.rms(mixed),p['peak_ceiling']/envelope_peak)
    stems = {k:[v*gain for v in samples] for k,samples in stems.items()}
    files = {}
    for part,samples in stems.items():
        files['stem-'+part+'.wav'] = d.encode(samples,p['sample_rate'])
    for layer,weights in LAYERS.items():
        samples = [sum(stems[k][i]*w for k,w in zip(PARTS,weights)) for i in range(count)]
        files['layer-'+layer+'.wav'] = d.encode(samples,p['sample_rate'])
    files['loop.wav'] = files['layer-danger.wav']
    score['mastering'] = p
    score['export_frames'] = count
    score['master_gain'] = gain
    score['adaptive'] = {'weights':LAYERS,'crossfade':'linear amplitude; shared clock, never restart stems',
                         'recommended_seconds':.5,'peak_bound':envelope_peak*gain}
    files['score.mid'] = midi(score)
    files['score.json'] = (json.dumps(score,sort_keys=True,indent=2)+'\n').encode()
    return {'files':files,'score':score}


def crossfade(first, second, frames):
    """Bounded linear-amplitude crossfade of phase-aligned layer buffers."""
    d.require(len(first)==len(second) and type(frames) is int and 2 <= frames <= len(first),
              'parameters','aligned equal-length layers and valid fade length required')
    result = []
    for i,(a,b) in enumerate(zip(first,second)):
        x = min(1.,i/(frames-1))
        result.append(a*(1-x)+b*x)
    return result
