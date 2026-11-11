"""Owner waiver for one character file (lane WAIVER, docs/WAIVER.md).

A character GLB may carry root extras `hermes64_waiver`: the owner's approval of named rig kit failures for this one
mesh. The validator applies a block only when its caller grants waivers (`validate_character(..., waiver=True)`).
Without that grant the block is reported and ignored, so every other path (hub, CLI, generated characters) is
unchanged. In the plugin, `hermes64_character bind waive=true owner_approved=<name>` is the only writer, and staging
grants a file's waiver only for the cast row that bind recorded.

Block (format hermes64-waiver/1):
  approved_by  'owner'
  owner        the owner's name as the user gave it to the agent (bind owner_approved=<name>)
  approved_on  YYYY-MM-DD, the day bind wrote the block
  reason       the owner's words (bind brief=...)
  scope        {checks: [check codes], clips: [clip names] | 'all'}
  measured     {rig, edge_limits, body_tris, clips: {clip: {edge_ratio: [lo, hi], keys_out, floor_dev_m, floor_keys}}}
               the failing numbers at waiver time
  file_hash    mesh_hash(): sha256 of the skinned mesh, skin weights and skeleton the waiver was granted for

Rules. They are fixed here, and nothing in a block can change them:
  waivable  mesh.deformation, mesh.silhouette.floor, and budget.body for a body of at most BUDGET_HARD_CAP triangles
  never     everything else. That covers non-finite data, the skeleton contract (bones, left/right hierarchy, rest
            pose, proportions), skin weights, clip form, root motion beyond the declared seat/flight rules,
            connectivity, props, the container and the file hash. A block that names any of these is refused whole.
  hash      a different mesh_hash: the block is refused whole (waiver.hash_mismatch) and nothing is waived
  growth    a clip whose numbers exceed the recorded ones by more than TOLERANCE (5 %) is not waived
  scope     a failing check or clip that the block does not list is not waived
A waived failure moves from report['errors'] to report['waived'] with its numbers; it is never dropped.
"""
import copy
import hashlib
import re

import numpy as np

from . import gltf, lbs

WAIVER_KEY = 'hermes64_waiver'
FORMAT = 'hermes64-waiver/1'
WAIVABLE = ('mesh.deformation', 'mesh.silhouette.floor', 'budget.body')
BUDGET_HARD_CAP = 800
TOLERANCE = 0.05
EDGE_LIMITS = (.45, 1.8)          # the validator's (validate.EDGE_LIMITS); repeated here to avoid an import cycle
OWNER_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,47}$")
GENERIC_OWNERS = {'owner', 'the owner', 'user', 'the user', 'me', 'myself', 'self', 'agent', 'assistant', 'ai', 'bot',
                  'hermes', 'claude', 'system', 'admin', 'yes', 'true', 'ok', 'okay', 'approved', 'unknown', 'none', 'n a',
                  'anonymous', 'someone', 'everyone', 'team'}
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
FLOOR_RE = re.compile(r'^(.+)@(\d+) lowest vertex at (-?[0-9.]+) m$')
FLOOR_OWNER_RE = re.compile(r'^WAIVED \((.+?)\): ')
CHECK_OF = {'mesh.deformation': 'deformation', 'mesh.silhouette.floor': 'silhouette', 'budget.body': 'budget'}


def read(doc):
    """The waiver block a parsed GLB document carries, or None."""
    ex = doc.get('extras')
    return ex.get(WAIVER_KEY) if isinstance(ex, dict) and WAIVER_KEY in ex else None


def block_of(raw):
    try:
        return read(gltf.parse(bytes(raw))[0])
    except Exception:          # noqa: BLE001 - not a GLB: no block
        return None


def mesh_hash(doc, binary):
    """sha256 over what deformation depends on, other than clips: every skinned primitive's positions, triangle
    indices, joint indices and weights (decoded, fixed dtypes, so a re-encode of the same data hashes the same), the
    inverse bind matrices, and the skin's joint names with their rest translations. Texture and materials are not
    included."""
    h = hashlib.sha256(b'hermes64-waiver-mesh/1')
    for r in lbs.primitives(doc, binary):
        if r['joints'] is None:
            continue
        for name, arr, dt in (('positions', r['positions'], '<f4'), ('indices', r['indices'], '<u4'),
                              ('joints', r['joints'], '<u2'), ('weights', r['weights'], '<f4')):
            if arr is None:
                h.update(name.encode() + b':none')
                continue
            a = np.ascontiguousarray(np.asarray(arr).astype(dt))
            h.update(('%s:%s;' % (name, 'x'.join(map(str, a.shape)))).encode())
            h.update(a.tobytes())
    skins = doc.get('skins') or []
    if skins:
        ibm = lbs.inverse_binds(doc, binary)
        h.update(b'ibm:' + (np.ascontiguousarray(ibm.astype('<f4')).tobytes() if ibm is not None else b'none'))
        for j in skins[0].get('joints', []):
            n = doc['nodes'][j]
            h.update(('joint:%s:%s;' % (n.get('name'), ','.join('%.6f' % float(v) for v in n.get('translation', [0, 0, 0])))).encode())
    return h.hexdigest()


def problems(block):
    """-> (code, [messages]): (None, []) for a usable block, 'waiver.invalid' for a malformed one, 'waiver.refused'
    for one that names a check the owner may not waive or a body over the hard cap."""
    bad = []
    if not isinstance(block, dict):
        return 'waiver.invalid', ['the waiver block is not an object']
    if block.get('format') != FORMAT:
        bad.append('format is not %s' % FORMAT)
    if block.get('approved_by') != 'owner':
        bad.append("approved_by must be 'owner'")
    owner = block.get('owner')
    if not owner_ok(owner):
        bad.append('owner must be the name the owner gave (owner_approved=<name>), not %r' % (owner,))
    day = block.get('approved_on')
    if not isinstance(day, str) or not DATE_RE.match(day):
        bad.append('approved_on must be a YYYY-MM-DD date')
    reason = block.get('reason')
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 400:
        bad.append('reason must be the owner\'s words (3-400 characters)')
    fh = block.get('file_hash')
    if not isinstance(fh, str) or not re.fullmatch(r'[0-9a-f]{64}', fh):
        bad.append('file_hash must be a sha256 hex digest')
    scope = block.get('scope')
    checks, clips = (scope.get('checks'), scope.get('clips')) if isinstance(scope, dict) else (None, None)
    if not isinstance(checks, list) or not checks or not all(isinstance(c, str) for c in checks):
        bad.append('scope.checks must list at least one check')
        checks = []
    per_clip = any(c in ('mesh.deformation', 'mesh.silhouette.floor') for c in checks)
    if not (clips == 'all' or (isinstance(clips, list) and (clips or not per_clip) and all(isinstance(c, str) for c in clips))):
        bad.append("scope.clips must list clips or be 'all'")
    measured = block.get('measured')
    if not isinstance(measured, dict) or not isinstance(measured.get('clips'), dict):
        bad.append('measured must hold the failing numbers per clip')
        measured = {}
    if bad:
        return 'waiver.invalid', bad
    never = [c for c in checks if c not in WAIVABLE]
    if never:
        return 'waiver.refused', ['%s cannot be waived: only %s may be (budget.body up to %d triangles); every other check '
                                  'guards the game itself' % (', '.join(never), ', '.join(WAIVABLE), BUDGET_HARD_CAP)]
    tris = measured.get('body_tris')
    if 'budget.body' in checks and (not isinstance(tris, int) or tris > BUDGET_HARD_CAP):
        return 'waiver.refused', ['budget.body may be waived only for a body of at most %d triangles (recorded: %s)'
                                  % (BUDGET_HARD_CAP, tris)]
    return None, []


def owner_ok(name):
    return isinstance(name, str) and bool(OWNER_RE.match(name.strip())) and \
        re.sub(r'[^a-z]+', ' ', name.lower()).strip() not in GENERIC_OWNERS


def _fails_deformation(n):
    return n['lo'] < EDGE_LIMITS[0] or n['hi'] > EDGE_LIMITS[1]


def numbers(n):
    """The block's per-clip record of the validator's per-clip numbers."""
    return {'edge_ratio': [round(n['lo'], 6), round(n['hi'], 6)], 'keys_out': int(n['keys_out']),
            'floor_dev_m': round(n['floor_dev'], 6), 'floor_keys': int(n['floor_keys'])}


def _within_deformation(now, rec):
    """-> None if the clip's deformation is inside its record (+TOLERANCE), else why not."""
    lo_rec, hi_rec = rec.get('edge_ratio', [1., 1.])
    lo_ok = lo_rec / (1 + TOLERANCE) if lo_rec < EDGE_LIMITS[0] else EDGE_LIMITS[0]
    hi_ok = hi_rec * (1 + TOLERANCE) if hi_rec > EDGE_LIMITS[1] else EDGE_LIMITS[1]
    why = []
    if now['lo'] < lo_ok:
        why.append('edge ratio low %.3f < %.3f (recorded %.3f - 5 %%)' % (now['lo'], lo_ok, lo_rec))
    if now['hi'] > hi_ok:
        why.append('edge ratio high %.3f > %.3f (recorded %.3f + 5 %%)' % (now['hi'], hi_ok, hi_rec))
    if now['keys_out'] > rec.get('keys_out', 0) * (1 + TOLERANCE):
        why.append('%d keys out > %d recorded' % (now['keys_out'], rec.get('keys_out', 0)))
    return '; '.join(why) or None


def _within_floor(now, rec):
    dev_rec = rec.get('floor_dev_m', 0.)
    why = []
    if rec.get('floor_keys', 0) <= 0:
        return 'no floor failure was recorded for this clip'
    if now['floor_dev'] > dev_rec * (1 + TOLERANCE):
        why.append('floor deviation %.4f m > %.4f m (recorded %.4f + 5 %%)' % (now['floor_dev'], dev_rec * (1 + TOLERANCE), dev_rec))
    if now['floor_keys'] > rec['floor_keys'] * (1 + TOLERANCE):
        why.append('%d floor keys > %d recorded' % (now['floor_keys'], rec['floor_keys']))
    return '; '.join(why) or None


def note(block, honored, **kw):
    d = {'present': True, 'honored': bool(honored)}
    if isinstance(block, dict):
        for k in ('format', 'approved_by', 'owner', 'approved_on', 'reason', 'scope', 'file_hash'):
            if k in block:
                d[k] = copy.deepcopy(block[k])
    d.update(kw)
    return d


def apply(rep, block, doc, binary, per, honor):
    """Move the failures this block covers from rep errors to rep['waived'] (validate_character, after every check).
    honor False: the block is only reported. per: the validator's per-clip numbers, None when the posed checks did
    not run."""
    d = rep.d
    if not honor:
        d['waiver'] = note(block, False, why='not granted by this caller: a waiver applies only where the project bound '
                                             'this file with hermes64_character bind waive=true owner_approved=<name>')
        return
    code, why = problems(block)
    if code:
        rep.error('waiver', code, '; '.join(why))
        d['waiver'] = note(block, False, why='; '.join(why))
        return
    if per is None:
        d['waiver'] = note(block, False, why='not applied: the validator stopped before the posed checks')
        return
    now_hash = mesh_hash(doc, binary)
    if now_hash != block['file_hash']:
        rep.error('waiver', 'waiver.hash_mismatch', 'the mesh/weights hash %s… differs from the one the waiver was granted '
                  'for (%s…); nothing is waived' % (now_hash[:12], block['file_hash'][:12]))
        d['waiver'] = note(block, False, why='mesh/weights hash differs', file_hash_now=now_hash)
        return
    scope_checks = set(block['scope']['checks'])
    scope_clips = block['scope']['clips']
    rec_clips = block['measured']['clips']
    owner = '%s, %s' % (block['owner'], block['approved_on'])

    def covered(clip):
        return (scope_clips == 'all' or clip in scope_clips) and clip in rec_clips

    keep, waived = [], []
    for e in d['errors']:
        c = e.get('code')
        if c == 'mesh.deformation' and c in scope_checks:
            failing = {k: v for k, v in per.items() if _fails_deformation(v)}
            ok, not_ok = {}, {}
            for clip, n in sorted(failing.items()):
                if not covered(clip):
                    not_ok[clip] = 'not in the waiver scope'
                    continue
                why = _within_deformation(n, rec_clips[clip])
                if why:
                    not_ok[clip] = 'grew beyond the waiver: ' + why
                else:
                    ok[clip] = {'now': numbers(n), 'recorded': rec_clips[clip]}
            if ok:
                lo = min(per[c2]['lo'] for c2 in ok)
                hi = max(per[c2]['hi'] for c2 in ok)
                waived.append({'check': 'deformation', 'code': c, 'clips': ok,
                               'message': 'WAIVED (%s): edge ratio %.3f..%.3f outside %s in %s' % (
                                   owner, lo, hi, EDGE_LIMITS, ', '.join('%s (%d keys)' % (k, ok[k]['now']['keys_out']) for k in ok))})
            if not_ok:
                e = dict(e, message='%s; not covered by the owner waiver: %s' % (
                    e['message'], '; '.join('%s: %s' % kv for kv in sorted(not_ok.items()))))
                keep.append(e)
            continue
        if c == 'mesh.silhouette.floor' and c in scope_checks:
            m = FLOOR_RE.match(e.get('message', ''))
            clip = m.group(1) if m else None
            if clip is not None and covered(clip) and clip in per:
                why = _within_floor(per[clip], rec_clips[clip])
                if not why:
                    waived.append({'check': 'silhouette', 'code': c, 'clips': {clip: {'now': numbers(per[clip]), 'recorded': rec_clips[clip]}},
                                   'message': 'WAIVED (%s): %s' % (owner, e['message'])})
                    continue
                e = dict(e, message='%s; not covered by the owner waiver: %s' % (e['message'], why))
            elif clip is not None:
                e = dict(e, message='%s; not covered by the owner waiver: not in the waiver scope' % e['message'])
            keep.append(e)
            continue
        if c == 'budget.body' and c in scope_checks:
            tris = (d['checks'].get('budget') or {}).get('body_tris')
            rec = block['measured'].get('body_tris')
            if isinstance(tris, int) and tris <= BUDGET_HARD_CAP and isinstance(rec, int) and tris <= rec:
                waived.append({'check': 'budget', 'code': c, 'body_tris': tris, 'recorded_body_tris': rec,
                               'message': 'WAIVED (%s): %s (hard cap %d)' % (owner, e['message'], BUDGET_HARD_CAP)})
                continue
            e = dict(e, message='%s; not covered by the owner waiver: %d triangles (recorded %s, hard cap %d)' % (
                e['message'], tris if isinstance(tris, int) else -1, rec, BUDGET_HARD_CAP))
        keep.append(e)
    d['errors'] = keep
    touched = {w['check'] for w in waived} | {e['check'] for e in keep}
    for name in touched:
        c = d['checks'].setdefault(name, {'ok': True})
        c['ok'] = not any(e['check'] == name for e in keep)
        n = sum(1 for w in waived if w['check'] == name)
        if n:
            c['waived'] = n
    d['ok'] = not keep
    d['waived'] = waived
    d['waiver'] = note(block, True, result=('WAIVED' if waived and not keep else 'not ok' if keep else 'nothing to waive'),
                       waived_checks=sorted({w['code'] for w in waived}))


def waived_lines(waived, prefix='rig '):
    """report['waived'] -> short lines for tool results: one per check, the floor's per-key entries grouped by clip
    (report['waived'] itself keeps every entry)."""
    out, floor = [], {}
    for w in waived:
        if w.get('code') == 'mesh.silhouette.floor' and len(w.get('clips') or {}) == 1:
            clip, n = next(iter(w['clips'].items()))
            floor.setdefault(clip, (w, n['now']))
            continue
        out.append('%s%s: %s' % (prefix, w['code'], w['message']))
    if floor:
        owner = FLOOR_OWNER_RE.match(next(iter(floor.values()))[0]['message'])
        dev = max(now['floor_dev_m'] for _, now in floor.values())
        out.append('%smesh.silhouette.floor: WAIVED (%s): lowest vertex off the floor by up to %.4f m in %s' % (
            prefix, owner.group(1) if owner else '?', dev,
            ', '.join('%s (%d keys)' % (c, now['floor_keys']) for c, (_, now) in sorted(floor.items()))))
    return out


def write(raw, block):
    """The GLB with this block as root extras hermes64_waiver (JSON chunk only; the binary chunk is copied)."""
    doc, binary = gltf.parse(bytes(raw))
    doc = copy.deepcopy(doc)
    doc['extras'] = dict(doc.get('extras') or {}, **{WAIVER_KEY: block})
    return gltf.encode(doc, binary)


def strip(raw):
    """The GLB without a waiver block (unchanged bytes when it has none)."""
    doc, binary = gltf.parse(bytes(raw))
    if read(doc) is None:
        return bytes(raw)
    doc = copy.deepcopy(doc)
    doc['extras'].pop(WAIVER_KEY)
    if not doc['extras']:
        doc.pop('extras')
    return gltf.encode(doc, binary)


def make_block(owner, reason, approved_on, checks, clips, measured, file_hash):
    return {'format': FORMAT, 'approved_by': 'owner', 'owner': owner.strip(), 'approved_on': approved_on,
            'reason': reason.strip(), 'scope': {'checks': sorted(checks), 'clips': sorted(clips) if clips != 'all' else 'all'},
            'measured': measured, 'file_hash': file_hash}
