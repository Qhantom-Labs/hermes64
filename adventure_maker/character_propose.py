"""Brief (+ optional reference images) -> THREE draft recipes. Deterministic, no model call, no network.

The brief is read with a small fixed vocabulary (body, age, hair, colours, garments, props, mood); anything it does
not mention is filled from the style lock's defaults and, for the second and third variants, from seeded
alternatives that never contradict what the brief did say. References are measured, never traced: the subject is
separated from a plain background by the border colour, cut into hair / face / top / legs / feet bands, and each
band's median colour is mapped to the nearest palette ROLE of the lock (Lab distance) - faces stay painted in house
style. The human picks a variant; nothing is adopted automatically.
"""
import hashlib
import json
import re
from pathlib import Path

from . import character_recipe as CR
from . import character_style as CS

RIG = {'id': 'human16_v1', 'version': '1.0.0'}
WORDS = re.compile(r"[a-z]+")

ROBOT = {'robot', 'robots', 'droid', 'android', 'mech', 'bot', 'bots', 'automaton', 'machine', 'unit', 'drone', 'drones'}
FLOAT = {'floating', 'floats', 'hover', 'hovering', 'flying', 'drone', 'drones', 'floater'}
BRUTE = {'big', 'huge', 'heavy', 'tall', 'brute', 'hulking', 'guard', 'bruiser', 'massive', 'enforcer', 'tank'}
SMALL = {'small', 'little', 'tiny', 'porter', 'helper', 'courier', 'walker', 'short', 'stubby'}
CAT, DOG = {'cat', 'kitten', 'cats'}, {'dog', 'puppy', 'hound', 'dogs'}
MASKED = {'masked', 'hooded', 'cowled', 'faceless', 'resident'}
AGE = {'child': {'child', 'kid', 'boy', 'girl', 'toddler'}, 'teen': {'teen', 'teenager', 'teenage', 'teenaged', 'adolescent', 'youth'},
       'elder': {'old', 'elder', 'elderly', 'grandmother', 'grandfather', 'aged', 'retired', 'grandma', 'grandpa'}}
ROLE = {'boss': {'boss', 'overseer', 'foreman', 'warlord'}, 'enemy': {'enemy', 'enemies', 'hostile', 'attacker', 'sentry', 'raider'},
        'crowd': {'crowd', 'passerby', 'citizen', 'extra', 'background'}, 'companion': {'companion', 'sidekick', 'friend'}}
HAIR = {'bald': 'hair.bald', 'ponytail': 'hair.ponytail', 'bun': 'hair.bun', 'braid': 'hair.braid', 'braided': 'hair.braid',
        'curly': 'hair.curls', 'curls': 'hair.curls', 'long': 'hair.long', 'bob': 'hair.bob', 'spiky': 'hair.spiky',
        'swept': 'hair.swept', 'crop': 'hair.crop', 'cropped': 'hair.crop', 'buzz': 'hair.crop'}
HAIR_COLOUR = {'black': 'hair_black', 'brown': 'hair_brown', 'brunette': 'hair_brown', 'auburn': 'hair_auburn', 'red': 'hair_auburn',
               'ginger': 'hair_auburn', 'blond': 'hair_blond', 'blonde': 'hair_blond', 'grey': 'hair_grey', 'gray': 'hair_grey',
               'white': 'hair_white', 'silver': 'hair_white', 'dyed': 'hair_dyed', 'pink': 'hair_dyed', 'teal': 'hair_dyed'}
SKIN = {'pale': 'skin_light', 'fair': 'skin_fair', 'light': 'skin_fair', 'olive': 'skin_mid', 'tan': 'skin_tan',
        'tanned': 'skin_tan', 'brown': 'skin_tan', 'dark': 'skin_deep', 'deep': 'skin_deep'}
CLOTH = {'red': 'cloth_warm', 'orange': 'cloth_warm', 'rust': 'cloth_warm', 'maroon': 'cloth_warm', 'blue': 'cloth_cool',
         'navy': 'cloth_deep', 'teal': 'cloth_cool', 'green': 'cloth_bright', 'yellow': 'cloth_accent', 'gold': 'cloth_accent',
         'mustard': 'cloth_accent', 'white': 'cloth_light', 'cream': 'cloth_pale', 'black': 'cloth_deep', 'grey': 'cloth_muted',
         'gray': 'cloth_muted', 'brown': 'leather', 'purple': 'cloth_deep', 'violet': 'cloth_pale'}
TOP = {'jacket': 'top.jacket', 'coat': 'top.parka', 'parka': 'top.parka', 'robe': 'top.robe', 'robes': 'top.robe',
       'apron': 'top.apron', 'tunic': 'top.tunic', 'sweater': 'top.sweater', 'jumper': 'top.sweater', 'vest': 'top.vest',
       'coverall': 'top.coverall', 'coveralls': 'top.coverall', 'overalls': 'top.coverall', 'jumpsuit': 'top.coverall',
       'uniform': 'top.coverall', 'cardigan': 'top.sweater'}
PROP = {'mug': 'prop.mug', 'coffee': 'prop.mug', 'tea': 'prop.mug', 'lantern': 'prop.lantern', 'lamp': 'prop.lantern',
        'tablet': 'prop.datapad', 'datapad': 'prop.datapad', 'clipboard': 'prop.datapad', 'cane': 'prop.cane',
        'stick': 'prop.cane', 'satchel': 'prop.satchel', 'bag': 'prop.duffel', 'duffel': 'prop.duffel', 'book': 'prop.book',
        'reading': 'prop.book', 'thermos': 'prop.thermos', 'staff': 'prop.staff', 'flask': 'prop.thermos'}
FACE = {'stern': 'face.stern', 'serious': 'face.stern', 'grim': 'face.stern', 'strict': 'face.stern', 'weathered': 'face.weathered',
        'tired': 'face.weathered', 'sharp': 'face.sharp', 'shrewd': 'face.sharp', 'scarred': 'face.scarred', 'scar': 'face.scarred',
        'gentle': 'face.gentle', 'kind': 'face.gentle', 'warm': 'face.gentle', 'cheerful': 'face.bright', 'bright': 'face.bright',
        'friendly': 'face.bright', 'round': 'face.round', 'freckled': 'face.freckled', 'freckles': 'face.freckled'}
EXPR = {'smiling': 'smile', 'smile': 'smile', 'happy': 'smile', 'cheerful': 'smile', 'worried': 'worried', 'nervous': 'worried',
        'surprised': 'surprised', 'sleepy': 'sleepy', 'tired': 'sleepy'}
MISC = {'scarf': 'collar.scarf', 'shawl': 'cape.shawl', 'gloves': 'hands.gloves', 'beanie': 'hat.beanie', 'hat': 'hat.beanie',
        'hood': 'hood.down', 'belt': 'acc.belt', 'boots': 'boots.heavy', 'shoes': 'boots.shoes', 'cargo': 'legs.cargo',
        'beard': 'beard.short', 'bearded': 'beard.full', 'moustache': 'beard.moustache', 'mustache': 'beard.moustache',
        'stubble': 'beard.stubble', 'satchel': 'acc.strap_satchel', 'strap': 'acc.strap_diagonal', 'backpack': 'acc.backpack'}
ROBOT_HEAD = {'dome': 'rhead.dome', 'domed': 'rhead.dome', 'lantern': 'rhead.lantern', 'helm': 'rhead.helm', 'helmet': 'rhead.helm', 'lid': 'rhead.lid'}
ROBOT_HAND = {'pincer': 'rhand.pincer', 'pincers': 'rhand.pincer', 'claw': 'rhand.pincer', 'claws': 'rhand.pincer', 'fist': 'rhand.fist',
              'fists': 'rhand.fist', 'mitt': 'rhand.mitt'}
ROBOT_VISOR = {'grille': 'visor.grille', 'grill': 'visor.grille', 'band': 'visor.band', 'slit': 'visor.slit',
               'twin': 'visor.twin', 'goggles': 'visor.twin', 'goggle': 'visor.twin'}
ROBOT_FOOT = {'long': 'rfoot.long', 'big': 'rfoot.long', 'pad': 'rfoot.pad', 'pads': 'rfoot.pad', 'padded': 'rfoot.pad'}
SLEEVES = {'rolled': 'sleeves.rolled', 'short': 'sleeves.short', 'long': 'sleeves.long'}
PATTERN = {'knit': 'pattern.knit', 'knitted': 'pattern.knit', 'quilted': 'pattern.quilted', 'striped': 'pattern.stripes',
           'stripes': 'pattern.stripes', 'stripy': 'pattern.stripes', 'checked': 'pattern.checks', 'checks': 'pattern.checks',
           'plaid': 'pattern.checks', 'tartan': 'pattern.checks', 'plain': 'pattern.plain'}
ROBOT_ACC = {'antenna': 'racc.antenna', 'backpack': 'racc.backpack', 'pauldrons': 'racc.pauldrons', 'armour': 'racc.pauldrons',
             'armor': 'racc.pauldrons', 'ears': 'racc.ear_pods', 'ear': 'racc.ear_pods', 'pods': 'racc.ear_pods',
             'vents': 'racc.vents', 'exhaust': 'racc.vents'}
# Robot liveries as role sets (the lock decides the colours): pearl, cobalt, graphite, steel.
LIVERIES = [{'shell': 'shell_light', 'shell_alt': 'shell_alt', 'dark': 'shell_dark'},
            {'shell': 'shell_alt', 'shell_alt': 'shell_light', 'dark': 'shell_dark'},
            {'shell': 'shell_dark', 'shell_alt': 'shell', 'dark': 'joint', 'accent': 'warning'},
            {'shell': 'shell', 'shell_alt': 'metal_light', 'dark': 'shell_dark', 'accent': 'emblem'}]
ROBOT_COLOUR = {'red': 'warning', 'orange': 'warning', 'yellow': 'warning', 'gold': 'emblem', 'blue': 'shell_alt',
                'teal': 'shell_alt', 'white': 'shell_light', 'silver': 'shell_light', 'chrome': 'shell', 'black': 'shell_dark',
                'dark': 'shell_dark', 'grey': 'shell', 'gray': 'shell'}


def _words(text):
    return WORDS.findall((text or '').lower())


def _pick(seq, h, k):
    return seq[int(h[k * 4:k * 4 + 4], 16) % len(seq)]


def _first(words, table):
    for w in words:
        if w in table:
            return table[w]
    return None


def _all(words, table):
    out = []
    for w in words:
        if w in table and table[w] not in out:
            out.append(table[w])
    return out


def _slug(text, n=3):
    ws = [w for w in _words(text) if w not in {'a', 'an', 'the', 'with', 'and', 'of', 'in', 'who', 'that', 'wearing', 'holding'}]
    return '_'.join(ws[:n])[:30] or 'character'


COLOUR_RGB = {'red': (190, 40, 40), 'orange': (225, 120, 40), 'rust': (170, 70, 40), 'maroon': (110, 30, 40),
              'yellow': (235, 200, 50), 'gold': (210, 170, 60), 'mustard': (200, 160, 40), 'green': (60, 150, 70),
              'teal': (30, 140, 140), 'blue': (50, 90, 190), 'navy': (30, 40, 90), 'purple': (110, 60, 150),
              'violet': (140, 100, 190), 'pink': (230, 130, 170), 'white': (240, 240, 240), 'cream': (235, 225, 195),
              'grey': (130, 130, 135), 'gray': (130, 130, 135), 'black': (25, 25, 30), 'brown': (110, 70, 40),
              'tan': (190, 150, 100), 'silver': (190, 195, 205)}
WEAR_FAMILIES = ('cloth', 'trim', 'leather', 'metal')


def colour_role(word, lock, families=WEAR_FAMILIES):
    """The lock role (of `families`) whose actual colour is nearest the colour word (Lab): a style-relative read."""
    if word not in COLOUR_RGB:
        return None
    target = _lab(COLOUR_RGB[word])
    pal = dict(lock.colours)
    best = None
    for fam in families:
        for role in CS.ROLE_FAMILIES[fam]:
            hx = pal[lock.roles[role].split('+')[0]]
            c = _lab(tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5)))
            d = sum((target[i] - c[i]) ** 2 for i in range(3))
            if best is None or d < best[0]:
                best = (d, role)
    return best[1]


HAIR_NOUNS = {'hair', 'ponytail', 'bun', 'braid', 'braids', 'curls', 'bob', 'locks', 'beard'}
LEG_NOUNS = {'trousers', 'pants', 'skirt', 'shorts', 'jeans', 'leggings', 'cargo'}
SKIN_NOUNS = {'skin', 'skinned', 'complexion'}


def bind_colours(w):
    """Colour word -> the noun it describes (looks ahead two words): {'hair'|'top'|'legs'|'skin'|'extra': colour}."""
    out, free = {}, []
    for i, word in enumerate(w):
        if word not in CLOTH and word not in HAIR_COLOUR and word not in SKIN:
            continue
        target = None
        for nxt in w[i + 1:i + 3]:
            if nxt in HAIR_NOUNS:
                target = 'hair'; break
            if nxt in TOP or nxt in ('shirt', 'top', 'hoodie', 'sweatshirt'):
                target = 'top'; break
            if nxt in LEG_NOUNS:
                target = 'legs'; break
            if nxt in SKIN_NOUNS:
                target = 'skin'; break
            if nxt in ('scarf', 'hood', 'hat', 'beanie', 'boots', 'gloves', 'cape', 'shawl'):
                target = nxt; break
        if target is None:
            free.append(word)
        elif target not in out:
            out[target] = word
    for word in free:
        if word in CLOTH and 'top' not in out:
            out['top'] = word
        elif word in CLOTH and 'legs' not in out:
            out['legs'] = word
    return out


def parse(brief):
    w = _words(brief)
    ws = set(w)
    if ws & (CAT | DOG):
        return {'archetype': 'creature', 'body': 'body.animal_cat' if ws & CAT else 'body.animal_dog', 'w': w}
    if ws & ROBOT or ws & FLOAT and not ws & {'person', 'woman', 'man'}:
        fam = 'floater' if ws & FLOAT else ('brute' if ws & BRUTE else 'walker')
        return {'archetype': 'robot', 'body': 'body.robot_' + fam, 'family': fam, 'w': w}
    body = 'body.person_masked' if ws & MASKED else 'body.person'
    return {'archetype': 'person', 'body': body, 'w': w}


def _role_of(ws):
    for role, keys in ROLE.items():
        if ws & keys:
            return role
    return 'npc'


def draft(brief, lock, variant=0, refs=None):
    """One draft recipe for variant 0/1/2 (0 = the brief read literally + lock defaults)."""
    pr = parse(brief)
    w = pr['w']; ws = set(w)
    h = hashlib.sha256(('%s|%d' % (brief.strip().lower(), variant)).encode()).hexdigest()
    rid = '%s_%s' % (_slug(brief), 'abc'[variant])
    rec = {'schema_version': '1.0.0', 'id': rid, 'rig': dict(RIG), 'archetype': pr['archetype'], 'body': pr['body'],
           'role': _role_of(ws), 'name': {'display': _slug(brief, 2).replace('_', ' ').title(), 'placeholder': True},
           'seed': 19}
    lib = CR.load_parts()
    parts = lib['parts']
    rec['rig'] = dict(lib['bodies'][pr['body']]['rig'])
    unmet = []
    if pr['archetype'] == 'robot':
        fam = pr['family']
        if rec['role'] == 'npc':
            rec['role'] = 'enemy'
        outfit = []
        head = _first(w, ROBOT_HEAD)
        heads = [p for p, r in parts.items() if r['kind'] == 'rhead' and pr['body'] in r['bodies']]
        hands = [p for p, r in parts.items() if r['kind'] == 'rhand' and pr['body'] in r['bodies']]
        visors = ['visor.twin', 'visor.band', 'visor.slit', 'visor.grille']
        if head is not None and head not in heads:
            unmet.append('%s head is not available on the %s body' % (head.split('.')[1], fam))
        if head not in heads:
            head = heads[0] if variant == 0 else _pick(heads, h, 1)
        hand = _first(w, ROBOT_HAND)
        if hand is not None and hand not in hands:
            unmet.append('%s hands are not available on the %s body' % (hand.split('.')[1], fam))
        if hand not in hands:
            hand = hands[0] if variant == 0 else _pick(hands, h, 2)
        visor = _first(w, ROBOT_VISOR) or (
            ('visor.slit' if ws & {'menacing', 'hostile', 'enemy', 'boss', 'sentry', 'angry'} else visors[0]) if variant == 0
            else _pick(visors, h, 3))
        outfit += [head, hand, visor]
        foot = next((ROBOT_FOOT[a] for a, b in zip(w, w[1:]) if a in ROBOT_FOOT and b in ('feet', 'foot', 'footed')), None)
        if foot and pr['body'] not in parts[foot]['bodies']:
            unmet.append('%s feet do not fit the %s body' % (foot.split('.')[1], fam))
        elif foot:
            outfit.append(foot)
        unmet += ['%s do not fit the %s body' % (a.split('.')[1], fam) for a in _all(w, ROBOT_ACC) if pr['body'] not in parts[a]['bodies']]
        accs = [a for a in _all(w, ROBOT_ACC) if pr['body'] in parts[a]['bodies']]
        if variant and not accs:
            opts = [p for p, r in parts.items() if r['kind'] == 'racc' and pr['body'] in r['bodies']]
            accs = [_pick(opts, h, 4)]
        outfit += accs
        rec['outfit'] = outfit
        colours = {}
        cw = [c for c in w if c in ROBOT_COLOUR]
        for i, c in enumerate(cw[:2]):
            slot = 'accent' if ROBOT_COLOUR[c] == 'warning' else ('shell' if i == 0 else 'shell_alt')
            colours[slot] = ROBOT_COLOUR[c] if slot != 'shell' or ROBOT_COLOUR[c] != 'warning' else 'shell'
        if not colours:
            # no colour words: a livery preset seeded by the brief, offset per variant so a/b/c always differ
            hv = int(hashlib.sha256(brief.strip().lower().encode()).hexdigest()[:8], 16)
            colours.update(LIVERIES[(hv + variant) % len(LIVERIES)])
        if colours:
            rec['colors'] = colours
        lo, hi, d = (lock.proportions['robot_height'][fam] + [None])[:3]
        if variant:
            rec['build'] = {'height': round(lo + (hi - lo) * (.3 + .4 * (int(h[24:28], 16) / 65535.)), 3)}
        if rec['role'] == 'boss':
            rec['boss'] = {'scale': 1.12, 'crown': 'crown.points', 'emblem': 'emblem.arch'}
            rec['clips'] = 'robot_boss'
        if unmet:
            rec['notes'] = ('not available: ' + '; '.join(unmet))[:400]
        return rec
    if pr['archetype'] == 'creature':
        rec['role'] = 'companion' if rec['role'] == 'npc' else rec['role']
        coats = [p for p, r in parts.items() if r['kind'] == 'coat']
        rec['outfit'] = [_first(w, {k: v for k, v in zip(['tuxedo', 'tabby', 'calico', 'spotted', 'socks', 'saddle', 'solid'],
                                                            ['coat.tuxedo', 'coat.tabby', 'coat.calico', 'coat.spotted', 'coat.socks', 'coat.saddle', 'coat.solid'])})
                         or (coats[1] if variant == 0 else _pick(coats, h, 1))]
        cmap = {'black': 'coat_dark', 'white': 'coat_light', 'ginger': 'coat_warm', 'orange': 'coat_warm', 'brown': 'coat_mid', 'grey': 'coat_mid'}
        cs = [cmap[c] for c in w if c in cmap]
        if cs:
            rec['colors'] = {'coat': cs[0]}
            if len(cs) > 1:
                rec['colors']['coat2'] = cs[1]
        return rec
    # people (the boss template is a robot/creature body: a person stays an npc and says so)
    if rec['role'] == 'boss':
        rec['role'] = 'npc'
        unmet.append('the boss template needs a robot body')
    age = next((a for a, keys in AGE.items() if ws & keys), 'adult')
    if pr['body'] == 'body.person_masked':
        age = 'adult'
    rng = lock.proportions['height'][age if pr['body'] == 'body.person' else 'masked']
    rec['build'] = {'age': age} if pr['body'] == 'body.person' else {}
    frac = .5 if variant == 0 else .25 + .5 * (int(h[8:12], 16) / 65535.)
    if ws & {'tall', 'lanky'}:
        frac = .85
    hair_short = re.search(r'\bshort (\w+ )?(hair|crop|cut|locks)\b', ' '.join(w)) is not None
    if ws & {'small', 'little'} or ('short' in ws and not hair_short):
        frac = .15
    rec['build']['height'] = round(rng[0] + (rng[1] - rng[0]) * frac, 3)
    if ws & {'stocky', 'broad', 'burly', 'strong'}:
        rec['build']['shoulders'] = lock.proportions['shoulders'][1]
    if pr['body'] == 'body.person_masked':
        tops = ['vest.quilted_wave', 'vest.quilted_diamond', 'vest.leather', 'vest.apron']
        outfit = ['hood.cowl', tops[0] if variant == 0 else _pick(tops, h, 2), 'cape.capelet', 'hands.gloves', 'boots.heavy']
        if variant == 2 or 'skirt' in ws:
            outfit.append('legs.skirt')
        extra = [m for m in _all(w, MISC) if parts.get(m) and 'body.person_masked' in parts[m]['bodies']]
        rec['outfit'] = list(dict.fromkeys(outfit + [e for e in extra if e not in ('hands.gloves',)]))
        cw = [colour_role(c, lock) for c in w if c in COLOUR_RGB]
        if cw:
            rec['colors'] = {'hood': cw[0]}
            if len(cw) > 1:
                rec['colors']['vest'] = cw[1]
        prop = _first(w, PROP)
        if prop:
            rec['prop'] = prop
        return rec
    hair = _first(w, HAIR)
    styles = ['hair.crop', 'hair.swept', 'hair.bob', 'hair.ponytail', 'hair.bun', 'hair.braid', 'hair.curls', 'hair.long', 'hair.spiky']
    if age == 'elder':
        styles = ['hair.crop', 'hair.bun', 'hair.swept', 'hair.bald']
    wants_hat = bool(ws & {'beanie', 'hat'})
    outfit = []
    if not wants_hat:
        rec['hair'] = {'style': hair or (styles[0] if variant == 0 else _pick(styles, h, 2))}
    bound = bind_colours(w)
    hc = HAIR_COLOUR.get(bound['hair']) if bound.get('hair') in HAIR_COLOUR else _first([x for x in w if x in ('blond', 'blonde', 'ginger', 'auburn', 'brunette', 'silver')], HAIR_COLOUR)
    if age == 'elder' and not hc:
        hc = 'hair_grey' if variant != 1 else 'hair_white'
    if hc:
        rec.setdefault('hair', {})['color'] = hc
    elif variant:
        rec.setdefault('hair', {})['color'] = _pick(['hair_black', 'hair_brown', 'hair_auburn', 'hair_blond'], h, 3)
    sk = SKIN.get(bound.get('skin', '')) or _first([x for x in w if x in ('pale', 'fair', 'olive', 'tan', 'tanned')], SKIN)
    if sk:
        rec['skin'] = sk
    elif variant:
        rec['skin'] = _pick(['skin_light', 'skin_fair', 'skin_mid', 'skin_tan', 'skin_deep'], h, 4)
    top = _first(w, TOP)
    tops = ['top.sweater', 'top.jacket', 'top.tunic', 'top.parka', 'top.coverall', 'top.vest', 'top.apron']
    outfit.append(top or (tops[0] if variant == 0 else _pick(tops, h, 5)))
    misc = [m for m in _all(w, MISC) if parts.get(m) and 'body.person' in parts[m]['bodies']]
    unmet += ['%s is only on the masked body' % m.split('.')[1] for m in _all(w, MISC)
              if parts.get(m) and 'body.person' not in parts[m]['bodies']]
    if ws & {'skirt', 'skirts'}:
        unmet.append('skirt is only on the masked body')
    sl = next((SLEEVES[a] for a, b in zip(w, w[1:]) if a in SLEEVES and b in ('sleeves', 'sleeve', 'sleeved')), None)
    if sl:
        misc.append(sl)
    pat = _first(w, PATTERN)
    if pat and 'body.person' in parts.get(pat, {}).get('bodies', []):
        misc.append(pat)
    if wants_hat:
        misc = [m for m in misc if m != 'hood.down'] + (['hat.beanie'] if 'hat.beanie' not in misc else [])
    outfit += misc
    if 'legs' not in {parts[p]['kind'] for p in outfit}:
        legs = ['legs.trousers', 'legs.trousers_slim', 'legs.cargo', 'legs.trousers_wide']
        outfit.append(legs[0] if variant == 0 else _pick(legs, h, 6))
    if variant == 2 and not any(parts[p]['kind'] == 'collar' for p in outfit):
        outfit.append(_pick(['collar.scarf', 'collar.high', 'collar.flat'], h, 7))
    rec['outfit'] = list(dict.fromkeys(outfit))
    colours = {}
    # the outer garment (jacket, parka, coverall, sweater, robe, tunic) is painted with the garment colour
    for target, slot in (('top', 'garment'), ('legs', 'legs'), ('scarf', 'collar'), ('hood', 'collar'), ('boots', 'boots'),
                         ('gloves', 'gloves'), ('shawl', 'collar'), ('hat', 'hat'), ('beanie', 'hat')):
        role = colour_role(bound.get(target), lock)
        if role:
            colours[slot] = role
    if colours.get('hat') and not wants_hat:
        colours.pop('hat')
    # unspecified slots vary per brief (seeded, never contradicting it): a crowd is not one uniform
    hv = hashlib.sha256(brief.strip().lower().encode()).hexdigest()
    colours.setdefault('legs', _pick(['cloth_dark', 'cloth_deep', 'cloth_muted', 'leather', 'cloth_mid'], hv, 10))
    colours.setdefault('garment', _pick(['cloth_warm', 'cloth_cool', 'cloth_mid', 'cloth_muted', 'cloth_pale', 'cloth_accent'], hv, 11))
    if variant and 'top' not in colours:
        colours['top'] = _pick(['cloth_light', 'cloth_pale', 'cloth_muted', 'trim_light'], h, 8)
        if not bound.get('top'):
            colours['garment'] = _pick(['cloth_warm', 'cloth_cool', 'cloth_accent', 'cloth_bright', 'cloth_muted', 'cloth_light'], h, 12)
    if colours:
        rec['colors'] = colours
    face = {}
    fp = 'face.scarred' if ws & {'scar', 'scarred'} else _first(w, FACE)
    if age == 'elder' and not fp:
        fp = 'face.elder_kind' if variant != 2 else 'face.weathered'
    if fp:
        face['preset'] = fp
    elif variant:
        face['preset'] = _pick(['face.calm', 'face.gentle', 'face.bright', 'face.round', 'face.freckled', 'face.sharp'], h, 9)
    ex = _first(w, EXPR)
    if ex:
        face['expression'] = ex
    if face:
        rec['face'] = face
    prop = _first(w, PROP)
    if prop:
        rec['prop'] = prop
        if prop == 'prop.staff':
            rec['clips'] = 'human_combat'
    if unmet:
        rec['notes'] = ('not available: ' + '; '.join(unmet))[:400]
    if refs:
        apply_reference(rec, refs, lock)
    return rec


def propose(brief, lock, refs=None):
    """-> [recipe A, B, C]; each compiles against `lock` (a variant that cannot is replaced by the literal read)."""
    out = []
    for v in range(3):
        rec = draft(brief, lock, v, refs)
        try:
            CR.compile_build(rec, lock)
        except CR.RecipeError:
            rec = dict(draft(brief, lock, 0, refs), id=rec['id'])
        out.append(rec)
    return out


# ------------------------------------------------------------------ reference images -> roles (measurement only)
def _lab(rgb):
    def lin(c):
        c = c / 255.
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb)
    x = (.4124 * r + .3576 * g + .1805 * b) / .95047
    y = .2126 * r + .7152 * g + .0722 * b
    z = (.0193 * r + .1192 * g + .9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3.) if t > .008856 else 7.787 * t + 16 / 116.
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def measure_reference(path):
    """-> {'hair', 'skin', 'top', 'legs', 'feet'}: median RGB of the subject in each height band (or None)."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    im.thumbnail((96, 96))
    w, h = im.size
    px = im.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    rows = [y for y in range(h) if any(max(abs(px[x, y][i] - bg[i]) for i in range(3)) > 40 for x in range(w))]
    if not rows:
        return {}
    y0, y1 = rows[0], rows[-1] + 1
    bands = {'hair': (0., .12), 'skin': (.12, .2), 'top': (.25, .55), 'legs': (.6, .88), 'feet': (.9, 1.)}
    out = {}
    for name, (a, b) in bands.items():
        cols = []
        for y in range(int(y0 + a * (y1 - y0)), max(int(y0 + b * (y1 - y0)), int(y0 + a * (y1 - y0)) + 1)):
            for x in range(w):
                c = px[x, min(y, h - 1)]
                if max(abs(c[i] - bg[i]) for i in range(3)) > 40:
                    cols.append(c)
        if cols:
            out[name] = tuple(sorted(c[i] for c in cols)[len(cols) // 2] for i in range(3))
    return out


def nearest_role(rgb, lock, family):
    pal = dict(lock.colours)
    best = None
    for role in CS.ROLE_FAMILIES[family]:
        tok = lock.roles[role].split('+')[0]
        hx = pal[tok]
        c = tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
        a, b = _lab(rgb), _lab(c)
        d = sum((a[i] - b[i]) ** 2 for i in range(3))
        if best is None or d < best[0]:
            best = (d, role)
    return best[1]


def apply_reference(rec, refs, lock):
    """Fill colour ROLES from the first readable reference (person bodies only; faces are never traced)."""
    if rec['archetype'] != 'person':
        return rec
    for path in refs:
        m = measure_reference(path)
        if not m:
            continue
        if rec['body'] == 'body.person':
            if 'skin' in m:
                rec['skin'] = nearest_role(m['skin'], lock, 'skin')
            if 'hair' in m and rec.get('hair') is not None:
                rec['hair']['color'] = nearest_role(m['hair'], lock, 'hair')
        cols = rec.setdefault('colors', {})
        fam = ('cloth', 'trim', 'leather', 'metal')
        for band, slot in (('top', 'top' if rec['body'] == 'body.person' else 'vest'), ('legs', 'legs'), ('feet', 'boots')):
            if band in m:
                best = None
                for f in fam:
                    r = nearest_role(m[band], lock, f)
                    tok = lock.roles[r].split('+')[0]
                    hx = dict(lock.colours)[tok]
                    c = tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
                    d = sum((x - y) ** 2 for x, y in zip(_lab(m[band]), _lab(c)))
                    if best is None or d < best[0]:
                        best = (d, r)
                if slot == 'boots' and CS.FAMILY_OF[best[1]] not in ('leather', 'metal', 'cloth', 'trim'):
                    continue
                cols[slot] = best[1]
        rec['notes'] = ('colour roles measured from %s' % Path(path).name)[:400]
        break
    return rec
