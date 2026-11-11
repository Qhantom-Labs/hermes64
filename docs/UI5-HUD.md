# UI5 controls HUD (data reference)

All key glyphs on screen come from one component, drawn at a whole number of physical pixels per UI pixel
(`P = max(1, floor(window_height_px / 240))`, so at least 240 UI rows), above the low-resolution world frame.
The world keeps its own frame and N64 bilinear upscale. Presentation only: nothing here enters simulation,
saves, movies or state hashes.

| File | Role |
|---|---|
| `runtime/godot/input/keycaps.gd` | Shared component: labels from the game's input map (`Actions.profile.bindings`), pad glyphs, keycap/icon/text drawing, fit/missing-glyph checks |
| `runtime/godot/input/key_overlay.gd` | Window-canvas overlay (CanvasLayer 2): pause menu, keycap interact prompt, corner hint |
| `runtime/godot/input/keyhud.json` | Data: pause rows, prompt icons per interactable kind, hint moments |
| `runtime/godot/input/hud.gd` | Unchanged legacy prompt (old games), checkpoint icon, dev overlays; no longer draws the pause panel |

## Per-game switches (`game.json` `metadata.hud`)

| Key | Values | Default when absent |
|---|---|---|
| `interact_prompt` | `keycap` (window overlay) / `legacy` (old low-res prompt) | `legacy` |
| `controls_hint` | `corner` / `off` | `off` |

`/hermes64 new` writes `{"interact_prompt": "keycap", "controls_hint": "corner"}` (`adventure_maker/newgame.py`).
Existing games, examples and golden/replay games have no `hud` block, so they keep the legacy prompt and no hint.
The pause menu is the same for every game. Test/proof override: boot options `ui_prompt=` / `ui_hint=`.

## Pause menu (`pause`)

Left column `controls`: what a key does in play. Row = keycap (current binding, active device) + icon + `word`
(the game's input-map action name). Rows whose action is unbound are skipped; `run` is skipped on legacy profiles.
Right column: `resume` (Esc), a settings icon, then `settings`: the key you press while paused (unchanged
behaviour: E focus mode, Shift run mode, Q reduced motion, Tab handed preset), an icon, and one word for the current
value from `words`. A value without a word is shown raw and reported in the layout's `unknown_values`.
`word_max_px` (44) bounds a word; longer words are cut to the column and reported (`overflow`).
Layout: two columns; if the window cannot fit them, stacked; if neither fits, the pixel scale steps down one whole
pixel at a time; only at 1 px per UI px may rows be clipped (reported as `clipped_rows`, nothing drawn off-window).

## Interact prompt (`prompt`)

Keycap of the `primary` binding + `icons[kind]` above the target (`lift_m` 0.9 m), clamped `margin_px` inside the
window. Alpha 1.0 within `full_alpha_m` (1.6 m), 0.5 at the reach radius (`focus_acquire_m`, 2.2 m), never lower
while E would act; fades in over `fade_in_s` (0.12 s) and out over `fade_out_s` (0.25 s) once out of reach. No
mastery fade (the icon says what E does). Kinds: move→door, talk/recall→talk, collect/take→take, use→use (lever),
examine/inspect/look→look, climb, attack, challenge→attack, checkpoint.

## Corner hint (`hint`)

Bottom-left strip of keycap + icon pairs, no words. `moments`:

| Moment | Keys | Shown for | Ends early on |
|---|---|---|---|
| `start` (game boot) | move, primary, dodge (each only if bound) | 8 s | first movement |
| `resume` (Esc pause or Tab menu closes) | same | 4 s | first movement |
| `challenge_started` (module event, once per session) | primary, dodge, focus | 6 s | first primary press |

The clock and the early end count only while the strip is visible; it waits while a dialogue/narration box is up.
Modules or arena games add a moment by name in `moments` and call `key_overlay.show_moment(name)` (or
`on_event(kind)` from `presenter.module_event`).
