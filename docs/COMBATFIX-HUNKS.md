# COMBATFIX hunks (for a merge into mergeprep-lane)

Branch `combatfix-lane`, base `f8218ecc` (mergeprep-lane, FINALINT2 rc5). Conflict check against mergeprep-lane
`8a9c60f9` (docs only since the base): `git merge-tree --write-tree --name-only mergeprep-lane combatfix-lane` exits 0,
no conflicted file. Every hunk is small and marked `COMBATFIX` in a comment. No tool, schema or tool description
changed (27 tools; guidance is in `docs/AUDIO-IMPORT.md` and `audio/combat_sfx/README.md`).

## GLIDE (P1)

`runtime/godot/actors/character.gd`

1. After `var loco_want`: `var hold := {}` (the stance a module holds: `{"clip", "key"}`) and `static var hold_cache`.
2. New `loco_held()` (the held key as a pose, read from the clip's tracks, cached, the shown pose put back) and
   `loco_upper()` (bones that move no boot take the held pose; legs, pelvis and root keep the cycle), before `loco_end()`.
3. `loco_tick()`: `loco_apply(loco_compose() if hold.is_empty() else loco_upper(loco_compose(), loco_held()))`.
4. `loco_tick()` stop end: `play_clip("idle" if hold.is_empty() else str(hold.clip))`.
5. `loco_stop()`: the settle target is the held pose (and its boot transforms) when `hold` is set, else `loco.idle` as
   before.
6. `drive(speed, still_mps, back := false)`: `loco_speed = -speed if back else speed` (the cycle plays backwards);
   start fade distance uses `absf(loco_speed)` (identical for forward motion).

`runtime/godot/modules/host.gd`

7. Combat tick: `animation.show(motion.pose, player_key(motion.pose))` -> `show_player(motion.pose)`.
8. New `show_player()` after `player_key()`: in `idle_combat` with a body that has baked locomotion tables and moves
   (ground speed from the body's move this tick, after the fight's impulse and arena clamp), the actor's cycle plays
   with the stance held (`actor.hold`), backwards when moving away from the facing (cos < -0.2, back to forward at
   cos > 0.2); a stop settles into the stance. Every other pose goes through `animation.show()` as before.

`runtime/godot/modules/animation_state.gd`

9. `release()`: clears `actor.hold`.

Bodies without baked locomotion tables, placeholder actors and every non-idle pose take the old path unchanged. Outside
combat nothing calls the new code (`hold` stays empty).

## HIT SFX (P2)

`runtime/godot/view/audio.gd`

10. `boot()`: groups rows `sfx:<event>:<n>` into `sfx_banks` (sorted keys).
11. `stop_playback()`: also stops the sfx players and clears `sfx_banks`.
12. New block after `cue()`: `SFX_VOICES` 4, `SFX_COOLDOWN` (ticks per event), `SFX_DUCK` (dB), `has_sfx()`,
    `sfx(event, variant)` (one-shot, cooldown, voice steal of the longest-playing sound, `sfx_stats`), `_process()` (music
    bus duck 0.35 s, 0.15 s release).

`runtime/godot/modules/host.gd`

13. Combat tick, after `tick_feedback = ...`: `sfx_extra = sfx_events()` only when `has_sfx()`.
14. New block before `tick_readability()`: `sfx_events()` (dodge = rolls counter rises; punch_miss = the swing's hit
    window closes with no hit; boss_telegraph = a boss enters telegraph; enemy kinds remembered for the hit mapping) and
    `combat_sfx(f)` (feedback kind + enemy kind -> event; false when the game has no sfx rows).
15. `tick_readability()`: `for f in feedback + sfx_extra:` first tries `combat_sfx(f)` and skips the stock cue when it
    played; `var played` moved above the loop (same initial value).

`adventure_maker/audio_import.py`

16. `validate_slots()`: accepts `combat_sfx`; the normalised copy carries it only when given (legacy output unchanged).
17. New `COMBAT_SFX_EVENTS`, `COMBAT_SFX_DIR`, `combat_sfx_slots()`, `combat_sfx_defaults()` (shipped set, sha256 checked
    against `audio/combat_sfx/combat_sfx.json`).
18. `runtime_rows()`: lowers `combat_sfx` to `sfx:<event>:<n>` rows `{path, sha256, gain_db: mix.sfx_db, kind: sfx}`.

`adventure_maker/assets_v3.py`

19. `imported_audio()`: a slots file with only `combat_sfx: "default"` (and `format`/`mix`) builds without an import
    manifest.

New files: `audio/combat_sfx/` (14 WAV, `combat_sfx.json`, `README.md`), `tools/combat_sfx_synth.py`,
`tests/test_combatfix.py`, `docs/COMBATFIX-HUNKS.md`, `docs/COMBATFIX-RESULT.md`, `evidence/combatfix/`.
Docs: `docs/AUDIO-IMPORT.md` gains the `combat_sfx` paragraph in section 3.

## Merge notes

- Runtime script changes move the runtime build hash (`input/movie.gd build_hash()` covers `actors/`, `modules/`,
  `view/`). Legacy movies replay in cross mode (frames and state hashes compared), as every runtime lane did.
- `audio/combat_sfx/*` is packaged by the existing `audio/*` rule (no new package rule).
