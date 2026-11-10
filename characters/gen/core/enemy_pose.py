"""Enemy clips (lane-combat-art). Pure Python 3.9, no Blender.

Seven clips per archetype, one per FSM state of the STORY 1.2 enemy templates (idle, approach, telegraph, attack,
recover, hurt, dead): idle, move, telegraph, attack, recover, hurt, death. Same held convention as the shared rig:
16 STEP keys over 1 s (key f at t = f / 15). Loops (idle, move) are periodic in t, so key 15 == key 0 and the
displayed cycle is keys 0-14 (15 frames).

Rotations are world-aligned local quaternions (every enemy bone rests pointing +Z, like core/pose.py). No root
motion: the root never moves; the body bone (hips / body) carries only a VERTICAL offset = grounding (lowest vertex on
the floor) + the authored hop/lift height. Nothing translates horizontally; the runtime moves the actor.

Signs (world axes, -Y forward): X>0 pitches a forward-pointing part down (head, chest) / a downward limb backward;
X<0 swings a downward limb forward; Y rolls about the forward axis (Y>0: toward the character's left, +X, for an
upward part); Z>0 turns toward the left.
"""
import math

from . import pose as PO
from . import enemies as EN

ENEMY_CLIPS = ['idle', 'move', 'telegraph', 'attack', 'recover', 'hurt', 'death']
FSM_CLIP = {'idle': 'idle', 'approach': 'move', 'telegraph': 'telegraph', 'attack': 'attack', 'recover': 'recover',
            'hurt': 'hurt', 'dead': 'death'}
LOOP = {'idle': True, 'move': True}
BODY_BONE = {'cairn_dasher': 'hips', 'reed_warden': 'body'}
FACE_CELLS = {'cols': 2, 'rows': 2, 'cell': 0, 'clip_cells': {'telegraph': 1, 'attack': 1, 'hurt': 2, 'death': 3},
              'cells': {'0': 'eyes', '1': 'eyes_flare', '2': 'eyes_hurt', '3': 'eyes_closed'}}

PHASES = {
    'cairn_dasher': {
        'idle': {'loop': True, 'phases': {'loop': [0, 15]}},
        'move': {'loop': True, 'phases': {'loop': [0, 15]}, 'gait': 'heavy diagonal walk, 1 cycle per second'},
        'telegraph': {'loop': False, 'phases': {'rear': [1, 3], 'paw_scrape': [4, 12], 'hold': [13, 15]},
                      'telegraph_peak_frame': 4, 'hold_frames': [13, 15]},
        'attack': {'loop': False, 'phases': {'launch': [1, 1], 'active': [2, 8], 'brake': [9, 11], 'settle': [12, 15]},
                   'hit_window': {'frames': [2, 8], 'start_s': round(2 / 15., 6), 'end_s': round(9 / 15., 6)},
                   'note': 'melee_dash_v1 commits its bounded dash during the active window; the clip charges in place'},
        'recover': {'loop': False, 'phases': {'shake': [1, 6], 'settle': [7, 15]}},
        'hurt': {'loop': False, 'phases': {'impact': [1, 3], 'recover': [4, 15]}},
        'death': {'loop': False, 'phases': {'impact': [1, 2], 'collapse': [3, 10], 'down_hold': [11, 15]}},
    },
    'reed_warden': {
        'idle': {'loop': True, 'phases': {'loop': [0, 15]}},
        'move': {'loop': True, 'phases': {'loop': [0, 15]}, 'gait': 'two hops per second (period 7.5 keys)'},
        'telegraph': {'loop': False, 'phases': {'squash_fan': [1, 3], 'hold_tremble': [4, 15]},
                      'telegraph_peak_frame': 3, 'hold_frames': [4, 15]},
        'attack': {'loop': False, 'phases': {'spring': [1, 2], 'active': [3, 5], 'recoil': [6, 8], 'settle': [9, 15]},
                   'hit_window': {'frames': [3, 5], 'start_s': round(3 / 15., 6), 'end_s': round(6 / 15., 6)},
                   'lob_socket': {'node': 'attach_lob', 'release_frame': 3,
                                  'note': 'optional: a runtime that wants a lobbed burr spawns it here at the release frame'}},
        'recover': {'loop': False, 'phases': {'shake': [1, 6], 'settle': [7, 15]}},
        'hurt': {'loop': False, 'phases': {'impact': [1, 3], 'recover': [4, 15]}},
        'death': {'loop': False, 'phases': {'impact': [1, 2], 'collapse': [3, 9], 'down_hold': [10, 15]}},
    },
}


def frame_of(t):
    return max(0, min(15, int(round(t * 15))))


def _lerp(a, b, w):
    return tuple(a[i] + (b[i] - a[i]) * w for i in range(3))


def _blend(a, b, w):
    out = {}
    for k in set(a) | set(b):
        if k == 'lift':
            out[k] = a.get('lift', 0.) + (b.get('lift', 0.) - a.get('lift', 0.)) * w
        else:
            out[k] = _lerp(a.get(k, (0., 0., 0.)), b.get(k, (0., 0., 0.)), w)
    return out


def _add(d, k, v):
    b = d.get(k, (0., 0., 0.))
    d[k] = (b[0] + v[0], b[1] + v[1], b[2] + v[2])


# ------------------------------------------------------------------ cairn dasher
D_IDLE = {'neck': (.06, 0, 0), 'head': (.04, 0, 0), 'tail': (.25, 0, 0)}
D_REAR = {'hips': (-.42, 0, 0), 'chest': (-.06, 0, 0), 'neck': (-.18, 0, 0), 'head': (-.28, 0, 0),
          'leg_bl': (.30, 0, 0), 'paw_bl': (.30, 0, 0), 'leg_br': (.30, 0, 0), 'paw_br': (.30, 0, 0),
          'leg_fl': (-.55, 0, 0), 'paw_fl': (1.05, 0, 0), 'leg_fr': (-.35, 0, 0), 'paw_fr': (.90, 0, 0),
          'tail': (.90, 0, 0), 'cairn_low': (-.10, 0, 0), 'cairn_top': (-.18, 0, 0)}
D_RAM = {'hips': (.06, 0, 0), 'chest': (.22, 0, 0), 'neck': (.42, 0, 0), 'head': (.30, 0, 0),
         'leg_bl': (-.42, 0, 0), 'paw_bl': (.70, 0, 0), 'leg_br': (-.42, 0, 0), 'paw_br': (.70, 0, 0),
         'leg_fl': (-.34, -.10, 0), 'paw_fl': (.45, 0, 0), 'leg_fr': (-.34, .10, 0), 'paw_fr': (.45, 0, 0),
         'tail': (.95, 0, 0), 'cairn_low': (.06, 0, 0), 'cairn_top': (.10, 0, 0)}
D_EXTEND = {'hips': (.06, 0, 0), 'chest': (.26, 0, 0), 'neck': (.30, 0, 0), 'head': (.24, 0, 0),
            'leg_fl': (-.70, 0, 0), 'paw_fl': (.20, 0, 0), 'leg_fr': (-.55, 0, 0), 'paw_fr': (.15, 0, 0),
            'leg_bl': (.62, 0, 0), 'paw_bl': (-.30, 0, 0), 'leg_br': (.50, 0, 0), 'paw_br': (-.25, 0, 0),
            'tail': (.95, 0, 0), 'cairn_low': (-.05, 0, 0), 'cairn_top': (-.14, 0, 0), 'lift': .05}
D_GATHER = {'hips': (.12, 0, 0), 'chest': (.30, 0, 0), 'neck': (.28, 0, 0), 'head': (.22, 0, 0),
            'leg_fl': (.30, 0, 0), 'paw_fl': (-.30, 0, 0), 'leg_fr': (.38, 0, 0), 'paw_fr': (-.35, 0, 0),
            'leg_bl': (-.48, 0, 0), 'paw_bl': (.55, 0, 0), 'leg_br': (-.40, 0, 0), 'paw_br': (.48, 0, 0),
            'tail': (.80, 0, 0), 'cairn_low': (.06, 0, 0), 'cairn_top': (.14, 0, 0)}
D_BRAKE = {'hips': (-.10, 0, 0), 'chest': (-.12, 0, 0), 'neck': (-.06, 0, 0), 'head': (-.18, 0, 0),
           'leg_fl': (-.55, 0, 0), 'paw_fl': (.25, 0, 0), 'leg_fr': (-.50, 0, 0), 'paw_fr': (.22, 0, 0),
           'leg_bl': (-.35, 0, 0), 'paw_bl': (.55, 0, 0), 'leg_br': (-.30, 0, 0), 'paw_br': (.50, 0, 0),
           'tail': (.45, 0, 0), 'cairn_low': (.12, 0, 0), 'cairn_top': (.22, 0, 0)}
D_HURT = {'hips': (-.08, .10, 0), 'chest': (-.18, .12, .08), 'neck': (-.25, 0, .12), 'head': (-.30, .10, .25),
          'tail': (1.0, 0, 0), 'cairn_low': (-.16, -.12, 0), 'cairn_top': (-.28, -.20, 0),
          'leg_fl': (-.20, -.10, 0), 'leg_fr': (-.15, .10, 0)}
D_KNEEL = {'chest': (.25, 0, 0), 'neck': (.30, 0, 0), 'head': (.25, 0, 0),
           'leg_fl': (.70, 0, 0), 'paw_fl': (-1.30, 0, 0), 'leg_fr': (.70, 0, 0), 'paw_fr': (-1.30, 0, 0),
           'leg_bl': (-.20, 0, 0), 'paw_bl': (.35, 0, 0), 'leg_br': (-.20, 0, 0), 'paw_br': (.35, 0, 0),
           'tail': (.20, 0, 0), 'cairn_low': (.10, 0, 0), 'cairn_top': (.20, 0, 0)}
D_DOWN = {'hips': (0, 1.45, 0), 'chest': (.05, .08, 0), 'neck': (.25, 0, .10), 'head': (.10, .20, .20),
          'leg_fl': (-.35, .20, 0), 'paw_fl': (.30, 0, 0), 'leg_fr': (-.15, -.30, 0), 'paw_fr': (.45, 0, 0),
          'leg_bl': (.30, .25, 0), 'paw_bl': (-.20, 0, 0), 'leg_br': (.45, -.35, 0), 'paw_br': (-.10, 0, 0),
          'tail': (-.10, 0, .30), 'cairn_low': (0, .08, .04), 'cairn_top': (0, .22, .10)}


def _dasher_idle(t):
    w = math.sin(t * math.tau); w2 = math.sin(t * math.tau * 2)
    d = dict(D_IDLE)
    _add(d, 'chest', (.02 * w2, 0, 0)); _add(d, 'hips', (0, .03 * w, 0))
    _add(d, 'neck', (.05 * w, 0, 0)); _add(d, 'head', (0, 0, .10 * w)); _add(d, 'tail', (0, 0, .30 * w2))
    _add(d, 'cairn_low', (.015 * math.sin(t * math.tau + .5), 0, 0)); _add(d, 'cairn_top', (.03 * math.sin(t * math.tau + 1.), 0, 0))
    return d


def _dasher_move(t):
    w = math.sin(t * math.tau); w2 = math.sin(t * math.tau * 2); c = math.cos(t * math.tau)
    d = {}
    amp = .42
    for limb, sg in (('fl', 1), ('br', 1), ('fr', -1), ('bl', -1)):
        d['leg_' + limb] = (-amp * sg * w, 0, 0)
        # the swinging leg lifts its hoof (knee/hock folds while it moves forward)
        lift = max(0., sg * c)
        d['paw_' + limb] = (amp * .55 * sg * w + .55 * lift * (1 if limb[0] == 'f' else -.6) * (1 if limb[0] == 'f' else 1), 0, 0)
    d['hips'] = (0, .07 * w, 0); d['chest'] = (.03 * w2, -.05 * w, .05 * w)
    d['neck'] = (.10 + .06 * w2, 0, 0); d['head'] = (.06 * w2, 0, -.06 * w)
    d['tail'] = (.35, 0, .30 * w)
    d['cairn_low'] = (.04 * math.sin(t * math.tau * 2 - .8), .05 * math.sin(t * math.tau - .6), 0)
    d['cairn_top'] = (.08 * math.sin(t * math.tau * 2 - 1.4), .10 * math.sin(t * math.tau - 1.2), 0)
    d['lift'] = 0.
    return d


def _dasher_telegraph(f):
    if f == 0:
        return _dasher_idle(0.)
    if f <= 3:
        d = _blend(_dasher_idle(0.), D_REAR, {1: .5, 2: 1., 3: 1.}[f])
        if f == 3:
            d = _blend(D_REAR, D_RAM, .5)
        return d
    d = dict(D_RAM)
    if 4 <= f <= 12:
        # front-left hoof scrapes the ground twice; the cairn rattles every key
        scrape = {4: 0., 5: 1., 6: .3, 7: -.3, 8: 1., 9: .3, 10: -.3, 11: .7, 12: 0.}[f]
        _add(d, 'leg_fl', (.80 * scrape, 0, 0)); _add(d, 'paw_fl', (-.45 * max(0., scrape) + .55 * max(0., -scrape), 0, 0))
        r = .07 if f % 2 else -.07
        _add(d, 'cairn_low', (0, r, 0)); _add(d, 'cairn_top', (0, -1.6 * r, 0))
        _add(d, 'head', (0, 0, .06 * (1 if f % 2 else -1)))
    return d


def _dasher_attack(f):
    if f == 0:
        return dict(D_RAM)
    if f == 1:
        return _blend(D_RAM, D_EXTEND, .7)
    if 2 <= f <= 8:
        return dict(D_EXTEND if f % 2 == 0 else D_GATHER)
    if f <= 11:
        return _blend(D_GATHER, D_BRAKE, {9: .6, 10: 1., 11: 1.}[f])
    return _blend(D_BRAKE, _dasher_idle(0.), {12: .35, 13: .65, 14: .9, 15: 1.}[f])


def _dasher_recover(f):
    base = _dasher_idle(0.)
    if f == 0:
        return dict(D_BRAKE)
    if f <= 6:
        d = _blend(D_BRAKE, base, .3)
        _add(d, 'neck', (.25, 0, 0)); _add(d, 'head', (.15, 0, (.35 if f % 2 else -.35) * (1 - f / 8.)))
        _add(d, 'cairn_top', (0, (.10 if f % 2 else -.10) * (1 - f / 7.), 0))
        return d
    return _blend(_blend(D_BRAKE, base, .3), base, min(1., (f - 6) / 7.))


def _dasher_hurt(f):
    w = [0., 1., 1., .85, .70, .55, .42, .30, .20, .12, .06, .02, 0., 0., 0., 0.][f]
    return _blend(_dasher_idle(0.), D_HURT, w)


def _dasher_death(f):
    T = [(0, 0, 0.), ('i', 'h', 1.), ('h', 'h', 0.), ('h', 'k', .5), ('k', 'k', 0.), ('k', 'k', 0.), ('k', 'd', .30),
         ('k', 'd', .60), ('k', 'd', .85), ('k', 'd', 1.), ('d', 'd', 0.), ('d', 'd', 0.), ('d', 'd', 0.), ('d', 'd', 0.),
         ('d', 'd', 0.), ('d', 'd', 0.)]
    P = {0: _dasher_idle(0.), 'i': _dasher_idle(0.), 'h': D_HURT, 'k': D_KNEEL, 'd': D_DOWN}
    a, b, w = T[f]
    d = _blend(P[a], P[b], w)
    if f == 10:
        _add(d, 'head', (.06, 0, 0))
    return d


# ------------------------------------------------------------------ reed warden
def _w_legs(d, crouch, point=0.):
    """crouch 0..1: thigh forward / shin back (knee zigzag), feet kept level unless `point` (toe down in the air)."""
    th = -.18 - .62 * crouch; sh = .32 + 1.05 * crouch
    for s in 'lr':
        d['thigh_' + s] = (th, (-.04 if s == 'l' else .04), 0)
        d['shin_' + s] = (sh, 0, 0)
        d['foot_' + s] = (-(th + sh) + point, 0, 0)


# ruff groups (core/enemies.reed_warden): crest = top three blades (pitch X: + raises them from swept-back to up),
# crest_l / crest_r = side blades (yaw Z: crest_l -, crest_r + swings them from swept-back to straight out sideways)
def _ruff(d, k, fwd=0.):
    """k 0 = folded back (rest) .. 1 = exact radial sunburst round the face (the inverse of enemies.RUFF_FOLD);
    fwd tips the flared blades further forward (attack)."""
    A = EN.RUFF_FOLD_ANGLE
    d['crest'] = (A * k + fwd, 0, 0)
    d['crest_l'] = (0, 0, -A * k - fwd * .6)
    d['crest_r'] = (0, 0, A * k + fwd * .6)


W_TELE = {'body': (-.24, 0, 0), 'head': (-.10, 0, 0), 'wing_l': (.25, -1.05, 0), 'wing_r': (.25, 1.05, 0), 'tail': (.55, 0, 0)}
_ruff(W_TELE, 1.)


def _warden_idle(t):
    w = math.sin(t * math.tau); w2 = math.sin(t * math.tau * 2)
    d = {}
    _w_legs(d, .18 + .08 * (.5 - .5 * math.cos(t * math.tau * 2)))
    d['body'] = (.04 + .02 * w2, 0, 0)
    d['head'] = (.04 * w2, 0, .22 * w)
    _ruff(d, .03 + .05 * (.5 + .5 * math.sin(t * math.tau * 2 - .7)))
    flap = .10 * max(0., math.sin(t * math.tau * 3))
    d['wing_l'] = (0, -flap, 0); d['wing_r'] = (0, flap, 0)
    d['tail'] = (.15 + .12 * w2, 0, .10 * w)
    d['lift'] = 0.
    return d


def _warden_move(t):
    """Two hops per second: phase p = (15 t mod 7.5) / 7.5 (key 15 == key 0)."""
    p = ((t * 15.) % 7.5) / 7.5
    d = {}
    air = 0. if not (.12 < p < .78) else math.sin(math.pi * (p - .12) / .66)
    crouch = max(0., math.cos(2 * math.pi * p)) * .85 if not (.12 < p < .78) else .15 * (1 - air)
    if p >= .78:
        crouch = .95 * math.sin(math.pi * (p - .78) / .44) + .2
    _w_legs(d, min(1., crouch), point=.45 * air)
    d['lift'] = .20 * air
    d['body'] = (.16 + .10 * air - .10 * crouch, 0, 0)
    d['head'] = (-.05 * air + .08 * crouch, 0, 0)
    _ruff(d, max(0., .25 * crouch - .10 * air))                     # blades stream back in the air
    flap = 1.1 * math.sin(math.pi * min(1., max(0., (p - .10) / .5))) if .10 < p < .60 else 0.
    d['wing_l'] = (.15, -.15 - flap, 0); d['wing_r'] = (.15, .15 + flap, 0)
    d['tail'] = (.10 + .50 * air, 0, 0)
    return d


def _warden_telegraph(f):
    base = _warden_idle(0.)
    if f == 0:
        return base
    tele = dict(W_TELE)
    _w_legs(tele, 1.)
    tele['lift'] = 0.
    if f <= 3:
        return _blend(base, tele, {1: .45, 2: .85, 3: 1.}[f])
    d = dict(tele)
    tr = .035 if f % 2 else -.035                                   # the flared ruff trembles
    _add(d, 'body', (0, 0, tr)); _add(d, 'crest', (tr * 2, 0, 0)); _add(d, 'crest_l', (0, 0, -tr * 2)); _add(d, 'crest_r', (0, 0, tr * 2))
    return d


def _warden_attack(f):
    tele = dict(W_TELE); _w_legs(tele, 1.); tele['lift'] = 0.
    if f == 0:
        return tele
    spring = {'body': (.30, 0, 0), 'head': (.10, 0, 0), 'wing_l': (.10, -.20, 0), 'wing_r': (.10, .20, 0), 'tail': (.70, 0, 0), 'lift': .10}
    _ruff(spring, .55); _w_legs(spring, 0., point=.30)
    air = {'body': (.70, 0, 0), 'head': (.35, 0, 0), 'wing_l': (-.20, -1.10, 0), 'wing_r': (-.20, 1.10, 0), 'tail': (.90, 0, 0), 'lift': .14}
    _ruff(air, 1., fwd=.25); _w_legs(air, .25, point=.40)
    strike = {'body': (1.00, 0, 0), 'head': (.50, 0, 0), 'wing_l': (-.30, -.85, 0), 'wing_r': (-.30, .85, 0), 'tail': (1.0, 0, 0), 'lift': .02}
    _ruff(strike, 1., fwd=.55); _w_legs(strike, .55)
    recoil = {'body': (.18, 0, 0), 'head': (-.10, 0, 0), 'wing_l': (.10, -.30, 0), 'wing_r': (.10, .30, 0), 'tail': (.30, 0, 0), 'lift': 0.}
    _ruff(recoil, .20); _w_legs(recoil, .85)
    T = {1: (spring, spring, 0.), 2: (air, air, 0.), 3: (strike, strike, 0.), 4: (strike, strike, 0.), 5: (strike, recoil, .25),
         6: (recoil, recoil, 0.), 7: (recoil, recoil, 0.), 8: (recoil, recoil, 0.)}
    if f in T:
        a, b, w = T[f]
        return _blend(a, b, w)
    return _blend(recoil, _warden_idle(0.), {9: .2, 10: .4, 11: .6, 12: .78, 13: .9, 14: .97, 15: 1.}[f])


def _warden_recover(f):
    base = _warden_idle(0.)
    sag = dict(base); _w_legs(sag, .5); _ruff(sag, 0.)
    if f == 0:
        r = {'body': (.18, 0, 0), 'head': (-.10, 0, 0), 'tail': (.30, 0, 0), 'lift': 0.}
        _ruff(r, .20); _w_legs(r, .85)
        return r
    if f <= 6:
        d = dict(sag)
        sh = (.18 if f % 2 else -.18) * (1 - f / 8.)              # dizzy head shake, ruff limp
        _add(d, 'body', (0, sh, 0)); _add(d, 'head', (0, 0, -1.6 * sh))
        return d
    return _blend(sag, base, min(1., (f - 6) / 7.))


def _warden_hurt(f):
    hurt = {'body': (-.45, .12, 0), 'head': (-.30, 0, .15), 'wing_l': (.0, -.95, 0), 'wing_r': (.0, .95, 0), 'tail': (.75, 0, 0), 'lift': .04}
    _ruff(hurt, 0.); _add(hurt, 'crest', (-.25, 0, 0)); _add(hurt, 'crest_l', (0, 0, .25)); _add(hurt, 'crest_r', (0, 0, -.25))
    _w_legs(hurt, .40)
    w = [0., 1., 1., .85, .70, .55, .42, .30, .20, .12, .06, .02, 0., 0., 0., 0.][f]
    return _blend(_warden_idle(0.), hurt, w)


def _warden_death(f):
    base = _warden_idle(0.)
    hurt = _warden_hurt(1)
    buckle = {'body': (.25, 0, 0), 'head': (.30, 0, 0), 'wing_l': (.20, .25, 0), 'wing_r': (.20, -.25, 0), 'tail': (-.10, 0, 0), 'lift': 0.}
    _ruff(buckle, 0.); _add(buckle, 'crest', (-.20, 0, 0)); _w_legs(buckle, 1.)
    down = {'body': (.10, 1.45, 0), 'head': (.25, .15, 0), 'wing_l': (.30, .35, 0), 'wing_r': (.10, -.55, 0), 'tail': (-.20, 0, .20), 'lift': 0.}
    _ruff(down, 0.); _add(down, 'crest', (-.25, 0, 0)); _w_legs(down, .55)
    T = [(base, base, 0.), (base, hurt, 1.), (hurt, hurt, 0.), (hurt, buckle, .5), (buckle, buckle, 0.), (buckle, buckle, 0.),
         (buckle, down, .35), (buckle, down, .70), (buckle, down, .92), (down, down, 0.), (down, down, 0.), (down, down, 0.),
         (down, down, 0.), (down, down, 0.), (down, down, 0.), (down, down, 0.)]
    a, b, w = T[f]
    d = _blend(a, b, w)
    if f == 9:
        _add(d, 'head', (.05, 0, 0))
    return d


def key_euler(eid, clip, t):
    f = frame_of(t)
    if eid == 'cairn_dasher':
        fn = {'idle': lambda: _dasher_idle(t), 'move': lambda: _dasher_move(t), 'telegraph': lambda: _dasher_telegraph(f),
              'attack': lambda: _dasher_attack(f), 'recover': lambda: _dasher_recover(f), 'hurt': lambda: _dasher_hurt(f),
              'death': lambda: _dasher_death(f)}
    else:
        fn = {'idle': lambda: _warden_idle(t), 'move': lambda: _warden_move(t), 'telegraph': lambda: _warden_telegraph(f),
              'attack': lambda: _warden_attack(f), 'recover': lambda: _warden_recover(f), 'hurt': lambda: _warden_hurt(f),
              'death': lambda: _warden_death(f)}
    if clip not in fn:
        raise ValueError('unknown enemy clip ' + str(clip))
    return fn[clip]()


def local_pose(m, clip, t):
    """-> (local quaternions {bone: (w, x, y, z)}, body_offset_z (m), lift (m)). body_offset_z = grounding + lift."""
    d = key_euler(m.id, clip, t)
    lift = float(d.get('lift', 0.))
    local = {n: PO.qe(*d.get(n, (0., 0., 0.))) for n in m.parents}
    V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
    floor = min(v[2] for v in V)
    return local, -floor + lift, lift


def posed_vertices(m, clip, t):
    local, dz, lift = local_pose(m, clip, t)
    V = PO.skin(m.bones, m.parents, local, m.vertices, m.weights)
    return [(x, y, z + dz) for x, y, z in V], local, dz
