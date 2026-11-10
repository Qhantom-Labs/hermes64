# FEEL2 Shift-to-run — input lane

## Integration contract (implemented; parent integration remains)

Owned files: `runtime/godot/input/{actions.gd,profile.gd,defaults.json,hud.gd}`, input tests, this document. No presenter/player/camera edits. Execution header: **gpt-6.1-sol**, **openai-api** (OpenAI API); no fallback observed. Commissioned reasoning: xhigh. Parent owns `FEEL2-MODEL.md`.

- Default `run_mode=hold`: unmodified movement settles at **0.65** normalized intent (comfortable jog/walk); hold **Shift** (`run`) for 1.0. Release returns to 0.65. The existing player speed curve consumes this without needing a new movement executor.
- **Alt** holds old `walk` precision, capped at existing 0.35; precision wins over run. Ctrl is not precision or focus. Z remains default game focus.
- `auto`: unmodified full-speed intent; `hold`: Shift-held full speed; `toggle`: each fresh Shift press toggles full speed. Old `walk` stays hold-only precision for modern profiles in every mode.
- Both handed presets bind Shift to `run`, Alt to `walk`; right-hand dodge becomes Space to avoid the previous Alt collision. Right-hand focus remains `/` and secondary remains Ctrl.
- The jog ceiling applies to keyboard and pad intent; lower analog magnitudes are not rescaled. No existing pad button was taken over: remap `run` or choose `auto` for full pad-stick speed.
- New `run` action is appended; all old action IDs remain. Full recorded legacy profiles (all original bindings and no `run`) keep the original auto/hold/toggle reducer and byte-identical action snapshots. A partial remap is modern, not an implicit legacy opt-out.
- New snapshots include `run_toggle`; legacy snapshots must not grow new keys. Movie schema/build guards remain unchanged. Old cross-build checks must still rebind only the build header in a test helper, never frame/state/hash payloads.

### Required parent presenter integration

`presenter.gd:pause_settings()` currently cycles `run_mode` on `actions.just_pressed("walk")`. Change the **modern-profile** branch to `actions.just_pressed("run")`, matching the HUD's Shift run row. Keep the `walk` branch for a profile whose `bindings` does not contain `run` so old settings-movie frames retain their semantics:

```gdscript
var run_setting_action := "run" if actions.profile.bindings.has("run") else "walk"
if actions.just_pressed(run_setting_action):
    cfg.options.run_mode = {"auto":"hold","hold":"toggle","toggle":"auto"}[cfg.options.run_mode]
    changed = true
```

Label/legend: **Shift — Run: hold / toggle / auto**; **Alt — Precision walk (hold)**. Resolve labels through `binding_glyph`, not hard-coded key names. This lane updates the input HUD only; presenter menu text, README/PLAY and export/browser integration remain parent-owned.

Player integration: preserve the magnitude contract and the legacy-profile speed curve; do not reinterpret old `walk` frames as run. New `jog_modifier_cap` is an input ceiling, not a replacement for module speed limits, focus limits or collision rules. No camera action/binding change is part of this feature.

### Additional parent integration / limits

- A legacy replay's handed-preset change must retain **legacy binding defaults** (old Shift precision and right-hand Alt dodge), rather than unconditionally erasing `cfg.bindings` and selecting modern defaults. The tested old movie does not visit that settings path. The modern preset path should continue to use the new defaults.
- `input/movie.gd:valid_initial()` should validate **optional** `actions.run_toggle` as bool when present; absence must stay valid for legacy states. This lane serializes/restores the new latch but does not edit the movie validator. Malformed new-latch movie rejection is not claimed.
- Parent owns merged-branch suites, presenter settings acceptance, browser/export/native checks, README/PLAY labels and human feel. Input tests inject actual `InputEventKey` events into Godot's InputMap, not native OS key delivery. HUD wiring/glyph tests are not screenshot approval. No game data, combat/course/puzzle executor, player, presenter or camera file was edited here.

## Live saved settings versus movie profiles

Only `Actions.load_remap()` upgrades a complete pre-FEEL2 saved profile. Old
default Shift/Alt/I bindings become Shift run / Alt precision / U pitch and V
recenter; the former default auto mode becomes hold (hold/toggle remain).
Explicit remaps survive: a new action selects an unused fallback if its default
key is occupied. The load does not rewrite saved bytes. Esc settings then saves
the modern form normally. `configure()` / movie profile decoding never run this
migration, preserving the original 213 input snapshots exactly.

Independent spec review found this live-settings seam; the new
`controls_saved_upgrade` test first failed seven assertions and then passed all
14 initial checks, then 18 including crowded/all-occupied remaps. A real occupied
key exhaustion returns the complete original mapping and an explicit warning,
never silently replacing it with defaults. Modern orbit commands are separately excluded from canonical input snapshots
and cannot select the pad movement device. `controls_orbit_input` compares 60
identical movement streams with/without orbit keys/right-stick commands (120
assertions), without changing historical movie action IDs.

## Verification

Godot **4.6.2.stable.official.71f334935**. Evidence is isolated under `evidence/feel2/run/` (local, gitignored), never shared LIVEFIX staging. The runtime is the untouched `7edc26fd` controls fixture overlaid only with this lane's input files and controls tests, not a claim that concurrent parent/other-lane changes passed.

| Receipt | Actual result |
|---|---|
| `baseline-controls-01.log` | All nine original controls suites passed before changes. |
| `legacy-capture-01.log` | 213 snapshots captured from the original reducer across auto/hold/toggle. Golden fixture: `tests/fixtures/feel2_legacy_input.json`. Preservation control, not RED. |
| `attempt-03-controls_run.log` | Behavioral/wiring RED: 79 checks, 47 failures on old input. Old-snapshot preservation control passed separately. |
| `attempt-08-controls_remap.log` | Separate persistence RED: full left/right saved profiles failed reload with `invalid pad axis`. Fixed exact integral ±1 validation after JSON turns signs into floats; invalid signs remain rejected. |
| `attempt-09.json`, `attempt-09-*.log` | **12 suites pass**, exit 0, clean stderr: nine existing suites plus run, legacy and run-movie suites. Run 79 checks; remap 34; legacy 218 checks / 213 exact snapshots; run movies 47 checks. |
| `attempt-09-controls_run_movie.log` | New hold/toggle/auto movies: 180 ticks each, strict playback twice. Old pre-FEEL2 movie: 240 ticks / four original checkpoints, twice; only test-memory build header rebound. Frame, initial-state and expected-hash payloads/file bytes unchanged. |
| `attempt-09-controls_matrix.log` | 20 handed-preset cases, each recorded and replayed twice, all equal; R10 remains the existing dummy fixture, not a shipped-module acceptance claim. |
| `verification.json` | Programmatically aggregated counts, scope and exact input SHA-256 values. |

Earlier parse/fixture-loader attempts remain under their original names and are **not** counted as RED/GREEN. Existing full-speed input/motion/collision checks now explicitly select auto-run, so the slower default cannot silently lower their stress; the R01 reach assertion also rejects the old `-1` sentinel. Default hold-run is tested separately.

Local repeat (fresh evidence label required):

```sh
/usr/bin/python3 -B evidence/feel2/run/run_suites.py <fresh-label> --refresh-input \
  controls_run controls_run_legacy controls_run_movie controls_api controls_input \
  controls_remap controls_motion controls_collision controls_context controls_movie \
  controls_animation controls_matrix
```

For **merged** verification, parent should use its own freshly staged current runtime and explicitly include the three new suites; `tools.controls_acceptance` still enumerates only the original nine. Do not reuse this lane's baseline fixture as final all-lane acceptance.
