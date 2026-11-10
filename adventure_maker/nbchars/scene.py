"""Scene model handed from assembly (generator -> Scene) to the writer (Scene -> GLB bytes).

Coordinates are the generator's (Blender Z-up, metres); the writer converts to glTF Y-up exactly the way the Blender
exporter does. Every container is ordered (lists / insertion-ordered dicts) because order is part of the byte layout.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SceneMaterial:
    name: str
    image_name: str
    png: bytes
    n64: Dict[str, Any]                       # material extras {'n64': ...} (insertion order is kept)
    atlas_cell: Optional[Tuple[int, int, int]] = None   # (cell, cols, rows) -> KHR_texture_transform


@dataclass
class SceneMesh:
    name: str                                 # mesh datablock name, e.g. kit_body_mesh
    vertices: np.ndarray                      # (N, 3) float32, Z-up
    faces: np.ndarray                         # (M, 3) int
    face_material: np.ndarray                 # (M,) int, index into materials
    corner_uv: np.ndarray                     # (3M, 2) float32 (Blender UV space)
    corner_color: Optional[np.ndarray]        # (3M, 4) uint8 sRGB bytes (+ alpha byte)
    materials: List[SceneMaterial]
    groups: Optional[List[str]] = None        # vertex-group names (creation order) when skinned
    weights: Optional[List[List[Tuple[int, float]]]] = None   # per vertex [(group index, float32 weight)] in add order
    vertex_normals: Optional[np.ndarray] = None   # (N, 3) float32 Blender-equivalent smooth normals (Z-up)


@dataclass
class SceneSocket:
    """An object parented to a bone (empty or rigid mesh) with its glTF local transform relative to the bone node."""
    name: str
    bone: str
    translation: Optional[Tuple[float, float, float]] = None   # glTF, float32-exact values
    rotation: Optional[Tuple[float, float, float, float]] = None  # glTF xyzw
    mesh: Optional[SceneMesh] = None
    extras: Optional[Dict[str, Any]] = None


@dataclass
class SceneClip:
    name: str
    times: np.ndarray                         # (K,) float32 seconds
    rotations: Dict[str, np.ndarray]          # bone -> (K, 4) glTF xyzw (float64 before the float32 write)
    translations: Dict[str, np.ndarray]       # bone -> (K, 3) pose offset in glTF axes; the writer adds the rest translation
    channel_order: List[Tuple[str, str]]      # [(bone, 'rotation' | 'translation')]
    extras: Optional[Dict[str, Any]] = None


@dataclass
class SceneRig:
    object_name: str                          # rig_<skeleton>
    skeleton: str
    bones: Dict[str, Tuple[float, float, float]]   # creation order, heads Z-up
    parents: Dict[str, Optional[str]]
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Scene:
    kind: str                                 # human | animal | enemy | prop
    rig: Optional[SceneRig]
    body: Optional[SceneMesh]                 # skinned body (kit_body) or the prop mesh for kind == 'prop'
    body_object: str = 'kit_body'
    body_extras: Optional[Dict[str, Any]] = None
    sockets: List[SceneSocket] = field(default_factory=list)
    clips: List[SceneClip] = field(default_factory=list)
    info: Dict[str, Any] = field(default_factory=dict)   # assembly facts (params, hashes, generator handles)
