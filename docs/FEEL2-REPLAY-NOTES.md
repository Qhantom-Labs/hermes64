# FEEL2 deliberate replay adoption ledger

## Resumed run, once

`evidence/feel2/replay-resume-01/summary.json`, exit 0: all five physical goal bots passed; six movies; 12 cold strict playbacks; 12 additional 30/144-cap strict runs; three 30/60/144 flat-floor witness runs; two legacy strict runs. No failures, stuck targets or unreachable targets. All **six movie SHA-256 values exactly match** pre-resume `replay-final-03`: no new simulation change or hash re-pin was introduced during the subscription resume.

These full-game movies are deliberately adopted **new collision-aware FEEL2 routes**, not patched historical M5/LIVEFIX expectations. The comparator stored in the machine ledger is the earlier FEEL2 `solids/inherited-bots-final` run, which already had collision. Differences from that intermediate run must not all be called collision-only regressions.

| Movie adopted (game / file) | Frames | Why adopted; what actually differs from the intermediate FEEL2 predecessor |
| --- | ---: | --- |
| Thaw / `winning-0.h64movie.json` (Quiet Night) | 3859 | Solid-aware NPC/prop-edge route, reciprocal safe doorway placement and transition latch reset; flat-floor adhesion. Earlier 3556-frame route differs from frame index 95; 65 checkpoints differ. A direct walk to an NPC/desk's original interior coordinate is no longer a valid physical route. |
| Thaw / `winning-1.h64movie.json` (Thaw) | 3861 | Same physical/entry changes on the other complete ending witness. Earlier 3558-frame route differs from index 95; 65 checkpoints differ. Retained original intermediate bytes, not replaced checkpoints. |
| Reedland Relay / `modules.h64movie.json` | 2728 | Solid-aware combat/course/portal journey, safe entries and fixed input-release boundary. Old intermediate 2816-frame route differs from index 63; 46 checkpoints differ. In addition, the exact old fixed-input route exposed native flat-floor recovery at tick 1031/144 cap; that separate physical nondeterminism was fixed, not hidden by a hash edit. |
| Reedland Combat / `modules.h64movie.json` | 926 | Adopted integrated input-snapshot/doorway boundary pin; 16 checkpoints differ, early differences are Actions rather than motion. Same length as predecessor, first input difference index 887. **No evidence that collision blocked this particular predecessor**; do not classify it as a collision-forced reroute. |
| Puzzle Hall / `modules.h64movie.json` | 2270 | Input-snapshot/integrated build pin. **Every input frame is unchanged**; 38 checkpoints differ, starting with Actions. No collision-forced reroute claimed. Native grid-cell/segment clearance is a separate gate. |
| City Arena / `modules.h64movie.json` | 4042 | Solid-aware district/boss journey with safe entry/latch and flat-support motion. Earlier 3965-frame intermediate movie differs from index 641; 68 checkpoints differ. No per-object attribution is inferred from a changed state hash alone. |

Hashes, predecessor SHA-256s and all changed checkpoint fields: `docs/FEEL2-REPLAYS.json` (regenerated from the selected resumed receipt by final verifier).

## Other deliberate pins

- **Actual pre-FEEL2 controls movie**, `evidence/feel2/run/legacy-controls-movie.json`: original bytes preserved (`f8b3afe37002b436041c581a1a6f69945f4d2347cecf20db79652f647280e6e7`), same 240 physical input frames and stable old action IDs. First three expected hashes still match; original checkpoint 240 is explicitly rejected with player-state divergence. Re-recording the same frames deliberately adopts the new portal/placement physical state; both strict playbacks pass. This is not described as a proven prop-blocked route, because that receipt establishes only a player-state difference.
- **Flat-floor witness**, `tests/fixtures/feel2_floor_rate_input.json`: exact 1120-frame retained prefix. Same frames re-recorded, then strict 30/60/144 equality; not a winning-path claim and not a collision workaround.

## Regression: the old straight-through route really is blocked

`runtime/godot/tests/feel2_solids.gd` drives ordinary production motion directly at a placed crate, tests the module impulse too, and checks glancing slide/no penetration. Retained behavioral RED `solids/attempt-01-room-red.json` has straight walk x=11.6 and unblocked impulse x=11.0. GREEN `attempt-02-room.json` has straight walk x=5.3891 and collision-stopped impulse x=5.375. The current connectivity/solids stage reruns that regression without removing a collider or changing the route assertion.

No historical M5/LIVEFIX movie files/checkpoint arrays were available for literal cross-build comparison. Existing receipts do not become those unavailable bytes. All required goals were re-recorded with production input and strict verified; production movie game/build guards remain strict. Only the explicitly named cross-build test helper rebinds a build header in memory; it never changes original frames or expected hashes.
