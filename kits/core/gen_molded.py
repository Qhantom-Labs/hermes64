"""Molded / sculpted furniture (theme-agnostic): seating pods, curled bench, blob desk + consoles.

Rounded, smooth-normal forms built from lathes, swept tubes and inflated lofts. Materials are ROLES
only (a pack decides whether a shell is chrome, glossy plastic, varnished wood or stone)."""
import math

import numpy as np

from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .genutil import finalize, post
from .rng import rng

V = "3.0.0"
SHELL = ["body", "body_alt", "chrome", "metal", "wood", "stone", "leather", "hull", "trim"]
SOFT = ["cushion", "quilt", "fabric", "knit", "fur", "leather"]
STAND = ["chrome", "metal", "wood", "body", "body_alt", "trim"]
PORT = ["band", "glass", "orb", "chrome", "screen"]


# ------------------------------------------------------------------ shared sculpting helpers
def pedestal(x, y, h, r_top, r_base, role, segs=6):
    """Flared trumpet foot (closed lathe): wide soft base, slim waist, small cup under the load."""
    prof = [(0.0, 0.0), (r_base, 0.0), (r_base * 0.78, h * 0.12), (r_top, h * 0.62), (r_top * 1.7, h), (0.0, h)]
    return K.lathe(prof, segs, role, smooth=True).translate(x, y, 0.0)


def puff(outline, z0, t, role, prof=None, dome=1.06, rough=None):
    """Inflated cushion on a star-shaped outline (closed, smooth)."""
    prof = prof or [(0.0, 0.62), (0.18, 0.92), (0.5, 1.0), (0.82, 0.92), (1.0, 0.62)]
    k = len(outline)
    rings = [[(x * sc, y * sc, z0 + zf * t) for x, y in outline] for zf, sc in prof]
    if rough is not None:  # seeded per-vertex wobble (fur throws, lumpy cushions)
        rings = [[(x + rough[(j * k + i) % len(rough)][0], y + rough[(j * k + i) % len(rough)][1], z)
                  for i, (x, y, z) in enumerate(r)] for j, r in enumerate(rings)]
    verts = [p for r in rings for p in r] + [(0.0, 0.0, z0), (0.0, 0.0, z0 + t * dome)]
    cb, ct = len(verts) - 2, len(verts) - 1
    faces = []
    for j in range(len(rings) - 1):
        for i in range(k):
            a, b = j * k + i, j * k + (i + 1) % k
            faces.append((a, b, b + k, a + k))
    last = (len(rings) - 1) * k
    for i in range(k):
        faces.append((cb, (i + 1) % k, i))
        faces.append((ct, last + i, last + (i + 1) % k))
    return K.Mesh().add(verts, faces, role, True).orient_outward()


def disc_port(cx, cy, cz, yaw, rx, rz, role, sides=8, depth=0.014, back=0.05):
    """Round/oval porthole lens facing outward along yaw (radians, 0 = -Y): a flat n-gon face standing
    `depth` proud of the shell, closed by a shallow pyramid whose apex sits `back` inside the shell wall
    (hidden). Closed solid, 2n-2 tris (8 sides = 14)."""
    ring = [(rx * math.cos(math.pi / sides + math.tau * i / sides), -depth, rz * math.sin(math.pi / sides + math.tau * i / sides))
            for i in range(sides)]
    verts = ring + [(0.0, back, 0.0)]
    ap = sides
    faces = [(0, i + 1, i) for i in range(1, sides - 1)]          # outward (-Y) face, fan
    faces += [(i, (i + 1) % sides, ap) for i in range(sides)]    # back pyramid
    d = K.Mesh().add(verts, faces, role, False).orient_outward()
    return d.rotate_z(yaw).translate(cx, cy, cz)


def sphere_orb(cx, cy, cz, r, role="orb", segs=8, rings=5):
    return K.sphere(cx, cy, cz, r, r, r, segs, rings, role, smooth=True)


def _est(parts):
    return int(sum(parts))


# ------------------------------------------------------------------ seating pods
BOWL_OPTS = ((16, 10), (16, 8), (14, 8), (12, 8), (10, 8), (12, 6), (10, 6))  # (shell segments, porthole sides)
SEG_OPTIONS = {"bowl": BOWL_OPTS, "egg": BOWL_OPTS, "lounge_pit": (16, 14, 12, 10),
               "chaise": ((9, 8), (8, 8), (7, 8), (9, 6), (8, 6), (7, 6))}  # chaise: (stations, porthole sides)


def _lathe_tris(m_off_axis, segs):
    """Lathe with poles at both ends: 2 pole fans + (m-1) quad bands."""
    return 2 * segs * m_off_axis


def _pod_parts(P, opt):
    """Exact triangle count of every component for one shell resolution option."""
    k, lob = P["kind"], P["lobes"]
    parts = {}
    if k in ("bowl", "egg"):
        segs, ps = opt
        parts["shell"] = _lathe_tris(6 if k == "bowl" else 7, segs)
        parts["cushion"] = 36 * lob + (64 if (lob or P["cushion"]) else 0)  # 6x4 back lobes + tufted 8-pt seat puff
        parts["ports"] = (2 * ps - 2) * P["portholes"]  # lens: n-gon face + hidden pyramid back
        nf = max(1, P["feet"]) if k == "egg" else P["feet"]
        parts["feet"] = 48 * nf                       # 6-segment trumpet pedestals
    elif k == "chaise":
        stations, ps = opt
        parts["shell"] = 2 * 10 * (stations - 1) + 2 * 8   # 10-point U section, capped ends
        parts["cushion"] = 36 * max(2, lob)
        parts["ports"] = (2 * ps - 2) * P["portholes"]
        parts["feet"] = 48 * max(1, P["feet"])
        parts["canopy"] = 56 if P["canopy"] else 0          # stem tube 20 + visor 36
    else:
        parts["shell"] = 2 * 6 * opt                         # closed 6-point loop revolved
        parts["throws"] = 108 if P["cushion"] else 0
        parts["pillows"] = 20 * lob
        parts["table"] = 62 if P["table"] else 0
        parts["orb"] = 42 if P["orb"] else 0
    return parts


def _pod_option(P, limit=400):
    for opt in SEG_OPTIONS[P["kind"]]:
        if sum(_pod_parts(P, opt).values()) <= limit:
            return opt
    return None


def _pod_rules(P):
    if _pod_option(P) is None:
        est = sum(_pod_parts(P, SEG_OPTIONS[P["kind"]][-1]).values())
        return ("pod detail needs %d tris even at the coarsest shell (furniture_large budget 400): "
                "reduce lobes/portholes/feet/canopy" % est)
    if P["kind"] == "chaise" and P["width"] < 1.4:
        return "chaise needs width >= 1.4 m"
    if P["kind"] == "lounge_pit" and min(P["width"], P["depth"]) < 1.8:
        return "lounge_pit needs width and depth >= 1.8 m"
    if P["kind"] == "lounge_pit" and P["height"] > 0.9:
        return "lounge_pit rim height must be <= 0.9 m"
    return None


def _tilt_rim(mesh, z_lo, f_front, f_back=1.0):
    """Lower the shell above z_lo toward the front (-Y): per-meridian vertical scale about z_lo."""
    def fn(v):
        th = np.arctan2(v[:, 1], v[:, 0])
        f = f_front + (f_back - f_front) * (0.5 - 0.5 * np.cos(th + math.pi / 2))
        out = v.copy()
        up = v[:, 2] > z_lo
        out[up, 2] = z_lo + (v[up, 2] - z_lo) * f[up]
        return out
    return mesh.apply(fn)


def _chaise_station(t, Dp, h, base):
    """(half beam, keel z, U depth) at t in [0, 1] along the chaise (0 = foot end, 1 = head end):
    capsule plan with round ends, almost flat keel, the head end rising gently into a headrest."""
    # r7a critique: blunt flat end caps read as a planter -> narrow caps (near-semicircular plan ends with
    # the cosine stations) and a rocker that curves the bottom up at both ends while the rim stays level
    wt = max(0.2, (1.0 - abs(2 * t - 1) ** 4) ** 0.5)
    back = max(0.0, (t - 0.66) / 0.34)
    rock = 0.12 * h * abs(2 * t - 1) ** 6
    zk = base + 0.03 * h * (2 * t - 1) ** 2 + 0.06 * h * back * back + rock
    u = min(1.0, max(0.0, (t - 0.58) / 0.42))
    D = 0.36 * h + 0.16 * h * u * u * (3 - 2 * u) - rock
    return Dp / 2 * wt, zk, D


def _chaise_shell(L, Dp, h, base, stations, role):
    """Sculpted tub along X: 10-point thick U sections (outer + mirrored inner), cosine-spaced stations
    (round capsule ends). Returns (mesh, floor_fn(x) -> cavity floor z, half_beam_fn, xs)."""
    from .gen_vehicles import capped_loft
    secs, xs, floor, beam = [], [], [], []
    for i in range(stations):
        t = 0.5 - 0.5 * math.cos(math.pi * i / (stations - 1))
        x = -L / 2 + L * t
        b, zk, D = _chaise_station(t, Dp, h, base)
        outer = [(-b, D), (-0.88 * b, 0.32 * D), (0.0, 0.0), (0.88 * b, 0.32 * D), (b, D)]
        th = min(0.13, 0.34 * b)
        s = 1.0 - th / b
        inner = [(px * s, D + (pz - D) * s) for px, pz in reversed(outer)]
        secs.append([(px, pz + zk) for px, pz in outer + inner])
        xs.append(x)
        floor.append(zk + D * (1.0 - s))
        beam.append(b * s)
    m = capped_loft(secs, xs, role, role, smooth=True, mirror_from=5)
    m.apply(lambda v: np.stack([v[:, 1], -v[:, 0], v[:, 2]], 1))  # stations along +X, sections across Y
    m.orient_outward()
    fx = lambda x: float(np.interp(x, xs, floor))
    fb = lambda x: float(np.interp(x, xs, beam))
    return m, fx, fb, xs


@register("furn.pod", V, "furniture_large", {
    "kind": S.enum("bowl", ["bowl", "chaise", "egg", "lounge_pit"]),
    "width": S.num(1.3, 0.6, 3.2), "depth": S.num(1.2, 0.6, 3.2), "height": S.num(0.75, 0.35, 1.6),
    "lobes": S.integer(4, 0, 5, "quilted cushion lobes (pit: small pillows)"),
    "portholes": S.integer(0, 0, 4, "round lens portholes set into the shell"),
    "feet": S.integer(1, 0, 3, "flared pedestal feet"), "cushion": S.boolean(True),
    "canopy": S.boolean(False, "chaise: glass visor egg on a curved stem"),
    "table": S.boolean(True, "lounge_pit: low disc table in the centre"), "orb": S.boolean(True, "lounge_pit: sphere on the table"),
    "shell_role": S.enum("body", SHELL), "cushion_role": S.enum("cushion", SOFT), "throw_role": S.enum("fur", SOFT),
    "port_role": S.enum("band", PORT), "foot_role": S.enum("chrome", STAND),
}, "Molded seating: glossy bowl pod with a front-lowered rim and quilted back lobes, chaise tub of quilted lobes "
   "with lens portholes and trumpet pedestal feet (+ visor), egg chair with a scooped opening, round conversation "
   "pit with throws, pillows and an optional disc table with a sphere. Shell resolution adapts to the detail "
   "requested so the 400-tri budget holds (rule rejects what cannot fit).", rules=_pod_rules)
def pod(P, seed):
    k = P["kind"]
    w, d, h = P["width"], P["depth"], P["height"]
    r = rng(seed, "pod")
    opt = _pod_option(P)
    sr, cr, fr = P["shell_role"], P["cushion_role"], P["foot_role"]
    shell, soft, feet, ports, extra = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    meta = {"kind": k, "shell_resolution": opt if not isinstance(opt, tuple) else list(opt)}
    if k in ("bowl", "egg"):
        segs, ps = opt
        foot_h = 0.16 * h if (P["feet"] or k == "egg") else 0.0
        b = foot_h
        hh = h - foot_h
        if k == "bowl":
            prof = [(0.0, b), (0.40, b + 0.12 * hh), (0.5, b + 0.46 * hh), (0.47, b + 0.78 * hh),
                    (0.43, b + 0.84 * hh), (0.37, b + 0.70 * hh), (0.25, b + 0.44 * hh), (0.0, b + 0.40 * hh)]
            seat_z = b + 0.40 * hh
        else:
            prof = [(0.0, b), (0.24, b), (0.44, b + 0.22 * hh), (0.5, b + 0.5 * hh), (0.42, b + 0.86 * hh),
                    (0.30, b + hh), (0.27, b + 0.95 * hh), (0.38, b + 0.55 * hh), (0.0, b + 0.33 * hh)]
            seat_z = b + 0.33 * hh
        sh = K.lathe(prof, segs, sr, smooth=True, rx=w, ry=d, start=math.pi / segs)
        z_lo = b + (0.45 if k == "bowl" else 0.40) * hh
        _tilt_rim(sh, z_lo, 0.62 if k == "bowl" else 0.3)
        shell.merge(sh)
        if P["lobes"] or P["cushion"]:  # tufted seat puff (centre dimple) sitting in the cavity
            rr = 0.27 if k == "bowl" else 0.31
            soft.merge(puff(K.circle2d(0, 8, rx=w * rr, ry=d * rr, start=math.pi / 8), seat_z - 0.01, 0.17 * hh, cr,
                            prof=[(0.0, 0.72), (0.3, 1.0), (0.72, 0.98), (1.0, 0.62)], dome=0.82))
        n = P["lobes"]
        spread = math.pi * (0.30 + 0.14 * n)
        for i in range(n):  # wide, flat quilted back pads lining the inner wall; neighbours overlap into one
            # tufted backrest instead of separate nuggets (r6 critique: lobes read as gems)
            a = math.pi / 2 + ((i - (n - 1) / 2) * spread / max(1, n - 1) if n > 1 else 0.0)
            lobe = K.blob(0.0, 0.0, 0.0, w * 0.17, d * 0.07, 0.25 * hh, cr, 6, 4, 0.1)
            lobe.rotate_x(-0.42).rotate_z(a - math.pi / 2).translate(math.cos(a) * w * 0.29, math.sin(a) * d * 0.29, seat_z + 0.27 * hh)
            soft.merge(lobe)
        for i in range(P["portholes"]):
            a = -math.pi / 2 + (i - (P["portholes"] - 1) / 2) * 0.55
            px, py = math.cos(a) * w * 0.495, math.sin(a) * d * 0.495
            ports.merge(disc_port(px, py, b + 0.47 * hh, a + math.pi / 2, 0.08 * min(w, d), 0.08 * min(w, d), P["port_role"], ps))
        nf = max(1, P["feet"]) if k == "egg" else P["feet"]
        md = min(w, d)
        if nf == 0:
            spots, rb = [], 0.0
        elif nf == 1:
            spots, rb = [(0.0, 0.0)], md * 0.22
        else:  # feet on a ring, bases sized so neighbouring flares never touch
            rr = md * 0.24
            spots = [(rr * math.cos(math.tau * i / nf + math.pi / 2), rr * math.sin(math.tau * i / nf + math.pi / 2)) for i in range(nf)]
            rb = min(md * 0.16, rr * math.sin(math.pi / nf) * 0.9)
        for x, y in spots:
            feet.merge(pedestal(x, y, foot_h + 0.04, min(0.05, rb * 0.45), rb, fr, 6))
        meta["seat_height"] = round(seat_z + 0.12 * hh, 3)
    elif k == "chaise":
        stations, ps = opt
        L, Dp = w, d
        base = 0.2 * h
        tub, floor_z, half_beam, xs = _chaise_shell(L, Dp, h, base, stations, sr)
        shell.merge(tub)
        n = max(2, P["lobes"])
        t0, t1 = 0.1, 0.9
        seg = L * (t1 - t0) / n
        for i in range(n):
            x = -L / 2 + L * (t0 + (i + 0.5) * (t1 - t0) / n)
            z0 = floor_z(x)
            slope = (floor_z(x + 0.05) - floor_z(x - 0.05)) / 0.1
            rz = 0.22 * h
            lobe = puff(K.superellipse2d(seg * 0.56, half_beam(x) * 0.96, 6, 2.6), -rz * 0.2, rz, cr,
                        prof=[(0.0, 0.8), (0.5, 1.0), (1.0, 0.72)], dome=1.25)
            lobe.rotate_y(-math.atan(slope)).translate(x, 0.0, z0)
            soft.merge(lobe)
        for i in range(P["portholes"]):
            t = 0.22 + (0.62 - 0.22) * (i + 0.5) / P["portholes"]
            x = -L / 2 + L * t
            bq, zk, D = _chaise_station(t, Dp, h, base)
            pr = min(0.3 * D, 0.11)
            ports.merge(disc_port(x, -(0.94 * bq + 0.004), zk + 0.62 * D, 0.0, pr, pr, P["port_role"], ps))
        nf = max(1, P["feet"])
        for i in range(nf):
            x = 0.0 if nf == 1 else (-L * 0.26 + L * 0.48 * i / (nf - 1))
            zb = _chaise_station((x + L / 2) / L, Dp, h, base)[1]
            feet.merge(pedestal(x, 0.0, zb + 0.03, 0.045, min(0.24, Dp * 0.3), fr, 6))
        if P["canopy"]:
            xt = L / 2 - L * 0.06
            zt = base + 0.06 * h + 0.52 * h
            stem = [(xt, 0.0, zt - 0.12), (xt - 0.12, 0.0, zt + 0.16), (xt - 0.38, 0.0, zt + 0.28)]
            extra.merge(K.tube(stem, [0.035, 0.03, 0.025], 4, sr))
            extra.merge(K.sphere(xt - 0.62, 0.0, zt + 0.32, 0.32, Dp * 0.34, 0.15, 6, 4, P["port_role"]))
        meta["seat_height"] = round(floor_z(0.0) + 0.15 * h, 3)
    else:  # lounge_pit
        segs = opt
        R = min(w, d) / 2
        sh_h = h
        loop = [(R * 0.50, 0.0), (R, 0.0), (R * 0.95, sh_h * 0.55), (R * 0.86, sh_h * 0.80), (R * 0.75, sh_h * 0.42),
                (R * 0.54, sh_h * 0.38)]
        seg_roles = [sr, sr, sr, cr, cr, sr]  # underside, berm, rim | backrest, seat (quilted) | seat front
        shell.merge(K.lathe_closed(loop, segs, sr, smooth=True, roles=seg_roles, start=math.pi / segs))
        seat_r = R * 0.645
        if P["cushion"]:  # fur throws draped over the seat ring and up the backrest
            for i in range(3):
                a = math.tau * i / 3 + r.random() * 0.6
                rough = [((r.random() - 0.5) * R * 0.06, (r.random() - 0.5) * R * 0.06) for _ in range(40)]
                th = puff(K.circle2d(0, 6, rx=R * 0.36, ry=R * 0.22), sh_h * 0.41, sh_h * 0.16, P["throw_role"],
                          prof=[(0.0, 0.85), (0.45, 1.0), (1.0, 0.7)], dome=1.3, rough=rough)
                soft.merge(th.rotate_z(a + math.pi / 2).translate(math.cos(a) * seat_r, math.sin(a) * seat_r, 0.0))
        for i in range(P["lobes"]):
            a = math.tau * (i + 0.5) / max(1, P["lobes"]) + 0.3
            pil = K.blob(0.0, 0.0, 0.0, R * 0.17, R * 0.075, sh_h * 0.22, cr, 5, 3, 0.1)
            pil.rotate_x(0.35).rotate_z(a - math.pi / 2).translate(math.cos(a) * R * 0.8, math.sin(a) * R * 0.8, sh_h * 0.62)
            soft.merge(pil)
        if P["table"]:
            tr = R * 0.34
            # stem stops 1 cm under the top: sharing the pole/rim plane made touching, intersecting fans
            # (core30_b pit samples 3 and 14)
            extra.merge(K.lathe([(0.0, 0.0), (0.14, 0.0), (0.05, 0.05), (0.05, 0.30), (0.0, 0.30)], 5, sr))
            extra.merge(K.lathe([(0.0, 0.31), (tr, 0.31), (tr * 1.02, 0.34), (0.0, 0.35)], 8, sr))
            if P["orb"]:
                extra.merge(sphere_orb(0.0, 0.0, 0.35 + tr * 0.24, tr * 0.24, "orb", 7, 4))
        elif P["orb"]:
            extra.merge(sphere_orb(0.0, 0.0, R * 0.12, R * 0.12, "orb", 7, 4))
        meta["seat_height"] = round(sh_h * 0.45, 3)
        meta["walkable_inner_radius_m"] = round(R * 0.5, 3)
    return finalize([Node("pod_shell", shell), Node("pod_cushion", soft), Node("pod_feet", feet), Node("portholes", ports),
                     Node("pod_extra", extra)], meta)


# ------------------------------------------------------------------ curled blob bench
def _bench_rules(P):
    R = (P["curl_height"] - P["seat_height"]) / 2
    if R < 2.2 * P["thickness"]:
        return "curl too tight for the slab thickness: (curl_height - seat_height)/2 = %.2f m < 2.2 x thickness" % R
    if R * 1.25 > P["length"] * 0.5:
        return "curl radius %.2f m too large for bench length %.2f m" % (R, P["length"])
    return None


@register("furn.bench", V, "furniture_large", {
    "length": S.num(2.2, 1.4, 3.2), "depth": S.num(0.6, 0.45, 0.9), "seat_height": S.num(0.42, 0.3, 0.55),
    "curl_height": S.num(1.25, 0.8, 1.7), "curl": S.num(0.7, 0.0, 1.0, "how far the back curls over the seat"),
    "thickness": S.num(0.12, 0.06, 0.2), "legs": S.integer(4, 0, 4), "throw": S.boolean(True),
    "orb": S.boolean(True, "sphere cradled inside the curl"), "side_table": S.boolean(False),
    "body_role": S.enum("chrome", SHELL), "leg_role": S.enum("chrome", STAND), "throw_role": S.enum("fur", SOFT),
}, "Curled blob bench: one sculpted slab sweeping from a rounded seat end up into a breaking-wave curl; "
   "tube legs, draped throw, sphere and small disc table inside the curl.", rules=_bench_rules)
def bench(P, seed):
    L, D, sh, ch = P["length"], P["depth"], P["seat_height"], P["curl_height"]
    t = P["thickness"]
    R = (ch - sh) / 2
    xc = L / 2 - R
    zc = sh + R
    end = math.radians(90.0 + 100.0 * P["curl"])
    path, rad, thk = [], [], []
    for x, f in ((-L / 2 + 0.06, 0.55), (-L / 2 + 0.22, 1.0), (xc - R * 0.6, 1.0)):
        path.append((x, 0.0, sh))
        rad.append(D / 2 * f)
        thk.append(t / 2 * (0.8 + 0.2 * f))
    angs = [-math.pi / 2 + (end + math.pi / 2) * i / 5 for i in range(6)]
    for i, a in enumerate(angs):
        u = i / 5
        path.append((xc + R * math.cos(a), 0.0, zc + R * math.sin(a)))
        rad.append(D / 2 * (1.0 - 0.18 * u))
        thk.append(t / 2 * (1.0 + 0.55 * u * u))  # bulbous rolled tip
    body = K.tube(path, rad, 8, P["body_role"], ry=thk)
    legs = K.Mesh()
    x0, x1 = -L / 2 + 0.3, xc - R * 0.2
    spots = {0: [], 1: [((x0 + x1) / 2, 0.0)], 2: [(x0, 0.0), (x1, 0.0)],
             3: [(x0, D * 0.28), (x0, -D * 0.28), (x1, 0.0)],
             4: [(x0, D * 0.28), (x0, -D * 0.28), (x1, D * 0.28), (x1, -D * 0.28)]}[P["legs"]]
    for x, y in spots:
        legs.merge(post(x, y, 0.0, sh - t * 0.3, 0.022, P["leg_role"], 4))
    if not spots:  # legless: the slab rests on a soft molded plinth (keeps the declared seat height)
        x_a, x_b = -L / 2 + 0.18, xc + R * 0.1
        legs.merge(K.rounded_box((x_a + x_b) / 2, 0.0, (sh - t * 0.3) / 2, x_b - x_a, D * 0.78, sh - t * 0.3, P["body_role"],
                                 bevel=0.7, smooth=True, k_corner=2))
    soft = K.Mesh()
    if P["throw"]:
        tl = (xc - R * 0.5) - (-L / 2 + 0.15)
        th = puff(K.superellipse2d(tl / 2, D * 0.55, 8, 2.6), sh + t * 0.42, 0.05, P["throw_role"],
                  prof=[(0.0, 0.92), (0.45, 1.0), (1.0, 0.9)], dome=1.5)
        soft.merge(th.translate((-L / 2 + 0.15 + xc - R * 0.5) / 2, -D * 0.04, 0.0))
    extra = K.Mesh()
    seat_top = sh + t / 2
    if P["orb"]:  # resting on the seat, cradled at the foot of the curl
        ro = max(0.05, min(R * 0.32, D * 0.22))
        extra.merge(sphere_orb(xc - R * 0.32, D * 0.12, seat_top + ro * 0.96, ro, "orb", 8, 4))
    if P["side_table"]:  # floor-standing disc table in front of the curl (clear of orb and throw)
        tz = seat_top + 0.08
        tx, ty = xc - R * 0.3, -D / 2 - 0.24
        extra.merge(K.lathe([(0.0, 0.0), (0.12, 0.0), (0.03, 0.04), (0.022, tz - 0.004), (0.0, tz - 0.004)], 5,
                            P["leg_role"]).translate(tx, ty, 0.0))
        extra.merge(K.lathe([(0.0, tz), (0.18, tz), (0.18, tz + 0.02), (0.0, tz + 0.02)], 8, "glass").translate(tx, ty, 0.0))
    return finalize([Node("bench_body", body), Node("bench_legs", legs), Node("bench_throw", soft), Node("bench_extra", extra)],
                    {"seat_height": round(sh + t / 2, 3), "curl_radius_m": round(R, 3)})


# ------------------------------------------------------------------ consoles: mushroom pod, blob desk, terminal, lectern
def _console_rules(P):
    if P["kind"] == "desk" and P["height"] > 0.95:
        return "desk top height %.2f m must be <= 0.95 m" % P["height"]
    if P["kind"] == "desk" and P["width"] < 0.5 + 0.6 * P["screens"]:
        return "desk width %.2f m too small for %d monitors (needs >= %.2f m)" % (P["width"], P["screens"], 0.5 + 0.6 * P["screens"])
    return None


def _crt(mw, mh, depth, role):
    """Rounded CRT housing: superellipse bezel tapering back into a tube (10-point rings, 56 tris)."""
    rings = []
    for yy, sx, sz in ((0.0, 1.0, 1.0), (depth * 0.35, 0.94, 0.92), (depth, 0.56, 0.56)):
        rings.append([(x * sx, yy, z * sz) for x, z in K.superellipse2d(mw / 2, mh / 2, 10, 3.2, start=math.pi / 10)])
    return K.loft(rings, role, smooth=True)


@register("furn.console", V, "furniture_large", {
    "kind": S.enum("mushroom", ["mushroom", "desk", "terminal", "lectern"]),
    "height": S.num(1.2, 0.6, 1.8), "width": S.num(0.9, 0.5, 2.4),
    "screens": S.integer(1, 0, 3), "joystick": S.boolean(True), "keyboard": S.boolean(False),
    "wavy": S.num(0.6, 0.0, 1.0, "desk: how strongly the molded rim ripples"),
    "body_role": S.enum("body", SHELL), "leg_role": S.enum("chrome", STAND),
}, "Console: smooth mushroom pod (glowing screen ring + top panels, joystick ledge), blobby kidney desk with a "
   "rippled rolled rim carrying 1-3 rounded CRT monitors on tube legs, terminal, lectern. Screens use role "
   "'screen' (emissive).", rules=_console_rules)
def console(P, seed):
    k, h, w = P["kind"], P["height"], P["width"]
    br = P["body_role"]
    body, scr, ctl = K.Mesh(), K.Mesh(), K.Mesh()
    ns = P["screens"]
    if k == "mushroom":
        R = w / 2
        prof = [(0, 0), (R * 0.72, 0), (R * 0.62, h * 0.06), (R * 0.36, h * 0.24), (R * 0.33, h * 0.5),
                (R * 0.62, h * 0.66), (R, h * 0.8), (R * 0.9, h * 0.95), (0, h)]
        roles = [br] * 8
        if ns:
            roles[6] = "screen"  # glowing band around the cap rim
        body.merge(K.lathe(prof, 14, br, roles=roles, start=math.pi / 14))
        for i in range(max(0, ns - 1)):  # extra screens: shallow panels set into the cap top, facing the user
            x = (i - (ns - 2) / 2) * R * 0.5
            slope = math.atan(0.05 * h / (0.9 * R))  # the cap top rises toward the centre
            z_surf = h * (0.95 + 0.05 * (1.0 - 0.48 / 0.9))
            panel = K.box(0, 0, 0, R * 0.42, R * 0.3, 0.02, "screen").rotate_x(slope).translate(x, -R * 0.48, z_surf + 0.012)
            scr.merge(panel)
        if P["joystick"]:
            ctl.merge(K.lathe([(0, h * 0.5), (R * 0.4, h * 0.5), (R * 0.44, h * 0.53), (0, h * 0.54)], 8, br)
                      .scale(1.0, 0.8, 1.0).translate(0, -R * 0.24, 0))
            ctl.merge(post(0, -R * 0.46, h * 0.53, h * 0.61, 0.012, "metal", 5))
            ctl.merge(K.sphere(0, -R * 0.46, h * 0.62, 0.028, 0.028, 0.028, 6, 4, "orb"))
    elif k == "desk":
        top_z = h
        t = 0.1
        dd = 0.82
        wv = 0.045 * P["wavy"]
        outline, wave = [], []
        for i in range(16):
            a = math.tau * (i + 0.5) / 16
            da = (a - 1.5 * math.pi + math.pi) % math.tau - math.pi
            indent = 0.26 * dd * math.exp(-da * da / 0.3)  # kidney: concave front where the sitter is
            wob = 1.0 + 0.05 * P["wavy"] * math.sin(3 * a + 0.7)
            outline.append((w / 2 * wob * math.cos(a), dd / 2 * wob * math.sin(a) + indent))
            wave.append(wv * math.sin(5 * a + 0.4))
        rings = [[(x * 0.9, y * 0.88, top_z - t) for x, y in outline],
                 [(x, y, top_z - t * 0.5 + zw) for (x, y), zw in zip(outline, wave)],
                 [(x * 0.985, y * 0.98, top_z + zw * 0.5) for (x, y), zw in zip(outline, wave)],
                 [(x * 0.93, y * 0.91, top_z) for x, y in outline]]
        body.merge(K.loft(rings, br, smooth=True))
        for x, y in ((-w * 0.36, -0.12), (w * 0.36, -0.12), (-w * 0.3, 0.24), (w * 0.3, 0.24)):
            body.merge(post(x, y, 0.0, top_z - t * 0.6, 0.024, P["leg_role"], 4))
        mw, mh, md = 0.5, 0.4, 0.34
        span = (ns - 1) * 0.6
        for i in range(ns):
            x = -span / 2 + 0.6 * i
            yaw = -(i - (ns - 1) / 2) * 0.2
            crt = _crt(mw, mh, md, br)
            crt.rotate_z(yaw).translate(x, 0.04, top_z + mh / 2 + 0.005)
            body.merge(crt)
            face = K.box(0, -0.008, 0, mw * 0.78, 0.02, mh * 0.72, "screen").rotate_z(yaw).translate(x, 0.04, top_z + mh / 2 + 0.005)
            scr.merge(face)
        if P["keyboard"]:  # plain slab (12 tris) keeps a 3-monitor desk + keyboard inside 400
            ctl.merge(K.box(0, -0.16, top_z + 0.014, 0.44, 0.15, 0.028, "metal"))
    elif k == "terminal":
        body.merge(K.rounded_box(0, 0, h * 0.35, w * 0.7, 0.5, h * 0.7, br, bevel=0.35, k_corner=1))
        head = K.rounded_box(0, 0, 0, w * 0.7, 0.45, h * 0.35, br, bevel=0.45, k_corner=1).rotate_x(-0.35).translate(0, 0.05, h * 0.85)
        body.merge(head)
        if ns:
            scr.merge(K.box(0, 0, 0, w * 0.5, 0.02, h * 0.22, "screen").rotate_x(-0.35).translate(0, -0.185, h * 0.84))
        if P["keyboard"]:
            ctl.merge(K.box(0, -0.27, h * 0.7, w * 0.55, 0.12, 0.03, "metal"))
    else:  # lectern
        body.merge(K.lathe([(0, 0), (w * 0.3, 0), (w * 0.26, 0.05), (0.06, 0.12), (0.05, h - 0.12), (0, h - 0.1)], 8, br))
        top = K.rounded_box(0, 0, 0, w * 0.7, 0.45, 0.05, br, bevel=0.4, smooth=False, k_corner=1).rotate_x(-0.3).translate(0, 0, h - 0.05)
        body.merge(top)
        if ns:
            scr.merge(K.box(0, 0, 0, w * 0.5, 0.3, 0.012, "screen").rotate_x(-0.3).translate(0, -0.01, h - 0.02))
    return finalize([Node("console_body", body), Node("console_screens", scr), Node("console_controls", ctl)],
                    {"screen_text_slots": ns})
