---
name: hermes64-gameplay-modules
description: "Use when authoring gameplay data. Verify bounded contracts."
version: 0.1.0
author: Qhantom Labs, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [games, contracts, verification]
    related_skills: [hermes64]
---

# Data-only gameplay modules

Use for STORY `1.2.0` module contracts, compiler/checker, finite abilities/keys,
checkpoint saves and typed edits. Load `docs/MODULES-CONTRACT.md`,
`docs/MODULES-PROOF.md` and `docs/MODULES-INTEGRATION.md` in the toolkit first.
This is phase-1 data/model support, not working Godot combat or a racing engine.

## When to use

Use for module source authoring, typed module edits, data-only regression checks
and runtime contract handoffs. Do not use to certify physical playability or
replace the legacy/native release workflow.

## Prerequisites

Use `read_file` for the contract docs. Python 3.9 stdlib is sufficient; an owner
must choose an existing absolute managed projects root before facade writes.
No engine or dependency installation is required for this data-only slice.
The bundled plugin's retained platform is macOS; other hosts are not certified
by this skill or by its offline import checks.

## Supported slice

- Original arena/enemy template data; bounded spawns/waves and hosted rewards.
- Connected outdoor region graphs with finite door gates, not seamless worlds.
- Ordered timed on-foot courses, not vehicle racing.
- Shared challenge lifecycle and monotonic finite abilities.
- Checkpoint-only save v2; explicit 1.1.0 conversion, never a mid-fight resume.

## Author/check/edit workflow

1. Inspect `hermes64_modules` only if Main has actually integrated the registration.
   A local Python registration test does not establish installed Hermes loading.
2. Author only the closed JSON fields. Never insert per-game scripts, custom
   registry entries, path-valued behaviors or metadata event wiring. Unknown
   versions/fields, cyclic ability dependencies, duplicate IDs and nonfinite
   numbers must reject, not be repaired silently.
3. Call `hermes64_module_check` with the managed project, source path and explicit
   `adopt: false` to inspect a candidate. For intentional data adoption use
   `adopt: true` plus exact expected source/build hashes (both empty only for an
   initial data pointer). Never treat this as runtime adoption.
4. Apply `hermes64_module_add` or `hermes64_module_edit` with the closed operation,
   exact current hashes, externally declared `expected_changed_rooms`, and a
   checkpoint `save_path` when checking persistence. Do not hand-edit generated
   game JSON or lower proof/locality gates to make an edit pass.
5. Read actual proof, structural diff, changed/unchanged room hashes and migration
   results. Failed checks, conflicts, locality, migration or artifact IO retain
   the previous data pointer. This pointer is `.maker/modules/current.json`,
   separate from any runtime/verified pointer.
6. Run `hermes64_module_benchmark` with explicit operations/locality and a save.
   Count only actual `data_verified_passed`; `fully_verified_passed` stays zero
   until real runtime requirements are met elsewhere.

## Operation shapes

The tool schemas advertise only `kind`; the full shapes below are what the
handlers validate (`contracts/gameplay/1.0.0/tools.json` is the frozen copy).
One object per operation: `kind` plus the listed fields, all required unless
marked, and optional `expected_changed_rooms` (unique room IDs). IDs match
`[a-z][a-z0-9_]{0,63}`; vectors are `[x, y, z]` metres within ±1024.

- `add-enemy` (module_add): `enemy` = {id, name, max_health 1-64, speed_mps
  0.1-20, aggro_range_m and leash_range_m 0.1-64, attack_range_m 0.1-8,
  fsm {template `melee_approach_v1`|`melee_dash_v1`, initial `idle`, states:
  all seven of idle/approach/telegraph/attack/recover/hurt/dead}, attack
  {windup_ticks 1-600, active_ticks 1-120, recovery_ticks 1-600, damage 1-64}}.
- `modify-enemy`: `id` + `changes`, a non-empty subset of the enemy fields except id.
- `change-arena`: `id` (encounter) + `changes`, a non-empty subset of {arena
  {min, max}, spawns 1-24 [{id, archetype, position_m, wave 0-7}], room}.
- `gate-region`: `id` (region link), `endpoint` `a`|`b`, `conditions`: list of
  {ability} | {item, present} | {flag, equals} | {challenge, status: completed} |
  {location} | {tide} | {dialogue, node} | {role, equals} | {collected} | {group, at_least}.
- `change-course-checkpoints`: `id` (course) + `checkpoints` 1-32 [{id, position_m, radius_m 0.1-4}].
- `add-ability` (module_add): `ability` {id, name, requires: ability IDs} +
  `grant` {kind: initial} | {kind: interaction, id} | {kind: challenge, id}.

STORY `1.3.0` puzzle sources (`docs/PUZZLES.md`) accept the kinds above except
`gate-region` (refused: no regions with the puzzle family) plus four puzzle kinds.
Puzzle and element IDs match `[a-z][a-z0-9_]{0,47}`; a cell is `[column, row]`, 0-15.

- `add-switch` (module_add): `puzzle` + `switch` {id, cell, mode `toggle`|`latch`}.
- `link-door`: `puzzle`, `door` (a door, timed gate or bridge element, or `goal`),
  `when` {of: 1-8 unique element IDs, at_least 1-8, invert: boolean}.
- `move-block`: `puzzle`, `block` (a block element), `cell`.
- `set-solution-hint`: `puzzle`, `hint`: up to 16 unique element IDs, the order the
  Focus assist (hold Z) points at.

`hermes64_module_edit`, `_add` and `_benchmark` (1-20 operations) require
`expected_spec_hash` and `expected_game_hash` (64 lowercase hex). `module_check`
needs them only with `adopt: true`, both `""` for the first data pointer.

## Evidence language

- A successful challenge graph is `conditional`, with named
  `combat_<id>_completable` / `course_<id>_completable` assumptions and
  `spatial_access`. An `assume:complete:*` witness is analysis-only, not a player
  action or physical replay.
- CLI `story check`: 0 = logical proved; 4 = conditional; 3 = inconclusive;
  2 = rejected/invalid. A search cap is inconclusive, never proof or rejection.
- A course distance/speed lower bound can reject an impossible time limit; a
  passing bound cannot prove steering, collision or human feasibility.
- Runtime, physically tested by bot and human-tested remain `not_run`. Missing
  action clips (`idle_combat`, `swing`, `hurt`, `death`, `roll`, `block`) may not be
  concealed by idle fallback in the later runtime.
- Save membership proves an abstract checkpoint, not a trusted physical history.
  Migration must validate old provenance and target membership, preserve old
  bytes on rejection and never replay completed rewards.

## Verification

Python 3.9 stdlib only; no install/network required. From toolkit root use
`terminal(command="python3 -B -m adventure_modules.export_contracts")`, then
`terminal(command="python3 -B -m adventure_modules.examples examples-authoring-NEW")`,
then `terminal(command="python3 -B -m adventure_modules.verify regression-NEW", timeout=600)`.
Use new evidence stage names and preserve failures. Verify legacy canonical
source/game/proof/save and room hash receipts against the recorded baseline.
The scoped runner includes every story and plugin fast test, explicitly excluding
native suites. It does not replace the full release gate or independent review.

## Pitfalls

Preflight full response encoding/report storage before committing the data
pointer: a late report-write failure must not return failure after adopting a
candidate. Bind every report to exact hashes and read back the pointer. Room
closures must include shared archetypes, both link endpoints/arrival checkpoints,
and transitive ability use in local dialogue/collectibles, without dragging in
unrelated neighbouring doors. Check failed attempts even when a completion flag
would otherwise match an ending, or retry dead ends can disappear from analysis.

Do not treat unchanged compiled legacy hashes as proof that a source-pinned
style lock still matches. Retained project locks hash toolkit source bytes; a
compiler dispatch change can require an explicit owner-controlled lock revision
even when every legacy game/proof/save remains identical. Preserve the failing
raw test receipt, keep approval null/runtime pending, and never skip that gate
or mutate an out-of-scope starter lock to manufacture a green suite. Memoize
ability DAG admission so a dense finite prerequisite graph cannot force an
exponential repeated traversal.

Keep runtime/view/asset work with its commissioned owner. Never enable tools,
restart services, edit another worktree or publish merely because this skill is
present. New games should require only data changes; retain toolkit-before/after
hashes across independent fixture creation.
