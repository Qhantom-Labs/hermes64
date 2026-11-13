"""Creator geometry (numpy): one welded parametric body + modules, in glTF axes (Y up, faces +Z, left = +X).

Every length is a fraction of height until finish() scales by height_m. The body is a single closed piece:
  torso   8-vertex rings T0 (hips) .. T4 (neck base); arm openings between T2 and T3 on each side
  legs    6-vertex rings that start from 5 hip-ring vertices + one crotch vertex, down to a chunky boot footprint
  arms    6-vertex rings from the side openings, then a flattened mitten hand with a welded thumb bulge
  head    8-vertex rings from the neck ring up to a crown apex
Hair and beards are inset skinned pieces (rigid on the head, their rim inside the closed head so the rig kit sees them
joined). Hats, ears, horns, muzzles, capes, backpacks, tails and held props are rigid socket meshes (rig props).
Corner UVs are part-local (u, v in 0..1); paint.py maps parts onto the 64x64 atlas and bakes the light.
"""
import math

import numpy as np

BONES = ['root', 'pelvis', 'spine', 'head', 'upper_arm_l', 'forearm_l', 'hand_l', 'upper_arm_r', 'forearm_r', 'hand_r',
         'thigh_l', 'shin_l', 'foot_l', 'thigh_r', 'shin_r', 'foot_r']
PARENT = {'root': None, 'pelvis': 'root', 'spine': 'pelvis', 'head': 'spine', 'upper_arm_l': 'spine', 'forearm_l': 'upper_arm_l',
          'hand_l': 'forearm_l', 'upper_arm_r': 'spine', 'forearm_r': 'upper_arm_r', 'hand_r': 'forearm_r', 'thigh_l': 'pelvis',
          'shin_l': 'thigh_l', 'foot_l': 'shin_l', 'thigh_r': 'pelvis', 'shin_r': 'thigh_r', 'foot_r': 'shin_r'}
U8 = [.5, .67, .8, .9, 0., .1, .2, .33]          # head/hair u of ring index k (k=0 front, k=2 left): seam at the back
U8_TORSO = [.5, .625, .75, .875, 0., .125, .25, .375]


def _n(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def skeleton(p):
    """Joint world positions (fractions of height) from the body parameters; mirrored left/right."""
    neck_y = 1. - p['head_h']
    sh_y = neck_y - p['neck_to_shoulder']
    sp_y = sh_y - p['torso_upper']
    pel_y = sp_y - p['spine_len']
    hip_y = pel_y - p['hip_drop']
    ank_y = p['ankle_y']
    leg = hip_y - ank_y
    knee_y = hip_y - leg * p['thigh_share']
    a, b = math.radians(p['arm_angle']), math.radians(p['forearm_angle'])
    J = {'root': np.zeros(3), 'pelvis': np.array([0., pel_y, 0.]), 'spine': np.array([0., sp_y, -.003]),
         'head': np.array([0., neck_y, -.008])}
    for s, sg in (('l', 1.), ('r', -1.)):
        sh = np.array([sg * p['shoulder_x'], sh_y, -.01])
        el = sh + p['upper_arm'] * np.array([sg * math.sin(a), -math.cos(a), 0.]) + np.array([0., 0., .004])
        wr = el + p['forearm'] * np.array([sg * math.sin(b), -math.cos(b), 0.]) + np.array([0., 0., .012])
        th = np.array([sg * p['hip_x'], hip_y, 0.])
        kn = np.array([sg * (p['hip_x'] + p['knee_out']), knee_y, .022])
        an = np.array([sg * (p['hip_x'] + p['ankle_out']), ank_y, -.016])
        J.update({'upper_arm_' + s: sh, 'forearm_' + s: el, 'hand_' + s: wr, 'thigh_' + s: th, 'shin_' + s: kn, 'foot_' + s: an})
    return J


class Mesh:
    """Vertices + per-vertex skin weights + triangles with part-local corner UVs."""

    def __init__(self):
        self.V, self.W, self.piece = [], [], []
        self.F, self.UV, self.part, self.side = [], [], [], []

    def v(self, p, w, piece='body'):
        self.V.append(np.asarray(p, float))
        self.W.append(dict(w))
        self.piece.append(piece)
        return len(self.V) - 1

    def tri(self, a, b, c, uva, uvb, uvc, part, side='c'):
        self.F.append((a, b, c))
        self.UV.append((tuple(uva), tuple(uvb), tuple(uvc)))
        self.part.append(part)
        self.side.append(side)

    def _outward(self, a, b, c, ref):
        V = self.V
        nrm = np.cross(V[b] - V[a], V[c] - V[a])
        ctr = (V[a] + V[b] + V[c]) / 3.
        return float(nrm @ (ctr - ref)) >= 0.

    def quad(self, a0, a1, b1, b0, uv, part, side, ref, axis=None):
        """Two triangles, wound so the face normal points away from ref (radially, when axis is given)."""
        V = self.V
        ctr = (V[a0] + V[a1] + V[b1] + V[b0]) / 4.
        r = ctr - ref
        if axis is not None:
            r = r - (r @ axis) * axis
        nrm = np.cross(V[a1] - V[a0], V[b0] - V[a0]) + np.cross(V[b1] - V[a1], V[a0] - V[a1])
        (ua0, ua1, ub1, ub0) = uv
        if float(nrm @ r) >= 0.:
            self.tri(a0, a1, b1, ua0, ua1, ub1, part, side)
            self.tri(a0, b1, b0, ua0, ub1, ub0, part, side)
        else:
            self.tri(a0, b1, a1, ua0, ub1, ua1, part, side)
            self.tri(a0, b0, b1, ua0, ub0, ub1, part, side)

    def loft(self, A, B, cols, va, vb, part, side='c', skip=()):
        """Quads between equal-length closed loops A and B. cols[k] = u of vertex k; the column whose u is 0 is the
        seam (quads ending there use u = 1). skip: quad indices left open (arm openings)."""
        n = len(A)
        cA = np.mean([self.V[i] for i in A], axis=0)
        cB = np.mean([self.V[i] for i in B], axis=0)
        axis = _n(cB - cA)
        ref = (cA + cB) / 2.
        for i in range(n):
            if i in skip:
                continue
            j = (i + 1) % n
            u0, u1 = cols[i], cols[j]
            if u1 <= u0:
                u1 = 1.
            self.quad(A[i], A[j], B[j], B[i], ((u0, va), (u1, va), (u1, vb), (u0, vb)), part, side, ref, axis)

    def fan(self, loop, apex, cols, v_loop, v_apex, part, side='c', ref=None):
        n = len(loop)
        ref = np.mean([self.V[i] for i in loop], axis=0) if ref is None else ref
        for i in range(n):
            j = (i + 1) % n
            u0, u1 = cols[i], cols[j]
            if u1 <= u0:
                u1 = 1.
            a, b = loop[i], loop[j]
            uva, uvb, uvc = (u0, v_loop), (u1, v_loop), ((u0 + u1) / 2., v_apex)
            if self._outward(a, b, apex, ref):
                self.tri(a, b, apex, uva, uvb, uvc, part, side)
            else:
                self.tri(a, apex, b, uva, uvc, uvb, part, side)

    def pts(self, idx):
        return np.array([self.V[i] for i in idx])

    def tris_of(self, piece_pred):
        return sum(1 for f in self.F if piece_pred(self.piece[f[0]]))


def _ring(M, centre, rx, rz, n, w, phase=0., piece='body', ydir=None, dirs=None):
    """n vertices on an ellipse around centre in the horizontal plane (k=0 at +Z, increasing toward +X)."""
    out = []
    for k in range(n):
        if dirs is not None:
            off = dirs[k][0] * rx + dirs[k][1] * rz
        else:
            phi = phase + 2. * math.pi * k / n
            off = np.array([rx * math.sin(phi), 0., rz * math.cos(phi)])
        out.append(M.v(np.asarray(centre, float) + off, w, piece))
    return out


def _frame(axis, hint):
    """Two unit vectors perpendicular to axis: e1 close to hint, e2 = axis x e1."""
    axis = _n(axis)
    e1 = _n(hint - (hint @ axis) * axis)
    e2 = np.cross(axis, e1)
    return e1, e2


def _limb_ring(M, centre, axis, root_dirs, rx, rz, w, piece='body'):
    """A ring perpendicular to axis whose vertices follow root_dirs (unit vectors in the ring plane, in loop order)."""
    out = []
    for d in root_dirs:
        dd = d - (d @ axis) * axis
        dd = _n(dd)
        out.append(M.v(centre + dd * rx, w, piece))
    return out


def _regular_dirs(M, loop, centre, axis, n):
    """Regular n-gon directions in the plane of axis, starting at loop[0]'s direction, turning the loop's way."""
    p0 = M.V[loop[0]] - centre
    p1 = M.V[loop[1]] - centre
    e1 = _n(p0 - (p0 @ axis) * axis)
    e2 = np.cross(axis, e1)
    turn = 1. if float((p1 - (p1 @ axis) * axis) @ e2) >= 0 else -1.
    return [e1 * math.cos(2 * math.pi * k / n) + turn * e2 * math.sin(2 * math.pi * k / n) for k in range(n)]


def _scaled_dirs(dirs, e_wide, sw, sn):
    """Flatten ring directions: component along e_wide scaled by sw, the rest by sn."""
    out = []
    for d in dirs:
        a = d @ e_wide
        rest = d - a * e_wide
        out.append(e_wide * a * sw + rest * sn)
    return out


def _wb(a, b, t):
    """Blend weights: (1-t) on a, t on b."""
    if t <= 0:
        return {a: 1.}
    if t >= 1:
        return {b: 1.}
    return {a: 1. - t, b: t}


def body(p, J):
    """The welded body. Returns (mesh, rings) where rings names loops modules attach to."""
    M = Mesh()
    neck_y, sh_y = J['head'][1], J['upper_arm_l'][1]
    pel_y, hip_y = J['pelvis'][1], J['thigh_l'][1]
    hx, sx = p['hip_x'], p['shoulder_x']
    cw, ww, cd = p['chest_w'] / 2., p['waist_w'] / 2., p['chest_d'] / 2.
    # ---------------- torso
    T0 = _ring(M, (0, hip_y + .012, 0.), hx + p['thigh_r'] * .92, p['hip_d'] / 2., 8, {'pelvis': 1.})
    T1 = _ring(M, (0, pel_y + .045, .004), ww, cd * .9, 8, {'pelvis': .5, 'spine': .5})
    T15 = _ring(M, (0, (pel_y + sh_y) / 2. + .02, .01), (ww + cw) / 2., cd * .97, 8, {'spine': 1.})
    T2 = _ring(M, (0, sh_y - .07, .012), cw, cd, 8, {'spine': 1.})
    T3 = _ring(M, (0, sh_y + .022, 0.), sx + .018, cd * .72, 8, {'spine': 1.})
    T4 = _ring(M, (0, neck_y - .012, -.006), p['neck_r'], p['neck_r'] * 1.05, 8, {'spine': .55, 'head': .45})
    M.loft(T0, T1, U8_TORSO, 1., .78, 'torso')
    M.loft(T1, T15, U8_TORSO, .78, .55, 'torso')
    M.loft(T15, T2, U8_TORSO, .55, .36, 'torso')
    M.loft(T2, T3, U8_TORSO, .36, .14, 'torso', skip=(1, 2, 5, 6))
    M.loft(T3, T4, U8_TORSO, .14, 0., 'torso')
    rings = {'T0': T0, 'T1': T1, 'T2': T2, 'T3': T3, 'T4': T4}
    # ---------------- legs (6-vertex): root = 5 hip-ring vertices + the crotch vertex
    C = M.v((0., hip_y - .028, .0), {'pelvis': 1.})
    leg_cols = [1 / 6., 2 / 6., 3 / 6., 4 / 6., 5 / 6., 0.]
    for s, root in (('l', [T0[0], T0[1], T0[2], T0[3], T0[4], C]), ('r', [T0[0], T0[7], T0[6], T0[5], T0[4], C])):
        th, kn, an = J['thigh_' + s], J['shin_' + s], J['foot_' + s]
        sg = 1. if s == 'l' else -1.
        rc = np.mean([M.V[i] for i in root], axis=0)
        axis = _n(rc - kn)
        dirs = _regular_dirs(M, root, rc, axis, 6)
        prev, pv = root, 0.
        knee_axis = _n(th - kn)
        shin_axis = _n(kn - an)
        boot_top = an[1] + p['boot_h']
        spec = [  # (centre, axis, rx, rz, weights, v)
            (th + (kn - th) * .2, knee_axis, p['thigh_r'], p['thigh_r'], _wb('pelvis', 'thigh_' + s, .65), .1),  # .2: clear of the crotch
            (th + (kn - th) * .55, knee_axis, p['thigh_r'] * .94, p['thigh_r'] * .94, {'thigh_' + s: 1.}, .32),
            (kn, _n(knee_axis + shin_axis), p['knee_r'], p['knee_r'], _wb('thigh_' + s, 'shin_' + s, .5), .5),
            (kn + (an - kn) * .38, shin_axis, p['calf_r'], p['calf_r'], {'shin_' + s: 1.}, .66),
            (an + np.array([0., boot_top - an[1], .0]), shin_axis, p['boot_r'], p['boot_r'], _wb('shin_' + s, 'foot_' + s, .2), .82),
            (an + np.array([0., .006, .004]), np.array([0., 1., 0.]), p['ankle_r'], p['ankle_r'], _wb('shin_' + s, 'foot_' + s, .55), .9),
        ]
        for centre, ax, rx, rz, w, v in spec:
            ring = _limb_ring(M, centre, ax, dirs, rx, rz, w)
            M.loft(prev, ring, leg_cols, pv, v, 'leg', s)
            prev, pv = ring, v
        rings['ankle_' + s] = prev
        # boot footprint: toe-inner, toe-outer, mid-outer, heel-outer, heel-inner, mid-inner
        L, Lb = p['boot_len'] * .72, p['boot_len'] * .28
        tw, mw, hw = p['boot_w'] * .42, p['boot_w'] * .5, p['boot_w'] * .36
        ax_, az = an[0], an[2]
        fp = [(-tw, L), (tw, L), (mw, .03), (hw, -Lb), (-hw, -Lb), (-mw, .03)]
        foot = {'foot_' + s: 1.}
        B = [M.v((ax_ + sg * x, p['boot_sole_h'], az + z), foot) for x, z in fp]
        S = [M.v((ax_ + sg * x * 1.03, 0., az + z * 1.02), foot) for x, z in fp]
        M.loft(prev, B, leg_cols, .9, .95, 'boot', s)
        M.loft(B, S, leg_cols, .95, 1., 'boot', s)
        sole_ref = np.array([ax_, .2, az])
        for a, b, c in ((S[0], S[1], S[2]), (S[0], S[2], S[3]), (S[0], S[3], S[4]), (S[0], S[4], S[5])):
            if M._outward(a, b, c, sole_ref):
                M.tri(a, b, c, (.1, .99), (.3, .99), (.5, .99), 'boot', s)
            else:
                M.tri(a, c, b, (.1, .99), (.5, .99), (.3, .99), 'boot', s)
    # ---------------- arms (6-vertex) from the side openings
    arm_cols = [5 / 6., 0., 1 / 6., 2 / 6., 3 / 6., 4 / 6.]
    for s, root in (('l', [T2[1], T2[2], T2[3], T3[3], T3[2], T3[1]]), ('r', [T2[7], T2[6], T2[5], T3[5], T3[6], T3[7]])):
        sh, el, wr = J['upper_arm_' + s], J['forearm_' + s], J['hand_' + s]
        ua_ax, fa_ax = _n(el - sh), _n(wr - el)
        rc = np.mean([M.V[i] for i in root], axis=0)
        dirs = _regular_dirs(M, root, rc, ua_ax, 6)
        prev, pv = root, 0.
        spec = [
            (sh + ua_ax * .03, ua_ax, p['upper_arm_r'] * 1.08, _wb('spine', 'upper_arm_' + s, .7), .12),
            (el, _n(ua_ax + fa_ax), p['elbow_r'], _wb('upper_arm_' + s, 'forearm_' + s, .5), .45),
            (el + (wr - el) * .55, fa_ax, p['forearm_r'], {'forearm_' + s: 1.}, .72),
            (wr - fa_ax * .006, fa_ax, p['wrist_r'], _wb('forearm_' + s, 'hand_' + s, .5), 1.),
        ]
        for centre, ax, r, w, v in spec:
            ring = _limb_ring(M, centre, ax, dirs, r, r, w)
            M.loft(prev, ring, arm_cols, pv, v, 'arm', s)
            prev, pv = ring, v
        # mitten hand: flattened across the palm (the palm faces the body), then a blunt tip
        hand = {'hand_' + s: 1.}
        palm_n = _n(np.cross(fa_ax, np.array([0., 0., 1.])))           # roughly +-X: the palm normal
        wide = _n(np.cross(palm_n, fa_ax))                               # roughly +-Z: across the knuckles
        hd = _scaled_dirs(dirs, wide, 1., .55)
        H1 = _limb_ring(M, wr + fa_ax * p['hand_len'] * .4, fa_ax, hd, p['hand_w'] * .5, 0, hand)
        H2 = _limb_ring(M, wr + fa_ax * p['hand_len'] * .78, fa_ax, _scaled_dirs(dirs, wide, 1.02, .42), p['hand_w'] * .52, 0, hand)
        M.loft(prev, H1, arm_cols, 0., .5, 'hand', s)
        M.loft(H1, H2, arm_cols, .5, .85, 'hand', s)
        tip = M.v(wr + fa_ax * p['hand_len'], hand)
        M.fan(H2, tip, arm_cols, .85, 1., 'hand', s)
        # thumb: the palm-ring vertex that faces forward is pulled out into a welded thumb bulge (no separate piece,
        # so there is no join for the rig kit to hold through the clips)
        k_th = max(range(len(H1)), key=lambda k: float(_n(M.V[H1[k]] - (wr + fa_ax * p['hand_len'] * .4)) @ wide))
        M.V[H1[k_th]] = M.V[H1[k_th]] + wide * p['hand_w'] * .32 + fa_ax * p['hand_len'] * .12 - palm_n * .006
    # ---------------- head (8-vertex) from the neck ring
    hs = p['head_h'] / .195
    hw, hd_ = p['head_w'] / 2., p['head_d'] / 2.
    head = {'head': 1.}
    levels = [  # (dy above the neck joint, rx, rz, z offset, v)
        (.03, .70, .74, .014, .86), (.07, .88, .94, .009, .68), (.112, 1., 1., .004, .5), (.152, .95, .97, 0., .3),
        (.182, .64, .68, -.005, .1)]
    prev, pv = T4, 1.
    hr = []
    for dy, fx, fz, oz, v in levels:
        ring = _ring(M, (0., neck_y + dy * hs, oz * hs), hw * fx, hd_ * fz, 8, head)
        M.loft(prev, ring, U8, pv, v, 'head')
        hr.append(ring)
        prev, pv = ring, v
    apex = M.v((0., neck_y + .195 * hs, -.005 * hs), head)
    M.fan(prev, apex, U8, .1, 0., 'head')
    rings['head'] = hr
    rings['apex'] = apex
    return M, rings


# ------------------------------------------------------------------ head surface sampling (for hair/beard/props)
def head_point(M, rings, k, t, out=0.):
    """Point on the head surface at column k (0..8, fractional) and level t (0 = jaw ring .. 4 = crown ring, may go
    beyond 4 toward the apex up to 5), pushed `out` along the horizontal outward normal (plus up near the crown)."""
    hr = rings['head']
    t = max(0., min(5., t))
    if t > 4.:
        a = _ring_point(M, hr[4], k)
        b = M.V[rings['apex']]
        f = t - 4.
        p0 = a * (1 - f) + b * f
        ctr = np.array([0., p0[1], b[2]])
    else:
        i = min(int(t), 3)
        f = t - i
        p0 = _ring_point(M, hr[i], k) * (1 - f) + _ring_point(M, hr[i + 1], k) * f
        c0 = np.mean([M.V[j] for j in hr[i]], axis=0) * (1 - f) + np.mean([M.V[j] for j in hr[i + 1]], axis=0) * f
        ctr = np.array([c0[0], p0[1], c0[2]])
    d = p0 - ctr
    up = max(0., t - 3.) * .5
    nrm = _n(np.array([d[0], 0., d[2]]) + np.array([0., up * (np.linalg.norm(d) + 1e-9), 0.]))
    return p0 + nrm * out


def _ring_point(M, ring, k):
    n = len(ring)
    k = k % n
    i = int(math.floor(k))
    f = k - i
    return M.V[ring[i]] * (1 - f) + M.V[ring[(i + 1) % n]] * f


def hair(M, rings, style, mod, scale=1.):
    """Hair mass: an inset rim inside the skull, a thick shell over the crown, style-specific hanging parts.
    style rows (creator.json modules[*].shape): rim levels per column, thickness, spikes, back length."""
    if mod.get('none'):
        return
    w = {'head': 1.}
    th = mod['thickness'] * scale
    rim = mod['rim']                       # 8 rim levels (k = 0 front .. 7), 0 = jaw ring .. 4 = crown
    cols = U8
    R_in = [M.v(head_point(M, rings, k, rim[k], -.006), w, 'hair') for k in range(8)]
    R_out = [M.v(head_point(M, rings, k, rim[k], th * .7), w, 'hair') for k in range(8)]
    lvl_mid = [max(rim[k], 3.2) for k in range(8)]
    R_mid = [M.v(head_point(M, rings, k, lvl_mid[k] + (4. - lvl_mid[k]) * .45, th), w, 'hair') for k in range(8)]
    R_top = [M.v(head_point(M, rings, k, 4.25, th * mod.get('crown', 1.)), w, 'hair') for k in range(8)]
    M.loft(R_in, R_out, cols, 1., .85, 'hair')
    M.loft(R_out, R_mid, cols, .85, .45, 'hair')
    M.loft(R_mid, R_top, cols, .45, .15, 'hair')
    ap = M.V[rings['apex']] + np.array([0., th * mod.get('crown', 1.) * 1.1, 0.])
    apex = M.v(ap, w, 'hair')
    M.fan(R_top, apex, cols, .15, 0., 'hair', ref=np.mean([M.V[i] for i in R_top], axis=0) - np.array([0., .05, 0.]))
    spikes = mod.get('spikes', 0)
    if spikes:
        # push alternate shell vertices out and up: a spiky silhouette with no extra triangles
        for ring, amt in ((R_mid, .55), (R_top, 1.)):
            for k in range(8):
                if k % 2 == (0 if ring is R_top else 1) and k not in (0,):
                    d = M.V[ring[k]] - np.array([0., M.V[ring[k]][1] - .03, 0.])
                    M.V[ring[k]] = M.V[ring[k]] + _n(np.array([d[0], .6, d[2]])) * spikes * amt * scale
    back = mod.get('back_len', 0.)
    if back > 0:
        # hanging back mass: two extra rings below the rim on the back half, kept clear of the neck and shoulders
        ks = [2, 3, 4, 5, 6]
        top = [R_out[k] for k in ks]
        neck_back = M.V[rings['T4'][4]]
        lows = []
        for f in (.5, 1.):
            row = []
            for k in ks:
                pt = M.V[R_out[k]].copy()
                pt[1] = pt[1] - back * f * scale
                outward = _n(np.array([pt[0], 0., pt[2] - neck_back[2] * .5]))
                clear = .035 + .03 * f
                pt[0] += outward[0] * clear * f
                pt[2] = min(pt[2], neck_back[2] - clear) if k in (3, 4, 5) else pt[2] + outward[2] * clear * f
                row.append(M.v(pt, w, 'hair'))
            lows.append(row)
        prev = top
        vs = [.85, .95, 1.]
        for i, row in enumerate(lows):
            for j in range(len(ks) - 1):
                u0, u1 = cols[ks[j]], cols[ks[j + 1]] if cols[ks[j + 1]] > cols[ks[j]] else 1.
                M.quad(prev[j], prev[j + 1], row[j + 1], row[j], ((u0, vs[i]), (u1, vs[i]), (u1, vs[i + 1]), (u0, vs[i + 1])),
                       'hair', 'c', np.array([0., M.V[row[j]][1], 0.]))
            prev = row
        # close the hanging sheet's inner side back to the skull rim (makes it a mass, not a card)
        inner = [M.v(head_point(M, rings, k, max(0., rim[k] - .2), -.004), w, 'hair') for k in ks]
        for j in range(len(ks) - 1):
            u0, u1 = cols[ks[j]], cols[ks[j + 1]] if cols[ks[j + 1]] > cols[ks[j]] else 1.
            M.quad(prev[j], prev[j + 1], inner[j + 1], inner[j], ((u0, 1.), (u1, 1.), (u1, .9), (u0, .9)), 'hair', 'c',
                   np.array([0., M.V[inner[j]][1] - .3, -.5]))
    fringe = mod.get('fringe', 0.)
    if fringe:
        # bangs: lower the front shell vertices over the brow
        for k in (7, 0, 1):
            M.V[R_out[k]] = M.V[R_out[k]] - np.array([0., fringe * scale, -.004])


def beard(M, rings, mod, scale=1.):
    """A wedge under the chin: root ring inset in the jaw, tip hanging in front of the chest (clear of the torso)."""
    w = {'head': 1.}
    ks = [6, 7, 0, 1, 2]
    lvl = mod['level']
    root = [M.v(head_point(M, rings, k, lvl, -.006), w, 'beard') for k in ks]
    outer = [M.v(head_point(M, rings, k, lvl, .012), w, 'beard') for k in ks]
    jaw_front = M.V[rings['head'][0][0]]
    length = mod['length'] * scale
    tipz = jaw_front[2] + .01 + mod.get('forward', .02)
    mid = [M.v(np.array([M.V[o][0] * .75, M.V[o][1] - length * .5, max(M.V[o][2], tipz - .02)]), w, 'beard') for o in outer]
    tip = M.v(np.array([0., jaw_front[1] - length, tipz]), w, 'beard')
    cols = [.0, .25, .5, .75, 1.]
    for j in range(4):
        M.quad(root[j], root[j + 1], outer[j + 1], outer[j], ((cols[j], 0.), (cols[j + 1], 0.), (cols[j + 1], .15), (cols[j], .15)),
               'beard', 'c', np.array([0., jaw_front[1] + .02, jaw_front[2] - .06]))
        M.quad(outer[j], outer[j + 1], mid[j + 1], mid[j], ((cols[j], .15), (cols[j + 1], .15), (cols[j + 1], .6), (cols[j], .6)),
               'beard', 'c', np.array([0., jaw_front[1] - length * .3, jaw_front[2] - .08]))
    ref = np.array([0., jaw_front[1] - length * .6, jaw_front[2] - .1])
    for j in range(4):
        a, b = mid[j], mid[j + 1]
        if M._outward(a, b, tip, ref):
            M.tri(a, b, tip, (cols[j], .6), (cols[j + 1], .6), ((cols[j] + cols[j + 1]) / 2, 1.), 'beard')
        else:
            M.tri(a, tip, b, (cols[j], .6), ((cols[j] + cols[j + 1]) / 2, 1.), (cols[j + 1], .6), 'beard')
    # close the back of the wedge against the throat side (inside the jaw), so it reads as a mass from the side
    back_ref = np.array([0., jaw_front[1] - length * .5, jaw_front[2] + .2])
    for a, b, c in ((root[0], mid[0], tip), (root[4], mid[4], tip), (root[0], tip, root[2]), (root[2], tip, root[4])):
        if M._outward(a, b, c, back_ref):
            M.tri(a, b, c, (.02, .98), (.02, .98), (.02, .98), 'beard')
        else:
            M.tri(a, c, b, (.02, .98), (.02, .98), (.02, .98), 'beard')


# ------------------------------------------------------------------ rigid props (socket meshes)
class Prop:
    def __init__(self, name, bone):
        self.name, self.bone = name, bone
        self.M = Mesh()


def _closed_loft(M, rings_xyz, part, w, ring_v, cap_bottom=True, apex=None, cols=None, ref_axis=None):
    """Closed lofted solid from a list of point rings (equal length). Returns vertex index rings."""
    n = len(rings_xyz[0])
    cols = cols or [k / n for k in range(n)]
    idx = [[M.v(p, w, part) for p in ring] for ring in rings_xyz]
    for i in range(len(idx) - 1):
        M.loft(idx[i], idx[i + 1], cols, ring_v[i], ring_v[i + 1], part)
    if cap_bottom:
        c = M.v(np.mean(rings_xyz[0], axis=0), w, part)
        M.fan(idx[0], c, cols, ring_v[0], ring_v[0], part, ref=np.mean(rings_xyz[1], axis=0))
    if apex is not None:
        a = M.v(apex, w, part)
        M.fan(idx[-1], a, cols, ring_v[-1], 1., part, ref=np.mean(rings_xyz[-2], axis=0))
    else:
        c = M.v(np.mean(rings_xyz[-1], axis=0), w, part)
        M.fan(idx[-1], c, cols, ring_v[-1], ring_v[-1], part, ref=np.mean(rings_xyz[-2], axis=0))
    return idx


def _circle(c, r, n, phase=0., rz=None, tilt=None):
    rz = r if rz is None else rz
    pts = []
    for k in range(n):
        a = phase + 2 * math.pi * k / n
        pts.append(np.asarray(c, float) + np.array([r * math.sin(a), 0., rz * math.cos(a)]))
    return pts


def hat(J, M_body, rings, mod, scale=1.):
    shape = mod['shape']
    P = Prop('kit_acc_head_hat', 'head')
    w = {'head': 1.}
    crown = M_body.pts(rings['head'][3])
    top_y = float(M_body.V[rings['apex']][1])
    band_y = float(np.mean(crown[:, 1])) - .006
    rx = float(np.ptp(crown[:, 0])) / 2. + .012
    rz = float(np.ptp(crown[:, 2])) / 2. + .012
    cz = float(np.mean(crown[:, 2]))
    hgt = mod.get('height', .1) * scale
    n = 8
    if shape in ('cone', 'cone_bent'):
        brim = mod.get('brim', .05)
        rings_xyz = [_circle((0, band_y - .004, cz), rx + brim, n, rz=rz + brim),
                     _circle((0, band_y + .006, cz), rx + brim * .9, n, rz=rz + brim * .9),
                     _circle((0, band_y + .012, cz), rx, n, rz=rz),
                     _circle((0, band_y + hgt * .45, cz - .01), rx * .6, n, rz=rz * .6)]
        tip = np.array([0., band_y + hgt, cz - .02])
        if shape == 'cone_bent':
            rings_xyz.append(_circle((0, band_y + hgt * .8, cz - .045), rx * .28, n, rz=rz * .28))
            tip = np.array([0., band_y + hgt * .92, cz - .11])
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .9, .8, .45, .15][:len(rings_xyz)], apex=tip)
    elif shape == 'cap':
        rings_xyz = [_circle((0, band_y - .004, cz), rx + .004, n, rz=rz + .004), _circle((0, top_y - .01, cz), rx * .9, n, rz=rz * .9),
                     _circle((0, top_y + .012 * scale, cz), rx * .55, n, rz=rz * .55)]
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .5, .1])
        # visor: a thin wedge forward
        vz = cz + rz + .004
        vis = [[np.array([x, band_y + .004, vz - .02]) for x in (-rx * .7, rx * .7)],
               [np.array([x * .8, band_y - .002, vz + .05 * scale]) for x in (-rx * .7, rx * .7)]]
        a, b = P.M.v(vis[0][0], w, 'hat'), P.M.v(vis[0][1], w, 'hat')
        c, d = P.M.v(vis[1][1], w, 'hat'), P.M.v(vis[1][0], w, 'hat')
        e, f = P.M.v(vis[1][1] + np.array([0, .006, 0]), w, 'hat'), P.M.v(vis[1][0] + np.array([0, .006, 0]), w, 'hat')
        P.M.tri(a, d, c, (.1, .9), (.1, 1.), (.9, 1.), 'hat'); P.M.tri(a, c, b, (.1, .9), (.9, 1.), (.9, .9), 'hat')
        P.M.tri(a, b, e, (.1, .9), (.9, .9), (.9, 1.), 'hat'); P.M.tri(a, e, f, (.1, .9), (.9, 1.), (.1, 1.), 'hat')
        P.M.tri(d, f, e, (.1, 1.), (.1, .95), (.9, .95), 'hat'); P.M.tri(d, e, c, (.1, 1.), (.9, .95), (.9, 1.), 'hat')
    elif shape == 'beanie':
        rings_xyz = [_circle((0, band_y - .012, cz), rx + .006, n, rz=rz + .006), _circle((0, band_y + .02, cz), rx + .008, n, rz=rz + .008),
                     _circle((0, top_y + .004, cz), rx * .7, n, rz=rz * .7)]
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .7, .2], apex=np.array([0., top_y + .02 * scale + .01, cz]))
    elif shape == 'helmet':
        lvl = [(band_y - .03, 1.06), (band_y + .01, 1.08), (top_y - .02, .85), (top_y + .012, .45)]
        rings_xyz = [_circle((0, y, cz), rx * f + .006, n, rz=rz * f + .006) for y, f in lvl]
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .7, .3, .1], apex=np.array([0., top_y + .02 + .03 * (scale - 1), cz]))
    elif shape == 'top_hat':
        brim = .035
        rings_xyz = [_circle((0, band_y - .002, cz), rx + brim, n, rz=rz + brim), _circle((0, band_y + .006, cz), rx + brim, n, rz=rz + brim),
                     _circle((0, band_y + .01, cz), rx * .92, n, rz=rz * .92),
                     _circle((0, band_y + hgt, cz), rx * .98, n, rz=rz * .98)]
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .92, .85, .1])
    elif shape == 'hood':
        # a hood shell around the back and sides of the head, open at the face
        lvl = [(band_y - .1, 1.25), (band_y - .045, 1.22), (band_y + .01, 1.15), (top_y - .005, .85), (top_y + .02, .4)]
        rings_xyz = [_circle((0, y, cz - .01), rx * f + .01, n, rz=rz * f + .012) for y, f in lvl]
        _closed_loft(P.M, rings_xyz, 'hat', w, [1., .8, .55, .25, .1])
    elif shape == 'crown':
        pts = 8
        base = _circle((0, band_y + .006, cz), rx + .002, pts, rz=rz + .002)
        mid = _circle((0, band_y + .03, cz), rx + .006, pts, rz=rz + .006)
        idx_b = [P.M.v(p, w, 'hat') for p in base]
        idx_m = [P.M.v(p, w, 'hat') for p in mid]
        P.M.loft(idx_b, idx_m, [k / pts for k in range(pts)], 1., .5, 'hat')
        for k in range(pts):
            a, b = idx_m[k], idx_m[(k + 1) % pts]
            tipp = (mid[k] + mid[(k + 1) % pts]) / 2. + np.array([0., .045 * scale, 0.])
            t = P.M.v(tipp, w, 'hat')
            ref = np.array([0., band_y + .03, cz])
            if P.M._outward(a, b, t, ref):
                P.M.tri(a, b, t, (k / pts, .5), ((k + 1) / pts, .5), ((k + .5) / pts, 0.), 'hat')
            else:
                P.M.tri(a, t, b, (k / pts, .5), ((k + .5) / pts, 0.), ((k + 1) / pts, .5), 'hat')
            # inner face of the point
            if P.M._outward(a, t, b, ref):
                P.M.tri(a, t, b, (k / pts, .5), ((k + .5) / pts, 0.), ((k + 1) / pts, .5), 'hat')
            else:
                P.M.tri(a, b, t, (k / pts, .5), ((k + 1) / pts, .5), ((k + .5) / pts, 0.), 'hat')
    else:
        raise ValueError('unknown hat shape ' + shape)
    return P


def ears(J, M_body, rings, mod, scale=1.):
    P = Prop('kit_acc_head_ears', 'head')
    w = {'head': 1.}
    shape = mod['shape']
    eye_ring = M_body.pts(rings['head'][2])
    for sg, k in ((1., 2), (-1., 6)):
        side = eye_ring[k].copy()
        side[0] -= sg * .006
        L = mod['length'] * scale
        if shape == 'pointed':           # elf / goblin: back and out along the side
            tip = side + np.array([sg * L * .85, L * .35, -L * .45])
            a, b = side + np.array([0., .022, .01]), side + np.array([0., -.022, -.004])
        elif shape == 'top':             # animal ears on the crown
            crown = M_body.pts(rings['head'][4])
            side = crown[1 if sg > 0 else 7].copy() * .5 + crown[2 if sg > 0 else 6] * .5
            side[1] -= .006
            tip = side + np.array([sg * L * .25, L, -.004])
            a, b = side + np.array([0., 0., .024]), side + np.array([0., 0., -.024])
        elif shape == 'long':            # rabbit
            crown = M_body.pts(rings['head'][4])
            side = crown[1 if sg > 0 else 7].copy()
            side[1] -= .006
            tip = side + np.array([sg * L * .15, L, -.03])
            a, b = side + np.array([0., 0., .02]), side + np.array([0., 0., -.02])
        else:                            # round (bear)
            crown = M_body.pts(rings['head'][4])
            side = crown[2 if sg > 0 else 6].copy()
            side[1] -= .004
            tip = side + np.array([sg * L * .5, L * .8, 0.])
            a, b = side + np.array([0., 0., .028]), side + np.array([0., 0., -.028])
        th = np.array([0., 0., 0.]) + (np.array([sg * -.008, 0., 0.]) if shape == 'pointed' else np.array([0., 0., 0.]))
        mid_in = (a + b) / 2. - np.array([sg * .012, 0., 0.]) + th
        verts = [P.M.v(x, w, 'ears') for x in (a, b, tip, mid_in)]
        cen = np.mean([a, b, tip, mid_in], axis=0)
        for x, y, z in ((0, 1, 2), (0, 2, 3), (1, 3, 2), (0, 3, 1)):
            A, B, Cc = verts[x], verts[y], verts[z]
            if P.M._outward(A, B, Cc, cen):
                P.M.tri(A, B, Cc, (.1, .9), (.9, .9), (.5, .1), 'ears', 'l' if sg > 0 else 'r')
            else:
                P.M.tri(A, Cc, B, (.1, .9), (.5, .1), (.9, .9), 'ears', 'l' if sg > 0 else 'r')
    return P


def horns(J, M_body, rings, mod, scale=1.):
    P = Prop('kit_acc_head_horns', 'head')
    w = {'head': 1.}
    crown = M_body.pts(rings['head'][3])
    for sg, k in ((1., 1), (-1., 7)):
        base = crown[k] * .6 + crown[2 if sg > 0 else 6] * .4
        base = base - np.array([sg * .006, 0., .0])
        L = mod['length'] * scale
        tip = base + np.array([sg * L * .5, L, -L * .3])
        ring = _circle(base, .014, 4)
        _closed_loft(P.M, [ring, _circle((base + tip) / 2. + np.array([sg * .004, 0, 0]), .009, 4)], 'horns', w, [1., .5], apex=tip)
    return P


def muzzle(J, M_body, rings, mod, scale=1.):
    P = Prop('kit_acc_head_muzzle', 'head')
    w = {'head': 1.}
    mouth = M_body.pts(rings['head'][1])
    front = mouth[0].copy()
    front[2] -= .012
    L = mod['length'] * scale
    r = mod.get('radius', .028)
    ring0 = [front + np.array([r * math.sin(a), r * .8 * math.cos(a), 0.]) for a in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
    ring1 = [p + np.array([0., -.004, L * .7]) * 1. - (p - front) * .25 for p in ring0]
    tip = front + np.array([0., -.002, L])
    idx0 = [P.M.v(p, w, 'muzzle') for p in ring0]
    idx1 = [P.M.v(p, w, 'muzzle') for p in ring1]
    cols = [k / 6. for k in range(6)]
    P.M.loft(idx0, idx1, cols, .2, .7, 'muzzle')
    t = P.M.v(tip, w, 'muzzle')
    P.M.fan(idx1, t, cols, .7, 1., 'muzzle', ref=front)
    c = P.M.v(front - np.array([0., 0., .01]), w, 'muzzle')
    P.M.fan(idx0, c, cols, .2, .2, 'muzzle', ref=tip)
    return P


def cape(J, M_body, rings, mod, scale=1.):
    """A thick sheet hanging from the shoulders behind the back (closed: front and back faces + rim)."""
    P = Prop('kit_acc_back_cape', 'spine')
    w = {'spine': 1.}
    T3 = M_body.pts(rings['T3'])
    sh_y = float(np.mean(T3[:, 1]))
    back_z = float(T3[:, 2].min())
    half = float(np.ptp(T3[:, 0])) / 2. + .01
    L = mod['length'] * scale
    rows = [(sh_y + .01, half * .9, back_z - .012), (sh_y - L * .4, half * 1.05, back_z - .05),
            (sh_y - L, half * 1.15, back_z - .085)]
    cols = 4
    th = .012
    outer, inner = [], []
    for y, hw, z in rows:
        ro, ri = [], []
        for c in range(cols + 1):
            x = -hw + 2 * hw * c / cols
            bulge = -.02 * math.cos(math.pi * (c / cols - .5))
            ro.append(P.M.v(np.array([x, y, z + bulge - th]), w, 'cape'))
            ri.append(P.M.v(np.array([x, y, z + bulge]), w, 'cape'))
        outer.append(ro); inner.append(ri)
    ref_out = np.array([0., sh_y - L / 2, back_z + .3])
    for r in range(len(rows) - 1):
        for c in range(cols):
            # outer face on the left half of the cape's rectangle, the lining on the right half
            uo = ((c / cols * .48, r / 2.), ((c + 1) / cols * .48, r / 2.), ((c + 1) / cols * .48, (r + 1) / 2.), (c / cols * .48, (r + 1) / 2.))
            ui = tuple((.52 + u, v) for u, v in uo)
            P.M.quad(outer[r][c], outer[r][c + 1], outer[r + 1][c + 1], outer[r + 1][c], uo, 'cape', 'c', ref_out)
            P.M.quad(inner[r][c], inner[r][c + 1], inner[r + 1][c + 1], inner[r + 1][c], ui, 'cape', 'c',
                     np.array([0., sh_y - L / 2, back_z - .6]))
    # rims: bottom, left, right, top
    for r in (0, len(rows) - 1):
        for c in range(cols):
            P.M.quad(outer[r][c], outer[r][c + 1], inner[r][c + 1], inner[r][c], ((c / cols, .98),) * 4, 'cape', 'c',
                     np.array([0., rows[r][0] + (.3 if r == 0 else -.3), back_z]))
    for c in (0, cols):
        for r in range(len(rows) - 1):
            P.M.quad(outer[r][c], outer[r + 1][c], inner[r + 1][c], inner[r][c], ((.98, r / 2.),) * 4, 'cape', 'c',
                     np.array([(-1 if c == 0 else 1) * -.5 + 0., rows[r][0], back_z]))
    return P


def backpack(J, M_body, rings, mod, scale=1.):
    P = Prop('kit_acc_back_pack', 'spine')
    w = {'spine': 1.}
    T2 = M_body.pts(rings['T2'])
    y = float(np.mean(T2[:, 1]))
    z = float(T2[:, 2].min()) + .012
    hw, hh, dd = .085 * scale, .1 * scale, .06 * scale
    n = 8
    pts0 = [np.array([hw * math.sin(a) * 1.08, y + hh * math.cos(a), z]) for a in np.linspace(0, 2 * math.pi, n, endpoint=False)]
    pts1 = [p + np.array([0., 0., -dd]) for p in pts0]
    pts2 = [np.array([p[0] * .85, y + (p[1] - y) * .85, z - dd - .015]) for p in pts0]
    # build along -Z: rings are vertical, so loft with explicit centre refs
    idx = [[P.M.v(p, w, 'pack') for p in ring] for ring in (pts0, pts1, pts2)]
    cols = [k / n for k in range(n)]
    P.M.loft(idx[0], idx[1], cols, 0., .6, 'pack')
    P.M.loft(idx[1], idx[2], cols, .6, .9, 'pack')
    c0 = P.M.v(np.array([0., y, z]), w, 'pack')
    c2 = P.M.v(np.array([0., y, z - dd - .02]), w, 'pack')
    P.M.fan(idx[0], c0, cols, 0., 0., 'pack', ref=np.array([0., y, z - .2]))
    P.M.fan(idx[2], c2, cols, .9, 1., 'pack', ref=np.array([0., y, z + .2]))
    return P


def tail(J, M_body, rings, mod, scale=1.):
    P = Prop('kit_acc_belt_tail', 'pelvis')
    w = {'pelvis': 1.}
    T0 = M_body.pts(rings['T0'])
    base = np.array([0., float(np.mean(T0[:, 1])) - .01, float(T0[:, 2].min()) + .01])
    L = mod['length'] * scale
    r = mod.get('radius', .03)
    pts = [base, base + np.array([0., -L * .15, -L * .45]), base + np.array([0., L * .05, -L * .85])]
    tip = base + np.array([0., L * .35, -L])
    rings_xyz = []
    for i, c in enumerate(pts):
        rr = r * (1. - .25 * i)
        rings_xyz.append([c + np.array([rr * math.sin(a), rr * math.cos(a), 0.]) for a in np.linspace(0, 2 * math.pi, 5, endpoint=False)])
    _closed_loft(P.M, rings_xyz, 'tail', w, [0., .4, .8], apex=tip)
    return P


def held(J, M_body, rings, mod, scale=1.):
    """A held prop on the right hand socket (cup, staff, book, lantern, wand)."""
    P = Prop('kit_acc_hand_r_' + mod['item'], 'hand_r')
    w = {'hand_r': 1.}
    wr, el = J['hand_r'], J['forearm_r']
    ax = _n(wr - el)
    palm = wr + ax * .06
    it = mod['item']
    if it in ('staff', 'wand'):
        L = (1.3 if it == 'staff' else .3) * scale
        bot = palm - np.array([0., L * .55, 0.])
        top = palm + np.array([0., L * .45, 0.])
        r = .016 if it == 'staff' else .008
        rings_xyz = [_circle(bot, r, 5), _circle(top, r, 5)]
        idx = _closed_loft(P.M, rings_xyz, 'held', w, [1., 0.])
        if it == 'staff':
            orb = [_circle(top + np.array([0, .02, 0]), .035, 6), _circle(top + np.array([0, .07, 0]), .03, 6)]
            _closed_loft(P.M, orb, 'held', w, [.2, 0.], apex=top + np.array([0, .1, 0]))
    elif it == 'cup':
        c = palm + np.array([0., 0., .03])
        rings_xyz = [_circle(c - np.array([0, .03, 0]), .028, 6), _circle(c + np.array([0, .04, 0]), .034, 6)]
        _closed_loft(P.M, rings_xyz, 'held', w, [1., .2])
    elif it == 'book':
        # closed book with a rounded spine and a bulged page edge (a plain box fails the cuboid gate, rightly)
        c = palm + np.array([0., 0., .04])
        prof = ((-.012, -.045), (-.014, .035), (0., .05), (.014, .035), (.012, -.045), (0., -.049))
        rings_xyz = [[c + np.array((x * k, y, z * k)) for x, z in prof] for y, k in ((-.06, 1.), (.06, 1.08))]
        _closed_loft(P.M, rings_xyz, 'held', w, [1., 0.])
    elif it == 'lantern':
        c = palm - np.array([0., .1, 0.])
        rings_xyz = [_circle(c - np.array([0, .05, 0]), .04, 6), _circle(c, .05, 6), _circle(c + np.array([0, .05, 0]), .035, 6)]
        _closed_loft(P.M, rings_xyz, 'held', w, [1., .5, 0.], apex=c + np.array([0, .09, 0]))
    else:
        raise ValueError('unknown held item ' + it)
    return P


PROP_BUILDERS = {'hat': hat, 'ears': ears, 'horns': horns, 'muzzle': muzzle, 'cape': cape, 'backpack': backpack, 'tail': tail,
                 'held': held}


def build(params, data):
    """-> (body Mesh, [Prop], joints) in fractions of height (scaled by finish())."""
    p = params['body']
    J = skeleton(p)
    M, rings = body(p, J)
    props = []
    mods = data['modules']
    for mid in params['modules']:
        m = mods[mid]
        sc = params['module_scale'].get(mid, 1.)
        if m['place'] == 'paint':          # painted modules (stubble, outfits, belts, glasses) add no geometry
            continue
        if m['kind'] == 'hair':
            hair(M, rings, mid, m['shape'], sc)
        elif m['kind'] == 'beard':
            beard(M, rings, m['shape'], sc)
        elif m['kind'] in PROP_BUILDERS:
            props.append(PROP_BUILDERS[m['kind']](J, M, rings, m['shape'], sc))
    return M, props, J, rings


def finish(M, height):
    """Scale fractions of height to metres; returns arrays."""
    V = np.array(M.V) * height
    return V


def vertex_normals(V, F):
    """Area-weighted smooth normals per vertex (welded by index)."""
    F = np.asarray(F)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return N / np.maximum(ln, 1e-12)
