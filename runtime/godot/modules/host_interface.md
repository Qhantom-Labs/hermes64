# MODRT host ABI v1 (merged with Controls API v1)

Owner: MODRT; integration owner: Hermes Main / MERGE2. After MERGE2 the ordinary presenter (`view/presenter.gd`) owns the whole host ABI; `modules/view.gd` and `modules/main.tscn` remain only as compatibility entries.

## Installation

`presenter.boot()` installs exactly one host for STORY 1.2 games: `Host.install(presenter, actions)` with the real `Actions` autoload. Legacy (1.0/1.1) games get no host. Production installation **requires** the Actions provider; a null provider returns a host carrying `binding_error` and boot fails closed. Isolated unit tests may still construct `modules/input_adapter.gd` directly and `inject()` deterministic snapshots; that seam is never reachable from a booted presenter. No alternate bindings are registered. Host physics priority is 10: Actions sampler -100, presenter -50, player locomotion 0, actor bridge/host 10, movie checkpoint 100.

The presenter mirrors the original `modules/view.gd` hooks: it rejects disallowed actions (`allows_action`), routes region-enabled `move:*` to `host.travel` (staged destination preflight), exposes `commit_portal(id)` for the post-preflight commit, rejects unsafe saves, restores the module checkpoint after loads/retries, and registers module state with the movie (`replay.register_state("modules", ...)`, see `modules/movie_state.gd`). Movies must start at a safe checkpoint.

## Control arbitration (single mover)

- Player locomotion (`view/player.gd`) is the only normal mover. `host.prepare_motion()` is called by the presenter at -50 (`sync_input_context`) and decides `player.enabled` and the module speed ceiling `player.speed_limit` for this tick: disabled while paused/modal (`Actions.context != "gameplay"` or `simulation_enabled == false`), during portal preflight, retry countdown, combat roll/hurt, course countdown and course roll.
- Host-owned impulses (combat roll/knockback, course roll) are applied with `move_and_collide` and snapped to the Controls position grid. Never connect a second motion consumer to `motion_requested`.
- Facing uses `player.set_facing_yaw()`; the collision capsule stays axis-aligned. Combat forward is derived from `player.facing_yaw`, not the body basis.
- Space (`dodge`) rolls only during combat or a running course; outside a challenge it has no consumer, and in modal contexts Actions turns it into `confirm`. Combat owns E/Q/Z/Space while an attempt is active; the presenter skips contextual story prompts then. Tab (action menu, e.g. Abort), I (inventory) and Esc (pause) stay available and freeze attempt clocks.

## Host-owned signals

- `control_claimed(owner, generation)` and `control_released(generation)`: owner combat/course/transition; the presenter clears contextual target, Focus and Actions buffers on both edges. Retry holds the mover until ready.
- `motion_requested(intent)`: telemetry of the applied intent (`enabled`, `speed_scale`, nullable `facing_target`, `impulse`). Animation root motion never moves the player.
- `animation_requested(clip, placeholder)`: exact names `idle_combat`, `swing`, `hurt`, `death`, `roll`, `block`. Since MERGE3 the imported combatants carry all six clips and the host shows them phase-locked (`modules/combat/clip_phases.gd`, see "Combat art" below). An actor without them (for example an animal protagonist) still falls back to labelled POSE TEST rig poses. Block requires a real bound clip.
- `focus_changed(id, position)`: the combat target also drives `player.focus_point` and `presenter.focus_id`; authored fixed cameras remain authoritative.
- `story_event(kind, payload)`: local post-observation telemetry (`challenge_started`, `encounter_cleared`, `course_checkpoint`, `course_completed`, `challenge_failed`, `checkpoint_ready`, `region_unlocked`). The presenter shows a short line for the major events and takes a physical checkpoint (with the save icon) on `checkpoint_ready`/`encounter_cleared`/`course_completed` when the story state is checkpoint-safe. It is not a player command or untrusted message validator.

`set_modal(bool)` freezes attempt clocks and clears intent. Provider-owned held inputs must return neutral before new gameplay effects. A generation increments on clear/start/room/load; transient actors/targets are destroyed. `finish_attempt` is internal trusted-executor code; menus must never call it. Ordinary `runtime.step` rejects analysis outcomes.

## Art binding seam

Optional toolkit manifest `res://combat-bindings.json`: `{"api_version":"1.0.0","bindings":{...}}`. Keys are `player` or admitted archetype IDs; values pin an existing character row with `character_id` and exact `sha256`. Normal rig/material/clip validation and provenance remain the character pipeline's responsibility. The module resolver checks that the row is non-placeholder, the file hash matches and all six required clip names are listed. A present malformed/missing/corrupt binding rejects boot. A pinned archetype keeps its pinned actor even when combat art is staged.

## Combat art (MERGE3)

`res://combat.json` (`api_version` 1.0.0, schema `hermes64-combat-runtime/1`) is written by `characters.integration.stage_combat` from `characters/combat/manifest.json` during runtime staging; export copies its GLBs as hash-checked media. It holds the enemy models of the staged kit pack (`cairn_dasher` = `melee_dash_v1`, `reed_warden` = `melee_approach_v1`; an archetype without its own model, such as the Cairn Keeper elite, uses its FSM template's model), the `trail_staff` per character pack, every public combatant's `hand_r` grip and the clip phase metadata. A present malformed file rejects boot; an absent file keeps the pre-MERGE3 POSE TEST path.

- **Phase-locked keys, never a clip clock.** Clips are 16 STEP keys over 1 s. The host picks the key from the tick state the combat runtime used for its checks this tick (`shown_swing`/`shown_roll`/`shown_hurt`), and seeks it (`AnimationState.show`). Swing: windup → keys 1-4, active → 5-7, recovery → 8-15, so damage can only land while keys 5-7 are on screen. Roll: the 15 invulnerable ticks show the documented i-frame keys 2-9, the remaining 9 ticks rise/ready keys 10-15. Hurt: keys 1-15 over the 18 hurt ticks. Death: 15 fps from key 0, holding key 15. Block: raise keys 1-2 on the first two ticks (protection starts on the press tick, unchanged), then guard keys 3-15 at 15 fps, holding 15. idle_combat loops keys 0-14.
- **Enemies.** FSM state → clip from `fsm_state_clip`; keys from the saved FSM age: telegraph keys 1-15 over `windup_ticks` (ending on the hold keys), attack shows only the documented hit-window keys over `active_ticks` (every attack tick may land), recover keys 1-15 over `recovery_ticks`, hurt keys 1-15 over 12 ticks, death in real time. The face atlas cell follows the clip (telegraph/attack 1, hurt 2, death 3, else 0). Defeated enemies stay as presentation-only corpses for 90 ticks; on a KO the player's corpse plays death during the retry countdown. Corpses are never hashed, saved or collided.
- **Staff.** `trail_staff` rides a `BoneAttachment3D` on `hand_r` with rotation `(0.8660254, 0, 0, 0.5)` and the character's grip translation; `kit_acc_hand_*` stance props hide while combat owns the actor and return afterwards.
- **Audit.** `host.combat_audit` (presentation only) records the keys on screen at every hit, contact and attack start; `module_runner.gd` writes it to `native.json` as `combat_clips`, and acceptance requires zero violations.

## COMBAT2 additive profile

Gameplay API 1.2.0 adds opt-in `movement_combat_profile: combat2_v1` and abilities config `moveset: brawler_v1`. Read `docs/COMBAT-MOVESET.md` for the frozen field surface. `host.run.snapshot()` publishes ticks, deaths, finished_tick, started and cue ages; disabled runs add no legacy snapshot keys. L2 must freeze simulation through the existing gate while cards show. Capture/restore includes complete brawler/budget/run state; normal finite checkpoint files are not ranked run receipts. New optional animation names fall back to the required swing/block clips. Host impulses still use move_and_collide; this lane never changes the mover or camera.

## Bot and acceptance boundary

The module bot (`playtest/module_runner.gd`) submits every movement, menu and combat input through `Actions.submit_frame` (source `bot`) and records one deterministic `modules.h64movie.json`. Combined native assertions live in `tests/merge2_controls.gd` and `tests/merge2_course.gd` (arranged contacts there are unit assertions, not bot wins). No physical gamepad or human-feel evidence is claimed.
