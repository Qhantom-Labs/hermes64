"""Paint delta of the tall_v3 visor body (lane CHARS4): edits the round-21 atlases, never repaints them whole.

repaint(pack, p, cloth, face, hair) -> (cloth, face, hair), uint8 images as the round-21 painters return them
(image row 0 = v 1). Two edits.

COLLAR (costume atlas): the round-21 texture was drawn for a 19 cm
tube with the zip running up it. The low collar maps its outer wall to the top of the region (rib knit, light rim,
shadow where it meets the jacket) and its lining to the bottom (dark), see ext/tall_v3.COLLAR_V.

LOWER FACE (face atlas, all 8 expression cells): the tube hid the mouth and jaw of round 21, so nobody ever looked at
them. Now they show:
  - under the chin the shared face painter leaves a two-tone stepped band that straddles the jaw edge of the mesh; on
    the exposed chin it reads as a stubble smear. tall_v3 has a real under-jaw plane with its own shade
    (ext/tall_v3 NECK), so everything from one texel above the jaw edge downward becomes plain skin: the mesh edge
    draws the jaw, not the texels.
  - the thin outline band at the sides of the face lands mid-cheek on this head as a stepped vertical seam: plain skin.
  - the closed-mouth line was the pack's black face line (a black blot at gameplay size); thin mouth lines are
    repainted in the darkest skin tone, as a painted mouth. Open mouths (talk, surprised) keep their dark interior.
The shared painter (core/face_paint.py) is not touched: every other character keeps its atlas byte for byte.
"""
import numpy as np

from . import face_paint as FP
from . import paint as P0
from . import people as PP
from . import people_paint as PPP


def repaint(pack, p, cloth, face, hair):
    T = PPP.Tones(pack)
    C = PPP._colors(pack, p)
    cc = C['collar_color']
    c, box = PPP._region_canvas(T, cc, PP.REGIONS['collar'])
    v = c.tv
    outer = v >= .55
    c.put(outer & (np.floor(c.x) % 4 == 0), cc, -1)          # vertical rib
    c.put(outer & (v < .70), cc, -1)                         # shadow at the jacket seam
    c.put(v > .90, cc, 1)                                    # rim catches the light
    c.put(~outer, cc, -2)                                    # lining
    c.put(~outer & (v > .30), cc, -1)                        # lining lightens toward the rim
    cloth = np.array(cloth, copy=True)
    cloth[box[2]:box[3], box[0]:box[1]] = P0.quantize(c.img, P0.palette(pack))
    if not CHEST_LIGHT:
        mask, box, base = chest_light(pack, p, cloth)
        cloth[box[2]:box[3], box[0]:box[1]][mask] = base[mask]
    return cloth, _lower_face(pack, T, C, face), hair


# The round-21 jacket has one texture mark that is shading and not pattern: a rectangle one tone lighter than the
# jacket colour on the upper chest (see chest_light()). True keeps it (round 21, revisions 1-3 as shipped); False
# repaints those texels in the plain jacket tone and touches nothing else (bands, strap, zip, buckle stay).
CHEST_LIGHT = True


def chest_light(pack, p, cloth):
    """(mask, box, base) for the lighter rectangle on the chest: the texels of the torso region that carry the jacket
    colour one tone up. The round-21 painter uses that tone for nothing else in the region, so the rectangle is found
    in the atlas itself. base = the same region in the plain jacket tone."""
    T = PPP.Tones(pack)
    g = PPP._colors(pack, p)['garment_color']
    c, box = PPP._region_canvas(T, g, PP.REGIONS['torso'])
    base = P0.quantize(c.img, P0.palette(pack))
    c.put(np.ones(c.u.shape, dtype=bool), g, 1)
    light = P0.quantize(c.img, P0.palette(pack))
    mask = (cloth[box[2]:box[3], box[0]:box[1]] == light).all(axis=2) & (light != base).any(axis=2)
    return mask, box, base


UNDER_JAW = .03              # plain skin from this far (v) above the jaw edge downward
PATCHES = (.13, .15)         # u margin at both sides / v height of the cell corners that hold the skin and ear patches
OUTLINE = (.93, 1.09, .80)   # the outline band of the shared painter: d range, top v
MOUTH_ZONE = (.20, .07)      # half width (u), half height (v) around the mouth line


def _tone(pack, T, name, k):
    c = PPP.Canvas(T, 64, 64, name)
    c.put(np.ones((64, 64), dtype=bool), name, k)
    return c, P0.quantize(c.img, P0.palette(pack))


def _lower_face(pack, T, C, face):
    sk = C['skin']
    c, skin = _tone(pack, T, sk, 0)
    _, deep = _tone(pack, T, sk, -3)
    _, black = _tone(pack, T, pack.get('face_line', sk), 0 if pack.get('face_line') else -4)
    u, v = c.u, c.v
    jaw = FP.jaw_v(u)
    patch = ((u < PATCHES[0]) | (u > 1 - PATCHES[0])) & (v < PATCHES[1])
    d = np.abs(u - .5) / np.maximum(FP.half(v), 1e-3)
    plain = ((v < jaw + UNDER_JAW) | ((v >= jaw) & (d >= OUTLINE[0]) & (d < OUTLINE[1]) & (v < OUTLINE[2]))) & ~patch
    zone = (np.abs(u - .5) < MOUTH_ZONE[0]) & (np.abs(v - FP.L['mouth_v']) < MOUTH_ZONE[1])
    out = np.array(face, copy=True)
    for cell in range(8):
        y0 = (1 - cell // 4) * 64; x0 = (cell % 4) * 64
        px = out[y0:y0 + 64, x0:x0 + 64]
        px[plain] = skin[plain]
        dark = (px == black).all(axis=2) & zone
        # thin = at most 2 texels of line in the column (a mouth line, not an open mouth)
        thin = dark & (dark.sum(axis=0, keepdims=True) <= 2)
        px[thin] = deep[thin]
    return out
