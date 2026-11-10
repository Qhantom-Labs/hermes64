# Token diet: tool schemas sent on every request

The 24 Hermes64 tools used to cost **14,607 tokens** of schema and description per request. They now cost **4,828** (budget 6,000). Tool names, count, handlers and validation are unchanged.

**MERGE3 update:** `hermes64_cover` (cover-lane) joined as the 25th tool. Registered as committed on cover-lane it cost 7,103 chars / **1,776 tokens** alone (total 26,415 chars / **6,604 tokens**, over budget; its description was 758 characters, over the 400 limit). It now goes through `wire.py` like the others: **440 tokens** (1,758 chars, longest description 226), total **5,268 tokens** for 25 tools (21,070 chars), inside the unchanged 6,000 budget. See [the MERGE3 section](#merge3-hermes64_cover-joins-25-tools).

## Method

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.schema_budget          # table
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.schema_budget --json   # machine-readable
```

The plugin is registered into a recording context. For each tool the meter takes `json.dumps(dict(name=name, **register_kwargs))` without the two callables (`handler`, `check_fn`) and counts characters / 4. Because the whole registration call is measured, each description counts twice (`description=` and `schema.description`); this follows the assignment's method and slightly overstates the wire cost if the host sends one copy. Exit status is 1 above budget. The "before" numbers come from the same meter run on the unmodified tree.

## Before and after, per tool

"Before" is commit `58d495c`; "after" is this lane. The last column is the longest description string anywhere in the registration (tool or parameter).

| Tool | Before chars | Before tokens | After chars | After tokens | Longest description before → after |
|---|---:|---:|---:|---:|---:|
| `hermes64_module_edit` | 11,435 | 2,859 | 1,252 | 313 | 197 → 269 |
| `hermes64_module_benchmark` | 11,432 | 2,858 | 1,236 | 309 | 160 → 269 |
| `hermes64_module_add` | 11,351 | 2,838 | 1,114 | 278 | 156 → 269 |
| `hermes64_audio` | 5,390 | 1,348 | 1,868 | 467 | 306 → 206 |
| `hermes64_edit` | 2,801 | 700 | 1,122 | 280 | 197 → 222 |
| `hermes64_pack_from_refs` | 1,492 | 373 | 914 | 228 | 332 → 125 |
| `hermes64_benchmark` | 1,179 | 295 | 799 | 200 | 286 → 117 |
| `hermes64_module_check` | 1,173 | 293 | 796 | 199 | 179 → 115 |
| `hermes64_open` | 1,021 | 255 | 676 | 169 | 283 → 127 |
| `hermes64_export` | 960 | 240 | 745 | 186 | 151 → 113 |
| `hermes64_playtest` | 926 | 232 | 875 | 219 | 147 → 138 |
| `hermes64_scaffold` | 913 | 228 | 761 | 190 | 160 → 121 |
| `hermes64_build_assets` | 824 | 206 | 595 | 149 | 194 → 96 |
| `hermes64_doctor` | 770 | 192 | 529 | 132 | 210 → 106 |
| `hermes64_demo` | 730 | 182 | 1,066 | 266 | 131 → 218 |
| `hermes64_pack_select` | 716 | 179 | 566 | 142 | 127 → 85 |
| `hermes64_pack_validate` | 696 | 174 | 570 | 142 | 115 → 85 |
| `hermes64_compile` | 684 | 171 | 571 | 143 | 126 → 103 |
| `hermes64_pack_create` | 684 | 171 | 535 | 134 | 120 → 81 |
| `hermes64_check` | 680 | 170 | 645 | 161 | 132 → 131 |
| `hermes64_replay` | 662 | 166 | 485 | 121 | 156 → 84 |
| `hermes64_packs` | 658 | 164 | 544 | 136 | 89 → 65 |
| `hermes64_modules` | 651 | 163 | 522 | 130 | 130 → 82 |
| `hermes64_kits` | 599 | 150 | 526 | 132 | 104 → 84 |
| **Total (24 tools)** | **58,427** | **14,607** | **19,312** | **4,828** | |

`hermes64_demo` grew because it now advertises the one-command start (`premise`, `style`). Registering the four bundled skills adds four short lines to the system prompt's skill index (364 characters, about 91 tokens by the same chars/4 rule, if formatted as `    - hermes64:<name>: <description>`), so the net saving is about 9,690 tokens per request.

## What changed

- **Advertised copy vs. validation copy.** `adventure_maker/wire.py` builds the schema shown to the model from each tool's full schema: names, types, enums (values kept), integer bounds, ID patterns, required fields and top-level `additionalProperties: false` stay; nested shapes, string length limits and prose go. Every registration path (`adventure_maker/tools.py`, `adventure_modules/tools.py`, `audio_tools.py`, `demo.py`) uses it.
- **Descriptions** are one or two sentences (`wire.SHORT`). Safety facts that change a model's choice stay in the sentence ("No downloads", "Cannot judge fun", "never hand-edit generated files").
- **Nested unions** (story edit operations, typed module operations, audio `music`/`voice`/`transform`) became an object with its `kind` enum where useful, plus a one-line pointer to the skill that holds the full shape.
- **Bundled skills are now registered** with `ctx.register_skill` when the host supports it, so `hermes64:hermes64`, `hermes64:hermes64-audio`, `hermes64:hermes64-gameplay-modules` and `hermes64:hermes64-playtest-and-ship` load on demand. Before this, the plugin shipped them but never registered them.

## What did not change

- Validation. Handlers still validate against the full schemas in `adventure_maker/schemas.py`, `adventure_modules/schemas.py`, `adventure_maker/audio_schemas.py` and `demo.SHIP_SCHEMAS`. `tests/test_schema_budget.py` pins their sha256 (`fdfd81ea…101c`, measured before the diet) and checks that calls the compact copy allows but the full copy forbids still fail with the original messages (`must match exactly one operation schema`, `unknown or malformed typed value`, `value outside enum`, `missing required or unknown arguments`).
- The frozen gameplay contract `contracts/gameplay/1.0.0/tools.json` (still equal to `adventure_modules.schemas.SCHEMAS`).
- Tool names and count (24 at the diet; 25 since MERGE3 added `hermes64_cover`), handlers, outputs and error codes.

## Where the detail went

| Removed from the wire | Now in |
|---|---|
| Story edit operation shapes (`move-entrance`, `change-role`, `add-ending`, `json-patch`), benchmark operations, scaffold arguments, ID rules | `skills/hermes64/SKILL.md` → "Tool argument shapes" |
| Typed module operation shapes, hash rules for module tools | `skills/hermes64-gameplay-modules/SKILL.md` → "Operation shapes"; full JSON in `contracts/gameplay/1.0.0/tools.json` |
| Audio per-action arguments, music/voice/transform fields | `skills/hermes64-audio/SKILL.md` (already listed every action) and `adventure_maker/audio_schemas.py` |
| Long honesty caveats in descriptions (rendered vs headless, catalog, human approval) | `skills/hermes64-playtest-and-ship/SKILL.md`, `docs/PLAYTEST.md`, `docs/EXPORT.md`, README |
| `hermes64_export.module_preview` long note | `docs/EXPORT.md`, `docs/MODULES-RUNTIME.md` |

## Near-duplicates (listed, none merged)

Merging would change tool names, the frozen contract and the 24-tool registration tests, so nothing was merged or hidden:

- `hermes64_module_add` is `hermes64_module_edit` restricted to `add-enemy`/`add-ability` (same schema, same handler path). Its wire copy advertises only those two kinds, which is exactly what its handler accepts.
- `hermes64_pack_select` and `hermes64_pack_validate` take identical arguments but do different things (adopt vs. read-only check).
- `hermes64_kits(action="style")` returns the same pack data as `hermes64_packs(action="inspect")`.
- `hermes64_replay` (story-witness replay with save round trip) and `hermes64_playtest` (bounded physical bots) both run Godot bots but answer different questions.
- `hermes64_benchmark` and `hermes64_module_benchmark` cover the two edit families (story 1.0/1.1 vs. STORY 1.2 modules).

Candidates for a future major version: fold `module_add` into `module_edit`, and `kits(style)` into `packs(inspect)`.

## MERGE3: hermes64_cover joins (25 tools)

Same meter (`python3 -B -m tools.schema_budget`), run on the merged tree before and after routing the cover tool through `wire.register`:

| Tool | As merged (chars / tokens / longest description) | Compact (chars / tokens / longest description) |
|---|---:|---:|
| `hermes64_cover` | 7,103 / 1,776 / 758 | 1,758 / 440 / 226 |
| **Total (25 tools)** | **26,415 / 6,604** (over the 6,000 budget) | **21,070 / 5,268** |

- The description is two sentences (`wire.SHORT['hermes64_cover']`): what the four actions do, and that `adopt=true` is only for the user's explicit choice; it keeps "Local Godot; writes only inside the project".
- `edits` is advertised as an array of objects with the `op` enum (`wire.COVER_OPS`, the 12 typed edit ops; a test keeps it equal to the full schema's enum) and a pointer to `skill hermes64:hermes64-cover`, which already documents the targets (`hero:<i>`, `prop:<i>`, `cast:<id>`), sizes and the adopt rule. Every other cover parameter keeps its type, enum, bounds and ID pattern through the normal `slim` projection.
- Validation is unchanged: `CoverService.handle` still validates the full `COVER_SCHEMA`. The cover tool's validation parameters are pinned separately (`COVER_VALIDATION_SHA256 = 7b2da889…c837`, the value on cover-lane `2c8403b`), so the 24-tool pin above is untouched. A call the compact copy allows but the full schema forbids (`{"op":"lighting","mood":"noon"}`) still fails with `value outside enum`.
- The cover skill (`skills/hermes64-cover/SKILL.md`) is now registered on load like the other four (five bundled skills). Its index line (`    - hermes64:hermes64-cover: <description>`, 86 characters) adds about 22 tokens by the same chars/4 rule.
- The budget was not raised; no description was tightened on the other 24 tools.

## Hub lane: `hermes64_hub` (measured on hub-lane, 25 tools there)

The hub lane added one compact tool, `hermes64_hub` (search, info, install, pack, publish for the local community
registry), instead of six. Measured with the same meter: 1,357 chars, **339 tokens**; the 25-tool total is **20,669
chars / 5,167 tokens**, still under the 6,000 budget. Its validation schema lives in `adventure_maker/hub.py`
(`HUB_SCHEMA`) and has its own sha256 pin in `tests/test_schema_budget.py`, so the 24-tool pin above is unchanged. The
argument detail is in `skills/hermes64/SKILL.md` ("Hub") and `docs/HUB.md`; `/hermes64 hub ...` reaches the same
handlers without any schema cost.

## AUDIT lane: style audit and repair parameters (no new tool)

The style audit and the auto-repair loop extend existing tools instead of adding a 26th: `hermes64_check` gains
`action` (`proof`|`audit`) and `views` (0-2); `hermes64_compile` gains `patch_json`. Same meter:

| Tool | Before (chars / tokens) | After (chars / tokens) |
|---|---:|---:|
| `hermes64_check` | 645 / 161 | 805 / 201 |
| `hermes64_compile` | 571 / 143 | 609 / 152 |
| **Total (25 tools)** | **21,070 / 5,268** | **21,268 / 5,317** |

+49 tokens. The validation pin `VALIDATION_SHA256` changed deliberately (three additive optional fields only) and
the test records the old value. For MERGE4 (27 tools), the delta to carry is exactly these two `SHORT` strings and
the three schema fields in `adventure_maker/schemas.py`; no registration lines change.

## Guard

`tests/test_schema_budget.py` fails if the total exceeds `TOKEN_BUDGET = 6000` tokens, if any description string exceeds `DESCRIPTION_LIMIT = 400` characters (both in `tools/schema_budget.py`), if a validation schema changes, if the compact copy drops a property, enum value, bound or required field, or if a registered skill's description drifts from its `SKILL.md`.

## MERGE4: 27 tools (`hermes64_character` and `hermes64_hub` joined)

Measured with `python3 -B -m tools.schema_budget` on the merged tree (characters / 4 per registration, the same
method as above):

| State | Tools | Tokens |
|---|---:|---:|
| After the charsys + hub merges, `hermes64_character` advertising its full schema | 27 | 6,380 |
| `hermes64_character` through `wire.register` (compact copy: edits show only `kind`) | 27 | 6,037 |
| Tightened descriptions of the two new tools (`hermes64_character` 197 chars, `hermes64_hub` 213 chars) | 27 | **5,990** |

The budget stays 6,000 tokens; nothing was raised. `hermes64_character` advertises 393 tokens (was 773); its full
schema is unchanged and pinned (`CHARACTER_VALIDATION_SHA256` in `tests/test_schema_budget.py`) and still validates
every call, so a bad edit field (for example `age: "baby"`) is refused by the handler. The moved detail lives in the
skills `hermes64-characters` and `hermes64-hub`, both now registered and loaded on demand (7 bundled skills).

### MERGE4 headroom for the parallel lanes (5,990 -> 5,938)

Five lanes (puzzle, dungeonkit, audit, combat, city) are adding actions to existing tools, and 5,990 left them 10
tokens. Two advertised-copy edits, validation untouched (all four sha256 pins pass, `test_schema_budget` +
`test_registration` 12 OK):

| Edit | Tool(s) | Tokens |
|---|---|---:|
| Module operation copy lists only the kinds the tool's enum accepts, as `kind{fields}`, without the `One of:` the enum already says. `hermes64_module_add` listed all six kinds while accepting two (`add-enemy`, `add-ability`): misleading as well as long | `hermes64_module_add` 278 -> 242, `hermes64_module_edit` 313 -> 311, `hermes64_module_benchmark` 309 -> 307 | -40 |
| Story edit operation in the same `kind{fields}` form: `move-entrance{room,door,wall,position} \| change-role{character,role} \| add-ending{ending_json} \| json-patch{patch_json}` (same kinds, same fields, same skill pointer) | `hermes64_edit` 280 -> 268 | -12 |
| **Total (27 tools)** | 23,752 chars | **5,938** |

Headroom now 62 tokens. Nothing else was cut: the long tool descriptions (cover, demo, hub, audio, character) were
already tightened by their lanes and further trims would cost meaning for a few tokens each. A lane that needs more
should route argument detail into its skill, the way the existing tools do, rather than raise the budget.

## MERGE5: puzzle + audit merged, headroom for the recipes and converter lanes (6,090 -> 5,868)

Measured with `python3 -B -m tools.schema_budget` on the merged tree (the same meter). The puzzle lane added four
STORY 1.3 kinds to the three module tools and the audit lane three optional fields (`check.action`, `check.views`,
`compile.patch_json`), which put the 27 tools at **6,090** tokens, over the 6,000 budget. The budget was not raised;
validation is unchanged (`VALIDATION_SHA256 = e6989609…ae5b`, recomputed at the audit merge for both lanes' additive
changes, plus the cover, hub and character pins all pass; `contracts/gameplay/1.0.0/tools.json` re-exported
byte-identical with `python3 -B -m adventure_modules.export_contracts`).

| Edit (advertised copy only) | Tokens after |
|---|---:|
| After the four merges | 6,090 |
| `hermes64_module_benchmark` items point at `hermes64_module_edit` ("One hermes64_module_edit operation.") instead of repeating the kind list, as `hermes64_benchmark` points at `hermes64_edit`; enum and required `kind` kept | 6,003 |
| Honest scope after the puzzle merge: `hermes64_module_add` "an enemy, ability or puzzle switch to a STORY 1.2/1.3 game", `hermes64_module_check` "STORY 1.2/1.3" (+4 tokens); trims: demo "(optional style)", cover "Box-art covers ... 3 variants ... apply typed edits", hub "Local Hermes64 Hub registry" | 5,999 |
| Module operation field lists (MERGE4's `kind{fields}`) moved to `skill hermes64:hermes64-gameplay-modules`, which already carried the full shapes the field names only pointed at; the four STORY 1.3 puzzle shapes were added there (they were only in `docs/PUZZLES.md`). Copy: "Fields per kind: skill hermes64:hermes64-gameplay-modules; plus expected_changed_rooms." | 5,908 |
| Story edit field list moved the same way to `skill hermes64:hermes64` (its "Tool argument shapes" section has every shape); trims: check "the calls that fix and retry", playtest, open, cover "export.", demo `style` | **5,868** |

Headroom **132 tokens** (the request was about 150 for the recipes and converter lanes). The kinds stay visible in
every enum; what moved is the field names, and every one of those operations needs its skill for the nested shapes
anyway. Not cut, and why: the audio tool's three nested field lists (`music`, `voice`, `transform`, about 59 tokens)
belong to the audio lane's copy and its skill does not list the `transform` fields; the remaining tool sentences
carry safety or honesty claims ("Never uploads", "Read-only", "Windows execution unverified on Mac", "Always check
after editing"). A lane that needs more than 132 should route its own argument detail into its skill.
