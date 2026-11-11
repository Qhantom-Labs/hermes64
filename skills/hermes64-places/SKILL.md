---
name: hermes64-places
description: Use when asked for a type of place. Dress rooms from data.
---

# Hermes64 places (place archetypes -> dressed rooms)

"Make a wizard's tower room" should not mean laying every prop by hand. A **place archetype** is data
(`kits/places/<id>.json`, contract `contracts/place/1.0.0.json`). It holds the room shell options, zones (entrance,
path, focal point, fight floor, nooks), prop groups by catalog **tag** with a placement rule, the look profile, the
default mood and a clearance rule. A seeded grammar turns it into a **normal room plan** for the kit compiler, and a
render loop builds it in the runtime, measures it and retries within bounds. Full guide: `docs/PLACES.md`.
Archetype list: `docs/PLACE-ARCHETYPES.md`.

## 1. Pick the archetype and the parameters

    python3 -B -m tools.place_maker list

| ask | archetype |
|---|---|
| wizard's room, mage study, alchemist's lab | `wizard_tower_interior` |
| western town, frontier street, cowboy main street | `western_main_street` |
| metro or subway station, cyberpunk underground | `cyber_subway_platform` |
| throne room, castle hall, feast hall | `castle_great_hall` |
| campsite, forest camp, woodland clearing | `forest_clearing_camp` |

Free parameters (everything else comes from the archetype):
- `size`: `small` / `medium` / `large`, only the sizes the archetype lists. Shell sizes are fixed kit pieces.
- `mood`: only moods the archetype offers. `base` is the pack as shipped. `pack:` moods are hand-made packs.
  `derive` moods are remapped from the base pack (`kits/core/mood.py`) and may be clamped or refused.
- `clutter`: 0-3. It moves every group between its min and max count.
- `seed`: any whole number. The same seed always gives the same plan bytes.

Map the user's words to mood names: "purple dusk / wizard purple" is `purple_dusk`, "sunset / golden" is
`golden_hour`, "embers / volcanic night" is `ember_night`. A mood the archetype does not offer is refused. Say so;
do not swap it for another mood.

## 2. Check the plan first (no render, about 1 s)

    python3 -B -m tools.place_maker plan wizard_tower_interior --size medium --mood purple_dusk --clutter 2 --seed 4
    python3 -B -m tools.place_maker diagram wizard_tower_interior ... --out plan.png     # top-down zones + footprints

Read the lines:
- `static: ok`: the clear square is at least the archetype's rule, every door, the focal approach and the fight
  floor are reachable (`tools.room_clearance`), coverage is within the clutter budget, and triangles are within the
  6,000 cap.
- `recipes`: generator pieces from another kit family that the render step builds into the pack (for example
  crystals in a castle room).
- `gap` / `not in library`: tags with no piece. They are left out and listed (taxonomy gap report). Never swap in
  a lookalike silently.
- `trimmed` / `short`: pieces dropped for the triangle budget or for lack of space.

## 3. Render and measure

    python3 -B -m tools.place_maker make wizard_tower_interior --size medium --mood purple_dusk --seed 4 --run my-run

It clones the bundle to scratch, installs the mood and recipe pieces there, and builds through the normal Service
path. It runs the style gate, the n64 gate and the reference band (style bible env statistics p10-p90) on the
game-camera frame. On failure it changes only bounded knobs (clutter, spacing, seed re-roll, light 0.85-1.15,
contrast 0-0.2, camera pull 0-0.3) and tries again. Read `evidence/placemaker/<run>/report.txt`, which lists every attempt.
Report numbers and what is shown. **Do not call a room good-looking; looks are for the owner to judge.**

## 4. Use the result in a game

The best attempt's `plan` (in `report.json`) is a normal kit room plan. Compile it with the kit's
`compile_room` (`tools.medievalkit_rooms`, `westernkit_rooms`, `cyberkit_rooms`), or call
`adventure_maker.place.compile(res, door_targets)`. That gives the spec room and the presentation row you add to
the game spec as usual. Use `door_targets` to wire each door to the next room. Rooms in the proof sit next to a
plain lobby, because a region link cannot point at its own room.

## 5. Style lock: approved examples

    python3 -B -m tools.place_maker examples wizard_tower_interior          # few-shot: approved params + seeds
    python3 -B -m tools.place_maker compare --run evidence/placemaker/<run> --room <room id>
    python3 -B -m tools.place_maker approve --run ... --room ... --by "the owner"  # only when the owner says so

Offer approved params and seeds first when the user wants "more like that one". `compare` reports palette and
layout distances to approvals. These are numbers, not a verdict. The store starts empty. Never record an approval
the user did not give. Test records are marked `synthetic` and are never offered as examples.

## When to author by hand instead

- The place is not in the list, or it needs a layout the zones cannot express (a winding cave, several levels, a
  puzzle with exact positions). Write a room plan for the kit compiler directly (see the kit docs). You may start
  from an archetype's plan and edit it.
- A story needs exact positions (a clue under the third table). Generate, then edit the plan, then run
  `place_maker plan` again on the same plan to keep the clearance check honest.
- The archetype's gaps are central to the request (a potion shop with no potion piece). Generate the missing piece
  first (plan 07 generator path), then add its key to the group's `prefer` list.
