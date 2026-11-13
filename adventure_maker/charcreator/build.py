"""Creator recipe -> skinned, animated GLB (numpy): mesh.py + paint.py -> nbchars Scene -> writer -> rig-pack clips.

The body is one skinned mesh (kit_body) on rig human16_v1 with every clip of the rig's clip pack written in by
rigkit.clips.attach_clips (joint rotations copied, grounding per key, deformation guard), so walk / run / idle /
swing / hurt / death / roll / block play like every other human16 body. Props (hat, cape, ears ...) are rigid socket
meshes on their bone. One material, one 64x64 atlas, KHR unlit, n64 kind baked_unlit (the card's material).
"""
import hashlib

import numpy as np

from . import mesh as ME
from . import paint as PT

F32 = np.float32
GENERATOR = 'hermes64 character creator (python)'


def _zup(a):
    """glTF (Y up, faces +Z) -> the Scene's Blender axes (Z up, faces -Y)."""
    a = np.asarray(a, float)
    return np.stack([a[..., 0], -a[..., 2], a[..., 1]], axis=-1)


def _faces_for_paint(M, V, N, part_rows, height):
    out = []
    for fi, (a, b, c) in enumerate(M.F):
        out.append((M.part[fi], M.side[fi], M.UV[fi], (V[a], V[b], V[c]), (N[a], N[b], N[c]), height))
    return out


def _scene_mesh(name, M, V, N, uv_atlas, material, groups=None):
    from ..nbchars.scene import SceneMesh
    F = np.array(M.F, dtype=np.int64)
    corner_uv = np.zeros((3 * len(F), 2), F32)
    for fi, uvs in enumerate(uv_atlas):
        for k in range(3):
            u, v = uvs[k]
            corner_uv[3 * fi + k] = (u, 1. - v)           # Blender UV space (the writer flips v back)
    weights = None
    if groups is not None:
        gi = {g: i for i, g in enumerate(groups)}
        weights = []
        for w in M.W:
            tot = sum(w.values())
            weights.append([(gi[b], float(F32(x / tot))) for b, x in sorted(w.items(), key=lambda kv: gi[kv[0]])])
    return SceneMesh(name=name, vertices=_zup(V).astype(F32), faces=F, face_material=np.zeros(len(F), np.int64),
                     corner_uv=corner_uv, corner_color=np.full((3 * len(F), 4), 255, np.uint8), materials=[material],
                     groups=groups, weights=weights, vertex_normals=_zup(N).astype(F32))


def assemble(params, data):
    """-> (Scene, meta) for a compiled creator recipe."""
    from ..nbchars.scene import Scene, SceneMaterial, SceneRig, SceneSocket
    H = float(params['body']['height_m'])
    M, props, J, rings = ME.build(params, data)
    V = np.array(M.V) * H
    N = ME.vertex_normals(V, M.F)
    faces = _faces_for_paint(M, V, N, None, H)
    prop_geo = []
    for P in props:
        PV = np.array(P.M.V) * H
        PN = ME.vertex_normals(PV, P.M.F)
        prop_geo.append((P, PV, PN))
        faces += _faces_for_paint(P.M, PV, PN, None, H)
    img, paint_meta = PT.paint(params, data, faces)
    png = PT.png_bytes(img)
    img_name = 'tex_creator_%s_atlas' % params['id']
    mat = SceneMaterial(name='mat_creator_%s_atlas' % params['id'], image_name=img_name, png=png,
                        n64={'kind': 'baked_unlit', 'role': 'costume', 'pack': 'creator64', 'texture': img_name,
                             'vertex_color_encoding': 'linear_gltf'})
    groups = list(ME.BONES)
    body_uv = [tuple(PT.atlas_uv(M.part[fi], uv) for uv in M.UV[fi]) for fi in range(len(M.F))]
    body = _scene_mesh('kit_body_mesh', M, V, N, body_uv, mat, groups)
    Jm = {b: J[b] * H for b in ME.BONES}
    rig = SceneRig(object_name='rig_human16_v1', skeleton='human16_v1',
                   bones={b: tuple(float(x) for x in _zup(Jm[b])) for b in ME.BONES}, parents=dict(ME.PARENT),
                   extras={'topology': 'creator64_v1', 'creator': {'species': params['species'], 'build': params['build'],
                                                                   'modules': params['modules'], 'seed': params['seed']}})
    sockets = []
    for P, PV, PN in prop_geo:
        local = PV - Jm[P.bone]
        uv = [tuple(PT.atlas_uv(P.M.part[fi], u) for u in P.M.UV[fi]) for fi in range(len(P.M.F))]
        pm = _scene_mesh(P.name + '_mesh', P.M, local, PN, uv, mat, None)
        sockets.append(SceneSocket(name=P.name, bone=P.bone, mesh=pm))
    sc = Scene(kind='human', rig=rig, body=body, sockets=sockets, clips=[])
    meta = {'height_m': round(float(V[:, 1].max()), 4), 'skull_m': round(H, 4), 'tris_body': len(M.F),
            'tris_props': {P.name: len(P.M.F) for P, _, _ in prop_geo}, 'joints': {b: [round(float(x), 5) for x in Jm[b]] for b in ME.BONES},
            'paint': paint_meta, 'atlas_png_sha256': hashlib.sha256(png).hexdigest(), 'pieces': sorted(set(M.piece))}
    return sc, meta, img


def glb(params, data, clips=True):
    """-> (GLB bytes, meta, atlas image)."""
    from ..nbchars.writer import write_scene
    sc, meta, img = assemble(params, data)
    raw = write_scene(sc, generator=GENERATOR)
    if clips:
        from ..rigkit.clips import attach_clips
        raw = attach_clips(raw, rig='human16_v1', clips=None, mode='copy', replace=True, ground='match', guard=True)
    meta['sha256'] = hashlib.sha256(raw).hexdigest()
    meta['bytes'] = len(raw)
    return raw, meta, img


def rig_segments(meta, rig_json):
    """Joint offsets as fractions of height against the rig contract's segment ranges -> list of problems."""
    J = {k: np.array(v) for k, v in meta['joints'].items()}
    h = meta['height_m']
    out = []
    rng = rig_json['proportions']['segment_fraction_of_height']
    for b in ME.BONES:
        par = ME.PARENT[b]
        if par is None or b not in rng:
            continue
        f = float(np.linalg.norm(J[b] - J[par])) / h
        lo, hi = rng[b]
        if not lo <= f <= hi:
            out.append('%s %.4f outside [%s, %s]' % (b, f, lo, hi))
    return out
