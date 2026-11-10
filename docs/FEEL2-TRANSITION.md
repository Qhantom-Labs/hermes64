# FEEL2 room transition — presenter integration contract

**Contract v1 — ready/frozen for the presenter owner.** This lane owns only
`view/room_transition.gd`, `tests/feel2_transition.gd`, and this document. The
controller does not dispatch actions, own simulation, or change canonical input.

## API

Mount `preload("res://view/room_transition.gd").new()` under the existing
`presenter.viewport`, above the other low-resolution HUDs. Call
`set_width(viewport.size.x)` from the presenter's existing `resize_screen()`.
The controller uses the existing `look/pixel_font.gd` / `look/pack.gd` palette.

```gdscript
signal entry_requested()  # priority 90: final spawn/camera, BEFORE Movie (100)
signal freeze_requested() # priority 200: after the trigger tick's Movie (100)
signal black_reached()    # once; opaque black, waiting for reveal()
signal finished()         # transparent AND a neutral raw-input release fence

func begin(source_world: Node3D, source_camera: Camera3D,
           source_visual: Node3D, exit_world: Vector3,
           outward: Vector3, reduced_motion := false) -> bool
func active() -> bool
func reveal(room_name: String) -> bool
func release_input(raw_frame: Dictionary, dead_zone: float) -> bool
func cancel() -> void
func set_width(width: int) -> void
func advance(delta: float) -> void # automatic _process; manual test clock also
func card_layout() -> Dictionary  # same fitted text/position/alpha as _draw
```

Read-only-by-contract observations: `phase` (`idle`, `out`, `black`, `in`,
`release`), `fade`, `ghost_viewport`, and `ghost_visual`.

`card_layout()` returns `{text, position, alpha, color, shadow}` or `{}` when
hidden. `cancel()` resets silently (no `finished` signal); an abort/load/teardown
owner must restore any saved process/HUD gates itself. Both source world and
controller must already be in the tree; begin only at an authoritative fixed
action boundary, not from an unsequenced GUI/render callback.

`begin()` captures an isolated World3D copy of the current source world/camera.
All cloned scripts are removed and processing disabled. Only the cloned visual
walks; neither `player.position`, facing, velocities, Action snapshots, story,
nor any existing camera is changed by this controller. This is **not** a copy
of the canonical player used for simulation. A null visual is a valid fade-only
fallback. A visual physics body, foreign camera/visual, non-finite coordinate,
zero horizontal exit direction, or overlapping transition is refused.

Normal fades: **0.22 s out + 0.18 s in = 0.40 s**, excluding a deliberately held
black/build barrier. The ghost walks to 0.35 m beyond the supplied exit plane,
keeping its source height. Remote action-menu exits farther than 2 m use a fade
rather than sliding the actor across the room. Reduced motion uses **0.06 s out
+ 0.06 s in**, without forced actor travel. Black is an explicit phase: even a
large delta cannot skip its handshake. The new room's single-line pixel name
lasts 0.85 s, fits the current 240-scanline viewport, and is not a dialogue,
bubble, interaction, prompt, or input-lock extension. There is no added exit HUD.

## Exact action / pause / entry sequence

The existing synchronous portal receipt must stay synchronous. In particular,
`modules/host.gd:tick_transition()` calls `presenter.commit_portal(action)` and
then sets its validated `pending.arrival`; returning a pretend successful pending
receipt or inserting an `await` there breaks that real caller.

1. In the presenter's **fixed-tick** successful portal path, resolve the source
   door from the actual `move:<room>:<door>` action. Use
   `room_root.target_positions.get(id, Room.door_position(door, room.grid_size))`
   for the exit, not an invented room API. `door.wall` maps north to
   `Vector3.FORWARD`, south to `BACK`, west to `LEFT`, east to `RIGHT`.
   Take the ghost **before** `enter_room()` frees the source room, using
   `world`, `drawing_camera()`, and `player.get_node_or_null("visual")`.
   Validate legality through the existing runtime/module gates; cancel a started
   presentation if the actual action fails. Do not animate boot, checkpoint
   restore, collection-driven room rebuilds, or replay `restore_state()`.
2. Perform the existing `runtime.step(id)` / `enter_room(id)` / `refresh()` /
   `state_changed.emit(result)` **once, synchronously on the triggering tick**.
   Preserve the existing `module_host.travel()` preflight and its 12 simulation
   ticks; capture at its final `commit_portal()` boundary, not before freezing
   a pending host which still needs to tick. The controller never calls any of
   these APIs. The underlying world is now the destination, hidden by the
   old-room ghost until black. Keep successful receipts, sounds, endings, and
   module events on their normal authoritative path.
3. Lock input immediately on that same boundary: set `simulation_enabled = false`,
   `player.simulation_enabled = false`, `player.enabled = false`, and use the
   existing `actions.set_context("pause")`. That clears stick smoothing,
   focus/walk toggles and action buffers and requires a real movement neutral.
   Keep the presenter's transition guard **ahead of** `belt.advance(actions)`,
   quick-save/load/reset/menu handling, follower motion and camera cycling on
   subsequent invocations; ordinary `sync_input_context()` must not override
   this lock. Do not repeatedly call `Actions.advance()`, `restore({})`,
   `set_source()`, `belt.advance()`, or the player mover during the fade.
4. The controller emits `entry_requested` at priority **90**, after normal
   movement/modules (0/10) and before Movie (100). In that handler, finalize
   the matching spawn after synchronous `room_entered` subscribers and the
   region host's arrival override. Existing `enter_room(id)` matches source
   `door.to_door` to the destination door and uses
   `Vector3(at.x, 0.1, at.z).lerp(centre, 0.17)`. The actor bridge's `place()`
   subscriber can replace that with authored protagonist coordinates; reapply
   the intended matching spawn for an ordinary door here if needed. Keep the
   region host's already-validated arrival when that path owns the spawn; do
   not silently substitute an unvalidated doorway. Any canonical entry
   correction belongs **here on the triggering tick**, never at black/reveal.
5. In the same priority-90 handler, frame the final spawn. Existing
   `follow_camera.reset()` only invalidates its centre; it does **not** frame
   a paused room by itself. Call `follow_camera.reset()` and, if
   `follow_camera.available()`, temporarily expose `simulation_enabled = true`
   solely around `follow_camera._physics_process(0.0)`, then restore the paused
   value. This existing method ignores delta and seeds its first centre exactly;
   it updates presentation camera state only. Do not call the player, module
   tick, Actions or toolbelt to obtain framing. Puzzle-owned framing keeps
   control. Also call `n64_ui.hide_dialog()` after entry/module UI refreshes;
   the name card must not become `narration_pending`. Save/hide the visibility
   of `n64_ui`, `controls_hud` and `module_host.hud` while the envelope runs so
   destination prompts/dialogue/combat HUD cannot show through the fade. The
   controller is a separate sibling, not a child of one of those hidden HUDs.
6. Let Movie at priority **100** record/verify that one fully committed canonical
   frame. The controller then emits `freeze_requested` at priority **200**,
   once. In that handler, save existing `is_physics_processing()` booleans and
   disable fixed processing on the presenter, `/root/Actions`, player, replay
   Movie, module host, follow camera and actor bridge if mounted. Use
   `set_physics_process(false)`; leave the controller's `_process` running.
   This tail barrier matters: `call_deferred()` alone can admit a render-dependent
   number of catch-up ticks. `simulation_enabled` by itself does **not** freeze
   Actions, Movie cursors or toolbelt clocks. Do not move hashed fields in this
   handler, because the triggering frame has already been recorded.
7. On `black_reached`, the ghost is already disposed. The room is committed and
   the camera must already be ready. Call
   `reveal(runtime.rooms[runtime.state.location].name)`. It starts at alpha 1;
   the controller consumes no leftover fade-out delta, so a black frame is
   retained even if `reveal()` is called synchronously. A graphical integration
   may hold black across `RenderingServer.frame_post_draw` for shader warm-up;
   the canonical pipeline remains frozen. Do not do new story work here.
8. After fade-in, phase `release` remains input-locked with no blackout. Poll
   `release_input(actions.sample_live(), actions.profile.tuning.dead_zone_pad)`
   outside the canonical tick loop. Digital and pad buttons must be empty and
   both move/camera axes neutral. Malformed/non-finite frames fail closed.
   `sample_live()` reads raw controls without advancing `actions.tick`.
   For production playback use `release_input({}, dead_zone)` instead: never
   consult OS keyboard/pad state or consume `frame_provider` during a replay.
   Bot drivers likewise provide their own neutral raw frame, not live input.
9. On `finished`, restore saved physics-processing booleans and the prior
   simulation gate, call the presenter's `sync_input_context()` once (or set
   the intended context explicitly), and let the **next** Actions tick sample
   normally. Do not run `input_tick()` again against the triggering held edges.
   The pause/gameplay boundary keeps movement blocked until neutral, and the
   raw release fence prevents held E/Space/Tab/R from leaking into the arrival.
   Restore the HUD visibility booleans too, without reopening entry dialogue.
   The name card may finish fading while normal play has resumed.

### Strict replay invariant

Use the same atomic commit, context lock, final entry and priority-200 freeze
for recording **and** playback, not a render-duration tick countdown. The Movie
cursor and Action tick freeze after the triggering frame; neither acquires fade
frames. Only the playback release fence ignores physical input. The ghost,
card, fade clock and follow transform are not movie-state extensions and must
not be added to `Movie.state()` or canonical saves. A different render cadence
changes presentation samples, not recorded frames/checkpoints. Do not loosen
`validate_movie()` build guards or repin expected state hashes to hide a failure.

## Integrated presenter implementation

The presenter now wires the controller and safe-entry/edge-target seams. Portal
commit remains synchronous; the priority-90 entry restores the reciprocal door
spawn after actor metadata, or retains the region host's validated checkpoint.
The priority-200 barrier freezes Actions, Movie, mover, presenter, host, follow
and actor bridge; no fade frames are inserted into movies. The trigger tick's
input lock is deterministic, and the same neutral-latch reset happens at resume
for live/bot/replay. No wall-clock delta enters simulation. Existing region
preflight retains its 12 ticks. Reduced motion uses the controller's 0.12 s fade.

`integrated-attempt-01` observed missing settings run routing, optional latch
validation and actual transition wiring. `-03` caught Godot duplicate sanitizing
autogenerated player names, losing the exit-walk clone; indexed clone lookup
fixes it. `-05` caught legacy preset migration; `-07` caught the stale movement
latch after neutral release. `-08` passes 21 integrated checks including a
72-frame movie strictly replayed twice. All five physical story/module/puzzle
bots pass in `integrated-bots-02`; the earlier failed bot receipts are retained.
The bot stepper waits outside its canonical clock during the same production
envelope rather than throwing action tokens into a frozen tick loop.

The destination global look swap is deferred to black, preserving the exit
copy's shading. The card replaces entry prose during this envelope; no added
exit arrow/glow was justified, avoiding HUD clutter. Final browser/frame-strip
review and export verification are separate gates below/in FEEL2-RESULT.

## Verification / limits

Controller TDD and run receipts are retained in `evidence/feel2/transition/`.
Godot used: `/Applications/Godot.app/Contents/MacOS/Godot`,
`4.6.2.stable.official.71f334935`. The test command is:

```sh
/Applications/Godot.app/Contents/MacOS/Godot --headless \
  --path evidence/feel2/transition/project --script res://tests/feel2_transition.gd
```

| Check | Actual receipt |
| --- | --- |
| Exact controller, two clean processes | `23-controller-clean` and `25-controller-repeat`: **150 checks, 9 cases, 0 failures**, empty stderr |
| Real raw input | InputMap E/W/Space/Tab/R/C press/release samples remain fenced without advancing Action tick/hash |
| Manual presentation cadences | 30/60/144 delta samples complete normal fades in 0.433333/0.416667/0.402778 s; original Action/player canonical digest is identical |
| Existing local regression snapshot | `24-regressions.json`: unit 36/0, controls API 0 failures, input 51/0, animation no failures; all empty stderr |

TDD receipts distinguish API wiring from behavior: `02-wiring` is absence only;
`03` reaches the runnable begin refusal; `04` proves missing visible walk/pose;
`05` the opaque barrier; `06` entry/Movie/freeze ordering; `08` reveal; `10`
neutral release; `11` card creation; `14` card fitting/expiry/whitespace. Reduced
and cancel behavior initially landed with coupled clock work, so those deltas
were removed and rerun RED in `18`–`20` before the final implementation. The
initial harness type-inference error (`01`) and same-frame InputEvent reuse
warning (`21`/`22`) are retained, not counted as clean RED/GREEN. The latter was
fixed with fresh release-event objects; final clean runs contain neither.
Passing invalid-source/held-input controls and the InputMap control are not
misrepresented as new behavioral REDs.

The isolated project is a runtime-source snapshot from **this worktree**, with
only the owned controller/test refreshed between attempts, never shared LIVEFIX
staging. Each receipt binds staged sources by SHA-256. These are controller
preservation/manual-clock tests, not measured FPS or production movie playback.
Presenter integration, actual game movies, rendered screenshot review, browser
capture and exports belong to the parent. No integrated-play or visual-approval
claim follows from these headless checks.

Rendering limit to review at integration: geometry/clip resources are shared
read-only while Environment is duplicated. `look/rig.gd` and `n64_mat.gd` use
global shader uniforms, which Godot shares across World3Ds. A destination look
change can therefore tint the exit copy during its short fade; the parent may
defer that presentation-only global look swap until black if necessary. This
controller does not mutate/recompile global shader state or certify that visual
edge case. No protected input/player/room/camera source was edited by this lane.
