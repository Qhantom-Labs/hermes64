"""Per-call plugin settings, plus the one default games folder used by `new`.

When projects_root is blank, `/hermes64 new` (and hermes64_demo with a premise) creates
games under the profile's Hermes plugin-data folder, ``<plugin data>/games``. Other tools
use that folder only after it exists, i.e. after an explicit `new`; otherwise they keep
the original "choose a projects_root" error. A configured projects_root always wins.
Nothing here performs I/O at registration time.

The plugin-data folder comes from the documented ``plugins.plugin_storage.plugin_data_dir``
(Hermes 0.20.4+), the same call Hermes64 Studio (dashboard/plugin_api.py) makes, so both
halves show the same games. Hosts without it fall back to ``ctx.state.data_dir``.
"""
from pathlib import Path

PLUGIN_ID = 'hermes64'


def storage_data_dir():
    """``<hermes home>/plugin-data/hermes64`` via the documented durable-state API, or None on older hosts."""
    try:
        from plugins.plugin_storage import plugin_data_dir
        path = Path(str(plugin_data_dir(PLUGIN_ID)))
    except Exception:
        return None
    return path if path.is_absolute() else None


def default_games_root(ctx):
    """``<Hermes plugin data dir>/games`` when the host exposes a plugin data folder, else None."""
    data_dir = storage_data_dir()
    if data_dir is None:
        raw = getattr(getattr(ctx, 'state', None), 'data_dir', None)
        data_dir = Path(str(raw)) if raw else None
    if data_dir is None or not data_dir.is_absolute():
        return None
    return data_dir / 'games'


def default_hub_root(ctx):
    """``<Hermes plugin data dir>/hub``: your packed hub entries, publish drafts and download cache."""
    games = default_games_root(ctx)
    return games.parent / 'hub' if games is not None else None


def plugin_settings(ctx, keys):
    settings = {key: ctx.get_config(key, '') for key in keys}
    if 'projects_root' in settings and not settings['projects_root']:
        default = default_games_root(ctx)
        if default is not None and default.is_dir():
            settings['projects_root'] = str(default)
    return settings
