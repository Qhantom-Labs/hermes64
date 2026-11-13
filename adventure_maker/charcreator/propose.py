"""Plain words -> creator recipes (stdlib, deterministic). 'a tired wizard with a long beard and a star hat'.

Variant a is the literal read. b and c keep every attribute the brief names. They change only what the brief leaves
open: the palette for b; the build or the face style for c. Words the creator cannot make are listed in the
recipe notes as "not available: ...". They are never dropped silently.
"""
import hashlib
import re

from . import BODY_ID, CreatorError, compile as compile_recipe, data, new_recipe

WORD = re.compile(r"[a-z]+")
SPECIES = {'elf': 'elf', 'elven': 'elf', 'elvish': 'elf', 'dwarf': 'dwarf', 'dwarven': 'dwarf', 'goblin': 'goblin', 'gremlin': 'goblin',
           'imp': 'goblin', 'robot': 'robot', 'android': 'robot', 'droid': 'robot', 'automaton': 'robot', 'mech': 'robot', 'bot': 'robot',
           'cyborg': 'robot', 'cat': 'cat', 'kitty': 'cat', 'feline': 'cat', 'catgirl': 'cat', 'fox': 'fox', 'kitsune': 'fox', 'wolf': 'fox',
           'dog': 'fox', 'bear': 'bear', 'rabbit': 'rabbit', 'bunny': 'rabbit', 'hare': 'rabbit', 'human': 'human', 'person': 'human'}
BUILD = {'stocky': 'stocky', 'stout': 'stocky', 'squat': 'stocky', 'broad': 'stocky', 'short': 'stocky', 'lean': 'lean', 'slim': 'lean',
         'thin': 'lean', 'skinny': 'lean', 'slender': 'lean', 'wiry': 'lean', 'tall': 'tall', 'lanky': 'tall', 'towering': 'tall',
         'child': 'child', 'kid': 'child', 'boy': 'child', 'girl': 'child', 'little': 'child', 'young': 'child', 'youngster': 'child',
         'big': 'bulky', 'bulky': 'bulky', 'huge': 'bulky', 'heavy': 'bulky', 'burly': 'bulky', 'muscular': 'bulky', 'strong': 'bulky',
         'hulking': 'bulky', 'brawny': 'bulky', 'giant': 'bulky'}
OLD = {'old', 'elderly', 'aged', 'elder', 'ancient', 'grandfather', 'grandmother', 'granny', 'grandpa'}
TIRED = {'tired', 'sleepy', 'weary', 'exhausted', 'drowsy', 'bored'}
HAPPY = {'happy', 'cheerful', 'smiling', 'jolly', 'friendly', 'merry', 'grinning'}
GRUMPY = {'grumpy', 'angry', 'stern', 'grim', 'sad', 'worried', 'gloomy'}
HAIR = {'bald': 'hair.bald', 'spiky': 'hair.spiky', 'ponytail': 'hair.ponytail', 'bun': 'hair.bun', 'curly': 'hair.curly',
        'curls': 'hair.curly', 'afro': 'hair.curly', 'bob': 'hair.bob', 'bangs': 'hair.bob', 'mohawk': 'hair.spiky'}
HAT = {'beanie': 'hat.beanie', 'cap': 'hat.cap', 'helmet': 'hat.helmet', 'helm': 'hat.helmet', 'hood': 'hat.hood', 'hooded': 'hat.hood',
       'crown': 'hat.crown', 'tiara': 'hat.crown'}
OUTFIT = {'robe': 'outfit.robe', 'robes': 'outfit.robe', 'gown': 'outfit.robe', 'dress': 'outfit.robe', 'jacket': 'outfit.jacket',
          'coat': 'outfit.jacket', 'blazer': 'outfit.jacket', 'apron': 'outfit.apron', 'overalls': 'outfit.overalls',
          'dungarees': 'outfit.overalls', 'armor': 'outfit.armor', 'armour': 'outfit.armor', 'plate': 'outfit.armor', 'tunic': 'outfit.tunic'}
ROLE = {  # role word -> modules, colours, outfit
    'wizard': (['hat.wizard', 'held.staff'], {'top': 'purple', 'hat': 'purple', 'hat2': 'gold'}, 'outfit.robe'),
    'witch': (['hat.wizard', 'held.wand'], {'top': 'black', 'hat': 'black', 'hat2': 'violet'}, 'outfit.robe'),
    'mage': (['hat.wizard', 'held.wand'], {'top': 'blue', 'hat': 'blue', 'hat2': 'gold'}, 'outfit.robe'),
    'sorcerer': (['hat.wizard', 'held.staff'], {'top': 'navy', 'hat': 'navy', 'hat2': 'silver'}, 'outfit.robe'),
    'monk': ([], {'top': 'orange'}, 'outfit.robe'), 'priest': ([], {'top': 'white', 'top2': 'gold'}, 'outfit.robe'),
    'knight': (['hat.helmet', 'belt.plain'], {'top': 'steel', 'legs': 'charcoal', 'hat': 'steel', 'boots': 'steel', 'extra': 'charcoal'}, 'outfit.armor'),
    'soldier': (['hat.helmet', 'belt.plain'], {'top': 'forest', 'legs': 'forest', 'hat': 'forest'}, 'outfit.jacket'),
    'guard': (['hat.helmet', 'belt.plain'], {'top': 'steel', 'legs': 'navy', 'hat': 'steel'}, 'outfit.armor'),
    'merchant': (['backpack.pack', 'belt.buckle'], {'top': 'tan', 'legs': 'brown', 'pack': 'brown', 'top2': 'cream'}, 'outfit.tunic'),
    'trader': (['backpack.pack', 'belt.plain'], {'top': 'tan', 'legs': 'brown'}, 'outfit.tunic'),
    'barista': (['held.cup'], {'top': 'white', 'top2': 'forest', 'legs': 'charcoal', 'held': 'white'}, 'outfit.apron'),
    'chef': (['held.cup'], {'top': 'white', 'top2': 'white'}, 'outfit.apron'), 'cook': ([], {'top': 'white', 'top2': 'white'}, 'outfit.apron'),
    'baker': ([], {'top': 'cream', 'top2': 'white'}, 'outfit.apron'), 'smith': ([], {'top': 'charcoal', 'top2': 'brown'}, 'outfit.apron'),
    'blacksmith': ([], {'top': 'charcoal', 'top2': 'brown'}, 'outfit.apron'),
    'farmer': (['hat.cap'], {'top': 'red', 'legs': 'blue', 'hat': 'tan'}, 'outfit.overalls'),
    'mechanic': (['gloves.plain'], {'top': 'grey', 'legs': 'blue'}, 'outfit.overalls'),
    'adventurer': (['backpack.pack', 'belt.plain'], {'top': 'green', 'legs': 'brown'}, 'outfit.jacket'),
    'explorer': (['backpack.pack', 'hat.cap'], {'top': 'tan', 'legs': 'brown', 'hat': 'tan'}, 'outfit.jacket'),
    'scholar': (['held.book', 'glasses.round'], {'top': 'navy', 'top2': 'cream'}, 'outfit.robe'),
    'librarian': (['held.book', 'glasses.round'], {'top': 'brown', 'top2': 'cream'}, 'outfit.jacket'),
    'king': (['hat.crown', 'cape.long'], {'top': 'crimson', 'cape': 'crimson', 'cape2': 'gold', 'hat': 'gold', 'hat2': 'gold'}, 'outfit.robe'),
    'queen': (['hat.crown', 'cape.long'], {'top': 'purple', 'cape': 'purple', 'cape2': 'gold', 'hat': 'gold', 'hat2': 'gold'}, 'outfit.robe'),
    'prince': (['hat.crown', 'cape.short'], {'top': 'blue', 'cape': 'blue', 'hat': 'gold', 'hat2': 'gold'}, 'outfit.jacket'),
    'princess': (['hat.crown'], {'top': 'pink', 'hat': 'gold', 'hat2': 'gold'}, 'outfit.robe'),
    'pirate': (['belt.buckle'], {'top': 'crimson', 'legs': 'black'}, 'outfit.jacket'),
    'ninja': (['hat.hood'], {'top': 'black', 'legs': 'black', 'hat': 'black'}, 'outfit.tunic'),
    'thief': (['hat.hood', 'belt.plain'], {'top': 'charcoal', 'legs': 'charcoal', 'hat': 'charcoal'}, 'outfit.tunic'),
    'ranger': (['hat.hood', 'cape.short'], {'top': 'forest', 'cape': 'forest', 'hat': 'forest'}, 'outfit.tunic'),
    'hero': (['belt.plain'], {}, 'outfit.tunic'), 'villager': ([], {}, 'outfit.tunic'),
    'scientist': (['glasses.round'], {'top': 'white', 'top2': 'sky'}, 'outfit.jacket'),
    'engineer': (['glasses.goggles', 'gloves.plain'], {'top': 'orange', 'legs': 'navy'}, 'outfit.overalls'),
    'courier': (['backpack.pack', 'hat.cap'], {'top': 'teal', 'hat': 'teal'}, 'outfit.jacket'),
    'detective': (['hat.top_hat'], {'top': 'tan', 'hat': 'charcoal'}, 'outfit.jacket'),
    'gentleman': (['hat.top_hat'], {'top': 'black', 'hat': 'black'}, 'outfit.jacket'),
}
ACCESSORY = {'cape': 'cape.long', 'cloak': 'cape.long', 'mantle': 'cape.long', 'backpack': 'backpack.pack', 'rucksack': 'backpack.pack',
             'knapsack': 'backpack.pack', 'satchel': 'backpack.pack', 'belt': 'belt.plain', 'buckle': 'belt.buckle', 'glasses': 'glasses.round',
             'spectacles': 'glasses.round', 'goggles': 'glasses.goggles', 'gloves': 'gloves.plain', 'gauntlets': 'gloves.plain',
             'mittens': 'gloves.plain', 'boots': 'boots.heavy', 'shoes': 'boots.shoes', 'sneakers': 'boots.shoes', 'sandals': 'boots.shoes',
             'scarf': 'scarf.plain', 'horns': 'horns.small', 'horned': 'horns.small', 'antenna': 'horns.antenna', 'antennae': 'horns.antenna',
             'tail': None, 'staff': 'held.staff', 'wand': 'held.wand', 'book': 'held.book', 'tome': 'held.book', 'lantern': 'held.lantern',
             'lamp': 'held.lantern', 'cup': 'held.cup', 'mug': 'held.cup', 'coffee': 'held.cup', 'tea': 'held.cup'}
NOUN_SLOT = {'hat': 'hat', 'cap': 'hat', 'helmet': 'hat', 'helm': 'hat', 'hood': 'hat', 'beanie': 'hat', 'crown': 'hat',
             'cloak': 'cape', 'cape': 'cape', 'mantle': 'cape', 'robe': 'top', 'robes': 'top', 'jacket': 'top', 'coat': 'top',
             'shirt': 'top', 'tunic': 'top', 'top': 'top', 'armor': 'top', 'armour': 'top', 'dress': 'top', 'sweater': 'top',
             'hoodie': 'top', 'apron': 'top2', 'vest': 'top', 'overalls': 'legs', 'trousers': 'legs', 'pants': 'legs', 'skirt': 'legs',
             'leggings': 'legs', 'shorts': 'legs', 'jeans': 'legs', 'boots': 'boots', 'shoes': 'boots', 'gloves': 'gloves',
             'belt': 'belt', 'hair': 'hair', 'beard': 'hair', 'eyes': 'eyes', 'eye': 'eyes', 'skin': 'skin', 'fur': 'skin',
             'shell': 'skin', 'backpack': 'pack', 'pack': 'pack', 'bag': 'pack', 'scarf': 'top2', 'lining': 'cape2', 'stars': 'hat2',
             'trim': 'top2', 'collar': 'top2', 'sleeves': 'top', 'visor': 'eyes'}
COLOURS = {'red', 'crimson', 'orange', 'yellow', 'lime', 'green', 'forest', 'teal', 'sky', 'blue', 'navy', 'purple', 'violet', 'pink',
           'brown', 'tan', 'cream', 'white', 'grey', 'gray', 'charcoal', 'black', 'gold', 'golden', 'silver', 'bronze', 'steel',
           'scarlet', 'maroon', 'burgundy', 'emerald', 'turquoise', 'cyan', 'azure', 'indigo', 'lavender', 'magenta', 'beige',
           'ivory', 'khaki', 'copper', 'brass', 'blonde', 'blond', 'ginger', 'auburn', 'platinum', 'rust', 'olive'}
# hair colour words in front of 'hair' resolve to hair palette entries
HAIR_COLOUR = {'black': 'hair_black', 'brown': 'hair_brown', 'dark': 'hair_dark', 'blonde': 'hair_blond', 'blond': 'hair_blond',
               'golden': 'hair_blond', 'ginger': 'hair_ginger', 'red': 'hair_ginger', 'auburn': 'hair_auburn', 'white': 'hair_white',
               'grey': 'hair_grey', 'gray': 'hair_grey', 'silver': 'hair_grey', 'platinum': 'hair_platinum', 'blue': 'hair_blue',
               'pink': 'hair_pink', 'green': 'hair_green', 'purple': 'hair_purple'}
FUR_COLOUR = {'orange': 'fur_orange', 'ginger': 'fur_orange', 'brown': 'fur_brown', 'grey': 'fur_grey', 'gray': 'fur_grey',
              'white': 'fur_white', 'black': 'fur_black', 'cream': 'fur_cream', 'red': 'fur_red', 'golden': 'fur_cream'}
SKIN_COLOUR = {'pale': 'porcelain', 'fair': 'fair', 'tan': 'tan_skin', 'tanned': 'tan_skin', 'olive': 'olive', 'brown': 'brown_skin',
               'dark': 'deep', 'green': 'green_skin', 'blue': 'blue_skin', 'grey': 'grey_skin', 'gray': 'grey_skin',
               'gold': 'gold', 'golden': 'gold', 'silver': 'silver', 'bronze': 'bronze', 'steel': 'steel', 'copper': 'bronze'}
UNAVAILABLE = {'wings': 'wings', 'winged': 'wings', 'sword': 'a held sword', 'shield': 'a shield', 'bow': 'a bow', 'gun': 'a gun',
               'spear': 'a spear', 'axe': 'an axe', 'hammer': 'a hammer', 'tentacles': 'tentacles', 'skirt': 'a separate skirt shape',
               'wheelchair': 'a wheelchair', 'horse': 'a mount', 'mask': 'a mask', 'tattoo': 'tattoos', 'tattoos': 'tattoos',
               'earrings': 'earrings', 'necklace': 'a necklace', 'umbrella': 'an umbrella', 'flowers': 'flowers'}
PALETTES = [{'top': 'teal', 'legs': 'navy', 'top2': 'cream', 'boots': 'brown'}, {'top': 'crimson', 'legs': 'charcoal', 'top2': 'gold', 'boots': 'black'},
            {'top': 'forest', 'legs': 'brown', 'top2': 'tan', 'boots': 'brown'}, {'top': 'blue', 'legs': 'grey', 'top2': 'white', 'boots': 'charcoal'},
            {'top': 'orange', 'legs': 'navy', 'top2': 'cream', 'boots': 'brown'}, {'top': 'purple', 'legs': 'black', 'top2': 'silver', 'boots': 'charcoal'}]
HAIRS = ['hair.crop', 'hair.spiky', 'hair.bob', 'hair.ponytail', 'hair.curly', 'hair.long']


def words(text):
    return WORD.findall(text.lower())


def _h(text, salt):
    return int(hashlib.sha256(('%s|%s' % (salt, text)).encode()).hexdigest()[:8], 16)


def read(brief):
    """-> facts read from the brief (literal; no defaults)."""
    w = words(brief)
    ws = set(w)
    f = {'species': None, 'build': None, 'old': bool(ws & OLD), 'tired': bool(ws & TIRED), 'mood': None, 'modules': [],
         'colours': {}, 'outfit': None, 'role': None, 'unavailable': [], 'named': set()}
    f['mood'] = 'smile' if ws & HAPPY else ('frown' if ws & GRUMPY else None)
    for x in w:
        if f['species'] is None and x in SPECIES:
            f['species'] = SPECIES[x]
        if f['build'] is None and x in BUILD:
            f['build'] = BUILD[x]
        if f['role'] is None and x in ROLE:
            f['role'] = x
        if x in UNAVAILABLE and UNAVAILABLE[x] not in f['unavailable']:
            f['unavailable'].append(UNAVAILABLE[x])
    for i, x in enumerate(w):
        nxt = w[i + 1] if i + 1 < len(w) else ''
        prev = w[i - 1] if i else ''
        back = [y for y in w[max(0, i - 3):i] if y not in COLOURS]   # 'long silver hair', 'long white beard'
        if x == 'hair':
            if 'long' in back:
                f['modules'].append('hair.long')
            elif set(back) & {'short', 'cropped'}:
                f['modules'].append('hair.crop')
        if x in HAIR:
            f['modules'].append(HAIR[x])
        if x == 'beard':
            size = {'long': 'beard.long', 'flowing': 'beard.long', 'big': 'beard.long', 'bushy': 'beard.long',
                    'short': 'beard.short', 'small': 'beard.short', 'neat': 'beard.short'}
            f['modules'].append(next((size[y] for y in reversed(back) if y in size), 'beard.short'))
        if x in ('bearded',):
            f['modules'].append('beard.short')
        if x in ('stubble', 'unshaven', 'scruffy'):
            f['modules'].append('beard.stubble')
        if x == 'hat':
            if prev in ('star', 'starry', 'stars', 'starred') or 'star' in ws or 'stars' in ws:
                f['modules'].append('hat.star_wizard')
            elif prev in ('wizard', 'pointy', 'pointed', 'witch', 'witches', 'mage'):
                f['modules'].append('hat.wizard')
            elif prev in ('top',):
                f['modules'].append('hat.top_hat')
            elif prev in ('sun', 'straw', 'baseball'):
                f['modules'].append('hat.cap')
            else:
                f['modules'].append('hat.wizard' if f['role'] in ('wizard', 'witch', 'mage', 'sorcerer') else 'hat.cap')
        if x in HAT:
            f['modules'].append(HAT[x])
        if x in OUTFIT:
            f['outfit'] = OUTFIT[x]
        if x in ACCESSORY and ACCESSORY[x]:
            m = ACCESSORY[x]
            if x in ('cape', 'cloak') and prev in ('short', 'small'):
                m = 'cape.short'
            f['modules'].append(m)
        # colour + noun within 3 words: "green cloak", "a long red cape", "her cloak to green"
        if x in COLOURS:
            for j in range(i + 1, min(len(w), i + 4)):
                if w[j] in NOUN_SLOT:
                    f['colours'][NOUN_SLOT[w[j]]] = x
                    break
            else:
                for j in range(max(0, i - 3), i):
                    if w[j] in NOUN_SLOT and NOUN_SLOT[w[j]] not in f['colours']:
                        f['colours'][NOUN_SLOT[w[j]]] = x
                        break
        if x in ('skinned', 'skin') and prev in SKIN_COLOUR:
            f['colours']['skin'] = prev
    return f


def _module_kind(mid):
    return data()['modules'][mid]['kind']


def draft(brief, variant=0, rid=None):
    d = data()
    f = read(brief)
    species = f['species'] or 'human'
    build = f['build'] or ('stocky' if species == 'dwarf' else 'average')
    if f['old'] and build == 'child':
        build = 'average'
    rid = rid or ('cr_' + hashlib.sha256(brief.encode()).hexdigest()[:8] + '_' + 'abc'[variant])
    rec = new_recipe(rid, species, build, seed=19 + _h(brief, 'seed') % 9973 + variant)
    rec['notes'] = []
    mods = list(rec['modules'])
    named = set(_module_kind(m) for m in f['modules']) | ({'hair'} if 'hair' in f['colours'] else set())
    outfit = f['outfit']
    if f['role']:
        rmods, rcols, rout = ROLE[f['role']]
        for m in rmods:              # a role default never hides what the brief named (a hood over 'long silver hair')
            if _module_kind(m) not in named and not set(d['modules'][m].get('excludes', [])) & named:
                mods.append(m)
        for k, v in rcols.items():
            rec['colours'][k] = v
        outfit = outfit or rout
    if species == 'robot':
        outfit = outfit or 'outfit.panels'
        rec['colours'].setdefault('extra', 'charcoal')
    mods += f['modules']
    if outfit:
        mods.append(outfit)
    if f['old'] and not any(_module_kind(m) == 'hair' for m in f['modules']):
        rec['colours']['hair'] = 'hair_grey' if variant != 2 else 'hair_white'
    # one module per kind; the brief's own words win over species / role defaults (they come later in mods)
    by_kind = {}
    for m in mods:
        by_kind[_module_kind(m)] = m
    if species == 'robot':
        by_kind.pop('hair', None); by_kind.pop('beard', None)
    # variants: change only what the brief leaves open
    if variant >= 1 and 'hair' not in named and species not in ('robot', 'goblin') and not f['old']:
        by_kind['hair'] = HAIRS[(_h(brief, 'hair') + variant) % len(HAIRS)]
    rec['modules'] = sorted(by_kind.values())
    pal_named = set(f['colours'])
    if variant >= 1:
        pal = PALETTES[(_h(brief, 'pal') + variant) % len(PALETTES)]
        for k, v in pal.items():
            if k not in pal_named and not (f['role'] and k in ROLE[f['role']][1]):
                rec['colours'][k] = v
    for slot, word in f['colours'].items():
        if slot == 'hair':
            fam = 'fur' if species in ('cat', 'fox', 'bear', 'rabbit') else 'hair'
            rec['colours']['hair'] = (FUR_COLOUR if fam == 'fur' else HAIR_COLOUR).get(word, rec['colours']['hair'])
            if fam == 'fur':
                rec['colours']['skin'] = rec['colours']['hair']
        elif slot == 'skin':
            if species in ('cat', 'fox', 'bear', 'rabbit'):
                rec['colours']['skin'] = FUR_COLOUR.get(word, rec['colours']['skin'])
                rec['colours']['hair'] = rec['colours']['skin']
            else:
                rec['colours']['skin'] = SKIN_COLOUR.get(word, word)
        elif slot == 'eyes':
            rec['colours']['eyes'] = {'red': 'eye_red', 'blue': 'eye_blue', 'green': 'eye_green', 'brown': 'eye_brown', 'amber': 'eye_amber',
                                      'gold': 'eye_amber', 'golden': 'eye_amber', 'cyan': 'eye_cyan', 'black': 'eye_dark'}.get(word, 'eye_dark')
        else:
            rec['colours'][slot] = word
    if 'hat' in by_kind and 'hat' in f['colours'] and 'hat2' not in f['colours'] and by_kind['hat'] != 'hat.star_wizard':
        pass
    face = rec['face']
    if f['tired'] or (f['old'] and variant == 1):
        face['style'] = 'sleepy'
    elif variant == 2 and species not in ('robot',):
        face['style'] = {'round': 'anime', 'anime': 'dot', 'dot': 'round', 'sleepy': 'sleepy'}.get(face.get('style', 'round'), 'round')
    if f['mood']:
        face['mouth'] = f['mood']
    if variant == 2 and not f['build'] and species in ('human', 'elf', 'cat', 'fox', 'bear', 'rabbit'):
        rec['build'] = ['lean', 'stocky', 'tall', 'bulky'][_h(brief, 'build') % 4]
    if f['unavailable']:
        rec['notes'].append('not available: ' + ', '.join(f['unavailable']))
    rec['brief'] = brief[:400]
    return rec


def propose(brief, n=3):
    """-> n creator recipes; a variant that cannot compile falls back to the literal read with its own id."""
    out = []
    for v in range(n):
        rec = draft(brief, v)
        try:
            compile_recipe(rec)
        except CreatorError as exc:
            lit = draft(brief, 0, rid=rec['id'])
            lit['notes'] = list(lit.get('notes', [])) + ['variant %s fell back to the literal read (%s)' % ('abc'[v], exc)]
            rec = lit
        out.append(rec)
    return out


def needs_creator(brief):
    """True when the words name something only the creator makes (species, star/wizard hats, animal people)."""
    f = read(brief)
    return f['species'] not in (None, 'human') or any(m.startswith(('hat.star', 'hat.wizard', 'ears.', 'horns.')) for m in f['modules'])


__all__ = ['propose', 'draft', 'read', 'needs_creator', 'BODY_ID']
