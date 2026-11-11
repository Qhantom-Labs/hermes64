# How to play

Use the actual `Play:` command returned by your game build, or launch its exported app. Installing Hermes64 does not launch a game. For installation and your first game, see [QUICKSTART.md](QUICKSTART.md).

## Default keyboard controls

These are the modern left-hand defaults; the game's on-screen key hints follow your saved bindings.

| Key | Action |
|---|---|
| WASD or arrow keys | Move |
| E | Act / interact; attack during combat |
| Tab | Actions menu |
| I | Inventory |
| Esc | Settings / pause; resume |
| Hold Shift | Run (default mode; settings also offer toggle / auto) |
| Hold Alt | Precision walk |
| Q or Backspace | Back / secondary; block in combat when available |
| Z | Focus / lock-on |
| Space | Dodge / roll where supported; not a general jump key |
| J / L; U / K | Camera left / right; up / down |
| V | Recenter camera |
| C | Cycle authored cameras / follow |
| F5 / F9 | Quick save / load |
| Hold R | Retry / restart |

Actions depend on the game and current mode. Combat owns attack/block/dodge; puzzle rooms have their own move/pull/undo controls. The right-hand preset changes act to Enter, secondary to Ctrl, focus to `/`, and actions to Backspace. Use the current in-game hints rather than this default table after changing presets or remapping.

Sources shipped with the plugin: [input profile](runtime/godot/input/profile.gd), [default options](runtime/godot/input/defaults.json) and [controls-hint data](runtime/godot/input/keyhud.json). Settings show the current controls, including run/focus mode and reduced motion. For test results rather than play instructions, see [Playtests and reports](docs/PLAYTEST.md).
