"""Per-key checks for the combat clips on the shared rig (lane-combat-art). numpy, no Blender.

check_key(a, clip, t) runs, on the actual skinned mesh at one exported key (16 per clip):
  * the pose-intersection volumes and hand-visibility of core/posecheck (same fixed LIMITS, same cameras), with the
    weapon as an occluder (it is in the right fist in every combat clip) and the character's own hand props stowed
    (runtime rule, as for 'carry');
  * the connectivity joins of core/connectivity (head/neck/collar/shoulders/limb roots/wrists/ankles, 3 mm);
  * the deformation gate of core/gates (edge length ratio in [.45, 1.8]);
  * where the weapon is (grip/tip/pommel world points) for the phase checks.
The thresholds are the existing constants; a pose is changed to meet them, never the threshold.
"""
import math

import numpy as np

from . import pose as PO
from . import posecheck as PC
from . import connectivity as CN
from . import gates
from . import weapon as WP
from . import combat as CB

KEY_TIMES = tuple(f / 15. for f in range(16))
STAFF_FLOOR_TOL = .012     # the shaft radius (~2 cm head); an end deeper than this visibly sinks into the ground


def weapon_rest(a):
    """Rest-world vertices of the staff rigidly placed in the right fist (core/weapon grip)."""
    m = WP.build()
    body = PO.body_metrics(a)
    g = WP.grip_offset(a.bones, body)
    j = a.bones['hand_r']
    t = (j[0] + g[0], j[1] + g[1], j[2] + g[2])
    q = WP.REST_Q_BLENDER
    return [PO._add(t, PO.qv(q, v)) for v in m.vertices], m


def weapon_posed(a, qw, pos, rest=None):
    rest, m = rest if rest is not None else weapon_rest(a)
    j = a.bones['hand_r']
    V = np.array([PO._add(pos['hand_r'], PO.qv(qw['hand_r'], PO._sub(v, j))) for v in rest])
    return V, m


def posed(a, clip, t):
    H = a.params.get('height', 1.)
    local = PO.local_rotations(a.bones, H, a.kind, clip, t, None, PO.body_metrics(a))
    qw, pos = PO._fk_world(a.bones, a.parents, local)
    V = np.array(PO.skin(a.bones, a.parents, local, a.vertices, a.weights))
    return V, qw, pos, local


def posed_local(a, local):
    qw, pos = PO._fk_world(a.bones, a.parents, local)
    V = np.array(PO.skin(a.bones, a.parents, local, a.vertices, a.weights))
    return V, qw, pos, local


def check_key(a, clip, t, views=True, wrest=None, st=None, local=None):
    """local: a solved pose to check instead of the clip key (used by the known-bad controls)."""
    V, qw, pos, local = posed(a, clip, t) if local is None else posed_local(a, local)
    P = PC.pieces(a, V)
    rep = {'clip': clip, 'key': int(round(t * 15)), 'fails': []}
    arm = {s: [P['forearm_' + s], P['mitt_' + s], P['thumb_' + s]] for s in 'lr'}
    va = {s: PC.volume(arm[s]) for s in 'lr'}
    rep['arm_arm'] = PC.overlap(arm['l'], arm['r']) / max(1e-9, min(va.values()))
    legs = {s: [P['shin_' + s], P['thigh_' + s], P['boot_' + s]] for s in 'lr'}
    vl = {s: PC.volume(legs[s]) for s in 'lr'}
    rep['leg_leg'] = PC.overlap(legs['l'], legs['r']) / max(1e-9, min(vl.values()))
    for s, o in (('l', 'r'), ('r', 'l')):
        vf = PC.volume([P['forearm_' + s]])
        rep['forearm_torso_' + s] = PC.overlap([P['forearm_' + s]], [P['torso']]) / max(1e-9, vf)
        hand = [P['mitt_' + s], P['thumb_' + s]]
        vh = PC.volume(hand)
        hosts = [P['torso'], P['thigh_l'], P['thigh_r'], P['sleeve_' + o]]
        rep['hand_buried_' + s] = PC.overlap(hand, hosts) / max(1e-9, vh)
        rep['elbow_in_torso_' + s] = PC.point_inside(P['torso'], pos['forearm_' + s])
    L = PC.LIMITS
    if rep['arm_arm'] > L['arm_arm']:
        rep['fails'].append('arm_arm_overlap %.2f' % rep['arm_arm'])
    if rep['leg_leg'] > L['leg_leg']:
        rep['fails'].append('leg_leg_overlap %.2f' % rep['leg_leg'])
    for s in 'lr':
        if rep['forearm_torso_' + s] > L['forearm_torso']:
            rep['fails'].append('forearm_%s_in_torso %.2f' % (s, rep['forearm_torso_' + s]))
        if rep['hand_buried_' + s] > L['hand_buried']:
            rep['fails'].append('hand_%s_buried %.2f' % (s, rep['hand_buried_' + s]))
        if rep['elbow_in_torso_' + s]:
            rep['fails'].append('elbow_%s_inside_torso' % s)
    WV, wm = weapon_posed(a, qw, pos, wrest)
    if views:
        extra = [('prop_' + WP.WEAPON_ID, WV[np.array(wm.faces)])]
        cams = {'front': 0., '34_l': PC.YAW_34, '34_r': -PC.YAW_34}
        vis = {c: PC.hand_visibility(a, V, P, extra, y) for c, y in cams.items()}
        rep['hand_vis'] = {c: {k: round(v[0], 3) for k, v in r.items()} for c, r in vis.items()}
        for s in 'lr':
            f = vis['front']['hand_' + s][0]
            q = vis['34_' + s]['hand_' + s][0]
            if f < L['hand_vis_front']:
                rep['fails'].append('hand_%s_hidden_front %.2f' % (s, f))
            if q < L['hand_vis_34']:
                rep['fails'].append('hand_%s_hidden_34 %.2f' % (s, q))
    cn = CN.check(a, [tuple(v) for v in V], st)
    rep['connectivity_max'] = round(max(cn['gaps'].values()) if cn['gaps'] else 0., 5)
    rep['connectivity_at'] = max(cn['gaps'], key=cn['gaps'].get) if cn['gaps'] else None
    for j in cn['fails']:
        rep['fails'].append('connectivity_%s %.4f' % (j, cn['gaps'][j]))
    dg = gates.deformation(a.vertices, [tuple(v) for v in V], a.faces)
    rep['edge_ratio'] = [round(dg['edge_ratio_min'], 3), round(dg['edge_ratio_max'], 3)]
    if not dg['pass']:
        rep['fails'].append('deformation %.3f..%.3f' % (dg['edge_ratio_min'], dg['edge_ratio_max']))
    floor = float(V[:, 2].min())
    rep['floor'] = round(floor, 4)
    # foot contact (standing clips): each boot's lowest point above the floor
    rep['foot_lift'] = {s: round(float(V[a.parts['boot_' + s], 2].min()) - floor, 4) for s in 'lr'}
    rr = {}
    if clip in CB.COMBAT_CLIPS:
        CB.local_rotations(a.bones, a.params.get('height', 1.), clip, t, PO.body_metrics(a), report=rr)
    rep['staff_residual_deg'] = round(rr.get('wrist_residual_deg', 0.), 2)
    grip, tip, pom = CB.staff_world(a.bones, local, PO.body_metrics(a))
    rep['staff'] = {'grip': [round(c - (0 if i < 2 else floor), 4) for i, c in enumerate(grip)],
                    'tip': [round(c - (0 if i < 2 else floor), 4) for i, c in enumerate(tip)],
                    'pommel': [round(c - (0 if i < 2 else floor), 4) for i, c in enumerate(pom)]}
    # the weapon may not pass through the body: staff points (5 samples on the shaft) inside the torso volume
    inside = 0
    for k in range(1, 6):
        p = tuple(grip[i] + (tip[i] - grip[i]) * k / 5. for i in range(3))
        if PC.point_inside(P['torso'], p):
            inside += 1
    rep['staff_in_torso'] = inside
    # the staff may not sink into the floor (it is not part of the body grounding): ends above floor - its radius
    low = min(tip[2], pom[2]) - floor
    rep['staff_floor'] = round(low, 4)
    if low < -STAFF_FLOOR_TOL:
        rep['fails'].append('staff_below_floor %.3f' % low)
    if inside >= 2:
        rep['fails'].append('staff_through_torso %d/5' % inside)
    rep['pass'] = not rep['fails']
    for k, v in list(rep.items()):
        if isinstance(v, float):
            rep[k] = round(v, 4)
    return rep


def check_clip(a, clip, views=True, times=KEY_TIMES):
    wrest = weapon_rest(a)
    st = CN.structure(a)
    return [check_key(a, clip, t, views, wrest, st) for t in times]
