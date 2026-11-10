"""Leg/torso proportion check + generator-side leg bounds (STEER-5 §1). Pure Python 3.9, no Blender.

The silhouette row at height z (orthographic camera at yaw) is the projection of the solid's horizontal
cross-section at z onto the screen x axis, so widths are measured exactly by slicing the mesh (rest pose, or any
posed vertex list) with horizontal planes.

Groups: leg_l = trouser_l + boot_l, leg_r = trouser_r + boot_r; arms (sleeve/mitt/thumb) only count at the shoulder
line; head/hair/visor, props and belt/back accessories are excluded; the torso group is everything else.
Rows (from the rig): thigh = mid hip..knee joints, knee = shin joint, calf = mid knee..ankle, boot = .55 x ankle
joint height, shoulder line = upper-arm joint - .015 H, torso band = waist (spine joint) .. shoulder line - .02 H.

  hip_w      max of (torso-group width over the band thigh joint +- .03 H) and (width of both trouser waistbands
             just under the top of the trousers): the visible hip / waistband line
  torso_w    widest torso-group width over the torso band (arms excluded)
  shoulder_w widest width over the shoulder band (upper-arm joint - .08 H .. joint) including the sleeves
  leg_w      widest single leg over the thigh/knee/calf rows; leg_span = widest outer width covering both legs
  boot_w / boot_span   the same at the boot row
LIMITS: leg_w <= .55 hip_w (Main's rule); leg_span <= 1.10 hip_w (legs continue the hip line; small baggy
allowance); leg_span <= 1.10 torso_w (legs never read wider than the upper body); boot_span <= 1.15 hip_w;
boot_w <= .62 hip_w; idle-stance foot span <= 1.35 shoulder_w.

leg_bounds(...) is the generator-side rule all three humanoid generators apply to their leg rings so that their
output satisfies these limits with margin (BOUND_* < LIMITS).
"""
import math

LIMITS = {'leg_over_hip': .55, 'span_over_hip': 1.10, 'span_over_torso': 1.10, 'boot_span_over_hip': 1.15,
          'boot_over_hip': .62, 'stance_span_over_shoulder': 1.35}
# generator-side targets (margin below LIMITS): single-leg half-width, outer leg extent, boot extent
BOUND_LEG = .52          # rx <= .52 hip_half          (leg_w <= .52 hip_w)
BOUND_SPAN = 1.07        # cx + rx (+ pocket) <= 1.07 min(hip_half, torso_half)
# negative space between the legs (round 13, after legs_compare.png showed merged leg columns): the lower rings keep a
# visible gap at the midline, the thigh ring may touch; units of the generator's x scale (x build/width)
LEG_GAPS = (.012, .010, .008, -.0035)   # ankle, calf, knee, thigh
BOUND_BOOT_SPAN = 1.09   # boot cx + rx <= 1.09 hip_half
BOUND_BOOT = .58         # boot rx <= .58 hip_half
HEAD = ('face', 'nose', 'ear', 'hair', 'extra', 'hood', 'spike', 'leaf', 'visor', 'acc_head', 'lock')
SKIP = ('acc_belt', 'acc_back')
ARMS = ('sleeve', 'mitt', 'thumb')


def group_of(name):
    if name.startswith(('trouser_l', 'boot_l')):
        return 'leg_l'
    if name.startswith(('trouser_r', 'boot_r')):
        return 'leg_r'
    if name.startswith(ARMS):
        return 'arm'
    if name.startswith(HEAD) or name.startswith(SKIP):
        return None
    return 'torso'


def _face_groups(a):
    owner = {}
    for name, ids in a.parts.items():
        g = group_of(name)
        for i in ids:
            owner[i] = g
    return [owner.get(f[0]) for f in a.faces]


def slice_intervals(V, faces, fgroups, z, groups, yaw=0.):
    """Screen-x intervals of the cross-section at height z seen from a camera at yaw (0 = front, camera on -Y;
    screen x = x cos(yaw) + y sin(yaw)), per requested group: {group: [(x0, x1), ...]} merged."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    out = {g: [] for g in groups}
    for f, g in zip(faces, fgroups):
        if g not in out:
            continue
        p = [V[i] for i in f]
        zs = [q[2] for q in p]
        if min(zs) > z or max(zs) < z or max(zs) - min(zs) < 1e-12:
            continue
        xs = []
        for k in range(3):
            a, b = p[k], p[(k + 1) % 3]
            if (a[2] - z) * (b[2] - z) <= 0 and abs(b[2] - a[2]) > 1e-12:
                t = (z - a[2]) / (b[2] - a[2])
                xs.append((a[0] + t * (b[0] - a[0])) * cy + (a[1] + t * (b[1] - a[1])) * sy)
        if len(xs) >= 2:
            out[g].append((min(xs), max(xs)))
    for g in out:
        iv = sorted(out[g])
        merged = []
        for x0, x1 in iv:
            if merged and x0 <= merged[-1][1] + 1e-4:
                merged[-1] = (merged[-1][0], max(merged[-1][1], x1))
            else:
                merged.append((x0, x1))
        out[g] = merged
    return out


def _extent(ivs):
    if not ivs:
        return None
    return (min(i[0] for i in ivs), max(i[1] for i in ivs))


def _width(ivs):
    e = _extent(ivs)
    return 0. if e is None else e[1] - e[0]


def rows(a):
    b = a.bones; H = max(v[2] for v in a.vertices)
    zh = b['thigh_l'][2]; zk = b['shin_l'][2]; za = b['foot_l'][2]
    return {'hip': zh, 'thigh': (zh + zk) / 2, 'knee': zk, 'calf': (zk + za) / 2, 'boot': .55 * za,
            'waist': b['spine'][2], 'shoulder': b['upper_arm_l'][2] - .015 * H}


def measure(a, V=None, yaw=0.):
    V = V or a.vertices
    fg = _face_groups(a)
    R = rows(a)
    H = max(v[2] for v in a.vertices)
    m = {'H': H}

    def sl(z, groups):
        return slice_intervals(V, a.faces, fg, z, groups, yaw)
    hip_t = 0.
    for k in range(7):
        z = R['hip'] - .03 * H + .06 * H * k / 6.
        hip_t = max(hip_t, _width(sl(z, ('torso',))['torso']))
    top = max(V[i][2] for n, ids in a.parts.items() if n.startswith('trouser') for i in ids)
    s = sl(top - .006 * H, ('leg_l', 'leg_r'))
    m['waistband_w'] = _width(s['leg_l'] + s['leg_r'])
    m['hip_w'] = max(hip_t, m['waistband_w'])
    tw = 0.
    for k in range(8):
        z = R['waist'] + (R['shoulder'] - .02 * H - R['waist']) * k / 7.
        tw = max(tw, _width(sl(z, ('torso',))['torso']))
    m['torso_w'] = tw
    shw = 0.
    for k in range(6):                       # shoulder band: upper-arm joint - .08 H .. joint (deltoid region)
        s = sl(R['shoulder'] + .015 * H - .08 * H * k / 5., ('torso', 'arm'))
        shw = max(shw, _width(s['torso'] + s['arm']))
    m['shoulder_w'] = shw
    leg_w = 0.; span = 0.; per_row = {}
    for row in ('thigh', 'knee', 'calf'):
        s = sl(R[row], ('leg_l', 'leg_r'))
        wl, wr = _width(s['leg_l']), _width(s['leg_r'])
        leg_w = max(leg_w, wl, wr)
        sp = _width(s['leg_l'] + s['leg_r'])
        span = max(span, sp)
        per_row[row] = {'leg_l': round(wl, 4), 'leg_r': round(wr, 4), 'span': round(sp, 4)}
    m['leg_w'] = leg_w; m['leg_span'] = span; m['rows'] = per_row
    s = sl(R['boot'], ('leg_l', 'leg_r'))
    m['boot_w'] = max(_width(s['leg_l']), _width(s['leg_r']))
    m['boot_span'] = _width(s['leg_l'] + s['leg_r'])
    return m


def ratios(m):
    hip = max(m['hip_w'], 1e-6)
    return {'leg_over_hip': m['leg_w'] / hip, 'span_over_hip': m['leg_span'] / hip,
            'span_over_torso': m['leg_span'] / max(m['torso_w'], 1e-6),
            'boot_span_over_hip': m['boot_span'] / hip, 'boot_over_hip': m['boot_w'] / hip}


def check(a, V=None, stance_V=None, yaw=0.):
    """Proportion verdict (rest pose unless V is given). stance_V (optional) = vertices posed in the idle stance,
    for the foot-span rule."""
    m = measure(a, V, yaw)
    r = ratios(m)
    if stance_V is not None:
        R = rows(a); fg = _face_groups(a)
        s = slice_intervals(stance_V, a.faces, fg, R['boot'], ('leg_l', 'leg_r'))
        r['stance_span_over_shoulder'] = _width(s['leg_l'] + s['leg_r']) / max(m['shoulder_w'], 1e-6)
    fails = ['%s %.3f > %.2f' % (k, v, LIMITS[k]) for k, v in r.items() if v > LIMITS[k]]
    return {'pass': not fails, 'fails': fails, 'ratios': {k: round(v, 4) for k, v in r.items()},
            'widths': {k: round(m[k], 4) for k in ('hip_w', 'waistband_w', 'torso_w', 'shoulder_w', 'leg_w', 'leg_span',
                                                    'boot_w', 'boot_span')},
            'rows': m['rows']}


# ------------------------------------------------------------------------------------------ generator side
def profile_max(zr, z0, z1, n=9):
    """Max half-width over [z0, z1] of a torso profile given as [(z, half_width), ...] (linear between rings,
    nothing outside the first/last ring)."""
    zr = sorted(zr)
    best = 0.
    for k in range(n):
        z = z0 + (z1 - z0) * k / (n - 1.)
        for (za, ra), (zb, rb) in zip(zr, zr[1:]):
            if za <= z <= zb and zb > za:
                best = max(best, ra + (rb - ra) * (z - za) / (zb - za))
    return best


def leg_bounds(hip_half, torso_half, gap=0.):
    """Return f(cx, rx, extra_out=0.) -> (cx', rx') for one leg ring (all values |x| in the same units).
    rx <= BOUND_LEG * hip_half; cx + rx + extra_out <= BOUND_SPAN * min(hip_half, torso_half);
    cx - rx >= gap (legs may touch at the midline, never cross it). The ring moves inward first (keeps the
    designed bagginess), then thins only if it cannot move further."""
    lim = BOUND_SPAN * min(hip_half, torso_half)
    rmax = BOUND_LEG * hip_half

    def f(cx, rx, extra_out=0.):
        rx = min(rx, rmax)
        if cx + rx + extra_out > lim:
            cx = max(lim - rx - extra_out, rx + gap)
            if cx + rx + extra_out > lim:
                rx = max(1e-4, (lim - extra_out - gap) / 2.)
                cx = rx + gap
        return cx, rx
    return f


def plan_legs(rings, hip_half, torso_half, gap=0., scale=1.):
    """rings: [(cx, rx, extra_out)] for [ankle, calf, knee, thigh] (bottom -> top). Returns [(cx', rx')] in the
    same order. Each ring gets leg_bounds (move inward, then thin) with its own midline gap (LEG_GAPS x scale; gap
    is a floor for every ring); then, if the knee moved inward, the ankle and calf may not splay further outward
    from the knee than designed (no knock-knees). Rings already inside the bound are returned bit-identical."""
    gaps = [max(g * scale, gap) for g in LEG_GAPS]
    out = [leg_bounds(hip_half, torso_half, g)(c, r, e) for (c, r, e), g in zip(rings, gaps)]
    kc, k0 = out[2][0], rings[2][0]
    if kc < k0:
        for i in (0, 1):
            c, r = out[i]
            cap = kc + max(0., rings[i][0] - k0)
            if c > cap:
                c = max(cap, r + gaps[i])
                if c + r > BOUND_SPAN * min(hip_half, torso_half):
                    r = max(1e-4, BOUND_SPAN * min(hip_half, torso_half) - c)
                out[i] = (c, r)
    return out


def boot_bounds(hip_half):
    lim = BOUND_BOOT_SPAN * hip_half; rmax = BOUND_BOOT * hip_half

    def f(cx, rx):
        rx = min(rx, rmax)
        if cx + rx > lim:
            cx = max(lim - rx, rx)
        return cx, rx
    return f
