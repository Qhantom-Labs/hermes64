"""Structured brief for any prompt (contract hermes64-brief/1, `contracts/brief/1.0.0.json`).

A prompt such as "a fantasy game in a wizard purple world" becomes a small, bounded JSON brief: setting, mood,
palette mood, build types, props, characters, genre hints, user-supplied asset slots and franchise/person terms.
The model driving the plugin normally fills the brief; when no model is available, `from_prompt` fills one from
plain keywords (deterministic, same prompt -> same brief) and says which parts were assumed.

Rules this module enforces:
- Every field is bounded. Closed fields take words from the vocabularies below, never free text, so a prompt cannot
  talk the plugin out of the style ("use 4K textures" has no field to land in, and free-text fields refuse it).
- Nothing is silently replaced. Unknown nouns stay as named needs or as `unrecognised` words for the report.
- Franchise or real-person names go into `ip_terms` with a generic stand-in and must not appear in any descriptive
  field, asset id or hub entry: the game gets the generic version.
- Errors are one plain line: a code, the field path and what to do next.

Pure stdlib, no I/O beyond `load`; no network; the prompt is data and is never executed.
"""
import difflib
import json
from pathlib import Path
import re
import sys

from .safety import Fault, fail, relative, strict_json

FORMAT = 'hermes64-brief/1'
CONTRACT = Path(__file__).resolve().parents[1] / 'contracts' / 'brief' / '1.0.0.json'
MAX_PROMPT = 600

# ---------------------------------------------------------------------------------------------------------------
# Closed vocabularies (mirrored in contracts/brief/1.0.0.json; tests/test_brief.py fails if they drift).
GENRES = ('adventure', 'fantasy', 'medieval', 'fairy-tale', 'sci-fi', 'space', 'cyberpunk', 'steampunk',
          'post-apocalypse', 'horror', 'mystery', 'noir', 'western', 'pirate', 'underwater', 'desert', 'volcano',
          'jungle', 'polar', 'ancient', 'samurai', 'viking', 'candy', 'dream', 'cozy', 'modern', 'school', 'sports')
HINTS = ('platformer', 'puzzle', 'racing', 'combat', 'stealth', 'exploration', 'collectathon', 'boss-rush',
         'survival', 'arena', 'magic', 'wizard', 'haunted', 'robot', 'toy', 'mushroom', 'dinosaur', 'dragon',
         'ghost', 'treasure', 'heist', 'farming', 'cooking', 'music')
TIMES = ('dawn', 'morning', 'noon', 'afternoon', 'golden-hour', 'dusk', 'night')
WEATHERS = ('clear', 'cloudy', 'rain', 'storm', 'fog', 'snow', 'wind', 'sandstorm', 'ash', 'underwater', 'none')
SEASONS = ('none', 'spring', 'summer', 'autumn', 'winter')
TONES = ('adventurous', 'cozy', 'mysterious', 'eerie', 'heroic', 'playful', 'whimsical', 'melancholy', 'tense',
         'serene', 'epic', 'gritty', 'hopeful', 'dreamy')
HUES = ('red', 'crimson', 'orange', 'amber', 'gold', 'yellow', 'lime', 'green', 'emerald', 'teal', 'cyan', 'blue',
        'indigo', 'purple', 'violet', 'magenta', 'pink', 'brown', 'tan', 'grey', 'silver', 'white', 'black')
VALUE_KEYS = ('low', 'mid', 'high')
SATURATIONS = ('muted', 'moderate', 'rich')
IMPORTANCE = ('key', 'dressing')
PROP_SOURCES = ('prompt', 'default', 'model', 'user')
ROLES = ('player', 'npc', 'enemy', 'boss', 'companion', 'crowd')
SLOT_KINDS = ('model', 'texture', 'logo', 'image', 'audio', 'character')
SLOT_EXT = {'model': ('glb', 'gltf', 'obj'), 'character': ('glb', 'gltf'), 'texture': ('png', 'jpg', 'jpeg'),
            'logo': ('png', 'jpg', 'jpeg'), 'image': ('png', 'jpg', 'jpeg'), 'audio': ('wav', 'ogg', 'mp3', 'flac')}
IP_KINDS = ('franchise', 'person', 'brand')
FILLED_BY = ('model', 'fallback', 'user')
# Hue word -> family, for neighbour scoring (plan 07 section 3.2 B) and accent picking.
HUE_FAMILY = {'red': 'red', 'crimson': 'red', 'orange': 'orange', 'amber': 'orange', 'gold': 'yellow',
              'yellow': 'yellow', 'lime': 'green', 'green': 'green', 'emerald': 'green', 'teal': 'cyan',
              'cyan': 'cyan', 'blue': 'blue', 'indigo': 'blue', 'purple': 'purple', 'violet': 'purple',
              'magenta': 'magenta', 'pink': 'magenta', 'brown': 'brown', 'tan': 'brown', 'grey': 'neutral',
              'silver': 'neutral', 'white': 'neutral', 'black': 'neutral'}
FAMILY_RING = ('red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'magenta')
COMPLEMENT = {'red': 'teal', 'orange': 'blue', 'yellow': 'violet', 'green': 'magenta', 'cyan': 'orange',
              'blue': 'gold', 'purple': 'gold', 'magenta': 'lime', 'brown': 'teal', 'neutral': 'gold'}
# Lenient spellings the normaliser accepts for closed words (applied before validation).
SYNONYMS = {
    'hue': {'golden': 'gold', 'warm gold': 'gold', 'gray': 'grey', 'navy': 'blue', 'scarlet': 'red', 'ruby': 'red',
            'turquoise': 'teal', 'aqua': 'cyan', 'lavender': 'violet', 'lilac': 'violet', 'mauve': 'purple',
            'plum': 'purple', 'rose': 'pink', 'beige': 'tan', 'sand': 'tan', 'ivory': 'white', 'charcoal': 'black',
            'rust': 'orange', 'copper': 'orange', 'jade': 'green', 'olive': 'green', 'mint': 'green',
            'sapphire': 'blue', 'azure': 'blue', 'fuchsia': 'magenta', 'cream': 'white', 'bronze': 'brown',
            'blood red': 'crimson', 'warm yellow': 'yellow', 'cool blue': 'blue', 'deep purple': 'purple'},
    'time': {'sunrise': 'dawn', 'midday': 'noon', 'sunset': 'dusk', 'twilight': 'dusk', 'evening': 'dusk',
             'golden hour': 'golden-hour', 'midnight': 'night', 'day': 'noon', 'daytime': 'noon'},
    'genre': {'sci fi': 'sci-fi', 'scifi': 'sci-fi', 'science fiction': 'sci-fi', 'cyber': 'cyberpunk',
              'fairy tale': 'fairy-tale', 'fairytale': 'fairy-tale', 'post apocalypse': 'post-apocalypse',
              'post-apocalyptic': 'post-apocalypse', 'postapocalyptic': 'post-apocalypse', 'sport': 'sports'},
    'weather': {'rainy': 'rain', 'stormy': 'storm', 'foggy': 'fog', 'mist': 'fog', 'snowy': 'snow',
                'windy': 'wind', 'sunny': 'clear', 'overcast': 'cloudy'},
    'season': {'fall': 'autumn'},
    'tone': {'cosy': 'cozy', 'spooky': 'eerie', 'creepy': 'eerie', 'whimsy': 'whimsical', 'sad': 'melancholy'},
}

# Text fields refuse words that try to steer quality or override the style (the bible owns those numbers).
STYLE_OVERRIDE = re.compile(
    r'\b(?:\d+(?:\.\d+)?\s*k(?:\s*(?:tris?|triangles?|polys?|polygons?|textures?))?|\d{3,}\s*(?:tris?|triangles?|'
    r'polys?|polygons?|px|pixels?)|[248]k|uhd|texture\s*(?:size|resolution)s?|resolution|photo\s*real\w*|'
    r'hyper\s*real\w*|realistic|ray\s*trac\w*|path\s*trac\w*|pbr|normal\s*maps?|ignore|disregard|override|bypass|'
    r'unlimited)\b', re.I)

ID_RE = re.compile(r'[a-z][a-z0-9_-]{0,47}')
LICENCE_RE = re.compile(r'[A-Za-z0-9.+-]{1,40}')


# ---------------------------------------------------------------------------------------------------------------
# Field specs: ('text', max) ('word', choices) ('int', lo, hi) ('bool',) ('const', v) ('list', spec, max)
# ('obj', {key: (spec, required)}) ('id',) ('licence',)
def _o(fields):
    return ('obj', fields)


ROOM_SCALES = ('small', 'medium', 'large', 'open')   # SCALE: adventure_maker/room_scale.py SCALES (optional word)
TEXT_FIELDS = {'place': 80, 'era': 40, 'scale': 60, 'want': 60, 'character': 80, 'generic': 80, 'term': 60,
               'for': 60, 'credit': 80, 'note': 120, 'unrecognised': 32}
# LONGSTORY-2 ("the only cap we want is the art style"): list sizes and counts below are input-size safety ceilings
# no real prompt reaches (was props 40, characters 16, build types 12, prop count 32, character count 16, assumptions
# 24); text lengths stay (they fit the pixel-font UI). What does not fit a room's triangle budget is placed elsewhere
# or listed as not placed, never refused here.
PROP = _o({'want': (('text', 60), True), 'count': (('int', 1, 64), True), 'importance': (('word', IMPORTANCE), True),
           'source': (('word', PROP_SOURCES), False)})
CHARACTER = _o({'want': (('text', 80), True), 'role': (('word', ROLES), True), 'count': (('int', 1, 64), False)})
SLOT = _o({'slot': (('id',), True), 'kind': (('word', SLOT_KINDS), True), 'for': (('text', 60), True),
           'file': (('text', 200), False), 'licence': (('licence',), False), 'credit': (('text', 80), False),
           'rights_confirmed': (('bool',), False)})
IPTERM = _o({'term': (('text', 60), True), 'kind': (('word', IP_KINDS), True), 'generic': (('text', 80), True)})
SPEC = _o({
    'format': (('const', FORMAT), True),
    'prompt': (('text', MAX_PROMPT), True),
    'filled_by': (('word', FILLED_BY), True),
    'setting': (_o({'genre': (('word', GENRES), True), 'genre_hints': (('list', ('word', GENRES + HINTS), 6), True),
                    'place': (('text', 80), True), 'era': (('text', 40), True), 'scale': (('text', 60), True),
                    'room_scale': (('word', ROOM_SCALES), False)}), True),
    'mood': (_o({'time': (('word', TIMES), True), 'weather': (('word', WEATHERS), True),
                 'season': (('word', SEASONS), True), 'tone': (('word', TONES), True)}), True),
    'palette_mood': (_o({'dominant': (('word', HUES), True), 'support': (('list', ('word', HUES), 3), True),
                         'accent': (('word', HUES), True), 'value_key': (('word', VALUE_KEYS), True),
                         'saturation': (('word', SATURATIONS), True)}), True),
    'build_types': (('list', ('text', 60), 64), True),
    'props': (('list', PROP, 256), True),
    'characters': (('list', CHARACTER, 256), True),
    'sources': (_o({'user_assets': (('list', SLOT, 32), True), 'allow_generate': (('bool',), True)}), True),
    'ip_terms': (('list', IPTERM, 64), True),
    'unrecognised': (('list', ('text', 32), 256), True),
    'assumptions': (('list', ('text', 120), 256), True),
    'tags': (('list', ('text', 40), 256), False),
})


def _err(code, path, message):
    fail(code, 'Brief %s: %s' % (path or 'root', message))


def _check(value, spec, path):
    kind = spec[0]
    if kind == 'obj':
        if not isinstance(value, dict):
            _err('brief_type', path, 'must be an object {...}.')
        for key in value:
            if key not in spec[1]:
                close = difflib.get_close_matches(str(key), list(spec[1]), 1)
                _err('brief_unknown_field', path, 'field %r is not part of hermes64-brief/1%s; remove it (the brief '
                     'has no place for instructions or quality settings).'
                     % (str(key)[:40], ' (did you mean %r?)' % close[0] if close else ''))
        for key, (sub, required) in spec[1].items():
            where = (path + '.' if path else '') + key
            if key not in value:
                if required:
                    _err('brief_missing_field', where, 'is required; add it (see docs/ANY-PROMPT.md).')
                continue
            _check(value[key], sub, where)
    elif kind == 'list':
        if not isinstance(value, list):
            _err('brief_type', path, 'must be a list [...].')
        if len(value) > spec[2]:
            _err('brief_too_many', path, 'has %d entries; keep it to %d.' % (len(value), spec[2]))
        for i, item in enumerate(value):
            _check(item, spec[1], '%s[%d]' % (path, i))
    elif kind == 'text':
        if not isinstance(value, str):
            _err('brief_type', path, 'must be text.')
        if not value.strip():
            _err('brief_empty', path, 'is empty; write a short phrase.')
        if len(value) > spec[1]:
            _err('brief_too_long', path, 'is %d characters; keep it to %d.' % (len(value), spec[1]))
        if any(ord(c) < 32 for c in value):
            _err('brief_type', path, 'contains control characters.')
    elif kind == 'word':
        if not isinstance(value, str) or value not in spec[1]:
            close = difflib.get_close_matches(str(value), spec[1], 3, 0.5) if isinstance(value, str) else []
            _err('brief_word', path, '%r is not an allowed word%s; allowed: %s.'
                 % (str(value)[:40], ' (closest: %s)' % ', '.join(close) if close else '', ', '.join(spec[1])))
    elif kind == 'int':
        if type(value) is not int or not spec[1] <= value <= spec[2]:
            _err('brief_count', path, 'must be a whole number from %d to %d.' % (spec[1], spec[2]))
    elif kind == 'bool':
        if type(value) is not bool:
            _err('brief_type', path, 'must be true or false.')
    elif kind == 'const':
        if value != spec[1]:
            _err('brief_format', path, 'must be %r.' % spec[1])
    elif kind == 'id':
        if not isinstance(value, str) or not ID_RE.fullmatch(value):
            _err('brief_slot', path, 'slot ids are short lowercase names like title_logo (letters, digits, _ or -).')
    elif kind == 'licence':
        if not isinstance(value, str) or not LICENCE_RE.fullmatch(value):
            _err('brief_slot', path, 'licence must be an SPDX id such as CC0-1.0 or CC-BY-4.0, or "unknown".')


def _free_text(brief):
    """(path, text) for every descriptive text field the build steps read (prompt/assumptions excluded)."""
    setting = brief['setting']
    for key in ('place', 'era', 'scale'):
        yield 'setting.' + key, setting[key]
    for i, item in enumerate(brief['build_types']):
        yield 'build_types[%d]' % i, item
    for i, item in enumerate(brief['props']):
        yield 'props[%d].want' % i, item['want']
    for i, item in enumerate(brief['characters']):
        yield 'characters[%d].want' % i, item['want']
    for i, item in enumerate(brief['sources']['user_assets']):
        yield 'sources.user_assets[%d].slot' % i, item['slot']
        yield 'sources.user_assets[%d].for' % i, item['for']
    for i, item in enumerate(brief['unrecognised']):
        yield 'unrecognised[%d]' % i, item


def _mentions(term, value):
    words = re.sub(r'[^a-z0-9]+', ' ', term.lower()).strip()
    hay = ' ' + re.sub(r'[^a-z0-9]+', ' ', value.lower()) + ' '
    return bool(words) and (' ' + words + ' ') in hay


def validate(brief):
    """Strict check of a normalised brief. Returns it unchanged; raises Fault(code, one line) on the first problem."""
    _check(brief, SPEC, '')
    for path, value in _free_text(brief):
        hit = STYLE_OVERRIDE.search(value)
        if hit:
            _err('brief_style_override', path, '%r tries to set quality or override the style; the style bible owns '
                 'triangles, texture sizes and the look. Describe the thing, not the rendering.' % hit.group(0))
    for i, term in enumerate(brief['ip_terms']):
        if _mentions(term['term'], term['generic']):
            _err('brief_ip_leak', 'ip_terms[%d].generic' % i, 'the generic stand-in must not repeat %r.' % term['term'])
        for path, value in _free_text(brief):
            if _mentions(term['term'], value):
                _err('brief_ip_leak', path, 'names %r, which is recorded in ip_terms; use the generic version (%r) '
                     'so the name stays out of asset ids and hub entries.' % (term['term'], term['generic']))
    palette = brief['palette_mood']
    if palette['dominant'] in palette['support']:
        _err('brief_palette', 'palette_mood.support', 'repeats the dominant hue %r.' % palette['dominant'])
    seen = set()
    for i, slot in enumerate(brief['sources']['user_assets']):
        where = 'sources.user_assets[%d]' % i
        if slot['slot'] in seen:
            _err('brief_slot', where + '.slot', 'slot %r is listed twice.' % slot['slot'])
        seen.add(slot['slot'])
        if 'file' in slot:
            try:
                relative(slot['file'])
            except Fault:
                _err('brief_slot', where + '.file', 'must be a path inside the project like assets/user/logo.png '
                     '(no absolute paths, drive letters, backslashes or ..).')
            ext = slot['file'].rsplit('.', 1)[-1].lower() if '.' in slot['file'] else ''
            if ext not in SLOT_EXT[slot['kind']]:
                _err('brief_slot', where + '.file', 'a %s slot takes %s files, not %r.'
                     % (slot['kind'], '/'.join(SLOT_EXT[slot['kind']]), ext or 'no extension'))
    if 'tags' in brief and brief['tags'] != tags(brief):
        _err('brief_tags', 'tags', 'are derived; drop them or run normalise() to recompute.')
    return brief


# ---------------------------------------------------------------------------------------------------------------
def _map(d, key, fn):
    """Apply fn to d[key] only when the key is present (missing fields stay missing for a clear error)."""
    if key in d:
        d[key] = fn(d[key])


def _clean_text(value):
    return ' '.join(value.split()) if isinstance(value, str) else value


def _word(value, group):
    if not isinstance(value, str):
        return value
    w = ' '.join(value.strip().lower().replace('_', ' ').split())
    w = SYNONYMS.get(group, {}).get(w, w)
    return w.replace(' ', '-') if group in ('time', 'genre') and w.replace(' ', '-') in TIMES + GENRES else w


def _dedupe(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def normalise(raw):
    """Lenient cleanup (case, spacing, synonyms, duplicates, optional defaults), derived tags, then validate()."""
    if isinstance(raw, (str, bytes)):
        raw = strict_json(raw)
    if not isinstance(raw, dict):
        fail('brief_type', 'Brief root: must be a JSON object; start from docs/ANY-PROMPT.md or brief.from_prompt().')
    b = json.loads(json.dumps(raw))   # deep copy; never mutate the caller's data
    b.pop('tags', None)
    b.setdefault('format', FORMAT)
    b.setdefault('filled_by', 'model')
    for key in ('build_types', 'props', 'characters', 'ip_terms', 'unrecognised', 'assumptions'):
        b.setdefault(key, [])
    b.setdefault('sources', {})
    if isinstance(b['sources'], dict):
        b['sources'].setdefault('user_assets', [])
        b['sources'].setdefault('allow_generate', True)
    if isinstance(b.get('prompt'), str):
        b['prompt'] = _clean_text(b['prompt'])
    s = b.get('setting')
    if isinstance(s, dict):
        s.setdefault('genre_hints', [])
        _map(s, 'genre', lambda v: _word(v, 'genre'))
        if isinstance(s['genre_hints'], list):
            s['genre_hints'] = _dedupe(_word(h, 'genre') for h in s['genre_hints'])
        for key in ('place', 'era', 'scale'):
            _map(s, key, _clean_text)
        _map(s, 'room_scale', lambda v: _word(v, 'room_scale'))
    m = b.get('mood')
    if isinstance(m, dict):
        m.setdefault('season', 'none')
        for key in ('time', 'weather', 'season', 'tone'):
            _map(m, key, lambda v, g=key: _word(v, g))
    p = b.get('palette_mood')
    if isinstance(p, dict):
        p.setdefault('saturation', 'moderate')
        p.setdefault('support', [])
        for key in ('dominant', 'accent'):
            _map(p, key, lambda v: _word(v, 'hue'))
        if isinstance(p['support'], list):
            p['support'] = [h for h in _dedupe(_word(h, 'hue') for h in p['support']) if h != p.get('dominant')]
        _map(p, 'value_key', lambda v: _word(v, 'value'))
        _map(p, 'saturation', lambda v: _word(v, 'saturation'))
    if isinstance(b['build_types'], list):
        b['build_types'] = _dedupe(_clean_text(x).lower() if isinstance(x, str) else x for x in b['build_types'])
    if isinstance(b['props'], list):
        merged = []
        for item in b['props']:
            if isinstance(item, dict):
                item = dict(item)
                _map(item, 'want', _clean_text)
                item.setdefault('count', 1)
                item['importance'] = _word(item.get('importance', 'dressing'), 'importance')
                same = [x for x in merged if isinstance(x, dict) and isinstance(item.get('want'), str)
                        and isinstance(x.get('want'), str) and x['want'].lower() == item['want'].lower()]
                if same and type(item['count']) is int and type(same[0]['count']) is int:
                    same[0]['count'] = min(64, same[0]['count'] + item['count'])
                    if item['importance'] == 'key':
                        same[0]['importance'] = 'key'
                    continue
            merged.append(item)
        b['props'] = merged
    if isinstance(b['characters'], list):
        chars = []
        for c in b['characters']:
            if isinstance(c, dict):
                c = dict(c)
                _map(c, 'want', _clean_text)
                _map(c, 'role', lambda v: _word(v, 'role'))
            chars.append(c)
        b['characters'] = chars
    if isinstance(b['unrecognised'], list):
        b['unrecognised'] = _dedupe(_clean_text(x).lower() if isinstance(x, str) else x for x in b['unrecognised'])
    _check(b, SPEC, '')
    b['tags'] = tags(b)
    return validate(b)


def tags(brief):
    """Derived, closed-vocabulary tags (used by fixtures, the 20-prompt score and the report)."""
    s, m, p = brief['setting'], brief['mood'], brief['palette_mood']
    out = ['genre:' + s['genre']] + ['hint:' + h for h in s['genre_hints']]
    out += ['time:' + m['time'], 'weather:' + m['weather'], 'tone:' + m['tone']]
    if m['season'] != 'none':
        out.append('season:' + m['season'])
    out += ['hue:' + p['dominant'], 'family:' + HUE_FAMILY[p['dominant']]]
    out += ['support:' + h for h in p['support']]
    out += ['accent:' + p['accent'], 'value:' + p['value_key'], 'saturation:' + p['saturation']]
    return _dedupe(out)


# ---------------------------------------------------------------------------------------------------------------
# Deterministic keyword fallback. Data first, then the filler.
# Per genre: place, era, time, weather, season, tone, (dominant, support, accent, value, saturation),
# build types, props [(want, importance)], characters [(want, role)] (first is the player).
D = {
    'adventure': ('village and its outskirts', 'timeless', 'afternoon', 'clear', 'none', 'adventurous',
                  ('green', ['blue', 'tan'], 'gold', 'mid', 'moderate'), ['village house', 'bridge', 'gate'],
                  [('treasure chest', 'key'), ('signpost', 'dressing'), ('crate', 'dressing'), ('lantern', 'dressing')],
                  [('young adventurer', 'player'), ('village elder', 'npc')]),
    'fantasy': ('enchanted realm', 'medieval-magical', 'dusk', 'clear', 'none', 'mysterious',
                ('purple', ['indigo', 'teal'], 'gold', 'low', 'moderate'), ['tower', 'castle', 'stone arch'],
                [('crystal', 'key'), ('ancient altar', 'key'), ('lantern', 'dressing'), ('rock', 'dressing')],
                [('young hero', 'player'), ('robed sage', 'npc')]),
    'medieval': ('castle town', 'medieval', 'morning', 'clear', 'none', 'heroic',
                 ('tan', ['grey', 'green'], 'red', 'mid', 'moderate'), ['castle', 'village house', 'market stall'],
                 [('banner', 'key'), ('well', 'key'), ('barrel', 'dressing'), ('cart', 'dressing')],
                 [('squire', 'player'), ('knight', 'npc')]),
    'fairy-tale': ('storybook forest', 'once upon a time', 'morning', 'clear', 'spring', 'whimsical',
                   ('green', ['pink', 'blue'], 'gold', 'high', 'moderate'), ['cottage', 'tower', 'bridge'],
                   [('spinning wheel', 'key'), ('mushroom', 'dressing'), ('flower', 'dressing'),
                    ('well', 'dressing')], [('young wanderer', 'player'), ('kind old woman', 'npc')]),
    'sci-fi': ('research outpost', 'far future', 'noon', 'clear', 'none', 'adventurous',
               ('cyan', ['grey', 'blue'], 'orange', 'mid', 'moderate'), ['lab module', 'landing pad', 'antenna tower'],
               [('console', 'key'), ('energy cell', 'key'), ('cargo crate', 'dressing'), ('pipe', 'dressing')],
               [('field engineer', 'player'), ('helper robot', 'companion')]),
    'space': ('orbital station', 'far future', 'night', 'none', 'none', 'serene',
              ('blue', ['indigo', 'silver'], 'orange', 'low', 'moderate'), ['station module', 'airlock', 'observation deck'],
              [('console', 'key'), ('space suit rack', 'dressing'), ('cargo crate', 'dressing'), ('plant pod', 'dressing')],
              [('astronaut', 'player'), ('station robot', 'npc')]),
    'cyberpunk': ('neon city block', 'near future', 'night', 'rain', 'none', 'gritty',
                  ('magenta', ['indigo', 'cyan'], 'yellow', 'low', 'rich'), ['city rooftop', 'alley', 'noodle stall'],
                  [('neon sign', 'key'), ('vending machine', 'dressing'), ('air vent', 'dressing'),
                   ('cable bundle', 'dressing')], [('street runner', 'player'), ('fixer', 'npc')]),
    'steampunk': ('brass sky city', 'alternate victorian', 'afternoon', 'cloudy', 'none', 'adventurous',
                  ('brown', ['orange', 'teal'], 'gold', 'mid', 'moderate'), ['airship dock', 'clock tower', 'workshop'],
                  [('gear machine', 'key'), ('steam pipe', 'dressing'), ('crate', 'dressing'), ('gas lamp', 'dressing')],
                  [('young inventor', 'player'), ('airship captain', 'npc')]),
    'post-apocalypse': ('overgrown ruins', 'after the fall', 'afternoon', 'wind', 'none', 'melancholy',
                        ('tan', ['green', 'grey'], 'orange', 'mid', 'muted'), ['ruined building', 'scrap shelter', 'broken road'],
                        [('scrap pile', 'key'), ('rusted car', 'key'), ('barrel', 'dressing'), ('tire', 'dressing')],
                        [('scavenger', 'player'), ('trader', 'npc')]),
    'horror': ('haunted grounds', 'old', 'night', 'fog', 'none', 'eerie',
               ('indigo', ['grey', 'green'], 'red', 'low', 'muted'), ['old house', 'graveyard gate', 'chapel'],
               [('candle', 'key'), ('gravestone', 'dressing'), ('dead tree', 'dressing'), ('broken chair', 'dressing')],
               [('lost visitor', 'player'), ('ghost', 'enemy')]),
    'mystery': ('quiet manor', 'early modern', 'dusk', 'rain', 'none', 'mysterious',
                ('teal', ['brown', 'grey'], 'gold', 'low', 'muted'), ['manor house', 'study', 'garden maze'],
                [('locked box', 'key'), ('bookshelf', 'dressing'), ('clock', 'dressing'), ('lamp', 'dressing')],
                [('young sleuth', 'player'), ('butler', 'npc')]),
    'noir': ('rain-slick city street', '1940s', 'night', 'rain', 'none', 'tense',
             ('indigo', ['grey', 'teal'], 'amber', 'low', 'muted'), ['detective office', 'street corner', 'jazz club'],
             [('desk', 'key'), ('street lamp', 'key'), ('filing cabinet', 'dressing'), ('telephone', 'dressing')],
             [('private detective', 'player'), ('informant', 'npc')]),
    'western': ('frontier town', 'old west', 'golden-hour', 'clear', 'summer', 'adventurous',
                ('orange', ['tan', 'brown'], 'teal', 'mid', 'moderate'), ['saloon', 'sheriff office', 'water tower'],
                [('wagon', 'key'), ('barrel', 'dressing'), ('hitching post', 'dressing'), ('cactus', 'dressing')],
                [('drifter', 'player'), ('sheriff', 'npc')]),
    'pirate': ('island cove', 'age of sail', 'golden-hour', 'clear', 'summer', 'adventurous',
               ('teal', ['tan', 'blue'], 'gold', 'mid', 'moderate'), ['ship', 'dock', 'beach shack'],
               [('treasure chest', 'key'), ('cannon', 'key'), ('barrel', 'dressing'), ('palm tree', 'dressing')],
               [('young pirate', 'player'), ('pirate captain', 'npc')]),
    'underwater': ('sea floor', 'timeless', 'noon', 'underwater', 'none', 'serene',
                   ('teal', ['blue', 'green'], 'pink', 'mid', 'moderate'), ['dome', 'reef', 'sunken ship'],
                   [('coral', 'key'), ('glowing fish', 'dressing'), ('kelp', 'dressing'), ('shell', 'dressing')],
                   [('diver', 'player'), ('mermaid', 'npc')]),
    'desert': ('dunes and oasis', 'timeless', 'golden-hour', 'clear', 'summer', 'adventurous',
               ('orange', ['tan', 'gold'], 'teal', 'mid', 'moderate'), ['tent camp', 'oasis', 'sandstone ruin'],
               [('camel saddle', 'key'), ('clay pot', 'dressing'), ('rug', 'dressing'), ('palm tree', 'dressing')],
               [('wanderer', 'player'), ('caravan merchant', 'npc')]),
    'volcano': ('volcanic forge', 'timeless', 'dusk', 'ash', 'none', 'epic',
                ('red', ['black', 'orange'], 'gold', 'low', 'rich'), ['forge', 'lava bridge', 'obsidian cave'],
                [('anvil', 'key'), ('lava pool', 'key'), ('ore rock', 'dressing'), ('brazier', 'dressing')],
                [('smith apprentice', 'player'), ('fire spirit', 'enemy')]),
    'jungle': ('jungle ruins', 'ancient', 'morning', 'fog', 'summer', 'adventurous',
               ('green', ['emerald', 'brown'], 'gold', 'mid', 'rich'), ['temple', 'rope bridge', 'waterfall'],
               [('idol', 'key'), ('vine', 'dressing'), ('fern', 'dressing'), ('stone block', 'dressing')],
               [('explorer', 'player'), ('guide', 'npc')]),
    'polar': ('frozen coast', 'timeless', 'noon', 'snow', 'winter', 'serene',
              ('white', ['blue', 'cyan'], 'orange', 'high', 'muted'), ['ice cave', 'cabin', 'research hut'],
              [('ice crystal', 'key'), ('sled', 'dressing'), ('snow drift', 'dressing'), ('lantern', 'dressing')],
              [('expedition member', 'player'), ('penguin', 'npc')]),
    'ancient': ('ancient ruins', 'antiquity', 'noon', 'clear', 'summer', 'epic',
                ('tan', ['white', 'teal'], 'gold', 'high', 'moderate'), ['temple', 'colonnade', 'amphitheatre'],
                [('statue', 'key'), ('urn', 'dressing'), ('broken column', 'dressing'), ('altar', 'dressing')],
                [('young hero', 'player'), ('oracle', 'npc')]),
    'samurai': ('mountain village', 'feudal', 'afternoon', 'clear', 'autumn', 'serene',
                ('red', ['brown', 'green'], 'gold', 'mid', 'moderate'), ['pagoda', 'shrine gate', 'tea house'],
                [('stone lantern', 'key'), ('paper lantern', 'dressing'), ('bamboo', 'dressing'),
                 ('maple tree', 'dressing')], [('wandering swordsman', 'player'), ('village elder', 'npc')]),
    'viking': ('fjord harbour', 'norse age', 'morning', 'snow', 'winter', 'epic',
               ('blue', ['grey', 'brown'], 'red', 'mid', 'muted'), ['longhouse', 'longship', 'watchtower'],
               [('rune stone', 'key'), ('shield rack', 'dressing'), ('barrel', 'dressing'), ('fire pit', 'dressing')],
               [('young raider', 'player'), ('jarl', 'npc')]),
    'candy': ('candy kingdom', 'storybook', 'afternoon', 'clear', 'none', 'playful',
              ('pink', ['cyan', 'yellow'], 'red', 'high', 'moderate'), ['candy castle', 'gingerbread house', 'cookie bridge'],
              [('lollipop tree', 'key'), ('gumdrop', 'dressing'), ('candy cane', 'dressing'), ('cupcake', 'dressing')],
              [('tiny hero', 'player'), ('gingerbread guard', 'npc')]),
    'dream': ('cloud realm', 'timeless', 'dawn', 'clear', 'none', 'dreamy',
              ('violet', ['pink', 'cyan'], 'gold', 'high', 'muted'), ['floating stairs', 'cloud island', 'arch'],
              [('floating door', 'key'), ('cloud puff', 'dressing'), ('star', 'dressing'), ('pillar', 'dressing')],
              [('dreamer', 'player'), ('moon guide', 'npc')]),
    'cozy': ('small town street', 'present', 'morning', 'rain', 'autumn', 'cozy',
             ('orange', ['brown', 'green'], 'teal', 'mid', 'moderate'), ['shop', 'cottage', 'cafe'],
             [('counter', 'key'), ('flower pot', 'dressing'), ('bench', 'dressing'), ('lamp', 'dressing')],
             [('shopkeeper', 'player'), ('neighbour', 'npc')]),
    'modern': ('town centre', 'present', 'afternoon', 'clear', 'none', 'hopeful',
               ('blue', ['grey', 'green'], 'orange', 'mid', 'moderate'), ['apartment block', 'park', 'shop'],
               [('bench', 'key'), ('street lamp', 'dressing'), ('bin', 'dressing'), ('bicycle', 'dressing')],
               [('teenager', 'player'), ('neighbour', 'npc')]),
    'school': ('school building', 'present', 'morning', 'clear', 'none', 'playful',
               ('yellow', ['green', 'blue'], 'red', 'high', 'moderate'), ['classroom', 'gym hall', 'school yard'],
               [('desk', 'key'), ('blackboard', 'key'), ('locker', 'dressing'), ('globe', 'dressing')],
               [('student', 'player'), ('teacher', 'npc')]),
    'sports': ('stadium', 'present', 'noon', 'clear', 'summer', 'heroic',
               ('green', ['white', 'blue'], 'red', 'high', 'moderate'), ['stadium stand', 'field', 'locker room'],
               [('ball', 'key'), ('goal', 'key'), ('scoreboard', 'dressing'), ('bench', 'dressing')],
               [('athlete', 'player'), ('coach', 'npc')]),
}

# Cue words. Phrases first (multiword or hyphenated); weights: genre name 3, strong cue 2, weak cue 1.
GENRE_CUES = {
    'fantasy': {3: ['fantasy'], 2: ['elf', 'elven', 'enchanted', 'sorcery', 'sorcerer', 'spell', 'spells'],
                1: ['magic', 'magical', 'kingdom', 'dragon', 'wizard', 'witch', 'mage', 'goblin', 'troll', 'mushroom']},
    'medieval': {3: ['medieval'], 2: ['knight', 'knights', 'siege', 'castle'], 1: ['king', 'queen', 'village']},
    'fairy-tale': {3: ['fairy tale', 'fairytale', 'storybook'], 2: ['once upon a time', 'princess', 'fairy'],
                   1: ['cottage', 'gingerbread']},
    'sci-fi': {3: ['sci fi', 'scifi', 'science fiction'], 2: ['robot', 'robots', 'alien', 'android', 'laser'],
               1: ['research', 'lab', 'future', 'futuristic', 'planet', 'junkyard']},
    'space': {3: ['space', 'outer space'], 2: ['astronaut', 'orbit', 'orbital', 'starship', 'spaceship', 'galaxy'],
              1: ['station', 'stars', 'moon', 'planet', 'rocket']},
    'cyberpunk': {3: ['cyberpunk', 'cyber'], 2: ['neon', 'hacker', 'megacity'], 1: ['rooftop', 'hologram']},
    'steampunk': {3: ['steampunk'], 2: ['airship', 'clockwork', 'gears', 'brass'], 1: ['inventor', 'steam']},
    'post-apocalypse': {3: ['post apocalypse', 'post apocalyptic', 'postapocalyptic', 'apocalypse',
                            'end of the world'], 2: ['wasteland', 'fallout', 'ruined city', 'after the bombs'],
                        1: ['scavenger', 'overgrown', 'rusty', 'ruined']},
    'horror': {3: ['horror'], 2: ['haunted', 'zombie', 'zombies', 'vampire', 'spooky', 'creepy'],
               1: ['ghost', 'ghosts', 'graveyard', 'skeleton', 'eerie', 'cursed']},
    'mystery': {3: ['mystery'], 2: ['clue', 'clues', 'whodunit', 'manor'], 1: ['detective', 'secret']},
    'noir': {3: ['noir', 'film noir'], 2: ['detective', '1940s', '1930s', 'gangster'], 1: ['jazz', 'private eye']},
    'western': {3: ['western', 'wild west', 'old west'], 2: ['cowboy', 'sheriff', 'saloon', 'outlaw', 'frontier'],
                1: ['ghost town', 'canyon', 'cactus', 'ranch']},
    'pirate': {3: ['pirate', 'pirates'], 2: ['buccaneer', 'shipwreck', 'treasure map'],
               1: ['cove', 'treasure', 'parrot', 'wrecked ship']},
    'underwater': {3: ['underwater', 'undersea', 'under the sea'], 2: ['coral', 'reef', 'mermaid', 'submarine', 'seabed'],
                   1: ['fish', 'ocean floor', 'deep sea']},
    'desert': {3: ['desert'], 2: ['dunes', 'caravan', 'oasis', 'sand dunes'], 1: ['camel', 'sand', 'sandstorm']},
    'volcano': {3: ['volcano', 'volcanic'], 2: ['lava', 'magma', 'eruption'], 1: ['obsidian', 'forge', 'ash']},
    'jungle': {3: ['jungle', 'rainforest'], 2: ['vines', 'tropical'], 1: ['temple', 'waterfall', 'monkey']},
    'polar': {3: ['polar', 'arctic', 'antarctic'], 2: ['glacier', 'tundra', 'igloo'], 1: ['ice', 'penguin', 'frozen']},
    'ancient': {3: ['ancient'], 2: ['pharaoh', 'pyramid', 'colosseum', 'greek', 'roman'], 1: ['ruins', 'temple']},
    'samurai': {3: ['samurai'], 2: ['ninja', 'shogun', 'dojo', 'pagoda'], 1: ['katana', 'shrine', 'bamboo']},
    'viking': {3: ['viking', 'vikings'], 2: ['norse', 'longship', 'fjord', 'longhouse'], 1: ['raider', 'runes']},
    'candy': {3: ['candy'], 2: ['sweets', 'lollipop', 'gumdrop', 'chocolate', 'gingerbread'], 1: ['cake', 'sugar']},
    'dream': {3: ['dream', 'dreamscape'], 2: ['surreal', 'clouds'], 1: ['floating', 'pastel', 'stairs']},
    'cozy': {3: ['cozy', 'cosy'], 2: ['bakery', 'cafe', 'tea shop'], 1: ['shop', 'rainy street']},
    'modern': {3: ['modern', 'present day'], 2: ['suburb', 'apartment', 'skateboard'], 1: ['city', 'town']},
    'school': {3: ['school'], 2: ['classroom', 'science fair', 'campus'], 1: ['student', 'teacher']},
    'sports': {3: ['sports', 'sport'], 2: ['volleyball', 'football', 'soccer', 'basketball', 'tennis', 'golf',
                                         'baseball', 'tournament', 'stadium', 'race track'], 1: ['match', 'team', 'ball']},
}
HINT_CUES = {'wizard': ['wizard', 'wizards', 'mage', 'sorcerer', 'witch'], 'magic': ['magic', 'magical', 'spell',
             'spells', 'enchanted', 'arcane'], 'haunted': ['haunted', 'cursed'], 'robot': ['robot', 'robots', 'android'],
             'toy': ['toy', 'toys', 'toy sized'], 'mushroom': ['mushroom', 'mushrooms'], 'dragon': ['dragon', 'dragons'],
             'ghost': ['ghost', 'ghosts', 'ghost town'], 'treasure': ['treasure', 'treasure map'],
             'dinosaur': ['dinosaur', 'dinosaurs'], 'racing': ['race', 'racing', 'race track', 'kart'],
             'platformer': ['platformer', 'jump', 'jumping'], 'puzzle': ['puzzle', 'puzzles'],
             'stealth': ['stealth', 'sneak'], 'heist': ['heist'], 'combat': ['battle', 'fight', 'siege', 'combat'],
             'survival': ['survive', 'survival'], 'farming': ['farm', 'farming'], 'cooking': ['bakery', 'cooking', 'chef'],
             'music': ['music', 'band', 'concert'], 'exploration': ['explore', 'exploration', 'expedition'],
             'arena': ['arena', 'tournament'], 'collectathon': ['collect', 'collecting'],
             'boss-rush': ['boss rush']}
TIME_CUES = {'dawn': ['dawn', 'sunrise', 'daybreak'], 'morning': ['morning'], 'noon': ['noon', 'midday', 'high noon'],
             'afternoon': ['afternoon'], 'golden-hour': ['golden hour'], 'dusk': ['dusk', 'sunset', 'twilight',
             'evening'], 'night': ['night', 'midnight', 'nighttime', 'moonlit', 'starry']}
WEATHER_CUES = {'rain': ['rain', 'rainy', 'raining', 'drizzle'], 'storm': ['storm', 'stormy', 'thunder', 'lightning',
                'thunderstorm'], 'fog': ['fog', 'foggy', 'mist', 'misty'], 'snow': ['snow', 'snowy', 'blizzard', 'snowfall'],
                'wind': ['wind', 'windy', 'gale'], 'sandstorm': ['sandstorm'], 'ash': ['ash', 'ashen', 'smoky'],
                'clear': ['sunny', 'clear sky'], 'cloudy': ['cloudy', 'overcast'],
                'underwater': ['underwater', 'undersea', 'under the sea']}
SEASON_CUES = {'spring': ['spring', 'blossom', 'blossoms'], 'summer': ['summer'], 'autumn': ['autumn', 'autumnal'],
               'winter': ['winter', 'frozen', 'icy', 'wintry']}
TONE_CUES = {'cozy': ['cozy', 'cosy', 'warm', 'homely'], 'mysterious': ['mysterious', 'mystery', 'arcane', 'secret'],
             'eerie': ['eerie', 'haunted', 'spooky', 'creepy', 'cursed', 'horror'], 'heroic': ['heroic', 'hero', 'siege'],
             'playful': ['playful', 'silly', 'toy', 'fun'], 'whimsical': ['whimsical', 'enchanted', 'fairy tale'],
             'melancholy': ['melancholy', 'lonely', 'forgotten', 'abandoned'], 'tense': ['tense', 'danger', 'chase'],
             'serene': ['serene', 'peaceful', 'calm', 'tranquil'], 'epic': ['epic', 'legendary', 'mighty'],
             'gritty': ['gritty', 'grimy', 'rusty'], 'hopeful': ['hopeful', 'bright future'],
             'dreamy': ['dreamy', 'dreamlike']}
VALUE_CUES = {'low': ['dark', 'gloomy', 'shadowy', 'dim'], 'high': ['bright', 'pastel', 'sunny', 'airy']}
SAT_CUES = {'rich': ['neon', 'vivid', 'vibrant', 'colourful', 'colorful', 'glowing'],
            'muted': ['pastel', 'faded', 'muted', 'washed', 'dusty']}
BUILD_CUES = {
    'tower': 'tower', 'castle': 'castle', 'kingdom': 'castle', 'palace': 'palace', 'cottage': 'cottage',
    'house': 'house', 'village': 'village house', 'temple': 'temple', 'shrine': 'shrine', 'lighthouse': 'lighthouse',
    'harbour': 'harbour', 'harbor': 'harbour', 'dock': 'dock', 'pier': 'pier', 'cove': 'cove', 'ship': 'ship',
    'wrecked ship': 'wrecked ship', 'shipwreck': 'wrecked ship', 'dome': 'dome', 'research dome': 'research dome',
    'station': 'station module', 'space station': 'station module', 'greenhouse': 'greenhouse', 'office': 'office',
    'forge': 'forge', 'camp': 'tent camp', 'caravan': 'tent camp', 'rooftop': 'city rooftop', 'junkyard': 'junkyard',
    'factory': 'factory', 'saloon': 'saloon', 'ghost town': 'frontier town', 'town': 'town street', 'city': 'city street',
    'street': 'street', 'bakery': 'bakery', 'shop': 'shop', 'cafe': 'cafe', 'library': 'library', 'school': 'school',
    'classroom': 'classroom', 'stadium': 'stadium', 'arena': 'arena', 'court': 'court', 'beach': 'beach',
    'waterfall': 'waterfall', 'bridge': 'bridge', 'cave': 'cave', 'mine': 'mine', 'garden': 'garden', 'farm': 'farm',
    'airship': 'airship dock', 'airship dock': 'airship dock', 'longhouse': 'longhouse', 'pagoda': 'pagoda',
    'dojo': 'dojo', 'pyramid': 'pyramid', 'ruins': 'ruins', 'ruined city': 'ruined city', 'manor': 'manor house',
    'graveyard': 'graveyard', 'chapel': 'chapel', 'cathedral': 'cathedral', 'church': 'chapel', 'mill': 'mill',
    'windmill': 'windmill', 'igloo': 'igloo', 'cabin': 'cabin', 'tavern': 'tavern', 'inn': 'inn', 'market': 'market',
    'lab': 'lab module', 'laboratory': 'lab module', 'island': 'island', 'floating island': 'floating island',
    'stairs': 'stairs', 'clock tower': 'clock tower', 'gate': 'gate', 'wall': 'wall', 'fortress': 'fortress',
    'reef': 'reef', 'oasis': 'oasis', 'volcano': 'volcano', 'workshop': 'workshop', 'science fair': 'school hall',
    'race track': 'race track', 'park': 'park', 'forest': 'forest', 'jungle': 'jungle clearing', 'mountain': 'mountain',
}
PROP_CUES = {
    'cauldron': 'cauldron', 'potion': 'potion bottle', 'crystal': 'crystal', 'crystal ball': 'crystal ball on a stand',
    'book': 'book', 'spellbook': 'spellbook on a lectern', 'scroll': 'scroll', 'staff': 'wizard staff',
    'wand': 'wand', 'lantern': 'lantern', 'candle': 'candle', 'torch': 'torch', 'chest': 'chest',
    'treasure': 'treasure chest', 'treasure chest': 'treasure chest', 'barrel': 'barrel', 'crate': 'crate',
    'cannon': 'cannon', 'anchor': 'anchor', 'map': 'map', 'treasure map': 'treasure map', 'telescope': 'telescope',
    'orrery': 'orrery', 'portal': 'portal ring', 'altar': 'altar', 'statue': 'statue', 'idol': 'idol',
    'mushroom': 'giant mushroom', 'tree': 'tree', 'glowing tree': 'glowing tree', 'flower': 'flower', 'rock': 'rock',
    'fish': 'fish', 'glowing fish': 'glowing fish', 'coral': 'coral', 'kelp': 'kelp', 'shell': 'shell',
    'lava': 'lava pool', 'lava river': 'lava river', 'anvil': 'anvil', 'cactus': 'cactus', 'wagon': 'wagon',
    'tent': 'tent', 'rug': 'rug', 'camel': 'camel saddle', 'vine': 'vine', 'idol statue': 'idol', 'gear': 'gear machine',
    'pipe': 'steam pipe', 'clock': 'clock', 'sword': 'sword', 'shield': 'shield', 'banner': 'banner', 'flag': 'flag',
    'bread': 'bread loaf', 'oven': 'oven', 'counter': 'counter', 'table': 'table', 'chair': 'chair', 'desk': 'desk',
    'lamp': 'lamp', 'street lamp': 'street lamp', 'telephone': 'telephone', 'typewriter': 'typewriter',
    'neon sign': 'neon sign', 'sign': 'sign', 'vending machine': 'vending machine', 'car': 'car', 'scrap': 'scrap pile',
    'tire': 'tire', 'robot part': 'robot part', 'ball': 'ball', 'net': 'net', 'goal': 'goal', 'trophy': 'trophy',
    'scoreboard': 'scoreboard', 'lollipop': 'lollipop tree', 'gumdrop': 'gumdrop', 'candy cane': 'candy cane',
    'cupcake': 'cupcake', 'cake': 'cake', 'cloud': 'cloud puff', 'door': 'door', 'key': 'key', 'firefly': 'firefly',
    'well': 'well', 'gravestone': 'gravestone', 'coffin': 'coffin', 'bones': 'bones', 'skull': 'skull',
    'rune': 'rune stone', 'rune circle': 'rune circle', 'runes': 'rune stone', 'shield rack': 'shield rack',
    'bamboo': 'bamboo', 'katana': 'katana rack', 'tea set': 'tea set', 'paper lantern': 'paper lantern',
    'palm': 'palm tree', 'palm tree': 'palm tree', 'boat': 'rowing boat', 'plant': 'plant pod', 'console': 'console',
    'computer': 'computer terminal', 'volcano rock': 'ore rock', 'ice': 'ice block', 'sled': 'sled',
    'science project': 'science project table', 'volcano model': 'volcano model', 'egg': 'egg', 'bottle': 'bottle',
    'jar': 'jar', 'bench': 'bench', 'fountain': 'fountain', 'piano': 'piano', 'guitar': 'guitar', 'bicycle': 'bicycle',
}
CHAR_CUES = {
    'wizard': ('old wizard, pointed hat, robe', 'npc'), 'witch': ('witch with a broom', 'npc'),
    'mage': ('young mage', 'npc'), 'sorcerer': ('sorcerer', 'npc'), 'knight': ('knight in armour', 'npc'),
    'king': ('king', 'npc'), 'queen': ('queen', 'npc'), 'princess': ('princess', 'npc'), 'prince': ('prince', 'npc'),
    'pirate': ('pirate crew member', 'npc'), 'captain': ('ship captain', 'npc'), 'samurai': ('samurai', 'npc'),
    'ninja': ('ninja', 'enemy'), 'viking': ('viking warrior', 'npc'), 'robot': ('robot', 'npc'),
    'android': ('android', 'npc'), 'detective': ('private detective', 'player'), 'cowboy': ('cowboy', 'npc'),
    'sheriff': ('sheriff', 'npc'), 'outlaw': ('outlaw', 'enemy'), 'ghost': ('ghost', 'enemy'), 'elf': ('elf', 'npc'),
    'elven': ('elf', 'npc'), 'dwarf': ('dwarf', 'npc'), 'fairy': ('fairy', 'npc'), 'gnome': ('gnome', 'npc'),
    'troll': ('troll', 'enemy'), 'goblin': ('goblin', 'enemy'), 'dragon': ('dragon', 'boss'),
    'zombie': ('zombie', 'enemy'), 'vampire': ('vampire', 'boss'), 'skeleton': ('skeleton', 'enemy'),
    'mermaid': ('mermaid', 'npc'), 'astronaut': ('astronaut', 'player'), 'alien': ('alien', 'npc'),
    'baker': ('baker', 'npc'), 'chef': ('chef', 'npc'), 'student': ('student', 'player'), 'teacher': ('teacher', 'npc'),
    'scientist': ('scientist', 'npc'), 'explorer': ('explorer', 'player'), 'monkey': ('monkey', 'npc'),
    'parrot': ('parrot', 'companion'), 'cat': ('cat', 'companion'), 'dog': ('dog', 'companion'),
    'fox': ('fox', 'npc'), 'owl': ('owl', 'npc'), 'penguin': ('penguin', 'npc'), 'dinosaur': ('dinosaur', 'enemy'),
    'athlete': ('athlete', 'player'), 'player': ('athlete', 'player'), 'monster': ('monster', 'enemy'),
    'firefly': ('firefly swarm', 'crowd'), 'fireflies': ('firefly swarm', 'crowd'), 'villager': ('villager', 'crowd'),
    'soldier': ('soldier', 'enemy'), 'gangster': ('gangster', 'enemy'), 'merchant': ('merchant', 'npc'),
}
# Safety net only: the model is the primary detector of franchise and real-person names (it records them in
# ip_terms). This list catches a few very common ones when no model is available. Name -> (kind, generic, hints).
IP_HINTS = {
    'mario': ('franchise', 'a cheerful jumping hero', ['platformer']),
    'super mario': ('franchise', 'a cheerful jumping hero', ['platformer']),
    'zelda': ('franchise', 'a sword-and-shield adventure', ['exploration']),
    'pokemon': ('franchise', 'friendly collectable creatures', ['collectathon']),
    'pikachu': ('franchise', 'a small electric creature', []),
    'sonic': ('franchise', 'a very fast running hero', ['racing']),
    'minecraft': ('franchise', 'a blocky building world', []),
    'star wars': ('franchise', 'a space opera', []),
    'harry potter': ('franchise', 'a school of magic', ['magic']),
    'hogwarts': ('franchise', 'a castle school of magic', ['magic']),
    'lord of the rings': ('franchise', 'an epic fantasy quest', []),
    'gandalf': ('franchise', 'a wandering grey wizard', ['wizard']),
    'batman': ('franchise', 'a masked night vigilante', []),
    'spider man': ('franchise', 'a wall-climbing masked hero', []),
    'mickey mouse': ('franchise', 'a cheerful cartoon mouse', []),
    'disney': ('brand', 'a classic animated fairy tale', []),
    'marvel': ('brand', 'a superhero team', []),
    'fortnite': ('franchise', 'a colourful battle arena', ['arena']),
    'kirby': ('franchise', 'a round pink puffball hero', ['platformer']),
    'donkey kong': ('franchise', 'a barrel-throwing jungle ape', ['platformer']),
    'banjo kazooie': ('franchise', 'a bear and bird duo', ['collectathon']),
    'nintendo': ('brand', 'a classic home console style', []),
}
IDIOMS = ('fairy tale', 'golden hour', 'ghost town', 'end of the world', 'once upon a time', 'film noir', 'private eye',
          'under the sea', 'high noon', 'toy sized', 'science fair', 'outer space', 'deep sea')
NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
           'ten': 10, 'eleven': 11, 'twelve': 12, 'dozen': 12, 'several': 3, 'many': 6, 'lots': 6}
STOP = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'for', 'and', 'or', 'its', 'his', 'her', 'their', 'my', 'your',
        'at', 'by', 'with', 'from', 'into', 'who', 'that', 'this', 'is', 'are', 'was', 'be', 'as', 'it', 's', 'some',
        'game', 'games', 'world', 'worlds', 'place', 'land', 'lands', 'story', 'adventure', 'level', 'levels', 'make',
        'build', 'create', 'set', 'style', 'theme', 'themed', 'like', 'full', 'where', 'about', 'very', 'lit', 'by',
        'n64', 'nintendo64', 'retro', 'low', 'poly', 'lowpoly', 'please', 'me', 'i', 'want', 'we', 'our', 'above',
        'among', 'below', 'under', 'over', 'near', 'after', 'before', 'during', 'between', 'around', 'inside',
        'outside', 'across', 'through', 'end', 'sized', 'use', 'using', 'instead', 'just', 'only', 'all', 'era', 'age', 'time', 'day', 'area', 'scene', 'zone'}
MODIFIERS = {'glowing', 'rusty', 'ruined', 'overgrown', 'wrecked', 'enchanted', 'haunted', 'frozen', 'tiny', 'giant',
             'big', 'small', 'old', 'ancient', 'abandoned', 'floating', 'toy', 'lost', 'secret', 'hidden', 'magical',
             'magic', 'dark', 'bright', 'little', 'huge', 'sunken', 'burning', 'crumbling', 'misty', 'golden', 'hour',
             'deep', 'high', 'tall', 'long', 'wide', 'empty', 'busy', 'quiet', 'sleepy', 'cursed', 'mighty', 'grand',
             'humble', 'lonely', 'forgotten', 'mysterious', 'cozy', 'cosy', 'peaceful', 'stormy', 'rainy', 'snowy',
             'brass', 'stone', 'wooden', 'iron', 'neon', 'pastel', 'vivid', 'vibrant', 'colourful', 'colorful',
             'sweet', 'fantasy', 'sci', 'fi', 'research', 'wild', 'tropical', 'starry', 'moonlit', 'red', 'orange',
             'new', 'young', 'strange', 'weird', 'shiny', 'spooky', 'creepy', 'eerie', 'epic', 'heroic', 'playful',
             'serene', 'calm', 'gritty', 'dreamy', 'dreamlike', 'surreal', 'warm', 'cold', 'icy', 'gloomy', 'shadowy'}


def _norm_text(prompt):
    text = prompt.lower().replace('\u2019', "'").replace('\u2018', "'")
    return ' ' + re.sub(r'[^a-z0-9]+', ' ', text).strip() + ' '


def _singulars(token):
    out = [token]
    if token.endswith('ies') and len(token) > 4:
        out.append(token[:-3] + 'y')
    if token.endswith('ves') and len(token) > 4:
        out.append(token[:-3] + 'f')
    if token.endswith('es') and token[:-2].endswith(('s', 'x', 'ch', 'sh')):
        out.append(token[:-2])
    if token.endswith('s') and not token.endswith('ss') and len(token) > 3:
        out.append(token[:-1])
    return out


class _Scan:
    """Phrase-aware matcher over the normalised prompt: finds cue phrases, remembers positions and used tokens."""

    def __init__(self, prompt):
        self.text = _norm_text(prompt)
        self.tokens = self.text.split()
        self.used = [False] * len(self.tokens)
        # Idioms: their words must not also count as a prop, character or colour ("fairy tale" is not a fairy,
        # "golden hour" is not gold, "ghost town" has no ghost).
        self.idiom = set()
        for phrase in IDIOMS:
            at = self.find(phrase)
            if at:
                self.idiom.update(range(at[0], at[0] + at[1]))

    def find(self, phrase):
        """Token index of the first match of phrase (singular/plural tolerant on the last word), or None."""
        words = phrase.split()
        n = len(words)
        for i in range(len(self.tokens) - n + 1):
            window = self.tokens[i:i + n]
            if window[:-1] == words[:-1] and words[-1] in _singulars(window[-1]):
                return i, n
        return None

    def cues(self, table, mark=True):
        """[(pos, key, weight)] for a {key: [phrases]} or {key: {weight: [phrases]}} table."""
        hits = []
        for key, phrases in table.items():
            groups = phrases.items() if isinstance(phrases, dict) else [(1, phrases)]
            for weight, items in groups:
                for phrase in items:
                    at = self.find(phrase)
                    if at:
                        hits.append((at[0], key, weight))
                        if mark:
                            for j in range(at[0], at[0] + at[1]):
                                self.used[j] = True
        return sorted(hits)

    def lookup(self, table, skip_idioms=True):
        """[(pos, value, n)] for a {phrase: value} table, longest phrase first so 'crystal ball' beats 'crystal'."""
        hits = []
        taken = [skip_idioms and j in self.idiom for j in range(len(self.tokens))]
        for phrase in sorted(table, key=lambda p: (-len(p.split()), p)):
            words = phrase.split()
            n = len(words)
            for i in range(len(self.tokens) - n + 1):
                window = self.tokens[i:i + n]
                if any(taken[i:i + n]):
                    continue
                if window[:-1] == words[:-1] and words[-1] in _singulars(window[-1]):
                    hits.append((i, table[phrase], n))
                    for j in range(i, i + n):
                        taken[j] = self.used[j] = True
        return sorted(hits)


def _prompt_text(prompt):
    if not isinstance(prompt, str):
        fail('brief_prompt', 'Brief prompt: must be text, e.g. "a fantasy game in a wizard purple world".')
    clean = ''.join(ch for ch in ' '.join(prompt.split()) if ch.isprintable())
    if not clean:
        fail('brief_prompt', 'Brief prompt: is empty; describe the game in one sentence, e.g. "a pirate cove at sunset".')
    if len(clean) > MAX_PROMPT:
        fail('brief_prompt', 'Brief prompt: is %d characters; keep it under %d.' % (len(clean), MAX_PROMPT))
    return clean


def from_prompt(prompt):
    """Deterministic keyword fallback: fill a complete, valid brief from plain words when no model is available.

    It never invents meaning it cannot see: defaults come from the genre table and every default is listed in
    `assumptions`; words it cannot classify are kept in `unrecognised` for the gap report, never replaced.
    """
    prompt = _prompt_text(prompt)
    scan = _Scan(prompt)
    notes = []
    # 1. franchise / person safety net, and quality-override words (both consumed so they reach no field).
    ip_terms, extra_hints = [], []
    for name in sorted(IP_HINTS, key=lambda p: (-len(p.split()), p)):
        words = name.split()
        n = len(words)
        hits = [i for i in range(len(scan.tokens) - n + 1)
                if scan.tokens[i:i + n - 1] == words[:-1] and words[-1] in _singulars(scan.tokens[i + n - 1])]
        fresh = [i for i in hits if not any(scan.used[i:i + n])]
        if fresh and not any(_mentions(name, t['term']) or _mentions(t['term'], name) for t in ip_terms):
            kind, generic, hints = IP_HINTS[name]
            ip_terms.append({'term': name, 'kind': kind, 'generic': generic})
            extra_hints += hints
        if fresh or any(_mentions(name, t['term']) for t in ip_terms):
            for i in hits:                                   # every occurrence, so none leaks into another field
                for j in range(i, i + n):
                    scan.used[j] = True
    if ip_terms:
        notes.append('named %s: using a generic version (%s)' % (', '.join(t['term'] for t in ip_terms),
                                                                  '; '.join(t['generic'] for t in ip_terms)))
    overrides = []
    for i, tok in enumerate(scan.tokens):
        if STYLE_OVERRIDE.fullmatch(tok) or tok in ('textures', 'texture', 'triangles', 'polygons', 'resolution'):
            overrides.append(tok)
            scan.used[i] = True
    if overrides:
        notes.append('ignored quality/override words (%s): the style bible sets those' % ', '.join(_dedupe(overrides)))
    # 2. closed-vocabulary cues.
    votes = {}
    first = {}
    for pos, genre, weight in scan.cues(GENRE_CUES):
        votes[genre] = votes.get(genre, 0) + weight
        first.setdefault(genre, pos)
    hints = _dedupe([h for _, h, _ in scan.cues(HINT_CUES)] + extra_hints)
    times = scan.cues(TIME_CUES)
    weathers = scan.cues(WEATHER_CUES)
    seasons = scan.cues(SEASON_CUES)
    tones = scan.cues(TONE_CUES)
    values = scan.cues(VALUE_CUES)
    sats = scan.cues(SAT_CUES)
    hue_table = {h: h for h in HUES}
    hue_table.update({k: v for k, v in SYNONYMS['hue'].items()})
    hue_hits = [(pos, h) for pos, h, n in scan.lookup(hue_table)]
    # Number words before nouns become counts.
    counts = {}
    for i, tok in enumerate(scan.tokens[:-1]):
        n = NUMBERS.get(tok) or (int(tok) if tok.isdigit() and 0 < int(tok) <= 32 else None)
        if n:
            counts[i + 1] = n
            scan.used[i] = True
    builds = scan.lookup(BUILD_CUES, skip_idioms=False)
    props = scan.lookup(PROP_CUES)
    chars = scan.lookup(CHAR_CUES)
    # 3. genre: most votes, then earliest mention, then table order.
    if votes:
        genre = sorted(votes, key=lambda g: (-votes[g], first[g], GENRES.index(g)))[0]
    else:
        genre = 'adventure'
        notes.append('no genre words: used the general adventure defaults')
    (place, era, time_, weather, season, tone, pal, d_builds, d_props, d_chars) = D[genre]
    hints = [h for h in hints if h != genre][:6]

    def pick(hits, default, label):
        if hits:
            return hits[0][1]
        notes.append('%s: none given, %s default "%s"' % (label, genre, default))
        return default
    time_ = pick(times, time_, 'time')
    weather = pick(weathers, weather, 'weather')
    season = seasons[0][1] if seasons else season
    if weather == 'snow' and season == 'none':
        season = 'winter'
    tone = pick(tones, tone, 'tone')
    dom, support, accent, value, sat = pal
    found_hues = _dedupe(h for _, h in hue_hits)
    if found_hues:
        dom = found_hues[0]
        support = _dedupe(found_hues[1:] + [h for h in support if h not in found_hues])[:3]
        if HUE_FAMILY[accent] == HUE_FAMILY[dom] or accent in found_hues[1:]:
            accent = COMPLEMENT[HUE_FAMILY[dom]]
    else:
        notes.append('palette: no colour words, %s default %s with %s' % (genre, dom, ', '.join(support)))
    support = [h for h in support if h != dom][:3]
    value = values[0][1] if values else value
    if time_ == 'night' and not values:
        value = 'low'
    sat = sats[0][1] if sats else sat
    if any(h[1] == 'rich' for h in sats) and 'neon' in scan.tokens:
        notes.append('neon: kept as rich saturation; the style gates clamp glow and neon, so it will read softer')
    # 4. needs.
    build_types = _dedupe([b for _, b, _ in builds] + list(d_builds))[:12]
    if not builds:
        notes.append('build types: none named, %s defaults' % genre)
    place_out = ' and '.join(_dedupe(b for _, b, _ in builds)[:2]) if builds else place
    prop_rows = []
    for pos, want, n in props:
        count = counts.get(pos, 1)
        prop_rows.append({'want': want, 'count': count, 'importance': 'key', 'source': 'prompt'})
    for want, importance in d_props:
        if not any(r['want'] == want for r in prop_rows):
            prop_rows.append({'want': want, 'count': 1 if importance == 'key' else 3,
                              'importance': 'dressing' if prop_rows and importance == 'key' and len(props) else importance,
                              'source': 'default'})
    char_rows = []
    named = [(want, role) for _, (want, role), _ in chars]
    if not any(role == 'player' for _, role in named):
        char_rows.append({'want': d_chars[0][0], 'role': 'player', 'count': 1})
        notes.append('player: none named, %s default "%s"' % (genre, d_chars[0][0]))
    for want, role in _dedupe(named):
        char_rows.append({'want': want, 'role': role, 'count': 1})
    if len(char_rows) < 2:
        for want, role in d_chars[1:]:
            char_rows.append({'want': want, 'role': role, 'count': 1})
    # 5. leftovers: unknown nouns after a number become key props (the resolver reports them as gaps if nothing
    # matches); other unclassified words are kept for the report, never silently dropped or swapped.
    unrecognised = []
    for i, tok in enumerate(scan.tokens):
        if scan.used[i] or tok in STOP or tok in MODIFIERS or tok.isdigit() or len(tok) < 3:
            continue
        if len(tok) > 32 or STYLE_OVERRIDE.search(tok):
            notes.append('skipped an over-long or quality word')
            continue
        if i in counts:
            forms = _singulars(tok)
            want = forms[1] if len(forms) > 1 else tok
            prop_rows.insert(0, {'want': want, 'count': counts[i], 'importance': 'key', 'source': 'prompt'})
            notes.append('"%s" is not in the keyword lists: kept as a requested piece (gap if nothing matches)' % want)
        else:
            unrecognised.append(tok)
    if unrecognised:
        notes.append('unrecognised words kept for the report: ' + ', '.join(_dedupe(unrecognised)[:16]))
    from .room_scale import keyword
    room_scale, phrase = keyword(prompt)
    if room_scale:
        notes.append('room scale %s from "%s"' % (room_scale, phrase))
    brief = {
        'format': FORMAT, 'prompt': prompt, 'filled_by': 'fallback',
        'setting': {'genre': genre, 'genre_hints': hints, 'place': place_out[:80], 'era': era,
                    'scale': 'small outdoor hub + 2 interiors'},
        'mood': {'time': time_, 'weather': weather, 'season': season, 'tone': tone},
        'palette_mood': {'dominant': dom, 'support': support, 'accent': accent, 'value_key': value, 'saturation': sat},
        'build_types': build_types, 'props': prop_rows[:40], 'characters': char_rows[:16],
        'sources': {'user_assets': [], 'allow_generate': True},
        'ip_terms': ip_terms, 'unrecognised': _dedupe(unrecognised)[:16],
        'assumptions': [n[:120] for n in notes][:24],
    }
    if room_scale:
        brief['setting']['room_scale'] = room_scale
    return normalise(brief)


# ---------------------------------------------------------------------------------------------------------------
def needs(brief):
    """One row per need for the resolver and the gap report (plan 07 sections 2.4 and 2.11). Never drops a need."""
    p, m = brief['palette_mood'], brief['mood']
    rows = [{'label': '%s %s palette, light and fog' % (p['dominant'], m['time']), 'kind': 'palette',
             'importance': 'key', 'count': 1, 'route': 'assets'},
            {'label': '%s sky (%s)' % (m['time'], m['weather']), 'kind': 'sky', 'importance': 'key', 'count': 1,
             'route': 'assets'}]
    rows += [{'label': b, 'kind': 'build', 'importance': 'key', 'count': 1, 'route': 'assets'}
             for b in brief['build_types']]
    rows += [{'label': x['want'], 'kind': 'prop', 'importance': x['importance'], 'count': x['count'],
              'route': 'assets'} for x in brief['props']]
    rows += [{'label': c['want'], 'kind': 'character', 'importance': 'key', 'count': c.get('count', 1),
              'route': 'characters'} for c in brief['characters']]
    for slot in brief['sources']['user_assets']:
        route = {'audio': 'audio', 'character': 'characters'}.get(slot['kind'], 'user')
        rows.append({'label': '%s (%s slot %s)' % (slot['for'], slot['kind'], slot['slot']), 'kind': 'user-asset',
                     'importance': 'key', 'count': 1, 'route': route, 'filled': 'file' in slot})
    rows += [{'label': w, 'kind': 'unrecognised', 'importance': 'dressing', 'count': 1, 'route': 'check'}
             for w in brief['unrecognised']]
    for i, row in enumerate(rows, 1):
        row['id'] = 'need-%02d' % i
    return rows


def summary(brief):
    """One plain line for a reply."""
    s, m, p = brief['setting'], brief['mood'], brief['palette_mood']
    line = '%s: %s; %s, %s, %s; %s%s with %s accent; %d builds, %d props, %d characters' % (
        s['genre'], s['place'], m['time'], m['weather'], m['tone'], p['dominant'],
        (' + ' + ', '.join(p['support'])) if p['support'] else '', p['accent'], len(brief['build_types']),
        len(brief['props']), len(brief['characters']))
    if brief['filled_by'] == 'fallback':
        line += ' (keyword fallback, %d assumptions)' % len(brief['assumptions'])
    if brief['ip_terms']:
        line += '; generic version of ' + ', '.join(t['term'] for t in brief['ip_terms'])
    return line


def load(path):
    """Read and normalise `<project>/brief.json`."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Fault('brief_missing', 'Brief file %s could not be read (%s); write one or use brief.from_prompt().'
                    % (path.name, exc.strerror or 'error')) from None
    try:
        data = strict_json(raw)
    except Fault as exc:
        raise Fault('brief_invalid_json', 'Brief file %s is not valid JSON: %s' % (path.name, exc)) from None
    return normalise(data)


def contract() -> dict:
    """The JSON Schema copy of this contract (documentation and drift test; validate() is the authority)."""
    data = strict_json(CONTRACT.read_bytes())
    assert isinstance(data, dict)
    return data


def main(argv=None):
    """`python -m adventure_maker.brief "<prompt>"` prints a fallback brief; `--check FILE` validates one."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ['--check'] and len(argv) == 2:
            brief = load(argv[1])
            print(summary(brief))
            return 0
        if argv[:1] == ['--needs'] and len(argv) == 2:
            for row in needs(load(argv[1])):
                print('%s  %-12s %-9s %-10s %s' % (row['id'], row['kind'], row['importance'], row['route'], row['label']))
            return 0
        if len(argv) == 1 and not argv[0].startswith('--'):
            print(json.dumps(from_prompt(argv[0]), indent=2, ensure_ascii=False))
            return 0
        print('usage: python -m adventure_maker.brief "<prompt>" | --check brief.json | --needs brief.json',
              file=sys.stderr)
        return 2
    except Fault as exc:
        print('%s: %s' % (exc.code, exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
