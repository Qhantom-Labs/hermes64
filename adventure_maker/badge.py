"""Proof badge: a compact, deterministic summary of existing proof, playtest and style reports.

The badge never claims more than its inputs show. A missing report reads "not run", a
failed gate is named in capitals, the playtest tier (SOLID/PLAYABLE/ROUGH/BROKEN) is
copied and never upgraded, and reports from different builds are flagged. Same inputs
always give the same badge (no clocks, no randomness).

    from adventure_maker.badge import compute, from_paths
"""
import json
from pathlib import Path

FORMAT = 'hermes64-proof-badge/1'
TIERS = ('SOLID', 'PLAYABLE', 'ROUGH', 'BROKEN')
SEPARATOR = ' · '


def plural(count, word):
    return '%d %s%s' % (count, word, '' if count == 1 else 's')


def _proof(proof):
    if not isinstance(proof, dict) or 'status' not in proof:
        return {'status': 'not_run'}, 'proof not run'
    status = str(proof.get('status'))
    row = {'status': status, 'complete': proof.get('complete'), 'softlock_count': proof.get('softlock_count')}
    text = {'proved': 'proof-checked', 'conditional': 'proof conditional', 'inconclusive': 'proof inconclusive'}.get(
        status, 'proof FAILED (' + status + ')')
    return row, text


def _softlocks(proof):
    if not isinstance(proof, dict) or 'status' not in proof:
        return 'softlocks not checked'
    count = proof.get('softlock_count')
    if isinstance(count, int) and not isinstance(count, bool):
        return plural(count, 'softlock') if count == 0 else plural(count, 'SOFTLOCK').upper()
    return 'softlocks unknown (search incomplete)'


def _bots(playtest):
    if not isinstance(playtest, dict) or 'verdict' not in playtest:
        return {'played': 0, 'status': 'not_run'}, 'bots not run'
    raw = playtest.get('paths')
    paths = raw if isinstance(raw, list) else []
    winning = len(paths)
    passed = sum(1 for row in paths if isinstance(row, dict) and row.get('passed') is True)
    replays = [str(name) for name in playtest.get('replay_files', []) if isinstance(name, str)]
    explorer = any(Path(name).name.startswith('explorer') for name in replays)
    played = winning + (1 if explorer else 0)
    row = {'played': played, 'winning_paths': winning, 'winning_passed': passed, 'explorer': explorer}
    text = plural(played, 'bot') + ' played'
    if passed < winning:
        text += ' (' + plural(winning - passed, 'winning path') + ' FAILED)'
    stuck = playtest.get('stuck')
    if isinstance(stuck, list) and stuck:
        row['stuck'] = len(stuck)
        text += ' (' + str(len(stuck)) + ' STUCK)'
    return row, text


def _style(style):
    if not isinstance(style, dict) or style.get('status') not in ('passed', 'failed'):
        return {'status': 'not_run'}, 'style gate not run'
    rooms = [r for r in style.get('rooms', []) if isinstance(r, dict)]
    failed = [r.get('id') for r in rooms if r.get('status') != 'passed']
    row = {'status': style['status'], 'rooms': len(rooms), 'rooms_failed': failed}
    if style['status'] == 'passed' and not failed:
        return row, 'style gate pass'
    detail = '%d/%d rooms' % (len(failed), len(rooms)) if rooms else 'set-level'
    return dict(row, status='failed'), 'style gate FAILED (' + detail + ')'


def _audit(audit):
    """Style audit (hermes64_check action=audit, audit.json). Replaces the style-gate slot when supplied."""
    if not isinstance(audit, dict):
        return None, None
    status = audit.get('status')
    if audit.get('rendered') is False and status == 'FAIL':
        return {'status': 'FAIL', 'static_only': True}, 'style audit FAIL (static check; render not run)'
    if audit.get('rendered') is False or status in (None, 'not_run'):
        why = audit.get('not_run_reason') or 'no display'
        return {'status': 'not_run', 'reason': why}, 'style audit not run (%s)' % why
    rooms = [r for r in audit.get('rooms', []) if isinstance(r, dict)]
    failed = [r.get('id') for r in rooms if r.get('status') == 'FAIL']
    score = audit.get('score')
    row = {'status': status, 'score': score, 'rooms': len(rooms), 'rooms_failed': failed}
    if status == 'FAIL':
        return row, 'style audit FAIL %s/100 (%d/%d rooms)' % (score, len(failed), len(rooms))
    return row, 'style audit %s %s/100' % (status, score)


def _assets(assets):
    """Room shells/kit assets (hermes64_build_assets), supplied by /hermes64 new: a style audit of an unbuilt game
    measures cutaway voids, so the badge says whether the assets were built before it. None when not supplied."""
    if not isinstance(assets, dict):
        return None, None
    status = assets.get('status')
    if status == 'passed':
        return {'status': 'passed', 'builder': assets.get('builder')}, 'assets built'
    why = ' '.join(str(assets.get('reason') or 'not run').split())[:80]
    if status == 'failed':
        return {'status': 'failed', 'builder': assets.get('builder'), 'reason': why}, 'assets build FAILED'
    return {'status': 'not_run', 'reason': why}, 'assets NOT BUILT (%s)' % why


def _tier(playtest):
    if not isinstance(playtest, dict) or playtest.get('verdict') not in TIERS:
        return {'verdict': 'not_run'}, 'tier not run'
    verdict = playtest['verdict']
    headless = playtest.get('display') == 'headless' or playtest.get('render_verified') is not True
    row = {'verdict': verdict, 'headless': headless}
    return row, verdict + (' (headless)' if headless else ' (rendered)')


def compute(proof=None, playtest=None, style=None, sources=None, audit=None, assets=None, required_modules=None):
    """Badge dict from report objects (any may be None). ``text`` is the one-line badge. A style audit report,
    when supplied, takes the style slot; a FAILED audit, like a failed style gate, keeps ``ok`` false. An assets row
    (MERGE5, /hermes64 new), when supplied, goes before the style slot and keeps ``ok`` false unless the assets
    were built."""
    proof_row, proof_text = _proof(proof)
    bots_row, bots_text = _bots(playtest)
    style_row, style_text = _style(style)
    audit_row, audit_text = _audit(audit)
    assets_row, assets_text = _assets(assets)
    if audit_text:
        style_text = audit_text
    tier_row, tier_text = _tier(playtest)
    required = list(required_modules or [])
    physical = (proof_row['status'] == 'conditional' and proof.get('complete') is True
                and bool(required) and playtest is not None and playtest.get('module_physical') is True
                and playtest.get('completed') is True and bool(playtest.get('receipt'))
                and bool(proof.get('game_hash')) and proof.get('game_hash') == playtest.get('game_hash')
                and bool(bots_row.get('winning_paths'))
                and all(mid in playtest.get('modules_tested', []) for mid in required))
    if physical:
        proof_text = 'proof conditional (module bot completed)'
    parts = [proof_text, bots_text] + ([assets_text] if assets_text else []) + [style_text, _softlocks(proof), tier_text]
    hashes = sorted({str(r['game_hash']) for r in (proof, playtest) if isinstance(r, dict) and r.get('game_hash')})
    if len(hashes) > 1:
        parts.append('REPORTS FROM DIFFERENT BUILDS')
    ok = ((proof_row['status'] == 'proved' or physical) and _softlocks(proof) == '0 softlocks'
          and tier_row['verdict'] in ('SOLID', 'PLAYABLE')
          and style_row['status'] != 'failed' and (audit_row or {}).get('status') != 'FAIL'
          and (assets_row is None or assets_row['status'] == 'passed')
          and bots_row.get('winning_passed') == bots_row.get('winning_paths')
          and not bots_row.get('stuck') and len(hashes) <= 1)
    out = {'format': FORMAT, 'text': SEPARATOR.join(parts), 'ok': bool(ok), 'proof': proof_row,
           'bots': bots_row, 'style_gate': style_row, 'softlocks': _softlocks(proof), 'tier': tier_row,
           'game_hashes': hashes, 'sources': dict(sorted((sources or {}).items()))}
    if audit_row is not None:
        out['style_audit'] = audit_row
    if assets_row is not None:
        out['assets'] = assets_row
    return out


def _read(path):
    if not path:
        return None
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def from_paths(proof=None, playtest=None, style=None, base=None, audit=None, assets=None, required_modules=None):
    """Badge from report files (paths relative to ``base`` when given). Missing files read 'not run'.
    ``audit`` may also be a dict (e.g. {'status': 'not_run', 'rendered': False, 'not_run_reason': 'no display'}).
    ``assets`` is a dict: {'status': 'passed'|'failed'|'not_run', 'builder', 'reason', 'report_path'}."""
    def resolve(value):
        return None if not value else (Path(base) / value if base else Path(value))
    sources = {key: str(value) for key, value in (('proof', proof), ('playtest', playtest), ('style', style),
                                                    ('audit', audit if isinstance(audit, str) else None),
                                                    ('assets', (assets or {}).get('report_path'))) if value}
    audit_report = audit if isinstance(audit, dict) else _read(resolve(audit))
    return compute(_read(resolve(proof)), _read(resolve(playtest)), _read(resolve(style)), sources, audit_report,
                   assets, required_modules=required_modules)
