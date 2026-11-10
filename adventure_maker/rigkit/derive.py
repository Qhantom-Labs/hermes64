"""Derive rigs/<rig_id>/rig.json from the vendored generator (reference bodies) and the Blender-published oracle
(proportion ranges, joint-limit envelopes, clip conventions). Deterministic; run once per contract revision:

    python3 -B -m adventure_maker.rigkit derive --oracle ../lane-combat-art/published [--out rigs]

Nothing here is needed at runtime: rig.json files are committed data.
"""
import json
import math
from pathlib import Path

import numpy as np

from . import gltf, lbs
from .rig import skin_order

REPO = Path(__file__).resolve().parents[2]
VERSION = '1.0.0'
HUMAN_CLIPS = ['idle', 'walk', 'run', 'interact', 'talk', 'carry', 'sit']
COMBAT_CLIPS = ['idle_combat', 'swing', 'hurt', 'death', 'roll', 'block']
ANIMAL_CLIPS = ['idle', 'walk', 'run', 'sit', 'loaf', 'sleep_curled', 'stretch']
ENEMY_CLIPS = ['idle', 'move', 'telegraph', 'attack', 'recover', 'hurt', 'death']


def _order(parents):
    out, seen = [], set()

    def visit(n):
        if n in seen:
            return
        if parents[n]:
            visit(parents[n])
        seen.add(n)
        out.append(n)
    for n in parents:
        visit(n)
    return out


def _gl(v):
    """generator (Blender Z-up) -> glTF (Y-up)."""
    return (float(v[0]), float(v[2]), -float(v[1]))


def _r6(x):
    return [round(float(c), 6) + 0.0 for c in x]


def _oracle_files(oracle, kind):
    root = Path(oracle)
    man = json.loads((root / 'manifest.json').read_text())
    rows = []
    if kind in ('human', 'quad'):
        for c in man['characters']:
            is_q = c.get('kind') == 'animal'
            if (kind == 'quad') == is_q:
                rows.append(root / c['file'])
    else:
        for e in man['enemies']:
            if e['id'] == kind:
                rows.append(root / e['file'])
    return rows


def _measure(files, bones, parents):
    """Per-bone segment length ranges (fraction of rest height) and joint rotation envelopes over every clip/key."""
    seg = {b: [] for b in bones if parents[b]}
    ang = {b: 0.0 for b in bones}
    heights = []
    for f in files:
        doc, binary = gltf.parse(Path(f).read_bytes())
        names = {n.get('name'): i for i, n in enumerate(doc['nodes'])}
        world = lbs.world_matrices(doc)
        prims = lbs.primitives(doc, binary)
        body = np.concatenate([r['positions'] for r in prims if r['joints'] is not None])
        h = float(body[:, 1].max() - body[:, 1].min())
        heights.append(h)
        for b in seg:
            d = world[names[b]][:3, 3] - world[names[parents[b]]][:3, 3]
            seg[b].append(float(np.linalg.norm(d)) / h)
        for an in doc.get('animations', []):
            for ch in an['channels']:
                if ch['target']['path'] != 'rotation':
                    continue
                nm = doc['nodes'][ch['target']['node']].get('name')
                if nm not in ang:
                    continue
                q = gltf.read_accessor(doc, binary, an['samplers'][ch['sampler']]['output']).astype(np.float64)
                w = np.clip(np.abs(q[:, 3]), 0, 1)
                ang[nm] = max(ang[nm], float(np.degrees(2 * np.arccos(w)).max()))
    return seg, ang, heights


def _limits(ang):
    out = {}
    for b, a in ang.items():
        out[b] = {'max_angle_deg': float(min(180, 5 * math.ceil((a + 10.) / 5.)))}
    return out


def _proportions(seg, heights):
    rng = {}
    for b, v in seg.items():
        lo, hi = min(v), max(v)
        rng[b] = [round(max(0.0, lo * 0.8 - 1e-3), 4), round(hi * 1.25 + 1e-3, 4)]
    return {'height_m': [round(min(heights) * 0.8, 3), round(max(heights) * 1.25, 3)],
            'segment_fraction_of_height': rng}


def _common(rig_id, kind, bones, parents, rest, files, measured):
    seg, ang, heights = measured
    pairs = []
    for b in bones:
        if b.endswith('_l') and b[:-2] + '_r' in bones:
            pairs.append([b, b[:-2] + '_r'])
    return {
        'schema': 'hermes64-rig/1.0.0', 'id': rig_id, 'version': VERSION, 'kind': kind,
        'conventions': {
            'units': 'metre', 'gltf_up': '+Y', 'gltf_forward': '+Z (the character faces +Z; Blender authoring: Z up, faces -Y)',
            'left_side': '+X (bones *_l sit on +X)', 'handedness': 'right-handed',
            'rest_rotation': 'identity on every joint; unit scale; translation-only offsets from the parent',
            'blender_authoring': 'every bone head at the joint, tail = head + (0, 0, 0.05), roll 0, export with +Y up, export_rest_position_armature',
            'armature_node': 'rig_' + rig_id, 'mesh_node': 'kit_body',
            'inverse_bind': 'IBM[i] = inverse(world rest matrix of joint i) = translation(-rest_world_position[i])',
        },
        'bones': [{'name': b, 'parent': parents[b], 'index': i, 'rest_translation': _r6(rest[b][0]),
                   'rest_world': _r6(rest[b][1])} for i, b in enumerate(bones)],
        'mirror_pairs': pairs,
        'skin': {'max_influences': 4, 'weights_sum_tolerance': 1e-3, 'joints_component': ['UNSIGNED_BYTE', 'UNSIGNED_SHORT'],
                 'weights_component': 'FLOAT', 'ibm_tolerance_m': 1e-5},
        'joint_limits': _limits(ang),
        'joint_limits_source': 'envelope of every key of every clip of %d Blender-published files + 10 deg, rounded up to 5 deg' % len(files),
        'proportions': _proportions(seg, heights),
        'proportions_source': 'Blender-published files: segment length / rest mesh height, range x0.8 .. x1.25',
    }


# The human reference body (reference rest skeleton, mannequin skeleton and the clip pack's pose source): the
# polar_pod face-head 'pp_medic'. Its per-body arm solutions are the most conservative of the cast (the generator's
# deformation-aware arm fallback on a face-head shoulder), so its clips copy onto every published humanoid
# (masked hood, face-head, visor) without a single key leaving the validator limits (docs/RIGKIT.md).
HUMAN_REFERENCE = {'pack': 'polar_pod', 'cast_id': 'pp_medic'}


def reference_values(G, ref=None):
    ref = ref or HUMAN_REFERENCE
    pk = G.pack(ref['pack'])
    for key in ('face_cast', 'character_cast'):
        for c in pk.get(key, []):
            if c['id'] == ref['cast_id']:
                return dict(c['params'])
    raise KeyError('reference %s not in pack %s' % (ref['cast_id'], ref['pack']))


def human(G, oracle):
    geometry = G.core('geometry')
    people = G.core('people')
    pk = G.pack(HUMAN_REFERENCE['pack'])
    p = dict(pk.get('face_defaults', {}))
    p.update(reference_values(G))
    a = people.person(p)
    parents = geometry.HUMAN_PARENTS
    bones = skin_order(parents)
    rest = {b: ((_gl(np.subtract(a.bones[b], a.bones[parents[b]])) if parents[b] else _gl(a.bones[b])), _gl(a.bones[b]))
            for b in bones}
    files = _oracle_files(oracle, 'human')
    doc = _common('human16_v1', 'humanoid', bones, parents, rest, files, _measure(files, bones, parents))
    doc['reference_body'] = {'generator': "core/people.person(packs/polar_pod face_defaults + face_cast 'pp_medic' params)",
                             'pack': HUMAN_REFERENCE['pack'], 'cast_id': HUMAN_REFERENCE['cast_id'],
                             'height_m': a.params['height'], 'topology': getattr(a, 'topology', 'human16_face'),
                             'role': 'reference rest skeleton, mannequin skeleton and clip-pack pose source'}
    doc['clips'] = {'required': HUMAN_CLIPS, 'combat': COMBAT_CLIPS, 'fps': 15, 'keys': 16, 'duration_s': 1.0,
                    'interpolation': 'STEP', 'key_time': 'key k at t = k / 15 s',
                    'channels': {'rotation': 'every joint (root included)', 'translation': ['root']},
                    'root_motion': 'root translation = vertical grounding only (x = z = 0); the runtime moves actors',
                    'combat_required_for': 'combatants (the 16 published cast humanoids); optional otherwise'}
    doc['sockets'] = [{'name': 'attach_' + s, 'bone': b} for s, b in
                      [('hand_l', 'hand_l'), ('hand_r', 'hand_r'), ('head', 'head'), ('back', 'spine'), ('belt', 'pelvis')]]
    doc['props'] = {'node_pattern': 'kit_acc_<slot>_<kind>', 'parent': 'the socket bone', 'tris_le': 200,
                    'weapon': {'id': 'trail_staff', 'bone': 'hand_r', 'rotation_xyzw': [0.8660254, 0.0, 0.0, 0.5],
                               'translation': 'per character: manifest characters[].combat.weapon_grip.translation'}}
    doc['budgets'] = {'body_tris_lt': 700, 'prop_tris_le': 200}
    doc['seams'] = [{'name': 'neck', 'parent': 'spine', 'child': 'head'},
                    {'name': 'shoulder_l', 'parent': 'spine', 'child': 'upper_arm_l'},
                    {'name': 'shoulder_r', 'parent': 'spine', 'child': 'upper_arm_r'},
                    {'name': 'hip_l', 'parent': 'pelvis', 'child': 'thigh_l'},
                    {'name': 'hip_r', 'parent': 'pelvis', 'child': 'thigh_r'},
                    {'name': 'wrist_l', 'parent': 'forearm_l', 'child': 'hand_l'},
                    {'name': 'wrist_r', 'parent': 'forearm_r', 'child': 'hand_r'},
                    {'name': 'ankle_l', 'parent': 'shin_l', 'child': 'foot_l'},
                    {'name': 'ankle_r', 'parent': 'shin_r', 'child': 'foot_r'}]
    doc['hover'] = {'mapping': 'floater robots use this rig: shell -> pelvis+spine, dome -> head, arm pods -> arm chains, '
                               'emitter/skirt -> pelvis; leg joints present with zero weight',
                    'profile': "validate_character(profile='hover'); lowest vertex >= rig node extras hover_m - 2 mm",
                    'optional_clips': ['sit']}
    doc['silhouette'] = {'rest_height_m': doc['proportions']['height_m'], 'floor': 'touch', 'floor_tolerance_m': 0.002,
                         'blowup_height_factor': 1.6, 'max_vertex_departure_m': 0.5}
    return doc


def quad(G, oracle):
    geometry = G.core('geometry')
    pk = G.pack('polar_pod')
    p = dict(pk['animal_defaults'])
    a = geometry.quadruped(p)
    parents = geometry.QUAD_PARENTS
    bones = skin_order(parents)
    rest = {b: ((_gl(np.subtract(a.bones[b], a.bones[parents[b]])) if parents[b] else _gl(a.bones[b])), _gl(a.bones[b]))
            for b in bones}
    files = _oracle_files(oracle, 'quad')
    doc = _common('quad16_v1', 'quadruped', bones, parents, rest, files, _measure(files, bones, parents))
    doc['reference_body'] = {'generator': 'core/geometry.quadruped(packs/polar_pod animal_defaults)', 'species': a.params['species'],
                             'topology': 'quad16_v1'}
    doc['clips'] = {'required': ANIMAL_CLIPS, 'fps': 15, 'keys': 16, 'duration_s': 1.0, 'interpolation': 'STEP',
                    'key_time': 'key k at t = k / 15 s',
                    'channels': {'rotation': 'every joint (root included)', 'translation': ['root']},
                    'root_motion': 'root translation = vertical grounding only (x = z = 0)',
                    'face_cells': {'sleep_curled': 1, 'default': 0}}
    doc['sockets'] = []
    doc['budgets'] = {'body_tris_le': 300, 'prop_tris_le': 200}
    doc['seams'] = [{'name': 'neck_body', 'parent': 'chest', 'child': 'neck'}, {'name': 'neck_head', 'parent': 'neck', 'child': 'head'},
                    {'name': 'tail', 'parent': 'hips', 'child': 'tail_1'}] + \
                   [{'name': 'leg_' + e, 'parent': 'chest' if e[0] == 'f' else 'hips', 'child': 'leg_' + e} for e in ('fl', 'fr', 'bl', 'br')]
    doc['silhouette'] = {'rest_height_m': doc['proportions']['height_m'], 'floor': 'touch', 'floor_tolerance_m': 0.002,
                         'blowup_height_factor': 1.6, 'max_vertex_departure_m': 0.5}
    return doc


ENEMY_SOCKETS = {'cairn_dasher': [('attach_ram', 'head'), ('attach_core', 'chest')],
                 'reed_warden': [('attach_lob', 'crest'), ('attach_core', 'body')]}


def enemy(G, oracle, eid):
    EN = G.core('enemies')
    EPO = G.core('enemy_pose')
    m = EN.build(eid)
    parents = m.parents
    bones = skin_order(parents)
    rest = {b: ((_gl(np.subtract(m.bones[b], m.bones[parents[b]])) if parents[b] else _gl(m.bones[b])), _gl(m.bones[b]))
            for b in bones}
    files = _oracle_files(oracle, eid)
    doc = _common(EN.RIG[eid], 'creature', bones, parents, rest, files, _measure(files, bones, parents))
    body = EPO.BODY_BONE[eid]
    doc['reference_body'] = {'generator': 'core/enemies.build(%r)' % eid, 'enemy_id': eid, 'topology': EN.TOPOLOGY[eid],
                             'template': EN.TEMPLATE[eid]}
    doc['clips'] = {'required': ENEMY_CLIPS, 'fps': 15, 'keys': 16, 'duration_s': 1.0, 'interpolation': 'STEP',
                    'key_time': 'key k at t = k / 15 s',
                    'channels': {'rotation': 'every joint except root', 'translation': [body]},
                    'root_motion': 'root never animated; the body joint %r carries a vertical offset only' % body,
                    'fsm_clip': EPO.FSM_CLIP}
    doc['sockets'] = [{'name': n, 'bone': b} for n, b in ENEMY_SOCKETS[eid]]
    doc['budgets'] = {'body_tris_lt': EN.BUDGET, 'prop_tris_le': 200}
    doc['seams'] = []
    doc['silhouette'] = {'rest_height_m': doc['proportions']['height_m'], 'floor': 'no_sink', 'floor_tolerance_m': 0.002,
                         'floor_note': 'creatures hop/gallop: the body joint lifts the mesh; it must never sink below y=0',
                         'blowup_height_factor': 1.6, 'max_vertex_departure_m': 0.5}
    return doc


def derive(oracle, out=None, generator_root=None):
    from ..nbchars import gen
    G = gen.load(generator_root)
    out = Path(out or (REPO / 'rigs'))
    docs = [human(G, oracle), quad(G, oracle), enemy(G, oracle, 'cairn_dasher'), enemy(G, oracle, 'reed_warden')]
    written = []
    for d in docs:
        p = out / d['id'] / 'rig.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, indent=1, sort_keys=False) + '\n')
        written.append(str(p))
    return written
