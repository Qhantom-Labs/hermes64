"""Clip packs (rigs/<rig_id>/clips.glb + clips.json) and attach_clips(): copy a rig's clip pack into any GLB that
is skinned to that rig.

A clip pack is the rig's skeleton at the reference rest pose plus every clip of the rig as a glTF animation (STEP,
16 keys at k/15 s), with no mesh. Because every rig-kit skeleton has identity rest rotations and translation-only
offsets, a clip's joint rotations mean the same thing on any body proportions: attach_clips copies them verbatim
(float32 bytes) and recomputes only the grounding translation per key with the numpy LBS reference.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from . import gltf, gltfedit, lbs
from .rig import RigError, load_rig

PACK_SCHEMA = 'hermes64-rig-clips/1.0.0'
GROUND_MODES = ('match', 'hover')


def detect_rig(raw):
    """Rig id from a character GLB: the skin name rig_<id> or the armature node extras 'skeleton'."""
    doc, _ = gltf.parse(raw)
    for sk in doc.get('skins', []):
        nm = sk.get('name', '')
        if nm.startswith('rig_'):
            return nm[4:]
    for n in doc.get('nodes', []):
        ex = n.get('extras') or {}
        if isinstance(ex, dict) and ex.get('skeleton'):
            return ex['skeleton']
    raise ValueError('cannot detect the rig of this GLB (no rig_<id> skin, no skeleton extras)')


def _raw(glb):
    if isinstance(glb, (bytes, bytearray, memoryview)):
        return bytes(glb)
    return Path(glb).read_bytes()


def pack_paths(rig):
    rig = load_rig(rig)
    base = Path(rig.path).parent if rig.path else None
    if base is None:
        raise RigError('rig %s has no directory (load it from rigs/<id>/rig.json)' % rig.id)
    return base / 'clips.glb', base / 'clips.json'


def load_pack(rig):
    """-> (doc, binary, meta) of the rig's clip pack; meta['clips'] in pack order. Raises RigError if missing or
    if clips.glb does not match the sha256 recorded in clips.json."""
    rig = load_rig(rig)
    g, j = pack_paths(rig)
    if not g.is_file() or not j.is_file():
        raise RigError('rig %s has no clip pack (%s, %s)' % (rig.id, g.name, j.name))
    raw = g.read_bytes()
    meta = json.loads(j.read_text(encoding='utf-8'))
    if meta.get('schema') != PACK_SCHEMA or meta.get('rig') != rig.id:
        raise RigError('%s is not a %s clip pack for %s' % (j, PACK_SCHEMA, rig.id))
    sha = hashlib.sha256(raw).hexdigest()
    want = meta.get('files', {}).get('clips.glb', {}).get('sha256')
    if want != sha:
        raise RigError('clips.glb sha256 %s does not match clips.json (%s)' % (sha[:12], str(want)[:12]))
    doc, binary = gltf.parse(raw)
    return doc, binary, meta


def _pack_channels(doc, binary, name):
    an = [a for a in doc.get('animations', []) if a.get('name') == name]
    if not an:
        raise RigError('clip %s not in the pack' % name)
    an = an[0]
    out = []
    times = None
    for ch in an['channels']:
        smp = an['samplers'][ch['sampler']]
        bone = doc['nodes'][ch['target']['node']]['name']
        t = gltf.read_accessor(doc, binary, smp['input'])[:, 0].astype(np.float32)
        times = t if times is None else times
        vals = gltf.read_accessor(doc, binary, smp['output']).astype(np.float32)
        out.append((bone, ch['target']['path'], vals))
    if times is None:
        raise RigError('clip %s has no channels in the pack' % name)
    return out, times, an.get('extras')


def _hover_m(doc, rig):
    for n in doc.get('nodes', []):
        if n.get('name') == 'rig_' + rig.id and isinstance(n.get('extras'), dict) and 'hover_m' in n['extras']:
            return float(n['extras']['hover_m'])
    for n in doc.get('nodes', []):
        if isinstance(n.get('extras'), dict) and 'hover_m' in n['extras']:
            return float(n['extras']['hover_m'])
    return None


EDGE_LIMITS = (0.45, 1.8)      # the validator's deformation limits (validate.EDGE_LIMITS)
GUARD_MARGIN = 0.0      # guard only keys the validator would reject
GUARD_STEPS = (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0)


def _body_edges(prims):
    from .validate import _edges
    out = []
    for r in prims:
        if r['joints'] is None:
            continue
        e = _edges(r)
        l0 = np.linalg.norm(r['positions'][e[:, 0]] - r['positions'][e[:, 1]], axis=1)
        ok = l0 > 1e-9
        out.append((r, e[ok], l0[ok]))
    return out


def _skin_mats(doc, binary, ov):
    world = lbs.world_matrices(doc, ov)
    sk = doc['skins'][0]
    ibm = lbs.inverse_binds(doc, binary, 0)
    if ibm is None:
        ibm = np.repeat(np.eye(4)[None], len(sk['joints']), axis=0)
    return np.stack([world[j] for j in sk['joints']]) @ ibm, world


def _worst_edge(body_edges, mats, lo, hi, only=None):
    """-> (violation amount, (prim row, edge)) of the edge farthest outside [lo, hi], or (0, None).
    only: joint indices; restrict to edges with a vertex weighted to one of them."""
    worst = (0.0, None)
    for r, e, l0 in body_edges:
        if only is not None:
            hit = ((np.isin(r['joints'], only)) & (r['weights'] > 0)).any(axis=1)
            sel = hit[e[:, 0]] | hit[e[:, 1]]
            if not sel.any():
                continue
            e, l0 = e[sel], l0[sel]
        p = lbs.skin(r['positions'], r['joints'], r['weights'], mats)
        ratio = np.linalg.norm(p[e[:, 0]] - p[e[:, 1]], axis=1) / l0
        i, j = int(np.argmin(ratio)), int(np.argmax(ratio))
        if lo - ratio[i] > worst[0]:
            worst = (float(lo - ratio[i]), (r, e[i]))
        if ratio[j] - hi > worst[0]:
            worst = (float(ratio[j] - hi), (r, e[j]))
    return worst


def _soften(q, s):
    """slerp(identity, q, s) for xyzw quaternions, w >= 0."""
    q = np.asarray(q, np.float64)
    if q[3] < 0:
        q = -q
    ang = 2 * np.arccos(min(1.0, q[3]))
    if ang < 1e-9:
        return q
    axis = q[:3] / np.linalg.norm(q[:3])
    a = ang * s / 2
    return np.concatenate([axis * np.sin(a), [np.cos(a)]])


def _culprits(rig, names, r, edge):
    """Joints to soften for a bad edge: the deepest joints influencing its two vertices (never the root)."""
    js = set()
    for v in edge:
        for j, w in zip(r['joints'][v], r['weights'][v]):
            if w > 0:
                js.add(names[j])

    def ancestors(b):
        out = set()
        p = rig.parents[b]
        while p is not None:
            out.add(p)
            p = rig.parents[p]
        return out
    deep = sorted(b for b in js if not any(b in ancestors(o) for o in js if o != b))
    return [b for b in deep if rig.parents[b] is not None]


def attach_clips(glb, rig='human16_v1', *, clips=None, mode='copy', replace=True, ground='match', guard=True):
    """-> bytes: the input GLB with the rig's clip pack written in (deterministic: same input, same bytes).

    clips    None = every clip of the pack; or a list of clip names.
    mode     'copy' (the only rig-kit mode): joint rotations copied verbatim (float32 bytes).
    replace  True = drop every existing animation first; False = keep existing animations whose names are not
             being attached.
    ground   'match' = per key, the root/body translation is set so the character's lowest skinned vertex has the
             same floor clearance as the pack's pose-source body at that key (0 for grounded clips);
             'hover' = like match, plus the hover height (rig node extras hover_m).
    guard    True = deformation guard: on a key where this character's skinning would stretch or collapse an edge
             outside the validator limits (0.45..1.8), the deepest joint(s) of the worst edge
             are rotated less (slerp toward rest in 0.1 steps) until the key is inside the limits. Only failing
             keys of failing characters change; each change is listed in the animation extras 'rigkit_guard'.
             False = verbatim copy (the validator then reports any collapse).
    Every animation carries extras 'rigkit_pack' = '<rig>@<version>:<clips.glb sha256[:16]>'.
    """
    if mode != 'copy':
        raise ValueError("rigkit.attach_clips supports mode='copy' only (generator bodies: nbchars per-body IK)")
    if ground not in GROUND_MODES:
        raise ValueError('ground must be one of %s' % (GROUND_MODES,))
    raw = _raw(glb)
    if isinstance(rig, str) and rig == 'auto':
        rig = detect_rig(raw)
    rig = load_rig(rig)
    doc, binary = gltf.parse(raw)
    skins = doc.get('skins', [])
    if len(skins) != 1:
        raise RigError('attach_clips needs exactly one skin (found %d); run validate_character first' % len(skins))
    names = [doc['nodes'][j].get('name') for j in skins[0]['joints']]
    if names != list(rig.bones):
        raise RigError('skin joints %s are not the %s joint order; run validate_character first' % (names, rig.id))
    pdoc, pbin, meta = load_pack(rig)
    tag = '%s:%s' % (rig.tag, meta['files']['clips.glb']['sha256'][:16])
    available = [c['name'] for c in meta['clips']]
    want = list(available) if clips is None else list(clips)
    missing = [c for c in want if c not in available]
    if missing:
        raise RigError('clips %s are not in the %s pack (has %s)' % (missing, rig.id, available))
    clip_meta = {c['name']: c for c in meta['clips']}
    hover = 0.0
    if ground == 'hover':
        h = _hover_m(doc, rig)
        if h is None:
            raise RigError("ground='hover' needs rig node extras hover_m")
        hover = h
    # strip the animations being replaced, garbage-collect their data
    keep = [] if replace else [a for a in doc.get('animations', []) if a.get('name') not in want]
    doc = dict(doc)
    if keep:
        doc['animations'] = keep
    else:
        doc.pop('animations', None)
    doc, binary = gltfedit.compact(doc, binary)
    keep = list(doc.get('animations', []))
    node_of = {doc['nodes'][j]['name']: j for j in doc['skins'][0]['joints']}
    prims = lbs.primitives(doc, binary)
    if not any(r['joints'] is not None for r in prims):
        raise RigError('no skinned primitive (kit_body) to animate')
    body_edges = _body_edges(prims) if guard else None
    parents = gltf.node_parents(doc)
    lo, hi = EDGE_LIMITS[0] + GUARD_MARGIN, EDGE_LIMITS[1] - GUARD_MARGIN
    b = gltfedit.Builder(doc, binary)
    new = []
    times_acc = {}
    for name in sorted(want):
        chans, times, extras = _pack_channels(pdoc, pbin, name)
        nkeys = len(times)
        rot = {bone: v.astype(np.float32).copy() for bone, path, v in chans if path == 'rotation'}
        trs = [bone for bone, path, v in chans if path == 'translation']
        rest_t = {bn: np.array(doc['nodes'][node_of[bn]].get('translation', [0., 0., 0.]), dtype=np.float64)
                  for bn in trs}
        tvals = {bn: np.repeat(rest_t[bn][None, :], nkeys, axis=0) for bn in trs}
        clear = clip_meta[name].get('floor_clearance_m') or [0.0] * nkeys
        guarded = []

        def overrides(k):
            ov = {node_of[bn]: {'rotation': q[k].astype(np.float64)} for bn, q in rot.items()}
            for bn in trs:
                ov.setdefault(node_of[bn], {})['translation'] = rest_t[bn]
            return ov
        for k in range(nkeys):
            if guard:
                done = set()
                for _round in range(8):
                    mats, _ = _skin_mats(doc, binary, overrides(k))
                    amount, where = _worst_edge(body_edges, mats, lo, hi)
                    if where is None:
                        break
                    culprits = [c for c in _culprits(rig, names, where[0], where[1]) if c in rot and c not in done]
                    if not culprits:
                        break
                    only = [names.index(c) for c in culprits]
                    orig = {c: rot[c][k].copy() for c in culprits}
                    chosen = None
                    for sc in GUARD_STEPS:              # largest share of the rotation that keeps these edges inside
                        for c in culprits:
                            rot[c][k] = _soften(orig[c], sc).astype(np.float32)
                        m2, _ = _skin_mats(doc, binary, overrides(k))
                        if _worst_edge(body_edges, m2, lo, hi, only)[1] is None:
                            chosen = sc
                            break
                    if chosen is None:                  # cannot be fixed by these joints: restore, let the validator report
                        for c in culprits:
                            rot[c][k] = orig[c]
                    done.update(culprits)
                    guarded.append([k, culprits, chosen])
            mats, world = _skin_mats(doc, binary, overrides(k))
            ys = [lbs.skin(r['positions'], r['joints'], r['weights'], mats)[r['used'], 1].min()
                  for r in prims if r['joints'] is not None and r['used'].any()]
            ymin = float(min(ys))
            for bn in trs:
                p = parents.get(node_of[bn])
                up = 1.0 if p is None else float(world[p][1, 1])
                if abs(up) < 1e-6:
                    raise RigError('the parent of %s is rotated sideways: cannot ground' % bn)
                tvals[bn][k, 1] = rest_t[bn][1] + (float(clear[k]) + hover - ymin) / up
                break                                # one grounding joint per rig (rig.json channels)
        key = times.astype(np.float32).tobytes()
        if key not in times_acc:
            times_acc[key] = b.accessor(times.astype(np.float32), 5126, 'SCALAR', minmax=True)
        channels, samplers = [], []
        for bone, path, v in chans:
            if bone not in node_of:
                raise RigError('pack joint %s missing in the character' % bone)
            vals = rot[bone] if path == 'rotation' else tvals[bone].astype(np.float32)
            out_acc = b.accessor(vals, 5126, 'VEC4' if path == 'rotation' else 'VEC3')
            samplers.append({'input': times_acc[key], 'interpolation': 'STEP', 'output': out_acc})
            channels.append({'sampler': len(samplers) - 1, 'target': {'node': node_of[bone], 'path': path}})
        ex = dict(extras or {})
        ex['rigkit_pack'] = tag
        if guarded:
            ex['rigkit_guard'] = guarded
        new.append({'channels': channels, 'extras': ex, 'name': name, 'samplers': samplers})
    anims = sorted(keep + new, key=lambda a: a.get('name', ''))
    b.doc['animations'] = anims
    return b.finish()
