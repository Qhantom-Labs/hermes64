# Host compatibility: which Hermes Agent versions Hermes64 needs

**Minimum: Hermes Agent 0.18.2. Full support: 0.20.1 or newer.** Declared in `plugin.yaml` as
`"requires_hermes": ">=0.18.2"` (hosts 0.21.2+ check it before importing the plugin; older hosts ignore unknown
manifest fields) and enforced again in-process by `adventure_maker/host_compat.py`.

Why: Dylan's Windows PC ran Hermes Agent **0.18.2** and needed a local fix. Reading the 0.18.2 release source
(`git show 9de9c25f62:hermes_cli/plugins.py` in the Hermes repository) shows its `PluginContext` has no
`get_config` and no `state`. Both arrived in commit 6bf93c0e38 (2026-08-08), first released in **v0.20.1**.
Every tool handler and `/hermes64 new` read settings through `ctx.get_config`, so on 0.18.2 each call failed with an
`AttributeError` (registration itself succeeded, which matches "plugin installed, doctor READY, then needed a fix").

## Every host API the plugin touches

| Host API | Used by | Since | On an older host |
|---|---|---|---|
| `ctx.register_tool(name, toolset, schema, handler, check_fn, requires_env, description)` | `adventure_maker/wire.py` (all 27 tools) | 0.3.0 | **Required.** Missing: plain `HostCompatError` naming 0.18.2 |
| `ctx.register_command(name, handler, description, args_hint)` | `__init__.py` (`/hermes64`) | 0.4.0 | Skipped when missing; retried without `args_hint` if the host rejects that keyword |
| `ctx.register_skill(name, path, description)` | `__init__.py` (7 bundled skills) | 0.10.0 | Skipped when missing; `OSError`/`ValueError` per skill ignored. Listed in the agent's `<available_skills>` only from 0.21.6; before that `skill_view('hermes64:<name>')` by exact name only (0.18.2 source: "opt-in explicit loads only") |
| `ctx.register_hook('pre_llm_call', fn)`; `fn(**kwargs)` returns `{"context": str}` or None | `adventure_maker/native_hint.py` (NATIVE: one-line hint for plain game requests) | present in 0.18.2 (`agent/turn_context.py`, same return contract on 0.22.7) | Skipped when `register_hook` is missing; `TypeError`/`ValueError` ignored; the callback never raises. Hook context goes into that turn's user message and is never stored |
| `ctx.get_config(key, default)` | `plugin_settings.py`, `newgame.py`, `character_tools.py`, `cover_tools.py` (call time) | 0.20.1 | Compat: reads `plugins.entries.hermes64.settings` (legacy `.config`) via `hermes_cli.config.load_config_readonly`, else the default |
| `ctx.state.data_dir` | `plugin_settings.default_games_root` (default games/hub folder) | 0.20.1 | Absent (not invented): set **projects_root**; otherwise `/hermes64 new` says to choose one |
| `ctx.manifest.key` / `.name` | `host_compat` (plugin id for the settings fallback) | 0.18.x | Falls back to `hermes64` |
| `hermes_cli.__version__` (literal module attribute only) | `host_compat.host_version` | 0.18.x | Newer hosts serve it lazily from an install stamp; treated as unknown (no I/O at registration) |
| `hermes_cli.config.load_config_readonly()` | `dashboard/plugin_api.py` (Studio), compat settings fallback | present in 0.18.2 | Studio: `{}` (no projects root) |
| Handler call `handler(args, **kwargs)` returning a JSON string | every tool | 0.3.0 | Same in 0.18.2 (`tools/registry.py`) |
| Slash handler `fn(raw_args)` | `/hermes64` | 0.4.0 | Same |
| Dashboard plugin `dashboard/manifest.json` + `plugin_api.py` exposing a FastAPI `router` (optional; stdlib fallback) | Hermes64 Studio | 0.18.2 mounts plugin API routes | Not exercised on 0.18.2 (see NOT verified) |
| Manifest fields `name, version, description, author, license, provides_tools, provides_hooks, provides_middleware, capabilities, requires_env, python_dependencies, config_schema, requires_hermes` | `plugin.yaml` | all known to 0.22.x | 0.18.2 reads name/version/description/author/requires_env/provides_tools/provides_hooks and ignores the rest (settings UI from `config_schema` absent there) |

Not used: hooks other than `pre_llm_call`, middleware, `ctx.llm`, `ctx.dispatch_tool`, `inject_message`, `register_cli_command`, `plugins_state`
imports, any other `hermes_cli`/`tools`/`agent` import. Plugin-internal `tools.*` imports are package-relative when
loaded by Hermes (`hermes_plugins.hermes64.*`), so they never resolve to Hermes's own `tools` package.

## Behaviour by host

- **0.20.1 and newer:** `adapt()` returns the host ctx unchanged (identity; no behaviour change).
- **0.18.2 to 0.20.0:** compatibility mode, one log warning naming the missing APIs. Settings come from
  `config.yaml` (`plugins.entries.hermes64.settings.<key>`); there is no plugin data folder, so set `projects_root`.
- **Older than 0.18.2 (when the host reports a literal version):** refused at load with
  `Hermes64 needs Hermes Agent 0.18.2 or newer; this is <v>. Update Hermes (hermes update), then restart it.`
  Versions 0.10-0.18.1 may well work (the same APIs exist) but no source of theirs was read; the floor is what was
  checked, not a proof that older fails.
- **No `register_tool` at all:** refused with one sentence naming `ctx.register_tool`.

Tests: `tests/test_host_compat.py` (stub 0.18.2 context with the exact 0.18.2 `register_tool` signature; known-bad
control: the unadapted stub makes `/hermes64 new` report `get_config`; 27 tools + command + 7 skills register in
compat mode; eight tool handlers and `/hermes64 new` answer without `AttributeError`; settings/legacy-config fallback
through a stub `hermes_cli.config`; version floor; missing tool API; missing command/skill APIs; `args_hint` retry;
foreign `TypeError` not swallowed; `plugin.yaml` floor equals `MIN_HERMES`).

## Adopt the PC fix (slot)

> **SLOT, not filled.** Dylan's PC agent applied a local compatibility fix for Hermes 0.18.2. Its diff has not been
> received and is **not guessed here**. When Main passes it (`git diff > hermes64-local-compat.patch` on the PC, see
> the test sheet v2):
> 1. Save it as `docs/windows-pc-compat.patch` (untouched).
> 2. List each host API it touches. Any API not in the table above: add a row, add it to `REQUIRED` or `OPTIONAL` in
>    `adventure_maker/host_compat.py`, and add a stub test with a known-bad control.
> 3. If it changed plugin code paths this adapter already covers (likely `ctx.get_config`), prefer the adapter and
>    record why in this section; if it found something the adapter misses, adopt it and record that instead.
> 4. Re-run `tests/test_host_compat.py` and `tests/test_registration.py`.
