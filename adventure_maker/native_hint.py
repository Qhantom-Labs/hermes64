"""One-line hint so a plain sentence reaches Hermes64 (docs/NATIVE-RESULT.md).

A user installs the plugin and tells their agent "make me a game about ...": no slash command, no preloaded skill.
Hosts before 0.21.6 keep plugin skills out of the agent's skills index (skill_view by exact name only), so the agent
may never learn that the create skill exists. This ``pre_llm_call`` hook adds ONE line to that turn's user message
when the message looks like a game request and the conversation has not loaded the create skill yet. Hosts treat
hook context as ephemeral (never stored, never in the system prompt). Pure text matching: no I/O, never raises.
"""
import json
import re

SKILL = 'hermes64:hermes64-create'
HINT = ("Hermes64 plugin: for this game request, load skill_view('%s') first unless it is already loaded, "
        "then follow it. No slash command is needed." % SKILL)
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


def skill_loaded(history):
    """True when the recent conversation already viewed or carries the create skill."""
    if not history:
        return False
    try:
        blob = json.dumps(list(history)[-HISTORY_WINDOW:], default=str)
    except (TypeError, ValueError):
        return False
    return 'hermes64-create' in blob


def pre_llm_call(user_message=None, conversation_history=None, **_kwargs):
    try:
        text = message_text(user_message)
        if 'hermes64-create' in text or not looks_like_game_request(text) or skill_loaded(conversation_history):
            return None
        return {'context': HINT}
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
