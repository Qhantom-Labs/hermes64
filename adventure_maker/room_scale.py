"""Room-scale dial (lane SCALE): small (legacy) / medium (default for new games) / large / open.

Pure data planning over the two-room starter that `templates.premise_spec` builds. `apply` keeps every story id,
condition, item and ending; it only writes room grid sizes, door positions, camera anchors and
`metadata.presentation` (kit pieces, actor/collectible/interaction anchors, player start, exterior/fog). `small`
returns the spec untouched, so the legacy starter stays byte-identical.

Layouts are data (`room_layouts.json`): element rules (edge, ring, scatter, walls, along_wall, corners, strip, ...)
over the room grid, using only core kit keys the pack already binds. A static checker mirrors the runtime capsule
grid (`runtime/godot/view/solid_navigation.gd`: 0.25 m cells, capsule radius 0.26 m, bounds margin 0.4 m, solid
footprints for piece/prop/dressing/wall kinds) and measures the clear square, reachability of every door, actor,
collectible and interaction, fill (pieces, coverage, empty patches) and triangles. The runtime measurement
(`runtime/godot/tests/ui5_rooms.gd`, `tools/scale_rooms.py`) stays the authority.
"""
import copy
import json
import math
import random
import re
import struct
from pathlib import Path

from .safety import Fault, fail

DATA = Path(__file__).with_name('room_layouts.json')
SCALES = ('small', 'medium', 'large', 'open')
CELL = 0.25
RADIUS = 0.26          # tuning capsule_radius_m
MARGIN = 0.4           # tuning bounds_margin_m
ACTOR_R = 0.3          # solid_footprints.gd actor capsule (human)
REACH = 1.0            # runner.gd near(): 1.05 m; 1.0 keeps a margin
SOLID_KINDS = ('piece', 'prop', 'dressing', 'wall')   # room.gd piece() registers these kinds as solids
WALKTHROUGH = ('arch.door', 'arch.window', 'arch.floor_module', 'arch.ceiling_module', 'arch.roof', 'arch.stairs',
               'arch.bridge', 'arch.pier', 'nature.grass', 'nature.flower', 'soft.rug', 'soft.blanket', 'terrain.patch',
               'sky.backdrop')   # solid_footprints.gd WALKTHROUGH (kit ids)
KIT_META = Path(__file__).resolve().parents[1] / 'runtime/godot/view/solid_kit_metadata.json'
WALK_MPS, RUN_MPS = 1.1, 3.2   # input/defaults.json walk_speed_mps / run_speed_mps
FACING = {'n': 0.0, 's': 180.0, 'w': 90.0, 'e': -90.0}   # yaw that turns a piece's front (+Z) into the room
_CACHE = {}

# Anchored phrases only: a scale word must name space ("small rooms", "vast", "open air"), never a creature or prop.
PHRASES = (
    ('open', re.compile(r'\b(?:wide[- ]open|open[- ](?:air|world|worlds|spaces?|areas?|plains?|fields?|country|'
                        r'countryside|landscapes?|skies|sky|ground|grounds)|outdoors?|out of doors)\b')),
    ('large', re.compile(r'\b(?:(?:large|big|huge|vast|giant|enormous|spacious|sprawling|expansive|grand|wide)\s+'
                         r'(?:rooms?|spaces?|areas?|maps?|levels?|halls?|world|worlds|places?|grounds?)|'
                         r'vast|spacious|sprawling|expansive)\b')),
    ('medium', re.compile(r'\b(?:medium|mid-sized?|midsized?|moderate)\s+(?:rooms?|spaces?|areas?|maps?|levels?)\b')),
    ('small', re.compile(r'\b(?:(?:small|tiny|little|compact|cramped|cozy|cosy)\s+(?:rooms?|spaces?|areas?|maps?|levels?)|'
                         r'cramped)\b')),
)


def data():
    if 'layouts' not in _CACHE:
        _CACHE['layouts'] = json.loads(DATA.read_text(encoding='utf-8'))
    return _CACHE['layouts']


def default_scale():
    return data()['default_scale']


def check_scale(value, code='new_scale'):
    if not isinstance(value, str) or value.strip().lower() not in SCALES:
        fail(code, 'Unknown room scale %r; choose small, medium, large or open.' % (str(value)[:40],))
    return value.strip().lower()


def keyword(text):
    """(scale, phrase) from anchored phrases in free text, or (None, None)."""
    low = ' '.join(str(text or '').lower().split())
    for scale, pattern in PHRASES:
        m = pattern.search(low)
        if m:
            return scale, m.group(0)
    return None, None


def pick(premise, explicit=None, brief=None, slots=None):
    """(scale, reason). explicit (command word/option) > premise file slot > brief field > prompt words > default."""
    sources = []
    if explicit not in (None, ''):
        sources.append((check_scale(explicit), 'chosen'))
    if (slots or {}).get('room_scale'):
        sources.append((check_scale(slots['room_scale'], 'premise_scale'), 'premise file'))
    if len({s for s, _ in sources}) > 1:
        fail('premise_scale', 'The story chooses room scale %s; remove the conflicting scale word or edit your story file.'
             % sources[1][0])
    if sources:
        return sources[0]
    setting = (brief or {}).get('setting') or {}
    if setting.get('room_scale'):
        return check_scale(setting['room_scale'], 'brief_scale'), 'brief room_scale'
    found, phrase = keyword(premise)
    if found:
        return found, 'auto: matched "%s"' % phrase
    return default_scale(), 'default for new games'


# ----------------------------------------------------------------------------------------------- pack facts
def _quat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _node(n):
    if 'matrix' in n:
        m = n['matrix']
        return [[m[0], m[4], m[8], m[12]], [m[1], m[5], m[9], m[13]], [m[2], m[6], m[10], m[14]]]
    r, s, t = _quat(n.get('rotation', [0, 0, 0, 1])), n.get('scale', [1, 1, 1]), n.get('translation', [0, 0, 0])
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] + [sum(a[i][k] * b[k][3] for k in range(3)) + a[i][3]]
            for i in range(3)]


def glb_facts(path):
    """(bounds (x0, y0, z0, x1, y1, z1) with node transforms, triangle count) of a GLB."""
    raw = Path(path).read_bytes()
    n = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20 + n])
    nodes = doc.get('nodes', [])
    eye = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
    roots = doc['scenes'][doc.get('scene', 0)]['nodes'] if doc.get('scenes') else range(len(nodes))
    todo = [(i, eye) for i in roots]
    lo, hi, tris = [math.inf] * 3, [-math.inf] * 3, 0
    while todo:
        i, m = todo.pop()
        node = nodes[i]
        at = _mul(m, _node(node))
        if 'mesh' in node:
            for prim in doc['meshes'][node['mesh']]['primitives']:
                acc = doc['accessors'][prim['attributes']['POSITION']]
                count = doc['accessors'][prim['indices']]['count'] if 'indices' in prim else acc['count']
                tris += count // 3
                for cx in (acc['min'][0], acc['max'][0]):
                    for cy in (acc['min'][1], acc['max'][1]):
                        for cz in (acc['min'][2], acc['max'][2]):
                            v = [at[r][0] * cx + at[r][1] * cy + at[r][2] * cz + at[r][3] for r in range(3)]
                            lo = [min(lo[k], v[k]) for k in range(3)]
                            hi = [max(hi[k], v[k]) for k in range(3)]
        todo.extend((c, at) for c in node.get('children', []))
    return tuple(lo + hi), tris


class Pack:
    """Bound assets of one bundled pack: bounds/triangles per key, and which pack look data exists."""

    def __init__(self, bundle, pack_id):
        self.id = pack_id
        root = Path(bundle)
        view_path = root / 'packs' / pack_id / 'view.json'
        self.view = json.loads(view_path.read_text(encoding='utf-8')) if view_path.is_file() else {}
        bpath = root / 'packs' / pack_id / 'bindings.json'
        self.assets = json.loads(bpath.read_text(encoding='utf-8')).get('assets', {}) if bpath.is_file() else {}
        self.root = root
        self._facts = {}

    @property
    def has_yards(self):
        return bool((self.view.get('yards') or {}).get('default'))

    @property
    def has_shells(self):
        return bool((self.view.get('shells') or {}).get('default'))

    @property
    def has_look(self):
        return bool((self.view.get('look') or {}).get('profiles'))

    def has(self, key):
        row = self.assets.get(key)
        return isinstance(row, dict) and bool(row.get('glb')) and (self.root / row['glb']).is_file()

    def facts(self, key):
        if key not in self._facts:
            if not self.has(key):
                fail('scale_asset', 'Pack %s does not bind %s.' % (self.id, key))
            path = self.root / self.assets[key]['glb']
            cache_key = (str(path), self.assets[key].get('sha256'))
            if cache_key not in _CACHE:
                _CACHE[cache_key] = glb_facts(path)
            self._facts[key] = _CACHE[cache_key]
        return self._facts[key]

    def kit(self, key):
        return str((self.assets.get(key) or {}).get('kit_id') or key)

    def meta(self, key):
        if 'kit_meta' not in _CACHE:
            path = self.root / 'runtime/godot/view/solid_kit_metadata.json'
            path = path if path.is_file() else KIT_META
            _CACHE['kit_meta'] = json.loads(path.read_text(encoding='utf-8')).get('assets', {}) if path.is_file() else {}
        row = self.assets.get(key) or {}
        out = dict((_CACHE['kit_meta'].get(str(row.get('sha256', ''))) or {}).get('meta') or {})
        out.update(row.get('meta') or {})
        return out

    def walkthrough(self, key):
        return self.kit(key) in WALKTHROUGH or bool(self.meta(key).get('walkthrough'))

    def solid_bounds(self, key):
        """XZ bounds the runtime solid uses (solid_footprints.gd definition): the kit bbox (Blender x, y) centred on
        the glTF bounds centre when the kit metadata has one, else the glTF bounds."""
        b = self.facts(key)[0]
        size = self.meta(key).get('bbox_size_m')
        if not size:
            return b
        cx, cz = (b[0] + b[3]) / 2.0, (b[2] + b[5]) / 2.0
        sx, sz = float(size[0]) / 2.0, float(size[1]) / 2.0
        return (cx - sx, b[1], cz - sz, cx + sx, b[4], cz + sz)


# ----------------------------------------------------------------------------------------------- 2D geometry
def footprint(bounds, x, z, yaw, sx, sz):
    """Oriented XZ rectangle (4 corners) of a placed piece: glTF bounds scaled, turned by yaw (Godot +Y)."""
    x0, _, z0, x1, _, z1 = bounds
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    pts = []
    for lx, lz in ((x0 * sx, z0 * sz), (x1 * sx, z0 * sz), (x1 * sx, z1 * sz), (x0 * sx, z1 * sz)):
        pts.append((x + lx * c + lz * s, z - lx * s + lz * c))
    return pts


def _aabb(poly):
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(zs), max(xs), max(zs)


def seg_dist(p, a, b):
    (px, pz), (ax, az), (bx, bz) = p, a, b
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / max(1e-12, dx * dx + dz * dz)))
    return math.hypot(px - ax - t * dx, pz - az - t * dz)


def inside(poly, p):
    sign = 0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cross) < 1e-12:
            continue
        if sign == 0:
            sign = 1 if cross > 0 else -1
        elif (cross > 0) != (sign > 0):
            return False
    return True


def poly_point_dist(poly, p):
    if inside(poly, p):
        return 0.0
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _segs_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def poly_seg_dist(poly, a, b):
    if inside(poly, a) or inside(poly, b):
        return 0.0
    best = math.inf
    for i in range(len(poly)):
        c, d = poly[i], poly[(i + 1) % len(poly)]
        if _segs_cross(a, b, c, d):
            return 0.0
        best = min(best, seg_dist(c, a, b), seg_dist(d, a, b), seg_dist(a, c, d), seg_dist(b, c, d))
    return best


def polys_gap(p, q):
    """0 when overlapping, else the smallest distance between two convex polygons."""
    if any(inside(p, v) for v in q) or any(inside(q, v) for v in p):
        return 0.0
    return min(poly_seg_dist(p, q[i], q[(i + 1) % len(q)]) for i in range(len(q)))


# ----------------------------------------------------------------------------------------------- planner
class Plan:
    def __init__(self, rid, layout_id, W, D, scale, cfg, pack, seed, doors, treatment):
        self.rid, self.layout_id, self.W, self.D = rid, layout_id, W, D
        self.scale, self.cfg, self.pack, self.treatment = scale, cfg, pack, treatment
        self.layout = data()['layouts'][layout_id]
        self.rng = random.Random('scale:%s:%s:%s:%s' % (layout_id, rid, scale, seed))
        C = float((self.layout.get('core_m') or {}).get(scale, cfg['core_m']))
        self.core_m = C
        x0 = float(self.layout['core_west_m']) if 'core_west_m' in self.layout else (W - C) / 2.0
        self.core = (x0, (D - C) / 2.0, x0 + C, (D + C) / 2.0)
        self.centre = ((self.core[0] + self.core[2]) / 2.0, (self.core[1] + self.core[3]) / 2.0)
        self.doors = doors          # [{'id', 'wall', 'x', 'z', 'approach'}]
        self.items = []             # placed: {'row', 'poly', 'solid', 'h', 'ground', 'tris', 'tag'}
        self.lanes, self.keep, self.anchors = [], [], {}
        self.cam_cone = None
        self.wall_h = 0.0
        self.notes = []

    # -- anchors and keep-outs
    def side_point(self, side, frac, dist):
        W, D = self.W, self.D
        if isinstance(dist, str):       # riverside anchors: 'bank' = on the bank strip, 'bank+1' = 1 m inland
            dist = W - self.water_x0() + 0.45 + (1.0 if dist.endswith('+1') else 0.0)
        return {'n': (frac * W, dist), 's': (frac * W, D - dist), 'w': (dist, frac * D), 'e': (W - dist, frac * D)}[side]

    def water_x0(self):
        """West edge of a riverside water strip: the core edge plus a 0.9 m bank."""
        return self.core[2] + 0.9

    def setup(self, roles):
        a = self.layout['anchors']
        c = self.centre
        for d in self.doors:
            self.lanes.append(((d['x'], d['z']), d['approach'], 1.0, 'door'))
            self.lanes.append((d['approach'], c, 1.0, 'door'))
            self.keep.append((d['approach'], 1.3))
        if 'npc' in roles:
            npc = self.side_point(*a['npc'])
            fin = self.side_point(*a['finish'])
            self.anchors.update(npc=npc, finish=fin)
            self.lanes.append((c, fin, 0.8, 'npc'))
            self.keep += [(npc, 0.95), (fin, 0.8)]
        if 'keepsake' in roles:
            # the keepsake rests on a support piece on the core line (never floating, never inside the clear core)
            side, frac, asset = a['keepsake_on']
            yaw = FACING[side]
            reach = self.inner_extent(asset, (1.0, 1.0, 1.0), yaw, side)
            x, z = self.side_point(side, frac, self.band(side) - reach - 0.08)
            it = self.place({'kind': 'piece'}, asset, x, z, yaw, (1.0, 1.0, 1.0), check=False, tag='support')
            k = (x, z)
            self.anchors['keepsake'] = k
            self.anchors['keepsake_y'] = round(it['top'], 3) if it else 0.0
            self.lanes.append((c, k, 0.8, 'keepsake'))
            self.keep.append((k, 0.2))
        start = (c[0], min(self.D * 0.78, self.core[3] - 0.6))
        self.anchors['start'] = start
        self.lanes.append((c, start, 0.8, 'start'))
        self.keep.append((start, 0.9))
        cam = self.camera()
        cx, cz = cam['position'][0], cam['position'][2]
        if self.layout['kind'] == 'outdoor':
            self.cam_cone = [(cx - 1.6, cz), (cx + 1.6, cz), (self.core[2], self.core[3]), (self.core[0], self.core[3])]
        else:
            self.cam_cone = [(cx - 1.5, cz - 1.5), (cx + 1.5, cz - 1.5), (cx + 1.5, cz + 1.5), (cx - 1.5, cz + 1.5)]

    def camera(self):
        cam = self.cfg['camera']
        c = self.centre
        if self.layout['kind'] == 'outdoor' and self.treatment == 'yard':
            # direction only: room.gd exterior_camera re-frames it on the yard ledge by the pack policy
            pos = [round(c[0], 2), cam['height'], round(self.D + cam['back'], 2)]
            look = [round(c[0], 2), 1.0, round(self.D * cam['look_z'], 2)]
        elif self.layout['kind'] == 'outdoor':
            # behind the south edge, high enough to see over the near dressing, horizon and sky dome in frame
            pos = [round(c[0], 2), round(self.D * 0.4, 2), round(self.D + 3.0, 2)]
            look = [round(c[0], 2), 1.0, round(self.D * cam['look_z'], 2)]
        else:
            h = self.wall_h or 3.0
            pos = [round(c[0], 2), round(max(1.6, h - 0.6), 2), round(self.D - 0.9, 2)]
            look = [round(c[0], 2), 0.9, round(self.D * 0.3, 2)]
        return {'id': 'fixed', 'position': pos, 'look_at': look, 'fov': cam['fov']}

    # -- placement
    def measure(self, asset, scale):
        b, tris = self.pack.facts(asset)
        sx, sy, sz = scale
        return b, tris, (b[4] - b[1]) * sy

    def fits(self, poly, h, solid, el, ground=False, lanes=True, core=True):
        x0, z0, x1, z1 = _aabb(poly)
        out = float(el.get('outside_m', 3.0))
        if x0 < -out or z0 < -out or x1 > self.W + out or z1 > self.D + out:
            return False
        if core and (solid or h > 0.12):
            cx0, cz0, cx1, cz1 = self.core
            corepoly = [(cx0, cz0), (cx1, cz0), (cx1, cz1), (cx0, cz1)]
            if polys_gap(poly, corepoly) <= 0.0:
                return False
        if lanes:
            for a, b, half, _tag in self.lanes:
                if poly_seg_dist(poly, a, b) < half:
                    return False
            for p, r in self.keep:
                if poly_point_dist(poly, p) < r:
                    return False
        if h > 0.9 and self.cam_cone and polys_gap(poly, self.cam_cone) <= 0.0:
            return False
        gap = float(el.get('gap_m', 0.3))
        for it in self.items:
            if it['ground'] or ground or it.get('overhead'):    # ceiling tiles and lintels hang above the floor
                continue
            if polys_gap(poly, it['poly']) < (gap if (solid and it['solid']) else 0.05):
                return False
        return True

    def place(self, el, asset, x, z, yaw=0.0, scale=(1.0, 1.0, 1.0), y=0.0, kind=None, check=True, lanes=True,
              core=True, ground=False, extra=None, tag=''):
        kind = kind or el.get('kind', 'piece')
        if not self.pack.has(asset):
            self.notes.append('gap: %s not bound in %s' % (asset, self.pack.id))
            return None
        b, tris, h = self.measure(asset, scale)
        # room.gd piece() registers every piece/prop/dressing/wall as a solid; solid_navigation.gd ignores bodies
        # wholly above the 1.4 m capsule (lintels, ceilings), and walk-through kits never block
        solid = (kind in SOLID_KINDS and not self.pack.walkthrough(asset)
                 and y + b[1] * scale[1] < 1.4 and y + b[4] * scale[1] > 0.0)
        poly = footprint(self.pack.solid_bounds(asset) if solid else b, x, z, yaw, scale[0], scale[2])
        if check and not self.fits(poly, h, solid, el, ground=ground, lanes=lanes, core=core):
            return None
        row = {'asset': asset, 'kind': kind, 'position': [round(x, 3), round(y, 3), round(z, 3)],
               'scale': [round(v, 3) for v in scale], 'yaw': round(yaw % 360.0, 1)}
        if extra:
            row.update(extra)
        tris = int(((data().get('variant_tris') or {}).get(self.pack.id) or {}).get(asset, tris))   # look variants
        item = {'row': row, 'poly': poly, 'solid': solid, 'h': h, 'top': y + b[4] * scale[1], 'ground': ground,
                'tris': tris, 'tag': tag or el.get('type', ''), 'asset': asset, 'overhead': y + b[1] * scale[1] >= 1.4}
        self.items.append(item)
        return item

    def jitter_scale(self, el):
        lo, hi = el.get('scale', [1.0, 1.0])[:2] if isinstance(el.get('scale', [1, 1]), list) else (el['scale'], el['scale'])
        s = lo + (hi - lo) * self.rng.random()
        return (s, s * (0.9 + 0.2 * self.rng.random()), s)

    # -- element rules
    def el_edge(self, el):
        spots = list(el['at']) + (list(el.get('large_at', [])) if self.scale in ('large', 'open') else [])
        for side, frac in spots:
            b, _, _ = self.measure(el['asset'], (1, 1, 1))
            depth = b[5] - b[2]
            centre_in = float(el.get('front_m', 1.0)) - depth / 2.0
            x, z = self.side_point(side, frac, centre_in)
            self.place(el, el['asset'], x, z, FACING[side], (1.0, 1.0, 1.0), extra={'edge': side} if False else None,
                       tag='edge:' + side)

    def el_anchor(self, el):
        s = float(el.get('scale', 1.0))
        scale = (s, s, s)
        yaw = float(el.get('yaw', self.rng.random() * 360.0 if el.get('kind') != 'landmark' else 0.0))
        if 'at' in el:
            x, z = el['at'][0] * self.W, el['at'][1] if el['at'][1] < 0 else el['at'][1]
            self.place(el, el['asset'], x, z, yaw, scale, check=el.get('kind') != 'landmark')
        elif 'at_lane' in el:
            _, t, off = el['at_lane']
            d = self.doors[0]
            a, b = d['approach'], self.centre
            px, pz = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
            nx, nz = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
            for sign in (1, -1):
                x, z = px + nx * off * sign, pz + nz * off * sign
                yaw = math.degrees(math.atan2(a[0] - x, a[1] - z))
                if self.place(el, el['asset'], x, z, yaw, scale, lanes=True):
                    break
        elif 'at_wall' in el:
            side, frac, inset = el['at_wall']
            x, z = self.side_point(side, frac, inset)
            self.place(el, el['asset'], x, z, FACING[side], scale)

    def el_near(self, el):
        hosts = [it for it in list(self.items) if it['asset'] == el['of']]
        k = 0
        for host in hosts:
            yaw = host['row']['yaw']
            fx, fz = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
            rx, rz = fz, -fx
            b, _, _ = self.measure(el['of'], (1, 1, 1))
            hx, hz = host['row']['position'][0], host['row']['position'][2]
            front = b[5] + float(el.get('front_m', 0.8))
            for j in range(int(el.get('per', 2))):
                asset = el['assets'][k % len(el['assets'])]
                k += 1
                lo, hi = el.get('side_m', [1.5, 3.0])
                side = (lo + (hi - lo) * self.rng.random()) * (1 if j % 2 == 0 else -1)
                x, z = hx + fx * front + rx * side, hz + fz * front + rz * side
                self.place(el, asset, x, z, yaw + (self.rng.random() - 0.5) * 30.0, self.jitter_scale(el) if 'scale' in el else (1, 1, 1))

    def el_gate(self, el):
        if self.treatment == 'yard':
            return
        b, _, _ = self.measure(el['asset'], (1, 1, 1))
        half = (b[3] - b[0]) / 2.0
        for d in self.doors:
            if d['wall'] != 'north':
                continue
            for sign in (-1, 1):
                x = d['x'] + sign * (0.8 + half)
                self.place(el, el['asset'], x, 0.3, 0.0, (1, 1, 1), lanes=False, tag='gate')

    def perimeter(self, inset, sides, spacing):
        W, D = self.W, self.D
        pts = []
        for side in sides:
            L = W if side in ('n', 's') else D
            n = max(1, int(L / spacing))
            for i in range(n):
                t = (i + 0.5) / n
                pts.append((side, self.side_point(side, t, inset)))
        return pts

    def band(self, side):
        """Distance from the wall to the core boundary on one side."""
        cx0, cz0, cx1, cz1 = self.core
        return {'n': cz0, 's': self.D - cz1, 'w': cx0, 'e': self.W - cx1}[side]

    def inner_extent(self, asset, scale, yaw, side):
        """How far the runtime solid footprint reaches from the piece origin toward the room interior."""
        poly = footprint(self.pack.solid_bounds(asset), 0.0, 0.0, yaw, scale[0], scale[2])
        xs, zs = [p[0] for p in poly], [p[1] for p in poly]
        return {'n': max(zs), 's': -min(zs), 'w': max(xs), 'e': -min(xs)}[side]

    def line_inset(self, el, side, asset, scale, yaw):
        """Wall-to-centre distance for an element: 'at_core' puts the piece just outside the core boundary (the core
        stays clear and the boundary is marked, which bounds the clear square); else inset_m from the wall."""
        if el.get('at_core'):
            return self.band(side) - self.inner_extent(asset, scale, yaw, side) - float(el.get('core_gap_m', 0.08))
        if 'inset_band' in el:
            return self.band(side) * float(el['inset_band'])
        return float(el.get('inset_m', 0.0))

    def el_ring(self, el):
        sides = el.get('sides', ['n', 'w', 'e', 's'])
        if el.get('rows') == 'back':
            sides = ['n']
        spacing = float(el['spacing_m'])
        assets = el.get('yard_assets', el['assets']) if self.treatment == 'yard' else el['assets']
        k = 0
        for side in sides:
            L = self.W if side in ('n', 's') else self.D
            n = max(1, int(L / spacing))
            for i in range(n):
                t = (i + 0.5 + (self.rng.random() - 0.5) * 0.35) / n
                for attempt in range(len(assets)):
                    asset = assets[(k + attempt) % len(assets)]
                    scale = self.jitter_scale(el)
                    # core-line pieces turn in quarter steps so their footprint edge sits exactly on the core line
                    yaw = 90.0 * self.rng.randrange(4) if el.get('at_core') else self.rng.random() * 360.0
                    jitter = 0.0 if el.get('at_core') else (self.rng.random() - 0.5) * float(el.get('jitter_m', 0.3))
                    x, z = self.side_point(side, t, self.line_inset(el, side, asset, scale, yaw) + jitter)
                    if self.place(el, asset, x, z, yaw, scale, tag=('core:' if el.get('at_core') else 'ring:') + side):
                        break
                k += 1

    def lattice(self, region):
        x0, z0, x1, z1 = (0.6, 0.6, self.W - 0.6, self.D - 0.6) if region == 'band' else self.core
        pts = [(x0 + i * 0.5, z0 + j * 0.5) for i in range(int((x1 - x0) / 0.5) + 1) for j in range(int((z1 - z0) / 0.5) + 1)]
        if region == 'band':
            cx0, cz0, cx1, cz1 = self.core
            pts = [p for p in pts if not (cx0 <= p[0] <= cx1 and cz0 <= p[1] <= cz1)]
        self.rng.shuffle(pts)
        return pts

    def el_scatter(self, el):
        region = el.get('region', 'band')
        assets = el['assets']
        ground = el.get('kind') == 'floor'
        if region == 'core':
            # stratified (jittered grid) so the open floor has dressing every few metres without a solid in the way
            cx0, cz0, cx1, cz1 = self.core
            cell = float(el.get('cell_m', 3.2))
            nx, nz = max(1, int(round((cx1 - cx0) / cell))), max(1, int(round((cz1 - cz0) / cell)))
            k = 0
            for i in range(nx):
                for j in range(nz):
                    for attempt in range(4):
                        x = cx0 + (i + 0.2 + 0.6 * self.rng.random()) * (cx1 - cx0) / nx
                        z = cz0 + (j + 0.2 + 0.6 * self.rng.random()) * (cz1 - cz0) / nz
                        if self.place(el, assets[k % len(assets)], x, z, self.rng.random() * 360.0, self.jitter_scale(el),
                                      core=False, ground=ground, tag='scatter:core'):
                            break
                    k += 1
            return
        pts = self.lattice(region)
        area = self.W * self.D - (self.core[2] - self.core[0]) * (self.core[3] - self.core[1])
        want = int(round(float(el['per_100m2']) * area / 100.0 * float(self.cfg.get('density', 1.0))))
        placed = k = 0
        for x, z in pts:
            if placed >= want:
                break
            asset = assets[k % len(assets)]
            k += 1
            if self.place(el, asset, x, z, self.rng.random() * 360.0, self.jitter_scale(el), ground=ground, tag='scatter:band'):
                placed += 1

    def el_path(self, el):
        if not self.doors:
            return
        d = self.doors[0]
        a, b = (d['x'], d['z'] + 0.6), self.centre
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        yaw = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))
        step = float(el.get('spacing_m', 2.0))
        n = max(1, int(L / step))
        for i in range(n):
            t = (i + 0.5) / n
            self.place(el, el['asset'], a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, yaw, (0.8, 1.0, 0.8),
                       kind='floor', check=False, ground=True, tag='path')

    def el_plaza(self, el):
        n = int(el.get('tiles', 3))
        b, _, _ = self.measure(el['asset'], (1, 1, 1))
        tw = b[3] - b[0]
        cx0, cz0, cx1, cz1 = self.core
        size = (cx1 - cx0) / n
        s = size / tw
        for i in range(n):
            for j in range(n):
                self.place(el, el['asset'], cx0 + (i + 0.5) * size, cz0 + (j + 0.5) * size, 0.0, (s * 0.96, 1.0, s * 0.96),
                           kind='floor', check=False, ground=True, tag='plaza')

    def el_walls(self, el):
        if self.treatment == 'shell':
            return
        asset = el['asset']
        b, _, _ = self.measure(asset, (1, 1, 1))
        mw, mh, md = b[3] - b[0], b[4] - b[1], b[5] - b[2]
        hs = float(el.get('height_scale', self.cfg.get('wall_height_scale', 1.0)))
        self.wall_h = round(mh * hs, 3)
        W, D = self.W, self.D
        gaps = {'n': [], 's': [], 'w': [], 'e': []}
        for d in self.doors:
            side = {'north': 'n', 'south': 's', 'west': 'w', 'east': 'e'}[d['wall']]
            along = d['x'] if side in ('n', 's') else d['z']
            gaps[side].append((along - 0.75, along + 0.75))
        for side in ('n', 's', 'w', 'e'):
            L = W if side in ('n', 's') else D
            # north/south runs reach over the wall thickness at both ends so the corners are closed
            end = md if side in ('n', 's') else 0.0
            cuts = [-end] + [v for g in sorted(gaps[side]) for v in g] + [L + end]
            for a0, a1 in zip(cuts[0::2], cuts[1::2]):
                seg = a1 - a0
                if seg < 0.2:
                    continue
                n = max(1, int(math.ceil(seg / (mw * float(el.get('stretch', 1.5))) - 0.15)))
                sx = seg / (n * mw) * 1.04          # 2% overlap at each joint: no hairline seams between modules
                for i in range(n):
                    t = a0 + (i + 0.5) * seg / n
                    x, z = self.side_point(side, t / L, -md / 2.0)   # inner face on the grid line (the boundary)
                    self.place(el, asset, x, z, FACING[side], (sx, hs, 1.0), check=False, tag='wall')
            for g0, g1 in gaps[side]:           # lintel above each door frame: the wall stays closed to the ceiling
                door_top = 2.25
                if self.wall_h - door_top > 0.1:
                    t = (g0 + g1) / 2.0
                    x, z = self.side_point(side, t / L, -md / 2.0)
                    self.place(el, asset, x, z, FACING[side], ((g1 - g0) / mw, (self.wall_h - door_top) / mh, 1.0),
                               y=door_top, check=False, extra={'mounted': True}, tag='lintel')
        windows = int(el.get('windows', 0))
        if windows and self.pack.has(el.get('window_asset', 'arch.window')):
            wa = el.get('window_asset', 'arch.window')
            wb, _, _ = self.measure(wa, (1, 1, 1))
            for side in ('w', 'e'):
                for i in range(windows):
                    t = (i + 1.0) / (windows + 1.0)
                    x, z = self.side_point(side, t, 0.02 - wb[2])
                    self.place(el, wa, x, z, FACING[side], (1, 1, 1), kind='window', check=False, tag='window')
        if el.get('ceiling'):
            ca = 'arch.ceiling_module'
            if self.pack.has(ca):
                cb, _, _ = self.measure(ca, (1, 1, 1))
                n = int(self.cfg.get('ceiling_tiles', 3))
                tx, tz = (W + 2 * md) / n, (D + 2 * md) / n      # over the wall tops, tiles overlapping 2%
                for i in range(n):
                    for j in range(n):
                        self.place(el, ca, (i + 0.5) * tx - md, (j + 0.5) * tz - md, 0.0,
                                   (tx / (cb[3] - cb[0]) * 1.04, 1.0, tz / (cb[5] - cb[2]) * 1.04),
                                   y=self.wall_h - 0.01, kind='ceiling', check=False, extra={'mounted': True}, tag='ceiling')

    def el_corners(self, el):
        inset = float(el.get('inset_m', 1.5))
        if 'inset_band' in el:
            inset = min(self.band('w'), self.band('n')) * float(el['inset_band'])
        W, D = self.W, self.D
        corners = [(inset, inset), (W - inset, inset), (inset, D - inset), (W - inset, D - inset)]
        for x, z in corners:
            yaw = math.degrees(math.atan2(self.centre[0] - x, self.centre[1] - z))
            if 'cluster' not in el:
                self.place(el, el['asset'], x, z, yaw, self.jitter_scale(el))
                continue
            base = None
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            group = []
            ok = True
            for part in el['cluster']:
                px, pz = x + part['dx'] * c + part['dz'] * s, z - part['dx'] * s + part['dz'] * c
                y = 0.0
                if part.get('y') in ('top', 'stack') and group:
                    y = group[0]['top'] if part['y'] == 'top' else group[-1]['top']
                pyaw = yaw + (180.0 if part.get('face') == 'in' and part['dx'] > 0 else 0.0) + (90.0 * (1 if part['dx'] < 0 else -1) if part.get('face') == 'in' else 0.0)
                it = self.place(el, part['asset'], px, pz, pyaw, (1, 1, 1), y=y, check=part.get('y') is None, tag='cluster')
                if it is None and part.get('y') is None:
                    ok = False
                    break
                if it is not None:
                    group.append(it)
            if not ok:
                for it in group:
                    self.items.remove(it)

    def el_along_wall(self, el):
        for item in el['items']:
            spacing = float(item['spacing_m'])
            sub = dict(el, **item)
            for side in item['sides']:
                L = self.W if side in ('n', 's') else self.D
                lo, hi = item.get('from', 0.12), item.get('to', 0.88)
                n = max(1, int((hi - lo) * L / spacing))
                scale = tuple(item.get('scale', [1.0, 1.0, 1.0]))
                yaw = FACING[side] + float(item.get('turn', 0.0))
                inset = self.line_inset(sub, side, item['asset'], scale, yaw)
                for i in range(n):
                    t = lo + (hi - lo) * (i + 0.5) / n
                    off = float(item.get('offset_m', 0.0))
                    x, z = self.side_point(side, min(max(t + off / L, 0.02), 0.98), inset)
                    self.place(sub, item['asset'], x, z, yaw, scale, tag=('core:' if item.get('at_core') else 'along:') + side)

    def el_on_top(self, el):
        hosts = [it for it in list(self.items) if it['asset'] == el['of']]
        k = 0
        for host in hosts:
            b, _, _ = self.measure(el['of'], (1, 1, 1))
            hx, hz = host['row']['position'][0], host['row']['position'][2]
            for j in range(int(el.get('per', 1))):
                asset = el['assets'][k % len(el['assets'])]
                k += 1
                ox = (self.rng.random() - 0.5) * (b[3] - b[0]) * 0.5
                oz = (self.rng.random() - 0.5) * (b[5] - b[2]) * 0.4
                yaw = host['row']['yaw']
                c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                self.place(el, asset, hx + ox * c + oz * s, hz - ox * s + oz * c, self.rng.random() * 360.0, (1, 1, 1),
                           y=host['top'], check=False, tag='on_top')

    def strip_x(self, el):
        return self.water_x0(), self.W + float(el.get('outside_m', 1.0))

    def el_strip(self, el):
        b, _, _ = self.measure(el['asset'], (1, 1, 1))
        x0, x1 = self.strip_x(el)
        out = float(el.get('outside_m', 1.0))
        z0, z1 = -out, self.D + out
        sx, sz = (x1 - x0) / (b[3] - b[0]), (z1 - z0) / (b[5] - b[2])
        self.place(el, el['asset'], (x0 + x1) / 2.0, (z0 + z1) / 2.0, 0.0, (sx, 1.0, sz), check=False, ground=True, tag='strip')

    def el_bank(self, el):
        x0, _ = self.strip_x(dict(el, outside_m=1.0))
        spacing = float(el['spacing_m'])
        n = int(self.D / spacing)
        for i in range(n):
            z = (i + 0.5) * self.D / n
            asset = el['assets'][i % len(el['assets'])]
            x = x0 - 0.35 + (self.rng.random() - 0.5) * 0.4
            self.place(el, asset, x, z, self.rng.random() * 360.0, (0.9 + 0.5 * self.rng.random(),) * 3, core=True, tag='bank')

    def el_on_strip(self, el):
        x0, _ = self.strip_x(dict(el, outside_m=1.0))
        for item in el['items']:
            x = x0 + float(item['into_m'])
            z = float(item['at']) * self.D if item['at'] > 0.1 else float(item['at']) * self.D
            self.place(el, item['asset'], x, max(z, -1.0), float(item.get('yaw', 0.0)), (1, 1, 1), check=False,
                       ground=True, tag='on_strip')

    def build(self, roles):
        if self.layout['kind'] == 'indoor':
            for el in self.layout['elements']:          # walls first: the camera sits under the wall height
                if el['type'] == 'walls':
                    self.el_walls(el)
            if self.treatment == 'shell':
                self.wall_h = float(((self.pack.view.get('shells') or {}).get('default') or {}).get('height', 3.0))
        self.setup(roles)
        for el in self.layout['elements']:
            if el.get('treatment') and el['treatment'] != self.treatment:
                continue
            if el['type'] == 'walls' and self.layout['kind'] == 'indoor':
                continue
            getattr(self, 'el_' + el['type'])(el)
        self.budget()

    def tris(self):
        return sum(it['tris'] for it in self.items)

    def actor_tris(self):
        """Reserve for a room character (bundled cast bodies are 720-768 triangles); the player is in base_tris."""
        return int(data()['runtime_tris']['npc']) if 'npc' in self.anchors else 0

    # dressing dropped first when a room is over its triangle budget; structure (walls, buildings, gates) never
    DROP_ORDER = ('scatter:band', 'on_top', 'near', 'scatter:core', 'plaza', 'path', 'bank', 'cluster', 'ring:', 'along:',
                  'core:')

    def budget(self):
        """Drop dressing (by DROP_ORDER, latest first) until the room's static estimate leaves the actor reserve."""
        cap = (min(int(self.cfg['tri_budget']), 6000) - self.actor_tris() - self.base_tris()
               - int(data()['runtime_tris']['margin']))
        dropped = 0
        while self.tris() > cap:
            victims = []
            for prefix in self.DROP_ORDER:
                victims = [it for it in self.items if it['tag'].startswith(prefix)]
                if victims:
                    break
            if not victims:
                break
            # keep the core-line markers (they bound the clear square): drop the costliest of the latest five
            pool = victims[-5:]
            self.items.remove(max(pool, key=lambda it: it['tris']))
            dropped += 1
        if dropped:
            self.notes.append('budget: dropped %d dressing pieces to stay under %d triangles' % (dropped, cap + self.base_tris()))

    def base_tris(self):
        """Triangles the runtime adds that the plan does not list (player, floor or yard, pack exterior composition,
        shell, door frames): measured per treatment and pack (room_layouts.json runtime_tris)."""
        rt = data()['runtime_tris']
        row = rt[self.treatment]
        return int(row.get(self.pack.id, row['default']) if isinstance(row, dict) else row)

    # -- presentation
    def presentation(self, roles):
        rows = [it['row'] for it in self.items]
        out = {'cameras': [self.camera()], 'pieces': rows}
        outdoor = self.layout['kind'] == 'outdoor'
        if outdoor:
            out['exterior'] = True
        if self.treatment == 'yard':
            out['yard'] = {'ponds': []}      # the layout owns water; a yard pond could land in the clear core
            out['layout_dressing'] = True    # room.gd compose_exterior: no legacy-offset clusters/rhythm
            out['clear_core'] = [round(v, 2) for v in self.core]    # pack framing stands beside it, never inside
        if outdoor and self.treatment == 'plain':
            W, D = self.W, self.D
            if self.pack.has('terrain.patch'):
                b, _ = self.pack.facts('terrain.patch')
                out['floor'] = 'terrain.patch'
                out['floor_scale'] = [round((W + 10.0) / (b[3] - b[0]), 3), 0.3, round((D + 10.0) / (b[5] - b[2]), 3)]
            extra = []
            if self.pack.has('sky.backdrop'):
                extra.append({'asset': 'sky.backdrop', 'kind': 'backdrop', 'position': [W / 2.0, -1.0, D / 2.0],
                              'scale': [0.1, 0.1, 0.1], 'yaw': 0.0})
            if self.pack.has('terrain.vista'):
                b, _ = self.pack.facts('terrain.vista')
                s = round(2.0 * (max(W, D) / 2.0 + 30.0) / (b[3] - b[0]), 3)
                extra.append({'asset': 'terrain.vista', 'kind': 'vista', 'position': [W / 2.0, 0.0, D / 2.0],
                              'scale': [s, 1.0, s], 'yaw': 0.0})
            out['pieces'] = extra + rows
        out.update(self.fog(outdoor))
        if self.treatment == 'plain' and (any(it['tag'] in ('gate', 'wall') for it in self.items) or not outdoor):
            out['kit_shell'] = True
        if self.wall_h and self.layout['kind'] == 'indoor':
            out['wall_height'] = self.wall_h
        if 'start' in roles:
            sx, sz = self.anchors['start']
            out['player_start'] = [round(sx, 2), 0.0, round(sz, 2)]
        return out

    def fog(self, outdoor):
        """Push the fog out with the room: near/far shift by the extra half-size over the legacy 4 m room, colour and
        maximum stay the pack's. Look packs: presentation.look.fog (the rig replaces the whole fog dict); legacy packs:
        presentation.fog (presenter.gd applies near/far, pack colour), scaled by the room ratio instead."""
        shift = (max(self.W, self.D) - 4.0) / 2.0
        look = (self.pack.view.get('look') or {}).get('profiles') or {}
        if look:
            name = 'exterior' if outdoor else 'interior'
            base = dict((look.get(name) or look.get('interior') or {}).get('fog') or {})
            if not base:
                return {}
            base.update(near=round(float(base.get('near', 6.0)) + shift, 2), far=round(float(base.get('far', 28.0)) + shift, 2))
            return {'look': {'fog': base}}
        # legacy pack fog was tuned for the 4 m starter (fog starts just past the far wall): scale with the room
        base = self.pack.view.get('fog') or {}
        k = max(self.W, self.D) / 4.0
        out = {'near': round(float(base.get('near', 6.0)) * k, 2), 'far': round(float(base.get('far', 28.0)) * k, 2)}
        src = self.shared_sky_fog() if outdoor else None
        if src:     # outdoors: the exterior fog another pack tuned for this same sky asset (room_layouts.json)
            out = {'color': src['color'], 'max': float(src.get('max', 1.0)),
                   'near': round(float(src.get('near', 6.0)) + shift, 2), 'far': round(float(src.get('far', 28.0)) + shift, 2)}
            if 'sky_fog_scale' in src:      # and that pack's sky material response (its sky dome is not fogged flat)
                out['sky_fog_scale'] = float(src['sky_fog_scale'])
        return {'fog': out}

    def shared_sky_fog(self):
        """Exterior fog of the pack named in room_layouts.json legacy_exterior_fog, used only when that pack binds the
        very same sky.backdrop file (its exterior fog was tuned against this sky); else None."""
        row = (data().get('legacy_exterior_fog') or {}).get(self.pack.id)
        if not row:
            return None
        other = Pack(self.pack.root, row['from'])
        mine, theirs = self.pack.assets.get('sky.backdrop') or {}, other.assets.get('sky.backdrop') or {}
        if not mine.get('glb') or mine.get('glb') != theirs.get('glb'):
            return None
        look = other.view.get('look') or {}
        fog = dict(((look.get('profiles') or {}).get('exterior') or {}).get('fog') or {})
        sky = (look.get('materials') or {}).get('sky') or {}
        if 'fog_scale' in sky:
            fog['sky_fog_scale'] = sky['fog_scale']
        return fog if fog.get('color') else None

    # -- static measurement (mirrors runtime/godot/view/solid_navigation.gd)
    def solids(self, extra_actor=None):
        polys = [it['poly'] for it in self.items if it['solid']]
        actors = []
        if 'npc' in self.anchors:
            actors.append(self.anchors['npc'])
        return polys, actors

    def grid(self, start):
        W, D = self.W, self.D
        nx, nz = int(math.ceil(W / CELL)), int(math.ceil(D / CELL))
        polys, actors = self.solids()
        boxes = [(_aabb(p), p) for p in polys]
        free = [[False] * nz for _ in range(nx)]
        for i in range(nx):
            px = (i + 0.5) * CELL
            if px < MARGIN or px > W - MARGIN:
                continue
            for j in range(nz):
                pz = (j + 0.5) * CELL
                if pz < MARGIN or pz > D - MARGIN:
                    continue
                ok = True
                for (x0, z0, x1, z1), poly in boxes:
                    if x0 - RADIUS < px < x1 + RADIUS and z0 - RADIUS < pz < z1 + RADIUS and poly_point_dist(poly, (px, pz)) < RADIUS:
                        ok = False
                        break
                if ok:
                    for ax, az in actors:
                        if math.hypot(px - ax, pz - az) < ACTOR_R + RADIUS:
                            ok = False
                            break
                free[i][j] = ok
        si, sj = min(nx - 1, int(start[0] / CELL)), min(nz - 1, int(start[1] / CELL))
        best = None
        for i in range(max(0, si - 3), min(nx, si + 4)):
            for j in range(max(0, sj - 3), min(nz, sj + 4)):
                if free[i][j]:
                    dd = (i - si) ** 2 + (j - sj) ** 2
                    if best is None or dd < best[0]:
                        best = (dd, i, j)
        seen = [[False] * nz for _ in range(nx)]
        if best:
            stack = [(best[1], best[2])]
            seen[best[1]][best[2]] = True
            while stack:
                i, j = stack.pop()
                for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if 0 <= a < nx and 0 <= b < nz and free[a][b] and not seen[a][b]:
                        seen[a][b] = True
                        stack.append((a, b))
        return nx, nz, free, seen

    def report(self, roles):
        start = self.anchors['start'] if 'start' in roles else (self.doors[0]['approach'] if self.doors else self.centre)
        nx, nz, free, seen = self.grid(start)
        targets = {'door:' + d['id']: (d['approach'], REACH) for d in self.doors}
        if 'npc' in self.anchors:
            targets['actor:inhabitant'] = (self.anchors['npc'], REACH + ACTOR_R)
            targets['interact:finish'] = (self.anchors['finish'], REACH)
        if 'keepsake' in self.anchors:
            targets['collect:keepsake'] = (self.anchors['keepsake'], REACH)
        reach = {}
        for name, (p, r) in targets.items():
            ok = False
            k = int(r / CELL) + 1
            ci, cj = int(p[0] / CELL), int(p[1] / CELL)
            for i in range(max(0, ci - k), min(nx, ci + k + 1)):
                for j in range(max(0, cj - k), min(nz, cj + k + 1)):
                    if seen[i][j] and math.hypot((i + 0.5) * CELL - p[0], (j + 0.5) * CELL - p[1]) <= r:
                        ok = True
                        break
                if ok:
                    break
            reach[name] = ok
        best, dp = 0, [[0] * (nz + 1) for _ in range(nx + 1)]
        for i in range(nx):
            for j in range(nz):
                if seen[i][j]:
                    dp[i + 1][j + 1] = 1 + min(dp[i][j + 1], dp[i + 1][j], dp[i][j])
                    best = max(best, dp[i + 1][j + 1])
        clear = round(best * CELL + 2 * RADIUS, 2)
        walk = round(sum(r.count(True) for r in seen) * CELL * CELL, 1)
        fill = self.fill(nx, nz, seen)
        door = self.doors[0]['approach'] if self.doors else self.centre
        far = max((math.hypot((i + 0.5) * CELL - door[0], (j + 0.5) * CELL - door[1]), i, j)
                  for i in range(nx) for j in range(nz) if seen[i][j]) if walk else (0.0, 0, 0)
        crossing = round(far[0], 2)
        tris = self.tris() + self.base_tris()
        return {'id': self.rid, 'layout': self.layout_id, 'kind': self.layout['kind'], 'treatment': self.treatment,
                'grid_m': [self.W, self.D], 'core_m': self.cfg['core_m'], 'clear_square_m': clear, 'walkable_m2': walk,
                'reachable': reach, 'all_reachable': all(reach.values()), 'crossing_m': crossing,
                'crossing_walk_s': round(crossing / WALK_MPS, 1), 'crossing_run_s': round(crossing / RUN_MPS, 1),
                'clear_walk_s': round(clear / WALK_MPS, 1), 'clear_run_s': round(clear / RUN_MPS, 1),
                'pieces': len(self.items), 'solid_pieces': sum(1 for it in self.items if it['solid']),
                'tris_estimate': tris, 'tris_pieces': self.tris(), 'tris_runtime_added': self.base_tris(),
                'actor_reserve_tris': self.actor_tris(), **fill,
                'notes': list(self.notes)}

    def fill(self, nx, nz, seen):
        occupied = [[False] * nz for _ in range(nx)]
        solid_cells = 0
        for it in self.items:
            if it['row']['kind'] in ('ceiling',) or it['tag'] == 'strip':
                continue
            x0, z0, x1, z1 = _aabb(it['poly'])
            for i in range(max(0, int(x0 / CELL)), min(nx, int(x1 / CELL) + 1)):
                for j in range(max(0, int(z0 / CELL)), min(nz, int(z1 / CELL) + 1)):
                    p = ((i + 0.5) * CELL, (j + 0.5) * CELL)
                    if not occupied[i][j] and inside(it['poly'], p):
                        occupied[i][j] = True
                        if it['solid']:
                            solid_cells += 1
        cover_any = sum(r.count(True) for r in occupied)
        # empty-floor patches: walkable cells farther than 3 m from any placed piece (any kind) and from the boundary
        pts = [((i + 0.5) * CELL, (j + 0.5) * CELL) for i in range(nx) for j in range(nz) if occupied[i][j]]
        far = []
        step = 2
        for i in range(0, nx, step):
            for j in range(0, nz, step):
                if not seen[i][j]:
                    continue
                p = ((i + 0.5) * CELL, (j + 0.5) * CELL)
                edge = min(p[0], p[1], self.W - p[0], self.D - p[1])
                near = min([math.hypot(p[0] - q[0], p[1] - q[1]) for q in pts] + [edge])
                if near > 3.0:
                    far.append((i // step, j // step, near))
        patches, rmax = 0, 0.0
        cells = {(a, b): r for a, b, r in far}
        left = set(cells)
        while left:
            patches += 1
            stack = [left.pop()]
            while stack:
                a, b = stack.pop()
                rmax = max(rmax, cells[(a, b)])
                for q in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if q in left:
                        left.remove(q)
                        stack.append(q)
        area = nx * nz
        return {'coverage_pct': round(100.0 * solid_cells / area, 1), 'dressed_pct': round(100.0 * cover_any / area, 1),
                'empty_patches_gt3m': patches, 'largest_empty_radius_m': round(rmax, 2)}


# ----------------------------------------------------------------------------------------------- spec rewrite
def treatment_for(layout, pack):
    if layout['kind'] == 'outdoor':
        return 'yard' if pack.has_yards else 'plain'
    return 'shell' if pack.has_shells else 'plain'


def choose_layouts(premise, pack_id, scale, explicit=None):
    """{'room_a': id, 'room_b': id, 'why': {...}} from the pack (room_a) and premise words (room_b)."""
    d = data()
    explicit = dict(explicit or {})
    for rid, lid in explicit.items():
        if lid not in d['layouts']:
            fail('scale_layout', 'Unknown room layout %r; choose %s.' % (str(lid)[:40], ', '.join(sorted(d['layouts']))))
    tokens = re.findall(r'[a-z]+', str(premise).lower())
    hits = {k: [w for w in tokens if w in set(v)] for k, v in d['words'].items()}
    why = {}
    a = explicit.get('room_a') or d['pack_outdoor'].get(pack_id)
    why['room_a'] = 'chosen' if 'room_a' in explicit else 'pack outdoor layout'
    if a is None:
        a = 'forest_clearing'
        why['room_a'] = 'no pack outdoor layout; forest clearing'
    b = explicit.get('room_b')
    if b:
        why['room_b'] = 'chosen'
    else:
        indoor = [k for k in ('library', 'workshop', 'hall') if hits.get(k)]
        indoor.sort(key=lambda k: -len(hits[k]))
        if indoor and scale != 'open':
            b = indoor[0]
            why['room_b'] = 'auto: matched ' + ', '.join('"%s"' % w for w in dict.fromkeys(hits[b]))
        elif hits.get('water'):
            b = d['second_outdoor']['water']
            why['room_b'] = 'auto: matched ' + ', '.join('"%s"' % w for w in dict.fromkeys(hits['water']))
        else:
            b = d['second_outdoor']['default']
            why['room_b'] = 'default second outdoor layout' + (' (open: no interiors)' if indoor and scale == 'open' else '')
        if b == a:
            b = 'courtyard' if a != 'courtyard' else 'riverside'
    return {'room_a': a, 'room_b': b, 'why': why}


def apply(spec, scale, pack_id, premise, bundle_root, layouts=None, seed=7, check=True):
    """(spec, report). 'small' and non-starter templates return the spec unchanged. check=False skips the static gates
    (diagnostics only; the report still carries every measurement)."""
    scale = check_scale(scale)
    report = {'format': 'hermes64-room-scale/1', 'scale': scale, 'applied': False}
    if scale == 'small':
        report['reason'] = 'legacy starter (4 x 4 m rooms), unchanged'
        return spec, report
    if spec.get('metadata', {}).get('template') != 'two_room_collect_v1' or [r['id'] for r in spec.get('rooms', [])] != ['room_a', 'room_b']:
        report['reason'] = 'room scale applies to the two-room starter only; %s keeps its authored rooms' % spec.get('metadata', {}).get('template')
        return spec, report
    d = data()
    cfg = d['scales'][scale]
    pack = Pack(bundle_root, pack_id)
    missing = [k for k in d['required_keys'] if not pack.has(k)]
    if missing:
        report['reason'] = ('pack %s lacks core kit pieces for open layouts (%s); rooms keep the legacy size. Route: '
                            'generate the missing pieces (hermes64 generator recipes) or pick village, forest or polar.'
                            % (pack_id, ', '.join(missing)))
        report['gaps'] = missing
        return spec, report
    chosen = choose_layouts(premise, pack_id, scale, layouts)
    if cfg.get('outdoor'):
        for rid in ('room_a', 'room_b'):
            if d['layouts'][chosen[rid]]['kind'] != 'outdoor':
                fail('scale_layout', 'Room scale open is outdoors only; %s is an interior layout.' % chosen[rid])
    out = copy.deepcopy(spec)
    W, D = cfg['grid']
    pres_rooms = {}
    rows = []
    protagonist = out['metadata'].get('protagonist', '')
    for room in out['rooms']:
        rid = room['id']
        roles = set()
        people = [c for c in room['character_ids'] if c != protagonist]
        if people:
            roles.add('npc')
        if any(c['room'] == rid for c in out.get('collectibles', [])):
            roles.add('keepsake')
        if out['start']['location'] == rid:
            roles.add('start')
        room['grid_size'] = [W, D]
        doors = []
        for door in room['doors']:
            door['wall'] = 'north'
            door['position'] = int(round(W * float(cfg['door_frac']) - 0.5))
            x = door['position'] + 0.5
            doors.append({'id': door['id'], 'wall': 'north', 'x': x, 'z': MARGIN, 'approach': (x, MARGIN + 1.0)})
        layout = d['layouts'][chosen[rid]]
        plan = Plan(rid, chosen[rid], W, D, scale, cfg, pack, seed, doors, treatment_for(layout, pack))
        plan.build(roles)
        pres = plan.presentation(roles)
        cam = pres['cameras'][0]
        room['cameras'] = [{'id': 'fixed', 'position': cam['position'], 'look_at': cam['look_at']}]
        if 'npc' in plan.anchors:
            nx, nz = plan.anchors['npc']
            yaw = math.degrees(math.atan2(plan.centre[0] - nx, plan.centre[1] - nz))
            pres['characters'] = {people[0]: {'position': [round(nx, 2), 0.0, round(nz, 2)], 'yaw': round(yaw / 15.0) * 15.0}}
            fx, fz = plan.anchors['finish']
            for it in out['interactions']:
                if it['room'] == rid:
                    pres.setdefault('interactions', {})['interact:' + it['id']] = {'position': [round(fx, 2), 0.9, round(fz, 2)]}
        if 'keepsake' in plan.anchors:
            kx, kz = plan.anchors['keepsake']
            pres['collectibles'] = {c['id']: {'position': [round(kx, 2), plan.anchors['keepsake_y'], round(kz, 2)]}
                                    for c in out['collectibles'] if c['room'] == rid}
        rep = plan.report(roles)
        rep['why'] = chosen['why'][rid]
        rows.append(rep)
        pres_rooms[rid] = pres
    report['gate'] = gate(rows, cfg, scale, strict=check)
    meta = out['metadata']
    meta['presentation'] = {'convention': 'hermes64-presentation/1', 'rotation_units': 'degrees', 'rotation_order': 'YXZ',
                            'rooms': pres_rooms}
    meta['room_scale'] = {'scale': scale, 'layouts': {r['id']: r['layout'] for r in rows}, 'version': 1}
    report.update(applied=True, layouts={r['id']: r['layout'] for r in rows}, rooms=rows, pack=pack_id,
                  grid_m=[W, D], clear_target_m=cfg['clear_m'])
    return out, report


def gate(rows, cfg, scale, strict=True):
    """Static gates on the plan; a failure is a layout bug (never silently shipped). Returns the failures."""
    lo, hi = cfg['clear_m']
    budget = min(int(cfg['tri_budget']), 6000)
    bad = []
    for r in rows:
        if not r['all_reachable']:
            bad.append(('scale_unreachable', 'Room %s (%s): %s not reachable from the start.' % (
                r['id'], r['layout'], ', '.join(k for k, v in r['reachable'].items() if not v))))
        if r['tris_estimate'] + r['actor_reserve_tris'] > budget:
            bad.append(('scale_budget', 'Room %s (%s): %d estimated triangles + %d actor reserve exceed %d.' % (
                r['id'], r['layout'], r['tris_estimate'], r['actor_reserve_tris'], budget)))
        if not lo <= r['clear_square_m'] <= hi:
            bad.append(('scale_clear', 'Room %s (%s): clear square %.2f m outside the %s range %.1f-%.1f m.' % (
                r['id'], r['layout'], r['clear_square_m'], scale, lo, hi)))
        r['gate'] = 'passed' if not any(m.startswith('Room %s ' % r['id']) for _, m in bad) else 'failed'
    if bad and strict:
        fail(bad[0][0], ' '.join(m for _, m in bad))
    return [m for _, m in bad]


def lane_blockers(spec, bundle_root, pack_id):
    """Solid pieces whose footprint touches a door's walk-in lane (door point -> 1.0 m inside), per room. Used by the
    known-bad control (fill blocking a door) and the proof report."""
    pack = Pack(bundle_root, pack_id)
    out = {}
    for room in spec['rooms']:
        pres = spec['metadata'].get('presentation', {}).get('rooms', {}).get(room['id'], {})
        hits = []
        for row in pres.get('pieces', []):
            if row.get('kind', 'piece') not in SOLID_KINDS or pack.kit(row['asset']) in WALKTHROUGH or row.get('mounted'):
                continue
            if not pack.has(row['asset']):
                continue
            b, _ = pack.facts(row['asset'])
            sc = row.get('scale', [1, 1, 1])
            poly = footprint(b, row['position'][0], row['position'][2], float(row.get('yaw', 0)), sc[0], sc[2])
            for door in room['doors']:
                x = door['position'] + 0.5
                a, c = (x, MARGIN), (x, MARGIN + 1.6)
                if door['wall'] == 'north' and poly_seg_dist(poly, a, c) < RADIUS + 0.35:
                    hits.append(row['asset'])
        if hits:
            out[room['id']] = hits
    return out


def summary_line(report):
    """The one 'Rooms:' line of the /hermes64 new summary."""
    if not report.get('applied'):
        if report['scale'] == 'small':
            return 'Rooms: small, legacy 4 x 4 m (%s)' % report.get('reason', 'legacy starter')
        return 'Rooms: %s not applied (%s)' % (report['scale'], report.get('reason', ''))
    parts = ['%s %.1f m clear' % (r['layout'].replace('_', ' '), r['clear_square_m']) for r in report['rooms']]
    return 'Rooms: %s, %d x %d m (%s): %s' % (report['scale'], report['grid_m'][0], report['grid_m'][1],
                                             report.get('reason', ''), ', '.join(parts))


CARD_KEYS = ('layout', 'kind', 'clear_square_m', 'walkable_m2', 'crossing_m', 'crossing_walk_s', 'pieces', 'solid_pieces',
             'tris_estimate', 'coverage_pct', 'empty_patches_gt3m', 'largest_empty_radius_m', 'all_reachable')


def card(report):
    """Compact game-card block: scale, reason and per-room static measurements (runtime numbers live in the audit)."""
    out = {'scale': report['scale'], 'applied': bool(report.get('applied')), 'reason': report.get('reason', '')}
    if report.get('applied'):
        out.update(grid_m=report['grid_m'], clear_target_m=report['clear_target_m'],
                   rooms={r['id']: {k: r[k] for k in CARD_KEYS} for r in report['rooms']})
    if report.get('gaps'):
        out['gaps'] = report['gaps']
    return out


__all__ = ['SCALES', 'apply', 'pick', 'keyword', 'check_scale', 'choose_layouts', 'summary_line', 'card', 'Fault']
