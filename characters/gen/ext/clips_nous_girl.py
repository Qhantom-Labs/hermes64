"""Clips of nous_girl (lane CAST2), rig human16_v1, 16 keys at 15 fps (the base family's clip contract).

sample(a, clip, key, metrics) -> (local rotations {bone: (w, x, y, z)}, lift in metres), as ext/clips_tall_v3.sample.
seat(a, posed) -> the root translation (x, y, z) in metres of the seated clips (see SEAT).

  captive           seated, wrists over the chair's arm cuffs, breathing; head a little down
  captive_look      the same seat; the head comes up and looks up to her left, then returns (loop)
  captive_struggle  the same seat; the shoulders twist and the forearms pull against the cuffs, small (loop)
  idle              standing, plumb and left-right symmetric (the hero idle without the chin-down), breathing
  walk              the planted-foot cycle of ext/clips_adult.py solved for her leg lengths (the hero's tables)
  wave              standing; the right hand is raised and waved, the head tips (the relieved wave of the ending)
  talk              the shared core talk clip

SEATED CLIPS AND THE CHAIR. The captive chair (cyber kit, cyroom.chair kind=captive; read-only for this lane) has its
origin at the floor centre and faces -y (glTF +Z). Measured from its GLB, metres: seat pad top SEAT['top'], pad front
edge y = SEAT['front'], back rest front face y = SEAT['back'], arm rests |x| >= SEAT['arm_x'] with their top at
SEAT['arm_top'], a cuff plate centred (+-.36, -.16, .645), base plate top SEAT['plate'].
The seated clips carry a root translation such that HER ORIGIN IS THE CHAIR'S ORIGIN: place her at the chair's
position with the chair's yaw and she is seated; no other offset is needed. The translation is solved once, on key 0
of `captive`, and is the same for every seated key (the pelvis and thighs do not move in these clips):
  z  the lowest point of hips and thighs rests SEAT['gap'] above the pad top
  y  the more forward of two limits: the rear of the jacket SEAT['back_gap'] in front of the back rest; every leg
     vertex below the pad top SEAT['front_gap'] in front of the pad's front edge (her thighs are shorter than the pad
     is deep, so this second limit is the one that holds)
She leans back (SIT['lean']) so that the upper back reaches the back rest.

The locomotion bake (lane CHARS3) is not on this branch: walk is the retargeted cycle on rig human16_v1.
"""
import math

from . import clips_adult as CA
from . import clips_tall_v3 as CL
from . import pose as PO

FPS = 15.
KEYS = 16
STANCE = 'neutral'
CLIPS = ['captive', 'captive_look', 'captive_struggle', 'idle', 'talk', 'walk', 'wave']
SEATED = ('captive', 'captive_look', 'captive_struggle')
EXPRESSION = {'captive': 'worried', 'captive_look': 'worried', 'captive_struggle': 'worried', 'idle': 'neutral',
              'talk': 'talk_a', 'walk': 'neutral', 'wave': 'smile'}
SEAT = {'top': .52, 'front': -.32, 'back': .23, 'arm_x': .31, 'arm_top': .64, 'cuff': (.36, -.16, .645), 'plate': .10,
        'gap': .004, 'back_gap': .012, 'front_gap': .012}
# seated pose, radians (Blender XYZ euler, as core/pose.qe). x < 0 swings a hanging limb forward / leans a spine back.
# The arm values put the hand over the cuff plate of the arm rest (solved by search against the chair's numbers).
SIT = {'lean': -.10, 'spine': -.06, 'head': .20, 'thigh': -1.34, 'shin': 1.02, 'foot': .10, 'knee_out': .05,
       'upper_arm': (.25, -.10, .25), 'forearm': (-1.00, 0., 0.), 'hand': (-.30, 0., 0.)}
ARM_IN = .10
TOE_OUT = .16
# +y lifts the RIGHT arm out to her side (a negative y swings it across the chest and through the torso). Solved by search:
# no crossing with head, hair, collar or legs, and the rig kit's connectivity check passes (an upper arm lift of .95 rad or
# more opens a gap over 3 mm between the sleeve and the torso, so the upper arm stays at .78 and the elbow does the rest).
WAVE = {'upper_arm': (-.25, .72, 0.), 'forearm': (-.20, 1.75, 0.), 'swing': .28, 'head_tip': .07}


def _q(a, e):
    return {n: PO.qe(*e.get(n, (0., 0., 0.))) for n in a.parents}


def _sit(a, key, mode):
    t = key / float(KEYS)
    breath = math.sin(t * math.tau)
    s2 = math.sin(2. * t * math.tau)
    look = (.5 - .5 * math.cos(t * math.tau)) if mode == 'look' else 0.          # 0 -> 1 -> 0
    tw = math.sin(t * math.tau) if mode == 'struggle' else 0.
    e = {'pelvis': (SIT['lean'], 0., 0.),
         'spine': (SIT['spine'] + .012 * breath + .03 * abs(tw) + .10 * look, 0., .10 * tw),
         'head': (SIT['head'] - .010 * breath - .50 * look - .06 * abs(tw), 0., -.22 * tw + .16 * look)}
    for s, sg in (('l', 1), ('r', -1)):
        ux, uy, uz = SIT['upper_arm']
        fx, fy, fz = SIT['forearm']
        # struggle: each wrist pulls UP against its cuff in turn (never down: the arm rest is 1.8 cm under the hand)
        pull = (.5 + .5 * s2 * sg) if mode == 'struggle' else 0.          # 0..1, the sides alternate
        e['upper_arm_' + s] = (ux - .008 * abs(breath) - .07 * pull - .03 * abs(tw), sg * uy, sg * uz)
        # look: the spine comes forward .10 rad, which lowers the hands 1.8 cm; the elbows bend by as much
        e['forearm_' + s] = (fx - .12 * pull - .04 * abs(tw) - .12 * look, sg * fy, sg * fz)
        hx, hy, hz = SIT['hand']
        e['hand_' + s] = (hx, sg * hy, sg * hz)
        e['thigh_' + s] = (SIT['thigh'] - SIT['lean'], 0., sg * SIT['knee_out'])
        # struggle: the feet kick forward in turn (never back: the calf is 1.2 cm in front of the seat pad)
        e['shin_' + s] = (SIT['shin'] - (.06 * (.5 - .5 * s2 * sg) if mode == 'struggle' else 0.), 0., 0.)
        e['foot_' + s] = (SIT['foot'], 0., 0.)
    return _q(a, e), 0.


def _stand(breath):
    e = {'spine': (.010 * breath, 0., 0.), 'head': (-.012 * breath, 0., 0.)}
    for s, sg in (('l', 1), ('r', -1)):
        e['upper_arm_' + s] = (-.05, sg * (ARM_IN - .006 * breath), sg * .045)
        e['forearm_' + s] = (-.20 - .01 * breath, 0., 0.)
        e['thigh_' + s] = (0., 0., sg * TOE_OUT)
    return e


def _idle(a, key):
    return _q(a, _stand(math.sin(key / float(KEYS) * math.tau))), 0.


def _wave(a, key):
    t = key / float(KEYS)
    w = math.sin(2. * t * math.tau)                          # two waves per loop
    e = _stand(math.sin(t * math.tau))
    e['head'] = (-.06, WAVE['head_tip'], 0.)
    ux, uy, uz = WAVE['upper_arm']
    fx, fy, fz = WAVE['forearm']
    e['upper_arm_r'] = (ux, uy + .06 * w, uz)
    e['forearm_r'] = (fx, fy + WAVE['swing'] * w, fz)
    return _q(a, e), 0.


CYCLES = {'walk': dict(CL.CYCLES['walk'])}
CYCLES['walk']['arm_in'] = (1.5, 2.)          # the hero's (5, 4) passes her hand through the thigh: her hips are as wide, her arms shorter


def stride_mps(a, clip):
    return CA.stride_mps(a, clip)


AUTHORED = {'captive': lambda a, k: _sit(a, k, 'still'), 'captive_look': lambda a, k: _sit(a, k, 'look'),
            'captive_struggle': lambda a, k: _sit(a, k, 'struggle'), 'idle': _idle, 'wave': _wave,
            'walk': lambda a, k: CA._cycle(a, 'walk', k, CYCLES)}


def sample(a, clip, key, metrics=None):
    fn = AUTHORED.get(clip)
    if fn is not None:
        return fn(a, key)
    H = a.params.get('height', 1.)
    return PO.local_rotations(a.bones, H, a.kind, clip, key / FPS, STANCE, metrics), 0.


def _ids(a, prefixes):
    return [vi for part, lst in a.parts.items() if part.startswith(tuple(prefixes)) for vi in lst]


def seat(a, posed):
    """Root translation (x, y, z) m from the posed vertices of `captive` key 0 (root at the origin)."""
    def upper(vi):          # carried by the pelvis, the spine or a thigh for more than half: what sits on the pad
        return sum(w for b, w in a.weights[vi].items() if b in ('pelvis', 'spine') or b.startswith('thigh')) > .5
    hips = [vi for vi in _ids(a, ('torso', 'trouser_')) if upper(vi)]
    legs = [vi for vi in _ids(a, ('trouser_', 'boot_')) if not upper(vi)]
    under = min(float(posed[vi][2]) for vi in hips)
    z = SEAT['top'] + SEAT['gap'] - under
    y_back = SEAT['back'] - SEAT['back_gap'] - max(float(posed[vi][1]) for vi in hips)
    low = [float(posed[vi][1]) for vi in legs if float(posed[vi][2]) + z < SEAT['top']]
    y_front = (SEAT['front'] - SEAT['front_gap'] - max(low)) if low else y_back
    return (0., min(y_back, y_front), z)
