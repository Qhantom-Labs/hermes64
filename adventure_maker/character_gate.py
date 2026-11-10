"""Automatic character gates: every generated, bound or community character passes ALL of these before it is shown
or adopted (contracts/character/1.0.0, docs/CHARACTERS.md).

  rig           lane NBCHARS's rig kit validator `adventure_maker.rigkit.validate_character` (contract rig/1.0.0):
                bone names/order/hierarchy, inverse binds, weights, budgets, proportions, every key of every clip:
                3 mm connectivity, deformation, silhouette/floor (or hover), no NaN. CHARSYS never re-implements it:
                in-process when the package has `rigkit` (after the lanes merge), else the rig kit's own CLI run from
                an explicit NBCHARS checkout (`rigkit_root`), else the gate FAILS CLOSED.
  glb           adventure_maker.glb_validate (container/accessors/skins/images) + the build's own audit errors
  palette       every texel of every image and every baked vertex colour is a colour of the style lock; every
                material is unlit (KHR_materials_unlit) with a white base factor
  cuboid        no mesh piece is a box (normals of >= 90 % of its area within 4 deg of three orthogonal axes)
  hair          face-head people: no scalp vertex pokes through the hair shell by > 1.5 mm (rest pose; hair and
                skull ride the same bone)
  silhouette    review renders read against snow and dark backgrounds (edge contrast)
  determinism   the item rebuilt in a second Blender pass is byte-identical
Each gate returns {'ok': bool, ...metrics, 'errors': [one-line strings]}; `run(...)` aggregates.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from . import glb as GLB
from . import glb_validate

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'characters' / 'gen'
EDGE_DELTA = .10          # min |luminance difference| of a silhouette edge pixel vs the background
# Share of edge pixels that must reach EDGE_DELTA, calibrated per rig family on review renders of the approved cast:
# a new character must read at least as well as the approved characters of its family.
#   humanoid (16 approved people): observed minimum snow 0.965, dark 0.145 -> both backgrounds required
#   quadruped (6 approved animals): snow 0.887, dark 0.000 (the approved black cat) -> snow >= 0.85 and readable on
#   at least one background (approved best-background minimum 0.887); dark readability is NOT enforced for animals
#   because the approved cast does not meet it
EDGE_SHARE = {'humanoid': {'snow': .90, 'dark': .12}, 'quadruped': {'snow': .85, 'dark': 0.}}
EITHER = {'humanoid': 0., 'quadruped': .85}
SNOW = (0.93, 0.95, 0.98)
DARK = (0.07, 0.08, 0.11)


def _np():
    import numpy as np  # the configured Python (doctor: numpy + Pillow)
    return np


def _fail(errors, **kw):
    return dict(kw, ok=not errors, errors=errors)


# ------------------------------------------------------------------ rig kit (lane NBCHARS)
def _rigkit_inprocess():
    try:
        from . import rigkit  # noqa: F401  (present once the NBCHARS lane is merged)
        return rigkit
    except ImportError:
        return None


def rig_gate(glb_path, rig, clips=None, profile='grounded', expect_sha256=None, rigkit_root=None, keys='all'):
    """Run validate_character; returns the rig kit's own report with 'ok' and a one-line 'errors' list added."""
    glb_path = Path(glb_path)
    rk = _rigkit_inprocess()
    if rk is not None:
        rep = rk.validate_character(glb_path, rig=rig, clips=clips, expect_sha256=expect_sha256, profile=profile, keys=keys)
        how = 'in-process'
    else:
        root = rigkit_root or os.environ.get('HERMES64_RIGKIT_ROOT')
        if not root or not (Path(root) / 'adventure_maker' / 'rigkit' / '__main__.py').is_file():
            return _fail(['rig: the rig kit validator (adventure_maker.rigkit, lane NBCHARS) is unavailable; '
                          'pass rigkit_root=<NBCHARS checkout> or merge the rig kit (gate fails closed)'],
                         rig=rig, how='unavailable')
        argv = [sys.executable, '-B', '-m', 'adventure_maker.rigkit', 'validate', str(glb_path.resolve()), '--rig', rig,
                '--profile', profile, '--keys', str(keys), '--json']
        if clips:
            argv += ['--clips', ','.join(clips)]
        if expect_sha256:
            argv += ['--expect-sha256', expect_sha256]
        env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': os.environ.get('HOME', '/tmp'),
               'TMPDIR': os.environ.get('TMPDIR', '/tmp'), 'LANG': 'C.UTF-8'}
        proc = subprocess.run(argv, cwd=str(Path(root).resolve()), capture_output=True, text=True, timeout=900, env=env)
        try:
            rep = json.loads(proc.stdout)
            if isinstance(rep, list):
                rep = rep[0]
            if isinstance(rep, dict) and 'reports' in rep:
                rep = rep['reports'][0]
        except ValueError:
            return _fail(['rig: validator produced no JSON (exit %d): %s' % (proc.returncode, (proc.stderr or '')[-300:])],
                         rig=rig, how='cli')
        how = 'cli'
    errs = ['rig %s: %s' % (e.get('code'), e.get('message')) for e in rep.get('errors', [])]
    if not rep.get('ok'):
        errs = errs or ['rig: validator reported not ok']
    return dict(rep, ok=bool(rep.get('ok')) and not errs, errors=errs, how=how)


# ------------------------------------------------------------------ GLB helpers
def _load(glb):
    raw = Path(glb).read_bytes() if not isinstance(glb, (bytes, bytearray)) else bytes(glb)
    doc, binary = GLB.read(raw)
    return raw, doc, binary


def _acc(doc, binary, i):
    np = _np()
    return np.asarray(GLB.accessor(doc, binary, i), dtype=np.float64)


def _skinned_prims(doc):
    for mi, mesh in enumerate(doc.get('meshes', [])):
        for pi, prim in enumerate(mesh['primitives']):
            yield mi, pi, prim


def glb_gate(glb, audit_errors=()):
    raw, doc, binary = _load(glb)
    rep = glb_validate.validate(raw, name=str(glb)[-60:])
    errs = ['glb %s' % e for e in (rep.get('errors') if isinstance(rep, dict) else getattr(rep, 'errors', []))]
    errs += ['audit %s' % e for e in audit_errors]
    return _fail(errs, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


# ------------------------------------------------------------------ palette + material
def _image_rgba(doc, binary, idx):
    from io import BytesIO
    from PIL import Image
    np = _np()
    im = doc['images'][idx]
    bv = doc['bufferViews'][im['bufferView']]
    data = bytes(binary[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']])
    return np.asarray(Image.open(BytesIO(data)).convert('RGBA'), dtype=np.int32)


def palette_gate(glb, palette_hex):
    """palette_hex: the lock's colours ['#rrggbb', ...]."""
    np = _np()
    raw, doc, binary = _load(glb)
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in palette_hex], dtype=np.int32)
    key = set((pal[:, 0] << 16 | pal[:, 1] << 8 | pal[:, 2]).tolist())
    errs, texels, offenders = [], 0, 0
    for i in range(len(doc.get('images', []))):
        px = _image_rgba(doc, binary, i)
        rgb = px[..., :3].reshape(-1, 3)
        k = rgb[:, 0] << 16 | rgb[:, 1] << 8 | rgb[:, 2]
        bad = ~np.isin(k, np.array(sorted(key)))
        texels += len(k)
        if bad.any():
            offenders += int(bad.sum())
            first = rgb[np.argmax(bad)]
            errs.append('palette: image %s has %d off-palette texels (e.g. #%02x%02x%02x)' % (
                doc['images'][i].get('name', i), int(bad.sum()), *first))
    vc_bad = 0
    for mi, pi, prim in _skinned_prims(doc):
        if 'COLOR_0' not in prim['attributes']:
            continue
        c = _acc(doc, binary, prim['attributes']['COLOR_0'])[:, :3]
        s = np.where(c <= .0031308, 12.92 * c, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - .055)
        s8 = np.clip(np.round(s * 255.), 0, 255).astype(np.int32)
        d = np.abs(s8[:, None, :] - pal[None, :, :]).max(axis=2).min(axis=1)
        vc_bad += int((d > 1).sum())
    if vc_bad:
        errs.append('palette: %d baked vertex colours are not lock colours' % vc_bad)
    for m in doc.get('materials', []):
        name = m.get('name', '?')
        if 'KHR_materials_unlit' not in m.get('extensions', {}):
            errs.append('material %s is not unlit' % name)
        f = m.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
        if any(abs(x - 1.) > 1e-6 for x in f[:3]):
            errs.append('material %s has a tinted base factor %s' % (name, f))
    return _fail(errs, images=len(doc.get('images', [])), texels=texels, off_palette=offenders, vertex_colour_off=vc_bad)


# ------------------------------------------------------------------ no cuboids
def _pieces(pos, tris):
    """Connected components after welding by position (1e-5 m)."""
    np = _np()
    q = np.round(pos / 1e-5).astype(np.int64)
    _, weld = np.unique(q, axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    parent = list(range(int(weld.max()) + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in tris:
        a, b, c = (find(int(weld[t[0]])), find(int(weld[t[1]])), find(int(weld[t[2]])))
        parent[b] = a
        parent[find(c)] = a
    comp = np.array([find(int(weld[t[0]])) for t in tris])
    return comp


def cuboid_gate(glb):
    np = _np()
    raw, doc, binary = _load(glb)
    errs, n_pieces, worst = [], 0, 0.
    for mi, pi, prim in _skinned_prims(doc):
        pos = _acc(doc, binary, prim['attributes']['POSITION'])
        idx = _acc(doc, binary, prim['indices']).astype(np.int64).reshape(-1, 3)
        comp = _pieces(pos, idx)
        for c in np.unique(comp):
            t = idx[comp == c]
            n_pieces += 1
            a, b, cc = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
            cr = np.cross(b - a, cc - a)
            area = np.linalg.norm(cr, axis=1)
            if area.sum() < 1e-6:
                continue
            nrm = cr / np.maximum(area[:, None], 1e-12)
            # dominant axis frame: the normal of the largest-area triangle, then the largest orthogonal one
            order = np.argsort(-area)
            ax1 = nrm[order[0]]
            ortho = np.abs(nrm @ ax1) < math.sin(math.radians(4))
            if not ortho.any():
                continue
            ax2 = nrm[order[np.argmax(ortho[order])]]
            ax3 = np.cross(ax1, ax2)
            ax3 /= max(np.linalg.norm(ax3), 1e-12)
            dots = np.abs(nrm @ np.stack([ax1, ax2, ax3]).T).max(axis=1)
            share = float(area[dots > math.cos(math.radians(4))].sum() / area.sum())
            worst = max(worst, share)
            if share >= .90 and len(t) >= 10:
                lo, hi = pos[t.reshape(-1)].min(axis=0), pos[t.reshape(-1)].max(axis=0)
                errs.append('cuboid: mesh %d piece of %d tris is a box (%.0f%% axis-aligned area, %.2fx%.2fx%.2f m)' % (
                    mi, len(t), share * 100, *(hi - lo)))
    return _fail(errs, pieces=n_pieces, max_axis_share=round(worst, 3))


# ------------------------------------------------------------------ hair clearance (face-head people)
def _gen_mesh(params_json):
    from .character_recipe import gen_module
    return gen_module('core.people').person(json.loads(params_json))


def _ring_at(phi, ring):
    """Periodic linear interpolation of (z, r) samples of one ring at azimuth phi. ring: [(phi, z, r)] sorted."""
    n = len(ring)
    for k in range(n):
        p0, z0, r0 = ring[k]
        p1, z1, r1 = ring[(k + 1) % n]
        if k == n - 1:
            p1 += 2 * math.pi
        q = phi if phi >= p0 else phi + 2 * math.pi
        if p0 <= q <= p1:
            w = (q - p0) / max(p1 - p0, 1e-12)
            return z0 + (z1 - z0) * w, r0 + (r1 - r0) * w
    return ring[0][1], ring[0][2]


def hair_check_mesh(m, tol=.0015):
    """Generator-space (Z up) check for the face-head topology: the hair shell (hem ring, temple/dome/crown rings and
    the crown point, built at skull radius + thickness + 8 mm) closes the cranium above the face loft. Every face-loft
    vertex ABOVE the hem at its azimuth must stay inside the hair profile of that meridian; one beyond it is skin
    poking through the hair."""
    np = _np()
    if 'hair' not in m.parts or 'face' not in m.parts or m.params.get('hair') == 'bald':
        return _fail([], tested=0, covered=0, max_poke_m=0.)
    V = np.asarray(m.vertices, dtype=np.float64)
    hid = sorted(set(m.parts['hair']))
    if len(hid) != 41:
        return _fail(['hair: unexpected hair shell topology (%d vertices)' % len(hid)], tested=0, covered=0, max_poke_m=0.)
    rings_v = [V[hid[k * 10:(k + 1) * 10]] for k in range(4)]
    crown = V[hid[40]]
    cx, cy = np.concatenate(rings_v[1:]).mean(axis=0)[:2]
    rings = []
    for R in rings_v:
        ph = np.arctan2(R[:, 0] - cx, -(R[:, 1] - cy)) % (2 * math.pi)
        rr = np.hypot(R[:, 0] - cx, R[:, 1] - cy)
        rings.append(sorted(zip(ph.tolist(), R[:, 2].tolist(), rr.tolist())))
    covered, worst, pokes = 0, 0., 0
    face = sorted(set(m.parts['face']))
    for vi in face:
        x, y, z = V[vi]
        phi = math.atan2(x - cx, -(y - cy)) % (2 * math.pi)
        r = math.hypot(x - cx, y - cy)
        prof = [_ring_at(phi, ring) for ring in rings] + [(float(crown[2]), 0.)]
        if z <= prof[0][0]:
            continue                      # below the hem: face, ears, neck - not under the hair
        covered += 1
        if z >= prof[-1][0]:
            rh = 0.
        else:
            rh = 0.
            for (z0, r0), (z1, r1) in zip(prof, prof[1:]):
                if z0 <= z <= z1:
                    rh = r0 + (r1 - r0) * (z - z0) / max(z1 - z0, 1e-12)
                    break
        poke = r - rh
        if poke > tol:
            pokes += 1
            worst = max(worst, poke)
    errs = ['hair: %d head vertices poke through the hair shell (worst %.1f mm)' % (pokes, worst * 1000)] if pokes else []
    return _fail(errs, tested=len(face), covered=covered, max_poke_m=round(worst, 5))


def hair_gate(params_json, kind):
    if kind != 'person':
        return _fail([], skipped='not a face-head person')
    return hair_check_mesh(_gen_mesh(params_json))


# ------------------------------------------------------------------ silhouette readability
def _lum(rgb):
    np = _np()
    lin = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return lin @ np.array([.2126, .7152, .0722])


def silhouette_gate(render_paths, family='humanoid'):
    """render_paths: transparent-film RGBA PNGs (front / three-quarter / side); family: humanoid | quadruped."""
    from PIL import Image
    np = _np()
    errs, shares = [], {}
    for p in render_paths:
        px = np.asarray(Image.open(p).convert('RGBA'), dtype=np.float64) / 255.
        alpha = px[..., 3] > .5
        if alpha.sum() < 40:
            errs.append('silhouette: %s is nearly empty (%d px)' % (Path(p).name, int(alpha.sum())))
            continue
        inner = alpha.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            inner &= np.roll(np.roll(alpha, dy, 0), dx, 1)
        edge = alpha & ~inner
        lum = _lum(px[..., :3])[edge]
        best = 0.
        for name, bg in (('snow', SNOW), ('dark', DARK)):
            lb = float(_lum(np.array(bg)))
            share = float((np.abs(lum - lb) >= EDGE_DELTA).mean())
            best = max(best, share)
            shares['%s:%s' % (Path(p).stem, name)] = round(share, 3)
            if share < EDGE_SHARE[family][name]:
                errs.append('silhouette: %s loses its outline on %s (%.0f%% of edge pixels readable, need %.0f%%)' % (
                    Path(p).stem, name, share * 100, EDGE_SHARE[family][name] * 100))
        if best < EITHER[family]:
            errs.append('silhouette: %s reads on neither background (best %.0f%%, need %.0f%%)' % (
                Path(p).stem, best * 100, EITHER[family] * 100))
    return _fail(errs, edge_share=shares)


# ------------------------------------------------------------------ aggregate
ORDER = ('glb', 'rig', 'palette', 'cuboid', 'hair', 'silhouette', 'determinism')


def run(glb_path, *, rig, clips, profile, palette_hex, kind, params_json=None, audit_errors=(), renders=(),
        determinism=None, rigkit_root=None, expect_sha256=None, keys='all', review=None):
    """review: why there are no review renders (no renderer on this host). The silhouette gate is then reported as
    skipped with that reason; it is never counted as passed, and without a reason missing renders still fail."""
    if renders:
        silhouette = silhouette_gate(renders, 'quadruped' if rig.startswith('quad') else 'humanoid')
    elif review:
        silhouette = _fail([], skipped=review, ran=False)
    else:
        silhouette = _fail(['silhouette: no review renders'])
    gates = {'glb': glb_gate(glb_path, audit_errors),
             'rig': rig_gate(glb_path, rig, clips=clips, profile=profile, expect_sha256=expect_sha256,
                             rigkit_root=rigkit_root, keys=keys),
             'palette': palette_gate(glb_path, palette_hex),
             'cuboid': cuboid_gate(glb_path),
             'hair': hair_gate(params_json, kind) if params_json else _fail([], skipped='no generator params'),
             'silhouette': silhouette,
             'determinism': determinism if determinism is not None else _fail(['determinism: not rebuilt'])}
    errors = [e for k in ORDER for e in gates[k]['errors']]
    slim = {k: {kk: vv for kk, vv in v.items() if kk not in ('checks', 'metrics', 'warnings') or k != 'rig'} for k, v in gates.items()}
    slim['rig']['checks'] = {k: v.get('ok') for k, v in gates['rig'].get('checks', {}).items()}
    not_run = {k: gates[k]['skipped'] for k in ORDER if gates[k].get('ran') is False}
    out = {'schema': 'hermes64-character-gates/1.0.0', 'ok': not errors, 'errors': errors, 'gates': slim}
    if not_run:
        out['not_run'] = not_run
    return out
