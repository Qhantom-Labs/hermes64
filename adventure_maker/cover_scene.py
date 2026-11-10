"""Cover scene data (contracts/cover/1.0.0.json): validation, typed edits and story-driven proposals.

Stdlib only; no engine, network or file writes. The structural schema is evaluated with the bundled subset evaluator
(style_profile.validate_schema); context checks need a CoverContext (style palette + kit binding table, the
project's cast bindings, the N64 convention ranges). Every reference is an identifier resolved through a fixed table:
scenes never carry paths, URLs or code, and nothing here executes data.

Determinism: proposals, edits and auto-framing are pure functions of (story, style, cast table, seed).
"""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

from . import cover_style
from . import style_profile as sp
from .safety import Fault, fail

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'contracts/cover/1.0.0.json'
VERSION = '1.0.0'
KIND = 'hermes64.cover_scene'
FRAMING_ASPECT = {'poster': 245.0 / 170.0, 'banner': 2.0, 'square': 1.0}
SENSOR_MM = 24.0  # vertical film height for focal length -> vertical FOV (35 mm still convention)
TITLE_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,'!?&:-]*$")
RESTRICTED_CAST = ('cameo_visor_01',)


def fov_deg(focal_mm):
    return math.degrees(2.0 * math.atan(SENSOR_MM / (2.0 * float(focal_mm))))


def _schema():
    return sp.parse_json(sp.read_confined(ROOT, CONTRACT))


# ------------------------------------------------------------------ context
class CoverContext:
    """Everything a scene may reference: style (palette, kits, ground textures) and the project's cast table."""

    def __init__(self, style, cast=None, root=ROOT):
        self.style = style
        self.cast = dict(cast or {})
        self.root = Path(root)
        self.conv = cover_style.convention(root)
        self._kit_sizes = None

    def kit_size(self, ref):
        """[width, depth, height] metres of a kit ref from the KITS manifest (approximate when absent)."""
        if self._kit_sizes is None:
            self._kit_sizes = {}
            try:
                manifest = sp.parse_json(sp.read_confined(self.root, 'kits/manifest.json'))
                for kit in manifest.get('kits', []):
                    for b in kit.get('builds', []):
                        size = (b.get('meta') or {}).get('bbox_size_m')
                        if isinstance(size, list) and len(size) == 3:
                            self._kit_sizes['kits/' + b['glb']] = [float(x) for x in size]
            except sp.StyleError:
                pass
        row = self.style.bindings.get(ref) or {}
        size = self._kit_sizes.get(row.get('glb', ''))
        if size:
            return size
        if ref == 'terrain.vista':
            return [80.0, 80.0, 8.0]
        return [1.0, 1.0, 1.0]


def cast_table(spec, bindings, root=ROOT):
    """Story characters with an exact, public, non-placeholder model binding (actors/assets.gd selector rules)."""
    rows = bindings.get('characters', []) if isinstance(bindings, dict) else []
    out = {}
    for c in (spec.get('characters') or []) if isinstance(spec, dict) else []:
        if not isinstance(c, dict) or not isinstance(c.get('id'), str):
            continue
        for row in rows:
            if row.get('body_id') != c.get('body_id') or row.get('base_rig_id') != c.get('base_rig_id') or row.get('params') != c.get('params'):
                continue
            if row.get('placeholder', True) or row.get('internal_only') or row.get('public_release') is False:
                continue
            if row.get('character_id') in RESTRICTED_CAST or c['id'] in RESTRICTED_CAST:
                continue
            glb = row.get('glb', '')
            if not isinstance(glb, str) or not (Path(root) / glb).is_file():
                continue
            animal = row.get('base_rig_id') == 'cat_8' or 'coat' in (c.get('params') or {})
            out[c['id']] = {'id': c['id'], 'name': c.get('name', c['id']), 'body_id': c['body_id'],
                            'base_rig_id': c['base_rig_id'], 'params': c['params'], 'role': c.get('role', ''),
                            'character_id': row.get('character_id'), 'glb': glb, 'sha256': row.get('sha256'),
                            'clips': sorted(row.get('animations') or []), 'animal': bool(animal),
                            'height_m': 0.42 if animal else 1.76, 'width_m': 0.7 if animal else 0.55,
                            'source_rig': row.get('source_rig', '')}
            break
    return out


# ------------------------------------------------------------------ validation
def normalise(scene):
    """Lower-case colours (the only normalisation); returns a deep copy."""
    scene = copy.deepcopy(scene)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str) and len(v) == 7 and v.startswith('#') and re.fullmatch(r'#[0-9A-Fa-f]{6}', v):
            return v.lower()
        return v
    return walk(scene)


def structural(scene):
    """Contract check only (no context). Raises Fault('cover_scene', reason)."""
    try:
        sp.canonical_bytes(scene)
        sp.validate_schema(scene, _schema())
    except sp.StyleError as exc:
        fail('cover_scene', 'Scene violates contracts/cover/1.0.0.json: ' + str(exc))
    return scene


def validate(scene, ctx):
    """Full validation; returns the normalised scene or raises Fault with a readable reason."""
    if not isinstance(scene, dict):
        fail('cover_scene', 'Scene must be a JSON object')
    scene = normalise(scene)
    structural(scene)
    st = ctx.style
    why = []
    if scene['style']['kit_pack'] != st.kit_pack or scene['style']['id'] != st.id:
        why.append('style %s/%s does not match the project style %s/%s' % (scene['style']['id'], scene['style']['kit_pack'], st.id, st.kit_pack))
    if scene['style']['remap'] != bool(st.remap):
        why.append('style.remap must be %s for %s' % (str(bool(st.remap)).lower(), st.id))
    pal = set(st.palette)
    for path, value in _colours(scene):
        if value not in pal:
            why.append('%s colour %s is not in the %s palette (choose one of its %d colours)' % (path, value, st.id, len(st.palette)))
    kits = set(st.kits())
    for group in ('hero', 'props'):
        for i, row in enumerate(scene[group]):
            if row['kit'] not in kits:
                why.append('%s[%d] kit %r is not in the %s kit binding table' % (group, i, row['kit'], st.kit_pack))
            if group == 'props' and row['kit'] in ('terrain.vista', 'sky.backdrop'):
                why.append('%s[%d] kit %r is staged by ground/sky, not as a prop' % (group, i, row['kit']))
    seen = set()
    for i, actor in enumerate(scene['cast']):
        cid = actor['id']
        if cid in seen:
            why.append('cast[%d] duplicates %s' % (i, cid))
        seen.add(cid)
        row = ctx.cast.get(cid)
        if row is None:
            why.append('cast[%d] id %r has no bound model in this project (cast bindings: %s)' % (i, cid, ', '.join(sorted(ctx.cast)) or 'none'))
            continue
        if actor['clip'] not in row['clips']:
            why.append('cast[%d] clip %r not in %s clips %s' % (i, actor['clip'], cid, row['clips']))
    rng = cover_style.ranges(scene['mood'], ctx.root, ctx.conv)
    li = scene['light']
    for key, field in (('ambient', 'ambient_energy'), ('key', 'key_energy'), ('fill', 'fill_energy')):
        lo, hi = rng[key]
        if not lo <= li[field] <= hi:
            why.append('light.%s %.3f outside the N64 convention range [%.2f, %.2f] for %s' % (field, li[field], lo, hi, scene['mood']))
    fog = scene['fog']
    if fog['far_m'] <= fog['near_m'] + 2:
        why.append('fog.far_m must exceed fog.near_m by more than 2 m')
    lo, hi = rng['fog.near']
    if not lo * 0.5 <= fog['near_m'] <= hi * 2.5:
        why.append('fog.near_m %.1f outside [%.1f, %.1f] (convention range scaled for a staged set)' % (fog['near_m'], lo * 0.5, hi * 2.5))
    lo, hi = rng['fog.far']
    if not lo * 0.5 <= fog['far_m'] <= hi * 2.0:
        why.append('fog.far_m %.1f outside [%.1f, %.1f] (convention range scaled for a staged set)' % (fog['far_m'], lo * 0.5, hi * 2.0))
    halo_max = float(ctx.conv.get('lighting', {}).get('halo', {}).get('max_strength', 0.85))
    for i, lamp in enumerate(li['lamps']):
        if lamp['halo'] > halo_max:
            why.append('light.lamps[%d].halo %.2f exceeds the convention halo max %.2f' % (i, lamp['halo'], halo_max))
    cam = scene['camera']
    pos = camera_position(cam)
    if pos[1] < 0.25:
        why.append('camera below the ground plane (y %.2f m); raise elevation or target' % pos[1])
    r = scene['ground']['radius_m']
    if math.hypot(pos[0], pos[2]) > r + 30:
        why.append('camera %.1f m from the stage centre, beyond the staged ground (radius %.1f m)' % (math.hypot(pos[0], pos[2]), r))
    if math.hypot(cam['target'][0], cam['target'][2]) > r:
        why.append('camera target outside the staged ground')
    for group in ('hero', 'props', 'cast'):
        for i, row in enumerate(scene[group]):
            if math.hypot(row['at'][0], row['at'][2]) > r + 12:
                why.append('%s[%d] at %s is beyond the staged ground (radius %.1f m)' % (group, i, row['at'], r))
    for field in ('text', 'subtitle'):
        value = scene['title'][field]
        if value and not TITLE_CHARS.fullmatch(value):
            why.append('title.%s uses characters outside the cover font' % field)
    if why:
        fail('cover_scene', '; '.join(why[:12]))
    return scene


def _colours(scene):
    out = []
    for sec in ('sky', 'light', 'fog', 'particles', 'title'):
        for k, v in scene[sec].items():
            if isinstance(v, str) and v.startswith('#'):
                out.append((sec + '.' + k, v))
    for i, lamp in enumerate(scene['light']['lamps']):
        out.append(('light.lamps[%d].color' % i, lamp['color']))
    out.append(('style.band', scene['style']['band']))
    return out


def camera_position(cam):
    az, el = math.radians(cam['azimuth_deg']), math.radians(cam['elevation_deg'])
    t = cam['target']
    d = cam['distance_m']
    return [t[0] + math.sin(az) * math.cos(el) * d, t[1] + math.sin(el) * d, t[2] + math.cos(az) * math.cos(el) * d]


def canonical(scene):
    return json.dumps(scene, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def scene_hash(scene):
    return hashlib.sha256(canonical(scene)).hexdigest()


# ------------------------------------------------------------------ projection / auto-framing
def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def project(point, cam, aspect):
    """Screen position (x 0..1 left->right, y 0..1 top->bottom, depth) of a world point; depth <= 0 behind."""
    p = camera_position(cam)
    f = _norm(_sub(cam['target'], p))
    r = _norm(_cross(f, [0.0, 1.0, 0.0]))
    u = _cross(r, f)
    v = _sub(point, p)
    z = _dot(v, f)
    if z <= 0.05:
        return (0.5, 0.5, -1.0)
    ty = math.tan(math.radians(fov_deg(cam['focal_mm'])) / 2.0)
    x = _dot(v, r) / (z * ty * aspect)
    y = _dot(v, u) / (z * ty)
    return ((x + 1.0) / 2.0, (1.0 - y) / 2.0, z)


def boxes(scene, ctx, groups=('hero', 'cast')):
    out = []
    for group in groups:
        for row in scene[group]:
            if group == 'cast':
                c = ctx.cast.get(row['id'], {'height_m': 1.7, 'width_m': 0.5})
                w, h, d = c['width_m'] * row['scale'], c['height_m'] * row['scale'], c['width_m'] * row['scale']
            else:
                s = ctx.kit_size(row['kit'])
                w, d, h = s[0] * row['scale'], s[1] * row['scale'], s[2] * row['scale']
            x, y, z = row['at']
            out.append((group, [x - w / 2, y, z - d / 2], [x + w / 2, y + h, z + d / 2]))
    return out


def screen_box(bxs, cam, aspect):
    xs, ys, behind = [], [], False
    for _g, lo, hi in bxs:
        for cx in (lo[0], hi[0]):
            for cy in (lo[1], hi[1]):
                for cz in (lo[2], hi[2]):
                    sx, sy, z = project([cx, cy, cz], cam, aspect)
                    if z <= 0:
                        behind = True
                        continue
                    xs.append(sx)
                    ys.append(sy)
    if not xs:
        return None
    return {'left': min(xs), 'right': max(xs), 'top': min(ys), 'bottom': max(ys), 'behind': behind}


def frame(scene, ctx, goal_top, goal_bottom, groups=('hero', 'cast'), x_centre=None):
    """Choose camera distance and target height so the subject boxes span [goal_top, goal_bottom] of the frame."""
    scene = copy.deepcopy(scene)
    cam = scene['camera']
    bxs = boxes(scene, ctx, groups)
    if not bxs:
        return scene
    lo = [min(b[1][i] for b in bxs) for i in range(3)]
    hi = [max(b[2][i] for b in bxs) for i in range(3)]
    cx, cz = (lo[0] + hi[0]) / 2.0, (lo[2] + hi[2]) / 2.0
    if x_centre is not None:
        cx = x_centre
    aspect = FRAMING_ASPECT[cam['framing']]
    best = None
    for di in range(56):
        d = 2.2 * (44.0 / 2.2) ** (di / 55.0)
        for ti in range(33):
            ty = lo[1] + (hi[1] - lo[1]) * (ti / 32.0) * 1.2 - 0.2
            trial = dict(cam, distance_m=round(d, 3), target=[round(cx, 3), round(ty, 3), round(cz, 3)])
            if camera_position(trial)[1] < 0.3:
                continue
            sb = screen_box(bxs, trial, aspect)
            if sb is None or sb['behind']:
                continue
            err = (sb['top'] - goal_top) ** 2 + (sb['bottom'] - goal_bottom) ** 2
            err += 2.0 * max(0.0, 0.06 - sb['left']) ** 2 + 2.0 * max(0.0, sb['right'] - 0.94) ** 2
            if best is None or err < best[0] - 1e-12:
                best = (err, trial)
    if best is not None:
        scene['camera'] = best[1]
    return scene


# ------------------------------------------------------------------ proposals from story + style
KEYWORDS = [
    (r'dome|pod|habitat|shelter|station|base|observatory', ['kit/glowing_dome', 'arch.house']),
    (r'lighthouse|beacon|tower|spire|signal|relay', ['arch.tower']),
    (r'cottage|house|village|town|market|bazaar|inn|home|post', ['arch.house__round_cottage', 'arch.house']),
    (r'bridge|crossing', ['arch.bridge']),
    (r'boat|ferry|harbou?r|coast|sea|tide|pier|dock|marsh|lake', ['vehicle.boat', 'kit/boat']),
    (r'orchard|forest|grove|tree|garden|seed|botan', ['nature.tree', 'nature.tree__birch']),
    (r'crystal|glass|frost|ice|star', ['look/crystal_tree', 'arch.window__panorama']),
]
MOOD_WORDS = [('night', r'night|star|moon|dark|lantern|aurora|midnight'), ('dusk', r'dusk|evening|sunset|twilight|ember|last light'),
              ('dawn', r'dawn|morning|sunrise|wake|frost'), ('day', r'day|noon|bright|summer|relay|race')]
PARTICLE_WORDS = [('snow', r'snow|polar|ice|frost|winter|blizzard|cold'), ('fireflies', r'firefl|lantern|moth|marsh|swamp|glow'),
                  ('dust', r'desert|dune|salt|sand|canyon|wind|dust'), ('petals', r'orchard|blossom|garden|petal|spring'),
                  ('embers', r'ember|forge|fire|volcan|cinder')]
GROUND_WORDS = [('snowfield', r'snow|polar|ice|frost|winter'), ('dunes', r'desert|dune|salt|sand|canyon'),
                ('meadow', r'marsh|meadow|field|reed|orchard|garden|forest|village'), ('cobbles', r'street|market|town|harbou?r'),
                ('stone', r'mine|spire|tower|glass')]


def _text(spec):
    """Story words a cover reads: title, description, room names, room descriptions (bounded) and kit refs."""
    parts = [str(spec.get('title', '')), str(spec.get('description', ''))[:600]]
    for r in (spec.get('rooms') or [])[:24]:
        parts.append(str(r.get('name', '')))
        parts.append(str(r.get('description', ''))[:400])
        parts.extend(str(k) for k in r.get('kit_refs') or [])
    return ' '.join(parts).lower()


def _pick(words, text, default):
    """The option whose pattern matches most often (ties: list order); default when nothing matches."""
    best, hits = default, 0
    for value, pattern in words:
        n = len(re.findall(pattern, text))
        if n > hits:
            best, hits = value, n
    return best


def _hash01(seed, *keys):
    h = hashlib.sha256(('%d:' % seed + ':'.join(str(k) for k in keys)).encode()).digest()
    return int.from_bytes(h[:6], 'big') / float(1 << 48)


def _title_text(spec):
    raw = str(spec.get('title') or spec.get('id') or 'Untitled')
    keep = ''.join(ch for ch in raw if ch.isalnum() or ch in " .,'!?&:-").strip()
    keep = re.sub(r'\s+', ' ', keep)
    return (keep or 'Untitled')[:28]


def hero_kits(spec, style):
    text = _text(spec)
    kits = set(style.kits())
    chosen = []
    for pattern, refs in KEYWORDS:
        if re.search(pattern, text):
            for ref in refs:
                if ref in kits and ref not in chosen:
                    chosen.append(ref)
                    break
    lm = (style.view.get('look', {}).get('exterior', {}).get('landmark') or {}).get('asset')
    if lm in kits and lm not in chosen:
        chosen.append(lm)
    for ref in ('arch.tower', 'arch.house'):
        if ref in kits and ref not in chosen:
            chosen.append(ref)
    return chosen


def protagonist(spec, cast):
    pid = (spec.get('metadata') or {}).get('protagonist')
    if pid in cast and not cast[pid]['animal']:
        return pid
    humans = [c for c in cast.values() if not c['animal']]
    return humans[0]['id'] if humans else None


def companions(spec, cast, lead):
    others = [c for c in (spec.get('characters') or []) if c.get('id') in cast and c.get('id') != lead]
    humans = [c['id'] for c in others if not cast[c['id']]['animal']]
    animals = [c['id'] for c in others if cast[c['id']]['animal']]
    return humans, animals


def base_scene(spec, ctx, seed, ident, mood, ground=None):
    st = ctx.style
    text = _text(spec)
    if ground is None:
        ground = _pick(GROUND_WORDS, text, 'snowfield' if st.kit_pack == 'polar_pod' else 'meadow')
        if st.id == 'warm_desert_example':
            ground = 'dunes'
    preset = st.mood_preset(mood, ground)
    col, en = preset['colours'], preset['energy']
    particles = _pick(PARTICLE_WORDS, text, 'none')
    if particles == 'fireflies' and mood not in ('night', 'dusk'):
        particles = 'petals' if 'petal' in text else 'none'
    pcol = {'snow': col['snow'], 'fireflies': col['firefly'], 'dust': st.colour(mood, 'cloud'), 'petals': st.colour(mood, 'aurora'),
            'embers': col['lamp'], 'none': col['snow']}[particles]
    rng = cover_style.ranges(mood, ctx.root, ctx.conv)

    def clampe(v, key):
        lo, hi = rng[key]
        return round(min(hi, max(lo, v)), 3)
    key_az = -35.0 + 70.0 * _hash01(seed, 'key')
    return {
        'schema_version': VERSION, 'kind': KIND, 'id': ident, 'revision': 1, 'parent': None, 'seed': int(seed),
        'game': {'id': _slug(spec.get('id', 'game')), 'title': _title_text(spec)},
        'style': {'id': st.id, 'source': st.source, 'kit_pack': st.kit_pack, 'label': st.label, 'band': st.band,
                  'remap': bool(st.remap)},
        'mood': mood,
        'sky': {'zenith': col['zenith'], 'horizon': col['horizon'], 'glow': col['glow'],
                'glow_strength': 0.55 if mood in ('dusk', 'dawn') else (0.35 if mood == 'night' else 0.25),
                'glow_azimuth_deg': round(-150.0 + 60.0 * _hash01(seed, 'glow'), 1), 'glow_elevation_deg': 6.0 if mood in ('dusk', 'dawn') else 22.0,
                'exposure': (0.88 if ground in ('snowfield', 'ice') else 0.8) if mood == 'night' else 1.0,
                'stars': 160 if mood == 'night' else 0, 'aurora': col['aurora'],
                'aurora_strength': 0.35 if (mood == 'night' and st.kit_pack == 'polar_pod') else 0.0,
                'clouds': 0.35 if mood in ('day', 'dawn', 'dusk') else 0.15, 'cloud_color': col['cloud']},
        'light': {'key': col['key'], 'key_energy': clampe(en['key'], 'key'), 'key_azimuth_deg': round(key_az, 1),
                  'key_elevation_deg': 22.0 if mood in ('dusk', 'dawn') else 48.0,
                  'ambient': col['ambient'], 'ambient_energy': clampe(en['ambient'], 'ambient'),
                  'fill': col['fill'], 'fill_energy': clampe(en['fill'], 'fill'),
                  'sky_bounce': en['sky'], 'ground_bounce': en['ground'], 'kicker': col['kicker'],
                  'kicker_energy': en['kicker'], 'lamps': []},
        'fog': ({'color': col['horizon'], 'near_m': 9.0, 'far_m': 46.0, 'density': 0.92} if re.search(r'\bfog|mist|haze', text)
                else {'color': col['horizon'], 'near_m': 14.0, 'far_m': 70.0, 'density': 0.85}),
        'ground': {'preset': ground, 'radius_m': 26.0, 'vista': True, 'vista_scale': 1.0},
        'hero': [], 'props': [], 'cast': [],
        'particles': {'kind': particles, 'count': 220 if particles == 'snow' else (140 if particles == 'fireflies' else 120),
                      'color': pcol, 'size_m': {'snow': 0.07, 'fireflies': 0.1}.get(particles, 0.05), 'area': [30.0, 12.0, 30.0]},
        'camera': {'framing': 'poster', 'focal_mm': 30.0, 'target': [0.0, 1.4, 0.0], 'distance_m': 10.0,
                   'azimuth_deg': 0.0, 'elevation_deg': 8.0, 'roll_deg': 0.0},
        'title': {'text': _title_text(spec), 'subtitle': '', 'placement': 'top', 'letter': 'block', 'size': 'xl',
                  'fill': col['title'], 'fill2': col['fill2'], 'outline': col['outline'], 'shadow': col['shadow']},
        'finish': {'vignette': 0.16, 'contrast': 1.06, 'saturation': 1.08, 'lift': 0.02, 'band_edge': 'bottom', 'mark': True},
    }


def _slug(value):
    s = re.sub(r'[^a-z0-9_-]+', '-', str(value).lower()).strip('-_') or 'game'
    if not s[0].isalpha():
        s = 'g' + s
    return s[:48]


def _scatter(scene, ctx, seed, refs, count, radius, avoid, tag):
    kits = [r for r in refs if r in set(ctx.style.kits())]
    if not kits:
        return
    placed = 0
    tries = 0
    while placed < count and tries < count * 12:
        tries += 1
        a = _hash01(seed, tag, 'a', tries) * 2 * math.pi
        rr = radius[0] + (radius[1] - radius[0]) * math.sqrt(_hash01(seed, tag, 'r', tries))
        x, z = math.cos(a) * rr, math.sin(a) * rr
        if any(math.hypot(x - ax, z - az) < ar for ax, az, ar in avoid):
            continue
        ref = kits[int(_hash01(seed, tag, 'k', tries) * len(kits)) % len(kits)]
        sc = 0.7 + 0.6 * _hash01(seed, tag, 's', tries)
        scene['props'].append({'kit': ref, 'at': [round(x, 2), 0.0, round(z, 2)], 'yaw': round(_hash01(seed, tag, 'y', tries) * 360.0 - 180.0, 1),
                               'scale': round(sc, 2)})
        avoid.append((x, z, 1.2 * sc + 0.4))
        placed += 1


def _clip(row, wanted):
    for c in wanted:
        if c in row['clips']:
            return c
    return row['clips'][0] if row['clips'] else 'idle'


def _yaw_to_camera(at, cam, offset):
    """Actor yaw (degrees) that faces the camera position, turned by `offset` degrees (3/4 views)."""
    p = camera_position(cam)
    return round(math.degrees(math.atan2(p[0] - at[0], p[2] - at[2])) + offset, 1)


def _kit_top(scene, ctx, group, i):
    """Screen box of one placement (hero/props/cast) under the scene camera."""
    return screen_box(boxes({group: [scene[group][i]]}, ctx, groups=(group,)), scene['camera'],
                      FRAMING_ASPECT[scene['camera']['framing']])


def _solve_scale(scene, ctx, i, top_y, lo=0.35, hi=3.0):
    """Scale hero[i] so its projected top sits at screen y = top_y (0 top .. 1 bottom); bounded to [lo, hi]."""
    row = scene['hero'][i]
    a, b = lo, hi
    for _ in range(28):
        mid = (a + b) / 2.0
        row['scale'] = mid
        sb = _kit_top(scene, ctx, 'hero', i)
        if sb is None:
            break
        if sb['top'] > top_y:
            a = mid
        else:
            b = mid
    row['scale'] = round(min(hi, max(lo, (a + b) / 2.0)), 3)


def _solve_x(scene, ctx, group, i, centre_x, span=40.0):
    """Slide a placement along world x so its screen centre sits at centre_x (0 left .. 1 right)."""
    row = scene[group][i]
    a, b = row['at'][0] - span, row['at'][0] + span
    for _ in range(30):
        mid = (a + b) / 2.0
        row['at'][0] = mid
        sb = _kit_top(scene, ctx, group, i)
        if sb is None:
            break
        if (sb['left'] + sb['right']) / 2.0 < centre_x:
            a = mid
        else:
            b = mid
    row['at'][0] = round((a + b) / 2.0, 3)


def _framers(scene, ctx, seed, refs, slots, tag):
    """Framing pieces placed in screen terms (classic box-art depth layering): each slot is (ndc_x -1 left .. 1 right,
    metres from the camera, scale). Pieces sit at the frame sides, never between the camera and the subject."""
    kits = [r for r in refs if r in set(ctx.style.kits())]
    if not kits:
        return
    cam = scene['camera']
    p = camera_position(cam)
    fx, fz = cam['target'][0] - p[0], cam['target'][2] - p[2]
    n = math.hypot(fx, fz) or 1.0
    fx, fz = fx / n, fz / n
    rx, rz = -fz, fx
    tan_h = math.tan(math.radians(fov_deg(cam['focal_mm'])) / 2.0) * FRAMING_ASPECT[cam['framing']]
    for k, (ndc_x, dist, scale) in enumerate(slots):
        ref = kits[int(_hash01(seed, tag, k) * len(kits)) % len(kits)]
        lateral = ndc_x * dist * tan_h
        x, z = p[0] + fx * dist + rx * lateral, p[2] + fz * dist + rz * lateral
        jitter = 0.85 + 0.3 * _hash01(seed, tag, 's', k)
        scene['props'].append({'kit': ref, 'at': [round(x, 2), 0.0, round(z, 2)],
                               'yaw': round(_hash01(seed, tag, 'y', k) * 360.0 - 180.0, 1), 'scale': round(scale * jitter, 2)})


def _ground_toward(cam, sx, dist, aspect):
    """Ground point at horizontal distance `dist` from the camera, on the horizontal ray through screen column sx."""
    p = camera_position(cam)
    f = _norm(_sub(cam['target'], p))
    fh = math.hypot(f[0], f[2]) or 1.0
    fx, fz = f[0] / fh, f[2] / fh
    rx, rz = -fz, fx
    tan_h = math.tan(math.radians(fov_deg(cam['focal_mm'])) / 2.0) * aspect
    th = math.atan((2.0 * sx - 1.0) * tan_h)
    dx, dz = fx * math.cos(th) + rx * math.sin(th), fz * math.cos(th) + rz * math.sin(th)
    return [p[0] + dx * dist, 0.0, p[2] + dz * dist]


def _landmark_shot(sc, ctx, side, heroes, party, kits, top_y=0.27, s_p=0.24, feet_y=0.95, h_c=1.8):
    """Classic landmark box-art construction, solved rather than nudged. The camera stands at eye level (h_c) and looks
    slightly up; the party stands at the distance that makes it s_p of the frame tall, feet near the bottom edge
    (feet_y) on one third; the landmark stands a depth gap behind on the other third, scaled so its top meets the title
    band (top_y). Pitch, then scale, are bisected; the gap grows when the landmark would not fit the frame width and
    shrinks when it cannot reach the title band at a plausible scale."""
    cam = sc['camera']
    asp = FRAMING_ASPECT[cam['framing']]
    tan_v = math.tan(math.radians(fov_deg(cam['focal_mm'])) / 2.0)
    tan_h = tan_v * asp
    _w, depth, _h = ctx.kit_size(heroes[0])
    hp = max([ctx.cast[c]['height_m'] for c in party] or [1.7])
    d_p = hp / (s_p * 2.0 * tan_v)
    gap = max(6.0, 1.2 * depth)
    az = math.radians(cam['azimuth_deg'])
    rx, rz = math.cos(az), -math.sin(az)
    lo_s, hi_s = 0.45, 3.2
    for attempt in range(7):
        d_l = d_p + gap if party else 20.0
        lat = -0.34 * side * d_l * tan_h          # aim offset that puts the landmark centre on its third

        def aim(y_t):
            cam['target'] = [round(rx * lat, 3), round(y_t, 3), round(rz * lat, 3)]
            cam['elevation_deg'] = round(math.degrees(math.atan2(h_c - y_t, d_l)), 3)
            cam['distance_m'] = round(math.hypot(d_l, h_c - y_t), 3)

        sc['hero'] = [{'kit': heroes[0], 'at': [0.0, 0.0, 0.0], 'yaw': 0.0, 'scale': 1.0}]
        aim(h_c)
        sc['cast'] = []
        for k, cid in enumerate(party):
            at = _ground_toward(cam, 0.5 - (0.2 - 0.07 * k) * side, d_p + 0.6 * k, asp)
            sc['cast'].append({'id': cid, 'clip': _clip(ctx.cast[cid], ['walk', 'idle']), 'frame': 4 + 3 * k,
                               'at': [round(at[0], 3), 0.0, round(at[2], 3)], 'yaw': 0.0, 'scale': 1.0})
        # pitch: looking further up moves everything down the frame; bisect on the party feet (or the landmark base)
        a, b = -30.0, h_c + d_l * math.tan(math.radians(11.5))   # contract: elevation >= -12 degrees
        for _ in range(32):
            y_t = (a + b) / 2.0
            aim(y_t)
            if party:
                sb = screen_box(boxes(sc, ctx, ('cast',)), cam, asp)
                low = sb['bottom'] if sb else 2.0
            else:
                sb = _kit_top(sc, ctx, 'hero', 0)
                low = sb['bottom'] if sb else 2.0
            if low > (feet_y if party else 0.86):
                b = y_t
            else:
                a = y_t
        aim((a + b) / 2.0)
        _solve_scale(sc, ctx, 0, top_y, lo=lo_s, hi=hi_s)
        hb = _kit_top(sc, ctx, 'hero', 0)
        if hb is None:
            break
        too_small = sc['hero'][0]['scale'] >= hi_s - 0.01 and hb['top'] > top_y + 0.03
        too_wide = hb['left'] < 0.04 or hb['right'] > 0.96
        if not party or not (too_small or too_wide):
            break
        gap = gap * 1.45 if too_wide else max(3.0, gap * 0.7)
    sc['hero'][0]['yaw'] = _yaw_to_camera(sc['hero'][0]['at'], cam, -20.0 * side)
    for row in sc['cast']:
        row['yaw'] = _yaw_to_camera(row['at'], cam, 35.0 * side)
    second = next((h for h in heroes[1:] if h != heroes[0]), None) or next(
        (r for r in ('arch.house', 'arch.house__round_cottage', 'kit/glowing_dome') if r in kits and r != heroes[0]), None)
    if second:
        at = _ground_toward(cam, 0.5 - 0.3 * side, (d_p + gap if party else 20.0) + 9.0, asp)
        sc['hero'].append({'kit': second, 'at': [round(at[0], 3), 0.0, round(at[2], 3)], 'yaw': 0.0, 'scale': 1.0})
        sc['hero'][1]['yaw'] = _yaw_to_camera(sc['hero'][1]['at'], cam, 25.0 * side)
        _solve_scale(sc, ctx, 1, 0.5, lo=0.4, hi=1.4)
    return sc


def _glow_in_view(sc, side):
    """Put the moon (night) or the low sun (dusk/dawn) in the frame on the side opposite the landmark: a real light
    source is what makes a night or sunset cover read at card size. Solved from the camera field of view."""
    cam = sc['camera']
    tan_v = math.tan(math.radians(fov_deg(cam['focal_mm'])) / 2.0)
    tan_h = tan_v * FRAMING_ASPECT[cam['framing']]
    fwd = cam['azimuth_deg'] + 180.0                      # glow azimuth that points along the view
    delta = math.degrees(math.atan(0.55 * tan_h)) * side  # positive turns toward screen left
    az = ((fwd + delta + 180.0) % 360.0) - 180.0
    if sc['mood'] == 'night':
        el = max(12.0, -cam['elevation_deg'] + math.degrees(math.atan(0.3 * tan_v)))
        strength = 0.55
    elif sc['mood'] in ('dusk', 'dawn'):
        el, strength = 7.0, 0.7
    else:
        return
    sc['sky']['glow_azimuth_deg'] = round(az, 1)
    sc['sky']['glow_elevation_deg'] = round(min(60.0, el), 1)
    sc['sky']['glow_strength'] = strength


def _door_light(scene, ctx, i, mood):
    """A warm light at the landmark's front (kits face +Z before yaw): its lit doorway pools on the ground."""
    if mood not in ('night', 'dusk', 'interior') or len(scene['light']['lamps']) >= 4:
        return
    row = scene['hero'][i]
    w, d, h = ctx.kit_size(row['kit'])
    s = row['scale']
    yaw = math.radians(row['yaw'])
    off = d * s / 2.0 + 0.7
    x, z = row['at'][0] + math.sin(yaw) * off, row['at'][2] + math.cos(yaw) * off
    scene['light']['lamps'].append({'at': [round(x, 2), round(min(1.4, 0.35 * h * s), 2), round(z, 2)],
                                    'color': ctx.style.colour(mood, 'lamp'), 'energy': 1.0,
                                    'radius_m': round(min(12.0, max(3.5, 4.0 * s)), 2), 'halo': 0.0})


def propose(spec, ctx, seed=7, prefix=None):
    """Three composition variants from the story + style; a human picks one (never adopted automatically).

    a  hero + landmark: low camera, the protagonist (and companion animal) large in the lower frame on a third, the
       landmark behind on the opposite third rising toward the title band; side framing pieces for depth.
    b  landmark shot: a low camera looking slightly up, the landmark dominant on one third rising to the title band,
       the party small but readable well in front of it on the other third (solved from real heights).
    c  two-shot portrait: longer lens, two cast members large, the second landmark softly behind; title at the bottom.
    """
    st = ctx.style
    text = _text(spec)
    mood = _pick(MOOD_WORDS, text, 'day')
    heroes = hero_kits(spec, st) or ['arch.house']
    lead = protagonist(spec, ctx.cast)
    humans, animals = companions(spec, ctx.cast, lead)
    prefix = _slug(prefix or spec.get('id', 'cover'))[:40]
    kits = set(st.kits())
    flora = [r for r in ('look/frosted_tree', 'nature.tree__crystal', 'nature.tree', 'nature.tree__birch', 'nature.bush')
             if r in kits] or [r for r in ('nature.rock',) if r in kits]
    rocks = [r for r in ('nature.rock', 'kit/snow_rocks', 'nature.bush') if r in kits]
    out = []
    for vi, (tag, arche) in enumerate((('a', 'hero'), ('b', 'vista'), ('c', 'portrait'))):
        s = seed + 101 * vi
        sc = base_scene(spec, ctx, s, '%s-%s' % (prefix, tag), mood)
        cam = sc['camera']
        side = -1.0 if _hash01(s, 'side') < 0.5 else 1.0  # which third the landmark takes
        sc['title']['letter'] = 'wedge' if arche in ('hero', 'vista') else 'block'
        if arche == 'hero':
            cam.update(focal_mm=28.0, azimuth_deg=round(-14.0 * side, 1), elevation_deg=3.0)
            if lead:
                sc['cast'].append({'id': lead, 'clip': _clip(ctx.cast[lead], ['walk', 'idle']), 'frame': 4,
                                   'at': [0.0, 0.0, 0.0], 'yaw': 0.0, 'scale': 1.0})
            if animals:
                sc['cast'].append({'id': animals[0], 'clip': _clip(ctx.cast[animals[0]], ['walk', 'idle']), 'frame': 2,
                                   'at': [round(0.95 * side, 2), 0.0, 0.55], 'yaw': 0.0, 'scale': 1.0})
            elif humans:
                sc['cast'].append({'id': humans[0], 'clip': _clip(ctx.cast[humans[0]], ['idle', 'walk']), 'frame': 0,
                                   'at': [round(1.1 * side, 2), 0.0, -0.9], 'yaw': 0.0, 'scale': 1.0})
            sc['hero'].append({'kit': heroes[0], 'at': [round(5.0 * side, 2), 0.0, -17.0], 'yaw': 0.0, 'scale': 1.0})
            if len(heroes) > 1:
                sc['hero'].append({'kit': heroes[1], 'at': [round(-9.0 * side, 2), 0.0, -26.0], 'yaw': 0.0, 'scale': 1.0})
            sc = frame(sc, ctx, 0.36, 0.96, groups=('cast',), x_centre=0.0) if sc['cast'] else frame(sc, ctx, 0.2, 0.9)
            cam = sc['camera']
            _solve_x(sc, ctx, 'hero', 0, 0.5 + 0.26 * side)
            sc['hero'][0]['yaw'] = _yaw_to_camera(sc['hero'][0]['at'], cam, 22.0 * side)
            _solve_scale(sc, ctx, 0, 0.16)
            for _ in range(20):   # keep the landmark wholly inside the frame
                hb = _kit_top(sc, ctx, 'hero', 0)
                if hb is None or (hb['left'] >= 0.03 and hb['right'] <= 0.97):
                    break
                sc['hero'][0]['scale'] = round(max(0.3, sc['hero'][0]['scale'] * 0.9), 3)
                _solve_x(sc, ctx, 'hero', 0, 0.5 + 0.26 * side)
            _door_light(sc, ctx, 0, mood)
            if len(sc['hero']) > 1:
                _solve_x(sc, ctx, 'hero', 1, 0.5 - 0.3 * side)
                _solve_scale(sc, ctx, 1, 0.42, lo=0.3, hi=1.6)
            for row in sc['cast']:
                row['yaw'] = _yaw_to_camera(row['at'], cam, -24.0 * side)
            _framers(sc, ctx, s, flora, [(-1.02, 9.0, 0.8), (1.0, 11.0, 0.75), (-0.75 * side, 30.0, 1.0)], 'fr')
            _framers(sc, ctx, s, rocks, [(0.62, 6.5, 0.55), (-0.7, 7.5, 0.6)], 'rk')
        elif arche == 'vista':
            # landmark shot: low heroic camera, the landmark dominant on one third, the party small on the other
            cam.update(focal_mm=30.0, azimuth_deg=round(16.0 * side, 1))
            party = ([lead] if lead else []) + (animals[:1] if animals else humans[:1])
            sc = _landmark_shot(sc, ctx, side, heroes, [c for c in party if c], kits)
            cam = sc['camera']
            sc['ground']['radius_m'] = 40.0
            _door_light(sc, ctx, 0, mood)
            _framers(sc, ctx, s, flora, [(-1.0, 15.0, 0.9), (1.0, 17.0, 0.85), (-0.6 * side, 30.0, 1.0), (0.85 * side, 34.0, 1.1)], 'fr')
            _framers(sc, ctx, s, rocks, [(0.55 * side, 6.0, 0.5), (-0.5 * side, 6.5, 0.55)], 'rk')
        else:
            cam.update(focal_mm=45.0, azimuth_deg=round(-6.0 * side, 1), elevation_deg=2.0)
            if lead:
                sc['cast'].append({'id': lead, 'clip': _clip(ctx.cast[lead], ['idle', 'talk']), 'frame': 0,
                                   'at': [round(-0.5 * side, 2), 0.0, 0.0], 'yaw': 0.0, 'scale': 1.0})
            partner = humans[0] if humans else (animals[0] if animals else None)
            if partner:
                prow = ctx.cast[partner]
                sc['cast'].append({'id': partner, 'clip': _clip(prow, ['talk', 'idle'] if not prow['animal'] else ['sit', 'idle']),
                                   'frame': 4, 'at': [round(0.62 * side, 2), 0.0, 0.3 if not prow['animal'] else 0.75],
                                   'yaw': 0.0, 'scale': 1.0})
            hero = heroes[1] if len(heroes) > 1 else heroes[0]
            sc['hero'].append({'kit': hero, 'at': [round(2.5 * side, 2), 0.0, -14.0], 'yaw': 0.0, 'scale': 1.0})
            sc['title']['placement'] = 'bottom'
            # a two-line logotype at the bottom needs more room under the cast
            from .cover_finish import title_layout
            two = len(title_layout(sc['title']['text'].upper(), sc['title']['letter'], sc['title']['size'], 227, 42, 2)[0]) > 1
            bottom = 0.6 if two else 0.74
            sc = frame(sc, ctx, 0.1, bottom, groups=('cast',)) if sc['cast'] else frame(sc, ctx, 0.1, bottom)
            cam = sc['camera']
            _solve_x(sc, ctx, 'hero', 0, 0.5 + 0.3 * side)
            sc['hero'][0]['yaw'] = _yaw_to_camera(sc['hero'][0]['at'], cam, 15.0 * side)
            _solve_scale(sc, ctx, 0, 0.1)
            for _ in range(20):   # keep the landmark wholly inside the frame (no accidental edge crops)
                hb = _kit_top(sc, ctx, 'hero', 0)
                if hb is None or (hb['left'] >= 0.03 and hb['right'] <= 0.97):
                    break
                sc['hero'][0]['scale'] = round(max(0.3, sc['hero'][0]['scale'] * 0.9), 3)
                _solve_x(sc, ctx, 'hero', 0, 0.5 + 0.3 * side)
            if len(sc['cast']) == 2:
                a0, a1 = sc['cast'][0]['at'], sc['cast'][1]['at']
                sc['cast'][0]['yaw'] = _yaw_to_camera(a0, cam, 28.0 * side)
                sc['cast'][1]['yaw'] = _yaw_to_camera(a1, cam, -32.0 * side)
            elif sc['cast']:
                sc['cast'][0]['yaw'] = _yaw_to_camera(sc['cast'][0]['at'], cam, 15.0)
            lamp_ref = next((r for r in ('furn.lamp', 'prop/central_lamp') if r in kits), None)
            if lamp_ref and mood in ('night', 'dusk', 'interior'):
                lx = round(-1.9 * side, 2)
                sc['props'].append({'kit': lamp_ref, 'at': [lx, 0.0, -1.2], 'yaw': 0.0, 'scale': 1.0})
                sc['light']['lamps'].append({'at': [lx, 1.5, -1.2], 'color': st.colour(mood, 'lamp'), 'energy': 0.7,
                                             'radius_m': 5.0, 'halo': 0.45})
            _framers(sc, ctx, s, flora, [(-0.95, 16.0, 0.9), (0.95, 19.0, 1.0)], 'fr')
        _glow_in_view(sc, side)
        for group in ('hero', 'props', 'cast'):
            for row in sc[group]:
                row['at'] = [round(v, 3) for v in row['at']]
                row['yaw'] = round(((row['yaw'] + 180.0) % 360.0) - 180.0, 1)
        out.append(validate(sc, ctx))
    return out


# ------------------------------------------------------------------ typed edits
EDIT_OPS = ('move', 'nudge', 'replace', 'add', 'remove', 'lighting', 'camera', 'title', 'particles', 'pose', 'finish', 'reframe')


def _target(scene, target):
    m = re.fullmatch(r'(hero|prop|cast):([a-z0-9_-]{1,48})', str(target or ''))
    if not m:
        fail('cover_edit', 'target must be hero:<index>, prop:<index> or cast:<id>')
    group, key = m.group(1), m.group(2)
    rows = scene['props' if group == 'prop' else group]
    if group == 'cast':
        for i, row in enumerate(rows):
            if row['id'] == key:
                return rows, i
        fail('cover_edit', 'No cast member %s in this scene' % key)
    if not key.isdigit() or int(key) >= len(rows):
        fail('cover_edit', 'No %s at index %s (scene has %d)' % (group, key, len(rows)))
    return rows, int(key)


def _num(op, key, lo, hi):
    v = op[key]
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        fail('cover_edit', '%s must be a number in [%s, %s]' % (key, lo, hi))
    return float(v)


def _vec(op, key, lim=60.0):
    v = op[key]
    if not isinstance(v, list) or len(v) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > lim for x in v):
        fail('cover_edit', '%s must be [x, y, z] metres within +-%g' % (key, lim))
    return [round(float(x), 3) for x in v]


def _only(op, allowed):
    extra = sorted(set(op) - set(allowed) - {'op'})
    if extra:
        fail('cover_edit', 'Unknown field(s) for %s: %s' % (op['op'], ', '.join(extra)))


def apply_edit(scene, op, ctx, new_id=None):
    """Apply one typed edit to a validated scene; returns a NEW validated scene (revision+1, parent=old id)."""
    if not isinstance(op, dict) or op.get('op') not in EDIT_OPS:
        fail('cover_edit', 'Edit must be an object with op in ' + ', '.join(EDIT_OPS))
    scene = validate(scene, ctx)
    out = copy.deepcopy(scene)
    kind = op['op']
    if kind == 'move':
        _only(op, ('target', 'by', 'to', 'yaw'))
        rows, i = _target(out, op.get('target'))
        if ('by' in op) == ('to' in op):
            fail('cover_edit', 'move needs exactly one of by or to')
        if 'by' in op:
            d = _vec(op, 'by', 30.0)
            rows[i]['at'] = [round(rows[i]['at'][k] + d[k], 3) for k in range(3)]
        else:
            rows[i]['at'] = _vec(op, 'to')
        if 'yaw' in op:
            rows[i]['yaw'] = _num(op, 'yaw', -360, 360)
    elif kind == 'nudge':
        _only(op, ('target', 'direction', 'metres'))
        rows, i = _target(out, op.get('target'))
        if op.get('direction') not in ('left', 'right', 'forward', 'back', 'up', 'down'):
            fail('cover_edit', 'direction must be left, right, forward, back, up or down (as seen from the camera)')
        m = _num(op, 'metres', 0.05, 30)
        az = math.radians(out['camera']['azimuth_deg'])
        right = [math.cos(az), 0.0, -math.sin(az)]
        fwd = [-math.sin(az), 0.0, -math.cos(az)]
        vec = {'left': [-right[0], 0, -right[2]], 'right': right, 'forward': fwd, 'back': [-fwd[0], 0, -fwd[2]],
               'up': [0, 1, 0], 'down': [0, -1, 0]}[op['direction']]
        rows[i]['at'] = [round(rows[i]['at'][k] + vec[k] * m, 3) for k in range(3)]
    elif kind == 'replace':
        rows, i = _target(out, op.get('target'))
        if op['target'].startswith('cast:'):
            _only(op, ('target', 'id'))
            cid = op.get('id')
            if cid not in ctx.cast:
                fail('cover_edit', 'replacement %r has no bound model in this project' % (cid,))
            rows[i]['id'] = cid
            rows[i]['clip'] = _clip(ctx.cast[cid], [rows[i]['clip'], 'idle'])
        else:
            _only(op, ('target', 'kit'))
            rows[i]['kit'] = op.get('kit')
    elif kind == 'add':
        _only(op, ('kind', 'kit', 'id', 'at', 'yaw', 'scale', 'clip', 'frame'))
        what = op.get('kind')
        if what not in ('hero', 'prop', 'cast'):
            fail('cover_edit', 'add.kind must be hero, prop or cast')
        yaw = _num(op, 'yaw', -360, 360) if 'yaw' in op else 180.0
        if what == 'cast':
            cid = op.get('id')
            if cid not in ctx.cast:
                fail('cover_edit', 'cast id %r has no bound model in this project (available: %s)' % (cid, ', '.join(sorted(ctx.cast))))
            if 'at' in op:
                at = _vec(op, 'at')
            else:
                anchor = out['cast'][0]['at'] if out['cast'] else out['camera']['target']
                side = 0.8 if ctx.cast[cid]['animal'] else 1.1
                at = [round(anchor[0] + side, 3), 0.0, round(anchor[2] + 0.5, 3)]
            row = {'id': cid, 'clip': op.get('clip') or _clip(ctx.cast[cid], ['idle']), 'frame': int(op.get('frame', 0)),
                   'at': at, 'yaw': yaw, 'scale': _num(op, 'scale', 0.8, 1.25) if 'scale' in op else 1.0}
            out['cast'].append(row)
        else:
            if 'at' not in op:
                fail('cover_edit', 'add %s needs at [x, y, z]' % what)
            row = {'kit': op.get('kit'), 'at': _vec(op, 'at'), 'yaw': yaw,
                   'scale': _num(op, 'scale', 0.2, 4) if 'scale' in op else 1.0}
            out['hero' if what == 'hero' else 'props'].append(row)
    elif kind == 'remove':
        _only(op, ('target',))
        rows, i = _target(out, op.get('target'))
        del rows[i]
    elif kind == 'lighting':
        _only(op, ('mood', 'key_energy', 'ambient_energy', 'fill_energy', 'key_azimuth_deg', 'key_elevation_deg',
                   'fog_near_m', 'fog_far_m', 'fog_density', 'glow_strength', 'stars', 'aurora_strength', 'clouds',
                   'exposure'))
        if 'mood' in op:
            if op['mood'] not in cover_style.MOODS:
                fail('cover_edit', 'mood must be one of ' + ', '.join(cover_style.MOODS))
            fresh = base_scene({'id': out['game']['id'], 'title': out['game']['title']}, ctx, out['seed'], out['id'], op['mood'],
                               ground=out['ground']['preset'])
            for sec in ('sky', 'fog'):
                out[sec] = fresh[sec]
            lamps = out['light']['lamps']
            out['light'] = fresh['light']
            out['light']['lamps'] = [dict(l, color=ctx.style.colour(op['mood'], 'lamp')) for l in lamps]
            out['mood'] = op['mood']
            for k in ('fill', 'fill2', 'outline', 'shadow'):
                out['title'][k] = fresh['title'][k]
            if out['particles']['kind'] == 'fireflies' and op['mood'] not in ('night', 'dusk'):
                out['particles']['kind'] = 'none'
        for key, (sec, field, lo, hi) in {'key_energy': ('light', 'key_energy', 0, 1), 'ambient_energy': ('light', 'ambient_energy', 0, 1),
                                          'fill_energy': ('light', 'fill_energy', 0, 1), 'key_azimuth_deg': ('light', 'key_azimuth_deg', -180, 180),
                                          'key_elevation_deg': ('light', 'key_elevation_deg', 5, 85), 'fog_near_m': ('fog', 'near_m', 0, 60),
                                          'fog_far_m': ('fog', 'far_m', 4, 160), 'fog_density': ('fog', 'density', 0, 0.95),
                                          'glow_strength': ('sky', 'glow_strength', 0, 0.9), 'aurora_strength': ('sky', 'aurora_strength', 0, 0.8),
                                          'clouds': ('sky', 'clouds', 0, 1), 'exposure': ('sky', 'exposure', 0.3, 1.0)}.items():
            if key in op:
                out[sec][field] = _num(op, key, lo, hi)
        if 'stars' in op:
            out['sky']['stars'] = int(_num(op, 'stars', 0, 400))
    elif kind == 'camera':
        _only(op, ('focal_mm', 'distance_m', 'azimuth_deg', 'elevation_deg', 'roll_deg', 'framing', 'target'))
        cam = out['camera']
        for key, lo, hi in (('focal_mm', 18, 85), ('distance_m', 2, 45), ('azimuth_deg', -180, 180), ('elevation_deg', -12, 65), ('roll_deg', -8, 8)):
            if key in op:
                cam[key] = _num(op, key, lo, hi)
        if 'framing' in op:
            if op['framing'] not in FRAMING_ASPECT:
                fail('cover_edit', 'framing must be poster, banner or square')
            cam['framing'] = op['framing']
        if 'target' in op:
            cam['target'] = _vec(op, 'target')
    elif kind == 'reframe':
        _only(op, ('top', 'bottom', 'subjects'))
        top, bottom = _num(op, 'top', 0.0, 0.9), _num(op, 'bottom', 0.1, 1.0)
        if bottom <= top + 0.1:
            fail('cover_edit', 'reframe bottom must exceed top by 0.1')
        groups = {'all': ('hero', 'cast'), 'cast': ('cast',), 'hero': ('hero',)}.get(op.get('subjects', 'all'))
        if groups is None:
            fail('cover_edit', 'reframe.subjects must be all, cast or hero')
        out = frame(out, ctx, top, bottom, groups=groups)
    elif kind == 'title':
        _only(op, ('text', 'subtitle', 'placement', 'letter', 'size', 'fill', 'fill2', 'outline', 'shadow'))
        for key in op:
            if key != 'op':
                out['title'][key] = op[key]
    elif kind == 'particles':
        _only(op, ('kind', 'count', 'color', 'size_m'))
        for key in op:
            if key != 'op':
                out['particles'][key] = op[key]
    elif kind == 'pose':
        _only(op, ('target', 'clip', 'frame', 'yaw'))
        rows, i = _target(out, op.get('target'))
        if not op['target'].startswith('cast:'):
            fail('cover_edit', 'pose applies to cast members')
        for key in ('clip', 'frame', 'yaw'):
            if key in op:
                rows[i][key] = op[key]
    elif kind == 'finish':
        _only(op, ('vignette', 'contrast', 'saturation', 'lift', 'band_edge', 'mark'))
        for key in op:
            if key != 'op':
                out['finish'][key] = op[key]
    out['parent'] = scene['id']
    out['revision'] = scene['revision'] + 1
    out['id'] = new_id or _revision_id(scene['id'], out['revision'])
    return validate(out, ctx)


def _revision_id(ident, revision):
    base = re.sub(r'-r[0-9]+$', '', ident)[:40]
    return '%s-r%d' % (base, revision)


def apply_edits(scene, ops, ctx, final_id=None):
    for i, op in enumerate(ops):
        scene = apply_edit(scene, op, ctx, new_id=final_id if (final_id and i == len(ops) - 1) else None)
    return scene


def explain(exc):
    return str(exc) if isinstance(exc, Fault) else type(exc).__name__ + ': ' + str(exc)
