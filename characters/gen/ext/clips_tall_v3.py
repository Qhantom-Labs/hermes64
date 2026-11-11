"""Clips of the tall_v3 visor body (rig human16_v1), 16 keys at 15 fps.

sample(a, clip, key, metrics) -> (local rotations {bone: (w, x, y, z)}, lift in metres), the contract of
ext/clips_adult.sample.

idle is authored here: a plumb, left-right symmetric stand (pelvis level, both legs straight under the hips, spine and
head upright) with breathing only. The round-21 idle put the 'confident' weight shift on top of the shared idle (pelvis
and spine rolled and yawed, right thigh splayed, left knee bent), which is what made the legs read as offset from the
body.

run and walk are the planted-foot cycle of ext/clips_adult.py (lane CHARS3) retargeted to this body: the solver reads
the leg lengths, the boot outline and the standing hip height from the built mesh, so the same phase tables give this
body its own joint angles and a ground speed scaled to its leg (stride_mps). Thigh, shin and foot only turn about the
side axis, so both legs stay in their own fore-aft plane under the hips (tools/chars4_run_metrics.py measures the
sideways drift of the boots, the sliding of the planted boot and the flight). CYCLES holds this body's tuning; the
adult family's tables are not modified.

The remaining clips are the shared core set with the neutral stance.
"""
import math

from . import clips_adult as CA
from . import pose as PO

FPS = 15.
KEYS = 16
STANCE = 'neutral'
CHIN_DOWN = .05          # rad: the head is carried a little chin-down (the serious look, without a tube to hide in)
ARM_IN = .10             # rad: upper arms brought in from the rest pose's A shape
ARM_ASYM = 0.            # rad: extra bend of the left forearm. Revision 1 had .10 (43 mm left-right difference at the
#                          hands in the idle); revision 2 is mirrored so the symmetry gate covers the stand as well
TOE_OUT = .19           # rad, each leg about its own vertical axis


def _idle(a, key):
    t = key / float(KEYS)
    breath = math.sin(t * math.tau)
    e = {
        'spine': (.010 * breath, 0., 0.),
        'head': (CHIN_DOWN - .012 * breath, 0., 0.),
    }
    for s, sg in (('l', 1), ('r', -1)):
        # arms hang closer to the jacket than the A-shaped rest pose, elbows slightly bent; they lift a hair on the
        # in-breath
        e['upper_arm_' + s] = (-.05, sg * (ARM_IN - .006 * breath), sg * .045)
        e['forearm_' + s] = (-.20 - .01 * breath - (ARM_ASYM if s == 'l' else 0.), 0., 0.)
        e['thigh_' + s] = (0., 0., sg * TOE_OUT)          # legs stay plumb; the feet turn out a little (not a toy soldier)
    return {n: PO.qe(*e.get(n, (0., 0., 0.))) for n in a.parents}, 0.


# this body's tuning of the shared cycle. The legs of this body stand close together, so the adult pelvis turn (7 and 6
# degrees) carried the forward boot across the centre line (3 cm in the run, measured); the pelvis turns 2.5 degrees
# here and the shoulders keep their counter-turn. Run: a little less spine lean (margin under the 18 degree limit).
CYCLES = {'run': dict(CA.RUN, lean=(8., 11.), yaw=(2.5, 13.)), 'walk': dict(CA.WALK, yaw=(2.5, 9.))}
STRIDE_MPS = CA.STRIDE_MPS


def stride_mps(a, clip):
    return CA.stride_mps(a, clip)


def _gait(clip):
    return lambda a, key: CA._cycle(a, clip, key, CYCLES)


AUTHORED = {'idle': _idle, 'run': _gait('run'), 'walk': _gait('walk')}


def sample(a, clip, key, metrics=None):
    fn = AUTHORED.get(clip)
    if fn is not None:
        return fn(a, key)
    H = a.params.get('height', 1.)
    return PO.local_rotations(a.bones, H, a.kind, clip, key / FPS, STANCE, metrics), 0.
