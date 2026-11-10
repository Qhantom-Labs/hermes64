"""Load the vendored character generator (characters/gen/core) as a private package, without Blender.

The generator modules use package-relative imports (`from . import pose`). They are loaded under a private package
name per root so several roots (the vendored copy, the read-only oracle lane for parity) can coexist in one process.
Only Blender-free modules are ever imported here: core/blender.py and core/combat_blender.py import bpy and are
replaced by adventure_maker/nbchars/assemble.py.
"""
import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

from . import pycompat

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / 'characters' / 'gen'
_LOADED = {}


class _CompatLoader(importlib.machinery.SourceFileLoader):
    """Source loader that makes generator modules compute like CPython 3.13 (see pycompat.py)."""

    def exec_module(self, module):
        pycompat.install(module)
        super().exec_module(module)
        pycompat.install_after(module)


class _Finder:
    def __init__(self, pkg, core):
        self.pkg, self.core = pkg, Path(core)

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.pkg + '.'):
            return None
        name = fullname[len(self.pkg) + 1:]
        f = self.core / (name + '.py')
        if '.' in name or not f.is_file():
            return None
        return importlib.util.spec_from_file_location(fullname, str(f), loader=_CompatLoader(fullname, str(f)))

    def invalidate_caches(self):
        pass


class Generator:
    """Handle on one generator root: .core(name) -> module, .pack(name) -> dict, .packs_dir."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        core = self.root / 'core'
        if not (core / 'pose.py').is_file():
            raise FileNotFoundError('no generator core at %s' % core)
        self.pkg = '_nbchars_gen_' + hashlib.sha256(str(core).encode()).hexdigest()[:12]
        if not any(isinstance(f, _Finder) and f.pkg == self.pkg for f in sys.meta_path):
            sys.meta_path.insert(0, _Finder(self.pkg, core))
        if self.pkg not in sys.modules:
            spec = importlib.util.spec_from_file_location(self.pkg, str(core / '__init__.py') if (core / '__init__.py').is_file() else None,
                                                          submodule_search_locations=[str(core)])
            if spec is None or spec.loader is None:
                spec = importlib.machinery.ModuleSpec(self.pkg, None, is_package=True)
                spec.submodule_search_locations = [str(core)]
                mod = importlib.util.module_from_spec(spec)
            else:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            sys.modules[self.pkg] = mod
        self.packs_dir = self.root / 'packs'
        self._packs = {}
        self.inline = {}

    def core(self, name):
        if name in ('blender', 'combat_blender'):
            raise ImportError('core/%s.py needs Blender; the python exporter never imports it' % name)
        if os.environ.get('COMBAT_GRIP_TILT_DEG') is not None and name in ('weapon', 'combat'):
            raise RuntimeError('COMBAT_GRIP_TILT_DEG must not be set: core/weapon.py reads it at import time')
        return importlib.import_module(self.pkg + '.' + name)

    def pack(self, name):
        if name in self.inline:
            return json.loads(json.dumps(self.inline[name]['pack']))
        if name not in self._packs:
            self._packs[name] = json.loads((self.packs_dir / name / 'pack.json').read_text())
        return json.loads(json.dumps(self._packs[name]))

    def combat_roles(self, pack):
        if pack['id'] in self.inline:
            return dict(self.inline[pack['id']].get('combat_roles', {}))
        p = self.packs_dir / pack['id'] / 'combat_roles.json'
        return json.loads(p.read_text()) if p.is_file() else {}


def load(root=None):
    root = Path(root or os.environ.get('NBCHARS_GENERATOR_ROOT') or DEFAULT_ROOT).resolve()
    key = str(root)
    if key not in _LOADED:
        _LOADED[key] = Generator(root)
    return _LOADED[key]
