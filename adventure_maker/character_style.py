"""Character style locks (contracts/character/style-1.0.0): the character rules of one style profile.

A lock lives at profiles/character-styles/<id>.json and is one of two kinds:
  profile      the character palette is DERIVED from the style profile's eight palette anchors by the lock's
               linear-light mix table, so selecting another profile recolours every character with no recipe change
  legacy_pack  roles bind straight to a vendored palette pack (characters/gen/packs/<pack>), which is what today's
               runtime renders; the approved cast reproduces byte-identically through it
Either way the generator only ever sees palette NAMES resolved from recipe ROLES through the lock, an inline pack
synthesised here, the lock's proportion ranges (refuse / clamp) and its budgets. Stdlib only, no Blender, no
network; every path is confined to the plugin root.
"""
import copy
import hashlib
import json
from pathlib import Path

from . import style_profile as SP

ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = 'profiles/character-styles'
SCHEMA = 'contracts/character/style-1.0.0.json'
PROFILES = 'profiles'

# Canonical palette roles. Every lock binds every role; recipes name roles, never palette names or colours.
ROLE_FAMILIES = {
    'skin': ['skin_light', 'skin_fair', 'skin_mid', 'skin_tan', 'skin_deep'],
    'hair': ['hair_black', 'hair_brown', 'hair_auburn', 'hair_blond', 'hair_grey', 'hair_white', 'hair_dyed'],
    'eye': ['eye_dark', 'eye_brown', 'eye_cool', 'eye_light'],
    'cloth': ['cloth_light', 'cloth_pale', 'cloth_mid', 'cloth_dark', 'cloth_deep', 'cloth_warm', 'cloth_cool',
              'cloth_muted', 'cloth_accent', 'cloth_bright'],
    'trim': ['trim_light', 'trim_dark', 'trim_accent'],
    'leather': ['leather', 'leather_dark'],
    'metal': ['metal_light', 'metal_mid', 'metal_dark'],
    'glow': ['glow'],
    'machine': ['shell', 'shell_light', 'shell_alt', 'shell_dark', 'joint', 'lens', 'visor', 'warning', 'emblem'],
    'coat': ['coat_dark', 'coat_mid', 'coat_light', 'coat_warm', 'eye_glow'],
    'internal': ['lip'],
}
ROLES = [r for fam in ROLE_FAMILIES.values() for r in fam]
WEAR = ('cloth', 'trim', 'leather', 'metal')
# recipe colour slot -> role families it may take ("wrong palette role" is any other family)
SLOT_FAMILIES = {
    'skin': ('skin',), 'hair': ('hair',), 'eyes': ('eye',),
    'top': WEAR, 'garment': WEAR, 'hat': WEAR, 'legs': WEAR, 'collar': WEAR, 'extra': WEAR + ('glow',), 'extra2': WEAR + ('glow',),
    'trim': WEAR + ('glow',), 'accent': WEAR + ('glow',), 'belt': WEAR, 'boots': ('leather', 'metal', 'cloth', 'trim'),
    'gloves': ('leather', 'cloth', 'metal', 'trim'),
    'hood': WEAR, 'vest': WEAR, 'cape': WEAR, 'skirt': WEAR, 'armband': WEAR + ('glow',),
    'shell': ('machine', 'metal'), 'shell_light': ('machine', 'metal'), 'shell_alt': ('machine', 'metal', 'cloth'),
    'dark': ('machine', 'metal'), 'joint': ('machine', 'metal'), 'lens': ('machine', 'glow'), 'visor': ('machine',),
    'accent_robot': ('machine', 'cloth', 'trim'), 'emblem': ('machine', 'trim', 'glow'),
    'coat': ('coat', 'hair'), 'coat2': ('coat', 'hair'), 'coat3': ('coat', 'hair'), 'eye_glow': ('coat', 'eye'),
}
FAMILY_OF = {r: fam for fam, rs in ROLE_FAMILIES.items() for r in rs}
SPECIAL_COLOURS = {'black': '#000000', 'pure_white': '#ffffff'}


class CharacterStyleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def _req(cond, code, message):
    if not cond:
        raise CharacterStyleError(code, message)


def _read_json(root, rel):
    try:
        return SP.parse_json(SP.read_confined(root, rel))
    except SP.StyleError as exc:
        raise CharacterStyleError(exc.code, str(exc)) from exc


# ------------------------------------------------------------------ colour maths (sRGB <-> linear, deterministic)
def _hex(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v * 255.)))) for v in c)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255. for i in (1, 3, 5))


def _lin(c):
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c)


def _srgb(c):
    return tuple(v * 12.92 if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055 for v in c)


def derive_palette(anchors, derive):
    """[(name, hex)] in table order. anchors: {name: '#rrggbb'} from the profile palette."""
    lin = {k.lower(): _lin(_rgb(v.lower())) for k, v in anchors.items()}
    for k, v in SPECIAL_COLOURS.items():
        lin.setdefault(k, _lin(_rgb(v)))
    out = []
    for row in derive:
        a, b, t = row['mix']
        _req(a in lin and b in lin, 'PALETTE', 'derive %s mixes unknown colour %s/%s' % (row['name'], a, b))
        _req(type(t) in (int, float) and 0 <= t <= 1, 'PALETTE', 'derive %s weight' % row['name'])
        c = tuple(lin[a][i] * (1. - t) + lin[b][i] * t for i in range(3))
        d = float(row.get('desaturate', 0.))
        if d:
            y = .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
            c = tuple(v * (1. - d) + y * d for v in c)
        hx = _hex(_srgb(c))
        lin[row['name']] = _lin(_rgb(hx))          # later rows mix the quantised colour (what the texels use)
        out.append((row['name'], hx))
    names = [n for n, _ in out]
    _req(len(set(names)) == len(names), 'PALETTE', 'duplicate derived name')
    return out


# ------------------------------------------------------------------ lock loading
class Lock:
    """A resolved character lock: roles, ranges, budgets, inline generator pack and digests."""

    def __init__(self, doc, chain, root):
        self.doc = doc; self.chain = chain; self.root = root
        self.id = doc['id']
        self.source = doc['source']
        self.kind = self.source['kind']
        self.roles = dict(doc['roles'])
        self.proportions = copy.deepcopy(doc['proportions'])
        self.budgets = dict(doc['budgets'])
        self.face = copy.deepcopy(doc['face'])
        self.texture = copy.deepcopy(doc['texture'])
        self.bodies = list(doc['bodies'])
        self.parts_denied = set(doc.get('parts_denied', []))
        self.defaults = dict(doc['defaults'])
        self.profile = None
        self.profile_closure_sha256 = None
        if self.kind == 'profile':
            prof = self.source['profile']
            try:
                resolved = SP.resolve_profile(root / PROFILES, prof['path'])
            except SP.StyleError as exc:
                raise CharacterStyleError('PROFILE', '%s: %s' % (prof['path'], exc)) from exc
            _req(resolved.profile['id'] == prof['id'] and resolved.profile['version'] == prof['version'], 'PROFILE',
                 'lock %s pins %s@%s but the file is %s@%s' % (self.id, prof['id'], prof['version'],
                                                              resolved.profile['id'], resolved.profile['version']))
            self.profile = resolved.profile
            self.profile_closure_sha256 = resolved.closure_sha256
            self.anchors = dict(resolved.profile['sections']['palette']['colors'])
            self.colours = derive_palette(self.anchors, doc['palette']['derive'])
            self.pack_id = 'cs_%s_%s' % (self.id, self.palette_digest()[:8])
        else:
            self.anchors = None
            pack = _read_json(root, 'characters/gen/packs/%s/pack.json' % self.source['pack'])
            self.colours = list(zip(pack['palette_names'], pack['palette']))
            self.pack_id = self.source['pack']
            self._legacy_pack = pack
        self._check_roles()

    def palette_digest(self):
        return hashlib.sha256(json.dumps(self.colours, separators=(',', ':')).encode()).hexdigest()

    def names(self):
        return [n for n, _ in self.colours]

    def _check_token(self, tok, where):
        for part in str(tok).split('+'):
            _req(part in self.names(), 'ROLE', '%s -> %r is not a palette name of lock %s' % (where, tok, self.id))

    def _check_roles(self):
        missing = [r for r in ROLES if r not in self.roles]
        _req(not missing, 'ROLE', 'lock %s leaves roles unbound: %s' % (self.id, ', '.join(missing)))
        extra = [r for r in self.roles if r not in ROLES]
        _req(not extra, 'ROLE', 'lock %s binds unknown roles: %s' % (self.id, ', '.join(extra)))
        for r, tok in self.roles.items():
            self._check_token(tok, 'role ' + r)
        for slot, role in self.defaults.items():
            _req(role in self.roles, 'ROLE', 'default %s -> unknown role %s' % (slot, role))

    def resolve(self, role):
        _req(role in self.roles, 'ROLE', 'unknown palette role %r' % role)
        return self.roles[role]

    def digest(self):
        body = {'lock': self.doc, 'colours': self.colours, 'profile_closure_sha256': self.profile_closure_sha256}
        return hashlib.sha256(SP.canonical_bytes(body)).hexdigest()

    def pack(self):
        """The generator pack for this lock (vendored for legacy_pack, synthesised for profile)."""
        if self.kind == 'legacy_pack':
            return copy.deepcopy(self._legacy_pack)
        pal = self.doc['palette']
        names = self.names()
        for ramp in list(pal['ramps'].values()) + [pal['light_ramp']] + list(pal['skin_ramps'].values()):
            for tok in ramp:
                self._check_token(tok, 'ramp')
        r = self.roles
        sp = pal['specials']
        face_defaults = {'skin': r['skin_mid'], 'hair_color': r['hair_brown'], 'eye_color': r['eye_brown'],
                         'brow_color': r['hair_brown'], 'lip_color': r['lip'], 'top_color': r['cloth_mid'],
                         'garment_color': r['cloth_dark'], 'trim_color': r['trim_light'], 'accent_color': r['cloth_accent'],
                         'bottom_color': r['cloth_deep'], 'boot_color': r['leather_dark'], 'glove_color': r['leather'],
                         'belt_color': r['leather_dark'], 'collar_color': r['cloth_muted'], 'extra_color': r['trim_accent'],
                         'extra_color_2': r['cloth_warm']}
        character_defaults = {'head_mode': 'faceless', 'headwear': 'hood', 'skin': r['glow'], 'headwear_color': r['cloth_light'],
                              'top_color': r['cloth_mid'], 'vest_color': r['cloth_dark'], 'vest_trim_color': r['cloth_accent'],
                              'mantle_color': r['cloth_mid'], 'skirt_color': r['cloth_dark'], 'bottom_color': r['cloth_deep'],
                              'glove_color': r['cloth_light'], 'boot_color': r['leather_dark'], 'belt_color': r['leather'],
                              'armband_color': r['cloth_accent']}
        return {
            'id': self.pack_id, 'version': '1.0.0',
            'note': 'Synthesised by adventure_maker.character_style from lock %s over profile %s (palette %s).' % (
                self.id, self.profile['id'], self.palette_digest()[:12]),
            'palette': [h for _, h in self.colours], 'palette_names': names,
            'ramps': copy.deepcopy(pal['ramps']), 'char_ramps': {}, 'skin_ramps': copy.deepcopy(pal['skin_ramps']),
            'light_ramp': list(pal['light_ramp']),
            'character_env': {'stops': [r['metal_dark'], r['metal_mid'], r['metal_light'], sp['eye_white']]},
            'env_maps': {}, 'face_defaults': face_defaults, 'character_defaults': character_defaults,
            'animal_defaults': {'coat_color_1': r['coat_mid'], 'coat_color_2': r['coat_light'], 'coat_color_3': r['coat_warm'],
                                'eye_color': r['eye_glow']},
            'prop_colors': {'body': r['metal_mid'], 'dark': r['cloth_deep'], 'light': r['cloth_light'], 'metal': r['metal_mid'],
                            'glass': r['glow'], 'accent': r['cloth_accent'], 'cloth': r['cloth_muted'], 'wood': r['leather']},
            'eye_white': sp['eye_white'], 'eye_glint': sp.get('eye_glint', sp['eye_white']), 'face_line': sp['face_line'],
            'teeth': sp['teeth'], 'sole': sp['sole'],
            'blush': sp['blush']}

    def combat_roles(self):
        """Robot/creature painter roles bound through the lock (core/roles.py binding format)."""
        r = self.roles
        out = {k: r[k] for k in ROLE_FAMILIES['machine']}
        out.update(shell_light=r['shell_light'])
        if self.kind == 'legacy_pack':
            base = _read_json(self.root, 'characters/gen/packs/%s/combat_roles.json' % self.source['pack'])['roles']
            base = dict(base); base.update(out)
            return base
        out.update({'hide': r['coat_dark'], 'hide_dark': r['trim_dark'], 'mane': r['coat_light'], 'stone': r['metal_light'],
                    'stone_dark': r['metal_dark'], 'lichen': r['cloth_cool'], 'plate': r['metal_mid'], 'hoof': r['joint'],
                    'eye': r['joint'], 'eye_glow': r['eye_glow'], 'weave': r['leather'], 'weave_dark': r['leather_dark'],
                    'weave_light': r['cloth_pale'], 'band': r['cloth_warm'], 'mask': r['cloth_light'], 'crest': r['cloth_cool'],
                    'crest_tip': r['cloth_accent'], 'leg': r['trim_dark'], 'wing': r['cloth_mid'], 'core_glow': r['glow'],
                    'wood': r['leather'], 'wood_dark': r['leather_dark'], 'wrap': r['cloth_warm'], 'metal': r['metal_light'],
                    'metal_dark': r['metal_dark'], 'accent': r['cloth_accent'], 'burr': r['leather'], 'burr_tip': r['glow']})
        return out

    def inline(self):
        """{pack_id: {'pack': ..., 'combat_roles': ...}} for a build job (empty for a vendored legacy pack)."""
        if self.kind == 'legacy_pack':
            return {}
        return {self.pack_id: {'pack': self.pack(), 'combat_roles': self.combat_roles()}}

    def receipt(self):
        return {'lock': self.id, 'kind': self.kind, 'lock_sha256': self.digest(), 'palette_sha256': self.palette_digest(),
                'pack_id': self.pack_id, 'profile': (self.source.get('profile') or {}).get('id'),
                'profile_closure_sha256': self.profile_closure_sha256, 'chain': self.chain}


def _merge(parent, child):
    out = copy.deepcopy(parent)
    for k, v in child.items():
        if k in ('extends', 'id', 'description', 'source', 'schema_version'):
            out[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and k in ('roles', 'defaults'):
            out[k].update(copy.deepcopy(v))
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_lock(lock_id, root=ROOT):
    """Resolve a lock and its `extends` chain (max depth 4). Raises CharacterStyleError."""
    root = Path(root)
    schema = _read_json(ROOT, SCHEMA)
    chain, docs, cur = [], [], lock_id
    while cur is not None:
        _req(len(chain) < 4 and cur not in chain, 'LOCK', 'lock inheritance cycle or depth at ' + str(cur))
        _req(isinstance(cur, str) and SP.re.fullmatch(r'[a-z][a-z0-9_]{0,63}', cur) is not None, 'LOCK', 'bad lock id')
        doc = _read_json(root, '%s/%s.json' % (LOCK_DIR, cur))
        try:
            SP.validate_schema(doc, schema)
        except SP.StyleError as exc:
            raise CharacterStyleError('SCHEMA', '%s: %s' % (cur, exc)) from exc
        _req(doc['id'] == cur, 'LOCK', 'lock file %s declares id %s' % (cur, doc['id']))
        chain.append(cur); docs.append(doc)
        cur = doc.get('extends')
    merged = {}
    for doc in reversed(docs):
        merged = _merge(merged, doc) if merged else copy.deepcopy(doc)
    for key in ('roles', 'proportions', 'budgets', 'face', 'texture', 'bodies', 'defaults'):
        _req(key in merged, 'LOCK', 'lock %s (with parents) lacks %s' % (lock_id, key))
    if merged['source']['kind'] == 'profile':
        _req('palette' in merged and 'profile' in merged['source'], 'LOCK', 'profile lock needs palette + source.profile')
    else:
        _req('pack' in merged['source'], 'LOCK', 'legacy lock needs source.pack')
    return Lock(merged, chain, root)


def list_locks(root=ROOT):
    d = Path(root) / LOCK_DIR
    return sorted(p.stem for p in d.glob('*.json'))


def lock_for_pack(pack_id):
    return {'polar_pod': 'pack_polar_pod', 'forest_village': 'pack_forest_village'}.get(pack_id)
