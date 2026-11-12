"""The `story` block of a create brief (lane DETAIL): a detailed prompt's people, places, beats, quests, item,
choice, fight, course, win/lose and mechanics, mapped onto the two-room create game.

The agent writes ONE brief file; its optional top-level `story` object is split off by the create flow (the brief
contract stays hermes64-brief/1) and stored as `create/story.json`. Every story part is either made, made as the
closest thing (named), or listed as not applied with the reason and the fix route. Nothing is dropped silently:
`not_applied` rows reach CREATE-REPORT, and names the prompt mentions that the brief and story never use are listed.
Pure stdlib; no I/O except the capability table next to this file.
"""
import copy
import json
import math
from pathlib import Path
import re

FORMAT = 'hermes64-create-story/1'
CAPS = Path(__file__).with_name('create_story.json')
ROLES = ('npc', 'companion', 'rival', 'suspect', 'captive', 'traitor', 'enemy', 'boss')
ACTOR_ROLES = ('npc', 'companion', 'rival', 'suspect', 'captive', 'traitor')
FOE_ROLES = ('enemy', 'boss')
KINDS = ('outdoor', 'indoor')
DONE = ('beat', 'talk', 'item', 'fight', 'course', 'choice', 'end')
CAPACITY = {'entry': {'actors': 4, 'spots': 6}, 'inside': {'actors': 3, 'spots': 4}}
ACTOR_R, SPOT_R = 0.9, 0.7
BOSS_HEALTH, PLAYER_HP_PER_ENEMY, MAX_AT_ONCE = 5, 3, 2
PERSON_TRIS = 760        # a public-cast body is 720-754 triangles; kept free in the room budget per extra person
COMBAT_HINTS = ('combat', 'heist', 'arena', 'boss-rush')
STOP = {'the', 'a', 'an', 'and', 'or', 'but', 'you', 'your', 'he', 'she', 'it', 'his', 'her', 'its', 'they', 'their',
        'make', 'at', 'in', 'on', 'of', 'to', 'for', 'with', 'from', 'by', 'when', 'then', 'there', 'this', 'that',
        'each', 'every', 'no', 'not', 'if', 'as', 'before', 'after', 'first', 'finally', 'keep', 'one', 'two',
        'three', 'four', 'five', 'six', 'is', 'are', 'be', 'old', 'young', 'make', 'create', 'build', 'i', 'we',
        'my', 'our', 'cozy', 'gentle', 'golden', 'dark', 'bright', 'run', 'search', 'talk', 'face', 'explore',
        'inspector', 'professor', 'captain', 'doctor', 'sir', 'lady', 'lord', 'mr', 'mrs', 'miss', 'master', 'saint',
        'king', 'queen', 'prince', 'princess', 'detective', 'officer', 'sergeant', 'mister'}


class StoryError(Exception):
    def __init__(self, code, message, next_step=''):
        super().__init__(message)
        self.code, self.message, self.next_step = code, ' '.join(str(message).split())[:400], next_step


def load_caps(path=None):
    return json.loads(Path(path or CAPS).read_text(encoding='utf-8'))


def split_brief(raw):
    """(brief without `story`, story or None). The brief contract has no story field, so it is taken off first."""
    if not isinstance(raw, dict) or 'story' not in raw:
        return raw, None
    raw = dict(raw)
    return raw, raw.pop('story')


# ------------------------------------------------------------------------------------------------- validation
def _fail(path, msg, nxt='fix that field of the story block and run plan again'):
    raise StoryError('story_field', 'story.%s: %s' % (path, msg), nxt)


def _text(v, path, n, required=True):
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v.strip():
        _fail(path, 'must be a short text')
    v = ' '.join(v.split())
    if len(v) > n:
        _fail(path, 'is %d characters; keep it to %d' % (len(v), n))
    if any(ord(c) < 32 for c in v):
        _fail(path, 'contains control characters')
    return v


def _obj(v, path, fields):
    if not isinstance(v, dict):
        _fail(path, 'must be an object {...}')
    extra = sorted(set(v) - set(fields))
    if extra:
        _fail(path, 'unknown field %r; allowed: %s' % (extra[0], ', '.join(fields)))
    return v


def _list(v, path, n, lo=0):
    if not isinstance(v, list):
        _fail(path, 'must be a list [...]')
    if not lo <= len(v) <= n:
        _fail(path, 'has %d entries; allowed %d to %d' % (len(v), lo, n))
    return v


def slug(text, taken=(), fallback='x'):
    s = re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')[:28] or fallback
    if not s[0].isalpha():
        s = 'p_' + s
    base, i = s, 2
    while s in taken:
        s = '%s_%d' % (base, i)
        i += 1
    return s


def done_ref(v, path):
    """'beat 3' / 'talk Bram' / 'item' / 'fight' / 'course' / 'choice' / 'end' -> (kind, arg)."""
    v = _text(v, path, 60)
    head, _sep, arg = v.partition(' ')
    head = head.lower()
    if head not in DONE:
        _fail(path, '%r must start with one of: %s (e.g. "beat 2", "talk Bram", "item")' % (v, ', '.join(DONE)))
    if head == 'beat':
        if not arg.strip().isdigit():
            _fail(path, '"beat N" needs a beat number, e.g. "beat 2"')
        return 'beat', int(arg)
    if head == 'talk':
        if not arg.strip():
            _fail(path, '"talk NAME" needs a cast name, e.g. "talk Bram"')
        return 'talk', arg.strip()
    return head, None


SPEC_FIELDS = ('title', 'player', 'cast', 'places', 'item', 'beats', 'quests', 'door_lock', 'choice', 'waves', 'course',
               'win', 'lose', 'mechanics', 'rooms', 'keys')
# LONGSTORY: list limits sized for a long story (a brief that names more places than the create flow builds is built
# up to create_long.json max_rooms and the rest are reported as story spots, never refused here).
# LONGSTORY-2 (Dylan: "the only cap we want is the art style"): these are input-size safety ceilings no real prompt
# reaches (a brief file of that size), not game caps. Rooms past create_long.json max_rooms (64, a build safety
# ceiling), people past a room's triangle budget and waves past the at-once budget are built elsewhere or split, and
# every one is reported; nothing here shrinks a story.
MAX_CAST, MAX_PLACES, MAX_BEATS, MAX_QUESTS, MAX_WAVES, MAX_KEYS, MAX_MECHANICS = 256, 256, 256, 256, 64, 64, 64
MAX_ROOMS_FIELD, MAX_WAVE_SIZE = 256, 64


def validate(story, brief=None):
    """Strict check; returns a normalised copy (format added). One-line StoryError naming the field on failure."""
    s = _obj(copy.deepcopy(story), 'root', SPEC_FIELDS + ('format',))
    out = {'format': FORMAT}
    if s.get('title') is not None:
        out['title'] = _text(s['title'], 'title', 60)
    if 'player' in s:
        p = _obj(s['player'], 'player', ('name', 'about'))
        out['player'] = {'name': _text(p.get('name'), 'player.name', 40)}
    names = {}
    out['cast'] = []
    for i, c in enumerate(_list(s.get('cast', []), 'cast', MAX_CAST)):
        c = _obj(c, 'cast[%d]' % i, ('name', 'role', 'place', 'says', 'about'))
        name = _text(c.get('name'), 'cast[%d].name' % i, 40)
        if c.get('role') not in ROLES:
            _fail('cast[%d].role' % i, '%r is not a role; allowed: %s' % (c.get('role'), ', '.join(ROLES)))
        if name.lower() in names:
            _fail('cast[%d].name' % i, '%r is listed twice' % name)
        row = {'name': name, 'role': c['role']}
        for k, n in (('place', 60), ('says', 200)):
            if c.get(k) is not None:
                row[k] = _text(c[k], 'cast[%d].%s' % (i, k), n)
        names[name.lower()] = row
        out['cast'].append(row)
    out['places'] = []
    for i, p in enumerate(_list(s.get('places', []), 'places', MAX_PLACES)):
        p = _obj(p, 'places[%d]' % i, ('name', 'kind', 'about'))
        if p.get('kind') not in KINDS:
            _fail('places[%d].kind' % i, 'must be outdoor or indoor')
        row = {'name': _text(p.get('name'), 'places[%d].name' % i, 40), 'kind': p['kind']}
        if p.get('about') is not None:
            row['about'] = _text(p['about'], 'places[%d].about' % i, 160)
        out['places'].append(row)
    if 'item' in s:
        it = _obj(s['item'], 'item', ('name', 'about', 'place'))
        out['item'] = {'name': _text(it.get('name'), 'item.name', 40)}
        if it.get('about') is not None:
            out['item']['about'] = _text(it['about'], 'item.about', 160)
        if it.get('place') is not None:
            out['item']['place'] = _text(it['place'], 'item.place', 60)
    if s.get('rooms') is not None:
        if type(s['rooms']) is not int or not 1 <= s['rooms'] <= MAX_ROOMS_FIELD:
            _fail('rooms', 'must be a whole number of rooms, e.g. 6 (one room per place; past create_long.json max_rooms '
                           'the rest become story spots, listed in the result)')
        out['rooms'] = s['rooms']
    if s.get('keys') is not None:
        out['keys'] = []
        for i, k in enumerate(_list(s['keys'], 'keys', MAX_KEYS)):
            k = _obj(k, 'keys[%d]' % i, ('name', 'place', 'opens', 'about'))
            row = {'name': _text(k.get('name'), 'keys[%d].name' % i, 40)}
            for f in ('place', 'opens'):
                if k.get(f) is not None:
                    row[f] = _text(k[f], 'keys[%d].%s' % (i, f), 60)
            out['keys'].append(row)
    out['beats'] = []
    for i, b in enumerate(_list(s.get('beats', []), 'beats', MAX_BEATS)):
        b = _obj(b, 'beats[%d]' % i, ('text', 'label', 'place', 'who', 'when'))
        row = {'text': _text(b.get('text'), 'beats[%d].text' % i, 200)}
        for k, n in (('label', 40), ('place', 60), ('who', 40), ('when', 24)):
            if b.get(k) is not None:
                row[k] = _text(b[k], 'beats[%d].%s' % (i, k), n)
        out['beats'].append(row)
    nbeats = len(out['beats'])
    out['quests'] = []
    for i, q in enumerate(_list(s.get('quests', []), 'quests', MAX_QUESTS)):
        q = _obj(q, 'quests[%d]' % i, ('title', 'done_when', 'about'))
        kind, arg = done_ref(q.get('done_when'), 'quests[%d].done_when' % i)
        _check_ref(kind, arg, 'quests[%d].done_when' % i, nbeats, names, s)
        out['quests'].append({'title': _text(q.get('title'), 'quests[%d].title' % i, 60), 'done_when': [kind, arg]})
    if s.get('door_lock') is not None:
        kind, arg = done_ref(s['door_lock'], 'door_lock')
        if kind not in ('beat', 'talk'):
            _fail('door_lock', 'must be "beat N" or "talk NAME"')
        _check_ref(kind, arg, 'door_lock', nbeats, names, s)
        out['door_lock'] = [kind, arg]
    if 'choice' in s:
        ch = _obj(s['choice'], 'choice', ('ask', 'options', 'right', 'who'))
        opts = [_text(o, 'choice.options[%d]' % i, 40) for i, o in enumerate(_list(ch.get('options'), 'choice.options', 4, 2))]
        right = _text(ch.get('right'), 'choice.right', 40)
        if right.lower() not in [o.lower() for o in opts]:
            _fail('choice.right', '%r must be one of the options' % right)
        row = {'ask': _text(ch.get('ask'), 'choice.ask', 120), 'options': opts, 'right': right}
        if ch.get('who') is not None:
            row['who'] = _text(ch['who'], 'choice.who', 40)
        out['choice'] = row
    if 'waves' in s:
        w = _list(s['waves'], 'waves', MAX_WAVES, 1)
        if not all(type(x) is int and 1 <= x <= MAX_WAVE_SIZE for x in w):
            _fail('waves', 'each wave is a whole number of enemies, e.g. [2, 3] (more than fit at once are split and said)')
        out['waves'] = w
    if 'course' in s:
        c = _obj(s['course'], 'course', ('seconds', 'checkpoints'))
        if type(c.get('seconds')) is not int or not 10 <= c['seconds'] <= 600:
            _fail('course.seconds', 'must be a whole number of seconds from 10 to 600')
        cps = [_text(x, 'course.checkpoints[%d]' % i, 40) for i, x in enumerate(_list(c.get('checkpoints', []), 'course.checkpoints', 5, 2))]
        out['course'] = {'seconds': c['seconds'], 'checkpoints': cps}
    for k in ('win', 'lose'):
        if s.get(k) is not None:
            out[k] = _text(s[k], k, 200)
    out['mechanics'] = [_text(m, 'mechanics[%d]' % i, 40).lower() for i, m in enumerate(_list(s.get('mechanics', []), 'mechanics', MAX_MECHANICS))]
    if brief:
        _ip_check(out, brief)
    return out


def _check_ref(kind, arg, path, nbeats, names, s):
    if kind == 'beat' and not 1 <= arg <= nbeats:
        _fail(path, 'beat %d does not exist (the story has %d beats)' % (arg, nbeats))
    if kind == 'talk' and arg.lower() not in names:
        _fail(path, '%r is not a cast name' % arg)
    if kind == 'choice' and 'choice' not in s:
        _fail(path, '"choice" needs a story.choice')
    if kind == 'course' and 'course' not in s:
        _fail(path, '"course" needs a story.course')


def _texts(story):
    out = [story.get('title', ''), story.get('player', {}).get('name', ''), story.get('item', {}).get('name', ''),
           story.get('item', {}).get('about', ''), story.get('win', ''), story.get('lose', '')]
    out += [c['name'] + ' ' + c.get('says', '') for c in story.get('cast', [])]
    out += [p['name'] + ' ' + p.get('about', '') for p in story.get('places', [])]
    out += [b['text'] + ' ' + b.get('label', '') for b in story.get('beats', [])]
    out += [q['title'] for q in story.get('quests', [])]
    if story.get('choice'):
        out += [story['choice']['ask']] + story['choice']['options']
    if story.get('course'):
        out += story['course']['checkpoints']
    return out


def _ip_check(story, brief):
    for t in brief.get('ip_terms', []):
        term = ' %s ' % ' '.join(re.findall(r'[a-z0-9]+', t['term'].lower()))
        for text in _texts(story):
            if term in ' %s ' % ' '.join(re.findall(r'[a-z0-9]+', text.lower())):
                raise StoryError('story_ip_leak', 'story text names %r, which the brief records in ip_terms' % t['term'],
                                 'use the generic version (%s) in the story' % t['generic'])


# ------------------------------------------------------------------------------------------------- mechanics
def mechanic_row(word, caps=None):
    """The capability row for one mechanic word: longest table phrase contained in it wins."""
    caps = caps or load_caps()
    w = ' %s ' % ' '.join(re.findall(r'[a-z0-9/-]+', word.lower()))
    best, size = None, 0
    for row in caps['mechanics']:
        for phrase in row['words']:
            if ' %s ' % phrase in w and len(phrase.split()) > size:
                best, size = row, len(phrase.split())
    if best is None:
        return {'feature': 'mechanic', 'asked': word, 'status': 'not_made', 'reason': 'not in the create capability table',
                'closest': 'none', 'fix': 'hand-author it with the hermes64 tools (skill hermes64-create, When to hand-author)'}
    row = {'feature': 'mechanic', 'asked': word, 'status': best['status'], 'route': best.get('route'),
           'what': best.get('what', ''), 'closest': best.get('closest', ''), 'fix': best.get('fix', '')}
    if best['status'] == 'not_made':
        row['reason'] = 'not supported by the create flow'
    return row


def hints_for(story, hints, caps=None):
    """Brief hints plus the routes the story implies (a fight for foes/waves/boss, a course for course/timed words),
    minus routes the story forbids (no combat / no puzzles). Returns (hints, notes)."""
    hints, notes = list(hints), []
    routes = [mechanic_row(m, caps).get('route') for m in story.get('mechanics', [])]
    foes = [c for c in story.get('cast', []) if c['role'] in FOE_ROLES]
    want_combat = bool(foes or story.get('waves')) or 'combat' in routes
    if '-combat' in routes:
        drop = [h for h in hints if h in COMBAT_HINTS]
        if drop:
            notes.append('the story says no combat, so the routed hint(s) %s were not used' % ', '.join(drop))
        hints = [h for h in hints if h not in COMBAT_HINTS]
    elif want_combat and not set(hints) & set(COMBAT_HINTS):
        hints.append('combat')
    if '-puzzle' in routes:
        hints = [h for h in hints if h != 'puzzle']
    if (story.get('course') or 'racing' in routes) and 'racing' not in hints:
        hints.append('racing')
    return hints, notes


# ------------------------------------------------------------------------------------------------- layout
def _match_place(text, places):
    t = set(re.findall(r'[a-z0-9]+', str(text).lower())) - STOP
    for p in places:
        if t and t & (set(re.findall(r'[a-z0-9]+', p['name'].lower())) - STOP):
            return p
    return None


def room_places(story):
    places = story.get('places', [])
    entry = next((p for p in places if p['kind'] == 'outdoor'), places[0] if places else None)
    inside = next((p for p in places if p['kind'] == 'indoor' and p is not entry), None)
    if inside is None:
        inside = next((p for p in places if p is not entry), None)
    return entry, inside


def _room_of(text, story, entry, inside, default='entry'):
    if not text:
        return default, None
    hit = _match_place(text, [p for p in (entry, inside) if p])
    if hit is not None:
        return ('entry' if hit is entry else 'inside'), None
    other = _match_place(text, story.get('places', []))
    if other is not None:
        return ('entry' if other['kind'] == 'outdoor' else 'inside'), other['name']
    return default, text


def _yaw(spot, centre):
    return round(math.degrees(math.atan2(centre[0] - spot[0], centre[1] - spot[1])) % 360.0 / 15.0) * 15.0


def layout(story, pats, slots_cls, seed=7):
    """Rooms, people and story spots. Deterministic. Returns the plan plus the spots the dresser must keep clear."""
    entry_p, inside_p = room_places(story)
    lay = {'rooms': {'entry': entry_p and entry_p['name'], 'inside': inside_p and inside_p['name']},
           'actors': [], 'beats': [], 'reserve': {'entry': [], 'inside': []}, 'rows': []}
    slots = {rid: slots_cls(dict(pats[rid]), '%s:story' % seed) for rid in ('entry', 'inside')}
    used = {'entry': 0, 'inside': 0}
    taken = {'traveller', 'inhabitant', 'keepsake'}
    for c in story.get('cast', []):
        if c['role'] not in ACTOR_ROLES:
            continue
        cid = slug(c['name'], taken, 'person')
        taken.add(cid)
        if c['role'] == 'captive':
            lay['actors'].append({'cid': cid, 'name': c['name'], 'role': c['role'], 'room': 'inside', 'pos': None, 'captive': True})
            continue
        room, _spot = _room_of(c.get('place'), story, entry_p, inside_p, default=None)
        order = [room] if room else []
        order += [r for r in ('entry', 'inside') if r not in order]
        placed = False
        for rid in order:
            if used[rid] >= CAPACITY[rid]['actors']:
                continue
            pat = pats[rid]
            if used[rid] == 0:
                pos = list(pat['npc_m'])
            else:
                pos = slots[rid].take(ACTOR_R)
                if pos is None:
                    continue
                lay['reserve'][rid].append([pos[0], pos[1], ACTOR_R])
            used[rid] += 1
            lay['actors'].append({'cid': 'inhabitant' if rid == 'entry' and used[rid] == 1 else cid, 'name': c['name'],
                                  'role': c['role'], 'room': rid, 'pos': pos, 'yaw': _yaw(pos, pat['centre_m']),
                                  'moved': room is not None and rid != room})
            placed = True
            break
        if not placed:
            lay['rows'].append({'feature': 'cast', 'asked': '%s (%s)' % (c['name'], c['role']), 'status': 'not_made',
                                'reason': 'no free spot: the entry room holds %d people and the inside room %d' % (
                                    CAPACITY['entry']['actors'], CAPACITY['inside']['actors']),
                                'closest': 'none', 'fix': 'merge minor people, or hand-author a third room'})
        elif lay['actors'][-1].get('moved') and c.get('place'):
            lay['rows'].append({'feature': 'cast', 'asked': '%s in %s' % (c['name'], c['place']), 'status': 'closest',
                                'reason': 'that room was full', 'closest': 'stands in the %s room' % lay['actors'][-1]['room'],
                                'fix': 'move someone else, or hand-author a third room'})
    by_name = {a['name'].lower(): a for a in lay['actors']}
    spots = {'entry': 0, 'inside': 0}
    for k, b in enumerate(story.get('beats', []), 1):
        who = by_name.get(b.get('who', '').lower()) if b.get('who') else None
        if who is not None and not who.get('captive'):
            lay['beats'].append({'k': k, 'room': who['room'], 'pos': None, 'who': who['cid'], 'spot': None})
            continue
        if who is not None and who.get('captive'):
            lay['beats'].append({'k': k, 'room': 'inside', 'pos': None, 'who': who['cid'], 'spot': None, 'captive': True})
            continue
        room, spot = _room_of(b.get('place'), story, entry_p, inside_p)
        order = [room] + [r for r in ('entry', 'inside') if r != room]
        done = False
        for rid in order:
            if spots[rid] >= CAPACITY[rid]['spots']:
                continue
            pos = slots[rid].take(SPOT_R)
            if pos is None:
                continue
            spots[rid] += 1
            lay['reserve'][rid].append([pos[0], pos[1], SPOT_R])
            lay['beats'].append({'k': k, 'room': rid, 'pos': pos, 'who': None, 'spot': spot if rid == room else b.get('place')})
            done = True
            break
        if not done:
            lay['beats'].append({'k': k, 'room': 'entry', 'pos': None, 'who': None, 'spot': None, 'unplaced': True})
            lay['rows'].append({'feature': 'beat', 'asked': 'beat %d: %s' % (k, b['text'][:60]), 'status': 'closest',
                                'reason': 'no free story spot left in either room', 'closest': 'the beat is an action without a spot (menu only)',
                                'fix': 'fewer beats per room, or hand-author a third room'})
        if b.get('who') and who is None:
            lay['rows'].append({'feature': 'beat', 'asked': 'beat %d spoken by %s' % (k, b['who']), 'status': 'closest',
                                'reason': '%s is not a cast person standing in a room' % b['who'], 'closest': 'a story spot with the text',
                                'fix': 'add them to story.cast with a non-fighting role'})
    used_places = {(lay['rooms']['entry'] or '').lower(), (lay['rooms']['inside'] or '').lower()}
    used_places |= {str(b.get('spot') or '').lower() for b in lay['beats']}
    for p in story.get('places', []):
        if p['name'].lower() in used_places:
            continue
        lay['rows'].append({'feature': 'place', 'asked': p['name'], 'status': 'not_made',
                            'reason': 'the create flow builds two rooms (%s, %s) and no beat is set there' % (
                                lay['rooms']['entry'] or 'entry', lay['rooms']['inside'] or 'inside'),
                            'closest': 'none', 'fix': 'set a beat there (it becomes a named story spot), or hand-author a third room'})
    if story.get('keys'):        # LONGSTORY: keys are built in a long story (3+ places); here they are said, not dropped
        lay['rows'].append({'feature': 'keys', 'asked': ', '.join(k['name'] for k in story['keys']), 'status': 'closest',
                            'reason': 'the two-room game has one door', 'closest': 'story.door_lock on the inside door',
                            'fix': 'name 3 or more places (one room each): keys then open the doors they name'})
    lock = story.get('door_lock')
    if lock:
        need = list(range(1, lock[1] + 1)) if lock[0] == 'beat' else []
        bad = [x['k'] for x in lay['beats'] if x['k'] in need and x['room'] != 'entry']
        if lock[0] == 'talk':
            a = by_name.get(lock[1].lower())
            if a is None or a['room'] != 'entry':
                bad = ['talk %s' % lock[1]]
        if bad:
            raise StoryError('story_door_lock', 'door_lock %s %s can never open: %s happen inside the locked room' % (
                lock[0], lock[1], ', '.join(map(str, bad))),
                'set those beats in the entry place (beat.place), or lock on an earlier beat')
    return lay


# ------------------------------------------------------------------------------------------------- apply
def _flag(spec, fid, text):
    if not any(f['id'] == fid for f in spec['flags']):
        spec['flags'].append({'id': fid, 'initial': False, 'description': text[:120] or fid})
        spec['start']['flags'][fid] = False


def _cond(ref, beat_flags, talk_flags, made):
    kind, arg = ref
    if kind == 'beat':
        return [{'flag': beat_flags[arg - 1], 'equals': True}]
    if kind == 'talk':
        return [{'flag': talk_flags[arg.lower()], 'equals': True}] if arg.lower() in talk_flags else None
    if kind == 'item':
        return [{'collected': 'keepsake'}]
    if kind in ('fight', 'course'):
        ch = next((m['challenge'] for m in made if m['module'] == ('combat_arena' if kind == 'fight' else 'timed_course')), None)
        return [{'challenge': ch, 'status': 'completed'}] if ch else None
    if kind == 'choice':
        return [{'flag': 'choice_right', 'equals': True}]
    return [{'flag': 'finished', 'equals': True}]


def apply(spec, story, lay, made, public_cast, rooms_pat):
    """Write the story into the two-room spec. Returns (spec, rows): rows are the not-applied list for this part."""
    spec = copy.deepcopy(spec)
    rows = list(lay['rows'])
    pres = spec['metadata']['presentation']['rooms']
    chars = {c['id']: c for c in spec['characters']}
    rooms = {r['id']: r for r in spec['rooms']}
    if story.get('player'):
        chars['traveller']['name'] = story['player']['name']
    about = {p['name']: p.get('about') for p in story.get('places', [])}
    for rid in ('entry', 'inside'):      # the room text is the place, not the prompt (a prompt is an instruction)
        nm = lay['rooms'][rid]
        if nm:
            rooms[rid]['name'] = nm
            rooms[rid]['description'] = about.get(nm) or '%s.' % nm
    if story.get('title'):
        spec['title'] = story['title']
    # public bodies for extra people: the cast after the player's body, cycled (looks are stand-ins, said elsewhere)
    bodies = list(public_cast[1:]) or list(public_cast)
    template = copy.deepcopy(chars['inhabitant'])
    talk_flags, n_extra = {}, 0

    def person(cid, name):
        nonlocal n_extra
        ch = copy.deepcopy(template)
        ch.update(id=cid, name=name)
        if bodies:
            body = bodies[(n_extra + 1) % len(bodies)]
            ch.update(body_id=body['body_id'], base_rig_id=body['base_rig_id'], params=copy.deepcopy(body['params']))
            ch['role_profiles'] = {k: copy.deepcopy(body['params']) for k in ch['role_profiles']}
        n_extra += 1
        spec['characters'].append(ch)
        chars[cid] = ch
        return ch

    for a in lay['actors']:
        if a.get('captive'):
            continue
        if a['cid'] == 'inhabitant':
            chars['inhabitant']['name'] = a['name']
        else:
            person(a['cid'], a['name'])
            if a['cid'] not in rooms[a['room']]['character_ids']:
                rooms[a['room']]['character_ids'].append(a['cid'])
        if a.get('pos') is not None:
            pres[a['room']].setdefault('characters', {})[a['cid']] = {'position': [a['pos'][0], 0, a['pos'][1]], 'yaw': a['yaw']}
    entry_names = [a['name'] for a in lay['actors'] if a['cid'] == 'inhabitant']
    if not entry_names:            # nobody from the story stands outside: the template's inhabitant leaves
        rooms['entry']['character_ids'] = [c for c in rooms['entry']['character_ids'] if c != 'inhabitant']
        pres['entry'].get('characters', {}).pop('inhabitant', None)
        if not any(a['cid'] == 'inhabitant' for a in lay['actors']):
            spec['characters'] = [c for c in spec['characters'] if c['id'] != 'inhabitant']
    # the item, or the captive as the thing collected
    keep = next(c for c in spec['collectibles'] if c['id'] == 'keepsake')
    captive = next((a for a in lay['actors'] if a.get('captive')), None)
    if captive is not None:
        person(captive['cid'], captive['name'])
        rooms['inside']['character_ids'].append(captive['cid'])
        at = (pres['inside'].get('collectibles') or {}).get('keepsake', {}).get('position') or \
            [rooms_pat['inside']['centre_m'][0], 0, rooms_pat['inside']['centre_m'][1]]
        pres['inside'].setdefault('characters', {})[captive['cid']] = {'position': list(at), 'yaw': 180}
        keep.update(name=captive['name'], label='Free %s' % captive['name'], character=captive['cid'],
                    follower_flag='%s_follows' % captive['cid'], text='%s is free and follows you.' % captive['name'])
        spec['collectible_groups'][0]['name'] = 'Rescued'
        if story.get('item'):
            rows.append({'feature': 'item', 'asked': story['item']['name'], 'status': 'not_made',
                         'reason': 'the captive %s is the one thing collected' % captive['name'], 'closest': 'none',
                         'fix': 'hand-author a second collectible'})
    elif story.get('item'):
        nm = story['item']['name']
        keep.update(name=nm, label='Take the %s' % nm if not nm.lower().startswith('the ') else 'Take %s' % nm,
                    text=story['item'].get('about') or 'You have the %s.' % nm)
        spec['collectible_groups'][0]['name'] = nm
    # people who just talk (no beat spoken by them)
    speaking = {b['who'] for b in lay['beats'] if b.get('who')}
    cast_by = {c['name'].lower(): c for c in story.get('cast', [])}
    for a in lay['actors']:
        if a.get('captive') or a['cid'] in speaking:
            continue
        c = cast_by[a['name'].lower()]
        fid = 'talked_%s' % a['cid']
        _flag(spec, fid, 'Talked to %s' % a['name'])
        spec['interactions'].append({'id': 'talk_%s' % a['cid'], 'room': a['room'], 'kind': 'talk', 'target': a['cid'],
                                     'label': 'Talk to %s' % a['name'], 'text': c.get('says') or '%s nods.' % a['name'],
                                     'conditions': [], 'effects': [{'flag': fid, 'value': True}]})
        talk_flags[a['name'].lower()] = fid
    # beats in order, on a story clock when they say when
    whens = []
    for b in story.get('beats', []):
        if b.get('when') and slug(b['when']) not in [slug(w) for w in whens]:
            whens.append(b['when'])
    if len(whens) >= 2:
        spec['tide'] = {'id': 'story_clock', 'states': [{'id': slug(w, fallback='phase'), 'label': w[:1].upper() + w[1:], 'duration': 3}
                                                        for w in whens], 'wait_label': 'Wait', 'wait_text': 'Time passes.'}
        spec['start']['tide'] = {'state': slug(whens[0], fallback='phase'), 'tick': 0}
    elif len(whens) == 1:
        rows.append({'feature': 'beat timing', 'asked': whens[0], 'status': 'closest', 'reason': 'one time word is not a clock',
                     'closest': 'beats in order', 'fix': 'give two or more beats a `when`'})
    beat_flags = []
    beats = story.get('beats', [])
    for x, b in zip(lay['beats'], beats):
        k = x['k']
        fid = 'beat_%d' % k
        beat_flags.append(fid)
        _flag(spec, fid, b['text'])
        conds = [{'flag': 'beat_%d' % (k - 1), 'equals': True}] if k > 1 else []
        if len(whens) >= 2 and b.get('when'):
            conds.append({'tide': slug(b['when'], fallback='phase')})
        effects = [{'flag': fid, 'value': True}]
        nxt = beats[k].get('when') if k < len(beats) else None
        if len(whens) >= 2 and nxt and slug(nxt) != slug(b.get('when') or ''):
            effects.append({'tide': slug(nxt, fallback='phase')})
        if x.get('who') and not x.get('captive'):
            who_name = chars[x['who']]['name']
            label = b.get('label') or 'Talk to %s' % who_name
            row = {'id': fid, 'room': x['room'], 'kind': 'talk', 'target': x['who'], 'label': label, 'text': b['text'],
                   'conditions': conds, 'effects': effects}
            talk_flags.setdefault(who_name.lower(), fid)
        else:
            spot = x.get('spot') or b.get('place')
            label = b.get('label') or (spot[:1].upper() + spot[1:] if spot else ' '.join(b['text'].split()[:5]) + '...')
            row = {'id': fid, 'room': x['room'], 'kind': 'examine', 'target': fid, 'label': label[:60], 'text': b['text'],
                   'conditions': conds, 'effects': effects}
            if x.get('pos') is not None:
                pres[x['room']].setdefault('interactions', {})[fid] = {'position': [x['pos'][0], 0, x['pos'][1]]}
        spec['interactions'].append(row)
    finish = next(i for i in spec['interactions'] if i['id'] == 'finish')
    if beat_flags:
        finish['conditions'] = list(finish['conditions']) + [{'flag': beat_flags[-1], 'equals': True}]
    # choice: asked after the last beat; right lets you finish, wrong ends the game
    ch = story.get('choice')
    if ch:
        asker = next((a for a in lay['actors'] if ch.get('who') and a['name'].lower() == ch['who'].lower() and not a.get('captive')), None)
        asker = asker or next((a for a in lay['actors'] if a['room'] == 'entry' and not a.get('captive')), None)
        if asker is None:
            rows.append({'feature': 'choice', 'asked': ch['ask'], 'status': 'not_made', 'reason': 'nobody stands in a room to ask it',
                         'closest': 'none', 'fix': 'add a cast person (npc) in the entry room'})
        else:
            _flag(spec, 'choice_right', 'Chose %s' % ch['right'])
            _flag(spec, 'choice_wrong', 'Chose wrongly')
            choices = []
            for i, o in enumerate(ch['options']):
                right = o.lower() == ch['right'].lower()
                choices.append({'id': 'opt_%d' % (i + 1), 'text': o, 'conditions': [],
                                'effects': [{'flag': 'choice_right' if right else 'choice_wrong', 'value': True}], 'next': ''})
            spec['dialogues'].append({'id': 'story_choice', 'character': asker['cid'], 'start_node': 'ask',
                                      'nodes': [{'id': 'ask', 'text': ch['ask'], 'conditions': [], 'choices': choices}]})
            spec['start']['dialogue']['story_choice'] = ''
            spec['interactions'].append({'id': 'ask_choice', 'room': asker['room'], 'kind': 'talk', 'target': asker['cid'],
                                         'label': ch['ask'][:40], 'text': ch['ask'],
                                         'conditions': ([{'flag': beat_flags[-1], 'equals': True}] if beat_flags else []) +
                                         [{'flag': 'choice_right', 'equals': False}, {'flag': 'choice_wrong', 'equals': False}],
                                         'effects': [{'dialogue': 'story_choice', 'node': 'ask'}]})
            finish['conditions'] = list(finish['conditions']) + [{'flag': 'choice_right', 'equals': True}]
            spec['endings'].append({'id': 'wrong_choice', 'conditions': [{'flag': 'choice_wrong', 'equals': True}],
                                    'text': story.get('lose') or 'That was the wrong answer. The story ends here.'})
    if story.get('win'):
        spec['endings'][0]['text'] = story['win']
    if story.get('lose') and not ch:
        rows.append({'feature': 'lose', 'asked': story['lose'][:80], 'status': 'closest' if made else 'not_made',
                     'reason': 'there is no fail ending without a story.choice',
                     'closest': 'a lost fight or course restarts at the checkpoint' if made else 'none',
                     'fix': 'add a story.choice, or hand-author a fail ending'})
    # door lock
    if story.get('door_lock'):
        cond = _cond(story['door_lock'], beat_flags, talk_flags, made)
        if cond:
            for d in rooms['entry']['doors']:
                if d['to_room'] == 'inside':
                    d['conditions'] = list(d['conditions']) + cond
    # quests (journal lines; they never gate anything)
    for i, q in enumerate(story.get('quests', []), 1):
        cond = _cond(q['done_when'], beat_flags, talk_flags, made)
        if cond is None:
            rows.append({'feature': 'quest', 'asked': q['title'], 'status': 'not_made',
                         'reason': 'done_when %s %s is not in this game' % (q['done_when'][0], q['done_when'][1] or ''),
                         'closest': 'none', 'fix': 'point done_when at a beat, a talk or the item'})
            continue
        spec['quests'].append({'id': 'quest_%d' % i, 'title': q['title'], 'description': q['title'], 'conditions': cond})
    spec = _fight_and_course(spec, story, made, rooms_pat, rows)
    return spec, rows


def _fight_and_course(spec, story, made, rooms_pat, rows):
    mods = {m['id']: m for m in (spec.get('gameplay') or {}).get('modules', [])}
    foes = [c for c in story.get('cast', []) if c['role'] in FOE_ROLES]
    combat = mods.get('combat')
    if combat:
        arche = combat['entities']['archetypes'][0]
        enc = combat['entities']['encounters'][0]
        enemy = next((c for c in foes if c['role'] == 'enemy'), None)
        if enemy:
            arche['name'] = enemy['name']
        boss = next((c for c in foes if c['role'] == 'boss'), None)
        asked = story.get('waves') or [len(enc['spawns'])]
        waves = []
        for n in asked:      # at most MAX_AT_ONCE fighters at a time: a wave of 3 measured 6,176 triangles in the room
            while n > 0:
                waves.append(min(n, MAX_AT_ONCE))
                n -= MAX_AT_ONCE
        if waves != asked:
            rows.append({'feature': 'waves', 'asked': str(asked), 'status': 'closest',
                         'reason': 'more than %d fighters at once go over the 6,000-triangle room budget' % MAX_AT_ONCE,
                         'closest': 'the same fighters in waves %s' % waves, 'fix': 'none needed; or keep waves to 2'})
        cx, cz = rooms_pat['inside']['centre_m']
        offs = [(-1.5, -1.0), (1.5, -1.0), (0.0, -1.8)]
        spawns = []
        for w, n in enumerate(waves):
            for j in range(n):
                spawns.append({'id': '%s_%d_%d' % (arche['id'], w + 1, j + 1), 'archetype': arche['id'], 'wave': w,
                               'position_m': [round(cx + offs[j][0], 2), 0, round(cz + offs[j][1], 2)]})
        if boss:
            bid = slug(boss['name'], {arche['id']}, 'boss')
            b = copy.deepcopy(arche)
            b.update(id=bid, name=boss['name'], max_health=BOSS_HEALTH, speed_mps=1.3)
            combat['entities']['archetypes'].append(b)
            spawns.append({'id': '%s_boss' % bid, 'archetype': bid, 'wave': len(waves), 'position_m': [cx, 0, round(cz - 1.8, 2)]})
        enc['spawns'] = spawns
        # the player's health grows with the fight: the stock arena (2 enemies) is balanced for 6
        extra = max(0, sum(waves) - 2) + (BOSS_HEALTH // 2 if boss else 0)
        abil = mods.get('abilities')
        if abil and extra:
            abil['config']['max_health'] = min(64, abil['config']['max_health'] + PLAYER_HP_PER_ENEMY * extra)
        for m in made:
            if m['module'] == 'combat_arena':
                m['enemies'] = [s['id'] for s in spawns]
                m['text'] = 'a fight in the inside room: %s%s, to unlock the item' % (
                    ' then '.join('%d %s' % (n, arche['name']) for n in waves), ', then %s' % boss['name'] if boss else '')
    elif foes and not any(mechanic_row(m).get('route') == '-combat' for m in story.get('mechanics', [])):
        rows.append({'feature': 'cast', 'asked': ', '.join('%s (%s)' % (c['name'], c['role']) for c in foes), 'status': 'not_made',
                     'reason': 'no fight was routed in this game', 'closest': 'none', 'fix': 'add the genre hint combat'})
    course = mods.get('course')
    if course and story.get('course'):
        tr = course['entities']['tracks'][0]
        c = story['course']
        tr['time_limit_ticks'] = c['seconds'] * 60
        tr['par_ticks'] = min(tr['par_ticks'], tr['time_limit_ticks'])
        cx, cz = rooms_pat['entry']['centre_m']
        n = len(c['checkpoints'])
        ids, cps = set(), []
        for i, name in enumerate(c['checkpoints']):
            ang = math.pi / 2 + 2 * math.pi * (i + 1) / (n + 1)
            cid = slug(name, ids, 'checkpoint')
            ids.add(cid)
            cps.append({'id': cid, 'position_m': [round(cx + 1.6 * math.cos(ang), 2), 0, round(cz + 1.6 * math.sin(ang), 2)], 'radius_m': 0.5})
        tr['checkpoints'] = cps
        for m in made:
            if m['module'] == 'timed_course':
                m['text'] = 'a timed course in the entry room: %s, %d s limit' % (', '.join(c['checkpoints']), c['seconds'])
    elif story.get('course') and not course:
        rows.append({'feature': 'course', 'asked': '%d s, %s' % (story['course']['seconds'], ', '.join(story['course']['checkpoints'])),
                     'status': 'not_made', 'reason': 'no timed course was routed', 'closest': 'none', 'fix': 'add the genre hint racing'})
    if story.get('waves') and not combat:
        rows.append({'feature': 'waves', 'asked': str(story['waves']), 'status': 'not_made', 'reason': 'no fight in this game',
                     'closest': 'none', 'fix': 'add the genre hint combat'})
    return spec


# ------------------------------------------------------------------------------------------------- rows
def mechanic_rows(story, caps=None):
    out = []
    for m in story.get('mechanics', []):
        r = mechanic_row(m, caps)
        if r['status'] != 'made':
            out.append({k: r[k] for k in ('feature', 'asked', 'status', 'reason', 'closest', 'fix') if k in r})
    return out


NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:[-'][A-Za-z]+)?\b")


def prompt_names(prompt, brief, story):
    """Capitalised words of the prompt (not first in a sentence) that neither the brief nor the story uses."""
    used = ' '.join(_texts(story or {}))
    used += ' ' + json.dumps({k: v for k, v in (brief or {}).items() if k not in ('prompt', 'tags', 'assumptions')})
    used_w = set(re.findall(r'[a-z0-9]+', used.lower()))
    out = []
    for m in NAME_RE.finditer(prompt):
        before = prompt[:m.start()].rstrip()
        if not before or before[-1] in '.!?:;"':
            continue
        w = re.sub(r"'s$", '', m.group(0))
        lw = w.lower()
        if lw in STOP or lw in used_w or w in out:
            continue
        out.append(w)
    return out


def plan_lines(story, lay, caps=None, routes=()):
    """'I will make X; not as asked: Y (closest Z)' lines for the plan, before any project exists."""
    caps = caps or load_caps()
    made, notes = [], []
    if story.get('player'):
        made.append('player %s' % story['player']['name'])
    actors = [a for a in lay['actors']]
    if actors:
        made.append('people %s' % ', '.join('%s (%s room%s)' % (a['name'], a['room'], ', follows you when freed' if a.get('captive') else '')
                                          for a in actors))
    rooms = [n for n in (lay['rooms']['entry'], lay['rooms']['inside']) if n]
    if rooms:
        made.append('rooms %s' % ' + '.join(rooms))
    if story.get('item'):
        made.append('item %s' % story['item']['name'])
    if story.get('beats'):
        made.append('%d beats in order (%s)' % (len(story['beats']), ', '.join(
            ('%s: %s' % (b['k'], ('talk' if b.get('who') else 'spot') + ' in ' + b['room'])) for b in lay['beats'])))
    if story.get('quests'):
        made.append('%d quests' % len(story['quests']))
    if story.get('choice'):
        made.append('a choice: %s' % ' / '.join(story['choice']['options']))
    if story.get('door_lock'):
        made.append('the inside door opens after %s %s' % tuple(str(x) for x in story['door_lock']))
    foes = [c['name'] for c in story.get('cast', []) if c['role'] in FOE_ROLES]
    if foes and 'combat_arena' in routes:
        made.append('fighters %s%s' % (', '.join(foes), (' in waves %s' % story['waves']) if story.get('waves') else ''))
        if any(n > MAX_AT_ONCE for n in story.get('waves', [])):
            notes.append(row_line({'feature': 'waves', 'asked': str(story['waves']), 'status': 'closest',
                                   'closest': 'waves of 3 are split so at most %d fight at once (room triangle budget)' % MAX_AT_ONCE}))
    if story.get('course') and 'timed_course' in routes:
        made.append('timed course %d s via %s' % (story['course']['seconds'], ', '.join(story['course']['checkpoints'])))
    for m in story.get('mechanics', []):
        r = mechanic_row(m, caps)
        if r['status'] == 'made':
            made.append('%s -> %s' % (m, r['what']))
    for r in lay['rows'] + mechanic_rows(story, caps):
        notes.append(row_line(r))
    return made, notes


def row_line(r):
    """One plain line for a not-applied row: what was asked, what happens instead, the fix."""
    head = '%s %r' % (r['feature'], r['asked'])
    closest = r.get('closest') if r.get('closest') not in (None, '', 'none') else None
    if r['status'] == 'closest':
        body = 'not made as asked; closest: %s' % (closest or 'none')
    else:
        body = 'not made (%s)%s' % (r.get('reason') or 'not supported', '; closest: %s' % closest if closest else '')
    return '%s: %s%s' % (head, body, '. Fix: %s' % r['fix'] if r.get('fix') else '')
