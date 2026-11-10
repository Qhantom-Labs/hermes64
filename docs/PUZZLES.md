# Puzzles and dungeons (STORY 1.3.0)

Rooms can hold grid puzzles: levers, pressure plates, braziers, locked doors and keys, pushable blocks,
bridges, timed gates, orbs and one-way shutters. Every puzzle is data. The checker proves each one solvable
(and reports the shortest solution) before a build is accepted. The Godot runtime executes the same rules on
a fixed tick, and a bot replays the proved solution through the real keyboard Actions.

The example is `examples/puzzle_hall` (`tools/puzzle_hall.py`). It has four rooms: the Bronze Key, Weights,
Three Fires and the Sun Chamber. Screenshots from the real renderer at game scale are in `docs/puzzles/`.

## How it fits STORY 1.2

STORY 1.3.0 is additive. A 1.3 source adds the `puzzle` module (`gameplay.modules`), empty start facts
(`start.modules.puzzle`) and puzzle conditions. It **lowers** to a plain STORY 1.2 source:

- Every permanent puzzle fact becomes a reserved flag that only the puzzle module sets:
  - `puzzle__s__<puzzle>` marks a puzzle solved.
  - `puzzle__t__<key>` marks a key as taken.
  - `puzzle__o__<lock>` marks a lock as opened.
  - `puzzle__l__<switch|plate>` marks a latch as set (persistent puzzles only).
- `{"puzzle": "sun", "status": "solved"}` lowers to `{"flag": "puzzle__s__sun", "equals": true}`.
- The compiled 1.3 game is the compiled 1.2 game plus three additive keys:
  - `puzzle`: normalized puzzles, config and per-room hashes.
  - `puzzle_contract`: schema and implementation hashes.
  - `lowered`: the embedded 1.2 identity.

Existing 1.0 to 1.2 games are unchanged byte for byte. The package lives in `story/puzzle/`, outside the
files the 1.2 `implementation_hash` and the starter style lock pin. Authored flags may not use the
`puzzle__` prefix. Entry points: `story/puzzle/api.py` (version dispatch), `compiler.py`, `analysis.py`,
`saves.py` and `edits.py`. The contracts are in `contracts/puzzle/1.0.0/`.

## Authoring a puzzle room

```json
{"id": "weights", "room": "weight_hall", "name": "Hall of Weights",
 "layout": ["####.####", "####.####", "#.......#", "#.......#", "#.......#", "#.......#", "#.......#", "####.####"],
 "start": [4, 6], "persistence": "reset_on_leave", "reset": "hold", "max_states": 200000,
 "elements": [
   {"id": "plate_west", "kind": "plate", "cell": [2, 3], "weight": 2, "mode": "momentary"},
   {"id": "block_west", "kind": "block", "cell": [3, 5], "pull": false},
   {"id": "weight_gate", "kind": "door", "cell": [4, 1], "when": {"of": ["plate_west", "plate_east"], "at_least": 2, "invert": false}}],
 "goal": {"when": {"of": ["plate_west", "plate_east"], "at_least": 2, "invert": false}, "opens": ["weight_gate"], "rewards": {"items": []}},
 "hint": ["block_west", "plate_west", "block_east", "plate_east"]}
```

- `layout` has one row per metre of room depth and one character per metre of width. `.` is floor, `#` is
  wall and `_` is a pit (crossable only on an open bridge). Cell `[x, y]` is the 1 m square whose centre is
  `(x + 0.5, y + 0.5)`. Door exit cells (from the room's doors) must be clear floor.
- `start` is where a visit begins when it doesn't enter through a door. Entering through a door starts on
  that door's cell.
- `persistence`:
  - `reset_on_leave` rebuilds the room from its data on every visit.
  - `persistent` additionally keeps latching levers and plates (`puzzle__l__*`).
  - Solved, taken and opened are always permanent.
- `reset`:
  - `hold` lets the player hold R to reset the room.
  - `none` requires the room to be fully reversible; the proof rejects any softlock.
- `goal.when` solves the puzzle. Solving it opens `goal.opens` for good and gives `goal.rewards.items` once.
- `hint` is the order the Focus assist (hold Z) points at. The proof checks that every hinted element is used
  by the shortest proved solution.
- Room conditions can depend on a puzzle with `{"puzzle": "<id>", "status": "solved"}`.

### Elements

| kind | fields | behaviour |
|---|---|---|
| `switch` (lever) | `cell`, `mode` toggle\|latch | E while adjacent flips it. A latch stays on (persistent puzzles save it). Solid. |
| `plate` (pressure plate) | `cell`, `weight` 1\|2, `mode` momentary\|latch | Pressed while the weight on it is at least `weight`: the player is 1, a block is 2. A latch plate stays pressed once triggered. |
| `torch` (brazier) | `cell`, `order` 0-8 | E while adjacent lights it. Ordered braziers must be lit in rising `order`; a wrong one puts every ordered brazier out. `order` 0 is unordered. Solid. |
| `lock` (locked door) | `cell`, `accepts` [items] | E while adjacent with an accepted item opens it for good and uses the item. Solid until opened. |
| `key` (key item) | `cell`, `item` | E while adjacent picks the item up (one pickup per item). Solid. |
| `block` (pushable) | `cell`, `pull` | Walk into it to push one cell. If `pull` is true, hold E facing it and step back to pull it. Blocks never enter walls, pits, solid elements or other blocks. |
| `bridge` (platform) | `cells` [pit cells], `when`, `mode` | Spans pits while its link holds. A latch bridge stays once open. It cannot close under anyone standing on it. |
| `door` | `cell`, `when` | Open while its link holds or after the goal opens it. It cannot close on an occupant. |
| `timed_gate` | `cell`, `when`, `open_ticks` | Opens on the rising edge of its link and stays open `open_ticks / step_ticks` grid steps (1-15). |
| `orb` (crystal target) | `cell`, `reach` 1-8 | E while facing it along a clear row or column within `reach` flips it. Solid. |
| `shutter` (one-way) | `cell`, `dir` n\|e\|s\|w | It can be passed only moving in `dir` (both directions after the goal opens it). |

Links are `{"of": [sources], "at_least": n, "invert": bool}`:
- Sources are switches, plates, braziers, orbs and locks.
- Inverted links may use only non-latching sources.
- Timed gates don't accept latch sources.

The goal may also count opened locks.

### Rules in one place

- One grid step is `config.step_ticks` fixed ticks (18 at 60 Hz in puzzle_hall). A move, push, pull, act or
  wait costs one step; turning in place costs nothing.
- After every step, latch plates update, then doors, bridges and timed gates update in sorted id order, then
  the goal is checked. Permanent facts apply at once, and the room settles again on the same tick.
- A checkpoint inside a puzzle room must sit on the puzzle start-cell centre. Committing it resets the room,
  so a save never holds transient grid state.
- Per puzzle, at most 16 x 16 cells, 32 elements, 3 blocks, 2 timed gates and 23 stateful bits. Element ids
  are unique across all puzzles. A room holds at most one puzzle and no challenge; the `regions` module is
  excluded. Each key or reward item has exactly one producer.

## The proof

`story/puzzle/api.py: check_game(game)` runs the exact 1.2 macro search with an exhaustive bounded grid
search folded into every puzzle visit. The search covers player cell, block cells, element bits and timer
steps for each (entry door, permanent facts) context. Obligations per puzzle:

- `solvable` (with `shortest_solution_steps`)
- `opens:<door|gate|bridge>`
- `key:<id>` and `lock:<id>` (no dead key logic)
- `recoverable`
- `hint`

The puzzle-hall proof reports states needing hold-R reset, for example a block pushed into a corner:
85,940 of 143,673 grid states in the Hall of Weights. With `reset: none`, those states are softlocks and
the proof rejects them. The ending witness becomes continuous grid routes (`puzzle_routes`), which are the
bot's plan.

Known-bad controls (`tools/puzzle_hall.py: controls()`). Each is rejected on its named obligation:

| control | rejected obligation |
|---|---|
| unsolvable plate count | `puzzle:weights:solvable` |
| block corner softlock (`reset: none`) | `puzzle:weights:recoverable` |
| key behind its own door | `puzzle:bronze:lock:bronze_lock` (and `key:bronze_stand`) |
| door that never opens | `puzzle:fires:opens:dead_door` |

If any grid search reaches `max_states`, the result is `inconclusive` and makes no claim.

## Controls (fixed, keyboard first)

| key | in a puzzle room |
|---|---|
| WASD | step one cell, push a block, or walk into a door wall from its cell to leave |
| E | act on the faced lever, brazier, key, lock or orb; otherwise the room's own interaction in reach; otherwise dismiss a story text box |
| hold E + step back | pull a pullable block |
| hold Z | Focus: turn in place without moving and show the next hint element |
| hold R | reset the room (permanent facts kept); outside puzzle rooms R keeps its checkpoint retry |
| Q, Tab, I, Esc | unchanged (cancel, action menu, inventory, pause) |
| Space | no effect in puzzle rooms |

## Runtime

`runtime/godot/modules/puzzle/` contains:
- `rules.gd`: an exact port of `story/puzzle/rules.py`, bound by `tools/puzzle_vectors.py`.
- `controller.gd`: the fixed-tick executor.
- `props.gd`: the N64 dressing.

The module host loads the controller only when the build ships `puzzle.json`, the sidecar bound to both
build hashes. The runtime itself runs the lowered 1.2 game. While a puzzle room is active:
- the grid executor is the only mover;
- E, Z and WASD belong to it;
- hold R resets the room.

The module save codec checks checkpoint membership against the build's proved safe-checkpoint set
(`puzzle.json: reachable`), because lowered 1.2 actions never set puzzle flags.

Presentation follows the N64 look:
- Props are low-poly procedural pieces with the pack's painted textures (`look.json` palette and recipes,
  shipped in the sidecar), baked top-down vertex light, the `n64_world` shader and fog.
- Kit pieces are used where they fit: `prop.key`, `prop/blue_glass_sphere` and `prop/lens_crystal`.
- Doors and portcullises slide.
- Levers swing.
- Plates sink.
- Braziers flicker with unlit painted flames and add a warm point light through the pack light rig.
- Orbs glow.
- The Focus marker is a small spinning gem; there are no text bubbles. The room-description box stays
  hidden in puzzle rooms; story text from interactions and endings still shows.

Cues use shipped catalog sounds (`tools/puzzle_play.py: AUDIO`):

| cue | catalog sound |
|---|---|
| lever | `core.lock.turn` |
| plate | `core.chest.close` |
| door | `core.door.metal.open` |
| gate | `core.gate.creak.open` |
| push | `core.footstep.stone.02` |
| brazier | `core.nature.fire.crackle` |
| key | `core.key.jingle` |
| unlock | `core.key.turn` |
| orb | `core.magic.chime` |
| solve | `core.reward.fanfare.small` |
| reset | `core.gate.creak.close` |

### Kit seam

The dungeon dressing is stand-in: n64_v0 textures on procedural shapes, plus four `arch.column` pieces per
room in `metadata.presentation.rooms[*].pieces`. A cave or temple kit replaces it in one place: the
per-kind builders in `props.gd` (`lever`, `plate`, `brazier`, `bronze_door`, `key_stand`, `stone_block`,
`bridge`, `portcullis`, `orb`, `shutter`, `wall`, `pit`). Each builder returns a node at the cell centre
whose animated children are named `arm`, `top`, `flame`, `slab`, `key`, `bars`, `sphere`, `glow` and
`flap`. A kit piece only has to keep those child names (or map them in `KIT`). Puzzle state never reads
presentation.

## Tools (no new tool)

`hermes64_module_check` accepts 1.3 sources. Puzzle kinds go through the existing transactional tools.
Each takes exact `expected_spec_hash`/`expected_game_hash` and `expected_changed_rooms`, rechecks the
proof, migrates an optional checkpoint, and moves the data pointer only on success.

```json
{"kind": "add-switch", "puzzle": "bronze", "switch": {"id": "spare_lever", "cell": [2, 5], "mode": "toggle"}, "expected_changed_rooms": ["key_hall"]}
{"kind": "link-door", "puzzle": "bronze", "door": "alcove_gate", "when": {"of": ["brass_lever", "spare_lever"], "at_least": 2, "invert": false}, "expected_changed_rooms": ["key_hall"]}
{"kind": "move-block", "puzzle": "weights", "block": "block_east", "cell": [5, 4], "expected_changed_rooms": ["weight_hall"]}
{"kind": "set-solution-hint", "puzzle": "bronze", "hint": ["brass_lever", "bronze_stand", "bronze_lock"], "expected_changed_rooms": ["key_hall"]}
```

- `module_add` takes `add-switch`.
- `module_edit` takes all four kinds (`link-door` also accepts `"door": "goal"`).
- `module_benchmark` runs 1-20 of them in sequence without moving the pointer.
- MERGE5: `hermes64_build_assets` and `hermes64_export` use an adopted 1.3 build (lowered build + `puzzle.json` +
  puzzle cue rows in `audio.json`); see docs/EXPORT.md.

## Commands

```sh
python3 -B -m tools.puzzle_hall [--check]        # example spec/game/proof/save
python3 -B -m tools.puzzle_contracts [--check]   # contracts/puzzle/1.0.0
python3 -B -m tools.puzzle_vectors OUT           # Python/Godot rule parity (seeded walks)
python3 -B -m tools.puzzle_play OUT [--render]   # build + physical puzzle bot (needs numpy for the asset builder)
```
