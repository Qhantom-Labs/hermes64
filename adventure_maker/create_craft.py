"""VARIETY: the create flow crafts by default.

A plain one-line brief ("a knight at night looking for his lost love") gets, without any helper wording:

  * a made protagonist (the character maker's own propose -> build -> bind, text chosen from the brief's words);
  * three to five brief-named pieces made new (bounded hermes64-recipe/1 data from create_craft.json, built and gated
    by the same generator loop an agent recipe takes, at most four tries each);
  * the brief's landmark piece on the entry pattern's landmark slot when the destination did not take it.

Nothing here lowers a gate. A piece or a protagonist that cannot be made is a "not applied" row with the reason and
the stand-in that is used instead (the library piece, the public cast). An agent recipe in create/candidates.json or an
agent-made cast member always wins over the defaults here.

Every create_flow.py call into this module is one line marked `# VARIETY` (see docs/VARIETY-HUNKS.md).
"""
import copy
import hashlib
import json
from pathlib import Path
import re

DATA = Path(__file__).with_name('create_craft.json')
MODEL = 'hermes64-create-craft-template'
INT_ARGS = ('segs', 'sides', 'rings', 'nu', 'nv')
RATIO_ARGS = ('squash_bottom',)
ACCENTS = ('grey', 'red', 'navy', 'orange', 'purple', 'green')
MAX_CHARACTER_TRIES = 4


def load():
    return json.loads(DATA.read_text(encoding='utf-8'))


def words(text):
    return re.findall(r'[a-z]+', str(text or '').lower())


def _singular(w):
    return w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w


def _head(want):
    w = words(want)
    return _singular(w[-1]) if w else ''


def prompt_bag(prompt):
    """The words the user wrote (plus singular forms). They lead every craft choice."""
    return {f for w in words(prompt) for f in (w, _singular(w))}


def brief_bag(prompt, brief):
    """Every word the user and the brief used (plus singular forms). Brief-only words (a no-LLM brief adds stock
    places and people the user never said) only fill a choice the user's own words left short."""
    texts = [prompt, (brief.get('setting') or {}).get('place', '')]
    texts += [p.get('want', '') for p in brief.get('props', [])]
    texts += [c.get('want', '') for c in brief.get('characters', [])]
    texts += list(brief.get('build_types', []))
    bag = set()
    for t in texts:
        for w in words(t):
            bag.add(w); bag.add(_singular(w))
    return bag


# ------------------------------------------------------------------------------------------------------- pieces
def _scaled(value, h=None):
    """Unit-space length -> a bounded reference to the recipe's one `height` parameter (so the loop's class-extent
    repair, which only moves declared size parameters, can resize the whole piece)."""
    if isinstance(value, list):
        return [_scaled(v) for v in value]
    return {'param': 'height', 'mul': round(float(value), 4)} if value else 0


def _role(spec, index, params):
    """'light|glass|paper' -> a string parameter whose declared alternatives the loop may step through on a palette or
    emission gate reason (asset_loop._adjust); a single role stays a plain role."""
    roles = spec.split('|')
    if len(roles) == 1:
        return roles[0]
    name = 'role_%d' % index
    params[name] = {'type': 'string', 'default': roles[0], 'enum': roles}
    return {'param': name}


def recipe_for(template_id, data=None):
    """One template -> a hermes64-recipe/1 document. Template lengths are unit-space and scaled by its height."""
    data = data or load()
    tpl = data['templates'][template_id]
    h = float(tpl['height'])
    params = {'segments': {'type': 'integer', 'default': 6, 'minimum': 5, 'maximum': 8},
              'height': {'type': 'number', 'default': h, 'minimum': round(h * .4, 3), 'maximum': round(h * 1.6, 3)}}
    ops = []
    for i, raw in enumerate(tpl['ops']):
        prim, role, args = raw[0], raw[1], raw[2]
        extra = raw[3] if len(raw) > 3 else {}
        out = {}
        for k, v in args.items():
            if k in INT_ARGS:
                out[k] = {'param': 'segments'} if v == 'segments' else int(v)
            elif k in RATIO_ARGS:
                out[k] = v
            else:
                out[k] = _scaled(v, h)
        op = {'primitive': prim, 'role': _role(role, i, params), 'args': out}
        tr = {}
        if 'rotate' in extra:
            tr['rotate'] = list(extra['rotate'])
        if 'translate' in extra:
            tr['translate'] = _scaled(extra['translate'], h)
        if tr:
            op['transform'] = tr
        if 'repeat' in extra:
            rep = dict(extra['repeat'])
            if 'step' in rep:
                rep['step'] = _scaled(rep['step'], h)
            op['repeat'] = rep
        if extra.get('mirror'):
            op['mirror'] = extra['mirror']
        ops.append(op)
    return {'format': 'hermes64-recipe/1', 'id': 'craft_' + template_id, 'class': tpl['class'], 'licence': 'CC0-1.0',
            'parameters': params, 'operations': ops}


def max_pieces(data, rooms=2):
    """LONGSTORY-2: crafted pieces the prompt's own words may ask for: pieces_per_room for every room (the two-room game
    keeps max_pieces, 4). The rooms stage places what fits each room's triangle budget and lists the rest as not
    placed with that reason, so this follows the budget instead of capping the game."""
    return max(int(data['max_pieces']), int(data.get('pieces_per_room', 2)) * int(rooms or 2))


def choose_pieces(said, bag, data, skip=(), have=0, rooms=2):
    """The ordered craft list (entry order is priority): pieces the user's own words (`said`) name, up to max_pieces
    (per room: max_pieces()); then pieces only the brief's other words (`bag`) name, then the defaults, up to
    min_pieces. `skip` (templates already offered) and `have` (pieces already planned) let plan() ask again when a
    choice could not be used."""
    out, used = [None] * have, set(skip)
    for src, limit, label in ((said, max_pieces(data, rooms), 'prompt word'), (bag, data['min_pieces'], 'brief word')):
        for e in data['pieces']:
            if len(out) >= limit:
                break
            if e['template'] in used or not set(e['words']) & src or set(e.get('unless', [])) & (said | bag):
                continue
            out.append(dict(e, by='%s: %s' % (label, ', '.join(sorted(set(e['words']) & src)))))
            used.add(e['template'])
    for e in data['defaults']:
        if len(out) >= data['min_pieces']:
            break
        if e['template'] not in used:
            out.append(dict(e, by='default: the brief named fewer than %d craftable things' % data['min_pieces']))
            used.add(e['template'])
    return out[have:]


def plan(prompt, brief, rows, candidates, rooms=2):
    """(rows, candidates, craft): gap rows and candidates with the default craft pieces added. A piece whose name an
    existing row already asks for is attached to that row (so the brief's own want is the one made); otherwise it is a
    new row. Rows the agent gave a candidate for, and 'not covered' rows, are left alone."""
    data = load()
    rows, candidates = [dict(r) for r in rows], dict(candidates)
    craft = {'format': 'hermes64-create-craft/1', 'pieces': [], 'skipped': []}
    wants = {r['want'] for r in rows}
    said, bag, offered, queue = prompt_bag(prompt), brief_bag(prompt, brief), set(), []
    while True:                                     # a choice that cannot be used is replaced, up to min_pieces
        if not queue:
            if offered and len(craft['pieces']) >= data['min_pieces']:
                break
            queue = choose_pieces(said, bag, data, skip=offered, have=len(craft['pieces']), rooms=rooms)
            if not queue:
                break
        e = queue.pop(0)
        offered.add(e['template'])
        names = set(e.get('names') or [_head(e['want'])])
        row = next((r for r in rows if (r['want'] == e['want'] or _head(r['want']) in names)
                    and r.get('status') != 'not covered'), None)
        want = row['want'] if row else e['want']
        if want in candidates:
            craft['skipped'].append({'want': want, 'reason': 'create/candidates.json already names a recipe for it'})
            continue
        if row is None and want in wants:
            craft['skipped'].append({'want': want, 'reason': 'the brief already has this line and it is not an asset need'})
            continue
        if row is None:
            rows.append({'want': want, 'status': 'missing', 'matches': [], 'why': 'crafted by default (%s)' % e['by']})
            wants.add(want)
        candidates[want] = {'recipe': recipe_for(e['template'], data), 'model': MODEL}
        craft['pieces'].append({'want': want, 'template': e['template'], 'role': e['role'], 'by': e['by'],
                                'attached': row is not None, 'was': (row or {}).get('status', 'new')})
    return rows, candidates, craft


def character_rows(rows, brief, protagonist):
    """The player's 'character:' line says what was made instead of 'no new character made'. The status stays
    'not covered' (it is not a placed asset need); the made character is recorded under `protagonist`."""
    if protagonist.get('status') != 'crafted':
        return rows
    player = next((c.get('want') for c in brief.get('characters', []) if c.get('role') == 'player'), None)
    out, done = [], False
    for r in rows:
        if not done and player is not None and r['want'] == 'character: ' + player:
            r = dict(r, why='new character made for this game: %s (%s)' % (protagonist['id'], protagonist.get('text', '')))
            done = True
        out.append(r)
    return out


def retry_plain(report, rows, craft, run_plain):
    """A default craft piece that failed its gates on a row the library could have served is run again the old way
    (no craft recipe), so crafting never costs a game a piece it would have had. The failure stays on record."""
    by_want = {c['want']: c for c in craft['pieces']}
    out = []
    for row in report['rows']:
        c = by_want.get(row['want'])
        if c and row['status'] != 'generated':
            c.update(status='not made', reason=' '.join(str(row.get('reason', '')).split())[:300],
                     tries=len(row.get('attempts', [])))
            if c['attached']:
                gap = next(g for g in rows if g['want'] == row['want'])
                row = run_plain([gap])['rows'][0]
                c['stand_in'] = row.get('id') if row['status'] not in ('failed', 'not covered') else None
        elif c:
            c.update(status='crafted', id=row.get('id'), tries=len(row.get('attempts', [])), tri_count=row.get('tri_count'))
        out.append(row)
    return dict(report, rows=out)


def mark_landmark(items, pat, assets):
    """The brief's crafted landmark takes the entry pattern's landmark slot when no destination piece did."""
    if not pat.get('landmark_vista_m') or any(it.get('landmark') for it in items):
        return None
    wants = [c['want'] for c in (assets.get('craft') or {}).get('pieces', [])
             if c.get('role') == 'landmark' and c.get('status') == 'crafted']
    for it in items:
        if it['want'] in wants and not it['placed'] and it['mode'] == 'append' and it['instance'] == 1 \
                and it['where'] in ('vista', 'outdoor'):
            it['landmark'] = True
            return it
    return None


# ----------------------------------------------------------------------------------------------- entry layout
MIRROR_SIDE = {'e': 'w', 'w': 'e'}


def _mx(x, w):
    return round(w - float(x), 3)


def mirror_pattern(pat, w):
    """The same kit skeleton seen from the other corner: every x of the plan and its anchors mirrored about the plot's
    middle (w = plot width in metres). Blocks are as wide as the plot, so a block origin bx becomes -bx."""
    pat = copy.deepcopy(pat)
    plan = pat['plan']
    cells_x = plan['plot_cells'][0]
    for pc in plan['pieces']:
        if 'block' in pc:
            pc['block'] = [-pc['block'][0], pc['block'][1]]
        if 'edge' in pc:
            cx, cz, side = pc['edge']
            pc['edge'] = [cells_x - 1 - cx, cz, MIRROR_SIDE.get(side, side)]
        if 'at_m' in pc:
            pc['at_m'] = [_mx(pc['at_m'][0], w), pc['at_m'][1]]
        if 'yaw' in pc:
            pc['yaw'] = -pc['yaw']
    for d in plan.get('doors', []):
        if d['side'] in ('n', 's'):
            d['cell'] = cells_x - 1 - d['cell']
        else:
            d['side'] = MIRROR_SIDE[d['side']]
    cam = plan['camera']
    cam['position'] = [_mx(cam['position'][0], w)] + list(cam['position'][1:])
    cam['look_at'] = [_mx(cam['look_at'][0], w)] + list(cam['look_at'][1:])
    for k in ('door_point_m', 'centre_m', 'npc_m'):
        pat[k] = [_mx(pat[k][0], w), pat[k][1]]
    if 'npc_yaw' in pat:
        pat['npc_yaw'] = -pat['npc_yaw']
    rect = lambda r: [_mx(r[2], w), r[1], _mx(r[0], w), r[3]]
    pat['dress_rect_m'] = rect(pat['dress_rect_m'])
    pat['blocked_m'] = [rect(r) for r in pat.get('blocked_m', [])]
    pat['vista_m'] = [[_mx(v[0], w), v[1], -v[2]] + list(v[3:]) for v in pat.get('vista_m', [])]
    if pat.get('landmark_vista_m'):
        lm = pat['landmark_vista_m']
        pat['landmark_vista_m'] = [_mx(lm[0], w), lm[1], -lm[2]] + list(lm[3:])
    return pat


def variant_pattern(base, v, w):
    """One create_craft.json layout variant -> a full pattern: the base pattern's kit skeleton with the variant's plot
    ground, entry building and wall piece (all shipped kit keys), mirrored when asked."""
    pat = copy.deepcopy(base)
    for pc in pat['plan']['pieces']:
        if v.get('ground') and pc.get('kind') == 'floor' and pc.get('block') == [0, 0]:
            pc['key'] = v['ground']
        elif v.get('doorway') and pc.get('door_to'):
            pc['key'] = v['doorway']
        elif v.get('wall') and pc.get('kind') == 'wall':
            pc['key'] = v['wall']
    if v.get('mirror'):
        pat = mirror_pattern(pat, w)
    pat.update(id=v['id'], tags=list(v['tags']), only_if_keys=sorted({pc['key'] for pc in pat['plan']['pieces']}),
               source='create_craft.json layout %s: the %s skeleton%s, ground %s, entry building %s' % (
                   v['id'], base['id'], ' mirrored' if v.get('mirror') else '', v.get('ground', 'unchanged'),
                   v.get('doorway', 'unchanged')))
    return pat


def setting_bags(prompt, brief, data):
    """(said, other): the words a layout is scored on. `said` is what the user wrote about the place, the time and the
    weather (two points each); `other` is what only the brief adds (one point). The genre is left out: it picks the
    family (the kit), so it cannot tell two places of one family apart."""
    s, m, alias = brief.get('setting') or {}, brief.get('mood') or {}, data['layouts']['aliases']
    widen = lambda bag: bag | {alias[w] for w in bag if w in alias}
    drop = {str(s.get('genre', '')), ''} | set(s.get('genre_hints', []))
    said = widen(prompt_bag(prompt)) - drop
    other = widen(brief_bag(prompt, brief) | {str(m.get(k, '')) for k in ('time', 'weather', 'season')}) - drop - said
    return said, other


def setting_pattern(options, family, chosen, prompt, brief, keys, scale, width_of):
    """(pattern, why): the entry layout for the brief's setting. The word-order choice (`chosen`) stays unless another
    usable layout of the family names strictly more of the brief's setting words; a brief that asks a room scale keeps
    the scale's choice."""
    data = load()
    if scale not in (None, 'medium'):
        return chosen, 'room scale %s picks the layout' % scale
    said, other = setting_bags(prompt, brief, data)
    by_id = {p['id']: p for p in options}
    pool = [p for p in options if set(p.get('only_if_keys', [])) <= keys]
    for v in data['layouts'].get(family, []):
        if v['from'] in by_id:
            pat = variant_pattern(by_id[v['from']], v, width_of(by_id[v['from']]))
            if set(pat['only_if_keys']) <= keys:
                pool.append(pat)
    score = lambda p: 2 * len(set(p['tags']) & said) + len(set(p['tags']) & other)
    best = max(pool, key=score) if pool else chosen          # max keeps the first of equals: shipped patterns lead
    if best['id'] != chosen['id'] and score(best) > score(chosen):
        return best, 'setting words %s (%d points against %d for %s)' % (
            ', '.join(sorted(set(best['tags']) & (said | other))), score(best), score(chosen), chosen['id'])
    return chosen, 'word-order choice kept (no layout names more of the setting)'


# -------------------------------------------------------------------------------------------------- protagonist
def pick_protagonist(prompt, brief, data=None):
    """The protagonist description for the character maker, from the brief's words (first match in list order)."""
    data = data or load()
    player = next((c.get('want', '') for c in brief.get('characters', []) if c.get('role') == 'player'), '')
    said = set(words(prompt)) | {_singular(w) for w in words(prompt)}
    grounded = bool((set(words(player)) | {_singular(w) for w in words(player)}) & said)
    # the brief's player line leads when the prompt uses its word; a player line the prompt never said (the no-LLM
    # brief's stock 'squire') comes after the prompt's own words, read in the order the user wrote them
    for text in ((player, prompt) if grounded else (prompt, player)):
        for w in words(text):
            for e in data['protagonists']:
                if w in e['words'] or _singular(w) in e['words']:
                    return dict(e, by='brief word: ' + (w if w in e['words'] else _singular(w)))
    accent = ACCENTS[int(hashlib.sha256(str(prompt).encode('utf-8')).hexdigest(), 16) % len(ACCENTS)]
    d = data['protagonist_default']
    return {'name': d['name'], 'text': d['text'].replace('{accent}', accent), 'by': 'default: no known protagonist word'}


def _agent_cast(ctx):
    """An agent-made, already bound cast member (characters/cast.json) is the protagonist; the flow makes none."""
    if not ctx.exists('characters/cast.json'):
        return None
    cast = (ctx.read_json('characters/cast.json') or {}).get('cast') or []
    return cast[0] if cast and isinstance(cast[0], dict) and cast[0].get('id') else None


def craft_protagonist(ctx, prompt, brief):
    """Always a record for create/assets.json: status 'crafted' (id, rig, tries) or 'not made' (reason, stand-in)."""
    if ctx.exists('create/assets.json'):
        prev = (ctx.read_json('create/assets.json') or {}).get('protagonist') or {}
        if prev.get('status') == 'crafted' and (ctx.root / 'characters' / 'built' / str(prev.get('id'))).is_dir():
            return prev
    pick = pick_protagonist(prompt, brief)
    rec = {'status': 'not made', 'name': pick['name'], 'text': pick['text'], 'by': pick['by'], 'tries': 0}
    if pick.get('closest'):
        rec['closest'] = pick['closest']
    mine = _agent_cast(ctx)
    if mine:
        rec.update(status='crafted', id=mine['id'], rig=(mine.get('rig') or {}).get('id'), by='the cast already made for this game')
        return rec
    try:
        from .character_tools import CharacterService
        svc = CharacterService(ctx.settings)
        errors = []
        for text in (pick['text'], load()['protagonist_default']['text'].replace('{accent}', 'grey')):
            got = json.loads(svc.handle({'action': 'propose', 'project': ctx.name, 'brief': text}))
            for v in (got.get('variants') or []) if got.get('ok') else []:
                if rec['tries'] >= MAX_CHARACTER_TRIES or not v.get('gates_ok'):
                    continue
                rec['tries'] += 1
                built = json.loads(svc.handle({'action': 'build', 'project': ctx.name, 'recipe': v['variant']}))
                if not built.get('ok'):
                    errors.append(str(built.get('error') or built.get('errors') or 'build refused')[:160])
                    continue
                bound = json.loads(svc.handle({'action': 'bind', 'project': ctx.name, 'id': built['id'],
                                               'display_name': pick['name']}))
                if not bound.get('ok'):
                    errors.append(str(bound.get('error') or 'bind refused')[:160])
                    continue
                rec.update(status='crafted', id=built['id'], rig=built.get('rig'), sha256=built.get('sha256'),
                           glb=built.get('glb'), summary=v.get('summary'), text=text)
                return rec
            if not got.get('ok'):
                errors.append(str(got.get('error') or 'propose refused')[:160])
        rec['reason'] = '; '.join(errors) or 'no proposed variant passed the character gates'
    except Exception as e:      # the character maker is optional equipment: its absence is a row, never a failed game
        rec['reason'] = ' '.join(('%s: %s' % (type(e).__name__, e)).split())[:300]
    return rec


def apply_cast(spec, assets):
    """The crafted protagonist plays the game's protagonist slot (the same cast mapping hermes64_character bind uses)."""
    prot = assets.get('protagonist') or {}
    if prot.get('status') != 'crafted' or not prot.get('id'):
        return spec
    spec = copy.deepcopy(spec)
    slot = spec['metadata'].get('protagonist', 'traveller')
    spec['metadata']['presentation'].setdefault('cast', {})[slot] = prot['id']
    for ch in spec.get('characters', []):
        if ch.get('id') == slot and ch.get('name') in ('Traveller', '', None):
            ch['name'] = str(prot.get('name') or 'Traveller')[:40]
    return spec


# ------------------------------------------------------------------------------------------------------- report
def summary(craft, protagonist):
    made = [c for c in craft['pieces'] if c.get('status') == 'crafted']
    return {'pieces_crafted': len(made), 'pieces_planned': len(craft['pieces']),
            'protagonist': protagonist.get('status'), 'protagonist_id': protagonist.get('id')}


def made_line(assets):
    """One report line: what the run made new for this game. Counts only; a miss is a Not applied row."""
    prot, craft = assets.get('protagonist') or {}, assets.get('craft') or {'pieces': []}
    made = [c for c in craft['pieces'] if c.get('status') == 'crafted']
    hero = ('hero %s (%s)' % (prot.get('id'), prot.get('text', ''))) if prot.get('status') == 'crafted' else 'no hero'
    return 'Made new for this game: %s; pieces %d of %d planned%s.' % (
        hero, len(made), len(craft['pieces']), (': ' + ', '.join(c['want'] for c in made)) if made else '')


def report_rows(assets):
    """Honest rows for what the default craft did not make (create/rooms.json not_applied; shown in the report)."""
    out = []
    prot = assets.get('protagonist')
    if prot and prot.get('status') != 'crafted':
        out.append({'feature': 'protagonist', 'asked': prot.get('text', ''), 'status': 'not_made',
                    'reason': 'protagonist not made: %s' % (prot.get('reason') or 'unknown'),
                    'closest': 'the public cast stands in', 'fix': 'hermes64_character propose/build/bind, then run again'})
    elif prot and prot.get('closest'):
        out.append({'feature': 'protagonist', 'asked': prot.get('by', ''), 'status': 'closest',
                    'reason': 'protagonist made as the closest body the character maker has: %s' % prot['closest'],
                    'closest': prot['closest'], 'fix': 'none in the create flow'})
    for c in (assets.get('craft') or {}).get('pieces', []):
        if c.get('status') == 'not made':
            out.append({'feature': 'crafted piece', 'asked': c['want'], 'status': 'not_made',
                        'reason': 'crafted %s failed its gates after %s tries: %s' % (c['want'], c.get('tries'), c.get('reason')),
                        'closest': ('library piece %s' % c['stand_in']) if c.get('stand_in') else 'nothing stands in',
                        'fix': 'author a recipe for it (skill hermes64-generators) in create/candidates.json'})
    return out
