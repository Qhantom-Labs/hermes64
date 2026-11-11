# UI5 jump proposal (small; not implemented)

**Confirmed:** there is no general jump system. `docs/AUTHORING-SCOPE.md` (Out of scope) says: "No general authored
jump/air-control/vertical traversal system. Flat X/Z room layouts and on-foot checkpoint spheres are not a
platformer." There is no `jump` input action (`runtime/godot/input/actions.gd` `NAMES`), and no `jump` clip in any rig
clip pack (`rigs/human16_v1` has block, carry, death, hurt, idle, idle_combat, interact, roll, run, sit, swing,
talk, walk). The bound player cast (e.g. `fv_scribe`, body `human_base_v1`) lists the same set.

## Minimal hop (step over a low obstacle; no platforming, no air control, no ledges)

| Piece | What it needs | Where |
|---|---|---|
| Input | New action `jump` appended after the existing IDs (old movie IDs unchanged), default Space outside combat/course. Space is `dodge` today and combat/course own it, so `jump` resolves only in `gameplay` with no module owning input | `input/actions.gd`, `input/profile.gd` defaults, `keyhud.json` row + hint |
| Controller | On a grounded `just_pressed("jump")`: `velocity.y = sqrt(2 g h)`, with h ≈ 0.45 m (g 9.8 → 2.97 m/s, about 0.6 s airtime). Horizontal velocity frozen at take-off (no air control). One jump until grounded; the coyote 0.10 s and buffer 0.10 s tuning already exist. The existing gravity integration in `player.gd` line 165 lands it. `step_height` 0.18 m and `floor_snap` 0.15 m unchanged | `view/player.gd` (`_physics_process`) |
| Collision | Capsule unchanged. Obstacles a hop clears are solids at most 0.4 m high, a new `hop` flag on solid footprints. Taller solids still block (they act as walls). `solid_navigation` treats hop solids as passable for reachability with a jump edge, so bots/proofs stay valid | `view/solid_footprints.gd`, `view/solid_navigation.gd`, kit metadata |
| Animation | A `jump` clip (crouch 3 f, air loop, land 4 f) authored into `human16_v1` clips (Blender clip pipeline). Until then, reuse the first frames of `roll` as a stand-in, flagged | rig clip pack, `modules/animation_state.gd` |
| Replays | The new action changes movement only when pressed. Legacy movies never press it, so the 15 comparisons should hold (to be proven by re-running them). New movies record `jump` frames; the snapshot gains no field (velocity.y is already physical state) | `input/movie.gd` (no change expected) |
| Authoring | Story data unchanged. Rooms opt in by placing `hop` obstacles; AUTHORING-SCOPE keeps "no platformer" | docs |

Estimate: about 60–100 lines of runtime code plus one clip. Tests: grounded/airborne/coyote/buffer unit cases,
hop over a 0.35 m solid and fail on a 0.6 m one, the 15 replay comparisons, and a movie with jumps played at
30/60/144 fps.
