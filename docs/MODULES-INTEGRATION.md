# Runtime and tool handoff for STORY 1.2.0

**Owner of this handoff: Hermes Main.** This lane supplies data/compiler/checker/checkpoint/edit contracts only. Nothing in this document authorizes a write to the visual lane, a runtime launch, a plugin install, a service restart, an independent review waiver or remote publication. The supplied Python data facade is exercised locally; the installed Hermes loader and the Godot module executor are **not_run**.

## Version boundary and files

Read `MODULES-CONTRACT.md` and `MODULES-PROOF.md` before integration. `contracts/gameplay/1.0.0/` is generated from trusted Python definitions. Only STORY `1.2.0` enables modules. `module_contract` carries schema/implementation pins and explicitly says `runtime_status: not_implemented`. Future runtime acceptance must bind a real executor version/resource digest in a separate receipt, not rewrite the compiler's marker to fabricate existing evidence. Do not widen a 1.1 save validator or put new mechanics into old free-form metadata. Ordinary 1.0/1.1 results must retain their exact hashes/actions.

New implementation: `story/modules/{schema,registry,validation,compiler,model,analysis,reference,course,events,save_codec,edits}.py`; facade: `adventure_modules/{schemas,service,tools,benchmark}.py`. Existing aggregate compile/build/replay services are deliberately not forked. Old runtime gates may refuse 1.2; do not remove that refusal until the runtime lane supplies parity/physical acceptance.

## Required host state machine (future Godot implementation)

- Authoritative shared core state remains location, inventory, flags, dialogue, tide/tick and collected IDs; add the finite module state exactly as documented. Persist only ready checkpoint state. Never resume live enemy actors, HP, animation/frame timers, velocity, target handles, a countdown or partial course progress from save v2.
- `ready -> active -> completed` grants declared rewards atomically once. `active -> failed -> ready` returns to the challenge's safe checkpoint, destroys transient actors/events, restores health and clears attempt state; permanent tokens/abilities/completions/discovery remain. An explicit abort is a failed attempt followed by reset, not a victory.
- Recheck entry conditions, room, dialogue/modal ownership and one-active constraint before starting. No ordinary story action may inject a completed challenge. `assume:*` action IDs belong only to the Python analysis harness and must be rejected by production dispatch.
- Completed IDs are monotonic and prohibit restarting/reward replay. A terminal ending must not suppress a pending failure/retry. No save during active/failed attempts. Validate source/build/module pins on load; reject unsupported migrators rather than guessing remaps.
- Increment a host-owned attempt generation on start/reset/load/scene unload. Scope event producers to the active scene and attempt. Clear pending input/events when releasing ownership. Shared state mutation belongs to the host, not individual enemy/trigger/animation nodes.

## Events, observations and idempotency

`events.json` and `story.modules.events.validate_event(game, event, active, attempt, last_sequence)` define a **data observation validator**, not authenticated gameplay or a reducer. The closed envelope is `{api_version, build_hash, challenge, attempt, sequence, physics_tick, kind, payload}`. Build pins must match; challenge/attempt must be current; sequence must be fresh and contiguous. Rejected/stale/duplicate observations must have zero effect. The host can discard an already-seen terminal notification idempotently; it must never grant another reward. Successful shape validation by itself is not a physics receipt.

| Kind | Closed payload | Additional host responsibility |
|---|---|---|
| `combat_completed` | every declared `defeated_spawns` ID, `player_alive: true` | Validate trusted hit/death records, all waves, live player; simultaneous player/enemy death resolves to failure, not completion. |
| `combat_failed` | reason `player_defeated` or `aborted` | Resolve outcome exactly once and begin safe reset. |
| `course_checkpoint` | checkpoint ID, zero-based index, elapsed ticks | Consume only the next ordered trigger and prove crossing from the real controller. Duplicate or out-of-order crossings cannot increment progress. |
| `course_completed` | exact ordered checkpoint ID list, elapsed ticks | Check actual observed history, deadline and same-attempt clock; the data validator also rejects missing/reordered IDs and durations below the necessary geometric minimum. Par is optional performance target, not the deadline. |
| `course_failed` | reason `deadline` or `aborted` | Reset countdown/progress/clock without changing permanent rewards. |

`physics_tick`, source authorization, observed checkpoint history and monotonic elapsed time are host-owned facts. The pure validator does not authenticate or infer them. Bind observations to a real executor/input receipt before claiming physically tested. Animation or render callbacks are never authoritative damage or timer events.

## Control, animation and timing arbitration

One control router owns player movement/actions. Priority: load/transition/death reset > pause/modal/dialogue > active challenge > normal exploration. Starting challenges during an open dialogue is prohibited. The future runtime must freeze challenge timing on pause/modal/transition, clear held input at ownership changes, and require a fresh edge for confirm/attack. A menu confirmation cannot also start an attack. Damage/death reset cancels attacks before returning exploration. This lane has not exercised those UI/device behaviors.

Use a single physics clock at 60 Hz for course countdown/deadline and combat windup/active/recovery. Physics state, not pose playback rate, decides movement, damage windows, invulnerability and course success. For an attack started at tick T, damage window is the half-open interval `[T + windup, T + windup + active)`; recover until the sum of all durations. Each attack-instance/target pair can damage only once. Hit validation must use admitted range/LOS/collision; no damage through a wall or to a freed scene target. If both sides die on a tick, resolve failure first. Bounds on data are not runtime collision tests.

Trusted enemy templates: `melee_approach_v1` idles until aggro, approaches until attack range, telegraphs, attacks, recovers, and respects leash; `melee_dash_v1` uses the same states/windows but commits a bounded dash toward its latched target during the active window. Hurt/dead pre-empt attack and cancel hit eligibility. Exact acceleration, target-lock/LOS and dash collision behavior need runtime tests; do not label them verified from this data contract. Wave N+1 starts only after wave N is cleared, preserving the simultaneous cap.

Required character animation clip names: **`idle_combat`, `swing`, `hurt`, `death`, `roll`, `block`**. Existing walk/idle clips remain exploration dependencies. Combat ownership must prevent the locomotion bridge from overwriting swing/hurt/death/roll/block. Attack state controls clip selection; clip clocks never control gameplay. A missing required clip is an explicit unsupported/failed runtime binding, not an idle fallback. Bind original assets/rig/socket/cue versions through the existing character/style/audio contracts; this lane supplies no new visual or audio files and prescribes no single look.

## Regions and timed traversal

Keep one region scene loaded. Door conditions are the only gate source; `regions.links` binds reciprocal endpoints to their authoritative room doors. Before transition commit, validate target scene and checkpoint collider clearance using the production controller. On load failure retain the prior room/state. Scene unload cancels all scoped enemies, targets, attacks and course events. Landmarks are data anchors, not guaranteed reachable terrain. No seamless streaming, fast travel, mounts or vehicles are implemented.

Course checkpoints are closed spheres in source order. Start timer only after the configured countdown. Sweep the player's real movement segment across the next expected sphere so high-speed crossings cannot be lost by overlap-only tests; reject shortcuts/reordered gates. Count one lap. Deadline bounds completion; par may label performance. Countdown, elapsed time and checkpoint history are transient and reset on retry/load. The current metric check assumes maximum straight-line speed without collision/acceleration and cannot certify physical feasibility.

## Exact plugin merge lines (NOT applied here)

Registration is implemented in new `adventure_modules/tools.py` using only public `ctx` APIs, with five schemas in `adventure_modules/schemas.py`. Tests register them against a recording context and invoke real local handlers. To expose them after Main's integration review:

1. In root `__init__.py`, immediately after the existing import, add:
   ```python
   from .adventure_modules.tools import register_tools as register_module_tools
   ```
   In `register(ctx)`, immediately after `register_tools(ctx)`, add:
   ```python
   register_module_tools(ctx)
   ```
2. In JSON-compatible `plugin.yaml`, append these exact strings to `provides_tools`, preserving every existing name:
   ```json
   "hermes64_modules", "hermes64_module_add", "hermes64_module_edit", "hermes64_module_check", "hermes64_module_benchmark"
   ```
   No config, dependency, hook or capability addition is needed. Existing `projects_root` is required; no implicit home-directory or bundle writes. This lane does not rewrite the legacy public description or claim native genre support.
3. No mutation of `adventure_maker/schemas.py` is needed with dual registration: the new module owns its five schemas. Do **not** merge them into the old `register_tools` loop without also routing handlers to `ModuleService`; the old `Service` intentionally has no module operations. If an integrator chooses a single schema catalogue later, it must pair schema merge and dispatch change, retain the old action behavior and rerun registration tests.
4. The existing benchmark remains unchanged for legacy tools. `adventure_modules/benchmark.py` extends the same sequential candidate/locality/save contract for module edits through `hermes64_module_benchmark`. Its full-verification count stays zero. Do not make the old benchmark's runtime pass gate conditional merely to accept these data receipts.

No existing plugin wiring lines were changed in this worktree. These are explicit integration instructions, not a claim of installed tool availability. The old baseline registration test remains intact.

## Transaction sequence and scope

Choose an existing owner-approved absolute projects root and a managed project. Place STORY 1.2 JSON in `source/spec.json` through the normal authorized file workflow. `hermes64_module_check` with `adopt: false` writes an immutable report candidate, not a pointer. For first data adoption pass both expected hashes as empty strings; subsequent adoption requires exact hashes from the existing data revision. Pass `adopt: true` only for intentional data adoption. Exact shape: `{project, spec_path, adopt, expected_spec_hash?, expected_game_hash?, max_states?}`.

For `module_add`/`module_edit`, pass `{project, operation, expected_spec_hash, expected_game_hash, save_path?}`. Add permits only `add-enemy`/`add-ability`; edit accepts the closed operation union. `module_benchmark` substitutes an operation list for `operation`; every row needs explicit expected rooms and a supplied starting save to count as data-verified. `hermes64_modules` takes `{action: list}` or `{action: inspect, id}`; it is read-only discovery.

The facade reuses project path validation, duplicate-key/nonfinite JSON rejection, cooperative locking and atomic writes. Paths are project-relative; traversal, symlink/hardlink escapes and shell-shaped input reject. Read source/build pins under the lock, write immutable spec/game/proof/diff/migration payloads, preflight response/report IO, and commit **one** `.maker/modules/current.json` pointer last. Read back that exact pointer. No runtime/verified pointer advances. Failed candidates and partial artifact directories are diagnostic only; current source is never overwritten. Cooperating writers must use the same project lock; this is not protection against a malicious process changing files behind the lock.

## Required next-lane acceptance

If adoption readback fails, the facade attempts to restore the exact previous
pointer bytes and verifies that restoration. If storage also prevents rollback,
it reports `COMMIT_UNCERTAIN` and requires inspection; it does not claim rollback
succeeded. A power/storage failure is not something an application can certify
away. Prepared report files describe the attempted candidate; the actual pointer
is authoritative for adoption.

The current full fast-suite blocker is detailed in `MODULES-BLOCKED.md`.
The retained starter-sketch style lock pins the baseline story source bytes;
commissioned source changes correctly invalidate it. Its manifest/lock were not
within this lane's write scope and have not been refreshed. A disposable-copy
control explicitly creates a new data-pending lock and verifies it, while
preserving both source files and the tamper rejection gate. Main must own the
real lock revision and rerun the unchanged raw suites after composition. Do not
count the isolated copy control as a pass for the currently pinned starter.

Implement/test reducers against these exact data bytes first; then production input, defeat/retry, resource/duplicate-event controls, same-build checkpoint parity, region collision/load rollback, real course crossings and frame/pose-rate independence. Request original action clip/cue assets from the proper owner, preserving visual holds. Run native/full retained suites, then actual authorized Hermes loading and independent review. Until those receipts exist, preserve every `not_run` field and do not promote this prototype to runtime verified.
