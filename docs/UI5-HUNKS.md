# UI5 shared hunks (for merges with FEEL4 / BFIX / others)

FEEL4 (`wt-feel4`, read at 90ee6802, no FEEL4 commits yet) has no key-glyph, prompt or controls-hint component, so
UI5 defines the shared one. FEEL4's arena controls hint should be a `moments` entry in
`runtime/godot/input/keyhud.json` (e.g. `"arena"`) shown with `key_overlay.show_moment("arena")`, drawn by the same
`input/keycaps.gd`; do not add a second keycap/hint system. Its arena games opt in with the same `metadata.hud` block.

## New files (no conflict expected)

- `runtime/godot/input/keycaps.gd`, `runtime/godot/input/key_overlay.gd`, `runtime/godot/input/keyhud.json`
- `runtime/godot/tests/ui5_overlay.gd`, `runtime/godot/tests/ui5_capture.gd`, `runtime/godot/tests/ui5_rooms.gd`
- `tools/ui5_proof.py`, `tools/ui5_rooms.py`, `tests/test_ui5_hud.py`, `docs/UI5-*.md`

## Edited shared files (dedupe here)

| File | Hunk | Likely overlap |
|---|---|---|
| `runtime/godot/view/presenter.gd` | `var key_overlay`; overlay created after `controls_hud` in `boot()`; added to the room-transition HUD gate list; `key_overlay.on_event(kind)` in `module_event()` | FEEL4 (camera smoothing / marker may touch `boot()` and `module_event()`) |
| `runtime/godot/input/hud.gd` | pause panel drawing removed (overlay draws it); `SETTINGS_CHOICES` removed; legacy prompt drawn only when `key_overlay.prompt_mode == "legacy"` | FEEL4 controls hint if it edits this file |
| `runtime/godot/tests/controls_run.gd` | run-mode row check reads `keyhud.json` instead of `SETTINGS_CHOICES` | none known |
| `runtime/godot/tests/controls_visual.gd` | `settings.png` captured from the window (`capture`) instead of the low-res frame | none known |
| `runtime/godot/tests/merge2_perf.gd` | `ui_off` also hides `key_overlay` | none known |
| `adventure_maker/newgame.py` | `starter_spec`: `spec['metadata']['hud'] = {...}` after `created_by` (one hunk; `asset_builder` untouched) | BFIX edits `asset_builder`/builder default in the same file: different hunk |
| `adventure_maker/export.py` | release copy allow-list (line 223) gains `input/keyhud.json`, so exported games ship the HUD data | any lane adding runtime data files: add them to the same tuple (`tests/test_ui5_hud.py` checks it) |
| `docs/controls-evidence/settings.png` | re-baselined pause golden (the only golden changed) | none |

Not touched: `/hermes64 setup`, builder defaults (`builders.py`, `asset_builder`), arena templates, camera code,
roof collision, any template's room dimensions.
