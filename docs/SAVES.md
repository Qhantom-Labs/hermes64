# Exported game saves

Every exported game keeps its saves (and its Godot log and input profile) in its own folder keyed by the game id:

| Platform | Folder | How |
|---|---|---|
| Windows | `%APPDATA%\Hermes64\<game id>\` | export writes `application/config/custom_user_dir_name="Hermes64/<game id>"` |
| macOS | `~/Library/Application Support/Hermes64/<game id>/` | same setting |
| Web | IndexedDB-backed `/userfs/hermes64/<game id>/` | Godot's web build has one `/userfs` per page origin and ignores the folder setting, so the slot path itself carries the id |

The slot is `saves/slot1.json` (+ `slot1.json.controls.json`) inside that folder. The save format is unchanged. The
save path is not part of any state, replay or proof hash.

Game ids must be 1-64 letters, digits, `_` or `-` and not a Windows device name (`CON`, `LPT1`, ...); export fails
with `release_save_dir` otherwise, and also fails if the runtime template stops carrying the folder setting (so this
cannot silently regress). At runtime an id that is somehow unsafe falls back to `game-<first 16 of game_hash>`.

## The bug this fixes (SAVEFIX, 2026-11-10)

The owner's Windows PC: thaw, relay_combat, reedland_mixed and puzzle_hall all saved to one shared
`%APPDATA%\Adventure Runtime\` slot, overwriting each other. Cause: the runtime template and `export.py` used the key
`config/custom_user_dir`, which Godot does not read (the setting is `config/custom_user_dir_name`). With the name
empty, Godot falls back to `config/name` = "Adventure Runtime" for every game, on every desktop OS. The older docs
(WINDOWS.md, README, PLATFORM-PARITY) already stated `Hermes64\<game id>`; that was the intent, not what shipped.
Logs were affected the same way: pre-fix builds wrote `logs\godot.log` under `Adventure Runtime`, not `Hermes64\<id>`.

## Old saves

On boot, if the game's own slot does not exist, the shipped entry (`runtime/godot/playtest/release.gd`) looks once for
a pre-fix slot: desktop `<data dir>/Adventure Runtime/saves/slot1.json` (then `.../Adventure Runtime/slot1.json`), web
`/userfs/saves/slot1.json`. It copies it into the game's own folder only when the old save's `game_hash` and
`spec_hash` name this exact build. It never overwrites an existing slot and never deletes or edits the old file.
Because the old slot was shared, only the game that saved last can recover it; the other games' old saves were already
overwritten before this fix and start fresh.

## Checks

- `tests/test_savefix.py` (7, real Godot 4.6.2 where installed): two ids give two folders and differ only by id;
  known-bad equal ids share; unsafe ids and a template without the key fail; real Godot resolves exported projects to
  `.../Hermes64/thaw` and `.../Hermes64/relay_combat`, known-bad old key resolves both to `.../Adventure Runtime`;
  `runtime/godot/tests/savefix_slots.gd`: desktop/web slot paths, legacy adoption (bytes identical, controls copied,
  legacy kept), other build's legacy not adopted, own slot never overwritten, flat legacy layout, corrupt legacy ignored.
- Mac export + boot (`python3 -B -m tools.savefix_export <out>`, then `sh tools/savefix_keys.sh <out>/exports.json
  <out>/keys`): thaw and puzzle_hall exported for macOS with `hermes64_export` (both `verification: passed`); each
  shipped .pck booted with stock Godot 4.6.2 headless, HOME redirected: hold W, F5, quit; relaunch, F9. Results in
  `evidence/savefix/`: separate folders `Hermes64/thaw` and `Hermes64/puzzle_hall`; thaw after relaunch + F9 returns
  to the saved spot (`ok`, `exact hashes and reachable state match`); puzzle_hall F9 loads `ok` (its STORY 1.3 codec
  restores the proved safe checkpoint, not the raw position, by design); legacy case: thaw's save at the old shared
  path is adopted by thaw (same sha256) and not by puzzle_hall.
- **Not done:** OS-level key presses. F5/F9 were injected as `InputEventKey` into Godot's input pipeline
  (`tools/savefix_keys.gd`); this unattended run had no Accessibility permission (`osascript ... key code` refused,
  desktop driver needs approval). Web and Windows were not run; Windows resolution follows the same Godot code path
  (`get_data_path()` + `custom_user_dir_name`) but is unverified until the owner's PC re-runs sheet step for saves.
- Replays/goldens: `test_golden`, `test_runner`, `test_puzzle_runtime` green, nothing re-pinned.
