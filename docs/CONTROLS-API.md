# Controls API v1 — FROZEN integration surface

Owner: CONTROLS, `controls-lane`. Implemented in `res://input/actions.gd`; Godot autoload **Actions** (a Node, not a static class). Module consumers may also receive this instance by dependency injection. Do not read `Input`, keycodes, wall time or device events in gameplay modules.

## Stable consumer contract

Read during `_physics_process`, **after priority -100** (the input sampler). Simulation is fixed **60 Hz**. Each getter is idempotent within a tick; edges are not consumed by reading them.

- `Actions.get_move() -> Vector2`: camera-space `(right, back)`; forward is negative Y. Circular length <= 1. Keyboard magnitude ramps; pad magnitude is continuous after radial dead zone. Player owns camera-basis transformation/latch and velocity, not modules.
- `Actions.is_pressed(name: String) -> bool`: semantic held state this tick. Unknown names return false.
- `Actions.just_pressed(name: String) -> bool`: semantic rising edge, true for exactly one sampled tick. Unknown names return false. `move` means nonzero movement.
- Required names: `move`, `walk`, `primary`, `secondary`, `focus`, `dodge`, `menu`, `action_menu`, `inventory`, `quick_save`, `quick_load`, `reset`.
- In gameplay, `walk` means **precision** even when user selects inverted hold-to-run or toggle. In a modal context it reflects the physical binding for settings navigation; gameplay must already be gated. `focus` reflects the user's hold/toggle choice. `reset` fires once after the configured hold duration, not on the initial R press.
- `primary` = E; `secondary` = Q; `focus` = Z; `dodge` = Space; `menu` = Esc; `action_menu` = Tab; `inventory` = I. F5/F9 save/load. WASD and arrows move. All are remappable physical bindings.
- Input layer reports intent, **never** damage, inventory changes, story dispatch, physics movement or module effects. Consumers revalidate legality. Space becomes `confirm`, not `dodge`, in modal contexts. Primary is preserved as a menu confirmation intent.

## Scheduling and modal ownership

`Actions.set_context(mode: String)` accepts `gameplay`, `menu`, `dialogue`, `inventory`, `pause`. Presenter owns modal context and routes menu inputs. Gameplay `get_move()` and `focus`/`dodge` are suppressed outside gameplay. After a modal boundary held movement must return neutral before resuming; no latent drift or surprise new camera heading. Modules must not run gameplay effects while presenter `simulation_enabled` is false or input context is not `gameplay`.

Optional names: `move_left/right/up/down`, `confirm`, `nav_up/down/left/right`, `camera_left/right/up/down`, `camera_cycle`, `dev_toggle`, `dev_pause`, `dev_step`, `dev_slow`, `dev_input`, `dev_perf`, `dev_record`, `screenshot`. Fixed camera rooms disable nudging; inventory always keeps I. Free-look IJKL requires look modifier C (inventory suppressed only during explicit free-look).

## Provider seam (bots / deterministic tests / replay)

- `Actions.set_source(source: String)` = `live`, `bot`, `replay`; clears stale held/ramp state. Production defaults to live.
- `Actions.submit_frame(frame: Dictionary)` supplies the **next fixed-tick** sample for bot/replay. No Input.parse_input_event and no direct presenter dispatch. Omitted fields are neutral. A submitted frame is used once, then neutral unless submitted again.
- Frame v1: `{"digital":["move_up","primary"],"analog":[0.0,0.0],"buttons":[],"camera":[0.0,0.0]}`. `digital` contains canonical physical-action names, before hold/toggle/buffer transformations; `buttons` contains canonical gamepad button actions. Analog is raw unit-square left-stick input, not a desired velocity. Both providers pass the **same** normalization/ramp/edge logic. Inputs are recorded post-device sampling, never inferred intentions.
- `Actions.advance(frame: Dictionary)` is the single-tick reducer for isolated tests only; do not call it in a running tree with automatic sampling enabled.
- `Actions.consume_buffer(name: String, legal: bool, contact_tick: int = -1) -> bool`: consumes a six-tick buffered primary/secondary/dodge edge exactly once when legal. Optional recent authorized contact supports explicit authored coyote actions; it does not grant traversal or bypass story guards. `tick` is the sampler's integer clock.
- `Actions.snapshot() -> Dictionary`, `Actions.restore(snapshot: Dictionary)`: replay/checkpoint hidden input state, including ramps, opposite-key ordering, toggles, held edges and buffers.
- `Actions.binding_glyph(name: String) -> String`: short active-device label; do not hard-code E in prompts.

## Movement/module seam

Presenter exposes `actions` (the singleton), `player`, `simulation_enabled`, and legal story `dispatch(id)` unchanged. Player exposes `direction(input)`, `camera_cut(basis)`, `velocity`, `position`, `camera_basis`, `latched_basis`, `latched`, `last_input`, `enabled` as before. `player.focus_point` is a nullable world target; focus never replaces fixed-room camera anchors. Modules own combat/course rules and must not duplicate keyboard bindings or the locomotion controller.

**Integration status at first commit:** API and headless-tested neutral/edge skeleton published. Full remap, virtual stick, buffering, modal policies, runtime consumer wiring and replay follow in this lane. The required three getters and required action names will not be renamed. No combat implementation is claimed here; R10 needs module integration or a clearly labeled contract fixture, not a fabricated shipped combat pass.

## Implemented integration notes

- Processing order: sampler **-100**, presenter/context/toolbelt **-50**, player **0**, actor pose bridge **10**, movie checkpoint **100**. Put gameplay consumers after the presenter and before the movie, and check both `presenter.simulation_enabled` and `Actions.context == "gameplay"`. Dev pause/slow/step deliberately gates simulation without changing 60 Hz input sampling.
- `presenter.replay.register_state(id, capture, restore)` registers deterministic module state before recording/playback. Callbacks must capture/restore every gameplay variable, including timers and local seeded RNG state. Extension IDs must match when loading; callback owner scripts are included in the build hash. Do not change module state from render callbacks. Module-specific state validation is the module's responsibility.
- `player.facing_yaw` / `player.set_facing_yaw(value)` is the authoritative facing scalar; the capsule stays axis-aligned and only the visual rotates. Reading `player.rotation.y` is not a facing API. Position is snapped in the simulation to the configured 0.1 mm grid after collision.
- All current benchmark bots use `submit_frame` with one-tick press/release separation. The older direct story-witness validator remains a logical checker, not evidence of physical play.
- Movie headers contain version, 60 Hz tick rate, exact game/build/engine hash, seed, profile and initial state. v0 is same-build/same-machine evidence, **not** a cross-platform physics guarantee or a rewind system. First divergence is reported at a recorded checkpoint (every 60 ticks and final tick), not necessarily the earliest differing individual tick.
- Current controls, motion, remap, contextual, animation, replay and benchmark results are in [CONTROLS-RESULT.md](CONTROLS-RESULT.md). Real combat/course R10 and its failure/reset semantics remain a composition test for Main and the module-runtime owner.
