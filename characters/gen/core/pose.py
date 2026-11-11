"""Shared pose library for the 16-bone rigs (pure Python 3.9, no Blender).

local_rotations(bones, height, kind, clip, t, stance) -> {bone: (w, x, y, z)}
Rotations are WORLD-ALIGNED LOCAL quaternions: q_world(b) = q_world(parent(b)) * q_local(b). Every bone
rests pointing +Z, so the rest orientation is shared; blender.pose() converts to bone space.

Clips are the shared held 15 fps set. A STANCE is per-character personality: FK offsets for
pelvis/spine/head/legs plus 2-bone arm IK targets expressed relative to body landmarks (so one stance
fits every height/build/age on the shared rig). Arms flagged `hold` keep their target during other
clips (a mug or lantern stays in the hand while walking).
"""
import math

from .geometry import HUMAN_PARENTS, QUAD_PARENTS

HCLIPS = ['idle', 'walk', 'run', 'interact', 'talk', 'carry', 'sit']
ACLIPS = ['idle', 'walk', 'run', 'sit', 'loaf', 'sleep_curled', 'stretch']
COMBAT_CLIPS = ['idle_combat', 'swing', 'hurt', 'death', 'roll', 'block']     # lane-combat-art (core/combat.py)


# ------------------------------------------------------------------ quaternion helpers (w, x, y, z)
def qn(q):
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def qm(a, b):
    aw, ax, ay, az = a; bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def qc(q):
    return (q[0], -q[1], -q[2], -q[3])


def qv(q, v):
    return qm(qm(q, (0., v[0], v[1], v[2])), qc(q))[1:]


def qa(axis, ang):
    n = math.sqrt(sum(c * c for c in axis)) or 1.
    s = math.sin(ang / 2)
    return (math.cos(ang / 2), axis[0] / n * s, axis[1] / n * s, axis[2] / n * s)


def qe(x, y, z):
    """Blender Euler 'XYZ' (X applied first) -> quaternion."""
    return qm(qa((0, 0, 1), z), qm(qa((0, 1, 0), y), qa((1, 0, 0), x)))


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _len(a): return math.sqrt(_dot(a, a))


def _unit(a):
    n = _len(a)
    return _mul(a, 1. / n) if n > 1e-12 else (0., 0., 1.)


def _mat_q(m):
    """Rotation matrix (rows) -> quaternion."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.) * 2
        return qn(((.25 * s), (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s))
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1. + m[0][0] - m[1][1] - m[2][2]) * 2
        return qn(((m[2][1] - m[1][2]) / s, .25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s))
    if m[1][1] > m[2][2]:
        s = math.sqrt(1. + m[1][1] - m[0][0] - m[2][2]) * 2
        return qn(((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, .25 * s, (m[1][2] + m[2][1]) / s))
    s = math.sqrt(1. + m[2][2] - m[0][0] - m[1][1]) * 2
    return qn(((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, .25 * s))


def q_frames(a1, a2, b1, b2):
    """Rotation taking direction a1 -> b1 while carrying the plane (a1, a2) onto (b1, b2)."""
    def frame(x, y):
        x = _unit(x); z = _unit(_cross(x, y)); y = _cross(z, x)
        return x, y, z
    ax, ay, az = frame(a1, a2); bx, by, bz = frame(b1, b2)
    # R = B * A^T
    m = [[bx[i] * ax[j] + by[i] * ay[j] + bz[i] * az[j] for j in range(3)] for i in range(3)]
    return _mat_q(m)


def q_between(a, b):
    a = _unit(a); b = _unit(b)
    d = _dot(a, b)
    if d > .999999:
        return (1., 0., 0., 0.)
    if d < -.999999:
        ax = _cross(a, (1, 0, 0))
        if _len(ax) < 1e-6:
            ax = _cross(a, (0, 1, 0))
        return qa(ax, math.pi)
    ax = _cross(a, b)
    return qn((1 + d, ax[0], ax[1], ax[2]))


# ------------------------------------------------------------------ base clips (Euler, world axes)
def base_euler(kind, clip, t, interact_side='r'):
    """The shared held clip set. X: negative swings a hanging limb forward (-Y); positive shin X bends the knee.
    interact_side: the arm that reaches for 'interact' ('l' when the right hand holds a prop)."""
    d = {}
    wave = math.sin(t * math.tau)

    def r(n, x=0., y=0., z=0.):
        d[n] = (x, y, z)
    if kind == 'human':
        r('pelvis', 0, .025 * wave, .012); r('spine', .025 * wave, -.065, .025 + .025 * wave); r('head', -.045, .07, .12 * wave)
        for s, sg in (('l', 1), ('r', -1)):
            r('upper_arm_' + s, -.10, sg * .065, sg * .035); r('forearm_' + s, -.24 - .07 * sg * wave)
        if clip == 'idle':
            r('thigh_l', -.055); r('shin_l', .12)
        if clip in ('walk', 'run', 'carry'):
            amp = .5 if clip != 'run' else .85
            r('spine', -.10 if clip == 'run' else -.025, 0, .05 * wave)
            for s, sg in (('l', 1), ('r', -1)):
                r('thigh_' + s, amp * sg * wave); r('shin_' + s, .10 + max(0, sg * wave) * (.9 if clip == 'run' else .5)); r('foot_' + s, -.08)
                r('upper_arm_' + s, -amp * .65 * sg * wave, 0, sg * .05); r('forearm_' + s, -.2 if clip != 'run' else -.65)
            if clip == 'carry':
                for s, sg in (('l', 1), ('r', -1)):
                    r('upper_arm_' + s, -.22, sg * .18, sg * .02); r('forearm_' + s, -1.15)
        if clip == 'interact':
            k = .5 - .5 * math.cos(t * math.tau)
            r('upper_arm_' + interact_side, -1.0 * k); r('forearm_' + interact_side, -.4 * k); r('spine', -.13 * k)
        if clip == 'talk':
            r('upper_arm_l', -.28 - .2 * wave, -.2, -.12); r('forearm_l', -.8 - .18 * wave); r('hand_l', .05, .15, .15)
            r('upper_arm_r', -.3 + .1 * wave, .12, .16); r('forearm_r', -.45 + .2 * wave); r('head', .07 * wave, 0, .15 * wave)
        if clip == 'sit':
            for s, sg in (('l', 1), ('r', -1)):
                r('thigh_' + s, -1.35); r('shin_' + s, 1.28); r('upper_arm_' + s, -.3); r('forearm_' + s, -.65)
    else:
        r('head', 0, 0, .04 * wave); r('tail_1', 0, 0, .06 * wave); r('tail_2', 0, 0, .12 * wave)
        if clip in ('walk', 'run'):
            amp = .4 if clip == 'walk' else .65
            for limb, sg in (('fl', 1), ('br', 1), ('fr', -1), ('bl', -1)):
                r('leg_' + limb, amp * sg * wave); r('paw_' + limb, -amp * sg * wave * .6)
        if clip == 'sit':
            r('hips', -.6); r('chest', .45); r('neck', .15)
            for s in ('l', 'r'):
                r('leg_b' + s, -1); r('paw_b' + s, 1.25); r('leg_f' + s, .15)
            r('tail_1', 0, 0, 1.0); r('tail_2', 0, 0, .55); r('tail_3', 0, 0, .4)
        if clip in ('loaf', 'sleep_curled'):
            for s in ('l', 'r'):
                r('leg_f' + s, 1.42); r('paw_f' + s, -1.42); r('leg_b' + s, -1.42); r('paw_b' + s, 1.42)
            r('neck', .14)
            if clip == 'sleep_curled':
                # round 19 (STEER-7 §2): the head stays upright (tilt <= 15 deg, ears standing on top) while it curls toward
                # the tail; the old head (.62, 0, .55) lay on its side and one ear pointed sideways, read from that side as a
                # dark triangle inside the head outline (probes/probe_sleep_head_grid.py, render_sleep_candidates.py)
                r('chest', 0, 0, .65); r('neck', .45, 0, .55); r('head', -.20, .30, .35)
                r('tail_1', -.45, 0, 1.1); r('tail_2', 0, 0, .85); r('tail_3', 0, 0, .8)
        if clip == 'stretch':
            r('chest', -.42); r('neck', .36)                  # round 11: lower chest/head (play-bow stretch)
            for s in ('l', 'r'):
                r('leg_f' + s, -.95); r('paw_f' + s, .95); r('leg_b' + s, .3)
    return d


# ------------------------------------------------------------------ sleeping head check (round 19, STEER-7 §2)
SLEEP_HEAD_MAX_TILT = 20.      # degrees: the sleeping head stays upright (ears on top), never lies on its side
SLEEP_HEAD_R18 = {'neck': (.42, 0., .55), 'head': (.62, 0., .55)}   # known-bad control: round-18 head (57 deg tilt)


def sleep_head_check(a, override=None):
    """Tilt of the head's up axis from vertical in sleep_curled at t = 0 (quadrupeds). A head lying on its side
    turns one ear sideways; from that side it reads as a dark triangle inside the head outline. override: Euler
    entries replacing the clip's (for the known-bad control)."""
    eul = base_euler(a.kind, 'sleep_curled', 0.)
    if override:
        eul.update(override)
    local = {n: qe(*eul.get(n, (0., 0., 0.))) for n in QUAD_PARENTS}
    qw, pos = _fk_world(a.bones, a.parents, local)
    up = qv(qw['head'], (0., 0., 1.))
    tilt = math.degrees(math.acos(max(-1., min(1., up[2]))))
    fails = ['sleep_head_tilt %.1f > %.0f deg' % (tilt, SLEEP_HEAD_MAX_TILT)] if tilt > SLEEP_HEAD_MAX_TILT else []
    return {'pass': not fails, 'fails': fails, 'tilt_deg': round(tilt, 2)}


# ------------------------------------------------------------------ stances (personality)
# fk: Euler offsets added to the clip (world axes; for arms/legs x is mirrored by side via 'l'/'r' names).
# ik: side -> (anchor, (out, fwd, up) offset in units of height, pole, hold)
#     anchors: hip, waist, chest, chin, above, back, side ; offset x is OUTWARD for that side, fwd = -Y.
STANCES = {
    'neutral': {},
    # round 8 (visor cameo): relaxed, confident weight shift; arms hang loose a little away from the body
    'confident': {'fk': {'pelvis': (0, .05, .05), 'spine': (-.05, -.06, -.04), 'head': (.03, .05, -.08),
                         'thigh_r': (-.08, .06, 0), 'shin_r': (.15, 0, 0), 'foot_r': (-.07, 0, 0), 'thigh_l': (0, -.03, 0),
                         'upper_arm_l': (.03, 0, .025), 'upper_arm_r': (-.02, 0, -.035), 'forearm_l': (-.08, 0, 0)}},
    'hands_hips': {'fk': {'spine': (-.07, 0, 0), 'head': (-.06, 0, 0), 'pelvis': (0, .03, 0), 'thigh_l': (0, -.07, 0),
                          'thigh_r': (0, .07, 0)},
                   'ik': {'l': ('hip', (.035, .0, .035), 'out', False), 'r': ('hip', (.035, .0, .035), 'out', False)}},
    # round 8: folded arms stacked in front of the chest (left forearm high, right forearm low and further
    # forward), each mitt ending at the opposite side so both hands show; replaces the round-7 lump
    # (kept as KNOWN_BAD_STANCES['arms_crossed_r7']).
    'arms_crossed': {'fk': {'spine': (-.03, 0, 0), 'head': (.03, 0, -.12), 'pelvis': (0, -.05, .04), 'thigh_r': (-.06, 0, 0),
                            'shin_r': (.14, 0, 0), 'foot_r': (-.08, 0, 0)},
                     'ik': {'l': ('chest', (-.05, .085, .045), 'down', False), 'r': ('chest', (-.05, .11, -.065), 'down', False)}},
    # round 8: mug held out from the chest in the right hand, left hand cupped below-beside it, elbows clear
    'hold_mug': {'fk': {'spine': (.04, 0, 0), 'head': (.12, 0, .05), 'pelvis': (0, .04, 0), 'thigh_l': (-.05, 0, 0), 'shin_l': (.12, 0, 0)},
                 'ik': {'r': ('chest', (.05, .10, .0), 'out_down', True), 'l': ('chest', (.08, .09, -.05), 'out_down', True)}},
    'lantern_up': {'fk': {'spine': (-.04, .05, .1), 'head': (-.10, -.06, .22), 'pelvis': (0, -.04, 0), 'thigh_r': (-.12, 0, 0),
                          'shin_r': (.06, 0, 0)},
                   'ik': {'r': ('shoulder', (.10, .15, .0), 'out_down', True)}},
    # round 8: book/datapad raised in both hands at its lower corners (core/attach.py tilts it to the eyes)
    'reading': {'fk': {'spine': (.08, 0, 0), 'head': (.30, 0, 0), 'thigh_l': (-.04, 0, 0), 'shin_l': (.1, 0, 0)},
                'ik': {'r': ('chest', (.09, .065, .03), 'out_down', True), 'l': ('chest', (.09, .065, .03), 'out_down', True)}},
    # round 16 (STEER-6 variety): datapad held low in both hands at the belly, head bowed over it (the masked
    # resident checking a route); the datapad tilts up to the eyes (core/attach.PLACE_STANCE)
    'tablet': {'fk': {'spine': (.10, 0, 0), 'head': (.40, 0, 0), 'pelvis': (0, .03, 0), 'thigh_r': (-.04, 0, 0), 'shin_r': (.09, 0, 0)},
               'ik': {'r': ('waist', (.075, .035, .07), 'out_down', True), 'l': ('waist', (.075, .035, .07), 'out_down', True)}},
    'wave': {'fk': {'spine': (0, .07, 0), 'head': (-.06, .1, .1), 'pelvis': (0, -.05, 0), 'thigh_l': (0, -.06, 0)},
             # round 12: 'hi' wave - hand beside the head, elbow below at shoulder height (the overhead wave
             # collapsed the LBS shoulder ring on face-head bodies in the sweep)
             'ik': {'r': ('above', (.12, .02, -.22), 'down', False)}},
    # round 8: hands rest apart on the back of the hips (no longer clasped through each other / the torso);
    # judged from the back cameras ('views')
    'behind_back': {'views': 'back', 'fk': {'spine': (-.08, 0, 0), 'head': (-.04, 0, .1), 'thigh_l': (-.08, 0, 0),
                                            'shin_l': (.16, 0, 0), 'foot_l': (-.08, 0, 0)},
                    'ik': {'l': ('back', (.07, -.03, -.01), 'back', False), 'r': ('back', (.07, -.03, -.02), 'back', False)}},
    'pockets': {'fk': {'spine': (.05, -.05, 0), 'head': (.08, -.06, -.1), 'pelvis': (0, .05, 0), 'thigh_r': (-.05, .05, 0),
                       'shin_r': (.1, 0, 0)},
                # round 12: thumbs hooked at the front pockets, hands visible (hands inside pockets failed the
                # hand-visibility check on every body the sweep tried)
                'ik': {'l': ('hip', (-.04, .075, -.01), 'out', False), 'r': ('hip', (-.04, .075, -.01), 'out', False)}},
    'stoop_cane': {'fk': {'spine': (.26, 0, 0), 'head': (-.24, 0, .06), 'thigh_l': (-.1, 0, 0), 'thigh_r': (-.1, 0, 0),
                          'shin_l': (.2, 0, 0), 'shin_r': (.2, 0, 0), 'foot_l': (-.1, 0, 0), 'foot_r': (-.1, 0, 0)},
                   'ik': {'r': ('hip', (.02, .11, -.01), 'out_down', True), 'l': ('waist', (-.01, .06, .0), 'down', False)},
                   'persist': True},
    'shy': {'fk': {'spine': (.07, 0, 0), 'head': (.2, .1, .22), 'pelvis': (0, .05, 0), 'thigh_l': (-.03, .06, 0),
                   'thigh_r': (0, -.05, 0), 'shin_l': (.1, 0, 0)},
            # round 12: hands held low in front, just apart (they crossed through each other and the belly before)
            'ik': {'l': ('waist', (.035, .10, -.085), 'out_down', False), 'r': ('waist', (.035, .105, -.09), 'out_down', False)}},
    # round 8: hand to chin with the elbow out, other hand across the waist in front (elbows clear of the torso)
    'thinking': {'fk': {'spine': (.02, -.04, 0), 'head': (.1, .12, -.12), 'thigh_l': (-.04, 0, 0), 'shin_l': (.12, 0, 0)},
                 # round 12: other hand on the hip (across-the-waist over-rotated the shoulder on deep bodies)
                 'ik': {'r': ('chin', (.01, .045, -.065), 'out_down', False), 'l': ('hip', (.015, .02, .02), 'out', False)}},
    'satchel': {'fk': {'spine': (.03, .04, .06), 'head': (0, .06, -.1), 'pelvis': (0, -.04, 0), 'thigh_l': (-.05, 0, 0),
                       'shin_l': (.1, 0, 0)},
                'ik': {'r': ('chest', (.005, .05, .0), 'out_down', False)}},
    'eager': {'fk': {'spine': (.1, 0, 0), 'head': (-.16, 0, 0), 'thigh_l': (-.12, 0, 0), 'shin_l': (.18, 0, 0), 'foot_l': (-.06, 0, 0)},
              # round 12: fists in front of the hips (less forward reach; the waist target over-rotated the
              # shoulders of compact bodies)
              'ik': {'l': ('hip', (-.03, .07, .03), 'down', False), 'r': ('hip', (-.03, .07, .03), 'down', False)}},
    'duffel': {'fk': {'spine': (0, .1, 0), 'head': (.05, -.05, .14), 'pelvis': (0, .07, 0), 'thigh_r': (0, .05, 0)},
               'ik': {'r': ('side', (.05, .0, -.01), 'out', True)}},
    'guard': {'fk': {'spine': (-.02, 0, -.1), 'head': (-.03, 0, .16), 'thigh_l': (-.16, -.08, 0), 'shin_l': (.12, 0, 0),
                     'thigh_r': (.12, .08, 0), 'shin_r': (.08, 0, 0), 'foot_l': (-.04, 0, 0)},
              'ik': {'r': ('waist', (.07, .09, -.04), 'down', True), 'l': ('hip', (.015, .02, .02), 'out', False)}},
}


# Known-bad controls for core/posecheck.py: kept verbatim, never used by a cast entry.
# 'arms_crossed_r7' is the round-7 crossed-arms stance the owner flagged (thin forearms merging into one lump,
# hands clipped inside the volume); the pose check must reject it (tests/test_posecheck.py).
KNOWN_BAD_STANCES = {
    'arms_crossed_r7': {'fk': {'spine': (-.03, 0, 0), 'head': (.03, 0, -.12), 'pelvis': (0, -.05, .04), 'thigh_r': (-.06, 0, 0),
                               'shin_r': (.14, 0, 0), 'foot_r': (-.08, 0, 0)},
                        'ik': {'l': ('chest', (-.075, .055, -.035), 'down', False), 'r': ('chest', (-.065, .07, -.06), 'down', False)}},
}


def stance_def(name):
    name = name or 'neutral'
    if name in STANCES:
        return STANCES[name]
    if name in KNOWN_BAD_STANCES:
        return KNOWN_BAD_STANCES[name]
    raise ValueError('unknown stance ' + str(name))


_BODY_SKIP = ('sleeve', 'mitt', 'thumb', 'trouser', 'boot', 'face', 'nose', 'hair', 'ear', 'spike', 'leaf', 'visor',
              'collar', 'hood', 'head', 'acc', 'extra', 'brim', 'lock', 'bun', 'tail', 'braid')


def body_metrics(a):
    """Torso extents of a humanoid mesh (rest pose), used to keep IK anchors outside wide/puffy bodies.
    Cached on the mesh. Returns None for non-humans."""
    if getattr(a, 'kind', None) != 'human':
        return None
    cached = getattr(a, '_body_metrics', None)
    if cached is not None:
        return cached
    H = a.params.get('height', 1.)
    ids = [i for n, v in a.parts.items() if not n.startswith(_BODY_SKIP) for i in v]
    V = [a.vertices[i] for i in ids]
    P = a.bones['pelvis']; Sh = a.bones['upper_arm_l']

    def band(z0, dz):
        sel = [v for v in V if abs(v[2] - z0) < dz]
        return sel or V
    ch = band(Sh[2] - .075 * H, .06 * H); wa = band(P[2] + .075 * H, .05 * H); hp = band(P[2] + .02 * H, .05 * H)
    m = {'chest_front': min(v[1] for v in ch), 'waist_front': min(v[1] for v in wa),
         'back': max(v[1] for v in hp), 'waist_half_w': max(abs(v[0]) for v in wa),
         'chest_half_w': max(abs(v[0]) for v in ch), 'chest_back': max(v[1] for v in ch),
         'z_chest': Sh[2] - .075 * H, 'z_waist': P[2] + .075 * H}
    # round 13 (STEER-5 §3): shoulder edges of each sleeve (any edge touching a vertex with spine weight), for the
    # deformation-aware arm fallback in local_rotations
    se = {}
    for side in 'lr':
        ids = set(a.parts.get('sleeve_' + side, []))
        edges = set()
        for f in a.faces:
            if f[0] in ids and f[1] in ids and f[2] in ids:
                for k in range(3):
                    i, j = sorted((f[k], f[(k + 1) % 3]))
                    if 'spine' in a.weights[i] or 'spine' in a.weights[j]:
                        edges.add((i, j))
        se[side] = [(a.vertices[i], a.vertices[j], a.weights[i], a.weights[j], _len(_sub(a.vertices[i], a.vertices[j])))
                    for i, j in sorted(edges) if _len(_sub(a.vertices[i], a.vertices[j])) > 1e-6]
    m['sleeve_edges'] = se
    # lane-combat-art: rest mitt centres (the weapon grip sits in the right fist; core/weapon.grip_offset)
    for side in 'lr':
        ids = a.parts.get('mitt_' + side, [])
        m['mitt_' + side] = tuple(sum(a.vertices[i][k] for i in ids) / float(len(ids)) for k in range(3)) if ids else None
        # boot sole points (rest), for planting both feet in the combat clips (core/combat._plant)
        bids = a.parts.get('boot_' + side, [])
        if bids:
            zmin = min(a.vertices[i][2] for i in bids)
            m['sole_' + side] = [a.vertices[i] for i in bids if a.vertices[i][2] < zmin + .025 * H]
    try:
        a._body_metrics = m
    except AttributeError:
        pass
    return m


def _push_out(target, body, H, margin=.012):
    """Keep an IK hand target outside the torso: elliptical cross-section interpolated between the waist and
    chest bands; a target inside is moved radially to the surface + margin (round 12; hands were buried in deep
    bellies / puffy chests on random bodies)."""
    x, y, z = target
    if not body or z < body['z_waist'] - .12 * H or z > body['z_chest'] + .08 * H:
        return target
    k = min(1., max(0., (z - body['z_waist']) / max(1e-6, body['z_chest'] - body['z_waist'])))
    ax = body['waist_half_w'] * (1 - k) + body['chest_half_w'] * k
    front = -(body['waist_front'] * (1 - k) + body['chest_front'] * k)
    back = body['back'] * (1 - k) + body['chest_back'] * k
    ay = front if y < 0 else back
    r = math.sqrt((x / ax) ** 2 + (y / ay) ** 2)
    need = 1. + margin * H / min(ax, ay)
    if r >= need or r < 1e-6:
        return target
    f = need / r
    return (x * f, y * f, z)


def _anchor(bones, H, name, s, body=None):
    """IK anchor points. With body metrics the anchors move out to stay clear of a deeper/wider torso than the
    nominal cast body (they never move inward, so tuned cast stances are unchanged)."""
    P = bones['pelvis']; Sh = bones['upper_arm_' + ('l' if s > 0 else 'r')]; Hd = bones['head']
    hipw = abs(bones['thigh_l'][0]) * 1.75
    if body:
        hipw = max(hipw, body['waist_half_w'] + .012 * H)
    if name == 'hip':
        return (s * hipw, P[1], P[2] + .02 * H)
    if name == 'waist':
        y = P[1] - .09 * H
        if body:
            y = min(y, body['waist_front'] - .02 * H)
        return (0., y, P[2] + .075 * H)
    if name == 'chest':
        y = -.10 * H
        if body:
            y = min(y, body['chest_front'] - .015 * H)
        return (0., y, Sh[2] - .075 * H)
    if name == 'chin':
        return (0., -.105 * H, Hd[2] + .06 * H)
    if name == 'above':
        return (s * abs(Sh[0]) * .9, -.03 * H, Hd[2] + .2 * H)
    if name == 'back':
        y = P[1] + .10 * H
        if body:
            y = max(y, body['back'] + .015 * H)
        return (0., y, P[2] + .05 * H)
    if name == 'side':
        return (s * abs(Sh[0]) * 1.5, -.01 * H, P[2] - .02 * H)
    if name == 'shoulder':
        return (s * abs(Sh[0]), Sh[1], Sh[2])
    raise ValueError('unknown anchor ' + name)


POLES = {'out': (1., .25, -.25), 'down': (.35, .35, -1.), 'back': (.45, 1., -.25), 'front': (.3, -1., -.4),
         'out_down': (1., .2, -.8)}


def _fk_world(bones, parents, local):
    """World rotations and posed joint positions from local rotations."""
    qw = {}; pos = {}
    for name in parents:
        pass
    order = []
    seen = set()

    def visit(n):
        if n in seen:
            return
        if parents[n]:
            visit(parents[n])
        seen.add(n); order.append(n)
    for n in parents:
        visit(n)
    for n in order:
        par = parents[n]
        q = local.get(n, (1., 0., 0., 0.))
        if par is None:
            qw[n] = q; pos[n] = bones[n]
        else:
            qw[n] = qm(qw[par], q)
            pos[n] = _add(pos[par], qv(qw[par], _sub(bones[n], bones[par])))
    return qw, pos


def _solve_arm(bones, local, qw, pos, side, target_rest, pole_rest):
    s = 1 if side == 'l' else -1
    sh, el, wr = 'upper_arm_' + side, 'forearm_' + side, 'hand_' + side
    qsp = qw['spine']
    # target/pole defined in the rest frame relative to the spine joint -> follow the posed spine
    T = _add(pos['spine'], qv(qsp, _sub(target_rest, bones['spine'])))
    pole = qv(qsp, pole_rest)
    S = pos[sh]
    a = _len(_sub(bones[el], bones[sh])); b = _len(_sub(bones[wr], bones[el]))
    # round 12: elbow flexion limit - never fold tighter than a reach of .58 x arm length (tight folds collapsed
    # the inner elbow on compact random bodies in the sweep); the cast's tightest pose (hand on chin) is .87
    dv = _sub(T, S); d = max(abs(a - b) + 1e-4, .58 * (a + b), min(a + b - 1e-4, _len(dv)))
    dirv = _unit(dv)
    cosA = max(-1., min(1., (a * a + d * d - b * b) / (2 * a * d)))
    pp = _sub(pole, _mul(dirv, _dot(pole, dirv)))
    pp = _unit(pp) if _len(pp) > 1e-6 else _unit(_cross(dirv, (0, 1, 0)))
    E = _add(S, _add(_mul(dirv, a * cosA), _mul(pp, a * math.sqrt(max(0., 1 - cosA * cosA)))))
    Tc = _add(S, _mul(dirv, d))
    up_r = _sub(bones[el], bones[sh]); fo_r = _sub(bones[wr], bones[el])
    up_n = _sub(E, S); fo_n = _sub(Tc, E)
    # carry the rest bend plane onto the solved bend plane (keeps the mitt twist sensible)
    bend_r = fo_r if _len(_cross(up_r, fo_r)) > 1e-6 * _len(up_r) * _len(fo_r) else (s * 1., 0., 0.)
    q_up = q_frames(up_r, bend_r, up_n, fo_n)
    q_fo = qm(q_between(qv(q_up, fo_r), fo_n), q_up)
    local[sh] = qm(qc(qsp), q_up)
    local[el] = qm(qc(q_up), q_fo)
    return q_up, q_fo


ARM_SAFE = .46     # min shoulder edge length ratio the arm fallback keeps (deform gate rejects < .45; clips are STEP
                   # keyed at exactly the 4 checked frames, so the margin is not eroded between keys)


def _sleeve_ratio(bones, parents, local, body, side):
    """Min length ratio of the sleeve's shoulder edges under the current local rotations (linear blend skinning)."""
    edges = body.get('sleeve_edges', {}).get(side)
    if not edges:
        return 1.
    qw, pos = _fk_world(bones, parents, local)

    def sk(v, w):
        x = y = z = 0.
        for b, k in w.items():
            r = qv(qw[b], _sub(v, bones[b])); q = pos[b]
            x += k * (q[0] + r[0]); y += k * (q[1] + r[1]); z += k * (q[2] + r[2])
        return (x, y, z)
    return min(_len(_sub(sk(vi, wi), sk(vj, wj))) / d0 for vi, vj, wi, wj, d0 in edges)


def local_rotations(bones, H, kind, clip, t, stance=None, body=None):
    if kind == 'human' and clip in COMBAT_CLIPS:
        # lane-combat-art: the six combat clips (core/combat.py). Combat poses replace the personality stance; the
        # original seven clips never reach this branch, so their keys are unchanged (byte-identical re-export).
        from . import combat
        return combat.local_rotations(bones, H, clip, t, body)
    parents = HUMAN_PARENTS if kind == 'human' else QUAD_PARENTS
    st = stance_def(stance) if kind == 'human' else {}
    r_hold = bool(st and st.get('ik', {}).get('r') and st['ik']['r'][3])
    iside = 'l' if r_hold else 'r'
    eul = base_euler(kind, clip, t, iside)
    if st:
        w = 1.0 if clip == 'idle' else (1.0 if st.get('persist') else (.5 if clip in ('talk', 'sit') else .35))
        for n, off in st.get('fk', {}).items():
            if clip in ('walk', 'run', 'carry', 'sit') and (n.startswith('thigh') or n.startswith('shin') or n.startswith('foot')):
                if not st.get('persist'):
                    continue
            b = eul.get(n, (0., 0., 0.))
            eul[n] = (b[0] + off[0] * w, b[1] + off[1] * w, b[2] + off[2] * w)
        if clip == 'idle':
            breath = .012 * math.sin(t * math.tau * 2)
            b = eul.get('spine', (0., 0., 0.)); eul['spine'] = (b[0] + breath, b[1], b[2])
    local = {n: qe(*eul.get(n, (0., 0., 0.))) for n in parents}
    if st and st.get('ik'):
        qw, pos = _fk_world(bones, parents, local)
        for side, (anchor, off, pole, hold) in st['ik'].items():
            use = clip == 'idle' or hold or (clip == 'talk' and side == 'l' and 'r' in st['ik'] and False)
            if clip in ('carry',) or (clip == 'interact' and side == iside) or (clip == 'talk' and not hold):
                use = False
            if clip in ('walk', 'run') and not hold:
                use = False
            if not use:
                continue
            s = 1 if side == 'l' else -1
            A = _anchor(bones, H, anchor, s, body)
            target = (A[0] + s * off[0] * H, A[1] - off[1] * H, A[2] + off[2] * H)
            if clip == 'sit' and hold:
                # round 12: seated, a held prop rides up above the lap/knees (it hid the hand behind the thighs)
                target = (target[0], target[1] - .04 * H, target[2] + .08 * H)
            target = _push_out(target, body, H)
            pv = POLES[pole]
            pole_r = (s * pv[0], pv[1], pv[2])
            q_up, q_fo = _solve_arm(bones, local, qw, pos, side, target, pole_r)
            if body and body.get('sleeve_edges') and _sleeve_ratio(bones, parents, local, body, side) < ARM_SAFE:
                # round 13 (STEER-5 §3): per-body pose fallback. On extreme bodies (puffy / big belly / child) a
                # front reach can fold the shoulder past what the 16-bone skin can carry (the inner shoulder edge
                # collapsed to 10-35% of its length on the fresh-seed sweep). Move the hand target the least
                # distance toward the relaxed hanging position that keeps the shoulder ring >= ARM_SAFE. Cast
                # stances never trigger this (their shoulders stay above the limit), so they are unchanged.
                relaxed = _anchor(bones, H, 'side', s, body)
                lo, hi = 0., 1.
                for _ in range(8):
                    mid = (lo + hi) / 2.
                    T = _push_out(_add(_mul(target, 1. - mid), _mul(relaxed, mid)), body, H)
                    _solve_arm(bones, local, qw, pos, side, T, pole_r)
                    if _sleeve_ratio(bones, parents, local, body, side) >= ARM_SAFE:
                        hi = mid
                    else:
                        lo = mid
                T = _push_out(_add(_mul(target, 1. - hi), _mul(relaxed, hi)), body, H)
                q_up, q_fo = _solve_arm(bones, local, qw, pos, side, T, pole_r)
            qw, pos = _fk_world(bones, parents, local)
    return local


def skin(bones, parents, local, vertices, weights):
    """Pure-python linear blend skinning (for tests/gates without Blender)."""
    qw, pos = _fk_world(bones, parents, local)
    out = []
    for v, w in zip(vertices, weights):
        acc = [0., 0., 0.]
        for b, wt in w.items():
            p = _add(pos[b], qv(qw[b], _sub(v, bones[b])))
            acc[0] += p[0] * wt; acc[1] += p[1] * wt; acc[2] += p[2] * wt
        out.append(tuple(acc))
    return out
