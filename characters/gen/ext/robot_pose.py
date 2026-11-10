"""Clips for the mechanical family on human16_v1 (lane CHARSYS). Pure Python 3.9, no Blender.

Every robot body carries the shared human clip set so clips work automatically in the runtime:
  base     idle walk run interact talk carry sit          core/pose.py (stance 'neutral')
  combat   idle_combat swing hurt death roll block         core/combat.py (IK on the robot's own proportions)
  enemy    move telegraph attack recover                   archetype templates below (one set per body type)
  boss     attack_sweep attack_slam                        boss template (any body; designed on the brute)
The STORY 1.2 enemy FSM maps onto them (FSM_CLIP); today's module host plays idle_combat / swing / hurt / death,
which every robot has. Same convention as the enemies: 16 STEP keys over 1 s (key f at t = f / 15), loops
(idle, move) periodic in t, no root motion: the root bone carries only the vertical grounding offset (lowest vertex
on the floor, plus the floater's hover height, plus an authored lift).
Euler signs as core/enemy_pose.py (world axes, -Y forward): spine X>0 leans forward; a hanging limb X<0 swings
forward; Y on a hanging left arm < 0 lifts it outward (right arm: > 0); Z>0 turns toward the character's left.
"""
import math

try:
    from ..core import pose as PO
except ImportError:  # Blender job: characters/gen is on sys.path
    from core import pose as PO
BASE = list(PO.HCLIPS)
COMBAT = list(PO.COMBAT_CLIPS)
ENEMY = ['move', 'telegraph', 'attack', 'recover']
BOSS = ['attack_sweep', 'attack_slam']
FSM_CLIP = {'idle': 'idle_combat', 'approach': 'move', 'telegraph': 'telegraph', 'attack': 'attack',
            'recover': 'recover', 'hurt': 'hurt', 'dead': 'death'}
LOOP = {'idle': True, 'walk': True, 'run': True, 'talk': True, 'idle_combat': True, 'move': True}

PHASES = {
    'move': {'loop': True, 'phases': {'loop': [0, 15]}},
    'telegraph': {'loop': False, 'phases': {'wind': [1, 3], 'hold': [4, 15]}, 'telegraph_peak_frame': 3, 'hold_frames': [4, 15]},
    'attack': {'loop': False, 'phases': {'launch': [1, 1], 'active': [2, 6], 'recoil': [7, 9], 'settle': [10, 15]},
               'hit_window': {'frames': [2, 6], 'start_s': round(2 / 15., 6), 'end_s': round(7 / 15., 6)}},
    'recover': {'loop': False, 'phases': {'shake': [1, 7], 'settle': [8, 15]}},
    'attack_sweep': {'loop': False, 'phases': {'wind': [1, 3], 'active': [4, 7], 'settle': [8, 15]},
                     'hit_window': {'frames': [4, 7], 'start_s': round(4 / 15., 6), 'end_s': round(8 / 15., 6)}},
    'attack_slam': {'loop': False, 'phases': {'rise': [1, 4], 'active': [5, 7], 'settle': [8, 15]},
                    'hit_window': {'frames': [5, 7], 'start_s': round(5 / 15., 6), 'end_s': round(8 / 15., 6)}},
}


def clips_for(body, boss=False):
    return BASE + COMBAT + ENEMY + (BOSS if boss else [])


def frame_of(t):
    return max(0, min(15, int(round(t * 15))))


def _blend(a, b, w):
    out = {}
    for k in set(a) | set(b):
        if k == 'lift':
            out[k] = a.get('lift', 0.) + (b.get('lift', 0.) - a.get('lift', 0.)) * w
        else:
            p = a.get(k, (0., 0., 0.)); q = b.get(k, (0., 0., 0.))
            out[k] = tuple(p[i] + (q[i] - p[i]) * w for i in range(3))
    return out


def _add(d, k, v):
    b = d.get(k, (0., 0., 0.))
    d[k] = (b[0] + v[0], b[1] + v[1], b[2] + v[2])


def _sym(**kw):
    """Pose dict from mirrored entries: arm=(x, y_out, z) expands to upper_arm_l/_r with mirrored Y and Z."""
    d = {}
    for k, v in kw.items():
        if k == 'lift':
            d['lift'] = v
        elif k.endswith('_lr'):
            base = k[:-3]
            out = -1. if base.startswith(('upper_arm', 'forearm', 'hand')) else 1.
            d[base + '_l'] = (v[0], v[1] * out, v[2])
            d[base + '_r'] = (v[0], -v[1] * out, -v[2])
        else:
            d[k] = v
    return d


REST = {'upper_arm_l': (-.08, .05, .03), 'upper_arm_r': (-.08, -.05, -.03), 'forearm_l': (-.22, 0, 0), 'forearm_r': (-.22, 0, 0)}

# ------------------------------------------------------------------ archetype key poses
POSES = {
    'walker': {
        'wind': _sym(spine=(-.16, 0, .10), head=(-.12, 0, -.06), pelvis=(0, 0, .06),
                     upper_arm_r=(.85, .35, -.10), forearm_r=(-.55, 0, 0), upper_arm_l=(-.55, .10, .05), forearm_l=(-.70, 0, 0),
                     thigh_lr=(-.38, 0, 0), shin_lr=(.62, 0, 0), foot_lr=(-.22, 0, 0)),
        'strike': _sym(spine=(.30, 0, -.18), head=(.06, 0, .08), pelvis=(.05, 0, -.10),
                       upper_arm_r=(-1.40, .05, .05), forearm_r=(-.10, 0, 0), upper_arm_l=(.40, .15, 0), forearm_l=(-.50, 0, 0),
                       thigh_l=(-.55, 0, 0), shin_l=(.35, 0, 0), thigh_r=(.32, 0, 0), shin_r=(.20, 0, 0), foot_r=(-.12, 0, 0)),
        'recoil': _sym(spine=(.10, 0, -.05), upper_arm_r=(-.65, 0, 0), forearm_r=(-.40, 0, 0), thigh_lr=(-.10, 0, 0), shin_lr=(.20, 0, 0)),
    },
    'brute': {
        'wind': _sym(spine=(-.26, 0, 0), head=(-.18, 0, 0), upper_arm_lr=(-2.45, .28, 0), forearm_lr=(-.70, 0, 0),
                     thigh_lr=(-.30, 0, 0), shin_lr=(.50, 0, 0), foot_lr=(-.18, 0, 0)),
        'strike': _sym(spine=(.52, 0, 0), head=(.20, 0, 0), pelvis=(.10, 0, 0), upper_arm_lr=(-.70, .12, 0), forearm_lr=(-.18, 0, 0),
                       thigh_lr=(-.42, 0, 0), shin_lr=(.62, 0, 0), foot_lr=(-.18, 0, 0)),
        'recoil': _sym(spine=(.22, 0, 0), upper_arm_lr=(-.40, .10, 0), forearm_lr=(-.35, 0, 0), thigh_lr=(-.15, 0, 0), shin_lr=(.25, 0, 0)),
    },
    'floater': {
        'wind': _sym(spine=(-.26, 0, 0), head=(-.10, 0, 0), upper_arm_lr=(-.35, .95, 0), forearm_lr=(-.35, 0, 0), lift=.07),
        'strike': _sym(spine=(.48, 0, 0), head=(.16, 0, 0), upper_arm_lr=(.80, .25, 0), forearm_lr=(-.20, 0, 0), lift=0.),
        'recoil': _sym(spine=(.16, 0, 0), upper_arm_lr=(.25, .35, 0), forearm_lr=(-.30, 0, 0), lift=.02),
    },
}
BOSS_POSES = {
    'sweep_wind': _sym(spine=(-.06, 0, .55), pelvis=(0, 0, .18), head=(0, 0, .20), upper_arm_r=(.30, 1.05, -.20),
                       forearm_r=(-.35, 0, 0), upper_arm_l=(-.60, .25, 0), forearm_l=(-.80, 0, 0),
                       thigh_lr=(-.28, 0, 0), shin_lr=(.45, 0, 0)),
    'sweep_hit': _sym(spine=(.18, 0, -.60), pelvis=(0, 0, -.20), head=(0, 0, -.25), upper_arm_r=(-1.35, -.30, .35),
                      forearm_r=(-.15, 0, 0), upper_arm_l=(.30, .30, 0), forearm_l=(-.70, 0, 0),
                      thigh_lr=(-.30, 0, 0), shin_lr=(.48, 0, 0)),
    'slam_rise': _sym(spine=(-.30, 0, 0), head=(-.20, 0, 0), upper_arm_lr=(-2.70, .12, 0), forearm_lr=(-.35, 0, 0),
                      thigh_lr=(-.10, 0, 0), shin_lr=(.15, 0, 0), lift=.05),
    'slam_hit': _sym(spine=(.62, 0, 0), head=(.25, 0, 0), pelvis=(.12, 0, 0), upper_arm_lr=(-.55, .05, 0), forearm_lr=(-.10, 0, 0),
                     thigh_lr=(-.62, 0, 0), shin_lr=(.95, 0, 0), foot_lr=(-.30, 0, 0)),
}


def _rest():
    return dict(REST)


def _move(body, t):
    w = math.sin(t * math.tau); w2 = math.sin(t * math.tau * 2)
    d = _rest()
    if body == 'floater':
        _add(d, 'spine', (.18, .03 * w, 0)); _add(d, 'head', (-.12, 0, .04 * w))
        for s, sg in (('l', 1), ('r', -1)):
            _add(d, 'upper_arm_' + s, (.35 + .06 * w2, -sg * .10, 0)); _add(d, 'forearm_' + s, (-.25, 0, 0))
        d['lift'] = .02 + .02 * w2
        return d
    amp = .45 if body == 'walker' else .36
    _add(d, 'spine', (.04, .05 * w if body == 'brute' else 0, .05 * w)); _add(d, 'pelvis', (0, .03 * w, -.04 * w))
    for s, sg in (('l', 1), ('r', -1)):
        _add(d, 'thigh_' + s, (amp * sg * w, 0, 0)); _add(d, 'shin_' + s, (.10 + max(0., sg * w) * .55, 0, 0))
        _add(d, 'foot_' + s, (-.06, 0, 0))
        _add(d, 'upper_arm_' + s, (-amp * .7 * sg * w, 0, 0)); _add(d, 'forearm_' + s, (-.25 if body == 'walker' else -.35, 0, 0))
    d['lift'] = .012 * abs(w2) if body == 'walker' else 0.
    return d


def _phase_pose(body, clip, f):
    P = POSES[body]
    rest = _rest()
    if clip == 'telegraph':
        if f == 0:
            return rest
        if f <= 3:
            return _blend(rest, P['wind'], f / 3.)
        d = dict(P['wind'])
        tr = .02 * math.sin(f * 2.1)                                # hold with a small tremble
        _add(d, 'spine', (tr, 0, 0)); _add(d, 'head', (0, 0, tr * 2))
        return d
    if clip == 'attack':
        if f == 0:
            return dict(P['wind'])
        if f == 1:
            return _blend(P['wind'], P['strike'], .6)
        if f <= 6:
            d = dict(P['strike'])
            _add(d, 'spine', (.015 * (f - 2), 0, 0))
            return d
        if f <= 9:
            return _blend(P['strike'], P['recoil'], (f - 6) / 3.)
        return _blend(P['recoil'], rest, (f - 9) / 6.)
    if clip == 'recover':
        if f <= 7:
            amp = .16 * (1. - f / 8.)
            d = _blend(P['recoil'], rest, f / 7.)
            _add(d, 'head', (0, amp * math.sin(f * 2.4), amp * math.sin(f * 1.9)))
            _add(d, 'spine', (0, amp * .5 * math.sin(f * 2.4 + 1.), 0))
            return d
        return _blend(_blend(P['recoil'], rest, 1.), rest, (f - 7) / 8.)
    if clip == 'attack_sweep':
        B = BOSS_POSES
        if f == 0:
            return rest
        if f <= 3:
            return _blend(rest, B['sweep_wind'], f / 3.)
        if f <= 7:
            return _blend(B['sweep_wind'], B['sweep_hit'], min(1., (f - 3) / 2.))
        return _blend(B['sweep_hit'], rest, (f - 7) / 8.)
    if clip == 'attack_slam':
        B = BOSS_POSES
        if f == 0:
            return rest
        if f <= 4:
            return _blend(rest, B['slam_rise'], f / 4.)
        if f <= 7:
            return _blend(B['slam_rise'], B['slam_hit'], min(1., (f - 4) / 1.))
        return _blend(B['slam_hit'], rest, (f - 7) / 8.)
    raise ValueError('unknown robot template clip ' + str(clip))


def key_euler(body, clip, t):
    if clip == 'move':
        return _move(body, t)
    return _phase_pose(body, clip, frame_of(t))


def local_rotations(m, clip, t):
    """-> ({bone: (w, x, y, z)}, lift_m). Base/combat clips delegate to the shared human pose library."""
    if clip in BASE or clip in COMBAT:
        return PO.local_rotations(m.bones, m.params['height'], 'human', clip, t, 'neutral', PO.body_metrics(m)), 0.
    d = key_euler(m.body, clip, t)
    # grounded bodies keep the lowest vertex on the floor on every key (rig kit silhouette.floor); only hovering
    # bodies may rise above their hover height
    lift = float(d.get('lift', 0.)) * m.params['height'] if getattr(m, 'hover', 0.) > 0 else 0.
    return {n: PO.qe(*d.get(n, (0., 0., 0.))) for n in m.parents}, lift


def posed_vertices(m, clip, t):
    """Skinned vertices with grounding: lowest vertex on the floor + hover + lift (root offset returned)."""
    local, lift = local_rotations(m, clip, t)
    V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
    floor = min(v[2] for v in V)
    dz = -floor + getattr(m, 'hover', 0.) + lift
    return [(x, y, z + dz) for x, y, z in V], local, dz


def check_poses(m, clips=None, tol=None):
    """Connectivity on EVERY key (16) of EVERY clip, plus the rest pose (core/connectivity joins)."""
    try:
        from ..core import connectivity as CN
    except ImportError:  # Blender job: characters/gen is on sys.path
        from core import connectivity as CN
    tol = CN.TOL if tol is None else tol
    clips = clips or clips_for(m.body, m.params.get('boss', False))
    st = CN.structure(m)
    worst, fails = {}, []
    poses = [('rest', None)] + [('%s@%02d' % (c, f), (c, f / 15.)) for c in clips for f in range(16)]
    for label, ct in poses:
        if ct is None:
            V = m.vertices
        else:
            local, _ = local_rotations(m, ct[0], ct[1])
            V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
        r = CN.check(m, V, st, tol)
        for j, g in r['gaps'].items():
            if j not in worst or g > worst[j][0]:
                worst[j] = [round(g, 5), label]
            if g > tol:
                fails.append('%s@%s %.4f' % (j, label, g))
    mx = max(worst.items(), key=lambda kv: kv[1][0]) if worst else (None, [0., None])
    return {'pass': not fails, 'fails': fails[:12], 'n_fails': len(fails), 'keys': len(poses), 'worst': worst,
            'max_gap': mx[1][0], 'max_at': '%s %s' % (mx[0], mx[1][1]), 'tol': tol}
