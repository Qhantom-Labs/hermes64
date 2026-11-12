"""Route game requests to create on every host exposing pre_llm_call.

The host appends context to the user turn (and may persist it in api_content),
not the system prompt. It runs once per user turn, not between tool calls.
Only a successful create skill_view call/result pair suppresses the hint;
root/author sibling banners, prior hints and failed loads are not evidence.
When the user names another engine or language (OTHER_ENGINE_NAMES/WORDS), the hint drops its "Do NOT write
HTML/..." sentence: an explicit request for another engine wins.
Pure conversation inspection: no I/O, never breaks the host turn.
"""
import json
import re

SKILL = 'hermes64:hermes64-create'
SKILL_NAMES = (SKILL, 'plugin:' + SKILL, 'hermes64-create')
GUARD = "Do NOT write HTML/JavaScript/Canvas/Unity/other engines. "
HINT = ("Hermes64 is installed: use it for any game request. " + GUARD +
        "Load the create skill FIRST: skill_view(name='plugin:hermes64:hermes64-create') "
        "(alias: skill_view(name='hermes64:hermes64-create')), then use the hermes64_* tools and follow its create flow. "
        "Do not detour to game-authoring or stop after doctor; doctor is a checklist, not a game.")
# The user asked for another engine or language: the same hint without GUARD, so their explicit choice wins.
HINT_OTHER_ENGINE = HINT.replace(GUARD, '')
# Engines and languages a user may ask for instead. NAMES count anywhere as whole words (case-insensitive). WORDS are
# also ordinary English (a unity of purpose, a python), so they count only as "in/with/using/via WORD" or
# "WORD game/engine/code/project/script/app".
OTHER_ENGINE_NAMES = ('html', 'html5', 'javascript', 'js', 'typescript', 'webgl', 'three.js', 'threejs', 'phaser',
                      'pixi.js', 'babylon.js', 'p5.js', 'unity3d', 'unreal', 'roblox', 'luau', 'game maker',
                      'gamemaker', 'rpg maker', 'defold', 'love2d', 'pico-8', 'pico8', 'gdevelop', 'bevy', 'monogame',
                      'libgdx', 'raylib', 'pygame', 'c++', 'c#', 'csharp')
OTHER_ENGINE_WORDS = ('unity', 'canvas', 'python', 'rust', 'java', 'lua', 'swift', 'scratch', 'construct', 'react')


def _either(words):
    return '|'.join(re.escape(w).replace(r'\ ', r'\s+') for w in sorted(words, key=len, reverse=True))


_OTHER_ENGINE = re.compile(r'(?<![\w.#+-])(?:%s|(?:in|with|using|via)\s+(?:%s)|(?:%s)\s+'
                           r'(?:games?|engine|code|project|script|app))(?![\w#+])'
                           % (_either(OTHER_ENGINE_NAMES), _either(OTHER_ENGINE_WORDS), _either(OTHER_ENGINE_WORDS)),
                           re.I)
_VERB = (r'(make|making|build|building|create|creating|design|generate|prototype|want|need|craft|edit|change|add|'
         r'remix|play|playtest|export|ship)')
_NOUN = r'(game|games|adventure|adventures|platformer|rpg|level|levels|quest)'
# "a game plan", "game theory" and friends are not game requests (known-bad controls in tests/test_native_hint.py).
_REQUEST = re.compile(r'\b%s\b[^.?!\n]{0,80}?\b%s\b(?!\s+(plan|plans|theory|changer|day|night|show|face)\b)'
                      % (_VERB, _NOUN), re.I)
_NAMED = re.compile(r'\bhermes ?64\b', re.I)
HISTORY_WINDOW = 80


def message_text(message):
    """Text of a user message: a string, or the text parts of a multimodal content list."""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return message_text(message.get('content') or message.get('text') or '')
    if isinstance(message, (list, tuple)):
        return ' '.join(message_text(part) for part in message if isinstance(part, (str, dict)))
    return ''


def looks_like_game_request(text):
    return bool(text) and bool(_NAMED.search(text) or _REQUEST.search(text))


def names_other_engine(text, history=None):
    """True when this message, or one of the user's recent messages, names another engine or language.

    Only user rows count, and this hint's own text is removed first (it names engines itself).
    """
    rows = list(history)[-HISTORY_WINDOW:] if isinstance(history, (list, tuple)) else []
    texts = [text] + [message_text(row.get('content')) for row in rows
                      if isinstance(row, dict) and row.get('role') == 'user']
    return any(_OTHER_ENGINE.search(t.replace(HINT, '').replace(GUARD, '')) for t in texts if t)


def skill_loaded(history):
    """Require a matching successful skill_view result containing the create body.

    A pending call, a root/author result with the host's sibling banner, a
    linked reference and a user/assistant mention do not load this skill.
    """
    if not isinstance(history, (list, tuple)):
        return False
    calls = {}
    for row in history:
        if not isinstance(row, dict):
            continue
        if row.get('role') == 'assistant':
            for call in row.get('tool_calls') or []:
                if not isinstance(call, dict):
                    continue
                function = call.get('function') or {}
                if not isinstance(function, dict) or function.get('name') != 'skill_view':
                    continue
                args = function.get('arguments')
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except (TypeError, ValueError):
                    continue
                if (isinstance(args, dict) and args.get('name') in SKILL_NAMES
                        and not args.get('file_path') and call.get('id')):
                    calls[call['id']] = True
        elif row.get('role') == 'tool' and row.get('tool_call_id') in calls:
            raw = row.get('content')
            try:
                result = raw if isinstance(raw, dict) else json.loads(message_text(raw))
            except (TypeError, ValueError):
                continue
            if not isinstance(result, dict):
                continue
            body = result.get('content')
            if (result.get('success') is True and result.get('name') in SKILL_NAMES
                    and not result.get('file') and isinstance(body, str)
                    and re.search(r'^name:\s*[\"\']?hermes64-create[\"\']?\s*$', body, re.M)):
                return True
    return False


def pre_llm_call(user_message=None, conversation_history=None, **_kwargs):
    try:
        text = message_text(user_message)
        if not looks_like_game_request(text) or skill_loaded(conversation_history):
            return None
        return {'context': HINT_OTHER_ENGINE if names_other_engine(text, conversation_history) else HINT}
    except Exception:  # a hint must never break a turn
        return None


def register(ctx):
    """Register the hook where the host has one (0.18.2 and newer do); older hosts skip it silently."""
    add_hook = getattr(ctx, 'register_hook', None)
    if not callable(add_hook):
        return False
    try:
        add_hook('pre_llm_call', pre_llm_call)
    except (TypeError, ValueError, AttributeError):
        return False
    return True
