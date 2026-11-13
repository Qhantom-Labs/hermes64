"""STYLEENGINE-2: what the style engine does not know is said and handed to the agent, never silently made generic.

The agent is the designer (it looks, plans parts, writes a builder script / recipe, or imports a file, and iterates
with previews); the plugin is the style engine (conform + gates + numbers). The composer's 29 forms stay as an
optional accelerator for the things they truly depict.

  assess(words)              -> {'fit': known | near | unknown, 'form', 'head', 'unknown', 'why'}
  placeholder_recipe(...)    -> a clearly marked stand-in (plinth, banded block, cap) that passes every gate; it is
                                reported as "placeholder: needs design" and never presented as the thing
  record(...)                -> the needs_design row: name, the user's words, context, kind guess, budget, builder
                                reference, two worked examples, accepted submission forms and the resume step
  report_lines / cli_lines   -> the "Needs design" section every create report and tool reply leads with
"""
from pathlib import Path
import re

PLUGIN = Path(__file__).resolve().parents[1]
BUILDER_REF = 'skills/hermes64-generators/references/builder-api.md'
GUIDE_REF = 'skills/hermes64-generators/references/art-direction.md'
PLACEHOLDER_MODEL = 'styleengine-placeholder'
DESIGN_MODEL = 'agent-design'
CLAUSE = {'with', 'that', 'which', 'holding', 'carrying', 'wearing', 'having', 'full', 'made', 'where', 'whose'}
FILLER = {'a', 'an', 'the', 'of', 'and', 'on', 'in', 'for', 'to', 'its', 'my', 'some', 'from', 'this', 'at', 'by',
          'very', 'his', 'her', 'their', 'our', 'your', 'one', 'two', 'three', 'four', 'me', 'make', 'game', 'or',
          'into', 'onto', 'near', 'beside', 'under', 'over', 'behind', 'inside', 'outside', 'is', 'are', 'that'}
ADJ = {'old', 'new', 'ancient', 'antique', 'broken', 'dusty', 'worn', 'mossy', 'shiny', 'simple', 'plain', 'ornate',
       'fancy', 'short', 'long', 'wide', 'narrow', 'heavy', 'dark', 'pale', 'strange', 'odd', 'weird', 'spooky',
       'creepy', 'scary', 'cute', 'pretty', 'grand', 'great', 'mighty', 'humble', 'lonely', 'sacred', 'holy', 'secret',
       'hidden', 'lost', 'forgotten', 'rickety', 'sturdy', 'massive', 'majestic', 'elegant', 'rough', 'smooth',
       'sharp', 'round', 'square', 'flat', 'hollow', 'empty', 'full', 'open', 'closed', 'locked', 'cozy', 'warm',
       'cold', 'burning', 'shining', 'sparkling', 'twinkling', 'flickering', 'humming', 'glittering', 'gleaming',
       'standing', 'leaning', 'hanging', 'big', 'small', 'little', 'tall', 'giant', 'huge', 'tiny', 'mini', 'large',
       'steam', 'water', 'gas', 'oil', 'smoke', 'sand', 'dirty', 'clean', 'tidy', 'messy', 'single', 'double',
       'main', 'only', 'other', 'first', 'last', 'top', 'bottom', 'front', 'back', 'side', 'magnificent', 'mysterious'}
COLOURS = {'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'violet', 'pink', 'white', 'black', 'grey', 'gray',
           'brown', 'teal', 'cyan', 'magenta', 'crimson', 'scarlet', 'azure', 'amber', 'emerald', 'turquoise'}
PLACES = {'library', 'castle', 'tower', 'house', 'kitchen', 'garden', 'temple', 'village', 'city', 'town', 'prison',
          'shop', 'church', 'chapel', 'cathedral', 'palace', 'school', 'cellar', 'dungeon', 'tavern', 'inn', 'harbor',
          'harbour', 'station', 'ship', 'train', 'street', 'park', 'market', 'farm', 'mine', 'forest', 'desert',
          'jungle', 'island', 'mountain', 'cave', 'lab', 'laboratory', 'office', 'hospital', 'museum', 'arena',
          'courtyard', 'hall', 'study', 'attic', 'bedroom', 'workshop', 'lighthouse', 'mill', 'bank', 'saloon',
          'sheriff', 'wizard', 'witch', 'king', 'queen', 'captain', 'pirate', 'royal', 'door', 'front'}
ADJ_SUFFIX = ('ous', 'ful', 'less', 'ish', 'ive')
CREATURE_WORDS = {'dragon', 'snake', 'serpent', 'spider', 'horse', 'pony', 'unicorn', 'bird', 'eagle', 'owl', 'crow',
                  'raven', 'blob', 'slime', 'jellyfish', 'octopus', 'squid', 'tentacle', 'tentacles', 'kraken',
                  'worm', 'centipede', 'scorpion', 'crab', 'beetle', 'insect', 'bat', 'wolf', 'bear', 'lion', 'tiger',
                  'fish', 'shark', 'whale', 'eel', 'frog', 'toad', 'lizard', 'turtle', 'dinosaur', 'griffin', 'gryphon',
                  'phoenix', 'hydra', 'golem', 'ghost', 'wisp', 'fairy', 'mermaid', 'deer', 'stag', 'goat', 'cow',
                  'pig', 'sheep', 'rabbit', 'mouse', 'rat', 'monkey', 'ape', 'elephant', 'camel', 'duck', 'chicken',
                  'beast', 'monster', 'creature'}
HUMANOID_OK = {'cat', 'kitten', 'dog', 'puppy', 'robot', 'android', 'droid', 'mech', 'automaton'}


def toks(text):
    return re.findall(r"[a-z][a-z'\-]*", str(text or '').lower())


def _singular(w):
    return w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w


def _maps(data):
    known, near = {}, {}
    for fid, f in data['forms'].items():
        for n in f.get('nouns', []):
            known.setdefault(n, fid)
        for n in f.get('near', []):
            near.setdefault(n, fid)
    return known, near


# states that do not change what a thing is ('a drifting station', 'a swinging pendulum'); 'sailing' is not one
STATE = {'drifting', 'floating', 'swinging', 'spinning', 'turning', 'rotating', 'hovering', 'flying', 'sinking',
         'burning', 'flickering', 'glowing', 'leaning', 'crumbling', 'dripping', 'humming', 'ticking', 'hanging',
         'standing', 'rolling', 'blinking', 'shining', 'smoking', 'steaming', 'bubbling', 'creaking', 'waving',
         'twinkling', 'sleeping', 'waiting', 'abandoned', 'haunted'}


def harmless(w, form, data):
    """A describing word the composer can show or that does not change what the thing is (materials, scale,
    colours, plain adjectives, places/owners, possessives)."""
    s = _singular(w)
    if w in FILLER or w in ADJ or s in ADJ or w in STATE or w in COLOURS or w in PLACES or s in PLACES or w in data['scale']:
        return True
    if any(w in m.get('words', []) for m in data['materials'].values()):
        return True
    if w.endswith("'s") or w.endswith("s'") or w.endswith('ly'):
        return True
    if len(w) > 5 and (w.endswith(ADJ_SUFFIX) or w.endswith('ed')) and not w.endswith('fish'):
        return True
    return w in (data['forms'].get(form) or {}).get('qualifiers', [])


def assess(description, data=None):
    """Does the composer truly depict this? known: the head noun names a form that IS that thing and every describing
    word is one it can show (or does not change the thing); near: the form is only a stand-in (the head is a 'near'
    noun, the form comes from a describing word, or describing words name things it cannot show); unknown: no form."""
    if data is None:
        from .styleengine import load
        data = load()
    words = toks(description)
    cut = next((i for i, w in enumerate(words) if w in CLAUSE and i > 0), len(words))
    main = [w for w in words[:cut] if w not in FILLER]
    extra = [w for w in words[cut + 1:] if w not in FILLER]
    known, near = _maps(data)
    head = main[-1] if main else ''
    hs = _singular(head)
    fid, fit, why, used = None, 'unknown', '', None
    if head in known or hs in known:
        fid, fit = known.get(head) or known[hs], 'known'
    elif head in near or hs in near:
        fid, fit = near.get(head) or near[hs], 'near'
        why = 'the %s form is only a stand-in for a %s' % (fid, head)
    else:
        for w in reversed(main[:-1]):
            s = _singular(w)
            if w in known or s in known or w in near or s in near:
                fid, used = known.get(w) or known.get(s) or near.get(w) or near[s], w
                fit = 'near'
                why = 'no form for "%s"; the closest form (%s) comes from "%s"' % (head, fid, w)
                break
    if fid is None:
        why = 'no form for "%s"' % (head or description)
    unknown = [w for w in main[:-1] + extra if w != used and not harmless(w, fid, data)]
    if fit == 'known' and unknown:
        fit = 'near'
        why = 'the %s form cannot show: %s' % (fid, ', '.join(unknown))
    elif unknown:
        why += '; not shown: %s' % ', '.join(unknown)
    return {'fit': fit, 'form': fid or 'object', 'head': head, 'unknown': unknown, 'why': why}


def identity_unknown(desc_words, data=None):
    """Describing words of the user's phrase that change what a library kind piece is (unknown, not harmless)."""
    if data is None:
        from .styleengine import load
        data = load()
    return [w for w in desc_words if w not in FILLER and not harmless(w, None, data)]


# ------------------------------------------------------------------------------------------------- placeholder
def placeholder_recipe(rid, info, height=None):
    """A clearly marked stand-in: a low plinth, a block at the guessed size with two contrasting bands and a cap
    pyramid. About 50 triangles, closed solids, pack roles only; the report always says "placeholder: needs design"."""
    from .styleengine import CLASS_TRIS
    h = float(height or info.get('height_m') or 0.8)
    cls = info.get('class') if info.get('class') in CLASS_TRIS else 'prop'
    h = max(0.4, min(h, {'prop': 1.5, 'furniture': 4.2, 'furniture_large': 5.6}.get(cls, 8.0)))
    w = round(max(0.3, min(h * 0.45, 2.4)), 3)
    body = round(h * 0.78, 3)
    ops = [{'primitive': 'box', 'role': 'stone', 'args': {'cx': 0, 'cy': 0, 'cz': round(h * 0.03, 4),
                                                         'sx': round(w * 1.3, 4), 'sy': round(w * 1.3, 4),
                                                         'sz': round(h * 0.06, 4)}},
           {'primitive': 'box', 'role': 'body', 'args': {'cx': 0, 'cy': 0, 'cz': round(h * 0.06 + body / 2, 4),
                                                        'sx': w, 'sy': w, 'sz': body}}]
    for z in (0.3, 0.62):
        ops.append({'primitive': 'box', 'role': 'trim', 'args': {'cx': 0, 'cy': 0, 'cz': round(h * 0.06 + body * z, 4),
                                                                'sx': round(w * 1.04, 4), 'sy': round(w * 1.04, 4),
                                                                'sz': round(body * 0.08, 4)}})
    ops.append({'primitive': 'lathe', 'role': 'trim', 'args': {'profile': [[round(w * 0.5, 4), round(h * 0.06 + body, 4)],
                                                                          [0.0, round(h, 4)]], 'segs': 4}})
    return {'format': 'hermes64-recipe/1', 'id': rid, 'class': cls, 'licence': 'CC0-1.0', 'operations': ops}


# --------------------------------------------------------------------------------------------- worked examples
EXAMPLES = {
    'tall': ('tall cabinet (box body, face panel, mirrored feet)',
             "body = box(0.6, 0.45, 1.8, at=(0, 0, 0.9), role='wood')\n"
             "face = box(0.5, 0.02, 0.5, at=(0, -0.235, 1.3), role='screen')\n"
             "feet = mirror(box(0.08, 0.08, 0.1, at=(0.25, -0.17, 0.05), role='metal'), 'x')\n"
             "emit(body, face, feet)"),
    'round': ('lamp-like round piece (lathe profile, emissive core)',
              "stem = lathe([(0.12, 0), (0.12, 0.04), (0.03, 0.08), (0.03, 1.2)], segs=6, role='metal')\n"
              "bell = lathe([(0.0, 1.5), (0.3, 1.45), (0.36, 1.25), (0.2, 1.2)], segs=8, role='glass')\n"
              "core = sphere(0.1, at=(0, 0, 1.32), role='light')\n"
              "emit(stem, bell, core)"),
    'ring': ('wheel / ring structure (torus, spokes by array, legs)',
             "rim = rotate(torus(2.0, 0.08, segs=16, sides=4, role='metal'), 90, 0, 0)\n"
             "spoke = box(0.06, 0.06, 4.0, at=(0, 0, 0), role='metal')\n"
             "spokes = array(spoke, 4, turn=(0, 45, 0))\n"
             "cabins = [box(0.4, 0.4, 0.4, at=(2.0 * cos(a), 0, 2.0 * sin(a)), role='body') for a in [i * pi / 4 for i in range(8)]]\n"
             "emit(move([rim, spokes, cabins], 0, 0, 2.6), mirror(box(0.12, 0.12, 2.8, at=(0.6, 0, 1.4), role='wood'), 'x'))"),
    'gate': ('gate / frame (two posts, two crossbeams, mirrored)',
             "posts = mirror(cylinder(0.14, 2.6, at=(0.9, 0, 0), sides=8, role='wood'), 'x')\n"
             "top = box(2.6, 0.22, 0.18, at=(0, 0, 2.7), role='wood')\n"
             "tie = box(2.1, 0.14, 0.12, at=(0, 0, 2.2), role='trim')\n"
             "emit(posts, top, tie)"),
    'creature': ('creature head / body (blobs, mirrored eyes and horns, tube jaw)',
                 "skull = blob(0.35, 0.5, 0.3, at=(0, 0, 0.4), role='body')\n"
                 "snout = blob(0.22, 0.35, 0.16, at=(0, -0.45, 0.32), role='body')\n"
                 "eyes = mirror(sphere(0.07, at=(0.18, -0.25, 0.5), role='frame'), 'x')\n"
                 "horns = mirror(tube([(0.2, 0.2, 0.6), (0.35, 0.45, 0.85), (0.3, 0.7, 0.95)], 0.05, sides=5, role='trim'), 'x')\n"
                 "emit(skull, snout, eyes, horns)"),
    'vehicle': ('hull + mast + sail (loft rings, cylinder, card)',
                "hull = loft([[(-0.2, -1.2, 0.5), (0.2, -1.2, 0.5), (0, -1.3, 0.2)], [(-0.6, 0, 0.55), (0.6, 0, 0.55), (0, 0, 0)],\n"
                "             [(-0.45, 1.1, 0.6), (0.45, 1.1, 0.6), (0, 1.1, 0.15)]], role='wood')\n"
                "mast = cylinder(0.05, 2.4, at=(0, 0, 0.5), sides=5, role='wood')\n"
                "sail = move(rotate(card(1.2, 1.4, role='fabric'), 0, 0, 90), 0, 0.02, 1.9)\n"
                "emit(hull, mast, sail)"),
    'statue': ('statue (plinth, body blobs, raised head, mirrored legs)',
               "base = box(0.9, 1.4, 0.3, at=(0, 0, 0.15), role='stone')\n"
               "body = blob(0.3, 0.55, 0.3, at=(0, 0, 0.95), role='stone')\n"
               "neck = tube([(0, -0.4, 1.05), (0, -0.55, 1.45)], 0.12, sides=6, role='stone')\n"
               "head = blob(0.14, 0.24, 0.14, at=(0, -0.62, 1.55), role='stone')\n"
               "legs = mirror([cylinder(0.07, 0.5, at=(0.15, y, 0.3), sides=5, role='stone') for y in (-0.35, 0.35)], 'x')\n"
               "emit(base, body, neck, head, legs)"),
    'box': ('boxy appliance (body, screen, buttons by array)',
            "shell = box(0.9, 0.7, 0.7, at=(0, 0, 0.35), role='body_alt')\n"
            "glass = box(0.62, 0.02, 0.46, at=(-0.05, -0.355, 0.38), role='screen')\n"
            "knobs = array(cylinder(0.04, 0.03, at=(0.36, -0.37, 0.5), sides=6, role='metal'), 3, step=(0, 0, -0.1))\n"
            "emit(shell, glass, knobs)"),
}
KIND_EXAMPLES = {'machine': ('tall', 'box'), 'console': ('box', 'tall'), 'container': ('box', 'tall'),
                 'lamp': ('round', 'creature'), 'wheel': ('ring', 'gate'), 'arch': ('gate', 'tall'),
                 'creature': ('creature', 'statue'), 'fish': ('creature', 'round'), 'column': ('statue', 'tall'),
                 'vessel': ('vehicle', 'round'), 'cart': ('vehicle', 'box'), 'tower': ('tall', 'round'),
                 'balloon': ('round', 'vehicle'), 'tree': ('round', 'creature'), 'dome': ('round', 'box'),
                 'pipe': ('round', 'tall'), 'crystal': ('round', 'statue'), 'object': ('box', 'round')}
GUESS_WORDS = (({'clock', 'cabinet', 'wardrobe', 'machine', 'locker', 'fridge', 'booth'}, ('tall', 'box')),
               ({'television', 'tv', 'radio', 'monitor', 'computer', 'microwave', 'oven'}, ('box', 'tall')),
               ({'gate', 'torii', 'frame', 'doorway', 'arch'}, ('gate', 'tall')),
               ({'wheel', 'ring', 'carousel', 'ferris'}, ('ring', 'gate')),
               ({'skull', 'head', 'dragon', 'beast', 'monster', 'jellyfish', 'octopus'}, ('creature', 'round')),
               ({'statue', 'idol', 'figure', 'unicorn', 'horse'}, ('statue', 'creature')),
               ({'ship', 'boat', 'submarine', 'periscope', 'galleon'}, ('vehicle', 'round')),
               ({'lamp', 'lantern', 'light'}, ('round', 'box')))


def examples_for(words, form):
    ws = set(toks(words))
    pick = next((p for keys, p in GUESS_WORDS if ws & keys), None) or KIND_EXAMPLES.get(form) or ('box', 'round')
    return [{'what': EXAMPLES[k][0], 'script': EXAMPLES[k][1]} for k in pick]


# ------------------------------------------------------------------------------------------------------ records
def record(want, words, info, *, named, project=None, pack=None, role='prop', design_id=None, placeholder=None,
           library_closest=None):
    """The needs_design row (create flow and make). Room numbers are filled in after the rooms stage."""
    from .styleengine import CLASS_TRIS
    cls = info.get('class') or 'prop'
    rid = design_id or ('ff_' + re.sub(r'[^a-z0-9_]', '', '_'.join(toks(want))[:40]))
    guess = None
    if info.get('form') and info['form'] != 'object':
        guess = {'form': info['form'], 'class': cls, 'height_m': info.get('height_m'), 'used_as': 'size and kind hint only'}
    proj = project or '<project>'
    rec = {'id': rid, 'name': want, 'user_words': words, 'named_by_user': bool(named),
           'context': {'role': role, 'room': None, 'pack': pack}, 'fit': info.get('fit'), 'why': info.get('why'),
           'kind_guess': guess, 'library_closest': library_closest,
           'budget': {'piece_tris': CLASS_TRIS.get(cls, 300), 'class': cls, 'room_left': None},
           'builder_reference': str(PLUGIN / BUILDER_REF), 'art_direction': str(PLUGIN / GUIDE_REF),
           'examples': examples_for(words or want, info.get('form')),
           'submit': {'builder_script': 'hermes64_character action=make project=%s recipe=<your .py in the project> id=%s render=true' % (proj, rid),
                      'recipe_json': 'hermes64_character action=make project=%s recipe=<your .json in the project> id=%s render=true' % (proj, rid),
                      'your_file': 'hermes64_character action=import project=%s glb=<.glb/.obj in the project> brief="<what it is>, my own model, CC0-1.0" id=%s' % (proj, rid)},
           'then': 'resume the game: python3 -B -m adventure_maker.create_flow run --name %s (assets and rooms run again; '
                   'the placeholder is replaced in place)' % proj,
           'status': 'placeholder in the game' if placeholder else ('optional: not built (setting suggestion)'
                                                                    if not named else 'not built')}
    if placeholder:
        rec['placeholder'] = placeholder
    if role == 'character':
        rec['submit'] = {'humanoid': 'hermes64_character action=propose project=%s brief="<a person or robot>"' % proj,
                         'creature_as_prop': rec['submit']['builder_script'],
                         'rigs': 'human16_v1 (people, robots), quad16_v1 (cat, dog), dasher16_v1 / warden15_v1 (two enemy creatures)'}
        rec['then'] = ('a creature with no rig for it: build it as a static prop with a builder script (no animation in '
                       'this runtime); a person or robot: propose/build/bind it; then resume the game')
    return rec


def character_records(brief, protagonist, pack=None, project=None, made=()):
    """Characters the creator64 bodies cannot be (a dragon, a jellyfish, a lantern-fish shopkeeper): the public cast
    or the closest body stands in, so each one is a needs_design row (computed at report time; the game files are
    unchanged). MERGEPREP-2: `made` holds the texts of characters the character creator built (hero, host); a
    creature word the creator has a species for, said in one of them, is that built character, not a row."""
    out = []
    for c in brief.get('characters', []):
        ws = set(toks(c.get('want', '')))
        ws |= {_singular(w) for w in ws}
        animal = ws & CREATURE_WORDS
        if animal and made:
            from .charcreator.propose import SPECIES
            built = [set(toks(m)) | {_singular(w) for w in toks(m)} for m in made]
            animal = {w for w in animal if not (w in SPECIES and any(w in b for b in built))}
        if not animal or ws & HUMANOID_OK:
            continue
        info = {'fit': 'unknown', 'form': 'creature', 'class': 'furniture', 'height_m': 1.0,
                'why': 'no creator64 body or rig is a %s (bodies: person, robot, cat/dog, two enemy creatures)'
                       % ', '.join(sorted(animal))}
        rec = record(c['want'], c['want'], info, named=True, project=project, pack=pack, role='character',
                     design_id='ff_' + re.sub(r'[^a-z0-9_]', '', '_'.join(toks(c['want']))[:40]))
        rec['status'] = ('the crafted hero stands in (closest body)' if c.get('role') == 'player'
                         and (protagonist or {}).get('status') == 'crafted' else 'the public cast stands in (placeholder)')
        rec['context']['role'] = 'character (%s)' % (c.get('role') or 'npc')
        out.append(rec)
    return out


def room_context(records, rooms_doc, cap, reserve):
    """Fill each record's room and the triangles left there (from create/rooms.json)."""
    rooms = {r['id']: r for r in rooms_doc.get('rooms', [])}
    for rec in records:
        hit = next((p for p in rooms_doc.get('placed', []) if p.get('want') == rec['name']), None)
        if hit:
            rep = (rooms.get(hit['room']) or {}).get('report') or {}
            used = rep.get('tri_estimate_with_appended', rep.get('tri_estimate'))
            rec['context']['room'] = hit['room']
            if used is not None:
                rec['budget']['room_left'] = int(cap - reserve - used + (hit.get('tris') or 0))
                rec['budget']['room_left_note'] = 'about: room cap %d - reserve %d - pieces now %d + this placeholder' % (
                    cap, reserve, used)
        elif rec.get('placeholder'):
            why = next((n.get('reason') for n in rooms_doc.get('not_placed', []) if n.get('want') == rec['name']), None)
            rec['context']['room'] = 'not placed' + (': %s' % why if why else '')
    return records


def line(rec):
    """One plain line for a report or a tool reply."""
    room = (rec.get('context') or {}).get('room')
    b = rec.get('budget') or {}
    left = b.get('room_left')
    return '%s ("%s"): %s. %s%s; budget %s triangles%s. Submit: %s' % (
        rec['name'], rec.get('user_words') or rec['name'], rec.get('why') or 'not known to the style engine',
        rec.get('status', ''), (' in room %s' % room) if room else '', b.get('piece_tris'),
        (', %s left in the room' % left) if left is not None else '',
        rec['submit'].get('builder_script') or rec['submit'].get('humanoid'))


def report_lines(records, skipped=(), designed=False):
    """The 'Needs design' block (Markdown) a create report leads with."""
    L = ['## Needs design', '']
    if not records:
        return L + ['- nothing open: ' + ('every placeholder was replaced by a design (below); every other thing is a '
                                          'library piece or a form the style engine knows' if designed else
                                          'every thing the prompt names is a library piece or a form the style engine '
                                          'knows'), '']
    L += ['These are NOT made yet. The game holds a marked placeholder for each named thing (never presented as the '
          'thing). Design each yourself: write a builder script (or recipe/GLB), submit it with the line given, look '
          'at the preview, then resume the game.', '']
    L += ['- ' + line(r) for r in records]
    if skipped:
        L += ['', 'Words not treated as things (say if one is a thing): ' + ', '.join(skipped)]
    return L + ['', 'Builder API: `%s`. Art direction: `%s` (skill hermes64-generators). Records: '
                    '`create/needs_design.json`.' % (PLUGIN / BUILDER_REF, PLUGIN / GUIDE_REF), '']


def cli_lines(records):
    """Lines create_flow prints FIRST (and repeats last) so an agent cannot miss them."""
    if not records:
        return []
    named = [r for r in records if r.get('named_by_user')]
    out = ['NEEDS DESIGN (%d): %s. The game holds marked placeholders for %d of them: design each yourself '
           '(builder script, recipe or file), submit with hermes64_character action=make ... id=<id> render=true, '
           'then run create_flow again with --name. Details: the top of CREATE-REPORT.md and create/needs_design.json; '
           'builder API: %s'
           % (len(records), ', '.join('%s [id %s]' % (r['name'], r['id']) for r in records), len(named), PLUGIN / BUILDER_REF)]
    return out
