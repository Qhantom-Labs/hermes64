"""Hermes64 native plugin entrypoint. Registration has no I/O or children."""
from pathlib import Path
from .adventure_maker.tools import register_tools, make_command
from .adventure_modules.tools import register_tools as register_module_tools
from .adventure_maker.audio_tools import register_audio_tools
from .adventure_maker.demo import register_tools as register_ship_tools
from .adventure_maker.cover_tools import register_cover_tools
from .adventure_maker.character_tools import register_character_tools
from .adventure_maker.hub import register_tools as register_hub_tools

# Bundled skills carry the detail the compact tool schemas leave out (docs/TOKEN-DIET.md).
# Descriptions mirror each SKILL.md frontmatter (tests/test_schema_budget.py checks they match).
SKILLS = {
    'hermes64': 'Make and safely edit retro-style 3D adventure games.',
    'hermes64-audio': 'Create and validate original retro game audio banks.',
    'hermes64-gameplay-modules': 'Use when authoring gameplay data. Verify bounded contracts.',
    'hermes64-playtest-and-ship': 'Use when testing or shipping Hermes64. Keep proof gates.',
    'hermes64-cover': 'Stage, render, gate and finish original box-art covers.',
    'hermes64-characters': 'Make house-style characters with hermes64_character.',
    'hermes64-hub': 'Use when sharing or installing Hermes64 Hub entries.',
}


def register(ctx):
    register_tools(ctx)
    register_module_tools(ctx)
    register_audio_tools(ctx)
    register_ship_tools(ctx)
    register_cover_tools(ctx)
    register_character_tools(ctx)
    register_hub_tools(ctx)
    ctx.register_command('hermes64', make_command(ctx),
                         description='Make a game: /hermes64 new "<premise>" [village|forest|polar]; share: /hermes64 hub search <words>',
                         args_hint='new "<premise>" [style] | hub search|info|install|pack|publish ...')
    add_skill = getattr(ctx, 'register_skill', None)
    if callable(add_skill):
        for name, description in SKILLS.items():
            try:  # older hosts or a trimmed install must not lose the tools over a skill
                add_skill(name, Path(__file__).absolute().parent / 'skills' / name / 'SKILL.md', description)
            except (OSError, ValueError):
                pass
