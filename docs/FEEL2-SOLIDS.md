# FEEL2 solid items

Implemented in the solids lane on `feel2-lane`, commissioned base `7edc26fd`. Actual session header: **gpt-6.1-sol / openai-api (OpenAI API)**; xhigh as commissioned. No fallback observed. Parent owns the hourly model document and presenter/export integration. Local git only: no network, installs, push, reset/stash, other worktrees or writes to shared LIVEFIX staging.

## Outcome

Placed furniture, ordinary props/items, stationary NPCs and large terrain now have native collision built from deterministic simulation footprints. The old straight-through-prop route is blocked, as are module `move_and_collide` impulses. Existing capsule sliding, steps, slopes and authoritative position quantization are retained. Story IDs, effects, conditions, game data and visual assets are unchanged.

**Parent integration remains required:** the collision bodies install automatically in `Room.build`, but contextual edge refresh and safe-spawn calls belong in the parent-owned presenter. This lane did not edit `presenter.gd`, `input/*`, `follow_camera.gd`, README or PLAY.

## Caller contract — version 1

1. `Room.build(...)` installs `room_root.solid_definitions` and their sorted native `room_root.solid_bodies`. Settling freezes its one-shot placement result; subsequently changing a mesh/camera/animation transform cannot move a simulation footprint. Additional generated support/accent pieces register collision too.
2. Call `room_root.update_interaction_targets(player.position)` **before contextual selection on every fixed tick**, and immediately on room entry. `target_anchors` preserves authored positions; `target_positions` supplies exposed nearest-edge prompt positions. This avoids an NPC/furniture collider occluding its own interaction ray and lets pickups on supports be reached from the edge. Dispatch still uses the original ID and original story conditions.
3. Call `player.place_in_room(room_root)` **after the final entry/retry/portal/checkpoint position has been chosen**, before capturing its checkpoint. Check the returned `ok`. A valid position is preserved exactly; an overlapping legacy spawn is moved to a deterministic nearby capsule-clear point, at most 2m away. Failure is explicit, not permission to disable a collider or silently declare the room playable.
4. Ordering matters: `actors/bridge.gd` can overwrite the protagonist position in its `room_entered` callback. Place only after that callback has run. Module-host checkpoint/portal/retry placement also occurs after some presenter entry paths, so apply the same placement contract after those final assignments, not merely before `room_entered.emit`.

Minimal caller intent (integrate into the actual lifecycle, not a second movement consumer):

```gdscript
# After final actor/module entry placement:
var placed: Dictionary = player.place_in_room(room_root)
# Refuse/report a false placed.ok; do not exempt obstacles.
room_root.update_interaction_targets(player.position)

# Each fixed contextual-selection tick:
room_root.update_interaction_targets(player.position)
```

The navigation/placement receipt is derived state and is not added to movie hashes. Native collision handles ordinary motion and existing module impulses; no alternate test-only mover or `move_and_slide` replacement was introduced. All 32 audited room states retained their authored default spawns without adjustment.

## Geometry policy

- `view/solid_footprints.gd` compiles immutable definitions without reading rendered meshes or camera transforms. `solid_kit_metadata.json` carries the **123 exact-SHA metadata records from the existing `kits/manifest.json`**; Python tests compare the shipped catalog with that source.
- Prefer declared footprint outlines and every footprint-bearing socket. Actual dungeon sockets use glTF `position`; `pos_gltf` is also accepted. Concave outlines are triangulated rather than filled by one convex hull. Hollow seating honors `walkable_inner_radius_m`, with separate rim parts and its declared central table instead of an impassable whole-room bbox.
- Otherwise use the kit bbox, preserving the immutable GLB's origin offset. Kit `bbox_size_m` uses Blender x/y/z; glTF/Godot uses x/y/z with Y up. Legacy bindings without metadata read glTF POSITION-accessor bounds and node TRS/matrices directly. Missing art gets a conservative 0.7m placeholder footprint with the authored scale/yaw preserved.
- Shape scale is baked into dimensions/vertices, never a nonuniform physics-body scale. Stationary humans/cats use fixed capsules, independent of limb/accessory animation. Collected follower proxies leave the room collision with the existing room rebuild.
- Explicit walkthrough semantics: doors/windows and structural walkable surfaces; grass/flowers; rugs/blankets; sky/backdrop; declared pickups/collectible proxy art; explicit `meta.walkthrough`. Real supporting furniture remains solid. Rocks, trees, columns, railings and generated floor-standing dressing remain obstacles. No bot-specific obstacle exemption exists.
- IDs, native-body insertion, metadata traversal, grid construction and tie-breaking have fixed order. `solid_navigation.gd` uses a 0.25m capsule-clear grid and 0.05m sampled segment validation; clear endpoints alone cannot authorize crossing a prop. Room boundaries are compared in the same float32 vector domain as the player, preserving the original margin rather than widening it to hide roundoff.
- Existing room floor/bounds and puzzle microgrid authority are not replaced with a whole-shell bbox. Puzzle gates, movable blocks and puzzle effects remain owned by the existing rules/controller.

## Connectivity and physical coverage

`tools/feel2_solids.py` reconstructs shipped fixtures into **only** `evidence/feel2/solids/staging`. It never calls the shared staging mutators. It fails on script errors even when Godot exits zero, missing receipts, empty case sets, incomplete/duplicate game-room rosters or accepted bad controls.

Final receipt: `evidence/feel2/solids/final-solids-01/connectivity-summary.json`:

- **All five games, 16 rooms, 32 resident/collected room states.**
- **154 required-target checks**: interactions, available collectible/NPC anchors, every exit, module starts/checkpoints and course checkpoints.
- **58 reciprocal entry/checkpoint linkage checks**, all linked.
- **302 puzzle-cell and 464 adjacent-segment checks** against the actual room solids. This prevents grid-owned position animation from silently walking through a newly placed native prop. Every potentially usable grid cell is checked, not just the winning route.
- **14 detected negative controls**: full room partitions and unreachable high checkpoints in every game, plus a native obstacle over the start cell in each of Puzzle Hall's four rooms. No failure was turned into an obstacle exemption.

Room enumeration and all-collected arrangements are explicitly **geometry fixtures**, not injected story wins. Story progression is separately exercised by the physical bots below.

### Actual production-input bots

`inherited-bots-final/summary.json` records complete physical runs. The two new test adapters inherit the existing story/module bots and change only target-edge planning and capsule-clear routes; movement/menu/combat still use production `Actions.submit_frame`, native bodies and the existing solvers. They do not inject positions, health, rewards or outcomes. Puzzle uses the existing physical puzzle runner and a plan bound to the exact shipped sidecar/game hashes.

| Game | Recorded ticks | Actual result |
|---|---:|---|
| Thaw | 7119 | Both Quiet Night and Thaw endings; no stuck/unreachable/failure |
| Reedland Relay | 2817 | Combat, course, portals and Home ending; no failures |
| Reedland Combat | 927 | Arena challenge and Home ending; no failures |
| Puzzle Hall | 2276 | All four puzzle rooms to Dawn; no mismatches/failures |
| City Arena | 3966 | District sweep, boss fight and Home ending; no failures |

All five processes exited zero with empty stderr. These are bounded headless bot results, not human feel/balance/art approval.

## TDD and determinism evidence

- `attempt-01-room-red.json`: behavioral RED against the old production room/mover. The actor walked through the prop to x=11.6; the module impulse crossed it to x=11.0. `attempt-02-room.json` blocks both; final straight-walk x=5.3891.
- `attempt-03-geometry-red.json`, `attempt-06-room-targets-red.json`, `attempt-07-feel2_room_targets.json`, `footprints-red/`, `socket-schema-red/`: observed missing metadata/exclusions, missing NPC/terrain bodies, self-occluded NPC prompts, filled hollow footprints and the real socket-schema defect before their fixes. Initial API-absence probes are retained as **wiring** evidence, not substituted for behavioral RED.
- `south-exit-red/`: detected Sun Hall's float32-vs-double boundary misclassification; corrected the comparison domain without increasing reach or shrinking collision.
- `puzzle-grid-aggregation-red.log`: a falsely green puzzle receipt with no native grid clearance was rejected after the guard was added.
- Final native suites: solids **7**, geometry **14**, room/target **10**, navigation **14** checks, all passing; native detour bot **141** ticks, **0** penetration ticks and an unobstructed actual NPC edge ray. Existing collision/motion/API suites also pass in `final-solids-01/`.
- `collision-rates-02/summary.json`: exact blocked/sliding native motion trace SHA-256 is identical at 30/60/144 render caps: `554de276c7cce5fbce10e46393ad89f671c89b1887e696ba396f00281a17ee8f`. The glancing-corner test retains no penetration and a bounded sticking streak. Its first 100-tick arrival assumption was too short for the other FEEL2 lane's legal walk default (zero stuck ticks); the retained failed calibration was corrected to allow 240 ticks without changing product speed or collision assertions.
- `inherited-replay-final/summary.json`: **six newly recorded movies, 12 cold strict production playbacks**, every expected hash unchanged. No build-header rebinding was used.
- `native-detour-replay-final/`: the new production-input detour movie passes strict playback at 30/60/144 caps (129 movie ticks, 3 checkpoints each). These are determinism checks, not measured FPS claims.
- `module-regressions-01/`: module parity 378, bindings 3, mechanics 18, physics 11 and combat robots 66 checks pass. `puzzle-parity-01/parity.json`: 20 puzzles, 80 walks, 11,200 transitions, **33,761 Godot checks**, pass. `story-suite-01.log`: **160 Python story tests**, pass. `final-python-01.log`: **7 runner/catalog guard tests**, pass.

### Honest retained failures / limits

The optional synthetic `module_lifecycle` fixture run reports 7 failures in 14 checks. The **identical failures reproduce with the same fixtures in a plain `git archive 7edc26fd` inside this worktree** (`baseline-regressions-01/process.json`), so this is not presented as a green full module suite or repaired outside scope. Actual shipped Relay/City portal/checkpoint journeys above pass. An initial puzzle-rule run lacked its vector file; the official vector generator's complete passing parity run is retained separately. Earlier parse/harness failures remain in their attempt folders.

No full-repository Python, final export/package, rendered feel, native OS keyboard or human playthrough acceptance is claimed here. Parent still integrates the caller seams and performs final exports/replays. No story or historical movie checkpoint was repinned. Old routes that physically crossed props are intentionally no longer compatible: their movement/state hashes must diverge. Parent should review new collision-aware routes and deliberately adopt any new movies, never rewrite old expected hashes to force a pass.

## Parent integration and wider regressions

The parent integrated edge updates and final spawn clearance into the actual
presenter/actor lifecycle. Wider Python tests then caught a sub-floor water plane
being treated as an NPC prompt container in two-dimensional containment. The
geometry regression first moved that prompt 9 m away, then passed after prompt
selection/exposure also checked vertical extent. Native solid bodies are not
exempted: below-floor water simply cannot own an above-ground interaction edge.

The production `playtest/runner.gd` (not just the new adapters) now uses the same
immutable footprint navigation and edge targets. Its original native trap,
unreachable-target and script-error controls remain active. The actor speed
oracle explicitly chooses auto-run to retain its original 2.4 m/s stress instead
of weakening the expected speed to accommodate the new walk default. All
`tests.test_characters_runtime` and `tests.test_ship_native` tests pass after
these full-suite discoveries (`python-targeted-02.log`).

## Reuse

From this exact worktree:

```text
/usr/bin/python3 -B -m unittest tests.test_feel2_solids -v
/usr/bin/python3 -B -m tools.feel2_solids <fresh-label> --connectivity
/usr/bin/python3 -B -m tools.feel2_solids <fresh-label> --games thaw --suites feel2_solid_bot controls_collision controls_motion controls_api
/usr/bin/python3 -B evidence/feel2/solids/run_inherited_bots.py <fresh-label>
```

The retained inherited-bot orchestrator is evidence tooling, not a replacement game runtime. Stage copies, PCKs, movies and exhaustive per-tick logs remain locally under `evidence/feel2/solids`; only selected compact receipts need to accompany the feature commit. Source-byte pins for the final native suites are in `final-solids-01/source-inputs.json`.
