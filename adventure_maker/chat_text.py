"""Chat-safe plugin text (NATIVE lane, docs/NATIVE-RESULT.md).

The Hermes desktop app shows a slash-command reply as a small, dimmed system line in plain text: no Markdown is
rendered there (apps/desktop system-message.tsx, LinkifiedText pretty=false), so `**bold**` or a ``` fence would show
as literal characters. Other surfaces (a Telegram chat, a model quoting the text in its reply) do render Markdown.
Text that reads cleanly in both: short lines, no leading indentation, '- ' bullets, tool names and placeholders in
backticks, no <angle> placeholders, no raw JSON, no terminal escape codes, at most MAX_LINES lines.
"""
import re

MAX_LINES = 12
MAX_LINE_CHARS = 400
_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')
_CODE_SPAN = re.compile(r'`[^`\n]*`')
_ANGLE = re.compile(r'<[A-Za-z][^<>\n]{0,60}>')
_EMPHASIS = re.compile(r'(?<![\w`*])(\*\*?|__?)(?=\S)[^*_\n]+?(?<=\S)\1(?![\w`*])')


def hazards(text, max_lines=MAX_LINES):
    """Patterns a chat renderer shows differently from what was meant: (line number, kind) pairs, 1-based."""
    out = []
    lines = str(text).split('\n')
    if len(lines) > max_lines:
        out.append((0, 'more than %d lines' % max_lines))
    for n, line in enumerate(lines, 1):
        bare = _CODE_SPAN.sub('', line)
        if _ANSI.search(line):
            out.append((n, 'terminal escape code'))
        if line.startswith('\t') or line.startswith('    '):
            out.append((n, 'leading indentation (a Markdown code block)'))
        if line.lstrip().startswith('>'):
            out.append((n, 'leading > (a Markdown quote)'))
        if _ANGLE.search(bare):
            out.append((n, '<angle> text outside backticks (dropped as HTML)'))
        if _EMPHASIS.search(bare):
            out.append((n, '*/_ pair outside backticks (rendered as emphasis)'))
        if line.lstrip().startswith(('{"', "{'", '[{')):
            out.append((n, 'raw JSON'))
        if len(line) > MAX_LINE_CHARS:
            out.append((n, 'line over %d characters' % MAX_LINE_CHARS))
    return out


def tidy(text):
    """Remove what never renders well anywhere: terminal escape codes, tabs and deep leading indentation."""
    lines = []
    for line in _ANSI.sub('', str(text)).split('\n'):
        stripped = line.lstrip(' \t')
        indent = len(line[:len(line) - len(stripped)].expandtabs(4))
        lines.append(('  ' if indent >= 2 and stripped else '') + stripped.rstrip())
    return '\n'.join(lines).strip('\n')
