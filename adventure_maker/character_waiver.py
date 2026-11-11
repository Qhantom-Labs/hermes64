"""Owner waivers through hermes64_character bind (lane WAIVER, docs/WAIVER.md).

    bind glb=... id=... display_name=... source=... waive=true owner_approved=<owner's name> brief="<owner's words>"

The owner (and only the owner) can approve named rig kit failures for one character file. The agent passes the
owner's name exactly as the user gave it, plus the owner's words as the reason. Bind then:
  1. validates the file (every clip it carries, plus idle) without a waiver;
  2. when this cast id is the player of the current combat game, also validates each fight clip the file lacks,
     attached from the rig clip packs exactly as staging attaches it (cast_binding._complete);
  3. refuses when anything fails that the owner may not waive (rigkit/waiver.py WAIVABLE; budget.body only up to
     800 triangles), or when nothing fails;
  4. writes characters/waived/<id>.glb: the file with a hermes64_waiver block that records the owner, the date, the
     reason, the scope (the failing checks and clips) and the failing numbers, plus the mesh/weights hash;
  5. re-validates that file with the waiver granted, and records the waiver in the cast row (block sha256).
Staging grants a file's block only for the cast row that recorded it. Nothing else writes or grants a waiver.
"""
import datetime
import hashlib
import json
from pathlib import Path

class _RigWaiver:
    """rigkit.waiver on first use: it imports numpy, and the read-only listing (all_waivers, called by
    hermes64_doctor) must work on a plugin interpreter without numpy (MERGEPREP; MERGE4 simulated-Windows load)."""
    def __getattr__(self, name):
        from .rigkit import waiver
        return getattr(waiver, name)


W = _RigWaiver()

WAIVED_DIR = 'characters/waived'
COMBAT = ('idle_combat', 'swing', 'hurt', 'death', 'roll', 'block')      # cast_binding.COMBAT (player fight clips)
TAG = 'owner-waiver'


class Refusal(Exception):
    def __init__(self, message, errors=()):
        super().__init__(message)
        self.errors = list(errors)


def today():
    return datetime.date.today().isoformat()


def block_sha(block):
    return hashlib.sha256(json.dumps(block, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_args(args):
    """A plain refusal line for the waiver arguments of a bind, or None."""
    waive, owner = args.get('waive'), args.get('owner_approved')
    if owner is not None and not waive:
        return 'owner_approved goes with waive=true (a waiver the owner approved); without waive it is not used'
    if not waive:
        return None
    if owner is None:
        return ("a waiver needs owner_approved=<the owner's name>, as the owner gave it to you. Only the owner can approve "
                "a waiver; an agent cannot approve one itself")
    if not W.owner_ok(owner):
        return "owner_approved must be the owner's own name as they gave it, not %r" % owner
    if not isinstance(args.get('brief'), str) or len(args['brief'].strip()) < 3:
        return 'a waiver needs brief="<the owner\'s own words>"; they are recorded as the waiver reason'
    return None


def roles(project, cid, rows):
    """-> (game ids of the current game that would use cast id `cid`, whether one of them is the combat player)."""
    if project is None or not project.path('.maker/current.json').is_file():
        return [], False
    from .cast_binding import game_ids, resolve
    cur = project.read_json('.maker/current.json')
    if not cur.get('game') or not project.path(cur['game']).is_file():
        return [], False
    ids = game_ids(project.read_json(cur['game']))
    got, _ = resolve(ids, dict(rows, **{cid: {'id': cid}}))
    gids = sorted(g for g, c in got.items() if c == cid)
    return gids, ids['protagonist'] in gids and any(t for t in ids['archetypes'].values())


def _numbers(rep, clip):
    d = rep['checks']['deformation']['per_clip'][clip]
    s = rep['checks']['silhouette']['per_clip'][clip]
    return {'edge_ratio': list(d['edge_ratio']), 'keys_out': d['keys_out'], 'floor_dev_m': s['floor_dev_m'],
            'floor_keys': s['floor_keys']}


def _failing(rep):
    """-> ({clip: numbers} of clips whose failures are waivable, [errors that are not], set of waivable codes)."""
    never = [e for e in rep['errors'] if e['code'] not in W.WAIVABLE]
    codes = {e['code'] for e in rep['errors'] if e['code'] in W.WAIVABLE}
    out = {}
    per = (rep['checks'].get('deformation') or {}).get('per_clip') or {}
    for clip in per:
        n = _numbers(rep, clip)
        lo, hi = n['edge_ratio']
        if ('mesh.deformation' in codes and (lo < W.EDGE_LIMITS[0] or hi > W.EDGE_LIMITS[1])) or \
                ('mesh.silhouette.floor' in codes and n['floor_keys'] > 0):
            out[clip] = n
    return out, never, codes


def _fight_candidates(raw, rig, have, profile):
    """Per fight clip the file lacks: the first pack clip (cast_binding.packs order) that the rig kit refuses only for
    waivable reasons, when no pack gives a clip that passes as it is. -> {clip: (pack, report)}."""
    from .cast_binding import packs
    from .rigkit import RigError, attach_clips, validate_character
    out = {}
    for clip in [c for c in COMBAT if c not in have]:
        first, clean = None, False
        for pack in packs(rig):
            try:
                cand = attach_clips(raw, pack, clips=[clip], replace=False)
            except (RigError, ValueError):
                continue
            rep = validate_character(cand, rig, clips=[clip], profile=profile, per_clip=True)
            if rep['ok']:
                clean = True
                break
            if first is None and all(e['code'] in W.WAIVABLE for e in rep['errors']):
                first = (pack, rep)
        if first is not None and not clean:
            out[clip] = first
    return out


def grant(raw, rig, clips, profile, owner, reason, player=False, day=None):
    """-> (waived GLB bytes, block, {'waived': [lines], 'fight_clips': {clip: pack}}). Raises Refusal with a plain line."""
    from .cast_binding import plain_reason
    from .rigkit import attach_clips, gltf, validate_character
    base = W.strip(raw)
    rep = validate_character(base, rig, clips=clips, profile=profile, per_clip=True)
    if not (rep['checks'].get('deformation') or {}).get('per_clip') and rep['errors']:
        lines = ['rig %s: %s' % (e['code'], e['message']) for e in rep['errors']]
        raise Refusal(plain_reason(lines, rig)[len('Refused: '):] + '; the validator stopped before the posed checks, '
                      'so nothing can be waived', lines)
    fails, never, codes = _failing(rep)
    if never:
        lines = ['rig %s: %s' % (e['code'], e['message']) for e in never]
        raise Refusal('%s; the owner cannot waive %s (only %s, budget.body up to %d triangles)' % (
            plain_reason(lines, rig)[len('Refused: '):], ', '.join(sorted({e['code'] for e in never})),
            ', '.join(W.WAIVABLE[:2]), W.BUDGET_HARD_CAP), lines)
    tris = (rep['checks'].get('budget') or {}).get('body_tris')
    if 'budget.body' in codes and (not isinstance(tris, int) or tris > W.BUDGET_HARD_CAP):
        raise Refusal('the body has %s triangles, over the hard cap of %d that an owner waiver may allow'
                      % (tris, W.BUDGET_HARD_CAP), [e['message'] for e in rep['errors'] if e['code'] == 'budget.body'])
    fight = {}
    if player:
        have = {a.get('name') for a in gltf.parse(base)[0].get('animations', [])}
        for clip, (pack, r) in sorted(_fight_candidates(base, rig, have, profile).items()):
            f2, _n2, c2 = _failing(r)
            if clip in f2:
                fails[clip] = f2[clip]
                codes |= c2
                fight[clip] = pack
    if not fails and 'budget.body' not in codes:
        raise Refusal('nothing to waive: the rig kit validator passes this file%s; bind it without waive'
                      % (' and the fight clips a player needs' if player else ''))
    doc, binary = gltf.parse(base)
    measured = {'rig': rig, 'edge_limits': list(W.EDGE_LIMITS), 'body_tris': tris, 'clips': fails}
    block = W.make_block(owner, reason, day or today(), codes, list(fails), measured, W.mesh_hash(doc, binary))
    code, why = W.problems(block)
    if code:
        raise Refusal('; '.join(why))
    out = W.write(base, block)
    check = validate_character(out, rig, clips=clips, profile=profile, waiver=True)
    lines = W.waived_lines(check.get('waived', []))
    for clip, pack in sorted(fight.items()):                       # what staging will attach, checked the same way
        r = validate_character(attach_clips(out, pack, clips=[clip], replace=False), rig, clips=[clip], profile=profile, waiver=True)
        if not r['ok']:
            raise Refusal('the %s clip from the %s pack still fails with the waiver (%s)' % (clip, pack, r['errors'][0]['message'][:160]))
        lines += ['%s (fight clip from the %s pack, attached when staged as the player)' % (s, pack) for s in W.waived_lines(r.get('waived', []))]
    if not check['ok']:
        raise Refusal('the waived file still fails: ' + check['errors'][0]['message'][:200],
                      ['rig %s: %s' % (e['code'], e['message']) for e in check['errors']])
    return out, block, {'waived': lines, 'fight_clips': fight}


def record(block, source_glb, source_sha256, lines):
    """The cast row's record of a waiver bind wrote."""
    return {'approved_by': block['approved_by'], 'owner': block['owner'], 'approved_on': block['approved_on'],
            'reason': block['reason'], 'scope': block['scope'], 'file_hash': block['file_hash'],
            'block_sha256': block_sha(block), 'source_glb': source_glb, 'source_sha256': source_sha256, 'waived': lines[:24]}


def granted(row, raw):
    """True when a cast row recorded a waiver and the file carries exactly that block (staging, re-bind)."""
    rec = (row or {}).get('waiver')
    block = W.block_of(raw)
    return bool(rec) and block is not None and block_sha(block) == rec.get('block_sha256')


def line(cid, rec):
    sc = rec.get('scope') or {}
    clips = sc.get('clips')
    return '%s: owner waiver (%s, %s): %s in %s' % (cid, rec.get('owner'), rec.get('approved_on'), ', '.join(sc.get('checks') or []),
                                                    'all clips' if clips == 'all' else ', '.join(clips or []))


def waived_rows(cast_doc):
    """[(cast id, waiver record)] of a characters/cast.json document."""
    return [(r['id'], r['waiver']) for r in (cast_doc or {}).get('cast', []) if isinstance(r, dict) and r.get('waiver')]


def project_waivers(project_dir):
    """Every waived character of one project folder (read-only) -> [{project, id, owner, approved_on, checks, clips, glb}]."""
    p = Path(project_dir) / 'characters' / 'cast.json'
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    out = []
    for r in doc.get('cast', []) if isinstance(doc, dict) else []:
        rec = r.get('waiver') if isinstance(r, dict) else None
        if rec:
            out.append({'project': Path(project_dir).name, 'id': r.get('id'), 'glb': r.get('glb'), 'owner': rec.get('owner'),
                        'approved_on': rec.get('approved_on'), 'checks': (rec.get('scope') or {}).get('checks'),
                        'clips': (rec.get('scope') or {}).get('clips'), 'reason': rec.get('reason')})
    return out


def all_waivers(projects_root, only=None):
    """Waived characters under a projects root (every project, or only the named one)."""
    if not projects_root or not Path(projects_root).is_dir():
        return []
    dirs = [Path(projects_root) / only] if only else sorted(p for p in Path(projects_root).iterdir() if p.is_dir())
    out = []
    for d in dirs:
        out += project_waivers(d)
    return out
