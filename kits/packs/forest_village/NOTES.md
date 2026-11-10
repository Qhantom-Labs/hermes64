# forest_village pack notes (3.1.0)

## Why this second pack (rationale)
The second pack exists to prove the core is theme-agnostic, so it must disagree with polar_pod on every
axis a theme can vary. If something theme-specific were hiding in the core, it would surface here.

| Axis | polar_pod | forest_village |
|---|---|---|
| Palette temperature | cold, near-monochrome cobalt / periwinkle / pearl | warm umber, wood, straw, leaf green, brick, sky blue |
| Surfaces | glossy molded plastic, chrome (env-map), quilted vinyl, knit, fur | grained timber, plaster, thatch, stone, iron (env-map `env_iron`), patchwork quilts |
| Forms | rounded plans, domes, ovals, pods, portholes, molded window lips | rectangular plans, gables, beams, shutters, mullions, plank doors |
| Lighting rig | high ambient, cool sky fill | warmer key from a lower sun angle, almost no ground bounce |
| Cast (supplied by lane-characters) | faceless expedition figures + cats | face-atlas villagers + dog + cat |

ruins_harbor was the alternative. Its stone, water and rope would have overlapped polar_pod's ice and
snow and shared its cool colour range, so it proves less.

## Core code the second pack needed
None. forest_village is `pack.json` data only: palette and ramps, material bindings for every core role,
env maps, light rig, fog, 49 kit presets, 35 fixture slot bindings and cast references.
The same generators and the same layout (`kits/layouts/lounge.json`) render in both packs. See
`sheets/room_lounge_dual.png`. Generator geometry for the same params and seed is identical across packs;
only materials and colours differ (`geometry_sha256` in the manifest).
Packs may tighten budgets in `validator_thresholds.tri_limits`, never loosen them. `core/packs.py`
rejects a looser limit.

## Contents
- Presets (fail-closed checked by `tools/packcheck.py`): timber house plus round stone cottage, gabled
  room shell, shuttered and arched windows, plank round-top door, trestle and round stone tables, chairs
  and stools, box bed, bookshelf, barrel/crate/chest, lantern, fireplace, fringed rug, egg basket-chair,
  wooden curled bench, lectern, cart with hoop canopy, rowboat, hanging sign, skeleton key, axe, stone
  jar, leather book, piped pillow, fringed quilt, leaf particles.
- Fixtures: every layout slot (door_main, window_main, window_side, seat_*, table_*, bed, lamps, shelf,
  rug, console, container, hearth, cat_bed, pillow, blanket, plant, sign_main, small props, vehicle_main,
  boat, tree, rock, ground, water, sky, weather) maps to {generator, preset[, params]}.
- Cast: references only (`character_id` + `preset`, `supplied_by: lane-characters`). This lane builds no
  people or animals.
