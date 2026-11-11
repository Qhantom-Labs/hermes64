# Controls — keyboard first

**Default scheme** (all physical bindings can be remapped):

| Input | Action |
|---|---|
| WASD or arrows | Move relative to the current camera. Brief taps make small steps; holding ramps into a run. |
| Shift | Precision walk. |
| E | Primary action at the nearest reachable legal target. |
| Q / Backspace | Secondary action / cancel / release Focus. |
| Hold Z | **Focus** on a nearby interactable: retain it within reach and gently turn toward it. Fixed room camera anchors stay fixed. |
| Space | Dodge intent for combat/course consumers; confirm in menus. This lane does not implement combat. |
| Esc | Pause/settings; Esc again resumes. |
| Tab | Full legal-action menu, four visible rows at a time. Move up/down to select; E, Space or Enter confirms. No actions are dropped. |
| I | Inventory; left/right selects; Q closes. |
| F5 / F9 | Quick-save / quick-load; a small checkpoint glyph confirms success. |
| Hold R, 0.6 s | Retry from the current checkpoint. |
| C | Optional authored camera-anchor cycle. Never required for progress. |

A small **key glyph + verb icon** appears beside a target, not a control sentence. Prompts fade after three uses of that verb and return after an idle interval. Games made by `/hermes64 new` (UI5) instead show the keycap + the target's type icon (door, take, talk, lever, look) whenever E would act, at a whole-pixel scale, fading only when out of reach, plus a corner keycap strip (move, E, Space) at start that fades after the first step or 8 s; see `UI5-HUD.md`. Story dialogue is separate from control prompts. Releasing all movement after a menu avoids stale held-key movement. Holding through camera cuts preserves world direction until release or a deliberate direction change.

## Preferences / remapping

Esc shows every control as keycap + icon + one word (left column) and, on the right, Resume plus the four settings with their current value, drawn at a whole-pixel scale outside the low-resolution frame. In Esc settings: E toggles hold/toggle Focus; Shift cycles auto-run / hold-to-run / toggle-precision; Q toggles reduced motion; Tab switches left/right-hand presets. These changes persist for live play. Reduced motion preserves fixed cameras and has no camera shake/bob to disable in this runtime.

The default **left-hand** preset uses the table above. **Right-hand** uses arrows, Shift, Enter primary, Ctrl secondary, `/` Focus, Alt dodge and Backspace action menu. Keyboard hardware ghosting and physical pad behavior still require hands-on testing.

Full binding/config overrides live at `user://hermes64_input.json` (Godot's per-user application directory). Example: `{"version":1,"bindings":{"primary":[{"key":70}]},"options":{"focus_mode":"toggle"}}` maps primary to physical F. Pad bindings use `button`, or `axis` plus `sign`; saved remaps are validated atomically. Invalid/unknown/duplicate bindings, malformed files and out-of-range tuning fall back to safe defaults; the input provider exposes `config_error`. Edit while the game is closed, or use the validated `save_remap` API. Never edit a shipped game's story save to remap controls.

Bonus pad: left stick has a radial dead zone and true analog magnitude; south primary, east cancel, left trigger Focus, right shoulder dodge, north action menu, Start pause, D-pad up inventory. Back + right/left shoulder saves/loads. Device-neutral button labels use `B<number>` / `T<number>`, not branded controller artwork. IJKL/right-stick nudges are suppressed in fixed-camera rooms; no camera input is required.

## Development and replay

Exports keep development tools off unless explicitly enabled with `--dev=1` (after Godot's `--`), or `hermes64/dev_enabled`. In an editor-capable runtime, Ctrl+Alt+F1 toggles the toolbelt. **P** pauses simulation; **.** advances exactly one simulation tick; **F6** toggles quarter-speed tick gating; **F2/F3** show input/performance; **F12** captures a screenshot; **F4** starts/stops an input movie. Esc remains the settings pause. None uses variable physics delta or `Engine.time_scale`.

`--record FILE --seed 7` records; `--replay FILE` validates and plays a movie, exiting nonzero on the first divergent checkpoint. Replay requires the exact game/build/engine and recorded profile. Playtest reports include their winning/explorer movie paths. See [API](CONTROLS-API.md) for module and bot contracts; [results](CONTROLS-RESULT.md) for measured tuning, commands and limitations.
