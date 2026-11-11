# Place archetypes

Data in `kits/places/<id>.json`, contract `contracts/place/1.0.0.json` (`hermes64-place/1`). Each archetype uses
existing kit pieces and generator recipes only. Gaps are listed, not faked. Numbers are from `tools.place_maker
plan` at seed 1 and clutter 1, unless the proof run (`docs/PLACEMAKER-RESULT.md`) says otherwise.

| archetype | kit compiler | base pack | sizes (plot cells) | moods offered | default mood |
|---|---|---|---|---|---|
| `wizard_tower_interior` | medieval | castle_keep | small 3x2 (`cst.hall__dungeon` + `vlg.ceiling`), medium 3x4 (`cst.hall` + `cst.ceiling__vault`) | base, purple_dusk, ember_night, golden_hour, deep_sea | purple_dusk |
| `western_main_street` | western | frontier_town | small 4x4, medium 5x4, large 6x4 (ground + boardwalks + gateways) | base, golden_hour (`frontier_town_golden`), night (`frontier_town_night`), ember_night, purple_dusk | base |
| `cyber_subway_platform` | cyber | neon_city_night | small 3x3 (`cyroom.subway`), large 5x4 (`cyroom.subway__arena`) | base, neon_dawn, blue_grid (`cyber_blue_grid`), ember_night, purple_dusk | base |
| `castle_great_hall` | medieval | castle_keep | medium 3x4 (`cst.hall__great` + `cst.ceiling__vault`) | base, golden_hour, ember_night, purple_dusk, frost_dawn | base |
| `forest_clearing_camp` | medieval | medieval_village | small 4x4, large 5x5 (meadow ground + painted backdrop) | base, golden_hour, ember_night, purple_dusk, dusk (`medieval_village_dusk`), night (`medieval_village_night`) | base |

## Zones and groups

**wizard_tower_interior.** Entrance: the shell's one cut door (west in the small room, south in the medium room).
- Focal: cauldron (`mprop.cauldron`, required). Crystals flank it (recipes: `alien.crystal__small`, `dprop.crystal`).
- Medium room only: a spiral stair in a north nook (`cst.spiral_stair`).
- Walls: book shelves (`mprop.shelf__books`) on shell wall sockets, and a reading table with candles on top.
- Corners: chests, crystal shards scattered, stores (sacks, baskets, barrels, crates). One hanging lantern.
- Gaps (listed by the taxonomy): potion, spellbook, telescope, rune circle, wand, rotunda (no round tower interior
  shell; the room is a rectangular castle shell).

**western_main_street.** Entrance: the west ranch gateway. The east gateway is the second door. The street runs
between the boardwalk fronts.
- Frontage rows: closed-front buildings on both lot lines, picked by seed, with empty lots where the triangle
  budget runs out.
- Focal: a well (required).
- Along both boardwalk edges: hitching posts, lantern posts, troughs, barrels and crates, a wanted board. A wagon
  stands in an east nook.
- Gaps: horse and tumbleweed. The taxonomy reports `water pump` as `exists` through the `water` kind, a loose word match.
- Triangles: the buildings use most of the 6,000 cap. The frontage group may use 55% of the dressing budget, so
  rows have gaps on larger plots.

**cyber_subway_platform.** Entrance: the south door socket.
- Focal: a carriage standing on the rails in the trough (required).
- Turnstiles flank the entrance where they fit. Signs are mounted on the walls.
- Back wall: lockers, vending machines, terminals and benches. Crates in the north-west and south-west nooks.
  Puddles.
- Gaps: escalator, route map (the kind `scroll` exists but has no piece) and ticket machine.
- Tag fixes: some mechanical tags are wrong (`cytech.vending` is tagged `book`, `cyroom.turnstile` is tagged
  `inn`), so those groups name the key directly (`tag.keys`).

**castle_great_hall.** Entrance: the south door.
- Focal: a dais with the canopied throne on top (both required). A runner lies on the path from the door to the
  dais (flat, so it never blocks).
- Pillar pairs stand along the path, kept outside a 5 m fight floor. Braziers flank the dais. One chandelier.
- East and west walls: long tables and benches, with tableware on the tables. Banners on free shell wall sockets.
  Stores in the corners.
- Wants checked by the taxonomy: `tapestry` reports `exists` through the `banner` kind, and `long table` through `table`.

**forest_clearing_camp.** Entrance: a postern gate in a hedge line on the south edge (`vlg.wall__postern` +
`mnat.hedgerow`). The medieval kit has no trail-gate piece, and a door must exist because the story check requires
every region to be reachable (proof run 2 failed on a doorless camp).
- Focal: a campfire (recipe `wprop.campfire` from the western kit). Logs ring the fire and lanterns flank it.
- Perimeter: a ring of trees (oak, pine, young oak, short pine). Tree canopies count as solid footprints in the
  clearance check.
- Supply clusters in the nooks, a cart, and rocks, bushes and flowers scattered.
- Gaps: tent and bedroll (not in the vocabulary). The taxonomy reports `cooking pot` as `exists` through `urn`, a loose match.
  `woodpile` exists (`mprop.woodpile`), but this archetype has no woodpile group yet (a follow-up).

## Placement rules (grammar)

| rule | what it does |
|---|---|
| `focal-point` / `centre` | one piece at the focal point / floor centre, facing the entrance (or a fixed yaw) |
| `against-wall` | slots along chosen walls, back to the wall, facing in; avoids door zones, the path, the fight floor and wall-mount fronts |
| `wall-mount` | on the footprint's wall sockets (medieval shell sockets through the compiler's `wall` list; other kits mounted metres) |
| `flanking-door` / `flanking-focal` | a pair either side of the entrance / focal point (first yaw that fits) |
| `along-path` | pairs along the entrance-to-focal path, outside the path width (+ optional extra lateral distance) |
| `on-path` | one flat piece (under 0.12 m) centred on the path; a tall piece is refused |
| `ring-focal` | pieces on a circle round the focal point, facing it |
| `cluster` | pieces inside chosen corner nooks |
| `scatter` | seeded spots in the floor (or the exterior placement rectangle) with spacing |
| `perimeter` | seeded spots in a band along the plot edge (trees round a clearing) |
| `ceiling` | mounted pieces over the focal approach / path middles |
| `on-top` | a piece on top of a piece from an earlier group (candles on a table, a throne on a dais) |
| `frontage-row` | lot-line buildings filling each frontage run (closed fronts only) |

Every floor piece is checked: it stays inside the floor box, does not overlap another piece (plus spacing), and
keeps out of door zones, the path corridor and the fight floor. Flat pieces never block. Sizes come from the built
GLB bounds. Sockets and triangles come from `kits/library/*-sockets.json`. Tags come from `catalog/tags.json`.
