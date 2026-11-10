# Runtime integration interface — contract 1.0.0 / 1.1.0

Owner: Hermes Main. This lane implements a **Godot 4.6.2 gameplay runtime layer**, not a new engine. No editor import, templates, network or package installation needed for primitive presentation.

## Launch / ownership

From `lane-runtime/`:

```sh
sh tools/godot.sh -- --game=/absolute/path/to/game.json
sh tools/godot.sh --headless --script res://tests/checker_replay.gd -- /absolute/game.json /absolute/check.json
sh tools/godot.sh --headless --script res://tests/replay.gd -- /absolute/path/to/replays.json
```

Use absolute data/output paths: Godot changes its working directory to the project. HOME/TMP/cache paths are constrained to this lane by the shell wrapper. Writes stay here. Default interactive game is the current STORY Thaw, falling back to Last Light. Source/compiled integrity validation belongs to the STORY compiler; the runtime consumes compiled dictionaries and rejects unsupported exact versions. Do not treat it as a replacement for `story validate_game` on untrusted/tampered files.

## Authoritative pure layer

`godot/core/runtime.gd` extends `RefCounted` (no Nodes, scenes, clocks, input or I/O):

- `configure(compiled_game) -> {ok, reason?}`. Exact versions 1.0.0 and 1.1.0; deep-copied initial state.
- `matches(conditions, state) -> bool`; `endings(state) -> [ID]` (multiple = ambiguity, never select the first).
- `actions(state) -> [{id,label,state,text,kind}]`, sorted by action ID. `state` is the hypothetical post-action state; enumerating actions is pure.
- `step(action_id) -> {ok, before?,state?,text?,endings?,ambiguous?,reason?}`. Illegal actions leave state unchanged. Reasons match Python's `action <id> unavailable at <room>`.
- `derived(state) -> {counts,follower_flags,quests}`. No independent mutable counters/follower flags. Preserve collected identities.
- Only `wait` changes cyclic clock tick. Render/physics frames must never do so. Wait/cancel work during dialogue, exactly like the checker.

`godot/core/save_codec.gd` is also scene/I/O independent. `pack(runtime)` produces only the versioned state and provenance fields. `load_into(runtime, save, max_states=20000)` checks exact types/IDs/keysets/hashes then proves reachable membership using actual runtime transitions. A target-directed search orders candidates; it never unions pickups or assumes count equivalence. Its only pruning is monotone identities outside the target. Success carries a real action witness. Unreachable rejects; a cap is **inconclusive** and leaves the session untouched. Changed hashes/version require external STORY migration, never resetting/guessing a new start. Optional timestamp objects survive a load/pack. Physical player XYZ is deliberately absent.

`wire.gd` handles Godot's JSON-number representation by restoring **integer tokens** to native ints before state comparison. It preserves `1.0` and `1e0` as floats, so strict save tick validation rejects them and opaque timestamp number types survive. Never compare unnormalised Godot JSON dictionaries against native int ticks as if a numeric-type mismatch were an effect mismatch. Runtime numeric representation is signed 64-bit integer / double; oversized integer tokens fail closed.

## Look plug-in seam

`view/presenter.gd` is replaceable; retain the pure core and the following action/state boundary:

- `boot(game, options)` constructs runtime, room view, UI and controller.
- `dispatch(action_id)` calls exactly one `runtime.step`, rebuilds room on location change, refreshes dialogue/inventory/followers/endings. Rendering never writes flags/inventory/tide.
- Signals: `room_entered(id)`, `camera_cut(id)`, `state_changed(result)`, `ending_reached(id)`.
- `refresh()` reads authoritative state; `capture(path)` awaits a real rendered frame and writes root UI PNG plus `-world.png` at 320x240. Headless returns false rather than hanging or claiming a screenshot.
- `save_game/load_game` own disk I/O only; save is temp-file + rename, load delegates membership to the pure codec.

LOOK may replace `view/room.gd`, `view/player.gd`, shader and UI wholesale. Do **not** reuse LOOK's provisional `game_state.gd`: its mini-game wire format/XYZ save differs from the frozen STORY contract. Use the original node/choice/ending text unchanged. `actions(state)` is the single legal-action source for contextual prompts and UI buttons.

Current presentation choices (not style acceptance): 320x240 world, nearest 2x output, readable high-resolution scrolling text/action sidebar; shader distance fog; room coordinates X east/Y up/Z south, one metre per tile. Theme colors, fog ranges, head-style and coat-color choices live in `godot/packs/<id>/view.json` (neutral default, polar_pod, ruins_harbor). Select from `metadata.style_pack`, or override with `--pack=res://packs/ruins_harbor/view.json`. Unknown pack uses the explicit neutral primitive fallback. The two themed presets are **presentation data**, not claims of complete kit/theme art; a second preset requires zero core-code changes once this seam exists. Authored character suit/hood params are preserved for a replacement visual adapter. `metadata.collectible_prop_ids` binds discoveries and character instances to authored prop positions and removes duplicate prop/actor proxies. Authored camera anchors are fixed; select nearest look-at target with 0.75m hysteresis, or cycle with C. Controller is camera-relative 8-way with held-input basis latch, following LOOK's read-only spike. WASD moves, Tab/Enter/click selects actions, Escape cancels graph, F5/F9 saves/loads, R restarts.

Geometry is not added as a new logical precondition. The complete legal room action list stays available even if placeholder geometry has no authored hotspot. This prevents an absent physical placement from silently changing the checker's semantics. The bot replays actions through `dispatch`, not a separate simulator; it does not prove geometric walkability or controller-based pathfinding.

## Kit seam / explicit placeholder boundary

Options: `asset_root=/absolute/root` for direct relative `.glb` refs, `asset_map=/absolute/map.json` for an explicit `{semantic_story_ref: absolute_glb_path}` map. Runtime GLTFDocument loads without mutating/importing a kit project. Missing refs yield visibly primitive placeholders and are listed in bot receipts. Do not silently map a default mesh to unbuilt costume/coat/seed variants.

KITS 2.0.0 contract was read. Its authoritative ready list is `lane-kits/kits/manifest.json`; early contract publication alone is not asset readiness. STORY currently names `expedition_base_v1/human_16` and `cat_base_v1/cat_8`, whereas KITS declares `char.expedition_figure/expedition16_v1` and `char.cat/cat16_v1`. Main must approve the mapping/variant translation. Room-shell origin requires half-width/depth offset; no world assembly is inferred from kit availability. Prop rotations are treated as **degrees**, matching Last Light's authored 90; the base contract should explicitly state the unit (see CONTRACT-FEEDBACK).

## Replay inputs

`PYTHONDONTWRITEBYTECODE=1 python3 -m tools.reference SOURCE_GAME OUTPUT_DIR [--exhaustive]` invokes the real STORY CLI `check`, snapshots the compiled game, then replays every report witness through the Python engine to record complete before/after state, full legal-action sets, labels and all unavailable action IDs with expected refusal reasons. The headless Godot replay compares these against real runtime logic. `--exhaustive` additionally checks every reachable state/edge (Last Light only; never brute-force Thaw).

Graphical bot: `sh tools/godot.sh -- --game=... --bot=.../replays.json --shots=...`. Bot receipts enumerate witnessed endings, all visited rooms, captures, save-membership checks, missing assets and measured frame intervals. Screenshot stalls and unpaced bot frames are not a shipping FPS benchmark.
