# GAPS2 shared-file hunks (for INTEG6 / CHARBIND)

Every hunk GAPS2 makes in a file that existed before the lane (base `demo-lane` 90ee6802). Line numbers are base lines
(`-`) / branch lines (`+`) from `git diff -U0 90ee6802 HEAD`. New files are listed at the end.

## Python

| File | Hunks (base → branch) | What | Gap |
|---|---|---|---|
| `adventure_maker/pack_rooms.py` | whole module | `load(settings, pack, games_root=None)`: games folder `rooms/<pack>/rooms.json` → `pack-rooms.json` → `rooms.json`; `rooms_from` variants; checks moved into `check(data, pack, accept)`; tri cap from `presentation.budget.room_tris` (max 8,000); optional `weather`/`captive`. `instantiate` unchanged | G1 G2 |
| `adventure_maker/newgame.py` | -172 +172 | `starter_spec(..., games_root=None)` | G2 |
| | -178 +178 | `pack_rooms.load(settings, pack_id, games_root)` | G2 |
| | -182 +183,7 | after `templates.build`: `metadata.rooms_source`; `premise_apply.apply` for arena_run_v1; `text_boxes` for other premise templates | G2 G3 G4 G9 |
| | -248 +255; -252 +259,3 | `create`: `starter_spec(..., games_root=root)`; `Not yet applied` list skips fields arena_run_v1 applies | G2 G3 |
| | -291 +301,3 | `create`: writes `audio/premise-slots.json` when the story has `audio` | G3 |
| | -362 +375,5 | card lines `Rooms: your games folder ...` and `Audio: ...` | G2 G3 |
| `adventure_maker/premise_packs.py` | -39 +40,7 | `RUNTIME_SCENE`, `BOSS_ROBOT`, `BOSS_SPEED` constants | G3 G4 |
| | -72 +80,28 | after `SCHEMA = obj(...)`: one block adding `bosses[].robot/speed_mps`, `scenes.list`, `text_boxes`; `_opaque` bounded check. **The `SCHEMA` rows themselves are untouched**, so charbind-lane's edit of the `robots`/`bosses` rows (`binding`) merges cleanly | G3 G4 G9 |
| | -76 +112,4 | `_check`: `x-validated-by` schemas use `_opaque` | G3 |
| | -113 +153,2 | `validate`: weather rooms must be in `rooms.order` | G3 |
| `adventure_maker/service.py` | -33 +34,20 | `proof_accepted`, `proof_reason` (module helpers) | G5 |
| | -350,2 +370,3 | `edit_candidate`: baseline accepted under the game's own policy; plain refusal | G5 |
| | -385,2 +406,14; -390,2 +423,7 | candidate re-checked under old and new policy; `reason`, `proof_status`, `note` in the result | G5 |
| `adventure_maker/audio_tools.py` | -132 +133; -134 +135,2 | import result gains `premise_apply.assign_imported(...)` keys | G3 |
| `contracts/premise/1.0.0.json` | generated | regenerate with `python3 -B -m tools.premise_contract` after any merge touching `premise_packs.py` (charbind-lane also regenerates it: resolve by regenerating, not by hand) | G3 G4 G9 |
| `tools/pack_rooms.py` | most of the module | room-anchors sources (cyber compiler, reachability check, `pack-rooms.json`); the castle path writes the same bytes (`--check` passes) | G1 |
| `tests/test_templates_arena.py` | -69 +69,2 | the npc-clip assertion. **Byte-identical to charbind-lane's hunk** (its comment names the CHARBIND bridge; in this branch `view/room.gd` plays the clip), so the two branches merge without a conflict | G3 |

## Runtime (GDScript)

| File | Hunks (base → branch) | What | Gap |
|---|---|---|---|
| `runtime/godot/view/presenter.gd` | -65 +66,6 | `var text_boxes`, `func boxed(text)` | G9 |
| | -170 +177,2 | `boot`: `text_boxes` from `metadata.presentation.text_boxes` (absent = true) | G9 |
| | -133 +139 | door reveal: `room_transition.reveal(boxed(name))` (no room-name card when off) | G9 |
| | -194 +202; -525 +533; -534 +542; -543 +551; -861 +869 | `last_text = boxed(...)` at boot, refusal, step text, room entry, restore | G9 |
| | -249 +257 | module event labels quiet when off | G9 |
| | -578 +586; -634 +642 | ending text and ending title line only when on | G9 |
| `runtime/godot/main.gd` | -32 +32,3; -33 +36,4 | `--replay` + `--capture_scenes=<dir>`: no auto-quit, attach `view/scene_capture.gd` | G14 |
| | -36 +43,3 | `--screens`: `scene_cards.enabled = false` before the first await | G12 sibling |
| | -56 +65 | `capture_all`: `last_text = boxed(room.description)` | G9 |
| `runtime/godot/playtest/runner.gd` | -138 +139,5 | `step()`: wait while `scene_cards.blocking()` (not the results card); control `no_scene_wait` | G12 |
| `runtime/godot/view/bot.gd` | -43 +43 | `view.boxed(description)` | G9 |
| `runtime/godot/view/room.gd` | -298 +299 | `play_clip(authored.clip)` when a placed character has a clip | G3 |

## Docs

| File | Hunks | What |
|---|---|---|
| `docs/TEMPLATES.md` | appended section 9 | what arena_run_v1 applies now; room data sources; text boxes |
| `docs/SCENES.md` | appended "GAPS2 additions" | story-file scenes, bots wait, capture command |

## New files (path-disjoint)

- `adventure_maker/premise_apply.py`, `adventure_maker/scene_capture.py`
- `kits/packs/neon_city_night/room-anchors.json`, `kits/packs/neon_city_night/pack-rooms.json`
- `runtime/godot/view/scene_capture.gd`, `runtime/godot/tests/gaps2_text.gd`
- `tests/test_gaps2_rooms.py`, `tests/test_gaps2_premise.py`, `tests/test_gaps2_edit.py`, `tests/test_gaps2_runtime.py`
- `docs/gaps2/proof.py`, `docs/gaps2/legacy_replays.py`, `docs/gaps2/owner_items.py`
- `docs/GAPS2-MODEL.md`, `docs/GAPS2-HUNKS.md`, `docs/GAPS2-RESULT.md`

## Known overlaps with charbind-lane (read at charbind fbdd8023)

- Same files: `adventure_maker/newgame.py` (its hunk is the cast-binding block, about 10 lines below GAPS2's insertion;
  no shared lines), `adventure_maker/premise_packs.py` (rows untouched here, see above), `tests/test_templates_arena.py`
  (identical hunk), `contracts/premise/1.0.0.json` (regenerate).
- Same behaviour, two places: the npc clip. CHARBIND plays it through its actor bridge, GAPS2 through `view/room.gd`
  `play_clip` (returns early when the clip is already playing, so both together play it once). After the merge one of
  the two can go; the data key (`presentation.rooms.<room>.characters.<id>.clip`) is the same.
