"""Provider-neutral tool schema; handler validates action-specific requirements."""
from .schemas import obj, text, ID

UINT = {'type':'integer','minimum':0,'maximum':4294967295}
NUMBER = lambda low,high: {'type':'number','minimum':low,'maximum':high}
INSTRUMENTS = ['ocarina','flute','strings','glass_pad','mallet','wood_mallet','harp','bass','soft_drums']
INSTRUMENT_MAP = obj({k:{'type':'string','enum':INSTRUMENTS} for k in ('pad','melody','bass','arpeggio','drums')})
TRANSFORM = obj({'pitch_semitones':NUMBER(-12,12),'filter_hz':NUMBER(300,5000),
                 'reverb_ms':NUMBER(15,120),'reverb_mix':NUMBER(0,.35),
                 'sample_rate':{'type':'integer','enum':[22050,32000]},'instruments':INSTRUMENT_MAP})
MUSIC = obj({'mood':{'type':'string','enum':['explore','home','mystery','night','danger','chase','wonder','sadness','victory','desert','water','machine']},
             'mode':{'type':'string','enum':['major','minor','dorian','mixolydian','phrygian','pentatonic']},
             'key':text(2),'tempo':NUMBER(40,180),'bars':{'type':'integer','minimum':2,'maximum':16},
             'seed':UINT,'style':{'type':'string','enum':['sequenced','cold_ambient','warm_folk','desert_folk']},
             'instruments':INSTRUMENT_MAP})
VOICE = obj({'character':{'type':'string','enum':['narrator','elder','child','robot','hooded-faceless','creature']},
             'emotion':{'type':'string','enum':['neutral','curious','happy','sad','angry','afraid']},
             'seed':UINT,'pitch':NUMBER(60,500),'rate':NUMBER(4,40),'timbre':NUMBER(0,.8),'formant':NUMBER(250,1800)})
IMPORT_OPTIONS = obj({'loop':{'type':'boolean'},'crossfade_ms':{'type':'integer','minimum':0,'maximum':10000},
                      'start_s':NUMBER(0,900),'max_seconds':NUMBER(.05,900),
                      'max_file_bytes':{'type':'integer','minimum':4096,'maximum':268435456},
                      'max_total_bytes':{'type':'integer','minimum':4096,'maximum':1073741824}})
IMPORT_ITEM = obj({'path':text(1024),'id':text(64,pattern=r'^[a-z][a-z0-9_.-]*$'),
                   'kind':{'type':'string','enum':['auto','music','voice','sfx']},'loop':{'type':'boolean'},
                   'crossfade_ms':{'type':'integer','minimum':0,'maximum':10000},'start_s':NUMBER(0,900),
                   'max_seconds':NUMBER(.05,900),'max_file_bytes':{'type':'integer','minimum':4096,'maximum':268435456}},['path'])
AUDIO_SCHEMA = {
    'name':'hermes64_audio',
    'description':'Search original N64-era audio; render WAV, variations, loop music + MIDI/stems/adaptive layers, dialogue babble + timing, or style banks; import your own MP3/OGG/WAV music and voice lines (ffmpeg) and assign them to music/voice/cue slots. Writes only new exports/audio directories, or audio/import and audio/slots.json for imports, in an existing managed project. Validate checks actual bytes and rerender determinism. Offline, no playback or human approval.',
    'parameters':obj({
        'action':{'type':'string','enum':['list','search','preview','variation','music','voice','bank','validate','import','assign','imported']},
        'project':ID,'export':ID,'id':text(128,pattern=r'^[a-z][a-z0-9_.-]*$'),
        'query':text(200),'tags':{'type':'array','items':text(64),'maxItems':12},'category':text(32),
        'limit':{'type':'integer','minimum':1,'maximum':50},'offset':{'type':'integer','minimum':0,'maximum':10000},
        'seed':UINT,'ordinal':{'type':'integer','minimum':0,'maximum':1023},
        'music':MUSIC,'voice':VOICE,'text':text(1000),'transform':TRANSFORM,
        'palette':text(64),'profile_path':text(240),
        'max_bytes':{'type':'integer','minimum':1024,'maximum':33554432},
        'max_assets':{'type':'integer','minimum':1,'maximum':64},
        # AUDIOPIPE: bring-your-own MP3/OGG/WAV import (adventure_maker/audio_import.py, docs/AUDIO-IMPORT.md).
        'sources':{'type':'array','items':text(1024),'minItems':1,'maxItems':64},
        'kind':{'type':'string','enum':['auto','music','voice','sfx']},
        'items':{'type':'array','minItems':1,'maxItems':64,'items':IMPORT_ITEM},
        'options':IMPORT_OPTIONS,'replace':{'type':'boolean'},'slots_json':text(65536)},['action'])}
SCHEMAS = {'hermes64_audio':AUDIO_SCHEMA}
