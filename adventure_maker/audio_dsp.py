"""Original AUDIO2 mastering and fail-closed numeric validation (stdlib only).

RMS dBFS is a rough loudness proxy, NOT LUFS. New audio is never human-approved
by a numerical gate. Legacy audio and its mastering path remain unchanged.
"""
import array
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import wave

SR = 22050
DATA = Path(__file__).resolve().parents[1] / 'audio' / 'expansion'
REVIEW = 'machine-checked, not human-approved'


class AudioError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def require(condition, code, message):
    if not condition:
        raise AudioError(code, message)


def number(value, low, high, name):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            'parameters', name + ' outside finite bounds ' + str((low, high)))
    return value


def uint(value, name='seed', maximum=2**32-1):
    require(type(value) is int and 0 <= value <= maximum, 'parameters', name + ' must be uint')
    return value


def identity():
    return json.loads((DATA / 'identity.json').read_text())['mastering']


def check_identity(p):
    expected = identity()
    require(isinstance(p, dict) and sorted(p) == sorted(expected), 'parameters', 'mastering fields')
    require(type(p['sample_rate']) is int and p['sample_rate'] in (SR, 32000), 'parameters', 'sample_rate')
    require(type(p['bits']) is int and 10 <= p['bits'] <= 16, 'parameters', 'bits')
    require(type(p['rate_divisor']) is int and 1 <= p['rate_divisor'] <= 3, 'parameters', 'rate_divisor')
    for key, low, high in (('filter_hz', 300, 5000), ('reverb_ms', 15, 120),
                          ('reverb_mix', 0, .35), ('peak_ceiling', .1, .65),
                          ('target_rms', .025, .13)):
        number(p[key], low, high, key)
    return dict(p)


def rms(samples):
    return math.sqrt(sum(x*x for x in samples) / max(1, len(samples)))


def lowpass(samples, hz, sr=SR, loop=False):
    alpha = 1 - math.exp(-2 * math.pi * hz / sr)
    beta = 1-alpha
    previous = 0.
    if loop:
        for value in samples:
            previous = alpha*value + beta*previous
        previous /= 1-beta**len(samples)
    result = []
    for value in samples:
        previous = alpha*value + beta*previous
        result.append(previous)
    return result


def resample(samples, source_rate, target_rate, loop=False):
    if source_rate == target_rate:
        return list(samples)
    count = round(len(samples)*target_rate/source_rate)
    result = []
    for i in range(count):
        x = i*source_rate/target_rate
        a = int(x)
        b = (a+1) % len(samples) if loop else min(a+1, len(samples)-1)
        result.append(samples[a]*(1-(x-a)) + samples[b]*(x-a))
    return result


def loop_bridge(samples, sr=SR):
    """Fixed-origin C1 interpolation at the wrap, preserving musical clock.

    Only <=2 ms on either side is adjusted. This removes sample discontinuities,
    not bad composition; energy-ratio and independent seam tests still apply.
    """
    y = list(samples)
    width = min(round(.002*sr), len(y)//8)
    if width < 2:
        return y
    center = (y[0]+y[-1])*.5
    first, last = y[-width-1], y[width]
    slope_a = max(-.001, min(.001, y[-width-1]-y[-width-2]))
    slope_b = max(-.001, min(.001, y[width+1]-y[width]))
    for j in range(width):
        t = (j+1)/width
        y[-width+j] = ((2*t**3-3*t*t+1)*first + (t**3-2*t*t+t)*width*slope_a
                       + (-2*t**3+3*t*t)*center)
        t = j/width
        y[j] = ((2*t**3-3*t*t+1)*center + (-2*t**3+3*t*t)*last
                + (t**3-t*t)*width*slope_b)
    return y


def process(samples, p, loop=False):
    """Linear filter/reverb stage; shared by stems to retain phase alignment."""
    p = check_identity(p)
    require(4 <= len(samples) <= SR*60 and all(math.isfinite(x) for x in samples),
            'numeric', 'invalid/oversized source buffer')
    y = lowpass(samples, min(p['filter_hz'], SR/(2.5*p['rate_divisor'])), loop=loop)
    quant = 2**(p['bits']-1)-1
    y = [round(y[(i//p['rate_divisor'])*p['rate_divisor']]*quant)/quant for i in range(len(y))]
    dry = lowpass(y, p['filter_hz'], loop=loop)
    y = list(dry)
    for scale, gain in ((1., 1.), (1.71, .52), (2.96, .25)):
        lag = round(SR*p['reverb_ms']*.001*scale)
        for i in range(len(y)):
            if loop or i >= lag:
                y[i] += dry[(i-lag) % len(y)]*p['reverb_mix']*gain
    y = resample(y, SR, p['sample_rate'], loop)
    if loop:
        y = loop_bridge(y, p['sample_rate'])
        bias = sum(y)/len(y)
        return [v-bias for v in y]
    fade = min(round(.012*p['sample_rate']), len(y)//6)
    weights = [.5-.5*math.cos(math.pi*min(i, len(y)-1-i, fade)/fade) for i in range(len(y))]
    bias = sum(v*w for v,w in zip(y,weights))/sum(weights)
    return [(v-bias)*w for v,w in zip(y,weights)]


def master(samples, p=None, loop=False):
    p = check_identity(identity() if p is None else p)
    y = process([math.tanh(v*1.3) for v in samples], p, loop)
    peak, level = max(abs(v) for v in y), rms(y)
    require(level > 1e-9, 'silence', 'silent synthesis')
    gain = min(p['target_rms']/level, p['peak_ceiling']/max(peak, 1e-9))
    return [v*gain for v in y]


def encode(samples, sample_rate=SR):
    require(sample_rate in (SR, 32000), 'format', 'expected 22050 or 32000 Hz')
    require(all(math.isfinite(v) for v in samples), 'numeric', 'nonfinite PCM')
    require(all(abs(v) < 1 for v in samples), 'peak', 'encoder refuses overflow')
    pcm = array.array('h', (round(v*32767) for v in samples))
    if sys.byteorder != 'little':
        pcm.byteswap()
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return stream.getvalue()


def decode(data):
    require(len(data) >= 44 and data[:4] == b'RIFF' and data[8:12] == b'WAVE'
            and struct.unpack('<I', data[4:8])[0]+8 == len(data), 'format', 'invalid RIFF')
    try:
        with wave.open(io.BytesIO(data), 'rb') as w:
            sr, count = w.getframerate(), w.getnframes()
            require(w.getnchannels() == 1 and w.getsampwidth() == 2 and
                    w.getcomptype() == 'NONE' and sr in (SR, 32000), 'format', 'mono PCM16 required')
            require(count <= sr*180, 'budget', 'WAV duration allocation limit')
            raw = w.readframes(count)
        require(len(raw) == count*2, 'format', 'truncated PCM')
        pcm = array.array('h')
        pcm.frombytes(raw)
        if sys.byteorder != 'little':
            pcm.byteswap()
        return [v/32768. for v in pcm], sr
    except (wave.Error, EOFError, struct.error) as exc:
        raise AudioError('format', str(exc)) from exc


def validate_samples(samples, sample_rate=SR, loop=False, sparse=False,
                     min_duration=.02, max_duration=60, loudness_bounds=(-48., -12.)):
    require(sample_rate in (SR, 32000), 'format', 'sample rate')
    require(len(samples) >= 4 and min_duration <= len(samples)/sample_rate <= max_duration,
            'duration', 'duration outside bounds')
    require(all(math.isfinite(v) for v in samples), 'numeric', 'nonfinite sample')
    peak = max(abs(v) for v in samples)
    require(peak <= .9, 'peak', 'peak exceeds 0.90 FS')
    level = rms(samples)
    require(level >= .0005, 'silence', 'RMS below .0005')
    dc = sum(samples)/len(samples)
    require(abs(dc) <= .002, 'dc_offset', 'mean exceeds +/-0.002 FS')
    loudness = 20*math.log10(level)
    require(loudness_bounds[0] <= loudness <= loudness_bounds[1], 'loudness', 'RMS dBFS outside bounds')
    seam = None
    if loop:
        jump = samples[0]-samples[-1]
        before, after = samples[-1]-samples[-2], samples[1]-samples[0]
        window = min(len(samples)//4, round(.02*sample_rate))
        seam = {'jump':abs(jump), 'slope_mismatch':max(abs(jump-before), abs(after-jump)),
                'head_rms_ratio':rms(samples[:window])/level,
                'tail_rms_ratio':rms(samples[-window:])/level, 'sparse':sparse}
        require(seam['jump'] <= .003 and seam['slope_mismatch'] <= .003 and
                (sparse or min(seam['head_rms_ratio'], seam['tail_rms_ratio']) >= .35),
                'loop_seam', str(seam))
    return {'duration':len(samples)/sample_rate, 'frames':len(samples), 'sample_rate':sample_rate,
            'peak':peak, 'rms':level, 'dc':dc, 'loudness_rms_dbfs':loudness,
            'loudness_method':'20*log10(unweighted RMS), not LUFS', 'seam':seam}


def validate_wav(data, **options):
    samples, sr = decode(data)
    report = validate_samples(samples, sr, **options)
    return dict(report, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def require_identical(first, second):
    require(first == second, 'non_determinism', 'same recipe produced different bytes')
    return hashlib.sha256(first).hexdigest()


def validate_collection(rows, max_bytes=32*1024*1024, max_assets=512, max_spread_db=18):
    require(len(rows) <= max_assets and sum(r['bytes'] for r in rows) <= max_bytes,
            'budget', 'bank byte/asset budget exceeded')
    require(bool(rows), 'catalog', 'empty bank')
    seen, groups = {}, {}
    for row in rows:
        require(row.get('licence') == 'CC0-1.0', 'licence', 'generated CC0 licence required')
        require(row['id'] not in seen, 'catalog', 'duplicate id')
        seen[row['id']] = True
        groups.setdefault(row['category'], []).append(row['loudness_rms_dbfs'])
    for name, levels in groups.items():
        require(max(levels)-min(levels) <= max_spread_db, 'loudness_spread', name)
    return {'assets':len(rows), 'bytes':sum(r['bytes'] for r in rows),
            'category_spread_db':{k:max(v)-min(v) for k,v in groups.items()}}
