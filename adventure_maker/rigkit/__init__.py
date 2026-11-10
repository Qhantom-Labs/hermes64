"""Rig kit (contract rig/1.0.0): skeleton contracts, numpy LBS reference, character validator, clip packs.

Public API (stable; docs/RIGKIT-API.md):
    list_rigs() -> [rig_id]
    load_rig(rig_id | path | Rig) -> Rig
    validate_character(glb, rig='human16_v1', *, clips=None, budget=None, expect_sha256=None, profile='grounded',
                       keys='all', tol_m=0.003) -> report dict
    validate_prop(glb, rig='human16_v1', *, slot=None, budget=None, expect_sha256=None) -> report dict
    attach_clips(glb, rig='human16_v1', *, clips=None, mode='copy', replace=True, ground='match', guard=True) -> bytes
    skin_vertices(glb, clip=None, key=0) -> numpy (N, 3)
"""
from .rig import Rig, RigError, list_rigs, load_rig, skin_order  # noqa: F401


def validate_character(glb, rig='human16_v1', **kw):
    from .validate import validate_character as _v
    return _v(glb, rig, **kw)


def validate_prop(glb, rig='human16_v1', **kw):
    from .validate import validate_prop as _v
    return _v(glb, rig, **kw)


def attach_clips(glb, rig='human16_v1', **kw):
    from .clips import attach_clips as _a
    return _a(glb, rig, **kw)


def skin_vertices(glb, clip=None, key=0):
    from .lbs import skin_vertices as _s
    return _s(glb, clip, key)


__all__ = ['Rig', 'RigError', 'list_rigs', 'load_rig', 'skin_order', 'validate_character', 'validate_prop',
           'attach_clips', 'skin_vertices']
