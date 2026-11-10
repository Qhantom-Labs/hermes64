"""Explicit registration seam; importing this module never installs or activates it."""
from .schemas import SCHEMAS
from .service import ModuleService
if '.' in (__package__ or ''):
    from ..adventure_maker import wire
    from ..adventure_maker.plugin_settings import plugin_settings
else:
    from adventure_maker import wire
    from adventure_maker.plugin_settings import plugin_settings


def available():
    return True


def register_tools(ctx):
    def make_handler(name):
        def handler(args, **kwargs):
            return ModuleService(plugin_settings(ctx, ('projects_root', 'bundle_root'))).handle(name, args, **kwargs)
        return handler
    for name, schema in SCHEMAS.items():
        # Compact advertised copy; ModuleService validates against the frozen full schema.
        wire.register(ctx, name, schema, make_handler(name), available)
