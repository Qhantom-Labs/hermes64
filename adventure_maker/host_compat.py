"""Host (Hermes Agent) compatibility for the plugin entrypoint. No I/O at import; registration reads no files.

Every host API Hermes64 touches is listed in docs/HOST-COMPAT.md. Summary:

- REQUIRED at registration: ``ctx.register_tool`` (Hermes >= 0.3). Missing -> one plain HostCompatError naming the
  minimum version, never an AttributeError deep inside a tool module.
- OPTIONAL, degraded when missing:
  ``ctx.get_config`` and ``ctx.state`` (both added in Hermes 0.20.1). On an older host (the owner's Windows PC ran 0.18.2)
  the adapter reads ``plugins.entries.hermes64.settings`` (legacy ``.config``) through
  ``hermes_cli.config.load_config_readonly`` (present in 0.18.2), else returns the default; ``state`` stays absent,
  so `/hermes64 new` without a projects_root gives the existing plain "choose a projects_root" message.
  ``ctx.register_command`` (0.4) and ``ctx.register_skill`` (0.10): skipped when missing.
- Version floor: MIN_HERMES. A host that reports an older ``hermes_cli.__version__`` is refused with a plain message;
  an unknown version is allowed (the API checks still apply). Hosts >= 0.21.2 also enforce ``requires_hermes`` in
  plugin.yaml before importing us.

ADOPT SLOT: the owner's PC agent applied a local compatibility fix for Hermes 0.18.2 whose diff has not been received.
When it arrives, compare it with this module (docs/HOST-COMPAT.md "Adopt the PC fix") and fold any API it touched
that this adapter does not cover into OPTIONAL/REQUIRED below, with a stub test in tests/test_host_compat.py.
"""
import logging
import re

MIN_HERMES = '0.18.2'          # oldest host whose plugin API source was read (git release 9de9c25f62) and that ran us
FULL_HERMES = '0.20.1'         # first release with ctx.get_config / ctx.state (commit 6bf93c0e38)
PLUGIN_ID = 'hermes64'
REQUIRED = ('register_tool',)
OPTIONAL = ('get_config', 'state', 'register_command', 'register_skill')

logger = logging.getLogger(__name__)
LAST_REPORT = {}


class HostCompatError(RuntimeError):
    """Plain, user-facing refusal: the host lacks an API Hermes64 cannot work without."""


def _version_tuple(text):
    m = re.match(r'\s*v?(\d+)\.(\d+)(?:\.(\d+))?', str(text or ''))
    return tuple(int(g or 0) for g in m.groups()) if m else None


def host_version():
    """The running Hermes version string, or '' when it cannot be read without I/O.

    Only a literal ``hermes_cli.__version__`` (0.18.x style) is read; newer hosts serve it lazily from an install
    stamp (file I/O, '0.0.0' placeholder), so it is treated as unknown there: those hosts enforce plugin.yaml's
    ``requires_hermes`` themselves (0.21.2+) and have every API this module checks."""
    try:
        import hermes_cli
        value = str(vars(hermes_cli).get('__version__') or '')
    except Exception:
        return ''
    return '' if value.startswith('0.0.0') else value


def _read_settings_fallback(plugin_id):
    """plugins.entries.<id>.settings (legacy .config) from the host's read-only config loader; {} if unavailable."""
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
    except Exception:
        return {}
    entry = cfg
    for key in ('plugins', 'entries', plugin_id):
        entry = entry.get(key) if isinstance(entry, dict) else None
    if not isinstance(entry, dict):
        return {}
    # Match native get_config's per-key fallback during a partial settings migration.
    # Explicit canonical blanks/nulls still override legacy values.
    result = dict(entry['config']) if isinstance(entry.get('config'), dict) else {}
    if isinstance(entry.get('settings'), dict):
        result.update(entry['settings'])
    return result


class CompatContext:
    """Delegates to the host ctx; supplies get_config on hosts older than FULL_HERMES. ``state`` is NOT invented."""

    def __init__(self, ctx, settings_reader=None):
        self._ctx = ctx
        self._read = settings_reader or _read_settings_fallback
        manifest = getattr(ctx, 'manifest', None)
        self._plugin_id = getattr(manifest, 'key', '') or getattr(manifest, 'name', '') or PLUGIN_ID

    def __getattr__(self, name):
        return getattr(self._ctx, name)

    def get_config(self, key, default=None):
        settings = self._read(self._plugin_id)
        value = settings.get(key, default) if isinstance(settings, dict) else default
        return default if value is None else value


def adapt(ctx, version=None, settings_reader=None):
    """Return a ctx the plugin modules can use, or raise HostCompatError with a plain sentence."""
    version = host_version() if version is None else version
    have = {name: hasattr(ctx, name) for name in REQUIRED + OPTIONAL}
    found = _version_tuple(version)
    report = {'host_version': version or 'unknown', 'min_hermes': MIN_HERMES, 'full_hermes': FULL_HERMES,
              'missing': sorted(name for name, ok in have.items() if not ok), 'mode': 'native'}
    LAST_REPORT.clear()
    LAST_REPORT.update(report)
    if found is not None and found < _version_tuple(MIN_HERMES):
        LAST_REPORT['mode'] = 'refused'
        raise HostCompatError('Hermes64 needs Hermes Agent %s or newer; this is %s. Update Hermes (hermes update), '
                              'then restart it.' % (MIN_HERMES, version))
    missing_required = [name for name in REQUIRED if not have[name]]
    if missing_required:
        LAST_REPORT['mode'] = 'refused'
        raise HostCompatError('Hermes64 cannot load: this Hermes host has no %s (plugin tool API). Hermes64 needs '
                              'Hermes Agent %s or newer.' % (', '.join('ctx.' + n for n in missing_required), MIN_HERMES))
    if have['get_config']:
        return ctx
    LAST_REPORT['mode'] = 'compat'
    logger.warning('Hermes64: host %s lacks %s; using compatibility mode (settings read from config.yaml, no plugin '
                   'data folder: set projects_root). Hermes %s or newer gives full support.',
                   version or 'unknown', ', '.join('ctx.' + n for n in report['missing']), FULL_HERMES)
    return CompatContext(ctx, settings_reader)


def register_command(ctx, name, handler, description, args_hint):
    """ctx.register_command when the host has it; older signatures without args_hint are retried once."""
    add = getattr(ctx, 'register_command', None)
    if not callable(add):
        return False
    try:
        add(name, handler, description=description, args_hint=args_hint)
    except TypeError as exc:
        if 'args_hint' not in str(exc):
            raise
        add(name, handler, description=description)
    return True
