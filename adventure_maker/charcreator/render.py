"""Software preview renderer (numpy + Pillow): front / three-quarter / side / back views of a GLB, no Blender or Godot.

It renders the shipped file (every primitive, posed by rigkit.lbs at rest or at a clip key) with a z-buffer,
bilinear texture sampling (as the game's three-point filter blurs a 64 px atlas) and a light approximation of the
card's capture: the atlas already carries baked light, so the renderer multiplies it by ambient + a soft key.
This is a review image, not the game's N64 shader: the private lineup uses the Godot capture for like-for-like.
Outputs transparent RGBA views (the silhouette gate's inputs) and a labelled contact sheet.
"""
import io
import math

import numpy as np

VIEWS = {'front': 0., 'three_quarter': -40., 'side': -90., 'back': 180.}
GATE_VIEWS = ('front', 'three_quarter', 'side')
BG = (196, 198, 201)
LIGHT = np.array([.35, .75, .55]) / np.linalg.norm([.35, .75, .55])


def _load(raw, clip=None, key=0):
    from ..rigkit import gltf, lbs
    doc, binary = gltf.parse(raw)
    prims = lbs.primitives(doc, binary)
    pos = lbs.posed(doc, binary, clip, key, prims)
    from PIL import Image
    tex = {}
    out = []
    for r, P in zip(prims, pos):
        p = doc['meshes'][r['mesh']]['primitives'][r['prim']]
        uv = gltf.read_accessor(doc, binary, p['attributes']['TEXCOORD_0']).astype(np.float64)
        mi = p.get('material')
        img = None
        if mi is not None:
            ti = doc['materials'][mi]['pbrMetallicRoughness']['baseColorTexture']['index']
            si = doc['textures'][ti]['source']
            if si not in tex:
                im = doc['images'][si]
                bv = doc['bufferViews'][im['bufferView']]
                data = bytes(binary[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']])
                tex[si] = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'), np.float64) / 255.
            img = tex[si]
        out.append((P, r['indices'].reshape(-1, 3), uv, img))
    return out


def _normals(P, F):
    q = np.round(P / 1e-5).astype(np.int64)
    _, weld = np.unique(q, axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    acc = np.zeros((weld.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, weld[F[:, k]], fn)
    N = acc[weld]
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _sample(img, uv):
    H, W = img.shape[:2]
    x = uv[:, 0] * W - .5
    y = uv[:, 1] * H - .5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    def at(yy, xx):
        return img[np.clip(yy, 0, H - 1), np.clip(xx, 0, W - 1)]
    return (at(y0, x0) * (1 - fx) * (1 - fy) + at(y0, x0 + 1) * fx * (1 - fy) + at(y0 + 1, x0) * (1 - fx) * fy
            + at(y0 + 1, x0 + 1) * fx * fy)


def render(raw, views=VIEWS, size=(176, 224), clip=None, key=0, pitch=8., height=None):
    """-> {view: RGBA uint8 array}. Every view uses one scale: the frame fits `height` metres (default: this model)."""
    geo = _load(raw, clip, key)
    allp = np.concatenate([g[0] for g in geo])
    top = float(allp[:, 1].max())
    span = max(height or 0., top) * 1.06
    W, Hh = size
    scale = Hh / span
    cx = float(np.median(allp[:, 0]))
    cz = float(np.median(allp[:, 2]))
    out = {}
    for name, yaw in (views.items() if isinstance(views, dict) else ((v, VIEWS[v]) for v in views)):
        a, b = math.radians(yaw), math.radians(pitch)
        Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
        Rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
        R = Rx @ Ry
        zbuf = np.full((Hh, W), -1e9)
        rgb = np.zeros((Hh, W, 3))
        alpha = np.zeros((Hh, W), bool)
        light = LIGHT
        for P, F, uv, img in geo:
            Q = (P - np.array([cx, 0., cz])) @ R.T
            N = _normals(P, F) @ R.T
            sx = W / 2. + Q[:, 0] * scale
            sy = Hh - (Q[:, 1] * scale + Hh * .03)
            for t in F:
                xs, ys = sx[t], sy[t]
                x0, x1 = int(max(0, math.floor(xs.min()))), int(min(W - 1, math.ceil(xs.max())))
                y0, y1 = int(max(0, math.floor(ys.min()))), int(min(Hh - 1, math.ceil(ys.max())))
                if x1 < x0 or y1 < y0:
                    continue
                d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
                if abs(d) < 1e-9:
                    continue
                gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                px, py = gx + .5, gy + .5
                l0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / d
                l1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / d
                l2 = 1 - l0 - l1
                m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
                if not m.any():
                    continue
                z = l0 * Q[t[0], 2] + l1 * Q[t[1], 2] + l2 * Q[t[2], 2]
                gyx, gxx = gy[m], gx[m]
                zz = z[m]
                closer = zz > zbuf[gyx, gxx]
                if not closer.any():
                    continue
                gyx, gxx, zz = gyx[closer], gxx[closer], zz[closer]
                L0, L1, L2 = l0[m][closer], l1[m][closer], l2[m][closer]
                n = L0[:, None] * N[t[0]] + L1[:, None] * N[t[1]] + L2[:, None] * N[t[2]]
                n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
                if img is not None:
                    u = L0[:, None] * uv[t[0]] + L1[:, None] * uv[t[1]] + L2[:, None] * uv[t[2]]
                    c = _sample(img, u)
                else:
                    c = np.full((len(zz), 3), .7)
                vl = np.clip(.78 + .3 * (n @ (R @ light)), .55, 1.12)
                zbuf[gyx, gxx] = zz
                rgb[gyx, gxx] = np.clip(c * vl[:, None], 0, 1)
                alpha[gyx, gxx] = True
        im = np.zeros((Hh, W, 4), np.uint8)
        im[..., :3] = np.round(rgb * 255).astype(np.uint8)
        im[..., 3] = np.where(alpha, 255, 0).astype(np.uint8)
        out[name] = im
    return out


def png(im):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(im).save(buf, 'PNG')
    return buf.getvalue()


def sheet(views, label=None, notes=None, bg=BG, zoom=2):
    """Views side by side over a neutral background (+ a label line), nearest-neighbour zoom."""
    from PIL import Image, ImageDraw
    tiles = []
    for name in ('front', 'three_quarter', 'side', 'back'):
        if name not in views:
            continue
        im = Image.fromarray(views[name])
        base = Image.new('RGBA', im.size, bg + (255,))
        base.alpha_composite(im)
        tiles.append(base.convert('RGB'))
    w = sum(t.size[0] for t in tiles)
    h = tiles[0].size[1]
    extra = 14 if (label or notes) else 0
    out = Image.new('RGB', (w, h + extra), bg)
    x = 0
    for t in tiles:
        out.paste(t, (x, extra))
        x += t.size[0]
    if label or notes:
        ImageDraw.Draw(out).text((3, 1), ((label or '') + ('  ' + notes if notes else ''))[:120], fill=(30, 30, 34))
    out = out.resize((out.size[0] * zoom, out.size[1] * zoom), Image.NEAREST)
    buf = io.BytesIO()
    out.save(buf, 'PNG')
    return buf.getvalue()
