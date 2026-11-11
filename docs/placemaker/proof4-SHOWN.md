# PLACEMAKER proof: what is shown

Real runtime frames from the plugin's normal Service path (scaffold, compile, check, build_assets, open with screenshots) in a scratch bundle clone. Numbers only; how it looks is for Dylan to judge.

Run: `python3 -B -m tools.place_maker proof --requests docs/placemaker/proof-requests.json --run proof4` (report: `evidence/placemaker/proof4/report.txt`, git-ignored).

## Files

- `castle_great_hall-sheet.png`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group).
- `cyber_subway_platform-sheet.png`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group).
- `forest_clearing_camp-sheet.png`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group).
- `western_main_street-sheet.png`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group).
- `wizard_tower_interior-sheet.png`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group).
- `hero-1-hall_b.png`: hero shot, hall_b (castle_great_hall), camera a, nearest-neighbour upscale, numbers strip.
- `hero-2-wizard_a.png`: hero shot, wizard_a (wizard_tower_interior), camera a, nearest-neighbour upscale, numbers strip.

Hero selection rule: highest reference-band score among rooms that passed every check, two different archetypes, ties by name. A numbers rule, not a look ranking.

## Rooms

| room | archetype | size | mood (pack) | clutter | seed | runtime tris | clear sq. m (rule) | reachable | coverage | style gate | n64 | band | attempts (renders) | all checks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| camp_a | forest_clearing_camp | small | golden_hour (medieval_village_golden_hour) | 1 | 3 | 4230 | 4.27 (4.00) | 2/2 | 0.343 | passed | passed | 0.71 | 1 (1) | yes |
| camp_b | forest_clearing_camp | large | purple_dusk (medieval_village_purple_dusk) | 2 | 8 | 5080 | 5.02 (5.00) | 2/2 | 0.301 | passed | passed | 0.71 | 1 (1) | yes |
| camp_c | forest_clearing_camp | large | ember_night (medieval_village_ember_night) | 1 | 13 | 4422 | 5.52 (5.00) | 2/2 | 0.258 | failed | passed | 0.71 | 3 (3) | no |
| hall_a | castle_great_hall | medium | golden_hour (castle_keep_golden_hour) | 1 | 2 | 4802 | 6.52 (4.60) | 3/3 | 0.211 | passed | passed | 0.86 | 1 (1) | yes |
| hall_b | castle_great_hall | medium | ember_night (castle_keep_ember_night) | 2 | 6 | 5368 | 6.52 (4.60) | 3/3 | 0.216 | passed | passed | 1.00 | 1 (1) | yes |
| hall_c | castle_great_hall | medium | purple_dusk (castle_keep_purple_dusk) | 3 | 10 | 5656 | 6.52 (4.60) | 3/3 | 0.235 | passed | passed | 1.00 | 1 (1) | yes |
| street_a | western_main_street | small | base (frontier_town) | 1 | 2 | 5324 | 9.27 (5.00) | 4/4 | 0.043 | passed | failed | 0.43 | 3 (3) | no |
| street_b | western_main_street | medium | golden_hour (frontier_town_golden) | 2 | 5 | 5840 | 10.27 (6.00) | 4/4 | 0.042 | failed | passed | 0.29 | 3 (3) | no |
| street_c | western_main_street | large | purple_dusk (frontier_town_purple_dusk) | 1 | 9 | 5636 | 10.27 (6.00) | 4/4 | 0.028 | passed | passed | 0.57 | 1 (1) | yes |
| subway_a | cyber_subway_platform | small | base (neon_city_night) | 1 | 1 | 2368 | 6.52 (3.40) | 4/4 | 0.063 | passed | passed | 0.57 | 1 (1) | yes |
| subway_b | cyber_subway_platform | large | neon_dawn (neon_dawn) | 2 | 4 | 3082 | 12.02 (7.00) | 4/4 | 0.044 | failed | passed | 0.86 | 3 (3) | no |
| subway_c | cyber_subway_platform | large | ember_night (neon_city_night_ember_night) | 1 | 11 | 2802 | 12.52 (7.00) | 4/4 | 0.027 | passed | passed | 0.86 | 1 (1) | yes |
| wizard_a | wizard_tower_interior | small | purple_dusk (castle_keep_purple_dusk) | 1 | 3 | 3086 | 6.02 (2.60) | 3/3 | 0.082 | passed | passed | 1.00 | 1 (1) | yes |
| wizard_b | wizard_tower_interior | medium | ember_night (castle_keep_ember_night) | 2 | 7 | 5404 | 8.02 (4.00) | 3/3 | 0.087 | passed | passed | 1.00 | 1 (1) | yes |
| wizard_c | wizard_tower_interior | medium | golden_hour (castle_keep_golden_hour) | 1 | 12 | 4680 | 8.27 (4.00) | 3/3 | 0.149 | passed | passed | 0.86 | 1 (1) | yes |

Camera b frames (second standard camera), gates on that frame:

| room | style gate | n64 | band | runtime tris |
|---|---|---|---|---|
| camp_a | passed | passed | 0.57 | 4230 |
| camp_b | passed | passed | 0.57 | 5080 |
| camp_c | failed | passed | 0.57 | 4422 |
| hall_a | passed | passed | 0.86 | 4802 |
| hall_b | failed | passed | 1.00 | 5368 |
| hall_c | failed | passed | 1.00 | 5656 |
| street_a | failed | failed | 0.57 | 5324 |
| street_b | passed | passed | 0.29 | 5840 |
| street_c | failed | passed | 0.71 | 5636 |
| subway_a | passed | failed | 0.71 | 2368 |
| subway_b | failed | passed | 0.86 | 3082 |
| subway_c | failed | passed | 0.86 | 2802 |
| wizard_a | passed | passed | 1.00 | 3086 |
| wizard_b | failed | passed | 1.00 | 5404 |
| wizard_c | passed | passed | 0.86 | 4680 |

## Attempts that changed something

- camp_c #1: style gate: accent overuse: 33.7% accent pixels (max 15%) -> seed re-roll
- camp_c #2: style gate: accent overuse: 35.4% accent pixels (max 15%) -> seed re-roll
- street_a #1: n64: neon colour: 2.08% saturated very bright pixels (max 1.00%) -> light -0.07
- street_a #2: n64: neon colour: 1.72% saturated very bright pixels (max 1.00%) -> light -0.07
- street_b #1: style gate: depth layering: 3/3 near/mid/far bands present, value range 0.509 (min 0.08), smallest gap 0.027 (min 0.03) -> clutter +1
- street_b #2: style gate: depth layering: 3/3 near/mid/far bands present, value range 0.503 (min 0.08), smallest gap 0.021 (min 0.03) -> light -0.07
- subway_b #1: style gate: low contrast: luma p95-p5 = 0.345 < 0.38 (washed out; add darks/highlights) -> contrast +0.1 (ambient down, key up)
- subway_b #2: style gate: low contrast: luma p95-p5 = 0.346 < 0.38 (washed out; add darks/highlights); fog flattens the frame: 20% of drawn (non-sky) pixels sit within 0.07 of the fog colour (max 20%) -> contrast +0.1 (ambient down, key up)

## Gaps and recipes per room

- camp_a: recipes wprop.campfire; not in library tent, bedroll; trimmed 0; short rocks 1/2, bushes 0/2
- camp_b: recipes wprop.campfire; not in library tent, bedroll; trimmed 0; short cart 0/1, bushes 1/3
- camp_c: recipes wprop.campfire; not in library tent, bedroll; trimmed 0; short none
- hall_a: recipes none; not in library none; trimmed 0; short banners 2/3, pillars 4/5
- hall_b: recipes none; not in library none; trimmed 0; short banners 2/4, pillars 4/5, tables 2/3
- hall_c: recipes none; not in library none; trimmed 0; short banners 2/5, tables 2/4, tableware 2/3, stores 3/5
- street_a: recipes none; not in library horse, tumbleweed; trimmed 1; short none
- street_b: recipes none; not in library horse, tumbleweed; trimmed 3; short wagon 0/1
- street_c: recipes none; not in library horse, tumbleweed; trimmed 1; short none
- subway_a: recipes none; not in library escalator, route map, ticket machine; trimmed 0; short benches 0/1
- subway_b: recipes none; not in library escalator, route map, ticket machine; trimmed 0; short crates 1/2
- subway_c: recipes none; not in library escalator, route map, ticket machine; trimmed 0; short none
- wizard_a: recipes dprop.crystal; not in library potion, spellbook, telescope, rune circle, wand, rotunda; trimmed 0; short shards 0/1
- wizard_b: recipes alien.crystal, dprop.crystal; not in library potion, spellbook, telescope, rune circle, wand, rotunda; trimmed 0; short stair 0/1
- wizard_c: recipes dprop.crystal; not in library potion, spellbook, telescope, rune circle, wand, rotunda; trimmed 0; short crystals 1/2

## Approval mechanism (synthetic, scratch store; nothing approved by a human)

- castle_great_hall: synthetic approval of hall_a (golden_hour). Same room from camera b (same style): palette 0.044. Other rooms (other moods) palette / layout: hall_b ember_night 0.374 / 0.065; hall_c purple_dusk 0.412 / 0.146. Known-bad control (inverted frame + clutter-3 layout): palette 0.674, layout 0.147. Approved examples offered (synthetic excluded): 0.
- cyber_subway_platform: synthetic approval of subway_a (base). Same room from camera b (same style): palette 0.096. Other rooms (other moods) palette / layout: subway_b neon_dawn 0.197 / 0.311; subway_c ember_night 0.421 / 0.437. Known-bad control (inverted frame + clutter-3 layout): palette 0.457, layout 0.110. Approved examples offered (synthetic excluded): 0.
- forest_clearing_camp: synthetic approval of camp_a (golden_hour). Same room from camera b (same style): palette 0.058. Other rooms (other moods) palette / layout: camp_b purple_dusk 0.443 / 0.076; camp_c ember_night 0.323 / 0.188. Known-bad control (inverted frame + clutter-3 layout): palette 0.432, layout 0.104. Approved examples offered (synthetic excluded): 0.
- western_main_street: synthetic approval of street_a (base). Same room from camera b (same style): palette 0.046. Other rooms (other moods) palette / layout: street_b golden_hour 0.321 / 0.100; street_c purple_dusk 0.349 / 0.257. Known-bad control (inverted frame + clutter-3 layout): palette 0.289, layout 0.210. Approved examples offered (synthetic excluded): 0.
- wizard_tower_interior: synthetic approval of wizard_a (purple_dusk). Same room from camera b (same style): palette 0.059. Other rooms (other moods) palette / layout: wizard_b ember_night 0.449 / 0.170; wizard_c golden_hour 0.446 / 0.340. Known-bad control (inverted frame + clutter-3 layout): palette 0.647, layout 0.323. Approved examples offered (synthetic excluded): 0.
