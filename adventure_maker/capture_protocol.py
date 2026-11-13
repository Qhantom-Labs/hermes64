"""Linux capture protocol and narrowly classified device diagnostics.

A rendered process is not a pass without its marker, complete room/file manifest,
CRC-valid decoded PNGs and nonblank primary frames. No style thresholds live here.
"""
from pathlib import Path
import re
import struct
import zlib

from .safety import Fault, inspect_path
from .style_gate import read_png

_FATAL = re.compile(r'SCRIPT ERROR|Parse Error|Failed to load|BOOT ERROR|\bCRASH\b|\bcrashed\b|\bsegmentation fault\b|\bsignal\s+\d+', re.I)
_ALSA = re.compile(r"ALSA lib (?:confmisc|conf|pcm)\.c:\d+:\([a-z_]+\) (?:cannot find card '[^']+'|function snd_func_[a-z_]+ returned error: No such file or directory|error evaluating (?:strings|name)|Evaluate error: No such file or directory|Unknown PCM default)$")
_AUDIO = 'ERROR: Condition "status < 0" is true. Returning: ERR_CANT_OPEN'
_AUDIO_SITE = re.compile(r'at: init_output_device \(drivers/alsa/audio_driver_alsa\.cpp:\d+\)$')
_X11 = '_XSERVTransmkdir: ERROR: euid != 0,directory /tmp/.X11-unix will not be created.'


def diagnostics(stdout, stderr):
    """Retain raw logs; exempt only known device messages, never script/crash/load errors."""
    benign, fatal = [], []
    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if _FATAL.search(s):
            fatal.append(line)
        elif s == _X11 or _ALSA.fullmatch(s) or (s == _AUDIO and i + 1 < len(lines) and
                _AUDIO_SITE.fullmatch(lines[i + 1].strip())) or _AUDIO_SITE.fullmatch(s) or s in (
                'WARNING: All audio drivers failed, falling back to the dummy driver.',
                'WARNING: Could not set V-Sync mode, as changing V-Sync mode is not supported by the graphics driver.') or re.fullmatch(
                r'at: (?:initialize \(servers/audio/audio_server\.cpp|set_use_vsync \(platform/linuxbsd/x11/gl_manager_x11\.cpp):\d+\)', s):
            benign.append(line)
        elif 'ERROR:' in s:
            fatal.append(line)  # unknown ERROR is still a failure, even beside an allowed device error
    fatal += [line for line in stdout.splitlines() if _FATAL.search(line) or 'ERROR:' in line]
    return benign, fatal


def png(path, resolution=None, nonblank=False):
    """Bounded CRC/container check before the existing stdlib decoder (which alone accepts truncation)."""
    inspect_path(path)
    size = path.stat().st_size
    if not 64 <= size <= 32 * 1024 * 1024:
        raise ValueError('missing/empty/oversize PNG: ' + path.name)
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG: ' + path.name)
    pos, ended, dimensions = 8, False, None
    while pos + 12 <= len(raw):
        length = struct.unpack('>I', raw[pos:pos + 4])[0]
        end = pos + length + 12
        if end > len(raw):
            raise ValueError('truncated PNG: ' + path.name)
        tag, body = raw[pos + 4:pos + 8], raw[pos + 8:end - 4]
        crc = struct.unpack('>I', raw[end - 4:end])[0]
        if zlib.crc32(tag + body) & 0xffffffff != crc:
            raise ValueError('PNG CRC mismatch: ' + path.name)
        if pos == 8:
            if tag != b'IHDR' or length != 13:
                raise ValueError('missing PNG header: ' + path.name)
            dimensions = list(struct.unpack('>II', body[:8]))
            w, h = dimensions
            if not (16 <= w <= 8192 and 16 <= h <= 8192 and w * h <= 8 * 1024 * 1024):
                raise ValueError('PNG dimensions out of bounds: ' + path.name)
        pos = end
        if tag == b'IEND':
            ended = length == 0 and pos == len(raw)
            break
    if not ended or (resolution is not None and dimensions != resolution):
        raise ValueError('incomplete PNG or wrong dimensions: ' + path.name)
    w, h, pixels = read_png(path)
    if len(pixels) != w * h * 3:
        raise ValueError('incomplete decoded image: ' + path.name)
    # Flat masks/depth passes are legal; a totally uniform game/clean/world frame is not.
    if nonblank and pixels == pixels[:3] * (w * h):
        raise ValueError('blank capture: ' + path.name)


def assess(project, folder, process, expected_rooms):
    benign, errors = diagnostics(process.get('stdout', ''), process.get('stderr', ''))
    process['benign_stderr'] = benign
    if process.get('returncode') != 0:
        errors.append('capture process exit %s' % process.get('returncode'))
    cap = process.get('capture') or {}
    rooms = cap.get('rooms') or []
    expected = [r['id'] for r in expected_rooms]
    received = [r.get('id') for r in rooms if isinstance(r, dict)]
    if (cap.get('status') != 'passed' or not expected or any(not isinstance(r, str) for r in received) or
            sorted(received) != sorted(expected) or
            len(set(received)) != len(received) or cap.get('missing_assets')):
        errors.append('capture manifest incomplete or failed')
    marks = re.findall(r'^CAPTURE status=(\w+) rooms=(\d+) missing=(\d+)$', process.get('stdout', ''), re.M)
    if marks != [('passed', str(len(expected)), '0')]:
        errors.append('missing/inconsistent CAPTURE status=passed marker')
    resolution = cap.get('resolution')
    if not isinstance(resolution, list) or len(resolution) != 2 or any(type(n) is not int for n in resolution):
        errors.append('missing capture resolution')
    checked = set()
    try:
        screens = project.path(folder + '/screens')
        for row in rooms:
            rid = row['id']
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', rid) or row.get('status') != 'passed':
                raise ValueError('invalid/failed room capture')
            files = [(row.get('screenshot'), None, True), (rid + '-world.png', resolution, True)]
            files += [(row.get(k), resolution, k == 'clean') for k in ('clean', 'key', 'depth', 'mask', 'noglow', 'classic')]
            if row.get('closeup'):
                files.append((row['closeup'].get('file'), resolution, True))
            for name, dims, nonblank in files:
                if not isinstance(name, str) or not re.fullmatch(re.escape(rid) + r'(?:-[a-z]+)?\.png', name) or name in checked:
                    raise ValueError('missing/unsafe/duplicate capture filename')
                png(screens / name, dims, nonblank)
                checked.add(name)
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error, zlib.error, Fault) as exc:
        errors.append(str(exc))
    result = {'status': 'failed' if errors else 'passed', 'png_count': len(checked), 'errors': errors}
    process['capture_validation'] = result
    return not errors
