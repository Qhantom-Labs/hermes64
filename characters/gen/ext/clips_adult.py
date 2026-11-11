"""Clips of the n64_adult family (rig human16_v3), 16 keys at 15 fps like every character clip.

sample(a, clip, key, metrics) -> (local rotations {bone: (w, x, y, z)} in the generator's Z-up space, lift in metres).
The assembler grounds the lowest vertex each key and then adds `lift`, so a positive lift is a real flight phase.
Clips not authored here fall through to core/pose.local_rotations (talk, sit, carry, interact and the six combat
clips), which only need the 16 bone names.

run and walk are authored as a planted-foot cycle, not as sine swings:
  * each leg has a phase p in [0, 16): p = 0 is its foot strike, the other leg is 8 keys behind;
  * while the foot is down it travels backward under the hip at exactly the clip's ground speed (STRIDE_MPS / FPS per
    key), pivoting on the heel at strike and on the toe at push-off; a two-bone solve in the sagittal plane gives thigh
    and shin, so the planted foot does not slide when the game plays the clip at speed / stride;
  * the run leaves the ground: toe-off is before key 5 of each step, the next strike is at key 8, so keys 5, 6, 7 of
    each step are flight with a ballistic hip height (returned as lift over the grounded pose);
  * the swing foot is keyed as an ankle path (behind/ahead of the hip, height over the ground, foot pitch) and solved
    the same way: heel to the seat, knee drive, reach, then it retreats at ground speed into the strike;
  * distances are in standing hip heights and the ground speed scales with the leg (stride_mps), so a short-legged
    build takes shorter steps instead of sliding;
  * arms counter the legs (elbows near 90 degrees in the run), the shoulders counter the pelvis, the head stays level.
Angles: X negative swings a hanging limb forward (-Y); positive shin X bends the knee (core/pose.base_euler).
"""
import math

try:
    from . import pose as PO
except ImportError:
    from core import pose as PO

FPS = 15.
KEYS = 16
STEP = 8
# ground speed at playback rate 1 (the runtime plays the clip at speed / stride); also written into clips.json
STRIDE_MPS = {'walk': 1.1, 'run': 2.2}
RAD = math.pi / 180.

# run -----------------------------------------------------------------------------------------------------------------
RUN = {
    'swing_angles': True,
    'toe0': -.497,                       # toe reference at strike, in hip heights ahead of the hip (- = forward)
    'stance': 4,                         # last planted key of a step (toe-off follows before key 5)
    'pitch': [-6., 0., 4., 18., 42.],    # foot pitch per planted key (deg; - = toe up on the heel, + = heel up on the toe)
    # hip height per step key as a fraction of the standing hip height: sink after the strike, drive, flight arc
    'hip': [.975, .962, .973, 1.000, 1.040, 1.060, 1.065, 1.030],
    # swing keys 5..15 as angles (deg, world): thigh (- = forward), knee flexion, foot pitch (+ = toe down): the heel
    # comes to the seat, the knee drives up to near horizontal, the shin swings out and the foot paws back to the strike
    'swing': {5: (18., 48., 70.), 6: (6., 94., 88.), 7: (-14., 108., 80.), 8: (-36., 106., 60.), 9: (-56., 98., 40.),
              10: (-68., 92., 25.), 11: (-72., 78., 14.), 12: (-68., 60., 4.), 13: (-58., 42., -4.),
              14: (-50., 24., -10.), 15: (-43., 11., -12.)},
    'lean': (8.5, 12.5),                   # pelvis, spine forward pitch (deg): the torso leans about 15 degrees
    'yaw': (7., 13.),                    # pelvis yaw amplitude, shoulder counter-yaw amplitude (deg, world)
    'arm': (26., 44., -78., 10.),          # upper arm: bias, swing amplitude; forearm: mean bend, bend swing (deg)
    'arm_in': (-3., 2.),                 # upper arm brought in (deg), forearm turned across the body (deg)
    'peak': 4.5,                         # leg phase at which the same-side arm is furthest forward
}
# walk ----------------------------------------------------------------------------------------------------------------
WALK = {
    # walk swing keys 10..15: ankle behind (+) / ahead (-) of the hip and clearance of the lowest point of the sole over
    # the ground, both in hip heights; foot pitch (deg, world, + = toe down)
    'toe0': -.660,
    'stance': 9,
    'pitch': [-24., -10., 0., 0., 0., 2., 9., 20., 32., 46.],
    'hip': [.990, .968, .972, .988, .996, .996, .994, .992],   # gives under the load, vaults over the passing pose
    'swing': {10: (.360, .060, 52.), 11: (.240, .160, 46.), 12: (.050, .230, 26.), 13: (-.150, .140, 4.),
              14: (-.330, .080, -16.), 15: (-.400, .050, -26.)},
    'lean': (1.5, 2.),
    'yaw': (6., 9.),
    'arm': (4., 25., -16., 14.),
    'arm_in': (5., 4.),
    'peak': 7.5,
}
CYCLES = {'run': RUN, 'walk': WALK}
_CACHE = {}


def _foot_model(a):
    """Rest leg geometry in the sagittal plane (y back, z up), from the built body: segment lengths and rest angles,
    toe and heel pivots relative to the ankle, and the boot vertices used to find the grounded height."""
    key = id(a)
    if key in _CACHE:
        return _CACHE[key]
    hip, knee, ank = a.bones['thigh_l'], a.bones['shin_l'], a.bones['foot_l']
    d1 = (knee[1] - hip[1], knee[2] - hip[2])
    d2 = (ank[1] - knee[1], ank[2] - knee[2])
    idx = list(a.parts['boot_l'])
    low = min(a.vertices[i][2] for i in idx)
    sole = [a.vertices[i] for i in idx if a.vertices[i][2] < low + .012]
    toe = min(v[1] for v in sole)
    heel = max(v[1] for v in sole)
    m = {'l1': math.hypot(*d1), 'a1': math.atan2(d1[1], d1[0]), 'l2': math.hypot(*d2), 'a2': math.atan2(d2[1], d2[0]),
         'toe': (ank[1] - toe, ank[2] - low), 'heel': (ank[1] - heel, ank[2] - low), 'hip': hip[2],
         'outline': [(a.vertices[i][1] - ank[1], a.vertices[i][2] - ank[2]) for i in idx
                     if a.weights[i].get('foot_l', 0.) > .99],
         'boots': list(a.parts['boot_l']) + list(a.parts['boot_r'])}
    _CACHE.clear()
    _CACHE[key] = m
    return m


def _rot(v, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _wrap(x):
    while x > math.pi:
        x -= math.tau
    while x < -math.pi:
        x += math.tau
    return x


HIP_REF = .804        # standing hip height of the reference hero build (m): STRIDE_MPS is its ground speed


def stride_mps(a, clip):
    """Ground speed of the clip at playback rate 1 for this body (scales with the leg)."""
    return STRIDE_MPS[clip] * _foot_model(a)['hip'] / HIP_REF


def _ank_z(M, psi):
    """Height of the ankle over the ground when the boot is pitched by psi and its lowest vertex is on the ground."""
    return -min(_rot(v, psi)[1] for v in M['outline'])


def _planted(M, cyc, clip, p):
    """Ankle (y, height over the ground) and foot pitch (rad) of a planted foot at integer phase p."""
    ref = (cyc['toe0'] + STRIDE_MPS[clip] / HIP_REF / FPS * p) * M['hip']   # the toe of a flat foot, relative to the hip
    psi = cyc['pitch'][p] * RAD
    if psi >= 0.:
        off = _rot(M['toe'], psi)                               # pivot on the toe
        return (ref + off[0], _ank_z(M, psi)), psi
    heel_y = ref + (M['toe'][0] - M['heel'][0])
    off = _rot(M['heel'], psi)                                  # pivot on the heel
    return (heel_y + off[0], _ank_z(M, psi)), psi


def _solve(M, target):
    """Two-bone solve, knee forward. target: ankle relative to the hip (y, z). -> thigh angle (world), knee flexion."""
    D = math.hypot(*target)
    reach = (M['l1'] + M['l2']) * .999
    if D > reach:
        target = (target[0] * reach / D, target[1] * reach / D)
        D = reach
    g = math.atan2(target[1], target[0])
    c = (M['l1'] ** 2 + D * D - M['l2'] ** 2) / (2. * M['l1'] * D)
    t1 = g - math.acos(max(-1., min(1., c)))
    knee = (M['l1'] * math.cos(t1), M['l1'] * math.sin(t1))
    t2 = math.atan2(target[1] - knee[1], target[0] - knee[0])
    th = _wrap(t1 - M['a1'])
    return th, _wrap(t2 - M['a2']) - th


def _cycle(a, clip, key, cycles=None):
    cyc = (cycles or CYCLES)[clip]                              # another body family may pass its own tuning (clips_tall_v3)
    M = _foot_model(a)
    hip0 = M['hip']
    reach = (M['l1'] + M['l2']) * .992
    phase = {'l': key % KEYS, 'r': (key + STEP) % KEYS}
    planted = {s: _planted(M, cyc, clip, p) for s, p in phase.items() if p <= cyc['stance']}
    hip = cyc['hip'][key % STEP] * hip0
    for (ank, _psi) in planted.values():                        # never ask a planted leg to reach further than it can
        hip = min(hip, ank[1] + math.sqrt(max(1e-6, reach * reach - ank[0] * ank[0])))
    hip -= cyc.get('dip', (0.,) * STEP)[key % STEP] * hip0
    lean_p, lean_s = cyc['lean'][0] * RAD, cyc['lean'][1] * RAD
    w = math.cos(math.tau * (phase['l'] - cyc['peak']) / KEYS)   # +1 when the left arm is furthest forward
    yaw_p = cyc['yaw'][0] * RAD * w
    yaw_s = -cyc['yaw'][1] * RAD * w
    eul = {'pelvis': (lean_p, 0., yaw_p), 'spine': (lean_s, 0., yaw_s - yaw_p),
           'head': (-.80 * (lean_p + lean_s), 0., -yaw_s)}
    for s, sg in (('l', 1.), ('r', -1.)):
        p = phase[s]
        if s in planted:
            ank, psi = planted[s]
            th, kn = _solve(M, (ank[0], ank[1] - hip))
            foot = psi - th - kn
        else:
            y, clr, psi = cyc['swing'][p]
            psi *= RAD
            if cyc.get('swing_angles'):
                th, kn = y * RAD, clr * RAD
            else:
                hz = clr * hip0 + _ank_z(M, psi)
                th, kn = _solve(M, (y * hip0, hz - hip))
            foot = psi - th - kn
        eul['thigh_' + s] = (th - lean_p, 0., 0.)
        eul['shin_' + s] = (kn, 0., 0.)
        eul['foot_' + s] = (foot, 0., 0.)
        ws = w if s == 'l' else -w
        bias, amp, bend, bsw = (v * RAD for v in cyc['arm'])
        inn, across = (v * RAD for v in cyc['arm_in'])
        eul['upper_arm_' + s] = (bias - amp * ws - (lean_p + lean_s), sg * inn, -sg * across)   # world swing: the lean is taken out
        eul['forearm_' + s] = (bend - bsw * ws, 0., 0.)
    local = {n: PO.qe(*eul.get(n, (0., 0., 0.))) for n in a.bones}
    lift = 0.
    if not planted:                                             # flight: the authored hip height over the grounded pose
        qw, pos = PO._fk_world(a.bones, a.parents, local)
        low = 1e9
        for i in M['boots']:
            z = 0.
            tot = 0.
            for b, wt in a.weights[i].items():
                z += wt * (pos[b][2] + PO.qv(qw[b], PO._sub(a.vertices[i], a.bones[b]))[2])
                tot += wt
            low = min(low, z / tot)
        lift = max(0., hip - (pos['thigh_l'][2] + pos['thigh_r'][2]) / 2. + low)
    return local, lift


AUTHORED = {'run': lambda a, key: _cycle(a, 'run', key), 'walk': lambda a, key: _cycle(a, 'walk', key)}


def sample(a, clip, key, metrics=None):
    fn = AUTHORED.get(clip)
    if fn is not None:
        return fn(a, key)
    H = a.params.get('height', 1.)
    return PO.local_rotations(a.bones, H, a.kind, clip, key / FPS, 'neutral', metrics), 0.
