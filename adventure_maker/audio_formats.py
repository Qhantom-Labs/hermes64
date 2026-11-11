"""Audio file intake routes with no bundled decoder (ZEROSETUP lane). Stdlib only.

Safest default, decided from what is on disk:
- WAV (PCM): read and processed in pure Python (``wave`` + adventure_maker/audio_dsp.py). Nothing extra.
- OGG Vorbis and MP3: Godot 4.6.2 plays both natively (AudioStreamOggVorbis, AudioStreamMP3), so they need no
  decoder in the plugin; they are recognised from their headers and passed through unchanged.
- Anything else (FLAC, AAC/M4A, Opus, AIFF, ...): needs a converter. ffmpeg is OPTIONAL and is used only from
  an explicit path (HERMES64_FFMPEG) or the pinned lookup path tools/bin/<platform>/ffmpeg[.exe] whose sha256
  must match tools/bin/MANIFEST.json. A random ffmpeg on PATH is never picked up silently (its licence and build
  are unknown: Homebrew's is a GPL build linked to 30+ shared libraries).
Nothing here downloads anything.
"""
import hashlib
import json
import os
import platform
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'tools' / 'bin'
ENV_FFMPEG = 'HERMES64_FFMPEG'
NATIVE = ('wav', 'ogg_vorbis', 'mp3')


def platform_key(system=None, machine=None):
    system = (system or sys.platform).lower()
    machine = (machine or platform.machine()).lower()
    arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x86_64' if machine in ('x86_64', 'amd64', 'x64') else machine
    name = 'darwin' if system.startswith('darwin') else 'windows' if system.startswith(('win', 'cygwin')) else 'linux'
    return name + '-' + arch


def sniff(head):
    """Format from the first bytes (at least 64 recommended). Never decodes audio."""
    if len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        return 'wav'
    if head[:4] == b'OggS':
        if b'\x01vorbis' in head[:128]:
            return 'ogg_vorbis'
        if b'OpusHead' in head[:128]:
            return 'ogg_opus'
        return 'ogg_other'
    if head[:3] == b'ID3':
        return 'mp3'
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        # MPEG audio frame sync; Layer III (bits 0x06 == 01) with a valid version (bits 0x18 != 01).
        return 'mp3' if (head[1] & 0x06) == 0x02 and (head[1] & 0x18) != 0x08 else 'mpeg_other'
    if head[:4] == b'fLaC':
        return 'flac'
    if len(head) >= 12 and head[4:8] == b'ftyp':
        return 'mp4_audio'
    if head[:4] == b'FORM' and head[8:12] in (b'AIFF', b'AIFC'):
        return 'aiff'
    return 'unknown'


def wav_info(raw):
    """Channels, rate, bits and seconds for a PCM WAV, read from its chunks (no wave module, so a broken header
    gives a clear error instead of an exception deep in decoding)."""
    if len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError('not a RIFF/WAVE file')
    pos, fmt, size = 12, None, None
    while pos + 8 <= len(raw):
        cid, clen = raw[pos:pos + 4], struct.unpack('<I', raw[pos + 4:pos + 8])[0]
        if cid == b'fmt ' and clen >= 16:
            fmt = struct.unpack('<HHIIHH', raw[pos + 8:pos + 24])
        elif cid == b'data':
            size = min(clen, len(raw) - pos - 8)
        pos += 8 + clen + (clen & 1)
    if fmt is None or size is None:
        raise ValueError('WAV is missing its fmt or data chunk')
    tag, channels, rate, _, align, bits = fmt
    if tag not in (1, 0xFFFE) or not channels or not rate or not align:
        raise ValueError('WAV is not plain PCM (format tag %d); convert it to 16-bit PCM WAV' % tag)
    return {'channels': channels, 'sample_rate': rate, 'bits': bits, 'seconds': round(size / (align * rate), 3)}


def route(path):
    """{'format', 'route': native_python|native_godot|needs_converter, 'message'} for one file."""
    path = Path(path)
    with open(path, 'rb') as f:
        head = f.read(256)
    fmt = sniff(head)
    if fmt == 'wav':
        try:
            info = wav_info(path.read_bytes())
        except ValueError as exc:
            return {'format': fmt, 'route': 'refused', 'message': str(exc)}
        return dict(info, format=fmt, route='native_python', message='WAV: read in pure Python, nothing to install')
    if fmt in ('ogg_vorbis', 'mp3'):
        return {'format': fmt, 'route': 'native_godot',
                'message': '%s: Godot 4.6.2 plays it natively; kept as is, nothing to install' % fmt.replace('_', ' ')}
    exe, why = find_ffmpeg()
    if exe:
        return {'format': fmt, 'route': 'needs_converter', 'converter': exe,
                'message': '%s: will be converted to WAV with the pinned ffmpeg' % fmt}
    return {'format': fmt, 'route': 'needs_converter', 'converter': None,
            'message': '%s is not WAV, OGG Vorbis or MP3. Convert it to one of those, or %s' % (fmt, why)}


def manifest():
    try:
        return json.loads((BIN / 'MANIFEST.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'binaries': {}}


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def find_ffmpeg(env=None, key=None):
    """(path, None) for an allowed ffmpeg, else (None, one-sentence reason with exactly one fix)."""
    env = os.environ if env is None else env
    explicit = env.get(ENV_FFMPEG, '')
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p), None
        return None, '%s points to %r, which is not an executable file' % (ENV_FFMPEG, explicit)
    key = key or platform_key()
    name = 'ffmpeg.exe' if key.startswith('windows') else 'ffmpeg'
    pinned = BIN / key / name
    row = manifest().get('binaries', {}).get(key, {})
    if not pinned.is_file():
        return None, ('place a licence-reviewed ffmpeg at tools/bin/%s/%s (optional; see docs/ZEROSETUP-RESULT.md) '
                      'or set %s to an ffmpeg you trust' % (key, name, ENV_FFMPEG))
    want = row.get('sha256') or ''
    if not want or want.startswith('TODO'):
        return None, 'tools/bin/%s/%s has no pinned sha256 in tools/bin/MANIFEST.json yet, so it is not used' % (key, name)
    if _sha(pinned) != want:
        return None, 'tools/bin/%s/%s does not match its pinned sha256; delete it' % (key, name)
    return str(pinned), None


def convert_argv(ffmpeg, source, dest, rate=22050):
    """Fixed argv: any input -> 16-bit PCM mono WAV at the plugin's sample rate. No network protocols."""
    return [ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-protocol_whitelist', 'file', '-i', str(source),
            '-vn', '-map_metadata', '-1', '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_s16le', '-f', 'wav', '-y', str(dest)]
