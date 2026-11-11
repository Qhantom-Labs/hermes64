"""Build the committed rig-kit files: rigs/<rig_id>/clips.glb + clips.json (every rig) and mannequin.glb (human16_v1,
quad16_v1). Dev-time tool: the clip data comes from the vendored generator through the Blender-free exporter
(adventure_maker.nbchars, parity-proven against the Blender-published cast). Runtime users only read the files.

    python3 -m adventure_maker.rigkit build-kits [--out DIR]
"""
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np

from . import clips as CL
from . import gltf, gltfedit, lbs, mannequin
from .rig import RIGS as RIGS_DIR, load_rig

KIT_RIGS = ('human16_v1', 'quad16_v1', 'dasher16_v1', 'warden15_v1')
MANNEQUIN_RIGS = ('human16_v1', 'quad16_v1')
ENEMY_OF = {'dasher16_v1': 'cairn_dasher', 'warden15_v1': 'reed_warden'}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def reference(rig_id, G=None, human_values=None):
    """-> (GLB bytes, clip table) of the rig's reference body with every clip of the rig, built without Blender."""
    from ..nbchars import api, gen
    from ..nbchars import assemble as A
    from ..nbchars import writer as W
    G = G or gen.load()
    PO = G.core('pose')
    table = {}
    if rig_id == 'human16_v1':
        CMB = G.core('combat')
        if human_values is None:
            from .derive import reference_values
            rb = load_rig('human16_v1').doc.get('reference_body', {})
            vals = reference_values(G, {'pack': rb.get('pack', 'polar_pod'), 'cast_id': rb.get('cast_id', 'pp_medic')})
        else:
            vals = dict(human_values)
        sc = A.character('polar_pod', vals, False, seed=19, stance=None, props=[], clips=PO.HCLIPS + CMB.COMBAT_CLIPS, G=G)
        ex = api.combat_extras(G)
        sc = dataclasses.replace(sc, clips=[dataclasses.replace(c, extras=ex.get(c.name)) for c in sc.clips])
        for c in PO.HCLIPS:
            table[c] = {'group': 'base'}
        for c in CMB.COMBAT_CLIPS:
            ph = dict(CMB.PHASES[c])
            table[c] = {'group': 'combat', 'loop': ph.pop('loop'), 'loop_source': 'core/combat.PHASES', 'phases': ph.pop('phases'),
                        **ph}
    elif rig_id == 'quad16_v1':
        sc = A.character('polar_pod', {}, True, seed=19, G=G)
        for c in PO.ACLIPS:
            table[c] = {'group': 'animal', 'face_cell': 1 if c == 'sleep_curled' else 0}
    else:
        eid = ENEMY_OF[rig_id]
        sc = A.enemy('polar_pod', eid, G=G)
        EPO = G.core('enemy_pose')
        phases = EPO.PHASES[eid]
        fsm = {}
        for st, c in EPO.FSM_CLIP.items():
            fsm.setdefault(c, []).append(st)
        for c in [x.name for x in sc.clips]:
            ph = dict(phases.get(c, {}))
            row = {'group': 'enemy', 'fsm_states': sorted(fsm.get(c, [])),
                   'face_cell': EPO.FACE_CELLS['clip_cells'].get(c, EPO.FACE_CELLS['cell'])}
            if ph:
                row.update(loop=ph.pop('loop'), loop_source='core/enemy_pose.PHASES', phases=ph.pop('phases'), **ph)
            table[c] = row
    return W.write_scene(sc), table, sc


def _floor_clearance(doc, binary, name, nkeys):
    prims = lbs.primitives(doc, binary)
    out = []
    for k in range(nkeys):
        pos = lbs.posed(doc, binary, name, k, prims)
        ys = [p[:, 1].min() for p, r in zip(pos, prims) if r['joints'] is not None]
        out.append(round(float(min(ys)), 6) + 0.0)
    return out


def clip_pack(rig_id, ref_raw, table):
    """Reference GLB -> (clips.glb bytes, clip rows): skeleton + animations only, no mesh."""
    rig = load_rig(rig_id)
    doc, binary = gltf.parse(ref_raw)
    rows = []
    for an in sorted(doc.get('animations', []), key=lambda a: a['name']):
        name = an['name']
        times = gltf.read_accessor(doc, binary, an['samplers'][0]['input'])[:, 0]
        nk = len(times)
        clear = _floor_clearance(doc, binary, name, nk)
        h = hashlib.sha256()
        loop = True
        offsets = {}
        for ch in an['channels']:
            smp = an['samplers'][ch['sampler']]
            v = gltf.read_accessor(doc, binary, smp['output'])
            h.update(gltf.accessor_bytes(doc, binary, smp['output']))
            if np.abs(v[-1].astype(np.float64) - v[0]).max() > 1e-6:
                loop = False
            if ch['target']['path'] == 'translation':
                node = doc['nodes'][ch['target']['node']]
                rest = np.array(node.get('translation', [0, 0, 0]), np.float64)
                offsets[node['name']] = [round(float(y), 6) + 0.0 for y in (v[:, 1].astype(np.float64) - rest[1])]
        row = {'name': name, 'keys': nk, 'floor_clearance_m': clear, 'vertical_offset_m': offsets,
               'key_sha256': h.hexdigest()}
        meta = dict(table.get(name, {}))
        if 'loop' not in meta:
            meta['loop'] = loop
            meta['loop_source'] = 'data: key 15 equals key 0 (1 s period)' if loop else 'data: key 15 differs from key 0'
        row.update(meta)
        rows.append(row)
    keep = set(doc['skins'][0]['joints'])
    rig_node = [i for i, n in enumerate(doc['nodes']) if n.get('name') == 'rig_' + rig_id]
    keep.update(rig_node)
    doc = gltfedit.remove_nodes(doc, [i for i in range(len(doc['nodes'])) if i not in keep])
    for k in ('meshes', 'materials', 'textures', 'images', 'samplers', 'extensionsUsed', 'extensionsRequired'):
        doc.pop(k, None)
    for n in doc['nodes']:
        if n.get('name') == 'rig_' + rig_id:
            n['extras'] = {'skeleton': rig_id, 'rig': rig.tag, 'clip_pack': True}
    doc['asset'] = {'generator': 'adventure-maker rigkit clip pack', 'version': '2.0'}
    doc, binary = gltfedit.compact(doc, binary)
    return gltf.encode(doc, binary, fix=True), rows


def build_kits(out=None, rigs=KIT_RIGS, log=print, human_values=None):
    from .validate import validate_character
    G = None
    try:
        from ..nbchars import gen
        G = gen.load()
    except Exception as e:   # noqa: BLE001
        raise RuntimeError('build-kits needs the vendored generator (characters/gen): %s' % e)
    report = {}
    for rid in rigs:
        rig = load_rig(rid)
        d = Path(out) / rid if out else Path(RIGS_DIR) / rid
        d.mkdir(parents=True, exist_ok=True)
        if out:                                  # a complete kit directory: the rig contract travels with its pack
            (d / 'rig.json').write_bytes((Path(rig.path)).read_bytes())
            rig = load_rig(str(d / 'rig.json'))
        ref, table, sc = reference(rid, G, human_values if rid == 'human16_v1' else None)
        pack, rows = clip_pack(rid, ref, table)
        meta = {'schema': CL.PACK_SCHEMA, 'rig': rid, 'rig_version': rig.version,
                'fps': rig.clips['fps'], 'keys': rig.clips['keys'], 'duration_s': rig.clips.get('duration_s', 1.0),
                'interpolation': 'STEP', 'key_time': rig.clips.get('key_time'),
                'channels': rig.clips.get('channels'), 'root_motion': rig.clips.get('root_motion'),
                'reference_body': dict(rig.doc.get('reference_body', {}), stance='neutral', props=[],
                                       reference_glb_sha256=_sha(ref)),
                'source': 'vendored generator (characters/gen) through adventure_maker.nbchars: the same per-key data '
                          'the Blender exporter writes for this body (docs/NBCHARS-RESULT.md parity)',
                'attach': "rigkit.attach_clips(glb, '%s'): rotations copied verbatim; the %s translation regrounded "
                          "per key so the lowest vertex keeps floor_clearance_m" % (rid, '/'.join(rig.translation_bones())),
                'files': {'clips.glb': {'sha256': _sha(pack), 'bytes': len(pack)}},
                'clips': rows}
        if rid in ENEMY_OF:
            meta['fsm_clip'] = G.core('enemy_pose').FSM_CLIP
            meta['face_atlas'] = {k: v for k, v in G.core('enemy_pose').FACE_CELLS.items() if k != 'cells'}
        if rid == 'quad16_v1':
            meta['face_atlas'] = {'cols': 2, 'rows': 1, 'cell': 0, 'clip_cells': {'sleep_curled': 1}}
        if rid == 'human16_v1':
            meta['combat_rules'] = {
                'blend': 'clips are STEP; do not crossfade into swing keys 6-8',
                'hand_props': 'hide kit_acc_hand_l_* / kit_acc_hand_r_* while a combat clip plays',
                'weapon': 'trail_staff on hand_r (rig.json props.weapon)'}
        (d / 'clips.glb').write_bytes(pack)
        rep = {'clips': [r['name'] for r in rows], 'clips_glb_sha256': _sha(pack), 'clips_glb_bytes': len(pack)}
        if rid in MANNEQUIN_RIGS:
            bare = mannequin.build(rid)
            (d / 'clips.json').write_bytes((json.dumps(meta, indent=1, sort_keys=True) + '\n').encode('utf-8'))
            full = CL.attach_clips(bare, rig)
            again = CL.attach_clips(bare, rig)
            v = validate_character(full, rig, clips=[r['name'] for r in rows])
            (d / 'mannequin.glb').write_bytes(full)
            meta['files']['mannequin.glb'] = {'sha256': _sha(full), 'bytes': len(full),
                                              'tris': int(json.loads(json.dumps(gltf.parse(full)[0]['nodes'][-1]['extras']))['tris']),
                                              'validate_ok': v['ok'], 'deterministic': full == again}
            rep.update(mannequin_ok=v['ok'], mannequin_errors=v['errors'][:6], deterministic=full == again,
                       connectivity=v['checks'].get('connectivity'), deformation=v['checks'].get('deformation'),
                       silhouette=v['checks'].get('silhouette'))
        (d / 'clips.json').write_bytes((json.dumps(meta, indent=1, sort_keys=True) + '\n').encode('utf-8'))
        report[rid] = rep
        log('KIT %-12s clips %2d pack %s%s' % (rid, len(rows), _sha(pack)[:12],
                                                '' if rid not in MANNEQUIN_RIGS else ' mannequin ok=%s' % rep['mannequin_ok']))
    return report
