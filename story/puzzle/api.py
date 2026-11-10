"""Version-dispatching facade: STORY 1.3.0 goes to the puzzle package, everything else to the unchanged core.

Callers that should accept 1.3 sources (module tools, puzzle playtest, examples) import from here; the
1.0-1.2 entry points in ``story.compiler``/``story.checker``/``story.saves`` are untouched.
"""
from ..compiler import compile_spec as compile12, validate_game as validate12
from ..checker import check_game as check12
from ..engine import Engine
from ..saves import make_save as make12, validate_save as validate_save12, migration_manifest as manifest12, migrate_save as migrate12
from ..modules.edits import edit as edit12, accepted
from . import is13


def compile_spec(spec):
    if is13(spec):
        from .compiler import compile_spec as compile13
        return compile13(spec)
    return compile12(spec)


def validate_game(game):
    if is13(game):
        from .compiler import validate_game as validate13
        return validate13(game)
    return validate12(game)


def check_game(game, max_states=100000, **kwargs):
    if is13(game):
        from .analysis import check
        return check(game, max_states)
    return check12(game, max_states, **kwargs)


def engine(game):
    if is13(game):
        from .model import PuzzleEngine
        return PuzzleEngine(game)
    return Engine(game)


def make_save(game, state, timestamps=None):
    if is13(game):
        from .saves import make_save as make13
        return make13(game, state, timestamps)
    return make12(game, state, timestamps)


def validate_save(save, game, max_states=100000):
    if is13(game):
        from .saves import validate_save as validate_save13
        return validate_save13(save, game, max_states)
    return validate_save12(save, game, max_states)


def migration_manifest(old, new):
    if is13(new):
        from .saves import migration_manifest as manifest13
        return manifest13(old, new)
    return manifest12(old, new)


def migrate_save(save, old, new, manifest=None, max_states=100000):
    if is13(new):
        from .saves import migrate_save as migrate13
        return migrate13(save, old, new, manifest, max_states)
    return migrate12(save, old, new, manifest, max_states)


def edit(spec, operation, expected_spec_hash, expected_game_hash, save=None):
    if is13(spec):
        from .edits import edit as edit13
        return edit13(spec, operation, expected_spec_hash, expected_game_hash, save)
    return edit12(spec, operation, expected_spec_hash, expected_game_hash, save)


__all__ = ['compile_spec', 'validate_game', 'check_game', 'engine', 'make_save', 'validate_save',
           'migration_manifest', 'migrate_save', 'edit', 'accepted', 'is13']
