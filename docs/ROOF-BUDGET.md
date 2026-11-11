# ROOF budget: what the 6,000-triangle cap counts, and how many fighters fit

Every number here was measured on this branch: GLB counts with `tools/glb_tris.py` (counted the way the runtime counts),
room numbers in the real runtime with `tools/roof_capture.py` (normal Service capture, then
`runtime/godot/tests/crowd_capture.tscn` on the same staged runtime). Evidence folders are `evidence/roof/round-*`
(git-ignored): b1 = the five rooms, f5 = repeat frame timings, f7/f7c = the final finale roof.

Machine: Mac mini (Mac16,11), Apple M4 Pro (14 CPU / 20 GPU cores), 64 GB, macOS 27.0.1, 4K display, Godot
4.6.2-stable. Window 960x720 showing the 320x240 game view, vsync off.

## 1. How the gate counts

- **Per room, not per frame.** The cap applies to the whole loaded room scene: `room.gd triangle_count()` walks every
  mesh under the room root (kit pieces, props, generated cards, glow and shadow quads, the sky signal, the people with
  their blob shadows), plus the player. Frustum culling does not matter: a robot behind the camera counts.
- **Only one room is loaded** (regions `load_policy: one_region`), so the cap is effectively "the scene at one moment".
- **Where it is checked:**
  - compile time: `tools/cyberkit_rooms.compile_room` estimate = kit triangles + doors + people x 760 + robots x 480 +
    overhead (200 outdoors / 80 indoors). It refuses an over-cap plan.
  - capture: `main.gd capture_all` fails a room over the cap; `adventure_maker/audit.py` reports `over_budget`.
  - module playtests: `playtest/module_runner.gd` takes the maximum of room + player + **every live combat enemy body**
    whenever the room, attempt or wave changes; `playtest.py` rates a room over the cap ROUGH.
- **Robots count.** Live enemies sit under the world, not the room, but the module playtest adds them. Defeated robots
  are moved under the room root as corpses for 90 ticks (1.5 s, `host.gd CORPSE_TICKS`), so a corpse overlaps the next
  wave briefly.
- **Rain costs 0 triangles** (2D screen-space streaks). The sky signal costs 88.
- The cap is 6,000 for every room unless the room plan names a larger **budget profile** (section 5).

## 2. Per-model cost

Robot livery note: **no `neon_city_night` robot livery exists** on any branch yet (`characters/combat/robots.json` has
`forest_village` and `polar_pod`). Liveries only change textures: the two existing liveries have identical triangle
counts, so a neon livery of the same meshes would cost the same.

| Model (template) | GLB triangles | + blob shadow (12) = runtime cost |
|---|---|---|
| `robot_porter` (walker, `walker_patrol_v1`) | 450 | 462 |
| `robot_sentry` (brute, `brute_slam_v1`) | 460 | 472 |
| `robot_drone` (drone, `hover_drone_v1`) | 456 | 468 |
| `robot_foreman` (boss, `boss_phases_v1`) | 570 | 582 |
| stand-in `reed_warden` / `cairn_dasher` (fallback art) | 464 / 488 | 476 / 500 |
| hero placeholder `fv_scribe` (player) | 720 | **732** (measured player) |
| boss placeholders `fv_warden` / `new_arrival` / `fv_elder` | 744 / 748 / 754 | 756 / 760 / 766 |
| captive placeholder `tavi` | 768 | 780 |
| other cast: `fv_smith` 696, `sol` 732, `ivo` 742, `luma` 708, `neri` 836, cats 300 | | +12 each |

The pack threshold `character_tris` is 700; every human placeholder above is 20-136 over it already.

**Per person in the finale:** hero + 3 bosses + captive = 732 + 756 + 760 + 766 + 780 = **3,794** (measured
actors 3,062 + player 732), about 760 each.

## 3. Room-only cost (no people), real runtime

Environment = room total minus player and actors (round b1, neon_city_night, view a).

| Room | Environment | + hero | Robots that fit with the hero only (472 each): under 6,000 / under 8,000 |
|---|---|---|---|
| `tower_roof` (opening) | 4,144 | 4,876 | 2 / 6 |
| `canyon` | 4,214 | 4,946 | 2 / 6 |
| `subway` | 1,900 | 2,632 | 7 / 11 |
| `club` | 2,346 | 3,078 | 6 / 10 |
| `server_room` | 2,122 | 2,854 | 6 / 10 |
| **`tower_roof_finale`** (new, trimmed) | **2,026** | 2,758 | 6 / 10 |

Waves are designed for at most 3 live robots (05C rule 3): every room fits that under 6,000, but `tower_roof` and
`canyon` go over during the 1.5 s corpse overlap if a full wave of 3 dies and 3 more spawn (4,946 + 6 x 472 = 7,778).

## 4. Capacity on the roof: the plain answer

The finale has 5 people: hero, 3 CEOs, captive.

| Finale roof setup (measured, real runtime) | Triangles | Under 6,000? | Under 8,000 (arena)? |
|---|---|---|---|
| trimmed roof + 5 people, no robots | **5,820** | yes (180 spare) | yes |
| + 1 robot | 6,282 | **no** | yes |
| + 4 robots (2 walkers, brute, drone) | 7,684 | no | **yes** |
| + 5 robots | 8,156 | no | no |
| + 6 robots | 8,624 | no | no |
| old `tower_roof` room + 5 people (for comparison) | about 7,900 (4,144 + 3,794) | no | no |

**Yes, the 6,000 cap limits the fight.** With today's models, the three CEOs, the captive and the hero use 3,794 on
their own. Even on the trimmed roof, **no robot fits** next to them under 6,000. Under the new arena profile
(8,000), **4 robots fit**. 6 robots fit under 8,000 only if robots get lighter (option b).

## 5. Options, measured

**(a) Trimmed room (done).** `tower_roof_finale` cuts the water tank, desk, chair, terminal, AC, cables, roof screen
sign, second vent, the south and far sky rings and two side towers: environment 4,144 -> 2,026 (-2,118). This alone
turns the finale from about 7,900 to 5,820, so the 5-person finale fits 6,000. It does not make room for robots
(180 spare). Cutting more sky (setback tower 336, megatower 184, needles 120) would leave 820 spare, which is 1 robot of
today's size.

**(b) Robot budget (constraint document for CHARS4).** `docs/ROBOT-BUDGET-CONSTRAINT.md`: walker 300, brute 360,
drone 260, boss-robot 450 (shadow included), humans held to the existing 700. At those sizes, finale + 6 robots =
2,026 + 3,794 + 6 x 307 (mean) = about 7,660: fits 8,000; with humans at 700 the 5 people are 3,500 and 7 robots
fit. Under 6,000 (humans at 700) the trimmed roof takes 1 light robot, or 3 with the further sky cut from (a). Not measured in the runtime (the meshes do not
exist; I do not own the robot generators, so no variants were made).

**(c) Named `arena` budget profile (done, data).** `kits/core/style_bible.json` `budget_profiles`: `default` 6,000
(unchanged) and `arena` 8,000, which a plan may use only if it has an `arena` clearance block. Read by the room
compiler, the capture gate (`main.gd`, via the compiled room's `budget` block), the audit and the playtest verdict. A
hard ceiling of 8,000 is in `main.gd`, `audit.py` and `playtest.py` (a test keeps them equal to the style bible
maximum). Rooms without the field keep 6,000 everywhere (test: every existing plan compiles with cap 6,000 and no
budget block).

Frame time, finale roof, 600 frames after 120 warm-up, two repeats (f5) plus the final room (f7):

| Triangles (robots) | GL Compatibility (export renderer): p50 / p95 / frames over 8 ms | Mobile (default `godot --path` renderer): p50 / p95 / frames over 8 ms | Draw calls (compat / mobile) |
|---|---|---|---|
| 6,014 (0) | 1.12-1.15 / 5.9-6.1 / 0 of 600 | 3.30 / 16.6-17.1 / 84-86 | 68 / 45 |
| 7,878 (4) | 1.22-1.28 / 5.7-6.3 / 0-6 | 3.21-3.38 / 16.8-17.0 / 77-88 | 80 / 53 |
| 7,684 (4, final room, one run) | 1.36 / 6.6 / 21 (p99 37 ms: a burst of slow frames in this single run) | 3.35 / 17.1 / 104 | 75 / 50 |
| 8,818 (6) | 1.27 / 6.2 / 3-8 | 3.26 / 16.3-16.8 / 88-100 | 86 / 57 |
| 17,230 (24, stress) | 1.63-1.71 / 13.4-13.5 / 33-35 | 3.33-3.38 / 16.8 / 90-100 | 140 / 93 |

(6,014 / 7,878 / 8,818 / 17,230 are round f5, whose room still had the roof screen sign: +194.)

Reading: on this Mac the compat renderer meets the 8 ms target at p95 up to about 9,000 triangles and misses it at
17,000. The Mobile renderer's p95 of about 17 ms and its 14-17 % slow frames are the same at 2,632 and at 17,230
triangles (and in all five rooms of round b1), so they come from presentation/compositor pacing on this machine, not
geometry. Render CPU time per frame stays under 0.75 ms in every case; GPU time is not reported by the Metal backend
(0).

**(d) Web export.** The web build uses the same GL Compatibility renderer over WebGL2. Measured natively as a proxy: an
8,000 room costs about 12 more draw calls than a 6,000 one (robots add about 3 surfaces each) and p95 stays at about 6
ms on this Mac. Robot count does not change download size (one GLB per robot type, shared). A browser run, an
integrated-GPU laptop or a phone was **not** measured; WebGL adds driver overhead, so the arena profile should stay
limited to rooms that declare an arena (enforced).

## 6. Recommendation

**Use (a) + (c) now, and ask for (b).** (a) makes the five-person finale fit 6,000 on its own (5,820), so even without
the profile the scene is legal. (c) is the only option that makes room for robots today: 4 robots + 3 CEOs + captive
+ hero = 7,684, with a measured p95 of 5.7-6.6 ms on the export renderer, inside the 8 ms target, while every other
room keeps the strict 6,000. (b) is the efficient long-term fix (6-7 robots under 8,000, and 1-2 under 6,000) but it
needs the characters lane to build lighter robots. Raising the default cap is not recommended: the frame-time evidence
is from one fast Mac, and the N64 look rests on the low counts.
