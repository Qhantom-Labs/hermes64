# RC3-BASE small tweaks (collected, NOT fixed here)

Collected at M0 from the merged lanes' own weak-frame lists (`docs/MOVE-RESULT.md`, `docs/CAM-RESULT.md`,
`docs/FEEL2-RESULT.md`, `docs/LIVEFIX-RESULT.md`) and from what the RC3-BASE verification touched. The owner's
play note on play-fix4 (move-lane 2443ba4f): "walls better, movement and camera a lot better; small tweaks
remain". His own list is still to be collected; this file is the agent-side list for that session. None of
these items is fixed on `rc3-lane`. Each is a general plugin feature (per `PRODUCT-PRINCIPLE.md`), not a
demo hack.

## Camera

1. **No camera collision on curved shell meshes.** The orbiting lens can pass outside a curved shell wall
   (Thaw dome: a third to half of the frame black void in `wso-W-orbit-23`, `S+L-orbit-t013/t062`). Predates
   MOVE; more visible now that the player stops at walls. Likely fix: derive camera collision (or a lens
   clamp) from the same floor outline MOVE uses for the player capsule.
2. **Foreground occluders hide the player.** Tree trunk (Relay `W-orbit-08`), course boulder, fence/canopy/
   rail/pole during reversal and circle. Static-collider pull-in exists; occluder fading/transparency does not.
3. **Puzzle Hall near-wall spawn hides most of the player** (reported by CAM, FEEL2 and LIVEFIX). Spawn camera
   yaw/offset or near-wall fade.
4. **Low, close lens at walls** (Thaw `wall-W-bump`) and **player at frame edge** on side bumps (Thaw
   `wall-D-bump`). Pull-in could keep a minimum framing height and recentre laterally.
5. **Orbit-key response is the weakest direction metric** (min dot 0.49 for orbit keys, 0.59 mouse orbit,
   0.60 hold-S; everything else >= 0.78). Within budget, but the first place to look if the owner still finds
   orbit-while-walking confusing.
6. **Crowded Workstation arrival** after the Thaw door; E-prompt overlaps the player in some frames.

## Collision edges

7. **Kit rooms have no walkable outline.** MERGE6 genre-kit pieces (sci-fi, ancient, medieval, western,
   dungeon) carry no walkable outline in metadata, so MOVE falls back to the grid-rect clamp there. Rooms
   generated from those kits were never run under `move_walls` or `feel2_connectivity` (the tools only stage
   the five shipped games). Plan 03 phase A step 4 asks for that cross-check; it is NOT done at M0 (see
   `docs/RC3BASE-RESULT.md`). First follow-up: derive outlines from kit shell metadata, then run the wall bot
   and connectivity on one generated game per kit.
8. **Capsule margin at curved walls** is 0.2599 m minimum (Thaw pod bay). Fine for walls; check that thin
   column/plinth contact (FEEL2 weak view) does not read as floating or clipping.
9. **Relay hub door is story-locked at start**, so `move_screen` records the door as unavailable there. A
   door-after-unlock scenario would cover it.
10. **Puzzle Hall first W step is short** (grid movement) and its strip tiles sort alphabetically in review.

## Tooling (small)

11. `tools.move_tests` / `tools.move_replays` stage only the five shipped games (`feel2_solids.GAMES`);
    accepting a generated project path would make item 7 a one-line run.
12. `tools.move_replays cross` needs `evidence/move/baseline-replays/`, which is git-ignored; RC3-BASE copied
    MOVE's movies from `wt-move` (sha256 listed in the result doc). Shipping the five baseline movies as test
    fixtures would make the replay check reproducible from a clean clone.
