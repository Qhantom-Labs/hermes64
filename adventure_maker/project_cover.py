"""Optional `cover` field for portable project manifests (project.json), backwards compatible.

project_model.py and contracts/project/1.0.0.json are NOT changed: the 1.0.0 manifest stays closed
(additionalProperties false). This module owns the one optional extra field:

  * a manifest WITHOUT `cover` passes through untouched (same bytes, same validation as before);
  * a manifest WITH `cover` is validated here: the cover block against contracts/cover/project-cover-1.0.0.json and
    the files it names (confined, present, the scene hash re-derived), the rest by project_model.validate_manifest.

Readers that call project_model.validate_manifest directly on a manifest carrying `cover` reject it (closed schema);
they should call project_cover.validate_manifest, or strip the field with split(). The Studio scanner reads raw JSON
and never validates project.json against the closed contract, so it can pick the field up (docs/COVER-INTEGRATION.md).
Stdlib only.
"""
import copy
import hashlib
from pathlib import Path

from . import project_model
from . import style_profile as style

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'contracts/cover/project-cover-1.0.0.json'
FIELD = 'cover'


class CoverFieldError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def split(manifest):
    """(manifest without `cover`, cover block or None) -- the base is what project_model validates."""
    if not isinstance(manifest, dict):
        raise CoverFieldError('SCHEMA', 'manifest must be an object')
    base = copy.deepcopy(manifest)
    cover = base.pop(FIELD, None)
    return base, cover


def validate_cover(cover, root=None):
    try:
        style.canonical_bytes(cover)
        style.validate_schema(cover, style.parse_json(style.read_confined(ROOT, CONTRACT)))
    except style.StyleError as exc:
        raise CoverFieldError(exc.code, str(exc)) from exc
    if root is not None:
        for key in ('scene', 'box', 'box_1x', 'banner', 'square', 'card_alpha', 'studio_art'):
            if key not in cover:
                continue
            try:
                raw = style.read_confined(root, cover[key], limit=16 * 1024 * 1024)
            except style.StyleError as exc:
                raise CoverFieldError('PATH', '%s: %s' % (key, exc)) from exc
            if key == 'scene':
                scene = style.parse_json(raw)
                sha = hashlib.sha256(_canonical_scene(scene)).hexdigest()
                if sha != cover['scene_sha256']:
                    raise CoverFieldError('COVER_MISMATCH', 'cover scene changed after adoption; adopt again')
            elif raw[:8] != b'\x89PNG\r\n\x1a\n':
                raise CoverFieldError('FORMAT', key + ' is not a PNG')
    return copy.deepcopy(cover)


def _canonical_scene(scene):
    import json
    return json.dumps(scene, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def validate_manifest(manifest, root=None):
    """project_model.validate_manifest + the optional cover block. Returns a deep copy (cover included)."""
    base, cover = split(manifest)
    out = project_model.validate_manifest(base)
    if cover is not None:
        out[FIELD] = validate_cover(cover, root)
    return out


def read(root):
    """The adopted cover of a portable project, or None (manifest validated through this module)."""
    manifest = style.parse_json(style.read_confined(root, 'project.json'))
    return validate_manifest(manifest, root).get(FIELD)


def with_cover(manifest, cover, root=None):
    """A new manifest carrying `cover` (validated); the input is not modified."""
    out = validate_manifest(manifest, root)
    out[FIELD] = validate_cover(cover, root)
    return out


def without_cover(manifest):
    return split(manifest)[0]


def manifest_bytes(manifest):
    """Canonical bytes (project_model's encoding: sorted keys, compact UTF-8)."""
    return style.canonical_bytes(manifest)


def cover_block(scene_rel, scene, exports, title_position):
    """Build a cover block from an export manifest (cover_tools export): exports = {name: project-relative path}."""
    block = {'schema_version': '1.0.0', 'scene': scene_rel,
             'scene_sha256': hashlib.sha256(_canonical_scene(scene)).hexdigest(),
             'box': exports['box-2x'], 'studio_art': exports['studio-art'], 'title_position': title_position}
    for key, name in (('box_1x', 'box-1x'), ('banner', 'banner'), ('square', 'square'), ('card_alpha', 'card-alpha')):
        if name in exports:
            block[key] = exports[name]
    return block
