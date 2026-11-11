# TFIX hunks (branch `tfix-lane`, base `mergeprep-lane` `a4bdcfb7`)

Lane TFIX, Claude Opus 5.5. Every hunk in a file another lane may also edit, with its base line (`git diff a4bdcfb7 -U0`).
The base already carries native-lane `aed8c4a7` (FINALINT3 G8) and combatfix-lane `898d1a0a` (G7).

## Shared files

| File | Base line | Hunk | Fix |
|---|---|---|---|
| `adventure_maker/audit.py` | after 91 (`known_assets`) | new `pack_presets(pack)` (6 lines) | F2 |
| `adventure_maker/audit.py` | 137, 146, 158, 160 (`static_findings`) | `drawn = known \| pack_presets(pack)`; the piece and prop membership tests use `drawn`; suggestions still use `known` | F2 |
| `adventure_maker/create_flow.py` | after 59 (`CAMERA_CLEAR_M`) | `SPAWN_BOOM_M, BOOM_CLEAR_M = 4.5, 0.4` + 3 comment lines | F1c |
| `adventure_maker/create_flow.py` | after 902 (`Slots.__init__`) | `self.booms = []` | F1c |
| `adventure_maker/create_flow.py` | after 921 (`Slots.fits`) | boom segment check (2 lines) | F1c |
| `adventure_maker/create_flow.py` | after 945 (`pattern_size_m`) | new `spawn_boom`, `LANDMARK_STOP`, `LANDMARK_KEEP_M`, `mark_landmark` (30 lines) | F1c, F1a |
| `adventure_maker/create_flow.py` | after 1066 (`dress`, after `Slots(...)`) | booms for the outdoor room; `lm` slot and the vista-slot drop (6 lines) | F1c, F1a |
| `adventure_maker/create_flow.py` | 1094 (`dress`, vista branch) | landmark branch before `if it['where'] == 'vista'` (5 lines) | F1a |
| `adventure_maker/create_flow.py` | 1115 (`dress`, append) | `'scale': [scale] * 3` (was `[1, 1, 1]`; 1 for every other piece) | F1a |
| `adventure_maker/create_flow.py` | after 1165 (`name_rows`) | new `weather_rows(ctx, brief, mood)` (10 lines) | F6 |
| `adventure_maker/create_flow.py` | after 1242 (`stage_rooms`) | `mark_landmark(items, brief, inner_name, outdoor)` before the outdoor `dress` | F1a |
| `adventure_maker/create_flow.py` | after 1330 (`stage_rooms`) | `not_applied += weather_rows(ctx, brief, mood)` | F6 |
| `adventure_maker/create_patterns.json` | 44, 65 | plaza and plaza_snow: `"landmark_vista_m": [-7.0, 8.5, 90, 2]` | F1a |
| `skills/hermes64-create/SKILL.md` | 35 (golden path step 5) | one sentence: wait for every background run you started before replying (`process_manage`) | F8 |
| `skills/hermes64-create/SKILL.md` | after 105 (Advanced) | 3-line bullet: the one-time generator order | F7 |

New files (no other lane touches them): `tests/test_tfix_audit.py`, `tests/test_tfix_create.py`,
`docs/tfix/audit_remeasure.py`, `docs/tfix/landmark_sweep.py`, `docs/tfix/rooms_replan.py`, `docs/tfix/rebuild.py`,
`docs/tfix/fox_audit.py`, `docs/tfix/collect.py`, `docs/tfix/measured.json`, `docs/TFIX-HUNKS.md`, `docs/TFIX-RESULT.md`.

## Distance from the other lanes

- NATIVE (`075273bc` .. `aed8c4a7`): `create_flow.py` default `projects_root` (`run()`, base about line 2075), `native_hint.py`,
  `chat_text.py`, skills text (`hermes64-create` line 3 description; `hermes64/SKILL.md`). TFIX hunks are 1,700+ lines
  away in `create_flow.py` and at lines 35 and 105 of the skill.
- COMBATFIX: runtime combat (`runtime/godot/...`, `tools/combat_sfx_synth.py`). TFIX changes no runtime file.
- No tool, schema or tool-description change (27 tools; schema tokens unchanged).

## Trial merge

Scratch `git clone --shared` of `tfix-lane` `ed82ef52`: native-lane `aed8c4a7` and combatfix-lane `898d1a0a` are already
ancestors (no-op); current `mergeprep-lane` `bf1dc3fd` merges with 0 conflicts and 0 files in common with TFIX since
`a4bdcfb7`; 48 tests OK on the merge result. Details in `docs/TFIX-RESULT.md`.
