# LONGSTORY plan (Phase A)

Base: `reviewfix-lane` 58404673 (= public main 17ab9a3, "rc83"). Numbers measured on this tree. No look verdicts.

## Answer first

The create flow makes a mini game because the rooms stage hard-codes two rooms. Every other part of the engine
already supports long games: the story contract has no room cap, rooms take any number of doors with conditions,
collectibles take per-key conditions and group thresholds, the module system runs several fights in several rooms
with checkpoints, and every kit ships a multi-room demo whose door connectors (postern, fence gateway, doorway
buildings) pass the kit compilers.

Smallest design for a long story through the same plain-prompt create flow:

1. A story block that names 3 or more places builds one room per place (up to 8 by default; places past the cap
   become named story spots and the tool result says which and why). A brief with 0 to 2 places takes today's
   two-room code path unchanged (byte-identical output).
2. Outdoor places form the spine (chained by the kit's edge gate: medieval `vlg.wall__postern`, western
   `wtown.fence__gateway`); indoor places hang off the outdoor room before them through doorway buildings (medieval
   kit interiors have exactly one door socket, so they are leaves). Every outdoor room gets a different entry layout
   (the VARIETY layout variants: plaza, glade, shore, island, snow) and every room its own dressing seed, name, people
   and spots; interiors rotate shell variants of the same footprint (hall: throne/great/plain; room: taproom/plain).
3. Story spine across the rooms: beats in order (each needs the one before), `keys` (new, optional) collected in
   their rooms open the door they name, fights per room (each boss in its place: the last one is the final boss),
   finish in the room of the last beat (default: the entry, so the hub is revisited). The story checker proves
   reachability and no softlock; bots must play it to the end.
4. More freedom: list limits that refused a long brief are raised (cast 8 -> 12, places 6 -> 12, beats 8 -> 24,
   quests 6 -> 12); "say so" lines in the skills become "build it and report what was folded".

## What makes it a mini game today (file:line)

| limit | where | value | kind |
|---|---|---|---|
| two rooms, built literally | `adventure_maker/create_flow.py:1295` (entry), `:1323` (inside), `:1390` (`'rooms': [room_o, room_i]`), template `create_two_room_collect_v1` `:1383` | 2 | code |
| places -> rooms | `adventure_maker/create_story.py:296-302` `room_places` takes the first outdoor + first indoor | 2 | code |
| extra places | `create_story.py:400-408`: other places become story spots only when a beat is set there, else `not_made` "the create flow builds two rooms" | spots | code |
| people per room | `create_story.py:23` `CAPACITY` entry 4 actors / 6 spots, inside 3 / 4 | 7 people | data |
| cast list | `create_story.py:134` `_list(cast, 8)` -> validation refusal at 9 | 8 | refusal |
| places list | `create_story.py:148` `_list(places, 6)` -> refusal at 7 | 6 | refusal |
| beats / quests | `create_story.py:162` beats 8, `:171` quests 6 -> refusal | 8 / 6 | refusal |
| one item, one lock | `create_story.py:156` `item` (one), `:176` `door_lock` (the inside door only) | 1 / 1 | contract |
| waves | `create_story.py:25` `MAX_AT_ONCE = 2`; `:643-650` a 3 is split ("a wave of 3 measured 6,176 triangles in the room") | 2 at once | TRUE budget limit, kept |
| one fight, one room | `create_flow.py:1505` "room already holds a challenge"; `create_modules.json` combat room `inside`, course room `entry` | 1 + 1 | code |
| crafted pieces | `adventure_maker/create_craft.json:4-5` `max_pieces` 4 / `min_pieces` 3 per game | 4 | data |
| room patterns | `adventure_maker/create_patterns.json`: medieval 2 outdoor + 2 indoor, western 1 + 1; no sci-fi, dungeon, ancient, cyber, forest or harbour family | 6 patterns | data |
| setting refusal | `create_flow.py:553-559` `create_style_refused` when the genre's pack has no pattern; otherwise a medieval/western pack is picked (VARIETY brief e, a space station, was built as a western street + saloon in `frontier_town_night`) | - | refusal / silent |
| skill text | `skills/hermes64-create/SKILL.md:98-102` "Two rooms ... More rooms or dialogue trees: say so, unless the human asks (then see Advanced)"; `:78` waves at most 2 | - | text |
| capability note | `adventure_maker/create_story.json` note "The flow builds two rooms" (printed by `vocab`/`plan`) | - | text |

Not limits for the create flow: `story/presentation/scenes.py:17` `MAX_SCENES = 32` (scene cards; the create flow
writes none); the story contract (`story/validation.py`) has no room count limit; doors are any number per room
with conditions (`story/validation.py:240-261`, reciprocal check).

## Budgets that stay

- Per room: 6,000 triangles (`create_flow.py:56` ROOM_CAP 6000, reserve 300; every kit compiler `TRI_CAP = 6000`);
  a person 760 triangles reserved (`create_story.py:26`); 256 draw calls/room and rendered p95 33.34 ms (playtest
  budget, `runtime/godot/playtest/module_runner.gd:220`).
- Checker: 100,000 states (`story/checker.py:154`). Independent flags multiply states, so the long path sets a talk
  flag only when a condition reads it; beats stay chained.
- Process limits: playtest Godot run 180 s (`adventure_maker/playtest.py:150`, `module_playtest.py:24`); open/capture
  `min(seconds + 25, 180)` s (`adventure_maker/adapters.py:213`) with `OPEN_SECONDS = 40` (`create_flow.py:55`);
  run budget `DEFAULT_BUDGET = 1800` s (`create_flow.py:53`, an exhausted budget pauses and resumes). The long path
  scales the capture window with the room count inside the 180 s cap; it changes no gate.

## Engine pieces reused (already there)

- Doors: kit compilers require a door on a door socket of a placed piece (`tools/medievalkit_rooms.py:227-246`).
  Door-socket pieces per kit: medieval `vlg.wall__postern` (edge), doorway buildings (`vlg.tavern__doorway`,
  `vlg.cottage__stone_doorway`, `vlg.chapel__doorway`, `vlg.smithy__doorway`, `cst.gatehouse*`); western
  `wtown.fence__gateway`, `wtown.saloon__entry`, `wtown.store__entry`, `wtown.sheriff__entry`, `wtown.bank__entry`.
  Interiors: one door socket each (`cst.hall*`, `vlg.room*`, `wtown.room*`).
- Multi-room demos per kit: medieval square/tavern/castle_gate/throne_room (`tools/medievalkit_demo.py:47-171`, the
  square's second door is the east postern `vlg.wall__postern` edge [3,1,e]), western main_street with 3 doors
  (saloon + west and east fence gateways, `tools/westernkit_demo.py:53-88`), sci-fi station chain of 4 interiors,
  dungeon chain, cyber `chain()` (`tools/cyberkit_rooms.py:193`).
- Layout variants: `create_craft.variant_pattern` (`adventure_maker/create_craft.py:279`) derives glade, shore,
  island and snow_village from the plaza skeleton (ground, doorway building, wall, mirror).
- Fights: STORY 1.2 modules take one encounter per challenge and any number of challenges in any rooms
  (`adventure_maker/templates.py:74-185` `arena_spec`, 3+ rooms with door chains and checkpoints).
- Collectibles: `{'collected': id}` and `{'group': g, 'at_least': n}` conditions on doors, interactions and endings
  (`story/validation.py:164-168`).
- Advanced path (hand-authored spec through scaffold/compile): no room cap in validation; the limits are the same
  per-room triangle budget and the checker state cap.

## Build and audit cost per room (from existing runs and code)

- Rooms stage: one kit compile per room plus one per dressed piece (milliseconds).
- build_assets: room pieces are pack-bound GLBs; new cost is per crafted piece (3-4 per game, unchanged).
- capture: one open renders every room; style gate + N64 gate per room; camera retries re-open the whole game
  (up to 7 opens). Measured in Phase B.
- playtest: the win bot walks the checker witness; longer games mean more ticks inside the same 180 s process limit.
  Measured in Phase B.

## Design decisions (smallest correct change)

- New module `adventure_maker/create_long.py` (layout + spec for N rooms) called from `stage_rooms` only when the
  story asks for 3+ rooms. The two-room code is not edited, so mini briefs stay byte-identical (proof: 6 VARIETY
  briefs x 8 stage files on rc83 vs candidate).
- Data: per outdoor pattern, `long_doors` rows (where an extra door may be cut, with the kit piece that carries the
  door socket), transcribed from the kit demos. Interior shell variants as data rows.
- Story block additions (optional, backward compatible): `rooms` (2-8), `keys` (name, place, opens), `item.place`,
  cast `place` already exists and now also places bosses/enemies. Nothing new is required: a brief with only places,
  cast and beats builds a long game.
- Wave size stays at 2 at once (measured triangle overrun at 3). Fights per room are added instead.
- No tool or schema change (27 tools, 6,000-token budget untouched). Guidance goes into skill text and the
  `vocab`/`plan` output.
- Sci-fi and other families: only if time remains after medieval and western work end to end; otherwise reported as
  not done with the numbers.
