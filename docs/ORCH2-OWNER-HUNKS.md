# ORCH2 owner hunks

Owner files are not edited in this lane. Each change below is an exact hunk under `docs/orch2-hunks/`, applied and
tested in a disposable copy only.

## `room-keepsake-floor.patch` (runtime owner: `runtime/godot/view/room.gd`)

**What:** a collectible with a resolved model and no authored position (no presentation `collectibles.<id>.position`,
no `collect:` anchor, no character anchor) rests on the floor (`y = 0`) instead of the hard-coded default `0.6` m. The
sphere fallback (no model) and every authored position are unchanged. The bot target position is unchanged.

**Why:** the two-room starter template (`adventure_maker/templates.py`, used by `/hermes64 new`) never authors a
keepsake position, so its keepsake model floats 0.60 m up and the style gate's geometry audit fails the room
("floating pieces"). The create flow now writes an explicit floor position itself
(`create_flow.keepsake_spot`, no owner file involved); this hunk fixes the same defect for `new` games.

**Applies to:** `git apply docs/orch2-hunks/room-keepsake-floor.patch` on orch-lane `2511a6dc` and later (2 added lines).

**Tested (disposable copies, Godot 4.6.2, macOS):** `/hermes64 new "A fox searches the village for its lost lantern"`
driven through `newgame.command` with a host-like ctx (`tools/orch_hook_drive.py`), once on the package without the
hunk and once with it:

| | without hunk | with hunk |
|---|---|---|
| style audit finding `room room_b has floating pieces: prop_key` | present | absent |
| style audit score (other findings: void, doors, camera, unchanged) | 4/100 | 10/100 |
| bots | PLAYABLE (softlock checker: proved) | PLAYABLE (softlock checker: proved) |

**Not verified:** golden captures of existing games whose collectibles have no authored position would change (the
keepsake model moves down 0.60 m); no golden was re-blessed. Logic replays are unaffected (the hunk is presentation
only); `last_light`/`thaw` replays were compared in the proof (`docs/ORCH2-RESULT.md`).

## Carried from ORCH (unchanged)

`docs/agen-hunks/*.patch` and `docs/orch-hunks/*.patch` (newgame `--create` hook, package includes, package-contents
doc, skill registration) are applied by the proof driver in the same order as in ORCH. The create-flow data files
added here (`adventure_maker/create_vocab.json`, `adventure_maker/create_modules.json`) live next to
`create_patterns.json` and are shipped by the existing `adventure_maker/*` package rule; no package hunk is needed.
