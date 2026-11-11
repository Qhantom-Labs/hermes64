"""Attack telegraphs for the robotkit bodies: walker poke, brute slam, drone shot.

The clip names, key count and phase frames are the stock robot contract (characters/gen/ext/robot_pose.py: telegraph
wind 1-3 / hold 4-15, attack launch 1 / active 2-6 / recoil 7-9 / settle 10-15, recover shake 1-7 / settle 8-15), so
modules/combat reads these clips unchanged. Only the three key poses per archetype (wind, strike, recoil) differ.
Every other clip (the base and combat sets, move) is the stock robot_pose clip of the archetype's pose family.
Euler XYZ in rig space, radians: +x on the spine leans forward, -x on an upper arm raises it forward."""
import math

TELEGRAPH_CLIPS = ('telegraph', 'attack', 'recover')


def poses(RPO):
    """{archetype: {'wind', 'strike', 'recoil'}} built with the stock `_sym` (mirrored `_lr` entries)."""
    S = RPO._sym
    return {
        # poke: crouch, both prods cocked back at the hip with the tips forward, then a straight two-prod thrust
        'walker': {
            'wind': S(spine=(-.20, 0, 0), head=(.22, 0, 0), pelvis=(-.06, 0, 0),
                      upper_arm_lr=(.95, .45, 0), forearm_lr=(-1.95, 0, 0), hand_lr=(-.10, 0, 0),
                      thigh_lr=(-.42, 0, 0), shin_lr=(.70, 0, 0), foot_lr=(-.26, 0, 0)),
            'strike': S(spine=(.34, 0, 0), head=(-.20, 0, 0), pelvis=(.06, 0, 0),
                        upper_arm_lr=(-1.20, .04, .15), forearm_lr=(-.32, 0, 0), hand_lr=(0, 0, 0),
                        thigh_l=(-.50, 0, 0), shin_l=(.32, 0, 0), thigh_r=(.45, 0, 0), shin_r=(.22, 0, 0), foot_r=(-.12, 0, 0)),
            'recoil': S(spine=(.10, 0, 0), upper_arm_lr=(-.55, .04, .15), forearm_lr=(-.55, 0, 0),
                        thigh_lr=(-.10, 0, 0), shin_lr=(.20, 0, 0)),
        },
        # slam: back arched, both fists straight overhead, bent knees; then fists driven to the floor in front of the feet
        'brute': {
            'wind': S(spine=(-.34, 0, 0), head=(-.22, 0, 0), pelvis=(-.08, 0, 0),
                      upper_arm_lr=(-2.90, -.10, 0), forearm_lr=(-.25, 0, 0),
                      thigh_lr=(-.40, 0, 0), shin_lr=(.68, 0, 0), foot_lr=(-.24, 0, 0)),
            # bow from the hips with bent knees so the fists end at the floor and no shin enters the torso (measured:
            # tools.robots_build clips, hands_bottom_m and distal_in_core_max_m); thigh + shin + foot = -pelvis keeps
            # the soles flat
            'strike': S(spine=(1.28, 0, 0), head=(.22, 0, 0), pelvis=(.50, 0, 0),
                        upper_arm_lr=(-1.78, -.04, 0), forearm_lr=(-.10, 0, 0),
                        thigh_lr=(-.90, 0, 0), shin_lr=(1.26, 0, 0), foot_lr=(-.86, 0, 0)),
            'recoil': S(spine=(.24, 0, 0), upper_arm_lr=(-.40, .08, 0), forearm_lr=(-.35, 0, 0),
                        thigh_lr=(-.18, 0, 0), shin_lr=(.30, 0, 0)),
        },
        # shot: rises with the nose pitched up and the side pods lifted like wings, then snaps nose-down onto the
        # target with the pods dropped; a short kick back after the shot
        'drone': {
            'wind': S(spine=(-.32, 0, 0), head=(-.16, 0, 0), upper_arm_lr=(0, .55, 0), forearm_lr=(-.30, 0, 0), lift=.07),
            'strike': S(spine=(.40, 0, 0), head=(.12, 0, 0), upper_arm_lr=(0, -.28, 0), forearm_lr=(.25, 0, 0), lift=-.01),
            'recoil': S(spine=(-.14, 0, 0), upper_arm_lr=(0, .12, 0), forearm_lr=(-.10, 0, 0), lift=.03),
        },
    }


def key_euler(RPO, archetype, clip, f):
    """The stock `_phase_pose` frame logic for telegraph / attack / recover over this module's key poses."""
    P = poses(RPO)[archetype]
    rest = RPO._rest()
    if clip == 'telegraph':
        if f == 0:
            return rest
        if f <= 3:
            return RPO._blend(rest, P['wind'], f / 3.)
        d = dict(P['wind'])
        tr = .02 * math.sin(f * 2.1)                                # hold with a small tremble
        RPO._add(d, 'spine', (tr, 0, 0)); RPO._add(d, 'head', (0, 0, tr * 2))
        return d
    if clip == 'attack':
        if f == 0:
            return dict(P['wind'])
        if f == 1:
            return RPO._blend(P['wind'], P['strike'], .6)
        if f <= 6:
            d = dict(P['strike'])
            RPO._add(d, 'spine', (.015 * (f - 2), 0, 0))
            return d
        if f <= 9:
            return RPO._blend(P['strike'], P['recoil'], (f - 6) / 3.)
        return RPO._blend(P['recoil'], rest, (f - 9) / 6.)
    if clip == 'recover':
        if f <= 7:
            amp = .16 * (1. - f / 8.)
            d = RPO._blend(P['recoil'], rest, f / 7.)
            RPO._add(d, 'head', (0, amp * math.sin(f * 2.4), amp * math.sin(f * 1.9)))
            RPO._add(d, 'spine', (0, amp * .5 * math.sin(f * 2.4 + 1.), 0))
            return d
        return rest
    raise ValueError('not a telegraph clip: ' + str(clip))


def local_rotations(RPO, PO, m, clip, t):
    """-> ({bone: (w, x, y, z)}, lift_m), the signature of ext/robot_pose.local_rotations."""
    if clip not in TELEGRAPH_CLIPS:
        return RPO.local_rotations(m, clip, t)
    d = key_euler(RPO, m.archetype, clip, RPO.frame_of(t))
    lift = float(d.get('lift', 0.)) * m.params['height'] if getattr(m, 'hover', 0.) > 0 else 0.
    return {n: PO.qe(*d.get(n, (0., 0., 0.))) for n in m.parents}, lift
