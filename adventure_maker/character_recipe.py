"""Character recipes (contracts/character/1.0.0): validate, clamp, compile to a generator build item.

    rec = json.loads(text)
    lock = character_style.load_lock('pack_polar_pod')
    item, report = compile_build(rec, lock)          # item -> characters/gen/build.py job; report -> clamps etc.

Refusals raise RecipeError(code, message) - one line each:
  SCHEMA        recipe JSON outside the contract
  UNKNOWN_PART  part id not in characters/library/parts.json
  PART_BODY     part exists but does not fit this body
  SLOT          two parts claim one slot (two tops, hair under a beanie, ...)
  ROLE          palette role unknown, or a role from the wrong family for the slot (skin painted 'cloth_accent')
  RANGE         a value outside the GENERATOR's declared range (values merely outside the LOCK's range are clamped)
  BUDGET        body + parts + attachments over the lock budget
  RIG           recipe rig differs from the body's registered rig contract
  LOCK          body or part not admitted by the style lock
  STANCE / TUNE / BOSS / CLIPS  invalid stance, tuning key, boss block, clip set
Clamps never fail: each is reported as one line "height 2.10 -> 1.92: above the adult range of lock pack_polar_pod".
Pure stdlib; imports only the generator's pure-Python parameter tables (no Blender, no numpy).
"""
import copy
import hashlib
import importlib
import json
import math
import sys
import types
from pathlib import Path

from . import style_profile as SP
from . import character_style as CS

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'characters' / 'gen'
SCHEMA = 'contracts/character/1.0.0.json'
PARTS = 'characters/library/parts.json'
SEED_DEFAULT = 19
SINGLE_KINDS = ('hair', 'hat', 'top', 'sleeves', 'legs', 'boots', 'hands', 'collar', 'cape', 'pattern', 'beard', 'rhead',
                'rhand', 'rfoot', 'coat', 'species', 'crown', 'emblem', 'visor', 'face')
COLOR_KEYS_PERSON = {'skin': 'skin', 'hair': 'hair_color', 'eyes': 'eye_color', 'top': 'top_color', 'garment': 'garment_color',
                     'trim': 'trim_color', 'accent': 'accent_color', 'legs': 'bottom_color', 'boots': 'boot_color',
                     'gloves': 'glove_color', 'belt': 'belt_color', 'collar': 'collar_color', 'extra': 'extra_color',
                     'extra2': 'extra_color_2', 'hat': None}
COLOR_KEYS_MASKED = {'skin': 'skin', 'hood': 'headwear_color', 'top': 'top_color', 'vest': 'vest_color',
                     'trim': 'vest_trim_color', 'cape': 'mantle_color', 'skirt': 'skirt_color', 'legs': 'bottom_color',
                     'gloves': 'glove_color', 'boots': 'boot_color', 'belt': 'belt_color', 'armband': 'armband_color'}
COLOR_KEYS_ROBOT = {'shell': 'shell', 'shell_light': 'shell_light', 'shell_alt': 'shell_alt', 'dark': 'shell_dark',
                    'joint': 'joint', 'lens': 'lens', 'visor': 'visor', 'accent': 'warning', 'emblem': 'emblem'}
COLOR_KEYS_ANIMAL = {'coat': 'coat_color_1', 'coat2': 'coat_color_2', 'coat3': 'coat_color_3', 'eyes': 'eye_color'}
SLOT_FAMILY_KEY = {'accent': 'accent'}           # robot 'accent' uses the accent_robot family (below)
DEFAULT_PARTS = {
    'body.person': ['top.sweater', 'legs.trousers', 'boots.boots', 'hands.bare'],
    'body.person_masked': ['hood.cowl', 'vest.quilted_wave', 'legs.trousers', 'boots.heavy', 'hands.gloves', 'cape.capelet'],
}
FAMILY_BODY = {'walker': 'body.robot_walker', 'brute': 'body.robot_brute', 'floater': 'body.robot_floater'}
# Largest head the vendored face-head generator keeps closed at the neck (3 mm) on every key, measured with its own
# join table over 16 keys of every clip (docs/CHARSYS-RESULT.md): base clips / combat clips (None = not supported).
FACE_HEAD_MAX = {'base': {'child': 1.05, 'teen': 1.2, 'adult': 1.2, 'elder': 1.2},
                 'combat': {'child': None, 'teen': .9, 'adult': 1.1, 'elder': 1.15}}
RIG_HEIGHT = {'human16_v1': 2.314, 'quad16_v1': .655}     # rig contract proportions.height_m upper bounds


class RecipeError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ': ' + message)


def _req(cond, code, message):
    if not cond:
        raise RecipeError(code, message)


_CACHE = {}


GEN_PACKAGE = '_hermes64_chargen'


def gen_module(dotted):
    """A module of the vendored generator ('core.people', 'ext.robots') under a private package name, without
    touching sys.path: the plugin process must never see a top-level 'core' (kits/core is another package)."""
    if GEN_PACKAGE not in sys.modules:
        pkg = types.ModuleType(GEN_PACKAGE)
        pkg.__path__ = [str(GEN)]
        pkg.__package__ = GEN_PACKAGE
        sys.modules[GEN_PACKAGE] = pkg
    return importlib.import_module('%s.%s' % (GEN_PACKAGE, dotted))


def _gen_modules():
    """The generator's pure-Python parameter tables (people / geometry / pose / robots) - no Blender."""
    if 'gen' not in _CACHE:
        _CACHE['gen'] = tuple(gen_module(m) for m in ('core.people', 'core.geometry', 'core.pose', 'ext.robots'))
    return _CACHE['gen']


def load_parts(root=ROOT):
    key = ('parts', str(root))
    if key not in _CACHE:
        _CACHE[key] = SP.parse_json(SP.read_confined(Path(root), PARTS))
    return _CACHE[key]


def recipe_digest(recipe):
    return hashlib.sha256(SP.canonical_bytes(recipe)).hexdigest()


def validate_schema(recipe):
    try:
        SP.canonical_bytes(recipe)
        SP.validate_schema(recipe, SP.parse_json(SP.read_confined(ROOT, SCHEMA)))
    except SP.StyleError as exc:
        raise RecipeError('SCHEMA', str(exc)) from exc


def _clamp(value, lo, hi, label, reason, clamps):
    if value < lo - 1e-9:
        clamps.append('%s %.3g -> %.3g: below %s (%.3g-%.3g)' % (label, value, lo, reason, lo, hi))
        return lo
    if value > hi + 1e-9:
        clamps.append('%s %.3g -> %.3g: above %s (%.3g-%.3g)' % (label, value, hi, reason, lo, hi))
        return hi
    return value


def _hard(value, lo, hi, label):
    _req(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and lo <= value <= hi,
         'RANGE', '%s %r outside the generator range %.3g-%.3g' % (label, value, lo, hi))


def _role(lock, slot, role, family_slot=None):
    fam_slot = family_slot or slot
    _req(role in CS.ROLES, 'ROLE', 'unknown palette role %r for %s' % (role, slot))
    allowed = CS.SLOT_FAMILIES.get(fam_slot)
    _req(allowed is not None, 'ROLE', 'unknown colour slot %r' % slot)
    _req(CS.FAMILY_OF[role] in allowed, 'ROLE', '%s cannot take role %r (family %s; allowed %s)' % (
        slot, role, CS.FAMILY_OF[role], '/'.join(allowed)))
    return lock.resolve(role)


def _parts_for(recipe, parts, body_id):
    """-> ({kind: [part ids]}, part rows). Refuses unknown parts, wrong bodies and slot conflicts."""
    ids = list(recipe.get('outfit', []))
    hair = recipe.get('hair') or {}
    face = recipe.get('face') or {}
    for extra in (hair.get('style'), face.get('preset'), face.get('beard'), face.get('visor'), recipe.get('prop')):
        if extra:
            ids.append(extra)
    boss = recipe.get('boss') or {}
    for extra in (boss.get('crown'), boss.get('emblem')):
        if extra:
            ids.append(extra)
    by_kind = {}
    rows = {}
    for pid in ids:
        row = parts['parts'].get(pid)
        _req(row is not None, 'UNKNOWN_PART', 'unknown part id %r' % pid)
        _req(body_id in row['bodies'], 'PART_BODY', '%s does not fit %s' % (pid, body_id))
        by_kind.setdefault(row['kind'], []).append(pid)
        rows[pid] = row
    _req(len(ids) == len(set(ids)), 'SLOT', 'part listed twice')
    for kind, lst in by_kind.items():
        if kind in SINGLE_KINDS or kind == 'prop':
            _req(len(lst) == 1, 'SLOT', 'two %s parts: %s' % (kind, ', '.join(lst)))
    groups = {}
    for pid, row in rows.items():
        if row.get('group'):
            _req(row['group'] not in groups, 'SLOT', 'two %s accessories: %s, %s' % (row['group'], groups.get(row['group']), pid))
            groups[row['group']] = pid
        for ex in row.get('excludes', []):
            _req(ex not in by_kind, 'SLOT', '%s excludes a %s part (%s)' % (pid, ex, ', '.join(by_kind.get(ex, []))))
        if row.get('requires_any'):
            _req(any(r in rows for r in row['requires_any']), 'SLOT', '%s needs one of %s' % (pid, ', '.join(row['requires_any'])))
    belts = [p for p in rows if p in ('acc.belt', 'acc.no_belt')]
    _req(len(belts) <= 1, 'SLOT', 'belt and no_belt together')
    return by_kind, rows


def _defaults_into(recipe, body_id, parts):
    """Fill missing single-slot parts with the body's defaults (never overrides a choice)."""
    rec = copy.deepcopy(recipe)
    have = set()
    for pid in rec.get('outfit', []):
        row = parts['parts'].get(pid)
        if row:
            have.add(row['kind'])
            have.update(row.get('excludes', []))
    add = []
    for pid in DEFAULT_PARTS.get(body_id, []):
        row = parts['parts'][pid]
        if row['kind'] not in have:
            add.append(pid)
            have.add(row['kind'])
    rec['outfit'] = list(rec.get('outfit', [])) + add
    return rec


def _check_tune(tune, allowed, hard, label, clamps, lock):
    out = {}
    for k, v in sorted(tune.items()):
        _req(k in allowed, 'TUNE', '%s cannot tune %r' % (label, k))
        if k in hard:
            lo, hi = hard[k]
            _hard(v, lo, hi, 'tune.' + k)
            if k == 'wear':
                v = _clamp(v, lock.texture['wear'][0], lock.texture['wear'][1], 'tune.wear', 'the texture wear range of lock ' + lock.id, clamps)
        out[k] = v
    return out


def compile_build(recipe, lock, out=None, render=None):
    """Validate + clamp + compile one recipe. -> (build item, report). Raises RecipeError."""
    validate_schema(recipe)
    _req('legacy' not in recipe, 'SCHEMA', 'legacy cast rows compile with compile_cast_recipe')
    parts = load_parts()
    people, geometry, pose, robots = _gen_modules()
    body_id = recipe['body']
    body = parts['bodies'].get(body_id)
    _req(body is not None, 'UNKNOWN_PART', 'unknown body %r' % body_id)
    _req(body['archetype'] == recipe['archetype'], 'SCHEMA', '%s is a %s body, recipe says %s' % (body_id, body['archetype'], recipe['archetype']))
    _req(recipe['rig'] == body['rig'], 'RIG', '%s is registered on rig %s@%s, recipe says %s@%s' % (
        body_id, body['rig']['id'], body['rig']['version'], recipe['rig']['id'], recipe['rig']['version']))
    _req(body_id in lock.bodies, 'LOCK', 'lock %s does not admit %s' % (lock.id, body_id))
    rec = _defaults_into(recipe, body_id, parts)
    by_kind, rows = _parts_for(rec, parts, body_id)
    denied = [p for p in rows if p in lock.parts_denied]
    _req(not denied, 'LOCK', 'lock %s denies %s' % (lock.id, ', '.join(denied)))
    clamps, warnings = [], []
    b = rec.get('build') or {}
    colors = dict(rec.get('colors') or {})
    family = body['family']
    seed = int(rec.get('seed', SEED_DEFAULT))
    rid = rec['id']
    item = {'id': rid, 'pack_id': lock.pack_id, 'out': out or ('%s.glb' % rid)}
    if render is not None:
        item['render'] = render
    tris = {'body': body['tris'], 'attachments': 0}
    clip_set = rec.get('clips')
    prop_row = rows.get(rec['prop']) if rec.get('prop') else None
    if rec['role'] == 'boss':
        _req(rec['archetype'] in ('robot', 'creature'), 'BOSS', 'a boss is a robot or creature body')
    else:
        _req('boss' not in rec, 'BOSS', 'boss block on a %s' % rec['role'])

    if family in ('face', 'masked'):
        P = people.DEFAULTS if family == 'face' else geometry.HUMAN_DEFAULTS
        if family == 'face':
            hard = dict(people.RANGES)
            p = {'head_mode': 'face'}
            age = b.get('age', 'adult')
            p['age'] = age
            hrange = lock.proportions['height'][age]
        else:
            hard = {'height': (1.25, 2.05), 'build': (.8, 1.25), 'head_size': (.85, 1.2), 'trouser_volume': (.85, 1.4),
                    'wear': (0, 1), 'mantle': (0, 1), 'skirt': (0, 1), 'hood_tilt': (-1, 1)}
            p = {'head_mode': 'faceless', 'headwear': 'hood'}
            _req(b.get('age', 'adult') == 'adult', 'RANGE', 'masked residents are adults (age %r)' % b.get('age'))
            hrange = lock.proportions['height']['masked']
            age = 'masked'
        height = b.get('height', round((hrange[0] + hrange[1]) / 2., 3))
        _hard(height, hard['height'][0], hard['height'][1], 'height')
        p['height'] = _clamp(height, hrange[0], hrange[1], 'height', 'the %s height range of lock %s' % (age, lock.id), clamps)
        for key, gk, lk in (('head', 'head_size', 'head'), ('shoulders', 'build', 'shoulders')):
            if key in b:
                _hard(b[key], hard[gk][0], hard[gk][1], key)
                p[gk] = _clamp(b[key], lock.proportions[lk][0], lock.proportions[lk][1], key, 'the %s range of lock %s' % (lk, lock.id), clamps)
        if 'waist' in b:
            if family == 'face':
                _hard(b['waist'], 0, 1, 'waist')
                p['belly'] = _clamp(b['waist'], lock.proportions['waist'][0], lock.proportions['waist'][1], 'waist', 'the waist range of lock ' + lock.id, clamps)
            else:
                warnings.append('waist ignored: the masked body has a fixed vest waist')
        # parts -> generator parameters (parts.json params are the generator's own enum values)
        for pid, row in sorted(rows.items()):
            if row['kind'] in ('prop', 'face'):
                continue
            for k, v in row.get('params', {}).items():
                p[k] = v
        if 'legs' in b:
            _hard(b['legs'], hard['trouser_volume'][0], hard['trouser_volume'][1], 'legs')
            p['trouser_volume'] = _clamp(b['legs'], lock.proportions['legs'][0], lock.proportions['legs'][1], 'legs', 'the legs range of lock ' + lock.id, clamps)
        elif 'trouser_volume' in p:
            p['trouser_volume'] = _clamp(p['trouser_volume'], max(lock.proportions['legs'][0], hard['trouser_volume'][0]),
                                         min(lock.proportions['legs'][1], hard['trouser_volume'][1]), 'legs part', 'the legs range of lock ' + lock.id, clamps)
        if family == 'face':
            face = rec.get('face') or {}
            preset = rows.get(face.get('preset')) if face.get('preset') else None
            if preset:
                for k, v in preset['params'].items():
                    p[k] = v
            elif face.get('preset') is None:
                for k, v in parts['parts']['face.calm']['params'].items():
                    p[k] = v
            expr = face.get('expression', 'neutral')
            _req(expr in lock.face['expressions'], 'LOCK', 'expression %s not admitted by lock %s' % (expr, lock.id))
            p['expression'] = people.EXPRESSIONS.index(expr)
            _req('painted_atlas' in lock.face['styles'], 'LOCK', 'lock %s admits no painted faces' % lock.id)
            if face.get('preset'):
                _req(face['preset'] in lock.face['presets'], 'LOCK', 'face %s not admitted by lock %s' % (face['preset'], lock.id))
            hair = rec.get('hair') or {}
            if 'hat.beanie' not in rows and not hair.get('style'):
                p['hair'] = 'crop'
            colors.setdefault('skin', rec.get('skin') or lock.defaults['skin'])
            if rec.get('skin'):
                colors['skin'] = rec['skin']
            if hair.get('color'):
                colors['hair'] = hair['color']
            if face.get('eyes'):
                colors['eyes'] = face['eyes']
            keymap = COLOR_KEYS_PERSON
        else:
            _req('faceless' in lock.face['styles'], 'LOCK', 'lock %s admits no masked residents' % lock.id)
            colors.setdefault('skin', rec.get('skin') or 'skin_light')
            if rec.get('skin'):
                colors['skin'] = rec['skin']
            _req(not rec.get('hair') and not (rec.get('face') or {}).get('preset'), 'PART_BODY', 'masked residents have no hair or face')
            keymap = COLOR_KEYS_MASKED
        for slot in keymap:
            if keymap[slot] and lock.defaults.get(slot):
                colors.setdefault(slot, lock.defaults[slot])
        for slot, role in sorted(colors.items()):
            _req(slot in keymap, 'ROLE', '%s body has no colour slot %r (slots: %s)' % (family, slot, ', '.join(sorted(keymap))))
            if keymap[slot]:
                p[keymap[slot]] = _role(lock, slot, role)
        if family == 'face':
            p['brow_color'] = p['hair_color']
            if p.get('hair') == 'beanie':
                # the knit cap takes the generator's hair colour; the real hair colour stays on the brows
                p['hair_color'] = _role(lock, 'hat', colors.get('hat') or lock.defaults['top'])
            else:
                _req('hat' not in colors, 'ROLE', 'colour slot hat needs hat.beanie')
            p['lip_color'] = lock.resolve('lip')
        if family == 'face':
            combat = bool(prop_row and prop_row.get('weapon')) or rec.get('clips') == 'human_combat'
            lim = FACE_HEAD_MAX['combat' if combat else 'base'][age]
            _req(lim is not None, 'CLIPS', 'combat clips (the staff) need a teen, adult or elder body: a child neck opens in rolls')
            hs = p.get('head_size', people.DEFAULTS['head_size'])
            if hs > lim:
                clamps.append('head %.3g -> %.3g: largest %s head kept closed at the neck in every %s clip' % (
                    hs, lim, age, 'combat' if combat else 'base'))
                p['head_size'] = lim
        tune_allowed = {k for k in P if k not in (people.COLOR_KEYS if family == 'face' else geometry.COLORS)} - {'head_mode', 'height'}
        p.update(_check_tune(rec.get('tune') or {}, tune_allowed, hard, family + ' body', clamps, lock))
        if 'wear' not in (rec.get('tune') or {}):
            p['wear'] = _clamp(.3, lock.texture['wear'][0], lock.texture['wear'][1], 'wear', 'the texture wear range of lock ' + lock.id, clamps)
        # the generator's own resolver is the last word on every value
        try:
            (people.resolve if family == 'face' else (lambda v: geometry.resolve(v, geometry.HUMAN_DEFAULTS)))(p)
        except ValueError as exc:
            raise RecipeError('RANGE', 'generator refused: %s' % exc) from exc
        stance = rec.get('stance')
        props = []
        weapon = False
        if prop_row:
            if prop_row.get('weapon'):
                weapon = True
                clip_set = clip_set or 'human_combat'
                _req(clip_set == 'human_combat', 'CLIPS', 'the staff rides the combat clips (clips must be human_combat)')
            else:
                props = [prop_row['prop']]
                stance = stance or prop_row.get('stance')
            tris['attachments'] += prop_row['tris']
        stance = stance or 'neutral'
        _req(stance in pose.STANCES, 'STANCE', 'unknown stance %r' % stance)
        clip_set = clip_set or 'human_base'
        _req(clip_set in body['clip_sets'], 'CLIPS', '%s cannot play clip set %s' % (body_id, clip_set))
        item.update(kind='person' if family == 'face' else 'masked', params=p, stance=stance, props=props, seed=seed,
                    clips=list(parts['clip_sets'][clip_set]), weapon=weapon)
        if prop_row:
            _req(prop_row['tris'] <= lock.budgets['prop_le'], 'BUDGET', '%s %d tris > prop budget %d' % (rec['prop'], prop_row['tris'], lock.budgets['prop_le']))
        _req(body['tris'] < lock.budgets['humanoid_body_lt'], 'BUDGET', 'body over budget')
        effective = p
    elif rec['archetype'] == 'robot':
        rp = {'boss': rec['role'] == 'boss', 'extras': []}
        hard_h = robots.HEIGHT[family]
        lo, hi = lock.proportions['robot_height'][family]
        height = b.get('height', hard_h[2])
        if rec['role'] == 'boss':
            bs = (rec.get('boss') or {}).get('scale', 1.12)
            bs = _clamp(bs, lock.proportions['boss_scale'][0], lock.proportions['boss_scale'][1], 'boss.scale', 'the boss scale range of lock ' + lock.id, clamps)
            height = round(height * bs, 4)
        _hard(height, hard_h[0], hard_h[1] + .25, 'height')
        rp['height'] = _clamp(height, max(lo, hard_h[0]), min(hi, hard_h[1]), 'height', 'the %s height range of lock %s / rig %s' % (family, lock.id, body['rig']['id']), clamps)
        if 'shoulders' in b:
            blo, bhi = robots.BUILD[family]
            _hard(b['shoulders'], .5, 1.6, 'shoulders')
            rp['build'] = _clamp(b['shoulders'], blo, bhi, 'shoulders', 'the %s build range (rig %s proportions)' % (family, body['rig']['id']), clamps)
        if 'head' in b:
            _hard(b['head'], .6, 1.5, 'head')
            rp['head_size'] = _clamp(b['head'], max(.85, lock.proportions['head'][0]), min(1.2, lock.proportions['head'][1]), 'head', 'the head range of lock ' + lock.id, clamps)
        for pid, row in sorted(rows.items()):
            if row['kind'] in ('rhead', 'rhand', 'rfoot', 'visor'):
                for k, v in row['params'].items():
                    rp[k] = v
            elif row['kind'] == 'racc':
                rp['extras'] = sorted(set(rp['extras']) | set(row['params']['extras']))
        for k in ('waist', 'legs', 'age'):
            if k in b:
                warnings.append('%s ignored on a %s robot' % (k, family))
        wear = (rec.get('tune') or {}).get('wear', .25)
        _req(set((rec.get('tune') or {})) <= {'wear'}, 'TUNE', 'robots tune only wear')
        _hard(wear, 0, 1, 'tune.wear')
        rp['wear'] = _clamp(wear, lock.texture['wear'][0], lock.texture['wear'][1], 'wear', 'the texture wear range of lock ' + lock.id, clamps)
        roles = {}
        for slot in COLOR_KEYS_ROBOT:
            role = colors.get(slot) or lock.defaults.get(slot) or COLOR_KEYS_ROBOT[slot]
            roles[COLOR_KEYS_ROBOT[slot]] = _role(lock, slot, role, 'accent_robot' if slot == 'accent' else slot)
        unknown = [s for s in colors if s not in COLOR_KEYS_ROBOT]
        _req(not unknown, 'ROLE', 'robot body has no colour slot %s (slots: %s)' % (unknown, ', '.join(COLOR_KEYS_ROBOT)))
        _req(not rec.get('hair') and not rec.get('skin') and not (rec.get('face') or {}).get('preset'), 'PART_BODY', 'robots have no hair, skin or painted face')
        _req(not rec.get('prop'), 'PART_BODY', 'robots hold no props in this version')
        crown = bool((rec.get('boss') or {}).get('crown'))
        _req(not crown or rec['role'] == 'boss', 'BOSS', 'a crown is a boss part')
        if rec['role'] == 'boss':
            _req(crown, 'BOSS', 'a boss needs its crown slot (crown.points)')
        try:
            m = robots.build(family, {k: v for k, v in rp.items()})
            top = max(v[2] for v in m.vertices) + (.045 * rp['height'] if crown else 0.)     # crown points rise .04 H
            cap = RIG_HEIGHT[body['rig']['id']] - .01
            if top > cap:
                new_h = round(rp['height'] * cap / top, 4)
                clamps.append('height %.3g -> %.3g: antenna/crown keep the rest height inside rig %s (<= %.3g m)' % (
                    rp['height'], new_h, body['rig']['id'], cap))
                rp['height'] = new_h
                m = robots.build(family, {k: v for k, v in rp.items()})
            tris['body'] = len(m.faces)
        except ValueError as exc:
            msg = str(exc)
            raise RecipeError('BUDGET' if 'over budget' in msg else 'RANGE', msg) from exc
        if crown:
            tris['attachments'] = 56
        clip_set = clip_set or ('robot_boss' if rec['role'] == 'boss' else 'robot')
        _req(clip_set in body['clip_sets'], 'CLIPS', '%s cannot play clip set %s' % (body_id, clip_set))
        _req((clip_set == 'robot_boss') == (rec['role'] == 'boss'), 'CLIPS', 'robot_boss clips go with the boss role')
        item.update(kind='robot', robot={'body': family, 'params': rp, 'roles': roles, 'crown': crown,
                                         'clips': list(parts['clip_sets'][clip_set])})
        _req(tris['body'] < lock.budgets['creature_body_lt'], 'BUDGET', 'robot body %d tris >= %d' % (tris['body'], lock.budgets['creature_body_lt']))
        effective = dict(rp, roles=roles, crown=crown)
    else:
        if family in ('dasher', 'warden'):
            _req(not rec.get('outfit') and not colors, 'PART_BODY', 'the %s creature is a fixed archetype (no outfit/colours)' % family)
            item.update(kind='enemy', enemy={'dasher': 'cairn_dasher', 'warden': 'reed_warden'}[family])
            clip_set = clip_set or 'enemy'
            effective = {'enemy': item['enemy']}
        else:
            p = {'species': family}
            for pid, row in sorted(rows.items()):
                for k, v in row.get('params', {}).items():
                    p[k] = v
            for slot in COLOR_KEYS_ANIMAL:
                role = colors.get(slot) or lock.defaults.get(slot) or ('eye_glow' if slot == 'eyes' else 'coat_mid')
                p[COLOR_KEYS_ANIMAL[slot]] = _role(lock, slot, role, 'eye_glow' if slot == 'eyes' else slot)
            hard = {'size': (.65, 1.4), 'leg_length': (.75, 1.3), 'snout_length': (.7, 1.3), 'tail_length': (.35, 1.3), 'chubby': (.85, 1.25)}
            p.update(_check_tune(rec.get('tune') or {}, set(hard) | {'ear_shape'}, hard, 'animal body', clamps, lock))
            try:
                geometry.resolve(p, geometry.QUAD_DEFAULTS)
            except ValueError as exc:
                raise RecipeError('RANGE', 'generator refused: %s' % exc) from exc
            item.update(kind='animal', params=p, clips=None, seed=seed)
            clip_set = clip_set or 'animal'
            effective = p
        _req(clip_set in body['clip_sets'], 'CLIPS', '%s cannot play clip set %s' % (body_id, clip_set))
    total = tris['body'] + tris['attachments']
    _req(total <= lock.budgets['actor_total_le'], 'BUDGET', '%s: %d body + %d attachment tris > %d' % (rid, tris['body'], tris['attachments'], lock.budgets['actor_total_le']))
    report = {'recipe_sha256': recipe_digest(recipe), 'id': rid, 'body': body_id, 'family': family,
              'rig': '%s@%s' % (body['rig']['id'], body['rig']['version']), 'clip_set': clip_set,
              'clips': list(parts['clip_sets'][clip_set]), 'parts': sorted(rows), 'tris': tris,
              'clamps': clamps, 'warnings': warnings, 'lock': lock.receipt(), 'effective': effective,
              'display_name': rec['name']['display'], 'placeholder_name': rec['name']['placeholder'], 'role': rec['role'],
              'hover': rec['body'] == 'body.robot_floater'}
    return item, report


def compile_cast_recipe(recipe, root=ROOT):
    """Imported legacy cast row (recipe.legacy) -> the exact build item that reproduces its published bytes."""
    validate_schema(recipe)
    lg = recipe.get('legacy')
    _req(lg is not None, 'SCHEMA', 'not a legacy cast recipe')
    return {'id': recipe['id'], 'kind': lg['kind'], 'pack_id': lg['pack'], 'params': copy.deepcopy(lg['params']),
            'stance': lg['stance'], 'props': list(lg['props']), 'seed': SEED_DEFAULT, 'clips': None,
            'out': '%s/%s.glb' % (lg['pack'], recipe['id'])}


# ------------------------------------------------------------------ typed edits
EDIT_KINDS = ('height', 'build', 'hair', 'color', 'swap', 'face', 'prop', 'name')


def apply_edit(recipe, edit):
    """One typed edit -> a new recipe (validated by the caller's compile). Raises RecipeError on a malformed edit.
    height {value} | build {head?, shoulders?, waist?, legs?, age?} | hair {style?, color?} | color {slot, role} |
    swap {part} (replaces the outfit part of the same slot) | face {preset?, expression?, eyes?, beard?, visor?} |
    prop {part|null} | name {display, placeholder?}"""
    _req(isinstance(edit, dict) and edit.get('kind') in EDIT_KINDS, 'SCHEMA', 'edit kind must be one of ' + ', '.join(EDIT_KINDS))
    rec = copy.deepcopy(recipe)
    k = edit['kind']
    parts = load_parts()
    if k == 'height':
        rec.setdefault('build', {})['height'] = edit['value']
    elif k == 'build':
        for key in ('head', 'shoulders', 'waist', 'legs', 'age'):
            if key in edit:
                rec.setdefault('build', {})[key] = edit[key]
    elif k == 'hair':
        h = rec.setdefault('hair', {})
        for key in ('style', 'color'):
            if key in edit:
                h[key] = edit[key]
        if edit.get('style'):
            rec['outfit'] = [p for p in rec.get('outfit', []) if p != 'hat.beanie']
    elif k == 'color':
        _req(isinstance(edit.get('slot'), str) and isinstance(edit.get('role'), str), 'SCHEMA', 'color edit needs slot + role')
        if edit['slot'] == 'skin' and rec['archetype'] == 'person':
            rec['skin'] = edit['role']
        elif edit['slot'] == 'hair' and rec['archetype'] == 'person':
            rec.setdefault('hair', {})['color'] = edit['role']
        elif edit['slot'] == 'eyes' and rec['archetype'] == 'person' and rec['body'] == 'body.person':
            rec.setdefault('face', {})['eyes'] = edit['role']
        else:
            rec.setdefault('colors', {})[edit['slot']] = edit['role']
    elif k == 'swap':
        pid = edit.get('part')
        row = parts['parts'].get(pid)
        _req(row is not None, 'UNKNOWN_PART', 'unknown part id %r' % pid)
        out = []
        for p in rec.get('outfit', []):
            r = parts['parts'].get(p)
            same = r and (r['kind'] == row['kind'] and (row['kind'] in SINGLE_KINDS or (r.get('group') and r.get('group') == row.get('group'))))
            if not same:
                out.append(p)
        if row['kind'] == 'beard':
            (rec.get('face') or {}).pop('beard', None)
        if row['kind'] == 'hair':
            rec.setdefault('hair', {})['style'] = pid
            out = [p for p in out if p != 'hat.beanie']
        elif row['kind'] == 'face':
            rec.setdefault('face', {})['preset'] = pid
        elif row['kind'] == 'prop':
            rec['prop'] = pid
        else:
            out.append(pid)
            if pid == 'hat.beanie':
                rec.get('hair', {}).pop('style', None)
        rec['outfit'] = out
    elif k == 'face':
        f = rec.setdefault('face', {})
        for key in ('preset', 'expression', 'eyes', 'beard', 'visor'):
            if key in edit:
                f[key] = edit[key]
        if 'beard' in edit:          # one beard: the face edit replaces a beard listed in the outfit
            rec['outfit'] = [p for p in rec.get('outfit', []) if (parts['parts'].get(p) or {}).get('kind') != 'beard']
    elif k == 'prop':
        rec['prop'] = edit.get('part')
        rec['stance'] = None
    elif k == 'name':
        rec['name'] = {'display': edit['display'], 'placeholder': bool(edit.get('placeholder', False))}
    return rec


def summary(recipe):
    """One line a human can scan."""
    parts = [p.split('.', 1)[1] for p in recipe.get('outfit', [])]
    b = recipe.get('build') or {}
    bits = [recipe['body'].split('.', 1)[1], ('%.2fm' % b['height']) if 'height' in b else '', b.get('age', '')]
    if recipe.get('hair', {}).get('style'):
        bits.append(recipe['hair']['style'].split('.', 1)[1])
    bits += parts[:6]
    if recipe.get('prop'):
        bits.append('holding ' + recipe['prop'].split('.', 1)[1])
    return ' '.join(x for x in bits if x)
