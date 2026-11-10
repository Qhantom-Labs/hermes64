# Combat art (imported in MERGE3)

Source: `lane-combat-art/published` (lane executor `claude-opus-5-5`), manifest sha256 `4705f007608ea8c467a368a221cfd1d75a8b356d05664de4d17eb65bc3f729ed`, `SHA256SUMS` sha256 `84550f1b6a1a5f5ed9cecf390d6bef07280e8e6609c77cfb0013f703af4a555e`. Read with the lane's `FINAL-HANDOFF.md`, `BINDING-PROPOSAL.md` and `RESULT.md`. No human art approval is claimed.

## What was imported

| Item | Count | Where | Budget (measured on import) |
|---|---|---|---|
| Combatants (8 masked residents + 8 face-heads), six clips appended: `idle_combat`, `swing`, `hurt`, `death`, `roll`, `block` | 16 | `characters/assets/<pack>/` | body < 700 tris (max 696) |
| Other cast rows (animals, studies, the restricted cameo) | 13 | unchanged r21 bytes | as r21 |
| Enemies `cairn_dasher` (`melee_dash_v1`, rig `dasher16_v1`) and `reed_warden` (`melee_approach_v1`, rig `warden15_v1`), seven FSM clips each, per pack | 4 | `characters/combat/enemies/<pack>/` | < 500 tris (488 and 464) |
| `trail_staff` weapon (`kit_acc_hand_r_trail_staff`, slot `hand_r`) and `reed_burr` projectile, per pack | 4 | `characters/combat/props/<pack>/` | <= 200 tris (190 and 96) |

The cameo `cameo_visor_01` stays internal-only (gitignored, never staged or exported) and is not a combatant.

## Import path and checks

```sh
python3 -B tools/import_characters.py --source ../lane-combat-art/published
```

The repository's own importer (`tools/import_characters.py`) validates everything before the first write:

- every character row as before (hashes, gate/audit, triangle budgets, restricted rows);
- `SHA256SUMS` lists exactly the exported GLBs and every hash matches, and it agrees with the manifest;
- enemy rows: body triangles < 500 and equal to the manifest, joint and clip inventory, STEP keys, no animated `root` joint (no root motion), a complete FSM state → clip map; prop rows: one rigid unanimated mesh, <= 200 triangles, the named node present; at least one weapon;
- over an existing import, a character file may change only if the manifest declares the change (`changed_hashes_vs_published_r21`, old and new hash) **and** the new GLB keeps every old BIN byte and every old glTF JSON object, appending exactly the six combat clips; no existing character may be dropped.

Result (`evidence/merge3/import-01.json`, verified independently against `SHA256SUMS`): 37 GLBs checked, 0 mismatches, 16 declared additive changes, 13 r21 files byte-identical, 22 bindings (10 bound to combatants now list 13 clips). A second import is byte-identical (`tests/test_characters_combat_import.py`).

The 16 changed files (published-r21 → combat, sha256 prefixes):

| File | r21 | combat |
|---|---|---|
| `polar_pod/new_arrival.glb` | `83f2bf239dc0` | `c9acb9be1f57` |
| `polar_pod/tavi.glb` | `2d909540a596` | `be7accc1c123` |
| `polar_pod/neri.glb` | `57c2e6327eb2` | `a8d0bd219d22` |
| `polar_pod/sol.glb` | `b55e112780d5` | `49b8d95034e4` |
| `polar_pod/ivo.glb` | `6a78ebd039f4` | `ced5ee5b449a` |
| `polar_pod/luma.glb` | `86869ce3acbd` | `5a0130cf5f34` |
| `polar_pod/study_07.glb` | `5f712e1e47b5` | `f6541597f4aa` |
| `polar_pod/study_08.glb` | `ba246c6bd326` | `acad0174da18` |
| `polar_pod/pp_engineer.glb` | `291f57d02119` | `0b63c5b59aee` |
| `polar_pod/pp_medic.glb` | `5dd3979b26d9` | `463883637f90` |
| `polar_pod/pp_kid.glb` | `e146a8483ab5` | `8a2d20207b16` |
| `polar_pod/pp_elder.glb` | `d945ae5727b5` | `46a91617ab97` |
| `forest_village/fv_warden.glb` | `4d6cd0088499` | `568a9e41e0a5` |
| `forest_village/fv_smith.glb` | `a9781555507b` | `7b52c0714c89` |
| `forest_village/fv_elder.glb` | `5d6de6958e2a` | `043b48eb0994` |
| `forest_village/fv_scribe.glb` | `39eb0dcfcaab` | `622fae8343ce` |

Mesh, skin, textures and the seven shared clips are unchanged, so exploration renders (room looks, goldens) are not expected to move; any golden difference would be a candidate only. Checked after the import: the roomlook capture of Thaw and Last Light matches MERGE2's within MERGE2's own run-to-run variation, with identical gate and golden statuses, so there are no candidates ([MERGE3-LOG.md](MERGE3-LOG.md), Roomlook).

## Runtime binding

`characters.integration.stage_runtime` now also writes `combat.json` (`stage_combat`): the enemy models of the staged kit pack (Thaw → `polar_pod`; Last Light/Reedland's `n64_v0` → `forest_village`), the staff per character pack, the grips of the public combatants and the clip phase metadata, each GLB hash-checked. Export copies the referenced GLBs as hash-pinned media; the physical playtest receipt pins them. Contract and behaviour: `runtime/godot/modules/host_interface.md` ("Combat art").

| Clip | Shown keys | Gameplay it lines up with |
|---|---|---|
| `swing` | windup ticks → 1-4, active → **5-7**, recovery → 8-15 | damage window `[8, 15)` ticks: a hit can only land on keys 5-7 |
| `roll` | invulnerable ticks 0-14 → **2-9**, ticks 15-23 → 10-15 | i-frames hold exactly while keys 2-9 show |
| `hurt` | 18 hurt ticks → 1-15 | hurt lockout |
| `death` | 15 fps from key 0, holds 15 | KO (shown on a corpse during the retry countdown) |
| `block` | press tick → 1, 2, then guard 3-15 at 15 fps, holds 15 | protection from the press tick (unchanged) |
| `idle_combat` | loop 0-14 at 15 fps | — |
| enemy `telegraph` | 1-15 over `windup_ticks` (hold keys last) | the whole windup is shown before any attack |
| enemy `attack` | only the hit-window keys (dasher 2-8, warden 3-5) over `active_ticks` | every attack tick may land |
| enemy `recover`/`hurt`/`death` | 1-15 over recovery ticks / 12 ticks / real time | FSM state durations |

The staff rides `hand_r` (BoneAttachment3D) with rotation `(0.8660254, 0, 0, 0.5)` and the character's grip translation; stance hand props hide while combat owns the actor. Enemy face atlases switch with the clip (telegraph/attack → flare, hurt → hurt, death → closed). The Cairn Keeper elite variant is drawn with the dasher model; the `reed_burr` projectile is imported but unbound (no ranged template exists).

## Deviations from BINDING-PROPOSAL (all presentation-only)

- **Roll and hurt are phase-locked, not real time.** The runtime roll is 24 ticks (0.4 s) with 15 invulnerable ticks; 15 fps playback would show keys 0-5 only and put the documented i-frame keys 2-9 on ticks 8-39. Phase-locking makes keys 2-9 coincide exactly with invulnerability, as this lane's acceptance requires. The 18-tick hurt likewise shows the whole reaction.
- **Block raise is two ticks** because protection starts on the press tick.
- **Swing/roll end keys.** Key 0 of the swing is the guard pose on the tick before the press; key 15 of swing and roll is not reached because the pose returns to `idle_combat` on the tick the action ends.
- **Enemy attack skips the launch/spring keys** (dasher 1, warden 1-2): the FSM can land on any attack tick, so only hit-window keys show during it.
- **Enemy telegraph maps keys 1-15 over the windup** (ending on the hold keys) instead of "1..hold start, then hold", so the authored tremble/hold plays before the strike.
- Windup data is unchanged: Reedland Relay uses 36- and 42-tick windups (above the proposal's 30-tick readability note); the small contract fixtures keep 8 ticks.

## Evidence and tests

- `tests/test_characters_combat_import.py`: additive import, rejections before any write, the additive check on synthetic GLBs, staging pack selection and tamper rejection.
- `runtime/godot/tests/merge3_combat.gd` through `tools/merge3_combat.py` (`tests/test_merge3_combat.py`): every tick of the phase maps, real combat ticks (hits only on keys 5-7, no damage on roll keys 2-9 and contact on the first key-10 tick, full telegraphs before attacks, enemy contact only on hit-window keys), every key of every clip on the real skeletons for both packs, staff grip and stance props.
- The module bot's `combat_clips` audit in every physical playtest (`native.json`), required violation-free by acceptance.
