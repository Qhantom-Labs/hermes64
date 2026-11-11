# DETAIL shared hunks

Files this lane edits that other lanes own or also edit. INTEG6 merges stack A; detail-lane sits on orch2-lane, so
these hunks land after orch2. Everything else in this lane is a new file (listed at the end).

| file | owner / other lanes | change | size |
|---|---|---|---|
| `adventure_maker/create_flow.py` | orch, orch2 | brief file split (`load_brief_file`: the brief's `story` block -> `create/story.json`), long-prompt fallback cut at a sentence; `Slots` honours `extra_clear_m`; `stage_rooms` lays out the story before dressing, routes story fights/courses, applies the story, collects `not_applied`; report `story` + `not_applied` + md sections; `plan` story section; `vocab` story fields/template/mechanics; SPEC: brief writes `create/story.json`, rooms reads it; `STAGE_CODE_VERSION` 3 -> 4; `bundle_import` loads `tools.*` by path; `/hermes64 new --create` reply line | about 200 added lines in 12 hunks |
| `adventure_maker/gen_screen.py` | agen | `from tools import style_bible` -> `bundle_tool('style_bible')` (loaded by path) | +13 / -1 |
| `adventure_maker/gen_tools.py` | agen | same import, from `gen_screen.SB` | 1 line |
| `skills/hermes64-create/SKILL.md` | orch, orch2 | 1.1.0 -> 1.2.0: one brief with a story block, plan before run, tell the human once, not-applied in the reply | rewritten (same length class) |

Why the `tools` import change: inside a Hermes process the module name `tools` is Hermes's own package
(`hermes-agent/tools/__init__.py`), so `hermes64_build_assets`, `hermes64_playtest` and `hermes64_replay` failed with
`cannot import name 'style_bible' from 'tools'` when an agent hand-authored a story layer (DETAIL before-runs
lighthouse-ghost and magic-school; ORCH2's Opus lighthouse run reported the same "code clash"). The same clash would
hit `/hermes64 new --create` in-process (`bundle_import('tools.mood_pack')`). Test:
`tests/test_create_detail.ToolsNameClash`.

New files (no conflict expected): `adventure_maker/create_story.py`, `adventure_maker/create_story.json`,
`tests/test_create_detail.py`, `tools/detail_proof.py`, `tools/detail_score.py`, `docs/detail/*`, `docs/DETAIL-*.md`.
The two adventure_maker files ship through the existing `adventure_maker/*` package rule (no package hunk).
