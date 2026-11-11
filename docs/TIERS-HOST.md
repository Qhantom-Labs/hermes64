# TIERS host investigation

Read-only on the host checkout `~/.hermes/hermes-agent`. Numbers come from the host's own tool-search code run on the
advertised Hermes64 schemas (`python3 -B -m tools.tiers_measure --host --work DIR`, raw output `docs/tiers/baseline.json`).
Tokens in this file are the host's estimate (compact JSON of the OpenAI tool definition, chars / 4).

## Answer

**No. None of these host versions lets a plugin keep some of its tools always visible and defer the rest.**

- **Newest host here (0.22.7) and every release from 0.19.1:** tool search is on by default. It defers **every**
  plugin tool, core or not, behind `tool_search` / `tool_describe` / `tool_call`. The model sees one listing line per
  tool. Hermes64 costs 641 tokens of listing (27 tools) in the default schema, or 265 with only the 11 CORE tools.
  Each call costs one bridge round: `tool_describe` once for the schemas, then `tool_call`.
- **Dylan's PC (0.18.2) and 0.16.0-0.19.0:** tool search runs on `auto`. It defers plugin and MCP tools only when
  together they use more than 10% of the context window. Hermes64 alone is 4,283 tokens, under every threshold
  (12,800 at 128K), so **all 27 tools are eager**. When MCP servers push the total over the line, every plugin tool
  defers behind a bare bridge with no listing (378 tokens): the agent must search to find any Hermes64 tool.
- **Before 0.16.0:** no tool search. All 27 tools are eager.

So "CORE always on, ADVANCED on request" needs a host change (below). What the plugin can do on every host today is
cheap: the skill names the exact CORE tools in order. That works whether the tools are eager (0.18.2) or behind the
bridge, where the listing tells the model "go straight to `tool_describe` when you see the exact name" (0.19.1+).
Nothing breaks on older hosts: the plugin registers the full set everywhere, exactly as today.

## Versions

| where | version | how known |
|---|---|---|
| this Mac (host here) | 0.22.7, commit b200f5bc60, tag `v0.22.7` (2026-11-03); install built 2026-11-05, tree dirty | `hermes_cli.main --version`, `install-stamp.json` |
| Dylan's PC | 0.18.2 = release tag `v2026.7.7.2` (2026-07-07) | `__version__` in `hermes_cli/__init__.py` at that tag |
| Dylan's MacBook | **unknown here**: no file this lane can read records it (Dylan says it differs). Any version falls in one row below | - |

## Behaviour by host version

| host release | tool search | Hermes64 tools in the default schema | default-schema tokens (27 tools / 11 CORE) | plugin skills in the prompt's `<available_skills>` |
|---|---|---|---|---|
| < 0.16.0 (before `v2026.6.5`) | absent | all eager | 4,283 / 1,409 | no: `skill_view('hermes64:<name>')` only |
| 0.16.0-0.19.0 (`v2026.6.5`-`v2026.7.20`), **incl. 0.18.2** | `auto`: defer plugin+MCP only above 10% of context; bridge has no listing | all eager unless plugin+MCP > 10% of context; then none, 378-token bridge | 4,283 / 1,409 (or 378) | no |
| 0.19.1-0.21.5 (`v2026.7.30`-`v2026.9.24`) | on by default: every plugin tool deferred; listing (name + first sentence, cut near 80 chars) in `tool_search` | none eager; listing lines | +641 / +265 on a 535-token bridge (measured with 0.22.7 code; this range not run) | no |
| 0.21.6-0.22.7 (`v0.21.6` 2026-10-08 onward), **host here** | same as above | none eager; listing lines | +641 / +265 on a 535-token bridge (measured) | yes, with the frontmatter description |

The bridge is on in a default 0.22.7 session anyway: the shipped `tools.tool_search.defer` list names cold built-ins
(`session_search`, `todo_list`, `process_manage`, ...), so Hermes64 adds only listing lines to it. The ORCH2 agent
runs on this host confirm it: they reached Hermes64 tools only through `tool_describe` / `tool_call`
(`wt-orch2/evidence/orch2/agent-summary.json`).

Measured controls (host here, 0.22.7):

- `tools.tool_search.defer: []`: still 27 of 27 Hermes64 tools deferred. The docs say `[]` keeps every tool eager;
  the code (`is_deferrable_tool_name`) still defers any tool whose toolset is not core or a GUI surface.
- `tools.tool_search.enabled: off`: all 27 eager (4,283 tokens). This is a user-wide switch that also un-defers every
  MCP server, so it is not a per-plugin answer.
- 0.18.2 code with `enabled: on`: all 27 deferred, bridge 378 tokens, no listing.

## How the host exposes plugin tools (0.22.7; the same calls exist at 0.18.2)

- `ctx.register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False,
  description='', emoji='', override=False)`. There is no defer/eager argument; the registry has none either. Hermes64
  registers all 27 under one toolset, `hermes64` (`adventure_maker/wire.py`).
- Toolsets: plugin toolsets are on by default on every platform unless the user's saved platform list leaves them out
  (`known_plugin_toolsets`). The default-off list (`_DEFAULT_OFF_TOOLSETS`) is fixed in the host; a plugin cannot
  add itself to it. `hermes tools enable|disable hermes64` switches all 27 at once, per platform.
- Deferral (`tools/tool_search.py`): a tool never defers if it is in `toolsets._HERMES_CORE_TOOLS` (a static host
  list) or in a GUI session toolset; any other non-MCP, non-core tool is deferrable. That rule is the reason there is
  no per-plugin control.
- Skills: `ctx.register_skill(name, path, description='', frontmatter=None)` makes `hermes64:<name>` loadable with
  `skill_view`. Hermes64 guards the call (`getattr` + `try`), so a host without it keeps the tools. Only 0.21.6+
  lists plugin skills in the prompt; on 0.18.2 an agent finds `hermes64:hermes64-create` only if a tool description,
  the user (`-s`, `/skill`) or a command help names it. On 0.19.1-0.21.5 the listing shows only about the first 80
  characters of each description, so a skill pointer later in the text is cut off until `tool_describe`.
- `hermes plugins` verbs (0.22.7): `install`, `search`, `browse`, `validate`, `update`, `adopt`, `trust`, `check`,
  `remove`, `list`, `enable`, `disable`, `capabilities`, `doctor`, `pack`, `show`. `enable`/`disable` switch the whole
  plugin (tools, skills, commands). None of them controls deferral per tool.

## Long tool calls (host here; seen in the agent runs)

The host gives every tool call a 420-second deadline (`agent/tool_executor.py`: `timeouts.tools.sequential_call`,
falling back to `timeouts.tools.concurrent_batch`, default 420 s, env `HERMES_CONCURRENT_TOOL_TIMEOUT_S`). A
terminal `timeout` of 600 does not raise it. When it fires, the agent gets `timed out after 420.0s` while the command
keeps running as an orphan. A `create_flow run` on this loaded machine took longer than that in 6 of the 36 agent
runs (the timed-race prompt in all four A and B1 runs; two B2-sol runs at the heaviest load); in 5 of them the agent
then started a second run, which met the first run's project lock (`Project busy: operation.lock exists`). Starting
the run with the terminal's `background: true` and waiting for it avoids both (two Opus agents switched to it).

## The host change that would allow CORE eager + ADVANCED deferred (not made: host is read-only here)

Smallest form, in `tools/tool_search.py::is_deferrable_tool_name` plus one registry field:

1. `registry.register(..., defer=None)` stores `entry.defer` (`True`, `False` or `None`). `PluginContext.register_tool`
   passes it through.
2. In `is_deferrable_tool_name`, after the bridge-name check: `if entry.defer is False and name not in defer_tools:
   return False`. A user's explicit `tools.tool_search.defer` list still wins.
3. Hermes64 would then call `register_tool(..., defer=False)` for the 11 CORE tools, guarded by
   `inspect.signature(ctx.register_tool)` so older hosts keep today's full registration.

Expected default schema with that change (host here): 1,409 tokens of eager CORE schemas plus listing lines for the
16 ADVANCED tools (641 - 265 = 376 tokens) on the bridge that is on anyway. The plugin side is about 10 lines and
waits on the host. Task 5 (gated registration) stops here.

## What an older host does with today's plugin

| host | registers | what the agent sees | breaks? |
|---|---|---|---|
| < 0.16.0 | 27 tools, the bundled skills (guarded; 9 with the stack A owner hunks), `/hermes64` | 27 eager schemas, no skill index | no |
| 0.18.2 | same | 27 eager schemas, skills only by explicit load | no |
| 0.19.1-0.21.5 | same | bridge + listing, skills only by explicit load | no |
| 0.21.6+ | same | bridge + listing, skills listed | no |
