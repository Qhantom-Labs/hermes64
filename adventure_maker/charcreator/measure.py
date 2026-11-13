"""Card measurements (numpy + Pillow): proportions, triangle split, texture statistics and silhouettes of a skinned
human16 GLB, and how a model sits against the style card (lane CHARCREATOR).

The same functions measured the two reference models into docs/charstyle/meshy_n64_card.json (repository tool
tools/charcreator_measure.py) and measure every creator output, so references and outputs share one method.
"""
import colorsys
import hashlib
import io
from pathlib import Path

import numpy as np

from ..rigkit import gltf as G

PARTS = {'head': ('head',), 'torso': ('pelvis', 'spine', 'root'), 'arms': ('upper_arm_l', 'forearm_l', 'upper_arm_r', 'forearm_r'),
         'hands': ('hand_l', 'hand_r'), 'legs': ('thigh_l', 'shin_l', 'thigh_r', 'shin_r'), 'feet': ('foot_l', 'foot_r')}
BANDS = 24          # silhouette bands over the normalised height
MASK = 96           # silhouette mask resolution (height = 1 -> MASK px)


def load(path):
    raw = bytes(path) if isinstance(path, (bytes, bytearray)) else Path(path).read_bytes()
    doc, binary = G.parse(raw)
    skin = doc['skins'][0]
    names = [doc['nodes'][j]['name'] for j in skin['joints']]
    ibm = G.read_accessor(doc, binary, skin['inverseBindMatrices']).reshape(-1, 4, 4)
    # glTF matrices are column-major: translation sits in elements 12..14 of each flattened matrix
    jworld = {n: -ibm[i].T[:3, 3] if abs(ibm[i].T[:3, :3] - np.eye(3)).max() < 1e-4 else np.linalg.inv(ibm[i].T)[:3, 3]
              for i, n in enumerate(names)}
    pos, tri, uv, col, jo, we, prim_mat = [], [], [], [], [], [], []
    base = 0
    for node in doc['nodes']:
        if 'mesh' not in node or 'skin' not in node:
            continue
        for p in doc['meshes'][node['mesh']]['primitives']:
            a = p['attributes']
            P = G.read_accessor(doc, binary, a['POSITION']).astype(np.float64)
            I = G.read_accessor(doc, binary, p['indices']).reshape(-1, 3).astype(np.int64)
            pos.append(P); tri.append(I + base); base += len(P)
            uv.append(G.read_accessor(doc, binary, a['TEXCOORD_0']).astype(np.float64) if 'TEXCOORD_0' in a else np.zeros((len(P), 2)))
            col.append(G.read_accessor(doc, binary, a['COLOR_0'])[:, :3].astype(np.float64) if 'COLOR_0' in a else np.ones((len(P), 3)))
            jo.append(G.read_accessor(doc, binary, a['JOINTS_0'], normalize=False).astype(np.int64))
            we.append(G.read_accessor(doc, binary, a['WEIGHTS_0']).astype(np.float64))
            prim_mat += [p.get('material')] * len(I)
    images = []
    for im in doc.get('images', []):
        if 'bufferView' in im:
            bv = doc['bufferViews'][im['bufferView']]
            data = binary[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
            from PIL import Image
            images.append(np.asarray(Image.open(io.BytesIO(bytes(data))).convert('RGBA')))
    return {'raw': raw, 'doc': doc, 'binary': binary, 'names': names, 'jworld': jworld, 'pos': np.vstack(pos), 'tri': np.vstack(tri),
            'uv': np.vstack(uv), 'col': np.vstack(col), 'joints': np.vstack(jo), 'weights': np.vstack(we),
            'prim_mat': prim_mat, 'images': images}


def dominant(m):
    """Per-vertex dominant joint name."""
    idx = m['joints'][np.arange(len(m['joints'])), np.argmax(m['weights'], axis=1)]
    return np.array([m['names'][i] for i in idx])


def part_of(joint):
    return next(k for k, v in PARTS.items() if joint in v)


def tri_parts(m):
    """Each triangle -> the joint with the largest summed weight over its corners -> body part."""
    J, W = m['joints'], m['weights']
    out = []
    for t in m['tri']:
        acc = {}
        for v in t:
            for j, w in zip(J[v], W[v]):
                if w > 0:
                    acc[j] = acc.get(j, 0.) + w
        out.append(part_of(m['names'][max(acc, key=lambda j: acc[j])]))
    return np.array(out)


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def rasterize(pts2, tri, res_w, res_h):
    """Binary mask of triangles given pixel-space 2D points (x right, y down)."""
    mask = np.zeros((res_h, res_w), bool)
    yy, xx = np.mgrid[0:res_h, 0:res_w]
    cx, cy = xx + .5, yy + .5
    for t in tri:
        a, b, c = pts2[t[0]], pts2[t[1]], pts2[t[2]]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0])))), int(min(res_w - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1])))), int(min(res_h - 1, np.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        px, py = cx[y0:y1 + 1, x0:x1 + 1], cy[y0:y1 + 1, x0:x1 + 1]
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
        l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (1 - l1 - l2 >= -1e-9)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return mask


def silhouettes(m):
    """Front (x,y) and side (z,y) masks of the rest pose, height normalised to 1, centred on the pelvis joint."""
    P = m['pos']
    y0, h = P[:, 1].min(), np.ptp(P[:, 1])
    pel = m['jworld']['pelvis']
    out = {}
    for view, axis in (('front', 0), ('side', 2)):
        u = (P[:, axis] - pel[axis]) / h          # -0.5 .. 0.5 of height
        v = (P[:, 1] - y0) / h                    # 0 .. 1
        pts = np.stack([(u + .5) * MASK, (1 - v) * MASK], axis=1)
        out[view] = rasterize(pts, m['tri'], MASK, MASK)
    return out


def band_widths(mask):
    """Width of the mask per height band, as a fraction of height (band 0 = feet)."""
    rows = mask.shape[0]
    out = []
    for b in range(BANDS):
        r0, r1 = rows - int(round((b + 1) * rows / BANDS)), rows - int(round(b * rows / BANDS))
        cols = np.where(mask[r0:r1].any(axis=0))[0]
        out.append(round(float((cols.max() - cols.min() + 1) / rows), 4) if len(cols) else 0.)
    return out


def body(m):
    P, jw = m['pos'], m['jworld']
    y0, h = P[:, 1].min(), float(np.ptp(P[:, 1]))
    dom = dominant(m)
    f = lambda v: round(float(v) / h, 4)                            # noqa: E731
    head_v = P[dom == 'head']
    neck_y = jw['head'][1]
    top = P[:, 1].max()
    lowest_head = head_v[:, 1].min()
    out = {'height_m': round(h, 4), 'ground_min_y_m': round(float(y0), 4),
           'head_height_from_neck': f(top - neck_y), 'heads_tall_from_neck': round(h / (top - neck_y), 3),
           'head_mesh_height': f(top - lowest_head), 'heads_tall_mesh': round(h / (top - lowest_head), 3),
           'head_width': f(np.ptp(head_v[:, 0])), 'head_depth': f(np.ptp(head_v[:, 2])),
           'neck_y': f(neck_y - y0), 'pelvis_y': f(jw['pelvis'][1] - y0), 'shoulder_joint_y': f(jw['upper_arm_l'][1] - y0),
           'shoulder_joint_span': f(abs(jw['upper_arm_l'][0] - jw['upper_arm_r'][0])),
           'hip_joint_span': f(abs(jw['thigh_l'][0] - jw['thigh_r'][0]))}
    def band(yc, hw, joints):
        keep = np.isin(dom, joints)
        return P[keep & (np.abs(P[:, 1] - yc) < hw * h)]
    sh = band(jw['upper_arm_l'][1], .03, ('spine', 'pelvis', 'upper_arm_l', 'upper_arm_r'))
    torso_v = P[np.isin(dom, ('spine', 'pelvis'))]
    out['shoulder_width_outer'] = f(np.ptp(sh[:, 0])) if len(sh) else None
    out['torso_width'] = f(np.ptp(torso_v[:, 0]))
    out['torso_depth'] = f(np.ptp(torso_v[:, 2]))
    hp = band(jw['thigh_l'][1], .03, ('pelvis', 'thigh_l', 'thigh_r'))
    out['hip_width_outer'] = f(np.ptp(hp[:, 0])) if len(hp) else None
    L = lambda a, b: f(np.linalg.norm(jw[a] - jw[b]))              # noqa: E731
    out.update(upper_arm=L('upper_arm_l', 'forearm_l'), forearm=L('forearm_l', 'hand_l'), thigh=L('thigh_l', 'shin_l'),
               shin=L('shin_l', 'foot_l'), arm_total=round(L('upper_arm_l', 'forearm_l') + L('forearm_l', 'hand_l'), 4),
               leg_total_joint=f(jw['thigh_l'][1] - jw['foot_l'][1]), foot_joint_y=f(jw['foot_l'][1] - y0))
    for name, a, b in (('upper_arm', 'upper_arm_l', 'forearm_l'), ('forearm', 'forearm_l', 'hand_l'),
                       ('thigh', 'thigh_l', 'shin_l'), ('shin', 'shin_l', 'foot_l')):
        vs = P[np.isin(dom, (a, a[:-1] + 'r'))]
        side = np.sign(jw[a][0])
        vs = vs[np.sign(vs[:, 0]) == side] if len(vs) else vs
        d = seg_dist(vs, jw[a], jw[b]) if len(vs) else np.array([0.])
        out[name + '_radius_median'] = f(np.median(d))
        out[name + '_radius_max'] = f(d.max())
    for name, j in (('hand', 'hand_l'), ('foot', 'foot_l')):
        vs = P[dom == j]
        out[name + '_length'] = f(max(np.ptp(vs[:, 1]), np.ptp(vs[:, 2]))) if name == 'hand' else f(np.ptp(vs[:, 2]))
        out[name + '_width'] = f(np.ptp(vs[:, 0]))
        out[name + '_height'] = f(np.ptp(vs[:, 1]))
    out['width_total'] = f(np.ptp(P[:, 0]))
    out['depth_total'] = f(np.ptp(P[:, 2]))
    # hair mass: head-weighted geometry below the neck joint (long hair), behind the head joint (back mass), above
    out['head_below_neck'] = f(max(0., neck_y - lowest_head))
    out['head_back_extent'] = f(jw['head'][2] - head_v[:, 2].min())
    out['head_front_extent'] = f(head_v[:, 2].max() - jw['head'][2])
    return out


def triangles(m):
    tp = tri_parts(m)
    n = len(tp)
    return {'total': int(n), 'share': {k: round(float((tp == k).sum()) / n, 4) for k in PARTS},
            'count': {k: int((tp == k).sum()) for k in PARTS}, 'vertices': int(len(m['pos'])),
            'vertices_per_triangle': round(len(m['pos']) / n, 3)}


def _lum(rgb):
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def texture(m):
    if not m['images']:
        return {'images': 0}
    img = m['images'][0].astype(np.float64) / 255.
    H, W = img.shape[:2]
    # texels a triangle covers (UV raster, v down like the image)
    pts = np.stack([m['uv'][:, 0] * W, m['uv'][:, 1] * H], axis=1)
    cov = rasterize(pts, m['tri'], W, H)
    rgb = img[..., :3]
    q = np.round(img * 255).astype(np.int64)
    key = (q[..., 0] << 24) | (q[..., 1] << 16) | (q[..., 2] << 8) | q[..., 3]
    used = key[cov]
    vals, counts = np.unique(used, return_counts=True)
    order = np.sort(counts)[::-1]
    cum = np.cumsum(order) / order.sum()
    lum = _lum(rgb)
    # 4-neighbour luminance steps inside covered area (gradient/noise level)
    dx = np.abs(lum[:, 1:] - lum[:, :-1])[cov[:, 1:] & cov[:, :-1]]
    dy = np.abs(lum[1:, :] - lum[:-1, :])[cov[1:, :] & cov[:-1, :]]
    steps = np.concatenate([dx, dy])
    # 2x2 checker (ordered-dither signature): a==d, b==c, a!=b
    a, b, c, d = key[:-1, :-1], key[:-1, 1:], key[1:, :-1], key[1:, 1:]
    c4 = cov[:-1, :-1] & cov[:-1, 1:] & cov[1:, :-1] & cov[1:, 1:]
    checker = ((a == d) & (b == c) & (a != b))[c4]
    # island border texels (covered with an uncovered 4-neighbour) vs interior
    pad = np.pad(cov, 1)
    interior = cov & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    border = cov & ~interior
    hsv = np.array([colorsys.rgb_to_hsv(*px) for px in rgb[cov]])
    sat = hsv[:, 1]
    hue_bins = np.zeros(12)
    for hh, ss, vv in hsv:
        if ss > .2 and vv > .12:
            hue_bins[int(hh * 12) % 12] += 1
    fam = int((hue_bins / max(1, len(hsv)) > .03).sum())
    # baked light: per-vertex texture luminance vs normal-free geometry cues (height in the body, facing up/down)
    vl = lum[np.clip((m['uv'][:, 1] * H).astype(int), 0, H - 1), np.clip((m['uv'][:, 0] * W).astype(int), 0, W - 1)]
    P = m['pos']
    tri = m['tri']
    fn = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    tl = vl[tri].mean(axis=1)
    up, down = tl[fn[:, 1] > .5], tl[fn[:, 1] < -.5]
    side = tl[np.abs(fn[:, 2]) < .25]
    front = tl[np.abs(fn[:, 2]) > .75]
    col = m['col']
    # per body part: luminance of the top third of its triangles minus the bottom third (baked vertical light)
    tp = tri_parts(m)
    cy = P[tri].mean(axis=1)[:, 1]
    grads = []
    for k in PARTS:
        sel = tp == k
        if sel.sum() < 6:
            continue
        lo_, hi_ = np.percentile(cy[sel], [33, 67])
        grads.append(float(tl[sel & (cy >= hi_)].mean() - tl[sel & (cy <= lo_)].mean()))
    lattice = np.round(np.round(q[..., :3] * 31 / 255.) * 255 / 31.)
    return {
        'part_top_minus_bottom_lum': round(float(np.mean(grads)), 4) if grads else None,
        'rgba5551_lattice_share': round(float((np.abs(lattice - q[..., :3]) < 1.).all(axis=2)[cov].mean()), 4),
        'size': [int(W), int(H)], 'images': len(m['images']), 'materials': len(m['doc'].get('materials', [])),
        'uv_coverage': round(float(cov.mean()), 4),
        'unique_colors_used': int(len(vals)), 'unique_colors_atlas': int(len(np.unique(key))),
        'colors_for_90pct': int(np.searchsorted(cum, .90) + 1), 'colors_for_95pct': int(np.searchsorted(cum, .95) + 1),
        'lum_p05': round(float(np.percentile(lum[cov], 5)), 4), 'lum_p50': round(float(np.percentile(lum[cov], 50)), 4),
        'lum_p95': round(float(np.percentile(lum[cov], 95)), 4),
        'step_mean': round(float(steps.mean()), 4), 'step_p90': round(float(np.percentile(steps, 90)), 4),
        'flat_neighbour_share': round(float((steps < 1. / 255).mean()), 4),
        'checker_share': round(float(checker.mean()) if checker.size else 0., 4),
        'border_to_interior_lum': round(float(lum[border].mean() / max(1e-6, lum[interior].mean())), 4) if interior.any() else None,
        'saturation_mean': round(float(sat.mean()), 4), 'saturation_p90': round(float(np.percentile(sat, 90)), 4),
        'hue_families': fam,
        'baked_up_minus_down_lum': round(float(up.mean() - down.mean()), 4) if len(up) and len(down) else None,
        'baked_front_minus_side_lum': round(float(front.mean() - side.mean()), 4) if len(front) and len(side) else None,
        'vertex_color_unique': int(len(np.unique(np.round(col * 255).astype(int), axis=0))),
        'vertex_color_lum_min': round(float(_lum(col).min()), 4),
        'uv_area_share': uv_share(m, W, H),
    }


def uv_share(m, W, H):
    tp = tri_parts(m)
    uv = m['uv'] * [W, H]
    t = m['tri']
    e1, e2 = uv[t[:, 1]] - uv[t[:, 0]], uv[t[:, 2]] - uv[t[:, 0]]
    area = .5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    tot = area.sum()
    return {k: round(float(area[tp == k].sum() / tot), 4) for k in PARTS}


def material(m):
    doc = m['doc']
    mats = doc.get('materials', [])
    return {'count': len(mats), 'unlit': all('KHR_materials_unlit' in (x.get('extensions') or {}) for x in mats),
            'n64_kinds': sorted({(x.get('extras') or {}).get('n64', {}).get('kind', '') for x in mats}),
            'samplers': doc.get('samplers', []), 'primitives': sum(len(me['primitives']) for me in doc['meshes']),
            'has_vertex_colors': True, 'normals': normals(m)}


def normals(m):
    """Share of vertices whose position is shared by another vertex (split for UV/normal seams)."""
    P = np.round(m['pos'], 5)
    _, inv, cnt = np.unique(P, axis=0, return_inverse=True, return_counts=True)
    out = {'unique_positions': int(len(cnt)), 'split_vertex_share': round(float((cnt[inv.ravel()] > 1).mean()), 4)}
    doc = m['doc']
    nrm = []
    for node in doc['nodes']:
        if 'mesh' in node and 'skin' in node:
            for p in doc['meshes'][node['mesh']]['primitives']:
                if 'NORMAL' in p['attributes']:
                    nrm.append(G.read_accessor(doc, m.get('binary', b''), p['attributes']['NORMAL']) if 'binary' in m else None)
    if nrm and all(n is not None for n in nrm):
        N = np.vstack(nrm).astype(np.float64)
        t = m['tri']
        fn = np.cross(m['pos'][t[:, 1]] - m['pos'][t[:, 0]], m['pos'][t[:, 2]] - m['pos'][t[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        dots = np.concatenate([np.sum(N[t[:, k]] * fn, axis=1) for k in range(3)])
        out['vertex_normal_vs_face_deg_median'] = round(float(np.degrees(np.arccos(np.clip(np.median(dots), -1, 1)))), 2)
        out['flat_corner_share'] = round(float((dots > .999).mean()), 4)
    return out


def rig(m):
    doc = m['doc']
    anim = []
    for a in doc.get('animations', []):
        ch = a['channels'][0]
        inp = doc['accessors'][a['samplers'][ch['sampler']]['input']]
        anim.append({'name': a['name'], 'keys': inp['count'], 'length_s': round(float(inp['max'][0]), 4),
                     'interp': a['samplers'][ch['sampler']].get('interpolation', 'LINEAR')})
    root = doc['nodes'][0]
    return {'skeleton': m['names'], 'skin_name': doc['skins'][0].get('name'),
            'root_identity': not any(k in root for k in ('translation', 'rotation', 'scale')),
            'clips': anim}


def model(path):
    m = load(path)
    sil = silhouettes(m)
    return {'body': body(m), 'triangles': triangles(m), 'texture': texture(m), 'material': material(m), 'rig': rig(m),
            'silhouette': {v: band_widths(sil[v]) for v in sil}, '_masks': sil, '_sha256': hashlib.sha256(m['raw']).hexdigest()}


def _range(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return {'min': round(min(vals), 4), 'max': round(max(vals), 4), 'mean': round(sum(vals) / len(vals), 4)} if vals else None


def card(models):
    """Generic ranges over the reference set (no per-model rows)."""
    def ranges(key):
        keys = models[0][key].keys()
        return {k: _range([mm[key][k] for mm in models]) for k in keys
                if all(isinstance(mm[key].get(k), (int, float)) for mm in models)}
    out = {'schema': 'hermes64-charstyle-card/1', 'references': len(models), 'method': 'tools/charcreator_measure.py',
           'body': ranges('body'), 'texture': ranges('texture'),
           'triangles': {'total': _range([mm['triangles']['total'] for mm in models]),
                         'share': {k: _range([mm['triangles']['share'][k] for mm in models]) for k in PARTS}},
           'uv_area_share': {k: _range([mm['texture']['uv_area_share'][k] for mm in models]) for k in PARTS},
           'silhouette': {v: {'bands': BANDS, 'min': [round(min(mm['silhouette'][v][b] for mm in models), 4) for b in range(BANDS)],
                              'max': [round(max(mm['silhouette'][v][b] for mm in models), 4) for b in range(BANDS)]}
                          for v in ('front', 'side')},
           'material': {'count': models[0]['material']['count'], 'unlit': all(mm['material']['unlit'] for mm in models),
                        'n64_kinds': models[0]['material']['n64_kinds'], 'samplers': models[0]['material']['samplers'],
                        'primitives': _range([mm['material']['primitives'] for mm in models])},
           'rig': {'skeleton': models[0]['rig']['skeleton'], 'skin_name': models[0]['rig']['skin_name'],
                   'clip_keys': sorted({c['keys'] for mm in models for c in mm['rig']['clips']}),
                   'clip_interp': sorted({c['interp'] for mm in models for c in mm['rig']['clips']})}}
    return out


def fit(meas, crd, tol=.10):
    """How a model sits against the card: per-metric inside [min-tol*mean, max+tol*mean]; silhouette band overlap."""
    rows, inside = {}, 0
    for k, r in crd['body'].items():
        v = meas['body'].get(k)
        if not isinstance(v, (int, float)) or r is None or k in ('height_m', 'ground_min_y_m'):
            continue
        lo, hi = r['min'] - tol * abs(r['mean']), r['max'] + tol * abs(r['mean'])
        ok = bool(lo <= v <= hi)
        rows[k] = {'value': v, 'lo': round(lo, 4), 'hi': round(hi, 4), 'inside': ok}
        inside += int(ok)
    sil = {}
    for v in ('front', 'side'):
        mn, mx = crd['silhouette'][v]['min'], crd['silhouette'][v]['max']
        w = meas['silhouette'][v]
        hits = [bool(mn[b] - .02 <= w[b] <= mx[b] + .02) for b in range(BANDS)]
        sil[v] = {'bands_inside': int(sum(hits)), 'bands': BANDS}
    return {'body_inside': inside, 'body_metrics': len(rows), 'rows': rows, 'silhouette': sil}


def iou(a, b):
    return round(float((a & b).sum() / max(1, (a | b).sum())), 4)


TEXTURE_KEYS = ('unique_colors_used', 'step_mean', 'flat_neighbour_share', 'checker_share', 'border_to_interior_lum',
                'baked_up_minus_down_lum', 'lum_p95', 'uv_coverage')


def card_fit(meas, crd, tol=.10):
    """Compact fit of one measured model against the card: body metrics inside the widened ranges, silhouette bands,
    triangle shares and texture statistics (value, card range, inside)."""
    f = fit(meas, crd, tol)
    tex = {}
    for k in TEXTURE_KEYS:
        r = crd['texture'].get(k)
        v = meas['texture'].get(k)
        if r is None or v is None:
            continue
        tex[k] = {'value': v, 'card': [r['min'], r['max']], 'inside': bool(r['min'] <= v <= r['max'])}
    head = meas['texture']['uv_area_share']['head']
    r = crd['uv_area_share']['head']
    tex['head_uv_share'] = {'value': head, 'card': [r['min'], r['max']], 'inside': bool(r['min'] <= head <= r['max'])}
    shares = {k: {'value': meas['triangles']['share'][k], 'card': [crd['triangles']['share'][k]['min'], crd['triangles']['share'][k]['max']]}
              for k in crd['triangles']['share']}
    b = meas['body']
    hb = crd['body']['heads_tall_from_neck']
    return {'height_m': b['height_m'], 'heads_tall_from_neck': b['heads_tall_from_neck'], 'card_heads_tall': [hb['min'], hb['max']],
            'body_inside': f['body_inside'], 'body_metrics': f['body_metrics'],
            'body_outside': sorted(k for k, r in f['rows'].items() if not r['inside']),
            'silhouette_bands_inside': {v: f['silhouette'][v]['bands_inside'] for v in f['silhouette']}, 'bands': f['silhouette']['front']['bands'],
            'triangles': meas['triangles']['total'], 'triangle_share': shares, 'texture': tex}
