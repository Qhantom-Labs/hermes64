"""Room clearance and reachability on compiled room data (any kit, any game; nothing names a story).

Mirrors the runtime movement rules of the solid-walls work (move-lane): a capsule of radius 0.26 m, the room
boundary (shell inner wall line, else the grid rectangle with a 0.4 m margin) and every free-standing presentation
piece (not mounted, not a shell/vista, inside the grid) as a solid footprint. Footprints are the rotated XZ bounds of
the bound GLB. A 0.25 m grid is flood-filled from a start point; doors, actor spots and extra targets must be
reachable, and the largest clear square of floor is measured (props pushed to the edges = a big square).

  report = clearance(room, pres, glb_for=lambda key: path)       # dict, see keys below

This is a static check over the authored data, not a runtime proof; the runtime's own solid_navigation remains the
authority on a merged move-lane build.
"""
import json
import math
import struct
from pathlib import Path

CELL = 0.25
RADIUS = 0.26
GRID_MARGIN = 0.4
SHELL_INSET = 1.18            # plot edge -> inner face of a kit shell wall (0.5 apron + 0.5 wall line + 0.18 relief)
NON_SOLID_KINDS = ('shell', 'vista')
_BOUNDS = {}


def glb_bounds(path):
    """XZ/Y bounds (glTF space, metres) of every POSITION accessor in a GLB: (minx, miny, minz, maxx, maxy, maxz)."""
    path = str(path)
    if path not in _BOUNDS:
        data = Path(path).read_bytes()
        n = struct.unpack_from('<I', data, 12)[0]
        doc = json.loads(data[20:20 + n])
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        for mesh in doc.get('meshes', []):
            for prim in mesh.get('primitives', []):
                acc = doc['accessors'][prim['attributes']['POSITION']]
                for i in range(3):
                    lo[i] = min(lo[i], acc['min'][i]); hi[i] = max(hi[i], acc['max'][i])
        _BOUNDS[path] = tuple(lo + hi)
    return _BOUNDS[path]


def footprint(row, bounds):
    """Axis-aligned XZ rect (plot metres) of a placed piece, rotated by its yaw like the socket maths."""
    x0, _, z0, x1, _, z1 = bounds
    yaw = math.radians(float(row.get('yaw', 0)))
    c, s = math.cos(yaw), math.sin(yaw)
    px, _, pz = row['position']
    xs, zs = [], []
    for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
        xs.append(px + x * c + z * s); zs.append(pz - x * s + z * c)
    return (min(xs), min(zs), max(xs), max(zs))


def clearance(room, pres, glb_for, start=None, targets=(), radius=RADIUS, boundary=None):
    """boundary: optional (x0, z0, x1, z1) inner wall line in plot metres for shells this module does not know
    (e.g. medieval halls); default None keeps the historical rule below."""
    w, d = room['grid_size']
    shell = any(p.get('kind') == 'shell' and str(p['asset']).startswith('cyroom.') for p in pres['pieces'])
    if boundary is not None:
        bx0, bz0, bx1, bz1 = (float(v) for v in boundary)
    elif shell and not pres.get('exterior'):
        bx0, bz0, bx1, bz1 = SHELL_INSET, SHELL_INSET, w - SHELL_INSET, d - SHELL_INSET
    elif shell:      # rooftop: parapet line
        bx0, bz0, bx1, bz1 = SHELL_INSET, SHELL_INSET, w - SHELL_INSET, d - SHELL_INSET
    else:
        bx0, bz0, bx1, bz1 = GRID_MARGIN, GRID_MARGIN, w - GRID_MARGIN, d - GRID_MARGIN
    solids = []
    for row in pres['pieces']:
        if row.get('kind') in NON_SOLID_KINDS or row.get('mounted'):
            continue
        b = glb_bounds(glb_for(row['asset']))
        if b[4] - b[1] < 0.12:          # flat decals (puddles, floor cards) never block
            continue
        r = footprint(row, b)
        if r[2] < 0 or r[3] < 0 or r[0] > w or r[1] > d:
            continue
        solids.append((row['asset'], r))
    nx, nz = int(math.ceil(w / CELL)), int(math.ceil(d / CELL))

    def free_at(x, z):
        if not (bx0 + radius <= x <= bx1 - radius and bz0 + radius <= z <= bz1 - radius):
            return False
        for _, (a, b, c, e) in solids:
            if a - radius < x < c + radius and b - radius < z < e + radius:
                return False
        return True

    free = [[free_at((i + 0.5) * CELL, (j + 0.5) * CELL) for j in range(nz)] for i in range(nx)]

    def cell_of(p):
        return (min(nx - 1, max(0, int(p[0] / CELL))), min(nz - 1, max(0, int(p[1] / CELL))))

    def nearest_free(p, reach=1.0):
        ci, cj = cell_of(p)
        k = int(reach / CELL)
        best = None
        for i in range(max(0, ci - k), min(nx, ci + k + 1)):
            for j in range(max(0, cj - k), min(nz, cj + k + 1)):
                if free[i][j]:
                    dd = (i - ci) ** 2 + (j - cj) ** 2
                    if best is None or dd < best[0]:
                        best = (dd, (i, j))
        return best[1] if best else None

    # door approach points: just inside the wall at the door centre
    door_pts = {}
    for dr in room['doors']:
        x = dr['position'] + 0.5
        z = bz0 + radius + 0.3 if dr['wall'] == 'north' else bz1 - radius - 0.3
        door_pts['door:' + dr['id']] = (x, z)
    pts = dict(door_pts)
    for cid, ch in (pres.get('characters') or {}).items():
        if 'position' in ch:
            pts['actor:' + cid] = (ch['position'][0], ch['position'][2])
    for name, p in dict(targets).items():
        pts[name] = tuple(p)
    if start is None:
        start = door_pts.get('door:south') or next(iter(door_pts.values()), (w / 2, d / 2))
    s = nearest_free(start)
    seen = [[False] * nz for _ in range(nx)]
    if s:
        stack = [s]; seen[s[0]][s[1]] = True
        while stack:
            i, j = stack.pop()
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < nx and 0 <= b < nz and free[a][b] and not seen[a][b]:
                    seen[a][b] = True; stack.append((a, b))
    reach = {}
    for name, p in pts.items():
        # actors stand on their spot (their own capsule); the player only has to get within 1.2 m of them
        c = nearest_free(p, 1.2 if name.startswith('actor:') else 0.75)
        reach[name] = bool(c and seen[c[0]][c[1]])
    # largest clear square of reachable capsule-centre cells, reported as physical floor (+ capsule diameter)
    best, at = 0, None
    dp = [[0] * (nz + 1) for _ in range(nx + 1)]
    for i in range(nx):
        for j in range(nz):
            if seen[i][j]:
                dp[i + 1][j + 1] = 1 + min(dp[i][j + 1], dp[i + 1][j], dp[i][j])
                if dp[i + 1][j + 1] > best:
                    best, at = dp[i + 1][j + 1], (i, j)
    side = best * CELL + 2 * radius
    centre = None
    if at:
        centre = [round((at[0] + 1 - best / 2) * CELL, 2), round((at[1] + 1 - best / 2) * CELL, 2)]
    walk = sum(row.count(True) for row in seen) * CELL * CELL
    return {'boundary': [round(v, 2) for v in (bx0, bz0, bx1, bz1)], 'solids': len(solids),
            'reachable': reach, 'all_reachable': all(reach.values()), 'clear_square_m': round(side, 2),
            'clear_centre': centre, 'walkable_m2': round(walk, 1)}
