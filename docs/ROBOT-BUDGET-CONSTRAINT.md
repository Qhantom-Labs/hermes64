# Robot triangle budget: constraint for the characters lane (CHARS4)

From the ROOF lane (measurements: `docs/ROOF-BUDGET.md`). This is a request, not an edit: the ROOF lane did not
touch robot or character meshes.

## Why

A room's 6,000-triangle cap (8,000 for rooms on the style bible's `arena` profile) counts everything loaded at one
moment, including every live robot and, for 1.5 s, each defeated robot's corpse. On the finale roof the hero, three
CEOs and the captive already use 3,794. Today's robots cost 462-472 each (582 for the boss robot), so only 4 fit
under 8,000 and none under 6,000.

## Budget per archetype (runtime cost, 12-triangle blob shadow included)

| Archetype (template) | Today (GLB + shadow) | Budget | Notes |
|---|---|---|---|
| walker (`walker_patrol_v1`, `robot_porter`) | 462 | **300** | smallest silhouette; the most numerous robot |
| brute (`brute_slam_v1`, `robot_sentry`) | 472 | **360** | keep the big readable mass, cut detail |
| drone (`hover_drone_v1`, `robot_drone`) | 468 | **260** | floats; underside and back are rarely seen |
| boss robot (`boss_phases_v1`, `robot_foreman`) | 582 | **450** | appears alone or with 2 more bosses |
| humans (hero, CEOs, captive) | 732-780 | **700** (existing `character_tris`) | today's placeholders are 20-136 over the pack threshold |

At these budgets: finale roof (2,026) + 5 humans at 700 (3,500) + 6 robots at a 307 mean = about 7,350 (fits
8,000 with room for corpse overlap); under 6,000 the trimmed roof takes 1 light robot (474 spare).

## Constraints

1. Same rig, clips, face atlas and hit/phase data as today: only the mesh gets lighter (the combat host binds by row).
2. Every livery of an archetype shares the mesh (liveries are textures; a `neon_city_night` livery does not exist yet).
3. Keep the blob shadow at 12 triangles (`actors/character.gd`).
4. Readability first: at 320x240 a robot is 25-60 px tall from the room cameras; cut hidden faces and small bevels,
   not the silhouette, the visor (face atlas) or the attack telegraph parts (arm, launcher, slam plate).
5. Report the GLB count the runtime will see (`python3 -B -m tools.glb_tris FILE.glb` counts per mesh node, like
   `room.gd`) in the robot row (`characters/combat/robots.json`) so the room compiler's robot allowance (style bible
   `robot_tris`, now 480) can drop to the real number.
6. Offer the light variants as additional rows or presets first; the heavier ones can stay for close-up scenes.

## Not verified

The proposed budgets are arithmetic from today's measured costs; no light robot has been built or captured.
