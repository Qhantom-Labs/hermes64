# Combat moveset and arena runs (gameplay API 1.2.0)

**READY contract for TEMPLATE and SCENES/RESULTS.** Core is theme-neutral. Do not put demo identities, counts, room names, tuning or story lines in runtime code.

## Opt-in and compatibility

Story contract stays 1.2.0. New gameplay manifest/module version is 1.2.0. Set `gameplay.movement_combat_profile` to `combat2_v1`; set abilities module `config.moveset` to `brawler_v1`. New fields require the profile. An API-1.2.0 manifest without new fields uses the legacy reducer. API 1.0.0/1.1.0 contracts are unchanged. No new tool/input actions/default tuning. Player/camera/wall files are unchanged.

The profile is compiled into the game and therefore pinned by the movie's existing game hash. New combat state is included only for combat2_v1, under `combat2` in snapshot/extra_snapshot. Legacy snapshot shapes are unchanged. The build hash still changes when runtime sources change: production cross-build checks are NOT waived.

## Five moves (all 60 Hz integer ticks)

| Move | Input | Windup/active/recovery | Damage | Displacement |
|---|---|---|---|---|
| jab | primary edge | 5/5/9 | 1 | .18 m |
| cross | primary edge during jab recovery | 5/5/9 | 1 | .18 m |
| finisher | primary edge during cross recovery | 8/7/16 | 1, up to 3, wider arc | .30 m; knockback 1.2 m |
| charged | hold primary at least 24 simulation ticks, release after initial jab | 0/8/20 | 2; bypasses armour | 1 m |
| running | primary edge with run held and actual speed >2 m/s | 4/8/18 | 1 | 2.2 m |

Chain input queues the next move but never cancels recovery. A held button does not repeat jabs. Roll/block/focus and swing deflection remain. Parry was implemented last, after P5: a front-facing secondary guard pressed at most 8 ticks before contact takes no damage, staggers a melee attacker for 30 ticks, and reflects contacting deflectable shots. Contact at tick 8 parries; tick 9 only blocks. Parry timers/staggers are saved in combat2 state. Optional clips `swing2`, `swing3`, `charge`, `dash_attack` fall back to `swing`; `parry` falls back to `block`; REQUIRED stays unchanged. Keys 5-7 always coincide with active ticks. Real bespoke clips belong to CHARS3, not this lane.

## Run block

Optional `gameplay.run` is closed and requires: `clock: first_control_to_last_challenge`, `death_penalty_ticks` (0..216000), `max_health` (1..64), `reset_encounter_on_death: true`, `pause_clock_in_cutscene: true`, `hit_invulnerability_ticks` (18..600). Unsupported false policies are rejected, not silently ignored. Values are authored data. Run health overrides abilities health when present.

The host exposes `host.run.ticks`, `.deaths`, `.finished_tick` (-1 until finish), `.started`; `snapshot()` returns these plus saved HUD cue ages. Movie/save-state extension capture includes `run` only when enabled. `state_hash()` includes it. Clock begins on first movement/combat control, increments during the 60-tick retry countdown, adds the penalty once per failed attempt, pauses under the existing simulation/modal gate, and freezes on the last enemy KO tick (before defeat hitstop). In a sequence with courses, the final course completion is also a finish line. Ordinary checkpoint files remain finite story saves, not authenticated timed run records.

One challenge per story wave and finale, each with its own checkpoint. The existing macro failure/retry preserves completed challenges, resets failed encounter actors and refills health. No per-game retry code is needed. `host.run.checkpoint_flash` supplies the 90-tick three-blink cue; `penalty_flash` supplies 45-tick amount and 60-tick clock emphasis. Penalty applies to authority immediately; HUD never drives score.

## Multi-boss encounter fields

`bosses`: unique array of 0..3 boss spawn IDs, alternative to nonempty singular `boss`. Every boss spawn must be named and in the final internal wave. `attack_budget`: 1..3; optional, absence retains unlimited behavior. `attack_gap_ticks`: 0..600; gap after the last windup/active ends before another begins. `label`: optional display text for L2. Singular boss and gate remain valid.

Budget admission is before telegraph in Robot.start_attack and in the original melee templates' approach transition. A stable saved request queue prevents starvation. Dead/stale requests expire. All windups/active states count; lingering projectiles/rings do NOT occupy a budget slot. Three HUD bars retain authored boss order, including emptied bars. Optimistic checker acceptance of multiple bosses currently requires budget 1 / gap >=30; wider overlapping attacks are honestly rejected, not claimed safe. Bounds account for the armour-breaking 2-damage strike but are not fairness/human acceptance evidence.

## Integration boundaries

- L2: read host.run snapshot; pause simulation during scene cards via existing simulation_enabled/modal gate; no wall-clock scoring. Read encounter.label for wave title. One boss_defeated event per boss; encounter_cleared only after all spawns.
- L4: use these versioned data fields in arena_run_v1. No edits here to templates.py/newgame.py/premise files owned by that lane. Adoption request is docs/COMBAT2-TEMPLATE-HANDOFF.md.
- AUDIOPIPE: consume encounter_cleared for end-of-encounter music, not first boss_defeated. No audio code edited.
- Browser notices remain owned by web/export UI: removal from canvas is an integration request, not silently changed here.

## Verification boundary

Evidence under evidence/combat2; native tests cover chain, charge/armour, running distance, recovery save restore, optional fallback, hit protection, run arithmetic, budget concurrency/gaps and anti-starvation. See COMBAT2-RESULT.md for exact final runs and unresolved acceptance. Historical FEEL2 movie bytes are unavailable in this checkout. No human-feel, hardware FPS, Windows or final demo claim is supplied by headless tests.
