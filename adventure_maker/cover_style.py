"""Cover styles: a game's pack (or a bundled style profile) -> palette, kit geometry, mood colours, binding table.

Stdlib only. Nothing here invents colours: every colour a cover may use is a member of the style's palette
(pack palette plus the colours its own view.json look profiles already use, or a style profile's named palette).
Mood presets are neutral targets snapped to the nearest palette colour in CIE Lab, so the same staging rules
produce a polar night, a forest dusk or a desert noon without theme-specific code.

Light energies are bounded by the shared N64 look convention (kits/core/n64_look.json environments.<type>.ranges),
the "allowed ranges" a cover may override within.
"""
import json
import math
from pathlib import Path

from .safety import JSON_LIMIT, fail, inspect_path, relative, strict_json

ROOT = Path(__file__).resolve().parents[1]
KIT_PACKS = ('polar_pod', 'forest_village')
MOODS = ('night', 'dusk', 'day', 'dawn', 'interior')
# mood -> N64 look convention environment type (ranges for ambient/key/fill/fog/grade)
ENVIRONMENT = {'night': 'exterior_night', 'dusk': 'exterior_day', 'day': 'exterior_day', 'dawn': 'exterior_day',
               'interior': 'interior_warm'}
# bundled style profiles a cover may name (bundle-relative); project-local profiles are not loaded here
PROFILES = {'n64_base': 'profiles/n64_base/profile.json',
            'polar_pod_example': 'profiles/examples/polar_pod/profile.json',
            'warm_desert_example': 'profiles/examples/warm_desert/profile.json'}
# climate of a style profile -> kit geometry that exists in this bundle
CLIMATE_KITS = {'polar': 'polar_pod', 'arid': 'forest_village', 'temperate': 'forest_village'}
# ground preset -> kit texture roles, first existing wins (kits/library/<kit_pack>/textures/tex_<pack>_<role>.png)
GROUND_ROLES = {'snowfield': ['snow', 'field'], 'ice': ['ice', 'water', 'snow'], 'meadow': ['field', 'grass'],
                'dunes': ['field', 'dirt', 'path'], 'cobbles': ['path', 'stone'], 'earth': ['dirt', 'path', 'field'],
                'stone': ['stone', 'rock'], 'deck': ['wood', 'floor']}
# neutral mood targets (sRGB hex), snapped per style; fog follows the horizon outdoors (N64 convention)
TARGETS = {
    'night': {'zenith': '#0a1030', 'horizon': '#7088f0', 'glow': '#ffd9a0', 'aurora': '#9fe6ff', 'cloud': '#4a5378',
              'key': '#ebeefe', 'ambient': '#a3abcd', 'fill': '#6a7dc4', 'kicker': '#c3cbfb', 'lamp': '#f0a050',
              'snow': '#ffffff', 'firefly': '#ffe27a', 'outline': '#06081a', 'shadow': '#02030c', 'fill2': '#a8b8ff',
              'title': '#ffffff'},
    'dusk': {'zenith': '#2a2c64', 'horizon': '#f0a060', 'glow': '#ffd890', 'aurora': '#c060a0', 'cloud': '#a85878',
             'key': '#ffc890', 'ambient': '#9080a8', 'fill': '#4c5ca0', 'kicker': '#ffd0a0', 'lamp': '#f0a050',
             'snow': '#fff0e0', 'firefly': '#ffe27a', 'outline': '#1a0c10', 'shadow': '#0c0608', 'fill2': '#ffd890',
             'title': '#fff8e8'},
    'day': {'zenith': '#2f62c0', 'horizon': '#d4e8f4', 'glow': '#fff6d8', 'aurora': '#ffffff', 'cloud': '#ffffff',
            'key': '#fff4dc', 'ambient': '#a8b8d0', 'fill': '#6488bc', 'kicker': '#ffffff', 'lamp': '#ffe0a0',
            'snow': '#ffffff', 'firefly': '#fff0a0', 'outline': '#101828', 'shadow': '#080c14', 'fill2': '#ffe08a',
            'title': '#ffffff'},
    'dawn': {'zenith': '#5878c4', 'horizon': '#f8c8b0', 'glow': '#fff0c8', 'aurora': '#f0b0c8', 'cloud': '#f0b8b8',
             'key': '#ffe0c0', 'ambient': '#b0a4c4', 'fill': '#7080bc', 'kicker': '#ffe8d0', 'lamp': '#ffd090',
             'snow': '#ffffff', 'firefly': '#fff0a0', 'outline': '#181020', 'shadow': '#0c0810', 'fill2': '#ffd0b0',
             'title': '#ffffff'},
    'interior': {'zenith': '#141020', 'horizon': '#3a2a30', 'glow': '#ffc070', 'aurora': '#ffc070', 'cloud': '#3a2a30',
                 'key': '#ffd8a0', 'ambient': '#8a7a90', 'fill': '#4a5490', 'kicker': '#ffd8a0', 'lamp': '#ffc070',
                 'snow': '#ffe8c8', 'firefly': '#ffe27a', 'outline': '#140a08', 'shadow': '#080404', 'fill2': '#ffd890',
                 'title': '#fff8e8'},
}
# default energies per mood (inside the convention ranges); fog distances are multiplied by the stage size later
# night over snow/ice keeps the luminous polar look; night over grass, dunes or stone is genuinely darker (moonlight)
NIGHT_DARK = {'key': 0.46, 'ambient': 0.42, 'fill': 0.2, 'sky': 0.12, 'ground': 0.08, 'kicker': 0.22}
ENERGY = {'night': {'key': 0.48, 'ambient': 0.58, 'fill': 0.26, 'sky': 0.2, 'ground': 0.12, 'kicker': 0.2},
          'dusk': {'key': 0.52, 'ambient': 0.5, 'fill': 0.24, 'sky': 0.16, 'ground': 0.1, 'kicker': 0.2},
          'day': {'key': 0.6, 'ambient': 0.45, 'fill': 0.18, 'sky': 0.18, 'ground': 0.1, 'kicker': 0.16},
          'dawn': {'key': 0.56, 'ambient': 0.44, 'fill': 0.2, 'sky': 0.16, 'ground': 0.1, 'kicker': 0.18},
          'interior': {'key': 0.45, 'ambient': 0.45, 'fill': 0.18, 'sky': 0.12, 'ground': 0.12, 'kicker': 0.2}}


# ------------------------------------------------------------------ colour maths (stdlib)
def hex_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lab(hexv):
    r, g, b = (_lin(c) for c in hex_rgb(hexv))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def delta_e(a, b):
    la, lb = lab(a), lab(b)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def luma(hexv):
    r, g, b = hex_rgb(hexv)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def snap(target, palette, k_light=0.5):
    """Nearest palette colour to a target in CIE Lab with lightness down-weighted (k_light), so a chromatic target
    (a peach dawn horizon) lands on a chromatic palette colour rather than on white (ties: palette order)."""
    best, dist = None, None
    lt = lab(target)
    for c in palette:
        lc = lab(c)
        d = math.sqrt((k_light * (lt[0] - lc[0])) ** 2 + (lt[1] - lc[1]) ** 2 + (lt[2] - lc[2]) ** 2)
        if dist is None or d < dist - 1e-9:
            best, dist = c, d
    return best


def normal_hex(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != '#':
        fail('cover_style', 'Colour must be #RRGGBB')
    try:
        int(value[1:], 16)
    except ValueError:
        fail('cover_style', 'Colour must be #RRGGBB')
    return value.lower()


# ------------------------------------------------------------------ bundle data
def _read(root, rel):
    path = inspect_path(Path(root) / relative(rel))
    if not path.is_file():
        fail('component_unavailable', 'Cover style data missing: ' + rel)
    with path.open('rb') as f:
        return strict_json(f.read(JSON_LIMIT + 1))


def convention(root=ROOT):
    return _read(root, 'kits/core/n64_look.json')


def ranges(mood, root=ROOT, conv=None):
    """Allowed light/fog/grade ranges for a mood, from the shared N64 look convention."""
    conv = conv or convention(root)
    env = conv.get('environments', {}).get(ENVIRONMENT[mood], {}).get('ranges', {})
    out = {'ambient': [0.3, 0.65], 'key': [0.2, 0.6], 'fill': [0.05, 0.35], 'fog.near': [4.0, 20.0],
           'fog.far': [14.0, 70.0], 'grade.contrast': [0.95, 1.12], 'grade.saturation': [0.8, 1.05]}
    for k, v in env.items():
        if isinstance(v, list) and len(v) == 2:
            out[k] = [float(v[0]), float(v[1])]
    return out


class CoverStyle:
    """Resolved, read-only style data for staging and validation."""

    def __init__(self, ident, source, kit_pack, label, palette, band, remap, view, bindings, root=ROOT, accent=None):
        if kit_pack not in KIT_PACKS:
            fail('cover_style', 'No built kit geometry for kit pack ' + str(kit_pack))
        self.id = ident
        self.source = source
        self.kit_pack = kit_pack
        self.label = label
        self.palette = list(dict.fromkeys(normal_hex(c) for c in palette))
        self.band = normal_hex(band)
        self.remap = remap  # None or 5 colours dark -> white
        self.view = view
        self.bindings = bindings
        self.root = Path(root)
        self.accent = normal_hex(accent) if accent else self.band
        if self.band not in self.palette:
            self.palette.append(self.band)
        if len(self.palette) < 4:
            fail('cover_style', 'Style palette too small for a cover (need >= 4 colours)')

    # -- vocabulary
    def kits(self):
        return sorted(self.bindings)

    def kit_row(self, ref):
        row = self.bindings.get(ref)
        if not isinstance(row, dict) or not isinstance(row.get('glb'), str):
            fail('cover_scene', 'Unknown kit ref for style %s: %s' % (self.id, ref))
        return row

    def ground_texture(self, preset):
        for role in GROUND_ROLES[preset]:
            rel = 'kits/library/%s/textures/tex_%s_%s.png' % (self.kit_pack, self.kit_pack, role)
            if (self.root / rel).is_file():
                return rel, role
        fail('cover_style', 'No ground texture for preset %s in %s' % (preset, self.kit_pack))

    def colour(self, mood, role):
        return snap(TARGETS[mood][role], self.palette)

    def darkest(self):
        return min(self.palette, key=luma)

    def lightest(self):
        return max(self.palette, key=luma)

    def mood_preset(self, mood, ground=None):
        """Palette-snapped sky/light/fog/title colours and default energies for a mood (and ground preset)."""
        t = {role: self.colour(mood, role) for role in TARGETS[mood]}
        if t['zenith'] == t['horizon']:
            # a narrow palette collapsed the gradient: take the next-lightest colour toward the horizon target
            others = sorted((c for c in self.palette if c != t['zenith']), key=lambda c: delta_e(TARGETS[mood]['horizon'], c))
            t['horizon'] = others[0]
        t['title'] = self.lightest() if luma(self.lightest()) > 0.85 else t['title']
        t['outline'] = self.darkest()
        t['shadow'] = self.darkest()
        t['fill2'] = self.complement(t['horizon'])
        energy = dict(NIGHT_DARK if (mood == 'night' and ground not in (None, 'snowfield', 'ice')) else ENERGY[mood])
        if self.remap and mood in ('day', 'dawn'):
            energy['key'] = round(energy['key'] * 0.85, 3)   # ramp-recoloured kits: keep the light end off white
        return {'colours': t, 'energy': energy}

    def complement(self, scene_hex):
        """Logotype accent: the most saturated bright palette colour on the far side of the colour wheel from the
        scene's dominant hue (warm gold on a blue night, sky blue on a desert noon)."""
        import colorsys
        sr, sg, sb = (v / 255.0 for v in hex_rgb(scene_hex))
        sh = colorsys.rgb_to_hsv(sr, sg, sb)[0]
        best, score = None, -1.0
        for c in self.palette:
            r, g, b = (v / 255.0 for v in hex_rgb(c))
            h, s_, v = colorsys.rgb_to_hsv(r, g, b)
            if s_ < 0.25 or v < 0.55:
                continue
            dist = abs(((h - sh) + 0.5) % 1.0 - 0.5) * 2.0   # 0 same hue .. 1 opposite
            sc = dist * 1.2 + s_ * 0.6 + v * 0.4
            if sc > score + 1e-9:
                best, score = c, sc
        return best or self.accent

    def summary(self):
        return {'id': self.id, 'source': self.source, 'kit_pack': self.kit_pack, 'label': self.label,
                'palette': list(self.palette), 'band': self.band, 'remap': self.remap}


def _pack_view(root, pack_id, kit_pack):
    for base in (pack_id, kit_pack):
        if (Path(root) / 'packs' / base / 'view.json').is_file():
            return _read(root, 'packs/%s/view.json' % base)
    return {}


def _pack_bindings(root, pack_id, kit_pack):
    for base in (pack_id, kit_pack):
        if (Path(root) / 'packs' / base / 'bindings.json').is_file():
            return _read(root, 'packs/%s/bindings.json' % base).get('assets', {})
    fail('component_unavailable', 'No binding table for pack ' + pack_id)


def _view_colours(view):
    """Colours a pack's own look profiles already use (part of its style data)."""
    out = []
    for prof in (view.get('look', {}).get('profiles', {}) or {}).values():
        for key in ('ambient', 'fill', 'key', 'sky', 'ground'):
            v = prof.get(key)
            if isinstance(v, list) and v and isinstance(v[0], str):
                out.append(v[0])
        for key in ('background',):
            if isinstance(prof.get(key), str):
                out.append(prof[key])
        fog = prof.get('fog') or {}
        if isinstance(fog.get('color'), str):
            out.append(fog['color'])
    return out


def from_pack(pack, root=ROOT):
    """Style from a validated Hermes64 pack (bundled or project snapshot)."""
    kit_pack = pack['kit_pack_id']
    view = _pack_view(root, pack['id'], kit_pack)
    palette = list(pack['palette']) + list(view.get('palette_colors') or []) + _view_colours(view)
    palette = [normal_hex(c) for c in palette]
    # band: the most saturated mid-value palette colour that is not a warm accent (the pack's signature hue)
    band = _signature(palette)
    accent = snap('#f2a65a', palette)
    label = pack.get('name') or pack['id']
    if label.upper().startswith('N64 V0'):
        label = 'Forest Village'
    return CoverStyle(pack['id'], 'pack', kit_pack, _label(label), palette, band, None, view,
                      _pack_bindings(root, pack['id'], kit_pack), root, accent)


def from_profile(profile_id, root=ROOT, kit_pack=None):
    """Style from a bundled style profile; geometry from the built kit pack matching its climate."""
    if profile_id not in PROFILES:
        fail('cover_style', 'Unknown bundled style profile ' + str(profile_id) + '; choose one of ' + ', '.join(sorted(PROFILES)))
    prof = _read(root, PROFILES[profile_id])
    sec = prof['sections']
    colours = sec['palette']['colors']
    palette = [normal_hex(c) for c in colours.values()]
    climate = sec.get('exterior', {}).get('climate', 'temperate')
    kp = kit_pack or CLIMATE_KITS.get(climate, 'forest_village')
    ramp_ids = sec['palette'].get('ramps', {}).get('light') or ['dark', 'low', 'mid', 'light', 'white']
    remap = [normal_hex(colours[k]) for k in ramp_ids][:5]
    while len(remap) < 5:
        remap.append(remap[-1])
    view = _pack_view(root, kp, kp)
    band = normal_hex(colours.get('accent') if profile_id == 'n64_base' else colours.get('mid', palette[0]))
    if profile_id == 'warm_desert_example':
        band = normal_hex(colours['mid'])
    label = {'n64_base': 'Classic Base', 'polar_pod_example': 'Polar Pod Example', 'warm_desert_example': 'Warm Desert'}[profile_id]
    return CoverStyle(profile_id, 'profile', kp, label, palette, band, remap, view, _pack_bindings(root, kp, kp), root,
                      normal_hex(colours.get('accent', band)))


def _signature(palette):
    best, score = palette[0], -1.0
    for c in palette:
        r, g, b = (x / 255.0 for x in hex_rgb(c))
        mx, mn = max(r, g, b), min(r, g, b)
        sat = (mx - mn) / mx if mx > 0 else 0.0
        val = mx
        s = sat * (1.0 - abs(val - 0.62) * 1.6)
        if s > score + 1e-9:
            best, score = c, s
    return best


def _label(text):
    keep = ''.join(ch for ch in str(text) if ch.isalnum() or ch in " .,'!?&:-")
    return (keep.strip() or 'Style')[:32]


def resolve(spec, packs=None, root=ROOT, profile=None, kit_pack=None):
    """Style for a story spec: an explicit bundled profile wins, else the spec's bound pack, else n64_base."""
    if profile:
        return from_profile(profile, root, kit_pack)
    ref = (spec.get('metadata') or {}).get('hermes64_pack') if isinstance(spec, dict) else None
    if isinstance(ref, dict) and packs is not None:
        try:
            pack = packs.selected(spec)
        except Exception:
            pack = packs.get(ref['id'])
        return from_pack(pack, root)
    return from_profile('n64_base', root, kit_pack)


def load_json_text(text):
    """Convenience for tests and tools: strict JSON from text."""
    return strict_json(text)


def dump(value):
    return json.dumps(value, sort_keys=True, indent=1)
