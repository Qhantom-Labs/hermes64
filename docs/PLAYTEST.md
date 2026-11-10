# Physical playtest

`hermes64_playtest` adds bounded physical evidence to the STORY proof. It **cannot judge fun**. It does not claim universal geometric reachability, GPU certification, perceptual style approval or identical floating-point traces across machines/engine versions.

## Tool

Arguments: `project` (existing project ID), `mode` (`winning`, `monkey`, `both`; default `both`), `seconds` (explorer simulation time, 1–120, default 30), `seed` (default 7), `drought_seconds` (1–120, default 20), `render` (default false). The project must already be compiled. SHIP tool registration is isolated until Main applies [SHIP-INTEGRATION.md](SHIP-INTEGRATION.md).

Headless uses Godot 4.6.2, fixed 60Hz fast-forward, production `CharacterBody3D` movement/collision, production action-menu input, and the checker's witnesses for **all reachable endings**, not an invented success route. A 0.5m AStar grid queries the actual physics space using a player-size capsule; steering converts world targets through the production camera-relative/latch rules. A route miss also attempts real steering, then records the failure rather than teleporting to an interaction. Normal production door transitions still change rooms/spawn as authored. The driver resets between witnesses, not mid-route. Camera latch/neutral probes and explorer C-key cuts are recorded.

The production contract allows legal actions in the room without proximity gating. This harness adds a 1.05m horizontal / 1.8m vertical arrival test for anchors **without changing production story semantics**. Dialogue choices and targets without anchors remain location-scoped and are listed. A mesh without a collider is not made solid by this harness. The grid is a bounded approach aid, not a 3D navigation proof for arbitrary multi-level/jumping games.

Explorer uses seeded WASD wandering, camera cuts and eligible action mashing. Repeated cells/no displacement are observations, not automatic claims of a softlock. `seconds` does not bound all winning-path simulation time; each target has a 2s no-route attempt / 40s route cap, and each process has a 180s wall timeout. Timeout is negative evidence, not a pass.

## Outputs

Under the selected project's `.maker/runs/playtest-<id>/`:

- `report.json`, `report.md`, `report.html`; reasons and explicit scope.
- `native.json`, proof, process argv/stdout/stderr/exit/wall timing.
- `inputs.jsonl`: sampled position/velocity/input/camera/latch/grounded state every six fixed ticks; not a full lossless input replay file. Discrete actions/events are separately timestamped in the report. Deterministic hashes omit wall/allocator/draw observations; repeatability is tested on the same host/version/mode.
- Per-room 0.5m density SVGs and `contact-sheet.svg`. These are **maps**, not screenshots or walkable-area percentages.
- With `render=true`, real room PNGs and `contact-sheet.png`; HTML embeds them. Rendering may be slower and visible; headless is the default.

Metrics include winning completion, script/crash/exit errors, stuck/loop spots, unreachable actions, logical softlocks from the existing checker, event droughts, first event simulation time, rooms/position coverage, camera input failures, triangle/draw counts, allocator start/peak/end, live object/resource/orphan monitors and exit ObjectDB/RID warnings. Geometry is sampled at room creation, after actions and once per simulation second; per-frame `Mesh.get_faces()` readback otherwise distorts the rendered test severely. Exit diagnostics are not proof of zero leaks. Headless draw/FPS values are `null`, not bogus zero-performance claims. Rendered frame cost comes from timestamp probes at global SceneTree priorities (`playtest/frame_probe.gd`): **frame work** = physics callbacks + physics step/deferred flush + process callbacks + RenderingServer measured render CPU, recorded for every frame (`timing.frame_work_*`, raw rows in `timing-samples.json`). Steady frames exclude the first 72 frames (1.2 s) after each room entry, reported separately as warm-up, and explicit harness frames (route grids, mesh/screenshot readbacks; listed in `timing.boundaries`). Frame work is CPU time, not wall frame time: GPU execution and present/vsync waits are excluded, and await-frame wall intervals (`timing.median_ms`/`p95_ms`/`max_ms`) and whole-probe throughput are reported separately. Godot's `TIME_PROCESS` monitor (the maximum over the previous wall second, including RenderingServer sync/present waits) is retained as `timing.monitor_*` for transparency only; it was the gate input before MERGE2 (the module lane's 37.2 ms steady p95), and on the same replayed frames its median was 22-47 ms while measured frame work had a median of 0.5-1.2 ms (`docs/PERF.md` T4). Collection/navigation overhead and fixed stepping make this a probe rather than a hardware benchmark.

Budgets: 6,000 triangles/room (existing cap), 256 draw calls/room and 33.34ms steady frame-work p95 on rendered runs (explicit SHIP probe budgets, not a promised device specification). A rendered run that produces no steady frame sample is ROUGH (fails closed); a negative control with a 40 ms busy wait in every frame rates ROUGH (`tools/merge2_gate_control.py`).

## Verdict policy

- **BROKEN:** nonzero/crashed/timed-out process, script/runtime errors, or rejected logical proof, even if a physical witness completed.
- **ROUGH:** proof inconclusive, incomplete winning witnesses, stuck/unreachable/input/missing-asset failures, measured budget breach, or exit leak warnings.
- **PLAYABLE:** bounded paths pass but renderer/coverage, location-scoped actions, droughts or explorer observations limit confidence. Headless cannot get SOLID.
- **SOLID:** all requested bounded paths and rendered gates pass without those caveats. Still not a judgment of fun.

## Reproduce and test

```sh
/usr/bin/python3 -B -m unittest tests.test_ship tests.test_ship_native -v
/usr/bin/python3 -B -m tools.ship_probe my-last-light --example last_light --build
/usr/bin/python3 -B -m tools.ship_probe my-thaw --example thaw --build --render
```

Probe labels create new evidence directories; use a new label per run. Known-bad native tests cover a physically unreachable key (while the story proof remains proved), a real collision enclosure, a deliberate real GDScript error (even though its witness succeeds), and an irrevocable logical softlock. Controls live only in fixtures/playtest code and are excluded from release staging. Both bundled benchmarks retain their actual verdicts; no thresholds are loosened to make them pass.
