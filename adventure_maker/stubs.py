"""Official Godot 4.6.2 export players kept by `/hermes64 setup --fetch --templates` (CAT-FIX F4).

The exporter reads three files from the official export templates: ``web_nothreads_release.zip``, ``macos.zip`` and
``windows_release_x86_64.exe``. When Godot's own export_templates folder lacks them, this module offers the copies
the setup fetch kept from the official, SHA-512-pinned ``.tpz`` in the per-user hermes64 cache. Nothing here
downloads, unpacks or builds anything, and nothing self-hosted or repackaged is accepted: a file is used only when
its bytes equal the official sha256 pinned in ``export.TEMPLATE_HASHES``. (Module name kept for the exporter's
existing import; the former self-hosted stub bundle is gone.)
"""
import hashlib
import os
import sys
from pathlib import Path

VERSION = '4.6.2.stable'
ENV_CACHE = 'HERMES64_TEMPLATE_CACHE'   # test/owner override of the cache folder; never a download source


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _official():
    from .export import TEMPLATES, TEMPLATE_HASHES
    return TEMPLATES, TEMPLATE_HASHES


def accepted(target, path):
    """Official template bytes only."""
    _, hashes = _official()
    path = Path(path)
    return path.is_file() and not path.is_symlink() and sha256_file(path) == hashes[target]


def cache_dir():
    """<hermes64 cache>/templates/4.6.2.stable, the folder godot_fetch.install_templates fills."""
    if os.environ.get(ENV_CACHE):
        return Path(os.environ[ENV_CACHE])
    from . import godot_fetch
    try:
        return godot_fetch.template_dir(godot_fetch.cache_dir())
    except godot_fetch.FetchError:  # Linux: no pinned fetch; read the XDG cache only
        base = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'hermes64'
        return godot_fetch.template_dir(base)


def template(target):
    """Path to the kept official player for ``target``, or None when setup has not fetched it.

    Raises ValueError when a file is present but differs from the pinned official bytes (never falls through to an
    unverified file)."""
    names, _ = _official()
    path = cache_dir() / names[target]
    if not path.is_file():
        return None
    if not accepted(target, path):
        raise ValueError('%s in the hermes64 cache does not match the pinned official Godot bytes; delete it and '
                         'rerun /hermes64 setup --fetch --templates' % names[target])
    return path


def status():
    """For the setup checklist: which targets the fetched cache holds (presence only; hashes are checked at export)."""
    names, _ = _official()
    folder = cache_dir()
    targets = {t: (folder / name).is_file() for t, name in names.items()}
    return {'cache': str(folder) if any(targets.values()) else None, 'targets': targets}
