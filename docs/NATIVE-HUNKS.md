# NATIVE hunks (for FINALINT3 / rc6)

Branch `native-lane`, base mergeprep-lane rc5 `f8218ecc` (+ docs-only `8a9c60f9`). Commits: `8517d9bc` (P2 reach),
`1a49623c` (P3+P4 chat text, first run, docs), then the P5 docs commit. Every shared-file hunk is listed below. New files
merge without conflict.

## New files (no conflicts expected)

| file | what |
|---|---|
| `adventure_maker/native_hint.py` | `pre_llm_call` hook: one ephemeral line for plain game requests when `hermes64-create` is not loaded yet; `register(ctx)` skips hosts without `register_hook` |
| `adventure_maker/chat_text.py` | `tidy()` (escape codes, tabs, deep indentation out of slash replies) and `hazards()` (renderer-hostile patterns) |
| `tests/test_native_hint.py`, `tests/test_native_text.py` | 10 + 7 tests, known-bad controls included |
| `tools/native_proof.py` | no-preload agent driver and scorer (verify kit case setup imported read-only; `--oldhost-index`, `--no-hook`) |
| `docs/NATIVE-MODEL.md`, `docs/NATIVE-RESULT.md`, `docs/NATIVE-HUNKS.md`, `docs/native/runs.json` | lane docs; runs.json has home paths as `~` |

## Shared-file hunks

| file | hunk | merge note |
|---|---|---|
| `__init__.py` | import line: `from .adventure_maker import host_compat, native_hint` | keep |
| `__init__.py` | `SKILLS['hermes64-create']` = `'Use for any request to make, edit, play or export a game.'` | must equal the SKILL.md frontmatter (test_schema_budget, test_tiers) |
| `__init__.py` | last two lines of `register()`: comment + `native_hint.register(ctx)` | keep after the skill loop; `tools/native_proof.py --oldhost-index` expects exactly one `add_skill(` call and `--no-hook` exactly one `native_hint.register(ctx)` |
| `plugin.yaml` | `"provides_hooks": ["pre_llm_call"]` | host `plugins validate` flags undeclared hooks |
| `adventure_maker/wire.py` | `SHORT['hermes64_demo']`: new text (trigger first) + one comment line | schema budget: 201 characters, was 204; any lane re-touching demo must keep the first sentence at most 80 characters (listing line) |
| `skills/hermes64-create/SKILL.md` | frontmatter `description` (same text as SKILLS) | body unchanged |
| `skills/hermes64/SKILL.md` | one new first bullet under `## When to use` | |
| `tests/test_tiers.py` | `DESCRIPTION` constant; help test: `assertNotIn('\n', text)` replaced by `hazards(text) == []` | help is now multi-line on purpose |
| `adventure_maker/tools.py` | `help_command` body (7 short lines; keeps the phrases test_bfix/test_bfix_host pin: `/hermes64 setup prints a checklist`, `it is never executed`, the unknown-word prefix) | |
| `adventure_maker/tools.py` | `make_command.command`: `console_text(tidy(...))` + import | all slash replies pass through `tidy` |
| `adventure_maker/setup_check.py` | `SYMBOL` without padding (+ comment); `render()` rows `- [status] item: detail`, continuation `  needed for ... Next step: ...` | `'[ok]' in row` and `Next step: ` checks still hold |
| `adventure_maker/create_flow.py` | new `default_games_folder()` before `settings_from_args`; `settings_from_args` falls back to it; docstring | |
| `adventure_maker/create_flow.py` | `run()`: mkdir of the default folder only, then the `create_root` message/next step reworded | no test pinned the old wording |
| `README.md` | "What you get" first bullet; Quickstart paragraph (agent first, checkup second) | readme_claims gate: no new `Hermes X.Y.Z`/`Godot X.Y.Z`/`N tools` claims added |
| `docs/QUICKSTART.md` | "First game": new lead paragraph; step 1 mentions `/hermes64 setup` | |
| `docs/HOST-COMPAT.md` | `register_skill` row extended (index from 0.21.6); new `register_hook('pre_llm_call')` row; "Not used" line | |
| `docs/TOKEN-DIET.md` | NATIVE paragraph and new total (23,993 characters, 5,998 tokens) | |

## Checks to repeat after the merge

- `tests.test_native_hint tests.test_native_text tests.test_tiers tests.test_bfix tests.test_schema_budget
  tests.test_host_compat`. Lane result: 255 focused tests across 20 touched modules, exit 0, 0 failures
  (`evidence/mergeprep/native-p5/summary.json`, local only, gitignored).
- Schema: 27 tools, 5,998 of 6,000 tokens. Legacy replays: 15/15 identical to the rc3-m15 rows on the lane.
- Verify kit (scratch copy, package at `1a49623c`): INCOMPLETE, 22 PASS / 0 FAIL / 1 SKIP (`measured_style_audit`, the
  same as rc5).
- Grep: one `add_skill(` and one `native_hint.register(ctx)` in `__init__.py`.
