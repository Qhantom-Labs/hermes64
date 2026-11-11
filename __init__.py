"""Hermes64 native plugin entrypoint. Registration has no I/O or children."""
from pathlib import Path
from .adventure_maker.tools import register_tools, make_command
from .adventure_modules.tools import register_tools as register_module_tools
from .adventure_maker.audio_tools import register_audio_tools
from .adventure_maker.demo import register_tools as register_ship_tools
from .adventure_maker.cover_tools import register_cover_tools
from .adventure_maker.character_tools import register_character_tools
from .adventure_maker.hub import register_tools as register_hub_tools
from .adventure_maker import host_compat, native_hint

# Bundled skills carry the detail the compact tool schemas leave out (docs/TOKEN-DIET.md).
# Descriptions mirror each SKILL.md frontmatter (tests/test_schema_budget.py checks they match).
SKILLS = {
    'hermes64-author': 'Use when building original games. Compile maps and verify.',
    'hermes64': 'Make and safely edit retro-style 3D adventure games.',
    'hermes64-audio': 'Create and validate original retro game audio banks.',
    'hermes64-gameplay-modules': 'Use when authoring gameplay data. Verify bounded contracts.',
    'hermes64-playtest-and-ship': 'Use when testing or shipping Hermes64. Keep proof gates.',
    'hermes64-cover': 'Stage, render, gate and finish original box-art covers.',
    'hermes64-characters': 'Make house-style characters with hermes64_character.',
    'hermes64-hub': 'Use when sharing or installing Hermes64 Hub entries.',
    'hermes64-generators': 'Use when a game needs a new prop. Author bounded recipes.',
    'hermes64-places': 'Use when asked for a type of place. Dress rooms from data.',
    'hermes64-create': 'Use for any request to make, edit, play or export a game.',
}


def register(ctx):
    # Older hosts (Hermes < 0.20.1 has no ctx.get_config/ctx.state) get a compatibility ctx; a host without the tool
    # API is refused with one plain sentence (docs/HOST-COMPAT.md).
    ctx = host_compat.adapt(ctx)
    register_tools(ctx)
    register_module_tools(ctx)
    register_audio_tools(ctx)
    register_ship_tools(ctx)
    register_cover_tools(ctx)
    register_character_tools(ctx)
    register_hub_tools(ctx)
    host_compat.register_command(ctx, 'hermes64', make_command(ctx),
                                 description='First run: /hermes64 setup. Make a game: /hermes64 new "<premise>" [village|forest|polar]; share: /hermes64 hub search <words>',
                                 args_hint='setup | new "<premise>" [style] | hub search|info|install|pack|publish ...')
    add_skill = getattr(ctx, 'register_skill', None)
    if callable(add_skill):
        for name, description in SKILLS.items():
            try:  # older hosts or a trimmed install must not lose the tools over a skill
                add_skill(name, Path(__file__).absolute().parent / 'skills' / name / 'SKILL.md', description)
            except (OSError, ValueError):
                pass
    # A plain "make me a game about ..." reaches the create skill on hosts that keep plugin skills out of the index.
    native_hint.register(ctx)
