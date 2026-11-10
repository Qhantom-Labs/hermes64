"""Stance-aware placement of held props (pure Python; used by core/blender.py and core/posecheck.py).

A prop stays a rigid child of its attachment bone. Its rest transform is solved so that in the character's
stance at idle t=0 it lands where it should (mug upright beside the fingers, lantern hanging below the
fist, book tilted up between both hands, cane tip on the floor); in every other clip it moves rigidly with
the bone. attach(a, stance, kind) -> (q_rest (w,x,y,z), t_rest (x,y,z)) in world rest coordinates.
"""
import math

from . import pose as PO
from . import props as PR

SLOT_BONE = {'hand_l': 'hand_l', 'hand_r': 'hand_r', 'head': 'head', 'back': 'spine', 'belt': 'pelvis'}
# kind: (anchor, (inward, forward, up) offset in units of height, world orientation Euler or 'floor')
PLACE = {
    'mug': ('mitt', (.014, .012, -.004), (0., 0., 0.)),
    'thermos': ('mitt', (.012, .008, -.004), (0., 0., 0.)),
    'lantern': ('mitt', (0., .0, -.008), (0., 0., 0.)),
    'duffel': ('mitt', (0., .0, -.004), (0., 0., 0.)),
    # reader-side face normal ends up pointing back-up toward the eyes; the hands hold the lower edge
    'datapad': ('hands', (0., .016, .03), (.19, 0., 0.)),      # round 9: held up, nearly upright
    'book': ('hands', (0., .018, .034), (.53, 0., 0.)),
    'cane': ('mitt', (0., .0, .006), 'floor'),
}
# round 16: per-stance overrides (kind, stance) -> PLACE row; the datapad held low ('tablet') tilts up to the eyes
PLACE_STANCE = {('datapad', 'tablet'): ('hands', (0., .010, .040), (.75, 0., 0.))}   # round 17: hands grip the lower edge (the r16 pad hid the hands in run/sit on a sweep body)


def _v(a): return (a[0], a[1], a[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mitt_centre(a, side):
    ids = a.parts['mitt_' + side]
    n = float(len(ids))
    return tuple(sum(a.vertices[i][k] for i in ids) / n for k in range(3))


def floor_gap(a, stance, kind):
    """Round 16: for floor-planted props (PLACE orientation 'floor', e.g. the cane) the gap in metres between the
    shaft tip and the floor at idle t=0 when the shaft is fully vertical (0 if the tip reaches the floor). attach()
    tilts the shaft until the tip touches; if the gripping hand is higher than the shaft is long it cannot, and the
    prop would float. Non-floor props return 0."""
    if kind not in PLACE:
        return 0.
    anchor, off, ori = PLACE_STANCE.get((kind, stance), PLACE[kind])
    if ori != 'floor':
        return 0.
    m = PR.build(kind)
    bone = SLOT_BONE[m.slot]
    H = a.params.get('height', 1.)
    local = PO.local_rotations(a.bones, H, a.kind, 'idle', 0., stance, PO.body_metrics(a))
    qw, pos = PO._fk_world(a.bones, a.parents, local)
    side = bone[-1]; s = 1 if side == 'l' else -1
    P = _add(pos[bone], PO.qv(qw[bone], _sub(mitt_centre(a, side), a.bones[bone])))
    P = _add(P, (-s * off[0] * H, -off[1] * H, off[2] * H))
    verts = PO.skin(a.bones, a.parents, local, a.vertices, a.weights)
    floor = min(v[2] for v in verts)
    reach = -min(v[2] for v in m.vertices)
    return max(0., (P[2] - floor) - reach)


def rigid_default(a, kind):
    m = PR.build(kind)
    bone = SLOT_BONE[m.slot]; g = PR.GRIP[m.slot]; H = a.params.get('height', 1.)
    j = a.bones[bone]
    return (1., 0., 0., 0.), (j[0] + g[0] * H, j[1] + g[1] * H, j[2] + g[2] * H)


# round 13 (STEER-5 §3) prop placement rule: a prop held at the side of a mitt never hides the gripping hand. If
# the hand's visible fraction (front + own-side 3/4 camera, over the clips where the prop is held) falls under
# VIS_KEEP, the prop slides inward (toward the body midline, past the fingers) in steps of a quarter of its own
# radius until the hand reads. Small hands (children) and large props need this; the tuned cast does not move.
VIS_KEEP = .36            # posecheck rejects < .30
VIS_RULE = ('mug', 'thermos')
# every clip key pose in which a hand prop is held (carry stows it), as checked by tools/pose_audit
VIS_CLIPS = tuple((c, t) for c in ('idle', 'walk', 'run', 'interact', 'talk', 'sit') for t in (0., .25, .5, .75))


def _posed_frames(a, stance):
    from . import posecheck as PC
    out = []
    for clip, t in VIS_CLIPS:
        V, qw, pos = PC._posed(a, stance, clip, t)
        out.append((V, qw, pos, PC.pieces(a, V)))
    return out


def _hand_vis_min(a, frames, kind, side, q_r, t_r, stop_below=None):
    import numpy as np
    from . import posecheck as PC
    m = PR.build(kind)
    bone = SLOT_BONE[m.slot]
    rest = [_add(t_r, PO.qv(q_r, v)) for v in m.vertices]
    j = a.bones[bone]
    F = np.array(m.faces)
    worst = 1.
    for V, qw, pos, P in frames:
        Vp = np.array([_add(pos[bone], PO.qv(qw[bone], _sub(v, j))) for v in rest])
        extra = [('prop_' + kind, Vp[F])]
        front = PC.hand_visibility(a, V, P, extra, 0.)
        for sd in 'lr':                  # both hands: the gripping hand and the supporting one (posecheck views)
            own = PC.hand_visibility(a, V, P, extra, PC.YAW_34 if sd == 'l' else -PC.YAW_34)
            worst = min(worst, front['hand_' + sd][0], own['hand_' + sd][0])
            if stop_below is not None and worst < stop_below:
                return worst
    return worst


def attach(a, stance, kind):
    cache = getattr(a, '_attach_cache', None)
    if cache is None:
        cache = {}
        try:
            a._attach_cache = cache
        except AttributeError:
            pass
    key = (stance, kind)
    if key not in cache:
        cache[key] = _attach(a, stance, kind)
    return cache[key]


def _attach(a, stance, kind):
    m = PR.build(kind)
    bone = SLOT_BONE[m.slot]
    if kind not in PLACE or not bone.startswith('hand_'):
        return rigid_default(a, kind)
    H = a.params.get('height', 1.)
    local = PO.local_rotations(a.bones, H, a.kind, 'idle', 0., stance, PO.body_metrics(a))
    qw, pos = PO._fk_world(a.bones, a.parents, local)

    def posed_mitt(sd):
        b = 'hand_' + sd
        return _add(pos[b], PO.qv(qw[b], _sub(mitt_centre(a, sd), a.bones[b])))
    anchor, off, ori = PLACE_STANCE.get((kind, stance), PLACE[kind])
    side = bone[-1]; s = 1 if side == 'l' else -1
    if anchor == 'hands':
        pl, pr = posed_mitt('l'), posed_mitt('r')
        P = tuple((pl[k] + pr[k]) / 2 for k in range(3))
    else:
        P = posed_mitt(side)
    P = _add(P, (-s * off[0] * H, -off[1] * H, off[2] * H))
    if ori == 'floor':
        # tilt the shaft forward until its tip reaches the floor (posed mesh minimum)
        verts = PO.skin(a.bones, a.parents, local, a.vertices, a.weights)
        floor = min(v[2] for v in verts)
        tip = min(v[2] for v in m.vertices)                 # shaft tip (prop-local, below the grip)
        reach = -tip
        drop = max(1e-3, P[2] - floor)
        ang = math.acos(max(-1., min(1., drop / reach))) if drop < reach else 0.
        q_des = PO.qa((1., 0., 0.), -ang)
    else:
        q_des = PO.qe(*ori)
    q_r = PO.qm(PO.qc(qw[bone]), q_des)
    t_r = _add(a.bones[bone], PO.qv(PO.qc(qw[bone]), _sub(P, pos[bone])))
    if kind in VIS_RULE and anchor == 'mitt' and getattr(a, 'kind', None) == 'human':
        frames = _posed_frames(a, stance)
        if _hand_vis_min(a, frames, kind, side, q_r, t_r, VIS_KEEP) < VIS_KEEP:
            rad = max(math.hypot(v[0], v[1]) for v in m.vertices)
            best = (_hand_vis_min(a, frames, kind, side, q_r, t_r), t_r)
            # nearest placement first: inward past the fingers, outward, then raised (hand grips the lower body)
            for k in range(1, 9):
                for d in ((-s, 0., 0.), (s, 0., 0.), (0., 0., 1.)):
                    Pk = _add(P, (d[0] * .25 * rad * k, 0., d[2] * .25 * rad * k))
                    tk = _add(a.bones[bone], PO.qv(PO.qc(qw[bone]), _sub(Pk, pos[bone])))
                    v = _hand_vis_min(a, frames, kind, side, q_r, tk, VIS_KEEP)
                    if v >= VIS_KEEP:
                        return q_r, tk
                    if v > best[0]:
                        best = (v, tk)
            return q_r, best[1]
    return q_r, t_r


def place_vertices(a, stance, kind, q_r=None, t_r=None):
    """Rest-world vertices of the prop (for pure-python checks)."""
    if q_r is None:
        q_r, t_r = attach(a, stance, kind)
    m = PR.build(kind)
    return [_add(t_r, PO.qv(q_r, v)) for v in m.vertices], m
