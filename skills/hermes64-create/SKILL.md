---
name: hermes64-create
description: "Use for any request to make, edit, play or export a game."
version: 2.1.0
license: MIT
---

# Make a game from a prompt

The deliverable is a Hermes64 game made by this plugin: never another engine, a web page or a script of your own.
If part of the request cannot be made, make the closest Hermes64 game and say exactly what is missing.

## How to call things

- **Hermes64 tools** are named `hermes64_*`. If they are not in your tool list, they are loaded on demand: call
  `tool_describe` with the tool you are about to use, then run it with `tool_call`. Describe a tool only when you
  will call it next. The names below are exact; do not search for them.
- **The create flow** is a terminal command. Start every command with `cd "$HERMES_HOME/plugins/hermes64" &&`
  (default `~/.hermes/plugins/hermes64`). It reads the games folder (`GAMES`) and Python from the plugin settings.
  Nothing is downloaded or installed.

## Golden path (in this order)

1. `create_flow vocab` (once): `python3 -B -m adventure_maker.create_flow vocab` prints the allowed brief words, the
   styles (packs), a brief template, the story fields and the mechanics table.
2. `create_flow find`: `python3 -B -m adventure_maker.create_flow find "lighthouse, statue, train car"` says
   `exists` / `partial` / `missing` for each thing. Use the library word in the brief.
3. Write `brief.json` with its `story` block at an absolute path (rules below); pass that same path to `--brief`.
4. `create_flow plan` (seconds, builds nothing): `python3 -B -m adventure_maker.create_flow plan --brief <path>`.
   Read `story:`: `will make`, `not as asked` (closest thing and fix) and `named in the prompt, used nowhere`. Fix
   the brief, then tell the human in ONE message: "I will make: ... Not as asked: X (closest: Y)." Do not wait.
5. `create_flow run` (2 to 15 min): `python3 -B -m adventure_maker.create_flow run "<the full prompt>" --brief <path>
   --name <slug>`. It compiles, proves the story, builds the rooms, lets bots play and takes pictures. Last line:
   `report: <path>`. Start it with the terminal's `background: true` and wait for it: a tool call is cut off after
   7 minutes while the run goes on. Never start a second run while one runs (`status --name <slug>`). Before you
   reply, wait until every background run you started has ended (`process_manage`).
6. Read that `CREATE-REPORT.md`: `In the game`, `Not applied` (asked -> closest -> fix), the gates (story check,
   bots, style, N64).
7. To change the game, edit the brief and run step 5 again: every gate runs again. `hermes64_edit` makes one story
   edit and re-proves it, but only on a game whose story check says `proved`; a fight or a course makes it
   `conditional`, and `hermes64_edit` then answers `baseline_unproved`.
8. `hermes64_check` (story proof; `action: "audit"` scores the style) and `hermes64_playtest` (bots: SOLID, PLAYABLE,
   ROUGH or BROKEN): only after a change made with tools. The run already did both.
9. `hermes64_open` with `screenshots: true`: only when the human wants to see or play it.
10. `hermes64_export` with `targets`: only when the human wants a build to share.
11. Reply: what is in the game, every `Not applied` row in plain words, the gate numbers, and the pictures in
    `GAMES/<slug>/create/captures/`. Do not judge looks; the human does.

Setup trouble (Python, numpy, Godot): `hermes64_doctor` shows what is missing and what to do. Never install anything.

## Writing brief.json

`filled_by: "model"`, every template field, allowed words only (from `vocab`): one `setting.genre`, up to 6
`genre_hints`; `build_types` and `props` from `find`; `palette_mood` colours; franchise or real-person names in
`ip_terms` with a plain description. Limits: each `assumptions` line up to 120 characters, each `unrecognised` item
up to 32, `setting.place` up to 80, the prompt up to 600. `setting.room_scale` (optional): rooms are medium by
default; say large/open for bigger. Then the `story` block, sentence by sentence:
- every named person -> `story.cast` (`name` as written; `role`: npc, companion, rival, suspect, captive, traitor,
  enemy, boss); the player -> `story.player.name`. A captive is the one you free; it follows you out.
- every place -> `story.places` (`kind` outdoor/indoor, `about` = one line on entering). A title -> `story.title`.
- the thing to get -> `story.item.name`. What happens, in order -> `story.beats` (`text`; `who`, `place`, `when`).
- goals -> `story.quests` with `done_when`: `beat N`, `talk NAME`, `item`, `fight`, `course`, `choice` or `end`.
- a fight -> cast with role enemy/boss, `waves` like `[2, 2]` (at most 2 at once; a 3 is split and reported);
  a race -> `course` with `seconds` and checkpoints;
  an accusation or riddle -> `choice` (2-4 options, `right`); a locked door -> `door_lock: "beat 2"`.
- endings -> `win` (and `lose`); every gameplay word of the prompt -> `mechanics` ("no combat", "stealth", ...).

```json
"story": {"player": {"name": "Oda"}, "places": [{"name": "Harbor", "kind": "outdoor"}, {"name": "Lamp Works", "kind": "indoor"}],
 "cast": [{"name": "Mister Pell", "role": "npc", "place": "Harbor", "says": "The boy went toward the lamp works."},
          {"name": "Fen", "role": "captive"}, {"name": "The Gull King", "role": "boss"}], "item": {"name": "Brass Lantern"},
 "beats": [{"text": "Pell points at the fog.", "who": "Mister Pell", "when": "dusk"}],
 "quests": [{"title": "Free Fen", "done_when": "item"}], "waves": [2], "win": "Oda and Fen walk home.", "mechanics": ["rescue"]}
```

## When something refuses

Every refusal is one line: `code: what happened. Next: what to do`. Do the Next part once.
- `create_style_refused`: run again with the `--style <pack>` it names; tell the human the style differs.
- Re-run after a brief edit: `... run --name <slug> --brief <path>` (without `--brief` it keeps the last brief).
  `status --name <slug>` shows each stage.
- The same step failed twice: stop and tell the human what failed. Do not read or change plugin source.

## What the flow makes

Two rooms (an outdoor entry and one inside room, medieval and western styles); more places become named story spots
when a beat is set there. People: entry up to 4, inside up to 3. Collect the item inside, finish outside after the
last beat. A fight guards the item; a course guards the finish; "no combat" removes fights. A puzzle is not made
(closest: `door_lock` or `choice`). More rooms or dialogue trees: say so, unless the human asks (then see Advanced).

## Other ways to make a game

- Quick starter from one sentence: `hermes64_demo` with `premise` (optional `style`).
- Your own story spec: `hermes64_packs` -> `hermes64_scaffold` (`spec_json` + `pack`) -> `hermes64_compile`
  (`spec_path` inside the project) -> `hermes64_check` -> `hermes64_build_assets` -> `hermes64_playtest`. Spec rules:
  skill `hermes64:hermes64`.

## Advanced tools: only when the human asks for that thing

Not for a plain "make me a game". Load the skill named first.
- Characters: `hermes64_character`; skill `hermes64:hermes64-characters`.
- Audio (music, sounds, voices): `hermes64_audio`; skill `hermes64:hermes64-audio`.
- Enemies, abilities, puzzle switches: `hermes64_modules`, `hermes64_module_add`, `hermes64_module_edit`,
  `hermes64_module_check`, `hermes64_module_benchmark`; skill `hermes64:hermes64-gameplay-modules`.
- Styles and moods: `hermes64_kits`, `hermes64_pack_create`, `hermes64_pack_select`, `hermes64_pack_validate`,
  `hermes64_pack_from_refs`. A missing prop: a recipe; skill `hermes64:hermes64-generators`.
- Pieces made with the generators, in this order: run step 5 once (it creates `GAMES/<slug>`); `gen_tools author`
  and `build --project GAMES/<slug>`; name `gen:<id>` in `GAMES/<slug>/create/candidates.json`; then
  `run --name <slug> --redo assets`.
- Box art: `hermes64_cover`; skill `hermes64:hermes64-cover`. Sharing (Hub): `hermes64_hub`; skill `hermes64:hermes64-hub`.
- Proof and export details: `hermes64_replay`, `hermes64_benchmark`; skill `hermes64:hermes64-playtest-and-ship`.

## Never

- Never claim a look is good; give what is shown and the measured gates.
- Never drop a part of the prompt without saying so; the `Not applied` list and your reply name it.
- Never edit gate thresholds, the style bible or shipped packs to make a stage pass. Never invent a licence.
