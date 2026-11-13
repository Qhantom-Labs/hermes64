"""Creation receipts: launch the built bytes, and name starter substitutions plainly."""
import json
from pathlib import Path
import re


def how_to_play(root, settings, captures=None, playtest=None):
    """Use the current capture/playtest receipt, never an arbitrary older runtime."""
    from .platforms import command_line
    from .runner import locate
    from .safety import Fault
    root = Path(root)
    runtime = None
    for receipt in (captures or {}, playtest or {}):
        rel = receipt.get('report_path')
        if not rel:
            continue
        candidate = root / Path(rel).parent / 'runtime'
        if root.resolve() in candidate.resolve().parents and current_runtime(root, candidate):
            runtime = candidate
            break
    out = {'available': False, 'project_dir': str(root), 'argv': [], 'command': None, 'keys': None}
    lines = ['How to play', 'Game folder: ' + str(root)]
    if runtime is None:
        out['lines'] = lines + ['Play not ready: no built runtime; resume the build first.']
        return out
    try:
        godot = locate('godot', settings.get('godot_path') or '')
    except Fault as exc:
        out['lines'] = lines + ['Play not ready: ' + ' '.join(str(exc).split())]
        return out
    argv = [godot, '--path', str(runtime), '--', '--pack=res://theme.json']
    command = command_line(argv)
    try:
        keys = runtime_keys(runtime)
    except (OSError, ValueError, KeyError):
        keys = 'not available; open the in-game pause menu to inspect controls'
    out.update(available=True, runtime=str(runtime), argv=argv, command=command, keys=keys,
               lines=lines + ['Play: ' + command, 'Default keys: ' + keys])
    return out


def current_runtime(root, runtime):
    """Do not advertise an incomplete runtime or a capture of an older revision."""
    if not all((runtime / name).is_file() for name in ('project.godot', 'game.json', 'theme.json')):
        return False
    try:
        game = json.loads((runtime / 'game.json').read_text(encoding='utf-8'))
        pointer = root / '.maker/current.json'
        if pointer.is_file():
            current = root / json.loads(pointer.read_text(encoding='utf-8'))['game']
            if root.resolve() not in current.resolve().parents:
                return False
            return game == json.loads(current.read_text(encoding='utf-8'))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def runtime_keys(runtime):
    """Labels from the staged HUD hints, keys from its staged default input profile.

    Saved personal remaps are deliberately not read: these are labelled default keys.
    """
    runtime = Path(runtime)
    hud = json.loads((runtime / 'input/keyhud.json').read_text(encoding='utf-8'))
    profile = (runtime / 'input/profile.gd').read_text(encoding='utf-8').split('static func validate', 1)[0]
    bindings = dict(re.findall(r'"(\w+)":\s*\[\s*\{"key":KEY_(\w+)', profile))
    labels = {r['action']: r['word'] for r in hud['pause']['controls']}
    game = json.loads((runtime / 'game.json').read_text(encoding='utf-8'))
    combat = any(m.get('id') == 'combat' for m in game.get('gameplay', {}).get('modules', []))
    actions = list(hud['hint']['moments']['start']['actions'])
    actions += ['run', 'action_menu', 'inventory', 'menu']
    if combat:
        actions += hud['hint']['moments']['arena_combat']['actions']
        labels['primary'] += '/Attack'
    pretty = {'ESCAPE': 'Esc', 'SPACE': 'Space', 'SHIFT': 'Shift', 'ALT': 'Alt', 'TAB': 'Tab',
              'BACKSPACE': 'Backspace', 'CTRL': 'Ctrl', 'ENTER': 'Enter'}
    rows = []
    for action in dict.fromkeys(actions):
        if action == 'move':
            key = ''.join(bindings['move_' + d] for d in ('up', 'left', 'down', 'right'))
        elif action in bindings:
            key = pretty.get(bindings[action], bindings[action])
        else:
            continue
        rows.append(key + ' ' + ('Pause/settings' if action == 'menu' else labels.get(action, action.title())))
    return '; '.join(rows)


def audit_details(report):
    """Explain a sub-90 result with its measured findings; never relabel the gate."""
    if not report or report.get('score', 100) >= 90:
        return ''
    findings = [f for room in report.get('rooms', []) for f in room.get('findings', [])]
    errors = [f for f in findings if f.get('severity') == 'error']
    reasons = list(dict.fromkeys(' '.join(str(f.get('says', '')).split()) for f in errors or findings))
    remainder = '; %d more; see the measured audit report' % (len(reasons) - 3) if len(reasons) > 3 else ''
    return 'Style detail: %s/100 (target 90); %s%s.' % (
        report['score'], '; '.join(reasons[:3]) or 'see the measured audit report for the shortfall', remainder)


# Only explicit mechanics words, not the absence of a setting/genre keyword.
UNSUPPORTED = (
    ('racing/driving', r'\b(?:racing|kart|driving|car race|vehicle)\b'),
    ('platform jumping', r'\b(?:platformer|platforming)\b'),
    ('shooting', r'\b(?:shooter|shooting|fps)\b'),
    ('multiplayer', r'\b(?:multiplayer|mmo|co-op|online game)\b'),
    ('strategy', r'\b(?:rts|strategy|turn-based)\b'),
    ('simulation', r'\b(?:simulator|simulation|farming game|cooking game)\b'),
)


def generic_prompt(premise):
    """Keep recognised names in the title/prompt receipt, not the generated story."""
    from .brief import IP_HINTS
    result = premise
    for term in sorted(IP_HINTS, key=len, reverse=True):
        pattern = r'\b' + r'[\s-]+'.join(map(re.escape, term.split())) + r'\b'
        result = re.sub(pattern, IP_HINTS[term][1], result, flags=re.I)
    return result


def reply_notes(premise, asked, spec, template):
    """One Note line each for unsupported mechanics, recognised names, stock parts."""
    from .brief import _mentions
    notes = []
    misses = [name for name, pattern in UNSUPPORTED if re.search(pattern, premise, re.I)]
    made = ('a walk-and-talk collect-and-return adventure' if template == 'two_room_collect_v1'
            else 'an on-foot combat arena adventure')
    if misses:
        notes.append('Note: %s is not supported by this quick starter; made %s instead.' % (', '.join(misses), made))
    terms = (asked or {}).get('ip_terms', [])
    if terms:
        names = ', '.join('"%s"' % t['term'].title() for t in terms)
        story = json.dumps({k: v for k, v in spec.items() if k not in ('title', 'metadata')}, ensure_ascii=False)
        in_story = any(_mentions(t['term'], story) for t in terms)
        where = 'in story text as well as the title' if in_story else 'only as title text'
        notes.append('Note: %s is kept %s, not recreated as a character or world; '
                     'try an original name such as "Amber Trail".' % (names, where))
    parts = []
    for row in spec.get('characters', []):
        if _mentions(row.get('name', ''), premise) and row.get('body_id'):
            body = row['body_id']
            human = 'human' in body or 'human' in row.get('base_rig_id', '')
            what = 'human body' if human else body.replace('_', ' ') + ' body'
            parts.append('"%s" uses the stock %s' % (row['name'], what))
    for row in spec.get('collectibles', []):
        if _mentions(row.get('name', ''), premise) and row.get('asset'):
            model = row['asset'].split('.')[-1].split('/')[-1].replace('_', ' ')
            parts.append('"%s" uses the stock %s model' % (row['name'], model))
    if parts:
        notes.append('Note: ' + '; '.join(parts) + '; their names do not change those shapes.')
    return notes
