# P0 spike / baseline

Base: rc3-base-1 (cea2fe88). Read product principle, definition of done, schedule, plans 02, 05B and 05C. 05C supersedes older demo values: budget 1, gap 30, +600 ticks, four challenge checkpoints, hit protection 45 ticks.

## Findings before implementation

- Admission in `story/modules/validation.py:89` requires the list of boss spawns to equal exactly the singleton `encounter.boss`. Three real boss rows cannot compile. The runtime already instantiates a Robot for each spawn, so no separate boss controller is necessary.
- `robot.gd:start_attack` has no concurrency guard. Three bosses can all enter telegraph on the same tick. Guard attack acquisition there with a shared, saved encounter budget; keep the old path when profile is absent.
- Existing `hurt_age` prevents successive melee/hazard hits only during the 18-tick hurt state. There is no separate 45-tick protection timer.
- `host.gd` owns challenge retry (60 ticks), checkpoint placement, and combat snapshot registration. Run timing must be integrated there and into movie capture, not attached to the HUD.
- New simulation profile will be `combat2_v1`, opt-in via gameplay API 1.2.0 `movement_combat_profile`; old API versions omit it and retain old snapshot shapes and reducer branches. No changes to player movement, walls, follow camera, input IDs or defaults.

## Baseline evidence and gaps

`evidence/combat2/p0-native/`: combat_robots passes (67 checks). The first generic runner incorrectly supplied city fixtures and no staged art to merge3_combat; merge5_robots and combat_trace need different production staging/configuration and timed out. These are harness setup failures, NOT baseline product failures and NOT counted as passing. Their attempts are retained. Run proper wrappers in final verification.

The six physical movie files listed by docs/FEEL2-REPLAYS.json (five games, two Thaw endings) are absent in this checkout. Thus the older FEEL2 full-movie comparison was NOT verified at P0. Do not fabricate replacement historical movies. Legacy reducer snapshots can still be compared on identical test inputs to the recorded base-stage copy.

Later custody recovery: the five M0-adopted MOVE movies were found read-only in wt-rc3 (not the six older FEEL2 paths). Their full original SHA values match the prefixes in docs/RC3BASE-RESULT.md. Copies under evidence/combat2/tag-replays/inputs were compared against the actual rc3-base-1 runtime and this lane at 30/60/144: 15/15 identical results; no movie bytes or hashes re-pinned here. The two Thaw inputs are MOVE's already-adopted wall-clip re-pins. See tools/combat2_tag_replays.py and tag-replays/summary.json for custody and scope.

No runtime production code changed during P0.
