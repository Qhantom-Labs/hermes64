"""Bring-your-own audio: import MP3/OGG/FLAC/WAV music, voice lines and cues into the runtime WAV format.

General plugin feature (docs/AUDIO-IMPORT.md). Any game can use it with any audio:

* decode + resample + channel-map with a bundled-or-detected ffmpeg (never downloaded; clear error if missing),
* trim leading/trailing silence, normalise integrated loudness per kind (voice 3 dB above music),
* optionally make a seamless loop with an equal-power crossfade and report the seam numerically,
* cap per-file and total size for web export (sample-rate/channel ladder, then a clear refusal),
* write 16-bit PCM WAVs (what runtime/godot/view/audio.gd loads) and a manifest with hashes and a size report.

Audio is presentation only: nothing here touches story, simulation, replay or save data.
Source paths are read, never written; the manifest stores only the source *basename* and hash, so a user's private
folder layout never reaches project data, evidence or exports.
"""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from . import platforms
from .runner import scratch_env
from .safety import Fault, fail

GENERATOR = 'hermes64.audio_import/1'
EXTENSIONS = ('.mp3', '.ogg', '.oga', '.wav', '.flac', '.opus', '.m4a')
KINDS = ('music', 'voice', 'sfx')
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_SECONDS = 15 * 60
MAX_FILES = 64
# Loudness targets (integrated LUFS, EBU R128 via ffmpeg ebur128). Voice sits 3 dB above music by design.
TARGETS = {
    'music': {'lufs': -18.0, 'ladder': [(32000, 2), (22050, 2), (22050, 1), (16000, 1)],
              'max_file_bytes': 10 * 1024 * 1024, 'trim_dbfs': -60.0, 'pad_ms': 0, 'loop': True},
    'voice': {'lufs': -15.0, 'ladder': [(22050, 1), (16000, 1)],
              'max_file_bytes': 1024 * 1024, 'trim_dbfs': -50.0, 'pad_ms': 40, 'loop': False},
    'sfx':   {'lufs': -16.0, 'ladder': [(22050, 1), (16000, 1)],
              'max_file_bytes': 512 * 1024, 'trim_dbfs': -55.0, 'pad_ms': 10, 'loop': False},
}
CEILING_DBFS = -1.0
MAX_LIMIT_DB = 6.0
DEFAULT_TOTAL_BYTES = 40 * 1024 * 1024
DEFAULT_CROSSFADE_MS = 1500
AUTO_MUSIC_SECONDS = 20.0
CLIP_LEVEL = 0.999
CLIP_FRACTION = 0.001
SILENT_PEAK = 10 ** (-80 / 20)
ID_RE = re.compile(r'^[a-z][a-z0-9_.-]{0,63}$')


class ImportError_(Fault):
    pass


def _fail(code, message):
    raise ImportError_(code, message)


# ---------------------------------------------------------------- ffmpeg discovery
def _exe(name):
    return name + '.exe' if os.name == 'nt' else name


def bundled_ffmpeg(root):
    """Optional bundled binary: <plugin>/tools/bin/<platform>/ffmpeg[.exe]. Not shipped by default (size/licence)."""
    plat = 'windows' if os.name == 'nt' else ('macos' if sys.platform == 'darwin' else 'linux')
    return Path(root) / 'tools' / 'bin' / plat / _exe('ffmpeg')


def find_ffmpeg(configured='', root=None):
    """Configured path > bundled binary > PATH > common install folders. Never downloads anything."""
    candidates = []
    if configured:
        path = Path(configured)
        if not path.is_absolute() or not path.is_file():
            _fail('ffmpeg_missing', 'Configured ffmpeg_path is not an existing absolute file: ' + str(configured))
        candidates.append(path)
    if root is not None:
        candidates.append(bundled_ffmpeg(root))
    found = shutil.which(_exe('ffmpeg')) or shutil.which('ffmpeg')
    if found:
        candidates.append(Path(found))
    candidates += [Path(p) for p in platforms.ffmpeg_candidates()]
    for path in candidates:
        if path.is_file() and os.access(str(path), os.X_OK):
            return path
    _fail('ffmpeg_missing', 'ffmpeg was not found. Install it (macOS: brew install ffmpeg; Windows: winget install '
          'Gyan.FFmpeg; Linux: your package manager), or set the plugin config ffmpeg_path to the executable, '
          'or place it at ' + (str(bundled_ffmpeg(root)) if root is not None else 'tools/bin/<platform>/ffmpeg') +
          '. Hermes64 never downloads ffmpeg.')


def _run(ffmpeg, args, data=None, timeout=600):
    try:
        # List argv, never a shell: spaces, quotes and Windows drive paths pass through untouched.
        argv = [str(ffmpeg), '-hide_banner'] + (['-nostdin'] if data is None else []) + list(args)
        # Windows: no console window flashing up per ffmpeg call when Hermes runs without a console.
        extra = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)} if os.name == 'nt' else {}
        # Runner's minimal environment (scratch HOME/TMPDIR, system PATH): never Hermes's variables or provider keys.
        with scratch_env() as env:
            if data is None:
                proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=timeout, env=env, **extra)
            else:
                proc = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=timeout, env=env, **extra)
    except subprocess.TimeoutExpired:
        _fail('ffmpeg_timeout', 'ffmpeg timed out')
    except OSError as exc:
        _fail('ffmpeg_missing', 'ffmpeg could not start: ' + str(exc))
    return proc


def ffmpeg_version(ffmpeg):
    out = _run(ffmpeg, ['-version']).stdout.decode('utf-8', 'replace').splitlines()
    return out[0].strip()[:200] if out else 'unknown'


# ---------------------------------------------------------------- probing / decoding
def probe(ffmpeg, path):
    text = _run(ffmpeg, ['-i', str(path)]).stderr.decode('utf-8', 'replace')
    dur = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', text)
    aud = re.search(r'Stream #\d+:\d+[^:]*: Audio:\s*([^,\s]+)[^\n]*?(\d+) Hz,\s*([^,\n]+)', text)
    if not aud:
        _fail('audio_unreadable', Path(path).name + ': no decodable audio stream (is it really MP3/OGG/WAV?)')
    layout = aud.group(3).strip()
    channels = {'mono': 1, 'stereo': 2}.get(layout)
    if channels is None:
        m = re.match(r'(\d+)', layout)
        channels = int(m.group(1)) if m else (6 if '5.1' in layout else 2)
    seconds = (int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))) if dur else None
    return {'codec': aud.group(1), 'sample_rate': int(aud.group(2)), 'channels': channels, 'seconds': seconds}


def decode(ffmpeg, path, rate, channels):
    proc = _run(ffmpeg, ['-v', 'error', '-i', str(path), '-vn', '-map', '0:a:0', '-ac', str(channels),
                         '-ar', str(rate), '-f', 'f32le', '-acodec', 'pcm_f32le', '-'])
    if proc.returncode != 0 or not proc.stdout:
        _fail('audio_unreadable', Path(path).name + ': ffmpeg could not decode: ' +
              proc.stderr.decode('utf-8', 'replace').strip()[-300:])
    samples = array.array('f')
    samples.frombytes(proc.stdout[:len(proc.stdout) // 4 * 4])
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples


def loudness(ffmpeg, samples, rate, channels):
    """Integrated loudness (LUFS) of float samples via ffmpeg ebur128. Returns None when gated silent/too short."""
    data = samples.tobytes() if sys.byteorder == 'little' else _swapped(samples)
    proc = _run(ffmpeg, ['-v', 'info', '-f', 'f32le', '-ar', str(rate), '-ac', str(channels), '-i', 'pipe:0',
                         '-af', 'ebur128=framelog=quiet', '-f', 'null', '-'], data=data)
    text = proc.stderr.decode('utf-8', 'replace')
    m = re.findall(r'I:\s*(-?\d+(?:\.\d+)?)\s*LUFS', text)
    if not m:
        return None
    value = float(m[-1])
    return None if value <= -69.9 else value


def measure_file(ffmpeg, path):
    proc = _run(ffmpeg, ['-v', 'info', '-i', str(path), '-af', 'ebur128=framelog=quiet', '-f', 'null', '-'])
    m = re.findall(r'I:\s*(-?\d+(?:\.\d+)?)\s*LUFS', proc.stderr.decode('utf-8', 'replace'))
    return float(m[-1]) if m and float(m[-1]) > -69.9 else None


def _swapped(samples):
    copy = array.array('f', samples)
    copy.byteswap()
    return copy.tobytes()


# ---------------------------------------------------------------- DSP helpers (pure Python, bounded passes)
def db(x):
    return 20 * math.log10(x) if x > 0 else -200.0


def peak(samples):
    return max(max(samples), -min(samples)) if len(samples) else 0.0


def clipped_fraction(samples):
    if not len(samples):
        return 0.0
    n = sum(1 for v in samples if v >= CLIP_LEVEL or v <= -CLIP_LEVEL)
    return n / len(samples)


def trim(samples, channels, rate, threshold_dbfs, pad_ms):
    thr = 10 ** (threshold_dbfs / 20)
    frames = len(samples) // channels
    first = 0
    while first < frames and all(abs(samples[first * channels + c]) < thr for c in range(channels)):
        first += 1
    last = frames - 1
    while last > first and all(abs(samples[last * channels + c]) < thr for c in range(channels)):
        last -= 1
    pad = int(rate * pad_ms / 1000)
    start = max(0, first - pad)
    end = min(frames, last + 1 + pad)
    return samples[start * channels:end * channels], start / rate, (frames - end) / rate


def make_loop(samples, channels, rate, crossfade_ms):
    """Equal-power crossfade of the tail into the head. Output length = N - F; playing it end->start is continuous
    because the last output frame is x[N-F-1] and the first is (mostly) x[N-F]."""
    frames = len(samples) // channels
    fade = int(rate * crossfade_ms / 1000)
    fade = max(0, min(fade, frames // 3))
    if fade == 0:
        return samples, 0
    out = samples[:(frames - fade) * channels]
    tail = (frames - fade) * channels
    for i in range(fade):
        t = (i + 0.5) / fade
        gin = math.sin(t * math.pi / 2)
        gout = math.cos(t * math.pi / 2)
        for c in range(channels):
            k = i * channels + c
            out[k] = samples[k] * gin + samples[tail + k] * gout
    return out, fade


def seam_report(samples, channels, rate):
    """Numeric loop-seam quality (end -> start wrap). Lower is better for jump/click; rms delta near 0 dB.

    jump_ratio: |x[last]-x[0]| / mean |first difference| (max over channels). ~1 = indistinguishable from any
                other sample step; >>4 = audible click risk.
    click_db:   peak |diff| within +-5 ms of the seam over the RMS of all first differences, in dB.
    rms_delta_db: loudness step between the last and first 250 ms.
    """
    frames = len(samples) // channels
    if frames < 8:
        return {'jump_ratio': None, 'click_db': None, 'rms_delta_db': None, 'verdict': 'too_short'}
    step = max(1, frames // 200000)   # bounded cost on long tracks; deterministic stride
    jump, typical, click, diff_rms = 0.0, 0.0, 0.0, 0.0
    w = max(1, int(rate * 0.005))
    for c in range(channels):
        total, sq, n = 0.0, 0.0, 0
        for i in range(1, frames, step):
            d = samples[i * channels + c] - samples[(i - 1) * channels + c]
            total += abs(d); sq += d * d; n += 1
        mean_abs = total / max(1, n)
        rms_d = math.sqrt(sq / max(1, n))
        seam = abs(samples[c] - samples[(frames - 1) * channels + c])
        jump = max(jump, seam / max(mean_abs, 1e-9))
        local = seam
        for i in range(1, w):
            local = max(local, abs(samples[i * channels + c] - samples[(i - 1) * channels + c]))
            j = frames - i
            local = max(local, abs(samples[j * channels + c] - samples[(j - 1) * channels + c]))
        click = max(click, db(local / max(rms_d, 1e-9)))
        typical = max(typical, mean_abs); diff_rms = max(diff_rms, rms_d)
    win = min(frames // 2, int(rate * 0.25))

    def rms(a, b):
        s = 0.0
        for i in range(a * channels, b * channels):
            s += samples[i] * samples[i]
        return math.sqrt(s / max(1, (b - a) * channels))
    delta = db(rms(frames - win, frames) or 1e-12) - db(rms(0, win) or 1e-12)
    good = jump <= 4.0 and click <= 12.0 and abs(delta) <= 3.0
    return {'jump_ratio': round(jump, 3), 'click_db': round(click, 2), 'rms_delta_db': round(delta, 2),
            'verdict': 'seamless' if good else 'audible_risk'}


# ---------------------------------------------------------------- encoding
def encode_wav(ffmpeg, samples, rate, channels, gain_db, out_path, limit_dbfs=None):
    """Gain (+ optional deterministic look-ahead peak limiter) then 16-bit PCM. No dither: identical input and
    ffmpeg build give identical bytes."""
    data = samples.tobytes() if sys.byteorder == 'little' else _swapped(samples)
    chain = 'volume=%.4fdB:precision=double' % gain_db
    attempts = [chain]
    if limit_dbfs is not None:
        lim = 'alimiter=limit=%.5f:attack=5:release=60:level=0' % (10 ** (limit_dbfs / 20))
        attempts = [chain + ',' + lim + ':latency=1', chain + ',' + lim]   # latency= needs ffmpeg >= 5.1
    for af in attempts:
        proc = _run(ffmpeg, ['-v', 'error', '-f', 'f32le', '-ar', str(rate), '-ac', str(channels), '-i', 'pipe:0',
                             '-af', af, '-c:a', 'pcm_s16le',
                             '-bitexact', '-map_metadata', '-1', '-fflags', '+bitexact', '-flags', '+bitexact',
                             '-f', 'wav', '-y', str(out_path)], data=data)
        if proc.returncode == 0:
            break
    if proc.returncode != 0:
        _fail('encode_failed', 'ffmpeg WAV encode failed: ' + proc.stderr.decode('utf-8', 'replace')[-300:])
    with wave.open(str(out_path), 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != channels or w.getframerate() != rate:
            _fail('encode_failed', 'Encoded WAV has unexpected format')
        return w.getnframes()


# ---------------------------------------------------------------- planning
def slug(name):
    base = re.sub(r'[^a-z0-9]+', '_', Path(name).stem.lower()).strip('_')
    if not base or not base[0].isalpha():
        base = 'a_' + base
    return base[:64].rstrip('_')


def collect(sources, base=None):
    """Expand files and folders (non-recursive into hidden entries) to a sorted, de-duplicated file list."""
    out = []
    for raw in sources:
        path = Path(raw)
        if not path.is_absolute():
            if base is None:
                _fail('path', 'Relative source needs a project: ' + str(raw))
            path = Path(base) / path
        if '..' in path.parts:
            _fail('path', 'Traversal in source path rejected')
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
                if child.is_file() and not child.name.startswith('.') and child.suffix.lower() in EXTENSIONS:
                    out.append(child)
        elif path.is_file():
            if path.suffix.lower() not in EXTENSIONS:
                _fail('format', path.name + ': unsupported extension (use ' + ', '.join(EXTENSIONS) + ')')
            out.append(path)
        else:
            _fail('path', 'Source not found: ' + path.name)
    seen, unique = set(), []
    for p in out:
        key = os.path.normcase(str(p.absolute()))
        if key not in seen:
            seen.add(key); unique.append(p)
    if not unique:
        _fail('empty', 'No audio files found (supported: ' + ', '.join(EXTENSIONS) + ')')
    if len(unique) > MAX_FILES:
        _fail('limit', 'At most %d files per import' % MAX_FILES)
    return unique


def sha256_file(path):
    h = hashlib.sha256()
    with open(str(path), 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- one file
def process_one(ffmpeg, src, kind, ident, opts, out_dir):
    size = src.stat().st_size
    if size > MAX_SOURCE_BYTES:
        _fail('source_too_large', '%s: %d MiB source exceeds the %d MiB import limit'
              % (src.name, size >> 20, MAX_SOURCE_BYTES >> 20))
    info = probe(ffmpeg, src)
    if info['seconds'] is not None and info['seconds'] > MAX_SOURCE_SECONDS:
        _fail('source_too_long', '%s: %.0f s exceeds the %d s import limit' % (src.name, info['seconds'], MAX_SOURCE_SECONDS))
    if kind == 'auto':
        kind = 'music' if (info['seconds'] or 0) >= AUTO_MUSIC_SECONDS else 'voice'
    target = TARGETS[kind]
    loop = opts.get('loop', target['loop']) if kind == 'music' else bool(opts.get('loop', False))
    crossfade_ms = int(opts.get('crossfade_ms', DEFAULT_CROSSFADE_MS if loop else 0))
    max_file = int(opts.get('max_file_bytes', target['max_file_bytes']))
    max_seconds = opts.get('max_seconds')
    warnings = []
    ladder = target['ladder']
    attempts = []
    for rate, channels in ladder:
        samples = decode(ffmpeg, src, rate, channels)
        in_peak = peak(samples)
        if in_peak < SILENT_PEAK:
            _fail('silent', src.name + ': the file is silent (peak below -80 dBFS); nothing to import')
        clip = clipped_fraction(samples)
        samples, head, tail = trim(samples, channels, rate, target['trim_dbfs'], target['pad_ms'])
        start_s = float(opts.get('start_s') or 0)
        if start_s:
            samples = samples[int(start_s * rate) * channels:]
        if max_seconds:
            samples = samples[:int(float(max_seconds) * rate) * channels]
        if len(samples) < channels * int(rate * 0.05):
            _fail('too_short', src.name + ': less than 50 ms of audio after trimming/start_s/max_seconds')
        fade = 0
        if loop:
            samples, fade = make_loop(samples, channels, rate, crossfade_ms)
        frames = len(samples) // channels
        est = 44 + frames * channels * 2
        attempts.append({'sample_rate': rate, 'channels': channels, 'bytes': est})
        if est <= max_file:
            break
    else:
        _fail('size_cap', '%s: %.1f s of %s is %.1f MiB even at %d Hz %s; the cap is %.1f MiB. Pass max_seconds '
              '(shorter loop) or raise max_file_bytes.' % (src.name, frames / rate, kind, est / 1048576, rate,
                                                           'mono' if channels == 1 else 'stereo', max_file / 1048576))
    if len(attempts) > 1:
        warnings.append('size_ladder: reduced to %d Hz %s to fit %.1f MiB' % (rate, 'mono' if channels == 1 else 'stereo', max_file / 1048576))
    if clip >= CLIP_FRACTION:
        warnings.append('source_clipped: %.2f%% of source samples at full scale; normalisation lowers level but '
                        'cannot undo distortion' % (100 * clip))
    if info['sample_rate'] < rate:
        warnings.append('low_source_rate: source is %d Hz, upsampled to %d Hz (no new detail)' % (info['sample_rate'], rate))
    if info['channels'] != channels:
        warnings.append('%s: %d -> %d channels' % ('upmixed' if channels > info['channels'] else 'downmixed',
                                                   info['channels'], channels))
    lufs_in = loudness(ffmpeg, samples, rate, channels)
    pk = peak(samples)
    if lufs_in is None:
        # Too short for gated integrated loudness: fall back to RMS-based level (documented approximation).
        s = sum(v * v for v in samples) / max(1, len(samples))
        lufs_in = db(math.sqrt(s)) - 0.7
        warnings.append('loudness_rms_fallback: clip too short for EBU R128 gating; RMS level used')
    gain = target['lufs'] - lufs_in
    over = db(pk) + gain - CEILING_DBFS
    limit = None
    if over > 0:
        # Up to MAX_LIMIT_DB of peak reduction by a look-ahead limiter keeps the loudness target (spoken lines
        # have a high crest factor); beyond that, lower the gain instead of squashing the performance.
        if over > MAX_LIMIT_DB:
            gain -= over - MAX_LIMIT_DB
            warnings.append('peak_limited: gain lowered %.1f dB below the %.1f LUFS target to avoid heavy limiting'
                            % (over - MAX_LIMIT_DB, target['lufs']))
        limit = CEILING_DBFS - 0.3
        warnings.append('limiter: up to %.1f dB of peak reduction to keep peaks under %.1f dBFS'
                        % (min(over, MAX_LIMIT_DB), CEILING_DBFS))
    gain = round(gain, 3)
    seam = seam_report(samples, channels, rate) if loop else None
    if seam and seam['verdict'] != 'seamless':
        warnings.append('loop_seam: %s (jump %.2f, click %.1f dB, rms step %.1f dB); try a longer crossfade_ms'
                        % (seam['verdict'], seam['jump_ratio'], seam['click_db'], seam['rms_delta_db']))
    out_path = out_dir / (ident + '.wav')
    frames = encode_wav(ffmpeg, samples, rate, channels, gain, out_path, limit)
    out_lufs = measure_file(ffmpeg, out_path)
    raw = out_path.read_bytes()
    with wave.open(str(out_path), 'rb') as w:
        pcm = array.array('h'); pcm.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder != 'little':
        pcm.byteswap()
    out_peak = max(max(pcm), -min(pcm)) / 32768.0 if len(pcm) else 0.0
    return {
        'kind': kind, 'file': out_path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'sample_rate': rate, 'channels': channels, 'frames': frames, 'seconds': round(frames / rate, 4),
        'loop': ({'begin': 0, 'end': frames, 'crossfade_ms': round(fade * 1000 / rate), 'seam': seam} if loop else None),
        'loudness': {'target_lufs': target['lufs'], 'measured_lufs': round(lufs_in, 2), 'gain_db': gain,
                     'output_lufs': out_lufs, 'limited': limit is not None, 'peak_dbfs': round(db(out_peak), 2)},
        'trimmed_s': {'head': round(head, 4), 'tail': round(tail, 4)},
        'source': {'name': src.name, 'sha256': sha256_file(src), 'bytes': size, 'codec': info['codec'],
                   'sample_rate': info['sample_rate'], 'channels': info['channels'],
                   'seconds': round(info['seconds'], 3) if info['seconds'] else None,
                   'clipped_fraction': round(clip, 6)},
        'size_attempts': attempts, 'warnings': warnings}


# ---------------------------------------------------------------- batch
def import_audio(out_dir, sources, ffmpeg, kind='auto', items=None, options=None, replace=False, base=None,
                 max_total_bytes=DEFAULT_TOTAL_BYTES):
    """Import into out_dir (created). Existing manifest entries are kept; same id needs replace=True.
    Work happens in a staging folder; nothing in out_dir changes unless every file and the budget pass."""
    options = dict(options or {})
    out_dir = Path(out_dir)
    plan = []
    for row in (items or []):
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            _fail('arguments', 'Each item needs a path (plus optional id, kind, loop, crossfade_ms, max_seconds)')
        src = collect([row['path']], base)[0]
        plan.append((src, row.get('kind', kind), row.get('id') or slug(src.name), {k: row[k] for k in row
                     if k in ('loop', 'crossfade_ms', 'start_s', 'max_seconds', 'max_file_bytes')}))
    if sources:
        for src in collect(sources, base):
            plan.append((src, kind, slug(src.name), {}))
    if not plan:
        _fail('empty', 'Give sources (files/folders) or items')
    ids = [p[2] for p in plan]
    for ident in ids:
        if not ID_RE.match(ident):
            _fail('id', 'Invalid asset id %r (lowercase letters, digits, _ . -; starts with a letter)' % ident)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        _fail('id', 'Two sources map to the same id: ' + ', '.join(dupes) + ' (give explicit items ids)')
    for _, k, _, _ in plan:
        if k not in KINDS + ('auto',):
            _fail('kind', 'kind must be music, voice, sfx or auto')
    manifest_path = out_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8')) if manifest_path.is_file() else None
    if manifest is not None and manifest.get('generator') != GENERATOR:
        _fail('manifest', 'Existing manifest was not written by ' + GENERATOR)
    assets = dict((manifest or {}).get('assets', {}))
    clash = sorted(i for i in ids if i in assets)
    if clash and not replace:
        _fail('exists', 'Already imported: ' + ', '.join(clash) + ' (pass replace=true to re-import)')
    staging = out_dir / '.staging'
    if staging.exists():
        shutil.rmtree(str(staging))
    staging.mkdir(parents=True)
    try:
        new = {}
        for src, k, ident, extra in plan:
            merged = dict(options); merged.update(extra)
            new[ident] = process_one(ffmpeg, src, k, ident, merged, staging)
        combined = dict(assets); combined.update(new)
        total = sum(a['bytes'] for a in combined.values())
        if total > max_total_bytes:
            _fail('size_budget', 'Imported audio would total %.1f MiB, over the %.1f MiB web budget. Largest: %s. '
                  'Lower max_seconds on music or raise max_total_bytes.' % (total / 1048576, max_total_bytes / 1048576,
                  ', '.join('%s %.1f MiB' % (i, a['bytes'] / 1048576) for i, a in sorted(combined.items(),
                            key=lambda kv: -kv[1]['bytes'])[:3])))
        for ident, row in new.items():
            os.replace(str(staging / row['file']), str(out_dir / row['file']))
    finally:
        shutil.rmtree(str(staging), ignore_errors=True)
    manifest = {'format': 1, 'generator': GENERATOR, 'ffmpeg': ffmpeg_version(ffmpeg),
                'targets': {k: {'lufs': v['lufs'], 'max_file_bytes': v['max_file_bytes'],
                                'ladder': [list(x) for x in v['ladder']]} for k, v in TARGETS.items()},
                'ceiling_dbfs': CEILING_DBFS, 'assets': dict(sorted(combined.items())),
                'budget': size_report(combined, max_total_bytes)}
    manifest_path.write_bytes((json.dumps(manifest, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return manifest, sorted(new)


def size_report(assets, max_total_bytes=DEFAULT_TOTAL_BYTES):
    by_kind = {}
    for a in assets.values():
        by_kind[a['kind']] = by_kind.get(a['kind'], 0) + a['bytes']
    total = sum(by_kind.values())
    return {'total_bytes': total, 'max_total_bytes': max_total_bytes, 'by_kind_bytes': dict(sorted(by_kind.items())),
            'within_budget': total <= max_total_bytes,
            'note': 'Web export ships these WAVs inside the .pck; the budget keeps first load reasonable.'}


def verify(out_dir):
    """Re-hash every manifest asset; returns problems (empty list = consistent)."""
    out_dir = Path(out_dir)
    manifest = json.loads((out_dir / 'manifest.json').read_text('utf-8'))
    problems = []
    for ident, row in manifest['assets'].items():
        path = out_dir / row['file']
        if not path.is_file():
            problems.append(ident + ': missing ' + row['file'])
        elif sha256_file(path) != row['sha256']:
            problems.append(ident + ': hash mismatch')
    return manifest, problems


# ---------------------------------------------------------------- slots (project data)
SLOT_MUSIC_FIXED = ('default', 'menu', 'results', 'boss')
SLOT_KEY = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
MIX_DEFAULT = {'music_db': -6.0, 'voice_db': -3.0, 'sfx_db': -6.0, 'crossfade_s': 1.5}


def validate_slots(slots, assets):
    """Check a slots document against the imported manifest. Returns a normalised copy."""
    if not isinstance(slots, dict):
        _fail('slots', 'slots must be an object')
    unknown = set(slots) - {'format', 'music', 'voice', 'cues', 'mix', 'combat_sfx'}
    if unknown:
        _fail('slots', 'Unknown slots fields: ' + ', '.join(sorted(unknown)))

    def ref(value, kinds, where):
        if not isinstance(value, str) or value not in assets:
            _fail('slots', '%s: %r is not an imported asset id' % (where, value))
        if assets[value]['kind'] not in kinds:
            _fail('slots', '%s: %s is %s, expected %s' % (where, value, assets[value]['kind'], '/'.join(kinds)))
        return value

    def keyed(obj, where):
        if not isinstance(obj, dict):
            _fail('slots', where + ' must be an object')
        for k in obj:
            if not SLOT_KEY.match(str(k)):
                _fail('slots', '%s key %r invalid' % (where, k))
        return obj
    out = {'format': 1, 'music': {}, 'voice': {}, 'cues': {}, 'mix': dict(MIX_DEFAULT)}
    music = keyed(slots.get('music', {}), 'music')
    for k, v in music.items():
        if k in SLOT_MUSIC_FIXED:
            out['music'][k] = ref(v, ('music',), 'music.' + k)
        elif k in ('scenes', 'waves', 'events'):
            out['music'][k] = {kk: ref(vv, ('music',), 'music.%s.%s' % (k, kk)) for kk, vv in keyed(v, 'music.' + k).items()}
        else:
            _fail('slots', 'music.%s unknown (use %s, scenes, waves, events)' % (k, ', '.join(SLOT_MUSIC_FIXED)))
    for line, v in keyed(slots.get('voice', {}), 'voice').items():
        row = {'asset': v} if isinstance(v, str) else v
        if not isinstance(row, dict) or set(row) - {'asset', 'on_action', 'on_scene', 'on_event'}:
            _fail('slots', 'voice.%s must be an asset id or {asset, on_action?, on_scene?, on_event?}' % line)
        ref(row.get('asset'), ('voice', 'sfx'), 'voice.' + line)
        for hook in ('on_action', 'on_scene', 'on_event'):
            if hook in row and not (isinstance(row[hook], str) and 0 < len(row[hook]) <= 128):
                _fail('slots', 'voice.%s.%s must be a short string' % (line, hook))
        out['voice'][line] = row
    for event, v in keyed(slots.get('cues', {}), 'cues').items():
        out['cues'][event] = ref(v, ('sfx', 'voice', 'music'), 'cues.' + event)
    mix = slots.get('mix', {})
    if not isinstance(mix, dict) or set(mix) - set(MIX_DEFAULT):
        _fail('slots', 'mix accepts ' + ', '.join(MIX_DEFAULT))
    for k, v in mix.items():
        lo, hi = (0.0, 10.0) if k == 'crossfade_s' else (-40.0, 6.0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
            _fail('slots', 'mix.%s must be a number in [%g, %g]' % (k, lo, hi))
        out['mix'][k] = float(v)
    if 'combat_sfx' in slots:
        out['combat_sfx'] = combat_sfx_slots(slots['combat_sfx'], ref)
    return out


# COMBATFIX: combat event sounds. `combat_sfx` is "default" (every event, the shipped original set) or
# {event: "default" | imported sfx id | [ids, up to 4 variants]}; events left out stay silent and keep the stock cue.
COMBAT_SFX_EVENTS = ('punch_hit', 'punch_miss', 'robot_hit', 'boss_hit', 'player_hurt', 'dodge', 'block', 'robot_death',
                     'boss_telegraph')
COMBAT_SFX_DIR = Path(__file__).resolve().parent.parent / 'audio' / 'combat_sfx'


def combat_sfx_slots(value, ref):
    if value == 'default':
        return {e: 'default' for e in COMBAT_SFX_EVENTS}
    if not isinstance(value, dict) or not value:
        _fail('slots', 'combat_sfx must be "default" or an object {event: "default" | sfx asset id | [ids]}')
    out = {}
    for event, v in value.items():
        if event not in COMBAT_SFX_EVENTS:
            _fail('slots', 'combat_sfx.%s unknown (use %s)' % (event, ', '.join(COMBAT_SFX_EVENTS)))
        ids = [v] if isinstance(v, str) else v
        if not isinstance(ids, list) or not 1 <= len(ids) <= 4:
            _fail('slots', 'combat_sfx.%s must be "default", an sfx asset id or a list of 1-4 ids' % event)
        out[event] = 'default' if ids == ['default'] else [ref(i, ('sfx',), 'combat_sfx.' + event) for i in ids]
    return out


def combat_sfx_defaults():
    """The shipped original set (audio/combat_sfx/combat_sfx.json): event -> [file paths], each hash-checked."""
    manifest = json.loads((COMBAT_SFX_DIR / 'combat_sfx.json').read_text(encoding='utf-8'))
    out = {}
    for name in sorted(manifest['files']):
        row = manifest['files'][name]
        path = COMBAT_SFX_DIR / name
        if not path.is_file() or sha256_file(path) != row['sha256']:
            _fail('asset_integrity', 'Default combat sound changed or missing: ' + name)
        out.setdefault(row['event'], []).append((str(path), row['sha256']))
    return out


def runtime_rows(slots, assets, folder_path):
    """Lower validated slots into runtime audio.json rows (event -> {path, sha256, ...}).

    music:<slot>, music:scene:<room>, music:wave:<n>, music:event:<kind>, voice:<line>, and cue rows that either
    override a named event (ambient/interact) or add cue:<id>. Every row keeps path+sha256 so the existing hash check,
    physical receipts and release closure treat it like any other audio row."""
    mix = slots['mix']
    rows = {}

    def base(ident, gain):
        a = assets[ident]
        return {'path': str(Path(folder_path) / a['file']), 'sha256': a['sha256'], 'gain_db': gain}
    for slot, value in slots['music'].items():
        targets = value.items() if isinstance(value, dict) else [(None, value)]
        for sub, ident in targets:
            key = 'music:' + slot if sub is None else 'music:%s:%s' % (slot[:-1], sub)
            row = base(ident, mix['music_db'])
            a = assets[ident]
            row.update(kind='music', fade_s=mix['crossfade_s'], loop=a['loop'] is not None,
                       loop_end=(a['loop'] or {}).get('end', a['frames']))
            rows[key] = row
    for line, v in slots['voice'].items():
        row = base(v['asset'], mix['voice_db'])
        row['kind'] = 'voice'
        for hook in ('on_action', 'on_scene', 'on_event'):
            if hook in v:
                row[hook] = v[hook]
        rows['voice:' + line] = row
    for event, ident in slots['cues'].items():
        row = base(ident, mix['sfx_db'])
        row['kind'] = 'sfx'
        rows[event if event in ('ambient', 'interact') or event.startswith('cue:') else 'cue:' + event] = row
    defaults = combat_sfx_defaults() if 'default' in slots.get('combat_sfx', {}).values() else {}
    for event, value in sorted(slots.get('combat_sfx', {}).items()):
        files = defaults.get(event, []) if value == 'default' else [(str(Path(folder_path) / assets[i]['file']), assets[i]['sha256']) for i in value]
        for n, (path, digest) in enumerate(files, 1):
            rows['sfx:%s:%d' % (event, n)] = {'path': path, 'sha256': digest, 'gain_db': mix['sfx_db'], 'kind': 'sfx'}
    return rows
