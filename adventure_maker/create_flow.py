"""One entry point: a prompt in, an original small game out, with an honest report (lane ORCH).

    python -B -m adventure_maker.create_flow run "a haunted lighthouse puzzle adventure" --projects-root DIR [--name N]
    python -B -m adventure_maker.create_flow status --projects-root DIR --name N
    python -B -m adventure_maker.create_flow run --projects-root DIR --name N          # resume / re-run changed stages

Stages (each writes a normal project artifact the agent can read and edit; a later run keeps an edited artifact
and re-runs only the stages downstream of it):

  project   hermes64_scaffold                                  -> create/prompt.json
  brief     adventure_maker.brief (agent brief or keyword fallback) -> brief.json
  gaps      adventure_maker.taxonomy gap report + brief.needs  -> create/gaps.json
  style     base pack (library hits x words) + shipped variant or mood -> create/style.json
  mood      tools.mood_pack install of a derived mood pack (bundle write, named)  -> create/mood.json
  assets    adventure_maker.asset_loop (existing / remap / recipe / named stand-in) -> ASSET-REPORT.json, create/assets.json
  rooms     placemaker archetype when adventure_maker.place exists, else the kit compiler + create_patterns.json
            skeletons, dressed with the resolved pieces       -> create/rooms.json, create/pack.json, source/spec.json
  build     hermes64_pack_create, compile, check, build_assets -> create/build.json
  playtest  adventure_maker.playtest bots                     -> create/playtest.json
  capture   hermes64_open screenshots + style/N64 gates       -> create/captures.json, create/captures/*.png
  report    CREATE-REPORT.{json,md}: ledger, counts, what could not be made, closeness score

State: <project>/.create/state.json (input/output hashes per stage, seconds, one-line errors). Pure stages are run twice
and compared, so a nondeterministic stage is refused instead of recorded. Everything is bounded by --budget-seconds;
an exhausted budget pauses (resumable), never truncates silently. No network, no model client, no installs: recipes
for missing pieces come from project recipes, the shipped exemplars or create/candidates.json written by the agent.
The closeness score counts needs, gates and attempts. It is never an aesthetic score; looks are for the owner to judge.
"""
import argparse
import copy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / 'kits')):
    if _p not in sys.path:
        sys.path.append(_p)

FORMAT = 'hermes64-create-state/1'
REPORT_FORMAT = 'hermes64-create-report/1'
STATE = '.create/state.json'
SEED = 7
DEFAULT_BUDGET = 1800
DEFAULT_PACK = 'n64_v0'
OPEN_SECONDS = 40
ROOM_CAP, ROOM_RESERVE = 6000, 300
MAX_INSTANCES = 3
ALT_TRIES = 3
CAMERA_CLEAR_M = 4.5
# TFIX F1c: the runtime starts the player at (w/2, 0.7 d) (view/presenter.gd) with the follow camera 4.5 m behind along
# the room camera's yaw (follow_camera.gd DEFAULT_DISTANCE x cos DEFAULT_PITCH). A solid piece on that boom pulls the
# camera in to the shoulder, so start-room dressing keeps it clear (footprint r x 1.42: a yawed box's corners).
SPAWN_BOOM_M, BOOM_CLEAR_M = 4.5, 0.4
PATTERNS = Path(__file__).with_name('create_patterns.json')
GAMEPLAY_WORDS = {'puzzle', 'puzzles', 'combat', 'shootout', 'shoot', 'gunfight', 'duel', 'fight', 'battle', 'racing',
                  'race', 'stealth', 'boss', 'boss-rush', 'arena', 'platformer', 'heist', 'robbery', 'chase', 'survival',
                  'collectathon', 'timed', 'escape'}
LARGE_RADIUS_M = 3.4
STRUCTURE_CLASSES = ('structure', 'building', 'terrain', 'shell', 'kit')
OUTDOOR_CLASSES = STRUCTURE_CLASSES + ('flora', 'vehicle', 'sky', 'arch')   # never dressed into the inside room


class CreateError(Exception):
    """One plain line: code, message and the next step."""
    def __init__(self, code, message, next_step=''):
        super().__init__(message)
        self.code, self.message, self.next_step = code, one_line(message), one_line(next_step)

    def line(self):
        return '%s: %s%s' % (self.code, self.message, (' Next: ' + self.next_step) if self.next_step else '')


def one_line(value):
    return ' '.join(str(value).split())[:600]


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(obj):
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + '\n').encode()


# ------------------------------------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, settings, name, prompt=None, opts=None, deadline=None):
        self.settings = dict(settings)
        self.settings.setdefault('bundle_root', str(ROOT))
        self.settings.setdefault('builder', 'python')
        self.bundle = Path(self.settings['bundle_root'])
        self.name = name
        self.root = Path(self.settings['projects_root']) / name
        self.prompt = prompt
        self.opts = dict(opts or {})
        self.deadline = deadline
        self._service = None
        self.memo = {}

    @property
    def service(self):
        if self._service is None:
            from .service import Service
            self._service = Service(self.settings)
        return self._service

    def path(self, rel):
        from .safety import relative
        return self.root / relative(rel).as_posix()

    def exists(self, rel):
        return self.path(rel).is_file()

    def read_json(self, rel):
        try:
            return json.loads(self.path(rel).read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise CreateError('create_missing', '%s is missing in %s' % (rel, self.root),
                              'run the stage that writes it again (create_flow run --redo <stage>)') from None
        except ValueError as e:
            raise CreateError('create_artifact', '%s is not valid JSON (%s)' % (rel, e),
                              'fix or delete the file, then run again') from None

    def write(self, rel, obj):
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(obj if isinstance(obj, bytes) else pretty(obj))

    def call(self, tool, **args):
        """A normal Hermes64 tool call through the Service (the same path the agent's tools use)."""
        raw = self.service.handle('hermes64_' + tool, dict(project=self.name, **args))
        result = json.loads(raw)
        if result.get('truncated') and result.get('report_path'):
            stored = json.loads((self.root / result['report_path']).read_text(encoding='utf-8'))
            result = stored if isinstance(stored, dict) else result
        return result

    def remaining(self):
        return None if self.deadline is None else self.deadline - time.monotonic()


def bundle_import(ctx, module):
    """Import a bundle module (tools.* live beside adventure_maker/ in the plugin tree)."""
    for p in (str(ctx.bundle), str(ctx.bundle / 'kits')):
        if p not in sys.path:
            sys.path.insert(0, p)
    path = ctx.bundle / (module.replace('.', '/') + '.py')
    if module.startswith('tools.') and path.is_file():   # by path: inside Hermes `tools` is Hermes's own package
        from importlib import util as ilu
        key = 'hermes64_bundle_' + module.replace('.', '_')
        if key not in sys.modules:
            spec = ilu.spec_from_file_location(key, path)
            mod = ilu.module_from_spec(spec)
            sys.modules[key] = mod
            try:
                spec.loader.exec_module(mod)
            except ImportError as e:
                sys.modules.pop(key, None)
                raise CreateError('create_component', '%s could not load (%s)' % (module, e), 'run from the plugin folder')
        return sys.modules[key]
    try:
        return importlib.import_module(module)
    except ImportError as e:
        raise CreateError('create_component', '%s is not available in this plugin tree (%s)' % (module, e),
                          'apply docs/orch-hunks/package-include.patch (docs/ORCH-NEWGAME-PATCH.md), or run from the source tree')


# ------------------------------------------------------------------------------------------------- small helpers
def words(text):
    return re.findall(r'[a-z]+', str(text).lower().replace('-', ' '))


def brief_words(brief):
    s = brief.get('setting', {})
    out = [s.get('genre', '')] + list(s.get('genre_hints', [])) + words(s.get('place', ''))
    for b in brief.get('build_types', []):
        out += words(b)
    for p in brief.get('props', []):
        out += words(p.get('want', ''))
    out += list(brief.get('unrecognised', []))
    m = brief.get('mood', {})
    out += [m.get('time', ''), m.get('weather', ''), m.get('season', ''), m.get('tone', '')]
    return [w for w in out if w]


def glb_radius(path):
    """Largest horizontal half-extent (m) from the GLB POSITION accessor bounds; 1.0 when unreadable."""
    try:
        raw = Path(path).read_bytes()
        length = struct.unpack('<I', raw[12:16])[0]
        doc = json.loads(raw[20:20 + length])
        xs, zs = [], []
        for mesh in doc.get('meshes', []):
            for prim in mesh['primitives']:
                acc = doc['accessors'][prim['attributes']['POSITION']]
                if 'min' in acc and 'max' in acc:
                    xs += [acc['min'][0], acc['max'][0]]
                    zs += [acc['min'][2], acc['max'][2]]
        if not xs:
            return 1.0
        return round(max(abs(v) for v in xs + zs), 3)
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return 1.0


def load_patterns():
    return json.loads(PATTERNS.read_text(encoding='utf-8'))


def family_for(base):
    for fam, row in load_patterns()['families'].items():
        if any(base == p or base.startswith(p + '_') for p in row['packs']):
            return fam
    return None


def place_api():
    """The PLACEMAKER place API when this plugin tree has it (detected at runtime, never required)."""
    try:
        mod = importlib.import_module('adventure_maker.place')
    except ImportError:
        return None
    need = ('list_archetypes', 'load_archetype', 'make_plan', 'compile')
    return mod if all(hasattr(mod, n) for n in need) else None


def gen_presets_supported():
    """Can a project pack preset name a gen: recipe? (owner hunk docs/agen-hunks/packs-gen-id.patch)."""
    from .packs import ASSET_ID
    from .schemas import validate
    from .safety import Fault
    try:
        validate('gen:probe_piece', ASSET_ID)
        return True
    except Fault:
        return False


# ------------------------------------------------------------------------------------------------------- stages
def stage_project(ctx):
    marker = ctx.root / '.maker/project.json'
    if marker.is_file():
        if ctx.exists('create/prompt.json'):
            return {}
        raise CreateError('create_exists', 'a project named %r already exists in %s and was not made by create'
                          % (ctx.name, ctx.root.parent), 'pick another --name')
    if ctx.root.exists():
        raise CreateError('create_exists', '%s exists and is not a Hermes64 project' % ctx.root, 'pick another --name')
    if not ctx.prompt:
        raise CreateError('create_prompt', 'no prompt given for a new project', 'pass the prompt: create_flow run "<prompt>"')
    result = ctx.call('scaffold', pack=DEFAULT_PACK, premise=ctx.prompt[:300])
    if not result.get('ok'):
        raise CreateError('create_scaffold', 'scaffold failed: %s' % (result.get('error') or {}).get('message', result),
                          'check projects_root and bundle_root')
    ctx.write('create/prompt.json', {'prompt': ctx.prompt, 'format': 'hermes64-create-prompt/1'})
    return {}


VOCAB = Path(__file__).with_name('create_vocab.json')


def load_vocab(path=None):
    return json.loads(Path(path or VOCAB).read_text(encoding='utf-8'))


def vocab_errors(vocab, B=None):
    """Every vocab key must be a word the brief's closed vocabulary already knows (no new genres/hints/roles)."""
    if B is None:
        from . import brief as B
    errs = []
    cues = vocab.get('brief_cues', {})
    for g, groups in cues.get('genre', {}).items():
        if g not in B.GENRES:
            errs.append('genre %r is not a brief genre' % g)
        for w in groups:
            if not str(w).isdigit():
                errs.append('genre %s weight %r is not a number' % (g, w))
    for h in cues.get('hint', {}):
        if h not in B.HINTS:
            errs.append('hint %r is not a brief hint' % h)
    for phrase, row in cues.get('character', {}).items():
        if not (isinstance(row, list) and len(row) == 2 and row[1] in B.ROLES):
            errs.append('character %r needs [want, role] with a brief role' % phrase)
    for g in vocab.get('genre_tags', {}):
        if g not in B.GENRES:
            errs.append('genre_tags key %r is not a brief genre' % g)
    for k in ('genre', 'hint', 'place', 'build', 'prop', 'time'):
        if not isinstance(vocab.get('weights', {}).get(k), (int, float)):
            errs.append('weights.%s missing' % k)
    return errs


def fallback_brief(prompt, vocab=None):
    """The keyword fallback brief, with the create vocabulary merged into brief.py's cue tables for this one call
    (restored afterwards, also on error). Returns (brief, added) where added names the cue phrases that fired."""
    from . import brief as B
    vocab = load_vocab() if vocab is None else vocab
    errs = vocab_errors(vocab, B)
    if errs:
        raise CreateError('create_vocab', 'create_vocab.json: ' + '; '.join(errs[:4]), 'fix the vocabulary file')
    cues = vocab.get('brief_cues', {})
    tables = {'genre': B.GENRE_CUES, 'hint': B.HINT_CUES, 'build': B.BUILD_CUES, 'prop': B.PROP_CUES, 'character': B.CHAR_CUES}
    saved = {k: copy.deepcopy(t) for k, t in tables.items()}
    try:
        for g, groups in cues.get('genre', {}).items():
            for w, phrases in groups.items():
                row = tables['genre'].setdefault(g, {})
                row[int(w)] = list(row.get(int(w), [])) + [p for p in phrases if p not in row.get(int(w), [])]
        for h, phrases in cues.get('hint', {}).items():
            tables['hint'][h] = list(tables['hint'].get(h, [])) + [p for p in phrases if p not in tables['hint'].get(h, [])]
        for k in ('build', 'prop'):
            for phrase, want in cues.get(k, {}).items():
                tables[k].setdefault(phrase, want)
        for phrase, (want, role) in cues.get('character', {}).items():
            tables['character'].setdefault(phrase, (want, role))
        brief = B.normalise(B.from_prompt(prompt))
    finally:
        for k, t in tables.items():
            t.clear()
            t.update(saved[k])
    text = ' ' + ' '.join(words(prompt)) + ' '
    added = sorted({p for k in ('build', 'prop', 'character') for p in cues.get(k, {}) if ' %s ' % p in text}
                   | {p for h in cues.get('hint', {}).values() for p in h if ' %s ' % p in text}
                   | {p for g in cues.get('genre', {}).values() for ps in g.values() for p in ps if ' %s ' % p in text})
    return brief, added


def load_brief_file(path):
    """(brief, story or None) from the agent's brief file: its optional `story` block is split off (lane DETAIL)."""
    from . import brief as B, create_story as CS
    from .safety import Fault, strict_json
    try:
        raw = strict_json(Path(path).read_bytes())
    except OSError as e:
        raise CreateError('brief_missing', 'brief file %s could not be read (%s)' % (path, e.strerror or 'error'),
                          'write the brief file or pass the right --brief path')
    except Fault as e:
        raise CreateError('brief_invalid_json', 'brief file %s is not valid JSON: %s' % (Path(path).name, e), 'fix the JSON')
    raw, story = CS.split_brief(raw)
    try:
        brief = B.normalise(raw)
        B.validate(brief)
        story = CS.validate(story, brief) if story is not None else None
    except Fault as e:
        raise CreateError(getattr(e, 'code', 'brief'), str(e), 'fix brief.json and run again (the error names the field)')
    except CS.StoryError as e:
        raise CreateError(e.code, e.message, e.next_step)
    return brief, story


def stage_brief(ctx):
    from . import brief as B, create_story as CS
    from .safety import Fault
    prompt = ctx.read_json('create/prompt.json')['prompt']
    story, notes = None, []
    try:
        if ctx.opts.get('brief_file'):
            brief, story = load_brief_file(ctx.opts['brief_file'])
        else:
            text = prompt
            if len(prompt) > B.MAX_PROMPT:      # the keyword fallback reads whole sentences up to the brief limit
                cut = prompt[:B.MAX_PROMPT]
                text = cut[:max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? ')) + 1] or cut
                notes.append({'feature': 'prompt', 'asked': '%d characters' % len(prompt), 'status': 'closest',
                              'reason': 'the keyword fallback reads the first %d characters' % len(text),
                              'closest': 'the rest of the prompt is not read', 'fix': 'write the brief with a story block (skill hermes64-create)'})
            brief, added = fallback_brief(text)
            if added:
                brief['assumptions'] = list(brief.get('assumptions', []))[:23] + [
                    ('create vocabulary words used: ' + ', '.join(added))[:120]]
            if ctx.opts.get('room_scale'):      # FINALINT2: `/hermes64 new create "<prompt>" large` (the scale word)
                brief['setting']['room_scale'] = ctx.opts['room_scale']
        B.validate(brief)
    except Fault as e:
        raise CreateError(getattr(e, 'code', 'brief'), str(e), 'fix brief.json and run again (the error names the field)')
    doc = story or {'format': CS.FORMAT, 'empty': True}
    if notes:
        doc = dict(doc, notes=notes)
    return {'brief.json': brief, 'create/story.json': doc}


def stage_gaps(ctx):
    from . import brief as B, taxonomy as T
    brief = ctx.read_json('brief.json')
    wanted = T.wanted_from_brief(brief) + [w for w in brief.get('unrecognised', [])]
    rep = T.gap_report(wanted, brief=brief)
    return {'create/gaps.json': {'format': 'hermes64-create-gaps/1', 'taxonomy': rep, 'needs': B.needs(brief)}}


def _pack_words(pid, ctx):
    from .genre_kits import PACKS as GP
    from .newgame import KEYWORDS
    out = set(GP.get(pid, {}).get('words', []))
    for pack, keys in KEYWORDS:
        if pack == pid:
            out |= set(keys)
    try:
        out |= set(words(json.loads((ctx.bundle / 'packs' / pid / 'pack.json').read_text(encoding='utf-8')).get('name', '')))
    except (OSError, ValueError):
        pass
    return {w for x in out for w in words(x)}


def shipped_packs(ctx):
    rows = []
    for d in sorted((ctx.bundle / 'packs').iterdir()):
        kit = ctx.bundle / 'kits/packs' / d.name / 'pack.json'
        if not (d / 'bindings.json').is_file() or not (d / 'pack.json').is_file():
            continue
        try:
            if kit.is_file() and 'mood' in json.loads(kit.read_text(encoding='utf-8')):
                continue            # a derived mood pack installed by an earlier create, not a shipped base
        except ValueError:
            continue
        rows.append(d.name)
    return rows


def bindings_keys(ctx, pid):
    path = ctx.bundle / 'packs' / pid / 'bindings.json'
    if not path.is_file():
        style = json.loads((ctx.bundle / 'packs' / pid / 'pack.json').read_text(encoding='utf-8'))
        path = ctx.bundle / 'packs' / style['kit_pack_id'] / 'bindings.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    keys = set(doc['assets'])
    keys |= {r.get('kit_id') for r in doc['assets'].values() if isinstance(r, dict) and r.get('kit_id')}
    return keys, doc


def sanitize_palette(brief, M):
    """The brief's hue words that the bible mood vocabulary does not know are dropped (recorded), not guessed."""
    bible = M.load_bible()
    hues = set(bible['mood_vocabulary']['hue_words_hsv_deg'])
    pm = dict(brief.get('palette_mood') or {})
    notes = []
    sup = [w for w in pm.get('support', []) if w in hues]
    for w in pm.get('support', []):
        if w not in hues:
            notes.append('palette support word %r is not a bible hue word; dropped for the mood' % w)
    pm['support'] = sup
    if pm.get('accent') and pm['accent'] not in hues:
        notes.append('accent %r is not a bible hue word; the mood default accent is used' % pm['accent'])
        pm.pop('accent')
    if pm.get('dominant') and pm['dominant'] not in hues:
        notes.append('dominant %r is not a bible hue word; no mood is derived from it' % pm['dominant'])
        pm.pop('dominant')
    # brief words the bible spells differently (DETAIL: 'golden-hour' and 'melancholy' refused every mood before)
    md = dict(brief.get('mood') or {})
    voc = bible['mood_vocabulary']
    t = str(md.get('time') or '').replace('-', '_')
    if t in voc['time_words']:
        md['time'] = t
    elif md.get('time'):
        notes.append('time %r is not a bible time word; the mood uses dusk light' % md.pop('time'))
    tone = {'melancholy': 'melancholic', 'dreamy': 'dreamlike'}.get(str(md.get('tone')), md.get('tone'))
    if tone in voc['tone_words']:
        md['tone'] = tone
    elif md.get('tone') is not None:
        notes.append('tone %r is not a bible tone word; the mood has no tone tint' % md.pop('tone'))
    return dict(brief, palette_mood=pm, mood=md), notes


def pack_scores(ctx, brief, gaps, packs, vocab=None):
    """Weighted tag coverage per shipped pack. Setting words (genre, hints, place) weigh more than prop words, so a
    pack is not chosen because it happens to own a chair and a tombstone. Deterministic: ties break by pack id."""
    from . import taxonomy
    vocab = vocab or load_vocab()
    W = vocab['weights']
    tag_rows = {r['id']: r for r in taxonomy.rows()}
    s = brief['setting']
    genre = s.get('genre', '')
    aliases = set(vocab.get('genre_tags', {}).get(genre, [genre])) | {genre}
    hints = [h for h in s.get('genre_hints', []) if h != genre]
    place_words = {w for w in words(s.get('place', '')) if len(w) > 2}
    builds = set(brief.get('build_types', []))
    props = {p['want'] for p in brief.get('props', [])}
    times = set(words(' '.join([brief.get('mood', {}).get('time', ''), brief.get('mood', {}).get('season', ''),
                                brief.get('mood', {}).get('weather', '')]))) - {'', 'none', 'clear', 'hour'}
    rows = []
    for pid in packs:
        keys, _ = bindings_keys(ctx, pid)
        pw = _pack_words(pid, ctx)
        tags = [set(tag_rows[k]['genre']) for k in keys if k in tag_rows]

        def cov(name, names):        # pack words count only for the word itself; catalog tags also for its aliases
            n = sum(1 for t in tags if t & names)
            if set(words(name)) <= pw or n >= vocab.get('genre_exists_min', 5):
                return 1.0, n
            return (0.5 if n else 0.0), n
        g_cov, g_n = cov(genre, aliases) if genre and genre != 'adventure' else (0.0, 0)
        h_cov = {h: cov(h, {h})[0] for h in hints}
        lib = {r['want'] for r in gaps['rows'] if r['status'] in ('exists', 'partial') and r.get('axis') != 'genre'
               and set(r.get('matches', [])) & keys}
        place_hit = bool(place_words & pw) or bool({b for b in lib if set(words(b)) & place_words})
        b_hits, p_hits = sorted(lib & builds), sorted(lib & props)
        t_hits = sorted(times & pw)
        parts = {'genre': W['genre'] * g_cov, 'hint': W['hint'] * sum(h_cov.values()), 'place': W['place'] * place_hit,
                 'build': W['build'] * len(b_hits), 'prop': W['prop'] * len(p_hits), 'time': W['time'] * len(t_hits)}
        rows.append({'pack': pid, 'score': round(sum(parts.values()), 2), 'parts': parts, 'eligible': bool(family_for(pid)),
                     'genre': genre, 'genre_coverage': g_cov, 'genre_pieces': g_n, 'hint_coverage': h_cov,
                     'place_hit': place_hit, 'build_hits': b_hits, 'prop_hits': p_hits, 'time_hits': t_hits,
                     'room_patterns': bool(family_for(pid))})
    rows.sort(key=lambda r: (-r['score'], r['pack']))
    return rows


def palette_named(brief):
    """True when the brief's palette came from the prompt or the agent (not a genre default)."""
    if brief.get('filled_by') != 'fallback':
        return bool((brief.get('palette_mood') or {}).get('dominant'))
    return not any(str(a).startswith('palette: no colour words') for a in brief.get('assumptions', []))


def _score_line(r):
    p = r['parts']
    return '%s %.1f (genre %.0f, hints %.0f, place %.0f, builds %.0f, props %.0f, time %.0f%s)' % (
        r['pack'], r['score'], p['genre'], p['hint'], p['place'], p['build'], p['prop'], p['time'],
        '' if r['eligible'] else '; no create room pattern')


def choose_pack(scores, vocab=None, caller=None):
    """(base, reason, notes) or CreateError. The top three candidates are always named. A pick whose pack does not
    cover the brief's genre at all, while a pack without room patterns does, is refused instead of made silently."""
    vocab = vocab or load_vocab()
    top3 = '; '.join(_score_line(r) for r in scores[:3])
    notes = []
    if caller:
        row = next((r for r in scores if r['pack'] == caller), None)
        best = scores[0]
        if row and best['pack'] != caller and best['score'] > row['score']:
            notes.append('caller chose %s (%.1f); the highest-scoring pack for this brief is %s (%.1f)' % (
                caller, row['score'], best['pack'], best['score']))
        return caller, 'chosen by the caller. Candidates: ' + top3, notes
    eligible = [r for r in scores if r['eligible']]
    if not eligible:
        raise CreateError('create_style', 'no shipped pack has create room patterns', 'hand-author the rooms (skill)')
    pick = eligible[0]
    genre = pick['genre']
    if genre and genre != 'adventure' and pick['genre_coverage'] == 0:
        better = [r for r in scores if not r['eligible'] and r['genre_coverage'] > 0]
        if better:
            raise CreateError('create_style_refused', 'no pack with create room patterns covers the genre %r; %s covers it '
                              'but has no room pattern. Top candidates: %s' % (genre, better[0]['pack'], top3),
                              'pass --style %s to accept the nearest pack with room patterns, or hand-author the rooms '
                              'on %s (skill hermes64-create)' % (pick['pack'], better[0]['pack']))
        notes.append('no shipped pack covers the genre %r; chosen by the other words' % genre)
    if scores[0]['pack'] != pick['pack']:
        notes.append('%s scored higher (%.1f) but has no create room pattern' % (scores[0]['pack'], scores[0]['score']))
    second = next((r for r in eligible[1:] if family_for(r['pack']) != family_for(pick['pack'])), None)
    if second and pick['score'] - second['score'] <= vocab.get('close_margin', 2):
        notes.append('close call: %s %.1f vs %s %.1f' % (pick['pack'], pick['score'], second['pack'], second['score']))
    reason = 'highest weighted tag coverage among packs with room patterns: %s. Candidates: %s' % (_score_line(pick), top3)
    return pick['pack'], reason, notes


def stage_style(ctx):
    from . import mood_packs
    brief = ctx.read_json('brief.json')
    gaps = ctx.read_json('create/gaps.json')['taxonomy']
    packs = shipped_packs(ctx)
    if not packs:
        raise CreateError('create_style', 'no shipped packs with bindings in %s' % ctx.bundle, 'check bundle_root')
    if ctx.opts.get('style') and ctx.opts['style'] not in packs:
        raise CreateError('create_style', 'unknown style pack %r' % ctx.opts['style'], 'choose one of: ' + ', '.join(packs))
    scores = pack_scores(ctx, brief, gaps, packs)
    explicit_palette = palette_named(brief)
    if explicit_palette:          # colours named in the prompt: a derived mood beats a hand-made time variant
        for r in scores:
            r['score'] = round(r['score'] - r['parts']['time'], 2)
            r['parts']['time'] = 0
        scores.sort(key=lambda r: (-r['score'], r['pack']))
    base, reason, pack_notes = choose_pack(scores, caller=ctx.opts.get('style'))
    if explicit_palette:
        pack_notes = pack_notes + ['the brief names its palette (%s), so a derived mood is preferred over hand-made time '
                                   'variants' % brief['palette_mood'].get('dominant')]
    adjustments = []
    time_words = set(words(' '.join([brief.get('mood', {}).get('time', ''), brief.get('mood', {}).get('season', ''),
                                     brief.get('mood', {}).get('weather', '')]))) - {'', 'none', 'clear', 'hour'}
    variant = None
    if explicit_palette:
        time_words = set()
    if not ctx.opts.get('mood') and base != base.split('_')[0] and time_words & _pack_words(base, ctx) \
            and any(base.startswith(p + '_') for p in packs):
        variant = base                     # the chosen base already is a hand-made variant for this time/weather
    if not ctx.opts.get('mood') and variant is None:
        for pid in packs:
            if pid.startswith(base + '_') and time_words & _pack_words(pid, ctx):
                variant = pid
                break
    out = {'format': 'hermes64-create-style/1', 'base': base, 'scores': scores[:6], 'reason': reason,
           'candidates': [_score_line(r) for r in scores[:3]], 'pack_notes': pack_notes,
           'adjustments': adjustments, 'family': family_for(base)}
    if explicit_palette:
        out['palette_asked'] = (brief.get('palette_mood') or {}).get('dominant')
    if variant:
        out.update(pack=variant, mood=None, mood_status='shipped-variant',
                   mood_reason='%s is a hand-made %s variant; no derived mood' % (
                       variant, '/'.join(sorted(time_words & _pack_words(variant, ctx)))))
        return {'create/style.json': out}
    mp = bundle_import(ctx, 'tools.mood_pack')
    M = mp.M
    clean, notes = sanitize_palette(brief, M)
    adjustments += notes
    mid = None
    if ctx.opts.get('mood'):
        mid = M.resolve_mood(ctx.opts['mood'])
        if mid is None:
            raise CreateError('create_mood', 'unknown mood %r' % ctx.opts['mood'], 'choose one of: ' + ', '.join(sorted(M.MOODS)))
        why = 'chosen by the caller'
    else:
        mid, why = mood_packs.pick_mood(ctx.read_json('create/prompt.json')['prompt'], clean, ctx.bundle)
    spec_id, mood_arg = None, mid
    if mid == 'brief':
        mood_arg = M.mood_from_brief(clean['palette_mood'], clean.get('mood'))
        spec_id = '%s_m%s' % (base, sha(canon(mood_arg))[:8])
    if not mid:
        out.update(pack=base, mood=None, mood_status='none', mood_reason=why)
        return {'create/style.json': out}
    key = (base, json.dumps(mood_arg, sort_keys=True) if isinstance(mood_arg, dict) else mood_arg)
    if key not in ctx.memo:
        try:
            derived, sp, view, rep = mp.derive_all(base, mood_arg, spec_id, root=ctx.bundle)
            ctx.memo[key] = {'id': derived['id'], 'pack_sha256': rep['pack_sha256'], 'strength': rep.get('strength'),
                             'clamped': rep.get('clamped'), 'style_pack': sp is not None}
        except SystemExit as e:
            ctx.memo[key] = {'refused': one_line(e)}
    d = ctx.memo[key]
    if 'refused' in d:
        out.update(pack=base, mood=mid if isinstance(mid, str) else 'brief', mood_status='refused',
                   mood_reason='mood %s refused for %s, base palette kept: %s' % (mid, base, d['refused']))
        return {'create/style.json': out}
    if not d['style_pack']:
        out.update(pack=base, mood=mid, mood_status='refused',
                   mood_reason='%s has no style pack/view to derive; base palette kept' % base)
        return {'create/style.json': out}
    out.update(pack=d['id'], mood=mid, mood_spec=mood_arg if isinstance(mood_arg, dict) else None,
               mood_status='derived', mood_reason=why, derive=d)
    return {'create/style.json': out}


def stage_mood(ctx):
    """Write the derived mood kit pack into the PROJECT (kits/packs/<id>/pack.json), so the asset stage builds every
    piece in the mood. Nothing is written to the bundle here."""
    style = ctx.read_json('create/style.json')
    out = {'format': 'hermes64-create-mood/1', 'pack': style['pack'], 'base': style['base'], 'derived': False}
    if style.get('mood_status') != 'derived':
        out['note'] = 'no derived mood (%s)' % style.get('mood_status')
        ctx.write('create/mood.json', out)
        return {}
    if ctx.opts.get('no_install_mood'):
        out.update(pack=style['base'], note='mood %s named but not applied (--no-install-mood); base pack used' % style['pack'])
        ctx.write('create/mood.json', out)
        return {}
    mp = bundle_import(ctx, 'tools.mood_pack')
    mood_arg = style.get('mood_spec') or style['mood']
    derived, sp, view, rep = mp.derive_all(style['base'], mood_arg, style['pack'] if style.get('mood_spec') else None,
                                           root=ctx.bundle)
    if derived['id'] != style['pack'] or rep['pack_sha256'] != style['derive']['pack_sha256']:
        raise CreateError('create_mood', 'derived %s (%s) differs from the style choice' % (derived['id'], rep['pack_sha256'][:12]),
                          'run again with --redo style')
    mp.write_derived(ctx.root, derived, sp, view, rep)
    out.update(derived=True, pack_sha256=rep['pack_sha256'], strength=rep.get('strength'), clamped=rep.get('clamped'),
               project_files=['kits/packs/%s/pack.json' % derived['id'], 'packs/%s/view.json' % derived['id']])
    ctx.write('create/mood.json', out)
    return {}


def stage_install(ctx):
    """Install the derived mood pack into the plugin bundle (bindings, view, env), plus the library pieces from other
    kit families that the brief resolved to, so the runtime can bind them. The only mood install path today."""
    mood = ctx.read_json('create/mood.json')
    assets = ctx.read_json('create/assets.json')
    out = {'format': 'hermes64-create-install/1', 'pack': mood['pack'], 'installed': False, 'bundle_writes': []}
    if not mood.get('derived'):
        out['note'] = 'nothing to install: %s is a shipped pack' % mood['pack']
        ctx.write('create/install.json', out)
        return {}
    pid, base = mood['pack'], mood['base']
    from core import pipeline
    reg = pipeline.load_generators()
    base_keys, _ = bindings_keys(ctx, base)
    core_kits = {k['id'] for k in json.loads((ctx.bundle / 'kits/manifest.json').read_text(encoding='utf-8'))['kits']}
    extras = sorted({r['id'] for r in assets['rows'] if r['status'] in ('existed', 'remapped', 'substituted')
                     and r.get('id') in reg and r['id'] not in base_keys and r['id'] not in core_kits})
    mp = bundle_import(ctx, 'tools.mood_pack')
    kit = ctx.bundle / 'kits/packs' / pid / 'pack.json'
    bind = ctx.bundle / 'packs' / pid / 'bindings.json'
    present = kit.is_file() and bind.is_file() and mp.M.pack_sha(json.loads(kit.read_text(encoding='utf-8'))) == mood['pack_sha256']
    style = ctx.read_json('create/style.json')
    if not present:
        summary = mp.install(ctx.bundle, base, style.get('mood_spec') or style['mood'],
                             extra=extras, new_id=pid if style.get('mood_spec') else None, quiet=True)
        out.update(built=summary['built'], failed=sorted(summary['failed']), failed_reasons=summary['failed'])
    else:
        doc = json.loads(bind.read_text(encoding='utf-8'))
        missing = [k for k in extras if k not in doc['assets']]
        failed = {}
        if missing:
            from adventure_maker.glb import srgb8, inspect
            tex = ctx.bundle / 'kits/library' / pid / 'textures'
            for key in missing:
                dest = mp._lib_path(ctx.bundle, pid, key, None)
                dest.parent.mkdir(parents=True, exist_ok=True)
                st, r = pipeline.build_one(key, pid, None, {}, 0, str(dest), tex_dir=str(tex), builder='python', pack_path=str(kit))
                if st != 'passed':
                    failed[key] = one_line(r.get('error') or [k for k, v in (r.get('validation') or {}).items() if not v['ok']])[:200]
                    continue
                conv = srgb8(dest.read_bytes())
                dest.write_bytes(conv)
                doc['assets'][key] = {'glb': str(dest.relative_to(ctx.bundle)), 'kit_id': key, 'preset': None,
                                      'sha256': inspect(conv)['sha256']}
            doc['assets'] = dict(sorted(doc['assets'].items()))
            bind.write_bytes(mp.jdump(doc).encode() if isinstance(mp.jdump(doc), str) else mp.jdump(doc))
        out.update(note='derived pack already installed with the same hash; %d extra keys added' % (len(missing) - len(failed)),
                   failed=sorted(failed), failed_reasons=failed)
    out.update(installed=True, extras=extras,
               bundle_writes=['packs/%s/' % pid, 'kits/packs/%s/' % pid, 'kits/library/%s/' % pid])
    ctx.write('create/install.json', out)
    return {}


def shipped_binding(ctx, p, bdoc, key, pack_id, row):
    """Existing piece tier for a SHIPPED pack: when every rebuilt copy failed a gen_tools gate, the pack's own
    hash-pinned binding GLB (the piece every game on this pack already loads) is used as-is and said so."""
    from .glb import inspect
    from .glb_validate import validate as validate_glb
    from . import provenance
    src = ctx.bundle / bdoc['assets'][key]['glb']
    raw = src.read_bytes()
    if sha(raw) != bdoc['assets'][key].get('sha256'):
        return None
    structural = validate_glb(raw, src.name)
    if not structural.ok:
        return None
    rel = 'assets/kit/shipped/%s.glb' % key.replace('.', '_')
    p.write_bytes(rel, raw)
    info = inspect(raw)
    gates = {'ok': True, 'scope': 'shipped binding of %s: bindings.json hash match + GLB structure; it was not re-gated by '
             'gen_tools (its rebuilt copy failed: %s)' % (pack_id, one_line(row.get('reason', ''))[:200]),
             'binding_sha256': info['sha256'], 'structure': True}
    provenance.record(p.root, {'id': key, 'file': rel, 'sha256': info['sha256'], 'seed': None, 'source': 'kit',
                               'model': 'native-library', 'licence': 'MIT', 'licence_required': True, 'pack': pack_id,
                               'kit_id': key, 'params': {}, 'gates': gates})
    row = dict(row)
    row['attempts'] = row.get('attempts', []) + [{'try': len(row.get('attempts', [])) + 1, 'params': {}, 'ok': True,
                                                  'errors': [], 'shipped_binding': key}]
    row.update(status='existed', id=key, kit_id=key, source='kit', file=rel, sha256=info['sha256'], tri_count=info['tri_count'],
               licence='MIT', model='native-library', shipped_binding=True,
               reason='rebuilt copy failed (%s); the shipped %s binding %s is used as-is' % (
                   one_line(row.get('reason', ''))[:120], pack_id, key))
    return row


def _class_of(gid, tag_rows):
    row = tag_rows.get(gid)
    return (row or {}).get('class') or ''


def _order_matches(matches, pack_keys, prefixes):
    def rank(m):
        return (0 if m in pack_keys else 1 if m.split('.')[0] + '.' in prefixes else 2)
    return sorted(matches, key=lambda m: (rank(m), matches.index(m)))


def stage_assets(ctx):
    from . import asset_loop, asset_report, gen_tools, provenance, taxonomy
    from .packs import Packs
    brief = ctx.read_json('brief.json')
    gaps = copy.deepcopy(ctx.read_json('create/gaps.json'))
    mood = ctx.read_json('create/mood.json')
    pack_id = mood['pack']
    style = Packs(ctx.settings, ctx.service.project(ctx.name)).get(pack_id)
    kit_pack = style['kit_pack_id']
    keys, bdoc = bindings_keys(ctx, mood['base'] if mood.get('derived') else pack_id)   # a derived pack rebinds every base key
    prefixes = {k.split('.')[0] + '.' for k in keys if '.' in k}
    rows = []
    setting_words = {brief['setting'].get('genre')} | set(brief['setting'].get('genre_hints', []))
    for r in gaps['taxonomy']['rows']:
        r = dict(r)
        if r['want'] in setting_words:
            r.update(status='not covered', why='setting word: answered by the style pack choice (%s), not by one asset' % pack_id)
        elif r.get('matches'):
            r['matches'] = _order_matches(r['matches'], keys, prefixes)
        rows.append(r)
    from .genre_kits import PACKS as GP
    from .newgame import CAST
    base = mood['base']
    cast = CAST.get(base) or CAST.get(DEFAULT_PACK)
    from . import create_craft                                                     # VARIETY V1 (5 lines): craft by default
    prompt = ctx.read_json('create/prompt.json')['prompt']
    protagonist = create_craft.craft_protagonist(ctx, prompt, brief)
    for i, c in enumerate(brief.get('characters', [])):
        used = cast[0] if c.get('role') == 'player' else cast[1]
        rows.append({'want': 'character: ' + c['want'], 'status': 'not covered',
                     'why': 'no new character made; the public cast %r stands in' % used})
    rows = create_craft.character_rows(rows, brief, protagonist)                   # VARIETY V1
    rows.append({'want': 'sounds and music', 'status': 'not covered', 'why': 'no new audio; the %s sound palette is used' % pack_id})
    candidates = {}
    if ctx.exists('create/candidates.json'):
        candidates = ctx.read_json('create/candidates.json')
        if not isinstance(candidates, dict):
            raise CreateError('create_candidates', 'create/candidates.json must map brief lines to recipes',
                              'see skills/hermes64-create/SKILL.md')
    rows, candidates, craft = create_craft.plan(prompt, brief, rows, candidates)  # VARIETY V1: brief-named pieces made new
    p = gen_tools.workspace(ctx.root)
    try:
        report = asset_loop.run(p.root, brief, {'rows': rows}, kit_pack, candidates=candidates, seed=SEED, max_tries=4,
                                python_path=ctx.settings.get('python_path', ''))
        report = create_craft.retry_plain(report, rows, craft, lambda gap_rows: asset_loop.run(     # VARIETY V2 (3 lines)
            p.root, brief, {'rows': gap_rows}, kit_pack, candidates={}, seed=SEED, max_tries=4,
            python_path=ctx.settings.get('python_path', '')))
    except (ValueError, gen_tools.RecipeError) as e:
        raise CreateError('create_assets', str(e), 'fix create/candidates.json or brief.json and run again')
    out_rows = []
    substituted = 0
    from core import pipeline
    reg = pipeline.load_generators()
    for row in report['rows']:
        row = dict(row)
        gap = next((g for g in rows if g['want'] == row['want']), {})
        if row['status'] == 'failed' and gap.get('status') == 'exists' and not mood.get('derived'):
            hit = next((m for m in gap.get('matches', []) if isinstance(bdoc['assets'].get(m), dict)
                        and bdoc['assets'][m].get('glb')), None)
            if hit:
                used = shipped_binding(ctx, p, bdoc, hit, pack_id, row)
                if used:
                    row = used
        if row['status'] == 'failed' and gap.get('status') == 'exists' and row.get('source') == 'kit':
            # the first library match failed a gate in this pack: try up to three further matches (same need, same gates)
            first = row.get('id')
            for gid in [m for m in gap.get('matches', []) if m in reg and m != first][:ALT_TRIES]:
                built = gen_tools.build(p.root, gid, kit_pack, seed=SEED, sweep=False, python_path=ctx.settings.get('python_path', ''))
                row['attempts'] = row.get('attempts', []) + [{'try': len(row.get('attempts', [])) + 1, 'params': {}, 'ok': built['ok'],
                                                              'errors': built['errors'], 'alternative': gid}]
                if built['ok']:
                    mooded = bool(gen_tools.resolve_pack(p.root, kit_pack).d.get('mood'))
                    row.update(status='remapped' if mooded else 'existed', id=gid, kit_id=gid, file=built['file'],
                               sha256=built['sha256'], tri_count=built['tri_count'], licence='MIT', model='native-library',
                               alternative_to=first, reason='first match %s failed: %s; next library match %s passed' % (
                                   first, one_line(row.get('reason', ''))[:160], gid))
                    break
        if (row['status'] == 'failed' and gap.get('status') == 'partial' and gap.get('matches')
                and row.get('reason', '').startswith('no recipe supplied')):
            for gid in [m for m in gap['matches'] if m in reg][:ALT_TRIES]:
                built = gen_tools.build(p.root, gid, kit_pack, seed=SEED, sweep=False, python_path=ctx.settings.get('python_path', ''))
                row['attempts'] = row.get('attempts', []) + [{'try': len(row.get('attempts', [])) + 1, 'params': {},
                                                              'ok': built['ok'], 'errors': built['errors'], 'stand_in': gid}]
                if built['ok']:
                    row.update(status='substituted', id=gid, source='kit', kit_id=gid, stand_in=gid, file=built['file'],
                               sha256=built['sha256'], tri_count=built['tri_count'], licence='MIT', model='native-library',
                               reason='no %s in the library and no recipe; used the partial match %s instead' % (row['want'], gid))
                    substituted += 1
                    break
        out_rows.append(row)
    final = asset_report.make(p.root, out_rows, brief)
    final['coverage_scope'] = 'asset definitions for the brief needs; placement is in create/rooms.json'
    final = asset_report.write(p.root, final)
    tag_rows = {r['id']: r for r in taxonomy.rows()}
    counts = {p_['want']: p_['count'] for p_ in brief.get('props', [])}
    imp = {p_['want']: p_['importance'] for p_ in brief.get('props', [])}
    summary = []
    for row in final['rows']:
        item = {k: row.get(k) for k in ('want', 'status', 'id', 'file', 'sha256', 'tri_count', 'stand_in', 'reason', 'source', 'params')}
        item['attempts'] = len(row.get('attempts', []))
        item['count'] = counts.get(row['want'], 1)
        item['importance'] = imp.get(row['want'], 'key')
        gid = row.get('id') or ''
        if gid.startswith('gen:'):
            try:
                item['class'] = gen_tools.load_recipe(p.root, gid).get('class', '')
            except Exception:
                item['class'] = ''
        else:
            item['class'] = _class_of(gid, tag_rows)
        summary.append(item)
    ctx.write('create/assets.json', {'format': 'hermes64-create-assets/1', 'pack': pack_id, 'kit_pack': kit_pack,
                                     'counts': final['counts'], 'ready': final['ready'], 'total': final['total'],
                                     'substituted_here': substituted, 'rows': summary,
                                     'craft': craft, 'protagonist': protagonist})      # VARIETY V3 (this line)
    return {}


# ---------------------------------------------------------------------------------------------------- room plans
class Slots:
    """Deterministic free-spot finder in a pattern's dress area (metres, compiler plot frame)."""
    def __init__(self, pat, seed):
        self.pat = pat
        x0, z0, x1, z1 = pat['dress_rect_m']
        pts = [(x0 + i * 0.5, z0 + j * 0.5) for i in range(int((x1 - x0) / 0.5) + 1) for j in range(int((z1 - z0) / 0.5) + 1)]
        random.Random('%s:%s' % (pat['id'], seed)).shuffle(pts)
        self.points = pts
        self.used = []           # (x, z, r)
        cx, cz = pat['centre_m']
        self.clear = [(cx, cz, 2.2), (pat['npc_m'][0], pat['npc_m'][1], 1.8)]
        self.clear += [tuple(c) for c in pat.get('extra_clear_m', [])]    # story people and story spots (DETAIL)
        cam = (pat.get('plan') or {}).get('camera') or {}
        if cam.get('position'):            # keep the camera's own floor area clear: nothing stands in front of the lens
            self.clear.append((cam['position'][0], cam['position'][2], CAMERA_CLEAR_M))
        self.lanes = [((cx, cz), tuple(pat['door_point_m']))]
        self.vistas = list(pat.get('vista_m', []))
        self.lots = list(pat.get('lots', []))
        self.booms = []          # TFIX F1c: the start room's follow-camera boom (set by dress(); see spawn_boom)

    @staticmethod
    def _seg(p, a, b):
        (px, pz), (ax, az), (bx, bz) = p, a, b
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / max(1e-9, dx * dx + dz * dz)))
        return math.hypot(px - ax - t * dx, pz - az - t * dz)

    def fits(self, x, z, r):
        x0, z0, x1, z1 = self.pat['dress_rect_m']
        if x - r < x0 - 1.0 or x + r > x1 + 1.0 or z - r < z0 - 1.0 or z + r > z1 + 1.0:
            return False
        for bx0, bz0, bx1, bz1 in self.pat.get('blocked_m', []):
            if bx0 - r < x < bx1 + r and bz0 - r < z < bz1 + r:
                return False
        if any(math.hypot(x - cx, z - cz) < cr + r for cx, cz, cr in self.clear):
            return False
        if any(self._seg((x, z), a, b) < 1.4 + r for a, b in self.lanes):
            return False
        if any(self._seg((x, z), a, b) < BOOM_CLEAR_M + r * 1.42 for a, b in self.booms):
            return False
        return all(math.hypot(x - ux, z - uz) >= ur + r + 0.3 for ux, uz, ur in self.used)

    def take(self, r):
        for x, z in self.points:
            if self.fits(x, z, r):
                self.used.append((x, z, r))
                return [round(x, 2), round(z, 2)]
        return None


def _yaw_for(slot, centre):
    return round(math.degrees(math.atan2(centre[0] - slot[0], centre[1] - slot[1])) % 360.0 / 15.0) * 15.0


# FINALINT2 (SCALE x create flow): the brief's optional setting.room_scale picks among a family's create patterns by
# plot size. Both kit compilers (tools.medievalkit_rooms, tools.westernkit_rooms) use 4 m cells and a 0.5 m apron.
KIT_CELL_M, KIT_APRON_M = 4.0, 0.5


def pattern_size_m(pat):
    cx, cz = pat['plan']['plot_cells']
    return KIT_CELL_M * cx + 2 * KIT_APRON_M, KIT_CELL_M * cz + 2 * KIT_APRON_M


def spawn_boom(pat):
    """TFIX F1c: [(spawn, eye)] floor segment of the start room's follow-camera boom (plot frame = runtime frame)."""
    cam = (pat.get('plan') or {}).get('camera') or {}
    if not cam.get('position') or not cam.get('look_at'):
        return []
    w, d = pattern_size_m(pat)
    bx, bz = cam['position'][0] - cam['look_at'][0], cam['position'][2] - cam['look_at'][2]
    n = math.hypot(bx, bz) or 1.0
    return [((w / 2.0, d * 0.7), (w / 2.0 + SPAWN_BOOM_M * bx / n, d * 0.7 + SPAWN_BOOM_M * bz / n))]


LANDMARK_STOP = {'the', 'a', 'an', 'of', 'in', 'to', 's', 'inside', 'interior', 'room'}
LANDMARK_KEEP_M = 9.0      # vista slots this close to the landmark slot are dropped (they would stand in front of it)


def mark_landmark(items, brief, inner_name, pat):
    """TFIX F1a: the first unplaced appended outdoor/vista item whose want words meet the destination (the inside room's
    name or the brief's first build type) takes the pattern's landmark_vista_m slot [x, z, yaw, scale], measured on the
    spawn camera's view. No slot or no match: nothing changes (today's vista order)."""
    if not pat.get('landmark_vista_m'):
        return None
    dest = (set(words(inner_name)) | set(words((brief.get('build_types') or [''])[0]))) - LANDMARK_STOP
    for it in items:
        if not it['placed'] and it['mode'] == 'append' and it['where'] in ('vista', 'outdoor') and it['instance'] == 1 \
                and dest & set(words(it['want'])):
            it['landmark'] = True
            return it
    return None


def brief_room_scale(brief):
    """(scale, reason): the brief's setting.room_scale, else the default for new games (medium)."""
    from . import room_scale as RS
    value = (brief.get('setting') or {}).get('room_scale')
    if value:
        return RS.check_scale(value, 'brief_scale'), 'brief room_scale'
    return RS.default_scale(), 'default for new games'


def choose_pattern(options, bw, keys, scale=None):
    """The pattern with most brief words; large/open take the biggest plot first, small the smallest. medium (the
    default) and no scale keep the word order alone."""
    usable = [p for p in options if set(p.get('only_if_keys', [])) <= keys]
    if not usable:
        raise CreateError('create_rooms', 'no usable room pattern for this pack', 'hand-author the rooms (skill)')
    sign = {'large': -1, 'open': -1, 'small': 1}.get(scale or '', 0)
    area = lambda p: pattern_size_m(p)[0] * pattern_size_m(p)[1]
    return sorted(usable, key=lambda p: (sign * area(p), -len(set(p['tags']) & bw), options.index(p)))[0]


def entry_pattern(fam, family, bw, keys, scale, brief):
    """VARIETY V6: (pattern, why): the word-order choice, or the layout that names more of the brief's setting."""
    from . import create_craft
    return create_craft.setting_pattern(fam['outdoor'], family, choose_pattern(fam['outdoor'], bw, keys, scale),
                                        brief.get('prompt', ''), brief, keys, scale, lambda p: pattern_size_m(p)[0])


def scale_report(scale, reason, outdoor, indoor):
    """(line, rows): the rooms line (plot sizes) and Not applied rows where the create flow cannot match the scale."""
    size = lambda p: '%g x %g m' % pattern_size_m(p)
    line = 'rooms: %s (%s): entry %s %s, inside %s %s plot' % (scale, reason, outdoor['id'], size(outdoor),
                                                               indoor['id'], size(indoor))
    rows = []
    if scale == 'small':
        rows.append({'feature': 'room scale', 'asked': 'small', 'status': 'closest',
                     'reason': 'create rooms are kit patterns; the smallest here are %s and %s' % (size(outdoor), size(indoor)),
                     'closest': 'the smallest patterns (%s, %s)' % (outdoor['id'], indoor['id']),
                     'fix': 'the 4 x 4 m starter: /hermes64 new "<prompt>" small'})
    elif scale == 'open':
        rows.append({'feature': 'room scale', 'asked': 'open', 'status': 'closest',
                     'reason': 'the create flow keeps one inside room', 'closest': 'the largest patterns (%s %s, %s %s)'
                     % (outdoor['id'], size(outdoor), indoor['id'], size(indoor)),
                     'fix': 'both rooms outdoors: /hermes64 new "<prompt>" open'})
    return line, rows


def _piece_info(manifest, key):
    return manifest['pieces'].get(key)


HANGS_WHY = ('it hangs on a wall or ceiling and this planner has no mount for it; standing free it would float '
             '(style gate floating check); not placed')


def hangs(info):
    """VARIETY V8: a kit piece made to hang (banner, sconce, hung lantern): its mesh starts above the floor, so it
    must never stand free as scenery."""
    return bool(info) and info.get('anchor') in ('wall_face', 'ceiling_hook')


def plan_dressing(ctx, assets, family, keys, bindings_doc, gen_ok):
    """Ready asset rows -> placeable instances (asset key, triangles, radius, where it may go)."""
    patterns = load_patterns()['families'].get(family) if family else None
    manifest = json.loads((ctx.bundle / patterns['manifest']).read_text(encoding='utf-8')) if patterns else {'pieces': {}}
    core_kits = {k['id'] for k in json.loads((ctx.bundle / 'kits/manifest.json').read_text(encoding='utf-8'))['kits']}
    items, skipped, presets = [], [], []
    for row in assets['rows']:
        if row['status'] not in ('existed', 'remapped', 'generated', 'converted', 'substituted'):
            continue
        gid = row['id']
        n = 1 if row.get('class') in STRUCTURE_CLASSES else max(1, min(MAX_INSTANCES, int(row.get('count') or 1)))
        info = _piece_info(manifest, gid) if not gid.startswith('gen:') else None
        if gid.startswith('gen:'):
            if not gen_ok:
                skipped.append({'want': row['want'], 'id': gid, 'reason': 'built and gated, but a project pack cannot name a '
                                'gen: recipe until docs/agen-hunks/packs-gen-id.patch is applied; not placed'})
                continue
            key, mode = 'preset/cf_' + gid[4:], 'append'
            presets.append({'id': 'cf_' + gid[4:], 'asset_id': gid, 'params_json': json.dumps(row.get('params') or {}, sort_keys=True)})
        elif info and info.get('anchor') in ('free', 'lot_line', 'lot_centre') and gid in keys:
            key, mode = gid, ('compiler' if info['anchor'] == 'free' else 'lot')
        elif gid in keys and not info:
            key, mode = gid, 'append'
        elif hangs(info) and gid in keys:                                                     # VARIETY V8
            skipped.append({'want': row['want'], 'id': gid, 'reason': HANGS_WHY})
            continue
        elif info and info.get('anchor') not in ('free', 'lot_line', 'lot_centre') and gid in keys:
            # grid/socket pieces cannot be snapped by this planner; they may stand as distant scenery outside the plot
            key, mode = gid, 'vista'
        elif gid in core_kits:
            pid = 'cf_' + gid.replace('.', '_')
            key, mode = 'preset/' + pid, 'append'
            presets.append({'id': pid, 'asset_id': gid, 'params_json': '{}'})
        else:
            skipped.append({'want': row['want'], 'id': gid, 'reason': 'library piece not bound in %s '
                            '(only a derived mood pack can bind extra pieces; pack presets take core kits only); not placed'
                            % assets['pack']})
            continue
        tris = int((info or {}).get('tris') or row.get('tri_count') or 0)
        src = ctx.root / row['file'] if row.get('file') else None
        if gid in bindings_doc['assets'] and isinstance(bindings_doc['assets'][gid], dict) and bindings_doc['assets'][gid].get('glb'):
            src = ctx.bundle / bindings_doc['assets'][gid]['glb']
        radius = glb_radius(src) if src else 1.0
        cls = row.get('class') or ''
        where = 'vista' if (radius > LARGE_RADIUS_M or mode == 'vista') else \
            ('outdoor' if cls in OUTDOOR_CLASSES or mode == 'lot' else 'indoor')
        if mode == 'vista':
            mode = 'append'
            n = 1
        for i in range(n):
            items.append({'want': row['want'], 'id': gid, 'key': key, 'mode': mode, 'tris': tris, 'radius': radius,
                          'where': where, 'instance': i + 1, 'importance': row.get('importance', 'key'), 'status': row['status']})
    items.sort(key=lambda it: (it['instance'] > 1, it['importance'] != 'key'))
    seen, uniq = set(), []
    for pr in presets:
        if pr['id'] not in seen:
            seen.add(pr['id']); uniq.append(pr)
    return items, skipped, uniq


def _compile(mod, plan):
    try:
        return mod.compile_room(copy.deepcopy(plan))
    except mod.PlanError as e:
        raise CreateError('create_rooms', 'kit compiler refused %s: %s' % (plan['id'], e), 'edit create/rooms.json or hand-author the room')


def build_room(ctx, mod, pat, rid, name, desc, door_id, to_room, to_door, label, npc, seed):
    plan = json.loads(json.dumps(pat['plan']).replace('@door', door_id))
    plan.update(id=rid, name=name, description=desc, protagonist='traveller', camera=plan['camera'])
    for d in plan['doors']:
        d.update(to_room=to_room, to_door=to_door, label=label)
    if npc:
        plan['characters'] = {npc: {'position': [pat['npc_m'][0], 0, pat['npc_m'][1]], 'yaw': pat.get('npc_yaw', 0)}}
    return plan


def dress(mod, plan, pat, items, seed, placed, not_placed, room_kind):
    """Add the items meant for this room; compiler-anchored ones go through the kit compiler (checked), the rest are
    appended to the presentation row after compile with the same clearance and triangle accounting."""
    slots = Slots(pat, seed)
    if room_kind == 'outdoor':       # the create flow's start room (entry) is the outdoor one
        slots.booms = spawn_boom(pat)
    lm = pat.get('landmark_vista_m') if room_kind == 'outdoor' and any(
        it.get('landmark') and not it['placed'] for it in items) else None
    if lm:                           # TFIX F1a: nothing else stands on or in front of the landmark slot
        slots.vistas = [v for v in slots.vistas if math.hypot(v[0] - lm[0], v[1] - lm[1]) >= LANDMARK_KEEP_M]
    _room, _pres, rep = _compile(mod, plan)
    budget = ROOM_CAP - ROOM_RESERVE - rep['tri_estimate'] - pat.get('reserve_tris', 0)   # story people/fighters
    appended = []
    for it in items:
        if it['placed']:
            continue
        ok_where = (it['where'] == room_kind) or (room_kind == 'outdoor' and it['where'] == 'vista') or \
                   (room_kind == 'outdoor' and it['where'] == 'indoor' and it.get('overflow'))
        if not ok_where:
            continue
        if it['tris'] > budget:
            it['why'] = 'room triangle budget (%d left, piece %d)' % (budget, it['tris'])
            continue
        if it['mode'] == 'lot':
            if not slots.lots:
                it['why'] = 'no free building lot in the %s pattern' % pat['id']
                continue
            lot = slots.lots.pop(0)
            plan['pieces'].append({'key': it['key'], 'lot': lot})
            try:
                _compile(mod, plan)
            except CreateError as e:
                plan['pieces'].pop()
                it['why'] = e.message
                continue
            spot, yaw = None, None
        else:
            scale = 1
            if it.get('landmark') and lm:
                spot, yaw, scale = [lm[0], lm[1]], float(lm[2]), lm[3]
                lm = None
            elif it['where'] == 'vista':
                if not slots.vistas:
                    it['why'] = 'no free distant slot for a large piece'
                    continue
                v = slots.vistas.pop(0)
                spot, yaw = [v[0], v[1]], float(v[2])
            else:
                spot = slots.take(it['radius'])
                if spot is None:
                    it['why'] = 'no clear spot left in the %s dress area' % pat['id']
                    continue
                yaw = _yaw_for(spot, pat['centre_m'])
            if it['mode'] == 'compiler':
                plan['pieces'].append({'key': it['key'], 'at_m': spot, 'yaw': yaw})
                try:
                    _compile(mod, plan)
                except CreateError as e:
                    plan['pieces'].pop()
                    it['why'] = e.message
                    continue
            else:
                appended.append({'asset': it['key'], 'position': [spot[0], 0.0, spot[1]], 'scale': [scale] * 3, 'yaw': yaw})
        budget -= it['tris']
        it['placed'] = True
        placed.append({'want': it['want'], 'id': it['id'], 'asset': it['key'], 'room': plan['id'], 'mode': it['mode'],
                       'at_m': spot, 'lot': plan['pieces'][-1].get('lot') if it['mode'] == 'lot' else None,
                       'tris': it['tris'], 'instance': it['instance']})
    room, pres, rep = _compile(mod, plan)
    pres['pieces'] = list(pres['pieces']) + appended
    rep = dict(rep, appended_pieces=len(appended), appended_tris=sum(p['tris'] for p in placed
                                                                       if p['room'] == plan['id'] and p['mode'] == 'append'))
    rep['tri_estimate_with_appended'] = rep['tri_estimate'] + rep['appended_tris']
    return room, pres, rep


def _title(text, fallback):
    t = ' '.join(w.capitalize() for w in words(text)[:5])
    return t or fallback


# ------------------------------------------------------------------------------------- story block (lane DETAIL)
def story_layout(ctx, outdoor, indoor):
    """(story doc, layout or None): the brief's story block laid out on the two room patterns."""
    from . import create_story as CS
    doc = ctx.read_json('create/story.json') if ctx.exists('create/story.json') else {}
    if doc.get('format') != CS.FORMAT or doc.get('empty'):
        return doc, None
    try:
        return doc, CS.layout(doc, {'entry': outdoor, 'inside': indoor}, Slots, SEED)
    except CS.StoryError as e:
        raise CreateError(e.code, e.message, e.next_step)


def story_hints(brief, story):
    """(brief with the story's routes, rows): a fight for foes/waves, a course for course words, none for no combat."""
    from . import create_story as CS
    if not story or story.get('empty') or story.get('format') != CS.FORMAT:
        return brief, []
    hints, notes = CS.hints_for(story, brief['setting'].get('genre_hints', []))
    rows = [{'feature': 'gameplay', 'asked': 'brief genre hints', 'status': 'closest', 'reason': n,
             'closest': 'the story wins', 'fix': 'remove the hint from the brief'} for n in notes]
    return dict(brief, setting=dict(brief['setting'], genre_hints=hints)), rows


def name_rows(prompt, brief, story):
    from . import create_story as CS
    return [{'feature': 'name in the prompt', 'asked': n, 'status': 'not_made',
             'reason': 'the prompt names it; neither the brief nor the story block uses it', 'closest': 'none',
             'fix': 'add it to story.cast, places or item (or tell the human why it is left out)'}
            for n in CS.prompt_names(prompt, brief, story)]


def weather_rows(ctx, brief, mood):
    """TFIX F6: a weather the game's pack does not render is said in the report, never silent (one mood per game;
    only a hand-made variant named for that weather renders it)."""
    w = str((brief.get('mood') or {}).get('weather') or '').strip().lower()
    if w in ('', 'none', 'clear') or (not mood.get('derived') and w in _pack_words(mood.get('pack', ''), ctx)):
        return []
    return [{'feature': 'weather', 'asked': w, 'status': 'not_made', 'reason': 'weather: %s is story text, not rendered' % w,
             'closest': 'story beats', 'fix': 'none in the create flow (the pack has one light and sky per game)'}]


def stage_rooms(ctx):
    from .packs import Packs, fingerprint, validate_pack
    from .newgame import CAST, COLLECTIBLE_ASSET, title_for
    from .genre_kits import PACKS as GP
    brief = ctx.read_json('brief.json')
    assets = ctx.read_json('create/assets.json')
    mood = ctx.read_json('create/mood.json')
    prompt = ctx.read_json('create/prompt.json')['prompt']
    pack_id, base = mood['pack'], mood['base']
    style = Packs(ctx.settings, ctx.service.project(ctx.name)).get(pack_id)
    keys, bdoc = bindings_keys(ctx, pack_id)
    family = family_for(base)
    gen_ok = gen_presets_supported()
    bw = set(brief_words(brief))
    items, skipped, presets = plan_dressing(ctx, assets, family, keys, bdoc, gen_ok)
    for it in items:
        it['placed'] = False
    placed, notes = [], []
    api = place_api()
    rooms_doc = {'format': 'hermes64-create-rooms/1', 'family': family, 'place_api': bool(api), 'pack': pack_id}
    entry_name = _title(brief['setting'].get('place', ''), 'Arrival')
    inner_name = _title((brief.get('build_types') or ['inside'])[0], 'Inside')
    if family is None:
        raise CreateError('create_rooms', 'no room pattern or kit compiler covers the %s pack family yet' % base,
                          'pass --style with a medieval or western pack, or hand-author the rooms (skills/hermes64-create)')
    fam = load_patterns()['families'][family]
    mod = bundle_import(ctx, fam['compiler'])
    scale, scale_reason = brief_room_scale(brief)      # FINALINT2: medium (default) keeps the word-based choice
    outdoor, layout_why = entry_pattern(fam, family, bw, keys, scale, dict(brief, prompt=prompt))      # VARIETY V6
    indoor = choose_pattern(fam['indoor'], bw, keys, scale)
    rooms_doc['layout'] = {'entry': outdoor['id'], 'why': layout_why}                                  # VARIETY V6
    story, lay = story_layout(ctx, outdoor, indoor)
    brief, not_applied = story_hints(brief, story)     # the story's fight / course / no-combat words route modules too
    if lay is not None:      # people and story spots are kept clear of the dressing, and their triangles are kept free
        from .create_story import PERSON_TRIS, MAX_AT_ONCE, COMBAT_HINTS
        n_in = sum(1 for a in lay['actors'] if a['room'] == 'inside')
        n_out = sum(1 for a in lay['actors'] if a['room'] == 'entry')
        fights = bool(set(brief['setting'].get('genre_hints', [])) & set(COMBAT_HINTS))
        outdoor = dict(outdoor, extra_clear_m=lay['reserve']['entry'], reserve_tris=PERSON_TRIS * max(0, n_out - 1))
        indoor = dict(indoor, extra_clear_m=lay['reserve']['inside'],
                      reserve_tris=PERSON_TRIS * (n_in + (MAX_AT_ONCE if fights else 0)))
        entry_name, inner_name = lay['rooms']['entry'] or entry_name, lay['rooms']['inside'] or inner_name
    desc = one_line(prompt)[:200]
    out_plan = build_room(ctx, mod, outdoor, 'entry', entry_name, desc, 'to_inside', 'inside', 'to_outside',
                          'Go inside', 'inhabitant', SEED)
    inner_res = None
    # MERGEPREP (orch x orch2 on a tree with PLACEMAKER): routed gameplay modules are positioned on create patterns
    # only, so a brief that routes one keeps the create pattern; module-free briefs still get a matching archetype.
    wants_modules = bool(route_modules(sorted(set(brief['setting'].get('genre_hints', []))))[0])
    if api is not None and lay is None and wants_modules:
        notes.append('placemaker archetype not used: the brief routes gameplay modules, which are placed on create '
                     'patterns')
    elif api is not None and lay is None and scale != brief_room_scale({})[0]:
        notes.append('placemaker archetype not used: the brief asks room_scale %s, which picks among create patterns'
                     % scale)
    elif api is not None and lay is None:      # a story lays out its people on the create pattern
        inner_res = _place_inner(api, family, base, bw, notes)
    if inner_res is not None:
        res, room_i, pres_i, rep_i = inner_res
        rooms_doc['inner_source'] = 'placemaker archetype %s (seed %s)' % (res['archetype'], res['params'].get('seed'))
        rooms_doc['placemaker'] = {'archetype': res['archetype'], 'plan_sha256': res['plan_sha256'], 'gaps': res.get('gaps')}
        room_i['id'] = 'inside'
        unbound = sorted({pc.get('asset') for pc in pres_i['pieces'] if pc.get('asset') and pc['asset'] not in keys
                          and not str(pc['asset']).startswith(('preset/', '_'))})
        if unbound:     # placemaker builds foreign recipes in its own scratch bundle; here they are not bound, so dropped
            pres_i['pieces'] = [pc for pc in pres_i['pieces'] if pc.get('asset') not in unbound]
            notes.append('placemaker pieces not bound in %s were removed from the inside room: %s' % (pack_id, ', '.join(unbound)))
        for d in room_i['doors']:
            d.update(to_room='entry', to_door='to_inside', label='Go back outside')
        out_plan['doors'][0]['to_door'] = room_i['doors'][0]['id']
    else:
        in_plan = build_room(ctx, mod, indoor, 'inside', inner_name, desc, 'to_outside', 'entry', 'to_inside',
                             'Go back outside', None, SEED)
        rooms_doc['inner_source'] = 'create pattern %s (%s)' % (indoor['id'], indoor['source'])
        room_i, pres_i, rep_i = dress(mod, in_plan, indoor, items, SEED, placed, None, 'indoor')
    for it in items:                      # props that did not fit inside may stand outside
        if not it['placed'] and it['where'] == 'indoor':
            it['overflow'] = True
    mark_landmark(items, brief, inner_name, outdoor)      # TFIX F1a: the destination as room 1's landmark
    from . import create_craft                            # VARIETY V4 (2 lines): else the brief's crafted landmark
    create_craft.mark_landmark(items, outdoor, assets)
    room_o, pres_o, rep_o = dress(mod, out_plan, outdoor, items, SEED, placed, None, 'outdoor')
    rooms_doc['entry_source'] = 'create pattern %s (%s)' % (outdoor['id'], outdoor['source'])
    not_placed = skipped + [{'want': it['want'], 'id': it['id'], 'instance': it['instance'],
                             'reason': it.get('why', 'no room took it')} for it in items if not it['placed']]
    # Reserved floor lights use the existing emissive light role, rather than tiny fire cores.
    # The lamp stays within the brazier's reserved footprint and below the lowest room ceiling.
    lamps = accent_lamps(pres_o, outdoor)
    if inner_res is None:
        lamps = accent_lamps(pres_i, indoor) or lamps
    if lamps:
        presets.append({'id': 'cf_accent_lamp', 'asset_id': 'furn.lamp', 'params_json': json.dumps({
            'kind': 'floor', 'height': 1.8, 'shade': 'drum', 'shade_size': 0.8,
            'base': 'tripod', 'stand_role': 'metal'})})
    # project pack: the chosen style pack + presets for pieces not bound in it (foreign families, gen: recipes)
    pack = copy.deepcopy(style)
    used = {p['asset'] for p in placed} | {pc.get('asset') for pc in pres_o['pieces'] + pres_i['pieces']}
    keep = [p for p in pack['presets'] if 'preset/' + p['id'] in used]
    mine = [p for p in presets if 'preset/' + p['id'] in used]
    pack['presets'] = (keep + mine)[:32] or pack['presets'][:1]
    pack['name'] = (pack['name'] + ' (create: ' + ctx.name + ')')[:120]
    body = dict(pack); body.pop('id')
    pack['id'] = ('cf_' + re.sub(r'[^a-z0-9]', '_', ctx.name)[:40] + '_' + sha(canon(body))[:8])
    validate_pack(pack)
    ref = {'id': pack['id'], 'sha256': fingerprint(pack)}
    # story: the shipped two-room collect template, on the dressed rooms
    cast = CAST.get(base) or CAST.get(DEFAULT_PACK)
    collect = GP[base]['collectible'] if base in GP else COLLECTIBLE_ASSET
    npc_want = next((c['want'] for c in brief.get('characters', []) if c.get('role') != 'player'), 'inhabitant')
    title = title_for(prompt)
    params = {'costume': 'plain', 'colour': style['palette'][0], 'voice_tags': []}
    characters = [{'id': 'traveller', 'name': 'Traveller', 'role': 'protagonist', 'body_id': 'core_humanoid',
                   'base_rig_id': 'human_16', 'params': dict(params), 'role_profiles': {'protagonist': dict(params)}},
                  {'id': 'inhabitant', 'name': _title(npc_want, 'Inhabitant')[:40], 'role': 'host', 'body_id': 'core_humanoid',
                   'base_rig_id': 'human_16', 'params': dict(params), 'role_profiles': {'host': dict(params), 'guide': dict(params)}}]
    bindings_path = ctx.bundle / 'bindings.json'
    rows = json.loads(bindings_path.read_text(encoding='utf-8')).get('characters', []) if bindings_path.is_file() else []
    public = {r.get('character_id'): r for r in rows if isinstance(r, dict) and r.get('public_release')}
    for ch, cid in zip(characters, cast):
        if cid in public:
            r = public[cid]
            ch.update(body_id=r['body_id'], base_rig_id=r['base_rig_id'], params=copy.deepcopy(r['params']))
            ch['role_profiles'] = {role: copy.deepcopy(r['params']) for role in ch['role_profiles']}
    room_o['character_ids'] = ['traveller', 'inhabitant']
    room_i['character_ids'] = ['traveller']
    keep_at = keepsake_spot(indoor if inner_res is None else None, pres_i, inner_res)
    if keep_at is not None:     # on the floor (y 0); the runtime default without a position is 0.60 m up
        pres_i['collectibles'] = {'keepsake': {'position': keep_at}}
    else:
        notes.append('keepsake: no floor spot known for the inside room; the runtime default height is used')
    spec = {'contract_version': '1.1.0', 'id': re.sub(r'[^a-z0-9_]', '_', ctx.name), 'title': title, 'description': desc,
            'metadata': {'template': 'create_two_room_collect_v1', 'authoring_status': 'create_flow_not_demo',
                         'created_by': 'hermes64 create', 'protagonist': 'traveller', 'style_pack': pack_id,
                         'hermes64_pack': ref,
                         'presentation': {'convention': 'hermes64-presentation/1', 'rotation_order': 'YXZ',
                                          'rotation_units': 'degrees', 'rooms': {'entry': pres_o, 'inside': pres_i}}},
            'start': {'location': 'entry', 'inventory': [], 'flags': {'finished': False}, 'dialogue': {},
                      'tide': {'state': 'calm', 'tick': 0}, 'collected': []},
            'rooms': [room_o, room_i], 'characters': characters, 'items': [],
            'flags': [{'id': 'finished', 'initial': False, 'description': 'Bring the keepsake back.'}],
            'dialogues': [], 'quests': [],
            'interactions': [{'id': 'finish', 'room': 'entry', 'kind': 'use', 'target': 'rest', 'label': 'Finish the journey',
                              'text': 'The keepsake is home.', 'conditions': [{'group': 'keepsakes', 'at_least': 1}],
                              'effects': [{'flag': 'finished', 'value': True}]}],
            'tide': {'id': 'cycle', 'states': [{'id': 'calm', 'label': 'Calm', 'duration': 1}], 'wait_label': 'Wait',
                     'wait_text': 'A moment passes.'},
            'endings': [{'id': 'rest', 'conditions': [{'flag': 'finished', 'equals': True}], 'text': 'The journey ends.'}],
            'collectible_groups': [{'id': 'keepsakes', 'name': 'Keepsakes', 'kind': 'keepsake', 'required': 1}],
            'collectibles': [{'id': 'keepsake', 'group': 'keepsakes', 'room': 'inside', 'name': 'Keepsake',
                              'label': 'Collect the keepsake', 'text': 'Something worth finding.', 'asset': collect,
                              'character': '', 'dialogue': '', 'follower_flag': '', 'conditions': []}]}
    made, mod_not_made = [], []
    if inner_res is None:
        spec, made, mod_not_made, _unrouted = attach_modules(spec, brief, {'entry': outdoor, 'inside': indoor})
    elif brief['setting'].get('genre_hints'):
        routed, _u = route_modules(sorted(set(brief['setting']['genre_hints'])))
        mod_not_made = [{'word': w, 'module': m, 'reason': 'the inside room is a placemaker archetype; module positions '
                         'are derived from create patterns only'} for w, m in routed]
    _routed, unrouted = route_modules(sorted(set(brief['setting'].get('genre_hints', []))))
    covered = set(brief['setting'].get('genre_hints', [])) - set(unrouted)
    hints = sorted(((set(brief['setting'].get('genre_hints', [])) | set(brief.get('unrecognised', [])) | bw)
                    & GAMEPLAY_WORDS) - covered)
    not_applied += list(story.get('notes', []))
    if lay is not None:
        from . import create_story as CS
        pool = list(cast) + [c for c in ('fv_elder', 'neri', 'sol', 'ivo', 'luma') if c in public and cast[0] in public
                             and public[c]['body_id'] == public[cast[0]]['body_id']]
        spec, rows = CS.apply(spec, story, lay, made, [public[c] for c in dict.fromkeys(pool) if c in public],
                              {'entry': outdoor, 'inside': indoor})
        not_applied += rows + CS.mechanic_rows(story)
    scale_line, scale_rows = scale_report(scale, scale_reason, outdoor, indoor)
    if inner_res is not None:
        scale_line = scale_line.split(', inside ')[0] + ', inside: ' + rooms_doc['inner_source']
    not_applied += scale_rows
    rooms_doc['room_scale'] = {'scale': scale, 'reason': scale_reason, 'line': scale_line,
                               'entry_plot_m': list(pattern_size_m(outdoor)),
                               'inside_plot_m': list(pattern_size_m(indoor)) if inner_res is None else None}
    not_applied += name_rows(prompt, brief, story if lay is not None else None)
    not_applied += weather_rows(ctx, brief, mood)        # TFIX F6
    not_applied += create_craft.report_rows(assets)      # VARIETY V5 (2 lines): craft misses are rows; the made cast plays
    spec = create_craft.apply_cast(spec, assets)
    rooms_doc.update(rooms=[{'id': 'entry', 'pattern': outdoor['id'], 'report': rep_o},
                            {'id': 'inside', 'pattern': indoor['id'] if inner_res is None else 'placemaker', 'report': rep_i}],
                     placed=placed, not_placed=not_placed, notes=notes,
                     gameplay_template='two-room collect and return' + (' + ' + ', '.join(m['module'] for m in made) if made else ''),
                     gameplay_made=made, gameplay_modules_not_made=mod_not_made,
                     gameplay_not_made=hints, gen_presets_supported=gen_ok, pack_ref=ref, not_applied=not_applied)
    return {'create/rooms.json': rooms_doc, 'create/pack.json': pack, 'source/spec.json': spec}


MODULES = Path(__file__).with_name('create_modules.json')
CAPABILITIES = {'create.story_1_3_adoption': False}    # the flow does not drive STORY 1.3 module-pointer adoption yet


def load_modules(path=None):
    return json.loads(Path(path or MODULES).read_text(encoding='utf-8'))


def module_missing(requires):
    """The first required piece this plugin tree lacks, or None."""
    import importlib.util
    for req in requires:
        if req in CAPABILITIES:
            if not CAPABILITIES[req]:
                return req
            continue
        try:
            if importlib.util.find_spec(req) is None:
                return req
        except (ImportError, ValueError):
            return req
    return None


def route_modules(hints, table=None):
    """Brief genre hints -> [(hint, module id)] in route order, each module once. Unrouted hints are returned too."""
    table = table or load_modules()
    out, seen, routed = [], set(), set()
    for route in table['routes']:
        hit = [h for h in hints if h in route['hints']]
        if hit:
            routed |= set(hit)
            if route['module'] not in seen:
                seen.add(route['module'])
                out.append((hit[0], route['module']))
    return out, [h for h in hints if h not in routed]


def _slug(text, fallback):
    s = re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')[:32]
    return s if re.fullmatch(r'[a-z][a-z0-9_]*', s or '') else fallback


def attach_modules(spec, brief, rooms_pat, table=None):
    """Turn the routed gameplay words into STORY 1.2 modules on the two-room spec (data only). Returns
    (spec, made, not_made). Bots must still be able to finish: every module gates the keepsake or the finish
    interaction, so the ending is reachable only through it."""
    table = table or load_modules()
    hints = sorted(set(brief['setting'].get('genre_hints', [])))
    routed, unrouted = route_modules(hints, table)
    made, not_made, mods, checkpoints, challenges = [], [], {}, [], []
    entry_c = rooms_pat['entry']['centre_m']
    checkpoints.append({'id': 'entry_safe', 'position_m': [entry_c[0], 0, entry_c[1]], 'room': 'entry'})
    for word, mid in routed:
        m = table['modules'].get(mid)
        if m is None:
            not_made.append({'word': word, 'module': mid, 'reason': 'module %s is not in create_modules.json' % mid})
            continue
        miss = module_missing(m.get('requires', []))
        if miss:
            not_made.append({'word': word, 'module': mid, 'reason': m.get('missing_reason') or
                             'module %s needs %s, which this plugin tree does not have' % (mid, miss)})
            continue
        if any(c['room'] == m['room'] for c in challenges):
            not_made.append({'word': word, 'module': mid, 'reason': 'room %s already holds a challenge' % m['room']})
            continue
        pat = rooms_pat[m['room']]
        cx, cz = pat['centre_m']
        dx, dz = pat['door_point_m']
        safe = '%s_safe' % m['room']
        if m['room'] != 'entry':
            checkpoints.append({'id': safe, 'position_m': [dx, 0, dz], 'room': m['room']})
        if mid == 'combat_arena':
            enemy = next((c['want'] for c in brief.get('characters', []) if c.get('role') in ('enemy', 'boss')), m['enemy_default'])
            aid = _slug(enemy.split(',')[0], 'rival')
            a = m['archetype']
            arche = {'id': aid, 'name': _title(enemy.split(',')[0], 'Rival')[:40], 'max_health': a['max_health'],
                     'speed_mps': a['speed_mps'], 'aggro_range_m': a['aggro_range_m'], 'leash_range_m': a['leash_range_m'],
                     'attack_range_m': a['attack_range_m'], 'attack': dict(a['attack']),
                     'fsm': {'initial': 'idle', 'template': a['template'],
                             'states': ['idle', 'approach', 'telegraph', 'attack', 'recover', 'hurt', 'dead']}}
            x0, z0, x1, z1 = pat['dress_rect_m']
            offs = [(-1.5, -1.0), (1.5, -1.0), (0.0, -1.8)][:max(1, min(3, m['spawns']))]
            spawns = [{'id': '%s_%d' % (aid, i + 1), 'archetype': aid, 'position_m': [round(cx + ox, 2), 0, round(cz + oz, 2)], 'wave': 0}
                      for i, (ox, oz) in enumerate(offs)]
            mods.setdefault('combat', {'id': 'combat', 'version': '1.0.0', 'config': {'max_simultaneous': 3},
                                       'entities': {'archetypes': [], 'encounters': []}})
            mods['combat']['entities']['archetypes'].append(arche)
            mods['combat']['entities']['encounters'].append({
                'id': m['challenge'] + '_arena', 'room': m['room'], 'arena': {'min': [x0, 0, z0], 'max': [x1, 4, z1]},
                'double_ko': 'failure', 'lose': 'player_health_zero', 'win': 'all_spawns_defeated', 'spawns': spawns})
            challenges.append({'id': m['challenge'], 'kind': 'combat', 'room': m['room'], 'subject': m['challenge'] + '_arena',
                               'checkpoint': safe, 'conditions': [], 'retry': 'checkpoint', 'rewards': {'abilities': [], 'items': []}})
            for c in spec['collectibles']:
                c['conditions'] = list(c.get('conditions', [])) + [{'challenge': m['challenge'], 'status': 'completed'}]
            made.append({'word': word, 'module': mid, 'room': m['room'], 'challenge': m['challenge'],
                         'enemies': [s['id'] for s in spawns], 'text': m['made'] % (len(spawns), arche['name'])})
        elif mid == 'timed_course':
            lane = [round(cx + 0.6 * (dx - cx), 2), round(cz + 0.6 * (dz - cz), 2)]
            back = [round(cx + 1.6, 2), round(cz, 2)]
            mods.setdefault('course', {'id': 'course', 'version': '1.0.0',
                                       'config': {'max_speed_mps': m['max_speed_mps'], 'mover': 'on_foot', 'simulation_hz': 60},
                                       'entities': {'tracks': []}})
            mods['course']['entities']['tracks'].append({
                'id': m['challenge'] + '_track', 'room': m['room'], 'laps': 1, 'start_position_m': [cx, 0, cz],
                'countdown_ticks': m['countdown_ticks'], 'par_ticks': m['par_ticks'], 'time_limit_ticks': m['time_limit_ticks'],
                'pause_policy': 'freeze', 'checkpoints': [{'id': 'lane', 'position_m': [lane[0], 0, lane[1]], 'radius_m': 0.5},
                                                          {'id': 'finish', 'position_m': [back[0], 0, back[1]], 'radius_m': 0.5}]})
            challenges.append({'id': m['challenge'], 'kind': 'course', 'room': m['room'], 'subject': m['challenge'] + '_track',
                               'checkpoint': safe, 'conditions': [], 'retry': 'checkpoint', 'rewards': {'abilities': [], 'items': []}})
            for it in spec['interactions']:
                if it['id'] == 'finish':
                    it['conditions'] = list(it['conditions']) + [{'challenge': m['challenge'], 'status': 'completed'}]
            made.append({'word': word, 'module': mid, 'room': m['room'], 'challenge': m['challenge'],
                         'text': m['made'] % (m['time_limit_ticks'] // 60)})
        else:
            not_made.append({'word': word, 'module': mid, 'reason': 'the create flow has no builder for module %s' % mid})
    if challenges:
        spec['contract_version'] = '1.2.0'
        order = [{'id': 'abilities', 'version': '1.0.0', 'config': {'max_health': 6}, 'entities': {'abilities': []}},
                 {'id': 'challenge', 'version': '1.0.0', 'config': {'entry_cost': 'none', 'failure_progress': 'unchanged', 'max_active': 1},
                  'entities': {'challenges': challenges, 'checkpoints': checkpoints}}]
        order += [mods[k] for k in ('combat', 'course') if k in mods]
        spec['gameplay'] = {'api_version': '1.0.0', 'modules': order, 'seed': SEED, 'verification_policy': 'conditional'}
        spec['start']['modules'] = {'abilities': [], 'active': '', 'checkpoint': 'entry_safe', 'completed': [],
                                    'discovered': [], 'failed': ''}
        spec['metadata']['template'] = 'create_two_room_collect_modules_v1'
    return spec, made, not_made, unrouted


def keepsake_spot(pattern, pres, inner_res):
    """Floor point for the keepsake: the pattern's room centre, which the dresser keeps clear (2.2 m) and the door
    lane reaches. y is 0: kit props stand on their base, so the piece rests on the floor (style gate floating check)."""
    centre = None
    if pattern is not None:
        centre = pattern.get('keepsake_m') or pattern.get('centre_m')
    elif inner_res is not None:
        plan = inner_res[0].get('plan') or {}
        centre = plan.get('centre_m') or plan.get('keepsake_m')
    if not centre or len(centre) != 2:
        return None
    return [round(float(centre[0]), 2), 0.0, round(float(centre[1]), 2)]


def accent_lamps(pres, pat):
    """Replace only the reserved create-pattern sources; no metric kit scaling or palette edits."""
    spots = {tuple(p['at_m']) for p in pat['plan']['pieces'] if p['key'] == 'cst.brazier'}
    changed = False
    for p in pres['pieces']:
        x, y, z = p['position']
        if p['asset'] == 'cst.brazier' and y == 0 and (x, z) in spots:
            p['asset'] = 'preset/cf_accent_lamp'
            changed = True
    return changed


def _place_inner(api, family, base, bw, notes):
    """Use a PLACEMAKER archetype for the inner room when one matches this kit family and the brief's words."""
    best = None
    try:
        for aid in api.list_archetypes():
            doc = api.load_archetype(aid)
            if doc.get('kit') != family or doc.get('exterior'):
                continue
            score = len(bw & set(words(' '.join(doc.get('genres', [])) + ' ' + aid)))
            if score and (best is None or score > best[0]):
                best = (score, aid)
        if best is None:
            notes.append('placemaker present, but no interior archetype matches this brief; create pattern used')
            return None
        res = api.make_plan(best[1], {'seed': SEED})
        doors = res['plan']['doors']
        room, pres, rep = api.compile(res, {d['id']: ('entry', 'to_inside', 'Go back outside') for d in doors})
        return res, room, pres, rep
    except Exception as e:      # the place API is optional; its refusal is recorded, never fatal
        notes.append('placemaker archetype refused (%s); create pattern used' % one_line(e)[:200])
        return None


def stage_build(ctx):
    pack = ctx.read_json('create/pack.json')
    calls = []

    def call(tool, required=True, **args):
        begin = time.monotonic()
        result = ctx.call(tool, **args)
        err = result.get('error') if isinstance(result.get('error'), dict) else {}
        calls.append({'tool': tool, 'ok': bool(result.get('ok')), 'status': result.get('status', err.get('code')),
                      'seconds': round(time.monotonic() - begin, 2), 'report_path': result.get('report_path'),
                      'error': one_line(err.get('message', ''))[:300] or None})
        ctx.write('create/build.json', {'format': 'hermes64-create-build/1', 'calls': calls, 'complete': False})
        if required and not result.get('ok'):
            raise CreateError('create_' + tool, '%s failed: %s' % (tool, one_line(err.get('message') or result.get('status'))[:300]),
                              'read create/build.json, fix source/spec.json or create/pack.json, run again')
        return result

    local = ctx.root / 'packs' / pack['id'] / 'pack.json'
    if not local.is_file():
        call('pack_create', pack_json=json.dumps(pack))
    compiled = call('compile', spec_path='source/spec.json')
    checked = call('check', required=False)
    built = call('build_assets', seed=SEED, required=False)
    out = {'format': 'hermes64-create-build/1', 'calls': calls, 'complete': True,
           'compile': compiled.get('status'), 'check': checked.get('status'),
           'check_witnesses': checked.get('witnesses'), 'build_assets': built.get('status'),
           'proof_path': checked.get('report_path'), 'assets_path': built.get('report_path')}
    if built.get('ok'):
        rep = ctx.read_json(built['report_path'])
        out['room_shells'] = rep.get('room_shells')
        out['built'] = rep.get('built')
        out['records'] = len(rep.get('records', []))
    ctx.write('create/build.json', out)
    if not built.get('ok'):
        raise CreateError('create_build_assets', 'build_assets failed: %s' % (calls[-1]['error'] or built.get('status')),
                          'read create/build.json; a refused recipe or missing binding is named there')
    return {}


def stage_playtest(ctx):
    from . import playtest
    project = ctx.service.project(ctx.name)
    with project.lock():
        result = playtest.run(ctx.service, project, {'mode': 'both', 'seconds': 10, 'seed': SEED})
    rep = ctx.read_json(result['report_path']) if result.get('report_path') else {}
    native = rep.get('native') or rep      # the playtest report carries the native probe fields at top level
    raw_rooms = native.get('rooms') if isinstance(native.get('rooms'), dict) else {}
    rooms = {rid: {'triangles': r.get('triangles'), 'draw_calls': r.get('draw_calls')} for rid, r in raw_rooms.items()}
    spec = ctx.read_json('source/spec.json')
    gated = [c['id'] for m in (spec.get('gameplay') or {}).get('modules', []) if m['id'] == 'challenge'
             for c in m['entities']['challenges']]
    out = {'format': 'hermes64-create-playtest/1', 'status': result.get('status'), 'ok': bool(result.get('ok')),
           'reasons': result.get('reasons', []), 'bot_completed': native.get('completed'),
           'goal_check': 'ending "rest" (finished flag) after collecting the keepsake' + (
               ' (gated by challenge %s)' % ', '.join(gated) if gated else ''), 'rooms': rooms,
           'module_attempts': native.get('attempts', []) if gated else [],
           'events': native.get('events', []), 'paths': native.get('paths', []),
           'stuck': len(native.get('stuck') or []), 'unreachable': len(native.get('unreachable') or []),
           'missing_assets': len(native.get('missing_assets') or []),
           'report_path': result.get('report_path'), 'html_path': result.get('html_path')}
    ctx.write('create/playtest.json', out)
    return {}


def camera_candidates(pat, knobs):
    """Bounded camera/light candidates for one room pattern. Candidate 0 is the pattern camera itself; the rest
    come from the pattern's camera_alternates (or the knob defaults). Anything outside the knobs is refused."""
    base = pat['plan']['camera']
    alts = pat.get('camera_alternates', knobs['default_alternates'])
    out = [{'id': 'pattern', 'camera': copy.deepcopy(base), 'lights': []}]
    for alt in alts[:max(0, knobs['max_candidates'] - 1)]:
        pos, look = list(base['position']), list(base['look_at'])
        if alt.get('move_back_m'):
            dx, dz = pos[0] - look[0], pos[2] - look[2]
            n = math.hypot(dx, dz) or 1.0
            pos = [pos[0] + dx / n * alt['move_back_m'], pos[1], pos[2] + dz / n * alt['move_back_m']]
        pos = [round(a + b, 3) for a, b in zip(pos, alt.get('position_delta', [0, 0, 0]))]
        look = [round(a + b, 3) for a, b in zip(look, alt.get('look_at_delta', [0, 0, 0]))]
        cam = {'fov': alt.get('fov', base.get('fov', 60)), 'position': pos, 'look_at': look}
        lights = []
        if alt.get('light'):
            lt = alt['light']
            if lt.get('at') == 'near':         # in the near band: a point ahead of the lens along the view direction
                vx, vz = look[0] - pos[0], look[2] - pos[2]
                n = math.hypot(vx, vz) or 1.0
                at = [round(pos[0] + vx / n * lt.get('ahead_m', 6.0), 3), round(lt.get('lift_m', 1.5), 3),
                      round(pos[2] + vz / n * lt.get('ahead_m', 6.0), 3)]
            else:
                at = [look[0], round(look[1] + lt.get('lift_m', 1.0), 3), look[2]]
            lights.append({'position': at, 'intensity': lt['intensity'], 'radius': lt['radius'], 'color': lt.get('color', '#ffffff')})
        moved = math.hypot(pos[0] - base['position'][0], pos[2] - base['position'][2])
        bad = []
        if not knobs['fov'][0] <= cam['fov'] <= knobs['fov'][1]:
            bad.append('fov %s outside %s' % (cam['fov'], knobs['fov']))
        if abs(pos[1] - base['position'][1]) > knobs['height_delta_m'] + 1e-9:
            bad.append('height change %.2f m > %.2f' % (abs(pos[1] - base['position'][1]), knobs['height_delta_m']))
        if abs(look[1] - base['look_at'][1]) > knobs['look_y_delta_m'] + 1e-9:
            bad.append('look height change > %.2f m' % knobs['look_y_delta_m'])
        if moved > knobs['move_delta_m'] + 1e-9:
            bad.append('camera moved %.2f m > %.2f' % (moved, knobs['move_delta_m']))
        if len(lights) > knobs['light']['max_lights'] or any(
                l['intensity'] > knobs['light']['intensity_max'] or l['radius'] > knobs['light']['radius_max'] for l in lights):
            bad.append('light outside intensity <= %s, radius <= %s' % (knobs['light']['intensity_max'], knobs['light']['radius_max']))
        if bad:
            raise CreateError('create_camera', 'camera candidate %s for %s is outside the knobs: %s' % (
                alt.get('id', '?'), pat['id'], '; '.join(bad)), 'keep camera_alternates inside camera_knobs (create_patterns.json)')
        out.append({'id': alt.get('id', 'alt%d' % len(out)), 'camera': cam, 'lights': lights})
    return out


def _retryable(reasons, knobs):
    """A failure a camera/light candidate could change (anything but floating pieces and uncut doors)."""
    return any(not any(r.startswith(n) for n in knobs['never_retry']) for r in reasons)


def _apply_camera(spec, rid, cand):
    spec = copy.deepcopy(spec)
    pres = spec['metadata']['presentation']['rooms'][rid]
    cam = dict(pres['cameras'][0], position=cand['camera']['position'], look_at=cand['camera']['look_at'], fov=cand['camera']['fov'])
    pres['cameras'] = [cam] + list(pres['cameras'][1:])
    room = next(r for r in spec['rooms'] if r['id'] == rid)
    if room.get('cameras'):
        room['cameras'] = [dict(room['cameras'][0], position=cam['position'], look_at=cam['look_at'])] + list(room['cameras'][1:])
    if cand['lights']:            # spec is always the rooms-stage spec, so its own lights (if any) stay first
        pres['lights'] = list(pres.get('lights', [])) + [dict(l) for l in cand['lights']]
    return spec


def _n64(result, root):
    from . import n64_gate
    theme_path = (result.get('process') or {}).get('theme_path')
    screens = root / Path(result['report_path']).parent / 'screens'
    theme = json.loads(Path(theme_path).read_text(encoding='utf-8')) if theme_path else {}
    return n64_gate.gate_folder(screens, theme)


def _open_measure(ctx, secs):
    """One open/capture: style gate rooms plus the N64 gate reasons per room (both count when a camera is chosen)."""
    result = ctx.call('open', seconds=secs, screenshots=True)
    sg = result.get('style_gate') or {}
    rooms = {r['id']: dict(r) for r in (sg.get('rooms') or [])}
    if result.get('report_path'):
        try:
            for r in _n64(result, ctx.root).get('rooms', []):
                if r.get('id') in rooms:
                    rooms[r['id']]['n64_reasons'] = list(r.get('reasons', []))
        except Exception as e:
            for r in rooms.values():
                r['n64_reasons'] = ['n64 gate not run: %s' % one_line(e)[:120]]
    return result, rooms


def _fails(r):
    return len((r or {}).get('reasons', [])) + len((r or {}).get('n64_reasons', [])) if r else 99


def frame_rooms(ctx, result, rooms_sg, secs):
    """Measure loop over the bounded camera/light candidates for rooms whose style-gate failure is about framing or
    values. Thresholds are never touched; every attempt is recorded. Returns (result, rooms_sg, attempts, choice)."""
    patterns = load_patterns()
    knobs = patterns['camera_knobs']
    rooms_doc = ctx.read_json('create/rooms.json')
    fam = patterns['families'].get(rooms_doc.get('family') or '', {})
    pats = {}
    for r in rooms_doc.get('rooms', []):
        pat = next((p for p in fam.get('outdoor', []) + fam.get('indoor', []) if p['id'] == r['pattern']), None)
        if pat is not None:
            pats[r['id']] = pat
    spec0 = ctx.read_json('source/spec.json')
    cands = {rid: camera_candidates(p, knobs) for rid, p in pats.items()}
    attempts = [{'candidate': {rid: 'pattern' for rid in pats}, 'rooms': {rid: {'status': r.get('status'), 'reasons': r.get('reasons', []), 'n64_reasons': r.get('n64_reasons', [])}
                                                                         for rid, r in rooms_sg.items()}}]
    best = {rid: (0, rooms_sg.get(rid)) for rid in pats}

    def failing():
        return [rid for rid, (_i, r) in best.items() if r and _fails(r) and _retryable(r.get('reasons', []) + r.get('n64_reasons', []), knobs)]
    if not failing():
        return result, rooms_sg, attempts, {rid: 'pattern' for rid in pats}
    n = max(len(c) for c in cands.values())
    for i in range(1, n):
        todo = [rid for rid in failing() if i < len(cands[rid])]
        if not todo:
            break
        if ctx.remaining() is not None and ctx.remaining() < 60:
            attempts.append({'note': 'time budget: camera candidates stopped at %d' % i})
            break
        spec = spec0
        for rid in pats:
            spec = _apply_camera(spec, rid, cands[rid][i if rid in todo else best[rid][0]])
        ctx.write('create/frame/spec.json', spec)
        comp = ctx.call('compile', spec_path='create/frame/spec.json')
        if not comp.get('ok'):
            attempts.append({'candidate': {rid: cands[rid][i]['id'] for rid in todo}, 'compile': 'refused',
                             'error': one_line((comp.get('error') or {}).get('message', ''))[:200]})
            continue
        res, sg = _open_measure(ctx, secs)
        attempts.append({'candidate': {rid: cands[rid][i if rid in todo else best[rid][0]]['id'] for rid in pats},
                         'rooms': {rid: {'status': r.get('status'), 'reasons': r.get('reasons', []), 'n64_reasons': r.get('n64_reasons', [])} for rid, r in sg.items()}})
        for rid in todo:
            r = sg.get(rid)
            old = best[rid][1]
            if r and _fails(r) < _fails(old):        # fewer style + N64 reasons; ties keep the earlier candidate
                best[rid] = (i, r)
    choice = {rid: cands[rid][best[rid][0]]['id'] for rid in pats}
    spec = spec0
    for rid in pats:
        spec = _apply_camera(spec, rid, cands[rid][best[rid][0]])
    if all(v == 'pattern' for v in choice.values()):
        comp = ctx.call('compile', spec_path='source/spec.json')        # back to the pattern build
    else:
        ctx.write('create/frame/spec.json', spec)
        comp = ctx.call('compile', spec_path='create/frame/spec.json')
    res, sg = _open_measure(ctx, secs)                                    # the final measured frames are of the chosen build
    attempts.append({'candidate': choice, 'final': True,
                     'rooms': {rid: {'status': r.get('status'), 'reasons': r.get('reasons', []), 'n64_reasons': r.get('n64_reasons', [])} for rid, r in sg.items()}})
    return res, sg, attempts, choice


def stage_capture(ctx):
    from . import n64_gate
    secs = int(ctx.opts.get('open_seconds') or OPEN_SECONDS)
    if ctx.exists('create/frame/spec.json'):     # an earlier camera choice is current: measure the pattern build first
        ctx.path('create/frame/spec.json').unlink()
        comp = ctx.call('compile', spec_path='source/spec.json')
        if not comp.get('ok'):
            raise CreateError('create_capture', 'recompiling source/spec.json failed: %s' % one_line(
                (comp.get('error') or {}).get('message', '')), 'run again with --redo build')
    result, rooms_sg = _open_measure(ctx, secs)
    attempts, choice = [], {}
    if result.get('report_path') and not ctx.opts.get('no_camera_retry'):
        result, rooms_sg, attempts, choice = frame_rooms(ctx, result, rooms_sg, secs)
    out = {'format': 'hermes64-create-captures/1', 'ok': bool(result.get('ok')), 'status': result.get('status'),
           'report_path': result.get('report_path'), 'frames': [], 'camera_attempts': attempts, 'camera_choice': choice,
           'camera_build': 'create/frame/spec.json' if any(v != 'pattern' for v in choice.values()) else 'source/spec.json'}
    if not result.get('report_path'):
        out['error'] = one_line((result.get('error') or {}).get('message', 'open returned no report'))
        ctx.write('create/captures.json', out)
        raise CreateError('create_capture', out['error'], 'check godot_path / a display; the game itself is built')
    run_dir = ctx.root / Path(result['report_path']).parent
    screens = run_dir / 'screens'
    dest = ctx.path('create/captures')
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for f in sorted(screens.glob('*.png')) if screens.is_dir() else []:
        shutil.copy2(f, dest / f.name)
        out['frames'].append('create/captures/' + f.name)
    sg = result.get('style_gate') or {}
    out['style_gate'] = {'status': sg.get('status'), 'set_reasons': sg.get('set_reasons'),
                         'rooms': sg.get('rooms'), 'report_path': sg.get('report_path')}
    theme_path = (result.get('process') or {}).get('theme_path')
    try:
        theme = json.loads(Path(theme_path).read_text(encoding='utf-8')) if theme_path else {}
        ng = n64_gate.gate_folder(screens, theme)
        out['n64'] = {'status': ng.get('status'), 'rooms': [{'id': r.get('id'), 'status': r.get('status'),
                                                              'reasons': r.get('reasons', [])} for r in ng.get('rooms', [])]}
    except Exception as e:
        out['n64'] = {'status': 'not_run', 'reason': one_line(e)[:200]}
    out['capture'] = result.get('capture')
    ctx.write('create/captures.json', out)
    if not result.get('ok'):
        raise CreateError('create_capture', 'open/capture did not pass: %s' % one_line(result.get('status')),
                          'read %s' % result['report_path'])
    return {}


# --------------------------------------------------------------------------------------------------- report/score
def closeness(asset_report, rooms, build, play, caps, consistency_ok, prov_ok):
    """Needs coverage, placement, gates and first-try attempts. Not an aesthetic score."""
    total = asset_report.get('total') or 0
    ready = asset_report.get('ready') or 0
    coverage = ready / total if total else 0.0
    ready_wants = {r['want'] for r in asset_report.get('rows', []) if r['status'] in
                   ('generated', 'converted', 'remapped', 'existed', 'substituted')}
    placed_wants = {p['want'] for p in (rooms or {}).get('placed', [])}
    placement = len(placed_wants & ready_wants) / len(ready_wants) if ready_wants else 0.0
    gates = {'compile': (build or {}).get('compile') == 'compiled',
             'story_check': (build or {}).get('check') in ('proved', 'conditional'),
             'build_assets': (build or {}).get('build_assets') == 'passed',
             'asset_report_consistent': bool(consistency_ok),
             'provenance_export_ok': bool(prov_ok),
             'bots_finished': bool((play or {}).get('bot_completed')),
             'style_gate': ((caps or {}).get('style_gate') or {}).get('status') == 'passed',
             'n64_fidelity': ((caps or {}).get('n64') or {}).get('status') == 'passed'}
    gate_frac = sum(gates.values()) / len(gates)
    first = [r for r in asset_report.get('rows', []) if r['status'] in ('generated', 'remapped', 'existed', 'converted')]
    first_try = sum(1 for r in first if len(r.get('attempts', [])) == 1) / len(first) if first else 0.0
    score = round(100 * (0.5 * coverage + 0.15 * placement + 0.3 * gate_frac + 0.05 * first_try), 1)
    return {'score': score, 'coverage': round(coverage, 3), 'placement': round(placement, 3),
            'gates': gates, 'gate_fraction': round(gate_frac, 3), 'first_try': round(first_try, 3),
            'formula': '100 x (0.5 coverage of brief needs + 0.15 placed share of ready needs + 0.3 gates passed + 0.05 first-try share)',
            'note': 'Closeness to the brief\'s listed needs and to the gates. Not an aesthetic score; looks are for the owner to judge.'}


def plain_lines(asset_report, rooms, style, mood):
    lines = []
    for r in asset_report.get('rows', []):
        w = r['want']
        if r['status'] == 'failed':
            lines.append('I could not make "%s": %s. Nothing was put in its place.' % (w, r.get('reason') or 'no recipe'))
        elif r['status'] == 'substituted':
            lines.append('There is no "%s" in the library and no recipe for it; I used %s instead.' % (w, r.get('stand_in')))
        elif r.get('shipped_binding'):
            lines.append('For "%s" I used the shipped piece %s as-is: %s.' % (w, r.get('id'), r.get('reason')))
        elif r.get('alternative_to'):
            lines.append('For "%s" I used %s because the first library match %s failed a gate in this pack.' % (
                w, r.get('id'), r.get('alternative_to')))
        elif r['status'] == 'not covered':
            lines.append('"%s" is not covered: %s.' % (w, r.get('reason') or 'outside this flow'))
    for n in (rooms or {}).get('not_placed', []):
        lines.append('"%s" (%s) was made but not placed in a room: %s.' % (n['want'], n['id'], n['reason']))
    for g in (rooms or {}).get('gameplay_made', []):
        lines.append('For \"%s\" I added %s (module %s, STORY 1.2).' % (g['word'], g['text'], g['module']))
    for g in (rooms or {}).get('gameplay_modules_not_made', []):
        lines.append('The prompt asks for \"%s\" (module %s); not made: %s.' % (g['word'], g['module'], g['reason']))
    for g in (rooms or {}).get('gameplay_not_made', []):
        lines.append('The prompt asks for "%s"; the game uses the two-room collect-and-return template, so that gameplay '
                     'was not made.' % g)
    for n in style.get('pack_notes', []):
        lines.append('Style: %s.' % n)
    if style.get('mood_status') in ('refused', 'none') and style.get('mood_reason'):
        asked = style.get('palette_asked')
        lines.append('Palette%s not applied: %s; the pack keeps its own colours.' % (
            ' %r' % asked if asked else '', style['mood_reason']))
    for a in style.get('adjustments', []):
        lines.append('Palette word: %s.' % a)
    if mood.get('pack') != style.get('pack'):
        lines.append('Mood: %s.' % mood.get('note'))
    return lines


def story_summary(spec):
    """What the game's story data holds (names as written), for the report and the agent's reply."""
    prot = spec.get('metadata', {}).get('protagonist', 'traveller')
    names = {c['id']: c['name'] for c in spec.get('characters', [])}
    mods = (spec.get('gameplay') or {}).get('modules', [])
    foes = [a['name'] for m in mods if m['id'] == 'combat' for a in m['entities']['archetypes']]
    return {'player': names.get(prot), 'rooms': [r['name'] for r in spec.get('rooms', [])],
            'people': ['%s (%s)' % (names[c], r['id']) for r in spec.get('rooms', []) for c in r.get('character_ids', []) if c != prot],
            'item': [c['name'] for c in spec.get('collectibles', [])], 'beats': sum(1 for a in spec.get('interactions', [])
                                                                                if a['id'].startswith('beat_')),
            'quests': [q['title'] for q in spec.get('quests', [])], 'endings': len(spec.get('endings', [])),
            'clock': [t['label'] for t in spec.get('tide', {}).get('states', [])] if len(spec.get('tide', {}).get('states', [])) > 1 else [],
            'fighters': foes, 'modules': [m['id'] for m in mods if m['id'] not in ('abilities', 'challenge')]}


from .creation_reply import how_to_play


def made_new_line(ctx):
    """VARIETY V7: the report's one line on what this run made new (the hero and the brief-named pieces)."""
    from . import create_craft
    return create_craft.made_line(ctx.read_json('create/assets.json') if ctx.exists('create/assets.json') else {})


def stage_report(ctx, state):
    from . import asset_report as AR, provenance
    ar = ctx.read_json('ASSET-REPORT.json')
    style = ctx.read_json('create/style.json')
    mood = ctx.read_json('create/mood.json')
    brief = ctx.read_json('brief.json')
    rooms = ctx.read_json('create/rooms.json') if ctx.exists('create/rooms.json') else {}
    build = ctx.read_json('create/build.json') if ctx.exists('create/build.json') else {}
    play = ctx.read_json('create/playtest.json') if ctx.exists('create/playtest.json') else {}
    caps = ctx.read_json('create/captures.json') if ctx.exists('create/captures.json') else {}
    inst = ctx.read_json('create/install.json') if ctx.exists('create/install.json') else {}
    consistency = AR.verify(ctx.root, ar, bundle_root=ctx.bundle)
    try:
        prov = provenance.validate_export(ctx.root, bundle_root=ctx.bundle)
    except Exception as e:
        prov = {'ok': False, 'errors': [one_line(e)]}
    from . import brief as B
    ledger = [{'stage': s, **{k: v for k, v in state['stages'].get(s, {}).items() if k in ('status', 'seconds', 'runs', 'error')}}
              for s in ORDER if s != 'report']
    score = closeness(ar, rooms, build, play, caps, consistency['ok'], prov.get('ok'))
    rep = {'format': REPORT_FORMAT, 'project': ctx.name, 'prompt': ctx.read_json('create/prompt.json')['prompt'],
           'brief_summary': B.summary(brief), 'brief_filled_by': brief.get('filled_by'),
           'style': {k: style.get(k) for k in ('base', 'pack', 'mood', 'mood_status', 'mood_reason', 'reason', 'candidates',
                                               'pack_notes')},
           'mood_install': {k: inst.get(k) for k in ('pack', 'installed', 'built', 'failed', 'extras', 'bundle_writes', 'note')},
           'asset_counts': ar['counts'], 'asset_ready': ar['ready'], 'asset_total': ar['total'],
           'made_new': made_new_line(ctx),                                                       # VARIETY V7
           'asset_consistency': consistency, 'provenance': {'ok': prov.get('ok'), 'errors': prov.get('errors', [])[:8],
                                                            'assets': len(provenance.load(ctx.root).get('assets', []))},
           'rooms': [{'id': r['id'], 'pattern': r['pattern'], 'tri_estimate': r['report'].get('tri_estimate_with_appended',
                      r['report'].get('tri_estimate'))} for r in rooms.get('rooms', [])],
           'rooms_source': {'entry': rooms.get('entry_source'), 'inside': rooms.get('inner_source'),
                            'place_api': rooms.get('place_api')},
           'room_scale': rooms.get('room_scale'),
           'placed': len(rooms.get('placed', [])), 'not_placed': rooms.get('not_placed', []),
           'build': {k: build.get(k) for k in ('compile', 'check', 'build_assets', 'room_shells')},
           'playtest': {k: play.get(k) for k in ('status', 'bot_completed', 'goal_check', 'rooms', 'stuck', 'unreachable',
                                                 'missing_assets', 'reasons', 'html_path')},
           'captures': {'frames': caps.get('frames', []), 'style_gate': (caps.get('style_gate') or {}).get('status'),
                        'style_rooms': (caps.get('style_gate') or {}).get('rooms'),
                        'n64': (caps.get('n64') or {}).get('status'), 'n64_rooms': (caps.get('n64') or {}).get('rooms'),
                        'camera_choice': caps.get('camera_choice'), 'camera_attempts': len([a for a in caps.get('camera_attempts', [])
                                                                                            if 'rooms' in a])},
           'could_not_make': plain_lines(ar, rooms, style, mood), 'not_applied': rooms.get('not_applied', []),
           'story': story_summary(ctx.read_json('source/spec.json')) if ctx.exists('source/spec.json') else {},
           'ledger': ledger, 'closeness': score,
           'note': 'Measured numbers and named gaps only. Appearance is for the owner to judge.'}
    rep['how_to_play'] = how_to_play(ctx.root, ctx.settings, caps, play)
    ctx.write('CREATE-REPORT.json', rep)
    ctx.write('CREATE-REPORT.md', report_md(rep).encode())
    return {}


def report_md(rep):
    L = ['# Create report: %s' % rep['project'], '', 'Prompt: "%s"' % rep['prompt'], '',
         'Brief (%s): %s' % (rep['brief_filled_by'], rep['brief_summary']), '',
         'In the game: %s' % '; '.join('%s %s' % (k, ', '.join(map(str, v)) if isinstance(v, list) else v)
                                       for k, v in (rep.get('story') or {}).items() if v not in (None, [], 0, '')), '',
         'Style: base `%s`, pack `%s`; mood %s (%s). %s' % (rep['style']['base'], rep['style']['pack'], rep['style']['mood'],
                                                             rep['style']['mood_status'], rep['style']['mood_reason'] or ''), '',
         'Pack choice: %s' % (rep['style'].get('reason') or ''), '',
         '## Stage ledger', '', '| stage | status | seconds | runs | error |', '|---|---|---:|---:|---|']
    for r in rep['ledger']:
        L.append('| %s | %s | %s | %s | %s |' % (r['stage'], r.get('status', 'not run'), r.get('seconds', ''), r.get('runs', ''),
                                              (r.get('error') or '').replace('|', '/')))
    c = rep['asset_counts']
    L += ['', '## Assets', '', 'Ready %d of %d needs: %s.' % (rep['asset_ready'], rep['asset_total'],
          ', '.join('%s %d' % (k, v) for k, v in c.items())),
          rep.get('made_new') or 'Made new for this game: not recorded.',                        # VARIETY V7
          'Report consistency: %s. Provenance export check: %s (%d asset records).' % (
              rep['asset_consistency']['ok'], rep['provenance']['ok'], rep['provenance']['assets']),
          '', '## What I could not make and what I used instead', '']
    L += ['- ' + x for x in rep['could_not_make']] or ['- nothing named']
    from .create_story import row_line
    L += ['', '## Not applied (story, mechanics, names)', '']
    L += ['- ' + row_line(r) for r in rep.get('not_applied', [])] or ['- nothing']
    L += ['', '## Rooms', '']
    if rep.get('room_scale'):
        L.append('- ' + rep['room_scale']['line'][0].upper() + rep['room_scale']['line'][1:])
    for r in rep['rooms']:
        L.append('- `%s` (pattern %s): estimated %s triangles' % (r['id'], r['pattern'], r['tri_estimate']))
    L.append('- placed pieces: %d; sources: entry = %s; inside = %s' % (rep['placed'], rep['rooms_source']['entry'],
                                                                        rep['rooms_source']['inside']))
    b, p, k = rep['build'], rep['playtest'], rep['captures']
    L += ['', '## Gates', '', '- compile: %s; story check: %s; build_assets: %s' % (b.get('compile'), b.get('check'), b.get('build_assets')),
          '- bots: %s, finished: %s (goal: %s); stuck %s, unreachable %s, missing assets %s' % (
              p.get('status'), p.get('bot_completed'), p.get('goal_check'), p.get('stuck'), p.get('unreachable'), p.get('missing_assets')),
          '- runtime rooms: %s' % json.dumps(p.get('rooms')),
          '- style gate: %s; N64 fidelity: %s' % (k.get('style_gate'), k.get('n64')),
          '- style gate rooms: %s' % ('; '.join('%s %s%s' % (r.get('id'), r.get('status'), (' (' + ', '.join(r.get('reasons', [])) + ')')
                                                           if r.get('reasons') else '') for r in (k.get('style_rooms') or [])) or 'none'),
          '- cameras: %s after %s measured capture(s) (bounded knobs in create_patterns.json camera_knobs)' % (
              json.dumps(k.get('camera_choice') or {}), k.get('camera_attempts') or 1),
          '', '## Closeness score', '', '%s / 100. %s' % (rep['closeness']['score'], rep['closeness']['formula']),
          'Gates: %s' % ', '.join('%s=%s' % (g, v) for g, v in rep['closeness']['gates'].items()),
          rep['closeness']['note'], '', '## Captures', '']
    L += ['- ' + f for f in k.get('frames', [])] or ['- none']
    L += ['', *rep.get('how_to_play', {}).get('lines', []), '', rep['note'], '']
    return '\n'.join(L)


# ----------------------------------------------------------------------------------------------------- the runner
ORDER = ('project', 'brief', 'gaps', 'style', 'mood', 'assets', 'install', 'rooms', 'build', 'playtest', 'capture', 'report')
SPEC = {   # inputs, outputs, pure (run twice and compared), min seconds left to start
    'project': ((), ('create/prompt.json',), False, 5),
    'brief': (('create/prompt.json',), ('brief.json', 'create/story.json'), True, 2),
    'gaps': (('brief.json',), ('create/gaps.json',), True, 2),
    'style': (('brief.json', 'create/gaps.json', 'create/prompt.json'), ('create/style.json',), True, 10),
    'mood': (('create/style.json',), ('create/mood.json',), False, 10),
    'install': (('create/mood.json', 'create/assets.json'), ('create/install.json',), False, 90),
    'assets': (('brief.json', 'create/gaps.json', 'create/mood.json', 'create/candidates.json'),
               ('ASSET-REPORT.json', 'create/assets.json'), False, 60),
    'rooms': (('brief.json', 'create/assets.json', 'create/mood.json', 'create/install.json', 'create/prompt.json',
               'create/story.json'),
              ('create/rooms.json', 'create/pack.json', 'source/spec.json'), True, 10),
    'build': (('source/spec.json', 'create/pack.json'), ('create/build.json',), False, 60),
    'playtest': (('create/build.json',), ('create/playtest.json',), False, 40),
    'capture': (('create/build.json',), ('create/captures.json',), False, 60),
    'report': (('ASSET-REPORT.json', 'create/rooms.json', 'create/build.json', 'create/playtest.json',
                'create/captures.json', 'create/style.json', 'create/mood.json', 'create/install.json'), ('CREATE-REPORT.json', 'CREATE-REPORT.md'), False, 1),
}
FUNCS = {'project': stage_project, 'brief': stage_brief, 'gaps': stage_gaps, 'style': stage_style, 'mood': stage_mood, 'install': stage_install,
         'assets': stage_assets, 'rooms': stage_rooms, 'build': stage_build, 'playtest': stage_playtest,
         'capture': stage_capture, 'report': stage_report}
STAGE_OPTS = {'brief': ('brief_file',), 'style': ('style', 'mood'), 'mood': ('no_install_mood',),
              'capture': ('open_seconds', 'no_camera_retry')}


def file_hash(ctx, rel):
    path = ctx.path(rel)
    return sha(path.read_bytes()) if path.is_file() else None


def input_hash(ctx, name):
    ins, _o, _p, _m = SPEC[name]
    parts = {rel: file_hash(ctx, rel) for rel in ins}
    opts = {k: ctx.opts.get(k) for k in STAGE_OPTS.get(name, ())}
    if name == 'brief' and ctx.opts.get('brief_file'):
        opts['brief_file'] = sha(Path(ctx.opts['brief_file']).read_bytes())
    return sha(canon({'inputs': parts, 'opts': opts, 'stage_code': STAGE_CODE_VERSION}))


STAGE_CODE_VERSION = 4


def load_state(ctx):
    path = ctx.path(STATE)
    if path.is_file():
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('format') != FORMAT:
            raise CreateError('create_state', 'unknown state format in %s' % path, 'move the project aside and start again')
        return state
    return {'format': FORMAT, 'project': ctx.name, 'stages': {}, 'runs': 0}


def save_state(ctx, state):
    ctx.write(STATE, state)


def run(settings, name, prompt=None, opts=None):
    """Run or resume every stage. Returns the state; raises CreateError (one line) on the first failure."""
    opts = dict(opts or {})
    budget = float(opts.get('budget_seconds') or DEFAULT_BUDGET)
    start = time.monotonic()
    ctx = Ctx(settings, name, prompt, opts, deadline=start + budget)
    root = settings.get('projects_root', '')
    if root and root == default_games_folder() and not Path(root).exists():
        Path(root).mkdir(parents=True, exist_ok=True)   # NATIVE: first run, the same default folder as /hermes64 new
    if not Path(settings.get('projects_root', '')).is_absolute() or not Path(settings['projects_root']).is_dir():
        raise CreateError('create_root', 'the games folder %r does not exist' % settings.get('projects_root'),
                          'set projects_root in the Hermes64 plugin settings to an existing folder, or pass '
                          '--projects-root with one')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name or ''):
        raise CreateError('create_name', 'project name %r is not a short lowercase slug' % name, 'use e.g. --name wizard-tower')
    state = load_state(ctx) if (ctx.root / STATE).is_file() else {'format': FORMAT, 'project': name, 'stages': {}, 'runs': 0}
    if prompt and state['stages'].get('project', {}).get('status') == 'done':
        old = ctx.read_json('create/prompt.json')['prompt']
        if old != prompt:
            raise CreateError('create_exists', 'project %r was created for a different prompt (%r)' % (name, old[:80]),
                              'pick another --name, or resume without a prompt')
    state['runs'] += 1
    redo = set(opts.get('redo') or ())
    until = opts.get('until')
    dirty = False
    for stage in ORDER:
        if until and ORDER.index(stage) > ORDER.index(until):
            break
        ins, outs, pure, min_s = SPEC[stage]
        rec = state['stages'].get(stage, {})
        if stage != 'project' and not (ctx.root / '.maker/project.json').is_file():
            raise CreateError('create_project', 'project %r does not exist yet' % name, 'run with a prompt first')
        h = input_hash(ctx, stage) if stage != 'project' else sha(canon({'project': name}))
        if stage == 'brief' and not opts.get('brief_file') and rec.get('from_brief_file') and stage not in redo \
                and rec.get('status') in ('done', 'overridden'):
            h = rec['inputs']     # a resume without --brief keeps the agent's brief and story (DETAIL)
        outs_now = {rel: file_hash(ctx, rel) for rel in outs}
        if rec.get('status') in ('done', 'overridden') and rec.get('inputs') == h and stage not in redo and not dirty \
                and all(outs_now.values()) and stage != 'report':
            if outs_now != rec.get('outputs'):
                rec.update(status='overridden', outputs=outs_now,
                           note='output edited after the run; kept as the agent\'s override')
                state['stages'][stage] = rec
                save_state(ctx, state)
            continue
        remaining = ctx.remaining()
        if remaining is not None and remaining < min_s:
            state['paused'] = {'at': stage, 'reason': 'time budget left %.0f s < %d s needed to start %s' % (remaining, min_s, stage)}
            save_state(ctx, state)
            raise CreateError('create_paused', state['paused']['reason'], 'run again to resume at %s' % stage)
        dirty = True if stage in redo else dirty
        begin = time.monotonic()
        rec = {'status': 'running', 'inputs': h, 'runs': rec.get('runs', 0) + 1}
        state['stages'][stage] = rec
        state.pop('paused', None)
        if stage != 'project':
            save_state(ctx, state)
        try:
            if stage == 'report':
                FUNCS[stage](ctx, state)
            elif pure:
                first = FUNCS[stage](ctx)
                second = FUNCS[stage](ctx)
                if canon(first) != canon(second):
                    diff = sorted(k for k in set(first) | set(second) if canon(first.get(k)) != canon(second.get(k)))
                    raise CreateError('create_nondeterministic', 'stage %s gave different output for the same inputs (%s)'
                                      % (stage, ', '.join(diff)), 'report this; the stage must be deterministic')
                for rel, obj in first.items():
                    ctx.write(rel, obj)
            else:
                FUNCS[stage](ctx)
        except CreateError as e:
            rec.update(status='failed', error=e.line(), seconds=round(time.monotonic() - begin, 2))
            if (ctx.root / '.maker/project.json').is_file():
                save_state(ctx, state)
            raise
        except Exception as e:
            err = CreateError('create_' + stage, '%s: %s' % (type(e).__name__, e), 'read the traceback with --debug; resume runs this stage again')
            rec.update(status='failed', error=err.line(), seconds=round(time.monotonic() - begin, 2))
            if (ctx.root / '.maker/project.json').is_file():
                save_state(ctx, state)
            if opts.get('debug'):
                raise
            raise err from None
        rec.update(status='done', seconds=round(time.monotonic() - begin, 2),
                   outputs={rel: file_hash(ctx, rel) for rel in outs})
        if stage == 'brief':
            rec['from_brief_file'] = bool(opts.get('brief_file'))
        rec.pop('error', None)
        dirty = True
        save_state(ctx, state)
    state['how_to_play'] = how_to_play(ctx.root, settings,
        ctx.read_json('create/captures.json') if ctx.exists('create/captures.json') else {},
        ctx.read_json('create/playtest.json') if ctx.exists('create/playtest.json') else {})
    return state


def status_lines(state):
    out = []
    for s in ORDER:
        r = state['stages'].get(s)
        if not r:
            out.append('%-9s not run' % s)
        else:
            out.append('%-9s %-10s %6ss  %s' % (s, r['status'], r.get('seconds', ''), r.get('error', '')))
    if state.get('paused'):
        out.append('paused at %s: %s' % (state['paused']['at'], state['paused']['reason']))
    return out


def command_create(settings, premise, style=None, name=None, default_root=None, scale=None):
    """`/hermes64 new --create "<prompt>"` (hook in docs/ORCH-NEWGAME-PATCH.md): the same doctor/root rules as `new`,
    then this flow. Returns the reply text: 4-5 lines, or one plain failure line. scale: an optional room-scale word
    (small/medium/large/open) for the keyword brief."""
    from . import newgame
    try:
        if scale not in (None, ''):
            from .room_scale import check_scale
            scale = check_scale(scale)
        premise = newgame.normalize_premise(premise)
        name = newgame.slug(premise) if name in (None, '') else newgame.check_name(name)
        tools = newgame.preflight(settings)
        root, uses_default = newgame.resolve_root(settings, default_root)
        if uses_default:
            root.mkdir(parents=True, exist_ok=True)
        s = dict(settings, projects_root=str(root), builder=settings.get('builder') or 'python')
        s.setdefault('godot_path', tools.get('godot') or '')
        opts = {'style': style or None}
        if scale:
            opts['room_scale'] = scale
        run(s, name, premise, opts)
        rep = json.loads((root / name / 'CREATE-REPORT.json').read_text(encoding='utf-8'))
        play = rep['playtest']
        lines = ['Made "%s" in %s (create flow)' % (rep['prompt'][:60], root / name),
                 'Style: %s, mood %s (%s)' % (rep['style']['pack'], rep['style']['mood'], rep['style']['mood_status']),
                 'Needs: %d of %d ready (%s); bots finished: %s; closeness %s/100 (needs, gates, attempts; not looks)' % (
                     rep['asset_ready'], rep['asset_total'], ', '.join('%s %d' % (k, v) for k, v in rep['asset_counts'].items() if v),
                     play.get('bot_completed'), rep['closeness']['score']),
                 'Report: %s' % (root / name / 'CREATE-REPORT.md')]
        if rep['could_not_make']:
            lines.append('Could not make: %d items, listed in the report' % len(rep['could_not_make']))
        if rep.get('not_applied'):
            lines.append('Not applied: %d parts of the prompt (story, mechanics, names), listed in the report'
                         % len(rep['not_applied']))
        lines.extend(rep.get('how_to_play', {}).get('lines', []))
        return '\n'.join(lines)
    except CreateError as e:
        return 'Hermes64 create: ' + e.line()
    except Exception as e:     # newgame's own Fault lines (premise, doctor, root) stay one line
        return 'Hermes64 create: ' + newgame.failure(e)['error']['message']


# ------------------------------------------------------------------------------------- introspection (no project)
BRIEF_TEMPLATE = {
    'format': 'hermes64-brief/1', 'prompt': '<the user prompt>', 'filled_by': 'model',
    'setting': {'genre': '<one genre>', 'genre_hints': ['<0-6 hints or genres>'], 'place': '<short place>',
                'era': '<short era>', 'scale': 'small outdoor hub + 2 interiors'},
    'mood': {'time': '<time>', 'weather': '<weather>', 'season': '<season>', 'tone': '<tone>'},
    'palette_mood': {'dominant': '<hue>', 'support': ['<hue>'], 'accent': '<hue>', 'value_key': 'mid', 'saturation': 'moderate'},
    'build_types': ['<library words: tower, saloon, train car ...>'],
    'props': [{'want': '<prop>', 'count': 1, 'importance': 'key', 'source': 'model'}],
    'characters': [{'want': '<player>', 'role': 'player', 'count': 1}, {'want': '<enemy>', 'role': 'enemy', 'count': 1}],
    'sources': {'user_assets': [], 'allow_generate': True}, 'ip_terms': [], 'unrecognised': [], 'assumptions': []}


def vocab_lines(bundle=None):
    """The closed words a brief may use, the packs (with room patterns or not) and the gameplay routes."""
    from . import brief as B
    ctx = Ctx({'projects_root': '/', 'bundle_root': str(bundle or ROOT)}, 'vocab')
    L = ['genres: ' + ', '.join(B.GENRES), 'genre_hints (or a genre): ' + ', '.join(B.HINTS),
         'time: ' + ', '.join(B.TIMES), 'weather: ' + ', '.join(B.WEATHERS), 'season: ' + ', '.join(B.SEASONS),
         'tone: ' + ', '.join(B.TONES), 'hues: ' + ', '.join(B.HUES), 'value_key: ' + ', '.join(B.VALUE_KEYS),
         'saturation: ' + ', '.join(B.SATURATIONS), 'character roles: ' + ', '.join(B.ROLES),
         'prop importance: key, dressing; prop source: prompt, default, model, user', '', 'packs (room patterns = the create flow can build rooms):']
    for pid in shipped_packs(ctx):
        L.append('  %-24s %s; words: %s' % (pid, 'room patterns' if family_for(pid) else 'no room pattern (hand-author rooms)',
                                            ', '.join(sorted(_pack_words(pid, ctx))[:30])))
    table = load_modules()
    L += ['', 'gameplay routes (genre_hints -> module):']
    for r in table['routes']:
        m = table['modules'][r['module']]
        miss = module_missing(m.get('requires', []))
        L.append('  %s -> %s (%s)' % ('/'.join(r['hints']), r['module'], 'buildable' if not miss else 'not buildable: ' + miss))
    L += ['', 'brief template (fill every field; names in build_types/props are library words, see `find`):',
          json.dumps(BRIEF_TEMPLATE, sort_keys=True)]
    from . import create_story as CS
    caps = CS.load_caps()
    L += ['', 'story block (put it in the same brief file as "story"; every part is optional; names and texts are free '
          'words, copied into the game as written):']
    L += ['  %-9s %s' % (k, v) for k, v in caps['fields'].items()]
    L += ['', 'story template:', json.dumps(STORY_TEMPLATE), '', 'mechanics (story.mechanics words -> what is made):']
    for row in caps['mechanics']:
        L.append('  %-8s %s: %s' % (row['status'], '/'.join(row['words'][:4]), row.get('what') or ('closest: ' + row.get('closest', ''))))
    return L


STORY_TEMPLATE = {
    'title': '<game title>', 'player': {'name': '<player name>'},
    'cast': [{'name': '<name>', 'role': 'npc', 'place': '<a place name>', 'says': '<one line>'},
             {'name': '<name>', 'role': 'boss'}],
    'places': [{'name': '<outdoor place>', 'kind': 'outdoor', 'about': '<one line shown on entering>'},
               {'name': '<indoor place>', 'kind': 'indoor'}],
    'item': {'name': '<the thing collected inside>'},
    'beats': [{'text': '<what happens, as the player reads it>', 'label': '<short action>', 'place': '<a place name>'},
              {'text': '<a line>', 'who': '<cast name>', 'when': '<time word, optional>'}],
    'quests': [{'title': '<journal line>', 'done_when': 'beat 1'}],
    'door_lock': 'beat 1', 'choice': {'ask': '<question>', 'options': ['<a>', '<b>'], 'right': '<a>', 'who': '<cast name>'},
    'waves': [2, 3], 'course': {'seconds': 90, 'checkpoints': ['<a>', '<b>', '<c>']},
    'win': '<ending text>', 'lose': '<text after a wrong choice>', 'mechanics': ['<each gameplay word of the prompt>']}


def find_lines(text, bundle=None, limit=5):
    """'What does the library have for X': top library pieces per phrase and the shipped packs that bind them."""
    from . import taxonomy
    ctx = Ctx({'projects_root': '/', 'bundle_root': str(bundle or ROOT)}, 'find')
    packs = {pid: bindings_keys(ctx, pid)[0] for pid in shipped_packs(ctx)}
    out = []
    for phrase in [p.strip() for p in text.split(',') if p.strip()]:
        row = taxonomy.gap_row(phrase)
        hits = taxonomy.find(phrase, limit=limit)
        out.append('%s: %s%s' % (phrase, row['status'], (' (%s)' % one_line(row.get('why', ''))[:120]) if row.get('why') else ''))
        for gid, score, why in hits:
            bound = sorted(p for p, keys in packs.items() if gid in keys)
            out.append('  %.2f %-22s %s; packs: %s' % (score, gid, '; '.join(why)[:80], ', '.join(bound[:4]) or 'none (library only)'))
        if row['status'] == 'missing' or not hits:
            out.append('  next: author a recipe for it (skill hermes64-generators) and name it in create/candidates.json')
    return out


def plan_lines(brief_path, bundle=None, style=None):
    """Preflight for an agent brief, before any project exists: brief check, gaps, pack candidates, gameplay routes."""
    from . import brief as B, taxonomy as T
    try:
        brief, story = load_brief_file(brief_path)
    except CreateError as e:
        return ['brief: %s' % e.line(), 'next: fix that field and run plan again']
    ctx = Ctx({'projects_root': '/', 'bundle_root': str(bundle or ROOT)}, 'plan')
    wanted = T.wanted_from_brief(brief) + list(brief.get('unrecognised', []))
    rep = T.gap_report(wanted, brief=brief)
    L = ['brief: ok (%s)' % B.summary(brief), '', 'needs:']
    for r in rep['rows']:
        nxt = {'exists': 'library piece', 'partial': 'stand-in unless you author a recipe', 'missing': 'author a recipe or drop it'}
        L.append('  %-22s %-8s %s%s' % (r['want'][:22], r['status'], ', '.join(r.get('matches', [])[:2]),
                                        ' -> ' + nxt.get(r['status'], '') if r['status'] != 'exists' else ''))
    packs = shipped_packs(ctx)
    scores = pack_scores(ctx, brief, rep, packs)
    explicit = palette_named(brief)
    if explicit:         # as stage_style: a named palette beats hand-made time variants
        for r in scores:
            r['score'] = round(r['score'] - r['parts']['time'], 2)
            r['parts']['time'] = 0
        scores.sort(key=lambda r: (-r['score'], r['pack']))
    L += ['', 'pack:']
    base = None
    try:
        base, reason, notes = choose_pack(scores, caller=style)
        L.append('  %s: %s' % (base, reason))
        L += ['  note: ' + n for n in notes]
    except CreateError as e:
        L.append('  ' + e.line())
    if base:
        L += ['', 'palette:'] + palette_plan_lines(ctx, brief, base, explicit)
    brief_r, hint_rows = story_hints(brief, story)
    hints = sorted(set(brief_r['setting'].get('genre_hints', [])))
    routed, unrouted = route_modules(hints)
    scale = brief_room_scale(brief)
    if base and family_for(base):      # FINALINT2: the room scale the run will use, with the patterns' plot sizes
        from .create_story import row_line
        fam = load_patterns()['families'][family_for(base)]
        keys, _ = bindings_keys(ctx, base)
        bw = set(brief_words(brief))
        try:
            line, rows = scale_report(scale[0], scale[1], entry_pattern(fam, family_for(base), bw, keys, scale[0], brief)[0],  # VARIETY V6
                                      choose_pattern(fam['indoor'], bw, keys, scale[0]))
            if story is None and not routed and scale[0] == brief_room_scale({})[0] and place_api() is not None:
                line += ' (or a placemaker archetype that matches the brief)'
            L += ['', 'rooms:', '  ' + line[len('rooms: '):]] + ['  not as asked: ' + row_line(r) for r in rows]
        except CreateError as e:
            L += ['', 'rooms:', '  ' + e.line()]
    L += ['', 'gameplay:']
    table = load_modules()
    will = []
    for w, mid in routed:
        miss = module_missing(table['modules'][mid].get('requires', []))
        if not miss:
            will.append(mid)
        L.append('  %s -> %s: %s' % (w, mid, 'will be added' if not miss else 'not made (%s)' % (table['modules'][mid].get('missing_reason') or miss)))
    if not routed:
        L.append('  collect-and-return only (no routed genre_hints)')
    return L + story_plan_lines(ctx, brief, story, base, will, hint_rows, scale[0])


def palette_plan_lines(ctx, brief, base, explicit):
    """The plan's palette part: the mood the run derives from the brief, or why the pack keeps its own colours."""
    if not explicit:
        return ['  no palette named: %s keeps its colours (or its hand-made time variant)' % base]
    M = bundle_import(ctx, 'tools.mood_pack').M
    clean, notes = sanitize_palette(brief, M)
    try:
        spec = M.mood_from_brief(clean['palette_mood'], clean.get('mood'))
        L = ['  %s, support %s, accent %s, %s light: a mood derived from %s in the run' % (
            spec['dominant'], spec['support'], spec['accent'], spec['time'], base)]
    except M.MoodError as e:
        L = ['  not applied: %s; %s keeps its own colours' % (e, base)]
    return L + ['  note: ' + n for n in notes]


def story_plan_lines(ctx, brief, story, base, will, hint_rows, scale=None):
    """The plan's story part: what will be made, what is not made as asked (closest + fix), unused prompt names."""
    from . import create_story as CS
    names = CS.prompt_names(brief.get('prompt', ''), brief, story)
    L = ['', 'story:']
    if story is None:
        L.append('  no story block: people, places, beats and quests of the prompt are not carried (add `story` to the brief)')
    elif base is None or family_for(base) is None:
        L.append('  story layout waits for a pack with room patterns (see pack above)')
    else:
        fam = load_patterns()['families'][family_for(base)]
        keys, _ = bindings_keys(ctx, base)
        bw = set(brief_words(brief))
        try:
            lay = CS.layout(story, {'entry': entry_pattern(fam, family_for(base), bw, keys, scale, brief)[0],  # VARIETY V6
                                    'inside': choose_pattern(fam['indoor'], bw, keys, scale)}, Slots, SEED)
        except CS.StoryError as e:
            return L + ['  story: %s: %s Next: %s' % (e.code, e.message, e.next_step)]
        made, notes = CS.plan_lines(story, lay, routes=will)
        L += ['  will make: ' + m for m in made]
        L += ['  not as asked: ' + n for n in notes + ['%s: %s' % (r['asked'], r['reason']) for r in hint_rows]]
    if names:
        L.append('  named in the prompt, used nowhere: %s (add them, or tell the human why not)' % ', '.join(names))
    L.append('')
    L.append('next: tell the human in one message what will be made and what is not made as asked (with the closest '
             'thing), then run. Do not wait for an answer unless something is truly ambiguous.')
    return L


SETTING_KEYS = ('projects_root', 'python_path', 'godot_path', 'blender_path', 'builder')


def host_plugin_settings(home=None, plugin='hermes64'):
    """The plugin's settings from the Hermes home config (`plugins.entries.<plugin>.settings`), read without YAML
    libraries (plain `key: value` lines only). {} when there is no home or no such block."""
    home = home or os.environ.get('HERMES_HOME') or str(Path.home() / '.hermes')
    path = Path(home) / 'config.yaml'
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    if text.lstrip().startswith('{'):     # JSON is valid YAML and Hermes reads it (FINALINT2: the verify kit writes it)
        try:
            node = json.loads(text)
        except ValueError:
            node = None
        for key in ('plugins', 'entries', plugin, 'settings'):
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            return {k: v for k, v in node.items() if k in SETTING_KEYS and isinstance(v, str)}
    lines = text.splitlines()
    want = ['plugins', 'entries', plugin, 'settings']
    stack, out = [], {}
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        key, _sep, val = raw.strip().partition(':')
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path_keys = [k for _i, k in stack]
        if path_keys == want and key in SETTING_KEYS:
            v = val.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            out[key] = v
        if not val.strip():
            stack.append((indent, key.strip()))
    return out


def python_has_numpy(python):
    """Builds run the configured Python isolated (-I): numpy must import that way (user site-packages do not count)."""
    import subprocess
    try:
        return subprocess.run([python, '-I', '-c', 'import numpy'], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def default_games_folder():
    """NATIVE: the folder `/hermes64 new` uses when projects_root is blank (<Hermes home>/plugin-data/hermes64/games,
    plugin_settings.default_games_root), so "make me a game" on a fresh install needs no setting. '' when the Hermes
    home does not exist."""
    home = Path(os.environ.get('HERMES_HOME') or Path.home() / '.hermes')
    return str(home / 'plugin-data' / 'hermes64' / 'games') if home.is_dir() else ''


def settings_from_args(a):
    """Flags first, then HERMES64_* environment variables, then the plugin's own settings in the Hermes home, then the
    default games folder."""
    host = host_plugin_settings()
    s = {'projects_root': str(Path(a.projects_root).resolve()) if a.projects_root else
         os.environ.get('HERMES64_PROJECTS_ROOT', '') or host.get('projects_root', '') or default_games_folder(),
         'bundle_root': str(Path(a.bundle_root).resolve()) if a.bundle_root else str(ROOT),
         'builder': a.builder or host.get('builder') or 'python'}
    for key in ('python_path', 'godot_path', 'blender_path'):
        if os.environ.get('HERMES64_' + key.upper()):
            s[key] = os.environ['HERMES64_' + key.upper()]
        elif host.get(key):
            s[key] = host[key]
    # Without a configured interpreter, builds use the one running the flow.
    s.setdefault('python_path', str(Path(sys.executable).absolute()))
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m adventure_maker.create_flow', description=__doc__.split('\n')[0])
    ap.add_argument('action', choices=['run', 'status', 'report', 'vocab', 'find', 'plan'])
    ap.add_argument('prompt', nargs='?')
    ap.add_argument('--projects-root'); ap.add_argument('--bundle-root'); ap.add_argument('--name')
    ap.add_argument('--builder', default=None, choices=['python', 'blender'])
    ap.add_argument('--brief', dest='brief_file'); ap.add_argument('--style'); ap.add_argument('--mood')
    ap.add_argument('--no-install-mood', action='store_true'); ap.add_argument('--budget-seconds', type=float, default=DEFAULT_BUDGET)
    ap.add_argument('--open-seconds', type=int, default=OPEN_SECONDS)
    ap.add_argument('--no-camera-retry', action='store_true', help='measure the pattern cameras only')
    ap.add_argument('--until', choices=ORDER); ap.add_argument('--redo', action='append', choices=ORDER, default=[])
    ap.add_argument('--debug', action='store_true')
    a = ap.parse_args(argv)
    if a.action in ('vocab', 'find', 'plan'):      # introspection: no project, nothing written
        bundle = Path(a.bundle_root).resolve() if a.bundle_root else ROOT
        try:     # FINALINT2: a plan-time CreateError was a raw traceback
            if a.action == 'vocab':
                print('\n'.join(vocab_lines(bundle)))
            elif a.action == 'find':
                if not a.prompt:
                    print('create: create_find: no words given. Next: create_flow find "lighthouse, ghost, train car"', file=sys.stderr)
                    return 2
                print('\n'.join(find_lines(a.prompt, bundle)))
            else:
                if not a.brief_file:
                    print('create: create_plan: no brief. Next: create_flow plan --brief brief.json', file=sys.stderr)
                    return 2
                print('\n'.join(plan_lines(a.brief_file, bundle, a.style)))
        except CreateError as e:
            print('create: ' + e.line(), file=sys.stderr)
            return 2
        return 0
    settings = settings_from_args(a)
    name = a.name
    if not name and a.prompt:
        from .newgame import slug
        name = slug(a.prompt)
    try:
        if not name:
            raise CreateError('create_name', 'no project name', 'pass --name or a prompt')
        if a.action == 'status':
            ctx = Ctx(settings, name)
            if not (ctx.root / STATE).is_file():
                raise CreateError('create_state', 'no create state for %r in %s' % (name, settings['projects_root']), 'run first')
            print('\n'.join(status_lines(load_state(ctx))))
            return 0
        if a.action == 'report':
            ctx = Ctx(settings, name)
            print(ctx.path('CREATE-REPORT.md').read_text(encoding='utf-8'))
            return 0
        if not python_has_numpy(settings['python_path']):
            raise CreateError('create_python', 'builds run %s in isolated mode (-I) and it cannot import numpy there' % settings['python_path'],
                              'set the plugin setting python_path (or HERMES64_PYTHON_PATH) to a Python whose own site-packages have numpy')
        opts = {k: getattr(a, k) for k in ('brief_file', 'style', 'mood', 'no_install_mood', 'budget_seconds', 'open_seconds',
                                           'until', 'redo', 'debug', 'no_camera_retry')}
        if opts['brief_file']:
            opts['brief_file'] = str(Path(opts['brief_file']).resolve())
        state = run(settings, name, a.prompt, opts)
        print('\n'.join(status_lines(state)))
        print('\n'.join(state['how_to_play']['lines']))
        ctx = Ctx(settings, name)
        if ctx.exists('CREATE-REPORT.json'):
            rep = ctx.read_json('CREATE-REPORT.json')
            print('report: %s  closeness %s/100 (needs, gates, attempts; not looks)' % (ctx.path('CREATE-REPORT.md'),
                                                                                       rep['closeness']['score']))
        return 0
    except CreateError as e:
        print('create: ' + e.line(), file=sys.stderr)
        return 2


def numpy_rerun_argv(argv, environ=None, has_numpy=None, executable=None):
    """The command that reruns this create_flow invocation under the configured python_path, or None.

    plan and run import tools.mood_pack (numpy) in the interpreter that started the flow; builds already use the
    configured python_path (HERMES64_PYTHON_PATH or the plugin setting). When the starting interpreter lacks numpy
    (macOS `python3` is often Apple's /usr/bin/python3) and python_path is a different file whose isolated import of
    numpy works, rerun there instead of failing (FINALINT2: every agent run lost 1-3 calls to this). One hop only."""
    environ = os.environ if environ is None else environ
    if environ.get('HERMES64_CREATE_RERUN'):
        return None
    if has_numpy is None:
        from importlib import util as ilu
        has_numpy = ilu.find_spec('numpy') is not None
    if has_numpy:
        return None
    configured = environ.get('HERMES64_PYTHON_PATH') or host_plugin_settings(environ.get('HERMES_HOME')).get('python_path') or ''
    try:
        if not configured or not Path(configured).is_file() or \
                Path(configured).resolve() == Path(executable or sys.executable).resolve():
            return None
    except OSError:
        return None
    if not python_has_numpy(configured):
        return None
    return [configured, '-B', '-m', 'adventure_maker.create_flow'] + list(argv)


def rerun_env(environ=None):
    env = dict(os.environ if environ is None else environ, HERMES64_CREATE_RERUN='1')
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT)] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    return env


if __name__ == '__main__':
    _rerun = numpy_rerun_argv(sys.argv[1:])
    if _rerun:
        import subprocess
        print('create: this Python has no numpy; using python_path %s' % _rerun[0], file=sys.stderr)
        sys.stderr.flush()
        sys.exit(subprocess.call(_rerun, env=rerun_env()))
    sys.exit(main())
