# Auto-repair: failure classes and fix hints

When a proof, compile, playtest or style audit fails, the tool result carries `next`: an ordered list of exact
tool calls that fix the game and re-check it. A cheap model can run them verbatim, read the new result and repeat.
Code: `adventure_maker/repair.py` (planner), `adventure_maker/audit.py` (style findings). Tests:
`tests/test_repair.py`, `tests/test_audit.py`. Measured hit rate: [AUDIT-RESULT.md](AUDIT-RESULT.md).

## Where `next` appears

| Tool result | When | Steps |
|---|---|---|
| `hermes64_compile` error | `compile_failed` (spec error) | `hermes64_compile(spec_path=<the failed copy>, patch_json)` → `hermes64_check` |
| `hermes64_check` | `rejected` / `invalid` | `hermes64_compile(spec_path=<current spec>, patch_json)` → `hermes64_check` |
| `hermes64_check` | proves, but some content can never happen (`lint`) | `hermes64_edit(json-patch)` (proved) or compile + check (conditional) |
| `hermes64_check(action="audit")` | an error-level style finding | optional `hermes64_build_assets` → `hermes64_edit(json-patch)` → `hermes64_check(action="audit")` |
| `hermes64_playtest` | not PLAYABLE/SOLID | proof fix and/or module envelope fix → `hermes64_check` → `hermes64_playtest` |

Step shape: `{"step": 1, "tool": "hermes64_compile", "args": {"project": "...", "spec_path": "...", "patch_json": "[...]"}, "why": "..."}`.
`patch_json` is RFC 6902 (add/remove/replace/test). All fixes of one round are built on a working copy, so every op
is valid in order. `hermes64_compile` applies the patch to that spec and writes a new immutable revision; it never
rewrites the source file. A proved build uses `hermes64_edit`, which is adopted only if it still proves.

## Rules

- **Causes first.** A blocked producer is fixed before the ending that needs it; softlocks and unreachable endings are
  usually consequences, so they are analysed only when nothing deeper explains the failure.
- **Never guess silently.** Findings without a safe mechanical fix have `auto: false`, go to `manual`, and produce
  no step. Two judgment calls (which ending condition to drop, how to separate two endings) are tried in-process
  with the local story compiler/checker and offered only when the candidate proves (`verified: true`).
- **Labelled heuristics.** Fixes that change design intent carry `heuristic: true`.
- **Deterministic.** Same report and spec, same plan.

## Failure classes

| Class | Detected from | Fix (typed patch) |
|---|---|---|
| `missing_exit` | door graph from the start room | add a reciprocal door pair to the first reachable room, free wall slots |
| `locked_gate` | a door/challenge condition nothing produces, or only produced behind the same gate; module `gate:`/`region:` counterexample | drop that condition (module gates: drop the door's conditions, heuristic) |
| `unreachable_item` | an interaction condition nothing produces | drop that condition |
| `unreachable_ending` | ending condition nothing produces; else the one condition whose removal proves (in-process) | drop it |
| `unreachable_collectible` | collectible condition nothing produces | drop it |
| `impossible_threshold` | collectible group/threshold asks more than exist | set it to the supply |
| `dead_end_dialogue` | a dialogue node/choice the story can never take (the engine always offers "End conversation", so a dead end means an unreachable branch) | drop the impossible condition |
| `softlock` | proof softlock with a door that stays shut / a consumed key | drop the blocking condition or the consuming `take` (heuristic); else manual |
| `ambiguous_ending` | two endings match one final state | the more general ending also requires a flag value, picked by an in-process proof; else manual |
| `broken_reference` | compile: `missing reference` / malformed condition | remove the reference |
| `door_not_reciprocal` | compile: door pair does not point back / missing `to_door` | link to the door that leads back, or add one |
| `missing_camera` | compile: no camera anchor | add camera `main` looking at the room centre |
| `bad_door_position` | compile: outside wall extent / duplicate slot | move to the nearest free slot |
| `bad_module_config` | par > deadline, crossed arena box, spawns outside the box, waves not contiguous or over the simultaneous bound | set par to the deadline, sort min/max, clamp spawns, renumber waves |
| `impossible_course_time` | module `metric:` counterexample (minimum ticks) | `time_limit_ticks` = 1.5 × bound (par capped) |
| `unwinnable_arena` | playtest not PLAYABLE + enemy stats outside the Reedland envelope (health ≤ 4, speed ≤ 1.5, reach ≤ 1.3, windup ≥ 36, active ≤ 12, recovery ≥ 36, damage ≤ ⅓ player health) | reset those stats to the bound (not a balance claim) |
| `unreachable_checkpoint` | on-foot course checkpoint above 1 m | put it on the ground |
| `missing_binding` | piece/prop/floor asset not in the pack bindings (draws a magenta cuboid), rendered cuboid placeholder, untextured surface, character without a body binding | replace with the nearest known asset of the same family; rebind the character to a public cast row (compile route: identity changes) |
| `over_budget` | rendered room triangles over `room_tris`; surfaces over 256 (warn); actor over `character_tris` (warn) | drop the heaviest authored pieces until under the cap; else manual (shell/cast cost) |
| `palette_drift` | room `look` colours outside the palette hue families; rendered palette adherence | snap the look colour to the nearest palette entry; asset-level drift is manual |
| `flat_room` | flatness, contrast, depth separation, detail, value range, cutaway void, free-standing doors, camera outside, exterior sky/haze/bands/ground/landmark | void/doors/camera/exterior with no built assets: `hermes64_build_assets` first; then add a lamp pool, rug and prop near the camera target (interiors) or `terrain.patch` floor + rock/bush/tree (exteriors) |
| `fog_swallow` | fog covers too much of the frame | room `look.fog`: far × 1.5, max ≤ 0.5 |
| `character_off_frame` | room characters all outside the default camera frustum (warn) | manual hint (move them toward the camera target) |

## Not covered (manual)

Permanently missable collectibles, retry/reward module obligations, softlocks with no blocking door or consumed key,
ambiguous endings no single flag can separate, asset-level palette or texture problems, character triangle budgets
(owned by the character lane), N64-fidelity tells (warnings only).
