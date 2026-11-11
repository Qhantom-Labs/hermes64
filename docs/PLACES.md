# Places: "make this type of place"

Ask for a type of place: a wizard's tower room, a frontier main street, a subway platform, a castle great hall or
a forest camp. Hermes64 dresses the room for you from kit pieces, in the style of the pack and mood you chose. It
builds the room in the game runtime, measures the frames, retries within safe limits and reports what it made and
what it could not make.

The look is still decided by the kits, packs and style rules. A place only decides what goes where and which
mood. **Only you judge how it looks.** The reports give numbers, not opinions.

## For users

Say what you want in plain words. The agent maps them to an archetype and a few settings:

| you say | archetype | settings |
|---|---|---|
| "a small wizard's study at purple dusk" | `wizard_tower_interior` | size small, mood purple_dusk |
| "a busy western street at sunset" | `western_main_street` | clutter 3, mood golden_hour |
| "a big empty subway platform for a fight" | `cyber_subway_platform` | size large, clutter 0 |
| "a throne room at night, embers" | `castle_great_hall` | mood ember_night |
| "a camp in the woods" | `forest_clearing_camp` | defaults |

Settings you can change: **size** (the sizes the place offers), **mood** (the moods the place offers), **clutter**
0-3 (how full it is) and **seed** (a different arrangement of the same place). The same seed always gives the
same room.

What you get back:
- the room in your game, built through the normal plugin path;
- a report listing every try, the triangle count, how big the clear floor is, whether every door and the focal
  point can be reached, the gate results, and which pieces came from another kit;
- a list of things the library does not have (for example: no potion bottles, no tents). Those are left out and
  named. Nothing is swapped for a lookalike.

If you like a room, say so. The agent can record it as **approved** (`approve`, with your name). Later rooms of
the same place then report how close they are to your approved ones, and your approved seeds are offered first.
Nothing is ever recorded as approved unless you said so.

## For agents

Skill: `skills/hermes64-places/SKILL.md`. Commands (run from the plugin folder):

    python3 -B -m tools.place_maker list
    python3 -B -m tools.place_maker plan ARCH [--size S] [--mood M] [--clutter N] [--seed N]
    python3 -B -m tools.place_maker diagram ARCH [...] --out plan.png
    python3 -B -m tools.place_maker make ARCH [...] [--attempts 3] [--run NAME]
    python3 -B -m tools.place_maker determinism ARCH [...]
    python3 -B -m tools.place_maker approve --run DIR --room ID --by NAME [--note T]
    python3 -B -m tools.place_maker compare --run DIR --room ID
    python3 -B -m tools.place_maker examples ARCH
    python3 -B -m tools.place_maker proof --requests docs/placemaker/proof-requests.json --run NAME --out DIR

In code: `adventure_maker.place.make_plan(archetype, params)` gives a result whose `plan` is a normal room plan for
the kit compiler. `place.compile(res, door_targets)` gives `(room, presentation, report)`.
`place.static_checks(res, room, pres, rep)` runs clearance, reachability, coverage and triangle checks.

### How a place is made

1. **Archetype (data).** `kits/places/<id>.json`, contract `contracts/place/1.0.0.json`. It holds:
   - footprint options, each a socket-checked kit skeleton (shell, ground, doors);
   - zones: entrance, path, focal point, fight floor, nooks;
   - prop groups by catalog tag, each with a rule, count range, spacing and height tier;
   - the look profile, moods, texture roles, spawn and door conventions, and the clearance rule.
2. **Grammar (seeded).** Groups are placed in order. Each floor piece is sized from its built GLB bounds and kept:
   - inside the floor box,
   - clear of other pieces (plus spacing),
   - out of door zones, the path corridor and the fight floor (flat pieces never block).

   Tags resolve through `catalog/tags.json`:
   - pieces built in the pack come first;
   - next, generator recipes from other kit families (built into the pack at render time);
   - otherwise the group is left out and the taxonomy gap report row is listed.

   A required group that cannot be placed refuses the place with one line. The triangle budget (6,000 per room,
   minus the skeleton, the protagonist and a reserve) trims dressing first.
3. **Compile.** The plan goes to the kit's own `compile_room` (`tools.medievalkit_rooms`, `westernkit_rooms`,
   `cyberkit_rooms`). The compiler checks sockets, doors and the triangle cap as for any hand-written room.
4. **Static checks.** `tools.room_clearance` (capsule 0.26 m, 0.25 m flood fill) from the entrance. Every door,
   the focal approach point and the fight floor centre must be reachable. The largest clear square must be at
   least the footprint's `min_clear_m`. Floor coverage must stay under the archetype's `max_coverage` (the
   clutter budget).
5. **Render and measure** (`make`).
   - Setup: clone the bundle to scratch, install the mood pack and recipe pieces there, and build through the
     Service (scaffold, compile, check, build_assets, open with screenshots).
   - Gates on each room's game-camera frame: the style gate, the n64 fidelity gate, and the reference band. The
     band is the share of seven frame statistics (lightness mean, contrast, RMS contrast, edges, flat share,
     chroma mean, accent share) inside the style bible's env reference p10-p90 range (`kits/core/style_ref_numbers.json`).
     The band must be at least 0.5.
   - Static failures change clutter, then spacing, then the seed. Render failures change light (±0.08 within
     0.85-1.15), camera pull (+0.15 up to 0.3) or clutter, or re-roll the seed.
   - Several requests share one game per pack in each round. The best attempt is kept, and every attempt is
     written to `evidence/placemaker/<run>/report.json` and `report.txt`.
6. **Style lock** (`place_approvals/`). `approve` records frames, the plan hash, params, pack and mood under
   `<archetype>/<pack>__<mood>/<id>/`. `compare` reports two distances to every approval of the archetype, same
   style first:
   - palette distance (hue, lightness and neutral-share distributions, 0..1);
   - layout distance (density, coverage, zone shares).

   `examples` lists approved params and seeds for few-shot use. Synthetic test records are never listed as
   approved.

### Limits (honest)

- Shell sizes are fixed kit pieces, so "size" picks among the footprints an archetype lists. The great hall has
  one size.
- The lobby room in render runs exists only because a region link cannot point at its own room. In a real game,
  wire the doors to your other rooms with `door_targets`.
- The forest camp is entered through a postern gate in a hedge line. The medieval kit has no trail-gate piece, and every
  region must be reachable, so a door piece is needed. Footprints can still mark `"virtual": true` openings, but a
  room whose only openings are virtual cannot be reached in a game.
- Light energy, contrast (ambient down / key up, 0-0.2) and camera pull are the only look knobs the loop touches. Fog, palette and materials belong to the
  pack and mood.
- The packaged plugin zip does not yet include `tools/place_maker.py` and the room compilers it uses. The CLI
  runs from the source tree or a bundle clone. The include list change for the integrator is in
  `docs/placemaker/package-include.patch`.
- `room_clearance` is a static check that mirrors the runtime movement rules. It is not a runtime walk.
