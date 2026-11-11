# Cutscenes, travel shots and the results card

Any Hermes64 game can have short in-engine cutscenes and a results card. They are plain data in the
story file, under `metadata.presentation`. No video files: every shot is the game's own rooms and
characters, drawn by the runtime with a camera move you describe.

- Cutscenes never change the game. While a card shows, the game is paused at a tick boundary: the
  clock, the run timer, enemies and the input recording all stop, and nothing is recorded. A replay
  plays the same with cutscenes watched, skipped or switched off.
- Any key, pad button or mouse click skips the whole cutscene. Play continues once every key is
  released, so the key you skipped with never becomes a jump or an action.
- Cutscenes play once per run unless `"once": false`.

## Where it goes

```json
"metadata": {
  "presentation": {
    "scenes": [ { "id": "...", "trigger": {...}, "cards": [ ... ] } ],
    "results": { "enabled": true }
  }
}
```

The plugin checks it when the game is compiled (`hermes64_compile` calls
`story/presentation/scenes.py`; it sits outside the pinned STORY core files). Unknown fields, missing
rooms or characters, a door that does not exist, a card with no end, or text that does not fit are
refused with the path of the bad field.

A full working example on the bundled Thaw game: `examples/scenes-thaw/scenes.json`.

## When a scene plays (`trigger`)

| `on` | Extra fields | Plays |
|---|---|---|
| `start` | none | when the game opens, before the first input |
| `door` | `from`, `to` (room ids) | inside the door fade, while the screen is black: a **travel shot**. The usual fade and room-name card follow it |
| `enter` | `room` | right after entering that room through a door |
| `event` | `kind`, optional `challenge` | on a gameplay event: `challenge_started`, `encounter_cleared`, `course_completed`, `challenge_failed`, `checkpoint_ready`, `region_unlocked`, `boss_phase`, `boss_defeated` |
| `ending` | optional `ending` (id) | when the story ends, before the results card |

Several scenes with the same trigger play one after another in list order.

## A scene

| Field | Meaning |
|---|---|
| `id` | unique lowercase id |
| `trigger` | see above |
| `cards` | 1 to 16 cards, shown in order |
| `transition_in`, `transition_out` | `fade` (default, same timing as doors: 0.22 s out, 0.18 s in), `iris` (a closing circle, same timing) or `cut` |
| `letterbox` | black bars top and bottom, default `true` |
| `music` | optional audio slot name for the scene (names only). By default a scene does **not** change the room's music |
| `room` | default room for its cards |
| `once` | default `true` |

A whole scene may hold at most 5,400 ticks (90 s).

## A card

| Field | Meaning |
|---|---|
| `room` | which room to show (any room of the game, not only the current one) |
| `hold` | how long the card shows, in ticks (60 per second), 1 to 1,800 |
| `shot` | the camera, see below |
| `actors` | up to 6: `{"character": id or "protagonist", "at": [x, z], "yaw": degrees, "clip": "idle"}`. Add `"to": [x, z]` and the actor moves there during the card, playing `moving_clip` (default `walk`). A clip the character does not have falls back to `idle` |
| `cast_only` | hide the room's other characters for this card |
| `subtitle` | one strip at the bottom: `{"speaker": "NAME", "text": "...", "color": "#rrggbb"}`. At most 80 characters (two lines). The speaker name is drawn in `color` |
| `title` | a title card in large pixel letters (at most 40 characters), for example the name of the next wave |
| `voice` | an optional voice line id from the audio slots; it starts when the card starts |
| `cut` | how this card replaces the previous one: `cut` (default), `fade` or `iris` |
| `reduced` | optional `{"shot": {...}}` used instead when the player has turned on reduced motion |
| `wait` | `"key"`: only on the first card of a `start` scene, for a title screen that waits for any key. Bots and replays continue after `hold` |

Positions are metres in the room's own grid: `x` across, `y` up, `z` down the room, the same numbers
used for character positions in `presentation.rooms`.

### Shot language

| `kind` | Fields | What the camera does |
|---|---|---|
| `cut` / `hold` | `from`, `look` (or `camera`) | stays still |
| `push` | `from`, `look`, `to` or `amount` (metres) | moves slowly toward the subject |
| `pan` | `from`, `look`, `look_to` | turns from one point to another |
| `orbit` | `look` (centre), `radius`, `height`, `start_deg`, `sweep_deg` | circles the centre |
| `track` | `follow` (actor index), `offset`, `look_height` | follows a moving actor: the travel shot |

All shots accept `fov` (20 to 100). `camera` uses one of the room's authored cameras by id. Moves are
eased in and out over the card's hold.

### Reduced motion

When the player turns on reduced motion (pause menu), fades take 0.06 s, an iris becomes a fade,
moving shots hold their end framing, and actors start at their end positions. Give a card a
`reduced.shot` for a different still framing.

### A travel shot between two rooms

```json
{
  "id": "street_to_subway",
  "trigger": {"on": "door", "from": "street", "to": "subway"},
  "cards": [
    {"room": "street", "hold": 150, "cast_only": true,
     "actors": [{"character": "protagonist", "at": [3, 8], "to": [12, 8], "moving_clip": "run"}],
     "shot": {"kind": "track", "follow": 0, "offset": [0, 2.4, 4.2]}},
    {"room": "subway", "hold": 120, "cut": "iris", "title": "WAVE 2",
     "shot": {"kind": "pan", "from": [10, 4, 10], "look": [4, 1, 4], "look_to": [7, 1, 5]}}
  ]
}
```

The door fades to black as usual, the shot plays inside the black, then the door's normal fade-in and
room name finish the entry.

## Wave titles

When a challenge starts, its label (`encounter.label`, or the challenge's `label`) shows for 1.5 s
in the upper third of the screen. No box, no other text.

## The results card

```json
"results": {"enabled": true, "title": "THE KEEP", "music": "results", "labels": {"time": "TIME"}}
```

Shown when the story ends (after any `ending` scene), or with `"on": "run_finished"` when a timed run
finishes. It shows, in digits only:

- `TIME` the game clock, `mm:ss.cc`. With a timed run (`gameplay.run`) death penalties are already in it.
- `DEATHS`
- `PENALTY` the time added by deaths, only when the game has a death penalty.
- `BEST` your best time for this game on this computer.
- `RUN` the run code: the first 12 hex characters of the sha256 of the run's input recording. The same
  run gives the same code, and a saved replay of it hashes to the same code.
- `AGAIN` restarts the game. `SAVE REPLAY` writes the recording to `user://replays/<code>.h64movie.json`
  (in the browser it is also downloaded).

Left/Right (or A/D, Up/Down, Tab) choose, Enter/Space/E confirm; a pad's d-pad and A work too. The card
waits until the key that ended the game is released.

`labels` can rename the words (`time`, `deaths`, `penalty`, `best`, `code`, `again`, `save`, `saved`),
for example for another language.

Where the time comes from: a game with a timed run (combat 1.2.0 `gameplay.run`) uses that run's
clock, deaths and penalty. Any other game uses the game's fixed-tick clock at the ending, with no deaths
(named `STUB_story_clock` in test receipts).

The best time is stored only on this computer (`user://hermes64/best_times.json`), never uploaded.
Watching a replay does not change it.

## For other parts of the plugin

- Runtime: `runtime/godot/view/scene_cards.gd` (director), `results_card.gd`, `best_store.gd`,
  `run_source.gd` (read-only run-state adapter). The presenter makes three calls: mount at boot,
  `travel()` at the door's black, `room_ready()` after a door's release.
- Audio: the director calls, when present, `sounds.voice(line)`, `sounds.on_cutscene_music(slot)`,
  `sounds.stop_voice()` and `sounds.on_results()`. Missing methods are skipped.
- Test seam: `options.scenes = "off"` disables scenes (results still show). Receipts: `receipts`,
  `cue_log`, `watchdog`; in the browser `window.hermes64.scenes`.

## GAPS2 additions

- **Story files.** `arena_run_v1` turns a story file's `scenes.opening/pre_finale/ending` cards into scenes of this
  format and appends `scenes.list` (full scenes) as written; see docs/TEMPLATES.md section 9.
- **Bots wait for scenes.** The physical bot (`playtest/runner.gd` `step()`) waits while scene cards play, as it waits
  for a doorway, off its own clock; it does not wait for the results card. Long `start`/`enter` scenes no longer make it
  report "no displacement" (known-bad control: playtest config `control: "no_scene_wait"`). The room-coverage capture
  (`--screens`, style audit) turns scenes off, so it shows rooms.
- **Capturing scenes and the results card.** A replay normally quits at its final hash. With `--capture_scenes=<dir>`
  it keeps running, so the ending scene and the results card play, and `view/scene_capture.gd` saves one frame per
  card (half its hold), one per room entry and the results card, plus `capture.json`. Command:
  `python3 -B -m adventure_maker.scene_capture --game-dir <games>/<game> --out <new folder>` (newest playtest movie) or
  `--runtime <runtime> --movie <x.h64movie.json> --out <new folder>`. Needs a display; headless runs the same flow
  without pixels.
