"""Per-asset validators on exported GLB files. Each returns {"check", "ok", "measured", "reason"}.

budget, palette, naming, origin_scale, topology (manifold/winding/degenerate/self-intersection),
rig (skeleton compatibility + reference-skinning deformation). Visible difference is a sweep-level
check (tools/visdiff.py) because it compares renders of many samples.
"""
import math
import re

import numpy as np

from core import png
from core.palette import linear_to_srgb
from .glb import GLB, weld

try:
    from mathutils.bvhtree import BVHTree
except Exception:  # pragma: no cover
    BVHTree = None

NAME_RE = re.compile(r"^[a-z0-9_]+$")
NODE_RE = re.compile(r"^(kit_(shell_|card_)?[a-z0-9_]+|rig_[a-z0-9_]+|attach_[a-z0-9_]+)$")
EXTENTS = {  # class -> (min largest extent, max largest extent) in metres
    "prop": (0.03, 1.6), "soft": (0.1, 3.2), "furniture": (0.15, 4.5), "furniture_large": (0.3, 6.0),
    "arch": (0.1, 16.0), "structure": (0.5, 40.0), "shell": (1.5, 40.0), "building": (2.0, 30.0),
    "terrain": (1.0, 200.0), "flora": (0.05, 30.0), "vehicle": (0.5, 20.0), "sky": (1.0, 4000.0),
    "fx": (0.01, 5.0), "character": (0.8, 2.6), "animal": (0.15, 2.6),
}
TEX_LIMIT = {"default": 64, "view_plane": 128, "face_atlas": 128, "character": 128, "sky": 128}


def _r(check, ok, measured, reason=""):
    return {"check": check, "ok": bool(ok), "measured": measured, "reason": "" if ok else reason}


def _image_kinds(g):
    """image index -> material kind using it."""
    out = {}
    tex = g.json.get("textures", [])
    for m in g.materials:
        kind = (m.get("extras", {}).get("n64", {}) or {}).get("kind", "?")
        bct = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if bct is not None:
            out[tex[bct["index"]]["source"]] = kind
    return out


def check_budget(g, cls, tri_limit):
    tris = g.tri_count()
    kinds = _image_kinds(g)
    sizes = {}
    bad = []
    for i, im in enumerate(g.images):
        data = g.image_bytes(i)
        w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        k = kinds.get(i, "default")
        lim = TEX_LIMIT.get(k, TEX_LIMIT["default"])
        if cls in ("character", "sky"):
            lim = 128
        sizes[im.get("name", str(i))] = [w, h]
        if w > lim or h > lim:
            bad.append("%s %dx%d > %d" % (im.get("name"), w, h, lim))
    ok = tris <= tri_limit and not bad
    reason = []
    if tris > tri_limit:
        reason.append("%d tris > limit %d" % (tris, tri_limit))
    reason += bad
    return _r("budget", ok, {"tris": tris, "tri_limit": tri_limit, "textures": sizes}, "; ".join(reason))


def check_palette(g, pal, light_ramp_idx, tol=2):
    off_tex = 0
    total_tex = 0
    alpha_bad = 0
    details = []
    for i, im in enumerate(g.images):
        arr = png.decode(g.image_bytes(i))
        rgb = arr[:, :, :3].reshape(-1, 3)
        total_tex += len(rgb)
        inside = pal.contains_rgb8(rgb, tol=0)
        n_off = int((~inside).sum())
        if n_off:
            details.append("%s: %d off-palette texels" % (im.get("name"), n_off))
        off_tex += n_off
        if arr.shape[2] == 4:
            a = arr[:, :, 3].reshape(-1)
            alpha_bad += int(((a != 0) & (a != 255)).sum())
    ramp = pal.rgb8[light_ramp_idx]
    off_vc = 0
    total_vc = 0
    for ni in g.mesh_nodes():
        geo = g.node_geometry(ni, world=False)
        explicit_srgb = g.json.get("asset", {}).get("extras", {}).get("vertex_color_encoding") == "srgb8"
        c = np.round((geo["col"] if explicit_srgb else linear_to_srgb(geo["col"])) * 255).astype(np.int64)
        total_vc += len(c)
        d = np.abs(c[:, None, :] - ramp[None, :, :]).max(-1).min(1)
        n_off = int((d > tol).sum())
        if n_off:
            details.append("%s: %d vertex colours off the light ramp" % (g.nodes[ni].get("name"), n_off))
        off_vc += n_off
    off_fac = 0
    for m in g.materials:
        f = m.get("pbrMetallicRoughness", {}).get("baseColorFactor")
        if f is None or all(abs(x - 1.0) < 1e-6 for x in f[:3]):
            continue
        c = np.round(linear_to_srgb(np.array(f[:3])) * 255).astype(np.int64)
        if not pal.contains_rgb8(c[None, :], tol=tol)[0]:
            off_fac += 1
            details.append("%s: baseColorFactor %s not a palette colour" % (m.get("name"), c.tolist()))
    ok = off_tex == 0 and off_vc == 0 and off_fac == 0 and alpha_bad == 0
    if alpha_bad:
        details.append("%d texels with partial alpha" % alpha_bad)
    return _r("palette", ok, {"texels": total_tex, "off_texels": off_tex, "vertex_colors": total_vc,
                              "off_vertex_colors": off_vc, "off_factors": off_fac, "partial_alpha": alpha_bad},
              "; ".join(details[:6]))


def check_naming(g, allowed_bones=()):
    bad = []
    bones = set(allowed_bones)
    joint_nodes = set()
    for s in g.skins:
        joint_nodes.update(s["joints"])
    for i, n in enumerate(g.nodes):
        name = n.get("name", "")
        if i in joint_nodes:
            if name not in bones:
                bad.append("joint %r not in skeleton" % name)
            continue
        if not NODE_RE.match(name):
            bad.append("node %r" % name)
        s = n.get("scale")
        if s is not None and any(abs(x - 1.0) > 1e-6 for x in s):
            bad.append("node %r has scale %s" % (name, s))
        if "matrix" in n:
            bad.append("node %r uses a matrix" % name)
    for m in g.materials:
        if not (m.get("name", "").startswith("mat_") and NAME_RE.match(m.get("name", ""))):
            bad.append("material %r" % m.get("name"))
    for im in g.images:
        if not (im.get("name", "").startswith("tex_") and NAME_RE.match(im.get("name", ""))):
            bad.append("image %r" % im.get("name"))
    for me in g.meshes:
        if not NAME_RE.match(me.get("name", "")):
            bad.append("mesh %r" % me.get("name"))
    return _r("naming", not bad, {"nodes": len(g.nodes), "bad": len(bad)}, "; ".join(bad[:6]))


def bounds(g):
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for i in g.mesh_nodes():
        p = g.node_geometry(i, world=True)["pos"]
        lo = np.minimum(lo, p.min(0))
        hi = np.maximum(hi, p.max(0))
    return lo, hi


def check_origin_scale(g, cls, origin_rule):
    lo, hi = bounds(g)
    ext = hi - lo
    largest = float(ext.max())
    emin, emax = EXTENTS[cls]
    problems = []
    if not (emin <= largest <= emax):
        problems.append("largest extent %.3f m outside [%g, %g] for class %s" % (largest, emin, emax, cls))
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    tolx = 0.02 + 0.03 * ext[0]
    tolz = 0.02 + 0.03 * ext[2]
    if origin_rule in ("floor_center", "room_floor", "opening_floor"):
        if abs(cx) > tolx:
            problems.append("footprint centre x %.3f not at origin (tol %.3f)" % (cx, tolx))
        if origin_rule != "opening_floor" and abs(cz) > tolz:
            problems.append("footprint centre z %.3f not at origin (tol %.3f)" % (cz, tolz))
    if origin_rule in ("floor_center", "opening_floor"):
        if abs(lo[1]) > 0.01:
            problems.append("min Y %.3f m (must be 0 +- 0.01)" % lo[1])
    if origin_rule == "room_floor" and not (-0.35 <= lo[1] <= 0.01):
        problems.append("room min Y %.3f outside [-0.35, 0.01]" % lo[1])
    if origin_rule == "terrain_center":
        if abs(cx) > tolx or abs(cz) > tolz:
            problems.append("terrain not centred (%.3f, %.3f)" % (cx, cz))
    return _r("origin_scale", not problems, {"bbox_min": [round(float(x), 4) for x in lo],
                                             "bbox_max": [round(float(x), 4) for x in hi],
                                             "largest_extent": round(largest, 4)}, "; ".join(problems))


def _tri_areas(P, T):
    return 0.5 * np.linalg.norm(np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]), axis=1)


def islands_of(T, nverts):
    parent = np.arange(nverts)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in T:
        a, b, c = find(t[0]), find(t[1]), find(t[2])
        parent[b] = a
        parent[find(c)] = a
    roots = np.array([find(i) for i in range(nverts)])
    return roots


def topology_of_node(geo, kind):
    """kind: solid | shell | card. Returns dict of measured problems."""
    P = geo["pos"]
    wid = weld(P)
    nw = int(wid.max()) + 1 if len(wid) else 0
    WP = np.zeros((nw, 3))
    WP[wid] = P
    T = wid[geo["idx"]]
    areas = _tri_areas(WP, T)
    degenerate = int((areas < 1e-9).sum()) + int(((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2]) | (T[:, 0] == T[:, 2])).sum())
    good = ~((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2]) | (T[:, 0] == T[:, 2]))
    T = T[good]
    und = {}
    dirc = {}
    for t in T:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            e = (a, b) if a < b else (b, a)
            und[e] = und.get(e, 0) + 1
            dirc[(a, b)] = dirc.get((a, b), 0) + 1
    boundary = sum(1 for c in und.values() if c == 1)
    nonman = sum(1 for c in und.values() if c > 2)
    incons = sum(1 for c in dirc.values() if c > 1)
    roots = islands_of(T, nw) if len(T) else np.zeros(0, dtype=int)
    tri_island = roots[T[:, 0]] if len(T) else np.zeros(0, dtype=int)
    n_islands = len(set(tri_island.tolist()))
    selfx = None
    if BVHTree is not None and len(T):
        tree = BVHTree.FromPolygons([tuple(p) for p in WP], [tuple(int(x) for x in t) for t in T], all_triangles=True)
        pairs = tree.overlap(tree)
        # Blender's self-overlap does not reliably skip triangles that only share a vertex (fan
        # poles); pairs sharing any welded vertex are treated as adjacent (documented limitation).
        selfx = 0
        for a, b in pairs:
            if a < b and tri_island[a] == tri_island[b]:
                ta, tb = T[a], T[b]
                if ta[0] in tb or ta[1] in tb or ta[2] in tb:
                    continue
                selfx += 1
    if selfx is None:
        from .intersections import count_intersections
        selfx = count_intersections(WP, T, tri_island) if len(T) else 0
    planar = None
    if kind == "card":
        worst = 0.0
        for isl in set(tri_island.tolist()):
            vs = np.unique(T[tri_island == isl].reshape(-1))
            pts = WP[vs]
            c = pts.mean(0)
            _, s, vt = np.linalg.svd(pts - c)
            worst = max(worst, float(np.abs((pts - c) @ vt[2]).max()))
        planar = worst
    return {"triangles": int(len(geo["idx"])), "islands": n_islands, "boundary_edges": boundary,
            "nonmanifold_edges": nonman, "inconsistent_edges": incons, "degenerate": degenerate,
            "self_intersections": selfx, "card_planarity_m": planar}


def check_topology(g):
    problems = []
    per = {}
    for i in g.mesh_nodes():
        name = g.nodes[i].get("name", "")
        kind = "card" if name.startswith("kit_card_") else ("shell" if name.startswith("kit_shell_") else "solid")
        m = topology_of_node(g.node_geometry(i, world=True), kind)
        per[name] = m
        if m["degenerate"]:
            problems.append("%s: %d degenerate tris" % (name, m["degenerate"]))
        if m["nonmanifold_edges"]:
            problems.append("%s: %d non-manifold edges" % (name, m["nonmanifold_edges"]))
        if m["inconsistent_edges"]:
            problems.append("%s: %d inconsistently wound edges" % (name, m["inconsistent_edges"]))
        if kind == "solid" and m["boundary_edges"]:
            problems.append("%s: %d boundary edges (holes) in a closed solid" % (name, m["boundary_edges"]))
        if kind != "card" and m["self_intersections"]:
            problems.append("%s: %d self-intersecting tri pairs" % (name, m["self_intersections"]))
        if kind == "card" and m["card_planarity_m"] is not None and m["card_planarity_m"] > 0.001:
            problems.append("%s: card not planar (%.4f m)" % (name, m["card_planarity_m"]))
        if m["self_intersections"] is None:
            problems.append("%s: self-intersection test unavailable (no mathutils)" % name)
    return _r("topology", not problems, per, "; ".join(problems[:6]))


# ------------------------------------------------------------------ rig + deformation
def _quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _trs(t, r, s):
    M = np.eye(4)
    M[:3, :3] = _quat_to_mat(r) * np.array(s)[None, :]
    M[:3, 3] = t
    return M


def skeleton_info(g):
    if len(g.skins) != 1:
        return None
    s = g.skins[0]
    joints = s["joints"]
    names = [g.nodes[j].get("name") for j in joints]
    parent = {}
    for j in joints:
        p = g._parent.get(j)
        parent[g.nodes[j]["name"]] = g.nodes[p]["name"] if (p is not None and p in joints) else None
    rots = {}
    for j in joints:
        M = g.world_matrix(j)
        R = M[:3, :3]
        sc = np.linalg.norm(R, axis=0)
        rots[g.nodes[j]["name"]] = (R / sc[None, :]).round(4).tolist()
    return {"names": names, "parent": parent, "world_rot": rots}


def _sample(times, values, t, path):
    """STEP sampling at time t."""
    k = int(np.searchsorted(times, t + 1e-6) - 1)
    k = max(0, min(k, len(times) - 1))
    return values[k]


def posed_positions(g, node_index, anim, t):
    """Reference glTF skinning (engine independent) of a skinned node at time t of animation."""
    s = g.skins[0]
    joints = s["joints"]
    ibm = g.accessor(s["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    local = {}
    for i, n in enumerate(g.nodes):
        local[i] = [list(n.get("translation", [0, 0, 0])), list(n.get("rotation", [0, 0, 0, 1])), list(n.get("scale", [1, 1, 1]))]
    if anim is not None:
        for ch in anim["channels"]:
            smp = anim["samplers"][ch["sampler"]]
            times = g.accessor(smp["input"]).reshape(-1)
            vals = g.accessor(smp["output"])
            v = _sample(times, vals, t, ch["target"]["path"])
            slot = {"translation": 0, "rotation": 1, "scale": 2}.get(ch["target"]["path"])
            if slot is not None:
                local[ch["target"]["node"]][slot] = list(v)
    world = {}

    def wm(i):
        if i in world:
            return world[i]
        M = _trs(*local[i])
        p = g._parent.get(i)
        if p is not None:
            M = wm(p) @ M
        world[i] = M
        return M
    mats = np.array([wm(j) @ ibm[k] for k, j in enumerate(joints)])
    geo = g.node_geometry(node_index, world=False)
    P = np.concatenate([geo["pos"], np.ones((len(geo["pos"]), 1))], 1)
    out = np.zeros((len(P), 3))
    for k in range(4):
        M = mats[geo["joints"][:, k]]
        out += geo["weights"][:, k:k + 1] * np.einsum("nij,nj->ni", M, P)[:, :3]
    return out, geo


def check_rig(g, ref, clips, attachments, root="root", stretch=(0.45, 1.8), contact_tol=0.03):
    """ref: {'names': [...], 'parent': {...}, 'world_rot': {...}} expected skeleton."""
    problems = []
    info = skeleton_info(g)
    if info is None:
        return _r("rig", False, {}, "expected exactly one skin")
    if sorted(info["names"]) != sorted(ref["names"]):
        problems.append("joint names differ: %s" % sorted(set(info["names"]) ^ set(ref["names"])))
    for n, p in ref["parent"].items():
        if info["parent"].get(n, "<missing>") != p:
            problems.append("joint %s parent %r != %r" % (n, info["parent"].get(n), p))
    worst_rot = 0.0
    for n, R in ref["world_rot"].items():
        if n in info["world_rot"]:
            worst_rot = max(worst_rot, float(np.abs(np.array(info["world_rot"][n]) - np.array(R)).max()))
    if worst_rot > 2e-3:
        problems.append("rest orientations differ (max %.4f)" % worst_rot)
    names = {n.get("name"): i for i, n in enumerate(g.nodes)}
    for a, parent_joint in attachments.items():
        if a not in names:
            problems.append("missing attachment %s" % a)
            continue
        p = g._parent.get(names[a])
        if p is None or g.nodes[p].get("name") != parent_joint:
            problems.append("attachment %s not under %s" % (a, parent_joint))
    anims = {a.get("name"): a for a in g.animations}
    if sorted(anims) != sorted(clips):
        problems.append("clips %s != %s" % (sorted(anims), sorted(clips)))
    joint_idx = set(g.skins[0]["joints"])
    for a in g.animations:
        for ch in a["channels"]:
            nn = g.nodes[ch["target"]["node"]].get("name")
            path = ch["target"]["path"]
            if ch["target"]["node"] not in joint_idx:
                problems.append("%s animates non-joint %s" % (a["name"], nn))
            elif nn != root and path != "rotation":
                problems.append("%s: %s.%s (non-root bones may only rotate)" % (a["name"], nn, path))
        for smp in a["samplers"]:
            if smp.get("interpolation") != "STEP":
                problems.append("%s: interpolation %s != STEP" % (a["name"], smp.get("interpolation")))
                break
            times = g.accessor(smp["input"]).reshape(-1)
            if np.abs(times * 12 - np.round(times * 12)).max() > 1e-3:
                problems.append("%s: keys not on 12 fps frames" % a["name"])
                break
    # weights
    skinned = [i for i in g.mesh_nodes() if "skin" in g.nodes[i]]
    wsum_bad = 0
    deform = {}
    for ni in skinned:
        geo = g.node_geometry(ni, world=False)
        ws = geo["weights"].sum(1)
        wsum_bad += int((np.abs(ws - 1) > 2e-3).sum())
        rest, _ = posed_positions(g, ni, None, 0.0)
        T = geo["idx"]
        wid = weld(geo["pos"])
        edges = set()
        for t in wid[T]:
            for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if a2 != b2:
                    edges.add((min(a2, b2), max(a2, b2)))
        first = {}
        for vi, w in enumerate(wid):
            first.setdefault(int(w), vi)
        E = np.array([(first[a2], first[b2]) for a2, b2 in sorted(edges)])
        rest_len = np.linalg.norm(rest[E[:, 0]] - rest[E[:, 1]], axis=1)
        roots = islands_of(wid[T], int(wid.max()) + 1)
        isl_of_v = roots[wid]
        isl_ids = sorted(set(isl_of_v.tolist()))
        groups = {k: np.where(isl_of_v == k)[0] for k in isl_ids}

        def min_dist(P, a2, b2):
            A, B = P[groups[a2]], P[groups[b2]]
            d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))
            return float(d.min())
        touching = []
        for ia in range(len(isl_ids)):
            for ib in range(ia + 1, len(isl_ids)):
                if min_dist(rest, isl_ids[ia], isl_ids[ib]) <= 0.012:
                    touching.append((isl_ids[ia], isl_ids[ib]))
        worst = {"max_stretch": 1.0, "min_stretch": 1.0, "max_gap": 0.0}
        for a in g.animations:
            times = sorted(set(np.round(np.concatenate([g.accessor(s2["input"]).reshape(-1) for s2 in a["samplers"]]), 5).tolist()))
            for t in times:
                P, _ = posed_positions(g, ni, a, t)
                if not np.isfinite(P).all():
                    problems.append("%s t=%.3f: non-finite skinned positions" % (a["name"], t))
                    break
                ln = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
                ratio = ln / np.maximum(rest_len, 1e-6)
                worst["max_stretch"] = max(worst["max_stretch"], float(ratio.max()))
                worst["min_stretch"] = min(worst["min_stretch"], float(ratio.min()))
                for ia2, ib2 in touching:
                    gap = min_dist(P, ia2, ib2)
                    if gap > worst["max_gap"]:
                        worst["max_gap"] = gap
                        worst["gap_where"] = "%s t=%.2f" % (a["name"], t)
        deform[g.nodes[ni].get("name")] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in worst.items()}
        deform[g.nodes[ni].get("name")]["touching_island_pairs"] = len(touching)
        if worst["max_stretch"] > stretch[1] or worst["min_stretch"] < stretch[0]:
            problems.append("%s: edge stretch %.2f..%.2f outside %s" % (g.nodes[ni].get("name"), worst["min_stretch"], worst["max_stretch"], stretch))
        if worst["max_gap"] > contact_tol:
            problems.append("%s: joined parts separate by %.3f m (%s)" % (g.nodes[ni].get("name"), worst["max_gap"], worst.get("gap_where")))
    if wsum_bad:
        problems.append("%d vertices with weights not summing to 1" % wsum_bad)
    return _r("rig", not problems, {"joints": len(info["names"]), "max_rot_dev": round(worst_rot, 5),
                                    "clips": sorted(anims), "deformation": deform}, "; ".join(problems[:6]))
