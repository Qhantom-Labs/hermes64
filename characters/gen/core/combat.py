"""Combat clips for the shared human16_v1 rig (lane-combat-art). Pure Python 3.9, no Blender.

Six clips, same convention as the shared set: 16 STEP keys over 1 s (key f at t = f / 15), world-aligned local
quaternions (core/pose.py), root carries only the vertical grounding offset (no horizontal root motion).

  idle_combat  loop   ready stance, staff up-forward in the right fist, left fist guarding the chest
  swing        once   right-handed overhead chop: anticipation 1-4, ACTIVE 5-7 (hit window), recovery 8-15
  hurt         once   snap recoil (head and shoulders thrown back, arms flung out), recover to ready
  death        once   recoil, knees give, topple backward, lie on the back (held from key 10)
  roll         once   forward tuck roll in place (pelvis pitches a full turn over keys 2-9), rise to ready
  block        once   two-handed horizontal staff guard raised by key 2 and HELD 3-15

Authoring: the body (pelvis, spine, head, legs) is FK Euler; each arm is a fist target (out, fwd, up) x height
relative to its shoulder in the rest frame of the posed spine (like the stance IK in core/pose.py), solved with
the shared two-bone IK. The weapon is a rigid child of hand_r whose shaft leaves the fist along GRIP_AXIS (66 deg
from the forearm). The staff direction of a key is reached by choosing the elbow (search around a hint) and a small
fist offset, rolling the forearm about its own axis (<= TWIST_MAX) and bending the wrist <= WRIST_BEND: a larger
bend opens the mitt/cuff seam past the 3 mm connectivity tolerance (probe: 10 deg -> 2.3 mm, 12 deg -> 4 mm).
Arms keep the shared shoulder safety rule (core/pose.ARM_SAFE): on bodies whose sleeve top is spine-weighted a raise
that would collapse the shoulder ring moves the fist toward the relaxed position. Standing keys plant both feet.

PHASES is the documented phase contract read by the manifest and tools/phase_check.py.
"""
import math

from . import pose as PO
from .geometry import HUMAN_PARENTS

COMBAT_CLIPS = ['idle_combat', 'swing', 'hurt', 'death', 'roll', 'block']
KEYS = 16
FPS = 15
from .weapon import GRIP_TILT  # noqa: E402  (rest lean of the shaft toward the forearm's extension)
GRIP_AXIS = (0., -math.cos(GRIP_TILT), -math.sin(GRIP_TILT))   # staff shaft in the hand's rest frame
WRIST_BEND = math.radians(9.)
TWIST_MAX = math.radians(70.)
STAFF_GRIP_TO_LEFT = .27

PHASES = {
    'idle_combat': {'loop': True, 'phases': {'loop': [0, 15]}},
    'swing': {'loop': False, 'phases': {'anticipation': [1, 4], 'active': [5, 7], 'recovery': [8, 15]},
              'hit_window': {'frames': [5, 7], 'start_s': round(5 / 15., 6), 'end_s': round(8 / 15., 6)}},
    'hurt': {'loop': False, 'phases': {'impact': [1, 3], 'recover': [4, 15]}},
    'death': {'loop': False, 'phases': {'impact': [1, 2], 'collapse': [3, 9], 'down_hold': [10, 15]}},
    'roll': {'loop': False, 'phases': {'crouch': [1, 1], 'tuck_roll': [2, 9], 'rise': [10, 13], 'ready': [14, 15]},
             'iframes': [2, 9], 'travel_m': [2.2, 3.2], 'travel_recommended_m': 2.6},
    'block': {'loop': False, 'phases': {'raise': [1, 2], 'guard_hold': [3, 15]}, 'guard_frames': [3, 15]},
}


def _u(*v):
    n = math.sqrt(sum(c * c for c in v)) or 1.
    return tuple(c / n for c in v)


def _pose(plant=True, R=None, L=None, **bones):
    d = {k: tuple(float(c) for c in v) for k, v in bones.items()}
    d['R'] = R; d['L'] = L; d['plant'] = plant
    return d


# Euler signs (core/pose.py): X<0 swings a hanging limb forward; shin X>0 bends the knee; spine/head X>0 bows
# forward; Z>0 turns toward the character's left (+X). R/L = (fist offset (out, fwd, up) x H from the shoulder,
# staff direction in the spine frame (R only), elbow pole hint (out, fwd, up)).
READY = _pose(pelvis=(0, 0, -.30), spine=(.10, 0, .22), head=(-.06, 0, .10),
              thigh_l=(-.30, -.10, 0), shin_l=(.40, 0, 0), foot_l=(-.08, 0, 0),
              thigh_r=(.20, .12, 0), shin_r=(.30, 0, 0), foot_r=(-.12, 0, 0),
              R=((-.04, .13, -.10), _u(-.30, -.45, .84), (1., .20, -.70)),
              L=((-.03, .15, -.07), None, (1., .30, -.80)))
WIND = _pose(pelvis=(0, 0, -.55), spine=(-.04, .05, -.38), head=(.02, 0, .48),
             thigh_l=(-.34, -.12, 0), shin_l=(.26, 0, 0), foot_l=(.06, 0, 0),
             thigh_r=(.26, .14, 0), shin_r=(.46, 0, 0), foot_r=(-.12, 0, 0),
             R=((.06, .09, .09), _u(-.10, .78, .62), (1., .10, -.25)),
             L=((-.03, .20, -.02), None, (1., .0, -1.)))
OVER = _pose(pelvis=(.02, 0, -.15), spine=(.08, .02, -.05), head=(-.02, 0, .18),
             thigh_l=(-.44, -.12, 0), shin_l=(.45, 0, 0), foot_l=(-.04, 0, 0),
             thigh_r=(.32, .13, 0), shin_r=(.30, 0, 0), foot_r=(-.12, 0, 0),
             R=((-.02, .14, .08), _u(.05, -.45, .89), (1., .20, -.60)),
             L=((.02, .12, -.12), None, (1., .30, -.60)))
STRIKE = _pose(pelvis=(.06, 0, .20), spine=(.30, -.04, .40), head=(.04, 0, -.28),
               thigh_l=(-.56, -.12, 0), shin_l=(.64, 0, 0), foot_l=(-.06, 0, 0),
               thigh_r=(.38, .12, 0), shin_r=(.16, 0, 0), foot_r=(-.12, 0, 0),
               R=((-.06, .19, .03), _u(-.10, -.95, -.28), (1., .10, -.80)),
               L=((.13, .08, -.15), None, (1., .40, -.55)))
FOLLOW = _pose(pelvis=(.08, 0, .32), spine=(.34, -.08, .58), head=(.08, 0, -.38),
               thigh_l=(-.56, -.12, 0), shin_l=(.68, 0, 0), foot_l=(-.08, 0, 0),
               thigh_r=(.38, .12, 0), shin_r=(.22, 0, 0), foot_r=(-.12, 0, 0),
               R=((.06, .25, .02), _u(.22, -.80, -.56), (1., .55, -.30)),
               L=((.15, .06, -.14), None, (1., .30, -.60)))
RECOIL = _pose(pelvis=(-.10, .05, -.24), spine=(-.56, .12, .10), head=(-.18, .14, .18),
               thigh_l=(-.18, -.12, 0), shin_l=(.50, 0, 0), foot_l=(-.12, 0, 0),
               thigh_r=(.16, .14, 0), shin_r=(.42, 0, 0), foot_r=(-.14, 0, 0),
               R=((.15, .04, -.06), _u(-.35, .20, .92), (1., .30, -.60)),
               L=((.15, .05, -.06), None, (1., .30, -.60)))
STAGGER = _pose(pelvis=(-.14, .06, -.10), spine=(-.32, .14, .06), head=(-.14, .18, .26),
                thigh_l=(-.30, -.14, 0), shin_l=(.85, 0, 0), foot_l=(-.14, 0, 0),
                thigh_r=(-.12, .16, 0), shin_r=(.80, 0, 0), foot_r=(-.14, 0, 0),
                R=((.13, .03, -.11), _u(-.50, .40, .77), (1., .30, -.60)),
                L=((.13, .05, -.10), None, (1., .30, -.60)))
FALLING = _pose(plant=False, pelvis=(-.85, .04, -.05), spine=(-.16, .06, .04), head=(.12, .10, .20),
                thigh_l=(-.68, -.16, 0), shin_l=(.80, 0, 0), foot_l=(-.10, 0, 0),
                thigh_r=(-.42, .18, 0), shin_r=(.55, 0, 0), foot_r=(-.10, 0, 0),
                R=((.17, .06, -.03), _u(-.70, .50, .50), (1., .40, -.50)),
                L=((.17, .08, -.02), None, (1., .40, -.50)))
DOWN = _pose(plant=False, pelvis=(-1.50, .02, .04), spine=(-.04, .02, 0), head=(.16, 0, .40),
             thigh_l=(-.40, -.20, 0), shin_l=(.66, 0, 0), foot_l=(.10, 0, 0),
             thigh_r=(-.10, .22, 0), shin_r=(.20, 0, 0), foot_r=(.12, 0, 0),
             R=((.20, .02, -.04), _u(-.55, 0., -.83), (.6, 1., -.20)),
             L=((.19, .05, -.07), None, (.6, 1., -.20)))
CROUCH = _pose(pelvis=(.38, 0, -.05), spine=(.40, 0, .05), head=(.20, 0, 0),
               thigh_l=(-1.00, -.14, 0), shin_l=(1.18, 0, 0), foot_l=(-.12, 0, 0),
               thigh_r=(-.82, .14, 0), shin_r=(1.08, 0, 0), foot_r=(-.12, 0, 0),
               R=((-.04, .19, -.10), _u(.10, -.90, .40), (1., .30, -.60)),
               L=((-.04, .19, -.10), None, (1., .30, -.60)))
TUCK = _pose(plant=False, pelvis=(0, 0, 0), spine=(.52, 0, 0), head=(.24, 0, 0),
             thigh_l=(-1.40, -.18, 0), shin_l=(1.50, 0, 0), foot_l=(-.12, 0, 0),
             thigh_r=(-1.40, .18, 0), shin_r=(1.50, 0, 0), foot_r=(-.12, 0, 0),
             R=((.20, .14, -.06), _u(-.90, .30, -.30), (1., .20, -.60)),
             L=((.20, .14, -.06), None, (1., .20, -.60)))
GUARD = _pose(pelvis=(0, 0, -.16), spine=(.06, 0, .12), head=(-.04, 0, .06),
              thigh_l=(-.28, -.14, 0), shin_l=(.40, 0, 0), foot_l=(-.10, 0, 0),
              thigh_r=(.14, .14, 0), shin_r=(.34, 0, 0), foot_r=(-.12, 0, 0),
              R=((-.03, .20, -.08), _u(.97, -.12, .10), (1., .15, -.90)),
              L=('staff', None, (1., .15, -.90)))


def _lerp(a, b, w):
    return tuple(a[i] + (b[i] - a[i]) * w for i in range(len(a)))


def _slerp_u(a, b, w):
    a = _u(*a); b = _u(*b)
    d = max(-1., min(1., sum(a[i] * b[i] for i in range(3))))
    ang = math.acos(d)
    if ang < 1e-5:
        return a
    s = math.sin(ang)
    return _u(*tuple(a[i] * math.sin((1 - w) * ang) / s + b[i] * math.sin(w * ang) / s for i in range(3)))


def _blend(a, b, w, wl=None):
    """Blend two key poses; wl (optional) = a separate weight for the left arm (it may lead or lag)."""
    out = {'plant': a['plant'] and b['plant']}
    w0 = w
    for k in set(a) | set(b):
        if k == 'plant':
            continue
        w = wl if (k == 'L' and wl is not None) else w0
        if k in ('R', 'L'):
            pa, pb = a[k], b[k]
            if pa[0] == 'staff' or pb[0] == 'staff':
                if pa[0] == 'staff' and pb[0] == 'staff':
                    tgt = 'staff'
                elif pb[0] == 'staff':
                    tgt = pa[0] if w <= 0. else ('staff' if w >= 1. else ('blend_to_staff', pa[0], w))
                else:
                    tgt = pb[0] if w >= 1. else ('staff' if w <= 0. else ('blend_to_staff', pb[0], 1. - w))
                out[k] = (tgt, None, _slerp_u(pa[2], pb[2], w))
                continue
            st = None if pa[1] is None else _slerp_u(pa[1], pb[1], w)
            out[k] = (_lerp(pa[0], pb[0], w), st, _slerp_u(pa[2], pb[2], w))
        else:
            out[k] = _lerp(a.get(k, (0., 0., 0.)), b.get(k, (0., 0., 0.)), w)
    return out


def _add(d, bone, off):
    b = d.get(bone, (0., 0., 0.))
    d[bone] = (b[0] + off[0], b[1] + off[1], b[2] + off[2])


def _swing(f):
    T = [(READY, READY, 0.), (READY, WIND, .45), (READY, WIND, .85), (WIND, WIND, 0.), (WIND, WIND, 0.),
         (OVER, OVER, 0.), (STRIKE, STRIKE, 0.), (FOLLOW, FOLLOW, 0.), (FOLLOW, FOLLOW, 0.), (FOLLOW, FOLLOW, 0.),
         (FOLLOW, READY, .15), (FOLLOW, READY, .38), (FOLLOW, READY, .62), (FOLLOW, READY, .82), (FOLLOW, READY, .95),
         (READY, READY, 0.)]
    a, b, w = T[f]
    if 10 <= f <= 14:                            # recovery: the guard (left) fist returns first, clear of the staff
        return _blend(a, b, w, wl=min(1., w * 1.7))
    return _blend(a, b, w)


def _hurt(f):
    w = [0., 1., 1., .92, .80, .64, .48, .34, .22, .13, .07, .03, 0., 0., 0., 0.][f]
    return _blend(READY, RECOIL, w)


def _death(f):
    T = [(READY, READY, 0.), (READY, RECOIL, 1.), (RECOIL, RECOIL, 0.), (RECOIL, STAGGER, .6), (STAGGER, STAGGER, 0.),
         (STAGGER, FALLING, .45), (STAGGER, FALLING, 1.), (FALLING, DOWN, .40), (FALLING, DOWN, .72), (FALLING, DOWN, .92),
         (DOWN, DOWN, 0.), (DOWN, DOWN, 0.), (DOWN, DOWN, 0.), (DOWN, DOWN, 0.), (DOWN, DOWN, 0.), (DOWN, DOWN, 0.)]
    a, b, w = T[f]
    d = _blend(a, b, w)
    if f == 10:
        _add(d, 'head', (.05, 0., 0.))           # small settle bounce, then still
    return d


ROLL_PITCH = {2: 1.05, 3: 1.85, 4: 2.65, 5: 3.45, 6: 4.25, 7: 5.05, 8: 5.80, 9: 6.40}


def _roll(f):
    if f == 0:
        return dict(READY)
    if f == 1:
        return dict(CROUCH)
    if 2 <= f <= 9:
        d = dict(TUCK)
        d['pelvis'] = (ROLL_PITCH[f], 0., 0.)
        return d
    if f <= 13:
        w = {10: .25, 11: .55, 12: .80, 13: 1.}[f]
        d = _blend(TUCK, CROUCH, w)
        d['pelvis'] = (.38 * w + (1 - w) * .12, 0., -.05 * w)
        d['plant'] = f >= 12
        return d
    return _blend(CROUCH, READY, {14: .85, 15: 1.}[f])


def _block(f):
    return _blend(READY, GUARD, {0: 0., 1: .55}.get(f, 1.))


def _idle(t):
    d = dict(READY)
    wave = math.sin(t * math.tau)
    _add(d, 'spine', (.018 * math.sin(t * math.tau * 2), 0., .02 * wave))
    _add(d, 'head', (0., 0., -.015 * wave))
    bob = .045 * (.5 - .5 * math.cos(t * math.tau * 2))
    for s in 'lr':
        _add(d, 'shin_' + s, (bob, 0., 0.)); _add(d, 'thigh_' + s, (-bob * .5, 0., 0.)); _add(d, 'foot_' + s, (-bob * .5, 0., 0.))
    r = d['R']; l = d['L']
    d['R'] = ((r[0][0], r[0][1], r[0][2] + .006 * math.sin(t * math.tau * 2)), r[1], r[2])
    d['L'] = ((l[0][0], l[0][1] + .006 * wave, l[0][2]), l[1], l[2])
    return d


def frame_of(t):
    return max(0, min(KEYS - 1, int(round(t * FPS))))


def key_pose(clip, t):
    f = frame_of(t)
    if clip == 'idle_combat':
        return _idle(t)
    if clip == 'swing':
        return _swing(f)
    if clip == 'hurt':
        return _hurt(f)
    if clip == 'death':
        return _death(f)
    if clip == 'roll':
        return _roll(f)
    if clip == 'block':
        d = _block(f)
        if f >= 3:
            _add(d, 'spine', (.010 * math.sin(t * math.tau * 2), 0., 0.))
        return d
    raise ValueError('unknown combat clip ' + str(clip))


# ------------------------------------------------------------------ solving
def _unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.
    return tuple(c / n for c in v)


def _angle(a, b):
    a = _unit(a); b = _unit(b)
    return math.acos(max(-1., min(1., sum(a[i] * b[i] for i in range(3)))))


def solve_hand(qw, side, want, wrist_max=None):
    wrist_max = WRIST_BEND if wrist_max is None else wrist_max
    qf = qw['forearm_' + side]
    carried = PO.qv(qf, GRIP_AXIS)
    ang = _angle(carried, want)
    target = want if ang <= wrist_max else _slerp_u(carried, want, wrist_max / ang)
    q_w = PO.qm(PO.q_between(carried, target), qf)
    return PO.qm(PO.qc(qf), q_w), max(0., ang - wrist_max)


def solve_staff(bones, local, side, want):
    """Roll the forearm about its own axis (<= TWIST_MAX) so the shaft reaches the plane of `want`, then bend the
    wrist <= WRIST_BEND. Mutates local forearm/hand. -> residual (rad)."""
    qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    fa, ha, up = 'forearm_' + side, 'hand_' + side, 'upper_arm_' + side
    f = PO.qv(qw[fa], _unit(PO._sub(bones[ha], bones[fa])))
    c = PO.qv(qw[fa], GRIP_AXIS)
    w = _unit(want)

    def proj(v):
        d = sum(v[i] * f[i] for i in range(3))
        p = tuple(v[i] - d * f[i] for i in range(3))
        n = math.sqrt(sum(x * x for x in p))
        return tuple(x / n for x in p) if n > 1e-6 else None
    cp, wp = proj(c), proj(w)
    if cp is not None and wp is not None:
        cr = PO._cross(cp, wp)
        phi = math.atan2(sum(cr[i] * f[i] for i in range(3)), sum(cp[i] * wp[i] for i in range(3)))
        phi = max(-TWIST_MAX, min(TWIST_MAX, phi))
        local[fa] = PO.qm(PO.qc(qw[up]), PO.qm(PO.qa(f, phi), qw[fa]))
        qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    q_h, resid = solve_hand(qw, side, w)
    local[ha] = q_h
    return resid


def _target(bones, H, side, off):
    s = 1 if side == 'l' else -1
    S = bones['upper_arm_' + side]
    return (S[0] + s * off[0] * H, S[1] - off[1] * H, S[2] + off[2] * H)


def _pole(side, hint):
    s = 1 if side == 'l' else -1
    return (s * hint[0], -hint[1], hint[2])


def _arm_ik(bones, H, local, side, target, pole, body):
    """Two-bone IK + the shared shoulder safety rule (core/pose.ARM_SAFE) for spine-weighted sleeve tops."""
    q0, p0 = PO._fk_world(bones, HUMAN_PARENTS, local)
    PO._solve_arm(bones, local, q0, p0, side, target, pole)
    if body and body.get('sleeve_edges') and PO._sleeve_ratio(bones, HUMAN_PARENTS, local, body, side) < PO.ARM_SAFE:
        s = 1 if side == 'l' else -1
        relaxed = PO._anchor(bones, H, 'side', s, body)
        lo, hi = 0., 1.
        for _ in range(8):
            mid = (lo + hi) / 2.
            T = PO._push_out(_lerp(target, relaxed, mid), body, H)
            q0, p0 = PO._fk_world(bones, HUMAN_PARENTS, local)
            PO._solve_arm(bones, local, q0, p0, side, T, pole)
            if PO._sleeve_ratio(bones, HUMAN_PARENTS, local, body, side) >= PO.ARM_SAFE:
                hi = mid
            else:
                lo = mid
        T = PO._push_out(_lerp(target, relaxed, hi), body, H)
        q0, p0 = PO._fk_world(bones, HUMAN_PARENTS, local)
        PO._solve_arm(bones, local, q0, p0, side, T, pole)


POLE_SEARCH = [math.radians(a) for a in (0, 15, -15, 30, -30, 45, -45, 60, -60, 80, -80)]
OFFSETS = [(0., 0., 0.)] + [tuple(s * d if i == k else 0. for i in range(3)) for k in range(3) for s in (1, -1) for d in (.025,)]


CONTINUITY_W = 0.        # cost per radian of right-arm rotation change vs the previous key. Measured round 3: weights .02-.3
#   could not remove the swing's k6->k7 upper-arm twist jump without raising the staff residual (straight-arm FOLLOW
#   vs bent-arm STRIKE are different IK branches), so it is off (0 = no key-to-key dependence).


def _qang(q1, q2):
    return 2 * math.acos(min(1., abs(sum(x * y for x, y in zip(q1, q2)))))


def _solve_right(bones, H, local, target, staff_spine, pole_hint, body, ref=None):
    """Search elbow (pole rotated about the shoulder->fist axis) and a small fist offset so the staff reaches its
    direction with the least residual (ties keep the authored hint; with `ref` = the previous key's solution, ties
    also keep the arm's twist continuous instead of flipping the elbow between keys)."""
    qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    want = PO.qv(qw['spine'], staff_spine)
    base = dict(local)
    best = None
    for off in OFFSETS:
        tgt = tuple(target[i] + off[i] * H / 1.65 for i in range(3))
        axis = _unit(PO._sub(tgt, bones['upper_arm_r']))
        for ang in POLE_SEARCH:
            trial = dict(base)
            p = PO.qv(PO.qa(axis, ang), _pole('r', pole_hint))
            _arm_ik(bones, H, trial, 'r', tgt, p, body)
            resid = solve_staff(bones, trial, 'r', want)
            cost = resid + .15 * abs(ang) + 2.5 * math.sqrt(sum(c * c for c in off))
            if ref is not None:
                cost += CONTINUITY_W * (_qang(trial['upper_arm_r'], ref['upper_arm_r']) + _qang(trial['forearm_r'], ref['forearm_r'])
                                        + _qang(trial['hand_r'], ref['hand_r']))
            if best is None or cost < best[0] - 1e-9:
                best = (cost, resid, trial)
            if resid < 1e-4 and ang == 0. and off == (0., 0., 0.):
                break
    local.clear(); local.update(best[2])
    return best[1]


FOOT_FLAT_MAX = .15      # radians of ankle correction used to level a boot before planting
FOOT_REL_MAX = .30       # max foot rotation relative to the shin: more opens the trouser-hem/boot seam (> 3 mm)


def _sole_z(bones, pos, qw, side, body):
    pts = (body or {}).get('sole_' + side)
    if not pts:
        return pos['foot_' + side][2]
    fb = 'foot_' + side
    return min(pos[fb][2] + PO.qv(qw[fb], PO._sub(p, bones[fb]))[2] for p in pts)


def _plant(bones, local, body=None):
    """Both boots on the floor: level each foot a little (<= FOOT_FLAT_MAX toward a flat sole), then bend the knee
    of the leg whose sole reaches lower until both soles are level (the grounding then puts both on the floor)."""
    qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    for side in 'lr':
        fb = 'foot_' + side
        toe = PO.qv(qw[fb], (0., -1., 0.))           # the boot points forward at rest
        level = _unit((toe[0], toe[1], 0.))
        ang = _angle(toe, level)
        tgt = level if ang <= FOOT_FLAT_MAX else _slerp_u(toe, level, FOOT_FLAT_MAX / ang)
        q = PO.q_between(toe, tgt)                   # world correction toward a level sole
        new = PO.qm(PO.qc(qw['shin_' + side]), PO.qm(q, qw[fb]))
        if 2 * math.acos(max(-1., min(1., abs(new[0])))) <= FOOT_REL_MAX:
            local[fb] = new
            qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    zl, zr = _sole_z(bones, pos, qw, 'l', body), _sole_z(bones, pos, qw, 'r', body)
    if abs(zl - zr) < .002:
        return
    side = 'l' if zl < zr else 'r'
    goal = max(zl, zr)
    shin = 'shin_' + side; foot = 'foot_' + side
    q_sh = local[shin]; q_ft = local[foot]

    def foot_q(mid):
        # compensate half the extra knee bend at the ankle, never past FOOT_REL_MAX relative to the shin
        q = PO.qm(PO.qa((1., 0., 0.), -.5 * mid), q_ft)
        ang = 2 * math.acos(max(-1., min(1., abs(q[0]))))
        if ang > FOOT_REL_MAX:
            q = PO.qn(tuple(c for c in PO.qm(PO.qa((1., 0., 0.), 0.), q)))
            axis = _unit(q[1:]) if math.sqrt(sum(c * c for c in q[1:])) > 1e-9 else (1., 0., 0.)
            q = PO.qa(axis if q[0] >= 0 else tuple(-c for c in axis), FOOT_REL_MAX)
        return q
    lo, hi = 0., .9
    for _ in range(18):
        mid = (lo + hi) / 2.
        local[shin] = PO.qm(PO.qa((1., 0., 0.), mid), q_sh)
        local[foot] = foot_q(mid)
        qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
        if _sole_z(bones, pos, qw, side, body) < goal:
            lo = mid
        else:
            hi = mid
    local[shin] = PO.qm(PO.qa((1., 0., 0.), hi), q_sh)
    local[foot] = foot_q(hi)


def _grip_point(bones, pos, qw, body=None):
    from . import weapon as WP
    g = WP.grip_offset(bones, body)
    return PO._add(pos['hand_r'], PO.qv(qw['hand_r'], g))


def _grip_point_l(bones, pos, qw, body=None):
    c = body.get('mitt_l') if body else None
    if c is None:
        return pos['hand_l']
    return PO._add(pos['hand_l'], PO.qv(qw['hand_l'], PO._sub(c, bones['hand_l'])))


def _rest_target(bones, qw, pos, world_target):
    rel = PO._sub(world_target, pos['spine'])
    return PO._add(bones['spine'], PO.qv(PO.qc(qw['spine']), rel))


_CACHE = {}


def local_rotations(bones, H, clip, t, body=None, report=None):
    """World-aligned local quaternions for a combat clip key (no stance: combat poses replace personality)."""
    key = (clip, frame_of(t), round(t, 6), H, tuple(sorted((k, v) for k, v in bones.items())),
           None if not body else (body.get('mitt_r'), body.get('chest_front'), body.get('waist_front'), len(body.get('sleeve_edges', {}).get('r', ()))))
    hit = _CACHE.get(key)
    if hit is not None:
        if report is not None:
            report['wrist_residual_deg'] = hit[1]
        return dict(hit[0])
    d = key_pose(clip, t)
    ref = None
    f = frame_of(t)
    if CONTINUITY_W > 0 and f > 0 and abs(t * FPS - f) < 1e-6:
        ref = local_rotations(bones, H, clip, (f - 1) / float(FPS), body)    # keys solve in order (deterministic)
    local, res_deg = solve_pose(bones, H, d, body, ref)
    _CACHE[key] = (dict(local), res_deg)
    if report is not None:
        report['wrist_residual_deg'] = res_deg
    return local


def solve_pose(bones, H, d, body=None, ref=None):
    """Solve one authored key pose dict (FK body + fist IK + staff) -> (local quaternions, staff residual deg).
    ref: the previous key's solution (continuity tie-break for the right arm)."""
    local = {n: PO.qe(*d.get(n, (0., 0., 0.))) for n in HUMAN_PARENTS}
    if d.get('plant'):
        _plant(bones, local, body)
    Roff, Rstaff, Rpole = d['R']
    tr = PO._push_out(_target(bones, H, 'r', Roff), body, H)
    resid = _solve_right(bones, H, local, tr, Rstaff, Rpole, body, ref)
    qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    Loff, _, Lpole = d['L']
    if Loff == 'staff' or (isinstance(Loff, tuple) and Loff and Loff[0] == 'blend_to_staff'):
        grip = _grip_point(bones, pos, qw, body)
        shaft = PO.qv(qw['hand_r'], GRIP_AXIS)
        on = tuple(grip[i] + shaft[i] * STAFF_GRIP_TO_LEFT for i in range(3))
        if Loff == 'staff':
            tgt_w = on
            for _ in range(3):
                _arm_ik(bones, H, local, 'l', _rest_target(bones, qw, pos, tgt_w), _pole('l', Lpole), body)
                solve_staff(bones, local, 'l', tuple(-c for c in shaft))
                qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
                tgt_w = PO._add(tgt_w, PO._sub(on, _grip_point_l(bones, pos, qw, body)))
        else:
            src = _target(bones, H, 'l', Loff[1])
            src_w = PO._add(pos['spine'], PO.qv(qw['spine'], PO._sub(src, bones['spine'])))
            _arm_ik(bones, H, local, 'l', _rest_target(bones, qw, pos, _lerp(src_w, on, Loff[2])), _pole('l', Lpole), body)
    else:
        tl = PO._push_out(_target(bones, H, 'l', Loff), body, H)
        _arm_ik(bones, H, local, 'l', tl, _pole('l', Lpole), body)
    return local, math.degrees(resid)


def staff_world(bones, local, body=None):
    """(grip, tip, pommel) world points of the staff for a solved pose."""
    from . import weapon as WP
    qw, pos = PO._fk_world(bones, HUMAN_PARENTS, local)
    grip = _grip_point(bones, pos, qw, body)
    shaft = PO.qv(qw['hand_r'], GRIP_AXIS)
    tip = tuple(grip[i] + shaft[i] * WP.TIP_LEN for i in range(3))
    pom = tuple(grip[i] - shaft[i] * WP.POMMEL_LEN for i in range(3))
    return grip, tip, pom
