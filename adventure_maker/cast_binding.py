"""Project cast -> generated game (lane CHARBIND): characters bound with `hermes64_character bind` appear in the game.

Data (presentation only; no story or gameplay identifier changes, so proofs, saves and replays are untouched):
  characters/cast.json              rows written by hermes64_character bind (rig-kit-validated GLBs in the project)
  metadata.presentation.cast        {game id: cast id}, written by /hermes64 new from premise `binding` fields that
                                    name a project cast id (or added with hermes64_compile patch_json)
A game id is a story character id, a combat archetype id (stock or premise robot/boss) or a scene actor id. It uses
the cast row the mapping names, else the cast row with its own id. With no project cast and no mapping the staged
runtime is byte-identical to before.

Staged by prepare_runtime (after characters.integration.stage_runtime):
  runtime/bindings.json characters  rows with `for_ids`; the actor resolver matches them by id before selector rows
  runtime/combat.json enemies       a body for every bound combat archetype (the stock robot art stays otherwise)
  runtime/cast-binding.json         what was bound to what, derived files, plain warnings

Clip contract per role:
  player (combat game)  idle_combat swing hurt death roll block, from the file, else from a clip pack the rig kit
                        accepts on this body, swing else from its own interact; one still missing is the runtime's
                        labelled POSE TEST hold (animation_state.gd) and the HUD shows POSE TEST
  room actor / captive  its authored clip (presentation rooms.<room>.characters.<id>.clip), else idle + a warning
  scene actor           every clip its cards ask for, else idle + a warning
  boss / enemy body     telegraph attack recover: the body's own clips, else derived from its swing keys (telegraph
                        = swing keys 0-3 then key 4 held, attack = swing with hit window keys 5-7, recover = swing
                        keys 7-15 spread over 16 keys); hurt death idle_combat from the body or the rig pack; approach
                        = walk, else run, else idle. A body that cannot show telegraph/attack/recover keeps the stock
                        robot art; a missing hurt/death/idle_combat shows the runtime's held POSE TEST pose.
Derived files: .maker/cache/cast/<key>.glb, deterministic, re-validated by the rig kit, cached by key.
"""
import copy
import hashlib
import json
from pathlib import Path

from .safety import fail

CAST = 'characters/cast.json'
CACHE = '.maker/cache/cast'
VERSION = 'charbind-2'
COMBAT = ('idle_combat', 'swing', 'hurt', 'death', 'roll', 'block')
ENEMY_NEEDS = ('idle_combat', 'hurt', 'death')
FIGHT = ('telegraph', 'attack', 'recover')
SWING_KEYS = {'telegraph': [0, 1, 2, 3] + [4] * 12, 'attack': list(range(16)),
              'recover': [7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15]}
HIT = [5, 7]
PHASES = {'telegraph': {'hold_frames': [4, 15], 'loop': False, 'phases': {'wind': [1, 3], 'hold': [4, 15]},
                        'telegraph_peak_frame': 4},
          'attack': {'hit_window': {'frames': HIT, 'start_s': round(HIT[0] / 15., 6), 'end_s': round((HIT[1] + 1) / 15., 6)},
                     'loop': False, 'phases': {'active': HIT, 'launch': [1, 4], 'settle': [8, 15]}},
          'recover': {'loop': False, 'phases': {'settle': [1, 15]}}}
TEMPLATES = ('boss_phases_v1', 'walker_patrol_v1', 'brute_slam_v1', 'hover_drone_v1', 'melee_approach_v1', 'melee_dash_v1')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _dump(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.cast-tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(path)


def game_ids(game):
    """{'characters': {id: spec row}, 'protagonist', 'archetypes': {id: template}, 'scene_actors': {id: set(clips)},
    'clips': {id: set(authored clips)}} of a compiled game."""
    meta = game.get('metadata') or {}
    pres = meta.get('presentation') if isinstance(meta.get('presentation'), dict) else {}
    chars = {c['id']: c for c in game.get('characters', []) if isinstance(c, dict) and 'id' in c}
    hero = str(meta.get('protagonist', ''))
    arch = {}
    for module in (game.get('gameplay') or {}).get('modules', []):
        for row in (module.get('entities') or {}).get('archetypes', []) or []:
            if isinstance(row, dict) and 'id' in row:
                arch[str(row['id'])] = str((row.get('fsm') or {}).get('template', ''))
    clips, actors = {}, {}
    for room in (pres.get('rooms') or {}).values():
        for cid, row in ((room or {}).get('characters') or {}).items():
            if isinstance(row, dict) and row.get('clip'):
                clips.setdefault(cid, set()).add(str(row['clip']))
    for scene in pres.get('scenes') or []:
        for card in (scene or {}).get('cards', []) if isinstance(scene, dict) else []:
            for a in (card or {}).get('actors', []) if isinstance(card, dict) else []:
                if not isinstance(a, dict):
                    continue
                cid = str(a.get('character', ''))
                cid = hero if cid == 'protagonist' else cid
                want = {str(a.get('clip', 'idle'))} | ({str(a['moving_clip'])} if a.get('moving_clip') else set())
                clips.setdefault(cid, set()).update(want)
                if cid and cid not in chars:
                    actors.setdefault(cid, set()).update(want)
    return {'characters': chars, 'protagonist': hero, 'archetypes': arch, 'scene_actors': actors, 'clips': clips,
            'mapping': pres.get('cast') if isinstance(pres.get('cast'), dict) else {}}


def resolve(ids, rows):
    """-> ({game id: cast id}, warnings). The mapping wins; otherwise a cast row with the game id's own name."""
    out, warnings = {}, []
    every = list(ids['characters']) + list(ids['archetypes']) + list(ids['scene_actors'])
    for gid in sorted(dict.fromkeys(every)):
        cid = ids['mapping'].get(gid)
        if cid is not None:
            if cid in rows:
                out[gid] = cid
            else:
                warnings.append('%s names cast id %s, which is not bound: run hermes64_character bind (id=... or glb=...) '
                                'for it; the bundled or stock body stays until then' % (gid, cid))
        elif gid in rows:
            out[gid] = gid
    for gid, cid in sorted(ids['mapping'].items()):
        if gid not in every:
            warnings.append('presentation.cast names %s, which is not a character, combat archetype or scene actor of '
                            'this game' % gid)
    return out, warnings


def uses(game, rows):
    """{cast id: [game ids]} for hermes64_character bind's report."""
    got, _ = resolve(game_ids(game), rows)
    out = {}
    for gid, cid in sorted(got.items()):
        out.setdefault(cid, []).append(gid)
    return out


# ------------------------------------------------------------------ derived bodies
class BodyError(Exception):
    pass


def _clips_of(raw):
    from .rigkit import gltf
    doc, _ = gltf.parse(raw)
    return [a.get('name') for a in doc.get('animations', [])]


def packs(rig):
    """Clip packs a body on `rig` may borrow from: its own rig first, then rigs with the same bones and parents."""
    from .rigkit import list_rigs, load_rig
    base = load_rig(rig)
    same = [r for r in list_rigs() if r != rig and load_rig(r).bones == base.bones and load_rig(r).parents == base.parents]
    return [rig] + sorted(same)


def _wv(waiver):
    """validate_character keyword for an owner waiver the cast row granted (lane WAIVER); nothing otherwise."""
    return {'waiver': True} if waiver else {}


def _complete(raw, rig, needed, waiver=False):
    """Missing clips of `needed` from the clip pack of the file's rig, else of a rig with the same bones (packs()),
    whichever the rig kit accepts on this body first, each clip checked alone (rigkit.attach_clips, existing clips
    kept). -> (bytes, {clip: pack rig}, {clip: why no pack fits})."""
    from .rigkit import attach_clips, RigError, validate_character
    have = set(_clips_of(raw))
    sources, refused = {}, {}
    for clip in [c for c in needed if c not in have]:
        why = None
        for pack in packs(rig):
            try:
                cand = attach_clips(raw, pack, clips=[clip], replace=False)
            except (RigError, ValueError) as exc:
                why = why or 'not in the %s pack (%s)' % (pack, str(exc)[:100])
                continue
            rep = validate_character(cand, rig, clips=[clip], **_wv(waiver))
            if rep['ok']:
                raw, sources[clip], why = cand, pack, None
                break
            why = why or '%s pack: %s: %s' % (pack, rep['errors'][0]['code'], rep['errors'][0]['message'][:140])
        if why:
            refused[clip] = why
    return raw, sources, refused


def _copy_clips(raw, base, plan):
    """New animations made of `base`'s keys: plan {name: [16 key indices]}; rotations and root translation copied,
    STEP keys, extras hermes64_derived {from, keys}. Existing names are left alone. -> (bytes, [made names])."""
    import numpy as np
    from .rigkit import gltf, gltfedit
    doc, binary = gltf.parse(raw)
    anims = {a.get('name'): a for a in doc.get('animations', [])}
    todo = [n for n in plan if n not in anims]
    if not todo:
        return raw, []
    src = anims[base]
    work = copy.deepcopy(doc)
    b = gltfedit.Builder(work, binary)
    for name in todo:
        keys = plan[name]
        channels, samplers = [], []
        for ch in src['channels']:
            s = src['samplers'][ch['sampler']]
            vals = gltf.read_accessor(doc, binary, s['output']).astype(np.float32)
            if len(vals) != 16:
                raise BodyError('its %s clip has %d keys, the rig contract has 16' % (base, len(vals)))
            typ = 'VEC4' if ch['target']['path'] == 'rotation' else 'VEC3'
            samplers.append({'input': s['input'], 'interpolation': 'STEP', 'output': b.accessor(vals[keys], 5126, typ)})
            channels.append({'sampler': len(samplers) - 1, 'target': dict(ch['target'])})
        work['animations'].append({'name': name, 'channels': channels, 'samplers': samplers,
                                   'extras': {'hermes64_derived': {'from': base, 'keys': list(keys)}}})
    work['animations'] = sorted(work['animations'], key=lambda a: a.get('name', ''))
    return b.finish(), todo


def _derive_fight(raw, base='swing'):
    """telegraph / attack / recover made of the body's swing keys, or of its own interact (reach) keys."""
    have = _clips_of(raw)
    if all(c in have for c in FIGHT):
        return raw, []
    if base not in have:
        raise BodyError('it has no telegraph/attack/recover clips and no %s clip to make them from' % base)
    return _copy_clips(raw, base, {n: SWING_KEYS[n] for n in FIGHT})


def _fit(raw, rig, candidates, waiver=False):
    """Each candidate clip checked on this body alone by the rig kit; refused ones leave the file (the actor shows idle
    for a clip it lacks). -> (bytes, {clip: first rig kit error})."""
    from .rigkit import validate_character
    from .rigkit.conform import keep_clips
    bad = {}
    for c in candidates:
        rep = validate_character(raw, rig, clips=[c], **_wv(waiver))
        if not rep['ok']:
            bad[c] = '%s: %s' % (rep['errors'][0]['code'], rep['errors'][0]['message'][:160])
    if bad:
        raw = keep_clips(raw, [c for c in _clips_of(raw) if c not in bad])
    return raw, bad


def _pack_tag(rig):
    from .rigkit.clips import load_pack
    try:
        return load_pack(rig)[2]['files']['clips.glb']['sha256']
    except Exception:          # noqa: BLE001 - a rig without a pack derives nothing from it
        return 'none'


def derived(project, raw, rig, kind, waiver=False):
    """(bytes, rel path, info) of the role variant of a bound GLB; cached and validated. kind: player | enemy.
    waiver: the cast row granted the file's owner waiver (lane WAIVER); every rig kit check here then grants it.
    Raises BodyError with a plain reason when the role cannot be met."""
    from .rigkit import validate_character
    key_doc = {'v': VERSION, 'src': sha(raw), 'rig': rig, 'kind': kind, 'packs': [[p, _pack_tag(p)] for p in packs(rig)]}
    if waiver:
        key_doc['waiver'] = True
    key = sha(json.dumps(key_doc, sort_keys=True).encode())[:32]
    rel, side = '%s/%s.glb' % (CACHE, key), '%s/%s.json' % (CACHE, key)
    if project.path(rel).is_file() and project.path(side).is_file():
        info = project.read_json(side)
        out = project.path(rel).read_bytes()
        if info.get('sha256') == sha(out):
            if not info.get('ok'):
                raise BodyError(info.get('reason', 'rig kit refused the derived body'))
            return out, rel, info
    sources, made, dropped, own = {}, [], {}, {}
    try:
        if kind == 'player':
            out, sources, dropped = _complete(raw, rig, COMBAT, waiver)
            if 'swing' in dropped and 'interact' in _clips_of(out):     # the body's own reach as its swing
                cand, _m = _copy_clips(out, 'interact', {'swing': list(range(16))})
                cand, bad = _fit(cand, rig, ['swing'], waiver)
                if not bad:
                    out, own['swing'] = cand, 'interact'
                    dropped.pop('swing')
        else:
            have = set(_clips_of(raw))
            need = list(ENEMY_NEEDS) + ([] if all(c in have for c in FIGHT) else ['swing'])
            out, sources, dropped = _complete(raw, rig, need, waiver)
            base = 'swing'
            if 'swing' in dropped:
                if 'interact' not in _clips_of(out):
                    raise BodyError('no swing fits this body (%s) and it has no interact clip to make '
                                    'telegraph/attack/recover from' % dropped['swing'])
                base = 'interact'
                dropped.pop('swing')              # an enemy shows telegraph/attack/recover, never swing itself
            out, made = _derive_fight(out, base)
            own.update({n: base for n in made})
            out, bad = _fit(out, rig, made, waiver)
            dropped.update(bad)
            lost = [c for c in FIGHT if c in dropped]
            if lost:
                raise BodyError('%s cannot be shown on this body (%s)' % (', '.join(lost), dropped[lost[0]]))
        names = sorted(_clips_of(out))
        rep = validate_character(out, rig, clips=names, **_wv(waiver))
        info = {'ok': bool(rep['ok']), 'kind': kind, 'source_sha256': sha(raw), 'sha256': sha(out), 'rig': rig,
                'clips': names, 'from_rig_pack': sources, 'made_from': own,
                'refused_clips': dropped, 'errors': ['%s: %s' % (e['code'], e['message']) for e in rep['errors']][:6]}
        if rep.get('waived'):
            info['waived'] = [w['message'] for w in rep['waived']]
        if not rep['ok']:
            info['reason'] = 'the rig kit refuses the %s body (%s)' % (kind, info['errors'][0] if info['errors'] else 'not ok')
    except BodyError as exc:
        out = raw
        info = {'ok': False, 'kind': kind, 'source_sha256': sha(raw), 'sha256': sha(out), 'rig': rig, 'reason': str(exc)}
    project.write_bytes(rel, out)
    project.write_json(side, info)
    if not info['ok']:
        raise BodyError(info['reason'])
    return out, rel, info


# ------------------------------------------------------------------ staging
def stage(runtime, project, root=None):
    """Stage the project cast into a prepared runtime folder; -> report dict, or None when nothing is bound."""
    runtime = Path(runtime)
    game = json.loads((runtime / 'game.json').read_text(encoding='utf-8'))
    ids = game_ids(game)
    cast = project.read_json(CAST) if project.path(CAST).is_file() else {}
    rows = {r['id']: r for r in cast.get('cast', []) if isinstance(r, dict) and 'id' in r}
    if not rows and not ids['mapping']:
        return None
    got, warnings = resolve(ids, rows)
    from .rigkit import load_rig
    files = {}

    def source(cid):
        if cid not in files:
            row = rows[cid]
            path = project.path(row['glb'])
            if not path.is_file():
                fail('missing', 'Bound character %s: %s is gone; bind it again with hermes64_character' % (cid, row['glb']))
            raw = path.read_bytes()
            if sha(raw) != row['sha256']:
                fail('asset_integrity', 'Bound character %s: %s changed since it was bound; bind it again' % (cid, row['glb']))
            files[cid] = raw
        return files[cid]

    combat_game = any(t for t in ids['archetypes'].values())
    report = {'schema': 'hermes64-cast-binding/1', 'bound': {}, 'derived': {}, 'warnings': warnings}
    char_rows = {}
    from .character_waiver import granted, line

    def waiver_of(cid):
        """WAIVER: the cast row recorded an owner waiver and the file carries exactly that block (else not granted)."""
        ok = granted(rows[cid], source(cid))
        if ok:
            report.setdefault('waived', {})[cid] = line(cid, rows[cid]['waiver'])
        elif rows[cid].get('waiver'):
            warnings.append('%s: the cast row records an owner waiver, but %s does not carry that waiver block; it is not '
                            'granted (bind it again with waive=true)' % (cid, rows[cid]['glb']))
        return ok
    for gid in sorted(set(ids['characters']) | set(ids['scene_actors'])):
        cid = got.get(gid)
        if cid is None:
            continue
        row = rows[cid]
        raw = source(cid)
        rig = row['rig']['id']
        kind, rel, path = 'actor', row['glb'], project.path(row['glb'])
        clips = list(row.get('clips') or _clips_of(raw))
        waiver = waiver_of(cid)
        if gid == ids['protagonist'] and combat_game:
            try:
                out, rel, info = derived(project, raw, rig, 'player', waiver)
                path, clips, kind = project.path(rel), info['clips'], 'player'
                report['derived'][rel] = {k: info.get(k) for k in ('kind', 'source_sha256', 'from_rig_pack', 'refused_clips')}
                for clip, why in sorted((info.get('refused_clips') or {}).items()):
                    warnings.append('%s (player): no clip pack (%s) gives a %s the rig kit accepts on this body (%s); '
                                    'in fights that pose is the labelled POSE TEST hold and the HUD shows POSE TEST'
                                    % (gid, ', '.join(packs(rig)), clip, why))
            except BodyError as exc:
                warnings.append('%s (player): %s; in fights its combat poses are the labelled POSE TEST holds' % (gid, exc))
        for clip in sorted(ids['clips'].get(gid, ())):
            if clip not in clips:
                warnings.append('%s: %s has no %s clip; idle is shown' % (gid, row['glb'], clip))
        spec = ids['characters'].get(gid, {})
        key = (cid, rel)
        if key not in char_rows:
            raw_out = path.read_bytes()
            char_rows[key] = {
                'character_id': cid, 'cast_id': cid, 'for_ids': [], 'path': str(path), 'sha256': sha(raw_out),
                'body_id': spec.get('body_id', ''), 'base_rig_id': spec.get('base_rig_id', ''),
                'params': copy.deepcopy(spec.get('params', {})), 'animations': sorted(clips),
                'bone_names': list(load_rig(rig).bones), 'placeholder': False, 'source_rig': rig, 'ground_offset': 0.0,
                'visibility': row.get('visibility', 'internal'), 'role': kind}
        char_rows[key]['for_ids'].append(gid)
        report['bound'].setdefault(gid, []).append({
            'cast': cid, 'as': 'player' if kind == 'player' else ('scene actor' if gid not in ids['characters'] else 'character'),
            'glb': rel})
    enemies = {}
    for gid, template in sorted(ids['archetypes'].items()):
        cid = got.get(gid)
        if cid is None:
            continue
        if template not in TEMPLATES:
            warnings.append('%s: template %s has no character-body contract; the stock art stays' % (gid, template))
            continue
        row = rows[cid]
        raw = source(cid)
        rig = row['rig']['id']
        try:
            out, rel, info = derived(project, raw, rig, 'enemy', waiver_of(cid))
        except BodyError as exc:
            warnings.append('%s (%s): body %s cannot fight: %s; the stock robot art stays' % (gid, template, cid, exc))
            continue
        report['derived'][rel] = {k: info.get(k) for k in ('kind', 'source_sha256', 'from_rig_pack', 'made_from',
                                                            'refused_clips')}
        for clip, why in sorted((info.get('refused_clips') or {}).items()):
            warnings.append('%s (%s): %s is refused on body %s (%s); that state shows the held POSE TEST pose'
                            % (gid, template, clip, cid, why))
        names = info['clips']
        approach = next(c for c in ('walk', 'run', 'idle') if c in names) if any(c in names for c in ('walk', 'run', 'idle')) else 'idle_combat'
        phases = dict(PHASES)
        phases[approach] = {'loop': True, 'phases': {'loop': [0, 15]}}
        enemies[gid] = {'id': gid, 'template': template, 'rig': rig, 'pack': 'project', 'path': str(project.path(rel)),
                        'sha256': info['sha256'], 'clips': names, 'face_atlas': {}, 'phases': phases,
                        'fsm_state_clip': {'idle': 'idle_combat', 'approach': approach, 'telegraph': 'telegraph',
                                           'attack': 'attack', 'recover': 'recover', 'hurt': 'hurt', 'dead': 'death'},
                        'tris_body': None, 'tris_glb': None, 'cast_id': cid}
        report['bound'].setdefault(gid, []).append({'cast': cid, 'as': 'combat body (%s)' % template, 'glb': rel})
    bpath = runtime / 'bindings.json'
    b = json.loads(bpath.read_text(encoding='utf-8'))
    b['characters'] = [char_rows[k] for k in sorted(char_rows)] + list(b.get('characters', []))
    _dump(bpath, b)
    if enemies:
        cpath = runtime / 'combat.json'
        if not cpath.is_file():
            warnings.append('combat bodies %s not staged: this build has no combat art manifest' % ', '.join(sorted(enemies)))
        else:
            c = json.loads(cpath.read_text(encoding='utf-8'))
            c['enemies'] = dict(c.get('enemies', {}), **enemies)
            c['cast_bodies'] = sorted(enemies)
            _dump(cpath, c)
    for cid, text in sorted((report.get('waived') or {}).items()):
        warnings.append(text + '; the rig kit reports these failures as WAIVED (docs/WAIVER.md)')
    report['warnings'] = list(dict.fromkeys(warnings))
    _dump(runtime / 'cast-binding.json', report)
    return report


# ------------------------------------------------------------------ plain refusal lines (hermes64_character bind)
PLAIN = (
    ('rig.bone_names', 'the skeleton is not {rig} ({msg}); retarget it onto the 16 {rig} bones first'),
    ('rig.skin_count', 'the file needs exactly one skin on the {rig} skeleton ({msg})'),
    ('rig.rest_rotation', 'a joint rest pose is rotated or scaled ({msg}); {rig} rest joints are translation-only'),
    ('rig.proportions', 'body proportions are outside the {rig} ranges ({msg})'),
    ('budget.body', 'the body is over budget ({msg})'),
    ('budget.prop', 'a prop is over budget ({msg})'),
    ('clip.missing', 'a needed clip is missing ({msg})'),
    ('clip.root_motion', 'a clip moves the root sideways ({msg}); clips play in place, and a seated clip must declare its '
                         'seat (rigkit.declare_seat)'),
    ('mesh.silhouette.floor', 'a clip floats or sinks ({msg}); a run flight phase must come with the base_v1 locomotion '
                              'block, a seated clip with its seat declaration'),
    ('mesh.deformation', 'an animation stretches the mesh past 0.45..1.8 of its rest edge lengths ({msg}); fused parts '
                         '(arms joined to the body, legs joined through a skirt) need separated limbs in the source'),
    ('mesh.connectivity.floating', 'loose mesh pieces float off the body at rest ({msg}); every skinned piece must touch the '
                                   'body within 3 mm, rigid accessories go in separate prop meshes'),
    ('mesh.connectivity', 'body parts come apart in a clip ({msg})'),
)


def plain_reason(errors, rig='human16_v1'):
    """One line for a refused bind: the first rig-kit error in plain words."""
    for line in errors:
        code, _, msg = str(line).partition(': ')
        code = code.replace('rig ', '', 1)
        for c, text in PLAIN:
            if code == c:
                return 'Refused: ' + text.format(rig=rig, msg=msg[:140])
    return 'Refused: ' + (str(errors[0])[:240] if errors else 'the rig kit validator reported not ok')
