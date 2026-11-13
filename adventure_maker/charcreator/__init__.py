"""Character creator (lane CHARCREATOR): original characters in the measured low-poly card shape and art style.

A creator recipe (schema 'hermes64-creator-recipe/1') is plain parameters: species, build, proportions, face style,
modules (hair / beard / hat / cape / backpack / belt / boots / gloves / glasses / ears / tail / horns / muzzle), base
colours from a named indexed palette, a seed. Everything else is derived deterministically by the builder:

    compile(recipe)        stdlib: validate + clamp against the card and the rig contract -> (params, report)
    propose(brief, n=3)    stdlib: plain words -> creator recipes (adventure_maker/charcreator/propose.py)
    apply_edit(recipe, e)  stdlib: the hermes64_character typed edits mapped onto creator parameters
    build(...)             numpy:  mesh + 64x64 baked atlas + human16_v1 clips -> GLB (adventure_maker/charcreator/build.py)

Data: characters/creator/creator.json (card targets, builds, species, modules, palette). Measured card:
docs/charstyle/meshy_n64_card.json (generic ranges; tests keep the copy in creator.json equal to it).
The plugin imports this package without numpy; only build/render/measure need numpy (and Pillow for PNGs).
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'characters' / 'creator' / 'creator.json'
STYLE_ID = 'creator64'
BODY_ID = 'body.creator'
SCHEMA = 'hermes64-creator-recipe/1'
RIG = {'id': 'human16_v1', 'version': '1.0.0'}
_CACHE = {}


class CreatorError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _req(cond, code, message):
    if not cond:
        raise CreatorError(code, message)


def data():
    if 'data' not in _CACHE:
        _CACHE['data'] = json.loads(DATA.read_text(encoding='utf-8'))
    return _CACHE['data']


LEVELS = (.42, .7, 1.0)              # shade multipliers of a base colour (linear light) + one highlight level
HILITE = .45                         # highlight = the base colour mixed this far toward white


def _lin(c):
    return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4


def _srgb(c):
    c = min(max(c, 0.), 1.)
    return 12.92 * c if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055


def ramp(hexcol):
    """4 sRGB byte colours (dark, mid-dark, base, highlight) of one palette colour (stdlib)."""
    base = [_lin(int(hexcol[i:i + 2], 16) / 255.) for i in (1, 3, 5)]
    out = [[c * m for c in base] for m in LEVELS] + [[c + (1. - c) * HILITE for c in base]]
    return [tuple(int(round(_srgb(c) * 255)) for c in col) for col in out]


def master_palette():
    """Every colour a creator atlas may hold (the palette gate's list): all ramps of all palette colours + white
    (vertex colours stay white: texture-only colour, as the card measured)."""
    hexes = {'#ffffff'}
    for row in data()['palette'].values():
        for c in ramp(row['hex']):
            hexes.add('#%02x%02x%02x' % c)
    return sorted(hexes)


def is_creator(recipe):
    return isinstance(recipe, dict) and (recipe.get('schema') == SCHEMA or recipe.get('body') == BODY_ID)


def digest(recipe):
    return hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _clamp(v, lo, hi, label, clamps):
    if v < lo or v > hi:
        nv = min(max(v, lo), hi)
        clamps.append({'field': label, 'asked': round(v, 4), 'used': round(nv, 4), 'range': [lo, hi]})
        return nv
    return v


def module_ids(kind=None):
    d = data()['modules']
    return sorted(k for k, v in d.items() if kind is None or v['kind'] == kind)


def palette_names():
    return sorted(data()['palette'])


def resolve_colour(word):
    """A colour word or palette name -> palette name, or None."""
    d = data()
    w = str(word).lower().strip().replace(' ', '_')
    if w in d['palette']:
        return w
    return d['colour_words'].get(w)


def new_recipe(rid, species='human', build='average', seed=19, display='Creator character'):
    d = data()
    sp = d['species'][species]
    rec = {'schema': SCHEMA, 'id': rid, 'body': BODY_ID, 'archetype': 'person', 'role': 'npc', 'rig': dict(RIG),
           'species': species, 'build': build, 'tune': {}, 'face': dict(sp.get('face', {'style': 'dot', 'mouth': 'line'})),
           'modules': list(sp.get('modules', [])), 'module_scale': {}, 'colours': dict(d['default_colours']),
           'seed': int(seed), 'name': {'display': display, 'placeholder': True}, 'notes': []}
    rec['colours'].update(sp.get('colours', {}))
    return rec


def compile(recipe):
    """-> (params, report). Raises CreatorError with a code (SCHEMA, UNKNOWN_PART, PART_BODY, BUDGET, RANGE, ROLE)."""
    d = data()
    _req(isinstance(recipe, dict) and recipe.get('schema') == SCHEMA, 'SCHEMA', 'not a creator recipe (schema %s)' % SCHEMA)
    for key in ('id', 'species', 'build', 'face', 'modules', 'colours', 'seed'):
        _req(key in recipe, 'SCHEMA', 'creator recipe lacks ' + key)
    _req(recipe.get('rig', RIG) == RIG, 'RIG', 'the creator builds on %s@%s' % (RIG['id'], RIG['version']))
    _req(recipe['species'] in d['species'], 'UNKNOWN_PART', 'unknown species %r (have %s)' % (recipe['species'], sorted(d['species'])))
    _req(recipe['build'] in d['builds'], 'UNKNOWN_PART', 'unknown build %r (have %s)' % (recipe['build'], sorted(d['builds'])))
    clamps, notes = [], []
    sp, bd = d['species'][recipe['species']], d['builds'][recipe['build']]
    # modules first (one per kind; a hat that covers the hair drops it), then the proportions they change
    mods = []
    kinds = {}
    for mid in recipe['modules']:
        _req(mid in d['modules'], 'UNKNOWN_PART', 'unknown module %r (list what=parts style=creator64)' % mid)
        m = d['modules'][mid]
        if m['kind'] in kinds:
            notes.append('%s replaces %s (one %s)' % (mid, kinds[m['kind']], m['kind']))
            mods = [x for x in mods if x != kinds[m['kind']]]
        kinds[m['kind']] = mid
        mods.append(mid)
    for mid in list(mods):
        for other in d['modules'][mid].get('excludes', []):
            if other in kinds and kinds[other] in mods and other != d['modules'][mid]['kind']:
                notes.append('%s hides %s (not built)' % (mid, kinds[other]))
                mods.remove(kinds[other])
    # proportions: card defaults x build x species x modules, then the recipe's tune, then clamps (fractions of height)
    p = dict(d['body_defaults'])
    for src in [bd.get('body', {}), sp.get('body', {})] + [d['modules'][m].get('body', {}) for m in mods]:
        for k, v in src.items():
            _req(k in p, 'SCHEMA', 'unknown body field %s' % k)
            p[k] = p[k] * v if k in d['multiplicative'] else v
    tune_map = {'head_scale': ('head_h', 'head_w', 'head_d'), 'shoulder_scale': ('shoulder_x', 'chest_w'),
                'waist_scale': ('waist_w', 'hip_d'), 'bulk': ('thigh_r', 'knee_r', 'calf_r', 'upper_arm_r', 'elbow_r', 'forearm_r')}
    for k, v in sorted((recipe.get('tune') or {}).items()):
        _req(k in d['tune_ranges'], 'SCHEMA', 'unknown tune field %s (have %s)' % (k, sorted(d['tune_ranges'])))
        lo, hi = d['tune_ranges'][k]
        v = _clamp(float(v), lo, hi, 'tune.' + k, clamps)
        if k == 'height_m':
            p['height_m'] = v
        elif k == 'leg_scale':
            p['torso_upper'] = p['torso_upper'] / v            # longer legs = the torso gives up the length
        else:
            for f in tune_map[k]:
                p[f] = p[f] * v
    lo, hi = d['height_m']
    p['height_m'] = _clamp(float(p['height_m']), lo, hi, 'height_m', clamps)
    for k, (lo, hi) in d['body_ranges'].items():
        p[k] = _clamp(float(p[k]), lo, hi, k, clamps)
    scale = {}
    for mid, v in sorted((recipe.get('module_scale') or {}).items()):
        _req(mid in mods, 'PART_BODY', 'module_scale for %s, which the recipe does not wear' % mid)
        scale[mid] = _clamp(float(v), .5, 2., 'module_scale.' + mid, clamps)
    # colours: every slot a palette name
    cols = dict(d['default_colours'])
    for slot, name in recipe['colours'].items():
        _req(slot in d['slots'], 'SLOT', 'unknown colour slot %r (have %s)' % (slot, sorted(d['slots'])))
        r = resolve_colour(name)
        _req(r is not None, 'ROLE', 'unknown colour %r for %s (palette: %s)' % (name, slot, ', '.join(palette_names())))
        allowed = d['slots'][slot]
        if allowed != 'any' and d['palette'][r]['family'] not in allowed:
            raise CreatorError('ROLE', '%s cannot be %s (a %s colour; %s takes %s)' % (slot, r, d['palette'][r]['family'], slot,
                                                                                       '/'.join(allowed)))
        cols[slot] = r
    used = sorted({cols[s] for s in cols if _slot_used(s, mods, recipe)})
    _req(len(used) <= d['card']['base_colours_max'], 'BUDGET', '%d base colours, the card allows %d' % (len(used), d['card']['base_colours_max']))
    face = dict(sp.get('face', {}))
    face.update(recipe.get('face') or {})
    _req(face.get('style', 'dot') in d['face_styles'], 'UNKNOWN_PART', 'unknown face style %r (have %s)' % (face.get('style'), sorted(d['face_styles'])))
    _req(face.get('mouth', 'line') in d['mouths'], 'UNKNOWN_PART', 'unknown mouth %r (have %s)' % (face.get('mouth'), sorted(d['mouths'])))
    tris_body = d['base_tris'] + sum(d['modules'][m]['tris'] for m in mods if d['modules'][m]['place'] == 'body')
    props = {m: d['modules'][m]['tris'] for m in mods if d['modules'][m]['place'] == 'prop'}
    _req(tris_body < d['card']['body_tris_lt'], 'BUDGET', 'body %d tris with %s; the rig budget is < %d (drop a module)' % (
        tris_body, ', '.join(mods) or 'no modules', d['card']['body_tris_lt']))
    for m, t in props.items():
        _req(t <= d['card']['prop_tris_le'], 'BUDGET', 'prop %s %d tris > %d' % (m, t, d['card']['prop_tris_le']))
    params = {'id': recipe['id'], 'seed': int(recipe['seed']), 'species': recipe['species'], 'build': recipe['build'],
              'body': p, 'modules': mods, 'module_scale': scale, 'colours': cols, 'base_colours': used, 'face': face,
              'skin_kind': sp.get('skin_kind', 'skin')}
    rep = {'clamps': clamps, 'notes': notes + list(recipe.get('notes') or []), 'tris': {'body': tris_body, 'props': props},
           'base_colours': len(used), 'recipe_sha256': digest(recipe), 'rig': '%s@%s' % (RIG['id'], RIG['version']),
           'clips': list(d['clips']), 'hover': False, 'lock': STYLE_ID}
    return params, rep


def _slot_used(slot, mods, recipe):
    d = data()
    need = d['slot_needs'].get(slot)
    if need is None:
        return True
    return any(d['modules'][m]['kind'] in need or m in need for m in mods)


def summary(recipe):
    bits = [recipe.get('species', '?'), recipe.get('build', '?')]
    mods = recipe.get('modules') or []
    if mods:
        bits.append('wears ' + ', '.join(m.split('.', 1)[1].replace('_', ' ') + ' ' + m.split('.', 1)[0] for m in mods))
    cols = recipe.get('colours') or {}
    if cols:
        bits.append('colours ' + ', '.join('%s %s' % (k, v) for k, v in sorted(cols.items())))
    return '; '.join(bits)


EDIT_KINDS = ('height', 'build', 'hair', 'color', 'swap', 'face', 'prop', 'name')


def apply_edit(recipe, edit):
    """The hermes64_character typed edits on a creator recipe (same kinds and fields as the house bodies)."""
    d = data()
    rec = copy.deepcopy(recipe)
    k = edit['kind']
    tune = rec.setdefault('tune', {})
    if k == 'height':
        _req('value' in edit, 'SCHEMA', 'height needs value (metres)')
        tune['height_m'] = float(edit['value'])
    elif k == 'build':
        for f, key in (('head', 'head_scale'), ('shoulders', 'shoulder_scale'), ('waist', 'waist_scale'), ('legs', 'leg_scale')):
            if f in edit:
                tune[key] = float(edit[f])
        if 'age' in edit:
            rec['build'] = {'child': 'child', 'teen': 'lean', 'adult': rec['build'] if rec['build'] != 'child' else 'average',
                            'elder': rec['build'] if rec['build'] != 'child' else 'average'}[edit['age']]
            if edit['age'] == 'elder':
                rec['colours']['hair'] = 'grey'
    elif k == 'hair':
        if 'style' in edit:
            sid = edit['style'] if edit['style'].startswith('hair.') else 'hair.' + edit['style']
            _req(sid in d['modules'], 'UNKNOWN_PART', 'unknown hair style %r (have %s)' % (edit['style'], ', '.join(module_ids('hair'))))
            rec['modules'] = [m for m in rec['modules'] if d['modules'][m]['kind'] != 'hair'] + [sid]
        if 'color' in edit:
            rec['colours']['hair'] = edit['color']
    elif k == 'color':
        _req('slot' in edit and 'role' in edit, 'SCHEMA', 'color needs slot and role (a palette colour name or colour word)')
        rec['colours'][edit['slot']] = edit['role']
    elif k == 'swap':
        _req('part' in edit, 'SCHEMA', 'swap needs part')
        pid = edit['part']
        _req(pid in d['modules'], 'UNKNOWN_PART', 'unknown module %r' % pid)
        kind = d['modules'][pid]['kind']
        if pid not in rec['modules']:            # the same part keeps its place: only its size moves
            rec['modules'] = [m for m in rec['modules'] if d['modules'][m]['kind'] != kind] + [pid]
        if 'value' in edit:                      # 'make the hat taller': swap the same part with a size value
            rec.setdefault('module_scale', {})[pid] = float(edit['value'])
    elif k == 'face':
        f = rec.setdefault('face', {})
        if 'preset' in edit:
            f['style'] = edit['preset'].split('.', 1)[1]
        if 'expression' in edit:
            f['mouth'] = d['expression_mouth'].get(edit['expression'], 'line')
        if 'eyes' in edit:
            rec['colours']['eyes'] = edit['eyes']
        if 'beard' in edit:
            rec['modules'] = [m for m in rec['modules'] if d['modules'][m]['kind'] != 'beard']
            if edit['beard'] != 'beard.none':
                _req(edit['beard'] in d['modules'], 'UNKNOWN_PART', 'unknown beard %r (have %s)' % (edit['beard'], ', '.join(module_ids('beard'))))
                rec['modules'].append(edit['beard'])
    elif k == 'prop':
        rec['modules'] = [m for m in rec['modules'] if d['modules'][m]['kind'] != 'held']
        if edit.get('part'):
            _req(edit['part'] in d['modules'] and d['modules'][edit['part']]['kind'] == 'held', 'UNKNOWN_PART',
                 'unknown held prop %r (have %s)' % (edit['part'], ', '.join(module_ids('held'))))
            rec['modules'].append(edit['part'])
    elif k == 'name':
        rec['name'] = {'display': edit.get('display', rec['name']['display']), 'placeholder': bool(edit.get('placeholder', False))}
    else:
        raise CreatorError('SCHEMA', 'unknown edit kind ' + str(k))
    compile(rec)
    return rec
