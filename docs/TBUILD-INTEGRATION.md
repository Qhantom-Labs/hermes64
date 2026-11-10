# L4 integration handoff and unowned patch requests

Main is the sole integrator. L4 changes no other worktree, runtime core, audio, wire or character source. This is not M7 or full showcase acceptance.

## Inputs still required for the rest of P3

1. **M1 / CYBERPOLISH room interchange.** The read-only cyber room data is `hermes64-room-plans/1`, six entries keyed by room id. Its rooms are larger now, but no `anchors` block was present when inspected. L4's installed path consumes `hermes64-pack-rooms/1` compiled rows. Before M7, bake the five selected rooms with the cyber compiler, preserving its computed door positions; supply explicit `hero_start`, `checkpoint`, arena bounds, eight spawn anchors, three boss anchors and captive/interaction anchors. Keep the optional sixth room as data. Rewrite the compiler's `pilgrim` character id to the chosen hero at instantiation, not in shared character code. The neutral castle data and `tools.pack_rooms` demonstrate the compiled format. Do not ship a JSON import string as an executable compiler.
2. **L2 scenes/results.** No scenes branch or `docs/SCENES.md` was available during implementation. Premise cards are validated and retained as requested data, but have no runtime consumer in this branch; results and scenes remain explicitly pending. Adopt the owner's *actual* fields once supplied, not the P0 proposal by guesswork. Likewise for texture slots/weather/media: no claim of a filled slot or played track is made.
3. **L3 overlay and M2 site pack.** `tools.make_demo` calls the real new/export handlers and has a tested qualified-development-export path. It refuses `--overlay` before creating a game because the overlay owner hook is unavailable; it does not silently copy an inert folder and call it applied. `tools.site_pack.pack` is called when that module is merged; here it is absent and its status stays not-run. There is no `site-nous` acceptance in this branch.
4. **AUDIOPIPE asset ids.** The premise contract uses the owner's real `music.default/menu/boss/results/scenes/waves/events`, voice, cues and mix vocabulary. The excluded showcase data has no audio mapping yet: real imported ids/overlay provenance must be supplied by that owner. No private audio or images were read/copied.

## COMBAT2 field adoption (tested)

The adapter uses gameplay `api_version: 1.2.0`, `movement_combat_profile: combat2_v1`, each module's version 1.2.0, `abilities.config.moveset: brawler_v1`, and `run` with `hit_invulnerability_ticks` (not the speculative `invulnerability_ticks`). A premise's `{count, gap_ticks}` budget becomes encounter `attack_budget` and `attack_gap_ticks`; `bosses` contains **spawn ids**, not archetype ids. Three legacy sequential finale challenges collapse into one encounter/challenge and the goal condition is rewired to that challenge. `encounter.label` supplies L1's actual HUD field.

A fresh isolated package with committed COMBAT2 `780acce6179828c18e91ad30fca90300284bdb1d` completed four challenges including three wardens together: PLAYABLE, conditional proof, zero softlocks, assets built. It still returned `new_game_needs_work` because of the rendered audit. This snapshot did not merge a branch or touch COMBAT2's worktree. All copied source hashes and the real receipt are in `evidence/template/combat2-adoption3/receipt.json`.

Two earlier attempts are retained: the first pinned P4 before runtime API admission was fixed; the second mixed local in-process story imports with a different `bundle_root`, yielding empty physical traces. The successful third run loads the composed package first in a fresh interpreter. These are distinct attempts, not re-labelled passes.

## Unapplied room-entry hook

`pack_rooms.instantiate` stores `hero_start` as presentation `player_start`, but the current presenter still uses its default spawn and then door/checkpoint positioning. `docs/tbuild/hero-start.patch` is a source-only request for the runtime owner: use the authored start before door-entry overrides, and retain `finalize_room_entry` capsule validation. It has not been applied to runtime source or claimed as a tested capability. Its absence does not stop the completed neutral bot, but explicit hero-start consumption remains NOT verified.

## Runtime art patch request: keep audit honest

`runtime/godot/modules/host.gd` draws flat-colour `gate`/`boss_gate` markers. The final castle sheet scores 74/100: the opening is WARN 94; the other four rooms FAIL 69 solely on cuboid-marker errors, with a fog/horizon warning. Use real pack-bound gate art in the runtime owner path, not a badge/audit exemption or removal of diagnostic metadata. L4 does not edit that file. A before/after physical and rendered probe is required; preserving the diagnostic failure is intentional until art is real.

The final neutral castle native run measured 3,474–5,856 triangles including combat, under the unchanged 6,000 cap. Earlier richer dressing exceeded it and was reduced as data. Larger rosters/NPCs/three bosses need their own live budget check; static pack estimates alone are insufficient. The sky is explicitly a `backdrop`, not a giant solid collider.

## Export determinism patch request (owner: export/integrator)

Two real builds with the same prompt and id, fresh games roots and unchanged toolkit bytes had equal game hashes. Both qualified web exports completed. The PCK differed, and so did `web/FILES.json`, `web.zip` and top-level `FILES.json`; 17 exported files existed per run. The exact SHA pairs are retained in `evidence/template/repeat/comparison.json`. Do not call A2 passed or discard these mismatches. Root cause in engine/export packing is not diagnosed here, and `adventure_maker/export.py` remains untouched.

## Windows union

The base lacks the later Windows preflight/command-line hunks. L4 leaves those regions untouched and keeps the exact Windows UTF-8 starter read. `evidence/template/legacy-text-diff.json` verifies preflight is unchanged from the tag and the old template body is unchanged. At M9 union the Windows preflight and `command_line` hunks byte-for-byte; retain MOVE's manual-audit-next-step hunk, which was absent on Windows' older base. No Windows execution is claimed.

## Showcase data only

`evidence/template/showcase/premises/teknium-vs-tyrants/` is excluded from packaging. Its validated data contains the exact 199-character prompt, 23 robots in capped groups, three bosses and 11 cards. It has not been built on cyber rooms, and camera/actor/clip/media composition still needs the owning lanes. The package ships only the neutral keep-under-siege premise. The historical package still includes the optional cameo pack under its pre-existing rules; full Q3 media/cameo leak acceptance remains an integrator gate, not a claim of this lane.
