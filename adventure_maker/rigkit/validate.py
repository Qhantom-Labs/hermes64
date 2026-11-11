"""validate_character(glb, rig): does a character GLB conform to a rig contract? (stdlib + numpy LBS reference)

Every check reports metrics under report['checks'][name]; any error makes report['ok'] False. Error codes are the
stable surface documented in docs/RIGKIT-API.md section 4.
"""
import hashlib
import math
from pathlib import Path

import numpy as np

from . import gltf, lbs
from .rig import load_rig

FLOAT = 5126
ROT_TOL = 1e-4          # rest rotation must be identity within this (quaternion components)
QUAT_TOL = 1e-3         # clip quaternion norm tolerance
ROOT_DRIFT_TOL = 1e-5   # metres of horizontal root translation allowed
TIME_TOL = 1e-5
PROFILES = ('grounded', 'hover')
EDGE_LIMITS = (.45, 1.8)
# Declared clip forms (lane CHARBIND, docs/CHARBIND-RESULT.md "rig contract amendment"). Only what a file declares is
# judged by these rules; an undeclared key or clip keeps the rig's own floor and root-motion rules.
#   run flight: the locomotion block (root extras hermes64_locomotion, base_v1 bake) lists the run keys that leave the
#     floor, and the run clip carries the same base in its extras. On exactly those keys the lowest vertex may be above
#     the floor, at most FLIGHT_MAX_FRACTION x rest height; it may never sink below it.
#   seated: an animation with extras hermes64_seat {height_m} sits on a seat. Its root keeps one horizontal placement
#     on every key (at most SEAT_MAX_OFFSET_M from rest) and its lowest vertex never goes below the floor.
LOCOMOTION_BLOCK = 'hermes64_locomotion'
SEAT_KEY = 'hermes64_seat'
FLIGHT_MAX_FRACTION = .15
SEAT_MAX_OFFSET_M = .5
SEAT_HEIGHT_M = (.2, 1.2)


def declarations(doc):
    """{'flight': {clip: set(keys)}, 'seats': {clip: seat height m}} that this file declares (see above)."""
    out = {'flight': {}, 'seats': {}}
    anims = {a.get('name'): a for a in doc.get('animations', [])}
    block = (doc.get('extras') or {}).get(LOCOMOTION_BLOCK)
    if isinstance(block, dict) and 'run' in anims:
        keys = (block.get('run') or {}).get('flight_keys')
        tagged = (anims['run'].get('extras') or {}).get(LOCOMOTION_BLOCK)
        if tagged and tagged == block.get('base') and isinstance(keys, list) and all(type(k) is int for k in keys):
            out['flight']['run'] = set(keys)
    for name, a in anims.items():
        seat = (a.get('extras') or {}).get(SEAT_KEY)
        h = seat.get('height_m') if isinstance(seat, dict) else None
        if isinstance(h, (int, float)) and SEAT_HEIGHT_M[0] <= h <= SEAT_HEIGHT_M[1]:
            out['seats'][name] = float(h)
    return out


class Report:
    def __init__(self, rig, sha):
        self.d = {'schema': 'hermes64-rig-validate/1.0.0', 'ok': True, 'rig': rig.tag, 'file_sha256': sha,
                  'errors': [], 'warnings': [], 'checks': {}, 'metrics': {}}

    def check(self, name, **metrics):
        c = self.d['checks'].setdefault(name, {'ok': True})
        c.update(metrics)
        return c

    def error(self, check, code, message, path=''):
        self.d['errors'].append({'code': code, 'message': message, 'path': path, 'check': check})
        self.check(check)['ok'] = False
        self.d['ok'] = False

    def warn(self, check, code, message, path=''):
        self.d['warnings'].append({'code': code, 'message': message, 'path': path, 'check': check})


def _raw(glb):
    if isinstance(glb, (bytes, bytearray)):
        return bytes(glb)
    return Path(glb).read_bytes()


def _container(rep, raw):
    from .. import glb_validate
    r = glb_validate.validate(raw, 'character')
    errs = [i for i in r.issues if i['severity'] == 'error']
    for i in errs:
        rep.error('container', i['code'], i['message'], i.get('path', ''))
    rep.check('container', issues=len(r.issues), errors=len(errs))
    return not errs


def _finite(rep, doc, binary):
    bad = []
    for i, a in enumerate(doc.get('accessors', [])):
        if a.get('componentType') != FLOAT or 'bufferView' not in a:
            continue
        arr = gltf.read_accessor(doc, binary, i)
        if not np.isfinite(arr).all():
            bad.append(i)
    for i in bad:
        rep.error('finite', 'data.nan', 'accessor %d has NaN/Inf' % i, 'accessors[%d]' % i)
    for i, n in enumerate(doc.get('nodes', [])):
        for k in ('translation', 'rotation', 'scale', 'matrix'):
            if k in n and not all(isinstance(x, (int, float)) and math.isfinite(x) for x in n[k]):
                rep.error('finite', 'data.nan', 'node %d %s not finite' % (i, k), 'nodes[%d]' % i)
    rep.check('finite', float_accessors_bad=len(bad))


def _rig(rep, rig, doc, binary, profile='grounded'):
    skins = doc.get('skins', [])
    if len(skins) != 1:
        rep.error('rig', 'rig.skin_count', 'exactly one skin required, found %d' % len(skins))
        return None
    sk = skins[0]
    nodes = doc['nodes']
    names = [nodes[j].get('name') for j in sk['joints']]
    if sorted(names) != sorted(rig.bones):
        missing = sorted(set(rig.bones) - set(names))
        extra = sorted(set(names) - set(rig.bones))
        rep.error('rig', 'rig.bone_names', 'joint names differ from %s (missing %s, extra %s)' % (rig.id, missing, extra))
        return None
    if names != rig.bones:
        rep.error('rig', 'rig.bone_order', 'joint order %s != contract %s' % (names, rig.bones))
    parents = gltf.node_parents(doc)
    idx = {nodes[j].get('name'): j for j in sk['joints']}
    for b in rig.bones:
        p = parents.get(idx[b])
        want = rig.parents[b]
        got = nodes[p].get('name') if p is not None else None
        if want is not None and got != want:
            rep.error('rig', 'rig.hierarchy', 'joint %s parent %s, contract %s' % (b, got, want))
        if want is None and got in idx:
            rep.error('rig', 'rig.hierarchy', 'root joint %s is parented to joint %s' % (b, got))
    max_rot = 0.0
    for b in rig.bones:
        n = nodes[idx[b]]
        r = n.get('rotation', [0, 0, 0, 1])
        s = n.get('scale', [1, 1, 1])
        dev = max(abs(r[0]), abs(r[1]), abs(r[2]), abs(abs(r[3]) - 1), *[abs(x - 1) for x in s])
        max_rot = max(max_rot, dev)
        if 'matrix' in n or dev > ROT_TOL:
            rep.error('rig', 'rig.rest_rotation', 'joint %s rest rotation/scale is not identity' % b, 'nodes[%d]' % idx[b])
    world = lbs.world_matrices(doc)
    ibm = lbs.inverse_binds(doc, binary)
    ibm_err = None
    if ibm is None:
        rep.error('rig', 'rig.ibm_missing', 'skin has no inverseBindMatrices')
    elif len(ibm) != len(sk['joints']):
        rep.error('rig', 'rig.ibm_missing', 'inverseBindMatrices count %d != joints %d' % (len(ibm), len(sk['joints'])))
    else:
        # IBM must invert the rest world matrix (relative to the skinned mesh node, identity here)
        ibm_err = 0.0
        for k, j in enumerate(sk['joints']):
            e = float(np.abs(ibm[k] @ world[j] - np.eye(4)).max())
            ibm_err = max(ibm_err, e)
        tol = rig.doc['skin'].get('ibm_tolerance_m', 1e-5)
        if ibm_err > tol * 10 + 1e-6:
            rep.error('rig', 'rig.ibm_mismatch', 'IBM x rest world deviates from identity by %.3g' % ibm_err)
    # proportions: segment length / rest body height. Grounded: lowest to highest rendered vertex. Hover: floor (the
    # rig's y = 0) to highest vertex, because a floater's hover gap stands in for the weightless legs (rig.json hover)
    prims = lbs.primitives(doc, binary)
    body = [r for r in prims if r['joints'] is not None]
    height = None
    if body:
        pos = np.concatenate([r['positions'][r['used']] for r in body])
        if not len(pos):
            height = 0.
        elif profile == 'hover':
            height = float(pos[:, 1].max())
        else:
            height = float(pos[:, 1].max() - pos[:, 1].min())
        pr = rig.proportions
        lo, hi = pr.get('height_m', [0, 99])
        if not lo <= height <= hi:
            rep.error('rig', 'rig.proportions', 'rest height %.3f m outside %s' % (height, [lo, hi]))
        for b, (flo, fhi) in pr.get('segment_fraction_of_height', {}).items():
            d = world[idx[b]][:3, 3] - world[idx[rig.parents[b]]][:3, 3]
            f = float(np.linalg.norm(d)) / height if height > 0 else 0.
            if not flo <= f <= fhi:
                rep.error('rig', 'rig.proportions', 'segment %s = %.4f x height outside %s' % (b, f, [flo, fhi]))
    rep.check('rig', joints=len(names), rest_rotation_dev=max_rot, ibm_err=ibm_err, rest_height_m=height,
              height_basis='floor_to_top' if profile == 'hover' else 'mesh_extent')
    return {'skin': sk, 'idx': idx, 'prims': prims, 'body': body, 'height': height}


def _skin(rep, rig, doc, binary, ctx):
    nj = len(ctx['skin']['joints'])
    worst_sum = 0.0
    max_inf = 0
    for r in ctx['body']:
        w = r['weights']
        j = r['joints']
        attrs = doc['meshes'][r['mesh']]['primitives'][r['prim']]['attributes']
        nz = (w > 0).sum(axis=1)
        max_inf = max(max_inf, int(nz.max()) if len(nz) else 0)
        if 'JOINTS_1' in attrs or 'WEIGHTS_1' in attrs or (nz > 4).any():
            rep.error('skin', 'skin.influences', '%s primitive %d uses more than 4 influences' % (r['name'], r['prim']))
        s = w.sum(axis=1)
        dev = float(np.abs(s - 1).max()) if len(s) else 0.
        worst_sum = max(worst_sum, dev)
        if dev > rig.doc['skin'].get('weights_sum_tolerance', 1e-3):
            rep.error('skin', 'skin.weights_sum', '%s primitive %d weights sum off by %.4g' % (r['name'], r['prim'], dev))
        if (w < 0).any():
            rep.error('skin', 'skin.negative_weight', '%s primitive %d has negative weights' % (r['name'], r['prim']))
        if (j[w > 0] >= nj).any():
            rep.error('skin', 'skin.joint_index', '%s primitive %d joint index >= %d' % (r['name'], r['prim'], nj))
    rep.check('skin', max_influences=max_inf, weights_sum_dev=worst_sum)


def _clips(rep, rig, doc, binary, ctx, clips, combat, profile='grounded', decl=None):
    seats = (decl or {}).get('seats', {})
    anims = {a.get('name'): a for a in doc.get('animations', [])}
    want = list(clips) if clips is not None else rig.required_clips(combat)
    if profile == 'hover' and clips is None:          # rig.json hover.optional_clips (sit): checked only when present
        opt = set((rig.doc.get('hover') or {}).get('optional_clips', []))
        want = [c for c in want if c not in opt or c in anims]
    for c in want:
        if c not in anims:
            rep.error('clips', 'clip.missing', 'clip %s missing' % c)
    nodes = doc['nodes']
    idx = ctx['idx']
    rot_need = set(rig.rotation_bones())
    tr_need = set(rig.translation_bones())
    k = rig.clips['keys']
    fps = float(rig.clips['fps'])
    times_want = np.arange(k) / fps
    limits = rig.limits
    worst_angle = {}
    checked = []
    for name in want:
        an = anims.get(name)
        if an is None:
            continue
        checked.append(name)
        have = {}
        for ch in an['channels']:
            nm = nodes[ch['target']['node']].get('name')
            have.setdefault((nm, ch['target']['path']), []).append(ch)
            s = an['samplers'][ch['sampler']]
            if s.get('interpolation', 'LINEAR') != 'STEP':
                rep.error('clips', 'clip.interpolation', '%s %s.%s is %s, not STEP' % (name, nm, ch['target']['path'], s.get('interpolation', 'LINEAR')))
            t = gltf.read_accessor(doc, binary, s['input'])[:, 0].astype(np.float64)
            if len(t) != k:
                rep.error('clips', 'clip.key_count', '%s %s.%s has %d keys, contract %d' % (name, nm, ch['target']['path'], len(t), k))
            elif np.abs(t - times_want).max() > TIME_TOL:
                rep.error('clips', 'clip.time_mismatch', '%s %s.%s key times differ from k/15 by %.3g s' % (name, nm, ch['target']['path'], np.abs(t - times_want).max()))
            v = gltf.read_accessor(doc, binary, s['output']).astype(np.float64)
            path = ch['target']['path']
            if path == 'rotation':
                nrm = np.linalg.norm(v, axis=1)
                if np.abs(nrm - 1).max() > QUAT_TOL:
                    rep.error('clips', 'clip.quat_norm', '%s %s rotation not unit (%.4g)' % (name, nm, np.abs(nrm - 1).max()))
                ang = float(np.degrees(2 * np.arccos(np.clip(np.abs(v[:, 3]) / np.maximum(nrm, 1e-12), 0, 1))).max())
                worst_angle[nm] = max(worst_angle.get(nm, 0.), ang)
                lim = limits.get(nm, {}).get('max_angle_deg')
                if lim is not None and ang > lim + 1e-6:
                    rep.warn('clips', 'clip.joint_limit', '%s %s rotates %.1f deg > limit %.1f' % (name, nm, ang, lim))
            elif path == 'translation':
                rest = np.array(nodes[ch['target']['node']].get('translation', [0, 0, 0]), dtype=np.float64)
                if name in seats:          # declared seat: one fixed horizontal placement, no travel
                    drift = float(max(np.abs(v[:, 0] - v[0, 0]).max(), np.abs(v[:, 2] - v[0, 2]).max()))
                    if math.hypot(v[0, 0] - rest[0], v[0, 2] - rest[2]) > SEAT_MAX_OFFSET_M:
                        rep.error('clips', 'clip.root_motion', '%s %s seat placement %.3f m from rest > %.2f' % (
                            name, nm, math.hypot(v[0, 0] - rest[0], v[0, 2] - rest[2]), SEAT_MAX_OFFSET_M))
                else:
                    drift = float(max(np.abs(v[:, 0] - rest[0]).max(), np.abs(v[:, 2] - rest[2]).max()))
                if drift > ROOT_DRIFT_TOL:
                    rep.error('clips', 'clip.root_motion', '%s %s horizontal translation drift %.4g m' % (name, nm, drift))
        for b in sorted(rot_need):
            if (b, 'rotation') not in have:
                rep.error('clips', 'clip.channel_missing', '%s has no rotation channel for %s' % (name, b))
        for b in sorted(tr_need):
            if (b, 'translation') not in have:
                rep.error('clips', 'clip.channel_missing', '%s has no translation channel for %s' % (name, b))
        for (nm, path), chs in sorted(have.items()):
            ok = (path == 'rotation' and nm in rot_need) or (path == 'translation' and nm in tr_need)
            if not ok or len(chs) > 1:
                rep.error('clips', 'clip.extra_channel', '%s has an unexpected %s channel on %s' % (name, path, nm))
    rep.check('clips', checked=checked, required=want, max_angle_deg={k2: round(v2, 2) for k2, v2 in sorted(worst_angle.items())})
    return checked


def _budget(rep, rig, doc, budget):
    b = dict(rig.budgets)
    if budget:
        b.update(budget)
    nodes = doc.get('nodes', [])

    def tris(mi):
        return sum(doc['accessors'][p['indices']]['count'] // 3 for p in doc['meshes'][mi]['primitives'] if 'indices' in p)
    body = sum(tris(n['mesh']) for n in nodes if 'mesh' in n and 'skin' in n)
    props = {n.get('name', 'node%d' % i): tris(n['mesh']) for i, n in enumerate(nodes) if 'mesh' in n and 'skin' not in n}
    if 'body_tris_lt' in b and not body < b['body_tris_lt']:
        rep.error('budget', 'budget.body', 'body %d tris, budget < %d' % (body, b['body_tris_lt']))
    if 'body_tris_le' in b and not body <= b['body_tris_le']:
        rep.error('budget', 'budget.body', 'body %d tris, budget <= %d' % (body, b['body_tris_le']))
    for nm, t in props.items():
        if t > b.get('prop_tris_le', 200):
            rep.error('budget', 'budget.prop', 'prop %s %d tris > %d' % (nm, t, b.get('prop_tris_le', 200)))
    rep.check('budget', body_tris=body, prop_tris=props, budgets=b)


def _edges(prim):
    ind = prim['indices'].reshape(-1, 3)
    e = np.concatenate([ind[:, [0, 1]], ind[:, [1, 2]], ind[:, [2, 0]]])
    e.sort(axis=1)
    return np.unique(e, axis=0)


def _posed_checks(rep, rig, doc, binary, ctx, clips, keys, profile, tol_m, connectivity_fn, decl=None):
    flight = (decl or {}).get('flight', {})
    seats = (decl or {}).get('seats', {})
    body = ctx['body']
    prims = ctx['prims']
    if not body:
        rep.error('deformation', 'mesh.no_skinned_body', 'no skinned primitive')
        return
    edges = [_edges(r) for r in body]
    rest = [r['positions'] for r in body]
    rest_len = [np.linalg.norm(p[e[:, 0]] - p[e[:, 1]], axis=1) for p, e in zip(rest, edges)]
    valid = [l > 1e-9 for l in rest_len]
    lo, hi = 1.0, 1.0
    worst_at = None
    sil = rig.silhouette
    floor_tol = sil.get('floor_tolerance_m', .002)
    floor_mode = sil.get('floor', 'touch')
    H = ctx['height'] or 1.
    blow = sil.get('blowup_height_factor', 1.6)
    depart = sil.get('max_vertex_departure_m', .5)
    hover = 0.
    if profile == 'hover':
        from .clips import _hover_m
        hover = _hover_m(doc, rig) or 0.
        if hover <= 0.:
            rep.error('silhouette', 'mesh.silhouette.hover_missing', "profile='hover' needs rig node extras hover_m > 0")
    floor_worst = 0.0
    n_keys = rig.clips['keys']
    stride = 1 if keys == 'all' else max(1, int(keys))
    seam_ctx = connectivity_fn.prepare(doc, binary, ctx, rig, tol_m) if connectivity_fn else None
    if seam_ctx is not None and seam_ctx.get('error'):
        rep.error('connectivity', 'mesh.connectivity.floating', seam_ctx['error'])
    conn_worst = (0.0, None)
    n_posed = 0
    per = {}         # per clip: edge ratio range, keys with an edge out, floor deviation (lane WAIVER; see validate_character)
    for clip in clips:
        pc = per.setdefault(clip, {'lo': 1.0, 'hi': 1.0, 'keys_out': 0, 'floor_dev': 0.0, 'floor_keys': 0})
        for k in range(0, n_keys, stride):
            pos_all = lbs.posed(doc, binary, clip, k, prims)
            pos = [p for p, r in zip(pos_all, prims) if r['joints'] is not None]
            n_posed += 1
            key_lo, key_hi = 1.0, 1.0
            for p, e, l0, ok in zip(pos, edges, rest_len, valid):
                l1 = np.linalg.norm(p[e[:, 0]] - p[e[:, 1]], axis=1)
                ratio = l1[ok] / l0[ok]
                if len(ratio):
                    key_lo, key_hi = min(key_lo, float(ratio.min())), max(key_hi, float(ratio.max()))
                    if ratio.min() < lo:
                        lo = float(ratio.min()); worst_at = '%s@%d' % (clip, k) if lo < EDGE_LIMITS[0] else worst_at
                    if ratio.max() > hi:
                        hi = float(ratio.max()); worst_at = '%s@%d' % (clip, k) if hi > EDGE_LIMITS[1] else worst_at
            pc['lo'], pc['hi'] = min(pc['lo'], key_lo), max(pc['hi'], key_hi)
            if key_lo < EDGE_LIMITS[0] or key_hi > EDGE_LIMITS[1]:
                pc['keys_out'] += 1
            if not all(np.isfinite(p).all() for p in pos):
                rep.error('deformation', 'data.nan', 'non-finite skinned position at %s@%d' % (clip, k))
                continue
            allp = np.concatenate([p[r['used']] for p, r in zip(pos, body)])        # rendered vertices only
            ymin = float(allp[:, 1].min())
            if profile == 'hover':
                dev = max(0., hover - floor_tol - ymin)
            elif clip in seats:
                dev = max(0., -ymin)
            elif floor_mode == 'touch' and k in flight.get(clip, ()) and ymin > 0.:
                dev = max(0., ymin - FLIGHT_MAX_FRACTION * H)
            elif floor_mode == 'touch':
                dev = abs(ymin)
            else:
                dev = max(0., -ymin)
            floor_worst = max(floor_worst, dev)
            pc['floor_dev'] = max(pc['floor_dev'], dev)
            if dev > floor_tol:
                pc['floor_keys'] += 1
                rep.error('silhouette', 'mesh.silhouette.floor', '%s@%d lowest vertex at %.4f m' % (clip, k, ymin))
            ext = float(allp[:, 1].max() - ymin)
            if ext > blow * H:
                rep.error('silhouette', 'mesh.silhouette.blowup', '%s@%d posed height %.3f > %.1f x rest' % (clip, k, ext, blow))
            if seam_ctx is not None and not seam_ctx.get('error'):
                g, where = connectivity_fn.gaps(seam_ctx, pos_all)
                if g > conn_worst[0]:
                    conn_worst = (g, '%s %s@%d' % (where, clip, k))
                if g > tol_m:
                    rep.error('connectivity', 'mesh.connectivity', '%s gap %.4f m > %.4f at %s@%d' % (where, g, tol_m, clip, k))
    if lo < EDGE_LIMITS[0] or hi > EDGE_LIMITS[1]:
        rep.error('deformation', 'mesh.deformation', 'edge ratio %.3f..%.3f outside %s (worst %s)' % (lo, hi, EDGE_LIMITS, worst_at))
    rep.check('deformation', edge_ratio_min=round(lo, 4), edge_ratio_max=round(hi, 4), limits=list(EDGE_LIMITS), keys_posed=n_posed)
    rep.check('silhouette', floor_dev_max_m=round(floor_worst, 6), floor_mode=('hover' if profile == 'hover' else floor_mode))
    if flight or seats:
        rep.check('silhouette', declared_flight={c: sorted(v) for c, v in flight.items()},
                  declared_seats=dict(sorted(seats.items())), flight_max_m=round(FLIGHT_MAX_FRACTION * H, 4))
    if seam_ctx is not None:
        rep.check('connectivity', method=seam_ctx.get('method'), joins=seam_ctx.get('n_joins'), max_gap_m=round(conn_worst[0], 6),
                  max_at=conn_worst[1], tol_m=tol_m)
    return per


def validate_character(glb, rig='human16_v1', *, clips=None, budget=None, expect_sha256=None, profile='grounded',
                       keys='all', tol_m=0.003, combat=None, connectivity=True, waiver=False, per_clip=False):
    """Validate a character GLB against a rig contract (see module docstring).

    waiver    lane WAIVER (rigkit/waiver.py, docs/WAIVER.md). A file may carry an owner waiver block (root extras
              hermes64_waiver). False (default): the block is reported under report['waiver'] and ignored. True: the
              caller grants it, and the failures it covers move from report['errors'] to report['waived'] with their
              numbers. Files without a block give the same report either way.
    per_clip  also report per-clip numbers (checks.deformation.per_clip, checks.silhouette.per_clip). They are always
              reported when the file carries a waiver block."""
    if profile not in PROFILES:
        raise ValueError('profile must be one of %s, not %r' % (PROFILES, profile))
    raw = _raw(glb)
    if isinstance(rig, str) and rig == 'auto':
        from .clips import detect_rig
        try:
            rig = detect_rig(raw)
        except ValueError:
            rig = 'human16_v1'
    rig = load_rig(rig)
    sha = hashlib.sha256(raw).hexdigest()
    rep = Report(rig, sha)
    if expect_sha256 is not None and expect_sha256 != sha:
        rep.error('hash', 'hash.mismatch', 'sha256 %s != expected %s' % (sha, expect_sha256))
    rep.check('hash', sha256=sha, expected=expect_sha256)
    try:
        doc, binary = gltf.parse(raw)
    except Exception as e:     # noqa: BLE001 - any parse failure is a container rejection
        rep.error('container', 'container.parse', str(e))
        return rep.d
    per = _checks(rep, rig, raw, doc, binary, clips, budget, profile, keys, tol_m, combat, connectivity)
    from . import waiver as W
    block = W.read(doc)
    if per is not None and (per_clip or block is not None):
        rep.check('deformation', per_clip={c: {'edge_ratio': [round(n['lo'], 4), round(n['hi'], 4)], 'keys_out': n['keys_out']}
                                           for c, n in per.items()})
        rep.check('silhouette', per_clip={c: {'floor_dev_m': round(n['floor_dev'], 6), 'floor_keys': n['floor_keys']}
                                          for c, n in per.items()})
    if block is not None:
        W.apply(rep, block, doc, binary, per, waiver)
    return rep.d


def _checks(rep, rig, raw, doc, binary, clips, budget, profile, keys, tol_m, combat, connectivity):
    """Every check of validate_character after the parse; -> per-clip numbers, or None when it stopped early."""
    _container(rep, raw)
    _finite(rep, doc, binary)
    if not rep.d['checks']['finite']['ok']:
        return None
    ctx = _rig(rep, rig, doc, binary, profile)
    if ctx is None:
        return None
    _skin(rep, rig, doc, binary, ctx)
    if combat is None:
        names = {a.get('name') for a in doc.get('animations', [])}
        combat = bool(set(rig.clips.get('combat', [])) & names)
    decl = declarations(doc)
    checked = _clips(rep, rig, doc, binary, ctx, clips, combat, profile, decl)
    _budget(rep, rig, doc, budget)
    if not rep.d['checks']['skin']['ok'] or any(e['code'] in ('rig.ibm_missing',) for e in rep.d['errors']):
        return None
    from . import seams
    per = _posed_checks(rep, rig, doc, binary, ctx, checked, keys, profile, tol_m, seams if connectivity else None, decl)
    rep.d['metrics'] = {'clips_checked': len(checked), 'keys_per_clip': rig.clips['keys'] if keys == 'all' else 'stride %s' % keys}
    return per


def validate_prop(glb, rig='human16_v1', *, slot=None, budget=None, expect_sha256=None):
    """Rigid prop / weapon check against a rig's prop rules: container, finite, unskinned and unanimated, every mesh
    within rig props.tris_le (200), and (slot given, e.g. 'hand_r') the rig has that socket bone."""
    raw = _raw(glb)
    rig = load_rig(rig)
    sha = hashlib.sha256(raw).hexdigest()
    rep = Report(rig, sha)
    rep.d['kind'] = 'prop'
    if expect_sha256 is not None and expect_sha256 != sha:
        rep.error('hash', 'hash.mismatch', 'sha256 %s != expected %s' % (sha, expect_sha256))
    rep.check('hash', sha256=sha, expected=expect_sha256)
    try:
        doc, binary = gltf.parse(raw)
    except Exception as e:     # noqa: BLE001
        rep.error('container', 'container.parse', str(e))
        return rep.d
    from .. import glb_validate
    r = glb_validate.validate(raw, 'prop')
    errs = [i for i in r.issues if i['severity'] == 'error']
    for i in errs:
        rep.error('container', i['code'], i['message'], i.get('path', ''))
    rep.check('container', issues=len(r.issues), errors=len(errs))
    _finite(rep, doc, binary)
    if doc.get('skins') or doc.get('animations'):
        rep.error('prop', 'prop.not_rigid', 'a prop must be unskinned and unanimated (it rides its socket bone)')
    limit = (budget or {}).get('prop_tris_le', (rig.doc.get('props') or {}).get('tris_le', rig.budgets.get('prop_tris_le', 200)))
    tris = {}
    for i, n in enumerate(doc.get('nodes', [])):
        if 'mesh' in n:
            t = sum(doc['accessors'][p['indices']]['count'] // 3 for p in doc['meshes'][n['mesh']]['primitives'] if 'indices' in p)
            tris[n.get('name', 'node%d' % i)] = t
            if t > limit:
                rep.error('budget', 'budget.prop', 'prop %s %d tris > %d' % (n.get('name'), t, limit))
    if not tris:
        rep.error('prop', 'prop.no_mesh', 'no mesh node')
    rep.check('budget', prop_tris=tris, prop_tris_le=limit)
    sock = None
    if slot is not None:
        bones = {s['name'][len('attach_'):]: s['bone'] for s in rig.sockets if s['name'].startswith('attach_')}
        sock = bones.get(slot, slot if slot in rig.bones else None)
        if sock is None:
            rep.error('prop', 'prop.slot', 'rig %s has no socket %s' % (rig.id, slot))
    weapon = (rig.doc.get('props') or {}).get('weapon') or {}
    rep.check('prop', slot=slot, socket_bone=sock, weapon_rule=weapon or None)
    return rep.d
