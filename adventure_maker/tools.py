"""Public ctx APIs only; closures bind each handler without global profile state."""
from .schemas import SCHEMAS
from .service import Service
from .plugin_settings import plugin_settings
from . import wire

SETTINGS = ('projects_root', 'bundle_root', 'python_path', 'blender_path', 'godot_path', 'builder')


def available():
    # Discovery/scaffold are useful even when optional local engines are absent.
    # Per-operation prerequisite errors are returned by the service.
    return True


def register_tools(ctx):
    def make_handler(name):
        def handler(args, **kwargs):
            return Service(plugin_settings(ctx, SETTINGS)).handle(name, args, **kwargs)
        return handler
    for name, schema in SCHEMAS.items():
        # Advertised copy is compact (wire.py); the handler validates against the full schema.
        wire.register(ctx, name, schema, make_handler(name), available)


def help_command(raw_args='', **kwargs):
    return ('Hermes64 makes N64-era-style 3D adventures. Quick start: /hermes64 new "<one-sentence premise>" '
            '[village|forest|polar] checks your tools, builds the game, proof-checks and bot-plays it, then prints '
            'a proof badge and the command to play it. Share and reuse styles, kits, characters, sounds and games: '
            '/hermes64 hub search <words> (then hub info, hub install, hub pack, hub publish). Everything else uses the tools: '
            'hermes64_packs → hermes64_scaffold(pack=ID) → hermes64_compile → hermes64_check. '
            'Edit with hermes64_edit; always check after every edit. Never hand-edit generated files. '
            '/hermes64 setup checks dependencies; /hermes64 setup --fetch explicitly offers a pinned Godot download. '
            'Other downloads require hub_url. See the bundled hermes64 skill. Other /hermes64 text only shows this help; '
            'it is never executed.')


def make_command(ctx):
    """`/hermes64 new ...` creates a game (data only); `/hermes64 hub ...` runs a hub action; anything else is help."""
    def command(raw_args='', **kwargs):
        text = raw_args if isinstance(raw_args, str) else ''
        first = text.strip().split(None, 1)
        if first and first[0].lower() == 'new':
            from .newgame import command as new_command
            return new_command(ctx, text.strip()[len(first[0]):])
        if first and first[0].lower() == 'hub':
            from .hub import command as hub_command
            return hub_command(ctx, text.strip()[len(first[0]):])
        if first and first[0].lower() == 'setup':
            from .setup_check import command as setup_command
            return setup_command(ctx, text.strip()[len(first[0]):])
        return help_command(text)
    return command
