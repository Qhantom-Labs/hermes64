# STORY 1.2 module runtime (MODRT)

Owner: Hermes Main. Executor: bounded MODRT lane, `gpt-6-astra` / `openai-codex`, assigned ultra (independent effort telemetry unavailable). Local Godot 4.6.2 / Python 3.9. No protected controls/player/presenter edits, network, installation or remote publication.

## Acceptance status

The native module mechanics and checkpoint reducer are implemented and exercised. The Reedland mixed fixture receives **PLAYABLE headless**, but its latest real-renderer report is **ROUGH** because the unchanged 33.34 ms steady-frame probe budget is exceeded. Its image style gate and visible geometry/draw-call budgets pass. This is **not a fully accepted rendered release**. Read `MODULES-RUNTIME-RESULT.md` and `MODRT-BLOCKED.md`; earlier positive render reports lacking the final timing instrumentation are superseded.

Modules are supported only for the exact build/runtime/resources covered by a **PLAYABLE** playtest report, and only in that report's stated scope. Balance is not proven. This branch does not certify installed plugin adoption, human feel, Windows, other machines or physical gamepads. The combat clips and their tick alignment are covered by the MERGE3 receipts (`docs/MERGE3-RESULT.md`); no human art or feel approval is claimed.

## What runs

- `core/module_runtime.gd` reproduces the finite STORY 1.2 reducer, conditions, ability unlocks, one-shot reward identities, discovery and challenge lifecycle. Ordinary dispatch never exposes `assume:*`. STORY 1.0/1.1 retain their legacy reducer/save paths.
- `modules/host.gd` owns one active attempt, a generation counter, fixed physics ticks, pause, outcome, reset and local event signals. Damage/course progress come from the trusted executors, never animation callbacks or user-authored code. Completion is atomic and duplicate terminal calls do nothing.
- Combat: nearest-visible focus selection with stable held target, frontal melee windup/active/recovery, per-swing target deduplication, occlusion checks, dodge windows, collision-resolved impulses, health/hurt, simultaneous KO failure, bounded waves and deterministic feedback RNG. Block is enabled **only** when the current player actor actually contains `block`.
- Reed Warden uses `melee_approach_v1`; Cairn Dasher uses `melee_dash_v1`. Cairn Keeper is a larger, higher-health/timing **elite data variant**, not a separate boss framework (it is drawn with the Cairn Dasher model at 1.12× scale). No ranged/lobbing template is admitted by the existing schema; none was invented, and the combat-art `reed_burr` projectile is imported but unbound.
- Defeat and abort destroy transient actors and restore checkpoint readiness after 60 fixed ticks. Cross-room abort recovery is covered. Permanent rewards/abilities are retained. Exit actions disappear during an active encounter. Arena coordinates bound movement; this is not a general navmesh or ledge solver.
- Regions: finite reciprocal door graph, authoritative core ability/item guards, physical approach, twelve-tick stepped dark transition, hidden destination preflight and capsule clearance check before committing. Failed arrival preserves the previous finite state. One visible region is active; the temporary hidden preflight room is also resident during validation. This is **not seamless streaming**.
- Courses: on-foot native mover, countdown, ordered forward swept-sphere crossings, deadline, par display, overspeed/teleport invalidation, retry and ghost-free UI. Par is advisory; the deadline is the success limit. No vehicle, opponent, lap-racing or record economy is claimed.
- `modules/hud.gd` uses the existing small glyph font, health bars, focus chevron, numeric timer/checkpoint count/par, checkpoint icon, restrained edge flash and stepped fade. Contact feedback uses the already hash-checked `interact` audio binding (the selected pack's `ui.select` cue); differentiated telegraph/death sound design and listening approval remain future work.

## Authoring and reproducing

1. Author only the closed STORY 1.2 schemas in `contracts/gameplay/1.0.0/` and the documented contracts. Abilities and challenge host are mandatory dependencies. Door conditions, not region links, own gates. Use supported approach/dash templates, contiguous bounded waves, one active challenge and safe floor-height checkpoints.
2. Start with `examples/gameplay-reedland-runtime/{spec,game,proof,save}.json` or `examples/gameplay-reedland-regions/`. The mixed example has exploration, an original dialogue choice granting the field action, three outdoor zones, an arena/key reward and a timed course. These are JSON games, not bespoke per-game scripts.
3. Compile/check through STORY. A challenge proof remains `conditional` (CLI exit 4), not `proved`. Do not change the compiler's `runtime_status: not_implemented` marker: the separate physical receipt binds this executor.
4. With an **already installed** numpy/Pillow interpreter, run from this worktree:
   ```sh
   python3 -B -m tools.modrt_demo UNIQUE --python /absolute/existing/python
   python3 -B -m tools.modrt_demo UNIQUE-RENDER --render --python /absolute/existing/python
   python3 -B -m tools.modrt_style UNIQUE-RENDER
   ```
   `--kind combat|course|regions|mixed` reuses the same host/executors. `--control strong_arena|high_checkpoint|region_softlock` makes real bad data. Every run requires a fresh evidence folder; never overwrite a failure receipt. The style helper is visual coverage by teleported room state, **not** a reachability proof.
5. Open the staged project with `res://modules/main.tscn`, not the unhooked legacy scene. Combat input is neutral until an Actions provider is installed. The bounded bot uses native movement/menu key events plus the explicitly labelled Actions-compatible button stub; it is not evidence for merged remapping, device semantics or human play.

`adventure_maker/playtest.py` additively routes current STORY 1.2 builds through `module_playtest.py`. The standalone helper also runs without adopting any service pointer. Legacy checker/replay/build acceptance is not relaxed, and no module data pointer is promoted to a verified runtime pointer by these tools.

## Controls and animation seams

Use `runtime/godot/modules/host_interface.md`. The Controls API was read from the other lane, not copied or modified. The adapter consumes the three frozen getters after the input sampler, waits for neutral after provider ownership boundaries, and honors presenter `simulation_enabled` when present. The existing body owns camera-relative direction/ordinary locomotion; module impulses use collision sweeps. Do not install a second impulse consumer.

`actors/bridge.gd` now yields locomotion animation when `module_animation_owner` is true. Six exact NEW-CLIPS names are supported: `idle_combat`, `swing`, `hurt`, `death`, `roll`, `block`. **MERGE3 imported the combat art** (`docs/COMBAT-ART.md`): the 16 public combatants carry the six clips, `cairn_dasher` and `reed_warden` have their own models and seven-clip FSM sets, and the `trail_staff` is held on `hand_r`. The host shows every clip phase-locked to the fixed-tick state (hit window = swing keys 5-7, roll i-frames = keys 2-9; `host_interface.md`). An actor that lacks the clips (an animal protagonist, or a runtime staged without the art) still falls back to conspicuous **POSE TEST** rig poses; these are neither delivered action animation nor silent idle fallbacks.

Optional toolkit-owned `res://combat-bindings.json` has `api_version: "1.0.0"` and `bindings`, mapping `player`/archetype IDs to `{character_id, sha256}`. Each identity must resolve to an existing non-placeholder exact character manifest row containing all six clips, and its file hash must match. The normal actor resolver supplies rig, material, clip and asset handling. No STORY gameplay path or callback is allowed. Absent manifest means explicit prototype poses; malformed/present unknown or corrupt pins reject boot. The default art path is the staged `res://combat.json` described in `host_interface.md`.

## Checkpoints and evidence

Save v2 stores only the finite ready state at a committed checkpoint. Active/failed attempts, unknown fields, stale build/module pins and unreachable states reject. Membership uses the bounded abstract graph; it is not authenticated proof of played history. HP, targets, enemies, RNG state, attack clocks, course clocks and velocity do not resume from saves. Retry gives a fresh transient attempt. Loading invalidates the generation and clears input.

Physical reports pin game, runtime files, bound resources/audio and recorded input bytes. `proof-with-physical.json` fills only `evidence.physically_tested_by_bot`; logical assumptions and human evidence are unchanged. Each simulation sample records button intent, movement input, actual player position and module state hash. The two final headless repeats have byte-identical traces. This is same-engine/same-host evidence, not cross-machine determinism.

## Honest limits

- Human readability/feel/balance are not tested. The fixed camera leaves the near course start at the lower frame edge; captured combat actors are small. The style gate is an automated image defect gate, not artistic approval.
- Latest rendered performance is still over budget. All-frame timing and steady samples are both retained; boot/load/route/capture/mesh-readback periods are explicitly marked. No threshold was raised. These monitor samples are not a GPU/device FPS certificate.
- Region preflight supports bounded flat floor-height checkpoints; it does not certify arbitrary hills, jumping, inaccessible scenic geometry or asynchronous streaming. Landmarks may be scenery.
- No external event-injection surface exists. The local `story_event` signal is host telemetry, not an implementation of an untrusted/network event transport. Generations are local attempt invalidation, not authentication.
- No ranged combat, production boss phases, scarce ammunition, consumable economy, free-form FSM scripts, seamless world, fast travel, mounts, vehicles, ghosts, multiplayer or replay authenticity claims.
- Tests cover selected adverse mechanics and lifecycle paths, not every combination in the research packet. Real clip/pose-rate integration is covered by `tests/merge3_combat.gd` and the bot's `combat_clips` audit (MERGE3); physical gamepad behavior and human review of the combined controls/art still need receipts.
