# L4 / L2 integration handoff (no protected-file edits)

READY data surface: docs/COMBAT-MOVESET.md and contracts/gameplay/1.2.0/*.json.

TEMPLATE/newgame.py owner: upgrade the arena template's gameplay and every module.version to 1.2.0; set movement_combat_profile combat2_v1; abilities.config.moveset brawler_v1. Copy authored run slots to gameplay.run including required hit_invulnerability_ticks. Emit one challenge/checkpoint per story wave and finale. For a simultaneous finale use encounter.bosses, attack_budget and attack_gap_ticks (not three separate boss challenges). Keep singular boss empty/omitted for a trio. Label goes on encounter.label. Demo values and rosters stay premise data. This lane intentionally does not touch templates.py or newgame.py.

05C data values: health 3, penalty 600, hit_invulnerability_ticks 45, true reset/pause policies, finale attack_budget 1 / attack_gap_ticks 30. The seven robot rows and three boss rows fit the existing 16-archetype cap; no code branches by row name. Bosses are existing boss_phases_v1 patterns surge/shot/slam; no new enemy-specific script needed.

SCENES/RESULTS owner: host.run.snapshot() has integer ticks, deaths, finished_tick (-1 unfinished), started, penalty_flash and checkpoint_flash. Freeze presenter.simulation_enabled during cards. First control excludes action-menu selection by design. Last enemy KO freezes time before hitstop; rescue may follow without clock change. Timed run state is in the movie extension. Results may read it, but must not mutate it.

AUDIOPIPE owner: music.boss ends on encounter_cleared rather than the first boss_defeated for multi-boss encounters. This is a request, not a claim that audio integration is done.

Web/export owner: move the notices link outside the game canvas / into pause-page UI; no browser/export ownership changes made here. New HUD supplies three boss bars, outlined health, run digits, penalty amount and checkpoint blink. Door-light cue and polished penalty merge animation are not implemented here.
