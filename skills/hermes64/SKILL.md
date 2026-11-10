---
name: hermes64
description: Make and safely edit retro-style 3D adventure games.
version: 0.1.0
author: Dylan (Qhantom), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [games, authoring, local]
    related_skills: []
---

# Hermes64 authoring

Create any N64-era-style 3D adventure within the story contract. Themes are data packs, not hard-coded game modes. `polar_pod` is the demo pack for Thaw; it is not the product. A premise creates an explicit two-room starter, not an automatically finished game.

## When to use
- Scaffold an original adventure, author story logic, change entrances/roles/endings, or compare edit regressions.
- Create/select a new visual theme using pack data and the same core.
- Do not use this as an arbitrary command runner or to install engines.

## Prerequisites
An owner chooses the existing `projects_root` (blank: `new` uses the profile's default games folder) and the trusted assembled `bundle_root` in Hermes64 settings. The project argument is a single slug, never a filesystem path. Python and Godot must already exist; Blender is needed only for Blender asset builds and new character bodies. This release requires the macOS subprocess sandbox and fails closed elsewhere. Do not disable the sandbox on error.

## Quick start
`/hermes64 new "<one-sentence premise>" [village|forest|polar]` (or `hermes64_demo` with `premise` and optional `style`/`project`) checks Python and Godot, picks a bundled style from premise words when none is given, builds the two-room starter through scaffold/compile/check, builds its room assets (`hermes64_build_assets`, seed 7), runs a short headless bot playtest and writes `project.json` with a proof badge such as `proof-checked · 2 bots played · assets built · style audit WARN 70/100 · 0 softlocks · PLAYABLE (headless)` plus the exact Godot command to play. With a window available it also runs the style audit after the playtest; without one the badge says `style audit not run (no display)`. With no usable builder (default Blender not found) the badge says `assets NOT BUILT (...)`, the game is not ok and `next` starts with `hermes64_build_assets`. With no `projects_root` set, games go to the profile's default games folder. Refusals are one line with the next step. Report the badge as written: it never upgrades a tier, and a failing audit keeps it not ok. The badge in `project.json` is a snapshot from creation and is not updated later.

## Tool argument shapes
The advertised schemas are compact; handlers validate the full shapes:
- `hermes64_edit.operation`: `{kind:"move-entrance", room, door, wall: north|south|east|west, position: 0-10000}`, `{kind:"change-role", character, role}`, `{kind:"add-ending", ending_json}` or `{kind:"json-patch", patch_json}` (RFC 6902 string), each with optional `expected_changed_rooms` (≤100 room IDs). Optional `save_path` and `expected_spec_hash` (64 hex).
- `hermes64_benchmark.operations_json`: a JSON array string of 1-20 such operations; `build_assets` is required, `style_gate` optional.
- `hermes64_scaffold`: `project`, `pack`, and exactly one of `premise` (≤6000 chars) or `spec_json`.
- `hermes64_check`: `action` `proof` (default) or `audit` (render + score the style, docs/STYLE-AUDIT.md); `views` 0-2 extra authored cameras per room (audit only).
- `hermes64_compile.patch_json`: an RFC 6902 array string applied to `spec_path` before compiling; copy it from a `next` step. The source file is not rewritten.
- IDs (`project`, `pack`, room/door IDs) are lowercase slugs `[a-z][a-z0-9_-]*` up to 64 characters; paths are project-relative, never absolute.

## Hub (share and reuse)
`hermes64_hub` (or `/hermes64 hub ...`) works on a local, file-based registry; the bundled one is `hub/` (browse offline: `hub/site/index.html`).
- `action:"search"` with optional `query` and `kind` (style, kit, character, sound, cover, game). `action:"info"` with `id`.
- `action:"install"` with `id` and `project` (games need no project; they install as a new game named after the entry, or `project`). Install verifies the archive sha256, runs the data-only validator, checks the plugin contract and the game's locked style (its pack's kit family), never overwrites, writes `assets/hub/<id>/` and records the install in the game's `catalog.json`. A style pack also lands in `packs/<id>/`; adopt it with `hermes64_pack_select`. Game installs compile and check; report the proof as returned.
- `action:"pack"` with `id` = a hub entry, a catalog id (`kit:furn.lamp`, `kit:furn.lamp/polar_pod`, `character:polar_pod/tavi`, `sound:ui.select`) or one of your games; optional `version`, `author` (a name, never an email) and `licence` (SPDX: CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0, MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC). `action:"publish"` with `id` turns the packed entry into a local pull-request draft (entry.json, archive, README, PR.md). Nothing is uploaded or pushed.
- Refusals are one line with the next step; relay them as written. Tiers (`validated`, `data-only`, `machine-checked`...) are honest labels, never upgrades.

## Procedure
1. Use `hermes64_packs` to list/inspect packs and `hermes64_kits` to inspect actual available assets. Do not infer assets exist from a preset. Read the assembled `docs/story/SPEC.md` and `GAME.md` with `read_file` before constructing a spec. Preserve the contract version and stable IDs.
2. Call `hermes64_scaffold` with `project`, `pack`, and exactly one of `premise` or `spec_json`. Source is `source/spec.json`; the pack is snapshotted inside the project. Scaffold status is intentionally unvalidated. For a supplied spec, preserve the author's text rather than rewriting it without approval.
3. Use `hermes64_compile` with the source-relative path, then `hermes64_check`. Require `proved`; `inconclusive`, invalid JSON, missing components and nonzero exits are not passes. Read full reports using `read_file` when an output is bounded. Witnesses prove abstract story transitions, not physical walkability.
4. Use `hermes64_edit` for every source edit. Named operations: `move-entrance`, `change-role`, `add-ending`. The generic `json-patch` operation supports RFC 6902 `add`, `remove`, `replace`, `test` with ordinary JSON Pointers (numeric array indices). Put `test` guards before index-sensitive edits. Pass the expected current spec hash when available. Version/game IDs, removed identity records, body and rig changes are rejected.
5. Supply `expected_changed_rooms` and a real pre-edit `save_path` where available. Read the returned diff and regression report. Always call `hermes64_check` after every edit, even though accepted edits already run a checker. Never hand-edit generated `.maker/runs/` files or `game.json`. The current revision pointer is the authoritative source after an edit; recompiling the original starter would discard that edit.
6. Use `hermes64_pack_create` with serialized validated pack data, then `hermes64_pack_select`. Pack IDs are immutable: create a new ID to revise data. Selection on an already compiled game recompiles/checks a candidate. Run `hermes64_pack_validate`; `data_valid` does not mean rendered style, audio, or assets passed.
7. Call `hermes64_build_assets`, then `hermes64_replay`. They invoke reviewed local Blender/Godot adapters, not arbitrary scripts. Failures or missing integration seams must be reported honestly; do not substitute fixture outputs. The runtime is a Godot runtime layer, not our engine.
8. `hermes64_benchmark` takes 1–20 serialized edit operations with exact expected room locality for every operation. It leaves the live source/game revision pointer unchanged. Report validity, identity, unchanged-room bytes, solvability, migration, measured asset validation and real Godot replay separately. Supply a real save: missing save/style/replay evidence cannot pass. Successful migrated saves are loaded by Godot as well as checked by Python.
9. New characters: `hermes64_character` (skill hermes64:hermes64-characters). Propose three variants from a one-sentence brief, let the user pick from the contact sheets, apply typed edits, then build and bind. Recipes name palette roles, so the project's style lock recolours them; every character passes the rig kit validator before it is shown.
10. Only call `hermes64_open` on explicit request to open a local GUI. It is a bounded foreground preview and does not prove playability. `screenshots:true` captures every room through the windowed renderer and reports missing assets, conservative room triangles and placeholder characters. Headless dummy rendering is not screenshot evidence.

10. Auto-repair: a failing check, compile, playtest or audit returns `next`, an ordered list of exact tool calls. Run them in order, then read the newest result's `next` and repeat until it is empty; items in `manual` have no safe automatic fix and need a decision (docs/AUTOREPAIR.md). `hermes64_check(action="audit")` measures rendered rooms against the pack's style lock; it is not human art approval.

## Templates, story files and prompt briefs

- Default new games retain the two-room collect structure, with room/hero/item/ending display text drawn from the sentence. The fox, penguin and lighthouse examples do not acquire combat just because they mention rescue or time.
- `arena_run_v1` uses pack-authored compiled rooms, reversible door chains, checkpointed arena challenges and wave groups of at most three enemies. Use `/hermes64 new "Keep Under Siege: defend the castle"` for the bundled neutral story, or a clear arena prompt with explicit `castle_keep`. A missing room pack is a refusal, never an undressed grid fallback.
- Story files are data in `<games folder>/premises/<id>/premise.json` or the installed `premises/` directory. Exact title-before-colon matching and `--story <id>` are supported. Show the returned `Story:` line and file hash; never imply that a bare sentence invented prepared rosters or scenes. See `docs/PREMISE-FILES.md` and `contracts/premise/1.0.0.json`.
- Every creation writes a keyword-fallback `brief.json` when the prompt can be parsed. For unmatched genres, a small data table chooses the closest shipped pack. For example, the wizard-purple-world prompt uses `castle_keep` and explicitly says its requested purple assets/palette were **not generated**. A structured brief is a record of intent, not evidence of custom asset generation. `project.json` carries the brief summary without adding a reply line.
- Combat remains `conditional`, never logically proved. A current complete physical module bot with all required modules may qualify readiness; failed assets, a failed audit or a ROUGH/BROKEN tier still prevents it. Relay `Not yet applied` verbatim for scenes, results, media or other runtime-owned fields. Missing optional cast clips use an explicitly reported idle fallback.
- Gameplay 1.2.0 adopts the installed COMBAT2 profile `combat2_v1`, `abilities.config.moveset`, `run.hit_invulnerability_ticks`, and encounter `bosses/attack_budget/attack_gap_ticks`. Before that contract/runtime is integrated, legacy combat remains active and multi-boss finales are sequential development slices, not the final showcase.
- Through the normal tools, call `hermes64_demo` then `hermes64_export` (`module_preview:true` for conditional module exports). Repository-only `python3 -B -m tools.make_demo` repeats those handlers and writes `MAKE-DEMO.json`; it is not an alternate game generator. The development flag `--export-needs-work` never clears the failed badge or returns successful acceptance. Overlay/site packing requires the corresponding owner integrations.

## Pitfalls
- When testing a composed package or changing `bundle_root`, run a **fresh isolated interpreter** with that package first on `sys.path`. Changing the filesystem root does not replace already-imported story modules; otherwise an old in-process checker can generate empty bot traces for a new gameplay API while the subprocess compiler succeeds.
- A pack's static room estimate is not the live combat budget. Measure the physical bot with enemies/corpses present; preserve the 6,000-triangle cap rather than raising it to pass.
- A sky/backdrop piece must retain its semantic `kind: backdrop`; treating a surrounding sky mesh as a normal solid can make every room-entry capsule check fail. Never disable collision or the entry guard to hide it.
- Equal source/game hashes are not equal export bytes. Compare every exported file, including the PCK, and report actual mismatches.
- Compile is not proof; proof is not a rendered playthrough. No generated-file patch can repair source truth.
- E2 selects an existing role profile; E3 needs an explicit authored trigger and ending. Do not invent unrequested prose.
- An empty or failed benchmark dimension is not a success. Asset exit zero requires a measured report too.
- No network, downloads, export-template installs, background services, credentials, or public publication through these tools. The one exception is opt-in: hub downloads happen only from the `hub_url` the owner sets (blank by default).
- Busy projects refuse concurrent writes. Inspect interrupted receipts before manually recovering a stale lock; never delete it while another tool is active.
- The local registration tests do not prove real Hermes loading or catalog admission. See RESULT.md and the checklist.
- For offline integration acceptance, run `sh tools/verify_all.sh` and cite its retained environment/argv/exit receipts. Background shells can resolve a different Python than foreground probes; trust the executed interpreter, not an earlier `python3 --version`. The wrapper aligns child discovery with its chosen interpreter.
- Allocate a fresh screenshot root independently of a nested run directory's leaf name; multiple verification runs may all contain a folder named `e2e`. Never overwrite prior images or infer success from an old report. Headless WAV loading is validation only; playback and visual captures require the actual windowed run.

## Verification
A successful handoff cites exact report paths and current hashes, records every rejected/inconclusive operation, and labels unrun engine/catalog gates. Thaw must be built through these tools in the assembled repository, not hand-assembled and presented as plugin output.
