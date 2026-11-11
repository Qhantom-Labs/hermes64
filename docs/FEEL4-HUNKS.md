# FEEL4 hunks in shared files

New FEEL4-only files are not listed (`view/kit_shells.gd`, `view/shell_kit_metadata.json`, `tools/feel4_shells.py`,
`tests/feel4_*.gd`, `tests/test_feel4_*.py`, docs). Every hunk below is tagged `# FEEL4` in the code.

## P1 collision

`runtime/godot/view/room.gd`
1. `build()`, presentation pieces loop, after the `mounted` meta line: one added line
   `if kit_shell and placed_node is Node3D: KitShells.collect(...)   # FEEL4`.
2. After `var boundary_source := ""`: two added lines (`const KitShells = preload(...)`, `var kit_outlines := []`).
3. `build_boundary()`: an `elif not kit_outlines.is_empty():` branch (3 lines) after the shell/yard outline branch,
   and one line after `boundary_outline = boundary_polygon(raw, w, d)` (`KitShells.doors_inside(self)`).

`runtime/godot/view/solid_footprints.gd`
1. `definition()`, before `if not polygons.is_empty():`: a 7-line `kit_obstacles` branch (binding policy from
   `room.register_solid`). Bindings without `kit_obstacles` are unchanged.

## P2+P3 goal cue, controls hint

`runtime/godot/view/presenter.gd`
1. `boot()`, right after `scene_cards.attach(self)`: two added lines
   (`preload("res://view/goal_cue.gd").install(self)`, `preload("res://input/controls_hint.gd").install(self)`).
   Both return without adding a node unless the game is arena_run_v1/premise or opts in
   (`metadata.presentation.goal_cue` / `controls_hint`). GAPS2 also edits `boot()` (text_boxes read after
   `runtime.configure`, `boxed(...)` at `last_text`): different lines, no overlap expected.

## P5 playtest combat bot

`runtime/godot/playtest/combat_bot.gd` (no other lane touches it; bot runs only, never replays)
1. New `safe_roll_aim()` / `roll_is_safe()` / `rings()` helpers after `free_to_act()`; `const Robot` preload.
2. `decide()`: the three roll returns (rings, shots, decals) go through `safe_roll_aim`; with no safe roll the bot
   waits (no swing) until contact <= LAST_CHANCE (1), then rolls exactly as before. Rule 4 returns idle while waiting.
   Why: with solid shell walls the demo's club fight started from a different state and the bot lost it; both hits came
   from the ring a brute slam emits catching the roll at tick 16 (first tick after its 15 i-frames), not the walls.

## P4 camera

`runtime/godot/view/follow_camera.gd` (no other lane listed it)
1. After `var heading_ready := false`: FEEL4 constants/state (FOLLOW_START/STOP, FOLLOW_HEADING_RATE, ORBIT_LEAD,
   following, follow_heading, follow_heading_ready, aim_sample_velocity).
2. `orbit_tick()`: manual orbit lead clamp (1 line); auto-follow hysteresis + low-passed travel heading (replaces the
   2-line threshold); heading guard skipped during `orbit_override`; braking-curve yaw controller (replaces the
   clamped spring, same 65 deg/s / 130 deg/s^2 auto caps); soft guard limit (safety clamp kept at +0.15 rad).
3. `reset()`: resets the new state and calls `face_goal()`; new `face_goal()` after `reset()`.
4. `_physics_process()`: aim sample filtered like the eye (2 lines + reset of `aim_sample_velocity`).
5. `present()`: aim spring uses the eye's omega; rotation controller is a braking curve (360 deg/s^2 cap, 240 deg/s)
   instead of the clamped PD (240 deg/s^2, 85 deg/s).

## Merge check (text level, `git merge-tree --write-tree`, no ref or worktree written)

| other lane head | result |
|---|---|
| GAPS2 `c6607b1b` (touches `presenter.gd` boot() lines 168-199 and room.gd line 296) | clean, no conflicted paths |
| CHARBIND `82bca4bd` | clean, no conflicted paths |

A 3-way merge of all three lanes was not run. A clean text merge does not prove that the merged runtime behaves.
Two semantic contact points: the controls hint moves above a shown dialogue box (`n64_ui.dlg_on`), so it still
works once GAPS2 removes the room-description box; and GAPS2's bot waits for scene cards in `bot.gd`/`runner.gd`,
which are not the FEEL4 file `combat_bot.gd`.
