"""Vertex-colour light baking (N64-style baked gouraud) + UV assignment. Pure numpy.

Light model (pack light_rig): t = ambient + key*max(0, n.k) + sky*max(0, n.z) + ground*max(0, -n.z)
- ao * contact(z) ; t -> nearest step of the pack light ramp (palette names dark->bright).
Emissive/view/card roles are full-bright (brightest ramp colour)."""
import json
import math
from pathlib import Path

import numpy as np

FULLBRIGHT_KINDS = ("emissive", "view_plane", "card_alpha")
_VARIATION = None


def vertex_variation():
    """N64 look convention bake.vertex_variation ({} without kits/core/n64_look.json): painted low-frequency
    light/dark patches in the baked vertex colour of large terrain roles, the way N64 artists broke up big faces."""
    global _VARIATION
    if _VARIATION is None:
        p = Path(__file__).with_name("n64_look.json")
        _VARIATION = json.loads(p.read_text(encoding='utf-8')).get("bake", {}).get("vertex_variation", {}) if p.is_file() else {}
    return _VARIATION


def _hash3(i, j, k):
    n = (i * 73856093 ^ j * 19349663 ^ k * 83492791) & 0xFFFFFFFF
    n = ((n << 13) ^ n) & 0xFFFFFFFF
    n = (n * ((n * n * 15731 + 789221) & 0xFFFFFFFF) + 1376312589) & 0x7FFFFFFF
    return n / 2147483647.0


def value_noise(p, scale):
    """Deterministic smooth value noise in [0, 1] at a world position (metres), cell size `scale`."""
    x, y, z = p[0] / scale, p[1] / scale, p[2] / scale
    xi, yi, zi = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - xi, y - yi, z - zi
    sx, sy, sz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    acc = 0.0
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                w = (sx if dx else 1 - sx) * (sy if dy else 1 - sy) * (sz if dz else 1 - sz)
                acc += w * _hash3(xi + dx, yi + dy, zi + dz)
    return acc


def face_normals(V, faces):
    out = np.zeros((len(faces), 3))
    for i, f in enumerate(faces):
        n = np.zeros(3)
        for j in range(len(f)):  # Newell
            a = V[f[j]]
            b = V[f[(j + 1) % len(f)]]
            n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
        ln = np.linalg.norm(n)
        out[i] = n / ln if ln > 1e-12 else np.array([0, 0, 1.0])
    return out


def corner_normals(V, faces, smooth, fn, angle_deg=55.0):
    """Smooth faces average neighbouring smooth-face normals within angle; flat faces use fn."""
    cosl = math.cos(math.radians(angle_deg))
    key = {}
    vid = np.zeros(len(V), dtype=np.int64)
    for i, p in enumerate(V):
        k = (round(p[0] * 1e5), round(p[1] * 1e5), round(p[2] * 1e5))
        vid[i] = key.setdefault(k, len(key))
    inc = {}
    for fi, f in enumerate(faces):
        if smooth[fi]:
            for vi in f:
                inc.setdefault(vid[vi], []).append(fi)
    out = []
    for fi, f in enumerate(faces):
        if not smooth[fi]:
            out.append([fn[fi]] * len(f))
            continue
        cn = []
        for vi in f:
            acc = np.zeros(3)
            for g in inc.get(vid[vi], ()):
                if np.dot(fn[g], fn[fi]) >= cosl:
                    acc += fn[g]
            ln = np.linalg.norm(acc)
            cn.append(acc / ln if ln > 1e-12 else fn[fi])
        out.append(cn)
    return out


def asset_rig(rig, asset):
    """DUNGEONKIT (additive, opt-in by pack data): the pack light rig plus per-asset bake inputs.

    - `point_bake` > 0 in the pack rig: the generator's `meta["bake_lights"]` ([{pos, radius, strength}], asset space,
      +Z up) add warm point-light pools to the BAKED vertex light (N64 torch light painted into vertex colour), scaled
      by point_bake. The pack light ramp decides the hue (e.g. warm top steps).
    - `ao_occlusion` > 0: real per-vertex ambient occlusion from short hemisphere rays against the whole asset (all
      nodes), so corners, crevices and the feet of walls darken in the baked colour.
    Packs without these keys get the rig object back unchanged (identical output for every existing pack)."""
    pb = float(rig.get("point_bake", 0.0) or 0.0)
    occ = float(rig.get("ao_occlusion", 0.0) or 0.0)
    if pb <= 0.0 and occ <= 0.0:
        return rig
    out = dict(rig)
    if pb > 0.0:
        lights = []
        for L in (getattr(asset, "meta", {}) or {}).get("bake_lights", []) or []:
            lights.append((np.asarray(L["pos"], dtype=np.float64), float(L.get("radius", 3.0)),
                           float(L.get("strength", 1.0)) * pb))
        out["_lights"] = lights
    if occ > 0.0:
        tris = []
        for node in getattr(asset, "nodes", []):
            Vn = np.asarray(node.mesh.v, dtype=np.float64)
            for f in node.mesh.f:
                for i in range(1, len(f) - 1):
                    tris.append((Vn[f[0]], Vn[f[i]], Vn[f[i + 1]]))
        out["_occluders"] = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
    return out


_AO_DIRS = None


def _ao_dirs(k=14):
    """Fixed cosine-weighted hemisphere directions around +Z (deterministic golden-angle spiral)."""
    global _AO_DIRS
    if _AO_DIRS is None or len(_AO_DIRS) != k:
        out = []
        for i in range(k):
            r = math.sqrt((i + 0.5) / k)
            a = i * 2.399963229728653
            out.append((r * math.cos(a), r * math.sin(a), math.sqrt(max(0.0, 1.0 - r * r))))
        _AO_DIRS = np.asarray(out)
    return _AO_DIRS


def _occlusion(p, n, tris, reach):
    """Fraction of hemisphere rays from p (offset along n) that hit an occluder triangle within `reach` metres."""
    if tris is None or not len(tris):
        return 0.0
    n = n / max(np.linalg.norm(n), 1e-12)
    a = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(n, a)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    D = _ao_dirs()
    dirs = D[:, 0:1] * t1 + D[:, 1:2] * t2 + D[:, 2:3] * n
    o = p + n * 0.02
    lo = np.minimum(np.minimum(tris[:, 0], tris[:, 1]), tris[:, 2])
    hi = np.maximum(np.maximum(tris[:, 0], tris[:, 1]), tris[:, 2])
    near = np.all((lo <= o + reach) & (hi >= o - reach), axis=1)
    T = tris[near]
    if not len(T):
        return 0.0
    v0, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    hits = 0
    for d in dirs:
        pv = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, pv)
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o - v0
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, e1)
        v = (qv @ d) * inv
        t = np.einsum("ij,ij->i", e2, qv) * inv
        if np.any(ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4) & (t < reach)):
            hits += 1
    return hits / float(len(dirs))


def bake_corner_light(mesh, rig, n_steps, role_kind, origin_z=0.0):
    """Returns per-face list of ramp indices per corner."""
    V = np.asarray(mesh.v, dtype=np.float64)
    fn = face_normals(V, mesh.f)
    cn = corner_normals(V, mesh.f, mesh.s, fn)
    k = np.asarray(rig["key_dir"], dtype=np.float64)
    k = k / np.linalg.norm(k)
    amb, key, sky, gnd = rig["ambient"], rig["key"], rig["sky"], rig["ground"]
    ao = rig.get("ao", 0.0)
    ao_h = rig.get("ao_height", 0.35)
    gamma = rig.get("gamma", 1.0)
    var = vertex_variation()
    var_amt = float(var.get("amount", 0.0))
    var_roles = set(var.get("roles", []))
    var_scale = float(var.get("scale_m", 3.0))
    lights = rig.get("_lights") or []
    occluders = rig.get("_occluders")
    occ_amt = float(rig.get("ao_occlusion", 0.0) or 0.0)
    occ_reach = float(rig.get("ao_reach", 1.2))
    occ_cache = {}
    # DUNGEONKIT (opt-in, pack data): `fullbright_back` steps full-bright roles (sky, flames, runes) back from the ramp
    # top, so a warm torch-pool top step (lit-torch variant) does not tint every emissive and sky surface
    fb_step = max(0, n_steps - 1 - int(rig.get("fullbright_back", 0) or 0))
    out = []
    for fi, f in enumerate(mesh.f):
        kind = role_kind(mesh.r[fi])
        if kind in FULLBRIGHT_KINDS:
            out.append([fb_step] * len(f))
            continue
        varied = var_amt > 0 and mesh.r[fi] in var_roles
        row = []
        for ci, vi in enumerate(f):
            n = cn[fi][ci]
            z = V[vi][2] - origin_z
            t = amb + key * max(0.0, float(np.dot(n, k))) + sky * max(0.0, n[2]) + gnd * max(0.0, -n[2])
            if ao > 0:
                c = max(0.0, min(1.0, z / ao_h))
                t -= ao * (1.0 - c) * (1.0 - c)
            if varied:
                t += var_amt * (2.0 * value_noise(V[vi], var_scale) - 1.0)
            for lp, lr, ls in lights:
                d = lp - V[vi]
                dd = float(np.dot(d, d))
                fall = max(0.0, 1.0 - dd / (lr * lr))
                if fall > 0.0:
                    wrap = max(0.0, float(np.dot(n, d)) / max(math.sqrt(dd), 1e-9) * 0.65 + 0.35)
                    t += ls * fall * fall * wrap
            if occ_amt > 0 and occluders is not None:
                key_ = (round(V[vi][0], 3), round(V[vi][1], 3), round(V[vi][2], 3), round(n[0], 2), round(n[1], 2), round(n[2], 2))
                if key_ not in occ_cache:
                    occ_cache[key_] = _occlusion(V[vi], np.asarray(n, dtype=np.float64), occluders, occ_reach)
                t -= occ_amt * occ_cache[key_]
            t = max(0.0, min(1.0, t)) ** gamma
            row.append(int(round(t * (n_steps - 1))))
        out.append(row)
    return out


def box_uv(p, n):
    ax = int(np.argmax(np.abs(n)))
    if ax == 2:
        return (p[0], p[1] if n[2] >= 0 else -p[1])
    if ax == 0:
        return ((p[1] if n[0] >= 0 else -p[1]), p[2])
    return ((-p[0] if n[1] >= 0 else p[0]), p[2])


def corner_uvs(mesh, tile_of_role):
    """Per-face corner UVs (Blender convention, v up). Metric/auto UVs are divided by the role's
    tile size in metres (pack data); normalized ('n') UVs are kept."""
    V = np.asarray(mesh.v, dtype=np.float64)
    fn = face_normals(V, mesh.f)
    out = []
    for fi, f in enumerate(mesh.f):
        u = mesh.uv[fi]
        if u is not None and u[0] == "n":
            out.append([tuple(c) for c in u[1]])
            continue
        t = tile_of_role(mesh.r[fi])
        if u is not None and u[0] == "m":
            out.append([(a / t, b / t) for a, b in u[1]])
            continue
        out.append([tuple(c / t for c in box_uv(V[vi], fn[fi])) for vi in f])
    return out
