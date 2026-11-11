# UI5 room size: measurements and a proposed room-scale dial

**Answer:** every room that `/hermes64 new` makes with the village, forest or polar style is a **4 x 4 m** grid
(template `two_room_collect_v1`, both rooms). The capsule centre can walk a **3.52 x 3.52 m** area. The clear
square is **1.77–3.52 m** (median 1.90 m), which is **3.4–6.8 player body widths**. Wall height is **2.8–3.0 m**.
For comparison, the median clear square of the repo's hand-authored rooms is 6.52 m. The arena rooms measure
14.5–16.3 m in CYBERPOLISH-RESULT.md (the lane brief says 14.5–16.8 m). No document sets 4 m as a room-size target, and none calls it a bug. The size comes from the
original starter (`premise_spec`, commit 89b383de), documented as "a two-room starter, not a finished game"
(QUICKSTART) and kept "byte-identical (A8)" (TEMPLATES). Defaults and goldens are unchanged; the dial below is a
proposal.

## Method

The runtime's own capsule-clear grid (`view/solid_navigation.gd`: 0.25 m cells, capsule r 0.26 m / h 1.4 m,
bounds margin 0.4 m, the room boundary outline and every solid footprint), flood-filled from the player spawn. Clear
square = largest square of reachable capsule-centre cells x 0.25 m + 0.52 m capsule diameter. This is the same
definition as `tools/room_clearance.py`, which produced the CYBERPOLISH arena numbers. Body width = 0.52 m.
Script: `runtime/godot/tests/ui5_rooms.gd`; driver: `python3 -B -m tools.ui5_rooms LABEL --new ... --shipped`
(run `r2`, `evidence/ui5/r2/rooms.json`). New games were built with the packaged plugin on this Mac. The builder was
Blender (installed here); BFIX's no-Blender override does not exist yet. Premises:

- fox: "A fox searches the village for its lost lantern" (style forest)
- village: "A keeper relights the harbor lighthouse before the storm"
- polar: "A penguin repairs the frozen station radio"

## Numbers

| Group | Rooms | Grid W x D (m) | Walkable extent (m) | Clear square m (min/median/max) | Body widths | Walkable m² | Wall height m |
|---|---|---|---|---|---|---|---|
| `/hermes64 new` village, forest, polar | 6 | 4 x 4 (all) | 3.52 x 3.52 (all) | 1.77 / 1.90 / 3.52 | 3.4 / 3.65 / 6.8 | 6.94 / 8.0 / 9.0 | 2.8 / 2.8 / 3.0 |
| Shipped hand-authored (thaw, reedland relay/combat, puzzle_hall) | 14 | 9–16 x 6–16 (median 13 x 11) | 8.52–15.52 x 5.52–15.52 | 3.52 / 6.52 / 10.52 | 6.8 / 12.5 / 20.2 | 37 / 82 / 208 | interiors 2.7–3.0; exteriors open |
| `city_arena_test` (shipped, exterior) | 2 | 12 x 12, 16 x 16 | 11.52, 15.52 | 6.52 / 7.65 / 8.77 | 12.5 / 14.7 / 16.9 | 109 / 162 / 214 | open |
| Cyber arena rooms (docs/CYBERPOLISH-RESULT.md, static tool) | 5 | 20 x 16 – 21 x 21 | n/a | 14.5 / 14.8 / 16.3 | 27.9 / 28.5 / 31.3 | 211 / 292 / 356 | n/a |

New-game rooms in detail. In room_a the clear square is set by the solid NPC standing in the room (1 solid). The
polar rooms have a built kit shell (outline boundary, 2 solids), while village and forest use placeholder walls.

| Game | room_a clear / walkable | room_b clear / walkable | Wall |
|---|---|---|---|
| fox (forest) | 1.77 m / 8.0 m² | 3.52 m / 9.0 m² | 2.8 m placeholder walls |
| village | 1.77 m / 8.0 m² | 3.52 m / 9.0 m² | 2.8 m placeholder walls |
| polar | 1.77 m / 6.94 m² | 2.02 m / 6.94 m² | 3.0 m kit shell |

Standard N64 adventure rooms: **NOT measured**. No sourced dimensions exist in the repo, and this lane has no
network access. The in-repo comparison above is the hand-authored rooms.

## Proposed dial: `room scale` small / medium / large

Measured on the real starter: the fox spec scaled, compiled and checked with the packaged plugin, then run through
the same runtime measurement (`drivers/scaled_rooms.py` in the lane scratch folder). All three variants compile and
check `proved`.

| Scale | Grid | Door cell (north wall) | Fixed camera | Clear square room_a / room_b | Body widths | Walkable m² | Proposed min clear square |
|---|---|---|---|---|---|---|---|
| small (default, today) | 4 x 4 m | 1 | [2,3,5] -> [2,0,2] | 1.77 / 3.52 m | 3.4 / 6.8 | 8.0 / 9.0 | 1.5 m |
| medium | 8 x 8 m | round(1.5 x 2 - 0.5) = 2 | x2 | 5.52 / 7.52 m | 10.6 / 14.5 | 48 / 49 | 5.0 m |
| large | 12 x 12 m | 4 | x3 | 9.52 / 11.52 m | 18.3 / 22.2 | 120 / 121 | 9.0 m |

What scales: `grid_size`, door cells (centre kept), fixed-camera position and look_at, and authored presentation
anchors (`player_start`, interaction and character positions) when a template has them. What does not scale:
wall height, the capsule, interaction reach (2.2 m) and props. A larger scale leaves more open floor; it does not
make props bigger. Gate: after the build, the runtime measurement above must meet the scale's minimum clear square,
otherwise `new` reports it like a style-audit fail. Where to wire it: one optional `rooms=` option on
`/hermes64 new` and a `room_scale` premise-file slot. The schema change for the `hermes64_demo` tool would count
against the 6,000-token budget, so that is left as an owner decision. `metadata.room_scale` records the choice.
Not implemented here: `newgame.py` parse/create is the file BFIX is editing in parallel, and the instruction was not
to change template defaults.
