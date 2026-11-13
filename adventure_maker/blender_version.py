"""Blender version facts. No installs; sanitized, bounded version-only children."""
import re
import subprocess
from .runner import scratch_env

TESTED = '5.2.1'
_CACHE = {}


def probe(path, run=subprocess.run):
    """Version reported by the executable, or None on an unreadable/failed probe."""
    try:
        from pathlib import Path
        st = Path(path).stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key in _CACHE:
        return _CACHE[key]
    try:
        with scratch_env() as env:
            flags = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)} if __import__('os').name == 'nt' else {}
            out = run([str(path), '--version'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                      timeout=10, stdin=subprocess.DEVNULL, env=env, **flags)
        match = re.search(r'^Blender (\d+\.\d+\.\d+)\b', out.stdout or '', re.M)
        value = match.group(1) if out.returncode == 0 and match else None
    except (OSError, subprocess.SubprocessError):
        value = None
    if key is not None:
        _CACHE[key] = value
    return value


def rank(version):
    """Prefer the exact measured version, then compatibility candidates, then unknown versions."""
    if version == TESTED:
        return 0
    parts = tuple(map(int, version.split('.'))) if version else ()
    return 1 if parts and (parts[0] == 5 or (parts[0] == 4 and 2 <= parts[1] <= 5)) else 2


def note(version):
    if version == TESTED:
        return version + ' (measured on Mac; platform rerun still required)'
    return (version or 'version unknown') + ' WARNING: outside the tested version; 4.2–4.5 LTS / 5.x compatibility candidate, real-run acceptance pending'


def row(record):
    if not record.get('available'):
        return 'absent   Blender (optional)'
    version = record.get('version')
    return '%s  Blender (optional): %s' % ('OK     ' if version == TESTED else 'WARN   ', note(version))
