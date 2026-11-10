"""Float32 emulation of the Blender 5.2 maths the glTF bytes depend on (no Blender at runtime).

Each function names the Blender behaviour it reproduces and how it was verified against Blender itself
(tools/nbchars_oracle_dump.py ground truth, see docs/NBCHARS-RESULT.md):
  face_normals      bit-exact (cross(v1-v2, v2-v3), normalize by division, no FMA) on every probed face
  vertex_normals    corner-angle weighted face normals with Blender's approximate acos (Cycles fast_acosf);
                    the exporter rounds normals to 4 decimals, after which ~99 percent of vertices are identical
  SRGB_TO_LINEAR    the 256 BYTE_COLOR sRGB->linear float32 values Blender returns (measured table)
  bone_chain        edit-bone tail/length and the matrix_local translation chain of BKE_armature_where_is_bone
"""
import numpy as np

F32 = np.float32

# BYTE_COLOR attribute: color_srgb bytes -> .color (linear float32), measured from Blender 5.2.1 (all 256 values)
_SRGB_BITS = [
    0x00000000, 0x399f22b4, 0x3a1f22b4, 0x3a6eb40f, 0x3a9f22b4, 0x3ac6eb61, 0x3aeeb40f, 0x3b0b3e5e,
    0x3b1f22b4, 0x3b33070b, 0x3b46eb61, 0x3b5b518d, 0x3b70f18d, 0x3b83e1c6, 0x3b8fe616, 0x3b9c87fd,
    0x3ba9c9b5, 0x3bb7ad6f, 0x3bc63549, 0x3bd5635f, 0x3be539c1, 0x3bf5ba70, 0x3c0373b5, 0x3c0c6152,
    0x3c15a703, 0x3c1f45be, 0x3c293e6b, 0x3c3391f7, 0x3c3e4149, 0x3c494d43, 0x3c54b6c7, 0x3c607eb1,
    0x3c6ca5dc, 0x3c792d22, 0x3c830aa8, 0x3c89af9f, 0x3c9085db, 0x3c978dc5, 0x3c9ec7c0, 0x3ca63431,
    0x3cadd37d, 0x3cb5a601, 0x3cbdac20, 0x3cc5e639, 0x3cce54ab, 0x3cd6f7d3, 0x3cdfd00e, 0x3ce8ddb9,
    0x3cf22131, 0x3cfb9ac6, 0x3d02a56c, 0x3d0798df, 0x3d0ca7e7, 0x3d11d2b0, 0x3d171965, 0x3d1c7c31,
    0x3d21fb3c, 0x3d2796b2, 0x3d2d4ebe, 0x3d332384, 0x3d39152e, 0x3d3f23e6, 0x3d454fd4, 0x3d4b991f,
    0x3d51ffef, 0x3d58846a, 0x3d5f26b7, 0x3d65e6fe, 0x3d6cc564, 0x3d73c20f, 0x3d7add25, 0x3d810b66,
    0x3d84b795, 0x3d887330, 0x3d8c3e4a, 0x3d9018f6, 0x3d940345, 0x3d97fd4a, 0x3d9c0716, 0x3da020bb,
    0x3da44a4b, 0x3da883d7, 0x3daccd70, 0x3db12728, 0x3db59110, 0x3dba0b38, 0x3dbe95b5, 0x3dc33092,
    0x3dc7dbe2, 0x3dcc97b6, 0x3dd1641f, 0x3dd6412c, 0x3ddb2eef, 0x3de02d77, 0x3de53cd5, 0x3dea5d19,
    0x3def8e55, 0x3df4d093, 0x3dfa23e8, 0x3dff8861, 0x3e027f07, 0x3e054282, 0x3e080ea5, 0x3e0ae379,
    0x3e0dc107, 0x3e10a755, 0x3e13966c, 0x3e168e53, 0x3e198f11, 0x3e1c98ae, 0x3e1fab32, 0x3e22c6a3,
    0x3e25eb09, 0x3e29186c, 0x3e2c4ed2, 0x3e2f8e45, 0x3e32d6c8, 0x3e362865, 0x3e398322, 0x3e3ce706,
    0x3e405419, 0x3e43ca62, 0x3e4749e8, 0x3e4ad2b1, 0x3e4e64c6, 0x3e52002b, 0x3e55a4e9, 0x3e595307,
    0x3e5d0a8b, 0x3e60cb7c, 0x3e6495e0, 0x3e6869bf, 0x3e6c4720, 0x3e702e08, 0x3e741e7f, 0x3e78188c,
    0x3e7c1c38, 0x3e8014c2, 0x3e82203c, 0x3e84308d, 0x3e8645ba, 0x3e885fc5, 0x3e8a7eb2, 0x3e8ca283,
    0x3e8ecb3d, 0x3e90f8e1, 0x3e932b74, 0x3e9562f8, 0x3e979f71, 0x3e99e0e2, 0x3e9c274e, 0x3e9e72b7,
    0x3ea0c322, 0x3ea31892, 0x3ea57308, 0x3ea7d289, 0x3eaa3718, 0x3eaca0b7, 0x3eaf0f69, 0x3eb18333,
    0x3eb3fc16, 0x3eb67a15, 0x3eb8fd34, 0x3ebb8576, 0x3ebe12e1, 0x3ec0a571, 0x3ec33d2d, 0x3ec5da17,
    0x3ec87c33, 0x3ecb2383, 0x3ecdd00b, 0x3ed081cd, 0x3ed338cc, 0x3ed5f50b, 0x3ed8b68d, 0x3edb7d54,
    0x3ede4965, 0x3ee11ac1, 0x3ee3f16b, 0x3ee6cd67, 0x3ee9aeb7, 0x3eec955d, 0x3eef815d, 0x3ef272ba,
    0x3ef56976, 0x3ef86594, 0x3efb6717, 0x3efe6e02, 0x3f00bd2b, 0x3f02460c, 0x3f03d1a5, 0x3f055ff8,
    0x3f06f106, 0x3f0884cf, 0x3f0a1b57, 0x3f0bb49d, 0x3f0d50a2, 0x3f0eef69, 0x3f1090f2, 0x3f123540,
    0x3f13dc53, 0x3f15862d, 0x3f1732cf, 0x3f18e23b, 0x3f1a9471, 0x3f1c4973, 0x3f1e0143, 0x3f1fbbe1,
    0x3f217950, 0x3f23398f, 0x3f24fca2, 0x3f26c288, 0x3f288b43, 0x3f2a56d5, 0x3f2c253f, 0x3f2df681,
    0x3f2fca9e, 0x3f31a197, 0x3f337b6c, 0x3f355820, 0x3f3737b3, 0x3f391a26, 0x3f3aff7e, 0x3f3ce7b7,
    0x3f3ed2d4, 0x3f40c0d6, 0x3f42b1c0, 0x3f44a592, 0x3f469c4d, 0x3f4895f3, 0x3f4a9284, 0x3f4c9203,
    0x3f4e9470, 0x3f5099cd, 0x3f52a21a, 0x3f54ad59, 0x3f56bb8c, 0x3f58ccb3, 0x3f5ae0cf, 0x3f5cf7e2,
    0x3f5f11ee, 0x3f612ef2, 0x3f634eef, 0x3f6571ec, 0x3f6797e1, 0x3f69c0d8, 0x3f6beccb, 0x3f6e1bc2,
    0x3f704db6, 0x3f7282b1, 0x3f74baae, 0x3f76f5b3, 0x3f7933b9, 0x3f7b74cb, 0x3f7db8e0, 0x3f800000,
]
SRGB_TO_LINEAR = np.array(_SRGB_BITS, dtype=np.uint32).view(np.float32)


def _dot3(a, b):
    return ((a[..., 0] * b[..., 0]).astype(F32) + (a[..., 1] * b[..., 1]).astype(F32)
            + (a[..., 2] * b[..., 2]).astype(F32)).astype(F32)


def normalize(v):
    """math::normalize: v / sqrt(dot(v, v)), zero below 1e-35 (float32, division per component)."""
    v = np.asarray(v, dtype=F32)
    d = _dot3(v, v)
    ok = d > F32(1e-35)
    L = np.sqrt(np.where(ok, d, F32(1))).astype(F32)
    out = (v / L[..., None]).astype(F32)
    return np.where(ok[..., None], out, F32(0)).astype(F32)


def face_normals(V32, F):
    """normal_tri: normalize(cross(v1 - v2, v2 - v3)) in float32."""
    a, b, c = V32[F[:, 0]], V32[F[:, 1]], V32[F[:, 2]]
    p = (a - b).astype(F32)
    q = (b - c).astype(F32)
    cr = np.stack([(p[:, 1] * q[:, 2]).astype(F32) - (p[:, 2] * q[:, 1]).astype(F32),
                   (p[:, 2] * q[:, 0]).astype(F32) - (p[:, 0] * q[:, 2]).astype(F32),
                   (p[:, 0] * q[:, 1]).astype(F32) - (p[:, 1] * q[:, 0]).astype(F32)], 1).astype(F32)
    return normalize(cr)


def acos_approx(x):
    """math::safe_acos_approx (Cycles fast_acosf), float32."""
    x = np.asarray(x, dtype=F32)
    f = np.abs(x)
    m = np.where(f < 1, (F32(1) - (F32(1) - f)).astype(F32), F32(1)).astype(F32)
    p = (F32(0.077980478) + (m * F32(-0.02164095)).astype(F32)).astype(F32)
    p = (F32(-0.213300989) + (m * p).astype(F32)).astype(F32)
    p = (F32(1.5707963267) + (m * p).astype(F32)).astype(F32)
    a = (np.sqrt((F32(1) - m).astype(F32)).astype(F32) * p).astype(F32)
    return np.where(x < 0, (F32(np.pi) - a).astype(F32), a).astype(F32)


def vertex_normals(V32, F, fn=None):
    """Angle-weighted vertex normals (faces in ascending order per vertex), float32."""
    F = np.asarray(F)
    fn = face_normals(V32, F) if fn is None else fn
    vert = F.reshape(-1)
    prev = np.roll(F, 1, axis=1).reshape(-1)
    nxt = np.roll(F, -1, axis=1).reshape(-1)
    face = np.repeat(np.arange(len(F)), 3)
    dp = normalize((V32[prev] - V32[vert]).astype(F32))
    dn = normalize((V32[nxt] - V32[vert]).astype(F32))
    fac = acos_approx(_dot3(dp, dn))
    contrib = (fn[face] * fac[:, None]).astype(F32)
    acc = np.zeros((len(V32), 3), F32)
    for i in np.argsort(vert, kind='stable'):
        v = vert[i]
        acc[v] = (acc[v] + contrib[i]).astype(F32)
    return normalize(acc)


def export_normals(n32):
    """glTF exporter: round to 4 decimals (float32), normalise (float32), identity skin transform, zero -> +Z."""
    n = np.round(np.asarray(n32, dtype=F32), 4)
    norms = np.linalg.norm(n, axis=1, keepdims=True)
    np.divide(n, norms, out=n, where=norms != 0)
    with np.errstate(all='ignore'):            # Accelerate BLAS raises spurious FP flags on an identity matmul
        n = np.matmul(n, np.eye(3)).astype(F32)
    norms = np.linalg.norm(n, axis=1, keepdims=True)
    np.divide(n, norms, out=n, where=norms != 0)
    zero = ~n.any(axis=1)
    n[zero, 2] = 1
    return n


def color_u16(lin):
    """Exporter COLOR_0 (unsigned short normalized): clip, *65535, +0.5, truncate (float32)."""
    d = np.clip(np.asarray(lin, dtype=F32), 0, 1).astype(F32)
    d = (d * F32(65535)).astype(F32)
    d = (d + F32(0.5)).astype(F32)
    return d.astype(np.uint16)


def unit_float_to_uchar(f):
    """unit_float_to_uchar_clamp: the color_srgb setter of a BYTE_COLOR attribute (value stored as float32)."""
    f = float(F32(f))
    if f <= 0.0:
        return 0
    if f > 1.0 - 0.5 / 255.0:
        return 255
    return int(float(F32(F32(255.0) * F32(f))) + 0.5)


TAIL = F32(0.05)


def bone_chain(bones, parents, creation_order):
    """Edit bones: head = xyz, tail = head + (0, 0, .05) (mathutils float32), roll 0; Bone.length; matrix_local
    translation through BKE_armature_where_is_bone's parent composition (float32).
    -> {name: {'head', 'tail', 'length', 'arm_t'}} (Blender Z-up coordinates)."""
    out = {}
    for name in creation_order:
        h = np.array(bones[name], dtype=np.float64).astype(F32)
        t = (h + np.array([0, 0, TAIL], F32)).astype(F32)
        d = (t - h).astype(F32)
        out[name] = {'head': h, 'tail': t, 'length': F32(np.sqrt(_dot3(d, d)))}
    done = {}

    def arm(name):
        if name in done:
            return done[name]
        p = parents[name]
        h = out[name]['head']
        if p is None:
            r = h.copy()
        else:
            pt = arm(p)
            d = (h - out[p]['tail']).astype(F32)              # head - parent tail (parent space = rotX(90))
            ox, oy, oz = d[0], F32(d[2] + out[p]['length']), F32(-d[1])
            r = np.array([F32(pt[0] + ox), F32(pt[1] + F32(-oz)), F32(pt[2] + oy)], F32)
        done[name] = r
        return r
    for name in creation_order:
        out[name]['arm_t'] = arm(name)
    return out
